from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, or_, select

from app.dependencies import CurrentUser, DB
from app.models import OAuthConnection, Rule
from app.schemas import ConnectionOut, ConnectionRename

router = APIRouter()

VALID_PROVIDERS = {"onedrive", "dropbox", "googledrive"}


@router.get("/", response_model=list[ConnectionOut])
async def list_connections(current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.user_id == current_user["sub"])
    )
    return result.scalars().all()


@router.patch("/{connection_id}", response_model=ConnectionOut)
async def rename_connection(connection_id: str, body: ConnectionRename, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.id == connection_id,
            OAuthConnection.user_id == current_user["sub"],
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn.display_name = body.display_name
    await db.commit()
    await db.refresh(conn)
    return conn


@router.delete("/{connection_id}", status_code=204)
async def disconnect_connection(connection_id: str, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.id == connection_id,
            OAuthConnection.user_id == current_user["sub"],
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Block deletion if any rule references this connection
    rules_result = await db.execute(
        select(Rule.id).where(
            Rule.user_id == current_user["sub"],
            or_(
                Rule.source_connection_id == connection_id,
                Rule.target_connection_id == connection_id,
            ),
        ).limit(1)
    )
    if rules_result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="This connection is used by one or more rules. Remove those rules first.",
        )

    await db.execute(
        delete(OAuthConnection).where(
            OAuthConnection.id == connection_id,
            OAuthConnection.user_id == current_user["sub"],
        )
    )
    await db.commit()
