"""API-level tests for GET .../sources/{source_id}/table (Canonical Table
View, DEC-079). Exercises the real end-to-end flow through a fully wired
FastAPI TestClient (same pattern as test_waveform_api.py), for BOTH a
real COMTRADE upload and a converted CSV/Excel source -- proving the
endpoint is format-independent, never branching on provider_type.
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


WS = "ws-1"


def _read(path) -> bytes:
    return path.read_bytes()


def _upload_comtrade(client, comtrade_fixtures_dir, stem="synth_ascii") -> str:
    cfg = _read(comtrade_fixtures_dir / f"{stem}.cfg")
    dat = _read(comtrade_fixtures_dir / f"{stem}.dat")
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{WS}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _upload_csv_and_convert(client, content: bytes, filename: str = "e.csv") -> str:
    files = {"csv_file": (filename, content, "text/csv")}
    resp = client.post(f"/api/v1/workspaces/{WS}/preparation-sources", files=files)
    assert resp.status_code == 201, resp.text
    prep_source_id = resp.json()["source_id"]

    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/0/role", json={"role": "time_axis"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/1/role", json={"role": "waveform"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/2/role", json={"role": "waveform"})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/1/engineering-quantity",
        json={"engineering_quantity": "Voltage"},
    )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/2/engineering-quantity",
        json={"engineering_quantity": "Voltage Angle"},
    )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
    return converted["source_id"]


class TestComtradeTable:
    def test_table_returns_canonical_rows(self, client, comtrade_fixtures_dir):
        source_id = _upload_comtrade(client, comtrade_fixtures_dir)

        resp = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table", params={"offset": 0, "limit": 5})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["returned_row_count"] == 5
        assert body["total_row_count"] == 40  # synth_ascii.cfg's own known sample count
        assert body["columns"][0]["key"] == "time"

    def test_default_pagination(self, client, comtrade_fixtures_dir):
        source_id = _upload_comtrade(client, comtrade_fixtures_dir)

        resp = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table")

        assert resp.status_code == 200
        assert resp.json()["limit"] == 200  # TABLE_DEFAULT_LIMIT

    def test_source_not_found_404(self, client):
        resp = client.get(f"/api/v1/workspaces/{WS}/sources/does-not-exist/table")
        assert resp.status_code == 404

    def test_negative_offset_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload_comtrade(client, comtrade_fixtures_dir)
        resp = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table", params={"offset": -1})
        assert resp.status_code == 422

    def test_limit_beyond_max_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload_comtrade(client, comtrade_fixtures_dir)
        resp = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table", params={"limit": 5000})
        assert resp.status_code == 422

    def test_source_removed_while_referenced_returns_404(self, client, comtrade_fixtures_dir):
        source_id = _upload_comtrade(client, comtrade_fixtures_dir)
        client.delete(f"/api/v1/workspaces/{WS}/sources/{source_id}")

        resp = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table")

        assert resp.status_code == 404


class TestNoFormatBranching:
    def test_comtrade_and_converted_csv_return_the_same_response_shape(self, client, comtrade_fixtures_dir):
        comtrade_id = _upload_comtrade(client, comtrade_fixtures_dir)
        csv_id = _upload_csv_and_convert(
            client, b"Time,V1,V1 Angle\n0.00,132.1,10.0\n0.02,132.2,10.1\n0.04,132.0,9.9\n"
        )

        comtrade_body = client.get(f"/api/v1/workspaces/{WS}/sources/{comtrade_id}/table").json()
        csv_body = client.get(f"/api/v1/workspaces/{WS}/sources/{csv_id}/table").json()

        assert set(comtrade_body.keys()) == set(csv_body.keys())
        assert set(comtrade_body["columns"][0].keys()) == set(csv_body["columns"][0].keys())


class TestPreparedCsvTable:
    def test_engineering_quantity_visible_in_columns(self, client):
        source_id = _upload_csv_and_convert(
            client, b"Time,V1,V1 Angle\n0.00,132.1,10.0\n0.02,132.2,10.1\n0.04,132.0,9.9\n"
        )

        body = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table").json()

        by_key = {c["key"]: c for c in body["columns"]}
        assert by_key["V1"]["engineering_quantity"] == "Voltage"
        assert by_key["V1 Angle"]["engineering_quantity"] == "Voltage Angle"
        assert by_key["V1 Angle"]["engineering_type"] == "Voltage"

    def test_exact_canonical_values(self, client):
        source_id = _upload_csv_and_convert(
            client, b"Time,V1,V1 Angle\n0.00,132.1,10.0\n0.02,132.2,10.1\n0.04,132.0,9.9\n"
        )

        body = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table").json()

        v1_index = [c["key"] for c in body["columns"]].index("V1")
        assert [row[v1_index] for row in body["rows"]] == pytest.approx([132.1, 132.2, 132.0])

    def test_relative_time_column_label_and_values(self, client):
        source_id = _upload_csv_and_convert(
            client, b"Time,V1,V1 Angle\n0.00,132.1,10.0\n0.02,132.2,10.1\n0.04,132.0,9.9\n"
        )

        body = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table").json()

        assert body["columns"][0]["label"] == "Time (s)"
        assert [row[0] for row in body["rows"]] == ["0.000", "0.020", "0.040"]


class TestAgreementWithCleanedExport:
    """Task section 50: for a prepared CSV/Excel recording, Table View
    must agree SEMANTICALLY with the canonical cleaned export -- same
    active samples, same configured time semantics, same waveform
    values, same channel order, same Engineering Quantity meaning
    (formatting may differ, e.g. export's own header suffix grammar
    vs. Table's separate engineering_quantity column)."""

    def test_table_and_cleaned_export_agree_on_time_values_channel_order_and_data(self, client):
        content = b"Time,V1,V1 Angle\n0.00,132.1,10.0\n0.02,132.2,10.1\n0.04,132.0,9.9\n"
        prep = client.post(
            f"/api/v1/workspaces/{WS}/preparation-sources", files={"csv_file": ("e.csv", content, "text/csv")},
        ).json()
        prep_source_id = prep["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/header", json={"row_number": 1})
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/data-region",
            json={"start_row": 2, "end_row": 4},
        )
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/0/role", json={"role": "time_axis"})
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/1/role", json={"role": "waveform"})
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/2/role", json={"role": "waveform"})
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/1/engineering-quantity",
            json={"engineering_quantity": "Voltage"},
        )
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/2/engineering-quantity",
            json={"engineering_quantity": "Voltage Angle"},
        )
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/time-axis",
            json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
        )

        # Export BEFORE conversion -- the PreparationSession is deleted
        # once conversion succeeds (task section 52's own "existing
        # preparation lifecycle unchanged" rule), so this must happen
        # first, exactly like an engineer would use either feature
        # independently today.
        export_resp = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/export")
        assert export_resp.status_code == 200, export_resp.text
        import csv as csv_module
        import io as io_module
        exported_rows = list(csv_module.reader(io_module.StringIO(export_resp.content.decode("utf-8"))))
        exported_header = exported_rows[0]
        exported_data_rows = exported_rows[1:]

        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        table_body = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table").json()

        # Same channel/column order (Time first, then waveform columns
        # in source order) -- export's own suffix-encoded header vs.
        # Table's own base channel name + separate engineering_quantity
        # field, same underlying meaning.
        assert exported_header == ["Time (s)", "V1 (Voltage)", "V1 Angle (Voltage Angle)"]
        assert [c["key"] for c in table_body["columns"]] == ["time", "V1", "V1 Angle"]

        # Same active samples, same configured time semantics, same
        # waveform values.
        assert len(exported_data_rows) == table_body["total_row_count"] == 3
        for exported_row, table_row in zip(exported_data_rows, table_body["rows"]):
            assert exported_row[0] == table_row[0]  # canonical time, identical formatting
            assert float(exported_row[1]) == pytest.approx(table_row[1])
            assert float(exported_row[2]) == pytest.approx(table_row[2])


class TestPerUnitDoesNotAffectTable:
    def test_table_ignores_workspace_per_unit_mode_configuration(self, client):
        prep_source_id_body = client.post(
            f"/api/v1/workspaces/{WS}/preparation-sources",
            files={"csv_file": ("e.csv", b"Time,V1\n0.00,132.1\n0.02,132.2\n0.04,132.0\n", "text/csv")},
        ).json()
        prep_source_id = prep_source_id_body["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/header", json={"row_number": 1})
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/data-region",
            json={"start_row": 2, "end_row": 4},
        )
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/0/role", json={"role": "time_axis"})
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/1/role", json={"role": "waveform"})
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/columns/1/engineering-quantity",
            json={"engineering_quantity": "Voltage"},
        )
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/working/time-axis",
            json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
        )
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 132.0})

        # The table endpoint accepts no unit_mode parameter at all --
        # confirming it always serves canonical engineering values,
        # never a per-unit-converted display, regardless of what the
        # workspace's own Waveform View unit mode is set to elsewhere.
        body = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/table").json()

        v1_index = [c["key"] for c in body["columns"]].index("V1")
        assert [row[v1_index] for row in body["rows"]] == pytest.approx([132.1, 132.2, 132.0])
