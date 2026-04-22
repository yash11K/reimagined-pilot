# KB Manager v2 — Shared Contracts

> **This file is the source of truth for both backend and frontend agents.**
> Read this FIRST before reading your own spec file.

## Context

KB Manager is a platform that ingests content from various sources (AEM websites, uploaded documents, future connectors) into a curated knowledge base. It uses AI agents to discover, extract, validate, and classify content — then routes it to human review or auto-approves it into the KB.

### Tech Stack
- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (async + asyncpg), Alembic, boto3 (S3 + Bedrock), strands-agents, Pydantic v2
- **Frontend**: Next.js 14+ (App Router), React 18, TypeScript, Tailwind CSS, SWR, react-markdown
- **Database**: PostgreSQL 15+
- **AI Models**: Claude Sonnet (extraction) via Bedrock, Claude Haiku (discovery, triage, QA) via Bedrock

---

## 1. Database Schema

### Table: `sources`
Minimal. Connector-specific details live in JSONB, not as columns.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | Auto-generated |
| type | TEXT NOT NULL | `aem` \| `upload` |
| identifier | TEXT NOT NULL | URL for web sources, original filename for uploads |
| region | TEXT | |
| brand | TEXT | |
| kb_target | TEXT NOT NULL | `public` \| `internal` |
| metadata | JSONB | Connector-specific (nav_label, nav_section, page_path for AEM; mime_type for uploads) |
| created_at | TIMESTAMPTZ | Default now() |

**Indexes**: UNIQUE(type, identifier)

---

### Table: `ingestion_jobs`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | Auto-generated |
| source_id | UUID FK → sources | |
| status | TEXT NOT NULL | `scouting` \| `awaiting_confirmation` \| `processing` \| `completed` \| `failed` |
| steering_prompt | TEXT | Optional user prompt to guide extraction |
| scout_summary | JSONB | Content map data (components + links + summary). Schema below. |
| error_message | TEXT | |
| started_at | TIMESTAMPTZ | Default now() |
| completed_at | TIMESTAMPTZ | |

**Indexes**: (status), (source_id)

Counters (files_created, files_approved, etc.) are **computed from `kb_files`** via count queries — no denormalization.

**scout_summary JSONB shape:**
```json
{
  "components": [
    {
      "id": "comp_1",
      "type": "hero | card | text | faq | table | unknown",
      "title": "Loss Damage Waiver",
      "snippet": "Our premier protection product...",
      "included": true
    }
  ],
  "links": [
    {
      "id": "link_1",
      "target_url": "/en/protections/ldw",
      "anchor_text": "Learn More",
      "source_component_id": "comp_1",
      "classification": "expansion | sibling | navigation | uncertain",
      "reason": "Teaser card → full article",
      "has_sub_links": true,
      "sub_link_count": 3
    }
  ],
  "summary": {
    "total_components": 8,
    "included_components": 5,
    "total_links": 7,
    "auto_queued": 5,
    "uncertain": 1
  }
}
```

Link status (`auto_queued`, `confirmed`, `dismissed`) lives in `content_links` table, not in the JSONB. The JSONB is the agent's raw output. User overrides are persisted in the relational table.

---

### Table: `content_links`
Stores classified links discovered during scouting. `navigation` links are never stored — they're auto-dismissed and simply not inserted.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | Auto-generated |
| job_id | UUID FK → ingestion_jobs | |
| target_url | TEXT NOT NULL | Where the link points |
| anchor_text | TEXT | Visible link text |
| classification | TEXT NOT NULL | `expansion` \| `sibling` \| `uncertain` |
| classification_reason | TEXT | Agent's one-line reasoning |
| status | TEXT NOT NULL DEFAULT 'auto_queued' | `auto_queued` \| `confirmed` \| `dismissed` \| `ingested` |
| has_sub_links | BOOLEAN DEFAULT false | |
| sub_link_count | INT DEFAULT 0 | |
| created_at | TIMESTAMPTZ | |

**Indexes**: (job_id), UNIQUE(job_id, target_url)

---

### Table: `kb_files`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | Auto-generated |
| job_id | UUID FK → ingestion_jobs | |
| source_id | UUID FK → sources | |
| title | TEXT NOT NULL | |
| md_content | TEXT NOT NULL | Markdown with YAML frontmatter |
| source_url | TEXT | Original page URL |
| region | TEXT | |
| brand | TEXT | |
| kb_target | TEXT NOT NULL | `public` \| `internal` |
| modify_date | TIMESTAMPTZ | From AEM — for versioning |
| merged_from_urls | TEXT[] | If merged from expansion links |
| status | TEXT NOT NULL | `approved` \| `pending_review` \| `rejected` \| `in_kb` \| `superseded` |
| quality_verdict | TEXT | `good` \| `acceptable` \| `poor` |
| quality_reasoning | TEXT | 2-3 sentences |
| uniqueness_verdict | TEXT | `unique` \| `overlapping` \| `duplicate` |
| uniqueness_reasoning | TEXT | 2-3 sentences |
| similar_file_ids | UUID[] | Top 3 similar files if overlapping/duplicate |
| s3_key | TEXT | Full S3 key (bucket is a config, not per-file) |
| reviewed_by | TEXT | |
| review_notes | TEXT | |
| created_at | TIMESTAMPTZ | Default now() |

**Indexes**: (status), (source_id), (job_id), (kb_target), (source_url, modify_date)

---

### Table: `nav_tree_cache`
Caches AEM navigation trees with 24h TTL.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| root_url | TEXT UNIQUE | |
| brand | TEXT | |
| region | TEXT | |
| tree_data | JSONB | |
| fetched_at | TIMESTAMPTZ | |
| expires_at | TIMESTAMPTZ | |

---

## 2. API Contracts

Base URL: `/api/v1`

### Ingestion Flow

#### `POST /ingest`
Start a new ingestion. For web sources, triggers scouting. For uploads, triggers direct processing.

**Request (web):**
```json
{
  "connector_type": "aem",
  "urls": [
    {
      "url": "https://www.avis.com/en/products-and-services/protections.model.json",
      "region": "nam",
      "brand": "avis",
      "nav_label": "Protections",
      "nav_section": "Products & Services",
      "page_path": "/products-and-services/protections"
    }
  ],
  "kb_target": "public",
  "steering_prompt": null
}
```

**Request (upload):**
```json
{
  "connector_type": "upload",
  "kb_target": "internal",
  "steering_prompt": null
}
```
Files sent as multipart form data alongside the JSON.

**Response (202):**
```json
{
  "jobs": [
    { "job_id": "uuid", "source_url": "...", "status": "scouting" }
  ]
}
```

---

#### `GET /ingest/{job_id}/scout-stream` — SSE
Real-time stream of scouting progress.

**SSE Events:**
```
event: scouting_started
data: { "job_id": "uuid", "source_url": "..." }

event: component_found
data: { "id": "comp_1", "type": "card", "title": "Loss Damage Waiver", "snippet": "Our premier..." }

event: link_found
data: { "id": "link_1", "target_url": "/en/protections/ldw", "anchor_text": "Learn More", "source_component_id": "comp_1" }

event: link_classified
data: { "id": "link_1", "classification": "expansion", "reason": "Teaser card links to full article", "has_sub_links": true, "sub_link_count": 3, "status": "auto_queued" }

event: scout_complete
data: { "job_id": "uuid", "summary": { "total_components": 8, ... } }

event: error
data: { "job_id": "uuid", "message": "Failed to fetch model.json" }
```

---

#### `GET /ingest/{job_id}/content-map`
Returns full content map after scouting completes. Used for recovery if SSE disconnects.

**Response (200):**
```json
{
  "job_id": "uuid",
  "status": "awaiting_confirmation",
  "source_url": "...",
  "content_map": {
    "components": [...],
    "links": [...],
    "summary": {...}
  }
}
```

---

#### `POST /ingest/{job_id}/confirm`
User confirms the ingestion plan after reviewing the Content Map. Triggers extraction + QA.

**Request:**
```json
{
  "link_overrides": [
    { "link_id": "uuid", "classification": "dismissed" }
  ],
  "excluded_component_ids": ["comp_7"],
  "steering_prompt": "Focus on the FAQ section, the comparison table is more important than the hero"
}
```

**Response (202):**
```json
{ "job_id": "uuid", "status": "processing" }
```

---

#### `GET /ingest/{job_id}/progress-stream` — SSE
Real-time stream of extraction + QA progress. Connected after confirm.

**SSE Events:**
```
event: extraction_started
data: { "job_id": "uuid", "total_pages": 6 }

event: page_processing
data: { "url": "/en/protections/ldw", "page_number": 1, "total": 6, "is_expansion": true, "parent_url": "/en/protections" }

event: file_created
data: { "file_id": "uuid", "title": "Loss Damage Waiver", "merged": true, "merged_from": ["/en/protections (card)", "/en/protections/ldw (full)"] }

event: qa_started
data: { "file_id": "uuid", "title": "..." }

event: qa_complete
data: { "file_id": "uuid", "quality_verdict": "good", "quality_reasoning": "...", "uniqueness_verdict": "unique", "uniqueness_reasoning": "...", "status": "approved" }

event: job_complete
data: { "job_id": "uuid", "files_created": 6, "files_approved": 4, "files_review": 2, "files_rejected": 0 }

event: error
data: { "file_id": "uuid", "message": "..." }
```

---

### Files

#### `GET /files`
List files with filtering and pagination.

**Query params:** `page`, `size`, `status`, `region`, `brand`, `content_type`, `kb_target`, `job_id`, `source_id`, `search`

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Loss Damage Waiver (LDW)",
      "status": "pending_review",
      "region": "nam",
      "brand": "avis",
      "kb_target": "public",
      "quality_verdict": "good",
      "uniqueness_verdict": "overlapping",
      "source_url": "...",
      "created_at": "..."
    }
  ],
  "total": 42,
  "page": 1,
  "size": 20,
  "pages": 3
}
```

---

#### `GET /files/{file_id}`
Full file detail with content and QA reports.

**Response (200):**
```json
{
  "id": "uuid",
  "title": "...",
  "md_content": "---\ntitle: ...\n---\n# Loss Damage Waiver...",
  "status": "pending_review",
  "region": "nam",
  "brand": "avis",
  "kb_target": "public",
  "source_url": "...",
  "modify_date": "...",
  "merged_from_urls": ["..."],
  "quality_verdict": "good",
  "quality_reasoning": "Substantial 2000-word article covering LDW details...",
  "uniqueness_verdict": "overlapping",
  "uniqueness_reasoning": "73% semantic overlap with existing file about rental protections overview...",
  "similar_files": [
    { "id": "uuid", "title": "Rental Protections Overview", "source_url": "..." }
  ],
  "s3_key": null,
  "reviewed_by": null,
  "review_notes": null,
  "job_id": "uuid",
  "source_id": "uuid",
  "created_at": "..."
}
```

`similar_files` is a hydrated array — backend joins `similar_file_ids` UUIDs with file titles/URLs. `content_type` and `namespace` live in the markdown frontmatter, not as separate API fields.

---

#### `POST /files/{file_id}/approve`
**Request:**
```json
{ "reviewed_by": "reviewer@example.com", "notes": "optional" }
```
**Response (200):** Updated FileDetail. Triggers S3 upload in background.

---

#### `POST /files/{file_id}/reject`
**Request:**
```json
{ "reviewed_by": "reviewer@example.com", "notes": "Content too thin, mostly marketing copy" }
```
**Response (200):** Updated FileDetail.

---

#### `PUT /files/{file_id}`
Edit file content before approving.
**Request:**
```json
{ "md_content": "updated markdown...", "reviewed_by": "reviewer@example.com" }
```
**Response (200):** Updated FileDetail. Re-runs QA in background, returns immediately.

---

#### `POST /files/{file_id}/revalidate`
Re-run QA (quality + uniqueness) on a single file. Synchronous.
**Response (200):** Updated FileDetail with new verdicts.

---

### Sources

#### `GET /sources`
**Query params:** `page`, `size`, `type`, `region`, `brand`, `kb_target`
**Response (200):** PaginatedResponse of source summaries with job counts.

#### `GET /sources/{source_id}`
**Response (200):** Source detail with aggregate file stats (total, approved, pending, rejected).

#### `GET /sources/active-jobs`
**Response (200):** `{ "active_jobs": { "source_id": "job_id", ... } }`
Used for dashboard polling.

---

### Knowledge Base

#### `POST /kb/search` — SSE
Stream search results from the knowledge base.
**Request:**
```json
{ "query": "pet policy for rental cars", "kb_target": "public", "limit": 10 }
```
**SSE Events:**
```
event: result
data: { "rank": 1, "title": "...", "snippet": "...", "source_url": "...", "score": 0.89 }

event: search_complete
data: { "total_results": 5 }
```

---

#### `POST /kb/chat` — SSE
RAG chat — retrieve context then stream generated answer.
**Request:**
```json
{ "query": "What protections does Avis offer?", "kb_target": "public", "context_limit": 5 }
```
**SSE Events:**
```
event: sources
data: { "sources": [{ "title": "...", "url": "...", "snippet": "..." }] }

event: token
data: { "text": "Avis offers several" }

event: chat_complete
data: {}
```

---

#### `POST /kb/download`
Get presigned S3 download URL.
**Request:** `{ "s3_uri": "s3://bucket/key" }`
**Response (200):** `{ "download_url": "https://..." }`

---

### Navigation

#### `GET /nav/tree`
**Query params:** `url`, `force_refresh`
**Response (200):** Nested tree structure for AEM navigation.

---

### Dashboard Stats

#### `GET /stats`
All counts computed directly from `kb_files` and `ingestion_jobs` tables.

**Response (200):**
```json
{
  "total_files": 156,
  "pending_review": 12,
  "approved": 130,
  "rejected": 14,
  "active_jobs": 2,
  "sources_count": 23,
  "kb_public_files": 120,
  "kb_internal_files": 36
}
```

---

## 3. Routing Rules

After QA, files are auto-routed based on verdicts:

| Quality | Uniqueness | Result |
|---------|------------|--------|
| good | unique | **Auto-approve** → upload to S3, status = `approved` |
| good | overlapping | **Pending review** → reviewer sees similar files |
| good | duplicate | **Auto-reject** → status = `rejected` |
| acceptable | unique | **Pending review** → reviewer checks quality |
| acceptable | overlapping | **Pending review** |
| acceptable | duplicate | **Auto-reject** |
| poor | any | **Auto-reject** |

Metadata completeness is a **gate**, not a score. If required fields are missing, the extraction agent retries. If still missing, file is `rejected` with reasoning "Missing required metadata: [fields]".

Required metadata fields: `title`, `content_type`, `source_url`, `region`, `brand`

---

## 4. Link Classification Rules

| Signal | Classification |
|--------|---------------|
| Anchor text is "Learn More", "Read More", "View Details", "Get Started" AND source component is a card/teaser with < 100 words | **expansion** |
| Link URL is a child path of source page (e.g., /protections → /protections/ldw) AND source has teaser content | **expansion** |
| Link URL is a sibling path AND source page has substantial content of its own | **sibling** |
| Link is in a component matching known nav patterns (headerNavigation, footerNavigation, hamburgerMenu, multiColumnLinks) | **navigation** |
| Link URL matches URL denylist (/reservation, /login, /account, /search, /booking, /checkout) | **navigation** |
| None of the above clearly apply | **uncertain** |

Auto-routing:
- `expansion` → `auto_queued` (fetched and merged with parent)
- `sibling` → `auto_queued` (ingested as separate file)
- `navigation` → auto dismissed (not stored)
- `uncertain` → surfaced in Content Map for user decision
