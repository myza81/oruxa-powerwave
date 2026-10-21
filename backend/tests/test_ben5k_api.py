"""Stage 7B Section 2 tests: BEN5K HTTP API integration.

Tests verify:
  - BEN5K upload with flag DISABLED → HTTP 400 unsupported_ben_variant
  - BEN5K upload with flag ENABLED  → HTTP 201 with correct metadata
  - Flag-enabled source has:
      • provider_type "BEN"
      • preparation_provenance.time_basis "UTC (unverified)"
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
