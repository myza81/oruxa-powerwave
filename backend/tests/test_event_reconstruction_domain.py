"""Pure-domain tests for Event Reconstruction (DEC-123/DEC-124/DEC-128):
eligibility, the record-level timing model, reference switching,
interval relationships and the large-gap warning."""

from __future__ import annotations

import itertools
import math
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.event_reconstruction import (
    INTERVAL_TOLERANCE_S,
    REASON_NO_ABSOLUTE_TIME_REFERENCE,
    REASON_TIME_OF_DAY_NOT_SUPPORTED,
    REASON_UNKNOWN_TIME_REFERENCE,
    RELATIONSHIP_FULL_OVERLAP,
    RELATIONSHIP_GAP,
    RELATIONSHIP_PARTIAL_OVERLAP,
    RELATIONSHIP_TOUCHING,
    EventReconstructionDefinition,
    ReconstructionMember,
    classify_interval_relationship,
    correction_valid,
    large_gaps,
    reconstruction_eligibility,
    reconstruction_offset_s,
    recorded_placement_s,
    total_reconstruction_offset_s,
)
from app.domain.time_grouping import (
    TIME_REFERENCE_ELAPSED_ONLY,
    TIME_REFERENCE_RECORDED_ABSOLUTE,
    TIME_REFERENCE_TIME_OF_DAY,
)

T0 = datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc)


class TestEligibility:
    def test_recorded_absolute_is_eligible(self):
        result = reconstruction_eligibility(TIME_REFERENCE_RECORDED_ABSOLUTE)
        assert result.eligible is True
        assert result.reason_code is None
        assert result.reason_message is None

    def test_time_of_day_is_not_supported_in_v1(self):
        result = reconstruction_eligibility(TIME_REFERENCE_TIME_OF_DAY)
        assert result.eligible is False
        assert result.reason_code == REASON_TIME_OF_DAY_NOT_SUPPORTED == "time_of_day_not_supported"
        assert "calendar date" in result.reason_message

    def test_elapsed_only_has_no_absolute_time_reference(self):
        result = reconstruction_eligibility(TIME_REFERENCE_ELAPSED_ONLY)
        assert result.eligible is False
        assert result.reason_code == REASON_NO_ABSOLUTE_TIME_REFERENCE == "no_absolute_time_reference"
        assert "absolute start" in result.reason_message

    def test_unknown_reference_type_is_rejected_explicitly(self):
        result = reconstruction_eligibility("something_else")
        assert result.eligible is False
        assert result.reason_code == REASON_UNKNOWN_TIME_REFERENCE


class TestCorrectionValidity:
    @pytest.mark.parametrize("value", [0.0, 1.0, -2.5, 1e-7, 0.0001234, 86400.0 * 3, 5])
    def test_finite_values_including_sub_millisecond_are_valid(self, value):
        assert correction_valid(value) is True

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1.0", None])
    def test_non_finite_or_non_numeric_values_are_invalid(self, value):
        assert correction_valid(value) is False


class TestTimingModel:
    def test_recorded_placement_is_exact_to_the_microsecond(self):
        record = T0 + timedelta(seconds=10, microseconds=200)
        assert recorded_placement_s(record_origin_start=record, reference_origin_start=T0) == pytest.approx(10.0002, abs=1e-12)
        assert recorded_placement_s(record_origin_start=T0, reference_origin_start=record) == pytest.approx(-10.0002, abs=1e-12)

    def test_naive_local_and_aware_utc_origins_compare_as_instants(self):
        naive_local = datetime(2026, 3, 6, 10, 0, 0)  # Asia/Kuala_Lumpur == 02:00 UTC
        assert recorded_placement_s(record_origin_start=naive_local, reference_origin_start=T0) == 0.0

    def test_offset_composes_placement_and_reference_independent_corrections(self):
        assert reconstruction_offset_s(recorded_placement_s=10.0, correction_s=0.25, reference_correction_s=0.0) == 10.25
        assert reconstruction_offset_s(recorded_placement_s=10.0, correction_s=0.25, reference_correction_s=0.25) == 10.0
        assert reconstruction_offset_s(recorded_placement_s=0.0, correction_s=0.5, reference_correction_s=0.5) == 0.0

    @staticmethod
    def _offsets(origins: dict[str, datetime], corrections: dict[str, float], reference: str) -> dict[str, float]:
        return {
            key: reconstruction_offset_s(
                recorded_placement_s=recorded_placement_s(record_origin_start=origin, reference_origin_start=origins[reference]),
                correction_s=corrections[key],
                reference_correction_s=corrections[reference],
            )
            for key, origin in origins.items()
        }

    def test_owner_example_reference_switch_preserves_alignment(self):
        origins = {"A": T0, "B": T0 + timedelta(milliseconds=100), "C": T0 + timedelta(milliseconds=300)}
        corrections = {"A": 0.0, "B": 0.0, "C": 0.0}
        from_a = self._offsets(origins, corrections, "A")
        from_b = self._offsets(origins, corrections, "B")
        assert from_a == pytest.approx({"A": 0.0, "B": 0.1, "C": 0.3}, abs=1e-12)
        assert from_b == pytest.approx({"A": -0.1, "B": 0.0, "C": 0.2}, abs=1e-12)

    def test_every_reference_gives_the_same_pairwise_alignment(self):
        origins = {
            "A": T0,
            "B": T0 + timedelta(seconds=37, microseconds=401),
            "C": T0 - timedelta(hours=2, microseconds=7),
        }
        corrections = {"A": 0.0123, "B": -0.000_2, "C": 1.5}
        frames = {ref: self._offsets(origins, corrections, ref) for ref in origins}
        for ref, offsets in frames.items():
            assert offsets[ref] == 0.0
            for a, b in itertools.permutations(origins, 2):
                assert offsets[a] - offsets[b] == pytest.approx(frames["A"][a] - frames["A"][b], abs=1e-9)

    def test_definition_helpers_return_new_objects_and_keep_others_unchanged(self):
        members = (
            ReconstructionMember(record_id="m1", source_ids=("m1",), correction_s=0.5),
            ReconstructionMember(record_id="m2", source_ids=("m2",)),
        )
        definition = EventReconstructionDefinition(members=members, reference_record_id="m1")
        corrected = definition.with_correction("m2", -0.25)
        assert definition.member("m2").correction_s == 0.0
        assert corrected.member("m2").correction_s == -0.25
        assert corrected.member("m1").correction_s == 0.5
        switched = corrected.with_reference("m2")
        assert switched.reference_record_id == "m2"
        assert [m.correction_s for m in switched.members] == [0.5, -0.25]
        assert definition.member("missing") is None
        with pytest.raises(FrozenInstanceError):
            definition.reference_record_id = "m2"


    def test_total_offset_adds_within_record_and_record_offsets_once(self):
        assert total_reconstruction_offset_s(within_record_offset_s=0.0, reconstruction_record_offset_s=7200.0004) == 7200.0004
        assert total_reconstruction_offset_s(within_record_offset_s=0.25, reconstruction_record_offset_s=-1.0) == -0.75

    def test_identical_recorded_starts_place_records_at_the_same_offset(self):
        # Two independently imported records with identical timestamps are
        # still two members; they simply share a placement.
        assert recorded_placement_s(record_origin_start=T0, reference_origin_start=T0) == 0.0


class TestIntervalRelationships:
    def test_positive_gap(self):
        result = classify_interval_relationship(0.0, 1.0, 3.5, 4.0)
        assert result.kind == RELATIONSHIP_GAP
        assert result.gap_s == 2.5
        assert result.overlap_s == 0.0

    def test_gap_is_symmetric(self):
        assert classify_interval_relationship(3.5, 4.0, 0.0, 1.0).gap_s == 2.5

    def test_touching_exactly_and_within_tolerance(self):
        assert classify_interval_relationship(0.0, 1.0, 1.0, 2.0).kind == RELATIONSHIP_TOUCHING
        assert classify_interval_relationship(0.0, 1.0, 1.0 + INTERVAL_TOLERANCE_S / 2, 2.0).kind == RELATIONSHIP_TOUCHING
        assert classify_interval_relationship(0.0, 1.0, 1.0 - INTERVAL_TOLERANCE_S / 2, 2.0).kind == RELATIONSHIP_TOUCHING

    def test_partial_overlap(self):
        result = classify_interval_relationship(0.0, 1.0, 0.5, 1.5)
        assert result.kind == RELATIONSHIP_PARTIAL_OVERLAP
        assert result.overlap_s == pytest.approx(0.5)
        assert result.gap_s == 0.0

    def test_full_overlap_is_containment_either_way(self):
        assert classify_interval_relationship(0.0, 10.0, 2.0, 3.0).kind == RELATIONSHIP_FULL_OVERLAP
        assert classify_interval_relationship(2.0, 3.0, 0.0, 10.0).kind == RELATIONSHIP_FULL_OVERLAP
        identical = classify_interval_relationship(1.0, 2.0, 1.0, 2.0)
        assert identical.kind == RELATIONSHIP_FULL_OVERLAP
        assert identical.overlap_s == pytest.approx(1.0)

    def test_containment_tolerates_float_noise_at_the_edges(self):
        assert classify_interval_relationship(0.0, 1.0, 0.1 + 0.2 - 0.3, 1.0).kind == RELATIONSHIP_FULL_OVERLAP


class TestLargeGaps:
    """The threshold is configuration (app.config), so every call here
    passes it explicitly -- the domain has no default of its own."""

    THRESHOLD = 3600.0

    def test_threshold_has_no_domain_default(self):
        with pytest.raises(TypeError):
            large_gaps([("a", 0.0, 1.0)])

    def test_gap_below_threshold_does_not_warn(self):
        assert large_gaps([("a", 0.0, 1.0), ("b", 3600.5, 3601.0)], threshold_s=self.THRESHOLD) == []

    def test_gap_exactly_at_threshold_warns(self):
        [warning] = large_gaps([("a", 0.0, 1.0), ("b", 3601.0, 3602.0)], threshold_s=self.THRESHOLD)
        assert warning.gap_s == 3600.0
        assert warning.threshold_s == self.THRESHOLD
        assert (warning.before_key, warning.after_key) == ("a", "b")

    def test_nominal_threshold_gap_with_float_rounding_still_warns(self):
        assert large_gaps([("a", 0.0, 0.1 + 0.2), ("b", 0.3 + 3600.0 - 1e-12, 3700.0)], threshold_s=self.THRESHOLD)

    def test_gap_above_threshold_warns(self):
        [warning] = large_gaps([("b", 90000.0, 90001.0), ("a", 0.0, 1.0)], threshold_s=self.THRESHOLD)
        assert warning.gap_s == 89999.0
        assert (warning.before_key, warning.after_key) == ("a", "b")

    def test_member_bridged_by_an_overlapping_member_does_not_warn(self):
        intervals = [("a", 0.0, 1.0), ("long", 0.5, 5000.0), ("c", 4000.0, 4001.0)]
        assert large_gaps(intervals, threshold_s=self.THRESHOLD) == []

    def test_gap_is_measured_from_the_latest_covered_end(self):
        intervals = [("a", 0.0, 100.0), ("inside", 10.0, 20.0), ("far", 4000.0, 4001.0)]
        [warning] = large_gaps(intervals, threshold_s=self.THRESHOLD)
        assert warning.before_key == "a"
        assert warning.gap_s == 3900.0

    def test_multiple_gaps_are_all_reported(self):
        intervals = [("a", 0.0, 1.0), ("b", 4000.0, 4001.0), ("c", 9000.0, 9001.0)]
        warnings = large_gaps(intervals, threshold_s=self.THRESHOLD)
        assert [(w.before_key, w.after_key) for w in warnings] == [("a", "b"), ("b", "c")]

    def test_other_thresholds_and_empty_input(self):
        assert large_gaps([], threshold_s=self.THRESHOLD) == []
        assert large_gaps([("a", 0.0, 1.0), ("b", 11.0, 12.0)], threshold_s=10.0)[0].gap_s == 10.0
        assert large_gaps([("a", 0.0, 1.0), ("b", 10.5, 12.0)], threshold_s=10.0) == []
        with pytest.raises(ValueError):
            large_gaps([("a", 0.0, 1.0)], threshold_s=0.0)
