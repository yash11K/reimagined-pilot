"""Queue improvements — retries, heartbeat, priority, dedup index.

Revision ID: 002_queue_improvements
Revises: 001_baseline
Create Date: 2026-04-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

# revision identifiers, used by Alembic.
revision = "002_queue_improvements"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("queue_items", sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("queue_items", sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")))
    op.add_column("queue_items", sa.Column("next_attempt_at", TIMESTAMP(timezone=True), nullable=True))
    op.add_column("queue_items", sa.Column("last_heartbeat", TIMESTAMP(timezone=True), nullable=True))
    op.add_column("queue_items", sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")))

    # Partial unique index: only one active (queued/processing) item per URL
    op.create_index(
        "uq_queue_active_url",
        "queue_items",
        ["url"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index("uq_queue_active_url", table_name="queue_items")
    op.drop_column("queue_items", "priority")
    op.drop_column("queue_items", "last_heartbeat")
    op.drop_column("queue_items", "next_attempt_at")
    op.drop_column("queue_items", "max_retries")
    op.drop_column("queue_items", "retry_count")
