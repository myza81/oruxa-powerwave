"""Wire shapes for the Phasor Analysis Slice 1 read-only, selected-time
endpoint -- thin exposure of
`app.services.phasor_analysis_service.compute_phasor_analysis()`, never
a reimplementation of its estimation/guardrail logic. Engineering units
only in this slice (no `unit_mode`/Per-Unit parameter -- deliberately
deferred, see that service module's own docstring).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut

PhasorAnalysisStatus = Literal["computed", "needs_configuration", "ambiguous", "not_applicable"]


class PhasorRoleResultOut(BaseModel):
    channel_ref: ChannelRefOut
    magnitude_rms: float
    unit: str
    angle_deg_absolute: float
    angle_deg_relative: float | None


class PhasorAnalysisResultOut(BaseModel):
    status: PhasorAnalysisStatus
    analysis_kind: str
    mode: str
    engineering_context_id: str
    analysis_time: float
    reference_frequency_hz: float | None
    window_seconds: float | None
    algorithm_version: str
    roles: dict[str, PhasorRoleResultOut]
    warnings: list[str]
    role_reasons: dict[str, str]
    reason_code: str | None
    message: str


#: Bay-centric aggregation wire shapes (Phasor UAT redesign; see
#: docs/project-memory/PHASOR_ANALYSIS.md's own "Bay-centric Phasor
#: Diagram" section) -- thin exposure of
#: `app.services.phasor_analysis_service.compute_phasor_diagram()`.
#: Deliberately a SEPARATE result shape from `PhasorAnalysisResultOut`
#: above (never reused/overloaded), since the two endpoints answer
#: different questions: one role for one requirement vs. all six roles
#: for one Engineering Context at once.
PhasorDiagramRoleStatus = Literal["available", "missing", "needs_configuration", "ambiguous", "not_eligible"]
PhasorDiagramStatus = Literal["computed", "needs_configuration"]


class PhasorDiagramRoleResultOut(BaseModel):
    status: PhasorDiagramRoleStatus
    channel_ref: ChannelRefOut | None
    magnitude_rms: float | None
    unit: str | None
    angle_deg_absolute: float | None
    angle_deg_relative: float | None
    reason_code: str | None


class PhasorDiagramResultOut(BaseModel):
    status: PhasorDiagramStatus
    engineering_context_id: str
    analysis_time: float
    reference_frequency_hz: float | None
    window_seconds: float | None
    algorithm_version: str
    roles: dict[str, PhasorDiagramRoleResultOut]
    warnings: list[str]
    reason_code: str | None
    message: str
