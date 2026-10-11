"""Oscillation Analysis -- oscillation interpretation service (DEC-179 [APPROVED], DEC-182 [APPROVED], DEC-183 [APPROVED]; building on DEC-171..181).

For the reference signal alone, or the reference plus explicitly chosen signals, it runs the SAME accepted per-signal chain as the
cross-signal evidence (`analyse_signals`: spectrum + DEC-175 candidates, DEC-177 damping, DEC-176 spectrogram -- no second peak
detector, no second signal registry), groups the candidates with `cross_signal_evidence.group_components` and then interprets each
component with `oscillation_classification.classify_component`.

DEC-182: with two or more signals and a synchronization registry the front half is the SHARED one of the mode shape
(`derive_components`: authoritative Time Group alignment, ONE analysis pass per signal -- spectrum, spectrogram and damping are not repeated), and
for every component seen in two or more signals the mode shape and the coherence are computed from that same context and handed to the
classifier as structured evidence; the same results are returned beside the components so the page draws them without further requests. The
classification consumes the structured results; it never touches samples. Without a synchronization registry, or for one signal, the result is the
DEC-179 result. Read-only; nothing is stored. Deterministic: no AI, no probability.
"""

from __future__ import annotations

import time

from app.domain import cross_signal_evidence as cs
from app.domain import coherence as co
from app.domain import mode_shape as ms
from app.domain import oscillation_classification as oc
from app.domain import oscillation_summary as osum
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.oscillation_coherence_service import coherence_component
from app.services.oscillation_cross_signal_service import analyse_signals, build_result, validate_entries
from app.services.oscillation_mode_shape_service import component_mode_shape, derive_components
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry


def compute_interpretation(
    *,
    workspace_id: str,
    entries: list[dict],
    f_min_hz: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
    sync_registry: SynchronizationRegistry | None = None,
) -> dict:
    """`entries` as for `compute_cross_signal` (1-8 signals). With `sync_registry` and 2+ signals the mode shape and the coherence are integrated."""
    validate_entries(entries, f_min_hz, f_max_hz, minimum=1)
    started = time.perf_counter()
    integrated = sync_registry is not None and len(entries) >= 2
    shape_components: list[dict] = []
    coherence_components: list[dict] = []
    if integrated:
        ctx = derive_components(
            workspace_id=workspace_id, entries=entries, f_min_hz=f_min_hz, f_max_hz=f_max_hz, source_registry=source_registry,
            calc_registry=calc_registry, sync_registry=sync_registry, include_damping=True, minimum=1)
        signal_rows, analysed, components = ctx["signal_rows"], ctx["analysed"], ctx["components"]
        analysed_at, grouped_at = ctx["analysed_at"], ctx["grouped_at"]
    else:
        signal_rows, analysed = analyse_signals(
            workspace_id=workspace_id, entries=entries, f_min_hz=f_min_hz, f_max_hz=f_max_hz,
            source_registry=source_registry, calc_registry=calc_registry)
        analysed_at = time.perf_counter()
        components = cs.group_components(analysed)
        grouped_at = time.perf_counter()
    spatial_ms = 0.0
    classify_ms = 0.0
    spatial_by_id: dict[int, dict] = {}
    for component in components:
        evidence = {"mode_shape": None, "coherence": None} if integrated else None
        if integrated and component["signal_count"] >= 2:
            tick = time.perf_counter()
            neighbours = [c["representative_frequency_hz"] for c in components if c is not component]
            shape = component_mode_shape(component, ctx["analysed_by_index"], ctx["window_of"], ctx["alignments"], neighbours)
            coherent = coherence_component(component, shape, ctx["analysed_by_index"], ctx["window_of"], ctx["alignments"])
            shape_components.append(shape)
            coherence_components.append(coherent)
            evidence = {"mode_shape": shape, "coherence": coherent}
            spatial_by_id[component["id"]] = evidence
            spatial_ms += (time.perf_counter() - tick) * 1000.0
        tick = time.perf_counter()
        component["interpretation"] = oc.classify_component(component, analysed, evidence)
        classify_ms += (time.perf_counter() - tick) * 1000.0
    # DEC-183: the engineer-facing summary is arranged from the structured results above -- no further signal processing.
    tick = time.perf_counter()
    units_by_index = {row["index"]: row.get("unit") for row in signal_rows}
    for component in components:
        spatial = spatial_by_id.get(component["id"]) or {}
        component["summary"] = osum.build_component_summary(
            component, units_by_index=units_by_index, integrated=integrated, mode_shape=spatial.get("mode_shape"), coherence=spatial.get("coherence"))
    summary_ms = (time.perf_counter() - tick) * 1000.0
    finished = time.perf_counter()
    result = build_result(signal_rows, analysed, f_min_hz, f_max_hz, components)
    result["interpretation_parameters"] = oc.parameters()
    result["timings_ms"] = {
        "signal_analysis": (analysed_at - started) * 1000.0,
        "grouping": (grouped_at - analysed_at) * 1000.0,
        "classification": classify_ms,
        "summary": summary_ms,
    }
    if integrated:
        result["timings_ms"].update(mode_shape_and_coherence=spatial_ms, total=(finished - started) * 1000.0)
        result["mode_shape"] = {"parameters": ms.parameters(), "components": shape_components}
        result["coherence"] = {"parameters": co.parameters(), "components": coherence_components}
    return result
