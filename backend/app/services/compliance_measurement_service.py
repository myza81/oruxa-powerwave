"""Compliance & Capability -- Voltage Measurement service layer (Slice
2 + the 2026-09-20 UAT correction; see docs/project-memory/
COMPLIANCE_CAPABILITY.md).

**UAT correction (2026-09-20): role resolution is now scoped to an
explicitly SELECTED Measurement Group, never the whole workspace.**
Owner UAT identified that a workspace-wide quantity resolution is
ambiguous the moment more than one bay/Measurement Group exists (a
`Va` in Bay A and a `Va` in Bay B are both real, valid channels -- there
is no naming conflict to "resolve," just two different bays). The
corrected workflow: select a Bay/Measurement Group FIRST, then role
resolution/normalization happens only against that group's own
`channel_refs`. This reuses the EXISTING `app.domain.measurement_group`
model as the sole source of truth for "what is a bay" -- no second,
Compliance-specific bay/group concept was introduced (task section 1's
own explicit instruction).

Orchestrates ELIGIBILITY resolution for one Voltage assessment quantity
against ONE selected Measurement Group's own member channels -- which
of them satisfy the quantity's required roles, whether their own
recorded representation (instantaneous vs already-RMS) is known
confidently enough to proceed, and whether that group's own Per-Unit
base is available for display. **This module deliberately never calls
`app.domain.phasor.estimate_phasor()` or `app.domain.compliance_
measurement.compute_voltage_quantity_value()`** -- Compliance has no
selected-time/Playback concept yet (DEC-100; Event Alignment/t0 is
explicitly out of scope for this slice), so there is no meaningful
instant to compute an actual numeric value AT. Everything this module
reports (status, resolved input channels, input representation,
"derived as" label, base metadata) is determinable from channel-level
metadata alone, without evaluating a single sample value -- keeping the
live "switch assessment quantity"/"switch group" path cheap (task
section 21) and honest about what Slice 2 actually provides.
`compute_voltage_quantity_value()` and `estimate_phasor()` are exercised
directly by this feature's own golden domain/service tests using
synthetic waveforms, proving the computation path correct and ready for
a later slice's actual selected-time wiring, without this module
pretending to expose it today.

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
UI shared with Analysis, no shared Analysis workspace lifecycle hook,
no Playback/Analysis Input Source coupling) -- its OWN Bay/Measurement
Group selector (this correction) is a completely separate, pre-existing
model (`app.domain.measurement_group`), not Engineering Context. See
DECISIONS.md#dec-101 and #dec-102 for the full record of this boundary.

**A Measurement Group's own channel_refs now scope detection input
directly (task section 11) -- a group may legitimately span more than
one loaded source**, so this module groups a selected group's own
`channel_refs` by `source_id` and runs `detect_engineering_contexts()`
once per represented source (that function's own single-source-only
design), flattening every detected member's phase across those sources
into one group-scoped `phase -> channel` map. Because every resolved
role is now, by construction, a member of the ONE selected group, a
resolved role can never span two different Measurement Groups any
more -- the previous cross-group `STATUS_INVALID_BASE` trigger is
structurally unreachable through this path and was removed; Base is now
simply "does the selected group have a configured Voltage base," a
single lookup via `app.services.measurement_group_view_service.
build_group_view()` (verbatim, no new base-resolution math -- task
section 9).
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
from app.domain.measurement_group import KIND_VOLTAGE, MeasurementGroup
from app.domain.rms_detector import LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS, classify_waveform_form
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import (
    ComplianceMeasurementGroupNotVoltageKindError,
    MeasurementGroupNotFoundError,
    UnknownComplianceQuantityError,
)
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
    """One canonical phase role's own resolution WITHIN the selected
    Measurement Group. `candidates` may legitimately contain more than
    one entry (two differently-named member channels of the SAME group
    both parsing to the same phase -- a real, if unusual, grouping
    situation) -- never silently picked from, always surfaced as
    ambiguous by the caller. This is no longer cross-bay: two channels
    in DIFFERENT groups that both happen to be named "VA" never appear
    together here, since this function only ever looks at one group's
    own membership (task section 7)."""

    role: str
    candidates: tuple[ResolvedRole, ...]


def list_compliance_voltage_groups(
    *, workspace_id: str, group_registry: MeasurementGroupRegistry
) -> list[MeasurementGroup]:
    """The Bay/Measurement Group picker's own candidate list -- EVERY
    Voltage-kind group in the workspace, of ANY status.

    2026-09-23 UAT correction: this used to exclude `STATUS_NEEDS_REVIEW`
    at this layer, which silently collapsed "groups exist but need
    review" into "no groups is available for this workspace" -- the
    exact owner-reported dead end this correction fixes (task section
    10: "It may be appropriate to expose two collections: usable_groups,
    review_required_groups... rather than pretending review-required
    groups do not exist"). This function now returns the raw,
    authoritative registry state; bucketing into usable vs review-
    required is the CALLER's job (the API layer's response already
    carries each group's own `status`, and the frontend buckets by it --
    see `wwComplianceRenderGroupOptions()`'s own `needs_review` filter
    for the SELECTABLE dropdown specifically, which still never lets an
    engineer pick a contested group's own membership without reviewing
    it first via the existing Measurement Groups management UI)."""
    return [
        group for group in group_registry.list_for_workspace(workspace_id)
        if group.kind == KIND_VOLTAGE
    ]


def resolve_voltage_role_catalogue_for_group(
    group: MeasurementGroup, *, workspace_id: str, source_registry: WorkspaceRegistry
) -> dict[str, RoleResolution]:
    """Builds `canonical phase role -> RoleResolution` from ONLY the
    selected group's own `channel_refs` -- never the whole workspace
    (task section 4/7). A group may span more than one source (task
    section 11: "do not assume one group == one file"), so membership is
    grouped by `source_id` first and `detect_engineering_contexts()`
    (single-source-only by design) is run once per represented source,
    fed ONLY that source's member channels (never that source's full
    channel list) -- flattening every detected member's phase across
    those source-scoped passes into one group-scoped map. A channel
    whose detected phase is unknown/not_applicable/neutral is simply
    absent from the returned map under any of this catalogue's own role
    keys (Compliance Slice 2 has no use for `N`/`unknown`/`L1`-etc.
    roles)."""
    refs_by_source: dict[str, list[str]] = {}
    for ref in group.channel_refs:
        if ref.kind != "source" or ref.source_id is None or ref.channel_name is None:
            continue
        refs_by_source.setdefault(ref.source_id, []).append(ref.channel_name)

    catalogue: dict[str, list[ResolvedRole]] = {}
    for source_id, member_names in refs_by_source.items():
        active = source_registry.get(workspace_id, source_id)
        if active is None:
            continue
        member_name_set = set(member_names)
        voltage_channels = [
            ch for ch in active.metadata.analog_channels
            if ch.engineering_type == VOLTAGE and ch.name in member_name_set
        ]
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
                    channel_ref=ChannelRef(kind="source", source_id=source_id, channel_name=member.channel_name),
                    channel_name=member.channel_name,
                    source_id=source_id,
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


def _base_for_group(
    group: MeasurementGroup,
    *,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> BaseInfo | None:
    """The selected group's OWN Voltage base, if configured -- `None` is
    the normal, non-error "no base configured yet, show engineering
    units" case (task section 16/9). Every resolved role is, by
    construction, a member of `group` (see `resolve_voltage_role_
    catalogue_for_group()`), so there is no longer a "resolved roles
    span two different groups" case to detect here at all -- that
    cross-group conflict is now structurally unreachable, not merely
    unlikely."""
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    voltage_config = view.voltage_config
    if voltage_config is None or voltage_config.nominal_voltage_ll_kv is None or voltage_config.effective_reference is None:
        return None
    return BaseInfo(
        nominal_voltage_ll_kv=voltage_config.nominal_voltage_ll_kv,
        effective_reference=voltage_config.effective_reference,
    )


def evaluate_voltage_measurement(
    *,
    workspace_id: str,
    measurement_group_id: str,
    quantity_id: str,
    source_registry: WorkspaceRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> ComplianceVoltageMeasurementResult:
    quantity = get_voltage_quantity(quantity_id)
    if quantity is None:
        raise UnknownComplianceQuantityError(f"Unknown Compliance assessment quantity_id '{quantity_id}'.")

    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    if group.kind != KIND_VOLTAGE:
        raise ComplianceMeasurementGroupNotVoltageKindError(
            f"Measurement group '{measurement_group_id}' is a Current group, not a Voltage group."
        )

    catalogue = resolve_voltage_role_catalogue_for_group(group, workspace_id=workspace_id, source_registry=source_registry)

    used_direct_pair = False
    roles_needed: tuple[str, ...]
    if quantity.direct_pair_role is not None and quantity.direct_pair_role in catalogue:
        used_direct_pair = True
        roles_needed = (quantity.direct_pair_role,)
    else:
        roles_needed = quantity.required_single_phase_roles

    missing = [role for role in roles_needed if role not in catalogue]
    if missing:
        required_display = ", ".join(ROLE_DISPLAY_NAME[role] for role in roles_needed)
        missing_display = ", ".join(ROLE_DISPLAY_NAME[role] for role in missing)
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_MISSING_INPUTS, missing=tuple(missing),
            message=f"{quantity.display_label} requires {required_display}. Missing: {missing_display}.",
        )

    ambiguous = [role for role in roles_needed if len(catalogue[role].candidates) > 1]
    if ambiguous:
        ambiguous_display = ", ".join(ROLE_DISPLAY_NAME[role] for role in ambiguous)
        return ComplianceVoltageMeasurementResult(
            quantity=quantity, status=STATUS_AMBIGUOUS_METADATA,
            message=(
                f"Multiple {ambiguous_display} channels match within the selected Measurement Group. "
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

    base = _base_for_group(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )

    return ComplianceVoltageMeasurementResult(
        quantity=quantity, status=STATUS_AVAILABLE, resolved_roles=resolved, used_direct_pair=used_direct_pair,
        input_type=input_type, value_representation=value_representation, base=base,
        assessment_unit=("pu" if base is not None else "engineering_unit"),
    )


def list_voltage_quantities() -> tuple[ComplianceVoltageQuantity, ...]:
    return VOLTAGE_QUANTITIES
