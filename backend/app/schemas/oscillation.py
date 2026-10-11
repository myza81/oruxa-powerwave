"""Wire shapes for the Oscillation Analysis representation endpoint
(DEC-173 [APPROVED]). Metadata only -- no sample arrays."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.calculated_channel import ChannelRefIn


class OscillationRepresentationRequest(BaseModel):
    input: ChannelRefIn
    #: Only `rms_magnitude` exists; the field lets later representations
    #: join without a new endpoint (unknown values are a 400).
    representation: str = "rms_magnitude"


class OscillationRepresentationOut(BaseModel):
    status: Literal["ready", "unavailable"]
    representation: str
    source_form: str | None = None
    reason_code: str | None = None
    message: str | None = None
    nominal_frequency_hz: float | None = None
    #: "recording_metadata" | "assumed_default"
    nominal_frequency_origin: str | None = None
    source_sample_count: int = 0
    source_sample_rate_hz: float | None = None
    source_start_s: float | None = None
    source_end_s: float | None = None
    # The following are present only when status == "ready".
    reporting: str | None = None
    representation_sample_rate_hz: float | None = None
    derived_sample_count: int | None = None
    window_s: float | None = None
    window_alignment: str | None = None
    group_delay_s: float | None = None
    valid_start_s: float | None = None
    valid_end_s: float | None = None
    boundary_loss_start_s: float | None = None
    boundary_loss_end_s: float | None = None
    bandwidth_half_power_hz: float | None = None
    bandwidth_limit_hz: float | None = None


class OscillationSpectrumRequest(BaseModel):
    """Welch PSD request (DEC-174 [PROPOSAL]). The signal is resolved from
    workspace state; no samples are accepted from the browser."""

    input: ChannelRefIn
    #: `native` (signal as recorded) or `rms_magnitude` (DEC-173).
    representation: str = "native"
    #: Echoed back so the caller can bind the result to a catalogue revision.
    signal_revision: str | None = None
    #: Selected analysis window, in the signal's SOURCE time (seconds).
    window_start_s: float
    window_end_s: float
    frequency_min_hz: float
    frequency_max_hz: float


class SpectrumSignalOut(BaseModel):
    name: str | None = None
    calculated_channel_id: str | None = None
    source_id: str
    source_recording: str | None = None
    unit: str | None = None
    #: `<unit>²/Hz`; None when the source unit is unknown (never invented).
    psd_unit: str | None = None


class SpectrumRepresentationOut(BaseModel):
    type: str
    source_sample_rate_hz: float | None = None
    analysis_sample_rate_hz: float
    nominal_frequency_hz: float | None = None
    nominal_frequency_origin: str | None = None
    rms_window_s: float | None = None
    rms_group_delay_s: float | None = None
    bandwidth_half_power_hz: float | None = None
    bandwidth_limit_hz: float | None = None


class SpectrumWindowOut(BaseModel):
    requested_start_s: float
    requested_end_s: float
    start_s: float
    end_s: float
    duration_s: float
    sample_count: int
    #: 1 / T of the whole window -- NOT the Welch bin spacing.
    basic_resolution_hz: float


class SpectrumWelchOut(BaseModel):
    detrend: str
    window: str
    scaling: str
    average: str
    zero_padding: bool
    nfft: int
    nperseg: int
    segment_s: float
    target_segment_s: float
    overlap_samples: int
    overlap_fraction: float
    segment_count: int
    unused_tail_samples: int
    #: fs / nperseg -- the grid the PSD is actually on.
    bin_spacing_hz: float
    segment_rule: str


class SpectrumFrequencyOut(BaseModel):
    requested_min_hz: float
    requested_max_hz: float
    returned_min_hz: float
    returned_max_hz: float
    bin_count: int
    nyquist_hz: float


class SpectrumWarningOut(BaseModel):
    code: str
    message: str


class DetectionEvidenceOut(BaseModel):
    """One structured, display-safe statement derived from a measured condition."""

    code: str
    message: str
    values: dict[str, float | int | str | bool | None] = {}


class OscillationCandidateOut(BaseModel):
    rank: int
    frequency_hz: float
    #: 1 / frequency_hz; None only for a non-positive frequency.
    period_s: float | None = None
    psd: float
    prominence_db: float
    cycles_observed: float
    base_psd: float
    left_base_hz: float | None = None
    right_base_hz: float | None = None
    #: `candidate` (deterministic criteria met). No strength label exists in Phase 1.
    assessment: str
    reasons: list[DetectionEvidenceOut]
    warnings: list[DetectionEvidenceOut]


class NotPromotedOut(BaseModel):
    """A spectral maximum that did NOT meet the criteria (`insufficient_evidence`)."""

    frequency_hz: float
    period_s: float | None = None
    psd: float
    prominence_db: float
    cycles_observed: float
    assessment: str
    reason_code: str
    reasons: list[DetectionEvidenceOut]
    warnings: list[DetectionEvidenceOut]


class LowFrequencyRegionOut(BaseModel):
    cutoff_hz: float
    bin_count: int
    peak_frequency_hz: float
    peak_psd: float
    power_fraction: float
    #: True when the band's largest PSD lies below the cut-off.
    dominant: bool
    message: str


class DetectionOut(BaseModel):
    """Deterministic candidate detection (DEC-175 [PROPOSAL])."""

    status: Literal["candidates_found", "no_candidate"]
    candidates: list[OscillationCandidateOut]
    total_candidates: int
    truncated: bool
    not_promoted: list[NotPromotedOut]
    no_candidate_reasons: list[DetectionEvidenceOut]
    low_frequency: LowFrequencyRegionOut | None = None
    parameters: dict[str, float | int | str | bool]
    counts: dict[str, int]


class OscillationSpectrumOut(BaseModel):
    status: Literal["ok"]
    signal: SpectrumSignalOut
    representation: SpectrumRepresentationOut
    window: SpectrumWindowOut
    welch: SpectrumWelchOut
    frequency: SpectrumFrequencyOut
    frequencies_hz: list[float]
    psd: list[float]
    warnings: list[SpectrumWarningOut]
    detection: DetectionOut


class OscillationSpectrogramRequest(BaseModel):
    """STFT spectrogram request (DEC-176 [APPROVED]). The same identity fields as
    the spectrum: the signal is resolved from workspace state and the window and
    band are re-validated by the backend; no samples are accepted."""

    input: ChannelRefIn
    #: `native` (signal as recorded) or `rms_magnitude` (DEC-173).
    representation: str = "native"
    #: Echoed back so the caller can bind the result to a catalogue revision.
    signal_revision: str | None = None
    #: Selected analysis window, in the signal's SOURCE time (seconds).
    window_start_s: float
    window_end_s: float
    frequency_min_hz: float
    frequency_max_hz: float


class SpectrogramSetupOut(BaseModel):
    """The exact setup the result belongs to (stale-result identity)."""

    representation: str
    signal_revision: str | None = None
    window_start_s: float
    window_end_s: float
    frequency_min_hz: float
    frequency_max_hz: float


class SpectrogramStftOut(BaseModel):
    window: str
    detrend: str
    scaling: str
    zero_padding: bool
    nfft: int
    nperseg: int
    window_s: float
    target_window_s: float
    overlap_samples: int
    overlap_fraction: float
    hop_samples: int
    hop_s: float
    slice_count: int
    unused_tail_samples: int
    #: fs / nperseg -- the frequency-row spacing of one slice.
    bin_spacing_hz: float
    #: `window_centre` -- each column is stamped at the centre of its slice.
    time_stamp: str
    window_rule: str
    #: `none` | `time_resolution` | `minimum_samples` | `data_length`
    limited_by: str


class SpectrogramFrequencyOut(BaseModel):
    requested_min_hz: float
    requested_max_hz: float
    returned_min_hz: float | None = None
    returned_max_hz: float | None = None
    row_count: int = 0
    #: Rows inside the band before any transport reduction.
    source_row_count: int = 0
    #: 1 = none. Otherwise each returned row is the MAXIMUM of this many adjacent rows.
    row_decimation_factor: int = 1
    nyquist_hz: float


class SpectrogramMatrixOut(BaseModel):
    rows: int
    columns: int
    cells: int
    max_cells: int
    #: Linear PSD `<unit>²/Hz`, rounded to 6 significant digits for transport.
    value_digits: int


class OscillationSpectrogramOut(BaseModel):
    #: `ok`, or `unavailable` -- a valid, explained "no spectrogram" result.
    status: Literal["ok", "unavailable"]
    reason_code: str | None = None
    message: str | None = None
    setup: SpectrogramSetupOut
    signal: SpectrumSignalOut
    representation: SpectrumRepresentationOut
    window: SpectrumWindowOut
    stft: SpectrogramStftOut | None = None
    frequency: SpectrogramFrequencyOut | None = None
    matrix: SpectrogramMatrixOut | None = None
    #: Slice-centre times in the signal's SOURCE time (seconds), length = columns.
    times_s: list[float] = []
    frequencies_hz: list[float] = []
    #: Linear PSD, `psd[row][column]` = `psd[frequency][time]`.
    psd: list[list[float]] = []
    warnings: list[SpectrumWarningOut] = []


class OscillationDampingRequest(BaseModel):
    """Ringdown damping request (DEC-177 [PROPOSAL]). The same identity as the spectrum
    -- the backend re-runs the (cheap) Welch spectrum and the DEC-175 detection for that
    exact setup and analyses ITS accepted candidates; nothing the browser says about
    candidates is trusted. ``candidate_frequencies_hz`` only SELECTS among them (each must
    match a backend candidate, else 409 ``candidate_mismatch``); omitted = all of them."""

    input: ChannelRefIn
    representation: str = "native"
    signal_revision: str | None = None
    window_start_s: float
    window_end_s: float
    frequency_min_hz: float
    frequency_max_hz: float
    candidate_frequencies_hz: list[float] | None = None


class DampingFitOut(BaseModel):
    #: Fit interval in the signal's SOURCE time.
    start_s: float
    end_s: float
    duration_s: float
    cycles_used: float
    samples: int
    #: `after_envelope_peak` | `active_run_around_peak`
    rule: str
    peak_s: float


class DampingFrequencyOut(BaseModel):
    #: The accepted DEC-175 spectral candidate frequency (never replaced).
    candidate_hz: float
    #: Phase-slope refinement over the fit interval; None when not reliable.
    fitted_hz: float | None = None
    used_hz: float
    #: `candidate` | `fitted`
    source: str


class DampingFitQualityOut(BaseModel):
    r_squared: float | None = None
    rms_log_residual: float
    monotonic_fraction: float | None = None
    samples: int
    time_bandwidth_product: float


class DampingEnvelopeChangeOut(BaseModel):
    start_amplitude: float
    end_amplitude: float
    log_change: float
    change_percent: float
    unit: str | None = None


class DampingFilterOut(BaseModel):
    type: str
    zero_phase: bool
    centre_hz: float
    bandwidth_fwhm_hz: float
    sigma_hz: float
    edge_guard_s: float
    nearest_other_candidate_hz: float | None = None
    neighbour_leakage: float | None = None


class DampingBackgroundOut(BaseModel):
    level: float | None = None
    sides: list[str] = []
    min_amplitude_over_background: float
    start_amplitude_over_background: float | None = None
    end_amplitude_over_background: float | None = None


class DampingEvidencePlotOut(BaseModel):
    """Thinned (<= 500 points) envelope for the audit plot. Times are SOURCE time."""

    times_s: list[float]
    envelope: list[float]
    #: Fitted exponential on the fit interval; None outside it.
    fitted_envelope: list[float | None] | None = None
    valid_start_s: float
    valid_end_s: float
    fit_start_s: float | None = None
    fit_end_s: float | None = None
    background_level: float | None = None
    stride: int


class CandidateDampingOut(BaseModel):
    rank: int
    candidate_frequency_hz: float
    #: `available` | `insufficient_evidence` | `not_applicable`
    status: Literal["available", "insufficient_evidence", "not_applicable"]
    #: Machine code of the (first) negative evidence; None when available.
    reason_code: str | None = None
    #: Short statement: Decaying / Approximately sustained / Growing, or why none.
    message: str
    #: `decaying` | `approximately_sustained` | `growing` (available only).
    behaviour: str | None = None
    fit: DampingFitOut | None = None
    #: alpha in s^-1, amplitude ~ exp(-alpha t): > 0 decays, ~0 sustained, < 0 grows.
    decay_rate_per_s: float | None = None
    time_constant_s: float | None = None
    #: zeta = alpha / sqrt(alpha^2 + omega^2); only for a decaying component.
    damping_ratio: float | None = None
    frequency: DampingFrequencyOut | None = None
    fit_quality: DampingFitQualityOut | None = None
    envelope_change: DampingEnvelopeChangeOut | None = None
    filter: DampingFilterOut | None = None
    background: DampingBackgroundOut | None = None
    reasons: list[DetectionEvidenceOut] = []
    warnings: list[DetectionEvidenceOut] = []
    evidence: DampingEvidencePlotOut | None = None


class OscillationDampingOut(BaseModel):
    #: `ok`, or `no_candidates` (a valid result: nothing to analyse).
    status: Literal["ok", "no_candidates"]
    message: str | None = None
    setup: SpectrogramSetupOut
    signal: SpectrumSignalOut
    representation: SpectrumRepresentationOut
    window: SpectrumWindowOut
    parameters: dict[str, float | int | str | bool]
    results: list[CandidateDampingOut] = []
    warnings: list[SpectrumWarningOut] = []


class CrossSignalEntryIn(BaseModel):
    """One compared signal. The backend resolves it from workspace state and re-validates its window; `offset_s`
    (workspace time = source time + offset, the page's existing alignment) is only used to compare time evidence."""

    input: ChannelRefIn
    representation: str = "native"
    signal_revision: str | None = None
    window_start_s: float
    window_end_s: float
    offset_s: float = 0.0
    label: str | None = None


class OscillationCrossSignalRequest(BaseModel):
    signals: list[CrossSignalEntryIn] = Field(min_length=2, max_length=8)
    frequency_min_hz: float
    frequency_max_hz: float


class CrossSignalRowOut(BaseModel):
    index: int
    label: str
    #: `ok` | `excluded` (could not be analysed; `reason_code` / `message` say why).
    status: Literal["ok", "excluded"]
    reason_code: str | None = None
    message: str | None = None
    representation: str
    signal_revision: str | None = None
    #: `raw` | `calculated`
    origin: str
    signal_type: str
    offset_s: float
    window_start_s: float
    window_end_s: float
    source_id: str | None = None
    recording: str | None = None
    unit: str | None = None
    bin_spacing_hz: float | None = None
    candidate_count: int = 0
    damping_available_count: int = 0
    spectrogram_status: str | None = None


class CrossSignalMemberOut(BaseModel):
    signal_index: int
    label: str
    rank: int
    frequency_hz: float
    prominence_db: float
    cycles_observed: float
    bin_spacing_hz: float
    damping: dict[str, Any] | None = None
    temporal: dict[str, Any] | None = None


class CrossSignalComponentOut(BaseModel):
    id: int
    representative_frequency_hz: float
    representative_rule: str
    frequency_spread_hz: float
    match_tolerance_hz: float
    signal_count: int
    recording_count: int
    distinct_measurement_count: int
    signal_types: list[str]
    recordings: list[str]
    max_prominence_db: float
    members: list[CrossSignalMemberOut]
    reasons: list[DetectionEvidenceOut]
    warnings: list[DetectionEvidenceOut]
    evidence: dict[str, Any] = {}


class OscillationCrossSignalOut(BaseModel):
    #: `ok`, or `no_components` (nothing to group -- a valid, explained result).
    status: Literal["ok", "no_components"]
    message: str | None = None
    setup: dict[str, float]
    parameters: dict[str, float | int | str | bool]
    signals: list[CrossSignalRowOut]
    components: list[CrossSignalComponentOut] = []


# ---------------------------------------------------------------- DEC-179 [APPROVED] oscillation interpretation


class InterpretationRequest(BaseModel):
    """The cross-signal request, but a single signal is a valid interpretation."""

    signals: list[CrossSignalEntryIn] = Field(min_length=1, max_length=8)
    frequency_min_hz: float
    frequency_max_hz: float


class BehaviourClassificationOut(BaseModel):
    #: Stable code, e.g. `disturbance_excited_ringdown`, `sustained_oscillation`, `insufficient_temporal_evidence`.
    code: str
    label: str


class TypeSubtypeOut(BaseModel):
    code: str
    label: str
    #: Always `possible`: a subtype is never definitive (DEC-179); DEC-182 adds `strength`.
    level: str
    #: `consistent_with` | `supported_provisional` where mode-shape / coherence evidence was integrated (DEC-182); otherwise null.
    strength: str | None = None


class ProbableTypeOut(BaseModel):
    #: `electromechanical` | `forced_or_sustained` | `control_converter_interaction` | `sub_synchronous_oscillation` | `unresolved`.
    code: str
    label: str
    subtype: TypeSubtypeOut | None = None


class InterpretationDescriptorOut(BaseModel):
    code: str
    label: str
    message: str
    values: dict[str, float | int | str | bool | None] = {}


class InterpretationAlternativeOut(BaseModel):
    code: str
    label: str
    level: str
    #: `subtype_alternative` | `lower_level` | `refined_by_primary` | `refined_by_alternative` | `equally_plausible`
    relation: str
    #: `consistent` | `weaker`
    consistency: str
    reasons: list[DetectionEvidenceOut] = []
    limitations: list[DetectionEvidenceOut] = []


class InterpretationStrengthOut(BaseModel):
    code: str
    label: str


class ComponentInterpretationOut(BaseModel):
    """Deterministic interpretation of one component: behaviour and probable type are separate dimensions; every statement is
    backed by structured supporting / limiting evidence. No probability, no percentage, no AI."""

    component_id: int
    component_frequency_hz: float
    behaviour_classification: BehaviourClassificationOut
    probable_type: ProbableTypeOut
    #: `probable` | `possible` | `unresolved` | `insufficient_evidence` (see `interpretation_parameters`).
    classification_level: str
    hierarchy: list[str]
    descriptors: list[InterpretationDescriptorOut] = []
    supporting_evidence: list[DetectionEvidenceOut]
    limiting_evidence: list[DetectionEvidenceOut]
    alternatives: list[InterpretationAlternativeOut] = []
    warnings: list[DetectionEvidenceOut] = []
    evidence_dimensions: dict[str, bool] = {}
    #: DEC-182: `detected` | `possible` | `consistent_with` | `supported_provisional` | `unresolved` (qualitative, never a score).
    interpretation_strength: InterpretationStrengthOut | None = None
    #: Evidence that pulls against the reading (weak coherence beside a phase, unstable phase, differing damping, no overlap).
    contradictory_evidence: list[DetectionEvidenceOut] = []
    #: Evidence that was refused or not computed (a short event); never penalised.
    unavailable_evidence: list[DetectionEvidenceOut] = []
    #: Machine-readable summary of the mode-shape / coherence facts used (empty when none were integrated).
    spatial_evidence: dict[str, Any] = {}


class SummaryFieldOut(BaseModel):
    code: str
    label: str
    value: str


class SummaryEvidenceOut(BaseModel):
    """One evidence layer of the summary strip. `unavailable` / `not_applicable` are valid results, never failures."""

    code: str
    label: str
    #: `available` | `unavailable` | `not_applicable` | `caution`
    status: Literal["available", "unavailable", "not_applicable", "caution"]
    status_label: str
    detail: str
    #: Whether the page prints the detail line under the strip (the others appear as a tooltip only).
    show_detail: bool = True


class ComponentSummaryOut(BaseModel):
    """DEC-183 [APPROVED]: engineer-facing summary of one component, arranged from the structured evidence of the same response."""

    component_id: int
    title: str
    frequency_hz: float
    growing: bool = False
    fields: list[SummaryFieldOut]
    evidence: list[SummaryEvidenceOut]
    conclusion: str
    caution: str | None = None


class InterpretedComponentOut(CrossSignalComponentOut):
    interpretation: ComponentInterpretationOut
    summary: ComponentSummaryOut | None = None


class OscillationInterpretationOut(BaseModel):
    status: Literal["ok", "no_components"]
    message: str | None = None
    setup: dict[str, float]
    parameters: dict[str, float | int | str | bool]
    interpretation_parameters: dict[str, float | int | str | bool]
    #: Wall-clock milliseconds of each step; the classification step is reported on its own.
    timings_ms: dict[str, float]
    signals: list[CrossSignalRowOut]
    components: list[InterpretedComponentOut] = []
    #: DEC-182: the mode shape and coherence of the components seen in two or more signals (same shapes as their own endpoints).
    mode_shape: InterpretationModeShapeOut | None = None
    coherence: InterpretationCoherenceOut | None = None


# ---------------------------------------------------------------- mode shape / relative phase (DEC-180 [PROPOSAL])

class ModeShapeEntryIn(BaseModel):
    """One compared signal. The alignment offset is NOT accepted: the backend takes it from the synchronization model."""

    input: ChannelRefIn
    representation: str = "native"
    signal_revision: str | None = None
    window_start_s: float
    window_end_s: float
    label: str | None = None


class ModeShapeRequest(BaseModel):
    signals: list[ModeShapeEntryIn] = Field(min_length=2, max_length=8)
    frequency_min_hz: float
    frequency_max_hz: float
    #: Restrict the result to the component whose representative frequency matches this (optional; default: every component seen in 2+ signals).
    component_frequency_hz: float | None = None


class ModeShapeStabilityOut(BaseModel):
    #: `stable` | `unstable` | `unavailable`
    status: str
    valid_subwindows: int
    subwindows: int
    circular_mean_deg: float | None = None
    circular_spread_deg: float | None = None
    max_deviation_deg: float | None = None
    subwindow_phase_deg: list[float] = []
    message: str


class ModeShapeMemberOut(BaseModel):
    signal_index: int
    label: str
    recording: str | None = None
    #: `raw` | `calculated`
    origin: str
    signal_type: str
    unit: str | None = None
    time_group_id: str | None = None
    candidate_frequency_hz: float
    prominence_db: float
    #: `ok` | `insufficient_evidence` | `unavailable`
    status: Literal["ok", "insufficient_evidence", "unavailable"]
    reason_code: str | None = None
    message: str | None = None
    #: Fitted oscillation amplitude in the signal's own unit, at the start of the common interval (null when no fit was made).
    amplitude: float | None = None
    #: A / max(A) within the comparable quantity group only.
    relative_amplitude: float | None = None
    #: Degrees in [-180, +180); positive = leads the reference; the reference is 0. Null when no number may be given.
    phase_deg: float | None = None
    #: White-noise approximation of the phase standard deviation of the fit, degrees (informational).
    phase_uncertainty_deg: float | None = None
    fit_power_ratio: float | None = None
    #: Exponential envelope rate used in the fit, 1/s (positive = decaying); amplitude is referred to the start of the common interval.
    envelope_rate_per_s: float | None = None
    samples_used: int | None = None
    is_reference: bool = False
    phase_stability: ModeShapeStabilityOut | None = None
    reasons: list[DetectionEvidenceOut] = []
    warnings: list[DetectionEvidenceOut] = []


class ModeShapeGroupOut(BaseModel):
    quantity_type: str
    unit: str | None = None
    #: False when the quantity is not classified: nothing is compared.
    comparable: bool
    status: Literal["ok", "insufficient_evidence", "unavailable"]
    reason_code: str | None = None
    message: str | None = None
    projection_frequency_hz: float | None = None
    frequency_refinement: dict[str, Any] | None = None
    common_interval: dict[str, Any] | None = None
    cycles_used: float | None = None
    reference: dict[str, Any] | None = None
    distinct_measurement_count: int
    members: list[ModeShapeMemberOut]
    phase_pattern: dict[str, Any]
    reasons: list[DetectionEvidenceOut]
    limitations: list[DetectionEvidenceOut]


class ModeShapeComponentOut(BaseModel):
    component_id: int
    component_frequency_hz: float
    frequency_spread_hz: float
    match_tolerance_hz: float
    signal_count: int
    groups: list[ModeShapeGroupOut]
    cross_variable: dict[str, Any] | None = None


class OscillationModeShapeOut(BaseModel):
    status: Literal["ok", "no_components"]
    message: str | None = None
    setup: dict[str, float]
    parameters: dict[str, float | int | str | bool]
    timings_ms: dict[str, float]
    signals: list[CrossSignalRowOut]
    components: list[ModeShapeComponentOut] = []


# ---------------------------------------------------------------- coherence (DEC-181 [PROPOSAL])

class CoherenceRequest(ModeShapeRequest):
    """Same request as the mode shape: explicit signals, the setup band and an optional component frequency. No offset, no result."""


class CoherencePairOut(BaseModel):
    reference_signal: str
    reference_index: int
    member_signal: str
    member_index: int
    #: `same_variable` | `cross_variable` (different physical quantities: supporting evidence only).
    relationship_type: Literal["same_variable", "cross_variable"]
    signal_types: list[str]
    status: Literal["ok", "insufficient_evidence", "unavailable"]
    reason_code: str | None = None
    message: str | None = None
    #: The numbers behind a refusal, machine-readable and separate from the presentation text in `message`.
    reason_values: dict[str, Any] = {}
    component_frequency_hz: float
    #: Magnitude-squared coherence in [0, 1] of the bin nearest the component frequency (not a probability).
    coherence: float | None = None
    coherence_frequency_hz: float | None = None
    target_offset_hz: float | None = None
    bin_spacing_hz: float | None = None
    local_peak_coherence: float | None = None
    local_peak_frequency_hz: float | None = None
    local_peak_offset_hz: float | None = None
    local_median_coherence: float | None = None
    local_band_bins: int | None = None
    #: Coherence unrelated noise would exceed with probability alpha for this many averages (shown separately from the measurement).
    chance_level: float | None = None
    exceeds_chance_level: bool | None = None
    local_peak_exceeds_chance_level: bool | None = None
    segment_count: int | None = None
    independent_segment_count: int | None = None
    segment_s: float | None = None
    nperseg: int | None = None
    samples: int | None = None
    sample_rate_hz: float | None = None
    common_interval: dict[str, Any] | None = None
    cycles_used: float | None = None
    #: Mode Shape relative phase (degrees) of the member against the reference, when one exists (context for the low-coherence warning only).
    relative_phase_deg: float | None = None
    reasons: list[DetectionEvidenceOut] = []
    warnings: list[DetectionEvidenceOut] = []


class CoherenceComponentOut(BaseModel):
    component_id: int
    component_frequency_hz: float
    signal_count: int
    reference: dict[str, Any] | None = None
    #: `mode_shape_reference` | `highest_candidate_prominence`
    reference_rule: str | None = None
    excluded_members: list[dict[str, Any]] = []
    #: The reference against every other member (what the page shows).
    pairs: list[CoherencePairOut] = []
    #: Every other pair, kept for completeness.
    other_pairs: list[CoherencePairOut] = []
    limitations: list[DetectionEvidenceOut] = []
    cross_variable: dict[str, Any] | None = None


class OscillationCoherenceOut(BaseModel):
    status: Literal["ok", "no_components"]
    message: str | None = None
    setup: dict[str, float]
    parameters: dict[str, float | int | str | bool]
    timings_ms: dict[str, float]
    signals: list[CrossSignalRowOut]
    components: list[CoherenceComponentOut] = []


class InterpretationModeShapeOut(BaseModel):
    parameters: dict[str, float | int | str | bool]
    components: list[ModeShapeComponentOut] = []


class InterpretationCoherenceOut(BaseModel):
    parameters: dict[str, float | int | str | bool]
    components: list[CoherenceComponentOut] = []
