"""rule: add source_connection_id and target_connection_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column(
            "source_connection_id",
            sa.String(),
            sa.ForeignKey("oauth_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "rules",
        sa.Column(
            "target_connection_id",
            sa.String(),
            sa.ForeignKey("oauth_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rules", "target_connection_id")
    op.drop_column("rules", "source_connection_id")
