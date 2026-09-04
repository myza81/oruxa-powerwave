"""Wire shape for the Canonical Table View endpoint (DEC-079).

JSON-first, matching every other Phase 2 wire-shape decision in this
repository (see app.schemas.waveform's own docstring) -- no binary
format.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.table_service import TableRowsResult


class TableColumnOut(BaseModel):
    """One table column's static metadata. `kind` is `"time"` |
    `"analog"` | `"digital"`. `unit`/`engineering_type`/
    `engineering_quantity` are `None` for the time column and for every
    digital column (digital channels carry no such metadata today --
    see `app.domain.channels.DigitalChannel`)."""

    key: str
    kind: str
    label: str
    unit: str | None = None
    engineering_type: str | None = None
    engineering_quantity: str | None = None


class SourceTableOut(BaseModel):
    """One bounded page of one source's own canonical rows -- exact
    values, never plot-reduced (see app.services.table_service's own
    module docstring). `rows` is row-major: each entry is a list of cell
    values aligned 1:1 with `columns` (including the leading time
    column). A missing/non-finite canonical value serializes as JSON
    `null`, never `0`."""

    source_id: str
    offset: int
    limit: int
    returned_row_count: int
    total_row_count: int
    columns: list[TableColumnOut]
    rows: list[list[float | int | str | None]]

    @classmethod
    def from_result(cls, result: TableRowsResult) -> "SourceTableOut":
        return cls(
            source_id=result.source_id,
            offset=result.offset,
            limit=result.limit,
            returned_row_count=result.returned_row_count,
            total_row_count=result.total_row_count,
            columns=[
                TableColumnOut(
                    key=col.key, kind=col.kind, label=col.label,
                    unit=col.unit, engineering_type=col.engineering_type, engineering_quantity=col.engineering_quantity,
                )
                for col in result.columns
            ],
            rows=result.rows,
        )
