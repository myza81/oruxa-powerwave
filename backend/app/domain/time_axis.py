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
#: is a currently-UNREACHABLE status in Slice 7's own `resolve_status()`
#: below (see that function's own docstring) -- it is a valid, real
#: value the type supports, reserved for Slice 8, once a diagnostic can
#: carry an actionable suggestion worth distinguishing from a plain
#: "needs attention" finding.
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

#: The two Slice 7 interpreter identifiers -- see
#: `app.services.time_axis_service`'s own module docstring for what
#: each actually does. Declared here (not only in the service module)
#: so domain-level code (`resolve_status()` below) can recognize the
#: `unsupported` sentinel without importing the service layer.
INTERPRETER_ID_MANUAL = "manual"
INTERPRETER_ID_UNSUPPORTED = "unsupported"

#: Borrowed vocabulary ONLY (see this module's own docstring) -- never
#: wired into `PreparationIssueSummary`'s own counts.
KNOWN_DIAGNOSTIC_SEVERITY_HINTS = (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO)


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
    Slice 7 never constructs one in production code -- this shape
    exists for Slice 8's own detection logic to populate."""

    severity_hint: str
    code: str
    message: str
    location: IssueLocation | None = None
    suggested_action: str | None = None


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

    `unit`/`interval_seconds`/`confirmed` are plain, uninterpreted
    ECHOES of the stored `TimeAxisConfiguration`'s own same-named
    fields (verbatim, never recalculated) -- included so a caller (the
    frontend's own edit form in particular) can prefill from the one
    read endpoint this framework exposes, without a second "give me the
    raw stored configuration" API. This is presentation convenience
    only, not new derived state: exactly like `column_indices` above,
    which was already an echo rather than a calculation."""

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


def resolve_status(
    configuration: TimeAxisConfiguration | None,
    *,
    columns_still_time_axis: bool,
    diagnostics: list[TimeAxisDiagnostic],
) -> str:
    """Pure function computing the user-facing `status` (§15.3) from
    already-known inputs -- no I/O, no session access (the caller,
    `app.services.time_axis_service`, resolves `columns_still_time_axis`
    against the CURRENT `column_roles` state before calling this).

    Precedence, most specific first:
    1. No configuration at all -> `unconfigured`.
    2. The stored configuration explicitly used the `unsupported`
       interpreter, OR its own columns no longer all carry the
       Time Axis role (staleness, see this module's own docstring) ->
       `unsupported`.
    3. `family == FAMILY_SAMPLE_INDEX` and
       `provenance == PROVENANCE_INDEX_ONLY` -> `index_fallback`.
    4. Any diagnostics present and not yet confirmed -> `needs_attention`
       (see `STATUS_REVIEW_REQUIRED`'s own docstring for why THAT status,
       not this one, is what Slice 8 will use for an actionable
       suggestion specifically -- Slice 7 never produces a diagnostic
       that could make that distinction, so this function never returns
       `review_required`).
    5. `confirmed` -> `confirmed`.
    6. Otherwise -> `detected`.
    """
    if configuration is None:
        return STATUS_UNCONFIGURED
    if configuration.interpreter_id == INTERPRETER_ID_UNSUPPORTED or not columns_still_time_axis:
        return STATUS_UNSUPPORTED
    if configuration.family == FAMILY_SAMPLE_INDEX and configuration.provenance == PROVENANCE_INDEX_ONLY:
        return STATUS_INDEX_FALLBACK
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
) -> TimeAxisInterpretationResult:
    """The one place `TimeAxisInterpretationResult` is assembled, so
    `status`/`confirmation_required` can never drift out of sync with
    each other across call sites."""
    diagnostics = diagnostics or []
    status = resolve_status(configuration, columns_still_time_axis=columns_still_time_axis, diagnostics=diagnostics)
    return TimeAxisInterpretationResult(
        status=status,
        family=configuration.family if configuration else None,
        provenance=configuration.provenance if configuration else None,
        interpreter_id=configuration.interpreter_id if configuration else None,
        column_indices=configuration.column_indices if configuration else (),
        confidence=CONFIDENCE_UNKNOWN,
        diagnostics=diagnostics,
        preview_supported=False,
        confirmation_required=bool(configuration and not configuration.confirmed),
        unit=configuration.unit if configuration else None,
        interval_seconds=configuration.interval_seconds if configuration else None,
        confirmed=configuration.confirmed if configuration else False,
    )
