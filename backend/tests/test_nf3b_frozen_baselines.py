"""NF-3B -- the frozen nominal-frequency consumer baseline.

LEGACY CHARACTERISATION, NOT ENGINEERING ORACLES. These tests require that the consumers still do exactly what they did at the
NF-3A commit (`c70182c`), defects included: it is how "Auto is unchanged" is proved for every later slice. A value that appears
here is not approved as correct. The correct expectations are in `test_nf3b_independent_oracles.py`; where this file and that
one disagree, the difference IS the defect, and it is corrected in the slice named there.

The baseline is `tests/fixtures/nf3b_baselines/nf3b_frozen_baselines.json`, generated once from the pristine tree by
`generate_nf3b_baselines.py`. It is never regenerated to make a failing test pass: a slice that changes a consumer on purpose
edits only the affected entries, in a reviewed commit that says why.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import nf3b_baseline_scenarios as scenarios

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "nf3b_baselines" / "nf3b_frozen_baselines.json").read_text(encoding="utf-8"))
FROZEN = BASELINE["outcomes"]
R0_API = json.loads(
    (Path(__file__).parent / "fixtures" / "rms_golden" / "service_behaviour_baseline.json").read_text(encoding="utf-8"))["outcomes"]["api"]

REL, ABS = 1e-9, 1e-12


@pytest.fixture(scope="module")
def current(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3b")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
        git_sha="local", version="local",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        return scenarios.run_all(client)


def _same(frozen, now, path="") -> list[str]:
    """Every difference between the frozen and the current outcome, as readable paths."""
    if isinstance(frozen, dict) and isinstance(now, dict):
        problems = []
        for key in sorted(set(frozen) | set(now)):
            if key not in frozen or key not in now:
                problems.append(f"{path}/{key}: {'missing now' if key not in now else 'new'}")
            else:
                problems += _same(frozen[key], now[key], f"{path}/{key}")
        return problems
    if isinstance(frozen, list) and isinstance(now, list):
        if len(frozen) != len(now):
            return [f"{path}: length {len(frozen)} -> {len(now)}"]
        return [p for i, (a, b) in enumerate(zip(frozen, now)) for p in _same(a, b, f"{path}[{i}]")]
    if isinstance(frozen, float) and isinstance(now, float):
        return [] if math.isclose(frozen, now, rel_tol=REL, abs_tol=ABS) else [f"{path}: {frozen!r} -> {now!r}"]
    return [] if frozen == now and type(frozen) is type(now) else [f"{path}: {frozen!r} -> {now!r}"]


class TestBaselineIntegrity:
    def test_the_baseline_was_generated_from_the_nf3a_production_tree(self):
        assert BASELINE["baseline_git_sha"].startswith("c70182c")
        assert BASELINE["schema"] == 1

    def test_every_group_and_scenario_is_present(self):
        assert set(FROZEN) == {"kernels", "in_process", "http", "oscillation_selection", "power_gate"}
        assert set(FROZEN["in_process"]) == set(scenarios.RECORDING_SPECS)
        assert set(FROZEN["http"]) == set(scenarios.HTTP_RECORDINGS)
        assert len(FROZEN["kernels"]["grid"]) == len(scenarios.KERNEL_GRID)
        assert len(FROZEN["kernels"]["invalid"]) == len(scenarios.INVALID_NOMINAL)
        assert set(FROZEN["power_gate"]) == set(scenarios.POWER_GATE_CASES)

    def test_the_invalid_inputs_cover_zero_negative_nan_infinite_and_out_of_range(self):
        assert {"0.0", "-50.0", "nan", "inf", "-inf", "0.5", "1001.0"} == set(FROZEN["kernels"]["invalid"])


class TestFrozenConsumerBehaviourIsUnchanged:
    @pytest.mark.parametrize("group", ["kernels", "in_process", "oscillation_selection", "power_gate"])
    def test_pure_and_in_process_consumers(self, current, group):
        assert _same(FROZEN[group], current[group], group) == []

    @pytest.mark.parametrize("recording", sorted(scenarios.HTTP_RECORDINGS))
    def test_http_consumers_per_recording(self, current, recording):
        assert _same(FROZEN["http"][recording], current["http"][recording], recording) == []


class TestTheR0AndR1ABaselinesRemainTheAuthorityForTheirOwnBehaviour:
    """The RMS creation/eligibility behaviour (including the eligibility HTTP 500) and the COMTRADE importer behaviour are frozen
    by earlier slices and are deliberately not duplicated; this only proves the existing freeze still says what NF-3A reported."""

    def test_the_rms_eligibility_endpoint_still_records_http_500_for_a_zero_frequency(self):
        assert R0_API["rms-eligibility/instantaneous/0"]["status"] == 500

    def test_the_eligibility_endpoint_accepts_a_negative_frequency_with_a_200(self):
        assert R0_API["rms-eligibility/instantaneous/-50"]["status"] == 200


class TestLegacyDefectsAreFrozenAsDefectsNotAsApprovedBehaviour:
    """Each assertion names a behaviour that is WRONG and says which slice must invert it. They exist so a reviewer sees the
    defect as a sentence, not only as a diff in a JSON file. Do not 'fix' these here: change the consumer in the named slice."""

    def test_D_A_power_on_a_60hz_recording_uses_a_50hz_window_and_stores_50_nfF(self):
        r60 = FROZEN["http"]["r60"]["power_channels"]["active_power"]
        r50 = FROZEN["http"]["r50"]["power_channels"]["active_power"]
        assert r60["parameters"]["nominal_frequency_hz"] == 50.0                        # stored as 50.0 for a 60 Hz recording
        assert r60["values"]["mean"] == pytest.approx(0.000764177184507)
        assert r60["values"]["mean"] / r50["values"]["mean"] - 1.0 == pytest.approx(-0.1176, abs=1e-3)   # about -11.8 %

    def test_D_A_the_power_kernel_default_is_50hz_so_the_service_window_is_50hz_nfF(self):
        default = FROZEN["kernels"]["power"]["fs4800_signal60_windowdefault"]["single_phase"]["active_power"]["returns"]
        explicit50 = FROZEN["kernels"]["power"]["fs4800_signal60_window50"]["single_phase"]["active_power"]["returns"]
        assert default == explicit50                                                     # the omitted argument IS 50 Hz

    def test_D_B_the_eligibility_endpoint_returns_http_500_for_zero_nfE(self):
        assert R0_API["rms-eligibility/instantaneous/0"]["status"] == 500

    @pytest.mark.parametrize("recording,status", [("declared_zero", 500), ("declared_nan", 200)])
    def test_D_C_phasor_with_an_unusable_declared_frequency_nfD(self, recording, status):
        assert FROZEN["http"][recording]["phasor_voltage_three_phase"]["status"] == status

    @pytest.mark.parametrize("recording", ["declared_zero", "declared_nan"])
    def test_D_C_overcurrent_with_an_unusable_declared_frequency_is_http_500_nfD(self, recording):
        assert FROZEN["http"][recording]["overcurrent_phase_a"]["status"] == 500

    def test_D_C_compliance_measurement_raises_for_an_unusable_declared_frequency_nfC(self):
        assert FROZEN["in_process"]["declared_zero"]["compliance_measurement_input_type"] == {"raises": "ZeroDivisionError"}
        assert FROZEN["in_process"]["declared_nan"]["compliance_measurement_input_type"] == {"raises": "ValueError"}

    def test_D_C_the_raw_engine_functions_raise_for_zero_nfC_nfD(self):
        invalid = FROZEN["kernels"]["invalid"]["0.0"]
        for name in ("rms_trailing", "phasor_point", "overcurrent_rms_point"):
            assert invalid[name] == {"raises": "ZeroDivisionError"}, name

    def test_D_D_the_oscillation_frequency_comparison_depends_on_member_order_nfG(self):
        cases = FROZEN["oscillation_selection"]["component_55hz"]
        assert cases["first_50_second_60"] != cases["first_60_second_50"]               # same two recordings, swapped order
        assert cases["first_60_second_50"]["returns"]["nominal_values_in_evidence"] == ["60.0"]

    def test_D_A_the_power_prerequisite_gates_apply_50_hz_to_a_60_hz_recording_nfF(self):
        gate = FROZEN["power_gate"]
        short = gate["short_0_018s_between_the_60hz_and_50hz_window"]["recording_60hz"]["returns"]
        sparse = gate["sparse_220hz_between_the_50hz_and_60hz_density"]["recording_60hz"]["returns"]
        assert short["code"] == "rms_recording_too_short"          # 0.018 s is longer than a 60 Hz cycle (0.0167 s) but is refused
        assert sparse["created"] is True                           # 220 Hz is below the 240 Hz a 60 Hz window needs, yet accepted

    def test_a_60hz_signal_with_an_assumed_50_hz_is_judged_not_eligible_by_the_phasor_gate(self):
        # Context for the Manual value: today there is no way to correct this; the recording is simply refused.
        body = FROZEN["http"]["assumed_on_60hz_signal"]["phasor_voltage_three_phase"]["body"]
        assert (body["status"], body["reason_code"]) == ("needs_configuration", "waveform_form_not_eligible")

    def test_the_4096hz_ascii_recording_is_refused_as_irregularly_sampled_before_any_frequency_is_used(self):
        # An existing limitation unrelated to NF-3 (NF-3A section 16): the timestamps are written to 0.1 microsecond.
        body = FROZEN["http"]["r60_fs4096"]["phasor_voltage_three_phase"]["body"]
        assert body["reason_code"] == "irregular_sampling_not_supported"

    def test_the_declared_value_is_echoed_unchanged_by_the_source_summary(self):
        assert FROZEN["http"]["declared_zero"]["source_summary_nominal_frequency"] == 0.0
        assert FROZEN["http"]["r60"]["source_summary_nominal_frequency"] == 60.0
        assert FROZEN["http"]["assumed_50"]["source_summary_nominal_frequency"] == 50.0
