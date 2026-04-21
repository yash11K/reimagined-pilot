"""QA verdict → file status routing matrix.

Pure function, no side effects. Maps quality and uniqueness verdicts
to a target file status, with a metadata completeness gate.
"""

import logging

logger = logging.getLogger(__name__)

# 3×3 verdict matrix: (quality, uniqueness) → status
_ROUTING_MATRIX: dict[tuple[str, str], str] = {
    ("good", "unique"): "approved",
    ("good", "overlapping"): "pending_review",
    ("good", "duplicate"): "rejected",
    ("acceptable", "unique"): "pending_review",
    ("acceptable", "overlapping"): "pending_review",
    ("acceptable", "duplicate"): "rejected",
    ("poor", "unique"): "rejected",
    ("poor", "overlapping"): "rejected",
    ("poor", "duplicate"): "rejected",
}


def route_file(quality: str, uniqueness: str, metadata_complete: bool) -> str:
    """Return the target file status based on QA verdicts and metadata completeness.

    Args:
        quality: One of "good", "acceptable", "poor".
        uniqueness: One of "unique", "overlapping", "duplicate".
        metadata_complete: Whether all required metadata fields are present.

    Returns:
        Target status: "approved", "pending_review", or "rejected".
    """
    # Metadata gate: incomplete metadata always rejects
    if not metadata_complete:
        logger.info("🚦 Routing: metadata incomplete → rejected (quality=%s, uniqueness=%s)", quality, uniqueness)
        return "rejected"

    status = _ROUTING_MATRIX.get((quality, uniqueness), "rejected")
    logger.info("🚦 Routing: quality=%s, uniqueness=%s, metadata=✅ → %s", quality, uniqueness, status)
    return status
