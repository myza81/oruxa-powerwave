"""Generator for the frozen COMTRADE nominal-frequency baseline (RMS display R1A).

Runs every scenario of `tests/comtrade_frequency_scenarios.py` against the PRISTINE pre-R1A production tree and
freezes the outcome in `comtrade_frequency_baseline.json`.

Run exactly once, before any production change, and never against a modified parser to make a failing test pass:

    cd backend
    python tests/fixtures/comtrade_frequency/generate_comtrade_frequency_baseline.py

It refuses to run if anything under `backend/app` differs from HEAD, runs the whole scenario set twice and refuses to
write unless both runs are identical, and records the HEAD SHA and interpreter/library versions.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests import comtrade_frequency_scenarios as scenarios  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=BACKEND, check=True, capture_output=True, text=True).stdout.strip()


def run_once() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            environment="development", storage_type="local", storage_path=tmp,
            cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
            git_sha="local", version="local",
        )
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            api = scenarios.run_api_scenarios(client)
    return {"parser": scenarios.run_parser_scenarios(), "fixtures": scenarios.run_fixture_sweep(), "api": api}


def main() -> int:
    dirty = git("status", "--porcelain", "--", "app")
    if dirty:
        print("REFUSING: production code under backend/app differs from HEAD:\n" + dirty, file=sys.stderr)
        return 2
    first, second = run_once(), run_once()
    if json.dumps(first, sort_keys=True) != json.dumps(second, sort_keys=True):
        print("REFUSING: two consecutive runs differ -- the scenarios are not deterministic.", file=sys.stderr)
        return 3
    document = {
        "schema": 1,
        "purpose": "Frozen pre-R1A COMTRADE nominal-frequency parser, provenance and import behaviour",
        "baseline_git_sha": git("rev-parse", "HEAD"),
        "python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform(),
        "scenario_runner": "backend/tests/comtrade_frequency_scenarios.py",
        "scenario_count": len(first["parser"]) + len(first["fixtures"]) + len(first["api"]),
        "outcomes": first,
    }
    with open(scenarios.BASELINE_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, sort_keys=True, indent=1)
        handle.write("\n")
    print(f"wrote {document['scenario_count']} scenario outcomes at baseline {document['baseline_git_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
