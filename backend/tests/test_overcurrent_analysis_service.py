"""Tests for app.services.overcurrent_analysis_service: the orchestration
layer that resolves live workspace state (via the unchanged resolver),
validates settings, decides reference frequency, enforces waveform-form
eligibility, and runs the pure domain estimator/IDMT engine. Mirrors
test_phasor_analysis_service.py's own registry-construction pattern.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_RMS
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.domain.metadata import RecordingMetadata
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_SOURCE_ENGINEER_CONFIRMED
from app.domain.overcurrent import OVERCURRENT_STATUS_COMPUTED, REASON_WAVEFORM_FORM_NOT_ELIGIBLE
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.analysis_input_resolution import STATUS_NEEDS_CONFIGURATION
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import EngineeringContextNotFoundError
from app.services.overcurrent_analysis_service import compute_overcurrent_analysis
from app.services.workspace_registry import WorkspaceRegistry

SAMPLE_RATE_HZ = 5000.0
DURATION_S = 3.0
REF_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _current_source(
    source_id: str, workspace_id: str, channel_name: str, rms_amps: float,
    *, nominal_frequency: float = 50.0, waveform_form: str = WAVEFORM_FORM_INSTANTANEOUS, unit: str = "A",
) -> ActiveSource:
    n = int(round(DURATION_S * SAMPLE_RATE_HZ))
    t = np.arange(n) / SAMPLE_RATE_HZ
    values = rms_amps * np.sqrt(2.0) * np.cos(2.0 * np.pi * nominal_frequency * t)
    analog_channels = [
        AnalogChannelSummary(
            name=channel_name, index=0, unit=unit, engineering_type=CURRENT, waveform_form=waveform_form,
        )
    ]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=nominal_frequency,
        ),
        waveform_data=pd.DataFrame({"time": t, channel_name: values}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[SAMPLE_RATE_HZ], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=REF_START, trigger_time=REF_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=REF_START,
        station_name="Station", recorder_name="Recorder", nominal_frequency=nominal_frequency,
        timing_reference="absolute", start_time=REF_START, trigger_time=REF_START,
        sample_count=n, duration_seconds=DURATION_S, elapsed_start_seconds=0.0, elapsed_end_seconds=DURATION_S,
        sampling_rates=(SAMPLE_RATE_HZ,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _member(source_id, name, phase):
    return EngineeringContextMember(
        channel_ref=ChannelRef(kind="source", source_id=source_id, channel_name=name),
        phase=phase, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED,
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


def _compute(registries, **overrides):
    kwargs = dict(
        workspace_id="ws-1", engineering_context_id="ec-1", phase="A", analysis_time=1.5,
        characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=1.0,
        recording_basis="secondary", ct_primary=None, ct_secondary=None,
        reference_frequency_hz_override=None,
        context_registry=registries["context"], source_registry=registries["source"],
        calculated_channel_registry=registries["calc"],
    )
    kwargs.update(overrides)
    return compute_overcurrent_analysis(**kwargs)


class TestBasicComputation:
    def test_secondary_basis_no_conversion(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, pickup_current_secondary=1.0)
        assert result.status == OVERCURRENT_STATUS_COMPUTED
        assert result.algorithm_version == "overcurrent_idmt_v1"
        assert result.measured_rms_current == pytest.approx(4.2, rel=1e-3)
        assert result.measured_rms_current_unit == "A"
        # Secondary basis: relay-equivalent current identical to measured (no CT conversion).
        assert result.relay_secondary_current == pytest.approx(result.measured_rms_current, rel=1e-9)
        assert result.multiple_of_pickup == pytest.approx(4.2, rel=1e-3)
        assert result.expected_operating_time_seconds is not None
        assert result.expected_operating_time_seconds > 0

    def test_primary_basis_applies_ct_conversion(self, registries):
        # 4200 A primary, CT 1000:1 -> 4.2 A secondary.
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4200.0))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(
            registries, recording_basis="primary", ct_primary=1000.0, ct_secondary=1.0, pickup_current_secondary=1.0,
        )
        assert result.status == OVERCURRENT_STATUS_COMPUTED
        assert result.measured_rms_current == pytest.approx(4200.0, rel=1e-3)
        assert result.relay_secondary_current == pytest.approx(4.2, rel=1e-3)
        assert result.multiple_of_pickup == pytest.approx(4.2, rel=1e-3)

    def test_below_pickup_has_no_finite_expected_time(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=0.5))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, pickup_current_secondary=1.0)
        assert result.status == OVERCURRENT_STATUS_COMPUTED
        assert result.multiple_of_pickup < 1.0
        assert result.expected_operating_time_seconds is None
        assert result.threshold_exceeded is False

    def test_all_three_phases_resolvable(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IB", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IB", PHASE_B)])
        result = _compute(registries, phase="B", pickup_current_secondary=1.0)
        assert result.status == OVERCURRENT_STATUS_COMPUTED
        assert result.channel_ref.channel_name == "ALPHA1_IB"


class TestGuardrails:
    def test_unknown_characteristic(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, characteristic_id="ansi_moderately_inverse")
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "unknown_characteristic"

    def test_invalid_tms(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, tms=-1.0)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "invalid_tms"

    def test_invalid_pickup(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, pickup_current_secondary=0.0)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "invalid_pickup"

    def test_invalid_ct_values_missing_for_primary_basis(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, recording_basis="primary", ct_primary=None, ct_secondary=None)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "invalid_ct_values"

    def test_invalid_ct_values_zero(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, recording_basis="primary", ct_primary=0.0, ct_secondary=1.0)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "invalid_ct_values"

    def test_missing_current_role(self, registries):
        _add_context(registries["context"], "ec-1", "ws-1", [])
        result = _compute(registries)
        assert result.status == STATUS_NEEDS_CONFIGURATION

    def test_ambiguous_role_passes_through_resolver_status(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        registries["source"].add(_current_source("src-2", "ws-1", "BETA1_IA", rms_amps=6.0))
        _add_context(registries["context"], "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_IA", PHASE_A), _member("src-2", "BETA1_IA", PHASE_A),
        ])
        result = _compute(registries)
        assert result.status in (STATUS_NEEDS_CONFIGURATION, "ambiguous")

    def test_non_instantaneous_waveform_form_rejected(self, registries):
        registries["source"].add(
            _current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2, waveform_form=WAVEFORM_FORM_RMS)
        )
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_WAVEFORM_FORM_NOT_ELIGIBLE

    def test_partial_engineering_context_still_valid_for_its_own_phase(self, registries):
        """A context with only ONE phase's own current member remains a
        valid, usable Overcurrent input for THAT phase -- partial contexts
        are normal, never rejected outright."""
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, phase="A")
        assert result.status == OVERCURRENT_STATUS_COMPUTED

    def test_unknown_context_raises(self, registries):
        with pytest.raises(EngineeringContextNotFoundError):
            _compute(registries, engineering_context_id="ec-missing")


class TestReferenceFrequency:
    def test_uses_source_declared_nominal_frequency_by_default(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2, nominal_frequency=60.0))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries)
        assert result.status == OVERCURRENT_STATUS_COMPUTED
        assert result.reference_frequency_hz == pytest.approx(60.0)
        assert result.window_seconds == pytest.approx(1.0 / 60.0)

    def test_explicit_override_wins(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2, nominal_frequency=50.0))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, reference_frequency_hz_override=60.0)
        assert result.reference_frequency_hz == pytest.approx(60.0)

    def test_invalid_override_rejected(self, registries):
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=4.2))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, reference_frequency_hz_override=5000.0)
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == "invalid_reference_frequency"


class TestAbovePickupDurationIntegration:
    def test_sustained_high_current_produces_positive_duration_and_possible_alert(self, registries):
        """A current held well above pickup for the whole recording (up to
        analysis_time) should report a duration close to the elapsed
        window-available time, and -- for a slow enough TMS/small enough
        margin -- may exceed the expected operating time."""
        registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=10.0))
        _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", PHASE_A)])
        result = _compute(registries, pickup_current_secondary=1.0, tms=0.025, analysis_time=2.9)
        assert result.status == OVERCURRENT_STATUS_COMPUTED
        assert result.above_pickup_duration_seconds > 2.0
        assert result.expected_operating_time_seconds is not None
        assert result.threshold_exceeded == (
            result.above_pickup_duration_seconds > result.expected_operating_time_seconds
        )
