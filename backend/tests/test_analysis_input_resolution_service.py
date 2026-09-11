"""Tests for app.services.analysis_input_resolution_service (Analysis
Guardrail Slice 2): the orchestration layer that resolves live workspace
state (context membership -> engineering metadata) and layers the
timebase-compatibility check on top of the pure domain resolver's own
role-matching result.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.analysis_input_resolution import (
    REASON_TIMEBASE_INCOMPATIBLE,
    STATUS_NEEDS_CONFIGURATION,
    STATUS_RESOLVED,
)
from app.domain.calculated_channel import CalculatedChannel, ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.domain.metadata import RecordingMetadata
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C, PHASE_SOURCE_ENGINEER_CONFIRMED
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.analysis_input_resolution_service import resolve_analysis_inputs
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import EngineeringContextNotFoundError, UnknownAnalysisRequirementError
from app.services.workspace_registry import WorkspaceRegistry

ELAPSED = [0.0, 0.25, 0.5, 0.75]


def _active_source(source_id: str, workspace_id: str, channels: list[tuple[str, str]], start_time: datetime) -> ActiveSource:
    analog_channels = [
        AnalogChannelSummary(name=name, index=i, unit="V" if etype == VOLTAGE else "A", engineering_type=etype)
        for i, (name, etype) in enumerate(channels)
    ]
    columns = {"time": list(ELAPSED)}
    for name, _etype in channels:
        columns[name] = [0.0, 1.0, 2.0, 3.0]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=start_time, trigger_time=start_time),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=start_time,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=start_time, trigger_time=start_time,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _calc(calc_id: str, workspace_id: str, reference_source_id: str, engineering_type: str, unit: str = "V") -> CalculatedChannel:
    n = 4
    return CalculatedChannel(
        id=calc_id, workspace_id=workspace_id, name=calc_id, unit=unit, operation="reverse_polarity",
        inputs=[ChannelRef(kind="source", source_id=reference_source_id, channel_name="X")],
        parameters={}, dependency_ids=[], reference_source_id=reference_source_id,
        time=np.array(ELAPSED, dtype=np.float64), values=np.ones(n, dtype=np.float64),
        created_at=datetime.now(timezone.utc), engineering_type=engineering_type,
    )


REF_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def source_registry() -> WorkspaceRegistry:
    registry = WorkspaceRegistry()
    registry.add(_active_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE), ("ALPHA1_VB", VOLTAGE), ("ALPHA1_IA", CURRENT), ("ALPHA1_MW", "Power")], REF_START))
    registry.add(_active_source("src-2", "ws-1", [("ALPHA1_VC", VOLTAGE)], REF_START))  # same start_time+elapsed as src-1 -- aligned
    registry.add(_active_source("src-3", "ws-1", [("ALPHA1_VC_LATE", VOLTAGE)], REF_START + timedelta(seconds=1)))  # misaligned
    registry.add(_active_source("bravo-src", "ws-1", [("BRAVO1_VB", VOLTAGE), ("BRAVO1_VC", VOLTAGE)], REF_START))
    return registry


@pytest.fixture
def calc_registry() -> CalculatedChannelRegistry:
    return CalculatedChannelRegistry()


@pytest.fixture
def context_registry() -> EngineeringContextRegistry:
    return EngineeringContextRegistry()


def _add_context(registry, context_id, workspace_id, members):
    registry.add(EngineeringContext(id=context_id, workspace_id=workspace_id, display_name="Test Context", members=members))


def _member(source_id, name, phase, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED):
    return EngineeringContextMember(
        channel_ref=ChannelRef(kind="source", source_id=source_id, channel_name=name),
        phase=phase, phase_source=phase_source,
    )


class TestBasicResolution:
    def test_single_phase_resolves(self, source_registry, calc_registry, context_registry):
        _add_context(context_registry, "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_RESOLVED
        assert result.resolved_roles["Va"].channel_name == "ALPHA1_VA"

    def test_unknown_context_raises(self, source_registry, calc_registry, context_registry):
        with pytest.raises(EngineeringContextNotFoundError):
            resolve_analysis_inputs(
                workspace_id="ws-1", engineering_context_id="ec-missing", analysis_kind="phasor", mode="voltage_phase_a",
                context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_unknown_requirement_raises(self, source_registry, calc_registry, context_registry):
        _add_context(context_registry, "ec-1", "ws-1", [])
        with pytest.raises(UnknownAnalysisRequirementError):
            resolve_analysis_inputs(
                workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="distance", mode="phase_a",
                context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )


class TestContextIsolation:
    def test_bravo_members_never_satisfy_alpha_requirement(self, source_registry, calc_registry, context_registry):
        _add_context(context_registry, "ec-alpha", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A)])
        _add_context(context_registry, "ec-bravo", "ws-1", [_member("bravo-src", "BRAVO1_VB", PHASE_B), _member("bravo-src", "BRAVO1_VC", PHASE_C)])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-alpha", analysis_kind="phasor", mode="voltage_three_phase",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert set(result.missing_roles) == {"Vb", "Vc"}


class TestMultiSourceTimebase:
    def test_compatible_timebases_resolve(self, source_registry, calc_registry, context_registry):
        _add_context(context_registry, "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A),
            _member("src-1", "ALPHA1_VB", PHASE_B),
            _member("src-2", "ALPHA1_VC", PHASE_C),  # different source, SAME start_time/elapsed
        ])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_RESOLVED
        assert result.resolved_roles["Vc"].source_id == "src-2"

    def test_incompatible_timebases_downgrade_to_needs_configuration(self, source_registry, calc_registry, context_registry):
        _add_context(context_registry, "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A),
            _member("src-1", "ALPHA1_VB", PHASE_B),
            _member("src-3", "ALPHA1_VC_LATE", PHASE_C),  # 1 second later start_time -- misaligned
        ])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_three_phase",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_TIMEBASE_INCOMPATIBLE
        # Role identity was still correctly resolved before the downgrade.
        assert result.resolved_roles["Va"].channel_name == "ALPHA1_VA"

    def test_same_source_roles_never_need_array_comparison_to_resolve(self, source_registry, calc_registry, context_registry):
        """Same-source roles share one timebase by construction
        (reference_source_id equality short-circuits timebases_aligned()
        instantly) -- confirmed indirectly: this resolves cleanly with no
        special per-role start_time setup beyond the shared fixture."""
        _add_context(context_registry, "ec-1", "ws-1", [_member("src-1", "ALPHA1_VA", PHASE_A), _member("src-1", "ALPHA1_IA", PHASE_A)])
        # (no requirement mixes Voltage+Current in this slice's known set,
        # so exercise two same-source single-phase resolutions instead)
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_RESOLVED


class TestBlankUnit:
    def test_blank_unit_resolves_but_not_numerically_ready(self, calc_registry, context_registry):
        source_registry = WorkspaceRegistry()
        blank_unit_source = _active_source("src-blank", "ws-1", [("ALPHA1_VA", VOLTAGE)], REF_START)
        blank_unit_source.metadata.analog_channels[0].unit = ""
        source_registry.add(blank_unit_source)
        _add_context(context_registry, "ec-1", "ws-1", [_member("src-blank", "ALPHA1_VA", PHASE_A)])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_RESOLVED
        assert result.numerically_ready is False


class TestCalculatedCandidate:
    def test_calculated_channel_resolves_by_its_own_metadata(self, source_registry, context_registry):
        calc_registry = CalculatedChannelRegistry()
        calc_registry.add(_calc("calc-va-est", "ws-1", "src-1", VOLTAGE))
        _add_context(context_registry, "ec-1", "ws-1", [
            EngineeringContextMember(
                channel_ref=ChannelRef(kind="calculated", calculated_channel_id="calc-va-est"),
                phase=PHASE_A, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED,
            )
        ])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == STATUS_RESOLVED
        assert result.resolved_roles["Va"].kind == "calculated"

    def test_raw_and_calculated_duplicate_is_ambiguous(self, source_registry, context_registry):
        calc_registry = CalculatedChannelRegistry()
        calc_registry.add(_calc("calc-va-est", "ws-1", "src-1", VOLTAGE))
        _add_context(context_registry, "ec-1", "ws-1", [
            _member("src-1", "ALPHA1_VA", PHASE_A),
            EngineeringContextMember(
                channel_ref=ChannelRef(kind="calculated", calculated_channel_id="calc-va-est"),
                phase=PHASE_A, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED,
            ),
        ])
        result = resolve_analysis_inputs(
            workspace_id="ws-1", engineering_context_id="ec-1", analysis_kind="phasor", mode="voltage_phase_a",
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert result.status == "ambiguous"
        assert len(result.ambiguous_roles["Va"]) == 2
