"""Oscillation Analysis -- Welch PSD / Frequency Spectrum service (DEC-174
[PROPOSAL], building on DEC-171/172/173).

Resolves the selected signal from WORKSPACE STATE (never from samples sent by
the browser), obtains the analysis representation -- the signal as recorded
or, for a raw Voltage/Current waveform, the DEC-173 RMS magnitude (the
existing `derive_analysis_representation`, not re-implemented) -- selects the
requested analysis window, and runs the Welch PSD of
`app.domain.spectral_estimation`. Read-only: nothing is stored, registered as
a calculated channel or cached; only the compact, band-limited spectrum and
the exact parameters used cross the wire.

The PSD is returned as computed (no RMS roll-off compensation). Candidate
detection (DEC-175 [PROPOSAL], `app.domain.oscillation_peaks`) is a separate,
deterministic pass over those same bins -- no second Welch run -- reported in
the `detection` block. No classification, spectrogram or damping exists here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import (
    CURRENT,
    VOLTAGE,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
)
from app.domain.oscillation_representation import (
    REPRESENTATION_RMS_MAGNITUDE,
    rms_bandwidth_limit_hz,
    rms_envelope_response,
    rms_half_power_frequency_hz,
)
from app.domain.oscillation_peaks import (
    MAX_REPORTED_CANDIDATES,
    MAX_REPORTED_NOT_PROMOTED,
    Detection,
    detect_candidates,
)
from app.domain.spectral_estimation import (
    MIN_SEGMENT_SAMPLES,
    RECOMMENDED_MIN_SEGMENTS,
    WELCH_AVERAGE,
    WELCH_DETREND,
    WELCH_OVERLAP_FRACTION,
    WELCH_SCALING,
    WELCH_WINDOW,
    choose_segmentation,
    welch_psd,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import _resolve_input
from app.services.errors import ImportServiceError, SourceNotFoundError
from app.services.oscillation_representation_service import (
    NOMINAL_FREQUENCY_ASSUMED_DEFAULT,
    STATUS_READY,
    UnsupportedRepresentationError,
    derive_analysis_representation,
)
from app.services.workspace_registry import WorkspaceRegistry

REPRESENTATION_NATIVE = "native"
SPECTRUM_REPRESENTATIONS = (REPRESENTATION_NATIVE, REPRESENTATION_RMS_MAGNITUDE)

#: Largest relative deviation of any sample interval from the median interval
#: before a series is refused as not uniformly sampled (Welch assumes a
#: constant `fs`; the project does not resample).
UNIFORM_SAMPLING_TOLERANCE = 0.01
#: A window whose peak-to-peak range is below this fraction of its largest
#: magnitude has no signal variation to assess (guards float round-off noise).
NEGLIGIBLE_VARIATION_RATIO = 1e-12
#: Window-edge matching tolerance, as a fraction of one sample interval.
EDGE_TOLERANCE_SAMPLES = 1e-3


class InvalidAnalysisWindowError(ImportServiceError):
    code = "invalid_analysis_window"


class InvalidFrequencyRangeError(ImportServiceError):
    code = "invalid_frequency_range"


class RepresentationUnavailableError(ImportServiceError):
    code = "representation_unavailable"


class RepresentationMismatchError(ImportServiceError):
    code = "representation_mismatch"


class InsufficientSamplesError(ImportServiceError):
    code = "insufficient_samples"


class NonFiniteSamplesError(ImportServiceError):
    code = "non_finite_samples"


class NonUniformSamplingError(ImportServiceError):
    code = "non_uniform_sampling"


class InvalidWelchConfigurationError(ImportServiceError):
    code = "invalid_welch_configuration"


@dataclass(frozen=True, slots=True)
class _Series:
    time: np.ndarray
    values: np.ndarray
    unit: str
    representation: str
    source_sample_rate_hz: float | None
    source_sample_count: int
    valid_start_s: float
    valid_end_s: float
    nominal_frequency_hz: float | None
    nominal_frequency_origin: str | None
    window_s: float | None
    group_delay_s: float | None


def _warning(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}g}"


def _median_rate(time: np.ndarray) -> float | None:
    if time.shape[0] < 2:
        return None
    dt = float(np.median(np.diff(time)))
    return 1.0 / dt if dt > 0 else None


def _analysis_series(
    *, workspace_id: str, input_ref: ChannelRef, representation: str,
    source_registry: WorkspaceRegistry, calc_registry: CalculatedChannelRegistry,
):
    """`(series, active_source)` for the requested representation."""
    resolved = _resolve_input(
        input_ref, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry
    )
    active = source_registry.get(workspace_id, resolved.reference_source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{resolved.reference_source_id}' in workspace '{workspace_id}'.")
    time = np.asarray(resolved.time, dtype=np.float64)
    source_rate = _median_rate(time)

    if representation == REPRESENTATION_NATIVE:
        if resolved.engineering_type in (VOLTAGE, CURRENT) and resolved.waveform_form not in (
            WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE
        ):
            raise RepresentationMismatchError(
                "This Voltage/Current signal is not known to be RMS/magnitude; analysing it as recorded would put the "
                "nominal-frequency carrier in the spectrum. Request the 'rms_magnitude' representation."
            )
        if time.shape[0] < 2:
            raise InsufficientSamplesError("The signal holds fewer than two samples.")
        return _Series(
            time=time, values=np.asarray(resolved.values, dtype=np.float64), unit=resolved.unit or "",
            representation=REPRESENTATION_NATIVE, source_sample_rate_hz=source_rate,
            source_sample_count=int(time.shape[0]), valid_start_s=float(time[0]), valid_end_s=float(time[-1]),
            nominal_frequency_hz=None, nominal_frequency_origin=None, window_s=None, group_delay_s=None,
        ), active

    derived_info = derive_analysis_representation(
        workspace_id=workspace_id, input_ref=input_ref, representation=representation,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    if derived_info.status != STATUS_READY or derived_info.derived is None:
        raise RepresentationUnavailableError(
            derived_info.message or "The RMS magnitude representation is not available for this signal."
        )
    d = derived_info.derived
    return _Series(
        time=d.time, values=d.values, unit=resolved.unit or "", representation=REPRESENTATION_RMS_MAGNITUDE,
        source_sample_rate_hz=source_rate, source_sample_count=int(d.time.shape[0]),
        valid_start_s=float(d.time[d.first_valid_index]), valid_end_s=float(d.time[d.last_valid_index]),
        nominal_frequency_hz=d.nominal_frequency_hz, nominal_frequency_origin=derived_info.nominal_frequency_origin,
        window_s=d.window_s, group_delay_s=d.group_delay_s,
    ), active


def _validate_request_numbers(start_s: float, end_s: float, f_min_hz: float, f_max_hz: float) -> None:
    if not (math.isfinite(start_s) and math.isfinite(end_s)):
        raise InvalidAnalysisWindowError("The analysis window start and end must be finite numbers.")
    if not end_s > start_s:
        raise InvalidAnalysisWindowError("The analysis window end must be greater than its start.")
    if not (math.isfinite(f_min_hz) and math.isfinite(f_max_hz)):
        raise InvalidFrequencyRangeError("The frequency range must be finite numbers.")
    if f_min_hz < 0:
        raise InvalidFrequencyRangeError("The minimum frequency must not be negative.")
    if not f_max_hz > f_min_hz:
        raise InvalidFrequencyRangeError("The maximum frequency must be greater than the minimum frequency.")


@dataclass(frozen=True, slots=True)
class PreparedWindow:
    """The validated, finite, uniformly sampled analysis window shared by the
    Welch spectrum and the STFT spectrogram (one preprocessing path)."""

    series: _Series
    active: object
    t: np.ndarray
    x: np.ndarray
    fs: float
    nyquist: float
    window_duration: float
    nominal: float | None


def prepare_analysis_window(
    *,
    workspace_id: str,
    input_ref: ChannelRef,
    representation: str,
    window_start_s: float,
    window_end_s: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> PreparedWindow:
    """Resolve the signal, derive the representation and select/validate the
    window and the upper band limit. Raises a structured `ImportServiceError`
    for every unusable request."""
    series, active = _analysis_series(
        workspace_id=workspace_id, input_ref=input_ref, representation=representation,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    time, values = series.time, series.values
    fs_source = series.source_sample_rate_hz
    if fs_source is None:
        raise InsufficientSamplesError("The signal's sampling rate cannot be determined.")
    dt = 1.0 / fs_source
    tolerance = EDGE_TOLERANCE_SAMPLES * dt
    if window_start_s < series.valid_start_s - tolerance or window_end_s > series.valid_end_s + tolerance:
        raise InvalidAnalysisWindowError(
            f"The analysis window ({_fmt(window_start_s)} to {_fmt(window_end_s)} s) lies outside the usable range of the "
            f"signal ({_fmt(series.valid_start_s)} to {_fmt(series.valid_end_s)} s)."
        )

    selected = np.flatnonzero((time >= window_start_s - tolerance) & (time <= window_end_s + tolerance))
    if selected.size < MIN_SEGMENT_SAMPLES:
        raise InsufficientSamplesError(
            f"The analysis window holds {selected.size} sample(s); at least {MIN_SEGMENT_SAMPLES} are required."
        )
    t = time[selected]
    x = values[selected]
    if not np.all(np.isfinite(x)):
        raise NonFiniteSamplesError(
            f"The analysis window contains {int(np.count_nonzero(~np.isfinite(x)))} non-finite sample(s); "
            "choose a window without gaps. Nothing is interpolated."
        )
    steps = np.diff(t)
    median_step = float(np.median(steps))
    if median_step <= 0 or float(np.max(np.abs(steps - median_step))) > UNIFORM_SAMPLING_TOLERANCE * median_step:
        raise NonUniformSamplingError(
            "The samples in the analysis window are not uniformly spaced; Welch PSD needs a constant sampling rate "
            "and the series is not resampled."
        )
    fs = 1.0 / median_step
    nyquist = fs / 2.0
    window_duration = float(t[-1] - t[0])

    nominal = series.nominal_frequency_hz
    if f_max_hz > nyquist * (1 + 1e-9):
        raise InvalidFrequencyRangeError(
            f"The maximum frequency {_fmt(f_max_hz)} Hz exceeds the Nyquist frequency {_fmt(nyquist)} Hz of the analysed samples."
        )
    if nominal is not None and f_max_hz >= rms_bandwidth_limit_hz(nominal):
        raise InvalidFrequencyRangeError(
            f"The maximum frequency {_fmt(f_max_hz)} Hz reaches the bandwidth limit of the RMS magnitude representation "
            f"({_fmt(rms_bandwidth_limit_hz(nominal))} Hz, the nominal frequency); modulation at or above it is not recoverable."
        )
    return PreparedWindow(
        series=series, active=active, t=t, x=x, fs=fs, nyquist=nyquist, window_duration=window_duration, nominal=nominal,
    )


def representation_warnings(series: _Series, nominal: float | None, f_max_hz: float) -> list[dict]:
    """The RMS-representation warnings of DEC-173/174 (assumed nominal frequency,
    roll-off), shared by the spectrum and the spectrogram."""
    warnings: list[dict] = []
    if nominal is not None:
        if series.nominal_frequency_origin == NOMINAL_FREQUENCY_ASSUMED_DEFAULT:
            warnings.append(_warning(
                "nominal_frequency_assumed",
                "The nominal frequency was not declared by the source and a default was assumed for the RMS window.",
            ))
        half_power = rms_half_power_frequency_hz(nominal)
        if f_max_hz > half_power:
            loss = 100.0 * (1.0 - rms_envelope_response(f_max_hz, nominal))
            warnings.append(_warning(
                "rms_rolloff",
                f"The requested range extends above the −3 dB frequency {_fmt(half_power)} Hz of the one-cycle RMS magnitude; "
                f"oscillation amplitude at {_fmt(f_max_hz)} Hz is attenuated by about {loss:.0f} % (zero at "
                f"{_fmt(rms_bandwidth_limit_hz(nominal))} Hz). The PSD is not corrected for this.",
            ))
    return warnings


def signal_block(series: _Series, active, input_ref: ChannelRef) -> dict:
    metadata = active.metadata
    filenames = list(metadata.original_filenames or ())
    return {
        "name": input_ref.channel_name if input_ref.kind == "source" else None,
        "calculated_channel_id": input_ref.calculated_channel_id if input_ref.kind == "calculated" else None,
        "source_id": metadata.source_id,
        "source_recording": filenames[0] if filenames else (metadata.station_name or None),
        "unit": series.unit or None,
        "psd_unit": f"{series.unit}²/Hz" if series.unit else None,
    }


def representation_block(series: _Series, fs: float, nominal: float | None) -> dict:
    return {
        "type": series.representation,
        "source_sample_rate_hz": series.source_sample_rate_hz,
        "analysis_sample_rate_hz": fs,
        "nominal_frequency_hz": nominal,
        "nominal_frequency_origin": series.nominal_frequency_origin,
        "rms_window_s": series.window_s,
        "rms_group_delay_s": series.group_delay_s,
        "bandwidth_half_power_hz": rms_half_power_frequency_hz(nominal) if nominal else None,
        "bandwidth_limit_hz": rms_bandwidth_limit_hz(nominal) if nominal else None,
    }


def window_block(t: np.ndarray, x: np.ndarray, window_start_s: float, window_end_s: float, window_duration: float) -> dict:
    return {
        "requested_start_s": window_start_s,
        "requested_end_s": window_end_s,
        "start_s": float(t[0]),
        "end_s": float(t[-1]),
        "duration_s": window_duration,
        "sample_count": int(x.size),
        "basic_resolution_hz": 1.0 / window_duration,
    }


def compute_spectrum(
    *,
    workspace_id: str,
    input_ref: ChannelRef,
    representation: str,
    window_start_s: float,
    window_end_s: float,
    f_min_hz: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> dict:
    """The wire-ready spectrum + the exact parameters used. Raises a
    structured `ImportServiceError` for every unusable request; never returns
    an empty spectrum."""
    if representation not in SPECTRUM_REPRESENTATIONS:
        raise UnsupportedRepresentationError(f"Analysis representation '{representation}' is not implemented.")
    _validate_request_numbers(window_start_s, window_end_s, f_min_hz, f_max_hz)

    prepared = prepare_analysis_window(
        workspace_id=workspace_id, input_ref=input_ref, representation=representation,
        window_start_s=window_start_s, window_end_s=window_end_s, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    series, active, t, x = prepared.series, prepared.active, prepared.t, prepared.x
    fs, nyquist, window_duration, nominal = prepared.fs, prepared.nyquist, prepared.window_duration, prepared.nominal

    try:
        seg = choose_segmentation(int(x.size), fs, f_min_hz)
        result = welch_psd(x, fs, seg)
    except ValueError as exc:
        raise InvalidWelchConfigurationError(str(exc)) from exc

    freqs, psd = result.frequencies_hz, result.psd
    edge = 1e-9 * max(1.0, f_max_hz)
    keep = (freqs >= f_min_hz - edge) & (freqs <= f_max_hz + edge)
    if not np.any(keep):
        raise InvalidWelchConfigurationError(
            f"The requested range {_fmt(f_min_hz)} to {_fmt(f_max_hz)} Hz contains no Welch frequency bin "
            f"(bin spacing {_fmt(seg.bin_spacing_hz)} Hz)."
        )
    freqs, psd = freqs[keep], psd[keep]
    if not (np.all(np.isfinite(freqs)) and np.all(np.isfinite(psd))):
        raise InvalidWelchConfigurationError("The Welch estimate produced non-finite values.")

    warnings: list[dict] = []
    if f_min_hz > 0 and seg.target_segment_s > window_duration:
        warnings.append(_warning(
            "insufficient_window_for_min_frequency",
            f"The window ({_fmt(window_duration)} s) is shorter than the {_fmt(seg.target_segment_s)} s segment (two cycles of "
            f"{_fmt(f_min_hz)} Hz) wanted for the lowest requested frequency; the segment was shortened to the window.",
        ))
    if f_min_hz > 0 and seg.bin_spacing_hz > f_min_hz:
        warnings.append(_warning(
            "min_frequency_below_bin_spacing",
            f"The lowest requested frequency {_fmt(f_min_hz)} Hz is below the Welch bin spacing {_fmt(seg.bin_spacing_hz)} Hz; "
            f"the first returned bin is {_fmt(float(freqs[0]))} Hz and low-frequency content is not resolved.",
        ))
    if seg.segment_count == 1:
        warnings.append(_warning(
            "single_segment",
            "Only one Welch segment fits the window, so no averaging took place; this is a single windowed periodogram "
            "with high variance.",
        ))
    elif seg.segment_count < RECOMMENDED_MIN_SEGMENTS:
        warnings.append(_warning(
            "few_segments",
            f"Only {seg.segment_count} Welch segments were averaged (fewer than {RECOMMENDED_MIN_SEGMENTS}); the estimate "
            "has limited variance reduction.",
        ))
    warnings.extend(representation_warnings(series, nominal, f_max_hz))

    peak_to_peak = float(np.ptp(x))
    detection = detect_candidates(
        freqs, psd, window_duration_s=window_duration, segment_count=seg.segment_count,
        rms_nominal_frequency_hz=nominal,
        signal_variation_negligible=peak_to_peak <= NEGLIGIBLE_VARIATION_RATIO * float(np.max(np.abs(x))),
    )

    return {
        "status": "ok",
        "signal": signal_block(series, active, input_ref),
        "representation": representation_block(series, fs, nominal),
        "window": window_block(t, x, window_start_s, window_end_s, window_duration),
        "welch": {
            "detrend": WELCH_DETREND,
            "window": WELCH_WINDOW,
            "scaling": WELCH_SCALING,
            "average": WELCH_AVERAGE,
            "zero_padding": False,
            "nfft": seg.nperseg,
            "nperseg": seg.nperseg,
            "segment_s": seg.segment_s,
            "target_segment_s": seg.target_segment_s,
            "overlap_samples": seg.noverlap,
            "overlap_fraction": WELCH_OVERLAP_FRACTION,
            "segment_count": seg.segment_count,
            "unused_tail_samples": seg.unused_tail_samples,
            "bin_spacing_hz": seg.bin_spacing_hz,
            "segment_rule": "2 / f_min" if f_min_hz > 0 else "window / 4.5 (f_min = 0)",
        },
        "frequency": {
            "requested_min_hz": f_min_hz,
            "requested_max_hz": f_max_hz,
            "returned_min_hz": float(freqs[0]),
            "returned_max_hz": float(freqs[-1]),
            "bin_count": int(freqs.size),
            "nyquist_hz": nyquist,
        },
        "frequencies_hz": freqs.tolist(),
        "psd": psd.tolist(),
        "warnings": warnings,
        "detection": _detection_wire(detection),
    }


def _detection_wire(detection: Detection) -> dict:
    """The compact wire form: the complete deterministic result is in `detection`;
    only the first `MAX_REPORTED_*` entries cross the wire, with the totals."""
    total = len(detection.candidates)
    return {
        "status": detection.status,
        "candidates": detection.candidates[:MAX_REPORTED_CANDIDATES],
        "total_candidates": total,
        "truncated": total > MAX_REPORTED_CANDIDATES,
        "not_promoted": detection.not_promoted[:MAX_REPORTED_NOT_PROMOTED],
        "no_candidate_reasons": detection.no_candidate_reasons,
        "low_frequency": detection.low_frequency,
        "parameters": detection.parameters,
        "counts": detection.counts,
    }
