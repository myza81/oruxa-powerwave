"""Generate `nf3f_approved_changes.json`: the explicitly approved NF-3F changes to two historical baselines (not a test module).

NF-3F (owner decision O-2, 2026-11-28) migrates the single- and three-phase power channels onto the central nominal-frequency authority.
Two frozen records contain power channels: the NF-3B HTTP consumer baseline and the NF-3E Phase A power group. Both stay historical and are
never edited. This script computes the structured difference between "history + earlier approved changes" and the code under test, REFUSES
any difference that is not one of the kinds below, and writes the rest as reviewable entries (path, before, after, kind).

Kinds (everything else aborts generation):

* `power_provenance_added` -- the three additive keys of a recording-following channel (`nominal_frequency_basis`,
  `nominal_frequency_origin`, `nominal_frequency_revision`), values taken from the recording's own record in the baseline.
* `power_frequency_effective` -- the stored `nominal_frequency_hz` now equals the recording's effective frequency (60.0 on the 60 Hz recording)
  instead of the fixed 50.0.
* `power_values_corrected_for_recording_frequency` -- the value statistics of a power channel on a recording whose effective frequency is not
  50 Hz (the O-2 numerical correction). The corrected numbers are verified independently in `test_nf3f_power_channels.py` (closed form and the
  unmodified kernel called directly with the recording's frequency).
* `power_refused_unusable_frequency` -- a recording with no usable nominal frequency no longer yields a power channel: 400
  `invalid_nominal_frequency` (the NF-3A matrix row for C-11..C-13).

Run from `backend/`:  python tests/fixtures/nf3f_baselines/generate_nf3f_approved_changes.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests import nf3b_baseline_scenarios as nf3b_scenarios  # noqa: E402
from tests import nf3c_approved_changes as nf3c  # noqa: E402
from tests import nf3e_approved_changes as nf3e  # noqa: E402
from tests import nf3e_baseline_scenarios as nf3e_scenarios  # noqa: E402
from tests.nf3d_diff_tools import ABSENT, structured_diff  # noqa: E402

OUT = Path(__file__).with_name("nf3f_approved_changes.json")
PROVENANCE_KEYS = {"nominal_frequency_basis", "nominal_frequency_origin", "nominal_frequency_revision"}
UNUSABLE_RECORDINGS = {"declared_zero", "declared_nan", "declared_negative_50", "declared_1001"}


def _settings(manual: bool) -> Settings:
    return Settings(
        environment="development", storage_type="local", storage_path=tempfile.mkdtemp(), cors_origins=("http://localhost:8101",),
        database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
        nominal_frequency_manual_override_enabled=manual)


def _kind(baseline: str, path: tuple, before, after, reference: dict) -> str:
    """Classify one difference, checking the new value against the baseline's OWN record of the recording (`reference`: `usable`, `hz`,
    `origin`, `revision`), never against the code under test. An unclassifiable difference aborts the generation."""
    leaf = path[-1]
    if "parameters" in path and leaf in PROVENANCE_KEYS and before == ABSENT:
        want = {"nominal_frequency_basis": "recording", "nominal_frequency_origin": reference["origin"],
                "nominal_frequency_revision": reference["revision"]}[leaf]
        if reference["usable"] and after == want:
            return "power_provenance_added"
        raise SystemExit(f"provenance {path}: {after!r} does not match the recording's own record ({want!r})")
    if not reference["usable"]:
        return "power_refused_unusable_frequency"
    if leaf == "nominal_frequency_hz" and before == 50.0 and after == reference["hz"] != 50.0:
        return "power_frequency_effective"
    if "values" in path and leaf in {"min", "mean", "max"} and reference["hz"] != 50.0:
        return "power_values_corrected_for_recording_frequency"
    raise SystemExit(f"UNCLASSIFIED difference in {baseline}: {path} {before!r} -> {after!r}")


def _http_reference(record: dict) -> dict:
    endpoint = record["nominal_frequency_endpoint"]
    return {"usable": endpoint["usable"], "hz": endpoint["effective_hz"], "origin": endpoint["origin"],
            "revision": 0 if endpoint["mode"] == "auto" else None}


def main() -> None:
    manifest: dict[str, list] = {}

    # ---- NF-3B HTTP baseline (power_channels of each recording)
    baseline = json.loads((BACKEND / "tests/fixtures/nf3b_baselines/nf3b_frozen_baselines.json").read_text(encoding="utf-8"))
    expected = nf3c.apply_approved(baseline, "nf3b_frozen_baselines", include_nf3f=False)
    with TestClient(create_app(_settings(False)), raise_server_exceptions=False) as client:
        current = nf3b_scenarios.run_all(client)
    entries = []
    for recording in sorted(expected["http"]):
        # the recording's effective frequency and origin are recorded by the baseline itself (the independent reference for the new value)
        reference = _http_reference(expected["http"][recording])
        for path, before, after in structured_diff(expected["http"][recording], current["http"][recording], ("http", recording)):
            if "power_channels" not in path:
                raise SystemExit(f"a non-power difference in {recording}: {path}")
            kind = _kind("nf3b_frozen_baselines", path, before, after, reference)
            entries.append({"path": list(path), "before": before, "after": after, "kind": kind})
    manifest["nf3b_frozen_baselines"] = entries

    # ---- NF-3E Phase A power group (r50, r60)
    phase_a = json.loads((BACKEND / "tests/fixtures/nf3e_baselines/nf3e_phase_a_baseline.json").read_text(encoding="utf-8"))["outcomes"]
    expected_a = nf3e.apply_phase_a(phase_a, include_nf3f=False)
    with TestClient(create_app(_settings(True)), raise_server_exceptions=False) as client:
        current_a = nf3e_scenarios.run_all(client)
    entries = []
    for recording in sorted(expected_a["power_channels"]):
        accessor = expected_a["power_channels"][recording]["accessor"]
        reference = {"usable": accessor["usable"], "hz": accessor["hz"], "origin": accessor["origin"], "revision": accessor["revision"]}
        for path, before, after in structured_diff(
                expected_a["power_channels"][recording], current_a["power_channels"][recording], ("power_channels", recording)):
            kind = _kind("nf3e_phase_a_baseline", path, before, after, reference)
            entries.append({"path": list(path), "before": before, "after": after, "kind": kind})
    manifest["nf3e_phase_a_baseline"] = entries

    OUT.write_text(json.dumps({
        "purpose": "The approved NF-3F (O-2) changes to the NF-3B HTTP baseline and the NF-3E Phase A power group; applied after the earlier "
                   "overlays. Generated by generate_nf3f_approved_changes.py; every entry has a kind, an unclassified difference aborts generation.",
        "schema": 1,
        "kinds": ["power_provenance_added", "power_frequency_effective", "power_values_corrected_for_recording_frequency",
                  "power_refused_unusable_frequency"],
        "changes": manifest,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for key, items in manifest.items():
        kinds = {}
        for item in items:
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        print(key, len(items), kinds)


if __name__ == "__main__":
    main()
