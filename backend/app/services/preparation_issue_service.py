"""Preparation Readiness Issue production (CSV/Excel ingestion Slice 6, DEC-072).

Owns the ONLY seam that turns current preparation state into
`app.domain.preparation_issue.PreparationIssue` findings. Deliberately
NOT a rules engine: `collect_preparation_issues()` is a short, linear
function checking a handful of already-known CONFIGURATION facts (is a
header selected? is a data region set? are all columns classified?) --
never data interpretation (no time-axis parsing, no value validation,
no monotonicity/duplicate-timestamp/missing-sample analysis). Those
belong to a later, genuinely full Readiness Validator slice; this one
proves the issue-transport plumbing works end to end using only issues
that are safe to state today.

Every issue this function produces is `SEVERITY_INFO` -- purely
descriptive, never implying that a source is invalid or blocked from
some future conversion (task's own explicit "do NOT silently decide
that a header is mandatory" / "do NOT silently decide that multiple
time-axis columns are invalid" guardrails). If a genuinely new product
rule is ever owner-approved to raise one of these to `warning` or
`blocking`, that is a `DECISIONS.md`-worthy change, not a quiet
severity bump here.

No caching: `build_issue_summary()` recomputes the issue list on every
call, directly from the session's own current overlay state --
`app.domain.preparation_session.PreparationSession.working_overlay`
never needs a special "recompute issues" trigger, because nothing is
ever stored. This means `evaluated_revision` always equals
`current_revision` and `is_stale` is always `False` today (see
`app.domain.preparation_issue`'s own module docstring for why those
fields exist anyway) -- recomputing three dict lookups plus, at most,
one already-memoized total-count check is cheap enough that a cache
would add complexity for no measurable benefit at this scale (task's
own "do not over-engineer caching" guidance).

Column-count awareness reuses the exact same helpers
`app.services.working_overlay_service` already built
(`ensure_csv_totals_cached` for CSV; the selected worksheet's own
best-effort `WorksheetInfo.column_count` for Excel) -- never a third,
possibly-divergent column-counting implementation. When that total is
genuinely unknown (an Excel worksheet with no cheap dimension hint),
the column-roles issue is simply skipped rather than fabricated.
"""

from __future__ import annotations

from app.domain.preparation_issue import (
    ISSUE_COLUMN_ROLES_UNASSIGNED,
    ISSUE_DATA_REGION_UNCONFIGURED,
    ISSUE_HEADER_NOT_SELECTED,
    SEVERITY_INFO,
    IssueLocation,
    PreparationIssue,
    PreparationIssueSummary,
    summarize_issues,
)
from app.domain.preparation_session import PreparationSession
from app.domain.working_overlay import ROLE_UNKNOWN
from app.services.errors import SourceNotFoundError, WorksheetNotSelectedError
from app.services.preparation_preview_service import ensure_csv_totals_cached
from app.services.preparation_session_registry import PreparationSessionRegistry


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


def _known_column_count(session: PreparationSession, worksheet_index: int | None) -> int | None:
    if worksheet_index is None:
        ensure_csv_totals_cached(session)
        return session.cached_column_count
    return session.summary.worksheets[worksheet_index].column_count


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

    column_count = _known_column_count(session, worksheet_index)
    if column_count:
        unassigned_count = sum(
            1 for c in range(column_count)
            if overlay.column_roles.get((worksheet_index, c), ROLE_UNKNOWN) == ROLE_UNKNOWN
        )
        if unassigned_count > 0:
            issues.append(
                PreparationIssue(
                    severity=SEVERITY_INFO,
                    code=ISSUE_COLUMN_ROLES_UNASSIGNED,
                    message=f"{unassigned_count} of {column_count} column(s) have no assigned role.",
                    location=IssueLocation(worksheet_index=worksheet_index, field="column_roles"),
                    suggested_action="Assign roles to the remaining columns in the Structure panel.",
                    details={"unassigned_count": unassigned_count, "total_columns": column_count},
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
    return summarize_issues(source_id=source_id, revision=session.working_overlay.revision, issues=issues)
