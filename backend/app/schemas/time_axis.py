"""API request/response DTOs for the Time-Axis interpretation FRAMEWORK
(CSV/Excel ingestion Slices 7-8B, DEC-072).

Mirrors `app.schemas.preparation_issue`'s own wire-shape pattern
verbatim: never adds a field the domain layer does not already carry,
and never loosens `family`/`provenance`/`status`/`confidence` beyond
`app.domain.time_axis`'s own closed sets. `TimeAxisDiagnosticOut` reuses
`IssueLocationOut` directly (the same `IssueLocation` value object
`app.domain.time_axis.TimeAxisDiagnostic` itself reuses) -- one location
shape on the wire, not two independently-evolving ones.

Slice 8A adds: `options`/`ambiguity`/`details` echoes on the existing
shapes (never a breaking change -- every new field has a default), plus
the dry-run `TimeAxisInterpretRequest`/`TimeAxisInterpretPreviewOut`
pair for `POST .../working/time-axis/interpret`
(`app.services.time_axis_service.interpret_time_axis`) and
`TimeAxisPreviewRowOut` for its own bounded preview rows.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.time_axis import (
    TimeAxisDiagnostic,
    TimeAxisInterpretationResult,
    TimeAxisPreviewRow,
)
from app.schemas.preparation_issue import IssueLocationOut
from app.services.time_axis_service import TimeAxisInterpretPreview


class TimeAxisDiagnosticOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity_hint: str
    code: str
    message: str
    location: IssueLocationOut | None = None
    suggested_action: str | None = None
    ambiguity: str = "unambiguous"
    details: dict[str, Any] | None = None

    @classmethod
    def from_domain(cls, diagnostic: TimeAxisDiagnostic) -> "TimeAxisDiagnosticOut":
        return cls(
            severity_hint=diagnostic.severity_hint,
            code=diagnostic.code,
            message=diagnostic.message,
            location=IssueLocationOut.from_domain(diagnostic.location) if diagnostic.location is not None else None,
            suggested_action=diagnostic.suggested_action,
            ambiguity=diagnostic.ambiguity,
            details=diagnostic.details,
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
    options: dict[str, Any] = Field(default_factory=dict)

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
            options=dict(result.options),
        )


class TimeAxisConfigurationRequest(BaseModel):
    """Body of `PUT .../working/time-axis`. `interpreter_id` is optional
    -- when omitted, the service resolves to `manual` (never silently to
    a real detecting interpreter -- see
    `app.services.time_axis_service.resolve_interpreter`'s own
    docstring).

    `family`/`provenance` are REQUIRED only for the `manual` interpreter
    (`InvalidTimeAxisConfigurationError` if missing or not one of
    `app.domain.time_axis`'s own known closed sets); for a SAMPLE
    interpreter (Slice 8A's `absolute_datetime`/`split_date_time`,
    Slice 8B's `elapsed_numeric`/`sample_index`) they are optional
    hints only -- the interpreter's own `detect()` always computes the
    real values from the actual sampled data. `options` (Slice 8A)
    carries interpreter-specific settings -- e.g. `{"date_order":
    "dmy"}` -- and is always optional; omitting it (or leaving
    `date_order` as `"auto"`/absent) means "not yet resolved," exactly
    like every other unconfirmed state in this framework. `unit`
    (Slice 8B, `elapsed_numeric` only) must be one of
    `app.domain.time_axis.KNOWN_ELAPSED_UNITS` if given at all --
    omitting it saves a `review_required` configuration, exactly like
    an unresolved date order. `interval_seconds` (Slice 8B,
    `sample_index` only) is entirely optional -- omitting it means
    index-only, the approved fallback, never an error."""

    column_indices: list[int]
    family: str | None = None
    provenance: str | None = None
    unit: str | None = None
    interval_seconds: float | None = None
    confirmed: bool = False
    interpreter_id: str | None = None
    options: dict[str, Any] | None = None


class TimeAxisInterpreterOut(BaseModel):
    """One entry of `GET .../time-axis/interpreters`."""

    interpreter_id: str


class TimeAxisInterpretRequest(BaseModel):
    """Body of `POST .../working/time-axis/interpret` (Slice 8A, task
    §T) -- a dry-run detect/preview action. `interpreter_id` is REQUIRED
    here (unlike the PUT above) since there is nothing sensible to
    "auto-resolve" for a preview the caller is explicitly asking for by
    trying a specific interpreter; `options` carries the same
    interpreter-specific settings as the PUT body (e.g. an explicit
    `date_order` the user is trying before committing to it). `unit`/
    `interval_seconds` (Slice 8B) let a caller try a specific elapsed
    unit or sample-index interval before committing to it via the real
    PUT -- the same pre-existing fields the PUT body already has."""

    column_indices: list[int]
    interpreter_id: str
    unit: str | None = None
    interval_seconds: float | None = None
    options: dict[str, Any] | None = None


class TimeAxisPreviewRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    original: list[Any]
    interpreted: str | None = None

    @classmethod
    def from_domain(cls, row: TimeAxisPreviewRow) -> "TimeAxisPreviewRowOut":
        return cls(row_number=row.row_number, original=list(row.original), interpreted=row.interpreted)


class TimeAxisInterpretPreviewOut(BaseModel):
    """Response of `POST .../working/time-axis/interpret` -- nothing
    here is ever stored; see
    `app.services.time_axis_service.TimeAxisInterpretPreview`'s own
    docstring."""

    interpreter_id: str
    column_indices: list[int]
    family: str | None = None
    provenance: str | None = None
    confidence: str
    diagnostics: list[TimeAxisDiagnosticOut] = Field(default_factory=list)
    resolved_options: dict[str, Any] = Field(default_factory=dict)
    resolved_unit: str | None = None
    resolved_interval_seconds: float | None = None
    preview_rows: list[TimeAxisPreviewRowOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, preview: TimeAxisInterpretPreview) -> "TimeAxisInterpretPreviewOut":
        return cls(
            interpreter_id=preview.interpreter_id,
            column_indices=list(preview.column_indices),
            family=preview.family,
            provenance=preview.provenance,
            confidence=preview.confidence,
            diagnostics=[TimeAxisDiagnosticOut.from_domain(d) for d in preview.diagnostics],
            resolved_options=dict(preview.resolved_options),
            resolved_unit=preview.resolved_unit,
            resolved_interval_seconds=preview.resolved_interval_seconds,
            preview_rows=[TimeAxisPreviewRowOut.from_domain(r) for r in preview.preview_rows],
        )
