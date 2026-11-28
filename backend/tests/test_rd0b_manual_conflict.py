"""RD-0B Option A — Manual-base compatibility tests.

Covers the three-case manual conflict detection logic added to
reconfigure_auto_base_after_membership_change():

  Case 1 (conflict):    detection resolves a DIFFERENT kV → manual_conflict_detected=True,
                        base_authority still "manual", PU blocked.
  Case 2 (compatible):  detection resolves the SAME kV (within 5%) → flag cleared.
  Case 3 (no evidence): detection insufficient → flag cleared, manual base in force.

Also covers: legacy_manual, unrelated group isolation, stale-flag clearing,
ambiguous evidence, repeated edits, and engineer-correction clearing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.domain.base_authority import BASE_AUTHORITY_MANUAL, BASE_AUTHORITY_LEGACY
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import (
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
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

# ---------------------------------------------------------------------------
# Shared helpers (mirror the pattern from test_rd0b_auto_base_membership_reconfigure)
# ---------------------------------------------------------------------------

WS = "ws-manual-conflict"
SRC = "src-mc"


def _channel(name: str, etype: str, unit: str = "kV",
             primary_ratio: float | None = None,
             measurement_side: str = "primary") -> AnalogChannelSummary:
    return AnalogChannelSummary(
        name=name, index=0, unit=unit, engineering_type=etype,
        measurement_side=measurement_side,
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


def _make_group(group_id: str, channel_names: list[str],
                kind: str = KIND_VOLTAGE,
                status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    refs = [ChannelRef(kind="source", source_id=SRC, channel_name=n) for n in channel_names]
    return MeasurementGroup(
        id=group_id, workspace_id=WS, source_id=SRC,
        kind=kind, display_name=group_id,
        channel_refs=refs, status=status,
    )


def _vconfig(group_id: str, nominal_kv: float,
             authority: str = BASE_AUTHORITY_MANUAL,
             manual_conflict_detected: bool = False,
             manual_conflict_detail: str | None = None) -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(
        measurement_group_id=group_id, workspace_id=WS,
        nominal_voltage_ll_kv=nominal_kv,
        base_reference_side="primary",
        base_authority=authority,
        manual_conflict_detected=manual_conflict_detected,
        manual_conflict_detail=manual_conflict_detail,
    )


# Channel name conventions (from test_rd0b_auto_base_membership_reconfigure.py):
#   L-L 132 kV: HV132_VRY, HV132_VYB, HV132_VBR  (primary_ratio=132.0)
#   L-L 275 kV: HV275_VRY, HV275_VYB, HV275_VBR  (primary_ratio=275.0)


# ---------------------------------------------------------------------------
# Test 1: Conflict detected — manual 132 kV, 275 kV channels
# ---------------------------------------------------------------------------

class TestManualConflictDetected:
    """Case 1: detection resolves a DIFFERENT kV — conflict flag set."""

    def _setup(self, manual_conflict_detected: bool = False, manual_conflict_detail: str | None = None):
        channels = [
            _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0),
        ]
        sr = _make_source_registry(channels)
        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["HV275_VRY", "HV275_VYB", "HV275_VBR"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g1", 132.0, manual_conflict_detected=manual_conflict_detected,
                            manual_conflict_detail=manual_conflict_detail))
        return sr, gr, vcr, group

    def test_conflict_flag_set(self):
        sr, gr, vcr, _group = self._setup()

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg is not None
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL   # never overwritten
        assert cfg.nominal_voltage_ll_kv == 132.0           # original kV preserved
        assert cfg.manual_conflict_detected is True
        assert cfg.manual_conflict_detail is not None
        assert "275" in cfg.manual_conflict_detail
        assert "132" in cfg.manual_conflict_detail
        assert result is not None
        assert result.action == "manual_conflict_flagged"

    def test_pu_blocked_when_conflict_flagged(self):
        sr, gr, vcr, group = self._setup(
            manual_conflict_detected=True,
            manual_conflict_detail="detected_275.0kv_conflicts_with_manual_132.0kv",
        )
        cfg = vcr.get(WS, "g1")
        resolution = resolve_voltage_base_for_group(group, cfg)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "manual_conflict_detected"


# ---------------------------------------------------------------------------
# Test 2: Compatible evidence — flag cleared / stays clear
# ---------------------------------------------------------------------------

class TestManualCompatibleEvidence:
    """Case 2: detection resolves the SAME kV — flag cleared."""

    def _setup(self, manual_conflict_detected: bool = False, manual_conflict_detail: str | None = None):
        channels = [
            _channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VYB", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VBR", VOLTAGE, primary_ratio=132.0),
        ]
        sr = _make_source_registry(channels)
        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["HV132_VRY", "HV132_VYB", "HV132_VBR"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g1", 132.0, manual_conflict_detected=manual_conflict_detected,
                            manual_conflict_detail=manual_conflict_detail))
        return sr, gr, vcr, group

    def test_no_conflict_flag_when_compatible(self):
        sr, gr, vcr, _group = self._setup()

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0
        assert cfg.manual_conflict_detected is False
        assert cfg.manual_conflict_detail is None
        assert result is not None
        assert result.action == "manual_compatible"

    def test_stale_conflict_flag_cleared_when_compatible(self):
        sr, gr, vcr, _group = self._setup(
            manual_conflict_detected=True, manual_conflict_detail="stale"
        )

        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg.manual_conflict_detected is False
        assert cfg.manual_conflict_detail is None


# ---------------------------------------------------------------------------
# Test 3: Insufficient evidence — manual base preserved, no flag
# ---------------------------------------------------------------------------

class TestManualInsufficientEvidence:
    """Case 3: detection cannot establish a kV — no conflict flag."""

    def _setup(self, manual_conflict_detected: bool = False, manual_conflict_detail: str | None = None):
        # Current channels only — no voltage evidence
        channels = [
            _channel("IA", CURRENT, unit="A", primary_ratio=None),
            _channel("IB", CURRENT, unit="A", primary_ratio=None),
        ]
        sr = _make_source_registry(channels)
        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["IA", "IB"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g1", 132.0, manual_conflict_detected=manual_conflict_detected,
                            manual_conflict_detail=manual_conflict_detail))
        return sr, gr, vcr, group

    def test_no_flag_when_evidence_insufficient(self):
        sr, gr, vcr, _group = self._setup()

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0
        assert cfg.manual_conflict_detected is False
        assert result is None   # no action taken

    def test_stale_flag_cleared_when_insufficient_evidence(self):
        sr, gr, vcr, _group = self._setup(
            manual_conflict_detected=True, manual_conflict_detail="stale_conflict"
        )

        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg.manual_conflict_detected is False
        assert cfg.manual_conflict_detail is None


# ---------------------------------------------------------------------------
# Test 4: Engineer correction clears the flag
# ---------------------------------------------------------------------------

class TestEngineerCorrectionClearsFlag:
    def test_manual_set_clears_conflict(self):
        from app.services.voltage_group_config_service import update_voltage_configuration

        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["HV275_VRY"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig(
            "g1", 132.0,
            manual_conflict_detected=True,
            manual_conflict_detail="detected_275kv_conflicts_with_manual_132kv",
        ))

        # Engineer corrects the value to 275 kV
        updated = update_voltage_configuration(
            workspace_id=WS, measurement_group_id="g1",
            nominal_voltage_ll_kv=275.0,
            group_registry=gr, voltage_config_registry=vcr,
        )

        assert updated.nominal_voltage_ll_kv == 275.0
        assert updated.base_authority == BASE_AUTHORITY_MANUAL
        assert updated.manual_conflict_detected is False
        assert updated.manual_conflict_detail is None


# ---------------------------------------------------------------------------
# Test 5: legacy_manual behaves identically to manual
# ---------------------------------------------------------------------------

class TestLegacyManualConflict:
    def test_legacy_manual_conflict_flagged(self):
        channels = [
            _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0),
        ]
        sr = _make_source_registry(channels)
        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["HV275_VRY", "HV275_VYB", "HV275_VBR"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g1", 132.0, authority=BASE_AUTHORITY_LEGACY))

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg.base_authority == BASE_AUTHORITY_LEGACY  # never overwritten
        assert cfg.nominal_voltage_ll_kv == 132.0
        assert cfg.manual_conflict_detected is True
        assert result.action == "manual_conflict_flagged"


# ---------------------------------------------------------------------------
# Test 6: Unrelated group is not affected
# ---------------------------------------------------------------------------

class TestUnrelatedGroupUnaffected:
    def test_sibling_group_untouched(self):
        all_channels = [
            _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0),
            _channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VYB", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VBR", VOLTAGE, primary_ratio=132.0),
        ]
        sr = _make_source_registry(all_channels)
        gr = MeasurementGroupRegistry()

        group_a = _make_group("g-a", ["HV275_VRY", "HV275_VYB", "HV275_VBR"])
        group_b = _make_group("g-b", ["HV132_VRY", "HV132_VYB", "HV132_VBR"])
        gr.add(group_a)
        gr.add(group_b)

        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g-a", 132.0))  # will conflict: manual 132 kV, 275 kV channels
        vcr.upsert(_vconfig("g-b", 132.0))  # will be untouched

        # Only edit group_a
        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g-a",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg_a = vcr.get(WS, "g-a")
        cfg_b = vcr.get(WS, "g-b")

        assert cfg_a.manual_conflict_detected is True
        assert cfg_b.manual_conflict_detected is False    # untouched
        assert cfg_b.nominal_voltage_ll_kv == 132.0


# ---------------------------------------------------------------------------
# Test 7: Ambiguous (conflicting candidates) → no conflict flag
# ---------------------------------------------------------------------------

class TestAmbiguousEvidenceNoFlag:
    """When detection produces conflicting candidates (not a single resolved kV),
    evidence is treated as insufficient — no conflict flag."""

    def test_ambiguous_channels_no_flag(self):
        # Mix of 132 kV and 275 kV channels in same group → ambiguous, not sufficient_for_auto_nominal
        channels = [
            _channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
            _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
        ]
        sr = _make_source_registry(channels)
        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["HV132_VRY", "HV275_VRY"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g1", 132.0))

        result = reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        # Ambiguous = insufficient for auto_nominal → no conflict flag
        assert cfg.manual_conflict_detected is False
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0
        assert result is None


# ---------------------------------------------------------------------------
# Test 8: Repeated edits converge correctly
# ---------------------------------------------------------------------------

class TestRepeatedEdits:
    def test_flag_conflict_then_clear_then_flag_again(self):
        """Cycle: 275 kV channels (conflict) → 132 kV channels (clear) → 275 kV (conflict)."""
        channels_275 = [
            _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0),
        ]
        channels_132 = [
            _channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VYB", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VBR", VOLTAGE, primary_ratio=132.0),
        ]

        gr = MeasurementGroupRegistry()
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig("g1", 132.0))

        def _edit_group(channel_names: list[str]):
            refs = [ChannelRef(kind="source", source_id=SRC, channel_name=n) for n in channel_names]
            group = MeasurementGroup(
                id="g1", workspace_id=WS, source_id=SRC,
                kind=KIND_VOLTAGE, display_name="g1",
                channel_refs=refs, status=STATUS_CONFIRMED,
            )
            try:
                gr.update(group)
            except Exception:
                gr.add(group)

        # Round 1: 275 kV channels → conflict
        _edit_group(["HV275_VRY", "HV275_VYB", "HV275_VBR"])
        sr = _make_source_registry(channels_275)
        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )
        assert vcr.get(WS, "g1").manual_conflict_detected is True

        # Round 2: 132 kV channels → conflict cleared
        _edit_group(["HV132_VRY", "HV132_VYB", "HV132_VBR"])
        sr = _make_source_registry(channels_132)
        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )
        assert vcr.get(WS, "g1").manual_conflict_detected is False

        # Round 3: 275 kV channels again → conflict again
        _edit_group(["HV275_VRY", "HV275_VYB", "HV275_VBR"])
        sr = _make_source_registry(channels_275)
        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )
        cfg = vcr.get(WS, "g1")
        assert cfg.manual_conflict_detected is True
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0


# ---------------------------------------------------------------------------
# Tests 9-12: voltage-config update + re-evaluation (RD-0B safety scenario)
#
# These tests simulate the combined API behavior: update_voltage_configuration()
# clears the conflict flag, then reconfigure_auto_base_after_membership_change()
# re-evaluates the new kV against current channel evidence.
# ---------------------------------------------------------------------------

class TestVoltageUpdateReEvaluation:
    """Verify that setting an incompatible kV does not silently restore PU eligibility."""

    def _channels_275(self):
        return [
            _channel("HV275_VRY", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VYB", VOLTAGE, primary_ratio=275.0),
            _channel("HV275_VBR", VOLTAGE, primary_ratio=275.0),
        ]

    def _channels_132(self):
        return [
            _channel("HV132_VRY", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VYB", VOLTAGE, primary_ratio=132.0),
            _channel("HV132_VBR", VOLTAGE, primary_ratio=132.0),
        ]

    def _run_update_then_reevaluate(
        self, channels, group_channels, initial_kv, new_kv, initial_conflict=True
    ):
        """Simulate the API: update_voltage_configuration() then reconfigure_auto_base_after_membership_change()."""
        from app.services.voltage_group_config_service import update_voltage_configuration

        sr = _make_source_registry(channels)
        gr = MeasurementGroupRegistry()
        group = _make_group("g1", group_channels)
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig(
            "g1", initial_kv,
            manual_conflict_detected=initial_conflict,
            manual_conflict_detail="detected_275.0kv_conflicts_with_manual_132.0kv" if initial_conflict else None,
        ))

        # Step 1: engineer sets new kV (clears flag unconditionally)
        update_voltage_configuration(
            workspace_id=WS, measurement_group_id="g1",
            nominal_voltage_ll_kv=new_kv,
            group_registry=gr, voltage_config_registry=vcr,
        )
        # Verify flag is cleared at this intermediate point
        mid = vcr.get(WS, "g1")
        assert mid.manual_conflict_detected is False, "flag should be cleared by update_voltage_configuration"

        # Step 2: re-evaluate (simulates put_voltage_config API behavior)
        reconfigure_auto_base_after_membership_change(
            workspace_id=WS, source_id=SRC, measurement_group_id="g1",
            source_registry=sr, group_registry=gr, voltage_config_registry=vcr,
        )

        return vcr.get(WS, "g1"), group

    def test_incompatible_edit_remains_blocked(self):
        """Setting 66 kV when channels indicate 275 kV: conflict re-flagged, PU blocked."""
        cfg, group = self._run_update_then_reevaluate(
            channels=self._channels_275(),
            group_channels=["HV275_VRY", "HV275_VYB", "HV275_VBR"],
            initial_kv=132.0, new_kv=66.0,
        )
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 66.0        # new kV preserved for engineer review
        assert cfg.manual_conflict_detected is True     # re-flagged
        resolution = resolve_voltage_base_for_group(group, cfg)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "manual_conflict_detected"

    def test_compatible_edit_clears_conflict(self):
        """Setting 275 kV when channels indicate 275 kV: conflict cleared, PU restored."""
        cfg, group = self._run_update_then_reevaluate(
            channels=self._channels_275(),
            group_channels=["HV275_VRY", "HV275_VYB", "HV275_VBR"],
            initial_kv=132.0, new_kv=275.0,
        )
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 275.0
        assert cfg.manual_conflict_detected is False
        resolution = resolve_voltage_base_for_group(group, cfg)
        assert resolution.status == STATUS_CONFIGURED

    def test_insufficient_evidence_does_not_block(self):
        """No voltage evidence in channels: no false conflict flag set.

        When detection cannot establish a kV, manual_conflict_detected stays False.
        PU eligibility may still require a voltage reference; this test only asserts
        that the conflict flag is NOT the reason for any base_required status.
        """
        # Channels provide no voltage evidence (current-only)
        channels_no_evidence = [
            _channel("IA", CURRENT, unit="A", primary_ratio=None),
        ]
        cfg, group = self._run_update_then_reevaluate(
            channels=channels_no_evidence,
            group_channels=["IA"],
            initial_kv=132.0, new_kv=132.0, initial_conflict=False,
        )
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0
        # Key assertion: insufficient evidence must NOT set the conflict flag
        assert cfg.manual_conflict_detected is False
        # If base_required, the reason must NOT be manual_conflict_detected
        resolution = resolve_voltage_base_for_group(group, cfg)
        assert resolution.reason != "manual_conflict_detected"

    def test_reference_only_change_preserves_manual_base(self):
        """Reference mode change only (no kV): manual base, authority, and conflict flag unchanged."""
        from app.services.voltage_group_config_service import update_voltage_configuration
        from app.domain.voltage_group_config import VOLTAGE_REFERENCE_MODE_MANUAL
        from app.domain.voltage_reference import LINE_TO_LINE

        gr = MeasurementGroupRegistry()
        group = _make_group("g1", ["HV132_VRY"])
        gr.add(group)
        vcr = VoltageGroupConfigRegistry()
        vcr.upsert(_vconfig(
            "g1", 132.0,
            manual_conflict_detected=True,
            manual_conflict_detail="existing_conflict",
        ))

        # Reference-only update: nominal_voltage_ll_kv=None → no kV change, no conflict clear
        update_voltage_configuration(
            workspace_id=WS, measurement_group_id="g1",
            nominal_voltage_ll_kv=None,
            reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL,
            reference_override=LINE_TO_LINE,
            group_registry=gr, voltage_config_registry=vcr,
        )

        cfg = vcr.get(WS, "g1")
        assert cfg.base_authority == BASE_AUTHORITY_MANUAL
        assert cfg.nominal_voltage_ll_kv == 132.0
        assert cfg.manual_conflict_detected is True       # flag not cleared by reference-only change
        assert cfg.manual_conflict_detail == "existing_conflict"
