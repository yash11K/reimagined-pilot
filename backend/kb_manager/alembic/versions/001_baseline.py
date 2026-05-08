"""Baseline migration — v2 simplified data model with denormalized source state.

Tables: sources, ingestion_jobs, kb_files, source_kb_files, queue_items, run_pages.

Source carries denormalized fields (display_status, active_job_id, active_file_id,
run_count, last_run_at). The `run_count` and `last_run_at` columns are kept fresh
by DB triggers on ingestion_jobs; the rest are app-side maintained.

Revision ID: 001_baseline
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Required extensions ---
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()

    # --- sources (created without FKs that point at later tables) ---
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("kb_target", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("display_status", sa.Text(), nullable=False, server_default=sa.text("'idle'")),
        sa.Column("active_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("active_file_id", UUID(as_uuid=True), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_run_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("scout_summary", JSONB(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("parent_source_id", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("type", "url", name="uq_sources_type_url"),
    )
    op.create_index("ix_sources_status", "sources", ["status"])
    op.create_index("ix_sources_listing", "sources", ["origin", "status", "created_at"])
    op.create_index("ix_sources_filters", "sources", ["brand", "region", "kb_target"])
    op.execute("CREATE INDEX ix_sources_url_trgm ON sources USING gin (url gin_trgm_ops)")
    op.execute("CREATE INDEX ix_sources_metadata ON sources USING gin (metadata)")

    # parent_source_id self-FK
    op.create_foreign_key(
        "fk_sources_parent", "sources", "sources",
        ["parent_source_id"], ["id"], ondelete="SET NULL",
    )

    # --- ingestion_jobs ---
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("steering_prompt", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_source_status", "ingestion_jobs", ["source_id", "status"])

    # --- kb_files ---
    op.create_table(
        "kb_files",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("md_content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("kb_target", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
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

    # --- Now wire deferred FKs from sources to ingestion_jobs / kb_files ---
    op.create_foreign_key(
        "fk_sources_active_job", "sources", "ingestion_jobs",
        ["active_job_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sources_active_file", "sources", "kb_files",
        ["active_file_id"], ["id"], ondelete="SET NULL",
    )

    # --- source_kb_files (M2M junction) ---
    op.create_table(
        "source_kb_files",
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kb_file_id", UUID(as_uuid=True), sa.ForeignKey("kb_files.id", ondelete="CASCADE"), primary_key=True),
    )

    # --- queue_items ---
    op.create_table(
        "queue_items",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("next_attempt_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_heartbeat", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("worker_id", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_queue_items_status", "queue_items", ["status"])
    # Partial unique: at most one active queue row per source
    op.execute(
        "CREATE UNIQUE INDEX uq_queue_active_source ON queue_items (source_id) "
        "WHERE status IN ('queued', 'processing')"
    )

    # --- run_pages ---
    op.create_table(
        "run_pages",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("kb_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_run_pages_job_id", "run_pages", ["job_id"])

    # --- Triggers: maintain sources.run_count + sources.last_run_at ---
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_source_job_insert() RETURNS TRIGGER AS $$
        BEGIN
            UPDATE sources
               SET run_count = run_count + 1
             WHERE id = NEW.source_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER ingestion_jobs_after_insert
        AFTER INSERT ON ingestion_jobs
        FOR EACH ROW EXECUTE FUNCTION trg_source_job_insert();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION trg_source_job_status_update() RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.status IN ('completed', 'failed')
               AND (OLD.status IS DISTINCT FROM NEW.status) THEN
                UPDATE sources
                   SET last_run_at = COALESCE(NEW.completed_at, now())
                 WHERE id = NEW.source_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER ingestion_jobs_after_status_update
        AFTER UPDATE OF status ON ingestion_jobs
        FOR EACH ROW EXECUTE FUNCTION trg_source_job_status_update();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ingestion_jobs_after_status_update ON ingestion_jobs")
    op.execute("DROP TRIGGER IF EXISTS ingestion_jobs_after_insert ON ingestion_jobs")
    op.execute("DROP FUNCTION IF EXISTS trg_source_job_status_update()")
    op.execute("DROP FUNCTION IF EXISTS trg_source_job_insert()")
    op.drop_table("run_pages")
    op.drop_table("queue_items")
    op.drop_table("source_kb_files")
    op.drop_constraint("fk_sources_active_file", "sources", type_="foreignkey")
    op.drop_constraint("fk_sources_active_job", "sources", type_="foreignkey")
    op.drop_table("kb_files")
    op.drop_table("ingestion_jobs")
    op.drop_constraint("fk_sources_parent", "sources", type_="foreignkey")
    op.drop_table("sources")
