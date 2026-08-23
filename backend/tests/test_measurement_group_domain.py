"""Tests for app.domain.measurement_group (Slice 1 of DEC-050): pure
domain functions and the `MeasurementGroup` dataclass itself -- no
registry, no service, no I/O. See test_measurement_group_registry.py
and test_measurement_group_service.py for the layers built on top.
"""

from __future__ import annotations

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, FREQUENCY, POWER, ROCOF, UNDEFINED, VOLTAGE
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    KNOWN_GROUP_KINDS,
    KNOWN_GROUP_STATUSES,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    MeasurementGroup,
    channel_kind_compatible,
    channel_ref_is_group_eligible,
    channel_ref_matches_source,
    group_kind_valid,
    group_status_valid,
    kind_for_engineering_type,
)


class TestKindMapping:
    def test_voltage_engineering_type_maps_to_voltage_kind(self):
        assert kind_for_engineering_type(VOLTAGE) == KIND_VOLTAGE

    def test_current_engineering_type_maps_to_current_kind(self):
        assert kind_for_engineering_type(CURRENT) == KIND_CURRENT

    def test_power_frequency_rocof_undefined_have_no_group_kind_yet(self):
        # Section 4: PU grouping initially applies to Voltage/Current
        # only -- no speculative Power/Frequency/ROCOF group kind.
        for etype in (POWER, FREQUENCY, ROCOF, UNDEFINED):
            assert kind_for_engineering_type(etype) is None

    def test_channel_kind_compatible_matches_the_kind_mapping(self):
        assert channel_kind_compatible(KIND_VOLTAGE, VOLTAGE) is True
        assert channel_kind_compatible(KIND_VOLTAGE, CURRENT) is False
        assert channel_kind_compatible(KIND_CURRENT, CURRENT) is True
        assert channel_kind_compatible(KIND_CURRENT, VOLTAGE) is False
        assert channel_kind_compatible(KIND_VOLTAGE, POWER) is False
        assert channel_kind_compatible(KIND_CURRENT, UNDEFINED) is False


class TestGroupKindValidation:
    def test_known_kinds_are_exactly_voltage_and_current(self):
        assert set(KNOWN_GROUP_KINDS) == {KIND_VOLTAGE, KIND_CURRENT}

    def test_group_kind_valid_accepts_known_and_rejects_unknown(self):
        assert group_kind_valid(KIND_VOLTAGE) is True
        assert group_kind_valid(KIND_CURRENT) is True
        assert group_kind_valid("power") is False
        assert group_kind_valid("") is False
        assert group_kind_valid("Voltage") is False  # case-sensitive; "voltage" is canonical


class TestGroupStatusValidation:
    def test_known_statuses_are_the_four_lifecycle_states(self):
        assert set(KNOWN_GROUP_STATUSES) == {STATUS_SUGGESTED, STATUS_CONFIRMED, STATUS_NEEDS_REVIEW, STATUS_MANUAL}

    def test_group_status_valid_accepts_known_and_rejects_unknown(self):
        for status in KNOWN_GROUP_STATUSES:
            assert group_status_valid(status) is True
        assert group_status_valid("confirmed_by_accident") is False
        assert group_status_valid("") is False


class TestChannelRefEligibility:
    def test_source_channel_ref_is_eligible(self):
        ref = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
        assert channel_ref_is_group_eligible(ref) is True

    def test_calculated_channel_ref_is_not_eligible_in_slice_1(self):
        ref = ChannelRef(kind="calculated", calculated_channel_id="calc-1")
        assert channel_ref_is_group_eligible(ref) is False


class TestSameSourceInvariant:
    def test_matching_source_id_passes(self):
        ref = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
        assert channel_ref_matches_source("src-1", ref) is True

    def test_mismatched_source_id_fails(self):
        ref = ChannelRef(kind="source", source_id="src-2", channel_name="VA")
        assert channel_ref_matches_source("src-1", ref) is False


class TestMeasurementGroupDataclass:
    def test_default_status_is_manual(self):
        group = MeasurementGroup(
            id="mg-1", workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="NORTH BUS VOLTAGE"
        )
        assert group.status == STATUS_MANUAL
        assert group.channel_refs == []

    def test_channel_refs_default_is_not_a_shared_mutable_list(self):
        # dataclass `field(default_factory=list)` pitfall check -- two
        # independently constructed groups must never share one list.
        a = MeasurementGroup(id="mg-a", workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="A")
        b = MeasurementGroup(id="mg-b", workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="B")
        a.channel_refs.append(ChannelRef(kind="source", source_id="src-1", channel_name="VA"))
        assert b.channel_refs == []

    def test_display_name_is_not_identity(self):
        a = MeasurementGroup(id="mg-a", workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="SAME NAME")
        b = MeasurementGroup(id="mg-b", workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="SAME NAME")
        assert a.id != b.id
