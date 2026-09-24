"""Domain-level tests for `app.domain.assessment_definition` (Compliance
Slice 4 architecture refinement, DEC-110) -- the AssessmentDefinition
model's own validation matrix and legacy `evaluation_quantity`
migration. Pure, no `ReferenceProfile`/registry/HTTP involved (see
`test_reference_profile_domain.py::TestAssessmentDefinitionValidation
PropagatesToProfileLevel`/`TestV1LegacySchemaMigration` for how this
integrates at the profile boundary)."""

from __future__ import annotations

import pytest

from app.domain.assessment_definition import (
    AssessmentDefinition,
    AssessmentDefinitionValidationError,
    MEMBER_A,
    MEMBER_AB,
    PHASE_TREATMENT_EACH_PHASE,
    PHASE_TREATMENT_MAXIMUM,
    PHASE_TREATMENT_MINIMUM,
    PHASE_TREATMENT_SINGLE,
    PHASE_TREATMENT_UNSPECIFIED,
    REPRESENTATION_LINE_LINE_RMS,
    REPRESENTATION_PHASE_GROUND_RMS,
    REPRESENTATION_POSITIVE_SEQUENCE_RMS,
    REPRESENTATION_UNSPECIFIED,
    assessment_definition_from_dict,
    assessment_definition_from_legacy_quantity,
    assessment_definition_to_dict,
    validate_assessment_definition,
)


class TestValidCombinations:
    """Task section 14's own worked examples, each proven valid."""

    def test_positive_sequence_single_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_POSITIVE_SEQUENCE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE))

    def test_line_line_minimum_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_MINIMUM))

    def test_line_line_maximum_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_MAXIMUM))

    def test_phase_ground_each_phase_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_EACH_PHASE))

    def test_phase_ground_minimum_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_MINIMUM))

    def test_explicit_member_single_line_line_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_AB))

    def test_explicit_member_single_phase_ground_is_valid(self):
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_A))

    def test_fully_unspecified_is_valid(self):
        validate_assessment_definition(AssessmentDefinition())

    def test_unspecified_representation_with_a_phase_treatment_is_valid(self):
        """A requirement may state "minimum phase voltage" without
        saying L-L vs L-N -- representation stays unspecified, the
        treatment hint is still preserved (never forced to guess the
        representation to satisfy some artificial completeness rule)."""
        validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_UNSPECIFIED, phase_treatment=PHASE_TREATMENT_MINIMUM))


class TestInvalidCombinations:
    """Task section 14's own worked invalid examples."""

    def test_line_line_each_phase_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_EACH_PHASE))
        assert exc.value.reason_code == "each_phase_not_supported_for_line_line"

    def test_single_with_no_member_for_line_line_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE))
        assert exc.value.reason_code == "member_required_for_single_treatment"

    def test_single_with_no_member_for_phase_ground_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE))
        assert exc.value.reason_code == "member_required_for_single_treatment"

    def test_minimum_with_specific_member_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_MINIMUM, member=MEMBER_A))
        assert exc.value.reason_code == "member_not_applicable_for_aggregate_treatment"

    def test_maximum_with_specific_member_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_MAXIMUM, member=MEMBER_AB))
        assert exc.value.reason_code == "member_not_applicable_for_aggregate_treatment"

    def test_each_phase_with_specific_member_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_EACH_PHASE, member=MEMBER_A))
        assert exc.value.reason_code == "member_not_applicable_for_aggregate_treatment"

    def test_positive_sequence_with_a_member_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_POSITIVE_SEQUENCE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_A))
        assert exc.value.reason_code == "member_not_applicable_for_positive_sequence"

    def test_member_without_any_representation_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_UNSPECIFIED, phase_treatment=PHASE_TREATMENT_UNSPECIFIED, member=MEMBER_A))
        assert exc.value.reason_code == "member_requires_specific_representation"

    def test_line_line_member_on_a_phase_ground_representation_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_AB))
        assert exc.value.reason_code == "member_representation_mismatch"

    def test_phase_ground_member_on_a_line_line_representation_is_invalid(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_A))
        assert exc.value.reason_code == "member_representation_mismatch"

    def test_unknown_representation_is_rejected(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation="phase_neutral_peak"))
        assert exc.value.reason_code == "unknown_representation"

    def test_unknown_phase_treatment_is_rejected(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(phase_treatment="average"))
        assert exc.value.reason_code == "unknown_phase_treatment"

    def test_unknown_member_is_rejected(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member="D"))
        assert exc.value.reason_code == "unknown_member"

    def test_unknown_quantity_family_is_rejected(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(quantity_family="current"))
        assert exc.value.reason_code == "unknown_quantity_family"

    def test_unknown_measurement_location_is_rejected(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(measurement_location="substation_bus"))
        assert exc.value.reason_code == "unknown_measurement_location"

    def test_unknown_provenance_is_rejected(self):
        with pytest.raises(AssessmentDefinitionValidationError) as exc:
            validate_assessment_definition(AssessmentDefinition(provenance="verbal_agreement"))
        assert exc.value.reason_code == "unknown_provenance"


class TestLegacyQuantityMigration:
    def test_none_becomes_fully_unspecified(self):
        definition = assessment_definition_from_legacy_quantity(None)
        assert definition == AssessmentDefinition()

    def test_empty_string_becomes_fully_unspecified(self):
        definition = assessment_definition_from_legacy_quantity("")
        assert definition == AssessmentDefinition()

    def test_unmapped_quantity_preserves_the_hint_and_stays_unspecified(self):
        definition = assessment_definition_from_legacy_quantity("some_future_quantity_id")
        assert definition.representation == REPRESENTATION_UNSPECIFIED
        assert definition.phase_treatment == PHASE_TREATMENT_UNSPECIFIED
        assert definition.member is None
        assert definition.legacy_quantity_hint == "some_future_quantity_id"

    def test_mapped_quantity_is_never_a_guess_result_matches_expected_shape(self):
        definition = assessment_definition_from_legacy_quantity("positive_sequence_rms")
        assert definition.representation == REPRESENTATION_POSITIVE_SEQUENCE_RMS
        assert definition.phase_treatment == PHASE_TREATMENT_SINGLE
        assert definition.member is None
        # Every mapped result is itself semantically valid.
        validate_assessment_definition(definition)


class TestDictSerializationRoundTrip:
    def test_to_dict_then_from_dict_round_trips(self):
        original = AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_AB)
        restored = assessment_definition_from_dict(assessment_definition_to_dict(original))
        assert restored == original

    def test_from_dict_defaults_missing_fields_to_unspecified(self):
        restored = assessment_definition_from_dict({})
        assert restored == AssessmentDefinition()

    def test_from_dict_tolerates_non_dict_input(self):
        assert assessment_definition_from_dict(None) == AssessmentDefinition()
        assert assessment_definition_from_dict("not a dict") == AssessmentDefinition()
