# KB Manager v2 — Backend Spec

> **Read `specs/shared-contracts.md` FIRST.** This file covers backend-specific implementation: pipeline flow, agent definitions, pruning rules, versioning, S3, and streaming.

---

## 1. Ingestion Pipeline Flow

### AEM Deterministic Pruning Rules
Before any agent sees the JSON, strip known noise. This is code, not an agent call.

**Drop these top-level keys entirely:**
- `i18n` — translation dictionaries (hundreds of UI strings, identical across pages)
- `dataLayer` — analytics/event tracking metadata

**Drop items whose key starts with:**
- `experiencefragment` — site-wide header/footer chrome

**Drop items whose `:type` matches:**
- `*/headerNavigation` — site header nav
- `*/footerNavigation` — footer nav links
- `*/footerLegal` — legal footer
- `*/header` — site header chrome
- `*/footer` — site footer chrome
- `*/loginModal` — login/auth UI
- `*/bookingwidget` — booking form (massive, 200+ lines)
- `*/multiColumnLinks` — columnar link lists (footer-style)

**After dropping items:** clean up corresponding `:itemsOrder` arrays to remove references to dropped items.

**URL denylist patterns** (links matching these are auto-skipped, never stored):
`/reservation`, `/login`, `/account`, `/search`, `/booking`, `/checkout`, `/payment`, `/registration`, `/reset-password`

---

### Web Ingestion (AEM and future web connectors)

```
POST /ingest (connector_type: "aem")
│
├─ Phase 1: SCOUT (status: "scouting")
│  │
│  ├─ Fetch model.json from URL
│  ├─ Deterministic prune (rules above)
│  ├─ Discovery Agent (Haiku): walk pruned JSON → identify components + links
│  ├─ For each link found:
│  │   ├─ Peek: fetch linked page's model.json (lightweight, just structure)
│  │   ├─ Link Triage Agent (Haiku): compare source context vs linked content
│  │   │   → classify as expansion / sibling / navigation / uncertain
│  │   │   → note has_sub_links and sub_link_count
│  │   └─ Store in content_links table
│  ├─ Build scout_summary JSONB
│  ├─ Update job status → "awaiting_confirmation"
│  └─ Stream all events via SSE
│
├─ User reviews Content Map, makes overrides
│
├─ Phase 2: PROCESS (status: "processing", triggered by POST /confirm)
│  │
│  ├─ For the source page:
│  │   ├─ Extractor Agent (Sonnet): convert included components to markdown
│  │   ├─ For each EXPANSION link:
│  │   │   ├─ Fetch linked page
│  │   │   ├─ Extract full content
│  │   │   ├─ MERGE: teaser context (from source card) + full content (from linked page)
│  │   │   │   → produces ONE markdown file with teaser as intro, full content as body
│  │   │   └─ Update content_link status → "ingested"
│  │   ├─ For each SIBLING link:
│  │   │   ├─ Fetch linked page
│  │   │   ├─ Extract as separate markdown file
│  │   │   └─ Update content_link status → "ingested"
│  │   └─ For each remaining source component (not linked to an expansion):
│  │       └─ Extract as separate markdown file
│  │
│  ├─ For each extracted file → QA Agent (Haiku):
│  │   ├─ Quality check: assess semantic quality → verdict + reasoning
│  │   ├─ Metadata gate: verify required fields present
│  │   ├─ Uniqueness check: query KB with file content → verdict + reasoning + similar IDs
│  │   └─ Route based on verdict matrix (see shared-contracts.md §3)
│  │
│  ├─ For auto-approved files → upload to S3
│  ├─ Update job status → "completed"
│  └─ Stream all events via SSE
```

### Upload Ingestion

```
POST /ingest (connector_type: "upload", multipart files)
│
├─ No scouting phase needed
├─ For each file:
│   ├─ Parse content (MD → direct, TXT → direct, PDF → text extraction)
│   ├─ Wrap in markdown + frontmatter
│   ├─ QA Agent: quality + uniqueness
│   └─ Route based on verdict matrix
├─ Update job → "completed"
└─ Stream progress via SSE
```

Upload ingestion skips scouting entirely. Job goes straight from creation to `processing` to `completed`. No Content Map needed.

---

## 2. Agent Definitions

### Discovery Agent
- **Model**: Haiku (us.anthropic.claude-3-5-haiku-20241022-v1:0)
- **Input**: Pruned AEM JSON (after deterministic prune)
- **Output**: List of content components + list of raw links
- **Key prompt instructions**:
  - Walk the ENTIRE JSON tree recursively through `:items` objects
  - For each content node: extract component type, title/headline, a text snippet, and any links (ctaLink, href fields)
  - Preserve text **verbatim** — no paraphrasing or summarization
  - Skip nodes that are purely structural (containers with no text content)
  - For links: capture the URL, anchor/CTA text, and the surrounding card/teaser text as context

### Link Triage Agent
- **Model**: Haiku
- **Input**: For each link — source context (card/teaser text, ~100 words max) + linked page's pruned JSON structure (top-level component list only, not full content)
- **Output**: classification + reason (one line) + has_sub_links (bool) + sub_link_count (int)
- **Key prompt instructions**:
  - If source is a short teaser (<100 words) with "Learn More"/"Read More" CTA and linked page has substantial content → `expansion`
  - If both source and linked page have independent substantial content → `sibling`
  - If linked page is mostly navigation/booking/login/structural → `navigation` (don't store)
  - If unclear → `uncertain` with honest reasoning
  - Count how many internal links the linked page has (sub_link_count)

### Extractor Agent
- **Model**: Sonnet (us.anthropic.claude-sonnet-4-20250514-v1:0)
- **Input**: Content components + steering prompt (if any) + expansion link full content for merging
- **Output**: Markdown files with YAML frontmatter
- **Key prompt instructions**:
  - Preserve ALL original text **verbatim** — no rephrasing, no summarization
  - Preserve ALL hyperlinks as `[text](url)` markdown
  - For expansion merges: use the teaser as a brief intro, then the full linked content as the body
  - Generate YAML frontmatter: `title`, `source_url`, `content_type` (inferred), `region`, `brand`
  - Generate a descriptive `title` if none exists in the content
  - If a steering prompt is provided, follow its guidance on what to focus on or skip

### QA Agent
- **Model**: Haiku
- **Input**: Markdown file content (full text)
- **Output**: quality_verdict + quality_reasoning + uniqueness_verdict + uniqueness_reasoning + similar_file_ids
- **Key prompt instructions**:
  - **Quality assessment** (independent of uniqueness):
    - `good`: substantial content (300+ words), well-structured, coherent, actionable information
    - `acceptable`: has useful content but thin, poorly structured, or partially incomplete
    - `poor`: near-empty, gibberish, pure navigation text, or marketing fluff with no substance
    - Reasoning: 2-3 sentences explaining the verdict
  - **Uniqueness assessment** (independent of quality):
    - Uses tool `query_kb(content_snippet, limit=3)` to find similar docs in Bedrock KB
    - `unique`: no meaningful overlap with existing KB documents
    - `overlapping`: partial overlap — covers similar topic but adds distinct value
    - `duplicate`: near-identical content already exists in KB
    - Reasoning: 2-3 sentences. If overlapping/duplicate, mention which existing docs and why
    - Return IDs of top 3 similar files
  - **Metadata gate** (not a verdict — binary check):
    - Required fields in frontmatter: `title`, `source_url`, `region`, `brand`
    - If missing: return quality_verdict = `poor` with reasoning "Missing required metadata: [fields]"
- **Tool**: `query_kb(content_snippet, limit=3)` → queries Bedrock KB, returns similar documents with IDs and similarity info

---

## 3. Versioning Logic

When ingesting a source URL that already exists:
1. Lookup existing `kb_files` by `source_url`
2. Compare `modify_date` from AEM with existing file's `modify_date`
3. If AEM date is newer → process new version, mark old file status as `superseded` (old stays in DB for audit, removed from S3)
4. If same → skip, no re-processing needed

---

## 4. S3 Key Structure

```
{kb_target}/{brand}/{region}/{namespace}/{filename}
```
Example: `public/avis/nam/protections/loss-damage-waiver.md`

S3 bucket name is a **config-level** setting (environment variable), not stored per-file.

---

## 5. Streaming Architecture

- Use FastAPI's `StreamingResponse` with `text/event-stream` content type
- In-memory event bus per job (StreamManager pattern)
- SSE keepalive: send comment every 15 seconds
- Frontend reconnect: if SSE disconnects, `GET /ingest/{job_id}/content-map` recovers state
- Two separate SSE endpoints per job: `scout-stream` (phase 1) and `progress-stream` (phase 2)

---

## 6. Configuration (Environment Variables)

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATABASE_URL` | Yes | — | `postgresql+asyncpg://...` |
| `AWS_REGION` | No | `us-east-1` | S3 and Bedrock region |
| `S3_BUCKET_NAME` | Yes | — | KB file storage |
| `BEDROCK_MODEL_ID` | No | `us.anthropic.claude-sonnet-4-20250514-v1:0` | Extraction agent |
| `HAIKU_MODEL_ID` | No | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Discovery, triage, QA agents |
| `BEDROCK_KB_ID` | No | — | Bedrock KB for uniqueness checks (empty = disabled) |
| `BEDROCK_MAX_TOKENS` | No | `16000` | Max output tokens per agent call |
| `AEM_REQUEST_TIMEOUT` | No | `30` | HTTP timeout for AEM fetches (seconds) |
| `MAX_CONCURRENT_JOBS` | No | `3` | Concurrent ingestion jobs |
