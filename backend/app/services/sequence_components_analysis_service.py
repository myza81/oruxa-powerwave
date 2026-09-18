"""Sequence Components orchestration layer (see
docs/project-memory/SEQUENCE_COMPONENTS_ANALYSIS.md).

**Recording mode reuses `app.services.phasor_analysis_service.
compute_phasor_diagram()` verbatim** -- never a second FFT/DFT/RMS
estimator. Extracts the Va/Vb/Vc (and Ia/Ib/Ic) role triplet the
resolved diagram already produced and, when all three of a family are
`available`, calls `app.domain.sequence_components.
compute_symmetrical_components()`.

**Manual mode reuses `app.domain.phasor.evaluate_manual_phasor_role()`
verbatim per role** -- the SAME six-role, two-independent-basis Manual
Phasor architecture, never a second manual-entry engine. Both Recording
and Manual funnel through the SAME `_evaluate_family()` helper below,
since `evaluate_manual_phasor_role()` returns a `PhasorDiagramRoleResult`
-- the identical shape `compute_phasor_diagram()`'s own `roles` dict
already uses -- so there is exactly ONE family-evaluation/complete-set-
guardrail implementation for both input sources.

Never persisted -- every result is derived fresh from current
context/channel state, exactly like Phasor/Overcurrent/Impedance.
"""

from __future__ import annotations

from app.domain.engineering_units import ENGINEERING_QUANTITY_CURRENT, ENGINEERING_QUANTITY_VOLTAGE
from app.domain.phasor import (
    ROLE_STATUS_AVAILABLE,
    ManualPhasorRoleInput,
    PhasorDiagramRoleResult,
    evaluate_manual_phasor_role,
)
from app.domain.sequence_components import (
    REASON_INCOMPLETE_PHASE_SET,
    SEQUENCE_STATUS_AMBIGUOUS,
    SEQUENCE_STATUS_COMPUTED,
    SEQUENCE_STATUS_MISSING,
    SEQUENCE_STATUS_NEEDS_CONFIGURATION,
    SEQUENCE_STATUS_NOT_ELIGIBLE,
    SequenceAnalysisResult,
    SequenceFamilyResult,
    SequenceManualResult,
    compute_symmetrical_components,
    sequence_ratio_percent,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.phasor_analysis_service import compute_phasor_diagram
from app.services.workspace_registry import WorkspaceRegistry

#: Worst-role-status precedence -- identical shape to
#: `app.services.impedance_analysis_service._ROLE_STATUS_PRECEDENCE`,
#: generalized here to THREE roles (one family) instead of two.
_ROLE_STATUS_PRECEDENCE = (
    SEQUENCE_STATUS_NEEDS_CONFIGURATION, SEQUENCE_STATUS_AMBIGUOUS, SEQUENCE_STATUS_NOT_ELIGIBLE, SEQUENCE_STATUS_MISSING,
)


def _worst_role_status(roles: tuple[PhasorDiagramRoleResult, ...]) -> tuple[str, str | None]:
    statuses = {r.status for r in roles}
    for status in _ROLE_STATUS_PRECEDENCE:
        if status in statuses:
            reason = next((r.reason_code for r in roles if r.status == status), None)
            return status, reason
    return SEQUENCE_STATUS_MISSING, None


def _evaluate_family(
    role_a: PhasorDiagramRoleResult, role_b: PhasorDiagramRoleResult, role_c: PhasorDiagramRoleResult,
) -> SequenceFamilyResult:
    """One family's (Voltage or Current) own sequence-component
    evaluation -- shared by Recording (`diagram.roles`) and Manual
    (`evaluate_manual_phasor_role()` output), since both produce the
    identical `PhasorDiagramRoleResult` shape. Requires ALL THREE roles
    `available` (task's own section 8 "complete-set requirement") before
    calling the transform; otherwise reports the worst of the three
    roles' own statuses, with channel identity still carried through
    whenever known (task's own "Related Waveforms shows source phase
    quantities regardless of sequence-calculation outcome" requirement)."""
    channel_a, channel_b, channel_c = role_a.channel_ref, role_b.channel_ref, role_c.channel_ref
    if role_a.status != ROLE_STATUS_AVAILABLE or role_b.status != ROLE_STATUS_AVAILABLE or role_c.status != ROLE_STATUS_AVAILABLE:
        status, reason = _worst_role_status((role_a, role_b, role_c))
        return SequenceFamilyResult(
            status=status, reason_code=reason if reason is not None else REASON_INCOMPLETE_PHASE_SET,
            phase_a_channel_ref=channel_a, phase_b_channel_ref=channel_b, phase_c_channel_ref=channel_c,
            message="Requires all three phases to be available.",
        )

    triplet = compute_symmetrical_components(
        role_a.magnitude_rms, role_a.angle_deg_absolute,
        role_b.magnitude_rms, role_b.angle_deg_absolute,
        role_c.magnitude_rms, role_c.angle_deg_absolute,
    )
    negative_ratio = sequence_ratio_percent(triplet.negative_magnitude, triplet.positive_magnitude)
    zero_ratio = sequence_ratio_percent(triplet.zero_magnitude, triplet.positive_magnitude)
    return SequenceFamilyResult(
        status=SEQUENCE_STATUS_COMPUTED,
        zero_sequence_magnitude=triplet.zero_magnitude, zero_sequence_angle_deg=triplet.zero_angle_deg,
        positive_sequence_magnitude=triplet.positive_magnitude, positive_sequence_angle_deg=triplet.positive_angle_deg,
        negative_sequence_magnitude=triplet.negative_magnitude, negative_sequence_angle_deg=triplet.negative_angle_deg,
        negative_sequence_ratio_percent=negative_ratio, zero_sequence_ratio_percent=zero_ratio,
        unit=role_a.unit,
        phase_a_channel_ref=channel_a, phase_b_channel_ref=channel_b, phase_c_channel_ref=channel_c,
        message="Sequence components computed.",
    )


def compute_sequence_analysis(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis_time: float,
    reference_frequency_hz_override: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> SequenceAnalysisResult:
    """Selected-time-only Recording-mode Sequence Components -- reuses
    the existing, unchanged `compute_phasor_diagram()` to resolve every
    role, never a second phasor estimator. Voltage and Current families
    are evaluated fully independently (task's own section 8) -- one
    family's own incompleteness never blocks the other. Only a genuine
    whole-diagram blocking condition (reference-frequency conflict,
    timebase incompatibility -- surfaced by `compute_phasor_diagram()`
    itself) ever produces `needs_configuration` for BOTH families
    uniformly."""
    diagram = compute_phasor_diagram(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz_override=reference_frequency_hz_override,
        context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
    )

    if diagram.status != "computed":
        blocked = SequenceFamilyResult(status=SEQUENCE_STATUS_NEEDS_CONFIGURATION, reason_code=diagram.reason_code, message=diagram.message)
        return SequenceAnalysisResult(
            status=diagram.status, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            voltage_sequences=blocked, current_sequences=blocked,
            reason_code=diagram.reason_code, message=diagram.message,
        )

    voltage_sequences = _evaluate_family(diagram.roles["Va"], diagram.roles["Vb"], diagram.roles["Vc"])
    current_sequences = _evaluate_family(diagram.roles["Ia"], diagram.roles["Ib"], diagram.roles["Ic"])

    return SequenceAnalysisResult(
        status="computed", engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
        voltage_sequences=voltage_sequences, current_sequences=current_sequences,
        message="Sequence components evaluated.",
    )


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode -- Analysis Input Source = "manual" (see
# docs/project-memory/ANALYSIS_INPUT_SOURCE.md). No registry/resolver/
# workspace access at all -- a standalone engineering-calculator path,
# reusing `evaluate_manual_phasor_role()` per role (the SAME Manual
# Phasor architecture, never a second manual-entry engine) and the SAME
# `_evaluate_family()` helper Recording mode uses above.
# ---------------------------------------------------------------------------


def compute_sequence_manual(
    *,
    voltage_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    current_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
    role_inputs: dict[str, ManualPhasorRoleInput],
) -> SequenceManualResult:
    """`role_inputs` keys are `"Va"`/`"Vb"`/`"Vc"`/`"Ia"`/`"Ib"`/`"Ic"` --
    the identical six-role shape `compute_phasor_manual_diagram()`
    already uses. `voltage_basis`/`current_basis` (and their own VT/CT
    ratios) are genuinely independent, exactly like Manual Phasor (task's
    own hard requirement -- an engineer can mix a Primary-basis Voltage
    family with a Secondary-basis Current family in the same
    evaluation)."""
    voltage_roles = tuple(
        evaluate_manual_phasor_role(
            role_inputs[key], engineering_quantity=ENGINEERING_QUANTITY_VOLTAGE,
            basis=voltage_basis, ratio_primary=vt_primary, ratio_secondary=vt_secondary,
        )
        for key in ("Va", "Vb", "Vc")
    )
    current_roles = tuple(
        evaluate_manual_phasor_role(
            role_inputs[key], engineering_quantity=ENGINEERING_QUANTITY_CURRENT,
            basis=current_basis, ratio_primary=ct_primary, ratio_secondary=ct_secondary,
        )
        for key in ("Ia", "Ib", "Ic")
    )
    voltage_sequences = _evaluate_family(*voltage_roles)
    current_sequences = _evaluate_family(*current_roles)
    return SequenceManualResult(
        status=SEQUENCE_STATUS_COMPUTED, voltage_sequences=voltage_sequences, current_sequences=current_sequences,
        message="Manual sequence components evaluated.",
    )
