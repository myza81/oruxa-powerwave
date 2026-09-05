"""Time-Axis interpretation FRAMEWORK orchestration (CSV/Excel ingestion
Slices 7-8A, DEC-072). Authoritative design source:
docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md.

Mirrors `app.services.working_overlay_service`'s own layering exactly:

    resolve (workspace_id, source_id) -> PreparationSession (registry)
            |
    resolve which worksheet's coordinate space applies (None for CSV;
    the selected worksheet for Excel -- never guessed)
            |
    validate the request against THIS source's own known dimensions and
    against its CURRENT column_roles state
            |
    app.domain.time_axis's own pure dataclasses/functions +
    app.domain.working_overlay's own set_time_axis_configuration/
    clear_time_axis_configuration
            |
    TimeAxisInterpretationResult (derived live, never cached -- see
    app.services.preparation_issue_service's own module docstring for
    why this pattern is used again here)

Slice 7 registered exactly two non-parsing interpreters (`manual`,
`unsupported`). Slice 8A adds the first two REAL, deterministic ones --
`absolute_datetime` (task §A) and `split_date_time` (task §B), both
implemented in `app.services.time_axis_interpreters` -- without
changing this module's own architecture: they are still resolved
through the same `_INTERPRETERS` registry, still produce a
`TimeAxisConfiguration`, still flow through the same `WorkingOverlay`
storage/undo-redo, and `time_grouping.py`/`synchronization.py` still
know nothing about any of this (DEC-072 point 6).

**Two interpreter "kinds," one registry.** `manual`/`unsupported` are
NON-SAMPLE interpreters (`needs_sample_data = False`): they never read
a single cell value, and their whole `TimeAxisConfiguration` is built
directly from what the CALLER supplied (`build_configuration()`).
`absolute_datetime`/`split_date_time` are SAMPLE interpreters
(`needs_sample_data = True`): `family`/`provenance` are COMPUTED from a
bounded row sample (`detect()`), not trusted from the caller -- a
caller-supplied `family`/`provenance` for these two is accepted as
optional input but always OVERRIDDEN by what the data itself says (see
`set_time_axis_configuration()`'s own docstring for why this is not a
silent trust violation: the interpreter's own name already IS the
family it produces). `build_preview_rows()` is likewise a
sample-interpreter-only method: `manual`/`unsupported` never implement
it because `preview_supported` is `False` for both (unchanged from
Slice 7) and it is never called for them.

**Bounded sampling** (task §H/§U): `_fetch_time_axis_samples()` is the
ONE place a sample interpreter's row data ever comes from -- it reuses
`app.services.preparation_preview_service.preview_preparation_source()`
verbatim (never a second raw-reading implementation), bounded to
`_TIME_AXIS_SAMPLE_LIMIT` rows starting at the configured data region's
own start row (or row 1 if none is set), and drops excluded/out-of-
region/header rows before an interpreter ever sees them -- so a sample
interpreter always evaluates exactly the rows that would actually be
used, never a raw/unfiltered slice.

**Diagnostics are recomputed on every `GET`, not stored.** A sample
interpreter's `detect()` is called TWICE per write
(`set_time_axis_configuration()` calls it once to resolve what to
store; the `get_time_axis_summary()` call at the end of that same
function calls it again, exactly as every other read does) -- a
deliberate, bounded, cheap redundancy in exchange for a single "always
derive live" code path with no second cache-invalidation concern, the
same tradeoff `preparation_preview_service`'s own CSV row-counting
already documents accepting.

Column-role relationship (task section N, unchanged from Slice 7): a
`TimeAxisConfiguration` is never mutated or auto-cleared when a
column's role changes away from Time Axis -- see
`app.domain.time_axis.resolve_status`'s own docstring for why
auto-clearing was considered and rejected. Instead,
`_columns_still_time_axis()` is recomputed live, on every read, against
the session's CURRENT `column_roles`, and fed into
`build_interpretation_result()` so a stale configuration is always
reported as `STATUS_UNSUPPORTED`, never silently presented as valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain import time_axis as time_axis_domain
from app.domain import working_overlay as overlay_domain
from app.domain.preparation_session import PreparationSession
from app.domain.time_axis import (
    KNOWN_PROVENANCES,
    KNOWN_TIME_FAMILIES,
    TimeAxisConfiguration,
    TimeAxisDetectionResult,
    TimeAxisDiagnostic,
    TimeAxisInterpretationResult,
    TimeAxisPreviewRow,
    TimeAxisSampleRow,
)
from app.services import time_axis_interpreters
from app.services.errors import (
    InvalidTimeAxisConfigurationError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    UnknownTimeAxisInterpreterError,
    WorksheetNotSelectedError,
)
from app.services.preparation_preview_service import (
    PreviewRow,
    ensure_csv_totals_cached,
    iterate_active_region_rows,
    preview_preparation_source,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_normalization import (
    format_absolute_iso,
    format_relative_seconds,
    format_time_of_day,
    parse_native_time_value,
    relative_seconds_with_anchor,
    seconds_from_midnight,
)

#: Bounded row-sample cap for every SAMPLE interpreter's own `detect()`/
#: `build_preview_rows()` call -- task's own explicit "bounded sample
#: rows... an explicit reasonable cap" allowance (§H), chosen over
#: reusing whatever page the frontend currently has open so this
#: module's own behavior never depends on unrelated pagination state.
_TIME_AXIS_SAMPLE_LIMIT = 50

#: How many of the (already-bounded) sample rows are ever echoed back
#: as a formatted {original, interpreted} preview row (§J/§16) -- a
#: second, smaller bound purely to keep the dry-run preview response
#: itself small; detection/diagnostics still consider the FULL
#: `_TIME_AXIS_SAMPLE_LIMIT` rows regardless of this cap.
_TIME_AXIS_PREVIEW_LIMIT = 20


class TimeAxisInterpreter(Protocol):
    """The interpreter contract every registry entry satisfies --
    extended in Slice 8A with a second "kind" (see this module's own
    docstring). `accepts()` is always a cheap, purely structural
    pre-check (column COUNT only, never a cell value)."""

    interpreter_id: str
    needs_sample_data: bool

    def accepts(self, *, column_count: int) -> bool: ...

    def build_configuration(
        self,
        *,
        column_indices: tuple[int, ...],
        family: str | None,
        provenance: str | None,
        unit: str | None,
        interval_seconds: float | None,
        confirmed: bool,
        options: dict[str, Any],
    ) -> TimeAxisConfiguration:
        """Non-sample interpreters only (`needs_sample_data = False`) --
        builds the whole `TimeAxisConfiguration` directly from caller-
        supplied fields. Never called for a sample interpreter."""
        ...

    def detect(
        self,
        *,
        samples: list[TimeAxisSampleRow],
        requested_family: str | None,
        requested_provenance: str | None,
        requested_unit: str | None,
        requested_interval_seconds: float | None,
        requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        """Sample interpreters only (`needs_sample_data = True`) --
        classifies `family`/`provenance`/`confidence`/diagnostics from
        an already-fetched bounded sample. `requested_unit`/
        `requested_interval_seconds` (Slice 8B) are the ONE place
        `elapsed_numeric`/`sample_index` receive their own required/
        optional configuration -- `absolute_datetime`/`split_date_time`
        simply ignore both. Never called for a non-sample interpreter."""
        ...

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        """Sample interpreters only -- bounded {original, interpreted}
        rows for the dry-run preview action. Never called for a
        non-sample interpreter (`preview_supported` is always `False`
        for those, so nothing ever asks)."""
        ...


@dataclass(slots=True, frozen=True)
class _ManualInterpreter:
    """Accepts any non-empty column set unconditionally. Stores exactly
    the family/provenance/unit/interval/options the caller supplied --
    this interpreter does not itself decide or validate what a sensible
    family is; `set_time_axis_configuration()` below already checked
    `family`/`provenance` against the known closed sets before an
    interpreter is ever reached."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_MANUAL
    needs_sample_data: bool = False

    def accepts(self, *, column_count: int) -> bool:
        return column_count >= 1

    def build_configuration(
        self,
        *,
        column_indices: tuple[int, ...],
        family: str | None,
        provenance: str | None,
        unit: str | None,
        interval_seconds: float | None,
        confirmed: bool,
        options: dict[str, Any],
    ) -> TimeAxisConfiguration:
        return TimeAxisConfiguration(
            column_indices=column_indices,
            family=family,
            provenance=provenance,
            interpreter_id=self.interpreter_id,
            unit=unit,
            interval_seconds=interval_seconds,
            confirmed=confirmed,
            options=dict(options),
        )


@dataclass(slots=True, frozen=True)
class _UnsupportedInterpreter:
    """The universal fallback sentinel -- `accepts()` is always `True` so
    `resolve_interpreter()` always has somewhere to land, never raising
    for "no interpreter recognizes this input" (task section H: "clean
    unconfigured/unsupported representation, never crashing"). Always
    produces `family=None, provenance=None` regardless of what the caller
    requested -- see `TimeAxisConfiguration`'s own docstring for why
    those two fields are `None` only for this one interpreter's output."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_UNSUPPORTED
    needs_sample_data: bool = False

    def accepts(self, *, column_count: int) -> bool:
        return True

    def build_configuration(
        self,
        *,
        column_indices: tuple[int, ...],
        family: str | None,
        provenance: str | None,
        unit: str | None,
        interval_seconds: float | None,
        confirmed: bool,
        options: dict[str, Any],
    ) -> TimeAxisConfiguration:
        return TimeAxisConfiguration(
            column_indices=column_indices,
            family=None,
            provenance=None,
            interpreter_id=self.interpreter_id,
            unit=None,
            interval_seconds=None,
            confirmed=False,
        )


@dataclass(slots=True, frozen=True)
class _AbsoluteDatetimeInterpreter:
    """Single-column absolute datetime (task §A) -- accepts exactly one
    column. Adapts `TimeAxisSampleRow.values[0]` into the plain
    `(row_number, value)` pairs `app.services.time_axis_interpreters`'s
    own pure functions expect; all real parsing/ambiguity logic lives
    there, never duplicated here."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_ABSOLUTE_DATETIME
    needs_sample_data: bool = True

    def accepts(self, *, column_count: int) -> bool:
        return column_count == 1

    def detect(
        self, *, samples: list[TimeAxisSampleRow], requested_family: str | None,
        requested_provenance: str | None, requested_unit: str | None,
        requested_interval_seconds: float | None, requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        raw = [(s.row_number, s.values[0] if s.values else None) for s in samples]
        return time_axis_interpreters.detect_absolute_datetime(raw, requested_options=requested_options)

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        raw = [(s.row_number, s.values) for s in samples]
        built = time_axis_interpreters.build_absolute_datetime_preview(raw, resolved_options=resolved_options, limit=limit)
        return [TimeAxisPreviewRow(row_number=rn, original=original, interpreted=interpreted) for rn, original, interpreted in built]


@dataclass(slots=True, frozen=True)
class _SplitDateTimeInterpreter:
    """Split Date + Time (task §B) -- accepts exactly two columns.
    `column_indices` is documented (see `TimeAxisSampleRow`'s own
    docstring) as `(date_column_index, time_column_index)` IN THAT
    ORDER for this interpreter specifically -- the order the caller
    submits `column_indices` in IS the date/time assignment; there is
    no separate "which one is the date column" field, per this
    codebase's own "smallest coherent representation" preference."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_SPLIT_DATE_TIME
    needs_sample_data: bool = True

    def accepts(self, *, column_count: int) -> bool:
        return column_count == 2

    def detect(
        self, *, samples: list[TimeAxisSampleRow], requested_family: str | None,
        requested_provenance: str | None, requested_unit: str | None,
        requested_interval_seconds: float | None, requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        date_values = [(s.row_number, s.values[0] if len(s.values) > 0 else None) for s in samples]
        time_values = [(s.row_number, s.values[1] if len(s.values) > 1 else None) for s in samples]
        return time_axis_interpreters.detect_split_date_time(date_values, time_values, requested_options=requested_options)

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        raw = [(s.row_number, s.values) for s in samples]
        built = time_axis_interpreters.build_split_date_time_preview(raw, resolved_options=resolved_options, limit=limit)
        return [TimeAxisPreviewRow(row_number=rn, original=original, interpreted=interpreted) for rn, original, interpreted in built]


@dataclass(slots=True, frozen=True)
class _TimeOfDayInterpreter:
    """Time of Day (task: clock time with no date component) -- accepts
    exactly one column. A DISTINCT, explicitly-selected interpreter,
    never an automatic fallback (see `app.services.time_axis_
    interpreters.detect_time_of_day`'s own docstring) --
    `detect_absolute_datetime()`'s own pre-existing "every sampled value
    is a time-of-day" -> `FAMILY_PARTIAL` diagnostic is completely
    unaffected by this interpreter's existence."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_TIME_OF_DAY
    needs_sample_data: bool = True

    def accepts(self, *, column_count: int) -> bool:
        return column_count == 1

    def detect(
        self, *, samples: list[TimeAxisSampleRow], requested_family: str | None,
        requested_provenance: str | None, requested_unit: str | None,
        requested_interval_seconds: float | None, requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        raw = [(s.row_number, s.values[0] if s.values else None) for s in samples]
        return time_axis_interpreters.detect_time_of_day(raw, requested_options=requested_options)

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        raw = [(s.row_number, s.values) for s in samples]
        built = time_axis_interpreters.build_time_of_day_preview(raw, resolved_options=resolved_options, limit=limit)
        return [TimeAxisPreviewRow(row_number=rn, original=original, interpreted=interpreted) for rn, original, interpreted in built]


@dataclass(slots=True, frozen=True)
class _ElapsedNumericInterpreter:
    """Single-column elapsed/relative numeric time (task §A) -- accepts
    exactly one column. `unit` (already an existing top-level
    `TimeAxisConfiguration` field since Slice 7, anticipating exactly
    this) is the ONE piece of caller-supplied configuration this
    interpreter actually needs -- see `app.services.
    time_axis_interpreters.detect_elapsed_numeric`'s own docstring for
    why a missing unit produces `review_required` rather than a guess."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_ELAPSED_NUMERIC
    needs_sample_data: bool = True

    def accepts(self, *, column_count: int) -> bool:
        return column_count == 1

    def detect(
        self, *, samples: list[TimeAxisSampleRow], requested_family: str | None,
        requested_provenance: str | None, requested_unit: str | None,
        requested_interval_seconds: float | None, requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        raw = [(s.row_number, s.values[0] if s.values else None) for s in samples]
        return time_axis_interpreters.detect_elapsed_numeric(raw, requested_unit=requested_unit)

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        raw = [(s.row_number, s.values) for s in samples]
        built = time_axis_interpreters.build_elapsed_preview(raw, resolved_unit=resolved_unit, limit=limit)
        return [TimeAxisPreviewRow(row_number=rn, original=original, interpreted=interpreted) for rn, original, interpreted in built]


@dataclass(slots=True, frozen=True)
class _SampleIndexInterpreter:
    """Single-column sample index (task §E-§L) -- accepts exactly one
    column. `interval_seconds` (already an existing top-level
    `TimeAxisConfiguration` field since Slice 7) is OPTIONAL -- absent
    means index-only (the approved fallback, task §F), present means a
    user-supplied sampling interval/rate already converted to canonical
    seconds by the caller (see `app.services.time_axis_service`'s own
    module docstring for why a rate-vs-interval UI choice is never a
    second stored representation)."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_SAMPLE_INDEX
    needs_sample_data: bool = True

    def accepts(self, *, column_count: int) -> bool:
        return column_count == 1

    def detect(
        self, *, samples: list[TimeAxisSampleRow], requested_family: str | None,
        requested_provenance: str | None, requested_unit: str | None,
        requested_interval_seconds: float | None, requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        raw = [(s.row_number, s.values[0] if s.values else None) for s in samples]
        return time_axis_interpreters.detect_sample_index(raw, requested_interval_seconds=requested_interval_seconds)

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        raw = [(s.row_number, s.values) for s in samples]
        built = time_axis_interpreters.build_sample_index_preview(
            raw, resolved_interval_seconds=resolved_interval_seconds, limit=limit,
        )
        return [TimeAxisPreviewRow(row_number=rn, original=original, interpreted=interpreted) for rn, original, interpreted in built]


@dataclass(slots=True, frozen=True)
class _RepeatedTimestampInterpreter:
    """Repeated-timestamp / precision-loss reconstruction (task §A-§L)
    -- accepts exactly one column. `interval_seconds`, if the CALLER
    supplies it, is a user override (§J) -- bypasses this interpreter's
    own cadence inference entirely, `provenance=user_specified`,
    matching `sample_index`'s own precedent. Otherwise the interpreter
    analyses bounded consecutive-run buckets itself; see
    `app.services.time_axis_interpreters.detect_repeated_timestamp_
    precision_loss`'s own docstring for the full confidence/anchor/
    provenance rules. `options.anchor_offset_seconds` (default `0.0`)
    is the ONE interpreter-specific setting stored -- no other new
    field was needed (`unit`/`interval_seconds` were both already
    top-level `TimeAxisConfiguration` fields since Slice 7)."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_REPEATED_TIMESTAMP
    needs_sample_data: bool = True

    def accepts(self, *, column_count: int) -> bool:
        return column_count == 1

    def detect(
        self, *, samples: list[TimeAxisSampleRow], requested_family: str | None,
        requested_provenance: str | None, requested_unit: str | None,
        requested_interval_seconds: float | None, requested_options: dict[str, Any],
    ) -> TimeAxisDetectionResult:
        raw = [(s.row_number, s.values[0] if s.values else None) for s in samples]
        return time_axis_interpreters.detect_repeated_timestamp_precision_loss(
            raw, requested_interval_seconds=requested_interval_seconds, requested_options=requested_options,
        )

    def build_preview_rows(
        self, *, samples: list[TimeAxisSampleRow], resolved_options: dict[str, Any],
        resolved_unit: str | None, resolved_interval_seconds: float | None, limit: int,
    ) -> list[TimeAxisPreviewRow]:
        raw = [(s.row_number, s.values) for s in samples]
        built = time_axis_interpreters.build_repeated_timestamp_preview(
            raw, resolved_options=resolved_options, resolved_interval_seconds=resolved_interval_seconds, limit=limit,
        )
        return [TimeAxisPreviewRow(row_number=rn, original=original, interpreted=interpreted) for rn, original, interpreted in built]


# Small, explicit, hand-written registry -- no dynamic loading, no entry
# points, no external config (task section G: "Do NOT build dynamic
# plugin discovery... An explicit registry/list is sufficient").
# `manual` stays FIRST among the non-`unsupported` entries so that every
# Slice 7 caller who omits `interpreter_id` entirely keeps resolving to
# `manual` exactly as before (`resolve_interpreter()`'s own auto-select
# walks this dict in insertion order) -- the two Slice 8A interpreters
# are only ever chosen when EXPLICITLY requested by id, never guessed.
_INTERPRETERS: dict[str, TimeAxisInterpreter] = {
    time_axis_domain.INTERPRETER_ID_MANUAL: _ManualInterpreter(),
    time_axis_domain.INTERPRETER_ID_UNSUPPORTED: _UnsupportedInterpreter(),
    time_axis_domain.INTERPRETER_ID_ABSOLUTE_DATETIME: _AbsoluteDatetimeInterpreter(),
    time_axis_domain.INTERPRETER_ID_SPLIT_DATE_TIME: _SplitDateTimeInterpreter(),
    time_axis_domain.INTERPRETER_ID_TIME_OF_DAY: _TimeOfDayInterpreter(),
    time_axis_domain.INTERPRETER_ID_ELAPSED_NUMERIC: _ElapsedNumericInterpreter(),
    time_axis_domain.INTERPRETER_ID_SAMPLE_INDEX: _SampleIndexInterpreter(),
    time_axis_domain.INTERPRETER_ID_REPEATED_TIMESTAMP: _RepeatedTimestampInterpreter(),
}


def list_time_axis_interpreters() -> list[str]:
    """Every registered interpreter id, for the API's own metadata
    endpoint and for schema validation of a caller-supplied
    `interpreter_id` override."""
    return list(_INTERPRETERS.keys())


def resolve_interpreter(*, column_count: int, requested_interpreter_id: str | None) -> TimeAxisInterpreter:
    """`requested_interpreter_id` must name a registered interpreter if
    given at all -- raises `UnknownTimeAxisInterpreterError` otherwise
    (task section M: "interpreter id exists").

    With NO explicit request, this ALWAYS prefers `manual` over any
    other accepting interpreter -- a deliberate, EXPLICIT preference
    (task's own Slice 7 "avoid a misleading Auto Detect" guardrail,
    now with real teeth: Slice 8A's `absolute_datetime`/
    `split_date_time` also `accepts()` a 1/2-column request, so a
    caller who does not explicitly ask for either must never be
    silently routed into real parsing). This is checked directly by
    id, NOT by "whichever registry entry happens to iterate first" --
    relying on dict insertion order here would be fragile (verified
    directly: a naive iteration-order version of this function broke
    under nothing more than a test's own `monkeypatch.delitem`/re-add
    of the `manual` entry, which Python dicts re-insert at the END,
    silently reordering every subsequent auto-resolution in the same
    process). Only when `manual` itself is unavailable or does not
    accept this column count does this fall through to scanning every
    OTHER real (non-`unsupported`) entry, finally falling back to
    `unsupported` if none do -- directly unit-testable via a synthetic
    fake interpreter whose `accepts()` returns `False`.
    """
    if requested_interpreter_id is not None:
        interpreter = _INTERPRETERS.get(requested_interpreter_id)
        if interpreter is None:
            raise UnknownTimeAxisInterpreterError(
                f"interpreter_id must be one of {list_time_axis_interpreters()}; got {requested_interpreter_id!r}."
            )
        return interpreter
    manual = _INTERPRETERS.get(time_axis_domain.INTERPRETER_ID_MANUAL)
    if manual is not None and manual.accepts(column_count=column_count):
        return manual
    for interpreter in _INTERPRETERS.values():
        if interpreter.interpreter_id in (time_axis_domain.INTERPRETER_ID_UNSUPPORTED, time_axis_domain.INTERPRETER_ID_MANUAL):
            continue
        if interpreter.accepts(column_count=column_count):
            return interpreter
    return _INTERPRETERS[time_axis_domain.INTERPRETER_ID_UNSUPPORTED]


def _resolve_session(*, workspace_id: str, source_id: str, registry: PreparationSessionRegistry) -> PreparationSession:
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(f"No preparation source '{source_id}' in workspace '{workspace_id}'.")
    return session


def _resolve_worksheet_index(session: PreparationSession) -> int | None:
    """`None` for CSV. For Excel, the currently selected worksheet --
    never guessed, mirroring every other Slice 4-6 service module's own
    identical rule."""
    worksheets = session.summary.worksheets
    if not worksheets:
        return None
    if session.summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before configuring its time axis."
        )
    return session.summary.selected_worksheet_index


def _column_total(session: PreparationSession, worksheet_index: int | None) -> int | None:
    if worksheet_index is None:
        ensure_csv_totals_cached(session)
        return session.cached_column_count
    return session.summary.worksheets[worksheet_index].column_count


def _check_column_bound(session: PreparationSession, worksheet_index: int | None, column_index: int) -> None:
    total = _column_total(session, worksheet_index)
    if total is not None and column_index >= total:
        raise InvalidWorkingCoordinateError(
            f"column_index {column_index} is beyond this source's own {total} known columns."
        )


def _columns_still_time_axis(
    session: PreparationSession, worksheet_index: int | None, column_indices: tuple[int, ...],
) -> bool:
    """Live check against CURRENT `column_roles` state -- never against
    whatever role each column carried at configuration time. Returns
    `True` for an empty `column_indices` tuple only in the degenerate
    case that should never occur in practice (schema validation always
    rejects an empty tuple before a configuration is ever stored)."""
    column_roles = session.working_overlay.column_roles
    return all(
        column_roles.get(overlay_domain.column_key(worksheet_index, c)) == overlay_domain.ROLE_TIME_AXIS
        for c in column_indices
    )


def _sample_offset(session: PreparationSession, worksheet_index: int | None) -> int:
    """0-based fetch offset for `_fetch_time_axis_samples()` -- starts
    at the configured data region's own start row when one is set (no
    point sampling header/pre-region rows an interpreter would never
    actually use), else row 1 (offset 0)."""
    region = session.working_overlay.data_region.get(worksheet_index)
    if region is None:
        return 0
    return max(0, region.start_row - 1)


def _fetch_time_axis_samples(
    *, workspace_id: str, source_id: str, worksheet_index: int | None,
    column_indices: tuple[int, ...], session: PreparationSession, registry: PreparationSessionRegistry,
) -> list[TimeAxisSampleRow]:
    """The ONE place a sample interpreter's row data comes from --
    reuses `preview_preparation_source()` verbatim (see this module's
    own docstring) so a sample interpreter always evaluates exactly the
    same working-view rows the rest of the workspace already shows,
    bounded to `_TIME_AXIS_SAMPLE_LIMIT`. Excluded, out-of-region, and
    the header row are all dropped before an interpreter ever sees
    them -- they are not rows this configuration would actually use."""
    offset = _sample_offset(session, worksheet_index)
    preview = preview_preparation_source(
        workspace_id=workspace_id, source_id=source_id, offset=offset, limit=_TIME_AXIS_SAMPLE_LIMIT, registry=registry,
    )
    samples: list[TimeAxisSampleRow] = []
    for row in preview.rows:
        if row.excluded or not row.in_active_region or row.is_header:
            continue
        values = tuple(row.cells[c] if c < len(row.cells) else None for c in column_indices)
        samples.append(TimeAxisSampleRow(row_number=row.row_number, values=values))
    return samples


def _has_ambiguous_diagnostic(diagnostics: list[TimeAxisDiagnostic]) -> bool:
    return any(d.ambiguity == time_axis_domain.AMBIGUITY_AMBIGUOUS for d in diagnostics)


def get_time_axis_summary(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> TimeAxisInterpretationResult:
    """Derived live on every call, directly from the session's own
    current `WorkingOverlay.time_axis` + `column_roles` state -- nothing
    is ever cached (see this module's own docstring). For a STORED
    configuration whose resolved interpreter is a SAMPLE interpreter
    (Slice 8A), diagnostics/confidence are recomputed fresh here too
    (a bounded re-`detect()` against the current data) -- `manual`/
    `unsupported` configurations skip this entirely, exactly
    reproducing Slice 7's own zero-I/O behavior for them."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    configuration = session.working_overlay.time_axis.get(worksheet_index)
    columns_still_time_axis = (
        _columns_still_time_axis(session, worksheet_index, configuration.column_indices)
        if configuration is not None
        else True
    )

    diagnostics: list[TimeAxisDiagnostic] = []
    confidence = time_axis_domain.CONFIDENCE_UNKNOWN
    preview_supported = False

    if configuration is not None and columns_still_time_axis:
        interpreter = _INTERPRETERS.get(configuration.interpreter_id)
        if interpreter is not None:
            preview_supported = interpreter.needs_sample_data
            if interpreter.needs_sample_data:
                samples = _fetch_time_axis_samples(
                    workspace_id=workspace_id, source_id=source_id, worksheet_index=worksheet_index,
                    column_indices=configuration.column_indices, session=session, registry=registry,
                )
                detection = interpreter.detect(
                    samples=samples, requested_family=configuration.family,
                    requested_provenance=configuration.provenance, requested_unit=configuration.unit,
                    requested_interval_seconds=configuration.interval_seconds, requested_options=configuration.options,
                )
                diagnostics = detection.diagnostics
                confidence = detection.confidence

    return time_axis_domain.build_interpretation_result(
        configuration, columns_still_time_axis=columns_still_time_axis, diagnostics=diagnostics,
        confidence=confidence, preview_supported=preview_supported,
    )


def set_time_axis_configuration(
    *,
    workspace_id: str,
    source_id: str,
    column_indices: tuple[int, ...],
    family: str | None = None,
    provenance: str | None = None,
    unit: str | None = None,
    interval_seconds: float | None = None,
    confirmed: bool = False,
    interpreter_id: str | None = None,
    options: dict[str, Any] | None = None,
    registry: PreparationSessionRegistry,
) -> TimeAxisInterpretationResult:
    """Validate and store one worksheet/source's `TimeAxisConfiguration`
    (task section M's own schema-validation list):

    - `column_indices` is non-empty, has no duplicate, and every index is
      within this source's own known column bounds.
    - every referenced column currently carries `ROLE_TIME_AXIS` (task
      section N -- a configuration may only reference columns presently
      marked Time Axis; this is checked at WRITE time here, in addition
      to the live re-check `get_time_axis_summary()` performs on every
      READ, so a caller gets an immediate, specific rejection rather than
      a silently-accepted configuration that would show as unsupported
      the moment it is read back).
    - `interval_seconds`, if given, is finite and positive.
    - `interpreter_id`, if given, names a registered interpreter whose
      own `accepts()` allows this many columns.

    **Slice 8A: `family`/`provenance` are optional here.** For a
    NON-SAMPLE interpreter (`manual`/`unsupported`) they are validated
    against the known closed sets exactly as in Slice 7 (`manual`
    requires both; `unsupported` ignores them). For a SAMPLE interpreter
    (`absolute_datetime`/`split_date_time`), whatever the caller passes
    is only a HINT -- the interpreter's own `detect()` computes the
    real `family`/`provenance` from the actual sampled data and that
    result always wins, since the interpreter's own identity already
    IS the family it produces (an `absolute_datetime` reading is never
    going to legitimately come back `elapsed`). Requesting `confirmed`
    while the sample data is still genuinely ambiguous (an
    `ambiguous_date_order`-class diagnostic, OR Slice 8B's own
    `missing_elapsed_unit`) is rejected outright -- the same "no silent
    auto-confirm" rule the design doc's own §5 states, enforced at the
    API boundary, not only in UI copy.

    **Slice 8B**: `unit`/`interval_seconds` are the SAME pre-existing
    top-level parameters Slice 7 always had (never a new `options` key)
    -- `elapsed_numeric` reads `unit` (required eventually, but a
    caller MAY save without one first, landing in `review_required`
    exactly like an unresolved date order); `sample_index` reads
    `interval_seconds` (entirely optional -- absent means index-only,
    the approved fallback, never an error). `elapsed_numeric`'s own
    `unit`, if given at all, must be one of `KNOWN_ELAPSED_UNITS` --
    checked here, scoped to that one interpreter, so `manual`'s own
    deliberately open-ended `unit` field is untouched.
    """
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)

    if not column_indices:
        raise InvalidTimeAxisConfigurationError("column_indices must not be empty.")
    if len(set(column_indices)) != len(column_indices):
        raise InvalidTimeAxisConfigurationError("column_indices must not contain a duplicate.")
    for column_index in column_indices:
        _check_column_bound(session, worksheet_index, column_index)
    if not _columns_still_time_axis(session, worksheet_index, column_indices):
        raise InvalidTimeAxisConfigurationError(
            "Every column in column_indices must currently carry the Time Axis column role."
        )
    if interval_seconds is not None and not (interval_seconds > 0):
        raise InvalidTimeAxisConfigurationError("interval_seconds must be a positive number when given.")

    interpreter = resolve_interpreter(column_count=len(column_indices), requested_interpreter_id=interpreter_id)
    if not interpreter.accepts(column_count=len(column_indices)):
        raise InvalidTimeAxisConfigurationError(
            f"'{interpreter.interpreter_id}' does not accept {len(column_indices)} column(s)."
        )
    # Slice 8B: `elapsed_numeric` is a deliberately CLOSED-vocabulary
    # interpreter (unlike `manual`'s own open-ended `unit` field, per
    # DEC-072 point 6) -- validated here, scoped to this one
    # interpreter, so `manual`'s existing freedom is untouched.
    if (
        interpreter.interpreter_id == time_axis_domain.INTERPRETER_ID_ELAPSED_NUMERIC
        and unit is not None
        and unit not in time_axis_domain.KNOWN_ELAPSED_UNITS
    ):
        raise InvalidTimeAxisConfigurationError(
            f"unit must be one of {time_axis_domain.KNOWN_ELAPSED_UNITS} for '{interpreter.interpreter_id}'; got {unit!r}."
        )
    options = dict(options or {})

    if interpreter.needs_sample_data:
        samples = _fetch_time_axis_samples(
            workspace_id=workspace_id, source_id=source_id, worksheet_index=worksheet_index,
            column_indices=tuple(column_indices), session=session, registry=registry,
        )
        detection = interpreter.detect(
            samples=samples, requested_family=family, requested_provenance=provenance,
            requested_unit=unit, requested_interval_seconds=interval_seconds, requested_options=options,
        )
        if confirmed and _has_ambiguous_diagnostic(detection.diagnostics):
            raise InvalidTimeAxisConfigurationError(
                "Cannot confirm this Time Axis configuration while it is still ambiguous -- "
                "resolve the ambiguity first (e.g. choose an explicit date order or unit)."
            )
        configuration = TimeAxisConfiguration(
            column_indices=tuple(column_indices),
            family=detection.family,
            provenance=detection.provenance,
            interpreter_id=interpreter.interpreter_id,
            unit=detection.resolved_unit,
            interval_seconds=detection.resolved_interval_seconds,
            confirmed=confirmed,
            options=detection.resolved_options,
        )
    else:
        if family not in KNOWN_TIME_FAMILIES:
            raise InvalidTimeAxisConfigurationError(f"family must be one of {KNOWN_TIME_FAMILIES}; got {family!r}.")
        if provenance not in KNOWN_PROVENANCES:
            raise InvalidTimeAxisConfigurationError(
                f"provenance must be one of {KNOWN_PROVENANCES}; got {provenance!r}."
            )
        configuration = interpreter.build_configuration(
            column_indices=tuple(column_indices),
            family=family,
            provenance=provenance,
            unit=unit,
            interval_seconds=interval_seconds,
            confirmed=confirmed,
            options=options,
        )

    overlay_domain.set_time_axis_configuration(session.working_overlay, worksheet_index, configuration)
    return get_time_axis_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)


def clear_time_axis_configuration(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> TimeAxisInterpretationResult:
    """Remove this worksheet/source's stored configuration entirely (a
    safe no-op if it had none) -- the state reverts to `unconfigured`."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    overlay_domain.clear_time_axis_configuration(session.working_overlay, worksheet_index)
    return get_time_axis_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)


@dataclass(slots=True)
class TimeAxisInterpretPreview:
    """The dry-run response of `interpret_time_axis()` below (task §T)
    -- everything `set_time_axis_configuration()` would compute for a
    SAMPLE interpreter, PLUS a bounded {original, interpreted} preview
    (§J/§16), without storing anything and without requiring
    `confirmed`. Mirrors `WorkingOverlaySummary`'s own precedent of
    living in the SERVICE layer, not the domain module -- this is an
    API-facing, transient read-model, never round-tripped through
    `WorkingOverlay`."""

    interpreter_id: str
    column_indices: tuple[int, ...]
    family: str | None
    provenance: str | None
    confidence: str
    diagnostics: list[TimeAxisDiagnostic] = field(default_factory=list)
    resolved_options: dict[str, Any] = field(default_factory=dict)
    resolved_unit: str | None = None
    resolved_interval_seconds: float | None = None
    preview_rows: list[TimeAxisPreviewRow] = field(default_factory=list)


def interpret_time_axis(
    *,
    workspace_id: str,
    source_id: str,
    column_indices: tuple[int, ...],
    interpreter_id: str,
    unit: str | None = None,
    interval_seconds: float | None = None,
    options: dict[str, Any] | None = None,
    registry: PreparationSessionRegistry,
) -> TimeAxisInterpretPreview:
    """Dry-run detect/preview action (task §T) -- computes exactly what
    `set_time_axis_configuration()` would resolve to for a SAMPLE
    interpreter, WITHOUT storing anything and without any `confirmed`
    concept (there is nothing to confirm yet; this is purely "what
    would happen if"). Column-role membership is still validated (the
    same "may only interpret columns actually marked Time Axis" rule
    as the real write path) so a preview always reflects the exact
    input a subsequent save would use. Rejects a non-sample
    `interpreter_id` (`manual`/`unsupported`) outright -- there is
    nothing to detect or preview for either. `unit`/`interval_seconds`
    (Slice 8B) let a caller try a specific elapsed unit or sample-index
    interval before committing to it via the real PUT."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)

    if not column_indices:
        raise InvalidTimeAxisConfigurationError("column_indices must not be empty.")
    if len(set(column_indices)) != len(column_indices):
        raise InvalidTimeAxisConfigurationError("column_indices must not contain a duplicate.")
    for column_index in column_indices:
        _check_column_bound(session, worksheet_index, column_index)
    if not _columns_still_time_axis(session, worksheet_index, column_indices):
        raise InvalidTimeAxisConfigurationError(
            "Every column in column_indices must currently carry the Time Axis column role."
        )
    if interval_seconds is not None and not (interval_seconds > 0):
        raise InvalidTimeAxisConfigurationError("interval_seconds must be a positive number when given.")

    interpreter = resolve_interpreter(column_count=len(column_indices), requested_interpreter_id=interpreter_id)
    if not interpreter.accepts(column_count=len(column_indices)):
        raise InvalidTimeAxisConfigurationError(
            f"'{interpreter.interpreter_id}' does not accept {len(column_indices)} column(s)."
        )
    if not interpreter.needs_sample_data:
        raise InvalidTimeAxisConfigurationError(
            f"'{interpreter.interpreter_id}' does not support detection/preview."
        )
    if (
        interpreter.interpreter_id == time_axis_domain.INTERPRETER_ID_ELAPSED_NUMERIC
        and unit is not None
        and unit not in time_axis_domain.KNOWN_ELAPSED_UNITS
    ):
        raise InvalidTimeAxisConfigurationError(
            f"unit must be one of {time_axis_domain.KNOWN_ELAPSED_UNITS} for '{interpreter.interpreter_id}'; got {unit!r}."
        )

    samples = _fetch_time_axis_samples(
        workspace_id=workspace_id, source_id=source_id, worksheet_index=worksheet_index,
        column_indices=tuple(column_indices), session=session, registry=registry,
    )
    detection = interpreter.detect(
        samples=samples, requested_family=None, requested_provenance=None,
        requested_unit=unit, requested_interval_seconds=interval_seconds, requested_options=dict(options or {}),
    )
    preview_rows = interpreter.build_preview_rows(
        samples=samples, resolved_options=detection.resolved_options,
        resolved_unit=detection.resolved_unit, resolved_interval_seconds=detection.resolved_interval_seconds,
        limit=_TIME_AXIS_PREVIEW_LIMIT,
    )
    return TimeAxisInterpretPreview(
        interpreter_id=interpreter.interpreter_id,
        column_indices=tuple(column_indices),
        family=detection.family,
        provenance=detection.provenance,
        confidence=detection.confidence,
        diagnostics=detection.diagnostics,
        resolved_options=detection.resolved_options,
        resolved_unit=detection.resolved_unit,
        resolved_interval_seconds=detection.resolved_interval_seconds,
        preview_rows=preview_rows,
    )


@dataclass(slots=True)
class ConfiguredTimeValues:
    """The RESOLVED/CONFIGURED Time Axis, standardized exactly like
    cleaned export's own Time column, for every row of the CURRENT
    active data region -- the Data Preview's own "show what Powerwave
    will actually use" enhancement (2026-09-04, DEC-075).
    `values_by_row_number` is keyed by the source's own 1-based
    `row_number` (never a page-relative index), so a caller can look up
    exactly the rows it needs regardless of which preview page they
    belong to -- see `configured_time_for_preview_page()` below, the
    ONE place this full-region dict is narrowed down to one page's own
    rows. A row absent from this dict (excluded, the header row, or
    outside the active region) or present with value `None` (its own
    Time Axis cell failed to interpret) both mean "no configured time
    for this row" -- the caller renders a blank cell either way, never
    a fabricated value."""

    column_name: str
    family: str
    values_by_row_number: dict[int, str | None]


def build_configured_time_values(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> ConfiguredTimeValues | None:
    """Computes the standardized Configured Time value for EVERY row of
    the current active data region, in ONE single streaming pass over
    `app.services.preparation_preview_service.iterate_active_region_rows()`
    -- the SAME row source, and the SAME single-pass shape,
    `app.services.readiness_service`'s own full-region scan already uses
    on every preview/issues interaction, so this is not a NEW class of
    per-request cost, merely one more pass of the same kind.

    Returns `None` when the current Time Axis is not resolved enough to
    derive a value from at all
    (`app.domain.time_axis.is_time_axis_resolved()` -- the SAME shared
    check `app.services.preparation_export_service._ensure_exportable()`
    uses, so Data Preview and cleaned export can never silently
    disagree about when a Configured Time exists).

    **Critical guardrail (task section M)**: for every non-absolute
    family, each row's own value is normalized relative to the TRUE
    FIRST ACTIVE ROW of the whole active region -- never merely the
    first row of whatever page a caller later asks for. This function
    always processes the FULL active region for exactly this reason:
    `sample_index`/`repeated_timestamp_precision_loss`'s own
    `build_preview_rows()` computes ITS OWN relative-to-first-of-the-
    given-window value (see `app.services.time_axis_interpreters`'s own
    docstrings), so the given window must always BE the full active
    region for that "first" to mean the dataset's true first active
    row -- exactly the same reason `app.services.preparation_
    conversion_service`/`preparation_export_service` also always pass
    the FULL active region to `build_preview_rows()` in one call,
    never a bounded sample, for their own canonical/exported time.

    No new inference happens here: every value comes from re-calling
    the ALREADY-CONFIRMED interpreter's own `build_preview_rows()` (the
    exact same call canonical conversion and cleaned export already
    make), through the SAME shared `app.services.time_axis_
    normalization` parse/format helpers those two features use --
    canonical conversion, cleaned export, and this preview can never
    disagree about what a configured Time Axis means (task's own
    explicit "must agree" requirement)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    summary = get_time_axis_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)
    if not time_axis_domain.is_time_axis_resolved(summary):
        return None

    interpreter = resolve_interpreter(
        column_count=len(summary.column_indices), requested_interpreter_id=summary.interpreter_id,
    )
    family = summary.family
    # Time of Day (additive): the primary user-facing derived column
    # presents CLOCK TIME for a Time of Day reading, never plain elapsed
    # seconds -- the same distinction `table_service._time_column_label()`
    # already makes, kept independently here since this module has no
    # dependency on that one.
    column_name = (
        "Time" if family == time_axis_domain.FAMILY_ABSOLUTE
        else "Time of Day" if family == time_axis_domain.FAMILY_PARTIAL
        else "Time (s)"
    )

    time_axis_samples: list[TimeAxisSampleRow] = []
    for row in iterate_active_region_rows(session, worksheet_index=worksheet_index):
        if row.excluded or row.is_header or not row.in_active_region:
            continue
        values = tuple(row.cells[c] if c < len(row.cells) else None for c in summary.column_indices)
        time_axis_samples.append(TimeAxisSampleRow(row_number=row.row_number, values=values))

    if not time_axis_samples:
        return ConfiguredTimeValues(column_name=column_name, family=family, values_by_row_number={})

    preview_rows = interpreter.build_preview_rows(
        samples=time_axis_samples, resolved_options=summary.options, resolved_unit=summary.unit,
        resolved_interval_seconds=summary.interval_seconds, limit=len(time_axis_samples),
    )

    natives_by_row: dict[int, Any] = {
        pr.row_number: (parse_native_time_value(pr.interpreted, family=family) if pr.interpreted is not None else None)
        for pr in preview_rows
    }

    values_by_row_number: dict[int, str | None] = {}
    if family == time_axis_domain.FAMILY_ABSOLUTE:
        for row_number, native in natives_by_row.items():
            values_by_row_number[row_number] = format_absolute_iso(native) if native is not None else None
    else:
        # The anchor is the FIRST successfully-parsed native value, in
        # row order -- never assumed to be row_order[0] itself (that
        # row may have failed to interpret; task's own "the correct
        # action is to fix the Time Axis configuration, never silently
        # skip to a later anchor" is honored by still deriving relative
        # values for every OTHER row once a real anchor is found).
        anchor = next((natives_by_row[pr.row_number] for pr in preview_rows if natives_by_row[pr.row_number] is not None), None)
        # 2026-09-05 fix: `relative_seconds_with_anchor()` must be called
        # ONCE with the FULL row-ordered sequence of successfully-parsed
        # natives, never once PER ROW with a one-element list. This
        # matters for FAMILY_PARTIAL (Time of Day) specifically: its
        # midnight-rollover unwrap (the SAME shared logic
        # `preparation_conversion_service`/`preparation_export_service`
        # already rely on for their own canonical/exported values) walks
        # the sequence step by step from one row to the NEXT, so it can
        # only ever unwrap a genuine rollover if it actually SEES every
        # intervening row -- calling it with a single-row list collapses
        # every step between the anchor and that one row into one lone
        # comparison, which only happens to look right for a row
        # immediately adjacent to the anchor and silently produces a
        # huge, wrong negative value for anything further past a real
        # rollover (verified directly: a row 5 minutes after a genuine
        # midnight crossing previously computed roughly -86100s instead
        # of the correct +300s). Batching once here is not a new
        # algorithm -- it is the SAME call `_canonical_time_and_anchor()`
        # already makes for the whole active region, so Data Preview and
        # canonical conversion can never disagree about a Time of Day
        # value again, including exactly at a pagination boundary (this
        # function already computes the FULL active region in one pass,
        # regardless of which page later narrows it down -- see this
        # function's own "Critical guardrail" paragraph above).
        ordered_resolved = [
            (pr.row_number, natives_by_row[pr.row_number]) for pr in preview_rows if natives_by_row[pr.row_number] is not None
        ]
        relative_by_row: dict[int, float] = {}
        if anchor is not None and ordered_resolved:
            try:
                relative_values = relative_seconds_with_anchor(
                    [native for _row_number, native in ordered_resolved], anchor, family=family,
                )
            except TypeError:
                relative_values = None
            if relative_values is not None:
                relative_by_row = {
                    row_number: rel for (row_number, _native), rel in zip(ordered_resolved, relative_values)
                }
        # Time of Day (additive): present CLOCK TIME (reference +
        # elapsed, wrapped for display by `format_time_of_day()` itself),
        # never plain elapsed seconds -- `anchor` above is already the
        # exact same first-active-row native value
        # `preparation_conversion_service`/`preparation_export_service`
        # use to derive `time_of_day_reference_seconds` at conversion
        # time, so this preview can never disagree with the eventual
        # canonical/exported clock reference.
        time_of_day_reference_seconds = (
            seconds_from_midnight(anchor) if family == time_axis_domain.FAMILY_PARTIAL and anchor is not None else None
        )
        for row_number in natives_by_row:
            rel = relative_by_row.get(row_number)
            if rel is None:
                values_by_row_number[row_number] = None
            elif time_of_day_reference_seconds is not None:
                values_by_row_number[row_number] = format_time_of_day(time_of_day_reference_seconds + rel)
            else:
                values_by_row_number[row_number] = format_relative_seconds(rel)

    return ConfiguredTimeValues(column_name=column_name, family=family, values_by_row_number=values_by_row_number)


def configured_time_for_preview_page(
    *, workspace_id: str, source_id: str, page_rows: list[PreviewRow], registry: PreparationSessionRegistry,
) -> tuple[str, str, list[str | None]] | None:
    """Narrows `build_configured_time_values()`'s own full-active-region
    result down to exactly `page_rows`' own rows, in the SAME order --
    the one function `GET .../rows` calls to build its own additive
    `configured_time` response field. Returns `(column_name, family,
    values)`, or `None` (never an empty column) when the Time Axis is
    not currently resolved enough to derive a value from at all."""
    computed = build_configured_time_values(workspace_id=workspace_id, source_id=source_id, registry=registry)
    if computed is None:
        return None
    values = [computed.values_by_row_number.get(row.row_number) for row in page_rows]
    return computed.column_name, computed.family, values
