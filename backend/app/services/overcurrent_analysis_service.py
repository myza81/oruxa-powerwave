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

from app.domain.time_reference import source_start_epoch

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
from app.domain.equipment_loading import equipment_loading_to_primary_current, positive_finite
from app.domain.overcurrent import (
    KNOWN_RECORDING_BASES,
    OVERCURRENT_MIN_SAMPLES_PER_CYCLE,
    OVERCURRENT_STATUS_COMPUTED,
    REASON_CHANNEL_UNAVAILABLE,
    REASON_INSUFFICIENT_SAMPLING_DENSITY,
    REASON_INVALID_CT_VALUES,
    REASON_INVALID_EQUIPMENT_RATING,
    REASON_INVALID_INPUT_CURRENT,
    REASON_INVALID_LOADING_PERCENT,
    REASON_INVALID_PICKUP,
    REASON_INVALID_RECORDING_BASIS,
    REASON_INVALID_REFERENCE_FREQUENCY,
    REASON_INVALID_SYSTEM_VOLTAGE,
    REASON_INVALID_TMS,
    REASON_UNKNOWN_CHARACTERISTIC,
    REASON_UNSUPPORTED_CURRENT_UNIT,
    REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
    RECORDING_BASIS_PRIMARY,
    EquipmentLoadingOvercurrentResult,
    ManualOvercurrentAnalysisResult,
    OvercurrentAnalysisResult,
    continuous_duration_above_pickup,
    convert_array_to_relay_secondary,
    convert_to_relay_secondary,
    ct_values_valid,
    estimate_trailing_rms_at_time,
    evaluate_multiple_and_operating_time,
    generate_idmt_curve_points,
    get_characteristic,
    input_current_valid,
    known_characteristics,
    pickup_valid,
    tms_valid,
)
from app.domain.rms_detector import LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS, classify_waveform_form
from app.services.analysis_input_resolution_service import resolve_analysis_inputs
from app.services.analysis_reference_frequency import (
    FORM_ELIGIBLE, FORM_NOT_ELIGIBLE, SAMPLING_UNSUPPORTED, decide_reference_frequency, sampling_reason_message, sampling_supports,
)
from app.services.calculated_timing_service import get_calculated_result
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_staleness import (
    REASON_STALE_CALCULATED_INPUT, StaleInputBlocked, stale_input_block,
)
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.nominal_frequency_access import NominalFrequencyAccess, SourceFrequency
from app.services.overcurrent_recorded_input import (
    OvercurrentAuthority,
    RecordedCurrentAuthority,
    evaluate_recorded_current_authority,
)
from app.services.workspace_registry import WorkspaceRegistry

_REQUIREMENT_BY_PHASE = {
    "A": OVERCURRENT_CURRENT_PHASE_A, "B": OVERCURRENT_CURRENT_PHASE_B, "C": OVERCURRENT_CURRENT_PHASE_C,
}
_ROLE_KEY_BY_PHASE = {"A": "Ia", "B": "Ib", "C": "Ic"}


def _source_start_epoch(active) -> float | None:
    """The shared recording-level effective UTC epoch, or None for unknown time."""
    return source_start_epoch(active.metadata)


class _CurrentCandidate:
    __slots__ = ("channel_ref", "time", "values", "unit", "waveform_form", "start_epoch", "frequency")

    def __init__(self, *, channel_ref, time, values, unit, waveform_form, start_epoch, frequency: SourceFrequency):
        self.channel_ref = channel_ref
        self.time = time
        self.values = values
        self.unit = unit
        self.waveform_form = waveform_form
        self.start_epoch = start_epoch
        #: NF-3D: the central authority's outcome for the recording that grounds this channel (never the imported value read directly).
        self.frequency = frequency


def _fetch_current_candidate(
    channel_ref: ChannelRef, *, workspace_id: str,
    source_registry: WorkspaceRegistry, calculated_channel_registry: CalculatedChannelRegistry, frequency_access: NominalFrequencyAccess,
) -> _CurrentCandidate | StaleInputBlocked | None:
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
            start_epoch=_source_start_epoch(active), frequency=frequency_access.for_source(workspace_id, channel_ref.source_id),
        )
    # NF-3E: a stale calculated channel is not a valid input for a new engineering calculation (shared staleness authority).
    stale = stale_input_block(channel_ref, workspace_id=workspace_id, calc_registry=calculated_channel_registry, frequency_access=frequency_access)
    if stale is not None:
        return stale
    calculated = get_calculated_result(workspace_id, channel_ref.calculated_channel_id, source_registry=source_registry, calc_registry=calculated_channel_registry)
    if calculated is None:
        return None
    reference_source = source_registry.get(workspace_id, calculated.reference_source_id)
    if reference_source is None:
        return None
    return _CurrentCandidate(
        channel_ref=channel_ref, time=calculated.time, values=calculated.values,
        unit=calculated.unit, waveform_form=calculated.waveform_form,
        start_epoch=_source_start_epoch(reference_source), frequency=frequency_access.for_source(workspace_id, calculated.reference_source_id),
    )


def _waveform_form_eligible_for_rms(candidate: _CurrentCandidate, reference_frequency_hz: float) -> str:
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
        return FORM_ELIGIBLE
    if candidate.waveform_form in (WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE):
        return FORM_NOT_ELIGIBLE
    # NF-3D (Phase C): a valid frequency the sampling cannot support (fewer than the estimator's own minimum samples per cycle) is a sampling
    # limit, not a form problem; the detector would only answer "uncertain".
    if not sampling_supports(candidate.time, reference_frequency_hz, OVERCURRENT_MIN_SAMPLES_PER_CYCLE):
        return SAMPLING_UNSUPPORTED
    detector_result = classify_waveform_form(candidate.time, candidate.values, reference_frequency_hz)
    return FORM_ELIGIBLE if detector_result == LIKELY_INSTANTANEOUS else FORM_NOT_ELIGIBLE
    # LIKELY_MAGNITUDE_OR_RMS and UNCERTAIN both fall through to False.


def _short_circuit(
    status: str, *, engineering_context_id: str, phase: str, analysis_time: float,
    reason_code: str | None, message: str,
    channel_ref: ChannelRef | None = None, measured_rms_current_unit: str | None = None,
    authority: RecordedCurrentAuthority | None = None,
) -> OvercurrentAnalysisResult:
    """`channel_ref`/`measured_rms_current_unit` are given ONLY by a configuration block where the current channel
    DID resolve (identity is not a result), so its signal stays plottable; no number is ever attached. `authority`
    (D5A-2B2C-1A) is given only when Recording Details' side/CT for that channel was evaluated: it reports what was
    found (side, how it was decided, owning group), never a number."""
    result = OvercurrentAnalysisResult(
        status=status, engineering_context_id=engineering_context_id, phase=phase,
        analysis_time=analysis_time, reason_code=reason_code, message=message,
        channel_ref=channel_ref, measured_rms_current_unit=measured_rms_current_unit,
    )
    if authority is not None:
        _attach_authority(result, authority)
    return result


def _attach_authority(result: OvercurrentAnalysisResult, authority: RecordedCurrentAuthority) -> None:
    result.measurement_group_id = authority.group_id
    if authority.side is not None:
        result.measurement_side = authority.side.side if authority.side.usable else None
        result.measurement_side_authority = authority.side.authority
    if authority.ct_pair is not None and authority.ct is not None:      # provenance of the CT actually APPLIED
        result.ct_authority = authority.ct.authority


def compute_overcurrent_analysis(
    *,
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    analysis_time: float,
    characteristic_id: str,
    tms: float,
    pickup_current_secondary: float,
    recording_basis: str | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    reference_frequency_hz_override: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    frequency_access: NominalFrequencyAccess,
    authority: OvercurrentAuthority,
) -> OvercurrentAnalysisResult:
    """The one service-layer entry point. Raises `EngineeringContextNotFoundError`/
    `UnknownAnalysisRequirementError` exactly like `resolve_analysis_
    inputs()` itself does (propagated unchanged); every other failure
    mode is returned as an `OvercurrentAnalysisResult` with an explicit
    `status`/`reason_code`, never an exception.

    D5A-2B2C-1A: the Primary/Secondary side of the recorded current and the CT applied to it come ONLY from Recording
    Details (`authority`, see `overcurrent_recorded_input`). `recording_basis`, `ct_primary` and `ct_secondary` are
    legacy request ASSERTIONS: omitted, they are not needed; supplied, they are validated against the authority and a
    contradiction blocks -- they can never override it. When the side is unresolved, only inferred, or contradictory,
    or a Primary side has no usable CT in the consumed channel's own group, the calculation is blocked with a
    configuration reason (the channel stays identified so its waveform remains available)."""
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
    if recording_basis is not None and recording_basis not in KNOWN_RECORDING_BASES:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_INVALID_RECORDING_BASIS,
            message="Recording current basis must be 'primary' or 'secondary'.",
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
        calculated_channel_registry=calculated_channel_registry, frequency_access=frequency_access,
    )
    if isinstance(candidate, StaleInputBlocked):
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_STALE_CALCULATED_INPUT, message=candidate.message,
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
    decision = decide_reference_frequency(
        override=reference_frequency_hz_override, frequencies=[candidate.frequency], conflict_message="",
    )
    if not decision.usable:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=decision.reason_code, message=decision.message,
        )
    reference_frequency_hz = decision.hz

    verdict = _waveform_form_eligible_for_rms(candidate, reference_frequency_hz)
    if verdict == SAMPLING_UNSUPPORTED:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_INSUFFICIENT_SAMPLING_DENSITY,
            message=sampling_reason_message(reference_frequency_hz, OVERCURRENT_MIN_SAMPLES_PER_CYCLE),
        )
    if verdict != FORM_ELIGIBLE:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
            message="The resolved current channel is not an eligible instantaneous waveform input for RMS evaluation.",
        )

    # ---- Recording Details is the authority for the side and the CT of THIS channel (decided after the channel's
    # identity/representation checks, in the same order `check_overcurrent_readiness()` reports them). ----
    recorded = evaluate_recorded_current_authority(
        workspace_id, candidate.channel_ref, authority=authority,
        requested_basis=recording_basis, request_ct=(ct_primary, ct_secondary),
    )
    if recorded.blocker is not None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=recorded.blocker.reason_code, message=recorded.blocker.message,
            channel_ref=candidate.channel_ref, measured_rms_current_unit=candidate.unit, authority=recorded,
        )
    recording_basis = recorded.basis
    ct_primary, ct_secondary = recorded.ct_pair or (None, None)

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
        measured_unit=candidate.unit,
    )
    if relay_secondary_current is None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_UNSUPPORTED_CURRENT_UNIT,
            message=(
                f"The resolved current channel's unit {candidate.unit!r} could not be "
                "normalized to amperes -- Overcurrent requires a recognized current unit."
            ),
            channel_ref=candidate.channel_ref, measured_rms_current_unit=candidate.unit, authority=recorded,
        )
    multiple_of_pickup, expected_operating_time_seconds = evaluate_multiple_and_operating_time(
        characteristic.constants, tms, relay_secondary_current, pickup_current_secondary,
    )

    # `continuous_duration_above_pickup()` needs the FULL relay-secondary-
    # converted array, normalized through the SAME shared engineering-unit
    # layer as the scalar RMS above -- otherwise the above-pickup duration
    # would stay dimensionally wrong even after the scalar fix.
    relay_secondary_values = convert_array_to_relay_secondary(
        candidate.values, recording_basis=recording_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        measured_unit=candidate.unit,
    )
    if relay_secondary_values is None:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            analysis_time=analysis_time, reason_code=REASON_UNSUPPORTED_CURRENT_UNIT,
            message=(
                f"The resolved current channel's unit {candidate.unit!r} could not be "
                "normalized to amperes -- Overcurrent requires a recognized current unit."
            ),
            channel_ref=candidate.channel_ref, measured_rms_current_unit=candidate.unit, authority=recorded,
        )
    duration_result = continuous_duration_above_pickup(
        candidate.time, relay_secondary_values, analysis_time, reference_frequency_hz, pickup_current_secondary,
    )
    above_pickup_duration_seconds = duration_result.duration_seconds if duration_result.available else None

    threshold_exceeded = (
        expected_operating_time_seconds is not None
        and above_pickup_duration_seconds is not None
        and above_pickup_duration_seconds > expected_operating_time_seconds
    )

    result = OvercurrentAnalysisResult(
        status=OVERCURRENT_STATUS_COMPUTED, engineering_context_id=engineering_context_id, phase=phase,
        analysis_time=analysis_time, characteristic_id=characteristic_id, tms=tms,
        pickup_current_secondary=pickup_current_secondary, recording_basis=recording_basis,
        ct_primary=ct_primary, ct_secondary=ct_secondary,
        reference_frequency_hz=reference_frequency_hz, window_seconds=window_seconds, frequency_provenance=decision.provenance,
        channel_ref=candidate.channel_ref,
        measured_rms_current=measured_rms_current, measured_rms_current_unit=candidate.unit,
        relay_secondary_current=relay_secondary_current, multiple_of_pickup=multiple_of_pickup,
        expected_operating_time_seconds=expected_operating_time_seconds,
        above_pickup_duration_seconds=above_pickup_duration_seconds,
        threshold_exceeded=threshold_exceeded,
        message="Overcurrent evaluated at the requested analysis_time.",
    )
    _attach_authority(result, recorded)
    return result


class OvercurrentReadiness:
    """DEC-107: Level 1 (role identity, via `resolve_analysis_inputs()`)
    + Level 2 (waveform-form eligibility, via `_waveform_form_eligible_
    for_rms()`) preflight for ONE phase -- deliberately performs NEITHER
    the RMS estimate NOR any other analysis_time-dependent step
    `compute_overcurrent_analysis()` goes on to attempt (Level 3); this
    function has no `analysis_time` parameter at all, by design. A
    context reported `status == STATUS_RESOLVED` here is not a promise
    that RMS evaluation will succeed at any PARTICULAR instant (a
    momentarily-quiet window, an as-yet-unelapsed first cycle, etc. are
    genuine runtime conditions this function never checks) -- only that
    nothing about the resolved channel's own IDENTITY or REPRESENTATION
    permanently disqualifies it.

    Mirrors `compute_overcurrent_analysis()`'s own first phase (role
    resolution -> candidate fetch -> reference frequency -> waveform-form
    eligibility) EXACTLY, reusing the same private helpers
    (`_REQUIREMENT_BY_PHASE`/`_ROLE_KEY_BY_PHASE`/`_fetch_current_candidate()`/
    `_waveform_form_eligible_for_rms()`) rather than re-deriving any of
    that logic -- keep both functions' own first phase in sync if either
    changes."""

    __slots__ = ("status", "reason_code", "message")

    def __init__(self, *, status: str, reason_code: str | None, message: str):
        self.status = status
        self.reason_code = reason_code
        self.message = message


def check_overcurrent_readiness(
    *,
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    reference_frequency_hz_override: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    frequency_access: NominalFrequencyAccess,
) -> OvercurrentReadiness:
    """Raises `EngineeringContextNotFoundError`/`UnknownAnalysisRequirementError`
    exactly like `resolve_analysis_inputs()` itself does (propagated
    unchanged) -- every other failure mode is returned as an
    `OvercurrentReadiness` with an explicit `status`/`reason_code`, never
    an exception, matching `compute_overcurrent_analysis()`'s own
    convention."""
    requirement = _REQUIREMENT_BY_PHASE.get(phase)
    if requirement is None:
        return OvercurrentReadiness(
            status=STATUS_NEEDS_CONFIGURATION, reason_code="unknown_phase",
            message=f"Unknown phase {phase!r} -- must be one of 'A'/'B'/'C'.",
        )
    role_key = _ROLE_KEY_BY_PHASE[phase]

    resolution = resolve_analysis_inputs(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        analysis_kind=requirement.analysis_kind, mode=requirement.mode,
        context_registry=context_registry, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    if resolution.status != STATUS_RESOLVED:
        assert resolution.status in (STATUS_NEEDS_CONFIGURATION, STATUS_AMBIGUOUS, STATUS_NOT_APPLICABLE)
        return OvercurrentReadiness(status=resolution.status, reason_code=resolution.reason_code, message=resolution.message)

    channel_ref = resolution.resolved_roles[role_key]
    candidate = _fetch_current_candidate(
        channel_ref, workspace_id=workspace_id, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry, frequency_access=frequency_access,
    )
    if isinstance(candidate, StaleInputBlocked):
        return OvercurrentReadiness(
            status=STATUS_NEEDS_CONFIGURATION, reason_code=REASON_STALE_CALCULATED_INPUT, message=candidate.message,
        )
    if candidate is None:
        return OvercurrentReadiness(
            status=STATUS_NEEDS_CONFIGURATION, reason_code=REASON_CHANNEL_UNAVAILABLE,
            message=f"Resolved current channel for role '{role_key}' could not be read.",
        )

    decision = decide_reference_frequency(
        override=reference_frequency_hz_override, frequencies=[candidate.frequency], conflict_message="",
    )
    if not decision.usable:
        return OvercurrentReadiness(
            status=STATUS_NEEDS_CONFIGURATION, reason_code=decision.reason_code, message=decision.message,
        )
    reference_frequency_hz = decision.hz

    verdict = _waveform_form_eligible_for_rms(candidate, reference_frequency_hz)
    if verdict == SAMPLING_UNSUPPORTED:
        return OvercurrentReadiness(
            status=STATUS_NEEDS_CONFIGURATION, reason_code=REASON_INSUFFICIENT_SAMPLING_DENSITY,
            message=sampling_reason_message(reference_frequency_hz, OVERCURRENT_MIN_SAMPLES_PER_CYCLE),
        )
    if verdict != FORM_ELIGIBLE:
        return OvercurrentReadiness(
            status=STATUS_NEEDS_CONFIGURATION, reason_code=REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
            message="The resolved current channel is not an eligible instantaneous waveform input for RMS evaluation.",
        )

    return OvercurrentReadiness(
        status=STATUS_RESOLVED, reason_code=None,
        message="The resolved current channel is eligible for RMS evaluation.",
    )


class RecordedCurrentInput:
    """D5A-2B2C-1A: what a recorded Overcurrent phase would consume from Recording Details, read without computing
    anything. `status` is `ready` only when `compute_overcurrent_analysis()` would not be blocked by the side/CT
    configuration; the two share `evaluate_recorded_current_authority()`, so they cannot disagree."""

    __slots__ = ("status", "engineering_context_id", "phase", "unit", "authority", "reason_code", "message")

    def __init__(self, *, status, engineering_context_id, phase, unit=None, authority=None, reason_code=None, message=""):
        self.status = status
        self.engineering_context_id = engineering_context_id
        self.phase = phase
        self.unit = unit
        self.authority = authority
        self.reason_code = reason_code
        self.message = message


INPUT_STATUS_READY = "ready"


def read_recorded_current_input(
    *,
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    frequency_access: NominalFrequencyAccess,
    authority: OvercurrentAuthority,
) -> RecordedCurrentInput:
    """Raises `EngineeringContextNotFoundError`/`UnknownAnalysisRequirementError` exactly like `resolve_analysis_
    inputs()`; every other outcome is returned, never raised."""
    requirement = _REQUIREMENT_BY_PHASE.get(phase)
    if requirement is None:
        return RecordedCurrentInput(
            status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            reason_code="unknown_phase", message=f"Unknown phase {phase!r} -- must be one of 'A'/'B'/'C'.",
        )
    resolution = resolve_analysis_inputs(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        analysis_kind=requirement.analysis_kind, mode=requirement.mode,
        context_registry=context_registry, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    if resolution.status != STATUS_RESOLVED:
        return RecordedCurrentInput(
            status=resolution.status, engineering_context_id=engineering_context_id, phase=phase,
            reason_code=resolution.reason_code, message=resolution.message,
        )
    candidate = _fetch_current_candidate(
        resolution.resolved_roles[_ROLE_KEY_BY_PHASE[phase]], workspace_id=workspace_id,
        source_registry=source_registry, calculated_channel_registry=calculated_channel_registry, frequency_access=frequency_access,
    )
    if isinstance(candidate, StaleInputBlocked):
        return RecordedCurrentInput(
            status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            reason_code=REASON_STALE_CALCULATED_INPUT, message=candidate.message,
        )
    if candidate is None:
        return RecordedCurrentInput(
            status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            reason_code=REASON_CHANNEL_UNAVAILABLE,
            message=f"Resolved current channel for role '{_ROLE_KEY_BY_PHASE[phase]}' could not be read.",
        )
    recorded = evaluate_recorded_current_authority(workspace_id, candidate.channel_ref, authority=authority)
    if recorded.blocker is not None:
        return RecordedCurrentInput(
            status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,
            unit=candidate.unit, authority=recorded, reason_code=recorded.blocker.reason_code,
            message=recorded.blocker.message,
        )
    return RecordedCurrentInput(
        status=INPUT_STATUS_READY, engineering_context_id=engineering_context_id, phase=phase,
        unit=candidate.unit, authority=recorded,
        message=("The recorded current is on the Primary side and is converted with the CT of its own Measurement Group."
                 if recorded.conversion_required else
                 "The recorded current is on the Secondary side; no CT conversion is applied."),
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


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode (Analysis Input Source = "manual") --
# see docs/project-memory/ANALYSIS_INPUT_SOURCE.md for the shared
# architecture, and app.domain.overcurrent.ManualOvercurrentAnalysisResult
# for the result shape's own rationale. Pure validation + calculation, no
# registry/I/O access at all (no Engineering Context, no channel, no
# waveform, no Playback) -- routed through this service layer anyway,
# mirroring `compute_idmt_curve()`'s own "consistent, testable seam"
# precedent immediately above. Reuses the EXACT SAME `convert_to_relay_
# secondary()`/`evaluate_multiple_and_operating_time()` domain functions
# `compute_overcurrent_analysis()` (the recording-driven path above)
# already calls -- never a second, manual-only calculation engine.
# ---------------------------------------------------------------------------


def compute_overcurrent_manual_analysis(
    *,
    characteristic_id: str,
    tms: float,
    pickup_current_secondary: float,
    input_current: float,
    input_current_unit: str,
    input_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
) -> ManualOvercurrentAnalysisResult:
    """Never raises -- every failure mode (unknown characteristic,
    invalid TMS/pickup/CT/basis/input current, an input unit that cannot
    be normalized to amperes) is returned as a `ManualOvercurrentAnalysisResult`
    with an explicit `status`/`reason_code`, mirroring `compute_overcurrent_
    analysis()`'s own never-raise-for-a-guardrail-failure precedent."""

    def _short_circuit(reason_code: str, message: str) -> ManualOvercurrentAnalysisResult:
        return ManualOvercurrentAnalysisResult(
            status=STATUS_NEEDS_CONFIGURATION, reason_code=reason_code, message=message,
        )

    characteristic = get_characteristic(characteristic_id)
    if characteristic is None:
        return _short_circuit(REASON_UNKNOWN_CHARACTERISTIC, f"Unknown Overcurrent characteristic id {characteristic_id!r}.")
    if not tms_valid(tms):
        return _short_circuit(REASON_INVALID_TMS, "TMS (Time Multiplier Setting) must be a finite number in the supported range.")
    if not pickup_valid(pickup_current_secondary):
        return _short_circuit(REASON_INVALID_PICKUP, "Pickup current (secondary amperes) must be a finite number greater than zero.")
    if input_basis not in KNOWN_RECORDING_BASES:
        return _short_circuit("invalid_recording_basis", "Manual input basis must be 'primary' or 'secondary'.")
    if input_basis == "primary":
        if ct_primary is None or ct_secondary is None or not ct_values_valid(ct_primary, ct_secondary):
            return _short_circuit(REASON_INVALID_CT_VALUES, "CT primary and CT secondary current must both be finite numbers greater than zero.")
    if not input_current_valid(input_current):
        return _short_circuit(REASON_INVALID_INPUT_CURRENT, "Manual input current must be a finite number greater than zero.")

    relay_secondary_current = convert_to_relay_secondary(
        input_current, recording_basis=input_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        measured_unit=input_current_unit,
    )
    if relay_secondary_current is None:
        return _short_circuit(
            REASON_UNSUPPORTED_CURRENT_UNIT,
            f"The manual input unit {input_current_unit!r} could not be normalized to amperes -- "
            "Overcurrent requires a recognized current unit.",
        )
    multiple_of_pickup, expected_operating_time_seconds = evaluate_multiple_and_operating_time(
        characteristic.constants, tms, relay_secondary_current, pickup_current_secondary,
    )
    return ManualOvercurrentAnalysisResult(
        status=OVERCURRENT_STATUS_COMPUTED, characteristic_id=characteristic_id, tms=tms,
        pickup_current_secondary=pickup_current_secondary, input_basis=input_basis,
        ct_primary=ct_primary, ct_secondary=ct_secondary,
        input_current=input_current, input_current_unit=input_current_unit,
        relay_secondary_current=relay_secondary_current, multiple_of_pickup=multiple_of_pickup,
        expected_operating_time_seconds=expected_operating_time_seconds,
        message="Overcurrent evaluated for the manually entered input current.",
    )


# Manual Input's Equipment Loading input method -- an INPUT CONVERSION
# only. The loading inputs become an equivalent primary current in
# amperes (`app.domain.equipment_loading`), which is then evaluated by
# `compute_overcurrent_manual_analysis()` above EXACTLY as if the engineer
# had typed that primary current directly (basis "primary", unit "A"), so
# the CT ratio, pickup multiple and IEC IDMT operating time all come from
# the one existing pipeline.


def compute_overcurrent_equipment_loading_analysis(
    *,
    characteristic_id: str,
    tms: float,
    pickup_current_secondary: float,
    equipment_rating_mva: float,
    loading_percent: float,
    system_voltage_kv: float,
    ct_primary: float | None,
    ct_secondary: float | None,
) -> EquipmentLoadingOvercurrentResult:
    """Never raises. Invalid loading inputs short-circuit with their own
    reason code and no conversion; every relay-setting/CT failure is the
    delegated manual result's own, with the conversion still reported."""
    for value, reason_code, message in (
        (equipment_rating_mva, REASON_INVALID_EQUIPMENT_RATING, "Equipment rating (MVA) must be a finite number greater than zero."),
        (loading_percent, REASON_INVALID_LOADING_PERCENT, "Equipment loading (%) must be a finite number greater than zero."),
        (system_voltage_kv, REASON_INVALID_SYSTEM_VOLTAGE, "System voltage (kV, line-to-line) must be a finite number greater than zero."),
    ):
        if not positive_finite(value):
            return EquipmentLoadingOvercurrentResult(
                analysis=ManualOvercurrentAnalysisResult(
                    status=STATUS_NEEDS_CONFIGURATION, reason_code=reason_code, message=message,
                ),
            )

    loading = equipment_loading_to_primary_current(equipment_rating_mva, loading_percent, system_voltage_kv)
    analysis = compute_overcurrent_manual_analysis(
        characteristic_id=characteristic_id, tms=tms, pickup_current_secondary=pickup_current_secondary,
        input_current=loading.primary_current_a, input_current_unit="A", input_basis=RECORDING_BASIS_PRIMARY,
        ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    if analysis.status == OVERCURRENT_STATUS_COMPUTED:
        analysis.message = "Overcurrent evaluated for the equivalent current of the entered equipment loading."
    return EquipmentLoadingOvercurrentResult(analysis=analysis, loading=loading)
