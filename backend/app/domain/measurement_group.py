"""Measurement Group domain model (Slice 1 of DEC-050's measurement-
group-aware Per-Unit redesign; see docs/project-memory/
PER_UNIT_MEASUREMENT_MODEL.md, especially section 4 ("Measurement Group
concept") and the domain-model sketch under section 18).

Slice 1 is internal scaffolding ONLY -- it introduces the
`source -> MeasurementGroup -> channel membership` foundation so a
later slice can attach group-specific Voltage/Current base
configuration (Slice 3/4) and group-aware PU resolution (Slice 5)
without a destructive redesign. This module deliberately does NOT
implement:

- any base-value/voltage-reference/current-base configuration (Slice
  3/4) -- a group here is pure identity + membership + lifecycle
  status, nothing else;
- any conversion math (`Vbase_phase = Vbase_LL / sqrt(3)`,
  `Ibase = Sbase / (sqrt(3) x Vbase)`) -- that stays entirely inside
  `app.domain.per_unit`, untouched by this module;
- automatic grouping/detection (Slice 2) -- every `MeasurementGroup` in
  this slice is created explicitly, by a caller that already knows its
  own `source_id`/`kind`/`channel_refs`, never by inspecting channel
  names.

The currently deployed DEC-049 source-wide Per-Unit configuration
(`app.domain.per_unit.PerUnitBaseProfile`, keyed 1:1 by `source_id`)
remains completely independent of this module and keeps operating
exactly as before -- the two concepts coexist deliberately during this
slice (section 13 of the canonical document); no migration between
them happens yet.

Group membership is restricted to real SOURCE channels only
(`ChannelRef(kind="source", ...)`) in this slice -- a calculated
channel is never a measurement-group member yet. Extending group
membership (or PU inheritance) to calculated channels is explicitly
Slice 7 scope (section 19 of the canonical document); admitting one
here now would blur that later decision, so a `ChannelRef` of kind
`"calculated"` is rejected outright (see `channel_ref_is_group_eligible`
below).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE

#: Group kinds. Deliberately a SEPARATE, lowercase vocabulary from
#: `app.domain.channel_classification`'s own `VOLTAGE`/`CURRENT`
#: engineering-type constants (which are capitalized channel-
#: classification labels, a different concept) -- see
#: `kind_for_engineering_type()` below for the one place that maps
#: between them. Per the canonical document's own section 4 scope,
#: Power/Frequency/ROCOF/Undefined channels have no group-kind
#: equivalent in this slice; do not add one speculatively.
KIND_VOLTAGE = "voltage"
KIND_CURRENT = "current"
KNOWN_GROUP_KINDS = (KIND_VOLTAGE, KIND_CURRENT)

_ENGINEERING_TYPE_TO_GROUP_KIND = {
    VOLTAGE: KIND_VOLTAGE,
    CURRENT: KIND_CURRENT,
}

#: Grouping-lifecycle statuses (canonical document section 7/15):
#: `suggested` (Slice 2's future auto-detection result, not yet
#: reviewed), `confirmed` (an engineer reviewed/configured/saved a
#: suggested group), `needs_review` (uncertain/contradictory automatic
#: evidence -- must never silently drive PU conversion once that exists),
#: `manual` (an engineer created this group directly, never via
#: detection -- the only status this slice's own tests/fixtures produce,
#: since Slice 2's detector does not exist yet). All four are modeled now
#: so Slice 2 does not need a destructive status-field redesign later.
STATUS_SUGGESTED = "suggested"
STATUS_CONFIRMED = "confirmed"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_MANUAL = "manual"
KNOWN_GROUP_STATUSES = (STATUS_SUGGESTED, STATUS_CONFIRMED, STATUS_NEEDS_REVIEW, STATUS_MANUAL)


def kind_for_engineering_type(engineering_type: str) -> str | None:
    """The measurement-group kind a channel of this engineering type is
    eligible for, or `None` if that type has no group-kind concept yet
    (Power/Frequency/ROCOF/Undefined -- Slice 1 scope is Voltage/Current
    only, canonical document section 4)."""
    return _ENGINEERING_TYPE_TO_GROUP_KIND.get(engineering_type)


def group_kind_valid(kind: str) -> bool:
    return kind in KNOWN_GROUP_KINDS


def group_status_valid(status: str) -> bool:
    return status in KNOWN_GROUP_STATUSES


def channel_ref_is_group_eligible(channel_ref: ChannelRef) -> bool:
    """Slice 1 scope restriction: only a real SOURCE channel may belong
    to a measurement group. A calculated channel is never eligible here
    -- see this module's own docstring and canonical document section
    19 (Slice 7 scope)."""
    return channel_ref.kind == "source"


def channel_ref_matches_source(source_id: str, channel_ref: ChannelRef) -> bool:
    """Same-source invariant (canonical document section 6/"Membership
    invariants"): a channel assigned to a group must belong to the exact
    same source as the group itself. Only meaningful for an
    already-group-eligible (source-kind) `channel_ref` -- callers should
    check `channel_ref_is_group_eligible()` first."""
    return channel_ref.source_id == source_id


def channel_kind_compatible(group_kind: str, channel_engineering_type: str) -> bool:
    """Engineering-type compatibility invariant: a Voltage group accepts
    only Voltage channels, a Current group accepts only Current
    channels -- never the other type, never an Undefined/Power/
    Frequency/ROCOF channel either (those simply have no compatible
    group kind at all in this slice, see `kind_for_engineering_type()`)."""
    return kind_for_engineering_type(channel_engineering_type) == group_kind


@dataclass(slots=True)
class MeasurementGroup:
    """One measurement group -- identity, ownership, kind, membership,
    and lifecycle status ONLY. No base configuration lives here yet
    (Slice 3/4); no conversion math reads this dataclass at all in this
    slice.

    `id` is a stable, opaque identity (never the `display_name`, never a
    channel label, never derived from a filename) -- generated once at
    creation time by the service layer (`"mg-" + uuid4().hex`, mirroring
    `CalculatedChannel`'s own `"calc-" + uuid4().hex` convention) and
    never recomputed from mutable fields.
    """

    id: str
    workspace_id: str
    source_id: str
    kind: str  # KIND_VOLTAGE | KIND_CURRENT
    display_name: str
    channel_refs: list[ChannelRef] = field(default_factory=list)
    status: str = STATUS_MANUAL
    created_at: datetime | None = None
