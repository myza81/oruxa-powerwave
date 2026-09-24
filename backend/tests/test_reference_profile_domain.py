"""Domain-level tests for Compliance Slice 3/4's Reference Profile model
(`app.domain.reference_profile`) -- validation, right-continuity/gap
rendering, and the versioned JSON export/import schema (including the
DEC-110 v1 -> v2 `evaluation_quantity` -> `assessment_definition`
migration). Pure, no registry/HTTP involved (see
`test_reference_profile_service.py`/`test_reference_profile_api.py` for
those layers, and `test_assessment_definition.py` for the
AssessmentDefinition model's own dedicated validation/migration
coverage)."""

from __future__ import annotations

import math

import pytest

from app.domain.assessment_definition import AssessmentDefinition
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
        assessment_definition=AssessmentDefinition(),
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


class TestAssessmentDefinitionValidationPropagatesToProfileLevel:
    """DEC-110: `AssessmentDefinition`'s own validation errors surface
    through `validate_reference_profile()` as an ordinary
    `ReferenceProfileValidationError`, with `field_name` prefixed
    `"assessment_definition."` -- one unified error surface at the
    `ReferenceProfile` boundary, even though the two models live in
    separate, mutually-independent domain modules."""

    def test_invalid_assessment_definition_is_rejected_at_profile_level(self):
        definition = AssessmentDefinition(representation="line_line_rms", phase_treatment="each_phase")
        with pytest.raises(ReferenceProfileValidationError) as exc:
            validate_reference_profile(_profile(assessment_definition=definition))
        assert exc.value.reason_code == "each_phase_not_supported_for_line_line"
        assert exc.value.field_name == "assessment_definition.phase_treatment"

    def test_fully_unspecified_assessment_definition_is_valid(self):
        validate_reference_profile(_profile(assessment_definition=AssessmentDefinition()))


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

    def test_schema_version_is_2_by_default(self):
        assert SCHEMA_VERSION == 2

    def test_export_always_writes_v2_with_assessment_definition_object(self):
        profile = _profile(assessment_definition=AssessmentDefinition(representation="positive_sequence_rms", phase_treatment="single"))
        envelope = self._envelope(profile)
        assert envelope["schema_version"] == 2
        assert "evaluation_quantity" not in envelope["profile"]
        assert envelope["profile"]["assessment_definition"]["representation"] == "positive_sequence_rms"

    def test_export_then_import_round_trips_structurally(self):
        profile = _profile(id="ignored-on-export", assessment_definition=AssessmentDefinition(representation="line_line_rms", phase_treatment="minimum"))
        envelope = self._envelope(profile)
        assert "id" not in envelope["profile"]
        imported = profile_from_json_dict(envelope, profile_id="new-id")
        assert imported.id == "new-id"
        assert imported.name == profile.name
        assert imported.assessment_definition == profile.assessment_definition
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


class TestV1LegacySchemaMigration:
    """DEC-110 task section 6/13: a v1 body's own `evaluation_quantity`
    is migrated into an equivalent `AssessmentDefinition`, never lost,
    never silently reinterpreted. v1 remains READABLE (import-only) --
    `profile_to_json_dict()` never writes it (see
    `TestJsonSchemaRoundTrip.test_export_always_writes_v2_with_
    assessment_definition_object`)."""

    def _v1_envelope(self, *, evaluation_quantity: str, **profile_overrides) -> dict:
        profile = {
            "name": "Legacy Profile", "category": "custom_reference", "evaluation_quantity": evaluation_quantity,
            "unit": "pu", "display_start_time": -0.5, "display_end_time": 3.0, "evaluation_start_time": 0.0,
            "evaluation_end_time": 3.0, "tolerance": 0.0,
            "lower_boundary": {"segments": [{"start_time": -0.5, "end_time": 3.0, "start_value": 0.8, "end_value": 0.8, "segment_type": "constant"}]},
            "upper_boundary": None, "metadata": {},
        }
        profile.update(profile_overrides)
        return {"schema_version": 1, "profile": profile}

    @pytest.mark.parametrize("quantity_id,representation,phase_treatment,member", [
        ("phase_a_lg_rms", "phase_ground_rms", "single", "A"),
        ("phase_b_lg_rms", "phase_ground_rms", "single", "B"),
        ("phase_c_lg_rms", "phase_ground_rms", "single", "C"),
        ("phase_ab_ll_rms", "line_line_rms", "single", "AB"),
        ("phase_bc_ll_rms", "line_line_rms", "single", "BC"),
        ("phase_ca_ll_rms", "line_line_rms", "single", "CA"),
        ("min_phase_lg_rms", "phase_ground_rms", "minimum", None),
        ("max_phase_lg_rms", "phase_ground_rms", "maximum", None),
        ("positive_sequence_rms", "positive_sequence_rms", "single", None),
    ])
    def test_every_canonical_v1_quantity_maps_unambiguously(self, quantity_id, representation, phase_treatment, member):
        imported = profile_from_json_dict(self._v1_envelope(evaluation_quantity=quantity_id), profile_id="new-id")
        definition = imported.assessment_definition
        assert definition.representation == representation
        assert definition.phase_treatment == phase_treatment
        assert definition.member == member
        assert definition.legacy_quantity_hint == quantity_id

    def test_unrecognized_legacy_quantity_becomes_unspecified_with_hint_preserved(self):
        imported = profile_from_json_dict(self._v1_envelope(evaluation_quantity="totally_unknown_quantity"), profile_id="new-id")
        definition = imported.assessment_definition
        assert definition.representation == "unspecified"
        assert definition.phase_treatment == "unspecified"
        assert definition.member is None
        assert definition.legacy_quantity_hint == "totally_unknown_quantity"

    def test_v1_body_missing_evaluation_quantity_is_rejected_explicitly(self):
        envelope = self._v1_envelope(evaluation_quantity="phase_a_lg_rms")
        del envelope["profile"]["evaluation_quantity"]
        with pytest.raises(ReferenceProfileValidationError) as exc:
            profile_from_json_dict(envelope, profile_id="new-id")
        assert exc.value.reason_code == "malformed_profile"

    def test_migrated_v1_profile_still_passes_full_domain_validation(self):
        envelope = self._v1_envelope(evaluation_quantity="phase_a_lg_rms", tolerance=-1.0)
        with pytest.raises(ReferenceProfileValidationError) as exc:
            profile_from_json_dict(envelope, profile_id="new-id")
        assert exc.value.reason_code == "negative_tolerance"

    def test_v1_import_then_v2_export_upgrades_the_schema(self):
        imported = profile_from_json_dict(self._v1_envelope(evaluation_quantity="positive_sequence_rms"), profile_id="new-id")
        envelope = profile_to_json_dict(imported)
        assert envelope["schema_version"] == 2
        assert envelope["profile"]["assessment_definition"]["representation"] == "positive_sequence_rms"
        assert envelope["profile"]["assessment_definition"]["legacy_quantity_hint"] == "positive_sequence_rms"


class TestProvenanceMetadataDEC111:
    """DEC-111: a reference requirement may live for years and later be
    revised -- provenance/version metadata lets a profile stay fully
    self-describing about WHICH requirement/revision it represents,
    without Powerwave ever assuming a newer revision replaces an older
    one."""

    def _metadata(self, **overrides) -> ReferenceProfileMetadata:
        defaults = dict(
            jurisdiction="Malaysia", authority="Example Utility", document_title="Example Grid Code",
            document_revision="2025", effective_date="2025-01-01", source_section="Clause 4.2",
            source_page="17", manufacturer="Example OEM",
        )
        defaults.update(overrides)
        return ReferenceProfileMetadata(**defaults)

    def test_provenance_metadata_round_trips_through_export_import(self):
        profile = _profile(metadata=self._metadata())
        envelope = profile_to_json_dict(profile)
        imported = profile_from_json_dict(envelope, profile_id="new-id")
        assert imported.metadata == profile.metadata

    def test_every_provenance_field_is_optional(self):
        # A fully bare metadata object (task's own "do not make all
        # fields mandatory" instruction) is valid on its own.
        validate_reference_profile(_profile(metadata=ReferenceProfileMetadata()))

    def test_two_revisions_of_the_same_jurisdiction_coexist_as_independent_profiles(self):
        """Never assume a new revision replaces an old one -- both are
        simply independent ReferenceProfile objects with their own id
        and their own document_revision metadata."""
        revision_2025 = _profile(id="p-2025", name="Example Grid Code", metadata=self._metadata(document_revision="2025"))
        revision_2027 = _profile(id="p-2027", name="Example Grid Code", metadata=self._metadata(document_revision="2027"))
        validate_reference_profile(revision_2025)
        validate_reference_profile(revision_2027)
        assert revision_2025.id != revision_2027.id
        assert revision_2025.metadata.document_revision != revision_2027.metadata.document_revision
        # Nothing about validating/exporting one profile ever reads or
        # is influenced by the other -- no "latest version" concept
        # exists anywhere in this module.
        envelope_2025 = profile_to_json_dict(revision_2025)
        envelope_2027 = profile_to_json_dict(revision_2027)
        assert envelope_2025["profile"]["metadata"]["document_revision"] == "2025"
        assert envelope_2027["profile"]["metadata"]["document_revision"] == "2027"
