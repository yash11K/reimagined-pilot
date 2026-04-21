"""Navigation tree route — GET /nav/tree with cache TTL.

Fetches AEM model.json, parses the navigation structure via
``nav_parser.parse()``, caches the result with a 24-hour TTL.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.config import get_settings
from kb_manager.database import get_db
from kb_manager.queries import nav_cache as nav_cache_queries
from kb_manager.services.nav_parser import parse as parse_nav_tree

router = APIRouter()
logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(hours=24)


async def _fetch_and_parse(url: str) -> list[dict]:
    """Fetch AEM model.json via httpx and parse the navigation tree."""
    settings = get_settings()
    logger.info("🌐 Fetching nav tree from %s", url)
    async with httpx.AsyncClient(
        timeout=settings.AEM_REQUEST_TIMEOUT, follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        raw = resp.json()
    tree = parse_nav_tree(raw, url)
    logger.info("🌳 Nav tree parsed — %d top-level nodes from %s", len(tree), url)
    return tree


@router.get("/nav/tree")
async def get_nav_tree(
    url: str = Query(..., description="Root URL of the AEM page model.json"),
    force_refresh: bool = Query(False, description="Bypass cache and fetch fresh"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return the site navigation tree extracted from AEM.

    Response is a ``NavTreeNode[]`` matching the frontend contract.
    Results are cached in the database with a 24-hour TTL.
    """
    logger.info("🌳 GET /nav/tree — url=%s, force_refresh=%s", url, force_refresh)

    if not force_refresh:
        cached = await nav_cache_queries.get_cached_tree(db, url)
        if cached is not None:
            logger.info("🎯 Nav tree cache HIT for %s", url)
            return cached.tree_data
        logger.info("💨 Nav tree cache MISS for %s", url)

    try:
        tree_data = await _fetch_and_parse(url)
    except httpx.HTTPStatusError as exc:
        logger.error("❌ AEM returned %d for %s", exc.response.status_code, url)
        raise HTTPException(
            status_code=502,
            detail=f"AEM returned {exc.response.status_code} for {url}",
        )
    except httpx.RequestError as exc:
        logger.error("❌ Failed to fetch navigation tree from %s: %s", url, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch navigation tree: {exc}",
        )

    now = datetime.now(timezone.utc)
    await nav_cache_queries.upsert_nav_cache(
        db,
        root_url=url,
        tree_data=tree_data,
        fetched_at=now,
        expires_at=now + _CACHE_TTL,
    )
    await db.commit()
    logger.info("💾 Nav tree cached for %s (expires in %s)", url, _CACHE_TTL)

    return tree_data
