"""NF-3B mutation checks: each mutation is applied to a scratch copy of the committed tree, the relevant tests are run, and the
mutation must be KILLED (at least one test fails). The worktree under test is never modified."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
PY = "D:/Programming/oruxa-powerwave/backend/.venv/Scripts/python.exe"
B = ROOT / "backend"
ACCESS_TESTS = ["tests/test_nf3b_nominal_frequency_access.py"]
GATE_TESTS = ["tests/test_nf3b_server_side_release_gate.py", "tests/test_nf1_nominal_frequency_authority.py"]
GUARD_TESTS = ["tests/test_nf3b_frequency_call_path_guard.py"]
BASE_TESTS = ["tests/test_nf3b_frozen_baselines.py"]

SVC = "app/services/nominal_frequency_service.py"
ACC = "app/services/nominal_frequency_access.py"
CFG = "app/config.py"
API = "app/api/v1/nominal_frequency.py"

MUTATIONS = [
    ("M1 service ignores a stored Manual value", SVC, "manual.value_hz if manual is not None and manual_override_enabled else None", "None", ACCESS_TESTS + GATE_TESTS),
    ("M2 service honours a stored Manual value while the gate is closed", SVC, "manual.value_hz if manual is not None and manual_override_enabled else None", "manual.value_hz if manual is not None else None", ACCESS_TESTS + GATE_TESTS),
    ("M3 set_manual does not enforce the gate", SVC, "    if not manual_override_enabled:\n        raise ManualNominalFrequencyDisabledError(", "    if False:\n        raise ManualNominalFrequencyDisabledError(", ACCESS_TESTS + GATE_TESTS),
    ("M4 set_manual validates the value before the gate", SVC, "    if not manual_override_enabled:\n        raise ManualNominalFrequencyDisabledError(", "    if not valid_nominal_frequency(value_hz):\n        raise InvalidNominalFrequencyError('bad')\n    if not manual_override_enabled:\n        raise ManualNominalFrequencyDisabledError(", ACCESS_TESTS + GATE_TESTS),
    ("M5 an unusable value is silently replaced by the 50 Hz default", ACC, "source_id=source_id, hz=r.effective_hz, origin=r.origin", "source_id=source_id, hz=(r.effective_hz if r.effective_hz is not None else 50.0), origin=r.origin", ACCESS_TESTS),
    ("M6 a mixed set returns the first member's frequency", ACC, "return MultiSourceFrequency(members, AGREEMENT_MIXED, None, distinct, ())", "return MultiSourceFrequency(members, AGREEMENT_MIXED, usable[0], distinct, ())", ACCESS_TESTS),
    ("M7 the agreed value is the first listed, not the smallest", ACC, "AGREEMENT_AGREED, min(usable), distinct", "AGREEMENT_AGREED, usable[0], distinct", ACCESS_TESTS),
    ("M8 a calculated channel is resolved by its own id, not its grounding recording", ACC, "return self.for_source(workspace_id, channel.reference_source_id)", "return self.for_source(workspace_id, ref.calculated_channel_id)", ACCESS_TESTS),
    ("M9 an unusable member does not make the set unavailable", ACC, "    if unusable:\n        return MultiSourceFrequency(members, AGREEMENT_UNAVAILABLE", "    if False:\n        return MultiSourceFrequency(members, AGREEMENT_UNAVAILABLE", ACCESS_TESTS),
    ("M10 the accessor ignores the policy it was built with", ACC, "self._enabled = bool(manual_override_enabled)", "self._enabled = True", ACCESS_TESTS + GATE_TESTS),
    ("M11 the gate defaults open in the dataclass", CFG, "nominal_frequency_manual_override_enabled: bool = False", "nominal_frequency_manual_override_enabled: bool = True", GATE_TESTS),
    ("M12 a deployed build accepts the open gate", CFG, "    if nominal_frequency_manual_override_enabled and deployed:", "    if False:", GATE_TESTS),
    ("M13 any non-empty value opens the gate", CFG, '"NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED", "").strip().lower() in ("1", "true", "yes")', '"NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED", "").strip().lower() != ""', GATE_TESTS),
    ("M14 the router does not map the disabled error to 409", API, '    "manual_nominal_frequency_disabled": status.HTTP_409_CONFLICT,\n', "", GATE_TESTS),
    ("M15 the router passes no policy: GET honours a stored value", ACC, "            manual_override_enabled=self._enabled)\n\n    def for_source", "            manual_override_enabled=True)\n\n    def for_source", GATE_TESTS + ACCESS_TESTS),
    ("M16 workspace isolation lost (accessor ignores the workspace)", ACC, "        return _authority.effective_nominal_frequency(\n            workspace_id, source_id,", "        return _authority.effective_nominal_frequency(\n            'ws-nf3b', source_id,", ACCESS_TESTS),
    ("M17 a consumer reads the imported value directly", "app/services/impedance_analysis_service.py", "\n", "\n\ndef _nf3b_mutant(active):\n    return active.metadata.nominal_frequency\n", GUARD_TESTS),
    ("M18 a consumer imports the accessor", "app/services/impedance_analysis_service.py", "\n", "\nfrom app.services.nominal_frequency_access import NominalFrequencyAccess  # noqa\n", GUARD_TESTS),
    ("M19 a consumer hard-codes a 60 Hz window", "app/services/impedance_analysis_service.py", "\n", "\n\ndef _nf3b_mutant(time):\n    return time * 60.0\n", GUARD_TESTS),
    ("M20 a consumer reads the stored registry value", "app/services/impedance_analysis_service.py", "\n", "\n\ndef _nf3b_mutant(request):\n    return request.app.state.nominal_frequency_registry.snapshot('w', 's')\n", GUARD_TESTS),
    ("M21 a new frequency default argument", "app/domain/overcurrent.py", "\n", "\n\ndef _nf3b_mutant(time, reference_frequency_hz=50.0):\n    return time\n", GUARD_TESTS),
    ("M22 a consumer migrates silently (RMS window uses 60 Hz)", "app/services/calculated_channel_service.py", "rms_recording_long_enough(v_res.time, 50.0)", "rms_recording_long_enough(v_res.time, 60.0)", BASE_TESTS + GUARD_TESTS),
    ("M23 the power kernel default changes", "app/domain/calculated_channel.py", "    nominal_frequency_hz: float = 50.0,\n) -> np.ndarray:\n    \"\"\"Time-varying P(t) [MW]", "    nominal_frequency_hz: float = 60.0,\n) -> np.ndarray:\n    \"\"\"Time-varying P(t) [MW]", BASE_TESTS + GUARD_TESTS),
]


def run(tests):
    r = subprocess.run([PY, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", "-x", "-W", "ignore", *tests],
                       cwd=B, capture_output=True, text=True)
    tail = [ln for ln in r.stdout.splitlines() if ("passed" in ln or "failed" in ln or "error" in ln)]
    return r.returncode, (tail[-1] if tail else r.stdout[-200:])


results = []
for name, rel, old, new, tests in MUTATIONS:
    path = B / rel
    original = path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    work = text.replace("\r\n", "\n")
    if old == "\n":                                           # append
        mutated = work.rstrip("\n") + new
    else:
        if old not in work:
            results.append({"mutation": name, "result": "SETUP-ERROR: pattern not found"})
            print(name, "SETUP-ERROR", flush=True)
            continue
        mutated = work.replace(old, new, 1)
    if crlf:
        mutated = mutated.replace("\n", "\r\n")
    path.write_bytes(mutated.encode("utf-8"))
    try:
        code, summary = run(tests)
    finally:
        path.write_bytes(original)
    verdict = "KILLED" if code != 0 else "SURVIVED"
    results.append({"mutation": name, "result": verdict, "evidence": summary})
    print(f"{verdict:9s} {name} -- {summary}", flush=True)

code, summary = run(ACCESS_TESTS + GUARD_TESTS)
print("restored-tree sanity:", "OK" if code == 0 else "BROKEN", summary)
Path(sys.argv[2]).write_text(json.dumps(results, indent=1), encoding="utf-8")
print("killed", sum(r["result"] == "KILLED" for r in results), "of", len(results))
