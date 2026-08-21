"""Wire shape for the Maximum/Minimum Peak annotation batch endpoint
(Phase 4G, DEC-046).

Batched per source (one request covers every requested channel/mode pair
for one shared time interval), the SAME shape choice
app.schemas.cursor_values already made for A/B cursor measurements --
never one request per annotation (section 33/34 of the Phase 4G task).
This is NOT a persistent annotation backend: the frontend's own
`ww.annotations` remains the sole state authority for +Peak/-Peak
afterward (DEC-044/DEC-046); this endpoint only ever answers "what is the
current max/min recorded sample for this channel, in this time interval."
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.services.waveform_service import PeakValueResult


class PeakValueRequestItem(BaseModel):
    """One requested channel/mode pair within the shared batch interval."""

    channel_name: str
    mode: Literal["max", "min"]


class PeakValueBatchRequest(BaseModel):
    """Request body for POST .../peak-values.

    `start_time`/`end_time` are the current visible X viewport, elapsed
    seconds on this source's own native time axis (section 4 -- the SAME
    coordinate system every other time-based request in this API already
    uses) -- NOT the whole recording, NOT an A/B cursor interval.
    """

    requests: list[PeakValueRequestItem]
    start_time: float
    end_time: float


class PeakValueResultOut(BaseModel):
    """One channel/mode pair's resolved (or unavailable) peak.

    `available=False` -- with every other field `None` -- means the
    requested interval, clipped to this source's own bounds, contained no
    finite sample for this channel; the caller must not present a stale
    prior value as current for this interval (section 12/67).
    """

    channel_name: str
    mode: str
    available: bool
    sample_index: int | None
    elapsed_seconds: float | None
    value: float | None
    unit: str | None

    @classmethod
    def from_result(cls, result: PeakValueResult) -> "PeakValueResultOut":
        return cls(
            channel_name=result.channel_name,
            mode=result.mode,
            available=result.available,
            sample_index=result.sample_index,
            elapsed_seconds=result.elapsed_seconds,
            value=result.value,
            unit=result.unit,
        )


class PeakValueBatchOut(BaseModel):
    source_id: str
    start_time: float
    end_time: float
    results: list[PeakValueResultOut]
