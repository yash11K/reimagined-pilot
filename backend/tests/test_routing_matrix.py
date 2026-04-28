"""Tests for the QA verdict → file status routing matrix."""

import pytest

from kb_manager.services.routing_matrix import route_file


class TestAcceptedQuality:
    """Files with accepted quality verdict."""

    def test_accepted_unique_approved(self):
        assert route_file("accepted", "unique", True) == "approved"

    def test_accepted_overlapping_approved(self):
        assert route_file("accepted", "overlapping", True) == "approved"

    def test_accepted_conflicting_pending_review(self):
        assert route_file("accepted", "conflicting", True) == "pending_review"


class TestRejectedQuality:
    """Files with rejected quality verdict are always rejected."""

    def test_rejected_unique_rejected(self):
        assert route_file("rejected", "unique", True) == "rejected"

    def test_rejected_overlapping_rejected(self):
        assert route_file("rejected", "overlapping", True) == "rejected"

    def test_rejected_conflicting_rejected(self):
        assert route_file("rejected", "conflicting", True) == "rejected"


class TestMetadataGate:
    """Incomplete metadata always results in rejection."""

    @pytest.mark.parametrize(
        "quality,uniqueness",
        [
            ("accepted", "unique"),
            ("accepted", "overlapping"),
            ("accepted", "conflicting"),
            ("rejected", "unique"),
            ("rejected", "overlapping"),
            ("rejected", "conflicting"),
        ],
    )
    def test_incomplete_metadata_always_rejected(self, quality, uniqueness):
        assert route_file(quality, uniqueness, False) == "rejected"

    def test_metadata_gate_overrides_approved(self):
        """Even accepted+unique is rejected when metadata is incomplete."""
        assert route_file("accepted", "unique", False) == "rejected"


class TestEdgeCases:
    """Unknown or unexpected verdict values fall through to rejected."""

    def test_unknown_quality_rejected(self):
        assert route_file("unknown", "unique", True) == "rejected"

    def test_unknown_uniqueness_rejected(self):
        assert route_file("accepted", "unknown", True) == "rejected"

    def test_both_unknown_rejected(self):
        assert route_file("unknown", "unknown", True) == "rejected"
