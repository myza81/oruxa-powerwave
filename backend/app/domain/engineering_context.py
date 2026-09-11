"""Engineering Context (physical/logical bay/equipment) domain model
(Analysis Guardrail Slice 1; see
docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md).

An `EngineeringContext` answers a DIFFERENT question than
`app.domain.measurement_group.MeasurementGroup`:

- **Measurement Group** -- "which channels, all of the SAME kind
  (Voltage or Current), together represent one measurement bank" -- a
  Per-Unit/base-configuration concern, source-scoped, kind-scoped.
- **Engineering Context** -- "which channels, of ANY kind, together
  represent one physical piece of equipment/bay" -- a future
  analysis-role-resolution concern. Workspace-scoped (an equipment bay
  may legitimately span more than one uploaded source/file -- see this
  module's own membership shape below), never kind-scoped, never
  source-scoped.

The two concepts coexist deliberately and independently. A channel may
belong to a Voltage Measurement Group AND an Engineering Context at the
same time (they answer different questions); nothing about Per-Unit
resolution, `linked_voltage_group_id`, or Measurement Group detection is
read, written, or altered by this module.

Slice 1 is metadata-only scaffolding: it introduces context identity,
membership, and durable per-member phase identity so a LATER slice can
build the automatic analysis-input resolver on top of it. This module
deliberately does not implement:

- any automatic ROLE resolution (mapping "Bay + Analysis Mode" to
  concrete channels) -- that is the explicitly out-of-scope next slice;
- any completeness/validity requirement on membership -- a context with
  only one member (e.g. just "Va") is exactly as valid a context as one
  with all six phases; completeness belongs to the future resolver, not
  here (canonical document "Single-phase / incomplete contexts");
- any engineering-type restriction on membership -- unlike a Measurement
  Group (kind="voltage" only accepts Voltage channels), an Engineering
  Context is not restricted to any particular engineering type at all,
  because it identifies physical equipment, not a measurement kind. A
  future Frequency/Power/digital member is representable without a
  model change; this slice simply never populates one automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import (
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
)
from app.domain.phase_identity import (
    PHASE_SOURCE_UNKNOWN,
    PHASE_UNKNOWN,
    phase_source_valid,
    phase_valid,
)

#: Deliberately the SAME status vocabulary `app.domain.measurement_group`
#: already established (owner instruction: "reuse existing project
#: conventions... do not create a new status vocabulary unless the
#: current Measurement Group model makes reuse inappropriate" -- it is
#: not inappropriate here, the lifecycle meaning is identical: `suggested`
#: = an automatic detector's own not-yet-reviewed result, `confirmed` = an
#: engineer reviewed a suggested context, `needs_review` = uncertain/
#: contradictory automatic evidence (must never silently drive a future
#: resolver), `manual` = an engineer created this context directly, never
#: via detection. Re-exported here (not just imported by callers from
#: `measurement_group`) so this module is the one place other
#: Engineering-Context code depends on for its own status vocabulary.
KNOWN_CONTEXT_STATUSES = (STATUS_SUGGESTED, STATUS_CONFIRMED, STATUS_NEEDS_REVIEW, STATUS_MANUAL)


def context_status_valid(status: str) -> bool:
    return status in KNOWN_CONTEXT_STATUSES


@dataclass(slots=True)
class EngineeringContextMember:
    """One channel's membership in one Engineering Context, PLUS its own
    durable phase identity. Deliberately a separate structure from
    `ChannelRef` itself (never a `phase` field bolted onto `ChannelRef`)
    -- `ChannelRef` is a stable identity reference reused unchanged
    across calculated-channel inputs and dependency graphs; phase is
    contextual engineering metadata about a channel's role WITHIN this
    one context, not part of the channel's own identity (owner
    instruction, canonical document section 5).

    `phase` is always one of `app.domain.phase_identity.KNOWN_PHASES`
    (defaults `PHASE_UNKNOWN` -- never guessed at construction time).
    `phase_source` records provenance (`engineer_confirmed`/`manual`/
    `structured_metadata`/`detected_from_name`/`unknown`), used to decide
    whether a later automatic re-detection may overwrite this value (see
    `phase_identity.may_overwrite_phase_assignment()`) -- never a
    numerical confidence score. `original_phase_label` preserves the
    engineer-facing/source-native label (e.g. "R", "L2") a canonical
    value was normalized from, purely for display -- resolver/matching
    logic must only ever compare `phase`, never this field.
    """

    channel_ref: ChannelRef
    phase: str = PHASE_UNKNOWN
    phase_source: str = PHASE_SOURCE_UNKNOWN
    original_phase_label: str | None = None


@dataclass(slots=True)
class EngineeringContext:
    """One Engineering Context -- identity, lifecycle status, and
    membership ONLY. No role/requirement/resolver logic lives here (a
    later slice).

    Workspace-scoped, deliberately with NO `source_id` field: a physical
    bay may legitimately span more than one uploaded source/file (owner's
    explicit correction to the original audit's source-scoped proposal --
    each member's own `ChannelRef` already carries its own `source_id`
    where relevant, so nothing here needs to assume, restrict, or imply
    single-source membership).

    `id` is a stable, opaque identity generated once at creation time by
    the service layer (`"ec-" + uuid4().hex`, mirroring
    `MeasurementGroup`'s own `"mg-" + uuid4().hex"` / `CalculatedChannel`'s
    own `"calc-" + uuid4().hex"` convention), never recomputed from
    mutable fields such as `display_name`.
    """

    id: str
    workspace_id: str
    display_name: str
    members: list[EngineeringContextMember] = field(default_factory=list)
    status: str = STATUS_MANUAL
    created_at: datetime | None = None


def context_channel_refs(context: EngineeringContext) -> list[ChannelRef]:
    return [member.channel_ref for member in context.members]


def member_for_channel_ref(context: EngineeringContext, channel_ref: ChannelRef) -> EngineeringContextMember | None:
    return next((m for m in context.members if m.channel_ref == channel_ref), None)


def validate_member_fields(member: EngineeringContextMember) -> None:
    """Pure structural validation -- does not touch workspace state (no
    channel-existence or engineering-type check here; that requires live
    workspace/registry data and lives in
    `app.services.engineering_context_service`, mirroring
    `app.domain.measurement_group`'s own domain/service split)."""
    if not phase_valid(member.phase):
        raise ValueError(f"Unknown phase {member.phase!r}.")
    if not phase_source_valid(member.phase_source):
        raise ValueError(f"Unknown phase source {member.phase_source!r}.")
