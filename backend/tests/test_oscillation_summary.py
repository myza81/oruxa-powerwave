"""Oscillation Analysis -- engineer-facing component summary (DEC-183 [APPROVED]).

The summary is a presentation layer: these tests feed it the REAL structured results (cross-signal grouping, interpretation, mode shape,
coherence) and check the deterministic wording, the evidence strip and the hard rules (unavailable is not failure, nothing is overstated,
no severity, no second analysis pass). Nothing here uses an AI, a probability or a severity.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain import coherence as co
from app.domain import cross_signal_evidence as cs
from app.domain import mode_shape as ms
from app.domain import oscillation_classification as oc
from app.domain import oscillation_integration as oi
from app.domain import oscillation_summary as osum
from app.main import create_app
from tests.test_oscillation_classification import _dmp, _sig, _tmp
from tests.test_oscillation_coherence import _cm
from tests.test_oscillation_integration import F, _cos, _coherence, _comp, _pair, _shape, _t, _mem
from tests.test_oscillation_integration import Env, WS, _entry, _interpret_service, _ring, _source, _srv_t

#: Words that must never appear in a summary (severity, certainty, dominance, failure).
FORBIDDEN = ("severe", "dangerous", "critical", "unstable system", "dominant", "failed", "failure", "error", "confirmed", "probability", "% confidence")


def _summaries(signals, evidence=None, *, integrated=True):
    comps = cs.group_components(signals)
    units = {s["index"]: "MW" for s in signals}
    out = []
    for comp in comps:
        comp["interpretation"] = oc.classify_component(comp, signals, evidence)
        spatial = evidence or {}
        out.append(osum.build_component_summary(
            comp, units_by_index=units, integrated=integrated, mode_shape=spatial.get("mode_shape"), coherence=spatial.get("coherence")))
    return out


def _one(signals, evidence=None, *, integrated=True):
    out = _summaries(signals, evidence, integrated=integrated)
    assert len(out) == 1, out
    return out[0]


def _status(summary):
    return {e["code"]: e["status"] for e in summary["evidence"]}


def _detail(summary, code):
    return next(e["detail"] for e in summary["evidence"] if e["code"] == code)


def _field(summary, code):
    return next((f["value"] for f in summary["fields"] if f["code"] == code), None)


def _text(summary):
    return " ".join([summary["title"], summary["conclusion"], summary["caution"] or ""] + [f["value"] for f in summary["fields"]]
                    + [e["detail"] + " " + e["status_label"] for e in summary["evidence"]])


def _no_forbidden(summary):
    text = _text(summary).lower()
    for word in FORBIDDEN:
        assert word not in text, (word, text)


def _two():
    return [_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB", damping=_dmp(alpha=0.3))]


# ------------------------------------------------------------------ the real short ~0.4 Hz event (the owner's UAT state) ----

def _short_event():
    """~0.4 Hz decaying in two MW measurements of two recordings; the shared active interval is 7 s (2.8 cycles); the cross-signal activity overlaps 31 s."""
    signals = [_sig(0, "POWER UNIT NO.1", 0.40, recording="rA", temporal=_tmp(0.0, 31.0), damping=_dmp(alpha=0.087, zeta=0.037)),
               _sig(1, "POWER UNIT UNIT NO.2", 0.40, recording="rB", temporal=_tmp(0.0, 31.0), damping=_dmp(alpha=0.147, zeta=0.061))]
    t = _t(7.0)
    shape = {"component_id": 1, "groups": [ms.analyse_quantity_group(
        quantity_type="Active Power", unit="MW", members=[_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 170))],
        representative_frequency_hz=F, tolerance_hz=0.05, neighbour_frequencies_hz=[])]}
    coh = {"component_id": 1, **co.analyse_component(members=[_cm(0, t, _cos(t, 0)), _cm(1, t, _cos(t, 170))], reference_index=0, frequency_hz=F)}
    assert shape["groups"][0]["status"] != "ok" and coh["pairs"][0]["status"] != "ok"
    return signals, {"mode_shape": shape, "coherence": coh}


class TestRealShortEvent:
    def test_the_summary_says_what_was_found_and_why_the_subtype_is_unresolved(self):
        signals, evidence = _short_event()
        s = _one(signals, evidence)
        assert s["title"] == "Component around 0.4 Hz"
        text = s["conclusion"]
        assert text.startswith("A ~0.4 Hz decaying electromechanical oscillation is observed in 2 distinct MW measurements.")
        assert "corroborated across two recordings with overlapping activity" in text
        assert "Local versus inter-area behaviour remains unresolved because the shared active interval is too short for reliable " \
               "relative-phase and coherence estimation." in text
        assert _field(s, "behaviour") == "Disturbance-excited decaying oscillation" or "decaying" in _field(s, "behaviour").lower()
        assert _field(s, "strength") == "Possible" and _field(s, "subtype") is None
        assert _field(s, "observed") == "2 signals · 2 distinct measurements · 2 recordings"
        _no_forbidden(s)

    def test_the_evidence_strip_marks_the_two_methods_unavailable_not_failed(self):
        signals, evidence = _short_event()
        s = _one(signals, evidence)
        assert [e["code"] for e in s["evidence"]] == ["spectrum", "time_frequency", "damping", "cross_signal", "mode_shape", "coherence"]
        assert _status(s) == {"spectrum": "available", "time_frequency": "available", "damping": "available", "cross_signal": "available",
                              "mode_shape": "unavailable", "coherence": "unavailable"}
        labels = {e["status_label"] for e in s["evidence"]}
        assert labels == {"Available", "Unavailable for this event"}
        # the backend's own refusal numbers are shown verbatim
        assert "2.78 cycles" in _detail(s, "mode_shape") and "at least 3" in _detail(s, "mode_shape")
        assert "0.62" in _detail(s, "coherence") and "at least 1.5" in _detail(s, "coherence")
        assert _detail(s, "coherence").count("Coherence unavailable") == 0          # the label is not duplicated
        assert "shared activity overlaps for 31 s" in _detail(s, "cross_signal")

    def test_the_damping_of_two_members_is_a_range_not_one_members_value(self):
        signals, evidence = _short_event()
        d = _detail(_one(signals, evidence), "damping")
        assert d.startswith("2 members decaying") and "α = 0.087–0.147 s⁻¹" in d and "damping ratio 3.7–6.1%" in d


# ------------------------------------------------------------------ wording hierarchy ----

class TestProvisionalInterArea:
    def test_supported_provisional_is_stated_but_never_confirmed(self):
        s = _one(_two(), {"mode_shape": _shape(165.0), "coherence": _coherence(165.0)})
        assert _field(s, "strength") == "Supported (provisional)" and _field(s, "subtype") == oi.SUBTYPE_PROVISIONAL_LABEL
        assert "support a provisional inter-area interpretation" in s["conclusion"]
        assert "does not independently prove that the measurements represent separate grid areas" in s["conclusion"]
        assert _status(s)["mode_shape"] == "available" and _status(s)["coherence"] == "available"
        assert "~165° phase separation" in _detail(s, "mode_shape") and "2 distinct MW measurements" in _detail(s, "mode_shape")
        assert "clearly above" in _detail(s, "coherence") and "95% null threshold" in _detail(s, "coherence")
        assert "confirmed" not in _text(s).lower()
        _no_forbidden(s)

    def test_phase_without_coherence_is_consistent_with_and_stays_provisional(self):
        refused = _pair(None, None, status="insufficient_evidence", message="Coherence unavailable — the shared 7 s interval is too short.", reason_code="too_few_cycles")
        s = _one(_two(), {"mode_shape": _shape(165.0), "coherence": _comp([refused])})
        assert _field(s, "strength") == "Consistent with" and _field(s, "subtype") == oi.SUBTYPE_POSSIBLE_LABEL
        assert "remains provisional because coherence is unavailable" in s["conclusion"]
        assert _status(s)["coherence"] == "unavailable" and _status(s)["mode_shape"] == "available"

    def test_weak_coherence_beside_a_phase_is_a_caution_with_the_contradiction_shown(self):
        s = _one(_two(), {"mode_shape": _shape(165.0), "coherence": _comp([_pair(0.40)])})
        assert _status(s)["coherence"] == "caution" and "not above" in _detail(s, "coherence")
        assert s["caution"] == oi.TEXT_COHERENCE_WEAK_FOR_PHASE
        assert "coherence is weak or marginal" in s["conclusion"]

    def test_marginal_coherence_is_a_caution(self):
        s = _one(_two(), {"mode_shape": _shape(165.0), "coherence": _comp([_pair(0.70)])})
        assert _status(s)["coherence"] == "caution" and "only marginally above" in _detail(s, "coherence")

    def test_an_unstable_phase_is_a_caution_and_no_pattern_is_relied_on(self):
        s = _one(_two(), {"mode_shape": _shape(100.0, ramp_deg=170.0), "coherence": _coherence(100.0)})
        assert _status(s)["mode_shape"] == "caution" and "not stable" in _detail(s, "mode_shape")
        assert "not stable across the common interval" in s["conclusion"] and _field(s, "subtype") is None


class TestNearInPhase:
    def test_is_neither_local_nor_inter_area(self):
        s = _one(_two(), {"mode_shape": _shape(8.0), "coherence": _coherence(8.0)})
        text = _text(s).lower()
        assert "local mode" not in text and "inter-area mode" not in text and "inter-area electromechanical" not in text
        assert "approximately in phase" in s["conclusion"] and "does not distinguish between local and inter-area behaviour" in s["conclusion"]
        assert "subtype remains unresolved" in s["conclusion"] and _field(s, "subtype") is None
        assert _detail(s, "mode_shape").startswith("Approximately in phase (~8° from")


class TestBehaviours:
    def test_growing_is_prominent_and_no_damping_ratio_is_invented(self):
        grow = _dmp(behaviour="growing", alpha=-0.05, zeta=None)
        signals = [_sig(0, "MW-A", 0.40, recording="rA", damping=grow), _sig(1, "MW-B", 0.40, recording="rB", damping=grow)]
        s = _one(signals, {"mode_shape": None, "coherence": None})
        assert s["growing"] is True and "growing" in s["conclusion"] and _field(s, "behaviour") == "Growing oscillation"
        assert "Its amplitude is increasing" in s["conclusion"]
        d = _detail(s, "damping")
        assert "growing" in d and "growth rate 0.05 s⁻¹" in d and "no damping ratio is reported" in d and "%" not in d
        _no_forbidden(s)
        assert "severity" not in _text(s).lower()

    def test_sustained_does_not_identify_a_forcing_source(self):
        sustained = _dmp(behaviour="approximately_sustained", alpha=0.0, zeta=None)
        signals = [_sig(0, "MW-A", 0.9, recording="rA", damping=sustained), _sig(1, "MW-B", 0.9, recording="rB", damping=sustained)]
        s = _one(signals, {"mode_shape": _shape(150.0), "coherence": _coherence(150.0)})
        assert "Sustained oscillatory behaviour is present; the forcing source is not identified." in s["conclusion"]
        assert "Approximately sustained" in _detail(s, "damping") or "approximately sustained" in _detail(s, "damping")
        assert "%" not in _detail(s, "damping")

    def test_conflicting_damping_is_shown_as_a_caution_not_averaged(self):
        signals = [_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB", damping=_dmp(behaviour="approximately_sustained", alpha=0.0, zeta=None))]
        s = _one(signals, {"mode_shape": None, "coherence": None})
        assert _status(s)["damping"] == "caution" and "reported, not averaged" in _detail(s, "damping")
        assert "Damping behaviour differs between the signals" in s["conclusion"]

    def test_one_valid_member_among_two_is_named_not_generalised(self):
        signals = [_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB", damping=_dmp(status="insufficient_evidence", behaviour=None, reason_code="x"))]
        d = _detail(_one(signals, {"mode_shape": None, "coherence": None}), "damping")
        assert d.startswith("Decaying in MW-A only") and "1 of 2 members had a valid estimate" in d

    def test_damping_unavailable_uses_the_backend_reason_and_is_unavailable_not_failed(self):
        gone = _dmp(status="insufficient_evidence", behaviour=None, reason_code="x")
        gone["message"] = "The envelope has too few cycles above the background."
        s = _one([_sig(0, "MW-A", 0.40, damping=gone)], None, integrated=False)
        assert _status(s)["damping"] == "unavailable" and "too few cycles" in _detail(s, "damping")


class TestSingleSignal:
    def test_cross_signal_mode_shape_and_coherence_are_not_applicable_in_both_request_forms(self):
        for evidence, integrated in ((None, False), ({"mode_shape": None, "coherence": None}, True)):
            s = _one([_sig(0, "MW-A", 1.2, recording="rA", damping=_dmp(alpha=0.05))], evidence, integrated=integrated)
            assert _status(s)["cross_signal"] == _status(s)["mode_shape"] == _status(s)["coherence"] == "not_applicable"
            assert "Observed in one signal only; cross-signal modal evidence is not applicable." in _detail(s, "cross_signal")
            assert s["conclusion"].startswith("A ~1.2 Hz decaying oscillation is detected in one MW measurement. Available evidence is consistent with an electromechanical oscillation. Cross-signal modal evidence is not available")
            assert "Cross-signal modal evidence is not available, so the local/inter-area subtype cannot be determined." in s["conclusion"]
            assert {e["status_label"] for e in s["evidence"] if e["status"] == "not_applicable"} == {"Not applicable"}
            _no_forbidden(s)


class TestHigherFrequency:
    def test_neutral_wording_is_kept_and_sso_is_not_inferred_from_frequency(self):
        signals = [_sig(0, "FREQ", 4.95, signal_type="Frequency", recording="rA"), _sig(1, "MW", 4.95, recording="rB")]
        s = _one(signals, {"mode_shape": _shape(170.0), "coherence": _coherence(170.0)})
        assert s["conclusion"].startswith("Higher-frequency oscillatory component detected at ~4.95 Hz")
        assert "insufficient to identify a control, converter or sub-synchronous mechanism" in s["conclusion"]
        assert "possible sub-synchronous" not in s["conclusion"].lower() and "Sub-synchronous oscillation" not in _field(s, "type")
        assert _field(s, "type") == oc.UNRESOLVED_LABEL


class TestSharedProvenance:
    def test_two_signals_of_one_measurement_are_one_distinct_measurement(self):
        shared = {"src::P"}
        signals = [_sig(0, "MW raw", 0.40, recording="rA", roots=shared), _sig(1, "MW calc", 0.40, recording="rA", roots=shared, origin="calculated")]
        s = _one(signals, {"mode_shape": _shape(180.0, shared=True), "coherence": _coherence(180.0, shared=True)})
        assert _field(s, "observed") == "2 signals · 1 distinct measurement · 1 recording"
        assert "2 signals that derive from only 1 distinct MW measurement" in s["conclusion"]
        assert "not independent corroboration" in s["conclusion"]
        assert _status(s)["mode_shape"] == "unavailable" and "share one source measurement" in _detail(s, "mode_shape")
        assert _status(s)["cross_signal"] == "caution" and "sharing only 1 distinct measurement" in _detail(s, "cross_signal")
        assert _field(s, "subtype") is None and _field(s, "strength") == "Possible"
        assert s["caution"] and "share" in s["caution"].lower()
        assert "2 distinct" not in _text(s) and "share one source measurement, so they provide no independent spatial evidence" in s["conclusion"]


class TestMultipleComponents:
    def test_each_component_gets_its_own_summary_in_the_interpretation_order(self):
        signals = [_sig(0, "MW-A", 0.40, recording="rA"), _sig(1, "MW-B", 0.40, recording="rB"), _sig(2, "MW-C", 1.15, recording="rC")]
        comps = cs.group_components(signals)
        assert len(comps) == 2
        out = _summaries(signals, {"mode_shape": None, "coherence": None})
        assert [s["component_id"] for s in out] == [c["id"] for c in comps]
        assert {s["title"] for s in out} == {"Component around 0.4 Hz", "Component around 1.15 Hz"}
        by_title = {s["title"]: s for s in out}
        assert "2 distinct MW measurements" in by_title["Component around 0.4 Hz"]["conclusion"]
        assert by_title["Component around 1.15 Hz"]["conclusion"].count("0.4 Hz") == 0          # no mixing of unrelated frequencies
        assert _status(by_title["Component around 1.15 Hz"])["mode_shape"] == "not_applicable"
        assert _status(by_title["Component around 0.4 Hz"])["mode_shape"] == "unavailable"


class TestWordingGuards:
    def test_the_vocabulary_never_overstates_across_every_scenario(self):
        scenarios = [
            _one(_two(), {"mode_shape": _shape(165.0), "coherence": _coherence(165.0)}),
            _one(_two(), {"mode_shape": _shape(8.0), "coherence": _coherence(8.0)}),
            _one(_two(), None, integrated=False),
            _one([_sig(0, "MW-A", 0.40)], None, integrated=False),
            _one(*_short_event()),
        ]
        for s in scenarios:
            _no_forbidden(s)
            assert {e["status"] for e in s["evidence"]} <= {"available", "unavailable", "not_applicable", "caution"}
            assert "highest-ranked" not in s["conclusion"].lower() and "dominant" not in _text(s).lower()

    def test_a_comparison_without_the_spatial_context_says_not_computed(self):
        s = _one(_two(), None, integrated=False)
        assert _status(s)["mode_shape"] == _status(s)["coherence"] == "unavailable"
        assert _detail(s, "mode_shape") == "Not computed for this comparison."
        assert "were not computed for this comparison" in s["conclusion"] and "phase separation" not in s["conclusion"]

    def test_status_labels_are_the_fixed_four(self):
        assert osum.STATUS_LABELS == {"available": "Available", "unavailable": "Unavailable for this event", "not_applicable": "Not applicable", "caution": "Caution"}


# ------------------------------------------------------------------ service / API ----

@pytest.fixture
def env():
    return Env()


class TestService:
    def _two(self, env, *, alpha, phase):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"MW A": _ring(t, F, 0.0, 4.0, alpha=alpha, seed=1)}, {"MW A": "Active Power"}))
        env.sources.add(_source("recB", t, {"MW B": _ring(t, F, phase, 3.1, alpha=alpha, seed=2)}, {"MW B": "Active Power"}))
        return _interpret_service(env, [_entry("recA", "MW A"), _entry("recB", "MW B")])

    def test_the_real_chain_short_event_summary(self, env):
        out = self._two(env, alpha=0.17, phase=172.0)
        s = out["components"][0]["summary"]
        assert _status(s)["mode_shape"] == "unavailable" and _status(s)["coherence"] == "unavailable" and _status(s)["damping"] == "available"
        assert "remains unresolved because the shared active interval is too short" in s["conclusion"]
        assert _field(s, "strength") == "Possible"

    def test_the_real_chain_positive_case_summary(self, env):
        out = self._two(env, alpha=0.01, phase=172.0)
        s = out["components"][0]["summary"]
        assert _field(s, "strength") == "Supported (provisional)" and _status(s)["mode_shape"] == "available" and _status(s)["coherence"] == "available"
        assert "provisional inter-area interpretation" in s["conclusion"] and "confirmed" not in s["conclusion"]

    def test_the_summary_is_one_small_extra_step_with_no_additional_analysis_pass(self, env, monkeypatch):
        import app.services.oscillation_cross_signal_service as svc
        calls = {"spectrum": 0, "spectrogram": 0, "damping": 0}
        for key, name in (("spectrum", "compute_spectrum"), ("spectrogram", "compute_spectrogram"), ("damping", "compute_damping")):
            original = getattr(svc, name)

            def counted(*a, _o=original, _k=key, **kw):
                calls[_k] += 1
                return _o(*a, **kw)
            monkeypatch.setattr(svc, name, counted)
        out = self._two(env, alpha=0.01, phase=172.0)
        assert calls == {"spectrum": 2, "spectrogram": 2, "damping": 2}
        assert 0.0 <= out["timings_ms"]["summary"] < 50.0

    def test_a_single_signal_request_has_a_summary_too(self, env):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"MW A": _ring(t, F, 0.0, 4.0, alpha=0.01, seed=1)}, {"MW A": "Active Power"}))
        out = _interpret_service(env, [_entry("recA", "MW A")])
        s = out["components"][0]["summary"]
        assert _status(s)["cross_signal"] == "not_applicable" and "is detected in one" in s["conclusion"]


class TestApi:
    URL = "/api/v1/workspaces/{ws}/oscillation-analysis/interpretation"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def test_the_response_carries_the_summary_without_a_second_endpoint(self, client):
        t = _srv_t()
        registry = client.app.state.workspace_registry
        registry.add(_source("recA", t, {"P": _ring(t, F, 0.0, 4.0, alpha=0.01, seed=41)}, {"P": "Active Power"}))
        registry.add(_source("recB", t, {"P": _ring(t, F, 172.0, 3.0, alpha=0.01, seed=42)}, {"P": "Active Power"}))
        sig = lambda src: {"input": {"kind": "source", "source_id": src, "channel_name": "P"}, "representation": "native", "window_start_s": 0.0,
                           "window_end_s": 159.98, "label": src, "offset_s": 99.0}
        r = client.post(self.URL.format(ws=WS), json={"signals": [sig("recA"), sig("recB")], "frequency_min_hz": 0.1, "frequency_max_hz": 5.0})
        assert r.status_code == 200, r.text
        summary = r.json()["components"][0]["summary"]
        assert set(summary) == {"component_id", "title", "frequency_hz", "growing", "fields", "evidence", "conclusion", "caution"}
        assert [e["code"] for e in summary["evidence"]] == ["spectrum", "time_frequency", "damping", "cross_signal", "mode_shape", "coherence"]
        assert summary["component_id"] == r.json()["components"][0]["id"] and "summary" in r.json()["timings_ms"]
