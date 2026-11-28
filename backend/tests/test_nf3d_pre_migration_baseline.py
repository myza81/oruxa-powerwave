"""NF-3D Phase A -- the pre-migration characterisation baseline of the phasor family and overcurrent.

HISTORICAL BEHAVIOUR, NOT ENGINEERING ORACLES. `nf3d_pre_migration_baseline.json` was generated from the unmodified NF-3C tree (`446b566`)
before any NF-3D change. Section 1 states the historical facts as readable sentences, defects included (the HTTP 500s are LEGACY DEFECTS, not
approved behaviour). Section 2 compares the code under test with that record after applying only the approved changes in
`nf3c_approved_changes.py` (NF-3D section), so unchanged outputs are proved and every change is explicit. In Phase A that list is empty and
this file passes against the unmodified code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import nf3c_approved_changes as approved
from tests import nf3d_baseline_scenarios as scenarios
from tests.test_nf3b_frozen_baselines import REL, _same

HISTORICAL = json.loads((Path(__file__).parent / "fixtures" / "nf3d_baselines" / "nf3d_pre_migration_baseline.json").read_text(encoding="utf-8"))
H = HISTORICAL["outcomes"]
KEY = "nf3d_pre_migration_baseline"
SURFACES = ["phasor_voltage_three_phase", "phasor_current_phase_a_fault", "phasor_diagram_fault", "overcurrent_pre_fault", "overcurrent_fault",
            "overcurrent_settled", "impedance_a", "impedance_locus_a", "sequence_components", "distance_ab"]
SERVER_ERROR = {"status": 500, "body": "Internal Server Error"}


@pytest.fixture(scope="module")
def current(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3d")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local")
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        return scenarios.run_all(client)


def body(recording, surface, group="recordings"):
    return H[group][recording][surface]["body"]


class TestHistoricalFacts:
    """Facts about the NF-3C tip. None is approved as correct; the NF-3D change (if any) is named."""

    @pytest.mark.parametrize("recording", ["declared_zero", "declared_inf"])
    def test_a_declared_zero_or_infinity_is_http_500_on_every_surface_legacy_defect(self, recording):
        for surface in SURFACES + ["input_readiness_overcurrent", "line_to_line_readiness"]:
            assert H["recordings"][recording][surface] == SERVER_ERROR, surface

    def test_a_declared_nan_is_http_500_for_overcurrent_and_a_frequency_conflict_for_the_phasor_family_legacy_defect(self):
        for surface in ("overcurrent_pre_fault", "overcurrent_fault", "overcurrent_settled", "input_readiness_overcurrent"):
            assert H["recordings"]["declared_nan"][surface] == SERVER_ERROR, surface
        for surface in ("phasor_voltage_three_phase", "phasor_diagram_fault", "sequence_components"):
            assert body("declared_nan", surface)["reason_code"] == "reference_frequency_conflict", surface

    @pytest.mark.parametrize("recording", ["declared_negative_50", "declared_0_5", "declared_1001"])
    def test_other_unusable_declarations_are_refused_as_waveform_form_not_eligible_which_names_the_wrong_cause(self, recording):
        assert body(recording, "phasor_voltage_three_phase")["reason_code"] == "waveform_form_not_eligible"
        assert body(recording, "overcurrent_fault")["reason_code"] == "waveform_form_not_eligible"

    def test_a_valid_override_the_sampling_cannot_support_is_also_waveform_form_not_eligible_which_names_the_wrong_cause(self):
        o = H["overrides"]["r50_override_1000_unsupported_by_sampling"]
        assert o["phasor_voltage_three_phase"]["body"]["reason_code"] == "waveform_form_not_eligible"
        assert o["overcurrent_fault"]["body"]["reason_code"] == "waveform_form_not_eligible"

    def test_an_invalid_explicit_override_is_already_a_typed_refusal(self):
        for label in ("r50_override_zero", "r50_override_negative", "r50_override_1001"):
            for surface in SURFACES:
                if surface == "impedance_locus_a":
                    continue
                assert H["overrides"][label][surface]["body"]["reason_code"] == "invalid_reference_frequency", (label, surface)

    def test_an_explicit_override_wins_even_over_an_unusable_declaration(self):
        for label in ("declared_zero_with_override_50", "declared_nan_with_override_50"):
            assert H["overrides"][label]["phasor_voltage_three_phase"]["body"]["status"] == "computed"
            assert H["overrides"][label]["overcurrent_fault"]["body"]["status"] == "computed"

    def test_ordinary_valid_recordings_are_computed_with_the_declared_frequency_and_no_provenance(self):
        for recording, hz in (("r50", 50.0), ("r60", 60.0), ("r50_fs4000", 50.0), ("r60_fs4000", 60.0), ("assumed_50", 50.0)):
            for surface in ("phasor_voltage_three_phase", "overcurrent_fault", "sequence_components", "impedance_a", "distance_ab"):
                b = body(recording, surface)
                assert (b["status"], b["reference_frequency_hz"]) == ("computed", hz), (recording, surface)
                assert "nominal_frequency_origin" not in b and "nominal_frequency_revision" not in b

    def test_a_60hz_signal_in_a_recording_whose_frequency_was_assumed_or_declared_50_is_refused(self):
        for recording in ("assumed_on_60hz_signal", "declared_50_on_60hz_signal"):
            assert body(recording, "phasor_voltage_three_phase")["reason_code"] == "waveform_form_not_eligible"

    def test_a_4096hz_ascii_recording_is_refused_as_irregularly_sampled_before_any_frequency_is_used(self):
        assert body("r60_fs4096", "overcurrent_fault")["reason_code"] == "irregular_sampling_not_supported"

    def test_recordings_with_different_frequencies_conflict_and_an_unusable_second_recording_is_a_500_for_overcurrent(self):
        t = H["two_recordings"]
        assert t["differ_50_60"]["phasor_diagram_fault"]["body"]["reason_code"] == "reference_frequency_conflict"
        assert t["differ_50_60"]["overcurrent_fault"]["body"]["reference_frequency_hz"] == 60.0        # overcurrent reads only the current role
        assert t["one_unusable"]["overcurrent_fault"] == SERVER_ERROR
        assert t["one_unusable"]["phasor_diagram_fault"]["body"]["reason_code"] == "reference_frequency_conflict"
        assert t["agree_50_50"]["phasor_diagram_fault"]["body"]["status"] == "computed"
        assert t["assumed_with_declared_50"]["phasor_diagram_fault"]["body"]["status"] == "computed"


#: The angle of a numerically negligible phasor is not a regression observable. A balanced three-phase set has a zero-sequence voltage that is only
#: round-off (frozen here: 2.4e-10 on a 100 scale, and up to 3.7e-8 for the 4 kHz record), and the angle of such a phasor is decided by the last bits of
#: its real and imaginary parts, which differ between platforms (Windows against Linux: 179.9943 against 179.9954 degrees) while the magnitude agrees to far
#: better than the comparison's own relative resolution. The floor IS that resolution: the established relative tolerance of `_same` (`REL`, 1e-9), applied
#: to the set's positive-sequence magnitude. A phasor smaller than that is zero as far as this comparison can tell, so its angle is undefined. (A floor of
#: 1e-10 was tried first and was not enough: the 4 kHz record's zero sequence is 3.7e-10 of the positive sequence.)
NOISE_FLOOR = REL


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _negligible_angles(expected: dict, actual: dict) -> set[str]:
    """Angle keys of a sequence-component set (`<name>_sequence_angle_deg`) that are not comparable: BOTH the expected and the actual magnitude of
    that sequence are at or below `NOISE_FLOOR` of the positive-sequence magnitude. A set without a positive-sequence magnitude has no scale, so
    nothing is skipped."""
    scales = [d.get("positive_sequence_magnitude") for d in (expected, actual)]
    if not all(_is_number(v) for v in scales):
        return set()
    limit = NOISE_FLOOR * max(abs(v) for v in scales)
    skipped = set()
    for key in expected:
        if not key.endswith("_sequence_angle_deg") or key not in actual:       # a key that appeared or disappeared is always reported
            continue
        magnitude_key = key[: -len("_angle_deg")] + "_magnitude"
        magnitudes = [d.get(magnitude_key) for d in (expected, actual)]
        if all(_is_number(m) for m in magnitudes) and all(abs(m) <= limit for m in magnitudes):
            skipped.add(key)
    return skipped


def _same_with_noise_floor(expected, actual, path="") -> list[str]:
    """`_same` (unchanged tolerances: REL 1e-9, ABS 1e-12), except that the angle of a negligible sequence-component phasor is not compared. The
    magnitude of every phasor is ALWAYS compared, and so is every angle that is not negligible on both sides."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        skipped = _negligible_angles(expected, actual)
        problems: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            if key in skipped:
                continue
            if key not in expected or key not in actual:
                problems.append(f"{path}/{key}: {'missing now' if key not in actual else 'new'}")
            else:
                problems += _same_with_noise_floor(expected[key], actual[key], f"{path}/{key}")
        return problems
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: length {len(expected)} -> {len(actual)}"]
        return [p for i, (a, b) in enumerate(zip(expected, actual)) for p in _same_with_noise_floor(a, b, f"{path}[{i}]")]
    return _same(expected, actual, path)


class TestCurrentBehaviourEqualsHistoryPlusApprovedChanges:
    @pytest.mark.parametrize("group", sorted(H))
    def test_group(self, current, group):
        expected = approved.apply_approved(HISTORICAL, KEY)
        assert _same_with_noise_floor(expected[group], current[group], group) == []

    def test_every_approved_change_still_matches_the_historical_record(self):
        approved.apply_approved(HISTORICAL, KEY)
