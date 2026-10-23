"""Explicit per-recording clock interpretation; never changes original timing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.domain.source_timezone import TimeBasis, canonical_utc

if TYPE_CHECKING:
    from app.domain.source import SourceMetadata


@dataclass(frozen=True, slots=True)
class TimeReferenceInterpretation:
    offset_minutes: int
    assigned_at: datetime
    provenance: str = "user_assigned"


def validate_interpretation(source: SourceMetadata, interpretation: TimeReferenceInterpretation | None) -> None:
    if source.time_basis != TimeBasis.UNKNOWN:
        raise ValueError("Only recordings with an unverified time basis can be interpreted.")
    if interpretation is None:
        return
    offset = interpretation.offset_minutes
    if type(offset) is not int or not -720 <= offset <= 840 or offset % 15:
        raise ValueError("UTC offset must be a whole 15-minute increment from -12:00 to +14:00.")
    clocks = [value for value in (source.start_time, source.trigger_time) if value is not None]
    if not clocks or any(value.tzinfo is not None for value in clocks):
        raise ValueError("Interpretation requires original clock digits without a conflicting timezone.")
    # Validate rollover before accepting state; datetime cannot represent years outside 1..9999.
    for value in clocks:
        interpret_clock(value, offset)


def interpret_clock(value: datetime, offset_minutes: int) -> datetime:
    return value.replace(tzinfo=timezone(timedelta(minutes=offset_minutes))).astimezone(timezone.utc)


def source_timestamp_utc(source: SourceMetadata, field: str) -> datetime | None:
    value = getattr(source, field)
    if value is None:
        return None
    if source.time_reference_interpretation is not None and source.time_basis == TimeBasis.UNKNOWN:
        return interpret_clock(value, source.time_reference_interpretation.offset_minutes)
    return canonical_utc(value, time_basis=source.time_basis)


def effective_timing_reference(source: SourceMetadata) -> str:
    if source.time_reference_interpretation is not None and source_timestamp_utc(source, "start_time") is not None:
        return "absolute"
    return source.timing_reference


def source_start_epoch(source: SourceMetadata) -> float | None:
    instant = source_timestamp_utc(source, "start_time")
    return instant.timestamp() if instant is not None else None
