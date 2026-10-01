"""EventReconstructionRegistry: one definition per workspace, analysis
state only (DEC-124)."""

from __future__ import annotations

from app.domain.event_reconstruction import EventReconstructionDefinition, ReconstructionMember
from app.services.event_reconstruction_registry import EventReconstructionRegistry


def _definition(reference: str = "m1") -> EventReconstructionDefinition:
    return EventReconstructionDefinition(
        members=(
            ReconstructionMember(member_id="m1", source_ids=("a",), confirmed_group_id="a"),
            ReconstructionMember(member_id="m2", source_ids=("b",), confirmed_group_id="b", correction_s=0.5),
        ),
        reference_member_id=reference,
    )


def test_unknown_workspace_has_no_definition():
    assert EventReconstructionRegistry().get("ws") is None


def test_put_then_get_and_replace():
    registry = EventReconstructionRegistry()
    first = _definition()
    registry.put("ws", first)
    assert registry.get("ws") is first
    second = _definition(reference="m2")
    registry.put("ws", second)
    assert registry.get("ws") is second
    assert registry.count() == 1


def test_workspaces_are_isolated():
    registry = EventReconstructionRegistry()
    registry.put("ws-1", _definition())
    assert registry.get("ws-2") is None
    registry.remove_workspace("ws-2")
    assert registry.get("ws-1") is not None


def test_remove_workspace_is_idempotent():
    registry = EventReconstructionRegistry()
    registry.put("ws", _definition())
    assert registry.remove_workspace("ws") is True
    assert registry.remove_workspace("ws") is False
    assert registry.get("ws") is None
    assert registry.count() == 0


def test_stored_definition_cannot_be_mutated_through_a_read():
    registry = EventReconstructionRegistry()
    registry.put("ws", _definition())
    read = registry.get("ws")
    changed = read.with_correction("m1", 9.0)
    assert registry.get("ws").member("m1").correction_s == 0.0
    assert changed.member("m1").correction_s == 9.0
