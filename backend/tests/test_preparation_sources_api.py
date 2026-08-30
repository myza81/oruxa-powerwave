"""API-level tests for the Slice 1 CSV preparation-source endpoints (DEC-072).

Mirrors tests/test_sources_api.py's own TestClient pattern. Covers the
"CSV upload" and "Invalid upload" categories from this slice's own
testing requirements, plus the guardrail that a preparation source never
becomes waveform-ready.
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


def _csv_file(content: bytes = b"time,VA\n0.0,1.0\n0.001,2.0\n", filename: str = "event.csv"):
    return {"csv_file": (filename, io.BytesIO(content), "text/csv")}


class TestCsvUpload:
    def test_valid_csv_upload_returns_201_with_preparation_summary(self, client):
        content = b"time,VA\n0.0,1.0\n0.001,2.0\n"

        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_csv_file(content, "GPTH disturbance.csv"),
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["workspace_id"] == "ws-1"
        assert body["file_format"] == "CSV"
        assert body["original_filename"] == "GPTH disturbance.csv"
        assert body["file_size_bytes"] == len(content)
        assert body["status"] == "needs_preparation"
        assert body["source_id"]
        assert "created_at" in body
        # No raw bytes, no waveform/channel shape anywhere in the response.
        assert "raw_bytes" not in body
        assert "analog_channels" not in body

    def test_uploaded_source_appears_in_the_preparation_sources_list(self, client):
        upload_resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file()
        )
        source_id = upload_resp.json()["source_id"]

        list_resp = client.get("/api/v1/workspaces/ws-1/preparation-sources")

        assert list_resp.status_code == 200
        ids = [s["source_id"] for s in list_resp.json()]
        assert ids == [source_id]

    def test_get_one_preparation_source_returns_the_same_summary(self, client):
        upload_resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file()
        )
        source_id = upload_resp.json()["source_id"]

        get_resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        assert get_resp.status_code == 200
        assert get_resp.json() == upload_resp.json()

    def test_a_csv_preparation_source_is_never_created_as_a_comtrade_source(self, client):
        client.post("/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file())

        # It must not appear on the COMTRADE-shaped sources list at all --
        # this is the structural reason a "Needs Preparation" CSV can
        # never reach normal waveform loading (it isn't even reachable
        # through that endpoint, not merely hidden by a status check).
        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []

    def test_workspaces_are_isolated(self, client):
        resp_a = client.post("/api/v1/workspaces/ws-a/preparation-sources", files=_csv_file())
        source_id_a = resp_a.json()["source_id"]

        assert client.get("/api/v1/workspaces/ws-b/preparation-sources").json() == []
        assert (
            client.get(f"/api/v1/workspaces/ws-b/preparation-sources/{source_id_a}").status_code
            == 404
        )


class TestInvalidCsvUpload:
    def test_unsupported_extension_returns_400(self, client):
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_csv_file(b"not a csv", "event.txt"),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unsupported_file_type"
        assert client.get("/api/v1/workspaces/ws-1/preparation-sources").json() == []

    def test_missing_csv_file_field_is_a_validation_error(self, client):
        resp = client.post("/api/v1/workspaces/ws-1/preparation-sources", files={})

        assert resp.status_code == 422

    def test_empty_csv_returns_400(self, client):
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(b"", "empty.csv")
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_file"

    def test_oversized_csv_returns_413(self, client):
        # settings fixture configures max_event_upload_size_mb=100; a
        # content-length header well beyond that is rejected by the
        # fast pre-check middleware before this endpoint even runs.
        big_content = b"x" * (101 * 1024 * 1024)

        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(big_content, "big.csv")
        )

        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == "upload_too_large"

    def test_blank_workspace_id_is_rejected(self, client):
        resp = client.post(
            "/api/v1/workspaces/%20/preparation-sources", files=_csv_file()
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_workspace"

    def test_get_unknown_source_returns_404(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/preparation-sources/does-not-exist")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestPreparationSourceLifecycle:
    def test_delete_removes_the_source(self, client):
        upload_resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file()
        )
        source_id = upload_resp.json()["source_id"]

        delete_resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        assert delete_resp.status_code == 204
        assert (
            client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}").status_code
            == 404
        )
        assert client.get("/api/v1/workspaces/ws-1/preparation-sources").json() == []

    def test_delete_unknown_source_returns_404(self, client):
        resp = client.delete("/api/v1/workspaces/ws-1/preparation-sources/does-not-exist")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_delete_does_not_affect_other_sources_in_the_same_workspace(self, client):
        source_id_a = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(filename="a.csv")
        ).json()["source_id"]
        source_id_b = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(filename="b.csv")
        ).json()["source_id"]

        assert client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id_a}").status_code == 204

        remaining = client.get("/api/v1/workspaces/ws-1/preparation-sources").json()
        assert [s["source_id"] for s in remaining] == [source_id_b]

    def test_workspace_delete_also_releases_preparation_sources(self, client):
        # Regression test for app.api.v1.workspaces.delete_workspace's
        # new preparation_session_registry.remove_workspace() call
        # (Slice 1, DEC-072) -- "Start New Workspace" must discard an
        # in-progress CSV upload exactly like it discards a fully
        # imported COMTRADE source.
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file()
        ).json()["source_id"]

        resp = client.delete("/api/v1/workspaces/ws-1")

        assert resp.status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/preparation-sources").json() == []
        assert (
            client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}").status_code
            == 404
        )

    def test_workspace_delete_does_not_affect_other_workspaces_preparation_sources(self, client):
        target_source_id = client.post(
            "/api/v1/workspaces/ws-target/preparation-sources", files=_csv_file()
        ).json()["source_id"]
        other_source_id = client.post(
            "/api/v1/workspaces/ws-other/preparation-sources", files=_csv_file()
        ).json()["source_id"]

        assert client.delete("/api/v1/workspaces/ws-target").status_code == 204

        assert client.get("/api/v1/workspaces/ws-target/preparation-sources").json() == []
        remaining = client.get("/api/v1/workspaces/ws-other/preparation-sources").json()
        assert [s["source_id"] for s in remaining] == [other_source_id]
