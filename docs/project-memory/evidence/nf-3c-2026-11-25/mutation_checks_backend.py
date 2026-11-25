"""NF-3C mutation checks: every mutation is applied to a scratch copy of the committed tree; the relevant tests must FAIL (mutation killed)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
PY = "D:/Programming/oruxa-powerwave/backend/.venv/Scripts/python.exe"
B = ROOT / "backend"
V = ["tests/test_nf3c_validating_consumers.py"]
O = ["tests/test_nf3c_oscillation_origin.py"]
BASE = ["tests/test_nf3b_frozen_baselines.py", "tests/test_nf3c_pre_migration_baseline.py"]
G = ["tests/test_nf3b_frequency_call_path_guard.py", "tests/test_nf1_nominal_frequency_authority.py"]

MS = "app/services/compliance_measurement_service.py"
RD = "app/services/compliance_readiness_service.py"
SY = "app/services/synchronization_service.py"
OS = "app/services/oscillation_representation_service.py"
OSP = "app/services/oscillation_spectrum_service.py"
AP = "tests/nf3c_approved_changes.py"

M = [
    ("N1 measurement classifier ignores usability and calls the detector", MS, "    if not frequency.usable:\n        return None\n", "", V),
    ("N2 measurement classifier uses the imported value, not the effective one", MS, "classify_waveform_form(time, values, frequency.hz)", "classify_waveform_form(time, values, active.metadata.nominal_frequency)", V),
    ("N3 readiness reports an unusable value as 'unknown' again", RD, 'what = f"the nominal frequency declared by this recording ({declared}) is not usable"', 'what = "the nominal frequency of this recording is unknown"', V),
    ("N4 readiness always offers the Manual remedy", RD, "                      if outcome.manual_override_enabled\n                      else \"Create the RMS channel in Calculated Channels with an explicit frequency.\")", "                      if True\n                      else \"Create the RMS channel in Calculated Channels with an explicit frequency.\")", V),
    ("N5 readiness step carries the imported value instead of the effective one", RD, "    frequency = outcome.hz\n", "    frequency = outcome.imported_hz\n", V),
    ("N6 readiness ignores the Manual value of a calculated channel's grounding recording", RD, "        return frequency_access.for_channel_ref(workspace_id, ref, calc_registry=calc_registry)", "        return frequency_access.for_source(workspace_id, getattr(ref, 'source_id', None) or 'src')", V),
    ("N7 event detection hands the detector the imported value", SY, "time_slice, values_slice, nominal_frequency_hz=frequency.hz, sensitivity=sensitivity", "time_slice, values_slice, nominal_frequency_hz=active.metadata.nominal_frequency, sensitivity=sensitivity", V),
    ("N8 event detection calls the detector for an unusable frequency", SY, "    if frequency.usable:\n        result = detect_event_onset(", "    if True:\n        result = detect_event_onset(", V),
    ("N9 event detection echoes the effective value as zero for an unusable recording", SY, "        echoed_frequency_hz = active.metadata.nominal_frequency\n", "        echoed_frequency_hz = 0.0\n", V + BASE),
    ("N10 oscillation origin is always recording_metadata", OS, "nominal_frequency_origin=frequency.origin,", "nominal_frequency_origin='recording_metadata',", O + BASE),
    ("N11 oscillation revision is always zero", OS, "nominal_frequency_revision=frequency.revision,", "nominal_frequency_revision=0,", O),
    ("N12 oscillation does not check usability before the numerics", OS, "    if not frequency.usable:\n        return unavailable(\"invalid_nominal_frequency\"", "    if False:\n        return unavailable(\"invalid_nominal_frequency\"", O),
    ("N13 oscillation derives the RMS with the imported value", OS, "derive_rms_magnitude(time, np.asarray(resolved.values, dtype=np.float64), frequency.hz)", "derive_rms_magnitude(time, np.asarray(resolved.values, dtype=np.float64), frequency.imported_hz)", O),
    ("N14 the spectrum response drops the revision", OSP, '"nominal_frequency_revision": series.nominal_frequency_revision,', '"nominal_frequency_revision": None,', O),
    ("N15 an approved change is dropped (the overlay is enforced)", AP, "APPROVED_CHANGES.append((\n        _NF3B, \"in_process/declared_1001/compliance_measurement_input_type\"", "(lambda *a: None)((\n        _NF3B, \"in_process/declared_1001/compliance_measurement_input_type\"", BASE),
    ("N16 a migrated consumer reads the imported value directly again", MS, "def evaluate_voltage_measurement(", "def _nf3c_mutant(active):\n    return active.metadata.nominal_frequency\n\n\ndef evaluate_voltage_measurement(", G),
    ("N17 an unmigrated consumer changes silently (power window default 60)", "app/domain/calculated_channel.py", "    nominal_frequency_hz: float = 50.0,\n) -> np.ndarray:\n    \"\"\"Time-varying P(t) [MW]", "    nominal_frequency_hz: float = 60.0,\n) -> np.ndarray:\n    \"\"\"Time-varying P(t) [MW]", BASE + G),
]


def run(tests):
    r = subprocess.run([PY, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", "-x", "-W", "ignore", *tests], cwd=B, capture_output=True, text=True)
    tail = [ln for ln in r.stdout.splitlines() if ("passed" in ln or "failed" in ln or "error" in ln)]
    return r.returncode, (tail[-1] if tail else r.stdout[-160:])


results = []
for name, rel, old, new, tests in M:
    path = B / rel
    original = path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    work = text.replace("\r\n", "\n")
    if old not in work:
        results.append({"mutation": name, "result": "SETUP-ERROR"})
        print("SETUP-ERROR", name, flush=True)
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
code, summary = run(V + O + G)
print("restored-tree sanity:", "OK" if code == 0 else "BROKEN", summary)
Path(sys.argv[2]).write_text(json.dumps(results, indent=1), encoding="utf-8")
print("killed", sum(r["result"] == "KILLED" for r in results), "of", len(results))
