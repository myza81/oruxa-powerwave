"""NF-3H -- the silent 50 Hz engine defaults are retired (C-16), the sanctioned fallback is not.

Owner decision (DEC-217 amendment 1, 2026-11-28): after the callers migrated (NF-3C..NF-3G), `compute_sliding_phasor`,
`evaluate_power_channel` and `evaluate_three_phase_power_channel` take the frequency as a REQUIRED argument, so a future caller cannot silently
get 50 Hz; the call-path guard is extended; the 50 Hz assumed-frequency fallback of the resolver stays (a recording that declares nothing is
Auto = 50 Hz, flagged assumed); Auto Base evidence (`extract_waveform_evidence`, C-17) is excluded (O-3); not every 50 Hz constant goes.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pytest

from app.domain import metadata as domain_metadata
from app.domain import waveform_evidence
from app.domain.calculated_channel import (
    OP_ACTIVE_POWER,
    OP_THREE_PHASE_ACTIVE_POWER,
    evaluate_power_channel,
    evaluate_three_phase_power_channel,
)
from app.domain.nominal_frequency import ORIGIN_ASSUMED_DEFAULT
from app.domain.sliding_phasor import compute_sliding_phasor
from app.services.nominal_frequency_service import effective_nominal_frequency
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests import nf3b_baseline_scenarios as scn

APP_DIR = Path(__file__).resolve().parents[1] / "app"

#: function -> (parameter name, minimum positional argument count that already supplies it)
RETIRED = {
    compute_sliding_phasor: ("reference_frequency_hz", 3),
    evaluate_power_channel: ("nominal_frequency_hz", 7),
    evaluate_three_phase_power_channel: ("nominal_frequency_hz", 15),
}


def _signals(f=50.0, fs=4800.0):
    t = np.arange(int(fs * 0.4)) / fs
    return t, 100e3 * np.cos(2 * np.pi * f * t), 1e3 * np.cos(2 * np.pi * f * t - np.deg2rad(30.0))


class TestTheDefaultsAreRetired:
    @pytest.mark.parametrize("function", list(RETIRED))
    def test_the_frequency_parameter_has_no_default(self, function):
        parameter = inspect.signature(function).parameters[RETIRED[function][0]]
        assert parameter.default is inspect.Parameter.empty

    def test_a_caller_that_omits_the_frequency_fails_loudly(self):
        t, v, i = _signals()
        with pytest.raises(TypeError):
            compute_sliding_phasor(t, v)
        with pytest.raises(TypeError):
            evaluate_power_channel(OP_ACTIVE_POWER, t, v, 1.0, i, 1.0)
        with pytest.raises(TypeError):
            evaluate_three_phase_power_channel(OP_THREE_PHASE_ACTIVE_POWER, t, v, 1.0, i, 1.0, v, 1.0, i, 1.0, v, 1.0, i, 1.0)

    def test_an_explicit_frequency_is_accepted_and_the_50hz_numbers_are_pinned_by_the_frozen_kernel_baselines(self):
        # The explicit 50.0 is exactly what the silent default supplied, so 50 Hz behaviour is unchanged; the numbers themselves are pinned bit
        # for bit by the frozen NF-3B kernel baselines (test_nf3b_frozen_baselines[kernels]) and by the NF-3F 50 Hz equality test.
        t, v, i = _signals()
        assert np.isfinite(evaluate_power_channel(OP_ACTIVE_POWER, t, v, 1.0, i, 1.0, nominal_frequency_hz=50.0)[-1])
        assert compute_sliding_phasor(t, v, 50.0).phasor.size > 0

    def test_a_60hz_value_reaches_the_kernel(self):
        t, v, i = _signals(60.0)
        at_60 = evaluate_power_channel(OP_ACTIVE_POWER, t, v, 1.0, i, 1.0, nominal_frequency_hz=60.0)
        at_50 = evaluate_power_channel(OP_ACTIVE_POWER, t, v, 1.0, i, 1.0, nominal_frequency_hz=50.0)
        assert not np.array_equal(at_60, at_50, equal_nan=True)


class TestEveryProductionCallerSuppliesTheFrequency:
    def test_no_production_call_omits_it(self):
        offenders, seen = [], set()
        for path in APP_DIR.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                for function, (keyword, positional) in RETIRED.items():
                    if name == function.__name__:
                        seen.add(function.__name__)
                        if len(node.args) < positional and all(k.arg != keyword for k in node.keywords):
                            offenders.append((path.name, node.lineno, name))
        assert offenders == []
        assert seen == {f.__name__ for f in RETIRED}                      # the scan really found the production call sites


class TestWhatIsKept:
    def test_auto_base_evidence_keeps_its_default_under_o3(self):
        parameter = inspect.signature(waveform_evidence.extract_waveform_evidence).parameters["nominal_frequency_hz"]
        assert parameter.default == 50.0
        callers = sorted(p.name for p in APP_DIR.rglob("*.py") if "extract_waveform_evidence(" in p.read_text(encoding="utf-8")
                         and p.name != "waveform_evidence.py")
        assert callers == ["auto_base_service.py"]                        # untouched: the Per-Unit workstream owns it

    def test_the_assumed_frequency_fallback_of_the_authority_is_retained(self):
        assert domain_metadata.DEFAULT_NOMINAL_FREQUENCY_HZ == 50.0
        sources = WorkspaceRegistry()
        sources.add(scn.build_source("src", None, {"source_format": "COMTRADE"}, 50.0))
        resolved = effective_nominal_frequency(scn.WS, "src", source_registry=sources, registry=NominalFrequencyRegistry(), manual_override_enabled=False)
        assert (resolved.effective_hz, resolved.origin) == (50.0, ORIGIN_ASSUMED_DEFAULT)

    def test_the_power_service_has_no_literal_default_of_its_own(self):
        # the no-authority path uses the one sanctioned constant, not a second 50.0 (see test_nf3f_power_channels for the shape it keeps)
        source = (APP_DIR / "services" / "calculated_channel_service.py").read_text(encoding="utf-8")
        assert "DEFAULT_NOMINAL_FREQUENCY_HZ" in source
