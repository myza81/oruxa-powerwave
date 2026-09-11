"""Tests for app.services.engineering_context_service (Analysis
Guardrail Slice 1): the orchestration layer that resolves live workspace
state and translates domain validation into ImportServiceError
subclasses, sitting above EngineeringContextRegistry. Mirrors
test_measurement_group_service.py's own coverage shape.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import CalculatedChannel, ChannelRef
from app.domain.channel_classification import CURRENT, POWER, VOLTAGE
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.engineering_context import EngineeringContextMember
from app.domain.measurement_group import STATUS_CONFIRMED, STATUS_MANUAL, STATUS_NEEDS_REVIEW, STATUS_SUGGESTED
from app.domain.metadata import RecordingMetadata
from app.domain.phase_identity import (
    PHASE_A,
    PHASE_B,
    PHASE_C,
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_ENGINEER_CONFIRMED,
    PHASE_SOURCE_STRUCTURED_METADATA,
    PHASE_UNKNOWN,
)
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.engineering_context_service import (
    create_context,
    delete_context,
    generate_suggested_contexts_for_source,
    get_context,
    list_contexts_for_workspace,
    prune_engineering_contexts_for_source,
    update_context_membership,
    update_context_metadata,
    update_member_phase,
)
from app.services.errors import (
    ChannelAlreadyInContextError,
    EngineeringContextChannelNotFoundError,
    EngineeringContextNotFoundError,
    InvalidEngineeringContextStatusError,
    InvalidPhaseError,
    SourceNotFoundError,
)
from app.services.workspace_registry import WorkspaceRegistry


def _active_source(source_id: str, workspace_id: str, channels: list[tuple[str, str]], phases: dict[str, str] | None = None) -> ActiveSource:
    now = datetime.now(timezone.utc)
    phases = phases or {}
    analog_channels = [
        AnalogChannelSummary(
            name=name, index=i, unit="V" if etype == VOLTAGE else "A", engineering_type=etype,
            phase=phases.get(name),
        )
        for i, (name, etype) in enumerate(channels)
    ]
    columns = {"time": [0.0, 0.25, 0.5, 0.75]}
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


def _calc(calc_id: str, workspace_id: str = "ws-1") -> CalculatedChannel:
    n = 4
    return CalculatedChannel(
        id=calc_id, workspace_id=workspace_id, name=calc_id, unit="V", operation="reverse_polarity",
        inputs=[ChannelRef(kind="source", source_id="src-1", channel_name="ALPHA1_VA")],
        parameters={}, dependency_ids=[], reference_source_id="src-1",
        time=np.arange(n, dtype=np.float64), values=np.ones(n, dtype=np.float64),
        created_at=datetime.now(timezone.utc),
    )


VA = ChannelRef(kind="source", source_id="src-1", channel_name="ALPHA1_VA")
IA = ChannelRef(kind="source", source_id="src-1", channel_name="ALPHA1_IA")
OTHER_SOURCE_VA = ChannelRef(kind="source", source_id="src-2", channel_name="BRAVO1_VA")
CALC_REF = ChannelRef(kind="calculated", calculated_channel_id="calc-1")


@pytest.fixture
def source_registry() -> WorkspaceRegistry:
    registry = WorkspaceRegistry()
    registry.add(_active_source("src-1", "ws-1", [("ALPHA1_VA", VOLTAGE), ("ALPHA1_IA", CURRENT), ("ALPHA1_MW", POWER)]))
    registry.add(_active_source("src-2", "ws-1", [("BRAVO1_VA", VOLTAGE)]))
    return registry


@pytest.fixture
def calc_registry() -> CalculatedChannelRegistry:
    registry = CalculatedChannelRegistry()
    registry.add(_calc("calc-1"))
    return registry


@pytest.fixture
def registry() -> EngineeringContextRegistry:
    return EngineeringContextRegistry()


class TestCreateContextHappyPath:
    def test_create_with_source_channels(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[
                EngineeringContextMember(channel_ref=VA, phase=PHASE_A, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED),
                EngineeringContextMember(channel_ref=IA, phase=PHASE_A, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED),
            ],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert context.id.startswith("ec-")
        assert context.status == STATUS_MANUAL
        assert len(context.members) == 2

    def test_create_with_calculated_channel_member_is_allowed(self, registry, source_registry, calc_registry):
        """Owner instruction: a calculated ChannelRef is an acceptable
        Engineering Context member (unlike Measurement Group Slice 1's
        own source-only restriction)."""
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=CALC_REF, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert len(context.members) == 1

    def test_create_spans_multiple_sources(self, registry, source_registry, calc_registry):
        """The owner's own explicit correction: a context is workspace-
        scoped and may contain ChannelRefs from multiple sources."""
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[
                EngineeringContextMember(channel_ref=VA, phase=PHASE_A),
                EngineeringContextMember(channel_ref=OTHER_SOURCE_VA, phase=PHASE_A),
            ],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert {m.channel_ref.source_id for m in context.members} == {"src-1", "src-2"}

    def test_create_single_phase_context_is_valid(self, registry, source_registry, calc_registry):
        """No blanket three-phase completeness requirement."""
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert len(context.members) == 1

    def test_create_does_not_restrict_engineering_type(self, registry, source_registry, calc_registry):
        """Unlike a Measurement Group, an Engineering Context is not
        kind-restricted -- even a Power channel may be a member."""
        power_ref = ChannelRef(kind="source", source_id="src-1", channel_name="ALPHA1_MW")
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=power_ref, phase=PHASE_UNKNOWN)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert len(context.members) == 1


class TestCreateContextValidationErrors:
    def test_unknown_source_channel_rejected(self, registry, source_registry, calc_registry):
        bogus = ChannelRef(kind="source", source_id="src-1", channel_name="NOT_A_CHANNEL")
        with pytest.raises(EngineeringContextChannelNotFoundError):
            create_context(
                workspace_id="ws-1", display_name="Alpha 1",
                members=[EngineeringContextMember(channel_ref=bogus, phase=PHASE_A)],
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_unknown_source_id_rejected(self, registry, source_registry, calc_registry):
        bogus = ChannelRef(kind="source", source_id="src-missing", channel_name="VA")
        with pytest.raises(EngineeringContextChannelNotFoundError):
            create_context(
                workspace_id="ws-1", display_name="Alpha 1",
                members=[EngineeringContextMember(channel_ref=bogus, phase=PHASE_A)],
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_unknown_calculated_channel_rejected(self, registry, source_registry, calc_registry):
        bogus = ChannelRef(kind="calculated", calculated_channel_id="calc-missing")
        with pytest.raises(EngineeringContextChannelNotFoundError):
            create_context(
                workspace_id="ws-1", display_name="Alpha 1",
                members=[EngineeringContextMember(channel_ref=bogus, phase=PHASE_A)],
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_invalid_phase_rejected(self, registry, source_registry, calc_registry):
        with pytest.raises(InvalidPhaseError):
            create_context(
                workspace_id="ws-1", display_name="Alpha 1",
                members=[EngineeringContextMember(channel_ref=VA, phase="Z")],
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_invalid_status_rejected(self, registry, source_registry, calc_registry):
        with pytest.raises(InvalidEngineeringContextStatusError):
            create_context(
                workspace_id="ws-1", display_name="Alpha 1", members=[], status="bogus",
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_channel_already_in_another_context_rejected(self, registry, source_registry, calc_registry):
        create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        with pytest.raises(ChannelAlreadyInContextError):
            create_context(
                workspace_id="ws-1", display_name="Alpha 1 Duplicate",
                members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )


class TestGetListDelete:
    def test_get_missing_raises(self, registry):
        with pytest.raises(EngineeringContextNotFoundError):
            get_context("ws-1", "ec-missing", registry=registry)

    def test_list_for_workspace(self, registry, source_registry, calc_registry):
        create_context(
            workspace_id="ws-1", display_name="Alpha 1", members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        contexts = list_contexts_for_workspace("ws-1", registry=registry)
        assert len(contexts) == 1

    def test_delete_is_idempotent(self, registry):
        assert delete_context("ws-1", "ec-missing", registry=registry) is False


class TestUpdateMetadata:
    def test_promotes_suggested_to_confirmed(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1", members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            status=STATUS_SUGGESTED,
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        updated = update_context_metadata(
            workspace_id="ws-1", engineering_context_id=context.id, registry=registry, status=STATUS_CONFIRMED,
        )
        assert updated.status == STATUS_CONFIRMED

    def test_rename_does_not_affect_id(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1", members=[],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        updated = update_context_metadata(
            workspace_id="ws-1", engineering_context_id=context.id, registry=registry, display_name="Renamed Bay",
        )
        assert updated.id == context.id
        assert updated.display_name == "Renamed Bay"


class TestUpdateMembership:
    def test_full_replace_including_adding_a_second_source(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1", members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        updated = update_context_membership(
            workspace_id="ws-1", engineering_context_id=context.id,
            members=[
                EngineeringContextMember(channel_ref=VA, phase=PHASE_A),
                EngineeringContextMember(channel_ref=IA, phase=PHASE_A),
                EngineeringContextMember(channel_ref=OTHER_SOURCE_VA, phase=PHASE_A),
            ],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert len(updated.members) == 3
        assert {m.channel_ref.source_id for m in updated.members} == {"src-1", "src-2"}


class TestUpdateMemberPhase:
    def test_corrects_one_members_phase_as_engineer_confirmed(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_UNKNOWN, phase_source=PHASE_SOURCE_DETECTED_FROM_NAME)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        updated = update_member_phase(
            workspace_id="ws-1", engineering_context_id=context.id, channel_ref=VA, phase=PHASE_A,
            registry=registry,
        )
        member = next(m for m in updated.members if m.channel_ref == VA)
        assert member.phase == PHASE_A
        assert member.phase_source == PHASE_SOURCE_ENGINEER_CONFIRMED

    def test_channel_not_a_member_raises(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1", members=[],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        with pytest.raises(EngineeringContextChannelNotFoundError):
            update_member_phase(
                workspace_id="ws-1", engineering_context_id=context.id, channel_ref=VA, phase=PHASE_A, registry=registry,
            )


class TestPruneForSource:
    def test_removes_only_affected_members_keeps_context_alive(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[
                EngineeringContextMember(channel_ref=VA, phase=PHASE_A),
                EngineeringContextMember(channel_ref=OTHER_SOURCE_VA, phase=PHASE_A),
            ],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        affected = prune_engineering_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry, calculated_channel_registry=calc_registry,
        )
        assert affected == [context.id]
        remaining = get_context("ws-1", context.id, registry=registry)
        assert {m.channel_ref.channel_name for m in remaining.members} == {"BRAVO1_VA"}

    def test_removes_whole_context_when_no_members_remain(self, registry, source_registry, calc_registry):
        context = create_context(
            workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        prune_engineering_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry, calculated_channel_registry=calc_registry,
        )
        with pytest.raises(EngineeringContextNotFoundError):
            get_context("ws-1", context.id, registry=registry)

    def test_idempotent_for_unaffected_source(self, registry, source_registry, calc_registry):
        create_context(
            workspace_id="ws-1", display_name="Alpha 1", members=[EngineeringContextMember(channel_ref=VA, phase=PHASE_A)],
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        affected = prune_engineering_contexts_for_source(
            workspace_id="ws-1", source_id="src-2", registry=registry, calculated_channel_registry=calc_registry,
        )
        assert affected == []


class TestGenerateSuggestedContextsForSource:
    def test_creates_suggested_context_from_source(self, registry, source_registry, calc_registry):
        created = generate_suggested_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert len(created) == 1
        context = created[0]
        assert context.status == STATUS_SUGGESTED
        assert {m.channel_ref.channel_name for m in context.members} == {"ALPHA1_VA", "ALPHA1_IA"}

    def test_creates_suggested_context_from_bare_roles(self, registry, source_registry, calc_registry):
        source_registry.add(
            _active_source(
                "src-bare", "ws-1",
                [
                    ("VA", VOLTAGE), ("VB", VOLTAGE), ("VC", VOLTAGE),
                    ("IA", CURRENT), ("IB", CURRENT), ("IC", CURRENT),
                ],
                phases={"VA": "A", "VB": "B", "VC": "C", "IA": "A", "IB": "B", "IC": "C"},
            )
        )

        created = generate_suggested_contexts_for_source(
            workspace_id="ws-1", source_id="src-bare", registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )

        assert len(created) == 1
        context = created[0]
        assert context.display_name == "Default Context"
        assert context.status == STATUS_SUGGESTED
        phases = {m.channel_ref.channel_name: m.phase for m in context.members}
        assert phases == {"VA": PHASE_A, "VB": PHASE_B, "VC": PHASE_C, "IA": PHASE_A, "IB": PHASE_B, "IC": PHASE_C}

    def test_unknown_source_raises(self, registry, source_registry, calc_registry):
        with pytest.raises(SourceNotFoundError):
            generate_suggested_contexts_for_source(
                workspace_id="ws-1", source_id="src-missing", registry=registry,
                source_registry=source_registry, calculated_channel_registry=calc_registry,
            )

    def test_idempotent_second_run_finds_nothing_new(self, registry, source_registry, calc_registry):
        generate_suggested_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        second = generate_suggested_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        assert second == []

    def test_rerunning_detection_never_overwrites_an_engineer_confirmed_phase(self, registry, source_registry, calc_registry):
        """The owner's own explicit guardrail: re-running detection must
        never silently overwrite a confirmed phase assignment. Achieved
        here structurally -- the additive-only/idempotent contract means
        a channel already claimed by an existing context is never
        touched by a second detection run at all."""
        created = generate_suggested_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        context = created[0]
        update_member_phase(
            workspace_id="ws-1", engineering_context_id=context.id, channel_ref=VA, phase=PHASE_B,
            registry=registry,
        )
        generate_suggested_contexts_for_source(
            workspace_id="ws-1", source_id="src-1", registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
        unchanged = get_context("ws-1", context.id, registry=registry)
        member = next(m for m in unchanged.members if m.channel_ref == VA)
        assert member.phase == PHASE_B
        assert member.phase_source == PHASE_SOURCE_ENGINEER_CONFIRMED
