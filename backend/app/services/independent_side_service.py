"""D5A-2B1 / D5A-2B2C-1B: the recorded Impedance Locus and Distance Protection input authority.

Recording Details is the single source of truth for the Primary/Secondary side of every recorded Voltage and Current channel
(DEC-216). For the channels one recorded calculation actually consumes this module:

  1. asks the shared channel policy (`recorded_side_authority.evaluate_channel_side`, built on the shared resolver
     `resolve_effective_measurement_side`) for the EFFECTIVE side of each consumed channel -- Level 2 Measurement-Group setting >
     Level 1 recording correction > the channel's own declaration > inferred default (not strict-usable) > unresolved;
  2. blocks when a side is calculated-channel, unresolved, only inferred, contradictory (a Measurement Group declaring mixed
     sides that no engineer has resolved) or different between the legs of one quantity;
  3. validates the legacy request parameters (`recording_basis`, `voltage_side`, `current_side`, `vt_*`, `ct_*`) as ASSERTIONS
     only: a contradicting assertion blocks, a matching one adds no conversion, and none can supply, replace or override a side
     or a ratio;
  4. reads a VT/CT ratio only for a quantity whose effective side differs from the requested output side, only from the
     Measurement Groups that own the consumed channels (never another group or recording), and only when it is consumable
     (`manual`, `recording_metadata`, or the nominal-derived `auto_nominal` VT).

Voltage and Current resolve independently (a Primary voltage with a Secondary current is legitimate). There is no legacy
fallback: omitting the newer parameters can no longer bypass Recording Details.

The same evaluation also feeds the read-only recorded-input report, so the page and the calculation cannot disagree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

from app.domain.calculated_channel import ChannelRef
from app.domain.side_conversion import (
    KNOWN_SIDES,
    REASON_CALCULATED_SIDE,
    REASON_CT_AUTHORITY_UNAVAILABLE,
    REASON_CURRENT_GROUP_CONFLICT,
    REASON_CURRENT_MIXED_SIDE,
    REASON_CURRENT_SIDE_CONTRADICTS,
    REASON_CURRENT_SIDE_INFERRED,
    REASON_CURRENT_SIDE_UNAVAILABLE,
    REASON_INVALID_CURRENT_SIDE,
    REASON_INVALID_IMPEDANCE_BASIS,
    REASON_INVALID_RECORDING_BASIS,
    REASON_INVALID_VOLTAGE_SIDE,
    REASON_REQUEST_CT_CONFLICTS,
    REASON_REQUEST_CT_INVALID,
    REASON_REQUEST_VT_CONFLICTS,
    REASON_REQUEST_VT_INVALID,
    REASON_VOLTAGE_GROUP_CONFLICT,
    REASON_VOLTAGE_MIXED_SIDE,
    REASON_VOLTAGE_SIDE_CONTRADICTS,
    REASON_VOLTAGE_SIDE_INFERRED,
    REASON_VOLTAGE_SIDE_UNAVAILABLE,
    REASON_VT_AUTHORITY_UNAVAILABLE,
    SideBlock,
    SidePlan,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import ImportServiceError
from app.services.protection_context_report_service import InvalidProtectionContextRequest, resolve_analysis_roles
from app.services.protection_instrument_context import (
    QUANTITY_CURRENT,
    QUANTITY_VOLTAGE,
    TransformerContext,
    resolve_channel_unit,
    resolve_transformer_context,
)
from app.services.recorded_side_authority import (
    PROBLEM_CALCULATED,
    PROBLEM_GROUP_CONFLICT,
    PROBLEM_INFERRED,
    PROBLEM_UNRESOLVED,
    ChannelSideAuthority,
    RecordedAuthority,
    channel_label,
    evaluate_channel_side,
)
from app.services.workspace_registry import WorkspaceRegistry

_RATIO_REL_TOL = 1e-6

_KIND_WORD = {QUANTITY_VOLTAGE: "Voltage", QUANTITY_CURRENT: "Current"}
_TAG = {QUANTITY_VOLTAGE: "VT", QUANTITY_CURRENT: "CT"}
_ANALYSIS_WORD = {"impedance": "Impedance Locus", "distance_protection": "Distance Protection"}
_CODES = {
    # quantity: (mixed, unavailable, inferred, group conflict, contradicts, invalid assertion)
    QUANTITY_VOLTAGE: (REASON_VOLTAGE_MIXED_SIDE, REASON_VOLTAGE_SIDE_UNAVAILABLE, REASON_VOLTAGE_SIDE_INFERRED,
                       REASON_VOLTAGE_GROUP_CONFLICT, REASON_VOLTAGE_SIDE_CONTRADICTS, REASON_INVALID_VOLTAGE_SIDE),
    QUANTITY_CURRENT: (REASON_CURRENT_MIXED_SIDE, REASON_CURRENT_SIDE_UNAVAILABLE, REASON_CURRENT_SIDE_INFERRED,
                       REASON_CURRENT_GROUP_CONFLICT, REASON_CURRENT_SIDE_CONTRADICTS, REASON_INVALID_CURRENT_SIDE),
}


def _positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


@dataclass(frozen=True, slots=True)
class QuantityAuthority:
    """The authority of ONE quantity (Voltage or Current) for the channels this analysis consumes."""

    quantity: str
    refs: tuple[ChannelRef, ...]
    channels: tuple[ChannelSideAuthority, ...]
    #: The one effective side ('primary'/'secondary'); None when the quantity is blocked or its legs disagree.
    side: str | None
    #: Provenance of that side (an authority such as `engineer_group_override`), `mixed` when the legs were decided
    #: differently, None when blocked.
    authority: str | None
    group_ids: tuple[str, ...]
    group_names: tuple[str, ...]
    #: VT/CT of the Measurement Groups that own the consumed channels (always read, so the page can show it).
    transformer: TransformerContext | None
    problem_code: str | None = None
    problem_message: str | None = None
    problem_detail: Mapping[str, str | float | None] = field(default_factory=dict)
    #: Whether the requested output side needs this quantity's ratio.
    ratio_required: bool = False

    @property
    def declared_sides(self) -> tuple[str, ...]:
        return tuple(c.side.declared_side for c in self.channels if c.side is not None)


@dataclass(frozen=True, slots=True)
class RecordedInputEvaluation:
    """Everything one evaluation decided: the plan (or block) the calculation uses and what the report shows."""

    analysis: str
    phase: str | None
    loop: str | None
    output_side: str
    outcome: SidePlan | SideBlock
    voltage: QuantityAuthority | None
    current: QuantityAuthority | None
    unresolved_roles: tuple[tuple[str, str, str | None], ...] = ()
    role_refs: Mapping[str, ChannelRef] = field(default_factory=dict)
    role_units: Mapping[str, str | None] = field(default_factory=dict)


def _quantity_authority(
    workspace_id: str, quantity: str, refs: tuple[ChannelRef, ...], *, analysis: str, output_side: str,
    authority: RecordedAuthority, group_cache: dict,
) -> QuantityAuthority:
    mixed_code, unavailable_code, inferred_code, conflict_code, _contradicts, _invalid = _CODES[quantity]
    kind = _KIND_WORD[quantity]
    channels = tuple(evaluate_channel_side(workspace_id, r, authority=authority, group_status_cache=group_cache) for r in refs)
    group_ids = tuple(dict.fromkeys(c.group_id for c in channels if c.group_id))
    group_names = tuple(dict.fromkeys(c.group_name for c in channels if c.group_name))
    transformer = resolve_transformer_context(
        workspace_id, refs, quantity, group_registry=authority.side.group_registry,
        voltage_config_registry=authority.voltage_config_registry, current_config_registry=authority.current_config_registry,
        source_registry=authority.side.source_registry,
    )
    base = dict(quantity=quantity, refs=refs, channels=channels, group_ids=group_ids, group_names=group_names,
                transformer=transformer, ratio_required=False)

    def blocked(code: str, message: str, **detail) -> QuantityAuthority:
        return QuantityAuthority(side=None, authority=None, problem_code=code, problem_message=message,
                                 problem_detail=detail, **base)

    per_channel = ",".join(f"{channel_label(c.ref)}={c.side.side if c.side else 'unknown'}" for c in channels)
    for problem, code, text in (
        (PROBLEM_CALCULATED, REASON_CALCULATED_SIDE,
         "Measurement-side support for calculated channels is not available yet: the consumed {q} channel '{ch}' is a "
         "calculated channel whose side is derived from its inputs, and Recording Details does not resolve it, so there is "
         "nothing to set there. A recorded {a} calculation cannot use it until that support is added; use recorded (source) "
         "channels or Manual input."),
        (PROBLEM_UNRESOLVED, unavailable_code,
         "The measurement side of the consumed {q} channel '{ch}' (Primary or Secondary) is not defined by the recording or "
         "by Recording Details, so the recorded values cannot be interpreted; a caller-supplied side cannot stand in for it. "
         "Set it in Recording Details (the recording, or the {k} Measurement Group{g})."),
        (PROBLEM_INFERRED, inferred_code,
         "The measurement side of the consumed {q} channel '{ch}' is only inferred from other channels of the recording; a "
         "recorded calculation needs the channel's own declaration or an engineer's setting. Set it in Recording Details "
         "(the recording, or the {k} Measurement Group{g})."),
        (PROBLEM_GROUP_CONFLICT, conflict_code,
         "The channels of the {k} Measurement Group{g} declare different measurement sides, so its side is contradictory. "
         "Choose Primary or Secondary for the group in Recording Details."),
    ):
        bad = next((c for c in channels if c.problem == problem), None)
        if bad is not None:
            group_text = f" '{bad.group_name}'" if bad.group_name else ""
            return blocked(code, text.format(q=quantity, ch=channel_label(bad.ref), k=kind,
                                             g=group_text, a=_ANALYSIS_WORD.get(analysis, analysis)),
                           channels=per_channel, problem_channel=channel_label(bad.ref))
    sides = {c.usable_side for c in channels}
    if len(sides) > 1:
        return blocked(mixed_code, f"The consumed {quantity} channels are on different measurement sides; mixed sides "
                                   "within a quantity are not supported.", channels=per_channel)
    side = next(iter(sides))
    authorities = {c.side.authority for c in channels if c.side is not None}
    return QuantityAuthority(
        side=side, authority=next(iter(authorities)) if len(authorities) == 1 else "mixed",
        problem_code=None, problem_message=None, problem_detail={},
        **{**base, "ratio_required": side != output_side},
    )


def evaluate_recorded_input(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis: str,
    phase: str | None,
    loop: str | None,
    impedance_basis: str,
    recording_basis: str | None = None,
    voltage_side: str | None = None,
    current_side: str | None = None,
    request_vt: tuple[float | None, float | None] = (None, None),
    request_ct: tuple[float | None, float | None] = (None, None),
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    authority: RecordedAuthority,
) -> RecordedInputEvaluation:
    resolved_roles: list[tuple[str, ChannelRef]] | None = None
    unresolved: list[tuple[str, str, str | None]] = []

    def load_roles() -> list[tuple[str, ChannelRef]]:
        """Roles that resolved for this analysis, best-effort: a missing context or bad phase simply yields none, so an
        early validation block is still returned exactly as before and no identity is ever invented."""
        nonlocal resolved_roles, unresolved
        if resolved_roles is None:
            try:
                resolved_roles, unresolved = resolve_analysis_roles(
                    workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis=analysis,
                    phase=phase, loop=loop, context_registry=context_registry, source_registry=source_registry,
                    calculated_channel_registry=calculated_channel_registry,
                )
            except (ImportServiceError, InvalidProtectionContextRequest):
                resolved_roles, unresolved = [], []
        return resolved_roles

    voltage: QuantityAuthority | None = None
    current: QuantityAuthority | None = None

    def make_block(code: str, message: str, quantity: str | None = None, **detail) -> RecordedInputEvaluation:
        roles = load_roles()
        block = SideBlock(
            code=code, message=message, quantity=quantity, detail=detail,
            voltage_side=voltage.side if voltage else None, current_side=current.side if current else None,
            output_side=impedance_basis,
            role_refs={key: ref for key, ref in roles},
            role_units={key: resolve_channel_unit(workspace_id, ref, source_registry=source_registry,
                                                  calculated_channel_registry=calculated_channel_registry)
                        for key, ref in roles},
            voltage_side_authority=voltage.authority if voltage else None,
            current_side_authority=current.authority if current else None,
            voltage_group_ids=voltage.group_ids if voltage else (), current_group_ids=current.group_ids if current else (),
            voltage_group_names=voltage.group_names if voltage else (), current_group_names=current.group_names if current else (),
        )
        return RecordedInputEvaluation(
            analysis=analysis, phase=phase, loop=loop, output_side=impedance_basis, outcome=block, voltage=voltage,
            current=current, unresolved_roles=tuple(unresolved), role_refs=dict(block.role_refs), role_units=dict(block.role_units),
        )

    if impedance_basis not in KNOWN_SIDES:
        return make_block(REASON_INVALID_IMPEDANCE_BASIS, "impedance_basis must be 'primary' or 'secondary'.",
                          impedance_basis=impedance_basis)
    if recording_basis is not None and recording_basis not in KNOWN_SIDES:
        return make_block(REASON_INVALID_RECORDING_BASIS, "recording_basis must be 'primary' or 'secondary'.",
                          recording_basis=recording_basis)
    if voltage_side is not None and voltage_side not in KNOWN_SIDES:
        return make_block(REASON_INVALID_VOLTAGE_SIDE, "voltage_side must be 'primary' or 'secondary'.", QUANTITY_VOLTAGE,
                          voltage_side=voltage_side)
    if current_side is not None and current_side not in KNOWN_SIDES:
        return make_block(REASON_INVALID_CURRENT_SIDE, "current_side must be 'primary' or 'secondary'.", QUANTITY_CURRENT,
                          current_side=current_side)

    try:
        resolved, unresolved_now = resolve_analysis_roles(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis=analysis, phase=phase,
            loop=loop, context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
    except InvalidProtectionContextRequest as exc:     # same reason codes the compute paths use
        return make_block("unsupported_loop" if analysis == "distance_protection" else "unsupported_phase", str(exc))
    resolved_roles, unresolved = resolved, list(unresolved_now)

    refs = {QUANTITY_VOLTAGE: tuple(r for k, r in resolved if k.startswith("V")),
            QUANTITY_CURRENT: tuple(r for k, r in resolved if k.startswith("I"))}
    group_cache: dict = {}
    if refs[QUANTITY_VOLTAGE]:
        voltage = _quantity_authority(workspace_id, QUANTITY_VOLTAGE, refs[QUANTITY_VOLTAGE], analysis=analysis,
                                      output_side=impedance_basis, authority=authority, group_cache=group_cache)
    if refs[QUANTITY_CURRENT]:
        current = _quantity_authority(workspace_id, QUANTITY_CURRENT, refs[QUANTITY_CURRENT], analysis=analysis,
                                      output_side=impedance_basis, authority=authority, group_cache=group_cache)

    if unresolved:
        # The compute path reports its own natural status for unresolved/ambiguous channels (that status is decided
        # before any side is consumed); the plan is a placeholder that is never used.
        plan = SidePlan(
            voltage_side=(voltage.side if voltage and voltage.side else impedance_basis),
            current_side=(current.side if current and current.side else impedance_basis),
            output_side=impedance_basis, vt_ratio=None, ct_ratio=None, validated=False,
        )
        return RecordedInputEvaluation(
            analysis=analysis, phase=phase, loop=loop, output_side=impedance_basis, outcome=plan, voltage=voltage,
            current=current, unresolved_roles=tuple(unresolved),
        )

    for quantity, qa in ((QUANTITY_VOLTAGE, voltage), (QUANTITY_CURRENT, current)):
        if qa is not None and qa.problem_code is not None:
            return make_block(qa.problem_code, qa.problem_message or "", quantity, **dict(qa.problem_detail))

    assertions = {
        QUANTITY_VOLTAGE: (("voltage_side", voltage_side), ("recording_basis", recording_basis)),
        QUANTITY_CURRENT: (("current_side", current_side), ("recording_basis", recording_basis)),
    }
    for quantity, qa in ((QUANTITY_VOLTAGE, voltage), (QUANTITY_CURRENT, current)):
        for name, asserted in assertions[quantity]:
            if asserted is not None and asserted != qa.side:
                return make_block(
                    _CODES[quantity][4],
                    f"The asserted {quantity} side ({name}={asserted}) contradicts the {quantity} side defined in Recording "
                    f"Details ({qa.side}). Recording Details is authoritative; change the side there.",
                    quantity, parameter=name, asserted_side=asserted, effective_side=qa.side,
                    declared_side=",".join(dict.fromkeys(qa.declared_sides)), authority=qa.authority,
                )

    pairs: dict[str, tuple[float, float] | None] = {QUANTITY_VOLTAGE: None, QUANTITY_CURRENT: None}
    ratios: dict[str, float | None] = {QUANTITY_VOLTAGE: None, QUANTITY_CURRENT: None}
    for quantity, qa, request, unavailable_code, conflict_code, invalid_code in (
        (QUANTITY_VOLTAGE, voltage, request_vt, REASON_VT_AUTHORITY_UNAVAILABLE, REASON_REQUEST_VT_CONFLICTS, REASON_REQUEST_VT_INVALID),
        (QUANTITY_CURRENT, current, request_ct, REASON_CT_AUTHORITY_UNAVAILABLE, REASON_REQUEST_CT_CONFLICTS, REASON_REQUEST_CT_INVALID),
    ):
        if not qa.ratio_required:
            continue                                   # already on the output side: no ratio needed, read or asserted
        ctx = qa.transformer
        tag = _TAG[quantity]
        if ctx is None or not ctx.ratio_consumable:
            where = f" ({', '.join(qa.group_names)})" if qa.group_names else ""
            return make_block(
                unavailable_code,
                f"Converting {quantity} needs a {tag} ratio from Recording Details for the Measurement Group{where} that owns "
                f"the consumed channel(s), which is {ctx.ratio_status if ctx else 'unavailable'}"
                f"{' (' + ctx.reason + ')' if ctx is not None and ctx.reason else ''}. A request-supplied ratio cannot stand in for it.",
                quantity, ratio_status=ctx.ratio_status if ctx else None, reason=ctx.reason if ctx else None,
                authority=ctx.authority if ctx else None,
            )
        req_p, req_s = request
        if req_p is not None or req_s is not None:
            if not (_positive(req_p) and _positive(req_s)):
                return make_block(
                    invalid_code, f"The request's {tag} values must both be finite numbers greater than zero.", quantity,
                    request_primary=req_p, request_secondary=req_s,
                )
            if not math.isclose(req_p / req_s, ctx.ratio, rel_tol=_RATIO_REL_TOL):
                return make_block(
                    conflict_code, f"The request's {tag} ratio contradicts the Recording Details ratio; Recording Details is "
                                   "authoritative and a request ratio never replaces it.", quantity,
                    request_ratio=req_p / req_s, authoritative_ratio=ctx.ratio,
                )
        pairs[quantity] = (float(ctx.primary), float(ctx.secondary))
        ratios[quantity] = ctx.ratio

    plan = SidePlan(
        voltage_side=voltage.side, current_side=current.side, output_side=impedance_basis,
        vt_ratio=ratios[QUANTITY_VOLTAGE], ct_ratio=ratios[QUANTITY_CURRENT],
        voltage_refs=voltage.refs, current_refs=current.refs,
        voltage_group_ids=voltage.group_ids, current_group_ids=current.group_ids,
        vt_pair=pairs[QUANTITY_VOLTAGE], ct_pair=pairs[QUANTITY_CURRENT],
        voltage_side_authority=voltage.authority, current_side_authority=current.authority,
        voltage_group_names=voltage.group_names, current_group_names=current.group_names,
    )
    return RecordedInputEvaluation(
        analysis=analysis, phase=phase, loop=loop, output_side=impedance_basis, outcome=plan, voltage=voltage, current=current,
        role_refs={key: ref for key, ref in resolved},
        role_units={key: resolve_channel_unit(workspace_id, ref, source_registry=source_registry,
                                              calculated_channel_registry=calculated_channel_registry)
                    for key, ref in resolved},
    )


def resolve_side_plan(**kwargs) -> SidePlan | SideBlock:
    """The plan (or the block) one recorded calculation uses -- never None: there is no legacy path. See
    `evaluate_recorded_input` for the parameters."""
    return evaluate_recorded_input(**kwargs).outcome
