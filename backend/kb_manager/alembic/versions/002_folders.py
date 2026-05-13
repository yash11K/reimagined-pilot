"""Folders table + kb_files.folder_id for SharePoint-style file manager.

Adds:
  - folders table with self-FK parent_folder_id (ON DELETE RESTRICT so
    cascade behaviour is explicit in app code via ?cascade=true).
  - case-insensitive uniqueness of (parent_folder_id, name) — root folders
    use a partial index since NULL parent_folder_id wouldn't be deduped by
    a plain UNIQUE constraint.
  - kb_files.folder_id (nullable; ON DELETE SET NULL).

Revision ID: 002_folders
Revises: 001_baseline
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision = "002_folders"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_folder_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kb_target", sa.Text(), nullable=False),
        sa.Column("default_brand", sa.Text(), nullable=True),
        sa.Column("default_region", sa.Text(), nullable=True),
        sa.Column("default_language", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_foreign_key(
        "fk_folders_parent", "folders", "folders",
        ["parent_folder_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_folders_parent", "folders", ["parent_folder_id"])
    op.create_index("ix_folders_kb_target", "folders", ["kb_target"])

    # Case-insensitive uniqueness of name within a parent. Two partial indexes
    # so NULL parent_folder_id (root folders) is also deduped — UNIQUE alone
    # would let multiple roots share a name because NULL != NULL.
    op.execute(
        "CREATE UNIQUE INDEX uq_folders_parent_name_ci "
        "ON folders (parent_folder_id, lower(name)) "
        "WHERE parent_folder_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_folders_root_name_ci "
        "ON folders (kb_target, lower(name)) "
        "WHERE parent_folder_id IS NULL"
    )

    # kb_files.folder_id — nullable FK, SET NULL on folder delete so a
    # non-cascade folder delete path can't leave dangling FKs.
    op.add_column(
        "kb_files",
        sa.Column("folder_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_kb_files_folder", "kb_files", "folders",
        ["folder_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_kb_files_folder_id", "kb_files", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_kb_files_folder_id", table_name="kb_files")
    op.drop_constraint("fk_kb_files_folder", "kb_files", type_="foreignkey")
    op.drop_column("kb_files", "folder_id")

    op.execute("DROP INDEX IF EXISTS uq_folders_root_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_folders_parent_name_ci")
    op.drop_index("ix_folders_kb_target", table_name="folders")
    op.drop_index("ix_folders_parent", table_name="folders")
    op.drop_constraint("fk_folders_parent", "folders", type_="foreignkey")
    op.drop_table("folders")
