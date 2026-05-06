"""Add ON DELETE CASCADE to ingestion_jobs.source_id and kb_files.job_id.

This makes ``DELETE FROM sources`` propagate cleanly through
``ingestion_jobs`` and ``kb_files`` instead of relying on the API layer
to delete child rows in the right order. The junction table
``source_kb_files`` already had CASCADE on both sides since baseline.

Revision ID: 004_cascade_deletes
Revises: 003_add_progress_pct
Create Date: 2026-04-28 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "004_cascade_deletes"
down_revision = "003_add_progress_pct"
branch_labels = None
depends_on = None


# Default Postgres FK constraint naming: <table>_<column>_fkey
_INGESTION_JOBS_FK = "ingestion_jobs_source_id_fkey"
_KB_FILES_FK = "kb_files_job_id_fkey"


def upgrade() -> None:
    # ingestion_jobs.source_id → sources.id   (CASCADE)
    op.drop_constraint(_INGESTION_JOBS_FK, "ingestion_jobs", type_="foreignkey")
    op.create_foreign_key(
        _INGESTION_JOBS_FK,
        source_table="ingestion_jobs",
        referent_table="sources",
        local_cols=["source_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # kb_files.job_id → ingestion_jobs.id   (CASCADE)
    op.drop_constraint(_KB_FILES_FK, "kb_files", type_="foreignkey")
    op.create_foreign_key(
        _KB_FILES_FK,
        source_table="kb_files",
        referent_table="ingestion_jobs",
        local_cols=["job_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # kb_files.job_id → ingestion_jobs.id   (no cascade)
    op.drop_constraint(_KB_FILES_FK, "kb_files", type_="foreignkey")
    op.create_foreign_key(
        _KB_FILES_FK,
        source_table="kb_files",
        referent_table="ingestion_jobs",
        local_cols=["job_id"],
        remote_cols=["id"],
    )

    # ingestion_jobs.source_id → sources.id   (no cascade)
    op.drop_constraint(_INGESTION_JOBS_FK, "ingestion_jobs", type_="foreignkey")
    op.create_foreign_key(
        _INGESTION_JOBS_FK,
        source_table="ingestion_jobs",
        referent_table="sources",
        local_cols=["source_id"],
        remote_cols=["id"],
    )
