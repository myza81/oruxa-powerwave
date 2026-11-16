"""DEC-050 Slice 5D-1 — Primary/Secondary PU Resolver Integration tests.

Covers the integration of voltage_primary_secondary.py into the live
resolve_voltage_base_for_group() resolver:

  Primary path backward compat:
    - base_reference_side "unknown" → uses nominal_voltage_ll_kv (LL and LG)
    - base_reference_side "primary" → uses nominal_voltage_ll_kv (LL and LG)
    - secondary_voltage_ll_v set but side "unknown" → still uses primary path

  Secondary path (Slice 5D-1):
    - base_reference_side "secondary" + valid secondary_voltage_ll_v → configured
    - base_reference_side "secondary" + no secondary → secondary_equivalent_not_configured
    - base_reference_side "secondary" + zero/inf/bool → secondary_equivalent_not_configured
    - nominal_voltage_ll_kv=None does NOT block secondary path
    - L-L and L-G representations via manual override

  Numerical acceptance (spec §6):
    - Primary 132 kV LL → 132,000 V denominator
    - Primary 132 kV LG → 76,210.235... V denominator (132000 / sqrt(3))
    - Secondary 110 V LL → 110 V denominator
    - Secondary 110 V LG → 63.508529... V denominator (110 / sqrt(3))
    - Phase-winding VT 76200/63.5 V primary L-L → 131,982.271... V (not 132000)
    - Phase-winding VT 76200/63.5 V secondary L-L → 109.985... V (not 110)
    - Unknown measurement side → no authoritative automatic PU

  Authority gates still active for secondary path:
    - needs_review authority + secondary → base_invalidated (gate first)
    - unavailable authority + secondary → base_invalidated (gate first)
    - suggested status (no bypass) + secondary → group_not_confirmed

  Stale secondary registry:
    - update_secondary=True stores value
    - update_secondary=False preserves existing
    - update_secondary=True, secondary_voltage_ll_v=None clears
    - Concurrent nominal + secondary edit is atomic

  Stale secondary service:
    - Changing nominal_voltage_ll_kv alone clears secondary (stale clear rule)
    - Providing both nominal and secondary in one call keeps both
    - Updating only secondary (nominal=None) preserves primary nominal
    - Reference-only change preserves secondary_voltage_ll_v

  Current base unaffected:
    - Equipment-rating Ibase always uses nominal_voltage_ll_kv, never secondary
    - Mixed secondary Voltage / primary Current → Current Ibase correct
"""

from __future__ import annotations

import math

import pytest

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
    BASE_AUTHORITY_UNAVAILABLE,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import (
    CurrentBaseConfiguration,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    SQRT_3 as CURRENT_SQRT_3,
    STATUS_CONFIGURED as C_STATUS_CONFIGURED,
    resolve_current_base_for_group,
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
    STATUS_BASE_REQUIRED as V_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as V_STATUS_CONFIGURED,
    VoltageBaseConfiguration,
    resolve_voltage_base_for_group,
)
from app.domain.voltage_primary_secondary import (
    SQRT_3,
    VtRatio,
    VT_WINDING_PHASE,
    VT_WINDING_LL,
    vt_primary_ll_v,
    vt_secondary_ll_v,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import (
    set_current_base_equipment_rating,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import (
    return_voltage_reference_to_auto,
    set_manual_voltage_reference,
    set_voltage_base,
    update_voltage_configuration,
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


def _vconfig(**kwargs) -> VoltageBaseConfiguration:
    defaults = dict(measurement_group_id="vg1", workspace_id="ws1", nominal_voltage_ll_kv=132.0)
    defaults.update(kwargs)
    return VoltageBaseConfiguration(**defaults)


def _iconfig(**kwargs) -> CurrentBaseConfiguration:
    defaults = dict(measurement_group_id="cg1", workspace_id="ws1", method=METHOD_MANUAL, manual_ibase_ka=1.0)
    defaults.update(kwargs)
    return CurrentBaseConfiguration(**defaults)


def _make_registries(
    *,
    group: MeasurementGroup,
    vconfig: VoltageBaseConfiguration | None = None,
    iconfig: CurrentBaseConfiguration | None = None,
) -> tuple[MeasurementGroupRegistry, VoltageGroupConfigRegistry, CurrentGroupConfigRegistry]:
    gr = MeasurementGroupRegistry()
    gr.add(group)
    vr = VoltageGroupConfigRegistry()
    if vconfig is not None:
        vr.upsert(vconfig)
    cr = CurrentGroupConfigRegistry()
    if iconfig is not None:
        cr.upsert(iconfig)
    return gr, vr, cr


# ---------------------------------------------------------------------------
# Primary path backward compatibility
# ---------------------------------------------------------------------------

class TestPrimaryPathBackwardCompat:
    """Existing configs have base_reference_side="unknown"; all must behave exactly as before."""

    def test_unknown_side_ll_reference_uses_nominal(self):
        """base_reference_side "unknown" + LL channels → denominator = nominal kV (in V)."""
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="unknown",
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)
        assert math.isclose(result.denominator_kv, 132.0, rel_tol=1e-9)

    def test_unknown_side_lg_reference_uses_nominal_over_sqrt3(self):
        """base_reference_side "unknown" + LG channels → denominator = nominal kV / √3."""
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="unknown",
                       reference_mode="manual", reference_override="line_to_ground")
        group = _vgroup(channel_names=("VR", "VY", "VB"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected_v = 132_000.0 / SQRT_3
        assert math.isclose(result.denominator_volts, expected_v, rel_tol=1e-9)

    def test_explicit_primary_side_ll_reference(self):
        """base_reference_side "primary" behaves identically to "unknown" for primary configs."""
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="primary",
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)

    def test_explicit_primary_side_lg_reference(self):
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="primary",
                       reference_mode="manual", reference_override="line_to_ground")
        group = _vgroup(channel_names=("VR", "VY", "VB"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected_v = 132_000.0 / SQRT_3
        assert math.isclose(result.denominator_volts, expected_v, rel_tol=1e-9)

    def test_secondary_voltage_set_but_side_unknown_still_primary(self):
        """secondary_voltage_ll_v present but base_reference_side is "unknown" → primary path."""
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="unknown",
                       secondary_voltage_ll_v=110.0,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)

    def test_no_config_still_base_required(self):
        """No config → voltage_base_not_configured regardless of new fields."""
        result = resolve_voltage_base_for_group(_vgroup(), None)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "voltage_base_not_configured"

    def test_legacy_config_no_secondary_field_behaves_as_before(self):
        """Config without explicit base_reference_side (defaults to "unknown") is unchanged."""
        cfg = _vconfig(nominal_voltage_ll_kv=275.0)
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 275_000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Secondary path
# ---------------------------------------------------------------------------

class TestSecondaryPath:
    """New behavior: base_reference_side="secondary" uses secondary_voltage_ll_v."""

    def test_secondary_side_ll_uses_secondary_voltage(self):
        """base_reference_side "secondary" + LL → denominator = secondary_voltage_ll_v."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 110.0, rel_tol=1e-9)
        assert math.isclose(result.denominator_kv, 0.11, rel_tol=1e-9)

    def test_secondary_side_lg_divides_by_sqrt3(self):
        """base_reference_side "secondary" + LG → denominator = secondary_voltage_ll_v / √3."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       reference_mode="manual", reference_override="line_to_ground")
        group = _vgroup(channel_names=("VR", "VY", "VB"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected_v = 110.0 / SQRT_3
        assert math.isclose(result.denominator_volts, expected_v, rel_tol=1e-9)

    def test_secondary_side_missing_secondary_voltage_is_base_required(self):
        """base_reference_side "secondary" but no secondary_voltage_ll_v → base_required.
        Safety rule: declaring secondary without a valid denominator must not silently fall
        through to the primary nominal (e.g. 63.5 V / 132 kV = 0.00048 pu — wrong).
        apply_voltage_reference() cannot catch this: secondary/secondary → "compatible"."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=None,
                       nominal_voltage_ll_kv=132.0, reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "secondary_equivalent_not_configured"

    def test_secondary_side_zero_secondary_is_base_required(self):
        """secondary_voltage_ll_v=0 is invalid; strict gate → secondary_equivalent_not_configured."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=0.0,
                       nominal_voltage_ll_kv=132.0, reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "secondary_equivalent_not_configured"

    def test_secondary_side_inf_secondary_is_base_required(self):
        """secondary_voltage_ll_v=inf is invalid; strict gate → secondary_equivalent_not_configured."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=float("inf"),
                       nominal_voltage_ll_kv=132.0, reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "secondary_equivalent_not_configured"

    def test_secondary_side_negative_secondary_is_base_required(self):
        """secondary_voltage_ll_v negative is invalid; strict gate → secondary_equivalent_not_configured."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=-110.0,
                       nominal_voltage_ll_kv=132.0, reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "secondary_equivalent_not_configured"

    def test_secondary_path_does_not_require_primary_nominal(self):
        """Secondary-referred recording may not have primary nominal configured yet."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       nominal_voltage_ll_kv=None,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 110.0, rel_tol=1e-9)

    def test_secondary_path_with_auto_ll_reference_detection(self):
        """Secondary path respects auto reference detection from channel names."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       nominal_voltage_ll_kv=None)
        group = _vgroup(channel_names=("VRY", "VYB"))  # LL-named → auto detects line_to_line
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert result.effective_reference == "line_to_line"
        assert math.isclose(result.denominator_volts, 110.0, rel_tol=1e-9)

    def test_secondary_undetermined_reference_is_base_required(self):
        """Secondary path: unresolved reference → voltage_reference_undetermined."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       nominal_voltage_ll_kv=None)
        # Ambiguous channel names → no auto detection
        group = _vgroup(channel_names=("CH1", "CH2"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "voltage_reference_undetermined"

    def test_secondary_path_suggested_plus_legacy_manual_blocked(self):
        """suggested group status + legacy_manual authority → group_not_confirmed (gate still applies)."""
        group = _vgroup(status=STATUS_SUGGESTED)
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_LEGACY,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"


# ---------------------------------------------------------------------------
# Authority gates — still active for secondary path
# ---------------------------------------------------------------------------

class TestAuthorityGatesSecondaryPath:
    """The authority gate runs before the secondary path; gates cannot be bypassed."""

    def test_needs_review_authority_blocks_secondary_path(self):
        """confirmed group + needs_review base authority → base_invalidated (gate first)."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_NEEDS_REVIEW,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(STATUS_CONFIRMED), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_unavailable_authority_blocks_secondary_path(self):
        """confirmed group + unavailable authority → base_invalidated."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_UNAVAILABLE,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(STATUS_CONFIRMED), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_needs_review_group_status_blocks_secondary_with_auto_resolved(self):
        """needs_review group status + auto_resolved authority → group_not_confirmed (identity conflict)."""
        group = _vgroup(status=STATUS_NEEDS_REVIEW)
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_AUTO,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_suggested_plus_auto_resolved_bypasses_for_secondary(self):
        """suggested group status + auto_resolved → bypass applies for secondary path too."""
        group = _vgroup(status=STATUS_SUGGESTED)
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_AUTO,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 110.0, rel_tol=1e-9)

    def test_manual_authority_confirmed_group_secondary_configured(self):
        """manual authority + confirmed group + secondary → configured."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_MANUAL,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(STATUS_CONFIRMED), cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_legacy_manual_authority_manual_group_secondary_configured(self):
        """legacy_manual authority + manual group status + secondary → configured."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       base_authority=BASE_AUTHORITY_LEGACY,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(MG_STATUS_MANUAL), cfg)
        assert result.status == V_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# Numerical acceptance (spec §6)
# ---------------------------------------------------------------------------

class TestNumericalAcceptance:
    """Exact numerical denominators per the Slice 5D-1 specification §6."""

    def test_primary_132kv_ll_denominator(self):
        """Primary 132 kV L-L → 132,000 V denominator."""
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="primary",
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)

    def test_primary_132kv_lg_denominator(self):
        """Primary 132 kV L-G → 132000/√3 = 76,210.235533... V denominator."""
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_reference_side="primary",
                       reference_mode="manual", reference_override="line_to_ground")
        group = _vgroup(channel_names=("VR", "VY", "VB"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected_v = 132_000.0 / SQRT_3
        assert math.isclose(result.denominator_volts, expected_v, rel_tol=1e-9)
        assert math.isclose(result.denominator_kv, expected_v / 1000.0, rel_tol=1e-9)
        # Spec §6: 76.210235533 kV
        assert math.isclose(result.denominator_kv, 76.210235533, rel_tol=1e-6)

    def test_secondary_110v_ll_denominator(self):
        """Secondary 110 V L-L → 110 V denominator."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 110.0, rel_tol=1e-9)

    def test_secondary_110v_lg_denominator(self):
        """Secondary 110 V measured L-G → 110/√3 = 63.508529611 V denominator."""
        cfg = _vconfig(base_reference_side="secondary", secondary_voltage_ll_v=110.0,
                       reference_mode="manual", reference_override="line_to_ground")
        group = _vgroup(channel_names=("VR", "VY", "VB"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected_v = 110.0 / SQRT_3
        assert math.isclose(result.denominator_volts, expected_v, rel_tol=1e-9)
        # Spec §6: 63.508529611 V
        assert math.isclose(result.denominator_volts, 63.508529611, rel_tol=1e-6)

    def test_phase_winding_vt_primary_not_132000(self):
        """Phase-winding VT 76200/63.5 V primary L-L → 76200×√3 ≠ 132000 V."""
        ratio = VtRatio(76_200.0, 63.5, VT_WINDING_PHASE)
        primary_ll_v = vt_primary_ll_v(ratio)
        assert not math.isclose(primary_ll_v, 132_000.0, rel_tol=1e-4)
        assert math.isclose(primary_ll_v, 131_982.271537, rel_tol=1e-4)
        # Configured via VT-derived primary value
        cfg = _vconfig(base_reference_side="primary",
                       nominal_voltage_ll_kv=primary_ll_v / 1000.0,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, primary_ll_v, rel_tol=1e-6)

    def test_phase_winding_vt_secondary_not_110(self):
        """Phase-winding VT 76200/63.5 V secondary L-L → 63.5×√3 ≠ 110 V."""
        ratio = VtRatio(76_200.0, 63.5, VT_WINDING_PHASE)
        secondary_ll_v = vt_secondary_ll_v(ratio)
        # 63.5 × √3 = 109.985... V; relative difference from 110 is ~0.014%
        # rel_tol=1e-4 (0.01%) is tighter than the difference, so isclose returns False
        assert not math.isclose(secondary_ll_v, 110.0, rel_tol=1e-4)
        assert math.isclose(secondary_ll_v, 109.985226, rel_tol=1e-4)
        cfg = _vconfig(base_reference_side="secondary",
                       secondary_voltage_ll_v=secondary_ll_v,
                       reference_mode="manual", reference_override="line_to_line")
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, secondary_ll_v, rel_tol=1e-6)

    def test_ll_referred_vt_gives_exact_values(self):
        """L-L-referred VT 132000/110 V → exact integer equivalents."""
        ratio = VtRatio(132_000.0, 110.0, VT_WINDING_LL)
        assert math.isclose(vt_primary_ll_v(ratio), 132_000.0, rel_tol=1e-12)
        assert math.isclose(vt_secondary_ll_v(ratio), 110.0, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Registry — secondary_voltage_ll_v update_fields
# ---------------------------------------------------------------------------

class TestStaleSecondaryRegistry:
    """VoltageGroupConfigRegistry.update_fields() secondary_voltage_ll_v / update_secondary."""

    def _fresh_registry(self) -> VoltageGroupConfigRegistry:
        return VoltageGroupConfigRegistry()

    def test_update_secondary_true_stores_value(self):
        reg = self._fresh_registry()
        cfg = reg.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        assert math.isclose(cfg.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        assert math.isclose(stored.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_update_secondary_false_preserves_existing(self):
        reg = self._fresh_registry()
        reg.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        # update without update_secondary flag → should preserve
        reg.update_fields("ws1", "vg1", nominal_voltage_ll_kv=132.0, update_secondary=False)
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        # Secondary should be preserved
        assert math.isclose(stored.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_update_secondary_true_with_none_clears(self):
        reg = self._fresh_registry()
        reg.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        reg.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=None)
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        assert stored.secondary_voltage_ll_v is None

    def test_update_secondary_default_false_no_new_config(self):
        """When update_secondary not passed, secondary_voltage_ll_v defaults to None on new config."""
        reg = self._fresh_registry()
        cfg = reg.update_fields("ws1", "vg1", nominal_voltage_ll_kv=132.0)
        assert cfg.secondary_voltage_ll_v is None

    def test_multiple_concurrent_fields_updated_atomically(self):
        """Nominal and secondary can be updated together without overwriting each other."""
        reg = self._fresh_registry()
        cfg = reg.update_fields(
            "ws1", "vg1",
            nominal_voltage_ll_kv=132.0,
            base_reference_side="secondary",
            update_secondary=True, secondary_voltage_ll_v=110.0,
        )
        assert math.isclose(cfg.nominal_voltage_ll_kv, 132.0, rel_tol=1e-12)
        assert cfg.base_reference_side == "secondary"
        assert math.isclose(cfg.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_reference_mode_update_does_not_touch_secondary(self):
        """Reference-mode-only update leaves secondary_voltage_ll_v unchanged."""
        reg = self._fresh_registry()
        reg.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        reg.update_fields("ws1", "vg1", reference_mode="auto")
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        assert math.isclose(stored.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Service — stale secondary clearing
# ---------------------------------------------------------------------------

class TestStaleSecondaryService:
    """voltage_group_config_service stale-secondary clearing via update_voltage_configuration."""

    def _setup(self):
        group = _vgroup()
        gr, vr, cr = _make_registries(group=group)
        return gr, vr, cr, group

    def test_changing_nominal_clears_secondary(self):
        """Updating nominal_voltage_ll_kv alone clears any existing secondary_voltage_ll_v."""
        gr, vr, cr, group = self._setup()
        # First, store a secondary voltage
        vr.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        # Now update primary nominal without secondary → stale clear
        cfg = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            group_registry=gr, voltage_config_registry=vr,
            nominal_voltage_ll_kv=132.0,
        )
        assert cfg.secondary_voltage_ll_v is None

    def test_providing_both_nominal_and_secondary_keeps_both(self):
        gr, vr, cr, group = self._setup()
        cfg = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            group_registry=gr, voltage_config_registry=vr,
            nominal_voltage_ll_kv=132.0,
            secondary_voltage_ll_v=110.0,
        )
        assert math.isclose(cfg.nominal_voltage_ll_kv, 132.0, rel_tol=1e-12)
        assert math.isclose(cfg.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_updating_only_secondary_preserves_primary(self):
        """secondary-only update (nominal=None) preserves nominal_voltage_ll_kv."""
        gr, vr, cr, group = self._setup()
        # Establish nominal first
        vr.update_fields("ws1", "vg1", nominal_voltage_ll_kv=132.0)
        # Update only secondary
        cfg = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            group_registry=gr, voltage_config_registry=vr,
            secondary_voltage_ll_v=110.0,
        )
        assert math.isclose(cfg.nominal_voltage_ll_kv, 132.0, rel_tol=1e-12)
        assert math.isclose(cfg.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_reference_only_change_preserves_secondary(self):
        """set_manual_voltage_reference does not touch secondary_voltage_ll_v."""
        gr, vr, cr, group = self._setup()
        vr.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        set_manual_voltage_reference(
            workspace_id="ws1", measurement_group_id="vg1",
            reference="line_to_ground",
            group_registry=gr, voltage_config_registry=vr,
        )
        stored = vr.get("ws1", "vg1")
        assert stored is not None
        assert math.isclose(stored.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_return_to_auto_preserves_secondary(self):
        """return_voltage_reference_to_auto does not touch secondary_voltage_ll_v."""
        gr, vr, cr, group = self._setup()
        vr.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        return_voltage_reference_to_auto(
            workspace_id="ws1", measurement_group_id="vg1",
            group_registry=gr, voltage_config_registry=vr,
        )
        stored = vr.get("ws1", "vg1")
        assert stored is not None
        assert math.isclose(stored.secondary_voltage_ll_v, 110.0, rel_tol=1e-12)

    def test_set_voltage_base_clears_secondary(self):
        """set_voltage_base changes primary nominal → stale secondary cleared."""
        gr, vr, cr, group = self._setup()
        vr.update_fields("ws1", "vg1", update_secondary=True, secondary_voltage_ll_v=110.0)
        cfg = set_voltage_base(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=275.0,
            group_registry=gr, voltage_config_registry=vr,
        )
        assert cfg.secondary_voltage_ll_v is None
        assert math.isclose(cfg.nominal_voltage_ll_kv, 275.0, rel_tol=1e-12)

    def test_invalid_secondary_raises_error(self):
        """update_voltage_configuration with invalid secondary_voltage_ll_v raises InvalidVoltageBaseValueError."""
        from app.services.errors import InvalidVoltageBaseValueError
        gr, vr, cr, group = self._setup()
        with pytest.raises(InvalidVoltageBaseValueError):
            update_voltage_configuration(
                workspace_id="ws1", measurement_group_id="vg1",
                group_registry=gr, voltage_config_registry=vr,
                secondary_voltage_ll_v=-5.0,
            )


# ---------------------------------------------------------------------------
# Current base unaffected
# ---------------------------------------------------------------------------

class TestCurrentBaseUnaffected:
    """Equipment-rating Ibase always uses nominal_voltage_ll_kv, never secondary_voltage_ll_v."""

    def test_equipment_rating_uses_primary_nominal(self):
        """Linked voltage group with secondary side → Current Ibase still uses primary nominal."""
        vgroup = _vgroup(channel_names=("VRY", "VYB"))
        cgroup = _cgroup()
        gr, vr, cr = _make_registries(group=vgroup)
        gr.add(cgroup)
        # Configure voltage group with secondary side and secondary value
        vr.upsert(_vconfig(
            nominal_voltage_ll_kv=132.0,
            base_reference_side="secondary",
            secondary_voltage_ll_v=110.0,
            base_authority=BASE_AUTHORITY_MANUAL,
        ))
        # Configure current group as equipment-rating linked to voltage group
        from app.domain.current_group_config import CurrentBaseConfiguration
        iconfig = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_EQUIPMENT_RATING,
            linked_voltage_group_id="vg1",
            equipment_rating_mva=100.0,
        )
        cr.upsert(iconfig)
        linked_vgroup = gr.get("ws1", "vg1")
        linked_vconfig = vr.get("ws1", "vg1")
        result = resolve_current_base_for_group(
            cgroup, iconfig,
            linked_voltage_group=linked_vgroup,
            linked_voltage_config=linked_vconfig,
        )
        assert result.status == C_STATUS_CONFIGURED
        # Ibase = Sbase / (sqrt(3) × nominal_voltage_ll_kv), never secondary
        expected_ibase_ka = 100.0 / (CURRENT_SQRT_3 * 132.0)
        assert math.isclose(result.ibase_ka, expected_ibase_ka, rel_tol=1e-6)
        # Must NOT use secondary_voltage_ll_v=110.0 (would inflate Ibase by ~1200×)
        wrong_ibase = 100.0 / (CURRENT_SQRT_3 * 0.11)  # using 110 V = 0.11 kV
        assert not math.isclose(result.ibase_ka, wrong_ibase, rel_tol=0.01)

    def test_manual_current_ibase_unaffected_by_voltage_side(self):
        """Manual Current base is independent of voltage group side declaration."""
        iconfig = _iconfig(manual_ibase_ka=0.5, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_current_base_for_group(_cgroup(), iconfig)
        assert result.status == C_STATUS_CONFIGURED
        assert math.isclose(result.ibase_ka, 0.5, rel_tol=1e-9)

    def test_equipment_rating_100mva_132kv_exact(self):
        """100 MVA / 132 kV equipment-rating Ibase exact value."""
        from app.domain.current_group_config import CurrentBaseConfiguration
        iconfig = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_EQUIPMENT_RATING,
            linked_voltage_group_id="vg1",
            equipment_rating_mva=100.0,
        )
        vconfig = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        vgroup = _vgroup()
        result = resolve_current_base_for_group(
            _cgroup(), iconfig,
            linked_voltage_group=vgroup,
            linked_voltage_config=vconfig,
        )
        assert result.status == C_STATUS_CONFIGURED
        expected = 100.0 / (CURRENT_SQRT_3 * 132.0)
        assert math.isclose(result.ibase_ka, expected, rel_tol=1e-9)
        # Spec: 0.4373865676 kA
        assert math.isclose(result.ibase_ka, 0.4373865676, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Unknown measurement side — not silently promoted
# ---------------------------------------------------------------------------

class TestUnknownSidePreservation:
    """Unknown base_reference_side must never silently activate secondary path."""

    def test_unknown_side_with_valid_secondary_uses_primary(self):
        """secondary_voltage_ll_v present but base_reference_side "unknown" → primary path used."""
        cfg = _vconfig(
            nominal_voltage_ll_kv=132.0,
            base_reference_side="unknown",
            secondary_voltage_ll_v=110.0,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        # Must use primary path: 132,000 V, not 110 V
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)
        assert not math.isclose(result.denominator_volts, 110.0, rel_tol=0.01)

    def test_unknown_side_no_nominal_still_base_required(self):
        """Unknown side + no nominal_voltage_ll_kv → voltage_base_not_configured (not secondary_equivalent_not_configured)."""
        cfg = _vconfig(
            nominal_voltage_ll_kv=None,
            base_reference_side="unknown",
            secondary_voltage_ll_v=110.0,
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "voltage_base_not_configured"

    def test_primary_side_with_no_secondary_still_works(self):
        """Explicit primary side with no secondary configured → normal primary path."""
        cfg = _vconfig(
            nominal_voltage_ll_kv=132.0,
            base_reference_side="primary",
            secondary_voltage_ll_v=None,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Final Safety Verification (spec §4 scenarios)
# ---------------------------------------------------------------------------

class TestFinalSafetyVerification:
    """Slice 5D-1 Final Safety Verification — targeted numerical regression tests.

    These tests verify the strict gate invariant:
      base_reference_side="secondary" without valid secondary_voltage_ll_v
      must NEVER silently fall back to the primary nominal denominator.
    """

    def test_secondary_63v5_lg_with_valid_denominator_approx_1pu(self):
        """Secondary 63.5 V LG with valid secondary_voltage_ll_v → denominator ~63.5 V.
        63.5 / 63.5 = 1.0 pu. Proves the secondary path, not the primary path."""
        cfg = _vconfig(
            base_reference_side="secondary",
            secondary_voltage_ll_v=110.0,  # 110 V LL → 110/√3 ≈ 63.5 V LG
            nominal_voltage_ll_kv=132.0,
            reference_mode="manual", reference_override="line_to_ground",
        )
        group = _vgroup(channel_names=("VR", "VY", "VB"))
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        expected_v = 110.0 / SQRT_3
        assert math.isclose(result.denominator_volts, expected_v, rel_tol=1e-9)
        # At 1 pu, channel_value_V / denominator ≈ 1.0 (e.g. 63.5 V / 63.508... V ≈ 1.0)
        ratio = 63.5 / result.denominator_volts
        assert math.isclose(ratio, 1.0, rel_tol=0.001)

    def test_secondary_missing_denominator_blocked(self):
        """Missing secondary_voltage_ll_v → base_required, not silently primary.
        Safety invariant: an incomplete secondary config must NEVER produce PU."""
        cfg = _vconfig(
            base_reference_side="secondary",
            secondary_voltage_ll_v=None,
            nominal_voltage_ll_kv=132.0,
            reference_mode="manual", reference_override="line_to_ground",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "secondary_equivalent_not_configured"
        # Denominator must be None — no accidental 132 kV denominator
        assert result.denominator_kv is None

    def test_secondary_no_equivalent_no_accidental_primary_denominator(self):
        """Secondary waveform declared (base_reference_side="secondary"), primary nominal
        is 132 kV, no secondary_voltage_ll_v → denominator must NOT be 132 kV.
        Without the strict gate a 63.5 V channel would compute ~0.00048 pu."""
        cfg = _vconfig(
            base_reference_side="secondary",
            secondary_voltage_ll_v=None,
            nominal_voltage_ll_kv=132.0,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        # The denominator must never be the primary 132 kV
        assert result.denominator_kv is None
        assert result.denominator_kv != 132.0

    def test_primary_waveform_unaffected_by_secondary_gate(self):
        """Primary-declared group is completely unaffected by the secondary gate."""
        cfg = _vconfig(
            base_reference_side="primary",
            secondary_voltage_ll_v=None,
            nominal_voltage_ll_kv=132.0,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)

    def test_vlt_ref_001_compat_secondary_realistic_vt_equivalent(self):
        """VLT-REF-001 compatibility: base_reference_side="secondary" with a physically
        realistic 110 V secondary circuit (132 kV / 110 V LL-referred VT).
        Strict gate satisfied → configured with 110 V denominator, not 132 kV."""
        cfg = _vconfig(
            base_reference_side="secondary",
            secondary_voltage_ll_v=110.0,   # real VT secondary: 110 V LL circuit
            nominal_voltage_ll_kv=132.0,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_volts, 110.0, rel_tol=1e-9)
        assert math.isclose(result.denominator_kv, 0.11, rel_tol=1e-9)
        # Must NOT use primary nominal (132,000 V)
        assert not math.isclose(result.denominator_volts, 132_000.0, rel_tol=0.01)

    def test_stale_secondary_cleared_on_primary_change_blocks_pu(self):
        """Changing nominal_voltage_ll_kv clears secondary_voltage_ll_v.
        After clear, base_reference_side="secondary" with None → base_required."""
        gr, vr, cr = _make_registries(group=_vgroup())
        # Establish a valid secondary config
        vr.update_fields("ws1", "vg1",
                         nominal_voltage_ll_kv=132.0,
                         base_reference_side="secondary",
                         update_secondary=True, secondary_voltage_ll_v=110.0,
                         base_authority=BASE_AUTHORITY_MANUAL)
        cfg_before = vr.get("ws1", "vg1")
        result_before = resolve_voltage_base_for_group(_vgroup(), cfg_before)
        assert result_before.status == V_STATUS_CONFIGURED
        assert math.isclose(result_before.denominator_volts, 110.0, rel_tol=1e-9)
        # Change primary nominal without re-providing secondary → stale clear
        cfg_after = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            group_registry=gr, voltage_config_registry=vr,
            nominal_voltage_ll_kv=275.0,
        )
        assert cfg_after.secondary_voltage_ll_v is None
        result_after = resolve_voltage_base_for_group(_vgroup(), cfg_after)
        # After stale clear: secondary declared but no denominator → blocked
        assert result_after.status == V_STATUS_BASE_REQUIRED
        assert result_after.reason == "secondary_equivalent_not_configured"

    def test_needs_review_authority_blocks_before_secondary_gate(self):
        """needs_review authority is blocked before the secondary gate even runs."""
        cfg = _vconfig(
            base_reference_side="secondary",
            secondary_voltage_ll_v=None,  # would be secondary_equivalent_not_configured anyway
            base_authority=BASE_AUTHORITY_NEEDS_REVIEW,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(STATUS_CONFIRMED), cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_unknown_side_not_promoted_to_secondary_path(self):
        """base_reference_side="unknown" with valid secondary_voltage_ll_v → primary path.
        Unknown side must never silently activate the secondary denominator."""
        cfg = _vconfig(
            base_reference_side="unknown",
            secondary_voltage_ll_v=63.5,
            nominal_voltage_ll_kv=132.0,
            reference_mode="manual", reference_override="line_to_line",
        )
        result = resolve_voltage_base_for_group(_vgroup(), cfg)
        assert result.status == V_STATUS_CONFIGURED
        # Must be primary path: 132,000 V, not 63.5 V
        assert math.isclose(result.denominator_volts, 132_000.0, rel_tol=1e-9)
