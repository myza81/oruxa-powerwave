"""Deterministic absolute-time, elapsed-time, sample-index, and
repeated-timestamp-reconstruction interpreters (CSV/Excel ingestion
Slices 8A-8C, DEC-072). Authoritative design source:
docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md, each slice's own
task spec.

Implements five REAL (non-`manual`) entries the Slice 7 registry always
anticipated:

    `absolute_datetime`  -- one Time Axis column, a full timestamp (8A)
    `split_date_time`    -- two Time Axis columns, Date + Time combined (8A)
    `elapsed_numeric`    -- one Time Axis column, a relative numeric
                            value with an explicit, required unit (8B)
    `sample_index`       -- one Time Axis column, a plain ordinal
                            sequence, optionally paired with a
                            user-supplied sampling interval (8B)
    `repeated_timestamp_precision_loss` -- one Time Axis column whose
                            own displayed precision is coarser than its
                            true sampling cadence (repeated native
                            values); analyses bounded groups ("buckets")
                            of consecutive identical values and, when
                            confidence supports it, SUGGESTS (never
                            silently applies) an even sub-interval
                            reconstruction (8C)
    `time_of_day`        -- one Time Axis column, clock time with
                            genuinely NO date component -- a DISTINCT,
                            explicitly-selected interpreter (never an
                            automatic fallback); always resolves to
                            `FAMILY_PARTIAL`, never invents a date

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

**Slice 8C: detect, suggest, preview -- never silently apply.**
`detect_repeated_timestamp_precision_loss()` groups CONSECUTIVE rows
sharing an identical native timestamp string into "buckets" (never a
whole-dataset scan -- the SAME bounded sample every other interpreter
here already receives). A bucket size greater than 1 means the
source's own recorded precision is coarser than its true sampling
interval. When enough INTERIOR buckets (excluding the first and last,
which may be truncated by the sample window's own edges -- §E) show a
stable size, a per-sample interval is suggested by dividing each
bucket's own span-to-the-next-bucket by its own row count; the FIRST
bucket's own count is never used for this estimate either (it may
itself be truncated). This is always reported as a PENDING
`PROVENANCE_RECONSTRUCTED` suggestion -- `resolve_status()` routes it
to `review_required` until the caller explicitly sends `confirmed=true`
in the same request that also carries the resolved interval; nothing
in this module ever sets `confirmed` itself. A confidence too low to
trust ANY suggestion reports `cadence_not_reliable` instead (no
`resolved_interval_seconds` at all), which the caller must resolve via
either a user-supplied manual interval/rate (`provenance=
user_specified`, matching `sample_index`'s own precedent) or a fallback
to `sample_index` itself (a completely separate interpreter switch,
not something this module performs on the caller's behalf). Every
reconstructed value also states its own anchor assumption explicitly
(`resolved_options["anchor_offset_seconds"]`, default `0.0` -- "first
sample aligned to the displayed timestamp") -- this is disclosed as a
STATED ASSUMPTION, never presented as recovered original phase (task's
own "reconstruction, never recovery" framing, restated from
CSV_EXCEL_TIME_INTERPRETATION.md §7).

**Slice 8D: detect, normalize, structure, report -- never repair.**
`absolute_datetime`/`split_date_time` are the ONE place this module
never checked row-to-row timing QUALITY at all (Slice 8B's
`elapsed_numeric`/`sample_index` and Slice 8C's own bucket-cadence
analysis already did). `_analyze_time_sequence()` fills that gap with
ONE shared, family-agnostic analyzer, called only once a resolved
absolute/partial reading already exists (never for a still-ambiguous or
still-unparseable one, where no single trustworthy sequence exists to
walk). It never sorts, rewrites, or drops a row -- every finding is
purely diagnostic, added to the SAME `diagnostics` list every other
finding in this module already returns through.

A backward transition is classified into exactly one of three
DISTINCT conditions, most specific first: (1) for `partial` sources
only, a transition from within `_MIDNIGHT_ROLLOVER_WINDOW_SECONDS` of
the end of the day to within that same window of the start of the day
is `partial_midnight_rollover_suspected` -- a distinct, well-understood
condition, never generic corruption, and never a fabricated date or an
automatic day increment (§D); (2) otherwise, a backward jump whose own
magnitude is at least `_LARGE_GAP_MULTIPLIER` times the SMALLEST
positive consecutive delta observed elsewhere in the sample (the best
available proxy for "the expected local interval" without a separately
declared cadence -- §F) is `timestamp_reset_suspected` -- "looks like a
clock reset, not ordinary jitter," never claimed with certainty (§C);
(3) any other backward step is the plain `time_goes_backward` (§B). A
FORWARD step at least that same multiple of the reference is
`large_time_gap` (§E/§F) -- deliberately the SAME multiplier in both
directions, since a disproportionate jump is disproportionate
regardless of sign. Using the MINIMUM (not the mean or median) of the
positive deltas as the reference is a deliberate, simple, documented
choice: it is naturally robust to a single large outlier inflating its
own comparison point, without requiring a second, more elaborate
statistical pass (task's own "do not overengineer statistical
detection" instruction). A single, dataset-level `non_uniform_interval`
finding (mirroring `non_uniform_elapsed_interval`'s own once-per-call
shape, never once per transition) covers the softer case where the
remaining ordinary forward steps still vary beyond a moderate ±20%
tolerance of their own median -- looser than `elapsed_numeric`'s own
±1%, since absolute/partial timestamps are typically second-granularity
and naturally jitter by whole seconds even under an otherwise-uniform
real-world cadence.

Exact repeats (`delta == 0`) are deliberately NOT flagged here at all --
Slice 8C's own `repeated_timestamp_precision_loss` interpreter already
owns that condition in full (bucket detection, confidence, suggested
reconstruction); duplicating even a bare presence check here would be
exactly the "duplicate the detection algorithm" this slice's own task
explicitly says not to do. A user who cares about repeated timestamps
specifically is expected to switch interpreters, not read it off of
`absolute_datetime`/`split_date_time`'s own diagnostics.

Every new diagnostic here is `SEVERITY_WARNING`/`AMBIGUITY_UNAMBIGUOUS`
-- the exact combination `elapsed_time_goes_backward`/`sample_index_gap`
already use: surfaced via the existing `needs_attention` path once
present, but never blocking `confirmed=true` (only `AMBIGUITY_AMBIGUOUS`
does that) -- CSV_EXCEL_TIME_INTERPRETATION.md §11's own "flag; never
force a decision" table, not a "the user must choose" case. No new
`resolve_status()` rule was needed for this slice at all.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.domain.preparation_issue import SEVERITY_INFO, SEVERITY_WARNING, IssueLocation
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
    DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED,
    DIAGNOSTIC_CADENCE_NOT_RELIABLE,
    DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD,
    DIAGNOSTIC_INCONSISTENT_BUCKET_COUNT,
    DIAGNOSTIC_LARGE_TIME_GAP,
    DIAGNOSTIC_MISSING_DATETIME_VALUE,
    DIAGNOSTIC_MISSING_ELAPSED_UNIT,
    DIAGNOSTIC_MISSING_ELAPSED_VALUE,
    DIAGNOSTIC_MISSING_SAMPLE_INDEX,
    DIAGNOSTIC_MIXED_DATETIME_FORMAT,
    DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE,
    DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX,
    DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL,
    DIAGNOSTIC_NON_UNIFORM_INTERVAL,
    DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED,
    DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE,
    DIAGNOSTIC_PRECISION_LOSS_SUSPECTED,
    DIAGNOSTIC_REPEATED_ELAPSED_TIME,
    DIAGNOSTIC_REPEATED_SAMPLE_INDEX,
    DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED,
    DIAGNOSTIC_SAMPLE_INDEX_GAP,
    DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD,
    DIAGNOSTIC_TIME_GOES_BACKWARD,
    DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE,
    DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED,
    DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT,
    DIAGNOSTIC_UNPARSEABLE_DATETIME,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    PROVENANCE_RECONSTRUCTED,
    PROVENANCE_USER_SPECIFIED,
    UNIT_DAYS,
    UNIT_HOURS,
    UNIT_MICROSECONDS,
    UNIT_MILLISECONDS,
    UNIT_MINUTES,
    UNIT_NANOSECONDS,
    UNIT_SECONDS,
    UNIT_WEEKS,
    TimeAxisDetectionResult,
    TimeAxisDiagnostic,
)

#: Bounded, explicit time-of-day pattern table -- tried in this fixed
#: order (most-specific first) for both the single-column combined
#: date+time case and the split Date/Time interpreter's own Time
#: column. Never extended dynamically.
#:
#: Enhancement (minute/AM-PM-hour absolute time support, owner-approved
#: scope): `%H:%M` (24-hour minute resolution, e.g. "17:25") and
#: `%I %p`/`%I%p` (explicit-AM/PM hour-only, e.g. "1 PM"/"1pm") are
#: added. Neither can ever shadow a MORE precise existing pattern --
#: `strptime` requires a full-string match with no leftover characters
#: (verified directly: `strptime("17:25:30", "%H:%M")` raises
#: `ValueError: unconverted data remains: :30`; `strptime("1:00 pm",
#: "%I%p")` raises `ValueError` for the same reason), so a string that
#: also matches a seconds- or minute-bearing pattern elsewhere in this
#: table can never ALSO match one of these two new, strictly shorter
#: patterns. `%p` is matched case-insensitively by Python's own
#: `_strptime` implementation (verified: "1PM"/"1pm"/"1 PM"/"1 pm" all
#: parse identically) -- consistent with this table's existing `%p`
#: entries, not a new case-sensitivity policy. Deliberately NOT added:
#: a bare 24-hour hour-only pattern (`%H` alone) -- explicit task scope
#: boundary; a numeric-only hour with no AM/PM marker and no minutes is
#: judged too easily confused with an unrelated short numeric column
#: (e.g. `sample_index`-like data) to add without a separate policy
#: decision, unlike `%I%p`/`%I %p`, which require a literal "am"/"pm"
#: text marker no numeric-only column could ever produce.
_TIME_PATTERNS: tuple[str, ...] = (
    "%H:%M:%S.%f",
    "%H:%M:%S",
    "%H:%M",
    "%I:%M:%S.%f %p",
    "%I:%M:%S %p",
    "%I:%M %p",
    "%I %p",
    "%I%p",
)

#: Bounded, explicit date-only pattern table per candidate order. Both
#: `/` and `-` separators are tried (the task's own example list uses
#: both for the same `dmy` order) -- a genuinely different separator is
#: not treated as a genuinely different "order," only as a different
#: literal pattern to try under that order.
#:
#: UAT fix (2026-09-04): a 2-digit-year (`%y`) variant is added for
#: `dmy`/`mdy` ONLY -- a real owner-reported source ("3/6/26 18:04:00.000",
#: interpreted via Date + Time / split_date_time) previously fell all
#: the way to a generic `unparseable_datetime` failure, because
#: `_DATE_PATTERNS_BY_ORDER` had NO 2-digit-year candidate at all
#: (`%Y` correctly refuses to match a bare 2-digit token like "26" --
#: verified directly: `strptime("3/6/26", "%d/%m/%Y")` raises
#: `ValueError`). This was a missing-format-family gap, not an
#: ambiguity-detection bug and not a split-date-time-specific bug --
#: every candidate order genuinely had zero matches, so the case never
#: reached the existing ambiguity-by-elimination logic at all.
#:
#: Deliberately NOT added for `ymd`: a 2-digit-year-FIRST format is not
#: among any of the task's own reported examples (all are day-or-month-
#: first, year-LAST), and adding one would risk spurious full-matches
#: against unrelated short numeric sequences (e.g. a `sample_index`-like
#: column) that this module has no way to distinguish from a genuine
#: date -- exactly the "do not introduce unrestricted fuzzy parsing"
#: guardrail this module's own docstring already establishes.
#:
#: `%y`'s own 2-digit-to-4-digit century mapping goes through
#: `_parse_with_pattern()` below, not Python's native `%y` inference
#: directly -- see that function's own docstring for why.
_DATE_PATTERNS_BY_ORDER: dict[str, tuple[str, ...]] = {
    DATE_ORDER_DMY: ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"),
    DATE_ORDER_MDY: ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"),
    DATE_ORDER_YMD: ("%Y/%m/%d", "%Y-%m-%d"),
}

_KNOWN_ORDERS: tuple[str, ...] = (DATE_ORDER_DMY, DATE_ORDER_MDY, DATE_ORDER_YMD)

#: UAT fix (2026-09-04): plain-language labels for the diagnostic
#: MESSAGE only -- the frontend's own `WW_DATA_PREP_DATE_ORDER_LABELS`
#: (`frontend/index.html`) independently renders the actual radio-
#: button choices as format patterns ("DD/MM/YYYY") rather than these
#: words; both are just different renderings of the SAME `date_order`
#: value, never a second stored representation.
_ORDER_DISPLAY_LABELS: dict[str, str] = {
    DATE_ORDER_DMY: "Day/Month/Year",
    DATE_ORDER_MDY: "Month/Day/Year",
    DATE_ORDER_YMD: "Year/Month/Day",
}

#: UAT fix (2026-09-04): task section D.3 -- "where practical, show
#: representative failing rows rather than only a count." Bounded (never
#: unbounded) to keep a diagnostic's own `details` payload small,
#: mirroring every other "generous but not unlimited" bound already
#: established in this codebase (e.g. `app.domain.working_overlay.
#: MAX_OPERATION_HISTORY`).
_MAX_DIAGNOSTIC_EXAMPLES = 5

#: strptime directive -> friendly display token, purely for the
#: human-readable `detected_format` option value shown in the UI (§P) --
#: never itself used to parse anything; parsing always goes back through
#: the real strptime pattern.
_DISPLAY_TOKENS: dict[str, str] = {
    "%Y": "YYYY", "%y": "YY", "%m": "MM", "%d": "DD",
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


#: UAT fix (2026-09-04): the explicit, documented 2-digit-year century
#: rule for this application -- `00-69 -> 2000-2069`, `70-99 ->
#: 1970-1999`. Python's own native `%y` strptime inference is ALMOST
#: this rule (it pivots at 68/69, giving `00-68 -> 2000-2068`, `69-99 ->
#: 1969-1999` -- verified directly), differing from this application's
#: own preferred boundary at EXACTLY one value: a 2-digit year of `69`.
#: Rather than silently accept Python's own slightly different pivot
#: (which this module's own docstring explicitly warns against --
#: "do not silently invent a different century rule" cuts both ways:
#: it also means not silently DEFERRING to a convention the task never
#: asked for), `_parse_with_pattern()` below applies this ONE explicit
#: correction after Python's own `%y` parse: a resulting year of `1969`
#: (which `%y` only ever produces from a literal 2-digit token of `69`)
#: is corrected to `2069`. Every other 2-digit value (`00`-`68`,
#: `70`-`99`) already agrees between Python's own convention and this
#: rule, so this is the ONLY case that needs a post-hoc override.
def _apply_two_digit_year_century_rule(parsed: dt.datetime) -> dt.datetime:
    if parsed.year == 1969:
        return parsed.replace(year=2069)
    return parsed


def _parse_with_pattern(value: str, pattern: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.strptime(value.strip(), pattern)
    except ValueError:
        return None
    if "%y" in pattern:
        return _apply_two_digit_year_century_rule(parsed)
    return parsed


def _is_time_only(value: str) -> bool:
    stripped = value.strip()
    return any(_parse_with_pattern(stripped, pattern) is not None for pattern in _TIME_PATTERNS)


def _parse_time_only(value: str) -> dt.time | None:
    """Same bounded `_TIME_PATTERNS` table `_is_time_only` already
    checks against, but returning the actual parsed `time` (Slice 8C
    needs the value itself, not just a yes/no)."""
    stripped = value.strip()
    for pattern in _TIME_PATTERNS:
        parsed = _parse_with_pattern(stripped, pattern)
        if parsed is not None:
            return parsed.time()
    return None


# ---- Slice 8D: shared timing-irregularity analysis (§B-§F) -----------

#: A transition (forward OR backward) is "large"/reset-scale when its
#: own magnitude is at least this many times the smallest positive
#: consecutive delta observed elsewhere in the bounded sample -- see
#: this module's own docstring for why the MINIMUM (not mean/median) is
#: used as the reference, and why one shared multiplier covers both
#: `large_time_gap` and `timestamp_reset_suspected`.
_LARGE_GAP_MULTIPLIER = 5.0

#: How close to the day boundary (on both sides, in seconds) a
#: `partial`-family backward transition must land to be treated as a
#: midnight-rollover CANDIDATE rather than an ordinary/reset backward
#: step (§D).
_MIDNIGHT_ROLLOVER_WINDOW_SECONDS = 2.0

#: Relative tolerance for the softer, dataset-level `non_uniform_interval`
#: finding -- looser than `elapsed_numeric`'s own ±1% (see this module's
#: own docstring for why).
_NON_UNIFORM_INTERVAL_TOLERANCE = 0.2


def _seconds_sequence_from_datetimes(pairs: list[tuple[int, dt.datetime | None]]) -> list[tuple[int, float]]:
    """(Slice 8D) `absolute`-family rows -> `(row_number, seconds)` pairs,
    relative to the FIRST successfully-parsed row's own value (only the
    relative spacing ever matters to `_analyze_time_sequence`, so an
    arbitrary but stable zero-point avoids any `datetime.timestamp()`
    timezone/epoch concern). Rows that failed to parse are silently
    excluded -- they already have their own missing/unparseable
    diagnostic elsewhere; this sequence only ever walks rows it can
    actually compare."""
    resolved = [(row_number, value) for row_number, value in pairs if value is not None]
    if not resolved:
        return []
    base = resolved[0][1]
    return [(row_number, (value - base).total_seconds()) for row_number, value in resolved]


def _seconds_sequence_from_times(pairs: list[tuple[int, dt.time | None]]) -> list[tuple[int, float]]:
    """(Slice 8D) `partial`-family counterpart of
    `_seconds_sequence_from_datetimes` -- seconds-from-midnight via the
    SAME `_seconds_from_midnight` helper Slice 8C's own bucket analysis
    already uses, never a second conversion."""
    return [(row_number, _seconds_from_midnight(value)) for row_number, value in pairs if value is not None]


def _analyze_time_sequence(ordered_seconds: list[tuple[int, float]], *, family: str) -> list[TimeAxisDiagnostic]:
    """(Slice 8D, §B-§F) Shared, family-agnostic row-to-row timing
    analysis over an already-RESOLVED sequence of `(row_number, seconds)`
    pairs, in ORIGINAL row order -- never sorted, never used to repair
    anything (Principle 3). Only ever called once `absolute_datetime`/
    `split_date_time` already has a resolved, non-ambiguous reading --
    see this module's own docstring for the full backward/reset/
    rollover/gap/non-uniform classification rules and their rationale.
    """
    diagnostics: list[TimeAxisDiagnostic] = []
    if len(ordered_seconds) < 2:
        return diagnostics

    deltas = [
        (ordered_seconds[i][0], ordered_seconds[i + 1][0], ordered_seconds[i + 1][1] - ordered_seconds[i][1])
        for i in range(len(ordered_seconds) - 1)
    ]
    positive_deltas = [delta for _, _, delta in deltas if delta > 0]
    reference = min(positive_deltas) if positive_deltas else None

    backward_rows: list[int] = []
    reset_rows: list[int] = []
    rollover_rows: list[int] = []
    gap_rows: list[int] = []
    normal_forward_deltas: list[float] = []

    for index, (_prev_row, curr_row, delta) in enumerate(deltas):
        if delta == 0:
            # Exact repeats are Slice 8C's own condition -- see this
            # module's own docstring for why this is deliberately never
            # flagged here.
            continue
        if delta < 0:
            prev_seconds = ordered_seconds[index][1]
            curr_seconds = ordered_seconds[index + 1][1]
            if (
                family == FAMILY_PARTIAL
                and prev_seconds >= 86400 - _MIDNIGHT_ROLLOVER_WINDOW_SECONDS
                and curr_seconds <= _MIDNIGHT_ROLLOVER_WINDOW_SECONDS
            ):
                rollover_rows.append(curr_row)
            elif reference is not None and abs(delta) >= reference * _LARGE_GAP_MULTIPLIER:
                reset_rows.append(curr_row)
            else:
                backward_rows.append(curr_row)
        elif reference is not None and delta >= reference * _LARGE_GAP_MULTIPLIER:
            gap_rows.append(curr_row)
        else:
            normal_forward_deltas.append(delta)

    if rollover_rows:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED,
                message=(
                    f"Time wraps from late in the day to early in the day near row {rollover_rows[0]} -- "
                    "consistent with an ordinary midnight rollover in a time-of-day reading."
                ),
                suggested_action="No date is invented automatically -- this remains a time-of-day reading only.",
                location=IssueLocation(row_number=rollover_rows[0]),
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"rollover_count": len(rollover_rows)},
            )
        )
    if reset_rows:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED,
                message=(
                    f"A sharp backward jump near row {reset_rows[0]} looks like a possible clock reset, "
                    "not ordinary backward jitter."
                ),
                suggested_action="Review the source recording for a restart or file concatenation around this point.",
                location=IssueLocation(row_number=reset_rows[0]),
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"reset_count": len(reset_rows)},
            )
        )
    if backward_rows:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_TIME_GOES_BACKWARD,
                message=f"Interpreted time decreases at {len(backward_rows)} point(s) in the sampled rows, near row {backward_rows[0]}.",
                location=IssueLocation(row_number=backward_rows[0]),
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"backward_count": len(backward_rows)},
            )
        )
    if gap_rows:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_LARGE_TIME_GAP,
                message=f"A timing gap near row {gap_rows[0]} is much larger than the typical interval in the sampled rows.",
                location=IssueLocation(row_number=gap_rows[0]),
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"gap_count": len(gap_rows)},
            )
        )
    if len(normal_forward_deltas) >= 2:
        median_normal = statistics.median(normal_forward_deltas)
        tolerance = max(1e-9, median_normal * _NON_UNIFORM_INTERVAL_TOLERANCE)
        if any(abs(d - median_normal) > tolerance for d in normal_forward_deltas):
            diagnostics.append(
                TimeAxisDiagnostic(
                    severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_NON_UNIFORM_INTERVAL,
                    message="The spacing between consecutive interpreted timestamps is not uniform across the sampled rows.",
                    ambiguity=AMBIGUITY_UNAMBIGUOUS,
                )
            )
    return diagnostics


def _sequence_diagnostics_for_datetime_column(
    non_empty: list[tuple[int, str]], *, family: str, date_order: str | None,
) -> list[TimeAxisDiagnostic]:
    """(Slice 8D) Builds the resolved per-row sequence for an ALREADY-
    resolved `absolute_datetime` reading and runs `_analyze_time_sequence`
    over it -- shared by every success branch of `detect_absolute_datetime`
    below (never called for a still-ambiguous/mixed/unparseable reading,
    where no single resolved sequence exists to walk safely). Reuses
    `parse_absolute_datetime()` verbatim for the `absolute` case -- the
    EXACT same parse path `build_absolute_datetime_preview` already
    uses, never a second, potentially-divergent parsing implementation."""
    if family == FAMILY_PARTIAL:
        ordered = _seconds_sequence_from_times([(rn, _parse_time_only(v)) for rn, v in non_empty])
        return _analyze_time_sequence(ordered, family=FAMILY_PARTIAL)
    if family == FAMILY_ABSOLUTE and date_order and date_order != DATE_ORDER_AUTO:
        ordered = _seconds_sequence_from_datetimes(
            [(rn, parse_absolute_datetime(v, date_order=date_order)) for rn, v in non_empty]
        )
        return _analyze_time_sequence(ordered, family=FAMILY_ABSOLUTE)
    return []


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


def _best_combined_match_for_order(values: list[str], order: str) -> _FormatMatch | None:
    """2026-09-05 fix: a TOLERANT full-match check for `order`, tried
    only after `_best_match_for_order()`'s own exhaustive single-fixed-
    pattern scan (below) fails to find one combined `strptime` pattern
    that explains the WHOLE sample. That scan requires one literal
    pattern like `"%d/%m/%Y %H:%M:%S.%f"` to match every row, so a
    column mixing "31/08/2026 18:04:00" (no fraction) with
    "31/08/2026 18:04:00.020000" (fraction) has NO single combined
    pattern that matches both -- the exact same structural weakness the
    2026-09-05 `detect_split_date_time()` fix already closed for the
    Date + Time (2 columns) interpreter, now closed here too for the
    single-column combined case.

    Splits each value on its FIRST space into `(date_part, time_part)`
    -- every `_DATE_PATTERNS_BY_ORDER` entry is a single space-free
    token, and every `_TIME_PATTERNS` entry (including the AM/PM
    variants, which contain their OWN internal space before `%p`) is
    always the LAST token block, so splitting on the first space alone
    always cleanly separates the two regardless of which time pattern
    a row happens to use. The DATE portion must match ONE CONSISTENT
    date pattern for `order` across the WHOLE sample (preserving the
    exact same separator-consistency guarantee date-order elimination
    already relies on -- this never lets two different date spellings
    coexist and still call it unambiguous); the TIME portion is checked
    per row via the SAME `_is_time_only()` tolerance (any pattern in
    `_TIME_PATTERNS`, independently per row) the split Date + Time fix
    and the Time of Day interpreter already use -- never a second,
    parallel time parser. Returns `None` (never a partial match) when
    no date pattern explains every row's date portion, or when any
    row has no space at all (a bare date-only value, already covered by
    `_best_match_for_order()`'s own separate date-only candidate set)."""
    if not values or not all(" " in v for v in values):
        return None
    parts = [v.partition(" ") for v in values]
    for date_pattern in _DATE_PATTERNS_BY_ORDER[order]:
        if all(
            _parse_with_pattern(date_part, date_pattern) is not None and _is_time_only(time_part)
            for date_part, _sep, time_part in parts
        ):
            display_pattern = f"{date_pattern} %H:%M:%S.%f"
            return _FormatMatch(pattern=display_pattern, match_count=len(values), total_count=len(values))
    return None


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
    # 2026-09-05 fix: no single FIXED pattern explains the whole sample,
    # but the sample may still be a fully valid, consistently-ordered
    # column whose fractional-second precision simply varies row to
    # row -- try the tolerant per-row combined match (see
    # `_best_combined_match_for_order()`'s own docstring) before falling
    # back to reporting a partial/mixed/unparseable finding.
    tolerant = _best_combined_match_for_order(values, order)
    if tolerant is not None:
        return tolerant
    return max(scored, key=lambda m: m.match_count)


def _failing_examples(
    non_empty: list[tuple[int, str]], *, pattern: str, limit: int = _MAX_DIAGNOSTIC_EXAMPLES,
) -> list[dict[str, Any]]:
    """UAT fix (2026-09-04), task section D.3: a handful of REAL
    `(row_number, value)` pairs that do not match `pattern` (the
    best-explaining candidate a `mixed`/`unparseable` diagnostic is
    already reporting a match RATE for) -- so the resulting UI can show
    concrete failing rows, not only a count. Bounded to `limit`; never a
    second, separate re-scan beyond this one pass over the already-
    bounded sample."""
    examples: list[dict[str, Any]] = []
    for row_number, value in non_empty:
        if _parse_with_pattern(value, pattern) is None:
            examples.append({"row_number": row_number, "value": value})
            if len(examples) >= limit:
                break
    return examples


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
    include_sequence_diagnostics: bool = True,
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

    `include_sequence_diagnostics` (Slice 8D) is `False` ONLY when
    `detect_split_date_time()` reuses this function for its own DATE-only
    sub-detection below -- a bare date column's own value sequence
    (always midnight-anchored, one entry per calendar day) is not a
    meaningful timing signal on its own; `detect_split_date_time()` runs
    its OWN `_analyze_time_sequence()` pass over the COMBINED date+time
    values instead, so this flag exists purely to avoid running (and
    duplicating) the wrong sequence's own analysis, never to disable it
    for a genuine single-column `absolute_datetime` caller.
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
        if include_sequence_diagnostics:
            diagnostics.extend(_sequence_diagnostics_for_datetime_column(non_empty, family=FAMILY_PARTIAL, date_order=None))
        return TimeAxisDetectionResult(
            family=FAMILY_PARTIAL, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_HIGH,
            diagnostics=diagnostics, resolved_options={},
        )

    iso_match = _score_pattern(raw_values, "iso8601", parser=lambda v, _p: _parse_iso(v))
    if iso_match.is_full_match:
        if include_sequence_diagnostics:
            diagnostics.extend(_sequence_diagnostics_for_datetime_column(non_empty, family=FAMILY_ABSOLUTE, date_order=DATE_ORDER_YMD))
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_HIGH,
            diagnostics=diagnostics,
            resolved_options={"date_order": DATE_ORDER_YMD, "detected_format": "ISO-8601"},
        )

    per_order_match = {order: _best_match_for_order(raw_values, order) for order in _KNOWN_ORDERS}
    candidate_orders = sorted(order for order, m in per_order_match.items() if m.is_full_match)

    if len(candidate_orders) == 1:
        order = candidate_orders[0]
        if include_sequence_diagnostics:
            diagnostics.extend(_sequence_diagnostics_for_datetime_column(non_empty, family=FAMILY_ABSOLUTE, date_order=order))
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
            if include_sequence_diagnostics:
                diagnostics.extend(_sequence_diagnostics_for_datetime_column(non_empty, family=FAMILY_ABSOLUTE, date_order=requested_order))
            return TimeAxisDetectionResult(
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_HIGH,
                diagnostics=diagnostics,
                resolved_options={"date_order": requested_order, "detected_format": _display_format(match.pattern)},
            )
        # UAT fix (2026-09-04), task section G: specific, actionable
        # wording -- "needs confirmation," not a generic parse failure --
        # since a viable interpretation genuinely exists for every
        # sampled value under 2+ orders; only the CHOICE between them is
        # unresolved. Names one real example value so the message reads
        # concretely against the engineer's own data, not abstractly.
        order_labels = " or ".join(_ORDER_DISPLAY_LABELS.get(o, o) for o in candidate_orders)
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
                message=(
                    f"Date format needs confirmation. The value \"{raw_values[0]}\" can be interpreted as "
                    f"{order_labels}. Choose the intended date order below."
                ),
                suggested_action="Choose the correct date order to confirm this Time Axis configuration.",
                ambiguity=AMBIGUITY_AMBIGUOUS,
                details={"candidate_orders": candidate_orders, "example_value": raw_values[0]},
            )
        )
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_LOW,
            diagnostics=diagnostics, resolved_options={"date_order": DATE_ORDER_AUTO},
        )

    # No order, and no ISO reading, fully explains the sample -- report
    # the single best-explaining candidate (by match count) as a
    # mixed/unparseable finding, never silently normalized (task §L).
    # UAT fix (2026-09-04), task section G/D.3: this generic failure
    # wording is now reserved for the case it actually describes --
    # genuinely no supported controlled format explains the sample
    # (never reached for a viable-but-ambiguous case any more, since
    # that is handled by the branch above) -- and names concrete
    # examples rather than only a count.
    best_order, best_match = max(per_order_match.items(), key=lambda kv: kv[1].match_count)
    code = DIAGNOSTIC_MIXED_DATETIME_FORMAT if best_match.match_count > 0 else DIAGNOSTIC_UNPARSEABLE_DATETIME
    unmatched = best_match.total_count - best_match.match_count
    examples = _failing_examples(non_empty, pattern=best_match.pattern)
    if code == DIAGNOSTIC_UNPARSEABLE_DATETIME:
        message = (
            f"{unmatched} of {best_match.total_count} sampled date/time value(s) could not be interpreted "
            "using the supported formats. Review the examples below or choose a different interpreter."
        )
    else:
        message = (
            f"{unmatched} of {best_match.total_count} sampled value(s) do not match one consistent format -- "
            "the column may mix formats or contain invalid entries. Review the examples below."
        )
    diagnostics.append(
        TimeAxisDiagnostic(
            severity_hint=SEVERITY_WARNING,
            code=code,
            message=message,
            suggested_action="Review the sampled values -- the column may mix formats or contain invalid entries.",
            ambiguity=AMBIGUITY_INVALID,
            details={
                "matched": best_match.match_count, "sample_size": best_match.total_count,
                "best_candidate_order": best_order, "examples": examples,
            },
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

    Slice 8D: row-to-row timing-quality analysis (backward/reset/gap/
    non-uniform) runs over the COMBINED date+time value per row, never
    the date-only sequence `detect_absolute_datetime()` itself would
    otherwise analyze -- see that function's own `include_sequence_
    diagnostics` parameter docstring for why it is disabled here.
    """
    date_result = detect_absolute_datetime(
        date_values_by_row, requested_options=requested_options, sample_size_label="date column",
        include_sequence_diagnostics=False,
    )

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
        # UAT fix (2026-09-05): a Time column is a single semantic
        # time-of-day value with OPTIONAL, VARIABLE-precision fractional
        # seconds -- not one fixed textual format every sampled row must
        # share. The previous check picked the single `_TIME_PATTERNS`
        # entry with the highest whole-sample match count (`_score_pattern`
        # over ALL rows) and only accepted it as a full match; a column
        # mixing "18:04:00" (no fraction) with "18:04:00.020000" (fraction)
        # has NO single pattern that matches every row, so the best
        # candidate (`%H:%M:%S.%f`) reported the fraction-less rows as
        # unparseable even though `_is_time_only()` -- the SAME per-value,
        # any-pattern-in-the-table check `detect_absolute_datetime()`
        # already uses to recognize a bare time-of-day column -- happily
        # accepts every one of them. Checking each value independently
        # against the whole table (rather than requiring one pattern to
        # explain the whole sample) also matches how `_combine_date_and_time()`
        # already parses each row for real (tries every pattern per value,
        # first match wins) -- detection and parsing must not disagree.
        failing_times = [(row_number, value) for row_number, value in non_empty_times if not _is_time_only(value)]
        if failing_times:
            matched = len(time_values) - len(failing_times)
            code = DIAGNOSTIC_MIXED_DATETIME_FORMAT if matched > 0 else DIAGNOSTIC_UNPARSEABLE_DATETIME
            # UAT fix (2026-09-04), task D.3: concrete failing examples,
            # not only a count -- same treatment as the DATE column's
            # own unparseable/mixed branch above.
            time_examples = [{"row_number": row_number, "value": value} for row_number, value in failing_times[:_MAX_DIAGNOSTIC_EXAMPLES]]
            diagnostics.append(
                TimeAxisDiagnostic(
                    severity_hint=SEVERITY_WARNING,
                    code=code,
                    message=f"{len(failing_times)} of {len(time_values)} sampled Time column value(s) could not be parsed as a time-of-day.",
                    suggested_action="Review the examples below -- the Time column may mix formats or contain invalid entries.",
                    ambiguity=AMBIGUITY_INVALID,
                    details={"matched": matched, "sample_size": len(time_values), "examples": time_examples},
                )
            )

    # Slice 8D: only run the combined-sequence analysis once the DATE
    # column's own order is genuinely resolved (never for an unresolved
    # ambiguity, an unparseable/mixed date column, or a bare time-only
    # date column) -- exactly the same "only a trustworthy resolved
    # reading gets walked" guardrail `detect_absolute_datetime()` itself
    # applies to its own single-column case.
    resolved_date_order = date_result.resolved_options.get("date_order")
    has_blocking_date_issue = any(
        d.code in (DIAGNOSTIC_AMBIGUOUS_DATE_ORDER, DIAGNOSTIC_MIXED_DATETIME_FORMAT, DIAGNOSTIC_UNPARSEABLE_DATETIME)
        for d in date_result.diagnostics
    )
    if (
        date_result.family == FAMILY_ABSOLUTE
        and resolved_date_order
        and resolved_date_order != DATE_ORDER_AUTO
        and not has_blocking_date_issue
    ):
        combined_pairs: list[tuple[int, dt.datetime | None]] = []
        for (row_number, date_value), (_, time_value) in zip(date_values_by_row, time_values_by_row):
            if date_value in (None, "") or time_value in (None, ""):
                continue
            combined_pairs.append(
                (row_number, _combine_date_and_time(str(date_value), str(time_value), date_order=resolved_date_order))
            )
        ordered = _seconds_sequence_from_datetimes(combined_pairs)
        diagnostics.extend(_analyze_time_sequence(ordered, family=FAMILY_ABSOLUTE))

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
    value(s) verbatim, `interpreted` is the resulting ISO-8601 string
    (`absolute` family) or an `"HH:MM:SS.ffffff"` string (`partial`
    family, Slice 10 fix -- see below), or `None` for a row that failed
    to parse under the resolved format (never dropped -- see
    `app.domain.time_axis.TimeAxisPreviewRow`'s own docstring).

    Slice 10 (DEC-072) fix: a bare time-of-day value never parses under
    ANY `date_order` (it has no date component at all) -- prior to this
    fix, every row of a genuinely `partial`-family column produced
    `interpreted=None` unconditionally, even though `detect_absolute_
    datetime()`'s own time-only branch correctly reports `family=
    FAMILY_PARTIAL` for exactly this data. This was a real, previously
    unexercised gap (no earlier slice's own preview needed a partial-
    family value to be non-`None`) -- fixed here by falling back to
    `_parse_time_only()`/`_format_seconds_from_midnight()`, the EXACT
    same helpers Slice 8C's own `build_repeated_timestamp_preview()`
    already uses for its own partial-family case, so there is still
    only one time-of-day formatting convention in this module, not two.
    """
    date_order = resolved_options.get("date_order", DATE_ORDER_AUTO)
    rows = []
    for row_number, values in samples[:limit]:
        value = values[0]
        if value in (None, ""):
            rows.append((row_number, values, None))
            continue
        text = str(value)
        parsed = parse_absolute_datetime(text, date_order=date_order) if date_order != DATE_ORDER_AUTO else _parse_iso(text)
        if parsed is not None:
            rows.append((row_number, values, parsed.isoformat()))
            continue
        time_only = _parse_time_only(text)
        interpreted = _format_seconds_from_midnight(_seconds_from_midnight(time_only)) if time_only is not None else None
        rows.append((row_number, values, interpreted))
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


# ---- Time of Day: explicit clock-time-only interpreter ----------------


def detect_time_of_day(
    raw_values_by_row: list[tuple[int, Any]],
    *,
    requested_options: dict[str, Any],
) -> TimeAxisDetectionResult:
    """Time of Day -- single-column detection for a value that carries
    clock time but genuinely NO date component (`18:04:00`, optionally
    with variable-precision fractional seconds). This is a DISTINCT,
    explicitly-selected interpreter, never an automatic fallback:
    `detect_absolute_datetime()`'s own pre-existing "every sampled value
    is a time-of-day" branch already reports `FAMILY_PARTIAL` when an
    Absolute Datetime reading happens to see only clock values -- that
    existing behavior is completely UNCHANGED by this interpreter's
    existence (an engineer who explicitly picks Absolute Datetime and
    supplies only clock values still lands there, still incomplete,
    exactly as before). This interpreter exists so an engineer who KNOWS
    their data has no date can say so directly, rather than reaching the
    same family only as an incidental byproduct of a different
    interpreter's own diagnostic.

    Reuses the EXACT SAME per-value, any-pattern-in-`_TIME_PATTERNS`
    tolerance `_is_time_only()`/`_parse_time_only()` already provide --
    mixed fractional-second precision within one column is valid, per
    the same policy the 2026-09-05 `detect_split_date_time()` fix
    established (never a second, parallel time-of-day parser).

    `family` is always `FAMILY_PARTIAL`, never promoted to
    `FAMILY_ABSOLUTE` regardless of confidence -- no date is ever
    invented, no sentinel date is ever attached. Row-to-row timing-
    quality diagnostics (backward/gap/midnight-rollover) reuse the SAME
    `_sequence_diagnostics_for_datetime_column()` Slice 8D already built
    for the single-column `absolute_datetime` interpreter's own bare-
    time-of-day branch -- one shared implementation, not a second one."""
    diagnostics: list[TimeAxisDiagnostic] = []
    total = len(raw_values_by_row)
    non_empty = [(row_number, str(value)) for row_number, value in raw_values_by_row if value not in (None, "")]
    missing_count = total - len(non_empty)
    if missing_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=DIAGNOSTIC_MISSING_DATETIME_VALUE,
                message=f"{missing_count} of {total} sampled row(s) have no value in this Time Axis column.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS,
                details={"missing_count": missing_count, "sample_size": total},
            )
        )
    if not non_empty:
        return TimeAxisDetectionResult(
            family=FAMILY_PARTIAL, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_UNKNOWN,
            diagnostics=diagnostics, resolved_options={},
        )

    failing = [(row_number, value) for row_number, value in non_empty if not _is_time_only(value)]
    if failing:
        matched = len(non_empty) - len(failing)
        code = DIAGNOSTIC_MIXED_DATETIME_FORMAT if matched > 0 else DIAGNOSTIC_UNPARSEABLE_DATETIME
        examples = [{"row_number": row_number, "value": value} for row_number, value in failing[:_MAX_DIAGNOSTIC_EXAMPLES]]
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING,
                code=code,
                message=f"{len(failing)} of {len(non_empty)} sampled Time of Day value(s) could not be parsed as a time-of-day.",
                suggested_action="Review the examples below -- the column may mix formats or contain invalid entries.",
                ambiguity=AMBIGUITY_INVALID,
                details={"matched": matched, "sample_size": len(non_empty), "examples": examples},
            )
        )
        confidence = _confidence_for_partial(_FormatMatch(pattern="time_of_day", match_count=matched, total_count=len(non_empty)))
    else:
        diagnostics.extend(_sequence_diagnostics_for_datetime_column(non_empty, family=FAMILY_PARTIAL, date_order=None))
        confidence = CONFIDENCE_HIGH

    return TimeAxisDetectionResult(
        family=FAMILY_PARTIAL, provenance=PROVENANCE_NATIVE, confidence=confidence,
        diagnostics=diagnostics, resolved_options={},
    )


def build_time_of_day_preview(
    samples: list[tuple[int, tuple[Any, ...]]], *, resolved_options: dict[str, Any], limit: int,
) -> list[tuple[int, tuple[Any, ...], str | None]]:
    """Time of Day counterpart of `build_absolute_datetime_preview` --
    `values[0]` is the single time-only cell. Formats a successfully-
    parsed value as `"%H:%M:%S.%f"`, matching `app.services.
    time_axis_normalization.parse_native_time_value()`'s own expected
    `FAMILY_PARTIAL` re-parse format -- the same `interpreted` string
    convention every other family's own preview builder already follows,
    never a second, divergent shape."""
    rows = []
    for row_number, values in samples[:limit]:
        value = values[0] if values else None
        if value in (None, ""):
            rows.append((row_number, values, None))
            continue
        parsed = _parse_time_only(str(value))
        interpreted = parsed.strftime("%H:%M:%S.%f") if parsed is not None else None
        rows.append((row_number, values, interpreted))
    return rows


# ---- Slice 8B: elapsed numeric time + sample index -------------------

#: Canonical-seconds conversion factor per known unit (§B) -- the ONLY
#: place a unit-to-seconds ratio is defined; `interval_seconds`/derived
#: preview values are always computed through this table, never a second
#: ad-hoc conversion elsewhere.
#: Enhancement (fixed-duration elapsed units): minutes/hours/days/weeks
#: are exact, fixed-duration multipliers -- no calendar involved (a
#: "day" here is always exactly 86400 seconds, never a calendar day
#: that might contain a DST transition; this interpreter has no
#: absolute anchor date to make DST meaningful in the first place, see
#: `app.domain.time_axis.UNIT_MINUTES`'s own docstring for why months/
#: years are deliberately excluded from this same table).
_ELAPSED_UNIT_SECONDS_FACTOR: dict[str, float] = {
    UNIT_SECONDS: 1.0,
    UNIT_MILLISECONDS: 1e-3,
    UNIT_MICROSECONDS: 1e-6,
    UNIT_NANOSECONDS: 1e-9,
    UNIT_MINUTES: 60.0,
    UNIT_HOURS: 3600.0,
    UNIT_DAYS: 86400.0,
    UNIT_WEEKS: 604800.0,
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
                message="This column's values could mean nanoseconds, microseconds, milliseconds, seconds, minutes, hours, days, or weeks -- a unit is required.",
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


# ---- Slice 8C: repeated timestamp / precision-loss reconstruction ----


@dataclass(slots=True, frozen=True)
class _BucketAnalysis:
    """Internal, shared result of grouping+parsing one column's own
    bounded sample -- used identically by `detect_repeated_timestamp_
    precision_loss()` (classification) and
    `build_repeated_timestamp_preview()` (formatting), so there is
    exactly one bucket-grouping/parsing implementation, never two that
    could disagree about which rows belong to which bucket.

    `buckets` is `[(native_value, [row_number, ...]), ...]` in
    ENCOUNTER order -- consecutive rows sharing the exact same native
    string form one bucket; the SAME string appearing again later
    (non-consecutively) starts a NEW bucket, matching
    CSV_EXCEL_TIME_INTERPRETATION.md §7's own "group CONSECUTIVE rows"
    definition. `seconds_from_first` is one float per bucket -- the
    bucket's own parsed time value minus the FIRST bucket's own parsed
    time value -- computed identically whether the underlying family is
    `absolute` (real calendar arithmetic) or `partial` (bare seconds-
    from-midnight arithmetic), so every statistic downstream (spans,
    confidence, suggested interval) is family-agnostic. `anchor_reference`
    is bucket 0's own parsed value in its NATIVE representation
    (`datetime` for absolute, `float` seconds-from-midnight for
    partial) -- needed only for FORMATTING a reconstructed value back
    into a display string, never for the statistics themselves."""

    family: str | None
    ambiguous_date_order: bool
    candidate_orders: list[str]
    unparseable: bool
    buckets: list[tuple[str, list[int]]]
    seconds_from_first: list[float]
    anchor_reference: Any
    missing_count: int
    date_order_used: str | None


def _seconds_from_midnight(value: dt.time) -> float:
    return value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1_000_000


def _analyze_buckets(raw_values_by_row: list[tuple[int, Any]], *, requested_options: dict[str, Any]) -> _BucketAnalysis:
    """Bounded, single-pass grouping + deterministic parsing -- never
    scans anything beyond the already-bounded `raw_values_by_row` this
    function receives (see this module's own docstring). Tries, in
    order: bare time-of-day (`partial`), ISO-8601 (`absolute`,
    unambiguous), then `dmy`/`mdy`/`ymd` elimination among the DISTINCT
    bucket values only (a naturally smaller, already-deduplicated-by-
    run set) -- the exact same machinery `detect_absolute_datetime`
    uses, never a second parsing implementation."""
    total = len(raw_values_by_row)
    non_empty = [(row_number, str(value)) for row_number, value in raw_values_by_row if value not in (None, "")]
    missing_count = total - len(non_empty)

    def _give_up(family: str | None = None, *, unparseable: bool = True, date_order_used: str | None = None) -> _BucketAnalysis:
        return _BucketAnalysis(
            family=family, ambiguous_date_order=False, candidate_orders=[], unparseable=unparseable,
            buckets=buckets, seconds_from_first=[], anchor_reference=None,
            missing_count=missing_count, date_order_used=date_order_used,
        )

    buckets: list[tuple[str, list[int]]] = []
    for row_number, value in non_empty:
        if buckets and buckets[-1][0] == value:
            buckets[-1][1].append(row_number)
        else:
            buckets.append((value, [row_number]))

    if not buckets:
        return _give_up()

    distinct_values = [value for value, _ in buckets]

    if all(_is_time_only(v) for v in distinct_values):
        parsed_times = [_parse_time_only(v) for v in distinct_values]
        if any(p is None for p in parsed_times):
            return _give_up()
        seconds = [_seconds_from_midnight(p) for p in parsed_times]
        return _BucketAnalysis(
            family=FAMILY_PARTIAL, ambiguous_date_order=False, candidate_orders=[], unparseable=False,
            buckets=buckets, seconds_from_first=[s - seconds[0] for s in seconds], anchor_reference=seconds[0],
            missing_count=missing_count, date_order_used=None,
        )

    iso_parsed = [_parse_iso(v) for v in distinct_values]
    if all(p is not None for p in iso_parsed):
        base = iso_parsed[0]
        return _BucketAnalysis(
            family=FAMILY_ABSOLUTE, ambiguous_date_order=False, candidate_orders=[], unparseable=False,
            buckets=buckets, seconds_from_first=[(p - base).total_seconds() for p in iso_parsed], anchor_reference=base,
            missing_count=missing_count, date_order_used=DATE_ORDER_YMD,
        )

    per_order_match = {order: _best_match_for_order(distinct_values, order) for order in _KNOWN_ORDERS}
    candidate_orders = sorted(order for order, m in per_order_match.items() if m.is_full_match)
    requested_order = requested_options.get("date_order")

    resolved_order: str | None = None
    if len(candidate_orders) == 1:
        resolved_order = candidate_orders[0]
    elif len(candidate_orders) >= 2:
        if requested_order in candidate_orders:
            resolved_order = requested_order
        else:
            return _BucketAnalysis(
                family=FAMILY_ABSOLUTE, ambiguous_date_order=True, candidate_orders=candidate_orders, unparseable=False,
                buckets=buckets, seconds_from_first=[], anchor_reference=None,
                missing_count=missing_count, date_order_used=None,
            )

    if resolved_order is None:
        return _give_up(family=FAMILY_ABSOLUTE)

    parsed = [parse_absolute_datetime(v, date_order=resolved_order) for v in distinct_values]
    if any(p is None for p in parsed):
        return _give_up(family=FAMILY_ABSOLUTE, date_order_used=resolved_order)

    base = parsed[0]
    return _BucketAnalysis(
        family=FAMILY_ABSOLUTE, ambiguous_date_order=False, candidate_orders=[], unparseable=False,
        buckets=buckets, seconds_from_first=[(p - base).total_seconds() for p in parsed], anchor_reference=base,
        missing_count=missing_count, date_order_used=resolved_order,
    )


def _bucket_confidence(bucket_sizes: list[int], interior_sizes: list[int]) -> str:
    """The exact, documented evidence rule (task §F, deliberately not
    overengineered):

    - HIGH: at least 2 full INTERIOR buckets (excluding the first and
      last, which may be truncated by the sample window's own edges --
      §E) and every one of them has the SAME size. "Interior" is what
      makes this trustworthy -- an edge bucket's own count is never
      used to judge stability.
    - MEDIUM: either (a) too few interior buckets to judge on their own
      (fewer than 2), but EVERY bucket including the edges happens to
      already agree, or (b) 2+ interior buckets exist but vary by at
      most 1 row from each other (a small, plausible amount of
      real-world jitter, not a structurally different pattern).
    - LOW: anything else -- fewer than 2 total buckets (no transition
      to measure at all), or an interior spread of more than 1 row.
    """
    if len(bucket_sizes) < 2:
        return CONFIDENCE_LOW
    if len(interior_sizes) >= 2 and len(set(interior_sizes)) == 1:
        return CONFIDENCE_HIGH
    if len(set(bucket_sizes)) == 1:
        return CONFIDENCE_MEDIUM
    if len(interior_sizes) >= 2 and (max(interior_sizes) - min(interior_sizes)) <= 1:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def detect_repeated_timestamp_precision_loss(
    raw_values_by_row: list[tuple[int, Any]], *, requested_interval_seconds: float | None, requested_options: dict[str, Any],
) -> TimeAxisDetectionResult:
    """Repeated-timestamp / precision-loss detection (task §A-§L, §O-§R).
    Never mutates or reorders anything -- a pure classification over an
    already-bounded sample. See this module's own docstring for the
    full "detect, suggest, preview -- never silently apply" contract.
    """
    analysis = _analyze_buckets(raw_values_by_row, requested_options=requested_options)
    diagnostics: list[TimeAxisDiagnostic] = []
    if analysis.missing_count:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_MISSING_DATETIME_VALUE,
                message=f"{analysis.missing_count} sampled row(s) have no value in this Time Axis column.",
                ambiguity=AMBIGUITY_UNAMBIGUOUS, details={"missing_count": analysis.missing_count},
            )
        )

    if analysis.ambiguous_date_order:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
                message=f"The date order is ambiguous -- {' and '.join(analysis.candidate_orders)} both fit every distinct timestamp.",
                suggested_action="Choose the correct date order to analyze this column's own repeated timestamps.",
                ambiguity=AMBIGUITY_AMBIGUOUS, details={"candidate_orders": analysis.candidate_orders},
            )
        )
        return TimeAxisDetectionResult(
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED, confidence=CONFIDENCE_LOW,
            diagnostics=diagnostics, resolved_options={"date_order": DATE_ORDER_AUTO},
            resolved_unit=None, resolved_interval_seconds=None,
        )

    if analysis.unparseable or analysis.family is None:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_UNPARSEABLE_DATETIME,
                message="This column's values could not be parsed as a consistent timestamp.",
                ambiguity=AMBIGUITY_INVALID,
            )
        )
        return TimeAxisDetectionResult(
            family=analysis.family or FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_UNKNOWN,
            diagnostics=diagnostics, resolved_options={}, resolved_unit=None, resolved_interval_seconds=None,
        )

    bucket_sizes = [len(row_numbers) for _, row_numbers in analysis.buckets]

    if max(bucket_sizes) <= 1:
        # No repetition anywhere in the sample -- nothing to reconstruct;
        # a clean, unambiguous pass-through (§5's own "clean case").
        return TimeAxisDetectionResult(
            family=analysis.family, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_HIGH,
            diagnostics=diagnostics, resolved_options={}, resolved_unit=None, resolved_interval_seconds=None,
        )

    repeated_bucket_count = sum(1 for size in bucket_sizes if size > 1)
    diagnostics.append(
        TimeAxisDiagnostic(
            severity_hint=SEVERITY_INFO, code=DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED,
            message=f"{repeated_bucket_count} of {len(bucket_sizes)} distinct timestamp value(s) in the sampled rows repeat across multiple rows.",
            ambiguity=AMBIGUITY_UNAMBIGUOUS, details={"repeated_bucket_count": repeated_bucket_count, "bucket_count": len(bucket_sizes)},
        )
    )
    diagnostics.append(
        TimeAxisDiagnostic(
            severity_hint=SEVERITY_INFO, code=DIAGNOSTIC_PRECISION_LOSS_SUSPECTED,
            message="Repeated timestamps suggest the source's own recorded precision is coarser than its true sampling interval.",
            ambiguity=AMBIGUITY_UNAMBIGUOUS,
        )
    )

    interior_sizes = bucket_sizes[1:-1]
    confidence = _bucket_confidence(bucket_sizes, interior_sizes)

    if len(interior_sizes) >= 2 and len(set(interior_sizes)) > 1:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_INCONSISTENT_BUCKET_COUNT,
                message=f"The number of rows sharing each timestamp varies across the sampled buckets ({sorted(set(interior_sizes))}).",
                ambiguity=AMBIGUITY_UNAMBIGUOUS, details={"observed_bucket_sizes": sorted(set(interior_sizes))},
            )
        )

    # One interval estimate per bucket transition (span to the NEXT
    # bucket, divided by THIS bucket's own row count) -- never using a
    # negative/zero span (goes-backward or, for `partial`, a midnight
    # rollover -- §Y: never auto-corrected, simply excluded as
    # unreliable evidence, never treated as ordinary corruption).
    # Estimate index 0 (built from the FIRST bucket's own count, which
    # may itself be truncated by the sample window -- §E) is excluded
    # from confidence-driving statistics specifically, falling back to
    # using it only if literally nothing else is available.
    spans = [analysis.seconds_from_first[i + 1] - analysis.seconds_from_first[i] for i in range(len(analysis.buckets) - 1)]
    raw_estimates = [(i, spans[i] / bucket_sizes[i]) for i in range(len(spans)) if spans[i] > 0]
    confidence_estimates = [estimate for index, estimate in raw_estimates if index != 0] or [estimate for _, estimate in raw_estimates]

    if requested_interval_seconds is not None:
        resolved_interval = requested_interval_seconds
        provenance = PROVENANCE_USER_SPECIFIED
        result_confidence = CONFIDENCE_HIGH
    elif confidence == CONFIDENCE_LOW or not confidence_estimates:
        diagnostics.append(
            TimeAxisDiagnostic(
                severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_CADENCE_NOT_RELIABLE,
                message="Repeated timestamps were detected, but a reliable sampling interval could not be determined from the sampled rows.",
                suggested_action="Enter timing manually, or use Sample Index instead.",
                ambiguity=AMBIGUITY_AMBIGUOUS,
            )
        )
        return TimeAxisDetectionResult(
            family=analysis.family, provenance=PROVENANCE_NATIVE, confidence=CONFIDENCE_LOW,
            diagnostics=diagnostics,
            resolved_options={"date_order": analysis.date_order_used} if analysis.family == FAMILY_ABSOLUTE else {},
            resolved_unit=None, resolved_interval_seconds=None,
        )
    else:
        resolved_interval = statistics.median(confidence_estimates)
        provenance = PROVENANCE_RECONSTRUCTED
        result_confidence = confidence

    # Missing/extra-sample diagnostics (§O/§P) -- only meaningful once a
    # real "expected" interior size exists; the first/last buckets are
    # never flagged (they may be legitimately truncated, §E).
    if interior_sizes:
        expected_size = Counter(interior_sizes).most_common(1)[0][0]
        missing_bucket_count = sum(1 for size in interior_sizes if size < expected_size)
        extra_bucket_count = sum(1 for size in interior_sizes if size > expected_size)
        if missing_bucket_count:
            diagnostics.append(
                TimeAxisDiagnostic(
                    severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE,
                    message=f"{missing_bucket_count} timestamp bucket(s) have fewer rows than the expected {expected_size}.",
                    ambiguity=AMBIGUITY_UNAMBIGUOUS,
                    details={"expected_bucket_size": expected_size, "affected_buckets": missing_bucket_count},
                )
            )
        if extra_bucket_count:
            diagnostics.append(
                TimeAxisDiagnostic(
                    severity_hint=SEVERITY_WARNING, code=DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT,
                    message=f"{extra_bucket_count} timestamp bucket(s) have more rows than the expected {expected_size}.",
                    ambiguity=AMBIGUITY_UNAMBIGUOUS,
                    details={"expected_bucket_size": expected_size, "affected_buckets": extra_bucket_count},
                )
            )

    anchor_offset_seconds = requested_options.get("anchor_offset_seconds", 0.0)
    try:
        anchor_offset_seconds = float(anchor_offset_seconds)
    except (TypeError, ValueError):
        anchor_offset_seconds = 0.0

    diagnostics.append(
        TimeAxisDiagnostic(
            severity_hint=SEVERITY_INFO, code=DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED,
            message=(
                "Reconstructed timestamps assume the first sample in each repeated-timestamp "
                "group aligns with the displayed timestamp, unless adjusted -- spacing is "
                "reconstructed, the original sub-second phase is not recovered."
            ),
            ambiguity=AMBIGUITY_UNAMBIGUOUS, details={"anchor_offset_seconds": anchor_offset_seconds},
        )
    )

    resolved_options: dict[str, Any] = {"anchor_offset_seconds": anchor_offset_seconds}
    if analysis.family == FAMILY_ABSOLUTE:
        resolved_options["date_order"] = analysis.date_order_used

    return TimeAxisDetectionResult(
        family=analysis.family, provenance=provenance, confidence=result_confidence,
        diagnostics=diagnostics, resolved_options=resolved_options,
        resolved_unit=None, resolved_interval_seconds=resolved_interval,
    )


def _format_seconds_from_midnight(total_seconds: float) -> str:
    total_seconds = total_seconds % 86400  # partial has no date -- never invent a day boundary beyond wrapping for display
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:09.6f}"


def build_repeated_timestamp_preview(
    samples: list[tuple[int, tuple[Any, ...]]], *, resolved_options: dict[str, Any],
    resolved_interval_seconds: float | None, limit: int,
) -> list[tuple[int, tuple[Any, ...], str | None]]:
    """Bounded {original, interpreted} preview (§S) -- re-derives the
    SAME bucket grouping `detect_repeated_timestamp_precision_loss()`
    itself computed (cheap, over the same already-bounded sample; never
    a second, divergent grouping implementation) so each row's own
    bucket/position is known, then formats using the resolved interval
    and the resolved (or default `0.0`) anchor offset. `None` (never a
    fabricated value) for any row whose bucket/position could not be
    established, or when no interval is resolved yet at all."""
    raw = [(row_number, values[0] if values else None) for row_number, values in samples]
    analysis = _analyze_buckets(raw, requested_options=resolved_options)
    if resolved_interval_seconds is None or analysis.unparseable or analysis.ambiguous_date_order or analysis.family is None:
        return [(row_number, values, None) for row_number, values in samples[:limit]]

    anchor_offset_seconds = resolved_options.get("anchor_offset_seconds", 0.0)
    try:
        anchor_offset_seconds = float(anchor_offset_seconds)
    except (TypeError, ValueError):
        anchor_offset_seconds = 0.0

    row_position: dict[int, tuple[int, int]] = {}
    for bucket_index, (_, row_numbers) in enumerate(analysis.buckets):
        for position, row_number in enumerate(row_numbers):
            row_position[row_number] = (bucket_index, position)

    rows: list[tuple[int, tuple[Any, ...], str | None]] = []
    for row_number, values in samples[:limit]:
        location = row_position.get(row_number)
        if location is None:
            rows.append((row_number, values, None))
            continue
        bucket_index, position = location
        offset = analysis.seconds_from_first[bucket_index] + anchor_offset_seconds + position * resolved_interval_seconds
        try:
            if analysis.family == FAMILY_ABSOLUTE:
                interpreted = (analysis.anchor_reference + dt.timedelta(seconds=offset)).isoformat()
            else:
                interpreted = _format_seconds_from_midnight(analysis.anchor_reference + offset)
        except (OverflowError, ValueError):
            interpreted = None
        rows.append((row_number, values, interpreted))
    return rows
