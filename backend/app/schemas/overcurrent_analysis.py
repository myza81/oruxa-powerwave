"""Wire shapes for Overcurrent Analysis v1's read-only endpoints -- thin
exposure of `app.services.overcurrent_analysis_service`, never a
reimplementation of its estimation/guardrail logic. See
docs/project-memory/OVERCURRENT_ANALYSIS.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.measurement_side import ChannelMeasurementSideOut

OvercurrentAnalysisStatus = Literal["computed", "needs_configuration", "ambiguous", "not_applicable"]
OvercurrentPhase = Literal["A", "B", "C"]
OvercurrentRecordingBasis = Literal["primary", "secondary"]
OvercurrentRecordedSide = Literal["primary", "secondary"]


class OvercurrentAnalysisResultOut(BaseModel):
    status: OvercurrentAnalysisStatus
    engineering_context_id: str
    phase: OvercurrentPhase
    analysis_time: float
    characteristic_id: str | None
    tms: float | None
    pickup_current_secondary: float | None
    recording_basis: OvercurrentRecordingBasis | None
    ct_primary: float | None
    ct_secondary: float | None
    reference_frequency_hz: float | None
    window_seconds: float | None
    algorithm_version: str
    channel_ref: ChannelRefOut | None
    measured_rms_current: float | None
    measured_rms_current_unit: str | None
    relay_secondary_current: float | None
    multiple_of_pickup: float | None
    expected_operating_time_seconds: float | None
    above_pickup_duration_seconds: float | None
    threshold_exceeded: bool
    warnings: list[str]
    reason_code: str | None
    message: str
    # D5A-2B2C-1A: the Recording Details authority the result consumed. `recording_basis` is the effective
    # measurement side of the consumed Current channel (never a request value); a configuration block reports
    # what was found (side, authority, owning Current Measurement Group) and never a number.
    measurement_side: OvercurrentRecordedSide | None = None
    measurement_side_authority: str | None = None
    measurement_group_id: str | None = None
    ct_authority: str | None = None


class OvercurrentCharacteristicOut(BaseModel):
    id: str
    family: str
    display_name: str
    k: float
    alpha: float
    c: float
    source: str


class OvercurrentCharacteristicsOut(BaseModel):
    characteristics: list[OvercurrentCharacteristicOut]


class OvercurrentCurvePointOut(BaseModel):
    multiple_of_pickup: float
    operating_time_seconds: float


class OvercurrentCurveOut(BaseModel):
    characteristic_id: str
    tms: float
    points: list[OvercurrentCurvePointOut]


OvercurrentManualAnalysisStatus = Literal["computed", "needs_configuration"]


class OvercurrentManualAnalysisResultOut(BaseModel):
    """Manual Input / Calculator mode (Analysis Input Source = 'manual')
    -- see docs/project-memory/ANALYSIS_INPUT_SOURCE.md. Deliberately has
    no `engineering_context_id`/`phase`/`analysis_time`/`channel_ref`/
    `above_pickup_duration_seconds`/`threshold_exceeded` fields, mirroring
    `app.domain.overcurrent.ManualOvercurrentAnalysisResult`'s own
    rationale for omitting them."""

    status: OvercurrentManualAnalysisStatus
    characteristic_id: str | None
    tms: float | None
    pickup_current_secondary: float | None
    input_basis: OvercurrentRecordingBasis | None
    ct_primary: float | None
    ct_secondary: float | None
    algorithm_version: str
    input_current: float | None
    input_current_unit: str | None
    relay_secondary_current: float | None
    multiple_of_pickup: float | None
    expected_operating_time_seconds: float | None
    reason_code: str | None
    message: str


class EquipmentLoadingConversionOut(BaseModel):
    """Manual Input's Equipment Loading conversion (balanced three-phase):
    `actual_loading_mva = equipment_rating_mva * loading_percent / 100`,
    `primary_current_a = actual_loading_mva * 1000 / (sqrt(3) *
    system_voltage_kv)`. See `app.domain.equipment_loading`."""

    equipment_rating_mva: float
    loading_percent: float
    system_voltage_kv: float
    actual_loading_mva: float
    primary_current_a: float


class OvercurrentManualLoadingResultOut(OvercurrentManualAnalysisResultOut):
    """The ordinary manual result (the equivalent primary current
    evaluated as `input_current`, unit `A`, basis `primary`) plus the
    conversion that produced it. `equipment_loading` is `None` only when
    the loading inputs themselves were invalid."""

    equipment_loading: EquipmentLoadingConversionOut | None


OvercurrentRecordedInputStatus = Literal["ready", "needs_configuration", "ambiguous", "not_applicable"]


class OvercurrentRecordedCtOut(BaseModel):
    """The CT of the Measurement Group that owns the consumed Current channel (never another group's)."""

    status: str
    consumable: bool
    primary: float | None
    secondary: float | None
    ratio: float | None
    authority: str
    reason: str | None
    group_ids: list[str]


class OvercurrentRecordedInputOut(BaseModel):
    """D5A-2B2C-1A: read-only report of what one recorded Overcurrent phase consumes from Recording Details -- the
    consumed Current channel, its Measurement Group, its effective measurement side (with provenance) and the CT of
    that group -- and whether the calculation is blocked by that configuration. Nothing is computed or stored; the
    calculation endpoint evaluates the identical authority."""

    status: OvercurrentRecordedInputStatus
    engineering_context_id: str
    phase: OvercurrentPhase
    channel_ref: ChannelRefOut | None
    channel_unit: str | None
    measurement_group_id: str | None
    measurement_group_name: str | None
    measurement_side: ChannelMeasurementSideOut | None
    ct: OvercurrentRecordedCtOut | None
    conversion: Literal["none", "primary_to_relay_secondary"] | None
    reason_code: str | None
    message: str
