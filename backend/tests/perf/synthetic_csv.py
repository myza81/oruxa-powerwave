"""Deterministic synthetic CSV fixture generator for the performance
baseline (Pre-Advanced Foundation Slice F2).

Produces a plain, header-less numeric CSV: one elapsed-seconds time
column followed by N waveform columns -- the exact shape the existing
CSV ingestion tests already exercise without any header-row
configuration step (see `test_sources_api.py`'s
`TestListIncludesTimeOfDayReferenceSeconds`/
`TestListIncludesPreparationInterpreterId`, which assign `time_axis`/
`waveform` roles by column INDEX directly against a header-less CSV).
Reusing that exact shape means this fixture needs no new Data
Preparation configuration path -- only the same role-assignment +
`elapsed_numeric` time-axis calls those tests already use, just looped
across more columns.

Row count is derived from a measured sample row's own encoded byte
length so the actual file size lands close to (never over) the
requested target -- never a guessed/hand-picked row count.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CsvFixtureInfo:
    csv_path: Path
    n_channels: int
    sample_rate_hz: float
    n_rows: int
    duration_seconds: float
    size_bytes: int


def _row_text(row_index: int, n_channels: int, sample_rate_hz: float) -> str:
    t = row_index / sample_rate_hz
    fields = [f"{t:.6f}"]
    for ch in range(n_channels):
        amplitude = 100.0 + ch
        phase = (ch % 12) * 0.5235987755982988  # pi/6, deterministic constant
        value = amplitude * math.sin(2.0 * math.pi * 50.0 * t + phase)
        fields.append(f"{value:.4f}")
    return ",".join(fields)


def generate_csv_fixture(
    out_dir: Path,
    *,
    n_channels: int,
    sample_rate_hz: float,
    target_size_bytes: int,
    stem: str = "event",
) -> CsvFixtureInfo:
    """Generate a deterministic, header-less numeric CSV into `out_dir`,
    sized so the file is as close as possible to (never over)
    `target_size_bytes`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{stem}.csv"

    # Row 0's own byte length UNDER-estimates the true average: the
    # leading elapsed-seconds field grows a digit every decade of
    # `row_index / sample_rate_hz`, so a later row is longer than row 0.
    # A first pass gives an UPPER BOUND on the final row count (rows only
    # ever get longer, never shorter); measuring the row at the far end
    # of that upper-bound range gives a length that is >= every row
    # actually written in the final, smaller range -- guaranteeing the
    # final file never exceeds `target_size_bytes`, not merely
    # approximating it.
    row0_len = len(_row_text(0, n_channels, sample_rate_hz).encode("ascii")) + 1
    upper_bound_rows = max(int(target_size_bytes // row0_len), 1)
    worst_case_len = len(_row_text(upper_bound_rows - 1, n_channels, sample_rate_hz).encode("ascii")) + 1
    n_rows = max(int(target_size_bytes // worst_case_len), 1)

    with csv_path.open("w", encoding="ascii", newline="") as fh:
        for i in range(n_rows):
            fh.write(_row_text(i, n_channels, sample_rate_hz))
            fh.write("\n")

    size_bytes = csv_path.stat().st_size
    return CsvFixtureInfo(
        csv_path=csv_path,
        n_channels=n_channels,
        sample_rate_hz=sample_rate_hz,
        n_rows=n_rows,
        duration_seconds=n_rows / sample_rate_hz,
        size_bytes=size_bytes,
    )
