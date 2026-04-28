# Nav Parser — AEM Navigation Tree Extraction

**File:** `kb_manager/services/nav_parser.py`

---

## Overview

Extracts navigation sections from AEM model.json by searching for specific `:type` suffixes in the nested `:items` tree. Produces a flat list of `NavTreeNode` dicts matching the frontend contract.

---

## Core Function

### `parse_nav_tree(aem_json, base_url) -> list[dict]`

Walks the AEM JSON tree looking for navigation components:
- `headerNavigation`
- `multiColumnLinks`
- `footerLegal`

For each found component, extracts the navigation structure into a flat list of nodes.

### Output: `NavTreeNode`
```python
{
    "label": "Products & Services",
    "path": "/en/products-and-services",
    "url": "https://www.avis.com/en/products-and-services.model.json",
    "children": [
        {
            "label": "Protections",
            "path": "/en/products-and-services/protections",
            "url": "https://...",
            "children": []
        }
    ]
}
```

---

## URL Resolution

### `_resolve_url(path, base_host) -> (url | None, is_external)`

Converts relative AEM paths to full model.json URLs:
- `/en/products` → `https://www.avis.com/en/products.model.json`
- `https://external.com/page` → `(url, is_external=True)`
- `None` or empty → `(None, False)`

---

## Region Detection

Maps locale prefixes to regions:

| Locale | Region |
|---|---|
| `en`, `en-us`, `en-ca`, `fr-ca` | `nam` |
| `en-gb`, `de`, `fr`, `es`, `it`, `pt`, `nl` | `emea` |
| `en-au`, `en-nz`, `ja`, `ko`, `zh` | `apac` |

---

## Caching

Navigation trees are cached in the `nav_tree_cache` table (via `queries/nav_cache.py`). The `GET /api/v1/nav` endpoint checks the cache before parsing, and stores results with a TTL.
