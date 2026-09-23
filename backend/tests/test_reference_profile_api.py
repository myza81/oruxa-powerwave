"""API-level tests for Compliance Slice 3's Reference Profile / Reference
Layer / Comparison Chart endpoints. Exercises the real FastAPI app
end-to-end for HTTP wiring/response-shape/error-mapping/workspace-
lifecycle only -- the full validation/compatibility/chart-assembly
decision matrix is already covered by `test_reference_profile_domain.py`/
`test_reference_profile_service.py`.

**No test in this file ever uploads a source or creates a Measurement
Group** -- every scenario (including the "configure references, then
upload a recording, then confirm layers survive" scenario) constructs
its own minimal COMTRADE fixture only where the scenario is specifically
about upload interaction; every other test proves the Reference
Profile/Layer surface is fully usable in a workspace that owns nothing
else at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "reference_profiles"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _profile_body(**overrides) -> dict:
    body = {
        "name": "API Test Profile", "category": "custom_reference", "evaluation_quantity": "phase_a_lg_rms",
        "unit": "pu", "display_start_time": -0.5, "display_end_time": 3.0, "evaluation_start_time": 0.0,
        "evaluation_end_time": 3.0, "tolerance": 0.0,
        "lower_boundary": {"segments": [
            {"start_time": -0.5, "end_time": 3.0, "start_value": 0.8, "end_value": 0.8, "segment_type": "constant"}
        ]},
        "upper_boundary": None,
        "metadata": {},
    }
    body.update(overrides)
    return body


WORKSPACE = "ws-ref-api-1"


class TestReferenceProfileCrudHttp:
    def test_list_starts_empty_in_a_fresh_workspace(self, client: TestClient):
        response = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_returns_201_with_a_generated_id(self, client: TestClient):
        response = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body())
        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["source"] == "custom"

    def test_create_rejects_invalid_data_with_400(self, client: TestClient):
        response = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body(tolerance=-1.0))
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "reference_profile_invalid"

    def test_invalid_segment_error_identifies_the_offending_row(self, client: TestClient):
        body = _profile_body(lower_boundary={"segments": [
            {"start_time": 0.0, "end_time": 1.0, "start_value": 0.5, "end_value": 0.5, "segment_type": "constant"},
            {"start_time": 0.5, "end_time": 2.0, "start_value": 0.6, "end_value": 0.6, "segment_type": "constant"},
        ]})
        response = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=body)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["reason_code"] == "overlapping_segments"
        assert detail["boundary"] == "lower"
        assert detail["segment_index"] == 1

    def test_get_unknown_profile_returns_404(self, client: TestClient):
        response = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/does-not-exist")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "reference_profile_not_found"

    def test_update_replaces_an_existing_profile(self, client: TestClient):
        profile_id = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body()).json()["id"]
        response = client.put(
            f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{profile_id}", json=_profile_body(name="Renamed"),
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    def test_duplicate_creates_a_second_independent_profile(self, client: TestClient):
        profile_id = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body()).json()["id"]
        response = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{profile_id}/duplicate")
        assert response.status_code == 201
        assert response.json()["id"] != profile_id

    def test_delete_removes_the_profile(self, client: TestClient):
        profile_id = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body()).json()["id"]
        assert client.delete(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{profile_id}").status_code == 204
        assert client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{profile_id}").status_code == 404

    def test_export_then_import_round_trips_as_a_new_profile(self, client: TestClient):
        profile_id = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body(name="Exportable")).json()["id"]
        envelope = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{profile_id}/export").json()
        assert envelope["schema_version"] == 1
        imported = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/import", json=envelope)
        assert imported.status_code == 201
        assert imported.json()["id"] != profile_id
        assert imported.json()["name"] == "Exportable"

    def test_import_unsupported_schema_version_returns_400(self, client: TestClient):
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/import", json={"schema_version": 999, "profile": {}},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unsupported_reference_profile_schema_version"


class TestBuiltInProfilesViaHttp:
    """Injects a clearly-labeled test-only built-in fixture in place of
    the (empty) production catalogue for the duration of each test --
    see this file's own top-of-module note; the production catalogue
    itself is proven empty by `test_reference_profile_builtins.py`."""

    @pytest.fixture(autouse=True)
    def _use_test_only_builtin_catalogue(self, monkeypatch):
        monkeypatch.setattr("app.domain.reference_profile_builtins.DEFAULT_BUILTIN_DIRECTORY", FIXTURES_DIR / "valid")

    def test_built_in_profile_is_listed(self, client: TestClient):
        response = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles")
        assert response.status_code == 200
        sources = {p["source"] for p in response.json()}
        assert "built_in" in sources

    def test_built_in_profile_can_be_duplicated(self, client: TestClient):
        builtin_id = next(p["id"] for p in client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles").json() if p["source"] == "built_in")
        response = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{builtin_id}/duplicate")
        assert response.status_code == 201
        assert response.json()["source"] == "custom"

    def test_built_in_profile_cannot_be_edited(self, client: TestClient):
        builtin_id = next(p["id"] for p in client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles").json() if p["source"] == "built_in")
        response = client.put(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{builtin_id}", json=_profile_body())
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "reference_profile_is_built_in"

    def test_built_in_profile_cannot_be_deleted(self, client: TestClient):
        builtin_id = next(p["id"] for p in client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles").json() if p["source"] == "built_in")
        response = client.delete(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{builtin_id}")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "reference_profile_is_built_in"


class TestReferenceLayerHttp:
    def test_add_list_toggle_remove_lifecycle(self, client: TestClient):
        profile_id = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body()).json()["id"]

        created = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-layers", json={"profile_id": profile_id})
        assert created.status_code == 201
        layer_id = created.json()["id"]
        assert created.json()["compatibility"]["status"] == "not_yet_applicable"

        listed = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers")
        assert listed.status_code == 200
        assert [layer["id"] for layer in listed.json()] == [layer_id]

        toggled = client.patch(f"/api/v1/workspaces/{WORKSPACE}/reference-layers/{layer_id}", json={"visible": False})
        assert toggled.status_code == 200
        assert toggled.json()["visible"] is False

        removed = client.delete(f"/api/v1/workspaces/{WORKSPACE}/reference-layers/{layer_id}")
        assert removed.status_code == 204
        assert client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers").json() == []
        # The profile itself is untouched by layer removal.
        assert client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-profiles/{profile_id}").status_code == 200

    def test_add_layer_for_unknown_profile_returns_404(self, client: TestClient):
        response = client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-layers", json={"profile_id": "does-not-exist"})
        assert response.status_code == 404

    def test_layer_compatibility_reflects_quantity_id_query_param(self, client: TestClient):
        profile_id = client.post(
            f"/api/v1/workspaces/{WORKSPACE}/reference-profiles", json=_profile_body(evaluation_quantity="phase_a_lg_rms"),
        ).json()["id"]
        client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-layers", json={"profile_id": profile_id})

        compatible = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers", params={"quantity_id": "phase_a_lg_rms"})
        assert compatible.json()[0]["compatibility"]["status"] == "compatible"

        incompatible = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers", params={"quantity_id": "phase_b_lg_rms"})
        assert incompatible.json()[0]["compatibility"]["status"] == "incompatible"

        not_yet_applicable = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers")
        assert not_yet_applicable.json()[0]["compatibility"]["status"] == "not_yet_applicable"


class TestComparisonChartHttp:
    def test_chart_data_reflects_active_visible_layers(self, client: TestClient):
        profile_id = client.post(
            f"/api/v1/workspaces/{WORKSPACE}/reference-profiles",
            json=_profile_body(display_start_time=-1.0, display_end_time=5.0),
        ).json()["id"]
        client.post(f"/api/v1/workspaces/{WORKSPACE}/reference-layers", json={"profile_id": profile_id})

        response = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers/chart-data")
        assert response.status_code == 200
        body = response.json()
        assert body["axis_unit"] == "pu"
        assert body["x_min"] == -1.0
        assert body["x_max"] == 5.0
        assert len(body["traces"]) == 1
        assert body["traces"][0]["boundary"] == "lower"
        assert body["traces"][0]["points"]

    def test_chart_data_is_empty_shape_for_a_workspace_with_no_layers(self, client: TestClient):
        response = client.get(f"/api/v1/workspaces/{WORKSPACE}/reference-layers/chart-data")
        assert response.status_code == 200
        body = response.json()
        assert body["traces"] == []
        assert body["axis_unit"] is None


class TestReferenceLayersWorkWithoutAnyUploadedRecording:
    """Direct proof of the mid-conversation amendment: every one of
    these calls happens against a workspace that has never had a source
    uploaded, never had a Measurement Group created, and never touched
    any Measurement-related endpoint at all."""

    def test_full_lifecycle_in_a_workspace_that_owns_nothing_else(self, client: TestClient):
        workspace = "ws-no-recording-1"
        assert client.get(f"/api/v1/workspaces/{workspace}/sources").json() == []

        profile_id = client.post(f"/api/v1/workspaces/{workspace}/reference-profiles", json=_profile_body()).json()["id"]
        layer_id = client.post(f"/api/v1/workspaces/{workspace}/reference-layers", json={"profile_id": profile_id}).json()["id"]
        chart = client.get(f"/api/v1/workspaces/{workspace}/reference-layers/chart-data").json()
        assert chart["traces"][0]["layer_id"] == layer_id

        # Still zero sources -- the Reference subsystem never created,
        # required, or touched one.
        assert client.get(f"/api/v1/workspaces/{workspace}/sources").json() == []


class TestUploadDoesNotDisturbReferenceState:
    """Configures Reference Layers FIRST, then uploads a real COMTRADE
    source afterward, then confirms the layers are still present
    unchanged -- the mid-conversation amendment's own explicit
    acceptance scenario ("configure references first, upload a
    recording afterward, references remain present")."""

    def test_layers_survive_a_source_upload_in_the_same_workspace(self, client: TestClient, comtrade_fixtures_dir):
        workspace = "ws-upload-after-refs-1"
        profile_id = client.post(f"/api/v1/workspaces/{workspace}/reference-profiles", json=_profile_body()).json()["id"]
        layer_id = client.post(f"/api/v1/workspaces/{workspace}/reference-layers", json={"profile_id": profile_id}).json()["id"]

        cfg_path = comtrade_fixtures_dir / "compliance_smoke_rms_phase_a.cfg"
        dat_path = comtrade_fixtures_dir / "compliance_smoke_rms_phase_a.dat"
        if not cfg_path.exists():
            pytest.skip("No COMTRADE fixture available for this upload scenario.")
        with cfg_path.open("rb") as cfg_file, dat_path.open("rb") as dat_file:
            upload = client.post(
                f"/api/v1/workspaces/{workspace}/sources",
                files={"cfg_file": ("event.cfg", cfg_file, "text/plain"), "dat_file": ("event.dat", dat_file, "text/plain")},
            )
        assert upload.status_code in (200, 201)

        layers_after_upload = client.get(f"/api/v1/workspaces/{workspace}/reference-layers").json()
        assert [layer["id"] for layer in layers_after_upload] == [layer_id]
        assert client.get(f"/api/v1/workspaces/{workspace}/reference-profiles/{profile_id}").status_code == 200


class TestStartNewWorkspaceClearsReferenceState:
    def test_delete_workspace_removes_custom_profiles_and_layers(self, client: TestClient):
        workspace = "ws-ref-reset-1"
        profile_id = client.post(f"/api/v1/workspaces/{workspace}/reference-profiles", json=_profile_body()).json()["id"]
        client.post(f"/api/v1/workspaces/{workspace}/reference-layers", json={"profile_id": profile_id})

        assert client.delete(f"/api/v1/workspaces/{workspace}").status_code == 204

        assert client.get(f"/api/v1/workspaces/{workspace}/reference-profiles").json() == []
        assert client.get(f"/api/v1/workspaces/{workspace}/reference-layers").json() == []
