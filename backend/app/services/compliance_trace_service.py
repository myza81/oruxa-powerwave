"""Compliance -- resolved measurement traces for the Comparison Chart
(DEC-169; see docs/project-memory/COMPLIANCE_CAPABILITY.md).

> Reference defines. Measurement satisfies. Comparison visualizes the
> resolved measurement against the Reference.

This is the integration point between the Reference-driven readiness
(`compliance_readiness_service`) and the Comparison Chart. For the selected
Measurement Group it returns the plottable traces of every active Reference
whose status is `ready`:

- `Each Phase` -> one trace per required voltage (VAB, VBC, VCA / their R/Y/B
  equivalents -- the frontend spells them in the group's own convention);
- `Single` -> only the named voltage;
- `Minimum` / `Maximum` -> ONE trace, the sample-by-sample min / max across
  the required voltages (Compliance-only assessment reduction, deliberately
  not a Calculated Channel; refused unless the members are proven to share
  one time base -- no resampling).

Nothing is computed here that readiness did not already resolve. The data are
the shared arrays behind the readiness members (a source channel that is
already RMS, or an ordinary Calculated Channel), put in the Reference's unit
by `compliance_series` (the same per-unit resolvers Waveform uses; V <-> kV
scaling only). No RMS, line-to-line or per-unit logic lives in this module,
and no private Compliance series is stored.

Traces are de-duplicated by measurement product (kind + members + shared
channels + unit): two References that require the identical
`Line-Line RMS / Each Phase / pu` product share ONE set of traces, each trace
listing every layer it serves.

**Event time.** `x = source_time + alignment_offset - t0`, the workspace's own
formula (`app.services.synchronization_service`: the source's effective Time
Group placement and that group's t0). When no t0 is set, `x` is the source's
time with the placement only -- exactly the Waveform behaviour -- and the
response says `aligned = false` so the UI can say so.

**Display size.** The shared peak-preserving reduction (`_clip_and_reduce`,
the Waveform pipeline) bounds every trace; arrays are only read, never
copied beyond the one converted/reduced pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.domain.compliance_requirement import READINESS_READY
from app.services.compliance_readiness_service import ReadinessResult, evaluate_readiness
from app.services.compliance_series import Registries, load_series
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import get_source_alignment, get_t0
from app.services.waveform_service import DEFAULT_POINT_BUDGET, _clip_and_reduce

TRACE_KIND_MEMBER = "member"
TRACE_KIND_MINIMUM = "minimum"
TRACE_KIND_MAXIMUM = "maximum"


@dataclass(slots=True)
class MeasurementTrace:
    id: str
    kind: str
    members: tuple[str, ...]
    unit: str
    layer_ids: list[str]
    x: list[float]
    y: list[float]
    representation: str
    source_id: str


@dataclass(slots=True)
class EventAlignmentInfo:
    time_group_id: str | None
    t0_workspace_time: float | None
    aligned: bool


@dataclass(slots=True)
class SkippedReference:
    layer_id: str
    profile_name: str
    reason: str


@dataclass(slots=True)
class TraceResult:
    measurement_group_id: str
    traces: list[MeasurementTrace] = field(default_factory=list)
    skipped: list[SkippedReference] = field(default_factory=list)
    event: EventAlignmentInfo = field(default_factory=lambda: EventAlignmentInfo(None, None, False))
    readiness_status: str = "no_reference"


def _trace_id(kind: str, members: tuple[str, ...], unit: str, refs: tuple[ChannelRef, ...]) -> str:
    parts = [f"{r.kind}:{r.source_id or ''}:{r.channel_name or ''}:{r.calculated_channel_id or ''}" for r in refs]
    return f"{kind}|{','.join(members)}|{unit}|{'+'.join(parts)}"


def build_measurement_traces(
    *,
    workspace_id: str,
    measurement_group_id: str,
    readiness: ReadinessResult,
    registries: Registries,
    sync_registry: SynchronizationRegistry,
) -> TraceResult:
    """Traces for every READY reference of an already-evaluated readiness."""
    result = TraceResult(measurement_group_id=measurement_group_id, readiness_status=readiness.status)
    cache: dict[tuple, tuple] = {}
    by_id: dict[str, MeasurementTrace] = {}
    shifts: dict[str, tuple[float, float | None, str]] = {}

    def event_shift(source_id: str) -> tuple[float, float | None, str]:
        if source_id not in shifts:
            alignment = get_source_alignment(
                workspace_id=workspace_id, source_id=source_id, registry=sync_registry,
                source_registry=registries.source,
            )
            t0 = get_t0(
                workspace_id=workspace_id, source_id=source_id, registry=sync_registry,
                source_registry=registries.source,
            )
            shifts[source_id] = (alignment.effective_alignment_offset_s, t0.t0_workspace_time, t0.time_group_id)
        return shifts[source_id]

    def series_for(ref: ChannelRef, unit: str):
        key = (ref, unit)
        if key not in cache:
            cache[key] = load_series(ref, unit, workspace_id=workspace_id, reg=registries)
        return cache[key]

    for reference in readiness.references:
        if reference.status != READINESS_READY:
            continue
        requirement = reference.requirement
        unit = requirement.unit
        refs = tuple(m.channel_ref for m in reference.members)
        members = tuple(m.member for m in reference.members)
        loaded = [series_for(ref, unit) for ref in refs]
        failed = next((problem for series, problem in loaded if series is None), None)
        if failed is not None:
            result.skipped.append(SkippedReference(reference.layer_id, reference.profile_name, failed))
            continue
        series_list = [series for series, _ in loaded]

        treatment = requirement.phase_treatment
        if treatment in ("minimum", "maximum") and len(series_list) > 1:
            base = series_list[0]
            if any(len(s.time) != len(base.time) or not np.array_equal(s.time, base.time) for s in series_list[1:]):
                result.skipped.append(SkippedReference(
                    reference.layer_id, reference.profile_name,
                    f"The required voltages do not share one time base, so the {treatment} cannot be formed.",
                ))
                continue
            stack = np.vstack([s.values for s in series_list])
            values = stack.min(axis=0) if treatment == "minimum" else stack.max(axis=0)
            products = [(
                TRACE_KIND_MINIMUM if treatment == "minimum" else TRACE_KIND_MAXIMUM, members, refs, base.time, values,
                base.source_id,
            )]
        else:
            products = [
                (TRACE_KIND_MEMBER, (member,), (ref,), series.time, series.values, series.source_id)
                for member, ref, series in zip(members, refs, series_list)
            ]

        for kind, product_members, product_refs, time, values, source_id in products:
            trace_id = _trace_id(kind, product_members, unit, product_refs)
            existing = by_id.get(trace_id)
            if existing is not None:
                if reference.layer_id not in existing.layer_ids:
                    existing.layer_ids.append(reference.layer_id)
                continue
            offset, t0, group_id = event_shift(source_id)
            event_time = np.asarray(time, dtype=float) + offset - (t0 if t0 is not None else 0.0)
            _, _, _, representation, out_time, out_values = _clip_and_reduce(
                event_time, np.asarray(values, dtype=float), start_time=None, end_time=None,
                point_budget=DEFAULT_POINT_BUDGET,
            )
            trace = MeasurementTrace(
                id=trace_id, kind=kind, members=product_members, unit=unit, layer_ids=[reference.layer_id],
                x=[float(v) for v in out_time], y=[None if not np.isfinite(v) else float(v) for v in out_values],
                representation=representation, source_id=source_id,
            )
            by_id[trace_id] = trace
            result.traces.append(trace)
            result.event = EventAlignmentInfo(group_id, t0, t0 is not None)
    return result
