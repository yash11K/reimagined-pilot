"""QA verdict → file status routing matrix.

Pure function, no side effects. Maps quality and uniqueness verdicts
to a target file status, with a metadata completeness gate.

Quality verdicts:  accepted | rejected
Uniqueness verdicts: unique | overlapping | conflicting
"""

import logging

logger = logging.getLogger(__name__)

# 2×3 verdict matrix: (quality, uniqueness) → status
_ROUTING_MATRIX: dict[tuple[str, str], str] = {
    # accepted quality
    ("accepted", "unique"):       "approved",
    ("accepted", "overlapping"):  "approved",
    ("accepted", "conflicting"):  "pending_review",
    # rejected quality
    ("rejected", "unique"):       "rejected",
    ("rejected", "overlapping"):  "rejected",
    ("rejected", "conflicting"):  "rejected",
}


def route_file(quality: str, uniqueness: str, metadata_complete: bool) -> str:
    """Return the target file status based on QA verdicts and metadata completeness.

    Args:
        quality: One of "accepted", "rejected".
        uniqueness: One of "unique", "overlapping", "conflicting".
        metadata_complete: Whether all required metadata fields are present.

    Returns:
        Target status: "approved", "pending_review", or "rejected".
    """
    if not metadata_complete:
        logger.info(
            "🚦 Routing: metadata incomplete → rejected (quality=%s, uniqueness=%s)",
            quality, uniqueness,
        )
        return "rejected"

    status = _ROUTING_MATRIX.get((quality, uniqueness), "rejected")
    logger.info(
        "🚦 Routing: quality=%s, uniqueness=%s, metadata=✅ → %s",
        quality, uniqueness, status,
    )
    return status
