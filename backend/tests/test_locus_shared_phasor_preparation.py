"""DEC-114: Impedance Locus and Distance Protection locus performance --
`compute_impedance_locus()`/`compute_distance_locus()` now call
`app.services.phasor_analysis_service.prepare_phasor_diagram()` ONCE for
the whole locus and `evaluate_prepared_phasor_diagram()` per sample time,
instead of calling the full `compute_phasor_diagram()` pipeline (role
resolution, candidate fetch, reference-frequency agreement, waveform-form
eligibility, shared-time-coordinate/timebase checks) independently for
every one of up to `MAX_LOCUS_POINTS` sample times. See
docs/project-memory/DECISIONS.md DEC-114 and docs/project-memory/
IMPEDANCE_LOCUS_ANALYSIS.md.

This module proves:
- numerical equivalence: a locus's own per-point result matches calling
  the still-unchanged single-point `compute_impedance_analysis()`/
  `compute_distance_analysis()` independently at the same sample times;
- structural equivalence: the STATIC preparation work (role resolution,
  waveform-form eligibility) runs a fixed, small number of times for the
  whole locus, never once per sample point;
- per-point failure semantics are preserved (an early, pre-first-cycle
  sample is reported `needs_configuration`/`insufficient_window_history`,
  never dropped, and never affects any OTHER point in the same locus);
- a genuine static/whole-request failure (e.g. a reference-frequency
  conflict) is reported identically for EVERY point in the locus, since
  it is now detected once during preparation rather than rediscovered
  independently per point.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import app.services.phasor_analysis_service as pas
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE, WAVEFORM_FORM_INSTANTANEOUS
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.distance_protection import ZoneSettings
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.domain.metadata import RecordingMetadata
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C, PHASE_SOURCE_ENGINEER_CONFIRMED
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.distance_protection_analysis_service import compute_distance_analysis, compute_distance_locus
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.impedance_analysis_service import compute_impedance_analysis, compute_impedance_locus
from app.services.workspace_registry import WorkspaceRegistry

SAMPLE_RATE_HZ = 1000.0
DURATION_S = 2.0
REF_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _sine_source(
    source_id, workspace_id, channels, *, nominal_frequency=50.0, start_time=REF_START,
    waveform_form=WAVEFORM_FORM_INSTANTANEOUS, duration_s=DURATION_S,
):
    n = int(round(duration_s * SAMPLE_RATE_HZ))
    t = np.arange(n) / SAMPLE_RATE_HZ
    analog_channels = []
    columns = {"time": t}
    for name, etype, amp_peak, phase_deg in channels:
        columns[name] = amp_peak * np.cos(2.0 * np.pi * nominal_frequency * t + np.radians(phase_deg))
        analog_channels.append(AnalogChannelSummary(
            name=name, index=len(analog_channels), unit="V" if etype == VOLTAGE else "A",
            engineering_type=etype, waveform_form=waveform_form,
        ))
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
        sample_count=n, duration_seconds=duration_s, elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(SAMPLE_RATE_HZ,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _member(source_id, name, phase):
    return EngineeringContextMember(
        channel_ref=ChannelRef(kind="source", source_id=source_id, channel_name=name), phase=phase,
        phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED,
    )


@pytest.fixture
def registries():
    return {
        "context": EngineeringContextRegistry(),
        "source": WorkspaceRegistry(),
        "calc": CalculatedChannelRegistry(),
    }


def _full_bay(registries, workspace_id="ws-1", context_id="ec-1", *, current_amp=1.0, **source_kwargs):
    registries["source"].add(_sine_source("src-1", workspace_id, [
        ("ZBAY_VA", VOLTAGE, np.sqrt(2) * 100.0, 0.0), ("ZBAY_VB", VOLTAGE, np.sqrt(2) * 100.0, -120.0), ("ZBAY_VC", VOLTAGE, np.sqrt(2) * 100.0, 120.0),
        ("ZBAY_IA", CURRENT, np.sqrt(2) * current_amp, -30.0), ("ZBAY_IB", CURRENT, np.sqrt(2) * current_amp, -150.0), ("ZBAY_IC", CURRENT, np.sqrt(2) * current_amp, 90.0),
    ], **source_kwargs))
    registries["context"].add(EngineeringContext(id=context_id, workspace_id=workspace_id, display_name="Zbay", members=[
        _member("src-1", "ZBAY_VA", PHASE_A), _member("src-1", "ZBAY_VB", PHASE_B), _member("src-1", "ZBAY_VC", PHASE_C),
        _member("src-1", "ZBAY_IA", PHASE_A), _member("src-1", "ZBAY_IB", PHASE_B), _member("src-1", "ZBAY_IC", PHASE_C),
    ]))
    return workspace_id, context_id


def _count_calls(monkeypatch, target_module, name):
    original = getattr(target_module, name)
    counter = {"n": 0}

    def wrapper(*args, **kwargs):
        counter["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(target_module, name, wrapper)
    return counter


DISABLED_ZONE = ZoneSettings(enabled=False)


class TestImpedanceLocusEquivalence:
    def test_locus_matches_independent_single_point_calls(self, registries):
        workspace_id, context_id = _full_bay(registries)
        sample_times = [0.3, 0.7, 1.1, 1.5, 1.9]
        kwargs = dict(
            workspace_id=workspace_id, engineering_context_id=context_id, phase="A",
            reference_frequency_hz_override=None, recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        locus_points = compute_impedance_locus(
            start_time=sample_times[0], end_time=sample_times[-1], point_count=len(sample_times), **kwargs,
        )
        assert [round(p.analysis_time, 6) for p in locus_points] == [round(t, 6) for t in sample_times]

        for point, t in zip(locus_points, sample_times):
            single = compute_impedance_analysis(analysis_time=t, **kwargs)
            assert point.status == single.status
            assert point.resistance_ohm == single.resistance_ohm
            assert point.reactance_ohm == single.reactance_ohm
            assert point.magnitude_ohm == single.magnitude_ohm
            assert point.angle_deg == single.angle_deg
            assert point.reason_code == single.reason_code

    def test_static_preparation_runs_once_not_per_point(self, registries, monkeypatch):
        workspace_id, context_id = _full_bay(registries)
        resolve_counter = _count_calls(monkeypatch, pas, "resolve_analysis_inputs")
        fetch_counter = _count_calls(monkeypatch, pas, "_fetch_role_candidate")
        eligible_counter = _count_calls(monkeypatch, pas, "_waveform_form_eligible")

        compute_impedance_locus(
            workspace_id=workspace_id, engineering_context_id=context_id, phase="A",
            start_time=0.3, end_time=1.9, point_count=50, reference_frequency_hz_override=None,
            recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )

        # One call per role (Va/Vb/Vc/Ia/Ib/Ic) for the WHOLE 50-point locus,
        # never once per role per point (which would be 300).
        assert resolve_counter["n"] == 6
        assert fetch_counter["n"] == 6
        assert eligible_counter["n"] == 6

    def test_early_window_point_reported_not_dropped(self, registries):
        workspace_id, context_id = _full_bay(registries)
        sample_times = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
        points = compute_impedance_locus(
            workspace_id=workspace_id, engineering_context_id=context_id, phase="A",
            start_time=sample_times[0], end_time=sample_times[-1], point_count=len(sample_times),
            reference_frequency_hz_override=None, recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert len(points) == len(sample_times)  # never silently dropped
        assert points[0].status == "needs_configuration"
        assert points[0].reason_code == "insufficient_window_history"
        for later in points[1:]:
            assert later.status == "computed"
            assert later.magnitude_ohm == pytest.approx(100.0, rel=1e-2)

    def test_current_too_small_preserved_across_every_point(self, registries):
        workspace_id, context_id = _full_bay(registries, current_amp=1e-6)
        points = compute_impedance_locus(
            workspace_id=workspace_id, engineering_context_id=context_id, phase="A",
            start_time=0.3, end_time=1.9, point_count=10, reference_frequency_hz_override=None,
            recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert len(points) == 10
        for p in points:
            assert p.status == "needs_configuration"
            assert p.reason_code == "current_too_small"
            assert p.magnitude_ohm is None

    def test_static_whole_request_failure_applies_identically_to_every_point(self, registries):
        workspace_id = "ws-conflict"
        registries["source"].add(_sine_source("src-50hz", workspace_id, [("ZBAY_VA", VOLTAGE, 100.0, 0.0)], nominal_frequency=50.0))
        registries["source"].add(_sine_source("src-60hz", workspace_id, [("ZBAY_IA", CURRENT, 1.0, -30.0)], nominal_frequency=60.0))
        registries["context"].add(EngineeringContext(id="ec-conflict", workspace_id=workspace_id, display_name="Zbay", members=[
            _member("src-50hz", "ZBAY_VA", PHASE_A), _member("src-60hz", "ZBAY_IA", PHASE_A),
        ]))
        points = compute_impedance_locus(
            workspace_id=workspace_id, engineering_context_id="ec-conflict", phase="A",
            start_time=0.3, end_time=1.5, point_count=8, reference_frequency_hz_override=None,
            recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert len(points) == 8
        for p in points:
            assert p.status == "needs_configuration"
            assert p.reason_code == "reference_frequency_conflict"


class TestDistanceLocusEquivalence:
    def _kwargs(self, registries, workspace_id, context_id):
        return dict(
            workspace_id=workspace_id, engineering_context_id=context_id, loop="AB",
            reference_frequency_hz_override=None, recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            characteristic="mho", zone1=DISABLED_ZONE, zone2=DISABLED_ZONE, zone3=DISABLED_ZONE,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )

    def test_locus_matches_independent_single_point_calls(self, registries):
        workspace_id, context_id = _full_bay(registries)
        sample_times = [0.3, 0.7, 1.1, 1.5, 1.9]
        kwargs = self._kwargs(registries, workspace_id, context_id)
        locus_points = compute_distance_locus(
            start_time=sample_times[0], end_time=sample_times[-1], point_count=len(sample_times), **kwargs,
        )
        assert [round(p.analysis_time, 6) for p in locus_points] == [round(t, 6) for t in sample_times]

        for point, t in zip(locus_points, sample_times):
            single = compute_distance_analysis(analysis_time=t, **kwargs)
            assert point.status == single.status
            assert point.resistance_ohm == single.resistance_ohm
            assert point.reactance_ohm == single.reactance_ohm
            assert point.magnitude_ohm == single.magnitude_ohm
            assert point.angle_deg == single.angle_deg
            assert point.reason_code == single.reason_code

    def test_static_preparation_runs_once_not_per_point(self, registries, monkeypatch):
        workspace_id, context_id = _full_bay(registries)
        resolve_counter = _count_calls(monkeypatch, pas, "resolve_analysis_inputs")
        fetch_counter = _count_calls(monkeypatch, pas, "_fetch_role_candidate")
        eligible_counter = _count_calls(monkeypatch, pas, "_waveform_form_eligible")

        compute_distance_locus(
            start_time=0.3, end_time=1.9, point_count=50, **self._kwargs(registries, workspace_id, context_id),
        )

        assert resolve_counter["n"] == 6
        assert fetch_counter["n"] == 6
        assert eligible_counter["n"] == 6

    def test_early_window_point_reported_not_dropped(self, registries):
        workspace_id, context_id = _full_bay(registries)
        sample_times = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
        points = compute_distance_locus(
            start_time=sample_times[0], end_time=sample_times[-1], point_count=len(sample_times),
            **self._kwargs(registries, workspace_id, context_id),
        )
        assert len(points) == len(sample_times)
        assert points[0].status == "needs_configuration"
        assert points[0].reason_code == "insufficient_window_history"
        for later in points[1:]:
            assert later.status == "computed"

    def test_loop_current_too_small_preserved_across_every_point(self, registries):
        workspace_id, context_id = _full_bay(registries, current_amp=1e-6)
        points = compute_distance_locus(
            start_time=0.3, end_time=1.9, point_count=10, **self._kwargs(registries, workspace_id, context_id),
        )
        assert len(points) == 10
        for p in points:
            assert p.status == "needs_configuration"
            assert p.reason_code == "loop_current_too_small"
            assert p.magnitude_ohm is None

    def test_static_whole_request_failure_applies_identically_to_every_point(self, registries):
        workspace_id = "ws-conflict-dist"
        registries["source"].add(_sine_source("src-50hz", workspace_id, [("ZBAY_VA", VOLTAGE, 100.0, 0.0), ("ZBAY_VB", VOLTAGE, 100.0, -120.0)], nominal_frequency=50.0))
        registries["source"].add(_sine_source("src-60hz", workspace_id, [("ZBAY_IA", CURRENT, 1.0, -30.0), ("ZBAY_IB", CURRENT, 1.0, -150.0)], nominal_frequency=60.0))
        registries["context"].add(EngineeringContext(id="ec-conflict", workspace_id=workspace_id, display_name="Zbay", members=[
            _member("src-50hz", "ZBAY_VA", PHASE_A), _member("src-50hz", "ZBAY_VB", PHASE_B),
            _member("src-60hz", "ZBAY_IA", PHASE_A), _member("src-60hz", "ZBAY_IB", PHASE_B),
        ]))
        points = compute_distance_locus(
            start_time=0.3, end_time=1.5, point_count=8, workspace_id=workspace_id, engineering_context_id="ec-conflict",
            loop="AB", reference_frequency_hz_override=None, recording_basis="secondary", impedance_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
            characteristic="mho", zone1=DISABLED_ZONE, zone2=DISABLED_ZONE, zone3=DISABLED_ZONE,
            context_registry=registries["context"], source_registry=registries["source"], calculated_channel_registry=registries["calc"],
        )
        assert len(points) == 8
        for p in points:
            assert p.status == "needs_configuration"
            assert p.reason_code == "reference_frequency_conflict"
