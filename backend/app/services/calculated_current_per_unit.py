"""PC-001 automatic Current bases, resolved live from all contributing leaves.

No inherited bases are persisted. Compare global extrema (not intermediate
representatives) with relative tolerance 1e-12 and zero absolute tolerance.
The minimum equivalent SI base is a deterministic, order-independent denominator.
"""
from dataclasses import dataclass, replace

from app.domain.calculated_channel import MULTI_OPERATIONS, UNARY_OPERATIONS, OP_ROCOF, CalculatedChannel
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.calculated_current_config import CalculatedCurrentConfiguration
from app.domain.current_group_config import AUTHORITATIVE_GROUP_STATUSES
from app.domain.measurement_group import KIND_CURRENT
from app.domain.per_unit import (
    STATUS_BASE_REQUIRED, STATUS_CONFIGURED, PerUnitResolution,
    resolve_conversion_eligibility, resolve_per_unit,
)
from app.domain.reference_side import configured_base_side
from app.domain.per_unit_reference import (
    BLOCKED,
    REASON_BASE_NOT_REPRESENTABLE,
    REASON_CURRENT_SIDE_INCOMPATIBLE,
    VERIFIED_CONVERTED,
    VERIFIED_DIRECT,
    RawVoltageSideInputs,
    SideProvenance,
    apply_current_reference,
    place_current_base,
    qualify_historical,
)
from app.domain.side_denominator import (
    BASE_RESULT_MANUAL,
    PROBLEM_UNRESOLVED,
    REASON_CT_AUTHORITY_UNAVAILABLE,
    REASON_DENOMINATOR_NOT_REPRESENTABLE,
    REASON_INVALID_BASE_VALUE,
    RATIO_NO_GROUP,
    SIDE_PRIMARY,
    SIDE_SECONDARY,
    SampleSide,
    SideBase,
    SideRatio,
)
from app.services.group_aware_per_unit import resolve_per_unit_for_group
from app.services.calculated_group_aware_per_unit import resolve_calculated_group_aware_per_unit
from app.services.per_unit_side_authority import raw_current_side_inputs
from app.services.protection_instrument_context import QUANTITY_CURRENT as CT_QUANTITY, resolve_transformer_context
from app.services.recorded_side_authority import RecordedAuthority

COMMON_BASE_RTOL = 1e-12
CURRENT_REASON_COPY = {
    "current_bases_differ": "Contributing current bases differ; no common automatic base is available.",
    "current_reference_side_unknown": "Contributing measurement or current-base reference side is unknown.",
    "current_reference_side_incompatible": "Contributing measurement and current-base reference sides are incompatible.",
    "current_secondary_reference_unestablished": "A shared secondary current reference is not established for automatic cross-authority conversion.",
    "current_dependency_unavailable": "A contributing Current dependency is missing, cyclic or incompatible.",
    "current_explicit_unassigned": "This calculated result is explicitly unassigned; return to Automatic to resume automatic resolution.",
    "current_group_unconfirmed": "A contributing Current Measurement Group requires confirmation.",
}


@dataclass(frozen=True, slots=True)
class CurrentInheritance:
    resolution: PerUnitResolution
    source_kind: str | None
    measurement_side: str
    base_reference_side: str
    resolution_origin: str | None = None
    configuration_mode: str = "automatic"
    configured_current_base_amps: float | None = None


def _strict_common_base(contributors, *, authorities, identity, workspace_id, side_authority):
    """S4 (K-1..K-3): the common denominator of a calculated Current result, in the leaves' strict sample side.

    Returns None whenever the historical gate must decide (a leaf whose side is not strict-usable, a base whose side is not declared --
    never assumed Primary --, leaves on different sides, or a Secondary result across several CT authorities (K-2)): those keep today's
    numbers, labelled, or today's refusals. Otherwise the S1 resolver places every contributor's base on that side (a conversion reads
    the CT of the one Measurement Group that owns the base, else it is refused) and the denominators (not the bases, C-8) are compared (K-3)."""
    samples = [c[4] for c in contributors]
    descriptors = [c[5] for c in contributors]
    if any(s.problem is not None for s in samples) or any(d is None or d.declared_side not in (SIDE_PRIMARY, SIDE_SECONDARY) for d in descriptors):
        return None
    sides = {s.side for s in samples}
    if len(sides) != 1:
        return None
    side = next(iter(sides))
    if side == SIDE_SECONDARY and len(authorities) > 1:
        return None
    single_group = next(iter(authorities))[1] if len(authorities) == 1 and next(iter(authorities))[0] == "measurement_group" else None
    ratio_cache: list[SideRatio] = []

    def ratio_for() -> SideRatio:
        if single_group is None:
            # A conversion needs exactly one Measurement Group to read a CT from; a Source Default, or leaves of several groups, have
            # none -- the established `current_reference_side_incompatible` refusal, now with the resolver's own code and detail.
            return SideRatio(status=RATIO_NO_GROUP)
        if not ratio_cache:
            context = resolve_transformer_context(
                workspace_id, tuple(c[6] for c in contributors), CT_QUANTITY,
                group_registry=side_authority.side.group_registry, voltage_config_registry=side_authority.voltage_config_registry,
                current_config_registry=side_authority.current_config_registry, source_registry=side_authority.side.source_registry,
            )
            ratio_cache.append(
                SideRatio(status=RATIO_NO_GROUP, group_ids=tuple(context.group_ids)) if tuple(context.group_ids) != (single_group,)
                else SideRatio(status=context.ratio_status, value=context.ratio, authority=context.authority, group_ids=context.group_ids))
        return ratio_cache[0]

    results = [
        place_current_base(d, SampleSide(side=side, problem=None, authority=s.authority), ratio_for)
        for s, d in zip(samples, descriptors)
    ]
    declared = {d.declared_side for d in descriptors}
    base_side = next(iter(declared)) if len(declared) == 1 else "unknown"
    first = results[0]
    refused = next((r for r in results if not r.resolved), None)
    provenance = SideProvenance(
        verification_state=BLOCKED, effective_side=side, side_authority=samples[0].authority, base_kind=descriptors[0].kind,
        base_side=base_side)
    if refused is not None:
        if refused.reason == REASON_CT_AUTHORITY_UNAVAILABLE:
            reason, compatibility = REASON_CURRENT_SIDE_INCOMPATIBLE, "incompatible"
        elif refused.reason in (REASON_DENOMINATOR_NOT_REPRESENTABLE, REASON_INVALID_BASE_VALUE):
            reason, compatibility = REASON_BASE_NOT_REPRESENTABLE, "compatible"
        else:
            reason, compatibility = refused.reason, "unverified"
        return PerUnitResolution(
            STATUS_BASE_REQUIRED, None, None, None, reason, reference_compatibility=compatibility, measurement_side=side,
            base_reference_side=base_side, side_provenance=replace(provenance, refusal_reason=refused.reason, refusal_detail=refused.detail))
    amounts = [r.denominator for r in results]
    smallest, largest = min(amounts), max(amounts)
    if (largest - smallest) / largest > COMMON_BASE_RTOL:
        return PerUnitResolution(
            STATUS_BASE_REQUIRED, None, None, None, "current_bases_differ", reference_compatibility="compatible", measurement_side=side,
            base_reference_side=base_side, side_provenance=replace(provenance, refusal_reason="current_bases_differ"))
    direct = first.ratio_applied is None
    return PerUnitResolution(
        STATUS_CONFIGURED, identity, smallest, "A", None,
        reference_compatibility="compatible", measurement_side=side, base_reference_side=base_side,
        side_provenance=replace(
            provenance, verification_state=VERIFIED_DIRECT if direct else VERIFIED_CONVERTED, conversion=first.conversion,
            ratio_applied=first.ratio_applied, ratio_authority=first.ratio_authority, ratio_group_ids=first.ratio_group_ids,
            denominator_side=first.denominator_side))


def resolve_calculated_current_per_unit(*, workspace_id, channel: CalculatedChannel,
                                      source_registry, per_unit_registry, calc_registry,
                                      group_registry, voltage_config_registry, current_config_registry,
                                      candidate_configuration: CalculatedCurrentConfiguration | None = None,
                                      side_authority: RecordedAuthority | None = None) -> CurrentInheritance | None:
    """PU-MIG S4: the calculated-Current inheritance, with Recording Details' side and the CT authority when the caller has them.
    Without `side_authority` it is exactly the historical resolution (raw leaf flags, base-amount comparison)."""
    trace: dict = {}
    inherited = _resolve_calculated_current(
        workspace_id=workspace_id, channel=channel, source_registry=source_registry, per_unit_registry=per_unit_registry,
        calc_registry=calc_registry, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry, candidate_configuration=candidate_configuration,
        side_authority=side_authority, trace=trace)
    if inherited is None or side_authority is None or inherited.resolution.side_provenance is not None or not trace.get("complete"):
        return inherited
    # D-1 (R+): whatever the historical gate decided is kept bit-for-bit and explicitly qualified.
    resolution = inherited.resolution
    if resolution.status != STATUS_CONFIGURED and resolution.reason in ("current_dependency_unavailable", "current_explicit_unassigned"):
        return inherited
    strict = trace["strict_side"] is not None
    aggregate = SampleSide(side=trace["strict_side"], problem=None if strict else trace["problem"], authority=trace["authority"])
    qualified = qualify_historical(
        resolution, RawVoltageSideInputs(sample=aggregate, ratio_for=lambda: None), strict=strict,
        base_side=inherited.base_reference_side)
    return replace(inherited, resolution=qualified)


def _resolve_calculated_current(*, workspace_id, channel: CalculatedChannel,
                                source_registry, per_unit_registry, calc_registry,
                                group_registry, voltage_config_registry, current_config_registry,
                                candidate_configuration, side_authority, trace) -> CurrentInheritance | None:
    configuration = candidate_configuration or per_unit_registry.current_configuration_for_calculated_channel(workspace_id, channel.id)
    manual = configuration is not None and configuration.mode == "manual"
    origin = "manual_calculated_current" if manual else None
    if configuration is not None and configuration.mode == "unassigned":
        return CurrentInheritance(
            PerUnitResolution(STATUS_BASE_REQUIRED, None, None, None, "current_explicit_unassigned"),
            None, "unknown", "unknown", "explicit_unassigned", "unassigned")
    leaves = {}
    visited, visiting = set(), set()
    legacy_manual = False
    sample_sides, base_sides, authorities = {"unknown"}, {"unknown"}, set()

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
        legacy_manual |= (per_unit_registry.assignment_mode_for_calculated_channel(workspace_id, node.id) == "manual"
                          and per_unit_registry.current_configuration_for_calculated_channel(workspace_id, node.id) is None)
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
        if manual:
            kind, identity, base_side = None, None, configuration.base_reference_side
        return CurrentInheritance(
            apply_current_reference(PerUnitResolution(STATUS_BASE_REQUIRED, identity, None, None, reason),
                                    sample_sides, base_sides, strict=manual or len(authorities) > 1,
                                    cross_authority=len(authorities) > 1), kind, measurement, base_side,
            origin, "manual" if manual else "automatic", configuration.current_base_amps if manual else None)

    if not visit(channel) or not leaves:
        return unavailable("current_dependency_unavailable")
    contributors = []
    side_cache: dict[tuple[str, str], bool] = {}
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
            if manual and group.status not in AUTHORITATIVE_GROUP_STATUSES:
                return unavailable("current_group_unconfirmed", measurement=metadata.measurement_side,
                                   base_side=configuration.base_reference_side)
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
        descriptor = resolution.base_descriptor
        if manual:
            # An explicit result base replaces input normalization bases, never
            # their physical samples, measured-unit or group review requirements.
            resolution = PerUnitResolution(STATUS_CONFIGURED, None, configuration.current_base_amps, "A", None)
            side = configuration.base_reference_side
            descriptor = SideBase(kind=BASE_RESULT_MANUAL, value=configuration.current_base_amps, declared_side=side)
        resolution = resolve_conversion_eligibility(resolution, metadata.unit, CURRENT)
        sample = (
            raw_current_side_inputs(workspace_id, source_id, name, authority=side_authority, group_status_cache=side_cache).sample
            if side_authority is not None else None
        )
        contributors.append(((kind, identity), resolution, metadata.measurement_side, side, sample, descriptor, ref))

    authorities = {c[0] for c in contributors}
    kind, identity = next(iter(authorities)) if len(authorities) == 1 and not manual else (None, None)
    samples = [c[4] for c in contributors]
    sample_sides, base_sides = {c[2] for c in contributors}, {c[3] for c in contributors}
    if side_authority is not None:
        # DEC-216: the side compared with the base is Recording Details' strict side where one is established (an engineer's correction
        # is neither ignored nor allowed to produce a "compatible" result against a known mismatch); the raw declaration otherwise.
        sample_sides = {c[4].side if c[4].problem is None else c[2] for c in contributors}
        sides = {s.side for s in samples if s.problem is None}
        problems = [s.problem for s in samples if s.problem is not None]
        trace.update(complete=True, strict_side=next(iter(sides)) if not problems and len(sides) == 1 else None,
                     problem=problems[0] if problems else PROBLEM_UNRESOLVED,
                     authority=(next(iter({s.authority for s in samples})) if len({s.authority for s in samples}) == 1 else "mixed"))
    measurement = next(iter(sample_sides)) if len(sample_sides) == 1 else "unknown"
    base_side = next(iter(base_sides)) if len(base_sides) == 1 else "unknown"
    for _, resolution, *_rest in contributors:
        if resolution.status != STATUS_CONFIGURED:
            if kind is not None:
                return CurrentInheritance(apply_current_reference(replace(resolution, profile_id=identity),
                    sample_sides, base_sides, strict=manual), kind, measurement, base_side)
            return unavailable(resolution.reason, kind, identity, measurement, base_side)
    if side_authority is not None and not (legacy_manual and not manual):
        strict = _strict_common_base(
            contributors, authorities=authorities, identity=identity, workspace_id=workspace_id, side_authority=side_authority)
        if strict is not None:
            resolution = strict if strict.status != STATUS_CONFIGURED else resolve_conversion_eligibility(
                strict, channel.unit, CURRENT, channel.values)
            return CurrentInheritance(
                resolution, kind, resolution.measurement_side, resolution.base_reference_side,
                origin, "manual" if manual else "automatic", configuration.current_base_amps if manual else None)
    reference = apply_current_reference(
        PerUnitResolution(STATUS_CONFIGURED, identity, contributors[0][1].base_amount, "A", None),
        sample_sides, base_sides, strict=manual or len(authorities) > 1, cross_authority=len(authorities) > 1)
    if reference.status != STATUS_CONFIGURED:
        return unavailable(reference.reason, kind, identity, measurement, base_side)
    if legacy_manual and not manual:
        # Retain the old explicit profile-pointer denominator, never a physical
        # reference bypass. Its original grouped inputs must also qualify above.
        legacy = resolve_calculated_group_aware_per_unit(
            workspace_id=workspace_id, channel=channel, calc_registry=calc_registry,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry)
        if legacy is not None:
            kind, identity = "measurement_group", legacy.profile_id
            config = current_config_registry.get(workspace_id, identity)
            side = configured_base_side(config.method, config.base_reference_side) if config else "unknown"
        else:
            identity = per_unit_registry.profile_for_calculated_channel(workspace_id, channel.id)
            profile = per_unit_registry.get(workspace_id, identity) if identity else None
            names = []
            active = source_registry.get(workspace_id, identity) if identity else None
            if active:
                names = [ch.name for ch in active.metadata.analog_channels if ch.engineering_type == VOLTAGE]
            legacy = resolve_per_unit(CURRENT, profile, names)
            side = configured_base_side(profile.current_base_mode, profile.current_base_reference_side) if profile else "unknown"
            kind = "source_default"
        legacy = apply_current_reference(legacy, sample_sides, [side], strict=len(authorities) > 1,
                                         cross_authority=len(authorities) > 1)
        legacy = resolve_conversion_eligibility(legacy, channel.unit, CURRENT, channel.values)
        return CurrentInheritance(legacy, kind, measurement, side)
    bases = [c[1].base_amount for c in contributors]
    smallest, largest = min(bases), max(bases)
    # Division avoids underflow of rtol * largest for subnormal SI bases.
    if (largest - smallest) / largest > COMMON_BASE_RTOL:
        return unavailable("current_bases_differ", kind, identity, measurement, base_side)
    resolution = resolve_conversion_eligibility(
        replace(reference, base_amount=smallest), channel.unit, CURRENT, channel.values)
    return CurrentInheritance(resolution, kind, measurement, base_side,
                              origin, "manual" if manual else "automatic",
                              configuration.current_base_amps if manual else None)
