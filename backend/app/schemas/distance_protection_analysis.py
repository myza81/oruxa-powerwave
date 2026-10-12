"""Wire shapes for Distance Protection v1 -- thin exposure of
`app.services.distance_protection_analysis_service`, never a
reimplementation of its calculation/guardrail/geometry logic (see
docs/project-memory/DISTANCE_PROTECTION_ANALYSIS.md).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.schemas.calculated_channel import ChannelRefOut

DistanceStatus = Literal["computed", "needs_configuration", "missing", "ambiguous", "not_eligible"]
ZoneState = Literal["operated", "not_operated"]


_Finite = Annotated[float, Field(allow_inf_nan=False)]

#: Request-size guard for the generic `zones` query parameter. Not a protection limit:
#: the engine evaluates however many zones it is given.
MAX_REQUEST_ZONES = 64


class ZoneSettingsIn(BaseModel):
    """One zone of the generic `zones` request parameter (Slice 10). ``key`` is the
    zone's stable identity: it is echoed back as ``ZoneResultOut.zone_key`` and never
    derived from position. ``None`` = not configured; nothing is defaulted."""

    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
    enabled: bool = False
    direction: Literal["forward", "reverse"] = "forward"
    reach_ohm: _Finite | None = None
    reactive_reach_ohm: _Finite | None = None
    resistive_reach_forward_ohm: _Finite | None = None
    resistive_reach_reverse_ohm: _Finite | None = None
    characteristic_angle_deg: _Finite | None = None
    delay_s: _Finite | None = None


ZONES_IN_ADAPTER: TypeAdapter[list[ZoneSettingsIn]] = TypeAdapter(
    Annotated[list[ZoneSettingsIn], Field(max_length=MAX_REQUEST_ZONES)]
)


class ZoneResultOut(BaseModel):
    """`state` is PURE geometric element state -- `Operated` means the
    calculated loop impedance satisfies/breaches the configured zone
    operating characteristic geometrically. It does NOT mean relay trip
    output asserted, breaker opened, or full relay logic completed.
    `delay_s` is configuration information only -- v1 never accumulates
    it, never declares it elapsed, never asserts a trip from it."""

    zone_key: str
    enabled: bool
    state: ZoneState
    #: None only for a Reverse Zone whose delay was never configured.
    delay_s: float | None
    #: The zone's own direction ("forward" | "reverse"). Independent of the
    #: zone identity and of a quadrilateral's reverse resistive reach.
    direction: str = "forward"


class DistanceAnalysisResultOut(BaseModel):
    """`v1_channel_ref`/`v2_channel_ref`/`i1_channel_ref`/`i2_channel_ref`
    are what let the shared Related Waveforms panel know which channels
    to fetch for the selected fault loop's source Voltage/Current
    traces, independent of this result's own `status` (mirrors
    `ImpedanceAnalysisResultOut`'s own precedent)."""

    status: DistanceStatus
    engineering_context_id: str
    loop: str
    analysis_time: float
    recording_basis: str | None
    impedance_basis: str | None
    vt_primary: float | None
    vt_secondary: float | None
    ct_primary: float | None
    ct_secondary: float | None
    reference_frequency_hz: float | None
    window_seconds: float | None
    algorithm_version: str
    v1_channel_ref: ChannelRefOut | None
    v2_channel_ref: ChannelRefOut | None
    i1_channel_ref: ChannelRefOut | None
    i2_channel_ref: ChannelRefOut | None
    voltage_unit: str | None
    current_unit: str | None
    resistance_ohm: float | None
    reactance_ohm: float | None
    magnitude_ohm: float | None
    angle_deg: float | None
    characteristic: str | None
    zone1: ZoneResultOut | None
    zone2: ZoneResultOut | None
    zone3: ZoneResultOut | None
    #: Added with the fourth (reverse-direction) manual slot; optional so
    #: older consumers that ignore it keep working.
    zone4: ZoneResultOut | None = None
    #: Slice 10: every evaluated zone, in request order, each under the key it was
    #: requested with. zone1..zone4 above are the entries with those keys.
    zones: list[ZoneResultOut] = []
    warnings: list[str]
    reason_code: str | None
    message: str


class DistanceLocusPointOut(BaseModel):
    analysis_time: float
    status: DistanceStatus
    resistance_ohm: float | None
    reactance_ohm: float | None
    magnitude_ohm: float | None
    angle_deg: float | None
    reason_code: str | None


class DistanceLocusOut(BaseModel):
    engineering_context_id: str
    loop: str
    points: list[DistanceLocusPointOut]


#: Manual Input / Calculator mode (Analysis Input Source = "manual") --
#: deliberately has no `engineering_context_id`/`analysis_time`/
#: `reference_frequency_hz`/`window_seconds`, mirroring
#: `ManualImpedanceResultOut`'s own field-omission rationale.
class ManualDistanceResultOut(BaseModel):
    status: DistanceStatus
    loop_label: str
    impedance_basis: str | None
    algorithm_version: str
    v1_magnitude_secondary: float | None
    v2_magnitude_secondary: float | None
    i1_magnitude_secondary: float | None
    i2_magnitude_secondary: float | None
    resistance_ohm: float | None
    reactance_ohm: float | None
    magnitude_ohm: float | None
    angle_deg: float | None
    characteristic: str | None
    zone1: ZoneResultOut | None
    zone2: ZoneResultOut | None
    zone3: ZoneResultOut | None
    #: Added with the fourth (reverse-direction) manual slot; optional so
    #: older consumers that ignore it keep working.
    zone4: ZoneResultOut | None = None
    #: Slice 10: every evaluated zone, in request order (see DistanceAnalysisResultOut).
    zones: list[ZoneResultOut] = []
    reason_code: str | None
    message: str
