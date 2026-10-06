"""DEC-166: the Operating Envelope point <-> segment translation
(`app.domain.reference_envelope`) -- deterministic, lossless where it
claims to be, and strict where order carries meaning. The golden vectors
in `fixtures/reference_envelope_vectors.json` are also replayed by
`browser-tests/reference_envelope_editor.spec.js` against the frontend's
mirror of the same translation, so the two implementations cannot drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.assessment_definition import validate_assessment_definition
from app.domain.reference_envelope import (
    DEFAULT_EVALUATION_START_TIME,
    DEFAULT_TOLERANCE,
    DEFAULT_UNIT,
    REGION_AT_OR_ABOVE_LOWER,
    REGION_AT_OR_BELOW_UPPER,
    REGION_INSIDE_ENVELOPE,
    EnvelopePoint,
    EnvelopePointError,
    compliance_region,
    default_assessment_definition,
    default_windows,
    derive_display_extent,
    points_to_segments,
    segments_to_points,
)
from app.domain.reference_profile import (
    BoundarySegment,
    ReferenceBoundary,
    ReferenceProfile,
    ReferenceProfileMetadata,
    find_boundary_crossing,
    profile_from_json_dict,
    profile_to_json_dict,
    validate_reference_profile,
)

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "reference_envelope_vectors.json").read_text(encoding="utf-8"))


def _pts(rows):
    return [EnvelopePoint(time=t, value=v) for t, v in rows]


def _seg(start_time, end_time, start_value, end_value, segment_type):
    return BoundarySegment(start_time, end_time, start_value, end_value, segment_type)


class TestGoldenPointToSegmentVectors:
    @pytest.mark.parametrize("case", VECTORS["points_to_segments"], ids=lambda c: c["name"])
    def test_vector(self, case):
        points = _pts(case["points"])
        if "error" in case:
            with pytest.raises(EnvelopePointError) as exc:
                points_to_segments(points)
            assert exc.value.reason_code == case["error"]
            assert exc.value.point_index == case.get("error_point_index")
        else:
            segments = points_to_segments(points)
            assert [
                [s.start_time, s.end_time, s.start_value, s.end_value, s.segment_type] for s in segments
            ] == case["segments"]


class TestEdgeInference:
    def test_same_voltage_increasing_time_is_a_constant_segment(self):
        (segment,) = points_to_segments(_pts([(0.0, 0.9), (3.0, 0.9)]))
        assert segment == _seg(0.0, 3.0, 0.9, 0.9, "constant")

    def test_different_voltage_increasing_time_is_a_linear_segment(self):
        (segment,) = points_to_segments(_pts([(0.15, 0.0), (3.0, 0.9)]))
        assert segment == _seg(0.15, 3.0, 0.0, 0.9, "linear")

    def test_vertical_edge_is_the_discontinuity_between_two_segments(self):
        segments = points_to_segments(_pts([(0.0, 0.0), (0.15, 0.0), (0.15, 0.9), (3.0, 0.9)]))
        assert segments == (_seg(0.0, 0.15, 0.0, 0.0, "constant"), _seg(0.15, 3.0, 0.9, 0.9, "constant"))

    def test_translation_is_deterministic(self):
        points = _pts([(-0.2, 1.0), (0.0, 1.0), (0.0, 0.2), (0.5, 0.2), (1.0, 0.9)])
        assert points_to_segments(points) == points_to_segments(list(points))

    def test_input_is_never_sorted(self):
        with pytest.raises(EnvelopePointError) as exc:
            points_to_segments(_pts([(0.0, 0.9), (0.15, 0.9), (0.10, 0.5)]))
        assert exc.value.reason_code == "decreasing_time"

    def test_negative_time_is_accepted(self):
        segments = points_to_segments(_pts([(-0.2, 1.0), (0.0, 1.0), (0.15, 0.0)]))
        assert segments[0].start_time == -0.2

    def test_non_finite_values_are_rejected(self):
        with pytest.raises(EnvelopePointError) as exc:
            points_to_segments(_pts([(0.0, float("nan")), (1.0, 0.9)]))
        assert exc.value.reason_code == "non_finite_value"


class TestRoundTripLosslessness:
    @pytest.mark.parametrize("rows", [
        [(0.0, 0.9), (3.0, 0.9)],
        [(0.0, 0.0), (0.15, 0.0), (0.15, 0.9), (3.0, 0.9)],
        [(-0.2, 1.0), (0.0, 1.0), (0.0, 0.2), (0.5, 0.2), (1.0, 0.9)],
        [(0.0, 0.0), (1.0, 0.5), (2.0, 0.5), (2.0, 0.0), (3.0, 0.0)],
    ])
    def test_points_survive_a_round_trip(self, rows):
        points = tuple(_pts(rows))
        assert segments_to_points(ReferenceBoundary(segments=points_to_segments(points))) == points

    def test_gap_is_not_representable_and_is_never_flattened(self):
        gap = ReferenceBoundary(segments=(_seg(0, 1, 0.9, 0.9, "constant"), _seg(2, 3, 0.9, 0.9, "constant")))
        assert segments_to_points(gap) is None

    def test_linear_segment_with_equal_values_is_not_representable(self):
        """Inference would relabel it `constant`; the stored type must not change silently."""
        assert segments_to_points(ReferenceBoundary(segments=(_seg(0, 1, 0.9, 0.9, "linear"),))) is None

    def test_out_of_order_storage_is_not_representable(self):
        unordered = ReferenceBoundary(segments=(_seg(1, 2, 0.9, 0.9, "constant"), _seg(0, 1, 0.9, 0.9, "constant")))
        assert segments_to_points(unordered) is None

    def test_empty_boundary_is_not_representable(self):
        assert segments_to_points(ReferenceBoundary(segments=())) is None


class TestExtentAndDefaults:
    def test_display_extent_is_the_union_of_both_boundaries(self):
        lower = ReferenceBoundary(segments=(_seg(-0.2, 3.0, 0.9, 0.9, "constant"),))
        upper = ReferenceBoundary(segments=(_seg(0.0, 5.0, 1.1, 1.1, "constant"),))
        assert derive_display_extent(lower, upper) == (-0.2, 5.0)
        assert derive_display_extent(lower, None) == (-0.2, 3.0)
        assert derive_display_extent(None, upper) == (0.0, 5.0)
        assert derive_display_extent(None, None) is None

    def test_default_windows_start_evaluation_at_zero_and_end_with_display(self):
        lower = ReferenceBoundary(segments=(_seg(-0.2, 3.0, 0.9, 0.9, "constant"),))
        assert default_windows(lower, None) == (-0.2, 3.0, 0.0, 3.0)
        assert default_windows(None, None) is None

    def test_new_profile_defaults(self):
        assert DEFAULT_UNIT == "pu"
        assert DEFAULT_EVALUATION_START_TIME == 0.0
        assert DEFAULT_TOLERANCE == 0.0
        definition = default_assessment_definition()
        assert (definition.representation, definition.phase_treatment) == ("line_line_rms", "each_phase")
        assert (definition.measurement_location, definition.provenance) == ("unspecified", "unspecified")
        validate_assessment_definition(definition)  # DEC-166: Line-Line RMS + Each Phase is valid

    def test_compliance_region_follows_the_configured_boundaries(self):
        assert compliance_region(has_lower=True, has_upper=False) == REGION_AT_OR_ABOVE_LOWER
        assert compliance_region(has_lower=False, has_upper=True) == REGION_AT_OR_BELOW_UPPER
        assert compliance_region(has_lower=True, has_upper=True) == REGION_INSIDE_ENVELOPE
        with pytest.raises(ValueError):
            compliance_region(has_lower=False, has_upper=False)


class TestGoldenCrossingVectors:
    @pytest.mark.parametrize("case", VECTORS["crossing"], ids=lambda c: c["name"])
    def test_vector(self, case):
        lower = ReferenceBoundary(segments=points_to_segments(_pts(case["lower"])))
        upper = ReferenceBoundary(segments=points_to_segments(_pts(case["upper"])))
        crossing = find_boundary_crossing(lower, upper)
        assert (crossing is not None) is case["crosses"]
        if case["crosses"]:
            assert crossing.time == case["time"]


class TestSimplifiedProfileEndToEnd:
    """A profile built from points is an ordinary `ReferenceProfile`: it
    validates and survives JSON export/import unchanged."""

    def _profile(self):
        lower = ReferenceBoundary(segments=points_to_segments(_pts([(-0.2, 1.0), (0.0, 1.0), (0.0, 0.0), (0.15, 0.0), (0.15, 0.9), (3.0, 0.9)])))
        upper = ReferenceBoundary(segments=points_to_segments(_pts([(-0.2, 1.1), (3.0, 1.1)])))
        start, end, eval_start, eval_end = default_windows(lower, upper)
        return ReferenceProfile(
            id="env", name="Envelope", category="grid_requirement", assessment_definition=default_assessment_definition(),
            unit=DEFAULT_UNIT, display_start_time=start, display_end_time=end, evaluation_start_time=eval_start,
            evaluation_end_time=eval_end, tolerance=DEFAULT_TOLERANCE, lower_boundary=lower, upper_boundary=upper,
            metadata=ReferenceProfileMetadata(),
        )

    def test_validates(self):
        validate_reference_profile(self._profile())

    def test_json_round_trip_is_lossless_and_stays_point_editable(self):
        profile = self._profile()
        restored = profile_from_json_dict(profile_to_json_dict(profile), profile_id="env")
        assert restored == profile
        assert segments_to_points(restored.lower_boundary) is not None
        assert segments_to_points(restored.upper_boundary) is not None
