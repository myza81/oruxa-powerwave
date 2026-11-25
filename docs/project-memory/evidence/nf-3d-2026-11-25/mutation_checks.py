"""NF-3D mutation checks on the authority, refusal and provenance paths (run on a scratch copy of the working tree)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
PY = "D:/Programming/oruxa-powerwave/backend/.venv/Scripts/python.exe"
TESTS = ["tests/test_nf3d_behaviour.py", "tests/test_nf3d_independent_oracles.py", "tests/test_nf3d_pre_migration_baseline.py",
         "tests/test_nf3d_approved_changes.py"]
results = []


def run(tests):
    r = subprocess.run([PY, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", "-x", "-W", "ignore", *tests],
                       cwd=ROOT / "backend", capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if " passed" in ln or " failed" in ln or ln.startswith("FAILED")]
    return r.returncode, " | ".join(lines[-2:]) if lines else r.stdout[-200:]


def mutate(rel, old, new, tests):
    path = ROOT / "backend" / rel
    original = path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    work = text.replace("\r\n", "\n")
    if work.count(old) < 1:
        return "SETUP-ERROR", "pattern not found"
    mutated = work.replace(old, new, 1)
    path.write_bytes((mutated.replace("\n", "\r\n") if crlf else mutated).encode("utf-8"))
    try:
        code, tail = run(tests)
    finally:
        path.write_bytes(original)
    return ("KILLED" if code != 0 else "SURVIVED"), tail


A = "app/services/analysis_reference_frequency.py"
P = "app/services/phasor_analysis_service.py"
O = "app/services/overcurrent_analysis_service.py"
CASES = [
    ("M1 an unusable authority substitutes 50 Hz instead of refusing", A,
     "    if combined.status == AGREEMENT_UNAVAILABLE:\n        return ReferenceFrequencyDecision(\n            None, REASON_INVALID_REFERENCE_FREQUENCY, unusable_message([m for m in combined.members if not m.usable]), None)",
     "    if combined.status == AGREEMENT_UNAVAILABLE:\n        return ReferenceFrequencyDecision(50.0, None, None, None)"),
    ("M2 the unusable-authority refusal is skipped (the value reaches the kernel path)", A,
     "    if combined.status == AGREEMENT_UNAVAILABLE:", "    if False:"),
    ("M3 an invalid explicit override is accepted", A, "        if not nominal_frequency_valid(override):", "        if False:"),
    ("M4 an unusable authority is reported under the conflict reason", A,
     "None, REASON_INVALID_REFERENCE_FREQUENCY, unusable_message(", "None, REASON_REFERENCE_FREQUENCY_CONFLICT, unusable_message("),
    ("M5 the decision drops the provenance of a computed frequency", A,
     "return ReferenceFrequencyDecision(combined.common_hz, None, None, provenance)", "return ReferenceFrequencyDecision(combined.common_hz, None, None, None)"),
    ("M6 an explicit override carries a recording provenance", A,
     "        return ReferenceFrequencyDecision(float(override), None, None, None)",
     "        return ReferenceFrequencyDecision(float(override), None, None, provenance_of([RecordingFrequencyUse(f.source_id, f.origin, f.revision) for f in frequencies]))"),
    ("M7 mixed origins are summarised as one origin", "app/domain/frequency_provenance.py",
     "origin = next(iter(origins)) if len(origins) == 1 else None", "origin = next(iter(origins))"),
    ("M8 a multi-recording revision is reported as the first recording's", "app/domain/frequency_provenance.py",
     "revision = used[0].revision if len(used) == 1 else None", "revision = used[0].revision"),
    ("M9 the origin is hard-coded to recording_metadata", "app/domain/frequency_provenance.py",
     "    origins = {u.origin for u in used}", "    origins = {'recording_metadata' for u in used}"),
    ("M10 the sampling pre-check is stricter than the estimator (floor instead of ceil)", A,
     "return math.ceil((1.0 / frequency_hz) / median_dt - _SPC_TOLERANCE)", "return math.floor((1.0 / frequency_hz) / median_dt - _SPC_TOLERANCE)"),
    ("M11 the sampling pre-check never refuses", A,
     ">= min_samples_per_cycle\n", ">= 0\n"),
    ("M12 phasor: the sampling pre-check is skipped before the detector", P,
     "    if not sampling_supports(candidate.time, reference_frequency_hz, PHASOR_MIN_SAMPLES_PER_CYCLE):", "    if False:"),
    ("M13 phasor: a sampling limit is reported as a waveform-form refusal", P,
     "        return SAMPLING_UNSUPPORTED\n    detector_result", "        return FORM_NOT_ELIGIBLE\n    detector_result"),
    ("M14 overcurrent: a sampling limit is reported as a waveform-form refusal", O,
     "        return SAMPLING_UNSUPPORTED", "        return FORM_NOT_ELIGIBLE"),
    ("M15 the router drops the provenance fields of the phasor result", "app/api/v1/engineering_contexts.py",
     "**provenance_fields(result.frequency_provenance), window_seconds=result.window_seconds,", "window_seconds=result.window_seconds,"),
    ("M16 the wire mixin always reports no provenance", "app/schemas/frequency_provenance.py",
     "    if provenance is None:", "    if True:"),
    ("M17 the server gate is ignored (Manual honoured while the gate is closed)", "app/services/nominal_frequency_access.py",
     "        self._enabled = bool(manual_override_enabled)", "        self._enabled = True"),
]

only = sys.argv[3:]
for name, rel, old, new in CASES:
    if only and not any(name.startswith(o + " ") for o in only):
        continue
    verdict, tail = mutate(rel, old, new, TESTS)
    results.append({"mutation": name, "result": verdict, "evidence": tail})
    print(f"{verdict:12s} {name} -- {tail}", flush=True)
Path(sys.argv[2]).write_text(json.dumps(results, indent=1), encoding="utf-8")
