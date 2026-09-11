"""Tests for app.domain.engineering_context (Analysis Guardrail Slice 1):
the pure identity/membership/status dataclasses -- no registry, no
service, no I/O.
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_context import (
    EngineeringContext,
    EngineeringContextMember,
    KNOWN_CONTEXT_STATUSES,
    context_channel_refs,
    context_status_valid,
    member_for_channel_ref,
    validate_member_fields,
)
from app.domain.measurement_group import STATUS_CONFIRMED, STATUS_MANUAL, STATUS_NEEDS_REVIEW, STATUS_SUGGESTED
from app.domain.phase_identity import PHASE_A, PHASE_SOURCE_ENGINEER_CONFIRMED, PHASE_SOURCE_UNKNOWN, PHASE_UNKNOWN


def _ref(name: str, source_id: str = "src-1") -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name=name)


class TestContextStatusVocabularyReused:
    def test_reuses_measurement_group_status_vocabulary(self):
        """Owner instruction: reuse the existing Measurement Group status
        vocabulary rather than inventing a new one."""
        assert set(KNOWN_CONTEXT_STATUSES) == {STATUS_SUGGESTED, STATUS_CONFIRMED, STATUS_NEEDS_REVIEW, STATUS_MANUAL}

    def test_status_validity(self):
        assert context_status_valid(STATUS_MANUAL)
        assert context_status_valid(STATUS_SUGGESTED)
        assert not context_status_valid("bogus")


class TestEngineeringContextMemberDefaults:
    def test_default_phase_is_unknown_never_guessed(self):
        member = EngineeringContextMember(channel_ref=_ref("ALPHA1_VA"))
        assert member.phase == PHASE_UNKNOWN
        assert member.phase_source == PHASE_SOURCE_UNKNOWN
        assert member.original_phase_label is None

    def test_phase_is_not_a_field_on_channel_ref(self):
        """Owner instruction: phase must never be added directly to
        ChannelRef -- confirms ChannelRef's own shape is untouched."""
        ref = _ref("ALPHA1_VA")
        assert not hasattr(ref, "phase")


class TestEngineeringContextNoSourceScoping:
    def test_context_has_no_source_id_field(self):
        """Owner's explicit correction to the original audit: a context
        must NOT be source-scoped."""
        context = EngineeringContext(id="ec-1", workspace_id="ws-1", display_name="Alpha 1")
        assert not hasattr(context, "source_id")

    def test_context_can_hold_members_from_multiple_sources(self):
        context = EngineeringContext(
            id="ec-1",
            workspace_id="ws-1",
            display_name="Alpha 1",
            members=[
                EngineeringContextMember(channel_ref=_ref("VA", source_id="src-A"), phase=PHASE_A),
                EngineeringContextMember(channel_ref=_ref("IA", source_id="src-B"), phase=PHASE_A),
            ],
        )
        refs = context_channel_refs(context)
        assert {r.source_id for r in refs} == {"src-A", "src-B"}


class TestEngineeringContextCompletenessNotRequired:
    def test_single_member_context_is_a_valid_shape(self):
        """Owner instruction: an Engineering Context must not require all
        phases -- a single Va+Ia (or even just Va) context is legitimate."""
        context = EngineeringContext(
            id="ec-1", workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=_ref("VA"), phase=PHASE_A)],
        )
        assert len(context.members) == 1


class TestMemberForChannelRef:
    def test_finds_existing_member(self):
        ref = _ref("VA")
        context = EngineeringContext(
            id="ec-1", workspace_id="ws-1", display_name="Alpha 1",
            members=[EngineeringContextMember(channel_ref=ref, phase=PHASE_A)],
        )
        found = member_for_channel_ref(context, ref)
        assert found is not None
        assert found.phase == PHASE_A

    def test_returns_none_for_unknown_ref(self):
        context = EngineeringContext(id="ec-1", workspace_id="ws-1", display_name="Alpha 1")
        assert member_for_channel_ref(context, _ref("VA")) is None


class TestValidateMemberFields:
    def test_valid_member_does_not_raise(self):
        member = EngineeringContextMember(
            channel_ref=_ref("VA"), phase=PHASE_A, phase_source=PHASE_SOURCE_ENGINEER_CONFIRMED
        )
        validate_member_fields(member)

    def test_invalid_phase_raises(self):
        member = EngineeringContextMember(channel_ref=_ref("VA"), phase="Z")
        with pytest.raises(ValueError):
            validate_member_fields(member)

    def test_invalid_phase_source_raises(self):
        member = EngineeringContextMember(channel_ref=_ref("VA"), phase_source="guessed")
        with pytest.raises(ValueError):
            validate_member_fields(member)
