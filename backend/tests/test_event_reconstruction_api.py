"""API tests for Event Reconstruction (DEC-123/DEC-124/DEC-128), end to
end through the real app: real COMTRADE uploads (start time edited in the
CFG; each upload is one independent record) plus injected Time-of-Day and
elapsed-only sources for the ineligible cases."""

from __future__ import annotations

import dataclasses
import io
import json
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.main import create_app

# synth_ascii.cfg records 06/03/2026 10:00:00 (naive, Asia/Kuala_Lumpur).
FIXTURE_START = datetime(2026, 3, 6, 10, 0, 0)
_TIMESTAMP_LINE = re.compile(rb"^\d{2}/\d{2}/\d{4},\d{2}:\d{2}:\d{2}\.\d{6}(\r?)$", re.MULTILINE)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _cfg_starting_at(cfg: bytes, start: datetime) -> bytes:
    stamps = iter([start, start + timedelta(milliseconds=5)])

    def repl(match: re.Match) -> bytes:
        return next(stamps).strftime("%d/%m/%Y,%H:%M:%S.%f").encode() + match.group(1)

    return _TIMESTAMP_LINE.sub(repl, cfg, count=2)


def _upload(client, ws, comtrade_fixtures_dir, *, offset_s: float = 0.0) -> str:
    cfg = _cfg_starting_at((comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes(), FIXTURE_START + timedelta(seconds=offset_s))
    dat = (comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()
    files = {
        "cfg_file": ("synth.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("synth.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{ws}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _inject(client, ws, source_id, *, timing_reference, time_of_day_s=None) -> None:
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="S", recorder_name="R", source_file="x.csv", provider_type="CSV", nominal_frequency=50.0
        ),
        waveform_data=pd.DataFrame({"time": np.linspace(0.0, 1.0, 11), "V": np.zeros(11)}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[10.0], samples_per_rate=[11]),
        timing_info=TimingInformation(start_time=FIXTURE_START, trigger_time=FIXTURE_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=ws, provider_type="CSV", original_filenames=("x.csv",),
        created_at=FIXTURE_START, station_name="S", recorder_name="R", nominal_frequency=50.0,
        timing_reference=timing_reference, start_time=None, trigger_time=None, sample_count=11,
        duration_seconds=1.0, elapsed_start_seconds=0.0, elapsed_end_seconds=1.0,
        sampling_rates=(10.0,), samples_per_rate=(11,), analog_channels=[], digital_channels=[],
        time_of_day_reference_seconds=time_of_day_s,
    )
    client.app.state.workspace_registry.add(ActiveSource(metadata=metadata, record=record))


def _url(ws, path=""):
    return f"/api/v1/workspaces/{ws}/event-reconstruction{path}"


def _assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == code
    assert isinstance(detail["message"], str) and detail["message"]


def _pair(client, ws, comtrade_fixtures_dir, *, offset_s=10.0):
    a = _upload(client, ws, comtrade_fixtures_dir)
    b = _upload(client, ws, comtrade_fixtures_dir, offset_s=offset_s)
    return a, b


def _define(client, ws, record_ids, reference):
    return client.put(_url(ws, "/definition"), json={"record_ids": list(record_ids), "reference_record_id": reference})


def _members(body):
    return {m["record_id"]: m for m in body["members"]}


class TestRecords:
    def test_lists_eligible_and_ineligible_records_with_reason_codes(self, client, comtrade_fixtures_dir):
        ws = "ws-er-records"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _inject(client, ws, "tod-1", timing_reference="time_of_day", time_of_day_s=36000.0)
        _inject(client, ws, "el-1", timing_reference="relative_elapsed")

        resp = client.get(_url(ws, "/records"))
        assert resp.status_code == 200
        records = {r["record_id"]: r for r in resp.json()}
        assert set(records) == {a, b, "tod-1", "el-1"}
        assert records[a]["eligible"] is True and records[a]["reason_code"] is None
        assert records[a]["source_ids"] == [a]
        assert records[a]["start_time_utc"] == "2026-03-06T02:00:00Z"
        assert records[b]["start_time_utc"] == "2026-03-06T02:00:10Z"
        assert records["tod-1"]["eligible"] is False
        assert records["tod-1"]["reason_code"] == "time_of_day_not_supported"
        assert records["tod-1"]["start_time_utc"] is None
        assert records["el-1"]["reason_code"] == "no_absolute_time_reference"
        assert records["el-1"]["duration_s"] == pytest.approx(1.0)

    def test_empty_workspace(self, client):
        assert client.get(_url("ws-er-empty", "/records")).json() == []

    def test_time_groups_endpoint_is_gone(self, client):
        assert client.get(_url("ws-er-old", "/time-groups")).status_code == 404

    def test_identical_timestamp_uploads_are_two_records_but_one_waveform_time_group(self, client, comtrade_fixtures_dir):
        ws = "ws-er-identical"
        bahs, btgh = _pair(client, ws, comtrade_fixtures_dir, offset_s=0.0)
        sync_groups = f"/api/v1/workspaces/{ws}/synchronization/time-groups"
        groups = client.get(sync_groups).json()
        assert len(groups) == 1 and sorted(groups[0]["source_ids"]) == sorted([bahs, btgh])

        assert {r["record_id"] for r in client.get(_url(ws, "/records")).json()} == {bahs, btgh}
        resp = _define(client, ws, [bahs, btgh], bahs)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [m["record_id"] for m in body["members"]] == [bahs, btgh]
        assert _members(body)[btgh]["reconstruction_offset_s"] == 0.0
        assert body["relationships"][0]["kind"] == "full_overlap"
        assert client.get(sync_groups).json() == groups


class TestDefinitionLifecycle:
    def test_create_get_reference_correction_and_clear(self, client, comtrade_fixtures_dir):
        ws = "ws-er-flow"
        a, b = _pair(client, ws, comtrade_fixtures_dir)

        undefined = client.get(_url(ws, "/definition")).json()
        assert undefined["defined"] is False and undefined["members"] == []
        assert undefined["large_gap_warning_threshold_s"] == 3600.0

        resp = _define(client, ws, [a, b], a)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["defined"] is True and body["status"] == "ready"
        assert body["reference_record_id"] == a
        assert _members(body)[b]["reconstruction_offset_s"] == pytest.approx(10.0)
        assert _members(body)[b]["source_ids"] == [b]
        assert body["relationships"][0]["kind"] == "gap"
        assert body["relationships"][0]["record_a_id"] == a
        assert client.get(_url(ws, "/definition")).json() == body
        assert {r["record_id"]: r["in_reconstruction"] for r in client.get(_url(ws, "/records")).json()} == {a: True, b: True}

        resp = client.put(_url(ws, "/definition/reference"), json={"record_id": b})
        assert resp.status_code == 200
        members = _members(resp.json())
        assert members[a]["reconstruction_offset_s"] == pytest.approx(-10.0)
        assert members[b]["is_reference"] is True

        resp = client.put(_url(ws, f"/definition/records/{a}/correction"), json={"correction_s": 0.0001234})
        assert resp.status_code == 200
        members = _members(resp.json())
        assert members[a]["correction_s"] == 0.0001234
        assert members[a]["reconstruction_offset_s"] == pytest.approx(-9.9998766, abs=1e-12)

        resp = client.delete(_url(ws, f"/definition/records/{a}/correction"))
        assert resp.status_code == 200
        assert _members(resp.json())[a]["correction_s"] == 0.0

        assert client.delete(_url(ws, "/definition")).status_code == 204
        assert client.get(_url(ws, "/definition")).json()["defined"] is False
        assert client.delete(_url(ws, "/definition")).status_code == 204  # idempotent

    def test_large_gap_warning_is_returned_without_rejecting(self, client, comtrade_fixtures_dir):
        ws = "ws-er-gap"
        a, b = _pair(client, ws, comtrade_fixtures_dir, offset_s=7200.0)
        resp = _define(client, ws, [a, b], a)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        [warning] = body["warnings"]
        assert warning["code"] == "large_gap"
        assert warning["threshold_s"] == 3600.0
        assert warning["gap_s"] > 3600.0
        assert (warning["before_record_id"], warning["after_record_id"]) == (a, b)


class TestConfiguredThreshold:
    def test_default_threshold_comes_from_settings(self, client, settings):
        body = client.get(_url("ws-er-threshold-default", "/definition")).json()
        assert body["large_gap_warning_threshold_s"] == settings.event_reconstruction_large_gap_warning_s

    @pytest.mark.parametrize(("offset_s", "warns"), [(59.0, False), (61.0, True)])
    def test_configured_threshold_is_reported_and_applied(self, settings, comtrade_fixtures_dir, offset_s, warns):
        custom = dataclasses.replace(settings, event_reconstruction_large_gap_warning_s=60.0)
        with TestClient(create_app(custom)) as client:
            ws = "ws-er-threshold-custom"
            a, b = _pair(client, ws, comtrade_fixtures_dir, offset_s=offset_s)
            resp = _define(client, ws, [a, b], a)
            assert resp.status_code == 200
            body = resp.json()
            assert body["large_gap_warning_threshold_s"] == 60.0
            assert body["status"] == "ready"
            assert len(body["warnings"]) == (1 if warns else 0)


class TestErrors:
    @pytest.mark.parametrize(
        ("record_ids", "reference", "status", "code"),
        [
            ([], "x", 400, "invalid_reconstruction_definition"),
            (["A", "A"], "A", 400, "duplicate_reconstruction_member"),
            (["A", "nope"], "A", 404, "source_not_found"),
            (["A", "tod-1"], "A", 400, "record_not_eligible"),
            (["A", "el-1"], "A", 400, "record_not_eligible"),
            (["A", "B"], "el-1", 400, "reconstruction_reference_not_member"),
        ],
    )
    def test_invalid_definitions(self, client, comtrade_fixtures_dir, record_ids, reference, status, code):
        ws = "ws-er-errors"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _inject(client, ws, "tod-1", timing_reference="time_of_day", time_of_day_s=100.0)
        _inject(client, ws, "el-1", timing_reference="relative_elapsed")
        names = {"A": a, "B": b}
        resp = _define(client, ws, [names.get(r, r) for r in record_ids], names.get(reference, reference))
        _assert_error(resp, status, code)
        assert client.get(_url(ws, "/definition")).json()["defined"] is False

    def test_member_operations_without_definition_or_member(self, client, comtrade_fixtures_dir):
        ws = "ws-er-member-errors"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _assert_error(client.put(_url(ws, "/definition/reference"), json={"record_id": a}), 404, "reconstruction_not_defined")
        _assert_error(client.put(_url(ws, f"/definition/records/{a}/correction"), json={"correction_s": 1.0}), 404, "reconstruction_not_defined")
        _define(client, ws, [a], a)
        _assert_error(client.put(_url(ws, "/definition/reference"), json={"record_id": b}), 404, "reconstruction_member_not_found")
        _assert_error(client.delete(_url(ws, f"/definition/records/{b}/correction")), 404, "reconstruction_member_not_found")

    def test_non_finite_and_malformed_corrections(self, client, comtrade_fixtures_dir):
        ws = "ws-er-bad-correction"
        a, _ = _pair(client, ws, comtrade_fixtures_dir)
        _define(client, ws, [a], a)
        resp = client.put(
            _url(ws, f"/definition/records/{a}/correction"),
            content=json.dumps({"correction_s": float("nan")}), headers={"content-type": "application/json"},
        )
        _assert_error(resp, 400, "invalid_reconstruction_correction")
        resp = client.put(_url(ws, f"/definition/records/{a}/correction"), json={"correction_s": "soon"})
        assert resp.status_code == 422


class TestStaleAndLifecycle:
    def test_overlapping_upload_never_stales_or_merges_a_member(self, client, comtrade_fixtures_dir):
        ws = "ws-er-overlap-upload"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _define(client, ws, [a, b], b)
        client.put(_url(ws, f"/definition/records/{a}/correction"), json={"correction_s": 0.5})

        c = _upload(client, ws, comtrade_fixtures_dir, offset_s=0.005)  # joins A's Waveform Time Group

        body = client.get(_url(ws, "/definition")).json()
        assert body["status"] == "ready"
        member_a = _members(body)[a]
        assert member_a["status"] == "current" and member_a["source_ids"] == [a]
        assert member_a["correction_s"] == 0.5 and member_a["start_s"] is not None
        assert c not in _members(body)

    def test_record_removal_marks_member_stale_and_workspace_reset_clears(self, client, comtrade_fixtures_dir):
        ws = "ws-er-remove"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _define(client, ws, [a, b], a)
        client.put(_url(ws, f"/definition/records/{b}/correction"), json={"correction_s": 0.5})
        assert client.delete(f"/api/v1/workspaces/{ws}/sources/{b}").status_code == 204
        body = client.get(_url(ws, "/definition")).json()
        assert body["status"] == "stale"
        member_b = _members(body)[b]
        assert member_b["status"] == "stale" and member_b["stale_reason"] == "record_removed"
        assert member_b["correction_s"] == 0.5
        assert member_b["start_s"] is None and member_b["source_timings"] is None
        _assert_error(
            client.put(_url(ws, f"/definition/records/{b}/correction"), json={"correction_s": 1.0}),
            409, "reconstruction_member_stale",
        )

        assert client.delete(f"/api/v1/workspaces/{ws}").status_code == 204
        assert client.app.state.event_reconstruction_registry.get(ws) is None
        assert client.get(_url(ws, "/definition")).json()["defined"] is False

    def test_reconstruction_never_changes_time_groups_or_synchronization(self, client, comtrade_fixtures_dir):
        ws = "ws-er-isolation"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        c = _upload(client, ws, comtrade_fixtures_dir, offset_s=0.0)  # same Waveform Time Group as A
        sync_sources = f"/api/v1/workspaces/{ws}/synchronization/sources"
        sync_groups = f"/api/v1/workspaces/{ws}/synchronization/time-groups"
        sources_before, groups_before = client.get(sync_sources).json(), client.get(sync_groups).json()

        _define(client, ws, [a, b, c], a)
        client.put(_url(ws, f"/definition/records/{c}/correction"), json={"correction_s": -0.004})
        client.put(_url(ws, f"/definition/records/{b}/correction"), json={"correction_s": -9.999})
        client.put(_url(ws, "/definition/reference"), json={"record_id": b})

        assert client.get(sync_sources).json() == sources_before
        assert client.get(sync_groups).json() == groups_before
        assert client.app.state.synchronization_registry.count() == 0
