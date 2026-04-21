"""Retrospective DB dump for seed job 1828530e and its descendants."""
import asyncio, os, sys, pathlib
from uuid import UUID
import asyncpg

# Load .env manually
env = pathlib.Path(__file__).parent.parent / ".env"
for line in env.read_text().splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = line.split("=", 1)[1]
        break

DB = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://").split("?")[0]
SEED_JOB = "1828530e"

async def main():
    conn = await asyncpg.connect(DB, ssl="require")
    try:
        # Resolve seed job full id
        seed = await conn.fetchrow(
            "SELECT id, source_id, status, started_at, completed_at, error_message "
            "FROM ingestion_jobs WHERE id::text LIKE $1", f"{SEED_JOB}%")
        print("=== SEED JOB ===")
        print(dict(seed) if seed else "NOT FOUND")

        seed_src = await conn.fetchrow("SELECT id, url, status, is_scouted, is_ingested, scout_summary IS NOT NULL AS has_summary FROM sources WHERE id=$1", seed["source_id"])
        print("\n=== SEED SOURCE ===")
        print(dict(seed_src))

        # All queue items created in this run window
        print("\n=== QUEUE ITEMS (recent) ===")
        rows = await conn.fetch(
            "SELECT id, substring(url,1,80) AS url, status, job_id, started_at, completed_at, error_message "
            "FROM queue_items WHERE created_at > now() - interval '6 hours' ORDER BY created_at")
        for r in rows:
            print(dict(r))

        # All jobs in window
        print("\n=== INGESTION JOBS (recent) ===")
        jobs = await conn.fetch(
            "SELECT j.id, substring(s.url,1,80) AS url, j.status, j.started_at, j.completed_at, "
            "EXTRACT(EPOCH FROM (j.completed_at - j.started_at))::int AS dur_s, "
            "substring(j.error_message,1,120) AS err "
            "FROM ingestion_jobs j JOIN sources s ON s.id=j.source_id "
            "WHERE j.started_at > now() - interval '6 hours' ORDER BY j.started_at")
        for j in jobs:
            print(dict(j))

        # Sources created in window (spot junk URLs)
        print("\n=== SOURCES CREATED (recent) ===")
        srcs = await conn.fetch(
            "SELECT id, substring(url,1,100) AS url, type, status, is_scouted, is_ingested "
            "FROM sources WHERE created_at > now() - interval '6 hours' ORDER BY created_at")
        for s in srcs:
            print(dict(s))

        # KB files in window
        print("\n=== KB FILES (recent) ===")
        files = await conn.fetch(
            "SELECT id, title, status, quality_verdict, uniqueness_verdict, "
            "length(md_content) AS md_len, s3_key IS NOT NULL AS uploaded, job_id "
            "FROM kb_files WHERE created_at > now() - interval '6 hours' ORDER BY created_at")
        for f in files:
            print(dict(f))

        # Counts summary
        print("\n=== SUMMARY ===")
        summary = await conn.fetchrow("""
          SELECT
            (SELECT count(*) FROM ingestion_jobs WHERE started_at > now() - interval '6 hours') AS jobs,
            (SELECT count(*) FROM ingestion_jobs WHERE started_at > now() - interval '6 hours' AND status='completed') AS jobs_ok,
            (SELECT count(*) FROM ingestion_jobs WHERE started_at > now() - interval '6 hours' AND status='failed') AS jobs_fail,
            (SELECT count(*) FROM sources WHERE created_at > now() - interval '6 hours') AS srcs,
            (SELECT count(*) FROM sources WHERE created_at > now() - interval '6 hours' AND url ~ ' ') AS srcs_with_space,
            (SELECT count(*) FROM kb_files WHERE created_at > now() - interval '6 hours') AS files,
            (SELECT count(*) FROM kb_files WHERE created_at > now() - interval '6 hours' AND status='approved') AS approved,
            (SELECT count(*) FROM kb_files WHERE created_at > now() - interval '6 hours' AND status='pending_review') AS pending,
            (SELECT count(*) FROM kb_files WHERE created_at > now() - interval '6 hours' AND status='rejected') AS rejected,
            (SELECT count(*) FROM queue_items WHERE created_at > now() - interval '6 hours') AS q_items,
            (SELECT count(*) FROM queue_items WHERE created_at > now() - interval '6 hours' AND status='completed') AS q_done
        """)
        print(dict(summary))
    finally:
        await conn.close()

asyncio.run(main())
