"""Tests for `app.services.phasor_analysis_service.compute_phasor_diagram()`
(Phasor UAT redesign -- bay-centric aggregation; see
docs/project-memory/PHASOR_ANALYSIS.md's own "Bay-centric Phasor
Diagram" section). Resolves ALL SIX supported single-phase roles
(Va/Vb/Vc/Ia/Ib/Ic) for one Engineering Context independently -- a
partial bay is a normal result, never a whole-request failure; only a
genuine cross-role incompatibility (reference-frequency conflict,
timebase incompatibility) blocks the combined result.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import (
    CURRENT,
    VOLTAGE,
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_RMS,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.domain.metadata import RecordingMetadata
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C, PHASE_SOURCE_ENGINEER_CONFIRMED
from app.domain.phasor import (
    PHASOR_STATUS_COMPUTED,
    REASON_REFERENCE_FREQUENCY_CONFLICT,
    ROLE_STATUS_AMBIGUOUS,
    ROLE_STATUS_AVAILABLE,
    ROLE_STATUS_MISSING,
    ROLE_STATUS_NEEDS_CONFIGURATION,
    ROLE_STATUS_NOT_ELIGIBLE,
)
from app.domain.analysis_input_resolution import STATUS_NEEDS_CONFIGURATION
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import EngineeringContextNotFoundError
from app.services.phasor_analysis_service import compute_phasor_diagram
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


def _compute(registries, *, context_id="ec-1", workspace_id="ws-1", analysis_time=1.5, reference_frequency_hz=None):
    return compute_phasor_diagram(
        workspace_id=workspace_id, engineering_context_id=context_id, analysis_time=analysis_time,
        reference_frequency_hz_override=reference_frequency_hz,
        context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
    )


class TestFullBay:
    def test_all_six_roles_available(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, np.sqrt(2) * 100.0, 0.0),
            ("ALPHA1_VB", VOLTAGE, np.sqrt(2) * 100.0, -120.0),
            ("ALPHA1_VC", VOLTAGE, np.sqrt(2) * 100.0, 120.0),
            ("ALPHA1_IA", CURRENT, np.sqrt(2) * 40.0, -30.0),
            ("ALPHA1_IB", CURRENT, np.sqrt(2) * 40.0, -150.0),
            ("ALPHA1_IC", CURRENT, np.sqrt(2) * 40.0, 90.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_VB", PHASE_B), _member("src-1", "ALPHA1_VC", PHASE_C),
            _member("src-1", "ALPHA1_IA", PHASE_A), _member("src-1", "ALPHA1_IB", PHASE_B), _member("src-1", "ALPHA1_IC", PHASE_C),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert set(result.roles) == {"Va", "Vb", "Vc", "Ia", "Ib", "Ic"}
        for role_key in result.roles:
            assert result.roles[role_key].status == ROLE_STATUS_AVAILABLE
        assert result.roles["Va"].magnitude_rms == pytest.approx(100.0, rel=1e-6)
        assert result.roles["Ia"].magnitude_rms == pytest.approx(40.0, rel=1e-6)
        assert result.roles["Va"].unit == "V"
        assert result.roles["Ia"].unit == "A"
        # Absolute angles preserve the true V-I relationship: Ia was
        # defined 30 degrees behind Va (a lagging power-factor angle),
        # NOT independently zero-referenced against its own family.
        assert (result.roles["Va"].angle_deg_absolute - result.roles["Ia"].angle_deg_absolute) == pytest.approx(30.0, abs=1e-3)
        # Per-family relative angle is still available as SECONDARY info.
        assert result.roles["Vb"].angle_deg_relative == pytest.approx(-120.0, abs=1e-3)
        assert result.roles["Ib"].angle_deg_relative == pytest.approx(-120.0, abs=1e-3)

    def test_unknown_context_raises(self, registries):
        with pytest.raises(EngineeringContextNotFoundError):
            _compute(registries, context_id="ec-missing")


class TestPartialAvailability:
    def test_voltage_only_context(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, 100.0, 0.0), ("ALPHA1_VB", VOLTAGE, 100.0, -120.0), ("ALPHA1_VC", VOLTAGE, 100.0, 120.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_VB", PHASE_B), _member("src-1", "ALPHA1_VC", PHASE_C),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        for role_key in ("Va", "Vb", "Vc"):
            assert result.roles[role_key].status == ROLE_STATUS_AVAILABLE
        for role_key in ("Ia", "Ib", "Ic"):
            assert result.roles[role_key].status == ROLE_STATUS_MISSING

    def test_current_only_context(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_IA", CURRENT, 40.0, 0.0), ("ALPHA1_IB", CURRENT, 40.0, -120.0), ("ALPHA1_IC", CURRENT, 40.0, 120.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_IA", PHASE_A), _member("src-1", "ALPHA1_IB", PHASE_B), _member("src-1", "ALPHA1_IC", PHASE_C),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        for role_key in ("Ia", "Ib", "Ic"):
            assert result.roles[role_key].status == ROLE_STATUS_AVAILABLE
        for role_key in ("Va", "Vb", "Vc"):
            assert result.roles[role_key].status == ROLE_STATUS_MISSING

    def test_two_vector_partial_context(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, 100.0, 0.0), ("ALPHA1_IA", CURRENT, 40.0, -30.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_IA", PHASE_A),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Va"].status == ROLE_STATUS_AVAILABLE
        assert result.roles["Ia"].status == ROLE_STATUS_AVAILABLE
        for role_key in ("Vb", "Vc", "Ib", "Ic"):
            assert result.roles[role_key].status == ROLE_STATUS_MISSING

    def test_no_supported_roles_resolvable(self, registries):
        _add_context(registries["context"], "ec-1", "ws-1", [])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert all(role.status == ROLE_STATUS_MISSING for role in result.roles.values())


class TestOneBadRoleDoesNotBlockOthers:
    def test_ambiguous_role_does_not_block_others(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, 100.0, 0.0),
            ("ALPHA1_VB", VOLTAGE, 100.0, -120.0), ("ALPHA1_VB2", VOLTAGE, 100.0, -119.0),
            ("ALPHA1_VC", VOLTAGE, 100.0, 120.0),
        ]))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A),
            _member("src-1", "ALPHA1_VB", PHASE_B), _member("src-1", "ALPHA1_VB2", PHASE_B),
            _member("src-1", "ALPHA1_VC", PHASE_C),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Vb"].status == ROLE_STATUS_AMBIGUOUS
        assert result.roles["Va"].status == ROLE_STATUS_AVAILABLE
        assert result.roles["Vc"].status == ROLE_STATUS_AVAILABLE

    def test_one_waveform_form_failure_does_not_block_others(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [
            ("ALPHA1_VA", VOLTAGE, 100.0, 0.0), ("ALPHA1_VB", VOLTAGE, 100.0, -120.0),
        ]))
        registries["source"].add(_sine_source("src-2", "ws-1", [
            ("ALPHA1_VC", VOLTAGE, 100.0, 120.0),
        ], waveform_form=WAVEFORM_FORM_RMS, start_time=REF_START))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_VB", PHASE_B), _member("src-2", "ALPHA1_VC", PHASE_C),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Vc"].status == ROLE_STATUS_NOT_ELIGIBLE
        assert result.roles["Va"].status == ROLE_STATUS_AVAILABLE
        assert result.roles["Vb"].status == ROLE_STATUS_AVAILABLE


class TestWholeResultBlockingConditions:
    def test_reference_frequency_conflict_blocks_combined_result(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], nominal_frequency=50.0))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_IA", CURRENT, 40.0, -30.0)], nominal_frequency=60.0))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_IA", PHASE_A),
        ])
        result = _compute(registries)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_REFERENCE_FREQUENCY_CONFLICT
        assert result.roles["Va"].status == ROLE_STATUS_NEEDS_CONFIGURATION
        assert result.roles["Ia"].status == ROLE_STATUS_NEEDS_CONFIGURATION
        assert result.roles["Va"].reason_code == REASON_REFERENCE_FREQUENCY_CONFLICT
        for role_key in ("Vb", "Vc", "Ib", "Ic"):
            assert result.roles[role_key].status == ROLE_STATUS_MISSING

    def test_explicit_override_resolves_conflicting_frequencies(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], nominal_frequency=50.0))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_IA", CURRENT, 40.0, -30.0)], nominal_frequency=60.0))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_IA", PHASE_A),
        ])
        result = _compute(registries, reference_frequency_hz=50.0)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Va"].status == ROLE_STATUS_AVAILABLE
        assert result.roles["Ia"].status == ROLE_STATUS_AVAILABLE

    def test_timebase_incompatibility_blocks_combined_result(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], start_time=REF_START))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_IA", CURRENT, 40.0, -30.0)], start_time=REF_START + timedelta(seconds=1)))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_IA", PHASE_A),
        ])
        result = _compute(registries)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "timebase_incompatible"


class TestMultiSourceCompatibleContext:
    def test_compatible_multi_source_context_resolves(self, registries):
        registries["source"].add(_sine_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE, 100.0, 0.0)], start_time=REF_START))
        registries["source"].add(_sine_source("src-2", "ws-1", [("ALPHA1_IA", CURRENT, 40.0, -30.0)], start_time=REF_START))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A), _member("src-2", "ALPHA1_IA", PHASE_A),
        ])
        result = _compute(registries)
        assert result.status == PHASOR_STATUS_COMPUTED
        assert result.roles["Va"].status == ROLE_STATUS_AVAILABLE
        assert result.roles["Ia"].status == ROLE_STATUS_AVAILABLE
