"""Config-area reader for the BEN5K flat binary layout.

Extracts the fixed header fields and channel descriptors from the flat
configuration area that starts at offset 0xDC. There is no typed-section
framing; the layout is entirely position- and stride-based.

All byte offsets are documented in:
  docs/project-memory/LEGACY_BEN5K_DECODER_DESIGN.md

Confirmed by direct binary analysis of:
  261016_180314535_GPTH_275kV.ben
  SHA-256: 55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from app.providers.ben.errors import BenStructureError, BenTruncatedError

# ── Fixed header field offsets (shared with SubBen family) ───────────────────

_STATION_NAME_OFFSET = 0x10
_STATION_NAME_SIZE = 0x28
_RATE_FIELD_OFFSET = 0x54          # u32le, µHz ÷ 1000 → samples/s
_PRE_TRIGGER_OFFSET = 0x58         # u32le
_SAMPLE_COUNT_OFFSET = 0x5C        # u32le
_WORDS_PER_SAMPLE_OFFSET = 0x60    # u16le (97 in GPTH); bytes 0x62-0x63 are NOT part of this field
_TRIGGER_TIME_OFFSET = 0x64        # 9 bytes: YY MM DD HH MM SS hh tt µµ
_LAST_SAMPLE_INDEX_OFFSET = 0x7A   # u32le, must equal sample_count − 1
_HEADER_END = 0xDC                 # flat config area starts here

# ── Config-area sub-section offsets (derived from binary analysis) ────────────

_LONG_FEEDER_DESC_OFFSET = 0x12C   # 12 entries × 129 bytes
_LONG_FEEDER_DESC_STRIDE = 129
_LONG_FEEDER_DESC_COUNT = 12

_SENSOR_NAME_GROUP_OFFSET = 0x73C  # stride 20: 16-byte name + 4 meta bytes
_SENSOR_NAME_GROUP_STRIDE = 20

_SHORT_FEEDER_NAME_OFFSET = 0xAAE  # 12 entries × 22 bytes
_SHORT_FEEDER_NAME_STRIDE = 22
_SHORT_FEEDER_NAME_COUNT = 12
_SHORT_FEEDER_NAME_END = 0xBB6     # end of short feeder name region
_FIRST_DESCRIPTOR_OFFSET = 0xBBA   # confirmed first channel descriptor (TBIN1 VR)

# ── Channel descriptor constants ──────────────────────────────────────────────

_DESC_SIZE = 58

# Analog descriptor field offsets (from descriptor start)
_ANALOG_TYPE_BYTE = 0       # 0x00=voltage, 0x04=current
_ANALOG_PHASE_SEQ = 1       # 1=R, 2=Y, 3=B, 4=N
_ANALOG_CLASS_CODE = 2      # u16le: 0x0528=VR, 0x0488=VY, 0x03E8=VB, etc.
_ANALOG_NAME = 4            # 16 bytes NUL-padded ASCII
_ANALOG_SCALE = 28          # f32le
_ANALOG_OFFSET = 32         # f32le
_ANALOG_LOW_RANGE = 36      # f32le
_ANALOG_HIGH_RANGE = 40     # f32le
_ANALOG_WORD_INDEX = 53     # u8, 0-indexed sample word slot (CONFIRMED)
_DESC_TERMINATOR = 57       # must be 0xFF

# Digital descriptor discriminator: byte 3 of the descriptor is 0xFF
_DIGITAL_TYPE_MARKER_OFFSET = 3
_DIGITAL_TYPE_MARKER = 0xFF

# Digital descriptor field offsets
_DIGITAL_POLARITY_FLAG = 0  # preserved raw; semantics unconfirmed
_DIGITAL_WORD_GROUP = 1     # 1-indexed group; maps to sample word via formula
_DIGITAL_BIT_INDEX = 2      # bit position within the digital word
_DIGITAL_NAME = 4           # 16 bytes NUL-padded ASCII

# Digital word_group → sample word index formula:
#   sample_word = _DIGITAL_WORD_GROUP_BASE + word_group
#
# CONFIRMED by direct payload analysis of 261016_180314535_GPTH_275kV.ben:
#   - Active analog occupies words 0-37 (5 feeders × 8 slots, 38 active words)
#   - Digital bitmask words are at 38-42 (quiescent 0xFFFF, narrow range ~900)
#   - word_group ∈ {1..5} → sample words 38..42  ✓
#   - word_group ≥ 6 → sample words ≥ 43 (constant 0x0800 inactive-feeder region;
#     those 120 digital channels have no real digital data in this recording)
# NOTE: SDAI2 IB (wi=38) and SDAI2 IN (wi=39) descriptors were previously excluded
# because their logical word_index values appeared to fall in the digital region.
# Stage 10 confirmed that two phantom descriptors shift their physical positions to
# 36 and 37 respectively — both within the analog region.  classify_channels() now
# correctly detects the phantoms and includes SDAI2 IB/IN in recorded_analog.
_DIGITAL_WORD_GROUP_BASE = 37  # digital_sample_word = 37 + word_group  (CONFIRMED)

# Valid type bytes for analog channels: 0x00=voltage, 0x04=current.
# False-positive positions in the config area (e.g. 4 bytes into a digital
# descriptor's name field) have b0 = printable ASCII bytes like 0x54='T',
# which this filter rejects.
_ANALOG_TYPE_BYTES: frozenset[int] = frozenset({0x00, 0x04})

_ANALOG_CLASS_CODES: dict[int, str] = {
    0x0528: "VR",
    0x0488: "VY",
    0x03E8: "VB",
    0x021C: "IR",
    0x0190: "IY",
    0x00F0: "IB",
    0x0050: "IN",
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Ben5kHeader:
    """Fields extracted from the fixed header (0x00–0xDB)."""
    station_name: str
    rate_hz: int            # samples per second
    pre_trigger: int        # sample count before trigger
    sample_count: int       # total samples
    words_per_sample: int
    trigger_bytes: bytes    # raw 9-byte timestamp; decode in normalize.py


@dataclass(frozen=True)
class Ben5kAnalogChannel:
    """One analog (sampled) channel from the flat config descriptors."""
    name: str
    word_index: int         # 0-indexed logical slot from descriptor byte 53
    scale: float            # f32le from descriptor bytes 28-31
    offset: float           # f32le from descriptor bytes 32-35
    low_range: float
    high_range: float
    type_byte: int          # 0x00=voltage, 0x04=current
    phase_seq: int          # 1=R, 2=Y, 3=B, 4=N
    class_code: int         # u16le channel-type template
    descriptor_offset: int  # byte offset of the descriptor start in the file
    # Physical payload word index, set by classify_channels() when sample data
    # is available for phantom detection.  Defaults to word_index (1:1 mapping)
    # when classify_channels() is called without sample_words.
    physical_word_index: int = 0  # 0 is a valid physical word; see below

    def __post_init__(self) -> None:
        # When the field is left at its dataclass default of 0 but word_index
        # is non-zero, it means classify_channels has not yet been called.
        # We cannot mutate a frozen dataclass, so callers must either set this
        # field explicitly or rely on classify_channels to return corrected
        # instances via dataclasses.replace().
        pass


@dataclass(frozen=True)
class Ben5kDigitalChannel:
    """One digital (binary) channel from the flat config descriptors."""
    name: str
    word_group: int         # 1-indexed group (maps to sample word via formula above)
    bit_index: int          # bit position within the digital word (0=LSB)
    polarity_flag: int      # raw byte; active-low assumed (same as SubBen convention)
    descriptor_offset: int  # byte offset of the descriptor start in the file

    @property
    def sample_word_index(self) -> int:
        """Sample word slot: 37 + word_group (formula confirmed by payload analysis)."""
        return _DIGITAL_WORD_GROUP_BASE + self.word_group


# ── Reader functions ──────────────────────────────────────────────────────────

def read_header(data: bytes) -> Ben5kHeader:
    """Extract fixed header fields from BEN5K file bytes."""
    if len(data) < _HEADER_END:
        raise BenTruncatedError(
            f"file is {len(data)} bytes, too short for the BEN5K header ({_HEADER_END})"
        )

    station_raw = data[_STATION_NAME_OFFSET : _STATION_NAME_OFFSET + _STATION_NAME_SIZE]
    station = station_raw.split(b"\x00")[0].decode("latin-1", errors="replace")

    rate_field = struct.unpack_from("<I", data, _RATE_FIELD_OFFSET)[0]
    pre_trigger = struct.unpack_from("<I", data, _PRE_TRIGGER_OFFSET)[0]
    sample_count = struct.unpack_from("<I", data, _SAMPLE_COUNT_OFFSET)[0]
    words_per_sample = struct.unpack_from("<H", data, _WORDS_PER_SAMPLE_OFFSET)[0]
    last_sample_index = struct.unpack_from("<I", data, _LAST_SAMPLE_INDEX_OFFSET)[0]

    if rate_field == 0:
        raise BenStructureError("BEN5K rate field is zero", offset=_RATE_FIELD_OFFSET)
    if sample_count == 0:
        raise BenStructureError("BEN5K record declares zero samples", offset=_SAMPLE_COUNT_OFFSET)
    if words_per_sample == 0:
        raise BenStructureError(
            "BEN5K record declares zero words per sample", offset=_WORDS_PER_SAMPLE_OFFSET
        )
    if last_sample_index != sample_count - 1:
        raise BenStructureError(
            f"BEN5K last-sample index {last_sample_index} disagrees with "
            f"sample count {sample_count}",
            offset=_LAST_SAMPLE_INDEX_OFFSET,
        )

    rate_hz = rate_field // 1000

    trigger_bytes = bytes(data[_TRIGGER_TIME_OFFSET : _TRIGGER_TIME_OFFSET + 9])

    return Ben5kHeader(
        station_name=station,
        rate_hz=rate_hz,
        pre_trigger=pre_trigger,
        sample_count=sample_count,
        words_per_sample=words_per_sample,
        trigger_bytes=trigger_bytes,
    )


def _payload_offset(data: bytes, header: Ben5kHeader) -> int:
    """Compute the byte offset where the sample payload starts (counted from EOF)."""
    payload_bytes = header.sample_count * header.words_per_sample * 2
    offset = len(data) - payload_bytes
    if offset <= _HEADER_END:
        raise BenStructureError(
            f"BEN5K payload size ({payload_bytes}) leaves no room for a config area"
        )
    return offset


def read_channel_descriptors(
    data: bytes,
    header: Ben5kHeader,
) -> tuple[list[Ben5kAnalogChannel], list[Ben5kDigitalChannel]]:
    """Walk the flat channel descriptor area and return analog and digital channels.

    Descriptors are 58 bytes each and start at _SHORT_FEEDER_NAME_END (0xBB6).
    The walk stops when the payload area is reached.  Within each descriptor,
    byte 3 == 0xFF discriminates digital from analog.

    Confirmed facts:
    - First analog descriptor starts at 0xBBA (_FIRST_DESCRIPTOR_OFFSET).
    - All 22 hand-confirmed channels match their sample-word signals correctly.
    - word_index (byte 53) is 0-indexed.
    - Analog descriptor: byte[3] != 0xFF AND byte[57] == 0xFF AND byte[0] in {0x00, 0x04}.
    - Digital descriptor: byte[3] == 0xFF (digital type marker); byte[57] is NOT 0xFF.
    - Walk uses a sliding window (advance +1 when current position doesn't match
      either analog or digital criteria) to handle the non-uniform inter-descriptor
      gaps in the BEN5K flat config area.
    - Name filter: non-empty, first character is printable ASCII and not '-'.
    """
    end = _payload_offset(data, header)
    analog: list[Ben5kAnalogChannel] = []
    digital: list[Ben5kDigitalChannel] = []

    off = _FIRST_DESCRIPTOR_OFFSET
    while off + _DESC_SIZE <= end:
        b0   = data[off + _ANALOG_TYPE_BYTE]
        b3   = data[off + _DIGITAL_TYPE_MARKER_OFFSET]
        b57  = data[off + _DESC_TERMINATOR]

        name_raw = data[off + _ANALOG_NAME : off + _ANALOG_NAME + 16]
        name_bytes = name_raw.split(b"\x00")[0]
        # Valid name: non-empty, first byte is printable ASCII and not '-'
        if (
            name_bytes
            and 0x20 <= name_bytes[0] <= 0x7E
            and name_bytes[0] != 0x2D  # not '-'
        ):
            name = name_bytes.decode("latin-1", errors="replace").strip()
        else:
            name = ""

        if b3 == _DIGITAL_TYPE_MARKER and name:
            digital.append(
                Ben5kDigitalChannel(
                    name=name,
                    word_group=data[off + _DIGITAL_WORD_GROUP],
                    bit_index=data[off + _DIGITAL_BIT_INDEX],
                    polarity_flag=data[off + _DIGITAL_POLARITY_FLAG],
                    descriptor_offset=off,
                )
            )
            off += _DESC_SIZE
        elif b3 != _DIGITAL_TYPE_MARKER and b57 == 0xFF and b0 in _ANALOG_TYPE_BYTES and name:
            word_index = data[off + _ANALOG_WORD_INDEX]
            scale, offset_val, low_r, high_r = struct.unpack_from("<ffff", data, off + _ANALOG_SCALE)
            class_code = struct.unpack_from("<H", data, off + _ANALOG_CLASS_CODE)[0]
            analog.append(
                Ben5kAnalogChannel(
                    name=name,
                    word_index=word_index,
                    physical_word_index=word_index,  # overridden by classify_channels
                    scale=scale,
                    offset=offset_val,
                    low_range=low_r,
                    high_range=high_r,
                    type_byte=b0,
                    phase_seq=data[off + _ANALOG_PHASE_SEQ],
                    class_code=class_code,
                    descriptor_offset=off,
                )
            )
            off += _DESC_SIZE
        else:
            off += 1

    return analog, digital


def read_feeder_names(data: bytes) -> list[str]:
    """Return the 12 short feeder names from the config area."""
    names: list[str] = []
    off = _SHORT_FEEDER_NAME_OFFSET
    for _ in range(_SHORT_FEEDER_NAME_COUNT):
        raw = data[off : off + 13].split(b"\x00")[0]
        names.append(raw.decode("latin-1", errors="replace").strip())
        off += _SHORT_FEEDER_NAME_STRIDE
    return names
