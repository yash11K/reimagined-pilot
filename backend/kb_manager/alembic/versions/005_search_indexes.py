"""Add pg_trgm extension + GIN trigram indexes on search-target columns.

The list endpoints and global search use ``ILIKE '%term%'`` patterns on
``kb_files.title``, ``kb_files.source_url``, and ``sources.url``. Without
trigram indexes these degrade into table scans as data grows; with the
indexes Postgres uses GIN trigram lookup and stays fast at ~10K+ rows.

Revision ID: 005_search_indexes
Revises: 004_cascade_deletes
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "005_search_indexes"
down_revision = "004_cascade_deletes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The pg_trgm extension is required for the gin_trgm_ops opclass below.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_index(
        "ix_kb_files_title_trgm",
        "kb_files",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_kb_files_source_url_trgm",
        "kb_files",
        ["source_url"],
        postgresql_using="gin",
        postgresql_ops={"source_url": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_sources_url_trgm",
        "sources",
        ["url"],
        postgresql_using="gin",
        postgresql_ops={"url": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_sources_url_trgm", table_name="sources")
    op.drop_index("ix_kb_files_source_url_trgm", table_name="kb_files")
    op.drop_index("ix_kb_files_title_trgm", table_name="kb_files")
    # Leave pg_trgm extension installed — other migrations or operator
    # tooling may rely on it.
