"""D5A-2B2A: additive API contract for the unified measurement-side configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.measurement_side_config import (
    AUTH_BAY_OVERRIDE,
    AUTH_RECORDING_CORRECTION,
    ChannelSideResolution,
    RecordingSideState,
    SideDiagnostic,
    SideSetResolution,
)
from app.services.measurement_side_service import BaySideView, RecordingSideView

ConfigurableSide = Literal["primary", "secondary"]


class SideDiagnosticOut(BaseModel):
    code: str
    severity: str
    message: str
    detail: dict[str, str | int | None] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, diagnostic: SideDiagnostic) -> "SideDiagnosticOut":
        return cls(code=diagnostic.code, severity=diagnostic.severity, message=diagnostic.message,
                   detail=dict(diagnostic.detail))


class ChannelMeasurementSideOut(BaseModel):
    """One channel's effective side, with the original evidence and the configuration that decided it."""

    source_id: str | None = None
    channel_name: str | None = None
    quantity: str | None = None
    effective_side: str
    authority: str
    usable: bool
    #: True for a concrete side strict side-dependent calculations may act on (reliable evidence or an engineer
    #: setting). False when the side is only inferred from the recording's other channels.
    strict_usable: bool
    inferred: bool
    declared_side: str
    recording_side: str | None = None
    recording_authority: str
    engineering_context_id: str | None = None
    bay_membership: str
    bay_override_side: str | None = None
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, r: ChannelSideResolution) -> "ChannelMeasurementSideOut":
        return cls(
            source_id=r.source_id, channel_name=r.channel_name, quantity=r.quantity, effective_side=r.side,
            authority=r.authority, usable=r.usable, strict_usable=r.strict_usable, inferred=r.inferred,
            declared_side=r.declared_side, recording_side=r.recording_side,
            recording_authority=r.recording_authority, engineering_context_id=r.context_id,
            bay_membership=r.membership, bay_override_side=r.bay_override_side,
            diagnostics=[SideDiagnosticOut.from_domain(d) for d in r.diagnostics],
        )


class RecordingDerivedSideOut(BaseModel):
    """What the recording's own channel declarations say -- no engineer input applied."""

    status: str
    side: str | None
    #: The side the declaring channels of each quantity agree on (null when none declare or they disagree).
    voltage_side: str | None
    current_side: str | None
    primary_channels: int
    secondary_channels: int
    undeclared_channels: int
    evidence_channels: int


class OverriddenDeclarationOut(BaseModel):
    """A channel whose original declaration an engineer setting overrides -- disclosed, never hidden."""

    source_id: str | None
    channel_name: str
    declared_side: str
    effective_side: str


def _overridden(channels, *, authorities: tuple[str, ...]) -> list[OverriddenDeclarationOut]:
    return [OverriddenDeclarationOut(source_id=c.source_id, channel_name=c.channel_name or "",
                                     declared_side=c.declared_side, effective_side=c.side)
            for c in channels if c.authority in authorities and c.declared_side not in ("unknown", c.side)]


class RecordingCorrectionOut(BaseModel):
    side: str
    note: str | None
    set_at: datetime


class RecordingMeasurementSideOut(BaseModel):
    source_id: str
    recording_derived: RecordingDerivedSideOut
    engineer_correction: RecordingCorrectionOut | None
    effective_side: str | None
    authority: str
    bay_ids: list[str] = Field(default_factory=list)
    #: Channels whose own declaration the engineer's recording-level correction contradicts.
    overridden_declarations: list[OverriddenDeclarationOut] = Field(default_factory=list)
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)
    channels: list[ChannelMeasurementSideOut] | None = None

    @classmethod
    def from_view(cls, view: RecordingSideView, *, include_channels: bool) -> "RecordingMeasurementSideOut":
        state: RecordingSideState = view.state
        d = state.derivation
        return cls(
            source_id=view.source_id,
            recording_derived=RecordingDerivedSideOut(
                status=d.status, side=d.side, voltage_side=d.voltage_side, current_side=d.current_side,
                primary_channels=d.primary_count, secondary_channels=d.secondary_count,
                undeclared_channels=d.undeclared_count, evidence_channels=d.evidence_channel_count),
            engineer_correction=(RecordingCorrectionOut(side=view.correction.side, note=view.correction.note,
                                                        set_at=view.correction.set_at) if view.correction else None),
            effective_side=state.effective_side, authority=state.authority, bay_ids=list(view.bay_ids),
            overridden_declarations=_overridden(view.channels, authorities=(AUTH_RECORDING_CORRECTION,)),
            diagnostics=[SideDiagnosticOut.from_domain(x) for x in state.diagnostics],
            channels=([ChannelMeasurementSideOut.from_domain(c) for c in view.channels]
                      if include_channels else None),
        )


class BayOverrideOut(BaseModel):
    side: str
    set_at: datetime
    active: bool


class BayMeasurementSideOut(BaseModel):
    engineering_context_id: str
    display_name: str
    context_status: str
    bay_membership: str
    #: The single Level 1 value every recording of this bay shares; null when it has none or they disagree.
    inherited_recording_side: str | None
    #: Present only when an engineer manually set this bay; absent means the bay follows Level 1.
    override: BayOverrideOut | None
    status: str
    #: One side only when every channel shares it; null when voltage and current legitimately differ
    #: (see `reference_sides`) or the bay is unresolved/conflicting.
    effective_side: str | None
    voltage_side: str | None
    current_side: str | None
    #: `uniform`, `voltage_current_differ` (legitimate: normalised independently) or null when not resolved.
    reference_sides: str | None
    strict_usable: bool
    inferred_channels: list[str]
    authority: str
    overridden_declarations: list[OverriddenDeclarationOut] = Field(default_factory=list)
    source_ids: list[str]
    voltage_group_ids: list[str]
    current_group_ids: list[str]
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)
    channels: list[ChannelMeasurementSideOut] | None = None

    @classmethod
    def from_view(cls, view: BaySideView, *, include_channels: bool) -> "BayMeasurementSideOut":
        res: SideSetResolution = view.resolution
        channels = [ChannelMeasurementSideOut.from_domain(c) for c in view.channels] if include_channels else None
        return cls(
            engineering_context_id=view.context_id, display_name=view.display_name, context_status=view.context_status,
            bay_membership=view.membership, inherited_recording_side=view.inherited_recording_side,
            override=(BayOverrideOut(side=view.override.side, set_at=view.override.set_at, active=view.override_active)
                      if view.override else None),
            status=res.status, effective_side=res.side, voltage_side=res.voltage_side, current_side=res.current_side,
            reference_sides=res.reference_sides, strict_usable=res.strict_usable,
            inferred_channels=list(res.inferred_channels), authority=res.authority,
            overridden_declarations=_overridden(view.channels, authorities=(AUTH_BAY_OVERRIDE, AUTH_RECORDING_CORRECTION)), source_ids=list(view.source_ids), voltage_group_ids=list(view.voltage_group_ids),
            current_group_ids=list(view.current_group_ids),
            diagnostics=[SideDiagnosticOut.from_domain(d) for d in view.diagnostics], channels=channels,
        )


class WorkspaceMeasurementSideOut(BaseModel):
    workspace_id: str
    recordings: list[RecordingMeasurementSideOut]
    bays: list[BayMeasurementSideOut]


class RecordingSideUpdateRequest(BaseModel):
    """`side: null` returns the recording to its own evidence (removes the engineer correction)."""

    side: ConfigurableSide | None
    note: str | None = Field(default=None, max_length=500)


class BaySideUpdateRequest(BaseModel):
    """There is no reset: selecting the side the bay inherits from the recording clears the override."""

    side: ConfigurableSide
