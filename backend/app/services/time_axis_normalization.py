"""Shared Time-Axis value normalization (CSV/Excel ingestion, DEC-072/
DEC-074/DEC-075).

The ONE place an already-CONFIRMED time-axis interpreter's own
`interpreted` preview strings (produced by
`app.services.time_axis_service`'s own interpreter registry, via
`build_preview_rows()`) are turned back into native Python values and,
where needed, canonical elapsed-seconds relative to a first/anchor row.
Extracted out of `app.services.preparation_conversion_service`
(Slice 10) so that module, `app.services.preparation_export_service`'s
own "export the resolved Time Axis" enhancement (DEC-074), and
`app.services.time_axis_service.build_configured_time_values()`'s own
"show the resolved Time Axis in Data Preview" enhancement (DEC-075)
share exactly ONE implementation of this logic -- none of the three may
ever silently disagree about what a configured Time Axis MEANS (each
task's own explicit "must agree"/"reuse existing resolved-time logic"
requirement).

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


def relative_seconds_with_anchor(natives: list[Any], anchor: Any, *, family: str) -> list[float]:
    """Canonical elapsed seconds for each already-parsed native value,
    relative to an EXTERNALLY supplied `anchor` (rather than assuming
    `natives[0]` -- see `relative_seconds()` below for that common
    case). The Data Preview's own "Configured Time" column needs this
    generalized form: a later preview PAGE must still normalize against
    the true FIRST ACTIVE ROW of the whole dataset, never that page's
    own first row (a critical guardrail -- see
    `app.services.time_axis_service.build_configured_time_values`'s own
    docstring). Every `natives` entry must be non-`None` -- callers
    raise their own typed error for a `None` BEFORE calling this, so
    the failing row number is always reported specifically rather than
    surfacing here as a generic `TypeError`/`ValueError`.

    For `FAMILY_ABSOLUTE`, raises `TypeError` if a `natives` entry mixes
    timezone-awareness with `anchor` (or vice-versa) -- exactly Python's
    own `datetime` subtraction behavior, left unwrapped so each caller
    can attach its own row-specific context."""
    if not natives:
        return []
    if family == FAMILY_ABSOLUTE:
        return [(n - anchor).total_seconds() for n in natives]
    if family == FAMILY_PARTIAL:
        anchor_seconds = seconds_from_midnight(anchor)
        return [seconds_from_midnight(n) - anchor_seconds for n in natives]
    anchor_value = float(anchor)
    return [float(n) - anchor_value for n in natives]


def relative_seconds(natives: list[Any], *, family: str) -> list[float]:
    """Canonical elapsed seconds for each already-parsed native value,
    relative to the FIRST one -- the one "preferred direction" every
    family uses (originally Slice 10's own `_canonical_time_and_anchor`
    rule, unchanged here). A thin convenience wrapper around
    `relative_seconds_with_anchor()` using `natives[0]` as the anchor;
    every `natives` entry must be non-`None`, matching that function's
    own contract."""
    if not natives:
        return []
    return relative_seconds_with_anchor(natives, natives[0], family=family)


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
