"""Tests for app.services.per_unit_coverage_service (Per-Unit Settings
hierarchy, Slice 2) -- the source-level coverage read model that answers
"how much of this recording is covered by Measurement Groups, how much
by Source Default, and how much needs configuration?" without
re-implementing DEC-051's own precedence rule.

Uses the same minimal `ActiveSource` construction pattern
`tests/test_per_unit_registry.py`'s own `_active_source()` helper
established (only `metadata.analog_channels`/`digital_channels` are
actually consulted; `record` just needs to satisfy DisturbanceRecord's
real constructor) and the same `_group()` helper shape
`tests/test_group_aware_per_unit_service.py` already uses for
Measurement Group fixtures.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import (
    CURRENT,
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    FREQUENCY,
    VOLTAGE,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, STATUS_SUGGESTED, MeasurementGroup
from app.domain.metadata import RecordingMetadata
from app.domain.per_unit import PerUnitBaseProfile
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import set_current_base_equipment_rating
from app.services.errors import SourceNotFoundError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_coverage_service import (
    CATEGORY_MEASUREMENT_GROUP,
    CATEGORY_NEEDS_CONFIGURATION,
    CATEGORY_SOURCE_DEFAULT,
    build_per_unit_coverage_summary,
)
from app.services.per_unit_registry import PerUnitRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base
from app.services.workspace_registry import WorkspaceRegistry

WORKSPACE = "ws-1"
SOURCE = "src-1"


def _channel(name: str, engineering_type: str, engineering_quantity: str = "Undefined") -> AnalogChannelSummary:
    return AnalogChannelSummary(
        name=name, index=0, unit="V" if engineering_type == VOLTAGE else "A",
        engineering_type=engineering_type, engineering_quantity=engineering_quantity,
    )


def _active_source(analog_channels: list[AnalogChannelSummary], digital_channels: list[DigitalChannelSummary] | None = None) -> ActiveSource:
    now = datetime.now(timezone.utc)
    digital_channels = digital_channels or []
    columns = {"time": [0.0, 0.25, 0.5, 0.75]}
    for channel in analog_channels:
        columns[channel.name] = [0.0, 1.0, 2.0, 3.0]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{SOURCE}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )
    metadata = SourceMetadata(
        source_id=SOURCE, workspace_id=WORKSPACE, provider_type="COMTRADE",
        original_filenames=(f"{SOURCE}.cfg",), created_at=now,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=now, trigger_time=now,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,),
        analog_channels=analog_channels, digital_channels=digital_channels,
    )
    return ActiveSource(metadata=metadata, record=record)


def _group(group_id: str, kind: str, channel_names: tuple[str, ...], status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id=WORKSPACE, source_id=SOURCE, kind=kind, display_name=group_id.upper(),
        channel_refs=[ChannelRef(kind="source", source_id=SOURCE, channel_name=n) for n in channel_names],
        status=status,
    )


@pytest.fixture
def source_registry() -> WorkspaceRegistry:
    return WorkspaceRegistry()


@pytest.fixture
def per_unit_registry() -> PerUnitRegistry:
    return PerUnitRegistry()


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    return MeasurementGroupRegistry()


@pytest.fixture
def voltage_config_registry() -> VoltageGroupConfigRegistry:
    return VoltageGroupConfigRegistry()


@pytest.fixture
def current_config_registry() -> CurrentGroupConfigRegistry:
    return CurrentGroupConfigRegistry()


def _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry):
    return build_per_unit_coverage_summary(
        workspace_id=WORKSPACE, source_id=SOURCE,
        source_registry=source_registry, per_unit_registry=per_unit_registry,
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )


class TestAllMeasurementGroups:
    """Scenario 1: every applicable channel resolved by Measurement Groups."""

    def test_fully_grouped_and_configured_source(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        source_registry.add(_active_source(channels))
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 3
        assert summary.measurement_group_count == 3
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 0


class TestAllSourceDefault:
    """Scenario 2: every applicable channel resolved by Source Default."""

    def test_fully_ungrouped_but_configured_source(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        source_registry.add(_active_source(channels))
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=275.0,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 3
        assert summary.measurement_group_count == 0
        assert summary.source_default_count == 3
        assert summary.needs_configuration_count == 0


class TestMixedSource:
    """Scenario 3: mixed grouped + ungrouped source -- the main Slice 2
    use case."""

    def test_mixed_grouped_and_ungrouped_channels(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [
            _channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE),  # grouped, configured
            _channel("V132", VOLTAGE),  # ungrouped, uses Source Default
        ]
        source_registry.add(_active_source(channels))
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=132.0,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 4
        assert summary.measurement_group_count == 3
        assert summary.source_default_count == 1
        assert summary.needs_configuration_count == 0


class TestGroupedButIncomplete:
    """Scenario 4 (critical requirement): a grouped channel whose group
    base is incomplete must count under Needs configuration, and must
    NEVER silently fall back to Source Default even when a usable
    Source Default configuration also exists on the same source."""

    def test_confirmed_group_with_no_base_set_is_needs_configuration_not_source_default(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        source_registry.add(_active_source(channels))
        # Confirmed group, but nominal_voltage_ll_kv was never set.
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB"), status=STATUS_CONFIRMED))
        # A fully usable Source Default ALSO exists on this source -- must
        # be ignored for these grouped channels (DEC-051).
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=275.0,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 3
        assert summary.measurement_group_count == 0
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 3

    def test_suggested_group_status_is_also_needs_configuration(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        source_registry.add(_active_source(channels))
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB"), status=STATUS_SUGGESTED))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        # A suggested (not yet confirmed) group is not authoritative for
        # PU purposes even with a fully valid configuration attached.
        assert summary.measurement_group_count == 0
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 3


class TestUngroupedWithoutDefault:
    """Scenario 5: an ungrouped channel with no usable Source Default."""

    def test_no_profile_at_all(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE)]
        source_registry.add(_active_source(channels))

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 1
        assert summary.measurement_group_count == 0
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 1

    def test_profile_exists_but_voltage_base_not_set(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE)]
        source_registry.add(_active_source(channels))
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=None,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.needs_configuration_count == 1
        assert summary.source_default_count == 0


class TestGroupedChannelNeverCountedAsSourceDefault:
    """Scenario 6: a grouped-and-configured channel must never ALSO be
    counted under Source Default, even when a Source Default
    configuration exists on the same source."""

    def test_grouped_configured_channel_excluded_from_source_default_even_with_a_valid_default(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        source_registry.add(_active_source(channels))
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=999.0,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.measurement_group_count == 3
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 0


class TestAngleQuantitiesExcluded:
    """Scenario 7: Voltage/Current Angle channels are not_applicable and
    must be excluded from every count, even if grouped."""

    def test_voltage_angle_excluded_even_when_ungrouped(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [
            _channel("VR", VOLTAGE),
            _channel("VR_ANGLE", VOLTAGE, engineering_quantity=ENGINEERING_QUANTITY_VOLTAGE_ANGLE),
        ]
        source_registry.add(_active_source(channels))
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=275.0,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 1
        assert summary.source_default_count == 1

    def test_current_angle_excluded_even_when_grouped(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("IR_ANGLE", CURRENT, engineering_quantity=ENGINEERING_QUANTITY_CURRENT_ANGLE)]
        source_registry.add(_active_source(channels))
        # Group membership alone does not exclude an Angle channel
        # (channel_kind_compatible() only checks broad engineering_type)
        # -- the coverage service must still exclude it via the same
        # DEC-078 guardrail waveform_service._resolve_effective_per_unit()
        # applies.
        group_registry.add(_group("mg-i", KIND_CURRENT, ("IR_ANGLE",)))
        set_current_base_equipment_rating(
            workspace_id=WORKSPACE, measurement_group_id="mg-i", equipment_rating_mva=100.0,
            linked_voltage_group_id=None, manual_voltage_base_kv=132.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 0
        assert summary.measurement_group_count == 0
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 0

    def test_undefined_and_frequency_channels_excluded(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("F1", FREQUENCY)]
        source_registry.add(_active_source(channels))

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 0


class TestDigitalChannelsExcluded:
    """Scenario 8: digital channels must never be counted."""

    def test_digital_channels_never_contribute_to_coverage(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("VR", VOLTAGE)]
        digital = [DigitalChannelSummary(name="TRIP", index=0)]
        source_registry.add(_active_source(channels, digital_channels=digital))
        per_unit_registry.upsert(
            PerUnitBaseProfile(
                source_id=SOURCE, workspace_id=WORKSPACE, voltage_base_value=275.0,
                voltage_reference_mode="auto", voltage_reference_override=None,
                current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
            )
        )

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 1


class TestNoApplicableChannels:
    """Scenario 9: a source with no Voltage/Current channels at all."""

    def test_no_applicable_channels_returns_all_zero_counts(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        channels = [_channel("F1", FREQUENCY)]
        source_registry.add(_active_source(channels))

        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)

        assert summary.applicable_channel_count == 0
        assert summary.measurement_group_count == 0
        assert summary.source_default_count == 0
        assert summary.needs_configuration_count == 0


class TestCountsSumCorrectly:
    """Scenario 10: applicable_channel_count always equals the sum of
    the three category counts, across every fixture above."""

    @pytest.mark.parametrize(
        "channels_factory",
        [
            lambda: [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE)],
            lambda: [_channel("VR", VOLTAGE), _channel("IR", CURRENT), _channel("F1", FREQUENCY)],
            lambda: [],
        ],
    )
    def test_sum_invariant_holds(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry, channels_factory
    ):
        source_registry.add(_active_source(channels_factory()))
        summary = _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)
        assert summary.applicable_channel_count == (
            summary.measurement_group_count + summary.source_default_count + summary.needs_configuration_count
        )


class TestSourceNotFound:
    def test_unknown_source_raises_source_not_found(
        self, source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry
    ):
        with pytest.raises(SourceNotFoundError):
            _build(source_registry, per_unit_registry, group_registry, voltage_config_registry, current_config_registry)


class TestCategoryConstants:
    """Guards against a silent typo in the category labels used above."""

    def test_categories_are_distinct_strings(self):
        assert len({CATEGORY_MEASUREMENT_GROUP, CATEGORY_SOURCE_DEFAULT, CATEGORY_NEEDS_CONFIGURATION}) == 3
