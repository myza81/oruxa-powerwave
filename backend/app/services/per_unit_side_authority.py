"""PU-MIG S2: Recording Details' side and VT authority for a raw Voltage channel, in the shape the strict resolver consumes.

This adapter only READS what the shared authorities already decide and translates it:

  * the consumed channel's effective measurement side and whether a calculation may consume it
    (`recorded_side_authority.evaluate_channel_side`, the one policy Overcurrent / Impedance / Distance also apply);
  * the VT of the Measurement Group that owns the channel (`protection_instrument_context.resolve_transformer_context`),
    read only when the base side differs from the sample side.

It chooses no base, decides no side, derives no ratio and does arithmetic of no kind: `per_unit_reference` hands the result to
`side_denominator.resolve_side_denominator()`. One function (`apply_raw_source_reference`) is the raw-channel reference gate every
source consumer calls (display seams, provenance, coverage), so they cannot disagree (S0 finding C-3).
"""

from __future__ import annotations

from app.domain.calculated_channel import CalculatedChannel, ChannelRef
from app.domain.calculated_side_lineage import resolve_calculated_side
from app.domain.channel_classification import VOLTAGE
from app.domain.per_unit import STATUS_CONFIGURED
from app.domain.per_unit_reference import RawVoltageSideInputs, apply_source_reference
from app.domain.side_denominator import RATIO_NO_GROUP, SampleSide, SideRatio
from app.services.protection_instrument_context import QUANTITY_VOLTAGE, resolve_transformer_context
from app.services.recorded_side_authority import RecordedAuthority, evaluate_channel_side


def raw_voltage_side_inputs(
    workspace_id: str, source_id: str, channel_name: str, *, authority: RecordedAuthority,
    group_status_cache: dict[tuple[str, str], bool] | None = None,
) -> RawVoltageSideInputs:
    ref = ChannelRef(kind="source", source_id=source_id, channel_name=channel_name)
    evaluated = evaluate_channel_side(workspace_id, ref, authority=authority, group_status_cache=group_status_cache)
    side_authority = evaluated.side.authority if evaluated.side is not None else None
    if evaluated.problem is None:
        sample = SampleSide(side=evaluated.usable_side, problem=None, authority=side_authority)
    else:
        sample = SampleSide(side=None, problem=evaluated.problem, authority=side_authority)

    def ratio_for() -> SideRatio:
        context = resolve_transformer_context(
            workspace_id, (ref,), QUANTITY_VOLTAGE,
            group_registry=authority.side.group_registry, voltage_config_registry=authority.voltage_config_registry,
            current_config_registry=authority.current_config_registry, source_registry=authority.side.source_registry,
        )
        # The ONE shared VT authority, exactly as DEC-215 defines it (manual > recording_metadata > auto_nominal > not_configured).
        # PU adds no rule of its own: the selected PU base (stored or derived) and the VT equipment ratio are independent
        # quantities, so a stored secondary base never changes what the VT authority says (decision D-4: it is only reported).
        return SideRatio(
            status=context.ratio_status, value=context.ratio, authority=context.authority, group_ids=context.group_ids,
        )

    return RawVoltageSideInputs(sample=sample, ratio_for=ratio_for)


def apply_raw_source_reference(
    resolution, engineering_type, channel_name, measurement_side="unknown", *,
    workspace_id: str | None = None, source_id: str | None = None,
    group_config=None, profile=None, voltage_group_config=None,
    side_authority: RecordedAuthority | None = None,
    group_status_cache: dict[tuple[str, str], bool] | None = None,
):
    """`per_unit_reference.apply_source_reference` for a SOURCE channel, with Recording Details' side authority when the
    caller has one. Without `side_authority` (or for Current, or for a resolution that is not configured) it is exactly the
    historical gate."""
    side_inputs = None
    if (
        side_authority is not None and engineering_type == VOLTAGE and resolution.status == STATUS_CONFIGURED
        and workspace_id is not None and source_id is not None
    ):
        side_inputs = raw_voltage_side_inputs(
            workspace_id, source_id, channel_name, authority=side_authority, group_status_cache=group_status_cache,
        )
    return apply_source_reference(
        resolution, engineering_type, measurement_side, group_config=group_config, profile=profile,
        voltage_group_config=voltage_group_config, side_inputs=side_inputs,
    )


# ------------------------------------------------------------------------------------------------ calculated Voltage (S3)
def collect_source_leaf_refs(workspace_id: str, channel: CalculatedChannel, calc_registry) -> tuple[ChannelRef, ...]:
    """The transitive set of SOURCE channels a calculated channel is calculated from (each once, in first-seen order). The same leaf set the
    calibration gate and the Current lineage already walk; a dependency cycle is structurally impossible and is guarded defensively."""
    seen: dict[tuple[str, str], ChannelRef] = {}
    visited: set[str] = set()

    def walk(current: CalculatedChannel) -> None:
        if current.id in visited:
            return
        visited.add(current.id)
        for ref in current.inputs:
            if ref.kind == "source":
                seen.setdefault((ref.source_id, ref.channel_name), ref)
            else:
                nested = calc_registry.get(workspace_id, ref.calculated_channel_id)
                if nested is not None:
                    walk(nested)

    walk(channel)
    return tuple(seen.values())


def calculated_voltage_side_inputs(
    workspace_id: str, channel: CalculatedChannel, *, calc_registry, authority: RecordedAuthority,
    group_id: str | None,
) -> RawVoltageSideInputs:
    """Recording Details' side and VT for a calculated Voltage result: the side of its leaves (`calculated_side_lineage`, which
    requires every leaf to agree) and the VT of the Measurement Group whose base was inherited (`group_id`; None when the base is a Source
    Default, which has no ratio authority -- S0 section 7, so a Secondary result on a Source Default base is blocked, `no_group`)."""
    leaves = collect_source_leaf_refs(workspace_id, channel, calc_registry)
    cache: dict[tuple[str, str], bool] = {}
    sides = [
        raw_voltage_side_inputs(workspace_id, ref.source_id, ref.channel_name, authority=authority, group_status_cache=cache).sample
        for ref in leaves
    ]
    lineage = resolve_calculated_side(sides)

    def ratio_for() -> SideRatio:
        if group_id is None:
            return SideRatio(status=RATIO_NO_GROUP)
        context = resolve_transformer_context(
            workspace_id, leaves, QUANTITY_VOLTAGE,
            group_registry=authority.side.group_registry, voltage_config_registry=authority.voltage_config_registry,
            current_config_registry=authority.current_config_registry, source_registry=authority.side.source_registry,
        )
        if tuple(context.group_ids) != (group_id,):
            return SideRatio(status=RATIO_NO_GROUP, group_ids=tuple(context.group_ids))
        return SideRatio(
            status=context.ratio_status, value=context.ratio, authority=context.authority, group_ids=context.group_ids,
        )

    placeholder = SampleSide(side=None, problem="unresolved", authority=None)
    return RawVoltageSideInputs(sample=lineage.sample or placeholder, ratio_for=ratio_for, refusal=lineage.refusal)


def apply_calculated_source_reference(
    resolution, channel: CalculatedChannel, *, workspace_id: str | None = None, calc_registry=None,
    group_config=None, profile=None, voltage_group_config=None, side_authority: RecordedAuthority | None = None,
):
    """`per_unit_reference.apply_source_reference` for a CALCULATED channel, with the lineage side when the caller has the authority.
    Without `side_authority` (or for anything but a configured Voltage resolution) it is exactly the historical gate."""
    side_inputs = None
    if (
        side_authority is not None and channel.engineering_type == VOLTAGE and resolution.status == STATUS_CONFIGURED
        and workspace_id is not None and calc_registry is not None and resolution.base_descriptor is not None
    ):
        side_inputs = calculated_voltage_side_inputs(
            workspace_id, channel, calc_registry=calc_registry, authority=side_authority,
            group_id=resolution.profile_id if voltage_group_config is not None else None,
        )
    return apply_source_reference(
        resolution, channel.engineering_type, "unknown", group_config=group_config, profile=profile,
        voltage_group_config=voltage_group_config, side_inputs=side_inputs,
    )
