"""BEN5K Slow record normalizer: builds a ``BenRecord`` from raw BEN5K Slow bytes.

Entry point: ``parse_ben5k_slow(data: bytes) -> BenRecord``

Production isolation: this module is NOT called by ``parse_ben()`` or any
production path.  It is only reachable through ``parse_ben_experimental()``
in parser.py, which requires the caller to explicitly opt in.

Channel mapping status:
  TENTATIVE channels (0 < word_index < wps, first claimant of that word) are
  included in value_channels with a scale of 1.0, offset 0.0, unit 'raw'.
  They carry a 'ben5k_slow_mapping_tentative' diagnostic.

  UNRESOLVED channels (OOR, zero-index ambiguous, or word conflict) are NOT
  included in value_channels.  Their count and names are reported in diagnostics.

Scale factors are not decoded from descriptor bytes 24-27.  Oracle validation
against SCADA or COMTRADE data is required before publishing engineering values.

Timestamp uncertainty: The BEN5K Slow recorder uses the same 9-byte timestamp
encoding as SubBen and BEN5K Fast (confirmed at offset 0x64).  Whether this
records UTC or local time is unconfirmed.  A 'time_basis_unconfirmed' diagnostic
is always attached.
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from dataclasses import replace

import numpy as np

from app.providers.ben import layout
from app.providers.ben.errors import BenStructureError, BenTruncatedError
from app.providers.ben.model import (
    BenChannelKind,
    BenDiagnostic,
    BenDigitalChannel,
    BenHeader,
    BenRecord,
    BenRecordClass,
    BenSampleSlot,
    BenTriggerTime,
    BenValueChannel,
)
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

_YEAR_BASE = layout.TRIGGER_TIME_YEAR_BASE   # 1900
_FRACTION_BASE = layout.TRIGGER_FRACTION_DIGIT_BASE  # 100


def _decode_trigger_time(raw9: bytes) -> BenTriggerTime:
    """Decode the 9-byte BEN5K Slow timestamp into a BenTriggerTime.

    Layout: YY MM DD HH MM SS hh tt µµ (same as SubBen and BEN5K Fast).
    Labelled UTC even though the timezone basis is unconfirmed for this family.
    """
    yr, mo, dy, hh, mm, ss, h1, h2, h3 = raw9[:9]
    year = _YEAR_BASE + yr
    try:
        dt = datetime(year, mo, dy, hh, mm, ss, tzinfo=timezone.utc)
    except ValueError:
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return BenTriggerTime(
            utc_whole_second=dt,
            fraction_digits=(h1, h2, h3),
            microsecond=None,
        )

    us = h1 * 10_000 + h2 * 100 + h3 if (h1 < 100 and h2 < 100 and h3 < 100) else None
    return BenTriggerTime(
        utc_whole_second=dt,
        fraction_digits=(h1, h2, h3),
        microsecond=us,
    )


def _build_header(header5k: Ben5kSlowHeader, data: bytes) -> BenHeader:
    """Translate Ben5kSlowHeader into the canonical BenHeader."""
    trigger_time = _decode_trigger_time(header5k.trigger_bytes)
    payload_bytes = header5k.sample_count * header5k.words_per_sample * 2
    data_offset = len(data) - payload_bytes
    trigger_info = bytes(data[layout.TRIGGER_INFO_OFFSET : layout.HEADER_SIZE])

    return BenHeader(
        recorder_unit_id=header5k.recorder_unit,
        station_name=header5k.station_name,
        record_label="",
        record_number=header5k.record_number,
        record_class=BenRecordClass.BEN5K_SLOW_LEGACY,
        record_class_code=0,
        rate_field=header5k.rate_hz * layout.RATE_FIELD_PER_SAMPLE_PER_SECOND,
        sample_count=header5k.sample_count,
        pre_trigger_samples=header5k.pre_trigger,
        words_per_sample=header5k.words_per_sample,
        sample_data_offset=data_offset,
        trigger_time=trigger_time,
        trigger_info_raw=trigger_info,
    )


def parse_ben5k_slow(data: bytes) -> BenRecord:
    """Parse a BEN5K Slow file into a BenRecord.

    This is the ONLY public entry point for the BEN5K Slow decoder.
    Must NOT be called from production paths — use parse_ben_experimental()
    in parser.py to opt in.

    Returns:
        A BenRecord whose value_channels contains TENTATIVE channels only.
        Scale = 1.0 and offset = 0.0 (raw int16).  Unit = 'raw'.
        All UNRESOLVED channels are reported in diagnostics only.

    Raises:
        BenTruncatedError, BenStructureError: structural or size errors.
    """
    if not isinstance(data, bytes):
        data = bytes(data)

    diagnostics: list[BenDiagnostic] = []

    # ── 1. Read fixed header ──────────────────────────────────────────────────
    header5k = read_header(data)

    # ── 2. Read config header (cross-check recorder unit) ────────────────────
    cfg = read_config_header(data)
    if cfg.recorder_unit != header5k.recorder_unit:
        diagnostics.append(BenDiagnostic(
            code="ben5k_slow_config_unit_mismatch",
            severity="warning",
            message=(
                f"BEN5K Slow config header recorder unit ({cfg.recorder_unit}) "
                f"does not match fixed header ({header5k.recorder_unit})"
            ),
        ))

    # ── 3. Read HVDC formula descriptor (preserved, not decoded) ────────────
    hvdc = read_hvdc_formula(data)

    # ── 4. Read channel groups and classify channels ─────────────────────────
    groups = read_channel_groups(data, header5k)
    tentative = active_channels(groups)
    unresolved = unresolved_channels(groups)

    # ── 5. Build sample_words matrix ─────────────────────────────────────────
    payload_bytes = header5k.sample_count * header5k.words_per_sample * 2
    data_offset = len(data) - payload_bytes
    if data_offset <= layout.HEADER_SIZE:
        raise BenTruncatedError(
            f"BEN5K Slow payload ({payload_bytes} bytes) leaves no room for config area"
        )
    sample_words = np.frombuffer(
        data,
        dtype=layout.SAMPLE_WORD_DTYPE,
        count=header5k.sample_count * header5k.words_per_sample,
        offset=data_offset,
    ).reshape(header5k.sample_count, header5k.words_per_sample)

    # ── 6. Build canonical BenHeader ─────────────────────────────────────────
    header = _build_header(header5k, data)

    # ── 7. Build value_channels from TENTATIVE channels ──────────────────────
    value_channels: list[BenValueChannel] = []
    for idx, ch in enumerate(tentative):
        slot = BenSampleSlot(
            word_index=ch.word_index_tentative,
            bit=0,
            slot_kind=0,
        )
        value_channels.append(
            BenValueChannel(
                index=idx,
                channel_id=idx,
                name=ch.name,
                kind=BenChannelKind.CALCULATED,
                measurement=None,       # measurement type not decoded from descriptor
                unit="raw",             # scale not confirmed; raw int16 values
                unit_code=0,
                unit_multiplier_exponent=0,
                phase=None,
                phase_code=0,
                quantity_code=0,
                scale=1.0,
                offset=0.0,
                primary_rating=None,
                secondary_rating=None,
                bay_name=ch.group_name,
                trigger_id=0,
                event_id=0,
                hardware_address=None,
                slot=slot,
                invalid_raw_value=None,
                descriptor_raw=b"",
            )
        )

    # ── 8. Attach diagnostics ────────────────────────────────────────────────
    diagnostics.append(BenDiagnostic(
        code="time_basis_unconfirmed",
        severity="warning",
        message=(
            "BEN5K Slow trigger timestamp decoded as UTC (same encoding as SubBen), "
            "but no COMTRADE oracle exists to confirm UTC vs local time for this "
            "recorder family. Do not synchronize cross-event timing from this value."
        ),
    ))
    diagnostics.append(BenDiagnostic(
        code="layout_ben5k_slow_legacy",
        severity="info",
        message=(
            f"Decoded via BEN5K Slow group-based config layout. "
            f"Tentative channels: {len(tentative)}, "
            f"unresolved channels: {len(unresolved)}, "
            f"groups: {len(groups)}."
        ),
    ))
    diagnostics.append(BenDiagnostic(
        code="ben5k_slow_mapping_tentative",
        severity="warning",
        message=(
            "BEN5K Slow channel-to-sample-word mapping uses the formula "
            "word_index = selector >> 8. S4 engineering analysis confirmed this "
            "formula for Group 0 (BDNG 1) only: FREQ BDNG 1 produces 49.6-50.6 Hz "
            "(Malaysian 50 Hz grid confirmed), POWER BDNG 1 produces 63-152 MW, "
            "MVAR BDNG 1 produces 13.5-13.7 Mvar (oracle validation still needed "
            "for power and Mvar scaling). Groups 1+ channels are excluded: S4 "
            "data analysis showed their word positions hold limit-event/status "
            "data, not the declared measurements. Scale factors are not decoded; "
            "all values are raw int16 with unit 'raw'."
        ),
    ))

    if tentative:
        names = ", ".join(f"{ch.name!r}(w{ch.word_index_tentative})" for ch in tentative[:8])
        if len(tentative) > 8:
            names += f" ... ({len(tentative) - 8} more)"
        diagnostics.append(BenDiagnostic(
            code="ben5k_slow_tentative_channels",
            severity="info",
            message=f"Tentative mapped channels: {names}",
        ))

    if unresolved:
        # Group by status for clearer reporting
        oor = [ch for ch in unresolved if ch.status == SlowChannelStatus.UNRESOLVED_OOR]
        zero = [ch for ch in unresolved if ch.status == SlowChannelStatus.UNRESOLVED_ZERO]
        conflict = [ch for ch in unresolved if ch.status == SlowChannelStatus.UNRESOLVED_CONFLICT]
        formula_unconfirmed = [
            ch for ch in unresolved if ch.status == SlowChannelStatus.UNRESOLVED_FORMULA_UNCONFIRMED
        ]
        if formula_unconfirmed:
            names = ", ".join(
                f"{ch.name!r}(w{ch.word_index_tentative},grp{ch.group_index})"
                for ch in formula_unconfirmed[:4]
            )
            if len(formula_unconfirmed) > 4:
                names += f" ... ({len(formula_unconfirmed) - 4} more)"
            diagnostics.append(BenDiagnostic(
                code="ben5k_slow_formula_unconfirmed_channels",
                severity="warning",
                message=(
                    f"{len(formula_unconfirmed)} channel(s) have a word index from "
                    f"selector >> 8 but are from Groups 1+ where that formula is "
                    f"NOT confirmed. S4 engineering analysis shows these word positions "
                    f"hold limit-event/status data, not the declared measurements. "
                    f"These channels are excluded from value_channels. {names}"
                ),
            ))
        if oor:
            diagnostics.append(BenDiagnostic(
                code="ben5k_slow_oor_channels",
                severity="info",
                message=(
                    f"{len(oor)} channel(s) have out-of-range word index "
                    f"(selector >> 8 >= words_per_sample={header5k.words_per_sample}). "
                    f"First: {oor[0].name!r} in {oor[0].group_name!r} "
                    f"selector={oor[0].selector_raw:#x} wi={oor[0].word_index_tentative}."
                ),
            ))
        if zero:
            diagnostics.append(BenDiagnostic(
                code="ben5k_slow_zero_index_channels",
                severity="info",
                message=(
                    f"{len(zero)} channel(s) have a low-byte selector "
                    f"(selector < 256, word_index_tentative=0). "
                    f"Word 0 is ambiguous; these channels are unresolved. "
                    f"First: {zero[0].name!r} in {zero[0].group_name!r} "
                    f"selector={zero[0].selector_raw:#x}."
                ),
            ))
        if conflict:
            diagnostics.append(BenDiagnostic(
                code="ben5k_slow_conflict_channels",
                severity="info",
                message=(
                    f"{len(conflict)} channel(s) conflict with an earlier channel "
                    f"on the same word index. "
                    f"First: {conflict[0].name!r} in {conflict[0].group_name!r} "
                    f"wi={conflict[0].word_index_tentative}."
                ),
            ))

    if hvdc.name:
        diagnostics.append(BenDiagnostic(
            code="ben5k_slow_hvdc_formula",
            severity="info",
            message=(
                f"HVDC formula channel {hvdc.name!r} found at config offset 0xFE. "
                f"Formula decoding is deferred; this channel is not included in "
                f"value_channels."
            ),
        ))

    record = BenRecord(
        header=header,
        value_channels=tuple(value_channels),
        digital_channels=(),   # BEN5K Slow has no digital channels in the primary groups
        diagnostics=tuple(diagnostics),
        sample_words=sample_words,
    )
    return record
