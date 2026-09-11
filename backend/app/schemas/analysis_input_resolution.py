"""Wire shapes for the Analysis Guardrail Slice 2 read-only Analysis
Input Resolution endpoint -- thin exposure of
`app.services.analysis_input_resolution_service.resolve_analysis_inputs()`,
never a reimplementation of its role-matching/timebase logic. A future
analysis page (Phasor first) receives exactly this shape and must never
reproduce engineering rules of its own -- backend-authoritative role
resolution, frontend presentation only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut

ResolutionStatus = Literal["resolved", "needs_configuration", "ambiguous", "not_applicable"]


class RoleSpecOut(BaseModel):
    role_key: str
    engineering_type: str
    phase: str
    representation: str


class AnalysisInputResolutionOut(BaseModel):
    status: ResolutionStatus
    analysis_kind: str
    mode: str
    engineering_context_id: str
    required_roles: list[str]
    required_role_specs: list[RoleSpecOut]
    resolved_roles: dict[str, ChannelRefOut]
    missing_roles: list[str]
    missing_role_reasons: dict[str, str]
    ambiguous_roles: dict[str, list[ChannelRefOut]]
    numerically_ready: bool
    reason_code: str | None
    message: str
