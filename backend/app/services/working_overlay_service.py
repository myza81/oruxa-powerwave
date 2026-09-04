"""Working Dataset overlay orchestration (CSV/Excel ingestion Slices 4-5, DEC-072).

The HTTP-mappable layer over `app.domain.working_overlay`'s own pure
data structures/mutation functions -- this module owns exactly the
things that module deliberately does not:

    resolve (workspace_id, source_id) -> PreparationSession (registry)
            |
    resolve which worksheet's coordinate space applies (None for CSV;
    the selected worksheet for Excel -- never guessed)
            |
    validate the request against THIS source's own known dimensions
    (structural row_number>=1 / column_index>=0 bounds are already
    enforced by the API's own Path(ge=...) constraints -- see
    app.api.v1.preparation_sources, matching that router's existing
    Query(ge=0)/Query(gt=0, le=...) precedent for offset/limit; this
    module only ever checks the UPPER bound, which depends on this
    one source's own dimensions and so cannot live in a static Path
    constraint)
            |
    app.domain.working_overlay's own pure mutation functions
            |
    WorkingOverlaySummary (also reused by GET .../preparation-sources/{id})

Never reads or writes `raw_bytes`, never touches a `DisturbanceRecord`,
never interprets a cell value's or a column's engineering meaning -- see
`app.domain.working_overlay`'s own module docstring for why a working
value is always a plain string and a column role is only ever the
user's own stated intent (Slice 5), not a validated/inferred fact.

Slice 5 adds header-row selection, data-region narrowing, and column
role assignment, each validated the same way Slice 4's cell/row/column
operations already are: a structural lower bound at the API's own
`Path(ge=...)` layer, and an upper bound checked here against this
source's own known row/column totals (reusing `_row_total`/
`_check_row_bound`/`_check_column_bound` -- the exact same helpers
Slice 4 built, not a second parallel bounds-checking implementation).

A later owner-UAT refinement extends `set_data_region()` with
`end_mode` (`END_MODE_SOURCE_END`/`END_MODE_SPECIFIC`) so a region's
own upper bound can float with the source/worksheet's own end instead
of always requiring a manually-found numeric row -- see
`app.domain.working_overlay.DataRegion`'s own docstring. This stays a
single, dataset-wide boundary; there is still no per-column end.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import working_overlay as overlay_domain
from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_UNDEFINED,
    KNOWN_ENGINEERING_QUANTITIES,
    measured_unit_valid_for_quantity,
    parse_engineering_quantity_and_unit_suffix,
)
from app.domain.preparation_session import PreparationSession
from app.services.errors import (
    InvalidColumnRoleError,
    InvalidDataRegionError,
    InvalidEngineeringQuantityError,
    InvalidMeasuredUnitError,
    InvalidWorkingCellValueError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    WorksheetNotSelectedError,
)
from app.services.preparation_preview_service import ensure_csv_totals_cached, resolve_single_column_label
from app.services.preparation_session_registry import PreparationSessionRegistry


@dataclass(slots=True)
class WorkingOverlaySummary:
    """A cheap, O(1)-ish snapshot of one session's own working overlay --
    never the overlay's full content (that is what the preview endpoint
    is for). `edited_cell_count` counts BOTH edits and explicit clears
    (both live in `WorkingOverlay.cell_overrides`, see that dataclass's
    own docstring) -- this summary does not distinguish the two kinds,
    only how many cells currently differ from raw.

    `edited_cell_count`/`excluded_row_count`/`can_undo`/`can_redo` are
    GLOBAL across every worksheet of this source (unchanged from Slice
    4). `header_row_number`/
    `data_start_row`/`data_end_mode`/`data_end_row` are, by contrast,
    scoped to ONE worksheet (Slice 5) -- whichever `worksheet_index` the
    caller resolved for its own operation (`None` for CSV; the selected
    sheet, or `None` if none is selected yet, for Excel). This
    intentional mix is why every caller of `summarize_working_overlay()`
    must pass the worksheet scope it actually resolved, never a fixed
    default.

    `data_end_mode`/`data_end_row` mirror
    `app.domain.working_overlay.DataRegion`'s own two fields verbatim
    (a later owner-UAT refinement) -- `data_end_row` is `None` for
    `END_MODE_SOURCE_END` (there is no stored numeric end to report,
    deliberately never a resolved/guessed one) and a real row number for
    `END_MODE_SPECIFIC`. Both are `None` when no region is configured at
    all (distinct from `END_MODE_SOURCE_END` -- see that constant's own
    docstring for why "no region" and "region with a floating end" are
    different states).

    UAT fix (2026-09-04): `ignored_column_count` is retired -- the
    three-role simplification (`not_assigned`/`time_axis`/`waveform`)
    makes "not assigned" the sparse DEFAULT (never an explicit
    `column_roles` entry, per `app.domain.working_overlay`'s own
    "absence is the default" convention), so it can no longer be
    counted the way the old, always-explicit `ignore` role could. This
    was already a purely-informational counter with no readiness/export
    consequence of its own; a caller wanting "how many columns are not
    assigned" now derives it from the preview's own `column_roles`
    array (task section S's own preferred "N Time · N Waveform · N Not
    Assigned" summary phrasing).
    """

    working_revision: int
    edited_cell_count: int
    excluded_row_count: int
    can_undo: bool
    can_redo: bool
    header_row_number: int | None
    data_start_row: int | None
    data_end_mode: str | None
    data_end_row: int | None


def summarize_working_overlay(session: PreparationSession, worksheet_index: int | None = None) -> WorkingOverlaySummary:
    """Shared by every mutation function below AND by
    `GET .../preparation-sources/{source_id}` (Slice 4 extends that
    existing endpoint's own response with this same summary), so there
    is exactly one place that defines what these counters mean.

    `worksheet_index` scopes ONLY `header_row_number`/`data_start_row`/
    `data_end_mode`/`data_end_row` (Slice 5) -- pass `None` for CSV, or
    for an Excel source with no worksheet selected yet (in which case
    these fields correctly come back `None`, since Slice 5 mutations can
    only ever write under a REAL worksheet index for Excel -- see
    `_resolve_worksheet_index`'s own docstring)."""
    overlay = session.working_overlay
    region = overlay.data_region.get(worksheet_index)
    return WorkingOverlaySummary(
        working_revision=overlay.revision,
        edited_cell_count=len(overlay.cell_overrides),
        excluded_row_count=len(overlay.excluded_rows),
        can_undo=bool(overlay.history),
        can_redo=bool(overlay.redo_stack),
        header_row_number=overlay.header_row.get(worksheet_index),
        data_start_row=region.start_row if region else None,
        data_end_mode=region.end_mode if region else None,
        data_end_row=region.end_row if region else None,
    )


def _resolve_session(*, workspace_id: str, source_id: str, registry: PreparationSessionRegistry) -> PreparationSession:
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(f"No preparation source '{source_id}' in workspace '{workspace_id}'.")
    return session


def _resolve_worksheet_index(session: PreparationSession) -> int | None:
    """`None` for CSV (no worksheet dimension at all). For Excel, the
    currently selected worksheet -- never guessed: raises
    `WorksheetNotSelectedError` for a multi-sheet workbook with no
    selection yet, exactly mirroring
    `preparation_preview_service._preview_excel`'s own rule, so a
    working edit is always made against the same coordinate space the
    preview itself is currently showing. Used for every mutation that
    targets a specific worksheet (cell/row/column/header/data-region
    writes) -- NOT used for reset-all/undo/redo, which are session-wide
    and must stay available even with no worksheet selected yet (see
    those functions' own use of `session.summary.selected_worksheet_index`
    directly instead)."""
    worksheets = session.summary.worksheets
    if not worksheets:
        return None
    if session.summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before editing its working dataset."
        )
    return session.summary.selected_worksheet_index


def _row_total(session: PreparationSession, worksheet_index: int | None) -> int | None:
    if worksheet_index is None:
        ensure_csv_totals_cached(session)
        return session.cached_row_count
    return session.summary.worksheets[worksheet_index].row_count


def _column_total(session: PreparationSession, worksheet_index: int | None) -> int | None:
    if worksheet_index is None:
        ensure_csv_totals_cached(session)
        return session.cached_column_count
    return session.summary.worksheets[worksheet_index].column_count


def _check_row_bound(session: PreparationSession, worksheet_index: int | None, row_number: int) -> None:
    total = _row_total(session, worksheet_index)
    # A `None` total (Excel worksheet with no cheap dimension hint, see
    # WorksheetInfo's own docstring) is never fabricated into a false
    # bound -- only a KNOWN total is ever enforced.
    if total is not None and row_number > total:
        raise InvalidWorkingCoordinateError(
            f"row_number {row_number} is beyond this source's own {total} known rows."
        )


def _check_column_bound(session: PreparationSession, worksheet_index: int | None, column_index: int) -> None:
    total = _column_total(session, worksheet_index)
    if total is not None and column_index >= total:
        raise InvalidWorkingCoordinateError(
            f"column_index {column_index} is beyond this source's own {total} known columns."
        )


def edit_cell(
    *,
    workspace_id: str,
    source_id: str,
    row_number: int,
    column_index: int,
    value: str | None,
    registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Set (or clear, when `value is None`) one cell's working value --
    see `app.domain.working_overlay.CellOverride`'s own docstring for
    why these stay distinct kinds despite rendering identically today."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_row_bound(session, worksheet_index, row_number)
    _check_column_bound(session, worksheet_index, column_index)
    if value is not None and len(value) > overlay_domain.MAX_CELL_VALUE_LENGTH:
        raise InvalidWorkingCellValueError(
            f"Cell working value exceeds the maximum length of "
            f"{overlay_domain.MAX_CELL_VALUE_LENGTH} characters."
        )
    key = overlay_domain.cell_key(worksheet_index, row_number, column_index)
    overlay_domain.set_cell_value(session.working_overlay, key, value)
    return summarize_working_overlay(session, worksheet_index)


def reset_cell(
    *, workspace_id: str, source_id: str, row_number: int, column_index: int, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Remove one cell's override entirely (a safe no-op if it had
    none) -- the working value reverts to the raw value exactly."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    key = overlay_domain.cell_key(worksheet_index, row_number, column_index)
    overlay_domain.reset_cell(session.working_overlay, key)
    return summarize_working_overlay(session, worksheet_index)


def set_row_excluded(
    *, workspace_id: str, source_id: str, row_number: int, excluded: bool, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Mark (or unmark) one row as excluded from the working view.
    Never renumbers surrounding rows -- see
    `app.domain.working_overlay`'s own module docstring. Independent of
    Slice 5's own data region: a row can be inside the active region
    AND excluded at the same time -- these are different concepts (task
    section: "Interaction with excluded rows"), never conflated here."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_row_bound(session, worksheet_index, row_number)
    key = overlay_domain.row_key(worksheet_index, row_number)
    overlay_domain.set_row_excluded(session.working_overlay, key, excluded)
    return summarize_working_overlay(session, worksheet_index)


def set_column_role(
    *, workspace_id: str, source_id: str, column_index: int, role: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Assign one column's semantic role (Slice 5). `role` must be one
    of `app.domain.working_overlay.KNOWN_COLUMN_ROLES` -- never a
    free-text field. Multiple columns may carry `ROLE_TIME_AXIS`
    simultaneously (task's own explicit "do not assume the future time
    basis must always come from exactly one physical column" guidance)
    -- no uniqueness/compatibility check is performed here or anywhere
    else in this slice; that is Slice 7/8's own concern once real
    time-axis interpretation exists."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    if role not in overlay_domain.KNOWN_COLUMN_ROLES:
        raise InvalidColumnRoleError(
            f"role must be one of {overlay_domain.KNOWN_COLUMN_ROLES}; got {role!r}."
        )
    _check_column_bound(session, worksheet_index, column_index)
    key = overlay_domain.column_key(worksheet_index, column_index)
    overlay_domain.set_column_role(session.working_overlay, key, role)
    # Engineering Quantity + Measured Unit suffix restoration (DEC-077/
    # DEC-080, task section S): the ONE place this fires. Only when the
    # column is newly being assigned ROLE_WAVEFORM AND has no EXPLICIT
    # quantity of its own yet (never overwrites a prior explicit choice,
    # including an explicit "Undefined") -- parses the column's current
    # WORKING label via the SAME deterministic suffix grammar the
    # exporter itself writes (app.domain.channel_classification.
    # parse_engineering_quantity_and_unit_suffix()), never a second,
    # looser guess. A quantity-only DEC-077 suffix (no unit bracket)
    # still restores the quantity alone, exactly as before -- the
    # combined parser falls back to that grammar automatically. The unit
    # is only ever auto-suggested ALONGSIDE a freshly-suggested quantity
    # here, never on its own against an already-explicit quantity, so an
    # explicit "Undefined" quantity with no unit is never disturbed.
    # Recorded as its own separate WorkingOperation(s) (a documented,
    # intentional simplification: reverting this specific restoration
    # takes extra Undo clicks beyond reverting the role assignment
    # itself -- every OTHER mutation in this module stays a strict
    # one-action-one-undo-step operation; only this rare, first-time-only
    # auto-suggestion path does not). Role=Waveform itself is NEVER
    # auto-assigned by this suffix match -- only the already-user-chosen
    # role's own Engineering Quantity/Measured Unit are.
    if role == overlay_domain.ROLE_WAVEFORM and key not in session.working_overlay.column_engineering_quantities:
        label = resolve_single_column_label(session, worksheet_index=worksheet_index, column_index=column_index)
        _, suggested_quantity, suggested_unit = parse_engineering_quantity_and_unit_suffix(label)
        if suggested_quantity is not None:
            overlay_domain.set_column_engineering_quantity(session.working_overlay, key, suggested_quantity)
            if suggested_unit is not None:
                overlay_domain.set_column_measured_unit(session.working_overlay, key, suggested_unit)
    return summarize_working_overlay(session, worksheet_index)


def reset_column_role(
    *, workspace_id: str, source_id: str, column_index: int, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Return one column's role to `ROLE_NOT_ASSIGNED` (a safe no-op if
    it already had no explicit role) -- the single neutral default
    state, never any other implicit value. The column's own Engineering
    Quantity (if any) is deliberately left untouched -- see
    `app.domain.working_overlay.WorkingOverlay.column_engineering_
    quantities`'s own docstring for why (task section J: "ignored," not
    cleared, so it survives if the column returns to Waveform later)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    key = overlay_domain.column_key(worksheet_index, column_index)
    overlay_domain.reset_column_role(session.working_overlay, key)
    return summarize_working_overlay(session, worksheet_index)


def set_column_engineering_quantity(
    *, workspace_id: str, source_id: str, column_index: int, engineering_quantity: str,
    registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Assign one column's Engineering Quantity (DEC-077). `engineering_
    quantity` must be one of `app.domain.channel_classification.
    KNOWN_ENGINEERING_QUANTITIES` -- never a free-text field. Meaningful
    only for a column currently carrying `ROLE_WAVEFORM` (task section C)
    -- this function does not itself check the column's current role
    (matching `set_column_role()`'s own "no cross-field validation"
    precedent); a value stored for a non-Waveform column is simply
    ignored by every downstream reader until the column becomes Waveform
    again."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    if engineering_quantity not in KNOWN_ENGINEERING_QUANTITIES:
        raise InvalidEngineeringQuantityError(
            f"engineering_quantity must be one of {KNOWN_ENGINEERING_QUANTITIES}; got {engineering_quantity!r}."
        )
    _check_column_bound(session, worksheet_index, column_index)
    key = overlay_domain.column_key(worksheet_index, column_index)
    overlay_domain.set_column_engineering_quantity(session.working_overlay, key, engineering_quantity)
    # Measured Unit enhancement (DEC-080, task section J): a quantity
    # change invalidates an existing unit that is no longer a member of
    # the NEW quantity's own controlled list (e.g. Voltage's "kV" is not
    # valid once the quantity becomes Frequency) -- cleared to blank,
    # never silently converted (task's own explicit "must not become Hz
    # automatically" example). A unit that is STILL valid for the new
    # quantity (including a coincidentally-shared blank) is left alone.
    existing_unit = session.working_overlay.column_measured_units.get(key)
    if existing_unit is not None and not measured_unit_valid_for_quantity(engineering_quantity, existing_unit):
        overlay_domain.reset_column_measured_unit(session.working_overlay, key)
    return summarize_working_overlay(session, worksheet_index)


def reset_column_engineering_quantity(
    *, workspace_id: str, source_id: str, column_index: int, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Return one column's Engineering Quantity to `Undefined` (a safe
    no-op if it already had no explicit value) -- the single neutral
    default state, never any other implicit value."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    key = overlay_domain.column_key(worksheet_index, column_index)
    overlay_domain.reset_column_engineering_quantity(session.working_overlay, key)
    # Same policy as the explicit-quantity-change path above: reverting
    # to Undefined only ever allows a blank unit (task section R) --
    # `column_measured_units` is sparse (a stored entry is never blank,
    # see set_column_measured_unit()'s own "" -> pop convention), so any
    # stored entry at all is, by construction, invalid for Undefined and
    # gets cleared too.
    if key in session.working_overlay.column_measured_units:
        overlay_domain.reset_column_measured_unit(session.working_overlay, key)
    return summarize_working_overlay(session, worksheet_index)


def set_column_measured_unit(
    *, workspace_id: str, source_id: str, column_index: int, measured_unit: str,
    registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Assign one column's Measured Unit (DEC-080). `measured_unit` must
    be `""` (always valid) or a member of `app.domain.channel_
    classification.MEASURED_UNIT_OPTIONS` for the column's CURRENT
    Engineering Quantity (default `Undefined` if none is set) -- never a
    free-text field, and the backend validates the pair itself (task
    section AF/AE), never trusting the frontend's own dropdown filtering
    alone. Meaningful only for a column currently carrying `ROLE_
    WAVEFORM` (task section D) -- this function does not itself check
    the column's current role, matching `set_column_engineering_
    quantity()`'s own "no cross-field validation" precedent; a value
    stored for a non-Waveform column is simply ignored by every
    downstream reader until the column becomes Waveform again."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_column_bound(session, worksheet_index, column_index)
    key = overlay_domain.column_key(worksheet_index, column_index)
    current_quantity = session.working_overlay.column_engineering_quantities.get(
        key, ENGINEERING_QUANTITY_UNDEFINED
    )
    if not measured_unit_valid_for_quantity(current_quantity, measured_unit):
        raise InvalidMeasuredUnitError(
            f"measured_unit {measured_unit!r} is not valid for engineering_quantity {current_quantity!r}."
        )
    overlay_domain.set_column_measured_unit(session.working_overlay, key, measured_unit)
    return summarize_working_overlay(session, worksheet_index)


def reset_column_measured_unit(
    *, workspace_id: str, source_id: str, column_index: int, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Return one column's Measured Unit to blank (a safe no-op if it
    already had no explicit value) -- the single neutral default state,
    never any other implicit value."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    key = overlay_domain.column_key(worksheet_index, column_index)
    overlay_domain.reset_column_measured_unit(session.working_overlay, key)
    return summarize_working_overlay(session, worksheet_index)


def set_header_row(
    *, workspace_id: str, source_id: str, row_number: int, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Select which raw row supplies working column labels (Slice 5).
    `row_number` may be inside or outside the current data region, and
    may be any row this source actually has -- the only requirement
    enforced here is that it exists (`_check_row_bound`); this slice
    deliberately does not force `header_row < data_start_row` or any
    other positional relationship (task section: "do not silently
    force... unless the user explicitly chooses it")."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_row_bound(session, worksheet_index, row_number)
    overlay_domain.set_header_row(session.working_overlay, worksheet_index, row_number)
    return summarize_working_overlay(session, worksheet_index)


def clear_header_row(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Remove the header-row selection -- working column labels revert
    to the neutral spreadsheet-letter fallback. Column role assignments
    are left untouched (see `app.domain.working_overlay.clear_header_row`'s
    own docstring)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    overlay_domain.clear_header_row(session.working_overlay, worksheet_index)
    return summarize_working_overlay(session, worksheet_index)


def set_data_region(
    *,
    workspace_id: str,
    source_id: str,
    start_row: int,
    end_row: int | None = None,
    end_mode: str = overlay_domain.END_MODE_SPECIFIC,
    registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Narrow the active working dataset (Slice 5; `end_mode` added by a
    later owner-UAT refinement -- owner feedback that manually finding
    the true last row of a large source was "unnecessarily burdensome").

    `end_mode` defaults to `END_MODE_SPECIFIC` so every pre-refinement
    caller (`start_row`/`end_row` only, no `end_mode`) keeps working
    completely unchanged -- a real backward-compatibility guarantee, not
    an arbitrary default. For `END_MODE_SOURCE_END`, `end_row` is
    ignored (never stored -- see `app.domain.working_overlay.DataRegion`'s
    own docstring for why a floating end is never resolved into a stored
    guess) and no upper-bound validation applies to it at all, since
    there is no numeric end to validate.

    Raises `InvalidDataRegionError` for an unrecognized `end_mode`, for
    `END_MODE_SPECIFIC` with no `end_row` supplied, or for
    `start_row > end_row` under `END_MODE_SPECIFIC` (a semantic error,
    distinct from either bound being outside this source's own known
    dimensions, which raises `InvalidWorkingCoordinateError` via
    `_check_row_bound` instead -- task's own explicit "if the source/
    sheet extent is uncertain... do not falsely reject a valid row"
    guardrail: an unknown total simply skips that bound check, exactly
    as `_check_row_bound` already does for every other coordinate).
    """
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    if end_mode not in overlay_domain.KNOWN_END_MODES:
        raise InvalidDataRegionError(
            f"end_mode must be one of {overlay_domain.KNOWN_END_MODES}; got {end_mode!r}."
        )
    if end_mode == overlay_domain.END_MODE_SPECIFIC:
        if end_row is None:
            raise InvalidDataRegionError("end_row is required when end_mode is 'specific'.")
        if start_row > end_row:
            raise InvalidDataRegionError(
                f"start_row ({start_row}) must be <= end_row ({end_row})."
            )
        _check_row_bound(session, worksheet_index, end_row)
    else:
        end_row = None  # never store a stray numeric value for a floating end
    _check_row_bound(session, worksheet_index, start_row)
    overlay_domain.set_data_region(session.working_overlay, worksheet_index, start_row, end_row, end_mode=end_mode)
    return summarize_working_overlay(session, worksheet_index)


def reset_data_region(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Remove the data-region narrowing -- the entire source range
    becomes active again (Slice 4's own original default)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    overlay_domain.reset_data_region(session.working_overlay, worksheet_index)
    return summarize_working_overlay(session, worksheet_index)


def reset_all_working_changes(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Clear every cell override, row exclusion, column role, header
    selection, and data-region narrowing for this source in one step
    (Slice 5 extends Slice 4's own "Reset All" to also cover structure/
    semantic mapping state -- see `app.domain.working_overlay.reset_all`'s
    own docstring) -- still undoable. Uses
    `session.summary.selected_worksheet_index` directly (never
    `_resolve_worksheet_index`, which would raise) so Reset All keeps
    working even for a multi-sheet Excel workbook with no worksheet
    selected yet -- this is a session-wide operation, not one that
    targets a specific worksheet's own coordinate space."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    overlay_domain.reset_all(session.working_overlay)
    return summarize_working_overlay(session, session.summary.selected_worksheet_index)


def undo_working_change(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Revert the most recent working-dataset operation, of any kind
    (cell/row/column-role/header/data-region/reset-all). A safe no-op
    when there is nothing to undo -- never an error, since a disabled
    Undo button racing a click is a normal UI state, not a client
    mistake."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    overlay_domain.undo(session.working_overlay)
    return summarize_working_overlay(session, session.summary.selected_worksheet_index)


def redo_working_change(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Reapply the most recently undone operation. A safe no-op when
    there is nothing to redo."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    overlay_domain.redo(session.working_overlay)
    return summarize_working_overlay(session, session.summary.selected_worksheet_index)
