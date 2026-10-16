"""Write or check relay conformance expectations from the current behaviour (DEC-199).

    python -m tests.relay_conformance.snapshot <expectation-name> [--sheet ID] [--overrides JSON] [--real FILE.pdf] [--write]

Without ``--write`` it prints the observation as JSON. With ``--write`` it records it as
``expectations/<expectation-name>.json`` (an existing file keeps its ``sample``, ``description``, ``browser`` and
``values_mode`` and, for a real sheet, only the ``values`` keys it already lists). A snapshot freezes behaviour: review
every difference before writing one -- the expectation states what the relay import must do, it is not a log.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.relay_conformance.golden import v1_golden
from tests.relay_conformance.shadow_golden import shadow_golden
from tests.relay_conformance.harness import EXPECTATIONS_DIR, SCHEMA, observe, sample_pdf


def make_client(storage: str) -> TestClient:
    settings = Settings(environment="development", storage_type="local", storage_path=storage,
                        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
                        git_sha="local", version="local")
    return TestClient(create_app(replace(settings, max_relay_import_upload_size_mb=5)))


def dump(data: dict) -> str:
    """Stable, diff-friendly JSON: one entry per line for the large maps."""
    lines = ["{"]
    keys = list(data)
    for n, key in enumerate(keys):
        value = data[key]
        comma = "," if n < len(keys) - 1 else ""
        if isinstance(value, dict) and value and key not in ("sample", "mutations", "identity", "counts", "readiness", "apply",
                                                               "golden", "coverage", "offers", "shadow_geometry"):
            inner = ",\n".join(f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                               for k, v in value.items())
            lines.append(f"  {json.dumps(key)}: {{\n{inner}\n  }}{comma}")
        elif key == "golden":
            head = ", ".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in value.items() if k != "zones")
            zones = ",\n".join(f"    {json.dumps(z, ensure_ascii=False)}" for z in value["zones"])
            lines.append(f'  "golden": {{{head}, "zones": [' + (f"\n{zones}\n  " if zones else "") + f']}}{comma}')
        elif key == "apply" and isinstance(value, dict) and value.get("zones"):
            zones = ",\n".join(f"      {json.dumps(z, ensure_ascii=False)}" for z in value["zones"])
            head = ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in value.items() if k != "zones")
            lines.append(f'  "apply": {{{head}, "zones": [\n{zones}\n  ]}}{comma}')
        else:
            lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}{comma}")
    lines.append("}")
    text = "\n".join(lines) + "\n"
    assert json.loads(text) == data
    return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="snapshot")
    parser.add_argument("name")
    parser.add_argument("--sheet")
    parser.add_argument("--overrides")
    parser.add_argument("--real")
    parser.add_argument("--manual", help='JSON list of {"item_id": ..., "value": ...} entered during review')
    parser.add_argument("--description")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    path = EXPECTATIONS_DIR / f"{args.name}.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if args.real:
        sample = {"kind": "real", "file": args.real}
    elif args.sheet:
        sample = {"kind": "synthetic", "sheet": args.sheet}
        if args.overrides:
            sample["overrides"] = json.loads(args.overrides)
    else:
        sample = existing["sample"]
    if args.manual:
        sample["manual"] = json.loads(args.manual)
    pdf = sample_pdf(sample)
    if pdf is None:
        sys.stderr.write("sample not available (set RELAY_SAMPLE_PDF_DIR)\n")
        return 1
    with tempfile.TemporaryDirectory() as storage, make_client(storage) as client:
        observed = observe(client, pdf, sample.get("manual"))
    record: dict = {"schema": SCHEMA}
    if args.description or existing.get("description"):
        record["description"] = args.description or existing["description"]
    record["sample"] = sample
    for key in ("browser", "values_mode", "mutations"):
        if key in existing:
            record[key] = existing[key]
    if sample["kind"] == "real":
        # an owner sheet: no full value dump is committed -- only the values the expectation already names
        wanted = existing.get("values", {})
        observed["values"] = {k: observed["values"].get(k) for k in wanted}
        observed["provenance"] = {k: observed["provenance"][k] for k in wanted if k in observed["provenance"]}
        record["values_mode"] = "subset"
        observed.pop("preserved", None)
    record.update(observed)
    record["golden"] = v1_golden(observed.get("apply"))              # V1 geometry, never V2 (DEC-199 Phase 1)
    # independent engineering goldens for shadow boundaries V1 cannot draw (DEC-199 Phase 2A)
    record["shadow_golden"] = shadow_golden(observed.get("shadow_geometry"))
    text = dump(record)
    if args.write:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.name}")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
