"""Group-aware Per-Unit resolution bridge for calculated-channel display
endpoints (DEC-050 Slice 7; see
docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md section 19/24, and
DEC-050's own Slice 7 scope note: "the existing source-level
`derive_per_unit_profile_id()` rule shape, confirmed as the correct
starting point extended from `source_id` to `measurement_group_id` --
no new inheritance algorithm needs inventing").

Calculated channels are deliberately NOT added as `MeasurementGroup`
members (see `app.services.measurement_group_registry`'s own
docstring -- group membership is source-channels-only). A calculated
channel's inherited group context is therefore always DERIVED, at
resolution time, by walking its own `inputs: list[ChannelRef]` --
never persisted onto the channel or the registry as a shortcut, so it
can never go stale the way a cached value could.

**Inheritance rule** (`resolve_inherited_measurement_group_id()`):
reuses `app.domain.per_unit.derive_per_unit_profile_id()` UNCHANGED,
keyed on `measurement_group_id` instead of `source_id` -- the exact
same shape DEC-049 already uses one level up (unary operations inherit
their single input's id verbatim, including `None`; Addition/
Subtraction inherit only when every input resolves to the identical
known id, otherwise `None`). A `"calculated"`-kind input recurses into
this same function on that input's own already-stored `CalculatedChannel`
(reading its `inputs` again), so the rule composes transitively through
arbitrarily deep calculated-on-calculated chains with no separate
recursive algorithm -- mirroring exactly how DEC-049's own
`derive_per_unit_profile_id()` already composes through such chains at
the source-id level (see `calculated_channel_service.create_calculated_channel`).
Per-request memoization (`_cache`) avoids recomputing a shared ancestor
more than once when several calculated channels share upstream inputs
in one request; the existing `would_create_cycle()` guard at
calculated-channel CREATION time already makes a real dependency cycle
structurally impossible here, so no separate cycle detection is added.

**Quantity/reference compatibility gate**
(`resolve_calculated_group_aware_per_unit()`): even once an inherited
`measurement_group_id` is found, inheritance is refused unless BOTH:

1. the calculated channel's own resolved `engineering_type` is Voltage
   or Current, and matches the inherited group's own `kind` (every
   other type -- Power/Frequency/ROCOF/Undefined -- is excluded, and
   no such operation exists in this codebase today: every supported
   operation -- reverse polarity, absolute value, multiply-by-constant,
   RMS, addition, subtraction -- inherits its unit/engineering_type
   verbatim from its input(s); there is no V x I / V / I operation to
   ever produce a different physical dimension);
2. for a MULTI-input operation (Addition/Subtraction) whose inherited
   group is `KIND_VOLTAGE`, inheritance is refused unconditionally,
   REGARDLESS of unanimous group agreement. Reason: this codebase has
   no metadata anywhere distinguishing a Voltage measurement group's
   own phase-to-ground vs. phase-to-phase reference from the physical
   reference an Addition/Subtraction of two of that group's own
   channels actually produces (e.g. `VR - VY` on a phase-to-ground
   group is numerically a phase-to-phase quantity, but the group's own
   resolved denominator remains phase-to-ground -- dividing the former
   by the latter would silently produce a wrong PU value, not merely a
   missing one). No canonical document resolves this, and this module
   deliberately does not invent the resolution -- per the task's own
   "prefer a conservative allowlist over clever inference" guidance,
   Voltage multi-input arithmetic simply never inherits, and resolves
   `base_required` like any other ambiguous case. A Current group has
   no such reference-frame concept (Ibase is a single scalar regardless
   of phase), so Current multi-input arithmetic (`IR + IY`, etc.) is
   not affected by this restriction. Unary operations on a Voltage
   group (`-VR`, `abs(VR)`, `VR * k`, `RMS(VR)`) are unaffected too --
   none of them can change which physical reference the result
   represents. This restriction is flagged for owner review (a possible
   future DEC) rather than treated as a permanent architectural limit --
   see the implementation report for this slice.

Returns `None` whenever no unambiguous, compatible group context
exists (ungrouped inputs, cross-group, cross-source, wrong/undefined
engineering type, the Voltage-multi-input restriction above, or the
inherited group itself no longer exists) -- the caller MUST then fall
back to the EXISTING DEC-049 per-calculated-channel-profile resolution
entirely unchanged, mirroring DEC-051's own source-channel precedence
one layer up (see `app.services.group_aware_per_unit`'s own module
docstring). Once a calculated channel's inherited group IS unambiguous
and compatible, this module's own result -- `configured` or
`base_required`, whichever the group's own configuration resolves to --
is authoritative for it; DEC-049's calculated-channel profile is never
additionally consulted for it, and never silently overrides it.
"""

from __future__ import annotations

from app.domain.calculated_channel import MULTI_OPERATIONS, CalculatedChannel
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.domain.per_unit import PerUnitResolution, derive_per_unit_profile_id
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.group_aware_per_unit import resolve_per_unit_for_group
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry

_ENGINEERING_TYPE_TO_GROUP_KIND = {VOLTAGE: KIND_VOLTAGE, CURRENT: KIND_CURRENT}


def resolve_inherited_measurement_group_id(
    workspace_id: str,
    channel: CalculatedChannel,
    *,
    calc_registry: CalculatedChannelRegistry,
    group_registry: MeasurementGroupRegistry,
    _cache: dict[str, str | None] | None = None,
) -> str | None:
    """Derives `channel`'s own inherited `measurement_group_id`, or
    `None` if no single unambiguous group context exists across its
    inputs. See module docstring for the exact rule. Never persists
    anything -- purely a read-time derivation over already-stored
    `ChannelRef`/`CalculatedChannel` state."""
    if _cache is None:
        _cache = {}
    if channel.id in _cache:
        return _cache[channel.id]

    input_group_ids: list[str | None] = []
    for ref in channel.inputs:
        if ref.kind == "source":
            input_group_ids.append(group_registry.group_for_channel(workspace_id, ref))
        else:
            input_channel = calc_registry.get(workspace_id, ref.calculated_channel_id)
            input_group_ids.append(
                resolve_inherited_measurement_group_id(
                    workspace_id, input_channel, calc_registry=calc_registry, group_registry=group_registry, _cache=_cache
                )
                if input_channel is not None
                else None
            )

    result = derive_per_unit_profile_id(channel.operation, input_group_ids)
    _cache[channel.id] = result
    return result


def resolve_calculated_group_aware_per_unit(
    *,
    workspace_id: str,
    channel: CalculatedChannel,
    calc_registry: CalculatedChannelRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> PerUnitResolution | None:
    """Returns `None` when `channel` has no unambiguous, quantity-
    compatible inherited `MeasurementGroup` -- see module docstring for
    why the caller must then fall back to the existing DEC-049
    calculated-channel resolution unchanged."""
    expected_kind = _ENGINEERING_TYPE_TO_GROUP_KIND.get(channel.engineering_type)
    if expected_kind is None:
        return None

    measurement_group_id = resolve_inherited_measurement_group_id(
        workspace_id, channel, calc_registry=calc_registry, group_registry=group_registry
    )
    if measurement_group_id is None:
        return None
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        # Defensive only: the inherited id came from a source channel's
        # own reverse-index entry (or transitively from one), which
        # MeasurementGroupRegistry keeps in lockstep with its stored
        # groups -- see resolve_group_aware_per_unit's own identical
        # defensive comment.
        return None
    if group.kind != expected_kind:
        # Structurally impossible under current invariants (group
        # membership is kind-gated, and derive_engineering_type()
        # requires every input to share one known type for a multi-op
        # result to be classified at all) -- defensive only.
        return None
    if channel.operation in MULTI_OPERATIONS and group.kind == KIND_VOLTAGE:
        return None

    return resolve_per_unit_for_group(
        group, measurement_group_id, group_registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )
