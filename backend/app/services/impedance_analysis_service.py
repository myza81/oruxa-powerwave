"""Impedance Locus orchestration layer (see
docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md).

**Recording mode reuses `app.services.phasor_analysis_service.
compute_phasor_diagram()` verbatim** -- the task's own explicit
instruction: "Recording mode must consume normalized Phasor results
rather than independently reimplementing waveform phasor estimation...
Do not create a second FFT/DFT/RMS estimator inside Impedance." Rather
than re-resolving Va/Ia (or Vb/Ib, Vc/Ic) independently via
`resolve_analysis_inputs()` (which would duplicate `compute_phasor_
diagram()`'s own candidate-fetch/reference-frequency/waveform-form-
eligibility/shared-time-coordinate machinery), this module calls the
existing bay-centric diagram aggregator ONCE and simply reads out
whichever Voltage/Current role pair the selected phase needs. This also
means Impedance automatically benefits from every one of that function's
own guardrails (reference-frequency conflict, timebase incompatibility,
waveform-form eligibility) with zero duplicated code.

Never persisted -- every result is derived fresh from current
context/channel state, exactly like Phasor/Overcurrent.
"""

from __future__ import annotations

from app.domain.impedance import (
    IMPEDANCE_BASIS_SECONDARY,
    IMPEDANCE_STATUS_AMBIGUOUS,
    IMPEDANCE_STATUS_COMPUTED,
    IMPEDANCE_STATUS_MISSING,
    IMPEDANCE_STATUS_NEEDS_CONFIGURATION,
    IMPEDANCE_STATUS_NOT_ELIGIBLE,
    REASON_CURRENT_TOO_SMALL,
    REASON_INVALID_RATIO,
    ImpedanceAnalysisResult,
    ImpedanceLocusPoint,
    ManualImpedanceResult,
    compute_impedance_point,
    convert_impedance_basis,
    evaluate_manual_impedance,
    impedance_ratio_valid,
)
from app.domain.phasor import ROLE_STATUS_AVAILABLE, ManualPhasorRoleInput
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.phasor_analysis_service import compute_phasor_diagram
from app.services.workspace_registry import WorkspaceRegistry

#: Role-status -> Impedance-status mapping for whichever of the two roles
#: (Voltage, Current) ends up "worse" -- reuses the SAME five-value
#: vocabulary `compute_phasor_diagram()` already returns per role
#: (`available`/`missing`/`needs_configuration`/`ambiguous`/
#: `not_eligible`), never inventing a new one.
_ROLE_STATUS_PRECEDENCE = (
    IMPEDANCE_STATUS_NEEDS_CONFIGURATION, IMPEDANCE_STATUS_AMBIGUOUS, IMPEDANCE_STATUS_NOT_ELIGIBLE, IMPEDANCE_STATUS_MISSING,
)


def _worse_role_status(voltage_role, current_role) -> tuple[str, str | None]:
    """Neither role being `available` blocks the OTHER independently the
    way Phasor's own six-role diagram allows -- Impedance always needs
    BOTH V and I together, so whichever one failed (or the more
    "blocking" of the two, if both failed) determines the whole result's
    status/reason. Precedence order mirrors how severe each condition
    is -- a genuine cross-role blocking condition
    (`needs_configuration`) outranks a simple `missing` role."""
    statuses = {voltage_role.status, current_role.status}
    for status in _ROLE_STATUS_PRECEDENCE:
        if status in statuses:
            reason = voltage_role.reason_code if voltage_role.status == status else current_role.reason_code
            return status, reason
    return IMPEDANCE_STATUS_MISSING, None


def compute_impedance_analysis(
    *,
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    analysis_time: float,
    reference_frequency_hz_override: float | None,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    ct_primary: float | None,
    ct_secondary: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> ImpedanceAnalysisResult:
    """Selected-time-only Recording-mode Impedance for ONE phase
    (`Za`/`Zb`/`Zc`). `recording_basis` describes the basis the
    RESOLVED Va/Vb/Vc and Ia/Ib/Ic channels' own `magnitude_rms` values
    already represent (mirrors Overcurrent's own `recording_basis`
    concept, extended to cover Voltage too since Impedance needs both);
    `impedance_basis` is the INDEPENDENT desired OUTPUT basis (task's own
    section 11 -- never inferred from `recording_basis`). Ratios
    (`vt_primary`/`vt_secondary`/`ct_primary`/`ct_secondary`) are only
    required, and only validated, when a genuine conversion is needed
    (`recording_basis != impedance_basis`) -- if they already match, `Z =
    V/I` is returned directly with zero ratio dependency, exactly
    matching the task's own golden-example convention (section 22: "same
    basis," no CT/VT involved at all)."""
    diagram = compute_phasor_diagram(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz_override=reference_frequency_hz_override,
        context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
    )

    def _short_circuit(status: str, *, reason_code: str | None, message: str) -> ImpedanceAnalysisResult:
        return ImpedanceAnalysisResult(
            status=status, engineering_context_id=engineering_context_id, phase=phase, analysis_time=analysis_time,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            reason_code=reason_code, message=message,
        )

    if diagram.status != "computed":
        return _short_circuit(diagram.status, reason_code=diagram.reason_code, message=diagram.message)

    voltage_role = diagram.roles.get("V" + phase.lower())
    current_role = diagram.roles.get("I" + phase.lower())
    if voltage_role is None or current_role is None:
        return _short_circuit(IMPEDANCE_STATUS_NEEDS_CONFIGURATION, reason_code="unsupported_phase", message="Unsupported phase.")

    if voltage_role.status != ROLE_STATUS_AVAILABLE or current_role.status != ROLE_STATUS_AVAILABLE:
        status, reason = _worse_role_status(voltage_role, current_role)
        return _short_circuit(status, reason_code=reason, message="One or both required phasors are not available for this phase.")

    needs_ratios = recording_basis != impedance_basis
    if needs_ratios and not (
        vt_primary is not None and vt_secondary is not None and ct_primary is not None and ct_secondary is not None
        and impedance_ratio_valid(vt_primary, vt_secondary) and impedance_ratio_valid(ct_primary, ct_secondary)
    ):
        return _short_circuit(
            IMPEDANCE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_INVALID_RATIO,
            message="Valid VT and CT ratios are required to convert between Recording and Impedance basis.",
        )

    point = compute_impedance_point(
        voltage_role.magnitude_rms, voltage_role.angle_deg_absolute, current_role.magnitude_rms, current_role.angle_deg_absolute,
    )
    if point is None:
        return ImpedanceAnalysisResult(
            status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
            voltage_magnitude_rms=voltage_role.magnitude_rms, voltage_unit=voltage_role.unit,
            current_magnitude_rms=current_role.magnitude_rms, current_unit=current_role.unit,
            reason_code=REASON_CURRENT_TOO_SMALL, message="Current too small for reliable impedance calculation.",
        )

    point_out = convert_impedance_basis(
        point, from_basis=recording_basis, to_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
    )

    return ImpedanceAnalysisResult(
        status=IMPEDANCE_STATUS_COMPUTED, engineering_context_id=engineering_context_id, phase=phase,
        analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
        voltage_magnitude_rms=voltage_role.magnitude_rms, voltage_unit=voltage_role.unit,
        current_magnitude_rms=current_role.magnitude_rms, current_unit=current_role.unit,
        resistance_ohm=point_out.resistance_ohm, reactance_ohm=point_out.reactance_ohm,
        magnitude_ohm=point_out.magnitude_ohm, angle_deg=point_out.angle_deg,
        message="Impedance computed.",
    )


#: Hard cap on locus sample count -- task's own explicit "avoid excessive
#: point counts" instruction. A caller-requested `point_count` above this
#: is clamped, never rejected outright (an oversized request is a benign
#: mistake, not a real error).
MAX_LOCUS_POINTS = 300


def compute_impedance_locus(
    *,
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    start_time: float,
    end_time: float,
    point_count: int,
    reference_frequency_hz_override: float | None,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    ct_primary: float | None,
    ct_secondary: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> list[ImpedanceLocusPoint]:
    """The static locus/trajectory (task's own section 18-19) --
    deterministic, independent of Playback speed: sampled once, on
    context/phase/settings/time-range change, NEVER by accumulating
    animation-frame samples during playback and never per Playback tick
    (the caller/frontend owns caching this result and only re-fetches it
    on a genuine settings change -- the exact same pattern Overcurrent's
    own `.../overcurrent-curve` endpoint already established for its
    characteristic geometry). `point_count` evenly samples
    `[start_time, end_time]` inclusive (a single-point range -- `start_time
    == end_time` -- degenerates to one point, never a division by zero).
    Each sample independently calls `compute_impedance_analysis()` --
    never a second estimator -- so a point outside the recording's own
    valid window is reported with whatever `status`/`reason_code` that
    call naturally produces, never silently dropped (a caller/frontend
    renders only the `computed` points as the path, per task's own
    "no invalid point should reach the plot" requirement)."""
    count = max(1, min(int(point_count), MAX_LOCUS_POINTS))
    if count == 1 or end_time <= start_time:
        sample_times = [start_time]
    else:
        step = (end_time - start_time) / (count - 1)
        sample_times = [start_time + i * step for i in range(count)]

    points: list[ImpedanceLocusPoint] = []
    for t in sample_times:
        result = compute_impedance_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, phase=phase, analysis_time=t,
            reference_frequency_hz_override=reference_frequency_hz_override,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
        )
        points.append(ImpedanceLocusPoint(
            analysis_time=t, status=result.status,
            resistance_ohm=result.resistance_ohm, reactance_ohm=result.reactance_ohm,
            magnitude_ohm=result.magnitude_ohm, angle_deg=result.angle_deg, reason_code=result.reason_code,
        ))
    return points


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode -- Analysis Input Source = "manual" (see
# docs/project-memory/ANALYSIS_INPUT_SOURCE.md). No registry/resolver/
# workspace access at all -- a standalone engineering-calculator path,
# thin orchestration wrapper mirroring `overcurrent_analysis_service.
# compute_overcurrent_manual_analysis()`/`phasor_analysis_service.
# compute_phasor_manual_diagram()`'s own placement.
# ---------------------------------------------------------------------------


def compute_impedance_manual(
    *,
    phase_label: str,
    voltage_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    current_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
    impedance_basis: str,
    voltage_input: ManualPhasorRoleInput,
    current_input: ManualPhasorRoleInput,
) -> ManualImpedanceResult:
    return evaluate_manual_impedance(
        voltage_input, current_input, phase_label=phase_label,
        voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        impedance_basis=impedance_basis,
    )
