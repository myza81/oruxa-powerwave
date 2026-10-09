"""Oscillation Analysis -- STFT spectrogram service (DEC-176 [APPROVED],
building on DEC-171/172/173/174).

The time-frequency companion of the Welch spectrum. It reuses the spectrum's
ONE preprocessing path (`prepare_analysis_window`: workspace-state signal,
native or DEC-173 RMS representation, window and band validation) and the
spectrum's RMS warnings, then runs the NumPy STFT of
`app.domain.spectrogram_estimation`. Read-only; nothing is stored. The linear
PSD matrix crosses the wire (the browser converts to dB for display only).

Evidence only: no candidate detection, classification, damping or
ringdown logic exists here. A window too short for a useful picture is a valid
`unavailable` result (HTTP 200), never an error, so the Welch spectrum and its
candidates stay available.
"""

from __future__ import annotations

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.domain.spectrogram_estimation import (
    LIMITED_BY_MINIMUM_SAMPLES,
    LIMITED_BY_TIME_RESOLUTION,
    MIN_FREQUENCY_ROWS,
    MIN_STFT_SAMPLES,
    MIN_TIME_SLICES,
    MIN_WINDOW_CYCLES_OF_MIN_FREQUENCY,
    STFT_CYCLES_OF_MIN_FREQUENCY,
    STFT_DETREND,
    STFT_OVERLAP_FRACTION,
    STFT_SCALING,
    STFT_WINDOW,
    TARGET_TIME_SLICES,
    StftGeometry,
    choose_stft_geometry,
    peak_hold_rows,
    stft_psd,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_representation_service import UnsupportedRepresentationError
from app.services.oscillation_spectrum_service import (
    SPECTRUM_REPRESENTATIONS,
    _fmt,
    _validate_request_numbers,
    _warning,
    prepare_analysis_window,
    representation_block,
    representation_warnings,
    signal_block,
    window_block,
)
from app.services.workspace_registry import WorkspaceRegistry

#: Largest number of matrix cells (frequency rows x time columns) returned to the
#: browser. Above it, adjacent frequency rows are reduced by peak-hold (maximum).
MAX_MATRIX_CELLS = 120_000
#: Significant digits kept for transport (relative error <= 5e-7 per cell).
VALUE_DIGITS = 6

REASON_WINDOW_TOO_SHORT = "window_too_short"
REASON_FREQUENCY_RESOLUTION_TOO_COARSE = "frequency_resolution_too_coarse"
REASON_TOO_MANY_TIME_SLICES = "too_many_time_slices"

_WINDOW_RULE = f"min(2 / f_min, longest window giving {TARGET_TIME_SLICES} slices); T / 4.5 when f_min = 0"


class InvalidSpectrogramConfigurationError(ImportServiceError):
    code = "invalid_spectrogram_configuration"


def _stft_block(g: StftGeometry) -> dict:
    return {
        "window": STFT_WINDOW,
        "detrend": STFT_DETREND,
        "scaling": STFT_SCALING,
        "zero_padding": False,
        "nfft": g.nperseg,
        "nperseg": g.nperseg,
        "window_s": g.window_s,
        "target_window_s": g.target_window_s,
        "overlap_samples": g.noverlap,
        "overlap_fraction": STFT_OVERLAP_FRACTION,
        "hop_samples": g.hop,
        "hop_s": g.hop_s,
        "slice_count": g.slice_count,
        "unused_tail_samples": g.unused_tail_samples,
        "bin_spacing_hz": g.bin_spacing_hz,
        "time_stamp": "window_centre",
        "window_rule": _WINDOW_RULE,
        "limited_by": g.limited_by,
    }


def _round_significant(values: np.ndarray) -> list:
    """Nested lists rounded to `VALUE_DIGITS` significant digits (transport only)."""
    fmt = "%." + str(VALUE_DIGITS) + "g"
    if values.ndim == 1:
        return [float(fmt % v) for v in values.tolist()]
    return [[float(fmt % v) for v in row] for row in values.tolist()]


def compute_spectrogram(
    *,
    workspace_id: str,
    input_ref: ChannelRef,
    representation: str,
    signal_revision: str | None,
    window_start_s: float,
    window_end_s: float,
    f_min_hz: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> dict:
    """The wire-ready spectrogram (or an explained `unavailable` result) plus the
    exact parameters used. Raises a structured `ImportServiceError` for every
    invalid request -- the same validation as the spectrum."""
    if representation not in SPECTRUM_REPRESENTATIONS:
        raise UnsupportedRepresentationError(f"Analysis representation '{representation}' is not implemented.")
    _validate_request_numbers(window_start_s, window_end_s, f_min_hz, f_max_hz)
    prepared = prepare_analysis_window(
        workspace_id=workspace_id, input_ref=input_ref, representation=representation,
        window_start_s=window_start_s, window_end_s=window_end_s, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    series, active, t, x = prepared.series, prepared.active, prepared.t, prepared.x
    fs, nyquist, duration, nominal = prepared.fs, prepared.nyquist, prepared.window_duration, prepared.nominal

    result: dict = {
        "status": "ok", "reason_code": None, "message": None,
        "setup": {
            "representation": representation, "signal_revision": signal_revision,
            "window_start_s": window_start_s, "window_end_s": window_end_s,
            "frequency_min_hz": f_min_hz, "frequency_max_hz": f_max_hz,
        },
        "signal": signal_block(series, active, input_ref),
        "representation": representation_block(series, fs, nominal),
        "window": window_block(t, x, window_start_s, window_end_s, duration),
        "stft": None, "frequency": None, "matrix": None, "times_s": [], "frequencies_hz": [], "psd": [], "warnings": [],
    }

    def unavailable(code: str, message: str, geometry: StftGeometry | None, rows: int = 0) -> dict:
        result.update(status="unavailable", reason_code=code, message=message)
        result["stft"] = _stft_block(geometry) if geometry else None
        result["frequency"] = {
            "requested_min_hz": f_min_hz, "requested_max_hz": f_max_hz, "returned_min_hz": None, "returned_max_hz": None,
            "row_count": 0, "source_row_count": rows, "row_decimation_factor": 1, "nyquist_hz": nyquist,
        }
        return result

    too_short = "The selected window is too short to provide useful time-frequency resolution. Frequency Spectrum remains available."
    try:
        geometry = choose_stft_geometry(int(x.size), fs, f_min_hz)
    except ValueError as exc:
        return unavailable(REASON_WINDOW_TOO_SHORT, f"{too_short} ({exc})", None)
    if geometry.slice_count < MIN_TIME_SLICES:
        return unavailable(
            REASON_WINDOW_TOO_SHORT,
            f"{too_short} The window ({_fmt(duration)} s) holds only {geometry.slice_count} STFT slice(s) of "
            f"{_fmt(geometry.window_s)} s; at least {MIN_TIME_SLICES} are needed.",
            geometry,
        )
    if f_min_hz > 0 and geometry.window_s * f_min_hz < MIN_WINDOW_CYCLES_OF_MIN_FREQUENCY:
        return unavailable(
            REASON_WINDOW_TOO_SHORT,
            f"{too_short} The longest STFT window that keeps {TARGET_TIME_SLICES} time slices ({_fmt(geometry.window_s)} s) holds "
            f"{_fmt(geometry.window_s * f_min_hz)} cycle(s) of the lowest requested frequency {_fmt(f_min_hz)} Hz; at least "
            f"{_fmt(MIN_WINDOW_CYCLES_OF_MIN_FREQUENCY)} is needed. Raise the minimum frequency or analyse a longer window.",
            geometry,
        )
    grid = np.fft.rfftfreq(geometry.nperseg, d=1.0 / fs)
    edge = 1e-9 * max(1.0, f_max_hz)
    keep = (grid >= f_min_hz - edge) & (grid <= f_max_hz + edge)
    source_rows = int(np.count_nonzero(keep))
    if source_rows < MIN_FREQUENCY_ROWS:
        return unavailable(
            REASON_FREQUENCY_RESOLUTION_TOO_COARSE,
            f"The frequency resolution of the time-frequency window ({_fmt(geometry.bin_spacing_hz)} Hz, from a "
            f"{_fmt(geometry.window_s)} s window) leaves {source_rows} row(s) inside {_fmt(f_min_hz)} to {_fmt(f_max_hz)} Hz; "
            f"at least {MIN_FREQUENCY_ROWS} are needed. A longer window or a wider band is required. "
            "Frequency Spectrum remains available.",
            geometry, source_rows,
        )
    factor = 1
    if source_rows * geometry.slice_count > MAX_MATRIX_CELLS:
        factor = -(-source_rows * geometry.slice_count // MAX_MATRIX_CELLS)
        reduced_rows = -(-source_rows // factor)
        if reduced_rows * geometry.slice_count > MAX_MATRIX_CELLS:
            return unavailable(
                REASON_TOO_MANY_TIME_SLICES,
                f"The spectrogram would hold {geometry.slice_count} time slices, more than can be returned "
                f"({MAX_MATRIX_CELLS} cells). Choose a shorter window or a lower maximum frequency. "
                "Frequency Spectrum remains available.",
                geometry, source_rows,
            )

    try:
        gram = stft_psd(x, fs, geometry)
    except ValueError as exc:
        raise InvalidSpectrogramConfigurationError(str(exc)) from exc
    freqs, psd = gram.frequencies_hz[keep], gram.psd[keep, :]
    if not (np.all(np.isfinite(freqs)) and np.all(np.isfinite(psd))):
        raise InvalidSpectrogramConfigurationError("The STFT produced non-finite values.")
    freqs, psd = peak_hold_rows(freqs, psd, factor)
    times = float(t[0]) + gram.times_s

    warnings: list[dict] = []
    if geometry.limited_by in (LIMITED_BY_TIME_RESOLUTION, LIMITED_BY_MINIMUM_SAMPLES):
        reach = (
            f"; components below about {_fmt(STFT_CYCLES_OF_MIN_FREQUENCY / geometry.window_s)} Hz "
            "fit fewer than two cycles per slice"
        )
        warnings.append(_warning(
            "window_shortened_for_time_resolution",
            f"The STFT window ({_fmt(geometry.window_s)} s) is shorter than the {_fmt(geometry.target_window_s)} s wanted for the "
            f"lowest requested frequency, so that at least {TARGET_TIME_SLICES} time slices fit; the frequency-row spacing is "
            f"{_fmt(geometry.bin_spacing_hz)} Hz (coarser than the Welch spectrum's){reach}. "
            "For better time resolution, raise the minimum analysis frequency when lower-frequency components are not required.",
        ))
    if geometry.limited_by == LIMITED_BY_MINIMUM_SAMPLES or geometry.slice_count < TARGET_TIME_SLICES:
        warnings.append(_warning(
            "few_time_slices",
            f"Only {geometry.slice_count} time slices fit the window (minimum window {MIN_STFT_SAMPLES} samples); the time "
            "resolution is limited.",
        ))
    if f_min_hz > 0 and geometry.bin_spacing_hz > f_min_hz:
        warnings.append(_warning(
            "min_frequency_below_bin_spacing",
            f"The lowest requested frequency {_fmt(f_min_hz)} Hz is below the STFT row spacing {_fmt(geometry.bin_spacing_hz)} Hz; "
            f"the first returned row is {_fmt(float(freqs[0]))} Hz and low-frequency content is not resolved.",
        ))
    if factor > 1:
        warnings.append(_warning(
            "frequency_rows_reduced",
            f"Display frequency rows reduced {factor}× using peak-hold (each returned row is the maximum of {factor} adjacent "
            f"rows, never an average; the band holds {source_rows} rows); narrow the frequency band for full resolution.",
        ))
    warnings.extend(representation_warnings(series, nominal, f_max_hz))

    result.update(
        stft=_stft_block(geometry),
        frequency={
            "requested_min_hz": f_min_hz, "requested_max_hz": f_max_hz,
            "returned_min_hz": float(freqs[0]), "returned_max_hz": float(freqs[-1]), "row_count": int(freqs.size),
            "source_row_count": source_rows, "row_decimation_factor": factor, "nyquist_hz": nyquist,
        },
        matrix={
            "rows": int(psd.shape[0]), "columns": int(psd.shape[1]), "cells": int(psd.size), "max_cells": MAX_MATRIX_CELLS,
            "value_digits": VALUE_DIGITS,
        },
        times_s=times.tolist(), frequencies_hz=freqs.tolist(), psd=_round_significant(psd), warnings=warnings,
    )
    return result
