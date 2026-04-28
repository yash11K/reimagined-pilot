# AEM Pruner — Deterministic JSON Cleaning & Link Extraction

**File:** `kb_manager/services/aem_pruner.py`

---

## Overview

The AEM Pruner is a collection of pure functions (no side effects, idempotent) that clean AEM model.json responses and extract valid links. It runs before any LLM agent touches the data, ensuring the agents work with clean, focused content.

---

## Function: `prune_aem_json(raw_json)`

Recursively walks the AEM JSON tree and removes noise.

### What Gets Removed

| Category | Examples |
|---|---|
| Noise keys (every level) | `i18n`, `dataLayer` |
| Experience fragments | Items with keys starting with `experiencefragment` |
| Noise component types | Items whose `:type` ends with: `headerNavigation`, `footerNavigation`, `footerLegal`, `header`, `footer`, `loginModal`, `bookingwidget`, `multiColumnLinks` |

### Behaviour
- Walks `:items` recursively at every level
- Checks `:type` suffix against noise list
- Removes matching items and keys in-place
- Returns the pruned tree (same structure, less noise)

---

## Function: `extract_links_deterministic(pruned_json, source_url)`

Walks the entire pruned tree and collects all link-like fields.

### Fields Scanned
Any key containing: `href`, `link`, `url`, `path` (case-insensitive)

### Filters Applied (in order)

1. **Valid URL shape** — Must look like a URL (not anchor text leaked into a URL field)
2. **Not denied** — Path doesn't contain: `/reservation`, `/login`, `/account`, `/search`, `/booking`, `/checkout`, `/payment`, `/registration`, `/reset-password`
3. **Not cross-domain** — Same hostname as source URL
4. **Not self-link** — Not pointing back to the source page
5. **Not ignored** — Not `/en/home`, `/en/home.model.json`, `/`

### Output
A deduplicated list of valid link URLs (strings).

---

## URL Validation Functions

### `is_valid_url_shape(url)`
Rejects strings that look like anchor text accidentally placed in URL fields. Checks for proper URL structure.

### `is_denied_url(url)`
Returns `True` if the URL path contains any denied segment (reservation, login, etc.).

### `is_cross_domain(url, source_url)`
Compares hostnames. Returns `True` if the link points to a different domain.

### `is_self_link(url, source_url)`
Returns `True` if the URL points back to the same page (with or without `.model.json`).

### `is_ignored_url(url)`
Returns `True` for homepage/index URLs that should be skipped entirely.

### `resolve_aem_link(url, source_url)`
Converts relative AEM paths to full fetchable `.model.json` URLs. Handles:
- Relative paths (`/en/products/...` → `https://host/en/products/....model.json`)
- Already-absolute URLs
- Fragment/query stripping

---

## Design Decisions

### Why Deterministic First?
The LLM-based Discovery Agent is powerful but can hallucinate URLs or miss links buried deep in the JSON tree. By extracting links deterministically first, we get a guaranteed ground truth. The Discovery Agent then classifies these known-good links rather than discovering them from scratch.

### Why Pure Functions?
No database access, no HTTP calls, no state. This makes the pruner:
- Fully testable with unit tests
- Safe to call multiple times (idempotent)
- Easy to reason about
- Fast (no I/O)
