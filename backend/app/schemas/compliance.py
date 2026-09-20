"""Pydantic response schemas for Compliance & Capability -- Voltage
Measurement (Slice 2). Thin translation only -- see
`app.services.compliance_measurement_service` for the actual resolution
logic these mirror."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut


class ComplianceVoltageQuantityOut(BaseModel):
    id: str
    display_label: str
    voltage_representation: str


class ComplianceResolvedRoleOut(BaseModel):
    role: str
    display_name: str
    channel_ref: ChannelRefOut
    channel_name: str


class ComplianceBaseOut(BaseModel):
    nominal_voltage_ll_kv: float
    effective_reference: str
    assessment_unit: str


class ComplianceVoltageMeasurementOut(BaseModel):
    status: str
    quantity_id: str
    quantity_display_label: str
    voltage_representation: str
    resolved_roles: list[ComplianceResolvedRoleOut] = []
    used_direct_pair: bool = False
    input_type: str | None = None
    value_representation: str | None = None
    base: ComplianceBaseOut | None = None
    assessment_unit: str = "engineering_unit"
    missing: list[str] = []
    message: str | None = None
