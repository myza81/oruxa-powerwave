"""Generator for the NF-3D pre-migration characterisation baseline (phasor family, overcurrent).

Runs every scenario of `tests/nf3d_baseline_scenarios.py` and freezes the outcome in `nf3d_pre_migration_baseline.json`.

The committed file was generated ONCE against the unmodified NF-3C tree (`446b566`), before NF-3D changed any
production file. Never regenerate it to make a failing test pass: a difference means a consumer's behaviour changed, and a
later slice that changes one deliberately updates only the affected entries in a reviewed commit that says why.

    cd backend
    python tests/fixtures/nf3d_baselines/generate_nf3d_baseline.py                  # (re)write the committed baseline
    python tests/fixtures/nf3d_baselines/generate_nf3d_baseline.py --out FILE.json   # write elsewhere (before/after comparison)

It refuses to write the committed baseline if anything under `backend/app` differs from HEAD, runs the whole scenario set
twice and refuses to write unless both runs are identical, and records the HEAD SHA and interpreter/library versions.
"""

from __future__ import annotations

import argparse
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
from tests import nf3d_baseline_scenarios as scenarios  # noqa: E402

BASELINE_PATH = HERE / "nf3d_pre_migration_baseline.json"


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
            return scenarios.run_all(client)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="write here instead of the committed baseline (no clean-tree requirement)")
    args = parser.parse_args()
    if args.out is None:
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
        "purpose": "Frozen pre-NF-3D consumer behaviour on the NF-3C tip (characterisation, defects included)",
        "baseline_git_sha": git("rev-parse", "HEAD"),
        "python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform(),
        "scenario_runner": "backend/tests/nf3d_baseline_scenarios.py",
        "outcomes": first,
    }
    path = Path(args.out) if args.out else BASELINE_PATH
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, sort_keys=True, indent=1)
        handle.write("\n")
    print(f"wrote {path} at {document['baseline_git_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
