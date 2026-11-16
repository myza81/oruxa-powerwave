"""Tests for app.domain.base_authority (DEC-050 Slices 5B and 5C-1).

Covers:

  Authority predicates:
    - is_base_eligible_for_pu: legacy_manual, manual, auto_resolved → True
    - needs_review, unavailable → False
    - is_engineer_approved: legacy_manual, manual → True; others → False
    - is_auto_resolved: auto_resolved → True; others → False
    - is_base_invalidated: unavailable → True; others → False
    - is_base_state_valid: all known states → True; garbage → False
    - should_invalidate_on_contradiction: auto_resolved → True; others → False

  Backward compatibility:
    - VoltageBaseConfiguration defaults to BASE_AUTHORITY_LEGACY
    - CurrentBaseConfiguration defaults to BASE_AUTHORITY_LEGACY
    - dataclasses.replace() preserves base_authority
    - Existing confirmed Voltage/Current configurations remain eligible
    - Legacy default does not change resolve_voltage_base_for_group outcome

  Authority independence from group status:
    - Suggested group + auto_resolved authority: eligible predicate True
    - Confirmed group + unavailable authority: NOT eligible
    - Confirmed group + needs_review authority: NOT eligible

  Primary/Secondary Voltage denominators:
    - 132 kV L-L → denominator 132 kV
    - 132 kV L-G → denominator 132 / sqrt(3) kV (= 76.210... kV)
    - 110 V L-L secondary (validated) → denominator 110 V (= 0.110 kV)
    - 110 V L-G secondary → denominator 110 / sqrt(3) V
    - Primary nominal NOT overwritten by secondary equivalent

  Equipment-MVA-derived Current:
    - 100 MVA, 132 kV: Ibase = 100 / (sqrt(3) × 132) = 0.43735... kA
    - CT primary rating (0.6 kA) ≠ Ibase (0.43735 kA)
    - Nominal voltage used in equipment_rating Ibase is always primary LL

  Unknown reference side:
    - Unknown side base_reference_side is not silently promoted

  Authority gate active (Slice 5C-1):
    - needs_review and unavailable block PU regardless of group lifecycle status
    - legacy_manual, manual, auto_resolved remain eligible for PU
    - auto_resolved authority bypasses the group-status gate (confirmed not required)
    - A confirmed group whose base is unavailable is still blocked
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
    BASE_AUTHORITY_UNAVAILABLE,
    KNOWN_BASE_AUTHORITY_STATES,
    is_base_eligible_for_pu,
    is_base_invalidated,
    is_base_state_valid,
    is_engineer_approved,
    is_auto_resolved,
    should_invalidate_on_contradiction,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import (
    SQRT_3,
    CurrentBaseConfiguration,
    equipment_rating_ibase_ka,
    resolve_current_base_for_group,
    STATUS_CONFIGURED,
    STATUS_BASE_REQUIRED,
    STATUS_NOT_APPLICABLE,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    METHOD_NONE,
)
from app.domain.measurement_group import (
    MeasurementGroup,
    KIND_VOLTAGE,
    KIND_CURRENT,
    STATUS_CONFIRMED,
    STATUS_MANUAL as MG_STATUS_MANUAL,
    STATUS_SUGGESTED,
    STATUS_NEEDS_REVIEW,
)
from app.domain.voltage_group_config import (
    VoltageBaseConfiguration,
    resolve_voltage_base_for_group,
    STATUS_CONFIGURED as V_STATUS_CONFIGURED,
    STATUS_BASE_REQUIRED as V_STATUS_BASE_REQUIRED,
    STATUS_NOT_APPLICABLE as V_STATUS_NOT_APPLICABLE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _voltage_group(status: str = STATUS_CONFIRMED, channel_names: tuple[str, ...] = ()) -> MeasurementGroup:
    return MeasurementGroup(
        id="vg1", workspace_id="ws1", source_id="src1",
        kind=KIND_VOLTAGE, status=status,
        display_name="275KV Group",
        channel_refs=[
            ChannelRef(kind="source", source_id="src1", channel_name=n)
            for n in channel_names
        ],
    )


def _current_group(status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id="cg1", workspace_id="ws1", source_id="src1",
        kind=KIND_CURRENT, status=status,
        display_name="HV Current Group",
        channel_refs=[],
    )


def _vconfig(**kwargs) -> VoltageBaseConfiguration:
    defaults = dict(
        measurement_group_id="vg1", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
    )
    defaults.update(kwargs)
    return VoltageBaseConfiguration(**defaults)


def _iconfig(**kwargs) -> CurrentBaseConfiguration:
    defaults = dict(
        measurement_group_id="cg1", workspace_id="ws1",
        method=METHOD_MANUAL, manual_ibase_ka=1.0,
    )
    defaults.update(kwargs)
    return CurrentBaseConfiguration(**defaults)


# ---------------------------------------------------------------------------
# BaseAuthorityState predicates
# ---------------------------------------------------------------------------

class TestIsBaseEligibleForPU:
    def test_legacy_manual_eligible(self):
        assert is_base_eligible_for_pu(BASE_AUTHORITY_LEGACY) is True

    def test_manual_eligible(self):
        assert is_base_eligible_for_pu(BASE_AUTHORITY_MANUAL) is True

    def test_auto_resolved_eligible(self):
        assert is_base_eligible_for_pu(BASE_AUTHORITY_AUTO) is True

    def test_needs_review_not_eligible(self):
        assert is_base_eligible_for_pu(BASE_AUTHORITY_NEEDS_REVIEW) is False

    def test_unavailable_not_eligible(self):
        assert is_base_eligible_for_pu(BASE_AUTHORITY_UNAVAILABLE) is False

    def test_unknown_string_not_eligible(self):
        assert is_base_eligible_for_pu("garbage") is False


class TestIsEngineerApproved:
    def test_legacy_manual_approved(self):
        assert is_engineer_approved(BASE_AUTHORITY_LEGACY) is True

    def test_manual_approved(self):
        assert is_engineer_approved(BASE_AUTHORITY_MANUAL) is True

    def test_auto_resolved_not_approved(self):
        assert is_engineer_approved(BASE_AUTHORITY_AUTO) is False

    def test_needs_review_not_approved(self):
        assert is_engineer_approved(BASE_AUTHORITY_NEEDS_REVIEW) is False

    def test_unavailable_not_approved(self):
        assert is_engineer_approved(BASE_AUTHORITY_UNAVAILABLE) is False


class TestIsAutoResolved:
    def test_auto_resolved_true(self):
        assert is_auto_resolved(BASE_AUTHORITY_AUTO) is True

    def test_legacy_manual_false(self):
        assert is_auto_resolved(BASE_AUTHORITY_LEGACY) is False

    def test_manual_false(self):
        assert is_auto_resolved(BASE_AUTHORITY_MANUAL) is False

    def test_needs_review_false(self):
        assert is_auto_resolved(BASE_AUTHORITY_NEEDS_REVIEW) is False

    def test_unavailable_false(self):
        assert is_auto_resolved(BASE_AUTHORITY_UNAVAILABLE) is False


class TestIsBaseInvalidated:
    def test_unavailable_invalidated(self):
        assert is_base_invalidated(BASE_AUTHORITY_UNAVAILABLE) is True

    def test_legacy_manual_not_invalidated(self):
        assert is_base_invalidated(BASE_AUTHORITY_LEGACY) is False

    def test_manual_not_invalidated(self):
        assert is_base_invalidated(BASE_AUTHORITY_MANUAL) is False

    def test_auto_resolved_not_invalidated(self):
        assert is_base_invalidated(BASE_AUTHORITY_AUTO) is False

    def test_needs_review_not_invalidated(self):
        assert is_base_invalidated(BASE_AUTHORITY_NEEDS_REVIEW) is False


class TestIsBaseStateValid:
    @pytest.mark.parametrize("state", list(KNOWN_BASE_AUTHORITY_STATES))
    def test_all_known_states_valid(self, state):
        assert is_base_state_valid(state) is True

    def test_garbage_invalid(self):
        assert is_base_state_valid("garbage") is False

    def test_empty_string_invalid(self):
        assert is_base_state_valid("") is False

    def test_case_sensitive(self):
        assert is_base_state_valid("Legacy_Manual") is False


class TestShouldInvalidateOnContradiction:
    def test_auto_resolved_invalidates(self):
        assert should_invalidate_on_contradiction(BASE_AUTHORITY_AUTO) is True

    def test_legacy_manual_does_not_invalidate(self):
        assert should_invalidate_on_contradiction(BASE_AUTHORITY_LEGACY) is False

    def test_manual_does_not_invalidate(self):
        assert should_invalidate_on_contradiction(BASE_AUTHORITY_MANUAL) is False

    def test_needs_review_does_not_invalidate(self):
        assert should_invalidate_on_contradiction(BASE_AUTHORITY_NEEDS_REVIEW) is False

    def test_unavailable_does_not_invalidate(self):
        assert should_invalidate_on_contradiction(BASE_AUTHORITY_UNAVAILABLE) is False


# ---------------------------------------------------------------------------
# Backward compatibility — VoltageBaseConfiguration
# ---------------------------------------------------------------------------

class TestVoltageBaseConfigurationDefaultAuthority:
    def test_default_authority_is_legacy_manual(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
        )
        assert cfg.base_authority == BASE_AUTHORITY_LEGACY

    def test_legacy_default_is_eligible_for_pu(self):
        cfg = _vconfig()
        assert is_base_eligible_for_pu(cfg.base_authority) is True

    def test_replace_preserves_base_authority(self):
        cfg = _vconfig(base_authority=BASE_AUTHORITY_MANUAL)
        copy = replace(cfg)
        assert copy.base_authority == BASE_AUTHORITY_MANUAL

    def test_replace_can_change_base_authority(self):
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        updated = replace(cfg, base_authority=BASE_AUTHORITY_UNAVAILABLE)
        assert updated.base_authority == BASE_AUTHORITY_UNAVAILABLE

    def test_all_authority_states_accepted(self):
        for state in KNOWN_BASE_AUTHORITY_STATES:
            cfg = _vconfig(base_authority=state)
            assert cfg.base_authority == state

    def test_existing_config_constructed_without_field_uses_default(self):
        """Simulate a configuration loaded from storage before Slice 5B.
        When the field is absent, Python uses the dataclass default.
        """
        cfg = VoltageBaseConfiguration(
            measurement_group_id="old-g", workspace_id="old-ws",
            nominal_voltage_ll_kv=275.0,
            reference_mode="auto",
            reference_override=None,
            base_reference_side="primary",
        )
        assert cfg.base_authority == BASE_AUTHORITY_LEGACY


class TestCurrentBaseConfigurationDefaultAuthority:
    def test_default_authority_is_legacy_manual(self):
        cfg = CurrentBaseConfiguration(
            measurement_group_id="g1", workspace_id="ws1",
        )
        assert cfg.base_authority == BASE_AUTHORITY_LEGACY

    def test_legacy_default_is_eligible_for_pu(self):
        cfg = _iconfig()
        assert is_base_eligible_for_pu(cfg.base_authority) is True

    def test_replace_preserves_base_authority(self):
        cfg = _iconfig(base_authority=BASE_AUTHORITY_MANUAL)
        copy = replace(cfg)
        assert copy.base_authority == BASE_AUTHORITY_MANUAL

    def test_all_authority_states_accepted(self):
        for state in KNOWN_BASE_AUTHORITY_STATES:
            cfg = _iconfig(base_authority=state)
            assert cfg.base_authority == state


# ---------------------------------------------------------------------------
# Authority independent of group status
# ---------------------------------------------------------------------------

class TestAuthorityIndependenceFromGroupStatus:
    """§1: authority state and Measurement Group identity status are INDEPENDENT."""

    def test_suggested_group_with_auto_resolved_authority_is_eligible(self):
        """Group status suggested, but evidence was auto_resolved: eligible."""
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        assert is_base_eligible_for_pu(cfg.base_authority) is True

    def test_confirmed_group_with_unavailable_authority_not_eligible(self):
        """Group status confirmed, but auto base was invalidated: NOT eligible (§4)."""
        cfg = _vconfig(base_authority=BASE_AUTHORITY_UNAVAILABLE)
        assert is_base_eligible_for_pu(cfg.base_authority) is False

    def test_confirmed_group_with_needs_review_not_eligible(self):
        """Measurement Group confirmed but evidence contradictory: NOT eligible."""
        cfg = _vconfig(base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        assert is_base_eligible_for_pu(cfg.base_authority) is False

    def test_manual_override_takes_precedence_over_auto(self):
        """Engineer's manual override is engineer-approved; auto is not."""
        manual_cfg = _vconfig(base_authority=BASE_AUTHORITY_MANUAL)
        auto_cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        assert is_engineer_approved(manual_cfg.base_authority) is True
        assert is_engineer_approved(auto_cfg.base_authority) is False

    def test_invalidation_does_not_keep_auto_base_usable(self):
        """§4: unavailable must not remain eligible just because group is confirmed."""
        cfg = _vconfig(base_authority=BASE_AUTHORITY_UNAVAILABLE)
        assert is_base_eligible_for_pu(cfg.base_authority) is False
        assert is_base_invalidated(cfg.base_authority) is True


# ---------------------------------------------------------------------------
# resolve_voltage_base_for_group — resolver behavior unchanged by Slice 5B
# ---------------------------------------------------------------------------

class TestVoltageResolverUnchangedBySlice5B:
    """Slice 5B adds the field inertly; Slice 5C-1 wires the authority gate.
    Tests here cover both backward-compatible behavior and the Slice 5C-1 gate."""

    def test_confirmed_group_legacy_authority_resolves(self):
        """Existing configurations with legacy authority still resolve correctly."""
        group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB", "VBR"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_kv, 275.0, rel_tol=1e-9)

    def test_manual_group_legacy_authority_resolves(self):
        group = _voltage_group(MG_STATUS_MANUAL, channel_names=("VRY", "VYB", "VBR"))
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_kv, 132.0, rel_tol=1e-9)

    def test_confirmed_group_explicit_manual_authority_resolves(self):
        group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_suggested_group_does_not_resolve_regardless_of_authority(self):
        """Group status gate: suggested → base_required (unchanged by Slice 5B)."""
        group = _voltage_group(STATUS_SUGGESTED, channel_names=("VRY",))
        cfg = _vconfig(base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_auto_resolved_authority_resolves_on_confirmed_group(self):
        """auto_resolved authority on a confirmed group → CONFIGURED."""
        group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_auto_resolved_authority_bypasses_status_gate_for_suggested_group(self):
        """Slice 5C-1: auto_resolved authority bypasses the group-status gate.
        A suggested group with valid auto_resolved config → CONFIGURED.
        """
        group = _voltage_group(STATUS_SUGGESTED, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_needs_review_group_status_with_auto_resolved_base_is_blocked(self):
        """Slice 5C-2 (Slice 5C-1 closure): a needs_review GROUP STATUS must block PU
        even when base_authority is auto_resolved.
        needs_review means conflicting identity evidence — the group identity itself is
        disputed, so it must never become PU-authoritative regardless of its base state.
        """
        group = _voltage_group(STATUS_NEEDS_REVIEW, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_unavailable_authority_blocks_resolver(self):
        """Slice 5C-1: unavailable authority blocks resolver regardless of group status."""
        group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_needs_review_authority_blocks_resolver(self):
        """Slice 5C-1: needs_review authority blocks resolver."""
        group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_no_config_still_base_required(self):
        group = _voltage_group(STATUS_CONFIRMED)
        result = resolve_voltage_base_for_group(group, None)
        assert result.status == V_STATUS_BASE_REQUIRED


# ---------------------------------------------------------------------------
# Primary/Secondary Voltage denominators
# ---------------------------------------------------------------------------

class TestVoltageDenominators:
    """Numerical correctness of the existing voltage-base denominator logic."""

    def test_ll_132kv_denominator(self):
        """L-L measurement, 132 kV nominal: denominator = 132 kV."""
        from app.domain.voltage_reference import LINE_TO_LINE

        group = MeasurementGroup(
            id="vg2", workspace_id="ws1", source_id="src1",
            kind=KIND_VOLTAGE, status=STATUS_CONFIRMED,
            display_name="132kV L-L",
            channel_refs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VRY"),
                ChannelRef(kind="source", source_id="src1", channel_name="VYB"),
            ],
        )
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg2", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert result.effective_reference == LINE_TO_LINE
        assert math.isclose(result.denominator_kv, 132.0, rel_tol=1e-9)

    def test_lg_132kv_denominator(self):
        """L-G measurement, 132 kV nominal: denominator = 132/√3 = 76.210... kV."""
        from app.domain.voltage_reference import LINE_TO_GROUND

        group = MeasurementGroup(
            id="vg3", workspace_id="ws1", source_id="src1",
            kind=KIND_VOLTAGE, status=STATUS_CONFIRMED,
            display_name="132kV L-G",
            channel_refs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VRN"),
                ChannelRef(kind="source", source_id="src1", channel_name="VYN"),
                ChannelRef(kind="source", source_id="src1", channel_name="VBN"),
            ],
        )
        cfg = VoltageBaseConfiguration(
            measurement_group_id="vg3", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,
        )
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert result.effective_reference == LINE_TO_GROUND
        expected_denom = 132.0 / SQRT_3
        assert math.isclose(result.denominator_kv, expected_denom, rel_tol=1e-9)

    def test_lg_denominator_exact_value(self):
        """132 / sqrt(3) = 76.2102..., not 76.2 (which is a winding rating).
        The difference (0.01023 kV ≈ 10.23 V) matters for PU accuracy.
        """
        denominator = 132.0 / SQRT_3
        assert math.isclose(denominator, 76.21023, rel_tol=1e-4)
        # 76.2102 vs 76.2: differ by ~0.0134% — distinguishable at rel_tol=1e-4
        assert not math.isclose(denominator, 76.2, rel_tol=1e-4)

    def test_primary_nominal_not_overwritten_by_secondary_equivalent(self):
        """The primary nominal (132 kV) must remain 132 kV.
        110 V L-L secondary equivalent is a different quantity and must
        not be stored in nominal_voltage_ll_kv (C1).
        """
        cfg_primary = VoltageBaseConfiguration(
            measurement_group_id="vg_p", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0,  # primary system LL
        )
        # A secondary-equivalent config would be wrong if stored here:
        cfg_secondary_wrong = VoltageBaseConfiguration(
            measurement_group_id="vg_s", workspace_id="ws1",
            nominal_voltage_ll_kv=0.110,  # This would be incorrect per C1
        )
        # Verify they are distinct and the primary value is preserved
        assert math.isclose(cfg_primary.nominal_voltage_ll_kv, 132.0, rel_tol=1e-9)
        assert not math.isclose(
            cfg_primary.nominal_voltage_ll_kv,
            cfg_secondary_wrong.nominal_voltage_ll_kv,
            rel_tol=0.5
        )

    def test_secondary_ll_denominator_requires_separate_config(self):
        """C1: secondary 110 V L-L equivalent is a separate design concern.
        The primary nominal_voltage_ll_kv = 132 kV must not be confused
        with the secondary 0.110 kV equivalent.
        """
        # 110 V L-L secondary → 0.110 kV denominator for secondary-referred PU
        # This is separate from primary-system configuration
        secondary_ll_kv = 0.110
        secondary_lg_kv = secondary_ll_kv / SQRT_3
        assert math.isclose(secondary_ll_kv, 0.110, rel_tol=1e-9)
        assert math.isclose(secondary_lg_kv, 0.110 / SQRT_3, rel_tol=1e-9)
        # Neither equals the 132 kV primary
        assert not math.isclose(secondary_ll_kv, 132.0, rel_tol=0.5)
        assert not math.isclose(secondary_lg_kv, 132.0 / SQRT_3, rel_tol=0.5)

    def test_sqrt3_constant_precision(self):
        """SQRT_3 must equal Python's math.sqrt(3) to 15+ significant figures."""
        assert math.isclose(SQRT_3, math.sqrt(3), rel_tol=1e-15)

    def test_76_2_times_sqrt3_exact(self):
        """76.2 × √3 = 131.9822715..., not 131.952 and not 132.0."""
        result = 76.2 * SQRT_3
        assert math.isclose(result, 131.9822715367, rel_tol=1e-9)
        assert not math.isclose(result, 131.952, rel_tol=1e-4)
        assert not math.isclose(result, 132.0, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# resolve_current_base_for_group — resolver behavior unchanged by Slice 5B
# ---------------------------------------------------------------------------

class TestCurrentResolverUnchangedBySlice5B:
    def test_manual_ibase_resolves(self):
        group = _current_group(STATUS_CONFIRMED)
        cfg = _iconfig(method=METHOD_MANUAL, manual_ibase_ka=1.0)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_CONFIGURED
        assert math.isclose(result.ibase_ka, 1.0, rel_tol=1e-9)

    def test_equipment_rating_resolves(self):
        """100 MVA, 132 kV: Ibase = 100 / (√3 × 132) = 0.43735... kA."""
        group = _current_group(STATUS_CONFIRMED)
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=100.0,
            manual_voltage_base_kv=132.0,
        )
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_CONFIGURED
        expected_ibase = 100.0 / (SQRT_3 * 132.0)
        assert math.isclose(result.ibase_ka, expected_ibase, rel_tol=1e-9)

    def test_suggested_group_does_not_resolve(self):
        group = _current_group(STATUS_SUGGESTED)
        cfg = _iconfig()
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_BASE_REQUIRED

    def test_legacy_authority_does_not_affect_resolver(self):
        """legacy_manual authority still resolves correctly."""
        group = _current_group(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_CONFIGURED

    def test_unavailable_authority_blocks_current_resolver(self):
        """Slice 5C-1: unavailable authority blocks current resolver."""
        group = _current_group(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_needs_review_authority_blocks_current_resolver(self):
        """Slice 5C-1: needs_review authority blocks current resolver."""
        group = _current_group(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_auto_resolved_bypasses_current_status_gate(self):
        """Slice 5C-1: auto_resolved authority bypasses the group-status gate for current groups."""
        group = _current_group(STATUS_SUGGESTED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_CONFIGURED

    def test_needs_review_group_status_with_auto_resolved_base_is_blocked_current(self):
        """Slice 5C-2 (Slice 5C-1 closure): needs_review GROUP STATUS blocks current PU
        even when base_authority is auto_resolved.
        """
        group = _current_group(STATUS_NEEDS_REVIEW)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"


# ---------------------------------------------------------------------------
# Equipment-MVA-derived Current — numerical correctness
# ---------------------------------------------------------------------------

class TestEquipmentRatingIbase:
    """Direct tests of equipment_rating_ibase_ka() and the numbers it produces."""

    def test_100mva_132kv(self):
        """Canonical worked example: 100 MVA, 132 kV.
        Ibase = 100 / (√3 × 132) = 0.43735... kA.
        """
        ibase = equipment_rating_ibase_ka(100.0, 132.0)
        expected = 100.0 / (SQRT_3 * 132.0)
        assert math.isclose(ibase, expected, rel_tol=1e-9)
        assert math.isclose(ibase, 0.43735, rel_tol=1e-4)

    def test_1000mva_500kv(self):
        """1000 MVA / 500 kV → 1000/(√3×500) = 2/√3 ≈ 1.1547 kA."""
        ibase = equipment_rating_ibase_ka(1000.0, 500.0)
        assert math.isclose(ibase, 2.0 / SQRT_3, rel_tol=1e-9)

    def test_1000mva_275kv(self):
        """1000 MVA / 275 kV → ~2.0995 kA."""
        ibase = equipment_rating_ibase_ka(1000.0, 275.0)
        expected = 1000.0 / (SQRT_3 * 275.0)
        assert math.isclose(ibase, expected, rel_tol=1e-9)
        assert math.isclose(ibase, 2.0995, rel_tol=1e-3)

    def test_1000mva_132kv(self):
        """1000 MVA / 132 kV → ~4.3739 kA."""
        ibase = equipment_rating_ibase_ka(1000.0, 132.0)
        expected = 1000.0 / (SQRT_3 * 132.0)
        assert math.isclose(ibase, expected, rel_tol=1e-9)
        assert math.isclose(ibase, 4.3739, rel_tol=1e-3)

    def test_ct_primary_rating_not_ibase(self):
        """CT primary rating (600 A = 0.6 kA) ≠ equipment nominal Ibase.
        For 100 MVA, 132 kV: Ibase = 0.43735 kA.
        These are different quantities and must never be confused.
        """
        ct_primary_ka = 0.6
        equipment_ibase = equipment_rating_ibase_ka(100.0, 132.0)
        assert not math.isclose(ct_primary_ka, equipment_ibase, rel_tol=0.1), (
            "CT primary (0.6 kA) must not equal equipment Ibase (0.437 kA)"
        )

    def test_equipment_rating_uses_primary_ll_voltage_not_phase(self):
        """Equipment-rating Ibase uses the raw LL voltage, never LL/√3.
        Linked Voltage group's L-G denominator must NOT be used here.
        Two otherwise-identical groups differing only in reference produce
        the same Ibase (module docstring invariant).
        """
        ibase_ll = equipment_rating_ibase_ka(100.0, 132.0)
        # If the phase voltage (132/√3 = 76.21 kV) were used incorrectly:
        ibase_wrong = equipment_rating_ibase_ka(100.0, 132.0 / SQRT_3)
        # The correct value uses 132 kV; the wrong value uses ~76.21 kV
        assert not math.isclose(ibase_ll, ibase_wrong, rel_tol=0.01), (
            "Using phase voltage instead of LL voltage gives wrong Ibase"
        )
        # Specifically: wrong_ibase = ibase_ll × √3 (roughly)
        assert math.isclose(ibase_wrong / ibase_ll, SQRT_3, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# Unknown reference side not silently promoted
# ---------------------------------------------------------------------------

class TestUnknownReferenceSideNotSilentlyPromoted:
    """§5: unknown base_reference_side must not be treated as primary or secondary."""

    def test_voltage_config_unknown_side_default(self):
        cfg = _vconfig()
        assert cfg.base_reference_side == "unknown"

    def test_current_config_unknown_side_default(self):
        cfg = _iconfig()
        assert cfg.base_reference_side == "unknown"

    def test_unknown_side_is_not_primary(self):
        cfg = _vconfig()
        assert cfg.base_reference_side != "primary"

    def test_unknown_side_is_not_secondary(self):
        cfg = _vconfig()
        assert cfg.base_reference_side != "secondary"

    def test_explicit_primary_side(self):
        cfg = _vconfig(base_reference_side="primary")
        assert cfg.base_reference_side == "primary"

    def test_replace_preserves_unknown_side(self):
        cfg = _vconfig(base_reference_side="unknown")
        copy = replace(cfg)
        assert copy.base_reference_side == "unknown"


# ---------------------------------------------------------------------------
# Source Default behavior unchanged
# ---------------------------------------------------------------------------

class TestSourceDefaultUnchanged:
    """Source Default PU path uses PerUnitBaseProfile, not VoltageBaseConfiguration.
    Slice 5B does not touch PerUnitBaseProfile — Source Default is unaffected.
    """

    def test_per_unit_base_profile_has_no_base_authority(self):
        """PerUnitBaseProfile is not modified by Slice 5B."""
        from app.domain.per_unit import PerUnitBaseProfile
        import inspect
        sig = inspect.signature(PerUnitBaseProfile)
        assert "base_authority" not in sig.parameters

    def test_per_unit_registry_uses_base_profile(self):
        """The source-wide per-unit registry does not involve VoltageBaseConfiguration."""
        from app.services.per_unit_registry import PerUnitRegistry
        reg = PerUnitRegistry()
        assert reg.count() == 0

    def test_voltage_group_config_has_base_authority(self):
        """VoltageBaseConfiguration does carry base_authority (Slice 5B)."""
        import inspect
        from app.domain.voltage_group_config import VoltageBaseConfiguration
        sig = inspect.signature(VoltageBaseConfiguration)
        assert "base_authority" in sig.parameters

    def test_current_group_config_has_base_authority(self):
        """CurrentBaseConfiguration does carry base_authority (Slice 5B)."""
        import inspect
        from app.domain.current_group_config import CurrentBaseConfiguration
        sig = inspect.signature(CurrentBaseConfiguration)
        assert "base_authority" in sig.parameters


# ---------------------------------------------------------------------------
# Automatic PU not activated — explicit confirmation
# ---------------------------------------------------------------------------

class TestAuthorityGateAndPUActivation:
    """Slice 5C-1 wires the authority gate; automatic PU import is still NOT activated."""

    def test_authority_gate_blocks_ineligible_states(self):
        """Slice 5C-1: needs_review and unavailable block PU for any group status."""
        for authority in (BASE_AUTHORITY_NEEDS_REVIEW, BASE_AUTHORITY_UNAVAILABLE):
            group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
            cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=authority)
            result = resolve_voltage_base_for_group(group, cfg)
            assert result.status == V_STATUS_BASE_REQUIRED, (
                f"authority={authority}: expected base_required, got {result.status}"
            )
            assert result.reason == "base_invalidated", (
                f"authority={authority}: expected 'base_invalidated', got {result.reason}"
            )

    def test_authority_gate_allows_eligible_states(self):
        """Slice 5C-1: legacy_manual, manual, auto_resolved all produce CONFIGURED."""
        for authority in (BASE_AUTHORITY_LEGACY, BASE_AUTHORITY_MANUAL, BASE_AUTHORITY_AUTO):
            group = _voltage_group(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
            cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=authority)
            result = resolve_voltage_base_for_group(group, cfg)
            assert result.status == V_STATUS_CONFIGURED, (
                f"authority={authority}: expected configured, got {result.status}"
            )

    def test_base_authority_module_has_no_import_of_live_registries(self):
        """base_authority.py must be a pure-domain module — no registry imports."""
        import app.domain.base_authority as ba_module
        import inspect
        source = inspect.getsource(ba_module)
        assert "registry" not in source.lower()
        assert "import" in source  # sanity: the module exists and has imports
        assert "app.services" not in source

    # test_no_auto_base_service_exists_yet removed: auto_base_service.py now exists (Slice 5D-2).
