"""rule: add recursive flag for source path

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("recursive", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("rules", "recursive")
