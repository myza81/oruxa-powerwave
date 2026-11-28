"""RMS display R0 -- the shared prerequisites / input-form classification
(`app.domain.rms_prerequisites`) and the Calculated Channels service's use of it.

The frozen baselines (`test_rms_golden_vectors.py`, `test_rms_service_behaviour_baseline.py`) prove that nothing
observable changed. These tests pin the new module's own contract and the separation of concerns:

* mathematics stays in `evaluate_rms` (this module defines none);
* shared prerequisites/classification carry no policy: no override, no wording, no exceptions;
* the Calculated Channels service delegates to them and keeps its own policy.
"""

from __future__ import annotations

import ast
import inspect

import numpy as np
import pytest

import app.domain.rms_prerequisites as shared
from app.domain.calculated_channel import rms_recording_long_enough, rms_sampling_dense_enough
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
)
from app.domain.rms_detector import LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS, UNCERTAIN, classify_waveform_form
from app.domain.rms_prerequisites import (
    FormBasis,
    InputForm,
    RmsPrerequisiteFailure,
    check_rms_window_prerequisites,
    classify_input_form,
)
from app.services import calculated_channel_service as service
from app.services.calculated_channel_service import (
    RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE,
    RMS_STATUS_SUITABLE,
    RMS_STATUS_UNCERTAIN,
)
from tests import rms_baseline_scenarios as scn

INPUTS = scn.load_service_inputs()


class TestWindowPrerequisites:
    @pytest.mark.parametrize(
        "data_key,expected",
        [
            ("svc_instantaneous", None),
            ("svc_uncertain", None),
            ("svc_short_instantaneous", RmsPrerequisiteFailure.RECORDING_TOO_SHORT),
            ("svc_sparse_instantaneous", RmsPrerequisiteFailure.SAMPLING_TOO_SPARSE),
            # Both fail: the FIRST prerequisite (recording length) is the one reported.
            ("svc_short_and_sparse", RmsPrerequisiteFailure.RECORDING_TOO_SHORT),
        ],
    )
    def test_known_inputs(self, data_key, expected):
        time, _ = INPUTS[data_key]
        assert check_rms_window_prerequisites(time, 50.0) is expected

    def test_agrees_with_the_underlying_predicates_for_every_frozen_input_and_frequency(self):
        with np.load(scn.VECTORS_PATH) as data:
            times = [data[key] for key in data.files if key.endswith("__time")]
        assert len(times) >= 30
        for time in times:
            for frequency in (1.0, 16.7, 50.0, 60.0, 400.0, 1000.0):
                long_enough = rms_recording_long_enough(time, frequency)
                dense = rms_sampling_dense_enough(time, frequency)
                expected = (
                    None if (long_enough and dense)
                    else RmsPrerequisiteFailure.RECORDING_TOO_SHORT if not long_enough
                    else RmsPrerequisiteFailure.SAMPLING_TOO_SPARSE
                )
                assert check_rms_window_prerequisites(time, frequency) is expected

    def test_second_predicate_is_not_evaluated_when_the_first_fails(self, monkeypatch):
        calls = []
        monkeypatch.setattr(shared, "rms_recording_long_enough", lambda t, f: calls.append("long") or False)
        monkeypatch.setattr(shared, "rms_sampling_dense_enough", lambda t, f: calls.append("dense") or True)
        assert check_rms_window_prerequisites(np.arange(3.0), 50.0) is RmsPrerequisiteFailure.RECORDING_TOO_SHORT
        assert calls == ["long"]

    def test_failure_values_are_stable_machine_codes(self):
        assert [f.value for f in RmsPrerequisiteFailure] == ["recording_too_short", "sampling_too_sparse"]


class TestInputFormClassification:
    @pytest.mark.parametrize("declared", [WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE])
    def test_declared_rms_or_magnitude_wins_without_running_the_detector(self, monkeypatch, declared):
        monkeypatch.setattr(shared, "classify_waveform_form", lambda *a: pytest.fail("detector must not run"))
        time, values = INPUTS["svc_instantaneous"]  # a perfect sinusoid: the declaration still wins
        result = classify_input_form(declared, time, values, 50.0)
        assert (result.outcome, result.basis, result.declared_waveform_form, result.detector_result) == \
            (InputForm.RMS_OR_MAGNITUDE, FormBasis.DECLARED_WAVEFORM_FORM, declared, None)

    def test_declared_instantaneous_wins_without_running_the_detector(self, monkeypatch):
        monkeypatch.setattr(shared, "classify_waveform_form", lambda *a: pytest.fail("detector must not run"))
        time, values = INPUTS["svc_magnitude_like"]  # magnitude-looking data: the declaration still wins
        result = classify_input_form(WAVEFORM_FORM_INSTANTANEOUS, time, values, 50.0)
        assert (result.outcome, result.basis, result.detector_result) == \
            (InputForm.INSTANTANEOUS, FormBasis.DECLARED_WAVEFORM_FORM, None)

    @pytest.mark.parametrize(
        "data_key,detector,outcome",
        [
            ("svc_instantaneous", LIKELY_INSTANTANEOUS, InputForm.INSTANTANEOUS),
            ("svc_magnitude_like", LIKELY_MAGNITUDE_OR_RMS, InputForm.RMS_OR_MAGNITUDE),
            ("svc_uncertain", UNCERTAIN, InputForm.UNCERTAIN),
            ("svc_rms_shaped", UNCERTAIN, InputForm.UNCERTAIN),
        ],
    )
    def test_unknown_form_defers_to_the_unchanged_detector(self, data_key, detector, outcome):
        time, values = INPUTS[data_key]
        assert classify_waveform_form(time, values, 50.0) == detector  # the detector itself, untouched
        result = classify_input_form(WAVEFORM_FORM_UNKNOWN, time, values, 50.0)
        assert (result.outcome, result.basis, result.detector_result, result.declared_waveform_form) == \
            (outcome, FormBasis.DETECTOR, detector, WAVEFORM_FORM_UNKNOWN)

    @pytest.mark.parametrize("declared", ["", "banana", "UNKNOWN", "Instantaneous"])
    def test_an_unrecognised_declared_value_is_treated_as_unknown(self, declared):
        time, values = INPUTS["svc_instantaneous"]
        result = classify_input_form(declared, time, values, 50.0)
        assert result.basis is FormBasis.DETECTOR and result.declared_waveform_form == declared

    def test_a_detector_result_is_never_reported_as_a_declared_form(self):
        time, values = INPUTS["svc_instantaneous"]
        result = classify_input_form(WAVEFORM_FORM_UNKNOWN, time, values, 50.0)
        assert result.outcome is InputForm.INSTANTANEOUS
        assert result.basis is FormBasis.DETECTOR            # inferred, not trusted
        assert result.declared_waveform_form == WAVEFORM_FORM_UNKNOWN  # nothing was promoted

    def test_result_is_immutable(self):
        time, values = INPUTS["svc_instantaneous"]
        result = classify_input_form(WAVEFORM_FORM_UNKNOWN, time, values, 50.0)
        with pytest.raises(Exception):
            result.outcome = InputForm.UNCERTAIN


class TestSeparationOfConcerns:
    """The shared module has no mathematics and no policy."""

    SOURCE = inspect.getsource(shared)
    TREE = ast.parse(SOURCE)

    def test_defines_no_rms_mathematics(self):
        banned_calls = {"sqrt", "cumsum", "evaluate_rms", "mean", "median", "diff", "allclose"}
        called = {
            (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None))
            for n in ast.walk(self.TREE) if isinstance(n, ast.Call)
        }
        assert not (called & banned_calls)

    def test_imports_no_service_or_api_layer(self):
        imported = {
            (n.module or "") for n in ast.walk(self.TREE) if isinstance(n, ast.ImportFrom)
        }
        assert all(m.startswith(("app.domain.", "__future__", "dataclasses", "enum")) or m == "__future__" for m in imported)
        assert not any(m.startswith(("app.services", "app.api", "app.schemas")) for m in imported)

    def test_has_no_override_or_exception_or_wording(self):
        names = {n.id for n in ast.walk(self.TREE) if isinstance(n, ast.Name)} | \
                {a.arg for n in ast.walk(self.TREE) if isinstance(n, ast.arguments) for a in n.args}
        assert not any("override" in name.lower() for name in names)
        assert not any(isinstance(n, ast.Raise) for n in ast.walk(self.TREE))
        assert "Applying RMS" not in self.SOURCE and "Signal form" not in self.SOURCE

    def test_does_not_validate_the_nominal_frequency(self):
        # Frequency validity stays a separate, unchanged predicate with the caller's own ordering. Checked on the
        # syntax tree (identifiers/imports), not the text, so docstrings may still mention it.
        identifiers = {n.id for n in ast.walk(self.TREE) if isinstance(n, ast.Name)} |                       {a.name for n in ast.walk(self.TREE) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert "nominal_frequency_valid" not in identifiers


class TestServiceUsesTheSharedFunctions:
    def _spy(self, monkeypatch, name):
        calls = []
        real = getattr(service, name)

        def wrapper(*args, **kwargs):
            calls.append(args)
            return real(*args, **kwargs)

        monkeypatch.setattr(service, name, wrapper)
        return calls

    def _env(self, data_key="svc_instantaneous", form=WAVEFORM_FORM_UNKNOWN):
        time, values = INPUTS[data_key]
        env = scn.Env()
        env.add(scn.build_source("src1", time, values, form=form))
        return env

    def test_eligibility_delegates_to_classify_input_form(self, monkeypatch):
        calls = self._spy(monkeypatch, "classify_input_form")
        assert scn.attempt_eligibility(self._env())["eligibility"]["status"] == RMS_STATUS_SUITABLE
        assert len(calls) == 1

    def test_create_classifies_once_then_applies_the_window_prerequisites_once(self, monkeypatch):
        classify_calls = self._spy(monkeypatch, "classify_input_form")
        prerequisite_calls = self._spy(monkeypatch, "check_rms_window_prerequisites")
        assert scn.attempt_create(self._env())["ok"] is True
        assert len(classify_calls) == 1 and len(prerequisite_calls) == 1

    def test_invalid_frequency_precedes_classification_and_prerequisites(self, monkeypatch):
        classify_calls = self._spy(monkeypatch, "classify_input_form")
        prerequisite_calls = self._spy(monkeypatch, "check_rms_window_prerequisites")
        result = scn.attempt_create(self._env(), parameters={"nominal_frequency_hz": 0})
        assert result["error"]["code"] == "invalid_nominal_frequency"
        assert classify_calls == [] and prerequisite_calls == []

    def test_override_required_precedes_the_window_prerequisites(self, monkeypatch):
        prerequisite_calls = self._spy(monkeypatch, "check_rms_window_prerequisites")
        env = self._env("svc_short_instantaneous", form=WAVEFORM_FORM_RMS)
        assert scn.attempt_create(env)["error"]["code"] == "rms_override_required"
        assert prerequisite_calls == []
        assert scn.attempt_create(env, override=True)["error"]["code"] == "rms_recording_too_short"
        assert len(prerequisite_calls) == 1

    @pytest.mark.parametrize(
        "form,data_key,status,override_required",
        [
            (WAVEFORM_FORM_INSTANTANEOUS, "svc_magnitude_like", RMS_STATUS_SUITABLE, False),
            (WAVEFORM_FORM_RMS, "svc_instantaneous", RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE, True),
            (WAVEFORM_FORM_MAGNITUDE, "svc_instantaneous", RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE, True),
            (WAVEFORM_FORM_UNKNOWN, "svc_instantaneous", RMS_STATUS_SUITABLE, False),
            (WAVEFORM_FORM_UNKNOWN, "svc_magnitude_like", RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE, True),
            (WAVEFORM_FORM_UNKNOWN, "svc_uncertain", RMS_STATUS_UNCERTAIN, True),
        ],
    )
    def test_service_policy_mapping_is_unchanged(self, form, data_key, status, override_required):
        result = scn.attempt_eligibility(self._env(data_key, form))["eligibility"]
        assert (result["status"], result["override_required"]) == (status, override_required)

    def test_wording_depends_on_what_decided(self):
        declared = scn.attempt_eligibility(self._env(form=WAVEFORM_FORM_INSTANTANEOUS))["eligibility"]["reason"]
        inferred = scn.attempt_eligibility(self._env())["eligibility"]["reason"]
        assert declared == "Input is explicitly marked instantaneous. Input appears suitable for RMS."
        assert inferred == "Input appears suitable for RMS."

    def test_the_service_keeps_exclusive_ownership_of_override_and_exceptions(self):
        source = inspect.getsource(service.create_calculated_channel)
        assert "RmsOverrideRequiredError" in source and "RmsRecordingTooShortError" in source
        assert "RmsSamplingTooSparseError" in source and "InvalidNominalFrequencyError" in source
