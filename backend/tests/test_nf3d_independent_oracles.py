"""NF-3D -- independent expected values for the phasor family and overcurrent, and the behaviour the migration must deliver.

Part 1 passes today and must keep passing: at a valid frequency the numbers are right, judged against (a) CLOSED FORMS for the pure-sinusoid
windows (|V| = 100 V rms at 0, -120, +120 degrees; pre-fault IA = 1 A rms at -30 degrees; settled fault IA = 10 A rms at -75 degrees) and (b) a
direct summation written here from the definition (half-open trailing window of one cycle, X = sqrt(2)/N * sum x[k] e^{-j w t[k]}; RMS =
sqrt(mean x^2)) for the window just after the fault onset, which contains the decaying DC offset a real fault has and has no closed form.
The samples are the exact values written to the file (6 decimals). Integer samples per cycle (50 Hz at 5000 and 4000 Hz: 100 and 80) must agree
to round-off; non-integer samples per cycle (60 Hz at 5000 and 4000 Hz: 83.33 and 66.67) to the proposed tolerances of NF-3A section 5.2
(1.05 % magnitude, 0.6 degrees) for the pure-sinusoid windows and to round-off against the direct summation.

Part 2 is what the migration must do. Each is a strict `xfail` naming the NF-3D rule it proves; the commit that delivers it removes the marker.
"""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import nf3d_baseline_scenarios as scn

VALID = {"r50": (5000.0, 50.0), "r50_fs4000": (4000.0, 50.0), "r60": (5000.0, 60.0), "r60_fs4000": (4000.0, 60.0)}
INTEGER_SPC = {"r50", "r50_fs4000"}
EPS = 1e-9


def window(t, x, t_end, f):
    mask = (t > t_end - 1.0 / f + EPS) & (t <= t_end + EPS)
    return t[mask], x[mask]


def direct_phasor(t, x, t_end, f):
    """RMS magnitude and angle (degrees) of the one-cycle trailing window, from the definition."""
    tw, xw = window(t, x, t_end, f)
    z = math.sqrt(2.0) / len(tw) * sum(v * cmath.exp(-1j * 2.0 * math.pi * f * s) for s, v in zip(tw, xw))
    return abs(z), math.degrees(cmath.phase(z))


def direct_rms(t, x, t_end, f):
    _, xw = window(t, x, t_end, f)
    return math.sqrt(float(np.mean(xw * xw)))


def file_samples(fs, f):
    t, signals = scn.fault_signals(fs, f)
    return t, {k: np.round(v, 6) for k, v in signals.items()}                  # exactly what the ASCII file carries


def settings(tmp_path, enabled=False):
    return Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=("http://localhost:8101",),
                    database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
                    nominal_frequency_manual_override_enabled=enabled)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    out = {}
    with TestClient(create_app(settings(tmp_path_factory.mktemp("nf3d-oracle"))), raise_server_exceptions=False) as client:
        for key, (fs, f) in VALID.items():
            ws = f"ws-o-{key}"
            sid = scn.upload(client, ws, key, fs, f, str(int(f)))
            cid = scn.context(client, ws, sid)
            out[key] = {"surfaces": scn.surfaces(client, ws, cid), "fs": fs, "f": f}
    return out


def roles(surface):
    return surface["body"]["roles"]


# --------------------------------------------------------------------------------------------- part 1: right at a valid frequency
@pytest.mark.parametrize("key", sorted(VALID))
class TestPhasorsAtAValidFrequency:
    def test_voltage_three_phase_matches_the_closed_form(self, world, key):
        r = roles(world[key]["surfaces"]["phasor_voltage_three_phase"])
        exact = key in INTEGER_SPC
        for role, angle in (("Va", 0.0), ("Vb", -120.0), ("Vc", 120.0)):
            assert r[role]["magnitude_rms"] == pytest.approx(100.0, rel=1e-6 if exact else 1.05e-2), role
            diff = (r[role]["angle_deg_absolute"] - angle + 180.0) % 360.0 - 180.0
            assert abs(diff) < (1e-3 if exact else 0.6), (role, diff)

    def test_the_fault_window_matches_the_direct_summation_to_round_off(self, world, key):
        fs, f = world[key]["fs"], world[key]["f"]
        t, x = file_samples(fs, f)
        mag, ang = direct_phasor(t, x["IA"], scn.FAULT_S, f)
        got = roles(world[key]["surfaces"]["phasor_current_phase_a_fault"])["Ia"]
        assert got["magnitude_rms"] == pytest.approx(mag, rel=1e-6)
        assert (got["angle_deg_absolute"] - ang + 180.0) % 360.0 - 180.0 == pytest.approx(0.0, abs=1e-4)

    def test_the_overcurrent_rms_matches_the_closed_form_and_the_direct_summation(self, world, key):
        fs, f = world[key]["fs"], world[key]["f"]
        s = world[key]["surfaces"]
        exact = key in INTEGER_SPC
        assert s["overcurrent_pre_fault"]["body"]["measured_rms_current"] == pytest.approx(1.0, rel=1e-6 if exact else 5e-3)
        assert s["overcurrent_settled"]["body"]["measured_rms_current"] == pytest.approx(10.0, rel=2e-3 if exact else 6e-3)
        t, x = file_samples(fs, f)
        assert s["overcurrent_fault"]["body"]["measured_rms_current"] == pytest.approx(direct_rms(t, x["IA"], scn.FAULT_S, f), rel=1e-6)

    def test_the_decaying_dc_offset_of_a_fault_visibly_inflates_the_rms_just_after_the_onset(self, world, key):
        # a property of the waveform, not of the code: ~10.19 A against 10 A. The oracle above proves the code reports it faithfully.
        rms = world[key]["surfaces"]["overcurrent_fault"]["body"]["measured_rms_current"]
        assert 10.05 < rms < 10.60

    def test_the_reference_frequency_reported_is_the_declared_one(self, world, key):
        for surface in ("phasor_voltage_three_phase", "phasor_diagram_fault", "overcurrent_fault", "impedance_a", "sequence_components", "distance_ab"):
            assert world[key]["surfaces"][surface]["body"]["reference_frequency_hz"] == world[key]["f"], surface


class TestProtectionResultsAreConsistentWithThePhasors:
    def test_the_sequence_components_of_a_balanced_voltage_set_are_all_positive_sequence(self, world):
        v = world["r50"]["surfaces"]["sequence_components"]["body"]["voltage_sequences"]
        assert v["positive_sequence_magnitude"] == pytest.approx(100.0, rel=1e-6)
        assert v["negative_sequence_magnitude"] == pytest.approx(0.0, abs=1e-4)
        assert v["zero_sequence_magnitude"] == pytest.approx(0.0, abs=1e-4)

    def test_the_fault_current_has_the_unbalance_a_single_phase_step_must_have(self, world):
        # IA steps from 1 A to ~10 A with IB, IC unchanged: closed form for the window just after onset is not needed to see that the
        # negative sequence is large and the zero sequence equals the negative sequence's size scale (both ~ (Ia_fault - Ia_load)/3)
        c = world["r50"]["surfaces"]["sequence_components"]["body"]["current_sequences"]
        assert c["negative_sequence_magnitude"] > 2.5 and c["zero_sequence_magnitude"] > 2.5


# ------------------------------------------------------------------------------- part 2: what the migration must deliver (strict xfail)
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(settings(tmp_path_factory.mktemp("nf3d-xfail"))), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def opened(tmp_path_factory):
    with TestClient(create_app(settings(tmp_path_factory.mktemp("nf3d-xfail-open"), enabled=True)), raise_server_exceptions=False) as c:
        yield c


def bay(client, key, ws):
    fs, f, lf = scn.RECORDINGS[key]
    sid = scn.upload(client, ws, key, fs, f, lf)
    return sid, scn.context(client, ws, sid)


def get(client, ws, cid, path, **params):
    return client.get(f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}/{path}", params=params)


class TestTheMigrationMustDeliver:
    @pytest.mark.xfail(strict=True, reason="NF-3D: an unusable declared frequency (-50) must be an invalid_reference_frequency refusal, not 'waveform form not eligible'")
    def test_a_negative_declaration_is_named_as_an_invalid_reference_frequency(self, client):
        sid, cid = bay(client, "declared_negative_50", "ws-x-neg")
        r = get(client, "ws-x-neg", cid, "phasor", analysis_kind="phasor", mode="voltage_three_phase", analysis_time=0.3)
        assert r.status_code == 200 and r.json()["reason_code"] == "invalid_reference_frequency"

    @pytest.mark.xfail(strict=True, reason="NF-3D (O-5, Phase C): a VALID frequency the sampling cannot support is insufficient_sampling_density, not a waveform-form refusal")
    def test_a_valid_override_beyond_the_samples_per_cycle_is_named_as_a_sampling_limit(self, client):
        sid, cid = bay(client, "r50", "ws-x-1000")
        r = get(client, "ws-x-1000", cid, "phasor", analysis_kind="phasor", mode="voltage_three_phase", analysis_time=0.3, reference_frequency_hz=1000.0)
        assert r.status_code == 200 and r.json()["reason_code"] != "waveform_form_not_eligible"

    @pytest.mark.xfail(strict=True, reason="NF-3D (O-6): the phasor result identifies the origin and revision of the frequency it used")
    def test_the_phasor_result_carries_the_origin_and_revision_of_the_frequency_used(self, client):
        sid, cid = bay(client, "r50", "ws-x-prov")
        b = get(client, "ws-x-prov", cid, "phasor", analysis_kind="phasor", mode="voltage_three_phase", analysis_time=0.3).json()
        assert (b["nominal_frequency_origin"], b["nominal_frequency_revision"]) == ("recording_metadata", 0)

    @pytest.mark.xfail(strict=True, reason="NF-3D (O-6): the overcurrent result identifies the origin and revision of the frequency it used")
    def test_the_overcurrent_result_carries_the_origin_and_revision_of_the_frequency_used(self, client):
        sid, cid = bay(client, "assumed_50", "ws-x-prov2")
        b = get(client, "ws-x-prov2", cid, "overcurrent", analysis_time=0.3, **scn.OVERCURRENT).json()
        assert (b["nominal_frequency_origin"], b["nominal_frequency_revision"]) == ("assumed_default", 0)

    @pytest.mark.xfail(strict=True, reason="NF-3D: a Manual value (server gate open) makes an unusable recording computable, with origin manual")
    def test_a_manual_value_is_the_frequency_the_phasor_uses(self, opened):
        sid, cid = bay(opened, "declared_zero", "ws-x-manual")
        assert opened.put(f"/api/v1/workspaces/ws-x-manual/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": 50}).status_code == 200
        b = get(opened, "ws-x-manual", cid, "phasor", analysis_kind="phasor", mode="voltage_three_phase", analysis_time=0.3).json()
        assert b["status"] == "computed" and b["nominal_frequency_origin"] == "manual"
