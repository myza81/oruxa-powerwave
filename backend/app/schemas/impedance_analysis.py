"""Wire shapes for Impedance Locus v1 -- thin exposure of
`app.services.impedance_analysis_service`, never a reimplementation of
its calculation/guardrail logic (see docs/project-memory/
IMPEDANCE_LOCUS_ANALYSIS.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut

ImpedanceStatus = Literal["computed", "needs_configuration", "missing", "ambiguous", "not_eligible"]


class ImpedanceAnalysisResultOut(BaseModel):
    """`voltage_channel_ref`/`current_channel_ref` are what let the
    shared Related Waveforms panel know which channel to fetch for this
    phase's Voltage/Current traces (see `ImpedanceAnalysisResult`'s own
    docstring in `app.domain.impedance` for the root-cause record this
    fixes)."""

    status: ImpedanceStatus
    engineering_context_id: str
    phase: str
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
    voltage_channel_ref: ChannelRefOut | None
    voltage_magnitude_rms: float | None
    voltage_unit: str | None
    current_channel_ref: ChannelRefOut | None
    current_magnitude_rms: float | None
    current_unit: str | None
    resistance_ohm: float | None
    reactance_ohm: float | None
    magnitude_ohm: float | None
    angle_deg: float | None
    warnings: list[str]
    reason_code: str | None
    message: str


class ImpedanceLocusPointOut(BaseModel):
    analysis_time: float
    status: ImpedanceStatus
    resistance_ohm: float | None
    reactance_ohm: float | None
    magnitude_ohm: float | None
    angle_deg: float | None
    reason_code: str | None


class ImpedanceLocusOut(BaseModel):
    engineering_context_id: str
    phase: str
    points: list[ImpedanceLocusPointOut]


#: Manual Input / Calculator mode (Analysis Input Source = "manual") --
#: deliberately has no `engineering_context_id`/`analysis_time`/
#: `reference_frequency_hz`/`window_seconds`, mirroring
#: `PhasorManualDiagramResultOut`/`OvercurrentManualAnalysisResultOut`'s
#: own field-omission rationale.
class ManualImpedanceResultOut(BaseModel):
    status: ImpedanceStatus
    phase_label: str
    impedance_basis: str | None
    algorithm_version: str
    voltage_magnitude_secondary: float | None
    current_magnitude_secondary: float | None
    resistance_ohm: float | None
    reactance_ohm: float | None
    magnitude_ohm: float | None
    angle_deg: float | None
    reason_code: str | None
    message: str
