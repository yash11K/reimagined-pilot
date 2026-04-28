# Pipeline — Two-Phase Ingestion Orchestrator

**File:** `kb_manager/services/pipeline.py`

---

## Overview

The Pipeline is the central orchestrator of the entire ingestion system. It implements a two-phase approach: Scout (discovery) and Process (extraction + QA + upload). Every content URL that enters the system flows through this component.

---

## Class: `Pipeline`

### Constructor

```python
Pipeline(
    stream_manager: StreamManager,
    s3_uploader: S3Uploader,
    versioning_service: VersioningService,
    session_factory: async_sessionmaker[AsyncSession],
)
```

Initialised once during app startup in `lifespan()`. Holds references to all shared services. Lazy-initialises the Bedrock KB client on first sync trigger.

### Dependencies

| Dependency | Purpose |
|---|---|
| `StreamManager` | Publish SSE events for real-time progress |
| `S3Uploader` | Upload approved files + metadata sidecars |
| `VersioningService` | Compare modify_date to avoid re-processing |
| `session_factory` | Create async DB sessions per operation |
| `DiscoveryAgent` | LLM-based component + link classification |
| `ExtractorAgent` | LLM-based component → markdown conversion |
| `QAAgent` | LLM-based quality gate |
| `UniquenessAgent` | LLM-based KB overlap detection |
| `BedrockKBClient` | Trigger KB data-source sync (lazy-init) |

---

## Method: `run_scout(job_id, source_url, steering_prompt?)`

### Purpose
Phase 1: Discover what content exists at a URL and classify all outbound links.

### Flow

1. **Fetch** — `httpx.get(source_url)` to retrieve AEM model.json
2. **Prune** — `prune_aem_json()` removes noise (headers, footers, nav, i18n, dataLayer)
3. **Deterministic Link Extraction** — `extract_links_deterministic()` walks the entire pruned tree and collects all valid links. This is the ground truth — no LLM involved.
4. **Discovery Agent** — `DiscoveryAgent.run(pruned, pre_extracted_links)` classifies components and links using Haiku. The pre-extracted links are passed in so the agent can validate against them (hallucination defense).
5. **Link Classification Loop** (in-memory, no DB):
   - Validates URL shape
   - Resolves relative paths to full model.json URLs
   - Deduplicates against existing DB sources (pre-fetched set)
   - Applies filter chain: cross-domain → denied path → self-link → ignored → non-English → navigation
   - Surviving links sorted into: certain, uncertain
6. **Batch DB Write** (single session):
   - Denied links → Source records with `denied_*` status (for audit)
   - Certain links → Source + QueueItem (for independent processing)
   - Uncertain links → Source with `needs_confirmation` status
7. **Finalise** — Store scout_summary, advance job to `processing`, publish SSE events
8. **Auto-advance** — Calls `run_process(job_id)` immediately

### Session Strategy
Uses two short-lived DB sessions to minimise connection hold time:
- Session 1: Load parent source data + pre-fetch existing URLs for dedup
- Session 2: Batch-write all classified links + finalise job

### SSE Events Published
`scouting_started`, `component_found`, `link_found`, `link_classified`, `scout_complete`

---

## Method: `run_process(job_id)`

### Purpose
Phase 2: Extract content from a single source, run QA, and upload approved files.

### Flow

1. **Load Job** — Fetch job + source from DB
2. **Fetch Content** — `httpx.get(source.url)` for the source page
3. **Extract modify_date** — Parse `jcr:lastModified` from AEM JSON
4. **Version Check** — `VersioningService.check_and_supersede()`:
   - `"skip"` → source unchanged, no re-processing
   - `"process"` → new or updated content, old file marked superseded
5. **Extraction** — `ExtractorAgent.run(components, steering_prompt)` converts to markdown
6. **Per-File Loop** — `_process_single_file()` for each extracted file (see below)
7. **Finalise** — Mark source ingested, job completed, publish SSE, trigger KB sync if files approved

### SSE Events Published
`extraction_started`, `page_processing`, `file_created`, `file_qa_complete`, `job_complete`

---

## Method: `_process_single_file(db, job, source_ids, extracted_file, qa_agent, uniqueness_agent, ...)`

### Purpose
Run the full QA pipeline on a single extracted file and persist the result.

### Flow

1. **Create KBFile** — `file_queries.create_file()` with `status=pending_review`
2. **Link Sources** — `file_queries.link_source_to_file()` for each source_id (M2M junction)
3. **QA Agent** — `qa_agent.run(md_content)` → `quality_verdict` (accepted/rejected)
4. **Uniqueness Agent** — `uniqueness_agent.run(md_content, metadata)` → `uniqueness_verdict` (unique/overlapping/conflicting)
5. **Routing Matrix** — `route_file(quality, uniqueness, metadata_complete)` → target status
6. **Update File** — Store verdicts, reasoning, similar_file_ids, final status
7. **S3 Upload** — If approved: `s3_uploader.upload(kb_file)` → markdown + metadata sidecar
8. **Publish SSE** — `file_created` and `file_qa_complete` events

---

## Method: `run_upload_process(job_id, files)`

### Purpose
Handle direct file uploads (not AEM crawling). Simpler flow — no scout phase.

### Flow

1. For each uploaded file: read content, wrap as `ExtractedFile`
2. Run `_process_single_file()` (same QA pipeline as AEM flow)
3. Finalise job, trigger KB sync

---

## Helper: `_extract_modify_date(aem_json)`

Searches for `jcr:lastModified`, `cq:lastModified`, or `lastModified` in the AEM JSON root and `jcr:content` node. Falls back to `datetime.now(UTC)`.

## Helper: `_is_english_url(url)`

Returns `True` only if the URL contains `/en/` path segment. Non-English URLs are filtered out during scout.

---

## Error Handling

Both `run_scout` and `run_process` wrap their entire body in try/except. On failure:
1. Log the exception with timing
2. Call `_fail_job(job_id, error_message, channel)`:
   - Update job: `status=failed`, `error_message` set
   - Publish SSE: `job_failed` event
   - Close the SSE channel

The queue worker inspects the job's final status after `run_scout` returns and mirrors it onto the queue item (with retry logic).
