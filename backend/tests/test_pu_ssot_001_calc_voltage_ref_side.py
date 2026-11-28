"""PU-SSOT-001 Finding-3 regression suite.

Verifies that _resolve_effective_per_unit_for_calculated_channel() selects
the authoritative base_reference_side for group-aware Voltage calculated
channels from the Voltage Measurement Group config (DEC-050), not from the
Source Default profile (DEC-049).  The fix mirrors the identical logic that
waveform_service._resolve_effective_per_unit() already applies for source
channels.

Tests do NOT use a TestClient: they call the dispatch function directly with
registries constructed in-process, so calibration-authority status is
transparent (COMTRADE source, no calibration_authority set → not-assessed →
eligible, matches the existing gate behaviour for all COMTRADE recordings).

Numerical invariants (base_amount, base_unit) are verified to be UNCHANGED
by the fix -- the correction only touches reference_compatibility metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.domain.calculated_channel import (
    OP_REVERSE_POLARITY,
    CalculatedChannel,
    ChannelRef,
)
from app.domain.channel_classification import VOLTAGE
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.per_unit import PerUnitBaseProfile, STATUS_BASE_REQUIRED, STATUS_CONFIGURED
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import _resolve_effective_per_unit_for_calculated_channel
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import update_voltage_configuration
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_per_unit_coverage_service import SOURCE, WORKSPACE, _active_source, _channel

SQRT_3 = 1.7320508075688772
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------


def _mg(group_id: str = "mg-v1") -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id=WORKSPACE, source_id=SOURCE,
        kind=KIND_VOLTAGE, display_name="V Group",
        channel_refs=[ChannelRef(kind="source", source_id=SOURCE, channel_name=n) for n in ("VR", "VY", "VB")],
        status=STATUS_CONFIRMED,
    )


def _unary_voltage_calc(calc_id: str = "calc-1") -> CalculatedChannel:
    n = 4
    return CalculatedChannel(
        id=calc_id, workspace_id=WORKSPACE, name=calc_id, unit="V",
        operation=OP_REVERSE_POLARITY,
        inputs=[ChannelRef(kind="source", source_id=SOURCE, channel_name="VR")],
        parameters={}, dependency_ids=[],
        reference_source_id=SOURCE,
        time=np.arange(n, dtype=float), values=np.ones(n, dtype=float),
        created_at=_NOW, engineering_type=VOLTAGE,
    )


def _sd_profile(*, voltage_base_reference_side: str = "unknown") -> PerUnitBaseProfile:
    """Source Default profile for SOURCE.  Voltage base 275 kV L-L (auto)."""
    return PerUnitBaseProfile(
        source_id=SOURCE, workspace_id=WORKSPACE,
        voltage_base_value=275.0, voltage_reference_mode="auto",
        voltage_reference_override=None, current_base_mode="direct",
        apparent_power_base_value=None, direct_current_base_value=2.0,
        voltage_base_reference_side=voltage_base_reference_side,
    )


def _base_registries() -> tuple:
    """Return (source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry)."""
    source_registry = WorkspaceRegistry()
    source = _active_source([_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)])
    source_registry.add(source)

    group_registry = MeasurementGroupRegistry()
    group_registry.add(_mg())

    voltage_config_registry = VoltageGroupConfigRegistry()
    current_config_registry = CurrentGroupConfigRegistry()
    calc_registry = CalculatedChannelRegistry()
    calc_registry.add(_unary_voltage_calc())
    return source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry


def _resolve(
    channel,
    per_unit_profile,
    *,
    source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry,
):
    return _resolve_effective_per_unit_for_calculated_channel(
        channel, per_unit_profile, ["VR", "VY", "VB"],
        workspace_id=WORKSPACE,
        source_registry=source_registry,
        calc_registry=calc_registry,
        group_registry=group_registry,
        voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
        per_unit_registry=None,
    )


# ---------------------------------------------------------------------------
# PU-SSOT-001 F3: group-aware Voltage uses MG voltage config authority
# ---------------------------------------------------------------------------


class TestGroupAwareVoltageReferenceAuthority:
    """The core fix: voltage_group_config is passed to apply_source_reference()
    for group-aware Voltage calculated channels, mirroring waveform_service."""

    def test_mg_primary_side_takes_priority_over_sd_secondary_profile(self):
        """Before fix: base_reference_side was 'secondary' (from SD profile).
        After fix:  base_reference_side is  'primary' (from MG voltage config).

        This is the canonical SSOT-8 scenario: MG and SD profile disagree.
        """
        source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        update_voltage_configuration(
            workspace_id=WORKSPACE, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=275.0, base_reference_side="primary",
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        profile = _sd_profile(voltage_base_reference_side="secondary")
        result = _resolve(
            _unary_voltage_calc(), profile,
            source_registry=source_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_CONFIGURED
        # MG voltage config's base_reference_side ("primary") wins, not SD profile's ("secondary").
        assert result.base_reference_side == "primary"
        assert result.reference_compatibility == "unverified"  # measurement_side is always "unknown" for calc channels

    def test_mg_secondary_side_takes_priority_over_sd_primary_profile(self):
        """Mirror of the above with the sides reversed.

        Secondary base_reference_side requires secondary_voltage_ll_v (Slice
        5D-1 safety rule): supply 1 kV LL secondary equivalent so the resolver
        can compute a valid denominator and reach STATUS_CONFIGURED.
        """
        source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        update_voltage_configuration(
            workspace_id=WORKSPACE, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=275.0, base_reference_side="secondary",
            secondary_voltage_ll_v=1000.0,  # 1 kV LL secondary (Slice 5D-1 requirement)
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        profile = _sd_profile(voltage_base_reference_side="primary")
        result = _resolve(
            _unary_voltage_calc(), profile,
            source_registry=source_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_CONFIGURED
        assert result.base_reference_side == "secondary"
        assert result.reference_compatibility == "unverified"

    def test_mg_unknown_side_is_reported_even_when_sd_has_explicit_side(self):
        """When MG's voltage config has base_reference_side='unknown' (the
        default), the resolution reports 'unknown' — not the SD profile's
        explicit side.  This confirms the MG config is the authority for
        all group-aware channels, even when its own side is unspecified."""
        source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        # set_voltage_base uses default base_reference_side="unknown"
        update_voltage_configuration(
            workspace_id=WORKSPACE, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        profile = _sd_profile(voltage_base_reference_side="primary")
        result = _resolve(
            _unary_voltage_calc(), profile,
            source_registry=source_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_CONFIGURED
        assert result.base_reference_side == "unknown"  # MG's unknown, not SD's "primary"
        assert result.reference_compatibility == "unverified"


# ---------------------------------------------------------------------------
# Source Default fallback path is preserved
# ---------------------------------------------------------------------------


class TestSourceDefaultFallbackReferencePreserved:
    """Channels without a Measurement Group fall through to DEC-049.
    The fix must not change the reference-side authority for this path."""

    def test_ungrouped_channel_uses_sd_profile_reference_side(self):
        """No MG → resolve_per_unit() runs → profile_id == profile.source_id →
        _voltage_group_config lookup is skipped → SD profile's side used."""
        source_registry, _, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        # Provide an empty group registry so no MG exists for this channel
        empty_group_registry = MeasurementGroupRegistry()
        profile = _sd_profile(voltage_base_reference_side="primary")
        channel = _unary_voltage_calc()
        result = _resolve(
            channel, profile,
            source_registry=source_registry, group_registry=empty_group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_CONFIGURED
        assert result.base_reference_side == "primary"  # from SD profile

    def test_no_sd_no_mg_reports_base_required(self):
        """No MG, no SD profile → base_required; no crash, no incompatible."""
        source_registry, _, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        empty_group_registry = MeasurementGroupRegistry()
        result = _resolve(
            _unary_voltage_calc(), None,
            source_registry=source_registry, group_registry=empty_group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_BASE_REQUIRED

    def test_sd_profile_reference_side_unknown_resolves_unverified(self):
        """SD path with unknown side: reference_compatibility is 'unverified'."""
        source_registry, _, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        empty_group_registry = MeasurementGroupRegistry()
        profile = _sd_profile(voltage_base_reference_side="unknown")
        result = _resolve(
            _unary_voltage_calc(), profile,
            source_registry=source_registry, group_registry=empty_group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_CONFIGURED
        assert result.reference_compatibility == "unverified"


# ---------------------------------------------------------------------------
# Numerical invariants: base_amount and base_unit unchanged
# ---------------------------------------------------------------------------


class TestNumericalInvariantsPreserved:
    """The fix only changes reference_compatibility metadata.  base_amount,
    base_unit, and status (CONFIGURED/BASE_REQUIRED) must be identical to what
    resolve_calculated_group_aware_per_unit() alone produces."""

    def test_base_amount_unchanged_by_reference_side_fix(self):
        """275 kV LL, 3-phase LG-detected: base = 275/sqrt(3) kV in volts."""
        source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        update_voltage_configuration(
            workspace_id=WORKSPACE, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=275.0, base_reference_side="primary",
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        profile = _sd_profile(voltage_base_reference_side="secondary")
        result = _resolve(
            _unary_voltage_calc(), profile,
            source_registry=source_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_CONFIGURED
        assert result.base_unit == "V"
        # VR is detected as LG: denominator = nominal_LL / sqrt(3), in volts.
        expected = (275.0 / SQRT_3) * 1000.0
        assert result.base_amount == pytest.approx(expected, rel=1e-6)

    def test_unconfigured_mg_is_base_required_regardless_of_sd_profile(self):
        """Group-aware path with no voltage config → base_required.
        The reference side is irrelevant; the status must not become configured."""
        source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry = _base_registries()
        # Deliberately do NOT configure the voltage base on mg-v1
        profile = _sd_profile(voltage_base_reference_side="primary")
        result = _resolve(
            _unary_voltage_calc(), profile,
            source_registry=source_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
        )
        # group-aware path gives base_required (group exists but unconfigured)
        assert result.status == STATUS_BASE_REQUIRED
        # The fix must not turn this into an incompatible block; base_required is correct.
        assert result.reference_compatibility != "incompatible"
