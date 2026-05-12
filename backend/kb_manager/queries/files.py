"""CRUD, pagination, filtering, and search queries for the kb_files table."""

import logging
import math
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import KBFile, source_kb_files

logger = logging.getLogger(__name__)


async def create_file(db: AsyncSession, **kwargs: Any) -> KBFile:
    """Create a new KB file record."""
    kb_file = KBFile(**kwargs)
    db.add(kb_file)
    await db.flush()
    await db.refresh(kb_file)
    logger.info("📄 KB file created: id=%s, title=%s, status=%s",
                str(kb_file.id)[:8], kb_file.title, kb_file.status)
    return kb_file


async def link_source_to_file(
    db: AsyncSession,
    source_id: uuid.UUID,
    kb_file_id: uuid.UUID,
) -> None:
    """Create a source ↔ kb_file junction record (idempotent)."""
    # Check if link already exists to avoid PK conflict
    existing = await db.execute(
        source_kb_files.select().where(
            source_kb_files.c.source_id == source_id,
            source_kb_files.c.kb_file_id == kb_file_id,
        )
    )
    if existing.first() is not None:
        return
    stmt = source_kb_files.insert().values(
        source_id=source_id,
        kb_file_id=kb_file_id,
    )
    await db.execute(stmt)
    await db.flush()
    logger.debug("🔗 Linked source=%s → file=%s", str(source_id)[:8], str(kb_file_id)[:8])


async def get_file(db: AsyncSession, file_id: uuid.UUID) -> KBFile | None:
    """Get a KB file by ID."""
    result = await db.execute(select(KBFile).where(KBFile.id == file_id))
    return result.scalar_one_or_none()


async def list_files(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
    region: str | None = None,
    brand: str | None = None,
    kb_target: str | None = None,
    language: str | None = None,
    job_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    unfiled: bool = False,
    search: str | None = None,
) -> dict:
    """List KB files with pagination, filtering, and title search.

    When source_id is given, filters via the junction table.

    Folder filtering:
      - ``folder_id`` (UUID): files inside that folder.
      - ``unfiled=True``: files with no folder (legacy URL-ingested files —
        the "Web Sources" virtual bucket). Mutually exclusive with
        ``folder_id``; if both are passed, ``folder_id`` wins.
    """
    query = select(KBFile)
    count_query = select(func.count()).select_from(KBFile)

    if status is not None:
        query = query.where(KBFile.status == status)
        count_query = count_query.where(KBFile.status == status)
    if region is not None:
        query = query.where(KBFile.region == region)
        count_query = count_query.where(KBFile.region == region)
    if brand is not None:
        query = query.where(KBFile.brand == brand)
        count_query = count_query.where(KBFile.brand == brand)
    if kb_target is not None:
        query = query.where(KBFile.kb_target == kb_target)
        count_query = count_query.where(KBFile.kb_target == kb_target)
    if language is not None:
        query = query.where(KBFile.language == language)
        count_query = count_query.where(KBFile.language == language)
    if job_id is not None:
        query = query.where(KBFile.job_id == job_id)
        count_query = count_query.where(KBFile.job_id == job_id)
    if folder_id is not None:
        query = query.where(KBFile.folder_id == folder_id)
        count_query = count_query.where(KBFile.folder_id == folder_id)
    elif unfiled:
        query = query.where(KBFile.folder_id.is_(None))
        count_query = count_query.where(KBFile.folder_id.is_(None))
    if source_id is not None:
        # Join through junction table
        query = query.join(source_kb_files, source_kb_files.c.kb_file_id == KBFile.id).where(
            source_kb_files.c.source_id == source_id,
        )
        count_query = (
            select(func.count())
            .select_from(KBFile)
            .join(source_kb_files, source_kb_files.c.kb_file_id == KBFile.id)
            .where(source_kb_files.c.source_id == source_id)
        )
    if search is not None:
        pattern = f"%{search}%"
        query = query.where(KBFile.title.ilike(pattern))
        count_query = count_query.where(KBFile.title.ilike(pattern))

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(KBFile.created_at.desc())

    result = await db.execute(query)
    items = list(result.scalars().all())
    pages = math.ceil(total / size) if size > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def update_file(
    db: AsyncSession, file_id: uuid.UUID, **kwargs: Any,
) -> KBFile | None:
    """Update a KB file by ID."""
    kb_file = await get_file(db, file_id)
    if kb_file is None:
        logger.warning("⚠️ Attempted to update non-existent file %s", file_id)
        return None
    for key, value in kwargs.items():
        setattr(kb_file, key, value)
    await db.flush()
    await db.refresh(kb_file)
    logger.debug("📄 KB file updated: id=%s, fields=%s", str(file_id)[:8], list(kwargs.keys()))
    return kb_file


async def delete_file(db: AsyncSession, file_id: uuid.UUID) -> bool:
    """Delete a KB file by ID."""
    kb_file = await get_file(db, file_id)
    if kb_file is None:
        logger.warning("⚠️ Attempted to delete non-existent file %s", file_id)
        return False
    await db.delete(kb_file)
    await db.flush()
    logger.info("🗑️ KB file deleted: id=%s", str(file_id)[:8])
    return True


async def count_files_by_status(
    db: AsyncSession, source_id: uuid.UUID,
) -> dict[str, int]:
    """Count files grouped by status for a given source (via junction)."""
    stmt = (
        select(KBFile.status, func.count())
        .select_from(KBFile)
        .join(source_kb_files, source_kb_files.c.kb_file_id == KBFile.id)
        .where(source_kb_files.c.source_id == source_id)
        .group_by(KBFile.status)
    )
    result = await db.execute(stmt)
    by_status: dict[str, int] = {row[0]: row[1] for row in result.all()}

    return {
        "total": sum(by_status.values()),
        "approved": by_status.get("approved", 0),
        "pending_review": by_status.get("pending_review", 0),
        "rejected": by_status.get("rejected", 0),
    }


async def list_active_files_for_source(
    db: AsyncSession, source_id: uuid.UUID,
) -> list[KBFile]:
    """List non-superseded, non-rejected files linked to this source."""
    stmt = (
        select(KBFile)
        .join(source_kb_files, source_kb_files.c.kb_file_id == KBFile.id)
        .where(
            source_kb_files.c.source_id == source_id,
            KBFile.status.notin_(("superseded", "rejected")),
        )
        .order_by(KBFile.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_files_pending_review(
    db: AsyncSession, *, page: int = 1, size: int = 20,
) -> dict:
    """List files awaiting human review."""
    import math as _m
    base = select(KBFile).where(KBFile.status == "pending_review")
    count_q = select(func.count()).select_from(KBFile).where(
        KBFile.status == "pending_review",
    )
    total = (await db.execute(count_q)).scalar_one()
    offset = (page - 1) * size
    rows = (await db.execute(
        base.order_by(KBFile.created_at.desc()).offset(offset).limit(size),
    )).scalars().all()
    return {
        "items": list(rows), "total": total, "page": page, "size": size,
        "pages": _m.ceil(total / size) if size > 0 else 0,
    }
