"""NF-3E Phase A -- independent expected values for why a stale RMS channel matters, from closed forms and a direct summation.

An RMS channel is computed with a trailing window of exactly one cycle of the frequency recorded in its parameters. If the engineer later changes
the recording's frequency, the stored channel keeps its window. These oracles pin, WITHOUT using the production RMS kernel, what that channel
is worth:

* at the frequency of the signal the stored value is A/sqrt(2) (closed form), on the pure 100 V rms phase-A voltage of the standard bay;
* with a window of the WRONG frequency the value is the direct summation of the last N samples, N = round(1 / (f_window * dt)) (the documented
  "window / dt non-redundant samples" of `evaluate_rms`; agrees to round-off with the stored channel), and the error is bounded by the closed
  form sqrt(1 +- |sin(wT)| / (wT)) of the rms (w = 2 pi f_signal, T = N * dt; from mean(cos^2) = 1/2 + (sin 2a - sin 2b) / (4 wT)): about
  -8.7 % to +8.0 % for a 60 Hz window on a 50 Hz signal.
  That error is large enough that a stored channel built with the old frequency must not be shown as if it reflected the new setting (O-4).

Observation F-1 (not NF-3E scope, not changed): for a window that is not a whole number of samples (60 Hz at 5 kHz: 83.33) the kernel uses the
ROUNDED sample count (83), not the elapsed-time window its docstring describes (83 or 84 samples); the difference to a time-based window is
about 0.3 %. It is the same for every stored channel, whatever its frequency, and is recorded here only so the oracle states the rule it checks.

No staleness behaviour is asserted here: the contract is the owner's choice after the NF-3E assessment. This file passes on the unmodified code.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import nf3d_baseline_scenarios as scn
from tests import nf3e_baseline_scenarios as nf3e
from tests.test_nf3d_independent_oracles import file_samples

V_RMS = scn.V_RMS
F_SIGNAL = 50.0


@pytest.fixture(scope="module")
def channels(tmp_path_factory):
    settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3e_oracle")),
                        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local",
                        version="local", nominal_frequency_manual_override_enabled=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        ws = "ws-nf3e-oracle"
        sid = scn.upload(client, ws, "r50", 5000.0, F_SIGNAL, "50")
        out = {}
        for hz in (50, 60):
            made = nf3e.create(client, ws, f"rms_{hz}", "rms", [nf3e.src(sid, "VA")], {"nominal_frequency_hz": hz})
            assert made["status"] == 201
            body = client.get(f"/api/v1/workspaces/{ws}/calculated-channels/{made['id']}/waveform", params={"point_budget": 100000}).json()
            out[hz] = (np.array(body["time"], dtype=float), np.array([np.nan if v is None else v for v in body["values"]], dtype=float))
        return out


def at(time, values, t):
    return float(values[int(np.argmin(np.abs(time - t)))])


def trailing_rms(time, x, t_end, f_window):
    """sqrt(mean(x^2)) over the last N samples ending at t_end, N = round(1 / (f_window * dt)), from the definition."""
    dt = float(np.median(np.diff(time)))
    n = max(int(round(1.0 / (f_window * dt))), 1)
    end = int(np.argmin(np.abs(time - t_end)))
    window = x[end - n + 1:end + 1]
    return math.sqrt(float(np.mean(window * window)))


class TestStoredRmsAgainstIndependentValues:
    def test_a_window_of_the_signal_frequency_gives_the_closed_form_rms(self, channels):
        _, values = channels[50]
        steady = values[np.isfinite(values)]
        assert steady.size and np.allclose(steady, V_RMS, rtol=1e-7)

    @pytest.mark.parametrize("t_end", [0.3, 0.55, 0.8, 0.95])
    def test_a_window_of_another_frequency_equals_the_direct_summation_of_the_same_samples(self, channels, t_end):
        time, values = channels[60]
        t, signals = file_samples(5000.0, F_SIGNAL)
        expected = trailing_rms(t, signals["VA"], t_end, 60.0)
        assert at(time, values, t_end) == pytest.approx(expected, rel=1e-9)

    def test_the_error_of_a_window_of_the_wrong_frequency_is_bounded_by_the_closed_form_and_is_not_small(self, channels):
        _, values = channels[60]
        steady = values[np.isfinite(values)]
        n = round(5000.0 / 60.0)                                                    # 83 samples at 5 kHz
        w_t = 2.0 * math.pi * F_SIGNAL * n / 5000.0
        ripple = abs(math.sin(w_t)) / w_t                                          # mean(cos^2) = 1/2 +- ripple / 2
        low, high = V_RMS * math.sqrt(1.0 - ripple), V_RMS * math.sqrt(1.0 + ripple)
        assert low - 0.5 <= steady.min() and steady.max() <= high + 0.5             # the sampled window sits within 0.5 % of the continuous bound
        assert steady.min() < low + 0.5 and steady.max() > high - 0.5               # and the bound is nearly reached (it is not a loose bound)
        assert (steady.max() - V_RMS) / V_RMS > 0.05 and (V_RMS - steady.min()) / V_RMS > 0.05
