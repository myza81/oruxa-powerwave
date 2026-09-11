"""Tests for app.domain.analysis_input_resolution (Analysis Guardrail
Slice 2): the pure role-matching resolver -- no registry, no service, no
I/O, no timebase checking (that's the service layer's own job, tested in
test_analysis_input_resolution_service.py).
"""

from __future__ import annotations

from app.domain.analysis_input_resolution import (
    REASON_AMBIGUOUS_CANDIDATES,
    REASON_EMPTY_REQUIREMENT,
    REASON_PHASE_IDENTITY_MISSING,
    REASON_ROLE_MISSING,
    STATUS_AMBIGUOUS,
    STATUS_NEEDS_CONFIGURATION,
    STATUS_NOT_APPLICABLE,
    STATUS_RESOLVED,
    ResolvedCandidate,
    resolve_requirement,
)
from app.domain.analysis_requirements import (
    AnalysisRequirement,
    PHASOR_CURRENT_PHASE_A,
    PHASOR_VOLTAGE_PHASE_A,
    PHASOR_VOLTAGE_THREE_PHASE,
    RoleSpec,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, POWER, VOLTAGE
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C, PHASE_SOURCE_ENGINEER_CONFIRMED, PHASE_UNKNOWN

CTX = "ec-alpha1"


def _candidate(name, engineering_type, phase, unit="V", phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED, kind="source", calc_id=None):
    ref = (
        ChannelRef(kind="source", source_id="src-1", channel_name=name)
        if kind == "source"
        else ChannelRef(kind="calculated", calculated_channel_id=calc_id or name)
    )
    return ResolvedCandidate(channel_ref=ref, engineering_type=engineering_type, phase=phase, phase_source=phase_source, unit=unit)


class TestSinglePhaseResolution:
    def test_alpha1_va_resolves_with_no_bc_present(self):
        candidates = [_candidate("ALPHA1_VA", VOLTAGE, PHASE_A)]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_RESOLVED
        assert result.resolved_roles["Va"].channel_name == "ALPHA1_VA"
        assert result.missing_roles == []
        assert result.ambiguous_roles == {}

    def test_current_phase_a_resolves(self):
        candidates = [_candidate("ALPHA1_IA", CURRENT, PHASE_A, unit="A")]
        result = resolve_requirement(PHASOR_CURRENT_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_RESOLVED
        assert result.resolved_roles["Ia"].channel_name == "ALPHA1_IA"


class TestThreePhaseResolution:
    def test_full_three_phase_resolves(self):
        candidates = [
            _candidate("ALPHA1_VA", VOLTAGE, PHASE_A),
            _candidate("ALPHA1_VB", VOLTAGE, PHASE_B),
            _candidate("ALPHA1_VC", VOLTAGE, PHASE_C),
        ]
        result = resolve_requirement(PHASOR_VOLTAGE_THREE_PHASE, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_RESOLVED
        assert set(result.resolved_roles) == {"Va", "Vb", "Vc"}

    def test_incomplete_three_phase_needs_configuration_with_precise_missing_role(self):
        candidates = [_candidate("ALPHA1_VA", VOLTAGE, PHASE_A), _candidate("ALPHA1_VB", VOLTAGE, PHASE_B)]
        result = resolve_requirement(PHASOR_VOLTAGE_THREE_PHASE, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.missing_roles == ["Vc"]
        assert result.missing_role_reasons["Vc"] == REASON_ROLE_MISSING
        assert "Va" in result.resolved_roles and "Vb" in result.resolved_roles


class TestWrongTypeAndWrongPhase:
    def test_power_channel_never_satisfies_voltage_role(self):
        candidates = [_candidate("ALPHA1_MW", POWER, PHASE_A, unit="MW")]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.missing_roles == ["Va"]
        assert result.missing_role_reasons["Va"] == REASON_ROLE_MISSING

    def test_voltage_phase_b_never_satisfies_va(self):
        candidates = [_candidate("ALPHA1_VB", VOLTAGE, PHASE_B)]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.missing_roles == ["Va"]


class TestUnknownPhaseNeverGuessed:
    def test_unknown_phase_candidate_reports_phase_identity_missing(self):
        candidates = [_candidate("ALPHA1_VA", VOLTAGE, PHASE_UNKNOWN)]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.missing_roles == ["Va"]
        assert result.missing_role_reasons["Va"] == REASON_PHASE_IDENTITY_MISSING
        assert "Va" not in result.resolved_roles


class TestAmbiguity:
    def test_two_voltage_a_candidates_is_ambiguous_never_silently_picked(self):
        candidates = [
            _candidate("ALPHA1_VA_1", VOLTAGE, PHASE_A),
            _candidate("ALPHA1_VA_2", VOLTAGE, PHASE_A),
        ]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_AMBIGUOUS
        assert result.reason_code == REASON_AMBIGUOUS_CANDIDATES
        assert {ref.channel_name for ref in result.ambiguous_roles["Va"]} == {"ALPHA1_VA_1", "ALPHA1_VA_2"}
        assert "Va" not in result.resolved_roles

    def test_raw_and_calculated_both_matching_is_ambiguous(self):
        candidates = [
            _candidate("ALPHA1_VA", VOLTAGE, PHASE_A, kind="source"),
            _candidate("calc-va-est", VOLTAGE, PHASE_A, kind="calculated", calc_id="calc-va-est"),
        ]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_AMBIGUOUS
        kinds = {ref.kind for ref in result.ambiguous_roles["Va"]}
        assert kinds == {"source", "calculated"}


class TestContextIsolation:
    def test_only_candidates_passed_in_are_considered(self):
        """The resolver never searches beyond its own candidate list --
        context-boundary enforcement is the SERVICE's job (only passing
        one context's own members in), proven here by simply observing
        that candidates from a "different context" (never passed to this
        pure function at all) cannot possibly influence the result."""
        candidates = [_candidate("ALPHA1_VA", VOLTAGE, PHASE_A)]  # Bravo1's own Vb/Vc are simply never in this list
        result = resolve_requirement(PHASOR_VOLTAGE_THREE_PHASE, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert set(result.missing_roles) == {"Vb", "Vc"}


class TestNumericalReadiness:
    def test_blank_unit_still_resolves_but_not_numerically_ready(self):
        candidates = [_candidate("ALPHA1_VA", VOLTAGE, PHASE_A, unit="")]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_RESOLVED
        assert result.numerically_ready is False

    def test_known_unit_is_numerically_ready(self):
        candidates = [_candidate("ALPHA1_VA", VOLTAGE, PHASE_A, unit="kV")]
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, candidates, engineering_context_id=CTX)
        assert result.status == STATUS_RESOLVED
        assert result.numerically_ready is True

    def test_not_resolved_is_never_numerically_ready(self):
        result = resolve_requirement(PHASOR_VOLTAGE_PHASE_A, [], engineering_context_id=CTX)
        assert result.numerically_ready is False


class TestNotApplicable:
    def test_empty_requirement_is_not_applicable(self):
        empty = AnalysisRequirement(analysis_kind="phasor", mode="degenerate", required_roles=())
        result = resolve_requirement(empty, [], engineering_context_id=CTX)
        assert result.status == STATUS_NOT_APPLICABLE
        assert result.reason_code == REASON_EMPTY_REQUIREMENT
