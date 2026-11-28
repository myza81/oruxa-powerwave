"""N15 (backend) plus the two frontend mutations (run through Playwright on the scratch copy)."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
PY = "D:/Programming/oruxa-powerwave/backend/.venv/Scripts/python.exe"
results = []


def mutate(rel, old, new, runner):
    path = ROOT / rel
    original = path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    work = text.replace("\r\n", "\n")
    if old not in work:
        return "SETUP-ERROR", "pattern not found"
    mutated = work.replace(old, new, 1)
    path.write_bytes((mutated.replace("\n", "\r\n") if crlf else mutated).encode("utf-8"))
    try:
        code, tail = runner()
    finally:
        path.write_bytes(original)
    return ("KILLED" if code != 0 else "SURVIVED"), tail


def pytest_runner(tests):
    def run():
        r = subprocess.run([PY, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", "-x", "-W", "ignore", *tests],
                           cwd=ROOT / "backend", capture_output=True, text=True)
        tail = [ln for ln in r.stdout.splitlines() if "passed" in ln or "failed" in ln]
        return r.returncode, (tail[-1] if tail else r.stdout[-120:])
    return run


def pw_runner(grep):
    def run():
        env = {**__import__("os").environ, "PW_PYTHON": PY}
        r = subprocess.run(["npx", "playwright", "test", "nf3c_origin_labels", "--workers=1", "--reporter=line", "-g", grep],
                           cwd=ROOT / "browser-tests", capture_output=True, text=True, shell=True, env=env)
        out = r.stdout + r.stderr
        tail = [ln.strip() for ln in out.splitlines() if re.search(r"^\s*\d+ (passed|failed)", ln)]
        return r.returncode, " / ".join(tail) if tail else out[-160:]
    return run


for name, rel, old, new, runner in [
    ("N18 the shared label function gives an unknown origin a provenance ('From recording')", "frontend/index.html",
     'default: return "Origin not recognised";', 'default: return "From recording";', pw_runner("shared label function")),
    ("N19 the facts card prints the raw imported number again (null Hz / NaN Hz)", "frontend/index.html",
     'html += fact("Nominal frequency", nominalDisplay.text);', 'html += fact("Nominal frequency", source.nominal_frequency + " Hz");', pw_runner("facts card")),
]:
    verdict, tail = mutate(rel, old, new, runner)
    results.append({"mutation": name, "result": verdict, "evidence": tail})
    print(f"{verdict:10s} {name} -- {tail}", flush=True)
Path(sys.argv[2]).write_text(json.dumps(results, indent=1), encoding="utf-8")
