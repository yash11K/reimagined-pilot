"""Activity feed — recent events across files and jobs, ordered by time desc."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, union_all, literal, cast, Text
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.database import get_db
from kb_manager.models import IngestionJob, KBFile, Source

router = APIRouter()
logger = logging.getLogger(__name__)


class ActivityItem(BaseModel):
    id: str
    type: str          # file_approved | file_rejected | job_completed | job_failed | source_confirmed | source_dismissed
    actor: str | None  # reviewed_by or None
    target_id: str
    target_title: str
    action: str
    timestamp: datetime


class ActivityResponse(BaseModel):
    items: list[ActivityItem]
    total: int


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ActivityResponse:
    """Union of recent events: file approvals/rejections, job completions, source confirmations."""
    items: list[ActivityItem] = []

    # --- File events (approved / rejected) ---
    file_result = await db.execute(
        select(KBFile)
        .where(KBFile.status.in_(("approved", "rejected")))
        .where(KBFile.reviewed_by.isnot(None))
        .order_by(KBFile.created_at.desc())
        .limit(limit + offset)
    )
    for f in file_result.scalars().all():
        event_type = "file_approved" if f.status == "approved" else "file_rejected"
        items.append(ActivityItem(
            id=f"file_{f.id}",
            type=event_type,
            actor=f.reviewed_by,
            target_id=str(f.id),
            target_title=f.title or "Untitled",
            action=f.status,
            timestamp=f.created_at,
        ))

    # --- Job events (completed / failed) ---
    job_result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.status.in_(("completed", "failed")))
        .order_by(IngestionJob.completed_at.desc())
        .limit(limit + offset)
    )
    for j in job_result.scalars().all():
        event_type = "job_completed" if j.status == "completed" else "job_failed"
        ts = j.completed_at or j.started_at
        if ts is None:
            continue
        # Get source URL for title
        source_url = ""
        if j.source:
            source_url = j.source.url or ""
        items.append(ActivityItem(
            id=f"job_{j.id}",
            type=event_type,
            actor=None,
            target_id=str(j.id),
            target_title=source_url[:80] or str(j.id)[:8],
            action=j.status,
            timestamp=ts,
        ))

    # --- Source confirmation events ---
    source_result = await db.execute(
        select(Source)
        .where(Source.status.in_(("ingested", "dismissed")))
        .order_by(Source.last_ingested_at.desc())
        .limit(limit + offset)
    )
    for s in source_result.scalars().all():
        ts = s.last_ingested_at or s.created_at
        if ts is None:
            continue
        event_type = "source_confirmed" if s.status == "ingested" else "source_dismissed"
        items.append(ActivityItem(
            id=f"source_{s.id}",
            type=event_type,
            actor=None,
            target_id=str(s.id),
            target_title=s.url[:80],
            action=s.status,
            timestamp=ts,
        ))

    # Sort all events by timestamp desc, apply offset+limit
    items.sort(key=lambda x: x.timestamp, reverse=True)
    total = len(items)
    paged = items[offset: offset + limit]

    return ActivityResponse(items=paged, total=total)
