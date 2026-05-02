import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.database import async_session_factory
from app.dependencies import CurrentUser, DB, create_jwt
from app.models import OAuthConnection, User
from app.schemas import EmailLoginIn, EmailRegisterIn, TokenOut, UserOut

logger = logging.getLogger(__name__)
router = APIRouter()

_PBKDF2_ITERS = 260_000


def _hash_password(plain: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, _PBKDF2_ITERS)
    return base64.b64encode(salt + dk).decode()


def _verify_password(plain: str, stored: str) -> bool:
    raw = base64.b64decode(stored.encode())
    salt, dk = raw[:16], raw[16:]
    check = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, _PBKDF2_ITERS)
    return hmac.compare_digest(dk, check)

# ─── In-memory OAuth state store (use Redis in production) ───────────────────
_oauth_states: dict[str, dict] = {}

MS_AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MS_GRAPH_URL = "https://graph.microsoft.com/v1.0"
OD_AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
OD_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
DB_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DB_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"


def _apple_client_secret() -> str:
    """Generate a short-lived client_secret JWT signed with ES256 for Apple."""
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iss": settings.apple_team_id,
        "iat": now,
        "exp": now + 86400 * 180,  # 6 months (Apple's maximum)
        "aud": "https://appleid.apple.com",
        "sub": settings.apple_client_id,
    }
    return jose_jwt.encode(
        payload,
        settings.apple_private_key,
        algorithm="ES256",
        headers={"kid": settings.apple_key_id},
    )


def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload of a JWT without verifying the signature."""
    try:
        _, payload_b64, _ = token.split(".")
        # Re-add Base64 padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise ValueError(f"Cannot decode JWT payload: {exc}") from exc


def _gen_state(data: dict | None = None) -> str:
    state = secrets.token_hex(16)
    _oauth_states[state] = data or {}
    return state


def _pop_state(state: str | None) -> dict | None:
    if not state:
        return None
    return _oauth_states.pop(state, None)


# ─── Upsert helper ────────────────────────────────────────────────────────────

async def _upsert_user(db, email: str, name: str | None, avatar: str | None, provider: str, provider_id: str) -> User:
    # Only overwrite stored name/avatar when new values are non-None so that
    # Apple's first-login-only name isn't erased on subsequent sign-ins.
    update_set: dict = {"provider": provider, "provider_id": provider_id}
    if name is not None:
        update_set["name"] = name
    if avatar is not None:
        update_set["avatar"] = avatar

    stmt = (
        pg_insert(User)
        .values(
            email=email,
            name=name,
            avatar=avatar,
            provider=provider,
            provider_id=provider_id,
        )
        .on_conflict_do_update(
            index_elements=["email"],
            set_=update_set,
        )
        .returning(User)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def _upsert_connection(db, user_id: str, provider: str, access_token: str,
                              refresh_token: str | None, expires_at: datetime | None,
                              scope: str | None = None,
                              display_name: str | None = None,
                              connection_id: str | None = None) -> None:
    """Update an existing connection row when connection_id is given, otherwise insert new."""
    if connection_id:
        result = await db.execute(
            select(OAuthConnection).where(
                OAuthConnection.id == connection_id,
                OAuthConnection.user_id == user_id,
            )
        )
        conn = result.scalar_one_or_none()
        if conn:
            conn.access_token = access_token
            if refresh_token:
                conn.refresh_token = refresh_token
            conn.expires_at = expires_at
            if scope:
                conn.scope = scope
            if display_name is not None:
                conn.display_name = display_name
            await db.commit()
            return
    # No connection_id (or not found) — insert new row
    conn = OAuthConnection(
        user_id=user_id,
        provider=provider,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scope=scope,
    )
    db.add(conn)
    await db.commit()


# ─── Google OAuth ─────────────────────────────────────────────────────────────

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@router.get("/google")
async def google_login():
    state = _gen_state()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_callback_url,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "access_type": "offline",
    }
    url = GOOGLE_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: DB = None,
):
    state_data = _pop_state(state)
    if error or not code or state_data is None:
        return RedirectResponse(f"{settings.frontend_url}/login?error=auth_failed")

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "redirect_uri": settings.google_callback_url,
                    "grant_type": "authorization_code",
                },
            )
            token_res.raise_for_status()
            tokens = token_res.json()

            userinfo_res = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo_res.raise_for_status()
            profile = userinfo_res.json()

        email = profile.get("email", "")
        if not email:
            raise ValueError("No email returned from Google")

        user = await _upsert_user(
            db,
            email=email,
            name=profile.get("name"),
            avatar=profile.get("picture"),
            provider="google",
            provider_id=profile["sub"],
        )
        token = create_jwt(user.id, user.email, user.name)
        return RedirectResponse(f"{settings.frontend_url}/auth/callback?token={token}")
    except Exception:
        logger.exception("Google OAuth error")
        return RedirectResponse(f"{settings.frontend_url}/login?error=auth_failed")


# ─── Microsoft OAuth ──────────────────────────────────────────────────────────

@router.get("/microsoft")
async def microsoft_login():
    state = _gen_state()
    params = {
        "client_id": settings.microsoft_client_id,
        "response_type": "code",
        "redirect_uri": settings.microsoft_callback_url,
        "scope": "openid profile email User.Read",
        "state": state,
        "response_mode": "query",
        "prompt": "select_account",
    }
    url = MS_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/microsoft/callback")
async def microsoft_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: DB = None,
):
    state_data = _pop_state(state)
    if error or not code or state_data is None:
        return RedirectResponse(f"{settings.frontend_url}/login?error=auth_failed")

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                MS_TOKEN_URL,
                data={
                    "client_id": settings.microsoft_client_id,
                    "client_secret": settings.microsoft_client_secret,
                    "code": code,
                    "redirect_uri": settings.microsoft_callback_url,
                    "grant_type": "authorization_code",
                },
            )
            token_res.raise_for_status()
            tokens = token_res.json()

            profile_res = await client.get(
                f"{MS_GRAPH_URL}/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            profile_res.raise_for_status()
            profile = profile_res.json()

        email = profile.get("mail") or profile.get("userPrincipalName", "")
        if not email:
            raise ValueError("No email returned from Microsoft")

        user = await _upsert_user(
            db,
            email=email,
            name=profile.get("displayName"),
            avatar=None,
            provider="microsoft",
            provider_id=profile["id"],
        )
        token = create_jwt(user.id, user.email, user.name)
        return RedirectResponse(f"{settings.frontend_url}/auth/callback?token={token}")
    except Exception:
        logger.exception("Microsoft OAuth error")
        return RedirectResponse(f"{settings.frontend_url}/login?error=auth_failed")


# ─── OneDrive connect ─────────────────────────────────────────────────────────

@router.get("/onedrive/connect")
async def onedrive_connect(current_user: CurrentUser, display_name: str | None = None, connection_id: str | None = None):
    state = _gen_state({"user_id": current_user["sub"], "display_name": display_name, "connection_id": connection_id})
    params = {
        "client_id": settings.onedrive_client_id,
        "response_type": "code",
        "redirect_uri": settings.onedrive_callback_url,
        "scope": "Files.ReadWrite.All offline_access",
        "state": state,
        "response_mode": "query",
        "prompt": "select_account",
    }
    url = OD_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/onedrive/callback")
async def onedrive_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: DB = None,
):
    state_data = _pop_state(state)
    if error or not code or not state_data or not state_data.get("user_id"):
        return RedirectResponse(
            f"{settings.frontend_url}/connections?error=connect_failed&provider=onedrive"
        )

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                OD_TOKEN_URL,
                data={
                    "client_id": settings.onedrive_client_id,
                    "client_secret": settings.onedrive_client_secret,
                    "code": code,
                    "redirect_uri": settings.onedrive_callback_url,
                    "grant_type": "authorization_code",
                },
            )
            token_res.raise_for_status()
            tokens = token_res.json()

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        await _upsert_connection(
            db,
            user_id=state_data["user_id"],
            provider="onedrive",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
            scope="Files.ReadWrite.All",
            display_name=state_data.get("display_name"),
            connection_id=state_data.get("connection_id"),
        )
        return RedirectResponse(f"{settings.frontend_url}/connections?success=onedrive")
    except Exception:
        logger.exception("OneDrive connect error")
        return RedirectResponse(
            f"{settings.frontend_url}/connections?error=connect_failed&provider=onedrive"
        )


# ─── Dropbox connect ──────────────────────────────────────────────────────────

@router.get("/dropbox/connect")
async def dropbox_connect(current_user: CurrentUser, display_name: str | None = None, connection_id: str | None = None):
    state = _gen_state({"user_id": current_user["sub"], "display_name": display_name, "connection_id": connection_id})
    params = {
        "client_id": settings.dropbox_app_key,
        "response_type": "code",
        "redirect_uri": settings.dropbox_callback_url,
        "token_access_type": "offline",
        "state": state,
    }
    url = DB_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/dropbox/callback")
async def dropbox_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: DB = None,
):
    state_data = _pop_state(state)
    if error or not code or not state_data or not state_data.get("user_id"):
        return RedirectResponse(
            f"{settings.frontend_url}/connections?error=connect_failed&provider=dropbox"
        )

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                DB_TOKEN_URL,
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.dropbox_callback_url,
                },
                auth=(settings.dropbox_app_key, settings.dropbox_app_secret),
            )
            token_res.raise_for_status()
            tokens = token_res.json()

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        await _upsert_connection(
            db,
            user_id=state_data["user_id"],
            provider="dropbox",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
            display_name=state_data.get("display_name"),
            connection_id=state_data.get("connection_id"),
        )
        return RedirectResponse(f"{settings.frontend_url}/connections?success=dropbox")
    except Exception:
        logger.exception("Dropbox connect error")
        return RedirectResponse(
            f"{settings.frontend_url}/connections?error=connect_failed&provider=dropbox"
        )


# ─── Google Drive connect ─────────────────────────────────────────────────────
# (separate from Google *login* – this connects Drive storage for rules)

GOOGLE_DRIVE_CONNECT_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_DRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@router.get("/googledrive/connect")
async def googledrive_connect(current_user: CurrentUser, display_name: str | None = None, connection_id: str | None = None):
    state = _gen_state({"user_id": current_user["sub"], "display_name": display_name, "connection_id": connection_id})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_drive_callback_url,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = GOOGLE_DRIVE_CONNECT_AUTH_URL + "?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/googledrive/callback")
async def googledrive_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: DB = None,
):
    state_data = _pop_state(state)
    if error or not code or not state_data or not state_data.get("user_id"):
        return RedirectResponse(
            f"{settings.frontend_url}/connections?error=connect_failed&provider=googledrive"
        )

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                GOOGLE_DRIVE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "redirect_uri": settings.google_drive_callback_url,
                    "grant_type": "authorization_code",
                },
            )
            token_res.raise_for_status()
            tokens = token_res.json()

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        await _upsert_connection(
            db,
            user_id=state_data["user_id"],
            provider="googledrive",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
            scope="https://www.googleapis.com/auth/drive",
            display_name=state_data.get("display_name"),
            connection_id=state_data.get("connection_id"),
        )
        return RedirectResponse(f"{settings.frontend_url}/connections?success=googledrive")
    except Exception:
        logger.exception("Google Drive connect error")
        return RedirectResponse(
            f"{settings.frontend_url}/connections?error=connect_failed&provider=googledrive"
        )


# ─── Apple OAuth ─────────────────────────────────────────────────────────────

@router.get("/apple")
async def apple_login():
    state = _gen_state()
    params = {
        "client_id": settings.apple_client_id,
        "redirect_uri": settings.apple_callback_url,
        "response_type": "code",
        "scope": "openid name email",
        "response_mode": "form_post",
        "state": state,
    }
    return RedirectResponse(f"{APPLE_AUTH_URL}?{urlencode(params)}")


@router.post("/apple/callback")
async def apple_callback(
    request: Request,
    db: DB = None,
):
    form = await request.form()
    code = form.get("code")
    state = form.get("state")
    error = form.get("error")
    # Apple only sends 'user' JSON on the very first authorisation
    user_json: str | None = form.get("user")  # type: ignore[assignment]

    state_data = _pop_state(state)  # type: ignore[arg-type]
    if error or not code or state_data is None:
        return RedirectResponse(
            f"{settings.frontend_url}/login?error=auth_failed", status_code=303
        )

    try:
        client_secret = _apple_client_secret()
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                APPLE_TOKEN_URL,
                data={
                    "client_id": settings.apple_client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": settings.apple_callback_url,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_res.raise_for_status()
            tokens = token_res.json()

        id_token = tokens.get("id_token", "")
        if not id_token:
            raise ValueError("No id_token in Apple token response")

        claims = _decode_jwt_payload(id_token)
        apple_user_id = claims.get("sub")
        email = claims.get("email", "")
        if not email or not apple_user_id:
            raise ValueError("Missing email or sub in Apple id_token")

        # Parse name — only present on the first sign-in
        name: str | None = None
        if user_json:
            try:
                user_data = json.loads(user_json)
                name_data = user_data.get("name", {})
                first = name_data.get("firstName", "")
                last = name_data.get("lastName", "")
                name = f"{first} {last}".strip() or None
            except Exception:
                pass  # non-critical — we'll store None

        user = await _upsert_user(
            db,
            email=email,
            name=name,
            avatar=None,
            provider="apple",
            provider_id=apple_user_id,
        )
        token = create_jwt(user.id, user.email, user.name)
        # 303 ensures the browser follows with a GET
        return RedirectResponse(
            f"{settings.frontend_url}/auth/callback?token={token}", status_code=303
        )
    except Exception:
        logger.exception("Apple OAuth error")
        return RedirectResponse(
            f"{settings.frontend_url}/login?error=auth_failed", status_code=303
        )


# ─── Email / password auth ────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def email_register(body: EmailRegisterIn, db: DB):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email,
        name=body.name,
        provider="email",
        provider_id=body.email,
        password_hash=_hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    logger.info("email_register: created user %s", body.email)
    return {"detail": "Account created"}


@router.post("/login", response_model=TokenOut)
async def email_login(body: EmailLoginIn, db: DB):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("email_login: no user found for email=%s", body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.password_hash:
        logger.warning("email_login: user %s has no password_hash (provider=%s)", body.email, user.provider)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not _verify_password(body.password, user.password_hash):
        logger.warning("email_login: password mismatch for user %s", body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(token=create_jwt(user.id, user.email, user.name))


# ─── Current user ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(User)
        .where(User.id == current_user["sub"])
        .options(selectinload(User.connections))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
