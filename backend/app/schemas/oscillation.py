"""Wire shapes for the Oscillation Analysis representation endpoint
(DEC-173 [APPROVED]). Metadata only -- no sample arrays."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

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
