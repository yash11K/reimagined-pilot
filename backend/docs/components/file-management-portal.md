# File Management Portal — Implementation Strategy

## 1. Overview

This document outlines the implementation strategy for a **SharePoint-inspired File Management Portal** that provides a rich UI/UX for manual uploads into the Knowledge Base system. The portal replaces raw file upload workflows with a structured document management experience — virtual folder hierarchies, metadata enrichment sidecars, drag-and-drop uploads, and full lifecycle tracking — while S3 remains the ultimate storage backend.

This is designed as a **standalone component** that can be integrated with the existing KB Manager system but does not require modifications to the current pipeline.

---

## 2. Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Mirrored folder hierarchy (DB + S3)** | The folder tree lives in PostgreSQL for fast querying AND is mirrored as real S3 key prefixes. S3 organizes files in the same folder structure the user sees — not flat. |
| **Presigned URL direct upload** | Files go straight from browser → S3 (no server proxy for large files). The backend only issues the presigned URL and tracks the upload record. |
| **Metadata-first ingestion** | Every upload triggers an async enrichment pipeline that produces a `.metadata.json` sidecar alongside the content file — consistent with the existing Bedrock KB sidecar pattern. |
| **Optimistic UI with eventual consistency** | The portal shows the file immediately after upload confirmation; metadata enrichment and KB sync happen asynchronously with status indicators. |
| **Content-type agnostic** | Supports PDF, DOCX, XLSX, Markdown, plain text, and images. Format-specific extractors normalize content before enrichment. |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (React/Next.js)                       │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ Explorer  │  │ Upload Modal │  │ Detail View│  │ Bulk Actions │  │
│  │ Tree View │  │ + Drag/Drop  │  │ + Metadata │  │ + Search     │  │
│  └──────────┘  └──────────────┘  └────────────┘  └──────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ REST / SSE
┌────────────────────────────▼────────────────────────────────────────┐
│                     Portal API (FastAPI)                              │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ Folder CRUD│  │ Upload Broker│  │ File Manager │  │ Search    │  │
│  │ (virtual)  │  │ (presigned)  │  │ (lifecycle)  │  │ (FTS+meta)│  │
│  └────────────┘  └──────────────┘  └──────────────┘  └──────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐
│   PostgreSQL    │  │       S3        │  │  Enrichment Pipeline  │
│ • folders       │  │ • mirrored      │  │  • Text extraction    │
│ • portal_files  │  │   folder tree   │  │  • Metadata enricher  │
│ • versions      │  │ • content files │  │  • Sidecar generation │
│ • permissions   │  │ • sidecars      │  │  • KB sync trigger    │
│                 │  │ • thumbnails    │  │                       │
└─────────────────┘  └─────────────────┘  └──────────────────────┘
```

---

## 4. Data Model

### 4.1 `portal_folders` — Virtual Folder Hierarchy

```sql
CREATE TABLE portal_folders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id       UUID REFERENCES portal_folders(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,          -- URL-safe segment
    s3_prefix       TEXT NOT NULL,          -- computed: parent prefix + slug + "/"
    kb_target       TEXT NOT NULL,
    brand           TEXT,
    region          TEXT,
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    UNIQUE (parent_id, slug)
);

-- Materialized path index for fast tree queries
CREATE INDEX ix_portal_folders_prefix ON portal_folders (s3_prefix);
CREATE INDEX ix_portal_folders_parent ON portal_folders (parent_id);
```

### 4.2 `portal_files` — Upload Records

```sql
CREATE TABLE portal_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id       UUID NOT NULL REFERENCES portal_folders(id) ON DELETE RESTRICT,
    original_name   TEXT NOT NULL,          -- user's filename
    display_name    TEXT,                   -- editable title
    mime_type       TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    s3_key          TEXT NOT NULL UNIQUE,   -- final location in S3
    sidecar_s3_key  TEXT,                   -- .metadata.json sidecar key
    
    -- Enrichment state machine
    enrichment_status TEXT NOT NULL DEFAULT 'pending',
        -- pending | extracting | enriching | complete | failed
    
    -- Enriched metadata (populated async)
    title           TEXT,
    category        TEXT,
    tags            TEXT[],
    visibility      TEXT DEFAULT 'public',
    language        TEXT,
    
    -- Versioning
    version         INT NOT NULL DEFAULT 1,
    previous_version_id UUID REFERENCES portal_files(id),
    is_latest       BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Audit
    uploaded_by     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    -- Link to existing KB system (optional)
    kb_file_id      UUID REFERENCES kb_files(id) ON DELETE SET NULL
);

CREATE INDEX ix_portal_files_folder ON portal_files (folder_id) WHERE is_latest = TRUE;
CREATE INDEX ix_portal_files_enrichment ON portal_files (enrichment_status);
CREATE INDEX ix_portal_files_search ON portal_files USING gin (to_tsvector('english', coalesce(display_name, '') || ' ' || coalesce(title, '')));
```

### 4.3 `portal_file_versions` — Version History

```sql
CREATE TABLE portal_file_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID NOT NULL REFERENCES portal_files(id) ON DELETE CASCADE,
    version         INT NOT NULL,
    s3_key          TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    change_summary  TEXT,                   -- auto-generated or user-provided
    uploaded_by     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),

    UNIQUE (file_id, version)
);
```

---

## 5. Upload Flow — Presigned URL Pattern

The upload flow follows the industry-standard **presigned URL direct-upload** pattern, keeping large file payloads off the application server.

```
Browser                    Portal API                    S3
  │                            │                          │
  │ 1. POST /portal/uploads    │                          │
  │    {folder_id, filename,   │                          │
  │     mime_type, size}        │                          │
  │ ──────────────────────────►│                          │
  │                            │                          │
  │                            │ 2. Validate (size, type, │
  │                            │    folder permissions)   │
  │                            │                          │
  │                            │ 3. Compute S3 key from   │
  │                            │    folder.s3_prefix +    │
  │                            │    sanitized filename    │
  │                            │                          │
  │                            │ 4. Generate presigned    │
  │                            │    PUT URL (5 min TTL)   │
  │                            │ ─────────────────────────►
  │                            │                          │
  │ 5. Return {upload_url,     │                          │
  │    file_id, s3_key}        │                          │
  │ ◄──────────────────────────│                          │
  │                            │                          │
  │ 6. PUT file directly ─────────────────────────────────►
  │                            │                          │
  │ 7. POST /portal/uploads/   │                          │
  │    {file_id}/confirm       │                          │
  │ ──────────────────────────►│                          │
  │                            │ 8. Verify object exists  │
  │                            │    (HeadObject)          │
  │                            │ ─────────────────────────►
  │                            │                          │
  │                            │ 9. Enqueue enrichment    │
  │                            │    task                  │
  │                            │                          │
  │ 10. Return {status: ok}    │                          │
  │ ◄──────────────────────────│                          │
```

### Key Design Decisions

- **5-minute presigned URL TTL** — short enough to limit abuse, long enough for large files on slow connections.
- **Multipart upload** for files > 100 MB — the API returns multiple presigned URLs for parts, and the frontend uses the S3 multipart upload protocol.
- **Upload confirmation step** — the backend verifies the object landed in S3 (HeadObject) before marking the record as uploaded and triggering enrichment. This prevents orphan DB records.
- **Quarantine prefix** — files initially land in `_staging/{file_id}/` and are moved to their final organized folder path only after validation passes (virus scan, size check, format validation). The final key mirrors the folder hierarchy: `{folder.s3_prefix}{sanitized_filename}`.

---

## 6. Metadata Enrichment Pipeline

After upload confirmation, an async enrichment pipeline processes the file:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  1. Extract  │────►│  2. Enrich   │────►│  3. Sidecar  │────►│  4. KB Sync  │
│  Raw Text    │     │  Metadata    │     │  Upload      │     │  Trigger     │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Stage 1: Text Extraction

| Format | Extraction Method |
|--------|-------------------|
| Markdown (.md) | Direct pass-through |
| PDF | `pdfplumber` or `PyMuPDF` for text + layout |
| DOCX | `python-docx` for structured text |
| XLSX | `openpyxl` → row-based markdown table |
| Plain text | Direct pass-through |
| Images | OCR via Textract or skip (metadata-only) |

### Stage 2: Metadata Enrichment (LLM-powered)

Reuses the existing `MetadataEnricher` agent pattern:

- **Input**: Extracted text content + user-provided hints (folder context, filename)
- **Output**: `EnrichedMetadata` — title, category, tags, visibility, brand, language
- **Model**: Claude Haiku (fast, cheap, sufficient for classification)
- **Fallback**: If LLM fails, derive metadata from filename + folder hierarchy

### Stage 3: Sidecar Generation

Produces a `.metadata.json` file following the existing Bedrock KB sidecar format:

```json
{
  "metadataAttributes": {
    "title": {"value": "Refueling Policies and Fees", "type": "STRING"},
    "category": {"value": "policy", "type": "STRING"},
    "brand": {"value": "avis", "type": "STRING"},
    "tags": {"value": ["fuel", "refueling", "charges"], "type": "STRING_LIST"},
    "source_type": {"value": "manual_upload", "type": "STRING"},
    "uploaded_by": {"value": "john.doe@company.com", "type": "STRING"},
    "folder_path": {"value": "/policies/fuel/", "type": "STRING"}
  }
}
```

### Stage 4: KB Sync Trigger

After sidecar upload, triggers a Bedrock Knowledge Base data-source sync (same as the existing `_trigger_kb_sync` pattern in the pipeline).

---

## 7. Mirrored Folder System (DB + S3)

### 7.1 Folder Hierarchy — Mirrored in S3

The folder hierarchy is stored in PostgreSQL for fast querying **and** mirrored as real S3 key prefixes. S3 organizes files in the exact same structure the user sees in the portal — browsing the S3 bucket directly (via console or CLI) shows the same logical tree:

```
s3://kb-portal-bucket/
├── policies/
│   ├── fuel/
│   │   ├── refueling-policies.md
│   │   ├── refueling-policies.md.metadata.json
│   │   └── fuel-surcharge-guide.pdf
│   └── insurance/
│       ├── liability-coverage.md
│       └── liability-coverage.md.metadata.json
├── faqs/
│   ├── avis/
│   │   ├── loyalty-program.md
│   │   └── loyalty-program.md.metadata.json
│   └── budget/
│       └── fastbreak-enrollment.md
└── training/
    └── onboarding-guide.docx
```

The DB `s3_prefix` column on each folder is the **source of truth** for where files land. When a user creates a folder "Fuel" under "Policies", the system:
1. Inserts the DB row with `s3_prefix = "policies/fuel/"`
2. Creates a zero-byte S3 "folder marker" object at `policies/fuel/` (optional — ensures the prefix shows up in S3 console even when empty)

### 7.2 Operations — DB and S3 Stay in Sync

| Operation | DB Action | S3 Action |
|-----------|-----------|-----------|
| Create folder | Insert row, compute prefix from parent chain | Create zero-byte folder marker at prefix (e.g. `policies/fuel/`) |
| Rename folder | Update name + slug, cascade prefix updates to all descendants | **Copy all objects** under old prefix to new prefix, then delete originals (async batch job) |
| Move folder | Re-parent, recompute prefix for entire subtree | **Copy all objects** from old prefix tree to new prefix tree, delete originals (async batch job) |
| Delete folder | Soft-delete row + cascade to children | Delete all objects under prefix including sidecars (async batch job) |
| Upload file | Insert `portal_files` row | File lands at `{folder.s3_prefix}{sanitized_filename}` |
| List contents | Query `portal_files WHERE folder_id = X AND is_latest = TRUE` | Not needed — DB is the fast-read path |

### 7.3 Why Mirror Instead of Flat?

| Benefit | Explanation |
|---------|-------------|
| **S3 console browsability** | Ops teams can navigate the bucket directly without needing the portal UI |
| **Bedrock KB data-source scoping** | Bedrock KB can be pointed at specific S3 prefixes (e.g. only `policies/`) for targeted knowledge bases |
| **Disaster recovery** | If the DB is lost, the S3 structure is self-describing — files can be re-indexed from prefix paths |
| **IAM prefix policies** | S3 bucket policies can restrict access by prefix (e.g. brand teams only see their folder) |
| **Lifecycle rules** | S3 lifecycle policies can target specific prefixes (e.g. archive `training/` after 90 days) |

### 7.4 Handling Renames/Moves at Scale

S3 has no native rename — it requires copy + delete. For large folder trees this is expensive, so:

1. **Async batch job** — Folder rename/move enqueues a background task. The UI shows "Reorganizing…" status.
2. **Dual-pointer window** — During the copy, both old and new prefixes are valid. The DB points to the new prefix immediately; a redirect map handles in-flight presigned URLs pointing to the old key.
3. **Batch delete after verification** — Old objects are only deleted after confirming all copies succeeded (checksum match).
4. **Rate limiting** — S3 copy operations are throttled to avoid 503 SlowDown errors on high-object-count prefixes.

### 7.3 Breadcrumb Navigation

The API returns the full ancestor chain for any folder using a recursive CTE:

```sql
WITH RECURSIVE ancestors AS (
    SELECT id, parent_id, name, slug, 0 AS depth
    FROM portal_folders WHERE id = :folder_id
    UNION ALL
    SELECT f.id, f.parent_id, f.name, f.slug, a.depth + 1
    FROM portal_folders f JOIN ancestors a ON f.id = a.parent_id
)
SELECT * FROM ancestors ORDER BY depth DESC;
```

---

## 8. Versioning Strategy

Inspired by SharePoint's document versioning:

- **Major versions only** (1, 2, 3…) — no minor/draft versions for simplicity.
- **Upload to existing filename** in the same folder triggers a new version.
- Previous version's S3 object is retained (moved to `versions/{file_id}/v{n}/`).
- The `portal_files.is_latest` flag ensures listing queries only show current versions.
- Version history is viewable in the file detail panel.
- **Restore** = create a new version from an old version's content.

---

## 9. UI/UX Components (SharePoint-Inspired)

### 9.1 Explorer View (Main Panel)

- **Left sidebar**: Folder tree with expand/collapse, drag-to-move
- **Main area**: File grid/list view with columns (Name, Modified, Size, Status, Tags)
- **Top bar**: Breadcrumb path + search + view toggle (grid/list) + "New Folder" / "Upload"
- **Right panel**: File detail/metadata preview on selection

### 9.2 Upload Experience

- **Drag-and-drop zone** overlays the current folder view
- **Multi-file upload** with progress bars per file
- **Upload queue** showing enrichment status (extracting → enriching → complete)
- **Inline metadata override** — user can edit auto-derived metadata before finalizing

### 9.3 File Detail Panel

- Preview (markdown rendered, PDF thumbnail, etc.)
- Metadata card (title, category, tags — editable)
- Version history timeline
- Download link (presigned URL)
- "Publish to KB" action (links to existing KB system)

### 9.4 Bulk Operations

- Multi-select with checkboxes
- Bulk move, bulk delete, bulk tag, bulk re-enrich
- Bulk download as ZIP (server-side assembly)

---

## 10. API Surface

### Folders

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/portal/folders` | List root folders |
| GET | `/portal/folders/{id}` | Get folder + children |
| GET | `/portal/folders/{id}/breadcrumb` | Ancestor chain |
| POST | `/portal/folders` | Create folder |
| PATCH | `/portal/folders/{id}` | Rename/move folder |
| DELETE | `/portal/folders/{id}` | Delete folder (soft) |

### Files

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/portal/folders/{id}/files` | List files in folder |
| GET | `/portal/files/{id}` | File detail + metadata |
| GET | `/portal/files/{id}/versions` | Version history |
| PATCH | `/portal/files/{id}` | Update metadata |
| DELETE | `/portal/files/{id}` | Soft-delete file |
| POST | `/portal/files/{id}/restore` | Restore from version |

### Uploads

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/portal/uploads/initiate` | Get presigned URL |
| POST | `/portal/uploads/{id}/confirm` | Confirm upload landed |
| POST | `/portal/uploads/{id}/multipart/initiate` | Start multipart |
| POST | `/portal/uploads/{id}/multipart/complete` | Complete multipart |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/portal/search?q=...&tags=...&category=...` | Full-text + faceted search |

---

## 11. Security & Access Control

| Concern | Approach |
|---------|----------|
| Upload authorization | Presigned URLs scoped to specific key + short TTL |
| File access | Presigned download URLs generated on-demand (1hr TTL) |
| Folder permissions | Role-based: admin (all), editor (CRUD in assigned folders), viewer (read-only) |
| Content validation | Server-side MIME check + file size limits + optional virus scan |
| Audit trail | All mutations logged with actor + timestamp |

---

## 12. Integration with Existing KB System

The portal is a **parallel ingestion path** alongside the existing AEM pipeline:

```
                    ┌──────────────────┐
                    │  Bedrock KB (S3) │
                    └────────▲─────────┘
                             │ sync
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────┴──────┐  ┌───┴────┐  ┌─────┴──────────┐
    │ AEM Pipeline   │  │ Portal │  │ Future Sources  │
    │ (automated)    │  │ (manual│  │ (API, webhook)  │
    │                │  │ upload)│  │                 │
    └────────────────┘  └────────┘  └────────────────┘
```

- Portal files can optionally be **linked** to `kb_files` records via `portal_files.kb_file_id`.
- The sidecar format is identical, so Bedrock KB treats portal uploads the same as pipeline-generated files.
- A "Publish to KB" action creates the corresponding `Source` + `KBFile` records for full system integration.

---

## 13. Implementation Phases

### Phase 1: Foundation (2-3 weeks)

- [ ] Database schema: `portal_folders`, `portal_files`, `portal_file_versions`
- [ ] Alembic migration
- [ ] Folder CRUD API endpoints
- [ ] Presigned URL upload flow (initiate → confirm)
- [ ] Basic file listing and detail endpoints

### Phase 2: Enrichment Pipeline (2 weeks)

- [ ] Text extraction service (PDF, DOCX, XLSX, MD)
- [ ] Async enrichment worker (reuse `MetadataEnricher` agent)
- [ ] Sidecar generation and upload
- [ ] Enrichment status tracking + SSE progress events
- [ ] KB sync trigger on enrichment complete

### Phase 3: Frontend — Explorer UI (3 weeks)

- [ ] Folder tree component with expand/collapse
- [ ] File grid/list view with sorting and filtering
- [ ] Drag-and-drop upload with progress
- [ ] File detail panel with metadata editing
- [ ] Breadcrumb navigation
- [ ] Search with facets (tags, category, date range)

### Phase 4: Versioning & Bulk Operations (1-2 weeks)

- [ ] Version detection on re-upload
- [ ] Version history UI + restore action
- [ ] Multi-select + bulk move/delete/tag
- [ ] Bulk download (ZIP assembly)

### Phase 5: Polish & Integration (1 week)

- [ ] "Publish to KB" workflow (link to existing system)
- [ ] Permission model (folder-level roles)
- [ ] Audit log UI
- [ ] Performance optimization (pagination, virtual scrolling for large folders)

---

## 14. Technology Choices

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend API | FastAPI (Python) | Consistent with existing KB Manager |
| Database | PostgreSQL | Already in use; supports recursive CTEs, GIN indexes, JSONB |
| Object Storage | AWS S3 | Already the storage backend; presigned URLs native |
| Async Tasks | Background workers (existing queue pattern) or Celery | Enrichment is async; reuse existing `queue_items` pattern |
| Text Extraction | `pdfplumber`, `python-docx`, `openpyxl` | Lightweight, no external service dependency |
| Metadata Enrichment | Bedrock (Haiku) via existing `MetadataEnricher` | Already proven in the system |
| Frontend | React + TypeScript | Industry standard for document management UIs |
| File Tree UI | `react-arborist` or custom | Performant virtualized tree |
| Upload UI | `react-dropzone` + custom progress | Proven drag-and-drop library |

---

## 15. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Large file uploads timing out | Failed uploads, poor UX | Multipart upload for >100MB; retry with resume |
| Enrichment pipeline backlog | Stale metadata, user confusion | Priority queue; show "enriching…" status clearly |
| Folder rename cascading S3 copies | Slow, expensive for deep trees | Async batch job with dual-pointer window; show progress; verify checksums before deleting originals |
| S3 eventual consistency on listing | Stale file lists after upload | DB is source of truth for listings; S3 mirrors the structure for direct access and DR |
| Permission model complexity | Scope creep | Start with simple admin/editor/viewer; iterate |

---

## 16. References

- [AWS: Integrating custom metadata with Amazon S3 Metadata](https://aws.amazon.com/blogs/storage/integrating-custom-metadata-with-amazon-s3-metadata/) — S3 metadata table patterns
- [AWS: Securing presigned URLs for serverless applications](https://aws.amazon.com/blogs/compute/securing-amazon-s3-presigned-urls-for-serverless-applications/) — presigned URL security best practices
- [AWS: Enhanced Document Search Using Content and Metadata Enrichment](https://aws.amazon.com/solutions/guidance/enhanced-document-search-using-content-and-metadata-enrichment-on-aws/) — metadata enrichment architecture on AWS
- [Microsoft: Document management in SharePoint Server](https://learn.microsoft.com/en-us/sharepoint/governance/document-management-in-sharepoint-server) — lifecycle management patterns
- [SharePoint Document Management Best Practices](https://www.tsinfotechnologies.com/sharepoint-document-management-best-practices/) — flat architecture with smart metadata
- [How to Design a Metadata Extraction Pipeline (2026)](https://about.fast.io/resources/metadata-extraction-pipeline-architecture-design/) — queue topology and worker routing
- [System Design Patterns for Handling Large Blobs](https://www.gyanblog.com/software-design/system-design-patterns-handling-large-blobs/) — presigned uploads, chunked uploads, async processing

Content was rephrased for compliance with licensing restrictions.
