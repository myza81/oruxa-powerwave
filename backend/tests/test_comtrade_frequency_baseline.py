"""RMS display R1A -- frozen COMTRADE nominal-frequency parser baseline.

`fixtures/comtrade_frequency/comtrade_frequency_baseline.json` was generated from the pristine pre-R1A tree (SHA
recorded in the file) by `fixtures/comtrade_frequency/generate_comtrade_frequency_baseline.py`, before any production
change. Every scenario is re-run against the code under test and must reproduce the frozen outcome exactly:

* parser acceptance or rejection, exception class and message;
* the Python warnings raised (category and message);
* the effective nominal frequency in `RecordingMetadata` and `SamplingInformation`;
* a fingerprint of the whole parsed record (waveform samples, timestamps, channel descriptors, sampling and timing);
* the upload endpoint's status, response keys, response and stored nominal frequency.

The ONLY fields excluded from the exact comparison are the ones R1A is allowed to add information to, and only for the
scenarios in which the parser really substituted the default (`FALLBACK`): the provenance dict and what the
oscillation analysis derives from it. For every other scenario those fields are compared exactly too. The baseline is
never regenerated to make a failure pass.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from tests import comtrade_frequency_scenarios as scn
from tests import nf3c_approved_changes as approved

BASELINE = json.loads(scn.BASELINE_PATH.read_text(encoding="utf-8"))
OUTCOMES = BASELINE["outcomes"]          # HISTORICAL (pre-R1A tree). Never edited.
#: NF-3C: what the code must now produce = the historical record plus the explicit approved changes (an unusable declaration's oscillation
#: origin is `unusable`; every frequency, status, key and fingerprint is unchanged).
EXPECTED = approved.apply_approved(BASELINE, "comtrade_frequency_baseline")

#: Scenarios in which the pre-R1A parser substituted the default. Derived from the FROZEN baseline's own warnings,
#: never from the code under test.
FALLBACK = sorted(
    key for key, outcome in OUTCOMES["parser"].items()
    if any("Cannot parse nominal frequency" in w["message"] for w in outcome["warnings"])
)

PARSER_PROVENANCE_FIELDS = {"provenance"}
API_PROVENANCE_FIELDS = {"stored_preparation_provenance", "oscillation_frequency_and_origin"}


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=1)


def _without(outcome: dict, fields: set[str]) -> dict:
    return {k: v for k, v in outcome.items() if k not in fields}


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("comtrade_freq")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
        git_sha="local", version="local",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        api = scn.run_api_scenarios(client)
    return {"parser": scn.run_parser_scenarios(), "fixtures": scn.run_fixture_sweep(), "api": api}


class TestBaselineFile:
    def test_baseline_sha_is_recorded(self):
        assert len(BASELINE["baseline_git_sha"]) == 40

    def test_scenario_count_is_recorded(self):
        assert BASELINE["scenario_count"] == sum(len(v) for v in OUTCOMES.values()) >= 130

    def test_no_scenario_added_or_dropped(self, actual):
        for section in ("parser", "fixtures", "api"):
            assert set(actual[section]) == set(OUTCOMES[section])

    def test_the_fallback_scenarios_are_the_unparseable_and_empty_ones(self):
        """Verified pre-change behaviour: ONLY an `lf` that `float()` cannot parse is substituted."""
        assert FALLBACK, "baseline lost its fallback scenarios"
        for key in FALLBACK:
            assert key.startswith(("unparseable_", "rev1991_unparseable", "rev1991_empty", "rev2013_unparseable",
                                   "rev2013_empty", "other_unrecognised_rev_yr_unparseable_lf")), key
        for key in OUTCOMES["parser"]:
            if key.startswith("declared_"):
                assert key not in FALLBACK, key


@pytest.mark.parametrize("key", sorted(OUTCOMES["parser"]))
def test_parser_outcome_is_unchanged(actual, key):
    excluded = PARSER_PROVENANCE_FIELDS if key in FALLBACK else set()
    assert _canonical(_without(actual["parser"][key], excluded)) == _canonical(_without(OUTCOMES["parser"][key], excluded))


@pytest.mark.parametrize("key", sorted(OUTCOMES["fixtures"]))
def test_checked_in_fixture_outcome_is_unchanged(actual, key):
    assert _canonical(actual["fixtures"][key]) == _canonical(OUTCOMES["fixtures"][key])


@pytest.mark.parametrize("key", sorted(OUTCOMES["api"]))
def test_upload_outcome_is_unchanged(actual, key):
    excluded = API_PROVENANCE_FIELDS if key in FALLBACK else set()
    assert _canonical(_without(actual["api"][key], excluded)) == _canonical(_without(EXPECTED["api"][key], excluded))


class TestBaselineCoversTheRequiredCases:
    """Guards against a baseline that silently stopped exercising an owner-listed case."""

    @pytest.mark.parametrize("key,frequency", [("declared_50", "50.0"), ("declared_60", "60.0"), ("declared_25", "25.0"),
                                               ("declared_400", "400.0"), ("unparseable_text", "50.0"),
                                               ("unparseable_empty", "50.0"), ("declared_zero", "0.0"),
                                               ("declared_negative_50", "-50.0"), ("declared_nan", "nan"),
                                               ("declared_inf", "inf"), ("declared_out_of_range_1001", "1001.0")])
    def test_required_case_present_with_its_frozen_frequency(self, key, frequency):
        assert OUTCOMES["parser"][key]["metadata_nominal_frequency"] == frequency

    def test_missing_lf_is_a_rejection_not_a_fallback(self):
        assert OUTCOMES["parser"]["missing_lf_file_truncated"]["accepted"] is False
        assert OUTCOMES["parser"]["missing_lf_line_removed"]["accepted"] is False
