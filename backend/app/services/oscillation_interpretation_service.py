"""Oscillation Analysis -- oscillation interpretation service (DEC-179 [APPROVED], building on DEC-171..178).

For the reference signal alone, or the reference plus explicitly chosen signals, it runs the SAME accepted per-signal chain as the
cross-signal evidence (`analyse_signals`: spectrum + DEC-175 candidates, DEC-177 damping, DEC-176 spectrogram -- no second peak
detector, no second signal registry), groups the candidates with `cross_signal_evidence.group_components` and then interprets each
component with `oscillation_classification.classify_component`. The classification consumes the structured results; it never
touches samples and costs a handful of comparisons per component (reported separately in `timings_ms`). Read-only; nothing is
stored. Deterministic: no AI, no probability.
"""

from __future__ import annotations

import time

from app.domain import cross_signal_evidence as cs
from app.domain import oscillation_classification as oc
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.oscillation_cross_signal_service import analyse_signals, build_result, validate_entries
from app.services.workspace_registry import WorkspaceRegistry


def compute_interpretation(
    *,
    workspace_id: str,
    entries: list[dict],
    f_min_hz: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> dict:
    """`entries` as for `compute_cross_signal` (1-8 signals)."""
    validate_entries(entries, f_min_hz, f_max_hz, minimum=1)
    started = time.perf_counter()
    signal_rows, analysed = analyse_signals(
        workspace_id=workspace_id, entries=entries, f_min_hz=f_min_hz, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry)
    analysed_at = time.perf_counter()
    components = cs.group_components(analysed)
    grouped_at = time.perf_counter()
    for component in components:
        component["interpretation"] = oc.classify_component(component, analysed)
    classified_at = time.perf_counter()
    result = build_result(signal_rows, analysed, f_min_hz, f_max_hz, components)
    result["interpretation_parameters"] = oc.parameters()
    result["timings_ms"] = {
        "signal_analysis": (analysed_at - started) * 1000.0,
        "grouping": (grouped_at - analysed_at) * 1000.0,
        "classification": (classified_at - grouped_at) * 1000.0,
    }
    return result
