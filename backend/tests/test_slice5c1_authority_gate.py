"""DEC-050 Slice 5C-1 — Safe Base-Authority Gate Integration tests (including 5C-1 hardening).

Covers the authority gate wired into the live resolvers:

  Voltage resolver gate:
    - needs_review authority → base_required("base_invalidated") regardless of group status
    - unavailable authority → base_required("base_invalidated") regardless of group status
    - legacy_manual authority → eligible, confirmed group resolves normally
    - manual authority → eligible, confirmed group resolves normally
    - auto_resolved authority → eligible; BYPASSES group-status gate (suggested OK)
    - No config → no authority to check → falls through to existing base-required

  Current resolver gate:
    - Mirrors voltage resolver exactly (same 5 × 2 matrix)
    - confirmed + unavailable → blocked
    - suggested + auto_resolved → CONFIGURED (bypass)

  Service-layer authority transitions:
    - set_voltage_base() → base_authority=manual on result config
    - set_manual_voltage_reference() → base_authority unchanged (reference-only)
    - return_voltage_reference_to_auto() → base_authority unchanged (reference-only)
    - set_current_base_equipment_rating() → base_authority=manual
    - set_current_base_manual() → base_authority=manual
    - set_current_base_none() → base_authority=manual (explicit engineer choice)

  Registry update_fields:
    - base_authority passed → stored; None → not changed (preserves existing)

  Downstream reason codes:
    - compliance_series returns message for base_invalidated reason
    - per_unit_provenance_service has base_invalidated entry in copy map

  AUTHORITATIVE_GROUP_STATUSES constant reuse:
    - calculated_current_per_unit uses domain constant (not an inline tuple)

  Scope guard:
    - base_authority domain module stays pure (no registry imports)
    - Live resolvers do not import auto_base_evidence/auto_base_service directly
    - update_voltage_configuration() does not expose base_authority as a parameter
    - NOTE: auto_base_service.py now exists (Slice 5D-2) but is not wired into resolvers
"""

from __future__ import annotations

import importlib
import inspect
import math

import pytest

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
    BASE_AUTHORITY_UNAVAILABLE,
    KNOWN_BASE_AUTHORITY_STATES,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import (
    AUTHORITATIVE_GROUP_STATUSES as CURRENT_AUTHORITATIVE_GROUP_STATUSES,
    CurrentBaseConfiguration,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    METHOD_NONE,
    SQRT_3,
    STATUS_BASE_REQUIRED as C_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as C_STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE as C_STATUS_NOT_APPLICABLE,
    resolve_current_base_for_group,
)
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL as MG_STATUS_MANUAL,
    STATUS_NEEDS_REVIEW as MG_STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.voltage_group_config import (
    AUTHORITATIVE_GROUP_STATUSES as VOLTAGE_AUTHORITATIVE_GROUP_STATUSES,
    STATUS_BASE_REQUIRED as V_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as V_STATUS_CONFIGURED,
    VoltageBaseConfiguration,
    resolve_voltage_base_for_group,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vgroup(status: str = STATUS_CONFIRMED, channel_names: tuple[str, ...] = ("VRY", "VYB")) -> MeasurementGroup:
    return MeasurementGroup(
        id="vg1", workspace_id="ws1", source_id="src1",
        kind=KIND_VOLTAGE, status=status,
        display_name="275KV Group",
        channel_refs=[
            ChannelRef(kind="source", source_id="src1", channel_name=n)
            for n in channel_names
        ],
    )


def _cgroup(status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id="cg1", workspace_id="ws1", source_id="src1",
        kind=KIND_CURRENT, status=status,
        display_name="HV Current Group",
        channel_refs=[],
    )


def _vconfig(**kwargs) -> VoltageBaseConfiguration:
    defaults = dict(measurement_group_id="vg1", workspace_id="ws1", nominal_voltage_ll_kv=275.0)
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
    group_reg = MeasurementGroupRegistry()
    group_reg.add(group)
    vol_reg = VoltageGroupConfigRegistry()
    if vconfig is not None:
        vol_reg.upsert(vconfig)
    cur_reg = CurrentGroupConfigRegistry()
    if iconfig is not None:
        cur_reg.upsert(iconfig)
    return group_reg, vol_reg, cur_reg


# ---------------------------------------------------------------------------
# Voltage resolver — authority gate
# ---------------------------------------------------------------------------

class TestVoltageAuthorityGate:

    def test_needs_review_blocks_confirmed_group(self):
        """Confirmed group with needs_review authority → base_invalidated."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_unavailable_blocks_confirmed_group(self):
        """A confirmed group must not bypass an invalidated base."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_unavailable_blocks_manual_group(self):
        """Even a MG_STATUS_MANUAL group cannot bypass an unavailable base."""
        group = _vgroup(MG_STATUS_MANUAL)
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_needs_review_blocks_suggested_group(self):
        """needs_review blocks even suggested groups (gate fires before status check)."""
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_legacy_manual_resolves_confirmed(self):
        """legacy_manual authority with confirmed group → CONFIGURED."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_manual_resolves_confirmed(self):
        """manual authority with confirmed group → CONFIGURED."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_auto_resolved_resolves_confirmed(self):
        """auto_resolved authority with confirmed group → CONFIGURED."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_auto_resolved_bypasses_status_gate_for_suggested(self):
        """auto_resolved authority bypasses the group-status gate.
        A suggested group with valid auto_resolved config → CONFIGURED.
        This is the key Slice 5C-1 behavioral difference from manual/legacy.
        """
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_legacy_manual_does_not_bypass_status_gate(self):
        """legacy_manual requires confirmed/manual group status."""
        group = _vgroup(STATUS_SUGGESTED, channel_names=("VRY",))
        cfg = _vconfig(base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_manual_does_not_bypass_status_gate(self):
        """manual authority also requires confirmed/manual group status."""
        group = _vgroup(STATUS_SUGGESTED, channel_names=("VRY",))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_no_config_still_base_required_no_authority_check(self):
        """When config is None, authority gate is not consulted — falls to base-not-configured."""
        group = _vgroup(STATUS_CONFIRMED)
        result = resolve_voltage_base_for_group(group, None)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "voltage_base_not_configured"


# ---------------------------------------------------------------------------
# Current resolver — authority gate
# ---------------------------------------------------------------------------

class TestCurrentAuthorityGate:

    def test_needs_review_blocks_confirmed_group(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_unavailable_blocks_confirmed_group(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_unavailable_blocks_manual_group(self):
        group = _cgroup(MG_STATUS_MANUAL)
        cfg = _iconfig(manual_ibase_ka=1.0, base_authority=BASE_AUTHORITY_UNAVAILABLE)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"

    def test_legacy_manual_resolves_confirmed(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED

    def test_manual_resolves_confirmed(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED

    def test_auto_resolved_resolves_confirmed(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED

    def test_auto_resolved_bypasses_status_gate_for_suggested(self):
        """Slice 5C-1: auto_resolved authority bypasses the current group-status gate."""
        group = _cgroup(STATUS_SUGGESTED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED

    def test_legacy_does_not_bypass_status_gate(self):
        group = _cgroup(STATUS_SUGGESTED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_no_config_still_base_required(self):
        group = _cgroup(STATUS_CONFIRMED)
        result = resolve_current_base_for_group(group, None)
        assert result.status == C_STATUS_BASE_REQUIRED


# ---------------------------------------------------------------------------
# Registry — update_fields base_authority parameter
# ---------------------------------------------------------------------------

class TestRegistryUpdateFieldsAuthority:

    def test_update_fields_stores_base_authority(self):
        """Passing base_authority to update_fields persists it."""
        reg = VoltageGroupConfigRegistry()
        result = reg.update_fields(
            "ws1", "vg1",
            nominal_voltage_ll_kv=275.0,
            base_authority=BASE_AUTHORITY_MANUAL,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        assert stored.base_authority == BASE_AUTHORITY_MANUAL

    def test_update_fields_preserves_authority_when_not_supplied(self):
        """Omitting base_authority from update_fields does not reset it."""
        reg = VoltageGroupConfigRegistry()
        reg.update_fields("ws1", "vg1", nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        # update reference_mode only — no base_authority argument
        from app.domain.voltage_group_config import VOLTAGE_REFERENCE_MODE_MANUAL
        from app.domain.voltage_reference import LINE_TO_LINE
        reg.update_fields("ws1", "vg1", reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL,
                          reference_override=LINE_TO_LINE)
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        assert stored.base_authority == BASE_AUTHORITY_MANUAL

    def test_update_fields_new_config_defaults_to_legacy(self):
        """A brand-new config created by update_fields gets BASE_AUTHORITY_LEGACY."""
        reg = VoltageGroupConfigRegistry()
        result = reg.update_fields("ws1", "vg2", nominal_voltage_ll_kv=132.0)
        assert result.base_authority == BASE_AUTHORITY_LEGACY

    def test_update_fields_can_transition_authority(self):
        """Authority can be changed after the config exists."""
        reg = VoltageGroupConfigRegistry()
        reg.update_fields("ws1", "vg1", nominal_voltage_ll_kv=275.0,
                          base_authority=BASE_AUTHORITY_AUTO)
        reg.update_fields("ws1", "vg1", base_authority=BASE_AUTHORITY_UNAVAILABLE)
        stored = reg.get("ws1", "vg1")
        assert stored is not None
        assert stored.base_authority == BASE_AUTHORITY_UNAVAILABLE


# ---------------------------------------------------------------------------
# Service layer — authority transitions
# ---------------------------------------------------------------------------

class TestVoltageServiceAuthorityTransitions:

    def _make_voltage_group(self, workspace_id: str = "ws1", group_id: str = "vg1") -> MeasurementGroup:
        return MeasurementGroup(
            id=group_id, workspace_id=workspace_id, source_id="src1",
            kind=KIND_VOLTAGE, status=STATUS_CONFIRMED, display_name="275KV Group",
            channel_refs=[],
        )

    def test_set_voltage_base_sets_manual_authority(self):
        """set_voltage_base() — engineer action — transitions authority to manual."""
        from app.services.voltage_group_config_service import set_voltage_base
        group = self._make_voltage_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        result = set_voltage_base(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=275.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_set_voltage_base_overwrites_legacy_authority(self):
        """An existing legacy_manual config transitions to manual on set_voltage_base."""
        from app.services.voltage_group_config_service import set_voltage_base
        group = self._make_voltage_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        # Seed a legacy config
        vol_reg.upsert(VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_LEGACY,
        ))
        result = set_voltage_base(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=275.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_set_manual_voltage_reference_does_not_change_authority(self):
        """Reference-only action must NOT touch base_authority."""
        from app.services.voltage_group_config_service import set_manual_voltage_reference
        from app.domain.voltage_reference import LINE_TO_LINE
        group = self._make_voltage_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO,
        ))
        result = set_manual_voltage_reference(
            workspace_id="ws1", measurement_group_id="vg1",
            reference=LINE_TO_LINE,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_AUTO

    def test_return_voltage_reference_to_auto_does_not_change_authority(self):
        """Reference reset must NOT touch base_authority."""
        from app.services.voltage_group_config_service import return_voltage_reference_to_auto
        group = self._make_voltage_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_MANUAL,
        ))
        result = return_voltage_reference_to_auto(
            workspace_id="ws1", measurement_group_id="vg1",
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL


class TestCurrentServiceAuthorityTransitions:

    def _make_current_group(self, workspace_id: str = "ws1", group_id: str = "cg1") -> MeasurementGroup:
        return MeasurementGroup(
            id=group_id, workspace_id=workspace_id, source_id="src1",
            kind=KIND_CURRENT, status=STATUS_CONFIRMED, display_name="HV Current",
            channel_refs=[],
        )

    def _make_voltage_group(self, workspace_id: str = "ws1", group_id: str = "vg1") -> MeasurementGroup:
        return MeasurementGroup(
            id=group_id, workspace_id=workspace_id, source_id="src1",
            kind=KIND_VOLTAGE, status=STATUS_CONFIRMED, display_name="275KV Group",
            channel_refs=[],
        )

    def test_set_current_base_manual_sets_authority(self):
        from app.services.current_group_config_service import set_current_base_manual
        group = self._make_current_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        cur_reg = CurrentGroupConfigRegistry()
        result = set_current_base_manual(
            workspace_id="ws1", measurement_group_id="cg1",
            manual_ibase_ka=1.0,
            group_registry=group_reg, current_config_registry=cur_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_set_current_base_equipment_rating_sets_authority(self):
        from app.services.current_group_config_service import set_current_base_equipment_rating
        group = self._make_current_group()
        vgroup = self._make_voltage_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        group_reg.add(vgroup)
        cur_reg = CurrentGroupConfigRegistry()
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1", nominal_voltage_ll_kv=275.0,
        ))
        result = set_current_base_equipment_rating(
            workspace_id="ws1", measurement_group_id="cg1",
            equipment_rating_mva=100.0,
            linked_voltage_group_id="vg1",
            group_registry=group_reg,
            current_config_registry=cur_reg,
            voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_set_current_base_none_sets_authority(self):
        """set_current_base_none() is an explicit engineer choice → manual authority."""
        from app.services.current_group_config_service import set_current_base_none
        group = self._make_current_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        cur_reg = CurrentGroupConfigRegistry()
        result = set_current_base_none(
            workspace_id="ws1", measurement_group_id="cg1",
            group_registry=group_reg, current_config_registry=cur_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_set_current_base_manual_overwrites_legacy_authority(self):
        """An existing legacy_manual config transitions to manual on a new engineer action."""
        from app.services.current_group_config_service import set_current_base_manual
        group = self._make_current_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        cur_reg = CurrentGroupConfigRegistry()
        cur_reg.upsert(CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_MANUAL, manual_ibase_ka=0.5,
            base_authority=BASE_AUTHORITY_LEGACY,
        ))
        result = set_current_base_manual(
            workspace_id="ws1", measurement_group_id="cg1",
            manual_ibase_ka=1.0,
            group_registry=group_reg, current_config_registry=cur_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL


# ---------------------------------------------------------------------------
# Downstream reason codes
# ---------------------------------------------------------------------------

class TestDownstreamReasonCodes:

    def test_per_unit_provenance_has_base_invalidated_copy(self):
        """per_unit_provenance_service must have base_invalidated copy text."""
        import app.services.per_unit_provenance_service as prov
        source = inspect.getsource(prov)
        assert '"base_invalidated"' in source or "'base_invalidated'" in source

    def test_compliance_series_handles_base_invalidated(self):
        """compliance_series must handle base_invalidated reason code."""
        import app.services.compliance_series as cs
        source = inspect.getsource(cs)
        assert "base_invalidated" in source


# ---------------------------------------------------------------------------
# AUTHORITATIVE_GROUP_STATUSES constant reuse
# ---------------------------------------------------------------------------

class TestAuthoritativeGroupStatusesConstant:

    def test_calculated_current_per_unit_uses_domain_constant(self):
        """The inline tuple ('confirmed', 'manual') must have been replaced
        with AUTHORITATIVE_GROUP_STATUSES from app.domain.current_group_config."""
        import app.services.calculated_current_per_unit as calc
        source = inspect.getsource(calc)
        # Confirm the domain constant is imported
        assert "AUTHORITATIVE_GROUP_STATUSES" in source
        # Confirm no raw inline tuple for group status check
        assert '"confirmed", "manual"' not in source
        assert "'confirmed', 'manual'" not in source

    def test_voltage_and_current_authoritative_statuses_agree(self):
        """Both modules export the same two-element tuple."""
        assert set(VOLTAGE_AUTHORITATIVE_GROUP_STATUSES) == set(CURRENT_AUTHORITATIVE_GROUP_STATUSES)
        assert len(VOLTAGE_AUTHORITATIVE_GROUP_STATUSES) == 2
        assert len(CURRENT_AUTHORITATIVE_GROUP_STATUSES) == 2


# ---------------------------------------------------------------------------
# Scope guard — no automatic PU activation
# ---------------------------------------------------------------------------

class TestScopeGuard:

    def test_base_authority_module_has_no_registry_imports(self):
        """base_authority.py must remain a pure-domain module."""
        import app.domain.base_authority as ba
        source = inspect.getsource(ba)
        assert "registry" not in source.lower()
        assert "app.services" not in source

    def test_no_automatic_import_in_resolvers(self):
        """The live resolvers must not trigger any automatic evidence collection."""
        import app.domain.voltage_group_config as vcfg
        import app.domain.current_group_config as ccfg
        for mod in (vcfg, ccfg):
            source = inspect.getsource(mod)
            assert "auto_base_evidence" not in source
            assert "auto_base_service" not in source

    def test_update_voltage_configuration_has_no_base_authority_parameter(self):
        """update_voltage_configuration() must NOT accept base_authority as a parameter.
        Authority is derived internally to prevent injection of automatic states.
        """
        import inspect as insp
        from app.services.voltage_group_config_service import update_voltage_configuration
        sig = insp.signature(update_voltage_configuration)
        assert "base_authority" not in sig.parameters, (
            "update_voltage_configuration must not expose base_authority as a parameter — "
            "it must derive authority internally to prevent client injection of auto_resolved."
        )


# ---------------------------------------------------------------------------
# 5C-1 Hardening: authority-transition invariants through update_voltage_configuration
# ---------------------------------------------------------------------------

class TestVoltageAuthorityHardening:
    """Hardening tests covering the mandatory invariant:
    An accepted nominal_voltage_ll_kv edit atomically establishes
    base_authority="manual", regardless of the previous authority state.
    """

    def _make_group(self, group_id: str = "vg1") -> MeasurementGroup:
        return MeasurementGroup(
            id=group_id, workspace_id="ws1", source_id="src1",
            kind=KIND_VOLTAGE, status=STATUS_CONFIRMED, display_name="275KV Group",
            channel_refs=[],
        )

    def _registries(self, group: MeasurementGroup, existing_config: VoltageBaseConfiguration | None = None):
        from app.services.measurement_group_registry import MeasurementGroupRegistry
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        if existing_config is not None:
            vol_reg.upsert(existing_config)
        return group_reg, vol_reg

    def test_nominal_edit_on_auto_resolved_transitions_to_manual(self):
        """Editing a previously auto_resolved Voltage via update_voltage_configuration
        (the same function the API endpoint calls) must transition to manual.
        """
        from app.services.voltage_group_config_service import update_voltage_configuration
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=132.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL
        assert result.nominal_voltage_ll_kv == 132.0

    def test_nominal_edit_on_unavailable_transitions_to_manual(self):
        """Correcting a previously unavailable base through update_voltage_configuration
        (the API path) transitions authority to manual.
        """
        from app.services.voltage_group_config_service import update_voltage_configuration
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_UNAVAILABLE,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=275.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_nominal_edit_on_needs_review_transitions_to_manual(self):
        """needs_review base corrected by engineer transitions to manual."""
        from app.services.voltage_group_config_service import update_voltage_configuration
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_NEEDS_REVIEW,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=275.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL

    def test_saving_unchanged_nominal_is_explicit_confirmation(self):
        """Saving the same nominal kV value constitutes explicit engineer confirmation
        and must set base_authority="manual" even if the value did not change.
        """
        from app.services.voltage_group_config_service import update_voltage_configuration
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=275.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL
        assert math.isclose(result.nominal_voltage_ll_kv, 275.0, rel_tol=1e-9)

    def test_reference_only_edit_does_not_change_auto_resolved_authority(self):
        """A reference-mode change (no nominal_voltage_ll_kv) must NOT change authority."""
        from app.services.voltage_group_config_service import update_voltage_configuration
        from app.domain.voltage_group_config import VOLTAGE_REFERENCE_MODE_MANUAL
        from app.domain.voltage_reference import LINE_TO_LINE
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL, reference_override=LINE_TO_LINE,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_AUTO

    def test_reference_only_edit_does_not_change_unavailable_authority(self):
        """Reference-only edit must not accidentally re-enable an invalidated base."""
        from app.services.voltage_group_config_service import update_voltage_configuration
        from app.domain.voltage_group_config import VOLTAGE_REFERENCE_MODE_AUTO
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_UNAVAILABLE,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            reference_mode=VOLTAGE_REFERENCE_MODE_AUTO,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_UNAVAILABLE

    def test_rejected_update_preserves_both_nominal_and_authority(self):
        """If the nominal update is rejected (invalid value), neither the nominal
        value nor the previous authority state must change — atomicity.
        """
        from app.services.voltage_group_config_service import update_voltage_configuration
        from app.services.errors import InvalidVoltageBaseValueError
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO,
        )
        group_reg, vol_reg = self._registries(group, existing)
        with pytest.raises(InvalidVoltageBaseValueError):
            update_voltage_configuration(
                workspace_id="ws1", measurement_group_id="vg1",
                nominal_voltage_ll_kv=-99.0,  # invalid
                group_registry=group_reg, voltage_config_registry=vol_reg,
            )
        # Registry must be unchanged
        stored = vol_reg.get("ws1", "vg1")
        assert stored is not None
        assert stored.base_authority == BASE_AUTHORITY_AUTO
        assert math.isclose(stored.nominal_voltage_ll_kv, 275.0, rel_tol=1e-9)

    def test_attempted_injection_of_auto_resolved_via_kwargs_raises_type_error(self):
        """update_voltage_configuration does not accept base_authority — passing it
        as a keyword argument raises TypeError.
        """
        from app.services.voltage_group_config_service import update_voltage_configuration
        from app.services.measurement_group_registry import MeasurementGroupRegistry
        group = self._make_group()
        group_reg = MeasurementGroupRegistry()
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        with pytest.raises(TypeError):
            update_voltage_configuration(
                workspace_id="ws1", measurement_group_id="vg1",
                nominal_voltage_ll_kv=275.0,
                base_authority=BASE_AUTHORITY_AUTO,  # must be rejected
                group_registry=group_reg, voltage_config_registry=vol_reg,
            )

    def test_nominal_edit_on_legacy_manual_keeps_manual_authority(self):
        """Legacy configurations also transition to manual when explicitly edited."""
        from app.services.voltage_group_config_service import update_voltage_configuration
        group = self._make_group()
        existing = VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_LEGACY,
        )
        group_reg, vol_reg = self._registries(group, existing)
        result = update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="vg1",
            nominal_voltage_ll_kv=132.0,
            group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result.base_authority == BASE_AUTHORITY_MANUAL


# ---------------------------------------------------------------------------
# 5C-1 Hardening: existing Current paths unchanged
# ---------------------------------------------------------------------------

class TestCurrentHardeningAndLegacyCompatibility:
    """Existing Current and legacy configurations must not be affected by Slice 5C-1."""

    def _make_current_group(self, group_id: str = "cg1") -> MeasurementGroup:
        return MeasurementGroup(
            id=group_id, workspace_id="ws1", source_id="src1",
            kind=KIND_CURRENT, status=STATUS_CONFIRMED, display_name="HV Current",
            channel_refs=[],
        )

    def _make_voltage_group(self, group_id: str = "vg1") -> MeasurementGroup:
        return MeasurementGroup(
            id=group_id, workspace_id="ws1", source_id="src1",
            kind=KIND_VOLTAGE, status=STATUS_CONFIRMED, display_name="275KV Group",
            channel_refs=[],
        )

    def test_current_equipment_rating_with_legacy_authority_still_resolves(self):
        """Existing equipment-rating current configs with legacy_manual authority resolve."""
        group = self._make_current_group()
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=100.0, manual_voltage_base_kv=132.0,
            base_authority=BASE_AUTHORITY_LEGACY,
        )
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED
        expected = 100.0 / (SQRT_3 * 132.0)
        assert math.isclose(result.ibase_ka, expected, rel_tol=1e-9)

    def test_current_manual_with_legacy_authority_still_resolves(self):
        """Existing manual current configs with legacy_manual authority resolve."""
        group = self._make_current_group()
        cfg = _iconfig(manual_ibase_ka=0.5, base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED
        assert math.isclose(result.ibase_ka, 0.5, rel_tol=1e-9)

    def test_voltage_legacy_manual_resolves_ll(self):
        """Existing voltage config with legacy authority resolves L-L correctly."""
        group = _vgroup(STATUS_CONFIRMED, channel_names=("VRY", "VYB"))
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_LEGACY)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert math.isclose(result.denominator_kv, 275.0, rel_tol=1e-9)

    def test_source_default_path_unaffected(self):
        """Source-default (legacy per_unit path) is not affected by the authority gate.
        The gate is only in the GROUP-AWARE resolvers."""
        from app.domain.per_unit import resolve_per_unit
        from app.domain.channel_classification import CURRENT
        resolution = resolve_per_unit(CURRENT, None, [])
        # Should still produce base_required (no source config) — not an error
        assert resolution is not None

    def test_concurrent_registry_updates_are_safe(self):
        """Registry update_fields acquires a lock — concurrent edits do not corrupt state."""
        import threading
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(VoltageBaseConfiguration(
            measurement_group_id="vg1", workspace_id="ws1",
            nominal_voltage_ll_kv=100.0, base_authority=BASE_AUTHORITY_AUTO,
        ))
        errors = []
        def edit(value: float) -> None:
            try:
                vol_reg.update_fields("ws1", "vg1",
                    nominal_voltage_ll_kv=value,
                    base_authority=BASE_AUTHORITY_MANUAL,
                )
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=edit, args=(float(i * 10),)) for i in range(1, 6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Concurrent updates raised: {errors}"
        final = vol_reg.get("ws1", "vg1")
        assert final is not None
        assert final.base_authority == BASE_AUTHORITY_MANUAL
