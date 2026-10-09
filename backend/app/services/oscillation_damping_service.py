"""Oscillation Analysis -- ringdown damping service (DEC-177 [PROPOSAL], building
on DEC-171..176).

For the accepted DEC-175 candidates of one setup it estimates whether each
component decays, is approximately sustained or grows, and how fast
(`app.domain.damping_estimation`). The setup is re-validated exactly as the
spectrum does it: the signal comes from WORKSPACE STATE, and the candidates are
those of a fresh run of the SAME Welch spectrum + DEC-175 detection (no second
peak detector; the browser's candidate list is only a selection that must
match). Read-only: nothing is stored. Independent of the spectrogram: no STFT
or pixel is consulted.
"""

from __future__ import annotations

from app.domain import damping_estimation as de
from app.domain.calculated_channel import ChannelRef
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_representation_service import UnsupportedRepresentationError
from app.services.oscillation_spectrum_service import (
    SPECTRUM_REPRESENTATIONS,
    _validate_request_numbers,
    compute_spectrum,
    prepare_analysis_window,
    representation_block,
    signal_block,
    window_block,
)
from app.services.workspace_registry import WorkspaceRegistry

#: Spectrum warnings that apply equally to the damping result.
_CARRIED_SPECTRUM_WARNINGS = ("rms_rolloff", "nominal_frequency_assumed")
_CARRIED_CANDIDATE_WARNINGS = ("rms_representation_attenuation",)
_FREQUENCY_MATCH_TOLERANCE = 1e-6


class CandidateMismatchError(ImportServiceError):
    code = "candidate_mismatch"


def _parameters() -> dict:
    return {
        "model": "A exp(-alpha t) cos(2 pi f t + phi) + offset/trend",
        "decay_rate_convention": "alpha = -sigma [1/s]; amplitude ~ exp(-alpha t); alpha > 0 decays, alpha < 0 grows",
        "frequency_convention": "damped oscillation frequency f [Hz]; omega = 2 pi f",
        "damping_ratio": "zeta = alpha / sqrt(alpha^2 + omega^2), decaying components only",
        "estimator": "zero-phase Gaussian band-pass (FFT) -> analytic envelope -> least-squares fit of ln(envelope)",
        "bandwidth_fraction": de.BANDWIDTH_FRACTION,
        "min_bandwidth_hz": de.MIN_BANDWIDTH_HZ,
        "isolation_sigmas": de.ISOLATION_SIGMAS,
        "edge_guard_sigmas": de.EDGE_GUARD_SIGMAS,
        "min_amplitude_over_noise": de.MIN_AMPLITUDE_OVER_NOISE,
        "envelope_floor_fraction": de.ENVELOPE_FLOOR_FRACTION,
        "min_fit_cycles": de.MIN_FIT_CYCLES,
        "min_fit_samples": de.MIN_FIT_SAMPLES,
        "sustained_envelope_change": de.SUSTAINED_ENVELOPE_CHANGE,
        "max_rms_log_residual": de.MAX_RMS_LOG_RESIDUAL,
        "min_r_squared": de.MIN_R_SQUARED,
        "min_monotonic_fraction": de.MIN_MONOTONIC_FRACTION,
        "heuristics": "Phase-1 engineering heuristics, not standards",
    }


def _select(candidates: list[dict], requested: list[float] | None) -> list[dict]:
    if not requested:
        return candidates
    chosen: list[dict] = []
    for frequency in requested:
        match = next(
            (c for c in candidates if abs(c["frequency_hz"] - frequency) <= _FREQUENCY_MATCH_TOLERANCE * max(1.0, abs(frequency))),
            None,
        )
        if match is None:
            raise CandidateMismatchError(
                f"{frequency:.6g} Hz is not an accepted spectral candidate of this setup; run the analysis again."
            )
        if match not in chosen:
            chosen.append(match)
    return chosen


def compute_damping(
    *,
    workspace_id: str,
    input_ref: ChannelRef,
    representation: str,
    signal_revision: str | None,
    window_start_s: float,
    window_end_s: float,
    f_min_hz: float,
    f_max_hz: float,
    candidate_frequencies_hz: list[float] | None,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> dict:
    if representation not in SPECTRUM_REPRESENTATIONS:
        raise UnsupportedRepresentationError(f"Analysis representation '{representation}' is not implemented.")
    _validate_request_numbers(window_start_s, window_end_s, f_min_hz, f_max_hz)

    spectrum = compute_spectrum(
        workspace_id=workspace_id, input_ref=input_ref, representation=representation,
        window_start_s=window_start_s, window_end_s=window_end_s, f_min_hz=f_min_hz, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    prepared = prepare_analysis_window(
        workspace_id=workspace_id, input_ref=input_ref, representation=representation,
        window_start_s=window_start_s, window_end_s=window_end_s, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    series = prepared.series
    detected = spectrum["detection"]["candidates"]
    selected = _select(detected, candidate_frequencies_hz)

    warnings = [w for w in spectrum["warnings"] if w["code"] in _CARRIED_SPECTRUM_WARNINGS]
    out = {
        "status": "ok" if selected else "no_candidates",
        "message": None if selected else "No oscillation candidate was detected in this setup, so there is no component to assess for damping.",
        "setup": {
            "representation": representation, "signal_revision": signal_revision, "window_start_s": window_start_s,
            "window_end_s": window_end_s, "frequency_min_hz": f_min_hz, "frequency_max_hz": f_max_hz,
        },
        "signal": signal_block(series, prepared.active, input_ref),
        "representation": representation_block(series, prepared.fs, prepared.nominal),
        "window": window_block(prepared.t, prepared.x, window_start_s, window_end_s, prepared.window_duration),
        "parameters": _parameters(),
        "results": [],
        "warnings": warnings,
    }
    if not selected:
        return out

    ws = de.window_spectrum(float(prepared.t[0]), prepared.x, prepared.fs)
    all_candidates = [(c["frequency_hz"], c["psd"]) for c in detected]
    for candidate in selected:
        result = de.estimate_damping(ws, candidate["frequency_hz"], candidate["psd"], all_candidates, series.unit)
        result["rank"] = candidate["rank"]
        for carried in candidate["warnings"]:
            if carried["code"] in _CARRIED_CANDIDATE_WARNINGS:
                result["warnings"].append({"code": carried["code"], "message": carried["message"], "values": carried.get("values", {})})
        out["results"].append(result)
    return out
