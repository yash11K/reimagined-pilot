# API Routes — Endpoint Reference

**Directory:** `kb_manager/routes/`
**Base path:** `/api/v1`

All routes are mounted in `main.py` under the `/api/v1` prefix.

---

## Ingestion (`routes/ingest.py`)

### `POST /api/v1/ingest`
Start a new ingestion job.

**Request Body:**
```json
{
    "connector_type": "aem",          // "aem" | "upload"
    "urls": [
        {
            "url": "https://www.avis.com/en/products.model.json",
            "region": "nam",
            "brand": "avis",
            "nav_label": "Products",   // optional
            "nav_section": "main",     // optional
            "page_path": "/en/products" // optional
        }
    ],
    "kb_target": "public",            // "public" | "internal"
    "steering_prompt": "Focus on..."  // optional
}
```

**Response:** `IngestResponse` with list of `JobCreated` (job_id, source_id, source_url, status)

For `connector_type=upload`, files are sent as multipart form data.

### `GET /api/v1/ingest/{job_id}/scout-stream`
SSE stream of scout phase events. Events: `scouting_started`, `component_found`, `link_found`, `link_classified`, `scout_complete`.

### `GET /api/v1/ingest/{job_id}/progress-stream`
SSE stream of process phase events. Events: `extraction_started`, `page_processing`, `file_created`, `file_qa_complete`, `job_complete`.

### `GET /api/v1/ingest/{job_id}/content-map`
Returns the scout summary after scout phase completes.

---

## Files (`routes/files.py`)

### `GET /api/v1/files`
List KB files with pagination and filters.

**Query params:** `page`, `size`, `status`, `region`, `brand`, `kb_target`, `job_id`, `source_id`, `search`

**Response:** `PaginatedResponse[FileSummary]`

### `GET /api/v1/files/{file_id}`
Get full file detail including markdown content, QA verdicts, similar files, and source references.

**Response:** `FileDetail`

### `POST /api/v1/files/{file_id}/approve`
Approve a file. Triggers background S3 upload + KB sync.

**Request Body:** `{ "reviewed_by": "user@example.com", "notes": "..." }`

### `POST /api/v1/files/{file_id}/reject`
Reject a file with reviewer info.

**Request Body:** `{ "reviewed_by": "user@example.com", "notes": "..." }`

### `PUT /api/v1/files/{file_id}`
Edit file markdown content. Triggers background QA re-run.

**Request Body:** `{ "md_content": "...", "reviewed_by": "user@example.com" }`

### `POST /api/v1/files/{file_id}/revalidate`
Re-run QA + Uniqueness synchronously and re-route via routing matrix.

### `DELETE /api/v1/files/{file_id}`
Hard-delete a file. Background S3 cleanup.

---

## Sources (`routes/sources.py`)

### `GET /api/v1/sources`
List sources with pagination and filters.

**Query params:** `page`, `size`, `type`, `status`, `region`, `brand`, `kb_target`, `search`

**Response:** `PaginatedResponse[SourceSummary]`

### `GET /api/v1/sources/{source_id}`
Get source detail including file stats (total, approved, pending, rejected).

**Response:** `SourceDetail`

### `GET /api/v1/sources/active-jobs`
Map of `source_id → job_id` for all currently active jobs.

### `POST /api/v1/sources/{source_id}/confirm`
Confirm or discard a source in `needs_confirmation` state.

**Request Body:** `{ "action": "process" | "discard" }`

### `DELETE /api/v1/sources/{source_id}`
Delete source + cascade-delete linked files + background S3 cleanup.

---

## Jobs (`routes/jobs.py`)

### `GET /api/v1/jobs`
List ingestion jobs with computed fields (source label, discovered count).

**Query params:** `page`, `size`, `status` (comma-separated), `source_id`, `brand`, `sort` (e.g. `started_at:desc`)

**Response:** `PaginatedResponse[JobSummary]`

---

## Queue (`routes/queue.py`)

### `POST /api/v1/queue`
Add URLs to the worker queue.

**Request Body:**
```json
{
    "urls": ["https://...model.json", "https://...model.json"],
    "region": "nam",
    "brand": "avis",
    "kb_target": "public",
    "priority": 0
}
```

### `GET /api/v1/queue`
List queue items with pagination.

**Query params:** `page`, `size`, `status`

### `GET /api/v1/queue/counts`
Lightweight queue status: counts by status + active worker count.

### `GET /api/v1/events/stream`
Global SSE event stream for the dashboard. Topics: `worker`, `queue`, `progress`.

### `GET /api/v1/logs/stream`
Legacy alias for `/events/stream`.

---

## Search (`routes/search.py`)

### `GET /api/v1/search`
Global search across files and jobs.

**Query params:** `q` (required), `limit` (default 5), `entity` (comma-separated: `files`, `jobs`)

**Response:** `GlobalSearchResponse` with `files` and `jobs` buckets.

---

## Knowledge Base (`routes/kb.py`)

### `POST /api/v1/kb/search`
Search the Bedrock Knowledge Base. Returns SSE stream of ranked results.

**Request Body:** `{ "query": "...", "kb_target": "public", "limit": 10 }`

### `POST /api/v1/kb/chat`
RAG chat with the Bedrock Knowledge Base. Returns SSE stream of generated answer + citations.

**Request Body:** `{ "query": "...", "kb_target": "public", "session_id": "..." }`

---

## Navigation (`routes/nav.py`)

### `GET /api/v1/nav`
Parse and return navigation tree from an AEM URL. Caches results.

**Query params:** `url` (AEM model.json URL)

---

## Stats (`routes/stats.py`)

### `GET /api/v1/stats`
Dashboard statistics: file counts by status, source counts, job counts, queue status.

---

## Activity (`routes/activity.py`)

### `GET /api/v1/activity`
Recent activity log (latest jobs, file changes, queue events).

**Query params:** `limit` (default 20)

---

## Health Check

### `GET /health`
Returns `{"status": "ok"}`. Not under `/api/v1` prefix.
