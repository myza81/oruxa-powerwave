"""Full independent BPHE native parity and unchanged BEN6K controls, owner files only."""
from dataclasses import replace
from functools import cache
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.ben.errors import BenStructureError, BenUnsupportedVariantError
from app.providers.ben import parse_ben
from app.providers.ben.legacy_ben5k.engineering import (
    fast_ac_engineering_values, has_supported_fast_ac_configuration,
)
from app.providers.ben.legacy_ben5k.decoder import decode_samples
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.legacy_ben5k.reader import read_header, read_channel_descriptors
from app.providers.ben.legacy_ben5k.reader import read_descriptor_region
from app.providers.ben.legacy_ben5k.bphe_layout import bphe_physical_words
from app.providers.ben.normalize import to_disturbance_record
from app.providers.ben.provider import BenProvider
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
    region = read_descriptor_region(data, read_header(data))
    assert (region.start, region.end) == (0x354, BPHE["payload_offset"] - 10)
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
    # P2 acceptance: actual native discovery, physical slot and P1 conversion,
    # including duplicate-name occurrences in descriptor order.
    record = parse_ben5k(data)
    channel = record.value_channels[column]
    assert len(record.value_channels) == 14
    assert channel.name == evidence["name"]
    assert channel.slot.word_index == evidence["physical_word"]
    assert channel.descriptor_raw == data[d:d + 58]
    assert channel.descriptor_raw[53] == evidence["descriptor"]["logical_word"]
    np.testing.assert_array_equal(record.raw_values(channel), raw)
    np.testing.assert_array_equal(record.engineering_values(channel), corrected)
    np.testing.assert_allclose(record.engineering_values(channel), expected, rtol=3e-8, atol=1e-9)
    assert has_supported_fast_ac_configuration(data, read_header(data))


def test_bphe_native_mapping_keeps_duplicate_names_and_physical_provenance(root):
    data, _, _ = _bphe(root)
    record = parse_ben5k(data)
    assert len(record.value_channels) == 14
    assert [c.slot.word_index for c in record.value_channels] == [c["physical_word"] for c in BPHE["channels"]]
    assert record.value_channels[7].name == record.value_channels[8].name == "YGPN/BBTU2 VR"
    assert record.value_channels[7].channel_id != record.value_channels[8].channel_id
    normalized = to_disturbance_record(record, source_file="bphe.ben", nominal_frequency_hz=50)
    assert "YGPN/BBTU2 VR" in normalized.waveform_data
    assert "YGPN/BBTU2 VR_1" in normalized.waveform_data
    assert not np.array_equal(normalized.waveform_data["YGPN/BBTU2 VR"], normalized.waveform_data["YGPN/BBTU2 VR_1"])
    ir = record.value_channel("YGPN/BBTU2 IR")
    assert ir.slot.word_index == 15
    correct_raw = np.array([struct.unpack_from(">h", data, BPHE["payload_offset"] + 2 * 15)[0]], dtype=np.int16)
    assert record.engineering_values(ir)[0] == fast_ac_engineering_values(correct_raw, ir.scale)[0]
    provenance = next(d.message for d in record.diagnostics if d.code == "ben5k_bphe_reviewed_physical_mapping")
    assert "0x1388/20/15" in provenance


def test_bphe_standalone_decoder_uses_discovered_physical_word(root):
    data, _, _ = _bphe(root)
    header = read_header(data)
    analog, _ = read_channel_descriptors(data, header)
    evidence = next(c for c in BPHE["channels"] if c["name"] == "YGPN/BBTU2 IR")
    ir = next(c for c in analog if c.name == evidence["name"])
    assert ir.physical_word_index == evidence["physical_word"]
    values, _ = decode_samples(data, header, [ir], [])
    assert values[0, 0] == pytest.approx(.2116712064, rel=1e-7)


@pytest.mark.parametrize("word", [0, 32767, 65535])
def test_bphe_mapping_does_not_depend_on_voltage_or_current_amplitude(root, word):
    original, _, _ = _bphe(root)
    data = bytearray(original)
    data[BPHE["payload_offset"]:] = struct.pack(">H", word) * (1148 * BPHE["words"])
    record = parse_ben5k(bytes(data))
    assert len(record.value_channels) == 14
    assert [c.slot.word_index for c in record.value_channels] == [c["physical_word"] for c in BPHE["channels"]]


def test_bphe_inventory_conflicts_and_unreviewed_configuration_are_rejected(root):
    data, _, _ = _bphe(root)
    analog, _ = read_channel_descriptors(data, read_header(data))
    with pytest.raises(BenStructureError, match="inventory"):
        bphe_physical_words(analog[:-1], 24)
    changed = bytearray(data)
    changed[0x354 + 4] = ord("Z")
    with pytest.raises(BenUnsupportedVariantError):
        parse_ben5k(bytes(changed))


def test_bphe_real_import_stored_arrays_api_waveforms_cursors_peaks_and_gates(root, settings):
    data, cfg, dat = _bphe(root)
    path = _original(root, BPHE["files"][0]["name"], BPHE["files"][0]["sha256"])[0]
    provided = BenProvider(ben5k_experimental_enabled=True).load(path)
    expected = {}
    for i, c in enumerate(BPHE["channels"]):
        name = c["name"] + (f"_{c['occurrence']}" if c["occurrence"] else "")
        expected[name] = dat[:, i + 2] * cfg.analog_defs[i].a + cfg.analog_defs[i].b
    assert len(expected) == 14
    assert list(provided.waveform_data.columns) == ["time", *expected]
    with TestClient(create_app(replace(settings, ben5k_experimental_enabled=True))) as client:
        base = "/api/v1/workspaces/ws-bphe-p2"
        response = client.post(f"{base}/sources", files={"ben_file": (path.name, data, "x")})
        assert response.status_code == 201, response.text
        source = response.json()
        sid = source["source_id"]
        assert source["sample_count"] == 1148
        url = f"{base}/sources/{sid}"
        active = client.app.state.workspace_registry.get("ws-bphe-p2", sid)
        assert [c.name for c in active.metadata.analog_channels] == list(expected)
        for c in active.record.analog_channels:
            assert c.calibration_authority.status == "unverified"
            assert c.calibration_authority.transform_id == "ben5k_v2_fast_ac_s12_gain_sqrt2_zero_offset"
        cursor = client.post(f"{url}/cursor-values", json={
            "analog_channel_names": list(expected), "cursor_a_time": 0, "cursor_b_time": 0.1,
        })
        assert cursor.status_code == 200, cursor.text
        cursors = {c["channel_name"]: c for c in cursor.json()["channels"]}
        peaks = client.post(f"{url}/peak-values", json={
            "requests": [{"channel_name": name, "mode": mode} for name in expected for mode in ["min", "max"]],
            "start_time": 0, "end_time": 1147 / 5000,
        })
        assert peaks.status_code == 200, peaks.text
        peak_values = {(p["channel_name"], p["mode"]): p for p in peaks.json()["results"]}
        for name, values in expected.items():
            np.testing.assert_allclose(provided.waveform_data[name], values, rtol=3e-8, atol=1e-9)
            np.testing.assert_allclose(active.record.waveform_data[name], values, rtol=3e-8, atol=1e-9)
            wave = client.get(f"{url}/waveform", params={"channel_name": name, "unit_mode": "engineering"})
            assert wave.status_code == 200, wave.text
            assert wave.json()["representation"] == "full_resolution"
            np.testing.assert_allclose(wave.json()["values"], values, rtol=3e-8, atol=1e-9)
            assert cursors[name]["a_value"] == pytest.approx(values[0], rel=3e-8, abs=1e-9)
            assert cursors[name]["b_value"] == pytest.approx(values[500], rel=3e-8, abs=1e-9)
            for mode, value in [("min", values.min()), ("max", values.max())]:
                assert peak_values[name, mode]["value"] == pytest.approx(value, rel=3e-8, abs=1e-9)
        for name in ["YGPN/BBTU1 VR", "YGPN/BBTU2 IR"]:
            wave = client.get(f"{url}/waveform", params={"channel_name": name, "unit_mode": "per_unit"})
            assert wave.status_code == 200, wave.text
            assert wave.json()["per_unit_status"] == "calibration_unavailable"


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
