"""D5A-1: CT/VT lookup from Recording Details Measurement Groups, and the
independent measurement-side contract, for protection analyses.

Expected values are derived by hand from the configured ratios (primary / secondary),
never from the resolver under test. Nothing here converts samples.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.source import ActiveSource, AnalogChannelSummary
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.protection_instrument_context import (
    RATIO_CONFIGURED,
    RATIO_CONFLICT,
    RATIO_INVALID,
    RATIO_NO_CHANNELS,
    RATIO_NO_GROUP,
    RATIO_NOT_CONFIGURED,
    RATIO_UNTRUSTED_AUTHORITY,
    SIDE_DECLARED,
    SIDE_MIXED,
    SIDE_UNKNOWN,
    resolve_protection_instrument_context,
    resolve_transformer_context,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_per_unit_coverage_service import SOURCE, WORKSPACE, _active_source

WS = WORKSPACE
SRC = SOURCE


def _ch(name: str, engineering_type: str, side: str = "unknown") -> AnalogChannelSummary:
    return AnalogChannelSummary(
        name=name, index=0, unit="V" if engineering_type == VOLTAGE else "A",
        engineering_type=engineering_type, measurement_side=side,
    )


def _ref(name: str, src: str = SRC) -> ChannelRef:
    return ChannelRef(kind="source", source_id=src, channel_name=name)


class Env:
    def __init__(self) -> None:
        self.sources = WorkspaceRegistry()
        self.groups = MeasurementGroupRegistry()
        self.vcfg = VoltageGroupConfigRegistry()
        self.ccfg = CurrentGroupConfigRegistry()

    def add_source(self, channels, *, src: str = SRC, ws: str = WS) -> None:
        base = _active_source(channels)
        self.sources.add(ActiveSource(metadata=replace(base.metadata, source_id=src, workspace_id=ws), record=base.record))

    def add_group(self, group_id: str, kind: str, names, *, src: str = SRC, ws: str = WS) -> None:
        self.groups.add(MeasurementGroup(
            id=group_id, workspace_id=ws, source_id=src, kind=kind, display_name=group_id,
            channel_refs=[_ref(n, src) for n in names], status=STATUS_CONFIRMED,
        ))

    def set_vt(self, group_id: str, primary, secondary, authority: str = "manual", ws: str = WS) -> None:
        self.vcfg.update_fields(ws, group_id, vt_primary_v=primary, vt_secondary_v=secondary,
                                vt_authority=authority, update_vt=True)

    def set_ct(self, group_id: str, primary, secondary, authority: str = "manual", ws: str = WS) -> None:
        self.ccfg.update_fields(ws, group_id, ct_primary_a=primary, ct_secondary_a=secondary,
                                ct_authority=authority, update_ct=True)

    def ctx(self, voltage, current, ws: str = WS):
        return resolve_protection_instrument_context(
            ws, voltage_refs=voltage, current_refs=current, group_registry=self.groups,
            voltage_config_registry=self.vcfg, current_config_registry=self.ccfg, source_registry=self.sources,
        )

    def one(self, refs, quantity: str, ws: str = WS):
        return resolve_transformer_context(
            ws, refs, quantity, group_registry=self.groups, voltage_config_registry=self.vcfg,
            current_config_registry=self.ccfg, source_registry=self.sources,
        )


@pytest.fixture
def env() -> Env:
    e = Env()
    e.add_source([_ch(n, VOLTAGE) for n in ("VR", "VY", "VB", "VR2")] + [_ch(n, CURRENT) for n in ("IR", "IY", "IB", "IR2")])
    return e


# --- 1/2: CT and VT come from the correct Measurement Group -------------------------------------


def test_ct_ratio_comes_from_the_owning_current_group(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR", "IY"])
    env.add_group("ig-2", KIND_CURRENT, ["IB", "IR2"])
    env.set_ct("ig-1", 1200.0, 5.0)     # 240
    env.set_ct("ig-2", 2000.0, 1.0)     # 2000
    first = env.one([_ref("IR"), _ref("IY")], "current")
    second = env.one([_ref("IB"), _ref("IR2")], "current")
    assert (first.ratio_status, first.group_ids, first.primary, first.secondary, first.ratio) == (
        RATIO_CONFIGURED, ("ig-1",), 1200.0, 5.0, 240.0)
    assert (second.group_ids, second.ratio) == (("ig-2",), 2000.0)


def test_vt_ratio_comes_from_the_owning_voltage_group(env):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR", "VY"])
    env.add_group("vg-2", KIND_VOLTAGE, ["VB", "VR2"])
    env.set_vt("vg-1", 132000.0, 110.0)  # 1200
    env.set_vt("vg-2", 275000.0, 110.0)  # 2500
    assert env.one([_ref("VR")], "voltage").ratio == pytest.approx(1200.0)
    assert env.one([_ref("VB")], "voltage").ratio == pytest.approx(2500.0)


def test_same_ratio_expressed_differently_across_groups_is_consistent(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.add_group("ig-2", KIND_CURRENT, ["IY"])
    env.set_ct("ig-1", 1200.0, 5.0)
    env.set_ct("ig-2", 240.0, 1.0)       # also 240
    got = env.one([_ref("IR"), _ref("IY")], "current")
    assert got.ratio_status == RATIO_CONFIGURED and got.ratio == pytest.approx(240.0)
    assert got.group_ids == ("ig-1", "ig-2")


def test_phases_in_groups_with_different_ratios_conflict(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.add_group("ig-2", KIND_CURRENT, ["IY"])
    env.set_ct("ig-1", 1200.0, 5.0)
    env.set_ct("ig-2", 2000.0, 1.0)
    got = env.one([_ref("IR"), _ref("IY")], "current")
    assert got.ratio_status == RATIO_CONFLICT and got.ratio is None and not got.ratio_consumable


# --- 3: isolation across sources and workspaces -------------------------------------------------


def test_same_channel_names_in_two_sources_resolve_independently(env):
    env.add_source([_ch("IR", CURRENT)], src="src-2")
    env.add_group("ig-a", KIND_CURRENT, ["IR"], src=SRC)
    env.add_group("ig-b", KIND_CURRENT, ["IR"], src="src-2")
    env.set_ct("ig-a", 1200.0, 5.0)
    env.set_ct("ig-b", 600.0, 5.0)
    assert env.one([_ref("IR", SRC)], "current").ratio == pytest.approx(240.0)
    assert env.one([_ref("IR", "src-2")], "current").ratio == pytest.approx(120.0)


def test_configuration_never_leaks_across_workspaces(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.set_ct("ig-1", 1200.0, 5.0)
    assert env.one([_ref("IR")], "current").ratio_consumable
    other = env.one([_ref("IR")], "current", ws="ws-OTHER")
    assert other.ratio_status == RATIO_NO_GROUP and other.ratio is None


# --- 4: missing / unusable configuration ----------------------------------------------------------


def test_channel_outside_any_group_has_no_ratio(env):
    assert env.one([_ref("IR")], "current").ratio_status == RATIO_NO_GROUP


def test_group_without_configuration_is_not_configured(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    got = env.one([_ref("IR")], "current")
    assert got.ratio_status == RATIO_NOT_CONFIGURED and got.ratio is None


def test_nominal_voltage_alone_yields_a_consumable_auto_derived_vt(env):
    """Owner decision (2026-11-21): the nominal-derived VT (nominal kV / 110 V) is valid engineering
    configuration, needs no confirmation, and keeps its own `auto_nominal` provenance."""
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.vcfg.update_fields(WS, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    got = env.one([_ref("VR")], "voltage")
    assert got.ratio_status == RATIO_CONFIGURED and got.ratio_consumable
    assert (got.primary, got.secondary, got.ratio) == (132000.0, 110.0, 1200.0)
    assert got.authority == "auto_nominal" and got.authority not in ("manual", "recording_metadata")
    assert got.provenance_note == "Auto-derived from nominal voltage 132 kV; secondary 110 V default"
    assert got.nominal_ll_kv == 132.0 and got.nominal_refused_reason is None


def test_a_stored_vt_always_takes_precedence_over_the_nominal(env):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.vcfg.update_fields(WS, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    env.set_vt("vg-1", 33000.0, 110.0, authority="manual")
    got = env.one([_ref("VR")], "voltage")
    assert (got.primary, got.secondary, got.authority) == (33000.0, 110.0, "manual")
    env.set_vt("vg-1", 11000.0, 110.0, authority="recording_metadata")
    assert env.one([_ref("VR")], "voltage").authority == "recording_metadata"


def test_changing_the_nominal_refreshes_the_derived_vt(env):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.vcfg.update_fields(WS, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    assert env.one([_ref("VR")], "voltage").primary == 132000.0
    env.vcfg.update_fields(WS, "vg-1", nominal_voltage_ll_kv=275.0, update_nominal=True)
    assert env.one([_ref("VR")], "voltage").primary == 275000.0


def test_the_nominal_derivation_is_refused_when_the_nominal_is_not_accepted(env):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.vcfg.update_fields(WS, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    config = env.vcfg.get(WS, "vg-1")
    config.manual_conflict_detected = True
    env.vcfg.upsert(config)
    got = env.one([_ref("VR")], "voltage")
    assert got.ratio_status == RATIO_NOT_CONFIGURED and got.ratio is None and got.primary is None
    assert (got.nominal_ll_kv, got.nominal_refused_reason) == (132.0, "manual_conflict")


def test_a_ct_is_never_derived_from_equipment_rating_or_capacity(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.ccfg.update_fields(WS, "ig-1", equipment_mva=100.0, equipment_linked_voltage_group_id=None, update_equipment=True)
    got = env.one([_ref("IR")], "current")
    assert got.ratio_status == RATIO_NOT_CONFIGURED and got.primary is None and got.nominal_ll_kv is None


@pytest.mark.parametrize("authority", ["auto_nominal", "assumed_default", "garbage"])
def test_unrecognised_authority_is_not_consumable(env, authority):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.set_vt("vg-1", 132000.0, 110.0, authority=authority)
    got = env.one([_ref("VR")], "voltage")
    assert got.ratio_status == RATIO_UNTRUSTED_AUTHORITY and got.ratio is None


def test_recording_metadata_authority_is_consumable(env):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.set_ct("ig-1", 800.0, 1.0, authority="recording_metadata")
    assert env.one([_ref("IR")], "current").ratio == pytest.approx(800.0)


@pytest.mark.parametrize("primary,secondary", [(1200.0, 0.0), (0.0, 5.0), (-1200.0, 5.0), (float("nan"), 5.0), (1200.0, None)])
def test_invalid_pair_is_rejected(env, primary, secondary):
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.set_ct("ig-1", primary, secondary)
    got = env.one([_ref("IR")], "current")
    assert got.ratio_status == RATIO_INVALID and got.ratio is None


def test_a_current_channel_is_not_resolved_through_a_voltage_group(env):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.set_vt("vg-1", 132000.0, 110.0)
    assert env.one([_ref("VR")], "current").ratio_status == RATIO_NO_GROUP


def test_calculated_channel_has_no_group_and_unknown_side(env):
    got = env.one([ChannelRef(kind="calculated", calculated_channel_id="calc-1")], "current")
    assert (got.ratio_status, got.side, got.side_status) == (RATIO_NO_GROUP, "unknown", SIDE_UNKNOWN)


def test_no_channels_resolved(env):
    assert env.one([], "voltage").ratio_status == RATIO_NO_CHANNELS


# --- 5/6/7/8: measurement side is recording-declared, independent, never inferred ----------------


@pytest.mark.parametrize("side", ["primary", "secondary"])
def test_declared_side_is_reported_and_proposed_as_the_basis(env, side):
    env.add_source([_ch("IR", CURRENT, side), _ch("IY", CURRENT, side)], src="src-2")
    got = env.one([_ref("IR", "src-2"), _ref("IY", "src-2")], "current")
    assert (got.side, got.side_status, got.declared_basis) == (side, SIDE_DECLARED, side)


def test_a_configured_ratio_is_not_evidence_of_the_side(env):
    """CT configured, recording side unknown: ratio is consumable but no basis is proposed."""
    env.add_group("ig-1", KIND_CURRENT, ["IR", "IY"])
    env.set_ct("ig-1", 1200.0, 5.0)
    got = env.one([_ref("IR"), _ref("IY")], "current")
    assert got.ratio_consumable is True
    assert (got.side, got.side_status, got.declared_basis) == ("unknown", SIDE_UNKNOWN, None)


def test_mixed_sides_within_one_quantity_propose_no_basis(env):
    env.add_source([_ch("IR", CURRENT, "primary"), _ch("IY", CURRENT, "secondary")], src="src-2")
    got = env.one([_ref("IR", "src-2"), _ref("IY", "src-2")], "current")
    assert (got.side, got.side_status, got.declared_basis) == ("unknown", SIDE_MIXED, None)


def test_one_unknown_channel_makes_the_quantity_unknown(env):
    env.add_source([_ch("IR", CURRENT, "primary"), _ch("IY", CURRENT, "unknown")], src="src-2")
    assert env.one([_ref("IR", "src-2"), _ref("IY", "src-2")], "current").declared_basis is None


def test_voltage_and_current_sides_are_independent(env):
    env.add_source([_ch("VR", VOLTAGE, "primary"), _ch("IR", CURRENT, "secondary")], src="src-2")
    both = env.ctx([_ref("VR", "src-2")], [_ref("IR", "src-2")])
    assert both.voltage.declared_basis == "primary"
    assert both.current.declared_basis == "secondary"


def test_unknown_voltage_side_does_not_affect_a_declared_current_side(env):
    env.add_source([_ch("VR", VOLTAGE, "unknown"), _ch("IR", CURRENT, "primary")], src="src-2")
    both = env.ctx([_ref("VR", "src-2")], [_ref("IR", "src-2")])
    assert both.voltage.declared_basis is None and both.current.declared_basis == "primary"


def test_missing_source_leaves_side_unknown(env):
    assert env.one([_ref("IR", "src-missing")], "current").declared_basis is None


def test_side_and_ratio_are_resolved_independently_in_the_combined_context(env):
    env.add_group("vg-1", KIND_VOLTAGE, ["VR"])
    env.add_group("ig-1", KIND_CURRENT, ["IR"])
    env.set_vt("vg-1", 132000.0, 110.0)
    env.set_ct("ig-1", 1200.0, 5.0)
    both = env.ctx([_ref("VR")], [_ref("IR")])
    assert both.voltage.ratio == pytest.approx(1200.0) and both.current.ratio == pytest.approx(240.0)
    assert both.voltage.declared_basis is None and both.current.declared_basis is None
