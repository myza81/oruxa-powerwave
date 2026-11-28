"""NF-3A numerical probes (investigation only; imports production code read-only, changes nothing).

Each probe feeds an exactly known synthetic signal to an existing frequency-dependent function and compares the output
with a closed-form expected value, so the assessment's oracles are measured, not assumed.
Run from the backend directory:  python <this file>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend")) if "backend" not in str(Path.cwd()) else None

from app.domain.calculated_channel import (  # noqa: E402
    MIN_SAMPLES_PER_CYCLE, OP_ACTIVE_POWER, OP_REACTIVE_POWER, evaluate_power_channel, evaluate_rms,
)
from app.domain.overcurrent import OVERCURRENT_MIN_SAMPLES_PER_CYCLE, estimate_trailing_rms_at_time  # noqa: E402
from app.domain.phasor import PHASOR_MIN_SAMPLES_PER_CYCLE, estimate_phasor  # noqa: E402
from app.domain.rms_detector import classify_waveform_form  # noqa: E402
from app.domain.sliding_phasor import compute_sliding_phasor  # noqa: E402

AMP = 100.0
EXPECTED_RMS = AMP / math.sqrt(2.0)
OUT: dict = {}


def signal(f_sig: float, fs: float, seconds: float, phase_deg: float = 0.0, amp: float = AMP):
    n = int(round(fs * seconds)) + 1
    t = np.arange(n) / fs
    return t, amp * np.cos(2 * np.pi * f_sig * t + math.radians(phase_deg))


def steady(t: np.ndarray, f_nom: float, cycles: float = 2.0) -> np.ndarray:
    return t >= cycles / f_nom + 1e-9


# --------------------------------------------------------------------------------------------- P1 RMS
def p1_rms():
    rows = []
    for fs in (5000.0, 4800.0, 4096.0, 3200.0, 1920.0):
        for f_sig in (50.0, 60.0):
            for f_nom in (50.0, 60.0):
                t, x = signal(f_sig, fs, 0.5)
                out = evaluate_rms(t, x, f_nom)
                m = steady(t, f_nom) & np.isfinite(out)
                e = (out[m] / EXPECTED_RMS - 1.0) * 100.0
                rows.append({
                    "fs_hz": fs, "signal_hz": f_sig, "nominal_hz": f_nom, "samples_per_cycle_at_nominal": round(fs / f_nom, 3),
                    "mean_error_pct": round(float(np.mean(e)), 5), "max_abs_error_pct": round(float(np.max(np.abs(e))), 5),
                    "ripple_pp_pct": round(float(np.max(e) - np.min(e)), 5),
                })
    OUT["P1_rms_trailing_one_cycle"] = rows


# --------------------------------------------------------------------------------------------- P2 sliding phasor
def p2_phasor():
    rows = []
    for fs in (5000.0, 4800.0, 4096.0):
        for f_sig in (50.0, 60.0):
            for f_nom in (50.0, 60.0):
                t, x = signal(f_sig, fs, 0.5, phase_deg=30.0)
                res = compute_sliding_phasor(t, x, f_nom)
                m = res.available.copy()
                mag = np.abs(res.phasor[m])
                # Expected angle: the phasor of cos(w t + phi) over a trailing window referenced to t=0 is phi at nominal.
                ang = np.degrees(np.angle(res.phasor[m]))
                rows.append({
                    "fs_hz": fs, "signal_hz": f_sig, "nominal_hz": f_nom, "available_windows": int(m.sum()),
                    "mag_mean_error_pct": round(float((np.mean(mag) / EXPECTED_RMS - 1.0) * 100.0), 5) if m.any() else None,
                    "mag_ripple_pp_pct": round(float((np.max(mag) - np.min(mag)) / EXPECTED_RMS * 100.0), 5) if m.any() else None,
                    "angle_mean_deg": round(float(np.mean(ang)), 4) if m.any() else None,
                    "angle_pp_deg": round(float(np.max(ang) - np.min(ang)), 4) if m.any() else None,
                })
    OUT["P2_sliding_phasor_trailing_one_cycle"] = rows

    # single-point estimator at one time, nominal vs mismatched
    rows = []
    for f_sig, f_nom in ((50.0, 50.0), (60.0, 60.0), (60.0, 50.0), (50.0, 60.0)):
        t, x = signal(f_sig, 4800.0, 0.5, phase_deg=30.0)
        est = estimate_phasor(t, x, 0.3, f_nom)
        rows.append({"signal_hz": f_sig, "nominal_hz": f_nom, "available": est.available,
                     "mag_error_pct": round((est.magnitude_rms / EXPECTED_RMS - 1.0) * 100.0, 4) if est.available else None,
                     "reason": est.reason_code})
    OUT["P2b_estimate_phasor_single_point_4800hz"] = rows


# --------------------------------------------------------------------------------------------- P3 power (hard-coded 50 Hz)
def p3_power():
    rows = []
    v_pk, i_pk, phi = 100e3, 1e3, 30.0
    p_exp = 0.5 * v_pk * i_pk * math.cos(math.radians(phi)) / 1e6
    q_exp = 0.5 * v_pk * i_pk * math.sin(math.radians(phi)) / 1e6
    for fs in (4800.0, 5000.0, 4096.0):
        for f_sig in (50.0, 60.0):
            for f_used in (50.0, 60.0):
                t, v = signal(f_sig, fs, 0.5, 0.0, v_pk)
                _, i = signal(f_sig, fs, 0.5, -phi, i_pk)       # current lags voltage by phi: passive P, Q > 0
                p = evaluate_power_channel(OP_ACTIVE_POWER, t, v, 1.0, i, 1.0, f_used)
                q = evaluate_power_channel(OP_REACTIVE_POWER, t, v, 1.0, i, 1.0, f_used)
                m = steady(t, f_used) & np.isfinite(p) & np.isfinite(q)
                rows.append({
                    "fs_hz": fs, "signal_hz": f_sig, "window_nominal_hz": f_used,
                    "P_expected_MW": round(p_exp, 4), "P_mean_MW": round(float(np.mean(p[m])), 4),
                    "P_mean_error_pct": round(float((np.mean(p[m]) / p_exp - 1.0) * 100.0), 4),
                    "P_ripple_pp_pct": round(float((np.max(p[m]) - np.min(p[m])) / p_exp * 100.0), 4),
                    "Q_mean_error_pct": round(float((np.mean(q[m]) / q_exp - 1.0) * 100.0), 4),
                })
    OUT["P3_power_channel_window_frequency"] = rows
    OUT["P3_note"] = ("services/calculated_channel_service.py passes NO frequency to evaluate_power_channel (domain default 50.0), "
                      "so rows with window_nominal_hz=50 on signal_hz=60 are what a 60 Hz recording gets today.")


# --------------------------------------------------------------------------------------------- P4 detector
def p4_detector():
    rows = []
    for f_sig in (50.0, 60.0):
        for f_nom in (50.0, 60.0):
            t, x = signal(f_sig, 4800.0, 0.5)
            rows.append({"signal_hz": f_sig, "nominal_hz": f_nom, "verdict": classify_waveform_form(t, x, f_nom)})
    # a flat RMS-like magnitude trace must stay magnitude-like at either nominal
    t = np.arange(2401) / 4800.0
    mag = 70.7 + 0.3 * np.sin(2 * np.pi * 2.0 * t)
    for f_nom in (50.0, 60.0):
        rows.append({"signal": "magnitude_trace", "nominal_hz": f_nom, "verdict": classify_waveform_form(t, mag, f_nom)})
    OUT["P4_waveform_form_detector"] = rows


# --------------------------------------------------------------------------------------------- P5 prerequisite envelope
def p5_envelope():
    """Smallest sampling rate each algorithm accepts, and the shortest recording, as functions of nominal frequency."""
    rows = []
    for f in (1.0, 25.0, 50.0, 60.0, 400.0, 1000.0):
        rows.append({
            "nominal_hz": f,
            "rms_min_fs_hz": MIN_SAMPLES_PER_CYCLE * f,
            "overcurrent_min_fs_hz": OVERCURRENT_MIN_SAMPLES_PER_CYCLE * f,
            "phasor_min_fs_hz": PHASOR_MIN_SAMPLES_PER_CYCLE * f,
            "window_s": 1.0 / f,
            "min_recording_s_rms": round(1.0 / f, 6),
        })
    OUT["P5_prerequisite_envelope"] = rows
    OUT["P5_constants"] = {
        "RMS MIN_SAMPLES_PER_CYCLE": MIN_SAMPLES_PER_CYCLE, "OVERCURRENT_MIN_SAMPLES_PER_CYCLE": OVERCURRENT_MIN_SAMPLES_PER_CYCLE,
        "PHASOR_MIN_SAMPLES_PER_CYCLE": PHASOR_MIN_SAMPLES_PER_CYCLE,
    }
    # a 5 kHz recording against each nominal frequency
    rms = []
    for f in (50.0, 60.0, 400.0, 1000.0):
        t, x = signal(f, 5000.0, 0.2)
        try:
            rms_ok = bool(np.isfinite(evaluate_rms(t, x, f)).any())
        except Exception as exc:                                        # noqa: BLE001
            rms_ok = f"raised {type(exc).__name__}"
        rms.append({"nominal_hz": f, "fs_hz": 5000.0, "samples_per_cycle": round(5000.0 / f, 3),
                    "rms_prerequisite_passes": (5000.0 / f) >= MIN_SAMPLES_PER_CYCLE, "evaluate_rms_returns_values": rms_ok})
    OUT["P5b_5khz_recording"] = rms


# --------------------------------------------------------------------------------------------- P6 invalid frequency into the raw functions
def p6_invalid():
    t, x = signal(50.0, 5000.0, 0.2)
    rows = []
    for bad in (0.0, -50.0, float("nan"), float("inf")):
        entry = {"nominal_hz": repr(bad)}
        for name, fn in (
            ("evaluate_rms", lambda: evaluate_rms(t, x, bad)),
            ("estimate_phasor", lambda: estimate_phasor(t, x, 0.15, bad)),
            ("estimate_trailing_rms_at_time", lambda: estimate_trailing_rms_at_time(t, x, 0.15, bad)),
            ("classify_waveform_form", lambda: classify_waveform_form(t, x, bad)),
        ):
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    r = fn()
                entry[name] = "returns " + (type(r).__name__ if not isinstance(r, str) else r)
            except Exception as exc:                                    # noqa: BLE001
                entry[name] = f"raises {type(exc).__name__}"
        rows.append(entry)
    OUT["P6_raw_functions_with_invalid_frequency"] = rows


# --------------------------------------------------------------------------------------------- P7 waveform evidence window
def p7_evidence_window():
    """auto_base_service passes no frequency to extract_waveform_evidence (default 50 Hz): RMS window = round(fs/50) samples."""
    rows = []
    for fs in (4800.0, 5000.0, 4096.0):
        for f_sig in (50.0, 60.0):
            win = max(2, round(fs / 50.0))
            t, x = signal(f_sig, fs, 0.5)
            sq = np.convolve(x * x, np.ones(win) / win, mode="valid")
            rms = np.sqrt(sq)
            rows.append({"fs_hz": fs, "signal_hz": f_sig, "window_samples_used": win, "window_cycles": round(win * f_sig / fs, 4),
                         "mean_error_pct": round(float((np.mean(rms) / EXPECTED_RMS - 1) * 100), 4),
                         "ripple_pp_pct": round(float((rms.max() - rms.min()) / EXPECTED_RMS * 100), 4)})
    OUT["P7_waveform_evidence_window_fixed_at_50hz"] = rows


# --------------------------------------------------------------------------------------------- P8 detector across the NF-1 range
def p8_detector_range():
    """A frequency the NF-1 validity range accepts is not necessarily one every algorithm supports: the detector slice is capped
    at MAX_SLICE_SECONDS while it needs MIN_CYCLES_FOR_DETECTION cycles."""
    rows = []
    for f in (1.0, 2.0, 3.0, 5.0, 16.7, 50.0, 400.0, 1000.0):
        fs = max(2000.0, 40.0 * f)
        t = np.arange(int(fs * max(10.0, 30.0 / f)) + 1) / fs
        x = AMP * np.cos(2 * np.pi * f * t)
        rows.append({"nominal_hz": f, "fs_hz": fs, "duration_s": round(float(t[-1]), 1), "verdict": classify_waveform_form(t, x, f)})
    OUT["P8_detector_verdict_across_nf1_range"] = rows


if __name__ == "__main__":
    for fn in (p1_rms, p2_phasor, p3_power, p4_detector, p5_envelope, p6_invalid, p7_evidence_window, p8_detector_range):
        fn()
    print(json.dumps(OUT, indent=1, default=str))
