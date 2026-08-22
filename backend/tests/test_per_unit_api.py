"""API-level tests for the Phase 5C Per-Unit Base configuration endpoints
(DEC-049; source-bound redesign following owner UAT): source-scoped
CRUD, base-field validation, automatic eligible-channel association
(section 2/16 -- no assignment endpoint any more), voltage-reference
auto-detection/override, and workspace/source/calculated-channel
lifecycle cleanup, wired through the real FastAPI app (not just the
registry directly -- see test_per_unit_registry.py for that).
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


def _read(path) -> bytes:
    return path.read_bytes()


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = _read(comtrade_fixtures_dir / f"{stem}.cfg")
    dat = _read(comtrade_fixtures_dir / f"{stem}.dat")
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


class TestSourceOwnership:
    """Section 1/2/16: every loaded source appears automatically, and its
    own configuration applies only to its own channels -- no separate
    profile identity, no channel-assignment step."""

    def test_every_loaded_source_appears_in_the_list_even_unconfigured(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        listed = client.get("/api/v1/workspaces/ws-1/per-unit/sources").json()
        assert [s["source_id"] for s in listed] == [source_id]
        assert listed[0]["configured"] is False

    def test_source_a_configuration_does_not_leak_to_source_b(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)  # SAME filename, different source_id

        put_a = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_a}",
            json={"voltage_base_value": 275.0},
        )
        assert put_a.status_code == 200, put_a.text

        listed = {s["source_id"]: s for s in client.get("/api/v1/workspaces/ws-1/per-unit/sources").json()}
        assert listed[source_a]["configured"] is True
        assert listed[source_a]["voltage_base_value"] == 275.0
        assert listed[source_b]["configured"] is False  # untouched, despite the identical filename

    def test_workspace_isolation(self, client, comtrade_fixtures_dir):
        source_target = _upload(client, "ws-target", comtrade_fixtures_dir)
        _upload(client, "ws-other", comtrade_fixtures_dir)

        client.put(f"/api/v1/workspaces/ws-target/per-unit/sources/{source_target}", json={"voltage_base_value": 275.0})

        target_listed = client.get("/api/v1/workspaces/ws-target/per-unit/sources").json()
        other_listed = client.get("/api/v1/workspaces/ws-other/per-unit/sources").json()
        assert target_listed[0]["configured"] is True
        assert other_listed[0]["configured"] is False

    def test_put_unknown_source_is_404(self, client):
        resp = client.put("/api/v1/workspaces/ws-1/per-unit/sources/does-not-exist", json={"voltage_base_value": 275.0})
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestBaseFieldValidation:
    def test_valid_voltage_base_and_resolved_current_base(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={
                "voltage_base_value": 275.0,
                "current_base_mode": "derived",
                "apparent_power_base_value": 500.0,
                "voltage_reference_mode": "manual",
                "voltage_reference_override": "line_to_line",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["resolved_current_base"]["unit"] == "A"
        assert body["resolved_current_base"]["value"] == pytest.approx(500_000_000.0 / (1.7320508075688772 * 275_000.0))

    def test_negative_voltage_base_is_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.put(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}", json={"voltage_base_value": -5.0})
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_per_unit_base"

    def test_manual_reference_mode_requires_an_override_value(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_reference_mode": "manual"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_per_unit_base"

    def test_canonical_units_only_no_unit_field_needed(self, client, comtrade_fixtures_dir):
        # Section 4: the request body carries bare numbers -- Voltage
        # Base is always kV, Apparent Power Base always MVA, Direct
        # Current Base always kA. No unit field exists in the schema.
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 275.0, "current_base_mode": "direct", "direct_current_base_value": 1.2},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["voltage_base_value"] == 275.0
        assert resp.json()["direct_current_base_value"] == 1.2
        assert resp.json()["resolved_current_base"]["value"] == pytest.approx(1200.0)


class TestVoltageReferenceAutoDetectionOverAPI:
    def test_auto_detects_line_to_ground_from_va_vb_vc(self, client, comtrade_fixtures_dir):
        # synth_ascii fixture's own analog channels are VA/VB (phase
        # field "A"/"B") and IA -- VA/VB alone are recognized single-
        # phase-to-ground evidence under the naming detector.
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.get(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["effective_voltage_reference"] == "line_to_ground"
        assert set(body["voltage_reference_evidence"]) == {"VA", "VB"}
        assert body["voltage_reference_reason"] == "detected_from_names"

    def test_manual_override_replaces_the_auto_detected_value(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_reference_mode": "manual", "voltage_reference_override": "line_to_line"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["voltage_reference_mode"] == "manual"
        assert body["effective_voltage_reference"] == "line_to_line"
        assert body["voltage_reference_reason"] == "manual_override"

    def test_return_to_auto_reruns_detection_rather_than_keeping_the_manual_value(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_reference_mode": "manual", "voltage_reference_override": "line_to_line"},
        )
        back_to_auto = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_reference_mode": "auto"},
        )
        assert back_to_auto.status_code == 200, back_to_auto.text
        body = back_to_auto.json()
        assert body["voltage_reference_mode"] == "auto"
        assert body["effective_voltage_reference"] == "line_to_ground"  # the real detected value, not the old manual one


class TestLifecycleCleanup:
    def test_deleting_a_source_clears_its_own_configuration(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}", json={"voltage_base_value": 275.0})

        assert client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 204

        assert client.get("/api/v1/workspaces/ws-1/per-unit/sources").json() == []

    def test_deleting_the_workspace_clears_every_source_configuration(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}", json={"voltage_base_value": 275.0})

        assert client.delete("/api/v1/workspaces/ws-1").status_code == 204

        assert client.get("/api/v1/workspaces/ws-1/per-unit/sources").json() == []

    def test_deleting_the_workspace_does_not_affect_other_workspaces(self, client, comtrade_fixtures_dir):
        source_target = _upload(client, "ws-target", comtrade_fixtures_dir)
        source_other = _upload(client, "ws-other", comtrade_fixtures_dir)
        client.put(f"/api/v1/workspaces/ws-target/per-unit/sources/{source_target}", json={"voltage_base_value": 275.0})
        client.put(f"/api/v1/workspaces/ws-other/per-unit/sources/{source_other}", json={"voltage_base_value": 132.0})

        assert client.delete("/api/v1/workspaces/ws-target").status_code == 204

        assert client.get("/api/v1/workspaces/ws-target/per-unit/sources").json() == []
        other_listed = client.get("/api/v1/workspaces/ws-other/per-unit/sources").json()
        assert other_listed[0]["configured"] is True

    def test_delete_of_an_unconfigured_source_is_idempotent(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.delete(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}")
        assert resp.status_code == 204
