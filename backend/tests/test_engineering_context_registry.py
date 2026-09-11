"""Tests for app.services.engineering_context_registry (Analysis
Guardrail Slice 1): thread-safe in-memory storage + cross-context
channel-uniqueness invariant. Mirrors
test_measurement_group_registry.py's own coverage shape.
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.domain.measurement_group import STATUS_CONFIRMED, STATUS_MANUAL
from app.domain.phase_identity import PHASE_A
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import (
    ChannelAlreadyInContextError,
    DuplicateChannelReferenceInContextError,
    EngineeringContextAlreadyExistsError,
)


def _ref(name: str, source_id: str = "src-1") -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name=name)


def _context(context_id: str, workspace_id: str = "ws-1", members=None, status: str = STATUS_MANUAL) -> EngineeringContext:
    return EngineeringContext(
        id=context_id, workspace_id=workspace_id, display_name="Alpha 1",
        members=members or [], status=status,
    )


class TestAddGet:
    def test_add_then_get_round_trips(self):
        registry = EngineeringContextRegistry()
        member = EngineeringContextMember(channel_ref=_ref("VA"), phase=PHASE_A)
        registry.add(_context("ec-1", members=[member]))
        fetched = registry.get("ws-1", "ec-1")
        assert fetched is not None
        assert fetched.display_name == "Alpha 1"
        assert len(fetched.members) == 1

    def test_get_missing_returns_none(self):
        registry = EngineeringContextRegistry()
        assert registry.get("ws-1", "ec-missing") is None

    def test_add_is_create_only(self):
        registry = EngineeringContextRegistry()
        registry.add(_context("ec-1"))
        with pytest.raises(EngineeringContextAlreadyExistsError):
            registry.add(_context("ec-1"))

    def test_get_returns_defensive_copy(self):
        """Mutating the returned object must not corrupt the registry's
        own stored state -- mirrors MeasurementGroupRegistry's own
        documented hazard."""
        registry = EngineeringContextRegistry()
        registry.add(_context("ec-1"))
        fetched = registry.get("ws-1", "ec-1")
        fetched.display_name = "Corrupted"
        fetched.members.append(EngineeringContextMember(channel_ref=_ref("VA")))
        still_stored = registry.get("ws-1", "ec-1")
        assert still_stored.display_name == "Alpha 1"
        assert still_stored.members == []


class TestCrossContextChannelUniqueness:
    def test_same_channel_in_two_contexts_rejected(self):
        registry = EngineeringContextRegistry()
        ref = _ref("VA")
        registry.add(_context("ec-1", members=[EngineeringContextMember(channel_ref=ref, phase=PHASE_A)]))
        with pytest.raises(ChannelAlreadyInContextError):
            registry.add(_context("ec-2", members=[EngineeringContextMember(channel_ref=ref, phase=PHASE_A)]))

    def test_duplicate_within_one_context_rejected(self):
        registry = EngineeringContextRegistry()
        ref = _ref("VA")
        members = [
            EngineeringContextMember(channel_ref=ref, phase=PHASE_A),
            EngineeringContextMember(channel_ref=ref, phase=PHASE_A),
        ]
        with pytest.raises(DuplicateChannelReferenceInContextError):
            registry.add(_context("ec-1", members=members))

    def test_context_for_channel(self):
        registry = EngineeringContextRegistry()
        ref = _ref("VA")
        registry.add(_context("ec-1", members=[EngineeringContextMember(channel_ref=ref, phase=PHASE_A)]))
        assert registry.context_for_channel("ws-1", ref) == "ec-1"
        assert registry.context_for_channel("ws-1", _ref("OTHER")) is None


class TestUpdate:
    def test_update_replaces_membership_and_reindexes(self):
        registry = EngineeringContextRegistry()
        old_ref = _ref("VA")
        registry.add(_context("ec-1", members=[EngineeringContextMember(channel_ref=old_ref, phase=PHASE_A)]))
        context = registry.get("ws-1", "ec-1")
        new_ref = _ref("VB")
        context.members = [EngineeringContextMember(channel_ref=new_ref, phase=PHASE_A)]
        context.status = STATUS_CONFIRMED
        registry.update(context)
        fetched = registry.get("ws-1", "ec-1")
        assert {m.channel_ref.channel_name for m in fetched.members} == {"VB"}
        assert fetched.status == STATUS_CONFIRMED
        # OLD channel released.
        assert registry.context_for_channel("ws-1", old_ref) is None
        assert registry.context_for_channel("ws-1", new_ref) == "ec-1"

    def test_update_keeping_own_channel_is_not_a_conflict(self):
        registry = EngineeringContextRegistry()
        ref = _ref("VA")
        registry.add(_context("ec-1", members=[EngineeringContextMember(channel_ref=ref, phase=PHASE_A)]))
        context = registry.get("ws-1", "ec-1")
        context.display_name = "Renamed"
        registry.update(context)  # same ref, same context -- must not raise
        assert registry.get("ws-1", "ec-1").display_name == "Renamed"

    def test_update_missing_context_raises_key_error(self):
        registry = EngineeringContextRegistry()
        with pytest.raises(KeyError):
            registry.update(_context("ec-missing"))


class TestRemove:
    def test_remove_releases_channel_index(self):
        registry = EngineeringContextRegistry()
        ref = _ref("VA")
        registry.add(_context("ec-1", members=[EngineeringContextMember(channel_ref=ref, phase=PHASE_A)]))
        assert registry.remove("ws-1", "ec-1") is True
        assert registry.get("ws-1", "ec-1") is None
        assert registry.context_for_channel("ws-1", ref) is None

    def test_remove_missing_is_false(self):
        registry = EngineeringContextRegistry()
        assert registry.remove("ws-1", "ec-missing") is False


class TestRemoveWorkspace:
    def test_removes_only_that_workspace(self):
        registry = EngineeringContextRegistry()
        registry.add(_context("ec-1", workspace_id="ws-A"))
        registry.add(_context("ec-2", workspace_id="ws-B"))
        removed = registry.remove_workspace("ws-A")
        assert removed == 1
        assert registry.get("ws-A", "ec-1") is None
        assert registry.get("ws-B", "ec-2") is not None

    def test_idempotent_for_empty_workspace(self):
        registry = EngineeringContextRegistry()
        assert registry.remove_workspace("ws-nothing") == 0


class TestCount:
    def test_count(self):
        registry = EngineeringContextRegistry()
        assert registry.count() == 0
        registry.add(_context("ec-1"))
        registry.add(_context("ec-2", workspace_id="ws-2"))
        assert registry.count() == 2
