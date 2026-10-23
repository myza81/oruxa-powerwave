"""Clock authority, microseconds, rollover, and unchanged workspace state."""
from dataclasses import replace
from datetime import datetime, timezone
import io
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.domain.source_timezone import TimeBasis
from app.domain.time_reference import interpret_clock, source_timestamp_utc
from test_ben5k_api import _make_ben5k_bytes, settings_flag_on

@pytest.fixture
def client(settings_flag_on):
    with TestClient(create_app(settings_flag_on)) as client:
        yield client

def upload(client):
    response = client.post("/api/v1/workspaces/clock/sources", files={"ben_file": ("clock.ben", io.BytesIO(_make_ben5k_bytes()), "application/octet-stream")})
    assert response.status_code == 201, response.text
    return response.json()

def url(sid):
    return f"/api/v1/workspaces/clock/sources/{sid}/time-reference"

@pytest.mark.parametrize("offset,raw,expected", [
    (0, "2026-10-16T18:03:14.535400", "2026-10-16T18:03:14.535400+00:00"),
    (480, "2026-10-16T18:03:14.535400", "2026-10-16T10:03:14.535400+00:00"),
    (-300, "2026-10-16T18:03:14.535400", "2026-10-16T23:03:14.535400+00:00"),
    (330, "2026-10-16T18:03:14.535400", "2026-10-16T12:33:14.535400+00:00"),
    (345, "2026-10-16T18:03:14.535400", "2026-10-16T12:18:14.535400+00:00"),
    (840, "2026-01-01T00:00:00.000001", "2025-12-31T10:00:00.000001+00:00"),
    (-720, "2026-12-31T23:59:59.999999", "2027-01-01T11:59:59.999999+00:00"),
    (480, "2026-03-01T01:00:00.000000", "2026-02-28T17:00:00+00:00"),
])
def test_microsecond_conversion(offset, raw, expected):
    assert interpret_clock(datetime.fromisoformat(raw), offset).isoformat() == expected

def test_api_preserves_raw_arrays_groups_offsets_and_t0(client):
    first, second = upload(client), upload(client)
    sid = first["source_id"]
    base = "/api/v1/workspaces/clock"
    registry = client.app.state.workspace_registry
    active = registry.get("clock", sid)
    original = active.record.waveform_data.copy(deep=True)
    client.app.state.synchronization_registry.set_offset("clock", sid, .123456)
    assert client.put(base + "/synchronization/t0", json={"source_id": sid, "t0_workspace_time": .25}).status_code == 200
    groups = client.get(base + "/synchronization/time-groups").json()
    alignments = client.get(base + "/synchronization/sources").json()
    assert first["time_reference_interpretation"] is None
    assert first["trigger_time_utc"] is None
    for offset in (480, 0, -210, 345, None):
        response = client.put(url(sid), json={"offset_minutes": offset})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["start_time"] == first["start_time"]
        assert result["trigger_time"] == "2026-10-16T18:03:14.535400"
        assert result["time_basis"] == "unknown"
        assert result["timing_reference"] == first["timing_reference"]
        assert result["sample_count"] == first["sample_count"]
        if offset is None:
            assert result["trigger_time_utc"] is None
            assert result["time_reference_interpretation"] is None
        else:
            assert result["time_reference_interpretation"]["provenance"] == "user_assigned"
            assert datetime.fromisoformat(result["trigger_time_utc"]) == interpret_clock(active.metadata.trigger_time, offset)
        channels = client.get(base + f"/sources/{sid}/channels").json()
        assert channels["timebase"]["trigger_time_utc"] == result["trigger_time_utc"]
        assert channels["timebase"]["time_reference_interpretation"] == result["time_reference_interpretation"]
        assert registry.get("clock", sid).record is active.record
        assert registry.get("clock", sid).record.waveform_data.equals(original)
        current_groups = client.get(base + "/synchronization/time-groups").json()
        assert sorted(g["source_ids"] for g in current_groups) == sorted(g["source_ids"] for g in groups)
        assert client.get(base + "/synchronization/sources").json() == alignments
        assert client.get(base + "/synchronization/t0", params={"source_id": sid}).json()["t0_workspace_time"] == .25
        assert client.get(base + f"/sources/{second['source_id']}").json()["trigger_time_utc"] is None
    assert client.put(url(sid).replace('/clock/', '/other/'), json={"offset_minutes": 480}).status_code == 404

@pytest.mark.parametrize("body", [{}, {"offset_minutes": True}, {"offset_minutes": "480"}, {"offset_minutes": 480.5}, {"offset_minutes": 481}, {"offset_minutes": -735}, {"offset_minutes": 855}, {"offset_minutes": 480, "timezone": "UTC"}])
def test_invalid_requests_do_not_change_state(client, body):
    source = upload(client)
    assert client.put(url(source["source_id"]), json=body).status_code == 422

@pytest.mark.parametrize("basis,raw", [(TimeBasis.VERIFIED_UTC, datetime(2026, 10, 16, tzinfo=timezone.utc)), (TimeBasis.SOURCE_TIMEZONE, datetime(2026, 10, 16))])
def test_verified_and_legacy_sources_cannot_be_overridden(client, basis, raw):
    source = upload(client)
    registry = client.app.state.workspace_registry
    active = registry.get("clock", source["source_id"])
    registry.add(replace(active, metadata=replace(active.metadata, time_basis=basis, start_time=raw)))
    before = source_timestamp_utc(registry.get("clock", source["source_id"]).metadata, "start_time")
    assert client.put(url(source["source_id"]), json={"offset_minutes": 480}).status_code == 409
    assert source_timestamp_utc(registry.get("clock", source["source_id"]).metadata, "start_time") == before

@pytest.mark.parametrize("missing", [True, False])
def test_missing_and_conflicting_clocks_rejected(client, missing):
    source = upload(client)
    registry = client.app.state.workspace_registry
    active = registry.get("clock", source["source_id"])
    registry.add(replace(active, metadata=replace(active.metadata, start_time=None if missing else datetime.now(timezone.utc), trigger_time=None)))
    assert client.put(url(source["source_id"]), json={"offset_minutes": 0}).status_code == 409


def test_gpth_ktbr_explicit_absolute_alignment(client):
    # GPTH and KTBR each have 2500 pre-trigger samples at 5000 Hz.
    gpth = upload(client)["source_id"]
    ktbr = upload(client)["source_id"]
    registry = client.app.state.workspace_registry
    for sid, start, trigger, basis, reference in [
        (gpth, datetime(2026,10,16,18,3,14,35400), datetime(2026,10,16,18,3,14,535400), TimeBasis.UNKNOWN, "relative_elapsed"),
        (ktbr, datetime(2026,10,16,10,3,14,37467,tzinfo=timezone.utc), datetime(2026,10,16,10,3,14,537467,tzinfo=timezone.utc), TimeBasis.VERIFIED_UTC, "absolute"),
    ]:
        active = registry.get("clock", sid)
        registry.add(replace(active, metadata=replace(active.metadata, start_time=start, trigger_time=trigger, time_basis=basis, timing_reference=reference)))
    base = "/api/v1/workspaces/clock"
    er = base + "/event-reconstruction"
    groups = client.get(base + "/synchronization/time-groups").json()
    client.app.state.synchronization_registry.set_offset("clock", gpth, .125)
    assert client.put(base + "/synchronization/t0", json={"source_id": gpth, "t0_workspace_time": .4}).status_code == 200
    assert client.put(er + "/definition", json={"record_ids": [ktbr, gpth], "reference_record_id": ktbr}).status_code == 400
    result = client.put(url(gpth), json={"offset_minutes": 480})
    assert result.status_code == 200
    assert result.json()["trigger_time_utc"] == "2026-10-16T10:03:14.535400Z"
    assert client.get(er + "/definition").json()["defined"] is False
    # The engineer explicitly selects both records; no group was automatically merged.
    response = client.put(er + "/definition", json={"record_ids": [ktbr, gpth], "reference_record_id": ktbr})
    assert response.status_code == 200, response.text
    members = {m["record_id"]: m for m in response.json()["members"]}
    assert members[gpth]["recorded_placement_s"] == pytest.approx(-.002067, abs=1e-12)
    assert members[gpth]["source_timings"][0]["total_reconstruction_offset_s"] == pytest.approx(-.002067, abs=1e-12)
    # Source elapsed trigger .5 s becomes reconstruction .497933 s vs KTBR .5 s.
    assert .5 + members[gpth]["reconstruction_offset_s"] == pytest.approx(.497933, abs=1e-12)
    assert members[gpth]["correction_s"] == 0
    assert client.put(er + f"/definition/records/{gpth}/correction", json={"correction_s": .01}).status_code == 200
    assert client.put(url(gpth), json={"offset_minutes": None}).status_code == 200
    reverted = client.get(er + "/definition").json()
    member = next(m for m in reverted["members"] if m["record_id"] == gpth)
    assert member["recorded_placement_s"] is None
    assert member["correction_s"] == .01
    assert client.put(url(gpth), json={"offset_minutes": 480}).status_code == 200
    restored = client.get(er + "/definition").json()
    member = next(m for m in restored["members"] if m["record_id"] == gpth)
    assert member["reconstruction_offset_s"] == pytest.approx(.007933, abs=1e-12)
    automatic = client.get(base + "/synchronization/time-groups").json()
    assert len(automatic) == 1
    assert set(automatic[0]["source_ids"]) == {gpth, ktbr}
    assert client.app.state.synchronization_registry.get_offset("clock", gpth) == .125
    assert client.get(base + "/synchronization/t0", params={"source_id": gpth}).json()["t0_workspace_time"] == .4


def test_page_session_isolation_reload_and_cleanup(client):
    source = upload(client)
    sid = source["source_id"]
    base = f"/api/v1/workspaces/clock/sources/{sid}"
    page_a, page_b = {"X-Powerwave-Session": "page-a"}, {"X-Powerwave-Session": "page-b"}
    assert client.put(base + "/time-reference", headers=page_a, json={"offset_minutes": 480}).status_code == 200
    interpreted = client.get(base, headers=page_a).json()
    assert interpreted["trigger_time_utc"] == "2026-10-16T10:03:14.535400Z"
    assert interpreted["effective_timing_reference"] == "absolute"
    assert interpreted["time_reference_revision"] == 1
    for headers in [page_b, {"X-Powerwave-Session": "reloaded-page"}, {}]:
        original = client.get(base, headers=headers).json()
        assert original["trigger_time_utc"] is None
        assert original["time_reference_interpretation"] is None
        assert original["effective_timing_reference"] == "relative_elapsed"
    # Even the registry's original source and record retain their original timing.
    stored = client.app.state.workspace_registry._sources[("clock", sid)]
    assert stored.metadata.time_reference_interpretation is None
    assert stored.record.timing_info.time_basis == TimeBasis.UNKNOWN
    assert client.delete(base, headers=page_a).status_code == 204
    registry = client.app.state.workspace_registry
    assert not registry._time_references and not registry._time_revisions


def test_every_epoch_consumer_uses_effective_time(client):
    from app.services import analysis_input_resolution_service, overcurrent_analysis_service, phasor_analysis_service, calculated_channel_service
    source = upload(client)
    sid = source["source_id"]
    registry = client.app.state.workspace_registry
    consumers = [m._source_start_epoch for m in [analysis_input_resolution_service, overcurrent_analysis_service, phasor_analysis_service, calculated_channel_service]]
    for offset in [None, 480, 0, -210, 345, None]:
        assert client.put(url(sid), json={"offset_minutes": offset}).status_code == 200
        active = registry.get("clock", sid)
        values = [f(active) for f in consumers]
        expected = source_timestamp_utc(active.metadata, "start_time")
        epoch = None if expected is None else expected.timestamp()
        assert values == [epoch] * len(consumers)
        # Exercise the real input readers used by readiness, Overcurrent,
        # Phasor and its Distance/Impedance/Sequence consumers, and calculations.
        from app.domain.calculated_channel import ChannelRef
        ref = ChannelRef(kind="source", source_id=sid, channel_name=active.metadata.analog_channels[0].name)
        calc_registry = client.app.state.calculated_channel_registry
        common = {"workspace_id": "clock", "source_registry": registry, "calculated_channel_registry": calc_registry}
        assert analysis_input_resolution_service._timebase_identity(ref, **common)[2] == epoch
        assert overcurrent_analysis_service._fetch_current_candidate(ref, **common).start_epoch == epoch
        assert phasor_analysis_service._fetch_role_candidate("Va", ref, **common).start_epoch == epoch
        assert calculated_channel_service._resolve_input(ref, workspace_id="clock", source_registry=registry, calc_registry=calc_registry).start_epoch == epoch
        table = client.get(f"/api/v1/workspaces/clock/sources/{sid}/table").json()
        assert table["columns"][0]["label"] == ("Time (s)" if offset is None else "Time")


def inject_pair(client):
    gpth, ktbr = upload(client)["source_id"], upload(client)["source_id"]
    registry = client.app.state.workspace_registry
    for sid, start, basis, reference in [
        (gpth, datetime(2026,10,16,18,3,14,35400), TimeBasis.UNKNOWN, "relative_elapsed"),
        (ktbr, datetime(2026,10,16,10,3,14,37467,tzinfo=timezone.utc), TimeBasis.VERIFIED_UTC, "absolute"),
    ]:
        active = registry.get("clock", sid)
        registry.add(replace(active, metadata=replace(active.metadata, start_time=start, time_basis=basis, timing_reference=reference)))
    return gpth, ktbr


def test_automatic_groups_rebase_t0_and_apply_manual_once(client):
    gpth, ktbr = inject_pair(client)
    base = "/api/v1/workspaces/clock/synchronization"
    assert client.put(base + "/t0", json={"source_id": ktbr, "t0_workspace_time": .4}).status_code == 200
    sync = client.app.state.synchronization_registry
    sync.set_offset("clock", gpth, .01)
    assert client.put(url(gpth), json={"offset_minutes": 480}).status_code == 200
    groups = client.get(base + "/time-groups").json()
    assert len(groups) == 1 and groups[0]["origin_source_id"] == gpth
    rows = {r["source_id"]: r for r in client.get(base + "/sources").json()}
    assert rows[ktbr]["timestamp_placement_offset_s"] == pytest.approx(.002067)
    assert rows[gpth]["manual_alignment_offset_s"] == .01
    assert rows[gpth]["alignment_offset_s"] == .01
    assert client.get(base + "/t0", params={"source_id": ktbr}).json()["t0_workspace_time"] == pytest.approx(.402067)
    assert client.put(url(gpth), json={"offset_minutes": None}).status_code == 200
    assert len(client.get(base + "/time-groups").json()) == 2
    assert client.get(base + "/t0", params={"source_id": ktbr}).json()["t0_workspace_time"] == pytest.approx(.4)
    assert sync.get_offset("clock", gpth) == .01


def test_conflicting_origins_reject_atomically(client):
    gpth, ktbr = inject_pair(client)
    base = "/api/v1/workspaces/clock/synchronization"
    for sid in [gpth, ktbr]:
        assert client.put(base + "/t0", json={"source_id": sid, "t0_workspace_time": .4}).status_code == 200
    response = client.put(url(gpth), json={"offset_minutes": 480})
    assert response.status_code == 409 and "conflicting t0" in response.text
    source = client.get(f"/api/v1/workspaces/clock/sources/{gpth}").json()
    assert source["time_reference_interpretation"] is None and source["time_reference_revision"] == 0
    assert len(client.get(base + "/time-groups").json()) == 2
    for sid in [gpth, ktbr]:
        assert client.get(base + "/t0", params={"source_id": sid}).json()["t0_workspace_time"] == .4


def test_ephemeral_responses_and_page_release(client):
    source = upload(client)
    sid = source["source_id"]
    headers = {"X-Powerwave-Session": "active-page"}
    base = "/api/v1/workspaces/clock/sources"
    assert client.put(base + f"/{sid}/time-reference", headers=headers, json={"offset_minutes": 480}).status_code == 200
    response = client.get(base + f"/{sid}", headers=headers)
    assert response.headers["cache-control"] == "no-store"
    assert "X-Powerwave-Session" in response.headers["vary"]
    assert client.delete(base + "/time-reference/session", headers=headers).status_code == 204
    result = client.get(base + f"/{sid}", headers=headers).json()
    assert result["trigger_time_utc"] is None
    assert result["time_reference_interpretation"] is None
    assert client.app.state.workspace_registry.count() == 1
