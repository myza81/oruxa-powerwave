"""Wire shape for the Phase 2A waveform range endpoint.

JSON-first per docs/project-memory/MIGRATION_PLAN.md's Phase 2 design §5/§20
("start with JSON, revisit binary only if measured necessary") -- no
Arrow/Protobuf/custom binary format introduced this phase.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.waveform_service import WaveformRangeResult


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
    values: list[float]
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
            time=result.time.tolist(),
            values=result.values.tolist(),
            per_unit_status=result.per_unit_status,
        )
