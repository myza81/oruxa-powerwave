"""Run the NF-3B scenario set against whichever backend tree is given and write the raw outcomes (sorted JSON) plus its SHA-256.
Usage: python equiv_run.py <backend_dir> <out.json>"""
import hashlib, json, sys
from pathlib import Path
backend = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(backend))
sys.path.insert(0, str(backend / "tests" / "fixtures" / "nf3b_baselines"))
import generate_nf3b_baselines as g
import app
print("app imported from:", Path(app.__file__).resolve().parent)
outcomes = g.run_once()
text = json.dumps(outcomes, sort_keys=True, indent=1)
Path(sys.argv[2]).write_text(text + "\n", encoding="utf-8", newline="\n")
print("sha256", hashlib.sha256(text.encode()).hexdigest(), "scenario leaves", text.count(":"))
