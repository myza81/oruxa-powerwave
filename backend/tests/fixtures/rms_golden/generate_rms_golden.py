"""Generator for the frozen RMS golden vectors (RMS display R0 baseline).

PURPOSE
    Freeze the *current* numerical behaviour of
    `app.domain.calculated_channel.evaluate_rms` -- the single RMS
    mathematical authority -- before the R0 shared-authority extraction
    changes the code that composes it. The frozen inputs and outputs are
    committed; the parity test (`tests/test_rms_golden_vectors.py`) feeds the
    frozen inputs to the engine as it exists at test time and requires the
    frozen outputs back.

WHEN TO RUN
    Exactly once, on a pristine pre-R0 production tree. The script refuses to
    run when anything under `backend/app` differs from HEAD, and it records
    the HEAD SHA in the manifest. It must NEVER be re-run against a modified
    engine to make a failing parity test pass: a mismatch is a regression to
    report, not a baseline to refresh.

        cd backend
        python tests/fixtures/rms_golden/generate_rms_golden.py

OUTPUT (written next to this file)
    rms_golden_vectors.npz   inputs (`<case>__time`, `<case>__values`) and the
                             engine outputs (`<case>__out`) of every case.
    manifest.json            baseline SHA, interpreter/library versions, the
                             generation procedure, per-case parameters and
                             SHA-256 hashes of the raw bytes of every array.

Inputs are frozen into the .npz (not regenerated at test time) so that a
different libm (`np.sin`) on another platform cannot change the inputs.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.domain.calculated_channel import evaluate_rms  # noqa: E402

SEED = 20261124
SQRT2 = float(np.sqrt(2.0))


def sha256_bytes(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def uniform_time(fs: float, n: int, t0: float = 0.0) -> np.ndarray:
    return t0 + np.arange(n, dtype=np.float64) / fs


def sine(time: np.ndarray, f0: float, rms: float = 100.0) -> np.ndarray:
    return rms * SQRT2 * np.sin(2.0 * np.pi * f0 * time)


def build_cases() -> list[dict]:
    rng = np.random.default_rng(SEED)
    cases: list[dict] = []

    def add(name, description, time, values, nominal, **extra):
        cases.append({
            "name": name, "description": description, "time": np.asarray(time, dtype=np.float64),
            "values": values, "nominal_frequency_hz": float(nominal), **extra,
        })

    # -- steady sinusoids: 50/60 Hz at the four sampling rates the owner named --
    for f0 in (50.0, 60.0):
        for fs in (5000.0, 4096.0, 3200.0, 960.0):
            n = int(round(0.4 * fs))
            t = uniform_time(fs, n)
            add(f"sine_{int(f0)}hz_{int(fs)}", f"100 V RMS sine {f0:g} Hz, uniform {fs:g} Hz, nominal {f0:g} Hz",
                t, sine(t, f0), f0, fs_hz=fs, f0_hz=f0)

    t = uniform_time(5000.0, 2000)
    add("sine_60hz_nominal50_5000", "60 Hz sine evaluated with nominal 50 Hz (mismatch)", t, sine(t, 60.0), 50.0,
        fs_hz=5000.0, f0_hz=60.0)
    add("sine_50hz_nominal60_5000", "50 Hz sine evaluated with nominal 60 Hz (mismatch)", t, sine(t, 50.0), 60.0,
        fs_hz=5000.0, f0_hz=50.0)

    # -- irregular / multi-rate spacing (two-pointer path) --
    dt = (1.0 / 5000.0) * (1.0 + 0.2 * rng.uniform(-1.0, 1.0, 2000))
    t = np.cumsum(dt) - dt[0]
    add("irregular_jitter_50hz", "50 Hz sine on randomly jittered (+/-20 %) monotonic timestamps", t, sine(t, 50.0), 50.0,
        fs_hz=5000.0, f0_hz=50.0)

    seg = [(4000.0, 600), (1000.0, 200), (4000.0, 600)]
    parts, cursor = [], 0.0
    for fs, n in seg:
        parts.append(cursor + np.arange(n, dtype=np.float64) / fs)
        cursor = parts[-1][-1] + 1.0 / fs
    t = np.concatenate(parts)
    add("multirate_50hz", "COMTRADE-style multi-rate record 4000/1000/4000 Hz, 50 Hz sine", t, sine(t, 50.0), 50.0,
        fs_hz=None, f0_hz=50.0)

    t = uniform_time(5000.0, 2000) + 1e-12 * rng.standard_normal(2000)
    t = np.maximum.accumulate(t)
    add("uniform_with_tiny_jitter", "Uniform spacing perturbed by 1e-12 s (exercises the uniformity tolerance)", t,
        sine(t, 50.0), 50.0, fs_hz=5000.0, f0_hz=50.0)

    # -- waveform shapes --
    t = uniform_time(5000.0, 2000)
    add("harmonics_50hz_5000", "50 Hz fundamental + 30 % 3rd + 20 % 5th harmonic", t,
        100.0 * SQRT2 * (np.sin(2 * np.pi * 50 * t) + 0.3 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 250 * t)),
        50.0, fs_hz=5000.0, f0_hz=50.0)
    add("decaying_dc_50hz_5000", "50 Hz sine with a 60 A decaying DC offset (tau 50 ms)", t,
        sine(t, 50.0) + 60.0 * np.exp(-t / 0.05), 50.0, fs_hz=5000.0, f0_hz=50.0)
    amp = np.where(t < 0.15, 1.0, np.where(t < 0.30, 4.0, 1.0))
    add("fault_step_50hz_5000", "Amplitude 100 A -> 400 A -> 100 A (fault inception and clearing)", t,
        amp * sine(t, 50.0), 50.0, fs_hz=5000.0, f0_hz=50.0)
    add("constant_dc_5000", "Constant 110 V DC", t, np.full(2000, 110.0), 50.0, fs_hz=5000.0)

    # -- non-finite handling --
    v = sine(t, 50.0).copy()
    v[:30] = np.nan
    add("leading_nan_50hz_5000", "First 30 samples NaN (leading non-finite interval)", t, v, 50.0, fs_hz=5000.0)
    v = sine(t, 50.0).copy()
    v[[300, 1100]] = np.nan
    add("window_nan_50hz_5000", "NaN at samples 300 and 1100 (NaN-containing windows)", t, v, 50.0, fs_hz=5000.0)
    add("all_nan_5000", "Every sample NaN", t, np.full(2000, np.nan), 50.0, fs_hz=5000.0)
    v = sine(t, 50.0).copy()
    v[100] = np.inf
    v[900] = -np.inf
    add("inf_in_window_5000", "+inf and -inf samples (non-finite, not NaN)", t, v, 50.0, fs_hz=5000.0)

    # -- length / density boundaries (the engine itself has no gate; the gates live in the service) --
    t = uniform_time(5000.0, 60)
    add("short_recording_5000", "60 samples = 12 ms, shorter than one 20 ms window", t, sine(t, 50.0), 50.0, fs_hz=5000.0)
    t = uniform_time(150.0, 75)
    add("sparse_150hz", "150 Hz sampling = 3 samples per cycle at 50 Hz", t, sine(t, 50.0), 50.0, fs_hz=150.0)
    add("single_sample", "One sample", np.array([0.0]), np.array([5.0]), 50.0, fs_hz=None)
    add("empty_input", "Zero samples", np.array([], dtype=np.float64), np.array([], dtype=np.float64), 50.0, fs_hz=None)

    # -- numerical-form / time-origin variants --
    t = uniform_time(5000.0, 2000)
    add("float32_values_5000", "float32 sample array (dtype handling)", t, sine(t, 50.0).astype(np.float32), 50.0,
        fs_hz=5000.0)
    t = uniform_time(5000.0, 2000, t0=12.34)
    add("time_offset_5000", "Time axis starting at 12.34 s", t, sine(t, 50.0), 50.0, fs_hz=5000.0)
    t = uniform_time(5000.0, 2000, t0=-0.1)
    add("time_negative_start_5000", "Time axis starting at -0.1 s (pre-trigger)", t, sine(t, 50.0), 50.0, fs_hz=5000.0)
    t = uniform_time(100.0, 250)
    add("nominal_1hz_100", "1 Hz sine, nominal 1 Hz (lower validity bound), 100 Hz sampling", t, sine(t, 1.0), 1.0,
        fs_hz=100.0, f0_hz=1.0)
    t = uniform_time(20000.0, 400)
    add("nominal_1000hz_20000", "1000 Hz sine, nominal 1000 Hz (upper validity bound), 20 kHz sampling", t,
        sine(t, 1000.0), 1000.0, fs_hz=20000.0, f0_hz=1000.0)

    # -- inputs consumed by the SERVICE-level baseline (see tests/rms_baseline_scenarios.py) --
    t = uniform_time(5000.0, 2500)
    add("svc_instantaneous", "service input: 1.0 pu sine 50 Hz, 0.5 s @ 5 kHz", t, np.sin(2 * np.pi * 50.0 * t), 50.0,
        fs_hz=5000.0, service_input=True)
    v = np.sin(2 * np.pi * 50.0 * t)
    v[[200, 1200]] = np.nan
    add("svc_instantaneous_nan", "service input: svc_instantaneous with NaN at samples 200 and 1200", t, v, 50.0,
        fs_hz=5000.0, service_input=True)
    add("svc_magnitude_like", "service input: 100 + 2 sin(2 pi 3 t) (magnitude-like)", t,
        100.0 + 2.0 * np.sin(2 * np.pi * 3.0 * t), 50.0, fs_hz=5000.0, service_input=True)
    t2 = uniform_time(2000.0, 3000)
    add("svc_uncertain", "service input: 110 + 5.5 sin 50 Hz at 2 kHz, 1.5 s", t2,
        110.0 + 5.5 * np.sin(2 * np.pi * 50.0 * t2), 50.0, fs_hz=2000.0, service_input=True)
    steps = np.where(t2 < 0.5, 100.0, np.where(t2 < 1.0, 400.0, 100.0)) + 0.5 * rng.standard_normal(3000)
    add("svc_rms_shaped", "service input: noisy 100/400/100 step (RMS-shaped)", t2, steps, 50.0, fs_hz=2000.0,
        service_input=True)
    t3 = uniform_time(5000.0, 50)
    add("svc_short_instantaneous", "service input: 10 ms sine @ 5 kHz (shorter than one window)", t3,
        np.sin(2 * np.pi * 50.0 * t3), 50.0, fs_hz=5000.0, service_input=True)
    t4 = uniform_time(150.0, 75)
    add("svc_sparse_instantaneous", "service input: 0.5 s sine @ 150 Hz (3 samples/cycle)", t4,
        np.sin(2 * np.pi * 50.0 * t4), 50.0, fs_hz=150.0, service_input=True)
    t5 = uniform_time(150.0, 2)
    add("svc_short_and_sparse", "service input: two samples @ 150 Hz (short AND sparse)", t5,
        np.sin(2 * np.pi * 50.0 * t5), 50.0, fs_hz=150.0, service_input=True)
    return cases


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=BACKEND, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    dirty = git("status", "--porcelain", "--", "app")
    if dirty:
        print("REFUSING: production code under backend/app differs from HEAD:\n" + dirty, file=sys.stderr)
        return 2
    cases = build_cases()
    arrays: dict[str, np.ndarray] = {}
    manifest_cases = []
    for case in cases:
        time, values = case["time"], np.asarray(case["values"])
        out = evaluate_rms(time, values, case["nominal_frequency_hz"])
        arrays[f"{case['name']}__time"] = time
        arrays[f"{case['name']}__values"] = values
        arrays[f"{case['name']}__out"] = out
        manifest_cases.append({
            "name": case["name"],
            "description": case["description"],
            "nominal_frequency_hz": case["nominal_frequency_hz"],
            "fs_hz": case.get("fs_hz"),
            "f0_hz": case.get("f0_hz"),
            "service_input": bool(case.get("service_input", False)),
            "n": int(time.shape[0]),
            "time_dtype": str(time.dtype), "values_dtype": str(values.dtype), "out_dtype": str(out.dtype),
            "time_sha256": sha256_bytes(time), "values_sha256": sha256_bytes(values), "out_sha256": sha256_bytes(out),
            "out_nan_count": int(np.isnan(out).sum()),
            "out_first_finite_index": int(np.argmax(np.isfinite(out))) if np.isfinite(out).any() else None,
        })
    np.savez_compressed(HERE / "rms_golden_vectors.npz", **arrays)
    manifest = {
        "schema": 1,
        "purpose": "Frozen pre-R0 evaluate_rms inputs/outputs for the RMS display R0 shared-authority extraction",
        "baseline_git_sha": git("rev-parse", "HEAD"),
        "baseline_git_branch_note": "pre-R0 tree; backend/app verified clean against HEAD at generation time",
        "engine": "app.domain.calculated_channel.evaluate_rms",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": platform.platform(),
        "byte_order": sys.byteorder,
        "generator": "backend/tests/fixtures/rms_golden/generate_rms_golden.py",
        "rng_seed": SEED,
        "generation_procedure": (
            "build_cases() constructs deterministic inputs; evaluate_rms(time, values, nominal_frequency_hz) is "
            "called once per case on the pristine pre-R0 tree; inputs and outputs are stored in the .npz "
            "(np.savez_compressed) and SHA-256 hashes of the raw little-endian array bytes are recorded here."
        ),
        "hash_definition": "sha256(np.ascontiguousarray(array).tobytes())",
        "cases": manifest_cases,
    }
    with open(HERE / "manifest.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"wrote {len(cases)} cases at baseline {manifest['baseline_git_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
