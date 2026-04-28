# KB Manager v2 — Architecture Overview

## 1. What Is This?

KB Manager v2 is an AI-powered content ingestion service that crawls AEM (Adobe Experience Manager) websites, extracts meaningful content, runs it through LLM-based quality gates, and publishes approved articles to an AWS Bedrock Knowledge Base via S3.

It powers a customer-facing knowledge base for the Avis Budget Group brands (Avis, Budget).

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI (async, Python 3.12) |
| Database | PostgreSQL 15 (via SQLAlchemy async + asyncpg) |
| Migrations | Alembic |
| AI / LLM | AWS Bedrock — Claude Sonnet (extraction), Claude Haiku (classification/QA) |
| Agent Framework | Strands Agents SDK |
| Object Storage | AWS S3 (markdown + metadata sidecars) |
| Knowledge Base | AWS Bedrock Knowledge Base (Retrieve, RAG, Sync) |
| HTTP Client | httpx (async) |
| Config | pydantic-settings (`.env` file) |
| Containerisation | Docker multi-stage build + Docker Compose |

---

## 3. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                         │
│                        (kb_manager/main.py)                         │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Ingest   │  │  Files   │  │  Sources │  │  Queue   │  ...      │
│  │  Routes   │  │  Routes  │  │  Routes  │  │  Routes  │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                 │
│  ┌────▼──────────────▼──────────────▼──────────────▼─────────────┐  │
│  │                      Query Layer (queries/)                    │  │
│  │   files.py │ jobs.py │ sources.py │ queue.py │ search.py      │  │
│  └──────────────────────────┬────────────────────────────────────┘  │
│                             │                                       │
│  ┌──────────────────────────▼────────────────────────────────────┐  │
│  │                    SQLAlchemy ORM (models.py)                  │  │
│  │   Source │ IngestionJob │ KBFile │ QueueItem │ NavTreeCache   │  │
│  └──────────────────────────┬────────────────────────────────────┘  │
│                             │                                       │
│                    PostgreSQL (asyncpg)                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        Services Layer                                │
│                                                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │  Pipeline   │  │Queue Worker│  │  Stream    │  │  S3 Uploader │ │
│  │ (2-phase)  │  │(background)│  │  Manager   │  │              │ │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └──────┬───────┘ │
│        │               │               │                 │         │
│  ┌─────▼───────────────▼───────────────▼─────────────────▼───────┐ │
│  │                    AI Agents Layer                              │ │
│  │  Discovery │ Extractor │ Link Triage │ QA │ Uniqueness │ Meta │ │
│  └──────────────────────────┬────────────────────────────────────┘ │
│                             │                                       │
│                    AWS Bedrock (Claude Sonnet / Haiku)               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     External Services                                │
│                                                                     │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │  AWS S3   │  │ Bedrock KB (RAG) │  │ AEM Content Delivery      │ │
│  │  Bucket   │  │ Retrieve & Sync  │  │ (model.json endpoints)    │ │
│  └──────────┘  └──────────────────┘  └───────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Project Structure

```
kb_manager/
├── main.py                  # FastAPI app factory + lifespan
├── config.py                # pydantic-settings (env vars)
├── database.py              # Async engine + session factory
├── models.py                # SQLAlchemy ORM models
│
├── agents/                  # LLM-powered agents (Strands SDK)
│   ├── discovery.py         # AEM component + link classification
│   ├── extractor.py         # Component → markdown conversion
│   ├── link_triage.py       # Uncertain link classification
│   ├── metadata_enricher.py # Raw content → rich metadata
│   └── qa.py                # Quality gate + uniqueness check
│
├── services/                # Core business logic
│   ├── pipeline.py          # Two-phase orchestrator (Scout → Process)
│   ├── queue_worker.py      # Background worker with bounded concurrency
│   ├── stream_manager.py    # In-memory SSE event bus
│   ├── s3_uploader.py       # S3 upload + metadata sidecars
│   ├── versioning.py        # Content version comparison
│   ├── routing_matrix.py    # QA verdict → file status mapping
│   ├── aem_pruner.py        # Deterministic AEM JSON pruning
│   ├── bedrock_kb.py        # Bedrock KB client (Retrieve/RAG/Sync)
│   └── nav_parser.py        # AEM navigation tree extraction
│
├── routes/                  # API endpoint modules
│   ├── ingest.py            # POST /ingest, SSE streams
│   ├── files.py             # CRUD + approve/reject/revalidate
│   ├── sources.py           # List, detail, confirm, delete
│   ├── jobs.py              # Paginated job listing
│   ├── queue.py             # Queue management + events SSE
│   ├── search.py            # Global search across entities
│   ├── kb.py                # Bedrock KB search + chat
│   ├── nav.py               # Navigation tree parsing
│   ├── stats.py             # Dashboard statistics
│   └── activity.py          # Activity log
│
├── queries/                 # Async DB query functions
│   ├── files.py, jobs.py, sources.py, queue.py
│   ├── search.py, links.py, nav_cache.py
│   └── __init__.py
│
├── schemas/                 # Pydantic request/response models
│   ├── ingest.py, files.py, jobs.py, sources.py
│   ├── search.py, kb.py, common.py
│   └── __init__.py
│
└── alembic/                 # Database migrations
    └── versions/
        ├── 001_baseline.py
        ├── 002_queue_improvements.py
        └── 003_add_progress_pct.py

scripts/                     # Operational scripts
├── ingest_excel.py          # Bulk Excel import with LLM enrichment
├── cleanup_failed_run.py    # Stale data cleanup
├── retro_seed_job.py        # Debug dump for specific jobs
├── reset_orphan_sources.py  # Orphan source reset
└── truncate_tables.py       # Full table truncation
```

---

## 5. Application Startup Sequence

```
uvicorn kb_manager.main:app
        │
        ▼
    lifespan()
        │
        ├── _configure_logging()
        ├── init_engine()              → PostgreSQL async engine
        ├── StreamManager()            → In-memory SSE event bus
        ├── S3Uploader()               → boto3 S3 client
        ├── VersioningService()        → Content version comparator
        ├── Pipeline(stream, s3, ver)  → Two-phase orchestrator
        ├── QueueWorker(pipeline, ...) → Background worker
        │       └── .start()           → Spawns poll loop + stale sweep
        │
        ├── Mount 10 route modules under /api/v1
        └── GET /health endpoint
```

---

## 6. Core Design Patterns

### Two-Phase Pipeline
Every ingestion goes through Scout (discovery) → Process (extraction + QA + upload). This separation allows the system to discover child pages, classify links, and queue them for independent processing.

### Background Queue Worker
A semaphore-bounded worker continuously polls the queue, claims items, and runs the full pipeline. Heartbeat-based stale detection reclaims crashed items. Exponential backoff handles transient failures.

### SSE Real-Time Streaming
Two-layer event bus: per-job channels for pipeline progress, and a global typed event stream for the UI. Clients subscribe once and filter client-side.

### LLM Defense-in-Depth
Deterministic link extraction runs first (guaranteed, no misses), then the Discovery Agent classifies links. URL validation catches hallucinated URLs. JSON parsing fallbacks handle malformed LLM output.

### Metadata Sidecars
Each S3 markdown file has a companion `.metadata.json` sidecar that enables Bedrock KB filtering by title, region, brand, category, tags, and visibility.

### Routing Matrix
A pure-function 2×3 matrix maps (quality_verdict, uniqueness_verdict) → file status, with a metadata completeness gate. No side effects, fully testable.

---

## 7. Environment Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — (required) | PostgreSQL async connection string |
| `S3_BUCKET_NAME` | — (required) | S3 bucket for KB files |
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-20250514-v1:0` | Sonnet model for extraction |
| `HAIKU_MODEL_ID` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Haiku model for classification |
| `BEDROCK_KB_ID` | `None` | Bedrock Knowledge Base ID |
| `BEDROCK_DS_ID` | `None` | Bedrock data source ID for sync |
| `MAX_CONCURRENT_JOBS` | `3` | Max parallel ingestion jobs |
| `QUEUE_POLL_INTERVAL` | `3` | Seconds between queue polls |
| `QUEUE_MAX_RETRIES` | `3` | Max retries for failed items |
| `QUEUE_STALE_TIMEOUT` | `300` | Seconds before stale detection |

---

## 8. Deployment

### Docker Compose (Development)
```yaml
services:
  db:   PostgreSQL 15 on port 5432
  api:  KB Manager on port 8000
        → runs alembic upgrade head, then uvicorn
```

### Docker Image (Production)
Multi-stage build: `python:3.12-slim` base, dependencies installed in builder stage, app copied to runtime stage. Exposes port 8000.
