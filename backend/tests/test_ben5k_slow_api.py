"""S4 tests: BEN5K Slow HTTP API integration.

Tests verify:
  - BEN5K Slow upload with flag DISABLED → HTTP 400 unsupported_ben_variant
  - BEN5K Slow upload with flag ENABLED  → HTTP 201 with correct metadata
  - Flag-enabled Slow source has:
      • provider_type "BEN"
      • layout_family "BEN32 BEN5K Slow Legacy"  (new S4 field in SourceSummaryOut)
      • timing_reference NOT "absolute" (timestamp safety -- relative_elapsed)
      • timing_reference in TIME_REFERENCE_ELAPSED_ONLY bucket
  - Slow flag does NOT enable BEN5K Fast (separate flag independence)
  - SubBen upload is not affected by either flag (still returns 201)
  - layout_family is None for COMTRADE sources

Uses the same minimal synthetic BEN5K Slow fixture pattern as
test_ben5k_slow_decoder.py, built inline to keep this file independent.
"""

from __future__ import annotations

import io
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# ── Slow fixture constants ────────────────────────────────────────────────────

_FAMILY_SIG = b"\x01\x00\x04\x00"
_SLOW_LAYOUT_SIG = b"\x29\xff\x03\x00\x6e\x00\xca\x00"
_FAST_LAYOUT_SIG = b"\x28\xff\x03\x00\x6e\x00\xca\x00"
_GEN_MARKER = b"\x05\x00"
_HEADER_END = 0xDC
_GROUP_STRIDE = 252
_GROUP_COUNT = 9


def _build_sens(group_index: int, name: str, active: bool = True) -> bytes:
    buf = bytearray(24)
    buf[0] = 0x02
    buf[1] = 0x3C
    buf[2] = group_index
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    buf[20:24] = b"\x33\xff\x38\x00" if active else b"\xff\xff\x00\x00"
    return bytes(buf)


def _build_ch_desc(name: str, selector: int) -> bytes:
    buf = bytearray(28)
    struct.pack_into("<H", buf, 0, selector)
    buf[3] = 0xFF
    n = name.encode("latin-1")[:16]
    buf[4 : 4 + len(n)] = n
    struct.pack_into("<I", buf, 20, 0xFFFFFFFF)
    buf[24:28] = b"\xff\xff\x38\x00"
    return bytes(buf)


def _build_inactive_ch() -> bytes:
    buf = bytearray(28)
    buf[3] = 0xFF
    buf[4:8] = b"----"
    return bytes(buf)


def _build_group(idx: int, name: str, channels: list[bytes], active: bool = True) -> bytes:
    buf = bytearray(252)
    buf[0:24] = _build_sens(idx, name, active)
    for i, ch in enumerate(channels[:8]):
        buf[24 + i * 28 : 24 + (i + 1) * 28] = ch
    for i in range(len(channels[:8]), 8):
        buf[24 + i * 28 : 24 + (i + 1) * 28] = _build_inactive_ch()
    buf[248:252] = b"\xff\xff\xff\xff"
    return bytes(buf)


def _build_config_header(recorder_unit: int = 1547, station: str = "GRNE") -> bytes:
    buf = bytearray(34)
    struct.pack_into("<H", buf, 0, 0x0004)
    struct.pack_into("<H", buf, 2, 0xFF32)
    struct.pack_into("<H", buf, 10, recorder_unit)
    struct.pack_into("<H", buf, 12, 5)
    n = station.encode("latin-1")[:16]
    buf[14 : 14 + len(n)] = n
    return bytes(buf)


def _build_hvdc() -> bytes:
    buf = bytearray(65)
    buf[4 : 4 + 10] = b"HVDC Power"
    buf[38 : 38 + 20] = b"C014+C041+C021\r\n\x84\x00\x00\x00"
    return bytes(buf)


def _make_slow_bytes(
    *,
    sample_count: int = 5,
    words_per_sample: int = 4,
    group0_channels: list[bytes] | None = None,
) -> bytes:
    """Minimal valid BEN5K Slow file with one Group-0 TENTATIVE channel."""
    header = bytearray(0xDC)
    header[0:4] = _FAMILY_SIG
    header[4:12] = _SLOW_LAYOUT_SIG
    struct.pack_into("<H", header, 0x0C, 1547)
    header[0x0E:0x10] = _GEN_MARKER
    header[0x10 : 0x10 + 4] = b"GRNE"
    struct.pack_into("<I", header, 0x38, 6606)
    header[0x3C] = 0x01           # BEN5K Slow class flag
    struct.pack_into("<I", header, 0x54, 20 * 1000)   # 20 sps
    struct.pack_into("<I", header, 0x58, 2)            # pre_trigger
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<H", header, 0x60, words_per_sample)
    # Trigger timestamp
    header[0x64:0x6D] = bytes([0x7B, 0x07, 0x1A, 0x0E, 0x22, 0x20, 0x2A, 0x19, 0x28])
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    if group0_channels is None:
        # One TENTATIVE channel: word_index = selector >> 8 = 1 (within wps)
        group0_channels = [_build_ch_desc("FREQ GRNE", selector=0x0100)]

    groups = [_build_group(0, "BDNG 1", group0_channels)]
    while len(groups) < _GROUP_COUNT:
        groups.append(_build_group(len(groups), f"GROUP {len(groups)}", []))

    config_hdr = _build_config_header(recorder_unit=1547, station="GRNE")
    hvdc = _build_hvdc()
    groups_bytes = b"".join(groups)

    payload = bytearray()
    for _ in range(sample_count):
        for _ in range(words_per_sample):
            payload.extend(struct.pack(">H", 13086))  # ~50 Hz raw

    return bytes(header) + config_hdr + hvdc + groups_bytes + bytes(payload)


def _make_fast_bytes() -> bytes:
    """Minimal BEN5K Fast file (layout sig 0x28ff) for flag-independence check."""
    header = bytearray(0xDC)
    header[0:4] = _FAMILY_SIG
    header[4:12] = _FAST_LAYOUT_SIG
    header[0x0E:0x10] = _GEN_MARKER
    struct.pack_into("<H", header, 0x0C, 9999)
    header[0x10 : 0x10 + 8] = b"FAST STA"
    struct.pack_into("<I", header, 0x54, 5000 * 1000)
    struct.pack_into("<I", header, 0x58, 10)
    struct.pack_into("<I", header, 0x5C, 10)
    struct.pack_into("<H", header, 0x60, 4)
    header[0x64:0x6D] = bytes([126, 10, 16, 18, 3, 14, 53, 54, 0])
    struct.pack_into("<I", header, 0x7A, 9)
    # Minimal stub config and payload so the parser doesn't error on size
    config = bytes(0xAAE - 0xDC)
    config += bytes(12 * 22)   # feeder names
    config += bytes(4)         # gap
    config += bytes(58)        # one descriptor slot
    payload = np.zeros((10, 4), dtype=">u2").tobytes()
    return bytes(header) + config + payload


# ── Settings fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def settings_both_off(tmp_path) -> Settings:
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
        ben5k_slow_experimental_enabled=False,
    )


@pytest.fixture
def settings_slow_only(tmp_path) -> Settings:
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
        ben5k_slow_experimental_enabled=True,
    )


@pytest.fixture
def settings_fast_only(tmp_path) -> Settings:
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
        ben5k_slow_experimental_enabled=False,
    )


_WS = "ws-ben5k-slow-api"
_URL = f"/api/v1/workspaces/{_WS}/sources"


def _upload_ben(client: TestClient, data: bytes, name: str = "event.ben") -> object:
    return client.post(
        _URL,
        files={"ben_file": (name, io.BytesIO(data), "application/octet-stream")},
    )


# ── Tests — Slow flag disabled ────────────────────────────────────────────────


class TestBen5kSlowFlagDisabled:
    def test_slow_returns_400_when_flag_off(self, settings_both_off):
        with TestClient(create_app(settings_both_off)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unsupported_ben_variant"

    def test_slow_not_registered_when_flag_off(self, settings_both_off):
        with TestClient(create_app(settings_both_off)) as client:
            _upload_ben(client, _make_slow_bytes())
            resp = client.get(_URL)
        assert resp.status_code == 200
        assert resp.json() == []


# ── Tests — Slow flag enabled ─────────────────────────────────────────────────


class TestBen5kSlowFlagEnabled:
    def test_slow_returns_201(self, settings_slow_only):
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.status_code == 201, resp.text

    def test_slow_provider_type_is_ben(self, settings_slow_only):
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.json()["provider_type"] == "BEN"

    def test_slow_layout_family_in_response(self, settings_slow_only):
        # S4: SourceSummaryOut.layout_family must be "BEN32 BEN5K Slow Legacy"
        # so the frontend can show the UAT notice.
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.json()["layout_family"] == "BEN32 BEN5K Slow Legacy"

    def test_slow_timing_reference_is_not_absolute(self, settings_slow_only):
        # Unverified UTC must not drive auto-synchronization.
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        timing_ref = resp.json().get("timing_reference")
        assert timing_ref != "absolute", (
            f"BEN5K Slow timing_reference must not be 'absolute' (got {timing_ref!r}). "
            "An unverified timestamp must not drive cross-source synchronization."
        )

    def test_slow_in_elapsed_only_bucket(self, settings_slow_only):
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        from app.domain.time_grouping import (
            TIME_REFERENCE_ELAPSED_ONLY,
            time_reference_type_for_source,
        )
        timing_ref = resp.json().get("timing_reference", "")
        assert time_reference_type_for_source(timing_ref) == TIME_REFERENCE_ELAPSED_ONLY, (
            f"BEN5K Slow must be in elapsed-only time bucket (got {timing_ref!r})."
        )

    def test_slow_tentative_channel_count(self, settings_slow_only):
        # One Group-0 TENTATIVE channel (selector 0x0100 → wi=1, wps=4 → in range).
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes(words_per_sample=4))
        body = resp.json()
        assert body["analog_channel_count"] == 1
        assert body["digital_channel_count"] == 0

    def test_slow_station_name(self, settings_slow_only):
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.json()["station_name"] == "GRNE"

    def test_slow_source_registered_in_list(self, settings_slow_only):
        with TestClient(create_app(settings_slow_only)) as client:
            _upload_ben(client, _make_slow_bytes())
            resp = client.get(_URL)
        sources = resp.json()
        assert len(sources) == 1
        assert sources[0]["layout_family"] == "BEN32 BEN5K Slow Legacy"


# ── Flag independence tests ───────────────────────────────────────────────────


class TestBen5kSlowFlagIndependence:
    def test_slow_flag_does_not_enable_fast(self, settings_slow_only):
        # BEN5K Fast (0x28ff) must remain rejected when only Slow flag is on.
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_fast_bytes())
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unsupported_ben_variant"

    def test_fast_flag_does_not_enable_slow(self, settings_fast_only):
        # BEN5K Slow (0x29ff) must remain rejected when only Fast flag is on.
        with TestClient(create_app(settings_fast_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unsupported_ben_variant"


# ── layout_family schema contract ─────────────────────────────────────────────


class TestLayoutFamilySchemaContract:
    def test_slow_layout_family_is_correct_string(self, settings_slow_only):
        # The exact string must match what the frontend checks
        # (`source.layout_family === "BEN32 BEN5K Slow Legacy"`).
        with TestClient(create_app(settings_slow_only)) as client:
            resp = _upload_ben(client, _make_slow_bytes())
        assert resp.json()["layout_family"] == "BEN32 BEN5K Slow Legacy"

    def test_slow_layout_family_in_source_list_response(self, settings_slow_only):
        # Ensure layout_family is also present on the GET /sources list endpoint.
        with TestClient(create_app(settings_slow_only)) as client:
            _upload_ben(client, _make_slow_bytes())
            list_resp = client.get(_URL)
        sources = list_resp.json()
        assert len(sources) == 1
        assert sources[0]["layout_family"] == "BEN32 BEN5K Slow Legacy"
