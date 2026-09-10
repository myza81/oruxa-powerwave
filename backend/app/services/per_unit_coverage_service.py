"""Per-Unit Settings hierarchy, Slice 2: source-level coverage read
model -- answers "how much of this recording is covered by Measurement
Groups, how much by Source Default, and how much is unresolved?"
without inventing a second implementation of DEC-051's own precedence
rule (see docs/project-memory/DECISIONS.md#dec-051).

This module is a pure, additive read model: it derives counts from
already-existing metadata and configuration state each request, exactly
like `app.services.measurement_group_view_service` derives its own
per-group `pu_status`. Nothing here is persisted, no registry is
mutated, and no waveform sample data is ever touched -- classification
only needs each channel's own already-parsed `AnalogChannelSummary`
(engineering_type/engineering_quantity) plus the same group/profile
registry reads the live display endpoints already perform per request.

**Classification must stay in lockstep with
`app.services.waveform_service._resolve_effective_per_unit()`** -- the
one seam every live per-unit-aware endpoint already dispatches through.
This module deliberately mirrors that exact dispatch order (Angle
guardrail first, then group-aware resolution, falling through to the
DEC-049 legacy resolver only when the channel is not a member of any
`MeasurementGroup`) using the SAME public building blocks that function
calls (`resolve_group_aware_per_unit()`, `resolve_per_unit()`) -- so the
actual precedence DECISION is never re-implemented here, only the
orchestration order is repeated. If that function's own dispatch order
ever changes, this module's `_classify_channel()` must change with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.channel_classification import (
    CURRENT,
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    VOLTAGE,
)
from app.domain.per_unit import STATUS_CONFIGURED, PerUnitBaseProfile, resolve_per_unit
from app.domain.source import AnalogChannelSummary
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import SourceNotFoundError
from app.services.group_aware_per_unit import resolve_group_aware_per_unit
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

#: Mutually exclusive coverage categories -- an applicable channel is
#: counted under exactly one of these three, never more than one and
#: never zero (a channel that is not applicable at all, per
#: `_classify_channel()` returning `None`, is excluded from every count
#: including `applicable_channel_count`).
CATEGORY_MEASUREMENT_GROUP = "measurement_group"
CATEGORY_SOURCE_DEFAULT = "source_default"
CATEGORY_NEEDS_CONFIGURATION = "needs_configuration"


@dataclass(slots=True)
class PerUnitCoverageSummary:
    """One source's own Per-Unit coverage breakdown -- derived fresh on
    every request, never stored. `applicable_channel_count` always
    equals the sum of the three category counts (locked in by this
    module's own tests)."""

    source_id: str
    applicable_channel_count: int
    measurement_group_count: int
    source_default_count: int
    needs_configuration_count: int


def _voltage_channel_names(analog_channels: list[AnalogChannelSummary]) -> list[str]:
    """Same derivation `app.api.v1.sources._voltage_channel_names_for_active()`
    already uses -- only consulted by the legacy DEC-049 resolver for a
    CURRENT channel under `current_base_mode == "derived"`."""
    return [ch.name for ch in analog_channels if ch.engineering_type == VOLTAGE]


def _classify_channel(
    channel: AnalogChannelSummary,
    *,
    workspace_id: str,
    source_id: str,
    per_unit_profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str],
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> str | None:
    """Returns one of the three `CATEGORY_*` constants, or `None` when
    this channel is not applicable to Per-Unit at all (not a Voltage/
    Current channel, or an Angle-quantity channel -- DEC-078's own
    guardrail, mirrored here exactly since group membership alone does
    not exclude an Angle channel: `measurement_group.channel_kind_compatible()`
    only checks the broad `engineering_type`, never `engineering_quantity`)."""
    if channel.engineering_type not in (VOLTAGE, CURRENT):
        return None
    if channel.engineering_quantity in (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, ENGINEERING_QUANTITY_CURRENT_ANGLE):
        return None

    group_resolution = resolve_group_aware_per_unit(
        workspace_id=workspace_id,
        source_id=source_id,
        channel_name=channel.name,
        engineering_type=channel.engineering_type,
        group_registry=group_registry,
        voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    if group_resolution is not None:
        # DEC-051: a grouped channel's Measurement Group resolution is
        # final -- an incomplete group configuration is
        # `needs_configuration`, never a silent fall-through to Source
        # Default (canonical document section 21's own "never silently
        # borrow another base" principle).
        return CATEGORY_MEASUREMENT_GROUP if group_resolution.status == STATUS_CONFIGURED else CATEGORY_NEEDS_CONFIGURATION

    legacy_resolution = resolve_per_unit(channel.engineering_type, per_unit_profile, voltage_channel_names)
    return CATEGORY_SOURCE_DEFAULT if legacy_resolution.status == STATUS_CONFIGURED else CATEGORY_NEEDS_CONFIGURATION


def build_per_unit_coverage_summary(
    *,
    workspace_id: str,
    source_id: str,
    source_registry: WorkspaceRegistry,
    per_unit_registry: PerUnitRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> PerUnitCoverageSummary:
    """The one entry point `app.api.v1.per_unit`'s coverage endpoint
    calls. Raises `SourceNotFoundError` for an unknown `source_id`,
    mirroring `app.services.per_unit_service.get_source_per_unit_config()`'s
    own exact validation shape. Digital channels are structurally
    excluded (only `active.metadata.analog_channels` is ever iterated);
    no waveform sample array is read."""
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")

    per_unit_profile = per_unit_registry.get(workspace_id, source_id)
    voltage_channel_names = _voltage_channel_names(active.metadata.analog_channels)

    counts = {CATEGORY_MEASUREMENT_GROUP: 0, CATEGORY_SOURCE_DEFAULT: 0, CATEGORY_NEEDS_CONFIGURATION: 0}
    applicable_count = 0
    for channel in active.metadata.analog_channels:
        category = _classify_channel(
            channel,
            workspace_id=workspace_id,
            source_id=source_id,
            per_unit_profile=per_unit_profile,
            voltage_channel_names=voltage_channel_names,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        if category is None:
            continue
        applicable_count += 1
        counts[category] += 1

    return PerUnitCoverageSummary(
        source_id=source_id,
        applicable_channel_count=applicable_count,
        measurement_group_count=counts[CATEGORY_MEASUREMENT_GROUP],
        source_default_count=counts[CATEGORY_SOURCE_DEFAULT],
        needs_configuration_count=counts[CATEGORY_NEEDS_CONFIGURATION],
    )
