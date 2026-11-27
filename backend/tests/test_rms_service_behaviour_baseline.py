"""RMS display R0 -- frozen Calculated Channels RMS *behavioural* baseline.

`fixtures/rms_golden/service_behaviour_baseline.json` was generated from the
pristine pre-R0 tree (SHA recorded in the file) by
`fixtures/rms_golden/generate_rms_service_baseline.py`, before any production
change. Every scenario below is re-run against the code under test and must
reproduce the frozen outcome exactly:

* eligibility status, reason string and override requirement;
* exception class, code, message and attributes, and the VALIDATION PRECEDENCE
  (the multi-failure scenarios record which failure wins);
* the override-False / override-True outcomes;
* the created channel's metadata and provenance, and SHA-256 hashes of the raw
  bytes of its timestamps and samples;
* HTTP status and the normalised response body of the eligibility, create,
  list, waveform, cursor and peak endpoints (including an unhandled HTTP 500
  that the eligibility endpoint returns today for `nominal_frequency_hz = 0`).

A failure is a behaviour change to investigate. The baseline is never
regenerated to make it pass.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from tests import nf3e_approved_changes as approved
from tests import rms_baseline_scenarios as scn

BASELINE = json.loads(scn.SERVICE_BASELINE_PATH.read_text(encoding="utf-8"))      # the frozen HISTORY: never edited
# NF-3E (O-10, O-6): the explicitly approved changes, as data (tests/nf3e_approved_changes.py). Expected = history + approved changes.
EXPECTED = approved.apply_r0(BASELINE["outcomes"])
SERVICE_KEYS = [(group, key) for group, items in BASELINE["outcomes"]["service"].items() for key in items]
API_KEYS = list(BASELINE["outcomes"]["api"])


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("rms_baseline")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
        git_sha="local", version="local",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        api = scn.run_api_scenarios(client)
    return {"service": scn.run_service_scenarios(), "api": api}


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=1)


class TestBaselineFile:
    def test_baseline_was_frozen_on_the_manifest_baseline_commit(self):
        manifest = json.loads(scn.MANIFEST_PATH.read_text(encoding="utf-8"))
        assert BASELINE["baseline_git_sha"] == manifest["baseline_git_sha"]

    def test_scenario_count_is_recorded(self):
        assert BASELINE["scenario_count"] == len(SERVICE_KEYS) + len(API_KEYS) >= 140

    def test_no_scenario_added_or_dropped(self, actual):
        assert {g: set(v) for g, v in actual["service"].items()} == \
            {g: set(v) for g, v in BASELINE["outcomes"]["service"].items()}
        assert set(actual["api"]) == set(API_KEYS)


@pytest.mark.parametrize("group,key", SERVICE_KEYS)
def test_service_scenario_outcome_is_unchanged(actual, group, key):
    expected = EXPECTED["service"][group][key]
    assert _canonical(actual["service"][group][key]) == _canonical(expected)


@pytest.mark.parametrize("key", API_KEYS)
def test_api_scenario_outcome_is_unchanged(actual, key):
    expected = EXPECTED["api"][key]
    assert _canonical(actual["api"][key]) == _canonical(expected)


class TestBaselineCoversTheRequiredBehaviour:
    """Guards against a baseline that silently stopped exercising an owner-required behaviour."""

    def test_every_required_outcome_kind_is_present(self):
        text = json.dumps(BASELINE["outcomes"])
        for needle in (
            "rms_override_required", "rms_recording_too_short", "rms_sampling_too_sparse", "invalid_nominal_frequency",
            "invalid_calibration_authority", "require_manual_value_null", "likely_already_rms_or_magnitude",
            '"status": "suitable"', '"status": "uncertain"', "propagate_null", "treat_null_as_zero",
            "estimate_missing_data", "Internal Server Error",
        ):
            assert needle in text, needle

    def test_eligibility_wording_is_frozen(self):
        text = json.dumps(BASELINE["outcomes"])
        for sentence in (
            "Input is explicitly marked instantaneous. Input appears suitable for RMS.",
            "This channel is already identified as RMS or magnitude data. Applying RMS again is not recommended.",
            "Input appears suitable for RMS.",
            "Signal form could not be confirmed. Verify that this is an instantaneous waveform before applying RMS.",
        ):
            assert sentence in text
