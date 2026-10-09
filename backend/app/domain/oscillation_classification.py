"""Oscillation Analysis -- deterministic oscillation interpretation (DEC-179 [APPROVED]).

Question answered: *given the structured evidence already measured for one oscillatory component
(candidate, STFT activity, damping, cross-signal grouping), what is it most consistent with -- and why,
and what stops us saying more?*  Deterministic and conservative; **no AI, no probability, no percentage
confidence, no phase / mode-shape / coherence / source-localisation evidence (none exists yet).**

Two separate dimensions are reported -- they are never collapsed into one label:

* **Behaviour** (temporal / dynamic): disturbance-excited ringdown, decaying oscillation (onset not observed),
  sustained, growing, intermittent, inconsistent across signals, insufficient temporal evidence.
* **Probable type** (family / mechanism): electromechanical (with a *possible* inter-area / local subtype),
  forced / sustained, control / converter interaction, sub-synchronous oscillation, or **unresolved**.

**Frequency alone never decides a type.** A frequency band is one named evidence dimension among several
(signal types, number of distinct measurements, recordings, temporal overlap, damping behaviour, onset);
every family below needs several dimensions at once, and a hypothesis whose band is satisfied but whose other
dimensions are not is simply not raised. Bands overlap between mechanisms and are Phase-1 heuristics.

Levels carry explicit deterministic meaning (see ``LEVEL_DEFINITIONS``); there is no numeric confidence.
``probable`` / ``possible`` / ``unresolved`` / ``insufficient_evidence`` are used only where the requirement
listed in the family's rule is met. Inter-area / local / SSO / control are never "definitive" in this slice.

Pure Python, no dependencies. Cheap: the cost is a handful of comparisons per component.
"""

from __future__ import annotations

from app.domain import channel_classification as cc
from app.domain import cross_signal_evidence as cs

# ---------------------------------------------------------------- Phase-1 heuristics (not standards)
#: Conventional electromechanical range (inter-area + local + intra-plant); a supporting dimension only.
ELECTROMECHANICAL_BAND_HZ = (0.1, 3.0)
#: Conventional sub-ranges. They OVERLAP on purpose: no frequency identifies a subtype.
INTER_AREA_BAND_HZ = (0.1, 1.0)
LOCAL_BAND_HZ = (0.8, 3.0)
#: Above the electromechanical range, up to the nominal frequency: described neutrally as a higher-frequency component. Frequency alone
#: never produces sub-synchronous wording; that needs the stronger SSO rule (control requirements + two recordings).
SUBSYNCHRONOUS_MIN_HZ = 3.0
#: Control / converter interactions are considered from the lower edge of this range upward.
CONTROL_BAND_HZ = (3.0, 100.0)
#: Assumed when neither the representation nor the recording declares one (flagged as a limitation).
ASSUMED_NOMINAL_FREQUENCY_HZ = 50.0
#: Active STFT span at least this fraction of the analysed window = "persistent".
PERSISTENT_SPAN_FRACTION = 0.8
#: A quiet lead-in of at least this fraction of the analysed window before the activity starts = onset observed.
ONSET_LEAD_FRACTION = 0.10
#: A candidate whose Welch base is at most this many bins wide is "narrow".
NARROW_BASE_BINS = 6.0

#: Broad engineering types (channel catalogue) that carry electromechanical swing information.
ELECTROMECHANICAL_SIGNAL_TYPES = frozenset({
    cc.POWER, cc.FREQUENCY, cc.ROCOF, cc.ENGINEERING_QUANTITY_ACTIVE_POWER, cc.ENGINEERING_QUANTITY_REACTIVE_POWER,
    cc.ENGINEERING_QUANTITY_APPARENT_POWER, cc.ENGINEERING_QUANTITY_VOLTAGE_ANGLE, cc.ENGINEERING_QUANTITY_CURRENT_ANGLE,
})
#: Broad engineering types that are electrical quantities of a converter / network interaction.
ELECTRICAL_SIGNAL_TYPES = frozenset({
    cc.VOLTAGE, cc.CURRENT, cc.POWER, cc.ENGINEERING_QUANTITY_ACTIVE_POWER, cc.ENGINEERING_QUANTITY_REACTIVE_POWER,
    cc.ENGINEERING_QUANTITY_APPARENT_POWER,
})

# ---------------------------------------------------------------- vocabulary (stable codes)
BEHAVIOUR_RINGDOWN = "disturbance_excited_ringdown"
BEHAVIOUR_DECAYING = "decaying_oscillation"
BEHAVIOUR_SUSTAINED = "sustained_oscillation"
BEHAVIOUR_GROWING = "growing_oscillation"
BEHAVIOUR_INTERMITTENT = "intermittent_oscillation"
BEHAVIOUR_INCONSISTENT = "inconsistent_across_signals"
BEHAVIOUR_INSUFFICIENT = "insufficient_temporal_evidence"

BEHAVIOUR_LABELS = {
    BEHAVIOUR_RINGDOWN: "Disturbance-excited decaying oscillation",
    BEHAVIOUR_DECAYING: "Decaying oscillation (onset not observed in the window)",
    BEHAVIOUR_SUSTAINED: "Sustained oscillation",
    BEHAVIOUR_GROWING: "Growing oscillation",
    BEHAVIOUR_INTERMITTENT: "Intermittent oscillation",
    BEHAVIOUR_INCONSISTENT: "Behaviour differs between signals",
    BEHAVIOUR_INSUFFICIENT: "Insufficient temporal evidence",
}

TYPE_ELECTROMECHANICAL = "electromechanical"
TYPE_FORCED_SUSTAINED = "forced_or_sustained"
TYPE_CONTROL_CONVERTER = "control_converter_interaction"
TYPE_SUB_SYNCHRONOUS = "sub_synchronous_oscillation"
TYPE_UNRESOLVED = "unresolved"

SUBTYPE_INTER_AREA = "inter_area"
SUBTYPE_LOCAL = "local"

DESCRIPTOR_HIGHER_FREQUENCY = "higher_frequency_oscillatory_component"

LEVEL_PROBABLE = "probable"
LEVEL_POSSIBLE = "possible"
LEVEL_UNRESOLVED = "unresolved"
LEVEL_INSUFFICIENT = "insufficient_evidence"
_LEVEL_RANK = {LEVEL_POSSIBLE: 1, LEVEL_PROBABLE: 2}

#: What each level means in this slice (echoed in every response's parameters).
LEVEL_DEFINITIONS = {
    LEVEL_PROBABLE: "every requirement of the family's rule is met, including cross-measurement and temporal agreement",
    LEVEL_POSSIBLE: "the family's minimum requirement is met but corroboration is missing or limited",
    LEVEL_UNRESOLVED: "evidence exists but no family's requirement is met, or several families remain equally plausible",
    LEVEL_INSUFFICIENT: "there is not enough temporal / damping / cross-signal evidence to say anything beyond the frequency",
}

_TYPE_LABELS = {
    TYPE_ELECTROMECHANICAL: "electromechanical oscillation",
    TYPE_FORCED_SUSTAINED: "forced/sustained oscillation",
    TYPE_CONTROL_CONVERTER: "control/converter interaction",
    TYPE_SUB_SYNCHRONOUS: "sub-synchronous oscillation",
}
_SUBTYPE_LABELS = {
    SUBTYPE_INTER_AREA: "inter-area electromechanical mode",
    SUBTYPE_LOCAL: "local electromechanical mode",
}
UNRESOLVED_LABEL = "Oscillation detected — type unresolved"
INSUFFICIENT_LABEL = "Oscillation detected — insufficient evidence to classify"

#: A hypothesis that satisfies strictly more of the same evidence dimensions as another is preferred to it
#: (the other stays visible as an alternative): sub-synchronous oscillation adds frequency-below-nominal and cross-recording
#: presence to control / converter interaction, which in turn adds electrical involvement and cross-measurement agreement to a
#: merely sustained component (forced / sustained).
_REFINES = {TYPE_SUB_SYNCHRONOUS: {TYPE_CONTROL_CONVERTER}, TYPE_CONTROL_CONVERTER: {TYPE_FORCED_SUSTAINED}}


def _fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}g}"


def _ev(code: str, message: str, **values) -> dict:
    return {"code": code, "message": message, "values": values}


def parameters() -> dict:
    """The conventions and thresholds, echoed in every response."""
    return {
        "classification": "Deterministic, evidence-based; frequency is supporting evidence only; no probability or percentage confidence; no AI",
        "level_probable": LEVEL_DEFINITIONS[LEVEL_PROBABLE],
        "level_possible": LEVEL_DEFINITIONS[LEVEL_POSSIBLE],
        "level_unresolved": LEVEL_DEFINITIONS[LEVEL_UNRESOLVED],
        "level_insufficient_evidence": LEVEL_DEFINITIONS[LEVEL_INSUFFICIENT],
        "electromechanical_band_hz": f"{ELECTROMECHANICAL_BAND_HZ[0]}-{ELECTROMECHANICAL_BAND_HZ[1]}",
        "inter_area_band_hz": f"{INTER_AREA_BAND_HZ[0]}-{INTER_AREA_BAND_HZ[1]}",
        "local_band_hz": f"{LOCAL_BAND_HZ[0]}-{LOCAL_BAND_HZ[1]}",
        "sub_synchronous_min_hz": SUBSYNCHRONOUS_MIN_HZ,
        "control_band_hz": f"{CONTROL_BAND_HZ[0]}-{CONTROL_BAND_HZ[1]}",
        "persistent_span_fraction": PERSISTENT_SPAN_FRACTION,
        "onset_lead_fraction": ONSET_LEAD_FRACTION,
        "narrow_base_bins": NARROW_BASE_BINS,
        "heuristics": "Phase-1 engineering heuristics, not standards; bands overlap and never decide a type on their own; "
                      "no phase, mode-shape, coherence or location evidence exists yet",
    }


# ---------------------------------------------------------------- evidence gathering
def _candidate_of(signal: dict, member: dict) -> dict | None:
    return next((c for c in signal["candidates"] if c["rank"] == member["rank"]), None)


def _temporal_facts(members: list[dict], signals: list[dict]) -> dict:
    """Per-member activity facts on each signal's OWN source-time window (lead-in and span are within one signal)."""
    spans, leads, with_evidence = [], [], 0
    for member in members:
        t = member.get("temporal")
        if not t or t.get("status") != "ok":
            continue
        signal = cs.signal_by_index(signals, member["signal_index"])
        window = signal["window_end_s"] - signal["window_start_s"]
        if not window > 0:
            continue
        with_evidence += 1
        spans.append(max(0.0, t["end_s"] - t["start_s"]) / window)
        leads.append(max(0.0, t["start_s"] - signal["window_start_s"]) / window)
    return {"members_with_evidence": with_evidence, "span_fractions": spans, "lead_fractions": leads}


def _behaviour(members: list[dict], temporal: dict) -> tuple[str, list[dict], list[dict]]:
    """Behaviour classification from the STFT activity and DEC-177 damping of the members. Returns (code, supporting, limiting)."""
    supporting: list[dict] = []
    limiting: list[dict] = []
    available = [m for m in members if m.get("damping") and m["damping"]["status"] == "available"]
    kinds = sorted({m["damping"]["behaviour"] for m in available})
    spans, leads = temporal["span_fractions"], temporal["lead_fractions"]
    n_temporal = temporal["members_with_evidence"]
    if n_temporal < len(members):
        limiting.append(_ev(
            "limited_temporal_evidence",
            f"Time-frequency activity is available for {n_temporal} of {len(members)} members.", with_evidence=n_temporal, members=len(members)))

    if len(kinds) > 1:
        limiting.append(_ev(
            "damping_behaviour_differs",
            "Damping behaviour differs between the signals (" + ", ".join(k.replace("_", " ") for k in kinds) + "), so no single behaviour is reported.",
            behaviours=",".join(kinds)))
        return BEHAVIOUR_INCONSISTENT, supporting, limiting
    if kinds == ["growing"]:
        supporting.append(_ev("growing_damping", f"The damping estimate shows a growing envelope in {len(available)} member(s).", members=len(available)))
        return BEHAVIOUR_GROWING, supporting, limiting
    if kinds == ["decaying"]:
        supporting.append(_ev("decaying_damping", f"The damping estimate shows a decaying envelope in {len(available)} member(s).", members=len(available)))
        if n_temporal and leads and all(lead >= ONSET_LEAD_FRACTION for lead in leads):
            supporting.append(_ev(
                "onset_observed",
                f"Activity begins after a quiet lead-in (at least {_fmt(ONSET_LEAD_FRACTION * 100, 2)} % of the analysed window) in every member with time-frequency evidence.",
                min_lead_fraction=min(leads), threshold=ONSET_LEAD_FRACTION))
            return BEHAVIOUR_RINGDOWN, supporting, limiting
        limiting.append(_ev(
            "onset_not_observed",
            "A quiet lead-in before the activity is not established in the window (or time-frequency evidence is missing), "
            "so the component is not reported as disturbance-excited.", members_with_evidence=n_temporal))
        return BEHAVIOUR_DECAYING, supporting, limiting
    if kinds == ["approximately_sustained"]:
        supporting.append(_ev("sustained_damping", f"The damping estimate shows an approximately constant envelope in {len(available)} member(s).", members=len(available)))
        return BEHAVIOUR_SUSTAINED, supporting, limiting

    # No damping estimate is available.
    limiting.append(_ev("damping_unavailable", "No damping estimate is available for this component.", available=0, members=len(members)))
    if any((m.get("damping") or {}).get("reason_code") == "intermittent_component" for m in members):
        supporting.append(_ev("intermittent_activity", "The damping estimator refused the component as intermittent (separate active bursts)."))
        return BEHAVIOUR_INTERMITTENT, supporting, limiting
    if n_temporal and spans and all(span >= PERSISTENT_SPAN_FRACTION for span in spans):
        supporting.append(_ev(
            "persistent_activity",
            f"The component stays active over at least {_fmt(PERSISTENT_SPAN_FRACTION * 100, 2)} % of the analysed window in every member with time-frequency evidence.",
            min_span_fraction=min(spans), threshold=PERSISTENT_SPAN_FRACTION))
        return BEHAVIOUR_SUSTAINED, supporting, limiting
    return BEHAVIOUR_INSUFFICIENT, supporting, limiting


# ---------------------------------------------------------------- the classifier
def classify_component(component: dict, signals: list[dict]) -> dict:
    """Interpret ONE cross-signal component. `component` is a `group_components` result; `signals` the analysed
    signal dicts it was grouped from (each with `window_start_s` / `window_end_s`, `candidates`, `representation`
    and optional `nominal_frequency_hz` / `nominal_frequency_assumed`). Nothing is recomputed from samples."""
    members = component["members"]
    frequency = component["representative_frequency_hz"]
    meta = [cs.signal_by_index(signals, m["signal_index"]) for m in members]
    types = set(component["signal_types"])
    distinct = component["distinct_measurement_count"]
    recordings = component["recording_count"]
    warn_codes = {w["code"] for w in component["warnings"]}
    reason_codes = {r["code"] for r in component["reasons"]}
    overlap = "temporal_overlap" in reason_codes
    damping_conflict = bool(warn_codes & {"damping_behaviour_differs", "decay_rates_differ_materially"})
    compared_without = max(0, len(signals) - component["signal_count"])
    em_types = sorted(types & ELECTROMECHANICAL_SIGNAL_TYPES)
    electrical_types = sorted(types & ELECTRICAL_SIGNAL_TYPES)
    nominal = next((s["nominal_frequency_hz"] for s in meta if s.get("nominal_frequency_hz")), None)
    nominal_assumed = nominal is None or any(s.get("nominal_frequency_assumed") for s in meta)
    nominal_hz = nominal if nominal is not None else ASSUMED_NOMINAL_FREQUENCY_HZ

    temporal = _temporal_facts(members, signals)
    behaviour, behaviour_support, behaviour_limits = _behaviour(members, temporal)

    # ---- facts that are true of the component regardless of the family (supporting / limiting building blocks)
    in_em_band = ELECTROMECHANICAL_BAND_HZ[0] <= frequency <= ELECTROMECHANICAL_BAND_HZ[1]
    in_inter_area = INTER_AREA_BAND_HZ[0] <= frequency <= INTER_AREA_BAND_HZ[1]
    in_local = LOCAL_BAND_HZ[0] <= frequency <= LOCAL_BAND_HZ[1]
    sub_synchronous_band = SUBSYNCHRONOUS_MIN_HZ <= frequency < nominal_hz
    in_control_band = CONTROL_BAND_HZ[0] <= frequency < CONTROL_BAND_HZ[1]
    narrow = _narrowness(members, signals)

    facts_support: list[dict] = []
    facts_limit: list[dict] = []
    if component["signal_count"] > 1:
        for reason in component["reasons"]:
            if reason["code"] in ("observed_in", "frequency_match", "multiple_signal_types", "multiple_recordings",
                                  "temporal_overlap", "damping_consistent"):
                facts_support.append(reason)
    else:
        facts_limit.append(_ev(
            "single_signal_only",
            "Observed in one signal only" + (" (other compared signals do not contain it)" if compared_without else "")
            + "; this is a valid detection but offers no cross-signal corroboration.", compared_without=compared_without))
    if component["signal_count"] > 1 and recordings < 2:
        facts_limit.append(_ev("single_recording", "All members come from one recording.", recordings=recordings))
    for warning in component["warnings"]:
        if warning["code"] in ("derived_from_same_source", "no_temporal_overlap", "damping_behaviour_differs", "decay_rates_differ_materially"):
            facts_limit.append(warning)
    if any(s.get("representation") == "rms_magnitude" for s in meta):
        facts_limit.append(_ev(
            "rms_representation",
            "At least one member was analysed through the RMS-magnitude representation: only the envelope of the quantity is seen, "
            "not its instantaneous waveform.", members=sum(1 for s in meta if s.get("representation") == "rms_magnitude")))

    # ---- hypotheses ----------------------------------------------------------------------------
    hypotheses: list[dict] = []

    # Electromechanical family.
    dynamic = behaviour in (BEHAVIOUR_RINGDOWN, BEHAVIOUR_DECAYING, BEHAVIOUR_GROWING)
    em_dims = {
        "frequency_in_electromechanical_range": in_em_band, "relevant_signal_type": bool(em_types),
        "dynamic_response": dynamic, "multiple_measurements": distinct >= 2, "temporal_overlap": overlap,
    }
    if in_em_band and em_types and dynamic:
        probable = distinct >= 2 and overlap and not damping_conflict and behaviour != BEHAVIOUR_GROWING
        support = [
            _ev("frequency_in_electromechanical_range",
                f"{_fmt(frequency, 4)} Hz lies in the conventional electromechanical range "
                f"({_fmt(ELECTROMECHANICAL_BAND_HZ[0], 2)}–{_fmt(ELECTROMECHANICAL_BAND_HZ[1], 2)} Hz); this range overlaps other mechanisms and is supporting evidence only.",
                frequency_hz=frequency),
            _ev("relevant_signal_types", f"Detected in {', '.join(em_types)} signal(s), quantities that carry electromechanical swing information.", types=",".join(em_types)),
        ]
        if distinct >= 2:
            support.append(_ev("multiple_measurements", f"Detected in {distinct} distinct measurements.", distinct_measurements=distinct))
        hypotheses.append({
            "code": TYPE_ELECTROMECHANICAL, "level": LEVEL_PROBABLE if probable else LEVEL_POSSIBLE, "dims": em_dims,
            "supporting": support, "limiting": [] if probable else [_ev(
                "family_corroboration_limited",
                "The electromechanical family is raised on its minimum requirement; corroboration across distinct measurements with overlapping, "
                "mutually consistent activity is missing or contradicted.", distinct_measurements=distinct, temporal_overlap=overlap,
                damping_conflict=damping_conflict)],
        })

    # Forced / sustained.
    if behaviour == BEHAVIOUR_SUSTAINED:
        support = []
        if narrow is not None and narrow["narrow"]:
            support.append(_ev("narrow_component", f"The component is narrow (spectral base {_fmt(narrow['base_bins'], 3)} bins).", base_bins=narrow["base_bins"]))
        if distinct >= 2:
            support.append(_ev("multiple_measurements", f"Detected in {distinct} distinct measurements.", distinct_measurements=distinct))
        hypotheses.append({
            "code": TYPE_FORCED_SUSTAINED, "level": LEVEL_POSSIBLE,
            "dims": {"sustained_behaviour": True, "narrow_component": bool(narrow and narrow["narrow"]), "multiple_measurements": distinct >= 2},
            "supporting": support, "limiting": [_ev("forcing_source_not_identified", "Source of forcing is not identified.")] + ([_ev(
                "component_not_narrow",
                f"The spectral base of the component is {_fmt(narrow['base_bins'], 3)} bins wide (narrow <= {_fmt(NARROW_BASE_BINS, 3)}), "
                "so it is not clearly a single narrow line.", base_bins=narrow["base_bins"])] if narrow is not None and not narrow["narrow"] else []),
        })

    # Control / converter interaction (and its refinement, sub-synchronous oscillation).
    control_dims = {
        "frequency_in_control_range": in_control_band, "electrical_signal_involvement": bool(electrical_types),
        "persistent_or_growing": behaviour in (BEHAVIOUR_SUSTAINED, BEHAVIOUR_GROWING),
        "multiple_measurements": distinct >= 2, "temporal_overlap": overlap,
    }
    if all(control_dims.values()):
        control_support = [
            _ev("electrical_signal_involvement", f"Present in electrical quantities: {', '.join(electrical_types)}.", types=",".join(electrical_types)),
            _ev("persistent_or_growing_behaviour", f"The component is {'growing' if behaviour == BEHAVIOUR_GROWING else 'sustained'}, a control-like temporal behaviour.", behaviour=behaviour),
            _ev("multiple_measurements", f"Detected in {distinct} distinct measurements.", distinct_measurements=distinct),
        ]
        control_limits = [_ev(
            "no_converter_metadata",
            "No plant, converter or controller metadata (PCS / PPC / IBR association) is available, so the interaction cannot be attributed.")]
        hypotheses.append({"code": TYPE_CONTROL_CONVERTER, "level": LEVEL_POSSIBLE, "dims": control_dims,
                           "supporting": control_support, "limiting": control_limits})
        sso_dims = dict(control_dims, frequency_below_nominal=sub_synchronous_band, multiple_recordings=recordings >= 2)
        if sub_synchronous_band and recordings >= 2:
            hypotheses.append({
                "code": TYPE_SUB_SYNCHRONOUS, "level": LEVEL_POSSIBLE, "dims": sso_dims,
                "supporting": control_support + [
                    _ev("frequency_below_nominal", f"{_fmt(frequency, 4)} Hz is below the nominal {_fmt(nominal_hz, 3)} Hz.", frequency_hz=frequency, nominal_frequency_hz=nominal_hz),
                    _ev("coherent_across_recordings", f"The component is present in {recordings} recordings.", recordings=recordings),
                ],
                "limiting": control_limits + [_ev(
                    "network_context_unavailable", "Network context (series compensation, plant topology) is not available to the analysis.")],
            })

    # ---- selection -------------------------------------------------------------------------------
    primary, alternatives = _select(hypotheses)
    unresolved_reason: dict | None = None
    if primary is None:
        if hypotheses:
            unresolved_reason = _ev(
                "multiple_families_plausible",
                "More than one family remains equally plausible: " + ", ".join(_TYPE_LABELS[h["code"]] for h in alternatives) + ".",
                families=",".join(h["code"] for h in alternatives))
        else:
            unresolved_reason = _ev(
                "no_family_requirements_met",
                "No family's requirement is met by the available evidence (frequency, signal types, distinct measurements, temporal and damping behaviour).")

    # ---- result ----------------------------------------------------------------------------------
    descriptors: list[dict] = []
    if sub_synchronous_band:
        descriptors.append({
            "code": DESCRIPTOR_HIGHER_FREQUENCY, "label": f"Higher-frequency oscillatory component detected at {_fmt(frequency, 4)} Hz",
            "message": "It lies above the electromechanical range; this describes the frequency only and does not identify a mechanism.",
            "values": {"frequency_hz": frequency, "nominal_frequency_hz": nominal_hz},
        })

    supporting = list(facts_support) + list(behaviour_support)
    limiting = list(facts_limit) + list(behaviour_limits)
    warnings: list[dict] = []
    if nominal_assumed and (sub_synchronous_band or in_control_band or primary is not None and primary["code"] == TYPE_SUB_SYNCHRONOUS):
        limiting.append(_ev("nominal_frequency_assumed", f"The nominal frequency was not declared; {_fmt(ASSUMED_NOMINAL_FREQUENCY_HZ, 3)} Hz is assumed for the sub-synchronous comparison.",
                            nominal_frequency_hz=ASSUMED_NOMINAL_FREQUENCY_HZ))

    if sub_synchronous_band and not (primary is not None and primary["code"] == TYPE_SUB_SYNCHRONOUS):
        limiting.append(_ev(
            "frequency_alone_not_sso",
            f"The component lies below the nominal {_fmt(nominal_hz, 3)} Hz fundamental, but frequency alone does not establish sub-synchronous oscillation.",
            frequency_hz=frequency, nominal_frequency_hz=nominal_hz))

    subtype = None
    if primary is not None:
        supporting += primary["supporting"]
        limiting += primary["limiting"]
        if primary["code"] == TYPE_ELECTROMECHANICAL:
            subtype, sub_support, sub_limit, sub_alt = _em_subtype(
                frequency, in_inter_area, in_local, distinct, recordings, overlap, damping_conflict, bool(em_types), behaviour, compared_without)
            supporting += sub_support
            limiting += sub_limit
            alternatives += sub_alt
        level = primary["level"]
        probable_type = {"code": primary["code"], "label": _type_label(primary["code"], level), "subtype": subtype}
        hierarchy = ["oscillatory_component", primary["code"]] + ([subtype["code"]] if subtype else [])
        dims = primary["dims"]
    else:
        level = LEVEL_UNRESOLVED
        if behaviour == BEHAVIOUR_INSUFFICIENT and distinct < 2 and not hypotheses:
            level = LEVEL_INSUFFICIENT
        limiting.append(unresolved_reason)
        probable_type = {"code": TYPE_UNRESOLVED, "label": INSUFFICIENT_LABEL if level == LEVEL_INSUFFICIENT else UNRESOLVED_LABEL, "subtype": None}
        hierarchy = ["oscillatory_component"]
        dims = {}
        if not in_em_band:
            limiting.append(_ev(
                "frequency_outside_electromechanical_range",
                f"{_fmt(frequency, 4)} Hz is outside the conventional electromechanical range; the frequency band overlaps several possible mechanisms.",
                frequency_hz=frequency))
        else:
            limiting.append(_ev(
                "frequency_band_overlaps_mechanisms",
                "The frequency band overlaps several possible mechanisms and does not identify one by itself.", frequency_hz=frequency))

    limiting = _unique(limiting)
    return {
        "component_id": component["id"],
        "component_frequency_hz": frequency,
        "behaviour_classification": {"code": behaviour, "label": BEHAVIOUR_LABELS[behaviour]},
        "probable_type": probable_type,
        "classification_level": level,
        "hierarchy": hierarchy,
        "descriptors": descriptors,
        "supporting_evidence": _unique(supporting),
        "limiting_evidence": limiting,
        "alternatives": alternatives,
        "warnings": warnings,
        "evidence_dimensions": dims,
    }


def _unique(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item is None or item["code"] in seen:
            continue
        seen.add(item["code"])
        out.append(item)
    return out


def _type_label(code: str, level: str) -> str:
    prefix = "Probable" if level == LEVEL_PROBABLE else "Possible"
    return f"{prefix} {_TYPE_LABELS[code]}"


def _narrowness(members: list[dict], signals: list[dict]) -> dict | None:
    """Narrow when the candidate's Welch base is at most NARROW_BASE_BINS wide in every member that reports its bases."""
    widths = []
    for m in members:
        signal = cs.signal_by_index(signals, m["signal_index"])
        c = _candidate_of(signal, m)
        if not c or c.get("left_base_hz") is None or c.get("right_base_hz") is None or not signal.get("bin_spacing_hz"):
            continue
        widths.append((c["right_base_hz"] - c["left_base_hz"]) / signal["bin_spacing_hz"])
    if not widths:
        return None
    widest = max(widths)
    return {"narrow": widest <= NARROW_BASE_BINS, "base_bins": widest}


def _select(hypotheses: list[dict]) -> tuple[dict | None, list[dict]]:
    """Pick the primary hypothesis or none (unresolved). Returns (primary, alternatives as wire dicts)."""
    if not hypotheses:
        return None, []
    top_rank = max(_LEVEL_RANK[h["level"]] for h in hypotheses)
    top = [h for h in hypotheses if _LEVEL_RANK[h["level"]] == top_rank]
    top_codes = {h["code"] for h in top}
    refined = set().union(*(_REFINES.get(code, set()) & top_codes for code in top_codes))
    top = [h for h in top if h["code"] not in refined]
    if len(top) == 1:
        primary = top[0]
        others = [h for h in hypotheses if h is not primary]
        return primary, [_alternative(h, "refined_by_primary" if h["code"] in refined else "lower_level") for h in others]
    return None, [_alternative(h, "refined_by_alternative" if h["code"] in refined else "equally_plausible") for h in hypotheses]


def _alternative(h: dict, relation: str) -> dict:
    return {
        "code": h["code"], "label": _type_label(h["code"], h["level"]), "level": h["level"], "relation": relation,
        "consistency": "consistent", "reasons": h["supporting"], "limitations": h["limiting"],
    }


def _em_subtype(frequency, in_inter_area, in_local, distinct, recordings, overlap, damping_conflict, relevant, behaviour, compared_without):
    """Provisional inter-area / local subtype of an electromechanical result. Never definitive: phase / mode-shape evidence is absent.

    Only the inter-area reading can become the *possible subtype*: it rests on positive evidence (the same component in several
    distinct measurements across recordings). A local reading would rest on the ABSENCE of the component elsewhere -- which is not
    proof of locality -- so it is never positively offered: without inter-area evidence the subtype is reported as unresolved in
    neutral wording, and beside a possible inter-area subtype a local mode is listed only as a not-excluded alternative."""
    support: list[dict] = []
    limit: list[dict] = []
    alternatives: list[dict] = []
    subtype = None
    inter_area_ok = in_inter_area and distinct >= 2 and recordings >= 2 and overlap and relevant and not damping_conflict
    local_limits = [_ev(
        "alternative_not_excluded",
        "A local or plant-related mode cannot be excluded without phase/mode-shape or location evidence"
        + ("." if in_local else "; the frequency is below the conventional local range, so this is the weaker reading."))]
    if inter_area_ok:
        subtype = {"code": SUBTYPE_INTER_AREA, "label": "Possible " + _SUBTYPE_LABELS[SUBTYPE_INTER_AREA], "level": LEVEL_POSSIBLE}
        support.append(_ev(
            "inter_area_compatible",
            f"Frequency in the inter-area-compatible range, observed in {distinct} distinct measurements across {recordings} recordings "
            "with overlapping activity and no contradictory damping.", frequency_hz=frequency, distinct_measurements=distinct, recordings=recordings))
        limit.append(_ev("phase_mode_shape_unavailable",
                         "Inter-area classification is provisional because relative phase/mode-shape evidence is not yet available."))
        limit.append(_ev("location_relationship_unknown",
                         "Recording locations are not proven to represent different grid areas (no station / area metadata is used)."))
        alternatives.append({
            "code": SUBTYPE_LOCAL, "label": "Possible " + _SUBTYPE_LABELS[SUBTYPE_LOCAL], "level": LEVEL_POSSIBLE, "relation": "subtype_alternative",
            "consistency": "consistent" if in_local else "weaker", "reasons": [], "limitations": local_limits,
        })
    else:
        limit.append(_ev(
            "subtype_unresolved",
            "Electromechanical subtype unresolved — local or inter-area cannot be distinguished with the available evidence "
            "(relative phase/mode-shape evidence is not available and the location relationship of the measurements is unknown)."))
        if compared_without:
            limit.append(_ev(
                "local_not_confirmed",
                f"Absence from the {compared_without} other compared signal(s) is not proof of locality.", compared_without=compared_without))
    return subtype, support, limit, alternatives
