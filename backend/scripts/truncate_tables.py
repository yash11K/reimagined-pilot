"""Truncate all app tables except alembic_version.

Usage (from backend/):
    python -m scripts.truncate_tables
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure we're working from the backend directory for .env resolution
backend_dir = Path(__file__).resolve().parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
import kb_manager.database as db_mod

# FK-safe order: children first, parents last
TABLES_TO_TRUNCATE = [
    "queue_items",
    "content_links",
    "kb_files",
    "ingestion_jobs",
    "sources",
    "nav_tree_cache",
]


async def main() -> None:
    db_mod.init_engine()
    factory = db_mod.async_session_factory
    assert factory is not None, "Engine failed to initialise — check .env"

    async with factory() as session:
        for table in TABLES_TO_TRUNCATE:
            await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
            print(f"✅ Truncated {table}")
        await session.commit()

    await db_mod.dispose_engine()
    print("\n🧹 All tables cleared (alembic_version preserved)")


if __name__ == "__main__":
    asyncio.run(main())
