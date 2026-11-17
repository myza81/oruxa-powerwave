"""P3 class dispatch, physical provenance and independent GPTH Slow export parity."""
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
from app.providers.ben.parser import parse_ben, parse_ben_experimental
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.legacy_ben5k.engineering import Ben5kRecord
from app.providers.ben.legacy_ben5k.gpth_slow import parse_gpth_slow, _read_catalog
from app.providers.ben.model import BenChannelKind, BenRecordClass
from app.providers.ben.normalize import to_disturbance_record, normalized_names
from app.providers.ben.provider import BenProvider
from app.providers.comtrade import _parse_cfg
from app.domain.physical_calibration import evaluate_calibration_eligibility

EVIDENCE = json.loads((Path(__file__).parent / "fixtures/ben/gpth_2022_legacy_slow.json").read_text())


def _fixture(payload=None):
    if payload is None:
        payload = np.arange(32 * 23, dtype=np.int16).reshape(32, 23)
    header = bytearray.fromhex(EVIDENCE["header_hex"])
    struct.pack_into("<I", header, 0x58, min(10, len(payload)))
    struct.pack_into("<I", header, 0x5C, len(payload))
    struct.pack_into("<I", header, 0x7A, len(payload) - 1)
    return bytes(header) + bytes.fromhex(EVIDENCE["configuration_hex"]) + payload.astype(">i2").tobytes()


def _decode(data):
    return parse_ben_experimental(data, allow_legacy_ben5k=True)


def _assert_printed_gain_precision(actual, expected, raw):
    # Original CFG gains print 10 decimal places; half of the last place,
    # propagated through each signed count, bounds coefficient-rounding error.
    assert np.all(np.abs(actual - expected) <= np.abs(raw) * 5e-11 + 1e-9)


def test_slow_dispatch_recovers_complete_calculated_inventory_and_keeps_legacy_gates():
    data = _fixture()
    record = _decode(data)
    assert not isinstance(record, Ben5kRecord)  # P1 Fast projection cannot run.
    assert record.header.record_class == BenRecordClass.BEN5K_LEGACY
    assert record.header.record_class_code == 1
    assert len(record.value_channels) == len(record.digital_channels) == 20
    assert all(c.kind == BenChannelKind.CALCULATED for c in record.value_channels)
    assert [c.name for c in record.value_channels] == [c["name"] for c in EVIDENCE["analog"]]
    assert [c.slot.word_index for c in record.value_channels] == [c["word"] for c in EVIDENCE["analog"]]
    assert not record.sample_words.flags.writeable
    normalized = to_disturbance_record(record, source_file="gpth.ben", nominal_frequency_hz=50)
    assert normalized.timing_info.time_basis == "unknown"
    assert normalized.timing_info.start_time.tzinfo is None
    assert {c.unit for c in normalized.analog_channels} == {"Hz", "MW"}
    authorities = [c.calibration_authority for c in normalized.analog_channels]
    assert all(a.status == "unverified" and a.transform_id == "ben5k_v1_raw_s16_linear_scale_offset" for a in authorities)
    assert not evaluate_calibration_eligibility(authorities, "engineering_calculation").eligible


@pytest.mark.parametrize("column", range(20), ids=[c["name"] for c in EVIDENCE["analog"]])
def test_independent_original_scalar_vectors_including_negative_power_and_frequency_offset(column):
    evidence = EVIDENCE["analog"][column]
    payload = np.zeros((1402, 23), dtype=np.int16)
    for sample in evidence["samples"]:
        payload[sample["index"], evidence["word"]] = sample["raw"]
    record = _decode(_fixture(payload))
    channel = record.value_channels[column]
    assert channel.channel_id == evidence["id"]
    assert channel.descriptor_raw.hex() == evidence["raw_hex"]
    assert channel.invalid_raw_value is None
    indices = [s["index"] for s in evidence["samples"]]
    raw = np.array([s["raw"] for s in evidence["samples"]], dtype=np.int64)
    np.testing.assert_array_equal(record.raw_values(channel)[indices], raw)
    _assert_printed_gain_precision(record.engineering_values(channel)[indices],
        np.array([s["engineering"] for s in evidence["samples"]]), raw)


def test_full_signed_words_low_bits_and_offsets_are_preserved_without_fast_transform():
    counts = np.array([-32768, -32767, -17, -16, -15, -1, 0, 1, 15, 16, 17, 2048, 32767])
    payload = np.zeros((len(counts), 23), dtype=np.int16)
    payload[:, 0] = payload[:, 2] = counts
    record = _decode(_fixture(payload))
    for name, gain, bias in [("FREQ UR TBIN 2", 0.0004882813, 50), ("POWER TBIN 1", 0.3217231333, 0)]:
        c = record.value_channel(name)
        np.testing.assert_array_equal(record.raw_values(c), counts)
        _assert_printed_gain_precision(record.engineering_values(c), counts * gain + bias, counts)


def test_physical_frames_address_every_channel_independently_of_constant_original_columns():
    payload = (np.arange(32 * 23).reshape(32, 23) - 16000).astype(np.int16)
    record = _decode(_fixture(payload))
    for c, evidence in zip(record.value_channels, EVIDENCE["analog"]):
        np.testing.assert_array_equal(record.raw_values(c), payload[:, evidence["word"]])
    for c, evidence in zip(record.digital_channels, EVIDENCE["digital"]):
        assert c.source_channel_id == evidence["id"]
        assert c.name == evidence["name"]  # includes original trailing space.
        assert (c.slot.word_index, c.slot.bit) == (evidence["word"], evidence["bit"])


@pytest.mark.parametrize("byte,value", [(0x3C, 0), (0x3C, 2), (4, 0x29), (6, 2), (14, 6), (0, 2), (0x7E8, 90)])
def test_slow_profile_refuses_other_classes_versions_and_configuration_changes(byte, value):
    data = bytearray(_fixture())
    data[byte] = value
    with pytest.raises(BenUnsupportedVariantError):
        parse_gpth_slow(bytes(data))


def test_opt_in_and_fast_boundary_cannot_accept_slow_as_an_empty_import():
    data = _fixture()
    for parser in (parse_ben, parse_ben5k):
        with pytest.raises(BenUnsupportedVariantError):
            parser(data)
    changed = bytearray(data)
    changed[0x3C] = 0
    with pytest.raises(BenUnsupportedVariantError, match="no supported recorded channels"):
        _decode(bytes(changed))
    changed[0x3C] = 2
    with pytest.raises(BenUnsupportedVariantError, match="record class"):
        _decode(bytes(changed))


@pytest.mark.parametrize("position,value", [(0x7DE, 1), (0x7E6, 0), (0x986, 16)])
def test_catalog_rejects_wrong_addresses_unknown_units_and_conflicting_binary_bits(position, value):
    data = bytearray(_fixture())
    data[position] = value
    with pytest.raises((BenStructureError, BenUnsupportedVariantError)):
        _read_catalog(bytes(data), EVIDENCE["payload_offset"] - 10, 23)


def test_catalog_rejects_truncation_and_header_acquisition_conflicts():
    data = _fixture()
    with pytest.raises(BenStructureError):
        _read_catalog(data, EVIDENCE["payload_offset"] - 30, 23)
    changed = bytearray(data)
    struct.pack_into("<I", changed, 0x54, 5000_000)
    with pytest.raises(BenStructureError):
        _decode(bytes(changed))


@pytest.fixture(scope="module")
def original(request):
    configured = request.config.getoption("--ben-reference-dir")
    if not configured:
        pytest.skip("Original GPTH Slow parity requires --ben-reference-dir")
    root = Path(configured) / EVIDENCE["relative_directory"]
    paths = [root / f["name"] for f in EVIDENCE["files"]]
    for p, spec in zip(paths, EVIDENCE["files"]):
        assert p.is_file(), f"Original GPTH Slow reference missing: {p}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == spec["sha256"]
    return paths, _parse_cfg(paths[1]), pd.read_csv(paths[2], header=None, comment="\x1a").dropna(how="all").to_numpy(dtype=np.int64)


@pytest.mark.ben_reference
def test_all_28040_original_raw_and_engineering_values_and_28040_binary_states(original):
    paths, cfg, dat = original
    record = _decode(paths[0].read_bytes())
    assert record.sample_count == 1402
    for c, e in zip(record.value_channels, EVIDENCE["analog"]):
        d = cfg.analog_defs[e["export_column"]]
        assert c.name == d.ch_id and c.unit == d.uu
        raw = dat[:, 2 + e["export_column"]]
        np.testing.assert_array_equal(record.raw_values(c), raw)
        assert hashlib.sha256(raw.astype('<i2').tobytes()).hexdigest() == e["raw_sha256"]
        expected = raw * d.a + d.b
        assert hashlib.sha256(expected.astype('<f8').tobytes()).hexdigest() == e["engineering_sha256"]
        _assert_printed_gain_precision(record.engineering_values(c), expected, raw)
    for c, e in zip(record.digital_channels, EVIDENCE["digital"]):
        expected = dat[:, 22 + e["export_column"]]
        np.testing.assert_array_equal(record.digital_states(c), expected)
        assert hashlib.sha256(expected.astype('u1').tobytes()).hexdigest() == e["states_sha256"]


@pytest.mark.ben_reference
def test_original_import_stored_engineering_api_waveforms_both_cursors_peaks_and_authority(original, settings):
    paths, cfg, dat = original
    provided = BenProvider(ben5k_experimental_enabled=True).load(paths[0])
    record = _decode(paths[0].read_bytes())
    names, _ = normalized_names(record)
    with TestClient(create_app(replace(settings, ben5k_experimental_enabled=True))) as client:
        base = "/api/v1/workspaces/ws-gpth-slow-p3"
        response = client.post(f"{base}/sources", files={"ben_file": (paths[0].name, paths[0].read_bytes(), "x")})
        assert response.status_code == 201, response.text
        sid = response.json()["source_id"]
        url = f"{base}/sources/{sid}"
        active = client.app.state.workspace_registry.get("ws-gpth-slow-p3", sid)
        assert len(active.record.analog_channels) == 20
        assert all(c.calibration_authority.status == "unverified" for c in active.record.analog_channels)
        cursors = client.post(f"{url}/cursor-values", json={
            "analog_channel_names": names, "cursor_a_time": 0, "cursor_b_time": 20,
        })
        assert cursors.status_code == 200, cursors.text
        cursor_values = {c["channel_name"]: c for c in cursors.json()["channels"]}
        peaks = client.post(f"{url}/peak-values", json={
            "requests": [{"channel_name": name, "mode": mode} for name in names for mode in ("min", "max")],
            "start_time": 0, "end_time": 1401 / 20,
        })
        assert peaks.status_code == 200, peaks.text
        peak_values = {(p["channel_name"], p["mode"]): p for p in peaks.json()["results"]}
        for name, e in zip(names, EVIDENCE["analog"]):
            definition = cfg.analog_defs[e["export_column"]]
            raw = dat[:, 2 + e["export_column"]]
            expected = raw * definition.a + definition.b
            for actual in (provided.waveform_data[name], active.record.waveform_data[name]):
                _assert_printed_gain_precision(np.asarray(actual), expected, raw)
            wave = client.get(f"{url}/waveform", params={"channel_name": name, "unit_mode": "engineering"})
            assert wave.status_code == 200, wave.text
            assert wave.json()["representation"] == "full_resolution"
            _assert_printed_gain_precision(np.array(wave.json()["values"]), expected, raw)
            assert cursor_values[name]["a_value"] == pytest.approx(expected[0], abs=2e-7)
            assert cursor_values[name]["b_value"] == pytest.approx(expected[400], abs=2e-7)
            for mode, value in (("min", expected.min()), ("max", expected.max())):
                assert peak_values[name, mode]["value"] == pytest.approx(value, abs=2e-7)
