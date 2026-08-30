"""Unit tests for the in-memory, ephemeral CSV preparation-session registry.

Mirrors tests/test_workspace_registry.py's own structure/coverage
exactly, since PreparationSessionRegistry deliberately mirrors
WorkspaceRegistry's implementation (see that module's own docstring for
why an in-memory sibling registry, not StorageBackend, was chosen).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.preparation_session import (
    FORMAT_CSV,
    STATUS_NEEDS_PREPARATION,
    PreparationSession,
    PreparationSessionSummary,
)
from app.services.preparation_session_registry import PreparationSessionRegistry


def _session(workspace_id: str, source_id: str, *, raw_bytes: bytes = b"a,b\n1,2\n") -> PreparationSession:
    summary = PreparationSessionSummary(
        source_id=source_id,
        workspace_id=workspace_id,
        original_filename=f"{source_id}.csv",
        source_format=FORMAT_CSV,
        original_byte_size=len(raw_bytes),
        status=STATUS_NEEDS_PREPARATION,
        created_at=datetime.now(timezone.utc),
    )
    return PreparationSession(summary=summary, raw_bytes=raw_bytes)


def test_add_and_get_round_trip():
    registry = PreparationSessionRegistry()
    session = _session("ws-1", "src-1")

    registry.add(session)

    assert registry.get("ws-1", "src-1") is session


def test_get_unknown_returns_none():
    registry = PreparationSessionRegistry()

    assert registry.get("ws-1", "does-not-exist") is None


def test_workspaces_are_isolated_from_each_other():
    registry = PreparationSessionRegistry()
    registry.add(_session("ws-1", "src-1"))
    registry.add(_session("ws-2", "src-1"))  # same source_id, different workspace

    assert registry.get("ws-1", "src-1").summary.workspace_id == "ws-1"
    assert registry.get("ws-2", "src-1").summary.workspace_id == "ws-2"
    assert registry.get("ws-1", "src-1") is not registry.get("ws-2", "src-1")


def test_list_for_workspace_only_returns_that_workspaces_sessions():
    registry = PreparationSessionRegistry()
    registry.add(_session("ws-1", "src-1"))
    registry.add(_session("ws-1", "src-2"))
    registry.add(_session("ws-2", "src-3"))

    listed = registry.list_for_workspace("ws-1")

    assert {s.summary.source_id for s in listed} == {"src-1", "src-2"}


def test_list_for_unknown_workspace_returns_empty():
    registry = PreparationSessionRegistry()

    assert registry.list_for_workspace("nonexistent") == []


def test_remove_releases_ownership_and_prevents_later_access():
    registry = PreparationSessionRegistry()
    registry.add(_session("ws-1", "src-1"))

    removed = registry.remove("ws-1", "src-1")

    assert removed is True
    assert registry.get("ws-1", "src-1") is None
    assert registry.list_for_workspace("ws-1") == []


def test_remove_unknown_returns_false():
    registry = PreparationSessionRegistry()

    assert registry.remove("ws-1", "does-not-exist") is False


def test_count_reflects_current_entries():
    registry = PreparationSessionRegistry()
    assert registry.count() == 0

    registry.add(_session("ws-1", "src-1"))
    registry.add(_session("ws-1", "src-2"))
    assert registry.count() == 2

    registry.remove("ws-1", "src-1")
    assert registry.count() == 1


def test_remove_workspace_releases_every_session_it_owns():
    registry = PreparationSessionRegistry()
    registry.add(_session("ws-1", "src-1"))
    registry.add(_session("ws-1", "src-2"))
    registry.add(_session("ws-1", "src-3"))

    removed_count = registry.remove_workspace("ws-1")

    assert removed_count == 3
    assert registry.list_for_workspace("ws-1") == []
    assert registry.count() == 0


def test_remove_workspace_leaves_other_workspaces_untouched():
    registry = PreparationSessionRegistry()
    registry.add(_session("ws-1", "src-1"))
    registry.add(_session("ws-2", "src-1"))
    registry.add(_session("ws-2", "src-2"))

    registry.remove_workspace("ws-1")

    assert registry.list_for_workspace("ws-1") == []
    assert {s.summary.source_id for s in registry.list_for_workspace("ws-2")} == {"src-1", "src-2"}
    assert registry.count() == 2


def test_remove_workspace_unknown_is_a_safe_no_op():
    registry = PreparationSessionRegistry()
    registry.add(_session("ws-2", "src-1"))

    removed_count = registry.remove_workspace("does-not-exist")

    assert removed_count == 0
    assert registry.count() == 1


def test_remove_workspace_already_empty_is_a_safe_no_op():
    registry = PreparationSessionRegistry()

    assert registry.remove_workspace("ws-1") == 0


def test_raw_bytes_are_held_immutably_by_reference():
    raw = b"a,b,c\n1,2,3\n"
    session = _session("ws-1", "src-1", raw_bytes=raw)
    registry = PreparationSessionRegistry()

    registry.add(session)

    stored = registry.get("ws-1", "src-1")
    assert stored.raw_bytes == raw
    assert stored.raw_bytes is raw
