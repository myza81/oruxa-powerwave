"""Stage 3B-2B-1 tests: Calculated Channel PU Calibration Authority Gate.

Verifies that the gate injected into
_resolve_effective_per_unit_for_calculated_channel() correctly propagates
PhysicalCalibrationAuthority from every leaf source-channel through
arbitrarily deep dependency chains, and blocks authoritative PU output
when any leaf is unverified or invalid (DEC-213).

Requirement categories covered:
  A  BEN5K → reverse-polarity calc → PU → calibration_unavailable
  B  Two BEN5K sources → subtraction → calibration_unavailable
  C  BEN5K (unverified) + COMTRADE (not-assessed) → addition → calibration_unavailable
  D  Deep chain BEN5K → calc1 → calc2 → calibration_unavailable (chain traversal)
  E  Pure COMTRADE not-assessed leaves → gate PASSES (backward compat)
  F  All-verified leaves → gate PASSES
  G  Mix verified BEN5K + not-assessed COMTRADE → gate PASSES (eligible=True, backward compat)
  H  BEN5K invalid authority → calibration_unavailable
  I  Deep chain BEN5K via two intermediate calcs → calibration_unavailable
  J  POWER quantity with BEN5K source → not_applicable (OD-4: gate does NOT fire)
  K  FREQUENCY / ROCOF quantity → not_applicable (OD-4 preserved)
  L  UNDEFINED quantity → not_applicable (OD-4 preserved)

Additional required cases:
  OD-1  source_registry=None with source-backed refs → source_registry_unavailable
  OD-3a source not found in registry → source_unavailable
  OD-3b BEN5K channel not in analog_channels → channel_not_found_ben5k
  OD-3c BEN5K authority is None → ben5k_authority_absent
  CYCLE  circular dependency detected → circular_dependency blocked_reason
  DEDUP  same (source_id, channel_name) leaf in multiple branches → counted once

Governance: Stage 3B-2B-1 — gate ONLY.
  No calibration correction factors are applied.
  No new PU bases are assigned.
  COMTRADE regressions (PULU-07/08/09) are unaffected (see Scenario E).
  Stage 3B-2C, 3B-3 and Slice 6D are NOT activated by any code here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import (
    ChannelRef,
    CalculatedChannel,
    OP_ADDITION,
    OP_REVERSE_POLARITY,
    OP_SUBTRACTION,
    OP_ACTIVE_POWER,
    OP_ROCOF,
    NULL_POLICY_PROPAGATE,
)
from app.domain.channel_classification import (
    UNDEFINED,
)
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import FORMAT_VARIANT_BEN5K_LEGACY, RecordingMetadata
from app.domain.per_unit import (
    STATUS_CALIBRATION_UNAVAILABLE,
    STATUS_NOT_APPLICABLE,
)
from app.domain.physical_calibration import (
    CALIBRATION_INVALID,
    CALIBRATION_UNVERIFIED,
    CALIBRATION_VERIFIED,
    REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    PhysicalCalibrationAuthority,
)
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    _collect_leaf_authorities,
    _resolve_effective_per_unit_for_calculated_channel,
)
from app.services.workspace_registry import WorkspaceRegistry

# ---------------------------------------------------------------------------
# Well-known authorities
# ---------------------------------------------------------------------------

_UNVERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_UNVERIFIED,
    reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)
_VERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_VERIFIED,
    reason="lab_verified_crosscheck",
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)
_INVALID_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_INVALID,
    reason="transform_id_mismatch_invalidated",
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

WS = "ws-gate-test"
_N = 10
_TIME = np.arange(_N, dtype=np.float64) * 0.001
_VALS = np.ones(_N, dtype=np.float64) * 10.0
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Engineering types used by the gate (OD-4 boundary)
VOLTAGE = "Voltage"
CURRENT = "Current"
POWER = "Power"
FREQUENCY = "Frequency"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_active_source(
    *,
    source_id: str,
    channel_name: str = "VA",
    engineering_type: str = VOLTAGE,
    unit: str = "kV",
    format_variant: str | None = FORMAT_VARIANT_BEN5K_LEGACY,
    calibration_authority: PhysicalCalibrationAuthority | None = _UNVERIFIED_AUTH,
) -> ActiveSource:
    """Minimal ActiveSource for calibration-gate testing.

    Defaults to BEN5K format_variant and an unverified authority — the
    common case for BEN5K scenario tests. Pass format_variant=None for
    COMTRADE-style sources, and calibration_authority=None for not-assessed.
    """
    analog_channel = AnalogChannel(
        name=channel_name,
        unit=unit,
        index=1,
        phase="A",
        calibration_authority=calibration_authority,
    )
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="TEST",
            recorder_name="TEST",
            source_file="test.ben",
            provider_type="BEN",
            nominal_frequency=50.0,
            format_variant=format_variant,
        ),
        waveform_data=pd.DataFrame({"time": _TIME, channel_name: _VALS}),
        analog_channels=[analog_channel],
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1000.0], samples_per_rate=[_N]),
        timing_info=TimingInformation(start_time=_NOW, trigger_time=_NOW),
    )
    metadata = SourceMetadata(
        source_id=source_id,
        workspace_id=WS,
        provider_type="BEN",
        original_filenames=("test.ben",),
        created_at=_NOW,
        station_name="TEST",
        recorder_name="TEST",
        nominal_frequency=50.0,
        timing_reference="relative_elapsed",
        start_time=_NOW,
        trigger_time=_NOW,
        sample_count=_N,
        duration_seconds=float(_TIME[-1] - _TIME[0]),
        elapsed_start_seconds=float(_TIME[0]),
        elapsed_end_seconds=float(_TIME[-1]),
        sampling_rates=(1000.0,),
        samples_per_rate=(_N,),
        analog_channels=[
            AnalogChannelSummary(
                name=channel_name,
                index=1,
                unit=unit,
                engineering_type=engineering_type,
            )
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _make_calc_channel(
    *,
    calc_id: str | None = None,
    workspace_id: str = WS,
    name: str = "calc",
    unit: str = "kV",
    operation: str = OP_REVERSE_POLARITY,
    inputs: list[ChannelRef],
    engineering_type: str = VOLTAGE,
    reference_source_id: str = "src1",
) -> CalculatedChannel:
    """Build a minimal CalculatedChannel for gate testing (no actual calculation)."""
    return CalculatedChannel(
        id=calc_id or str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=name,
        unit=unit,
        operation=operation,
        inputs=inputs,
        parameters={},
        dependency_ids=[
            ref.calculated_channel_id
            for ref in inputs
            if ref.kind == "calculated"
        ],
        reference_source_id=reference_source_id,
        time=_TIME.copy(),
        values=_VALS.copy(),
        created_at=_NOW,
        engineering_type=engineering_type,
    )


# ---------------------------------------------------------------------------
# _collect_leaf_authorities unit tests
# ---------------------------------------------------------------------------


class TestCollectLeafAuthoritiesStructural:
    """Unit tests for _collect_leaf_authorities traversal and OD conditions."""

    def test_od1_source_registry_none_blocks(self):
        """OD-1: source_registry=None with source-backed ref → source_registry_unavailable."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=None,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason == "source_registry_unavailable"

    def test_od1_workspace_id_none_blocks(self):
        """OD-1: workspace_id=None with source-backed ref → source_registry_unavailable."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=None,
            source_registry=WorkspaceRegistry(),
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason == "source_registry_unavailable"

    def test_od3a_source_not_found(self):
        """OD-3a: source not in registry → source_unavailable."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="missing-src", channel_name="VA")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=WorkspaceRegistry(),
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason == "source_unavailable"

    def test_od3b_ben5k_channel_missing_from_analog_channels(self):
        """OD-3b: BEN5K source but channel not in analog_channels → channel_not_found_ben5k."""
        source_registry = WorkspaceRegistry()
        source_registry.add(_make_active_source(source_id="src1", channel_name="VA"))
        # Reference a channel that does not exist in that source
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VB")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason == "channel_not_found_ben5k"

    def test_od3c_ben5k_authority_absent(self):
        """OD-3c: BEN5K channel with calibration_authority=None → ben5k_authority_absent."""
        source_registry = WorkspaceRegistry()
        source_registry.add(
            _make_active_source(source_id="src1", calibration_authority=None)
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason == "ben5k_authority_absent"

    def test_non_ben5k_missing_channel_is_not_assessed(self):
        """Non-BEN5K source with missing channel → None authority (not-assessed, backward compat)."""
        source_registry = WorkspaceRegistry()
        source_registry.add(
            _make_active_source(
                source_id="src1",
                channel_name="VA",
                format_variant=None,  # COMTRADE
                calibration_authority=None,
            )
        )
        # Reference a channel that doesn't exist → non-BEN5K: not-assessed
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VB")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason is None
        assert result.authorities == [None]

    def test_non_ben5k_missing_authority_is_not_assessed(self):
        """Non-BEN5K source channel with authority=None → None (not-assessed, backward compat)."""
        source_registry = WorkspaceRegistry()
        source_registry.add(
            _make_active_source(
                source_id="src1",
                format_variant=None,  # COMTRADE
                calibration_authority=None,
            )
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason is None
        assert result.authorities == [None]

    def test_single_unverified_leaf_collected(self):
        """Single BEN5K unverified leaf → one unverified authority."""
        source_registry = WorkspaceRegistry()
        source_registry.add(_make_active_source(source_id="src1"))
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason is None
        assert len(result.authorities) == 1
        assert result.authorities[0].status == CALIBRATION_UNVERIFIED

    def test_deduplication_same_leaf_in_two_branches(self):
        """DEDUP: same (source_id, channel_name) in two inputs → collected once."""
        source_registry = WorkspaceRegistry()
        source_registry.add(_make_active_source(source_id="src1"))
        # Both inputs reference the same source channel
        channel = _make_calc_channel(
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VA"),
                ChannelRef(kind="source", source_id="src1", channel_name="VA"),
            ],
            operation=OP_ADDITION,
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason is None
        assert len(result.authorities) == 1

    def test_cycle_detection_returns_circular_dependency(self):
        """CYCLE: inject a cycle manually via _path_visited → circular_dependency."""
        calc_id = "calc-cycle"
        channel = _make_calc_channel(
            calc_id=calc_id,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=calc_id)],
        )
        calc_registry = CalculatedChannelRegistry()
        calc_registry.add(channel)
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=WorkspaceRegistry(),
            calc_registry=calc_registry,
        )
        assert result.blocked_reason == "circular_dependency"

    def test_calculated_ref_with_no_calc_registry_blocks(self):
        """Calc-kind ref without calc_registry → source_registry_unavailable."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="calculated", calculated_channel_id="calc-1")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=None,
            calc_registry=None,
        )
        assert result.blocked_reason == "source_registry_unavailable"

    def test_calculated_channel_not_found_in_registry(self):
        """Calc-kind ref not in registry → calculated_channel_not_found."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="calculated", calculated_channel_id="missing-calc")],
        )
        result = _collect_leaf_authorities(
            channel,
            workspace_id=WS,
            source_registry=WorkspaceRegistry(),
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.blocked_reason == "calculated_channel_not_found"

    def test_two_level_chain_ben5k_propagates(self):
        """Two-level chain: calc → calc → BEN5K source → unverified propagates up."""
        source_registry = WorkspaceRegistry()
        source_registry.add(_make_active_source(source_id="src1"))

        calc_registry = CalculatedChannelRegistry()
        inner_id = "inner-calc"
        inner_calc = _make_calc_channel(
            calc_id=inner_id,
            name="-VA",
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            reference_source_id="src1",
        )
        calc_registry.add(inner_calc)

        outer_calc = _make_calc_channel(
            name="--VA",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=inner_id)],
            reference_source_id="src1",
        )
        result = _collect_leaf_authorities(
            outer_calc,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.blocked_reason is None
        assert len(result.authorities) == 1
        assert result.authorities[0].status == CALIBRATION_UNVERIFIED


# ---------------------------------------------------------------------------
# _resolve_effective_per_unit_for_calculated_channel scenario tests
# ---------------------------------------------------------------------------


def _registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


class TestGateScenarioA:
    """A: BEN5K voltage → reverse polarity → PU → calibration_unavailable."""

    def test_ben5k_reverse_polarity_blocked(self):
        source_registry, calc_registry = _registries()
        source_registry.add(_make_active_source(source_id="src1"))

        channel = _make_calc_channel(
            name="-VA",
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioB:
    """B: Two BEN5K sources → subtraction → calibration_unavailable."""

    def test_two_ben5k_sources_blocked(self):
        source_registry, calc_registry = _registries()
        source_registry.add(_make_active_source(source_id="src1", channel_name="VA"))
        source_registry.add(_make_active_source(source_id="src2", channel_name="VB"))

        channel = _make_calc_channel(
            name="VA-VB",
            operation=OP_SUBTRACTION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VA"),
                ChannelRef(kind="source", source_id="src2", channel_name="VB"),
            ],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioC:
    """C: BEN5K (unverified) + COMTRADE (not-assessed) → calibration_unavailable."""

    def test_mix_unverified_and_not_assessed_blocked(self):
        source_registry, calc_registry = _registries()
        source_registry.add(_make_active_source(source_id="ben5k-src", channel_name="VA"))
        source_registry.add(
            _make_active_source(
                source_id="comtrade-src",
                channel_name="VB",
                format_variant=None,
                calibration_authority=None,
            )
        )
        channel = _make_calc_channel(
            name="VA+VB",
            operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="ben5k-src", channel_name="VA"),
                ChannelRef(kind="source", source_id="comtrade-src", channel_name="VB"),
            ],
            engineering_type=VOLTAGE,
            reference_source_id="ben5k-src",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioD:
    """D: BEN5K → calc1 (reverse polarity) → gate fires on initial calc too."""

    def test_one_hop_chain_blocked(self):
        source_registry, calc_registry = _registries()
        source_registry.add(_make_active_source(source_id="src1"))

        inner_id = "calc-neg-va"
        inner = _make_calc_channel(
            calc_id=inner_id,
            name="-VA",
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        calc_registry.add(inner)

        outer = _make_calc_channel(
            name="--VA",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=inner_id)],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            outer, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioE:
    """E: Pure COMTRADE not-assessed leaves → gate PASSES (backward compat)."""

    def test_comtrade_not_assessed_passes_gate(self):
        source_registry, calc_registry = _registries()
        source_registry.add(
            _make_active_source(
                source_id="comtrade-src",
                format_variant=None,  # not BEN5K
                calibration_authority=None,  # not-assessed
            )
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="comtrade-src", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="comtrade-src",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        # Gate must NOT return calibration_unavailable for not-assessed COMTRADE
        assert result.status != STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioF:
    """F: All-verified BEN5K leaves → gate PASSES."""

    def test_all_verified_passes_gate(self):
        source_registry, calc_registry = _registries()
        source_registry.add(
            _make_active_source(
                source_id="src1",
                calibration_authority=_VERIFIED_AUTH,
            )
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        # Gate must NOT block a verified source
        assert result.status != STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioG:
    """G: Mix verified BEN5K + not-assessed COMTRADE → gate PASSES (not_fully_verified,
    eligible=True — backward compat preserved for not-assessed leaves).

    The domain evaluator treats not-assessed (None) as eligible regardless of
    purpose (_result_for_not_assessed returns eligible=True). The gate only
    blocks when an explicitly Unverified or Invalid authority is present.
    """

    def test_mix_verified_and_not_assessed_passes_gate(self):
        source_registry, calc_registry = _registries()
        # Verified BEN5K
        source_registry.add(
            _make_active_source(
                source_id="ben5k-src",
                channel_name="VA",
                calibration_authority=_VERIFIED_AUTH,
            )
        )
        # Not-assessed COMTRADE
        source_registry.add(
            _make_active_source(
                source_id="comtrade-src",
                channel_name="VB",
                format_variant=None,
                calibration_authority=None,
            )
        )
        channel = _make_calc_channel(
            name="VA+VB",
            operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="ben5k-src", channel_name="VA"),
                ChannelRef(kind="source", source_id="comtrade-src", channel_name="VB"),
            ],
            engineering_type=VOLTAGE,
            reference_source_id="ben5k-src",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        # Not-assessed (None) leaves do not block the gate — eligible=True (not_fully_verified).
        assert result.status != STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioH:
    """H: BEN5K invalid authority → calibration_unavailable."""

    def test_invalid_authority_blocked(self):
        source_registry, calc_registry = _registries()
        source_registry.add(
            _make_active_source(source_id="src1", calibration_authority=_INVALID_AUTH)
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioI:
    """I: Deep chain BEN5K → calc1 → calc2 → calibration_unavailable."""

    def test_two_hop_chain_blocked(self):
        source_registry, calc_registry = _registries()
        source_registry.add(_make_active_source(source_id="src1"))

        inner_id = "calc-1"
        inner = _make_calc_channel(
            calc_id=inner_id,
            name="-VA",
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        calc_registry.add(inner)

        middle_id = "calc-2"
        middle = _make_calc_channel(
            calc_id=middle_id,
            name="--VA",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=inner_id)],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        calc_registry.add(middle)

        outer = _make_calc_channel(
            name="---VA",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=middle_id)],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            outer, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE


class TestGateScenarioJ:
    """J: POWER quantity with BEN5K source → not_applicable (OD-4: gate does NOT fire)."""

    def test_power_quantity_not_applicable_od4(self):
        source_registry, calc_registry = _registries()
        source_registry.add(
            _make_active_source(source_id="src1", calibration_authority=_UNVERIFIED_AUTH)
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=POWER,
            unit="MW",
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        # OD-4: gate must not fire for POWER; must return not_applicable
        assert result.status == STATUS_NOT_APPLICABLE


class TestGateScenarioK:
    """K: FREQUENCY quantity → not_applicable (OD-4 preserved)."""

    def test_frequency_quantity_not_applicable_od4(self):
        source_registry, calc_registry = _registries()
        source_registry.add(
            _make_active_source(source_id="src1", calibration_authority=_UNVERIFIED_AUTH)
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=FREQUENCY,
            unit="Hz",
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_NOT_APPLICABLE


class TestGateScenarioL:
    """L: UNDEFINED engineering type → not_applicable (OD-4 preserved)."""

    def test_undefined_quantity_not_applicable_od4(self):
        source_registry, calc_registry = _registries()
        source_registry.add(
            _make_active_source(source_id="src1", calibration_authority=_UNVERIFIED_AUTH)
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=UNDEFINED,
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_NOT_APPLICABLE


class TestGateOD2EngineeringMode:
    """OD-2: ENG mode (source_registry=None) → gate does not fire for callers that
    omit source_registry (preserving existing ENG-mode behavior).

    When source_registry is None and workspace_id is None, the gate fires
    source_registry_unavailable for VOLTAGE/CURRENT types — but the CURRENT
    inherited-PU path and ENG-mode callers pass unit_mode=UNIT_MODE_ENGINEERING
    and never reach this function at all. What we verify here is that
    passing source_registry=None to the function blocks cleanly rather than
    crashing, so callers that DO omit it get a safe calibration_unavailable
    rather than a silent bypass or an exception.
    """

    def test_no_registry_voltage_returns_calibration_unavailable(self):
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        # Both registries omitted — OD-1 fail-closed applies
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_no_registry_current_returns_calibration_unavailable(self):
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="IA")],
            engineering_type=CURRENT,
            unit="kA",
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_no_registry_power_still_not_applicable(self):
        """OD-4: POWER with no registries → not_applicable (gate does not fire for POWER)."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=POWER,
            unit="MW",
            reference_source_id="src1",
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
        )
        assert result.status == STATUS_NOT_APPLICABLE


class TestGateReasonStrings:
    """OD-3: blocked_reason strings are machine-readable, not fabricated authority objects."""

    def test_unverified_ben5k_reason_propagates_to_resolution(self):
        source_registry, calc_registry = _registries()
        source_registry.add(_make_active_source(source_id="src1"))
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            engineering_type=VOLTAGE,
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE
        # reason must be a non-empty string (machine-readable), not None
        assert result.reason is not None
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_blocked_reason_for_missing_source(self):
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="missing", channel_name="VA")],
            engineering_type=VOLTAGE,
        )
        result = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS,
            source_registry=WorkspaceRegistry(),
            calc_registry=CalculatedChannelRegistry(),
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE
        assert result.reason == "source_unavailable"
