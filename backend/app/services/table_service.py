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

from app.domain.source import ActiveSource
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


def fetch_table_rows(active: ActiveSource, *, offset: int, limit: int) -> TableRowsResult:
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
    """
    df = active.record.waveform_data
    total = len(df)
    page = df.iloc[offset : offset + limit] if offset < total else df.iloc[0:0]

    columns = build_table_columns(active)
    time_is_absolute = active.metadata.timing_reference == "absolute" and active.metadata.start_time is not None
    start_time = active.metadata.start_time

    column_arrays = {col.key: page[col.key].to_numpy() for col in columns}
    row_count = len(page)
    rows: list[list[object]] = []
    for i in range(row_count):
        elapsed = float(column_arrays["time"][i])
        if time_is_absolute:
            time_cell: object = format_absolute_iso(start_time + timedelta(seconds=elapsed))
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
    )
