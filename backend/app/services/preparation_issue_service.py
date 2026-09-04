"""Preparation Readiness Issue production (CSV/Excel ingestion Slices 6
and 9, DEC-072).

Owns the ONLY seam that turns current preparation state into
`app.domain.preparation_issue.PreparationIssue` findings.
`collect_preparation_issues()` (Slice 6, UNCHANGED by Slice 9) stays a
short, linear function checking a handful of already-known
CONFIGURATION facts (is a header selected? is a data region set?) --
never data interpretation. Every issue it produces is still
`SEVERITY_INFO` -- purely descriptive, never implying a source is
invalid or blocked (task's own explicit "do NOT silently decide that a
header is mandatory" guardrail).

UAT fix (2026-09-04): the third Slice 6 issue, `column_roles_unassigned`
("N columns have no assigned role"), is retired -- the three-role
column model (`not_assigned`/`time_axis`/`waveform`) makes
`not_assigned` a normal, INTENTIONAL final state, not incomplete
configuration, so a column remaining `not_assigned` is no longer
informative to flag at all. See `app.domain.preparation_issue`'s own
module docstring for the full rationale.

`build_issue_summary()` (the ONE entry point `GET .../issues` calls)
now ALSO calls `app.services.readiness_service.collect_readiness_
issues()` -- the genuinely full Readiness Validator this module's own
docstring used to describe as "a later slice." That module owns ALL
real `blocking`/`warning` policy (time-axis coherence, time-axis cell
validity, waveform cell validity); this module still only ever produces
`SEVERITY_INFO` findings of its own. Both lists are merged into ONE
`PreparationIssueSummary` via `summarize_issues()` -- there is still
only one issue TRANSPORT model, never two independently-shaped ones.

No caching: `build_issue_summary()` recomputes the FULL issue list
(Slice 6 + Slice 9) on every call, directly from the session's own
current overlay state -- nothing is ever stored, so `evaluated_revision`
always equals `current_revision` and `is_stale` is always `False`
(see `app.domain.preparation_issue`'s own module docstring for why
those fields exist anyway, and `app.services.readiness_service`'s own
docstring for why a cache was deliberately not introduced there
either, despite doing meaningfully more work than Slice 6's own two
dict lookups).
"""

from __future__ import annotations

from app.domain.preparation_issue import (
    ISSUE_DATA_REGION_UNCONFIGURED,
    ISSUE_HEADER_NOT_SELECTED,
    SEVERITY_INFO,
    IssueLocation,
    PreparationIssue,
    PreparationIssueSummary,
    summarize_issues,
)
from app.domain.preparation_session import PreparationSession
from app.services.errors import SourceNotFoundError, WorksheetNotSelectedError
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.readiness_service import collect_readiness_issues


def _resolve_worksheet_index(session: PreparationSession) -> int | None:
    """`None` for CSV. For Excel, the currently selected worksheet --
    never guessed: raises `WorksheetNotSelectedError` for a multi-sheet
    workbook with no selection yet, exactly mirroring the preview and
    working-overlay-mutation endpoints' own rule, so an issue's own
    `location.worksheet_index` always refers to the same worksheet the
    rest of the workspace is currently showing."""
    worksheets = session.summary.worksheets
    if not worksheets:
        return None
    if session.summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before requesting its readiness issues."
        )
    return session.summary.selected_worksheet_index


def collect_preparation_issues(session: PreparationSession, worksheet_index: int | None) -> list[PreparationIssue]:
    """Deliberately conservative, informational-only issue set -- see
    this module's own docstring. Every issue returned here is
    `SEVERITY_INFO`; none implies the source is invalid or blocked."""
    overlay = session.working_overlay
    issues: list[PreparationIssue] = []

    if overlay.header_row.get(worksheet_index) is None:
        issues.append(
            PreparationIssue(
                severity=SEVERITY_INFO,
                code=ISSUE_HEADER_NOT_SELECTED,
                message="No header row is selected -- column labels use plain spreadsheet letters.",
                location=IssueLocation(worksheet_index=worksheet_index, field="header"),
                suggested_action="Select a header row in the Structure panel if this source has one.",
            )
        )

    if overlay.data_region.get(worksheet_index) is None:
        issues.append(
            PreparationIssue(
                severity=SEVERITY_INFO,
                code=ISSUE_DATA_REGION_UNCONFIGURED,
                message="No data region is set -- the entire source is currently treated as active.",
                location=IssueLocation(worksheet_index=worksheet_index, field="data_region"),
                suggested_action="Narrow the data region in the Structure panel if only part of the source is relevant.",
            )
        )

    return issues


def build_issue_summary(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> PreparationIssueSummary:
    """Resolve the session, collect its current issues, and summarize
    them -- the single entry point `app.api.v1.preparation_sources`'s
    own `GET .../issues` endpoint calls. Raises `SourceNotFoundError` if
    no such preparation session exists, or `WorksheetNotSelectedError`
    for an Excel source with no worksheet chosen yet (see
    `_resolve_worksheet_index`'s own docstring) -- both ordinary
    `ImportServiceError` runtime failures, never a `PreparationIssue`
    (task's own explicit "these must not appear as PreparationIssue"
    rule)."""
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(f"No preparation source '{source_id}' in workspace '{workspace_id}'.")

    worksheet_index = _resolve_worksheet_index(session)
    issues = collect_preparation_issues(session, worksheet_index)
    issues += collect_readiness_issues(
        session, worksheet_index, workspace_id=workspace_id, source_id=source_id, registry=registry,
    )
    return summarize_issues(source_id=source_id, revision=session.working_overlay.revision, issues=issues)
