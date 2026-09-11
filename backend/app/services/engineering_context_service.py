"""Engineering Context orchestration layer (Analysis Guardrail Slice 1).

Sits above `EngineeringContextRegistry` exactly the way
`measurement_group_service.py` sits above `MeasurementGroupRegistry`: the
registry stays pure storage plus the one structural invariant it alone
can verify (cross-context channel uniqueness); this module resolves
everything that requires OTHER workspace state (does the source/
calculated channel actually exist?) via `WorkspaceRegistry`/
`CalculatedChannelRegistry`, translates domain validation into the
`ImportServiceError` subclasses from `app.services.errors`, and is the
only place that generates a new `engineering_context_id`.

`generate_suggested_contexts_for_source()` mirrors
`measurement_group_service.generate_suggested_groups_for_source()`
exactly: it calls the pure
`app.domain.engineering_context_detection.detect_engineering_contexts()`
algorithm, then persists each still-eligible candidate through
`create_context()` -- the SAME validated creation path every other
caller uses, never a direct `registry.add()`. Idempotent and
additive-only; no automatic trigger is wired into any existing endpoint.

Membership validation deliberately does NOT restrict a member's own
engineering_type (unlike `measurement_group_service`'s own kind-
compatibility check) -- see `app.domain.engineering_context`'s own
module docstring for why: an Engineering Context identifies physical
equipment, not a measurement kind, so any real channel (source or
calculated) may join one. Membership validation also deliberately does
NOT enforce a duplicate-role (same engineering_type + phase) guardrail
on manual create/update -- that guardrail is Slice 1's automatic
DETECTION-only concern (`engineering_context_detection.py`'s own
`STATUS_NEEDS_REVIEW` rule), mirroring `measurement_group_service`'s own
precedent of never re-deriving that on a manual, engineer-authored
`create_group()`/`update_group_membership()` call.
"""

from __future__ import annotations

from uuid import uuid4

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_context import (
    EngineeringContext,
    EngineeringContextMember,
    context_status_valid,
    member_for_channel_ref,
)
from app.domain.engineering_context_detection import ChannelForDetection, detect_engineering_contexts
from app.domain.measurement_group import STATUS_MANUAL
from app.domain.phase_identity import PHASE_SOURCE_ENGINEER_CONFIRMED, phase_source_valid, phase_valid
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import (
    EngineeringContextChannelNotFoundError,
    EngineeringContextNotFoundError,
    InvalidEngineeringContextStatusError,
    InvalidPhaseError,
    InvalidPhaseSourceError,
    SourceNotFoundError,
)
from app.services.workspace_registry import WorkspaceRegistry


def _validate_status(status: str) -> None:
    if not context_status_valid(status):
        raise InvalidEngineeringContextStatusError(f"Unknown Engineering Context status {status!r}.")


def _validate_member_channel_ref(
    *,
    workspace_id: str,
    channel_ref: ChannelRef,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> None:
    """Confirms `channel_ref` resolves to a real, existing channel --
    the one invariant every member must satisfy regardless of kind.
    Digital channels are not yet resolvable here (Slice 1 scope is
    analog engineering roles only, per the canonical document's own
    "digital channels" section) -- a digital channel name is simply
    absent from `analog_channels`, so it is rejected the same way an
    unrecognized name is, not specially detected."""
    if channel_ref.kind == "source":
        active = source_registry.get(workspace_id, channel_ref.source_id)
        if active is None:
            raise EngineeringContextChannelNotFoundError(f"No source '{channel_ref.source_id}' in this workspace.")
        matching = next(
            (ch for ch in active.metadata.analog_channels if ch.name == channel_ref.channel_name), None
        )
        if matching is None:
            raise EngineeringContextChannelNotFoundError(
                f"No analog channel named '{channel_ref.channel_name}' on source '{channel_ref.source_id}'."
            )
    elif channel_ref.kind == "calculated":
        calculated = calculated_channel_registry.get(workspace_id, channel_ref.calculated_channel_id)
        if calculated is None:
            raise EngineeringContextChannelNotFoundError(
                f"No calculated channel '{channel_ref.calculated_channel_id}' in this workspace."
            )
    else:
        raise EngineeringContextChannelNotFoundError(f"Unrecognized channel reference kind {channel_ref.kind!r}.")


def _validate_members(
    *,
    workspace_id: str,
    members: list[EngineeringContextMember],
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> None:
    for member in members:
        if not phase_valid(member.phase):
            raise InvalidPhaseError(f"Unknown phase {member.phase!r}.")
        if not phase_source_valid(member.phase_source):
            raise InvalidPhaseSourceError(f"Unknown phase source {member.phase_source!r}.")
        _validate_member_channel_ref(
            workspace_id=workspace_id,
            channel_ref=member.channel_ref,
            source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )


def create_context(
    *,
    workspace_id: str,
    display_name: str,
    members: list[EngineeringContextMember],
    status: str = STATUS_MANUAL,
    registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> EngineeringContext:
    """Creates and stores a brand-new Engineering Context. Every member
    is validated before anything is written -- no partial context is
    ever stored on a validation failure."""
    _validate_status(status)
    _validate_members(
        workspace_id=workspace_id, members=members, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    context = EngineeringContext(
        id="ec-" + uuid4().hex,
        workspace_id=workspace_id,
        display_name=display_name,
        members=list(members),
        status=status,
    )
    registry.add(context)
    return context


def get_context(workspace_id: str, engineering_context_id: str, *, registry: EngineeringContextRegistry) -> EngineeringContext:
    context = registry.get(workspace_id, engineering_context_id)
    if context is None:
        raise EngineeringContextNotFoundError(f"No Engineering Context '{engineering_context_id}' in this workspace.")
    return context


def list_contexts_for_workspace(workspace_id: str, *, registry: EngineeringContextRegistry) -> list[EngineeringContext]:
    return registry.list_for_workspace(workspace_id)


def update_context_metadata(
    *,
    workspace_id: str,
    engineering_context_id: str,
    registry: EngineeringContextRegistry,
    display_name: str | None = None,
    status: str | None = None,
) -> EngineeringContext:
    """Partial update of `display_name`/`status` ONLY -- membership
    changes go through `update_context_membership` below."""
    context = get_context(workspace_id, engineering_context_id, registry=registry)
    if status is not None:
        _validate_status(status)
        context.status = status
    if display_name is not None:
        context.display_name = display_name
    registry.update(context)
    return context


def update_context_membership(
    *,
    workspace_id: str,
    engineering_context_id: str,
    members: list[EngineeringContextMember],
    registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> EngineeringContext:
    """Full replace of a context's own `members` -- re-validates every
    invariant from scratch, exactly like `create_context`. A channel
    currently owned by THIS context is correctly treated as available
    (see `EngineeringContextRegistry.update()`'s own docstring); a
    channel owned by a different context is still rejected."""
    context = get_context(workspace_id, engineering_context_id, registry=registry)
    _validate_members(
        workspace_id=workspace_id, members=members, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    context.members = list(members)
    registry.update(context)
    return context


def update_member_phase(
    *,
    workspace_id: str,
    engineering_context_id: str,
    channel_ref: ChannelRef,
    phase: str,
    original_phase_label: str | None = None,
    phase_source: str = PHASE_SOURCE_ENGINEER_CONFIRMED,
    registry: EngineeringContextRegistry,
) -> EngineeringContext:
    """The explicit, engineer-triggered manual phase-correction path
    (owner requirement: "the engineer must eventually be able to
    correct... phase identity"). Always defaults to writing
    `phase_source="engineer_confirmed"` -- an engineer calling this
    endpoint at all IS the confirmation act, so this never needs to
    consult `phase_identity.may_overwrite_phase_assignment()`: an
    explicit, targeted correction always applies, regardless of
    whatever provenance the member previously carried. That guard exists
    for a future AUTOMATIC re-detection path to respect, not for this
    one (canonical document: "Re-running detection must never silently
    overwrite confirmed/manual... assignments" -- this function is the
    one place that IS allowed to set them)."""
    context = get_context(workspace_id, engineering_context_id, registry=registry)
    member = member_for_channel_ref(context, channel_ref)
    if member is None:
        raise EngineeringContextChannelNotFoundError(
            f"Channel reference {channel_ref!r} is not a member of Engineering Context {engineering_context_id!r}."
        )
    if not phase_valid(phase):
        raise InvalidPhaseError(f"Unknown phase {phase!r}.")
    if not phase_source_valid(phase_source):
        raise InvalidPhaseSourceError(f"Unknown phase source {phase_source!r}.")
    member.phase = phase
    member.phase_source = phase_source
    member.original_phase_label = original_phase_label
    registry.update(context)
    return context


def delete_context(workspace_id: str, engineering_context_id: str, *, registry: EngineeringContextRegistry) -> bool:
    return registry.remove(workspace_id, engineering_context_id)


def prune_engineering_contexts_for_source(
    *,
    workspace_id: str,
    source_id: str,
    registry: EngineeringContextRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> list[str]:
    """Source-removal lifecycle counterpart. Unlike
    `remove_measurement_groups_for_source` (a Measurement Group is
    source-scoped 1:1, so removing its source always removes the whole
    group), an Engineering Context may span multiple sources -- removing
    ONE source must not delete a context that still has valid members
    from OTHER sources. Instead: every member referencing the removed
    source (source-kind) or a now-gone calculated channel (calculated-
    kind, e.g. one this SAME source removal's own calculated-channel
    cascade already deleted) is dropped from each affected context; a
    context left with zero remaining members is removed entirely,
    otherwise its membership is simply reduced in place. Returns the ids
    of every AFFECTED context (edited or removed), for logging/testing.
    Idempotent for a source that owns no context membership at all.

    Callers must invoke this AFTER any calculated-channel removal
    cascade for the same source has already run (see
    `app.api.v1.sources.delete_source`'s own call ordering), so a
    calculated-kind member's own existence check here reflects the
    post-cascade truth.
    """
    affected: list[str] = []
    for context in registry.list_for_workspace(workspace_id):
        remaining = [
            member
            for member in context.members
            if not (member.channel_ref.kind == "source" and member.channel_ref.source_id == source_id)
            and not (
                member.channel_ref.kind == "calculated"
                and calculated_channel_registry.get(workspace_id, member.channel_ref.calculated_channel_id) is None
            )
        ]
        if len(remaining) == len(context.members):
            continue
        affected.append(context.id)
        if remaining:
            context.members = remaining
            registry.update(context)
        else:
            registry.remove(workspace_id, context.id)
    return affected


def generate_suggested_contexts_for_source(
    *,
    workspace_id: str,
    source_id: str,
    registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> list[EngineeringContext]:
    """Runs deterministic automatic detection
    (`detect_engineering_contexts()`) against one source's own analog
    channels and persists each still-eligible candidate as a new
    `STATUS_SUGGESTED`/`STATUS_NEEDS_REVIEW` Engineering Context --
    through `create_context()`, the same validated path every other
    caller uses.

    **Idempotent and additive-only, never destructive** -- mirrors
    `measurement_group_service.generate_suggested_groups_for_source()`'s
    own exact contract: a detected candidate is skipped ENTIRELY if even
    one of its own channels already belongs to ANY existing context, of
    ANY status. An existing context's own fields/membership are never
    read, modified, or replaced by this function.

    **No automatic trigger exists for this function** -- not called from
    the source-upload endpoint or anywhere else; only reachable through
    its own explicit `POST .../engineering-contexts/suggest` endpoint.
    """
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in this workspace.")

    channels = [
        ChannelForDetection(name=ch.name, engineering_type=ch.engineering_type, phase_label=ch.phase)
        for ch in active.metadata.analog_channels
    ]
    detected_contexts = detect_engineering_contexts(channels)

    candidates: list[tuple[str, str, list[EngineeringContextMember]]] = []
    for detected in detected_contexts:
        members = [
            EngineeringContextMember(
                channel_ref=ChannelRef(kind="source", source_id=source_id, channel_name=m.channel_name),
                phase=m.phase,
                phase_source=m.phase_source,
                original_phase_label=m.original_phase_label,
            )
            for m in detected.members
        ]
        refs = [member.channel_ref for member in members]
        if len(refs) != len(set(refs)):
            # Only reachable if the source itself has two analog
            # channels sharing one exact name -- never partially
            # applied, skipped deterministically before touching the
            # registry, mirroring measurement_group_service's own
            # identical guard.
            continue
        if any(registry.context_for_channel(workspace_id, ref) is not None for ref in refs):
            continue
        candidates.append((detected.display_name, detected.status, members))

    return [
        create_context(
            workspace_id=workspace_id,
            display_name=display_name,
            members=members,
            status=status,
            registry=registry,
            source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
        for display_name, status, members in candidates
    ]
