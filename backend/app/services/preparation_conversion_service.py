"""Canonical Conversion to Powerwave `DisturbanceRecord` (CSV/Excel
ingestion Slice 10, DEC-072).

The canonical-boundary crossing this feature has been building toward
since Slice 7:

    Slice 8  -> interpret (time-axis interpretation)
    Slice 9  -> validate  (Full Powerwave Readiness Validator)
    Slice 10 -> convert   (THIS module)

**No new inference happens here.** Every per-row time value comes from
re-calling the ALREADY-CONFIRMED time-axis interpreter's own
`build_preview_rows()` (the exact same Protocol method the Time Axis
review UI already uses) over the FULL active region -- never a second,
divergent parsing/reconstruction/cadence-estimation implementation.
This module's own job is narrowly: re-verify readiness, walk the
already-decided per-row strings into canonical floats, assemble a
`DisturbanceRecord`, validate it, and register it -- never decide what
a value MEANS.

**Re-checks readiness fresh, every time** (task's own explicit "never
trust stale frontend state" rule): `app.services.preparation_issue_
service.build_issue_summary()` is called again here, live, regardless
of whatever the frontend last displayed. A single revision is captured
at the START and re-verified immediately before registration (task
section V) -- if the working overlay changed in between, the whole
attempt is discarded (`ConversionRevisionChangedError`) and preparation
state is left completely untouched.

**Index-only is not canonical-seconds-ready** (task's own explicit
owner decision, section 2): `sample_index` + `provenance=index_only`
is a legitimate, Slice-9-approved READY (with warning) state -- but it
is a CONVERSION capability constraint, not a readiness failure, that
this specific combination cannot honestly become a seconds-based
`waveform_data["time"]` column. `ConversionRequiresIntervalError` is
raised instead of ever pretending `sample 5 = 5 seconds`.

**`manual`/`unsupported` interpreters cannot convert either** -- for a
different, related reason: neither ever parses a real per-row value
from the source's own columns at all (see `app.services.time_axis_
service._ManualInterpreter`), so there is nothing honest for this
module to "consume." `ConversionUnsupportedInterpreterError` covers
this.

**No fake dates, ever** (task's own explicit rule): `TimingInformation.
start_time`/`.trigger_time` are `None` whenever genuinely unknown (see
`app.domain.timing`'s own Slice 10 hardening note) -- never `1970-01-
01`, never `2000-01-01`, never `trigger_time = start_time`. CSV/Excel
recordings carry no trigger concept at all today, so `trigger_time` is
always `None` for a source converted here.

**Row selection**: exactly `active data region - excluded rows +
current working cell overrides` (task section B) -- powered by
`app.services.preparation_preview_service.iterate_active_region_rows()`,
the SAME single-pass streaming generator Slice 9's own readiness
validator uses, filtered here to non-excluded, non-header, in-region
rows only. The raw source is never touched.

**Waveform channels**: only columns CURRENTLY carrying the Waveform
Channel role, in source column order (task section K, never
alphabetical). Duplicate display labels never collapse channels (task
section J) -- the first column to use a given label keeps it verbatim;
every later column sharing that label gets a stable `__{Spreadsheet
Letter}` suffix (`Voltage`, `Voltage__C`, `Voltage__D`), with the
ORIGINAL display label preserved separately on `AnalogChannel.
description` so it is never lost. Digital channels are always `[]` --
Slice 9 already established that the column-role model has no
dedicated digital role yet (see `app.services.readiness_service`'s own
docstring); nothing here invents one.

**Sampling metadata is honest about irregularity** (task sections M/N):
`SamplingInformation.is_uniform` (Slice 10's own additive hardening) is
`True` only when every consecutive canonical-time delta stays within
`_UNIFORM_INTERVAL_RELATIVE_TOLERANCE` (±1%, the SAME convention
`non_uniform_elapsed_interval` already established in Slice 8B) of the
sequence's own median delta -- `sampling_rates`/`samples_per_rate`
still carry a best-effort nominal single-section summary either way
(for display), but the AUTHORITATIVE per-sample timing is always
`waveform_data["time"]` itself, never a fabricated average passed off
as uniform.

**Provenance** (task section O): a small, generic, JSON-safe dict on
`SourceMetadata.preparation_provenance` (Slice 10's own additive
field) -- source format, original filename, worksheet name/index,
preparation revision, time family/provenance/interpreter id/unit/
interval, reconstruction status, header row, data region, excluded row
count. Never written into `waveform_data` itself.

**Idempotency** (task section S): conversion REMOVES the preparation
session on success (mirroring how a COMTRADE upload never leaves a
"Needs Preparation" row behind either) -- a repeated conversion request
against the same (now-gone) `source_id` simply 404s with the ordinary
`SourceNotFoundError` every other endpoint already uses for an unknown
source. No separate duplicate-detection table, no elaborate
persistence -- the registry's own existing removal semantics are the
entire idempotency story.

**Never repairs anything**: no row is ever deleted, inserted, sorted,
or reordered by this module; no timestamp is ever synthesized; no
waveform value is ever interpolated or coerced. A contradiction found
during canonical construction (task section E) is reported via
`ConversionValidationError`, never silently corrected.

**Performance** (task section AB): one single-pass stream
(`iterate_active_region_rows`) builds only the two in-memory
structures conversion actually needs (the time-axis sample list, and a
`row_number -> {column_index: float}` waveform-value map) -- the final
`pandas.DataFrame` is constructed exactly once, from those, at the very
end. No raw-copy + working-copy + normalized-copy + canonical-copy
ever coexist.
"""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from typing import Any

import pandas as pd

from app.domain.channel_classification import classify_analog_channel
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.preparation_issue import SEVERITY_BLOCKING
from app.domain.preparation_session import PreparationSession
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata, utc_now
from app.domain.time_axis import (
    FAMILY_ABSOLUTE,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    INTERPRETER_ID_MANUAL,
    INTERPRETER_ID_UNSUPPORTED,
    PROVENANCE_RECONSTRUCTED,
    TimeAxisSampleRow,
)
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.working_overlay import ROLE_WAVEFORM
from app.services.errors import (
    ConversionNotReadyError,
    ConversionRequiresIntervalError,
    ConversionRevisionChangedError,
    ConversionUnsupportedInterpreterError,
    ConversionValidationError,
    SourceNotFoundError,
    WorksheetNotSelectedError,
)
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_preview_service import (
    _spreadsheet_column_label,
    iterate_active_region_rows,
    preview_preparation_source,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_interpreters import _to_float
from app.services.time_axis_service import get_time_axis_summary, resolve_interpreter
from app.services.workspace_registry import WorkspaceRegistry

#: CSV/Excel sources declare no nominal system frequency at all -- this
#: is a CONVENTIONAL DEFAULT (never a detected value), recorded as such
#: in `preparation_provenance` (`nominal_frequency_assumed: True`) so
#: nothing downstream mistakes it for a real, source-declared value.
#: `RecordingMetadata.nominal_frequency`/`SourceMetadata.
#: nominal_frequency` stay REQUIRED fields (unlike `TimingInformation`'s
#: own `start_time`/`trigger_time`) because `app.services.
#: synchronization_service`'s event-detection sensitivity calculation
#: already consumes them as a real float -- widening those to Optional
#: would be exactly the "existing waveform integration" redesign this
#: slice must not perform.
_DEFAULT_NOMINAL_FREQUENCY_HZ = 50.0

#: A transition is treated as "uniform" when every consecutive
#: canonical-time delta stays within this RELATIVE tolerance of the
#: sequence's own median delta -- the SAME ±1% convention Slice 8B's
#: own `non_uniform_elapsed_interval` already established. Loose enough
#: to tolerate ordinary floating-point jitter from the string-round-
#: tripped conversion below, tight enough that genuinely irregular
#: timing is still correctly reported as non-uniform (never claimed
#: uniform merely by averaging it away).
_UNIFORM_INTERVAL_RELATIVE_TOLERANCE = 0.01


def _resolve_session(*, workspace_id: str, source_id: str, registry: PreparationSessionRegistry) -> PreparationSession:
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(f"No preparation source '{source_id}' in workspace '{workspace_id}'.")
    return session


def _resolve_worksheet_index(session: PreparationSession) -> int | None:
    worksheets = session.summary.worksheets
    if not worksheets:
        return None
    if session.summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before converting it."
        )
    return session.summary.selected_worksheet_index


def _parse_absolute(interpreted: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(interpreted)
    except ValueError:
        return None


def _parse_partial(interpreted: str) -> dt.time | None:
    try:
        return dt.datetime.strptime(interpreted, "%H:%M:%S.%f").time()
    except ValueError:
        return None


def _parse_seconds_suffix(interpreted: str) -> float | None:
    """Both `build_elapsed_preview` and `build_sample_index_preview`
    format their own resolved value as `f"{seconds:.6f} s"` -- one
    shared parser for that one shared shape."""
    text = interpreted.strip()
    if text.endswith(" s"):
        text = text[:-2]
    try:
        return float(text)
    except ValueError:
        return None


def _seconds_from_midnight(value: dt.time) -> float:
    return value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1_000_000


def _canonical_time_and_anchor(preview_rows, *, family: str) -> tuple[list[float], dt.datetime | None]:
    """Turns the CONFIRMED interpreter's own already-resolved `interpreted`
    strings into canonical `time` floats, relative to the FIRST active
    row (task section C's own "preferred direction" for every family --
    `sample_index`'s own preview builder already produces exactly this
    shape, so subtracting its own first value again is a harmless
    identity operation). Returns `(canonical_seconds_per_row, anchor)`
    where `anchor` is the real first-row `datetime` for `FAMILY_ABSOLUTE`
    (used by the caller to populate `TimingInformation.start_time`
    honestly) and `None` otherwise. Raises `ConversionValidationError`
    defensively for any row Slice 9's own readiness pass should already
    have prevented from reaching here (task section E) -- never silently
    skipped or dropped.
    """
    natives: list[tuple[int, Any]] = []
    for row in preview_rows:
        if row.interpreted is None:
            raise ConversionValidationError(
                f"Row {row.row_number}'s Time Axis value could not be interpreted under the confirmed configuration."
            )
        if family == FAMILY_ABSOLUTE:
            native = _parse_absolute(row.interpreted)
        elif family == FAMILY_PARTIAL:
            native = _parse_partial(row.interpreted)
        else:
            native = _parse_seconds_suffix(row.interpreted)
        if native is None:
            raise ConversionValidationError(
                f"Row {row.row_number}'s Time Axis value '{row.interpreted}' could not be parsed during conversion."
            )
        natives.append((row.row_number, native))

    if not natives:
        raise ConversionValidationError("No active rows with a Time Axis value were found to convert.")

    anchor = natives[0][1] if family == FAMILY_ABSOLUTE else None
    canonical: list[float] = []
    if family == FAMILY_ABSOLUTE:
        first = natives[0][1]
        for row_number, native in natives:
            try:
                canonical.append((native - first).total_seconds())
            except TypeError as exc:
                raise ConversionValidationError(
                    f"Row {row_number} mixes a timezone-aware timestamp with the first active row's own "
                    "naive (or vice-versa) timestamp -- cannot compute relative time."
                ) from exc
    elif family == FAMILY_PARTIAL:
        first_seconds = _seconds_from_midnight(natives[0][1])
        for _row_number, native in natives:
            canonical.append(_seconds_from_midnight(native) - first_seconds)
    else:
        first_value = float(natives[0][1])
        for _row_number, native in natives:
            canonical.append(float(native) - first_value)

    return canonical, anchor


def _unique_channel_names(column_labels: list[str], waveform_column_indices: list[int]) -> dict[int, tuple[str, str]]:
    """One `(canonical_name, display_label)` pair per waveform column,
    in SOURCE column order (task section K -- callers must iterate
    `waveform_column_indices` in ascending order, never re-sort). The
    FIRST column to use a given display label keeps it verbatim; every
    LATER column sharing that same label gets a stable
    `__{SpreadsheetLetter}` suffix (task section J's own suggested
    strategy: `Voltage`, `Voltage__C`, `Voltage__D`) -- deterministic
    (keyed by the column's own stable position, never a fragile
    incrementing counter alone) and NEVER an unpredictable rename. The
    original display label is always still returned alongside, so the
    caller can preserve it (via `AnalogChannel.description`) even when
    the canonical name itself had to be disambiguated."""
    seen: dict[str, int] = {}
    result: dict[int, tuple[str, str]] = {}
    for column_index in waveform_column_indices:
        label = (
            column_labels[column_index]
            if column_index < len(column_labels)
            else _spreadsheet_column_label(column_index)
        )
        count = seen.get(label, 0)
        seen[label] = count + 1
        canonical = label if count == 0 else f"{label}__{_spreadsheet_column_label(column_index)}"
        result[column_index] = (canonical, label)
    return result


def convert_preparation_source(
    *,
    workspace_id: str,
    source_id: str,
    preparation_registry: PreparationSessionRegistry,
    workspace_registry: WorkspaceRegistry,
) -> SourceMetadata:
    """Convert one READY CSV/Excel preparation source into a canonical
    `DisturbanceRecord`, register it into `workspace_registry` exactly
    like a COMTRADE upload already does, and release the preparation
    session. Raises an `ImportServiceError` subclass (never a
    `PreparationIssue`) for every runtime/capability failure -- see
    this module's own docstring and `app.services.errors`'s own new
    `Conversion*` classes. On ANY failure, the preparation session (and
    its own current working state) is left completely untouched.
    """
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=preparation_registry)
    worksheet_index = _resolve_worksheet_index(session)
    captured_revision = session.working_overlay.revision

    # 1. Readiness must be rechecked at conversion time -- never trust
    # stale frontend state (task's own explicit rule).
    issue_summary = build_issue_summary(workspace_id=workspace_id, source_id=source_id, registry=preparation_registry)
    if not issue_summary.is_ready:
        blocking_messages = [i.message for i in issue_summary.issues if i.severity == SEVERITY_BLOCKING]
        raise ConversionNotReadyError(
            "This source is not yet ready to convert to Powerwave: " + " ".join(blocking_messages)
        )

    time_axis_summary = get_time_axis_summary(workspace_id=workspace_id, source_id=source_id, registry=preparation_registry)

    if time_axis_summary.interpreter_id in (INTERPRETER_ID_MANUAL, INTERPRETER_ID_UNSUPPORTED):
        raise ConversionUnsupportedInterpreterError(
            "The active Time Axis configuration does not parse real per-row values from this source's own "
            "columns -- assign a real interpreter (Absolute Datetime, Date + Time, Elapsed Time, Sample Index, "
            "or Repeated Timestamp) before converting to Powerwave."
        )

    if time_axis_summary.family == FAMILY_SAMPLE_INDEX and time_axis_summary.interval_seconds is None:
        raise ConversionRequiresIntervalError(
            "A sampling interval or sampling rate is required before this sample-index dataset can be "
            "converted to Powerwave time in seconds. Return to Time Axis configuration and provide one."
        )

    interpreter = resolve_interpreter(
        column_count=len(time_axis_summary.column_indices), requested_interpreter_id=time_axis_summary.interpreter_id,
    )

    # 2. Resolve the current working dataset: active data region, minus
    # excluded rows, with current working cell overrides already
    # applied by iterate_active_region_rows() -- one single streaming
    # pass builds both the time-axis sample list and the waveform
    # value map together.
    waveform_column_indices = sorted(
        c for (ws, c), role in session.working_overlay.column_roles.items()
        if ws == worksheet_index and role == ROLE_WAVEFORM
    )

    time_axis_samples: list[TimeAxisSampleRow] = []
    waveform_values_by_row: dict[int, dict[int, float]] = {}
    row_order: list[int] = []
    for row in iterate_active_region_rows(session, worksheet_index=worksheet_index):
        if row.excluded or row.is_header or not row.in_active_region:
            continue
        values = tuple(row.cells[c] if c < len(row.cells) else None for c in time_axis_summary.column_indices)
        time_axis_samples.append(TimeAxisSampleRow(row_number=row.row_number, values=values))
        row_values: dict[int, float] = {}
        for column_index in waveform_column_indices:
            raw_value = row.cells[column_index] if column_index < len(row.cells) else None
            parsed = _to_float(raw_value)
            if parsed is None:
                raise ConversionValidationError(
                    f"Row {row.row_number}'s Waveform Channel value at column {column_index} could not be "
                    "interpreted as numeric during conversion."
                )
            row_values[column_index] = parsed
        waveform_values_by_row[row.row_number] = row_values
        row_order.append(row.row_number)

    if not row_order:
        raise ConversionValidationError("No active rows were found to convert.")

    # 3. Construct the canonical time axis -- reusing the CONFIRMED
    # interpreter's own build_preview_rows() over the FULL active
    # region (never a bounded sample, never a second reconstruction).
    preview_rows = interpreter.build_preview_rows(
        samples=time_axis_samples,
        resolved_options=time_axis_summary.options,
        resolved_unit=time_axis_summary.unit,
        resolved_interval_seconds=time_axis_summary.interval_seconds,
        limit=len(time_axis_samples),
    )
    canonical_time, absolute_anchor = _canonical_time_and_anchor(preview_rows, family=time_axis_summary.family)

    if len(canonical_time) != len(row_order):
        raise ConversionValidationError("Canonical time values did not align one-to-one with active waveform rows.")

    # 4. Construct waveform channels -- source column order, duplicate
    # labels preserved via stable unique names (task sections H-K).
    preview = preview_preparation_source(
        workspace_id=workspace_id, source_id=source_id, offset=0, limit=1, registry=preparation_registry,
    )
    name_by_column = _unique_channel_names(preview.column_labels, waveform_column_indices)

    data: dict[str, list[float]] = {"time": canonical_time}
    analog_channels: list[AnalogChannel] = []
    for position, column_index in enumerate(waveform_column_indices):
        canonical_name, display_label = name_by_column[column_index]
        data[canonical_name] = [waveform_values_by_row[row_number][column_index] for row_number in row_order]
        analog_channels.append(
            AnalogChannel(name=canonical_name, unit="", index=position, description=display_label)
        )
    waveform_data = pd.DataFrame(data)

    if not analog_channels:
        # Already guaranteed by readiness's own waveform_channel_missing
        # check -- defensive only (task section E).
        raise ConversionValidationError("No Waveform Channel columns were found to convert.")

    # 5. Sampling metadata -- honest about irregularity (task sections M/N).
    deltas = [canonical_time[i + 1] - canonical_time[i] for i in range(len(canonical_time) - 1)]
    positive_deltas = [d for d in deltas if d > 0]
    is_uniform = True
    nominal_interval_seconds: float | None = None
    if positive_deltas:
        nominal_interval_seconds = statistics.median(positive_deltas)
        tolerance = max(1e-9, nominal_interval_seconds * _UNIFORM_INTERVAL_RELATIVE_TOLERANCE)
        is_uniform = all(abs(d - nominal_interval_seconds) <= tolerance for d in deltas)
    nominal_rate_hz = (1.0 / nominal_interval_seconds) if nominal_interval_seconds else 0.0
    sampling_info = SamplingInformation(
        sampling_rates=[nominal_rate_hz], samples_per_rate=[len(row_order)],
        nominal_frequency=None, is_uniform=is_uniform,
    )

    # 6. Timing metadata -- no fake dates, no fake trigger (task
    # sections F/G).
    timing_reference = "absolute" if time_axis_summary.family == FAMILY_ABSOLUTE else "relative_elapsed"
    start_time = absolute_anchor if time_axis_summary.family == FAMILY_ABSOLUTE else None
    timezone_label: str | None = None
    if start_time is not None and start_time.tzinfo is not None:
        offset_text = start_time.strftime("%z")
        timezone_label = f"{offset_text[:3]}:{offset_text[3:]}" if offset_text else None
    timing_info = TimingInformation(
        start_time=start_time, trigger_time=None,
        timezone=timezone_label, timing_reference=timing_reference, time_axis_unit=time_axis_summary.unit,
    )

    # 7. Provenance/source metadata (task section O).
    region = session.working_overlay.data_region.get(worksheet_index)
    provenance: dict[str, Any] = {
        "source_format": session.summary.source_format,
        "original_filename": session.summary.original_filename,
        "worksheet_name": session.summary.worksheets[worksheet_index].name if worksheet_index is not None else None,
        "worksheet_index": worksheet_index,
        "preparation_revision": captured_revision,
        "time_family": time_axis_summary.family,
        "time_provenance": time_axis_summary.provenance,
        "interpreter_id": time_axis_summary.interpreter_id,
        "time_unit": time_axis_summary.unit,
        "time_interval_seconds": time_axis_summary.interval_seconds,
        "reconstructed": time_axis_summary.provenance == PROVENANCE_RECONSTRUCTED,
        "header_row_number": session.working_overlay.header_row.get(worksheet_index),
        "data_region": (
            {"start_row": region.start_row, "end_mode": region.end_mode, "end_row": region.end_row}
            if region is not None else None
        ),
        "excluded_row_count": sum(1 for (ws, _rn) in session.working_overlay.excluded_rows if ws == worksheet_index),
        "nominal_frequency_assumed": True,
    }
    if time_axis_summary.family != FAMILY_ABSOLUTE and preview_rows[0].interpreted is not None and preview_rows[0].interpreted.endswith(" s"):
        provenance["source_time_offset_seconds"] = _parse_seconds_suffix(preview_rows[0].interpreted)

    recording_metadata = RecordingMetadata(
        station_name=session.summary.original_filename,
        recorder_name="CSV/Excel Import",
        source_file=session.summary.original_filename,
        provider_type=session.summary.source_format.lower(),
        nominal_frequency=_DEFAULT_NOMINAL_FREQUENCY_HZ,
    )

    record = DisturbanceRecord(
        metadata=recording_metadata,
        waveform_data=waveform_data,
        analog_channels=analog_channels,
        digital_channels=[],
        sampling_info=sampling_info,
        timing_info=timing_info,
    )

    validation_errors = record.validate()
    if validation_errors:
        raise ConversionValidationError("Canonical record failed validation: " + "; ".join(validation_errors))

    # 8. Revision race protection (task section V) -- verify the
    # working overlay has not changed since conversion began, right
    # before this attempt becomes visible to the rest of the workspace.
    if session.working_overlay.revision != captured_revision:
        raise ConversionRevisionChangedError(
            "This preparation source changed while conversion was in progress -- please retry."
        )

    new_source_id = str(uuid.uuid4())
    metadata = SourceMetadata(
        source_id=new_source_id,
        workspace_id=workspace_id,
        provider_type=recording_metadata.provider_type,
        original_filenames=(session.summary.original_filename,),
        created_at=utc_now(),
        file_size_bytes=session.summary.original_byte_size,
        station_name=recording_metadata.station_name,
        recorder_name=recording_metadata.recorder_name,
        nominal_frequency=recording_metadata.nominal_frequency,
        timing_reference=timing_info.timing_reference,
        start_time=timing_info.start_time,
        trigger_time=timing_info.trigger_time,
        sample_count=record.sample_count(),
        duration_seconds=record.duration_seconds(),
        elapsed_start_seconds=record.elapsed_start_seconds(),
        elapsed_end_seconds=record.elapsed_end_seconds(),
        sampling_rates=tuple(sampling_info.sampling_rates),
        samples_per_rate=tuple(sampling_info.samples_per_rate),
        analog_channels=[
            AnalogChannelSummary(
                name=ch.name, index=ch.index, unit=ch.unit,
                engineering_type=classify_analog_channel(parameter_type=ch.parameter_type, unit=ch.unit),
                phase=ch.phase, scale=ch.scale, offset=ch.offset,
            )
            for ch in analog_channels
        ],
        digital_channels=[],
        preparation_provenance=provenance,
    )

    workspace_registry.add(ActiveSource(metadata=metadata, record=record))
    preparation_registry.remove(workspace_id, source_id)
    return metadata
