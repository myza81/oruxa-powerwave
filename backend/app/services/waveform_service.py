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
