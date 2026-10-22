"""BEN5K record normalizer: builds a ``BenRecord`` from raw BEN5K bytes.

Entry point: ``parse_ben5k(data: bytes) -> BenRecord``

Production isolation: this module is NOT called by ``parse_ben()`` or any
production path. It is only reachable through ``parse_ben_experimental()``
in parser.py, which requires the caller to explicitly opt in.

Timestamp uncertainty: The BEN5K recorder stores a trigger timestamp using
the same 9-byte YY MM DD HH MM SS hh tt µµ encoding as SubBen files (confirmed
at offset 0x64 from the same GPTH recording).  Whether BEN5K stores UTC or
local time has NOT been confirmed by an oracle (SubBen stores UTC, confirmed
by COMTRADE comparison; no such COMTRADE exists for BEN5K).  A
``"time_basis_unconfirmed"`` diagnostic is always attached.  The returned
``BenTriggerTime.utc_whole_second`` is labelled UTC by Python's type system
but may actually be local time until oracle confirmation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace

import numpy as np

from app.providers.ben import layout
from app.providers.ben.errors import BenStructureError, BenTruncatedError
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
from app.providers.ben.legacy_ben5k.reader import (
    Ben5kHeader,
    read_header,
    read_channel_descriptors,
)
from app.providers.ben.legacy_ben5k.channel_map import classify_channels

# BEN5K uses the same trigger-time base as SubBen.
_YEAR_BASE = layout.TRIGGER_TIME_YEAR_BASE  # 1900
_FRACTION_BASE = layout.TRIGGER_FRACTION_DIGIT_BASE  # 100


def _decode_trigger_time(raw9: bytes) -> BenTriggerTime:
    """Decode the 9-byte BEN5K timestamp into a ``BenTriggerTime``.

    Layout: YY MM DD HH MM SS hh tt µµ (each one byte, same as SubBen at 0x64).
    The result is labelled UTC even though the timezone basis is unconfirmed.
    """
    yr, mo, dy, hh, mm, ss, h1, h2, h3 = raw9[:9]
    year = _YEAR_BASE + yr
    try:
        dt = datetime(year, mo, dy, hh, mm, ss, tzinfo=timezone.utc)
    except ValueError:
        # Corrupted timestamp — return epoch so callers get a safe sentinel.
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return BenTriggerTime(
            utc_whole_second=dt,
            fraction_digits=(h1, h2, h3),
            microsecond=None,
        )

    # Sub-second: three base-100 digits → microseconds
    # h1 = hundredths (×10000 µs), h2 = 1e-4 s (×100 µs), h3 = µs
    if h1 < 100 and h2 < 100 and h3 < 100:
        us = h1 * 10_000 + h2 * 100 + h3
    else:
        us = None

    return BenTriggerTime(
        utc_whole_second=dt,
        fraction_digits=(h1, h2, h3),
        microsecond=us,
    )


def _build_header(header5k: Ben5kHeader, data: bytes) -> BenHeader:
    """Translate a ``Ben5kHeader`` into the canonical ``BenHeader``."""
    # recorder_unit_id is a u16 at offset 0x0C (shared with SubBen).
    import struct
    recorder_unit_id = struct.unpack_from("<H", data, layout.RECORDER_UNIT_ID_OFFSET)[0]

    trigger_time = _decode_trigger_time(header5k.trigger_bytes)

    # Payload starts at (file_size − sample_count × words_per_sample × 2).
    payload_bytes = header5k.sample_count * header5k.words_per_sample * 2
    data_offset = len(data) - payload_bytes

    # trigger_info_raw: same region as SubBen (0x80..0xDB)
    trigger_info = bytes(data[layout.TRIGGER_INFO_OFFSET : layout.HEADER_SIZE])

    return BenHeader(
        recorder_unit_id=recorder_unit_id,
        station_name=header5k.station_name,
        record_label="",           # BEN5K has no record label field
        record_number=0,           # BEN5K has no record number field
        record_class=BenRecordClass.BEN5K_LEGACY,
        record_class_code=0,       # no typed-section record-class in BEN5K
        rate_field=header5k.rate_hz * layout.RATE_FIELD_PER_SAMPLE_PER_SECOND,
        sample_count=header5k.sample_count,
        pre_trigger_samples=header5k.pre_trigger,
        words_per_sample=header5k.words_per_sample,
        sample_data_offset=data_offset,
        trigger_time=trigger_time,
        trigger_info_raw=trigger_info,
    )


def parse_ben5k(data: bytes) -> BenRecord:
    """Parse a BEN5K file into a ``BenRecord``.

    This is the ONLY public entry point for the legacy BEN5K decoder.
    It must NOT be called from production paths — use ``parse_ben_experimental()``
    in parser.py to opt in.

    Returns:
        A ``BenRecord`` compatible with ``to_disturbance_record()`` in
        normalize.py. Inactive and unsupported channels are excluded from
        ``value_channels`` and ``digital_channels``; their counts are
        reported in ``diagnostics``.

    Raises:
        BenTruncatedError, BenStructureError: structural or size errors.
    """
    if not isinstance(data, bytes):
        data = bytes(data)

    diagnostics: list[BenDiagnostic] = []

    # ── 1. Read header and channel descriptors ─────────────────────────────
    header5k = read_header(data)
    analog_raw, digital_raw = read_channel_descriptors(data, header5k)

    # ── 2. Build sample_words matrix (needed for variance detection) ───────
    payload_bytes = header5k.sample_count * header5k.words_per_sample * 2
    data_offset = len(data) - payload_bytes
    if data_offset <= layout.HEADER_SIZE:
        raise BenTruncatedError(
            f"BEN5K payload ({payload_bytes} bytes) leaves no room for config area"
        )
    sample_words = np.frombuffer(
        data,
        dtype=layout.SAMPLE_WORD_DTYPE,
        count=header5k.sample_count * header5k.words_per_sample,
        offset=data_offset,
    ).reshape(header5k.sample_count, header5k.words_per_sample)

    # ── 3. Classify channels with payload variance analysis ────────────────
    ch_map = classify_channels(
        list(analog_raw),
        list(digital_raw),
        header5k.words_per_sample,
        sample_words=sample_words,
    )

    # ── 4. Build canonical BenHeader ──────────────────────────────────────
    header = _build_header(header5k, data)

    # ── 5. Build value_channels from recorded_analog ─────────────────────
    value_channels: list[BenValueChannel] = []
    for idx, ch in enumerate(ch_map.recorded_analog):
        # Map BEN5K type_byte → measurement kind
        if ch.type_byte == 0x00:
            measurement = "voltage"
        elif ch.type_byte == 0x04:
            measurement = "current"
        else:
            measurement = None

        # Map BEN5K phase_seq (1=R/A, 2=Y/B, 3=B/C, 4=N) → phase string
        # Phase seq uses R/Y/B convention from the recorder; canonical phase
        # codes are A/B/C/N.  Use layout.PHASE_CODES mapping (0=None, 1=A,
        # 2=B, 3=C, 4=N) — BEN5K's 1/2/3/4 coincidentally matches.
        phase = layout.PHASE_CODES.get(ch.phase_seq)

        # Unit code: derive from type_byte (voltage=29 V, current=5 A).
        if ch.type_byte == 0x00:
            unit_code = 29   # V
            unit = "kV"
            unit_multiplier = 3
        elif ch.type_byte == 0x04:
            unit_code = 5    # A
            unit = "kA"
            unit_multiplier = 3
        else:
            unit_code = 0
            unit = None
            unit_multiplier = 0

        slot = BenSampleSlot(
            word_index=ch.word_index,
            bit=0,
            slot_kind=0,
        )
        value_channels.append(
            BenValueChannel(
                index=idx,
                channel_id=idx,
                name=ch.name,
                kind=BenChannelKind.ANALOG,
                measurement=measurement,
                unit=unit,
                unit_code=unit_code,
                unit_multiplier_exponent=unit_multiplier,
                phase=phase,
                phase_code=ch.phase_seq,
                quantity_code=ch.type_byte,
                scale=ch.scale,
                offset=ch.offset,
                primary_rating=None,
                secondary_rating=None,
                bay_name=None,
                trigger_id=0,
                event_id=0,
                hardware_address=None,
                slot=slot,
                invalid_raw_value=None,
                descriptor_raw=b"",
            )
        )

    # ── 6. Build digital_channels from verified_digital ───────────────────
    digital_channels: list[BenDigitalChannel] = []
    for idx, ch in enumerate(ch_map.verified_digital):
        slot = BenSampleSlot(
            word_index=ch.sample_word_index,
            bit=ch.bit_index,
            slot_kind=0,
        )
        digital_channels.append(
            BenDigitalChannel(
                index=idx,
                event_id=idx,
                name=ch.name,
                event_name=ch.name,
                source=BenDigitalSource.PHYSICAL,
                bit_channel_id=idx,
                source_channel_id=idx,
                bay_name=None,
                slot=slot,
                active_low=layout.DIGITAL_STORED_BIT_ACTIVE_LOW,
            )
        )

    # ── 7. Attach diagnostics ─────────────────────────────────────────────
    diagnostics.append(BenDiagnostic(
        code="time_basis_unconfirmed",
        severity="warning",
        message=(
            "BEN5K trigger timestamp decoded as UTC (same encoding as SubBen), "
            "but no COMTRADE oracle exists to confirm UTC vs local time for this "
            "recorder family. Do not synchronize cross-event timing from this value."
        ),
    ))
    diagnostics.append(BenDiagnostic(
        code="layout_ben5k_legacy",
        severity="info",
        message=(
            f"Decoded via legacy BEN5K flat config layout. "
            f"Recorded analog: {len(ch_map.recorded_analog)}, "
            f"verified digital: {len(ch_map.verified_digital)}."
        ),
    ))
    if ch_map.inactive_analog:
        diagnostics.append(BenDiagnostic(
            code="ben5k_inactive_analog",
            severity="info",
            message=(
                f"{len(ch_map.inactive_analog)} analog channel(s) excluded: "
                f"word_index outside active analog region or duplicate "
                f"(inactive feeder). First: {ch_map.inactive_analog[0].name!r}."
            ),
        ))
    if ch_map.inactive_digital:
        diagnostics.append(BenDiagnostic(
            code="ben5k_inactive_digital",
            severity="info",
            message=(
                f"{len(ch_map.inactive_digital)} digital channel(s) excluded: "
                f"sample word in constant-0x0800 region (inactive feeder). "
                f"First: {ch_map.inactive_digital[0].name!r}."
            ),
        ))
    if ch_map.constant_placeholder_digital:
        diagnostics.append(BenDiagnostic(
            code="ben5k_constant_placeholder_digital",
            severity="info",
            message=(
                f"{len(ch_map.constant_placeholder_digital)} digital channel(s) excluded: "
                f"sample word carries constant value 0x0800 across all samples "
                f"(confirmed inactive-feeder placeholder). "
                f"First: {ch_map.constant_placeholder_digital[0].name!r}."
            ),
        ))
    if ch_map.unsupported_digital:
        diagnostics.append(BenDiagnostic(
            code="ben5k_unsupported_digital",
            severity="warning",
            message=(
                f"{len(ch_map.unsupported_digital)} group-0 digital channel(s) "
                f"(SENS OUT) not decoded: addressing scheme unconfirmed. "
                f"First: {ch_map.unsupported_digital[0].name!r}."
            ),
        ))

    return BenRecord(
        header=header,
        value_channels=tuple(value_channels),
        digital_channels=tuple(digital_channels),
        diagnostics=tuple(diagnostics),
        sample_words=sample_words,
    )
