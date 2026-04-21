"""Unit tests for the QA routing matrix."""

import pytest

from kb_manager.services.routing_matrix import route_file


class TestRoutingMatrix:
    """Tests for the 3×3 verdict matrix (Requirements 16.1–16.7)."""

    def test_good_unique_approved(self):
        assert route_file("good", "unique", True) == "approved"

    def test_good_overlapping_pending_review(self):
        assert route_file("good", "overlapping", True) == "pending_review"

    def test_good_duplicate_rejected(self):
        assert route_file("good", "duplicate", True) == "rejected"

    def test_acceptable_unique_pending_review(self):
        assert route_file("acceptable", "unique", True) == "pending_review"

    def test_acceptable_overlapping_pending_review(self):
        assert route_file("acceptable", "overlapping", True) == "pending_review"

    def test_acceptable_duplicate_rejected(self):
        assert route_file("acceptable", "duplicate", True) == "rejected"

    def test_poor_unique_rejected(self):
        assert route_file("poor", "unique", True) == "rejected"

    def test_poor_overlapping_rejected(self):
        assert route_file("poor", "overlapping", True) == "rejected"

    def test_poor_duplicate_rejected(self):
        assert route_file("poor", "duplicate", True) == "rejected"


class TestMetadataGate:
    """Tests for the metadata completeness gate (Requirement 16.8)."""

    @pytest.mark.parametrize(
        "quality,uniqueness",
        [
            ("good", "unique"),
            ("good", "overlapping"),
            ("good", "duplicate"),
            ("acceptable", "unique"),
            ("acceptable", "overlapping"),
            ("acceptable", "duplicate"),
            ("poor", "unique"),
            ("poor", "overlapping"),
            ("poor", "duplicate"),
        ],
    )
    def test_incomplete_metadata_always_rejected(self, quality, uniqueness):
        assert route_file(quality, uniqueness, False) == "rejected"

    def test_metadata_gate_overrides_approved(self):
        """Even good+unique is rejected when metadata is incomplete."""
        assert route_file("good", "unique", False) == "rejected"


class TestUnknownVerdicts:
    """Edge case: unknown verdict values fall back to rejected."""

    def test_unknown_quality_rejected(self):
        assert route_file("unknown", "unique", True) == "rejected"

    def test_unknown_uniqueness_rejected(self):
        assert route_file("good", "unknown", True) == "rejected"

    def test_both_unknown_rejected(self):
        assert route_file("unknown", "unknown", True) == "rejected"
