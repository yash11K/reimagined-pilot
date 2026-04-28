# Routing Matrix — QA Verdict → File Status

**File:** `kb_manager/services/routing_matrix.py`

---

## Overview

The routing matrix is a pure function that maps QA verdicts to a target file status. No side effects, no database access — just a lookup table with a metadata completeness gate.

---

## Function: `route_file(quality, uniqueness, metadata_complete) -> str`

### Decision Table

| Quality | Uniqueness | Metadata Complete | → Status |
|---|---|---|---|
| `accepted` | `unique` | ✅ | `approved` |
| `accepted` | `overlapping` | ✅ | `approved` |
| `accepted` | `conflicting` | ✅ | `pending_review` |
| `rejected` | `unique` | ✅ | `rejected` |
| `rejected` | `overlapping` | ✅ | `rejected` |
| `rejected` | `conflicting` | ✅ | `rejected` |
| `*` | `*` | ❌ | `rejected` |

### Key Rules

1. **Metadata gate first** — If metadata is incomplete (missing title, source_url, region, or brand), the file is always rejected regardless of QA verdicts.

2. **Quality trumps uniqueness** — A rejected-quality file is always rejected, even if it's unique content.

3. **Conflicting content needs review** — Even if quality is accepted, conflicting content (contradicts existing KB) requires human review.

4. **Overlapping is OK** — Content that overlaps with existing KB but adds value (different angle, more detail) is auto-approved.

---

## Metadata Completeness Check

The pipeline checks these fields before calling `route_file()`:

```python
metadata_complete = all([
    kb_file.title,
    kb_file.source_url,
    kb_file.region,
    kb_file.brand,
])
```

---

## Usage

Called in two places:
1. `Pipeline._process_single_file()` — during initial ingestion
2. `routes/files.py` — during file revalidation and edit
