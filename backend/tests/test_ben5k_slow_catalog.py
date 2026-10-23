"""Synthetic tests for the BEN5K Slow extended catalog reader.

Covers read_extended_catalog():
  - Correct name decoding (bytes 6-25, not bytes 10-25)
  - LOGICAL (0x01:0x01) and DERIVED (0x04:0x33) record type classification
  - Channel ID extraction (u16le at bytes 2-3)
  - Flags extraction (u16le at bytes 4-5)
  - SubBen2 boundary: records before b"SubBen 2" only
  - Tail validation: records where bytes 26-29 != 0xFFFFFFFF are excluded
  - Returns empty list when SubBen 2 marker absent
  - Multiple records in sequence
  - Empty catalog section (SubBen 2 immediately after groups)

All assertions use synthetic bytes; the real GRNE recording is NOT read.
"""

from __future__ import annotations

import struct

import pytest

from app.providers.ben.legacy_ben5k_slow.reader import (
    ExtendedCatalogEntry,
    ExtendedCatalogEntryType,
    read_extended_catalog,
)

# ── Offset constants ──────────────────────────────────────────────────────────

_GROUPS_START = 0x013F
_GROUPS_END = _GROUPS_START + 9 * 252   # 0x0A1B
_RECORD_STRIDE = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_catalog_record(
    b0: int,
    b1: int,
    channel_id: int,
    flags: int,
    name: str,
    tail: bytes = b"\xff\xff\xff\xff",
) -> bytes:
    """Build a single 30-byte catalog record."""
    name_bytes = name.encode("latin-1")[:20]
    name_field = name_bytes.ljust(20, b"\x00")
    rec = bytes([b0, b1])
    rec += struct.pack("<H", channel_id)
    rec += struct.pack("<H", flags)
    rec += name_field
    rec += tail[:4]
    assert len(rec) == _RECORD_STRIDE
    return rec


def _make_file_with_catalog(records: list[bytes], after_catalog: bytes = b"") -> bytes:
    """Build a minimal BEN5K Slow file with the given catalog records.

    Pads the region before the catalog with zeroes and appends after_catalog.
    Does NOT include a valid file header or payload; sufficient for
    read_extended_catalog() which only needs the catalog section.
    """
    catalog = b"".join(records)
    # Pad from zero to catalog start
    prefix = b"\x00" * _GROUPS_END
    return prefix + catalog + after_catalog


# ── Tests: basic record parsing ───────────────────────────────────────────────

class TestReadExtendedCatalog:

    def test_empty_when_no_subben2_marker(self):
        # No "SubBen 2" marker → empty list
        rec = _build_catalog_record(0x01, 0x01, 44, 0xff00, "MVAR JJNG 1")
        data = _make_file_with_catalog([rec], after_catalog=b"\x00" * 100)
        result = read_extended_catalog(data)
        assert result == []

    def test_single_logical_record(self):
        rec = _build_catalog_record(0x01, 0x01, 44, 0xff00, "MVAR JJNG 1")
        data = _make_file_with_catalog([rec], after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert len(result) == 1
        entry = result[0]
        assert entry.entry_type == ExtendedCatalogEntryType.LOGICAL
        assert entry.channel_id == 44
        assert entry.flags == 0xff00
        assert entry.name == "MVAR JJNG 1"

    def test_single_derived_record(self):
        rec = _build_catalog_record(0x04, 0x33, 56, 0xff00, "FREQ BDNG 1")
        data = _make_file_with_catalog([rec], after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert len(result) == 1
        entry = result[0]
        assert entry.entry_type == ExtendedCatalogEntryType.DERIVED
        assert entry.channel_id == 56
        assert entry.name == "FREQ BDNG 1"

    def test_unknown_type_still_returned(self):
        rec = _build_catalog_record(0x02, 0x05, 99, 0xff00, "CUSTOM")
        data = _make_file_with_catalog([rec], after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert len(result) == 1
        assert result[0].entry_type == ExtendedCatalogEntryType.UNKNOWN

    def test_name_at_bytes_6_to_25_not_10_to_25(self):
        # Name "MVAR JJNG 1" is 11 chars; bytes 6-9 = "MVAR", bytes 10-25 = " JJNG 1..."
        # Correct decoding should give full "MVAR JJNG 1", not " JJNG 1"
        rec = _build_catalog_record(0x01, 0x01, 44, 0xff00, "MVAR JJNG 1")
        data = _make_file_with_catalog([rec], after_catalog=b"SubBen 2        ")
        entry = read_extended_catalog(data)[0]
        assert entry.name == "MVAR JJNG 1"
        assert not entry.name.startswith(" JJNG")

    def test_name_truncated_at_null(self):
        # 20-byte name field NUL-padded; longer suffix must be stripped
        rec = _build_catalog_record(0x01, 0x01, 45, 0xff00, "UR JJNG 2 RMS")
        data = _make_file_with_catalog([rec], after_catalog=b"SubBen 2        ")
        entry = read_extended_catalog(data)[0]
        assert entry.name == "UR JJNG 2 RMS"
        assert "\x00" not in entry.name

    def test_name_20_chars_no_null(self):
        # Exactly 20 chars, no NUL (still valid, no termination needed)
        rec = _build_catalog_record(0x01, 0x01, 60, 0xff00, "ABCDEFGHIJKLMNOPQRST")
        data = _make_file_with_catalog([rec], after_catalog=b"SubBen 2        ")
        entry = read_extended_catalog(data)[0]
        assert entry.name == "ABCDEFGHIJKLMNOPQRST"

    def test_multiple_records_in_order(self):
        recs = [
            _build_catalog_record(0x01, 0x01, 44, 0xff00, "MVAR JJNG 1"),
            _build_catalog_record(0x01, 0x01, 45, 0xff00, "UR JJNG 2 RMS"),
            _build_catalog_record(0x04, 0x33, 56, 0xff00, "FREQ BDNG 1"),
        ]
        data = _make_file_with_catalog(recs, after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert len(result) == 3
        assert result[0].channel_id == 44
        assert result[1].channel_id == 45
        assert result[2].channel_id == 56
        assert result[2].entry_type == ExtendedCatalogEntryType.DERIVED

    def test_record_offsets_are_correct(self):
        recs = [
            _build_catalog_record(0x01, 0x01, 44, 0xff00, "MVAR JJNG 1"),
            _build_catalog_record(0x01, 0x01, 45, 0xff00, "UR JJNG 2 RMS"),
        ]
        data = _make_file_with_catalog(recs, after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert result[0].record_offset == _GROUPS_END
        assert result[1].record_offset == _GROUPS_END + _RECORD_STRIDE

    def test_tail_validation_excludes_bad_tail(self):
        # Record with bad tail is excluded
        bad_rec = _build_catalog_record(0x01, 0x01, 99, 0xff00, "BAD", tail=b"\x00\x00\x00\x00")
        good_rec = _build_catalog_record(0x01, 0x01, 44, 0xff00, "GOOD")
        # Place bad first, good second
        data = _make_file_with_catalog([bad_rec, good_rec], after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        # Only the good record should be returned
        assert len(result) == 1
        assert result[0].name == "GOOD"

    def test_empty_catalog_section_when_subben2_immediately_after_groups(self):
        # SubBen 2 starts right at the group end; zero records
        data = _make_file_with_catalog([], after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert result == []

    def test_flags_primary_vs_secondary(self):
        # flags=0xff00 = primary, flags=0xff01 = secondary substation
        recs = [
            _build_catalog_record(0x01, 0x01, 44, 0xff00, "MVAR JJNG 1"),
            _build_catalog_record(0x01, 0x01, 44, 0xff01, "P AUTO TF1"),
        ]
        data = _make_file_with_catalog(recs, after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert len(result) == 2
        assert result[0].flags == 0xff00
        assert result[1].flags == 0xff01

    def test_stop_at_subben2_boundary(self):
        # Records BEFORE the SubBen 2 marker should be included;
        # the SubBen 2 data itself must not be parsed as catalog records
        recs = [
            _build_catalog_record(0x01, 0x01, 44, 0xff00, "BEFORE"),
            _build_catalog_record(0x01, 0x01, 45, 0xff00, "ALSO BEFORE"),
        ]
        # SubBen 2 arrives exactly at the end of the two records
        data = _make_file_with_catalog(recs, after_catalog=b"SubBen 2        " + b"\xff" * 200)
        result = read_extended_catalog(data)
        assert len(result) == 2
        assert all(e.name in ("BEFORE", "ALSO BEFORE") for e in result)

    def test_partial_record_before_subben2_is_excluded(self):
        # 45 bytes of catalog (one full record + 15 extra) before SubBen 2:
        # only the 1 complete record should be returned
        rec = _build_catalog_record(0x01, 0x01, 44, 0xff00, "FULL")
        partial = b"\x01\x01" + b"\x00" * 13   # incomplete 15-byte fragment
        data = _make_file_with_catalog([rec, partial], after_catalog=b"SubBen 2        ")
        result = read_extended_catalog(data)
        assert len(result) == 1
        assert result[0].name == "FULL"

    def test_real_grne_catalog_entry_structure(self):
        # Regression: exact bytes for GRNE record 0 at 0x0a1b
        # 01 01 2c 00 00 ff 4d 56 41 52 20 4a 4a 4e 47 20 31 00 00 00 00 00 ff ff ff ff ff ff ff ff
        raw = bytes([
            0x01, 0x01, 0x2c, 0x00, 0x00, 0xff,
            0x4d, 0x56, 0x41, 0x52, 0x20, 0x4a, 0x4a, 0x4e, 0x47, 0x20,
            0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,
            0xff, 0xff, 0xff, 0xff,
        ])
        assert len(raw) == 30
        data = b"\x00" * _GROUPS_END + raw + b"SubBen 2        "
        result = read_extended_catalog(data)
        assert len(result) == 1
        e = result[0]
        assert e.entry_type == ExtendedCatalogEntryType.LOGICAL
        assert e.channel_id == 44   # 0x2c
        assert e.flags == 0xff00    # 0x00 0xff interpreted as u16le
        assert e.name == "MVAR JJNG 1"
        assert e.record_offset == _GROUPS_END
