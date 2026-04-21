"""Cache get/upsert queries for the nav_tree_cache table with TTL check."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.models import NavTreeCache

logger = logging.getLogger(__name__)


async def get_cached_tree(
    db: AsyncSession, root_url: str
) -> NavTreeCache | None:
    """Get a cached nav tree by root_url, only if not expired.

    Returns None if no cache entry exists or if the entry has expired.
    """
    result = await db.execute(
        select(NavTreeCache).where(NavTreeCache.root_url == root_url)
    )
    cache = result.scalar_one_or_none()
    if cache is None:
        logger.debug("🌳 Nav cache MISS for %s (no entry)", root_url)
        return None
    # TTL check: return None if expired
    if cache.expires_at is not None and cache.expires_at <= datetime.now(timezone.utc):
        logger.debug("🌳 Nav cache EXPIRED for %s (expired_at=%s)", root_url, cache.expires_at)
        return None
    logger.debug("🌳 Nav cache HIT for %s", root_url)
    return cache


async def get_cached_tree_no_ttl(
    db: AsyncSession, root_url: str
) -> NavTreeCache | None:
    """Get a cached nav tree by root_url without TTL check."""
    result = await db.execute(
        select(NavTreeCache).where(NavTreeCache.root_url == root_url)
    )
    return result.scalar_one_or_none()


async def upsert_nav_cache(
    db: AsyncSession,
    *,
    root_url: str,
    brand: str | None = None,
    region: str | None = None,
    tree_data: dict,
    fetched_at: datetime,
    expires_at: datetime,
) -> NavTreeCache:
    """Insert or update a nav tree cache entry.

    If a record with the same root_url exists, update it.
    Otherwise, create a new record.
    """
    existing = await get_cached_tree_no_ttl(db, root_url)
    if existing is not None:
        existing.brand = brand
        existing.region = region
        existing.tree_data = tree_data
        existing.fetched_at = fetched_at
        existing.expires_at = expires_at
        await db.flush()
        await db.refresh(existing)
        logger.info("🌳 Nav cache UPDATED for %s (expires=%s)", root_url, expires_at)
        return existing

    cache = NavTreeCache(
        root_url=root_url,
        brand=brand,
        region=region,
        tree_data=tree_data,
        fetched_at=fetched_at,
        expires_at=expires_at,
    )
    db.add(cache)
    await db.flush()
    await db.refresh(cache)
    logger.info("🌳 Nav cache CREATED for %s (expires=%s)", root_url, expires_at)
    return cache


async def get_nav_cache_by_id(
    db: AsyncSession, cache_id: uuid.UUID
) -> NavTreeCache | None:
    """Get a nav tree cache entry by ID."""
    result = await db.execute(
        select(NavTreeCache).where(NavTreeCache.id == cache_id)
    )
    return result.scalar_one_or_none()


async def delete_nav_cache(db: AsyncSession, root_url: str) -> bool:
    """Delete a nav tree cache entry by root_url. Returns True if deleted."""
    existing = await get_cached_tree_no_ttl(db, root_url)
    if existing is None:
        return False
    await db.delete(existing)
    await db.flush()
    return True
