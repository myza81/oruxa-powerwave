"""Compliance & Capability -- Voltage Measurement service layer (Slice
2; see docs/project-memory/COMPLIANCE_CAPABILITY.md).

Orchestrates ELIGIBILITY resolution for one Voltage assessment quantity
against the workspace's currently loaded sources -- which channels
satisfy the quantity's required roles, whether their own recorded
representation (instantaneous vs already-RMS) is known confidently
enough to proceed, and whether a Per-Unit base is available for display.
**This module deliberately never calls `app.domain.phasor.estimate_
phasor()` or `app.domain.compliance_measurement.compute_voltage_
quantity_value()`** -- Compliance has no selected-time/Playback concept
yet (DEC-100; Event Alignment/t0 is explicitly out of scope for this
slice), so there is no meaningful instant to compute an actual numeric
value AT. Everything this module reports (status, resolved input
channels, input representation, "derived as" label, base metadata) is
determinable from channel-level metadata alone, without evaluating a
single sample value -- keeping the live "switch assessment quantity"
path cheap (task section 21) and honest about what Slice 2 actually
provides. `compute_voltage_quantity_value()` and `estimate_phasor()` are
exercised directly by this feature's own golden domain/service tests
(task section 22) using synthetic waveforms, proving the computation
path is correct and ready for a later slice's actual selected-time
wiring, without this module pretending to expose it today.

**Reuses `app.domain.engineering_context_detection.detect_engineering_
contexts()` directly, as a pure function call, for per-channel phase
identity** -- the SAME algorithm Analysis Guardrail Slice 1 already
built and tested, since Compliance's own quantity catalogue (Phase A/B/
C, Line-Line AB/BC/CA, Positive Sequence) fundamentally needs the exact
same "which channel is phase A vs phase B" classification Engineering
Context already solves; duplicating that pattern-matching algorithm
would violate the task's own "reuse existing foundations" instruction.
**This is call-by-value only** -- no `EngineeringContext` object is
created, read, or persisted, and `EngineeringContextRegistry` is never
imported here. Compliance still does not register as an Engineering
Context CONSUMER (DEC-100's own architectural boundary: no Bay selector
UI, no shared Analysis workspace lifecycle hook, no Playback/Analysis
Input Source coupling) -- it independently re-runs the same detection
algorithm, fresh, against whatever sources are currently loaded, every
time the workspace's channel set might have changed. See
DECISIONS.md#dec-101 for the full record of this boundary.

Voltage measurement-group BASE display reuses `app.services.
measurement_group_view_service.build_group_view()` verbatim (no new
base-resolution math) -- Compliance never builds a second base model
(task section 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import (
    VOLTAGE,
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
)
from app.domain.compliance_measurement import (
    ROLE_A,
    ROLE_B,
    ROLE_C,
    STATUS_AMBIGUOUS_METADATA,
    STATUS_AVAILABLE,
    STATUS_INVALID_BASE,
    STATUS_MISSING_INPUTS,
    STATUS_UNSUPPORTED_REPRESENTATION,
    VALUE_REPRESENTATION_DIRECT_RMS,
    VALUE_REPRESENTATION_FUNDAMENTAL_RMS,
    VOLTAGE_QUANTITIES,
    VOLTAGE_REPRESENTATION_LINE_TO_LINE,
    VOLTAGE_REPRESENTATION_POSITIVE_SEQUENCE,
    ComplianceVoltageQuantity,
    get_voltage_quantity,
)
from app.domain.engineering_context_detection import ChannelForDetection, detect_engineering_contexts
from app.domain.measurement_group import KIND_VOLTAGE
from app.domain.rms_detector import LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS, classify_waveform_form
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import UnknownComplianceQuantityError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_view_service import build_group_view
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

#: Display convention matching the task's own literal example wording
#: ("Input: Va, Vb, Vc", "Missing: Vb, Vc"). Public (no leading
#: underscore) -- the API layer reuses this exact mapping for its own
#: `ComplianceResolvedRoleOut.display_name`, never a second copy.
ROLE_DISPLAY_NAME = {
    ROLE_A: "Va", ROLE_B: "Vb", ROLE_C: "Vc",
    "AB": "Vab", "BC": "Vbc", "CA": "Vca",
}

INPUT_TYPE_INSTANTANEOUS = "instantaneous"
INPUT_TYPE_RMS = "rms"


@dataclass(frozen=True, slots=True)
class ResolvedRole:
    channel_ref: ChannelRef
    channel_name: str
    source_id: str


@dataclass(frozen=True, slots=True)
class RoleResolution:
    """One canonical phase role's own resolution against the workspace's
    currently loaded Voltage channels. `candidates` may legitimately
    contain more than one entry (a cross-source or cross-channel name
    collision for the same role) -- never silently picked from, always
    surfaced as ambiguous by the caller."""

    role: str
    candidates: tuple[ResolvedRole, ...]


def resolve_voltage_role_catalogue(*, workspace_id: str, source_registry: WorkspaceRegistry) -> dict[str, RoleResolution]:
    """Builds `canonical phase role -> RoleResolution` across every
    currently loaded source in the workspace, by running `detect_
    engineering_contexts()` independently PER SOURCE (that function is
    single-source-only by design) against ONLY that source's own Voltage
    channels, then flattening every detected member's own phase across
    every source into one workspace-wide map. A channel whose detected
    phase is unknown/not_applicable/neutral is simply absent from the
    returned map under any of this catalogue's own role keys (Compliance
    Slice 2 has no use for `N`/`unknown`/`L1`-etc. roles)."""
    catalogue: dict[str, list[ResolvedRole]] = {}
    for active in source_registry.list_for_workspace(workspace_id):
        voltage_channels = [ch for ch in active.metadata.analog_channels if ch.engineering_type == VOLTAGE]
        if not voltage_channels:
            continue
        detection_input = [
            ChannelForDetection(name=ch.name, engineering_type=ch.engineering_type, phase_label=ch.phase)
            for ch in voltage_channels
        ]
        for detected_context in detect_engineering_contexts(detection_input):
            for member in detected_context.members:
                role = member.phase
                if role not in (ROLE_A, ROLE_B, ROLE_C, "AB", "BC", "CA"):
                    continue
                resolved = ResolvedRole(
                    channel_ref=ChannelRef(kind="source", source_id=active.metadata.source_id, channel_name=member.channel_name),
                    channel_name=member.channel_name,
                    source_id=active.metadata.source_id,
                )
                catalogue.setdefault(role, []).append(resolved)
    return {role: RoleResolution(role=role, candidates=tuple(entries)) for role, entries in catalogue.items()}


def _classify_input_type(channel_ref: ChannelRef, *, workspace_id: str, source_registry: WorkspaceRegistry) -> str | None:
    """Trusted-metadata-first, algorithmic-detector-fallback -- the exact
    same hierarchy `app.services.calculated_channel_service.check_rms_
    eligibility()`/`app.services.phasor_analysis_service._waveform_form_
    eligible()` already established, reused here rather than a third
    reimplementation. Returns `INPUT_TYPE_INSTANTANEOUS`/`INPUT_TYPE_RMS`,
    or `None` for an unresolvable/ambiguous verdict (task section 4:
    "If metadata is ambiguous: do not guess")."""
    active = source_registry.get(workspace_id, channel_ref.source_id)
    if active is None:
        return None
    matching = next((ch for ch in active.metadata.analog_channels if ch.name == channel_ref.channel_name), None)
    if matching is None:
        return None
    if matching.waveform_form == WAVEFORM_FORM_INSTANTANEOUS:
        return INPUT_TYPE_INSTANTANEOUS
    if matching.waveform_form in (WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE):
        return INPUT_TYPE_RMS
    waveform_data = active.record.waveform_data
    time = waveform_data["time"].to_numpy()
    values = waveform_data[channel_ref.channel_name].to_numpy()
    detector_result = classify_waveform_form(time, values, active.metadata.nominal_frequency)
    if detector_result == LIKELY_INSTANTANEOUS:
        return INPUT_TYPE_INSTANTANEOUS
    if detector_result == LIKELY_MAGNITUDE_OR_RMS:
        return INPUT_TYPE_RMS
    return None  # UNCERTAIN -- do not guess.


@dataclass(frozen=True, slots=True)
class BaseInfo:
    nominal_voltage_ll_kv: float
    effective_reference: str  # voltage_reference.LINE_TO_GROUND | LINE_TO_LINE
    assessment_unit: str = "pu"


@dataclass(frozen=True, slots=True)
class ComplianceVoltageMeasurementResult:
    quantity: ComplianceVoltageQuantity
    status: str
    resolved_roles: dict[str, ResolvedRole] = field(default_factory=dict)
    used_direct_pair: bool = False
    input_type: str | None = None
    value_representation: str | None = None
    base: BaseInfo | None = None
    assessment_unit: str = "engineering_unit"
    missing: tuple[str, ...] = ()
    reason_code: str | None = None
    message: str | None = None


def _base_for_resolved_roles(
    resolved: dict[str, ResolvedRole],
    *,
    workspace_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> tuple[BaseInfo | None, str | None]:
    """`(base_info, error_message)`. `error_message` is set only for a
    genuine STATUS_INVALID_BASE condition (resolved roles span more than
    one measurement group, or share a group with mutually-incompatible
    config) -- `(None, None)` is the normal, non-error "no base
    configured yet, show engineering units" case (task section 16 is
    explicit that this is not treated as an error)."""
    group_ids = set()
    for role_result in resolved.values():
        group_id = group_registry.group_for_channel(workspace_id, role_result.channel_ref)
        if group_id is not None:
            group_ids.add(group_id)
    if not group_ids:
        return None, None
    if len(group_ids) > 1:
        return None, (
            "Voltage basis is ambiguous. The resolved phases belong to different measurement groups with "
            "potentially different bases."
        )
    group = group_registry.get(workspace_id, next(iter(group_ids)))
    if group is None or group.kind != KIND_VOLTAGE:
        return None, None
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    voltage_config = view.voltage_config
    if voltage_config is None or voltage_config.nominal_voltage_ll_kv is None or voltage_config.effective_reference is None:
        return None, None
    return BaseInfo(
        nominal_voltage_ll_kv=voltage_config.nominal_voltage_ll_kv,
        effective_reference=voltage_config.effective_reference,
    ), None


def evaluate_voltage_measurement(
    *,
    workspace_id: str,
    quantity_id: str,
    source_registry: WorkspaceRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> ComplianceVoltageMeasurementResult:
    quantity = get_voltage_quantity(quantity_id)
    if quantity is None:
        raise UnknownComplianceQuantityError(f"Unknown Compliance assessment quantity_id '{quantity_id}'.")

    catalogue = resolve_voltage_role_catalogue(workspace_id=workspace_id, source_registry=source_registry)

    used_direct_pair = False
    roles_needed: tuple[str, ...]
    if quantity.direct_pair_role is not None and quantity.direct_pair_role in catalogue:
        used_direct_pair = True
        roles_needed = (quantity.direct_pair_role,)
    else:
        roles_needed = quantity.required_single_phase_roles

    missing = [role for role in roles_needed if role not in catalogue]
    if missing:
        missing_display = ", ".join(ROLE_DISPLAY_NAME[role] for role in missing)
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_MISSING_INPUTS, missing=tuple(missing),
            message=f"Cannot calculate {quantity.display_label}. Missing: {missing_display}.",
        )

    ambiguous = [role for role in roles_needed if len(catalogue[role].candidates) > 1]
    if ambiguous:
        ambiguous_display = ", ".join(ROLE_DISPLAY_NAME[role] for role in ambiguous)
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_AMBIGUOUS_METADATA,
            message=(
                f"Multiple channels match {ambiguous_display} across the loaded recordings. "
                "Resolve the naming conflict before this quantity can be assessed."
            ),
        )

    resolved = {role: catalogue[role].candidates[0] for role in roles_needed}

    input_types: dict[str, str | None] = {
        role: _classify_input_type(entry.channel_ref, workspace_id=workspace_id, source_registry=source_registry)
        for role, entry in resolved.items()
    }
    if any(value is None for value in input_types.values()):
        unresolved_display = ", ".join(ROLE_DISPLAY_NAME[role] for role, value in input_types.items() if value is None)
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_AMBIGUOUS_METADATA, resolved_roles=resolved, used_direct_pair=used_direct_pair,
            message=(
                f"Could not confidently determine whether {unresolved_display} is Instantaneous or RMS. "
                "Powerwave does not guess this from the channel name."
            ),
        )
    distinct_input_types = set(input_types.values())
    if len(distinct_input_types) > 1:
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_AMBIGUOUS_METADATA, resolved_roles=resolved, used_direct_pair=used_direct_pair,
            message=(
                "The resolved phase channels do not agree on Instantaneous vs RMS representation -- "
                "they cannot be combined into one assessment quantity."
            ),
        )
    input_type = next(iter(distinct_input_types))

    needs_angle = (not used_direct_pair) and quantity.voltage_representation in (
        VOLTAGE_REPRESENTATION_LINE_TO_LINE, VOLTAGE_REPRESENTATION_POSITIVE_SEQUENCE,
    )
    if needs_angle and input_type == INPUT_TYPE_RMS:
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_UNSUPPORTED_REPRESENTATION, resolved_roles=resolved,
            used_direct_pair=used_direct_pair, input_type=input_type,
            message=(
                f"{quantity.display_label} requires simultaneous complex phase phasors, which requires "
                "Instantaneous input. The resolved phase channels are already-RMS magnitude-only, with no "
                "phase-angle information -- deriving this quantity would require an unsafe balanced-system "
                "assumption during a disturbance."
            ),
        )

    value_representation = (
        VALUE_REPRESENTATION_FUNDAMENTAL_RMS if input_type == INPUT_TYPE_INSTANTANEOUS else VALUE_REPRESENTATION_DIRECT_RMS
    )

    base, base_error = _base_for_resolved_roles(
        resolved, workspace_id=workspace_id, group_registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )
    if base_error is not None:
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_INVALID_BASE, resolved_roles=resolved, used_direct_pair=used_direct_pair,
            input_type=input_type, value_representation=value_representation, message=base_error,
        )

    return ComplianceVoltageMeasurementResult(
        quantity=quantity, status=STATUS_AVAILABLE, resolved_roles=resolved, used_direct_pair=used_direct_pair,
        input_type=input_type, value_representation=value_representation, base=base,
        assessment_unit=("pu" if base is not None else "engineering_unit"),
    )


def list_voltage_quantities() -> tuple[ComplianceVoltageQuantity, ...]:
    return VOLTAGE_QUANTITIES
