"""Reproducible performance-baseline benchmark runner (Pre-Advanced
Foundation Slice F2).

Standalone script, NOT a pytest test module (so it is never
auto-collected by `pytest tests/` -- see
`../test_performance_baseline.py` for the small, fast correctness tests
that DO run as part of normal regression). Deliberately outside the
pytest process for two reasons:

1. **Peak-memory measurement needs process isolation.** `mem_probe.
   peak_bytes()` reports a monotonic "high-water mark since process
   start" -- meaningful only when exactly one operation ran in that
   process. Fixture GENERATION (building a large synthetic waveform
   array in memory before writing it to disk) and IMPORT/PARSE are
   therefore each run in their OWN fresh subprocess, so neither
   contaminates the other's peak-memory number, and so running this
   script twice for two different scenarios in the same pytest session
   can never contaminate either scenario's number either.
2. **A 50-100 MB benchmark has no place in the default `pytest tests/`
   run** -- this script is the explicit, separately-invoked command;
   see `docs/development/PERFORMANCE_BASELINE.md` for the exact
   reproduction command and its output.

Usage (from `backend/`, matching this repo's existing test-invocation
convention):

    python tests/perf/baseline_runner.py run --scenario medium_comtrade
    python tests/perf/baseline_runner.py run --scenario large_comtrade
    python tests/perf/baseline_runner.py run --scenario csv_medium
    python tests/perf/baseline_runner.py run --scenario all

`run` is the one command a developer needs; `gen-comtrade`/`gen-csv`/
`measure-comtrade`/`measure-csv` are the internal phases it shells out
to (each printing one JSON object to stdout and nothing else, so `run`
can parse a child's output) -- also directly callable for debugging one
phase in isolation.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_comtrade import generate_comtrade_fixture  # noqa: E402
from synthetic_csv import generate_csv_fixture  # noqa: E402

_BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_DIR))

SCENARIOS: dict[str, dict] = {
    "medium_comtrade": dict(
        kind="comtrade", n_analog=40, n_digital=16, sample_rate_hz=10_000.0, target_mb=15,
        label="Scenario A -- medium COMTRADE recording",
    ),
    "large_comtrade": dict(
        kind="comtrade", n_analog=64, n_digital=32, sample_rate_hz=20_000.0, target_mb=75,
        label="Scenario B -- large COMTRADE recording",
    ),
    "csv_medium": dict(
        kind="csv", n_channels=20, sample_rate_hz=5_000.0, target_mb=12,
        label="Scenario C -- medium CSV recording",
    ),
}

# Generous headroom above every scenario's own target size so the
# benchmark never trips the application's own upload-size guardrail
# (DEFAULT_MAX_EVENT_UPLOAD_SIZE_MB=100) -- this is a benchmark harness
# setting, never a change to the application's own default.
_MAX_UPLOAD_MB = 300

# A reduced/"visible-range" waveform request, for the playback-relevance
# question -- an arbitrary but fixed 2-second window near the start of
# every scenario's recording (every scenario's own duration comfortably
# exceeds 2 seconds -- see docs/development/PERFORMANCE_BASELINE.md).
_REDUCED_WINDOW_SECONDS = 2.0


def _print_json(obj: dict) -> None:
    print(json.dumps(obj))


# ---- generation phases ------------------------------------------------


def _cmd_gen_comtrade(args: argparse.Namespace) -> None:
    info = generate_comtrade_fixture(
        Path(args.out_dir),
        n_analog=args.n_analog,
        n_digital=args.n_digital,
        sample_rate_hz=args.sample_rate_hz,
        target_size_bytes=int(args.target_mb * 1024 * 1024),
    )
    _print_json({
        "cfg_path": str(info.cfg_path),
        "dat_path": str(info.dat_path),
        "n_analog": info.n_analog,
        "n_digital": info.n_digital,
        "sample_rate_hz": info.sample_rate_hz,
        "n_samples": info.n_samples,
        "duration_seconds": info.duration_seconds,
        "cfg_size_bytes": info.cfg_size_bytes,
        "dat_size_bytes": info.dat_size_bytes,
        "total_size_bytes": info.total_size_bytes,
        "row_size_bytes": info.row_size_bytes,
        "analog_channel_names": info.analog_channel_names,
    })


def _cmd_gen_csv(args: argparse.Namespace) -> None:
    info = generate_csv_fixture(
        Path(args.out_dir),
        n_channels=args.n_channels,
        sample_rate_hz=args.sample_rate_hz,
        target_size_bytes=int(args.target_mb * 1024 * 1024),
    )
    _print_json({
        "csv_path": str(info.csv_path),
        "n_channels": info.n_channels,
        "sample_rate_hz": info.sample_rate_hz,
        "n_rows": info.n_rows,
        "duration_seconds": info.duration_seconds,
        "size_bytes": info.size_bytes,
    })


# ---- measurement phases ------------------------------------------------


def _build_test_client():
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    tmp_storage = tempfile.mkdtemp(prefix="oruxa-perfbaseline-storage-")
    settings = Settings(
        environment="development",
        storage_type="local",
        storage_path=tmp_storage,
        cors_origins=("http://localhost:8101",),
        database_url=None,
        max_event_upload_size_mb=_MAX_UPLOAD_MB,
        git_sha="perf-baseline",
        version="perf-baseline",
    )
    app = create_app(settings)
    return TestClient(app)


def _time_get(client, url: str, **kwargs) -> tuple[float, "object"]:
    start = time.perf_counter()
    resp = client.get(url, **kwargs)
    elapsed = time.perf_counter() - start
    return elapsed, resp


def _waveform_metrics(client, workspace_id: str, source_id: str, channel_name: str, duration_seconds: float) -> dict:
    from mem_probe import peak_bytes  # noqa: E402  (sys.path already extended above)

    full_elapsed, full_resp = _time_get(
        client, f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform",
        params={"channel_name": channel_name},
    )
    assert full_resp.status_code == 200, f"Full-range waveform request failed: {full_resp.status_code} {full_resp.text[:500]}"
    full_body = full_resp.json()
    assert full_body["returned_point_count"] > 0, "Full-range waveform returned zero points"
    assert len(full_body["time"]) == full_body["returned_point_count"]
    assert len(full_body["values"]) == full_body["returned_point_count"]

    window = min(_REDUCED_WINDOW_SECONDS, duration_seconds / 2.0) or duration_seconds
    reduced_elapsed, reduced_resp = _time_get(
        client, f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform",
        params={"channel_name": channel_name, "start_time": 0.0, "end_time": window},
    )
    assert reduced_resp.status_code == 200, f"Reduced-range waveform request failed: {reduced_resp.status_code}"
    reduced_body = reduced_resp.json()
    assert reduced_body["returned_point_count"] > 0, "Reduced-range waveform returned zero points"

    return {
        "peak_memory_bytes_after_waveform": peak_bytes(),
        "full_range": {
            "requested_span_seconds": duration_seconds,
            "wall_clock_seconds": full_elapsed,
            "payload_bytes": len(full_resp.content),
            "returned_point_count": full_body["returned_point_count"],
            "original_sample_count": full_body["original_sample_count"],
            "representation": full_body["representation"],
        },
        "reduced_range": {
            "requested_span_seconds": window,
            "wall_clock_seconds": reduced_elapsed,
            "payload_bytes": len(reduced_resp.content),
            "returned_point_count": reduced_body["returned_point_count"],
            "original_sample_count": reduced_body["original_sample_count"],
            "representation": reduced_body["representation"],
        },
    }


def _cmd_measure_comtrade(args: argparse.Namespace) -> None:
    from mem_probe import memory_metric_label, peak_bytes  # noqa: E402

    workspace_id = "ws-perf-baseline"
    cfg_bytes = Path(args.cfg).read_bytes()
    dat_bytes = Path(args.dat).read_bytes()

    client = _build_test_client()
    with client:
        start = time.perf_counter()
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/sources",
            files={
                "cfg_file": ("event.cfg", io.BytesIO(cfg_bytes), "application/octet-stream"),
                "dat_file": ("event.dat", io.BytesIO(dat_bytes), "application/octet-stream"),
            },
        )
        import_elapsed = time.perf_counter() - start
        assert resp.status_code == 201, f"COMTRADE import failed: {resp.status_code} {resp.text[:500]}"
        body = resp.json()
        assert body["analog_channel_count"] == args.expected_n_analog, (
            f"Expected {args.expected_n_analog} analog channels, got {body['analog_channel_count']}"
        )
        assert body["sample_count"] == args.expected_n_samples, (
            f"Expected {args.expected_n_samples} samples, got {body['sample_count']}"
        )
        peak_after_import = peak_bytes()

        source_id = body["source_id"]
        channels_resp = client.get(f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/channels")
        assert channels_resp.status_code == 200
        channels_body = channels_resp.json()
        analog_channels = channels_body["analog_channels"]
        assert len(analog_channels) == args.expected_n_analog
        channel_name = analog_channels[0]["name"]

        waveform_metrics = _waveform_metrics(
            client, workspace_id, source_id, channel_name, body["duration_seconds"]
        )

    _print_json({
        "format": "comtrade",
        "memory_metric": memory_metric_label(),
        "import_wall_clock_seconds": import_elapsed,
        "peak_memory_bytes_after_import": peak_after_import,
        "analog_channel_count": body["analog_channel_count"],
        "digital_channel_count": body["digital_channel_count"],
        "sample_count": body["sample_count"],
        "duration_seconds": body["duration_seconds"],
        "channel_used": channel_name,
        **waveform_metrics,
    })


def _cmd_measure_csv(args: argparse.Namespace) -> None:
    from mem_probe import memory_metric_label, peak_bytes  # noqa: E402

    workspace_id = "ws-perf-baseline-csv"
    csv_bytes = Path(args.csv).read_bytes()
    n_channels = args.n_channels

    client = _build_test_client()
    with client:
        start = time.perf_counter()
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/preparation-sources",
            files={"csv_file": ("event.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        upload_elapsed = time.perf_counter() - start
        assert resp.status_code == 201, f"CSV upload failed: {resp.status_code} {resp.text[:500]}"
        prep_source_id = resp.json()["source_id"]

        start = time.perf_counter()
        role_resp = client.put(
            f"/api/v1/workspaces/{workspace_id}/preparation-sources/{prep_source_id}/working/columns/0/role",
            json={"role": "time_axis"},
        )
        assert role_resp.status_code == 200, f"Time-axis role assignment failed: {role_resp.text[:300]}"
        for col in range(1, n_channels + 1):
            role_resp = client.put(
                f"/api/v1/workspaces/{workspace_id}/preparation-sources/{prep_source_id}/working/columns/{col}/role",
                json={"role": "waveform"},
            )
            assert role_resp.status_code == 200, f"Waveform role assignment failed for column {col}: {role_resp.text[:300]}"
        time_axis_resp = client.put(
            f"/api/v1/workspaces/{workspace_id}/preparation-sources/{prep_source_id}/working/time-axis",
            json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
        )
        assert time_axis_resp.status_code == 200, f"Time-axis configuration failed: {time_axis_resp.text[:300]}"
        configure_elapsed = time.perf_counter() - start

        start = time.perf_counter()
        convert_resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/preparation-sources/{prep_source_id}/convert"
        )
        convert_elapsed = time.perf_counter() - start
        assert convert_resp.status_code in (200, 201), f"CSV conversion failed: {convert_resp.status_code} {convert_resp.text[:500]}"
        converted = convert_resp.json()
        source_id = converted["source_id"]
        peak_after_import = peak_bytes()

        channels_resp = client.get(f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/channels")
        assert channels_resp.status_code == 200
        channels_body = channels_resp.json()
        analog_channels = channels_body["analog_channels"]
        assert len(analog_channels) == n_channels, (
            f"Expected {n_channels} converted analog channels, got {len(analog_channels)}"
        )
        channel_name = analog_channels[0]["name"]
        duration_seconds = channels_body["timebase"]["duration_seconds"]
        sample_count = channels_body["timebase"]["sample_count"]

        waveform_metrics = _waveform_metrics(
            client, workspace_id, source_id, channel_name, duration_seconds
        )

    _print_json({
        "format": "csv",
        "memory_metric": memory_metric_label(),
        "upload_wall_clock_seconds": upload_elapsed,
        "configure_wall_clock_seconds": configure_elapsed,
        "convert_wall_clock_seconds": convert_elapsed,
        "import_wall_clock_seconds": upload_elapsed + configure_elapsed + convert_elapsed,
        "peak_memory_bytes_after_import": peak_after_import,
        "analog_channel_count": len(analog_channels),
        "sample_count": sample_count,
        "duration_seconds": duration_seconds,
        "channel_used": channel_name,
        **waveform_metrics,
    })


# ---- orchestration -------------------------------------------------------


def _run_subprocess_json(argv: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *argv],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Subprocess {argv} failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    # The measured/generation commands print exactly one JSON object as
    # their last stdout line -- warnings/deprecation notices (if any)
    # land on stderr, never stdout, so this is never ambiguous.
    last_line = result.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


def _run_scenario(scenario_name: str, workdir: Path) -> dict:
    spec = SCENARIOS[scenario_name]
    scenario_dir = workdir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    if spec["kind"] == "comtrade":
        gen = _run_subprocess_json([
            "gen-comtrade", "--out-dir", str(scenario_dir),
            "--n-analog", str(spec["n_analog"]), "--n-digital", str(spec["n_digital"]),
            "--sample-rate-hz", str(spec["sample_rate_hz"]), "--target-mb", str(spec["target_mb"]),
        ])
        measured = _run_subprocess_json([
            "measure-comtrade", "--cfg", gen["cfg_path"], "--dat", gen["dat_path"],
            "--expected-n-analog", str(spec["n_analog"]), "--expected-n-samples", str(gen["n_samples"]),
        ])
        return {"scenario": scenario_name, "label": spec["label"], "generation": gen, "measurement": measured}

    if spec["kind"] == "csv":
        gen = _run_subprocess_json([
            "gen-csv", "--out-dir", str(scenario_dir),
            "--n-channels", str(spec["n_channels"]), "--sample-rate-hz", str(spec["sample_rate_hz"]),
            "--target-mb", str(spec["target_mb"]),
        ])
        measured = _run_subprocess_json([
            "measure-csv", "--csv", gen["csv_path"], "--n-channels", str(spec["n_channels"]),
        ])
        return {"scenario": scenario_name, "label": spec["label"], "generation": gen, "measurement": measured}

    raise ValueError(f"Unknown scenario kind: {spec['kind']!r}")


def _cmd_run(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="oruxa-perfbaseline-"))
    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    results = [_run_scenario(name, workdir) for name in names]
    _print_json({"workdir": str(workdir), "results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("gen-comtrade")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--n-analog", type=int, required=True)
    p.add_argument("--n-digital", type=int, required=True)
    p.add_argument("--sample-rate-hz", type=float, required=True)
    p.add_argument("--target-mb", type=float, required=True)
    p.set_defaults(func=_cmd_gen_comtrade)

    p = sub.add_parser("gen-csv")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--n-channels", type=int, required=True)
    p.add_argument("--sample-rate-hz", type=float, required=True)
    p.add_argument("--target-mb", type=float, required=True)
    p.set_defaults(func=_cmd_gen_csv)

    p = sub.add_parser("measure-comtrade")
    p.add_argument("--cfg", required=True)
    p.add_argument("--dat", required=True)
    p.add_argument("--expected-n-analog", type=int, required=True)
    p.add_argument("--expected-n-samples", type=int, required=True)
    p.set_defaults(func=_cmd_measure_comtrade)

    p = sub.add_parser("measure-csv")
    p.add_argument("--csv", required=True)
    p.add_argument("--n-channels", type=int, required=True)
    p.set_defaults(func=_cmd_measure_csv)

    p = sub.add_parser("run")
    p.add_argument("--scenario", required=True, choices=[*SCENARIOS.keys(), "all"])
    p.add_argument("--workdir", default=None)
    p.set_defaults(func=_cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
