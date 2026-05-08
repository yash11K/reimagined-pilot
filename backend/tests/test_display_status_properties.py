"""Property-based tests for compute_display_status.

Feature: source-detail-backend-enhancements
Uses Hypothesis to validate correctness properties of the display status computation.
"""

from hypothesis import given, settings, strategies as st

from kb_manager.utils.display_status import DISPLAY_STATUS_VALUES, compute_display_status

# --- Strategies for valid input domains ---

# Valid source statuses per the domain model
source_status_st = st.sampled_from(
    ["idle", "ingested", "active", "failed", "needs_confirmation", "needs_review"]
)

# Active job status: None or one of the known job statuses
active_job_status_st = st.sampled_from(
    [None, "scouting", "awaiting_confirmation", "processing"]
)

# Progress percentage: None or 0-100
active_job_progress_pct_st = st.one_of(st.none(), st.integers(min_value=0, max_value=100))

# Queue item status: None or one of the known queue statuses
queue_item_status_st = st.sampled_from(
    [None, "queued", "processing", "completed", "failed"]
)


# --- Property 1: Display status mapping is total and deterministic ---
# Feature: source-detail-backend-enhancements, Property 1: Display status mapping is total and deterministic


@settings(max_examples=200)
@given(
    source_status=source_status_st,
    active_job_status=active_job_status_st,
    active_job_progress_pct=active_job_progress_pct_st,
    queue_item_status=queue_item_status_st,
)
def test_display_status_total_and_deterministic(
    source_status: str,
    active_job_status: str | None,
    active_job_progress_pct: int | None,
    queue_item_status: str | None,
) -> None:
    """**Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9**

    For any valid input combination, compute_display_status must:
    - Return a value in the valid enum set (totality)
    - Return the same value when called with the same inputs (determinism)
    """
    result = compute_display_status(
        source_status, active_job_status, active_job_progress_pct, queue_item_status
    )

    # Totality: result is always in the valid set
    assert result in DISPLAY_STATUS_VALUES, (
        f"Got unexpected display_status '{result}' for inputs: "
        f"source_status={source_status!r}, active_job_status={active_job_status!r}, "
        f"progress_pct={active_job_progress_pct!r}, queue_item_status={queue_item_status!r}"
    )

    # Determinism: calling again with same inputs yields same result
    result2 = compute_display_status(
        source_status, active_job_status, active_job_progress_pct, queue_item_status
    )
    assert result == result2, (
        f"Non-deterministic: first call returned '{result}', second returned '{result2}'"
    )


# --- Property 2: Display status priority ordering ---
# Feature: source-detail-backend-enhancements, Property 2: Display status priority ordering


@settings(max_examples=200)
@given(
    active_job_status=active_job_status_st,
    active_job_progress_pct=active_job_progress_pct_st,
    queue_item_status=queue_item_status_st,
)
def test_display_status_failed_priority(
    active_job_status: str | None,
    active_job_progress_pct: int | None,
    queue_item_status: str | None,
) -> None:
    """**Validates: Requirements 7.8, 7.9**

    When source_status is "failed", display_status must be "failed"
    regardless of active job status or queue item status.
    """
    result = compute_display_status(
        "failed", active_job_status, active_job_progress_pct, queue_item_status
    )
    assert result == "failed", (
        f"Expected 'failed' but got '{result}' with "
        f"active_job_status={active_job_status!r}, "
        f"progress_pct={active_job_progress_pct!r}, "
        f"queue_item_status={queue_item_status!r}"
    )


@settings(max_examples=200)
@given(
    active_job_status=active_job_status_st,
    active_job_progress_pct=active_job_progress_pct_st,
    queue_item_status=queue_item_status_st,
)
def test_display_status_needs_review_priority(
    active_job_status: str | None,
    active_job_progress_pct: int | None,
    queue_item_status: str | None,
) -> None:
    """**Validates: Requirements 7.8, 7.9**

    When source_status is "needs_confirmation", display_status must be "needs_review"
    regardless of active job status or queue item status.
    """
    result = compute_display_status(
        "needs_confirmation", active_job_status, active_job_progress_pct, queue_item_status
    )
    assert result == "needs_review", (
        f"Expected 'needs_review' but got '{result}' with "
        f"active_job_status={active_job_status!r}, "
        f"progress_pct={active_job_progress_pct!r}, "
        f"queue_item_status={queue_item_status!r}"
    )
