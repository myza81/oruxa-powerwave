"""PC-001 automatic Current bases, resolved live from all contributing leaves.

No inherited bases are persisted. Compare global extrema (not intermediate
representatives) with relative tolerance 1e-12 and zero absolute tolerance.
The minimum equivalent SI base is a deterministic, order-independent denominator.
"""
from dataclasses import dataclass, replace

from app.domain.calculated_channel import MULTI_OPERATIONS, UNARY_OPERATIONS, OP_ROCOF, CalculatedChannel
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT
from app.domain.per_unit import (
    STATUS_BASE_REQUIRED, STATUS_CONFIGURED, PerUnitResolution,
    resolve_conversion_eligibility, resolve_per_unit,
)
from app.domain.reference_side import configured_base_side
from app.services.group_aware_per_unit import resolve_per_unit_for_group

COMMON_BASE_RTOL = 1e-12
CURRENT_REASON_COPY = {
    "current_bases_differ": "Contributing current bases differ; no common automatic base is available.",
    "current_reference_side_unknown": "Contributing measurement or current-base reference side is unknown.",
    "current_reference_side_incompatible": "Contributing measurement and current-base reference sides are incompatible.",
    "current_secondary_reference_unestablished": "A shared secondary current reference is not established for automatic cross-authority conversion.",
    "current_dependency_unavailable": "A contributing Current dependency is missing, cyclic or incompatible.",
}


@dataclass(frozen=True, slots=True)
class CurrentInheritance:
    resolution: PerUnitResolution
    source_kind: str | None
    measurement_side: str
    base_reference_side: str


def resolve_calculated_current_per_unit(*, workspace_id, channel: CalculatedChannel,
                                      source_registry, per_unit_registry, calc_registry,
                                      group_registry, voltage_config_registry, current_config_registry) -> CurrentInheritance | None:
    leaves = {}
    visited, visiting = set(), set()
    legacy_manual = False

    def visit(node):
        nonlocal legacy_manual
        if node.id in visiting:
            return False
        if node.id in visited:
            return True
        if node.engineering_type != CURRENT or node.operation not in (UNARY_OPERATIONS | MULTI_OPERATIONS) - {OP_ROCOF}:
            return False
        if (node.operation in UNARY_OPERATIONS and len(node.inputs) != 1) or (node.operation in MULTI_OPERATIONS and len(node.inputs) < 2):
            return False
        visiting.add(node.id)
        legacy_manual |= per_unit_registry.assignment_mode_for_calculated_channel(workspace_id, node.id) == "manual"
        for ref in node.inputs:
            if ref.kind == "source":
                leaves[(ref.source_id, ref.channel_name)] = ref
            else:
                parent = calc_registry.get(workspace_id, ref.calculated_channel_id)
                if parent is None or not visit(parent):
                    return False
        visiting.remove(node.id)
        visited.add(node.id)
        return True

    def unavailable(reason, kind=None, identity=None, measurement="unknown", base_side="unknown"):
        return CurrentInheritance(
            PerUnitResolution(STATUS_BASE_REQUIRED, identity, None, None, reason), kind, measurement, base_side)

    if not visit(channel) or not leaves:
        return unavailable("current_dependency_unavailable")
    if legacy_manual:
        # Stage 5A is automatic only. Preserve the existing internal assignment
        # contract; making it an engineer-facing result override is Stage 5B.
        return None
    contributors = []
    for (source_id, name), ref in leaves.items():
        active = source_registry.get(workspace_id, source_id)
        metadata = next((ch for ch in active.metadata.analog_channels if ch.name == name), None) if active else None
        if metadata is None or metadata.engineering_type != CURRENT or name not in active.record.waveform_data:
            return unavailable("current_dependency_unavailable")
        group_id = group_registry.group_for_channel(workspace_id, ref)
        if group_id is not None:
            kind, identity = "measurement_group", group_id
            group = group_registry.get(workspace_id, group_id)
            if group is None or group.kind != KIND_CURRENT:
                return unavailable("current_dependency_unavailable", kind, identity)
            config = current_config_registry.get(workspace_id, group_id)
            side = configured_base_side(config.method, config.base_reference_side) if config else "unknown"
            resolution = resolve_per_unit_for_group(
                group, group_id, group_registry=group_registry,
                voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry)
        else:
            kind, identity = "source_default", source_id
            profile = per_unit_registry.get(workspace_id, source_id)
            side = configured_base_side(profile.current_base_mode, profile.current_base_reference_side) if profile else "unknown"
            resolution = resolve_per_unit(CURRENT, profile, [ch.name for ch in active.metadata.analog_channels if ch.engineering_type == VOLTAGE])
        # Validate input units/bases, not normalized input arrays: arithmetic is
        # physical ENG first. Only the actual final result needs PU range checks
        # (large opposing inputs can legitimately produce a representable zero).
        resolution = resolve_conversion_eligibility(resolution, metadata.unit, CURRENT)
        contributors.append(((kind, identity), resolution, metadata.measurement_side, side))

    authorities = {c[0] for c in contributors}
    kind, identity = next(iter(authorities)) if len(authorities) == 1 else (None, None)
    sample_sides, base_sides = {c[2] for c in contributors}, {c[3] for c in contributors}
    measurement = next(iter(sample_sides)) if len(sample_sides) == 1 else "unknown"
    base_side = next(iter(base_sides)) if len(base_sides) == 1 else "unknown"
    for _, resolution, _, _ in contributors:
        if resolution.status != STATUS_CONFIGURED:
            if kind is not None:
                return CurrentInheritance(replace(resolution, profile_id=identity), kind, measurement, base_side)
            return unavailable(resolution.reason, kind, identity, measurement, base_side)
    bases = [c[1].base_amount for c in contributors]
    smallest, largest = min(bases), max(bases)
    # Division avoids underflow of rtol * largest for subnormal SI bases.
    if (largest - smallest) / largest > COMMON_BASE_RTOL:
        return unavailable("current_bases_differ", kind, identity, measurement, base_side)
    if len(authorities) > 1:
        if "unknown" in sample_sides or "unknown" in base_sides:
            return unavailable("current_reference_side_unknown", measurement=measurement, base_side=base_side)
        if sample_sides != base_sides or len(sample_sides) != 1:
            return unavailable("current_reference_side_incompatible", measurement=measurement, base_side=base_side)
        if sample_sides == {"secondary"}:
            return unavailable("current_secondary_reference_unestablished", measurement=measurement, base_side=base_side)
    resolution = resolve_conversion_eligibility(
        PerUnitResolution(STATUS_CONFIGURED, identity, smallest, "A", None), channel.unit, CURRENT, channel.values)
    return CurrentInheritance(resolution, kind, measurement, base_side)
