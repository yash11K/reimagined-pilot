"""Unit tests for AEM Pruner — validates Requirements 12.1–12.6."""

import copy

from kb_manager.services.aem_pruner import is_denied_url, prune_aem_json


# ---------------------------------------------------------------------------
# Requirement 12.1 — Drop top-level i18n and dataLayer keys
# ---------------------------------------------------------------------------

def test_drops_top_level_i18n_and_datalayer():
    raw = {
        "i18n": {"greeting": "hello"},
        "dataLayer": {"event": "pageview"},
        "title": "My Page",
    }
    result = prune_aem_json(raw)
    assert "i18n" not in result
    assert "dataLayer" not in result
    assert result["title"] == "My Page"


# ---------------------------------------------------------------------------
# Requirement 12.2 — Drop items keyed with experiencefragment prefix
# ---------------------------------------------------------------------------

def test_drops_experiencefragment_items():
    raw = {
        ":items": {
            "experiencefragment_header": {":type": "some/type", "text": "nav"},
            "content": {":type": "some/content", "text": "real content"},
        },
        ":itemsOrder": ["experiencefragment_header", "content"],
    }
    result = prune_aem_json(raw)
    assert "experiencefragment_header" not in result[":items"]
    assert "content" in result[":items"]


# ---------------------------------------------------------------------------
# Requirement 12.3 — Drop items whose :type ends with noise patterns
# ---------------------------------------------------------------------------

def test_drops_noise_type_items():
    noise_types = [
        "wknd/components/headerNavigation",
        "wknd/components/footerNavigation",
        "wknd/components/footerLegal",
        "wknd/components/header",
        "wknd/components/footer",
        "wknd/components/loginModal",
        "wknd/components/bookingwidget",
        "wknd/components/multiColumnLinks",
    ]
    items = {}
    order = []
    for i, t in enumerate(noise_types):
        key = f"noise_{i}"
        items[key] = {":type": t, "text": "noise"}
        order.append(key)
    items["keeper"] = {":type": "wknd/components/text", "text": "keep me"}
    order.append("keeper")

    raw = {":items": items, ":itemsOrder": order}
    result = prune_aem_json(raw)

    assert len(result[":items"]) == 1
    assert "keeper" in result[":items"]


# ---------------------------------------------------------------------------
# Requirement 12.4 — Clean up :itemsOrder after dropping items
# ---------------------------------------------------------------------------

def test_cleans_items_order():
    raw = {
        ":items": {
            "experiencefragment_nav": {":type": "some/header", "text": "nav"},
            "body": {":type": "some/text", "text": "body"},
        },
        ":itemsOrder": ["experiencefragment_nav", "body"],
    }
    result = prune_aem_json(raw)
    assert result[":itemsOrder"] == ["body"]


# ---------------------------------------------------------------------------
# Requirement 12.5 — URL denylist
# ---------------------------------------------------------------------------

def test_denied_urls():
    denied = [
        "https://example.com/reservation",
        "https://example.com/en/login",
        "https://example.com/account/settings",
        "https://example.com/search?q=test",
        "https://example.com/booking/confirm",
        "https://example.com/checkout",
        "https://example.com/payment/status",
        "https://example.com/registration",
        "https://example.com/reset-password",
    ]
    for url in denied:
        assert is_denied_url(url), f"Expected denied: {url}"


def test_allowed_urls():
    allowed = [
        "https://example.com/about",
        "https://example.com/en/destinations/hawaii",
        "https://example.com/faq",
        "https://example.com/contact",
    ]
    for url in allowed:
        assert not is_denied_url(url), f"Expected allowed: {url}"


# ---------------------------------------------------------------------------
# Requirement 12.6 — Idempotence
# ---------------------------------------------------------------------------

def test_idempotence():
    raw = {
        "i18n": {"k": "v"},
        "dataLayer": {"e": "pv"},
        ":items": {
            "experiencefragment_hdr": {":type": "x/header", "text": "hdr"},
            "content": {
                ":type": "x/text",
                "text": "hello",
                ":items": {
                    "nested_noise": {":type": "y/footer", "data": "f"},
                    "nested_keep": {":type": "y/paragraph", "data": "p"},
                },
                ":itemsOrder": ["nested_noise", "nested_keep"],
            },
        },
        ":itemsOrder": ["experiencefragment_hdr", "content"],
    }
    once = prune_aem_json(raw)
    twice = prune_aem_json(once)
    assert once == twice


# ---------------------------------------------------------------------------
# No mutation of input
# ---------------------------------------------------------------------------

def test_does_not_mutate_input():
    raw = {
        "i18n": {"k": "v"},
        ":items": {
            "experiencefragment_x": {":type": "a/header"},
            "keep": {":type": "a/text", "body": "ok"},
        },
        ":itemsOrder": ["experiencefragment_x", "keep"],
    }
    original = copy.deepcopy(raw)
    prune_aem_json(raw)
    assert raw == original


# ---------------------------------------------------------------------------
# Recursive nested :items pruning
# ---------------------------------------------------------------------------

def test_recursive_nested_pruning():
    raw = {
        ":items": {
            "root_container": {
                ":type": "core/container",
                ":items": {
                    "deep_noise": {":type": "brand/headerNavigation"},
                    "deep_content": {":type": "brand/richtext", "text": "deep"},
                },
                ":itemsOrder": ["deep_noise", "deep_content"],
            },
        },
        ":itemsOrder": ["root_container"],
    }
    result = prune_aem_json(raw)
    container = result[":items"]["root_container"]
    assert "deep_noise" not in container[":items"]
    assert "deep_content" in container[":items"]
    assert container[":itemsOrder"] == ["deep_content"]
