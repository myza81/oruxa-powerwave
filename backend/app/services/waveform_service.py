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
                more raw samples than FULL_RESOLUTION_DISPLAY_THRESHOLD)
                -- app.domain.waveform_reduction's min/max envelope,
                never "decimation" (see that module's terminology note)

The output of this module (`WaveformRangeResult`) is always a *display
representation* when reduction was applied, and is explicitly labelled as
such (`representation` field) so nothing downstream can mistake it for
authoritative engineering data -- see DEC-019.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    UNDEFINED,
)
from app.domain.per_unit import (
    STATUS_NOT_APPLICABLE,
    PerUnitBaseProfile,
    PerUnitResolution,
    apply_per_unit_to_array,
    apply_per_unit_to_value,
    resolve_per_unit,
)
from app.domain.source import ActiveSource, DigitalChannelSummary
from app.domain.waveform_reduction import build_min_max_envelope
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import (
    ChannelNotAnalogError,
    ChannelNotDigitalError,
    ChannelNotFoundError,
    InvalidTimeRangeError,
)
from app.services.group_aware_per_unit import resolve_group_aware_per_unit
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry

UNIT_MODE_ENGINEERING = "engineering"
UNIT_MODE_PER_UNIT = "per_unit"


def _analog_channel_engineering_type(active: ActiveSource, channel_name: str) -> str:
    """Phase 5C (DEC-049): the same "look up the already-classified
    AnalogChannelSummary" pattern app.services.calculated_channel_service's
    own `_resolve_input` uses -- never a second classification pass."""
    matching = next((ch for ch in active.metadata.analog_channels if ch.name == channel_name), None)
    return matching.engineering_type if matching is not None else UNDEFINED


def _analog_channel_engineering_quantity(active: ActiveSource, channel_name: str) -> str:
    """Angle-axis enhancement (DEC-078): the same lookup pattern as
    `_analog_channel_engineering_type()` immediately above, for the
    richer, additive `engineering_quantity` field -- "Undefined" for
    every COMTRADE/calculated channel today (neither sets it) and for
    any CSV/Excel channel the engineer never classified, matching that
    field's own API-level default."""
    matching = next((ch for ch in active.metadata.analog_channels if ch.name == channel_name), None)
    return matching.engineering_quantity if matching is not None else UNDEFINED


def _resolve_effective_per_unit(
    active: ActiveSource,
    channel_name: str,
    engineering_type: str,
    per_unit_profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str] | None,
    *,
    workspace_id: str | None,
    group_registry: MeasurementGroupRegistry | None,
    voltage_config_registry: VoltageGroupConfigRegistry | None,
    current_config_registry: CurrentGroupConfigRegistry | None,
) -> PerUnitResolution:
    """DEC-050 Slice 5: the ONE dispatch point every per-unit-aware
    function below calls, instead of `resolve_per_unit()` directly.
    Attempts group-aware resolution first (only when the caller supplied
    all four new registry-scoped params -- every existing caller/test
    that omits them gets the exact previous behaviour, unchanged); if
    the channel is not a member of any `MeasurementGroup`,
    `resolve_group_aware_per_unit()` returns `None` and this falls
    through to the existing DEC-049 source-wide resolution exactly as
    before. See `app.services.group_aware_per_unit`'s own module
    docstring for the full precedence rule (DEC-051).

    Angle-axis enhancement (DEC-078) per-unit guardrail: this is the ONE
    seam that check lives in -- `engineering_quantity` is looked up
    HERE (not threaded through every one of this function's own 4 call
    sites) and, for the two angle quantities, short-circuits to
    `NOT_APPLICABLE` before EITHER the group-aware or legacy DEC-049
    path ever runs, regardless of the channel's own broad
    `engineering_type` (Voltage/Current) or whether a base is
    configured. `resolve_per_unit()`/`resolve_group_aware_per_unit()`
    themselves are UNCHANGED -- every other caller of either (e.g.
    calculated channels, which cannot carry `engineering_quantity` at
    all today) keeps today's exact engineering_type-only behavior."""
    engineering_quantity = _analog_channel_engineering_quantity(active, channel_name)
    if engineering_quantity in (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, ENGINEERING_QUANTITY_CURRENT_ANGLE):
        return PerUnitResolution(
            status=STATUS_NOT_APPLICABLE, profile_id=None, base_amount=None, base_unit=None,
            reason="engineering_quantity_angle",
        )
    resolution: PerUnitResolution | None = None
    if (
        workspace_id is not None
        and group_registry is not None
        and voltage_config_registry is not None
        and current_config_registry is not None
    ):
        resolution = resolve_group_aware_per_unit(
            workspace_id=workspace_id,
            source_id=active.metadata.source_id,
            channel_name=channel_name,
            engineering_type=engineering_type,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
    if resolution is None:
        resolution = resolve_per_unit(engineering_type, per_unit_profile, voltage_channel_names)
    return resolution

#: Starting reference point: `powerwave`'s own live desktop code
#: (`build_aligned_data`/`decimate_for_display`) uses this exact value at
#: every one of its call sites, never overridden -- see
#: docs/project-memory/MIGRATION_PLAN.md's Phase 2 design §3. Reused here
#: as a reasonable default, not because the *algorithm* it was paired with
#: there is being reused (it isn't -- see app.domain.waveform_reduction).
DEFAULT_POINT_BUDGET = 4000

#: Waveform reduction is an overview rendering optimization only. Once a
#: requested analog range is small enough to inspect directly, the display
#: must receive the exact recorded sample sequence even if the caller's
#: display budget is lower. Approved after the waveform zoom-resolution
#: investigation (DEC-041).
FULL_RESOLUTION_DISPLAY_THRESHOLD = 10_000

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
    # Phase 5C (DEC-049): `None` when unit_mode="engineering" (the
    # default -- per-unit mode was never requested for this response).
    # Otherwise one of app.domain.per_unit's three statuses; `unit`/
    # `values` above are already converted when this is "configured".
    per_unit_status: str | None = None


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


def _clip_and_reduce(
    time_full: np.ndarray,
    values_full: np.ndarray,
    *,
    start_time: float | None,
    end_time: float | None,
    point_budget: int,
) -> tuple[float, float, int, str, np.ndarray, np.ndarray]:
    """Pure array-level core of `extract_waveform_range` (Phase 5A extraction,
    DEC-047): boundary-inclusive clip + adaptive-resolution reduction,
    with no knowledge of WHOSE arrays these are -- a real source channel's,
    or (Phase 5A) a calculated channel's full-resolution result. This is
    the ONE place the full-resolution-threshold/min-max-envelope decision
    is made; `extract_waveform_range` (below) and
    `app.services.calculated_channel_service`'s own display-range
    extraction both call this directly rather than each re-implementing
    the clip+reduce decision (section 48/49 of the Phase 5A task: "reuse
    the established waveform display pipeline... never build a completely
    separate mechanism").

    Returns `(effective_start, effective_end, original_sample_count,
    representation, out_time, out_values)`.
    """
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
    elif original_sample_count <= FULL_RESOLUTION_DISPLAY_THRESHOLD:
        out_time = clipped_time
        out_values = clipped_values
        representation = REPRESENTATION_FULL_RESOLUTION
    else:
        reduction_budget = min(point_budget, FULL_RESOLUTION_DISPLAY_THRESHOLD)
        out_time, out_values = build_min_max_envelope(clipped_time, clipped_values, reduction_budget)
        representation = REPRESENTATION_MIN_MAX_ENVELOPE

    return effective_start, effective_end, original_sample_count, representation, out_time, out_values


def extract_waveform_range(
    active: ActiveSource,
    *,
    channel_name: str,
    start_time: float | None,
    end_time: float | None,
    point_budget: int,
    unit_mode: str = UNIT_MODE_ENGINEERING,
    per_unit_profile: PerUnitBaseProfile | None = None,
    voltage_channel_names: list[str] | None = None,
    workspace_id: str | None = None,
    group_registry: MeasurementGroupRegistry | None = None,
    voltage_config_registry: VoltageGroupConfigRegistry | None = None,
    current_config_registry: CurrentGroupConfigRegistry | None = None,
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

    Display-resolution semantics: if the number of raw samples actually
    inside the resolved range is <= `FULL_RESOLUTION_DISPLAY_THRESHOLD`,
    the full-resolution range is returned unchanged
    (`representation="full_resolution"`) -- no reduction is ever applied
    to a manageable event interval. Otherwise a peak-preserving min/max
    envelope is built (`representation="min_max_envelope"`, see
    app.domain.waveform_reduction) using the caller's `point_budget` as a
    display budget, capped by the full-resolution threshold so a very wide
    display cannot turn an overview range back into an unrestricted full
    sample transfer.

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

    effective_start, effective_end, original_sample_count, representation, out_time, out_values = _clip_and_reduce(
        time_full, values_full, start_time=start_time, end_time=end_time, point_budget=point_budget
    )

    per_unit_status: str | None = None
    if unit_mode == UNIT_MODE_PER_UNIT:
        engineering_type = _analog_channel_engineering_type(active, channel_name)
        resolution = _resolve_effective_per_unit(
            active, channel_name, engineering_type, per_unit_profile, voltage_channel_names,
            workspace_id=workspace_id, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        out_values, unit, per_unit_status = apply_per_unit_to_array(out_values, unit, engineering_type, resolution)

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
        per_unit_status=per_unit_status,
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
    """One analog channel's recorded Y-axis value at cursor A/B (Phase 4C1;
    terminology corrected by DEC-040's addendum -- this is a generic
    channel value, not an instantaneous-only assumption).

    `a_value`/`b_value` are `None` exactly when the corresponding cursor
    itself is `None` (not supplied) or fell outside this source's bounds
    -- never a fabricated/clamped value.
    """

    channel_name: str
    unit: str
    a_value: float | None
    b_value: float | None
    per_unit_status: str | None = None


@dataclass(slots=True)
class DigitalChannelCursorState:
    """One digital channel's recorded state (0/1) at cursor A/B (Phase 4C2).

    `a_state`/`b_state` are `None` exactly when the corresponding cursor
    itself is `None` or fell outside this source's bounds -- never a
    fabricated/clamped state. Deliberately a separate dataclass from
    `ChannelCursorValues` (no `unit`, `int` not `float`) -- see
    extract_cursor_values's own docstring for why digital state reuses
    the SAME nearest-sample indices as analog rather than a second
    transition-search algorithm.
    """

    channel_name: str
    a_state: int | None
    b_state: int | None


@dataclass(slots=True)
class CursorValuesResult:
    """A whole source's A/B cursor measurement batch (Phase 4C1 analog +
    Phase 4C2 digital).

    See app.schemas.cursor_values for the wire shape and
    extract_cursor_values's own docstring for the full engineering-rule
    rationale (full-resolution source data, nearest actual sample, one
    index lookup shared by every requested channel of EITHER kind).
    """

    source_id: str
    cursor_a: CursorPointResult | None
    cursor_b: CursorPointResult | None
    channels: list[ChannelCursorValues]
    digital_channels: list[DigitalChannelCursorState]


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
    analog_channel_names: list[str],
    digital_channel_names: list[str],
    cursor_a_time: float | None,
    cursor_b_time: float | None,
    unit_mode: str = UNIT_MODE_ENGINEERING,
    per_unit_profile: PerUnitBaseProfile | None = None,
    voltage_channel_names: list[str] | None = None,
    workspace_id: str | None = None,
    group_registry: MeasurementGroupRegistry | None = None,
    voltage_config_registry: VoltageGroupConfigRegistry | None = None,
    current_config_registry: CurrentGroupConfigRegistry | None = None,
) -> CursorValuesResult:
    """Recorded channel values/states at cursor A/B, from full-resolution
    source data (Phase 4C1 analog, Phase 4C2 digital).

    Engineering authority (section 2, DEC-040; Phase 4C2 section 3):
    ALWAYS reads `active.record.waveform_data` directly -- the same
    authoritative, never-mutated, full-resolution record
    `extract_waveform_range` itself reads (DEC-019) -- never a display/
    downsampled representation. This is a read-only analysis;
    `active.record`/`active.metadata` are never mutated (section 40).

    Digital state reuses the SAME nearest-sample lookup as analog, not a
    separate transition-interval search (Phase 4C2 section 4/26):
    `extract_digital_waveform`'s sparse transition list is itself DERIVED
    (via `np.diff`) from this exact same dense per-sample `waveform_data`
    column, sharing the identical "time" array analog channels use -- so
    the transition list is a display-oriented representation of the same
    underlying full-resolution data, not a second source of truth. Reading
    `waveform_data[digital_name]` at the nearest-sample index therefore
    both IS the full-resolution authority and naturally satisfies the
    exact-transition-timestamp rule (Phase 4C2 section 6: "state at T =
    the NEW state beginning at T") for free -- the recorded sample AT a
    transition's own timestamp already holds the new state by
    construction (see `_extract_digital_channels`/`_build_dataframe` in
    `app.providers.comtrade`), so no special-casing is needed here.

    Batching shape (section 10; Phase 4C2 section 16/17): the source's own
    shared "time" column is searched ONCE per cursor
    (`_nearest_sample_index`, at most two calls total regardless of how
    many channels of EITHER kind are requested), then every requested
    channel -- analog or digital -- just indexes its own values array at
    those two already-resolved indices -- O(2 log n + n_channels), never
    O(n_channels log n), and never a second index computation for digital.

    Unknown/wrong-kind channel names (in either list) are silently skipped
    (not raised) -- a deliberate, documented departure from
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
    digital_names = {channel.name for channel in active.metadata.digital_channels}

    channels: list[ChannelCursorValues] = []
    for name in analog_channel_names:
        unit = unit_by_name.get(name)
        if unit is None:
            continue
        values_full = waveform_data[name].to_numpy()
        a_value = float(values_full[a_index]) if a_index is not None else None
        b_value = float(values_full[b_index]) if b_index is not None else None

        display_unit = unit
        per_unit_status: str | None = None
        if unit_mode == UNIT_MODE_PER_UNIT:
            engineering_type = _analog_channel_engineering_type(active, name)
            resolution = _resolve_effective_per_unit(
                active, name, engineering_type, per_unit_profile, voltage_channel_names,
                workspace_id=workspace_id, group_registry=group_registry,
                voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
            )
            a_value, display_unit, per_unit_status = apply_per_unit_to_value(a_value, unit, engineering_type, resolution)
            b_value, display_unit, per_unit_status = apply_per_unit_to_value(b_value, unit, engineering_type, resolution)

        channels.append(
            ChannelCursorValues(
                channel_name=name, unit=display_unit, a_value=a_value, b_value=b_value,
                per_unit_status=per_unit_status,
            )
        )

    digital_channels: list[DigitalChannelCursorState] = []
    for name in digital_channel_names:
        if name not in digital_names:
            continue
        values_full = waveform_data[name].to_numpy()
        a_state = int(values_full[a_index]) if a_index is not None else None
        b_state = int(values_full[b_index]) if b_index is not None else None
        digital_channels.append(DigitalChannelCursorState(channel_name=name, a_state=a_state, b_state=b_state))

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
        digital_channels=digital_channels,
    )


@dataclass(slots=True)
class AnnotationAnchorResult:
    """Phase 4F: one authoritative full-resolution sample anchor for a
    Callout annotation (DEC-045; see app.schemas.annotation_anchor for the
    wire shape).

    Resolved ONCE, at Callout creation time only -- the frontend's own
    stored `sample_index`/`elapsed_seconds`/`value` become the
    annotation's authoritative engineering anchor from that point on and
    are never re-resolved against this service again (no backend call
    during drag/zoom/pan -- section 55 of the Phase 4F task).
    """

    source_id: str
    channel_name: str
    unit: str
    sample_index: int
    elapsed_seconds: float
    value: float
    per_unit_status: str | None = None


def resolve_annotation_anchor(
    active: ActiveSource,
    *,
    channel_name: str,
    approximate_elapsed_seconds: float,
    unit_mode: str = UNIT_MODE_ENGINEERING,
    per_unit_profile: PerUnitBaseProfile | None = None,
    voltage_channel_names: list[str] | None = None,
    workspace_id: str | None = None,
    group_registry: MeasurementGroupRegistry | None = None,
    voltage_config_registry: VoltageGroupConfigRegistry | None = None,
    current_config_registry: CurrentGroupConfigRegistry | None = None,
) -> AnnotationAnchorResult:
    """Resolve a Callout annotation's anchor to the nearest ACTUAL
    full-resolution recorded sample on one analog channel (Phase 4F,
    DEC-045).

    Deliberately reuses, rather than reimplements, the two pieces of
    logic this exact task already established elsewhere:
    `_resolve_analog_channel` (the SAME analog-only validation
    `extract_waveform_range` uses -- raises `ChannelNotFoundError` for an
    unknown channel, `ChannelNotAnalogError` for a real but digital one)
    and `_nearest_sample_index` (the SAME nearest-sample/earlier-sample-
    on-tie rule `extract_cursor_values` already uses for A/B). There is no
    second nearest-sample definition anywhere in this codebase.

    Raises `InvalidTimeRangeError` if `approximate_elapsed_seconds` falls
    outside this source's own recorded `[time[0], time[-1]]` bounds --
    deliberately never clamped to a boundary sample, matching
    `_nearest_sample_index`'s own "never clamped" contract: a Callout
    anchor is either a genuine recorded sample or a clean rejection, never
    an approximate/silent fallback (section 66 of the Phase 4F task).
    """
    unit = _resolve_analog_channel(active, channel_name)
    waveform_data = active.record.waveform_data
    time_full = waveform_data["time"].to_numpy()
    values_full = waveform_data[channel_name].to_numpy()

    index = _nearest_sample_index(time_full, approximate_elapsed_seconds)
    if index is None:
        raise InvalidTimeRangeError(
            f"approximate_elapsed_seconds ({approximate_elapsed_seconds}) is outside "
            "this source's own recorded time bounds."
        )

    value = float(values_full[index])
    per_unit_status: str | None = None
    if unit_mode == UNIT_MODE_PER_UNIT:
        engineering_type = _analog_channel_engineering_type(active, channel_name)
        resolution = _resolve_effective_per_unit(
            active, channel_name, engineering_type, per_unit_profile, voltage_channel_names,
            workspace_id=workspace_id, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        value, unit, per_unit_status = apply_per_unit_to_value(value, unit, engineering_type, resolution)

    return AnnotationAnchorResult(
        source_id=active.metadata.source_id,
        channel_name=channel_name,
        unit=unit,
        sample_index=index,
        elapsed_seconds=float(time_full[index]),
        value=value,
        per_unit_status=per_unit_status,
    )


PEAK_MODE_MAX = "max"
PEAK_MODE_MIN = "min"


@dataclass(slots=True)
class PeakValueResult:
    """Phase 4G: one Maximum/Minimum Peak annotation's dynamic measurement
    (DEC-046) -- the maximum or minimum RECORDED sample value of one analog
    channel within one requested time interval (the engineer's current
    visible X viewport, resolved by the caller -- this function has no
    concept of "viewport", only a start/end time it is given).

    `available` is `False` exactly when the requested `[start_time,
    end_time]` interval, clipped to this source's own recorded bounds,
    contains zero FINITE samples for this channel (either the intersection
    itself is empty, or every sample in it is NaN/inf -- section 14/38 of
    the Phase 4G task: a peak annotation must never resolve to a
    fabricated/non-finite value). When `available` is `False` every other
    field is `None` -- the caller (the annotation's own frontend state)
    keeps the annotation's existing identity but must not render a stale
    value as if it were current for this interval (section 67).
    """

    channel_name: str
    mode: str
    available: bool
    sample_index: int | None
    elapsed_seconds: float | None
    value: float | None
    unit: str | None
    per_unit_status: str | None = None


def _peak_in_range(
    time_full: np.ndarray,
    values_full: np.ndarray,
    *,
    mode: str,
    start_time: float,
    end_time: float,
) -> tuple[bool, int | None, float | None, float | None]:
    """Pure array-level core of `resolve_peak_value` (Phase 5A extraction,
    DEC-047): boundary-inclusive clip, non-finite masking, earliest-tie
    argmax/argmin -- no knowledge of WHOSE arrays these are. Reused by
    `resolve_peak_value` (below, source channels) AND
    `app.services.calculated_channel_service`'s own calculated-channel
    peak resolution, so there is exactly ONE peak-search implementation in
    the codebase, never two that could silently drift apart.

    Returns `(available, sample_index, elapsed_seconds, value)` --
    `sample_index` indexes into the ORIGINAL (unclipped) `time_full`/
    `values_full` arrays, matching `resolve_peak_value`'s own established
    contract.
    """
    lo = int(np.searchsorted(time_full, start_time, side="left"))
    hi = int(np.searchsorted(time_full, end_time, side="right"))
    clipped_values = values_full[lo:hi]

    finite_mask = np.isfinite(clipped_values)
    if not np.any(finite_mask):
        return False, None, None, None

    finite_values = clipped_values[finite_mask]
    finite_positions = np.nonzero(finite_mask)[0]
    local_idx = int(np.argmax(finite_values)) if mode == PEAK_MODE_MAX else int(np.argmin(finite_values))
    full_idx = lo + int(finite_positions[local_idx])

    return True, full_idx, float(time_full[full_idx]), float(values_full[full_idx])


def resolve_peak_value(
    active: ActiveSource,
    *,
    channel_name: str,
    mode: str,
    start_time: float,
    end_time: float,
    unit_mode: str = UNIT_MODE_ENGINEERING,
    per_unit_profile: PerUnitBaseProfile | None = None,
    voltage_channel_names: list[str] | None = None,
    workspace_id: str | None = None,
    group_registry: MeasurementGroupRegistry | None = None,
    voltage_config_registry: VoltageGroupConfigRegistry | None = None,
    current_config_registry: CurrentGroupConfigRegistry | None = None,
) -> PeakValueResult:
    """Resolve one analog channel's maximum or minimum RECORDED sample
    value within `[start_time, end_time]` (Phase 4G, DEC-046).

    Generic recorded-channel semantics (section 7): this is the maximum/
    minimum of whatever this channel's own recorded Y-axis values are --
    MW, kV, Hz, pu, instantaneous voltage, RMS, anything -- never a
    waveform-type-specific assumption.

    Full-resolution authority (section 8/70): always reads
    `active.record.waveform_data` directly, the SAME authoritative,
    never-mutated, full-resolution record `extract_waveform_range` and
    `resolve_annotation_anchor` already read -- never the reduced display
    envelope, regardless of how many samples fall in the requested
    interval.

    Range clipping (section 11): boundary-inclusive, via the SAME
    `np.searchsorted` technique `extract_waveform_range` already
    established -- the requested interval is clipped to this channel's own
    recorded time bounds; a viewport that extends beyond this source's
    duration is silently narrowed to the valid intersection, never
    fabricating samples outside it.

    Tie rule (section 13, DEC-046): exact ties select the EARLIEST sample.
    Reuses `numpy.argmax`/`argmin`'s own documented behaviour of returning
    the FIRST occurrence's index among tied values -- not a second,
    hand-rolled tie-break implementation.

    NaN/non-finite handling (section 14, documented per that section's
    explicit instruction): non-finite samples (`NaN`/`+inf`/`-inf`) are
    masked out via `np.isfinite` before the max/min search, so a single bad
    sample can never win or shift a tie. If every sample in the clipped
    interval is non-finite (or the interval is empty), `available=False` is
    returned -- never a fabricated peak.

    Raises `ChannelNotFoundError`/`ChannelNotAnalogError` (via the SAME
    `_resolve_analog_channel` every other analog endpoint already uses) --
    NOT wrapped here; the caller (the batched API endpoint) decides whether
    one bad channel request should fail its whole batch or just that one
    item (section 12's per-annotation "unavailable" semantics favour the
    latter).
    """
    unit = _resolve_analog_channel(active, channel_name)
    waveform_data = active.record.waveform_data
    time_full = waveform_data["time"].to_numpy()
    values_full = waveform_data[channel_name].to_numpy()

    available, sample_index, elapsed_seconds, value = _peak_in_range(
        time_full, values_full, mode=mode, start_time=start_time, end_time=end_time
    )

    per_unit_status: str | None = None
    display_unit = unit if available else None
    if available and unit_mode == UNIT_MODE_PER_UNIT:
        engineering_type = _analog_channel_engineering_type(active, channel_name)
        resolution = _resolve_effective_per_unit(
            active, channel_name, engineering_type, per_unit_profile, voltage_channel_names,
            workspace_id=workspace_id, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        value, display_unit, per_unit_status = apply_per_unit_to_value(value, unit, engineering_type, resolution)

    return PeakValueResult(
        channel_name=channel_name,
        mode=mode,
        available=available,
        sample_index=sample_index,
        elapsed_seconds=elapsed_seconds,
        value=value,
        unit=display_unit,
        per_unit_status=per_unit_status,
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
