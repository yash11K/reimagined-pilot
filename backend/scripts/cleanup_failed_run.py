"""Clean up stale data left by the crashed scout run from 2026-04-16.

Targets:
  - Job 8d19e839 (failed scout) and its parent source b8615fc1
  - Child sources created during that scout (active sources discovered from
    the protections.model.json page)
  - Queue items left in queued/processing state from that run
  - source_kb_files junction rows referencing any of the above

Usage (from backend/):
    python -m scripts.cleanup_failed_run             # dry-run
    python -m scripts.cleanup_failed_run --apply     # actually clean up
"""

import argparse
import asyncio
import os
import pathlib
import sys

import asyncpg

# Load .env
env = pathlib.Path(__file__).parent.parent / ".env"
for line in env.read_text().splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = line.split("=", 1)[1]
        break

DB = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://").split("?")[0]

# The parent source URL from the failed ingest
PARENT_URL = "https://www.avis.com/en/products-and-services/protections.model.json"

# All child URLs that were being created during the scout
CHILD_URL_PREFIX = "https://www.avis.com/en/products-and-services/protections/"
# Also the sibling discovered source
SIBLING_URL = "https://www.avis.com/en/products-and-services.model.json"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete the stale data")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB, ssl="require")
    try:
        # 1. Find the parent source
        parent = await conn.fetchrow(
            "SELECT id, url, status, is_scouted, is_ingested FROM sources WHERE url = $1",
            PARENT_URL,
        )
        print("=== Parent source ===")
        if parent:
            print(f"  id={parent['id']}  status={parent['status']}  "
                  f"scouted={parent['is_scouted']}  ingested={parent['is_ingested']}")
        else:
            print("  Not found (may have been rolled back)")

        # 2. Find child sources from this scout
        children = await conn.fetch(
            """SELECT id, url, status FROM sources
               WHERE (url LIKE $1 OR url = $2)
                 AND url != $3
               ORDER BY created_at""",
            CHILD_URL_PREFIX + "%", SIBLING_URL, PARENT_URL,
        )
        print(f"\n=== Child/sibling sources ({len(children)}) ===")
        for c in children:
            print(f"  id={c['id']}  status={c['status']:<20}  url={c['url'][:80]}")

        # 3. Find jobs linked to parent source
        jobs = []
        if parent:
            jobs = await conn.fetch(
                "SELECT id, status, error_message FROM ingestion_jobs WHERE source_id = $1",
                parent["id"],
            )
        print(f"\n=== Jobs for parent source ({len(jobs)}) ===")
        for j in jobs:
            print(f"  id={j['id']}  status={j['status']}  error={str(j['error_message'] or '')[:80]}")

        # 4. Find stale queue items
        queue_items = await conn.fetch(
            """SELECT id, url, status FROM queue_items
               WHERE url LIKE $1 AND status IN ('queued', 'processing', 'failed')""",
            CHILD_URL_PREFIX + "%",
        )
        print(f"\n=== Stale queue items ({len(queue_items)}) ===")
        for q in queue_items:
            print(f"  id={q['id']}  status={q['status']}  url={q['url'][:80]}")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to clean up.")
            return 0

        print("\n--- Applying cleanup ---")

        # Delete in FK-safe order
        # a) queue items
        if queue_items:
            qids = [q["id"] for q in queue_items]
            r = await conn.execute(
                "DELETE FROM queue_items WHERE id = ANY($1::uuid[])", qids,
            )
            print(f"  Deleted queue_items: {r}")

        # b) source_kb_files junction for child sources
        all_source_ids = [c["id"] for c in children]
        if parent:
            all_source_ids.append(parent["id"])
        if all_source_ids:
            r = await conn.execute(
                "DELETE FROM source_kb_files WHERE source_id = ANY($1::uuid[])",
                all_source_ids,
            )
            print(f"  Deleted source_kb_files: {r}")

        # c) kb_files for the failed jobs
        if jobs:
            jids = [j["id"] for j in jobs]
            r = await conn.execute(
                "DELETE FROM kb_files WHERE job_id = ANY($1::uuid[])", jids,
            )
            print(f"  Deleted kb_files: {r}")

        # d) ingestion_jobs
        if jobs:
            r = await conn.execute(
                "DELETE FROM ingestion_jobs WHERE id = ANY($1::uuid[])",
                [j["id"] for j in jobs],
            )
            print(f"  Deleted ingestion_jobs: {r}")

        # e) child sources
        if children:
            r = await conn.execute(
                "DELETE FROM sources WHERE id = ANY($1::uuid[])",
                [c["id"] for c in children],
            )
            print(f"  Deleted child sources: {r}")

        # f) parent source
        if parent:
            r = await conn.execute(
                "DELETE FROM sources WHERE id = $1", parent["id"],
            )
            print(f"  Deleted parent source: {r}")

        print("\n🧹 Cleanup complete.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
