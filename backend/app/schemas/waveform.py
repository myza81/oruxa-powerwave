"""Wire shape for the Phase 2A waveform range endpoint.

JSON-first per docs/project-memory/MIGRATION_PLAN.md's Phase 2 design §5/§20
("start with JSON, revisit binary only if measured necessary") -- no
Arrow/Protobuf/custom binary format introduced this phase.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from app.services.waveform_service import WaveformRangeResult


def _sanitize_float_array(values: np.ndarray) -> list[float | None]:
    """DEC-084 (Slice 3): `NaN` -> `null`, everything else unchanged --
    the SAME sanitization rule `app.schemas.calculated_channel.
    _sanitize_float_list` independently established for calculated
    channels (Phase 5B, DEC-048's own RMS warm-up region), applied here
    for a source channel's own `values` ONLY (an explicit-null CSV/Excel
    cell converts to `NaN`, see `app.services.preparation_conversion_
    service`). FastAPI's default `JSONResponse` calls `json.dumps(...,
    allow_nan=False)`, so an unsanitized `NaN` reaching this response
    body would 500 the request rather than degrade to `null`. A second,
    source-channel-scoped copy of the identical one-line rule rather
    than a shared import, since the calculated-channel schema module is
    calculated-channel-specific and this one is not.

    DEC-084 approves an explicit-null GAP for a Waveform/data cell only
    -- never for the Time Axis (see `_require_finite_time_array` below,
    used for `time` instead of this function)."""
    return [float(v) if np.isfinite(v) else None for v in values]


def _require_finite_time_array(values: np.ndarray) -> list[float]:
    """DEC-084 (Slice 3 tightening): a Time Axis coordinate is NEVER an
    approved gap -- DEC-084's explicit-null resolution exists only for
    Waveform/data cells, and Slice 1's own readiness gate keeps an
    explicit-null Time Axis cell permanently BLOCKING (see
    `app.services.readiness_service`), so a converted, registered
    `DisturbanceRecord`'s own `time` column is already guaranteed finite
    by `app.domain.disturbance_record.DisturbanceRecord.validate()`
    before it can ever reach this boundary at all.

    This function therefore never normalizes a non-finite value into
    `null` the way `_sanitize_float_array` does for `values` -- doing so
    would make a genuinely broken time axis silently indistinguishable
    from an ordinary, approved data gap to every caller (frontend
    plotting, cursor lookup, exports). If a non-finite time somehow still
    reaches here, that is a real invariant violation, not routine data --
    it fails LOUDLY (raises) rather than degrading quietly."""
    out: list[float] = []
    for v in values:
        if not np.isfinite(v):
            raise ValueError(
                f"Non-finite Time Axis value ({v!r}) reached the waveform response boundary -- "
                "DEC-084 approves an explicit-null gap for Waveform/data cells only, never the "
                "Time Axis; this indicates DisturbanceRecord.validate()'s own finite-time "
                "invariant was violated upstream."
            )
        out.append(float(v))
    return out


class WaveformRangeOut(BaseModel):
    """One channel's waveform data for a requested time range.

    `representation` is always either `"full_resolution"` (the exact raw
    samples in `[start_time, end_time]`, unmodified) or
    `"min_max_envelope"` (a peak-preserving display representation -- see
    app.domain.waveform_reduction -- never authoritative engineering data,
    see DEC-019). `returned_point_count` is the actual length of `time`/
    `values` -- for `"min_max_envelope"` this is a budget outcome, not
    guaranteed to equal any requested `point_budget` (see
    app.domain.waveform_reduction.build_min_max_envelope's docstring).

    `values` is `list[float | None]` (DEC-084, Slice 3 -- widened from
    `list[float]`): a genuinely non-finite sample (an explicit-null
    Waveform/data gap, see `_sanitize_float_array`) serializes as `null`,
    never a raw `NaN`, never `0`.

    `time` stays `list[float]` -- NEVER nullable (DEC-084, Slice 3
    tightening: gaps are approved for Waveform/data cells only, never
    the Time Axis). `time` is always finite by construction
    (`app.domain.disturbance_record.DisturbanceRecord.validate()`
    enforces it upstream) -- see `_require_finite_time_array`, which
    raises rather than silently normalizing a violation of that
    invariant into `null`.
    """

    source_id: str
    channel_name: str
    unit: str
    start_time: float
    end_time: float
    original_sample_count: int
    returned_point_count: int
    representation: str
    time: list[float]
    values: list[float | None]
    # Phase 5C (DEC-049): `None` when unit_mode="engineering" (per-unit
    # mode not requested); otherwise "not_applicable"/"configured"/
    # "base_required" -- `unit`/`values` above are already converted
    # when this is "configured".
    per_unit_status: str | None = None

    @classmethod
    def from_result(cls, result: WaveformRangeResult) -> "WaveformRangeOut":
        return cls(
            source_id=result.source_id,
            channel_name=result.channel_name,
            unit=result.unit,
            start_time=result.start_time,
            end_time=result.end_time,
            original_sample_count=result.original_sample_count,
            returned_point_count=len(result.time),
            representation=result.representation,
            time=_require_finite_time_array(result.time),
            values=_sanitize_float_array(result.values),
            per_unit_status=result.per_unit_status,
        )
