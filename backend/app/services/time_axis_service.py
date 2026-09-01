"""Time-Axis interpretation FRAMEWORK orchestration (CSV/Excel ingestion
Slice 7, DEC-072). Authoritative design source:
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

FRAMEWORK ONLY: this module does not parse a single real timestamp, does
not compute a real confidence value, and does not gate anything. Its own
`_INTERPRETERS` registry currently holds exactly two entries -- `manual`
(the user asserts the family/provenance/unit directly) and `unsupported`
(the universal fallback sentinel) -- both non-parsing by design (task's
own "for example: pass_through / unsupported / manual... not to parse
real datetime formats" guidance). Slice 8 adds real interpreters to this
same registry; nothing here changes shape when that happens.

Column-role relationship (task section N): a `TimeAxisConfiguration` is
never mutated or auto-cleared when a column's role changes away from
Time Axis -- see `app.domain.time_axis.resolve_status`'s own docstring
for why auto-clearing was considered and rejected. Instead,
`_columns_still_time_axis()` is recomputed live, on every read, against
the session's CURRENT `column_roles`, and fed into
`build_interpretation_result()` so a stale configuration is always
reported as `STATUS_UNSUPPORTED`, never silently presented as valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain import time_axis as time_axis_domain
from app.domain import working_overlay as overlay_domain
from app.domain.preparation_session import PreparationSession
from app.domain.time_axis import (
    KNOWN_PROVENANCES,
    KNOWN_TIME_FAMILIES,
    TimeAxisConfiguration,
    TimeAxisDiagnostic,
    TimeAxisInterpretationResult,
)
from app.services.errors import (
    InvalidTimeAxisConfigurationError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    UnknownTimeAxisInterpreterError,
    WorksheetNotSelectedError,
)
from app.services.preparation_preview_service import ensure_csv_totals_cached
from app.services.preparation_session_registry import PreparationSessionRegistry


class TimeAxisInterpreter(Protocol):
    """The interpreter contract every registry entry satisfies. `accepts`
    is a cheap, purely structural pre-check (never inspects cell values --
    no interpreter in this framework reads raw data); `build_configuration`
    produces the actual `TimeAxisConfiguration` to store. Both are pure
    functions of their own arguments -- no interpreter holds state."""

    interpreter_id: str

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
    ) -> TimeAxisConfiguration: ...


@dataclass(slots=True, frozen=True)
class _ManualInterpreter:
    """Accepts any non-empty column set unconditionally. Stores exactly
    the family/provenance/unit/interval the caller supplied -- this
    interpreter does not itself decide or validate what a sensible family
    is; `set_time_axis_configuration()` below already checked `family`/
    `provenance` against the known closed sets before an interpreter is
    ever reached."""

    interpreter_id: str = time_axis_domain.INTERPRETER_ID_MANUAL

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
    ) -> TimeAxisConfiguration:
        return TimeAxisConfiguration(
            column_indices=column_indices,
            family=family,
            provenance=provenance,
            interpreter_id=self.interpreter_id,
            unit=unit,
            interval_seconds=interval_seconds,
            confirmed=confirmed,
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


# Small, explicit, hand-written registry -- no dynamic loading, no entry
# points, no external config (task section G: "Do NOT build dynamic
# plugin discovery... An explicit registry/list is sufficient").
_INTERPRETERS: dict[str, TimeAxisInterpreter] = {
    time_axis_domain.INTERPRETER_ID_MANUAL: _ManualInterpreter(),
    time_axis_domain.INTERPRETER_ID_UNSUPPORTED: _UnsupportedInterpreter(),
}


def list_time_axis_interpreters() -> list[str]:
    """Every registered interpreter id, for the API's own metadata
    endpoint and for schema validation of a caller-supplied
    `interpreter_id` override."""
    return list(_INTERPRETERS.keys())


def resolve_interpreter(*, column_count: int, requested_interpreter_id: str | None) -> TimeAxisInterpreter:
    """`requested_interpreter_id` must name a registered interpreter if
    given at all -- raises `UnknownTimeAxisInterpreterError` otherwise
    (task section M: "interpreter id exists"). With no explicit request,
    resolves to the first registered interpreter that `accepts()` this
    column count, falling back to `unsupported` if none do (structurally
    unreachable today, since `manual` accepts every column_count >= 1 and
    Slice 7 never calls this with `column_count == 0`, but implemented
    for real so Slice 8's additional interpreters -- and this fallback
    path itself -- are directly unit-testable via a synthetic fake
    interpreter whose `accepts()` returns `False`)."""
    if requested_interpreter_id is not None:
        interpreter = _INTERPRETERS.get(requested_interpreter_id)
        if interpreter is None:
            raise UnknownTimeAxisInterpreterError(
                f"interpreter_id must be one of {list_time_axis_interpreters()}; got {requested_interpreter_id!r}."
            )
        return interpreter
    for interpreter in _INTERPRETERS.values():
        if interpreter.interpreter_id == time_axis_domain.INTERPRETER_ID_UNSUPPORTED:
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


def get_time_axis_summary(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> TimeAxisInterpretationResult:
    """Derived live on every call, directly from the session's own
    current `WorkingOverlay.time_axis` + `column_roles` state -- nothing
    is ever cached (see this module's own docstring)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    configuration = session.working_overlay.time_axis.get(worksheet_index)
    columns_still_time_axis = (
        _columns_still_time_axis(session, worksheet_index, configuration.column_indices)
        if configuration is not None
        else True
    )
    diagnostics: list[TimeAxisDiagnostic] = []
    return time_axis_domain.build_interpretation_result(
        configuration, columns_still_time_axis=columns_still_time_axis, diagnostics=diagnostics,
    )


def set_time_axis_configuration(
    *,
    workspace_id: str,
    source_id: str,
    column_indices: tuple[int, ...],
    family: str,
    provenance: str,
    unit: str | None = None,
    interval_seconds: float | None = None,
    confirmed: bool = False,
    interpreter_id: str | None = None,
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
    - `family`/`provenance` are each one of the known closed sets.
    - `interval_seconds`, if given, is finite and positive.
    - `interpreter_id`, if given, names a registered interpreter.
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
    if family not in KNOWN_TIME_FAMILIES:
        raise InvalidTimeAxisConfigurationError(f"family must be one of {KNOWN_TIME_FAMILIES}; got {family!r}.")
    if provenance not in KNOWN_PROVENANCES:
        raise InvalidTimeAxisConfigurationError(
            f"provenance must be one of {KNOWN_PROVENANCES}; got {provenance!r}."
        )
    if interval_seconds is not None and not (interval_seconds > 0):
        raise InvalidTimeAxisConfigurationError("interval_seconds must be a positive number when given.")

    interpreter = resolve_interpreter(column_count=len(column_indices), requested_interpreter_id=interpreter_id)
    configuration = interpreter.build_configuration(
        column_indices=tuple(column_indices),
        family=family,
        provenance=provenance,
        unit=unit,
        interval_seconds=interval_seconds,
        confirmed=confirmed,
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
