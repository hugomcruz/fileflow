"""add file_pattern to rules

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("file_pattern", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("rules", "file_pattern")
