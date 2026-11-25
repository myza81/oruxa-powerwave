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

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import VOLTAGE
from app.domain.per_unit import STATUS_CONFIGURED
from app.domain.per_unit_reference import RawVoltageSideInputs, apply_source_reference
from app.domain.auto_nominal_vt import AUTHORITY_AUTO_NOMINAL
from app.domain.secondary_base_diagnostic import secondary_base_discrepancy
from app.domain.side_denominator import RATIO_UNTRUSTED_AUTHORITY, SampleSide, SideRatio
from app.services.protection_instrument_context import QUANTITY_VOLTAGE, resolve_transformer_context
from app.services.recorded_side_authority import RecordedAuthority, evaluate_channel_side


def _contradicts_default_secondary(workspace_id: str, context, authority: RecordedAuthority) -> bool:
    for group_id in context.group_ids:
        if secondary_base_discrepancy(authority.voltage_config_registry.get(workspace_id, group_id)) is not None:
            return True
    return False


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
        ratio = SideRatio(
            status=context.ratio_status, value=context.ratio, authority=context.authority, group_ids=context.group_ids,
        )
        if context.authority == AUTHORITY_AUTO_NOMINAL and _contradicts_default_secondary(workspace_id, context, authority):
            # D-7: `auto_nominal` is the approved DEFAULT (nominal as primary, 110 V as secondary). A group that itself stores a
            # different secondary base is evidence against that default, so the default is not consumed for PU -- no new
            # inference is made and nothing is guessed. The refusal is reported; the engineer enters the VT in Recording Details.
            return SideRatio(status=RATIO_UNTRUSTED_AUTHORITY, value=None, authority=context.authority, group_ids=context.group_ids)
        return ratio

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
