"""Calculated Channels orchestration (Phase 5A, DEC-047).

Resolves `ChannelRef`s against the live source (`WorkspaceRegistry`) and
calculated-channel (`CalculatedChannelRegistry`) registries, runs the
arity/name/unit/timebase compatibility checks
(app.domain.calculated_channel), evaluates the requested operation ONCE
(eager evaluation, section 46), and stores the result. Also serves
calculated channels through the SAME display/cursor/peak/annotation-
anchor engineering pipelines the source-channel endpoints already use
(app.services.waveform_service's own `_clip_and_reduce`/`_peak_in_range`/
`_nearest_sample_index` -- reused directly, never reimplemented, section
48/49 of the task).

Frontend never computes engineering results (section 16): it builds a
definition, this module validates and evaluates it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

from app.domain.calculated_channel import (
    ALL_OPERATIONS,
    MAX_NAME_LENGTH,
    MULTI_OPERATIONS,
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_SUBTRACTION,
    UNARY_OPERATIONS,
    CalculatedChannel,
    ChannelRef,
    evaluate_absolute_value,
    evaluate_addition,
    evaluate_multiply_constant,
    evaluate_reverse_polarity,
    evaluate_subtraction,
    timebases_aligned,
    units_compatible,
    would_create_cycle,
)
from app.domain.source import ActiveSource
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import (
    CalculatedChannelHasDependentsError,
    CalculatedChannelNotFoundError,
    CyclicDependencyError,
    DuplicateCalculatedChannelNameError,
    IncompatibleTimeBaseError,
    IncompatibleUnitError,
    InvalidCalculatedChannelNameError,
    InvalidCalculatedOperationError,
    InvalidConstantError,
    InvalidOperationArityError,
    SourceNotFoundError,
)
from app.services.waveform_service import (
    DEFAULT_POINT_BUDGET,
    PEAK_MODE_MAX,
    PEAK_MODE_MIN,
    _clip_and_reduce,
    _nearest_sample_index,
    _peak_in_range,
    _resolve_analog_channel,
)
from app.services.workspace_registry import WorkspaceRegistry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class _ResolvedInput:
    time: np.ndarray
    values: np.ndarray
    unit: str
    reference_source_id: str
    start_epoch: float | None


def _source_start_epoch(active: ActiveSource) -> float | None:
    if active.metadata.start_time is None:
        return None
    return active.metadata.start_time.timestamp()


def _resolve_input(
    ref: ChannelRef,
    *,
    workspace_id: str,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> _ResolvedInput:
    """Resolve one `ChannelRef` to its full-resolution (time, values, unit,
    timebase-identity) tuple -- reads `active.record.waveform_data`
    directly for a source channel (the SAME authoritative record every
    other analog endpoint reads), or a calculated channel's own already-
    evaluated, retained arrays. Never touches a reduced/display
    representation.
    """
    if ref.kind == "source":
        active = source_registry.get(workspace_id, ref.source_id)
        if active is None:
            raise SourceNotFoundError(f"No source '{ref.source_id}' in workspace '{workspace_id}'.")
        unit = _resolve_analog_channel(active, ref.channel_name)  # raises ChannelNotFoundError/ChannelNotAnalogError
        waveform_data = active.record.waveform_data
        time = waveform_data["time"].to_numpy()
        values = waveform_data[ref.channel_name].to_numpy()
        return _ResolvedInput(
            time=time, values=values, unit=unit,
            reference_source_id=ref.source_id, start_epoch=_source_start_epoch(active),
        )

    calc = calc_registry.get(workspace_id, ref.calculated_channel_id)
    if calc is None:
        raise CalculatedChannelNotFoundError(f"No calculated channel '{ref.calculated_channel_id}' in this workspace.")
    # A calculated channel's own start_epoch is derived from whichever
    # real source ultimately grounds it -- resolved here (not cached on
    # the channel itself) so a since-removed source cleanly yields `None`
    # rather than a stale value; in practice this path is unreachable
    # for a channel whose reference source was removed, since source
    # removal cascades to delete every calculated channel grounded on it
    # (see remove_calculated_channels_for_source below).
    reference_source = source_registry.get(workspace_id, calc.reference_source_id)
    start_epoch = _source_start_epoch(reference_source) if reference_source is not None else None
    return _ResolvedInput(
        time=calc.time, values=calc.values, unit=calc.unit,
        reference_source_id=calc.reference_source_id, start_epoch=start_epoch,
    )


def create_calculated_channel(
    *,
    workspace_id: str,
    name: str,
    operation: str,
    inputs: list[ChannelRef],
    parameters: dict,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> CalculatedChannel:
    """Validate, evaluate, and store one new calculated channel.

    Order of validation (each an independent, clearly-attributable
    rejection reason -- section 44): operation known -> arity -> name ->
    input resolution (existence) -> timebase alignment -> unit
    compatibility -> constant validity (Multiply only) -> cycle guard
    (defensive, see would_create_cycle's own docstring) -> evaluate ->
    store. Atomic (section 107): nothing is written to `calc_registry`
    until every check has passed and the array has been computed --
    a failed validation never partially registers a channel, and never
    touches any other source/calculated-channel state.
    """
    if operation not in ALL_OPERATIONS:
        raise InvalidCalculatedOperationError(f"Unsupported operation: {operation!r}.")

    if operation in UNARY_OPERATIONS:
        if len(inputs) != 1:
            raise InvalidOperationArityError(f"{operation} requires exactly 1 input channel.")
    else:
        if len(inputs) < 2:
            raise InvalidOperationArityError(f"{operation} requires at least 2 input channels.")

    clean_name = (name or "").strip()
    if not clean_name:
        raise InvalidCalculatedChannelNameError("Name must not be empty.")
    if len(clean_name) > MAX_NAME_LENGTH:
        raise InvalidCalculatedChannelNameError(f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
    existing_names = {c.name for c in calc_registry.list_for_workspace(workspace_id)}
    if clean_name in existing_names:
        raise DuplicateCalculatedChannelNameError(f"A calculated channel named '{clean_name}' already exists.")

    resolved = [
        _resolve_input(ref, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry)
        for ref in inputs
    ]

    first = resolved[0]
    for other in resolved[1:]:
        if not timebases_aligned(
            first.reference_source_id, first.time, first.start_epoch,
            other.reference_source_id, other.time, other.start_epoch,
        ):
            raise IncompatibleTimeBaseError(
                "These channels cannot be combined because their sample times are not aligned."
            )

    if operation in MULTI_OPERATIONS:
        if not units_compatible([r.unit for r in resolved]):
            raise IncompatibleUnitError("All input channels must use the same unit to be combined.")
        output_unit = next((r.unit for r in resolved if r.unit), "") or ""
    else:
        output_unit = resolved[0].unit

    constant: float | None = None
    if operation == OP_MULTIPLY_CONSTANT:
        raw_constant = parameters.get("constant") if parameters else None
        if isinstance(raw_constant, bool) or not isinstance(raw_constant, (int, float)) or not np.isfinite(raw_constant):
            raise InvalidConstantError("Constant must be a finite number.")
        constant = float(raw_constant)

    dependency_ids = [ref.calculated_channel_id for ref in inputs if ref.kind == "calculated"]
    calc_id = "calc-" + uuid4().hex
    dependency_map = {c.id: c.dependency_ids for c in calc_registry.list_for_workspace(workspace_id)}
    if would_create_cycle(dependency_map, calc_id, dependency_ids):
        raise CyclicDependencyError("This calculation would create a circular dependency.")

    if operation == OP_REVERSE_POLARITY:
        values = evaluate_reverse_polarity(resolved[0].values)
    elif operation == OP_ABSOLUTE_VALUE:
        values = evaluate_absolute_value(resolved[0].values)
    elif operation == OP_MULTIPLY_CONSTANT:
        values = evaluate_multiply_constant(resolved[0].values, constant)
    elif operation == OP_ADDITION:
        values = evaluate_addition([r.values for r in resolved])
    else:
        values = evaluate_subtraction([r.values for r in resolved])

    channel = CalculatedChannel(
        id=calc_id,
        workspace_id=workspace_id,
        name=clean_name,
        unit=output_unit,
        operation=operation,
        inputs=list(inputs),
        parameters={"constant": constant} if constant is not None else {},
        dependency_ids=dependency_ids,
        reference_source_id=first.reference_source_id,
        time=first.time,
        values=values,
        created_at=_utc_now(),
    )
    calc_registry.add(channel)
    return channel


def delete_calculated_channel(
    *, workspace_id: str, calculated_channel_id: str, calc_registry: CalculatedChannelRegistry
) -> None:
    """Delete one calculated channel -- BLOCKED (never a silent cascade,
    section 25/63) if another calculated channel still depends on it."""
    channel = calc_registry.get(workspace_id, calculated_channel_id)
    if channel is None:
        raise CalculatedChannelNotFoundError(f"No calculated channel '{calculated_channel_id}' in this workspace.")
    dependents = [
        c for c in calc_registry.list_for_workspace(workspace_id)
        if calculated_channel_id in c.dependency_ids
    ]
    if dependents:
        names = ", ".join(f"'{d.name}'" for d in dependents)
        raise CalculatedChannelHasDependentsError(
            f"Cannot delete '{channel.name}' because the following calculated channels depend on it: {names}."
        )
    calc_registry.remove(workspace_id, calculated_channel_id)


def remove_calculated_channels_for_source(
    *, workspace_id: str, source_id: str, calc_registry: CalculatedChannelRegistry
) -> list[str]:
    """Section 64: when a source is removed, every calculated channel
    grounded on it -- directly or transitively -- must go too, never left
    "pretending to be valid." A flat filter on `reference_source_id`
    (inherited transitively through every calculated-from-calculated
    chain -- see `CalculatedChannel`'s own docstring) removes the WHOLE
    affected subtree in one pass, with no separate graph walk needed and
    no dependency-ordering concern (the entire subtree is removed
    together, so no removed channel can ever still have a live dependent
    afterward). Returns the removed ids, for logging/testing.
    """
    affected = [c.id for c in calc_registry.list_for_workspace(workspace_id) if c.reference_source_id == source_id]
    for calculated_channel_id in affected:
        calc_registry.remove(workspace_id, calculated_channel_id)
    return affected


# ------------------------------------------------------------------
# Display / measurement pipelines -- reuse the SAME engineering
# primitives waveform_service.py already established for source
# channels (section 48/49/54/55/56 of the Phase 5A task).
# ------------------------------------------------------------------


@dataclass(slots=True)
class CalculatedWaveformRangeResult:
    calculated_channel_id: str
    name: str
    unit: str
    start_time: float
    end_time: float
    original_sample_count: int
    representation: str
    time: np.ndarray
    values: np.ndarray


def extract_calculated_waveform_range(
    channel: CalculatedChannel,
    *,
    start_time: float | None,
    end_time: float | None,
    point_budget: int = DEFAULT_POINT_BUDGET,
) -> CalculatedWaveformRangeResult:
    """Display-range extraction for one calculated channel -- calls the
    SAME `_clip_and_reduce()` core the source-channel waveform endpoint
    uses (full-resolution-threshold + peak-preserving min/max envelope,
    never a second reduction algorithm, section 48/49)."""
    effective_start, effective_end, original_sample_count, representation, out_time, out_values = _clip_and_reduce(
        channel.time, channel.values, start_time=start_time, end_time=end_time, point_budget=point_budget
    )
    return CalculatedWaveformRangeResult(
        calculated_channel_id=channel.id,
        name=channel.name,
        unit=channel.unit,
        start_time=effective_start,
        end_time=effective_end,
        original_sample_count=original_sample_count,
        representation=representation,
        time=out_time,
        values=out_values,
    )


@dataclass(slots=True)
class CalculatedCursorValues:
    calculated_channel_id: str
    name: str
    unit: str
    a_value: float | None
    b_value: float | None


def extract_calculated_cursor_values(
    channels: list[CalculatedChannel],
    *,
    cursor_a_time: float | None,
    cursor_b_time: float | None,
) -> list[CalculatedCursorValues]:
    """A/B cursor values for a batch of calculated channels (section 54) --
    each channel's own full-resolution `time` array is searched
    independently (a calculated channel's `time` array is not necessarily
    identical in length/spacing to some OTHER calculated channel's, even
    though within one multi-input calculation every input shared one
    timebase) via the SAME `_nearest_sample_index()` A/B cursors already
    use for source channels -- never display points, never a second
    nearest-sample definition.
    """
    results: list[CalculatedCursorValues] = []
    for channel in channels:
        a_index = _nearest_sample_index(channel.time, cursor_a_time)
        b_index = _nearest_sample_index(channel.time, cursor_b_time)
        results.append(
            CalculatedCursorValues(
                calculated_channel_id=channel.id,
                name=channel.name,
                unit=channel.unit,
                a_value=float(channel.values[a_index]) if a_index is not None else None,
                b_value=float(channel.values[b_index]) if b_index is not None else None,
            )
        )
    return results


@dataclass(slots=True)
class CalculatedPeakResult:
    calculated_channel_id: str
    mode: str
    available: bool
    sample_index: int | None
    elapsed_seconds: float | None
    value: float | None
    unit: str | None


def resolve_calculated_peak_value(
    channel: CalculatedChannel, *, mode: str, start_time: float, end_time: float
) -> CalculatedPeakResult:
    """+Peak/-Peak for one calculated channel (section 55) -- calls the
    SAME `_peak_in_range()` core (earliest-tie argmax/argmin, non-finite
    masking) `resolve_peak_value` uses for source channels."""
    available, sample_index, elapsed_seconds, value = _peak_in_range(
        channel.time, channel.values, mode=mode, start_time=start_time, end_time=end_time
    )
    return CalculatedPeakResult(
        calculated_channel_id=channel.id,
        mode=mode,
        available=available,
        sample_index=sample_index,
        elapsed_seconds=elapsed_seconds,
        value=value,
        unit=channel.unit if available else None,
    )


@dataclass(slots=True)
class CalculatedAnnotationAnchorResult:
    calculated_channel_id: str
    unit: str
    sample_index: int
    elapsed_seconds: float
    value: float


def resolve_calculated_annotation_anchor(
    channel: CalculatedChannel, *, approximate_elapsed_seconds: float
) -> CalculatedAnnotationAnchorResult | None:
    """Callout anchor resolution for one calculated channel (section 56) --
    reuses `_nearest_sample_index()` directly, the exact same nearest-
    sample/earlier-sample-on-tie rule Callout already uses for source
    channels. Returns `None` (never clamped) when
    `approximate_elapsed_seconds` falls outside this channel's own
    recorded bounds, matching `resolve_annotation_anchor`'s own contract.
    """
    index = _nearest_sample_index(channel.time, approximate_elapsed_seconds)
    if index is None:
        return None
    return CalculatedAnnotationAnchorResult(
        calculated_channel_id=channel.id,
        unit=channel.unit,
        sample_index=index,
        elapsed_seconds=float(channel.time[index]),
        value=float(channel.values[index]),
    )
