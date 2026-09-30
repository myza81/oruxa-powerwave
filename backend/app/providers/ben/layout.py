"""Structural constants of the validated BEN32 "SubBen" file layout.

Every byte offset, section type code and record size the BEN parser
relies on lives here, named and explained, so no other module carries an
unexplained magic number. Nothing here describes a *particular* event
file: sample rate, sample count, pre-trigger count, channel counts,
sample stride, sample-data offset and every channel's position inside a
sample are all read from each file's own configuration (see
``app.providers.ben.parser``).

Provenance: reverse-engineered statically (no BEN32 executable was ever
run) from BEN files written by the legacy BEN32 3.8.9.6 software, and
validated against BEN32-generated COMTRADE exports of the same events.
See docs/project-memory/BEN_FORMAT.md for the evidence behind each
constant, and for what is still unknown.

Byte order: every header / configuration field is LITTLE-endian. Every
sample word in the sample-data payload is BIG-endian (a separate,
equally validated fact -- see ``SAMPLE_WORD_DTYPE``).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Fixed file header (offsets 0x00 .. HEADER_SIZE)
# ─────────────────────────────────────────────────────────────────────────────

#: Bytes 0x00-0x03, identical in every BEN file examined (both the
#: supported SubBen layout and the older, unsupported one). A file that
#: does not start with this is not recognized as BEN at all.
BEN_FAMILY_SIGNATURE = b"\x01\x00\x04\x00"

#: Bytes 0x04-0x0B of the supported SubBen layout. Byte 0x04 is the
#: layout discriminator: 0x2A in every SubBen file examined, 0x28 in an
#: older BEN layout whose configuration area is structured completely
#: differently (and which stores local rather than UTC time).
SUBBEN_LAYOUT_SIGNATURE = b"\x2a\xff\x03\x00\x6e\x00\xca\x00"
SUBBEN_LAYOUT_SIGNATURE_OFFSET = 0x04

#: Bytes 0x0E-0x0F of the supported SubBen layout (0x05 0x00 in the older
#: layout).
SUBBEN_GENERATION_MARKER = b"\x06\xff"
SUBBEN_GENERATION_MARKER_OFFSET = 0x0E

#: u16 -- recorder unit number (equals the COMTRADE ``rec_dev_id`` BEN32
#: writes on CFG line 1, e.g. 1196, 1214).
RECORDER_UNIT_ID_OFFSET = 0x0C

#: NUL-terminated station text; bytes after the terminator are unused
#: buffer contents and are ignored.
STATION_NAME_OFFSET = 0x10
STATION_NAME_SIZE = 0x28

#: u32 -- recorder-assigned record number. Repeated as the first field of
#: the RECORD_SUMMARY sub-block; its meaning beyond identity is unknown.
RECORD_NUMBER_OFFSET = 0x38

#: u8 -- 0 for a Fast SubBen record, 1 for a Slow SubBen record. Followed
#: by 0xFF. Cross-checked against RECORD_CLASS_SECTION.
RECORD_CLASS_FLAG_OFFSET = 0x3C

#: NUL-terminated record label (every file examined says "New Record").
RECORD_LABEL_OFFSET = 0x42
RECORD_LABEL_SIZE = 0x12

#: u32 -- sampling-rate field; samples per second = field / 1000
#: (5_000_000 -> 5000 samples/s, 20_000 -> 20 samples/s).
RATE_FIELD_OFFSET = 0x54
RATE_FIELD_PER_SAMPLE_PER_SECOND = 1000

#: u32 -- samples recorded before the trigger instant.
PRE_TRIGGER_SAMPLES_OFFSET = 0x58

#: u32 -- total samples in the sample-data payload.
SAMPLE_COUNT_OFFSET = 0x5C

#: u16 -- 16-bit words per sample; sample stride = 2 * this value.
WORDS_PER_SAMPLE_OFFSET = 0x60

#: Trigger timestamp, one byte per field: year-1900, month, day, hour,
#: minute, second, then the fractional second as three base-100 digits
#: (hundredths, 1e-4 s, 1e-6 s). BEN stores this in UTC -- the BEN32
#: COMTRADE export of the same record shows the same instant rendered in
#: the exporting PC's local time (UTC+08:00 in every validated pair).
TRIGGER_TIME_OFFSET = 0x64
TRIGGER_TIME_YEAR_BASE = 1900
TRIGGER_FRACTION_OFFSET = 0x6A
TRIGGER_FRACTION_DIGITS = 3
TRIGGER_FRACTION_DIGIT_BASE = 100

#: u32 -- index of the last sample (always sample_count - 1). Used only
#: as an internal consistency check.
LAST_SAMPLE_INDEX_OFFSET = 0x7A

#: Bytes TRIGGER_INFO_OFFSET-HEADER_SIZE hold the trigger-cause
#: description (e.g. the name of the channel that triggered); they are
#: preserved raw, not interpreted.
TRIGGER_INFO_OFFSET = 0x80

#: Size of the fixed header. The typed-section chain starts here.
HEADER_SIZE = 0xDC

# ─────────────────────────────────────────────────────────────────────────────
# Typed configuration sections
# ─────────────────────────────────────────────────────────────────────────────
#
# From HEADER_SIZE onward the file is a chain of sections framed as
#
#     u16 section type | u16 0xFFFF | u32 payload length | payload
#
# A "record section" payload is ``u16 count | u16 0xFFFF`` followed by
# ``count`` fixed-size records (so length == 4 + count * record size).
# A "string table" payload is a block of NUL-terminated names addressed
# by byte offset from the start of the payload.

SECTION_MARKER = 0xFFFF
SECTION_FRAME_SIZE = 8  # type + marker + length
RECORD_SECTION_PREFIX_SIZE = 4  # count + marker

SECTION_RECORDER_INFO = 0x0001
SECTION_RECORD_CLASS = 0x06A4
SECTION_ANALOG_CHANNELS = 0x0514
SECTION_PHYSICAL_DIGITALS = 0x0515
SECTION_CALCULATED_CHANNELS = 0x0516
SECTION_CHANNEL_NAMES = 0x0518
SECTION_TRIGGER_DEFINITIONS = 0x0578
SECTION_EVENT_CHANNELS = 0x0579
SECTION_EVENT_NAMES = 0x057A
SECTION_STATION = 0x06A5
SECTION_BAYS = 0x06A6
SECTION_BAY_CHANNELS = 0x06A7
SECTION_BAY_CARDS = 0x06A9
SECTION_BAY_NAMES = 0x06AA
SECTION_CARD_NAMES = 0x06AB

#: Record sections and their fixed record sizes, validated exactly
#: against each section's declared length.
RECORD_SIZES: dict[int, int] = {
    SECTION_RECORD_CLASS: 84,
    SECTION_ANALOG_CHANNELS: 52,
    SECTION_PHYSICAL_DIGITALS: 18,
    SECTION_CALCULATED_CHANNELS: 164,
    SECTION_TRIGGER_DEFINITIONS: 210,
    SECTION_EVENT_CHANNELS: 86,
    SECTION_STATION: 44,
    SECTION_BAYS: 28,
    SECTION_BAY_CHANNELS: 36,
    SECTION_BAY_CARDS: 52,
}

STRING_TABLE_SECTIONS = frozenset(
    {SECTION_CHANNEL_NAMES, SECTION_EVENT_NAMES, SECTION_BAY_NAMES, SECTION_CARD_NAMES}
)

#: Every known section type (recognized sections the parser does not
#: interpret are still length-validated and skipped).
KNOWN_SECTIONS = frozenset(RECORD_SIZES) | STRING_TABLE_SECTIONS | {SECTION_RECORDER_INFO}

#: Sections every supported record must carry. A Fast record additionally
#: needs SECTION_ANALOG_CHANNELS, a Slow record SECTION_CALCULATED_CHANNELS
#: (see RECORD_CLASSES).
REQUIRED_SECTIONS = frozenset(
    {
        SECTION_RECORD_CLASS,
        SECTION_CHANNEL_NAMES,
        SECTION_EVENT_CHANNELS,
        SECTION_EVENT_NAMES,
    }
)

# ── SECTION_RECORD_CLASS record (84 bytes) ──────────────────────────────────
RECORD_CLASS_CODE_FIELD = 0  # u32
RECORD_CLASS_NAME_FIELD = 12  # NUL-terminated
RECORD_CLASS_NAME_SIZE = 24
RECORD_CLASS_RATE_FIELD = 36  # u32, repeats header RATE_FIELD
RECORD_CLASS_PRE_TRIGGER_FIELD = 52  # u32, repeats header PRE_TRIGGER

#: code -> (class name as stored in the file, header class flag, channel
#: descriptor section). These are the only two record classes validated.
RECORD_CLASSES: dict[int, tuple[str, int, int]] = {
    1006: ("Fast SubBen", 0, SECTION_ANALOG_CHANNELS),
    1007: ("Slow SubBen", 1, SECTION_CALCULATED_CHANNELS),
}

# ── Channel identity fields shared by the channel descriptor records ────────
#
# Every channel carries a u16 id unique within the file. Descriptor
# records reference one another -- and the sample layout map -- only
# through these ids, never through positions.

# SECTION_ANALOG_CHANNELS record (52 bytes): a sampled analog input.
ANALOG_ID_FIELD = 0  # u16
ANALOG_TRIGGER_ID_FIELD = 2  # u16, first derived trigger of this input (0 = none)
ANALOG_EVENT_ID_FIELD = 4  # u16
ANALOG_NAME_FIELD = 8  # u16 offset into SECTION_CHANNEL_NAMES
ANALOG_QUANTITY_CODE_FIELD = 12  # u8 (0 voltage input, 4 current input)
ANALOG_PHASE_CODE_FIELD = 13  # u8, see PHASE_CODES
ANALOG_UNIT_CODE_FIELD = 14  # u8, see UNIT_CODES
ANALOG_UNIT_MULTIPLIER_FIELD = 15  # u8 power-of-ten exponent, see UNIT_MULTIPLIERS
ANALOG_SCALE_FIELD = 16  # f32: engineering value = scale * raw + offset
ANALOG_OFFSET_FIELD = 20  # f32
ANALOG_PRIMARY_RATING_FIELD = 28  # f32, in the channel's (prefixed) unit
ANALOG_SECONDARY_RATING_FIELD = 36  # f32, in the channel's BASE unit (V, A)
ANALOG_HARDWARE_ADDRESS_FIELD = 44  # u16

# SECTION_CALCULATED_CHANNELS record (164 bytes): a quantity the recorder
# computes (frequency, power, ...). Same coding as the analog record for
# the fields below; the remainder (calculation inputs) is kept raw.
CALCULATED_ID_FIELD = 0
CALCULATED_TRIGGER_ID_FIELD = 2
CALCULATED_EVENT_ID_FIELD = 6
CALCULATED_NAME_FIELD = 8
CALCULATED_QUANTITY_CODE_FIELD = 12
CALCULATED_PHASE_CODE_FIELD = 13
CALCULATED_UNIT_CODE_FIELD = 14
CALCULATED_UNIT_MULTIPLIER_FIELD = 15
CALCULATED_SCALE_FIELD = 16
CALCULATED_OFFSET_FIELD = 20

# SECTION_PHYSICAL_DIGITALS record (18 bytes): one physical binary input.
PHYSICAL_DIGITAL_ID_FIELD = 0
PHYSICAL_DIGITAL_EVENT_ID_FIELD = 4
PHYSICAL_DIGITAL_NAME_FIELD = 8
PHYSICAL_DIGITAL_HARDWARE_ADDRESS_FIELD = 12

# SECTION_TRIGGER_DEFINITIONS record (210 bytes): one derived binary
# indication computed by the recorder (e.g. "OVER BUGL1 VR"). Only its
# id is interpreted; thresholds etc. stay raw.
TRIGGER_ID_FIELD = 0

# SECTION_EVENT_CHANNELS record (86 bytes): BEN32's exported binary
# channel list (derived indications and physical inputs, in BEN order).
EVENT_ID_FIELD = 0
EVENT_NAME_FIELD = 2  # u16 offset into SECTION_EVENT_NAMES
EVENT_TRIGGER_ID_FIELD = 74  # u16: derived trigger carrying the bit (0 = none)
EVENT_SOURCE_ID_FIELD = 76  # u16: source channel (analog/calculated or physical digital)

# Bay (feeder) configuration: SECTION_BAYS names each bay (offset into
# SECTION_BAY_NAMES, text "<station> : <bay>"); SECTION_BAY_CHANNELS links
# an analog/calculated channel id to its bay; SECTION_BAY_CARDS lists up to
# CARD_MEMBER_COUNT binary ids (trigger or physical digital) per bay card.
BAY_ID_FIELD = 0  # u32
BAY_NAME_FIELD = 8  # u16
BAY_NAME_SEPARATOR = " : "
BAY_CHANNEL_BAY_ID_FIELD = 4  # u32
BAY_CHANNEL_CHANNEL_ID_FIELD = 16  # u16
CARD_BAY_ID_FIELD = 4  # u32
CARD_MEMBERS_FIELD = 20  # CARD_MEMBER_COUNT x u32
CARD_MEMBER_COUNT = 8

#: Phase codes of analog/calculated descriptors, rendered the way BEN32's
#: COMTRADE export renders them (the ``ph`` CFG field). 0 = no phase.
PHASE_CODES: dict[int, str | None] = {0: None, 1: "A", 2: "B", 3: "C", 4: "N"}

#: Unit codes (base unit) of analog/calculated descriptors. Only codes
#: observed in the validated files are listed; the numbering coincides
#: with IEC 61850-7-3 SIUnit, but codes not seen here are deliberately not
#: guessed. value: (base unit symbol, measurement kind).
UNIT_CODES: dict[int, tuple[str, str]] = {
    5: ("A", "current"),
    29: ("V", "voltage"),
    33: ("Hz", "frequency"),
    38: ("W", "active_power"),
}

#: Power-of-ten unit multipliers observed (0 -> none, 3 -> k, 6 -> M).
UNIT_MULTIPLIERS: dict[int, str] = {0: "", 3: "k", 6: "M"}

# ─────────────────────────────────────────────────────────────────────────────
# Sample-layout container and sample data
# ─────────────────────────────────────────────────────────────────────────────
#
# After the last configuration section comes one container framed WITHOUT
# the 0xFFFF marker:  u16 CONTAINER_TYPE | u32 length | sub-blocks,
# whose sub-blocks use the ordinary section framing. It is immediately
# followed by the u16 SAMPLE_DATA_TAG and then the sample payload, which
# runs to end of file.

CONTAINER_TYPE = 0x03E8
CONTAINER_FRAME_SIZE = 6

SUB_BLOCK_ACQUISITION = 0x4E20  # 96 bytes, preserved raw
SUB_BLOCK_RECORD_SUMMARY = 0x4E21
SUB_BLOCK_SAMPLE_LAYOUT = 0x4E25

# RECORD_SUMMARY sub-block: repeats header facts -- cross-checked.
SUMMARY_RECORD_NUMBER_FIELD = 0  # u32
SUMMARY_RECORD_CLASS_CODE_FIELD = 4  # u16
SUMMARY_WORDS_PER_SAMPLE_FIELD = 24  # u16
SUMMARY_RATE_FIELD = 28  # u32
SUMMARY_PRE_TRIGGER_FIELD = 32  # u32
SUMMARY_SAMPLE_COUNT_FIELD = 36  # u32
SUMMARY_MIN_SIZE = 40

#: SAMPLE_LAYOUT sub-block: a record section of LAYOUT_ENTRY_SIZE entries
#:   u16 channel id | u16 word index | u8 bit | u8 slot kind (raw)
#: declaring where every channel lives inside a sample. Value channels
#: (analog/calculated) occupy a whole word; binary channels one bit of a
#: word, bit 0 = least significant bit of the big-endian word.
LAYOUT_ENTRY_SIZE = 6

SAMPLE_DATA_TAG = 0x07D0
SAMPLE_DATA_TAG_SIZE = 2

#: Sample words are BIG-endian 16-bit (signed for value channels).
SAMPLE_WORD_DTYPE = ">u2"
SAMPLE_VALUE_DTYPE = ">i2"
SAMPLE_WORD_BYTES = 2
BITS_PER_WORD = 16

#: Stored binary bits are ACTIVE-LOW: a stored 0 means the indication is
#: active (COMTRADE value 1), a stored 1 means inactive.
DIGITAL_STORED_BIT_ACTIVE_LOW = True

#: Raw value a calculated (Slow SubBen) channel stores when the quantity
#: is unavailable. BEN32 exports it as 99999 in COMTRADE. Not applied to
#: sampled analog inputs, for which no such rule has been observed.
CALCULATED_UNAVAILABLE_RAW = -32768
