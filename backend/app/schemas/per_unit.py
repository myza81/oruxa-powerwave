"""Wire shapes for the Phase 5C Per-Unit Measurement Mode API (DEC-049).

Reuses `ChannelRefIn`/`ChannelRefOut` from app.schemas.calculated_channel
directly (section 57's one structured channel reference, never a second
wire type for the same identity).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.per_unit import PerUnitBaseProfile
from app.schemas.calculated_channel import ChannelRefIn, ChannelRefOut


class PerUnitProfileBaseFields(BaseModel):
    """Shared base-configuration fields for create/update requests --
    `None`/`None` for a value+unit pair is the valid "not yet configured"
    state; a partially-filled pair (one set, one `None`) is rejected by
    app.domain.per_unit's own validators at the service layer."""

    voltage_base_value: float | None = None
    voltage_base_unit: str | None = None
    voltage_basis: Literal["line_to_line", "line_to_neutral"] = "line_to_line"
    apparent_power_base_value: float | None = None
    apparent_power_base_unit: str | None = None
    current_base_mode: Literal["none", "derived", "direct"] = "none"
    direct_current_base_value: float | None = None
    direct_current_base_unit: str | None = None


class PerUnitProfileCreateRequest(PerUnitProfileBaseFields):
    name: str


class PerUnitProfileUpdateRequest(PerUnitProfileBaseFields):
    """Full replace of one profile's base fields + `assigned_channels`
    (decision 4). `reassign_conflicting` defaults to False -- a normal
    PUT can never silently steal a channel from another profile; the
    frontend only resubmits with this set to True after the user
    explicitly confirms a "Move N channel(s) here?" prompt."""

    name: str
    assigned_channels: list[ChannelRefIn] = []
    reassign_conflicting: bool = False


class ResolvedCurrentBaseOut(BaseModel):
    value: float
    unit: str


class PerUnitProfileOut(PerUnitProfileBaseFields):
    id: str
    workspace_id: str
    name: str
    resolved_current_base: ResolvedCurrentBaseOut | None
    assigned_channels: list[ChannelRefOut]
    created_at: datetime | None

    @classmethod
    def from_domain(cls, profile: PerUnitBaseProfile) -> "PerUnitProfileOut":
        from app.domain.per_unit import resolve_current_base_amps

        resolved_amps, _reason = resolve_current_base_amps(profile)
        return cls(
            id=profile.id,
            workspace_id=profile.workspace_id,
            name=profile.name,
            voltage_base_value=profile.voltage_base_value,
            voltage_base_unit=profile.voltage_base_unit,
            voltage_basis=profile.voltage_basis,
            apparent_power_base_value=profile.apparent_power_base_value,
            apparent_power_base_unit=profile.apparent_power_base_unit,
            current_base_mode=profile.current_base_mode,
            direct_current_base_value=profile.direct_current_base_value,
            direct_current_base_unit=profile.direct_current_base_unit,
            resolved_current_base=(
                ResolvedCurrentBaseOut(value=resolved_amps, unit="A") if resolved_amps is not None else None
            ),
            assigned_channels=[ChannelRefOut.from_domain(ref) for ref in profile.assigned_channels],
            created_at=profile.created_at,
        )


class ChannelAlreadyAssignedConflictOut(BaseModel):
    channel: ChannelRefOut
    profile_id: str
    profile_name: str


class ChannelAlreadyAssignedErrorOut(BaseModel):
    code: Literal["channel_already_assigned"] = "channel_already_assigned"
    message: str
    conflicts: list[ChannelAlreadyAssignedConflictOut]
