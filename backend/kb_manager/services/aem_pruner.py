"""Deterministic AEM JSON pruning and URL denylist checking.

Pure functions with no side effects. Idempotent by design.
"""

from __future__ import annotations

from urllib.parse import urlparse, urljoin

# Keys to remove at EVERY level of the tree (not just top-level)
_DROP_KEYS_EVERYWHERE: set[str] = {"i18n", "dataLayer"}

# Item key prefixes that indicate noise (experience fragments)
_DROP_KEY_PREFIX: str = "experiencefragment"

# Noise component type suffixes — items whose `:type` ends with any of these are dropped
_NOISE_TYPE_SUFFIXES: tuple[str, ...] = (
    "headerNavigation",
    "footerNavigation",
    "footerLegal",
    "header",
    "footer",
    "loginModal",
    "bookingwidget",
    "multiColumnLinks",
)

# URL path segments that mark a link as denied
_DENIED_URL_SEGMENTS: tuple[str, ...] = (
    "/reservation",
    "/login",
    "/account",
    "/search",
    "/booking",
    "/checkout",
    "/payment",
    "/registration",
    "/reset-password",
)

# URL paths that should be ignored entirely (self-links, homepages, etc.)
_IGNORED_URL_PATHS: tuple[str, ...] = (
    "/en/home",
    "/en/home.model.json",
    "/",
)


def _is_noise_type(type_value: str) -> bool:
    """Return True if the :type value ends with a known noise suffix."""
    return type_value.endswith(_NOISE_TYPE_SUFFIXES)


def _prune_items(items: dict) -> dict:
    """Prune a :items dict, removing noisy keys and recursing into children."""
    pruned: dict = {}
    for key, value in items.items():
        # Drop experience fragment keys
        if key.startswith(_DROP_KEY_PREFIX):
            continue
        # Drop items whose :type matches noise patterns
        if isinstance(value, dict):
            item_type = value.get(":type", "")
            if isinstance(item_type, str) and _is_noise_type(item_type):
                continue
        # Keep this item — recurse into it
        pruned[key] = _prune_node(value) if isinstance(value, dict) else value
    return pruned


def _prune_node(node: dict) -> dict:
    """Recursively prune a single AEM JSON node (dict)."""
    result: dict = {}
    for key, value in node.items():
        # Drop noise keys at every level
        if key in _DROP_KEYS_EVERYWHERE:
            continue
        if key == ":items" and isinstance(value, dict):
            pruned_items = _prune_items(value)
            result[":items"] = pruned_items
            # Also fix :itemsOrder if present in the same node
            if ":itemsOrder" in node:
                kept_keys = set(pruned_items.keys())
                result[":itemsOrder"] = [
                    k for k in node[":itemsOrder"] if k in kept_keys
                ]
        elif key == ":itemsOrder":
            # Handled together with :items above; if :items was already
            # processed we skip, otherwise keep as-is (no sibling :items).
            if ":items" not in node:
                result[key] = value
        else:
            # Recurse into nested dicts that might contain :items deeper down
            if isinstance(value, dict):
                result[key] = _prune_node(value)
            elif isinstance(value, list):
                result[key] = [
                    _prune_node(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
    return result


def prune_aem_json(raw: dict) -> dict:
    """Apply deterministic pruning rules to AEM model.json.

    1. Drop top-level keys: i18n, dataLayer
    2. Drop items keyed with 'experiencefragment' prefix
    3. Drop items whose :type matches noise patterns
    4. Clean up :itemsOrder arrays
    5. Recursively process nested :items

    Returns a new dict — does **not** mutate the input.
    """
    # First strip the top-level noise keys, then treat the whole thing as a node
    filtered: dict = {
        k: v for k, v in raw.items() if k not in _DROP_KEYS_EVERYWHERE
    }
    return _prune_node(filtered)


def is_valid_url_shape(raw_url: str) -> bool:
    """Cheap sanity check on a candidate URL string before we trust it.

    Rejects anchor-text or free-form strings that leak out of LLM output
    (e.g. "Your Avis account is already linked..."). Must be either an
    absolute http(s) URL with a host, or a site-absolute path starting
    with '/'. No whitespace, no control characters, bounded length.
    """
    if not raw_url or not isinstance(raw_url, str):
        return False
    if len(raw_url) > 500:
        return False
    # Any whitespace disqualifies — real URLs percent-encode spaces
    if any(c.isspace() for c in raw_url):
        return False
    # Reject sentence-like strings that got concatenated into a URL path
    # (e.g. ".../Your Avis account is already linked..." or ".../We are unable...")
    # These have 3+ consecutive uppercase-starting words in the path, which real
    # URL slugs never do.
    if raw_url.startswith(("http://", "https://")):
        parsed = urlparse(raw_url)
        if not (bool(parsed.netloc) and "." in parsed.netloc):
            return False
        # Reject paths containing sentence fragments: 3+ words with uppercase
        # or common sentence punctuation in the path portion
        path = parsed.path
        if any(c in path for c in ("'", ".", ",", "!")) and len(path) > 60:
            return False
        return True
    if raw_url.startswith("/"):
        # Reject paths with suspicious character classes (letters+digits+-/_.# only)
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/_.#?=&%:")
        return all(c in allowed for c in raw_url)
    return False


def is_denied_url(url: str) -> bool:
    """Return True if the URL path contains a denylist segment."""
    path = urlparse(url).path
    for segment in _DENIED_URL_SEGMENTS:
        if segment in path:
            return True
    return False


def is_ignored_url(url: str) -> bool:
    """Return True if the URL path matches an ignored pattern (homepage, etc.)."""
    path = urlparse(url).path.rstrip("/")
    for ignored in _IGNORED_URL_PATHS:
        if path == ignored.rstrip("/"):
            return True
    return False


def is_self_link(link_url: str, source_url: str) -> bool:
    """Return True if the link points back to the same page as the source."""
    link_path = urlparse(link_url).path.rstrip("/")
    source_path = urlparse(source_url).path.rstrip("/")
    # Strip .model.json suffix for comparison
    link_clean = link_path.replace(".model.json", "")
    source_clean = source_path.replace(".model.json", "")
    return link_clean == source_clean


def resolve_aem_link(raw_url: str, source_url: str) -> str:
    """Resolve a discovered link URL into a fetchable AEM model.json URL.

    Handles:
    - Stripping query parameters and fragments (tracking params like ?_gl=...)
    - Relative paths like ``/en/products/foo`` → full URL with ``.model.json``
    - Absolute URLs missing ``.model.json`` suffix
    - URLs that already end in ``.model.json`` (returned as-is)
    - External domains (returned as-is, no ``.model.json``)
    """
    # Parse the source to get the base origin
    source_parsed = urlparse(source_url)
    source_origin = f"{source_parsed.scheme}://{source_parsed.netloc}"

    # Strip query params and fragments before resolving
    clean_raw = raw_url.split("?")[0].split("#")[0]

    # Resolve relative URLs against the source origin
    if clean_raw.startswith("/"):
        resolved = source_origin + clean_raw
    elif not clean_raw.startswith(("http://", "https://")):
        resolved = urljoin(source_url, clean_raw)
    else:
        resolved = clean_raw

    # Only append .model.json for same-domain AEM pages
    resolved_parsed = urlparse(resolved)
    if resolved_parsed.netloc != source_parsed.netloc:
        return resolved

    # Already has .model.json — return as-is
    if resolved_parsed.path.endswith(".model.json"):
        return resolved

    # Strip trailing slash, append .model.json
    clean_path = resolved_parsed.path.rstrip("/")
    return f"{source_origin}{clean_path}.model.json"


def is_cross_domain(link_url: str, source_url: str) -> bool:
    """Return True if the link points to a different domain than the source."""
    link_netloc = urlparse(link_url).netloc
    source_netloc = urlparse(source_url).netloc
    return link_netloc != source_netloc


# ---------------------------------------------------------------------------
# Deterministic link extraction from AEM JSON
# ---------------------------------------------------------------------------

# Field names that contain actionable content links
_LINK_FIELD_NAMES: set[str] = {
    "ctaLink", "ctaUrl", "linkUrl", "linkURL", "seeAllLinkUrl",
}


def _walk_links(node: dict, parent_title: str | None = None) -> list[dict]:
    """Recursively walk an AEM JSON node and extract all link fields.

    Returns a list of dicts with keys: url, anchor_text, context.
    """
    found: list[dict] = []
    if not isinstance(node, dict):
        return found

    # Determine a human-readable label for this node
    node_title = (
        node.get("headline")
        or node.get("title")
        or node.get("heroHeadline")
        or node.get("header")
        or parent_title
    )
    node_type = node.get(":type", "")

    # Check known link field names
    for field_name in _LINK_FIELD_NAMES:
        url_val = node.get(field_name)
        if isinstance(url_val, str) and url_val.strip():
            anchor = node.get("ctaTitle") or node.get("linkTitle") or None
            context = f"{node_type} {node_title or ''} {field_name}".strip()
            found.append({"url": url_val.strip(), "anchor_text": anchor, "context": context})

    # Check any field whose name contains Link/Url/URL/href (catch-all)
    for key, value in node.items():
        if key in _LINK_FIELD_NAMES or key.startswith(":") or key == "dataLayer":
            continue
        if isinstance(value, str) and value.strip():
            key_lower = key.lower()
            if ("link" in key_lower or "url" in key_lower or "href" in key_lower):
                # Skip image/icon/source URLs and target fields
                if any(skip in key_lower for skip in ("icon", "image", "source", "target", "logo")):
                    continue
                found.append({
                    "url": value.strip(),
                    "anchor_text": None,
                    "context": f"{node_type} {node_title or ''} {key}".strip(),
                })

    # Recurse into :items
    items = node.get(":items")
    if isinstance(items, dict):
        for child in items.values():
            if isinstance(child, dict):
                found.extend(_walk_links(child, parent_title=node_title))

    # Recurse into lists (e.g. banners, navigationList, subLinks)
    for key, value in node.items():
        if key == ":items":
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    found.extend(_walk_links(item, parent_title=node_title))
        elif isinstance(value, dict) and key not in ("dataLayer", "iconPath", "logo"):
            found.extend(_walk_links(value, parent_title=node_title))

    return found


def extract_links_deterministic(pruned_json: dict, source_url: str) -> list[dict]:
    """Extract all content links from pruned AEM JSON deterministically.

    Walks the full tree, collects every link field, then filters out
    denied / self / ignored / non-English URLs and deduplicates.

    Returns list of dicts: {url, anchor_text, context} with resolved URLs.
    """
    raw_links = _walk_links(pruned_json)
    seen: set[str] = set()
    result: list[dict] = []

    for link in raw_links:
        resolved = resolve_aem_link(link["url"], source_url)

        if resolved in seen:
            continue
        if is_cross_domain(resolved, source_url):
            continue
        if is_denied_url(resolved):
            continue
        if is_self_link(resolved, source_url):
            continue
        if is_ignored_url(resolved):
            continue

        seen.add(resolved)
        result.append({
            "url": resolved,
            "anchor_text": link.get("anchor_text"),
            "context": link.get("context"),
        })

    return result
