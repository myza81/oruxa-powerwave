"""Oscillation Analysis -- deterministic oscillation interpretation (DEC-179 [APPROVED]).

Domain tests hand-build the cross-signal evidence (so every rule and boundary is exact); service / API tests run
the real Welch + DEC-175 + STFT + DEC-177 + cross-signal chain on synthetic signals and check the interpretation
that comes back. Nothing here uses an AI, a probability or a phase / mode-shape quantity.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.domain import cross_signal_evidence as cs
from app.domain import oscillation_classification as oc
from app.main import create_app
from app.services.oscillation_cross_signal_service import compute_cross_signal
from tests.test_oscillation_cross_signal import _entry, _event, _run, registries  # noqa: F401  (fixture re-use)
from tests.test_oscillation_representation import WS, _active


# ------------------------------------------------------------------ domain helpers ----

WINDOW = 160.0


def _cand(freq, prominence=20.0, rank=1, cycles=50.0, base_bins=4.0, bin_hz=0.05):
    half = base_bins * bin_hz / 2.0
    return {"rank": rank, "frequency_hz": freq, "prominence_db": prominence, "cycles_observed": cycles, "psd": 1.0,
            "left_base_hz": freq - half, "right_base_hz": freq + half}


def _dmp(behaviour="decaying", alpha=0.2, zeta=0.03, status="available", reason_code=None):
    return {"status": status, "behaviour": behaviour, "decay_rate_per_s": alpha, "damping_ratio": zeta, "reason_code": reason_code, "message": ""}


def _tmp(start, end):
    return {"status": "ok", "start_s": start, "end_s": end, "active_slices": 5, "slice_count": 8, "active_fraction": 0.6, "active_threshold": 0.1}


def _sig(index, label, freq, *, signal_type="Active Power", recording="r1", roots=None, damping=_dmp(), temporal=_tmp(40.0, 120.0),
         bin_hz=0.05, origin="raw", representation="native", prominence=20.0, candidate=None, nominal=50.0, nominal_assumed=False):
    cand = candidate or _cand(freq, prominence, bin_hz=bin_hz)
    return {
        "index": index, "label": label, "signal_type": signal_type, "recording": recording, "origin": origin,
        "lineage_roots": roots if roots is not None else [f"{recording}::{label}"], "offset_s": 0.0, "bin_spacing_hz": bin_hz,
        "candidates": [cand] if cand is not None else [], "damping": {1: damping} if damping is not None else {},
        "temporal": {1: temporal} if temporal is not None else {}, "window_start_s": 0.0, "window_end_s": WINDOW,
        "representation": representation, "nominal_frequency_hz": nominal, "nominal_frequency_assumed": nominal_assumed,
    }


def _interpret(signals):
    comps = cs.group_components(signals)
    return [oc.classify_component(c, signals) for c in comps]


def _one(signals):
    out = _interpret(signals)
    assert len(out) == 1, out
    return out[0]


def _codes(items):
    return [i["code"] for i in items]


# ------------------------------------------------------------------ owner-style scenarios ----

class TestOwnerScenarios:
    def test_case_a_low_frequency_decaying_mode_in_two_mw_signals_across_two_recordings(self):
        r = _one([_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB", damping=_dmp(alpha=0.3))])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_RINGDOWN
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["classification_level"] == oc.LEVEL_PROBABLE
        assert r["probable_type"]["label"] == "Probable electromechanical oscillation"
        sub = r["probable_type"]["subtype"]
        assert sub["code"] == oc.SUBTYPE_INTER_AREA and sub["level"] == oc.LEVEL_POSSIBLE      # provisional, never definitive
        assert sub["label"] == "Possible inter-area electromechanical mode"
        assert "phase_mode_shape_unavailable" in _codes(r["limiting_evidence"])
        assert "location_relationship_unknown" in _codes(r["limiting_evidence"])
        lim = {i["code"]: i["message"] for i in r["limiting_evidence"]}
        assert lim["phase_mode_shape_unavailable"] == "Inter-area classification is provisional because relative phase/mode-shape evidence is not yet available."
        assert [a["code"] for a in r["alternatives"]] == [oc.SUBTYPE_LOCAL] and r["alternatives"][0]["consistency"] == "weaker"
        assert r["hierarchy"] == ["oscillatory_component", "electromechanical", "inter_area"]
        assert {"observed_in", "frequency_match", "temporal_overlap", "damping_consistent", "decaying_damping", "onset_observed"} <= set(_codes(r["supporting_evidence"]))

    def test_case_b_4_95_hz_in_mw_and_frequency_is_not_forced_into_control_interaction(self):
        r = _one([_sig(0, "FREQ", 4.95, signal_type="Frequency"), _sig(1, "MW", 4.95, signal_type="Active Power")])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED and r["classification_level"] == oc.LEVEL_UNRESOLVED
        assert r["probable_type"]["label"] == "Oscillation detected — type unresolved"
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_RINGDOWN
        assert [d["code"] for d in r["descriptors"]] == [oc.DESCRIPTOR_HIGHER_FREQUENCY]   # a frequency description, not a mechanism
        assert "no_family_requirements_met" in _codes(r["limiting_evidence"])
        assert "frequency_outside_electromechanical_range" in _codes(r["limiting_evidence"])
        assert {"observed_in", "multiple_signal_types"} <= set(_codes(r["supporting_evidence"]))   # the stronger cross-signal physical component

    def test_case_c_single_signal_1_15_hz_mw_is_a_possible_family_only_and_never_false(self):
        r = _one([_sig(0, "MW", 1.15)])
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["classification_level"] == oc.LEVEL_POSSIBLE
        assert r["probable_type"]["subtype"] is None                     # one signal with nothing to compare against: no subtype
        assert "single_signal_only" in _codes(r["limiting_evidence"]) and "subtype_unresolved" in _codes(r["limiting_evidence"])
        assert "false" not in " ".join(i["message"] for i in r["limiting_evidence"]).lower().replace("this is a valid detection", "")

    def test_single_signal_without_damping_or_time_evidence_is_insufficient_evidence(self):
        r = _one([_sig(0, "MW", 1.15, damping=None, temporal=None)])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED and r["classification_level"] == oc.LEVEL_INSUFFICIENT
        assert r["probable_type"]["label"] == "Oscillation detected — insufficient evidence to classify"
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_INSUFFICIENT


# ------------------------------------------------------------------ behaviour rules ----

class TestBehaviour:
    def test_ringdown_needs_a_quiet_lead_in(self):
        ring = _one([_sig(0, "MW", 1.15, temporal=_tmp(30.0, 100.0))])
        assert ring["behaviour_classification"]["code"] == oc.BEHAVIOUR_RINGDOWN
        from_start = _one([_sig(0, "MW", 1.15, temporal=_tmp(0.0, 100.0))])
        assert from_start["behaviour_classification"]["code"] == oc.BEHAVIOUR_DECAYING
        assert "onset_not_observed" in _codes(from_start["limiting_evidence"])

    def test_lead_in_boundary(self):
        at = _one([_sig(0, "MW", 1.15, temporal=_tmp(oc.ONSET_LEAD_FRACTION * WINDOW, 100.0))])
        below = _one([_sig(0, "MW", 1.15, temporal=_tmp(oc.ONSET_LEAD_FRACTION * WINDOW - 0.5, 100.0))])
        assert at["behaviour_classification"]["code"] == oc.BEHAVIOUR_RINGDOWN
        assert below["behaviour_classification"]["code"] == oc.BEHAVIOUR_DECAYING

    def test_growing_follows_the_damping_estimate(self):
        r = _one([_sig(0, "MW", 1.15, damping=_dmp("growing", alpha=-0.1, zeta=None))])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_GROWING and "growing_damping" in _codes(r["supporting_evidence"])

    def test_sustained_from_damping(self):
        r = _one([_sig(0, "MW", 1.15, damping=_dmp("approximately_sustained", 0.0, None))])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_SUSTAINED

    def test_sustained_from_persistence_when_damping_is_unavailable(self):
        r = _one([_sig(0, "MW", 1.15, damping=_dmp(status="insufficient_evidence", reason_code="near_noise_floor"), temporal=_tmp(2.0, 158.0))])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_SUSTAINED
        assert "persistent_activity" in _codes(r["supporting_evidence"]) and "damping_unavailable" in _codes(r["limiting_evidence"])

    def test_persistence_boundary(self):
        edge = _one([_sig(0, "MW", 1.15, damping=None, temporal=_tmp(0.0, oc.PERSISTENT_SPAN_FRACTION * WINDOW))])
        less = _one([_sig(0, "MW", 1.15, damping=None, temporal=_tmp(0.0, oc.PERSISTENT_SPAN_FRACTION * WINDOW - 1.0))])
        assert edge["behaviour_classification"]["code"] == oc.BEHAVIOUR_SUSTAINED
        assert less["behaviour_classification"]["code"] == oc.BEHAVIOUR_INSUFFICIENT

    def test_intermittent_when_the_damping_estimator_refused_it_as_intermittent(self):
        r = _one([_sig(0, "MW", 1.15, damping=_dmp(status="insufficient_evidence", reason_code="intermittent_component"))])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_INTERMITTENT
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED                  # intermittent never becomes a family on frequency alone

    def test_contradictory_damping_across_signals_is_reported_not_averaged(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA"), _sig(1, "MW-B", 0.4, recording="rB", damping=_dmp("growing", -0.1, None))])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_INCONSISTENT
        assert "damping_behaviour_differs" in _codes(r["limiting_evidence"])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED

    def test_missing_stft_keeps_the_behaviour_but_caps_the_level_and_says_so(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA", temporal=None), _sig(1, "MW-B", 0.4, recording="rB", temporal=None)])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_DECAYING          # onset cannot be established without the STFT
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["classification_level"] == oc.LEVEL_POSSIBLE   # no overlap evidence
        assert "limited_temporal_evidence" in _codes(r["limiting_evidence"])
        assert r["probable_type"]["subtype"] is None

    def test_missing_damping_everywhere(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA", damping=None), _sig(1, "MW-B", 0.4, recording="rB", damping=None)])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_INSUFFICIENT and "damping_unavailable" in _codes(r["limiting_evidence"])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED and r["classification_level"] == oc.LEVEL_UNRESOLVED   # two measurements: not "insufficient"


# ------------------------------------------------------------------ frequency alone never decides ----

class TestFrequencyIsOnlySupportingEvidence:
    @pytest.mark.parametrize("freq", [0.15, 0.4, 0.9, 1.2, 2.0, 2.9])
    def test_a_frequency_in_the_electromechanical_band_without_dynamics_or_signal_type_is_not_a_type(self, freq):
        # Voltage-type signal, no damping and no time evidence: the band alone raises nothing.
        r = _one([_sig(0, "V", freq, signal_type="Voltage", damping=None, temporal=None)])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED

    @pytest.mark.parametrize("freq", [0.15, 0.4, 1.2, 2.9])
    def test_a_relevant_signal_type_alone_is_not_enough_without_a_dynamic_response(self, freq):
        r = _one([_sig(0, "MW", freq, damping=None, temporal=None)])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED

    @pytest.mark.parametrize("freq", [3.5, 10.0, 25.0, 45.0])
    def test_a_sub_synchronous_frequency_alone_is_only_described(self, freq):
        r = _one([_sig(0, "I", freq, signal_type="Current", damping=None, temporal=None)])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED
        assert [d["code"] for d in r["descriptors"]] == [oc.DESCRIPTOR_HIGHER_FREQUENCY]
        assert r["descriptors"][0]["label"] == f"Higher-frequency oscillatory component detected at {freq:g} Hz"
        assert "frequency_alone_not_sso" in _codes(r["limiting_evidence"])
        lim = {i["code"]: i["message"] for i in r["limiting_evidence"]}
        assert "frequency alone does not establish sub-synchronous oscillation" in lim["frequency_alone_not_sso"]
        assert "sub-synchronous" not in (r["descriptors"][0]["label"] + r["descriptors"][0]["message"] + r["probable_type"]["label"]).lower()
        assert "SSO" not in str(r["probable_type"]) and "confirmed" not in str(r).lower()

    @pytest.mark.parametrize("freq", [4.0, 12.0, 30.0])
    def test_the_same_frequency_yields_different_results_when_the_other_evidence_differs(self, freq):
        ringdown = _one([_sig(0, "MW", freq), _sig(1, "F", freq, signal_type="Frequency", recording="r2")])
        sustained = _one([_sig(0, "I", freq, signal_type="Current", damping=_dmp("approximately_sustained", 0.0, None)),
                          _sig(1, "V", freq, signal_type="Voltage", recording="r2", damping=_dmp("approximately_sustained", 0.0, None))])
        assert ringdown["probable_type"]["code"] == oc.TYPE_UNRESOLVED
        assert sustained["probable_type"]["code"] != ringdown["probable_type"]["code"]

    def test_bands_overlap_by_design_and_are_echoed(self):
        p = oc.parameters()
        assert oc.INTER_AREA_BAND_HZ[1] > oc.LOCAL_BAND_HZ[0]
        assert "never decide a type on their own" in p["heuristics"]
        assert not any(isinstance(v, str) and "%" in v and "confidence" in v for v in p.values())


# ------------------------------------------------------------------ electromechanical family / subtypes ----

class TestElectromechanical:
    def test_same_frequency_single_recording_is_a_family_without_inter_area(self):
        r = _one([_sig(0, "MW", 0.4, recording="rA"), _sig(1, "FREQ", 0.4, signal_type="Frequency", recording="rA")])
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["classification_level"] == oc.LEVEL_PROBABLE
        assert r["probable_type"]["subtype"] is None                              # needs >= 2 recordings
        assert "single_recording" in _codes(r["limiting_evidence"]) and "subtype_unresolved" in _codes(r["limiting_evidence"])

    def test_inter_area_is_never_definitive_and_always_carries_its_limitations(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA"), _sig(1, "MW-B", 0.4, recording="rB")])
        assert r["probable_type"]["subtype"]["level"] == oc.LEVEL_POSSIBLE
        for forbidden in ("definitive", "confirmed", "is inter-area"):
            assert forbidden not in str(r).lower()

    def test_no_inter_area_without_temporal_overlap(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA", temporal=_tmp(20.0, 60.0)), _sig(1, "MW-B", 0.4, recording="rB", temporal=_tmp(80.0, 120.0))])
        assert r["probable_type"]["subtype"] is None and r["classification_level"] == oc.LEVEL_POSSIBLE
        assert "no_temporal_overlap" in _codes(r["limiting_evidence"])

    def test_no_inter_area_with_materially_different_decay(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA", damping=_dmp(alpha=0.1)), _sig(1, "MW-B", 0.4, recording="rB", damping=_dmp(alpha=0.5))])
        assert r["probable_type"]["subtype"] is None and r["classification_level"] == oc.LEVEL_POSSIBLE
        assert "decay_rates_differ_materially" in _codes(r["limiting_evidence"])

    def test_inter_area_frequency_boundary(self):
        inside = _one([_sig(0, "A", oc.INTER_AREA_BAND_HZ[1], recording="rA"), _sig(1, "B", oc.INTER_AREA_BAND_HZ[1], recording="rB")])
        outside = _one([_sig(0, "A", oc.INTER_AREA_BAND_HZ[1] + 0.1, recording="rA"), _sig(1, "B", oc.INTER_AREA_BAND_HZ[1] + 0.1, recording="rB")])
        assert inside["probable_type"]["subtype"]["code"] == oc.SUBTYPE_INTER_AREA
        assert outside["probable_type"]["subtype"] is None

    def test_local_is_never_positively_offered_from_absence_elsewhere(self):
        mw = _sig(0, "MW", 1.6, recording="rA")
        other = _sig(1, "MW2", 3.3, recording="rB", candidate=_cand(7.0))          # a compared signal WITHOUT the component
        r = [x for x in _interpret([mw, other]) if abs(x["component_frequency_hz"] - 1.6) < 0.01][0]
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["probable_type"]["subtype"] is None
        assert r["alternatives"] == []                                              # no "Possible local ..." reading from absence
        msgs = {i["code"]: i["message"] for i in r["limiting_evidence"]}
        assert msgs["subtype_unresolved"].startswith(
            "Electromechanical subtype unresolved — local or inter-area cannot be distinguished with the available evidence")
        assert "not proof of locality" in msgs["local_not_confirmed"]
        assert "Possible local" not in str(r) and "local_compatible" not in str(r)

    def test_unresolved_subtype_uses_neutral_wording_for_every_single_signal_frequency(self):
        for freq in (0.4, 0.9, 2.0):
            r = _one([_sig(0, "MW", freq)])
            assert r["alternatives"] == [] and "Possible local" not in str(r) and "Possible inter-area" not in str(r)
            assert "subtype_unresolved" in _codes(r["limiting_evidence"])

    def test_a_local_alternative_is_listed_only_beside_a_possible_inter_area_subtype(self):
        mid = _one([_sig(0, "A", 0.9, recording="rA"), _sig(1, "B", 0.9, recording="rB")])
        assert mid["probable_type"]["subtype"]["code"] == oc.SUBTYPE_INTER_AREA
        assert [a["code"] for a in mid["alternatives"]] == [oc.SUBTYPE_LOCAL] and mid["alternatives"][0]["consistency"] == "consistent"
        assert "not be excluded" in mid["alternatives"][0]["limitations"][0]["message"] or "cannot be excluded" in mid["alternatives"][0]["limitations"][0]["message"]

    def test_growing_electromechanical_component_is_at_most_possible(self):
        g = lambda i, rec: _sig(i, f"MW{i}", 0.4, recording=rec, damping=_dmp("growing", -0.05, None))     # noqa: E731
        r = _one([g(0, "rA"), g(1, "rB")])
        assert r["behaviour_classification"]["code"] == oc.BEHAVIOUR_GROWING
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and r["classification_level"] == oc.LEVEL_POSSIBLE

    def test_raw_plus_derived_duplicate_is_one_measurement_and_never_probable(self):
        raw = _sig(0, "MW", 0.4, roots=["r::MW"])
        derived = _sig(1, "-MW", 0.4, roots=["r::MW"], origin="calculated")
        r = _one([raw, derived])
        assert r["classification_level"] == oc.LEVEL_POSSIBLE and r["probable_type"]["subtype"] is None
        assert "derived_from_same_source" in _codes(r["limiting_evidence"])
        text = str(r).lower()
        assert "independently confirmed" not in text and "independent confirmation" not in text.replace("is not independent evidence", "")

    def test_rms_representation_is_disclosed(self):
        r = _one([_sig(0, "I", 1.2, signal_type="Current", representation="rms_magnitude")])
        assert "rms_representation" in _codes(r["limiting_evidence"])


# ------------------------------------------------------------------ forced / control / SSO ----

class TestOtherFamilies:
    def test_sustained_narrow_component_is_possible_forced_with_unidentified_source(self):
        r = _one([_sig(0, "MW", 0.4, damping=_dmp("approximately_sustained", 0.0, None), temporal=_tmp(0.0, 160.0), candidate=_cand(0.4, base_bins=3.0))])
        assert r["probable_type"]["code"] == oc.TYPE_FORCED_SUSTAINED and r["classification_level"] == oc.LEVEL_POSSIBLE
        assert "forcing_source_not_identified" in _codes(r["limiting_evidence"])
        assert {i["code"]: i["message"] for i in r["limiting_evidence"]}["forcing_source_not_identified"] == "Source of forcing is not identified."
        assert "narrow_component" in _codes(r["supporting_evidence"])

    def test_a_broad_sustained_component_is_still_possible_but_says_it_is_not_narrow(self):
        r = _one([_sig(0, "MW", 0.4, damping=_dmp("approximately_sustained", 0.0, None), candidate=_cand(0.4, base_bins=12.0))])
        assert r["probable_type"]["code"] == oc.TYPE_FORCED_SUSTAINED and "component_not_narrow" in _codes(r["limiting_evidence"])

    def test_control_like_component_needs_several_dimensions_and_never_exceeds_possible(self):
        sus = _dmp("approximately_sustained", 0.0, None)
        i, v = _sig(0, "I", 12.0, signal_type="Current", damping=sus, recording="r1"), _sig(1, "V", 12.0, signal_type="Voltage", damping=sus, recording="r1")
        r = _one([i, v])
        assert r["probable_type"]["code"] == oc.TYPE_CONTROL_CONVERTER and r["classification_level"] == oc.LEVEL_POSSIBLE
        assert r["probable_type"]["label"] == "Possible control/converter interaction"
        assert "no_converter_metadata" in _codes(r["limiting_evidence"])
        one = _one([i])
        assert one["probable_type"]["code"] != oc.TYPE_CONTROL_CONVERTER             # a single measurement is not enough

    def test_decaying_component_at_several_hz_is_not_control_interaction(self):
        r = _one([_sig(0, "I", 8.0, signal_type="Current", recording="r1"), _sig(1, "V", 8.0, signal_type="Voltage", recording="r2")])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED

    def test_possible_sso_needs_every_dimension_including_two_recordings(self):
        sus = _dmp("approximately_sustained", 0.0, None)
        full = _one([_sig(0, "I", 22.0, signal_type="Current", damping=sus, recording="r1"), _sig(1, "V", 22.0, signal_type="Voltage", damping=sus, recording="r2")])
        assert full["probable_type"]["code"] == oc.TYPE_SUB_SYNCHRONOUS and full["classification_level"] == oc.LEVEL_POSSIBLE
        assert full["probable_type"]["label"] == "Possible sub-synchronous oscillation"
        assert {a["code"] for a in full["alternatives"]} == {oc.TYPE_CONTROL_CONVERTER, oc.TYPE_FORCED_SUSTAINED}   # the less specific readings stay visible
        assert all(a["relation"] == "refined_by_primary" for a in full["alternatives"])
        assert "network_context_unavailable" in _codes(full["limiting_evidence"])
        assert "frequency_alone_not_sso" not in _codes(full["limiting_evidence"])      # the stronger rule is met: no disclaimer needed
        one_recording = _one([_sig(0, "I", 22.0, signal_type="Current", damping=sus), _sig(1, "V", 22.0, signal_type="Voltage", damping=sus)])
        assert one_recording["probable_type"]["code"] == oc.TYPE_CONTROL_CONVERTER

    def test_above_nominal_is_never_sub_synchronous(self):
        sus = _dmp("approximately_sustained", 0.0, None)
        r = _one([_sig(0, "I", 62.0, signal_type="Current", damping=sus, recording="r1"), _sig(1, "V", 62.0, signal_type="Voltage", damping=sus, recording="r2")])
        assert r["probable_type"]["code"] == oc.TYPE_CONTROL_CONVERTER and not r["descriptors"]

    def test_assumed_nominal_frequency_is_disclosed(self):
        r = _one([_sig(0, "I", 12.0, signal_type="Current", damping=None, temporal=None, nominal=None, nominal_assumed=True)])
        assert "nominal_frequency_assumed" in _codes(r["limiting_evidence"])

    def test_ambiguous_case_with_several_plausible_families_is_unresolved_with_alternatives(self):
        # A growing component exactly at the shared 3 Hz edge of the electromechanical and control bands, in two power measurements:
        # both families are `possible` on equal footing and neither refines the other -> no primary, both listed.
        grow = _dmp("growing", -0.05, None)
        r = _one([_sig(0, "MW-A", 3.0, damping=grow, recording="rA"), _sig(1, "MW-B", 3.0, damping=grow, recording="rB")])
        assert r["probable_type"]["code"] == oc.TYPE_UNRESOLVED and r["classification_level"] == oc.LEVEL_UNRESOLVED
        # (at 3 Hz in two recordings the sub-synchronous reading is raised too and refines the control reading)
        assert {a["code"]: a["relation"] for a in r["alternatives"]} == {
            oc.TYPE_ELECTROMECHANICAL: "equally_plausible", oc.TYPE_SUB_SYNCHRONOUS: "equally_plausible", oc.TYPE_CONTROL_CONVERTER: "refined_by_alternative"}
        assert "multiple_families_plausible" in _codes(r["limiting_evidence"])

    def test_a_higher_level_hypothesis_wins_and_the_lower_stays_an_alternative(self):
        hyps = [
            {"code": oc.TYPE_ELECTROMECHANICAL, "level": oc.LEVEL_PROBABLE, "supporting": [], "limiting": [], "dims": {}},
            {"code": oc.TYPE_FORCED_SUSTAINED, "level": oc.LEVEL_POSSIBLE, "supporting": [], "limiting": [], "dims": {}},
        ]
        primary, alternatives = oc._select(hyps)
        assert primary["code"] == oc.TYPE_ELECTROMECHANICAL and [a["code"] for a in alternatives] == [oc.TYPE_FORCED_SUSTAINED]

    def test_a_sustained_electrical_component_is_refined_to_control_with_forced_kept_as_an_alternative(self):
        sus = _dmp("approximately_sustained", 0.0, None)
        r = _one([_sig(0, "I", 12.0, signal_type="Current", damping=sus, recording="r1"), _sig(1, "V", 12.0, signal_type="Voltage", damping=sus, recording="r1")])
        assert r["probable_type"]["code"] == oc.TYPE_CONTROL_CONVERTER
        assert [(a["code"], a["relation"]) for a in r["alternatives"]] == [(oc.TYPE_FORCED_SUSTAINED, "refined_by_primary")]


# ------------------------------------------------------------------ structure ----

class TestResultModel:
    def test_every_evidence_item_is_structured_and_codes_are_stable_identifiers(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA"), _sig(1, "MW-B", 0.4, recording="rB")])
        for item in r["supporting_evidence"] + r["limiting_evidence"]:
            assert set(item) == {"code", "message", "values"} and item["code"].replace("_", "").isalnum() and item["message"]

    def test_no_statistical_confidence_or_probability_appears_anywhere(self):
        r = _one([_sig(0, "MW-A", 0.4, recording="rA"), _sig(1, "MW-B", 0.4, recording="rB")])
        text = str(r).lower()
        for forbidden in ("confidence", "probability", "% likely", "ai-generated"):
            assert forbidden not in text
        assert r["classification_level"] in (oc.LEVEL_PROBABLE, oc.LEVEL_POSSIBLE, oc.LEVEL_UNRESOLVED, oc.LEVEL_INSUFFICIENT)

    def test_the_result_does_not_depend_on_the_order_the_signals_were_listed(self):
        a = _sig(0, "MW-A", 0.4, recording="rA")
        b = _sig(1, "MW-B", 0.4, recording="rB", damping=_dmp(alpha=0.3))
        one = _one([a, b])
        swapped = _one([dict(b, index=0), dict(a, index=1)])
        for key in ("classification_level", "hierarchy", "behaviour_classification"):
            assert one[key] == swapped[key]
        assert one["probable_type"]["code"] == swapped["probable_type"]["code"]

    def test_classification_is_cheap(self):
        signals = [_sig(i, f"MW{i}", 0.4, recording=f"r{i}") for i in range(8)]
        comps = cs.group_components(signals)
        start = time.perf_counter()
        for _ in range(200):
            for c in comps:
                oc.classify_component(c, signals)
        per_call_ms = (time.perf_counter() - start) * 1000.0 / 200
        assert per_call_ms < 5.0


# ------------------------------------------------------------------ service / API (real chain) ----

def _interpret_run(registries, entries, f_min=0.1, f_max=10.0):  # noqa: F811
    from app.services.oscillation_interpretation_service import compute_interpretation
    return compute_interpretation(workspace_id=WS, entries=entries, f_min_hz=f_min, f_max_hz=f_max,
                                  source_registry=registries[0], calc_registry=registries[1])


class TestService:
    def _owner_case(self, registries):
        t, freq = _event(1, [(4.95, 0.01, 0.4)], step=0.5)
        _, mw = _event(2, [(4.95, 0.01, 0.4), (1.15, 0.02, 1.0)])
        registries[0].add(_active("src", t, {"FREQ": freq, "MW": mw}, types={"FREQ": "Frequency", "MW": "Active Power"}))
        return _interpret_run(registries, [_entry("src", "FREQ"), _entry("src", "MW")])

    def test_owner_real_event_pattern(self, registries):  # noqa: F811
        out = self._owner_case(registries)
        by = {round(c["representative_frequency_hz"]): c["interpretation"] for c in out["components"]}
        five, one = by[5], by[1]
        # 4.95 Hz in frequency + MW: a cross-signal physical component, but the family stays unresolved (never forced into control interaction)
        assert five["probable_type"]["code"] == oc.TYPE_UNRESOLVED and five["behaviour_classification"]["code"] == oc.BEHAVIOUR_RINGDOWN
        assert {"observed_in", "multiple_signal_types", "temporal_overlap", "decaying_damping"} <= {i["code"] for i in five["supporting_evidence"]}
        assert [d["code"] for d in five["descriptors"]] == [oc.DESCRIPTOR_HIGHER_FREQUENCY]
        # 1.15 Hz in MW only: a broad family at most, a valid single-signal detection
        assert one["probable_type"]["code"] in (oc.TYPE_ELECTROMECHANICAL, oc.TYPE_UNRESOLVED) and one["probable_type"]["subtype"] is None
        assert "single_signal_only" in {i["code"] for i in one["limiting_evidence"]}
        assert set(out["timings_ms"]) == {"signal_analysis", "grouping", "classification", "summary"}

    def test_a_single_signal_is_a_valid_interpretation(self, registries):  # noqa: F811
        t, mw = _event(2, [(1.15, 0.02, 1.0)])
        registries[0].add(_active("src", t, {"MW": mw}, types={"MW": "Active Power"}))
        out = _interpret_run(registries, [_entry("src", "MW")])
        interp = out["components"][0]["interpretation"]
        assert out["status"] == "ok" and interp["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL and interp["classification_level"] == oc.LEVEL_POSSIBLE
        assert interp["behaviour_classification"]["code"] == oc.BEHAVIOUR_RINGDOWN

    def test_same_mode_in_two_recordings_is_probable_electromechanical_with_a_provisional_subtype_at_most(self, registries):  # noqa: F811
        t, a = _event(3, [(0.6, 0.03, 1.5)])
        _, b = _event(4, [(0.6, 0.03, 1.5)])
        registries[0].add(_active("rA", t, {"P": a}, types={"P": "Active Power"}))
        registries[0].add(_active("rB", t, {"P": b}, types={"P": "Active Power"}))
        out = _interpret_run(registries, [_entry("rA", "P", label="P (A)"), _entry("rB", "P", label="P (B)")], f_min=0.1, f_max=3.0)
        interp = out["components"][0]["interpretation"]
        assert interp["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL
        assert interp["probable_type"]["subtype"] is None or interp["probable_type"]["subtype"]["level"] == oc.LEVEL_POSSIBLE
        assert interp["classification_level"] in (oc.LEVEL_PROBABLE, oc.LEVEL_POSSIBLE)

    def test_an_excluded_signal_is_reported_and_the_rest_are_interpreted(self, registries):  # noqa: F811
        t, p = _event(7, [(3.2, 0.02, 0.8)])
        registries[0].add(_active("src", t, {"P": p, "Q": p}, types={"P": "Active Power", "Q": "Active Power"}))
        out = _interpret_run(registries, [_entry("src", "Q", start=-500.0, end=100.0), _entry("src", "P")])
        assert [s["status"] for s in out["signals"]] == ["excluded", "ok"] and out["components"][0]["interpretation"]["component_id"] == 1

    def test_no_candidates_is_an_explained_success_without_interpretations(self, registries):  # noqa: F811
        import numpy as np
        t = np.arange(8000) / 50.0
        registries[0].add(_active("src", t, {"A": np.random.default_rng(9).normal(size=t.size)}))
        out = _interpret_run(registries, [_entry("src", "A")])
        assert out["status"] == "no_components" and out["components"] == []

    def test_classification_is_cheap_next_to_the_signal_analysis(self, registries):  # noqa: F811
        out = self._owner_case(registries)
        t = out["timings_ms"]
        assert t["classification"] < 5.0 and t["classification"] < t["signal_analysis"]

    def test_the_cross_signal_evidence_endpoint_still_classifies_nothing(self, registries):  # noqa: F811
        from app.services.oscillation_cross_signal_service import compute_cross_signal
        t, p = _event(7, [(3.2, 0.02, 0.8)])
        registries[0].add(_active("src", t, {"P": p}, types={"P": "Active Power"}))
        out = compute_cross_signal(workspace_id=WS, entries=[_entry("src", "P")], f_min_hz=0.1, f_max_hz=10.0,
                                   source_registry=registries[0], calc_registry=registries[1])
        assert all("interpretation" not in c for c in out["components"])


class TestApi:
    BASE = "/api/v1/workspaces/{ws}/oscillation-analysis/interpretation"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def test_a_single_signal_is_accepted_and_the_shape_is_stable(self, client):
        base = self.BASE.format(ws="w1")
        sig = {"input": {"kind": "source", "source_id": "nope", "channel_name": "A"}, "window_start_s": 0, "window_end_s": 10}
        r = client.post(base, json={"signals": [sig], "frequency_min_hz": 0.1, "frequency_max_hz": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "no_components" and [s["status"] for s in body["signals"]] == ["excluded"]
        assert body["interpretation_parameters"]["classification"].startswith("Deterministic")
        assert set(body["timings_ms"]) == {"signal_analysis", "grouping", "classification", "summary"}

    def test_empty_and_oversized_requests_are_refused(self, client):
        base = self.BASE.format(ws="w1")
        assert client.post(base, json={"signals": [], "frequency_min_hz": 0.1, "frequency_max_hz": 5}).status_code == 422
        sig = {"input": {"kind": "source", "source_id": "x", "channel_name": "A"}, "window_start_s": 0, "window_end_s": 10}
        many = [{**sig, "input": {**sig["input"], "channel_name": f"C{i}"}} for i in range(9)]
        assert client.post(base, json={"signals": many, "frequency_min_hz": 0.1, "frequency_max_hz": 5}).status_code == 422
