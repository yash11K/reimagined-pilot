"""AEM navigation tree parser.

Extracts navigation sections from AEM model.json by searching for
specific :type suffixes in the nested :items tree. Produces a flat
list of NavTreeNode dicts matching the frontend contract.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Locale prefix → region mapping
_LOCALE_REGION_MAP: dict[str, str] = {
    "en": "nam",
    "en-us": "nam",
    "en-ca": "nam",
    "fr-ca": "nam",
    "en-gb": "emea",
    "de": "emea",
    "fr": "emea",
    "es": "emea",
    "it": "emea",
    "pt": "emea",
    "nl": "emea",
    "en-au": "apac",
    "en-nz": "apac",
    "ja": "apac",
    "ko": "apac",
    "zh": "apac",
}


# ------------------------------------------------------------------
# URL resolution
# ------------------------------------------------------------------

def _resolve_url(
    path: str | None, base_host: str,
) -> tuple[str | None, bool]:
    """Convert a relative AEM path to a full model.json URL.

    Returns:
        (model_json_url | None, is_external)
    """
    if not path:
        return None, False

    parsed = urlparse(path)

    # Anchor-only or empty
    if path.startswith("#") or not path.strip():
        return None, False

    # Full URL with a different host → external
    if parsed.scheme and parsed.netloc:
        base_parsed = urlparse(base_host)
        if parsed.netloc != base_parsed.netloc:
            return None, True
        # Same host full URL
        clean = parsed.path.rstrip("/")
        if clean.endswith(".model.json"):
            return f"{base_host}{clean}", False
        return f"{base_host}{clean}.model.json", False

    # Relative path
    clean = path.rstrip("/")
    if clean.endswith(".model.json"):
        return f"{base_host}{clean}", False
    return f"{base_host}{clean}.model.json", False


# ------------------------------------------------------------------
# :type suffix search (recursive DFS)
# ------------------------------------------------------------------

def _find_by_type_suffix(items: dict, suffix: str) -> dict | None:
    """Recursive DFS through :items looking for a :type ending with *suffix*."""
    if not isinstance(items, dict):
        return None
    for _key, val in items.items():
        if not isinstance(val, dict):
            continue
        component_type = val.get(":type", "")
        if isinstance(component_type, str) and component_type.endswith(suffix):
            return val
        nested = val.get(":items", {})
        found = _find_by_type_suffix(nested, suffix)
        if found is not None:
            return found
    return None


# ------------------------------------------------------------------
# Link → NavTreeNode conversion
# ------------------------------------------------------------------

def _link_to_node(
    link: dict, base_host: str, section: str,
) -> dict:
    """Convert a single AEM nav link dict to a NavTreeNode."""
    title = link.get("title", "")
    raw_url = link.get("url") or ""

    model_json_url, is_external = _resolve_url(raw_url, base_host)

    # Build path and full url
    if raw_url.startswith("http"):
        full_url = raw_url
        path = urlparse(raw_url).path
    elif raw_url.startswith("/"):
        full_url = f"{base_host}{raw_url}"
        path = raw_url
    else:
        full_url = ""
        path = ""

    children: list[dict] = []
    for sub in link.get("subLinks") or []:
        children.append(_link_to_node(sub, base_host, section=title))

    return {
        "label": title,
        "path": path,
        "url": full_url,
        "section": section,
        "model_json_url": model_json_url or "",
        "children": children,
    }


# ------------------------------------------------------------------
# Main parse function
# ------------------------------------------------------------------

def parse(model_json: dict, page_url: str) -> list[dict]:
    """Parse AEM model.json into a list of NavTreeNode dicts.

    Extracts navigation from three component types:
    - ``/headerNavigation`` → hamburgerMenu.navigationList,
      hamburgerMenu.vehicleList, and top-level navigationList
    - ``/multiColumnLinks`` → linkList (footer sections)
    - ``/footerLegal`` → termsList

    Args:
        model_json: Raw AEM model.json dict.
        page_url: The URL the JSON was fetched from (for base_host derivation).

    Returns:
        List of NavTreeNode dicts matching the frontend contract.
    """
    parsed_url = urlparse(page_url)
    base_host = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # Infer brand from hostname: strip "www.", take first segment before "."
    hostname = parsed_url.netloc.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    brand = hostname.split(".")[0] if hostname else ""

    # Infer region from first URL path segment
    path_parts = [p for p in parsed_url.path.strip("/").split("/") if p]
    locale = path_parts[0].lower() if path_parts else ""
    region = _LOCALE_REGION_MAP.get(locale, "")

    root_items = model_json.get(":items", {})
    nodes: list[dict] = []

    # --- 1. headerNavigation ---
    header_nav = _find_by_type_suffix(root_items, "/headerNavigation")
    if header_nav:
        # hamburgerMenu has the richest nav (sections with deep subLinks)
        hamburger = header_nav.get("hamburgerMenu", {})
        if isinstance(hamburger, dict):
            for entry in hamburger.get("navigationList", []):
                nodes.append(_link_to_node(entry, base_host, section=""))

            # vehicleList as a "Vehicles" section
            vehicle_list = hamburger.get("vehicleList", [])
            if vehicle_list:
                vehicle_children = []
                for v in vehicle_list:
                    vehicle_children.append(_link_to_node(v, base_host, section="Vehicles"))
                nodes.append({
                    "label": "Vehicles",
                    "path": "",
                    "url": "",
                    "section": "",
                    "model_json_url": "",
                    "children": vehicle_children,
                })

        # Also include top-level navigationList (main header nav)
        top_nav = header_nav.get("navigationList", [])
        if isinstance(top_nav, list):
            for entry in top_nav:
                title = entry.get("title", "")
                # Avoid duplicates — hamburgerMenu often overlaps with top nav
                existing_labels = {n["label"] for n in nodes}
                if title not in existing_labels:
                    nodes.append(_link_to_node(entry, base_host, section=""))

    # --- 2. multiColumnLinks (footer) ---
    mcl = _find_by_type_suffix(root_items, "/multiColumnLinks")
    if mcl:
        link_list = mcl.get("linkList", [])
        if isinstance(link_list, list):
            for group in link_list:
                group_title = group.get("title", "")
                group_children = []
                for lk in group.get("links") or []:
                    group_children.append(_link_to_node(lk, base_host, section=group_title))
                if group_children:
                    nodes.append({
                        "label": group_title,
                        "path": "",
                        "url": "",
                        "section": "Footer",
                        "model_json_url": "",
                        "children": group_children,
                    })

    # --- 3. footerLegal ---
    fl = _find_by_type_suffix(root_items, "/footerLegal")
    if fl:
        terms = fl.get("termsList", [])
        if isinstance(terms, list):
            legal_children = []
            for t in terms:
                legal_children.append(_link_to_node(t, base_host, section="Legal"))
            if legal_children:
                nodes.append({
                    "label": "Legal",
                    "path": "",
                    "url": "",
                    "section": "Footer",
                    "model_json_url": "",
                    "children": legal_children,
                })

    logger.info(
        "Parsed nav tree for %s: brand=%s region=%s nodes=%d",
        page_url, brand, region, len(nodes),
    )
    return nodes
