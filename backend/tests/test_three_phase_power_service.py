"""Service-level tests for three-phase power calculated channels (DEC-208, Phase E-2B).

36 tests covering:
  A–C: Basic creation for MW / Mvar / MVA, output metadata
  D:   Arity guard (6 inputs required)
  E–F: Engineering-type slot guards (wrong type in voltage / current slot)
  G:   Unit guard (blank unit rejected)
  H:   Confirmed phase mismatch rejection (VR+IB — same RYB convention, different tokens)
  I:   Cross-convention pair (VR+IA): uncertain → error; accepted with pairing_confirmed
  J:   Generic channel names (CH1–CH6) → uncertain pairing → UnconfirmedPhasePairingError
  K:   Generic names with phase_pairing_confirmed + voltage_reference_confirmed → accepted
  L:   Line-to-line naming (VRY/VYB/VBR) → rejected WITHOUT needing pairing_confirmed
       (per-channel L-L guard runs before phase matching — Finding 4)
  M:   RYB convention (VR/IR/VY/IY/VB/IB) — LINE_TO_GROUND auto-detected, proceed
  N:   ABC convention (VA/IA/VB/IB/VC/IC) — accepted
  O:   L1/L2/L3 convention (VL1/IL1/VL2/IL2/VL3/IL3) — accepted with vref confirmation
  P:   Mixed units (kV + A) → correct MW via SI scaling
  Q:   Short recording → RmsRecordingTooShortError
  R:   Timebase misalignment → IncompatibleTimeBaseError
  S:   NaN propagation: NaN in one phase → NaN samples in output
  T:   Atomicity: a validation failure leaves calc_registry empty
  U:   Deletion: delete_calculated_channel removes the channel
  V:   Single-phase regression: existing active_power still creates correctly
  W:   Parameters recording: voltage_reference, vref_reason, vref_confirmed, pairing_confirmed

Safety Verification I–IV (Issues 1–4 from prior review):
  X:   Mixed L-L: VR+VY+VBR with vref_confirmed → per-channel guard rejects VBR
  Y:   Sixth-channel misalignment: channels 1–5 aligned, channel 6 from offset source
  Z:   V + kA units: SI scale factors yield correct MW (100 A rms stored as 0.1 kA)

Complete Identity Validation (Findings 1–3 from this review):
  AA:  Cross-convention sets (RYB voltages + ABC currents): VY+IB must not be a
       confirmed mismatch — convention-level detection classifies as uncertain
  BB:  Cross-context pairing (TBIN VR / TKBR IR): same token, different context
       hints → uncertain without confirmation
  CC:  Duplicate phase assignments (same ref or same token in multiple slots):
       rejected unconditionally, cannot be overridden by pairing_confirmed
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import (
    OP_ACTIVE_POWER,
    OP_THREE_PHASE_ACTIVE_POWER,
    OP_THREE_PHASE_APPARENT_POWER,
    OP_THREE_PHASE_REACTIVE_POWER,
    ChannelRef,
)
from app.domain.channel_classification import WAVEFORM_FORM_UNKNOWN
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.voltage_reference import REASON_NO_PATTERN
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel, delete_calculated_channel
from app.services.errors import (
    DuplicatePhaseAssignmentError,
    IncompatibleTimeBaseError,
    InvalidOperationArityError,
    InvalidPowerInputTypeError,
    InvalidPowerInputUnitError,
    InvalidThreePhasePhaseMismatchError,
    LineToLineVoltageRejectedError,
    RmsRecordingTooShortError,
    UnconfirmedPhasePairingError,
    UnconfirmedVoltageReferenceError,
)
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-1"
BASE_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
F0_HZ = 50.0
FS_HZ = 5_000.0   # 100 samples/cycle
_CYCLES = 5
_N = int(FS_HZ / F0_HZ * _CYCLES)  # 500 samples


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _time() -> np.ndarray:
    return np.arange(_N, dtype=np.float64) / FS_HZ


def _sin(amplitude: float, phase_deg: float) -> np.ndarray:
    t = _time()
    return amplitude * np.sin(2 * math.pi * F0_HZ * t + math.radians(phase_deg))


def _active_source(
    *,
    source_id: str,
    time: np.ndarray,
    channels: dict[str, np.ndarray],
    units: dict[str, str] | None = None,
    engineering_types: dict[str, str] | None = None,
    start_time: datetime | None = BASE_START,
) -> ActiveSource:
    units = units or {}
    engineering_types = engineering_types or {}
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
        sample_count=len(time),
        duration_seconds=float(time[-1] - time[0]) if len(time) else 0.0,
        elapsed_start_seconds=float(time[0]) if len(time) else 0.0,
        elapsed_end_seconds=float(time[-1]) if len(time) else 0.0,
        sampling_rates=(1.0,), samples_per_rate=(len(time),),
        analog_channels=[
            AnalogChannelSummary(
                name=name, index=i, unit=units.get(name, "V"),
                engineering_type=engineering_types.get(name, "Voltage"),
                waveform_form=WAVEFORM_FORM_UNKNOWN,
            )
            for i, name in enumerate(channels)
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _balanced_source(
    *,
    source_id: str = "src1",
    v_names: tuple[str, str, str] = ("VR", "VY", "VB"),
    i_names: tuple[str, str, str] = ("IR", "IY", "IB"),
    v_amplitude_v: float = 1000.0 * math.sqrt(2),  # 1000 V rms
    i_amplitude_a: float = 100.0 * math.sqrt(2),   # 100 A rms
    pf_angle_deg: float = 30.0,
    v_units: str = "V",
    i_units: str = "A",
    v_et: str = "Voltage",
    i_et: str = "Current",
) -> ActiveSource:
    """Balanced positive-sequence source: R at 0°, Y at -120°, B at -240°."""
    v_phase = (0.0, -120.0, -240.0)
    i_phase = (0.0 - pf_angle_deg, -120.0 - pf_angle_deg, -240.0 - pf_angle_deg)
    t = _time()
    channels: dict[str, np.ndarray] = {}
    for name, ph in zip(v_names, v_phase):
        channels[name] = _sin(v_amplitude_v, ph)
    for name, ph in zip(i_names, i_phase):
        channels[name] = _sin(i_amplitude_a, ph)
    units = {n: v_units for n in v_names}
    units.update({n: i_units for n in i_names})
    et = {n: v_et for n in v_names}
    et.update({n: i_et for n in i_names})
    return _active_source(source_id=source_id, time=t, channels=channels, units=units, engineering_types=et)


def _refs_ryb(source_id: str = "src1") -> list[ChannelRef]:
    return [
        ChannelRef(kind="source", source_id=source_id, channel_name="VR"),
        ChannelRef(kind="source", source_id=source_id, channel_name="IR"),
        ChannelRef(kind="source", source_id=source_id, channel_name="VY"),
        ChannelRef(kind="source", source_id=source_id, channel_name="IY"),
        ChannelRef(kind="source", source_id=source_id, channel_name="VB"),
        ChannelRef(kind="source", source_id=source_id, channel_name="IB"),
    ]


# ---------------------------------------------------------------------------
# Expected steady-state values for V_rms=1000V, I_rms=100A, PF angle=30° lag:
#   P = 3 × 1000 × 100 × cos(30°) = 150000√3 W = 0.15√3 MW
#   Q = 3 × 1000 × 100 × sin(30°) = 150000 var  = 0.15 Mvar
#   |S| = 3 × 1000 × 100           = 300000 VA   = 0.30 MVA
# ---------------------------------------------------------------------------
_EXP_P_MW = 3 * 1000 * 100 * math.cos(math.radians(30)) / 1e6
_EXP_Q_MVAR = 3 * 1000 * 100 * math.sin(math.radians(30)) / 1e6
_EXP_S_MVA = 3 * 1000 * 100 / 1e6

# Steady-state window: skip the first two full cycles (phasor transient)
_SKIP = int(2 * FS_HZ / F0_HZ)
_ABS_TOL_MW = 1e-6   # MW/Mvar/MVA


# ===========================================================================
# Test A: three_phase_active_power creates MW channel with correct metadata
# ===========================================================================

class TestA_ActivePowerCreation:
    def test_creates_mw_channel(self):
        sr, cr = _registries()
        sr.add(_balanced_source())
        ch = create_calculated_channel(
            workspace_id=WS, name="3-phase P",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.unit == "MW"
        assert ch.engineering_type == "Power"
        assert ch.operation == OP_THREE_PHASE_ACTIVE_POWER
        assert ch.reference_source_id == "src1"
        assert ch.values is not None and len(ch.values) == _N
        steady = ch.values[_SKIP:]
        assert abs(float(np.nanmean(steady)) - _EXP_P_MW) < _ABS_TOL_MW


# ===========================================================================
# Test B: three_phase_reactive_power creates Mvar channel
# ===========================================================================

class TestB_ReactivePowerCreation:
    def test_creates_mvar_channel(self):
        sr, cr = _registries()
        sr.add(_balanced_source())
        ch = create_calculated_channel(
            workspace_id=WS, name="3-phase Q",
            operation=OP_THREE_PHASE_REACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.unit == "Mvar"
        assert ch.engineering_type == "Power"
        steady = ch.values[_SKIP:]
        assert abs(float(np.nanmean(steady)) - _EXP_Q_MVAR) < _ABS_TOL_MW


# ===========================================================================
# Test C: three_phase_apparent_power creates MVA channel
# ===========================================================================

class TestC_ApparentPowerCreation:
    def test_creates_mva_channel(self):
        sr, cr = _registries()
        sr.add(_balanced_source())
        ch = create_calculated_channel(
            workspace_id=WS, name="3-phase |S|",
            operation=OP_THREE_PHASE_APPARENT_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.unit == "MVA"
        assert ch.engineering_type == "Power"
        steady = ch.values[_SKIP:]
        assert abs(float(np.nanmean(steady)) - _EXP_S_MVA) < _ABS_TOL_MW


# ===========================================================================
# Test D: arity guard — 6 inputs required
# ===========================================================================

class TestD_ArityGuard:
    def test_five_inputs_rejected(self):
        sr, cr = _registries()
        sr.add(_balanced_source())
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="3-phase P arity",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb()[:5],
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_seven_inputs_rejected(self):
        sr, cr = _registries()
        src = _balanced_source(v_names=("VR", "VY", "VB"), i_names=("IR", "IY", "IB"))
        sr.add(src)
        extra = ChannelRef(kind="source", source_id="src1", channel_name="VR")
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="3-phase P arity7",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb() + [extra],
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test E: engineering-type guard — voltage slot with Current input
# ===========================================================================

class TestE_TypeGuardVoltageSlot:
    def test_current_in_voltage_slot_rejected(self):
        sr, cr = _registries()
        sr.add(_balanced_source(v_et="Current"))  # slots 0/2/4 will be Current
        with pytest.raises(InvalidPowerInputTypeError):
            create_calculated_channel(
                workspace_id=WS, name="type guard E",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb(),
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test F: engineering-type guard — current slot with Voltage input
# ===========================================================================

class TestF_TypeGuardCurrentSlot:
    def test_voltage_in_current_slot_rejected(self):
        sr, cr = _registries()
        sr.add(_balanced_source(i_et="Voltage"))  # slots 1/3/5 will be Voltage
        with pytest.raises(InvalidPowerInputTypeError):
            create_calculated_channel(
                workspace_id=WS, name="type guard F",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb(),
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test G: unit guard — blank unit rejected
# ===========================================================================

class TestG_UnitGuard:
    def test_blank_voltage_unit_rejected(self):
        sr, cr = _registries()
        # Override VR unit to blank
        src = _balanced_source(v_units="")
        sr.add(src)
        with pytest.raises(InvalidPowerInputUnitError):
            create_calculated_channel(
                workspace_id=WS, name="unit guard G",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb(),
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test H: confirmed phase mismatch — VR + IB in one pair
# ===========================================================================

class TestH_PhaseMismatch:
    def test_vr_ib_pairing_rejected(self):
        """VR and IB are both in the RYB convention; R ≠ B → confirmed mismatch."""
        sr, cr = _registries()
        t = _time()
        # Pair 1: VR + IB (mismatch), pairs 2-3 valid
        channels = {
            "VR": _sin(1000 * math.sqrt(2), 0.0),
            "IB": _sin(100 * math.sqrt(2), -30.0),   # named IB but in slot 1
            "VY": _sin(1000 * math.sqrt(2), -120.0),
            "IY": _sin(100 * math.sqrt(2), -150.0),
            "VB": _sin(1000 * math.sqrt(2), -240.0),
            "IR": _sin(100 * math.sqrt(2), -270.0),   # named IR but in slot 5
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IB"),  # mismatch: IB in V_R's current slot
            ChannelRef(kind="source", source_id="src1", channel_name="VY"),
            ChannelRef(kind="source", source_id="src1", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src1", channel_name="IR"),
        ]
        with pytest.raises(InvalidThreePhasePhaseMismatchError):
            create_calculated_channel(
                workspace_id=WS, name="mismatch H",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test I: cross-convention pair (VR + IA) — different conventions, NOT confirmed
# ===========================================================================

class TestI_CrossConventionNotMismatch:
    def test_vr_ia_without_confirmation_raises_pairing_error(self):
        """VR (RYB R) + IA (ABC A) are cross-convention: not a confirmed MISMATCH but
        UNCERTAIN. Without phase_pairing_confirmed, UnconfirmedPhasePairingError must
        be raised — not InvalidThreePhasePhaseMismatchError."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "VR": _sin(1000 * math.sqrt(2), 0.0),
            "IA": _sin(100 * math.sqrt(2), -30.0),
            "VY": _sin(1000 * math.sqrt(2), -120.0),
            "IY": _sin(100 * math.sqrt(2), -150.0),
            "VB": _sin(1000 * math.sqrt(2), -240.0),
            "IB": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IA"),
            ChannelRef(kind="source", source_id="src1", channel_name="VY"),
            ChannelRef(kind="source", source_id="src1", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src1", channel_name="IB"),
        ]
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="cross-convention reject",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_vr_ia_with_confirmation_accepted(self):
        """Same cross-convention pair with phase_pairing_confirmed=True → accepted."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "VR": _sin(1000 * math.sqrt(2), 0.0),
            "IA": _sin(100 * math.sqrt(2), -30.0),
            "VY": _sin(1000 * math.sqrt(2), -120.0),
            "IY": _sin(100 * math.sqrt(2), -150.0),
            "VB": _sin(1000 * math.sqrt(2), -240.0),
            "IB": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IA"),
            ChannelRef(kind="source", source_id="src1", channel_name="VY"),
            ChannelRef(kind="source", source_id="src1", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src1", channel_name="IB"),
        ]
        ch = create_calculated_channel(
            workspace_id=WS, name="cross-convention accept",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
        )
        assert ch.unit == "MW"
        assert ch.parameters["phase_pairing_confirmed"] is True


# ===========================================================================
# Test J: unknown voltage reference — rejected without confirmation
# ===========================================================================

class TestJ_UnknownPhasePairingNoConfirmation:
    def test_generic_names_without_pairing_confirmation_rejected(self):
        """Channel names with no recognizable phase tokens → uncertain pairing →
        UnconfirmedPhasePairingError (fires before voltage reference check)."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "CH1": _sin(1000 * math.sqrt(2), 0.0),
            "CH2": _sin(100 * math.sqrt(2), -30.0),
            "CH3": _sin(1000 * math.sqrt(2), -120.0),
            "CH4": _sin(100 * math.sqrt(2), -150.0),
            "CH5": _sin(1000 * math.sqrt(2), -240.0),
            "CH6": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={"CH1": "V", "CH2": "A", "CH3": "V", "CH4": "A", "CH5": "V", "CH6": "A"},
            engineering_types={"CH1": "Voltage", "CH2": "Current", "CH3": "Voltage",
                               "CH4": "Current", "CH5": "Voltage", "CH6": "Current"},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6"]]
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="unknown pairing J",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test K: unknown voltage reference — accepted WITH confirmation
# ===========================================================================

class TestK_UnknownVrefWithConfirmation:
    def test_generic_names_with_confirmation_accepted(self):
        sr, cr = _registries()
        t = _time()
        channels = {
            "CH1": _sin(1000 * math.sqrt(2), 0.0),
            "CH2": _sin(100 * math.sqrt(2), -30.0),
            "CH3": _sin(1000 * math.sqrt(2), -120.0),
            "CH4": _sin(100 * math.sqrt(2), -150.0),
            "CH5": _sin(1000 * math.sqrt(2), -240.0),
            "CH6": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={"CH1": "V", "CH2": "A", "CH3": "V", "CH4": "A", "CH5": "V", "CH6": "A"},
            engineering_types={"CH1": "Voltage", "CH2": "Current", "CH3": "Voltage",
                               "CH4": "Current", "CH5": "Voltage", "CH6": "Current"},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6"]]
        ch = create_calculated_channel(
            workspace_id=WS, name="unknown vref K",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
            voltage_reference_confirmed=True,
        )
        assert ch.unit == "MW"


# ===========================================================================
# Test L: line-to-line naming evidence — rejected outright
# ===========================================================================

class TestL_LineToLineRejected:
    def test_vry_naming_rejected(self):
        """VRY, VYB, VBR are phase-pair names → LINE_TO_LINE evidence → rejected."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "VRY": _sin(1000 * math.sqrt(2), 0.0),
            "IR":  _sin(100 * math.sqrt(2), -30.0),
            "VYB": _sin(1000 * math.sqrt(2), -120.0),
            "IY":  _sin(100 * math.sqrt(2), -150.0),
            "VBR": _sin(1000 * math.sqrt(2), -240.0),
            "IB":  _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["VRY", "IR", "VYB", "IY", "VBR", "IB"]]
        # Per-channel L-L guard fires BEFORE phase matching (Finding 4), so
        # LineToLineVoltageRejectedError is raised without any confirmation flags.
        with pytest.raises(LineToLineVoltageRejectedError):
            create_calculated_channel(
                workspace_id=WS, name="ll reject L",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test M: RYB convention — LINE_TO_GROUND auto-detected, proceeds without confirmation
# ===========================================================================

class TestM_RybConvention:
    def test_ryb_autodetected(self):
        sr, cr = _registries()
        sr.add(_balanced_source(v_names=("VR", "VY", "VB"), i_names=("IR", "IY", "IB")))
        ch = create_calculated_channel(
            workspace_id=WS, name="RYB M",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.parameters.get("voltage_reference") == "line_to_ground"
        assert ch.parameters.get("voltage_reference_confirmed") is False


# ===========================================================================
# Test N: ABC convention
# ===========================================================================

class TestN_AbcConvention:
    def test_abc_convention_accepted(self):
        sr, cr = _registries()
        sr.add(_balanced_source(v_names=("VA", "VB", "VC"), i_names=("IA", "IB", "IC")))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["VA", "IA", "VB", "IB", "VC", "IC"]]
        ch = create_calculated_channel(
            workspace_id=WS, name="ABC N",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.unit == "MW"


# ===========================================================================
# Test O: L1/L2/L3 convention
# ===========================================================================

class TestO_L123Convention:
    def test_l123_convention_accepted_with_confirmation(self):
        """VL1/VL2/VL3 naming is not recognized as LINE_TO_GROUND by the voltage-reference
        detector (L1/L2/L3 tokens are outside its current vocabulary), so
        voltage_reference_confirmed=True is required. With confirmation the channel is created."""
        sr, cr = _registries()
        sr.add(_balanced_source(v_names=("VL1", "VL2", "VL3"), i_names=("IL1", "IL2", "IL3")))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["VL1", "IL1", "VL2", "IL2", "VL3", "IL3"]]
        ch = create_calculated_channel(
            workspace_id=WS, name="L123 O",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            voltage_reference_confirmed=True,
        )
        assert ch.unit == "MW"


# ===========================================================================
# Test P: mixed units (kV + A) → correct MW via SI scaling
# ===========================================================================

class TestP_MixedUnitsScaling:
    def test_kv_amps_gives_correct_mw(self):
        """kV voltage + A current: SI scale factors must give the same MW output
        as V + A at the same physical magnitudes."""
        sr, cr = _registries()
        # V_rms = 1 kV (amplitude = 1000√2 V, but in kV = √2 kV)
        # I_rms = 100 A (amplitude = 100√2 A), PF=30° lag
        # Expected P = 3 × 1000 × 100 × cos(30°) = 150000√3 W = 0.15√3 MW
        sr.add(_balanced_source(v_units="kV", i_units="A",
                                v_amplitude_v=math.sqrt(2),    # √2 kV → 1 kV rms
                                i_amplitude_a=100 * math.sqrt(2)))
        ch = create_calculated_channel(
            workspace_id=WS, name="kV mixed P",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        steady = ch.values[_SKIP:]
        assert abs(float(np.nanmean(steady)) - _EXP_P_MW) < _ABS_TOL_MW


# ===========================================================================
# Test Q: short recording — RmsRecordingTooShortError
# ===========================================================================

class TestQ_ShortRecording:
    def test_sub_cycle_recording_rejected(self):
        """A recording shorter than one phasor cycle must be rejected."""
        sr, cr = _registries()
        n_short = int(FS_HZ / F0_HZ * 0.5)  # half a cycle
        t_short = np.arange(n_short, dtype=float) / FS_HZ
        channels = {
            "VR": _sin(1000 * math.sqrt(2), 0.0)[:n_short],
            "IR": _sin(100 * math.sqrt(2), -30.0)[:n_short],
            "VY": _sin(1000 * math.sqrt(2), -120.0)[:n_short],
            "IY": _sin(100 * math.sqrt(2), -150.0)[:n_short],
            "VB": _sin(1000 * math.sqrt(2), -240.0)[:n_short],
            "IB": _sin(100 * math.sqrt(2), -270.0)[:n_short],
        }
        sr.add(_active_source(
            source_id="src1", time=t_short, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        with pytest.raises(RmsRecordingTooShortError):
            create_calculated_channel(
                workspace_id=WS, name="short Q",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb(),
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test R: timebase misalignment — IncompatibleTimeBaseError
# ===========================================================================

class TestR_TimebaseMisalignment:
    def test_misaligned_source_rejected(self):
        """Two sources whose start epochs differ by more than 300 ns must be rejected."""
        from datetime import timedelta
        sr, cr = _registries()
        t = _time()
        def _src(src_id: str, start: datetime, ch_names: list[str]) -> ActiveSource:
            channels = {n: _sin(1000 * math.sqrt(2), 0.0) for n in ch_names}
            units = {n: "V" if n.startswith("V") else "A" for n in ch_names}
            et = {n: "Voltage" if n.startswith("V") else "Current" for n in ch_names}
            return _active_source(source_id=src_id, time=t, channels=channels,
                                  units=units, engineering_types=et, start_time=start)
        # src1 has VR, IR; src2 (misaligned by 1 s) has VY, IY, VB, IB
        offset_start = BASE_START + timedelta(seconds=1)
        sr.add(_src("src1", BASE_START, ["VR", "IR"]))
        sr.add(_src("src2", offset_start, ["VY", "IY", "VB", "IB"]))
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IR"),
            ChannelRef(kind="source", source_id="src2", channel_name="VY"),
            ChannelRef(kind="source", source_id="src2", channel_name="IY"),
            ChannelRef(kind="source", source_id="src2", channel_name="VB"),
            ChannelRef(kind="source", source_id="src2", channel_name="IB"),
        ]
        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="misalign R",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Test S: NaN propagation — NaN in one phase waveform → NaN output samples
# ===========================================================================

class TestS_NanPropagation:
    def test_nan_in_phase2_propagates(self):
        """NaN in VY should produce NaN in output samples affected by that window."""
        sr, cr = _registries()
        t = _time()
        vr = _sin(1000 * math.sqrt(2), 0.0)
        ir = _sin(100 * math.sqrt(2), -30.0)
        vy = _sin(1000 * math.sqrt(2), -120.0)
        iy = _sin(100 * math.sqrt(2), -150.0)
        vb = _sin(1000 * math.sqrt(2), -240.0)
        ib = _sin(100 * math.sqrt(2), -270.0)
        # Inject NaN into the middle of VY (samples 200-250)
        vy[200:250] = np.nan
        channels = {"VR": vr, "IR": ir, "VY": vy, "IY": iy, "VB": vb, "IB": ib}
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        ch = create_calculated_channel(
            workspace_id=WS, name="nan S",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        # Output around samples 200-349 (one phasor window = 100 samples) must contain NaN
        assert np.isnan(ch.values[220:260]).any()
        # Samples well after the gap (window has cleared) should be finite
        assert np.isfinite(ch.values[400:]).all()


# ===========================================================================
# Test T: atomicity — a validation failure leaves calc_registry unchanged
# ===========================================================================

class TestT_Atomicity:
    def test_type_error_leaves_registry_empty(self):
        """A type-guard failure must not create a partial channel entry."""
        sr, cr = _registries()
        sr.add(_balanced_source(v_et="Current"))  # will trigger type error
        assert len(cr.list_for_workspace(WS)) == 0
        with pytest.raises(InvalidPowerInputTypeError):
            create_calculated_channel(
                workspace_id=WS, name="atomic T",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=_refs_ryb(),
                parameters={}, source_registry=sr, calc_registry=cr,
            )
        assert len(cr.list_for_workspace(WS)) == 0


# ===========================================================================
# Test U: deletion — delete_calculated_channel removes the channel
# ===========================================================================

class TestU_Deletion:
    def test_delete_removes_channel(self):
        sr, cr = _registries()
        sr.add(_balanced_source())
        ch = create_calculated_channel(
            workspace_id=WS, name="to delete U",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert cr.get(WS, ch.id) is not None
        delete_calculated_channel(
            workspace_id=WS, calculated_channel_id=ch.id,
            calc_registry=cr,
        )
        assert cr.get(WS, ch.id) is None


# ===========================================================================
# Test V: single-phase regression — existing active_power still works
# ===========================================================================

class TestV_SinglePhaseRegression:
    def test_single_phase_active_power_unaffected(self):
        """DEC-208 additions must not break the existing Slice 3 single-phase power path."""
        sr, cr = _registries()
        t = _time()
        v_amp = 1000.0 * math.sqrt(2)
        i_amp = 100.0 * math.sqrt(2)
        sr.add(_active_source(
            source_id="src1", time=t,
            channels={
                "VR": _sin(v_amp, 0.0),
                "IR": _sin(i_amp, -30.0),
            },
            units={"VR": "V", "IR": "A"},
            engineering_types={"VR": "Voltage", "IR": "Current"},
        ))
        ch = create_calculated_channel(
            workspace_id=WS, name="single-phase P",
            operation=OP_ACTIVE_POWER,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VR"),
                ChannelRef(kind="source", source_id="src1", channel_name="IR"),
            ],
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.unit == "MW"
        # Expected: V_rms=1000V, I_rms=100A, PF=cos(30°) → P=100000×(√3/2)=50000√3 W = 0.05√3 MW
        exp_p = 1000.0 * 100.0 * math.cos(math.radians(30)) / 1e6
        steady = ch.values[_SKIP:]
        assert abs(float(np.nanmean(steady)) - exp_p) < _ABS_TOL_MW


# ===========================================================================
# Test W: parameters recording — vref info stored in output_parameters
# ===========================================================================

class TestW_ParametersRecording:
    def test_vref_recorded_in_parameters(self):
        """output_parameters must carry voltage_reference, reason, confirmed, evidence."""
        sr, cr = _registries()
        sr.add(_balanced_source())  # VR/VY/VB → LINE_TO_GROUND detected
        ch = create_calculated_channel(
            workspace_id=WS, name="params W",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        p = ch.parameters
        assert p["voltage_reference"] == "line_to_ground"
        assert p["voltage_reference_reason"] is not None
        assert p["voltage_reference_confirmed"] is False
        assert isinstance(p["voltage_reference_evidence_names"], list)
        assert p["nominal_frequency_hz"] == 50.0
        assert p["window_mode"] == "trailing"
        assert p["sign_convention"] == "passive"

    def test_vref_confirmed_flag_stored(self):
        """When voltage_reference_confirmed=True is passed, it must appear in parameters."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "CH1": _sin(1000 * math.sqrt(2), 0.0),
            "CH2": _sin(100 * math.sqrt(2), -30.0),
            "CH3": _sin(1000 * math.sqrt(2), -120.0),
            "CH4": _sin(100 * math.sqrt(2), -150.0),
            "CH5": _sin(1000 * math.sqrt(2), -240.0),
            "CH6": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={"CH1": "V", "CH2": "A", "CH3": "V", "CH4": "A", "CH5": "V", "CH6": "A"},
            engineering_types={"CH1": "Voltage", "CH2": "Current", "CH3": "Voltage",
                               "CH4": "Current", "CH5": "Voltage", "CH6": "Current"},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6"]]
        ch = create_calculated_channel(
            workspace_id=WS, name="params W2",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
            voltage_reference_confirmed=True,
        )
        assert ch.parameters["voltage_reference_confirmed"] is True
        assert ch.parameters["voltage_reference"] is None
        assert ch.parameters["voltage_reference_reason"] == REASON_NO_PATTERN
        assert ch.parameters["phase_pairing_confirmed"] is True


# ===========================================================================
# Issue 1 (Safety Verification): mixed L-L evidence — per-channel guard fires
# even when group-level result is CONFLICTING and voltage_reference_confirmed=True
# ===========================================================================

class TestX_MixedLLPerChannelGuard:
    def test_vr_vy_vbr_with_vref_confirmed_still_rejected(self):
        """VR, VY, VBR: group-level detection → CONFLICTING (not LINE_TO_LINE), so a
        naive implementation would accept this with voltage_reference_confirmed=True.
        The per-channel guard must detect VBR individually as LINE_TO_LINE and reject
        before the group-level check, regardless of confirmation flags."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "VR":  _sin(1000 * math.sqrt(2), 0.0),
            "IR":  _sin(100 * math.sqrt(2), -30.0),
            "VY":  _sin(1000 * math.sqrt(2), -120.0),
            "IY":  _sin(100 * math.sqrt(2), -150.0),
            "VBR": _sin(1000 * math.sqrt(2), -240.0),
            "IB":  _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["VR", "IR", "VY", "IY", "VBR", "IB"]]
        # Per-channel L-L guard fires BEFORE phase matching (Finding 4), so VBR
        # raises LineToLineVoltageRejectedError immediately — no confirmation flags
        # are needed, and voltage_reference_confirmed=True does NOT bypass it.
        with pytest.raises(LineToLineVoltageRejectedError):
            create_calculated_channel(
                workspace_id=WS, name="mixed ll X",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
                voltage_reference_confirmed=True,
            )


# ===========================================================================
# Issue 3 (Safety Verification): sixth-channel timebase misalignment
# — first five channels align but the sixth does not
# ===========================================================================

class TestY_SixthChannelMisalignment:
    def test_first_five_aligned_sixth_misaligned_rejected(self):
        """Channels 1–5 share the same timebase; channel 6 (IB) comes from a source
        misaligned by 1 second. The operation must be rejected before any workspace
        state is modified (atomicity + timebase guard)."""
        from datetime import timedelta
        sr, cr = _registries()
        t = _time()

        def _src(src_id: str, start: datetime, ch_names: list[str]) -> ActiveSource:
            channels = {
                n: (_sin(1000 * math.sqrt(2), 0.0) if n.startswith("V")
                    else _sin(100 * math.sqrt(2), -30.0))
                for n in ch_names
            }
            units = {n: "V" if n.startswith("V") else "A" for n in ch_names}
            et = {n: "Voltage" if n.startswith("V") else "Current" for n in ch_names}
            return _active_source(source_id=src_id, time=t, channels=channels,
                                  units=units, engineering_types=et, start_time=start)

        offset_start = BASE_START + timedelta(seconds=1)
        # src1 has VR, IR, VY, IY, VB — all aligned
        sr.add(_src("src1", BASE_START, ["VR", "IR", "VY", "IY", "VB"]))
        # src2 (misaligned by 1 s) carries only IB
        sr.add(_src("src2", offset_start, ["IB"]))

        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IR"),
            ChannelRef(kind="source", source_id="src1", channel_name="VY"),
            ChannelRef(kind="source", source_id="src1", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src2", channel_name="IB"),
        ]
        assert len(cr.list_for_workspace(WS)) == 0
        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="sixth misalign Y",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )
        # Atomicity: registry must still be empty after the failure
        assert len(cr.list_for_workspace(WS)) == 0


# ===========================================================================
# Issue 4 (Safety Verification): V + kA mixed units — correct SI scaling
# ===========================================================================

class TestZ_VoltKiloampScaling:
    def test_v_kilamp_gives_correct_mw(self):
        """V voltage + kA current: SI scale factors must yield the same MW output
        as V + A at the same physical magnitudes.
        V_rms = 1000 V, I_rms = 0.1 kA (= 100 A), PF angle = 30° lag.
        Expected P = 3 × 1000 × 100 × cos(30°) / 1e6 MW."""
        sr, cr = _registries()
        # Stored values are in kA: amplitude = 100√2 A → 0.1√2 kA
        sr.add(_balanced_source(
            v_units="V",  i_units="kA",
            v_amplitude_v=1000 * math.sqrt(2),   # 1000 V rms
            i_amplitude_a=0.1 * math.sqrt(2),    # 0.1 kA rms = 100 A rms
        ))
        ch = create_calculated_channel(
            workspace_id=WS, name="V+kA Z",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        steady = ch.values[_SKIP:]
        assert abs(float(np.nanmean(steady)) - _EXP_P_MW) < _ABS_TOL_MW


# ===========================================================================
# Finding 1 (Complete Cross-Convention Sets): RYB voltages + ABC currents
# ===========================================================================

class TestAA_CrossConventionSets:
    """VR/VY/VB (RYB) paired with IA/IB/IC (ABC).
    VY+IB must NOT be rejected as a confirmed mismatch (both 'Y' and 'B' are
    in {R,Y,B}, but 'A' and 'C' mark the current set as ABC, not RYB).
    Convention-level detection classifies this as cross-convention → uncertain."""

    def _build(self) -> tuple:
        sr, cr = _registries()
        t = _time()
        channels = {
            "VR": _sin(1000 * math.sqrt(2), 0.0),
            "IA": _sin(100 * math.sqrt(2), -30.0),
            "VY": _sin(1000 * math.sqrt(2), -120.0),
            "IB": _sin(100 * math.sqrt(2), -150.0),
            "VB": _sin(1000 * math.sqrt(2), -240.0),
            "IC": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if n.startswith("V") else "A" for n in channels},
            engineering_types={n: "Voltage" if n.startswith("V") else "Current" for n in channels},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["VR", "IA", "VY", "IB", "VB", "IC"]]
        return sr, cr, inputs

    def test_ryb_voltages_abc_currents_without_confirmation_rejected(self):
        """Cross-convention set (RYB vs ABC) → uncertain → UnconfirmedPhasePairingError."""
        sr, cr, inputs = self._build()
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="cross-set AA reject",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_ryb_voltages_abc_currents_with_confirmation_accepted(self):
        """Same cross-convention pairing with phase_pairing_confirmed=True → accepted."""
        sr, cr, inputs = self._build()
        ch = create_calculated_channel(
            workspace_id=WS, name="cross-set AA accept",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
        )
        assert ch.unit == "MW"
        assert ch.parameters["phase_pairing_confirmed"] is True


# ===========================================================================
# Finding 2 (Cross-Context Pairing): same phase token, different equipment context
# ===========================================================================

class TestBB_CrossContextPairing:
    """'TBIN VR' and 'TKBR IR': both have phase token 'R' but context hints
    'TBIN' and 'TKBR' are established and distinct. This requires confirmation."""

    def _build(self) -> tuple:
        sr, cr = _registries()
        t = _time()
        channels = {
            "TBIN VR": _sin(1000 * math.sqrt(2), 0.0),
            "TKBR IR": _sin(100 * math.sqrt(2), -30.0),
            "TBIN VY": _sin(1000 * math.sqrt(2), -120.0),
            "TKBR IY": _sin(100 * math.sqrt(2), -150.0),
            "TBIN VB": _sin(1000 * math.sqrt(2), -240.0),
            "TKBR IB": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if "V" in n else "A" for n in channels},
            engineering_types={n: "Voltage" if "V" in n else "Current" for n in channels},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["TBIN VR", "TKBR IR", "TBIN VY", "TKBR IY", "TBIN VB", "TKBR IB"]]
        return sr, cr, inputs

    def test_cross_context_same_token_without_confirmation_rejected(self):
        """Same phase token 'R' / 'Y' / 'B' but TBIN vs TKBR contexts → uncertain."""
        sr, cr, inputs = self._build()
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="cross-ctx BB reject",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_cross_context_same_token_with_confirmation_accepted(self):
        """Cross-context pairing with phase_pairing_confirmed=True → accepted."""
        sr, cr, inputs = self._build()
        ch = create_calculated_channel(
            workspace_id=WS, name="cross-ctx BB accept",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
        )
        assert ch.unit == "MW"
        assert ch.parameters["phase_pairing_confirmed"] is True


# ===========================================================================
# Finding 3 (Duplicate Phase Assignments): same ref or same token in multiple slots
# ===========================================================================

class TestCC_DuplicatePhaseAssignment:
    """Duplicate phase assignments must be rejected unconditionally —
    phase_pairing_confirmed=True cannot override them."""

    def test_same_ref_in_two_voltage_slots_rejected(self):
        """VR appears in both voltage slot 0 and slot 2 → DuplicatePhaseAssignmentError."""
        sr, cr = _registries()
        sr.add(_balanced_source())
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IR"),
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),  # duplicate
            ChannelRef(kind="source", source_id="src1", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src1", channel_name="IB"),
        ]
        with pytest.raises(DuplicatePhaseAssignmentError):
            create_calculated_channel(
                workspace_id=WS, name="dup ref CC",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_same_ref_rejected_even_with_pairing_confirmed(self):
        """Duplicate reference rejection is unconditional — cannot be confirmed away."""
        sr, cr = _registries()
        sr.add(_balanced_source())
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src1", channel_name="IR"),
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),  # duplicate
            ChannelRef(kind="source", source_id="src1", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src1", channel_name="IB"),
        ]
        with pytest.raises(DuplicatePhaseAssignmentError):
            create_calculated_channel(
                workspace_id=WS, name="dup ref confirmed CC",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
                phase_pairing_confirmed=True,
            )

    def test_duplicate_voltage_token_from_different_sources_rejected(self):
        """Two different source channels both named 'VR' → same token 'R' in two
        voltage slots → DuplicatePhaseAssignmentError even though refs differ."""
        sr, cr = _registries()
        t = _time()
        for sid in ("src1", "src2", "src3"):
            sr.add(_active_source(
                source_id=sid, time=t,
                channels={"VR": _sin(1000 * math.sqrt(2), 0.0),
                          "IR": _sin(100 * math.sqrt(2), -30.0)},
                units={"VR": "V", "IR": "A"},
                engineering_types={"VR": "Voltage", "IR": "Current"},
            ))
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),  # token R
            ChannelRef(kind="source", source_id="src1", channel_name="IR"),
            ChannelRef(kind="source", source_id="src2", channel_name="VR"),  # token R (dup)
            ChannelRef(kind="source", source_id="src2", channel_name="IR"),
            ChannelRef(kind="source", source_id="src3", channel_name="VR"),  # token R (dup)
            ChannelRef(kind="source", source_id="src3", channel_name="IR"),
        ]
        with pytest.raises(DuplicatePhaseAssignmentError):
            create_calculated_channel(
                workspace_id=WS, name="dup token CC",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )


# ===========================================================================
# Source and Equipment Identity Safety (Scenarios 1–3 from final safety check)
# ===========================================================================

class TestDD_SourceIdentitySafety:
    """Three scenarios that must require phase_pairing_confirmed=True:
    1. Voltages from src1, currents from src2 — matching tokens, no context.
    2. Each V-I phase pair from a different source pair.
    3. Three pairs with individually matching contexts but different contexts
       across the three pairs (TBIN+TBIN, TKBR+TKBR, TBUS+TBUS).
    Positive: same-source, null-context, unambiguous pairing proceeds without
    confirmation (verified by TestM; repeated here for completeness)."""

    # ---- Scenario 1: voltages from src1, currents from src2 ----

    def _build_two_source(self) -> tuple:
        """VR/VY/VB from src1, IR/IY/IB from src2 — aligned timebases."""
        sr, cr = _registries()
        t = _time()
        sr.add(_active_source(
            source_id="src1", time=t,
            channels={
                "VR": _sin(1000 * math.sqrt(2), 0.0),
                "VY": _sin(1000 * math.sqrt(2), -120.0),
                "VB": _sin(1000 * math.sqrt(2), -240.0),
            },
            units={"VR": "V", "VY": "V", "VB": "V"},
            engineering_types={"VR": "Voltage", "VY": "Voltage", "VB": "Voltage"},
        ))
        sr.add(_active_source(
            source_id="src2", time=t,
            channels={
                "IR": _sin(100 * math.sqrt(2), -30.0),
                "IY": _sin(100 * math.sqrt(2), -150.0),
                "IB": _sin(100 * math.sqrt(2), -270.0),
            },
            units={"IR": "A", "IY": "A", "IB": "A"},
            engineering_types={"IR": "Current", "IY": "Current", "IB": "Current"},
        ))
        inputs = [
            ChannelRef(kind="source", source_id="src1", channel_name="VR"),
            ChannelRef(kind="source", source_id="src2", channel_name="IR"),
            ChannelRef(kind="source", source_id="src1", channel_name="VY"),
            ChannelRef(kind="source", source_id="src2", channel_name="IY"),
            ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ChannelRef(kind="source", source_id="src2", channel_name="IB"),
        ]
        return sr, cr, inputs

    def test_src1_voltages_src2_currents_without_confirmation_rejected(self):
        """Voltages from src1, currents from src2: matching tokens, aligned timebases,
        but multi-source → uncertain → UnconfirmedPhasePairingError."""
        sr, cr, inputs = self._build_two_source()
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="multisrc DD1 reject",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_src1_voltages_src2_currents_with_confirmation_accepted(self):
        """Same multi-source split with phase_pairing_confirmed=True → accepted
        (legitimate use: busbar VT on one recorder, feeder CT on another)."""
        sr, cr, inputs = self._build_two_source()
        ch = create_calculated_channel(
            workspace_id=WS, name="multisrc DD1 accept",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
        )
        assert ch.unit == "MW"
        assert ch.parameters["phase_pairing_confirmed"] is True

    # ---- Scenario 2: each V-I pair from a different source pair ----

    def test_each_pair_from_different_sources_rejected(self):
        """Six distinct sources (src_v1/src_i1, src_v2/src_i2, src_v3/src_i3),
        each phase pair entirely from different instruments → uncertain."""
        sr, cr = _registries()
        t = _time()
        pair_data = [("VR", "IR", 0.0), ("VY", "IY", -120.0), ("VB", "IB", -240.0)]
        inputs = []
        for k, (vn, in_, ph) in enumerate(pair_data, start=1):
            v_src = f"src_v{k}"
            i_src = f"src_i{k}"
            sr.add(_active_source(
                source_id=v_src, time=t,
                channels={vn: _sin(1000 * math.sqrt(2), ph)},
                units={vn: "V"}, engineering_types={vn: "Voltage"},
            ))
            sr.add(_active_source(
                source_id=i_src, time=t,
                channels={in_: _sin(100 * math.sqrt(2), ph - 30.0)},
                units={in_: "A"}, engineering_types={in_: "Current"},
            ))
            inputs.append(ChannelRef(kind="source", source_id=v_src, channel_name=vn))
            inputs.append(ChannelRef(kind="source", source_id=i_src, channel_name=in_))
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="multisrc DD2 reject",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_each_pair_from_different_sources_with_confirmation_accepted(self):
        """Same six-source scenario with phase_pairing_confirmed=True → accepted."""
        sr, cr = _registries()
        t = _time()
        pair_data = [("VR", "IR", 0.0), ("VY", "IY", -120.0), ("VB", "IB", -240.0)]
        inputs = []
        for k, (vn, in_, ph) in enumerate(pair_data, start=1):
            v_src = f"src_v{k}"
            i_src = f"src_i{k}"
            sr.add(_active_source(
                source_id=v_src, time=t,
                channels={vn: _sin(1000 * math.sqrt(2), ph)},
                units={vn: "V"}, engineering_types={vn: "Voltage"},
            ))
            sr.add(_active_source(
                source_id=i_src, time=t,
                channels={in_: _sin(100 * math.sqrt(2), ph - 30.0)},
                units={in_: "A"}, engineering_types={in_: "Current"},
            ))
            inputs.append(ChannelRef(kind="source", source_id=v_src, channel_name=vn))
            inputs.append(ChannelRef(kind="source", source_id=i_src, channel_name=in_))
        ch = create_calculated_channel(
            workspace_id=WS, name="multisrc DD2 accept",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
        )
        assert ch.unit == "MW"

    # ---- Scenario 3: individually-matching contexts, inconsistent across pairs ----

    def _build_three_context(self) -> tuple:
        """All from src1; pair 1=TBIN, pair 2=TKBR, pair 3=TBUS — individual
        context matches within each pair but inconsistent across the three pairs."""
        sr, cr = _registries()
        t = _time()
        channels = {
            "TBIN VR": _sin(1000 * math.sqrt(2), 0.0),
            "TBIN IR": _sin(100 * math.sqrt(2), -30.0),
            "TKBR VY": _sin(1000 * math.sqrt(2), -120.0),
            "TKBR IY": _sin(100 * math.sqrt(2), -150.0),
            "TBUS VB": _sin(1000 * math.sqrt(2), -240.0),
            "TBUS IB": _sin(100 * math.sqrt(2), -270.0),
        }
        sr.add(_active_source(
            source_id="src1", time=t, channels=channels,
            units={n: "V" if "V" in n else "A" for n in channels},
            engineering_types={n: "Voltage" if "V" in n else "Current" for n in channels},
        ))
        inputs = [ChannelRef(kind="source", source_id="src1", channel_name=n)
                  for n in ["TBIN VR", "TBIN IR", "TKBR VY", "TKBR IY", "TBUS VB", "TBUS IB"]]
        return sr, cr, inputs

    def test_inconsistent_cross_pair_contexts_rejected(self):
        """TBIN/TBIN, TKBR/TKBR, TBUS/TBUS: each pair matches internally but
        three different equipment contexts across the pairs → uncertain."""
        sr, cr, inputs = self._build_three_context()
        with pytest.raises(UnconfirmedPhasePairingError):
            create_calculated_channel(
                workspace_id=WS, name="crossctx DD3 reject",
                operation=OP_THREE_PHASE_ACTIVE_POWER,
                inputs=inputs,
                parameters={}, source_registry=sr, calc_registry=cr,
            )

    def test_inconsistent_cross_pair_contexts_with_confirmation_accepted(self):
        """Same multi-context set with phase_pairing_confirmed=True → accepted."""
        sr, cr, inputs = self._build_three_context()
        ch = create_calculated_channel(
            workspace_id=WS, name="crossctx DD3 accept",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=inputs,
            parameters={}, source_registry=sr, calc_registry=cr,
            phase_pairing_confirmed=True,
        )
        assert ch.unit == "MW"
        assert ch.parameters["phase_pairing_confirmed"] is True

    def test_same_source_null_context_accepted_without_confirmation(self):
        """Positive regression: single source, matching RYB tokens, no context hints
        → accepted without phase_pairing_confirmed (standard balanced case)."""
        sr, cr = _registries()
        sr.add(_balanced_source())
        ch = create_calculated_channel(
            workspace_id=WS, name="single-src positive DD",
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=_refs_ryb(),
            parameters={}, source_registry=sr, calc_registry=cr,
        )
        assert ch.unit == "MW"
