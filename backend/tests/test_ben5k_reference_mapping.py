"""Exact October BEN5K physical-column goldens, not calibration goldens.

Owner recordings are immutable and uncommitted. Supply --ben-reference-dir.
Expected columns are pinned independently of the classifier under test; signed
packed samples are read directly with struct, then projected by the approved P1
zero-offset Fast AC contract. Original mapping hashes remain unchanged.
"""

from dataclasses import replace
from functools import cache
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.normalize import to_disturbance_record
from app.providers.ben.provider import BenProvider


pytestmark = pytest.mark.ben_reference
MANIFEST = json.loads((Path(__file__).parent / "fixtures/ben/ben5k_physical_mapping.json").read_text())
RECORDS = {r["id"]: r for r in MANIFEST["records"]}
CHANNELS = [(r["id"], c) for r in RECORDS.values() for c in r["channels"]]


@pytest.fixture(scope="module")
def mapping_reference_root(request):
    configured = request.config.getoption("--ben-reference-dir")
    if not configured:
        pytest.skip("October BEN5K owner files require --ben-reference-dir")
    root = Path(configured)
    assert root.is_dir(), f"BEN reference directory does not exist: {root}"
    return root


@cache
def _original(root, record_id):
    spec = RECORDS[record_id]
    candidates = sorted(root.rglob(spec["name"]))
    if not candidates:
        pytest.skip(f"October BEN5K reference not found: {spec['name']}")
    for path in candidates:
        data = path.read_bytes()
        if len(data) == spec["size"] and hashlib.sha256(data).hexdigest() == spec["sha256"]:
            return path, data
    pytest.fail(f"Found {spec['name']} but no file matches its original size and SHA-256")


@cache
def _parsed(root, record_id):
    path, data = _original(root, record_id)
    record = parse_ben5k(data)
    normalized = to_disturbance_record(record, source_file=str(path), nominal_frequency_hz=50)
    return record, normalized


def _golden_values(data, spec, channel):
    # Independent scalar binary reads, not extract_raw_matrix/classify_channels.
    words = [data[pos:pos + 2] for pos in range(
        spec["payload_offset"] + 2 * channel["physical_word_index"],
        len(data), 2 * spec["words_per_sample"],
    )]
    assert len(words) == spec["sample_count"]
    assert hashlib.sha256(b"".join(words)).hexdigest() == channel["packed_words_sha256"]
    raw = np.array([struct.unpack(">h", word)[0] for word in words], dtype=np.int16)
    descriptor = channel["descriptor_offset"]
    assert data[descriptor + 53] == channel["logical_word_index"]
    gain, offset = struct.unpack_from("<ff", data, descriptor + 28)
    assert offset == 0.0
    return raw, (raw.astype(np.int32) >> 4).astype(float) * gain * math.sqrt(2), gain, offset


@pytest.mark.parametrize("record_id,channel", CHANNELS, ids=[f"{r}-{c['name']}" for r, c in CHANNELS])
def test_every_channel_uses_its_pinned_physical_payload(mapping_reference_root, record_id, channel):
    _, data = _original(mapping_reference_root, record_id)
    record, normalized = _parsed(mapping_reference_root, record_id)
    raw, expected, gain, offset = _golden_values(data, RECORDS[record_id], channel)
    actual = record.value_channel(channel["name"])
    assert actual.slot.word_index == channel["physical_word_index"]
    np.testing.assert_array_equal(record.raw_values(actual), raw)
    np.testing.assert_array_equal(record.engineering_values(actual), expected)
    np.testing.assert_array_equal(normalized.waveform_data[channel["name"]], expected)
    assert (actual.scale, actual.offset) == (gain, offset)
    unit = "kV" if data[channel["descriptor_offset"]] == 0 else "kA"
    assert actual.unit == unit
    metadata = next(c for c in normalized.analog_channels if c.name == channel["name"])
    assert metadata.unit == unit
    assert metadata.measurement_side == "unknown"
    assert metadata.primary_ratio is None and metadata.secondary_ratio is None
    assert metadata.calibration_authority.status == "unverified"
    assert metadata.calibration_authority.transform_id == "ben5k_v2_fast_ac_s12_gain_sqrt2_zero_offset"


@pytest.mark.parametrize("record_id", RECORDS)
def test_all_real_channels_reach_provider_api_cursors_peaks_and_calculation(
    mapping_reference_root, settings, record_id,
):
    spec = RECORDS[record_id]
    path, data = _original(mapping_reference_root, record_id)
    assert sum(c["physical_word_index"] != c["logical_word_index"] for c in spec["channels"]) == spec["affected_channels"]
    expected = {c["name"]: _golden_values(data, spec, c)[1] for c in spec["channels"]}
    provided = BenProvider(ben5k_experimental_enabled=True).load(path)
    with TestClient(create_app(replace(settings, ben5k_experimental_enabled=True))) as client:
        base = f"/api/v1/workspaces/ws-map-{record_id}"
        response = client.post(f"{base}/sources", files={"ben_file": (spec["name"], data, "x")})
        assert response.status_code == 201, response.text
        source = response.json()
        assert source["sample_count"] == spec["sample_count"]
        sid = source["source_id"]
        url = f"{base}/sources/{sid}"
        active = client.app.state.workspace_registry.get(f"ws-map-{record_id}", sid)
        assert set(expected) == {c.name for c in active.metadata.analog_channels}
        cursor = client.post(f"{url}/cursor-values", json={
            "analog_channel_names": list(expected), "cursor_a_time": 0, "cursor_b_time": 0.5,
        })
        assert cursor.status_code == 200, cursor.text
        cursors = {c["channel_name"]: c for c in cursor.json()["channels"]}
        peak = client.post(f"{url}/peak-values", json={
            "requests": [{"channel_name": name, "mode": mode} for name in expected for mode in ["min", "max"]],
            "start_time": 0, "end_time": (spec["sample_count"] - 1) / 5000,
        })
        assert peak.status_code == 200, peak.text
        peaks = {(p["channel_name"], p["mode"]): p for p in peak.json()["results"]}
        for name, values in expected.items():
            np.testing.assert_array_equal(provided.waveform_data[name], values)
            np.testing.assert_array_equal(active.record.waveform_data[name], values)
            wave = client.get(f"{url}/waveform", params={"channel_name": name, "unit_mode": "engineering"})
            assert wave.status_code == 200, wave.text
            assert wave.json()["representation"] == "full_resolution"
            np.testing.assert_array_equal(wave.json()["values"], values)
            assert cursors[name]["a_value"] == values[0]
            assert cursors[name]["b_value"] == values[2500]
            assert peaks[name, "min"]["value"] == float(values.min())
            assert peaks[name, "max"]["value"] == float(values.max())
        # The same corrected Current numerator reaches exploratory calculation.
        name = "KTBR2 IR" if record_id == "permas_jaya" else "SDAI2 IB"
        calculation = client.post(f"{base}/calculated-channels", json={
            "name": "Mapped current polarity", "operation": "reverse_polarity",
            "inputs": [{"kind": "source", "source_id": sid, "channel_name": name}],
        })
        assert calculation.status_code == 201, calculation.text
        cid = calculation.json()["id"]
        wave = client.get(f"{base}/calculated-channels/{cid}/waveform")
        assert wave.status_code == 200, wave.text
        np.testing.assert_array_equal(wave.json()["values"], -expected[name])
        blocked = client.get(f"{url}/waveform", params={"channel_name": name, "unit_mode": "per_unit"})
        assert blocked.status_code == 200, blocked.text
        assert blocked.json()["per_unit_status"] == "calibration_unavailable"
        for name, values in expected.items():
            np.testing.assert_array_equal(active.record.waveform_data[name], values)
