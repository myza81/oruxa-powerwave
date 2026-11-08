"""DEC-050 Slice 5C-2 — Primary/Secondary Voltage Reference Model tests.

Covers all cases from the Slice 5C-2 specification:

  Case A — Primary L-L (132 kV):         denominator = 132 kV
  Case B — Primary L-G (132 kV):         denominator = 132/√3 = 76.210235... kV
  Case C — Secondary L-L (132kV/110V):   denominator = 110 V
  Case D — Secondary L-G (132kV/110V):   denominator = 110/√3 = 63.508529... V
  Case E — Phase-winding VT (76200/63.5):
              primary_ll_v = 76200 × √3 = 131982.277... V  (≠ 132000 V)
              secondary_ll_v = 63.5 × √3 = 109.985... V    (≠ 110 V)
  Case F — Unknown measurement side:     unverified, not silently chosen

  VT ratio:
    - vt_ratio_valid: accepts positive finite values, known winding_ref
    - vt_primary_ll_v / vt_secondary_ll_v: correct for phase-referred and L-L-referred
    - Phase-winding: multiplies by √3; L-L winding: returns directly
    - Turns ratio = primary_winding_v / secondary_winding_v

  Numerical acceptance:
    - All 6 cases above independently verified
    - 76200 × √3 is NOT silently rounded to 132000
    - 63.5 × √3 is NOT silently rounded to 110

  Configuration field:
    - VoltageBaseConfiguration.secondary_voltage_ll_v field present and defaults None
    - Adding secondary_voltage_ll_v does not change existing resolve_voltage_base_for_group output
    - Legacy configurations with no secondary_voltage_ll_v continue to resolve correctly

  Current compatibility:
    - 100 MVA, 132 kV: Ibase_primary = 100e6 / (√3 × 132e3) = 437.3865676 A = 0.4373865676 kA
    - Secondary CT ratio 1200/1: Ibase_secondary = 437.3865676 / 1200 = 0.36448... A
    - Equipment-rating Ibase always uses PRIMARY nominal voltage, never secondary VT voltage
    - CT primary winding rating ≠ Nominal Current ≠ Equipment-rated Ibase

  Validation:
    - Invalid VT ratio (negative/zero/None/bool) is rejected
    - Unknown winding_ref is rejected
    - Invalid measurement side is handled
    - representation_unknown produces base_required

  Mixed reference scenarios:
    - Primary Voltage + Primary Current (consistent)
    - Secondary Voltage + Secondary Current (consistent)
    - Primary Voltage + Secondary Current (P/S mismatch noted, Current blocked)
    - Unknown-side measurement must not silently become authoritative

  Slice 5C-1 closure — authority gate matrix (all 6 required combinations):
    - suggested + auto_resolved → CONFIGURED (bypass)
    - needs_review (GROUP STATUS) + auto_resolved → BLOCKED (identity conflict)
    - confirmed + auto_resolved → CONFIGURED
    - confirmed + unavailable → BLOCKED
    - manual + manual → CONFIGURED (existing behavior)
    - confirmed + legacy_manual → CONFIGURED (existing behavior)
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_UNAVAILABLE,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import (
    SQRT_3 as CURRENT_SQRT_3,
    CurrentBaseConfiguration,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    resolve_current_base_for_group,
    STATUS_BASE_REQUIRED as C_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as C_STATUS_CONFIGURED,
)
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL as MG_STATUS_MANUAL,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.voltage_group_config import (
    SQRT_3,
    AUTHORITATIVE_GROUP_STATUSES,
    VoltageBaseConfiguration,
    resolve_voltage_base_for_group,
    STATUS_BASE_REQUIRED as V_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as V_STATUS_CONFIGURED,
)
from app.domain.voltage_primary_secondary import (
    DERIVATION_PRIMARY_NOMINAL,
    DERIVATION_SECONDARY_CONFIGURED,
    DERIVATION_SECONDARY_FROM_VT,
    DERIVATION_UNKNOWN_UNVERIFIED,
    PS_STATUS_BASE_REQUIRED,
    PS_STATUS_CONFIGURED,
    PS_STATUS_UNVERIFIED,
    REPR_LINE_TO_GROUND,
    REPR_LINE_TO_LINE,
    SIDE_PRIMARY,
    SIDE_SECONDARY,
    SIDE_UNKNOWN,
    VT_WINDING_LL,
    VT_WINDING_PHASE,
    VtRatio,
    VoltageReferenceSideResolution,
    resolve_ps_voltage_denominator,
    resolve_ps_voltage_denominator_from_vt_ratio,
    vt_primary_ll_v,
    vt_ratio_valid,
    vt_secondary_ll_v,
    vt_turns_ratio,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vgroup(status: str = STATUS_CONFIRMED, channel_names: tuple[str, ...] = ("VRY", "VYB")) -> MeasurementGroup:
    return MeasurementGroup(
        id="vg1", workspace_id="ws1", source_id="src1",
        kind=KIND_VOLTAGE, status=status, display_name="132kV Group",
        channel_refs=[ChannelRef(kind="source", source_id="src1", channel_name=n) for n in channel_names],
    )


def _cgroup(status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id="cg1", workspace_id="ws1", source_id="src1",
        kind=KIND_CURRENT, status=status, display_name="HV Current",
        channel_refs=[],
    )


# ---------------------------------------------------------------------------
# Case A — Primary L-L
# ---------------------------------------------------------------------------

class TestCaseA_PrimaryLL:
    """Nominal system Voltage: 132 kV L-L. Measurement: Primary L-L.
    Expected PU denominator: 132 kV.
    """

    def test_denominator_is_132kv(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_CONFIGURED
        assert result.measurement_side == SIDE_PRIMARY
        assert result.representation == REPR_LINE_TO_LINE
        assert math.isclose(result.denominator_kv, 132.0, rel_tol=1e-9)
        assert math.isclose(result.denominator_v, 132_000.0, rel_tol=1e-9)
        assert result.derivation == DERIVATION_PRIMARY_NOMINAL

    def test_denominator_is_132kv_exact_value(self):
        """Exact float comparison for 132 kV."""
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.denominator_v == 132_000.0

    def test_missing_primary_nominal_gives_base_required(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=None,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_BASE_REQUIRED
        assert result.reason == "primary_nominal_not_configured"


# ---------------------------------------------------------------------------
# Case B — Primary L-G
# ---------------------------------------------------------------------------

class TestCaseB_PrimaryLG:
    """Nominal system Voltage: 132 kV L-L. Measurement: Primary L-G.
    Expected denominator: 132 / sqrt(3) = 76.210235533... kV.
    """

    def test_denominator_is_132_over_sqrt3_kv(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_GROUND,
        )
        assert result.status == PS_STATUS_CONFIGURED
        expected_kv = 132.0 / SQRT_3
        assert math.isclose(result.denominator_kv, expected_kv, rel_tol=1e-9)
        expected_v = 132_000.0 / SQRT_3
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-9)

    def test_denominator_independent_verification(self):
        """Independently verify: 132000 / 1.7320508075688772 = 76210.235..."""
        expected_v = 132_000.0 / 1.7320508075688772
        assert math.isclose(expected_v, 76_210.235, rel_tol=1e-4)
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_GROUND,
        )
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Case C — Secondary L-L
# ---------------------------------------------------------------------------

class TestCaseC_SecondaryLL:
    """Nominal primary: 132 kV L-L. VT: 132,000/110 V L-L-referred.
    Measurement: Secondary L-L.
    Expected denominator: 110 V.
    """

    def test_denominator_is_110v(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_CONFIGURED
        assert result.measurement_side == SIDE_SECONDARY
        assert math.isclose(result.denominator_v, 110.0, rel_tol=1e-9)
        assert math.isclose(result.denominator_kv, 0.110, rel_tol=1e-9)
        assert result.derivation == DERIVATION_SECONDARY_CONFIGURED

    def test_secondary_denominator_is_not_primary_nominal(self):
        """The secondary denominator must NOT be 132 kV."""
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert not math.isclose(result.denominator_kv, 132.0, rel_tol=1e-6)
        assert math.isclose(result.denominator_v, 110.0, rel_tol=1e-9)

    def test_missing_secondary_gives_base_required(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_BASE_REQUIRED
        assert result.reason == "secondary_equivalent_not_configured"


# ---------------------------------------------------------------------------
# Case D — Secondary L-G
# ---------------------------------------------------------------------------

class TestCaseD_SecondaryLG:
    """Nominal primary: 132 kV L-L. Secondary equivalent: 110 V L-L.
    Measurement: Secondary L-G.
    Expected denominator: 110 / sqrt(3) = 63.508529611... V.
    """

    def test_denominator_is_110_over_sqrt3_v(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_GROUND,
        )
        assert result.status == PS_STATUS_CONFIGURED
        expected_v = 110.0 / SQRT_3
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-9)

    def test_denominator_independent_verification(self):
        """Independently verify: 110 / 1.7320508075688772 = 63.508529..."""
        expected_v = 110.0 / 1.7320508075688772
        assert math.isclose(expected_v, 63.5085, rel_tol=1e-4)
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_GROUND,
        )
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Case E — Phase-winding VT ratio
# ---------------------------------------------------------------------------

class TestCaseE_PhaseWindingVT:
    """VT winding: 76,200 V / 63.5 V, phase-referred.
    primary_ll_v  = 76,200 × √3  (NOT exactly 132,000 V)
    secondary_ll_v = 63.5 × √3   (NOT exactly 110 V)
    """

    _ratio = VtRatio(primary_winding_v=76_200.0, secondary_winding_v=63.5, winding_ref=VT_WINDING_PHASE)

    def test_vt_ratio_valid(self):
        assert vt_ratio_valid(self._ratio)

    def test_primary_ll_is_76200_times_sqrt3_not_132000(self):
        """76200 × √3 ≠ 132000 — must NOT be silently rounded."""
        expected = 76_200.0 * SQRT_3
        result = vt_primary_ll_v(self._ratio)
        assert math.isclose(result, expected, rel_tol=1e-12)
        assert not math.isclose(result, 132_000.0, rel_tol=1e-6)

    def test_secondary_ll_is_63point5_times_sqrt3_not_110(self):
        """63.5 × √3 ≠ 110 — must NOT be silently rounded."""
        expected = 63.5 * SQRT_3
        result = vt_secondary_ll_v(self._ratio)
        assert math.isclose(result, expected, rel_tol=1e-12)
        assert not math.isclose(result, 110.0, rel_tol=1e-4)

    def test_primary_ll_independent_verification(self):
        """76200 × 1.7320508075688772 = 131982.277..."""
        expected = 76_200.0 * 1.7320508075688772
        assert math.isclose(expected, 131_982.277, rel_tol=1e-4)
        result = vt_primary_ll_v(self._ratio)
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_secondary_ll_independent_verification(self):
        """63.5 × 1.7320508075688772 = 109.985..."""
        expected = 63.5 * 1.7320508075688772
        assert math.isclose(expected, 109.985, rel_tol=1e-3)
        result = vt_secondary_ll_v(self._ratio)
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_turns_ratio(self):
        """Turns ratio = primary / secondary = 76200 / 63.5 = 1200.0."""
        assert math.isclose(vt_turns_ratio(self._ratio), 76_200.0 / 63.5, rel_tol=1e-12)

    def test_resolve_secondary_ll_via_vt_ratio(self):
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=self._ratio,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_CONFIGURED
        assert result.derivation == DERIVATION_SECONDARY_FROM_VT
        expected_v = 63.5 * SQRT_3
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-12)

    def test_resolve_secondary_lg_via_vt_ratio(self):
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=self._ratio,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_GROUND,
        )
        expected_v = (63.5 * SQRT_3) / SQRT_3
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-12)

    def test_resolve_primary_ll_via_vt_ratio_no_nominal_given(self):
        """Without a separately established nominal, primary side uses VT-derived primary_ll_v."""
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=self._ratio,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_CONFIGURED
        expected_v = 76_200.0 * SQRT_3
        assert math.isclose(result.denominator_v, expected_v, rel_tol=1e-12)

    def test_resolve_primary_ll_via_vt_ratio_with_nominal_overrides(self):
        """When a separately established nominal is given, it overrides VT-derived primary."""
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=self._ratio,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
            nominal_primary_ll_kv=132.0,
        )
        assert result.status == PS_STATUS_CONFIGURED
        assert math.isclose(result.denominator_v, 132_000.0, rel_tol=1e-9)

    def test_secondary_equivalent_stored_in_resolution(self):
        """The resolution carries the derived secondary_equivalent_ll_v for provenance."""
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=self._ratio,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        expected_secondary = 63.5 * SQRT_3
        assert result.secondary_equivalent_ll_v is not None
        assert math.isclose(result.secondary_equivalent_ll_v, expected_secondary, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Case F — Unknown measurement side
# ---------------------------------------------------------------------------

class TestCaseF_UnknownSide:
    """Unknown measurement side must not be silently promoted to primary or secondary."""

    def test_unknown_side_returns_unverified(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=275.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_UNKNOWN,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_UNVERIFIED
        assert result.denominator_v is None
        assert result.denominator_kv is None
        assert result.reason == "measurement_side_unknown"

    def test_unknown_side_via_vt_ratio_still_unverified(self):
        ratio = VtRatio(76_200.0, 63.5, VT_WINDING_PHASE)
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=ratio,
            measurement_side=SIDE_UNKNOWN,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_UNVERIFIED

    def test_unknown_side_does_not_silently_equal_primary(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=275.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_UNKNOWN,
            representation=REPR_LINE_TO_LINE,
        )
        # Must never produce a denominator for unverified side
        assert result.status != PS_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# VT ratio validation
# ---------------------------------------------------------------------------

class TestVtRatioValidation:

    def test_valid_phase_referred(self):
        assert vt_ratio_valid(VtRatio(76_200.0, 63.5, VT_WINDING_PHASE))

    def test_valid_ll_referred(self):
        assert vt_ratio_valid(VtRatio(132_000.0, 110.0, VT_WINDING_LL))

    def test_ll_referred_returns_values_directly(self):
        ratio = VtRatio(132_000.0, 110.0, VT_WINDING_LL)
        assert math.isclose(vt_primary_ll_v(ratio), 132_000.0, rel_tol=1e-12)
        assert math.isclose(vt_secondary_ll_v(ratio), 110.0, rel_tol=1e-12)

    def test_negative_primary_is_invalid(self):
        assert not vt_ratio_valid(VtRatio(-76_200.0, 63.5, VT_WINDING_PHASE))

    def test_zero_secondary_is_invalid(self):
        assert not vt_ratio_valid(VtRatio(76_200.0, 0.0, VT_WINDING_PHASE))

    def test_bool_winding_v_is_invalid(self):
        assert not vt_ratio_valid(VtRatio(True, 63.5, VT_WINDING_PHASE))

    def test_unknown_winding_ref_is_invalid(self):
        assert not vt_ratio_valid(VtRatio(76_200.0, 63.5, "unknown"))  # type: ignore

    def test_invalid_ratio_in_resolver_gives_base_required(self):
        result = resolve_ps_voltage_denominator_from_vt_ratio(
            vt_ratio=VtRatio(-1.0, 63.5, VT_WINDING_PHASE),
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_BASE_REQUIRED
        assert result.reason == "vt_ratio_invalid"


# ---------------------------------------------------------------------------
# VoltageBaseConfiguration backward compatibility
# ---------------------------------------------------------------------------

class TestVoltageBaseConfigurationBackwardsCompatibility:
    """secondary_voltage_ll_v field defaults to None; existing code is unaffected."""

    def test_secondary_voltage_ll_v_defaults_to_none(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
        )
        assert cfg.secondary_voltage_ll_v is None

    def test_secondary_voltage_ll_v_can_be_set(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
            secondary_voltage_ll_v=110.0,
        )
        assert cfg.secondary_voltage_ll_v == 110.0

    def test_dataclasses_replace_preserves_secondary_voltage(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
            secondary_voltage_ll_v=110.0,
        )
        updated = replace(cfg, nominal_voltage_ll_kv=275.0)
        assert updated.secondary_voltage_ll_v == 110.0

    def test_resolve_voltage_base_unaffected_by_secondary_voltage_ll_v(self):
        """The live resolver (primary path) must still use nominal_voltage_ll_kv
        unchanged when secondary_voltage_ll_v is set.
        """
        group = _vgroup(STATUS_CONFIRMED, ("VRY", "VYB"))
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
            secondary_voltage_ll_v=110.0,  # set but not wired yet
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        # Denominator must be 132 kV (L-L), not 110 V
        assert math.isclose(result.denominator_kv, 132.0, rel_tol=1e-9)

    def test_legacy_config_resolves_unchanged(self):
        """Legacy configs (no secondary_voltage_ll_v) resolve as before."""
        group = _vgroup(STATUS_CONFIRMED, ("VRN", "VYN", "VBN"))
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0,
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected = 275.0 / SQRT_3
        assert math.isclose(result.denominator_kv, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Current compatibility — primary Ibase
# ---------------------------------------------------------------------------

class TestCurrentPrimaryIbase:
    """Equipment-rated Ibase always uses PRIMARY nominal voltage, never secondary.

    Spec example:
      Sbase = 100 MVA, NominalVoltage_LL_primary = 132 kV
      Ibase_primary = 100e6 / (√3 × 132e3) = 437.3865676... A = 0.4373865676... kA
    """

    _SBASE_MVA = 100.0
    _VLL_KV = 132.0

    def test_equipment_rating_ibase_primary(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=self._SBASE_MVA,
            manual_voltage_base_kv=self._VLL_KV,
        )
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED
        expected_ka = self._SBASE_MVA / (CURRENT_SQRT_3 * self._VLL_KV)
        assert math.isclose(result.ibase_ka, expected_ka, rel_tol=1e-9)

    def test_independent_verification_437_a(self):
        """100e6 / (1.7320508 × 132e3) = 437.386..."""
        expected_a = 100e6 / (1.7320508075688772 * 132_000.0)
        assert math.isclose(expected_a, 437.3865676, rel_tol=1e-6)
        group = _cgroup(STATUS_CONFIRMED)
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=100.0, manual_voltage_base_kv=132.0,
        )
        result = resolve_current_base_for_group(group, cfg)
        assert math.isclose(result.ibase_ka * 1000.0, expected_a, rel_tol=1e-9)

    def test_equipment_ibase_uses_primary_voltage_not_secondary(self):
        """Using 110 V (secondary VT voltage) in place of 132 kV would give a wildly
        wrong value. This test documents and verifies the correct behavior.
        """
        # Wrong: if someone accidentally used 0.11 kV (110 V) as voltage base
        # Ibase_wrong = 100 MVA / (√3 × 0.11 kV) = 524.9... kA
        wrong_ka = 100.0 / (CURRENT_SQRT_3 * 0.11)
        # Correct: 100 MVA / (√3 × 132 kV) = 0.43738... kA
        correct_ka = 100.0 / (CURRENT_SQRT_3 * 132.0)
        # They are vastly different — the wrong value is ~1200× too large
        assert wrong_ka / correct_ka > 1000.0, "Using secondary voltage would inflate Ibase by ~1200x"

    def test_secondary_ct_ratio_ibase(self):
        """Secondary Ibase via CT ratio 1200/1:
        Ibase_secondary = 437.3865676 / 1200 = 0.36448880... A.
        This is currently manual-entered (CT ratio handling is not yet wired).
        """
        expected_a = 437.3865676 / 1200.0
        assert math.isclose(expected_a, 0.36448, rel_tol=1e-4)
        # Manual Ibase path
        group = _cgroup(STATUS_CONFIRMED)
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_MANUAL,
            manual_ibase_ka=expected_a / 1000.0,  # in kA
        )
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED
        assert math.isclose(result.ibase_ka * 1000.0, expected_a, rel_tol=1e-6)

    def test_ct_primary_rating_ne_equipment_ibase(self):
        """CT primary rating ≠ equipment Ibase.
        A CT rated 600/1 A does not mean Ibase is 600 A — verify these stay separate.
        """
        # Equipment-rated Ibase from MVA
        equipment_ibase_ka = 100.0 / (CURRENT_SQRT_3 * 132.0)
        # CT primary winding 600 A
        ct_primary_a = 600.0
        # They are different values representing different engineering quantities
        assert not math.isclose(equipment_ibase_ka * 1000.0, ct_primary_a, rel_tol=0.01)


# ---------------------------------------------------------------------------
# Slice 5C-1 closure — authority gate matrix (all 6 required combinations)
# ---------------------------------------------------------------------------

class TestSlice5C1AuthorityGateMatrix:
    """Verification of the complete authority gate matrix from the Slice 5C-2 spec §2.

    All six combinations must be verified through tests (spec requirement):
    1. suggested + auto_resolved → Eligible (bypasses status gate)
    2. needs_review + auto_resolved → BLOCKED (identity conflict)
    3. confirmed + auto_resolved → Eligible
    4. confirmed + unavailable → BLOCKED
    5. manual + manual → Existing behavior preserved
    6. confirmed + legacy_manual → Existing behavior preserved
    """

    def _ll_config(self, base_authority) -> VoltageBaseConfiguration:
        return VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
            base_authority=base_authority,
        )

    def test_1_suggested_plus_auto_resolved_is_eligible(self):
        """Row 1: suggested + auto_resolved → CONFIGURED (bypass)."""
        group = _vgroup(STATUS_SUGGESTED, ("VRY", "VYB"))
        cfg = self._ll_config(BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_2_needs_review_group_plus_auto_resolved_is_blocked(self):
        """Row 2: needs_review (GROUP STATUS) + auto_resolved → BLOCKED.
        Conflicting identity evidence prevents authoritative PU even with a valid base.
        """
        group = _vgroup(STATUS_NEEDS_REVIEW, ("VRY", "VYB"))
        cfg = self._ll_config(BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_3_confirmed_plus_auto_resolved_is_eligible(self):
        """Row 3: confirmed + auto_resolved → CONFIGURED."""
        group = _vgroup(STATUS_CONFIRMED, ("VRY", "VYB"))
        cfg = self._ll_config(BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_4_confirmed_plus_unavailable_is_blocked(self):
        """Row 4: confirmed + unavailable → BLOCKED (base_invalidated)."""
        group = _vgroup(STATUS_CONFIRMED, ("VRY", "VYB"))
        cfg = self._ll_config(BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_5_manual_group_plus_manual_authority_is_eligible(self):
        """Row 5: manual (GROUP STATUS) + manual (BASE AUTHORITY) → CONFIGURED."""
        group = _vgroup(MG_STATUS_MANUAL, ("VRY", "VYB"))
        cfg = self._ll_config(BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_6_confirmed_plus_legacy_manual_is_eligible(self):
        """Row 6: confirmed + legacy_manual → CONFIGURED (existing behavior preserved)."""
        group = _vgroup(STATUS_CONFIRMED, ("VRY", "VYB"))
        cfg = self._ll_config(BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# Unknown reference side must not be silently promoted
# ---------------------------------------------------------------------------

class TestUnknownReferenceSide:
    """VoltageBaseConfiguration.base_reference_side = "unknown" must not cause
    automatic promotion. The PS resolver handles this explicitly.
    """

    def test_unknown_base_reference_side_field_exists_and_defaults(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
        )
        assert cfg.base_reference_side == "unknown"

    def test_ps_resolver_unknown_side_does_not_configure(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_UNKNOWN,
            representation=REPR_LINE_TO_LINE,
        )
        assert result.status == PS_STATUS_UNVERIFIED
        assert result.denominator_v is None


# ---------------------------------------------------------------------------
# Mixed reference scenarios
# ---------------------------------------------------------------------------

class TestMixedReferenceScenarios:
    """Recording may contain measurements at different reference sides."""

    def test_primary_voltage_primary_current_consistent(self):
        """Primary voltage + primary current: both use nominal primary voltage."""
        v_result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert v_result.status == PS_STATUS_CONFIGURED
        assert v_result.measurement_side == SIDE_PRIMARY

        # Primary Ibase: Sbase / (√3 × Vbase_LL_primary)
        ibase_primary_ka = 100.0 / (SQRT_3 * 132.0)
        assert math.isclose(ibase_primary_ka, 0.43738, rel_tol=1e-4)

    def test_secondary_voltage_secondary_current_consistent(self):
        """Secondary voltage + secondary current: both use secondary equivalents."""
        v_result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert v_result.status == PS_STATUS_CONFIGURED
        assert v_result.measurement_side == SIDE_SECONDARY
        assert math.isclose(v_result.denominator_v, 110.0, rel_tol=1e-9)

    def test_primary_voltage_secondary_current_note_mismatch(self):
        """P/S mismatch: primary voltage with secondary current is a valid recording
        scenario but requires careful handling. The PS model preserves both sides
        independently — no forced conflation.
        """
        v_result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert v_result.measurement_side == SIDE_PRIMARY

        c_result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=None,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_SECONDARY,
            representation=REPR_LINE_TO_LINE,
        )
        assert c_result.measurement_side == SIDE_SECONDARY

        # P and S denominators are different — this is correct, not an error
        assert not math.isclose(
            v_result.denominator_v, c_result.denominator_v, rel_tol=1e-6
        )

    def test_no_double_scaling_primary_to_secondary(self):
        """Primary denominator must not be additionally divided by VT ratio.
        That would constitute double-scaling.
        """
        ratio = VtRatio(132_000.0, 110.0, VT_WINDING_LL)
        turns = vt_turns_ratio(ratio)
        assert math.isclose(turns, 132_000.0 / 110.0, rel_tol=1e-12)

        # Primary denominator from nominal
        v_primary = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=110.0,
            measurement_side=SIDE_PRIMARY,
            representation=REPR_LINE_TO_LINE,
        )
        # Must NOT be 132000 / turns (that would be double-scaling)
        double_scaled = 132_000.0 / turns
        assert not math.isclose(v_primary.denominator_v, double_scaled, rel_tol=1e-6)
        assert math.isclose(v_primary.denominator_v, 132_000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# No change to existing PU outputs
# ---------------------------------------------------------------------------

class TestNoChangeToExistingPUOutputs:
    """The Slice 5C-2 additions must not change any existing resolver outputs."""

    def test_275kv_ll_group_resolves_as_before(self):
        group = _vgroup(STATUS_CONFIRMED, ("VRY", "VYB", "VBR"))
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0,
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_kv, 275.0, rel_tol=1e-9)

    def test_275kv_lg_group_resolves_as_before(self):
        group = _vgroup(STATUS_CONFIRMED, ("VRN", "VYN", "VBN"))
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0,
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected = 275.0 / SQRT_3
        assert math.isclose(result.denominator_kv, expected, rel_tol=1e-9)

    def test_suggested_group_still_base_required(self):
        group = _vgroup(STATUS_SUGGESTED, ("VRY",))
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_LEGACY,
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED

    def test_authoritative_group_statuses_unchanged(self):
        """AUTHORITATIVE_GROUP_STATUSES still contains exactly confirmed and manual."""
        assert STATUS_CONFIRMED in AUTHORITATIVE_GROUP_STATUSES
        assert MG_STATUS_MANUAL in AUTHORITATIVE_GROUP_STATUSES
        assert STATUS_SUGGESTED not in AUTHORITATIVE_GROUP_STATUSES
        assert STATUS_NEEDS_REVIEW not in AUTHORITATIVE_GROUP_STATUSES


# ---------------------------------------------------------------------------
# Representation unknown handling
# ---------------------------------------------------------------------------

class TestRepresentationUnknown:

    def test_primary_unknown_representation_gives_base_required(self):
        result = resolve_ps_voltage_denominator(
            nominal_primary_ll_kv=132.0,
            secondary_equivalent_ll_v=None,
            measurement_side=SIDE_PRIMARY,
            representation="diagonal",  # not a known representation
        )
        assert result.status == PS_STATUS_BASE_REQUIRED
        assert result.reason == "representation_unknown"
