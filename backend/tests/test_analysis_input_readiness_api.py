"""API-level tests for DEC-107's `GET .../engineering-contexts/{id}/
input-readiness` endpoint -- one level deeper than `GET .../input-
resolution` (test_analysis_input_resolution_api.py's own suite): also
checks whether the resolved channel's own waveform REPRESENTATION
(instantaneous vs. RMS/magnitude) is eligible for the requesting
analyzer, reusing `app.services.overcurrent_analysis_service.check_
overcurrent_readiness()`/`app.services.phasor_analysis_service.check_
phasor_diagram_readiness()` -- see those modules' own docstrings for the
full Level 1/2/3 distinction this endpoint deliberately stops at Level 2.

Fixture: representation_eligibility_multibay(.cfg/.dat) -- two bays,
RMSBAY (proper instantaneous Voltage, but Current shaped as an always-
positive slowly-varying envelope -- the exact shape
backend/tests/test_rms_detector.py's own
test_slowly_varying_positive_magnitude_series_is_likely_magnitude_or_rms
uses, scaled to realistic secondary units) and INSTBAY (both Voltage and
Current proper instantaneous sinusoids). Uploaded via the real endpoint
so DEC-104's own automatic Engineering Context discovery produces both
contexts with zero manual seeding -- reused directly, never cleared,
since this suite's own assertions are exactly about what upload alone
already resolves.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="representation_eligibility_multibay"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _contexts_by_name(client, workspace_id):
    contexts = client.get(f"/api/v1/workspaces/{workspace_id}/engineering-contexts").json()
    return {c["display_name"]: c for c in contexts}


def _readiness(client, workspace_id, context_id, analysis_kind, mode):
    return client.get(
        f"/api/v1/workspaces/{workspace_id}/engineering-contexts/{context_id}/input-readiness",
        params={"analysis_kind": analysis_kind, "mode": mode},
    )


class TestOvercurrentReadiness:
    def test_rms_shaped_current_is_not_eligible(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        resp = _readiness(client, "ws-1", contexts["RMSBAY"]["id"], "overcurrent", "current_phase_a")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "waveform_form_not_eligible"

    def test_instantaneous_current_is_eligible(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        resp = _readiness(client, "ws-1", contexts["INSTBAY"]["id"], "overcurrent", "current_phase_a")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "resolved"
        assert body["reason_code"] is None

    def test_readiness_matches_the_real_computation_outcome(self, client, comtrade_fixtures_dir):
        """The whole point of this endpoint: its own verdict must predict
        whether the real, time-dependent computation will reject the
        context for the SAME reason -- proven directly against the real
        `/overcurrent` endpoint at a real analysis_time."""
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        readiness = _readiness(client, "ws-1", contexts["RMSBAY"]["id"], "overcurrent", "current_phase_a").json()
        assert readiness["status"] == "needs_configuration"

        compute_resp = client.get(
            f"/api/v1/workspaces/ws-1/engineering-contexts/{contexts['RMSBAY']['id']}/overcurrent",
            params={
                "phase": "A", "analysis_time": 1.0,
                "characteristic_id": "iec_standard_inverse", "tms": 0.1, "pickup_current_secondary": 1.0,
                "recording_basis": "secondary",
            },
        )
        assert compute_resp.status_code == 200, compute_resp.text
        computed = compute_resp.json()
        assert computed["status"] == "needs_configuration"
        assert computed["reason_code"] == readiness["reason_code"] == "waveform_form_not_eligible"

    def test_all_three_phases_are_checked_independently(self, client, comtrade_fixtures_dir):
        """RMSBAY's own IR/IY/IB are ALL RMS-shaped (not just phase A) --
        readiness must report `needs_configuration` for every phase
        independently, never assuming phase A's own verdict applies to
        B/C without actually checking each."""
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        for mode in ("current_phase_a", "current_phase_b", "current_phase_c"):
            resp = _readiness(client, "ws-1", contexts["RMSBAY"]["id"], "overcurrent", mode)
            assert resp.json()["status"] == "needs_configuration", mode
            assert resp.json()["reason_code"] == "waveform_form_not_eligible", mode


class TestImpedanceAndDistanceReadinessReuseThePhasorDiagramRule:
    """Impedance/Distance never get their own eligibility rule -- both
    ask this SAME endpoint under their own `analysis_kind`, which
    internally reuses `check_phasor_diagram_readiness()` (the identical
    function Phasor's own future readiness caller would use), proving
    the "one shared phasor-eligibility rule, never a per-analyzer copy"
    architecture directly."""

    def test_impedance_current_not_eligible_voltage_eligible_on_the_same_rms_bay(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        current_resp = _readiness(client, "ws-1", contexts["RMSBAY"]["id"], "impedance", "current_phase_a")
        assert current_resp.json()["status"] == "needs_configuration"
        assert current_resp.json()["reason_code"] == "waveform_form_not_eligible"

        voltage_resp = _readiness(client, "ws-1", contexts["RMSBAY"]["id"], "impedance", "voltage_phase_a")
        assert voltage_resp.json()["status"] == "resolved"

    def test_distance_current_not_eligible_on_the_rms_bay(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        resp = _readiness(client, "ws-1", contexts["RMSBAY"]["id"], "distance", "current_phase_b")
        assert resp.json()["status"] == "needs_configuration"
        assert resp.json()["reason_code"] == "waveform_form_not_eligible"

    def test_both_voltage_and_current_eligible_on_the_instantaneous_bay(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        for analysis_kind in ("impedance", "distance", "phasor", "sequence_components"):
            for mode in ("voltage_phase_a", "current_phase_a"):
                resp = _readiness(client, "ws-1", contexts["INSTBAY"]["id"], analysis_kind, mode)
                assert resp.status_code == 200, resp.text
                assert resp.json()["status"] == "resolved", (analysis_kind, mode, resp.json())


class TestUnknownRequirement:
    def test_unknown_analysis_kind_400s(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        resp = _readiness(client, "ws-1", contexts["INSTBAY"]["id"], "not_a_real_kind", "current_phase_a")
        assert resp.status_code == 400, resp.text

    def test_multi_role_mode_400s(self, client, comtrade_fixtures_dir):
        """This endpoint is single-role by design (mirrors `/input-
        resolution`'s own per-role query shape) -- a three-phase mode
        like `voltage_three_phase` has more than one required role and
        is deliberately rejected rather than silently checking only the
        first."""
        _upload(client, "ws-1", comtrade_fixtures_dir)
        contexts = _contexts_by_name(client, "ws-1")
        resp = _readiness(client, "ws-1", contexts["INSTBAY"]["id"], "phasor", "voltage_three_phase")
        assert resp.status_code == 400, resp.text
