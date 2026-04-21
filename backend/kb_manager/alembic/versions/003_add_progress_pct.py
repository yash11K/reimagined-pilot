"""Add progress_pct column to ingestion_jobs.

Revision ID: 003_add_progress_pct
Revises: 002_queue_improvements
Create Date: 2026-04-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "003_add_progress_pct"
down_revision = "002_queue_improvements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "progress_pct")
