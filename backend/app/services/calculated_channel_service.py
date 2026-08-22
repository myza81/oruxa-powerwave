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
    OP_RMS,
    OP_SUBTRACTION,
    UNARY_OPERATIONS,
    CalculatedChannel,
    ChannelRef,
    derive_engineering_type,
    evaluate_absolute_value,
    evaluate_addition,
    evaluate_multiply_constant,
    evaluate_reverse_polarity,
    evaluate_rms,
    evaluate_subtraction,
    nominal_frequency_valid,
    rms_recording_long_enough,
    rms_sampling_dense_enough,
    timebases_aligned,
    units_compatible,
    would_create_cycle,
)
from app.domain.channel_classification import (
    UNDEFINED,
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
    derive_waveform_form,
)
from app.domain.rms_detector import (
    LIKELY_INSTANTANEOUS,
    LIKELY_MAGNITUDE_OR_RMS,
    classify_waveform_form,
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
    InvalidNominalFrequencyError,
    InvalidOperationArityError,
    RmsOverrideRequiredError,
    RmsRecordingTooShortError,
    RmsSamplingTooSparseError,
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


def _finite_or_none(value: float) -> float | None:
    """Phase 5B (DEC-048): sanitize a single sample value for a JSON
    response. RMS's leading warm-up region is ROUTINE, guaranteed NaN --
    the first calculated-channel operation to make this a normal case
    rather than an unreachable edge case. FastAPI's default JSONResponse
    calls `json.dumps(..., allow_nan=False)`, so a raw NaN reaching a
    response body would 500 the request; `None` is valid JSON `null` and
    is exactly what every existing schema field here already types this
    as (`float | None`) for the "cursor outside the recording" case, so
    this reuses that same representation rather than inventing a second
    one. Sanitizing HERE (this calculated-channel-only boundary), not
    inside `waveform_service.py`'s shared `_nearest_sample_index`/
    `_peak_in_range`/`_clip_and_reduce` primitives, keeps every
    source-channel code path -- which reuses those same primitives and
    has never produced NaN -- completely unaffected."""
    return float(value) if np.isfinite(value) else None


@dataclass(slots=True)
class _ResolvedInput:
    time: np.ndarray
    values: np.ndarray
    unit: str
    reference_source_id: str
    start_epoch: float | None
    # Phase 5A-UAT4: the input's own already-known engineering
    # classification -- a real source channel's `AnalogChannelSummary.
    # engineering_type` (computed once at import time by
    # classify_analog_channel), or another calculated channel's own
    # already-derived `engineering_type`. Feeds derive_engineering_type()
    # in create_calculated_channel() below.
    engineering_type: str
    # Phase 5B (DEC-048): the input's own TRUSTED waveform-form metadata --
    # a real source channel's `AnalogChannelSummary.waveform_form`
    # (currently always WAVEFORM_FORM_UNKNOWN for every provider, since
    # none sets it yet -- see app.domain.channel_classification's own
    # docstring), or another calculated channel's own already-derived
    # `waveform_form`. Feeds check_rms_eligibility()/derive_waveform_form()
    # below -- this is the metadata-first tier of the owner's eligibility
    # hierarchy, checked BEFORE the algorithmic detector ever runs.
    waveform_form: str


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
        # Phase 5A-UAT4: the channel was just confirmed to exist by
        # _resolve_analog_channel() above, so this always finds a match --
        # reuses that same AnalogChannelSummary the Channel Browser API
        # already serves, never a second classification pass.
        matching_channel = next(
            (ch for ch in active.metadata.analog_channels if ch.name == ref.channel_name), None
        )
        engineering_type = matching_channel.engineering_type if matching_channel else UNDEFINED
        waveform_form = matching_channel.waveform_form if matching_channel else WAVEFORM_FORM_UNKNOWN
        waveform_data = active.record.waveform_data
        time = waveform_data["time"].to_numpy()
        values = waveform_data[ref.channel_name].to_numpy()
        return _ResolvedInput(
            time=time, values=values, unit=unit,
            reference_source_id=ref.source_id, start_epoch=_source_start_epoch(active),
            engineering_type=engineering_type, waveform_form=waveform_form,
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
        # Phase 5A-UAT4: a calculated-from-calculated input passes its own
        # already-derived engineering_type back through
        # derive_engineering_type() -- this is the entire transitive-
        # propagation mechanism, no separate graph walk needed.
        engineering_type=calc.engineering_type,
        # Phase 5B: same transitive-propagation mechanism for waveform_form
        # -- an RMS-of-RMS input arrives here already carrying
        # WAVEFORM_FORM_RMS, so check_rms_eligibility() blocks it from
        # trusted metadata alone, with no detector re-run needed.
        waveform_form=calc.waveform_form,
    )


RMS_STATUS_SUITABLE = "suitable"
RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE = "likely_already_rms_or_magnitude"
RMS_STATUS_UNCERTAIN = "uncertain"


@dataclass(slots=True)
class RmsEligibility:
    status: str
    reason: str
    override_required: bool


def check_rms_eligibility(
    *,
    workspace_id: str,
    input_ref: ChannelRef,
    nominal_frequency_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> RmsEligibility:
    """The owner's metadata-first RMS-eligibility hierarchy (sections
    11-24): (1) trustworthy `waveform_form` metadata, when available --
    explicit `instantaneous` allows directly, no detector run; explicit
    `rms`/`magnitude` blocks by default, also no detector run (section 14:
    "Because this metadata is explicit/trusted, no algorithmic detector is
    needed"); (2) otherwise, the lightweight algorithmic detector
    (app.domain.rms_detector.classify_waveform_form) on the input's own
    authoritative full-resolution data.

    This is the SOLE eligibility authority -- called identically by the
    dedicated `POST .../rms-eligibility` endpoint and internally by
    `create_calculated_channel()`'s own RMS branch below, so the backend
    never trusts a client-supplied eligibility result (section 43: "the
    frontend should not be able to bypass hard/trusted-metadata guardrails
    by crafting a local result"). `override_required` reflects POLICY
    (section 23/24: block-by-default, override allowed), never whether an
    override was actually supplied -- that check happens in the caller.
    """
    resolved = _resolve_input(
        input_ref, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry
    )

    if resolved.waveform_form in (WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE):
        return RmsEligibility(
            status=RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE,
            reason="This channel is already identified as RMS or magnitude data. Applying RMS again is not recommended.",
            override_required=True,
        )
    if resolved.waveform_form == WAVEFORM_FORM_INSTANTANEOUS:
        return RmsEligibility(
            status=RMS_STATUS_SUITABLE,
            reason="Input is explicitly marked instantaneous. Input appears suitable for RMS.",
            override_required=False,
        )

    detector_result = classify_waveform_form(resolved.time, resolved.values, nominal_frequency_hz)
    if detector_result == LIKELY_INSTANTANEOUS:
        return RmsEligibility(
            status=RMS_STATUS_SUITABLE,
            reason="Input appears suitable for RMS.",
            override_required=False,
        )
    if detector_result == LIKELY_MAGNITUDE_OR_RMS:
        return RmsEligibility(
            status=RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE,
            reason=(
                "This channel appears to already be an RMS or magnitude signal. "
                "Applying RMS again may not be meaningful."
            ),
            override_required=True,
        )
    return RmsEligibility(
        status=RMS_STATUS_UNCERTAIN,
        reason="Signal form could not be confirmed. Verify that this is an instantaneous waveform before applying RMS.",
        override_required=True,
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
    override: bool = False,
) -> CalculatedChannel:
    """Validate, evaluate, and store one new calculated channel.

    Order of validation (each an independent, clearly-attributable
    rejection reason -- section 44): operation known -> arity -> name ->
    input resolution (existence) -> timebase alignment -> unit
    compatibility -> constant validity (Multiply only) / nominal-frequency
    validity + RMS eligibility + recording-duration/sampling-density
    (RMS only, Phase 5B) -> cycle guard (defensive, see
    would_create_cycle's own docstring) -> evaluate -> store. Atomic
    (section 107): nothing is written to `calc_registry` until every check
    has passed and the array has been computed -- a failed validation
    never partially registers a channel, and never touches any other
    source/calculated-channel state.

    `override` (Phase 5B, DEC-048) only ever matters for RMS: it is the
    engineer's explicit "Calculate anyway" acknowledgement, checked here
    against eligibility RE-DERIVED by this same function (never a
    client-supplied eligibility result) -- see check_rms_eligibility()'s
    own docstring for the anti-bypass rationale.
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

    # Phase 5A-UAT4: classification/grouping only -- never a second
    # eligibility gate. derive_engineering_type() already conservatively
    # falls back to UNDEFINED for a mixed/unknown set; this never blocks
    # or alters the unit/timebase checks above, which remain the sole
    # calculation-eligibility authority.
    output_engineering_type = derive_engineering_type([r.engineering_type for r in resolved])
    # Phase 5B (DEC-048): same "classification/grouping only" status as
    # engineering_type above -- derive_waveform_form() never blocks or
    # alters a calculation itself; the RMS-specific eligibility/override
    # enforcement below is a SEPARATE, deliberate gate, not this one.
    output_waveform_form = derive_waveform_form(operation, [r.waveform_form for r in resolved])

    constant: float | None = None
    nominal_frequency_hz: float | None = None
    if operation == OP_MULTIPLY_CONSTANT:
        raw_constant = parameters.get("constant") if parameters else None
        if isinstance(raw_constant, bool) or not isinstance(raw_constant, (int, float)) or not np.isfinite(raw_constant):
            raise InvalidConstantError("Constant must be a finite number.")
        constant = float(raw_constant)
    elif operation == OP_RMS:
        raw_frequency = parameters.get("nominal_frequency_hz") if parameters else None
        if not nominal_frequency_valid(raw_frequency):
            raise InvalidNominalFrequencyError(
                "Nominal frequency must be a finite number in a sensible range (e.g. 50 or 60)."
            )
        nominal_frequency_hz = float(raw_frequency)

        eligibility = check_rms_eligibility(
            workspace_id=workspace_id,
            input_ref=inputs[0],
            nominal_frequency_hz=nominal_frequency_hz,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
        if eligibility.override_required and not override:
            raise RmsOverrideRequiredError(eligibility.reason)

        # Hard data-quality constraints -- never overridable, unlike the
        # eligibility judgment above (owner section 40/41: these are not
        # a "may this signal be misinterpreted" judgment call, they are
        # "can a one-cycle RMS even be computed meaningfully at all").
        if not rms_recording_long_enough(first.time, nominal_frequency_hz):
            raise RmsRecordingTooShortError(
                "Recording is shorter than one complete RMS window."
            )
        if not rms_sampling_dense_enough(first.time, nominal_frequency_hz):
            raise RmsSamplingTooSparseError(
                "Sample rate is too low relative to the RMS window to produce a meaningful result."
            )

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
    elif operation == OP_RMS:
        values = evaluate_rms(resolved[0].time, resolved[0].values, nominal_frequency_hz)
    elif operation == OP_ADDITION:
        values = evaluate_addition([r.values for r in resolved])
    else:
        values = evaluate_subtraction([r.values for r in resolved])

    if operation == OP_MULTIPLY_CONSTANT:
        output_parameters = {"constant": constant}
    elif operation == OP_RMS:
        # Section 3: retained explicitly, never an invisibly hard-coded
        # semantic -- window_mode/rms_kind record THIS phase's fixed
        # trailing/true-RMS choice so a future differently-shaped RMS
        # variant cannot be confused with this one just by operation name.
        output_parameters = {
            "nominal_frequency_hz": nominal_frequency_hz,
            "window_mode": "trailing",
            "rms_kind": "true_rms",
        }
    else:
        output_parameters = {}

    channel = CalculatedChannel(
        id=calc_id,
        workspace_id=workspace_id,
        name=clean_name,
        unit=output_unit,
        operation=operation,
        inputs=list(inputs),
        parameters=output_parameters,
        dependency_ids=dependency_ids,
        reference_source_id=first.reference_source_id,
        time=first.time,
        values=values,
        created_at=_utc_now(),
        engineering_type=output_engineering_type,
        waveform_form=output_waveform_form,
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
                a_value=_finite_or_none(channel.values[a_index]) if a_index is not None else None,
                b_value=_finite_or_none(channel.values[b_index]) if b_index is not None else None,
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
    # Phase 5B: None when the resolved sample falls in an RMS channel's
    # own warm-up region (or any other future non-finite result) -- see
    # _finite_or_none()'s own docstring. The anchor itself (sample_index/
    # elapsed_seconds) is always valid; only the displayed engineering
    # VALUE can be unavailable.
    value: float | None


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
        value=_finite_or_none(channel.values[index]),
    )
