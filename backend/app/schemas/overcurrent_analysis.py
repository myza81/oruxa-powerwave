"""Wire shapes for Overcurrent Analysis v1's read-only endpoints -- thin
exposure of `app.services.overcurrent_analysis_service`, never a
reimplementation of its estimation/guardrail logic. See
docs/project-memory/OVERCURRENT_ANALYSIS.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut

OvercurrentAnalysisStatus = Literal["computed", "needs_configuration", "ambiguous", "not_applicable"]
OvercurrentPhase = Literal["A", "B", "C"]
OvercurrentRecordingBasis = Literal["primary", "secondary"]


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
