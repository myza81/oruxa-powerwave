"""Waveform time-synchronization orchestration (Slice 1).

Every real source currently in the workspace is a candidate for its own
alignment offset -- this module lists them all (offset defaults to `0`
until explicitly set), resolves which one is the current reference
source (`app.domain.synchronization.reference_source_id_for_workspace`,
by earliest `created_at`), enforces that the reference source's own
offset can never become non-zero, and validates/stores/clears an offset
via `SynchronizationRegistry`.

This module never touches waveform/cursor/digital-waveform data --
Slice 1's request/response time-shift for those endpoints happens
entirely on the frontend (convert the workspace-time range to
source-native before calling the EXISTING `.../waveform`/`.../cursor-
values`/`.../digital-waveform` endpoints unchanged, then shift the
returned times back into workspace time for display), mirroring
DEC-042's own "presentation-layer transform, not a backend data
authority" precedent for Absolute/Elapsed time-mode. The backend's own
role is authoritative storage and validation of the scalar offset value
only -- see app.domain.synchronization's own module docstring for the
full architectural rationale.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.synchronization import alignment_offset_valid, reference_source_id_for_workspace
from app.services.errors import InvalidAlignmentOffsetError, ReferenceSourceAlignmentError, SourceNotFoundError
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
    """Every source offset in this workspace `-> 0` (task section 10:
    "reset all synchronization"). Returns the number of sources that
    actually had a non-default offset cleared, for logging/testing, not
    for any success/failure branching by the caller (mirrors
    `WorkspaceRegistry.remove_workspace()`'s own idempotent contract)."""
    return registry.remove_workspace(workspace_id)


def remove_source_alignment(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry) -> None:
    """Source-removal lifecycle hook (task section 10) -- called from
    `app.api.v1.sources.delete_source`, mirroring
    `delete_source_per_unit_config`'s own call-site shape exactly."""
    registry.remove_source(workspace_id, source_id)


def remove_workspace_alignment(*, workspace_id: str, registry: SynchronizationRegistry) -> None:
    """Workspace-reset lifecycle hook (task section 10) -- called from
    `app.api.v1.workspaces.delete_workspace`."""
    registry.remove_workspace(workspace_id)
