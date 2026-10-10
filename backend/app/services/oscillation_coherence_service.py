"""Oscillation Analysis -- coherence evidence service (DEC-181 [PROPOSAL], building on DEC-171..180).

For the explicit signals of a comparison it re-derives the DEC-178 components from WORKSPACE STATE exactly as the mode shape does
(`oscillation_mode_shape_service.derive_components`: accepted per-signal chain, authoritative Time Group alignment, browser offsets ignored),
then, per component observed in two or more signals, estimates the magnitude-squared coherence between a deterministic reference member and
every other member (`app.domain.coherence`). The reference is the Mode Shape reference where a mode shape exists, otherwise the member with
the highest candidate prominence. The Mode Shape relative phase is attached only to warn when it is available but the coherence is low; the
mode-shape numbers are not changed. Read-only; nothing is stored; no classification; no AI.
"""

from __future__ import annotations

import time as _time

from app.domain import coherence as co
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.oscillation_mode_shape_service import (
    _component as mode_shape_component,
    build_component_members,
    derive_components,
    select_components,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry

REFERENCE_RULE_MODE_SHAPE = "mode_shape_reference"
REFERENCE_RULE_PROMINENCE = "highest_candidate_prominence"


def _reference(shape: dict, usable: list[dict]) -> tuple[int, str, dict[int, float | None]]:
    """The Mode Shape reference of the best mode-shape group (most members with a phase) when one exists, else the most prominent usable member."""
    usable_indexes = {m["signal_index"] for m in usable}
    best = None
    for group in shape["groups"]:
        if group["status"] != "ok" or not group["reference"] or group["reference"]["signal_index"] not in usable_indexes:
            continue
        phased = [m for m in group["members"] if m["phase_deg"] is not None]
        reference = next(m for m in group["members"] if m["is_reference"])
        key = (len(phased), reference["prominence_db"])
        if best is None or key > best[0]:
            best = (key, group, phased)
    if best is not None:
        _, group, phased = best
        return group["reference"]["signal_index"], REFERENCE_RULE_MODE_SHAPE, {m["signal_index"]: m["phase_deg"] for m in phased}
    strongest = sorted(usable, key=lambda m: (-m["prominence_db"], m["origin"] != "raw", m["signal_index"]))[0]
    return strongest["signal_index"], REFERENCE_RULE_PROMINENCE, {}


def coherence_component(comp: dict, shape: dict, analysed_by_index: dict, window_of, alignments: dict) -> dict:
    """The coherence evidence of ONE component. `shape` is that component's mode shape (computed once by the caller): its reference is the
    coherence reference and its phases give the low-coherence warning; the mode-shape numbers are not changed."""
    members = build_component_members(comp, analysed_by_index, window_of, alignments)
    usable = [m for m in members if "t" in m]
    excluded = [{"signal_index": m["signal_index"], "label": m["label"], "reason_code": m["reason_code"], "message": m["message"]}
                for m in members if "t" not in m]
    item = {"component_id": comp["id"], "component_frequency_hz": comp["representative_frequency_hz"], "signal_count": comp["signal_count"],
            "excluded_members": excluded, "reference": None, "reference_rule": None, "pairs": [], "other_pairs": [], "limitations": [],
            "cross_variable": None}
    if len(usable) >= 2:
        reference_index, rule, phases = _reference(shape, usable)
        result = co.analyse_component(
            members=usable, reference_index=reference_index, frequency_hz=comp["representative_frequency_hz"], phase_by_member=phases)
        item.update(reference=result["reference"], reference_rule=rule, pairs=result["pairs"], other_pairs=result["other_pairs"],
                    limitations=result["limitations"])
        kinds = {p["relationship_type"] for p in result["pairs"]}
        if len(kinds) > 1:
            item["cross_variable"] = {"message": "Same-variable pairs corroborate the spatial / modal evidence; cross-variable pairs (different physical quantities) "
                                                 "are supporting dynamic evidence only and are not equivalent to a mode shape."}
    return item


def compute_coherence(
    *,
    workspace_id: str,
    entries: list[dict],
    f_min_hz: float,
    f_max_hz: float,
    component_frequency_hz: float | None = None,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
    sync_registry: SynchronizationRegistry,
) -> dict:
    """`entries` as for `compute_mode_shape` (2-8 signals; any `offset_s` is ignored)."""
    ctx = derive_components(
        workspace_id=workspace_id, entries=entries, f_min_hz=f_min_hz, f_max_hz=f_max_hz, source_registry=source_registry,
        calc_registry=calc_registry, sync_registry=sync_registry)
    components, analysed_by_index, window_of, alignments = ctx["components"], ctx["analysed_by_index"], ctx["window_of"], ctx["alignments"]
    out_components = []
    for comp in select_components(components, component_frequency_hz):
        neighbours = [c["representative_frequency_hz"] for c in components if c is not comp]
        shape = mode_shape_component(comp, analysed_by_index, window_of, alignments, neighbours)
        out_components.append(coherence_component(comp, shape, analysed_by_index, window_of, alignments))
    finished = _time.perf_counter()
    return {
        "status": "ok" if out_components else "no_components",
        "message": None if out_components else (
            "No oscillation component is observed in two or more of the compared signals, so no coherence can be estimated."),
        "setup": {"frequency_min_hz": f_min_hz, "frequency_max_hz": f_max_hz},
        "parameters": co.parameters(), "signals": ctx["signal_rows"], "components": out_components,
        "timings_ms": {"signal_analysis": (ctx["analysed_at"] - ctx["started"]) * 1000.0,
                       "grouping": (ctx["grouped_at"] - ctx["analysed_at"]) * 1000.0,
                       "coherence": (finished - ctx["grouped_at"]) * 1000.0},
    }
