"""Wire shapes for the Phase 5C Per-Unit Measurement Mode API (DEC-049;
source-bound redesign following owner UAT).

No `ChannelRefIn`/`assigned_channels`/`reassign_conflicting` any more --
a configuration is identified by its own owning `source_id` (the URL
path parameter), and every eligible channel of that source uses it
automatically. Base values are canonical (Voltage Base: kV, Direct
Current Base: kA, Apparent Power Base: MVA) -- no unit field, matching
the owner's own UAT preference for a fixed unit suffix over a dropdown.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.services.per_unit_service import SourcePerUnitConfigView


class SourcePerUnitConfigUpdateRequest(BaseModel):
    """Request body for PUT .../per-unit/sources/{source_id}. Full
    replace, matching every other PUT in this codebase -- there is no
    partial-update concept."""

    voltage_base_value: float | None = None
    voltage_reference_mode: Literal["auto", "manual"] = "auto"
    voltage_reference_override: Literal["line_to_ground", "line_to_line"] | None = None
    current_base_mode: Literal["none", "derived", "direct"] = "none"
    apparent_power_base_value: float | None = None
    direct_current_base_value: float | None = None


class ResolvedCurrentBaseOut(BaseModel):
    value: float
    unit: str


class SourcePerUnitConfigOut(BaseModel):
    source_id: str
    configured: bool
    voltage_base_value: float | None
    voltage_reference_mode: Literal["auto", "manual"]
    voltage_reference_override: Literal["line_to_ground", "line_to_line"] | None
    # The LIVE effective reference -- auto-detected from this source's
    # own current Voltage channel names, or the manual override, per
    # app.domain.per_unit.resolve_effective_voltage_reference(). `None`
    # when auto mode cannot determine a confident result (section 7:
    # never silently invented).
    effective_voltage_reference: Literal["line_to_ground", "line_to_line"] | None
    voltage_reference_evidence: list[str]
    voltage_reference_reason: str
    current_base_mode: Literal["none", "derived", "direct"]
    apparent_power_base_value: float | None
    direct_current_base_value: float | None
    resolved_current_base: ResolvedCurrentBaseOut | None
    created_at: datetime | None

    @classmethod
    def from_view(cls, view: SourcePerUnitConfigView) -> "SourcePerUnitConfigOut":
        return cls(
            source_id=view.source_id,
            configured=view.configured,
            voltage_base_value=view.voltage_base_value,
            voltage_reference_mode=view.voltage_reference_mode,
            voltage_reference_override=view.voltage_reference_override,
            effective_voltage_reference=view.effective_voltage_reference,
            voltage_reference_evidence=view.voltage_reference_evidence,
            voltage_reference_reason=view.voltage_reference_reason,
            current_base_mode=view.current_base_mode,
            apparent_power_base_value=view.apparent_power_base_value,
            direct_current_base_value=view.direct_current_base_value,
            resolved_current_base=(
                ResolvedCurrentBaseOut(value=view.resolved_current_base_amps, unit="A")
                if view.resolved_current_base_amps is not None
                else None
            ),
            created_at=view.created_at,
        )
