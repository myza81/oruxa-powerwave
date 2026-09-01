"""API request/response DTOs for the Time-Axis interpretation FRAMEWORK
(CSV/Excel ingestion Slice 7, DEC-072).

Mirrors `app.schemas.preparation_issue`'s own wire-shape pattern
verbatim: never adds a field the domain layer does not already carry,
and never loosens `family`/`provenance`/`status`/`confidence` beyond
`app.domain.time_axis`'s own closed sets. `TimeAxisDiagnosticOut` reuses
`IssueLocationOut` directly (the same `IssueLocation` value object
`app.domain.time_axis.TimeAxisDiagnostic` itself reuses) -- one location
shape on the wire, not two independently-evolving ones.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.time_axis import (
    TimeAxisDiagnostic,
    TimeAxisInterpretationResult,
)
from app.schemas.preparation_issue import IssueLocationOut


class TimeAxisDiagnosticOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity_hint: str
    code: str
    message: str
    location: IssueLocationOut | None = None
    suggested_action: str | None = None

    @classmethod
    def from_domain(cls, diagnostic: TimeAxisDiagnostic) -> "TimeAxisDiagnosticOut":
        return cls(
            severity_hint=diagnostic.severity_hint,
            code=diagnostic.code,
            message=diagnostic.message,
            location=IssueLocationOut.from_domain(diagnostic.location) if diagnostic.location is not None else None,
            suggested_action=diagnostic.suggested_action,
        )


class TimeAxisInterpretationResultOut(BaseModel):
    """`GET .../preparation-sources/{source_id}/time-axis` (also returned
    by the PUT/DELETE mutation endpoints, mirroring
    `WorkingOverlaySummaryOut`'s own "every mutation returns the fresh
    summary" convention). Always derived live -- never itself a stored
    object (see `app.services.time_axis_service`'s own module
    docstring)."""

    status: str
    family: str | None = None
    provenance: str | None = None
    interpreter_id: str | None = None
    column_indices: list[int] = Field(default_factory=list)
    confidence: str
    diagnostics: list[TimeAxisDiagnosticOut] = Field(default_factory=list)
    preview_supported: bool
    confirmation_required: bool
    unit: str | None = None
    interval_seconds: float | None = None
    confirmed: bool = False

    @classmethod
    def from_domain(cls, result: TimeAxisInterpretationResult) -> "TimeAxisInterpretationResultOut":
        return cls(
            status=result.status,
            family=result.family,
            provenance=result.provenance,
            interpreter_id=result.interpreter_id,
            column_indices=list(result.column_indices),
            confidence=result.confidence,
            diagnostics=[TimeAxisDiagnosticOut.from_domain(d) for d in result.diagnostics],
            preview_supported=result.preview_supported,
            confirmation_required=result.confirmation_required,
            unit=result.unit,
            interval_seconds=result.interval_seconds,
            confirmed=result.confirmed,
        )


class TimeAxisConfigurationRequest(BaseModel):
    """Body of `PUT .../working/time-axis`. `family`/`provenance` must
    each be one of `app.domain.time_axis`'s own known closed sets
    (`InvalidTimeAxisConfigurationError` otherwise); `interpreter_id` is
    optional -- when omitted, the service resolves one automatically
    (task's own "avoid a misleading Auto Detect" guardrail applies to
    UI copy, not to this always-explicit `family`/`provenance` input:
    the caller still states the family/provenance directly, only the
    interpreter routing itself is implicit for the single `manual`
    interpreter Slice 7 registers)."""

    column_indices: list[int]
    family: str
    provenance: str
    unit: str | None = None
    interval_seconds: float | None = None
    confirmed: bool = False
    interpreter_id: str | None = None


class TimeAxisInterpreterOut(BaseModel):
    """One entry of `GET .../time-axis/interpreters`."""

    interpreter_id: str
