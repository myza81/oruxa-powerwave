"""Deterministic absolute-time, elapsed-time, and sample-index
interpreters (CSV/Excel ingestion Slices 8A-8B, DEC-072). Authoritative
design source: docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md,
each slice's own task spec.

Implements four REAL (non-`manual`) entries the Slice 7 registry always
anticipated:

    `absolute_datetime`  -- one Time Axis column, a full timestamp (8A)
    `split_date_time`    -- two Time Axis columns, Date + Time combined (8A)
    `elapsed_numeric`    -- one Time Axis column, a relative numeric
                            value with an explicit, required unit (8B)
    `sample_index`       -- one Time Axis column, a plain ordinal
                            sequence, optionally paired with a
                            user-supplied sampling interval (8B)

Both are deterministic, bounded, non-fuzzy parsers -- a small, explicit
table of `datetime.strptime` patterns (plus `datetime.fromisoformat`'s
own fast path for ISO-8601, which already handles the space/`T`
separator, fractional seconds, and a trailing `Z`/`±HH:MM` offset
without any pattern of our own). There is deliberately no
`dateutil`/free-form fuzzy parsing anywhere in this module -- the
task's own explicit "controlled parsing strategy" requirement.

**Ambiguity by elimination, not by guessing.** For a non-ISO date like
`01/02/2026`, this module never assumes a locale. Instead it tries
EVERY known date order (`dmy`/`mdy`/`ymd`) against the WHOLE bounded
sample and keeps only the orders under which every sampled value is a
structurally valid date (`strptime` itself already rejects month=31,
day=13-under-%m, etc. -- no extra range-checking needed). If exactly
one order survives, the reading is unambiguous BY ELIMINATION (e.g.
`31/08/2026` can only be `dmy`, since `mdy` would require a 31st
month) -- reported as `native` provenance, `unambiguous`. If two or
more orders survive, the case is genuinely ambiguous -- reported via
the `ambiguous_date_order` diagnostic, `review_required` (via
`resolve_status()`), and only the user's own explicit `date_order`
choice can resolve it (`user_specified` provenance once they do).
Never auto-confirmed merely because one order is statistically more
common (task's own explicit instruction).

**Time-only values stay `partial`, never silently promoted.** If every
sampled value in a candidate absolute-datetime column is a bare
time-of-day (matches one of the time-only patterns with no date
component at all), `detect_absolute_datetime()` reports
`FAMILY_PARTIAL`, not `FAMILY_ABSOLUTE` -- see `app.domain.time_axis`'s
own family table, §3's own "family is a classification of the SOURCE
representation" note: an interpreter is allowed, and expected, to
report the TRUE family even when it differs from what the column role
alone would suggest, rather than force-fitting the family the
interpreter happens to be named after.

**Bounded, always.** Every function in this module receives an
ALREADY-FETCHED, already-bounded list of sample values (see
`app.services.time_axis_service`'s own module docstring for exactly
how that bound is enforced) -- nothing here ever reads a session, a
file, or a database row itself.

**Slice 8B: no invented absolute time, no silent unit guessing.**
`elapsed_numeric` NEVER anchors its values to a fabricated date (no
`2000-01-01`, no file-open time, no browser/local time) -- its own
`family` is always `FAMILY_ELAPSED`, never promoted to `absolute`.
`detect_elapsed_numeric()` requires an EXPLICIT unit before it will
report anything but a `missing_elapsed_unit` diagnostic (`ambiguity:
"ambiguous"`, routing through the same `STATUS_REVIEW_REQUIRED`
precedence Slice 8A's own `ambiguous_date_order` established -- one
mechanism, two producers). `detect_sample_index()` treats "no sampling
interval supplied" as a first-class, complete, NON-diagnostic state
(`provenance=index_only`) -- this is the approved fallback (§F), never
an error to report or a gap to fill.

**Preserve source order, never repair.** Both `elapsed_numeric` and
`sample_index` only ever REPORT backward/repeated/gap findings as
diagnostics -- neither ever reorders, drops, collapses, or synthesizes
a row. `sample_index`'s own gap/backward/repeat check compares each
value only to the PREVIOUS one in the bounded sample, in original row
order -- never sorted first.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from app.domain.preparation_issue import SEVERITY_WARNING
from app.domain.time_axis import (
    AMBIGUITY_AMBIGUOUS,
    AMBIGUITY_INVALID,
    AMBIGUITY_UNAMBIGUOUS,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    DATE_ORDER_AUTO,
    DATE_ORDER_DMY,
    DATE_ORDER_MDY,
    DATE_ORDER_YMD,
    DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
    DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD,
    DIAGNOSTIC_MISSING_DATETIME_VALUE,
    DIAGNOSTIC_MISSING_ELAPSED_UNIT,
    DIAGNOSTIC_MISSING_ELAPSED_VALUE,
    DIAGNOSTIC_MISSING_SAMPLE_INDEX,
    DIAGNOSTIC_MIXED_DATETIME_FORMAT,
    DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE,
    DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX,
    DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL,
    DIAGNOSTIC_REPEATED_ELAPSED_TIME,
    DIAGNOSTIC_REPEATED_SAMPLE_INDEX,
    DIAGNOSTIC_SAMPLE_INDEX_GAP,
    DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD,
    DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE,
    DIAGNOSTIC_UNPARSEABLE_DATETIME,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    PROVENANCE_USER_SPECIFIED,
    UNIT_MICROSECONDS,
    UNIT_MILLISECONDS,
    UNIT_NANOSECONDS,
    UNIT_SECONDS,
    TimeAxisDetectionResult,
    TimeAxisDiagnostic,
)

#: Bounded, explicit time-of-day pattern table -- tried in this fixed
#: order (most-specific first) for both the single-column combined
#: date+time case and the split Date/Time interpreter's own Time
#: column. Never extended dynamically.
_TIME_PATTERNS: tuple[str, ...] = (
    "%H:%M:%S.%f",
    "%H:%M:%S",
    "%I:%M:%S.%f %p",
    "%I:%M:%S %p",
    "%I:%M %p",
)

#: Bounded, explicit date-only pattern table per candidate order. Both
#: `/` and `-` separators are tried (the task's own example list uses
#: both for the same `dmy` order) -- a genuinely different separator is
#: not treated as a genuinely different "order," only as a different
#: literal pattern to try under that order.
_DATE_PATTERNS_BY_ORDER: dict[str, tuple[str, ...]] = {
    DATE_ORDER_DMY: ("%d/%m/%Y", "%d-%m-%Y"),
    DATE_ORDER_MDY: ("%m/%d/%Y", "%m-%d-%Y"),
    DATE_ORDER_YMD: ("%Y/%m/%d", "%Y-%m-%d"),
}

_KNOWN_ORDERS: tuple[str, ...] = (DATE_ORDER_DMY, DATE_ORDER_MDY, DATE_ORDER_YMD)

#: strptime directive -> friendly display token, purely for the
#: human-readable `detected_format` option value shown in the UI (§P) --
#: never itself used to parse anything; parsing always goes back through
#: the real strptime pattern.
_DISPLAY_TOKENS: dict[str, str] = {
    "%Y": "YYYY", "%m": "MM", "%d": "DD",
    "%H": "HH", "%M": "mm", "%S": "ss", "%f": "SSS",
    "%I": "hh", "%p": "A",
}


def _display_format(pattern: str) -> str:
    display = pattern
    for directive, token in _DISPLAY_TOKENS.items():
        display = display.replace(directive, token)
    return display


def _parse_iso(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_with_pattern(value: str, pattern: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value.strip(), pattern)
    except ValueError:
        return None


def _is_time_only(value: str) -> bool:
    stripped = value.strip()
    return any(_parse_with_pattern(stripped, pattern) is not None for pattern in _TIME_PATTERNS)


@dataclass(slots=True, frozen=True)
class _FormatMatch:
    """How well ONE candidate pattern explains the WHOLE sample --
    `is_full_match` is the only thing that ever counts as "this is the
    format"; a partial match is only ever used for a diagnostic
    message, never treated as a resolved reading."""

    pattern: str
    match_count: int
    total_count: int

    @property
    def match_rate(self) -> float:
        return self.match_count / self.total_count if self.total_count else 0.0

    @property
    def is_full_match(self) -> bool:
        return self.total_count > 0 and self.match_count == self.total_count


def _score_pattern(values: list[str], pattern: str, *, parser) -> _FormatMatch:
    match_count = sum(1 for v in values if parser(v, pattern) is not None)
    return _FormatMatch(pattern=pattern, match_count=match_count, total_count=len(values))


def _candidate_patterns_for_order(order: str, *, with_time: bool) -> list[str]:
    date_patterns = _DATE_PATTERNS_BY_ORDER[order]
    if not with_time:
        return list(date_patterns)
    return [f"{d} {t}" for d in date_patterns for t in _TIME_PATTERNS]


def _best_match_for_order(values: list[str], order: str) -> _FormatMatch:
    """The single best-explaining pattern for this order across every
    combined date+time candidate AND the bare date-only candidates
    (a source may legitimately have no time component at all) -- "best"
    means a full match if any exists, else the highest partial-match
    count, so a `mixed`/`unparseable` diagnostic can still report a
    concrete, useful match rate."""
    scored = [
        _score_pattern(values, pattern, parser=_parse_with_pattern)
        for pattern in _candidate_patterns_for_order(order, with_time=True) + _candidate_patterns_for_order(order, with_time=False)
    ]
    full = [m for m in scored if m.is_full_match]
    if full:
        return full[0]
    return max(scored, key=lambda m: m.match_count)


def _confidence_for_partial(match: _FormatMatch) -> str:
    if match.match_count == 0:
        return CONFIDENCE_UNKNOWN
    if match.match_rate >= 0.5:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def detect_absolute_datetime(
    raw_values_by_row: list[tuple[int, Any]],
    *,
    requested_options: dict[str, Any],
    sample_size_label: str = "column",
) -> TimeAxisDetectionResult:
    """Single-column absolute datetime detection (task §A). Never
    scans anything beyond the already-bounded `raw_values_by_row` list
    handed to it by `app.services.time_axis_service`.

    `requested_options` may carry a `date_order` -- one of
    `KNOWN_DATE_ORDERS` (§C) -- from either a prior confirmation
    (stored) or the current dry-run request. Only consulted when the
    data itself is genuinely ambiguous (2+ orders fully match); an
    unambiguous-by-elimination or ISO reading always wins regardless of
    what was requested, since that is simply what the data says, not a
    preference to override.
    """
    diagnostics: list[TimeAxisDiagnostic] = []
    total = len(raw_values_by_row)
    non_empty = [(row_number, str(value)) for row_number, value in raw_values_by_row if value not in (None, "")]
    missing_count = total - len(non_empty)
    if missing_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_MISSING_DATETIME_VALUE,
                message=f"{missing_count} of {total} sampled row(s) have no value in this Time Axis {sample_size_label}.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"missing_count": missing_count, "sample_size": total},
            )
        )
    raw_values = [v for _, v in non_empty]
    if not raw_values:
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_UNKNOWN,
            diagnostics=diagnostics, resolved_options={"date_order": requested_options.get("date_order", DATE_ORDER_AUTO)},
        )

    if all(_is_time_only(v) for v in raw_values):
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE,
                message="Every sampled value is a time-of-day with no date component -- this belongs to the 'partial' family, not 'absolute'.",
                suggested_action="A date component is required. Use Date + Time if the date lives in a separate column.",
                ambiguity=AMBIGUITY_INVALID,
            )
        )
        return TimeAxisDetectionResult(
            family=FAMILY_PARTIAL, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_HIGH,
            diagnostics=diagnostics, resolved_options={},
        )

    iso_match = _score_pattern(raw_values, "iso8601", parser=lambda v, _p: _parse_iso(v))
    if iso_match.is_full_match:
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_HIGH,
            diagnostics=diagnostics,
            resolved_options={"date_order": DATE_ORDER_YMD, "detected_format": "ISO-8601"},
        )

    per_order_match = {order: _best_match_for_order(raw_values, order) for order in _KNOWN_ORDERS}
    candidate_orders = sorted(order for order, m in per_order_match.items() if m.is_full_match)

    if len(candidate_orders) == 1:
        order = candidate_orders[0]
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_HIGH,
            diagnostics=diagnostics,
            resolved_options={"date_order": order, "detected_format": _display_format(per_order_match[order].pattern)},
        )

    if len(candidate_orders) >= 2:
        requested_order = requested_options.get("date_order")
        if requested_order in candidate_orders:
            # The user's own explicit choice resolves what the data
            # alone could not -- this is now a settled reading, not an
            # open ambiguity, so no `ambiguous_date_order` diagnostic
            # is emitted for this outcome.
            match = per_order_match[requested_order]
            return TimeAxisDetectionResult(
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_HIGH,
                diagnostics=diagnostics,
                resolved_options={"date_order": requested_order, "detected_format": _display_format(match.pattern)},
            )
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
                message=f"The date order is ambiguous -- {' and '.join(candidate_orders)} both fit every sampled value.",
                suggested_action="Choose the correct date order to confirm this Time Axis configuration.",
                ambiguity=AMBIGUITY_AMBIGUOUS,
                details={"candidate_orders": candidate_orders},
            )
        )
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_LOW,
            diagnostics=diagnostics, resolved_options={"date_order": DATE_ORDER_AUTO},
        )

    # No order, and no ISO reading, fully explains the sample -- report
    # the single best-explaining candidate (by match count) as a
    # mixed/unparseable finding, never silently normalized (task §L).
    best_order, best_match = max(per_order_match.items(), key=lambda kv: kv[1].match_count)
    code = DIAGNOSTIC_MIXED_DATETIME_FORMAT if best_match.match_count > 0 else DIAGNOSTIC_UNPARSEABLE_DATETIME
    unmatched = best_match.total_count - best_match.match_count
    diagnostics.append(
        TimeAxisDiagnostic(
            severity_hint=SEVERITY_WARNING,
            code=code,
            message=f"{unmatched} of {best_match.total_count} sampled value(s) could not be parsed under a consistent format.",
            suggested_action="Review the sampled values -- the column may mix formats or contain invalid entries.",
            ambiguity=AMBIGUITY_INVALID,
            details={"matched": best_match.match_count, "sample_size": best_match.total_count, "best_candidate_order": best_order},
        )
    )
    return TimeAxisDetectionResult(
        family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confidence=_confidence_for_partial(best_match),
        diagnostics=diagnostics, resolved_options={"date_order": requested_options.get("date_order", DATE_ORDER_AUTO)},
    )


def detect_split_date_time(
    date_values_by_row: list[tuple[int, Any]],
    time_values_by_row: list[tuple[int, Any]],
    *,
    requested_options: dict[str, Any],
) -> TimeAxisDetectionResult:
    """Split Date + Time detection (task §B). Reuses
    `detect_absolute_datetime()` verbatim for the DATE column's own
    ambiguity handling (§B's own "support user-confirmed date format
    where ambiguous" requirement is identical to the single-column
    case) -- never a second, parallel date-order algorithm. The TIME
    column is checked independently against the same bounded
    `_TIME_PATTERNS` table used by the single-column interpreter's own
    combined patterns.

    `family`/`provenance`/`confidence`/`resolved_options` come from the
    DATE column's own detection outcome (the ambiguity that matters is
    the date order, exactly as for the single-column case); the TIME
    column only ever contributes its own diagnostics (missing/
    unparseable time-of-day values) -- never a second ambiguity axis,
    since a time-of-day alone has no locale-dependent ordering to
    disambiguate.
    """
    date_result = detect_absolute_datetime(date_values_by_row, requested_options=requested_options, sample_size_label="date column")

    total = len(time_values_by_row)
    non_empty_times = [(row_number, str(value)) for row_number, value in time_values_by_row if value not in (None, "")]
    missing_time_count = total - len(non_empty_times)
    diagnostics = list(date_result.diagnostics)
    if missing_time_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_MISSING_DATETIME_VALUE,
                message=f"{missing_time_count} of {total} sampled row(s) have no value in the Time column.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"missing_count": missing_time_count, "sample_size": total},
            )
        )
    time_values = [v for _, v in non_empty_times]
    if time_values:
        time_match = max(
            (_score_pattern(time_values, pattern, parser=_parse_with_pattern) for pattern in _TIME_PATTERNS),
            key=lambda m: m.match_count,
        )
        if not time_match.is_full_match:
            unmatched = time_match.total_count - time_match.match_count
            code = DIAGNOSTIC_MIXED_DATETIME_FORMAT if time_match.match_count > 0 else DIAGNOSTIC_UNPARSEABLE_DATETIME
            diagnostics.append(
                TimeAxisDiagnostic(
                    severity_hint=SEVERITY_WARNING,
                    code=code,
                    message=f"{unmatched} of {time_match.total_count} sampled Time column value(s) could not be parsed as a time-of-day.",
                    ambiguity=AMBIGUITY_INVALID,
                    details={"matched": time_match.match_count, "sample_size": time_match.total_count},
                )
            )

    return TimeAxisDetectionResult(
        family=date_result.family, provenance=date_result.provenance, confidence=date_result.confidence,
        diagnostics=diagnostics, resolved_options=date_result.resolved_options,
    )


def _combine_date_and_time(date_value: str, time_value: str, *, date_order: str) -> dt.datetime | None:
    """Parse ONE row's own date+time pair under an already-RESOLVED
    (non-`auto`) `date_order` -- used only for building preview rows
    (§J), never for detection itself (see `detect_split_date_time`
    above)."""
    date_part = _parse_iso(date_value)
    if date_part is None and date_order in _DATE_PATTERNS_BY_ORDER:
        for pattern in _DATE_PATTERNS_BY_ORDER[date_order]:
            date_part = _parse_with_pattern(date_value, pattern)
            if date_part is not None:
                break
    if date_part is None:
        return None
    for pattern in _TIME_PATTERNS:
        time_part = _parse_with_pattern(time_value, pattern)
        if time_part is not None:
            return dt.datetime.combine(date_part.date(), time_part.time())
    return None


def parse_absolute_datetime(value: str, *, date_order: str) -> dt.datetime | None:
    """Parse ONE value under an already-RESOLVED (non-`auto`)
    `date_order` -- used only for building single-column preview rows
    (§J)."""
    parsed = _parse_iso(value)
    if parsed is not None:
        return parsed
    if date_order not in _DATE_PATTERNS_BY_ORDER:
        return None
    for pattern in _candidate_patterns_for_order(date_order, with_time=True) + _candidate_patterns_for_order(date_order, with_time=False):
        parsed = _parse_with_pattern(value, pattern)
        if parsed is not None:
            return parsed
    return None


def build_absolute_datetime_preview(
    samples: list[tuple[int, tuple[Any, ...]]], *, resolved_options: dict[str, Any], limit: int,
) -> list[tuple[int, tuple[Any, ...], str | None]]:
    """Bounded {row_number, original, interpreted} rows for the
    single-column interpreter (§J/§16) -- `original` is the raw sample
    value(s) verbatim, `interpreted` is the resulting ISO-8601 string or
    `None` for a row that failed to parse under the resolved format
    (never dropped -- see `app.domain.time_axis.TimeAxisPreviewRow`'s
    own docstring)."""
    date_order = resolved_options.get("date_order", DATE_ORDER_AUTO)
    rows = []
    for row_number, values in samples[:limit]:
        value = values[0]
        if value in (None, ""):
            rows.append((row_number, values, None))
            continue
        parsed = parse_absolute_datetime(str(value), date_order=date_order) if date_order != DATE_ORDER_AUTO else _parse_iso(str(value))
        rows.append((row_number, values, parsed.isoformat() if parsed else None))
    return rows


def build_split_date_time_preview(
    samples: list[tuple[int, tuple[Any, ...]]], *, resolved_options: dict[str, Any], limit: int,
) -> list[tuple[int, tuple[Any, ...], str | None]]:
    """Split Date+Time counterpart of `build_absolute_datetime_preview`
    -- `values[0]` is the date cell, `values[1]` is the time cell (the
    same `(date_column_index, time_column_index)` order
    `TimeAxisConfiguration.column_indices` is documented to use for
    this interpreter)."""
    date_order = resolved_options.get("date_order", DATE_ORDER_AUTO)
    rows = []
    for row_number, values in samples[:limit]:
        date_value, time_value = (values + (None, None))[:2]
        if date_value in (None, "") or time_value in (None, ""):
            rows.append((row_number, values, None))
            continue
        combined = _combine_date_and_time(str(date_value), str(time_value), date_order=date_order)
        rows.append((row_number, values, combined.isoformat() if combined else None))
    return rows


# ---- Slice 8B: elapsed numeric time + sample index -------------------

#: Canonical-seconds conversion factor per known unit (§B) -- the ONLY
#: place a unit-to-seconds ratio is defined; `interval_seconds`/derived
#: preview values are always computed through this table, never a second
#: ad-hoc conversion elsewhere.
_ELAPSED_UNIT_SECONDS_FACTOR: dict[str, float] = {
    UNIT_SECONDS: 1.0,
    UNIT_MILLISECONDS: 1e-3,
    UNIT_MICROSECONDS: 1e-6,
    UNIT_NANOSECONDS: 1e-9,
}


def _to_float(value: Any) -> float | None:
    """A bounded, deterministic numeric parse -- accepts anything
    `float()` accepts (including a numeric string from a CSV cell or a
    native `int`/`float` from an Excel cell), rejects everything else.
    Never raises; `None` means "not a number," handled by the caller as
    a `non_numeric_*` diagnostic rather than a crash."""
    if isinstance(value, bool):  # bool is technically an int subtype -- never treated as a numeric sample here
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_elapsed_numeric(
    raw_values_by_row: list[tuple[int, Any]], *, requested_unit: str | None,
) -> TimeAxisDetectionResult:
    """Single-column elapsed/relative numeric time detection (task §A).
    `family` is always `FAMILY_ELAPSED` -- this interpreter never
    invents an absolute anchor (task §3's own explicit guardrail).

    `requested_unit` must already be validated as either `None` or a
    member of `KNOWN_ELAPSED_UNITS` by the caller (`app.services.
    time_axis_service.set_time_axis_configuration`'s own unit-set
    check) -- this function only ever distinguishes "no unit yet"
    (`None`) from "a real unit," it never itself rejects a garbage
    string.

    `None` produces `missing_elapsed_unit` (`ambiguity: "ambiguous"`,
    §8/§9's own "units are never silently inferred" rule) and NOTHING
    else is computed -- there is nothing safe to say about backward/
    repeated/non-uniform elapsed time before even knowing what a "1"
    in this column means (a "1" could be 1 second or 1 nanosecond;
    "goes backward" is not even well-defined without a unit since the
    comparison itself doesn't depend on unit -- but reporting data-
    quality findings for values whose meaning is not yet settled would
    imply more confidence than the framework actually has)."""
    total = len(raw_values_by_row)
    non_empty = [(row_number, value) for row_number, value in raw_values_by_row if value not in (None, "")]
    missing_count = total - len(non_empty)
    diagnostics: list[TimeAxisDiagnostic] = []
    if missing_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_MISSING_ELAPSED_VALUE,
                message=f"{missing_count} of {total} sampled row(s) have no value in this Time Axis column.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"missing_count": missing_count, "sample_size": total},
            )
        )

    if requested_unit is None:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_MISSING_ELAPSED_UNIT,
                message="This column's values could mean seconds, milliseconds, microseconds, or nanoseconds -- a unit is required.",
                suggested_action="Choose the unit this column's numbers are expressed in.",
                ambiguity=AMBIGUITY_AMBIGUOUS,
            )
        )
        return TimeAxisDetectionResult(
            family=FAMILY_ELAPSED, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_UNKNOWN,
            diagnostics=diagnostics, resolved_options={}, resolved_unit=None, resolved_interval_seconds=None,
        )

    numeric_by_row: list[tuple[int, float]] = []
    non_numeric_count = 0
    for row_number, value in non_empty:
        parsed = _to_float(value)
        if parsed is None:
            non_numeric_count += 1
        else:
            numeric_by_row.append((row_number, parsed))
    if non_numeric_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE,
                message=f"{non_numeric_count} of {len(non_empty)} sampled value(s) are not numeric.",
                ambiguity=AMBIGUITY_INVALID,
                details={"non_numeric_count": non_numeric_count, "sample_size": len(non_empty)},
            )
        )

    backward_count = 0
    repeated_count = 0
    deltas: list[float] = []
    for (_, prev), (_, curr) in zip(numeric_by_row, numeric_by_row[1:]):
        delta = curr - prev
        if delta < 0:
            backward_count += 1
        elif delta == 0:
            repeated_count += 1
        else:
            deltas.append(delta)
    if backward_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD,
                message=f"Elapsed time decreases at {backward_count} point(s) in the sampled rows.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"backward_count": backward_count},
            )
        )
    if repeated_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_REPEATED_ELAPSED_TIME,
                message=f"{repeated_count} consecutive sampled row(s) repeat the same elapsed value.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"repeated_count": repeated_count},
            )
        )
    if len(deltas) >= 2:
        reference = deltas[0]
        tolerance = max(1e-12, abs(reference) * 0.01)
        if any(abs(d - reference) > tolerance for d in deltas):
            diagnostics.append(
                TimeAxisDiagnostic(
                    severity_hint=SEVERITY_WARNING,
                    code=DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL,
                    message="The spacing between consecutive elapsed values is not uniform across the sampled rows.",
                    ambiguity=AMBIGUITY_UNAMBIGUOUS,
                )
            )

    return TimeAxisDetectionResult(
        family=FAMILY_ELAPSED, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_HIGH,
        diagnostics=diagnostics, resolved_options={}, resolved_unit=requested_unit, resolved_interval_seconds=None,
    )


def build_elapsed_preview(
    samples: list[tuple[int, tuple[Any, ...]]], *, resolved_unit: str | None, limit: int,
) -> list[tuple[int, tuple[Any, ...], str | None]]:
    """Bounded {original, interpreted-seconds} rows (§Q) -- `interpreted`
    is always a canonical-SECONDS string (`"0.010000 s"`), never the
    original unit re-displayed, so the preview always shows what this
    configuration would actually mean downstream. `None` (not `0`) for
    a missing/non-numeric row or while no unit is resolved yet -- a
    failed/undetermined row is never silently treated as zero elapsed
    time."""
    factor = _ELAPSED_UNIT_SECONDS_FACTOR.get(resolved_unit) if resolved_unit else None
    rows = []
    for row_number, values in samples[:limit]:
        value = values[0] if values else None
        parsed = _to_float(value) if value not in (None, "") else None
        if factor is None or parsed is None:
            rows.append((row_number, values, None))
            continue
        rows.append((row_number, values, f"{parsed * factor:.6f} s"))
    return rows


def detect_sample_index(
    raw_values_by_row: list[tuple[int, Any]], *, requested_interval_seconds: float | None,
) -> TimeAxisDetectionResult:
    """Single-column sample-index detection (task §E-§L). `family` is
    always `FAMILY_SAMPLE_INDEX`. Unlike `elapsed_numeric`'s required
    unit, an ABSENT `requested_interval_seconds` is a complete, valid,
    NON-diagnostic outcome (task §F: "This is not an error. It is the
    approved fallback") -- `provenance` alone communicates the
    difference (`index_only` vs `user_specified`), never a diagnostic.

    Never assumes the index starts at 0 or 1, never renumbers, never
    sorts -- backward/repeated/gap checks all compare each sampled
    value only to the PREVIOUS one, in the ORIGINAL row order the
    sample arrived in."""
    total = len(raw_values_by_row)
    non_empty = [(row_number, value) for row_number, value in raw_values_by_row if value not in (None, "")]
    missing_count = total - len(non_empty)
    diagnostics: list[TimeAxisDiagnostic] = []
    if missing_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_MISSING_SAMPLE_INDEX,
                message=f"{missing_count} of {total} sampled row(s) have no value in this Time Axis column.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"missing_count": missing_count, "sample_size": total},
            )
        )

    numeric_by_row: list[tuple[int, float]] = []
    non_numeric_count = 0
    for row_number, value in non_empty:
        parsed = _to_float(value)
        if parsed is None:
            non_numeric_count += 1
        else:
            numeric_by_row.append((row_number, parsed))
    if non_numeric_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX,
                message=f"{non_numeric_count} of {len(non_empty)} sampled value(s) are not numeric.",
                ambiguity=AMBIGUITY_INVALID,
                details={"non_numeric_count": non_numeric_count, "sample_size": len(non_empty)},
            )
        )

    backward_count = 0
    repeated_count = 0
    gap_count = 0
    for (_, prev), (_, curr) in zip(numeric_by_row, numeric_by_row[1:]):
        delta = curr - prev
        if delta < 0:
            backward_count += 1
        elif delta == 0:
            repeated_count += 1
        elif delta > 1:
            gap_count += 1
    if backward_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD,
                message=f"The sample index decreases at {backward_count} point(s) in the sampled rows.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"backward_count": backward_count},
            )
        )
    if repeated_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_REPEATED_SAMPLE_INDEX,
                message=f"{repeated_count} consecutive sampled row(s) repeat the same sample index.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"repeated_count": repeated_count},
            )
        )
    if gap_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_SAMPLE_INDEX_GAP,
                message=f"Possible sample-index gap at {gap_count} point(s) in the sampled rows.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"gap_count": gap_count},
            )
        )

    if requested_interval_seconds is not None:
        provenance = PROVENANCE_USER_SPECIFIED
        confidence = CONFIDENCE_HIGH
    else:
        provenance = PROVENANCE_INDEX_ONLY
        confidence = CONFIDENCE_UNKNOWN

    return TimeAxisDetectionResult(
        family=FAMILY_SAMPLE_INDEX, provenance=provenance, confidence=confidence,
        diagnostics=diagnostics, resolved_options={},
        resolved_unit=None, resolved_interval_seconds=requested_interval_seconds,
    )


def build_sample_index_preview(
    samples: list[tuple[int, tuple[Any, ...]]], *, resolved_interval_seconds: float | None, limit: int,
) -> list[tuple[int, tuple[Any, ...], str | None]]:
    """Bounded {index, relative-seconds} rows (§Q). When
    `resolved_interval_seconds` is `None` (index-only), every
    `interpreted` value is `None` -- NEVER a fabricated seconds column
    (task's own explicit "no fake seconds column" instruction). When a
    rate/interval IS known, `relative_seconds = (index - first_valid_
    index) * interval_seconds` (task §G's own recommended rule,
    generalized to interval form) -- `first_valid_index` is the first
    non-missing, numeric value in THIS bounded sample (never assumed to
    be `0`; also never a whole-dataset scan, consistent with this
    module's own bounded-sampling guarantee)."""
    rows: list[tuple[int, tuple[Any, ...], str | None]] = []
    first_value: float | None = None
    if resolved_interval_seconds is not None:
        for _, values in samples:
            candidate = _to_float(values[0]) if values and values[0] not in (None, "") else None
            if candidate is not None:
                first_value = candidate
                break

    for row_number, values in samples[:limit]:
        value = values[0] if values else None
        parsed = _to_float(value) if value not in (None, "") else None
        if resolved_interval_seconds is None or parsed is None or first_value is None:
            rows.append((row_number, values, None))
            continue
        relative_seconds = (parsed - first_value) * resolved_interval_seconds
        rows.append((row_number, values, f"{relative_seconds:.6f} s"))
    return rows
