"""GPTH 2022 legacy 28 ff Slow: independently validated, configuration-bounded.

This is separate from both the Fast AC decoder and the frozen GRNE 29 ff study.
The catalog's 0x1300 frames explicitly address physical payload words. Calculated
samples are full signed int16; effective gain is catalog gain / 16, offset intact.
No physical instrument calibration or general legacy Slow contract is claimed.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import math
import struct

import numpy as np

from app.providers.ben import layout
from app.providers.ben.errors import BenStructureError, BenUnsupportedVariantError
from app.providers.ben.legacy_ben5k.normalize import _build_header
from app.providers.ben.legacy_ben5k.reader import read_header, _payload_offset
from app.providers.ben.model import (
    BenChannelKind, BenDiagnostic, BenDigitalChannel, BenDigitalSource,
    BenRecord, BenSampleSlot, BenValueChannel,
)

CONFIGURATION_SHA256 = "3caff3c4cccef555d7521da101ff722bcb162200afdcf5ba1941e1457addff38"
_FOOTER = bytes.fromhex("ff ff 70 00 02 00 00 ff 6f 00")
# Native quantity, native unit, literal unit -> canonical metadata.
_QUANTITIES = {
    (0x1D, 5, b"Hz"): ("frequency", "Hz", 33, 0),
    (0x1E, 2, b"MW"): ("active_power", "MW", 38, 6),
}


def _name(raw: bytes) -> str:
    name, _, padding = raw.partition(b"\x00")
    if not name.strip() or any(padding) or any(b < 32 or b > 126 for b in name):
        raise BenStructureError("Legacy Slow catalog name is invalid")
    return name.decode("ascii")


def _read_catalog(data: bytes, end: int, words: int):
    """Read all addressed frames, accounting for every byte through the footer.

    Analog frames: 4-byte physical address + 56-byte calculated descriptor.
    Binary frames: 4-byte address + consecutive 24-byte indication descriptors.
    The two 3-byte group boundaries are retained as framing, not channel selectors.
    Caller must establish the reviewed configuration fingerprint first.
    """
    start = data.find(b"\x00\x13\x00\x00\x06", layout.HEADER_SIZE, end)
    if start < 0:
        raise BenStructureError("Legacy Slow acquisition catalog is absent")
    values: list[BenValueChannel] = []
    digitals: list[BenDigitalChannel] = []
    pos = start
    for word in range(words):
        if pos + 6 > end or data[pos:pos + 4] != struct.pack("<HH", 0x1300, word):
            raise BenStructureError("Legacy Slow physical-word frames are incomplete or conflicting", offset=pos)
        frame = pos
        tag = struct.unpack_from("<H", data, pos + 4)[0]
        if tag & 0xF0FF == 0x3006:
            if pos + 60 > end:
                raise BenStructureError("Legacy Slow calculated descriptor is truncated", offset=pos)
            channel_id = struct.unpack_from("<H", data, pos + 6)[0]
            quantity, unit = data[pos + 10:pos + 12]
            coding = (quantity, unit, data[pos + 28:pos + 30])
            if coding not in _QUANTITIES:
                raise BenUnsupportedVariantError("Legacy Slow calculated quantity/unit is not validated", offset=pos)
            measurement, unit_name, unit_code, exponent = _QUANTITIES[coding]
            gain, bias, low, high = struct.unpack_from("<ffff", data, pos + 36)
            if not all(math.isfinite(v) for v in (gain, bias, low, high)) or low >= high:
                raise BenStructureError("Legacy Slow calculated coefficients are invalid", offset=pos)
            values.append(BenValueChannel(
                index=len(values), channel_id=channel_id, name=_name(data[pos + 12:pos + 28]),
                kind=BenChannelKind.CALCULATED, measurement=measurement, unit=unit_name,
                unit_code=unit_code, unit_multiplier_exponent=exponent,
                phase=None, phase_code=0, quantity_code=quantity,
                scale=gain / 16.0, offset=bias, primary_rating=None, secondary_rating=None,
                bay_name=None, trigger_id=0, event_id=0, hardware_address=None,
                slot=BenSampleSlot(word_index=word, bit=0, slot_kind=tag),
                # No missing-value marker is independently established for this
                # profile. Preserve 0x0800 numerically, exactly as the CFG/DAT do.
                invalid_raw_value=None, descriptor_raw=data[frame:frame + 60],
            ))
            pos += 60
        elif tag == 0x3705:
            pos += 4
            bits: set[int] = set()
            while pos + 2 <= end and data[pos:pos + 2] == b"\x05\x37":
                if pos + 24 > end:
                    raise BenStructureError("Legacy Slow binary descriptor is truncated", offset=pos)
                bit, source_id = struct.unpack_from("<H", data, pos + 2)[0], struct.unpack_from("<H", data, pos + 6)[0]
                if bit >= 16 or bit in bits:
                    raise BenStructureError("Legacy Slow binary bits conflict", offset=pos)
                bits.add(bit)
                digitals.append(BenDigitalChannel(
                    index=len(digitals), event_id=source_id, name=_name(data[pos + 8:pos + 24]),
                    event_name=_name(data[pos + 8:pos + 24]), source=BenDigitalSource.DERIVED,
                    bit_channel_id=source_id, source_channel_id=source_id, bay_name=None,
                    slot=BenSampleSlot(word_index=word, bit=bit, slot_kind=tag), active_low=True,
                ))
                pos += 24
        else:
            raise BenUnsupportedVariantError("Legacy Slow acquisition frame type is not validated", offset=pos)
        if data[pos:pos + 3] in (b"\xff\x03\x01", b"\xff\x05\x02"):
            pos += 3
    ids = [c.channel_id for c in values]
    if (pos != end or len(values) != 20 or len(digitals) != 20 or len(set(ids)) != 20
            or sorted(c.source_channel_id for c in digitals) != sorted(ids)):
        raise BenStructureError("Legacy Slow catalog does not contain the complete reviewed inventory")
    return tuple(values), tuple(digitals)


def parse_gpth_slow(data: bytes) -> BenRecord:
    """Decode only the reviewed legacy 28 ff Slow configuration; refuse others."""
    data = bytes(data)
    header = read_header(data)
    if (data[:4] != layout.BEN_FAMILY_SIGNATURE or data[4:12] != layout.BEN5K_LAYOUT_SIGNATURE
            or data[14:16] != layout.BEN5K_GENERATION_MARKER
            or data[layout.RECORD_CLASS_FLAG_OFFSET] != 1):
        raise BenUnsupportedVariantError("Not the supported legacy 28 ff Slow record class")
    payload = _payload_offset(data, header)
    if hashlib.sha256(data[layout.HEADER_SIZE:payload]).hexdigest() != CONFIGURATION_SHA256:
        raise BenUnsupportedVariantError("Legacy 28 ff Slow configuration has no validated engineering contract")
    if (header.words_per_sample != 23 or struct.unpack_from("<I", data, layout.RATE_FIELD_OFFSET)[0] != 20_000
            or header.pre_trigger > header.sample_count or data[payload - 10:payload] != _FOOTER):
        raise BenStructureError("Legacy Slow acquisition header disagrees with the reviewed configuration")
    values, digitals = _read_catalog(data, payload - len(_FOOTER), header.words_per_sample)
    native_header = replace(
        _build_header(header, data), record_class_code=1,
        record_number=struct.unpack_from("<I", data, layout.RECORD_NUMBER_OFFSET)[0],
    )
    sample_words = np.frombuffer(data, dtype=layout.SAMPLE_WORD_DTYPE, offset=payload).reshape(
        header.sample_count, header.words_per_sample,
    )
    return BenRecord(
        header=native_header, value_channels=values, digital_channels=digitals, sample_words=sample_words,
        diagnostics=(
            BenDiagnostic("ben5k_gpth_slow_reviewed_configuration", "info",
                          "Reviewed GPTH 28 ff Slow: physical words from 0x1300 frames; "
                          "signed int16 * (catalog gain / 16) + catalog offset; " + CONFIGURATION_SHA256),
            BenDiagnostic("time_basis_unconfirmed", "warning",
                          "Legacy BEN5K recorder clock time basis remains unconfirmed"),
        ),
    )
