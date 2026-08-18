"""Wire shape for the Phase 4A batched digital-waveform endpoint.

JSON-first, same discipline as app.schemas.waveform (the analog endpoint's
own wire shape) -- see that module's own docstring. Unlike the analog
endpoint, there is no `representation`/point-budget concept here: digital
data is always returned as the full-record transition list, never reduced
-- see app.services.waveform_service.extract_digital_waveform's own
docstring for why that's the deliberate, engineering-safe choice, not an
oversight.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.waveform_service import DigitalWaveformResult


class DigitalTransitionOut(BaseModel):
    time: float
    state: int


class DigitalWaveformOut(BaseModel):
    """One digital channel's full-record state -- see DigitalWaveformResult."""

    source_id: str
    channel_name: str
    classification: str
    normal_state: int
    initial_state: int
    transitions: list[DigitalTransitionOut]
    start_time: float
    end_time: float
    sample_count: int

    @classmethod
    def from_result(cls, result: DigitalWaveformResult) -> "DigitalWaveformOut":
        return cls(
            source_id=result.source_id,
            channel_name=result.channel_name,
            classification=result.classification,
            normal_state=result.normal_state,
            initial_state=result.initial_state,
            transitions=[
                DigitalTransitionOut(time=t.time, state=t.state) for t in result.transitions
            ],
            start_time=result.start_time,
            end_time=result.end_time,
            sample_count=result.sample_count,
        )


class DigitalWaveformBatchOut(BaseModel):
    """Batched response for GET .../digital-waveform -- one entry per
    requested `channel_names` value, in the SAME order they were
    requested (the caller already has the correct group/alphabetical
    display order from GET .../channels; this endpoint does not
    re-derive or re-sort it)."""

    channels: list[DigitalWaveformOut]
