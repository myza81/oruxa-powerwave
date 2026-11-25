"""NF-3C Phase A -- the pre-migration characterisation baseline (closes NF-3B handover gaps G-1 and G-2).

HISTORICAL BEHAVIOUR, NOT ENGINEERING ORACLES. `nf3c_pre_migration_baseline.json` was generated from the unmodified NF-3B tree before any
NF-3C change. Section 1 states the historical facts as readable sentences (what the code did, including defects). Section 2 compares the
code under test with that record after applying only the approved changes in `nf3c_approved_changes.py`, so unchanged outputs are proved
and every change is explicit. In Phase A the list is empty and this file passes against the unmodified code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import nf3c_approved_changes as approved
from tests import nf3c_baseline_scenarios as scenarios
from tests.test_nf3b_frozen_baselines import _same

HISTORICAL = json.loads((Path(__file__).parent / "fixtures" / "nf3c_baselines" / "nf3c_pre_migration_baseline.json").read_text(encoding="utf-8"))
H = HISTORICAL["outcomes"]
KEY = "nf3c_pre_migration_baseline"


@pytest.fixture(scope="module")
def current(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3c")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local")
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        return scenarios.run_all(client)


# ------------------------------------------------------------------------------------------ 1. what the code did
class TestHistoricalFacts:
    """Each test is a fact about the NF-3B tip. None is approved as correct; the NF-3C change (if any) is named."""

    @pytest.mark.parametrize("recording", ["declared_zero", "declared_nan", "declared_inf"])
    def test_G2_measurement_endpoint_is_http_500_for_an_unusable_declaration_oc1(self, recording):
        for quantity in scenarios.QUANTITIES:
            assert H["compliance_measurement_http"][recording][quantity] == {"status": 500, "body": "Internal Server Error"}

    @pytest.mark.parametrize("recording", ["declared_negative_50", "declared_0_5"])
    def test_G2_measurement_endpoint_already_reports_unresolved_for_negative_and_half_hertz(self, recording):
        for quantity in scenarios.QUANTITIES:
            r = H["compliance_measurement_http"][recording][quantity]
            assert (r["status"], r["body"]["status"]) == (200, "ambiguous_measurement_metadata")

    def test_G2_a_declared_1001_hz_is_classified_and_the_measurement_is_available_oc2(self):
        r = H["compliance_measurement_http"]["declared_1001"]
        assert r["phase_a_lg_rms"]["body"]["status"] == "available"
        assert r["phase_ab_ll_rms"]["body"]["status"] == "unsupported_representation"       # classified as already-RMS

    @pytest.mark.parametrize("recording", ["r50", "r60", "assumed_50"])
    def test_G2_ordinary_and_assumed_recordings_are_available(self, recording):
        for quantity in scenarios.QUANTITIES:
            assert H["compliance_measurement_http"][recording][quantity]["body"]["status"] == "available"

    def test_G1_a_ben_upload_supplied_frequency_reports_recording_metadata_in_the_oscillation_response_oc7(self):
        ben = H["ben_import_supplied_http"]
        for label, hz in (("supplied_60", 60.0), ("supplied_50_explicit", 50.0)):
            assert ben[label]["nominal_frequency_endpoint"]["origin"] == "import_supplied"            # the authority already knows
            body = ben[label]["oscillation_representation"]["body"]
            assert (body["nominal_frequency_hz"], body["nominal_frequency_origin"]) == (hz, "recording_metadata")   # the consumer does not

    def test_G1_a_ben_upload_without_a_frequency_is_assumed_default(self):
        body = H["ben_import_supplied_http"]["not_supplied_assumed"]["oscillation_representation"]["body"]
        assert (body["nominal_frequency_hz"], body["nominal_frequency_origin"]) == (50.0, "assumed_default")

    def test_the_oscillation_wire_value_set_today_is_two_origins_and_an_unusable_value_is_labelled_recording_metadata_oc8(self):
        origins = {r["body"]["nominal_frequency_origin"] for r in H["oscillation_representation_http"].values()}
        assert origins == {"recording_metadata", "assumed_default"}
        for key in ("declared_zero", "declared_nan", "declared_negative_50", "declared_1001", "declared_0_5", "declared_inf"):
            body = H["oscillation_representation_http"][key]["body"]
            assert (body["status"], body["reason_code"], body["nominal_frequency_origin"]) == ("unavailable", "invalid_nominal_frequency", "recording_metadata")

    def test_the_oscillation_wire_value_of_a_declared_nan_or_infinity_is_null(self):
        for key in ("declared_nan", "declared_inf"):
            assert H["oscillation_representation_http"][key]["body"]["nominal_frequency_hz"] is None

    def test_the_historical_responses_carry_no_revision_field(self):
        assert all("nominal_frequency_revision" not in r["body"] for r in H["oscillation_representation_http"].values())


# ------------------------------------------------------------------------ 2. current code versus history plus approved changes
class TestCurrentBehaviourEqualsHistoryPlusApprovedChanges:
    @pytest.mark.parametrize("group", sorted(H))
    def test_group(self, current, group):
        expected = approved.apply_approved(HISTORICAL, KEY)
        assert _same(expected[group], current[group], group) == []

    def test_every_approved_change_still_matches_the_historical_record(self):
        approved.apply_approved(HISTORICAL, KEY)
