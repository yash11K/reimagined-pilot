"""Display-status enum + writer-side mapping helper.

Canonical value lives in `sources.display_status` and is updated by writers
as job/queue state changes. `map_from_job_status` returns the value to set.
"""

DISPLAY_STATUS_VALUES = frozenset({
    "idle",
    "queued",
    "discovering",
    "extracting",
    "qa",
    "failed",
    "needs_review",
})


def map_from_job_status(
    source_status: str | None = None,
    job_status: str | None = None,
    job_progress_pct: int | None = None,
    queue_item_status: str | None = None,
) -> str:
    """Translate current state into a display_status enum value.

    Priority (first match wins):
    1. source.status == "failed"            → "failed"
    2. source.status == "needs_confirmation"→ "needs_review"
    3. queue_item_status == "queued"        → "queued"
    4. job_status == "scouting"             → "discovering"
    5. job_status == "processing" >80%      → "qa"
    6. job_status == "processing"           → "extracting"
    7. otherwise                            → "idle"
    """
    if source_status == "failed":
        return "failed"
    if source_status == "needs_confirmation":
        return "needs_review"
    if queue_item_status == "queued":
        return "queued"
    if job_status == "scouting":
        return "discovering"
    if job_status == "processing":
        if job_progress_pct is not None and job_progress_pct > 80:
            return "qa"
        return "extracting"
    return "idle"


# Back-compat alias for older callers / tests.
compute_display_status = map_from_job_status
