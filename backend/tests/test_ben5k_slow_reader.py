"""Synthetic tests for the BEN5K Slow config reader and channel classifier.

All assertions use purpose-built synthetic fixtures; the real GRNE recording
is NOT read by these tests.

Confirmed facts built into the fixtures:
  - Layout signature: 29 ff 03 00 6e 00 ca 00 (byte 4 = 0x29 vs 0x28 for Fast)
  - Gen marker: 05 00  (same as BEN5K Fast)
  - Class flag at 0x3C: 0x01 (Slow)
  - 8 channel slots per group: 24(SENS) + 8x28(channels) + 4(separator) = 252
  - Word-index formula: selector >> 8 (confirmed for Group 0 only)
  - INACTIVE: name starts with '-'
  - UNRESOLVED_ZERO: named channel with selector < 256 (high byte == 0)
  - UNRESOLVED_OOR: word_index >= words_per_sample
  - UNRESOLVED_CONFLICT: word_index already claimed by an earlier channel
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app.providers.ben.legacy_ben5k_slow.reader import (
    Ben5kSlowHeader,
    SlowChannelStatus,
    active_channels,
    read_channel_groups,
    read_config_header,
    read_header,
    read_hvdc_formula,
    unresolved_channels,
)
from app.providers.ben.errors import BenStructureError, BenTruncatedError

# ── Signature constants ───────────────────────────────────────────────────────

_FAMILY_SIG = b"\x01\x00\x04\x00"
_SLOW_LAYOUT_SIG = b"\x29\xff\x03\x00\x6e\x00\xca\x00"
_GEN_MARKER = b"\x05\x00"
_HEADER_END = 0xDC

_GROUP_STRIDE = 252
_GROUP_COUNT = 9
_GROUPS_START = 0x013F
_GROUPS_END = _GROUPS_START + _GROUP_COUNT * _GROUP_STRIDE   # 0x0A1B


# ── Fixture builders ──────────────────────────────────────────────────────────

def _build_sens_descriptor(
    group_index: int = 0,
    name: str = "SENS GROUP 0",
    active: bool = True,
) -> bytes:
    """Build a 24-byte SENS descriptor."""
    buf = bytearray(24)
    buf[0] = 0x02
    buf[1] = 0x3C
    buf[2] = group_index
    buf[3] = 0x00  # SENS discriminator
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    # meta bytes 20-23: active groups use 0x33 0xff 0x38 0x00; empty use 0xff 0xff 0x00 0x00
    if active:
        buf[20:24] = b"\x33\xff\x38\x00"
    else:
        buf[20:24] = b"\xff\xff\x00\x00"
    return bytes(buf)


def _build_channel_descriptor(
    name: str = "TEST CHAN",
    selector: int = 0x0100,    # word_index = 1 via >> 8
    scale_ref: bytes = b"\xff\xff\x38\x00",
) -> bytes:
    """Build a 28-byte channel descriptor."""
    buf = bytearray(28)
    struct.pack_into("<H", buf, 0, selector)
    buf[2] = 0x00  # reserved
    buf[3] = 0xFF  # channel discriminator
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    struct.pack_into("<I", buf, 20, 0xFFFFFFFF)  # NaN marker
    buf[24:28] = scale_ref[:4]
    return bytes(buf)


def _build_inactive_channel_descriptor() -> bytes:
    """Build a 28-byte inactive ('----') channel descriptor."""
    buf = bytearray(28)
    # selector = 0x0000 for inactive
    buf[3] = 0xFF
    buf[4] = ord("-")
    buf[5] = ord("-")
    buf[6] = ord("-")
    buf[7] = ord("-")
    return bytes(buf)


def _build_group(
    group_index: int,
    name: str,
    channels: list[bytes],  # up to 8 channel descriptor bytes (28 each)
    active: bool = True,
) -> bytes:
    """Build a 252-byte channel group."""
    assert len(channels) <= 8, "at most 8 channel slots per group"
    buf = bytearray(252)
    buf[0:24] = _build_sens_descriptor(group_index, name, active)
    for i, ch in enumerate(channels):
        start = 24 + i * 28
        buf[start : start + 28] = ch
    # fill remaining slots with inactive descriptors
    for i in range(len(channels), 8):
        start = 24 + i * 28
        buf[start : start + 28] = _build_inactive_channel_descriptor()
    # group separator
    buf[248:252] = b"\xff\xff\xff\xff"
    return bytes(buf)


def _build_config_header(
    recorder_unit: int = 1547,
    group_count: int = 5,
    station: str = "TEST",
) -> bytes:
    """Build a 34-byte BEN5K Slow config header."""
    buf = bytearray(34)
    struct.pack_into("<H", buf, 0, 0x0004)   # version
    struct.pack_into("<H", buf, 2, 0xFF32)   # marker
    struct.pack_into("<H", buf, 10, recorder_unit)
    struct.pack_into("<H", buf, 12, group_count)
    name_b = station.encode("latin-1")[:16]
    buf[14 : 14 + len(name_b)] = name_b
    return bytes(buf)


def _build_hvdc_formula(
    name: str = "HVDC Power",
    formula: str = "C014+C041+C021+C019+178",
) -> bytes:
    """Build a 65-byte HVDC formula descriptor."""
    buf = bytearray(65)
    # bytes 0-3: header
    buf[0:4] = b"\x00\x00\x00\x00"
    # bytes 4-19: name
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    # bytes 38-60: formula string + terminator
    formula_b = formula.encode("latin-1")[:23]
    buf[38 : 38 + len(formula_b)] = formula_b
    buf[38 + len(formula_b) : 38 + len(formula_b) + 3] = b"\x0d\x0a\x84"
    return bytes(buf)


def _make_slow_fixture(
    sample_count: int = 5,
    words_per_sample: int = 4,
    rate_hz: int = 20,
    pre_trigger: int = 2,
    station: str = "GRNE",
    recorder_unit: int = 1547,
    groups: list[bytes] | None = None,
    payload_words: list[list[int]] | None = None,
) -> bytes:
    """Build a minimal valid BEN5K Slow file for testing.

    Produces a complete binary file with:
      - 0x00DC-byte fixed header
      - 34-byte config header
      - 65-byte HVDC formula descriptor
      - 9 groups × 252 bytes (provided or minimal defaults)
      - big-endian u16 sample payload
    """
    # ── Fixed header (0xDC bytes) ────────────────────────────────────────────
    header = bytearray(0xDC)
    header[0:4] = _FAMILY_SIG
    header[4:12] = _SLOW_LAYOUT_SIG
    struct.pack_into("<H", header, 0x0C, recorder_unit)
    header[0x0E:0x10] = _GEN_MARKER
    station_b = station.encode("latin-1")[:0x28]
    header[0x10 : 0x10 + len(station_b)] = station_b
    struct.pack_into("<I", header, 0x38, 6606)   # record number
    header[0x3C] = 0x01  # class flag = Slow
    struct.pack_into("<I", header, 0x54, rate_hz * 1000)
    struct.pack_into("<I", header, 0x58, pre_trigger)
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<H", header, 0x60, words_per_sample)
    # Trigger timestamp: 2023-07-26 14:34:32.426316
    header[0x64:0x6D] = bytes([0x7B, 0x07, 0x1A, 0x0E, 0x22, 0x20, 0x2A, 0x19, 0x28])
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    # ── Config header ────────────────────────────────────────────────────────
    config_hdr = _build_config_header(recorder_unit=recorder_unit, station=station)

    # ── HVDC formula descriptor ──────────────────────────────────────────────
    hvdc = _build_hvdc_formula()

    # ── Channel groups ───────────────────────────────────────────────────────
    if groups is None:
        groups = []
    while len(groups) < _GROUP_COUNT:
        groups.append(_build_group(
            len(groups),
            f"SENS GROUP {len(groups)}",
            [],
        ))

    groups_bytes = b"".join(g for g in groups[:_GROUP_COUNT])

    # ── Sample payload ───────────────────────────────────────────────────────
    if payload_words is None:
        payload_words = [[i * words_per_sample + j for j in range(words_per_sample)]
                         for i in range(sample_count)]
    payload = bytearray()
    for row in payload_words:
        for w in row:
            payload.extend(struct.pack(">H", w & 0xFFFF))

    return bytes(header) + config_hdr + hvdc + groups_bytes + bytes(payload)


# ── Header tests ──────────────────────────────────────────────────────────────

class TestReadHeader:
    def test_basic_fields(self):
        data = _make_slow_fixture(sample_count=10, words_per_sample=6, rate_hz=20, pre_trigger=4)
        h = read_header(data)
        assert h.station_name == "GRNE"
        assert h.rate_hz == 20
        assert h.pre_trigger == 4
        assert h.sample_count == 10
        assert h.words_per_sample == 6
        assert len(h.trigger_bytes) == 9

    def test_record_number_read(self):
        data = _make_slow_fixture()
        h = read_header(data)
        assert h.record_number == 6606

    def test_truncated_raises(self):
        data = _make_slow_fixture()[:0xD0]
        with pytest.raises(BenTruncatedError):
            read_header(data)

    def test_zero_rate_raises(self):
        data = bytearray(_make_slow_fixture())
        struct.pack_into("<I", data, 0x54, 0)  # rate = 0
        with pytest.raises(BenStructureError):
            read_header(bytes(data))

    def test_zero_sample_count_raises(self):
        data = bytearray(_make_slow_fixture(sample_count=1))
        struct.pack_into("<I", data, 0x5C, 0)
        struct.pack_into("<I", data, 0x7A, 0)  # must also fix last_index to avoid separate error
        with pytest.raises(BenStructureError):
            read_header(bytes(data))

    def test_zero_words_per_sample_raises(self):
        data = bytearray(_make_slow_fixture())
        struct.pack_into("<H", data, 0x60, 0)
        with pytest.raises(BenStructureError):
            read_header(bytes(data))

    def test_last_sample_index_mismatch_raises(self):
        data = bytearray(_make_slow_fixture(sample_count=5))
        struct.pack_into("<I", data, 0x7A, 99)  # wrong last sample index
        with pytest.raises(BenStructureError):
            read_header(bytes(data))


# ── Config header tests ───────────────────────────────────────────────────────

class TestReadConfigHeader:
    def test_basic_fields(self):
        data = _make_slow_fixture(recorder_unit=1547, station="GRNE")
        cfg = read_config_header(data)
        assert cfg.recorder_unit == 1547
        assert cfg.primary_group_count == 5
        assert cfg.station_name == "GRNE"
        assert cfg.section_marker == 0xFF32
        assert cfg.version == 0x0004

    def test_truncated_raises(self):
        data = _make_slow_fixture()[:0xF0]
        with pytest.raises(BenTruncatedError):
            read_config_header(data)


# ── HVDC formula tests ────────────────────────────────────────────────────────

class TestReadHvdcFormula:
    def test_name_extracted(self):
        data = _make_slow_fixture()
        hvdc = read_hvdc_formula(data)
        assert hvdc.name == "HVDC Power"
        assert len(hvdc.raw_bytes) == 65

    def test_empty_name_tolerated(self):
        data = _make_slow_fixture()
        hvdc = read_hvdc_formula(data)
        # formula descriptor presence confirmed; name may be empty in other recordings
        assert isinstance(hvdc.name, str)


# ── Channel group tests ───────────────────────────────────────────────────────

class TestReadChannelGroups:
    def _make_with_groups(self, groups: list[bytes], wps: int = 6) -> bytes:
        return _make_slow_fixture(words_per_sample=wps, groups=groups)

    def test_nine_groups_returned(self):
        data = self._make_with_groups([])
        groups = read_channel_groups(data, read_header(data))
        assert len(groups) == 9

    def test_group_name_extracted(self):
        g0 = _build_group(0, "SENS BDNG 1", [])
        data = self._make_with_groups([g0])
        groups = read_channel_groups(data, read_header(data))
        assert groups[0].group_name == "SENS BDNG 1"

    def test_group_index_in_channels(self):
        ch = _build_channel_descriptor("FREQ BDNG 1", selector=0x0100)
        g0 = _build_group(0, "SENS BDNG 1", [ch])
        data = self._make_with_groups([g0])
        groups = read_channel_groups(data, read_header(data))
        named = [c for c in groups[0].channels if c.name == "FREQ BDNG 1"]
        assert len(named) == 1
        assert named[0].group_index == 0

    def test_inactive_slots_classified_inactive(self):
        # Group with only inactive slots
        g = _build_group(0, "SENS TEST", [], active=True)
        data = self._make_with_groups([g])
        groups = read_channel_groups(data, read_header(data))
        for ch in groups[0].channels:
            assert ch.status == SlowChannelStatus.INACTIVE

    def test_tentative_channel_in_range(self):
        # selector=0x0200 → word_index=2, wps=4 → in range
        ch = _build_channel_descriptor("MVAR TEST", selector=0x0200)
        g = _build_group(0, "SENS TEST", [ch])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        named = [c for c in groups[0].channels if c.name == "MVAR TEST"]
        assert len(named) == 1
        assert named[0].status == SlowChannelStatus.TENTATIVE
        assert named[0].word_index_tentative == 2

    def test_unresolved_oor_above_wps(self):
        # selector=0x2000 → word_index=32, wps=4 → OOR
        ch = _build_channel_descriptor("POWER JJNG", selector=0x2000)
        g = _build_group(0, "SENS JJNG", [ch])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        named = [c for c in groups[0].channels if c.name == "POWER JJNG"]
        assert named[0].status == SlowChannelStatus.UNRESOLVED_OOR
        assert named[0].word_index_tentative == 32

    def test_unresolved_zero_for_low_byte_selector(self):
        # selector=0x0010 (bit 4 in low byte) → word_index=0 → UNRESOLVED_ZERO
        ch = _build_channel_descriptor("POWER JJNG 2", selector=0x0010)
        g = _build_group(0, "SENS JJNG 2", [ch])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        named = [c for c in groups[0].channels if c.name == "POWER JJNG 2"]
        assert named[0].status == SlowChannelStatus.UNRESOLVED_ZERO
        assert named[0].word_index_tentative == 0

    def test_unresolved_conflict_duplicate_word(self):
        # Two channels in different groups both claiming word 2
        ch_a = _build_channel_descriptor("MVAR A", selector=0x0200)   # wi=2
        ch_b = _build_channel_descriptor("MVAR B", selector=0x0200)   # wi=2 — conflict
        g0 = _build_group(0, "SENS A", [ch_a])
        g1 = _build_group(1, "SENS B", [ch_b])
        data = self._make_with_groups([g0, g1], wps=4)
        groups = read_channel_groups(data, read_header(data))
        a = next(c for g in groups for c in g.channels if c.name == "MVAR A")
        b = next(c for g in groups for c in g.channels if c.name == "MVAR B")
        assert a.status == SlowChannelStatus.TENTATIVE
        assert b.status == SlowChannelStatus.UNRESOLVED_CONFLICT

    def test_active_channels_helper_returns_tentative_only(self):
        ch1 = _build_channel_descriptor("FREQ", selector=0x0100)      # wi=1, TENTATIVE
        ch2 = _build_channel_descriptor("POWER", selector=0x2000)     # wi=32, OOR
        ch3 = _build_channel_descriptor("LOWBYTE", selector=0x0010)   # wi=0, UNRESOLVED_ZERO
        g = _build_group(0, "SENS TEST", [ch1, ch2, ch3])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        actives = active_channels(groups)
        assert len(actives) == 1
        assert actives[0].name == "FREQ"

    def test_unresolved_channels_helper(self):
        ch_oor = _build_channel_descriptor("OOR", selector=0x2000)      # wi=32 OOR
        ch_zero = _build_channel_descriptor("ZERO", selector=0x0010)    # wi=0
        ch_ok = _build_channel_descriptor("OK", selector=0x0100)        # wi=1
        g = _build_group(0, "SENS TEST", [ch_oor, ch_zero, ch_ok])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        unresolved = unresolved_channels(groups)
        names = {c.name for c in unresolved}
        assert "OOR" in names
        assert "ZERO" in names
        assert "OK" not in names

    def test_bad_sens_discriminator_raises(self):
        g = bytearray(_build_group(0, "SENS TEST", []))
        g[3] = 0xFF  # corrupt SENS discriminator (should be 0x00)
        data = bytearray(_make_slow_fixture())
        # Overwrite first group
        groups_start = _GROUPS_START
        data[groups_start : groups_start + _GROUP_STRIDE] = g
        with pytest.raises(BenStructureError):
            read_channel_groups(bytes(data), read_header(bytes(data)))

    def test_truncated_groups_raises(self):
        # File too short to contain all 9 groups
        data = _make_slow_fixture()[:_GROUPS_START + 100]
        with pytest.raises(BenTruncatedError):
            read_channel_groups(data, read_header(data))

    def test_scale_ref_raw_preserved(self):
        custom_scale_ref = b"\x01\x02\x03\x04"
        ch = _build_channel_descriptor("CHAN", selector=0x0100, scale_ref=custom_scale_ref)
        g = _build_group(0, "SENS TEST", [ch])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        named = next(c for c in groups[0].channels if c.name == "CHAN")
        assert named.scale_ref_raw == custom_scale_ref

    def test_slot_index_assigned(self):
        ch0 = _build_channel_descriptor("CH0", selector=0x0100)
        ch1 = _build_channel_descriptor("CH1", selector=0x0200)
        g = _build_group(0, "SENS TEST", [ch0, ch1])
        data = self._make_with_groups([g], wps=4)
        groups = read_channel_groups(data, read_header(data))
        c0 = next(c for c in groups[0].channels if c.name == "CH0")
        c1 = next(c for c in groups[0].channels if c.name == "CH1")
        assert c0.slot_index == 0
        assert c1.slot_index == 1

    def test_eight_slots_per_group(self):
        # All 8 slots active
        chs = [
            _build_channel_descriptor(f"CH{i}", selector=(i + 1) << 8)
            for i in range(8)
        ]
        g = _build_group(0, "SENS FULL", chs)
        data = self._make_with_groups([g], wps=10)
        groups = read_channel_groups(data, read_header(data))
        assert len(groups[0].channels) == 8
        active = [c for c in groups[0].channels if c.status == SlowChannelStatus.TENTATIVE]
        assert len(active) == 8


# ── Descriptor offset tests ───────────────────────────────────────────────────

class TestDescriptorOffsets:
    def test_descriptor_offset_within_file(self):
        ch = _build_channel_descriptor("FREQ", selector=0x0100)
        g = _build_group(0, "SENS BDNG 1", [ch])
        data = _make_slow_fixture(groups=[g], words_per_sample=4)
        groups = read_channel_groups(data, read_header(data))
        named = next(c for c in groups[0].channels if c.name == "FREQ")
        # descriptor_offset must point at valid data inside the file
        assert 0 < named.descriptor_offset < len(data)
        # The name bytes at that offset should match
        name_at_offset = data[named.descriptor_offset + 4 : named.descriptor_offset + 20]
        assert name_at_offset.startswith(b"FREQ")


# ── Integration with parse_ben_experimental ───────────────────────────────────

class TestParserDispatch:
    def test_is_ben5k_slow_recognized(self):
        from app.providers.ben.parser import _is_ben5k_slow
        data = _make_slow_fixture()
        assert _is_ben5k_slow(data) is True

    def test_is_ben5k_slow_rejects_fast(self):
        from app.providers.ben.parser import _is_ben5k_slow
        # BEN5K Fast has layout byte 0x28, not 0x29
        data = bytearray(_make_slow_fixture())
        data[4] = 0x28  # change to Fast layout byte
        assert _is_ben5k_slow(bytes(data)) is False

    def test_is_ben5k_slow_rejects_subben(self):
        from app.providers.ben.parser import _is_ben5k_slow
        data = bytearray(_make_slow_fixture())
        data[4:12] = b"\x2a\xff\x03\x00\x6e\x00\xca\x00"  # SubBen layout
        assert _is_ben5k_slow(bytes(data)) is False

    def test_is_ben5k_slow_rejects_too_short(self):
        from app.providers.ben.parser import _is_ben5k_slow
        assert _is_ben5k_slow(b"\x29\xff") is False

    def test_parse_ben_experimental_dispatches_slow(self):
        from app.providers.ben.parser import parse_ben_experimental
        from app.providers.ben.model import BenRecordClass
        data = _make_slow_fixture(
            groups=[_build_group(0, "SENS BDNG 1", [
                _build_channel_descriptor("FREQ BDNG 1", selector=0x0100),
            ])],
            words_per_sample=4,
        )
        record = parse_ben_experimental(data, allow_legacy_ben5k_slow=True)
        assert record.header.record_class == BenRecordClass.BEN5K_SLOW_LEGACY

    def test_parse_ben_experimental_rejects_slow_when_flag_off(self):
        from app.providers.ben.parser import parse_ben_experimental
        from app.providers.ben.errors import BenUnsupportedVariantError
        data = _make_slow_fixture()
        with pytest.raises(BenUnsupportedVariantError):
            parse_ben_experimental(data, allow_legacy_ben5k_slow=False)

    def test_parse_ben_experimental_does_not_confuse_fast_and_slow(self):
        from app.providers.ben.parser import parse_ben_experimental
        from app.providers.ben.model import BenRecordClass
        # A Slow file should NOT be decoded by the Fast decoder
        data = _make_slow_fixture()
        # Passing allow_legacy_ben5k=True but NOT allow_legacy_ben5k_slow should still
        # raise because the layout signature 0x29 is not the Fast signature 0x28
        from app.providers.ben.errors import BenUnsupportedVariantError
        with pytest.raises(BenUnsupportedVariantError):
            parse_ben_experimental(data, allow_legacy_ben5k=True, allow_legacy_ben5k_slow=False)
