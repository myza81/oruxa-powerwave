"""Oscillation Analysis -- cross-signal evidence service (DEC-178 [APPROVED], building on DEC-171..177).

For an explicit, user-chosen set of signals (the page's "Compare signals" control -- never a hidden
all-workspace batch) it re-validates every signal from WORKSPACE STATE and runs the SAME accepted
analysis as a single-signal Analyze for each: the Welch spectrum + DEC-175 candidates, the DEC-176
spectrogram (for time evidence) and the DEC-177 damping estimate. It then groups the candidates with
`app.domain.cross_signal_evidence` (no second peak detector, no second signal registry). Read-only,
nothing is stored. A signal that cannot be analysed is reported as `excluded` with its reason and the
others still compare. No classification is made.
"""

from __future__ import annotations

from app.domain import cross_signal_evidence as cs
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import UNDEFINED
from app.domain.mode_shape import track_activity
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_damping_service import compute_damping
from app.services.oscillation_representation_service import UnsupportedRepresentationError
from app.services.oscillation_spectrogram_service import compute_spectrogram
from app.services.oscillation_spectrum_service import (
    SPECTRUM_REPRESENTATIONS,
    _validate_request_numbers,
    compute_spectrum,
)
from app.services.workspace_registry import WorkspaceRegistry

MAX_SIGNALS = 8


class _Lineage:
    """The raw source channels a signal is ultimately computed from (calculated channels follow their inputs)."""

    def __init__(self, workspace_id: str, source_registry: WorkspaceRegistry, calc_registry: CalculatedChannelRegistry) -> None:
        self.workspace_id, self.source_registry, self.calc_registry = workspace_id, source_registry, calc_registry

    def roots(self, ref: ChannelRef, _seen: frozenset = frozenset()) -> frozenset[str]:
        if ref.kind == "source":
            return frozenset({f"{ref.source_id}::{ref.channel_name}"})
        if ref.calculated_channel_id in _seen:
            return frozenset()
        calc = self.calc_registry.get(self.workspace_id, ref.calculated_channel_id)
        if calc is None:
            return frozenset({f"calculated::{ref.calculated_channel_id}"})
        out: frozenset[str] = frozenset()
        for inner in calc.inputs:
            out |= self.roots(inner, _seen | {ref.calculated_channel_id})
        return out or frozenset({f"calculated::{ref.calculated_channel_id}"})

    def engineering_type(self, ref: ChannelRef) -> str:
        if ref.kind == "calculated":
            calc = self.calc_registry.get(self.workspace_id, ref.calculated_channel_id)
            return (calc.engineering_type if calc else None) or UNDEFINED
        active = self.source_registry.get(self.workspace_id, ref.source_id)
        if active is None:
            return UNDEFINED
        channel = next((c for c in active.metadata.analog_channels if c.name == ref.channel_name), None)
        return channel.engineering_type if channel else UNDEFINED


def _parameters() -> dict:
    return {
        "match_rule": "|f_a - f_b| <= factor x max(Welch bin spacing of the two signals)",
        "match_resolution_factor": cs.MATCH_RESOLUTION_FACTOR,
        "representative_frequency": "prominence-weighted mean of the members' frequencies",
        "active_track_fraction": cs.ACTIVE_TRACK_FRACTION,
        "decay_rate_ratio_limit": cs.DECAY_RATE_RATIO_LIMIT,
        "max_signals": MAX_SIGNALS,
        "heuristics": "Phase-1 engineering heuristics, not standards; no oscillation type is inferred",
    }


def validate_entries(entries: list[dict], f_min_hz: float, f_max_hz: float, *, minimum: int = 1) -> None:
    """The request-level checks shared by the cross-signal evidence and the interpretation: cap, representation, duplicates, numbers."""
    if len(entries) < minimum:
        raise ImportServiceError(f"At least {minimum} signal{'s' if minimum != 1 else ''} must be given.")
    if len(entries) > MAX_SIGNALS:
        raise ImportServiceError(f"At most {MAX_SIGNALS} signals can be compared at once.")
    seen: set[tuple] = set()
    for entry in entries:
        if entry["representation"] not in SPECTRUM_REPRESENTATIONS:
            raise UnsupportedRepresentationError(f"Analysis representation '{entry['representation']}' is not implemented.")
        ref = entry["input_ref"]
        identity = (ref.kind, ref.source_id, ref.channel_name, ref.calculated_channel_id)
        if identity in seen:
            raise ImportServiceError("The same signal was listed twice; a signal is compared once.")
        seen.add(identity)
        _validate_request_numbers(entry["window_start_s"], entry["window_end_s"], f_min_hz, f_max_hz)


def analyse_signals(
    *,
    workspace_id: str,
    entries: list[dict],
    f_min_hz: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
    include_damping: bool = True,
    keep_activity: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Run the accepted per-signal chain (spectrum + candidates, damping, spectrogram) for already validated `entries`.
    Returns (`signal rows` for the response, `analysed` signal dicts for grouping / interpretation).
    `include_damping=False` skips the DEC-177 estimate (the mode-shape evidence does not use it); `keep_activity=True` keeps each
    candidate's per-slice STFT activity (`activity`, rank -> track) for the mode-shape common interval. Defaults change nothing."""
    lineage = _Lineage(workspace_id, source_registry, calc_registry)
    signal_rows: list[dict] = []
    analysed: list[dict] = []
    for index, entry in enumerate(entries):
        ref = entry["input_ref"]
        label = entry.get("label") or (ref.channel_name if ref.kind == "source" else ref.calculated_channel_id)
        row = {
            "index": index, "label": label, "status": "ok", "reason_code": None, "message": None,
            "representation": entry["representation"], "signal_revision": entry.get("signal_revision"),
            "origin": cs.ORIGIN_CALCULATED if ref.kind == "calculated" else cs.ORIGIN_RAW,
            "signal_type": lineage.engineering_type(ref), "offset_s": entry["offset_s"],
            "window_start_s": entry["window_start_s"], "window_end_s": entry["window_end_s"],
            "source_id": None, "recording": None, "unit": None, "bin_spacing_hz": None,
            "candidate_count": 0, "damping_available_count": 0, "spectrogram_status": None,
        }
        signal_rows.append(row)
        common = dict(
            workspace_id=workspace_id, input_ref=ref, representation=entry["representation"],
            window_start_s=entry["window_start_s"], window_end_s=entry["window_end_s"], f_min_hz=f_min_hz, f_max_hz=f_max_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
        try:
            spectrum = compute_spectrum(**common)
            damping = (compute_damping(signal_revision=entry.get("signal_revision"), candidate_frequencies_hz=None, spectrum=spectrum, **common)
                       if include_damping else {"results": []})
            gram = compute_spectrogram(signal_revision=entry.get("signal_revision"), **common)
        except ImportServiceError as exc:
            row.update(status="excluded", reason_code=exc.code, message=exc.message)
            continue
        candidates = spectrum["detection"]["candidates"]
        sig = spectrum["signal"]
        row.update(
            source_id=sig["source_id"], recording=sig.get("source_recording") or sig["source_id"], unit=sig.get("unit"),
            bin_spacing_hz=spectrum["welch"]["bin_spacing_hz"], candidate_count=len(candidates),
            spectrogram_status=gram["status"],
        )
        by_rank_damping = {r["rank"]: r for r in damping["results"]}
        row["damping_available_count"] = sum(1 for r in damping["results"] if r["status"] == "available")
        temporal: dict[int, dict] = {}
        activity: dict[int, dict | None] = {}
        if gram["status"] == "ok":
            for c in candidates:
                temporal[c["rank"]] = cs.active_interval(
                    gram["times_s"], gram["frequencies_hz"], gram["psd"], c["frequency_hz"], gram["stft"]["window_s"])
                if keep_activity:
                    activity[c["rank"]] = track_activity(gram["times_s"], gram["frequencies_hz"], gram["psd"], c["frequency_hz"])
        analysed.append({
            "index": index, "label": label, "signal_type": row["signal_type"], "recording": sig["source_id"],
            "recording_label": row["recording"], "origin": row["origin"], "lineage_roots": sorted(lineage.roots(ref)),
            "offset_s": entry["offset_s"], "bin_spacing_hz": row["bin_spacing_hz"], "candidates": candidates,
            "damping": {rank: _damping_summary(r) for rank, r in by_rank_damping.items()}, "temporal": temporal,
            "activity": activity, "unit": sig.get("unit"),
            # Additive context for the interpretation (DEC-179); grouping ignores it.
            "window_start_s": spectrum["window"]["start_s"], "window_end_s": spectrum["window"]["end_s"],
            "representation": entry["representation"],
            "nominal_frequency_hz": spectrum["representation"].get("nominal_frequency_hz"),
            "nominal_frequency_assumed": spectrum["representation"].get("nominal_frequency_origin") == "assumed_default",
        })
    return signal_rows, analysed


def compute_cross_signal(
    *,
    workspace_id: str,
    entries: list[dict],
    f_min_hz: float,
    f_max_hz: float,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> dict:
    """`entries`: `{input_ref, representation, signal_revision, window_start_s, window_end_s, offset_s, label}`."""
    validate_entries(entries, f_min_hz, f_max_hz, minimum=1)
    signal_rows, analysed = analyse_signals(
        workspace_id=workspace_id, entries=entries, f_min_hz=f_min_hz, f_max_hz=f_max_hz,
        source_registry=source_registry, calc_registry=calc_registry)
    return build_result(signal_rows, analysed, f_min_hz, f_max_hz, cs.group_components(analysed))


def build_result(signal_rows: list[dict], analysed: list[dict], f_min_hz: float, f_max_hz: float, components: list[dict]) -> dict:
    ok = sum(1 for r in signal_rows if r["status"] == "ok")
    return {
        "status": "ok" if components else "no_components",
        "message": None if components else ("No candidate was detected in any compared signal." if ok else "None of the compared signals could be analysed."),
        "setup": {"frequency_min_hz": f_min_hz, "frequency_max_hz": f_max_hz},
        "parameters": _parameters(), "signals": signal_rows, "components": components,
    }


def _damping_summary(result: dict) -> dict:
    return {
        "status": result["status"], "behaviour": result["behaviour"], "decay_rate_per_s": result["decay_rate_per_s"],
        "damping_ratio": result["damping_ratio"], "reason_code": result["reason_code"], "message": result["message"],
        "fit_start_s": result["fit"]["start_s"] if result["fit"] else None,
        "fit_end_s": result["fit"]["end_s"] if result["fit"] else None,
    }
