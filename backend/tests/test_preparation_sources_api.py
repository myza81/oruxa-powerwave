"""API-level tests for the CSV/Excel preparation-source endpoints (Slices 1-2, DEC-072).

Mirrors tests/test_sources_api.py's own TestClient pattern. Covers the
"CSV upload"/"Excel upload"/"worksheet discovery"/"Invalid upload"
categories from this slice's own testing requirements, plus the
guardrail that a preparation source never becomes waveform-ready.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _csv_file(content: bytes = b"time,VA\n0.0,1.0\n0.001,2.0\n", filename: str = "event.csv"):
    return {"csv_file": (filename, io.BytesIO(content), "text/csv")}


_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_xlsx(sheets: dict | None = None, hidden: frozenset = frozenset()) -> bytes:
    if sheets is None:
        sheets = {"Sheet1": [["a", "b"], [1, 2]]}
    workbook = Workbook()
    names = list(sheets.keys())
    workbook.active.title = names[0]
    for row in sheets[names[0]]:
        workbook.active.append(row)
    for name in names[1:]:
        ws = workbook.create_sheet(name)
        for row in sheets[name]:
            ws.append(row)
    for name in hidden:
        workbook[name].sheet_state = "hidden"
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _excel_file(content: bytes | None = None, filename: str = "event.xlsx"):
    if content is None:
        content = _build_xlsx()
    return {"excel_file": (filename, io.BytesIO(content), _XLSX_CONTENT_TYPE)}


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
        # Slice 2 (DEC-072): the endpoint's own upload fields became
        # optional (csv_file OR excel_file, exactly one) so a second
        # format could share this endpoint without breaking Slice 1's
        # own required-field shape for a REAL upload -- providing
        # neither is now a deliberate, explicit 400
        # "ambiguous_preparation_upload" business-rule rejection rather
        # than FastAPI's generic 422 "field required" validation error.
        # A real Slice 1 CSV upload (csv_file present) is unaffected --
        # see TestCsvUpload above, still green.
        resp = client.post("/api/v1/workspaces/ws-1/preparation-sources", files={})

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "ambiguous_preparation_upload"

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


# ---- CSV/Excel ingestion Slice 2 (DEC-072): Excel upload + worksheet discovery ----


class TestExcelUpload:
    def test_valid_single_sheet_excel_upload_returns_201_with_auto_selected_sheet(self, client):
        content = _build_xlsx({"Event Data": [["time", "VA"], [0.0, 1.0]]})

        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_excel_file(content, "Event.xlsx"),
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["file_format"] == "Excel"
        assert body["original_filename"] == "Event.xlsx"
        assert body["file_size_bytes"] == len(content)
        assert body["status"] == "needs_preparation"
        assert [w["name"] for w in body["worksheets"]] == ["Event Data"]
        assert body["worksheets"][0]["index"] == 0
        assert body["worksheets"][0]["visible"] is True
        assert body["selected_worksheet_index"] == 0
        # Never fabricated waveform metadata anywhere in this response.
        assert "raw_bytes" not in body

    def test_multi_sheet_workbook_discovers_all_four_sheets(self, client):
        content = _build_xlsx({
            "Event Data": [["time", "VA"]],
            "RMS": [["time", "rms"]],
            "Settings": [["k", "v"]],
            "Summary": [["note"]],
        })

        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_excel_file(content, "multi.xlsx"),
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert [w["name"] for w in body["worksheets"]] == ["Event Data", "RMS", "Settings", "Summary"]
        assert body["selected_worksheet_index"] is None

    def test_hidden_sheet_is_reported_as_not_visible(self, client):
        content = _build_xlsx(
            {"Visible": [["a"]], "Hidden": [["b"]]}, hidden=frozenset({"Hidden"}),
        )

        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "h.xlsx"),
        )

        by_name = {w["name"]: w for w in resp.json()["worksheets"]}
        assert by_name["Visible"]["visible"] is True
        assert by_name["Hidden"]["visible"] is False

    def test_uploaded_excel_source_appears_in_the_preparation_sources_list(self, client):
        upload_resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file()
        )
        source_id = upload_resp.json()["source_id"]

        list_resp = client.get("/api/v1/workspaces/ws-1/preparation-sources")

        assert list_resp.status_code == 200
        ids = [s["source_id"] for s in list_resp.json()]
        assert ids == [source_id]

    def test_an_excel_preparation_source_is_never_created_as_a_comtrade_source(self, client):
        client.post("/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file())

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []

    def test_csv_and_excel_can_coexist_in_the_same_workspace(self, client):
        csv_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file()
        ).json()["source_id"]
        excel_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file()
        ).json()["source_id"]

        listed = client.get("/api/v1/workspaces/ws-1/preparation-sources").json()
        ids = {s["source_id"] for s in listed}
        formats_by_id = {s["source_id"]: s["file_format"] for s in listed}
        assert ids == {csv_id, excel_id}
        assert formats_by_id[csv_id] == "CSV"
        assert formats_by_id[excel_id] == "Excel"
        # CSV's own worksheet field stays empty -- no fake sheet metadata
        # invented for a format with no worksheet concept.
        assert [s["worksheets"] for s in listed if s["source_id"] == csv_id] == [[]]


class TestInvalidExcelUpload:
    def test_legacy_xls_extension_is_rejected_as_unsupported(self, client):
        # .xls is explicitly deferred this slice (see
        # app.domain.preparation_session's own module docstring) -- a
        # real attempt must be rejected cleanly, not silently mis-handled.
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files={"excel_file": ("legacy.xls", io.BytesIO(_build_xlsx()), "application/vnd.ms-excel")},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unsupported_file_type"

    def test_empty_excel_upload_returns_400(self, client):
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_excel_file(b"", "empty.xlsx"),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_file"

    def test_corrupt_workbook_returns_400_workbook_parse_error(self, client):
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_excel_file(b"not a real workbook" * 10, "corrupt.xlsx"),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "workbook_parse_error"
        assert client.get("/api/v1/workspaces/ws-1/preparation-sources").json() == []

    def test_non_excel_bytes_renamed_xlsx_returns_400_workbook_parse_error(self, client):
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files=_excel_file(b"time,VA\n0.0,1.0\n", "fake.xlsx"),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "workbook_parse_error"

    def test_both_csv_and_excel_provided_is_rejected(self, client):
        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources",
            files={
                "csv_file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv"),
                "excel_file": ("b.xlsx", io.BytesIO(_build_xlsx()), _XLSX_CONTENT_TYPE),
            },
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "ambiguous_preparation_upload"
        assert client.get("/api/v1/workspaces/ws-1/preparation-sources").json() == []

    def test_oversized_excel_returns_413(self, client):
        # settings fixture configures max_event_upload_size_mb=100.
        big_content = _build_xlsx() + b"\x00" * (101 * 1024 * 1024)

        resp = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(big_content, "big.xlsx"),
        )

        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == "upload_too_large"


class TestWorksheetSelectionApi:
    def test_select_a_worksheet_via_patch(self, client):
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        resp = client.patch(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}",
            json={"selected_worksheet_index": 1},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["selected_worksheet_index"] == 1
        # The change is durable across a fresh GET, not just echoed back.
        get_resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")
        assert get_resp.json()["selected_worksheet_index"] == 1

    def test_select_out_of_range_index_returns_400(self, client):
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        resp = client.patch(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}",
            json={"selected_worksheet_index": 5},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_worksheet_index"

    def test_select_on_a_csv_source_returns_400_not_applicable(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(),
        ).json()["source_id"]

        resp = client.patch(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}",
            json={"selected_worksheet_index": 0},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "worksheet_selection_not_applicable"

    def test_select_on_unknown_source_returns_404(self, client):
        resp = client.patch(
            "/api/v1/workspaces/ws-1/preparation-sources/does-not-exist",
            json={"selected_worksheet_index": 0},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestExcelLifecycle:
    def test_delete_removes_the_excel_session(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(),
        ).json()["source_id"]

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        assert resp.status_code == 204
        assert (
            client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}").status_code == 404
        )

    def test_workspace_delete_also_releases_excel_sessions(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(),
        ).json()["source_id"]

        resp = client.delete("/api/v1/workspaces/ws-1")

        assert resp.status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/preparation-sources").json() == []
        assert (
            client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}").status_code == 404
        )
