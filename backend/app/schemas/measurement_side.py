"""D5A-2B2A: additive API contract for the unified measurement-side configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Mapping

from pydantic import BaseModel, Field

from app.domain.measurement_side_config import (
    GroupOwnership,
    AUTH_BAY_OVERRIDE,
    AUTH_RECORDING_CORRECTION,
    ChannelSideResolution,
    RecordingSideState,
    SideDiagnostic,
    SideSetResolution,
)
from app.services.measurement_side_service import BaySideView, ContextSideView, RecordingSideView

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


def _contradicted_by_correction(channels, engineer_side: str | None) -> list[OverriddenDeclarationOut]:
    """Every channel whose own declaration the recording-level correction contradicts, whether or not a bay setting
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
            overridden_declarations=_contradicted_by_correction(view.channels, state.engineer_side),
            diagnostics=[SideDiagnosticOut.from_domain(x) for x in state.diagnostics],
            channels=([ChannelMeasurementSideOut.from_domain(c) for c in view.channels]
                      if include_channels else None),
        )


class BayOverrideOut(BaseModel):
    side: str
    set_at: datetime
    active: bool


class BayRefOut(BaseModel):
    engineering_context_id: str
    display_name: str


class GroupOwnershipOut(BaseModel):
    """Which bays hold the channels of one Voltage/Current Measurement Group (CT/VT ownership)."""

    group_id: str
    kind: str
    display_name: str
    #: `no_bay`, `single_bay`, `spans_bays` (all on one side), `spans_bays_ambiguous` (sides differ or unresolved).
    status: str
    #: True when a conversion through this group's ratio must be blocked rather than guessed.
    conversion_authority_ambiguous: bool
    bays: list[BayRefOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, o: GroupOwnership, bay_names: Mapping[str, str]) -> "GroupOwnershipOut":
        return cls(group_id=o.group_id, kind=o.kind, display_name=o.display_name, status=o.status,
                   conversion_authority_ambiguous=o.conversion_authority_ambiguous,
                   bays=[BayRefOut(engineering_context_id=b, display_name=bay_names.get(b, b)) for b in o.bay_ids])


class BayMeasurementSideOut(BaseModel):
    """One bay (Engineering Context) WITHIN ONE recording -- the unit a Level 2 setting belongs to."""

    engineering_context_id: str
    source_id: str
    display_name: str
    context_status: str
    bay_membership: str
    #: This recording's own Level 1 side; never a value shared across the bay's other recordings.
    inherited_recording_side: str | None
    #: Present only when an engineer manually set this bay for THIS recording; absent means it follows Level 1.
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
    voltage_group_ids: list[str]
    current_group_ids: list[str]
    group_ownership: list[GroupOwnershipOut] = Field(default_factory=list)
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)
    channels: list[ChannelMeasurementSideOut] | None = None

    @classmethod
    def from_view(cls, view: BaySideView, *, include_channels: bool,
                  bay_names: Mapping[str, str] | None = None) -> "BayMeasurementSideOut":
        res: SideSetResolution = view.resolution
        names = bay_names or {}
        channels = [ChannelMeasurementSideOut.from_domain(c) for c in view.channels] if include_channels else None
        return cls(
            engineering_context_id=view.context_id, source_id=view.source_id, display_name=view.display_name,
            context_status=view.context_status, bay_membership=view.membership,
            inherited_recording_side=view.inherited_recording_side,
            override=(BayOverrideOut(side=view.override.side, set_at=view.override.set_at, active=view.override_active)
                      if view.override else None),
            status=res.status, effective_side=res.side, voltage_side=res.voltage_side, current_side=res.current_side,
            reference_sides=res.reference_sides, strict_usable=res.strict_usable,
            inferred_channels=list(res.inferred_channels), authority=res.authority,
            overridden_declarations=_overridden(view.channels, authorities=(AUTH_BAY_OVERRIDE, AUTH_RECORDING_CORRECTION)),
            voltage_group_ids=list(view.voltage_group_ids), current_group_ids=list(view.current_group_ids),
            group_ownership=[GroupOwnershipOut.from_domain(o, names) for o in view.group_ownership],
            diagnostics=[SideDiagnosticOut.from_domain(d) for d in view.diagnostics], channels=channels,
        )


class ContextMeasurementSideOut(BaseModel):
    """An Engineering Context: one association per recording that contributes voltage/current channels."""

    engineering_context_id: str
    display_name: str
    context_status: str
    bay_membership: str
    associations: list[BayMeasurementSideOut]
    diagnostics: list[SideDiagnosticOut] = Field(default_factory=list)

    @classmethod
    def from_view(cls, view: ContextSideView, *, include_channels: bool,
                  bay_names: Mapping[str, str] | None = None) -> "ContextMeasurementSideOut":
        return cls(
            engineering_context_id=view.context_id, display_name=view.display_name, context_status=view.context_status,
            bay_membership=view.membership,
            associations=[BayMeasurementSideOut.from_view(a, include_channels=include_channels, bay_names=bay_names)
                          for a in view.associations],
            diagnostics=[SideDiagnosticOut.from_domain(d) for d in view.diagnostics],
        )


class WorkspaceMeasurementSideOut(BaseModel):
    workspace_id: str
    recordings: list[RecordingMeasurementSideOut]
    #: Every (bay, recording) association -- one entry per recording a bay contributes channels from.
    bays: list[BayMeasurementSideOut]


class RecordingSideUpdateRequest(BaseModel):
    """`side: null` returns the recording to its own evidence (removes the engineer correction)."""

    side: ConfigurableSide | None
    note: str | None = Field(default=None, max_length=500)


class BaySideUpdateRequest(BaseModel):
    """There is no reset: selecting the side the bay inherits from the recording clears the override."""

    side: ConfigurableSide
