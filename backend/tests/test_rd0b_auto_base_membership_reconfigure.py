"""RD-0B regression tests — automatic voltage-base recalculation after
Measurement Group membership changes.

Covers the 10 scenarios specified in the RD-0B task:

  1.  Auto-resolved 132 kV → auto-resolved 275 kV (membership replaced)
  2.  Auto-resolved 132 kV → remains 132 kV (evidence still supports 132 kV)
  3.  Auto-resolved → conflicting evidence
  4.  Auto-resolved → insufficient evidence (no voltage channels)
  5.  Manual base → membership edit (manual base preserved, C4)
  6.  Unrelated group remains unchanged after a sibling group is edited
  7.  PU eligibility removed when automatic authority becomes unavailable
  8.  Existing waveform samples and engineering-unit values unchanged
  9.  Existing nominal-voltage detection behavior compatible (existing tests pass)
 10.  Repeated edits do not leave stale state

Root fix: ``update_group()`` in ``measurement_group_service`` now calls
``reconfigure_auto_base_after_membership_change()`` whenever ``channel_refs``
is replaced and a ``voltage_config_registry`` is provided.

``reconfigure_auto_base_after_membership_change()`` is also tested directly
in ``test_rd0b_reconfigure_function`` as a pure unit.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.voltage_group_config import (
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    VoltageBaseConfiguration,
    resolve_voltage_base_for_group,
)
from app.services.auto_base_service import reconfigure_auto_base_after_membership_change
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_service import update_group
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

WS = "ws-rdb0"
SRC = "src-rdb0"


def _channel(name: str, etype: str, unit: str = "kV", primary_ratio: float | None = None) -> AnalogChannelSummary:
    # measurement_side="primary" so the auto-base evidence pipeline can resolve
    # without PS-flag data from an imported file.
    return AnalogChannelSummary(
        name=name, index=0, unit=unit, engineering_type=etype,
        measurement_side="primary",
        primary_ratio=primary_ratio,
    )


def _make_source_registry(channels: list[AnalogChannelSummary]) -> WorkspaceRegistry:
    now = datetime.now(timezone.utc)
    col_names = ["time"] + [ch.name for ch in channels]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="S", recorder_name="R", source_file="f.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({c: [0.0] for c in col_names}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[1]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )
    metadata = SourceMetadata(
        source_id=SRC, workspace_id=WS, provider_type="COMTRADE",
        original_filenames=("f.cfg",), created_at=now,
        station_name="S", recorder_name="R", nominal_frequency=50.0,
        timing_reference="absolute", start_time=now, trigger_time=now,
        sample_count=1, duration_seconds=0.0, elapsed_start_seconds=0.0, elapsed_end_seconds=0.0,
        sampling_rates=(1.0,), samples_per_rate=(1,),
        analog_channels=channels, digital_channels=[],
    )
    active = ActiveSource(metadata=metadata, record=record)
    reg = WorkspaceRegistry()
    reg.add(active)
    return reg


def _make_group(group_id: str, channel_names: list[str], kind: str = KIND_VOLTAGE) -> MeasurementGroup:
    refs = [ChannelRef(kind="source", source_id=SRC, channel_name=n) for n in channel_names]
    return MeasurementGroup(
        id=group_id, workspace_id=WS, source_id=SRC,
        kind=kind, display_name=group_id,
        channel_refs=refs, status=STATUS_SUGGESTED,
    )


def _vconfig(group_id: str, nominal_kv: float, authority: str = BASE_AUTHORITY_AUTO) -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(
        measurement_group_id=group_id, workspace_id=WS,
        nominal_voltage_ll_kv=nominal_kv,
        base_reference_side="primary",
        base_authority=authority,
    )


def _refs(names: list[str]) -> list[ChannelRef]:
    return [ChannelRef(kind="source", source_id=SRC, channel_name=n) for n in names]


# ---------------------------------------------------------------------------
# Channel name conventions used in these tests
#
# detect_voltage_reference() classifies channel names by trailing phase token:
#   L-L: ends with V+{RY,YB,BR,AB,BC,CA,...}  e.g. "VRY", "HV_VYB"
#   L-G: ends with V+{R,Y,B,A,C}              e.g. "VR", "BUS_VB"
#
# primary_ratio drives nominal kV detection.  For auto_resolved to succeed:
#   - channel_reference must resolve (channel names must carry phase tokens)
#   - ≥1 high/medium candidate at or above _MIN_NOMINAL_LL_KV
#   - all candidates consistent (no contradictions)
#
# We use:
#   L-L 132 kV group: HV132_VRY, HV132_VYB, HV132_VBR  (primary_ratio=132.0)
#   L-L 275 kV group: HV275_VRY, HV275_VYB, HV275_VBR  (primary_ratio=275.0)
#   L-G  33 kV group: BUS33_VR,  BUS33_VY,  BUS33_VB   (primary_ratio=33.0)
# ---------------------------------------------------------------------------

class TestScenario1_AutoResolved132To275:
    """When membership is replaced with channels carrying 275 kV evidence,
    the base must update to 275 kV with auto_resolved authority."""

    def test_base_updates_to_275kv_after_membership_change(self):
        ch_132 = [_channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
                  _channel("HV132_VYB", VOLTAGE, primary_ratio=132.0),
                  _channel("HV132_VBR", VOLTAGE, primary_ratio=132.0)]
        ch_275 = [_channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
                  _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
                  _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0)]
        all_channels = ch_132 + ch_275
        source_reg = _make_source_registry(all_channels)

        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["HV132_VRY", "HV132_VYB", "HV132_VBR"])
        group_reg.add(group)

        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["HV275_VRY", "HV275_VYB", "HV275_VBR"]),
            source_registry=source_reg,
            voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        assert config is not None
        assert config.base_authority == BASE_AUTHORITY_AUTO
        assert config.nominal_voltage_ll_kv == pytest.approx(275.0)

    def test_pu_remains_eligible_after_base_update(self):
        ch = [_channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
              _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
              _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["HV275_VRY", "HV275_VYB", "HV275_VBR"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["HV275_VRY", "HV275_VYB", "HV275_VBR"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        updated_group = group_reg.get(WS, "vg1")
        result = resolve_voltage_base_for_group(updated_group, config)
        assert result.status == STATUS_CONFIGURED
        assert result.denominator_kv == pytest.approx(275.0)


# ---------------------------------------------------------------------------
# Scenario 2 — auto-resolved 132 kV → remains 132 kV
# ---------------------------------------------------------------------------

class TestScenario2_SameBaseRemains:
    """When updated membership still supports 132 kV, authority stays auto_resolved
    and the base value is preserved."""

    def test_base_stays_132kv_when_evidence_unchanged(self):
        # L-L channels: prefix ensures phase token (VRY/VYB/VBR) ends the name.
        ch = [_channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
              _channel("HV132_VYB", VOLTAGE, primary_ratio=132.0),
              _channel("HV132_VBR", VOLTAGE, primary_ratio=132.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["HV132_VRY", "HV132_VYB", "HV132_VBR"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        # Remove one channel but evidence still resolves to 132 kV.
        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["HV132_VRY", "HV132_VYB"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        assert config is not None
        assert config.base_authority == BASE_AUTHORITY_AUTO
        assert config.nominal_voltage_ll_kv == pytest.approx(132.0)


# ---------------------------------------------------------------------------
# Scenario 3 — auto-resolved → conflicting evidence
# ---------------------------------------------------------------------------

class TestScenario3_ConflictingEvidence:
    """When updated membership contains contradictory voltage evidence,
    the authority must be downgraded to needs_review and PU blocked."""

    def test_needs_review_on_contradictory_channels(self):
        # Mix of 132 kV and 275 kV channels in the same group → conflict.
        ch = [_channel("VRY_132", VOLTAGE, primary_ratio=132.0),
              _channel("VRY_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VRY_132"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_132", "VRY_275"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        assert config is not None
        assert config.base_authority == BASE_AUTHORITY_NEEDS_REVIEW

    def test_pu_blocked_on_needs_review(self):
        ch = [_channel("VRY_132", VOLTAGE, primary_ratio=132.0),
              _channel("VRY_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VRY_132"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_132", "VRY_275"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        updated_group = group_reg.get(WS, "vg1")
        result = resolve_voltage_base_for_group(updated_group, config)
        assert result.status == STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"


# ---------------------------------------------------------------------------
# Scenario 4 — auto-resolved → insufficient evidence (no voltage channels)
# ---------------------------------------------------------------------------

class TestScenario4_InsufficientEvidence:
    """When updated channels have no voltage channels at all, the evidence
    is insufficient and the authority must not remain auto_resolved."""

    def test_needs_review_when_no_voltage_channels_after_edit(self):
        # Source has both voltage and current channels, but we move to current-only
        # members (which is actually invalid for a voltage group, so test the
        # scenario where channels have no primary_ratio / ambiguous evidence).
        ch = [_channel("VA_norat", VOLTAGE),  # no primary_ratio → low evidence
              _channel("VB_norat", VOLTAGE)]   # no primary_ratio
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VA_norat"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        # Previously auto-resolved (e.g. from name-based detection giving 132 kV)
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VA_norat", "VB_norat"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        assert config is not None
        # Insufficient evidence → needs_review, not auto_resolved.
        assert config.base_authority != BASE_AUTHORITY_AUTO


# ---------------------------------------------------------------------------
# Scenario 5 — manual base → membership edit (C4: manual preserved)
# ---------------------------------------------------------------------------

class TestScenario5_ManualBasePreserved:
    """An engineer-set base must never be overwritten by an automatic re-run (C4)."""

    def test_manual_base_preserved_after_membership_change(self):
        ch = [_channel("VRY_132", VOLTAGE, primary_ratio=132.0),
              _channel("VRY_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VRY_132"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        # Engineer manually set 400 kV (unusual, but it's their choice).
        vol_reg.upsert(_vconfig("vg1", 400.0, BASE_AUTHORITY_MANUAL))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_275"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        assert config is not None
        assert config.base_authority == BASE_AUTHORITY_MANUAL
        assert config.nominal_voltage_ll_kv == pytest.approx(400.0)

    def test_legacy_manual_base_preserved_after_membership_change(self):
        ch = [_channel("VRY_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VRY_275"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_LEGACY))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_275"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        assert config is not None
        assert config.base_authority == BASE_AUTHORITY_LEGACY
        assert config.nominal_voltage_ll_kv == pytest.approx(132.0)


# ---------------------------------------------------------------------------
# Scenario 6 — unrelated group remains unchanged
# ---------------------------------------------------------------------------

class TestScenario6_UnrelatedGroupUnchanged:
    """Editing one group must not affect any other group's config."""

    def test_sibling_group_config_unchanged(self):
        ch = [_channel("VRY_132", VOLTAGE, primary_ratio=132.0),
              _channel("VRY_275", VOLTAGE, primary_ratio=275.0),
              _channel("VR_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group1 = _make_group("vg1", ["VRY_132"])
        group2 = _make_group("vg2", ["VRY_275"])
        group_reg.add(group1)
        group_reg.add(group2)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))
        vol_reg.upsert(_vconfig("vg2", 275.0, BASE_AUTHORITY_AUTO))

        # Edit vg1 only.
        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_132"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config2 = vol_reg.get(WS, "vg2")
        assert config2 is not None
        assert config2.base_authority == BASE_AUTHORITY_AUTO
        assert config2.nominal_voltage_ll_kv == pytest.approx(275.0)


# ---------------------------------------------------------------------------
# Scenario 7 — PU eligibility removed when authority becomes unavailable
# ---------------------------------------------------------------------------

class TestScenario7_PuEligibilityRemoved:
    """After a membership change that produces needs_review authority,
    the resolver must return base_required, not configured."""

    def test_pu_base_required_after_needs_review_transition(self):
        # Group member with no primary_ratio → insufficient evidence.
        ch = [_channel("VA_norat", VOLTAGE),
              _channel("VB_norat", VOLTAGE)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VA_norat"])
        group.status = STATUS_SUGGESTED
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VA_norat", "VB_norat"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        config = vol_reg.get(WS, "vg1")
        updated_group = group_reg.get(WS, "vg1")
        result = resolve_voltage_base_for_group(updated_group, config)
        # Either base_invalidated (needs_review/unavailable) or base_not_configured.
        assert result.status == STATUS_BASE_REQUIRED


# ---------------------------------------------------------------------------
# Scenario 8 — Waveform samples and engineering-unit values unchanged
# ---------------------------------------------------------------------------

class TestScenario8_WaveformSamplesUnchanged:
    """The reconfiguration must never modify the source's waveform samples."""

    def test_waveform_data_identical_before_and_after_reconfiguration(self):
        ch = [_channel("VRY_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VRY_275"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        active_before = source_reg.get(WS, SRC)
        waveform_id_before = id(active_before.record.waveform_data)
        values_before = active_before.record.waveform_data["VRY_275"].tolist()

        update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_275"]),
            source_registry=source_reg, voltage_config_registry=vol_reg,
        )

        active_after = source_reg.get(WS, SRC)
        waveform_id_after = id(active_after.record.waveform_data)
        values_after = active_after.record.waveform_data["VRY_275"].tolist()

        # Same object identity and same values — the reconfiguration touched nothing.
        assert waveform_id_before == waveform_id_after
        assert values_before == values_after


# ---------------------------------------------------------------------------
# Scenario 9 — Backward-compatible: no voltage_config_registry → old behavior
# ---------------------------------------------------------------------------

class TestScenario9_BackwardCompatibility:
    """When ``voltage_config_registry`` is not supplied, ``update_group``
    must behave exactly as before RD-0B — no reconfiguration, no errors."""

    def test_update_group_without_voltage_registry_does_not_raise(self):
        ch = [_channel("VRY_132", VOLTAGE, primary_ratio=132.0),
              _channel("VRY_275", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["VRY_132"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        # No voltage_config_registry — old call site behavior.
        updated = update_group(
            workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
            channel_refs=_refs(["VRY_275"]),
            source_registry=source_reg,
            # voltage_config_registry intentionally omitted
        )
        assert updated is not None

        # Config is unchanged (reconfiguration was not triggered).
        config = vol_reg.get(WS, "vg1")
        assert config is not None
        assert config.base_authority == BASE_AUTHORITY_AUTO
        assert config.nominal_voltage_ll_kv == pytest.approx(132.0)


# ---------------------------------------------------------------------------
# Scenario 10 — Repeated edits leave no stale state
# ---------------------------------------------------------------------------

class TestScenario10_RepeatedEdits:
    """Editing a group multiple times must always produce a consistent,
    current state — no stale authority leaks from earlier iterations."""

    def test_triple_edit_converges_to_final_evidence(self):
        # Use prefix naming so phase tokens (VRY) end the channel name.
        ch = [_channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
              _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
              _channel("HV33_VRY", VOLTAGE, primary_ratio=33.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["HV132_VRY"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        # Edit 1: → 275 kV channels.
        update_group(workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
                     channel_refs=_refs(["HV275_VRY"]), source_registry=source_reg, voltage_config_registry=vol_reg)
        assert vol_reg.get(WS, "vg1").nominal_voltage_ll_kv == pytest.approx(275.0)
        assert vol_reg.get(WS, "vg1").base_authority == BASE_AUTHORITY_AUTO

        # Edit 2: → 33 kV channels.
        update_group(workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
                     channel_refs=_refs(["HV33_VRY"]), source_registry=source_reg, voltage_config_registry=vol_reg)
        assert vol_reg.get(WS, "vg1").nominal_voltage_ll_kv == pytest.approx(33.0)
        assert vol_reg.get(WS, "vg1").base_authority == BASE_AUTHORITY_AUTO

        # Edit 3: → back to 132 kV.
        update_group(workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
                     channel_refs=_refs(["HV132_VRY"]), source_registry=source_reg, voltage_config_registry=vol_reg)
        final = vol_reg.get(WS, "vg1")
        assert final.base_authority == BASE_AUTHORITY_AUTO
        assert final.nominal_voltage_ll_kv == pytest.approx(132.0)

    def test_no_stale_auto_resolved_after_evidence_removed(self):
        """After going from good evidence → no evidence, the state must not
        remain auto_resolved from the first edit."""
        ch = [_channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
              _channel("VA_norat", VOLTAGE)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group = _make_group("vg1", ["HV132_VRY"])
        group_reg.add(group)
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        # Edit 1: good evidence → auto_resolved.
        update_group(workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
                     channel_refs=_refs(["HV132_VRY"]), source_registry=source_reg, voltage_config_registry=vol_reg)
        assert vol_reg.get(WS, "vg1").base_authority == BASE_AUTHORITY_AUTO

        # Edit 2: no primary_ratio → insufficient evidence.
        update_group(workspace_id=WS, measurement_group_id="vg1", registry=group_reg,
                     channel_refs=_refs(["VA_norat"]), source_registry=source_reg, voltage_config_registry=vol_reg)
        final = vol_reg.get(WS, "vg1")
        assert final.base_authority != BASE_AUTHORITY_AUTO


# ---------------------------------------------------------------------------
# Direct unit tests of reconfigure_auto_base_after_membership_change
# ---------------------------------------------------------------------------

class TestReconfigureFunctionDirect:
    """Direct unit tests for the new service function, independent of update_group."""

    def test_returns_none_for_current_group(self):
        ch = [_channel("IA", CURRENT, unit="A")]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        cg = MeasurementGroup(
            id="cg1", workspace_id=WS, source_id=SRC, kind=KIND_CURRENT,
            display_name="CG", channel_refs=_refs(["IA"]), status=STATUS_SUGGESTED,
        )
        group_reg.add(cg)
        vol_reg = VoltageGroupConfigRegistry()

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="cg1",
            source_registry=source_reg, group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result is None

    def test_returns_none_when_no_config_exists(self):
        ch = [_channel("VRY", VOLTAGE, primary_ratio=132.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group_reg.add(_make_group("vg1", ["VRY"]))
        vol_reg = VoltageGroupConfigRegistry()
        # No config written → nothing to reconfigure.

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="vg1",
            source_registry=source_reg, group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result is None

    def test_manual_config_runs_compatibility_check(self):
        # RD-0B Option A: manual bases now run a compatibility check rather than
        # returning None immediately.  Compatible evidence → action="manual_compatible";
        # authority is never overwritten.
        ch = [_channel("VRY", VOLTAGE, primary_ratio=132.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group_reg.add(_make_group("vg1", ["VRY"]))
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_MANUAL))

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="vg1",
            source_registry=source_reg, group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        # Compatible evidence: no conflict flag, authority preserved
        cfg = vol_reg.get(WS, "vg1")
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0
        assert cfg.manual_conflict_detected is False
        assert result is not None
        assert result.action == "manual_compatible"

    def test_returns_none_when_group_does_not_exist(self):
        source_reg = _make_source_registry([])
        group_reg = MeasurementGroupRegistry()
        vol_reg = VoltageGroupConfigRegistry()

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="nonexistent",
            source_registry=source_reg, group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result is None

    def test_configured_primary_action_on_good_evidence(self):
        ch = [_channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
              _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
              _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group_reg.add(_make_group("vg1", ["HV275_VRY", "HV275_VYB", "HV275_VBR"]))
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="vg1",
            source_registry=source_reg, group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result is not None
        assert result.action.startswith("configured_")
        assert vol_reg.get(WS, "vg1").base_authority == BASE_AUTHORITY_AUTO
        assert vol_reg.get(WS, "vg1").nominal_voltage_ll_kv == pytest.approx(275.0)

    def test_needs_review_action_on_no_evidence(self):
        ch = [_channel("VA_norat", VOLTAGE)]
        source_reg = _make_source_registry(ch)
        group_reg = MeasurementGroupRegistry()
        group_reg.add(_make_group("vg1", ["VA_norat"]))
        vol_reg = VoltageGroupConfigRegistry()
        vol_reg.upsert(_vconfig("vg1", 132.0, BASE_AUTHORITY_AUTO))

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="vg1",
            source_registry=source_reg, group_registry=group_reg, voltage_config_registry=vol_reg,
        )
        assert result is not None
        assert result.action == "needs_review"
        assert vol_reg.get(WS, "vg1").base_authority == BASE_AUTHORITY_NEEDS_REVIEW
