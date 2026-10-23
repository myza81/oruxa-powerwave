"""Config-area reader for the BEN5K Slow flat binary layout.

The BEN5K Slow format uses a group-based config area starting at offset 0xDC:

  [0x00DC – 0x00FD]  Config header (34 bytes)
  [0x00FE – 0x013E]  HVDC Power formula descriptor (65 bytes)
  [0x013F – 0x0A1A]  Nine channel groups, 252 bytes each
  [0x0A1B – SubBen2] Extended catalog: 30-byte logical/derived channel records
  [SubBen2 – payload] SubBen 2 section: display-text strings for recorder panel

Each 252-byte channel group:
  [0  – 23]    SENS descriptor   24 bytes   (group header)
  [24 – 247]   Eight channel descriptor slots, 28 bytes each
  [248 – 251]  Group separator   4 bytes    (0xFF FF FF FF)

Word-index encoding:
  selector_u16le = struct.unpack_from('<H', descriptor, 0)[0]
  word_index_tentative = selector_u16le >> 8  (equivalent to // 256)

This formula is confirmed for Group 0 (BDNG 1):
  FREQ BDNG 1:  selector=0x0100, word_index=1  (raw 12898-13152, 49.6-50.6 Hz)
  MVAR BDNG 1:  selector=0x0200, word_index=2  (raw 13453-13720, ~13.5 Mvar)
  POWER BDNG 1: selector=0x0400, word_index=4  (raw 63-152, ~100 MW)

For groups with low-byte selectors (selector < 256), word_index_tentative == 0,
which is ambiguous (word 0 is a status/flag word in GRNE).  Those channels are
classified as UNRESOLVED.

Channels with word_index_tentative >= words_per_sample (e.g. POWER JJNG 1 at
word_index 32, UR JJNG 2 MAX at 64) cannot be decoded and are UNRESOLVED.

Confirmed by direct binary analysis of:
  GRNE230726_143432426.ben
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from app.providers.ben.errors import BenStructureError, BenTruncatedError

# ── Fixed header field offsets (same as BEN5K family) ─────────────────────────

_STATION_NAME_OFFSET = 0x10
_STATION_NAME_SIZE = 0x28
_RECORDER_UNIT_OFFSET = 0x0C
_RECORD_NUMBER_OFFSET = 0x38
_RATE_FIELD_OFFSET = 0x54
_PRE_TRIGGER_OFFSET = 0x58
_SAMPLE_COUNT_OFFSET = 0x5C
_WORDS_PER_SAMPLE_OFFSET = 0x60
_TRIGGER_TIME_OFFSET = 0x64
_LAST_SAMPLE_INDEX_OFFSET = 0x7A
_HEADER_END = 0xDC

# ── BEN5K Slow config area layout constants ───────────────────────────────────

_CONFIG_HEADER_OFFSET = 0x00DC
_CONFIG_HEADER_SIZE = 34
# Bytes within config header:
_CH_VERSION_OFFSET = 0          # u16le version/type
_CH_MARKER_OFFSET = 2           # u16le section marker (0xFF32 observed)
_CH_RECORDER_UNIT_OFFSET = 10   # u16le recorder unit cross-check
_CH_GROUP_COUNT_OFFSET = 12     # u16le primary group count (5 in GRNE)
_CH_STATION_OFFSET = 14         # 16-byte NUL-padded station name

_HVDC_FORMULA_OFFSET = 0x00FE
_HVDC_FORMULA_SIZE = 65
_HVDC_NAME_OFFSET = 4           # 16-byte NUL-padded name within formula descriptor
_HVDC_NAME_SIZE = 16
_HVDC_FORMULA_STRING_OFFSET = 38   # formula text within formula descriptor

_GROUPS_START_OFFSET = 0x013F
_GROUP_STRIDE = 252
_GROUP_COUNT = 9

# Within each 252-byte group:
_SENS_SIZE = 24                  # SENS descriptor size
_CHANNEL_SLOT_SIZE = 28          # one channel descriptor size
_CHANNEL_SLOTS_PER_GROUP = 8     # confirmed: 252 = 24 + 8×28 + 4
_GROUP_SEPARATOR_SIZE = 4        # ff ff ff ff at bytes [248–251]

# SENS descriptor field offsets (from SENS start):
_SENS_TYPE_BYTE = 0              # 0x02 in GRNE
_SENS_SUB_TYPE = 1               # 0x3C in GRNE (constant)
_SENS_GROUP_INDEX = 2            # group index (0-based)
_SENS_DISCRIMINATOR = 3          # 0x00 = SENS descriptor
_SENS_NAME_OFFSET = 4            # 16-byte NUL-padded name
_SENS_NAME_SIZE = 16
_SENS_META_OFFSET = 20           # 4 bytes, function not decoded

# Channel descriptor field offsets (from channel descriptor start):
_CH_SELECTOR_OFFSET = 0          # u16le word-index selector
_CH_RESERVED_OFFSET = 2          # reserved byte
_CH_DISCRIMINATOR_OFFSET = 3     # 0xFF = channel slot (active or inactive)
_CH_NAME_OFFSET = 4              # 16-byte NUL-padded name
_CH_NAME_SIZE = 16
_CH_NAN_MARKER_OFFSET = 20       # u32le 0xFFFFFFFF = NaN/unavailable marker
_CH_SCALE_REF_OFFSET = 24        # 4 bytes, scale/unit reference (not decoded)

# Inactive channel detection: name starts with '-'
_INACTIVE_NAME_PREFIX = ord("-")

# ── Extended catalog layout constants ─────────────────────────────────────────

_EXT_CATALOG_OFFSET = _GROUPS_START_OFFSET + _GROUP_COUNT * _GROUP_STRIDE  # 0x0A1B
_EXT_RECORD_STRIDE = 30       # each 30-byte extended catalog record
_EXT_RECORD_TAIL = b"\xff\xff\xff\xff"  # bytes 26-29 of a valid catalog record

# Record-type byte pairs (bytes 0-1 of each 30-byte record):
_EXT_TYPE_LOGICAL = (0x01, 0x01)   # logical channel, unique id in bytes 2-3
_EXT_TYPE_DERIVED = (0x04, 0x33)   # derived/threshold channel, parent id in bytes 2-3

# Field offsets within a 30-byte record:
_EXT_ID_OFFSET = 2        # u16le channel ID
_EXT_FLAGS_OFFSET = 4     # u16le flags (0xFF00 = primary, 0xFF01 = secondary)
_EXT_NAME_OFFSET = 6      # 20-byte NUL-padded name (bytes 6-25)
_EXT_NAME_SIZE = 20
_EXT_TAIL_OFFSET = 26     # 4-byte tail (0xFFFFFFFF for valid records)

# SubBen 2 section boundary marker:
_SUBBEN2_MARKER = b"SubBen 2"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Ben5kSlowHeader:
    """Fields extracted from the fixed BEN5K Slow file header (0x00–0xDB)."""
    station_name: str
    recorder_unit: int
    record_number: int
    rate_hz: int            # samples per second
    pre_trigger: int        # samples before trigger
    sample_count: int
    words_per_sample: int
    trigger_bytes: bytes    # raw 9-byte timestamp; decoded in normalize.py


@dataclass(frozen=True)
class SlowConfigHeader:
    """Fields from the 34-byte BEN5K Slow config header at offset 0xDC."""
    version: int
    section_marker: int
    recorder_unit: int      # cross-check against fixed header
    primary_group_count: int
    station_name: str


@dataclass(frozen=True)
class SlowHvdcFormula:
    """Raw HVDC Power formula descriptor at offset 0xFE.

    The formula references channel IDs like 'C014+C041+C021+C019+178'.
    Decoding the formula is deferred; the raw bytes are preserved.
    """
    name: str
    raw_bytes: bytes


class SlowChannelStatus(Enum):
    """Mapping status of a BEN5K Slow channel descriptor."""
    #: Channel slot not in use (name == '----' or selector == 0 and name empty).
    INACTIVE = auto()
    #: word_index in range (0 < wi < words_per_sample); mapping is TENTATIVE.
    #: The word_index formula (selector >> 8) is confirmed for Group 0 only.
    #: Other groups use this formula tentatively pending oracle validation.
    TENTATIVE = auto()
    #: word_index == 0 for a named channel: selector has only its low byte set.
    #: Word 0 in GRNE is a status/flag word; mapping is ambiguous.
    UNRESOLVED_ZERO = auto()
    #: word_index >= words_per_sample: selector encodes a channel reference
    #: that is out of range for this recording's sample frame.
    UNRESOLVED_OOR = auto()
    #: word_index conflicts with a previously assigned channel.
    #: The word has already been claimed by an earlier group's channel.
    UNRESOLVED_CONFLICT = auto()


@dataclass(frozen=True)
class SlowChannelDescriptor:
    """One channel slot from a BEN5K Slow channel group.

    Inactive slots (name == '----') have status INACTIVE.
    All other slots carry a selector value and a tentative word_index.
    """
    name: str
    selector_raw: int           # raw u16le from descriptor bytes 0-1
    word_index_tentative: int   # selector_raw >> 8 (may be 0 or OOR)
    group_index: int            # 0-based group index this channel belongs to
    group_name: str             # SENS name of the group (e.g. 'SENS BDNG 1')
    slot_index: int             # 0-based slot within the group (0-7)
    descriptor_offset: int      # byte offset of this channel descriptor in the file
    status: SlowChannelStatus
    scale_ref_raw: bytes        # raw 4 bytes at descriptor+24; not yet decoded


@dataclass(frozen=True)
class SlowGroup:
    """One 252-byte BEN5K Slow channel group."""
    group_index: int
    group_name: str
    channels: tuple[SlowChannelDescriptor, ...]   # all 8 slots including INACTIVE


# ── Reader functions ──────────────────────────────────────────────────────────

def read_header(data: bytes) -> Ben5kSlowHeader:
    """Extract fixed header fields from BEN5K Slow file bytes."""
    if len(data) < _HEADER_END:
        raise BenTruncatedError(
            f"file is {len(data)} bytes, too short for the BEN5K Slow header ({_HEADER_END})"
        )

    station_raw = data[_STATION_NAME_OFFSET : _STATION_NAME_OFFSET + _STATION_NAME_SIZE]
    station = station_raw.split(b"\x00")[0].decode("latin-1", errors="replace")

    recorder_unit = struct.unpack_from("<H", data, _RECORDER_UNIT_OFFSET)[0]
    record_number = struct.unpack_from("<I", data, _RECORD_NUMBER_OFFSET)[0]
    rate_field = struct.unpack_from("<I", data, _RATE_FIELD_OFFSET)[0]
    pre_trigger = struct.unpack_from("<I", data, _PRE_TRIGGER_OFFSET)[0]
    sample_count = struct.unpack_from("<I", data, _SAMPLE_COUNT_OFFSET)[0]
    words_per_sample = struct.unpack_from("<H", data, _WORDS_PER_SAMPLE_OFFSET)[0]
    last_sample_index = struct.unpack_from("<I", data, _LAST_SAMPLE_INDEX_OFFSET)[0]

    if rate_field == 0:
        raise BenStructureError(
            "BEN5K Slow rate field is zero", offset=_RATE_FIELD_OFFSET
        )
    if sample_count == 0:
        raise BenStructureError(
            "BEN5K Slow record declares zero samples", offset=_SAMPLE_COUNT_OFFSET
        )
    if words_per_sample == 0:
        raise BenStructureError(
            "BEN5K Slow record declares zero words per sample",
            offset=_WORDS_PER_SAMPLE_OFFSET,
        )
    if last_sample_index != sample_count - 1:
        raise BenStructureError(
            f"BEN5K Slow last-sample index {last_sample_index} disagrees with "
            f"sample count {sample_count}",
            offset=_LAST_SAMPLE_INDEX_OFFSET,
        )

    return Ben5kSlowHeader(
        station_name=station,
        recorder_unit=recorder_unit,
        record_number=record_number,
        rate_hz=rate_field // 1000,
        pre_trigger=pre_trigger,
        sample_count=sample_count,
        words_per_sample=words_per_sample,
        trigger_bytes=bytes(data[_TRIGGER_TIME_OFFSET : _TRIGGER_TIME_OFFSET + 9]),
    )


def _payload_offset(data: bytes, header: Ben5kSlowHeader) -> int:
    """Byte offset where the sample payload starts (payload is at EOF)."""
    payload_bytes = header.sample_count * header.words_per_sample * 2
    offset = len(data) - payload_bytes
    if offset <= _HEADER_END:
        raise BenStructureError(
            f"BEN5K Slow payload ({payload_bytes} bytes) leaves no room for a config area"
        )
    return offset


def read_config_header(data: bytes) -> SlowConfigHeader:
    """Extract the 34-byte BEN5K Slow config header at offset 0xDC."""
    if len(data) < _CONFIG_HEADER_OFFSET + _CONFIG_HEADER_SIZE:
        raise BenTruncatedError(
            f"file too short for BEN5K Slow config header at {_CONFIG_HEADER_OFFSET:#x}"
        )
    base = _CONFIG_HEADER_OFFSET
    version = struct.unpack_from("<H", data, base + _CH_VERSION_OFFSET)[0]
    marker = struct.unpack_from("<H", data, base + _CH_MARKER_OFFSET)[0]
    recorder_unit = struct.unpack_from("<H", data, base + _CH_RECORDER_UNIT_OFFSET)[0]
    group_count = struct.unpack_from("<H", data, base + _CH_GROUP_COUNT_OFFSET)[0]
    station_raw = data[base + _CH_STATION_OFFSET : base + _CH_STATION_OFFSET + 16]
    station = station_raw.split(b"\x00")[0].decode("latin-1", errors="replace")
    return SlowConfigHeader(
        version=version,
        section_marker=marker,
        recorder_unit=recorder_unit,
        primary_group_count=group_count,
        station_name=station,
    )


def read_hvdc_formula(data: bytes) -> SlowHvdcFormula:
    """Extract the 65-byte HVDC Power formula descriptor at offset 0xFE."""
    if len(data) < _HVDC_FORMULA_OFFSET + _HVDC_FORMULA_SIZE:
        raise BenTruncatedError(
            f"file too short for BEN5K Slow HVDC formula at {_HVDC_FORMULA_OFFSET:#x}"
        )
    base = _HVDC_FORMULA_OFFSET
    raw = bytes(data[base : base + _HVDC_FORMULA_SIZE])
    name_raw = data[base + _HVDC_NAME_OFFSET : base + _HVDC_NAME_OFFSET + _HVDC_NAME_SIZE]
    name = name_raw.split(b"\x00")[0].decode("latin-1", errors="replace")
    return SlowHvdcFormula(name=name, raw_bytes=raw)


def read_channel_groups(
    data: bytes,
    header: Ben5kSlowHeader,
) -> list[SlowGroup]:
    """Read all nine channel groups from the BEN5K Slow config area.

    Groups start at offset 0x013F with a fixed stride of 252 bytes each.
    Each group contains one 24-byte SENS descriptor, eight 28-byte channel
    descriptor slots, and a 4-byte separator (ff ff ff ff).

    Channel classification:
      - INACTIVE  : name starts with '-' or selector == 0 and name is empty
      - TENTATIVE : 0 < word_index_tentative < words_per_sample, not yet
                    conflicting (word_index_tentative = selector >> 8)
      - UNRESOLVED_ZERO : named channel where selector >> 8 == 0 (low-byte
                    selector; word 0 is status/flags in GRNE; mapping ambiguous)
      - UNRESOLVED_OOR  : word_index_tentative >= words_per_sample (out of range)
      - UNRESOLVED_CONFLICT : word_index already claimed by an earlier channel

    Returns:
        Nine SlowGroup objects, one per group, in order.
    """
    groups_end = _GROUPS_START_OFFSET + _GROUP_COUNT * _GROUP_STRIDE
    if len(data) < groups_end:
        raise BenTruncatedError(
            f"file too short for {_GROUP_COUNT} BEN5K Slow channel groups "
            f"(need {groups_end:#x} bytes, have {len(data):#x})"
        )

    claimed_words: set[int] = set()  # word indices already assigned to TENTATIVE channels
    groups: list[SlowGroup] = []

    for g in range(_GROUP_COUNT):
        goff = _GROUPS_START_OFFSET + g * _GROUP_STRIDE
        gdata = data[goff : goff + _GROUP_STRIDE]

        # SENS descriptor
        if gdata[_SENS_DISCRIMINATOR] != 0x00:
            raise BenStructureError(
                f"BEN5K Slow group {g} at {goff:#x}: SENS discriminator byte "
                f"is {gdata[_SENS_DISCRIMINATOR]:#x}, expected 0x00",
                offset=goff + _SENS_DISCRIMINATOR,
            )
        sens_name_raw = gdata[_SENS_NAME_OFFSET : _SENS_NAME_OFFSET + _SENS_NAME_SIZE]
        group_name = sens_name_raw.split(b"\x00")[0].decode("latin-1", errors="replace")

        channels: list[SlowChannelDescriptor] = []
        for s in range(_CHANNEL_SLOTS_PER_GROUP):
            slot_start = _SENS_SIZE + s * _CHANNEL_SLOT_SIZE
            cdesc = gdata[slot_start : slot_start + _CHANNEL_SLOT_SIZE]

            selector = struct.unpack_from("<H", cdesc, _CH_SELECTOR_OFFSET)[0]
            name_raw = cdesc[_CH_NAME_OFFSET : _CH_NAME_OFFSET + _CH_NAME_SIZE]
            name_bytes = name_raw.split(b"\x00")[0]
            name = name_bytes.decode("latin-1", errors="replace") if name_bytes else ""
            scale_ref = bytes(cdesc[_CH_SCALE_REF_OFFSET : _CH_SCALE_REF_OFFSET + 4])

            desc_offset = goff + slot_start

            # INACTIVE: name starts with '-' (covers '----' placeholder)
            if not name or name_bytes[0] == _INACTIVE_NAME_PREFIX:
                status = SlowChannelStatus.INACTIVE
                wi = 0
            else:
                wi = selector >> 8   # equivalent to selector // 256
                if wi == 0:
                    status = SlowChannelStatus.UNRESOLVED_ZERO
                elif wi >= header.words_per_sample:
                    status = SlowChannelStatus.UNRESOLVED_OOR
                elif wi in claimed_words:
                    status = SlowChannelStatus.UNRESOLVED_CONFLICT
                else:
                    status = SlowChannelStatus.TENTATIVE
                    claimed_words.add(wi)

            channels.append(SlowChannelDescriptor(
                name=name,
                selector_raw=selector,
                word_index_tentative=wi,
                group_index=g,
                group_name=group_name,
                slot_index=s,
                descriptor_offset=desc_offset,
                status=status,
                scale_ref_raw=scale_ref,
            ))

        groups.append(SlowGroup(
            group_index=g,
            group_name=group_name,
            channels=tuple(channels),
        ))

    return groups


class ExtendedCatalogEntryType(Enum):
    """Type of a 30-byte extended catalog record."""
    #: `0x01 0x01` — logical channel with unique sequential ID and name.
    LOGICAL = auto()
    #: `0x04 0x33` — derived/threshold channel referencing a parent logical ID.
    DERIVED = auto()
    #: Any other byte pair; the record's interpretation is unknown.
    UNKNOWN = auto()


@dataclass(frozen=True)
class ExtendedCatalogEntry:
    """One 30-byte record from the extended catalog section.

    The catalog starts immediately after the nine channel groups (0x0A1B) and
    ends at the SubBen 2 display section.  Each record carries:

      bytes 0-1  : type marker  (0x01,0x01 = LOGICAL; 0x04,0x33 = DERIVED)
      bytes 2-3  : channel_id   (u16le; sequential for LOGICAL; parent ID for DERIVED)
      bytes 4-5  : flags        (0x00FF = primary substation; 0x01FF = secondary)
      bytes 6-25 : name         (20-byte NUL-padded latin-1 string)
      bytes 26-29: tail         (0xFFFFFFFF for valid records)

    The catalog defines logical channel names and IDs but does NOT contain
    physical sample word indices.  The relationship between catalog IDs and
    the group-descriptor selector values is not yet decoded.
    """
    entry_type: ExtendedCatalogEntryType
    channel_id: int       # u16le from bytes 2-3
    flags: int            # u16le from bytes 4-5
    name: str             # decoded from bytes 6-25, NUL-stripped
    record_offset: int    # byte offset in the file


def read_extended_catalog(data: bytes) -> list[ExtendedCatalogEntry]:
    """Read 30-byte extended catalog records between the group area and SubBen 2.

    The catalog section starts at 0x0A1B (immediately after the nine channel
    groups) and ends where the SubBen 2 display section begins, identified by
    the ASCII signature b"SubBen 2".

    Only records with tail == 0xFFFFFFFF are included.  Records in the overlap
    zone near SubBen 2 (which may be corrupted by the SubBen 2 overlay) are
    excluded if their tail does not match.

    Returns:
        List of ExtendedCatalogEntry, in file order.  Returns an empty list if
        the SubBen 2 marker is not found or the catalog section is empty.
    """
    subben2_off = data.find(_SUBBEN2_MARKER, _EXT_CATALOG_OFFSET)
    if subben2_off < 0:
        return []

    entries: list[ExtendedCatalogEntry] = []
    max_records = (subben2_off - _EXT_CATALOG_OFFSET) // _EXT_RECORD_STRIDE

    for i in range(max_records):
        off = _EXT_CATALOG_OFFSET + i * _EXT_RECORD_STRIDE
        if off + _EXT_RECORD_STRIDE > len(data):
            break
        rec = data[off : off + _EXT_RECORD_STRIDE]

        # Validate tail; skip records that are not cleanly 0xFFFFFFFF
        if rec[_EXT_TAIL_OFFSET : _EXT_TAIL_OFFSET + 4] != _EXT_RECORD_TAIL:
            continue

        b0, b1 = rec[0], rec[1]
        if (b0, b1) == _EXT_TYPE_LOGICAL:
            entry_type = ExtendedCatalogEntryType.LOGICAL
        elif (b0, b1) == _EXT_TYPE_DERIVED:
            entry_type = ExtendedCatalogEntryType.DERIVED
        else:
            entry_type = ExtendedCatalogEntryType.UNKNOWN

        channel_id = struct.unpack_from("<H", rec, _EXT_ID_OFFSET)[0]
        flags = struct.unpack_from("<H", rec, _EXT_FLAGS_OFFSET)[0]
        name_raw = rec[_EXT_NAME_OFFSET : _EXT_NAME_OFFSET + _EXT_NAME_SIZE]
        name = name_raw.split(b"\x00")[0].decode("latin-1", errors="replace")

        entries.append(ExtendedCatalogEntry(
            entry_type=entry_type,
            channel_id=channel_id,
            flags=flags,
            name=name,
            record_offset=off,
        ))

    return entries


def active_channels(groups: list[SlowGroup]) -> list[SlowChannelDescriptor]:
    """Return all TENTATIVE channels across all groups, in group order."""
    return [
        ch
        for g in groups
        for ch in g.channels
        if ch.status == SlowChannelStatus.TENTATIVE
    ]


def unresolved_channels(groups: list[SlowGroup]) -> list[SlowChannelDescriptor]:
    """Return all UNRESOLVED channels (OOR, ZERO, CONFLICT) across all groups."""
    _unresolved = {
        SlowChannelStatus.UNRESOLVED_ZERO,
        SlowChannelStatus.UNRESOLVED_OOR,
        SlowChannelStatus.UNRESOLVED_CONFLICT,
    }
    return [
        ch
        for g in groups
        for ch in g.channels
        if ch.status in _unresolved
    ]
