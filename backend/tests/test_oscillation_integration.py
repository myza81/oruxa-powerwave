"""Oscillation Analysis -- integration of Mode Shape + Coherence into the interpretation (DEC-182 [PROPOSAL]).

Domain tests feed the REAL structured results of `mode_shape.analyse_quantity_group` and `coherence.analyse_component` (built from synthetic signals
of known phase and relationship) into `classify_component`; service / API tests run the whole chain and the synchronization model. Nothing here
uses an AI, a probability or a confidence, and nothing here identifies a source, a cause or a grid area.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain import cross_signal_evidence as cs
from app.domain import coherence as co
from app.domain import mode_shape as ms
from app.domain import oscillation_classification as oc
from app.domain import oscillation_integration as oi
from app.main import create_app
from app.services.oscillation_interpretation_service import compute_interpretation
from tests.test_oscillation_classification import _dmp, _sig
from tests.test_oscillation_coherence import _cm, _noise, _sin
from tests.test_oscillation_mode_shape import Env, F, WS, _entry, _mem, _ring, _source, _srv_t

FS = 20.0
LONG = 120.0


def _t(duration=LONG, fs=FS):
    return np.arange(int(round(duration * fs))) / fs


def _cos(t, phase_deg, amplitude=1.0, f=F, alpha=0.0):
    return amplitude * np.exp(-alpha * t) * np.cos(2 * np.pi * f * t + np.deg2rad(phase_deg))


def _shape(phase_deg, *, shared=False, duration=LONG, noise=0.02, quantity="Active Power", ramp_deg=0.0):
    """A real mode-shape component for two signals of one quantity with a known relative phase."""
    t = _t(duration)
    ramp = ramp_deg * t / duration
    x = _cos(t, 0.0) + _noise(t.size, noise, 1)
    y = _cos(t, phase_deg + ramp, 0.8) + _noise(t.size, noise, 2)
    roots = {"src::P"} if shared else None
    group = ms.analyse_quantity_group(
        quantity_type=quantity, unit="MW", members=[_mem(0, t, x, prominence=30.0, roots=roots), _mem(1, t, y, roots=roots, origin="calculated" if shared else "raw")],
        representative_frequency_hz=F, tolerance_hz=0.05, neighbour_frequencies_hz=[])
    return {"component_id": 1, "groups": [group]}


def _coherence(phase_deg, *, related=True, shared=False, duration=LONG, quantities=(("Active Power", "MW"), ("Active Power", "MW"))):
    t = _t(duration)
    x = _sin(t) + _noise(t.size, 0.05, 3)
    y = (_sin(t, phase_deg=phase_deg, amplitude=0.8) if related else 0.0 * t) + _noise(t.size, 0.05 if related else 1.0, 4)
    roots = {"src::P"} if shared else None
    members = [_cm(0, t, x, quantity=quantities[0], roots=roots), _cm(1, t, y, quantity=quantities[1], roots=roots, origin="calculated" if shared else "raw")]
    result = co.analyse_component(members=members, reference_index=0, frequency_hz=F, phase_by_member={1: phase_deg})
    return {"component_id": 1, **result}


def _pair(coherence, chance=0.632, *, kind="same_variable", status="ok", **extra):
    p = {"status": status, "relationship_type": kind, "reference_index": 0, "member_index": 1, "reference_signal": "S0", "member_signal": "S1",
         "coherence": coherence, "chance_level": chance, "coherence_frequency_hz": 0.4125, "warnings": [], "message": extra.pop("message", None)}
    p.update(extra)
    return p


def _comp(pairs=None, **extra):
    return {"component_id": 1, "pairs": pairs or [], "other_pairs": [], **extra}


def _signals():
    return [_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB", damping=_dmp(alpha=0.3))]


def _interpret(evidence, signals=None):
    signals = signals or _signals()
    comps = cs.group_components(signals)
    assert len(comps) == 1
    return oc.classify_component(comps[0], signals, evidence)


def _codes(items):
    return [i["code"] for i in items]


def _text(r):
    return " ".join(i["message"] for k in ("supporting_evidence", "limiting_evidence", "contradictory_evidence", "unavailable_evidence") for i in r[k])


# ------------------------------------------------------------------ coherence level (the transparent margin) ----

class TestCoherenceLevel:
    def test_below_marginal_and_clear_use_the_headroom_above_the_chance_level(self):
        chance = 0.632
        clear = chance + oi.COHERENCE_CLEAR_HEADROOM_FRACTION * (1 - chance)
        assert clear == pytest.approx(0.816)
        assert oi.coherence_level({"coherence": 0.40, "chance_level": chance})["level"] == oi.COHERENCE_BELOW
        assert oi.coherence_level({"coherence": chance, "chance_level": chance})["level"] == oi.COHERENCE_BELOW      # equal is not above
        assert oi.coherence_level({"coherence": 0.70, "chance_level": chance})["level"] == oi.COHERENCE_MARGINAL
        assert oi.coherence_level({"coherence": clear - 1e-6, "chance_level": chance})["level"] == oi.COHERENCE_MARGINAL
        assert oi.coherence_level({"coherence": clear, "chance_level": chance})["level"] == oi.COHERENCE_CLEAR
        assert oi.coherence_level({"coherence": 0.91, "chance_level": chance})["level"] == oi.COHERENCE_CLEAR
        assert oi.coherence_level({"coherence": 0.9, "chance_level": None})["level"] == oi.COHERENCE_UNKNOWN

    def test_the_margin_scales_with_the_chance_level(self):
        lv = oi.coherence_level({"coherence": 0.6, "chance_level": 0.35})
        assert lv["clear_threshold"] == pytest.approx(0.675) and lv["level"] == oi.COHERENCE_MARGINAL
        assert oi.coherence_level({"coherence": 0.7, "chance_level": 0.35})["level"] == oi.COHERENCE_CLEAR


# ------------------------------------------------------------------ the wording hierarchy ----

class TestHierarchy:
    def test_weak_evidence_no_mode_shape_and_no_coherence(self):
        """A: a multi-recording low-frequency component with neither: possible electromechanical, subtype unresolved, spatial evidence unavailable."""
        r = _interpret({"mode_shape": None, "coherence": None})
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["probable_type"]["subtype"] is None
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE
        assert "subtype_unresolved" in _codes(r["limiting_evidence"]) and "spatial_evidence_not_computed" in _codes(r["limiting_evidence"])
        assert "Electromechanical subtype unresolved — local or inter-area cannot be distinguished with the available evidence." in _text(r)
        # ONE concise statement, not a second differently worded copy of it
        assert sum("local or inter-area" in i["message"] for i in r["limiting_evidence"]) == 1 and "spatial_evidence_unavailable" not in _codes(r["limiting_evidence"])
        assert _text(r).count("local or inter-area") == 1

    def test_some_spatial_evidence_phase_without_coherence(self):
        """B: stable relative phase across distinct measurements, coherence unavailable: consistent with a spatial mode; inter-area only possible."""
        r = _interpret({"mode_shape": _shape(165.0), "coherence": None})
        sub = r["probable_type"]["subtype"]
        assert sub["code"] == "inter_area" and sub["label"] == oi.SUBTYPE_POSSIBLE_LABEL and sub["level"] == "possible"
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_CONSISTENT
        assert "stable_relative_phase" in _codes(r["supporting_evidence"]) and oi.TEXT_PHASE_ONLY in _text(r)
        assert "location_relationship_unknown" in _codes(r["limiting_evidence"])
        assert [a["code"] for a in r["alternatives"]] == ["local"] and r["alternatives"][0]["consistency"] == "weaker"
        assert "confirmed" not in _text(r).lower()

    def test_stronger_phase_one_evidence_phase_and_clear_coherence(self):
        """C: stable phase + meaningful separation + same-variable coherence clearly above the chance level + distinct measurements."""
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _coherence(165.0)})
        sub = r["probable_type"]["subtype"]
        assert sub["label"] == oi.SUBTYPE_PROVISIONAL_LABEL and sub["code"] == "inter_area"
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_SUPPORTED and r["interpretation_strength"]["label"] == "Supported (provisional)"
        text = _text(r)
        assert oi.TEXT_PHASE_AND_COHERENCE in text
        assert "supports a provisional inter-area interpretation" in text and "does not independently prove" in text
        assert "same_variable_coherence" in _codes(r["supporting_evidence"])
        assert "clearly above" in text
        assert r["spatial_evidence"]["mode_shape"]["pattern"] == "anti_phase" and r["spatial_evidence"]["coherence"]["weakest_level"] == oi.COHERENCE_CLEAR
        for word in ("confirmed", "probability", "confidence"):
            assert word not in text.lower().replace("not independently", "")
        assert r["classification_level"] == oc.LEVEL_PROBABLE                 # DEC-179 level logic is unchanged

    def test_intermediate_phase_separation_is_also_a_meaningful_separation(self):
        r = _interpret({"mode_shape": _shape(95.0), "coherence": _coherence(95.0)})
        assert r["probable_type"]["subtype"]["code"] == "inter_area" and r["spatial_evidence"]["mode_shape"]["pattern"] == "intermediate"


class TestPhaseAndCoherenceInteraction:
    def test_near_in_phase_is_not_local_and_not_inter_area(self):
        r = _interpret({"mode_shape": _shape(8.0), "coherence": _coherence(8.0)})
        assert r["probable_type"]["subtype"] is None and r["alternatives"] == []
        assert "in_phase_response" in _codes(r["supporting_evidence"]) and "Absence of opposing phase is not proof of a local mode" in _text(r)
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_CONSISTENT
        assert "local mode" not in r["probable_type"]["label"].lower() and "Possible local" not in str(r["probable_type"])
        assert "subtype_unresolved" in _codes(r["limiting_evidence"])

    @pytest.mark.parametrize("coherence, level", [(0.40, oi.COHERENCE_BELOW), (0.70, oi.COHERENCE_MARGINAL)])
    def test_stable_phase_with_weak_or_marginal_coherence_keeps_the_phase_but_is_not_upgraded(self, coherence, level):
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _comp([_pair(coherence)])})
        assert "stable_relative_phase" in _codes(r["supporting_evidence"])                   # the phase result is retained
        weak = next(i for i in r["contradictory_evidence"] if i["code"] == "coherence_weak_for_phase")
        assert weak["message"] == oi.TEXT_COHERENCE_WEAK_FOR_PHASE and weak["values"]["level"] == level
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_CONSISTENT              # not supported_provisional
        assert r["probable_type"]["subtype"]["label"] == oi.SUBTYPE_POSSIBLE_LABEL
        assert oi.TEXT_PHASE_AND_COHERENCE not in _text(r)

    def test_a_phase_with_unavailable_coherence_is_not_invalidated(self):
        refused = _pair(None, None, status="insufficient_evidence", message="Coherence unavailable — the shared 7 s interval is too short to resolve a 0.4 Hz component reliably. "
                                                                          "Each Welch segment contains only 0.62 cycles; at least 1.5 cycles are required.", reason_code="too_few_cycles")
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _comp([refused])})
        assert r["probable_type"]["subtype"]["label"] == oi.SUBTYPE_POSSIBLE_LABEL and "coherence_weak_for_phase" not in _codes(r["contradictory_evidence"])
        un = next(i for i in r["unavailable_evidence"] if i["code"] == "coherence_unavailable")
        assert "0.62 cycles" in un["message"] and un["values"]["reason_code"] == "too_few_cycles"       # the dynamic text is passed through, not rewritten

    def test_coherence_alone_supports_a_shared_relationship_but_no_phase_pattern(self):
        refused_shape = {"component_id": 1, "groups": [{"quantity_type": "Active Power", "status": "insufficient_evidence", "reason_code": "too_few_cycles",
                                                        "message": "The common interval (7 s) holds 2.8 cycles; at least 3 are needed.", "members": [],
                                                        "distinct_measurement_count": 2, "phase_pattern": {"code": "unavailable", "member_bands": {}}}]}
        r = _interpret({"mode_shape": refused_shape, "coherence": _comp([_pair(0.93)])})
        assert "coherence_shared_dynamic" in _codes(r["supporting_evidence"]) and oi.TEXT_COHERENCE_ONLY in _text(r)
        assert r["probable_type"]["subtype"] is None and r["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE
        assert r["spatial_evidence"]["mode_shape"]["pattern"] is None and "stable_relative_phase" not in _codes(r["supporting_evidence"])
        assert "mode_shape_unavailable" in _codes(r["unavailable_evidence"])

    def test_cross_variable_coherence_supports_dynamics_but_never_a_subtype(self):
        r = _interpret({"mode_shape": {"component_id": 1, "groups": []}, "coherence": _comp([_pair(0.97, kind="cross_variable")])})
        assert "cross_variable_coherence" in _codes(r["supporting_evidence"]) and oi.TEXT_CROSS_VARIABLE in _text(r)
        assert r["probable_type"]["subtype"] is None and "same_variable_coherence" not in _codes(r["supporting_evidence"])
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE
        # and cross-variable coherence cannot rescue a refused same-variable phase either
        with_phase = _interpret({"mode_shape": _shape(165.0), "coherence": _comp([_pair(0.97, kind="cross_variable")])})
        assert with_phase["interpretation_strength"]["code"] == oi.STRENGTH_CONSISTENT                  # not supported_provisional
        assert with_phase["probable_type"]["subtype"]["label"] == oi.SUBTYPE_POSSIBLE_LABEL

    def test_shared_provenance_cannot_create_spatial_evidence(self):
        r = _interpret({"mode_shape": _shape(180.0, shared=True), "coherence": _coherence(180.0, shared=True)})
        assert r["probable_type"]["subtype"] is None and r["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE
        assert "spatial_evidence_shared_provenance" in _codes(r["limiting_evidence"])
        assert "stable_relative_phase" not in _codes(r["supporting_evidence"]) and "same_variable_coherence" not in _codes(r["supporting_evidence"])
        assert r["spatial_evidence"]["mode_shape"]["status"] == "shared_provenance"

    def test_an_unstable_phase_is_a_contradiction_not_a_subtype(self):
        r = _interpret({"mode_shape": _shape(100.0, ramp_deg=170.0), "coherence": _coherence(100.0)})
        assert "phase_unstable" in _codes(r["contradictory_evidence"])
        assert r["probable_type"]["subtype"] is None and "stable_relative_phase" not in _codes(r["supporting_evidence"])

    def test_unrelated_signals_with_a_phase_are_not_upgraded(self):
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _coherence(165.0, related=False)})
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_CONSISTENT and any(i["code"] == "coherence_weak_for_phase" for i in r["contradictory_evidence"])


class TestShortEventAndUnavailable:
    def _refused(self):
        t = _t(7.0)
        shape = {"component_id": 1, "groups": [ms.analyse_quantity_group(
            quantity_type="Active Power", unit="MW", members=[_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 170))],
            representative_frequency_hz=F, tolerance_hz=0.05, neighbour_frequencies_hz=[])]}
        coh = {"component_id": 1, **co.analyse_component(members=[_cm(0, t, _cos(t, 0)), _cm(1, t, _cos(t, 170))], reference_index=0, frequency_hz=F)}
        assert shape["groups"][0]["status"] != "ok" and coh["pairs"][0]["status"] != "ok"
        return shape, coh

    def test_the_real_short_event_keeps_its_valid_evidence_and_says_spatial_evidence_is_insufficient(self):
        shape, coh = self._refused()
        with_evidence = _interpret({"mode_shape": shape, "coherence": coh})
        baseline = _interpret(None)
        assert with_evidence["probable_type"]["code"] == baseline["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL
        assert with_evidence["classification_level"] == baseline["classification_level"]          # nothing is downgraded
        assert with_evidence["behaviour_classification"] == baseline["behaviour_classification"]
        assert {"mode_shape_unavailable", "coherence_unavailable"} <= set(_codes(with_evidence["unavailable_evidence"]))
        text = _text(with_evidence)
        assert "too short" in text and "cycles" in text                                              # the dynamic refusal text is shown
        assert with_evidence["probable_type"]["subtype"] is None and "subtype_unresolved" in _codes(with_evidence["limiting_evidence"])
        assert with_evidence["contradictory_evidence"] == [] or all(c["code"] != "coherence_weak_for_phase" for c in with_evidence["contradictory_evidence"])
        for word in ("invalid", "false detection", "not credible", "unreliable"):
            assert word not in text.lower()
        assert {"observed_in", "frequency_match", "temporal_overlap"} <= set(_codes(with_evidence["supporting_evidence"]))    # the cross-signal evidence stays
        assert with_evidence["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE

    def test_no_stale_unavailable_wording_once_valid_results_exist(self):
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _coherence(165.0)})
        text = _text(r)
        assert "not yet available" not in text and "phase_mode_shape_unavailable" not in _codes(r["limiting_evidence"])
        assert "mode_shape_unavailable" not in _codes(r["unavailable_evidence"]) and "coherence_unavailable" not in _codes(r["unavailable_evidence"])
        assert "no phase, mode-shape, coherence or location evidence exists yet" not in str(oc.parameters())

    def test_without_evidence_the_dec_179_result_is_unchanged(self):
        r = _interpret(None)
        assert r["probable_type"]["subtype"]["label"] == "Possible inter-area electromechanical mode"
        assert "phase_mode_shape_unavailable" in _codes(r["limiting_evidence"])
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE and r["contradictory_evidence"] == [] and r["unavailable_evidence"] == []


class TestSingleSignalComponentInAnIntegratedComparison:
    def test_a_component_seen_in_one_signal_is_not_applicable_not_blanket_unavailable(self):
        single = [_sig(0, "MW-A", 0.40, recording="rA")]
        comp = cs.group_components(single)[0]
        r = oc.classify_component(comp, single, {"mode_shape": None, "coherence": None})
        codes = _codes(r["limiting_evidence"])
        assert "single_signal_only" in codes and "spatial_evidence_not_applicable" in codes and "subtype_unresolved" in codes
        text = _text(r)
        assert "relative phase/mode-shape evidence is not available" not in text and "not yet available" not in text
        assert "do not apply to it" in text and r["probable_type"]["subtype"] is None
        assert r["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE and r["spatial_evidence"]["not_applicable"] is True
        assert r["unavailable_evidence"] == []                       # nothing was refused: the methods simply need two signals

    def test_without_evidence_the_single_signal_card_keeps_its_dec_179_wording(self):
        single = [_sig(0, "MW-A", 0.40, recording="rA")]
        r = oc.classify_component(cs.group_components(single)[0], single)
        assert "relative phase/mode-shape evidence is not available" in _text(r) and "spatial_evidence_not_applicable" not in _codes(r["limiting_evidence"])


class TestScopeGuards:
    def test_frequency_still_never_decides_and_higher_frequency_is_not_sso_from_phase_or_coherence(self):
        signals = [_sig(0, "FREQ", 4.95, signal_type="Frequency", recording="rA"), _sig(1, "MW", 4.95, recording="rB")]
        r = _interpret({"mode_shape": _shape(170.0), "coherence": _coherence(170.0)}, signals)
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED and r["probable_type"]["subtype"] is None
        assert "sub_synchronous" not in str(r["probable_type"]) and "frequency_alone_not_sso" in _codes(r["limiting_evidence"])

    def test_a_sustained_coherent_component_does_not_identify_a_forcing_source(self):
        signals = [_sig(0, "MW-A", 0.9, recording="rA", damping=_dmp(behaviour="approximately_sustained", alpha=0.0)),
                   _sig(1, "MW-B", 0.9, recording="rB", damping=_dmp(behaviour="approximately_sustained", alpha=0.0))]
        r = _interpret({"mode_shape": _shape(150.0), "coherence": _coherence(150.0)}, signals)
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_SUSTAINED
        assert "forcing_source_not_identified" in str(r) or r["probable_type"]["code"] != oc.TYPE_FORCED_SUSTAINED

    def test_damping_conflict_is_not_overridden_by_spatial_evidence(self):
        signals = [_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB", damping=_dmp(behaviour="approximately_sustained", alpha=0.0))]
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _coherence(165.0)}, signals)
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_INCONSISTENT
        assert r["probable_type"]["subtype"] is None                                                 # DEC-179 rule: no inter-area beside a damping conflict
        assert "damping_behaviour_differs" in _codes(r["limiting_evidence"])

    def test_nothing_in_the_vocabulary_overclaims(self):
        r = _interpret({"mode_shape": _shape(165.0), "coherence": _coherence(165.0)})
        blob = str(r).lower()
        for word in ("confirmed", "probability", "confidence", "causes", "caused by", "source of the oscillation is"):
            assert word not in blob
        assert "does not independently prove" in blob and "no combined" not in blob


# ------------------------------------------------------------------ service ----

@pytest.fixture
def env():
    return Env()


def _interpret_service(env, entries, *, with_sync=True):
    return compute_interpretation(
        workspace_id=WS, entries=[{**e, "offset_s": 0.0} for e in entries], f_min_hz=0.1, f_max_hz=5.0, source_registry=env.sources,
        calc_registry=env.calc, sync_registry=env.sync if with_sync else None)


class TestService:
    def _two(self, env, *, alpha, phase, amp_b=3.1):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"MW A": _ring(t, F, 0.0, 4.0, alpha=alpha, seed=1)}, {"MW A": "Active Power"}))
        env.sources.add(_source("recB", t, {"MW B": _ring(t, F, phase, amp_b, alpha=alpha, seed=2)}, {"MW B": "Active Power"}))
        return _interpret_service(env, [_entry("recA", "MW A"), _entry("recB", "MW B")])

    def test_positive_inter_area_style_case(self, env):
        out = self._two(env, alpha=0.01, phase=172.0)
        it = out["components"][0]["interpretation"]
        assert it["probable_type"]["subtype"]["label"] == oi.SUBTYPE_PROVISIONAL_LABEL
        assert it["interpretation_strength"]["code"] == oi.STRENGTH_SUPPORTED
        assert {"stable_relative_phase", "same_variable_coherence"} <= set(_codes(it["supporting_evidence"]))
        assert it["unavailable_evidence"] == []
        assert out["mode_shape"]["components"][0]["groups"][0]["status"] == "ok" and out["coherence"]["components"][0]["pairs"][0]["status"] == "ok"
        assert "provisional inter-area interpretation" in _text(it)

    def test_phase_valid_but_coherence_unavailable_style_case(self, env):
        """A fast ringdown (decay 0.075 /s): the shared interval holds enough cycles for a phase but not for a coherence."""
        out = self._two(env, alpha=0.075, phase=172.0)
        it = out["components"][0]["interpretation"]
        assert out["mode_shape"]["components"][0]["groups"][0]["status"] == "ok"
        assert out["coherence"]["components"][0]["pairs"][0]["status"] == "insufficient_evidence"
        assert it["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL
        assert it["probable_type"]["subtype"]["label"] == oi.SUBTYPE_POSSIBLE_LABEL and it["interpretation_strength"]["code"] == oi.STRENGTH_CONSISTENT
        assert _codes(it["unavailable_evidence"]) == ["coherence_unavailable"] and "stable_relative_phase" in _codes(it["supporting_evidence"])
        assert "too short" in _text(it) and "Coherence unavailable" in _text(it)

    def test_the_real_short_event_style_case(self, env):
        """The owner's event: the shared active interval is so short that BOTH advanced methods refuse. The interpretation stays valid
        (electromechanical family, cross-signal evidence) and states that the spatial evidence is insufficient."""
        out = self._two(env, alpha=0.17, phase=172.0)
        shape = out["mode_shape"]["components"][0]["groups"][0]
        pair = out["coherence"]["components"][0]["pairs"][0]
        assert shape["status"] != "ok" and pair["status"] != "ok", (shape["status"], shape["message"], pair["message"])
        it = out["components"][0]["interpretation"]
        assert it["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and it["classification_level"] in (oc.LEVEL_PROBABLE, oc.LEVEL_POSSIBLE)
        assert {"mode_shape_unavailable", "coherence_unavailable"} <= set(_codes(it["unavailable_evidence"]))
        assert it["probable_type"]["subtype"] is None and it["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE
        assert {"observed_in", "frequency_match", "temporal_overlap"} <= set(_codes(it["supporting_evidence"]))
        text = _text(it)
        assert "too short" in text and "Electromechanical subtype unresolved" in text
        assert it["contradictory_evidence"] == []

    def _two_with_extra_single(self, env, alpha=0.17):
        """The short event of the owner (two matched MW signals) plus a 1.2 Hz component that only the second signal carries."""
        t = _srv_t()
        env.sources.add(_source("recA", t, {"POWER UNIT NO.1": _ring(t, F, 0.0, 4.0, alpha=alpha, seed=1)}, {"POWER UNIT NO.1": "Active Power"}))
        extra = _ring(t, F, 172.0, 3.1, alpha=alpha, seed=2) + _ring(t, 1.2, 30.0, 2.5, alpha=0.05, seed=3)
        env.sources.add(_source("recB", t, {"POWER UNIT UNIT NO.2": extra}, {"POWER UNIT UNIT NO.2": "Active Power"}))
        return _interpret_service(env, [_entry("recA", "POWER UNIT NO.1"), _entry("recB", "POWER UNIT UNIT NO.2")])

    def test_one_matched_component_and_one_member_set_reach_all_three_consumers(self, env):
        """DEC-182 UAT: the interpretation, the cross-signal grouping, the mode shape and the coherence of one comparison are the SAME component
        with the SAME member set -- the interpretation never sees one signal where the others see two."""
        out = self._two_with_extra_single(env)
        matched = next(c for c in out["components"] if c["signal_count"] == 2)
        labels = {m["label"] for m in matched["members"]}
        assert labels == {"POWER UNIT NO.1", "POWER UNIT UNIT NO.2"}
        shape = next(c for c in out["mode_shape"]["components"] if c["component_id"] == matched["id"])
        coh = next(c for c in out["coherence"]["components"] if c["component_id"] == matched["id"])
        assert {m["label"] for g in shape["groups"] for m in g["members"]} == labels
        assert {p["reference_signal"] for p in coh["pairs"]} | {p["member_signal"] for p in coh["pairs"]} == labels
        assert shape["component_frequency_hz"] == matched["representative_frequency_hz"] == coh["component_frequency_hz"]
        # the single-signal component is NOT given a mode shape / coherence block (they need two signals)
        singles = [c for c in out["components"] if c["signal_count"] == 1]
        assert singles and all(c["id"] not in {x["component_id"] for x in out["mode_shape"]["components"]} for c in singles)
        # the interpretation of the matched component reports two distinct measurements and BOTH structured refusals, verbatim
        it = matched["interpretation"]
        assert matched["distinct_measurement_count"] == 2 and "single_signal_only" not in _codes(it["limiting_evidence"])
        assert {"observed_in", "multiple_measurements"} <= set(_codes(it["supporting_evidence"]))
        assert it["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and it["interpretation_strength"]["code"] == oi.STRENGTH_POSSIBLE
        assert it["probable_type"]["subtype"] is None
        group, pair = shape["groups"][0], coh["pairs"][0]
        assert group["status"] != "ok" and pair["status"] != "ok"
        un = {u["code"]: u for u in it["unavailable_evidence"]}
        assert group["message"] in un["mode_shape_unavailable"]["message"] and pair["message"] in un["coherence_unavailable"]["message"]
        assert un["mode_shape_unavailable"]["values"]["reason_code"] == group["reason_code"]
        assert un["coherence_unavailable"]["values"]["reason_code"] == pair["reason_code"]
        assert "relative phase/mode-shape evidence is not available" not in _text(it)

    def test_the_single_signal_component_of_the_same_comparison_is_explicit_not_stale(self, env):
        out = self._two_with_extra_single(env)
        single = next(c for c in out["components"] if c["signal_count"] == 1)
        it = single["interpretation"]
        assert "single_signal_only" in _codes(it["limiting_evidence"]) and "spatial_evidence_not_applicable" in _codes(it["limiting_evidence"])
        assert "relative phase/mode-shape evidence is not available" not in _text(it) and it["unavailable_evidence"] == []

    def test_near_in_phase_case(self, env):
        it = self._two(env, alpha=0.01, phase=8.0)["components"][0]["interpretation"]
        assert it["probable_type"]["subtype"] is None and "in_phase_response" in _codes(it["supporting_evidence"])

    def test_a_single_signal_keeps_the_dec_179_behaviour(self, env):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"MW A": _ring(t, F, 0.0, 4.0, alpha=0.01, seed=1)}, {"MW A": "Active Power"}))
        out = _interpret_service(env, [_entry("recA", "MW A")])
        assert "mode_shape" not in out or out["mode_shape"] is None
        assert out["components"][0]["interpretation"]["spatial_evidence"] == {}

    def test_without_a_synchronization_registry_the_old_path_is_used(self, env):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"MW A": _ring(t, F, 0.0, 4.0, alpha=0.01, seed=1)}, {"MW A": "Active Power"}))
        env.sources.add(_source("recB", t, {"MW B": _ring(t, F, 172.0, 3.1, alpha=0.01, seed=2)}, {"MW B": "Active Power"}))
        out = _interpret_service(env, [_entry("recA", "MW A"), _entry("recB", "MW B")], with_sync=False)
        assert out["components"][0]["interpretation"]["probable_type"]["subtype"]["label"] == "Possible inter-area electromechanical mode"
        assert out.get("mode_shape") is None

    def test_the_analysis_chain_runs_once_per_signal(self, env, monkeypatch):
        """No duplicated spectrum / spectrogram / damping: one pass per signal serves interpretation, mode shape and coherence."""
        import app.services.oscillation_cross_signal_service as svc
        calls = {"spectrum": 0, "spectrogram": 0, "damping": 0}
        for key, name in (("spectrum", "compute_spectrum"), ("spectrogram", "compute_spectrogram"), ("damping", "compute_damping")):
            original = getattr(svc, name)

            def counted(*a, _o=original, _k=key, **kw):
                calls[_k] += 1
                return _o(*a, **kw)
            monkeypatch.setattr(svc, name, counted)
        self._two(env, alpha=0.01, phase=172.0)
        assert calls == {"spectrum": 2, "spectrogram": 2, "damping": 2}


class TestApi:
    URL = "/api/v1/workspaces/{ws}/oscillation-analysis/interpretation"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def _sig(self, src):
        return {"input": {"kind": "source", "source_id": src, "channel_name": "P"}, "representation": "native", "window_start_s": 0.0,
                "window_end_s": 159.98, "label": src, "offset_s": 99.0}

    def test_the_response_carries_the_integrated_evidence_and_the_new_fields(self, client):
        t = _srv_t()
        registry = client.app.state.workspace_registry
        registry.add(_source("recA", t, {"P": _ring(t, F, 0.0, 4.0, alpha=0.01, seed=41)}, {"P": "Active Power"}))
        registry.add(_source("recB", t, {"P": _ring(t, F, 172.0, 3.0, alpha=0.01, seed=42)}, {"P": "Active Power"}))
        r = client.post(self.URL.format(ws=WS), json={"signals": [self._sig("recA"), self._sig("recB")], "frequency_min_hz": 0.1, "frequency_max_hz": 5.0})
        assert r.status_code == 200, r.text
        body = r.json()
        it = body["components"][0]["interpretation"]
        assert it["interpretation_strength"] == {"code": "supported_provisional", "label": "Supported (provisional)"}
        assert set(it) >= {"supporting_evidence", "limiting_evidence", "contradictory_evidence", "unavailable_evidence", "spatial_evidence", "alternatives"}
        assert body["mode_shape"]["components"][0]["groups"][0]["status"] == "ok" and body["coherence"]["components"][0]["pairs"][0]["status"] == "ok"
        assert {"signal_analysis", "grouping", "mode_shape_and_coherence", "classification", "total"} <= set(body["timings_ms"])

    def test_a_single_signal_request_still_works(self, client):
        t = _srv_t()
        client.app.state.workspace_registry.add(_source("recA", t, {"P": _ring(t, F, 0.0, 4.0, alpha=0.01, seed=41)}, {"P": "Active Power"}))
        r = client.post(self.URL.format(ws=WS), json={"signals": [self._sig("recA")], "frequency_min_hz": 0.1, "frequency_max_hz": 5.0})
        assert r.status_code == 200, r.text
        assert r.json()["components"][0]["interpretation"]["interpretation_strength"]["code"] in ("possible", "detected", "unresolved")
