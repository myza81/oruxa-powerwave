"""Measurement Group orchestration layer (Slice 1/2 of DEC-050's
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

Slice 2 adds exactly one new function,
`generate_suggested_groups_for_source()`, layered on top of the Slice 1
functions below rather than beside them: it calls the pure
`app.domain.measurement_group_detection.detect_measurement_groups()`
algorithm, then persists each still-eligible candidate through
`create_group()` -- the SAME validated creation path every other caller
uses, never a direct `registry.add()`. It is a standalone, explicitly-
callable function with no automatic trigger wired into any existing
endpoint (e.g. source upload) -- see this function's own docstring for
why, and canonical document section 15/25 for the broader Slice
sequencing this defers to.
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
from app.domain.measurement_group_detection import DetectedGroup, detect_measurement_groups
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
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
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


def delete_group(
    workspace_id: str,
    measurement_group_id: str,
    *,
    registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry | None = None,
) -> bool:
    """Deletes one group. Slice 3: also releases its own Voltage base
    configuration, if any (optional param, same reason
    `remove_calculated_channels_for_source` takes an optional
    `per_unit_registry` -- older callers/tests that predate Slice 3 and
    have no voltage configuration to worry about are unaffected)."""
    removed = registry.remove(workspace_id, measurement_group_id)
    if removed and voltage_config_registry is not None:
        voltage_config_registry.delete(workspace_id, measurement_group_id)
    return removed


def remove_measurement_groups_for_source(
    *,
    workspace_id: str,
    source_id: str,
    registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry | None = None,
) -> list[str]:
    """Source-removal lifecycle counterpart to
    `calculated_channel_service.remove_calculated_channels_for_source`
    -- a flat scan (via `list_for_source`) rather than a maintained
    reverse "groups by source" index, matching this codebase's own
    established "no denormalized reverse index beyond what one
    invariant strictly requires" convention. Returns the removed group
    ids, for logging/testing. Idempotent for a source with no groups.

    Slice 3: also releases each removed group's own Voltage base
    configuration, if any (optional param, same reason as above)."""
    affected = [group.id for group in registry.list_for_source(workspace_id, source_id)]
    for measurement_group_id in affected:
        registry.remove(workspace_id, measurement_group_id)
        if voltage_config_registry is not None:
            voltage_config_registry.delete(workspace_id, measurement_group_id)
    return affected


def generate_suggested_groups_for_source(
    *, workspace_id: str, source_id: str, registry: MeasurementGroupRegistry, source_registry: WorkspaceRegistry
) -> list[MeasurementGroup]:
    """Slice 2: runs deterministic automatic detection
    (`detect_measurement_groups()`) against one source's own Voltage/
    Current channels and persists each still-eligible candidate as a
    new `STATUS_SUGGESTED`/`STATUS_NEEDS_REVIEW` measurement group --
    through `create_group()`, the same validated path every other
    caller uses, never a direct `registry.add()`.

    **Idempotent and additive-only, never destructive** -- this is what
    makes "regenerating" safe to call as often as wanted: a detected
    cluster is skipped ENTIRELY (not partially applied) if even one of
    its own channels already belongs to ANY existing group, of ANY
    status (`manual`, `confirmed`, or a `suggested`/`needs_review` group
    from a prior run). An existing group's own fields/membership are
    never read, modified, or replaced by this function -- only genuinely
    still-ungrouped channels ever result in a new group. Returns the
    newly created groups only (an empty list on a source with nothing
    new to suggest, including a source that was already fully grouped).

    **No automatic trigger exists for this function** -- it is not
    called from the source-upload endpoint or anywhere else yet. This
    is a deliberate Slice 2 scope boundary: wiring it into an existing
    endpoint's behaviour is deferred to whichever later slice first
    needs the result to be observable (group-aware PU resolution or the
    frontend configuration workspace), so this slice changes no
    existing endpoint's behaviour at all -- exactly like Slice 1's own
    scope discipline.
    """
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in this workspace.")

    channels = [(ch.name, ch.engineering_type) for ch in active.metadata.analog_channels]
    detected_groups = detect_measurement_groups(channels)

    # Slice 3 robustness fix: every candidate is fully validated BEFORE
    # any persistence is attempted, so a single invalid candidate (e.g.
    # a source with two literally-identically-named channels, producing
    # a duplicate ChannelRef within one detected cluster) can never
    # leave earlier-processed candidates already persisted while a
    # later one crashes mid-loop. This is preflight validation, not
    # exception-swallowing: the ONE known failure mode
    # (`create_group()`'s own duplicate-reference check) is checked
    # directly here, on data that cannot change between this check and
    # the persistence loop below (both read the same already-fetched
    # `active.metadata.analog_channels` within one synchronous call) --
    # so the persistence loop itself is not expected to raise for any
    # candidate that reaches it.
    candidates: list[tuple[DetectedGroup, list[ChannelRef]]] = []
    for detected in detected_groups:
        channel_refs = [
            ChannelRef(kind="source", source_id=source_id, channel_name=name) for name in detected.channel_names
        ]
        if len(channel_refs) != len(set(channel_refs)):
            # A detected cluster containing the same channel reference
            # twice (only reachable when the source itself has two
            # channels sharing one exact name) can never be persisted
            # as a valid group -- skip it entirely, deterministically,
            # before touching the registry at all. Never partially
            # applied, never silently retried with a mutated ref list.
            continue
        if any(registry.group_for_channel(workspace_id, ref) is not None for ref in channel_refs):
            continue
        candidates.append((detected, channel_refs))

    return [
        create_group(
            workspace_id=workspace_id,
            source_id=source_id,
            kind=detected.kind,
            display_name=detected.display_name,
            channel_refs=channel_refs,
            status=detected.status,
            registry=registry,
            source_registry=source_registry,
        )
        for detected, channel_refs in candidates
    ]
