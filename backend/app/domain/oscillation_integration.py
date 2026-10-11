"""Oscillation Analysis -- integration of the Mode Shape (DEC-180) and Coherence (DEC-181) evidence into the interpretation (DEC-182 [PROPOSAL]).

This module turns the STRUCTURED results of the mode shape and the coherence of ONE component into interpretation evidence: supporting,
contradictory, unavailable and limiting entries, a spatial summary and -- for an electromechanical result -- a provisional subtype and an
interpretation strength. It never touches samples, never recomputes a spectrum, a phase or a coherence, and is a handful of comparisons.

**Evidence layers stay separate.** Frequency, temporal, dynamic (damping), spatial / modal (mode shape) and cross-spectral (coherence) evidence
are reported as their own entries; nothing is folded into a score, a probability or a percentage.

**Hard rules.**

* Frequency alone never decides a subtype (the DEC-179 rule is unchanged); the spatial evidence adjusts the *strength* of what the other
  dimensions already allow.
* A subtype is offered only from POSITIVE spatial evidence: stable relative phase across at least two distinct measurements of one comparable
  quantity. Anti-phase does not by itself prove inter-area; near-in-phase does not prove local; station names are never area evidence.
* Same-variable phase and coherence carry modal weight. Cross-variable coherence (for example MW with frequency) supports a common dynamic
  relationship only and never upgrades a subtype.
* Signals that share one source measurement are one measurement: they cannot create spatial evidence.
* Evidence that was refused or is unavailable (a short event) is reported as unavailable. It never lowers the family, the level or the
  behaviour that the other evidence supports.
* Coherence only adjusts the strength of the phase interpretation: below the chance level, or only marginally above it, the phase is
  kept but flagged as cautious and the subtype is not strengthened. "Clearly above" means at least
  ``COHERENCE_CLEAR_HEADROOM_FRACTION`` of the way from the chance level to 1 (a transparent Phase-1 margin, not a confidence).

Pure Python. Every threshold is a Phase-1 engineering heuristic, not a standard.
"""

from __future__ import annotations

# ---------------------------------------------------------------- Phase-1 heuristics (not standards)
#: A coherence is "clearly above" its chance level when it is at least this fraction of the way from the chance level to 1.
COHERENCE_CLEAR_HEADROOM_FRACTION = 0.5
#: A relative phase is a meaningful separation (not "approximately in phase") beyond this many degrees (the DEC-180 in-phase band).
MEANINGFUL_PHASE_SEPARATION_DEG = 30.0

COHERENCE_BELOW = "below_chance_level"
COHERENCE_MARGINAL = "marginally_above_chance_level"
COHERENCE_CLEAR = "clearly_above_chance_level"
COHERENCE_UNKNOWN = "chance_level_unavailable"

STRENGTH_DETECTED = "detected"
STRENGTH_POSSIBLE = "possible"
STRENGTH_CONSISTENT = "consistent_with"
STRENGTH_SUPPORTED = "supported_provisional"
STRENGTH_UNRESOLVED = "unresolved"
STRENGTH_LABELS = {
    STRENGTH_DETECTED: "Detected",
    STRENGTH_POSSIBLE: "Possible",
    STRENGTH_CONSISTENT: "Consistent with",
    STRENGTH_SUPPORTED: "Supported (provisional)",
    STRENGTH_UNRESOLVED: "Unresolved",
}

SUBTYPE_PROVISIONAL_LABEL = "Provisional inter-area electromechanical mode"
SUBTYPE_POSSIBLE_LABEL = "Possible inter-area electromechanical mode"

#: The wording hierarchy (DEC-182). Kept verbatim so a reviewer can find it.
TEXT_PHASE_ONLY = (
    "The component has spatial phase evidence consistent with an electromechanical mode. Inter-area behaviour is possible, but coherence and/or area "
    "metadata are insufficient for a stronger conclusion.")
TEXT_PHASE_AND_COHERENCE = (
    "The evidence is consistent with a spatial electromechanical mode and supports a provisional inter-area interpretation. The available metadata does "
    "not independently prove that the measurements represent separate grid areas.")
TEXT_PHASE_SEPARATION = (
    "The component shows stable phase separation across distinct measurements, which is consistent with a spatial electromechanical mode. The available "
    "metadata does not establish that the measurements represent different grid areas, so inter-area classification remains provisional.")
TEXT_IN_PHASE = (
    "Distinct measurements respond approximately in phase. Absence of opposing phase is not proof of a local mode: it may be a common coherent response, "
    "measurements in one modal region, a common forcing, or too little spatial diversity.")
TEXT_COHERENCE_WEAK_FOR_PHASE = (
    "Relative phase is available, but cross-spectral coherence at the component frequency is weak or marginal; interpret the phase relationship cautiously.")
TEXT_CROSS_VARIABLE = "Cross-variable coherence supports a common dynamic relationship but does not establish a conventional mode-shape relationship."
TEXT_COHERENCE_ONLY = "Same-variable coherence supports a shared oscillatory relationship but cannot replace relative phase / mode-shape evidence."
TEXT_SUBTYPE_UNRESOLVED = "Electromechanical subtype unresolved — local or inter-area cannot be distinguished with the available evidence."


def _fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}g}"


def _ev(code: str, message: str, **values) -> dict:
    return {"code": code, "message": message, "values": values}


def parameters() -> dict:
    return {
        "coherence_clear_headroom_fraction": COHERENCE_CLEAR_HEADROOM_FRACTION,
        "meaningful_phase_separation_deg": MEANINGFUL_PHASE_SEPARATION_DEG,
        "spatial_evidence": "mode shape and coherence refine the strength of an interpretation; unavailable evidence never lowers it; no combined score",
    }


def coherence_level(pair: dict) -> dict:
    """Where one coherence measurement stands against its own chance level: below it, marginally above it, or clearly above it."""
    chance, value = pair.get("chance_level"), pair.get("coherence")
    if chance is None or value is None:
        return {"level": COHERENCE_UNKNOWN, "coherence": value, "chance_level": chance, "clear_threshold": None}
    clear = chance + COHERENCE_CLEAR_HEADROOM_FRACTION * (1.0 - chance)
    level = COHERENCE_BELOW if value <= chance else COHERENCE_MARGINAL if value < clear else COHERENCE_CLEAR
    return {"level": level, "coherence": value, "chance_level": chance, "clear_threshold": clear}


LEVEL_ORDER = {COHERENCE_UNKNOWN: 0, COHERENCE_BELOW: 1, COHERENCE_MARGINAL: 2, COHERENCE_CLEAR: 3}


def _codes(items: list[dict]) -> set[str]:
    return {item["code"] for item in items}


# ---------------------------------------------------------------- facts
def mode_shape_facts(mode_shape: dict | None) -> dict:
    """The best usable same-variable group of the mode shape and why the others are not."""
    if mode_shape is None:
        return {"computed": False, "chosen": None, "unavailable": [], "provenance_only": False}
    groups = mode_shape.get("groups", [])
    unavailable = [g for g in groups if g["status"] != "ok"]
    usable, provenance_only = [], False
    for group in groups:
        if group["status"] != "ok":
            continue
        pattern = group["phase_pattern"]
        by_index = {m["signal_index"]: m for m in group["members"]}
        independents = [by_index[i] for i in pattern.get("member_bands", {}) if i in by_index]
        if group["distinct_measurement_count"] < 2:
            provenance_only = True
            continue
        if pattern["code"] == "unstable":
            non_ref = [m for m in group["members"] if m["status"] == "ok" and not m["is_reference"] and m["phase_deg"] is not None]
            usable.append({"group": group, "pattern": pattern, "independents": non_ref, "unstable": True})
        elif independents:
            usable.append({"group": group, "pattern": pattern, "independents": independents, "unstable": False})
        else:
            provenance_only = True
    chosen = max(usable, key=lambda u: (len(u["independents"]), u["group"]["distinct_measurement_count"])) if usable else None
    return {"computed": True, "chosen": chosen, "unavailable": unavailable, "provenance_only": provenance_only}


def coherence_facts(coherence: dict | None, chosen: dict | None) -> dict:
    if coherence is None:
        return {"computed": False, "same": [], "cross": [], "refused": []}
    pairs = list(coherence.get("pairs", [])) + list(coherence.get("other_pairs", []))
    ok = [p for p in pairs if p["status"] == "ok" and "shared_measurement_provenance" not in _codes(p["warnings"])]
    refused = [p for p in coherence.get("pairs", []) if p["status"] != "ok"]
    indexes = {m["signal_index"] for m in chosen["group"]["members"]} if chosen else None
    same = [p for p in ok if p["relationship_type"] == "same_variable"
            and (indexes is None or (p["reference_index"] in indexes and p["member_index"] in indexes))]
    cross = [p for p in ok if p["relationship_type"] == "cross_variable"]
    return {"computed": True, "same": same, "cross": cross, "refused": refused}


# ---------------------------------------------------------------- integration
def integrate(evidence: dict | None, *, em_primary: bool, inter_area_ok: bool, in_local: bool, frequency_hz: float, distinct: int) -> dict:
    """Spatial interpretation evidence of ONE component.

    Returns ``supporting`` / ``limiting`` / ``contradictory`` / ``unavailable`` entries, a provisional ``subtype`` (electromechanical result with
    positive spatial evidence only) with its ``strength``, local ``alternatives`` and a machine-readable ``summary``. ``evidence`` is
    ``{"mode_shape": <component mode shape or None>, "coherence": <component coherence or None>}``."""
    supporting: list[dict] = []
    limiting: list[dict] = []
    contradictory: list[dict] = []
    unavailable: list[dict] = []
    alternatives: list[dict] = []
    ms = mode_shape_facts(evidence.get("mode_shape"))
    chosen = ms["chosen"]
    co = coherence_facts(evidence.get("coherence"), chosen)
    subtype = None
    strength = STRENGTH_POSSIBLE

    # ---- unavailable evidence is reported, never penalised -------------------------------------------------------
    for group in ms["unavailable"]:
        unavailable.append(_ev(
            "mode_shape_unavailable", f"Mode shape unavailable for {group['quantity_type']}: {group['message']}",
            quantity=group["quantity_type"], reason_code=group.get("reason_code") or "", status=group["status"]))
    if ms["computed"] and not ms["unavailable"] and chosen is None and not ms["provenance_only"]:
        unavailable.append(_ev("mode_shape_unavailable", "Mode shape unavailable: no comparable group of signals was available."))
    if co["computed"] and co["refused"] and not co["same"] and not co["cross"]:
        first = co["refused"][0]
        unavailable.append(_ev(
            "coherence_unavailable", f"Coherence unavailable for {first['member_signal']}: {first['message']}",
            reason_code=first.get("reason_code") or "", pairs=len(co["refused"])))
    elif co["computed"] and co["refused"]:
        unavailable.append(_ev(
            "coherence_partly_unavailable", f"Coherence was unavailable for {len(co['refused'])} pair(s): {co['refused'][0]['message']}",
            pairs=len(co["refused"])))
    if ms["provenance_only"]:
        limiting.append(_ev(
            "spatial_evidence_shared_provenance",
            "Relative phase exists only between signals that share one source measurement; copies of one measurement are not spatial evidence."))

    # ---- coherence of the chosen phase group ---------------------------------------------------------------------
    levels = [coherence_level(p) for p in co["same"]]
    weakest = min(levels, key=lambda lv: LEVEL_ORDER[lv["level"]]) if levels else None
    for pair, lv in zip(co["same"], levels):
        if lv["level"] == COHERENCE_UNKNOWN:
            continue
        text = {COHERENCE_CLEAR: "clearly above", COHERENCE_MARGINAL: "only marginally above", COHERENCE_BELOW: "not above"}[lv["level"]]
        supporting.append(_ev(
            "same_variable_coherence",
            f"Same-variable coherence between {pair['reference_signal']} and {pair['member_signal']} at {_fmt(pair['coherence_frequency_hz'], 4)} Hz is "
            f"{_fmt(pair['coherence'], 3)}, {text} the {_fmt(lv['chance_level'], 3)} 95% null threshold.",
            coherence=pair["coherence"], chance_level=lv["chance_level"], level=lv["level"], member=pair["member_signal"]))
    if co["cross"]:
        best = max(co["cross"], key=lambda p: p["coherence"])
        supporting.append(_ev(
            "cross_variable_coherence",
            f"{TEXT_CROSS_VARIABLE} ({best['reference_signal']} – {best['member_signal']}: {_fmt(best['coherence'], 3)} at {_fmt(best['coherence_frequency_hz'], 4)} Hz).",
            coherence=best["coherence"], pairs=len(co["cross"])))

    # ---- phase of the chosen group ---------------------------------------------------------------------------------
    summary = {
        "mode_shape": {"computed": ms["computed"], "status": "ok" if chosen else ("shared_provenance" if ms["provenance_only"] else "unavailable"),
                       "quantity": chosen["group"]["quantity_type"] if chosen else None,
                       "pattern": chosen["pattern"]["code"] if chosen else None,
                       "independent_members": len(chosen["independents"]) if chosen else 0},
        "coherence": {"computed": co["computed"], "same_variable_pairs": len(co["same"]), "cross_variable_pairs": len(co["cross"]),
                      "refused_pairs": len(co["refused"]), "weakest_level": weakest["level"] if weakest else None},
    }
    if chosen is None:
        if co["same"] and em_primary:
            supporting.append(_ev("coherence_shared_dynamic", TEXT_COHERENCE_ONLY))
        if em_primary:
            if not (ms["computed"] or co["computed"]):
                limiting.append(_ev("spatial_evidence_not_computed", "Mode shape and coherence were not computed for this comparison."))
            # ONE concise statement of the unresolved subtype and why (never a second, differently worded copy of it).
            missing = "Relative phase / mode-shape evidence" if co["same"] else "Spatial phase and coherence evidence"
            limiting.append(_ev(
                "subtype_unresolved",
                f"{TEXT_SUBTYPE_UNRESOLVED} {missing} is unavailable and the location relationship of the measurements is unknown."))
        summary["strength"] = STRENGTH_POSSIBLE
        return _result(subtype, strength, supporting, limiting, contradictory, unavailable, alternatives, summary)

    group, pattern, independents = chosen["group"], chosen["pattern"], chosen["independents"]
    phases = ", ".join(f"{m['label']} {m['phase_deg']:+.3g}°" for m in independents)
    reference = group["reference"]["label"]
    stabilities = [(m.get("phase_stability") or {}).get("status") for m in independents]
    unstable = chosen["unstable"] or "unstable" in stabilities
    stable = bool(independents) and all(s == "stable" for s in stabilities)
    in_phase = pattern["code"] == "in_phase"
    separation = (not unstable) and pattern["code"] in ("anti_phase", "intermediate", "mixed")
    if unstable:
        contradictory.append(_ev(
            "phase_unstable", f"The relative phase against {reference} is not stable across the common interval ({phases}), so no phase pattern is relied on.",
            reference=reference))
    elif stable:
        supporting.append(_ev(
            "stable_relative_phase",
            f"Relative phase is stable across {len(independents) + 1} distinct {group['quantity_type']} measurements against {reference}: {phases}.",
            reference=reference, quantity=group["quantity_type"], members=len(independents)))
    else:
        supporting.append(_ev(
            "relative_phase_stability_not_assessed",
            f"Relative phase against {reference}: {phases}; its stability across the interval was not fully assessed.", reference=reference))
    if co["same"] and weakest is not None and weakest["level"] in (COHERENCE_BELOW, COHERENCE_MARGINAL) and not unstable:
        contradictory.append(_ev(
            "coherence_weak_for_phase", TEXT_COHERENCE_WEAK_FOR_PHASE, level=weakest["level"], coherence=weakest["coherence"], chance_level=weakest["chance_level"]))
    coherence_clear = bool(levels) and weakest is not None and weakest["level"] == COHERENCE_CLEAR

    if not em_primary:
        summary["strength"] = STRENGTH_POSSIBLE
        return _result(subtype, strength, supporting, limiting, contradictory, unavailable, alternatives, summary)

    # ---- electromechanical subtype from positive spatial evidence only -------------------------------------------
    if unstable:
        limiting.append(_ev("subtype_unresolved", TEXT_SUBTYPE_UNRESOLVED + " The relative phase is not stable."))
    elif in_phase:
        strength = STRENGTH_CONSISTENT
        supporting.append(_ev("in_phase_response", TEXT_IN_PHASE))
        limiting.append(_ev("subtype_unresolved", TEXT_SUBTYPE_UNRESOLVED + " The measurements respond approximately in phase."))
    elif separation:
        strength = STRENGTH_CONSISTENT
        if inter_area_ok:
            if stable and coherence_clear:
                strength = STRENGTH_SUPPORTED
                subtype = {"code": "inter_area", "label": SUBTYPE_PROVISIONAL_LABEL, "level": "possible", "strength": STRENGTH_SUPPORTED}
                supporting.append(_ev("spatial_summary", TEXT_PHASE_AND_COHERENCE))
            else:
                subtype = {"code": "inter_area", "label": SUBTYPE_POSSIBLE_LABEL, "level": "possible", "strength": STRENGTH_CONSISTENT}
                supporting.append(_ev("spatial_summary", TEXT_PHASE_ONLY if not co["same"] else TEXT_PHASE_SEPARATION))
            limiting.append(_ev(
                "location_relationship_unknown",
                "Recording locations are not proven to represent different grid areas (no station / area metadata is used), so inter-area remains provisional."))
            alternatives.append({
                "code": "local", "label": "Possible local electromechanical mode", "level": "possible", "relation": "subtype_alternative",
                "consistency": "consistent" if in_local else "weaker", "reasons": [],
                "limitations": [_ev("alternative_not_excluded",
                                    "A local or plant-related mode cannot be excluded without location evidence; phase separation alone does not distinguish it.")]})
        else:
            supporting.append(_ev("spatial_summary", TEXT_PHASE_SEPARATION))
            limiting.append(_ev(
                "subtype_unresolved", TEXT_SUBTYPE_UNRESOLVED + " The frequency, recordings or activity conditions do not support an inter-area reading by themselves."))
    summary["strength"] = strength
    summary["stable"] = stable
    summary["coherence_clear"] = coherence_clear
    return _result(subtype, strength, supporting, limiting, contradictory, unavailable, alternatives, summary)


def not_applicable(*, em_primary: bool) -> dict:
    """A component seen in ONE signal inside a multi-signal comparison: the mode shape and the coherence need two or more signals, so they are
    not applicable (not "unavailable" and not "refused"). The subtype stays unresolved and the card never claims that the relative phase is
    missing for a reason that does not apply to the matched components of the same comparison."""
    limiting = [_ev(
        "spatial_evidence_not_applicable",
        "Mode shape and coherence need the component in two or more signals; this component was observed in one signal, so they do not apply to it.")]
    if em_primary:
        limiting.append(_ev("subtype_unresolved", TEXT_SUBTYPE_UNRESOLVED + " The component has no counterpart in the other compared signals."))
    return _result(None, STRENGTH_POSSIBLE, [], limiting, [], [], [], {"strength": STRENGTH_POSSIBLE, "not_applicable": True})


def _result(subtype, strength, supporting, limiting, contradictory, unavailable, alternatives, summary) -> dict:
    return {"subtype": subtype, "strength": strength, "supporting": supporting, "limiting": limiting, "contradictory": contradictory,
            "unavailable": unavailable, "alternatives": alternatives, "summary": summary}
