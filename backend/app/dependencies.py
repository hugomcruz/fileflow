from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def create_jwt(user_id: str, email: str, name: str | None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expiry_days)
    payload = {"sub": user_id, "email": email, "name": name, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    _auth: Annotated[str | None, Query()] = None,
) -> dict:
    """
    Accepts JWT from Authorization: Bearer header OR ?_auth= query param.
    The query param is used for browser-redirect OAuth flows (connect endpoints).
    """
    token: str | None = None
    if credentials:
        token = credentials.credentials
    elif _auth:
        token = _auth

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return _decode_token(token)


CurrentUser = Annotated[dict, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
