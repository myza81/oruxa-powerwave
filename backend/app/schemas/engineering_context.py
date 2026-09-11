"""Wire shapes for the Analysis Guardrail Slice 1 Engineering Context
API -- thin exposure of `app.services.engineering_context_service`,
never a reimplementation of its validation. Mirrors
`app.schemas.measurement_group`'s own shape/conventions.

Workspace-scoped (deliberately NOT source-scoped, unlike Measurement
Groups -- an Engineering Context may span multiple sources; see
`app.domain.engineering_context`'s own module docstring). Human-facing
`display_name` is a label only -- every request/response identifies a
context by its own opaque `id`, never by name.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefIn, ChannelRefOut

ContextStatus = Literal["suggested", "confirmed", "needs_review", "manual"]
Phase = Literal["A", "B", "C", "N", "AB", "BC", "CA", "unknown", "not_applicable"]
PhaseSource = Literal["engineer_confirmed", "manual", "structured_metadata", "detected_from_name", "unknown"]


class EngineeringContextMemberIn(BaseModel):
    channel_ref: ChannelRefIn
    phase: Phase = "unknown"
    phase_source: PhaseSource = "unknown"
    original_phase_label: str | None = None


class EngineeringContextMemberOut(BaseModel):
    channel_ref: ChannelRefOut
    phase: Phase
    phase_source: PhaseSource
    original_phase_label: str | None


class EngineeringContextOut(BaseModel):
    id: str
    workspace_id: str
    display_name: str
    members: list[EngineeringContextMemberOut]
    status: ContextStatus
    created_at: datetime | None


class EngineeringContextCreateRequest(BaseModel):
    display_name: str
    members: list[EngineeringContextMemberIn] = []
    status: ContextStatus = "manual"


class EngineeringContextUpdateRequest(BaseModel):
    """Partial update -- only supplied fields change. `members`, if
    supplied, is a FULL replace of membership (never a merge), mirroring
    `MeasurementGroupUpdateRequest`'s own `channel_refs` contract."""

    display_name: str | None = None
    status: ContextStatus | None = None
    members: list[EngineeringContextMemberIn] | None = None


class EngineeringContextMemberPhaseUpdateRequest(BaseModel):
    """Body for the dedicated per-member phase-correction endpoint --
    the manual-correction path an engineer uses to confirm or fix one
    member's own phase without resending the whole membership list.
    Always persisted as `phase_source="engineer_confirmed"` server-side
    (see `engineering_context_service.update_member_phase()`'s own
    docstring) -- this request body never lets the caller claim a
    different provenance for what is, by construction, an explicit
    engineer action."""

    channel_ref: ChannelRefIn
    phase: Phase
    original_phase_label: str | None = None


class SuggestEngineeringContextsRequest(BaseModel):
    """Empty body -- POST .../engineering-contexts/suggest takes no
    parameters; mirrors `SuggestGroupsRequest`'s own explicit-action-shape
    rationale."""
