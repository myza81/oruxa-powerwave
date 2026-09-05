"""Time-Axis interpretation FRAMEWORK domain model (CSV/Excel ingestion
Slice 7, DEC-072). Authoritative design source:
docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md.

**This module is framework only.** It defines the shapes and the small
set of pure, non-parsing mutation functions the rest of the system
needs to represent a Time-Axis interpretation -- it contains NO real
datetime parsing, NO reconstruction algorithm, NO confidence
calculation, and NO detection logic. Every value this module's own
functions ever produce is either exactly what the caller supplied
(`manual` interpreter, see `app.services.time_axis_service`) or the
explicit "nothing was determined" sentinel (`unsupported` interpreter).
Slice 8 is the slice that teaches the registry (§ below) to actually
look at data.

Fits into the SAME architecture every prior slice already established:

    Immutable raw source (PreparationSession.raw_bytes, untouched)
            +
    Sparse WorkingOverlay (this module adds ONE more sparse dict,
    `WorkingOverlay.time_axis`, exactly like `header_row`/`data_region`/
    `column_roles` before it -- same undo/redo history, same revision
    counter, zero new mechanism)
            =
    Working view (computed live at read time by
    app.services.time_axis_service, never cached, mirroring
    app.services.preparation_issue_service's own "derive live" choice)

Coordinate identity: a `TimeAxisConfiguration` is scoped by
`worksheet_index_or_None` alone (`None` for CSV; a real 0-based index
for Excel) -- the SAME coarse scope `header_row`/`data_region` already
use, since a time-axis configuration is a worksheet/source-wide
setting, not a per-row/per-cell one. `column_indices` inside it are
0-based, matching every other column reference in this codebase.

**Relationship with column roles (Slice 5)**: a `TimeAxisConfiguration`
may only be CREATED referencing columns that currently carry
`app.domain.working_overlay.ROLE_TIME_AXIS`
(`app.services.time_axis_service` enforces this at write time). If the
user later changes one of those columns' own role away from
`ROLE_TIME_AXIS`, the STORED configuration is deliberately left
untouched here -- no automatic clearing, no cross-mutation between
`set_column_role()` and this module's own state, which would otherwise
either need a second bundled undo-history entry or silently skip
recording one. Instead, staleness is detected LIVE, at
result-computation time (`resolve_status()` below, given the current
`column_roles` state as an input) and reported as `STATUS_UNSUPPORTED`
-- the configuration is never presented as valid once stale, even
though it is never silently mutated either. This is Slice 7's own
chosen minimal rule; an alternative (auto-clearing on role change) was
considered and rejected specifically to avoid a compound,
harder-to-reason-about undo/redo step.

**Relationship with `app.domain.preparation_issue`**: time-axis
diagnostics (`TimeAxisDiagnostic` below) are a SEPARATE model, not
merged into `PreparationIssue`/`PreparationIssueSummary` -- Slice 6's
own severity model (`blocking`/`warning`/`info`) is reused here only as
a borrowed, informal VOCABULARY for `TimeAxisDiagnostic.severity_hint`
(so the eventual mapping, if any, is a relabeling exercise rather than
a redesign) -- it is never counted into, or transported through,
`GET .../issues`. `TimeAxisDiagnostic.location` reuses
`app.domain.preparation_issue.IssueLocation` verbatim (the exact same
optional worksheet/row/column/field shape) rather than a second,
parallel location type. Whether/how these two models are unified is an
explicit open question for whenever Slice 9 (Readiness Validator) is
actually scoped -- see CSV_EXCEL_TIME_INTERPRETATION.md §13/§21. Slice 7
never produces a single real diagnostic (the list is always empty in
practice today) -- the shape exists so Slice 8 has somewhere to put
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.preparation_issue import IssueLocation, SEVERITY_BLOCKING, SEVERITY_INFO, SEVERITY_WARNING

#: Time semantic families (CSV_EXCEL_TIME_INTERPRETATION.md §3).
#: Deliberately open-ended (DEC-072 point 6) -- this tuple is the
#: CURRENTLY known set, not a permanently closed enumeration; a future
#: family is added here exactly the way `KNOWN_COLUMN_ROLES` already
#: grows, never by inventing a second parallel list elsewhere.
FAMILY_ABSOLUTE = "absolute"
FAMILY_ELAPSED = "elapsed"
FAMILY_SAMPLE_INDEX = "sample_index"
FAMILY_PARTIAL = "partial"
FAMILY_UNKNOWN = "unknown"
KNOWN_TIME_FAMILIES = (
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_SAMPLE_INDEX,
    FAMILY_PARTIAL,
    FAMILY_UNKNOWN,
)

#: Time provenance / interpretation quality
#: (CSV_EXCEL_TIME_INTERPRETATION.md §4). Deliberately four states, not
#: five -- "inferred" was considered and folded into `confidence`
#: (below) instead, since it would otherwise duplicate that concept
#: (see this module's own design doc §4 for the full reasoning). A
#: `reconstructed` value must never be presented as though `native`.
PROVENANCE_NATIVE = "native"
PROVENANCE_RECONSTRUCTED = "reconstructed"
PROVENANCE_USER_SPECIFIED = "user_specified"
PROVENANCE_INDEX_ONLY = "index_only"
KNOWN_PROVENANCES = (
    PROVENANCE_NATIVE,
    PROVENANCE_RECONSTRUCTED,
    PROVENANCE_USER_SPECIFIED,
    PROVENANCE_INDEX_ONLY,
)

#: Qualitative confidence (CSV_EXCEL_TIME_INTERPRETATION.md §6).
#: Deliberately NOT a numeric score -- Slice 7 never computes a real
#: value here at all; every `TimeAxisInterpretationResult` this slice
#: produces carries `CONFIDENCE_UNKNOWN`, since no detection logic
#: exists yet to justify anything else. Slice 8's own interpreters are
#: the first real producers of `HIGH`/`MEDIUM`/`LOW`.
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"
KNOWN_CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_UNKNOWN)

#: User-facing status model (CSV_EXCEL_TIME_INTERPRETATION.md §15.3) --
#: deliberately small; internal interpreter state may be richer, but
#: nothing richer than this is ever shown to the user. `REVIEW_REQUIRED`
#: was UNREACHABLE in Slice 7's own `resolve_status()` (no interpreter
#: produced a diagnostic yet) -- Slice 8A's deterministic absolute-time
#: interpreters are the first real producers, for the specific case of
#: an unresolved `ambiguous_date_order` diagnostic (see
#: `resolve_status()` below).
STATUS_UNCONFIGURED = "unconfigured"
STATUS_DETECTED = "detected"
STATUS_REVIEW_REQUIRED = "review_required"
STATUS_CONFIRMED = "confirmed"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_INDEX_FALLBACK = "index_fallback"
STATUS_UNSUPPORTED = "unsupported"
KNOWN_TIME_AXIS_STATUSES = (
    STATUS_UNCONFIGURED,
    STATUS_DETECTED,
    STATUS_REVIEW_REQUIRED,
    STATUS_CONFIRMED,
    STATUS_NEEDS_ATTENTION,
    STATUS_INDEX_FALLBACK,
    STATUS_UNSUPPORTED,
)

#: The Slice 7 framework interpreter identifiers, plus the two Slice 8A
#: deterministic absolute-time interpreters -- see
#: `app.services.time_axis_service`'s own module docstring for what
#: `manual`/`unsupported` do, and `app.services.time_axis_interpreters`
#: for what the two real ones do. Declared here (not only in the
#: service module) so domain-level code (`resolve_status()` below) can
#: recognize the `unsupported` sentinel without importing the service
#: layer.
INTERPRETER_ID_MANUAL = "manual"
INTERPRETER_ID_UNSUPPORTED = "unsupported"
INTERPRETER_ID_ABSOLUTE_DATETIME = "absolute_datetime"
INTERPRETER_ID_SPLIT_DATE_TIME = "split_date_time"

#: Borrowed vocabulary ONLY (see this module's own docstring) -- never
#: wired into `PreparationIssueSummary`'s own counts.
KNOWN_DIAGNOSTIC_SEVERITY_HINTS = (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO)

#: Date-component ordering for the two-digit/four-digit slash-or-dash
#: date styles a deterministic (non-fuzzy) absolute-datetime interpreter
#: has to disambiguate (CSV_EXCEL_TIME_INTERPRETATION.md §3's own
#: "01/02/2026" worked example) -- `auto` means "not yet chosen; try
#: every known order and see whether the sample data itself resolves
#: the ambiguity by elimination" (Slice 8A's own §D/§E: a day value >12
#: already rules out `mdy` without needing a locale guess). Kept as an
#: open-ended tuple like every other vocabulary in this module, not a
#: hard-coded two-way switch.
DATE_ORDER_DMY = "dmy"
DATE_ORDER_MDY = "mdy"
DATE_ORDER_YMD = "ymd"
DATE_ORDER_AUTO = "auto"
KNOWN_DATE_ORDERS = (DATE_ORDER_DMY, DATE_ORDER_MDY, DATE_ORDER_YMD, DATE_ORDER_AUTO)

#: Ambiguity classification (Slice 8A §D) -- a SEPARATE axis from
#: `confidence` above: confidence is "how much evidence supports this
#: reading," ambiguity is "could a reasonable person read this
#: differently, or is it simply broken." `unambiguous` covers both a
#: self-describing format (ISO-8601) and a format resolved BY
#: ELIMINATION (only one candidate order parses every sampled value) --
#: neither is a guess. `ambiguous` means two or more candidate orders
#: each parse the ENTIRE sample validly and only the user can pick.
#: `invalid` means the sample could not be parsed as a coherent absolute
#: timestamp under any candidate at all (or only partially, under the
#: currently selected order) -- a data-quality finding, not a decision
#: for the user to make.
AMBIGUITY_UNAMBIGUOUS = "unambiguous"
AMBIGUITY_AMBIGUOUS = "ambiguous"
AMBIGUITY_INVALID = "invalid"
KNOWN_AMBIGUITY_LEVELS = (AMBIGUITY_UNAMBIGUOUS, AMBIGUITY_AMBIGUOUS, AMBIGUITY_INVALID)

#: Diagnostic codes the Slice 8A deterministic interpreters may produce
#: (§K). Not an exhaustive closed set for all time -- future
#: interpreters may add their own codes exactly like `KNOWN_TIME_FAMILIES`
#: grows -- but these are the ones THIS slice's own two interpreters are
#: capable of emitting, kept here (not string-literal scattered through
#: the service module) so tests and documentation have one place to
#: read the vocabulary from.
DIAGNOSTIC_AMBIGUOUS_DATE_ORDER = "ambiguous_date_order"
DIAGNOSTIC_UNPARSEABLE_DATETIME = "unparseable_datetime"
DIAGNOSTIC_MIXED_DATETIME_FORMAT = "mixed_datetime_format"
DIAGNOSTIC_MISSING_DATETIME_VALUE = "missing_datetime_value"
DIAGNOSTIC_TIMEZONE_INCONSISTENT = "timezone_inconsistent"
DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE = "time_only_not_absolute"

#: The two Slice 8B interpreter identifiers -- see
#: `app.services.time_axis_interpreters` for what each actually does.
INTERPRETER_ID_ELAPSED_NUMERIC = "elapsed_numeric"
INTERPRETER_ID_SAMPLE_INDEX = "sample_index"

#: Elapsed-time units (CSV_EXCEL_TIME_INTERPRETATION.md §9) -- matches
#: `TimingInformation.time_axis_unit`'s own existing (previously dead)
#: field, which `elapsed_numeric` (Slice 8B) is the first real producer
#: for. Deliberately open-ended like every other vocabulary in this
#: module (a future interpreter may recognize more units), but THIS
#: interpreter's own contract only ever accepts these four -- see
#: `app.services.time_axis_service.set_time_axis_configuration`'s own
#: unit-set validation, scoped to `elapsed_numeric` specifically so it
#: never narrows `manual`'s deliberately open-ended `unit` field.
UNIT_SECONDS = "seconds"
UNIT_MILLISECONDS = "milliseconds"
UNIT_MICROSECONDS = "microseconds"
UNIT_NANOSECONDS = "nanoseconds"
#: Enhancement (fixed-duration elapsed units, owner-approved scope):
#: minutes/hours/days/weeks are all FIXED-duration units (60/3600/
#: 86400/604800 seconds respectively -- see
#: `app.services.time_axis_interpreters._ELAPSED_UNIT_SECONDS_FACTOR`
#: for the actual conversion factors) needing no calendar anchor,
#: unlike a month or year (variable length -- 28-31 days, 365-366 days
#: -- with no single fixed-seconds factor). Months/years are
#: deliberately NOT added here and never will be under this same
#: fixed-multiplier model; a calendar-aware elapsed unit would need a
#: genuine anchor DATE this interpreter never has (`elapsed_numeric`'s
#: own "no invented absolute time" contract), so it is a structurally
#: different, separate feature, not an extension of this tuple.
UNIT_MINUTES = "minutes"
UNIT_HOURS = "hours"
UNIT_DAYS = "days"
UNIT_WEEKS = "weeks"
KNOWN_ELAPSED_UNITS = (
    UNIT_SECONDS, UNIT_MILLISECONDS, UNIT_MICROSECONDS, UNIT_NANOSECONDS,
    UNIT_MINUTES, UNIT_HOURS, UNIT_DAYS, UNIT_WEEKS,
)

#: Diagnostic codes the Slice 8B deterministic interpreters may produce
#: (§C/§J). `DIAGNOSTIC_MISSING_ELAPSED_UNIT` is the ONE Slice 8B
#: diagnostic that ever carries `AMBIGUITY_AMBIGUOUS` -- an elapsed
#: column with no unit chosen is not "broken data," it is a genuine
#: unresolved CHOICE the user must make (§8/§9's own "units are never
#: silently inferred... the field stays required" rule), so it routes
#: through the exact same `STATUS_REVIEW_REQUIRED` precedence Slice 8A's
#: `ambiguous_date_order` already established -- no new status logic
#: needed. Every other diagnostic below is a plain data-quality finding
#: (`unambiguous`/`invalid`), never a "the user must choose" case.
DIAGNOSTIC_MISSING_ELAPSED_UNIT = "missing_elapsed_unit"
DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE = "non_numeric_elapsed_value"
DIAGNOSTIC_MISSING_ELAPSED_VALUE = "missing_elapsed_value"
DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD = "elapsed_time_goes_backward"
DIAGNOSTIC_REPEATED_ELAPSED_TIME = "repeated_elapsed_time"
DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL = "non_uniform_elapsed_interval"
DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX = "non_numeric_sample_index"
DIAGNOSTIC_MISSING_SAMPLE_INDEX = "missing_sample_index"
DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD = "sample_index_goes_backward"
DIAGNOSTIC_REPEATED_SAMPLE_INDEX = "repeated_sample_index"
DIAGNOSTIC_SAMPLE_INDEX_GAP = "sample_index_gap"

#: The one Slice 8C interpreter identifier -- see
#: `app.services.time_axis_interpreters` for what it does. Accepts
#: exactly 1 column, same as `absolute_datetime`/`elapsed_numeric`.
INTERPRETER_ID_REPEATED_TIMESTAMP = "repeated_timestamp_precision_loss"

#: Diagnostic codes the Slice 8C interpreter may produce (§R).
#: `DIAGNOSTIC_CADENCE_NOT_RELIABLE` is the ONE Slice 8C diagnostic that
#: ever carries `AMBIGUITY_AMBIGUOUS` -- when confidence is too low to
#: offer any concrete suggestion at all, there is nothing yet to accept
#: (the user must actively choose manual timing or Sample Index), so it
#: routes through the same `STATUS_REVIEW_REQUIRED`-blocks-`confirmed`
#: precedence `ambiguous_date_order`/`missing_elapsed_unit` already
#: established. A HIGH/MEDIUM-confidence suggestion is a fundamentally
#: DIFFERENT situation -- a concrete, actionable proposal already
#: exists, and `confirmed=true` accepting it must be ALLOWED to
#: succeed -- so `repeated_timestamp_detected`/`precision_loss_suspected`/
#: `anchor_assumption_required` (always attached whenever a real
#: suggestion is offered) are deliberately `unambiguous`; instead,
#: `resolve_status()` gets its own SEPARATE new precedence rule keying
#: off `provenance == PROVENANCE_RECONSTRUCTED` directly (§15.3's own
#: "Review suggested — a diagnostic exists AND/OR a reconstruction is
#: offered" wording, taken literally as a second, independent trigger
#: for the same `STATUS_REVIEW_REQUIRED` value -- not a re-use of the
#: ambiguity-blocks-confirm mechanism, which would make an offered
#: suggestion impossible to ever accept).
DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED = "repeated_timestamp_detected"
DIAGNOSTIC_PRECISION_LOSS_SUSPECTED = "precision_loss_suspected"
DIAGNOSTIC_INCONSISTENT_BUCKET_COUNT = "inconsistent_bucket_count"
DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE = "possible_missing_sample"
DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT = "unexpected_bucket_sample_count"
DIAGNOSTIC_CADENCE_NOT_RELIABLE = "cadence_not_reliable"
DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED = "anchor_assumption_required"

#: Slice 8D (DEC-072, "Time Irregularity Diagnostics") -- the small set
#: of GENUINELY NEW diagnostic codes this slice adds, filling the one
#: real gap left by Slices 8A-8C: `absolute_datetime`/`split_date_time`
#: never checked row-to-row timing quality at all (only elapsed_numeric/
#: sample_index, and repeated_timestamp_precision_loss's own bucket
#: cadence, ever did). Every OTHER condition Slice 8D's own task asks
#: for already has an established code from an earlier slice --
#: `missing_datetime_value`/`missing_elapsed_value`/`missing_sample_index`
#: (missing timestamp), `unparseable_datetime` (unparseable timestamp),
#: `mixed_datetime_format` (mixed format), `ambiguous_date_order`
#: (ambiguous date order), `repeated_timestamp_detected`/
#: `elapsed_time_goes_backward`/`repeated_elapsed_time`/
#: `non_uniform_elapsed_interval`/`sample_index_gap`/
#: `repeated_sample_index`/`sample_index_goes_backward`/
#: `possible_missing_sample`/`unexpected_bucket_sample_count`/
#: `cadence_not_reliable` (their own respective family's repeat/backward/
#: gap/cadence findings) -- reused verbatim, never renamed, per this
#: slice's own "prefer consolidation... do not rename existing public
#: codes unnecessarily" instruction.
#:
#: `DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED` is checked BEFORE
#: `DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED` for a `partial`-family
#: backward transition specifically -- a time-of-day column wrapping
#: `23:59:59 -> 00:00:00` is a distinct, well-understood condition
#: (§D), never generic backward-time corruption, and never implies a
#: fabricated date or an automatic day increment.
#:
#: All five are `SEVERITY_WARNING`/`AMBIGUITY_UNAMBIGUOUS` -- the exact
#: same combination `elapsed_time_goes_backward`/`sample_index_gap`
#: already use: attention-worthy once surfaced (via the existing
#: `_has_attention_worthy_diagnostic` -> `needs_attention` path), but
#: NEVER blocking `confirmed=true` (only `AMBIGUITY_AMBIGUOUS` does
#: that) -- these are "flag, never force a decision" findings per
#: CSV_EXCEL_TIME_INTERPRETATION.md §11's own table, not a "the user
#: must choose" case. No new `resolve_status()` rule was needed for
#: this slice at all.
DIAGNOSTIC_TIME_GOES_BACKWARD = "time_goes_backward"
DIAGNOSTIC_LARGE_TIME_GAP = "large_time_gap"
DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED = "timestamp_reset_suspected"
DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED = "partial_midnight_rollover_suspected"
DIAGNOSTIC_NON_UNIFORM_INTERVAL = "non_uniform_interval"

#: Slice 8D (§N/§O): lightweight, INTERNAL/UX grouping labels only --
#: never mapped to `blocking`/`warning`/`info` (that mapping, if any,
#: remains Slice 9's own decision, per this module's own docstring on
#: `KNOWN_DIAGNOSTIC_SEVERITY_HINTS`). Computed from `code` via
#: `diagnostic_category()` below, never stored as a second, independently
#: settable field -- one canonical mapping, not N call sites each having
#: to remember to set it correctly.
CATEGORY_FORMAT = "format"
CATEGORY_ORDERING = "ordering"
CATEGORY_GAP = "gap"
CATEGORY_REPEAT = "repeat"
CATEGORY_SAMPLING = "sampling"
CATEGORY_AMBIGUITY = "ambiguity"
KNOWN_DIAGNOSTIC_CATEGORIES = (
    CATEGORY_FORMAT, CATEGORY_ORDERING, CATEGORY_GAP, CATEGORY_REPEAT, CATEGORY_SAMPLING, CATEGORY_AMBIGUITY,
)

#: One central code->category table (Slice 8D) -- covers every
#: diagnostic code produced anywhere in Slices 8A-8D. A code not listed
#: here (future slice) simply has no category yet (`None`), never a
#: crash -- see `diagnostic_category()`.
_DIAGNOSTIC_CATEGORY_BY_CODE: dict[str, str] = {
    DIAGNOSTIC_AMBIGUOUS_DATE_ORDER: CATEGORY_AMBIGUITY,
    DIAGNOSTIC_UNPARSEABLE_DATETIME: CATEGORY_FORMAT,
    DIAGNOSTIC_MIXED_DATETIME_FORMAT: CATEGORY_FORMAT,
    DIAGNOSTIC_MISSING_DATETIME_VALUE: CATEGORY_FORMAT,
    DIAGNOSTIC_TIMEZONE_INCONSISTENT: CATEGORY_FORMAT,
    DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE: CATEGORY_FORMAT,
    DIAGNOSTIC_MISSING_ELAPSED_UNIT: CATEGORY_AMBIGUITY,
    DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE: CATEGORY_FORMAT,
    DIAGNOSTIC_MISSING_ELAPSED_VALUE: CATEGORY_FORMAT,
    DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD: CATEGORY_ORDERING,
    DIAGNOSTIC_REPEATED_ELAPSED_TIME: CATEGORY_REPEAT,
    DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL: CATEGORY_SAMPLING,
    DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX: CATEGORY_FORMAT,
    DIAGNOSTIC_MISSING_SAMPLE_INDEX: CATEGORY_FORMAT,
    DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD: CATEGORY_ORDERING,
    DIAGNOSTIC_REPEATED_SAMPLE_INDEX: CATEGORY_REPEAT,
    DIAGNOSTIC_SAMPLE_INDEX_GAP: CATEGORY_GAP,
    DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED: CATEGORY_REPEAT,
    DIAGNOSTIC_PRECISION_LOSS_SUSPECTED: CATEGORY_REPEAT,
    DIAGNOSTIC_INCONSISTENT_BUCKET_COUNT: CATEGORY_SAMPLING,
    DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE: CATEGORY_SAMPLING,
    DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT: CATEGORY_SAMPLING,
    DIAGNOSTIC_CADENCE_NOT_RELIABLE: CATEGORY_SAMPLING,
    DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED: CATEGORY_REPEAT,
    DIAGNOSTIC_TIME_GOES_BACKWARD: CATEGORY_ORDERING,
    DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED: CATEGORY_ORDERING,
    DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED: CATEGORY_ORDERING,
    DIAGNOSTIC_LARGE_TIME_GAP: CATEGORY_GAP,
    DIAGNOSTIC_NON_UNIFORM_INTERVAL: CATEGORY_SAMPLING,
}


def diagnostic_category(code: str) -> str | None:
    """The Slice 8D UX-grouping category for a diagnostic `code`, or
    `None` if this code predates the category concept entirely (never
    raises)."""
    return _DIAGNOSTIC_CATEGORY_BY_CODE.get(code)


@dataclass(slots=True, frozen=True)
class TimeAxisConfiguration:
    """One worksheet/source's own current time-axis configuration --
    always the whole object is replaced on any change (never mutated
    in place), matching `DataRegion`/`CellOverride`'s own established
    frozen-dataclass convention.

    `column_indices` is the ordered "Time Axis Input Set"
    (CSV_EXCEL_TIME_INTERPRETATION.md §10) -- one or more 0-based column
    indices, always a subset of the columns currently carrying
    `app.domain.working_overlay.ROLE_TIME_AXIS` at the moment this
    configuration was created (enforced by
    `app.services.time_axis_service`, not here).

    `family`/`provenance` are `None` ONLY for the built-in `unsupported`
    interpreter's own output (see `INTERPRETER_ID_UNSUPPORTED`) -- every
    other interpreter always sets both to one of `KNOWN_TIME_FAMILIES`/
    `KNOWN_PROVENANCES`.

    `unit`/`interval_seconds` are both optional and independent:
    `interval_seconds` is the CANONICAL internal timing value (seconds
    per sample) per CSV_EXCEL_TIME_INTERPRETATION.md §8's own explicit
    "pick one canonical internal representation" instruction -- a
    sampling RATE is only ever a display-time conversion of this value,
    never stored separately. `unit` is for the `elapsed` family's own
    numeric-unit requirement (§9) -- "seconds"/"milliseconds"/
    "microseconds"/"nanoseconds" today, open-ended like everything else
    here. Neither is ever required: `family=sample_index` with both
    `None` is an explicitly valid, complete state (§9's own "do not
    require a sampling rate merely to preserve row order" rule).

    `confirmed` records the User Authority Model's own explicit
    accept/adjust action (§5) -- never implied by anything else.

    `options` is a small, generic, interpreter-specific bag (e.g. a
    future interpreter's own extra settings) -- deliberately NOT
    pre-populated with Slice 8-only fields now, per this slice's own
    "do not overfill" guardrail.
    """

    column_indices: tuple[int, ...]
    family: str | None
    provenance: str | None
    interpreter_id: str
    unit: str | None = None
    interval_seconds: float | None = None
    confirmed: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class TimeAxisDiagnostic:
    """A structured time-interpretation finding -- see this module's
    own docstring for why this is a SEPARATE model from
    `app.domain.preparation_issue.PreparationIssue`, not a reuse of it.
    Never raised as an exception; always returned in a plain list.
    Slice 7 never constructed one in production code; Slice 8A's own
    two deterministic interpreters are the first real producers.

    `ambiguity` (Slice 8A, default `AMBIGUITY_UNAMBIGUOUS` for backward
    compatibility with a hypothetical pre-8A diagnostic) drives
    `resolve_status()`'s own `review_required` vs `needs_attention`
    split below -- `AMBIGUITY_AMBIGUOUS` is the ONLY value that routes
    to `review_required` (a genuine "the user must choose" case);
    `AMBIGUITY_INVALID` (broken/unparseable data) and
    `AMBIGUITY_UNAMBIGUOUS` (a diagnostic that is not about ambiguity at
    all, e.g. a missing-value count) both fall through to the existing
    generic `needs_attention` path -- one axis, reused, not a second
    parallel severity system.

    `details` mirrors `PreparationIssue.details`'s own role (a small,
    optional, structured data bag -- e.g. `{"unparsed_count": 3,
    "sample_size": 12}`) for a UI that wants more than the human-
    readable `message` alone; never required, never load-bearing for
    `resolve_status()`.

    `category` (Slice 8D, §N/§O) is a COMPUTED property, not a stored
    field -- looked up from `code` via `diagnostic_category()` above, so
    every diagnostic ever constructed (including every one from Slices
    7/8A/8B/8C, none of which needed to change) already has a correct
    `category` with zero call-site churn. Internal/UX grouping only,
    never mapped to `blocking`/`warning`/`info`."""

    severity_hint: str
    code: str
    message: str
    location: IssueLocation | None = None
    suggested_action: str | None = None
    ambiguity: str = AMBIGUITY_UNAMBIGUOUS
    details: dict[str, Any] | None = None

    @property
    def category(self) -> str | None:
        return diagnostic_category(self.code)


@dataclass(slots=True, frozen=True)
class TimeAxisSampleRow:
    """One bounded-sample row handed to an interpreter's own `detect()`/
    `build_preview_rows()` -- fetched ONCE by
    `app.services.time_axis_service` (via the existing
    `app.services.preparation_preview_service.preview_preparation_source`,
    never a second raw-reading implementation) and reused for both
    calls, per this module's own "bounded, no second fetch" requirement
    (§H). `values` holds exactly one raw (working-view) cell value per
    the configuration's own `column_indices`, IN THAT ORDER -- for
    `split_date_time`, `values[0]` is the date column's cell and
    `values[1]` is the time column's cell, since `column_indices` is
    itself documented as `(date_column_index, time_column_index)` for
    that interpreter specifically."""

    row_number: int
    values: tuple[Any, ...]


@dataclass(slots=True, frozen=True)
class TimeAxisPreviewRow:
    """One bounded preview row (§16/§J) -- `original` echoes
    `TimeAxisSampleRow.values` verbatim (never re-derived), `interpreted`
    is the resulting absolute-datetime value as an ISO-8601 string, or
    `None` when this particular row could not be interpreted under the
    resolved format (a per-row failure, never silently dropped -- the
    row still appears here with `interpreted=None`)."""

    row_number: int
    original: tuple[Any, ...]
    interpreted: str | None


@dataclass(slots=True, frozen=True)
class TimeAxisDetectionResult:
    """The pure output of one interpreter's own `detect()` call (§17's
    own illustrative `detect(...) -> DetectionResult` contract) --
    classification + confidence + diagnostics, computed from an
    already-fetched bounded sample, no I/O of its own. Used identically
    by `app.services.time_axis_service` at THREE call sites: (a) writing
    a new/changed configuration, (b) recomputing live diagnostics for an
    already-stored configuration on every `GET`, and (c) the dry-run
    `POST .../working/time-axis/interpret` preview action -- one
    function, three callers, never three detection implementations.

    `family`/`provenance` are `None` only for `unsupported`'s own
    output, matching `TimeAxisConfiguration`'s own same rule.
    `resolved_options` is the options bag to actually STORE (§C) -- for
    `manual` this simply echoes whatever the caller supplied; for a real
    interpreter it is the ACTUAL resolved configuration (e.g.
    `{"date_order": "dmy"}` once elimination or user confirmation
    settled it, still `{"date_order": "auto"}` while genuinely
    unresolved).

    `resolved_unit`/`resolved_interval_seconds` (Slice 8B) mirror
    `TimeAxisConfiguration`'s own same-named TOP-LEVEL fields (never
    `options` -- both already existed on that dataclass since Slice 7,
    anticipating exactly this) -- `elapsed_numeric` resolves `unit`
    only, `sample_index` resolves `interval_seconds` only,
    `absolute_datetime`/`split_date_time`/`manual`/`unsupported` leave
    both `None`. Kept as two explicit fields here (not folded into
    `resolved_options`) so the write path can assign them directly onto
    `TimeAxisConfiguration.unit`/`.interval_seconds` without the
    service layer needing to know which key means what per
    interpreter."""

    family: str | None
    provenance: str | None
    confidence: str
    diagnostics: list[TimeAxisDiagnostic]
    resolved_options: dict[str, Any]
    resolved_unit: str | None = None
    resolved_interval_seconds: float | None = None


@dataclass(slots=True)
class TimeAxisInterpretationResult:
    """The read-time-computed, presentation-ready summary of one
    worksheet/source's own time-axis state -- mirrors
    `app.domain.preparation_issue.PreparationIssueSummary`'s own role
    exactly (a live-derived wrapper around stored state, never itself
    persisted). Returned by
    `app.services.time_axis_service.get_time_axis_summary()` and by
    every mutation function in that same module.

    `confidence` is always `CONFIDENCE_UNKNOWN` in Slice 7 (no
    detection logic exists to justify anything else -- see
    `CONFIDENCE_UNKNOWN`'s own docstring above). `diagnostics` is
    always `[]` in Slice 7 for the same reason. `preview_supported` is
    always `False` in Slice 7 (CSV_EXCEL_TIME_INTERPRETATION.md §16's
    own bounded-preview model is a Slice 8 concern -- the field exists
    now purely as the seam, per this slice's own "avoid returning fake
    preview rows" guardrail). `confirmation_required` is `True`
    whenever a configuration exists and has not yet been explicitly
    confirmed -- Slice 7 has no way to distinguish "genuinely
    unambiguous, no confirmation needed" from anything else, so it
    never claims that distinction (a disclosed simplification, not a
    design contradiction -- CSV_EXCEL_TIME_INTERPRETATION.md §5's own
    "clean case" exception is left for Slice 8, once real detection can
    actually tell the difference).

    `unit`/`interval_seconds`/`confirmed`/`options` are plain,
    uninterpreted ECHOES of the stored `TimeAxisConfiguration`'s own
    same-named fields (verbatim, never recalculated) -- included so a
    caller (the frontend's own edit form in particular) can prefill from
    the one read endpoint this framework exposes, without a second
    "give me the raw stored configuration" API. This is presentation
    convenience only, not new derived state: exactly like
    `column_indices` above, which was already an echo rather than a
    calculation. `options` (Slice 8A) is how a caller learns the
    resolved `date_order`/similar interpreter-specific settings without
    a second endpoint."""

    status: str
    family: str | None
    provenance: str | None
    interpreter_id: str | None
    column_indices: tuple[int, ...]
    confidence: str = CONFIDENCE_UNKNOWN
    diagnostics: list[TimeAxisDiagnostic] = field(default_factory=list)
    preview_supported: bool = False
    confirmation_required: bool = False
    unit: str | None = None
    interval_seconds: float | None = None
    confirmed: bool = False
    options: dict[str, Any] = field(default_factory=dict)


def _has_ambiguous_diagnostic(diagnostics: list[TimeAxisDiagnostic]) -> bool:
    return any(d.ambiguity == AMBIGUITY_AMBIGUOUS for d in diagnostics)


def _has_attention_worthy_diagnostic(diagnostics: list[TimeAxisDiagnostic]) -> bool:
    """(Slice 8C) A diagnostic counts toward `needs_attention` only when
    it is NOT purely informational (`severity_hint != SEVERITY_INFO`).
    Slice 8C is the first producer of `SEVERITY_INFO` diagnostics --
    always-present disclosure notes (`repeated_timestamp_detected`,
    `anchor_assumption_required`) that describe a TRUE, permanent fact
    about an ACCEPTED reconstruction, never a problem to attend to. Without
    this filter, a confirmed reconstruction could never reach
    `STATUS_CONFIRMED` at all, since its own disclosure notes never go
    away. A genuine data-quality WARNING (e.g. `mixed_datetime_format`,
    `cadence_not_reliable`) still blocks `confirmed` from ever being
    reported, exactly as it always has for every earlier slice -- this
    filter changes nothing for Slice 7/8A/8B, which never produced an
    INFO-severity diagnostic."""
    return any(d.severity_hint != SEVERITY_INFO for d in diagnostics)


def resolve_status(
    configuration: TimeAxisConfiguration | None,
    *,
    columns_still_time_axis: bool,
    diagnostics: list[TimeAxisDiagnostic],
) -> str:
    """Pure function computing the user-facing `status` (§15.3) from
    already-known inputs -- no I/O, no session access (the caller,
    `app.services.time_axis_service`, resolves `columns_still_time_axis`
    against the CURRENT `column_roles` state, and `diagnostics` via a
    fresh `detect()` call for a sample-needing interpreter, before
    calling this).

    Precedence, most specific first:
    1. No configuration at all -> `unconfigured`.
    2. The stored configuration explicitly used the `unsupported`
       interpreter, OR its own columns no longer all carry the
       Time Axis role (staleness, see this module's own docstring) ->
       `unsupported`.
    3. `family == FAMILY_SAMPLE_INDEX` and
       `provenance == PROVENANCE_INDEX_ONLY` -> `index_fallback`.
    4. (Slice 8A) Any diagnostic carries `ambiguity == AMBIGUITY_AMBIGUOUS`
       and the configuration is not yet confirmed -> `review_required`
       -- a genuine "the user must pick one" case (e.g.
       `ambiguous_date_order`, Slice 8B's `missing_elapsed_unit`, Slice
       8C's `cadence_not_reliable`), distinct from a plain data-quality
       finding. This is the first production path that actually reaches
       `STATUS_REVIEW_REQUIRED` (Slice 7 never did -- see that
       constant's own docstring, now superseded by this rule).
    5. (Slice 8C) `provenance == PROVENANCE_RECONSTRUCTED` and the
       configuration is not yet confirmed -> `review_required` -- §15.3's
       own "a diagnostic exists AND/OR a reconstruction is offered"
       wording, taken as a SEPARATE trigger for the same status value.
       Deliberately NOT folded into rule 4's ambiguity mechanism: an
       offered reconstruction is a concrete, actionable proposal (not an
       unresolved choice), and `confirmed=true` accepting it must
       succeed -- which rule 4's own confirm-blocking behavior would
       otherwise prevent forever. See
       `DIAGNOSTIC_CADENCE_NOT_RELIABLE`'s own docstring for why the
       "nothing reliable to suggest" case uses rule 4 instead.
    6. Any OTHER ATTENTION-WORTHY diagnostic present (`severity_hint !=
       SEVERITY_INFO`) -> `needs_attention` (e.g. `unparseable_datetime`,
       `missing_datetime_value` -- a finding worth surfacing, but not
       one with a specific choice for the user to make). This rule is
       NOT gated on `not confirmed` -- a genuine data-quality warning
       stays surfaced even after confirmation, exactly as it always
       has. A purely informational diagnostic (Slice 8C's own
       `SEVERITY_INFO` disclosure notes) never triggers this rule at
       all -- see `_has_attention_worthy_diagnostic`'s own docstring
       for why (otherwise an accepted reconstruction could never reach
       `confirmed`, since its own disclosure notes never disappear).
    7. `confirmed` -> `confirmed`.
    8. Otherwise -> `detected`.
    """
    if configuration is None:
        return STATUS_UNCONFIGURED
    if configuration.interpreter_id == INTERPRETER_ID_UNSUPPORTED or not columns_still_time_axis:
        return STATUS_UNSUPPORTED
    if configuration.family == FAMILY_SAMPLE_INDEX and configuration.provenance == PROVENANCE_INDEX_ONLY:
        return STATUS_INDEX_FALLBACK
    if not configuration.confirmed and _has_ambiguous_diagnostic(diagnostics):
        return STATUS_REVIEW_REQUIRED
    if not configuration.confirmed and configuration.provenance == PROVENANCE_RECONSTRUCTED:
        return STATUS_REVIEW_REQUIRED
    if _has_attention_worthy_diagnostic(diagnostics):
        return STATUS_NEEDS_ATTENTION
    if configuration.confirmed:
        return STATUS_CONFIRMED
    return STATUS_DETECTED


def is_time_axis_resolved(result: TimeAxisInterpretationResult) -> bool:
    """Whether `result`'s own Time Axis is resolved enough to derive a
    real, standardized time value from -- the ONE shared eligibility
    check reused by cleaned export
    (`app.services.preparation_export_service._ensure_exportable`) and
    the Data Preview's own derived "Configured Time" column
    (`app.services.time_axis_service.build_configured_time_values`), so
    the two features can never silently disagree about what counts as
    "resolved" (a 2026-09-04 UAT enhancement's own explicit "reuse
    existing resolved-time logic" rule).

    `True` for `STATUS_DETECTED`/`STATUS_CONFIRMED`/
    `STATUS_NEEDS_ATTENTION`/`STATUS_INDEX_FALLBACK` -- a genuine,
    usable reading exists even if it also carries a data-quality
    warning, was never explicitly confirmed (the prior confirmation-UX
    UAT fix's own "native/unambiguous needs no confirmation" policy),
    or floats on sample-index-only fallback. `False` for
    `STATUS_UNCONFIGURED`/`STATUS_UNSUPPORTED`/`STATUS_REVIEW_REQUIRED`
    (no coherent reading exists yet -- unconfigured, a stale role
    reference, an unresolved ambiguity, or an unconfirmed reconstruction
    suggestion), for a `manual`/`unsupported` interpreter (neither ever
    parses a real per-row value from the source's own columns), and for
    `sample_index` with no real interval/rate (index-only can never
    honestly become a seconds value -- `sample 5 != 5 seconds`)."""
    if result.status in (STATUS_UNCONFIGURED, STATUS_UNSUPPORTED, STATUS_REVIEW_REQUIRED):
        return False
    if result.interpreter_id in (INTERPRETER_ID_MANUAL, INTERPRETER_ID_UNSUPPORTED):
        return False
    if result.family == FAMILY_SAMPLE_INDEX and result.interval_seconds is None:
        return False
    return True


def build_interpretation_result(
    configuration: TimeAxisConfiguration | None,
    *,
    columns_still_time_axis: bool,
    diagnostics: list[TimeAxisDiagnostic] | None = None,
    confidence: str = CONFIDENCE_UNKNOWN,
    preview_supported: bool = False,
) -> TimeAxisInterpretationResult:
    """The one place `TimeAxisInterpretationResult` is assembled, so
    `status`/`confirmation_required` can never drift out of sync with
    each other across call sites. `confidence`/`preview_supported`
    (Slice 8A) are supplied by the caller -- `app.services.
    time_axis_service`, which alone knows (via the interpreter
    registry) whether the resolved interpreter actually computed a real
    confidence value or supports a preview; this module never imports
    the service layer to look that up itself."""
    diagnostics = diagnostics or []
    status = resolve_status(configuration, columns_still_time_axis=columns_still_time_axis, diagnostics=diagnostics)
    return TimeAxisInterpretationResult(
        status=status,
        family=configuration.family if configuration else None,
        provenance=configuration.provenance if configuration else None,
        interpreter_id=configuration.interpreter_id if configuration else None,
        column_indices=configuration.column_indices if configuration else (),
        confidence=confidence,
        diagnostics=diagnostics,
        preview_supported=preview_supported,
        confirmation_required=bool(configuration and not configuration.confirmed),
        unit=configuration.unit if configuration else None,
        interval_seconds=configuration.interval_seconds if configuration else None,
        confirmed=configuration.confirmed if configuration else False,
        options=dict(configuration.options) if configuration else {},
    )
