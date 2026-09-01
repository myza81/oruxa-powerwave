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
    `resolve_status()`."""

    severity_hint: str
    code: str
    message: str
    location: IssueLocation | None = None
    suggested_action: str | None = None
    ambiguity: str = AMBIGUITY_UNAMBIGUOUS
    details: dict[str, Any] | None = None


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
    unresolved)."""

    family: str | None
    provenance: str | None
    confidence: str
    diagnostics: list[TimeAxisDiagnostic]
    resolved_options: dict[str, Any]


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
       `ambiguous_date_order`), distinct from a plain data-quality
       finding. This is the first production path that actually reaches
       `STATUS_REVIEW_REQUIRED` (Slice 7 never did -- see that
       constant's own docstring, now superseded by this rule).
    5. Any OTHER diagnostics present and not yet confirmed ->
       `needs_attention` (e.g. `unparseable_datetime`,
       `missing_datetime_value` -- a finding worth surfacing, but not
       one with a specific choice for the user to make).
    6. `confirmed` -> `confirmed`.
    7. Otherwise -> `detected`.
    """
    if configuration is None:
        return STATUS_UNCONFIGURED
    if configuration.interpreter_id == INTERPRETER_ID_UNSUPPORTED or not columns_still_time_axis:
        return STATUS_UNSUPPORTED
    if configuration.family == FAMILY_SAMPLE_INDEX and configuration.provenance == PROVENANCE_INDEX_ONLY:
        return STATUS_INDEX_FALLBACK
    if not configuration.confirmed and _has_ambiguous_diagnostic(diagnostics):
        return STATUS_REVIEW_REQUIRED
    if diagnostics:
        return STATUS_NEEDS_ATTENTION
    if configuration.confirmed:
        return STATUS_CONFIRMED
    return STATUS_DETECTED


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
