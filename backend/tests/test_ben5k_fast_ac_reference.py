"""Full independent BPHE parity and unchanged BEN6K controls, owner files only.

BPHE conversion uses the recovered independent physical columns. Its existing
end-to-end mapping is explicitly asserted to remain unresolved (P2 excluded).
"""
from dataclasses import replace
from functools import cache
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import pandas as pd
import pytest

from app.providers.ben import parse_ben
from app.providers.ben.legacy_ben5k.engineering import (
    fast_ac_engineering_values, has_supported_fast_ac_configuration,
)
from app.providers.ben.legacy_ben5k.decoder import decode_samples
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.legacy_ben5k.reader import read_header, read_channel_descriptors
from app.providers.ben.normalize import to_disturbance_record
from app.providers.comtrade import _parse_cfg

pytestmark = pytest.mark.ben_reference
FIXTURES = Path(__file__).parent / "fixtures/ben"
EVIDENCE = json.loads((FIXTURES / "ben5k_fast_ac_scaling.json").read_text())
BPHE = EVIDENCE["bphe"]
CONTROL = json.loads((FIXTURES / "ben6k_scaling_control.json").read_text())["record"]


@pytest.fixture(scope="module")
def root(request):
    configured = request.config.getoption("--ben-reference-dir")
    if not configured:
        pytest.skip("P1 owner-file parity requires --ben-reference-dir")
    return Path(configured)


@cache
def _original(root, name, sha256):
    paths = sorted(root.rglob(name))
    if not paths:
        pytest.skip(f"Owner reference unavailable: {name}")
    for p in paths:
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() == sha256:
            return p, data
    pytest.fail(f"No original hash matches {name}")


@cache
def _bphe(root):
    paths = [_original(root, e["name"], e["sha256"])[0] for e in BPHE["files"]]
    data = paths[0].read_bytes()
    cfg = _parse_cfg(paths[1])
    values = pd.read_csv(paths[2], header=None, comment="\x1a").dropna(how="all").to_numpy(dtype=np.int64)
    return data, cfg, values


@pytest.mark.parametrize("column", range(14), ids=[f"{c['name']}-{c['occurrence']}" for c in BPHE["channels"]])
def test_bphe_all_1148_samples_match_independent_export_with_real_descriptor(root, column):
    data, cfg, dat = _bphe(root)
    evidence = BPHE["channels"][column]
    d = evidence["descriptor"]["offset"]
    gain, offset = struct.unpack_from("<ff", data, d + 28)
    assert (gain, offset) == (evidence["descriptor"]["gain"], 0.0)
    assert data[d:d + 58].hex(" ") == evidence["descriptor"]["raw_hex"]
    raw = np.array([struct.unpack_from(">h", data, BPHE["payload_offset"] + 2 * (i * BPHE["words"] + evidence["physical_word"]))[0]
                    for i in range(1148)], dtype=np.int16)
    assert cfg.analog_defs[column].ch_id == evidence["name"]
    # Complete original DAT column, not generated numerical targets.
    np.testing.assert_array_equal((raw.astype(np.int32) >> 4) << 4, dat[:, column + 2])
    expected = dat[:, column + 2] * cfg.analog_defs[column].a + cfg.analog_defs[column].b
    corrected = fast_ac_engineering_values(raw, gain, offset)
    np.testing.assert_allclose(corrected, expected, rtol=3e-8, atol=1e-9)
    assert has_supported_fast_ac_configuration(data, read_header(data))


def test_bphe_native_mapping_remains_explicitly_unresolved(root):
    data, _, _ = _bphe(root)
    record = parse_ben5k(data)
    assert len(record.value_channels) == 7  # missing first feeder is P2
    assert [c.slot.word_index for c in record.value_channels] == [16, 17, 18, 20, 21, 22, 23]
    ir = record.value_channel("YGPN/BBTU2 IR")
    assert ir.slot.word_index == 20  # oracle physical word is 15
    correct_raw = np.array([struct.unpack_from(">h", data, BPHE["payload_offset"] + 2 * 15)[0]], dtype=np.int16)
    assert record.engineering_values(ir)[0] != fast_ac_engineering_values(correct_raw, ir.scale)[0]


def test_bphe_standalone_decoder_uses_same_numeric_contract_without_fixing_mapping(root):
    data, _, _ = _bphe(root)
    header = read_header(data)
    analog, _ = read_channel_descriptors(data, header)
    evidence = next(c for c in BPHE["channels"] if c["name"] == "YGPN/BBTU2 IR")
    ir = next(c for c in analog if c.name == evidence["name"])
    # Isolate P1 from P2 with the already independently established slot.
    ir = replace(ir, physical_word_index=evidence["physical_word"])
    values, _ = decode_samples(data, header, [ir], [])
    assert values[0, 0] == pytest.approx(.2116712064, rel=1e-7)


@pytest.mark.parametrize("header_byte,value", [(4, 0x2a), (4, 0x29), (6, 2), (14, 6), (60, 1)])
def test_reviewed_configuration_cannot_bypass_format_and_fast_guards(root, header_byte, value):
    data, _, _ = _bphe(root)
    changed = bytearray(data)
    changed[header_byte] = value
    assert not has_supported_fast_ac_configuration(bytes(changed), read_header(data))


def test_unidentified_configuration_is_not_inferred_from_voltage_current_labels(root):
    data, _, _ = _bphe(root)
    changed = bytearray(data)
    changed[220] ^= 1
    assert not has_supported_fast_ac_configuration(bytes(changed), read_header(data))
    # Sample/header changes do not change AC interpretation of a known catalog.
    changed = bytearray(data)
    changed[0x64] ^= 1
    changed[BPHE["payload_offset"] + 1] ^= 1
    assert has_supported_fast_ac_configuration(bytes(changed), read_header(data))


def test_ben6k_subben_all_103_engineering_columns_unchanged_from_initial_parser(root):
    p, data = _original(root, CONTROL["name"], CONTROL["sha256"])
    record = parse_ben(data)
    assert len(record.value_channels) == 103
    normalized = to_disturbance_record(record, source_file=p.name, nominal_frequency_hz=50)
    for c, expected in zip(record.value_channels, CONTROL["channels"]):
        assert c.name == expected["name"]
        assert hashlib.sha256(record.raw_values(c).astype('<i2').tobytes()).hexdigest() == expected["raw_sha256"]
        engineering = record.engineering_values(c)
        assert hashlib.sha256(engineering.astype('<f8').tobytes()).hexdigest() == expected["engineering_sha256"]
        np.testing.assert_array_equal(normalized.waveform_data[c.name.strip()], engineering)
