"""Tests for app.services.measurement_group_service (Slice 1 of
DEC-050): the orchestration layer that resolves live workspace state
(does the source exist? what is this channel's own engineering_type?)
and translates domain validation into ImportServiceError subclasses,
sitting above MeasurementGroupRegistry -- see
test_measurement_group_registry.py for the pure-registry layer this
builds on, and test_measurement_group_domain.py for the pure functions
underneath both.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    channel_kind_compatible,
)
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.errors import (
    ChannelAlreadyGroupedError,
    ChannelNotFoundError,
    ChannelWrongEngineeringTypeError,
    ChannelWrongSourceError,
    DuplicateChannelReferenceError,
    InvalidMeasurementGroupKindError,
    InvalidMeasurementGroupStatusError,
    MeasurementGroupNotFoundError,
    SourceNotFoundError,
    UnsupportedChannelReferenceKindError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_service import (
    create_group,
    delete_group,
    generate_suggested_groups_for_source,
    get_group,
    list_groups_for_source,
    list_groups_for_workspace,
    remove_measurement_groups_for_source,
    update_group_membership,
    update_group_metadata,
)
from app.services.workspace_registry import WorkspaceRegistry


def _active_source(source_id: str, workspace_id: str, channel_names_and_types: list[tuple[str, str]]) -> ActiveSource:
    """Minimal ActiveSource fixture -- mirrors
    test_per_unit_registry.py's own helper of the same name (only
    `metadata.analog_channels` is actually consulted by this service's
    own validation)."""
    now = datetime.now(timezone.utc)
    analog_channels = [
        AnalogChannelSummary(name=name, index=i, unit="V" if etype == VOLTAGE else "A", engineering_type=etype)
        for i, (name, etype) in enumerate(channel_names_and_types)
    ]
    columns = {"time": [0.0, 0.25, 0.5, 0.75]}
    for name, _etype in channel_names_and_types:
        columns[name] = [0.0, 1.0, 2.0, 3.0]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=now,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=now, trigger_time=now,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


VA = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
VB = ChannelRef(kind="source", source_id="src-1", channel_name="VB")
IA = ChannelRef(kind="source", source_id="src-1", channel_name="IA")
OTHER_SOURCE_VA = ChannelRef(kind="source", source_id="src-2", channel_name="VA")
CALC_REF = ChannelRef(kind="calculated", calculated_channel_id="calc-1")


@pytest.fixture
def source_registry() -> WorkspaceRegistry:
    registry = WorkspaceRegistry()
    registry.add(_active_source("src-1", "ws-1", [("VA", VOLTAGE), ("VB", VOLTAGE), ("IA", CURRENT)]))
    registry.add(_active_source("src-2", "ws-1", [("VA", VOLTAGE)]))
    return registry


@pytest.fixture
def registry() -> MeasurementGroupRegistry:
    return MeasurementGroupRegistry()


class TestCreateGroupHappyPath:
    def test_create_voltage_group(self, registry, source_registry):
        group = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="NORTH BUS VOLTAGE",
            channel_refs=[VA, VB], registry=registry, source_registry=source_registry,
        )
        assert group.id.startswith("mg-")
        assert group.kind == KIND_VOLTAGE
        assert group.status == STATUS_MANUAL  # default
        assert registry.get("ws-1", group.id) is not None

    def test_create_current_group(self, registry, source_registry):
        group = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_CURRENT, display_name="IBT1 HV CURRENT",
            channel_refs=[IA], registry=registry, source_registry=source_registry,
        )
        assert group.kind == KIND_CURRENT

    def test_create_group_with_explicit_non_default_status(self, registry, source_registry):
        group = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[], status=STATUS_SUGGESTED, registry=registry, source_registry=source_registry,
        )
        assert group.status == STATUS_SUGGESTED

    def test_create_group_with_no_channels_is_allowed(self, registry, source_registry):
        # An empty group is a valid intermediate state (e.g. created,
        # membership added later via update_group_membership).
        group = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="EMPTY",
            channel_refs=[], registry=registry, source_registry=source_registry,
        )
        assert group.channel_refs == []


class TestCreateGroupValidation:
    def test_unknown_source_raises_source_not_found(self, registry, source_registry):
        with pytest.raises(SourceNotFoundError):
            create_group(
                workspace_id="ws-1", source_id="does-not-exist", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[], registry=registry, source_registry=source_registry,
            )

    def test_invalid_kind_raises(self, registry, source_registry):
        with pytest.raises(InvalidMeasurementGroupKindError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind="power", display_name="X",
                channel_refs=[], registry=registry, source_registry=source_registry,
            )

    def test_invalid_status_raises(self, registry, source_registry):
        with pytest.raises(InvalidMeasurementGroupStatusError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[], status="bogus", registry=registry, source_registry=source_registry,
            )

    def test_channel_from_a_different_source_is_rejected(self, registry, source_registry):
        with pytest.raises(ChannelWrongSourceError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[OTHER_SOURCE_VA], registry=registry, source_registry=source_registry,
            )

    def test_voltage_group_rejects_current_channel(self, registry, source_registry):
        with pytest.raises(ChannelWrongEngineeringTypeError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[IA], registry=registry, source_registry=source_registry,
            )

    def test_current_group_rejects_voltage_channel(self, registry, source_registry):
        with pytest.raises(ChannelWrongEngineeringTypeError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_CURRENT, display_name="X",
                channel_refs=[VA], registry=registry, source_registry=source_registry,
            )

    def test_voltage_group_accepts_voltage_channel(self, registry, source_registry):
        group = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[VA], registry=registry, source_registry=source_registry,
        )
        assert group.channel_refs == [VA]

    def test_current_group_accepts_current_channel(self, registry, source_registry):
        group = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_CURRENT, display_name="X",
            channel_refs=[IA], registry=registry, source_registry=source_registry,
        )
        assert group.channel_refs == [IA]

    def test_nonexistent_channel_name_raises_channel_not_found(self, registry, source_registry):
        ghost = ChannelRef(kind="source", source_id="src-1", channel_name="VZ")
        with pytest.raises(ChannelNotFoundError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[ghost], registry=registry, source_registry=source_registry,
            )

    def test_calculated_channel_ref_is_rejected_in_slice_1(self, registry, source_registry):
        with pytest.raises(UnsupportedChannelReferenceKindError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[CALC_REF], registry=registry, source_registry=source_registry,
            )

    def test_duplicate_channel_within_one_group_is_rejected(self, registry, source_registry):
        with pytest.raises(DuplicateChannelReferenceError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[VA, VA], registry=registry, source_registry=source_registry,
            )

    def test_channel_already_in_another_group_is_rejected(self, registry, source_registry):
        create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="FIRST",
            channel_refs=[VA], registry=registry, source_registry=source_registry,
        )
        with pytest.raises(ChannelAlreadyGroupedError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="SECOND",
                channel_refs=[VA], registry=registry, source_registry=source_registry,
            )

    def test_failed_create_leaves_no_partial_group_stored(self, registry, source_registry):
        with pytest.raises(ChannelWrongEngineeringTypeError):
            create_group(
                workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
                channel_refs=[VA, IA], registry=registry, source_registry=source_registry,
            )
        assert list_groups_for_workspace("ws-1", registry=registry) == []
        assert registry.group_for_channel("ws-1", VA) is None


class TestGetAndList:
    def test_get_group_raises_not_found_for_unknown_id(self, registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            get_group("ws-1", "does-not-exist", registry=registry)

    def test_get_group_returns_stored_group(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[], registry=registry, source_registry=source_registry,
        )
        assert get_group("ws-1", created.id, registry=registry).id == created.id

    def test_list_groups_for_source_is_scoped(self, registry, source_registry):
        create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="A",
            channel_refs=[], registry=registry, source_registry=source_registry,
        )
        create_group(
            workspace_id="ws-1", source_id="src-2", kind=KIND_VOLTAGE, display_name="B",
            channel_refs=[], registry=registry, source_registry=source_registry,
        )
        assert len(list_groups_for_source("ws-1", "src-1", registry=registry)) == 1
        assert len(list_groups_for_source("ws-1", "src-2", registry=registry)) == 1


class TestUpdateGroupMetadata:
    def test_rename_display_name(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="OLD",
            channel_refs=[], registry=registry, source_registry=source_registry,
        )
        updated = update_group_metadata(workspace_id="ws-1", measurement_group_id=created.id, display_name="NEW", registry=registry)
        assert updated.display_name == "NEW"
        assert updated.id == created.id  # identity survives a rename

    def test_valid_status_transition_accepted(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[], status=STATUS_SUGGESTED, registry=registry, source_registry=source_registry,
        )
        updated = update_group_metadata(workspace_id="ws-1", measurement_group_id=created.id, status=STATUS_CONFIRMED, registry=registry)
        assert updated.status == STATUS_CONFIRMED

    def test_invalid_status_rejected(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[], registry=registry, source_registry=source_registry,
        )
        with pytest.raises(InvalidMeasurementGroupStatusError):
            update_group_metadata(workspace_id="ws-1", measurement_group_id=created.id, status="bogus", registry=registry)
        # Rejected update must not have partially applied.
        assert get_group("ws-1", created.id, registry=registry).status == STATUS_MANUAL

    def test_needs_review_status_reachable_and_never_auto_promoted(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[], status=STATUS_NEEDS_REVIEW, registry=registry, source_registry=source_registry,
        )
        # Nothing in this slice ever changes status on its own.
        assert get_group("ws-1", created.id, registry=registry).status == STATUS_NEEDS_REVIEW

    def test_update_metadata_of_unknown_group_raises_not_found(self, registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            update_group_metadata(workspace_id="ws-1", measurement_group_id="does-not-exist", display_name="X", registry=registry)


class TestUpdateGroupMembership:
    def test_add_a_channel_to_an_existing_group(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[VA], registry=registry, source_registry=source_registry,
        )
        updated = update_group_membership(
            workspace_id="ws-1", measurement_group_id=created.id, channel_refs=[VA, VB],
            registry=registry, source_registry=source_registry,
        )
        assert updated.channel_refs == [VA, VB]

    def test_remove_a_channel_releases_it_for_other_groups(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[VA, VB], registry=registry, source_registry=source_registry,
        )
        update_group_membership(
            workspace_id="ws-1", measurement_group_id=created.id, channel_refs=[VA],
            registry=registry, source_registry=source_registry,
        )
        # VB is now free -- a second group may claim it.
        other = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="Y",
            channel_refs=[VB], registry=registry, source_registry=source_registry,
        )
        assert other.channel_refs == [VB]

    def test_membership_update_still_enforces_kind_compatibility(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[VA], registry=registry, source_registry=source_registry,
        )
        with pytest.raises(ChannelWrongEngineeringTypeError):
            update_group_membership(
                workspace_id="ws-1", measurement_group_id=created.id, channel_refs=[VA, IA],
                registry=registry, source_registry=source_registry,
            )

    def test_membership_update_of_unknown_group_raises_not_found(self, registry, source_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            update_group_membership(
                workspace_id="ws-1", measurement_group_id="does-not-exist", channel_refs=[],
                registry=registry, source_registry=source_registry,
            )


class TestDeleteGroup:
    def test_delete_returns_true_and_removes_it(self, registry, source_registry):
        created = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="X",
            channel_refs=[VA], registry=registry, source_registry=source_registry,
        )
        assert delete_group("ws-1", created.id, registry=registry) is True
        assert registry.get("ws-1", created.id) is None
        assert registry.group_for_channel("ws-1", VA) is None

    def test_delete_is_idempotent(self, registry):
        assert delete_group("ws-1", "does-not-exist", registry=registry) is False


class TestRemoveMeasurementGroupsForSource:
    def test_removes_every_group_owned_by_that_source_only(self, registry, source_registry):
        create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="A",
            channel_refs=[VA], registry=registry, source_registry=source_registry,
        )
        create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_CURRENT, display_name="B",
            channel_refs=[IA], registry=registry, source_registry=source_registry,
        )
        create_group(
            workspace_id="ws-1", source_id="src-2", kind=KIND_VOLTAGE, display_name="C",
            channel_refs=[OTHER_SOURCE_VA], registry=registry, source_registry=source_registry,
        )
        removed = remove_measurement_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry)
        assert len(removed) == 2
        assert list_groups_for_source("ws-1", "src-1", registry=registry) == []
        assert len(list_groups_for_source("ws-1", "src-2", registry=registry)) == 1
        assert registry.group_for_channel("ws-1", VA) is None
        assert registry.group_for_channel("ws-1", IA) is None
        assert registry.group_for_channel("ws-1", OTHER_SOURCE_VA) == list_groups_for_source("ws-1", "src-2", registry=registry)[0].id

    def test_idempotent_for_a_source_with_no_groups(self, registry):
        assert remove_measurement_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry) == []


@pytest.fixture
def phase_source_registry() -> WorkspaceRegistry:
    """A source whose channel names carry realistic deterministic-
    grouping evidence: a clean voltage triplet, a clean current triplet,
    a spare channel with no recognizable phase suffix, and two channels
    that deliberately conflict with each other (Slice 2's own
    TestGenerateSuggestedGroupsForSource below)."""
    ws_registry = WorkspaceRegistry()
    ws_registry.add(
        _active_source(
            "src-1", "ws-1",
            [
                ("NORTH BUS VR", VOLTAGE), ("NORTH BUS VY", VOLTAGE), ("NORTH BUS VB", VOLTAGE),
                ("IBT1 HV IR", CURRENT), ("IBT1 HV IY", CURRENT), ("IBT1 HV IB", CURRENT),
                ("SPARE1", VOLTAGE),
                ("BUS1 VR", VOLTAGE), ("BUS1 VRY", VOLTAGE),  # mixed representation -> needs_review
            ],
        )
    )
    return ws_registry


class TestGenerateSuggestedGroupsForSource:
    def test_creates_a_suggested_group_per_clean_cluster(self, registry, phase_source_registry):
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        by_kind = {g.kind: g for g in created if g.status == STATUS_SUGGESTED and len(g.channel_refs) == 3}
        assert KIND_VOLTAGE in by_kind
        assert KIND_CURRENT in by_kind
        assert {ref.channel_name for ref in by_kind[KIND_VOLTAGE].channel_refs} == {"NORTH BUS VR", "NORTH BUS VY", "NORTH BUS VB"}
        assert {ref.channel_name for ref in by_kind[KIND_CURRENT].channel_refs} == {"IBT1 HV IR", "IBT1 HV IY", "IBT1 HV IB"}

    def test_created_groups_are_persisted_and_retrievable(self, registry, phase_source_registry):
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        for group in created:
            assert get_group("ws-1", group.id, registry=registry).id == group.id

    def test_ambiguous_cluster_is_created_as_needs_review_not_suggested(self, registry, phase_source_registry):
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        needs_review = [g for g in created if g.status == STATUS_NEEDS_REVIEW]
        assert len(needs_review) == 1
        assert {ref.channel_name for ref in needs_review[0].channel_refs} == {"BUS1 VR", "BUS1 VRY"}

    def test_nothing_ever_created_as_confirmed(self, registry, phase_source_registry):
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        assert all(g.status != STATUS_CONFIRMED for g in created)

    def test_channel_with_no_phase_suffix_never_gets_grouped(self, registry, phase_source_registry):
        generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        spare_ref = ChannelRef(kind="source", source_id="src-1", channel_name="SPARE1")
        assert registry.group_for_channel("ws-1", spare_ref) is None

    def test_unknown_source_raises_source_not_found(self, registry, phase_source_registry):
        with pytest.raises(SourceNotFoundError):
            generate_suggested_groups_for_source(workspace_id="ws-1", source_id="does-not-exist", registry=registry, source_registry=phase_source_registry)

    def test_rerunning_on_an_unchanged_source_creates_nothing_new(self, registry, phase_source_registry):
        first = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        assert len(first) > 0
        second = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        assert second == []
        # Every originally created group survives untouched.
        for group in first:
            assert get_group("ws-1", group.id, registry=registry).status == group.status

    def test_regeneration_never_touches_an_existing_manual_group(self, registry, phase_source_registry):
        # An engineer manually grouped the voltage triplet differently
        # (e.g. only two of the three phases) BEFORE detection ever ran.
        manual = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="MY OWN GROUP", status=STATUS_MANUAL,
            channel_refs=[ChannelRef(kind="source", source_id="src-1", channel_name="NORTH BUS VR")],
            registry=registry, source_registry=phase_source_registry,
        )
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        # The manual group's own membership must be completely untouched.
        assert get_group("ws-1", manual.id, registry=registry).channel_refs == manual.channel_refs
        assert get_group("ws-1", manual.id, registry=registry).status == STATUS_MANUAL
        # The whole NORTH BUS VOLTAGE cluster is skipped entirely (one of
        # its channels is already claimed) -- never partially re-grouped.
        voltage_created = [g for g in created if g.kind == KIND_VOLTAGE]
        assert all("NORTH BUS VY" not in {ref.channel_name for ref in g.channel_refs} for g in voltage_created)

    def test_regeneration_never_touches_a_previously_confirmed_group(self, registry, phase_source_registry):
        suggested = create_group(
            workspace_id="ws-1", source_id="src-1", kind=KIND_CURRENT, display_name="IBT1 HV CURRENT", status=STATUS_SUGGESTED,
            channel_refs=[
                ChannelRef(kind="source", source_id="src-1", channel_name="IBT1 HV IR"),
                ChannelRef(kind="source", source_id="src-1", channel_name="IBT1 HV IY"),
                ChannelRef(kind="source", source_id="src-1", channel_name="IBT1 HV IB"),
            ],
            registry=registry, source_registry=phase_source_registry,
        )
        update_group_metadata(workspace_id="ws-1", measurement_group_id=suggested.id, status=STATUS_CONFIRMED, registry=registry)
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        assert get_group("ws-1", suggested.id, registry=registry).status == STATUS_CONFIRMED
        assert all(g.kind != KIND_CURRENT for g in created)

    def test_generation_goes_through_create_group_validation(self, registry, phase_source_registry):
        # A tamper check: if this function ever bypassed create_group()
        # and called registry.add() directly, a detected cluster
        # spanning channels from the wrong engineering type would slip
        # through unvalidated. Since detect_measurement_groups() itself
        # only ever proposes kind-homogeneous clusters, the strongest
        # available proof that validation still runs is that every
        # created group's own channel_refs are all real channels on the
        # correct source with the correct engineering type.
        created = generate_suggested_groups_for_source(workspace_id="ws-1", source_id="src-1", registry=registry, source_registry=phase_source_registry)
        active = phase_source_registry.get("ws-1", "src-1")
        by_name = {ch.name: ch.engineering_type for ch in active.metadata.analog_channels}
        for group in created:
            for ref in group.channel_refs:
                assert ref.source_id == "src-1"
                assert channel_kind_compatible(group.kind, by_name[ref.channel_name])
