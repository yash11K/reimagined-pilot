# Implementation Plan: KB Manager v2 Backend

## Overview

Greenfield Python/FastAPI backend built in 4 phases: Foundation → API Layer → Pipeline & Agents → Integration. Each task references specific requirements and design properties. The sole source of truth for all contracts, schemas, and implementation details is `specs/shared-contracts.md` and `specs/backend-spec.md`.

## Tasks

- [x] 1. Foundation — Configuration, Models, Migrations, App Bootstrap
  - [x] 1.1 Create project skeleton and dependencies
    - Create `kb_manager/` package with `__init__.py`
    - Create `pyproject.toml` (or `requirements.txt`) with: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, boto3, aiobotocore, httpx, strands-agents, hypothesis, pytest, pytest-asyncio
    - Create `kb_manager/config.py` with `Settings(BaseSettings)` — require `DATABASE_URL` and `S3_BUCKET_NAME`, provide defaults for all optional vars per design §1
    - Expose `get_settings()` singleton via `@lru_cache`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 1.2 Write property test for required settings validation
    - **Property 1: Required settings validation**
    - **Validates: Requirements 1.2, 1.5**

  - [x] 1.3 Create database engine and session factory
    - Create `kb_manager/database.py` with `create_async_engine`, `async_sessionmaker`, and `get_db()` async generator for FastAPI DI
    - _Requirements: 2.6_

  - [x] 1.4 Define SQLAlchemy ORM models
    - Create `kb_manager/models.py` with all 5 models: `Source`, `IngestionJob`, `ContentLink`, `KBFile`, `NavTreeCache`
    - Use `mapped_column` with `server_default=func.gen_random_uuid()` for UUID PKs and `server_default=func.now()` for timestamps
    - Enforce UNIQUE constraints: `(type, identifier)` on sources, `(job_id, target_url)` on content_links, `root_url` on nav_tree_cache
    - Match column types and names exactly to shared-contracts.md §1
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8_

  - [ ]* 1.5 Write property tests for unique constraints
    - **Property 2: Unique constraint enforcement on sources**
    - **Property 3: Unique constraint enforcement on content_links**
    - **Property 4: Unique constraint enforcement on nav_tree_cache**
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x] 1.6 Set up Alembic migrations
    - Create `kb_manager/alembic/` directory with `alembic.ini`, `env.py` (async-aware), and `versions/001_baseline.py`
    - Baseline migration creates all 5 tables with indexes per shared-contracts.md §1
    - _Requirements: 2.7_

  - [x] 1.7 Create FastAPI application bootstrap
    - Create `kb_manager/main.py` with app factory, async lifespan (engine create/dispose), CORS middleware (allow all origins), and `GET /health` returning `{"status": "ok"}`
    - Mount all route modules under `/api/v1` prefix
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 1.8 Write property test for API route prefix
    - **Property 5: API route prefix**
    - **Validates: Requirements 3.3**

  - [x] 1.9 Create Pydantic request/response schemas
    - Create `kb_manager/schemas/common.py` with `PaginatedResponse[T]`
    - Create `kb_manager/schemas/ingest.py` with `AemUrlInput`, `IngestRequest`, `JobCreated`, `IngestResponse`, `LinkOverride`, `ConfirmRequest` — match shared-contracts.md §2 exactly
    - Create `kb_manager/schemas/files.py` with `FileSummary`, `SimilarFile`, `FileDetail`, `ApproveRequest`, `RejectRequest`, `EditRequest`
    - Create `kb_manager/schemas/sources.py` with source list/detail models
    - Create `kb_manager/schemas/kb.py` with search/chat request models
    - _Requirements: 5.3, 10.1, 10.2_

  - [x] 1.10 Implement query layer
    - Create `kb_manager/queries/sources.py` — CRUD + filtering by type, region, brand, kb_target
    - Create `kb_manager/queries/jobs.py` — CRUD + status transitions
    - Create `kb_manager/queries/files.py` — CRUD + pagination + filtering (status, region, brand, kb_target, job_id, source_id) + case-insensitive title search
    - Create `kb_manager/queries/links.py` — CRUD for content_links
    - Create `kb_manager/queries/nav_cache.py` — cache get/upsert with TTL check
    - All functions accept `AsyncSession` and return model instances or paginated results
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 1.11 Write property tests for query layer
    - **Property 6: CRUD round trip**
    - **Property 7: Pagination correctness**
    - **Property 8: Filter correctness**
    - **Property 9: Case-insensitive title search**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [x] 2. Checkpoint — Foundation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. API Layer — All Endpoints and Router Aggregation
  - [x] 3.1 Implement ingestion routes
    - Create `kb_manager/routes/ingest.py` with `APIRouter`
    - `POST /ingest` — validate `IngestRequest`, create source + job records, return 202 with `IngestResponse`. For `aem`: set status `"scouting"`, trigger scout in background. For `upload`: set status `"processing"`, accept multipart files, trigger upload processing in background.
    - `GET /ingest/{job_id}/scout-stream` — return `StreamingResponse(media_type="text/event-stream")`, subscribe to StreamManager `"scout"` channel, emit keepalive every 15s
    - `GET /ingest/{job_id}/content-map` — return 200 with content map if status is `"awaiting_confirmation"`, return 409 if still `"scouting"`
    - `POST /ingest/{job_id}/confirm` — accept `ConfirmRequest`, apply link_overrides and excluded_component_ids, set status `"processing"`, trigger process phase in background, return 202
    - `GET /ingest/{job_id}/progress-stream` — return `StreamingResponse`, subscribe to `"progress"` channel, emit keepalive every 15s
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4_

  - [ ]* 3.2 Write property tests for ingestion API
    - **Property 10: AEM ingest creates correct number of jobs**
    - **Property 11: Ingest request schema validation**
    - **Property 12: SSE event serialization**
    - **Property 13: Confirmation overrides are applied**
    - **Validates: Requirements 5.1, 5.3, 6.2, 8.2, 8.3, 9.2**

  - [x] 3.3 Implement files routes
    - Create `kb_manager/routes/files.py` with `APIRouter`
    - `GET /files` — paginated list with filters (status, region, brand, kb_target, job_id, source_id, search), return `PaginatedResponse[FileSummary]`
    - `GET /files/{file_id}` — full `FileDetail` with hydrated `similar_files` (join similar_file_ids → file titles/URLs)
    - `POST /files/{file_id}/approve` — accept `ApproveRequest`, set status `"approved"`, store reviewer, trigger S3 upload in background, return updated detail
    - `POST /files/{file_id}/reject` — accept `RejectRequest`, set status `"rejected"`, store reviewer + notes, return updated detail
    - `PUT /files/{file_id}` — accept `EditRequest`, update `md_content`, trigger QA re-run in background, return updated detail immediately
    - `POST /files/{file_id}/revalidate` — re-run QA synchronously, return updated detail with new verdicts
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 3.4 Write property tests for files API
    - **Property 14: File detail hydrates similar_files**
    - **Property 15: File review actions update status and reviewer**
    - **Property 16: File edit updates content**
    - **Validates: Requirements 10.2, 10.3, 10.4, 10.5**

  - [x] 3.5 Implement sources routes
    - Create `kb_manager/routes/sources.py` with `APIRouter`
    - `GET /sources` — paginated list with filters (type, region, brand, kb_target), include job counts
    - `GET /sources/{source_id}` — source detail with aggregate file stats (total, approved, pending, rejected) computed from kb_files
    - `GET /sources/active-jobs` — return mapping of source_id → job_id for active statuses (`scouting`, `awaiting_confirmation`, `processing`)
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ]* 3.6 Write property tests for sources API
    - **Property 17: Source detail file stats are accurate**
    - **Property 18: Active jobs returns only active statuses**
    - **Validates: Requirements 11.2, 11.3**

  - [x] 3.7 Implement KB search, chat, and download routes
    - Create `kb_manager/routes/kb.py` with `APIRouter`
    - `POST /kb/search` — accept query, kb_target, limit; stream SSE results (result events + search_complete)
    - `POST /kb/chat` — accept query, kb_target, context_limit; stream SSE (sources, token, chat_complete)
    - `POST /kb/download` — accept s3_uri, return presigned URL
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

  - [x] 3.8 Implement navigation and stats routes
    - Create `kb_manager/routes/nav.py` — `GET /nav/tree` with url and force_refresh params, check cache TTL, fetch fresh if needed, store with 24h TTL
    - Create `kb_manager/routes/stats.py` — `GET /stats` returning all counts computed via COUNT queries from kb_files and ingestion_jobs
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 21.1, 21.2_

  - [ ]* 3.9 Write property tests for nav cache and stats
    - **Property 30: Nav tree cache TTL**
    - **Property 31: Nav tree cache hit**
    - **Property 32: Dashboard stats accuracy**
    - **Validates: Requirements 20.2, 20.4, 21.1**

  - [x] 3.10 Wire all routers into the app
    - In `kb_manager/main.py`, import and include all route modules under the `/api/v1` prefix
    - Verify all routes are registered with correct methods and paths per design §10
    - _Requirements: 3.3_

- [x] 4. Checkpoint — API Layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Pipeline & Agents — Pruner, Stream Manager, Pipeline, Agent Stubs, S3, KB Query
  - [x] 5.1 Implement AEM Pruner
    - Create `kb_manager/services/aem_pruner.py` with two pure functions:
    - `prune_aem_json(raw: dict) -> dict` — drop `i18n`/`dataLayer` top-level keys, drop items keyed with `experiencefragment` prefix, drop items whose `:type` ends with noise patterns (headerNavigation, footerNavigation, footerLegal, header, footer, loginModal, bookingwidget, multiColumnLinks), clean up `:itemsOrder` arrays, recurse into nested `:items`. Return new dict (no mutation).
    - `is_denied_url(url: str) -> bool` — check URL path against denylist segments (/reservation, /login, /account, /search, /booking, /checkout, /payment, /registration, /reset-password)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 5.2 Write property tests for AEM Pruner
    - **Property 19: AEM pruner removes all noise**
    - **Property 20: AEM pruner URL denylist**
    - **Property 21: AEM pruner idempotence**
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6**

  - [x] 5.3 Implement Stream Manager
    - Create `kb_manager/services/stream_manager.py` with `StreamManager` class
    - `subscribe(job_id, channel)` — create `asyncio.Queue` per subscriber, yield events, block until events or sentinel `None`
    - `publish(job_id, channel, event, data)` — push event to all active subscriber queues for that job/channel
    - `close_channel(job_id, channel)` — push sentinel `None` to all subscribers, clean up internal data structures
    - Channels: `"scout"` and `"progress"` per job
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 5.4 Write property tests for Stream Manager
    - **Property 22: Stream manager channel isolation and fan-out**
    - **Property 23: Stream manager late subscriber sees only new events**
    - **Property 24: Stream manager cleanup**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

  - [x] 5.5 Implement QA Routing Matrix
    - Create `kb_manager/services/routing_matrix.py` with pure function `route_file(quality: str, uniqueness: str, metadata_complete: bool) -> str`
    - Implement the 3×3 verdict matrix: good+unique→approved, good+overlapping→pending_review, good+duplicate→rejected, acceptable+unique→pending_review, acceptable+overlapping→pending_review, acceptable+duplicate→rejected, poor+any→rejected
    - Metadata gate: if `metadata_complete` is False, return `"rejected"` regardless of verdicts
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8_

  - [ ]* 5.6 Write property tests for Routing Matrix
    - **Property 26: QA routing matrix correctness**
    - **Property 27: Metadata gate rejects incomplete files**
    - **Validates: Requirements 16.1–16.8**

  - [x] 5.7 Implement S3 Uploader
    - Create `kb_manager/services/s3_uploader.py` with `S3Uploader` class
    - `build_s3_key(kb_target, brand, region, namespace, filename) -> str` — construct `{kb_target}/{brand}/{region}/{namespace}/{filename}`, no leading/trailing/double slashes
    - `upload(file: KBFile) -> str | None` — upload markdown to S3, return s3_key on success, None on failure (log error)
    - `delete(s3_key: str) -> bool` — delete file from S3 (used for superseding)
    - `generate_presigned_url(s3_uri: str) -> str` — return presigned download URL
    - Use aiobotocore/boto3 with bucket name from settings
    - _Requirements: 17.1, 17.2, 17.3_

  - [ ]* 5.8 Write property test for S3 key construction
    - **Property 28: S3 key construction**
    - **Validates: Requirements 17.1**

  - [x] 5.9 Implement Versioning Service
    - Create `kb_manager/services/versioning.py` with `VersioningService` class
    - `check_and_supersede(source_url, new_modify_date, db) -> str` — lookup existing kb_files by source_url, compare modify_date. If newer → return `"process"`, mark old file `"superseded"`. If equal → return `"skip"`.
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

  - [ ]* 5.10 Write property test for Versioning
    - **Property 29: Versioning decision**
    - **Validates: Requirements 18.1, 18.2, 18.3**

  - [x] 5.11 Implement Agent Stubs
    - Create `kb_manager/agents/discovery.py` — `DiscoveryAgent` class with `async run(pruned_json: dict) -> DiscoveryResult` returning components + links. Use strands-agents with Haiku model ID from settings.
    - Create `kb_manager/agents/link_triage.py` — `LinkTriageAgent` class with `async run(source_context: str, linked_structure: dict) -> TriageResult` returning classification, reason, has_sub_links, sub_link_count. Use Haiku.
    - Create `kb_manager/agents/extractor.py` — `ExtractorAgent` class with `async run(components, steering_prompt, expansion_content) -> list[ExtractedFile]` returning markdown files with YAML frontmatter. Use Sonnet.
    - Create `kb_manager/agents/qa.py` — `QAAgent` class with `async run(md_content: str) -> QAResult` returning quality/uniqueness verdicts + reasoning + similar_file_ids. Include `query_kb` tool definition for Bedrock KB. Use Haiku.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 5.12 Implement Pipeline Orchestrator
    - Create `kb_manager/services/pipeline.py` with `Pipeline` class
    - `run_scout(job_id, source_url, steering_prompt)` — fetch model.json via httpx, apply `prune_aem_json`, invoke DiscoveryAgent, classify links via LinkTriageAgent, store results in content_links + scout_summary JSONB, set status `"awaiting_confirmation"`, publish SSE events (scouting_started, component_found, link_found, link_classified, scout_complete) via StreamManager
    - `run_process(job_id, confirmation)` — extract content for included components and queued links (expansion → merge teaser + full content; sibling → separate file), run QA on each file, route via routing_matrix, upload auto-approved files to S3, set status `"completed"`, publish SSE events (extraction_started, page_processing, file_created, qa_started, qa_complete, job_complete)
    - `run_upload_process(job_id, files)` — parse uploaded files, wrap in markdown + frontmatter, run QA, route, upload approved, set status `"completed"`
    - Use `asyncio.Semaphore(MAX_CONCURRENT_JOBS)` for concurrency control
    - Wrap each phase in try/except: on error set status `"failed"`, store error_message, publish error SSE event
    - Individual file failures during process phase mark file as `rejected` with error reasoning, processing continues
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [ ]* 5.13 Write property test for Pipeline failure handling
    - **Property 25: Pipeline failure sets job to failed**
    - **Validates: Requirements 14.5**

- [x] 6. Checkpoint — Pipeline & Agents
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integration — SSE Wiring, S3 Background Tasks, Versioning, Docker
  - [x] 7.1 Wire SSE streaming into ingestion routes
    - In `routes/ingest.py`, connect `scout-stream` and `progress-stream` endpoints to StreamManager subscriptions
    - Implement 15-second keepalive timer interleaved with queue reads using `asyncio.wait` / `asyncio.timeout`
    - Format SSE output as `event: {type}\ndata: {json}\n\n`
    - Close stream on sentinel or scout_complete/job_complete events
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3, 9.4_

  - [x] 7.2 Wire S3 background tasks into file routes
    - In `routes/files.py` approve handler, use `BackgroundTasks` to trigger `S3Uploader.upload()` after setting status to `"approved"`, then update kb_file with s3_key on success
    - In `routes/files.py` edit handler, use `BackgroundTasks` to trigger QA re-run after updating content
    - _Requirements: 10.3, 10.5, 17.1, 17.2, 17.3_

  - [x] 7.3 Wire versioning into pipeline process phase
    - Before extracting content for a source URL, call `VersioningService.check_and_supersede()` — if `"skip"`, skip re-processing; if `"process"`, mark old file `"superseded"` and delete old S3 key via `S3Uploader.delete()`
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

  - [x] 7.4 Wire KB search/chat SSE streaming
    - In `routes/kb.py`, implement SSE streaming for search (result + search_complete events) and chat (sources + token + chat_complete events) using StreamingResponse
    - _Requirements: 19.1, 19.2_

  - [x] 7.5 Create Dockerfile
    - Create `kb_manager/Dockerfile` — multi-stage build using Python 3.12+ slim base, install dependencies, copy source, expose port, run uvicorn
    - _Requirements: 22.1_

  - [x] 7.6 Create docker-compose.yml
    - Create `kb_manager/docker-compose.yml` with two services: `api` (FastAPI app) and `db` (PostgreSQL 15+)
    - API service depends on db, runs Alembic migrations on startup before serving requests
    - Configure DATABASE_URL to point to the compose db service
    - _Requirements: 22.2, 22.3_

- [x] 8. Final Checkpoint — Full Integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each phase
- Property tests validate universal correctness properties from the design document (Properties 1–32)
- The sole source of truth for all contracts, schemas, and implementation details is `specs/shared-contracts.md` and `specs/backend-spec.md`
- All agent stubs use strands-agents SDK with model IDs from config
- All database operations are async via asyncpg
