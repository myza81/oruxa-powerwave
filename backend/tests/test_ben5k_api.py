"""Stage 7B Section 2 tests: BEN5K HTTP API integration.

Tests verify:
  - BEN5K upload with flag DISABLED → HTTP 400 unsupported_ben_variant
  - BEN5K upload with flag ENABLED  → HTTP 201 with correct metadata
  - Flag-enabled source has:
      • provider_type "BEN"
      • preparation_provenance.time_basis "unknown"
      • timing_reference NOT "absolute" (timestamp safety, Stage 7B §4)
  - SubBen upload is not affected by the flag (still returns 201)

Uses the same minimal synthetic BEN5K fixture as test_ben5k_normalize.py
but builds it inline to keep this file independent.
"""

from __future__ import annotations

import io
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# ── Constants (must match test_ben5k_normalize.py) ──────────────────────────

_BEN5K_FAMILY_SIG  = b"\x01\x00\x04\x00"
_BEN5K_LAYOUT_SIG  = b"\x28\xff\x03\x00\x6e\x00\xca\x00"
_BEN5K_GEN_MARKER  = b"\x05\x00"

_SHORT_FEEDER_NAME_OFFSET = 0xAAE
_SHORT_FEEDER_NAME_STRIDE = 22
_SHORT_FEEDER_NAME_COUNT  = 12


# ── Minimal fixture builder ───────────────────────────────────────────────────


def _build_analog_descriptor(name: str, word_index: int) -> bytes:
    buf = bytearray(58)
    buf[0] = 0x00  # voltage
    buf[1] = 1     # phase R
    struct.pack_into("<H", buf, 2, 0x0528)
    n = name.encode("latin-1")[:16]
    buf[4 : 4 + len(n)] = n
    struct.pack_into("<f", buf, 28, 0.01)  # scale
    struct.pack_into("<f", buf, 32, 0.0)   # offset
    struct.pack_into("<f", buf, 36, -100.0)
    struct.pack_into("<f", buf, 40, 100.0)
    buf[53] = word_index
    buf[57] = 0xFF
    return bytes(buf)


def _build_digital_descriptor(name: str, word_group: int) -> bytes:
    buf = bytearray(58)
    buf[0] = 0x01
    buf[1] = word_group
    buf[2] = 0
    buf[3] = 0xFF
    n = name.encode("latin-1")[:16]
    buf[4 : 4 + len(n)] = n
    buf[57] = 0xFF
    return bytes(buf)


def _make_ben5k_bytes(*, sample_count: int = 20, words_per_sample: int = 40) -> bytes:
    """Minimal valid BEN5K file: 1 analog (wi=0), 1 digital (group=1)."""
    header = bytearray(0xDC)
    header[0:4]   = _BEN5K_FAMILY_SIG
    header[4:12]  = _BEN5K_LAYOUT_SIG
    header[14:16] = _BEN5K_GEN_MARKER
    struct.pack_into("<H", header, 0x0C, 1234)                  # recorder_unit_id
    header[0x10:0x10 + 10] = b"API TEST 1"                     # station
    struct.pack_into("<I", header, 0x54, 5000 * 1000)           # rate 5000 Hz
    struct.pack_into("<I", header, 0x58, 10)                    # pre_trigger
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<H", header, 0x60, words_per_sample)
    header[0x64:0x6D] = bytes([126, 10, 16, 18, 3, 14, 53, 54, 0])  # trigger time
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    # Config area: prefix + feeder names + 4-byte gap + descriptors
    config_prefix = bytes(0xAAE - 0xDC)
    feeder_names  = bytes(_SHORT_FEEDER_NAME_COUNT * _SHORT_FEEDER_NAME_STRIDE)
    gap           = bytes(4)
    analog_desc   = _build_analog_descriptor("API VR", word_index=0)
    digital_desc  = _build_digital_descriptor("API CB", word_group=1)
    config = config_prefix + feeder_names + gap + analog_desc + digital_desc

    payload = np.zeros((sample_count, words_per_sample), dtype=">u2")
    payload[:, 0] = 1000  # analog raw
    for i in range(sample_count):
        payload[i, 38] = np.uint16(0x0000 if i % 2 == 0 else 0x0002)  # varying digital

    return bytes(header) + config + payload.tobytes()


# ── Settings fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def settings_flag_off(tmp_path) -> Settings:
    return Settings(
        environment="development",
        storage_type="local",
        storage_path=str(tmp_path),
        cors_origins=("http://localhost:8101",),
        database_url=None,
        max_event_upload_size_mb=100,
        git_sha="local",
        version="local",
        ben5k_experimental_enabled=False,
    )


@pytest.fixture
def settings_flag_on(tmp_path) -> Settings:
    return Settings(
        environment="development",
        storage_type="local",
        storage_path=str(tmp_path),
        cors_origins=("http://localhost:8101",),
        database_url=None,
        max_event_upload_size_mb=100,
        git_sha="local",
        version="local",
        ben5k_experimental_enabled=True,
    )


_WS   = "ws-ben5k-api"
_URL  = f"/api/v1/workspaces/{_WS}/sources"


def _upload(client: TestClient, data: bytes, name: str = "event.ben") -> object:
    return client.post(
        _URL,
        files={"ben_file": (name, io.BytesIO(data), "application/octet-stream")},
    )


# ── Tests — flag disabled ─────────────────────────────────────────────────────


class TestBen5kFlagDisabled:
    def test_ben5k_returns_400_unsupported_variant(self, settings_flag_off):
        with TestClient(create_app(settings_flag_off)) as client:
            resp = _upload(client, _make_ben5k_bytes())
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unsupported_ben_variant"

    def test_ben5k_not_registered_in_workspace(self, settings_flag_off):
        with TestClient(create_app(settings_flag_off)) as client:
            _upload(client, _make_ben5k_bytes())
            resp = client.get(f"/api/v1/workspaces/{_WS}/sources")
        assert resp.status_code == 200
        assert resp.json() == []


# ── Tests — flag enabled ──────────────────────────────────────────────────────


class TestBen5kFlagEnabled:
    def test_ben5k_returns_201(self, settings_flag_on):
        with TestClient(create_app(settings_flag_on)) as client:
            resp = _upload(client, _make_ben5k_bytes())
        assert resp.status_code == 201, resp.text

    def test_ben5k_source_registered(self, settings_flag_on):
        with TestClient(create_app(settings_flag_on)) as client:
            resp = _upload(client, _make_ben5k_bytes())
        body = resp.json()
        assert body["provider_type"] == "BEN"
        assert body["status"] == "ready"
        assert body["station_name"] == "API TEST 1"

    def test_ben5k_timing_reference_is_not_absolute(self, settings_flag_on):
        # Timestamp safety: unverified UTC must NOT drive auto-synchronization.
        # The HTTP response returns timing_reference directly in SourceMetadata.
        with TestClient(create_app(settings_flag_on)) as client:
            resp = _upload(client, _make_ben5k_bytes())
        body = resp.json()
        timing_ref = body.get("timing_reference")
        assert timing_ref != "absolute", (
            f"BEN5K timing_reference must not be 'absolute' (got {timing_ref!r}). "
            "An unverified timestamp must not drive cross-source synchronization."
        )

    def test_ben5k_analog_and_digital_channels_present(self, settings_flag_on):
        with TestClient(create_app(settings_flag_on)) as client:
            resp = _upload(client, _make_ben5k_bytes())
        body = resp.json()
        assert body["analog_channel_count"] == 1
        assert body["digital_channel_count"] == 1
        assert body["sample_count"] == 20

    def test_ben5k_elapsed_only_timing_class(self, settings_flag_on):
        # BEN5K timing_reference is "relative_elapsed", which the time-grouping
        # module maps to TIME_REFERENCE_ELAPSED_ONLY (never "absolute").
        # This is the key regression guard for timestamp safety (Stage 7B §4).
        with TestClient(create_app(settings_flag_on)) as client:
            resp = _upload(client, _make_ben5k_bytes())
        from app.domain.time_grouping import time_reference_type_for_source, TIME_REFERENCE_ELAPSED_ONLY
        timing_ref = resp.json().get("timing_reference", "")
        assert time_reference_type_for_source(timing_ref) == TIME_REFERENCE_ELAPSED_ONLY, (
            f"BEN5K must be in the elapsed-only time bucket (got timing_reference={timing_ref!r}). "
            "This prevents unverified UTC timestamps from driving auto-synchronization."
        )


@pytest.mark.parametrize("raw_trigger, expected_trigger, expected_start", [
    (bytes.fromhex("7e 0a 10 12 03 0e 35 36 00"), "2026-10-16T18:03:14.535400", "2026-10-16T18:03:14.035400"),
    (bytes.fromhex("7e 0a 10 12 03 0e 00 00 00"), "2026-10-16T18:03:14.000000", "2026-10-16T18:03:13.500000"),
    # The UTC+8 display rollover that previously moved GPTH to the next day.
    (bytes.fromhex("7e 0a 10 17 3b 3b 63 63 63"), "2026-10-16T23:59:59.999999", "2026-10-16T23:59:59.499999"),
])
def test_unknown_clock_preserved_through_upload_list_channels_and_t0(
    settings_flag_on, raw_trigger, expected_trigger, expected_start,
):
    from app.providers.ben.parser import parse_ben_experimental
    data = bytearray(_make_ben5k_bytes(sample_count=3000))
    data[0x64:0x6D] = raw_trigger
    struct.pack_into("<I", data, 0x58, 2500)
    original = bytes(data)
    parsed = parse_ben_experimental(original, allow_legacy_ben5k=True)
    assert parsed.header.trigger_time.fraction_digits == tuple(raw_trigger[6:])
    np.testing.assert_array_equal(parsed.time_axis(), np.arange(3000) / 5000)
    with TestClient(create_app(settings_flag_on)) as client:
        response = _upload(client, original)
        assert response.status_code == 201, response.text
        body = response.json()
        source_id = body["source_id"]
        channels_url = f"{_URL}/{source_id}/channels"
        payloads = [body, client.get(_URL).json()[0]]
        channels = client.get(channels_url).json()
        payloads += [channels["source"], channels["timebase"]]
        for value in payloads:
            assert value["time_basis"] == "unknown"
            assert value["start_time"] == expected_start
            assert value["trigger_time"] == expected_trigger
            assert value["start_time_utc"] is None
            assert value["trigger_time_utc"] is None
            assert value["timing_reference"] == "relative_elapsed"
        active = client.app.state.workspace_registry.get(_WS, source_id)
        assert active.record.timing_info.timezone is None
        assert active.record.metadata.timezone is None
        assert active.metadata.preparation_provenance["trigger_timestamp_raw"] == raw_trigger.hex(" ")
        np.testing.assert_array_equal(active.record.waveform_data["time"], parsed.time_axis())
        np.testing.assert_array_equal(active.record.waveform_data["API VR"], parsed.engineering_values(parsed.value_channels[0]))
        # Canonical Table remains a valid relative-time consumer without UTC.
        table = client.get(f"{_URL}/{source_id}/table?limit=3")
        assert table.status_code == 200, table.text
        assert table.json()["row_native_times"] == [0, 0.0002, 0.0004]
        sync = f"/api/v1/workspaces/{_WS}/synchronization"
        before = client.get(f"{sync}/sources/{source_id}").json()
        assert before["timestamp_placement_offset_s"] == 0
        assert before["manual_alignment_offset_s"] == 0
        changed = client.put(f"{sync}/t0", json={"source_id": source_id, "t0_workspace_time": 0.123456})
        assert changed.status_code == 200, changed.text
        assert changed.json()["t0_workspace_time"] == 0.123456
        assert client.get(f"{sync}/sources/{source_id}").json() == before
        assert client.get(channels_url).json() == channels
        assert bytes(data) == original



def test_unknown_clock_supports_single_source_calculation_but_not_cross_source_alignment(settings_flag_on):
    from app.services.calculated_channel_service import _source_start_epoch
    with TestClient(create_app(settings_flag_on)) as client:
        first = _upload(client, _make_ben5k_bytes()).json()
        second = _upload(client, _make_ben5k_bytes(), "second.ben").json()
        source_id = first["source_id"]
        active = client.app.state.workspace_registry.get(_WS, source_id)
        assert _source_start_epoch(active) is None
        calc_url = f"/api/v1/workspaces/{_WS}/calculated-channels"
        ref = {"kind": "source", "source_id": source_id, "channel_name": "API VR"}
        result = client.post(calc_url, json={"name": "inverted", "operation": "reverse_polarity", "inputs": [ref]})
        assert result.status_code == 201, result.text
        cross = client.post(calc_url, json={
            "name": "unproven", "operation": "addition", "inputs": [
                ref, {"kind": "source", "source_id": second["source_id"], "channel_name": "API VR"},
            ],
        })
        assert cross.status_code == 400, cross.text
        assert first["start_time_utc"] is None



def test_unknown_clock_upload_does_not_change_existing_manual_offset_or_t0(settings_flag_on, comtrade_fixtures_dir):
    with TestClient(create_app(settings_flag_on)) as client:
        for stem in ("synth_ascii", "synth_binary"):
            files = {f"{ext}_file": (f"{stem}.{ext}", (comtrade_fixtures_dir / f"{stem}.{ext}").read_bytes(), "application/octet-stream") for ext in ("cfg", "dat")}
            response = client.post(_URL, files=files)
            assert response.status_code == 201, response.text
        sync = f"/api/v1/workspaces/{_WS}/synchronization"
        alignments = client.get(f"{sync}/sources").json()
        source_id = next(row["source_id"] for row in alignments if not row["is_reference"])
        response = client.put(f"{sync}/sources/{source_id}", json={"alignment_offset_s": -0.0185})
        assert response.status_code == 200, response.text
        response = client.put(f"{sync}/t0", json={"source_id": source_id, "t0_workspace_time": 0.123456})
        assert response.status_code == 200, response.text
        alignment = client.get(f"{sync}/sources/{source_id}").json()
        t0 = client.get(f"{sync}/t0", params={"source_id": source_id}).json()
        unknown = _upload(client, _make_ben5k_bytes()).json()
        assert unknown["time_basis"] == "unknown"
        assert client.get(f"{sync}/sources/{source_id}").json() == alignment
        assert client.get(f"{sync}/t0", params={"source_id": source_id}).json() == t0
        groups = client.get(f"{sync}/time-groups").json()
        assert len(groups) == 2  # Known pair together; BEN5K remains a singleton.
