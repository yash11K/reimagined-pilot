"""Activity feed — recent events across files, jobs and sources.

Pagination happens at the SQL layer: each event source contributes a row
shape ``(id, type, actor, target_id, target_title, action, ts)`` to a
``UNION ALL``, and Postgres handles the ``ORDER BY ts DESC LIMIT/OFFSET``
plus the ``COUNT(*)`` over the union. This avoids loading the full event
universe into memory and gives an honest ``total``.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Text, case, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

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


def _file_events_select() -> Select:
    # UUID columns must be cast to TEXT before string concat: Postgres has no
    # ``varchar + uuid`` operator. ``cast(..., Text)`` produces ``::text``.
    file_id_text = cast(KBFile.id, Text)
    type_expr = case(
        (KBFile.status == "approved", literal("file_approved")),
        else_=literal("file_rejected"),
    )
    return select(
        (literal("file_") + file_id_text).label("id"),
        type_expr.label("type"),
        KBFile.reviewed_by.label("actor"),
        file_id_text.label("target_id"),
        func.coalesce(KBFile.title, literal("Untitled")).label("target_title"),
        KBFile.status.label("action"),
        KBFile.created_at.label("ts"),
    ).where(
        KBFile.status.in_(("approved", "rejected")),
        KBFile.reviewed_by.isnot(None),
        KBFile.created_at.isnot(None),
    )


def _job_events_select() -> Select:
    job_id_text = cast(IngestionJob.id, Text)
    type_expr = case(
        (IngestionJob.status == "completed", literal("job_completed")),
        else_=literal("job_failed"),
    )
    ts_expr = func.coalesce(IngestionJob.completed_at, IngestionJob.started_at)
    return (
        select(
            (literal("job_") + job_id_text).label("id"),
            type_expr.label("type"),
            literal(None).label("actor"),
            job_id_text.label("target_id"),
            func.coalesce(
                func.left(Source.url, 80),
                func.left(job_id_text, 8),
            ).label("target_title"),
            IngestionJob.status.label("action"),
            ts_expr.label("ts"),
        )
        .join(Source, IngestionJob.source_id == Source.id)
        .where(
            IngestionJob.status.in_(("completed", "failed")),
            ts_expr.isnot(None),
        )
    )


def _source_events_select() -> Select:
    source_id_text = cast(Source.id, Text)
    type_expr = case(
        (Source.status == "ingested", literal("source_confirmed")),
        else_=literal("source_dismissed"),
    )
    ts_expr = func.coalesce(Source.last_ingested_at, Source.created_at)
    return select(
        (literal("source_") + source_id_text).label("id"),
        type_expr.label("type"),
        literal(None).label("actor"),
        source_id_text.label("target_id"),
        func.left(Source.url, 80).label("target_title"),
        Source.status.label("action"),
        ts_expr.label("ts"),
    ).where(
        Source.status.in_(("ingested", "dismissed")),
        ts_expr.isnot(None),
    )


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ActivityResponse:
    """Union of recent events ordered by timestamp DESC, paginated in SQL."""
    union = union_all(
        _file_events_select(),
        _job_events_select(),
        _source_events_select(),
    ).subquery("activity")

    total = (
        await db.execute(select(func.count()).select_from(union))
    ).scalar_one()

    rows = (
        await db.execute(
            select(union)
            .order_by(union.c.ts.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items = [
        ActivityItem(
            id=row.id,
            type=row.type,
            actor=row.actor,
            target_id=row.target_id,
            target_title=row.target_title,
            action=row.action,
            timestamp=row.ts,
        )
        for row in rows
    ]
    return ActivityResponse(items=items, total=total)
