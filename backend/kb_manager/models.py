"""SQLAlchemy ORM models for the KB Manager database.

Tables: sources, ingestion_jobs, source_kb_files (junction), kb_files,
nav_tree_cache, queue_items.
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
# Source — the single unified entity for any content URL
# ---------------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("type", "url", name="uq_sources_type_url"),
        Index("ix_sources_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # aem | upload | manual
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_target: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Lifecycle flags ---
    is_scouted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    is_ingested: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)

    # --- Status: active | needs_confirmation | dismissed | ingested | failed ---
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'"),
    )

    # --- Scout summary (stored after scout phase) ---
    scout_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # --- Metadata ---
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )

    # --- Relationships ---
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="source", lazy="selectin",
    )
    kb_files: Mapped[list["KBFile"]] = relationship(
        secondary=source_kb_files, back_populates="sources", lazy="selectin",
    )


# ---------------------------------------------------------------------------
# IngestionJob — execution instance against a source
# ---------------------------------------------------------------------------

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_status", "status"),
        Index("ix_ingestion_jobs_source_id", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False,
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

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="ingestion_jobs", lazy="selectin")
    kb_files: Mapped[list["KBFile"]] = relationship(
        back_populates="job", lazy="selectin",
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
        UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    md_content: Mapped[str] = mapped_column(Text, nullable=False)  # pure markdown, no YAML
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # primary source URL (denormalized for quick access)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_target: Mapped[str] = mapped_column(Text, nullable=False)

    # --- New metadata fields for Bedrock filtering ---
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str | None] = mapped_column(Text, nullable=True)  # public | internal | restricted
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    modify_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # pending_review | approved | rejected | superseded

    # --- QA verdicts ---
    quality_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    uniqueness_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    uniqueness_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    similar_file_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True,
    )

    # --- S3 ---
    s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Review ---
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )

    # --- Relationships ---
    job: Mapped["IngestionJob"] = relationship(back_populates="kb_files")
    sources: Mapped[list["Source"]] = relationship(
        secondary=source_kb_files, back_populates="kb_files", lazy="selectin",
    )


# ---------------------------------------------------------------------------
# NavTreeCache
# ---------------------------------------------------------------------------

class NavTreeCache(Base):
    __tablename__ = "nav_tree_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    root_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    tree_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )


# ---------------------------------------------------------------------------
# QueueItem — worker queue for automated ingestion
# ---------------------------------------------------------------------------

class QueueItem(Base):
    __tablename__ = "queue_items"
    __table_args__ = (
        Index("ix_queue_items_status", "status"),
        Index(
            "uq_queue_active_url",
            "url",
            unique=True,
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_target: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'public'"),
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'queued'"),
    )  # queued | processing | completed | failed
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Retry support ---
    retry_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0"),
    )
    max_retries: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("3"),
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    # --- Heartbeat for stale detection ---
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    # --- Priority (higher = processed first) ---
    priority: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0"),
    )

    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )

    # Relationships
    job: Mapped["IngestionJob | None"] = relationship(lazy="selectin")
