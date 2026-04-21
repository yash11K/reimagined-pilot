"""Find and optionally reset orphan sources left behind by crashed jobs.

An "orphan" is a source whose most recent ingestion job is failed (or stuck
in an active status past some threshold), but whose `status` is not one of
the terminal states (ingested / failed / dismissed). These rows block future
retries because the scout phase dedupes on URL and sees the source as
"already tracked".

Usage:
    python scripts/reset_orphan_sources.py             # dry-run, just list
    python scripts/reset_orphan_sources.py --apply     # actually reset them

Reset action: set `status='failed'`, `is_ingested=False`. Does NOT delete.
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


ORPHAN_QUERY = """
SELECT
    s.id              AS source_id,
    substring(s.url, 1, 100) AS url,
    s.status          AS source_status,
    s.is_scouted,
    s.is_ingested,
    j.id              AS job_id,
    j.status          AS job_status,
    substring(j.error_message, 1, 120) AS job_error,
    j.completed_at    AS job_completed_at
FROM sources s
JOIN LATERAL (
    SELECT id, status, error_message, completed_at
    FROM ingestion_jobs
    WHERE source_id = s.id
    ORDER BY started_at DESC
    LIMIT 1
) j ON TRUE
WHERE
    j.status = 'failed'
    AND s.status NOT IN ('failed', 'dismissed', 'ingested')
ORDER BY j.completed_at DESC NULLS LAST
"""


RESET_SQL = """
UPDATE sources
SET status = 'failed', is_ingested = FALSE
WHERE id = ANY($1::uuid[])
"""


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually reset the orphans")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB, ssl="require")
    try:
        rows = await conn.fetch(ORPHAN_QUERY)
        if not rows:
            print("No orphan sources found.")
            return 0

        print(f"Found {len(rows)} orphan source(s) with failed jobs:\n")
        for r in rows:
            print(f"  source={str(r['source_id'])[:8]}  status={r['source_status']:<12}  "
                  f"job={str(r['job_id'])[:8]}  job_status={r['job_status']}")
            print(f"    url={r['url']}")
            if r["job_error"]:
                print(f"    error={r['job_error']}")
            print()

        if not args.apply:
            print("Dry-run only. Re-run with --apply to reset them.")
            return 0

        ids = [r["source_id"] for r in rows]
        result = await conn.execute(RESET_SQL, ids)
        print(f"Reset complete: {result}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
