"""Preparation Readiness Issue domain model (CSV/Excel ingestion Slices
6 and 9, DEC-072).

Slice 6's own explicit scope was the ISSUE LANGUAGE AND TRANSPORT MODEL
a future, full Powerwave Readiness Validator would eventually produce
findings through -- not that validator itself. This module still parses
nothing and validates no waveform value directly; it stays the plain,
unvalidated SHAPE every producer returns through. Slice 9 is that
"future validator" arriving: `app.services.readiness_service` is the
new seam that actually decides blocking/warning/info for time-axis
coherence, time-axis cell values, and waveform cell values, alongside
Slice 6's own unchanged configuration-only checks (still produced by
`app.services.preparation_issue_service.collect_preparation_issues()`)
-- see that new service module's own docstring for the full policy.
`PreparationIssueSummary.is_ready` (Slice 9) is the one readiness
verdict this model now carries; see that field's own docstring.

Critical distinction this module exists to preserve (task's own
explicit architectural rule): a `PreparationIssue` is a STRUCTURED
FINDING about the current preparation state, never an exception.
Runtime/request failures (source not found, malformed upload, invalid
coordinates, a workbook that will not open) remain
`app.services.errors.ImportServiceError`'s job, completely unchanged by
this slice -- a `PreparationIssue` is never raised, and
`ImportServiceError` never carries one. The two taxonomies are parallel
and do not overlap:

    Runtime/API failure          Dataset preparation/readiness finding
    (something went wrong        (the current, successfully-loaded
     handling the request)        state has something worth noting)
            |                             |
    ImportServiceError            PreparationIssue
    (raised, becomes an            (returned in a list, never raised,
     HTTP error response)           becomes part of a 200 OK response)

Severity (`KNOWN_SEVERITIES`) is a three-tier CAPABILITY this slice
establishes, not a policy this slice exercises in full: `blocking` and
`warning` exist as valid values a future validator can use, but Slice 6
itself only ever produces `info`-level findings (see the issue-
production module for why) -- never invents that something is
`blocking` or a `warning` without owner-approved validation semantics
behind it (task's own explicit guardrail).

Issue codes are stable, machine-readable identifiers (never a free-form
string invented ad hoc at each call site) -- see `KNOWN_ISSUE_CODES`.
Only the codes Slice 6 itself actually produces are defined here; this
is deliberately NOT a preemptive registry of every future validation
finding (task's own "do not prematurely define the whole future
validation code list" guardrail).

Location (`IssueLocation`) is a set of OPTIONAL dimensions
(`worksheet_index`/`row_number`/`column_index`/`field`) -- a
dataset-level issue is valid and simply carries no location at all
(every field `None`); nothing forces an issue to point at a cell.

`suggested_action` is advisory text only -- reading it, or acting on it,
never happens automatically; nothing in this codebase ever auto-fixes a
`PreparationIssue`.

`details` is a small, bounded, JSON-safe dict for the rare case a
message benefits from one or two extra structured values (e.g. an
unassigned-column count) -- never a place to carry row lists or other
unbounded data (task's own explicit "keep issue transport bounded"
guardrail).

Revision linkage (`PreparationIssueSummary.evaluated_revision`/
`current_revision`/`is_stale`): Slice 6 derives issues LIVE on every
request (see the issue-production module's own docstring for why no
caching was introduced) -- `evaluated_revision` and `current_revision`
are therefore always equal and `is_stale` is always `False` today. The
fields exist now so a future caching layer can represent staleness
without a wire-shape change -- not because Slice 6 itself needs them
to differ yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Task's own approved three-tier severity model. `blocking`/`warning`
#: are capabilities this slice establishes for a FUTURE validator --
#: Slice 6's own issue production (see
#: app.services.preparation_issue_service) only ever emits `info`.
SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
KNOWN_SEVERITIES = (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO)

#: Stable, machine-readable issue codes actually produced by Slice 6's
#: own conservative issue-production seam -- see
#: app.services.preparation_issue_service.collect_preparation_issues()
#: for exactly when each fires. Deliberately not a preemptive list of
#: every future validator finding.
ISSUE_HEADER_NOT_SELECTED = "header_not_selected"
ISSUE_DATA_REGION_UNCONFIGURED = "data_region_unconfigured"

#: UAT fix (2026-09-04): `ISSUE_COLUMN_ROLES_UNASSIGNED` (formerly
#: "column_roles_unassigned") is retired. The three-role simplification
#: makes `not_assigned` a normal, intentional, final state -- not
#: incomplete configuration -- so a column remaining `not_assigned` is
#: no longer worth flagging even at INFO severity (task's own explicit
#: "owner intent: unassigned columns are normal and intentional...
#: do not add a redundant 'unassigned columns' issue"). If every column
#: is `not_assigned`, readiness is already correctly blocked by the
#: MEANINGFUL issues (`time_axis_unconfigured`/`waveform_channel_
#: missing`), never by this one.

#: Slice 9 (Full Powerwave Readiness Validator, DEC-072) -- the real
#: BLOCKING/WARNING findings a stored preparation source may now carry,
#: produced by `app.services.readiness_service.collect_readiness_issues()`
#: (never by this module, which stays a pure, unvalidated data carrier --
#: see this module's own docstring). Genuinely NEW codes only; a
#: readiness finding whose condition ALREADY has an established
#: `app.domain.time_axis.DIAGNOSTIC_*` code (e.g. `time_goes_backward`,
#: `large_time_gap`, `missing_datetime_value`, `non_uniform_elapsed_interval`,
#: `repeated_timestamp_detected`, ...) is PROMOTED into a
#: `PreparationIssue` reusing that EXACT string verbatim (task's own
#: "reuse existing preparation/time diagnostic codes where it improves
#: clarity" instruction) -- deliberately NOT re-declared here a second
#: time, to avoid two independently-maintained copies of the same
#: string. `ISSUE_DIGITAL_VALUE_INVALID` is listed for the controlled
#: vocabulary but never actually PRODUCED this slice -- the column-role
#: model has no dedicated digital role yet (see
#: `app.services.readiness_service`'s own module docstring for why this
#: is deliberately deferred, not silently invented).
ISSUE_TIME_AXIS_UNCONFIGURED = "time_axis_unconfigured"
ISSUE_TIME_AXIS_UNSUPPORTED = "time_axis_unsupported"
ISSUE_TIME_AXIS_UNRESOLVED = "time_axis_unresolved"
#: Preparation Status integrity guardrail: a `manual` Time Axis
#: configuration is an engineer ASSERTION, never a real per-row reading
#: -- `app.domain.time_axis.is_time_axis_resolved()` and
#: `app.services.preparation_conversion_service.convert_preparation_
#: source()` already independently, unconditionally treat it as
#: never-eligible (confirmed or not; see those functions' own
#: docstrings) precisely because it can never actually reach Powerwave.
#: Before this fix, `readiness_service` never encoded that same
#: exclusion -- a saved `manual` configuration whose asserted family
#: happened to match the raw data closely enough to pass the full-region
#: cell scan could reach `is_ready=true`/"Ready for Powerwave" despite
#: being permanently un-convertible, a real inconsistency with export/
#: conversion's own established policy, not merely a confirmation-
#: wording gap.
ISSUE_TIME_AXIS_MANUAL_UNRESOLVED = "time_axis_manual_unresolved"
ISSUE_TIME_VALUE_MISSING = "time_value_missing"
ISSUE_TIME_VALUE_INVALID = "time_value_invalid"
ISSUE_WAVEFORM_CHANNEL_MISSING = "waveform_channel_missing"
ISSUE_WAVEFORM_VALUE_MISSING = "waveform_value_missing"
ISSUE_WAVEFORM_VALUE_INVALID = "waveform_value_invalid"
ISSUE_DIGITAL_VALUE_INVALID = "digital_value_invalid"
ISSUE_SAMPLE_INDEX_FALLBACK = "sample_index_fallback"
ISSUE_PARTIAL_TIME_REFERENCE = "partial_time_reference"
ISSUE_RECONSTRUCTED_TIME = "reconstructed_time"
ISSUE_USER_SPECIFIED_TIME = "user_specified_time"
ISSUE_TIMEZONE_UNSPECIFIED = "timezone_unspecified"

KNOWN_ISSUE_CODES = (
    ISSUE_HEADER_NOT_SELECTED,
    ISSUE_DATA_REGION_UNCONFIGURED,
    ISSUE_TIME_AXIS_UNCONFIGURED,
    ISSUE_TIME_AXIS_UNSUPPORTED,
    ISSUE_TIME_AXIS_UNRESOLVED,
    ISSUE_TIME_VALUE_MISSING,
    ISSUE_TIME_VALUE_INVALID,
    ISSUE_WAVEFORM_CHANNEL_MISSING,
    ISSUE_WAVEFORM_VALUE_MISSING,
    ISSUE_WAVEFORM_VALUE_INVALID,
    ISSUE_DIGITAL_VALUE_INVALID,
    ISSUE_SAMPLE_INDEX_FALLBACK,
    ISSUE_PARTIAL_TIME_REFERENCE,
    ISSUE_RECONSTRUCTED_TIME,
    ISSUE_USER_SPECIFIED_TIME,
    ISSUE_TIMEZONE_UNSPECIFIED,
)


@dataclass(slots=True, frozen=True)
class IssueLocation:
    """Where a `PreparationIssue` applies, if anywhere -- every field is
    optional and independent (task's own explicit "do not force every
    issue to point to a cell" guardrail). A dataset-level issue leaves
    every field `None`. `worksheet_index` is `None` for CSV (no
    worksheet dimension) or for a dataset-level Excel issue; `field` is
    a short, stable string naming a non-cell configuration surface
    (e.g. `"header"`, `"data_region"`, `"column_roles"`) rather than a
    free-form description."""

    worksheet_index: int | None = None
    row_number: int | None = None
    column_index: int | None = None
    field: str | None = None


@dataclass(slots=True, frozen=True)
class PreparationIssue:
    """One structured finding about the CURRENT preparation state --
    never raised, never a substitute for
    `app.services.errors.ImportServiceError`. `code` must be one of
    `KNOWN_ISSUE_CODES`; `severity` must be one of `KNOWN_SEVERITIES`
    (both enforced by whatever constructs this, e.g.
    `app.services.preparation_issue_service` -- this dataclass itself
    stays a plain, unvalidated data carrier, matching every other
    `app.domain` dataclass's own layering contract). `details` is a
    small, bounded, JSON-safe mapping -- never a place for row lists or
    other unbounded payloads."""

    severity: str
    code: str
    message: str
    location: IssueLocation | None = None
    suggested_action: str | None = None
    details: dict[str, Any] | None = None


@dataclass(slots=True)
class PreparationIssueSummary:
    """The full response shape for one preparation source's own current
    issue set. `evaluated_revision`/`current_revision`/`is_stale` exist
    for future-caching compatibility (see this module's own docstring)
    -- issues are always computed LIVE against the CURRENT
    `WorkingOverlay.revision` (Slice 6 and Slice 9 alike -- see
    `app.services.readiness_service`'s own module docstring for why no
    caching was introduced there either), so `evaluated_revision ==
    current_revision` and `is_stale is False` on every response today.

    `is_ready` (Slice 9) is the ONE readiness verdict Powerwave
    conversion (a LATER slice, not this one) would act on --
    `blocking_count == 0`, computed here so it can never drift out of
    sync with the counts above. Warnings and info findings never affect
    it (task's own explicit "warnings do not block" rule)."""

    source_id: str
    evaluated_revision: int
    current_revision: int
    is_stale: bool
    blocking_count: int
    warning_count: int
    info_count: int
    is_ready: bool = False
    issues: list[PreparationIssue] = field(default_factory=list)


def summarize_issues(
    *, source_id: str, revision: int, issues: list[PreparationIssue],
) -> PreparationIssueSummary:
    """Build a `PreparationIssueSummary` from an already-collected issue
    list -- the one place severity counts (and `is_ready`) are computed,
    so no caller ever has to re-derive them independently."""
    blocking_count = sum(1 for issue in issues if issue.severity == SEVERITY_BLOCKING)
    warning_count = sum(1 for issue in issues if issue.severity == SEVERITY_WARNING)
    info_count = sum(1 for issue in issues if issue.severity == SEVERITY_INFO)
    return PreparationIssueSummary(
        source_id=source_id,
        evaluated_revision=revision,
        current_revision=revision,
        is_stale=False,
        blocking_count=blocking_count,
        warning_count=warning_count,
        info_count=info_count,
        is_ready=blocking_count == 0,
        issues=list(issues),
    )
