"""multi-connection support: drop unique constraint, add display_name

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the unique constraint that prevented multiple connections per provider
    op.drop_constraint("oauth_connections_user_id_provider_key", "oauth_connections", type_="unique")
    # Add a human-readable label for each connection (e.g. "Work OneDrive")
    op.add_column("oauth_connections", sa.Column("display_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("oauth_connections", "display_name")
    op.create_unique_constraint(
        "oauth_connections_user_id_provider_key",
        "oauth_connections",
        ["user_id", "provider"],
    )
