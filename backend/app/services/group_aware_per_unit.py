"""Group-aware Per-Unit resolution bridge for live display endpoints
(DEC-050 Slice 5; see docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md
section 21/24).

This is the ONLY new piece of production wiring Slice 5 introduces. It
deliberately does not reimplement any conversion math -- it resolves a
`ChannelRef`'s owning `MeasurementGroup` (Slice 1), delegates to the
already-proven, already-tested pure domain resolvers
(`voltage_group_config.resolve_voltage_base_for_group`, Slice 3;
`current_group_config.resolve_current_base_for_group`, Slice 4), and
adapts the result into `app.domain.per_unit.PerUnitResolution` -- the
SAME shape `app.services.waveform_service`'s existing DEC-049 source-
wide path already produces. This is what lets
`per_unit.apply_per_unit_to_value()`/`apply_per_unit_to_array()` --
unchanged, not touched by this module -- consume either resolution
identically, with zero duplicated conversion/unit-normalization logic.

`PerUnitResolution.profile_id` is repurposed here to carry a
`measurement_group_id` instead of a `source_id` -- this is safe: no API
response schema exposes `profile_id` (only `.status`, surfaced as
`per_unit_status`), and no calculated-channel inheritance code (Slice 7
scope, untouched) ever sees a resolution produced by this module.

**DEC-049 / DEC-050 coexistence precedence (recorded as DEC-051 --
see docs/project-memory/DECISIONS.md)**: `resolve_group_aware_per_unit()`
returns `None` when a channel is NOT a member of any `MeasurementGroup`
-- the caller MUST then fall back to the existing DEC-049 source-wide
resolution entirely unchanged (this is the backwards-compatibility path
for every channel/workspace that predates, or never uses, Slice 1-4
grouping). Once a channel IS grouped, this module's own result --
`configured` or `base_required`, whichever the group's own configuration
resolves to -- is authoritative for that channel; DEC-049's source-wide
profile is never additionally consulted for it, and never silently
overrides it. A grouped channel therefore never falls back to a
source-wide number merely because its OWN group's configuration is
incomplete -- see `PER_UNIT_MEASUREMENT_MODEL.md` section 21's own
"never silently borrow another group's/source's base" principle.

Group/config resolution happens exactly ONCE per requested channel per
request (three registry lookups: the group, its own kind-specific
config, and -- only for an equipment-rating Current group with a link
-- the linked Voltage group's own config) -- never per sample, and
never invoking Slice 2's grouping detector (this module only ever
READS already-persisted group/config state).

`resolve_per_unit_for_group()` below is the shared kind-dispatch core
(source `MeasurementGroup` -> `PerUnitResolution`), factored out so
DEC-050 Slice 7's calculated-channel inheritance
(`app.services.calculated_group_aware_per_unit`) can reuse it once a
calculated channel's own inherited `measurement_group_id` has been
derived, without duplicating the Voltage/Current config-resolution
logic here a second time (see that module's own docstring).
"""

from __future__ import annotations

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.current_group_config import (
    METHOD_EQUIPMENT_RATING,
    STATUS_CONFIGURED as _CURRENT_STATUS_CONFIGURED,
    resolve_current_base_for_group,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, MeasurementGroup
from app.domain.per_unit import STATUS_BASE_REQUIRED, STATUS_CONFIGURED, PerUnitResolution
from app.domain.voltage_group_config import STATUS_CONFIGURED as _VOLTAGE_STATUS_CONFIGURED, resolve_voltage_base_for_group
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry


def resolve_per_unit_for_group(
    group: MeasurementGroup,
    measurement_group_id: str,
    *,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> PerUnitResolution:
    """Resolves an already-identified `MeasurementGroup` to a
    `PerUnitResolution` -- the kind-dispatch core shared by
    `resolve_group_aware_per_unit()` (source channels, below) and
    `app.services.calculated_group_aware_per_unit` (Slice 7, calculated
    channels). Callers are responsible for having already established
    that `group` is the correct, unambiguous group for whatever channel
    they are resolving -- this function performs no membership lookup
    of its own."""
    if group.kind == KIND_VOLTAGE:
        config = voltage_config_registry.get(group.workspace_id, measurement_group_id)
        resolution = resolve_voltage_base_for_group(group, config)
        if resolution.status == _VOLTAGE_STATUS_CONFIGURED:
            return PerUnitResolution(
                status=STATUS_CONFIGURED,
                profile_id=measurement_group_id,
                base_amount=resolution.denominator_kv * 1000.0,
                base_unit="V",
                reason=None,
            )
        return PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id=measurement_group_id, base_amount=None, base_unit=None,
            reason=resolution.reason,
        )

    if group.kind == KIND_CURRENT:
        current_config = current_config_registry.get(group.workspace_id, measurement_group_id)
        linked_voltage_group = None
        linked_voltage_config = None
        if (
            current_config is not None
            and current_config.method == METHOD_EQUIPMENT_RATING
            and current_config.linked_voltage_group_id is not None
        ):
            linked_voltage_group = group_registry.get(group.workspace_id, current_config.linked_voltage_group_id)
            linked_voltage_config = voltage_config_registry.get(group.workspace_id, current_config.linked_voltage_group_id)
        resolution = resolve_current_base_for_group(
            group, current_config, linked_voltage_group=linked_voltage_group, linked_voltage_config=linked_voltage_config
        )
        if resolution.status == _CURRENT_STATUS_CONFIGURED:
            return PerUnitResolution(
                status=STATUS_CONFIGURED,
                profile_id=measurement_group_id,
                base_amount=resolution.ibase_ka * 1000.0,
                base_unit="A",
                reason=None,
            )
        return PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id=measurement_group_id, base_amount=None, base_unit=None,
            reason=resolution.reason,
        )

    # A Voltage/Current-typed channel assigned to a group of some other
    # kind is structurally impossible -- channel_kind_compatible() is
    # enforced at group-membership time (Slice 1) -- defensive only.
    return PerUnitResolution(
        status=STATUS_BASE_REQUIRED, profile_id=measurement_group_id, base_amount=None, base_unit=None,
        reason="group_kind_mismatch",
    )


def resolve_group_aware_per_unit(
    *,
    workspace_id: str,
    source_id: str,
    channel_name: str,
    engineering_type: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> PerUnitResolution | None:
    """Returns `None` when this channel is not a member of any
    `MeasurementGroup` -- see module docstring for why the caller must
    then use the existing DEC-049 source-wide resolution unchanged, and
    must never blend the two for the same channel.

    An engineering type other than Voltage/Current never performs a
    registry lookup at all and returns `None` immediately -- the
    existing DEC-049 `resolve_per_unit()` already correctly reports
    `not_applicable` for every such type (Power/Frequency/ROCOF/
    Undefined), and this module must never extend DEC-050 group bases
    into those types (canonical document section 4 scope)."""
    if engineering_type not in (VOLTAGE, CURRENT):
        return None

    channel_ref = ChannelRef(kind="source", source_id=source_id, channel_name=channel_name)
    measurement_group_id = group_registry.group_for_channel(workspace_id, channel_ref)
    if measurement_group_id is None:
        return None
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        # Defensive only: a stale reverse-index entry pointing at a
        # group that no longer exists should be structurally
        # impossible (MeasurementGroupRegistry keeps both in lockstep),
        # but resolving as "ungrouped" here is the safe degradation --
        # never a guessed base.
        return None

    return resolve_per_unit_for_group(
        group, measurement_group_id, group_registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )
