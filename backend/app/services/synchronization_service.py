"""Waveform time-synchronization orchestration (Slice 1: per-source
alignment offsets; Slice 2: one workspace-wide event origin, `t0`).

Every real source currently in the workspace is a candidate for its own
alignment offset -- this module lists them all (offset defaults to `0`
until explicitly set), resolves which one is the current reference
source (`app.domain.synchronization.reference_source_id_for_workspace`,
by earliest `created_at`), enforces that the reference source's own
offset can never become non-zero, and validates/stores/clears an offset
via `SynchronizationRegistry`. Slice 2 adds the equivalent
validate/store/clear surface for the workspace's own single event
origin (`t0_workspace_time`) -- deliberately a SEPARATE set of
functions/registry keys from the per-source offset ones above (Slice 2
task section 11: "these are separate concepts... do not absorb the
alignment offset into t0"), never sharing a clear/reset code path except
at full workspace-lifecycle teardown (`remove_workspace_synchronization_state()`).

This module never touches waveform/cursor/digital-waveform data --
Slice 1's request/response time-shift for those endpoints, and Slice 2's
additional event-time layer on top, both happen entirely on the frontend
(convert the event/workspace-time range to source-native before calling
the EXISTING `.../waveform`/`.../cursor-values`/`.../digital-waveform`
endpoints unchanged, then shift the returned times back for display),
mirroring DEC-042's own "presentation-layer transform, not a backend
data authority" precedent for Absolute/Elapsed time-mode. The backend's
own role is authoritative storage and validation of the scalar
offset/t0 values only -- see app.domain.synchronization's own module
docstring for the full architectural rationale.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.synchronization import alignment_offset_valid, reference_source_id_for_workspace
from app.services.errors import (
    InvalidAlignmentOffsetError,
    InvalidT0Error,
    ReferenceSourceAlignmentError,
    SourceNotFoundError,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry


@dataclass(slots=True)
class SourceAlignmentView:
    """One source's own alignment offset, as the manual-synchronization
    UI needs to render it."""

    source_id: str
    alignment_offset_s: float
    is_reference: bool


def resolve_reference_source_id(*, workspace_id: str, source_registry: WorkspaceRegistry) -> str | None:
    """The one place this workspace's current reference source is
    computed -- see app.domain.synchronization.reference_source_id_for_workspace's
    own docstring for the deterministic rule (earliest `created_at`).
    Recomputed fresh on every call rather than cached/persisted: the
    reference identity is a derived fact of the CURRENT source set, and
    must never go stale after a source is added/removed."""
    sources = [(active.metadata.source_id, active.metadata.created_at) for active in source_registry.list_for_workspace(workspace_id)]
    return reference_source_id_for_workspace(sources)


def _view_for_source(*, source_id: str, registry: SynchronizationRegistry, workspace_id: str, reference_source_id: str | None) -> SourceAlignmentView:
    return SourceAlignmentView(
        source_id=source_id,
        alignment_offset_s=registry.get_offset(workspace_id, source_id),
        is_reference=(source_id == reference_source_id),
    )


def list_source_alignments(*, workspace_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry) -> list[SourceAlignmentView]:
    """Every real source currently loaded in the workspace, offset or
    not -- mirrors `list_source_per_unit_configs`'s own "every loaded
    recording appears automatically" rule."""
    reference_source_id = resolve_reference_source_id(workspace_id=workspace_id, source_registry=source_registry)
    return [
        _view_for_source(source_id=active.metadata.source_id, registry=registry, workspace_id=workspace_id, reference_source_id=reference_source_id)
        for active in source_registry.list_for_workspace(workspace_id)
    ]


def get_source_alignment(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry) -> SourceAlignmentView:
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    reference_source_id = resolve_reference_source_id(workspace_id=workspace_id, source_registry=source_registry)
    return _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, reference_source_id=reference_source_id)


def set_source_alignment_offset(
    *, workspace_id: str, source_id: str, alignment_offset_s: float, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry
) -> SourceAlignmentView:
    """Create-or-replace ONE source's own alignment offset (task section
    2: "updating a source offset"). 404s if `source_id` does not exist in
    this workspace; rejects a non-finite offset
    (`InvalidAlignmentOffsetError`); rejects a non-zero offset on the
    CURRENT reference source (`ReferenceSourceAlignmentError`, task
    section 9's own "reference offset is always 0" rule) -- setting the
    reference source's own offset to exactly `0` is accepted as a
    harmless no-op, never rejected, so a client does not need to special-
    case "skip the reference row" before calling this."""
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    if not alignment_offset_valid(alignment_offset_s):
        raise InvalidAlignmentOffsetError("alignment_offset_s must be a finite number of seconds.")
    reference_source_id = resolve_reference_source_id(workspace_id=workspace_id, source_registry=source_registry)
    if source_id == reference_source_id and alignment_offset_s != 0.0:
        raise ReferenceSourceAlignmentError(
            "The reference source's own alignment offset is always 0 and cannot be changed directly."
        )
    if alignment_offset_s == 0.0:
        registry.reset_offset(workspace_id, source_id)
    else:
        registry.set_offset(workspace_id, source_id, alignment_offset_s)
    return _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, reference_source_id=reference_source_id)


def reset_source_alignment_offset(
    *, workspace_id: str, source_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry
) -> SourceAlignmentView:
    """`alignment_offset_s -> 0` for one source (task section 10). 404s
    if `source_id` does not exist; idempotent for an already-unshifted
    source (resetting the reference source, which is already always `0`,
    is always a harmless no-op, never an error)."""
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    registry.reset_offset(workspace_id, source_id)
    reference_source_id = resolve_reference_source_id(workspace_id=workspace_id, source_registry=source_registry)
    return _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, reference_source_id=reference_source_id)


def reset_all_alignment_offsets(*, workspace_id: str, registry: SynchronizationRegistry) -> int:
    """Every source offset in this workspace `-> 0` (Slice 1 task section
    10: "reset all synchronization"). Returns the number of sources that
    actually had a non-default offset cleared, for logging/testing, not
    for any success/failure branching by the caller (mirrors
    `WorkspaceRegistry.remove_workspace()`'s own idempotent contract).

    **Deliberately leaves t0 untouched** (Slice 2 task section 14:
    "Synchronization reset and t=0 reset are independent... source
    offsets return to zero; t=0 should remain unchanged") --
    `registry.remove_workspace()` only ever cleared the offsets store;
    this call site is exactly why that method must never be widened to
    also clear `_t0` (see that method's own docstring)."""
    return registry.remove_workspace(workspace_id)


def remove_source_alignment(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry) -> None:
    """Source-removal lifecycle hook (Slice 1 task section 10) -- called
    from `app.api.v1.sources.delete_source`, mirroring
    `delete_source_per_unit_config`'s own call-site shape exactly.

    Deliberately does NOT touch t0 (Slice 2 task section 15) --
    `registry.remove_source()` only ever touched this one source's own
    offset in the first place, so no change was needed here to preserve
    that; documented at this call site anyway since a future reader
    extending source-removal cleanup should not assume t0 belongs in
    this function too."""
    registry.remove_source(workspace_id, source_id)


def remove_workspace_synchronization_state(*, workspace_id: str, registry: SynchronizationRegistry) -> None:
    """Full workspace-lifecycle teardown hook -- called from
    `app.api.v1.workspaces.delete_workspace` ("Start New Workspace").
    Clears BOTH every source's own alignment offset AND the workspace's
    own t0 event origin (Slice 2 task section 15: "t=0 is workspace-
    scoped state. It must be cleared when starting a new workspace;
    deleting/resetting the workspace"). Distinct from
    `reset_all_alignment_offsets()` below (offsets only, "Reset All"
    within a still-live workspace) -- see that function's own docstring
    for why t0 must stay untouched there."""
    registry.remove_workspace(workspace_id)
    registry.clear_t0(workspace_id)


@dataclass(slots=True)
class T0View:
    """The workspace's own single event-origin state, as the API needs
    to render it. `t0_workspace_time` is `None` exactly when no event
    origin has been selected (or it was cleared) -- never a fabricated
    `0.0` default (see `SynchronizationRegistry.get_t0()`'s own
    docstring)."""

    t0_workspace_time: float | None


def get_t0(*, workspace_id: str, registry: SynchronizationRegistry) -> T0View:
    return T0View(t0_workspace_time=registry.get_t0(workspace_id))


def set_t0(*, workspace_id: str, t0_workspace_time: float, registry: SynchronizationRegistry) -> T0View:
    """Sets the workspace's single common event origin (Slice 2 task
    section 4: "one common event origin for the workspace," never
    per-source -- there is no `source_id` parameter here at all).
    Rejects a non-finite value (`InvalidT0Error`) -- reuses the SAME
    finite-real-number validator alignment offsets already use
    (`app.domain.synchronization.alignment_offset_valid`, see that
    function's own docstring for why sharing the predicate is correct
    even though the two are kept as distinctly-coded API errors).

    Deliberately does NOT touch any source's own `alignment_offset_s`
    (task section 11: "these are separate concepts... do not absorb the
    alignment offset into t0") and does NOT require any particular
    source to exist -- once selected, t0 is a pure workspace-time
    coordinate, decoupled from whichever source's cursor happened to
    help choose it (task section 15's own "t0 is a workspace coordinate
    once defined" framing). Setting a NEW t0 while one already exists is
    a plain create-or-replace, matching every other PUT in this
    codebase -- the caller (the frontend's "Set Cursor A as t=0" action)
    always sends the engineer's current, deliberate choice."""
    if not alignment_offset_valid(t0_workspace_time):
        raise InvalidT0Error("t0_workspace_time must be a finite number of seconds.")
    registry.set_t0(workspace_id, t0_workspace_time)
    return T0View(t0_workspace_time=t0_workspace_time)


def clear_t0(*, workspace_id: str, registry: SynchronizationRegistry) -> None:
    """"Clear t=0" (Slice 2 task section 13): removes ONLY the
    event-origin reference, returning the display to plain workspace-
    elapsed time. Never touches any source's own `alignment_offset_s`
    -- deliberately NOT the same operation as `reset_all_alignment_offsets()`
    below (task section 13: "Do not make Clear t=0 equivalent to
    synchronization Reset All")."""
    registry.clear_t0(workspace_id)
