"""Wire shapes for Sequence Components v1 -- thin exposure of
`app.services.sequence_components_analysis_service`, never a
reimplementation of its calculation/guardrail logic (see
docs/project-memory/SEQUENCE_COMPONENTS_ANALYSIS.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut

SequenceStatus = Literal["computed", "needs_configuration", "missing", "ambiguous", "not_eligible"]


class SequenceFamilyResultOut(BaseModel):
    """`phase_a_channel_ref`/`phase_b_channel_ref`/`phase_c_channel_ref`
    are what let the shared Related Waveforms panel know which channels
    to fetch for this family's Va/Vb/Vc (or Ia/Ib/Ic) source traces --
    populated whenever that phase's own role identity is known,
    independent of this family's own `status` (mirrors
    `ImpedanceAnalysisResultOut`'s own channel-ref precedent)."""

    status: SequenceStatus
    zero_sequence_magnitude: float | None
    zero_sequence_angle_deg: float | None
    positive_sequence_magnitude: float | None
    positive_sequence_angle_deg: float | None
    negative_sequence_magnitude: float | None
    negative_sequence_angle_deg: float | None
    negative_sequence_ratio_percent: float | None
    zero_sequence_ratio_percent: float | None
    unit: str | None
    phase_a_channel_ref: ChannelRefOut | None
    phase_b_channel_ref: ChannelRefOut | None
    phase_c_channel_ref: ChannelRefOut | None
    reason_code: str | None
    message: str


class SequenceAnalysisResultOut(BaseModel):
    status: SequenceStatus
    engineering_context_id: str
    analysis_time: float
    reference_frequency_hz: float | None
    window_seconds: float | None
    algorithm_version: str
    voltage_sequences: SequenceFamilyResultOut
    current_sequences: SequenceFamilyResultOut
    warnings: list[str]
    reason_code: str | None
    message: str


#: Manual Input / Calculator mode (Analysis Input Source = "manual") --
#: deliberately has no `engineering_context_id`/`analysis_time`/
#: `reference_frequency_hz`/`window_seconds`, mirroring
#: `ManualImpedanceResultOut`'s own field-omission rationale.
class SequenceManualResultOut(BaseModel):
    status: SequenceStatus
    algorithm_version: str
    voltage_sequences: SequenceFamilyResultOut
    current_sequences: SequenceFamilyResultOut
    warnings: list[str]
    reason_code: str | None
    message: str
