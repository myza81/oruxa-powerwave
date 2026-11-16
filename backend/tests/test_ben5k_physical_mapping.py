"""BEN5K adapter regression: classified physical slots reach every consumer.

These tests deliberately retain the existing packed-word scale/offset formula.
They establish channel identity, not absolute engineering calibration.
"""

from dataclasses import replace
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.normalize import to_disturbance_record
from test_ben5k_normalize import _build_analog_descriptor, _make_ben5k_fixture


def phantom_fixture(phantoms):
    """Known physical layout with zero, one, or two absent logical slots."""
    payload = np.zeros((200, 40), dtype=">u2")
    voltage = np.resize(np.array([-12000, 11000], dtype=np.int16), 200)
    current = np.resize(np.array([-512, -129, 0, 128, 511, 900], dtype=np.int16), 200)
    payload[:, 0] = voltage.astype(np.uint16)
    extra = b""
    slots = {"TBIN1 VR": 0}
    if phantoms:
        extra += _build_analog_descriptor("PHANTOM I", 1, type_byte=4)
        extra += _build_analog_descriptor("AFTER VR", 2)
        # Duplicate configured descriptors must not consume a physical slot.
        extra += _build_analog_descriptor("DUPLICATE VR", 2)
        payload[:, 1] = (-voltage).astype(np.uint16)
        slots["AFTER VR"] = 1
    physical = 2 if phantoms else 1
    if phantoms == 2:
        extra += _build_analog_descriptor("PHANTOM V", 3)
    descriptor = bytearray(_build_analog_descriptor("REAL IR", physical + phantoms, 0.125, 4))
    struct.pack_into("<f", descriptor, 32, 7.25)
    extra += descriptor
    slots["REAL IR"] = physical
    payload[:, physical] = current.astype(np.uint16)
    # Under the discarded logical index this is a different, voltage-like word.
    # It also supplies the existing classifier's second-phantom look-ahead.
    payload[:, physical + 1] = voltage.astype(np.uint16)
    payload[:, physical + 2] = (-voltage).astype(np.uint16)
    payload[:, 38] = np.resize(np.array([0xFFFF, 0xFFFE], dtype=np.uint16), 200)
    data = _make_ben5k_fixture(
        sample_count=200, pre_trigger=100, payload_words=payload,
        extra_analog_descriptors=extra,
    )
    return data, slots, current


@pytest.mark.parametrize("phantoms", [0, 1, 2])
def test_physical_slots_reach_raw_and_shared_normalized_values(phantoms):
    data, slots, current = phantom_fixture(phantoms)
    record = parse_ben5k(data)
    assert {c.name: c.slot.word_index for c in record.value_channels} == slots
    normalized = to_disturbance_record(record, source_file="mapping.ben", nominal_frequency_hz=50)
    channel = record.value_channel("REAL IR")
    np.testing.assert_array_equal(record.raw_values(channel), current)
    expected = current.astype(float) * 0.125 + 7.25
    np.testing.assert_array_equal(record.engineering_values(channel), expected)
    np.testing.assert_array_equal(normalized.waveform_data["REAL IR"], expected)
    assert (channel.scale, channel.offset, channel.unit) == (0.125, 7.25, "kA")
    assert channel.primary_rating is None and channel.secondary_rating is None
    assert normalized.analog_channels[-1].measurement_side == "unknown"
    np.testing.assert_array_equal(
        record.digital_states(record.digital_channels[0]), np.tile([0, 1], 100),
    )


@pytest.mark.parametrize("phantoms", [1, 2])
def test_mapping_propagates_through_upload_waveform_cursor_peak_and_calculation(settings, phantoms):
    data, _, current = phantom_fixture(phantoms)
    expected = current.astype(float) * 0.125 + 7.25
    with TestClient(create_app(replace(settings, ben5k_experimental_enabled=True))) as client:
        base = "/api/v1/workspaces/ws-mapping"
        response = client.post(f"{base}/sources", files={"ben_file": ("mapping.ben", data, "x")})
        assert response.status_code == 201, response.text
        sid = response.json()["source_id"]
        url = f"{base}/sources/{sid}"
        active = client.app.state.workspace_registry.get("ws-mapping", sid)
        np.testing.assert_array_equal(active.record.waveform_data["REAL IR"], expected)
        wave = client.get(f"{url}/waveform", params={"channel_name": "REAL IR", "unit_mode": "engineering"})
        assert wave.status_code == 200, wave.text
        np.testing.assert_array_equal(wave.json()["values"], expected)
        assert wave.json()["unit"] == "kA"
        cursors = client.post(f"{url}/cursor-values", json={
            "analog_channel_names": ["REAL IR"], "cursor_a_time": 0, "cursor_b_time": 1 / 5000,
        })
        assert cursors.status_code == 200, cursors.text
        assert cursors.json()["channels"][0]["a_value"] == expected[0]
        assert cursors.json()["channels"][0]["b_value"] == expected[1]
        peak = client.post(f"{url}/peak-values", json={
            "requests": [{"channel_name": "REAL IR", "mode": "max"}],
            "start_time": 0, "end_time": 199 / 5000,
        })
        assert peak.status_code == 200, peak.text
        assert peak.json()["results"][0]["value"] == float(expected.max())
        calculation = client.post(f"{base}/calculated-channels", json={
            "name": "Mapped current negated", "operation": "reverse_polarity",
            "inputs": [{"kind": "source", "source_id": sid, "channel_name": "REAL IR"}],
        })
        assert calculation.status_code == 201, calculation.text
        cid = calculation.json()["id"]
        calculated = client.get(f"{base}/calculated-channels/{cid}/waveform")
        assert calculated.status_code == 200, calculated.text
        np.testing.assert_array_equal(calculated.json()["values"], -expected)
        # Downstream requests do not mutate the imported engineering array.
        np.testing.assert_array_equal(active.record.waveform_data["REAL IR"], expected)
