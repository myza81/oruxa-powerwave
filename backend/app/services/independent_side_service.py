"""D5A-2B1: validate a strict independent-side request against authoritative evidence.

Returns:
  * None       -- neither `voltage_side` nor `current_side` was supplied: the LEGACY single-
                  `recording_basis` path applies, untouched.
  * SideBlock  -- strict mode was requested but could not be justified; no conversion happens and
                  legacy is never used as a fallback. Carries a machine-readable reason code.
  * SidePlan   -- strict mode is justified; carries the sides and the Recording Details CT/VT
                  ratios to apply.

Authority rules: a supplied side is an ASSERTION validated against the recording's own per-channel
declarations (never confirmed merely because the caller supplied it, never inferred from a ratio or
from `recording_basis`). Ratios come only from the Measurement Groups, and only for a quantity that
actually needs converting. Request-supplied `vt_*`/`ct_*` are never applied; a complete, valid pair
that contradicts the authority blocks, because silently preferring either would be a silent override.
"""

from __future__ import annotations

import math

from app.domain.calculated_channel import ChannelRef
from app.domain.side_conversion import (
    KNOWN_SIDES,
    REASON_CT_AUTHORITY_UNAVAILABLE,
    REASON_CURRENT_MIXED_SIDE,
    REASON_CURRENT_SIDE_CONTRADICTS,
    REASON_CURRENT_SIDE_REQUIRED,
    REASON_CURRENT_SIDE_UNAVAILABLE,
    REASON_INVALID_CURRENT_SIDE,
    REASON_INVALID_IMPEDANCE_BASIS,
    REASON_INVALID_VOLTAGE_SIDE,
    REASON_REQUEST_CT_CONFLICTS,
    REASON_REQUEST_VT_CONFLICTS,
    REASON_VOLTAGE_MIXED_SIDE,
    REASON_VOLTAGE_SIDE_CONTRADICTS,
    REASON_VOLTAGE_SIDE_REQUIRED,
    REASON_VOLTAGE_SIDE_UNAVAILABLE,
    REASON_VT_AUTHORITY_UNAVAILABLE,
    SideBlock,
    SidePlan,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import ImportServiceError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.protection_context_report_service import InvalidProtectionContextRequest, resolve_analysis_roles
from app.services.protection_instrument_context import (
    QUANTITY_CURRENT,
    QUANTITY_VOLTAGE,
    resolve_channel_facts,
    resolve_channel_unit,
    resolve_transformer_context,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

_RATIO_REL_TOL = 1e-6


def _label(ref: ChannelRef) -> str:
    return ref.channel_name if ref.kind == "source" else f"calculated:{ref.calculated_channel_id}"


def _positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def resolve_side_plan(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis: str,
    phase: str | None,
    loop: str | None,
    voltage_side: str | None,
    current_side: str | None,
    impedance_basis: str,
    request_vt: tuple[float | None, float | None] = (None, None),
    request_ct: tuple[float | None, float | None] = (None, None),
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> SidePlan | SideBlock | None:
    if voltage_side is None and current_side is None:
        return None

    resolved_roles: list[tuple[str, ChannelRef]] | None = None

    def known_roles() -> list[tuple[str, ChannelRef]]:
        """Roles that resolved for this analysis, best-effort: a missing context or bad phase simply yields none, so an
        early validation block is still returned exactly as before and no identity is ever invented."""
        nonlocal resolved_roles
        if resolved_roles is None:
            try:
                resolved_roles, _ = resolve_analysis_roles(
                    workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis=analysis,
                    phase=phase, loop=loop, context_registry=context_registry, source_registry=source_registry,
                    calculated_channel_registry=calculated_channel_registry,
                )
            except (ImportServiceError, InvalidProtectionContextRequest):
                resolved_roles = []
        return resolved_roles

    def block(code: str, message: str, quantity: str | None = None, **detail) -> SideBlock:
        roles = known_roles()
        return SideBlock(
            code=code, message=message, quantity=quantity, detail=detail,
            voltage_side=voltage_side, current_side=current_side, output_side=impedance_basis,
            role_refs={key: ref for key, ref in roles},
            role_units={key: resolve_channel_unit(workspace_id, ref, source_registry=source_registry,
                                                  calculated_channel_registry=calculated_channel_registry)
                        for key, ref in roles},
        )

    if impedance_basis not in KNOWN_SIDES:
        return block(REASON_INVALID_IMPEDANCE_BASIS, "impedance_basis must be 'primary' or 'secondary'.",
                     impedance_basis=impedance_basis)
    if voltage_side is None:
        return block(REASON_VOLTAGE_SIDE_REQUIRED,
                     "Independent-side mode requires voltage_side; it is never inferred from recording_basis.", "voltage")
    if current_side is None:
        return block(REASON_CURRENT_SIDE_REQUIRED,
                     "Independent-side mode requires current_side; it is never inferred from recording_basis.", "current")
    if voltage_side not in KNOWN_SIDES:
        return block(REASON_INVALID_VOLTAGE_SIDE, "voltage_side must be 'primary' or 'secondary'.", "voltage",
                     voltage_side=voltage_side)
    if current_side not in KNOWN_SIDES:
        return block(REASON_INVALID_CURRENT_SIDE, "current_side must be 'primary' or 'secondary'.", "current",
                     current_side=current_side)

    try:
        resolved, unresolved = resolve_analysis_roles(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis=analysis, phase=phase,
            loop=loop, context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
    except InvalidProtectionContextRequest as exc:     # same reason codes the legacy compute paths use
        return block("unsupported_loop" if analysis == "distance_protection" else "unsupported_phase", str(exc))
    resolved_roles = resolved
    if unresolved:
        # The compute path reports its own natural status for unresolved/ambiguous channels.
        return SidePlan(voltage_side=voltage_side, current_side=current_side, output_side=impedance_basis,
                        vt_ratio=None, ct_ratio=None, validated=False)

    refs = {QUANTITY_VOLTAGE: tuple(r for k, r in resolved if k.startswith("V")),
            QUANTITY_CURRENT: tuple(r for k, r in resolved if k.startswith("I"))}
    asserted = {QUANTITY_VOLTAGE: voltage_side, QUANTITY_CURRENT: current_side}
    codes = {
        QUANTITY_VOLTAGE: (REASON_VOLTAGE_MIXED_SIDE, REASON_VOLTAGE_SIDE_UNAVAILABLE, REASON_VOLTAGE_SIDE_CONTRADICTS),
        QUANTITY_CURRENT: (REASON_CURRENT_MIXED_SIDE, REASON_CURRENT_SIDE_UNAVAILABLE, REASON_CURRENT_SIDE_CONTRADICTS),
    }
    for quantity in (QUANTITY_VOLTAGE, QUANTITY_CURRENT):
        mixed_code, unavailable_code, contradicts_code = codes[quantity]
        facts = [resolve_channel_facts(workspace_id, r, quantity, group_registry=group_registry,
                                       source_registry=source_registry) for r in refs[quantity]]
        known = {f.declared_side for f in facts if f.declared_side != "unknown"}
        unknown = [_label(f.ref) for f in facts if f.declared_side == "unknown"]
        per_channel = ",".join(f"{_label(f.ref)}={f.declared_side}" for f in facts)
        if len(known) > 1:
            return block(mixed_code, f"The consumed {quantity} channels declare different measurement sides; "
                                     "mixed sides within a quantity are not supported.", quantity, channels=per_channel)
        if unknown:
            return block(unavailable_code, f"The recording does not declare the {quantity} measurement side of every "
                                           "consumed channel; a caller-supplied side cannot stand in for it.",
                         quantity, unknown_channels=",".join(unknown), asserted_side=asserted[quantity])
        declared = next(iter(known))
        if declared != asserted[quantity]:
            return block(contradicts_code, f"The asserted {quantity} side contradicts the recording's declaration.",
                         quantity, asserted_side=asserted[quantity], declared_side=declared, channels=per_channel)

    lookup = dict(group_registry=group_registry, voltage_config_registry=voltage_config_registry,
                  current_config_registry=current_config_registry, source_registry=source_registry)
    vt_ctx = resolve_transformer_context(workspace_id, refs[QUANTITY_VOLTAGE], QUANTITY_VOLTAGE, **lookup)
    ct_ctx = resolve_transformer_context(workspace_id, refs[QUANTITY_CURRENT], QUANTITY_CURRENT, **lookup)

    vt_ratio = ct_ratio = None
    for ctx, source_side, tag, unavailable_code, conflict_code, request in (
        (vt_ctx, voltage_side, "VT", REASON_VT_AUTHORITY_UNAVAILABLE, REASON_REQUEST_VT_CONFLICTS, request_vt),
        (ct_ctx, current_side, "CT", REASON_CT_AUTHORITY_UNAVAILABLE, REASON_REQUEST_CT_CONFLICTS, request_ct),
    ):
        if source_side == impedance_basis:
            continue                                   # already on the output side: no ratio needed or read
        quantity = ctx.quantity
        if not ctx.ratio_consumable:
            return block(unavailable_code, f"Converting {quantity} needs a {tag} ratio from Recording Details, "
                                           f"which is {ctx.ratio_status}.", quantity,
                         ratio_status=ctx.ratio_status, reason=ctx.reason, authority=ctx.authority)
        req_p, req_s = request
        if _positive(req_p) and _positive(req_s) and not math.isclose(req_p / req_s, ctx.ratio, rel_tol=_RATIO_REL_TOL):
            return block(conflict_code, f"The request's {tag} ratio contradicts the Recording Details ratio; "
                                        "independent-side mode never silently prefers either.", quantity,
                         request_ratio=req_p / req_s, authoritative_ratio=ctx.ratio)
        if quantity == QUANTITY_VOLTAGE:
            vt_ratio = ctx.ratio
        else:
            ct_ratio = ctx.ratio

    return SidePlan(
        voltage_side=voltage_side, current_side=current_side, output_side=impedance_basis,
        vt_ratio=vt_ratio, ct_ratio=ct_ratio, voltage_refs=refs[QUANTITY_VOLTAGE], current_refs=refs[QUANTITY_CURRENT],
        voltage_group_ids=vt_ctx.group_ids, current_group_ids=ct_ctx.group_ids,
    )
