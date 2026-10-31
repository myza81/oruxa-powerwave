"""Engineering and service-level tests for Slice 3 single-phase power
calculated channels (DEC-202): active_power, reactive_power, apparent_power.

Covers:
  - evaluate_power_channel() domain function (unit, numerical correctness,
    passive sign convention, unit scaling, NaN propagation)
  - create_calculated_channel() service integration (arity guard, type guard,
    unit guard, RMS data-quality guards, successful creation, output metadata)
  - Numerical equivalence: evaluate_power_channel() vs single_phase_power()
    (Item 2 of Slice 3 Engineering Verification)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import cmath

from app.domain.calculated_channel import (
    OP_ACTIVE_POWER,
    OP_APPARENT_POWER,
    OP_REACTIVE_POWER,
    ChannelRef,
    evaluate_power_channel,
)
from app.domain.power_calculation import single_phase_power
from app.domain.sliding_phasor import compute_sliding_phasor
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.errors import (
    IncompatibleTimeBaseError,
    InvalidOperationArityError,
    InvalidPowerInputTypeError,
    InvalidPowerInputUnitError,
    RmsRecordingTooShortError,
    RmsSamplingTooSparseError,
)
from app.services.workspace_registry import WorkspaceRegistry

import pandas as pd
from datetime import datetime, timezone

WS = "ws-1"
BASE_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
F0_HZ = 50.0
FS_HZ = 5000.0  # 100 samples/cycle — well above density threshold


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _active_source(
    *,
    source_id: str,
    time: np.ndarray,
    channels: dict[str, np.ndarray],
    units: dict[str, str] | None = None,
    engineering_types: dict[str, str] | None = None,
    waveform_forms: dict[str, str] | None = None,
    start_time: datetime | None = BASE_START,
) -> ActiveSource:
    units = units or {}
    engineering_types = engineering_types or {}
    waveform_forms = waveform_forms or {}
    col_data = {"time": time, **channels}
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH", recorder_name="TEST", source_file="synthetic.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(col_data),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(time)]),
        timing_info=TimingInformation(start_time=BASE_START, trigger_time=BASE_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE",
        original_filenames=("synthetic.cfg", "synthetic.dat"), created_at=BASE_START,
        station_name="SYNTH", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference="absolute", start_time=start_time, trigger_time=start_time,
        sample_count=len(time), duration_seconds=float(time[-1] - time[0]) if len(time) else 0.0,
        elapsed_start_seconds=float(time[0]) if len(time) else 0.0,
        elapsed_end_seconds=float(time[-1]) if len(time) else 0.0,
        sampling_rates=(1.0,), samples_per_rate=(len(time),),
        analog_channels=[
            AnalogChannelSummary(
                name=name, index=i, unit=units.get(name, "V"),
                engineering_type=engineering_types.get(name, "Voltage"),
                waveform_form=waveform_forms.get(name, WAVEFORM_FORM_UNKNOWN),
            )
            for i, name in enumerate(channels)
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _two_channel_source(
    *,
    source_id: str = "src1",
    fs: float = FS_HZ,
    duration: float = 0.5,
    v_amplitude_v: float = 1000.0,
    i_amplitude_a: float = 1.0,
    i_phase_offset_deg: float = 0.0,
    v_unit: str = "V",
    i_unit: str = "A",
    v_eng_type: str = "Voltage",
    i_eng_type: str = "Current",
) -> tuple[WorkspaceRegistry, CalculatedChannelRegistry]:
    """Builds a source with VA (voltage) and IA (current) channels sharing the
    same timebase, and returns pre-populated registries."""
    n = int(round(fs * duration))
    time = np.arange(n, dtype=np.float64) / fs
    phi = math.radians(i_phase_offset_deg)
    v_values = v_amplitude_v * np.sin(2 * np.pi * F0_HZ * time)
    i_values = i_amplitude_a * np.sin(2 * np.pi * F0_HZ * time + phi)

    source_registry, calc_registry = _registries()
    source_registry.add(_active_source(
        source_id=source_id, time=time,
        channels={"VA": v_values, "IA": i_values},
        units={"VA": v_unit, "IA": i_unit},
        engineering_types={"VA": v_eng_type, "IA": i_eng_type},
        waveform_forms={"VA": WAVEFORM_FORM_INSTANTANEOUS, "IA": WAVEFORM_FORM_INSTANTANEOUS},
    ))
    return source_registry, calc_registry


def _v_ref(source_id: str = "src1") -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name="VA")


def _i_ref(source_id: str = "src1") -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name="IA")


# ---------------------------------------------------------------------------
# Domain-level tests: evaluate_power_channel()
# ---------------------------------------------------------------------------

class TestEvaluatePowerChannelNumerics:
    """Verify the domain function computes correct MW/Mvar/MVA values."""

    def _steady_sinusoid(
        self, v_amp_v: float, i_amp_a: float, phase_deg: float
    ) -> tuple[np.ndarray, np.ndarray]:
        n = int(FS_HZ * 2.0)  # 2 seconds — several cycles
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v = v_amp_v * np.sin(2 * np.pi * F0_HZ * time)
        phi = math.radians(phase_deg)
        i = i_amp_a * np.sin(2 * np.pi * F0_HZ * time + phi)
        return time, v, i

    def _steady_result(
        self, operation: str, v_amp_v: float, i_amp_a: float, phase_deg: float
    ) -> np.ndarray:
        time, v, i = self._steady_sinusoid(v_amp_v, i_amp_a, phase_deg)
        return evaluate_power_channel(
            operation, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )

    def test_active_power_in_phase(self):
        # V and I in phase: P = Vrms × Irms = (Vp/√2) × (Ip/√2) = Vp×Ip/2
        vp, ip = 1000.0, 1.0
        expected_p_mw = vp * ip / 2.0 / 1e6
        result = self._steady_result(OP_ACTIVE_POWER, vp, ip, 0.0)
        # Skip transient first cycle and test steady-state tail
        steady = result[int(FS_HZ * 1.0):]  # last second
        assert np.nanmean(steady) == pytest.approx(expected_p_mw, rel=0.01)

    def test_active_power_quadrature_zero(self):
        # V and I 90° apart: P should be ~0
        vp, ip = 1000.0, 1.0
        result = self._steady_result(OP_ACTIVE_POWER, vp, ip, 90.0)
        steady = result[int(FS_HZ * 1.0):]
        assert abs(np.nanmean(steady)) < 1e-6  # MW — effectively zero

    def test_reactive_power_in_phase_zero(self):
        # V and I in phase: Q = 0
        vp, ip = 1000.0, 1.0
        result = self._steady_result(OP_REACTIVE_POWER, vp, ip, 0.0)
        steady = result[int(FS_HZ * 1.0):]
        assert abs(np.nanmean(steady)) < 1e-6

    def test_reactive_power_quadrature(self):
        # I lags V by 90° (inductive load): Q = Vrms×Irms > 0 in passive S=V×conj(I)
        # phase_offset = -90° means i = sin(ωt − π/2) → I phasor lags V by 90°
        vp, ip = 1000.0, 1.0
        expected_q_mvar = vp * ip / 2.0 / 1e6
        result = self._steady_result(OP_REACTIVE_POWER, vp, ip, -90.0)
        steady = result[int(FS_HZ * 1.0):]
        assert np.nanmean(steady) == pytest.approx(expected_q_mvar, rel=0.01)

    def test_apparent_power_matches_s_magnitude(self):
        # |S| = Vrms × Irms = Vp×Ip/2, regardless of phase angle
        vp, ip = 1000.0, 1.0
        expected_s_mva = vp * ip / 2.0 / 1e6
        for phase_deg in [0.0, 30.0, 45.0, 90.0]:
            result = self._steady_result(OP_APPARENT_POWER, vp, ip, phase_deg)
            steady = result[int(FS_HZ * 1.0):]
            assert np.nanmean(steady) == pytest.approx(expected_s_mva, rel=0.01), (
                f"phase_deg={phase_deg}"
            )

    def test_p_q_s_triangle_relationship(self):
        # |S|² = P² + Q² must hold sample-by-sample in the steady state
        vp, ip = 1000.0, 1.0
        phase_deg = 36.87  # ~0.8 power-factor angle
        time, v, i = self._steady_sinusoid(vp, ip, phase_deg)
        p = evaluate_power_channel(OP_ACTIVE_POWER, v_time=time, v_values=v, v_scale_to_si=1.0, i_values=i, i_scale_to_si=1.0)
        q = evaluate_power_channel(OP_REACTIVE_POWER, v_time=time, v_values=v, v_scale_to_si=1.0, i_values=i, i_scale_to_si=1.0)
        s = evaluate_power_channel(OP_APPARENT_POWER, v_time=time, v_values=v, v_scale_to_si=1.0, i_values=i, i_scale_to_si=1.0)
        # Evaluate in steady-state only (skip first cycle transient)
        idx = slice(int(FS_HZ * 1.0), None)
        np.testing.assert_allclose(s[idx] ** 2, p[idx] ** 2 + q[idx] ** 2, rtol=1e-6)

    def test_passive_sign_convention(self):
        # Passive sign convention S = V × conj(I):
        # I leads V by 90° (capacitive load): S = V × conj(I) → Im(S) < 0 → Q < 0
        # phase_offset = +90° means i = sin(ωt + π/2) = cos(ωt) → I phasor leads V
        vp, ip = 1000.0, 1.0
        result = self._steady_result(OP_REACTIVE_POWER, vp, ip, 90.0)
        steady = result[int(FS_HZ * 1.0):]
        assert np.nanmean(steady) < 0, "Q should be negative when I leads V by 90° (passive convention)"

    def test_unit_scale_kv_ka_to_mw(self):
        # 1 kV (amplitude) × 1 kA (amplitude) in phase → P ≈ 0.5 MW
        # scale_to_si: kV=1000, kA=1000
        n = int(FS_HZ * 2.0)
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v_kv = np.sin(2 * np.pi * F0_HZ * time)   # 1 kV amplitude
        i_ka = np.sin(2 * np.pi * F0_HZ * time)   # 1 kA amplitude
        result = evaluate_power_channel(
            OP_ACTIVE_POWER, v_time=time,
            v_values=v_kv, v_scale_to_si=1000.0,  # kV → V
            i_values=i_ka, i_scale_to_si=1000.0,  # kA → A
        )
        steady = result[int(FS_HZ * 1.0):]
        # Expected: (1000 V)×(1000 A)/2 / 1e6 = 0.5 MW
        assert np.nanmean(steady) == pytest.approx(0.5, rel=0.01)

    def test_nan_propagation_in_output(self):
        # NaN in V at an index → NaN in output at that same index
        n = int(FS_HZ * 1.0)
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v = np.sin(2 * np.pi * F0_HZ * time)
        i = np.sin(2 * np.pi * F0_HZ * time)
        nan_idx = n // 2
        v[nan_idx] = np.nan
        result = evaluate_power_channel(
            OP_ACTIVE_POWER, v_time=time,
            v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        # At least one NaN must appear in the output (sliding window may
        # propagate it across a window width, not just one sample).
        assert np.any(np.isnan(result))


# ---------------------------------------------------------------------------
# Service-level tests: create_calculated_channel() with power operations
# ---------------------------------------------------------------------------

class TestPowerChannelArityGuard:
    def test_zero_inputs_raises(self):
        sr, cr = _two_channel_source()
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[], parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_one_input_raises(self):
        sr, cr = _two_channel_source()
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref()], parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_three_inputs_raises(self):
        sr, cr = _two_channel_source()
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref(), _v_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )


class TestPowerChannelTypeGuard:
    def test_current_in_voltage_slot_raises(self):
        # Slot 0 must be Voltage or Undefined; Current is rejected
        sr, cr = _two_channel_source(v_eng_type="Current", i_eng_type="Current")
        with pytest.raises(InvalidPowerInputTypeError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_voltage_in_current_slot_raises(self):
        # Slot 1 must be Current or Undefined; Voltage is rejected
        sr, cr = _two_channel_source(v_eng_type="Voltage", i_eng_type="Voltage")
        with pytest.raises(InvalidPowerInputTypeError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_undefined_in_both_slots_accepted(self):
        # Undefined engineering type is allowed in either slot
        sr, cr = _two_channel_source(v_eng_type="Undefined", i_eng_type="Undefined")
        channel = create_calculated_channel(
            workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
            inputs=[_v_ref(), _i_ref()],
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert channel is not None

    def test_frequency_type_in_voltage_slot_raises(self):
        sr, cr = _two_channel_source(v_eng_type="Frequency", i_eng_type="Current")
        with pytest.raises(InvalidPowerInputTypeError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )


class TestPowerChannelUnitGuard:
    def test_blank_voltage_unit_raises(self):
        sr, cr = _two_channel_source(v_unit="", i_unit="A")
        with pytest.raises(InvalidPowerInputUnitError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_blank_current_unit_raises(self):
        sr, cr = _two_channel_source(v_unit="kV", i_unit="")
        with pytest.raises(InvalidPowerInputUnitError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_unrecognized_voltage_unit_raises(self):
        sr, cr = _two_channel_source(v_unit="pu", i_unit="A")
        with pytest.raises(InvalidPowerInputUnitError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_unrecognized_current_unit_raises(self):
        sr, cr = _two_channel_source(v_unit="V", i_unit="pu")
        with pytest.raises(InvalidPowerInputUnitError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_kv_and_ka_units_accepted(self):
        sr, cr = _two_channel_source(v_unit="kV", i_unit="kA")
        channel = create_calculated_channel(
            workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
            inputs=[_v_ref(), _i_ref()],
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert channel is not None


class TestPowerChannelDataQualityGuard:
    def test_recording_too_short_raises(self):
        # Less than one 50 Hz window (20 ms)
        n = int(FS_HZ * 0.005)  # 5 ms
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v = np.sin(2 * np.pi * F0_HZ * time)
        i = np.sin(2 * np.pi * F0_HZ * time)
        sr, cr = _registries()
        sr.add(_active_source(
            source_id="src1", time=time,
            channels={"VA": v, "IA": i},
            units={"VA": "V", "IA": "A"},
            engineering_types={"VA": "Voltage", "IA": "Current"},
            waveform_forms={"VA": WAVEFORM_FORM_INSTANTANEOUS, "IA": WAVEFORM_FORM_INSTANTANEOUS},
        ))
        with pytest.raises(RmsRecordingTooShortError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_sampling_too_sparse_raises(self):
        # 100 Hz sampling — only 2 samples/cycle for 50 Hz
        fs_sparse = 100.0
        n = int(fs_sparse * 1.0)  # 1 second
        time = np.arange(n, dtype=np.float64) / fs_sparse
        v = np.sin(2 * np.pi * F0_HZ * time)
        i = np.sin(2 * np.pi * F0_HZ * time)
        sr, cr = _registries()
        sr.add(_active_source(
            source_id="src1", time=time,
            channels={"VA": v, "IA": i},
            units={"VA": "V", "IA": "A"},
            engineering_types={"VA": "Voltage", "IA": "Current"},
            waveform_forms={"VA": WAVEFORM_FORM_INSTANTANEOUS, "IA": WAVEFORM_FORM_INSTANTANEOUS},
        ))
        with pytest.raises(RmsSamplingTooSparseError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )


class TestPowerChannelCrossSourceGuard:
    def test_different_reference_source_raises(self):
        # Two sources with independent absolute timebases cannot be combined
        n = int(FS_HZ * 0.5)
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v = np.sin(2 * np.pi * F0_HZ * time)
        i = np.sin(2 * np.pi * F0_HZ * time)

        from datetime import timedelta
        start2 = BASE_START + timedelta(seconds=1)

        sr, cr = _registries()
        sr.add(_active_source(
            source_id="src1", time=time, channels={"VA": v},
            units={"VA": "V"}, engineering_types={"VA": "Voltage"},
        ))
        sr.add(_active_source(
            source_id="src2", time=time, channels={"IA": i},
            units={"IA": "A"}, engineering_types={"IA": "Current"},
            start_time=start2,
        ))
        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="P", operation=OP_ACTIVE_POWER,
                inputs=[
                    ChannelRef(kind="source", source_id="src1", channel_name="VA"),
                    ChannelRef(kind="source", source_id="src2", channel_name="IA"),
                ],
                parameters={}, source_registry=sr, calc_registry=cr,
            )


class TestPowerChannelSuccessfulCreation:
    def _create_power(self, operation: str, name: str = "P", **kwargs) -> object:
        sr, cr = _two_channel_source(**kwargs)
        return create_calculated_channel(
            workspace_id=WS, name=name, operation=operation,
            inputs=[_v_ref(), _i_ref()],
            parameters={}, source_registry=sr, calc_registry=cr,
        )

    # --- Output unit ---

    def test_active_power_unit_is_mw(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        assert ch.unit == "MW"

    def test_reactive_power_unit_is_mvar(self):
        ch = self._create_power(OP_REACTIVE_POWER, name="Q")
        assert ch.unit == "Mvar"

    def test_apparent_power_unit_is_mva(self):
        ch = self._create_power(OP_APPARENT_POWER, name="S")
        assert ch.unit == "MVA"

    # --- Output engineering_type ---

    def test_engineering_type_is_power(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        assert ch.engineering_type == "Power"

    # --- Output waveform_form ---

    def test_waveform_form_is_rms(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        assert ch.waveform_form == WAVEFORM_FORM_RMS

    # --- Output parameters ---

    def test_parameters_stored(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        assert ch.parameters["nominal_frequency_hz"] == 50.0
        assert ch.parameters["window_mode"] == "trailing"
        assert ch.parameters["sign_convention"] == "passive"

    # --- Reference source is the voltage input's source ---

    def test_reference_source_id_is_voltage_source(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        assert ch.reference_source_id == "src1"

    # --- Values shape and finiteness ---

    def test_values_same_length_as_time(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        assert len(ch.values) == len(ch.time)

    def test_steady_state_values_are_finite(self):
        ch = self._create_power(OP_ACTIVE_POWER)
        # Skip transient (first cycle)
        n_skip = int(FS_HZ / F0_HZ)
        assert np.isfinite(ch.values[n_skip:]).all()

    # --- Unit scaling: kV × kA → correct MW magnitude ---

    def test_kv_ka_result_magnitude(self):
        # 1 kV amplitude × 1 kA amplitude in phase → ~0.5 MW
        ch = self._create_power(
            OP_ACTIVE_POWER, name="P_scaled",
            v_amplitude_v=1.0,   # stored as kV in source
            i_amplitude_a=1.0,   # stored as kA in source
            v_unit="kV", i_unit="kA",
        )
        n_skip = int(FS_HZ / F0_HZ)
        steady = ch.values[n_skip:]
        # 1 kV peak × 1 kA peak in phase = 1000 V × 1000 A / 2 / 1e6 = 0.5 MW
        assert np.nanmean(steady) == pytest.approx(0.5, rel=0.02)

    # --- All three operations produce non-trivially different outputs ---

    def test_all_three_operations_differ_at_nonzero_angle(self):
        # At 36.87° (cos=0.8, sin=0.6), P ≠ Q ≠ S
        n = int(FS_HZ * 2.0)
        time = np.arange(n, dtype=np.float64) / FS_HZ
        vp, ip = 1000.0, 1.0
        phi = math.radians(36.87)
        v = vp * np.sin(2 * np.pi * F0_HZ * time)
        i = ip * np.sin(2 * np.pi * F0_HZ * time + phi)

        sr, cr = _registries()
        sr.add(_active_source(
            source_id="src1", time=time,
            channels={"VA": v, "IA": i},
            units={"VA": "V", "IA": "A"},
            engineering_types={"VA": "Voltage", "IA": "Current"},
            waveform_forms={"VA": WAVEFORM_FORM_INSTANTANEOUS, "IA": WAVEFORM_FORM_INSTANTANEOUS},
        ))

        def _make(operation, name):
            return create_calculated_channel(
                workspace_id=WS, name=name, operation=operation,
                inputs=[_v_ref(), _i_ref()],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

        p_ch = _make(OP_ACTIVE_POWER, "P")
        q_ch = _make(OP_REACTIVE_POWER, "Q")
        s_ch = _make(OP_APPARENT_POWER, "S")

        n_skip = int(FS_HZ * 1.0)
        p_mean = np.nanmean(p_ch.values[n_skip:])
        q_mean = np.nanmean(q_ch.values[n_skip:])
        s_mean = np.nanmean(s_ch.values[n_skip:])

        assert p_mean != pytest.approx(q_mean, rel=0.05), "P and Q should differ at 36.87°"
        assert s_mean > p_mean, "|S| >= P"
        assert s_mean > abs(q_mean), "|S| >= |Q|"


# ---------------------------------------------------------------------------
# Equivalence tests: evaluate_power_channel() vs single_phase_power()
# (Slice 3 Engineering Verification Item 2)
# ---------------------------------------------------------------------------

class TestEvaluatePowerVsSinglePhasePower:
    """Verify that evaluate_power_channel() and single_phase_power() produce
    numerically equivalent results.

    evaluate_power_channel() cannot call single_phase_power() directly because:
    1. Interface mismatch: single_phase_power() takes scalar (float, float, float,
       float) — pre-computed phasor magnitude + angle separately; evaluate_power_channel()
       receives raw time-domain sample arrays.
    2. Output mismatch: single_phase_power() returns a SinglePhasePowerResult
       dataclass (P, Q, S, power angle, PF, metadata); evaluate_power_channel()
       returns a np.ndarray of one component in MW/Mvar/MVA.
    3. Vectorisation: a Python loop over single_phase_power() on thousands of
       time steps would be orders of magnitude slower than the NumPy path.

    Both functions implement S = V × conj(I) (DEC-PWR-003 passive sign convention),
    so they must agree numerically at each time step.  The only floating-point
    difference is the trivial degree-to-radian round-trip inside _to_complex().
    """

    def _make_inputs(self, v_amp_v: float, i_amp_a: float, phase_deg: float):
        n = int(FS_HZ * 2.0)
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v = v_amp_v * np.sin(2 * np.pi * F0_HZ * time)
        phi = math.radians(phase_deg)
        i = i_amp_a * np.sin(2 * np.pi * F0_HZ * time + phi)
        return time, v, i

    def _steady_idx(self) -> int:
        """First sample index that is past the transient (≥1 full second)."""
        return int(FS_HZ * 1.0)

    def test_active_power_in_phase_pointwise(self):
        """P values from evaluate_power_channel() match single_phase_power() pointwise."""
        time, v, i = self._make_inputs(1000.0, 1.0, 0.0)
        p_arr = evaluate_power_channel(
            OP_ACTIVE_POWER, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        vr = compute_sliding_phasor(time, v, F0_HZ)
        ir = compute_sliding_phasor(time, i, F0_HZ)

        idx = self._steady_idx()
        for t in range(idx, idx + 5):  # five consecutive steady-state points
            v_mag = abs(vr.phasor[t])
            v_ang = math.degrees(cmath.phase(vr.phasor[t]))
            i_mag = abs(ir.phasor[t])
            i_ang = math.degrees(cmath.phase(ir.phasor[t]))
            sp = single_phase_power(v_mag, v_ang, i_mag, i_ang)
            np.testing.assert_allclose(
                p_arr[t],
                sp.p_watts / 1e6,
                rtol=1e-10,
                err_msg=f"Active power mismatch at index {t}",
            )

    def test_reactive_power_inductive_pointwise(self):
        """Q values match at each time step for an inductive load (I lags V 30°)."""
        time, v, i = self._make_inputs(1000.0, 1.0, -30.0)
        q_arr = evaluate_power_channel(
            OP_REACTIVE_POWER, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        vr = compute_sliding_phasor(time, v, F0_HZ)
        ir = compute_sliding_phasor(time, i, F0_HZ)

        idx = self._steady_idx()
        for t in range(idx, idx + 5):
            v_mag = abs(vr.phasor[t])
            v_ang = math.degrees(cmath.phase(vr.phasor[t]))
            i_mag = abs(ir.phasor[t])
            i_ang = math.degrees(cmath.phase(ir.phasor[t]))
            sp = single_phase_power(v_mag, v_ang, i_mag, i_ang)
            np.testing.assert_allclose(
                q_arr[t],
                sp.q_var / 1e6,
                rtol=1e-10,
                err_msg=f"Reactive power mismatch at index {t}",
            )

    def test_apparent_power_pointwise(self):
        """|S| values match at each time step regardless of phase angle."""
        time, v, i = self._make_inputs(1000.0, 1.0, 45.0)
        s_arr = evaluate_power_channel(
            OP_APPARENT_POWER, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        vr = compute_sliding_phasor(time, v, F0_HZ)
        ir = compute_sliding_phasor(time, i, F0_HZ)

        idx = self._steady_idx()
        for t in range(idx, idx + 5):
            v_mag = abs(vr.phasor[t])
            v_ang = math.degrees(cmath.phase(vr.phasor[t]))
            i_mag = abs(ir.phasor[t])
            i_ang = math.degrees(cmath.phase(ir.phasor[t]))
            sp = single_phase_power(v_mag, v_ang, i_mag, i_ang)
            np.testing.assert_allclose(
                s_arr[t],
                sp.s_va / 1e6,
                rtol=1e-10,
                err_msg=f"Apparent power mismatch at index {t}",
            )

    def test_all_three_components_match_simultaneously(self):
        """At one steady-state time step, P, Q, and |S| all match single_phase_power()."""
        time, v, i = self._make_inputs(1000.0, 1.0, 36.87)
        p_arr = evaluate_power_channel(
            OP_ACTIVE_POWER, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        q_arr = evaluate_power_channel(
            OP_REACTIVE_POWER, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        s_arr = evaluate_power_channel(
            OP_APPARENT_POWER, v_time=time, v_values=v, v_scale_to_si=1.0,
            i_values=i, i_scale_to_si=1.0,
        )
        vr = compute_sliding_phasor(time, v, F0_HZ)
        ir = compute_sliding_phasor(time, i, F0_HZ)

        t = self._steady_idx()
        v_mag = abs(vr.phasor[t])
        v_ang = math.degrees(cmath.phase(vr.phasor[t]))
        i_mag = abs(ir.phasor[t])
        i_ang = math.degrees(cmath.phase(ir.phasor[t]))
        sp = single_phase_power(v_mag, v_ang, i_mag, i_ang)

        np.testing.assert_allclose(p_arr[t], sp.p_watts / 1e6, rtol=1e-10, err_msg="P mismatch")
        np.testing.assert_allclose(q_arr[t], sp.q_var / 1e6, rtol=1e-10, err_msg="Q mismatch")
        np.testing.assert_allclose(s_arr[t], sp.s_va / 1e6, rtol=1e-10, err_msg="|S| mismatch")

    def test_unit_scaled_equivalence(self):
        """Unit-scaled (kV × kA) inputs produce numerically equivalent results."""
        n = int(FS_HZ * 2.0)
        time = np.arange(n, dtype=np.float64) / FS_HZ
        v_kv = np.sin(2 * np.pi * F0_HZ * time)   # amplitude 1 kV
        i_ka = 0.5 * np.sin(2 * np.pi * F0_HZ * time - math.radians(20.0))  # amplitude 0.5 kA

        # evaluate_power_channel with explicit SI scaling
        p_arr = evaluate_power_channel(
            OP_ACTIVE_POWER, v_time=time,
            v_values=v_kv, v_scale_to_si=1000.0,   # kV → V
            i_values=i_ka, i_scale_to_si=1000.0,   # kA → A
        )
        # same with SI inputs manually
        v_si = v_kv * 1000.0
        i_si = i_ka * 1000.0
        vr = compute_sliding_phasor(time, v_si, F0_HZ)
        ir = compute_sliding_phasor(time, i_si, F0_HZ)

        t = int(FS_HZ * 1.0)
        v_mag = abs(vr.phasor[t])
        v_ang = math.degrees(cmath.phase(vr.phasor[t]))
        i_mag = abs(ir.phasor[t])
        i_ang = math.degrees(cmath.phase(ir.phasor[t]))
        sp = single_phase_power(v_mag, v_ang, i_mag, i_ang)

        np.testing.assert_allclose(p_arr[t], sp.p_watts / 1e6, rtol=1e-10)
