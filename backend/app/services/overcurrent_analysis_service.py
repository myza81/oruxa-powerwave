"""Overcurrent Analysis v1 -- orchestration layer (see
docs/project-memory/OVERCURRENT_ANALYSIS.md).

Mirrors `app.services.phasor_analysis_service.compute_phasor_analysis()`'s
own layering exactly: sits above the pure `app.domain.overcurrent`
estimator/curve/CT-conversion functions, calls the unchanged `resolve_
analysis_inputs()` FIRST (never re-implements role matching or channel-
name parsing), and owns everything the pure domain module does not --
input resolution, sample-array retrieval, reference-frequency selection,
waveform-form eligibility, and settings validation.

Selected-time only -- computes one Overcurrent evaluation at exactly one
`analysis_time`, never a time series, never persisted. Every guardrail
failure (unresolved role, invalid setting, ineligible waveform form,
unavailable RMS window) is returned as an `OvercurrentAnalysisResult`
with an explicit `status`/`reason_code`, never an exception -- only
`EngineeringContextNotFoundError`/`UnknownAnalysisRequirementError` (from
`resolve_analysis_inputs()` itself) propagate, exactly like Phasor's own
precedent.
"""

from __future__ import annotations

from app.domain.analysis_input_resolution import (
    STATUS_AMBIGUOUS,
    STATUS_NEEDS_CONFIGURATION,
    STATUS_NOT_APPLICABLE,
    STATUS_RESOLVED,
)
from app.domain.analysis_requirements import (
    OVERCURRENT_CURRENT_PHASE_A,
    OVERCURRENT_CURRENT_PHASE_B,
    OVERCURRENT_CURRENT_PHASE_C,
)
from app.domain.calculated_channel import ChannelRef, nominal_frequency_valid
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
)
from app.domain.overcurrent import (
    KNOWN_RECORDING_BASES,
    OVERCURRENT_STATUS_COMPUTED,
    REASON_CHANNEL_UNAVAILABLE,
    REASON_INVALID_CT_VALUES,
    REASON_INVALID_PICKUP,
    REASON_INVALID_REFERENCE_FREQUENCY,
    REASON_INVALID_TMS,
    REASON_UNKNOWN_CHARACTERISTIC,
    REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
    OvercurrentAnalysisResult,
    continuous_duration_above_pickup,
    convert_to_relay_secondary,
    ct_values_valid,
    estimate_trailing_rms_at_time,
    evaluate_idmt_operating_time,
    generate_idmt_curve_points,
    get_characteristic,
    known_characteristics,
    pickup_valid,
    tms_valid,
)
from app.domain.rms_detector import LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS, classify_waveform_form
from app.domain.time_grouping import normalize_absolute_datetime
from app.services.analysis_input_resolution_service import resolve_analysis_inputs
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.workspace_registry import WorkspaceRegistry

_REQUIREMENT_BY_PHASE = {
    "A": OVERCURRENT_CURRENT_PHASE_A, "B": OVERCURRENT_CURRENT_PHASE_B, "C": OVERCURRENT_CURRENT_PHASE_C,
}
_ROLE_KEY_BY_PHASE = {"A": "Ia", "B": "Ib", "C": "Ic"}


def _source_start_epoch(active) -> float | None:
    """Locally-owned copy of the same naive-datetime-ambiguity fix every
    other analysis service module in this codebase re-declares rather
    than imports (see `app.domain.engineering_context_detection`'s own
    docstring for the established reasoning)."""
    if active.metadata.start_time is None:
        return None
    return normalize_absolute_datetime(active.metadata.start_time).timestamp()


class _CurrentCandidate:
    __slots__ = ("channel_ref", "time", "values", "unit", "waveform_form", "start_epoch", "nominal_frequency")

    def __init__(self, *, channel_ref, time, values, unit, waveform_form, start_epoch, nominal_frequency):
        self.channel_ref = channel_ref
        self.time = time
        self.values = values
        self.unit = unit
        self.waveform_form = waveform_form
        self.start_epoch = start_epoch
        self.nominal_frequency = nominal_frequency


def _fetch_current_candidate(
    channel_ref: ChannelRef, *, workspace_id: str,
    source_registry: WorkspaceRegistry, calculated_channel_registry: CalculatedChannelRegistry,
) -> _CurrentCandidate | None:
    """Fetches the resolved current role's own full-resolution sample
    array and engineering metadata. Locally-owned copy of the same
    source/calculated-channel branching `phasor_analysis_service._fetch_
    role_candidate()` already established -- deliberately duplicated,
    not imported, per this codebase's own convention."""
    if channel_ref.kind == "source":
        active = source_registry.get(workspace_id, channel_ref.source_id)
        if active is None:
            return None
        matching = next((ch for ch in active.metadata.analog_channels if ch.name == channel_ref.channel_name), None)
        if matching is None:
            return None
        waveform_data = active.record.waveform_data
        return _CurrentCandidate(
            channel_ref=channel_ref, time=waveform_data["time"].to_numpy(),
            values=waveform_data[channel_ref.channel_name].to_numpy(),
            unit=matching.unit, waveform_form=matching.waveform_form,
            start_epoch=_source_start_epoch(active), nominal_frequency=active.metadata.nominal_frequency,
        )
    calculated = calculated_channel_registry.get(workspace_id, channel_ref.calculated_channel_id)
    if calculated is None:
        return None
    reference_source = source_registry.get(workspace_id, calculated.reference_source_id)
    if reference_source is None:
        return None
    return _CurrentCandidate(
        channel_ref=channel_ref, time=calculated.time, values=calculated.values,
        unit=calculated.unit, waveform_form=calculated.waveform_form,
        start_epoch=_source_start_epoch(reference_source), nominal_frequency=reference_source.metadata.nominal_frequency,
    )


def _waveform_form_eligible_for_rms(candidate: _CurrentCandidate, reference_frequency_hz: float) -> bool:
    """Trusted-metadata-first, algorithmic-fallback-second -- mirrors
    `phasor_analysis_service._waveform_form_eligible()`'s own structure
    and STRICT policy exactly (explicit `instantaneous` passes; explicit
    `rms`/`magnitude` fails with no override; `unknown` falls back to the
    algorithmic detector, with `UNCERTAIN` REJECTED, never "allow with a
    warning" -- there is no override mechanism anywhere in this v1's
    read-only, selected-time analysis, the same reasoning Phasor's own
    docstring already establishes for why `check_rms_eligibility()`'s own
    override-eligible policy does not apply here)."""
    if candidate.waveform_form == WAVEFORM_FORM_INSTANTANEOUS:
        return True
    if candidate.waveform_form in (WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE):
        return False
    detector_result = classify_waveform_form(candidate.time, candidate.values, reference_frequency_hz)
    return detector_result == LIKELY_INSTANTANEOUS
    # LIKELY_MAGNITUDE_OR_RMS and UNCERTAIN both fall through to False.


def _short_circuit(
    status: str, *, engineering_context_id: str, phase: str, analysis_time: float,
    reason_code: str | None, message: str,
) -> OvercurrentAnalysisResult:
    return OvercurrentAnalysisResult(
        status=status, engineering_context_id=engineering_context_id, phase=phase,
        analysis_time=analysis_time, reason_code=reason_code, message=message,
    )


def compute_overcurrent_analysis(
    *,
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    analysis_time: float,
    characteristic_id: str,
    tms: float,
    pickup_current_secondary: float,
    recording_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
    reference_frequency_hz_override: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> OvercurrentAnalysisResult:
    """The one service-layer entry point. Raises `EngineeringContextNotFoundError`/
    `UnknownAnalysisRequirementError` exactly like `resolve_analysis_
    inputs()` itself does (propagated unchanged); every other failure
    mode is returned as an `OvercurrentAnalysisResult` with an explicit
    `status`/`reason_code`, never an exception."""
    requirement = _REQUIREMENT_BY_PHASE.get(phase)
    if requirement is None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code="unknown_phase",
            message=f"Unknown phase {phase!r} -- must be one of 'A'/'B'/'C'.",
        )
    role_key = _ROLE_KEY_BY_PHASE[phase]

    # ---- Settings validation -- BEFORE resolution/estimation, so an
    # invalid setting is reported immediately regardless of whether the
    # current role even resolves yet. ----
    characteristic = get_characteristic(characteristic_id)
    if characteristic is None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_UNKNOWN_CHARACTERISTIC,
            message=f"Unknown Overcurrent characteristic id {characteristic_id!r}.",
        )
    if not tms_valid(tms):
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_INVALID_TMS,
            message="TMS (Time Multiplier Setting) must be a finite number in the supported range.",
        )
    if not pickup_valid(pickup_current_secondary):
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_INVALID_PICKUP,
            message="Pickup current (secondary amperes) must be a finite number greater than zero.",
        )
    if recording_basis not in KNOWN_RECORDING_BASES:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code="invalid_recording_basis",
            message="Recording current basis must be 'primary' or 'secondary'.",
        )
    if recording_basis == "primary":
        if ct_primary is None or ct_secondary is None or not ct_values_valid(ct_primary, ct_secondary):
            return _short_circuit(
                STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
                analysis_time=analysis_time, reason_code=REASON_INVALID_CT_VALUES,
                message="CT primary and CT secondary current must both be finite numbers greater than zero.",
            )

    resolution = resolve_analysis_inputs(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        analysis_kind=requirement.analysis_kind, mode=requirement.mode,
        context_registry=context_registry, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    if resolution.status != STATUS_RESOLVED:
        assert resolution.status in (STATUS_NEEDS_CONFIGURATION, STATUS_AMBIGUOUS, STATUS_NOT_APPLICABLE)
        return _short_circuit(
            resolution.status, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=resolution.reason_code, message=resolution.message,
        )

    channel_ref = resolution.resolved_roles[role_key]
    candidate = _fetch_current_candidate(
        channel_ref, workspace_id=workspace_id, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    if candidate is None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_CHANNEL_UNAVAILABLE,
            message=f"Resolved current channel for role '{role_key}' could not be read.",
        )

    # ---- Reference frequency: explicit override, else this role's own
    # source-declared value (a single-role requirement, so there is no
    # cross-source AGREEMENT to check -- unlike Phasor's own multi-role
    # requirements). ----
    if reference_frequency_hz_override is not None:
        if not nominal_frequency_valid(reference_frequency_hz_override):
            return _short_circuit(
                STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
                analysis_time=analysis_time, reason_code=REASON_INVALID_REFERENCE_FREQUENCY,
                message="The supplied reference_frequency_hz is outside the plausible range.",
            )
        reference_frequency_hz = reference_frequency_hz_override
    else:
        reference_frequency_hz = candidate.nominal_frequency

    if not _waveform_form_eligible_for_rms(candidate, reference_frequency_hz):
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
            message="The resolved current channel is not an eligible instantaneous waveform input for RMS evaluation.",
        )

    if candidate.start_epoch is None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code="absolute_time_unavailable",
            message="The resolved source has no known absolute start time.",
        )

    window_seconds = 1.0 / reference_frequency_hz
    estimate = estimate_trailing_rms_at_time(candidate.time, candidate.values, analysis_time, reference_frequency_hz)
    if not estimate.available:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=estimate.reason_code,
            message="The current RMS could not be estimated at the requested analysis_time.",
        )

    measured_rms_current = estimate.value
    relay_secondary_current = convert_to_relay_secondary(
        measured_rms_current, recording_basis=recording_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    multiple_of_pickup = relay_secondary_current / pickup_current_secondary
    expected_operating_time_seconds = evaluate_idmt_operating_time(
        characteristic.constants, tms, multiple_of_pickup,
    )

    # `continuous_duration_above_pickup()` needs the FULL relay-secondary-
    # converted array -- CT conversion is a linear scalar, so it is
    # equivalent (and cheaper) to scale the array once here rather than
    # re-deriving per sample.
    if recording_basis == "primary":
        scale = ct_secondary / ct_primary
        relay_secondary_values = candidate.values * scale
    else:
        relay_secondary_values = candidate.values
    duration_result = continuous_duration_above_pickup(
        candidate.time, relay_secondary_values, analysis_time, reference_frequency_hz, pickup_current_secondary,
    )
    above_pickup_duration_seconds = duration_result.duration_seconds if duration_result.available else None

    threshold_exceeded = (
        expected_operating_time_seconds is not None
        and above_pickup_duration_seconds is not None
        and above_pickup_duration_seconds > expected_operating_time_seconds
    )

    return OvercurrentAnalysisResult(
        status=OVERCURRENT_STATUS_COMPUTED, engineering_context_id=engineering_context_id, phase=phase,
        analysis_time=analysis_time, characteristic_id=characteristic_id, tms=tms,
        pickup_current_secondary=pickup_current_secondary, recording_basis=recording_basis,
        ct_primary=ct_primary, ct_secondary=ct_secondary,
        reference_frequency_hz=reference_frequency_hz, window_seconds=window_seconds,
        channel_ref=candidate.channel_ref,
        measured_rms_current=measured_rms_current, measured_rms_current_unit=candidate.unit,
        relay_secondary_current=relay_secondary_current, multiple_of_pickup=multiple_of_pickup,
        expected_operating_time_seconds=expected_operating_time_seconds,
        above_pickup_duration_seconds=above_pickup_duration_seconds,
        threshold_exceeded=threshold_exceeded,
        message="Overcurrent evaluated at the requested analysis_time.",
    )


# ---------------------------------------------------------------------------
# Characteristic metadata / curve points -- both pure functions of static
# configuration (no registry/I/O access needed), but still routed through
# this service layer (never called directly from the API route) for the
# same reason every other read here is: a consistent, testable seam, and
# so a future characteristic needing config-derived data has somewhere to
# put it without reshaping the API layer.
# ---------------------------------------------------------------------------


def list_known_characteristics() -> tuple:
    """Every characteristic the API's own metadata endpoint exposes --
    thin passthrough of `app.domain.overcurrent.known_characteristics()`,
    never a second registry."""
    return known_characteristics()


class CurveComputationError(Exception):
    """Raised for an unknown `characteristic_id` or invalid `tms` --
    caught by the API route and mapped to a 422, exactly like FastAPI's
    own request-validation errors (this endpoint has no Engineering
    Context/analysis_time to return a `status`/`reason_code` result
    object against -- it is pure characteristic-curve geometry, not an
    analysis result)."""


def compute_idmt_curve(characteristic_id: str, tms: float) -> list[tuple[float, float]]:
    characteristic = get_characteristic(characteristic_id)
    if characteristic is None:
        raise CurveComputationError(f"Unknown Overcurrent characteristic id {characteristic_id!r}.")
    if not tms_valid(tms):
        raise CurveComputationError("TMS (Time Multiplier Setting) must be a finite number in the supported range.")
    return generate_idmt_curve_points(characteristic.constants, tms)
