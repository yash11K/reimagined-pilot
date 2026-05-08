"""SQLAlchemy ORM models — v2 simplified data model.

Tables: sources, ingestion_jobs, source_kb_files (junction), kb_files,
queue_items, run_pages.

Key denormalizations on `sources`:
  - display_status / active_job_id / active_file_id  → app-side maintained
  - run_count / last_run_at                          → DB-trigger maintained
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Many-to-many junction: sources ↔ kb_files
# ---------------------------------------------------------------------------

source_kb_files = Table(
    "source_kb_files",
    Base.metadata,
    Column("source_id", UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
    Column("kb_file_id", UUID(as_uuid=True), ForeignKey("kb_files.id", ondelete="CASCADE"), primary_key=True),
)


# ---------------------------------------------------------------------------
# Source — unified entity for any content URL (manual or discovered)
# ---------------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("type", "url", name="uq_sources_type_url"),
        Index("ix_sources_listing", "origin", "status", "created_at"),
        Index("ix_sources_filters", "brand", "region", "kb_target"),
        Index("ix_sources_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # aem | upload | manual
    origin: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'manual'"),
    )  # manual | discovered

    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_target: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)

    # active | needs_confirmation | dismissed | denied | failed | ingested
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'"),
    )

    # idle | queued | discovering | extracting | qa | failed | needs_review
    display_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'idle'"),
    )

    # --- Denormalized pointers / counters ---
    active_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    active_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_files.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    run_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0"),
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    # --- Scout summary + freeform metadata ---
    scout_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )

    # --- Provenance: parent source for discovered URLs ---
    parent_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Relationships (lazy="raise" — must be opted into per query) ---
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="source",
        lazy="raise",
        foreign_keys="IngestionJob.source_id",
    )
    kb_files: Mapped[list["KBFile"]] = relationship(
        secondary=source_kb_files, back_populates="sources", lazy="raise",
    )


# ---------------------------------------------------------------------------
# IngestionJob — execution instance against a source
# ---------------------------------------------------------------------------

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_source_status", "source_id", "status"),
        Index("ix_ingestion_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # scouting | awaiting_confirmation | processing | completed | failed
    progress_pct: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0"),
    )
    steering_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    source: Mapped["Source"] = relationship(
        back_populates="ingestion_jobs",
        lazy="raise",
        foreign_keys=[source_id],
    )
    kb_files: Mapped[list["KBFile"]] = relationship(
        back_populates="job", lazy="raise",
    )


# ---------------------------------------------------------------------------
# KBFile — extracted knowledge base article
# ---------------------------------------------------------------------------

class KBFile(Base):
    __tablename__ = "kb_files"
    __table_args__ = (
        Index("ix_kb_files_status", "status"),
        Index("ix_kb_files_job_id", "job_id"),
        Index("ix_kb_files_kb_target", "kb_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    md_content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_target: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    modify_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # pending_review | approved | rejected | superseded

    quality_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    uniqueness_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    uniqueness_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    similar_file_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True,
    )

    s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )

    job: Mapped["IngestionJob"] = relationship(back_populates="kb_files", lazy="raise")
    sources: Mapped[list["Source"]] = relationship(
        secondary=source_kb_files, back_populates="kb_files", lazy="raise",
    )


# ---------------------------------------------------------------------------
# QueueItem — worker queue (rows deleted on completion; no history)
# ---------------------------------------------------------------------------

class QueueItem(Base):
    __tablename__ = "queue_items"
    __table_args__ = (
        Index("ix_queue_items_status", "status"),
        Index(
            "uq_queue_active_source",
            "source_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'queued'"),
    )  # queued | processing  (completed/failed rows are deleted)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0"),
    )
    max_retries: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("3"),
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    last_heartbeat: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    worker_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    priority: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0"),
    )

    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    source: Mapped["Source"] = relationship(lazy="raise")
    job: Mapped["IngestionJob | None"] = relationship(lazy="raise")


# ---------------------------------------------------------------------------
# RunPage — per-page outcome record for an ingestion job
# ---------------------------------------------------------------------------

class RunPage(Base):
    __tablename__ = "run_pages"
    __table_args__ = (
        Index("ix_run_pages_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bytes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )
