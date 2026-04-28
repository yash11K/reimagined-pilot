# Bedrock KB Client — RAG Search & Sync

**File:** `kb_manager/services/bedrock_kb.py`

---

## Overview

Thin wrapper around AWS Bedrock Knowledge Base APIs. Provides three capabilities: vector search (Retrieve), RAG generation (RetrieveAndGenerate), and data-source sync (StartIngestionJob).

---

## Class: `BedrockKBClient`

### Constructor
Reads from settings: `BEDROCK_KB_ID`, `BEDROCK_DS_ID`, `BEDROCK_MODEL_ID`, `AWS_REGION`. Creates two boto3 clients:
- `bedrock-agent-runtime` — for Retrieve and RetrieveAndGenerate
- `bedrock-agent` — for StartIngestionJob (KB sync)

---

## Methods

### `retrieve(query, kb_target?, limit=10) -> list[dict]`
Calls Bedrock Retrieve API. Returns ranked results:
```python
{
    "rank": 1,
    "title": "Refueling Policies",
    "snippet": "When you return your vehicle...",
    "source_url": "https://www.avis.com/en/...",
    "score": 0.87,
    "s3_uri": "s3://bucket/public/avis/nam/..."
}
```

Used by:
- `POST /api/v1/kb/search` — direct search endpoint
- `UniquenessAgent` — tool-use for KB overlap detection

### `retrieve_and_generate(query, kb_target?, session_id?) -> dict`
Calls Bedrock RetrieveAndGenerate API. Returns LLM-generated answer with citations:
```python
{
    "output": "When returning your vehicle, you have several refueling options...",
    "citations": [
        {"title": "...", "source_url": "...", "snippet": "..."}
    ]
}
```

Used by `POST /api/v1/kb/chat` — RAG chat endpoint.

### `start_sync() -> str | None`
Triggers a Bedrock KB data-source ingestion job. Called after files are uploaded to S3 so Bedrock re-indexes the new content.

Returns the `ingestionJobId` or `None` if sync is not configured.

Used by:
- `Pipeline` — after process phase uploads files
- `routes/files.py` — after manual file approval + S3 upload

---

## Configuration

| Setting | Purpose |
|---|---|
| `BEDROCK_KB_ID` | Knowledge Base ID (required for search/chat) |
| `BEDROCK_DS_ID` | Data Source ID (required for sync) |
| `BEDROCK_MODEL_ID` | Foundation model ARN for RAG generation |
| `BEDROCK_MAX_TOKENS` | Max tokens for RAG response |

If `BEDROCK_KB_ID` or `BEDROCK_DS_ID` are not set, the respective operations are no-ops.
