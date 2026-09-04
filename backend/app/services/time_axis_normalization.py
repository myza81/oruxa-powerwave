"""Shared Time-Axis value normalization (CSV/Excel ingestion, DEC-072/
DEC-074).

The ONE place an already-CONFIRMED time-axis interpreter's own
`interpreted` preview strings (produced by
`app.services.time_axis_service`'s own interpreter registry, via
`build_preview_rows()`) are turned back into native Python values and,
where needed, canonical elapsed-seconds relative to the first active
row. Extracted out of `app.services.preparation_conversion_service`
(Slice 10) so that module and `app.services.preparation_export_service`'s
own "export the resolved Time Axis" enhancement share exactly ONE
implementation of this logic -- the two features must never silently
disagree about what a configured Time Axis MEANS (task's own explicit
"canonical conversion and cleaned export must agree" requirement).

**No new inference happens here.** Every function in this module only
re-parses a string an interpreter's own `build_preview_rows()` ALREADY
produced (itself already reviewed/confirmed by the engineer) -- nothing
here re-runs date-order elimination, re-estimates cadence, or invents a
timezone/date. `parse_native_time_value()` re-parsing an interpreter's
own `isoformat()`/`"HH:MM:SS.ffffff"`/`"{seconds:.6f} s"` output is
exactly the same round-trip `preparation_conversion_service` already
performed before this module existed -- moved, not changed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.domain.time_axis import FAMILY_ABSOLUTE, FAMILY_PARTIAL


def parse_native_time_value(interpreted: str | None, *, family: str) -> Any:
    """One interpreter-produced `interpreted` string -> its native
    Python value: `datetime.datetime` for `FAMILY_ABSOLUTE`,
    `datetime.time` for `FAMILY_PARTIAL`, `float` seconds for every
    other family (`elapsed`/`sample_index`/a repeated-timestamp
    reconstruction resolving to a non-absolute anchor -- all of which
    format their own `interpreted` as the same `"{seconds:.6f} s"`
    shape). Returns `None` for `interpreted is None` (a row that itself
    failed to interpret) or a value that unexpectedly fails to re-parse
    under its own stated family -- both defensive cases a caller must
    handle explicitly, never silently coerced to zero/now/epoch."""
    if interpreted is None:
        return None
    if family == FAMILY_ABSOLUTE:
        try:
            return dt.datetime.fromisoformat(interpreted)
        except ValueError:
            return None
    if family == FAMILY_PARTIAL:
        try:
            return dt.datetime.strptime(interpreted, "%H:%M:%S.%f").time()
        except ValueError:
            return None
    text = interpreted.strip()
    if text.endswith(" s"):
        text = text[:-2]
    try:
        return float(text)
    except ValueError:
        return None


def seconds_from_midnight(value: dt.time) -> float:
    return value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1_000_000


def relative_seconds(natives: list[Any], *, family: str) -> list[float]:
    """Canonical elapsed seconds for each already-parsed native value,
    relative to the FIRST one -- the one "preferred direction" every
    family uses (originally Slice 10's own `_canonical_time_and_anchor`
    rule, unchanged here). Every `natives` entry must be non-`None` --
    callers raise their own typed error for a `None` BEFORE calling
    this, so the failing row number is always reported specifically
    rather than surfacing here as a generic `TypeError`/`ValueError`.

    For `FAMILY_ABSOLUTE`, raises `TypeError` if `natives` mixes a
    timezone-aware value with the first (naive) one or vice-versa --
    exactly Python's own `datetime` subtraction behavior, left
    unwrapped so each caller can attach its own row-specific context."""
    if not natives:
        return []
    if family == FAMILY_ABSOLUTE:
        first = natives[0]
        return [(n - first).total_seconds() for n in natives]
    if family == FAMILY_PARTIAL:
        first_seconds = seconds_from_midnight(natives[0])
        return [seconds_from_midnight(n) - first_seconds for n in natives]
    first_value = float(natives[0])
    return [float(n) - first_value for n in natives]


def format_absolute_iso(value: dt.datetime) -> str:
    """Deterministic export representation for one resolved absolute
    timestamp: millisecond precision by default, widened to full
    microsecond precision only when genuine sub-millisecond information
    is present in the value itself -- never truncated to whole seconds,
    never padded beyond what the value actually carries. Preserves a
    real timezone offset exactly as `datetime.isoformat()` already does
    (a naive `value` renders with no offset at all, same as always);
    never invents one, and never appends a bare `Z` (Python's own
    `isoformat()` always writes `+00:00` for a UTC-aware value, never
    `Z`, which already satisfies "do not fabricate a Z" with no special
    case needed)."""
    if value.microsecond % 1000 == 0:
        return value.isoformat(timespec="milliseconds")
    return value.isoformat(timespec="microseconds")


def format_relative_seconds(value: float) -> str:
    """Deterministic export representation for one resolved relative
    (elapsed/sample-index-derived/partial) seconds value -- fixed
    3-decimal-place text."""
    return f"{value:.3f}"
