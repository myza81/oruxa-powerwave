"""Preparation Readiness Issue domain model (CSV/Excel ingestion Slice 6, DEC-072).

This slice's own explicit scope: the ISSUE LANGUAGE AND TRANSPORT MODEL
that a future, full Powerwave Readiness Validator will eventually
produce findings through -- NOT that validator itself. Nothing in this
module parses a time axis, validates a waveform value, or decides
whether a preparation source is "ready." See
`app.services.preparation_issue_service`'s own module docstring for
exactly which (deliberately conservative, informational-only) issues
Slice 6 itself produces.

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
ISSUE_COLUMN_ROLES_UNASSIGNED = "column_roles_unassigned"
KNOWN_ISSUE_CODES = (
    ISSUE_HEADER_NOT_SELECTED,
    ISSUE_DATA_REGION_UNCONFIGURED,
    ISSUE_COLUMN_ROLES_UNASSIGNED,
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
    -- Slice 6 always computes issues live, so `evaluated_revision ==
    current_revision` and `is_stale is False` on every response."""

    source_id: str
    evaluated_revision: int
    current_revision: int
    is_stale: bool
    blocking_count: int
    warning_count: int
    info_count: int
    issues: list[PreparationIssue] = field(default_factory=list)


def summarize_issues(
    *, source_id: str, revision: int, issues: list[PreparationIssue],
) -> PreparationIssueSummary:
    """Build a `PreparationIssueSummary` from an already-collected issue
    list -- the one place severity counts are computed, so
    `app.services.preparation_issue_service` never has to re-derive
    them independently."""
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
        issues=list(issues),
    )
