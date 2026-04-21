"""Request/response schemas for the ingestion API."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class AemUrlInput(BaseModel):
    """Single AEM URL entry for ingestion."""

    url: str
    region: str
    brand: str | None = None
    nav_label: str | None = None
    nav_section: str | None = None
    page_path: str | None = None


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    connector_type: Literal["aem", "upload"]
    urls: list[AemUrlInput] | None = None
    kb_target: Literal["public", "internal"]
    steering_prompt: str | None = None


class JobCreated(BaseModel):
    """Single job entry in the ingest response."""

    job_id: UUID
    source_id: UUID
    source_url: str
    status: str


class IngestResponse(BaseModel):
    """Response body for POST /ingest."""

    jobs: list[JobCreated]
