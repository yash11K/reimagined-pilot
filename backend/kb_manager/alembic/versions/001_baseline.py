"""Baseline migration — create all tables (v3 simplified sources, no discovery fields).

Revision ID: 001_baseline
Revises: None
Create Date: 2026-04-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID

# revision identifiers, used by Alembic.
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- sources ---
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("kb_target", sa.Text(), nullable=False),
        sa.Column("is_scouted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_ingested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("scout_summary", JSONB(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("last_ingested_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("type", "url", name="uq_sources_type_url"),
    )
    op.create_index("ix_sources_status", "sources", ["status"])

    # --- ingestion_jobs ---
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("steering_prompt", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])

    # --- kb_files ---
    op.create_table(
        "kb_files",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("md_content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("kb_target", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("visibility", sa.Text(), nullable=True),
        sa.Column("tags", ARRAY(sa.Text()), nullable=True),
        sa.Column("modify_date", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("quality_verdict", sa.Text(), nullable=True),
        sa.Column("quality_reasoning", sa.Text(), nullable=True),
        sa.Column("uniqueness_verdict", sa.Text(), nullable=True),
        sa.Column("uniqueness_reasoning", sa.Text(), nullable=True),
        sa.Column("similar_file_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("s3_key", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_kb_files_status", "kb_files", ["status"])
    op.create_index("ix_kb_files_job_id", "kb_files", ["job_id"])
    op.create_index("ix_kb_files_kb_target", "kb_files", ["kb_target"])

    # --- source_kb_files (M2M junction — no relationship type) ---
    op.create_table(
        "source_kb_files",
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kb_file_id", UUID(as_uuid=True), sa.ForeignKey("kb_files.id", ondelete="CASCADE"), primary_key=True),
    )

    # --- nav_tree_cache ---
    op.create_table(
        "nav_tree_cache",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("root_url", sa.Text(), unique=True, nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("tree_data", JSONB(), nullable=True),
        sa.Column("fetched_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
    )

    # --- queue_items ---
    op.create_table(
        "queue_items",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("kb_target", sa.Text(), nullable=False, server_default=sa.text("'public'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id"), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_queue_items_status", "queue_items", ["status"])


def downgrade() -> None:
    op.drop_table("queue_items")
    op.drop_table("nav_tree_cache")
    op.drop_table("source_kb_files")
    op.drop_table("kb_files")
    op.drop_table("ingestion_jobs")
    op.drop_table("sources")
