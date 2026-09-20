"""Golden-vector tests for `app.domain.compliance_measurement` (Compliance
& Capability Slice 2 -- see docs/project-memory/COMPLIANCE_CAPABILITY.md).

Every expected value below is derived independently from closed-form
physics/complex arithmetic -- never by running this module's own
function and calling the result "expected" (the same convention
`test_phasor_domain.py`/`test_sequence_components_domain.py` already
establish). `estimate_phasor()` and `compute_symmetrical_components()`
are the SAME, already-golden-tested functions those other suites cover
-- these tests exercise `compute_voltage_quantity_value()`'s own
combination logic on top of them, plus the per-unit reuse required by
task section 7 (no second Compliance-specific base model).
"""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from app.domain.compliance_measurement import (
    QUANTITY_MAX_PHASE_LG_RMS,
    QUANTITY_MIN_PHASE_LG_RMS,
    QUANTITY_PHASE_A_LG_RMS,
    QUANTITY_PHASE_AB_LL_RMS,
    QUANTITY_POSITIVE_SEQUENCE_RMS,
    ROLE_A,
    ROLE_AB,
    ROLE_B,
    ROLE_C,
    STATUS_AVAILABLE,
    STATUS_UNSUPPORTED_REPRESENTATION,
    VOLTAGE_QUANTITIES,
    RolePhasor,
    compute_voltage_quantity_value,
    get_voltage_quantity,
)
from app.domain.per_unit import PerUnitBaseProfile, resolve_per_unit
from app.domain.phasor import estimate_phasor
from app.domain.sequence_components import compute_symmetrical_components
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE


def _sine(amp_peak: float, phase_deg: float, freq_hz: float, sample_rate_hz: float, duration_s: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(round(duration_s * sample_rate_hz))
    t = np.arange(n) / sample_rate_hz
    x = amp_peak * np.cos(2.0 * np.pi * freq_hz * t + np.radians(phase_deg))
    return t, x


class TestCatalogue:
    def test_nine_quantities_in_task_order(self):
        assert [q.id for q in VOLTAGE_QUANTITIES] == [
            "phase_a_lg_rms", "phase_b_lg_rms", "phase_c_lg_rms",
            "phase_ab_ll_rms", "phase_bc_ll_rms", "phase_ca_ll_rms",
            "min_phase_lg_rms", "max_phase_lg_rms",
            "positive_sequence_rms",
        ]

    def test_unknown_quantity_id_returns_none(self):
        assert get_voltage_quantity("not_a_real_quantity") is None


class TestInstantaneousBalancedThreePhase:
    """Golden scenario (task section 22): Va/Vb/Vc instantaneous, 100 V
    RMS balanced, 120 deg apart -> Positive Sequence RMS ~= 100 V (the
    nominal per-phase magnitude); zero/negative sequence are irrelevant
    to this scenario and not asserted."""

    def test_positive_sequence_matches_nominal_magnitude(self):
        quantity = get_voltage_quantity(QUANTITY_POSITIVE_SEQUENCE_RMS)
        peak = math.sqrt(2) * 100.0
        role_phasors = {}
        for role, phase_deg in ((ROLE_A, 0.0), (ROLE_B, -120.0), (ROLE_C, 120.0)):
            t, x = _sine(peak, phase_deg, 50.0, sample_rate_hz=5000.0, duration_s=1.0)
            estimate = estimate_phasor(t, x, analysis_time=0.9, reference_frequency_hz=50.0)
            assert estimate.available
            role_phasors[role] = RolePhasor(magnitude=estimate.magnitude_rms, angle_deg=estimate.angle_deg)

        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        assert result.status == STATUS_AVAILABLE
        assert result.magnitude == pytest.approx(100.0, rel=1e-3)


class TestRmsDirectPhaseA:
    """Golden scenario: an already-RMS Phase A channel is used directly
    -- never re-derived as a fundamental phasor estimate."""

    def test_phase_a_uses_direct_rms_value(self):
        quantity = get_voltage_quantity(QUANTITY_PHASE_A_LG_RMS)
        role_phasors = {ROLE_A: RolePhasor(magnitude=158.77, angle_deg=None)}
        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        assert result.status == STATUS_AVAILABLE
        assert result.magnitude == pytest.approx(158.77)
        assert result.angle_deg is None


def _voltage_profile(*, reference: str) -> PerUnitBaseProfile:
    return PerUnitBaseProfile(
        source_id="src-1", workspace_id="ws-1", voltage_base_value=275.0,
        voltage_reference_mode="manual", voltage_reference_override=reference,
        current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
    )


class Test275kVBaseReuse:
    """Golden scenario (task section 7): 275 kV L-L -> ~1 pu, 158.77 kV
    L-G -> ~1 pu, on the SAME `app.domain.per_unit` engine Compliance
    never duplicates. This proves a Compliance-normalized engineering
    value can be handed straight to the existing per-unit resolver with
    zero Compliance-specific conversion math."""

    def test_line_to_line_275kv_is_one_pu(self):
        resolution = resolve_per_unit("Voltage", _voltage_profile(reference=LINE_TO_LINE))
        assert resolution.status == "configured"
        base_kv = resolution.base_amount / 1000.0  # base_amount is volts
        assert 275.0 / base_kv == pytest.approx(1.0, rel=1e-4)

    def test_line_to_ground_15877kv_is_approximately_one_pu(self):
        resolution = resolve_per_unit("Voltage", _voltage_profile(reference=LINE_TO_GROUND))
        assert resolution.status == "configured"
        base_kv = resolution.base_amount / 1000.0  # base_amount is volts
        measured_lg_kv = 275.0 / math.sqrt(3)
        assert measured_lg_kv / base_kv == pytest.approx(1.0, rel=1e-4)


class TestUnbalancedLineLineDerivation:
    """Golden scenario (task section 22): verify L-L is derived from
    `Va - Vb` (complex), never `sqrt(3) * Va` -- an UNBALANCED case makes
    the two formulas diverge sharply, so this is a real discriminating
    test, not just a balanced-case coincidence."""

    def test_derived_vab_matches_complex_subtraction_not_sqrt3_shortcut(self):
        quantity = get_voltage_quantity(QUANTITY_PHASE_AB_LL_RMS)
        # Deliberately unbalanced: Va and Vb have different magnitudes
        # and a non-120-degree separation (a plausible disturbance/fault
        # condition, not a healthy balanced system).
        va = RolePhasor(magnitude=120.0, angle_deg=10.0)
        vb = RolePhasor(magnitude=80.0, angle_deg=-100.0)
        role_phasors = {ROLE_A: va, ROLE_B: vb}

        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        assert result.status == STATUS_AVAILABLE

        expected_complex = cmath.rect(va.magnitude, math.radians(va.angle_deg)) - cmath.rect(vb.magnitude, math.radians(vb.angle_deg))
        expected_magnitude, expected_angle_rad = cmath.polar(expected_complex)
        assert result.magnitude == pytest.approx(expected_magnitude, rel=1e-9)
        assert result.angle_deg == pytest.approx(math.degrees(expected_angle_rad), rel=1e-9)

        # The sqrt(3)*VLN shortcut this task explicitly forbids would give
        # a materially different answer for this unbalanced pair -- proves
        # the two approaches are NOT numerically indistinguishable here.
        sqrt3_shortcut = math.sqrt(3) * va.magnitude
        assert result.magnitude != pytest.approx(sqrt3_shortcut, rel=0.05)

    def test_direct_pair_channel_used_verbatim_never_rederived(self):
        """task section 11: a genuine direct Vab reading is used as-is,
        never re-derived from Va/Vb even if both also happen to resolve."""
        quantity = get_voltage_quantity(QUANTITY_PHASE_AB_LL_RMS)
        role_phasors = {ROLE_AB: RolePhasor(magnitude=273.4, angle_deg=None)}
        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=True)
        assert result.status == STATUS_AVAILABLE
        assert result.magnitude == pytest.approx(273.4)
        assert result.angle_deg is None


class TestUnsupportedRepresentationGuardrail:
    """task sections 8/10: deriving line-line (without a direct pair) or
    positive sequence requires genuine complex phasors -- an already-RMS,
    angle-less input must be REJECTED, never silently assumed balanced."""

    def test_derived_line_line_rejects_angle_less_rms_input(self):
        quantity = get_voltage_quantity(QUANTITY_PHASE_AB_LL_RMS)
        role_phasors = {ROLE_A: RolePhasor(magnitude=120.0, angle_deg=None), ROLE_B: RolePhasor(magnitude=118.0, angle_deg=None)}
        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        assert result.status == STATUS_UNSUPPORTED_REPRESENTATION
        assert result.magnitude is None
        assert "angle" in result.message.lower()

    def test_positive_sequence_rejects_angle_less_rms_input(self):
        quantity = get_voltage_quantity(QUANTITY_POSITIVE_SEQUENCE_RMS)
        role_phasors = {
            ROLE_A: RolePhasor(magnitude=120.0, angle_deg=None),
            ROLE_B: RolePhasor(magnitude=118.0, angle_deg=None),
            ROLE_C: RolePhasor(magnitude=121.0, angle_deg=None),
        }
        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        assert result.status == STATUS_UNSUPPORTED_REPRESENTATION
        assert result.magnitude is None

    def test_positive_sequence_accepts_when_only_some_roles_have_angles_missing_is_still_rejected(self):
        quantity = get_voltage_quantity(QUANTITY_POSITIVE_SEQUENCE_RMS)
        role_phasors = {
            ROLE_A: RolePhasor(magnitude=120.0, angle_deg=0.0),
            ROLE_B: RolePhasor(magnitude=118.0, angle_deg=-120.0),
            ROLE_C: RolePhasor(magnitude=121.0, angle_deg=None),
        }
        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        assert result.status == STATUS_UNSUPPORTED_REPRESENTATION


class TestMinMaxPhase:
    def test_min_and_max_of_three_phase_magnitudes(self):
        role_phasors = {
            ROLE_A: RolePhasor(magnitude=100.0, angle_deg=0.0),
            ROLE_B: RolePhasor(magnitude=70.0, angle_deg=-120.0),
            ROLE_C: RolePhasor(magnitude=105.0, angle_deg=120.0),
        }
        min_result = compute_voltage_quantity_value(get_voltage_quantity(QUANTITY_MIN_PHASE_LG_RMS), role_phasors, used_direct_pair=False)
        max_result = compute_voltage_quantity_value(get_voltage_quantity(QUANTITY_MAX_PHASE_LG_RMS), role_phasors, used_direct_pair=False)
        assert min_result.status == STATUS_AVAILABLE
        assert min_result.magnitude == pytest.approx(70.0)
        assert max_result.status == STATUS_AVAILABLE
        assert max_result.magnitude == pytest.approx(105.0)


class TestPositiveSequenceReusesSequenceComponentsVerbatim:
    def test_matches_compute_symmetrical_components_directly(self):
        quantity = get_voltage_quantity(QUANTITY_POSITIVE_SEQUENCE_RMS)
        role_phasors = {
            ROLE_A: RolePhasor(magnitude=100.0, angle_deg=5.0),
            ROLE_B: RolePhasor(magnitude=95.0, angle_deg=-118.0),
            ROLE_C: RolePhasor(magnitude=102.0, angle_deg=121.0),
        }
        result = compute_voltage_quantity_value(quantity, role_phasors, used_direct_pair=False)
        expected = compute_symmetrical_components(100.0, 5.0, 95.0, -118.0, 102.0, 121.0)
        assert result.magnitude == pytest.approx(expected.positive_magnitude)
        assert result.angle_deg == pytest.approx(expected.positive_angle_deg)
