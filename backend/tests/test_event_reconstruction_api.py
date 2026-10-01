"""API tests for Event Reconstruction (DEC-123/DEC-124), end to end
through the real app: real COMTRADE uploads (start time edited in the
CFG to create separate Time Groups) plus injected Time-of-Day and
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
from app.domain.event_reconstruction import membership_fingerprint
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


class TestTimeGroups:
    def test_lists_eligible_and_ineligible_groups_with_reason_codes(self, client, comtrade_fixtures_dir):
        ws = "ws-er-groups"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _inject(client, ws, "tod-1", timing_reference="time_of_day", time_of_day_s=36000.0)
        _inject(client, ws, "el-1", timing_reference="relative_elapsed")

        resp = client.get(_url(ws, "/time-groups"))
        assert resp.status_code == 200
        groups = {g["group_id"]: g for g in resp.json()}
        assert set(groups) == {a, b, "tod-1", "el-1"}
        assert groups[a]["eligible"] is True and groups[a]["reason_code"] is None
        assert groups[a]["start_time_utc"] == "2026-03-06T02:00:00Z"
        assert groups[b]["start_time_utc"] == "2026-03-06T02:00:10Z"
        assert groups[a]["membership_fingerprint"] == membership_fingerprint([a])
        assert groups["tod-1"]["eligible"] is False
        assert groups["tod-1"]["reason_code"] == "time_of_day_not_supported"
        assert groups["tod-1"]["start_time_utc"] is None
        assert groups["el-1"]["reason_code"] == "no_absolute_time_reference"
        assert groups["el-1"]["duration_s"] == pytest.approx(1.0)

    def test_empty_workspace(self, client):
        assert client.get(_url("ws-er-empty", "/time-groups")).json() == []


class TestDefinitionLifecycle:
    def test_create_get_reference_correction_and_clear(self, client, comtrade_fixtures_dir):
        ws = "ws-er-flow"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        member_a, member_b = membership_fingerprint([a]), membership_fingerprint([b])

        undefined = client.get(_url(ws, "/definition")).json()
        assert undefined["defined"] is False and undefined["members"] == []
        assert undefined["large_gap_warning_threshold_s"] == 3600.0

        resp = client.put(_url(ws, "/definition"), json={"group_ids": [a, b], "reference_group_id": a})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["defined"] is True and body["status"] == "ready"
        assert body["reference_member_id"] == member_a
        members = {m["member_id"]: m for m in body["members"]}
        assert members[member_b]["reconstruction_offset_s"] == pytest.approx(10.0)
        assert members[member_b]["confirmed_group_id"] == b
        assert body["relationships"][0]["kind"] == "gap"
        assert client.get(_url(ws, "/definition")).json() == body

        resp = client.put(_url(ws, "/definition/reference"), json={"member_id": member_b})
        assert resp.status_code == 200
        members = {m["member_id"]: m for m in resp.json()["members"]}
        assert members[member_a]["reconstruction_offset_s"] == pytest.approx(-10.0)
        assert members[member_b]["is_reference"] is True

        resp = client.put(_url(ws, f"/definition/members/{member_a}/correction"), json={"correction_s": 0.0001234})
        assert resp.status_code == 200
        members = {m["member_id"]: m for m in resp.json()["members"]}
        assert members[member_a]["correction_s"] == 0.0001234
        assert members[member_a]["reconstruction_offset_s"] == pytest.approx(-9.9998766, abs=1e-12)

        resp = client.delete(_url(ws, f"/definition/members/{member_a}/correction"))
        assert resp.status_code == 200
        assert {m["member_id"]: m["correction_s"] for m in resp.json()["members"]}[member_a] == 0.0

        assert client.delete(_url(ws, "/definition")).status_code == 204
        assert client.get(_url(ws, "/definition")).json()["defined"] is False
        assert client.delete(_url(ws, "/definition")).status_code == 204  # idempotent

    def test_large_gap_warning_is_returned_without_rejecting(self, client, comtrade_fixtures_dir):
        ws = "ws-er-gap"
        a, b = _pair(client, ws, comtrade_fixtures_dir, offset_s=7200.0)
        resp = client.put(_url(ws, "/definition"), json={"group_ids": [a, b], "reference_group_id": a})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        [warning] = body["warnings"]
        assert warning["code"] == "large_gap"
        assert warning["threshold_s"] == 3600.0
        assert warning["gap_s"] > 3600.0


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
            resp = client.put(_url(ws, "/definition"), json={"group_ids": [a, b], "reference_group_id": a})
            assert resp.status_code == 200
            body = resp.json()
            assert body["large_gap_warning_threshold_s"] == 60.0
            assert body["status"] == "ready"
            assert len(body["warnings"]) == (1 if warns else 0)


class TestErrors:
    @pytest.mark.parametrize(
        ("payload", "status", "code"),
        [
            ({"group_ids": [], "reference_group_id": "x"}, 400, "invalid_reconstruction_definition"),
            ({"group_ids": ["A", "A"], "reference_group_id": "A"}, 400, "duplicate_reconstruction_member"),
            ({"group_ids": ["A", "nope"], "reference_group_id": "A"}, 404, "time_group_not_found"),
            ({"group_ids": ["A", "tod-1"], "reference_group_id": "A"}, 400, "time_group_not_eligible"),
            ({"group_ids": ["A", "el-1"], "reference_group_id": "A"}, 400, "time_group_not_eligible"),
            ({"group_ids": ["A", "B"], "reference_group_id": "el-1"}, 400, "reconstruction_reference_not_member"),
        ],
    )
    def test_invalid_definitions(self, client, comtrade_fixtures_dir, payload, status, code):
        ws = "ws-er-errors"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        _inject(client, ws, "tod-1", timing_reference="time_of_day", time_of_day_s=100.0)
        _inject(client, ws, "el-1", timing_reference="relative_elapsed")
        names = {"A": a, "B": b}
        body = {
            "group_ids": [names.get(g, g) for g in payload["group_ids"]],
            "reference_group_id": names.get(payload["reference_group_id"], payload["reference_group_id"]),
        }
        _assert_error(client.put(_url(ws, "/definition"), json=body), status, code)
        assert client.get(_url(ws, "/definition")).json()["defined"] is False

    def test_member_operations_without_definition_or_member(self, client, comtrade_fixtures_dir):
        ws = "ws-er-member-errors"
        a, _ = _pair(client, ws, comtrade_fixtures_dir)
        member_a = membership_fingerprint([a])
        _assert_error(client.put(_url(ws, "/definition/reference"), json={"member_id": member_a}), 404, "reconstruction_not_defined")
        _assert_error(client.put(_url(ws, f"/definition/members/{member_a}/correction"), json={"correction_s": 1.0}), 404, "reconstruction_not_defined")
        client.put(_url(ws, "/definition"), json={"group_ids": [a], "reference_group_id": a})
        _assert_error(client.put(_url(ws, "/definition/reference"), json={"member_id": "tgm1-x"}), 404, "reconstruction_member_not_found")
        _assert_error(client.delete(_url(ws, "/definition/members/tgm1-x/correction")), 404, "reconstruction_member_not_found")

    def test_non_finite_and_malformed_corrections(self, client, comtrade_fixtures_dir):
        ws = "ws-er-bad-correction"
        a, _ = _pair(client, ws, comtrade_fixtures_dir)
        member_a = membership_fingerprint([a])
        client.put(_url(ws, "/definition"), json={"group_ids": [a], "reference_group_id": a})
        resp = client.put(
            _url(ws, f"/definition/members/{member_a}/correction"),
            content=json.dumps({"correction_s": float("nan")}), headers={"content-type": "application/json"},
        )
        _assert_error(resp, 400, "invalid_reconstruction_correction")
        resp = client.put(_url(ws, f"/definition/members/{member_a}/correction"), json={"correction_s": "soon"})
        assert resp.status_code == 422


class TestStaleAndLifecycle:
    def test_overlapping_upload_makes_member_stale_and_blocks_changes(self, client, comtrade_fixtures_dir):
        ws = "ws-er-stale"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        member_a = membership_fingerprint([a])
        client.put(_url(ws, "/definition"), json={"group_ids": [a, b], "reference_group_id": b})
        client.put(_url(ws, f"/definition/members/{member_a}/correction"), json={"correction_s": 0.5})

        _upload(client, ws, comtrade_fixtures_dir, offset_s=0.005)  # overlaps A -> merges with A's group

        body = client.get(_url(ws, "/definition")).json()
        assert body["status"] == "stale"
        stale = {m["member_id"]: m for m in body["members"]}[member_a]
        assert stale["status"] == "stale"
        assert stale["stale_reason"] == "membership_changed"
        assert stale["correction_s"] == 0.5 and stale["start_s"] is None
        _assert_error(
            client.put(_url(ws, f"/definition/members/{member_a}/correction"), json={"correction_s": 1.0}),
            409, "reconstruction_member_stale",
        )

    def test_source_removal_marks_member_stale_and_workspace_reset_clears(self, client, comtrade_fixtures_dir):
        ws = "ws-er-remove"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        client.put(_url(ws, "/definition"), json={"group_ids": [a, b], "reference_group_id": a})
        assert client.delete(f"/api/v1/workspaces/{ws}/sources/{b}").status_code == 204
        member_b = {m["member_id"]: m for m in client.get(_url(ws, "/definition")).json()["members"]}[membership_fingerprint([b])]
        assert member_b["stale_reason"] == "sources_removed"

        assert client.delete(f"/api/v1/workspaces/{ws}").status_code == 204
        assert client.app.state.event_reconstruction_registry.get(ws) is None
        assert client.get(_url(ws, "/definition")).json()["defined"] is False

    def test_reconstruction_never_changes_time_groups_or_synchronization(self, client, comtrade_fixtures_dir):
        ws = "ws-er-isolation"
        a, b = _pair(client, ws, comtrade_fixtures_dir)
        sync_sources = f"/api/v1/workspaces/{ws}/synchronization/sources"
        sync_groups = f"/api/v1/workspaces/{ws}/synchronization/time-groups"
        sources_before, groups_before = client.get(sync_sources).json(), client.get(sync_groups).json()

        client.put(_url(ws, "/definition"), json={"group_ids": [a, b], "reference_group_id": a})
        client.put(_url(ws, f"/definition/members/{membership_fingerprint([b])}/correction"), json={"correction_s": -9.999})
        client.put(_url(ws, "/definition/reference"), json={"member_id": membership_fingerprint([b])})

        assert client.get(sync_sources).json() == sources_before
        assert client.get(sync_groups).json() == groups_before
        assert client.app.state.synchronization_registry.count() == 0
