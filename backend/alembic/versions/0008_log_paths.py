"""processing_logs: add source_path, target_path, source_connection, target_connection

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_logs", sa.Column("source_path", sa.String(), nullable=True))
    op.add_column("processing_logs", sa.Column("target_path", sa.String(), nullable=True))
    op.add_column("processing_logs", sa.Column("source_connection", sa.String(), nullable=True))
    op.add_column("processing_logs", sa.Column("target_connection", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_logs", "target_connection")
    op.drop_column("processing_logs", "source_connection")
    op.drop_column("processing_logs", "target_path")
    op.drop_column("processing_logs", "source_path")
