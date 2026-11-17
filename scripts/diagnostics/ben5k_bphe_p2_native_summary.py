"""Read-only before/after native summaries; run from each baseline's backend."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd()))
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.normalize import to_disturbance_record, normalized_names
from app.providers.comtrade import _parse_cfg

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--reference-root", required=True, type=Path)
args = parser.parse_args()
fixtures = Path.cwd() / "tests/fixtures/ben"
evidence = json.loads((fixtures / "ben5k_fast_ac_scaling.json").read_text())["bphe"]
mapping = json.loads((fixtures / "ben5k_physical_mapping.json").read_text())["records"]
root = args.reference_root
october = root / "2026" / "20261016 132kV_KTBR" / "BEN"
bphe_dir = root / "2022" / "YGPN 275kV Busbar" / "BEN Files" / "BPHE"
sources = [("bphe", bphe_dir / evidence["files"][0]["name"], evidence["files"][0]["sha256"])]
sources += [(r["id"], october / r["name"], r["sha256"]) for r in mapping]
cfg = _parse_cfg(bphe_dir / evidence["files"][1]["name"])
dat = pd.read_csv(bphe_dir / evidence["files"][2]["name"], header=None, comment="\x1a").dropna(how="all").to_numpy(dtype=np.int64)
export = {}
for i, row in enumerate(evidence["channels"]):
    name = row["name"] + (f"_{row['occurrence']}" if row["occurrence"] else "")
    export[name] = dat[:, i + 2] * cfg.analog_defs[i].a + cfg.analog_defs[i].b
for spec in evidence["files"]:
    assert hashlib.sha256((bphe_dir / spec["name"]).read_bytes()).hexdigest() == spec["sha256"]
result = {}
for label, path, digest in sources:
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    record = parse_ben5k(data)
    names, _ = normalized_names(record)
    normalized = to_disturbance_record(record, source_file=path.name, nominal_frequency_hz=50)
    rows = []
    for c, name, meta in zip(record.value_channels, names, normalized.analog_channels):
        raw = record.raw_values(c)
        values = record.engineering_values(c)
        row = dict(name=name, source_name=c.name, phase=c.phase, physical_word=c.slot.word_index,
                   raw_sha256=hashlib.sha256(raw.astype('<i2').tobytes()).hexdigest(),
                   engineering_sha256=hashlib.sha256(values.astype('<f8').tobytes()).hexdigest(),
                   gain=c.scale, offset=c.offset, unit=c.unit,
                   calibration_status=meta.calibration_authority.status,
                   samples=[dict(index=i, signed_raw=int(raw[i]), engineering=float(values[i]))
                            for i in [0, min(500, len(values) - 1), len(values) - 1]])
        if label == "bphe":
            row.update(export_values_compared=len(values),
                       export_max_abs_error=float(np.max(np.abs(values - export[name]))),
                       export_all_match=bool(np.allclose(values, export[name], rtol=3e-8, atol=1e-9)))
        rows.append(row)
    result[label] = dict(file_sha256=digest, sample_count=record.sample_count, channels=rows)
Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
