"""Generator for `nf3d_approved_changes.json`: every difference NF-3D makes to a frozen baseline, as reviewable data.

The historical baselines are never edited. For each baseline this runs the scenarios on the CURRENT tree, diffs the result against
"history + NF-3C approved changes" and records every difference as `{path, before, after, kind}`. A difference that falls in no
approved KIND makes the generator refuse (exit 2): an unexplained change is never written down as approved.

KINDS (the NF-3D owner decisions O-5, O-6 and the Phase B/C requirements)
  provenance_added       a new `nominal_frequency_origin` / `_revision` / `_sources` field (O-6); additive, never a changed value
  unusable_refusal       a recording whose declared frequency is unusable (0, NaN, +/-inf, negative, outside 1-1000 Hz) is refused with the
                         typed `invalid_reference_frequency` BEFORE any kernel: the legacy HTTP 500, the wrongly-reported
                         `waveform_form_not_eligible` / `reference_frequency_conflict`, and the echoed unusable value all go (O-5)
  sampling_unsupported   a VALID nominal frequency the recording's sampling cannot support is reported as `insufficient_sampling_density`
                         (the existing reason, derived from the estimator's own minimum samples per cycle), not `waveform_form_not_eligible`

    cd backend
    python tests/fixtures/nf3d_baselines/generate_nf3d_approved_changes.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests import nf3b_baseline_scenarios as nf3b_scenarios  # noqa: E402
from tests import nf3c_approved_changes as approved  # noqa: E402
from tests import nf3d_baseline_scenarios as nf3d_scenarios  # noqa: E402
from tests.nf3d_diff_tools import ABSENT, structured_diff  # noqa: E402

MANIFEST = HERE / "nf3d_approved_changes.json"
NF3D, NF3B = "nf3d_pre_migration_baseline", "nf3b_frozen_baselines"
PROVENANCE_KEYS = ("nominal_frequency_origin", "nominal_frequency_revision", "nominal_frequency_sources")
UNUSABLE_RECORDINGS = {"declared_zero", "declared_nan", "declared_inf", "declared_negative_50", "declared_0_5", "declared_1001"}
SAMPLING_SCENARIO = "r50_override_1000_unsupported_by_sampling"


def _run(module) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            environment="development", storage_type="local", storage_path=tmp, cors_origins=("http://localhost:8101",),
            database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
        )
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            return module.run_all(client)


def scenario_of(baseline: str, path: tuple) -> str | None:
    """The scenario (recording / override / two-recording case) a path belongs to."""
    if baseline == NF3D:
        return path[1] if len(path) > 1 else None
    if len(path) > 1 and path[0] in ("http", "in_process"):
        return path[1]
    return None


def classify(baseline: str, path: tuple, before, after) -> str | None:
    leaf, scenario = path[-1], scenario_of(baseline, path)
    if leaf in PROVENANCE_KEYS and before == ABSENT:
        return "provenance_added"
    if scenario == SAMPLING_SCENARIO:
        return "sampling_unsupported"
    if scenario in UNUSABLE_RECORDINGS or scenario == "one_unusable":
        return "unusable_refusal"
    return None


def entries_for(baseline: str, expected: dict, current: dict) -> tuple[list[dict], list[str]]:
    entries, unexplained = [], []
    for path, before, after in structured_diff(expected, current):
        kind = classify(baseline, path, before, after)
        if kind is None:
            unexplained.append(f"{baseline}: {list(path)!r}: {before!r} -> {after!r}")
            continue
        entries.append({"path": list(path), "before": before, "after": after, "kind": kind})
    return entries, unexplained


def main() -> int:
    nf3d_doc = json.loads((BACKEND / "tests/fixtures/nf3d_baselines/nf3d_pre_migration_baseline.json").read_text(encoding="utf-8"))
    nf3b_doc = json.loads((BACKEND / "tests/fixtures/nf3b_baselines/nf3b_frozen_baselines.json").read_text(encoding="utf-8"))
    runs = {NF3D: (nf3d_doc, nf3d_scenarios), NF3B: (nf3b_doc, nf3b_scenarios)}
    changes, problems = {}, []
    for baseline, (doc, module) in runs.items():
        first, second = _run(module), _run(module)
        if json.dumps(first, sort_keys=True) != json.dumps(second, sort_keys=True):
            print(f"REFUSING: two consecutive {baseline} runs differ -- not deterministic.", file=sys.stderr)
            return 3
        expected = approved.apply_approved(doc, baseline, include_nf3d=False)
        entries, unexplained = entries_for(baseline, expected, first)
        changes[baseline] = entries
        problems += unexplained
    if problems:
        print("REFUSING: differences that fall in no approved kind:", *problems[:40], sep="\n  ", file=sys.stderr)
        print(f"  ({len(problems)} in total)", file=sys.stderr)
        return 2
    document = {
        "schema": 1,
        "purpose": "Every behaviour difference NF-3D makes to the NF-3B and NF-3D frozen baselines (history + NF-3C approved changes + these = current)",
        "kinds": ["provenance_added", "unusable_refusal", "sampling_unsupported"],
        "changes": changes,
    }
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, sort_keys=True, indent=1)
        handle.write("\n")
    print(f"wrote {MANIFEST}: " + ", ".join(f"{k}={len(v)}" for k, v in changes.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
