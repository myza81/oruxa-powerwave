"""Waveform range extraction and display preparation (Phase 2A).

Owns the boundary the project's Phase 2 design settled on
(docs/project-memory/MIGRATION_PLAN.md's Phase 2 design section, §19/§6):

    ActiveSource (authoritative, full-resolution)
            |
    WaveformRangeService (this module)
            |-- exact-range extraction (always, from the authoritative
            |   record; never mutates it -- see DisturbanceRecord's and
            |   ActiveSource's own docstrings)
            `-- display preparation (only when the extracted range has
                more raw samples than the requested point_budget) --
                app.domain.waveform_reduction's min/max envelope, never
                "decimation" (see that module's terminology note)

The output of this module (`WaveformRangeResult`) is always a *display
representation* when reduction was applied, and is explicitly labelled as
such (`representation` field) so nothing downstream can mistake it for
authoritative engineering data -- see DEC-019.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.source import ActiveSource, DigitalChannelSummary
from app.domain.waveform_reduction import build_min_max_envelope
from app.services.errors import (
    ChannelNotAnalogError,
    ChannelNotDigitalError,
    ChannelNotFoundError,
    InvalidTimeRangeError,
)

#: Starting reference point: `powerwave`'s own live desktop code
#: (`build_aligned_data`/`decimate_for_display`) uses this exact value at
#: every one of its call sites, never overridden -- see
#: docs/project-memory/MIGRATION_PLAN.md's Phase 2 design §3. Reused here
#: as a reasonable default, not because the *algorithm* it was paired with
#: there is being reused (it isn't -- see app.domain.waveform_reduction).
DEFAULT_POINT_BUDGET = 4000

REPRESENTATION_FULL_RESOLUTION = "full_resolution"
REPRESENTATION_MIN_MAX_ENVELOPE = "min_max_envelope"


@dataclass(slots=True)
class WaveformRangeResult:
    """Result of one waveform range request -- see app.schemas.waveform for the wire shape."""

    source_id: str
    channel_name: str
    unit: str
    start_time: float
    end_time: float
    original_sample_count: int
    representation: str
    time: np.ndarray
    values: np.ndarray


def _resolve_analog_channel(active: ActiveSource, channel_name: str) -> str:
    """Validate channel_name and return its confirmed unit.

    Raises ChannelNotFoundError if channel_name isn't any channel on this
    source, or ChannelNotAnalogError if it names a real but digital
    channel -- digital waveform delivery is deliberately out of scope for
    Phase 2A (see app.services.errors.ChannelNotAnalogError).
    """
    for channel in active.metadata.analog_channels:
        if channel.name == channel_name:
            return channel.unit
    for channel in active.metadata.digital_channels:
        if channel.name == channel_name:
            raise ChannelNotAnalogError(
                f"Channel '{channel_name}' is a digital channel; the waveform "
                "endpoint currently serves analog channels only."
            )
    raise ChannelNotFoundError(f"No channel named '{channel_name}' on this source.")


def extract_waveform_range(
    active: ActiveSource,
    *,
    channel_name: str,
    start_time: float | None,
    end_time: float | None,
    point_budget: int,
) -> WaveformRangeResult:
    """Extract an exact time range for one analog channel, then prepare it for display.

    Time semantics: `start_time`/`end_time` are elapsed seconds on the
    same native axis as the source's own `waveform_data["time"]` column
    (matches the already-shipped Phase 1 `TimebaseOut` -- COMTRADE's
    `timing_reference` is always "absolute" by provider construction, and
    this endpoint deliberately does not introduce a second,
    trigger-relative or wall-clock axis -- see
    docs/project-memory/MIGRATION_PLAN.md's Phase 2 design §11). Omitting
    either bound defaults it to the record's own true start/end -- omitting
    both therefore returns the entire record. Boundary-inclusive at both
    ends (a sample exactly at `start_time` or `end_time` is included).

    Point-budget semantics: if the number of raw samples actually inside
    the resolved range is <= `point_budget`, the full-resolution range is
    returned unchanged (`representation="full_resolution"`) -- no
    reduction is ever applied when none is needed, so a sufficiently
    narrow request always exposes true full-resolution samples. Otherwise
    a peak-preserving min/max envelope is built
    (`representation="min_max_envelope"`, see
    app.domain.waveform_reduction) -- never plain stride sampling.

    Never mutates `active.record.waveform_data`. Raises
    app.services.errors.ChannelNotFoundError / ChannelNotAnalogError /
    InvalidTimeRangeError on bad input -- the caller (app.api.v1.sources)
    maps these onto HTTP status codes exactly like every other
    ImportServiceError subclass already in use.
    """
    if start_time is not None and end_time is not None and start_time > end_time:
        raise InvalidTimeRangeError(
            f"start_time ({start_time}) must not be greater than end_time ({end_time})."
        )

    unit = _resolve_analog_channel(active, channel_name)

    waveform_data = active.record.waveform_data
    time_full = waveform_data["time"].to_numpy()
    values_full = waveform_data[channel_name].to_numpy()

    effective_start = float(start_time) if start_time is not None else float(time_full[0])
    effective_end = float(end_time) if end_time is not None else float(time_full[-1])

    # Boundary-inclusive clip. searchsorted requires ascending order, which
    # every COMTRADE record's "time" column satisfies by construction (see
    # app.providers.comtrade) -- not re-validated here, consistent with
    # this function trusting its own authoritative record, the same way
    # app.domain.disturbance_record's own methods do.
    lo = int(np.searchsorted(time_full, effective_start, side="left"))
    hi = int(np.searchsorted(time_full, effective_end, side="right"))
    clipped_time = time_full[lo:hi]
    clipped_values = values_full[lo:hi]
    original_sample_count = int(clipped_time.shape[0])

    if original_sample_count == 0:
        out_time = clipped_time
        out_values = clipped_values
        representation = REPRESENTATION_FULL_RESOLUTION
    elif original_sample_count <= point_budget:
        out_time = clipped_time
        out_values = clipped_values
        representation = REPRESENTATION_FULL_RESOLUTION
    else:
        out_time, out_values = build_min_max_envelope(clipped_time, clipped_values, point_budget)
        representation = REPRESENTATION_MIN_MAX_ENVELOPE

    return WaveformRangeResult(
        source_id=active.metadata.source_id,
        channel_name=channel_name,
        unit=unit,
        start_time=effective_start,
        end_time=effective_end,
        original_sample_count=original_sample_count,
        representation=representation,
        time=out_time,
        values=out_values,
    )


@dataclass(slots=True)
class CursorPointResult:
    """One cursor's own resolution against a source's true time bounds.

    `sample_time` is `None` exactly when `requested_time` fell outside this
    source's own `[time[0], time[-1]]` bounds (section 12 -- never
    clamped/pretended-in-bounds; a source that ends before the requested
    cursor time simply has no measurement there).
    """

    requested_time: float
    sample_time: float | None


@dataclass(slots=True)
class ChannelCursorValues:
    """One analog channel's instantaneous value at cursor A/B (Phase 4C1).

    `a_value`/`b_value` are `None` exactly when the corresponding cursor
    itself is `None` (not supplied) or fell outside this source's bounds
    -- never a fabricated/clamped value.
    """

    channel_name: str
    unit: str
    a_value: float | None
    b_value: float | None


@dataclass(slots=True)
class CursorValuesResult:
    """A whole source's instantaneous A/B measurement batch (Phase 4C1).

    See app.schemas.cursor_values for the wire shape and
    extract_cursor_values's own docstring for the full engineering-rule
    rationale (full-resolution source data, nearest actual sample, one
    index lookup shared by every requested channel).
    """

    source_id: str
    cursor_a: CursorPointResult | None
    cursor_b: CursorPointResult | None
    channels: list[ChannelCursorValues]


def _nearest_sample_index(time_full: np.ndarray, requested_time: float | None) -> int | None:
    """Nearest-actual-sample index into `time_full` for one cursor time.

    Section 3/11: never interpolates, never derives an index via
    `round(time * nominal_rate)` -- COMTRADE may be multi-rate and a
    nominal rate is not necessarily authoritative for every sample, so
    this always searches the source's own real time array
    (`np.searchsorted`, O(log n), never a full linear scan -- section 10).

    Section 12: returns `None` (never clamped) when `requested_time` is
    `None`, the array is empty, or `requested_time` falls outside this
    source's own `[time_full[0], time_full[-1]]` bounds.

    Section 42 (tie behaviour, deliberately documented): when
    `requested_time` is exactly equidistant between two neighbouring
    samples, the EARLIER sample wins -- chosen so a measurement never
    reads a moment that has not "happened yet" relative to the requested
    time, consistent with `numpy.searchsorted(..., side="left")`'s own
    convention of preferring the lower insertion point for exact/ambiguous
    matches, reused here rather than a second convention.
    """
    if requested_time is None or time_full.size == 0:
        return None
    if requested_time < time_full[0] or requested_time > time_full[-1]:
        return None

    idx = int(np.searchsorted(time_full, requested_time, side="left"))
    if idx <= 0:
        return 0
    if idx >= time_full.size:
        return int(time_full.size - 1)

    before = time_full[idx - 1]
    after = time_full[idx]
    if (requested_time - before) <= (after - requested_time):
        return idx - 1
    return idx


def extract_cursor_values(
    active: ActiveSource,
    *,
    channel_names: list[str],
    cursor_a_time: float | None,
    cursor_b_time: float | None,
) -> CursorValuesResult:
    """Instantaneous analog values at cursor A/B, from full-resolution source data (Phase 4C1).

    Engineering authority (section 2, DEC-040): ALWAYS reads
    `active.record.waveform_data` directly -- the same authoritative,
    never-mutated, full-resolution record `extract_waveform_range` itself
    reads (DEC-019) -- never a display/downsampled representation. This is
    a read-only analysis; `active.record`/`active.metadata` are never
    mutated (section 40).

    Batching shape (section 10): the source's own shared "time" column is
    searched ONCE per cursor (`_nearest_sample_index`, at most two calls
    total regardless of how many channels are requested), then every
    requested channel just indexes its own values array at those two
    already-resolved indices -- O(2 log n + n_channels), never
    O(n_channels log n).

    Unknown/non-analog channel names are silently skipped (not raised) --
    a deliberate, documented departure from
    `extract_digital_waveform`/`get_source_digital_waveform`'s own
    all-or-nothing batch behaviour, chosen because this endpoint backs a
    live-dragging UI where one stale/renamed channel must never blank out
    every other channel's otherwise-valid measurement (section 38: "do not
    break waveform rendering... do not show fabricated values" -- omission
    is the correct degradation, not a hard failure).
    """
    waveform_data = active.record.waveform_data
    time_full = waveform_data["time"].to_numpy()

    a_index = _nearest_sample_index(time_full, cursor_a_time)
    b_index = _nearest_sample_index(time_full, cursor_b_time)

    unit_by_name = {channel.name: channel.unit for channel in active.metadata.analog_channels}

    channels: list[ChannelCursorValues] = []
    for name in channel_names:
        unit = unit_by_name.get(name)
        if unit is None:
            continue
        values_full = waveform_data[name].to_numpy()
        a_value = float(values_full[a_index]) if a_index is not None else None
        b_value = float(values_full[b_index]) if b_index is not None else None
        channels.append(ChannelCursorValues(channel_name=name, unit=unit, a_value=a_value, b_value=b_value))

    cursor_a = (
        CursorPointResult(
            requested_time=cursor_a_time,
            sample_time=float(time_full[a_index]) if a_index is not None else None,
        )
        if cursor_a_time is not None
        else None
    )
    cursor_b = (
        CursorPointResult(
            requested_time=cursor_b_time,
            sample_time=float(time_full[b_index]) if b_index is not None else None,
        )
        if cursor_b_time is not None
        else None
    )

    return CursorValuesResult(
        source_id=active.metadata.source_id,
        cursor_a=cursor_a,
        cursor_b=cursor_b,
        channels=channels,
    )


@dataclass(slots=True)
class DigitalTransition:
    time: float
    state: int


@dataclass(slots=True)
class DigitalWaveformResult:
    """One digital channel's full-record transition list (Phase 4A).

    See app.schemas.digital_waveform for the wire shape.

    Deliberately NOT a dense sample array and NOT point-budget-reduced:
    digital data is a step function, so the minimal, engineering-safe
    representation is the initial state plus every transition edge (see
    this module's own top-level docstring update note, and DEC-019's
    caution against ever applying analog-style envelope reduction to
    digital data -- transitions are already sparse for any real
    protection/status channel, so returning all of them is both the most
    truthful AND the smallest-payload representation, not a tradeoff).
    """

    source_id: str
    channel_name: str
    classification: str
    normal_state: int
    initial_state: int
    transitions: list[DigitalTransition]
    start_time: float
    end_time: float
    sample_count: int


def _resolve_digital_channel(active: ActiveSource, channel_name: str) -> DigitalChannelSummary:
    """Validate channel_name and return its DigitalChannelSummary.

    Raises ChannelNotFoundError if channel_name isn't any channel on this
    source, or ChannelNotDigitalError if it names a real but analog
    channel -- symmetric with _resolve_analog_channel above.
    """
    for channel in active.metadata.digital_channels:
        if channel.name == channel_name:
            return channel
    for channel in active.metadata.analog_channels:
        if channel.name == channel_name:
            raise ChannelNotDigitalError(
                f"Channel '{channel_name}' is an analog channel; the digital-waveform "
                "endpoint serves digital channels only."
            )
    raise ChannelNotFoundError(f"No channel named '{channel_name}' on this source.")


def extract_digital_waveform(active: ActiveSource, *, channel_name: str) -> DigitalWaveformResult:
    """Extract one digital channel's full-record transition list.

    Always the full record -- no start_time/end_time/point_budget
    parameters, deliberately (see this module's own investigation record
    in docs/project-memory/MIGRATION_PLAN.md's Phase 4A entry): a real
    protection/status channel's transition COUNT is already tiny relative
    to its sample count, so range-scoping and reduction would only add
    request complexity without a measured payload-size problem to solve.
    The frontend fetches this once per displayed digital channel and
    re-renders presentation-only (viewport zoom/pan, Absolute/Elapsed) —
    exactly like the shared time-mode conversion already established for
    analog panels (DEC-029), never a second data fetch.

    Never mutates `active.record.waveform_data`. Raises
    app.services.errors.ChannelNotFoundError / ChannelNotDigitalError —
    mapped onto HTTP status codes the same way every other
    ImportServiceError subclass already is.
    """
    channel = _resolve_digital_channel(active, channel_name)

    waveform_data = active.record.waveform_data
    time_full = waveform_data["time"].to_numpy()
    values_full = waveform_data[channel_name].to_numpy()

    if values_full.size == 0:
        return DigitalWaveformResult(
            source_id=active.metadata.source_id,
            channel_name=channel_name,
            classification=channel.classification,
            normal_state=channel.normal_state,
            initial_state=0,
            transitions=[],
            start_time=0.0,
            end_time=0.0,
            sample_count=0,
        )

    # Vectorized edge-finding: np.diff flags every sample-to-sample change;
    # nonzero() gives the indices of the SAMPLE AFTER each change (the new
    # state's own first sample) -- only actual transitions are then
    # iterated in the Python loop below, never the full sample array, so
    # this stays fast regardless of the record's raw sample count.
    change_indices = np.nonzero(np.diff(values_full) != 0)[0] + 1
    transitions = [
        DigitalTransition(time=float(time_full[i]), state=int(values_full[i]))
        for i in change_indices
    ]

    return DigitalWaveformResult(
        source_id=active.metadata.source_id,
        channel_name=channel_name,
        classification=channel.classification,
        normal_state=channel.normal_state,
        initial_state=int(values_full[0]),
        transitions=transitions,
        start_time=float(time_full[0]),
        end_time=float(time_full[-1]),
        sample_count=int(values_full.shape[0]),
    )
