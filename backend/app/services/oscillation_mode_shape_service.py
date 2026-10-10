"""Oscillation Analysis -- mode shape / relative phase service (DEC-180 [PROPOSAL], building on DEC-171..179).

For the explicit signals of a comparison it re-derives the DEC-178 components from WORKSPACE STATE with the accepted
chain (`analyse_signals`: spectrum + DEC-175 candidates + DEC-176 spectrogram; the DEC-177 damping estimate is not used here and is
skipped) and groups them with `cross_signal_evidence.group_components` -- no second peak detector, no second signal registry. For
every component observed in two or more signals it then, per comparable quantity group (engineering type + unit), projects the
members onto one common frequency over one common physical interval (`app.domain.mode_shape`).

Time alignment is taken from the AUTHORITATIVE synchronization model (`synchronization_service.list_source_alignments`: Time
Group + timestamp placement + manual offset), never from an offset sent by the browser. Members whose recordings sit in different
Time Groups are not compared: they get no number, only the explicit unavailable statement. Read-only; nothing is stored. Phases
supplied by the frontend are not accepted. No classification, no AI.
"""

from __future__ import annotations

import time as _time

import numpy as np

from app.domain import cross_signal_evidence as cs
from app.domain import mode_shape as ms
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import UNDEFINED
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_cross_signal_service import analyse_signals, validate_entries
from app.services.oscillation_spectrum_service import prepare_analysis_window
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import list_source_alignments
from app.services.workspace_registry import WorkspaceRegistry

QUANTITY_UNKNOWN_MESSAGE = (
    "The signal type is not classified, so these signals cannot be established as the same physical quantity.")


def _source_id_of(ref: ChannelRef, workspace_id: str, calc_registry: CalculatedChannelRegistry) -> str | None:
    if ref.kind == "source":
        return ref.source_id
    calc = calc_registry.get(workspace_id, ref.calculated_channel_id)
    return calc.reference_source_id if calc else None


def compute_mode_shape(
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
    """`entries`: `{input_ref, representation, signal_revision, window_start_s, window_end_s, label}` (2-8 signals). Any `offset_s`
    is ignored: the effective alignment offset comes from the synchronization model."""
    validate_entries([{**e, "offset_s": 0.0} for e in entries], f_min_hz, f_max_hz, minimum=2)
    started = _time.perf_counter()
    alignments = {v.source_id: v for v in list_source_alignments(
        workspace_id=workspace_id, registry=sync_registry, source_registry=source_registry)}
    prepared_entries = []
    for entry in entries:
        view = alignments.get(_source_id_of(entry["input_ref"], workspace_id, calc_registry))
        prepared_entries.append({**entry, "offset_s": view.effective_alignment_offset_s if view else 0.0})
    signal_rows, analysed = analyse_signals(
        workspace_id=workspace_id, entries=prepared_entries, f_min_hz=f_min_hz, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry, include_damping=False, keep_activity=True)
    analysed_at = _time.perf_counter()
    components = cs.group_components(analysed)
    grouped_at = _time.perf_counter()
    analysed_by_index = {s["index"]: s for s in analysed}
    windows: dict[int, object] = {}

    def window_of(index: int):
        if index not in windows:
            entry, signal = prepared_entries[index], analysed_by_index[index]
            windows[index] = prepare_analysis_window(
                workspace_id=workspace_id, input_ref=entry["input_ref"], representation=entry["representation"],
                window_start_s=signal["window_start_s"], window_end_s=signal["window_end_s"], f_max_hz=f_max_hz,
                source_registry=source_registry, calc_registry=calc_registry)
        return windows[index]

    wanted = None
    if component_frequency_hz is not None:
        multi = [c for c in components if c["signal_count"] >= 2]
        if multi:
            nearest = min(multi, key=lambda c: abs(c["representative_frequency_hz"] - component_frequency_hz))
            if abs(nearest["representative_frequency_hz"] - component_frequency_hz) <= nearest["match_tolerance_hz"] * (1 + 1e-9) + 1e-9:
                wanted = nearest["id"]
    out_components = []
    for comp in components:
        if comp["signal_count"] < 2 or (component_frequency_hz is not None and comp["id"] != wanted):
            continue
        neighbours = [c["representative_frequency_hz"] for c in components if c is not comp]
        out_components.append(_component(comp, analysed_by_index, window_of, alignments, neighbours))
    finished = _time.perf_counter()
    return {
        "status": "ok" if out_components else "no_components",
        "message": None if out_components else (
            "No oscillation component is observed in two or more of the compared signals, so no relative phase can be estimated."),
        "setup": {"frequency_min_hz": f_min_hz, "frequency_max_hz": f_max_hz},
        "parameters": ms.parameters(), "signals": signal_rows, "components": out_components,
        "timings_ms": {"signal_analysis": (analysed_at - started) * 1000.0, "grouping": (grouped_at - analysed_at) * 1000.0,
                       "mode_shape": (finished - grouped_at) * 1000.0},
    }


def _component(comp: dict, analysed_by_index: dict, window_of, alignments: dict, neighbours: list[float]) -> dict:
    by_quantity: dict[tuple, list[dict]] = {}
    for member in comp["members"]:
        signal = analysed_by_index[member["signal_index"]]
        by_quantity.setdefault((signal["signal_type"], signal.get("unit") or ""), []).append(member)
    groups = []
    for (quantity, unit), members in sorted(by_quantity.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        raws = []
        for member in members:
            signal = analysed_by_index[member["signal_index"]]
            view = alignments.get(signal["recording"])
            raws.append({
                "signal_index": member["signal_index"], "label": member["label"],
                "recording": signal.get("recording_label", signal["recording"]), "origin": signal["origin"],
                "signal_type": quantity, "unit": unit or None, "time_group_id": view.time_group_id if view else None,
                "roots": frozenset(signal["lineage_roots"]), "candidate_frequency_hz": member["frequency_hz"],
                "prominence_db": member["prominence_db"], "rank": member["rank"],
            })
        if quantity == UNDEFINED:
            groups.append(ms.unavailable_group(
                quantity, unit or None, raws, code="quantity_unknown", message=QUANTITY_UNKNOWN_MESSAGE, comparable=False))
            continue
        # One time basis per comparison: the Time Group with the most members, then the strongest candidate, then the lowest id.
        by_time_group: dict = {}
        for raw in raws:
            by_time_group.setdefault(raw["time_group_id"], []).append(raw)
        keep = sorted(by_time_group.items(), key=lambda kv: (
            kv[0] is None, -len(kv[1]), -max(r["prominence_db"] for r in kv[1]), str(kv[0])))[0][0]
        use = [r for r in raws if r["time_group_id"] == keep] if keep is not None else []
        aside = [r for r in raws if r not in use]
        usable = []
        for raw in use:
            built = _build_member(raw, analysed_by_index[raw["signal_index"]], window_of, comp["representative_frequency_hz"])
            (usable if "t" in built else aside).append(built)
        groups.append(ms.analyse_quantity_group(
            quantity_type=quantity, unit=unit or None, members=usable,
            representative_frequency_hz=comp["representative_frequency_hz"], tolerance_hz=comp["match_tolerance_hz"],
            neighbour_frequencies_hz=neighbours, excluded_members=aside))
    quantities = [g["quantity_type"] for g in groups]
    cross = None
    if len(groups) > 1:
        cross = {
            "status": "not_combined", "quantities": quantities,
            "message": f"The component appears in {', '.join(quantities)}. Each quantity is shown as its own mode shape; the phase between "
                       "different physical quantities is a dynamic cross-variable relationship, is not combined into one mode shape and is "
                       "not computed in Phase 1.",
        }
    return {
        "component_id": comp["id"], "component_frequency_hz": comp["representative_frequency_hz"],
        "frequency_spread_hz": comp["frequency_spread_hz"], "match_tolerance_hz": comp["match_tolerance_hz"],
        "signal_count": comp["signal_count"], "groups": groups, "cross_variable": cross,
    }


def _build_member(raw: dict, signal: dict, window_of, frequency_hz: float) -> dict:
    """Attach the workspace-time samples and the activity episodes to a member, or report why it cannot be used."""
    try:
        pw = window_of(raw["signal_index"])
    except ImportServiceError as exc:
        return {**raw, "reason_code": exc.code, "message": exc.message}
    offset = signal["offset_s"]
    delay = pw.series.group_delay_s or 0.0
    t_ws = pw.t + offset - delay
    warnings = []
    if delay:
        warnings.append({"code": "rms_delay_compensated", "values": {"delay_s": delay},
                         "message": f"The RMS magnitude lags the waveform by {delay:.4g} s; the sample times were shifted back by that delay."})
    window = [(signal["window_start_s"] + offset, signal["window_end_s"] + offset)]
    data = [(float(t_ws[0]), float(t_ws[-1]))]
    activity = (signal.get("activity") or {}).get(raw["rank"])
    if activity is not None:
        episodes = ms.activity_episodes(activity, offset)
    else:
        episodes = window
        warnings.append({"code": "no_temporal_evidence", "values": {},
                         "message": "No time-frequency activity evidence exists for this member; its whole analysis window is used."})
    episodes = ms.intersect_episodes(ms.intersect_episodes(episodes, window), data)
    x = np.asarray(pw.x, dtype=float)
    # The STFT episode is long-windowed (tens of seconds at low frequency); restrict it to where the component is actually active.
    episodes = [run for episode in episodes for run in ms.refine_episode(t_ws, x, frequency_hz, episode)]
    return {**raw, "t": t_ws, "x": x, "episodes": episodes, "warnings": warnings}
