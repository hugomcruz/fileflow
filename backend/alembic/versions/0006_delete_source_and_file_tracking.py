"""rule: add delete_source; processing_log: add source_file_id

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("delete_source", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "processing_logs",
        sa.Column("source_file_id", sa.String(), nullable=True),
    )
    # Index speeds up the already-processed lookup in the processor
    op.create_index(
        "ix_processing_logs_source_file_id",
        "processing_logs",
        ["source_file_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_logs_source_file_id", table_name="processing_logs")
    op.drop_column("processing_logs", "source_file_id")
    op.drop_column("rules", "delete_source")
