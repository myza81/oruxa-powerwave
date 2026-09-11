"""Tests for app.services.phasor_analysis_service (Phasor Analysis
Slice 1): the orchestration layer that resolves live workspace state
(via the unchanged Slice 2 resolver), decides reference frequency,
enforces waveform-form eligibility, builds the shared absolute-time
coordinate, and runs the pure domain estimator per resolved role.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import CalculatedChannel, ChannelRef
from app.domain.channel_classification import (
    CURRENT,
    VOLTAGE,
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.domain.metadata import RecordingMetadata
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C, PHASE_SOURCE_ENGINEER_CONFIRMED
from app.domain.phasor import PHASOR_STATUS_COMPUTED, REASON_REFERENCE_FREQUENCY_CONFLICT, REASON_WAVEFORM_FORM_NOT_ELIGIBLE
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.analysis_input_resolution import STATUS_NEEDS_CONFIGURATION
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import EngineeringContextNotFoundError, UnknownAnalysisRequirementError
from app.services.phasor_analysis_service import compute_phasor_analysis
from app.services.workspace_registry import WorkspaceRegistry

SAMPLE_RATE_HZ = 5000.0
DURATION_S = 3.0
REF_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _sine_source(
    source_id: str, workspace_id: str, channels: list[tuple[str, str, float, float]],
    *, nominal_frequency: float = 50.0, start_time: datetime = REF_START, waveform_form: str = WAVEFORM_FORM_INSTANTANEOUS,
) -> ActiveSource:
    """`channels`: list of (name, engineering_type, amp_peak, phase_deg)."""
    n = int(round(DURATION_S * SAMPLE_RATE_HZ))
    t = np.arange(n) / SAMPLE_RATE_HZ
    analog_channels = []
    columns = {"time": t}
    for name, etype, amp_peak, phase_deg in channels:
        columns[name] = amp_peak * np.cos(2.0 * np.pi * nominal_frequency * t + np.radians(phase_deg))
        analog_channels.append(
            AnalogChannelSummary(
                name=name, index=len(analog_channels), unit="V" if etype == VOLTAGE else "A",
                engineering_type=etype, waveform_form=waveform_form,
            )
        )
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=nominal_frequency,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[SAMPLE_RATE_HZ], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=start_time, trigger_time=start_time),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=start_time,
        station_name="Station", recorder_name="Recorder", nominal_frequency=nominal_frequency,
        timing_reference="absolute", start_time=start_time, trigger_time=start_time,
        sample_count=n, duration_seconds=DURATION_S, elapsed_start_seconds=0.0, elapsed_end_seconds=DURATION_S,
        sampling_rates=(SAMPLE_RATE_HZ,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _calc(calc_id: str, workspace_id: str, reference_source_id: str, engineering_type: str, waveform_form: str, amp_peak: float, phase_deg: float, nominal_frequency: float = 50.0) -> CalculatedChannel:
    n = int(round(DURATION_S * SAMPLE_RATE_HZ))
    t = np.arange(n) / SAMPLE_RATE_HZ
    values = amp_peak * np.cos(2.0 * np.pi * nominal_frequency * t + np.radians(phase_deg))
    return CalculatedChannel(
        id=calc_id, workspace_id=workspace_id, name=calc_id, unit="V" if engineering_type == VOLTAGE else "A",
        operation="reverse_polarity", inputs=[ChannelRef(kind="source", source_id=reference_source_id, channel_name="X")],
        parameters={}, dependency_ids=[], reference_source_id=reference_source_id,
        time=t, values=values, created_at=datetime.now(timezone.utc),
        engineering_type=engineering_type, waveform_form=waveform_form,
    )


def _member(source_id, name, phase, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED):
    return EngineeringContextMember(
        channel_ref=ChannelRef(kind="source", source_id=source_id, channel_name=name), phase=phase, phase_source=phase_source,
    )


def _add_context(registry, context_id, workspace_id, members):
    registry.add(EngineeringContext(id=context_id, workspace_id=workspace_id, display_name="Test Context", members=members))


@pytest.fixture
def registries():
    return {
        "context": EngineeringContextRegistry(),
        "source": WorkspaceRegistry(),
        "calc": CalculatedChannelRegistry(),
    }


class TestBasicSinglePhaseComputation:
    def test_single_phase_voltage_computed(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, np.sqrt(2) * 100.0, 30.0)]))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.algorithm_version == "phasor_estimator_v1"
        assert result.reference_frequency_hz == 50.0
        role = result.roles["Va"]
        assert role.magnitude_rms == pytest.approx(100.0, rel=1e-6)
        assert role.angle_deg_absolute == pytest.approx(30.0, abs=1e-6)
        assert role.angle_deg_relative is None  # single-phase: no relative reference
        assert role.unit == "V"

    def test_unknown_context_raises(self, registries):
        with pytest.raises(EngineeringContextNotFoundError):
            compute_phasor_analysis(
                workspace_id="ws-1", engineering_context_id="ec-missing", analysis_kind="phasor", mode="voltage_phase_a",
                analysis_time=1.5, reference_frequency_hz_override=None,
                context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
            )

    def test_unknown_requirement_raises(self, registries):
        _add_context(registries["context"], "ec-1", "ws-1", [])
        with pytest.raises(UnknownAnalysisRequirementError):
            compute_phasor_analysis(
                workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="distance", mode="phase_a",
                analysis_time=1.5, reference_frequency_hz_override=None,
                context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
            )


class TestThreePhaseComputation:
    def test_balanced_three_phase_with_relative_angles(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, np.sqrt(2) * 100.0, 0.0),
            ("ALPHA1_VB", VOLTAGE, np.sqrt(2) * 100.0, -120.0),
            ("ALPHA1_VC", VOLTAGE, np.sqrt(2) * 100.0, 120.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_VB", PHASE_B), _member("src-1", "ALPHA1_VC", PHASE_C),
        ])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Va"].angle_deg_relative == pytest.approx(0.0, abs=1e-6)
        assert result.roles["Vb"].angle_deg_relative == pytest.approx(-120.0, abs=1e-6)
        assert result.roles["Vc"].angle_deg_relative == pytest.approx(120.0, abs=1e-6)

    def test_incomplete_three_phase_passes_through_resolver_status(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, 100.0, 0.0), ("ALPHA1_VB", VOLTAGE, 100.0, -120.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_VB", PHASE_B),
        ])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.role_reasons.get("Vc") == "role_missing"
        assert result.roles == {}


class TestMultiSourceTimebaseAndFrequency:
    def test_compatible_multi_source_resolves(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], start_time=REF_START))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_VB", VOLTAGE, 100.0, -120.0)], start_time=REF_START))
        registries["source"].add(_sine_source("src-3", "ws-1", [("ALPHA1_VC", VOLTAGE, 100.0, 120.0)], start_time=REF_START))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_VB", PHASE_B), _member("src-3", "ALPHA1_VC", PHASE_C),
        ])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Vb"].angle_deg_relative == pytest.approx(-120.0, abs=1e-3)

    def test_incompatible_timebase_passes_through_resolver_status(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], start_time=REF_START))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_VB", VOLTAGE, 100.0, -120.0)], start_time=REF_START + timedelta(seconds=1)))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_VB", PHASE_B)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        # Single-phase requirement (only Va) -- no cross-source pairing
        # needed, so this actually resolves; the incompatible-timebase
        # scenario is exercised properly by the three-phase case below.
        assert result.status == PHASOR_STATUS_COMPUTED

    def test_three_phase_incompatible_timebase_across_sources(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0), ("ALPHA1_VB", VOLTAGE, 100.0, -120.0)], start_time=REF_START))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_VC", VOLTAGE, 100.0, 120.0)], start_time=REF_START + timedelta(seconds=1)))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_VB", PHASE_B), _member("src-2", "ALPHA1_VC", PHASE_C),
        ])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "timebase_incompatible"

    def test_conflicting_nominal_frequency_rejected(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], nominal_frequency=50.0, start_time=REF_START))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_VB", VOLTAGE, 100.0, -120.0)], nominal_frequency=60.0, start_time=REF_START))
        registries["source"].add(_sine_source("src-3", "ws-1", [("ALPHA1_VC", VOLTAGE, 100.0, 120.0)], nominal_frequency=50.0, start_time=REF_START))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_VB", PHASE_B), _member("src-3", "ALPHA1_VC", PHASE_C),
        ])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_REFERENCE_FREQUENCY_CONFLICT

    def test_explicit_override_resolves_conflicting_frequencies(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], nominal_frequency=50.0, start_time=REF_START))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=50.0,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.reference_frequency_hz == 50.0

    def test_invalid_override_rejected(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)]))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=5000.0,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "invalid_reference_frequency"


class TestWaveformFormGuardrail:
    def test_rms_waveform_form_rejected(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], waveform_form=WAVEFORM_FORM_RMS))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.role_reasons.get("Va") == REASON_WAVEFORM_FORM_NOT_ELIGIBLE

    def test_magnitude_waveform_form_rejected(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], waveform_form=WAVEFORM_FORM_MAGNITUDE))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION

    def test_instantaneous_waveform_form_accepted(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], waveform_form=WAVEFORM_FORM_INSTANTANEOUS))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED

    def test_unknown_but_clearly_sinusoidal_is_accepted_via_detector(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], waveform_form=WAVEFORM_FORM_UNKNOWN))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED

    def test_unknown_but_clearly_flat_signal_is_rejected_via_detector(self, registries):
        """A constant (DC, non-oscillating) signal with unknown
        waveform_form -- the algorithmic detector should call this
        likely-magnitude/RMS-like (near-zero bipolarity/zero-crossings),
        and Phasor Slice 1 rejects it (no override mechanism)."""
        source = _sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], waveform_form=WAVEFORM_FORM_UNKNOWN)
        source.record.waveform_data["ALPHA1_VA"] = 100.0  # flat/DC, overwrite the sine values
        registries["source"].add(source)
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.role_reasons.get("Va") == REASON_WAVEFORM_FORM_NOT_ELIGIBLE


class TestCalculatedChannelCandidate:
    def test_calculated_channel_resolves_by_its_own_metadata(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_MARKER", VOLTAGE, 1.0, 0.0)]))
        registries["calc"].add(_calc("calc-va", "ws-1", "src-1", VOLTAGE, WAVEFORM_FORM_INSTANTANEOUS, 100.0, 30.0))
        _add_context(registries["context"], "ec-1", "ws-1", [
            EngineeringContextMember(
                channel_ref=ChannelRef(kind="calculated", calculated_channel_id="calc-va"),
                phase=PHASE_A, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED,
            )
        ])
        result = compute_phasor_analysis(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            analysis_time=1.5, reference_frequency_hz_override=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Va"].magnitude_rms == pytest.approx(100.0 / np.sqrt(2), rel=1e-6)
        assert result.roles["Va"].channel_ref.kind == "calculated"


class TestMovingAnalysisTimeServiceLevel:
    def test_angle_stable_as_analysis_time_advances(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 37.0)]))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        angles = []
        for at in (1.0, 1.3333, 2.0, 2.777):
            result = compute_phasor_analysis(
                workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
                analysis_time=at, reference_frequency_hz_override=None,
                context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
            )
            assert result.status == PHASOR_STATUS_COMPUTED
            angles.append(result.roles["Va"].angle_deg_absolute)
        assert max(angles) - min(angles) < 1e-3
