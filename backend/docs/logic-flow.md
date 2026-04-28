# KB Manager v2 — Logic Flow

This document traces every major flow through the system end-to-end.

---

## 1. AEM Ingestion Flow (Primary Path)

This is the main flow: a user submits an AEM URL and the system discovers, extracts, validates, and publishes content.

```
User → POST /api/v1/ingest
         │
         ▼
    ┌─────────────────────────────────────────────────┐
    │  Route: start_ingest()                          │
    │  1. Validate IngestRequest (connector_type=aem) │
    │  2. For each URL in request.urls:               │
    │     a. Create Source (type=aem, status=active)   │
    │     b. Create IngestionJob (status=scouting)     │
    │     c. Spawn background task: _run_scout()       │
    │  3. Return IngestResponse with job IDs           │
    └──────────────────────┬──────────────────────────┘
                           │
              ┌────────────▼────────────────┐
              │     SCOUT PHASE             │
              │   Pipeline.run_scout()      │
              └────────────┬────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 1: Fetch AEM model.json                    │
    │  httpx.get(source_url) → raw JSON                │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 2: Prune AEM JSON                          │
    │  aem_pruner.prune_aem_json(raw_json)             │
    │  - Remove i18n, dataLayer keys                   │
    │  - Drop experience fragments                     │
    │  - Drop header/footer/nav/booking components     │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 3: Deterministic Link Extraction            │
    │  aem_pruner.extract_links_deterministic()         │
    │  - Walk entire pruned tree                        │
    │  - Collect all href/link/url fields               │
    │  - Filter: denylist, cross-domain, self-links     │
    │  - Validate URL shape (no anchor-text leaks)      │
    │  → Guaranteed set of valid links (no LLM needed)  │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 4: Discovery Agent (LLM)                   │
    │  DiscoveryAgent.run(pruned, pre_extracted_links)  │
    │  - Identifies content components                  │
    │  - Classifies each link:                          │
    │    • certain  → content worth ingesting           │
    │    • uncertain → needs human confirmation          │
    │    • navigation → skip                            │
    │  - Validates against pre-extracted link set        │
    │    (catches hallucinated URLs)                     │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 5: Link Processing (in-memory)             │
    │  For each classified link:                        │
    │                                                   │
    │  Filters applied (in order):                      │
    │  1. Valid URL shape?         → drop junk           │
    │  2. Resolve relative path    → full model.json URL │
    │  3. Already in DB?           → skip (dedup)        │
    │  4. Cross-domain?            → denied_cross_domain │
    │  5. Denied path segment?     → denied_path         │
    │  6. Self-link?               → skip                │
    │  7. Ignored URL (homepage)?  → denied_ignored      │
    │  8. Non-English (/en/)?      → denied_non_english  │
    │  9. Navigation classified?   → denied_navigation   │
    │                                                   │
    │  Surviving links:                                  │
    │  • certain  → Create Source + add to Queue         │
    │  • uncertain → Create Source (needs_confirmation)  │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 6: Finalise Scout                          │
    │  - Store scout_summary on parent Source           │
    │  - Update job: status=processing, progress=40%    │
    │  - Publish SSE: scout_complete                    │
    │  - Auto-advance to Process phase                  │
    └──────────────────────┬──────────────────────────┘
                           │
              ┌────────────▼────────────────┐
              │    PROCESS PHASE            │
              │  Pipeline.run_process()     │
              └────────────┬────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 7: Fetch Source Content                     │
    │  httpx.get(source.url) → source JSON              │
    │  Extract modify_date from jcr:lastModified        │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 8: Version Check                           │
    │  VersioningService.check_and_supersede()          │
    │  - Compare modify_date vs existing KB files       │
    │  - If unchanged → "skip" (no re-processing)       │
    │  - If newer → "process" + mark old as superseded  │
    │  - If new → "process"                             │
    │  - Delete superseded file from S3                  │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 9: Extraction (LLM)                        │
    │  ExtractorAgent.run(components, steering_prompt)  │
    │  - Converts AEM components → markdown files       │
    │  - Preserves all text verbatim                    │
    │  - Derives: title, source_url, region, brand,     │
    │    category, visibility, tags                      │
    │  → List of ExtractedFile objects                   │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 10: Per-File Processing Loop               │
    │  _process_single_file() for each ExtractedFile    │
    │                                                   │
    │  a. Create KBFile record (status=pending_review)  │
    │  b. Link source(s) to file via M2M junction       │
    │  c. QA Agent → quality_verdict (accepted/rejected)│
    │  d. Uniqueness Agent → uniqueness_verdict          │
    │     (unique/overlapping/conflicting)               │
    │  e. Routing Matrix:                                │
    │     ┌──────────┬────────────┬───────────────┐     │
    │     │ Quality  │ Uniqueness │ → Status       │     │
    │     ├──────────┼────────────┼───────────────┤     │
    │     │ accepted │ unique     │ → approved     │     │
    │     │ accepted │ overlapping│ → approved     │     │
    │     │ accepted │ conflicting│ → pending_review│    │
    │     │ rejected │ *          │ → rejected     │     │
    │     │ *        │ * (no meta)│ → rejected     │     │
    │     └──────────┴────────────┴───────────────┘     │
    │  f. If approved → S3 upload (md + metadata.json)  │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │  Step 11: Finalise Job                           │
    │  - Mark source as ingested                        │
    │  - Update job: status=completed, progress=100%    │
    │  - Publish SSE: job_complete                      │
    │  - If files approved → trigger Bedrock KB sync    │
    └─────────────────────────────────────────────────┘
```

---

## 2. Queue Worker Flow

The queue worker runs continuously in the background, processing URLs that were queued during the scout phase or added manually via `POST /api/v1/queue`.

```
┌─────────────────────────────────────────────────────┐
│  QueueWorker._run_loop()  (continuous)               │
│                                                      │
│  while True:                                         │
│    1. Acquire semaphore slot (bounded concurrency)   │
│    2. claim_next(db) → QueueItem or None             │
│       - SELECT ... WHERE status='queued'             │
│         ORDER BY priority DESC, created_at ASC       │
│         FOR UPDATE SKIP LOCKED                       │
│       - SET status='processing', last_heartbeat=now  │
│    3. If None → release slot, wait poll_interval     │
│    4. Spawn asyncio.Task:                            │
│       _process_item_wrapper(item, worker_id)         │
│         ├── Start heartbeat loop (every 30s)         │
│         ├── _process_item():                         │
│         │   a. Create Source + Job for URL            │
│         │   b. pipeline.run_scout(job_id, url)       │
│         │      (scout auto-advances to process)      │
│         │   c. Check job final status:               │
│         │      • completed → mark_completed()        │
│         │      • failed → mark_failed()              │
│         │        - If retries left → requeue         │
│         │          (exponential backoff)              │
│         │        - If max retries → permanent fail   │
│         ├── Cancel heartbeat                         │
│         └── Release semaphore slot                   │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  QueueWorker._stale_sweep_loop()  (periodic)         │
│                                                      │
│  Every stale_timeout/2 seconds:                      │
│    1. Find items WHERE status='processing'           │
│       AND last_heartbeat < now - stale_timeout       │
│    2. Reset to 'queued' (reclaim for retry)          │
│    3. Notify poll loop to wake up                    │
└─────────────────────────────────────────────────────┘
```

---

## 3. File Upload Flow

Users can upload markdown files directly instead of crawling AEM.

```
POST /api/v1/ingest (connector_type=upload, files attached)
    │
    ├── Create Source (type=upload)
    ├── Create IngestionJob (status=processing)
    ├── Spawn background: Pipeline.run_upload_process()
    │
    │   For each uploaded file:
    │     1. Read content as UTF-8
    │     2. Wrap as ExtractedFile (title from filename)
    │     3. _process_single_file():
    │        QA → Uniqueness → Route → Upload if approved
    │
    └── Finalise job (completed, trigger KB sync)
```

---

## 4. Excel Bulk Import Flow

The `scripts/ingest_excel.py` script imports content from an Excel export (e.g., Decagon KB dump).

```
python -m scripts.ingest_excel [--dry-run] [--skip-s3] [--concurrency N]
    │
    ├── Phase 1: Metadata Enrichment (concurrent)
    │   For each Excel row:
    │     1. MetadataEnricher (Haiku LLM) derives:
    │        title, filename, brand, category, tags, visibility
    │     2. Results cached to JSON file for resume
    │
    ├── Phase 2: Persist (sequential)
    │   For each enriched row:
    │     1. Create Source (type=manual, url=decagon://<id>)
    │     2. Create IngestionJob (status=completed)
    │     3. Create KBFile (status=approved)
    │     4. Upload markdown + metadata sidecar to S3
    │
    └── Output: live log file + JSON summary report
```

---

## 5. Source Confirmation Flow

When the scout phase classifies a link as "uncertain", it creates a source with `status=needs_confirmation`. A human reviews and decides.

```
GET /api/v1/sources?status=needs_confirmation
    → List uncertain sources for review

POST /api/v1/sources/{id}/confirm
    │
    ├── action="process"
    │   1. Update source status → active
    │   2. Create new IngestionJob
    │   3. Spawn background: run_scout(job_id, source.url)
    │   → Full scout + process pipeline runs
    │
    └── action="discard"
        1. Update source status → dismissed
        → No further processing
```

---

## 6. File Review Flow

After extraction, files land in various statuses. Humans can review and override.

```
GET /api/v1/files?status=pending_review
    → List files needing human review

POST /api/v1/files/{id}/approve
    1. Update status → approved
    2. Background: upload to S3 + trigger KB sync

POST /api/v1/files/{id}/reject
    1. Update status → rejected
    2. Store reviewer + notes

PUT /api/v1/files/{id}
    1. Update markdown content
    2. Background: re-run QA + Uniqueness → re-route

POST /api/v1/files/{id}/revalidate
    1. Re-run QA + Uniqueness synchronously
    2. Re-route via routing matrix
    → Status may change based on new verdicts
```

---

## 7. Search & RAG Flow

```
GET /api/v1/search?q=refueling&entity=files,jobs
    │
    ├── search_files(q) → ILIKE on title, tags, source_url
    ├── search_jobs(q)  → ILIKE on source label
    └── Return GlobalSearchResponse { files: {...}, jobs: {...} }

POST /api/v1/kb/search  (Bedrock Retrieve)
    → SSE stream of ranked results from Bedrock KB

POST /api/v1/kb/chat    (Bedrock RetrieveAndGenerate)
    → SSE stream of LLM-generated answer + citations
```

---

## 8. SSE Event Streaming

```
Per-Job Channels (pipeline progress):
  GET /api/v1/ingest/{job_id}/scout-stream
      Events: scouting_started, component_found, link_found,
              link_classified, scout_complete

  GET /api/v1/ingest/{job_id}/progress-stream
      Events: extraction_started, page_processing,
              file_created, file_qa_complete, job_complete

Global Event Stream (UI dashboard):
  GET /api/v1/events/stream
      Topics: worker, queue, progress
      Events: worker_started, worker_idle,
              item_completed, item_failed, item_requeued,
              item_reclaimed, phase_changed
```

---

## 9. Error Handling & Retry Logic

```
Pipeline Failure:
  1. Pipeline catches exception in run_scout/run_process
  2. Calls _fail_job(job_id, error_message, channel)
     - Updates job: status=failed, error_message set
     - Publishes SSE: job_failed event
     - Closes SSE channel

Queue Retry:
  1. Queue worker detects job failure
  2. Calls mark_failed(item_id, error, retry_base_delay)
  3. If retry_count < max_retries:
     - Increment retry_count
     - Set next_attempt_at = now + base_delay * 2^retry_count
     - Reset status → queued (requeued)
  4. If retry_count >= max_retries:
     - Set status → failed (permanent)

Stale Recovery:
  1. Stale sweep runs every stale_timeout/2 seconds
  2. Finds items: status=processing AND heartbeat expired
  3. Resets to queued for re-processing
```
