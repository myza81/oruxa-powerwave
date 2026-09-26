"""Line-to-Line Voltage calculated channels -- readiness + atomic creation
(DEC-115; see docs/project-memory/LINE_TO_LINE_VOLTAGE.md).

Input model: the engineer picks ONE Bay / Engineering Context, never
individual Va/Vb/Vc channels. The phase voltages are resolved by the SAME
authorities Analysis uses -- nothing here detects phases from names:

- role identity (Voltage + canonical phase A/B/C, ambiguity, phase
  identity missing): `resolve_analysis_inputs()` via
  `check_phasor_diagram_readiness()`;
- waveform representation (instantaneous vs RMS/magnitude, metadata
  first, multi-window detector fallback) and reference-frequency
  agreement: the same `check_phasor_diagram_readiness()` preflight
  (restricted to Va/Vb/Vc).

On top of that, this module adds only the guardrails specific to
subtracting two phase voltages: the resolved channel must be a genuine
phase-to-neutral Voltage magnitude (not a DEC-078 Voltage ANGLE channel,
not an already line-to-line calculated channel), the two phases' units
must be identical (DEC-047 rule, no conversion layer), and their
timebases must be proven aligned (`timebases_aligned()`, never
resampling).

Only the INSTANTANEOUS source path is implemented. The complex-phasor
path (RMS L-L magnitude from |V|/angle phasors) is deliberately deferred
-- see the design document for the exact architectural gap. RMS-only
phase voltages are therefore rejected with an actionable reason, never
combined as `VA_RMS - VB_RMS`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.analysis_input_resolution import (
    REASON_PHASE_IDENTITY_MISSING,
    REASON_ROLE_MISSING,
    STATUS_AMBIGUOUS,
    STATUS_RESOLVED,
)
from app.domain.calculated_channel import (
    DEFAULT_NULL_POLICY,
    MAX_NAME_LENGTH,
    NULL_POLICY_REQUIRE_MANUAL,
    CalculatedChannel,
    ChannelRef,
    timebases_aligned,
    units_compatible,
    values_all_finite,
    would_create_cycle,
)
from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    VOLTAGE,
    WAVEFORM_FORM_INSTANTANEOUS,
)
from app.domain.line_to_line_voltage import (
    OP_LINE_TO_LINE_VOLTAGE,
    OUTPUT_ALL_THREE,
    PAIR_OPERANDS,
    PAIR_ORDER,
    PHASE_BY_ROLE_KEY,
    PHASE_ROLE_KEYS,
    ROLE_KEY_BY_PHASE,
    SOURCE_PATH_INSTANTANEOUS,
    default_output_name,
    evaluate_line_to_line_instantaneous,
    output_valid,
    pairs_for_output,
)
from app.domain.engineering_context import context_phase_display
from app.domain.per_unit import derive_per_unit_profile_id
from app.domain.phase_identity import CANONICAL_PHASE_DISPLAY, PhaseDisplayConvention, phase_symbol_text
from app.domain.phasor import REASON_WAVEFORM_FORM_NOT_ELIGIBLE
from app.domain.voltage_reference import LINE_TO_LINE
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    _effective_input_values,
    _resolve_input,
    _validate_null_policy_configuration,
)
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import (
    CyclicDependencyError,
    DuplicateCalculatedChannelNameError,
    EngineeringContextNotFoundError,
    InvalidCalculatedChannelNameError,
    InvalidLineToLineOutputError,
    LineToLineInputsUnavailableError,
    RequireManualValueNullError,
)
from app.services.per_unit_registry import PerUnitRegistry
from app.services.phasor_analysis_service import check_phasor_diagram_readiness
from app.services.workspace_registry import WorkspaceRegistry

# ---- Per-role readiness vocabulary ----
ROLE_READY = "ready"
ROLE_MISSING = "missing"
ROLE_AMBIGUOUS = "ambiguous"
ROLE_PHASE_IDENTITY_MISSING = "phase_identity_missing"
ROLE_UNSUPPORTED_REPRESENTATION = "unsupported_representation"
ROLE_NEEDS_CONFIGURATION = "needs_configuration"

# ---- Context-level summary vocabulary (owner section 31) ----
CONTEXT_READY = "ready"
CONTEXT_INCOMPLETE = "incomplete"
CONTEXT_UNSUPPORTED_REPRESENTATION = "unsupported_representation"
CONTEXT_AMBIGUOUS = "ambiguous"

#: The owner-worded, actionable reason shown whenever a phase voltage is
#: RMS/magnitude-only (or cannot be confirmed instantaneous).
UNSUPPORTED_REPRESENTATION_MESSAGE = (
    "Line-to-line voltage requires either instantaneous phase voltages or full complex phase "
    "phasors. RMS magnitudes alone are insufficient."
)


@dataclass(slots=True)
class PhaseRoleReadiness:
    role_key: str
    status: str
    message: str | None
    channel_ref: ChannelRef | None = None
    channel_label: str | None = None
    unit: str | None = None


@dataclass(slots=True)
class OutputReadiness:
    output: str
    available: bool
    reason: str | None


@dataclass(slots=True)
class LineToLineContextReadiness:
    engineering_context_id: str
    display_name: str
    status: str
    summary: str
    source_path: str | None
    roles: dict[str, PhaseRoleReadiness] = field(default_factory=dict)
    outputs: dict[str, OutputReadiness] = field(default_factory=dict)
    #: DEC-118: how this bay spells its phases (A->R for an R/Y/B bay).
    #: Every user-facing symbol in `summary`/messages already uses it;
    #: role keys, output keys and `phase_member` stay canonical.
    phase_display: PhaseDisplayConvention = CANONICAL_PHASE_DISPLAY


def _channel_label(ref: ChannelRef, calc_registry: CalculatedChannelRegistry, workspace_id: str) -> str:
    if ref.kind == "source":
        return ref.channel_name
    calc = calc_registry.get(workspace_id, ref.calculated_channel_id)
    return calc.name if calc is not None else ref.calculated_channel_id


def _representation_violation(
    ref: ChannelRef, *, workspace_id: str, source_registry: WorkspaceRegistry, calc_registry: CalculatedChannelRegistry
) -> str | None:
    """The phase-to-neutral guardrail beyond role identity: a resolved
    "Voltage, phase A" channel must be a phase VOLTAGE magnitude, not a
    DEC-078 angle channel (which shares the broad Voltage type) and not a
    quantity already declared line-to-line. Returns a reason, or `None`."""
    if ref.kind == "source":
        active = source_registry.get(workspace_id, ref.source_id)
        channel = (
            next((ch for ch in active.metadata.analog_channels if ch.name == ref.channel_name), None)
            if active is not None
            else None
        )
        if channel is None:
            return "channel is no longer available"
        if channel.engineering_quantity in (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, ENGINEERING_QUANTITY_CURRENT_ANGLE):
            return "resolves to an angle channel, not a phase voltage"
        if channel.engineering_type != VOLTAGE:
            return "is not a Voltage channel"
        return None
    calc = calc_registry.get(workspace_id, ref.calculated_channel_id)
    if calc is None:
        return "channel is no longer available"
    if calc.engineering_type != VOLTAGE:
        return "is not a Voltage channel"
    if calc.voltage_representation == LINE_TO_LINE:
        return "is already a line-to-line quantity, not a phase-to-neutral voltage"
    return None


def _role_label(role_key: str, display: PhaseDisplayConvention) -> str:
    """User-facing plain symbol for a phase role key in this bay's own
    convention (DEC-118): "Va" -> "VA" (A/B/C) or "VR" (R/Y/B). Messages
    carry this; `role_key` itself stays the canonical internal key."""
    return phase_symbol_text("V", PHASE_BY_ROLE_KEY[role_key], display)


def _role_from_phasor_readiness(
    role_key: str, readiness, candidate, display: PhaseDisplayConvention
) -> PhaseRoleReadiness:
    label = _role_label(role_key, display)
    phase_letter = display.symbol(PHASE_BY_ROLE_KEY[role_key])
    if readiness.status == STATUS_RESOLVED:
        return PhaseRoleReadiness(role_key=role_key, status=ROLE_READY, message=None)
    if readiness.status == STATUS_AMBIGUOUS:
        return PhaseRoleReadiness(
            role_key=role_key, status=ROLE_AMBIGUOUS,
            message=f"{label} is ambiguous: more than one phase-{phase_letter} voltage in this bay. "
            "Resolve it in the Engineering Context.",
        )
    if readiness.reason_code == REASON_ROLE_MISSING:
        return PhaseRoleReadiness(role_key=role_key, status=ROLE_MISSING, message=f"{label} missing.")
    if readiness.reason_code == REASON_PHASE_IDENTITY_MISSING:
        return PhaseRoleReadiness(
            role_key=role_key, status=ROLE_PHASE_IDENTITY_MISSING,
            message=f"{label}: phase identity not confirmed. Assign phases in the Engineering Context.",
        )
    if readiness.reason_code == REASON_WAVEFORM_FORM_NOT_ELIGIBLE:
        return PhaseRoleReadiness(
            role_key=role_key, status=ROLE_UNSUPPORTED_REPRESENTATION,
            message=f"{label} is not a confirmed instantaneous waveform. {UNSUPPORTED_REPRESENTATION_MESSAGE}",
        )
    if candidate is None and readiness.reason_code == "channel_unavailable":
        return PhaseRoleReadiness(role_key=role_key, status=ROLE_MISSING, message=f"{label} could not be read.")
    return PhaseRoleReadiness(
        role_key=role_key, status=ROLE_NEEDS_CONFIGURATION, message=readiness.message or f"{label} is not usable.",
    )


def _pair_label(pair: str, display: PhaseDisplayConvention) -> str:
    return phase_symbol_text("V", pair, display)


def check_line_to_line_readiness(
    *,
    workspace_id: str,
    engineering_context_id: str,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> LineToLineContextReadiness:
    """Per-role and per-output readiness for one Engineering Context --
    the ONE authority both the selector UI and creation consult (creation
    re-derives it server-side, never trusting a client verdict)."""
    context = context_registry.get(workspace_id, engineering_context_id)
    if context is None:
        raise EngineeringContextNotFoundError(f"No Engineering Context '{engineering_context_id}' in this workspace.")
    display = context_phase_display(context)

    phasor_readiness = check_phasor_diagram_readiness(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        reference_frequency_hz_override=None, context_registry=context_registry,
        source_registry=source_registry, calculated_channel_registry=calc_registry,
        role_keys=PHASE_ROLE_KEYS,
    )

    roles: dict[str, PhaseRoleReadiness] = {}
    for role_key in PHASE_ROLE_KEYS:
        candidate = phasor_readiness.candidates.get(role_key)
        role = _role_from_phasor_readiness(role_key, phasor_readiness.role_readiness[role_key], candidate, display)
        if candidate is not None:
            role.channel_ref = candidate.channel_ref
            role.channel_label = _channel_label(candidate.channel_ref, calc_registry, workspace_id)
            role.unit = candidate.unit
            violation = _representation_violation(
                candidate.channel_ref, workspace_id=workspace_id, source_registry=source_registry,
                calc_registry=calc_registry,
            )
            if violation is not None:
                role.status = ROLE_UNSUPPORTED_REPRESENTATION
                role.message = f"{_role_label(role_key, display)} ({role.channel_label}) {violation}."
            elif role.status == ROLE_UNSUPPORTED_REPRESENTATION:
                role.message = (
                    f"{_role_label(role_key, display)} ({role.channel_label}) is not a confirmed instantaneous waveform. "
                    f"{UNSUPPORTED_REPRESENTATION_MESSAGE}"
                )
        roles[role_key] = role

    outputs: dict[str, OutputReadiness] = {}
    for pair in PAIR_ORDER:
        from_key, to_key = (ROLE_KEY_BY_PHASE[p] for p in PAIR_OPERANDS[pair])
        blocking = [roles[k] for k in (from_key, to_key) if roles[k].status != ROLE_READY]
        if blocking:
            outputs[pair] = OutputReadiness(output=pair, available=False, reason=blocking[0].message)
            continue
        a, b = phasor_readiness.candidates[from_key], phasor_readiness.candidates[to_key]
        if not units_compatible([a.unit, b.unit], [VOLTAGE, VOLTAGE]):
            outputs[pair] = OutputReadiness(
                output=pair, available=False,
                reason=f"{_role_label(from_key, display)} ({a.unit or 'no unit'}) and "
                f"{_role_label(to_key, display)} ({b.unit or 'no unit'}) use different "
                "units and cannot be subtracted.",
            )
            continue
        if not timebases_aligned(
            a.reference_source_id, a.time, a.start_epoch, b.reference_source_id, b.time, b.start_epoch,
        ):
            outputs[pair] = OutputReadiness(
                output=pair, available=False,
                reason=f"{_role_label(from_key, display)} and {_role_label(to_key, display)} sample times are not "
                "aligned; resampling is never performed.",
            )
            continue
        outputs[pair] = OutputReadiness(output=pair, available=True, reason=None)

    all_available = all(outputs[p].available for p in PAIR_ORDER)
    first_blocked = next((outputs[p] for p in PAIR_ORDER if not outputs[p].available), None)
    outputs[OUTPUT_ALL_THREE] = OutputReadiness(
        output=OUTPUT_ALL_THREE, available=all_available,
        reason=None if all_available else (first_blocked.reason if first_blocked else None),
    )

    available_pairs = [p for p in PAIR_ORDER if outputs[p].available]
    role_statuses = {r.status for r in roles.values()}
    if all_available:
        status, summary = CONTEXT_READY, "Ready for All Three"
    else:
        blocking_messages = [r.message for r in roles.values() if r.status != ROLE_READY and r.message]
        detail = blocking_messages[0] if blocking_messages else (first_blocked.reason if first_blocked else "")
        if ROLE_AMBIGUOUS in role_statuses:
            status = CONTEXT_AMBIGUOUS
        elif not available_pairs and ROLE_UNSUPPORTED_REPRESENTATION in role_statuses:
            status = CONTEXT_UNSUPPORTED_REPRESENTATION
        else:
            status = CONTEXT_INCOMPLETE
        if available_pairs:
            summary = "Ready for " + ", ".join(_pair_label(p, display) for p in available_pairs) + " only — " + detail
        else:
            summary = detail or "Not available"

    return LineToLineContextReadiness(
        engineering_context_id=context.id,
        display_name=context.display_name,
        status=status,
        summary=summary,
        source_path=SOURCE_PATH_INSTANTANEOUS if available_pairs else None,
        roles=roles,
        outputs=outputs,
        phase_display=display,
    )


def list_line_to_line_readiness(
    *,
    workspace_id: str,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> list[LineToLineContextReadiness]:
    """Every Engineering Context in the workspace, INCLUDING incomplete/
    unsupported ones (owner section 11/31: never hide a bay -- show why)."""
    return [
        check_line_to_line_readiness(
            workspace_id=workspace_id, engineering_context_id=context.id, context_registry=context_registry,
            source_registry=source_registry, calc_registry=calc_registry,
        )
        for context in context_registry.list_for_workspace(workspace_id)
    ]


def create_line_to_line_voltage_channels(
    *,
    workspace_id: str,
    engineering_context_id: str,
    output: str,
    names: dict[str, str] | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
    per_unit_registry: PerUnitRegistry | None = None,
    null_policy: str = DEFAULT_NULL_POLICY,
    estimation_method: str | None = None,
    max_gap_value: int | None = None,
    max_gap_unit: str | None = None,
    local_mean_radius: int | None = None,
) -> list[CalculatedChannel]:
    """Create one (VAB/VBC/VCA) or all three line-to-line channels.

    ATOMIC: every check -- output, null-policy configuration, readiness
    of EVERY required pair, every name -- and every evaluation completes
    before anything is written. If any requested output is unavailable,
    nothing is created (All Three is never a partial set). Each output is
    an ordinary, individually usable/deletable `CalculatedChannel`; an
    All Three request stamps a shared `creation_batch_id` for UI grouping
    only."""
    if not output_valid(output):
        raise InvalidLineToLineOutputError(f"Unsupported line-to-line output {output!r}. Use AB, BC, CA or all_three.")

    estimation_method_out, max_gap_value_out, max_gap_unit_out, local_mean_radius_out = (
        _validate_null_policy_configuration(
            null_policy=null_policy, estimation_method=estimation_method, max_gap_value=max_gap_value,
            max_gap_unit=max_gap_unit, local_mean_radius=local_mean_radius,
        )
    )

    readiness = check_line_to_line_readiness(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        context_registry=context_registry, source_registry=source_registry, calc_registry=calc_registry,
    )
    requested_pairs = pairs_for_output(output)
    unavailable = [readiness.outputs[p] for p in requested_pairs if not readiness.outputs[p].available]
    if unavailable:
        display = readiness.phase_display
        details = "; ".join(f"{_pair_label(o.output, display)}: {o.reason}" for o in unavailable)
        raise LineToLineInputsUnavailableError(
            f"Cannot create {'All Three' if output == OUTPUT_ALL_THREE else _pair_label(output, display)} for "
            f"{readiness.display_name} — nothing was created. {details}"
        )

    existing_names = {c.name for c in calc_registry.list_for_workspace(workspace_id)}
    planned_names: dict[str, str] = {}
    for pair in requested_pairs:
        raw = (names or {}).get(pair)
        clean = (
            raw if raw is not None else default_output_name(readiness.display_name, pair, readiness.phase_display)
        ).strip()
        if not clean:
            raise InvalidCalculatedChannelNameError(
                f"Name for {_pair_label(pair, readiness.phase_display)} must not be empty."
            )
        if len(clean) > MAX_NAME_LENGTH:
            raise InvalidCalculatedChannelNameError(f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
        if clean in existing_names or clean in planned_names.values():
            raise DuplicateCalculatedChannelNameError(f"A calculated channel named '{clean}' already exists.")
        planned_names[pair] = clean

    resolved_by_role = {}
    for pair in requested_pairs:
        for phase in PAIR_OPERANDS[pair]:
            role_key = ROLE_KEY_BY_PHASE[phase]
            if role_key not in resolved_by_role:
                resolved_by_role[role_key] = _resolve_input(
                    readiness.roles[role_key].channel_ref, workspace_id=workspace_id,
                    source_registry=source_registry, calc_registry=calc_registry,
                )

    if null_policy == NULL_POLICY_REQUIRE_MANUAL:
        for role_key, r in resolved_by_role.items():
            if not values_all_finite(r.values):
                raise RequireManualValueNullError(
                    f"Cannot create with Require Manual Value: {_role_label(role_key, readiness.phase_display)} "
                    f"({readiness.roles[role_key].channel_label}) contains missing/invalid (null) values."
                )

    role_keys = list(resolved_by_role)
    effective = dict(zip(role_keys, _effective_input_values(
        [resolved_by_role[k] for k in role_keys], null_policy=null_policy,
        estimation_method=estimation_method_out, max_gap_value=max_gap_value_out,
        local_mean_radius=local_mean_radius_out,
    )))

    batch_id = ("llb-" + uuid4().hex) if len(requested_pairs) > 1 else None
    dependency_map = {c.id: c.dependency_ids for c in calc_registry.list_for_workspace(workspace_id)}
    created_at = datetime.now(timezone.utc)
    channels: list[CalculatedChannel] = []
    for pair in requested_pairs:
        from_key, to_key = (ROLE_KEY_BY_PHASE[p] for p in PAIR_OPERANDS[pair])
        from_ref = readiness.roles[from_key].channel_ref
        to_ref = readiness.roles[to_key].channel_ref
        first = resolved_by_role[from_key]
        dependency_ids = [ref.calculated_channel_id for ref in (from_ref, to_ref) if ref.kind == "calculated"]
        calc_id = "calc-" + uuid4().hex
        if would_create_cycle(dependency_map, calc_id, dependency_ids):
            raise CyclicDependencyError("This calculation would create a circular dependency.")
        channels.append(CalculatedChannel(
            id=calc_id,
            workspace_id=workspace_id,
            name=planned_names[pair],
            unit=first.unit or resolved_by_role[to_key].unit or "",
            operation=OP_LINE_TO_LINE_VOLTAGE,
            inputs=[from_ref, to_ref],
            parameters={
                "pair": pair,
                "source_path": SOURCE_PATH_INSTANTANEOUS,
                "engineering_context_id": readiness.engineering_context_id,
                "engineering_context_name": readiness.display_name,
                # DEC-118: the display convention this channel was named
                # and labelled with, snapshotted so its system-default name
                # and formula stay recognisable even if the bay's phases are
                # later corrected. `phase_member` stays canonical.
                "phase_display": readiness.phase_display.to_dict(),
            },
            dependency_ids=dependency_ids,
            reference_source_id=first.reference_source_id,
            time=first.time,
            values=evaluate_line_to_line_instantaneous(effective[from_key], effective[to_key]),
            created_at=created_at,
            engineering_type=VOLTAGE,
            waveform_form=WAVEFORM_FORM_INSTANTANEOUS,
            null_policy=null_policy,
            estimation_method=estimation_method_out,
            max_gap_value=max_gap_value_out,
            max_gap_unit=max_gap_unit_out,
            local_mean_radius=local_mean_radius_out,
            voltage_representation=LINE_TO_LINE,
            phase_member=pair,
            creation_batch_id=batch_id,
        ))

    # Commit phase: in-memory adds cannot fail after the validation above,
    # but roll back defensively so a partial set can never survive.
    added: list[str] = []
    try:
        for channel in channels:
            calc_registry.add(channel)
            added.append(channel.id)
    except Exception:
        for calc_id in added:
            calc_registry.remove(workspace_id, calc_id)
        raise

    if per_unit_registry is not None:
        for channel in channels:
            input_profile_ids = [
                per_unit_registry.profile_for_channel(workspace_id, ref, VOLTAGE) for ref in channel.inputs
            ]
            per_unit_registry.set_auto_assignment_for_calculated_channel(
                workspace_id, channel.id, derive_per_unit_profile_id(OP_LINE_TO_LINE_VOLTAGE, input_profile_ids)
            )
    return channels
