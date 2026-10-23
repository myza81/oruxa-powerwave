"""Synthetic tests for the BEN5K Slow sample-matrix decoder and normalizer.

Tests cover:
  - extract_raw_matrix(): shape, big-endian decode, truncation guard
  - extract_channel_columns(): correct int16 from big-endian u16,
    .astype() vs .view() byte-order difference, empty-list case,
    0xFFFF→-1 preservation, error paths for non-TENTATIVE channels
  - sample_word_inventory(): per-word stats accuracy
  - parse_ben5k_slow(): end-to-end BenRecord structure, diagnostics,
    value_channel fields, sample_words shape

All tests use the same _make_slow_fixture() / _build_* helpers as
test_ben5k_slow_reader.py, duplicated here for test-file independence.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app.providers.ben.errors import BenStructureError, BenTruncatedError
from app.providers.ben.legacy_ben5k_slow.decoder import (
    extract_channel_columns,
    extract_raw_matrix,
    sample_word_inventory,
)
from app.providers.ben.legacy_ben5k_slow.reader import (
    Ben5kSlowHeader,
    SlowChannelDescriptor,
    SlowChannelStatus,
    read_channel_groups,
    read_header,
    active_channels,
)

# ── Fixture builders (same as test_ben5k_slow_reader.py) ──────────────────────

_FAMILY_SIG = b"\x01\x00\x04\x00"
_SLOW_LAYOUT_SIG = b"\x29\xff\x03\x00\x6e\x00\xca\x00"
_GEN_MARKER = b"\x05\x00"
_HEADER_END = 0xDC

_GROUP_STRIDE = 252
_GROUP_COUNT = 9
_GROUPS_START = 0x013F


def _build_sens_descriptor(
    group_index: int = 0,
    name: str = "SENS GROUP 0",
    active: bool = True,
) -> bytes:
    buf = bytearray(24)
    buf[0] = 0x02
    buf[1] = 0x3C
    buf[2] = group_index
    buf[3] = 0x00
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    if active:
        buf[20:24] = b"\x33\xff\x38\x00"
    else:
        buf[20:24] = b"\xff\xff\x00\x00"
    return bytes(buf)


def _build_channel_descriptor(
    name: str = "TEST CHAN",
    selector: int = 0x0100,
    scale_ref: bytes = b"\xff\xff\x38\x00",
) -> bytes:
    buf = bytearray(28)
    struct.pack_into("<H", buf, 0, selector)
    buf[3] = 0xFF
    name_b = name.encode("latin-1")[:16]
    buf[4 : 4 + len(name_b)] = name_b
    struct.pack_into("<I", buf, 20, 0xFFFFFFFF)
    buf[24:28] = scale_ref[:4]
    return bytes(buf)


def _build_inactive_channel_descriptor() -> bytes:
    buf = bytearray(28)
    buf[3] = 0xFF
    buf[4] = ord("-")
    buf[5] = ord("-")
    buf[6] = ord("-")
    buf[7] = ord("-")
    return bytes(buf)


def _build_group(
    group_index: int,
    name: str,
    channels: list[bytes],
    active: bool = True,
) -> bytes:
    assert len(channels) <= 8
    buf = bytearray(252)
    buf[0:24] = _build_sens_descriptor(group_index, name, active)
    for i, ch in enumerate(channels):
        start = 24 + i * 28
        buf[start : start + 28] = ch
    for i in range(len(channels), 8):
        start = 24 + i * 28
        buf[start : start + 28] = _build_inactive_channel_descriptor()
    buf[248:252] = b"\xff\xff\xff\xff"
    return bytes(buf)


def _build_config_header(recorder_unit: int = 1547, station: str = "GRNE") -> bytes:
    buf = bytearray(34)
    struct.pack_into("<H", buf, 0, 0x0004)
    struct.pack_into("<H", buf, 2, 0xFF32)
    struct.pack_into("<H", buf, 10, recorder_unit)
    struct.pack_into("<H", buf, 12, 5)
    name_b = station.encode("latin-1")[:16]
    buf[14 : 14 + len(name_b)] = name_b
    return bytes(buf)


def _build_hvdc_formula() -> bytes:
    buf = bytearray(65)
    buf[4 : 4 + 10] = b"HVDC Power"
    buf[38 : 38 + 20] = b"C014+C041+C021\r\n\x84\x00\x00\x00"
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
    header = bytearray(0xDC)
    header[0:4] = _FAMILY_SIG
    header[4:12] = _SLOW_LAYOUT_SIG
    struct.pack_into("<H", header, 0x0C, recorder_unit)
    header[0x0E:0x10] = _GEN_MARKER
    station_b = station.encode("latin-1")[:0x28]
    header[0x10 : 0x10 + len(station_b)] = station_b
    struct.pack_into("<I", header, 0x38, 6606)
    header[0x3C] = 0x01
    struct.pack_into("<I", header, 0x54, rate_hz * 1000)
    struct.pack_into("<I", header, 0x58, pre_trigger)
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<H", header, 0x60, words_per_sample)
    header[0x64:0x6D] = bytes([0x7B, 0x07, 0x1A, 0x0E, 0x22, 0x20, 0x2A, 0x19, 0x28])
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    config_hdr = _build_config_header(recorder_unit=recorder_unit, station=station)
    hvdc = _build_hvdc_formula()

    if groups is None:
        groups = []
    while len(groups) < _GROUP_COUNT:
        groups.append(_build_group(len(groups), f"SENS GROUP {len(groups)}", []))

    groups_bytes = b"".join(groups[:_GROUP_COUNT])

    if payload_words is None:
        payload_words = [
            [i * words_per_sample + j for j in range(words_per_sample)]
            for i in range(sample_count)
        ]
    payload = bytearray()
    for row in payload_words:
        for w in row:
            payload.extend(struct.pack(">H", w & 0xFFFF))

    return bytes(header) + config_hdr + hvdc + groups_bytes + bytes(payload)


def _make_tentative_descriptor(name: str, word_index: int) -> SlowChannelDescriptor:
    """Build a synthetic TENTATIVE SlowChannelDescriptor without reading a file."""
    return SlowChannelDescriptor(
        name=name,
        selector_raw=word_index << 8,
        word_index_tentative=word_index,
        group_index=0,
        group_name="SENS TEST",
        slot_index=0,
        descriptor_offset=0,
        status=SlowChannelStatus.TENTATIVE,
        scale_ref_raw=b"\x00\x00\x00\x00",
    )


def _make_bad_descriptor(name: str, word_index: int, status: SlowChannelStatus) -> SlowChannelDescriptor:
    return SlowChannelDescriptor(
        name=name,
        selector_raw=word_index << 8,
        word_index_tentative=word_index,
        group_index=0,
        group_name="SENS TEST",
        slot_index=0,
        descriptor_offset=0,
        status=status,
        scale_ref_raw=b"\x00\x00\x00\x00",
    )


# ── extract_raw_matrix() tests ────────────────────────────────────────────────

class TestExtractRawMatrix:
    def test_shape(self):
        data = _make_slow_fixture(sample_count=7, words_per_sample=5)
        header = read_header(data)
        mat = extract_raw_matrix(data, header)
        assert mat.shape == (7, 5)

    def test_dtype_unsigned(self):
        data = _make_slow_fixture(sample_count=3, words_per_sample=4)
        header = read_header(data)
        mat = extract_raw_matrix(data, header)
        assert mat.dtype == np.dtype(">u2")

    def test_values_are_big_endian(self):
        # Payload word = 0x0102 big-endian = bytes [0x01, 0x02]
        payload_words = [[0x0102, 0x0304, 0x0506, 0x0708]] * 3
        data = _make_slow_fixture(
            sample_count=3, words_per_sample=4, payload_words=payload_words
        )
        header = read_header(data)
        mat = extract_raw_matrix(data, header)
        # word 0 of sample 0 should be 0x0102
        assert int(mat[0, 0]) == 0x0102
        assert int(mat[0, 1]) == 0x0304
        assert int(mat[0, 2]) == 0x0506
        assert int(mat[0, 3]) == 0x0708

    def test_payload_at_end_of_file(self):
        # The payload is always at the end of the file
        payload_words = [[0xAAAA, 0xBBBB]] * 2
        data = _make_slow_fixture(
            sample_count=2, words_per_sample=2, payload_words=payload_words
        )
        header = read_header(data)
        mat = extract_raw_matrix(data, header)
        assert int(mat[0, 0]) == 0xAAAA
        assert int(mat[1, 1]) == 0xBBBB

    def test_truncated_raises(self):
        # Build a header that claims a huge payload, but pass a tiny data buffer.
        # payload_bytes = 1000 * 4 * 2 = 8000; len(data) = 100 → offset <= 0 → raises.
        header = Ben5kSlowHeader(
            station_name="TEST",
            recorder_unit=1547,
            record_number=0,
            rate_hz=20,
            pre_trigger=0,
            sample_count=1000,
            words_per_sample=4,
            trigger_bytes=bytes(9),
        )
        with pytest.raises(BenTruncatedError):
            extract_raw_matrix(b"\x00" * 100, header)


# ── extract_channel_columns() tests ──────────────────────────────────────────

class TestExtractChannelColumns:
    def test_basic_extraction(self):
        # word 1 = pattern A, word 2 = pattern B
        payload_words = [
            [0xDEAD, 0x1111, 0x2222, 0xBEEF],
            [0xDEAD, 0x3333, 0x4444, 0xBEEF],
            [0xDEAD, 0x5555, 0x6666, 0xBEEF],
        ]
        data = _make_slow_fixture(
            sample_count=3, words_per_sample=4, payload_words=payload_words
        )
        header = read_header(data)
        ch1 = _make_tentative_descriptor("CH1", 1)
        ch2 = _make_tentative_descriptor("CH2", 2)
        cols = extract_channel_columns(data, header, [ch1, ch2])
        assert cols.shape == (3, 2)
        assert cols.dtype == np.int16

    def test_signed_conversion_via_astype_not_view(self):
        # 0x8000 is 32768 unsigned, -32768 as signed int16
        # .view(np.int16) on big-endian >u2 would give wrong result on LE systems
        payload_words = [[0x8000, 0x8001, 0x7FFF, 0x0000]] * 1
        data = _make_slow_fixture(
            sample_count=1, words_per_sample=4, payload_words=payload_words
        )
        header = read_header(data)
        ch0 = _make_tentative_descriptor("NEG", 1)   # word_index=1, value=0x8001
        cols = extract_channel_columns(data, header, [ch0])
        # 0x8001 = 32769 unsigned, as signed int16 = -32767
        assert int(cols[0, 0]) == -32767

    def test_0xffff_becomes_minus_one(self):
        # 0xFFFF unsigned = -1 as signed int16
        payload_words = [[0x0000, 0xFFFF, 0x0001, 0x0000]] * 2
        data = _make_slow_fixture(
            sample_count=2, words_per_sample=4, payload_words=payload_words
        )
        header = read_header(data)
        ch = _make_tentative_descriptor("UNAVAIL", 1)
        cols = extract_channel_columns(data, header, [ch])
        assert int(cols[0, 0]) == -1
        assert int(cols[1, 0]) == -1

    def test_empty_channels_list(self):
        data = _make_slow_fixture(sample_count=4, words_per_sample=3)
        header = read_header(data)
        cols = extract_channel_columns(data, header, [])
        assert cols.shape == (4, 0)
        assert cols.dtype == np.int16

    def test_rejects_inactive_channel(self):
        data = _make_slow_fixture(sample_count=3, words_per_sample=4)
        header = read_header(data)
        ch = _make_bad_descriptor("INACTIVE", 1, SlowChannelStatus.INACTIVE)
        with pytest.raises(BenStructureError):
            extract_channel_columns(data, header, [ch])

    def test_rejects_unresolved_oor_channel(self):
        data = _make_slow_fixture(sample_count=3, words_per_sample=4)
        header = read_header(data)
        ch = _make_bad_descriptor("OOR", 32, SlowChannelStatus.UNRESOLVED_OOR)
        with pytest.raises(BenStructureError):
            extract_channel_columns(data, header, [ch])

    def test_rejects_unresolved_zero_channel(self):
        data = _make_slow_fixture(sample_count=3, words_per_sample=4)
        header = read_header(data)
        ch = _make_bad_descriptor("ZERO", 0, SlowChannelStatus.UNRESOLVED_ZERO)
        with pytest.raises(BenStructureError):
            extract_channel_columns(data, header, [ch])

    def test_rejects_word_index_0_even_if_tentative(self):
        # word_index == 0 is forbidden even for a TENTATIVE descriptor
        data = _make_slow_fixture(sample_count=3, words_per_sample=4)
        header = read_header(data)
        # Build a TENTATIVE descriptor at wi=0 (unusual; reader wouldn't produce this)
        ch = SlowChannelDescriptor(
            name="WEIRD",
            selector_raw=0x0000,
            word_index_tentative=0,
            group_index=0,
            group_name="SENS TEST",
            slot_index=0,
            descriptor_offset=0,
            status=SlowChannelStatus.TENTATIVE,  # wrongly marked TENTATIVE
            scale_ref_raw=b"\x00\x00\x00\x00",
        )
        with pytest.raises(BenStructureError):
            extract_channel_columns(data, header, [ch])

    def test_rejects_word_index_at_wps(self):
        data = _make_slow_fixture(sample_count=3, words_per_sample=4)
        header = read_header(data)
        ch = _make_tentative_descriptor("AT_WPS", 4)  # words_per_sample=4, so wi=4 is OOB
        with pytest.raises(BenStructureError):
            extract_channel_columns(data, header, [ch])

    def test_multiple_channels_independent_columns(self):
        # Verify columns are independent: channel A and B from separate word_indexes
        payload_words = [
            [0, 100, 200, 300],
            [0, 110, 210, 310],
            [0, 120, 220, 320],
        ]
        data = _make_slow_fixture(
            sample_count=3, words_per_sample=4, payload_words=payload_words
        )
        header = read_header(data)
        ch1 = _make_tentative_descriptor("WI1", 1)
        ch2 = _make_tentative_descriptor("WI2", 2)
        ch3 = _make_tentative_descriptor("WI3", 3)
        cols = extract_channel_columns(data, header, [ch1, ch2, ch3])
        assert cols.shape == (3, 3)
        np.testing.assert_array_equal(cols[:, 0], [100, 110, 120])
        np.testing.assert_array_equal(cols[:, 1], [200, 210, 220])
        np.testing.assert_array_equal(cols[:, 2], [300, 310, 320])

    def test_int16_sign_boundary(self):
        # 0x7FFF = 32767 (max positive int16)
        # 0x8000 = -32768 (min negative int16)
        payload_words = [[0, 0x7FFF, 0x8000, 1]] * 1
        data = _make_slow_fixture(
            sample_count=1, words_per_sample=4, payload_words=payload_words
        )
        header = read_header(data)
        ch_pos = _make_tentative_descriptor("POS", 1)
        ch_neg = _make_tentative_descriptor("NEG", 2)
        cols = extract_channel_columns(data, header, [ch_pos, ch_neg])
        assert int(cols[0, 0]) == 32767
        assert int(cols[0, 1]) == -32768


# ── sample_word_inventory() tests ────────────────────────────────────────────

class TestSampleWordInventory:
    def _make_raw(self, rows: list[list[int]]) -> np.ndarray:
        """Build a big-endian u16 ndarray directly from row values."""
        # np.array(..., dtype=">u2") produces big-endian u16 with values preserved.
        # Do NOT use .view(">u2") on a native-endian array: that byte-swaps values.
        return np.array(rows, dtype=">u2")

    def test_inventory_length_equals_words_per_sample(self):
        raw = self._make_raw([[1, 2, 3, 4]] * 5)
        inv = sample_word_inventory(raw)
        assert len(inv) == 4

    def test_word_index_field(self):
        raw = self._make_raw([[0, 0]] * 2)
        inv = sample_word_inventory(raw)
        assert inv[0]["word_index"] == 0
        assert inv[1]["word_index"] == 1

    def test_min_max_unsigned(self):
        # word 0: values 10, 20, 30
        raw = self._make_raw([[10, 100], [20, 200], [30, 300]])
        inv = sample_word_inventory(raw)
        assert inv[0]["min_unsigned"] == 10
        assert inv[0]["max_unsigned"] == 30
        assert inv[1]["min_unsigned"] == 100
        assert inv[1]["max_unsigned"] == 300

    def test_min_max_signed(self):
        # 0x8000 = -32768 signed, 0x7FFF = 32767 signed
        raw = self._make_raw([[0x8000, 0x7FFF]] * 1)
        inv = sample_word_inventory(raw)
        assert inv[0]["min_signed"] == -32768
        assert inv[0]["max_signed"] == -32768
        assert inv[1]["min_signed"] == 32767
        assert inv[1]["max_signed"] == 32767

    def test_count_unavailable(self):
        # word 0: two 0xFFFF, one normal
        raw = self._make_raw([[0xFFFF, 0], [0xFFFF, 0], [0x1234, 0]])
        inv = sample_word_inventory(raw)
        assert inv[0]["count_unavailable"] == 2
        assert inv[1]["count_unavailable"] == 0

    def test_count_zero(self):
        raw = self._make_raw([[0, 0], [0, 1], [1, 1]])
        inv = sample_word_inventory(raw)
        assert inv[0]["count_zero"] == 2
        assert inv[1]["count_zero"] == 1

    def test_unique_count(self):
        raw = self._make_raw([[1, 1], [2, 1], [2, 2]])
        inv = sample_word_inventory(raw)
        assert inv[0]["unique_count"] == 2   # values: 1, 2
        assert inv[1]["unique_count"] == 2   # values: 1, 2

    def test_is_constant_true(self):
        raw = self._make_raw([[42, 99]] * 5)
        inv = sample_word_inventory(raw)
        assert inv[0]["is_constant"] is True
        assert inv[1]["is_constant"] is True

    def test_is_constant_false(self):
        raw = self._make_raw([[1, 5], [2, 5], [1, 5]])
        inv = sample_word_inventory(raw)
        assert inv[0]["is_constant"] is False
        assert inv[1]["is_constant"] is True

    def test_inventory_dict_keys(self):
        raw = self._make_raw([[0]] * 3)
        inv = sample_word_inventory(raw)
        expected_keys = {
            "word_index", "min_unsigned", "max_unsigned",
            "min_signed", "max_signed", "count_unavailable",
            "count_zero", "unique_count", "is_constant",
        }
        assert set(inv[0].keys()) == expected_keys

    def test_single_sample_single_word(self):
        raw = self._make_raw([[0xABCD]])
        inv = sample_word_inventory(raw)
        assert len(inv) == 1
        assert inv[0]["min_unsigned"] == 0xABCD
        assert inv[0]["max_unsigned"] == 0xABCD
        assert inv[0]["unique_count"] == 1
        assert inv[0]["is_constant"] is True


# ── parse_ben5k_slow() end-to-end tests ──────────────────────────────────────

class TestParseBen5kSlow:
    def _parse(self, **kwargs):
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        data = _make_slow_fixture(**kwargs)
        return parse_ben5k_slow(data)

    def test_returns_ben_record(self):
        from app.providers.ben.model import BenRecord
        record = self._parse()
        assert isinstance(record, BenRecord)

    def test_record_class_is_slow_legacy(self):
        from app.providers.ben.model import BenRecordClass
        record = self._parse()
        assert record.header.record_class == BenRecordClass.BEN5K_SLOW_LEGACY

    def test_sample_words_shape(self):
        record = self._parse(sample_count=7, words_per_sample=5)
        assert record.sample_words.shape == (7, 5)

    def test_value_channels_from_tentative_only(self):
        ch1 = _build_channel_descriptor("FREQ BDNG 1", selector=0x0100)  # wi=1 TENTATIVE
        ch2 = _build_channel_descriptor("OOR CHAN", selector=0x2000)      # wi=32 OOR
        g = _build_group(0, "SENS BDNG 1", [ch1, ch2])
        # Pass just the one group; _make_slow_fixture fills the remaining 8 with empty.
        data = _make_slow_fixture(groups=[g], words_per_sample=4)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        names = [ch.name for ch in record.value_channels]
        assert "FREQ BDNG 1" in names
        assert "OOR CHAN" not in names

    def test_value_channel_scale_and_unit(self):
        ch = _build_channel_descriptor("FREQ BDNG 1", selector=0x0100)
        g = _build_group(0, "SENS BDNG 1", [ch])
        data = _make_slow_fixture(groups=[g], words_per_sample=4)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        ch_out = record.value_channel("FREQ BDNG 1")
        assert ch_out.scale == 1.0
        assert ch_out.offset == 0.0
        assert ch_out.unit == "raw"

    def test_value_channel_bay_name_is_group_name(self):
        ch = _build_channel_descriptor("MVAR BDNG 1", selector=0x0200)
        g = _build_group(0, "SENS BDNG 1", [ch])
        data = _make_slow_fixture(groups=[g], words_per_sample=4)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        ch_out = record.value_channel("MVAR BDNG 1")
        assert ch_out.bay_name == "SENS BDNG 1"

    def test_value_channel_slot_word_index(self):
        ch = _build_channel_descriptor("POWER BDNG 1", selector=0x0400)  # wi=4
        g = _build_group(0, "SENS BDNG 1", [ch])
        data = _make_slow_fixture(groups=[g], words_per_sample=6)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        ch_out = record.value_channel("POWER BDNG 1")
        assert ch_out.slot.word_index == 4

    def test_raw_values_signed(self):
        # Payload word at index 1 is 0x8000 = -32768 signed
        payload_words = [[0xDEAD, 0x8000, 0x0001, 0x0000]] * 3
        ch = _build_channel_descriptor("FREQ", selector=0x0100)
        g = _build_group(0, "SENS TEST", [ch])
        data = _make_slow_fixture(
            sample_count=3, words_per_sample=4,
            groups=[g], payload_words=payload_words,
        )
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        ch_out = record.value_channel("FREQ")
        raw = record.raw_values(ch_out)
        assert all(v == -32768 for v in raw)

    def test_digital_channels_empty(self):
        record = self._parse()
        assert record.digital_channels == ()

    def test_diagnostics_always_present(self):
        record = self._parse()
        codes = {d.code for d in record.diagnostics}
        assert "time_basis_unconfirmed" in codes
        assert "layout_ben5k_slow_legacy" in codes
        assert "ben5k_slow_mapping_tentative" in codes

    def test_oor_diagnostic_present_when_oor_exists(self):
        ch_oor = _build_channel_descriptor("OOR CH", selector=0x2000)  # wi=32
        g = _build_group(0, "SENS TEST", [ch_oor])
        data = _make_slow_fixture(groups=[g], words_per_sample=4)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        codes = {d.code for d in record.diagnostics}
        assert "ben5k_slow_oor_channels" in codes

    def test_no_oor_diagnostic_when_no_oor(self):
        ch_ok = _build_channel_descriptor("OK CH", selector=0x0100)  # wi=1
        g = _build_group(0, "SENS TEST", [ch_ok])
        data = _make_slow_fixture(groups=[g], words_per_sample=4)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(data)
        codes = {d.code for d in record.diagnostics}
        assert "ben5k_slow_oor_channels" not in codes

    def test_station_name_in_header(self):
        record = self._parse(station="GRNE")
        assert record.header.station_name == "GRNE"

    def test_trigger_time_utc_is_aware(self):
        from datetime import timezone
        record = self._parse()
        assert record.header.trigger_time_utc.tzinfo is not None
        assert record.header.trigger_time_utc.tzinfo == timezone.utc

    def test_sample_count_matches_header(self):
        record = self._parse(sample_count=12)
        assert record.header.sample_count == 12
        assert record.sample_count == 12
        assert record.sample_words.shape[0] == 12

    def test_config_unit_mismatch_diagnostic(self):
        # Patch config header recorder_unit to mismatch fixed header
        data = bytearray(_make_slow_fixture(recorder_unit=1547))
        # Config header recorder unit is at 0xDC + 10 = 0xE6
        struct.pack_into("<H", data, 0xDC + 10, 9999)
        from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow
        record = parse_ben5k_slow(bytes(data))
        codes = {d.code for d in record.diagnostics}
        assert "ben5k_slow_config_unit_mismatch" in codes
