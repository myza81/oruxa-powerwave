"""NF-3G (O-9) -- the oscillation cross-signal classifier no longer takes the FIRST member's nominal frequency.

Owner decision (2026-11-28): where all members of a component agree on a nominal frequency, that frequency is used; where they disagree, the
result carries `nominal_frequency_mixed` limiting evidence and NO frequency is selected (nothing is compared with a chosen value); the
assumed-frequency provenance is preserved; the verdict does not depend on recording order; valid independent signal-analysis results
(family, behaviour, supporting evidence) are preserved; the existing agreement authority is reused and the oscillation mathematics is unchanged.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
from pathlib import Path

import numpy as np
import pytest

from app.domain import nominal_frequency as nf
from app.domain import oscillation_classification as oc
from app.services import nominal_frequency_access as access_module
from app.services.oscillation_interpretation_service import compute_interpretation
from tests.nf3c_access_support import access_for
from tests.test_oscillation_classification import _codes, _interpret, _one, _sig
from tests.test_oscillation_mode_shape import Env, WS, _entry, _ring, _source, _srv_t

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def members(frequency, spec, *, signal_type="Voltage"):
    """`spec`: (nominal, assumed) per member; one member per recording."""
    return [_sig(i, f"S{i}", frequency, signal_type=signal_type, recording=f"r{i}", nominal=nominal, nominal_assumed=assumed)
            for i, (nominal, assumed) in enumerate(spec)]


def facets(result):
    """Everything a consumer sees of one interpretation, order of members aside."""
    return {
        "type": (result.get("probable_type") or {}).get("code"),
        "descriptors": sorted(d["code"] for d in result.get("descriptors", [])),
        "supporting": sorted(e["code"] for e in result["supporting_evidence"]),
        "limiting": sorted(e["code"] for e in result["limiting_evidence"]),
        "mixed_values": [e["values"] for e in result["limiting_evidence"] if e["code"] == "nominal_frequency_mixed"],
        "nominal_values": sorted({str(e.get("values", {}).get("nominal_frequency_hz")) for key in ("supporting_evidence", "limiting_evidence", "descriptors")
                                  for e in result.get(key, []) if e.get("values", {}).get("nominal_frequency_hz") is not None}),
    }


# ============================================================================================================== agreement
class TestMembersThatAgreeUseTheAgreedFrequency:
    @pytest.mark.parametrize("frequency,nominal,below", [(45.0, 50.0, True), (55.0, 50.0, False), (55.0, 60.0, True), (65.0, 60.0, False)])
    def test_the_sub_synchronous_comparison_uses_the_agreed_value(self, frequency, nominal, below):
        r = _one(members(frequency, [(nominal, False), (nominal, False)]))
        assert ("higher_frequency_oscillatory_component" in [d["code"] for d in r["descriptors"]]) is below
        assert "nominal_frequency_mixed" not in _codes(r["limiting_evidence"])
        if below:
            assert facets(r)["nominal_values"] == [str(nominal)]

    def test_values_within_the_agreement_tolerance_are_one_frequency(self):
        r = _one(members(55.0, [(60.0, False), (60.0 + 1e-12, False)]))
        assert "nominal_frequency_mixed" not in _codes(r["limiting_evidence"])
        assert "higher_frequency_oscillatory_component" in [d["code"] for d in r["descriptors"]]

    def test_a_member_without_a_declared_value_does_not_decide_and_does_not_block(self):
        r = _one(members(55.0, [(None, False), (60.0, False)]))
        assert "nominal_frequency_mixed" not in _codes(r["limiting_evidence"]) and "nominal_frequency_assumed" not in _codes(r["limiting_evidence"])
        assert facets(r)["nominal_values"] == ["60.0"]

    def test_the_assumed_frequency_fallback_is_retained_when_nothing_is_declared(self):
        r = _one(members(12.0, [(None, False), (None, False)], signal_type="Current"))
        assert "nominal_frequency_assumed" in _codes(r["limiting_evidence"])
        assert oc.ASSUMED_NOMINAL_FREQUENCY_HZ == 50.0

    def test_assumed_provenance_survives_agreement(self):
        r = _one(members(45.0, [(50.0, True), (50.0, False)]))
        assert "nominal_frequency_assumed" in _codes(r["limiting_evidence"])
        assert "nominal_frequency_mixed" not in _codes(r["limiting_evidence"])


# ============================================================================================================== disagreement
class TestMembersThatDisagreeGiveNoFrequency:
    @pytest.mark.parametrize("frequency", [4.0, 45.0, 55.0])
    @pytest.mark.parametrize("spec", [[(50.0, False), (60.0, False)], [(60.0, False), (50.0, False)], [(50.0, True), (60.0, False)]])
    def test_nominal_frequency_mixed_is_reported_and_nothing_is_compared_with_a_nominal_value(self, frequency, spec):
        r = _one(members(frequency, spec))
        assert "nominal_frequency_mixed" in _codes(r["limiting_evidence"])
        assert [d["code"] for d in r["descriptors"]] == []                       # the 'higher-frequency component' descriptor needs ONE nominal
        assert "frequency_alone_not_sso" not in _codes(r["limiting_evidence"])
        assert "nominal_frequency_assumed" not in _codes(r["limiting_evidence"])    # no 50 Hz is assumed for a comparison that is not made
        assert facets(r)["nominal_values"] == []                                  # no member's value is quoted as THE nominal
        assert (r.get("probable_type") or {}).get("code") != oc.TYPE_SUB_SYNCHRONOUS

    def test_the_evidence_names_every_declared_value_and_carries_the_assumed_provenance(self):
        r = _one(members(55.0, [(50.0, True), (60.0, False)]))
        evidence = next(e for e in r["limiting_evidence"] if e["code"] == "nominal_frequency_mixed")
        assert evidence["values"] == {"nominal_frequencies_hz": "50,60", "any_assumed": True}
        assert "50 Hz" in evidence["message"] and "60 Hz" in evidence["message"] and "no single nominal frequency is chosen" in evidence["message"]
        agreed_assumed = _one(members(55.0, [(50.0, False), (60.0, False)]))
        assert next(e for e in agreed_assumed["limiting_evidence"] if e["code"] == "nominal_frequency_mixed")["values"]["any_assumed"] is False

    def test_a_component_below_the_sub_synchronous_floor_does_not_report_it(self):
        # below 3 Hz no nominal comparison exists at all, so there is nothing for a disagreement to withhold
        r = _one(members(1.0, [(50.0, False), (60.0, False)], signal_type="Active Power"))
        assert "nominal_frequency_mixed" not in _codes(r["limiting_evidence"])


class TestTheVerdictDoesNotDependOnRecordingOrder:
    @pytest.mark.parametrize("frequency", [4.0, 45.0, 55.0, 65.0])
    @pytest.mark.parametrize("spec", [
        [(50.0, False), (60.0, False)], [(50.0, True), (60.0, False)], [(50.0, False), (50.0, False)], [(60.0, False), (60.0, True)],
        [(None, False), (60.0, False)], [(50.0, False), (55.0, False), (60.0, False)],
    ])
    def test_every_permutation_of_the_members_gives_the_same_result(self, frequency, spec):
        results = []
        for permutation in itertools.permutations(spec):
            results.append(facets(_one(members(frequency, list(permutation)))))
        assert all(r == results[0] for r in results), results


class TestIndependentResultsArePreserved:
    @pytest.mark.parametrize("frequency", [4.0, 45.0, 55.0])
    def test_family_and_supporting_evidence_equal_those_of_an_agreeing_pair(self, frequency):
        mixed = _one(members(frequency, [(50.0, False), (60.0, False)]))
        agreed = _one(members(frequency, [(50.0, False), (50.0, False)]))
        assert (mixed.get("probable_type") or {}).get("code") == (agreed.get("probable_type") or {}).get("code")
        assert sorted(e["code"] for e in mixed["supporting_evidence"]) == sorted(e["code"] for e in agreed["supporting_evidence"])
        assert mixed["behaviour_classification"] == agreed["behaviour_classification"]

    def test_a_single_recording_pair_is_unchanged(self):
        r = _one([_sig(0, "A", 0.40, recording="rA"), _sig(1, "B", 0.40, recording="rB")])
        assert r["probable_type"]["code"] == oc.TYPE_ELECTROMECHANICAL


# ============================================================================================================== the one authority
class TestTheSharedAgreementAuthorityIsReused:
    def test_the_accessor_and_the_classifier_apply_the_same_function_and_tolerance(self):
        assert access_module.frequencies_agree is nf.frequencies_agree
        assert (access_module.AGREEMENT_REL_TOL, access_module.AGREEMENT_ABS_TOL) == (nf.AGREEMENT_REL_TOL, nf.AGREEMENT_ABS_TOL) == (1e-9, 1e-9)

    @pytest.mark.parametrize("values,expected", [([50.0, 50.0], 50.0), ([60.0, 60.0 + 1e-12], 60.0), ([50.0, 60.0], None), ([], None),
                                                 ([60.0, 50.0, 50.0], None)])
    def test_agreed_frequency_is_the_smallest_agreeing_value_or_none_and_never_a_representative(self, values, expected):
        assert nf.agreed_frequency(values) == expected
        assert nf.agreed_frequency(list(reversed(values))) == expected

    def test_the_classifier_has_no_agreement_arithmetic_of_its_own(self):
        tree = ast.parse((APP_DIR / "domain" / "oscillation_classification.py").read_text(encoding="utf-8"))
        names = {n.attr if isinstance(n, ast.Attribute) else n.id for n in ast.walk(tree) if isinstance(n, (ast.Attribute, ast.Name))}
        assert "isclose" not in names
        assert "agreed_frequency" in names

    def test_the_accessors_multi_recording_outcomes_are_unchanged(self):
        from app.domain.nominal_frequency import EffectiveNominalFrequency  # noqa: F401  (the resolver module still imports cleanly)
        from app.services.nominal_frequency_access import SourceFrequency, combine
        member = lambda sid, hz: SourceFrequency(sid, hz, "recording_metadata", "auto", 0, hz, False)      # noqa: E731
        assert combine([member("a", 50.0), member("b", 50.0)]).common_hz == 50.0
        mixed = combine([member("a", 50.0), member("b", 60.0)])
        assert (mixed.status, mixed.common_hz, mixed.distinct_hz) == ("mixed", None, (50.0, 60.0))


# ============================================================================================================== through the service chain
FS = 500.0
T = np.arange(int(FS * 160.0)) / FS


def _modulated_voltage(f_carrier_hz, seed):
    """A voltage whose RMS envelope carries a decaying 4 Hz oscillation from t = 30 s (the carrier is the recording's own frequency)."""
    tau = np.clip(T - 30.0, 0, None)
    envelope = 1.0 + 0.25 * np.exp(-0.01 * tau) * np.cos(2 * np.pi * 4.0 * tau) * (T >= 30.0) + np.random.default_rng(seed).normal(0, 0.002, T.size)
    return 100e3 * envelope * np.cos(2 * np.pi * f_carrier_hz * T)


class TestEndToEndThroughTheInterpretationService:
    """Two recordings carrying the same 4 Hz oscillation in an RMS-magnitude analysis, declaring their own nominal frequencies, through
    `compute_interpretation` (the production path: the representation takes each recording's frequency from the central accessor)."""

    @staticmethod
    def run(first_hz, second_hz, *, swap=False, representation="rms_magnitude"):
        env = Env()
        for source_id, name, nominal, seed in (("recA", "VA A", first_hz, 1), ("recB", "VA B", second_hz, 2)):
            source = _source(source_id, T, {name: _modulated_voltage(nominal, seed)}, {name: "Voltage"})
            # a recording that DECLARES its frequency (the shared fixture marks its default as assumed, which would resolve to 50 Hz)
            declared = dataclasses.replace(source.metadata, nominal_frequency=nominal, preparation_provenance={"source_format": "COMTRADE"})
            env.sources.add(dataclasses.replace(source, metadata=declared))
        entries = [{**_entry("recA", "VA A", start=1.0, end=159.0), "representation": representation, "offset_s": 0.0},
                   {**_entry("recB", "VA B", start=1.0, end=159.0), "representation": representation, "offset_s": 0.0}]
        if swap:
            entries.reverse()
        out = compute_interpretation(
            workspace_id=WS, entries=entries, f_min_hz=0.1, f_max_hz=5.0, source_registry=env.sources,
            frequency_access=access_for(env.sources), calc_registry=env.calc, sync_registry=env.sync)
        return [c["interpretation"] for c in out["components"]]

    def test_different_declared_frequencies_report_nominal_frequency_mixed_whatever_the_order(self):
        first, swapped = self.run(50.0, 60.0), self.run(50.0, 60.0, swap=True)
        assert len(first) == len(swapped) == 1
        assert "nominal_frequency_mixed" in _codes(first[0]["limiting_evidence"])
        assert facets(first[0]) == facets(swapped[0])
        assert [d["code"] for d in first[0]["descriptors"]] == []
        assert facets(self.run(60.0, 50.0)[0]) == facets(first[0])                 # which recording declares which does not matter either

    @pytest.mark.parametrize("hz", [50.0, 60.0])
    def test_equal_declared_frequencies_use_the_agreed_value(self, hz):
        (r,) = self.run(hz, hz)
        assert "nominal_frequency_mixed" not in _codes(r["limiting_evidence"])
        assert [d["code"] for d in r["descriptors"]] == ["higher_frequency_oscillatory_component"]
        assert facets(r)["nominal_values"] == [str(hz)]

    def test_native_members_carry_no_nominal_frequency_so_the_agreement_rule_has_nothing_to_compare_there(self):
        # Unchanged by NF-3G (recorded as a limitation): a native-representation signal never carried the recording's frequency into the
        # classifier, so it neither agrees nor disagrees and the assumed-frequency fallback applies exactly as before. Feeding native
        # members would change Auto-mode output (the assumed flag) and is not part of the approved O-9 scope.
        env = Env()
        t = _srv_t()
        for source_id, name, nominal, seed in (("recA", "MW A", 50.0, 1), ("recB", "MW B", 60.0, 2)):
            source = _source(source_id, t, {name: _ring(t, 4.0, 0.0, 4.0, alpha=0.01, seed=seed)}, {name: "Active Power"})
            declared = dataclasses.replace(source.metadata, nominal_frequency=nominal, preparation_provenance={"source_format": "COMTRADE"})
            env.sources.add(dataclasses.replace(source, metadata=declared))
        entries = [{**_entry("recA", "MW A"), "offset_s": 0.0}, {**_entry("recB", "MW B"), "offset_s": 0.0}]
        out = compute_interpretation(
            workspace_id=WS, entries=entries, f_min_hz=0.1, f_max_hz=5.0, source_registry=env.sources,
            frequency_access=access_for(env.sources), calc_registry=env.calc, sync_registry=env.sync)
        (component,) = out["components"]
        limiting = _codes(component["interpretation"]["limiting_evidence"])
        assert "nominal_frequency_mixed" not in limiting
        assert "nominal_frequency_assumed" in limiting
