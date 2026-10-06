"""Compliance & Capability -- Reference-driven Measurement readiness and
shared preparation (DEC-167; see docs/project-memory/COMPLIANCE_CAPABILITY.md).

> **Reference defines. Measurement satisfies.**
> **Compliance never owns a private RMS channel or private per-unit
> configuration.**

The active Reference Layer(s) fix the unit, voltage representation and
phase evaluation (`app.domain.compliance_requirement.resolve_requirement`).
This module checks whether the selected Measurement Group can satisfy
every active Reference and reports ONE of three honest states per
Reference (and overall):

- `ready`            everything required can be produced as it stands;
- `action_required`  the recording CAN satisfy it, but a shared
                     preparation/configuration step is still missing
                     (an RMS calculated channel; a per-unit base);
- `incompatible`     it cannot be satisfied safely (missing phase,
                     angle-less RMS where phasors are needed, ambiguous
                     metadata, a Reference that states too little).

**Orchestrator, never an owner.** Everything a preparation step creates is
an ordinary shared resource:

- RMS -> `calculated_channel_service.create_calculated_channel(OP_RMS)`,
  an ordinary Calculated Channel in the shared registry (visible to
  Calculated Channels/Waveform/Table/Analysis at once);
- line-to-line voltage derived from instantaneous phases -> the existing
  `line_to_line_voltage_service` (DEC-115), never a Compliance-private
  derivation;
- per-unit base -> the existing Measurement/Voltage Group configuration,
  read through `build_group_view()`; this module can only REPORT a missing
  base (the UI sends the engineer to the existing group editor) and never
  writes one.

**Reuse is by calculation identity, never by name.** An RMS channel is
equivalent when it is `operation=rms` over the SAME input `ChannelRef`
with the SAME `nominal_frequency_hz` and the same null policy; a
line-to-line channel when it is `operation=line_to_line_voltage` with the
same pair over the same two input refs. Equivalent channels are reused;
a source channel that is already RMS is used directly and never wrapped.

**Electrical safety is unchanged** (DEC-101): a direct measured
VAB/VBC/VCA is used as-is; a line-line quantity is derived only from two
INSTANTANEOUS phases (time-domain subtraction in the L-L service, then
RMS); angle-less RMS phase magnitudes are never combined
(`incompatible`), and `sqrt(3) * VLN` is never used.

**One narrow, read-only Engineering Context lookup (DEC-167 amendment to
DEC-100/101).** The shared line-to-line service is keyed by Engineering
Context. When -- and only when -- a line-to-line calculated channel must be
created, this module asks `EngineeringContextRegistry.context_for_channel()`
which context already owns the two phase channels and hands that id to the
shared service. Compliance still registers as no Engineering Context
consumer, creates/updates no context, and treats the group (not the
context) as its bay. No matching context -> the step is reported as needing
manual action rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.assessment_definition import MEMBER_A, MEMBER_B, MEMBER_C
from app.domain.calculated_channel import (
    DEFAULT_NULL_POLICY,
    OP_RMS,
    CalculatedChannel,
    ChannelRef,
    nominal_frequency_valid,
)
from app.domain.compliance_measurement import ROLE_A, ROLE_B, ROLE_C
from app.domain.compliance_requirement import (
    MEMBER_POSITIVE_SEQUENCE,
    READINESS_ACTION_REQUIRED,
    READINESS_INCOMPATIBLE,
    READINESS_NO_REFERENCE,
    READINESS_READY,
    LINE_LINE_MEMBERS,
    MeasurementRequirement,
    resolve_requirement,
)
from app.domain.line_to_line_voltage import (
    OP_LINE_TO_LINE_VOLTAGE,
    PAIR_OPERANDS,
    default_output_name,
)
from app.domain.measurement_group import KIND_VOLTAGE, MeasurementGroup
from app.domain.phase_identity import CANONICAL_PHASE_DISPLAY, PhaseDisplayConvention
from app.domain.reference_layer import ReferenceLayer
from app.domain.reference_profile import ReferenceProfile
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.compliance_series import Registries, timebase_key, unit_problem
from app.services.compliance_measurement_service import (
    INPUT_TYPE_INSTANTANEOUS,
    INPUT_TYPE_RMS,
    BaseInfo,
    RoleResolution,
    _base_for_group,
    _catalogue_from_detected,
    _classify_input_type,
    _detect_group_members,
    _phase_display_from_detected,
    _role_text,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import (
    ComplianceMeasurementGroupNotVoltageKindError,
    MeasurementGroupNotFoundError,
)
from app.services.line_to_line_voltage_service import (
    check_line_to_line_readiness,
    create_line_to_line_voltage_channels,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.reference_layer_registry import ReferenceLayerRegistry
from app.services.reference_profile_registry import ReferenceProfileRegistry
from app.services.reference_profile_service import get_profile_entry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

# ---- per-member states ------------------------------------------------
STATE_SOURCE_RMS = "source_rms"                    # the source channel is already RMS: used directly
STATE_REUSED = "reused"                            # an equivalent shared calculated channel exists
STATE_NEEDS_RMS = "needs_rms"                      # an RMS calculated channel must be created
STATE_NEEDS_LINE_LINE = "needs_line_to_line"       # a line-to-line calculated channel must be created first
STATE_DERIVED_AT_ASSESSMENT = "derived_at_assessment"  # phasor-derived at assessment time; nothing to prepare
STATE_BLOCKED = "blocked"                          # satisfiable, but not preparable here (needs manual action)
STATE_INCOMPATIBLE = "incompatible"

STEP_RMS = "rms"
STEP_LINE_TO_LINE = "line_to_line"

_ROLE_BY_MEMBER = {MEMBER_A: ROLE_A, MEMBER_B: ROLE_B, MEMBER_C: ROLE_C}
_PHASE_OPERAND_ROLE = {"A": ROLE_A, "B": ROLE_B, "C": ROLE_C}


@dataclass(frozen=True, slots=True)
class PreparationStep:
    """One shared resource that is missing. Deduplicated across
    References by `key`, so two References needing RMS(VAB) create it once."""

    kind: str  # STEP_RMS | STEP_LINE_TO_LINE
    key: tuple
    description: str
    executable: bool
    reason: str | None = None
    input_ref: ChannelRef | None = None          # STEP_RMS
    pair: str | None = None                      # STEP_LINE_TO_LINE
    operand_refs: tuple[ChannelRef, ChannelRef] | None = None
    engineering_context_id: str | None = None
    nominal_frequency_hz: float | None = None


@dataclass(frozen=True, slots=True)
class MemberReadiness:
    member: str
    state: str
    message: str | None = None
    channel_name: str | None = None
    calculated_channel_id: str | None = None
    #: The shared channel the trace is read from, once the member is satisfied
    #: (`source_rms` / `reused`). `None` while something still has to be prepared.
    channel_ref: ChannelRef | None = None
    step: PreparationStep | None = None


@dataclass(frozen=True, slots=True)
class ReferenceReadiness:
    layer_id: str
    profile_id: str
    profile_name: str
    requirement: MeasurementRequirement
    status: str
    message: str | None
    members: tuple[MemberReadiness, ...]
    #: `not_required` | `ready` | `action_required`
    unit_state: str
    unit_message: str | None


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    measurement_group_id: str
    status: str
    references: tuple[ReferenceReadiness, ...]
    steps: tuple[PreparationStep, ...]
    base: BaseInfo | None
    needs_base: bool
    phase_display: PhaseDisplayConvention = CANONICAL_PHASE_DISPLAY


@dataclass(frozen=True, slots=True)
class PreparationOutcome:
    created: tuple[CalculatedChannel, ...]
    result: ReadinessResult


# ---------------------------------------------------------------- identity

def find_equivalent_rms(
    calc_registry: CalculatedChannelRegistry, workspace_id: str, input_ref: ChannelRef, nominal_frequency_hz: float,
) -> CalculatedChannel | None:
    """An existing RMS calculated channel with the SAME calculation
    identity -- never matched by name."""
    for channel in calc_registry.list_for_workspace(workspace_id):
        if (
            channel.operation == OP_RMS
            and channel.inputs == [input_ref]
            and channel.null_policy == DEFAULT_NULL_POLICY
            and channel.parameters.get("nominal_frequency_hz") == nominal_frequency_hz
        ):
            return channel
    return None


def find_equivalent_line_to_line(
    calc_registry: CalculatedChannelRegistry, workspace_id: str, pair: str, operand_refs: tuple[ChannelRef, ChannelRef],
) -> CalculatedChannel | None:
    for channel in calc_registry.list_for_workspace(workspace_id):
        if (
            channel.operation == OP_LINE_TO_LINE_VOLTAGE
            and channel.parameters.get("pair") == pair
            and channel.inputs == list(operand_refs)
            and channel.null_policy == DEFAULT_NULL_POLICY
        ):
            return channel
    return None


def _nominal_frequency_for(
    ref: ChannelRef, *, workspace_id: str, source_registry: WorkspaceRegistry, calc_registry: CalculatedChannelRegistry,
) -> float | None:
    source_id = ref.source_id
    if ref.kind == "calculated":
        channel = calc_registry.get(workspace_id, ref.calculated_channel_id)
        source_id = channel.reference_source_id if channel is not None else None
    if source_id is None:
        return None
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        return None
    frequency = active.metadata.nominal_frequency
    return float(frequency) if nominal_frequency_valid(frequency) else None


def _display_name(ref: ChannelRef, *, workspace_id: str, calc_registry: CalculatedChannelRegistry) -> str:
    if ref.kind == "calculated":
        channel = calc_registry.get(workspace_id, ref.calculated_channel_id)
        return channel.name if channel is not None else ref.calculated_channel_id
    return ref.channel_name


# --------------------------------------------------------------- evaluation

@dataclass
class _Context:
    workspace_id: str
    group: MeasurementGroup
    catalogue: dict[str, RoleResolution]
    display: PhaseDisplayConvention
    source_registry: WorkspaceRegistry
    calc_registry: CalculatedChannelRegistry
    context_registry: EngineeringContextRegistry
    registries: Registries | None = None
    input_types: dict[ChannelRef, str | None] = field(default_factory=dict)

    def input_type(self, ref: ChannelRef) -> str | None:
        if ref not in self.input_types:
            self.input_types[ref] = _classify_input_type(
                ref, workspace_id=self.workspace_id, source_registry=self.source_registry,
            )
        return self.input_types[ref]


def _role_ref(ctx: _Context, role: str) -> tuple[ChannelRef | None, str | None]:
    """`(ref, problem)` for one canonical role within the group."""
    resolution = ctx.catalogue.get(role)
    if resolution is None:
        return None, f"{_role_text(role, ctx.display)} is missing from the selected Measurement Group."
    if len(resolution.candidates) > 1:
        return None, (
            f"Multiple {_role_text(role, ctx.display)} channels match within the selected Measurement Group; "
            "resolve the naming conflict first."
        )
    return resolution.candidates[0].channel_ref, None


def _rms_step_or_state(ctx: _Context, member: str, ref: ChannelRef, *, label: str) -> MemberReadiness:
    """A resolved channel that is an instantaneous waveform (or a
    calculated channel derived from one): reuse an equivalent RMS channel,
    else describe the RMS channel that has to be created."""
    frequency = _nominal_frequency_for(
        ref, workspace_id=ctx.workspace_id, source_registry=ctx.source_registry, calc_registry=ctx.calc_registry,
    )
    name = _display_name(ref, workspace_id=ctx.workspace_id, calc_registry=ctx.calc_registry)
    if frequency is None:
        step = PreparationStep(
            kind=STEP_RMS, key=(STEP_RMS, ref), description=f"RMS of {name}", executable=False, input_ref=ref,
            reason="The recording's nominal frequency is unknown, so Powerwave will not guess an RMS window.",
        )
        return MemberReadiness(
            member=member, state=STATE_BLOCKED, channel_name=name, step=step,
            message=f"{label}: fundamental RMS is required, but the nominal frequency of this recording is unknown. "
                    "Create the RMS channel in Calculated Channels with an explicit frequency.",
        )
    existing = find_equivalent_rms(ctx.calc_registry, ctx.workspace_id, ref, frequency)
    if existing is not None:
        return MemberReadiness(
            member=member, state=STATE_REUSED, channel_name=existing.name, calculated_channel_id=existing.id,
            channel_ref=ChannelRef(kind="calculated", calculated_channel_id=existing.id),
            message=f"{label}: existing RMS calculated channel '{existing.name}' is reused.",
        )
    step = PreparationStep(
        kind=STEP_RMS, key=(STEP_RMS, ref, frequency), description=f"RMS of {name}", executable=True,
        input_ref=ref, nominal_frequency_hz=frequency,
    )
    return MemberReadiness(
        member=member, state=STATE_NEEDS_RMS, channel_name=name, step=step,
        message=f"{label}: fundamental RMS of {name} needs to be prepared.",
    )


def _line_to_line_context_id(ctx: _Context, pair: str, operands: tuple[ChannelRef, ChannelRef]) -> tuple[str | None, str | None]:
    """The Engineering Context whose shared line-to-line service can build
    this pair from exactly these two channels (see module docstring), or
    `(None, reason)`."""
    ids = {ctx.context_registry.context_for_channel(ctx.workspace_id, ref) for ref in operands}
    if len(ids) != 1 or None in ids:
        return None, "No single Engineering Context owns both phase channels, so the shared line-to-line service cannot be used."
    context_id = next(iter(ids))
    try:
        readiness = check_line_to_line_readiness(
            workspace_id=ctx.workspace_id, engineering_context_id=context_id, context_registry=ctx.context_registry,
            source_registry=ctx.source_registry, calc_registry=ctx.calc_registry,
        )
    except Exception as exc:  # noqa: BLE001 -- any shared-service refusal is "not preparable here", never a crash
        return None, str(exc)
    phase_a, phase_b = PAIR_OPERANDS[pair]
    role_key = {"A": "Va", "B": "Vb", "C": "Vc"}
    expected = (readiness.roles[role_key[phase_a]].channel_ref, readiness.roles[role_key[phase_b]].channel_ref)
    if expected != operands:
        return None, "The Engineering Context resolves different phase channels than the selected Measurement Group."
    if not readiness.outputs[pair].available:
        return None, readiness.outputs[pair].reason or "The shared line-to-line service reports this pair unavailable."
    return context_id, None


def _plan_phase_ground(ctx: _Context, member: str) -> MemberReadiness:
    role = _ROLE_BY_MEMBER[member]
    label = _role_text(role, ctx.display)
    ref, problem = _role_ref(ctx, role)
    if ref is None:
        return MemberReadiness(member=member, state=STATE_INCOMPATIBLE, message=problem)
    return _plan_direct_channel(ctx, member, ref, label)


def _plan_direct_channel(ctx: _Context, member: str, ref: ChannelRef, label: str) -> MemberReadiness:
    input_type = ctx.input_type(ref)
    if input_type is None:
        return MemberReadiness(
            member=member, state=STATE_INCOMPATIBLE,
            message=f"Could not confidently determine whether {label} is Instantaneous or RMS. "
                    "Powerwave does not guess this from the channel name.",
        )
    if input_type == INPUT_TYPE_RMS:
        return MemberReadiness(
            member=member, state=STATE_SOURCE_RMS, channel_name=ref.channel_name, channel_ref=ref,
            message=f"{label}: the source channel '{ref.channel_name}' is already RMS and is used directly.",
        )
    return _rms_step_or_state(ctx, member, ref, label=label)


def _plan_line_line(ctx: _Context, pair: str) -> MemberReadiness:
    label = _role_text(pair, ctx.display)
    if pair in ctx.catalogue:  # a direct, measured line-line channel is authoritative and used as-is
        ref, problem = _role_ref(ctx, pair)
        if ref is None:
            return MemberReadiness(member=pair, state=STATE_INCOMPATIBLE, message=problem)
        return _plan_direct_channel(ctx, pair, ref, label)

    phase_a, phase_b = PAIR_OPERANDS[pair]
    refs: list[ChannelRef] = []
    for phase in (phase_a, phase_b):
        ref, problem = _role_ref(ctx, _PHASE_OPERAND_ROLE[phase])
        if ref is None:
            return MemberReadiness(member=pair, state=STATE_INCOMPATIBLE, message=f"{label} cannot be derived: {problem}")
        refs.append(ref)
    types = [ctx.input_type(r) for r in refs]
    if any(t is None for t in types):
        return MemberReadiness(
            member=pair, state=STATE_INCOMPATIBLE,
            message=f"{label} cannot be derived: Powerwave could not confidently determine whether the phase "
                    "channels are Instantaneous or RMS, and does not guess it from the channel name.",
        )
    if any(t == INPUT_TYPE_RMS for t in types):
        return MemberReadiness(
            member=pair, state=STATE_INCOMPATIBLE,
            message=f"{label} requires simultaneous phase information. The phase channels are already-RMS "
                    "magnitudes with no phase angle, so a line-line quantity would need an unsafe "
                    "balanced-system assumption during a disturbance. Provide a measured "
                    f"{label} channel or instantaneous phase voltages.",
        )
    operands = (refs[0], refs[1])
    existing = find_equivalent_line_to_line(ctx.calc_registry, ctx.workspace_id, pair, operands)
    if existing is not None:
        ll_ref = ChannelRef(kind="calculated", calculated_channel_id=existing.id)
        result = _rms_step_or_state(ctx, pair, ll_ref, label=label)
        return result
    context_id, reason = _line_to_line_context_id(ctx, pair, operands)
    step = PreparationStep(
        kind=STEP_LINE_TO_LINE, key=(STEP_LINE_TO_LINE, pair, operands), description=f"Line-line voltage {label}",
        executable=context_id is not None, reason=reason, pair=pair, operand_refs=operands,
        engineering_context_id=context_id,
    )
    if context_id is None:
        return MemberReadiness(
            member=pair, state=STATE_BLOCKED, step=step,
            message=f"{label} has to be derived from instantaneous phases as a shared line-to-line calculated "
                    f"channel, but it cannot be prepared here: {reason} Create it in Calculated Channels.",
        )
    return MemberReadiness(
        member=pair, state=STATE_NEEDS_LINE_LINE, step=step,
        message=f"{label} has to be derived from instantaneous phases (a shared line-to-line calculated "
                "channel), then RMS.",
    )


def _plan_positive_sequence(ctx: _Context) -> MemberReadiness:
    refs: list[ChannelRef] = []
    for role in (ROLE_A, ROLE_B, ROLE_C):
        ref, problem = _role_ref(ctx, role)
        if ref is None:
            return MemberReadiness(member=MEMBER_POSITIVE_SEQUENCE, state=STATE_INCOMPATIBLE, message=f"Positive sequence needs all three phases: {problem}")
        refs.append(ref)
    types = [ctx.input_type(r) for r in refs]
    if any(t is None for t in types):
        return MemberReadiness(
            member=MEMBER_POSITIVE_SEQUENCE, state=STATE_INCOMPATIBLE,
            message="Positive sequence cannot be assessed: the phase channels' Instantaneous/RMS form is ambiguous.",
        )
    if any(t == INPUT_TYPE_RMS for t in types):
        return MemberReadiness(
            member=MEMBER_POSITIVE_SEQUENCE, state=STATE_INCOMPATIBLE,
            message="Positive sequence requires simultaneous complex phasors, which requires Instantaneous input. "
                    "The phase channels are already-RMS magnitudes with no phase angle.",
        )
    return MemberReadiness(
        member=MEMBER_POSITIVE_SEQUENCE, state=STATE_INCOMPATIBLE,
        message="The phase channels are instantaneous, but no positive-sequence voltage time series can be "
                "produced from them yet (no shared sequence-voltage channel exists), so it cannot be plotted "
                "against the Reference.",
    )


def _plan_member(ctx: _Context, requirement: MeasurementRequirement, member: str) -> MemberReadiness:
    if member == MEMBER_POSITIVE_SEQUENCE:
        return _plan_positive_sequence(ctx)
    if member in LINE_LINE_MEMBERS:
        return _plan_line_line(ctx, member)
    return _plan_phase_ground(ctx, member)


def _plottable_problem(
    ctx: _Context, profile: ReferenceProfile, members: tuple[MemberReadiness, ...],
) -> tuple[str, str | None]:
    """`(severity, problem)`; severity is `"action"` (the engineer can fix it)
    or `"incompatible"`. `(.., None)` when every trace can be produced."""
    if ctx.registries is None:
        return "incompatible", None
    refs = [m.channel_ref for m in members]
    if any(ref is None for ref in refs):
        return "incompatible", "A required measurement channel could not be resolved."
    for ref in refs:
        problem = unit_problem(ref, profile.unit, workspace_id=ctx.workspace_id, reg=ctx.registries)
        if problem is not None:
            return ("action" if profile.unit == "pu" else "incompatible"), problem
    treatment = profile.assessment_definition.phase_treatment
    if treatment in ("minimum", "maximum") and len(refs) > 1:
        keys = {timebase_key(ref, workspace_id=ctx.workspace_id, reg=ctx.registries) for ref in refs}
        if len(keys) != 1 or None in keys:
            return "incompatible", (
                "The required voltages are not on one proven common time base, so the "
                f"{treatment} across them cannot be formed without resampling."
            )
    return "incompatible", None


def _evaluate_reference(
    ctx: _Context, layer: ReferenceLayer, profile: ReferenceProfile, base: BaseInfo | None,
) -> ReferenceReadiness:
    requirement = resolve_requirement(profile.assessment_definition, profile.unit)

    unit_state = "not_required"
    unit_message: str | None = None
    if requirement.requires_per_unit:
        if base is not None:
            unit_state = "ready"
        else:
            unit_state = "action_required"
            unit_message = "Per-unit assessment requires a configured voltage base."

    if requirement.unresolved_reason is not None:
        return ReferenceReadiness(
            layer_id=layer.id, profile_id=profile.id, profile_name=profile.name, requirement=requirement,
            status=READINESS_INCOMPATIBLE, message=requirement.unresolved_reason + " Edit the Reference Profile.",
            members=(), unit_state=unit_state, unit_message=unit_message,
        )

    members = tuple(_plan_member(ctx, requirement, m) for m in requirement.required_members)

    # The resolved base channels of one Reference must agree on Instantaneous
    # vs RMS -- they cannot be combined into one assessment otherwise.
    base_types = {t for t in (ctx.input_types.get(r) for r in list(ctx.input_types)) if t is not None}
    mixed = len(base_types) > 1 and not any(m.state == STATE_INCOMPATIBLE for m in members)
    if mixed:
        members = tuple(
            MemberReadiness(member=m.member, state=STATE_INCOMPATIBLE, message=(
                "The resolved phase channels do not agree on Instantaneous vs RMS representation -- "
                "they cannot be combined into one assessment."))
            for m in members
        )

    incompatible = [m for m in members if m.state == STATE_INCOMPATIBLE]
    needs_action = [m for m in members if m.state in (STATE_NEEDS_RMS, STATE_NEEDS_LINE_LINE, STATE_BLOCKED)]
    if incompatible:
        status, message = READINESS_INCOMPATIBLE, incompatible[0].message
    elif needs_action or unit_state == "action_required":
        status = READINESS_ACTION_REQUIRED
        message = (needs_action[0].message if needs_action else unit_message)
    else:
        # "Ready" must mean the measurement product can actually be resolved
        # for comparison: every member has a shared channel, it can be shown
        # in the Reference's unit, and (minimum/maximum) the members share one
        # time base. Metadata readiness alone is not Ready (DEC-169).
        severity, problem = _plottable_problem(ctx, profile, members)
        if problem is None:
            status, message = READINESS_READY, None
        elif severity == "action":
            # A per-unit configuration exists but does not apply yet (e.g. the
            # group is not confirmed): the engineer can fix it -> Configure Base.
            status, message = READINESS_ACTION_REQUIRED, problem
            unit_state, unit_message = "action_required", problem
        else:
            status, message = READINESS_INCOMPATIBLE, problem
    return ReferenceReadiness(
        layer_id=layer.id, profile_id=profile.id, profile_name=profile.name, requirement=requirement,
        status=status, message=message, members=members, unit_state=unit_state, unit_message=unit_message,
    )


def evaluate_readiness(
    *,
    workspace_id: str,
    measurement_group_id: str,
    source_registry: WorkspaceRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    calc_registry: CalculatedChannelRegistry,
    context_registry: EngineeringContextRegistry,
    layer_registry: ReferenceLayerRegistry,
    profile_registry: ReferenceProfileRegistry,
    per_unit_registry: PerUnitRegistry | None = None,
) -> ReadinessResult:
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    if group.kind != KIND_VOLTAGE:
        raise ComplianceMeasurementGroupNotVoltageKindError(
            f"Measurement group '{measurement_group_id}' is a Current group, not a Voltage group."
        )

    detected = _detect_group_members(group, workspace_id=workspace_id, source_registry=source_registry)
    ctx = _Context(
        workspace_id=workspace_id, group=group, catalogue=_catalogue_from_detected(detected),
        display=_phase_display_from_detected(detected), source_registry=source_registry,
        calc_registry=calc_registry, context_registry=context_registry,
        registries=(
            Registries(
                source=source_registry, calc=calc_registry, per_unit=per_unit_registry, group=group_registry,
                voltage_config=voltage_config_registry, current_config=current_config_registry,
            )
            if per_unit_registry is not None else None
        ),
    )
    base = _base_for_group(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )

    references: list[ReferenceReadiness] = []
    for layer in sorted(layer_registry.list_for_workspace(workspace_id), key=lambda l: l.order):
        if not layer.visible:
            continue  # a hidden layer is excluded from the comparison, so it imposes no requirement
        entry = get_profile_entry(workspace_id, layer.profile_id, custom_registry=profile_registry)
        if entry is None:
            continue
        ctx.input_types = {}  # the Instantaneous/RMS agreement check is per Reference
        references.append(_evaluate_reference(ctx, layer, entry.profile, base))

    steps: dict[tuple, PreparationStep] = {}
    for reference in references:
        for member in reference.members:
            if member.step is not None:
                steps.setdefault(member.step.key, member.step)

    if not references:
        status = READINESS_NO_REFERENCE
    elif any(r.status == READINESS_INCOMPATIBLE for r in references):
        status = READINESS_INCOMPATIBLE
    elif any(r.status == READINESS_ACTION_REQUIRED for r in references):
        status = READINESS_ACTION_REQUIRED
    else:
        status = READINESS_READY
    needs_base = any(r.unit_state == "action_required" for r in references)
    return ReadinessResult(
        measurement_group_id=measurement_group_id, status=status, references=tuple(references),
        steps=tuple(steps.values()), base=base, needs_base=needs_base, phase_display=ctx.display,
    )


# -------------------------------------------------------------- preparation

def _unique_name(calc_registry: CalculatedChannelRegistry, workspace_id: str, base_name: str) -> str:
    taken = {c.name for c in calc_registry.list_for_workspace(workspace_id)}
    if base_name not in taken:
        return base_name
    index = 2
    while f"{base_name} ({index})" in taken:
        index += 1
    return f"{base_name} ({index})"


def prepare_measurement(
    *,
    workspace_id: str,
    measurement_group_id: str,
    source_registry: WorkspaceRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    calc_registry: CalculatedChannelRegistry,
    context_registry: EngineeringContextRegistry,
    layer_registry: ReferenceLayerRegistry,
    profile_registry: ReferenceProfileRegistry,
    per_unit_registry: PerUnitRegistry,
) -> PreparationOutcome:
    """Creates ONLY the missing shared resources, through the shared
    services, reusing anything equivalent that already exists. Never writes
    a per-unit base and never guesses an engineering setting. Idempotent:
    a second call creates nothing."""
    created: list[CalculatedChannel] = []

    def evaluate() -> ReadinessResult:
        return evaluate_readiness(
            workspace_id=workspace_id, measurement_group_id=measurement_group_id, source_registry=source_registry,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry, calc_registry=calc_registry,
            context_registry=context_registry, layer_registry=layer_registry, profile_registry=profile_registry,
            per_unit_registry=per_unit_registry,
        )

    for _ in range(3):  # line-line first, then the RMS that depends on it
        result = evaluate()
        runnable = [s for s in result.steps if s.executable]
        if not runnable:
            break
        for step in sorted(runnable, key=lambda s: 0 if s.kind == STEP_LINE_TO_LINE else 1):
            if step.kind == STEP_LINE_TO_LINE:
                phase_display = result.phase_display
                context = context_registry.get(workspace_id, step.engineering_context_id)
                name = _unique_name(
                    calc_registry, workspace_id, default_output_name(context.display_name, step.pair, phase_display),
                )
                created.extend(create_line_to_line_voltage_channels(
                    workspace_id=workspace_id, engineering_context_id=step.engineering_context_id, output=step.pair,
                    names={step.pair: name}, context_registry=context_registry, source_registry=source_registry,
                    calc_registry=calc_registry, per_unit_registry=per_unit_registry,
                ))
            else:
                source_name = _display_name(step.input_ref, workspace_id=workspace_id, calc_registry=calc_registry)
                created.append(create_calculated_channel(
                    workspace_id=workspace_id, name=_unique_name(calc_registry, workspace_id, f"RMS ({source_name})"),
                    operation=OP_RMS, inputs=[step.input_ref],
                    parameters={"nominal_frequency_hz": step.nominal_frequency_hz},
                    source_registry=source_registry, calc_registry=calc_registry, per_unit_registry=per_unit_registry,
                ))
    return PreparationOutcome(created=tuple(created), result=evaluate())
