"""Wire shape for the batched A/B cursor-values endpoint (Phase 4C1
analog, Phase 4C2 digital).

JSON-first, matching every other endpoint in this API (see
app.schemas.waveform's own header note) -- a POST body rather than query
params because this request naturally carries channel lists alongside two
independent optional scalars (cursor_a_time/cursor_b_time), the same
shape FastAPI/pydantic already handle cleanly as a body model.

Analog and digital channels are two separate, explicitly-typed lists on
both the request and response (never a single untyped "channels" list) --
Phase 4C2's own smallest-maintainable-design choice: one endpoint, one
request per source, one shared pair of nearest-sample indices computed
once server-side (see extract_cursor_values's own docstring), but the
wire shape keeps analog values (float, has a unit) and digital states
(int 0/1, no unit) in clearly distinct fields rather than blurring them
into one polymorphic shape.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.waveform_service import CursorValuesResult


class CursorValuesRequest(BaseModel):
    """Request body for POST .../cursor-values.

    `analog_channel_names`/`digital_channel_names` are channel names as
    returned by GET .../channels -- unknown or wrong-kind names are
    silently omitted from the response rather than rejected (see
    extract_cursor_values's own docstring). Either list may be empty (a
    source with only digital channels displayed sends an empty
    `analog_channel_names`, and vice versa). `cursor_a_time`/
    `cursor_b_time` are elapsed seconds on this source's own native time
    axis (the same shared workspace engineering cursor time
    app.services.waveform_service already expects for start_time/
    end_time) -- omit either one (`null`/absent) when that cursor is
    off/individually closed; the response's own `cursor_a`/`cursor_b` and
    every channel's corresponding value/state are `null` in that case, and
    no per-channel work is done for it.
    """

    analog_channel_names: list[str] = []
    digital_channel_names: list[str] = []
    cursor_a_time: float | None = None
    cursor_b_time: float | None = None
    # Phase 5C (DEC-049): "engineering" (default) or "per_unit".
    unit_mode: str = "engineering"


class CursorPointOut(BaseModel):
    """One cursor's own resolution against a source's true time bounds.

    `sample_time` is `null` exactly when `requested_time` fell outside
    this source's own valid time bounds (never clamped -- section 12).
    """

    requested_time: float
    sample_time: float | None


class ChannelCursorValuesOut(BaseModel):
    """One analog channel's recorded value at cursor A/B.

    `a_value`/`b_value` are `null` exactly when that cursor was not
    supplied or fell outside this source's bounds -- never a fabricated or
    boundary-clamped value.
    """

    channel_name: str
    unit: str
    a_value: float | None
    b_value: float | None
    per_unit_status: str | None = None


class DigitalChannelCursorStateOut(BaseModel):
    """One digital channel's recorded state (0/1) at cursor A/B (Phase 4C2).

    `a_state`/`b_state` are `null` exactly when that cursor was not
    supplied or fell outside this source's bounds -- never a fabricated or
    boundary-clamped state. Plain `int` (0/1), never a float or bool, per
    the owner's explicit numeric-representation requirement.
    """

    channel_name: str
    a_state: int | None
    b_state: int | None


class CursorValuesOut(BaseModel):
    """A whole source's A/B cursor measurement batch (analog + digital)."""

    source_id: str
    cursor_a: CursorPointOut | None
    cursor_b: CursorPointOut | None
    channels: list[ChannelCursorValuesOut]
    digital_channels: list[DigitalChannelCursorStateOut]

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
                    per_unit_status=channel.per_unit_status,
                )
                for channel in result.channels
            ],
            digital_channels=[
                DigitalChannelCursorStateOut(
                    channel_name=channel.channel_name,
                    a_state=channel.a_state,
                    b_state=channel.b_state,
                )
                for channel in result.digital_channels
            ],
        )
