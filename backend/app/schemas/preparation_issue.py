"""API response DTOs for Preparation Readiness Issues (CSV/Excel ingestion Slice 6, DEC-072).

Mirrors `app.domain.preparation_issue`'s own shapes for the wire --
never adds fields the domain layer does not already carry, and never
loosens `severity`/`code` to anything but the domain module's own
closed sets (`KNOWN_SEVERITIES`/`KNOWN_ISSUE_CODES`). See that module's
own docstring for the full "issue vs exception" architectural
distinction this schema exists to transport, never to blur --
`GET .../preparation-sources/{source_id}/issues` always returns `200
OK` with this shape; an actual runtime/request failure (source not
found, worksheet not selected) still raises an `ImportServiceError`
subclass and is still mapped to an HTTP error response the ordinary
way, exactly like every other preparation-source endpoint.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.preparation_issue import IssueLocation, PreparationIssue, PreparationIssueSummary


class IssueLocationOut(BaseModel):
    """Every field is optional and independent -- a dataset-level issue
    carries an instance with every field `None`, never omits the
    object entirely (so the frontend can rely on its shape being
    present whenever `PreparationIssueOut.location` is not `null`)."""

    model_config = ConfigDict(from_attributes=True)

    worksheet_index: int | None = None
    row_number: int | None = None
    column_index: int | None = None
    field: str | None = None

    @classmethod
    def from_domain(cls, location: IssueLocation) -> "IssueLocationOut":
        return cls(
            worksheet_index=location.worksheet_index,
            row_number=location.row_number,
            column_index=location.column_index,
            field=location.field,
        )


class PreparationIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity: str
    code: str
    message: str
    location: IssueLocationOut | None = None
    suggested_action: str | None = None
    details: dict[str, Any] | None = None

    @classmethod
    def from_domain(cls, issue: PreparationIssue) -> "PreparationIssueOut":
        return cls(
            severity=issue.severity,
            code=issue.code,
            message=issue.message,
            location=IssueLocationOut.from_domain(issue.location) if issue.location is not None else None,
            suggested_action=issue.suggested_action,
            details=issue.details,
        )


class PreparationIssueSummaryOut(BaseModel):
    """`GET .../preparation-sources/{source_id}/issues` (Slice 6, now
    carrying real Slice 9 readiness policy too -- see
    `app.services.readiness_service`'s own module docstring).
    `evaluated_revision`/`current_revision` are always equal and
    `is_stale` is always `False` today -- see
    `app.domain.preparation_issue`'s own module docstring for why the
    fields exist regardless (future-caching compatibility, not a
    behavior either slice exercises). `is_ready` (Slice 9) is
    `blocking_count == 0` -- warnings and info never affect it."""

    source_id: str
    evaluated_revision: int
    current_revision: int
    is_stale: bool
    blocking_count: int
    warning_count: int
    info_count: int
    is_ready: bool = False
    issues: list[PreparationIssueOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, summary: PreparationIssueSummary) -> "PreparationIssueSummaryOut":
        return cls(
            source_id=summary.source_id,
            evaluated_revision=summary.evaluated_revision,
            current_revision=summary.current_revision,
            is_stale=summary.is_stale,
            blocking_count=summary.blocking_count,
            warning_count=summary.warning_count,
            info_count=summary.info_count,
            is_ready=summary.is_ready,
            issues=[PreparationIssueOut.from_domain(i) for i in summary.issues],
        )
