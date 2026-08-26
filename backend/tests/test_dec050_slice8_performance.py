"""DEC-050 Slice 8 performance regression guard.

Not a formal SLA (none is defined in the canonical docs) -- this exists
to catch an obvious future regression class (per-sample registry
access, repeated grouping-detector invocation, non-vectorized PU
conversion) rather than to enforce a tight latency budget. Thresholds
are deliberately generous so this never flakes on a loaded CI runner;
see the module-level `PU_OVERHEAD_RATIO_CEILING` for the actual bar.

Benchmarks the group-aware Per-Unit path directly at the service layer
(`extract_waveform_range`), bypassing HTTP/TestClient overhead, so the
measurement isolates PU resolution + conversion cost specifically --
not upload/parse/serialization noise.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import WAVEFORM_FORM_UNKNOWN
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_MANUAL, MeasurementGroup
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import set_current_base_manual
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base
from app.services.waveform_service import extract_waveform_range

WS = "ws-perf"
SRC = "src-perf"
BASE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Generous ceiling: PU conversion may cost at most this many times an
# engineering-mode request of the same size. A per-sample registry
# lookup or a repeated grouping-detector scan would blow this well past
# 10x on a 500k-sample array; ordinary vectorized conversion overhead is
# a small constant fraction of the array-copy cost already paid by the
# engineering path.
PU_OVERHEAD_RATIO_CEILING = 8.0

LARGE_SAMPLE_COUNT = 500_000
GROUP_COUNT = 20  # 10 Voltage + 10 Current, per section 12's own "large-group" scale


def _large_active_source() -> ActiveSource:
    time_arr = np.linspace(0.0, 5.0, LARGE_SAMPLE_COUNT)
    channels: dict[str, np.ndarray] = {}
    units: dict[str, str] = {}
    engineering_types: dict[str, str] = {}
    rng = np.random.default_rng(0)
    for i in range(GROUP_COUNT):
        for phase in ("R", "Y", "B"):
            if i < GROUP_COUNT // 2:
                name = f"V{i}_{phase}"
                channels[name] = 100.0 + rng.normal(0, 1, LARGE_SAMPLE_COUNT)
                units[name] = "kV"
                engineering_types[name] = "Voltage"
            else:
                name = f"I{i}_{phase}"
                channels[name] = 1000.0 + rng.normal(0, 1, LARGE_SAMPLE_COUNT)
                units[name] = "A"
                engineering_types[name] = "Current"

    col_data = {"time": time_arr, **channels}
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="PERF", recorder_name="TEST", source_file="perf.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(col_data),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[100000.0], samples_per_rate=[LARGE_SAMPLE_COUNT]),
        timing_info=TimingInformation(start_time=BASE_START, trigger_time=BASE_START),
    )
    metadata = SourceMetadata(
        source_id=SRC, workspace_id=WS, provider_type="COMTRADE",
        original_filenames=("perf.cfg", "perf.dat"), created_at=BASE_START,
        station_name="PERF", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference="absolute", start_time=BASE_START, trigger_time=BASE_START,
        sample_count=LARGE_SAMPLE_COUNT, duration_seconds=5.0,
        elapsed_start_seconds=0.0, elapsed_end_seconds=5.0,
        sampling_rates=(100000.0,), samples_per_rate=(LARGE_SAMPLE_COUNT,),
        analog_channels=[
            AnalogChannelSummary(
                name=name, index=i, unit=units[name], engineering_type=engineering_types[name],
                waveform_form=WAVEFORM_FORM_UNKNOWN,
            )
            for i, name in enumerate(channels)
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _build_registries():
    group_registry = MeasurementGroupRegistry()
    voltage_config_registry = VoltageGroupConfigRegistry()
    current_config_registry = CurrentGroupConfigRegistry()
    for i in range(GROUP_COUNT):
        if i < GROUP_COUNT // 2:
            name = f"V{i}"
            group = MeasurementGroup(
                id=f"mg-{name}", workspace_id=WS, source_id=SRC, kind=KIND_VOLTAGE, display_name=name,
                channel_refs=[ChannelRef(kind="source", source_id=SRC, channel_name=f"{name}_{p}") for p in ("R", "Y", "B")],
                status=STATUS_MANUAL,
            )
            group_registry.add(group)
            set_voltage_base(
                workspace_id=WS, measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
                group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            )
        else:
            name = f"I{i}"
            group = MeasurementGroup(
                id=f"mg-{name}", workspace_id=WS, source_id=SRC, kind=KIND_CURRENT, display_name=name,
                channel_refs=[ChannelRef(kind="source", source_id=SRC, channel_name=f"{name}_{p}") for p in ("R", "Y", "B")],
                status=STATUS_MANUAL,
            )
            group_registry.add(group)
            set_current_base_manual(
                workspace_id=WS, measurement_group_id=group.id, manual_ibase_ka=2.0,
                group_registry=group_registry, current_config_registry=current_config_registry,
            )
    return group_registry, voltage_config_registry, current_config_registry


@pytest.fixture(scope="module")
def perf_fixture():
    active = _large_active_source()
    group_registry, voltage_config_registry, current_config_registry = _build_registries()
    return active, group_registry, voltage_config_registry, current_config_registry


def _time_extraction(active, channel_name, unit_mode, group_registry, voltage_config_registry, current_config_registry, repeats=5):
    start = time.perf_counter()
    for _ in range(repeats):
        extract_waveform_range(
            active, channel_name=channel_name, start_time=None, end_time=None, point_budget=4000,
            unit_mode=unit_mode,
            workspace_id=WS, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
    return (time.perf_counter() - start) / repeats


class TestGroupAwarePerUnitPerformance:
    def test_per_unit_overhead_is_bounded_for_a_large_grouped_voltage_channel(self, perf_fixture, capsys):
        active, group_registry, voltage_config_registry, current_config_registry = perf_fixture
        engineering_time = _time_extraction(active, "V0_R", "engineering", group_registry, voltage_config_registry, current_config_registry)
        per_unit_time = _time_extraction(active, "V0_R", "per_unit", group_registry, voltage_config_registry, current_config_registry)
        ratio = per_unit_time / engineering_time if engineering_time > 0 else float("inf")
        with capsys.disabled():
            print(
                f"\n[perf] Voltage, {LARGE_SAMPLE_COUNT:,} samples, {GROUP_COUNT} groups: "
                f"engineering={engineering_time * 1000:.3f} ms, per_unit={per_unit_time * 1000:.3f} ms, "
                f"ratio={ratio:.2f}x"
            )
        assert ratio < PU_OVERHEAD_RATIO_CEILING, (
            f"Per-Unit conversion took {ratio:.1f}x longer than engineering mode for a "
            f"{LARGE_SAMPLE_COUNT:,}-sample array across {GROUP_COUNT} groups -- "
            "investigate for per-sample registry access or a non-vectorized conversion path."
        )

    def test_per_unit_overhead_is_bounded_for_a_large_grouped_current_channel(self, perf_fixture, capsys):
        active, group_registry, voltage_config_registry, current_config_registry = perf_fixture
        engineering_time = _time_extraction(active, f"I{GROUP_COUNT - 1}_R", "engineering", group_registry, voltage_config_registry, current_config_registry)
        per_unit_time = _time_extraction(active, f"I{GROUP_COUNT - 1}_R", "per_unit", group_registry, voltage_config_registry, current_config_registry)
        ratio = per_unit_time / engineering_time if engineering_time > 0 else float("inf")
        with capsys.disabled():
            print(
                f"\n[perf] Current, {LARGE_SAMPLE_COUNT:,} samples, {GROUP_COUNT} groups: "
                f"engineering={engineering_time * 1000:.3f} ms, per_unit={per_unit_time * 1000:.3f} ms, "
                f"ratio={ratio:.2f}x"
            )
        assert ratio < PU_OVERHEAD_RATIO_CEILING

    def test_lookup_cost_does_not_scale_with_group_count(self, perf_fixture, capsys):
        """A registry with GROUP_COUNT groups must resolve a single
        channel's group just as fast as a registry with one group --
        proving the lookup is indexed (O(1)), never a linear scan over
        every stored group."""
        active, group_registry, voltage_config_registry, current_config_registry = perf_fixture
        many_groups_time = _time_extraction(active, "V0_R", "per_unit", group_registry, voltage_config_registry, current_config_registry, repeats=10)

        small_group_registry, small_voltage_registry, small_current_registry = _build_registries()
        # Keep only ONE group in the small registry to compare against.
        for wid_gid in list(small_group_registry._groups.keys()):
            if wid_gid[1] != "mg-V0":
                small_group_registry.remove(wid_gid[0], wid_gid[1])
        one_group_time = _time_extraction(active, "V0_R", "per_unit", small_group_registry, small_voltage_registry, small_current_registry, repeats=10)

        with capsys.disabled():
            print(
                f"\n[perf] Lookup scaling: {GROUP_COUNT} groups={many_groups_time * 1000:.4f} ms, "
                f"1 group={one_group_time * 1000:.4f} ms"
            )
        # Generous: allow up to 3x noise, never the near-linear-with-
        # group-count blowup a dict-scan implementation would show.
        assert many_groups_time < one_group_time * 3.0 + 0.005
