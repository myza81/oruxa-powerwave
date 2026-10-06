"""DEC-167 -- `resolve_requirement()`: a Reference's unit, representation and
phase evaluation become the Measurement requirement. Nothing here is a
default: RMS is required because the representation is an RMS
representation; a per-unit base because the unit is `pu`."""

from __future__ import annotations

import pytest

from app.domain.assessment_definition import AssessmentDefinition
from app.domain.compliance_requirement import RMS_REPRESENTATIONS, resolve_requirement


def _req(representation, treatment, member=None, unit="pu"):
    return resolve_requirement(
        AssessmentDefinition(representation=representation, phase_treatment=treatment, member=member), unit,
    )


class TestPerUnitIsRequiredOnlyForPu:
    @pytest.mark.parametrize("unit,expected", [("pu", True), ("kV", False), ("V", False)])
    def test_unit(self, unit, expected):
        assert _req("line_line_rms", "each_phase", unit=unit).requires_per_unit is expected


class TestRmsIsRequiredOnlyForRmsRepresentations:
    @pytest.mark.parametrize("representation", sorted(RMS_REPRESENTATIONS))
    def test_rms_representations_require_rms(self, representation):
        assert _req(representation, "single", member=None if representation == "positive_sequence_rms" else
                    ("AB" if representation == "line_line_rms" else "A")).requires_rms is True

    def test_a_non_rms_representation_would_not_force_rms(self):
        """The decision comes from the representation set, not a blanket
        True: a future non-RMS representation needs no consumer change."""
        assert "instantaneous" not in RMS_REPRESENTATIONS
        assert "unspecified" not in RMS_REPRESENTATIONS


class TestRequiredMembers:
    @pytest.mark.parametrize("treatment", ["each_phase", "minimum", "maximum"])
    def test_aggregate_treatments_need_the_whole_set(self, treatment):
        assert _req("line_line_rms", treatment).required_members == ("AB", "BC", "CA")
        assert _req("phase_ground_rms", treatment).required_members == ("A", "B", "C")

    def test_single_needs_only_the_named_member(self):
        assert _req("line_line_rms", "single", "BC").required_members == ("BC",)
        assert _req("phase_ground_rms", "single", "C").required_members == ("C",)

    def test_positive_sequence_is_one_quantity(self):
        assert _req("positive_sequence_rms", "single").required_members == ("1",)

    @pytest.mark.parametrize("representation,treatment,member", [
        ("unspecified", "each_phase", None),
        ("line_line_rms", "unspecified", None),
        ("line_line_rms", "single", None),
    ])
    def test_under_specified_reference_is_unresolved_never_guessed(self, representation, treatment, member):
        requirement = _req(representation, treatment, member)
        assert requirement.required_members == ()
        assert requirement.unresolved_reason
