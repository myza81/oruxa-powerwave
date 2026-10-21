"""Stage 2 tests: BEN5K config reader and channel descriptor walker.

Tests validate byte-level facts confirmed by direct binary analysis of:
  261016_180314535_GPTH_275kV.ben
  SHA-256: 55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88

The real recording is NOT read by these tests.  All assertions are against a
purpose-built synthetic fixture that contains:
  - A 220-byte (0xDC) header with the confirmed BEN5K signature and field values
  - A short flat config area with exactly two channel descriptors (one analog,
    one digital) followed by padding
  - A minimal payload (2 samples, 3 words each) with known values

Confirmed against the real recording (22 channels, validated):
  - Header: station name, rate (5000 Hz), sample count, words per sample (97)
  - word_index is 0-indexed (TBIN1 VR = word_index 0 confirmed)
  - First analog descriptor at 0xBBA (4 bytes after 0xBB6)
  - Analog descriptor byte 53 = word_index; byte 28 = f32le scale
  - Digital discriminator: byte 3 == 0xFF
  - Payload boundary: file_size − count × wps × 2
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app.providers.ben.legacy_ben5k.reader import (
    Ben5kAnalogChannel,
    Ben5kDigitalChannel,
    Ben5kHeader,
    read_channel_descriptors,
    read_feeder_names,
    read_header,
)
from app.providers.ben.errors import BenStructureError, BenTruncatedError

# ── Synthetic fixture builder ─────────────────────────────────────────────────

_BEN5K_FAMILY_SIG = b"\x01\x00\x04\x00"
_BEN5K_LAYOUT_SIG = b"\x28\xff\x03\x00\x6e\x00\xca\x00"
_BEN5K_GEN_MARKER = b"\x05\x00"

# Descriptor constants
_DESC_SIZE = 58
_SHORT_FEEDER_NAME_END = 0xBB6


def _build_analog_descriptor(
    name: str,
    word_index: int,
    scale: float = 1.0,
    offset: float = 0.0,
    low_range: float = -100.0,
    high_range: float = 100.0,
    type_byte: int = 0x00,
    phase_seq: int = 1,
    class_code: int = 0x0528,
) -> bytes:
    """Build a 58-byte analog channel descriptor."""
    buf = bytearray(58)
    buf[0] = type_byte
    buf[1] = phase_seq
    struct.pack_into("<H", buf, 2, class_code)
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    # bytes 20-27: fixed constants observed in GPTH (preserved raw)
    buf[20:22] = b"\x4b\x41"  # 0x414B
    buf[26:28] = b"\x28\x00"  # 0x0028
    struct.pack_into("<f", buf, 28, scale)
    struct.pack_into("<f", buf, 32, offset)
    struct.pack_into("<f", buf, 36, low_range)
    struct.pack_into("<f", buf, 40, high_range)
    buf[44] = 0x02
    buf[52] = 0x02
    buf[53] = word_index
    buf[57] = 0xFF
    return bytes(buf)


def _build_digital_descriptor(
    name: str,
    word_group: int,
    bit_index: int,
    polarity_flag: int = 0x01,
) -> bytes:
    """Build a 58-byte digital channel descriptor."""
    buf = bytearray(58)
    buf[0] = polarity_flag
    buf[1] = word_group
    buf[2] = bit_index
    buf[3] = 0xFF  # digital type marker
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    buf[57] = 0xFF
    return bytes(buf)


def _build_short_feeder_names(names: list[str]) -> bytes:
    """Build 12 × 22-byte short feeder name entries."""
    result = bytearray()
    for i in range(12):
        name = names[i] if i < len(names) else ""
        entry = bytearray(22)
        n = name.encode("latin-1")[:13]
        entry[:len(n)] = n
        entry[16:22] = b"\xff" * 6  # separator
        result.extend(entry)
    return bytes(result)


def _make_fixture(
    sample_count: int = 10,
    words_per_sample: int = 3,
    rate_hz: int = 5000,
    pre_trigger: int = 2,
    station: str = "TEST STATION",
    extra_analog: list[Ben5kAnalogChannel] | None = None,
    extra_digital: list[tuple[str, int, int]] | None = None,
    payload_words: np.ndarray | None = None,
) -> bytes:
    """Build a minimal valid BEN5K file for testing."""
    # Fixed header (220 bytes = 0xDC)
    header = bytearray(0xDC)
    header[0:4] = _BEN5K_FAMILY_SIG
    header[4:12] = _BEN5K_LAYOUT_SIG
    header[14:16] = _BEN5K_GEN_MARKER
    station_b = station.encode("latin-1")[:0x28]
    header[0x10 : 0x10 + len(station_b)] = station_b
    struct.pack_into("<I", header, 0x54, rate_hz * 1000)
    struct.pack_into("<I", header, 0x58, pre_trigger)
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<I", header, 0x60, words_per_sample)
    # Trigger bytes: 2026-10-16 18:03:14.535400 UTC
    header[0x64:0x6D] = bytes([0x7E, 0x0A, 0x10, 0x12, 0x03, 0x0E, 0x35, 0x36, 0x00])
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    # Config area: must reach at least _SHORT_FEEDER_NAME_END (0xBB6)
    feeder_names = _build_short_feeder_names(["TBIN1", "SDAI1"])
    # config area from 0xDC to 0xBB6 = 0xADA bytes
    config_prefix = bytearray(0xAAE - 0xDC)  # up to short feeder names
    config_area = bytes(config_prefix) + feeder_names  # ends at 0xBB6

    # 4-byte gap between end of short feeder names (0xBB6) and first descriptor (0xBBA)
    _GAP = bytes(4)

    # Descriptors
    analog_desc = _build_analog_descriptor("TBIN1 VR", word_index=0, scale=0.01)
    digital_desc = _build_digital_descriptor("TBIN1 CB_R OPEN", word_group=1, bit_index=7)
    descriptors = _GAP + analog_desc + digital_desc

    # Payload: big-endian u16
    if payload_words is None:
        payload_words = np.zeros((sample_count, words_per_sample), dtype=">u2")
        # Word 0: VR signal (known raw value 1000 → engineering = 0.01 × 1000 = 10.0)
        payload_words[:, 0] = 1000
        # Word 2: digital bitmask words (word_group=1 → sample_word = 37+1=38,
        #         but our fixture only has 3 words, so word_group=1 maps to word 1
        #         for this small fixture — override in test)

    payload = payload_words.tobytes()

    # Pad config area to exactly hit the payload offset
    payload_size = sample_count * words_per_sample * 2
    payload_offset_target = 0xDC + len(config_area) + len(descriptors)
    # Round up to at least a descriptor boundary
    total_config = len(config_area) + len(descriptors)
    full_file = bytes(header) + config_area + descriptors + payload
    return full_file


# ── Header tests ──────────────────────────────────────────────────────────────

class TestBen5kReadHeader:
    def test_reads_station_name(self) -> None:
        data = _make_fixture(station="GPTH 275kV - BEN5K")
        h = read_header(data)
        assert h.station_name == "GPTH 275kV - BEN5K"

    def test_reads_rate(self) -> None:
        data = _make_fixture(rate_hz=5000)
        h = read_header(data)
        assert h.rate_hz == 5000

    def test_reads_sample_count(self) -> None:
        data = _make_fixture(sample_count=100)
        h = read_header(data)
        assert h.sample_count == 100

    def test_reads_words_per_sample(self) -> None:
        data = _make_fixture(words_per_sample=4)
        h = read_header(data)
        assert h.words_per_sample == 4

    def test_reads_pre_trigger(self) -> None:
        data = _make_fixture(sample_count=10, pre_trigger=3)
        h = read_header(data)
        assert h.pre_trigger == 3

    def test_reads_trigger_bytes(self) -> None:
        data = _make_fixture()
        h = read_header(data)
        assert len(h.trigger_bytes) == 9

    def test_raises_truncated_for_short_file(self) -> None:
        with pytest.raises(BenTruncatedError):
            read_header(b"\x01\x00\x04\x00" + b"\x00" * 10)

    def test_raises_structure_error_zero_rate(self) -> None:
        data = bytearray(_make_fixture())
        struct.pack_into("<I", data, 0x54, 0)  # zero rate
        with pytest.raises(BenStructureError):
            read_header(bytes(data))

    def test_raises_structure_error_zero_sample_count(self) -> None:
        data = bytearray(_make_fixture(sample_count=5))
        struct.pack_into("<I", data, 0x5C, 0)
        with pytest.raises(BenStructureError):
            read_header(bytes(data))

    def test_raises_structure_error_last_index_mismatch(self) -> None:
        data = bytearray(_make_fixture(sample_count=10))
        struct.pack_into("<I", data, 0x7A, 5)  # should be 9
        with pytest.raises(BenStructureError):
            read_header(bytes(data))


# ── Channel descriptor tests ──────────────────────────────────────────────────

class TestBen5kReadChannelDescriptors:
    def _make_and_read(self, **kw: object) -> tuple[
        list[Ben5kAnalogChannel], list[Ben5kDigitalChannel]
    ]:
        data = _make_fixture(**kw)
        header = read_header(data)
        return read_channel_descriptors(data, header)

    def test_finds_one_analog_channel(self) -> None:
        analog, digital = self._make_and_read()
        assert len(analog) == 1

    def test_finds_one_digital_channel(self) -> None:
        analog, digital = self._make_and_read()
        assert len(digital) == 1

    def test_analog_name(self) -> None:
        analog, _ = self._make_and_read()
        assert analog[0].name == "TBIN1 VR"

    def test_analog_word_index(self) -> None:
        analog, _ = self._make_and_read()
        assert analog[0].word_index == 0

    def test_analog_scale(self) -> None:
        analog, _ = self._make_and_read()
        assert abs(analog[0].scale - 0.01) < 1e-6

    def test_analog_type_byte_voltage(self) -> None:
        analog, _ = self._make_and_read()
        assert analog[0].type_byte == 0x00

    def test_digital_name(self) -> None:
        _, digital = self._make_and_read()
        assert digital[0].name == "TBIN1 CB_R OPEN"

    def test_digital_word_group(self) -> None:
        _, digital = self._make_and_read()
        assert digital[0].word_group == 1

    def test_digital_bit_index(self) -> None:
        _, digital = self._make_and_read()
        assert digital[0].bit_index == 7

    def test_analog_word_index_varies(self) -> None:
        """Different descriptors must each report their own word_index."""
        # Build a file with two analog channels at different word_indices.
        header_b = bytearray(0xDC)
        header_b[0:4] = _BEN5K_FAMILY_SIG
        header_b[4:12] = _BEN5K_LAYOUT_SIG
        header_b[14:16] = _BEN5K_GEN_MARKER
        struct.pack_into("<I", header_b, 0x54, 5_000_000)
        struct.pack_into("<I", header_b, 0x5C, 10)
        struct.pack_into("<I", header_b, 0x60, 5)  # 5 words per sample
        struct.pack_into("<I", header_b, 0x7A, 9)
        header_b[0x64:0x6D] = bytes([0x7E, 0x0A, 0x10, 0x12, 0x03, 0x0E, 0x35, 0x36, 0x00])

        feeder_names = _build_short_feeder_names(["TBIN1"])
        config_prefix = bytearray(0xAAE - 0xDC)
        desc1 = _build_analog_descriptor("TBIN1 VR", word_index=0, scale=0.1)
        desc2 = _build_analog_descriptor("TBIN1 VB", word_index=2, scale=0.1)
        # 4-byte gap between feeder names (end 0xBB6) and first descriptor (0xBBA)
        descriptors = bytes(4) + desc1 + desc2

        payload = np.zeros((10, 5), dtype=">u2").tobytes()
        data = bytes(header_b) + bytes(config_prefix) + feeder_names + descriptors + payload

        h = read_header(data)
        analog, digital = read_channel_descriptors(data, h)

        names = {ch.name: ch.word_index for ch in analog}
        assert names.get("TBIN1 VR") == 0
        assert names.get("TBIN1 VB") == 2

    def test_descriptor_offset_recorded(self) -> None:
        """Each descriptor's descriptor_offset must be within the config area."""
        analog, digital = self._make_and_read()
        for ch in analog + digital:
            assert ch.descriptor_offset >= _SHORT_FEEDER_NAME_END


# ── Digital sample_word_index property test ───────────────────────────────────

class TestBen5kDigitalSampleWordIndex:
    def test_word_group_1_maps_to_38(self) -> None:
        ch = Ben5kDigitalChannel(
            name="CB_R OPEN", word_group=1, bit_index=7, polarity_flag=1, descriptor_offset=0
        )
        assert ch.sample_word_index == 38

    def test_word_group_5_maps_to_42(self) -> None:
        ch = Ben5kDigitalChannel(
            name="CB_B OPEN", word_group=5, bit_index=9, polarity_flag=1, descriptor_offset=0
        )
        assert ch.sample_word_index == 42


# ── Feeder name tests ─────────────────────────────────────────────────────────

class TestBen5kReadFeederNames:
    def test_returns_12_names(self) -> None:
        data = _make_fixture()
        names = read_feeder_names(data)
        assert len(names) == 12

    def test_first_name_tbin1(self) -> None:
        data = _make_fixture()
        names = read_feeder_names(data)
        assert names[0] == "TBIN1"
