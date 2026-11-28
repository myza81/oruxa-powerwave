"""D5A-2B2A: additive API contract for the unified measurement-side configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.measurement_side_config import (
    AUTH_GROUP_OVERRIDE,
    AUTH_RECORDING_CORRECTION,
    ChannelSideResolution,
    RecordingSideState,
    SideDiagnostic,
    SideSetResolution,
)
from app.services.measurement_side_service import GroupSideView, RecordingSideView

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
    measurement_group_id: str | None = None
    group_override_side: str | None = None
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, r: ChannelSideResolution) -> "ChannelMeasurementSideOut":
        return cls(
            source_id=r.source_id, channel_name=r.channel_name, quantity=r.quantity, effective_side=r.side,
            authority=r.authority, usable=r.usable, strict_usable=r.strict_usable, inferred=r.inferred,
            declared_side=r.declared_side, recording_side=r.recording_side,
            recording_authority=r.recording_authority, measurement_group_id=r.group_id,
            group_override_side=r.group_override_side,
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


def _contradicted_by_correction(channels, engineer_side: str | None) -> list[OverriddenDeclarationOut]:
    """Every channel whose own declaration the recording-level correction contradicts, whether or not a group setting
    later takes over that channel: the contradiction is a property of the correction, so it is always disclosed."""
    if engineer_side is None:
        return []
    return [OverriddenDeclarationOut(source_id=c.source_id, channel_name=c.channel_name or "",
                                     declared_side=c.declared_side, effective_side=engineer_side)
            for c in channels if c.declared_side not in ("unknown", engineer_side)]


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
    group_ids: list[str] = Field(default_factory=list)
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
            effective_side=state.effective_side, authority=state.authority, group_ids=list(view.group_ids),
            overridden_declarations=_contradicted_by_correction(view.channels, state.engineer_side),
            diagnostics=[SideDiagnosticOut.from_domain(x) for x in state.diagnostics],
            channels=([ChannelMeasurementSideOut.from_domain(c) for c in view.channels]
                      if include_channels else None),
        )


class GroupOverrideOut(BaseModel):
    side: str
    set_at: datetime


class GroupMeasurementSideOut(BaseModel):
    """One Voltage or Current Measurement Group of one recording -- the unit a Level 2 setting belongs to. One
    value covers all phases of the group; the bay's other group (Voltage vs Current) has its own."""

    measurement_group_id: str
    source_id: str
    kind: str
    display_name: str
    #: The side this group's channels would have WITHOUT an override (null when that is not a single side).
    inherited_side: str | None
    #: This recording's own Level 1 side.
    recording_side: str | None
    #: Present only when an engineer manually set this group; absent means it follows Level 1 / the evidence.
    override: GroupOverrideOut | None
    status: str
    #: One side only when every channel of the group shares it; null when unresolved or conflicting.
    effective_side: str | None
    strict_usable: bool
    inferred_channels: list[str]
    authority: str
    overridden_declarations: list[OverriddenDeclarationOut] = Field(default_factory=list)
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)
    channels: list[ChannelMeasurementSideOut] | None = None

    @classmethod
    def from_view(cls, view: GroupSideView, *, include_channels: bool) -> "GroupMeasurementSideOut":
        res: SideSetResolution = view.resolution
        return cls(
            measurement_group_id=view.group_id, source_id=view.source_id, kind=view.kind,
            display_name=view.display_name, inherited_side=view.inherited_side, recording_side=view.recording_side,
            override=(GroupOverrideOut(side=view.override.side, set_at=view.override.set_at) if view.override else None),
            status=res.status, effective_side=res.side, strict_usable=res.strict_usable,
            inferred_channels=list(res.inferred_channels), authority=res.authority,
            overridden_declarations=_overridden(view.channels, authorities=(AUTH_GROUP_OVERRIDE, AUTH_RECORDING_CORRECTION)),
            diagnostics=[SideDiagnosticOut.from_domain(d) for d in view.diagnostics],
            channels=[ChannelMeasurementSideOut.from_domain(c) for c in view.channels] if include_channels else None,
        )


class WorkspaceMeasurementSideOut(BaseModel):
    workspace_id: str
    recordings: list[RecordingMeasurementSideOut]
    #: Every Measurement Group of those recordings, each with its own Level 2 state.
    groups: list[GroupMeasurementSideOut]


class RecordingSideUpdateRequest(BaseModel):
    """`side: null` returns the recording to its own evidence (removes the engineer correction)."""

    side: ConfigurableSide | None
    note: str | None = Field(default=None, max_length=500)


class GroupSideUpdateRequest(BaseModel):
    """There is no reset: selecting the side the group already has without an override clears the override."""

    side: ConfigurableSide
