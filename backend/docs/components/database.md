# Database Layer — Models, Queries & Migrations

**Files:** `kb_manager/models.py`, `kb_manager/database.py`, `kb_manager/queries/`, `kb_manager/alembic/`

---

## Database Setup

**Engine:** PostgreSQL 15 via SQLAlchemy async + asyncpg
**Session:** `async_sessionmaker` with `expire_on_commit=False`
**Connection:** Pool with `pool_pre_ping=True` for connection health checks

```python
# database.py
init_engine()       # Creates engine + session factory (called at startup)
dispose_engine()    # Closes pool (called at shutdown)
get_db()            # FastAPI dependency → yields AsyncSession
```

---

## Entity-Relationship Diagram

```
┌──────────────┐       1:N       ┌──────────────────┐       1:N       ┌──────────────┐
│   Source      │───────────────►│  IngestionJob     │───────────────►│   KBFile      │
│              │                 │                    │                │              │
│ id (PK)      │                 │ id (PK)            │                │ id (PK)       │
│ url          │                 │ source_id (FK)     │                │ job_id (FK)   │
│ type         │                 │ status             │                │ title         │
│ region       │                 │ progress_pct       │                │ md_content    │
│ brand        │                 │ steering_prompt    │                │ source_url    │
│ kb_target    │                 │ error_message      │                │ status        │
│ status       │                 │ started_at         │                │ s3_key        │
│ is_scouted   │                 │ completed_at       │                │ ...           │
│ is_ingested  │                 └──────────────────┘                └──────┬───────┘
│ scout_summary│                                                            │
│ metadata     │                                                            │
└──────┬───────┘                                                            │
       │                                                                    │
       │              M:N (source_kb_files junction)                        │
       └────────────────────────────────────────────────────────────────────┘

┌──────────────────┐                    ┌──────────────────┐
│  NavTreeCache     │                    │   QueueItem       │
│                    │                    │                    │
│ id (PK)            │                    │ id (PK)            │
│ root_url (unique)  │                    │ url                │
│ brand              │                    │ status             │
│ region             │                    │ job_id (FK)        │
│ tree_data (JSONB)  │                    │ retry_count        │
│ fetched_at         │                    │ last_heartbeat     │
│ expires_at         │                    │ priority           │
└──────────────────┘                    └──────────────────┘
```

---

## Model: Source

The unified entity for any content URL entering the system.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `url` | Text | Content URL |
| `type` | Text | `aem` \| `upload` \| `manual` |
| `region` | Text? | `nam` \| `emea` \| `apac` |
| `brand` | Text? | `avis` \| `budget` |
| `kb_target` | Text | `public` \| `internal` |
| `status` | Text | `active` \| `needs_confirmation` \| `dismissed` \| `ingested` \| `failed` \| `denied_*` |
| `is_scouted` | Boolean | Scout phase completed |
| `is_ingested` | Boolean | Process phase completed |
| `scout_summary` | JSONB? | Components + link classification summary |
| `metadata_` | JSONB? | Arbitrary metadata (reason, anchor_text, etc.) |
| `last_ingested_at` | Timestamp? | Last successful ingestion |

**Unique constraint:** `(type, url)` — prevents duplicate sources.

---

## Model: IngestionJob

An execution instance against a source.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `source_id` | UUID (FK) | Parent source |
| `status` | Text | `scouting` \| `awaiting_confirmation` \| `processing` \| `completed` \| `failed` |
| `progress_pct` | Integer | 0-100 progress indicator |
| `steering_prompt` | Text? | User-provided guidance for extraction |
| `error_message` | Text? | Failure details |
| `started_at` | Timestamp | Job creation time |
| `completed_at` | Timestamp? | Completion time |

---

## Model: KBFile

An extracted knowledge base article.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `job_id` | UUID (FK) | Parent job |
| `title` | Text | Article title |
| `md_content` | Text | Pure markdown (no YAML frontmatter) |
| `source_url` | Text? | Primary source URL (denormalized) |
| `region` | Text? | Content region |
| `brand` | Text? | Content brand |
| `kb_target` | Text | `public` \| `internal` |
| `category` | Text? | `faq` \| `policy` \| `product` \| `service` \| etc. |
| `visibility` | Text? | `public` \| `internal` \| `restricted` |
| `tags` | Text[]? | Descriptive tags |
| `status` | Text | `pending_review` \| `approved` \| `rejected` \| `superseded` |
| `quality_verdict` | Text? | `accepted` \| `rejected` |
| `quality_reasoning` | Text? | QA agent explanation |
| `uniqueness_verdict` | Text? | `unique` \| `overlapping` \| `conflicting` |
| `uniqueness_reasoning` | Text? | Uniqueness agent explanation |
| `similar_file_ids` | UUID[]? | IDs of similar existing files |
| `s3_key` | Text? | S3 object key (set after upload) |
| `reviewed_by` | Text? | Human reviewer |
| `review_notes` | Text? | Review comments |

---

## Model: QueueItem

Worker queue for automated ingestion.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `url` | Text | URL to process |
| `status` | Text | `queued` \| `processing` \| `completed` \| `failed` |
| `job_id` | UUID? (FK) | Linked job (set after processing starts) |
| `retry_count` | Integer | Current retry attempt |
| `max_retries` | Integer | Max allowed retries (default: 3) |
| `next_attempt_at` | Timestamp? | Earliest retry time (backoff) |
| `last_heartbeat` | Timestamp? | Worker liveness proof |
| `priority` | Integer | Higher = processed first |

**Partial unique index:** `(url)` WHERE `status IN ('queued', 'processing')` — prevents duplicate active items.

---

## Model: NavTreeCache

Cached navigation trees parsed from AEM.

| Field | Type | Description |
|---|---|---|
| `root_url` | Text (unique) | AEM navigation root URL |
| `tree_data` | JSONB? | Parsed navigation tree |
| `expires_at` | Timestamp? | Cache TTL |

---

## Query Layer (`queries/`)

Async functions organized by entity. All accept `AsyncSession` as first argument.

### `queries/files.py`
- `create_file(**kwargs)` → KBFile
- `link_source_to_file(source_id, file_id)` — M2M junction insert
- `get_file(file_id)` → KBFile?
- `list_files(page, size, status?, region?, brand?, ...)` → paginated
- `update_file(file_id, **kwargs)` → KBFile
- `delete_file(file_id)` → bool
- `count_files_by_status(source_id)` → dict

### `queries/jobs.py`
- `create_job(**kwargs)` → IngestionJob
- `get_job(job_id)` → IngestionJob?
- `list_jobs_extended(page, size, status?, ...)` → paginated with computed fields
- `update_job(job_id, **kwargs)`
- `update_job_status(job_id, status)`
- `get_active_jobs()` → list of active jobs

### `queries/sources.py`
- `create_source(**kwargs)` → Source
- `get_source(source_id)` → Source?
- `get_source_by_url(url, type)` → Source?
- `list_sources(page, size, ...)` → paginated
- `update_source(source_id, **kwargs)`
- `mark_scouted(source_id, scout_summary)`
- `mark_ingested(source_id)`
- `dismiss_source(source_id)`
- `delete_source(source_id)`

### `queries/queue.py`
- `add_to_queue(url, region?, brand?, ...)` → QueueItem
- `get_queue_items(page, size, status?)` → paginated
- `claim_next()` → QueueItem? (FOR UPDATE SKIP LOCKED)
- `update_heartbeat(item_id)`
- `mark_completed(item_id, job_id)`
- `mark_failed(item_id, error, retry_base_delay)` → dict with outcome
- `reclaim_stale(stale_timeout)` → list of reclaimed items

### `queries/search.py`
- `search_files(q, limit)` → ILIKE on title, tags, source_url
- `search_jobs(q, limit)` → ILIKE on source label

---

## Migrations

| Version | Description |
|---|---|
| `001_baseline` | Initial schema: sources, ingestion_jobs, kb_files, nav_tree_cache, queue_items, source_kb_files junction |
| `002_queue_improvements` | Heartbeat, priority, retry logic, partial unique index on queue_items |
| `003_add_progress_pct` | Progress percentage tracking on ingestion_jobs |
