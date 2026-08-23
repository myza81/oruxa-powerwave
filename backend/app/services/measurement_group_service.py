"""Measurement Group orchestration layer (Slice 1 of DEC-050's
measurement-group-aware Per-Unit redesign).

Sits above `MeasurementGroupRegistry` exactly the way
`per_unit_service.py` sits above `PerUnitRegistry`: the registry stays
pure storage plus the one structural invariant it alone can verify
(cross-group channel uniqueness); this module resolves everything that
requires OTHER workspace state (does the source exist? what is this
channel's own `engineering_type`?) via `WorkspaceRegistry`, translates
domain validation into the `ImportServiceError` subclasses from
`app.services.errors`, and is the only place that generates a new
`measurement_group_id`.

Internal-only in this slice -- no `app/api/v1/measurement_groups.py`
router exists yet (per the task's own explicit instruction not to
expose a new public API without first reporting why it would be
necessary; nothing here needed one). Every function is exercised
directly by `backend/tests/test_measurement_group_*.py`.
"""

from __future__ import annotations

from uuid import uuid4

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import (
    KNOWN_GROUP_KINDS,
    STATUS_MANUAL,
    MeasurementGroup,
    channel_kind_compatible,
    channel_ref_is_group_eligible,
    channel_ref_matches_source,
    group_kind_valid,
    group_status_valid,
)
from app.services.errors import (
    ChannelNotFoundError,
    ChannelWrongEngineeringTypeError,
    ChannelWrongSourceError,
    InvalidMeasurementGroupKindError,
    InvalidMeasurementGroupStatusError,
    MeasurementGroupNotFoundError,
    SourceNotFoundError,
    UnsupportedChannelReferenceKindError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.workspace_registry import WorkspaceRegistry


def _validate_kind(kind: str) -> None:
    if not group_kind_valid(kind):
        raise InvalidMeasurementGroupKindError(
            f"Unknown measurement group kind {kind!r}; must be one of {KNOWN_GROUP_KINDS!r}."
        )


def _validate_status(status: str) -> None:
    if not group_status_valid(status):
        raise InvalidMeasurementGroupStatusError(f"Unknown measurement group status {status!r}.")


def _validate_channel_refs_for_group(
    *, workspace_id: str, source_id: str, kind: str, channel_refs: list[ChannelRef], source_registry: WorkspaceRegistry
) -> None:
    """Resolves and checks every one of the "Membership invariants"
    (canonical document section 6) that require live workspace state:
    channel-reference kind eligibility (source-only, Slice 1 scope),
    same-source, channel existence, and engineering-type compatibility.
    Duplicate-within-list and cross-group-uniqueness are checked by
    `MeasurementGroupRegistry` itself (see that module's own docstring)
    -- not repeated here, so there is exactly one place each invariant
    is enforced."""
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in this workspace.")
    for ref in channel_refs:
        if not channel_ref_is_group_eligible(ref):
            raise UnsupportedChannelReferenceKindError(
                f"Channel reference {ref!r} is not a source channel; only source channels may belong to a "
                "measurement group in this slice."
            )
        if not channel_ref_matches_source(source_id, ref):
            raise ChannelWrongSourceError(
                f"Channel reference {ref!r} does not belong to source '{source_id}'."
            )
        # Same "read the already-classified channel, never reclassify"
        # pattern as waveform_service._analog_channel_engineering_type
        # and per_unit_registry._engineering_type_for_input (source
        # branch) -- duplicated here by this codebase's own established
        # convention rather than centralized, see those modules' own
        # docstrings. A missing channel and an Undefined-typed channel
        # are deliberately distinguished (ChannelNotFoundError vs.
        # ChannelWrongEngineeringTypeError), unlike those two read-only
        # accessors which only need a single UNDEFINED fallback value.
        matching = next((ch for ch in active.metadata.analog_channels if ch.name == ref.channel_name), None)
        if matching is None:
            raise ChannelNotFoundError(f"No channel named '{ref.channel_name}' on source '{source_id}'.")
        if not channel_kind_compatible(kind, matching.engineering_type):
            raise ChannelWrongEngineeringTypeError(
                f"Channel '{ref.channel_name}' has engineering type {matching.engineering_type!r}, "
                f"which is not compatible with group kind {kind!r}."
            )


def create_group(
    *,
    workspace_id: str,
    source_id: str,
    kind: str,
    display_name: str,
    channel_refs: list[ChannelRef],
    status: str = STATUS_MANUAL,
    registry: MeasurementGroupRegistry,
    source_registry: WorkspaceRegistry,
) -> MeasurementGroup:
    """Creates and stores a brand-new measurement group. Every channel
    reference is validated against `source_id`/`kind` before anything is
    written -- no partial group is ever stored on a validation failure."""
    _validate_kind(kind)
    _validate_status(status)
    _validate_channel_refs_for_group(
        workspace_id=workspace_id, source_id=source_id, kind=kind, channel_refs=channel_refs, source_registry=source_registry
    )
    group = MeasurementGroup(
        id="mg-" + uuid4().hex,
        workspace_id=workspace_id,
        source_id=source_id,
        kind=kind,
        display_name=display_name,
        channel_refs=list(channel_refs),
        status=status,
    )
    registry.add(group)
    return group


def get_group(workspace_id: str, measurement_group_id: str, *, registry: MeasurementGroupRegistry) -> MeasurementGroup:
    group = registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    return group


def list_groups_for_workspace(workspace_id: str, *, registry: MeasurementGroupRegistry) -> list[MeasurementGroup]:
    return registry.list_for_workspace(workspace_id)


def list_groups_for_source(workspace_id: str, source_id: str, *, registry: MeasurementGroupRegistry) -> list[MeasurementGroup]:
    return registry.list_for_source(workspace_id, source_id)


def update_group_metadata(
    *,
    workspace_id: str,
    measurement_group_id: str,
    registry: MeasurementGroupRegistry,
    display_name: str | None = None,
    status: str | None = None,
) -> MeasurementGroup:
    """Partial update of `display_name`/`status` ONLY -- membership
    changes go through `update_group_membership` below, which needs the
    source registry to re-validate references. Section 8: display name
    is never identity, so renaming never affects `id`/membership."""
    group = get_group(workspace_id, measurement_group_id, registry=registry)
    if status is not None:
        _validate_status(status)
        group.status = status
    if display_name is not None:
        group.display_name = display_name
    registry.update(group)
    return group


def update_group_membership(
    *,
    workspace_id: str,
    measurement_group_id: str,
    channel_refs: list[ChannelRef],
    registry: MeasurementGroupRegistry,
    source_registry: WorkspaceRegistry,
) -> MeasurementGroup:
    """Full replace of a group's own `channel_refs` -- re-validates every
    invariant from scratch against the group's own (immutable)
    `source_id`/`kind`, exactly like `create_group`. A channel currently
    owned by THIS group is correctly treated as available (see
    `MeasurementGroupRegistry.update()`'s own docstring); a channel owned
    by a different group is still rejected."""
    group = get_group(workspace_id, measurement_group_id, registry=registry)
    _validate_channel_refs_for_group(
        workspace_id=workspace_id, source_id=group.source_id, kind=group.kind, channel_refs=channel_refs, source_registry=source_registry
    )
    group.channel_refs = list(channel_refs)
    registry.update(group)
    return group


def delete_group(workspace_id: str, measurement_group_id: str, *, registry: MeasurementGroupRegistry) -> bool:
    return registry.remove(workspace_id, measurement_group_id)


def remove_measurement_groups_for_source(
    *, workspace_id: str, source_id: str, registry: MeasurementGroupRegistry
) -> list[str]:
    """Source-removal lifecycle counterpart to
    `calculated_channel_service.remove_calculated_channels_for_source`
    -- a flat scan (via `list_for_source`) rather than a maintained
    reverse "groups by source" index, matching this codebase's own
    established "no denormalized reverse index beyond what one
    invariant strictly requires" convention. Returns the removed group
    ids, for logging/testing. Idempotent for a source with no groups."""
    affected = [group.id for group in registry.list_for_source(workspace_id, source_id)]
    for measurement_group_id in affected:
        registry.remove(workspace_id, measurement_group_id)
    return affected
