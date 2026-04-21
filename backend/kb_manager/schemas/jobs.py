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
