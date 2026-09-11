"""Tests for app.domain.analysis_requirements (Analysis Guardrail
Slice 2): the small, closed set of typed AnalysisRequirement constants.
"""

from __future__ import annotations

from app.domain.analysis_requirements import (
    PHASOR_CURRENT_PHASE_A,
    PHASOR_CURRENT_THREE_PHASE,
    PHASOR_VOLTAGE_PHASE_A,
    PHASOR_VOLTAGE_PHASE_B,
    PHASOR_VOLTAGE_PHASE_C,
    PHASOR_VOLTAGE_THREE_PHASE,
    REPRESENTATION_SAMPLED,
    get_requirement,
    known_requirements,
)
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C


class TestKnownRequirements:
    def test_at_least_eight_representative_requirements(self):
        assert len(known_requirements()) == 8

    def test_all_are_phasor_kind(self):
        assert all(r.analysis_kind == "phasor" for r in known_requirements())


class TestGetRequirement:
    def test_lookup_by_kind_and_mode(self):
        assert get_requirement("phasor", "voltage_phase_a") is PHASOR_VOLTAGE_PHASE_A

    def test_unknown_returns_none(self):
        assert get_requirement("distance", "phase_a") is None
        assert get_requirement("phasor", "nonexistent_mode") is None


class TestSinglePhaseRoleShape:
    def test_voltage_phase_a_requires_exactly_one_role(self):
        assert len(PHASOR_VOLTAGE_PHASE_A.required_roles) == 1
        role = PHASOR_VOLTAGE_PHASE_A.required_roles[0]
        assert role.role_key == "Va"
        assert role.engineering_type == VOLTAGE
        assert role.phase == PHASE_A
        assert role.representation == REPRESENTATION_SAMPLED

    def test_current_phase_a_requires_current_not_voltage(self):
        role = PHASOR_CURRENT_PHASE_A.required_roles[0]
        assert role.engineering_type == CURRENT
        assert role.phase == PHASE_A

    def test_b_and_c_modes_supported(self):
        assert PHASOR_VOLTAGE_PHASE_B.required_roles[0].phase == PHASE_B
        assert PHASOR_VOLTAGE_PHASE_C.required_roles[0].phase == PHASE_C


class TestThreePhaseRoleShape:
    def test_voltage_three_phase_requires_all_three_roles(self):
        roles = PHASOR_VOLTAGE_THREE_PHASE.required_roles
        assert [r.role_key for r in roles] == ["Va", "Vb", "Vc"]
        assert [r.phase for r in roles] == [PHASE_A, PHASE_B, PHASE_C]
        assert all(r.engineering_type == VOLTAGE for r in roles)

    def test_current_three_phase_requires_all_three_roles(self):
        roles = PHASOR_CURRENT_THREE_PHASE.required_roles
        assert [r.role_key for r in roles] == ["Ia", "Ib", "Ic"]
        assert all(r.engineering_type == CURRENT for r in roles)
