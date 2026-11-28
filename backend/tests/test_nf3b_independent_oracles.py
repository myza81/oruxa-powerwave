"""NF-3B -- independent engineering oracles for the nominal-frequency consumers.

These are the DESIRED behaviours, derived from closed-form mathematics and the owner-approved contracts (DEC-217, NF-001,
NF-3A section 5), never from what the code currently does. They are separate from the legacy characterisation in
`test_nf3b_frozen_baselines.py`:

* Part 1 is what the engine kernels already do correctly when they are handed the right frequency. It passes today and must
  keep passing through every migration: it is the proof that a migration only changes WHICH frequency reaches a kernel, never
  the arithmetic.
* Part 2 is what the CONSUMERS must do once migrated. Each is `xfail(strict=True)` with the slice that fixes it. While the
  defect exists the test fails (xfail); the day the slice fixes it the test passes, strict mode turns that into a failure, and
  the slice removes the marker deliberately. Nothing here is a hidden "expected failure" that can rot: an unexpected pass is loud.

Expected values: a unit-amplitude cosine of peak 100 has RMS 100/sqrt(2). A load with the current lagging 30 degrees, V = 100 kV
peak and I = 1 kA peak, takes P = 43.3013 MW and Q = 25 Mvar.
"""

from __future__ import annotations

import io
import math
import warnings

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.calculated_channel import (
    OP_ACTIVE_POWER, OP_REACTIVE_POWER, ChannelRef, evaluate_power_channel, evaluate_rms,
)
from app.domain.overcurrent import estimate_trailing_rms_at_time
from app.domain.sliding_phasor import compute_sliding_phasor
from app.main import create_app
from tests import nf3b_baseline_scenarios as scn

RMS = 100.0 / math.sqrt(2.0)
P_MW = 0.5 * 100e3 * 1e3 * math.cos(math.radians(30.0)) / 1e6
Q_MVAR = 0.5 * 100e3 * 1e3 * math.sin(math.radians(30.0)) / 1e6


def _steady(t, f, cycles=2.0):
    return t >= cycles / f + 1e-9


# ------------------------------------------------------------------------------ part 1: kernels given the right frequency
class TestKernelsAreExactWhenTheWindowMatchesTheSignal:
    """Integer samples per cycle (4800 Hz: 96 at 50 Hz, 80 at 60 Hz): the one-cycle window is exact, so the error is round-off."""

    @pytest.mark.parametrize("f", [50.0, 60.0])
    def test_trailing_rms(self, f):
        t, x = scn.signal(f, 4800.0, 0.5)
        out = evaluate_rms(t, x, f)
        ok = _steady(t, f) & np.isfinite(out)
        assert ok.sum() > 1000 and np.max(np.abs(out[ok] / RMS - 1.0)) < 1e-9

    @pytest.mark.parametrize("f", [50.0, 60.0])
    def test_sliding_phasor_magnitude_and_a_constant_angle(self, f):
        t, x = scn.signal(f, 4800.0, 0.5, 30.0)
        res = compute_sliding_phasor(t, x, f)
        m = res.available
        assert m.sum() > 1000
        assert np.max(np.abs(np.abs(res.phasor[m]) / RMS - 1.0)) < 1e-9
        angle = np.degrees(np.angle(res.phasor[m]))
        assert np.ptp(np.unwrap(np.radians(angle))) < 1e-6                              # no rotation at the matched frequency

    @pytest.mark.parametrize("f", [50.0, 60.0])
    def test_overcurrent_trailing_rms(self, f):
        t, x = scn.signal(f, 4800.0, 0.5)
        est = estimate_trailing_rms_at_time(t, x, 0.3, f)
        assert est.available and est.value == pytest.approx(RMS, rel=1e-9)

    @pytest.mark.parametrize("f", [50.0, 60.0])
    def test_power_with_the_window_set_to_the_signal_frequency(self, f):
        t, v = scn.signal(f, 4800.0, 0.5, 0.0, 100e3)
        _, i = scn.signal(f, 4800.0, 0.5, -30.0, 1e3)
        p = evaluate_power_channel(OP_ACTIVE_POWER, t, v, 1.0, i, 1.0, f)
        q = evaluate_power_channel(OP_REACTIVE_POWER, t, v, 1.0, i, 1.0, f)
        ok = _steady(t, f) & np.isfinite(p) & np.isfinite(q)
        assert np.max(np.abs(p[ok] / P_MW - 1.0)) < 1e-9 and np.max(np.abs(q[ok] / Q_MVAR - 1.0)) < 1e-9


class TestNonIntegerSamplesPerCycleStaysInsideTheProposedTolerance:
    """4096 Hz gives 81.92 samples per 50 Hz cycle and 68.27 per 60 Hz cycle: the window is rounded to whole samples, so a small
    residual ripple is inherent. Proposed tolerances (NF-3A section 5.2) are about 1.3x the worst case measured then."""

    @pytest.mark.parametrize("f,ripple_pct", [(50.0, 0.13), (60.0, 0.52)])
    def test_rms_ripple(self, f, ripple_pct):
        t, x = scn.signal(f, 4096.0, 0.5)
        out = evaluate_rms(t, x, f)
        ok = _steady(t, f) & np.isfinite(out)
        assert (np.ptp(out[ok]) / RMS) * 100.0 < ripple_pct

    @pytest.mark.parametrize("f,ripple_pct", [(50.0, 0.26), (60.0, 1.05)])
    def test_phasor_magnitude_ripple(self, f, ripple_pct):
        t, x = scn.signal(f, 4096.0, 0.5, 30.0)
        res = compute_sliding_phasor(t, x, f)
        mag = np.abs(res.phasor[res.available])
        assert (np.ptp(mag) / RMS) * 100.0 < ripple_pct


# ------------------------------------------------------------------------------ part 2: consumers once migrated (strict xfail)
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3b-oracle")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


def _upload(client, ws, fs, f_sig, lf):
    cfg, dat = scn.build_comtrade(fs, f_sig, lf)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        response = client.post(f"/api/v1/workspaces/{ws}/sources", files={
            "cfg_file": ("o.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": ("o.dat", io.BytesIO(dat), "application/octet-stream")})
    assert response.status_code == 201, response.text
    sid = response.json()["source_id"]
    for context in client.get(f"/api/v1/workspaces/{ws}/engineering-contexts").json():
        client.delete(f"/api/v1/workspaces/{ws}/engineering-contexts/{context['id']}")
    return sid


def _context(client, ws, sid):
    ref = lambda n: {"kind": "source", "source_id": sid, "channel_name": n}      # noqa: E731
    response = client.post(f"/api/v1/workspaces/{ws}/engineering-contexts", json={"display_name": "A", "status": "manual", "members": [
        {"channel_ref": ref("ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
        {"channel_ref": ref("ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}]})
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestConsumersMustRefuseAnUnusableDeclaredFrequencyWithoutAnException:
    def test_phasor_for_a_recording_declaring_zero_hertz(self, client):
        ws = "ws-oracle-phasor"
        sid = _upload(client, ws, 5000.0, 50.0, "0")
        cid = _context(client, ws, sid)
        r = client.get(f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}/phasor",
                       params={"analysis_kind": "phasor", "mode": "voltage_phase_a", "analysis_time": 0.5})
        assert r.status_code == 200 and r.json()["status"] == "needs_configuration"

    def test_overcurrent_for_a_recording_declaring_zero_hertz(self, client):
        ws = "ws-oracle-oc"
        sid = _upload(client, ws, 5000.0, 50.0, "0")
        cid = _context(client, ws, sid)
        r = client.get(f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}/overcurrent", params={
            "phase": "A", "analysis_time": 0.5, "characteristic_id": "iec_standard_inverse", "tms": 0.1,
            "pickup_current_secondary": 1.0, "recording_basis": "secondary"})
        assert r.status_code == 200 and r.json()["status"] == "needs_configuration"

    def test_compliance_measurement_does_not_raise_for_zero_hertz(self):
        # NF-3C fixed this (the strict xfail flipped and its marker was removed in the same commit): an unusable declaration is
        # never handed to the detector; the classifier answers "do not guess".
        from app.services.compliance_measurement_service import _classify_input_type
        from app.services.workspace_registry import WorkspaceRegistry
        from tests.nf3c_access_support import access_for
        sources = WorkspaceRegistry()
        sources.add(scn.build_source("src", 0.0, {"source_format": "COMTRADE"}, 50.0))
        result = _classify_input_type(ChannelRef(kind="source", source_id="src", channel_name="IA"),
                                      workspace_id=scn.WS, source_registry=sources, frequency_access=access_for(sources))
        assert result is None                                                         # "do not guess"

    def test_rms_eligibility_rejects_zero_hertz_as_a_client_error(self, client):
        ws = "ws-oracle-elig"
        sid = _upload(client, ws, 5000.0, 50.0, "50")
        r = client.post(f"/api/v1/workspaces/{ws}/calculated-channels/rms-eligibility", json={
            "input": {"kind": "source", "source_id": sid, "channel_name": "ALPHA1_VA"}, "nominal_frequency_hz": 0})
        assert r.status_code == 400


class TestPowerChannelsMustUseTheRecordingsFrequency:
    @pytest.mark.xfail(strict=True, reason="NF-3F: the power window is hard-coded to 50 Hz (D-A, needs O-2)")
    def test_active_power_of_a_60hz_recording_is_the_closed_form_value(self):
        from app.services.calculated_channel_registry import CalculatedChannelRegistry
        from app.services.calculated_channel_service import create_calculated_channel
        from app.services.workspace_registry import WorkspaceRegistry
        sources, calcs = WorkspaceRegistry(), CalculatedChannelRegistry()
        sources.add(scn.build_source("src", 60.0, {"source_format": "COMTRADE"}, 60.0))
        channel = create_calculated_channel(
            workspace_id=scn.WS, name="P", operation=OP_ACTIVE_POWER, parameters={}, source_registry=sources, calc_registry=calcs,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="VA"), ChannelRef(kind="source", source_id="src", channel_name="IA")])
        t = np.asarray(channel.time)
        steady = np.isfinite(channel.values) & (t >= 0.1)
        assert np.max(np.abs(np.asarray(channel.values)[steady] / P_MW - 1.0)) < 1e-3

    @pytest.mark.xfail(strict=True, reason="NF-3F: the stored parameter says 50.0 whatever the recording (D-A)")
    def test_the_stored_frequency_is_the_one_the_calculation_used(self):
        from app.services.calculated_channel_registry import CalculatedChannelRegistry
        from app.services.calculated_channel_service import create_calculated_channel
        from app.services.workspace_registry import WorkspaceRegistry
        sources, calcs = WorkspaceRegistry(), CalculatedChannelRegistry()
        sources.add(scn.build_source("src", 60.0, {"source_format": "COMTRADE"}, 60.0))
        channel = create_calculated_channel(
            workspace_id=scn.WS, name="P", operation=OP_ACTIVE_POWER, parameters={}, source_registry=sources, calc_registry=calcs,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="VA"), ChannelRef(kind="source", source_id="src", channel_name="IA")])
        assert channel.parameters["nominal_frequency_hz"] == 60.0


class TestOscillationFrequencySelectionMustNotDependOnMemberOrder:
    @pytest.mark.xfail(strict=True, reason="NF-3G: the FIRST member's frequency decides (D-D, needs O-9)")
    def test_swapping_the_recordings_does_not_change_the_verdict(self):
        cases = scn.run_oscillation_selection_scenarios()["component_55hz"]
        assert cases["first_50_second_60"] == cases["first_60_second_50"]
