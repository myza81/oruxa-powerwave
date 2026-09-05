"""Canonical Table View (DEC-079): a read-only, paginated, exact-row
inspection surface over one recording's own authoritative
`DisturbanceRecord.waveform_data` -- never the Data Preparation
Workspace's `PreparationSession`/`WorkingOverlay`/raw grid (that state
is discarded on successful conversion, see
`app.services.preparation_conversion_service`'s own module docstring),
and never the plotting endpoint's own point-budget/min-max-envelope
reduction (`app.services.waveform_service.extract_waveform_range`) --
that reduction exists purely for chart display performance and is
explicitly NOT authoritative engineering data (DEC-019).

Format-independent by construction: this module reads only
`ActiveSource.metadata`/`ActiveSource.record` -- the exact same object
shape a COMTRADE upload and a converted CSV/Excel source both produce
(see `app.api.v1.sources.upload_comtrade_source` and
`app.services.preparation_conversion_service.convert_preparation_source`,
which both call `workspace_registry.add(ActiveSource(...))`). There is
no `if provider_type == ...` branch anywhere in this module, and there
must never be one.

One shared `time` column, one column per analog/digital channel, ALL in
the SAME `pandas.DataFrame` (`DisturbanceRecord.waveform_data`) -- this
is already true for every existing provider today, including multi-rate
COMTRADE (`app.providers.comtrade` already unifies every rate segment
into one common time axis at import time; there is no separate
per-segment array this module needs to reconcile). A table "row" is
therefore simply `waveform_data.iloc[i]` -- no per-channel alignment,
no join, no resampling.

Pagination reuses the Data Preparation Workspace's own established
default/max page size (200/1000, `app.services.preparation_preview_
service.PREVIEW_DEFAULT_LIMIT`/`PREVIEW_MAX_LIMIT`) as a documented
convention match, not an import -- this module has no dependency on
that pre-conversion-only service.

Time formatting reuses the EXACT SAME canonical representation
DEC-074's cleaned export already established
(`app.services.time_axis_normalization.format_absolute_iso`/
`format_relative_seconds`) -- never a third, competing time-formatting
implementation. A source's own `timing_reference`/`start_time`
(`ActiveSource.metadata`, already computed once at import time) decide
which representation applies; workspace-level synchronization/
alignment offsets (t0, manual offsets, common-time-group alignment --
all purely frontend/display-only state, see
`app.services.synchronization_service`) are never read or applied here
-- Table View always shows the recording's own canonical source time,
per the owner's own explicit "no silent transformation" requirement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np

from app.domain.source import ActiveSource
from app.services.errors import InvalidTimeRangeError
from app.services.time_axis_normalization import format_absolute_iso, format_relative_seconds

#: Matches app.services.preparation_preview_service.PREVIEW_DEFAULT_LIMIT/
#: PREVIEW_MAX_LIMIT exactly -- a deliberate convention match (task's own
#: "reuse the Data Preparation value if appropriate"), not a shared import;
#: this module has no dependency on the pre-conversion-only preview service.
TABLE_DEFAULT_LIMIT = 200
TABLE_MAX_LIMIT = 1000

COLUMN_KIND_TIME = "time"
COLUMN_KIND_ANALOG = "analog"
COLUMN_KIND_DIGITAL = "digital"


@dataclass(slots=True)
class TableColumn:
    """One table column's own static metadata -- page-independent,
    computed once per request from `ActiveSource.metadata` alone (never
    from a page of rows)."""

    key: str
    kind: str  # COLUMN_KIND_TIME | COLUMN_KIND_ANALOG | COLUMN_KIND_DIGITAL
    label: str
    unit: str | None = None
    engineering_type: str | None = None
    engineering_quantity: str | None = None


@dataclass(slots=True)
class TableRowsResult:
    source_id: str
    offset: int
    limit: int
    returned_row_count: int
    total_row_count: int
    columns: list[TableColumn] = field(default_factory=list)
    # Row-major: one list of cell values per row, aligned 1:1 with
    # `columns` (including the leading time column). A missing/non-finite
    # canonical value is `None` (JSON `null`) -- never `0`, never a
    # fabricated/interpolated value.
    rows: list[list[object]] = field(default_factory=list)
    # Split View enhancement (owner-approved): the SAME raw elapsed-
    # seconds value (this source's own native time axis) already
    # computed to build each row's own formatted `time` cell above,
    # additionally exposed here verbatim -- never re-derived, never a
    # second computation. Aligned 1:1 with `rows`. Purely additive: the
    # Canonical Table View's own existing frontend consumer ignores this
    # extra field entirely. Exists because the formatted `time` cell
    # (a fixed-precision relative string, or a locale-formatted absolute
    # ISO string) cannot be reliably parsed back into an exact native
    # elapsed-seconds value -- Split View needs that exact value, both
    # to match a row against the existing waveform cursor's own
    # resolved sample time (`extract_cursor_values`'s own nearest-
    # sample native time) and to convert a clicked row back into a
    # workspace-time cursor position.
    row_native_times: list[float] = field(default_factory=list)


def _time_column_label(active: ActiveSource) -> str:
    """Same "absolute vs elapsed" decision `SourceSummaryOut`/`TimebaseOut`
    already expose (`timing_reference == "absolute"` AND a real
    `start_time` -- both required, matching `TimingInformation`'s own
    "start_time is None exactly when genuinely unknown" contract) --
    never re-derived differently here."""
    if active.metadata.timing_reference == "absolute" and active.metadata.start_time is not None:
        return "Time"
    return "Time (s)"


def build_table_columns(active: ActiveSource) -> list[TableColumn]:
    """The full, page-independent column list for one source -- canonical
    channel order (task section 20: "column order should follow
    canonical channel order," never alphabetical/re-sorted), Time always
    first. Every analog channel is included regardless of whether it is
    currently plotted in Waveform View (task's own "what canonical data
    exists," not "what is visible right now" distinction) -- and
    regardless of engineering_quantity, including "Undefined" and Angle
    quantities, which are included as ordinary data columns (DEC-078's
    own secondary-axis behavior is a Waveform-plotting-only concern,
    irrelevant here)."""
    columns = [TableColumn(key="time", kind=COLUMN_KIND_TIME, label=_time_column_label(active))]
    for ch in active.metadata.analog_channels:
        columns.append(
            TableColumn(
                key=ch.name, kind=COLUMN_KIND_ANALOG, label=ch.name,
                unit=ch.unit, engineering_type=ch.engineering_type, engineering_quantity=ch.engineering_quantity,
            )
        )
    for ch in active.metadata.digital_channels:
        columns.append(TableColumn(key=ch.name, kind=COLUMN_KIND_DIGITAL, label=ch.name))
    return columns


def _safe_float(value: object) -> float | None:
    fval = float(value)  # type: ignore[arg-type]
    return None if math.isnan(fval) or math.isinf(fval) else fval


def _safe_int(value: object) -> int | None:
    fval = float(value)  # type: ignore[arg-type]
    return None if math.isnan(fval) or math.isinf(fval) else int(fval)


def fetch_table_rows(
    active: ActiveSource, *, offset: int, limit: int,
    start_time: float | None = None, end_time: float | None = None,
    center_time: float | None = None,
) -> TableRowsResult:
    """Slice EXACTLY `waveform_data.iloc[offset:offset+limit]` -- never
    the plotting endpoint's own point-budget/min-max-envelope reduction
    (task section 11), never a full-record copy (task section 42):
    `.iloc[...]` on a pandas DataFrame is a bounded view over the
    underlying arrays, not a deep copy of the whole record, and this
    function converts only the requested page's own cells to Python
    values. `offset` beyond the last row is not an error -- it simply
    yields an empty page (`returned_row_count == 0`), the same
    "out-of-range offset silently yields empty, never an unrelated page"
    convention `app.services.preparation_preview_service` already
    established, never a second/different rule invented here.

    Canonical time formatting matches DEC-074's cleaned export exactly
    (`format_absolute_iso`/`format_relative_seconds`) -- workspace
    synchronization/alignment offsets are never read or applied; the
    value shown is always `waveform_data["time"]` itself (elapsed
    seconds relative to the record's own native origin), optionally
    recombined with the source's own `start_time` for absolute display,
    never a t0-shifted or otherwise workspace-adjusted value.

    Split View enhancement (owner-approved): `start_time`/`end_time` are
    an OPTIONAL, additive time-window filter over this SAME source-
    native elapsed-seconds axis -- the identical convention
    `app.services.waveform_service.extract_waveform_range`/
    `extract_cursor_values` already use for their own `start_time`/
    `end_time` parameters, never a third, competing time convention.
    When given, `offset`/`limit` apply WITHIN the time-filtered window
    (offset 0 is the window's own first matching row, never the
    source's row 0), so ordinary pagination math still works unchanged
    for a narrowed window; `total_row_count` becomes the window's own
    row count. Omitting both leaves this function's own pre-existing
    whole-source-offset behavior byte-for-byte unchanged (Canonical
    Table View, DEC-079, never touches these parameters). Raises
    `InvalidTimeRangeError` for `start_time > end_time`, mirroring
    `extract_waveform_range`'s own validation exactly.

    Split View cursor-correctness fix (owner-approved): `center_time`
    is a SECOND, independent, OPTIONAL way to choose `offset` -- when
    given, the caller's own `offset` argument is ignored and REPLACED
    with the offset that puts the row nearest `center_time` (by exact
    elapsed-seconds distance, never row-number/index guessing) as close
    to the middle of the returned page as the window's own edges allow.
    Exists so a bounded page can always be repositioned to genuinely
    CONTAIN whichever sample the waveform cursor currently points to,
    without ever fetching/rendering the entire (possibly huge) visible
    range just to answer "where is the cursor" -- see
    `app.api.v1.sources.get_source_table`'s own docstring for the full
    Split View rationale. Still fully backward compatible: omitted by
    every existing caller (Canonical Table View, and Split View's own
    non-cursor fetches), and has zero effect when `total == 0`.
    """
    if start_time is not None and end_time is not None and start_time > end_time:
        raise InvalidTimeRangeError(
            f"start_time ({start_time}) must not be greater than end_time ({end_time})."
        )

    df = active.record.waveform_data
    window_start_row = 0
    window_end_row = len(df)
    time_array = None
    if start_time is not None or end_time is not None or center_time is not None:
        time_array = df["time"].to_numpy()
    if start_time is not None or end_time is not None:
        if start_time is not None:
            window_start_row = int(np.searchsorted(time_array, start_time, side="left"))
        if end_time is not None:
            window_end_row = int(np.searchsorted(time_array, end_time, side="right"))
        window_end_row = max(window_start_row, window_end_row)

    total = window_end_row - window_start_row

    if center_time is not None and total > 0:
        # Nearest-by-VALUE, never nearest-by-index: searchsorted only
        # gives an insertion point (the first row >= center_time), which
        # is frequently NOT the closer of its two neighbors, especially
        # under irregular sampling (task's own explicit "different
        # sample intervals" scenario) -- both neighbors are compared by
        # actual elapsed-seconds distance and the closer one wins.
        windowed = time_array[window_start_row:window_end_row]
        insertion = int(np.searchsorted(windowed, center_time, side="left"))
        candidates = [i for i in (insertion - 1, insertion) if 0 <= i < len(windowed)]
        nearest_local = min(candidates, key=lambda i: abs(float(windowed[i]) - center_time))
        # Center the returned PAGE on the nearest row, clamped so the
        # page never runs past either edge of the window -- the same
        # "never fetch outside the intended visible range" guarantee
        # start_time/end_time already provide.
        offset = max(0, min(nearest_local - limit // 2, max(0, total - limit)))
    page_start = window_start_row + offset
    page_stop = min(page_start + limit, window_end_row)
    page = df.iloc[page_start:page_stop] if offset < total else df.iloc[0:0]

    columns = build_table_columns(active)
    time_is_absolute = active.metadata.timing_reference == "absolute" and active.metadata.start_time is not None
    # Renamed from the parameter's own `start_time` (this source's
    # absolute wall-clock ORIGIN, unrelated to the caller's optional
    # time-WINDOW filter above) to avoid shadowing it -- purely an
    # internal disambiguation, never part of this function's signature.
    record_start_time = active.metadata.start_time

    column_arrays = {col.key: page[col.key].to_numpy() for col in columns}
    row_count = len(page)
    rows: list[list[object]] = []
    row_native_times: list[float] = []
    for i in range(row_count):
        elapsed = float(column_arrays["time"][i])
        row_native_times.append(elapsed)
        if time_is_absolute:
            time_cell: object = format_absolute_iso(record_start_time + timedelta(seconds=elapsed))
        else:
            time_cell = format_relative_seconds(elapsed)
        row: list[object] = [time_cell]
        for col in columns[1:]:
            raw = column_arrays[col.key][i]
            row.append(_safe_int(raw) if col.kind == COLUMN_KIND_DIGITAL else _safe_float(raw))
        rows.append(row)

    return TableRowsResult(
        source_id=active.metadata.source_id,
        offset=offset,
        limit=limit,
        returned_row_count=row_count,
        total_row_count=total,
        columns=columns,
        rows=rows,
        row_native_times=row_native_times,
    )
