# Requirements Document

## Introduction

KB Manager v2 Backend is a Python/FastAPI service that ingests content from AEM websites and uploaded documents into a curated knowledge base. It uses AI agents (via Bedrock) to discover, extract, validate, and classify content, then routes files to human review or auto-approves them into S3-backed storage. The backend exposes a RESTful API with SSE streaming, backed by PostgreSQL.

## Glossary

- **Backend**: The FastAPI application serving the KB Manager v2 API
- **Ingestion_Job**: A unit of work representing the processing of one source through the pipeline
- **Source**: An origin of content — either an AEM web page or an uploaded document
- **KB_File**: A markdown file with YAML frontmatter produced by the extraction pipeline
- **Content_Link**: A hyperlink discovered during scouting, classified by the Link Triage Agent
- **Nav_Tree_Cache**: A cached AEM navigation tree with a 24-hour TTL
- **AEM_Pruner**: A deterministic module that strips known noise from AEM JSON before agent processing
- **Discovery_Agent**: An AI agent (Haiku) that walks pruned AEM JSON to identify components and links
- **Link_Triage_Agent**: An AI agent (Haiku) that classifies discovered links as expansion, sibling, navigation, or uncertain
- **Extractor_Agent**: An AI agent (Sonnet) that converts content components into markdown files with YAML frontmatter
- **QA_Agent**: An AI agent (Haiku) that assesses quality, uniqueness, and metadata completeness of extracted files
- **Stream_Manager**: An in-memory event bus that publishes SSE events per job
- **Pipeline**: The orchestrator that runs the two-phase ingestion flow (scout then process)
- **Scout_Phase**: Phase 1 of web ingestion — fetches, prunes, discovers components, classifies links
- **Process_Phase**: Phase 2 of ingestion — extracts content, runs QA, routes files
- **Content_Map**: The scout summary presented to users for review before processing
- **Routing_Matrix**: The decision table mapping quality and uniqueness verdicts to file status
- **S3_Uploader**: A service that uploads approved KB files to S3

## Requirements

### Requirement 1: Project Configuration

**User Story:** As a developer, I want a centralized configuration module, so that all environment variables are validated and accessible via a typed settings object.

#### Acceptance Criteria

1. THE Backend SHALL load configuration from environment variables using Pydantic BaseSettings
2. THE Backend SHALL require DATABASE_URL and S3_BUCKET_NAME as mandatory settings with no defaults
3. THE Backend SHALL provide default values for AWS_REGION ("us-east-1"), BEDROCK_MODEL_ID, HAIKU_MODEL_ID, BEDROCK_MAX_TOKENS (16000), AEM_REQUEST_TIMEOUT (30), and MAX_CONCURRENT_JOBS (3)
4. WHEN BEDROCK_KB_ID is not set, THE Backend SHALL treat knowledge base uniqueness checks as disabled
5. IF a required environment variable is missing at startup, THEN THE Backend SHALL raise a validation error with the missing variable name

### Requirement 2: Database Models and Migrations

**User Story:** As a developer, I want SQLAlchemy ORM models for all five database tables, so that the application can interact with PostgreSQL using async operations.

#### Acceptance Criteria

1. THE Backend SHALL define async SQLAlchemy ORM models for sources, ingestion_jobs, content_links, kb_files, and nav_tree_cache tables matching the schema in shared-contracts.md §1
2. THE Backend SHALL use UUID primary keys with server-side auto-generation for all tables
3. THE Backend SHALL enforce a UNIQUE constraint on (type, identifier) for the sources table
4. THE Backend SHALL enforce a UNIQUE constraint on (job_id, target_url) for the content_links table
5. THE Backend SHALL enforce a UNIQUE constraint on root_url for the nav_tree_cache table
6. THE Backend SHALL provide an async session factory using asyncpg as the database driver
7. THE Backend SHALL include an Alembic setup with a baseline migration that creates all five tables
8. WHEN a TIMESTAMPTZ column has a default, THE Backend SHALL use server-side now() as the default value

### Requirement 3: Application Bootstrap and Health

**User Story:** As a developer, I want a FastAPI application with CORS enabled and a health endpoint, so that the service can be deployed and monitored.

#### Acceptance Criteria

1. THE Backend SHALL expose a FastAPI application with CORS allowing all origins for development
2. THE Backend SHALL expose a GET /health endpoint that returns HTTP 200 with a JSON body indicating service status
3. THE Backend SHALL mount all API routes under the /api/v1 prefix
4. THE Backend SHALL use an async lifespan context manager for startup and shutdown

### Requirement 4: Database Query Layer

**User Story:** As a developer, I want a query layer with CRUD, pagination, and filtering functions, so that all database access is centralized and consistent.

#### Acceptance Criteria

1. THE Backend SHALL provide async query functions for creating, reading, updating, and deleting records in all five tables
2. WHEN a list endpoint is called with page and size parameters, THE Backend SHALL return paginated results with a separate count query to compute total and pages
3. WHEN filtering parameters (status, region, brand, kb_target, type, job_id, source_id, search) are provided, THE Backend SHALL apply them as WHERE clauses to the query
4. WHEN a search parameter is provided to the files list query, THE Backend SHALL perform a case-insensitive match against the title field

### Requirement 5: Ingestion API — Start Ingestion

**User Story:** As a user, I want to start an ingestion job by providing URLs or uploading files, so that content enters the processing pipeline.

#### Acceptance Criteria

1. WHEN a POST /ingest request is received with connector_type "aem", THE Backend SHALL create a source record and an ingestion_job record for each URL, set job status to "scouting", and return HTTP 202 with the list of created jobs
2. WHEN a POST /ingest request is received with connector_type "upload", THE Backend SHALL create a source record and an ingestion_job record, set job status to "processing", and return HTTP 202
3. THE Backend SHALL accept the request body fields: connector_type, urls (for aem), kb_target, and steering_prompt matching the exact shapes in shared-contracts.md §2
4. WHEN connector_type is "upload", THE Backend SHALL accept multipart form data with files alongside the JSON payload
5. WHEN a web ingestion job is created, THE Backend SHALL trigger the scout phase asynchronously in the background

### Requirement 6: Ingestion API — Scout Stream

**User Story:** As a user, I want to receive real-time scouting progress via SSE, so that I can see components and links as they are discovered.

#### Acceptance Criteria

1. WHEN a GET /ingest/{job_id}/scout-stream request is received, THE Backend SHALL return a StreamingResponse with content type text/event-stream
2. THE Backend SHALL emit SSE events: scouting_started, component_found, link_found, link_classified, scout_complete, and error with the exact data shapes from shared-contracts.md §2
3. WHILE a scout-stream connection is open, THE Backend SHALL send an SSE comment as a keepalive every 15 seconds
4. WHEN scouting completes, THE Backend SHALL emit a scout_complete event and close the stream

### Requirement 7: Ingestion API — Content Map Recovery

**User Story:** As a user, I want to retrieve the full content map after scouting, so that I can recover state if the SSE connection drops.

#### Acceptance Criteria

1. WHEN a GET /ingest/{job_id}/content-map request is received and the job status is "awaiting_confirmation", THE Backend SHALL return HTTP 200 with the job_id, status, source_url, and content_map containing components, links, and summary
2. IF a GET /ingest/{job_id}/content-map request is received and the job status is "scouting", THEN THE Backend SHALL return HTTP 409 indicating scouting is still in progress

### Requirement 8: Ingestion API — Confirm and Process

**User Story:** As a user, I want to confirm the ingestion plan with optional overrides, so that extraction and QA proceed on the content I selected.

#### Acceptance Criteria

1. WHEN a POST /ingest/{job_id}/confirm request is received, THE Backend SHALL accept link_overrides, excluded_component_ids, and steering_prompt in the request body
2. WHEN link_overrides are provided, THE Backend SHALL update the corresponding content_link records with the new classification or status
3. WHEN excluded_component_ids are provided, THE Backend SHALL mark those components as excluded in the scout_summary JSONB
4. WHEN confirmation is accepted, THE Backend SHALL set the job status to "processing" and return HTTP 202
5. WHEN confirmation is accepted, THE Backend SHALL trigger the process phase asynchronously in the background

### Requirement 9: Ingestion API — Progress Stream

**User Story:** As a user, I want to receive real-time extraction and QA progress via SSE, so that I can monitor file creation and quality results.

#### Acceptance Criteria

1. WHEN a GET /ingest/{job_id}/progress-stream request is received, THE Backend SHALL return a StreamingResponse with content type text/event-stream
2. THE Backend SHALL emit SSE events: extraction_started, page_processing, file_created, qa_started, qa_complete, job_complete, and error with the exact data shapes from shared-contracts.md §2
3. WHILE a progress-stream connection is open, THE Backend SHALL send an SSE comment as a keepalive every 15 seconds
4. WHEN processing completes, THE Backend SHALL emit a job_complete event with file counts and close the stream

### Requirement 10: Files API

**User Story:** As a user, I want to list, view, edit, approve, reject, and revalidate KB files, so that I can manage the knowledge base content.

#### Acceptance Criteria

1. WHEN a GET /files request is received, THE Backend SHALL return a paginated list of file summaries with fields: id, title, status, region, brand, kb_target, quality_verdict, uniqueness_verdict, source_url, and created_at
2. WHEN a GET /files/{file_id} request is received, THE Backend SHALL return the full file detail including md_content, QA verdicts with reasoning, hydrated similar_files array (joined from similar_file_ids), and review metadata
3. WHEN a POST /files/{file_id}/approve request is received with reviewed_by and optional notes, THE Backend SHALL set the file status to "approved", store the reviewer info, trigger S3 upload in the background, and return the updated file detail
4. WHEN a POST /files/{file_id}/reject request is received with reviewed_by and notes, THE Backend SHALL set the file status to "rejected", store the reviewer info and notes, and return the updated file detail
5. WHEN a PUT /files/{file_id} request is received with md_content and reviewed_by, THE Backend SHALL update the file content, trigger QA re-run in the background, and return the updated file detail immediately
6. WHEN a POST /files/{file_id}/revalidate request is received, THE Backend SHALL re-run QA synchronously and return the updated file detail with new verdicts

### Requirement 11: Sources API

**User Story:** As a user, I want to list and view content sources with their job and file statistics, so that I can track ingestion history.

#### Acceptance Criteria

1. WHEN a GET /sources request is received, THE Backend SHALL return a paginated list of source summaries with job counts, filterable by type, region, brand, and kb_target
2. WHEN a GET /sources/{source_id} request is received, THE Backend SHALL return the source detail with aggregate file stats: total, approved, pending, and rejected counts computed from kb_files
3. WHEN a GET /sources/active-jobs request is received, THE Backend SHALL return a mapping of source_id to job_id for all jobs with status in ("scouting", "awaiting_confirmation", "processing")

### Requirement 12: AEM Deterministic Pruning

**User Story:** As a developer, I want a deterministic pruner that strips known noise from AEM JSON, so that agents receive clean input without boilerplate content.

#### Acceptance Criteria

1. THE AEM_Pruner SHALL drop the top-level keys "i18n" and "dataLayer" from the AEM JSON
2. THE AEM_Pruner SHALL drop items whose key starts with "experiencefragment"
3. THE AEM_Pruner SHALL drop items whose ":type" value ends with any of: headerNavigation, footerNavigation, footerLegal, header, footer, loginModal, bookingwidget, multiColumnLinks
4. WHEN items are dropped, THE AEM_Pruner SHALL remove the corresponding entries from ":itemsOrder" arrays
5. THE AEM_Pruner SHALL identify and flag links matching URL denylist patterns: /reservation, /login, /account, /search, /booking, /checkout, /payment, /registration, /reset-password
6. FOR ALL valid AEM JSON inputs, pruning then serializing then pruning again SHALL produce an equivalent result (idempotence property)

### Requirement 13: Stream Manager

**User Story:** As a developer, I want an in-memory event pub/sub system per job, so that SSE endpoints can stream events to connected clients.

#### Acceptance Criteria

1. THE Stream_Manager SHALL maintain separate event channels for each job_id
2. WHEN an event is published to a job channel, THE Stream_Manager SHALL deliver the event to all active subscribers of that channel
3. WHEN a subscriber connects after events have been published, THE Stream_Manager SHALL deliver only new events from the point of subscription
4. WHEN a job completes or fails, THE Stream_Manager SHALL clean up the channel resources for that job

### Requirement 14: Pipeline Orchestration

**User Story:** As a developer, I want a pipeline orchestrator that runs the two-phase ingestion flow, so that scouting and processing are coordinated with proper status transitions.

#### Acceptance Criteria

1. WHEN the scout phase runs, THE Pipeline SHALL fetch the AEM model.json, apply deterministic pruning, invoke the Discovery_Agent, classify links via the Link_Triage_Agent, store results in content_links and scout_summary, and set job status to "awaiting_confirmation"
2. WHEN the process phase runs, THE Pipeline SHALL extract content for included components and queued links, run QA on each file, route files based on the Routing_Matrix, upload auto-approved files to S3, and set job status to "completed"
3. WHILE the scout phase is running, THE Pipeline SHALL publish SSE events (scouting_started, component_found, link_found, link_classified, scout_complete) via the Stream_Manager
4. WHILE the process phase is running, THE Pipeline SHALL publish SSE events (extraction_started, page_processing, file_created, qa_started, qa_complete, job_complete) via the Stream_Manager
5. IF an unrecoverable error occurs during either phase, THEN THE Pipeline SHALL set the job status to "failed", store the error message, and publish an error SSE event
6. WHEN processing expansion links, THE Pipeline SHALL merge the source teaser context with the linked page's full content into a single markdown file
7. WHEN processing sibling links, THE Pipeline SHALL extract each linked page as a separate markdown file

### Requirement 15: Agent Stubs

**User Story:** As a developer, I want agent stubs for Discovery, Link Triage, Extractor, and QA agents using strands-agents, so that the pipeline can invoke them with defined interfaces.

#### Acceptance Criteria

1. THE Backend SHALL define a Discovery_Agent stub that accepts pruned AEM JSON and returns a list of content components and raw links
2. THE Backend SHALL define a Link_Triage_Agent stub that accepts source context and linked page structure and returns classification, reason, has_sub_links, and sub_link_count
3. THE Backend SHALL define an Extractor_Agent stub that accepts content components and optional steering prompt and returns markdown files with YAML frontmatter
4. THE Backend SHALL define a QA_Agent stub that accepts markdown file content and returns quality_verdict, quality_reasoning, uniqueness_verdict, uniqueness_reasoning, and similar_file_ids
5. THE QA_Agent stub SHALL include a query_kb tool definition for querying the Bedrock knowledge base

### Requirement 16: QA Routing Matrix

**User Story:** As a developer, I want files to be auto-routed based on QA verdicts, so that good unique content is approved automatically and poor or duplicate content is rejected.

#### Acceptance Criteria

1. WHEN quality_verdict is "good" and uniqueness_verdict is "unique", THE Backend SHALL set the file status to "approved"
2. WHEN quality_verdict is "good" and uniqueness_verdict is "overlapping", THE Backend SHALL set the file status to "pending_review"
3. WHEN quality_verdict is "good" and uniqueness_verdict is "duplicate", THE Backend SHALL set the file status to "rejected"
4. WHEN quality_verdict is "acceptable" and uniqueness_verdict is "unique", THE Backend SHALL set the file status to "pending_review"
5. WHEN quality_verdict is "acceptable" and uniqueness_verdict is "overlapping", THE Backend SHALL set the file status to "pending_review"
6. WHEN quality_verdict is "acceptable" and uniqueness_verdict is "duplicate", THE Backend SHALL set the file status to "rejected"
7. WHEN quality_verdict is "poor", THE Backend SHALL set the file status to "rejected" regardless of uniqueness_verdict
8. IF required metadata fields (title, content_type, source_url, region, brand) are missing after extraction, THEN THE Backend SHALL set the file status to "rejected" with reasoning indicating the missing fields

### Requirement 17: S3 Upload Service

**User Story:** As a developer, I want a service that uploads approved files to S3 with the correct key structure, so that files are stored in the knowledge base.

#### Acceptance Criteria

1. WHEN a file is approved, THE S3_Uploader SHALL upload the markdown content to S3 using the key pattern: {kb_target}/{brand}/{region}/{namespace}/{filename}
2. WHEN the upload succeeds, THE S3_Uploader SHALL update the kb_file record with the s3_key value
3. IF the S3 upload fails, THEN THE S3_Uploader SHALL log the error and leave the file status as "approved" without an s3_key

### Requirement 18: Versioning Logic

**User Story:** As a developer, I want the system to detect and handle content versions, so that updated pages supersede old files without losing audit history.

#### Acceptance Criteria

1. WHEN ingesting a source URL that already exists in kb_files, THE Backend SHALL compare the modify_date from AEM with the existing file's modify_date
2. WHEN the AEM modify_date is newer than the existing file's modify_date, THE Backend SHALL process the new version and set the old file's status to "superseded"
3. WHEN the AEM modify_date equals the existing file's modify_date, THE Backend SHALL skip re-processing of that source URL
4. WHEN a file is superseded, THE Backend SHALL remove the old file from S3 but retain the record in the database for audit

### Requirement 19: Knowledge Base Search and Chat

**User Story:** As a user, I want to search the knowledge base and chat with it using RAG, so that I can find and query ingested content.

#### Acceptance Criteria

1. WHEN a POST /kb/search request is received, THE Backend SHALL stream search results via SSE with events: result (rank, title, snippet, source_url, score) and search_complete (total_results)
2. WHEN a POST /kb/chat request is received, THE Backend SHALL retrieve context from the knowledge base, then stream the generated answer via SSE with events: sources, token, and chat_complete
3. THE Backend SHALL accept query, kb_target, and limit parameters for search, and query, kb_target, and context_limit parameters for chat
4. WHEN a POST /kb/download request is received with an s3_uri, THE Backend SHALL return a presigned S3 download URL

### Requirement 20: Navigation Tree

**User Story:** As a user, I want to browse AEM navigation trees, so that I can select pages for ingestion.

#### Acceptance Criteria

1. WHEN a GET /nav/tree request is received with a url parameter, THE Backend SHALL return the nested navigation tree structure for that AEM site
2. WHEN a cached tree exists for the given root_url and has not expired, THE Backend SHALL return the cached tree
3. WHEN force_refresh is true, THE Backend SHALL fetch a fresh tree regardless of cache status
4. WHEN a fresh tree is fetched, THE Backend SHALL store it in nav_tree_cache with a 24-hour TTL

### Requirement 21: Dashboard Statistics

**User Story:** As a user, I want to see aggregate statistics on the dashboard, so that I can monitor the overall state of the knowledge base.

#### Acceptance Criteria

1. WHEN a GET /stats request is received, THE Backend SHALL return total_files, pending_review, approved, rejected, active_jobs, sources_count, kb_public_files, and kb_internal_files
2. THE Backend SHALL compute all counts directly from kb_files and ingestion_jobs tables without denormalized counters

### Requirement 22: Containerization

**User Story:** As a developer, I want a Dockerfile and docker-compose configuration, so that the backend and PostgreSQL can be run together locally.

#### Acceptance Criteria

1. THE Backend SHALL include a Dockerfile that builds a production image for the FastAPI application using Python 3.12+
2. THE Backend SHALL include a docker-compose.yml that runs the FastAPI service and a PostgreSQL 15+ database
3. WHEN docker-compose starts, THE Backend SHALL apply database migrations automatically before serving requests
