"""NF-3D: the approved-changes manifest is restricted to the kinds the owner approved (O-5, O-6) and is checked against the baselines.

`tests/fixtures/nf3d_baselines/nf3d_approved_changes.json` lists every difference NF-3D makes to the frozen NF-3B and NF-3D baselines.
The baseline comparison tests prove "history + NF-3C changes + this manifest = current output"; THIS module proves the manifest itself
contains nothing but the approved kinds, so a numerical or behavioural change can never hide in it:

* `provenance_added`      only NEW fields, carrying the origin the scenario's recording actually has (or null where no provenance applies)
* `unusable_refusal`      only recordings whose declared frequency is unusable, and only toward a refusal (never toward a computed result)
* `sampling_unsupported`  only the one scenario whose valid frequency the sampling cannot support, and only toward the existing sampling reason

No entry may touch a number: a changed measured value, magnitude, angle or RMS would fall in none of these kinds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import nf3c_approved_changes as approved
from tests.fixtures.nf3d_baselines.generate_nf3d_approved_changes import (
    PROVENANCE_KEYS, SAMPLING_SCENARIO, UNUSABLE_RECORDINGS, classify, scenario_of,
)
from tests.nf3d_diff_tools import ABSENT, apply_entries

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "nf3d_baselines" / "nf3d_approved_changes.json").read_text(encoding="utf-8"))
NF3D, NF3B = "nf3d_pre_migration_baseline", "nf3b_frozen_baselines"
DOCS = {
    NF3D: json.loads((FIXTURES / "nf3d_baselines" / "nf3d_pre_migration_baseline.json").read_text(encoding="utf-8")),
    NF3B: json.loads((FIXTURES / "nf3b_baselines" / "nf3b_frozen_baselines.json").read_text(encoding="utf-8")),
}
ALL = [(baseline, entry) for baseline, entries in MANIFEST["changes"].items() for entry in entries]
ORIGINS = {"recording_metadata", "import_supplied", "assumed_default", "manual", "unusable"}      # the NF-1 vocabulary; never extended

#: What a recording's own authority is, for the single-recording scenarios (an unusable recording is refused: no frequency was used, so no provenance).
RECORDING_ORIGIN = {
    "r50": "recording_metadata", "r60": "recording_metadata", "r50_fs4000": "recording_metadata", "r60_fs4000": "recording_metadata",
    "r60_fs4096": "recording_metadata", "r50_fs4096": "recording_metadata", "declared_50_on_60hz_signal": "recording_metadata",
    "assumed_50": "assumed_default", "assumed_on_60hz_signal": "assumed_default",
}


class TestTheManifestIsComplete:
    def test_it_covers_exactly_the_two_baselines(self):
        assert set(MANIFEST["changes"]) == {NF3D, NF3B}

    def test_every_entry_has_an_approved_kind_and_is_classified_by_the_generator_the_same_way(self):
        for baseline, entry in ALL:
            assert entry["kind"] in MANIFEST["kinds"]
            assert classify(baseline, tuple(entry["path"]), entry["before"], entry["after"]) == entry["kind"], entry["path"]

    @pytest.mark.parametrize("baseline", [NF3D, NF3B])
    def test_every_entry_matches_the_historical_record_plus_the_nf3c_overlay(self, baseline):
        base = approved.apply_approved(DOCS[baseline], baseline, include_nf3d=False)
        apply_entries(base, MANIFEST["changes"][baseline])          # raises when a recorded `before` no longer matches

    def test_no_entry_is_listed_twice(self):
        paths = [(b, tuple(e["path"])) for b, e in ALL]
        assert len(paths) == len(set(paths))


class TestProvenanceAddedIsAdditiveAndTruthful:
    ENTRIES = [(b, e) for b, e in ALL if e["kind"] == "provenance_added"]

    def test_there_are_provenance_entries(self):
        assert len(self.ENTRIES) > 200

    def test_only_the_three_new_keys_are_added_and_nothing_existed_before(self):
        for _baseline, entry in self.ENTRIES:
            assert entry["path"][-1] in PROVENANCE_KEYS
            assert entry["before"] == ABSENT

    def test_values_are_in_the_nf1_vocabulary(self):
        for _baseline, entry in self.ENTRIES:
            leaf, value = entry["path"][-1], entry["after"]
            if leaf == "nominal_frequency_origin":
                assert value is None or value in ORIGINS
            elif leaf == "nominal_frequency_revision":
                assert value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
            else:
                assert isinstance(value, list)
                for source in value:
                    assert set(source) == {"source_id", "origin", "revision"} and source["origin"] in ORIGINS

    def test_an_explicit_override_carries_no_provenance(self):
        for baseline, entry in self.ENTRIES:
            if baseline == NF3D and entry["path"][0] == "overrides":
                assert entry["after"] in (None, [])

    def test_a_single_recordings_origin_is_its_own_authority_never_another(self):
        for baseline, entry in self.ENTRIES:
            if entry["path"][-1] != "nominal_frequency_origin" or entry["after"] is None:
                continue
            scenario = scenario_of(baseline, tuple(entry["path"]))
            if scenario in RECORDING_ORIGIN:
                assert entry["after"] == RECORDING_ORIGIN[scenario], entry["path"]

    def test_an_unusable_recording_reports_no_origin_because_no_frequency_was_used(self):
        for baseline, entry in self.ENTRIES:
            if scenario_of(baseline, tuple(entry["path"])) in UNUSABLE_RECORDINGS:
                assert entry["after"] in (None, [], 0) or entry["path"][-1] == "nominal_frequency_revision"

    def test_a_revision_is_zero_when_no_engineer_value_exists(self):
        for _baseline, entry in self.ENTRIES:
            if entry["path"][-1] == "nominal_frequency_revision" and entry["after"] is not None:
                assert entry["after"] == 0           # the baselines contain no Manual value; Manual is covered by test_nf3d_behaviour

    def test_no_manual_origin_exists_in_the_gate_closed_baselines(self):
        assert all(e["after"] != "manual" for _b, e in self.ENTRIES if e["path"][-1] == "nominal_frequency_origin")


class TestUnusableRefusalIsOnlyTowardARefusal:
    ENTRIES = [(b, e) for b, e in ALL if e["kind"] == "unusable_refusal"]

    def test_only_unusable_recordings_are_involved(self):
        for baseline, entry in self.ENTRIES:
            assert scenario_of(baseline, tuple(entry["path"])) in UNUSABLE_RECORDINGS | {"one_unusable"}

    def test_no_entry_introduces_a_computed_status_or_a_number(self):
        for _baseline, entry in self.ENTRIES:
            after = entry["after"]
            assert after != "computed"
            assert not (isinstance(after, (int, float)) and not isinstance(after, bool) and entry["path"][-1] != "status")
            if isinstance(after, dict):
                assert after.get("status") != "computed"

    def test_the_unusable_value_is_never_echoed_as_the_reference_frequency(self):
        for _baseline, entry in self.ENTRIES:
            if entry["path"][-1] == "reference_frequency_hz":
                assert entry["after"] is None

    def test_every_legacy_http_500_becomes_a_typed_200(self):
        for _baseline, entry in self.ENTRIES:
            if entry["path"][-1] == "status" and entry["before"] == 500:
                assert entry["after"] == 200
            if entry["path"][-1] == "body" and entry["before"] == "Internal Server Error":
                assert isinstance(entry["after"], (dict, list))

    def test_the_reason_code_is_the_established_one_never_a_new_vocabulary(self):
        for _baseline, entry in self.ENTRIES:
            if entry["path"][-1] == "reason_code":
                assert entry["after"] in ("invalid_reference_frequency", None)


class TestSamplingUnsupportedIsOnlyTheExistingReason:
    ENTRIES = [(b, e) for b, e in ALL if e["kind"] == "sampling_unsupported"]

    def test_only_the_one_scenario(self):
        assert self.ENTRIES
        for baseline, entry in self.ENTRIES:
            assert scenario_of(baseline, tuple(entry["path"])) == SAMPLING_SCENARIO

    def test_only_toward_insufficient_sampling_density_or_its_explanation(self):
        for _baseline, entry in self.ENTRIES:
            if entry["path"][-1] in PROVENANCE_KEYS:
                continue
            after = entry["after"]
            assert after == "insufficient_sampling_density" or (isinstance(after, str) and "samples per cycle" in after), entry
            if entry["path"][-1] == "reason_code" or entry["path"][-1] in ("Ia", "Va", "Vb", "Vc"):
                assert entry["before"] == "waveform_form_not_eligible"
