"""Count-derived descriptor bounds and rejection of ambiguous flat records."""
import json
from pathlib import Path
import struct

import pytest

from app.providers.ben.errors import BenStructureError, BenTruncatedError, BenUnsupportedVariantError
from app.providers.ben.legacy_ben5k.reader import (
    read_header, read_descriptor_region, read_channel_descriptors, _read_structured_descriptors,
)
from test_ben5k_reader import _make_fixture, _build_digital_descriptor

EVIDENCE = json.loads((Path(__file__).parent / "fixtures/ben/ben5k_fast_ac_scaling.json").read_text())["bphe"]
DESCRIPTOR = bytes.fromhex(EVIDENCE["channels"][0]["descriptor"]["raw_hex"])
FOOTER = bytes.fromhex("ff ff 70 00 02 00 00 ff 6f 00")


def _flat_fixture(n=2, s=12, descriptors=DESCRIPTOR):
    data = bytearray(_make_fixture(sample_count=2, words_per_sample=24)[:0xDC])
    data.extend(bytes(0x12C - len(data)))
    data[0xED] = data[0xF6] = n
    data[0xF7] = s
    data[0xF8:0xFE] = b"SubBen"
    struct.pack_into("<H", data, 0x114, 24)
    data.extend(bytes(n * 129))
    for i in range(s):
        data.extend(bytes([1 + i % n, 0xFF, 0xC3, 7]) + b"SENSOR" + bytes(10))
    data.extend(b"\xff" * 6 + bytes(n * 22) + bytes(4))
    data.extend(descriptors + FOOTER + bytes(2 * 24 * 2))
    return bytes(data)


@pytest.mark.parametrize("n,s,start", [(1, 2, 501), (2, 12, 852), (6, 24, 1696), (12, 44, 3002)])
def test_region_follows_variable_tables_instead_of_gpth_or_bphe_fixed_offset(n, s, start):
    data = _flat_fixture(n, s)
    region = read_descriptor_region(data, read_header(data))
    assert (region.start, region.end) == (start, start + 58)
    analog, digital = _read_structured_descriptors(data, region)
    assert len(analog) == 1 and not digital
    assert analog[0].descriptor_offset == start


def test_names_are_not_descriptor_identity_and_prefix_payload_are_not_scanned():
    data = bytearray(_flat_fixture(descriptors=DESCRIPTOR * 2))
    data[0x12C:0x12C + 58] = DESCRIPTOR  # valid-looking bytes in a feeder text
    data[-96:-38] = DESCRIPTOR  # valid-looking bytes in sample words
    region = read_descriptor_region(data, read_header(data))
    analog, _ = _read_structured_descriptors(bytes(data), region)
    assert [c.name for c in analog] == ["YGPN/BBTU1 VR"] * 2
    assert [c.descriptor_offset for c in analog] == [region.start, region.start + 58]


@pytest.mark.parametrize("position,value", [(0, 3), (1, 0), (20, 0), (57, 0), (10, 1), (19, 1)])
def test_incomplete_signatures_control_characters_and_nonzero_name_padding_do_not_match(position, value):
    false = bytearray(DESCRIPTOR)
    false[position] = value
    data = _flat_fixture(descriptors=bytes(false) + DESCRIPTOR)
    region = read_descriptor_region(data, read_header(data))
    analog, _ = _read_structured_descriptors(data, region)
    assert [c.descriptor_offset for c in analog] == [region.start + 58]


def test_nonfinite_coefficients_are_not_descriptors():
    false = bytearray(DESCRIPTOR)
    struct.pack_into("<f", false, 28, float("nan"))
    data = _flat_fixture(descriptors=bytes(false))
    assert _read_structured_descriptors(data, read_descriptor_region(data, read_header(data))) == ([], [])


def test_overlapping_analog_and_digital_interpretations_are_rejected():
    digital = bytearray(_build_digital_descriptor("CONTACT", 1, 0))
    digital[20:22] = b"\x04\x05"
    overlapping = bytearray(54 + 58)
    overlapping[:58] = DESCRIPTOR
    overlapping[54:] = digital
    data = _flat_fixture(descriptors=bytes(overlapping))
    with pytest.raises(BenStructureError, match="overlap"):
        _read_structured_descriptors(data, read_descriptor_region(data, read_header(data)))


@pytest.mark.parametrize("position,value", [(0xED, 3), (0xF7, 255), (0x114, 25)])
def test_invalid_counts_width_or_truncated_tables_are_rejected(position, value):
    data = bytearray(_flat_fixture())
    data[position] = value
    with pytest.raises((BenStructureError, BenTruncatedError)):
        read_descriptor_region(bytes(data), read_header(data))


def test_truncated_descriptor_or_missing_footer_never_returns_partial_inventory():
    data = _flat_fixture()
    for damaged in (data[:-96 - 30] + data[-106:], data[:-106] + bytes(10) + data[-96:]):
        with pytest.raises((BenStructureError, BenTruncatedError)):
            read_descriptor_region(damaged, read_header(damaged))


def test_unreviewed_compact_bphe_configuration_never_falls_back_to_gpth_heuristic():
    data = _flat_fixture()
    with pytest.raises(BenUnsupportedVariantError, match="physical mapping is not established"):
        read_channel_descriptors(data, read_header(data))
