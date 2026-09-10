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

from app.schemas.measurement_group import VoltageReferenceValue
from app.services.per_unit_coverage_service import PerUnitCoverageSummary
from app.services.per_unit_provenance_service import PerUnitChannelProvenance
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


class PerUnitCoverageOut(BaseModel):
    """Per-Unit Settings hierarchy, Slice 2: one source's own Per-Unit
    coverage breakdown -- mutually exclusive counts, derived fresh per
    request (see app.services.per_unit_coverage_service), never stored."""

    source_id: str
    applicable_channel_count: int
    measurement_group_count: int
    source_default_count: int
    needs_configuration_count: int

    @classmethod
    def from_summary(cls, summary: PerUnitCoverageSummary) -> "PerUnitCoverageOut":
        return cls(
            source_id=summary.source_id,
            applicable_channel_count=summary.applicable_channel_count,
            measurement_group_count=summary.measurement_group_count,
            source_default_count=summary.source_default_count,
            needs_configuration_count=summary.needs_configuration_count,
        )


class PerUnitResolutionOut(BaseModel):
    """Per-Unit Settings hierarchy, Slice 3: one channel's own Per-Unit
    provenance/traceability -- built directly from the exact
    `PerUnitResolution` that would convert this channel's own displayed
    value (see app.services.per_unit_provenance_service's own module
    docstring for the "one source of truth" guarantee). Derived fresh
    per request, never stored.

    Every field beyond `status`/`engineering_type` is `None` unless the
    channel's own effective resolution scope actually carries it --
    `nominal_base_kv`/`nominal_reference` are populated ONLY for a
    Voltage Measurement Group (never for Source Default, which has no
    separate nominal-vs-effective distinction in its own current
    arithmetic); `equipment_rating_mva`/`applicable_voltage_ll_kv` ONLY
    for a Current Measurement Group using the equipment-rating method."""

    status: Literal["configured", "base_required", "not_applicable"]
    engineering_type: str
    source_kind: Literal["measurement_group", "source_default"] | None
    reason: str | None
    measurement_group_id: str | None
    measurement_group_name: str | None
    nominal_base_kv: float | None
    nominal_reference: VoltageReferenceValue | None
    effective_base_amount: float | None
    effective_base_unit: Literal["kV", "kA"] | None
    equipment_rating_mva: float | None
    applicable_voltage_ll_kv: float | None

    @classmethod
    def from_provenance(cls, provenance: PerUnitChannelProvenance) -> "PerUnitResolutionOut":
        return cls(
            status=provenance.status,
            engineering_type=provenance.engineering_type,
            source_kind=provenance.source_kind,
            reason=provenance.reason,
            measurement_group_id=provenance.measurement_group_id,
            measurement_group_name=provenance.measurement_group_name,
            nominal_base_kv=provenance.nominal_base_kv,
            nominal_reference=provenance.nominal_reference,
            effective_base_amount=provenance.effective_base_amount,
            effective_base_unit=provenance.effective_base_unit,
            equipment_rating_mva=provenance.equipment_rating_mva,
            applicable_voltage_ll_kv=provenance.applicable_voltage_ll_kv,
        )
