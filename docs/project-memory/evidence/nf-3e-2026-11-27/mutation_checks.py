"""NF-3E mutation checks over the derived-staleness predicate, the Option B refusal, the intent/provenance stamp and the O-10 validation.

Each mutation edits ONE production line in a scratch COPY of `backend/` (the worktree is never touched), runs the focused staleness test file and
requires at least one test to fail. A surviving mutation means a test gap. Run from anywhere:

    python mutation_checks.py <path to a python with the backend requirements> [--out results.json] [--only M4,M11]

The scratch copy lives under the system temp directory and is removed afterwards.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"
TEST = "tests/test_nf3e_staleness.py"

#: (id, file under backend/, exact text to replace, replacement, what it breaks)
MUTATIONS = [
    ("M1", "app/services/calculated_channel_staleness.py", "return math.isclose(a, b, rel_tol=AGREEMENT_REL_TOL, abs_tol=AGREEMENT_ABS_TOL)",
     "return True", "frequencies always agree: nothing is ever stale"),
    ("M2", "app/services/calculated_channel_staleness.py", "return math.isclose(a, b, rel_tol=AGREEMENT_REL_TOL, abs_tol=AGREEMENT_ABS_TOL)",
     "return False", "frequencies never agree: a channel is stale even when the recording returns to its frequency"),
    ("M3", "app/services/calculated_channel_staleness.py", 'channel.parameters.get("nominal_frequency_basis") == BASIS_RECORDING',
     'channel.parameters.get("nominal_frequency_basis") in (BASIS_RECORDING, BASIS_EXPLICIT)', "an explicit frequency is assessed (stale because it differs)"),
    ("M4", "app/services/calculated_channel_staleness.py", 'channel.parameters.get("nominal_frequency_basis") == BASIS_RECORDING',
     'channel.parameters.get("nominal_frequency_basis") != BASIS_EXPLICIT', "intent inferred: an omitted basis would follow the recording"),
    ("M5", "app/services/calculated_channel_staleness.py", "    for dependency_id in channel.dependency_ids:\n", "    for dependency_id in []:\n",
     "no inheritance from dependants' ancestors"),
    ("M6", "app/services/calculated_channel_staleness.py", "if all(cause.channel_id != c.channel_id for c in causes):", "if True:",
     "an ancestor reached twice is reported twice"),
    ("M7", "app/services/calculated_channel_staleness.py", "if effective.usable and _agree(float(stored), effective.hz):", "if not effective.usable or _agree(float(stored), effective.hz):",
     "an unusable recording frequency is not stale"),
    ("M8", "app/services/calculated_channel_staleness.py", "REASON_CHANGED if effective.usable else REASON_UNUSABLE", "REASON_CHANGED",
     "the unusable reason is lost"),
    ("M9", "app/services/calculated_channel_staleness.py", "        if staleness.stale:\n            raise StaleCalculatedInputError", "        if False:\n            raise StaleCalculatedInputError",
     "a stale input is never refused"),
    ("M10", "app/services/calculated_channel_staleness.py", "        if staleness.stale:\n            raise StaleCalculatedInputError",
     "        if staleness.stale and any(c.channel_id == channel.id for c in staleness.causes):\n            raise StaleCalculatedInputError",
     "only a DIRECTLY stale input is refused (transitive staleness slips through)"),
    ("M11", "app/services/calculated_channel_staleness.py", "        if ref.kind != \"calculated\":\n            continue\n", "        if ref.kind != \"calculated\":\n            break\n",
     "a source input first in the list hides a later stale calculated input"),
    ("M12", "app/services/calculated_channel_service.py", "if rms_basis == BASIS_RECORDING and not (grounding.usable and abs(grounding.hz - nominal_frequency_hz) <= 1e-9):",
     "if False:", "a recording-following frequency that is not the recording's is accepted"),
    ("M13", "app/services/calculated_channel_service.py", "rms_origin, rms_revision = grounding.origin, grounding.revision", "rms_origin, rms_revision = None, None",
     "origin and revision are not stamped"),
    ("M14", "app/services/calculated_channel_service.py", "rms_basis = BASIS_EXPLICIT if raw_basis is None else raw_basis", "rms_basis = BASIS_RECORDING if raw_basis is None else raw_basis",
     "an omitted basis defaults to recording-following"),
    ("M15", "app/services/calculated_channel_service.py", "if isinstance(rms_basis, bool) or rms_basis not in KNOWN_BASES:", "if False:",
     "an unknown basis is accepted"),
    ("M16", "app/services/calculated_channel_service.py", "    if not nominal_frequency_valid(nominal_frequency_hz):\n        # NF-3E / O-10", "    if False:\n        # NF-3E / O-10",
     "the eligibility endpoint no longer validates the frequency (HTTP 500 for zero)"),
    ("M17", "app/services/compliance_readiness_service.py", "and not (frequency_access is not None and frequency_staleness(", "and not (False and frequency_staleness(",
     "the readiness identity reuses a stale channel"),
    ("M18", "app/api/v1/calculated_channels.py", "            frequency_access=frequency_access,\n        )\n    except ImportServiceError as exc:\n        logger.info(\"Calculated channel creation",
     "        )\n    except ImportServiceError as exc:\n        logger.info(\"Calculated channel creation", "the API forgets to pass the authority to creation"),
    ("M19", "app/api/v1/calculated_channels.py", "if frequency_access is not None and workspace_id is not None else None", "if False else None",
     "the response never carries the derived staleness"),
]


def run(python: str, scratch: Path) -> tuple[int, str]:
    result = subprocess.run([python, "-m", "pytest", "-o", "addopts=--strict-markers", "-p", "no:cacheprovider", "-q", "--no-header", "-W", "ignore", "-x", TEST],
                            cwd=scratch, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr)[-400:]


def main() -> int:
    python = sys.argv[1]
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "backend"
        shutil.copytree(BACKEND, scratch, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        code, tail = run(python, scratch)
        if code != 0:
            print("BASELINE FAILS before any mutation:\n" + tail)
            return 2
        only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
        for mid, rel, old, new, why in MUTATIONS:
            if only and mid not in only:
                continue
            path = scratch / rel
            original = path.read_text(encoding="utf-8")
            text = original.replace("\r\n", "\n")
            if text.count(old) != 1:
                results.append({"id": mid, "status": "NOT_APPLIED", "why": why, "matches": text.count(old)})
                print(mid, "NOT APPLIED", text.count(old))
                continue
            path.write_text(text.replace(old, new), encoding="utf-8", newline="")
            try:
                code, tail = run(python, scratch)
            finally:
                path.write_text(original, encoding="utf-8", newline="")
            status = "KILLED" if code != 0 else "SURVIVED"
            results.append({"id": mid, "status": status, "why": why})
            print(mid, status, "-", why)
    summary = {"killed": sum(r["status"] == "KILLED" for r in results), "total": len(results), "results": results}
    print(f"{summary['killed']} of {summary['total']} killed")
    if out:
        out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0 if summary["killed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
