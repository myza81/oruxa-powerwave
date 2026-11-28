"""RMS display R0 -- frozen mathematical baseline for `evaluate_rms`.

These tests were committed BEFORE any production change and pass on the
unmodified pre-R0 tree (baseline SHA in `fixtures/rms_golden/manifest.json`).
They prove that the engine's numerical behaviour, and the code surrounding it
that R0 touches, did not change. They must not be "refreshed" to make a
failure pass: a failure is a regression to investigate.

Three levels of equality are asserted separately, so a failure names the
level that broke:

1. SHAPE/DTYPE   -- identical dtype and shape.
2. NUMERICAL     -- exact element equality with identical NaN positions
                    (`np.array_equal(..., equal_nan=True)` plus mask equality).
                    This is NOT a claim of binary identity: it also accepts
                    e.g. a different NaN payload or -0.0 vs 0.0.
3. BINARY        -- identical raw bytes (and SHA-256 equal to the manifest).
                    This is the strict claim.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import platform
import textwrap

import numpy as np
import pytest

import app.domain.calculated_channel as calculated_channel
import app.domain.rms_detector as rms_detector
from app.domain.calculated_channel import (
    MAX_NOMINAL_FREQUENCY_HZ,
    MIN_NOMINAL_FREQUENCY_HZ,
    MIN_SAMPLES_PER_CYCLE,
    evaluate_rms,
)
from app.domain.channel_classification import WAVEFORM_FORM_INSTANTANEOUS
from app.services import calculated_channel_service

from tests import rms_baseline_scenarios as scn

MANIFEST = json.loads(scn.MANIFEST_PATH.read_text(encoding="utf-8"))
CASE_NAMES = [case["name"] for case in MANIFEST["cases"]]
CASES = {case["name"]: case for case in MANIFEST["cases"]}


@pytest.fixture(scope="module")
def vectors():
    with np.load(scn.VECTORS_PATH) as data:
        return {key: data[key].copy() for key in data.files}


def _sha(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _environment_note() -> str:
    return (
        f"frozen on python {MANIFEST['python']} / numpy {MANIFEST['numpy']} / {MANIFEST['platform']}; "
        f"running on python {platform.python_version()} / numpy {np.__version__} / {platform.platform()}"
    )


class TestManifest:
    def test_baseline_sha_is_recorded(self):
        assert len(MANIFEST["baseline_git_sha"]) == 40
        assert MANIFEST["engine"] == "app.domain.calculated_channel.evaluate_rms"

    def test_covers_the_required_scenarios(self):
        names = set(CASE_NAMES)
        for required in (
            "sine_50hz_5000", "sine_50hz_4096", "sine_50hz_3200", "sine_50hz_960",
            "sine_60hz_5000", "sine_60hz_4096", "sine_60hz_3200", "sine_60hz_960",
            "irregular_jitter_50hz", "multirate_50hz", "harmonics_50hz_5000", "decaying_dc_50hz_5000",
            "fault_step_50hz_5000", "leading_nan_50hz_5000", "window_nan_50hz_5000", "all_nan_5000",
            "constant_dc_5000", "short_recording_5000", "sparse_150hz",
        ):
            assert required in names

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_frozen_arrays_match_their_manifest_hashes(self, vectors, name):
        case = CASES[name]
        assert _sha(vectors[f"{name}__time"]) == case["time_sha256"]
        assert _sha(vectors[f"{name}__values"]) == case["values_sha256"]
        assert _sha(vectors[f"{name}__out"]) == case["out_sha256"]


class TestEngineGoldenParity:
    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_engine_reproduces_the_frozen_output(self, vectors, name):
        case = CASES[name]
        time, values, frozen = vectors[f"{name}__time"], vectors[f"{name}__values"], vectors[f"{name}__out"]
        out = evaluate_rms(time, values, case["nominal_frequency_hz"])

        # 1. dtype / shape
        assert out.dtype == frozen.dtype, f"dtype {out.dtype} != frozen {frozen.dtype}"
        assert out.shape == frozen.shape, f"shape {out.shape} != frozen {frozen.shape}"

        # 2. exact numerical equality with identical NaN positions
        assert np.array_equal(np.isnan(out), np.isnan(frozen)), "NaN positions differ from the frozen baseline"
        assert np.array_equal(out, frozen, equal_nan=True), "finite values differ from the frozen baseline"

        # 3. binary equality (the strict claim)
        if out.tobytes() != frozen.tobytes():
            differing = int(np.count_nonzero(out.view(np.uint64) != frozen.view(np.uint64)))
            pytest.fail(
                f"numerically equal but NOT binary identical: {differing} of {out.size} elements differ in raw bytes "
                f"({_environment_note()}). Report this difference; do not relax the check."
            )
        assert _sha(out) == case["out_sha256"]

    def test_quantised_observations_recorded_in_stage2_still_hold(self, vectors):
        """Accepted engine behaviour (Stage 2 report, section 6/13): non-integer samples per cycle give a small
        ripple; integer samples per cycle give none. Recorded as an independent, human-readable sanity check."""
        for name, tolerance in (("sine_50hz_4096", 0.06), ("sine_50hz_960", 0.6)):
            out = vectors[f"{name}__out"]
            finite = out[np.isfinite(out)]
            assert np.max(np.abs(finite - 100.0)) < tolerance
        for name in ("sine_50hz_5000", "sine_50hz_3200"):
            out = vectors[f"{name}__out"]
            finite = out[np.isfinite(out)]
            assert np.max(np.abs(finite - 100.0)) < 1e-9


def _ast_fingerprint(source: str) -> str:
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


class TestProtectedCodeTripwire:
    """Fingerprints of the mathematical engine, its three reused predicates and the detector module.

    Comments, docstrings, whitespace and line endings are ignored (the fingerprint is of the parsed syntax tree),
    so only a change of logic trips it. If one trips, the change must be a deliberate, owner-approved one: update the
    golden files from a clean engine commit and the fingerprint together, never the fingerprint alone."""

    EXPECTED = {
        "evaluate_rms": "99d19f8a4f5089d2476623bc9ee7f2989047bf97074f7d6cdad57f72bc9148e6",
        "nominal_frequency_valid": "7865601dc42ce925910f76553d1255667144b275dae0ea787f36af061076d36e",
        "rms_recording_long_enough": "02c4f4759aff1adb752b47e10159d899ad0fdd21da941aa362ea5a7c532246ab",
        "rms_sampling_dense_enough": "c3aa45119017132b05f7e0f4520e45e30c2838c49b41a5e69429d4312b11ab24",
    }
    DETECTOR_MODULE = "74b2f7a76c870094c7fffa308e6d15dd129cd17bb4cff74ec7c2768c941b4229"

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_engine_and_predicates_unchanged(self, name):
        assert _ast_fingerprint(inspect.getsource(getattr(calculated_channel, name))) == self.EXPECTED[name]

    def test_detector_module_unchanged(self):
        assert _ast_fingerprint(inspect.getsource(rms_detector)) == self.DETECTOR_MODULE

    def test_gate_constants_unchanged(self):
        assert (MIN_SAMPLES_PER_CYCLE, MIN_NOMINAL_FREQUENCY_HZ, MAX_NOMINAL_FREQUENCY_HZ) == (4, 1.0, 1000.0)


class TestCalculatedChannelsInvokeTheAuthoritativeEngine:
    """The existing Calculated Channels RMS path calls `evaluate_rms` exactly once, with the resolved input time,
    the effective (null-policy-applied) values and the nominal frequency, and stores its output unmodified.
    (A display-path spy belongs to R2: no display path exists in R0.)"""

    def _spy(self, monkeypatch):
        calls = []
        real = calculated_channel_service.evaluate_rms

        def spy(time, values, nominal_frequency_hz):
            calls.append((time.copy(), values.copy(), nominal_frequency_hz))
            return real(time, values, nominal_frequency_hz)

        monkeypatch.setattr(calculated_channel_service, "evaluate_rms", spy)
        return calls

    def test_single_call_with_resolved_inputs_and_stored_output(self, monkeypatch):
        time, values = scn.load_service_inputs()["svc_instantaneous"]
        env = scn.Env()
        env.add(scn.build_source("src1", time, values, form=WAVEFORM_FORM_INSTANTANEOUS))
        calls = self._spy(monkeypatch)
        result = scn.attempt_create(env)
        assert result["ok"] is True
        assert len(calls) == 1
        call_time, call_values, f = calls[0]
        assert call_time.tobytes() == time.tobytes()
        assert call_values.tobytes() == values.tobytes()
        assert f == 50.0 and isinstance(f, float)
        stored = env.calcs.list_for_workspace(scn.WS)[0]
        assert stored.values.tobytes() == evaluate_rms(time, values, 50.0).tobytes()

    def test_null_policy_zero_passes_the_substituted_values_to_the_engine(self, monkeypatch):
        time, values = scn.load_service_inputs()["svc_instantaneous_nan"]
        env = scn.Env()
        env.add(scn.build_source("src1", time, values, form=WAVEFORM_FORM_INSTANTANEOUS))
        calls = self._spy(monkeypatch)
        result = scn.attempt_create(env, null_policy="treat_null_as_zero")
        assert result["ok"] is True and len(calls) == 1
        passed = calls[0][1]
        assert not np.isnan(passed).any()
        assert passed[200] == 0.0 and passed[1200] == 0.0

    @pytest.mark.parametrize("frequency", [0, 0.5, 1001, float("nan"), True, "50"])
    def test_engine_not_called_when_frequency_invalid(self, monkeypatch, frequency):
        time, values = scn.load_service_inputs()["svc_instantaneous"]
        env = scn.Env()
        env.add(scn.build_source("src1", time, values, form=WAVEFORM_FORM_INSTANTANEOUS))
        calls = self._spy(monkeypatch)
        assert scn.attempt_create(env, parameters={"nominal_frequency_hz": frequency})["ok"] is False
        assert calls == []

    @pytest.mark.parametrize("data_key", ["svc_short_instantaneous", "svc_sparse_instantaneous", "svc_short_and_sparse"])
    def test_engine_not_called_when_a_hard_gate_fails(self, monkeypatch, data_key):
        time, values = scn.load_service_inputs()[data_key]
        env = scn.Env()
        env.add(scn.build_source("src1", time, values, form=WAVEFORM_FORM_INSTANTANEOUS))
        calls = self._spy(monkeypatch)
        assert scn.attempt_create(env, override=True)["ok"] is False
        assert calls == []
