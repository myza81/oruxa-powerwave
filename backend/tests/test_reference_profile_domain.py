"""Domain-level tests for Compliance Slice 3's Reference Profile model
(`app.domain.reference_profile`) -- validation, right-continuity/gap
rendering, and the versioned JSON export/import schema. Pure, no
registry/HTTP involved (see `test_reference_profile_service.py`/
`test_reference_profile_api.py` for those layers)."""

from __future__ import annotations

import math

import pytest

from app.domain.reference_profile import (
    BoundarySegment,
    ReferenceBoundary,
    ReferenceProfile,
    ReferenceProfileMetadata,
    ReferenceProfileValidationError,
    SCHEMA_VERSION,
    UnsupportedReferenceProfileSchemaVersionError,
    boundary_to_render_points,
    profile_from_json_dict,
    profile_to_json_dict,
    validate_reference_profile,
)


def _segment(start_time, end_time, start_value, end_value, segment_type="linear") -> BoundarySegment:
    return BoundarySegment(start_time=start_time, end_time=end_time, start_value=start_value, end_value=end_value, segment_type=segment_type)


def _profile(**overrides) -> ReferenceProfile:
    defaults = dict(
        id="p1",
        name="Test Profile",
        category="custom_reference",
        evaluation_quantity="phase_a_lg_rms",
        unit="pu",
        display_start_time=-0.5,
        display_end_time=3.0,
        evaluation_start_time=0.0,
        evaluation_end_time=3.0,
        tolerance=0.0,
        lower_boundary=ReferenceBoundary(segments=(_segment(-0.5, 3.0, 0.9, 0.9, "constant"),)),
        upper_boundary=None,
        metadata=ReferenceProfileMetadata(),
    )
    defaults.update(overrides)
    return ReferenceProfile(**defaults)


class TestValidationHappyPaths:
    def test_lower_only_profile_is_valid(self):
        validate_reference_profile(_profile(upper_boundary=None))

    def test_upper_only_profile_is_valid(self):
        profile = _profile(lower_boundary=None, upper_boundary=ReferenceBoundary(segments=(_segment(-0.5, 3.0, 1.1, 1.1, "constant"),)))
        validate_reference_profile(profile)

    def test_envelope_profile_with_both_boundaries_is_valid(self):
        profile = _profile(upper_boundary=ReferenceBoundary(segments=(_segment(-0.5, 3.0, 1.1, 1.1, "constant"),)))
        validate_reference_profile(profile)

    def test_negative_time_segments_are_allowed(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(_segment(-2.0, -1.0, 0.5, 0.5, "constant"),)))
        validate_reference_profile(profile)

    def test_linear_segment_with_differing_values_is_allowed(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(_segment(0.0, 1.0, 0.2, 0.9, "linear"),)))
        validate_reference_profile(profile)


class TestValidationRejections:
    def test_no_boundary_defined_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(lower_boundary=None, upper_boundary=None))
        assert exc.value.reason_code == "no_boundary_defined"

    def test_non_finite_segment_value_is_rejected(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(_segment(0.0, 1.0, math.nan, 0.9, "linear"),)))
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(profile)
        assert exc.value.reason_code == "non_finite_value"
        assert exc.value.segment_index == 0

    def test_non_finite_display_window_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(display_end_time=math.inf))
        assert exc.value.reason_code == "non_finite_value"
        assert exc.value.field_name == "display_end_time"

    def test_end_time_not_greater_than_start_time_is_rejected(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(_segment(1.0, 1.0, 0.5, 0.5, "constant"),)))
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(profile)
        assert exc.value.reason_code == "invalid_segment_time_range"

    def test_overlapping_segments_within_same_boundary_are_rejected(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(
            _segment(0.0, 1.0, 0.5, 0.5, "constant"),
            _segment(0.5, 1.5, 0.6, 0.6, "constant"),
        )))
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(profile)
        assert exc.value.reason_code == "overlapping_segments"

    def test_adjacent_touching_segments_are_not_an_overlap(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(
            _segment(0.0, 1.0, 0.5, 0.5, "constant"),
            _segment(1.0, 2.0, 0.9, 0.9, "constant"),
        )))
        validate_reference_profile(profile)

    def test_gap_between_segments_is_allowed(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(
            _segment(0.0, 1.0, 0.5, 0.5, "constant"),
            _segment(2.0, 3.0, 0.9, 0.9, "constant"),
        )))
        validate_reference_profile(profile)

    def test_malformed_segment_type_is_rejected(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(_segment(0.0, 1.0, 0.5, 0.5, "exponential"),)))
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(profile)
        assert exc.value.reason_code == "malformed_segment_type"

    def test_constant_segment_with_mismatched_values_is_rejected(self):
        profile = _profile(lower_boundary=ReferenceBoundary(segments=(_segment(0.0, 1.0, 0.2, 0.9, "constant"),)))
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(profile)
        assert exc.value.reason_code == "constant_segment_value_mismatch"

    def test_unknown_category_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(category="malaysia_grid_code"))
        assert exc.value.reason_code == "unknown_category"

    def test_unsupported_unit_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(unit="MW"))
        assert exc.value.reason_code == "unsupported_unit"

    def test_blank_name_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(name="   "))
        assert exc.value.reason_code == "blank_name"

    def test_negative_tolerance_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(tolerance=-0.01))
        assert exc.value.reason_code == "negative_tolerance"

    def test_evaluation_window_end_not_after_start_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(evaluation_start_time=1.0, evaluation_end_time=1.0))
        assert exc.value.reason_code == "invalid_evaluation_window"

    def test_empty_boundary_segments_is_rejected(self):
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(lower_boundary=ReferenceBoundary(segments=())))
        assert exc.value.reason_code == "empty_boundary"


class TestRightContinuityAndGapRendering:
    def test_discontinuity_produces_a_vertical_connector(self):
        # Segment 1: 0.9 constant until t=0.15; segment 2: linear 0.2 -> 0.9
        # from t=0.15 -- a genuine discontinuity at the shared instant.
        boundary = ReferenceBoundary(segments=(
            _segment(-0.5, 0.15, 0.9, 0.9, "constant"),
            _segment(0.15, 3.0, 0.2, 0.9, "linear"),
        ))
        points = boundary_to_render_points(boundary)
        values = [(p.time, p.value) for p in points]
        assert values == [(-0.5, 0.9), (0.15, 0.9), (0.15, 0.2), (3.0, 0.9)]
        # Right-continuity: the ACTIVE value at t=0.15 is the NEW
        # segment's own start_value (0.2), which is exactly the second
        # of the two same-time points above.

    def test_genuine_gap_inserts_a_none_break(self):
        boundary = ReferenceBoundary(segments=(
            _segment(0.0, 1.0, 0.5, 0.5, "constant"),
            _segment(2.0, 3.0, 0.9, 0.9, "constant"),
        ))
        points = boundary_to_render_points(boundary)
        values = [(p.time, p.value) for p in points]
        assert values == [(0.0, 0.5), (1.0, 0.5), (1.0, None), (2.0, 0.9), (3.0, 0.9)]

    def test_continuous_touching_segments_produce_no_visible_artifact(self):
        boundary = ReferenceBoundary(segments=(
            _segment(0.0, 1.0, 0.5, 0.9, "linear"),
            _segment(1.0, 2.0, 0.9, 0.9, "constant"),
        ))
        points = boundary_to_render_points(boundary)
        values = [(p.time, p.value) for p in points]
        assert values == [(0.0, 0.5), (1.0, 0.9), (1.0, 0.9), (2.0, 0.9)]

    def test_out_of_order_segments_are_rendered_in_time_order(self):
        boundary = ReferenceBoundary(segments=(
            _segment(2.0, 3.0, 0.9, 0.9, "constant"),
            _segment(0.0, 1.0, 0.5, 0.5, "constant"),
        ))
        points = boundary_to_render_points(boundary)
        times = [p.time for p in points]
        assert times == sorted(times)

    def test_empty_boundary_renders_no_points(self):
        assert boundary_to_render_points(ReferenceBoundary(segments=())) == []


class TestJsonSchemaRoundTrip:
    def _envelope(self, profile: ReferenceProfile) -> dict:
        return profile_to_json_dict(profile)

    def test_export_then_import_round_trips_structurally(self):
        profile = _profile(id="ignored-on-export")
        envelope = self._envelope(profile)
        assert envelope["schema_version"] == SCHEMA_VERSION
        assert "id" not in envelope["profile"]
        imported = profile_from_json_dict(envelope, profile_id="new-id")
        assert imported.id == "new-id"
        assert imported.name == profile.name
        assert imported.lower_boundary == profile.lower_boundary
        assert imported.upper_boundary == profile.upper_boundary

    def test_import_assigns_the_caller_supplied_id_never_a_file_supplied_one(self):
        envelope = self._envelope(_profile())
        envelope["profile"]["id"] = "attacker-supplied-id"  # ignored -- not even a recognized field
        imported = profile_from_json_dict(envelope, profile_id="caller-id")
        assert imported.id == "caller-id"

    def test_unsupported_schema_version_is_rejected_explicitly(self):
        envelope = self._envelope(_profile())
        envelope["schema_version"] = 999
        with pytest.raises(UnsupportedReferenceProfileSchemaVersionError) as exc:
            profile_from_json_dict(envelope, profile_id="new-id")
        assert exc.value.schema_version == 999

    def test_missing_schema_version_is_rejected_explicitly(self):
        envelope = self._envelope(_profile())
        del envelope["schema_version"]
        with pytest.raises(UnsupportedReferenceProfileSchemaVersionError):
            profile_from_json_dict(envelope, profile_id="new-id")

    def test_malformed_profile_object_is_rejected_never_coerced(self):
        with pytest.raises(ReferenceProfileValidationError):
            profile_from_json_dict({"schema_version": SCHEMA_VERSION, "profile": {"name": "Incomplete"}}, profile_id="new-id")

    def test_imported_profile_still_passes_full_domain_validation(self):
        envelope = self._envelope(_profile())
        envelope["profile"]["tolerance"] = -5.0  # structurally parseable but domain-invalid
        with pytest.raises(ReferenceProfileValidationError) as exc:
            profile_from_json_dict(envelope, profile_id="new-id")
        assert exc.value.reason_code == "negative_tolerance"
