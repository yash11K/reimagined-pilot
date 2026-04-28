# KB Manager v2 — Business Case & Problem Statement

---

## 1. The Company

Avis Budget Group (ABG) operates two major car rental brands — **Avis** and **Budget** — across multiple regions (North America, EMEA, Asia-Pacific). Both brands maintain extensive customer-facing websites built on **Adobe Experience Manager (AEM)**, containing hundreds of pages covering products, services, protections, policies, FAQs, promotions, and regional specifics.

---

## 2. The Problem

### 2.1 Customer Support Is Drowning in Repetitive Questions

Customers and support agents need quick, accurate answers about rental policies, protection plans, refueling options, fees, regional rules, and more. This information exists — scattered across:

- **AEM website pages** — Product pages, policy pages, FAQ sections, regional landing pages. Structured as deeply nested JSON component trees, not easily searchable.
- **Legacy Decagon KB** — A previous knowledge base system containing hundreds of manually curated Q&A articles exported as Excel spreadsheets. No structured metadata, inconsistent formatting, no version control.
- **Manual uploads** — Ad-hoc markdown documents created by internal teams.

The result: information silos. The same question gets answered differently depending on which source a support agent finds first. Content goes stale. New pages are published on the website but never make it into the knowledge base.

### 2.2 AEM Content Is Not KB-Ready

AEM model.json responses are designed for rendering web pages, not for knowledge retrieval. A typical page contains:

- Navigation headers and footers
- Experience fragments (shared UI components)
- Booking widgets, login modals
- i18n translation keys, dataLayer analytics payloads
- Deeply nested component trees mixing content with chrome

Extracting the actual *knowledge* from this structure requires:
1. Stripping away all the noise (headers, footers, nav, booking widgets)
2. Identifying which components carry real content
3. Following links to discover related detail pages
4. Converting structured components into readable articles
5. Classifying content by brand, region, category, and visibility

This is too complex and tedious for manual curation at scale.

### 2.3 No Quality Control or Deduplication

Without automated quality gates:
- Boilerplate pages (cookie banners, empty stubs, index pages) get ingested as "articles"
- The same content gets ingested multiple times from different source pages
- Contradictory information from different sources coexists without flagging
- Outdated content is never superseded when the source page is updated

### 2.4 No Connection to Modern AI Search

The end goal is to power an **AWS Bedrock Knowledge Base** — enabling semantic search and RAG (Retrieval-Augmented Generation) for customer support. But Bedrock KB needs:
- Clean markdown files in S3
- Metadata sidecar files for filtering (by brand, region, category, etc.)
- Regular sync triggers when content changes

There was no pipeline to get content from AEM → clean markdown → S3 → Bedrock KB.

---

## 3. The Solution: KB Manager v2

KB Manager v2 is an **AI-powered content ingestion pipeline** that automates the entire journey from raw AEM content to a production-ready Bedrock Knowledge Base.

### 3.1 Automated Discovery

Point the system at an AEM page URL. It will:
- Fetch and parse the AEM model.json
- Strip away all noise (headers, footers, nav, widgets, analytics)
- Discover all outbound links and classify them:
  - **Certain** content pages → automatically queued for ingestion
  - **Uncertain** links → flagged for human review
  - **Navigation/utility** links → filtered out
- Recursively discover the entire content tree from a single entry point

### 3.2 LLM-Powered Extraction

AI agents (Claude Sonnet) convert raw AEM components into clean, standalone markdown articles. Each article gets:
- A clear title
- Pure markdown content (no HTML, no YAML frontmatter)
- Structured metadata: brand, region, category, visibility, tags
- Source URL traceability

### 3.3 Automated Quality Gates

Every extracted article passes through two AI quality checks:

- **QA Agent** — Is this article worth ingesting? Rejects boilerplate, stubs, gibberish, and navigation-only pages.
- **Uniqueness Agent** — Does this overlap with existing KB content? Flags contradictions for human review, allows complementary content through.

A deterministic **routing matrix** maps the combined verdicts to a file status:
- `approved` → auto-published to S3 and Bedrock KB
- `pending_review` → flagged for human review (conflicting content)
- `rejected` → filtered out (low quality or incomplete metadata)

### 3.4 Content Versioning

When a source page is re-ingested, the system compares the `modify_date` against existing KB files. Unchanged content is skipped (saving LLM costs). Updated content supersedes the old version — the old S3 file is deleted, the new one takes its place.

### 3.5 Legacy Content Migration

The Excel import script (`ingest_excel.py`) migrates the entire legacy Decagon KB into the same system. Each row gets:
- LLM-enriched metadata (title, filename, brand, category, tags)
- The same DB schema as AEM-ingested content
- S3 upload with metadata sidecars

After migration, all content — regardless of origin — lives in one unified knowledge base.

### 3.6 Bedrock KB Integration

Approved articles are uploaded to S3 with metadata sidecar files that enable Bedrock KB to filter search results by:
- Brand (Avis, Budget, or both)
- Region (NAM, EMEA, APAC)
- Category (FAQ, policy, product, service, promotion, help)
- Visibility (public, internal, restricted)
- Tags (free-form descriptive labels)

After upload, the system triggers a Bedrock KB data-source sync so the new content is immediately searchable.

### 3.7 Human-in-the-Loop

The system is not fully autonomous. Humans stay in control:
- **Uncertain links** require confirmation before ingestion
- **Conflicting content** is flagged for review
- Files can be manually approved, rejected, edited, or revalidated
- Real-time SSE streaming shows exactly what the system is doing

---

## 4. Content Sources

| Source | Type | Volume | Ingestion Method |
|---|---|---|---|
| AEM website pages | `aem` | Hundreds of pages across brands/regions | Automated crawl via model.json |
| Legacy Decagon KB | `manual` | ~500+ Q&A articles (Excel export) | Bulk import script with LLM enrichment |
| Manual uploads | `upload` | Ad-hoc markdown files | Direct file upload via API |

---

## 5. Target Brands & Regions

| Brand | Regions |
|---|---|
| Avis | NAM (US, Canada), EMEA (UK, DE, FR, ES, IT, PT, NL), APAC (AU, NZ, JP, KO, ZH) |
| Budget | NAM, EMEA, APAC |
| Avis Budget (shared) | Cross-brand content applicable to both |

---

## 6. Key Business Outcomes

### For Customer Support
- **Faster resolution** — Support agents find accurate, up-to-date answers via semantic search instead of hunting across multiple systems
- **Consistent answers** — One source of truth, deduplicated and quality-checked
- **RAG-powered chat** — Bedrock RetrieveAndGenerate enables natural language Q&A with citations

### For Content Operations
- **Automated ingestion** — No more manual copy-paste from website to KB
- **Continuous freshness** — Re-ingestion detects changes and updates automatically
- **Quality at scale** — AI quality gates catch boilerplate and duplicates that humans miss
- **Full traceability** — Every KB article links back to its source URL(s) and ingestion job

### For Engineering
- **Unified pipeline** — AEM pages, legacy content, and manual uploads all flow through the same system
- **Real-time visibility** — SSE streaming and dashboard stats show pipeline health
- **Resilient processing** — Queue worker with retries, heartbeat, and stale recovery handles failures gracefully
- **Cost efficiency** — Versioning skips unchanged content; Haiku handles classification cheaply; Sonnet is reserved for extraction

---

## 7. Before vs. After

| Aspect | Before (Legacy) | After (KB Manager v2) |
|---|---|---|
| Content discovery | Manual — someone notices a new page | Automated — scout phase crawls and discovers |
| Extraction | Copy-paste from website | LLM-powered, preserves all content verbatim |
| Quality control | None — everything goes in | AI quality gate + uniqueness check |
| Deduplication | None — duplicates accumulate | Uniqueness agent flags overlaps and conflicts |
| Versioning | None — stale content persists | Modify-date comparison, auto-supersede |
| Metadata | Manual tagging (inconsistent) | LLM-derived, structured, consistent |
| Search | Keyword-based | Semantic search + RAG via Bedrock KB |
| Multi-brand/region | Separate systems per brand | Unified pipeline with brand/region filtering |
| Monitoring | None | Real-time SSE streaming + dashboard |
| Failure recovery | Manual re-run | Automatic retry with exponential backoff |
