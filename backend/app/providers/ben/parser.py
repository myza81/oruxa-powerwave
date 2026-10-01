"""Native BEN (BEN32 SubBen) record parser.

    BEN bytes -> parse_ben() -> BenRecord

No COMTRADE is involved at any point. Every structural value -- sample
rate, sample count, pre-trigger count, channel counts, words per sample,
sample-data offset and each channel's position within a sample -- is
read from the file's own configuration and cross-checked against the
other places the file repeats it. A file whose declarations disagree, run
past the end of the file, or leave bytes unaccounted for is rejected; a
layout that has not been validated is rejected rather than guessed.

Parsing steps:

1. Fixed header: family signature, layout signature, record facts.
2. Typed configuration sections from ``layout.HEADER_SIZE`` onward.
3. Record class (Fast / Slow) from its own section, cross-checked with
   the header flag and the channel descriptor section present.
4. Channel descriptors, names, bays and BEN's exported binary list.
5. The sample-layout container: the summary sub-block (cross-checked)
   and the layout map placing every channel inside a sample.
6. The payload boundary: data offset + count x stride == file size.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.providers.ben import layout
from app.providers.ben.errors import (
    BenFormatError,
    BenNotRecognizedError,
    BenStructureError,
    BenTruncatedError,
    BenUnsupportedVariantError,
)
from app.providers.ben.model import (
    BenChannelKind,
    BenDiagnostic,
    BenDigitalChannel,
    BenDigitalSource,
    BenHeader,
    BenRecord,
    BenRecordClass,
    BenSampleSlot,
    BenTriggerTime,
    BenValueChannel,
)
from app.providers.ben.reader import ByteView, Section, StringTable, read_section, record_entries

_RECORD_CLASS_ENUM = {
    "Fast SubBen": BenRecordClass.FAST,
    "Slow SubBen": BenRecordClass.SLOW,
}


def parse_ben_file(path: Path) -> BenRecord:
    """Read and parse the BEN file at *path*."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BenFormatError(f"Cannot read BEN file '{path}': {exc}") from exc
    return parse_ben(data)


def parse_ben(data: bytes) -> BenRecord:
    """Parse BEN file bytes into a ``BenRecord``.

    Raises a ``BenFormatError`` subclass for anything not decodable with
    the validated SubBen layout.
    """
    if not isinstance(data, bytes):
        data = bytes(data)
    file = ByteView.whole(data)
    diagnostics: list[BenDiagnostic] = []

    _check_signatures(file)
    header_fields = _read_header_fields(file, diagnostics)

    sections, container_offset = _read_sections(file, diagnostics)
    record_class, class_code = _read_record_class(sections, header_fields)

    container = _read_container(file, container_offset)
    data_offset = container.end + layout.SAMPLE_DATA_TAG_SIZE
    _check_summary(container.summary, header_fields, class_code)

    header = BenHeader(
        recorder_unit_id=header_fields.recorder_unit_id,
        station_name=header_fields.station_name,
        record_label=header_fields.record_label,
        record_number=header_fields.record_number,
        record_class=record_class,
        record_class_code=class_code,
        rate_field=header_fields.rate_field,
        sample_count=header_fields.sample_count,
        pre_trigger_samples=header_fields.pre_trigger_samples,
        words_per_sample=header_fields.words_per_sample,
        sample_data_offset=data_offset,
        trigger_time=header_fields.trigger_time,
        trigger_info_raw=file.raw(layout.TRIGGER_INFO_OFFSET, layout.HEADER_SIZE - layout.TRIGGER_INFO_OFFSET),
    )
    _check_payload_boundary(file, header)

    slots = _read_layout_map(container.layout_map, header.words_per_sample)
    config = _ChannelConfig.read(sections, record_class)
    value_channels = _build_value_channels(config, slots)
    digital_channels = _build_digital_channels(config, slots, diagnostics)
    _check_slot_overlaps(value_channels, digital_channels)
    diagnostics.extend(_unreferenced_slot_diagnostics(slots, value_channels, digital_channels))

    sample_words = np.frombuffer(
        data,
        dtype=layout.SAMPLE_WORD_DTYPE,
        count=header.sample_count * header.words_per_sample,
        offset=data_offset,
    ).reshape(header.sample_count, header.words_per_sample)

    record = BenRecord(
        header=header,
        value_channels=tuple(value_channels),
        digital_channels=tuple(digital_channels),
        diagnostics=(),
        sample_words=sample_words,
    )
    diagnostics.extend(_value_diagnostics(record))
    diagnostics.extend(_duplicate_name_diagnostics(record))
    return replace(record, diagnostics=tuple(diagnostics))


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _HeaderFields:
    recorder_unit_id: int
    station_name: str
    record_label: str
    record_number: int
    class_flag: int
    rate_field: int
    pre_trigger_samples: int
    sample_count: int
    words_per_sample: int
    trigger_time: BenTriggerTime


def _check_signatures(file: ByteView) -> None:
    if file.size < layout.HEADER_SIZE:
        if file.size >= len(layout.BEN_FAMILY_SIGNATURE) and file.raw(
            0, len(layout.BEN_FAMILY_SIGNATURE)
        ) == layout.BEN_FAMILY_SIGNATURE:
            raise BenTruncatedError(
                f"file is {file.size} bytes, shorter than the {layout.HEADER_SIZE}-byte BEN header"
            )
        raise BenNotRecognizedError("file is too short to be a BEN record")
    if file.raw(0, len(layout.BEN_FAMILY_SIGNATURE)) != layout.BEN_FAMILY_SIGNATURE:
        raise BenNotRecognizedError("file does not start with the BEN family signature", offset=0)
    signature = file.raw(layout.SUBBEN_LAYOUT_SIGNATURE_OFFSET, len(layout.SUBBEN_LAYOUT_SIGNATURE))
    generation = file.raw(layout.SUBBEN_GENERATION_MARKER_OFFSET, len(layout.SUBBEN_GENERATION_MARKER))
    if signature != layout.SUBBEN_LAYOUT_SIGNATURE or generation != layout.SUBBEN_GENERATION_MARKER:
        raise BenUnsupportedVariantError(
            f"BEN layout signature {signature.hex(' ')} / {generation.hex(' ')} is not the validated "
            f"BEN32 SubBen layout ({layout.SUBBEN_LAYOUT_SIGNATURE.hex(' ')} / "
            f"{layout.SUBBEN_GENERATION_MARKER.hex(' ')})",
            offset=layout.SUBBEN_LAYOUT_SIGNATURE_OFFSET,
        )


def _read_header_fields(file: ByteView, diagnostics: list[BenDiagnostic]) -> _HeaderFields:
    rate_field = file.u32(layout.RATE_FIELD_OFFSET)
    pre_trigger = file.u32(layout.PRE_TRIGGER_SAMPLES_OFFSET)
    sample_count = file.u32(layout.SAMPLE_COUNT_OFFSET)
    words = file.u16(layout.WORDS_PER_SAMPLE_OFFSET)
    last_index = file.u32(layout.LAST_SAMPLE_INDEX_OFFSET)

    if rate_field == 0:
        raise BenStructureError("sampling-rate field is zero", offset=layout.RATE_FIELD_OFFSET)
    if sample_count == 0:
        raise BenStructureError("record declares zero samples", offset=layout.SAMPLE_COUNT_OFFSET)
    if words == 0:
        raise BenStructureError("record declares zero words per sample", offset=layout.WORDS_PER_SAMPLE_OFFSET)
    if pre_trigger > sample_count:
        raise BenStructureError(
            f"pre-trigger count {pre_trigger} exceeds sample count {sample_count}",
            offset=layout.PRE_TRIGGER_SAMPLES_OFFSET,
        )
    if last_index != sample_count - 1:
        raise BenStructureError(
            f"last-sample index {last_index} disagrees with sample count {sample_count}",
            offset=layout.LAST_SAMPLE_INDEX_OFFSET,
        )

    return _HeaderFields(
        recorder_unit_id=file.u16(layout.RECORDER_UNIT_ID_OFFSET),
        station_name=file.text(layout.STATION_NAME_OFFSET, layout.STATION_NAME_SIZE),
        record_label=file.text(layout.RECORD_LABEL_OFFSET, layout.RECORD_LABEL_SIZE),
        record_number=file.u32(layout.RECORD_NUMBER_OFFSET),
        class_flag=file.u8(layout.RECORD_CLASS_FLAG_OFFSET),
        rate_field=rate_field,
        pre_trigger_samples=pre_trigger,
        sample_count=sample_count,
        words_per_sample=words,
        trigger_time=_read_trigger_time(file, diagnostics),
    )


def _read_trigger_time(file: ByteView, diagnostics: list[BenDiagnostic]) -> BenTriggerTime:
    base = layout.TRIGGER_TIME_OFFSET
    year, month, day, hour, minute, second = (file.u8(base + i) for i in range(6))
    try:
        whole = datetime(
            layout.TRIGGER_TIME_YEAR_BASE + year, month, day, hour, minute, second, tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise BenStructureError(f"trigger timestamp is not a valid date/time: {exc}", offset=base) from exc

    digits = tuple(
        file.u8(layout.TRIGGER_FRACTION_OFFSET + i) for i in range(layout.TRIGGER_FRACTION_DIGITS)
    )
    microsecond: int | None = 0
    for digit in digits:
        if digit >= layout.TRIGGER_FRACTION_DIGIT_BASE:
            microsecond = None
            break
        microsecond = microsecond * layout.TRIGGER_FRACTION_DIGIT_BASE + digit
    if microsecond is None:
        diagnostics.append(
            BenDiagnostic(
                "trigger_fraction_undecodable",
                "warning",
                f"trigger sub-second digits {list(digits)} are not base-100 digits; "
                "only the whole-second trigger time is reported",
            )
        )
    return BenTriggerTime(whole, digits, microsecond)  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# Sections
# ─────────────────────────────────────────────────────────────────────────────


def _read_sections(file: ByteView, diagnostics: list[BenDiagnostic]) -> tuple[dict[int, Section], int]:
    """Walk the section chain up to the sample-layout container."""
    sections: dict[int, Section] = {}
    pos = layout.HEADER_SIZE
    while True:
        type_code = file.u16(pos, "section type")
        if type_code == layout.CONTAINER_TYPE:
            break
        section = read_section(file, pos)
        if type_code in sections:
            raise BenStructureError(f"section {type_code:#06x} occurs twice", offset=pos)
        if type_code not in layout.KNOWN_SECTIONS:
            diagnostics.append(
                BenDiagnostic(
                    "unrecognized_section",
                    "warning",
                    f"section {type_code:#06x} ({section.payload.size} bytes) at {pos:#x} is not "
                    "recognized; it was length-checked and skipped",
                )
            )
        sections[type_code] = section
        pos = section.payload.end

    missing = sorted(layout.REQUIRED_SECTIONS - sections.keys())
    if missing:
        raise BenUnsupportedVariantError(
            "required section(s) missing: " + ", ".join(f"{t:#06x}" for t in missing)
        )
    return sections, pos


def _read_record_class(sections: dict[int, Section], fields: _HeaderFields) -> tuple[BenRecordClass, int]:
    (record,) = _records(sections, layout.SECTION_RECORD_CLASS, exactly_one=True)
    code = record.u32(layout.RECORD_CLASS_CODE_FIELD)
    name = record.text(layout.RECORD_CLASS_NAME_FIELD, layout.RECORD_CLASS_NAME_SIZE)
    known = layout.RECORD_CLASSES.get(code)
    if known is None or known[0] != name:
        raise BenUnsupportedVariantError(
            f"record class {code} ({name!r}) is not a validated BEN record class "
            f"({', '.join(f'{c} {n!r}' for c, (n, _, _) in layout.RECORD_CLASSES.items())})",
            offset=record.start,
        )
    _, header_flag, descriptor_section = known
    if fields.class_flag != header_flag:
        raise BenStructureError(
            f"header class flag {fields.class_flag} disagrees with record class {name!r}",
            offset=layout.RECORD_CLASS_FLAG_OFFSET,
        )
    if descriptor_section not in sections:
        raise BenUnsupportedVariantError(
            f"{name} record has no channel descriptor section {descriptor_section:#06x}"
        )
    for rel, value, what in (
        (layout.RECORD_CLASS_RATE_FIELD, fields.rate_field, "sampling-rate field"),
        (layout.RECORD_CLASS_PRE_TRIGGER_FIELD, fields.pre_trigger_samples, "pre-trigger count"),
    ):
        repeated = record.u32(rel)
        if repeated != value:
            raise BenStructureError(
                f"record-class section {what} {repeated} disagrees with header value {value}",
                offset=record.start + rel,
            )
    return _RECORD_CLASS_ENUM[name], code


def _records(sections: dict[int, Section], type_code: int, *, exactly_one: bool = False) -> list[ByteView]:
    section = sections.get(type_code)
    if section is None:
        return []
    entries = record_entries(section, layout.RECORD_SIZES[type_code])
    if exactly_one and len(entries) != 1:
        raise BenStructureError(
            f"section {type_code:#06x} holds {len(entries)} records, expected exactly 1",
            offset=section.offset,
        )
    return entries


def _strings(sections: dict[int, Section], type_code: int) -> StringTable | None:
    section = sections.get(type_code)
    return StringTable(section.payload, type_code) if section else None


# ─────────────────────────────────────────────────────────────────────────────
# Sample-layout container
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Container:
    end: int  # absolute offset just past the container
    summary: ByteView
    layout_map: Section


def _read_container(file: ByteView, pos: int) -> _Container:
    length = file.u32(pos + 2, "container length")
    body = file.sub(pos + layout.CONTAINER_FRAME_SIZE, length, "sample-layout container")
    blocks: dict[int, Section] = {}
    rel = 0
    while rel < body.size:
        block = read_section(body, rel)
        if block.type_code in blocks:
            raise BenStructureError(f"container sub-block {block.type_code:#06x} occurs twice", offset=block.offset)
        blocks[block.type_code] = block
        rel = block.payload.end - body.start
    if rel != body.size:
        raise BenStructureError("container sub-blocks overrun the container length", offset=body.start)

    for required in (layout.SUB_BLOCK_RECORD_SUMMARY, layout.SUB_BLOCK_SAMPLE_LAYOUT):
        if required not in blocks:
            raise BenUnsupportedVariantError(f"sample-layout container has no sub-block {required:#06x}")
    tag = file.u16(body.end - file.start, "sample-data tag")
    if tag != layout.SAMPLE_DATA_TAG:
        raise BenStructureError(
            f"expected sample-data tag {layout.SAMPLE_DATA_TAG:#06x} after the container, found {tag:#06x}",
            offset=body.end,
        )
    summary = blocks[layout.SUB_BLOCK_RECORD_SUMMARY].payload
    if summary.size < layout.SUMMARY_MIN_SIZE:
        raise BenStructureError("record-summary sub-block is too short", offset=summary.start)
    return _Container(body.end, summary, blocks[layout.SUB_BLOCK_SAMPLE_LAYOUT])


def _check_summary(summary: ByteView, fields: _HeaderFields, class_code: int) -> None:
    checks = (
        (layout.SUMMARY_RECORD_NUMBER_FIELD, summary.u32, fields.record_number, "record number"),
        (layout.SUMMARY_RECORD_CLASS_CODE_FIELD, summary.u16, class_code, "record class"),
        (layout.SUMMARY_WORDS_PER_SAMPLE_FIELD, summary.u16, fields.words_per_sample, "words per sample"),
        (layout.SUMMARY_RATE_FIELD, summary.u32, fields.rate_field, "sampling-rate field"),
        (layout.SUMMARY_PRE_TRIGGER_FIELD, summary.u32, fields.pre_trigger_samples, "pre-trigger count"),
        (layout.SUMMARY_SAMPLE_COUNT_FIELD, summary.u32, fields.sample_count, "sample count"),
    )
    for rel, read, expected, what in checks:
        value = read(rel)
        if value != expected:
            raise BenStructureError(
                f"record-summary {what} {value} disagrees with header value {expected}",
                offset=summary.start + rel,
            )


def _check_payload_boundary(file: ByteView, header: BenHeader) -> None:
    expected_end = header.sample_data_offset + header.sample_count * header.sample_stride_bytes
    if expected_end > file.size:
        raise BenTruncatedError(
            f"sample data needs {header.sample_count} x {header.sample_stride_bytes} bytes from "
            f"{header.sample_data_offset:#x} (to {expected_end}); the file is {file.size} bytes"
        )
    if expected_end < file.size:
        raise BenStructureError(
            f"{file.size - expected_end} unexplained byte(s) after {header.sample_count} samples of "
            f"{header.sample_stride_bytes} bytes",
            offset=expected_end,
        )


def _read_layout_map(section: Section, words_per_sample: int) -> dict[int, BenSampleSlot]:
    slots: dict[int, BenSampleSlot] = {}
    for entry in record_entries(section, layout.LAYOUT_ENTRY_SIZE):
        channel_id = entry.u16(0)
        word_index = entry.u16(2)
        bit = entry.u8(4)
        if word_index >= words_per_sample:
            raise BenStructureError(
                f"layout map places channel {channel_id} in word {word_index}, but a sample has "
                f"{words_per_sample} words",
                offset=entry.start,
            )
        if bit >= layout.BITS_PER_WORD:
            raise BenStructureError(f"layout map gives channel {channel_id} bit {bit}", offset=entry.start)
        if channel_id in slots:
            raise BenStructureError(f"layout map lists channel {channel_id} twice", offset=entry.start)
        slots[channel_id] = BenSampleSlot(word_index, bit, entry.u8(5))
    return slots


# ─────────────────────────────────────────────────────────────────────────────
# Channels
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _ChannelConfig:
    record_class: BenRecordClass
    value_records: list[ByteView]
    physical_records: list[ByteView]
    trigger_ids: set[int]
    event_records: list[ByteView]
    channel_names: StringTable
    event_names: StringTable
    bay_of_channel: dict[int, str]
    bay_of_binary: dict[int, str]

    @classmethod
    def read(cls, sections: dict[int, Section], record_class: BenRecordClass) -> _ChannelConfig:
        descriptor_section = (
            layout.SECTION_ANALOG_CHANNELS
            if record_class is BenRecordClass.FAST
            else layout.SECTION_CALCULATED_CHANNELS
        )
        bay_of_channel, bay_of_binary = _read_bays(sections)
        return cls(
            record_class=record_class,
            value_records=_records(sections, descriptor_section),
            physical_records=_records(sections, layout.SECTION_PHYSICAL_DIGITALS),
            trigger_ids={r.u16(layout.TRIGGER_ID_FIELD) for r in _records(sections, layout.SECTION_TRIGGER_DEFINITIONS)},
            event_records=_records(sections, layout.SECTION_EVENT_CHANNELS),
            channel_names=_strings(sections, layout.SECTION_CHANNEL_NAMES),  # type: ignore[arg-type]
            event_names=_strings(sections, layout.SECTION_EVENT_NAMES),  # type: ignore[arg-type]
            bay_of_channel=bay_of_channel,
            bay_of_binary=bay_of_binary,
        )


def _read_bays(sections: dict[int, Section]) -> tuple[dict[int, str], dict[int, str]]:
    """Map channel ids to bay (feeder) names where BEN declares the link."""
    names = _strings(sections, layout.SECTION_BAY_NAMES)
    if names is None:
        return {}, {}
    bays: dict[int, str] = {}
    for record in _records(sections, layout.SECTION_BAYS):
        text = names.name(record.u16(layout.BAY_NAME_FIELD))
        bays[record.u32(layout.BAY_ID_FIELD)] = text.split(layout.BAY_NAME_SEPARATOR)[-1].strip()

    of_channel: dict[int, str] = {}
    for record in _records(sections, layout.SECTION_BAY_CHANNELS):
        bay = bays.get(record.u32(layout.BAY_CHANNEL_BAY_ID_FIELD))
        if bay is not None:
            of_channel[record.u16(layout.BAY_CHANNEL_CHANNEL_ID_FIELD)] = bay

    of_binary: dict[int, str] = {}
    for record in _records(sections, layout.SECTION_BAY_CARDS):
        bay = bays.get(record.u32(layout.CARD_BAY_ID_FIELD))
        if bay is None:
            continue
        for i in range(layout.CARD_MEMBER_COUNT):
            member = record.u32(layout.CARD_MEMBERS_FIELD + 4 * i)
            if member:
                of_binary[member] = bay
    return of_channel, of_binary


def _build_value_channels(config: _ChannelConfig, slots: dict[int, BenSampleSlot]) -> list[BenValueChannel]:
    fast = config.record_class is BenRecordClass.FAST
    channels: list[BenValueChannel] = []
    seen: set[int] = set()
    for index, record in enumerate(config.value_records):
        if fast:
            channel_id = record.u16(layout.ANALOG_ID_FIELD)
            trigger_id = record.u16(layout.ANALOG_TRIGGER_ID_FIELD)
            event_id = record.u16(layout.ANALOG_EVENT_ID_FIELD)
            name_offset = record.u16(layout.ANALOG_NAME_FIELD)
            codes = (
                record.u8(layout.ANALOG_QUANTITY_CODE_FIELD),
                record.u8(layout.ANALOG_PHASE_CODE_FIELD),
                record.u8(layout.ANALOG_UNIT_CODE_FIELD),
                record.u8(layout.ANALOG_UNIT_MULTIPLIER_FIELD),
            )
            scale = record.f32(layout.ANALOG_SCALE_FIELD)
            offset = record.f32(layout.ANALOG_OFFSET_FIELD)
            primary: float | None = record.f32(layout.ANALOG_PRIMARY_RATING_FIELD)
            secondary: float | None = record.f32(layout.ANALOG_SECONDARY_RATING_FIELD)
            hardware: int | None = record.u16(layout.ANALOG_HARDWARE_ADDRESS_FIELD)
            kind = BenChannelKind.ANALOG
            invalid_raw = None
        else:
            channel_id = record.u16(layout.CALCULATED_ID_FIELD)
            trigger_id = record.u16(layout.CALCULATED_TRIGGER_ID_FIELD)
            event_id = record.u16(layout.CALCULATED_EVENT_ID_FIELD)
            name_offset = record.u16(layout.CALCULATED_NAME_FIELD)
            codes = (
                record.u8(layout.CALCULATED_QUANTITY_CODE_FIELD),
                record.u8(layout.CALCULATED_PHASE_CODE_FIELD),
                record.u8(layout.CALCULATED_UNIT_CODE_FIELD),
                record.u8(layout.CALCULATED_UNIT_MULTIPLIER_FIELD),
            )
            scale = record.f32(layout.CALCULATED_SCALE_FIELD)
            offset = record.f32(layout.CALCULATED_OFFSET_FIELD)
            primary = secondary = hardware = None
            kind = BenChannelKind.CALCULATED
            invalid_raw = layout.CALCULATED_UNAVAILABLE_RAW

        if channel_id in seen:
            raise BenStructureError(f"channel id {channel_id} is declared twice", offset=record.start)
        seen.add(channel_id)
        slot = slots.get(channel_id)
        if slot is None:
            raise BenStructureError(
                f"value channel {channel_id} has no entry in the sample layout map", offset=record.start
            )
        if slot.bit != 0:
            raise BenStructureError(
                f"value channel {channel_id} is mapped to bit {slot.bit}; value channels occupy a whole word",
                offset=record.start,
            )
        if not np.isfinite(scale) or not np.isfinite(offset):
            raise BenStructureError(f"value channel {channel_id} has a non-finite scale/offset", offset=record.start)

        quantity_code, phase_code, unit_code, multiplier = codes
        unit_entry = layout.UNIT_CODES.get(unit_code)
        prefix = layout.UNIT_MULTIPLIERS.get(multiplier)
        unit = prefix + unit_entry[0] if unit_entry is not None and prefix is not None else None
        channels.append(
            BenValueChannel(
                index=index,
                channel_id=channel_id,
                name=config.channel_names.name(name_offset),
                kind=kind,
                measurement=unit_entry[1] if unit_entry is not None else None,
                unit=unit,
                unit_code=unit_code,
                unit_multiplier_exponent=multiplier,
                phase=layout.PHASE_CODES.get(phase_code),
                phase_code=phase_code,
                quantity_code=quantity_code,
                scale=float(scale),
                offset=float(offset),
                primary_rating=primary,
                secondary_rating=secondary,
                bay_name=config.bay_of_channel.get(channel_id),
                trigger_id=trigger_id,
                event_id=event_id,
                hardware_address=hardware,
                slot=slot,
                invalid_raw_value=invalid_raw,
                descriptor_raw=record.raw(0, record.size),
            )
        )
    return channels


def _build_digital_channels(
    config: _ChannelConfig,
    slots: dict[int, BenSampleSlot],
    diagnostics: list[BenDiagnostic],
) -> list[BenDigitalChannel]:
    physical_names = {
        r.u16(layout.PHYSICAL_DIGITAL_ID_FIELD): config.channel_names.name(r.u16(layout.PHYSICAL_DIGITAL_NAME_FIELD))
        for r in config.physical_records
    }
    channels: list[BenDigitalChannel] = []
    unresolved: list[str] = []
    for index, record in enumerate(config.event_records):
        event_id = record.u16(layout.EVENT_ID_FIELD)
        event_name = config.event_names.name(record.u16(layout.EVENT_NAME_FIELD))
        trigger_id = record.u16(layout.EVENT_TRIGGER_ID_FIELD)
        source_id = record.u16(layout.EVENT_SOURCE_ID_FIELD)

        if trigger_id and trigger_id in config.trigger_ids:
            source, bit_id, name = BenDigitalSource.DERIVED, trigger_id, event_name
        elif not trigger_id and source_id in physical_names:
            source, bit_id, name = BenDigitalSource.PHYSICAL, source_id, physical_names[source_id]
        else:
            unresolved.append(f"{event_name!r} (trigger {trigger_id}, source {source_id})")
            continue
        slot = slots.get(bit_id)
        if slot is None:
            unresolved.append(f"{event_name!r} (channel {bit_id} absent from the layout map)")
            continue
        channels.append(
            BenDigitalChannel(
                index=index,
                event_id=event_id,
                name=name,
                event_name=event_name,
                source=source,
                bit_channel_id=bit_id,
                source_channel_id=source_id,
                bay_name=config.bay_of_binary.get(bit_id),
                slot=slot,
            )
        )
    if unresolved:
        diagnostics.append(
            BenDiagnostic(
                "unresolved_digital_channels",
                "warning",
                f"{len(unresolved)} exported binary channel(s) could not be resolved to a sample bit "
                f"through BEN's descriptor links and were omitted: {', '.join(unresolved[:10])}"
                + (" ..." if len(unresolved) > 10 else ""),
            )
        )
    return channels


def _check_slot_overlaps(values: list[BenValueChannel], digitals: list[BenDigitalChannel]) -> None:
    """A value word must belong to exactly one value channel and no bit channel."""
    owners: dict[int, str] = {}
    for channel in values:
        word = channel.slot.word_index
        if word in owners:
            raise BenStructureError(
                f"value channels {owners[word]!r} and {channel.name!r} share sample word {word}"
            )
        owners[word] = channel.name
    for channel in digitals:
        if channel.slot.word_index in owners:
            raise BenStructureError(
                f"binary channel {channel.name!r} is mapped into value word {channel.slot.word_index} "
                f"({owners[channel.slot.word_index]!r})"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostics derived from values
# ─────────────────────────────────────────────────────────────────────────────


def _value_diagnostics(record: BenRecord) -> list[BenDiagnostic]:
    diagnostics: list[BenDiagnostic] = []
    for channel in record.value_channels:
        if channel.unit is None:
            diagnostics.append(
                BenDiagnostic(
                    "unknown_unit_code",
                    "warning",
                    f"channel {channel.name!r}: unit code {channel.unit_code} / multiplier "
                    f"{channel.unit_multiplier_exponent} is not a validated BEN unit; unit left unknown",
                )
            )
        raw = record.raw_values(channel)
        if channel.invalid_raw_value is not None:
            invalid = int(np.count_nonzero(raw == channel.invalid_raw_value))
            if invalid:
                diagnostics.append(
                    BenDiagnostic(
                        "unavailable_samples",
                        "info",
                        f"channel {channel.name!r}: {invalid} of {raw.size} samples are marked unavailable",
                    )
                )
        elif np.any(raw == layout.CALCULATED_UNAVAILABLE_RAW):
            diagnostics.append(
                BenDiagnostic(
                    "unverified_raw_extreme",
                    "warning",
                    f"analog channel {channel.name!r} contains raw {layout.CALCULATED_UNAVAILABLE_RAW}; "
                    "its meaning for sampled inputs is unverified, so it is kept as a measured value",
                )
            )
    return diagnostics


def _unreferenced_slot_diagnostics(
    slots: dict[int, BenSampleSlot],
    values: list[BenValueChannel],
    digitals: list[BenDigitalChannel],
) -> list[BenDiagnostic]:
    used = {c.channel_id for c in values} | {c.bit_channel_id for c in digitals}
    unused = sorted(set(slots) - used)
    if not unused:
        return []
    return [
        BenDiagnostic(
            "unreferenced_layout_entries",
            "warning",
            f"{len(unused)} sample-layout entr(y/ies) belong to no exposed channel "
            f"(channel ids {unused[:10]}{' ...' if len(unused) > 10 else ''}); their data is not decoded",
        )
    ]


def _duplicate_name_diagnostics(record: BenRecord) -> list[BenDiagnostic]:
    names = Counter(c.name for c in record.value_channels) + Counter(c.name for c in record.digital_channels)
    duplicates = sorted(name for name, count in names.items() if count > 1)
    if not duplicates:
        return []
    return [
        BenDiagnostic(
            "duplicate_channel_names",
            "info",
            f"{len(duplicates)} channel name(s) occur more than once (channel ids stay unique): "
            + ", ".join(repr(n) for n in duplicates[:10])
            + (" ..." if len(duplicates) > 10 else ""),
        )
    ]
