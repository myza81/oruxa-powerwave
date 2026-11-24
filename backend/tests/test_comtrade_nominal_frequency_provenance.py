"""RMS display R1A -- COMTRADE nominal-frequency provenance.

An unparseable `lf` line is replaced by 50 Hz by the parser. R1A records that substitution with the key BEN and
CSV/Excel imports already use (`nominal_frequency_assumed`, in the source's `preparation_provenance`) and changes
nothing else. The frozen pre-R1A behaviour lives in `test_comtrade_frequency_baseline.py`; this module pins the
provenance semantics on top of it.
"""

from __future__ import annotations

import ast
import json
import re
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.ben.provider import BenProvider
from app.providers.comtrade import ComtradeProvider, _parse_cfg

from tests import comtrade_frequency_scenarios as scn

APP_DIR = Path(__file__).resolve().parents[1] / "app"

BASELINE = json.loads(scn.BASELINE_PATH.read_text(encoding="utf-8"))["outcomes"]
FALLBACK = sorted(
    key for key, outcome in BASELINE["parser"].items()
    if any("Cannot parse nominal frequency" in w["message"] for w in outcome["warnings"])
)
ACCEPTED_NOT_FALLBACK = sorted(
    key for key, outcome in BASELINE["parser"].items() if outcome["accepted"] and key not in FALLBACK
)
REJECTED = sorted(key for key, outcome in BASELINE["parser"].items() if not outcome["accepted"])

ASSUMED = {"source_format": "COMTRADE", "nominal_frequency_assumed": True}


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("comtrade_prov")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
        git_sha="local", version="local",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        api = scn.run_api_scenarios(client)
    return {"parser": scn.run_parser_scenarios(), "api": api}


class TestAssumedFrequencyIsRecorded:
    @pytest.mark.parametrize("key", FALLBACK)
    def test_parser_reports_the_substitution(self, actual, key):
        outcome = actual["parser"][key]
        assert outcome["provenance"] == ASSUMED
        assert outcome["metadata_nominal_frequency"] == "50.0" == outcome["sampling_nominal_frequency"]

    @pytest.mark.parametrize("key", FALLBACK)
    def test_import_stores_it_and_the_existing_consumer_sees_it(self, actual, key):
        entry = actual["api"][key]
        assert entry["stored_preparation_provenance"] == ASSUMED
        assert entry["stored_nominal_frequency"] == "50.0"
        # The oscillation analysis already reads this key for BEN/CSV; it now reports the origin for COMTRADE too.
        assert entry["oscillation_frequency_and_origin"] == ["50.0", "assumed_default"]

    @pytest.mark.parametrize("key", FALLBACK)
    def test_the_warning_is_unchanged_and_still_single(self, actual, key):
        assert actual["parser"][key]["warnings"] == BASELINE["parser"][key]["warnings"]
        assert sum("Cannot parse nominal frequency" in w["message"] for w in actual["parser"][key]["warnings"]) == 1

    def test_the_fallback_set_is_exactly_the_unparseable_set(self):
        assert FALLBACK
        assert all(key.startswith(("unparseable_", "rev1991_", "rev2013_", "other_unrecognised")) for key in FALLBACK)
        assert not any(key.startswith("declared_") for key in FALLBACK)


class TestDeclaredFrequencyIsNotMarkedAssumed:
    @pytest.mark.parametrize("key", ACCEPTED_NOT_FALLBACK)
    def test_parser_provenance_is_exactly_the_frozen_one(self, actual, key):
        assert actual["parser"][key]["provenance"] == BASELINE["parser"][key]["provenance"]
        assert actual["parser"][key]["provenance"] is None

    @pytest.mark.parametrize("key", ACCEPTED_NOT_FALLBACK)
    def test_import_reports_a_recording_metadata_origin(self, actual, key):
        entry = actual["api"][key]
        assert entry["stored_preparation_provenance"] is None
        assert entry["oscillation_frequency_and_origin"][1] == "recording_metadata"

    def test_declared_50_is_distinguishable_from_assumed_50(self, actual):
        declared, assumed = actual["api"]["declared_50"], actual["api"]["unparseable_text"]
        assert declared["stored_nominal_frequency"] == assumed["stored_nominal_frequency"] == "50.0"
        assert declared["oscillation_frequency_and_origin"] == ["50.0", "recording_metadata"]
        assert assumed["oscillation_frequency_and_origin"] == ["50.0", "assumed_default"]

    def test_declared_60_remains_declared(self, actual):
        for key in ("declared_60", "declared_60_0", "rev1991_declared_60", "rev2013_declared_60"):
            assert actual["parser"][key]["metadata_nominal_frequency"] == "60.0"
            assert actual["parser"][key]["provenance"] is None
            assert actual["api"][key]["oscillation_frequency_and_origin"] == ["60.0", "recording_metadata"]

    @pytest.mark.parametrize("key,value", [
        ("declared_zero", "0.0"), ("declared_negative_zero", "-0.0"), ("declared_negative_50", "-50.0"),
        ("declared_nan", "nan"), ("declared_inf", "inf"), ("declared_negative_inf", "-inf"),
        ("declared_out_of_range_1001", "1001.0"), ("declared_out_of_range_0_5", "0.5"), ("declared_tiny", "1e-09"),
    ])
    def test_an_invalid_declared_value_is_neither_assumed_nor_replaced(self, actual, key, value):
        """No new fallback: an explicitly invalid declared value keeps its value and is not marked as substituted."""
        assert actual["parser"][key]["metadata_nominal_frequency"] == value
        assert actual["parser"][key]["frequency_valid_for_rms"] is False
        assert actual["parser"][key]["provenance"] is None
        assert actual["api"][key]["stored_preparation_provenance"] is None

    @pytest.mark.parametrize("key", [
        "other_unrecognised_rev_yr_declared_60", "other_nonstandard_rev_yr_2005_declared_60",
        "other_unparseable_timemult_declared_60",
    ])
    def test_other_parser_fallbacks_are_not_frequency_substitutions(self, actual, key):
        assert actual["parser"][key]["provenance"] is None
        assert actual["parser"][key]["metadata_nominal_frequency"] == "60.0"


class TestRejectionsAreUnchanged:
    @pytest.mark.parametrize("key", REJECTED)
    def test_still_rejected_with_the_same_error(self, actual, key):
        assert actual["parser"][key] == BASELINE["parser"][key]
        assert actual["api"][key] == BASELINE["api"][key]


class TestCombinedWithChannelRenames:
    CFG = (
        "SYNTH_STATION,SYNTH_DEV,1999\n"
        "2,1A,1D\n"
        "1,POWER,A,,MW,1.0,0.0,0,-32767,32767,1.0,1.0,P\n"
        "1,POWER,,,0\n"
        "{lf}\n"
        "1\n"
        "4000.0,2\n"
        "06/03/2026,10:00:00.000000\n"
        "06/03/2026,10:00:00.005000\n"
        "ASCII\n"
        "1.0\n"
    )
    DAT = "1,0,5,0\n2,250,6,1\n"
    RENAME = {"name": "POWER_1", "source_name": "POWER", "kind": "digital", "index": 1}

    def _load(self, tmp_path, lf):
        (tmp_path / "e.cfg").write_text(self.CFG.format(lf=lf))
        (tmp_path / "e.dat").write_text(self.DAT)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return ComtradeProvider().load_with_provenance(tmp_path / "e.cfg")

    def test_renames_and_assumed_frequency_are_reported_together(self, tmp_path):
        record, provenance = self._load(tmp_path, "abc")
        assert provenance == {
            "source_format": "COMTRADE", "channel_renames": [self.RENAME], "nominal_frequency_assumed": True,
        }
        assert record.metadata.nominal_frequency == 50.0

    def test_renames_alone_are_reported_exactly_as_before(self, tmp_path):
        _, provenance = self._load(tmp_path, "60")
        assert provenance == {"source_format": "COMTRADE", "channel_renames": [self.RENAME]}


class TestExistingConventionIsReused:
    def test_same_key_and_value_type_as_the_ben_provider(self):
        assert BenProvider()._nominal_frequency_assumed is True
        ben_source = (APP_DIR / "providers" / "ben" / "provider.py").read_text(encoding="utf-8")
        assert '"nominal_frequency_assumed": self._nominal_frequency_assumed' in ben_source
        assert isinstance(ASSUMED["nominal_frequency_assumed"], bool)

    def test_no_separate_frequency_provenance_model_was_added(self):
        text = (APP_DIR / "providers" / "comtrade.py").read_text(encoding="utf-8")
        for forbidden in ("frequency_source", "frequency_origin", "frequency_provenance", "frequency_status"):
            assert forbidden not in text
        # Executable code (not the docstring) must not mention RMS: this is metadata, not an RMS feature.
        code = [n.id for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Name)]
        assert not [name for name in code if "rms" in name.lower()]

    def test_only_the_expected_modules_read_the_flag(self):
        """Consumer inventory tripwire: a new reader of `nominal_frequency_assumed` must be reviewed, because a
        COMTRADE source can now carry it."""
        readers = sorted(
            str(path.relative_to(APP_DIR)).replace("\\", "/") for path in APP_DIR.rglob("*.py")
            if re.search(r"nominal_frequency_assumed", path.read_text(encoding="utf-8"))
        )
        assert readers == [
            "domain/metadata.py",
            "domain/nominal_frequency.py",  # NF-1: the one recording-level resolver (DEC-217), the reviewed new reader
            "domain/oscillation_classification.py",
            "providers/ben/provider.py",
            "providers/comtrade.py",
            "services/oscillation_cross_signal_service.py",
            "services/oscillation_damping_service.py",
            "services/oscillation_representation_service.py",
            "services/oscillation_spectrum_service.py",
            "services/preparation_conversion_service.py",
        ]


class TestParserInternals:
    def test_a_declared_frequency_is_not_assumed(self, comtrade_fixtures_dir):
        assert _parse_cfg(comtrade_fixtures_dir / "synth_ascii.cfg").nominal_freq_assumed is False

    def test_every_loadable_checked_in_fixture_is_declared(self, comtrade_fixtures_dir):
        checked = 0
        for cfg in sorted(comtrade_fixtures_dir.glob("*.cfg")):
            try:
                parsed = _parse_cfg(cfg)
            except Exception:  # noqa: BLE001 -- three fixtures have no companion DAT; they are rejected today too
                continue
            assert parsed.nominal_freq_assumed is False, cfg.name
            checked += 1
        assert checked >= 15

    def test_plain_load_is_unchanged(self, tmp_path):
        (tmp_path / "e.cfg").write_text(scn.build_variants()["unparseable_text"])
        (tmp_path / "e.dat").write_text(scn._DAT)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            record = ComtradeProvider().load(tmp_path / "e.cfg")
        assert record.metadata.nominal_frequency == 50.0
        assert len([w for w in caught if "Cannot parse nominal frequency" in str(w.message)]) == 1
