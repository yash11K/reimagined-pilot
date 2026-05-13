"""CRUD + tree walks for the folders table."""

import logging
import math
import uuid
from typing import Any

from sqlalchemy import and_, delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import Folder, KBFile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_folder(db: AsyncSession, **kwargs: Any) -> Folder:
    """Insert a new folder. Caller must have validated kb_target inheritance
    (root requires explicit kb_target; subfolders inherit from parent)."""
    folder = Folder(**kwargs)
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    logger.info(
        "📁 Folder created: id=%s, name=%s, parent=%s, kb_target=%s",
        str(folder.id)[:8], folder.name,
        str(folder.parent_folder_id)[:8] if folder.parent_folder_id else "<root>",
        folder.kb_target,
    )
    return folder


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_folder(db: AsyncSession, folder_id: uuid.UUID) -> Folder | None:
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    return result.scalar_one_or_none()


async def list_folders(
    db: AsyncSession,
    *,
    parent_folder_id: uuid.UUID | None = None,
    kb_target: str | None = None,
    roots_only: bool = False,
) -> list[Folder]:
    """List folders. If `roots_only`, returns root folders (parent IS NULL)
    optionally scoped by kb_target. Otherwise filters by parent_folder_id."""
    stmt = select(Folder)
    if roots_only:
        stmt = stmt.where(Folder.parent_folder_id.is_(None))
        if kb_target is not None:
            stmt = stmt.where(Folder.kb_target == kb_target)
    else:
        stmt = stmt.where(Folder.parent_folder_id == parent_folder_id)
    stmt = stmt.order_by(Folder.name.asc())
    return list((await db.execute(stmt)).scalars().all())


async def get_breadcrumb(
    db: AsyncSession, folder_id: uuid.UUID,
) -> list[Folder]:
    """Return chain from root → folder_id (inclusive). Walks parent_folder_id."""
    chain: list[Folder] = []
    current_id: uuid.UUID | None = folder_id
    # Hard cap to defend against pathological cycles.
    for _ in range(64):
        if current_id is None:
            break
        folder = await get_folder(db, current_id)
        if folder is None:
            break
        chain.append(folder)
        current_id = folder.parent_folder_id
    chain.reverse()
    return chain


async def get_folder_path(
    db: AsyncSession, folder_id: uuid.UUID,
) -> str:
    """Slash-joined folder names from root to folder_id, e.g. 'A/B/C'."""
    chain = await get_breadcrumb(db, folder_id)
    return "/".join(f.name for f in chain)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_folder(
    db: AsyncSession, folder_id: uuid.UUID, **kwargs: Any,
) -> Folder | None:
    folder = await get_folder(db, folder_id)
    if folder is None:
        return None
    for key, value in kwargs.items():
        setattr(folder, key, value)
    await db.flush()
    await db.refresh(folder)
    return folder


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def is_empty(db: AsyncSession, folder_id: uuid.UUID) -> bool:
    """True iff folder has no child folders and no files."""
    child_count = (await db.execute(
        select(func.count()).select_from(Folder).where(
            Folder.parent_folder_id == folder_id,
        ),
    )).scalar_one()
    if child_count > 0:
        return False
    file_count = (await db.execute(
        select(func.count()).select_from(KBFile).where(
            KBFile.folder_id == folder_id,
        ),
    )).scalar_one()
    return file_count == 0


async def delete_folder(db: AsyncSession, folder_id: uuid.UUID) -> bool:
    """Delete a folder. Caller must have verified it's empty (or handled
    cascade via `walk_subtree`). The DB FK is ON DELETE RESTRICT for
    parent_folder_id, so this will raise if children exist."""
    folder = await get_folder(db, folder_id)
    if folder is None:
        return False
    await db.delete(folder)
    await db.flush()
    return True


async def walk_subtree(
    db: AsyncSession, folder_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Return folder IDs in the subtree rooted at `folder_id`, deepest first.

    Caller can iterate in returned order to delete children before parents,
    satisfying the parent_folder_id ON DELETE RESTRICT constraint.
    """
    result: list[uuid.UUID] = []

    async def _walk(fid: uuid.UUID) -> None:
        children = await list_folders(db, parent_folder_id=fid)
        for child in children:
            await _walk(child.id)
        result.append(fid)

    await _walk(folder_id)
    return result


async def collect_s3_keys_in_folders(
    db: AsyncSession, folder_ids: list[uuid.UUID],
) -> list[str]:
    """Return all non-null S3 keys for KBFiles inside the given folders.

    Used by the cascade-delete flow to gather S3 objects that need cleanup
    AFTER the DB rows are removed. The deletion happens in a background
    task so the API response can return quickly.
    """
    if not folder_ids:
        return []
    stmt = select(KBFile.s3_key).where(
        KBFile.folder_id.in_(folder_ids),
        KBFile.s3_key.is_not(None),
    )
    return [row[0] for row in (await db.execute(stmt)).all()]


async def delete_files_in_folders(
    db: AsyncSession, folder_ids: list[uuid.UUID],
) -> int:
    """Bulk delete KBFiles whose folder_id is in the given list.

    Returns the number of rows deleted. Cascading FKs handle the
    source_kb_files junction and any other dependent rows.
    """
    if not folder_ids:
        return 0
    stmt = sa_delete(KBFile).where(KBFile.folder_id.in_(folder_ids))
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Contents — children folders + paginated files
# ---------------------------------------------------------------------------

async def list_files_in_folder(
    db: AsyncSession,
    folder_id: uuid.UUID | None,
    *,
    page: int = 1,
    size: int = 50,
) -> dict:
    """Paginated files directly inside `folder_id`. None = unfiled (legacy)."""
    where_clause = (
        KBFile.folder_id.is_(None) if folder_id is None
        else KBFile.folder_id == folder_id
    )
    total = (await db.execute(
        select(func.count()).select_from(KBFile).where(where_clause),
    )).scalar_one()
    offset = (page - 1) * size
    rows = (await db.execute(
        select(KBFile)
        .where(where_clause)
        .order_by(KBFile.created_at.desc())
        .offset(offset)
        .limit(size),
    )).scalars().all()
    return {
        "items": list(rows), "total": total, "page": page, "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

async def name_exists_under_parent(
    db: AsyncSession,
    *,
    parent_folder_id: uuid.UUID | None,
    kb_target: str,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Case-insensitive name collision check matching the DB partial indexes."""
    lower = name.lower()
    if parent_folder_id is None:
        stmt = select(func.count()).select_from(Folder).where(
            and_(
                Folder.parent_folder_id.is_(None),
                Folder.kb_target == kb_target,
                func.lower(Folder.name) == lower,
            ),
        )
    else:
        stmt = select(func.count()).select_from(Folder).where(
            and_(
                Folder.parent_folder_id == parent_folder_id,
                func.lower(Folder.name) == lower,
            ),
        )
    if exclude_id is not None:
        stmt = stmt.where(Folder.id != exclude_id)
    count = (await db.execute(stmt)).scalar_one()
    return count > 0
