"""Wire shape for the Phase 4C1 batched A/B cursor-values endpoint.

JSON-first, matching every other endpoint in this API (see
app.schemas.waveform's own header note) -- a POST body rather than query
params because this request naturally carries a list (channel_names)
alongside two independent optional scalars (cursor_a_time/cursor_b_time),
the same shape FastAPI/pydantic already handle cleanly as a body model.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.waveform_service import CursorValuesResult


class CursorValuesRequest(BaseModel):
    """Request body for POST .../cursor-values.

    `channel_names` are analog channel names as returned by GET
    .../channels -- unknown/non-analog names are silently omitted from the
    response rather than rejected (see extract_cursor_values's own
    docstring). `cursor_a_time`/`cursor_b_time` are elapsed seconds on this
    source's own native time axis (the same shared workspace engineering
    cursor time app.services.waveform_service already expects for
    start_time/end_time) -- omit either one (`null`/absent) when that
    cursor is off/individually closed; the response's own `cursor_a`/
    `cursor_b` and every channel's corresponding value are `null` in that
    case, and no per-channel work is done for it.
    """

    channel_names: list[str]
    cursor_a_time: float | None = None
    cursor_b_time: float | None = None


class CursorPointOut(BaseModel):
    """One cursor's own resolution against a source's true time bounds.

    `sample_time` is `null` exactly when `requested_time` fell outside
    this source's own valid time bounds (never clamped -- section 12).
    """

    requested_time: float
    sample_time: float | None


class ChannelCursorValuesOut(BaseModel):
    """One analog channel's instantaneous value at cursor A/B.

    `a_value`/`b_value` are `null` exactly when that cursor was not
    supplied or fell outside this source's bounds -- never a fabricated or
    boundary-clamped value.
    """

    channel_name: str
    unit: str
    a_value: float | None
    b_value: float | None


class CursorValuesOut(BaseModel):
    """A whole source's instantaneous A/B measurement batch."""

    source_id: str
    cursor_a: CursorPointOut | None
    cursor_b: CursorPointOut | None
    channels: list[ChannelCursorValuesOut]

    @classmethod
    def from_result(cls, result: CursorValuesResult) -> "CursorValuesOut":
        return cls(
            source_id=result.source_id,
            cursor_a=(
                CursorPointOut(
                    requested_time=result.cursor_a.requested_time,
                    sample_time=result.cursor_a.sample_time,
                )
                if result.cursor_a is not None
                else None
            ),
            cursor_b=(
                CursorPointOut(
                    requested_time=result.cursor_b.requested_time,
                    sample_time=result.cursor_b.sample_time,
                )
                if result.cursor_b is not None
                else None
            ),
            channels=[
                ChannelCursorValuesOut(
                    channel_name=channel.channel_name,
                    unit=channel.unit,
                    a_value=channel.a_value,
                    b_value=channel.b_value,
                )
                for channel in result.channels
            ],
        )
