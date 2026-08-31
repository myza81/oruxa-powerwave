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


# ---- CSV/Excel ingestion Slice 3 (DEC-072): paged raw-data preview ----


class TestCsvRowsApi:
    def test_response_schema_and_exact_offset_limit_and_row_numbering(self, client):
        content = ("\n".join(f"{i},v{i}" for i in range(1, 11))).encode()
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(content, "e.csv"),
        ).json()["source_id"]

        resp = client.get(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows",
            params={"offset": 2, "limit": 3},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["selected_worksheet_index"] is None
        assert body["offset"] == 2
        assert body["limit"] == 3
        assert body["returned_row_count"] == 3
        assert [r["row_number"] for r in body["rows"]] == [3, 4, 5]
        assert body["rows"][0]["cells"] == ["3", "v3"]
        assert body["total_row_count"] == 10
        assert body["total_row_count_basis"] == "exact"
        assert body["column_count"] == 2
        assert body["column_count_basis"] == "exact"
        # No file path, no waveform-shaped fields anywhere.
        assert "file_path" not in str(body)

    def test_default_offset_and_limit(self, client):
        content = b"a,b\n1,2\n"
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(content, "e.csv"),
        ).json()["source_id"]

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["offset"] == 0
        assert body["limit"] == 200

    def test_negative_offset_is_rejected(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(),
        ).json()["source_id"]

        resp = client.get(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows", params={"offset": -1},
        )

        assert resp.status_code == 422

    def test_zero_limit_is_rejected(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(),
        ).json()["source_id"]

        resp = client.get(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows", params={"limit": 0},
        )

        assert resp.status_code == 422

    def test_excessive_limit_is_rejected(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(),
        ).json()["source_id"]

        resp = client.get(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows", params={"limit": 1001},
        )

        assert resp.status_code == 422

    def test_preview_of_deleted_source_returns_404(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(),
        ).json()["source_id"]
        client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_preview_never_registers_a_waveform_ready_source(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(),
        ).json()["source_id"]

        client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []


class TestExcelRowsApi:
    def test_single_sheet_preview_via_api(self, client):
        content = _build_xlsx({"Only": [["time", "VA"], [0.0, 1.0]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "e.xlsx"),
        ).json()["source_id"]

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["selected_worksheet_index"] == 0
        assert body["rows"][0]["cells"] == ["time", "VA"]
        assert body["total_row_count_basis"] == "best_effort"

    def test_multi_sheet_requires_selection_first(self, client):
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "worksheet_not_selected"

    def test_preview_after_worksheet_selection(self, client):
        content = _build_xlsx({"A": [["from-a"]], "B": [["from-b"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        client.patch(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}",
            json={"selected_worksheet_index": 1},
        )
        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["selected_worksheet_index"] == 1
        assert body["rows"][0]["cells"] == ["from-b"]

    def test_switching_worksheet_changes_the_preview(self, client):
        content = _build_xlsx({"A": [["from-a"]], "B": [["from-b"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 0})
        first = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert first["rows"][0]["cells"] == ["from-a"]

        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 1})
        second = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert second["rows"][0]["cells"] == ["from-b"]

    def test_hidden_sheet_preview_after_selection(self, client):
        content = _build_xlsx({"Visible": [["v"]], "Hidden": [["h"]]}, hidden=frozenset({"Hidden"}))
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "h.xlsx"),
        ).json()["source_id"]

        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 1})
        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.json()["rows"][0]["cells"] == ["h"]

    def test_preview_of_deleted_excel_source_returns_404(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(),
        ).json()["source_id"]
        client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert resp.status_code == 404

    def test_preview_never_registers_a_waveform_ready_source(self, client):
        content = _build_xlsx({"Only": [["a"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "e.xlsx"),
        ).json()["source_id"]

        client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows")

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []


# ---- CSV/Excel ingestion Slice 4 (DEC-072): Working Dataset overlay API ----


def _upload_csv(client, content: bytes = b"a,b\n1,2\n3,4\n", filename: str = "e.csv") -> str:
    return client.post(
        "/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file(content, filename),
    ).json()["source_id"]


class TestWorkingSummaryOnExistingEndpoints:
    def test_freshly_uploaded_source_reports_an_empty_working_overlay(self, client):
        source_id = _upload_csv(client)

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        overlay = resp.json()["working_overlay"]
        assert overlay == {
            "working_revision": 0,
            "edited_cell_count": 0,
            "excluded_row_count": 0,
            "ignored_column_count": 0,
            "can_undo": False,
            "can_redo": False,
            "header_row_number": None,
            "data_start_row": None,
            "data_end_row": None,
        }

    def test_upload_response_itself_includes_an_empty_working_overlay(self, client):
        resp = client.post("/api/v1/workspaces/ws-1/preparation-sources", files=_csv_file())

        assert resp.json()["working_overlay"]["edited_cell_count"] == 0

    def test_get_reflects_edits_made_via_the_working_endpoints(self, client):
        source_id = _upload_csv(client)

        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0",
            json={"value": "X"},
        )

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}")

        assert resp.json()["working_overlay"]["edited_cell_count"] == 1
        assert resp.json()["working_overlay"]["working_revision"] == 1

    def test_list_reflects_edits_too(self, client):
        source_id = _upload_csv(client)
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0",
            json={"value": "X"},
        )

        resp = client.get("/api/v1/workspaces/ws-1/preparation-sources")

        assert resp.json()[0]["working_overlay"]["edited_cell_count"] == 1


class TestCellWorkingEndpoints:
    def test_put_cell_edits_and_preview_reflects_it(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0",
            json={"value": "EDITED"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["edited_cell_count"] == 1
        assert resp.json()["working_revision"] == 1

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["rows"][0]["cells"] == ["EDITED", "b"]
        assert rows["working_revision"] == 1
        assert rows["rows"][0]["modified_cells"] == [{"column_index": 0, "raw_value": "a"}]

    def test_put_cell_clear_sets_none_in_preview(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/1",
            json={"value": None},
        )

        assert resp.status_code == 200, resp.text
        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["rows"][0]["cells"] == ["a", None]

    def test_delete_cell_resets_it(self, client):
        source_id = _upload_csv(client)
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0",
            json={"value": "X"},
        )

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0")

        assert resp.status_code == 200, resp.text
        assert resp.json()["edited_cell_count"] == 0

    def test_put_cell_beyond_known_bounds_returns_400(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/999/0",
            json={"value": "X"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_coordinate"

    def test_put_cell_negative_row_number_returns_422(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/0/0",
            json={"value": "X"},
        )

        assert resp.status_code == 422  # Path(ge=1) rejects row_number=0

    def test_put_cell_negative_column_index_returns_422(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/-1",
            json={"value": "X"},
        )

        assert resp.status_code == 422  # Path(ge=0) rejects column_index=-1

    def test_put_cell_oversized_value_returns_400(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0",
            json={"value": "x" * 10_001},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_cell_value"

    def test_put_cell_on_unknown_source_returns_404(self, client):
        resp = client.put(
            "/api/v1/workspaces/ws-1/preparation-sources/does-not-exist/working/cells/1/0",
            json={"value": "X"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_put_cell_on_multi_sheet_excel_without_selection_returns_400(self, client):
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0",
            json={"value": "X"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "worksheet_not_selected"


class TestRowAndColumnWorkingEndpoints:
    def test_put_row_exclusion_reflects_in_preview(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/rows/2",
            json={"excluded": True},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["excluded_row_count"] == 1

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        excluded_flags = {r["row_number"]: r["excluded"] for r in rows["rows"]}
        assert excluded_flags[2] is True
        assert excluded_flags[1] is False

    def test_put_row_beyond_known_bounds_returns_400(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/rows/999",
            json={"excluded": True},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_coordinate"

    def test_put_column_ignore_reflects_in_preview(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1",
            json={"ignored": True},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["ignored_column_count"] == 1

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["ignored_columns"] == [1]

    def test_put_column_beyond_known_bounds_returns_400(self, client):
        source_id = _upload_csv(client)

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/999",
            json={"ignored": True},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_coordinate"


class TestResetAllAndUndoRedoEndpoints:
    def test_delete_working_resets_everything(self, client):
        source_id = _upload_csv(client)
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0", json={"value": "X"})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/rows/2", json={"excluded": True})

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["edited_cell_count"] == 0
        assert body["excluded_row_count"] == 0

    def test_undo_after_edit_reverts_it(self, client):
        source_id = _upload_csv(client)
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0", json={"value": "X"})

        resp = client.post(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/undo")

        assert resp.status_code == 200, resp.text
        assert resp.json()["edited_cell_count"] == 0
        assert resp.json()["can_redo"] is True

    def test_redo_after_undo_reapplies_it(self, client):
        source_id = _upload_csv(client)
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0", json={"value": "X"})
        client.post(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/undo")

        resp = client.post(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/redo")

        assert resp.status_code == 200, resp.text
        assert resp.json()["edited_cell_count"] == 1

    def test_undo_with_no_history_is_a_safe_no_op_200(self, client):
        source_id = _upload_csv(client)

        resp = client.post(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/undo")

        assert resp.status_code == 200, resp.text
        assert resp.json()["can_undo"] is False

    def test_reset_all_on_unknown_source_returns_404(self, client):
        resp = client.delete("/api/v1/workspaces/ws-1/preparation-sources/does-not-exist/working")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestWorkingOverlayDoesNotAffectWaveformOrOtherWorkspaces:
    def test_editing_never_registers_a_waveform_ready_source(self, client):
        source_id = _upload_csv(client)

        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0", json={"value": "X"})

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []

    def test_working_edits_are_workspace_isolated(self, client):
        source_id_a = client.post(
            "/api/v1/workspaces/ws-a/preparation-sources", files=_csv_file(),
        ).json()["source_id"]

        resp = client.put(
            f"/api/v1/workspaces/ws-b/preparation-sources/{source_id_a}/working/cells/1/0",
            json={"value": "X"},
        )

        assert resp.status_code == 404


# ---- CSV/Excel ingestion Slice 5 (DEC-072): Header/Data Region + Column Role Mapping API ----


class TestHeaderEndpoints:
    def test_put_header_and_preview_reflects_labels(self, client):
        source_id = _upload_csv(client, content=b"Station: GPTH\nEvent: Trip\nTime,VR\n0.0,1\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header",
            json={"row_number": 3},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["header_row_number"] == 3

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["header_row_number"] == 3
        assert rows["column_labels"] == ["Time", "VR"]
        header_flags = {r["row_number"]: r["is_header"] for r in rows["rows"]}
        assert header_flags == {1: False, 2: False, 3: True, 4: False}

    def test_delete_header_reverts_to_letters(self, client):
        source_id = _upload_csv(client, content=b"Time,VR\n0.0,1\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header")

        assert resp.status_code == 200, resp.text
        assert resp.json()["header_row_number"] is None
        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_labels"] == ["A", "B"]

    def test_header_beyond_known_bounds_returns_400(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header",
            json={"row_number": 999},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_coordinate"

    def test_header_on_unknown_source_returns_404(self, client):
        resp = client.put(
            "/api/v1/workspaces/ws-1/preparation-sources/does-not-exist/working/header",
            json={"row_number": 1},
        )

        assert resp.status_code == 404

    def test_blank_and_duplicate_headers(self, client):
        source_id = _upload_csv(client, content=b"Time,VR,,VR\n0.0,1,2,4\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()

        assert rows["column_labels"] == ["Time", "VR", "Column C", "VR"]

    def test_working_header_edit_updates_label_and_reset_restores_it(self, client):
        source_id = _upload_csv(client, content=b"Vr,Vy\n1,2\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0", json={"value": "VR"})

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_labels"][0] == "VR"

        client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/cells/1/0")
        rows_after_reset = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows_after_reset["column_labels"][0] == "Vr"


class TestDataRegionEndpoints:
    def test_put_region_and_preview_reflects_flags(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n3,4\n5,6\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 2, "end_row": 3},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data_start_row"] == 2
        assert resp.json()["data_end_row"] == 3

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        flags = {r["row_number"]: r["in_active_region"] for r in rows["rows"]}
        assert flags == {1: False, 2: True, 3: True, 4: False}

    def test_delete_region_reactivates_full_source(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n3,4\n")
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 1, "end_row": 1},
        )

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region")

        assert resp.status_code == 200, resp.text
        assert resp.json()["data_start_row"] is None
        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert all(r["in_active_region"] for r in rows["rows"])

    def test_start_greater_than_end_returns_400(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n3,4\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 3, "end_row": 1},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_data_region"

    def test_region_beyond_known_bounds_returns_400(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 1, "end_row": 999},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_coordinate"

    def test_excluded_row_inside_region_reports_both_flags(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n3,4\n5,6\n")
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 1, "end_row": 3},
        )
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/rows/2", json={"excluded": True})

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        row2 = next(r for r in rows["rows"] if r["row_number"] == 2)
        assert row2["in_active_region"] is True
        assert row2["excluded"] is True


class TestColumnRoleEndpoints:
    def test_put_role_and_preview_reflects_it(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role",
            json={"role": "time_axis"},
        )

        assert resp.status_code == 200, resp.text
        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"] == ["time_axis", "unknown"]

    def test_multiple_time_axis_columns_allowed(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1/role",
            json={"role": "time_axis"},
        )

        assert resp.status_code == 200, resp.text
        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"] == ["time_axis", "time_axis"]

    def test_delete_role_resets_to_unknown(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role", json={"role": "waveform"})

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role")

        assert resp.status_code == 200, resp.text
        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"][0] == "unknown"

    def test_ignore_role_resets_to_unknown_too(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role", json={"role": "ignore"})

        client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role")

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"][0] == "unknown"

    def test_invalid_role_returns_400(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role",
            json={"role": "voltage"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_column_role"

    def test_role_column_beyond_known_bounds_returns_400(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        resp = client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/99/role",
            json={"role": "metadata"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_working_coordinate"


class TestIgnoreMigrationCoherence:
    """Slice 4's legacy boolean ignore endpoint and Slice 5's role
    endpoint must always agree -- see
    app.services.working_overlay_service.set_column_ignored's own
    docstring for why there is exactly one underlying representation."""

    def test_legacy_ignore_then_role_endpoint_agree(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1", json={"ignored": True})

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"][1] == "ignore"
        assert rows["ignored_columns"] == [1]

    def test_role_ignore_then_legacy_unignore_agree(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1/role", json={"role": "ignore"})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1", json={"ignored": False})

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"][1] == "unknown"
        assert rows["ignored_columns"] == []

    def test_legacy_unignore_never_disturbs_a_different_explicit_role(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})

        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1", json={"ignored": False})

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_roles"][1] == "waveform"


class TestResetAllIncludesStructureMapping:
    def test_reset_all_clears_header_region_and_roles(self, client):
        source_id = _upload_csv(client, content=b"Time,VR\n0.0,1\n0.001,2\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 2, "end_row": 2},
        )
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})

        resp = client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["header_row_number"] is None
        assert body["data_start_row"] is None

        rows = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows["column_labels"] == ["A", "B"]
        assert rows["column_roles"] == ["unknown", "unknown"]
        assert all(r["in_active_region"] for r in rows["rows"])


class TestExcelWorksheetIsolationForStructureMapping:
    def test_configuring_one_sheet_does_not_affect_another(self, client):
        content = _build_xlsx({
            "A": [["Time", "VR"], [0.0, 1.0], [0.001, 2.0]],
            "B": [["x"], [1], [2]],
        })
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 0})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 2, "end_row": 3},
        )
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})

        # Sheet B starts completely unconfigured.
        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 1})
        rows_b = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows_b["header_row_number"] is None
        assert rows_b["data_start_row"] is None
        assert rows_b["column_roles"] == ["unknown"]

        # Configure sheet B differently.
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role", json={"role": "metadata"})

        # Sheet A's own configuration remains intact.
        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 0})
        rows_a = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/rows").json()
        assert rows_a["header_row_number"] == 1
        assert rows_a["data_start_row"] == 2
        assert rows_a["data_end_row"] == 3
        assert rows_a["column_roles"] == ["time_axis", "unknown"]


# ---- CSV/Excel ingestion Slice 6 (DEC-072): Preparation Readiness Issue API ----


class TestPreparationIssuesEndpoint:
    def test_get_issues_returns_schema_and_counts(self, client):
        source_id = _upload_csv(client, content=b"a,b,c\n1,2,3\n")

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["evaluated_revision"] == 0
        assert body["current_revision"] == 0
        assert body["is_stale"] is False
        assert body["blocking_count"] == 0
        assert body["warning_count"] == 0
        assert body["info_count"] == len(body["issues"])
        codes = {i["code"] for i in body["issues"]}
        assert codes == {"header_not_selected", "data_region_unconfigured", "column_roles_unassigned"}
        assert all(i["severity"] == "info" for i in body["issues"])

    def test_issue_codes_are_stable_and_locations_present(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        body = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues").json()

        by_code = {i["code"]: i for i in body["issues"]}
        assert by_code["header_not_selected"]["location"]["field"] == "header"
        assert by_code["header_not_selected"]["location"]["worksheet_index"] is None
        assert by_code["data_region_unconfigured"]["location"]["field"] == "data_region"
        assert by_code["header_not_selected"]["suggested_action"]

    def test_setting_header_removes_the_issue_and_bumps_revision(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        body = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues").json()

        assert "header_not_selected" not in {i["code"] for i in body["issues"]}
        assert body["evaluated_revision"] == 1

    def test_issues_on_unknown_source_returns_404(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/preparation-sources/does-not-exist/issues")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_issues_on_multi_sheet_excel_without_selection_returns_400(self, client):
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]

        resp = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues")

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "worksheet_not_selected"

    def test_issues_scoped_to_selected_excel_worksheet(self, client):
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=_excel_file(content, "m.xlsx"),
        ).json()["source_id"]
        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 0})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})

        body_a = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues").json()
        assert "header_not_selected" not in {i["code"] for i in body_a["issues"]}

        client.patch(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}", json={"selected_worksheet_index": 1})
        body_b = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues").json()
        assert "header_not_selected" in {i["code"] for i in body_b["issues"]}

    def test_issues_never_appear_via_runtime_error_response(self, client):
        # Task's own explicit rule: a runtime failure must never be
        # represented as a PreparationIssue in an error body.
        resp = client.get("/api/v1/workspaces/ws-1/preparation-sources/does-not-exist/issues")

        assert "severity" not in resp.text
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_reset_all_restores_all_three_issues(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        client.put(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 1, "end_row": 1},
        )
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/0/role", json={"role": "waveform"})
        client.put(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})

        client.delete(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/working")
        body = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues").json()

        codes = {i["code"] for i in body["issues"]}
        assert codes == {"header_not_selected", "data_region_unconfigured", "column_roles_unassigned"}

    def test_recording_status_remains_needs_preparation(self, client):
        # Slice 6 must not introduce a status transition.
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues")
        summary = client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}").json()

        assert summary["status"] == "needs_preparation"

    def test_issues_never_registers_a_waveform_ready_source(self, client):
        source_id = _upload_csv(client, content=b"a,b\n1,2\n")

        client.get(f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/issues")

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []
