"""Request/response schemas for the sources API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SourceSummary(BaseModel):
    """Summary representation of a source for list views."""

    id: UUID
    url: str
    type: str
    region: str | None
    brand: str | None
    kb_target: str
    status: str
    is_scouted: bool
    is_ingested: bool
    created_at: datetime | None
    job_count: int


class FileStats(BaseModel):
    """Aggregate file statistics for a source."""

    total: int
    approved: int
    pending: int
    rejected: int


class SourceDetail(BaseModel):
    """Full source detail with file stats and scout summary."""

    id: UUID
    url: str
    type: str
    region: str | None
    brand: str | None
    kb_target: str
    status: str
    is_scouted: bool
    is_ingested: bool
    metadata: dict | None
    scout_summary: dict | None
    last_ingested_at: datetime | None
    created_at: datetime | None
    file_stats: FileStats
