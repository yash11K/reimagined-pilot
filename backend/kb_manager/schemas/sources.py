"""Request/response schemas for the sources API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SourceSummary(BaseModel):
    """Summary representation of a source for list views (flat read)."""

    id: UUID
    url: str
    type: str
    origin: str
    region: str | None
    brand: str | None
    kb_target: str
    status: str
    display_status: str
    run_count: int
    last_run_at: datetime | None
    created_at: datetime | None


class FileStats(BaseModel):
    total: int
    approved: int
    pending: int
    rejected: int


class RuntimeInfo(BaseModel):
    queue_position: int | None
    worker_id: int | None


class RunHistoryEntry(BaseModel):
    id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None


class ActiveFileInfo(BaseModel):
    id: UUID
    title: str
    status: str


class SourceDetail(BaseModel):
    """Source detail — adds run history + active files + runtime."""

    id: UUID
    url: str
    type: str
    origin: str
    region: str | None
    brand: str | None
    kb_target: str
    status: str
    display_status: str
    run_count: int
    last_run_at: datetime | None
    metadata: dict | None
    scout_summary: dict | None
    created_at: datetime | None
    parent_url: str | None = None

    file_stats: FileStats
    active_files: list[ActiveFileInfo] = []
    run_history: list[RunHistoryEntry] = []
    runtime: RuntimeInfo | None = None
    steering_prompt: str | None = None


class FilterCounts(BaseModel):
    by_status: dict[str, int]
    by_region: dict[str, int]
    by_brand: dict[str, int]
    by_origin: dict[str, int]


class SourceListResponse(BaseModel):
    items: list[SourceSummary]
    total: int
    page: int
    size: int
    pages: int
    counts: FilterCounts | None = None


class ReingestRequest(BaseModel):
    steering_prompt: str | None = None
    priority: int | None = None


class ReingestResponse(BaseModel):
    job_id: UUID
    source_id: UUID
    status: str
