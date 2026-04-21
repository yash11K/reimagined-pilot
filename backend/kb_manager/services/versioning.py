"""Versioning service for KB files.

Compares modify_date of incoming content against existing files
to decide whether to process a new version or skip. When a newer
version is detected the old file is marked as "superseded".
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import KBFile

logger = logging.getLogger(__name__)


class VersioningService:
    """Handles content versioning decisions for KB files."""

    async def check_and_supersede(
        self,
        source_url: str,
        new_modify_date: datetime,
        db: AsyncSession,
    ) -> str:
        """Decide whether to process or skip a source URL based on modify_date.

        Looks up existing kb_files by *source_url* (excluding already-superseded
        records) and compares *new_modify_date* against the most recent one.

        Returns:
            ``"process"`` — no existing file found, or the new date is strictly
            newer (the old file is marked ``"superseded"``).

            ``"skip"`` — an existing file with the same modify_date already
            exists; no re-processing needed.
        """
        logger.debug("🔄 Checking version for %s (new_modify_date=%s)", source_url, new_modify_date)

        # Find existing non-superseded files for this source_url,
        # ordered by modify_date descending so the newest is first.
        stmt = (
            select(KBFile)
            .where(KBFile.source_url == source_url)
            .where(KBFile.status != "superseded")
            .order_by(KBFile.modify_date.desc())
        )
        result = await db.execute(stmt)
        existing = result.scalars().first()

        # No existing file → process
        if existing is None:
            logger.info("🆕 No existing file for %s — will process", source_url)
            return "process"

        # Same modify_date → skip
        if existing.modify_date is not None and existing.modify_date == new_modify_date:
            logger.info(
                "⏭️ File %s for %s has same modify_date (%s) — skipping",
                str(existing.id)[:8],
                source_url,
                new_modify_date,
            )
            return "skip"

        # Newer modify_date → supersede old, process new
        if existing.modify_date is None or new_modify_date > existing.modify_date:
            logger.info(
                "🔄 Superseding file %s for %s (old=%s → new=%s)",
                str(existing.id)[:8],
                source_url,
                existing.modify_date,
                new_modify_date,
            )
            existing.status = "superseded"
            await db.flush()
            return "process"

        # new_modify_date is older than existing — skip (edge case)
        logger.info(
            "⏭️ New modify_date %s is older than existing %s for %s — skipping",
            new_modify_date,
            existing.modify_date,
            source_url,
        )
        return "skip"
