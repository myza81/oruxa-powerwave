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

import math
from dataclasses import dataclass

import numpy as np

from app.domain import working_overlay as overlay_domain
from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_UNDEFINED,
    KNOWN_ENGINEERING_QUANTITIES,
    measured_unit_valid_for_quantity,
    parse_engineering_quantity_and_unit_suffix,
)
# Missing-value fill/estimation enhancement (owner UAT hardening pass,
# 2026-09-10): imported from the shared, calculated-channel-agnostic
# app.domain.missing_data_estimation -- NEVER from app.domain.
# calculated_channel (that module now re-exports these same names only
# for its own pre-existing callers; Data Preparation has no legitimate
# reason to depend on the Calculated Channel domain merely to obtain
# generic estimation constants). See that module's own docstring.
from app.domain.missing_data_estimation import (
    ESTIMATION_METHOD_LINEAR,
    ESTIMATION_METHOD_LOCAL_MEAN,
    UNIMPLEMENTED_ESTIMATION_METHODS,
    apply_estimation,
    estimation_method_valid,
    find_gaps,
    local_mean_radius_valid,
    max_gap_unit_valid,
    max_gap_value_valid,
)
from app.domain.preparation_issue import ISSUE_WAVEFORM_VALUE_INVALID, ISSUE_WAVEFORM_VALUE_MISSING
from app.domain.preparation_session import PreparationSession
from app.services.errors import (
    InvalidColumnRoleError,
    InvalidDataRegionError,
    InvalidEngineeringQuantityError,
    InvalidEstimationConfigurationError,
    InvalidFillTargetError,
    InvalidMeasuredUnitError,
    InvalidWorkingCellValueError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    WorksheetNotSelectedError,
)
from app.services.preparation_preview_service import (
    ensure_csv_totals_cached,
    iterate_active_region_rows,
    resolve_single_column_label,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.readiness_service import eligible_bulk_null_rows
from app.services.time_axis_interpreters import _to_float


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
    kind: str | None = None,
    registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Set (or clear, when `value is None`) one cell's working value --
    see `app.domain.working_overlay.CellOverride`'s own docstring for
    why these stay distinct kinds despite rendering identically today.

    DEC-084 (Slice 1): `kind=overlay_domain.OVERRIDE_KIND_NULL` requests
    the THIRD, explicit-null kind instead. `value` must be omitted or
    explicitly `None` in that case -- a REAL (non-`None`) `value` alongside
    `kind="null"` is rejected outright, never silently discarded (DEC-084's
    own "must not silently reinterpret or discard supplied data"
    guardrail: a future buggy client sending both an explicit-null
    operation and a real value must fail visibly, not lose the value
    quietly). `kind=None` (the default) preserves the original edit/clear
    behavior exactly, unchanged, for every existing caller. Any other
    `kind` is rejected outright -- never silently downgraded to
    edit/clear."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_row_bound(session, worksheet_index, row_number)
    _check_column_bound(session, worksheet_index, column_index)
    key = overlay_domain.cell_key(worksheet_index, row_number, column_index)
    if kind is not None:
        if kind != overlay_domain.OVERRIDE_KIND_NULL:
            raise InvalidWorkingCellValueError(
                f"kind must be omitted or {overlay_domain.OVERRIDE_KIND_NULL!r}; got {kind!r}."
            )
        if value is not None:
            raise InvalidWorkingCellValueError(
                f"value must be omitted or null when kind={overlay_domain.OVERRIDE_KIND_NULL!r}; "
                f"got a non-null value instead."
            )
        overlay_domain.set_cell_null(session.working_overlay, key)
        return summarize_working_overlay(session, worksheet_index)
    if value is not None and len(value) > overlay_domain.MAX_CELL_VALUE_LENGTH:
        raise InvalidWorkingCellValueError(
            f"Cell working value exceeds the maximum length of "
            f"{overlay_domain.MAX_CELL_VALUE_LENGTH} characters."
        )
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


@dataclass(slots=True)
class BulkNullPreview:
    """DEC-084 (Slice 5): the authoritative eligible-cell COUNT for one
    `(column_index, issue_code)` bulk-null scope, computed WITHOUT any
    mutation -- never derived from the Data Issues browse list's own
    `MAX_CELL_ISSUES`-capped `cell_issues` (see `app.services.
    readiness_service.eligible_bulk_null_rows()`'s own docstring for
    why that cap must never define bulk scope)."""

    column_index: int
    issue_code: str
    eligible_count: int


@dataclass(slots=True)
class BulkNullApplyResult:
    """DEC-084 (Slice 5): the result of actually applying a bulk-null
    scope. `eligible_count` is re-evaluated FRESH at apply time --
    NEVER trusting a caller's own earlier preview call, since the
    overlay may have changed in between (task's own explicit "apply
    must re-evaluate current eligibility" / "stale scope" requirement).
    `applied_count` is the number of cells THIS call actually changed.
    Both are reported separately (task section 24/9's own suggested
    shape) even though they are equal by construction today (a cell
    `eligible_bulk_null_rows()` returns can never already be
    explicit-null -- see that function's own docstring -- so
    `bulk_set_cells_null()`'s own "skip already-null" branch never
    actually triggers here); keeping them as two distinct fields costs
    nothing and stays transparent/future-proof rather than collapsing
    an intentional distinction into one number."""

    column_index: int
    issue_code: str
    eligible_count: int
    applied_count: int
    overlay: WorkingOverlaySummary


def preview_bulk_mark_null(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str, registry: PreparationSessionRegistry,
) -> BulkNullPreview:
    """DEC-084 (Slice 5): count-before-apply (task section 8) -- a pure,
    read-only evaluation of exactly which cells `apply_bulk_mark_null()`
    would affect right now, with NO mutation and NO history entry.
    Mirrors the Time Axis `interpret`/apply precedent already
    established in this codebase (a dedicated preview step distinct
    from the mutating one, not a `dry_run` flag folded into the same
    endpoint).

    Raises `InvalidWorkingCoordinateError` for an out-of-range
    `column_index`, or `InvalidBulkNullIssueCodeError` for anything
    other than `ISSUE_WAVEFORM_VALUE_MISSING`/`ISSUE_WAVEFORM_VALUE_
    INVALID` (see `eligible_bulk_null_rows()`'s own docstring for why
    a Time Axis issue code is a real error here, never a silent zero).
    A column that is not currently Waveform (Not Assigned, Time Axis,
    or simply has zero matching cells right now) returns
    `eligible_count=0` -- not an error."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_column_bound(session, worksheet_index, column_index)
    rows = eligible_bulk_null_rows(
        session, worksheet_index=worksheet_index, column_index=column_index, issue_code=issue_code,
        workspace_id=workspace_id, source_id=source_id, registry=registry,
    )
    return BulkNullPreview(column_index=column_index, issue_code=issue_code, eligible_count=len(rows))


def apply_bulk_mark_null(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str, registry: PreparationSessionRegistry,
) -> BulkNullApplyResult:
    """DEC-084 (Slice 5): applies bulk explicit-null resolution to
    EVERY currently eligible cell in this exact `(column_index,
    issue_code)` scope, as ONE grouped, single-Undo/Redo working-overlay
    operation (`app.domain.working_overlay.bulk_set_cells_null()`) --
    never one HTTP request, one rescan, or one history entry per cell.

    Eligibility is recomputed HERE, fresh, from the CURRENT overlay
    state -- never from a caller's own earlier `preview_bulk_mark_null()`
    call, which may now be stale (a manual edit, an earlier Undo, or a
    role change could have happened in between). `eligible_count` in
    the response is this fresh count; `applied_count` is how many cells
    were actually changed. Valid raw values, valid manual edits, cells
    already resolved (explicit-null or no-longer-matching-the-issue-
    type), sibling channels on the same row, and any column that is not
    currently Waveform are all left completely untouched -- this
    function only ever writes the cells `eligible_bulk_null_rows()`
    itself currently reports.

    Raises the SAME `InvalidWorkingCoordinateError`/
    `InvalidBulkNullIssueCodeError` as `preview_bulk_mark_null()` for an
    invalid scope. Returns `applied_count=0` (a normal, successful
    response, never an error) when nothing is currently eligible --
    matching this module's own "no eligible cells is not a failure"
    precedent (e.g. `reset_cell()`'s own safe no-op)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_column_bound(session, worksheet_index, column_index)
    rows = eligible_bulk_null_rows(
        session, worksheet_index=worksheet_index, column_index=column_index, issue_code=issue_code,
        workspace_id=workspace_id, source_id=source_id, registry=registry,
    )
    keys = [overlay_domain.cell_key(worksheet_index, row_number, column_index) for row_number in rows]
    applied_count = overlay_domain.bulk_set_cells_null(session.working_overlay, keys)
    return BulkNullApplyResult(
        column_index=column_index, issue_code=issue_code,
        eligible_count=len(rows), applied_count=applied_count,
        overlay=summarize_working_overlay(session, worksheet_index),
    )


# ==============================================================================
# Missing-value fill/estimation enhancement (owner UAT, 2026-09-10)
#
# Extends DEC-084's original three resolution paths (Mark as Null / Fill
# Manually / Not Assigned) with a fourth -- Estimate Missing Value -- and
# a bulk-only fifth -- Constant Value fill -- for `waveform_value_missing`/
# `waveform_value_invalid` cells ONLY. Time Axis cells are never eligible
# (`_resolve_fill_scope()` enforces this backend-side via
# `_BULK_ISSUE_CODES`, never only in the frontend).
#
# Reuses, never duplicates:
#   - app.domain.missing_data_estimation.apply_estimation()/find_gaps() --
#     the SAME engine DEC-084 Calc Slice 2 built for calculated-channel
#     estimation (gap definition, per-method math, max-gap enforcement --
#     an oversized gap is left unfilled by that engine already, never
#     partially filled).
#   - app.domain.calculated_channel's own method/max-gap/local-mean-radius
#     constants and `*_valid()` predicates -- pure, config-shape-only,
#     zero calculated-channel-specific coupling, so reusing them here adds
#     no real dependency beyond a shared vocabulary (see this module's
#     own test coverage for the deliberate choice not to relocate them).
#   - app.services.readiness_service.eligible_bulk_null_rows() -- the
#     SAME authoritative, uncapped (column_index, issue_code) eligibility
#     list bulk Mark as Null already uses; estimation/fill never invents
#     a second interpretation of "which cells are currently unresolved."
#   - app.services.time_axis_service.build_configured_time_values() --
#     for Linear Interpolation only, the SAME resolved Time Axis
#     canonical conversion/cleaned export/Configured-Time-preview-column
#     already use, so Linear can never silently disagree with what
#     Powerwave will actually use as this recording's own time axis.
# ==============================================================================

#: The one "method" value that is NOT an estimation algorithm -- explicit
#: constant user fill (task section 7: "Constant Value is not
#: interpolation"). Deliberately NOT a member of
#: app.domain.calculated_channel.ALL_ESTIMATION_METHODS (calculated
#: channels have no constant-fill concept at all) -- validated as its
#: own case here instead.
FILL_METHOD_CONSTANT = "constant"

_BULK_ISSUE_CODES = (ISSUE_WAVEFORM_VALUE_MISSING, ISSUE_WAVEFORM_VALUE_INVALID)


def _validate_estimation_method(
    method: str, *, max_gap_value: object, max_gap_unit: object, local_mean_radius: object,
) -> None:
    if not estimation_method_valid(method):
        raise InvalidEstimationConfigurationError(
            f"method must be one of the recognized estimation methods; got {method!r}."
        )
    if method in UNIMPLEMENTED_ESTIMATION_METHODS:
        raise InvalidEstimationConfigurationError(f"method {method!r} is not implemented yet.")
    if not max_gap_value_valid(max_gap_value):
        raise InvalidEstimationConfigurationError("max_gap_value must be a positive whole number of samples.")
    if not max_gap_unit_valid(max_gap_unit):
        raise InvalidEstimationConfigurationError("max_gap_unit must be 'samples' -- no other unit is supported.")
    if method == ESTIMATION_METHOD_LOCAL_MEAN and not local_mean_radius_valid(local_mean_radius):
        raise InvalidEstimationConfigurationError(
            "local_mean_radius must be a positive whole number of samples when method='local_mean'."
        )


def _build_column_series(
    session: PreparationSession, *, worksheet_index: int | None, column_index: int,
) -> tuple[list[int], np.ndarray]:
    """One single-pass scan over the active region for ONE column,
    producing `(row_numbers, values)` where `values[i]` is the finite
    float currently at `row_numbers[i]` if that cell holds a valid
    working number, and NaN otherwise. Missing, unparseable/invalid, AND
    explicit-null cells are ALL represented as NaN here -- all three are
    equally "no usable value" for GAP-FINDING/bracketing purposes (you
    cannot interpolate FROM an invalid or deliberately-null cell any more
    than from a blank one). This does NOT mean an explicit-null cell can
    ever be overwritten: every caller below only ever WRITES to the
    `eligible_bulk_null_rows()` subset (missing/invalid, never null), so
    a null cell can influence gap math but is never itself a write
    target. Excluded rows, the header row, and rows outside the active
    region are skipped, matching every other full-region scan in this
    codebase."""
    row_numbers: list[int] = []
    values: list[float] = []
    for row in iterate_active_region_rows(session, worksheet_index=worksheet_index):
        if row.excluded or row.is_header or not row.in_active_region:
            continue
        row_numbers.append(row.row_number)
        if column_index in row.explicit_null_columns:
            values.append(float("nan"))
            continue
        cell = row.cells[column_index] if column_index < len(row.cells) else None
        parsed = _to_float(cell) if cell not in (None, "") else None
        values.append(parsed if parsed is not None else float("nan"))
    return row_numbers, np.array(values, dtype=float)


def _build_column_time_seconds(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry, row_numbers: list[int],
) -> np.ndarray:
    """Real, Time-Axis-aware elapsed seconds for each row in
    `row_numbers`, reusing `app.services.time_axis_service.
    build_configured_time_values()` -- the SAME resolved Time Axis
    canonical conversion/cleaned export/Configured-Time-preview-column
    already use. Linear Interpolation therefore uses actual aligned time
    coordinates, never assumed-uniform sample spacing (task section 8's
    own "reuse the already-approved calculated-channel semantics"
    requirement). For the absolute family the resolved value is an ISO
    string -- converted to a POSIX timestamp float purely as a
    consistent, monotonic linear time basis (interpolation only ever
    uses DIFFERENCES/RATIOS of this value, so a constant epoch offset is
    mathematically irrelevant); every other family's own resolved value
    is already a plain numeric-seconds string.

    Raises `InvalidEstimationConfigurationError` if the current Time
    Axis is not resolved enough to supply real coordinates -- Linear
    Interpolation is never silently downgraded to sample-index spacing."""
    # Local import: avoids a module-level import cycle (time_axis_service
    # itself imports from preparation_preview_service, which this module
    # already imports from at module scope).
    from app.domain.time_axis import FAMILY_ABSOLUTE
    from app.services.time_axis_service import build_configured_time_values
    from datetime import datetime

    configured = build_configured_time_values(workspace_id=workspace_id, source_id=source_id, registry=registry)
    if configured is None:
        raise InvalidEstimationConfigurationError(
            "Linear Interpolation requires a resolved Time Axis; the current Time Axis configuration is not "
            "usable yet."
        )
    seconds: list[float] = []
    for row_number in row_numbers:
        raw = configured.values_by_row_number.get(row_number)
        if raw is None:
            seconds.append(float("nan"))
            continue
        try:
            seconds.append(datetime.fromisoformat(raw).timestamp() if configured.family == FAMILY_ABSOLUTE else float(raw))
        except ValueError:
            seconds.append(float("nan"))
    return np.array(seconds, dtype=float)


def _resolve_fill_scope(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str,
    target_row_number: int | None, registry: PreparationSessionRegistry,
) -> tuple[PreparationSession, int | None, list[int], np.ndarray, list[int]]:
    """Shared resolution step for every single-cell/bulk estimate/fill
    preview+apply function below (task sections 11/13: authoritative
    backend scope, never a frontend-supplied coordinate list; re-run
    fresh on every call, including at apply time -- task section 12's
    own "never blindly apply to a stale coordinate list" requirement).

    Returns `(session, worksheet_index, row_numbers, values,
    target_rows)`. `row_numbers`/`values` are this column's own full
    active-region numeric series (`_build_column_series()`);
    `target_rows` is the set of row_numbers THIS action is actually
    scoped to -- every currently-eligible `(column_index, issue_code)`
    row for a bulk action (`target_row_number=None`), or only the
    eligible rows within the ONE contiguous gap containing
    `target_row_number` for a single-cell action (task section 5's own
    recommendation B: estimate the entire contiguous gap containing the
    clicked cell, never only that one cell in isolation).

    A column that is not currently Waveform (Not Assigned, Time Axis, or
    out-of-range) is never a special-cased error here -- exactly like
    `eligible_bulk_null_rows()` itself (reused below unchanged), it
    naturally reports zero eligible rows, since `waveform_value_missing`/
    `waveform_value_invalid` are only ever produced for Waveform-role
    columns in the first place -- this is what backend-enforces task
    section 3's Time-Axis guardrail structurally, with no separate
    check needed."""
    if issue_code not in _BULK_ISSUE_CODES:
        raise InvalidFillTargetError(
            f"issue_code must be one of {_BULK_ISSUE_CODES}; got {issue_code!r}. Time Axis issues are never "
            f"eligible for estimation/fill."
        )
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_column_bound(session, worksheet_index, column_index)
    eligible_rows = eligible_bulk_null_rows(
        session, worksheet_index=worksheet_index, column_index=column_index, issue_code=issue_code,
        workspace_id=workspace_id, source_id=source_id, registry=registry,
    )
    row_numbers, values = _build_column_series(session, worksheet_index=worksheet_index, column_index=column_index)
    if target_row_number is None:
        target_rows = list(eligible_rows)
    else:
        if target_row_number not in eligible_rows:
            raise InvalidFillTargetError(
                f"row_number {target_row_number} is not currently an unresolved {issue_code} cell in this column."
            )
        position_by_row = {rn: i for i, rn in enumerate(row_numbers)}
        gap = next((g for g in find_gaps(values) if g[0] <= position_by_row[target_row_number] <= g[1]), None)
        eligible_set = set(eligible_rows)
        target_rows = (
            [row_numbers[p] for p in range(gap[0], gap[1] + 1) if row_numbers[p] in eligible_set]
            if gap is not None else [target_row_number]
        )
    return session, worksheet_index, row_numbers, values, target_rows


def _expand_to_gap_rows(
    row_numbers: list[int], values: np.ndarray, seed_rows: list[int], writable_rows: set[int],
) -> list[int]:
    """Owner hardening pass (2026-09-10): a contiguous non-finite gap is
    a single mathematical unit REGARDLESS of whether its individual
    members are classified `waveform_value_missing` or `waveform_value_
    invalid` -- `_build_column_series()` already represents both (and an
    explicit-null cell) identically as NaN, so `find_gaps()` already sees
    ONE gap spanning e.g. blank/invalid/blank. For every row in
    `seed_rows` (the ORIGINALLY-requested, single-issue-type scope), find
    its own containing gap and include every row of that gap that is
    CURRENTLY a writable waveform cell (`writable_rows` -- the union of
    both issue types' own eligible sets, deliberately EXCLUDING explicit-
    null rows, which are never a write target regardless of gap
    membership). The result is a SUPERSET of `seed_rows` whenever a
    touched gap mixes both issue types; equal to it otherwise. A seed row
    with no containing gap (should not normally happen, since every seed
    is itself non-finite) falls back to just that one row, never an
    error.

    Order is `row_numbers`' own ascending order, deduplicated -- stable
    and deterministic regardless of `seed_rows`' own order."""
    if not seed_rows:
        return []
    position_by_row = {rn: i for i, rn in enumerate(row_numbers)}
    gaps = find_gaps(values)
    result_positions: set[int] = set()
    for seed in seed_rows:
        pos = position_by_row[seed]
        gap = next((g for g in gaps if g[0] <= pos <= g[1]), None)
        if gap is None:
            result_positions.add(pos)
            continue
        for p in range(gap[0], gap[1] + 1):
            if row_numbers[p] in writable_rows:
                result_positions.add(p)
    return [row_numbers[p] for p in sorted(result_positions)]


def _resolve_estimation_scope(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str,
    target_row_number: int | None, registry: PreparationSessionRegistry,
) -> tuple[PreparationSession, int | None, list[int], np.ndarray, list[int], list[int]]:
    """The estimate-specific counterpart of `_resolve_fill_scope()`
    (constant fill keeps using that one, unchanged -- task's own
    explicit "Constant Value... keep strictly scoped to the selected
    issue group/cells, because it is not a gap-based mathematical
    operation" requirement). Estimation, unlike constant fill, treats
    the full contiguous non-finite waveform gap as the mathematical
    unit -- a gap mixing `waveform_value_missing` and `waveform_value_
    invalid` members is never split by issue type.

    Returns `(session, worksheet_index, row_numbers, values,
    matching_rows, affected_rows)`:
    - `matching_rows` -- the ORIGINALLY-requested, single-issue-type
      scope (task's own "matching group cells: N"): exactly the one
      clicked cell for a single-cell request, or every currently-
      eligible `(column_index, issue_code)` row for a bulk request --
      mirrors `_resolve_fill_scope()`'s own `target_row_number`
      branching exactly.
    - `affected_rows` -- `matching_rows` expanded to the full contiguous
      gap(s) they belong to, unioned across BOTH issue types
      (`_expand_to_gap_rows()`) -- task's own "total cells that will be
      estimated: M". A superset of `matching_rows` whenever a touched
      gap mixes both issue types; equal to it otherwise."""
    if issue_code not in _BULK_ISSUE_CODES:
        raise InvalidFillTargetError(
            f"issue_code must be one of {_BULK_ISSUE_CODES}; got {issue_code!r}. Time Axis issues are never "
            f"eligible for estimation/fill."
        )
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_column_bound(session, worksheet_index, column_index)
    eligible_by_code = {
        code: eligible_bulk_null_rows(
            session, worksheet_index=worksheet_index, column_index=column_index, issue_code=code,
            workspace_id=workspace_id, source_id=source_id, registry=registry,
        )
        for code in _BULK_ISSUE_CODES
    }
    writable_rows = set(eligible_by_code[ISSUE_WAVEFORM_VALUE_MISSING]) | set(eligible_by_code[ISSUE_WAVEFORM_VALUE_INVALID])
    row_numbers, values = _build_column_series(session, worksheet_index=worksheet_index, column_index=column_index)
    if target_row_number is None:
        matching_rows = list(eligible_by_code[issue_code])
    else:
        if target_row_number not in eligible_by_code[issue_code]:
            raise InvalidFillTargetError(
                f"row_number {target_row_number} is not currently an unresolved {issue_code} cell in this column."
            )
        matching_rows = [target_row_number]
    affected_rows = _expand_to_gap_rows(row_numbers, values, matching_rows, writable_rows)
    return session, worksheet_index, row_numbers, values, matching_rows, affected_rows


@dataclass(slots=True)
class ConstantFillPreview:
    """The authoritative eligible-cell COUNT for a bulk constant-fill
    scope, computed WITHOUT any mutation -- mirrors `BulkNullPreview`
    exactly. Every currently-eligible cell would be filled regardless of
    WHAT constant is chosen, so `constant_value` is not needed for
    preview at all."""

    column_index: int
    issue_code: str
    eligible_count: int


@dataclass(slots=True)
class ConstantFillApplyResult:
    """Mirrors `BulkNullApplyResult` exactly -- `eligible_count` is
    re-evaluated fresh at apply time, never trusting an earlier preview
    call."""

    column_index: int
    issue_code: str
    eligible_count: int
    applied_count: int
    overlay: WorkingOverlaySummary


def preview_bulk_constant_fill(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str, registry: PreparationSessionRegistry,
) -> ConstantFillPreview:
    """Count-before-apply for `POST .../working/cells/bulk-constant-fill/apply`."""
    _session, _worksheet_index, _row_numbers, _values, target_rows = _resolve_fill_scope(
        workspace_id=workspace_id, source_id=source_id, column_index=column_index, issue_code=issue_code,
        target_row_number=None, registry=registry,
    )
    return ConstantFillPreview(column_index=column_index, issue_code=issue_code, eligible_count=len(target_rows))


def apply_bulk_constant_fill(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str, constant_value: float,
    registry: PreparationSessionRegistry,
) -> ConstantFillApplyResult:
    """Applies an explicit constant fill to EVERY currently eligible
    cell in this exact `(column_index, issue_code)` scope, as ONE
    grouped, single-Undo/Redo working-overlay operation
    (`bulk_set_cells_constant_fill()`). Valid cells, manually-fixed
    cells, explicit-null cells, and any non-Waveform column are never
    touched -- this function only ever writes the cells
    `eligible_bulk_null_rows()` itself currently reports. The original
    source data is never modified (task section 7's own confirmation
    wording)."""
    if constant_value is None or not math.isfinite(constant_value):
        raise InvalidEstimationConfigurationError("constant_value must be a finite number.")
    session, worksheet_index, _row_numbers, _values, target_rows = _resolve_fill_scope(
        workspace_id=workspace_id, source_id=source_id, column_index=column_index, issue_code=issue_code,
        target_row_number=None, registry=registry,
    )
    keys = [overlay_domain.cell_key(worksheet_index, rn, column_index) for rn in target_rows]
    applied_count = overlay_domain.bulk_set_cells_constant_fill(session.working_overlay, keys, str(constant_value))
    return ConstantFillApplyResult(
        column_index=column_index, issue_code=issue_code,
        eligible_count=len(target_rows), applied_count=applied_count,
        overlay=summarize_working_overlay(session, worksheet_index),
    )


@dataclass(slots=True)
class EstimationPreview:
    """Authoritative preview for a single-cell OR bulk estimation
    request, computed WITHOUT any mutation (task section 11's own
    required shape: "Matching unresolved cells / Eligible for X
    estimation / Will remain unresolved," extended by the owner
    hardening pass with the mixed-gap `affected_count` breakdown).

    `matching_count` (N) -- the ORIGINALLY-requested, single-issue-type
    scope: 1 for a single-cell request, or every currently-eligible
    `(column_index, issue_code)` row for a bulk request.
    `affected_count` (M) -- `matching_count`'s own rows expanded to the
    full contiguous non-finite gap(s) they belong to, unioned across
    BOTH `waveform_value_missing`/`waveform_value_invalid` (estimation
    treats a mixed gap as one mathematical unit, never split by issue
    type) -- equal to `matching_count` unless a touched gap mixes both
    issue types, in which case `M > N`. `eligible_count` is how many of
    the `affected_count` rows fall inside a gap `<= max_gap_value`
    samples under the requested method; `unresolved_count` is the rest
    -- an oversized gap that will remain unresolved even after apply,
    never partially filled."""

    column_index: int
    issue_code: str
    method: str
    matching_count: int
    affected_count: int
    eligible_count: int
    unresolved_count: int


@dataclass(slots=True)
class EstimationApplyResult:
    """Mirrors `EstimationPreview`, plus the actual `applied_count` --
    re-evaluated fresh at apply time (task section 12), never trusting
    an earlier preview call. `eligible_count` here is this SAME fresh
    apply-time count, always equal to `applied_count` (every cell the
    fresh scan reports eligible is, by construction, one this call
    actually writes)."""

    column_index: int
    issue_code: str
    method: str
    matching_count: int
    affected_count: int
    eligible_count: int
    applied_count: int
    unresolved_count: int
    overlay: WorkingOverlaySummary


def _compute_estimation(
    *, row_numbers: list[int], values: np.ndarray, method: str, max_gap_value: int, local_mean_radius: int | None,
    workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> np.ndarray:
    """Runs `app.domain.missing_data_estimation.apply_estimation()` over
    the WHOLE column series in one call (cheap, O(active rows)) -- max-
    gap enforcement happens INSIDE that engine already (task section 9:
    an oversized gap is left NaN, never partially filled), so this
    function adds only the one extra piece that engine does not itself
    own: real Time-Axis-aware seconds for Linear
    (`_build_column_time_seconds()`); every other method ignores `time`
    entirely, matching the engine's own per-method contract."""
    time_seconds = (
        _build_column_time_seconds(
            workspace_id=workspace_id, source_id=source_id, registry=registry, row_numbers=row_numbers,
        )
        if method == ESTIMATION_METHOD_LINEAR else np.zeros_like(values)
    )
    return apply_estimation(
        time=time_seconds, values=values, estimation_method=method,
        max_gap_value=max_gap_value, local_mean_radius=local_mean_radius,
    )


def preview_estimate(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str, method: str,
    max_gap_value: int, max_gap_unit: str, local_mean_radius: int | None, target_row_number: int | None,
    registry: PreparationSessionRegistry,
) -> EstimationPreview:
    """Count-before-apply for both the single-cell (`target_row_number`
    set) and bulk (`target_row_number=None`) estimate endpoints. Uses
    `_resolve_estimation_scope()` (never `_resolve_fill_scope()`, which
    stays constant-fill-only) so a mixed missing+invalid gap is always
    reported and estimated as one complete unit -- `matching_count`
    (N, the originally-requested single-issue-type group) and
    `affected_count` (M, the gap-expanded true scope) are reported
    separately, transparently, whenever they differ."""
    _validate_estimation_method(
        method, max_gap_value=max_gap_value, max_gap_unit=max_gap_unit, local_mean_radius=local_mean_radius,
    )
    _session, _worksheet_index, row_numbers, values, matching_rows, affected_rows = _resolve_estimation_scope(
        workspace_id=workspace_id, source_id=source_id, column_index=column_index, issue_code=issue_code,
        target_row_number=target_row_number, registry=registry,
    )
    estimated = _compute_estimation(
        row_numbers=row_numbers, values=values, method=method, max_gap_value=max_gap_value,
        local_mean_radius=local_mean_radius, workspace_id=workspace_id, source_id=source_id, registry=registry,
    )
    position_by_row = {rn: i for i, rn in enumerate(row_numbers)}
    eligible_count = sum(1 for rn in affected_rows if math.isfinite(estimated[position_by_row[rn]]))
    return EstimationPreview(
        column_index=column_index, issue_code=issue_code, method=method,
        matching_count=len(matching_rows), affected_count=len(affected_rows), eligible_count=eligible_count,
        unresolved_count=len(affected_rows) - eligible_count,
    )


def apply_estimate(
    *, workspace_id: str, source_id: str, column_index: int, issue_code: str, method: str,
    max_gap_value: int, max_gap_unit: str, local_mean_radius: int | None, target_row_number: int | None,
    registry: PreparationSessionRegistry,
) -> EstimationApplyResult:
    """Applies estimation to every currently-eligible cell in scope, as
    ONE grouped, single-Undo/Redo working-overlay operation
    (`bulk_set_cells_estimated()`) -- used identically for a single-cell
    gap estimate (task section 22: "one user action -> one Undo") and a
    whole-column bulk estimate; `bulk_set_cells_estimated()` already
    groups any number of entries, including exactly one, into a single
    `WorkingOperation`, so no separate single-cell code path is needed.
    Scope (both `matching_rows` and its gap-expanded `affected_rows`) is
    recomputed fresh here (task section 12) -- never trusting an earlier
    preview call. A mixed missing+invalid gap is always resolved as one
    complete unit -- never a partial hole left merely because one member
    has a different classification than the one that launched this
    action."""
    _validate_estimation_method(
        method, max_gap_value=max_gap_value, max_gap_unit=max_gap_unit, local_mean_radius=local_mean_radius,
    )
    session, worksheet_index, row_numbers, values, matching_rows, affected_rows = _resolve_estimation_scope(
        workspace_id=workspace_id, source_id=source_id, column_index=column_index, issue_code=issue_code,
        target_row_number=target_row_number, registry=registry,
    )
    estimated = _compute_estimation(
        row_numbers=row_numbers, values=values, method=method, max_gap_value=max_gap_value,
        local_mean_radius=local_mean_radius, workspace_id=workspace_id, source_id=source_id, registry=registry,
    )
    position_by_row = {rn: i for i, rn in enumerate(row_numbers)}
    entries = [
        (overlay_domain.cell_key(worksheet_index, rn, column_index), str(float(estimated[position_by_row[rn]])))
        for rn in affected_rows if math.isfinite(estimated[position_by_row[rn]])
    ]
    applied_count = overlay_domain.bulk_set_cells_estimated(
        session.working_overlay, entries, estimation_method=method, max_gap_value=max_gap_value,
        max_gap_unit=max_gap_unit, local_mean_radius=local_mean_radius,
    )
    matching_count = len(matching_rows)
    affected_count = len(affected_rows)
    return EstimationApplyResult(
        column_index=column_index, issue_code=issue_code, method=method,
        matching_count=matching_count, affected_count=affected_count,
        eligible_count=applied_count, applied_count=applied_count,
        unresolved_count=affected_count - applied_count,
        overlay=summarize_working_overlay(session, worksheet_index),
    )
