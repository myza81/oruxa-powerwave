"""NF-3E Phase A -- the characterisation baseline of stored calculated channels against a recording's nominal frequency.

HISTORICAL BEHAVIOUR, NOT ENGINEERING ORACLES. `nf3e_phase_a_baseline.json` was generated from the unmodified NF-3D tip (`65390d3`) before any
NF-3E change. Section 1 states the facts as readable sentences, gaps included: the central accessor and the NF-1 endpoint move with a
recording's frequency, but nothing in the channel inventory, the waveform response or the stored parameters says that a stored channel was
computed with another frequency (the gap NF-3E, O-4, closes). Section 2 compares the code under test with that record. In Phase A nothing in
production changes, so it passes against the unmodified code; a later NF-3E commit that changes a recorded outcome on purpose edits only the
affected entries, in a reviewed commit that says why. Never regenerate the file to make a failing test pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import nf3e_baseline_scenarios as scenarios
from tests.test_nf3b_frozen_baselines import _same

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "nf3e_baselines" / "nf3e_phase_a_baseline.json").read_text(encoding="utf-8"))
H = BASELINE["outcomes"]


@pytest.fixture(scope="module")
def current(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3e")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
        nominal_frequency_manual_override_enabled=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        return scenarios.run_all(client)


class TestBaselineIntegrity:
    def test_the_baseline_was_generated_from_the_nf3d_tip(self):
        assert BASELINE["baseline_git_sha"].startswith("65390d3")
        assert BASELINE["schema"] == 1

    def test_every_scenario_group_is_present(self):
        assert set(H) == {"rms_after_manual_change", "dag", "two_recordings", "remove_reference_recording", "power_channels",
                          "frequency_independent_operations", "unusable_recording", "rms_frequency_parameter_validation"}


class TestHistoricalFacts:
    """Facts about the NF-3D tip. They describe the gap NF-3E addresses; none is approved as the desired behaviour."""

    def test_the_channel_inventory_names_no_staleness_and_no_frequency_provenance_field(self):
        fields = H["dag"]["inventory_fields"]
        assert not [f for f in fields if "stale" in f or "frequency" in f or "revision" in f or "origin" in f]
        assert "parameters" in fields

    def test_a_frequency_change_leaves_the_inventory_the_waveform_and_the_stored_parameters_byte_identical(self):
        r = H["rms_after_manual_change"]
        assert r["inventory_unchanged_by_the_change"] is True
        assert r["before"]["waveform"] == r["after_manual_60"]["waveform"]
        assert r["before"]["stored"] == r["after_manual_60"]["stored"]
        assert H["dag"]["inventory_identical_after_change"] is True

    def test_a_stored_rms_channel_records_only_the_frequency_value_it_used_with_no_origin_or_revision(self):
        parameters = H["rms_after_manual_change"]["before"]["stored"]["parameters"]
        assert parameters == {"nominal_frequency_hz": 50.0, "rms_kind": "true_rms", "window_mode": "trailing"}

    def test_the_central_accessor_follows_the_recording_so_a_channel_has_the_frequency_of_its_reference_recording(self):
        r = H["rms_after_manual_change"]
        assert (r["before"]["accessor_for_channel"]["hz"], r["before"]["accessor_for_channel"]["origin"]) == (50.0, "recording_metadata")
        after = r["after_manual_60"]["accessor_for_channel"]
        assert (after["hz"], after["origin"], after["revision"]) == (60.0, "manual", 1)
        assert H["dag"]["accessor_for_top_of_dag"]["hz"] == 60.0

    def test_the_readiness_identity_proposes_a_new_step_after_a_change_and_leaves_the_old_channel_matching_its_own_frequency(self):
        r = H["rms_after_manual_change"]
        assert (r["before"]["equivalent_at_50"], r["before"]["equivalent_at_60"]) == ("rms_va_50", None)
        assert (r["after_manual_60"]["equivalent_at_50"], r["after_manual_60"]["equivalent_at_60"]) == ("rms_va_50", None)   # a 60 Hz step is NEW
        assert r["created_60_on_the_same_input"]["status"] == 201
        assert r["both_channels_afterwards"]["equivalent_at_60"] == "rms_va_60"

    def test_both_channels_stay_in_the_inventory_and_the_old_one_is_never_recomputed_overwritten_or_removed(self):
        r = H["rms_after_manual_change"]
        assert r["both_channels_afterwards"]["inventory"]["names"] == ["rms_va_50", "rms_va_60"]
        assert r["both_channels_afterwards"]["waveform_50"] == r["before"]["waveform"]
        assert r["after_auto"]["waveform_50"] == r["before"]["waveform"]

    def test_returning_to_auto_moves_the_revision_again_and_the_stored_channel_matches_the_recording_again(self):
        auto = H["rms_after_manual_change"]["after_auto"]
        assert (auto["recording"]["effective_hz"], auto["recording"]["origin"], auto["recording"]["revision"]) == (50.0, "recording_metadata", 2)

    def test_a_derived_channel_stores_no_frequency_of_its_own(self):
        stored = H["dag"]["stored"]
        assert stored["add"]["parameters"] == {} and stored["abs"]["parameters"] == {}
        assert stored["add"]["dependency_count"] == 2 and stored["abs"]["dependency_count"] == 1
        assert "nominal_frequency_hz" in stored["rms"]["parameters"]

    def test_an_input_with_a_dependent_cannot_be_deleted(self):
        assert H["dag"]["delete_of_an_input_is_blocked_while_a_dependent_exists"]["code"]["detail"]["code"] == "calculated_channel_has_dependents"

    def test_a_channel_over_two_recordings_takes_its_frequency_from_the_first_recording_only(self):
        t = H["two_recordings"]
        assert t["reference_source_is_the_first_input_recording"] is True
        assert (t["accessor_for_sum"]["hz"], t["accessor_for_sum"]["origin"]) == (50.0, "recording_metadata")      # b was changed to 60 Hz
        assert t["recordings_combined"] == {"status": "mixed", "common_hz": None, "distinct_hz": [50.0, 60.0]}

    def test_removing_the_non_reference_recording_keeps_the_mixed_channel_but_its_waveform_is_unavailable(self):
        t = H["two_recordings"]
        assert t["remove_non_reference_recording"]["status"] == 204
        assert t["after_removal"]["inventory_names"] == ["rms_a", "sum_ab"]                       # rms_b (reference b) went with its recording
        assert t["after_removal"]["waveform_of_sum"]["status"] == 400
        assert t["after_removal"]["waveform_of_sum"]["body"]["detail"]["code"] == "incompatible_time_base"
        assert t["after_removal"]["waveform_of_rms_a"]["status"] == 200

    def test_removing_the_reference_recording_removes_every_channel_it_grounds_including_the_mixed_one(self):
        r = H["remove_reference_recording"]
        assert r["inventory_names"] == ["rms_b"] and r["sum_still_present"] is False
        assert r["waveform_of_rms_b"]["status"] == 200

    def test_power_channels_store_a_fixed_50_hz_on_a_recording_of_any_frequency(self):
        p = H["power_channels"]
        assert p["r50"]["stored"]["parameters"]["nominal_frequency_hz"] == 50.0
        assert p["r60"]["stored"]["parameters"]["nominal_frequency_hz"] == 50.0
        assert p["r60"]["accessor"]["hz"] == 60.0

    def test_operations_that_do_not_use_the_frequency_store_none(self):
        ops = H["frequency_independent_operations"]
        for label in ("addition", "subtraction", "absolute_value", "reverse_polarity"):
            assert ops[label]["stored_parameters"] == {}, label
        assert ops["multiply_constant"]["stored_parameters"] == {"constant": 2.0}
        assert "nominal_frequency_hz" not in ops["rocof_with_override"]["stored_parameters"]
        assert ops["rocof_override_not_given"]["status"] == 400

    def test_an_rms_channel_can_be_created_on_an_unusable_recording_with_an_explicit_frequency_and_the_accessor_then_refuses(self):
        b = H["unusable_recording"]
        assert b["recording"]["usable"] is False and b["created_with_explicit_50"]["status"] == 201
        assert (b["accessor_for_channel"]["usable"], b["accessor_for_channel"]["hz"]) == (False, None)
        assert b["equivalent_rms_at_50"] == "rms_bad"
        assert (b["after_manual"]["accessor_for_channel"]["hz"], b["after_manual"]["equivalent_rms_at_50"]) == (60.0, "rms_bad")

    def test_the_explicit_rms_frequency_is_validated_at_creation(self):
        v = H["rms_frequency_parameter_validation"]
        for label in ("missing", "zero", "negative", "below_range", "above_range", "string", "bool"):
            assert (v[label]["status"], v[label]["code"]) == (400, "invalid_nominal_frequency"), label
        assert v["valid_60"]["status"] == 201


class TestCurrentBehaviourEqualsHistory:
    @pytest.mark.parametrize("group", sorted(H))
    def test_group(self, current, group):
        assert _same(H[group], current[group], group) == []
