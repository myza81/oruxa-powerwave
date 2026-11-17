"""Reproduce native GPTH Slow parity against pinned independent BEN/CFG/DAT.

Run from the repository root with --reference-root and --output. Original files
stay read-only; this writes numerical summaries and digests, never original data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
from app.providers.ben.parser import parse_ben_experimental
from app.providers.comtrade import _parse_cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads((REPO / "backend/tests/fixtures/ben/gpth_2022_legacy_slow.json").read_text())
    paths = [args.reference_root / evidence["relative_directory"] / f["name"] for f in evidence["files"]]
    for path, spec in zip(paths, evidence["files"]):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"], path
    cfg = _parse_cfg(paths[1])
    dat = pd.read_csv(paths[2], header=None, comment="\x1a").dropna(how="all").to_numpy(dtype=np.int64)
    record = parse_ben_experimental(paths[0].read_bytes(), allow_legacy_ben5k=True)
    rows = []
    for c, e in zip(record.value_channels, evidence["analog"]):
        definition = cfg.analog_defs[e["export_column"]]
        raw = dat[:, 2 + e["export_column"]]
        expected = raw * definition.a + definition.b
        actual = record.engineering_values(c)
        assert c.name == definition.ch_id and c.unit == definition.uu
        assert np.array_equal(record.raw_values(c), raw)
        assert np.all(np.abs(actual - expected) <= np.abs(raw) * 5e-11 + 1e-9)
        rows.append(dict(channel_id=c.channel_id, name=c.name, physical_word=c.slot.word_index,
            frame_offset=e["frame_offset"], native_gain=e["gain"], effective_gain=c.scale, offset=c.offset,
            unit=c.unit, export_column=e["export_column"], values_matched=len(raw),
            max_abs_error=float(np.max(np.abs(actual - expected))),
            raw_sha256=hashlib.sha256(record.raw_values(c).astype('<i2').tobytes()).hexdigest(),
            engineering_sha256=hashlib.sha256(actual.astype('<f8').tobytes()).hexdigest(),
            constant_0x0800=bool(np.all(raw == 0x0800)), samples=e["samples"]))
    for c, e in zip(record.digital_channels, evidence["digital"]):
        assert np.array_equal(record.digital_states(c), dat[:, 22 + e["export_column"]])
    result = dict(files=evidence["files"], configuration_sha256=evidence["configuration_sha256"],
        sample_count=record.sample_count, analog_channels=len(record.value_channels),
        engineering_values_matched=sum(c["values_matched"] for c in rows),
        max_abs_error=max(c["max_abs_error"] for c in rows),
        binary_channels=len(record.digital_channels), binary_states_matched=len(record.digital_channels)*record.sample_count,
        constant_0x0800_channels=sum(c["constant_0x0800"] for c in rows), channels=rows)
    assert result["engineering_values_matched"] == result["binary_states_matched"] == 28040
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({k: v for k, v in result.items() if k != "channels"}, indent=2))


if __name__ == "__main__":
    main()
