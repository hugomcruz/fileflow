"""
Proactive + reactive OAuth token refresh for OneDrive and Dropbox connections.

Usage in processor:
    conn = await ensure_fresh_token(db, conn)
    # ...
    # on httpx.HTTPStatusError with status 401:
    conn = await refresh_token_now(db, conn)
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models import OAuthConnection

logger = logging.getLogger(__name__)

# Refresh if the token expires within this window
_REFRESH_BUFFER = timedelta(minutes=5)

MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
DB_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"


def _is_expiring(conn: OAuthConnection) -> bool:
    if conn.expires_at is None:
        # Unknown expiry — assume the token could have expired (Dropbox tokens last ~4 h).
        # A failed refresh here is caught and logged; the job continues normally.
        return True
    now = datetime.now(timezone.utc)
    exp = conn.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp - now < _REFRESH_BUFFER


async def _do_refresh_onedrive(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            MS_TOKEN_URL,
            data={
                "client_id": settings.onedrive_client_id,
                "client_secret": settings.onedrive_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        res.raise_for_status()
        return res.json()


async def _do_refresh_dropbox(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            DB_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(settings.dropbox_app_key, settings.dropbox_app_secret),
        )
        res.raise_for_status()
        return res.json()


async def _apply_new_tokens(db, conn: OAuthConnection, tokens: dict) -> OAuthConnection:
    conn.access_token = tokens["access_token"]
    if tokens.get("refresh_token"):
        conn.refresh_token = tokens["refresh_token"]
    if tokens.get("expires_in"):
        conn.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
    await db.commit()
    await db.refresh(conn)
    logger.info("Refreshed token for connection %s (%s)", conn.id, conn.provider)
    return conn


async def refresh_token_now(db, conn: OAuthConnection) -> OAuthConnection:
    """Force-refresh the token regardless of expiry. Raises if no refresh_token or refresh fails."""
    if not conn.refresh_token:
        raise RuntimeError(
            f"Connection {conn.id} ({conn.provider}) has no refresh token – user must reauthenticate."
        )
    try:
        if conn.provider == "onedrive":
            tokens = await _do_refresh_onedrive(conn.refresh_token)
        elif conn.provider == "dropbox":
            tokens = await _do_refresh_dropbox(conn.refresh_token)
        else:
            raise RuntimeError(f"No refresh logic for provider '{conn.provider}'")
        return await _apply_new_tokens(db, conn, tokens)
    except Exception as exc:
        logger.error("Token refresh failed for connection %s: %s", conn.id, exc)
        raise


async def ensure_fresh_token(db, conn: OAuthConnection) -> OAuthConnection:
    """Refresh the token if it is expiring soon. Returns the (possibly updated) connection."""
    if _is_expiring(conn):
        logger.info(
            "Token for connection %s (%s) is expiring soon (or expiry unknown), refreshing proactively.",
            conn.id, conn.provider,
        )
        try:
            return await refresh_token_now(db, conn)
        except Exception as exc:
            logger.warning(
                "Proactive refresh failed for connection %s (%s): %s — will attempt reactive refresh on 401.",
                conn.id, conn.provider, exc,
            )
    return conn
