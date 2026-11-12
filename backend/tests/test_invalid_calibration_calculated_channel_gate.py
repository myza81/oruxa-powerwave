"""Stage 3B-2B-2 tests: Invalid Calibration Authority Gate for Calculated Channels.

Verifies that:
  - Creation-time gate (OD-5): rejects ALL engineering types when any source
    leaf carries CALIBRATION_INVALID authority, before _resolve_input() runs.
  - Evaluation-time gate (OD-6): raises InvalidCalibrationAuthorityError for
    waveform/cursor/peak/annotation when any source leaf is Invalid.
  - Unverified and Not Assessed sources pass both gates (backward compat).
  - Stage 3B-2B-1 PU gate is preserved (Unverified → calibration_unavailable).
  - BEN5K Unverified (not Invalid) is unaffected by Stage 3B-2B-2.

Requirement coverage:
  Creation-time (CA / A–F / CA-7 to CA-10):
    A   Direct Invalid source VOLTAGE → InvalidCalibrationAuthorityError
    B   Nested calc chain with Invalid leaf → creation raises
    C   Mixed Invalid + Verified → creation raises
    D   Direct Invalid source POWER → creation raises (OD-5: ALL types)
    E   BEN5K Unverified → creation PASSES
    F   COMTRADE not-assessed → creation PASSES
    CA-7  COMTRADE not-assessed + BEN5K Invalid → creation raises
    CA-8  COMTRADE not-assessed + BEN5K Unverified → creation PASSES
    CA-9  BEN5K, Invalid, channel absent from registry → channel_not_found_ben5k
    CA-10 Depth-3 chain with BEN5K Invalid leaf → creation raises

  Evaluation-time (EV / G–I):
    G   Invalid leaf → waveform raises InvalidCalibrationAuthorityError
    H   Invalid leaf → cursor raises InvalidCalibrationAuthorityError
    I   Invalid leaf → peak raises InvalidCalibrationAuthorityError
    J   Invalid leaf → annotation raises InvalidCalibrationAuthorityError
    EV-2  BEN5K Unverified → evaluation PASSES (exploratory allowed)
    EV-4  COMTRADE not-assessed → evaluation PASSES
    EV-5  Calc chain with Invalid leaf → evaluation raises

  Preservation (K–N):
    K   Source removed → cascade deletes calc channel; no stale state
    L   Stage 3B-2B-1 PU gate still returns calibration_unavailable for Unverified
    M   source_registry=None → guard skipped (backward compat for tests)
    N   BEN5K Unverified ENG values unchanged (not Invalid; no Stage 3B-2B-2 effect)

Governance: Stage 3B-2B-2 — gate only.
  No calibration correction factors applied.
  No new PU bases assigned.
  Stage 3B-2C, 3B-3 and Slice 6D NOT activated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import (
    CalculatedChannel,
    ChannelRef,
    NULL_POLICY_PROPAGATE,
    OP_ADDITION,
    OP_ACTIVE_POWER,
    OP_REVERSE_POLARITY,
    OP_SUBTRACTION,
)
from app.domain.channel_classification import CURRENT, POWER, VOLTAGE
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import FORMAT_VARIANT_BEN5K_LEGACY, RecordingMetadata
from app.domain.per_unit import STATUS_CALIBRATION_UNAVAILABLE
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
    _resolve_effective_per_unit_for_calculated_channel,
    create_calculated_channel,
    extract_calculated_cursor_values,
    extract_calculated_waveform_range,
    resolve_calculated_annotation_anchor,
    resolve_calculated_peak_value,
)
from app.services.errors import InvalidCalibrationAuthorityError
from app.services.workspace_registry import WorkspaceRegistry

# ---------------------------------------------------------------------------
# Well-known authorities
# ---------------------------------------------------------------------------

_UNVERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_UNVERIFIED,
    reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    transform_id="ben5k_v1_raw_s16",
)
_VERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_VERIFIED,
    reason="lab_verified",
    transform_id="ben5k_v1_raw_s16",
)
_INVALID_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_INVALID,
    reason="transform_id_mismatch_invalidated",
    transform_id="ben5k_v1_raw_s16",
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

WS = "ws-3b2b2-test"
_N = 20
_TIME = np.arange(_N, dtype=np.float64) * 0.001
_VALS = np.ones(_N, dtype=np.float64) * 5.0
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

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
    """Minimal ActiveSource for calibration-gate testing."""
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
    """Minimal CalculatedChannel for gate testing (pre-built, no calculation)."""
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


def _source_registry(sources: list[ActiveSource]) -> WorkspaceRegistry:
    r = WorkspaceRegistry()
    for s in sources:
        r.add(s)
    return r


def _calc_registry(channels: list[CalculatedChannel]) -> CalculatedChannelRegistry:
    r = CalculatedChannelRegistry()
    for c in channels:
        r.add(c)
    return r


# ---------------------------------------------------------------------------
# Creation-time gate tests
# ---------------------------------------------------------------------------


class TestCreationGateInvalidAuthority:
    """OD-5 strict: creation gate fires for all engineering types."""

    def test_a_direct_invalid_voltage_source_blocked(self):
        """A: Direct Invalid source (VOLTAGE) → creation raises."""
        source_id = "src-invalid"
        source = _make_active_source(
            source_id=source_id,
            channel_name="VA",
            engineering_type=VOLTAGE,
            calibration_authority=_INVALID_AUTH,
        )
        sr = _source_registry([source])
        cr = CalculatedChannelRegistry()

        with pytest.raises(InvalidCalibrationAuthorityError) as exc_info:
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_A",
                operation=OP_REVERSE_POLARITY,
                inputs=[ChannelRef(kind="source", source_id=source_id, channel_name="VA")],
                parameters={},
                source_registry=sr,
                calc_registry=cr,
            )
        assert exc_info.value.code == "invalid_calibration_authority"

    def test_b_nested_chain_with_invalid_leaf_blocked(self):
        """B: Existing calc channel over Invalid leaf → new calc chain raises."""
        src_id = "src-invalid-b"
        src = _make_active_source(
            source_id=src_id, channel_name="VA", calibration_authority=_INVALID_AUTH,
        )
        inner_calc_id = "calc-inner-b"
        inner = _make_calc_channel(
            calc_id=inner_calc_id, name="inner_b",
            inputs=[ChannelRef(kind="source", source_id=src_id, channel_name="VA")],
        )
        sr = _source_registry([src])
        cr = _calc_registry([inner])

        with pytest.raises(InvalidCalibrationAuthorityError):
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_B",
                operation=OP_REVERSE_POLARITY,
                inputs=[ChannelRef(kind="calculated", calculated_channel_id=inner_calc_id)],
                parameters={},
                source_registry=sr,
                calc_registry=cr,
            )

    def test_c_mixed_invalid_verified_blocked(self):
        """C: Mixed Invalid + Verified → creation raises (any Invalid wins)."""
        src_v = _make_active_source(
            source_id="src-v", channel_name="VA", calibration_authority=_VERIFIED_AUTH,
        )
        src_i = _make_active_source(
            source_id="src-i", channel_name="VA", calibration_authority=_INVALID_AUTH,
        )
        sr = _source_registry([src_v, src_i])
        cr = CalculatedChannelRegistry()

        with pytest.raises(InvalidCalibrationAuthorityError):
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_C",
                operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id="src-v", channel_name="VA"),
                    ChannelRef(kind="source", source_id="src-i", channel_name="VA"),
                ],
                parameters={},
                source_registry=sr,
                calc_registry=cr,
            )

    def test_d_invalid_power_type_also_blocked(self):
        """D: Direct Invalid source (POWER engineering context) → creation raises (OD-5: all types).

        OD-5 is strict: even a POWER or UNDEFINED channel with an Invalid authority
        source is rejected — there is no OD-4 exception for the creation gate.

        Uses a Voltage + Current power pair where the Voltage input has Invalid authority.
        """
        src_v = _make_active_source(
            source_id="src-v-power", channel_name="VA",
            engineering_type=VOLTAGE, unit="kV",
            calibration_authority=_INVALID_AUTH,
        )
        src_i = _make_active_source(
            source_id="src-i-power", channel_name="IA",
            engineering_type=CURRENT, unit="kA",
            format_variant=None, calibration_authority=None,
        )
        sr = _source_registry([src_v, src_i])
        cr = CalculatedChannelRegistry()

        with pytest.raises(InvalidCalibrationAuthorityError):
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_D",
                operation=OP_ACTIVE_POWER,
                inputs=[
                    ChannelRef(kind="source", source_id="src-v-power", channel_name="VA"),
                    ChannelRef(kind="source", source_id="src-i-power", channel_name="IA"),
                ],
                parameters={"null_policy": NULL_POLICY_PROPAGATE},
                source_registry=sr,
                calc_registry=cr,
            )

    def test_e_ben5k_unverified_creation_passes(self):
        """E: BEN5K Unverified → creation PASSES (Unverified allowed for exploratory)."""
        src = _make_active_source(
            source_id="src-unverified", channel_name="VA",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        sr = _source_registry([src])
        cr = CalculatedChannelRegistry()

        channel = create_calculated_channel(
            workspace_id=WS,
            name="TestCalc_E",
            operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src-unverified", channel_name="VA")],
            parameters={},
            source_registry=sr,
            calc_registry=cr,
        )
        assert channel.name == "TestCalc_E"

    def test_f_comtrade_not_assessed_creation_passes(self):
        """F: COMTRADE not-assessed → creation PASSES (backward compat)."""
        src = _make_active_source(
            source_id="src-comtrade", channel_name="VA",
            format_variant=None, calibration_authority=None,
        )
        sr = _source_registry([src])
        cr = CalculatedChannelRegistry()

        channel = create_calculated_channel(
            workspace_id=WS,
            name="TestCalc_F",
            operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src-comtrade", channel_name="VA")],
            parameters={},
            source_registry=sr,
            calc_registry=cr,
        )
        assert channel.name == "TestCalc_F"

    def test_ca7_comtrade_not_assessed_plus_ben5k_invalid_blocked(self):
        """CA-7: COMTRADE not-assessed + BEN5K Invalid → creation raises."""
        src_c = _make_active_source(
            source_id="src-comtrade-7", channel_name="VA",
            format_variant=None, calibration_authority=None,
        )
        src_i = _make_active_source(
            source_id="src-invalid-7", channel_name="VA",
            calibration_authority=_INVALID_AUTH,
        )
        sr = _source_registry([src_c, src_i])
        cr = CalculatedChannelRegistry()

        with pytest.raises(InvalidCalibrationAuthorityError):
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_CA7",
                operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id="src-comtrade-7", channel_name="VA"),
                    ChannelRef(kind="source", source_id="src-invalid-7", channel_name="VA"),
                ],
                parameters={},
                source_registry=sr,
                calc_registry=cr,
            )

    def test_ca8_comtrade_not_assessed_plus_ben5k_unverified_passes(self):
        """CA-8: COMTRADE not-assessed + BEN5K Unverified → creation PASSES."""
        src_c = _make_active_source(
            source_id="src-comtrade-8", channel_name="VA",
            format_variant=None, calibration_authority=None,
        )
        src_u = _make_active_source(
            source_id="src-unverified-8", channel_name="VA",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        sr = _source_registry([src_c, src_u])
        cr = CalculatedChannelRegistry()

        channel = create_calculated_channel(
            workspace_id=WS,
            name="TestCalc_CA8",
            operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src-comtrade-8", channel_name="VA"),
                ChannelRef(kind="source", source_id="src-unverified-8", channel_name="VA"),
            ],
            parameters={},
            source_registry=sr,
            calc_registry=cr,
        )
        assert channel.name == "TestCalc_CA8"

    def test_ca9_ben5k_invalid_channel_missing_raises(self):
        """CA-9: BEN5K, Invalid auth, referencing non-existent channel → channel_not_found_ben5k."""
        # Source has channel 'VA' but we reference 'VB'
        src = _make_active_source(
            source_id="src-9", channel_name="VA",
            calibration_authority=_INVALID_AUTH,
        )
        sr = _source_registry([src])
        cr = CalculatedChannelRegistry()

        with pytest.raises(InvalidCalibrationAuthorityError) as exc_info:
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_CA9",
                operation=OP_REVERSE_POLARITY,
                inputs=[ChannelRef(kind="source", source_id="src-9", channel_name="VB")],
                parameters={},
                source_registry=sr,
                calc_registry=cr,
            )
        assert exc_info.value.reason == "channel_not_found_ben5k"

    def test_ca10_depth3_chain_invalid_leaf_blocked(self):
        """CA-10: Depth-3 chain BEN5K Invalid → creation raises (chain traversal)."""
        src_id = "src-10"
        src = _make_active_source(
            source_id=src_id, channel_name="VA",
            calibration_authority=_INVALID_AUTH,
        )
        calc1_id = "calc1-10"
        calc1 = _make_calc_channel(
            calc_id=calc1_id, name="calc1_10",
            inputs=[ChannelRef(kind="source", source_id=src_id, channel_name="VA")],
        )
        calc2_id = "calc2-10"
        calc2 = _make_calc_channel(
            calc_id=calc2_id, name="calc2_10",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=calc1_id)],
        )
        sr = _source_registry([src])
        cr = _calc_registry([calc1, calc2])

        with pytest.raises(InvalidCalibrationAuthorityError):
            create_calculated_channel(
                workspace_id=WS,
                name="TestCalc_CA10",
                operation=OP_REVERSE_POLARITY,
                inputs=[ChannelRef(kind="calculated", calculated_channel_id=calc2_id)],
                parameters={},
                source_registry=sr,
                calc_registry=cr,
            )


# ---------------------------------------------------------------------------
# Evaluation-time gate tests
# ---------------------------------------------------------------------------


class TestEvaluationGateInvalidAuthority:
    """OD-6: evaluation-time Invalid → structured API error (raises), unconditional on unit_mode."""

    def _invalid_setup(self) -> tuple[CalculatedChannel, WorkspaceRegistry, CalculatedChannelRegistry]:
        """Build channel + registries with an Invalid leaf source."""
        src_id = "src-eval-invalid"
        src = _make_active_source(
            source_id=src_id, channel_name="VA",
            calibration_authority=_INVALID_AUTH,
        )
        channel = _make_calc_channel(
            calc_id="calc-eval-invalid",
            inputs=[ChannelRef(kind="source", source_id=src_id, channel_name="VA")],
        )
        sr = _source_registry([src])
        cr = _calc_registry([channel])
        return channel, sr, cr

    def test_g_waveform_raises_for_invalid_leaf(self):
        """G: waveform endpoint raises InvalidCalibrationAuthorityError for Invalid leaf."""
        channel, sr, cr = self._invalid_setup()
        with pytest.raises(InvalidCalibrationAuthorityError) as exc_info:
            extract_calculated_waveform_range(
                channel, start_time=None, end_time=None,
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )
        assert exc_info.value.code == "invalid_calibration_authority"

    def test_h_cursor_raises_for_invalid_leaf(self):
        """H: cursor endpoint raises InvalidCalibrationAuthorityError for Invalid leaf."""
        channel, sr, cr = self._invalid_setup()
        with pytest.raises(InvalidCalibrationAuthorityError):
            extract_calculated_cursor_values(
                [channel], cursor_a_time=0.005, cursor_b_time=0.010,
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )

    def test_i_peak_raises_for_invalid_leaf(self):
        """I: peak endpoint raises InvalidCalibrationAuthorityError for Invalid leaf."""
        channel, sr, cr = self._invalid_setup()
        with pytest.raises(InvalidCalibrationAuthorityError):
            resolve_calculated_peak_value(
                channel, mode="max",
                start_time=float(_TIME[0]), end_time=float(_TIME[-1]),
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )

    def test_j_annotation_raises_for_invalid_leaf(self):
        """J: annotation endpoint raises InvalidCalibrationAuthorityError for Invalid leaf."""
        channel, sr, cr = self._invalid_setup()
        with pytest.raises(InvalidCalibrationAuthorityError):
            resolve_calculated_annotation_anchor(
                channel, approximate_elapsed_seconds=0.005,
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )

    def test_g_waveform_in_pu_mode_also_raises(self):
        """G (PU mode): evaluation-time guard fires even in per_unit mode (unconditional)."""
        channel, sr, cr = self._invalid_setup()
        with pytest.raises(InvalidCalibrationAuthorityError):
            extract_calculated_waveform_range(
                channel, start_time=None, end_time=None,
                unit_mode="per_unit",
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )

    def test_ev2_unverified_evaluation_passes(self):
        """EV-2: BEN5K Unverified (not Invalid) → evaluation PASSES."""
        src = _make_active_source(
            source_id="src-unv-ev2", channel_name="VA",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src-unv-ev2", channel_name="VA")],
        )
        sr = _source_registry([src])
        cr = _calc_registry([channel])

        # Should not raise
        result = extract_calculated_waveform_range(
            channel, start_time=None, end_time=None,
            workspace_id=WS, source_registry=sr, calc_registry=cr,
        )
        assert result.unit == "kV"

    def test_ev4_comtrade_not_assessed_evaluation_passes(self):
        """EV-4: COMTRADE not-assessed → evaluation PASSES (backward compat)."""
        src = _make_active_source(
            source_id="src-comtrade-ev4", channel_name="VA",
            format_variant=None, calibration_authority=None,
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src-comtrade-ev4", channel_name="VA")],
        )
        sr = _source_registry([src])
        cr = _calc_registry([channel])

        result = extract_calculated_waveform_range(
            channel, start_time=None, end_time=None,
            workspace_id=WS, source_registry=sr, calc_registry=cr,
        )
        assert result.unit == "kV"

    def test_ev5_calc_chain_with_invalid_leaf_evaluation_raises(self):
        """EV-5: Calc chain with Invalid leaf → evaluation raises."""
        src_id = "src-ev5"
        src = _make_active_source(
            source_id=src_id, channel_name="VA",
            calibration_authority=_INVALID_AUTH,
        )
        inner_id = "calc-inner-ev5"
        inner = _make_calc_channel(
            calc_id=inner_id,
            inputs=[ChannelRef(kind="source", source_id=src_id, channel_name="VA")],
        )
        outer = _make_calc_channel(
            calc_id="calc-outer-ev5",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=inner_id)],
        )
        sr = _source_registry([src])
        cr = _calc_registry([inner, outer])

        with pytest.raises(InvalidCalibrationAuthorityError):
            extract_calculated_waveform_range(
                outer, start_time=None, end_time=None,
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )

    def test_deep_chain_invalid_leaf_evaluation_raises(self):
        """Deep chain (3 hops) with Invalid leaf → evaluation raises."""
        src_id = "src-deep"
        src = _make_active_source(
            source_id=src_id, channel_name="VA",
            calibration_authority=_INVALID_AUTH,
        )
        c1_id, c2_id, c3_id = "calc-d1", "calc-d2", "calc-d3"
        c1 = _make_calc_channel(
            calc_id=c1_id, inputs=[ChannelRef(kind="source", source_id=src_id, channel_name="VA")]
        )
        c2 = _make_calc_channel(
            calc_id=c2_id, inputs=[ChannelRef(kind="calculated", calculated_channel_id=c1_id)]
        )
        c3 = _make_calc_channel(
            calc_id=c3_id, inputs=[ChannelRef(kind="calculated", calculated_channel_id=c2_id)]
        )
        sr = _source_registry([src])
        cr = _calc_registry([c1, c2, c3])

        with pytest.raises(InvalidCalibrationAuthorityError):
            extract_calculated_waveform_range(
                c3, start_time=None, end_time=None,
                workspace_id=WS, source_registry=sr, calc_registry=cr,
            )


# ---------------------------------------------------------------------------
# Preservation regression tests
# ---------------------------------------------------------------------------


class TestStage3B2B2Preservation:
    """Confirm Stage 3B-2B-1 PU gate and backward-compat cases are unaffected."""

    def test_k_source_removed_cascade_no_stale_state(self):
        """K: After source removal, the calc channel is removed via cascade.
        A fresh import creates a new source_id, so the old calc channel
        (referencing old source_id) is gone — no stale state to evaluate."""
        from app.services.calculated_channel_service import remove_calculated_channels_for_source

        src_id = "src-stale"
        src = _make_active_source(source_id=src_id, channel_name="VA", calibration_authority=None)
        channel = _make_calc_channel(
            calc_id="calc-stale",
            inputs=[ChannelRef(kind="source", source_id=src_id, channel_name="VA")],
            reference_source_id=src_id,
        )
        sr = _source_registry([src])
        cr = _calc_registry([channel])

        # Cascade delete simulates source removal before reimport
        remove_calculated_channels_for_source(workspace_id=WS, source_id=src_id, calc_registry=cr)
        assert cr.get(WS, "calc-stale") is None

    def test_l_stage3b2b1_pu_gate_still_blocks_unverified_on_pu_path(self):
        """L: Unverified source → PU path still returns calibration_unavailable (Stage 3B-2B-1 intact)."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src-unv-l", channel_name="VA")],
            engineering_type=VOLTAGE,
        )
        src = _make_active_source(
            source_id="src-unv-l", channel_name="VA",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        sr = _source_registry([src])
        cr = _calc_registry([channel])

        resolution = _resolve_effective_per_unit_for_calculated_channel(
            channel, None, None,
            workspace_id=WS, source_registry=sr, calc_registry=cr,
        )
        assert resolution.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_m_source_registry_none_guard_skipped(self):
        """M: source_registry=None → evaluation-time guard is skipped (backward compat for direct tests)."""
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src-none", channel_name="VA")],
        )
        # No registries — guard is skipped, function runs normally (no crash)
        result = extract_calculated_waveform_range(
            channel, start_time=None, end_time=None,
            # source_registry=None, workspace_id=None → guard skipped
        )
        assert result.unit == "kV"

    def test_n_unverified_ben5k_eng_values_unchanged(self):
        """N: BEN5K Unverified (not Invalid) → ENG values unchanged by Stage 3B-2B-2."""
        src = _make_active_source(
            source_id="src-unv-n", channel_name="VA",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        channel = _make_calc_channel(
            inputs=[ChannelRef(kind="source", source_id="src-unv-n", channel_name="VA")],
        )
        sr = _source_registry([src])
        cr = _calc_registry([channel])

        result = extract_calculated_waveform_range(
            channel, start_time=None, end_time=None,
            unit_mode="engineering",
            workspace_id=WS, source_registry=sr, calc_registry=cr,
        )
        # ENG values are the channel's own stored values — unchanged
        assert result.unit == "kV"
        np.testing.assert_array_equal(result.values, channel.values)
