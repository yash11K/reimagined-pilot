"""Request/response schemas for the jobs API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobSummary(BaseModel):
    """Single job row for the jobs list endpoint."""

    id: UUID
    source_id: UUID
    source_label: str
    source_type: str
    status: str
    progress_pct: int
    discovered_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    brand: str | None


class RunPageResponse(BaseModel):
    """Single run page outcome record."""

    id: UUID
    job_id: UUID
    url: str
    outcome: str
    reason: str | None
    bytes: int | None
    file_id: UUID | None
    created_at: datetime | None
