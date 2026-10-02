"""Event Reconstruction Relative / Absolute time display: the absolute
instant of reconstruction time 0 (`reconstruction_zero_time_utc`) is the
reference's recorded start plus the reference's own correction, so

    absolute(x) = reconstruction_zero_time_utc + x
                = record recorded start + correction(record) + source elapsed

for every point of every record, whichever record is the reference. The
reconstruction timing itself is unchanged."""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.event_reconstruction import reconstruction_zero_instant
from app.main import create_app

# synth_ascii.cfg records 06/03/2026 10:00:00 (naive, Asia/Kuala_Lumpur).
FIXTURE_START = datetime(2026, 3, 6, 10, 0, 0)
_TIMESTAMP_LINE = re.compile(rb"^\d{2}/\d{2}/\d{4},\d{2}:\d{2}:\d{2}\.\d{6}(\r?)$", re.MULTILINE)
OFFSETS = {"a": 0.0, "b": 10.0005, "c": 12.25}
CORRECTIONS = {"a": 0.02, "b": -0.0005, "c": 0.3}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload(client, ws, comtrade_fixtures_dir, offset_s: float) -> str:
    start = FIXTURE_START + timedelta(seconds=offset_s)
    stamps = iter([start, start + timedelta(milliseconds=5)])
    cfg = _TIMESTAMP_LINE.sub(
        lambda m: next(stamps).strftime("%d/%m/%Y,%H:%M:%S.%f").encode() + m.group(1),
        (comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes(), count=2,
    )
    files = {
        "cfg_file": ("s.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("s.dat", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{ws}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _url(ws, path=""):
    return f"/api/v1/workspaces/{ws}/event-reconstruction{path}"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _absolute(body: dict, x: float) -> datetime:
    return _utc(body["reconstruction_zero_time_utc"]) + timedelta(seconds=x)


@pytest.fixture
def three(client, comtrade_fixtures_dir):
    ws = "ws-er-absolute"
    ids = {name: _upload(client, ws, comtrade_fixtures_dir, offset) for name, offset in OFFSETS.items()}
    resp = client.put(_url(ws, "/definition"), json={"record_ids": list(ids.values()), "reference_record_id": ids["a"]})
    assert resp.status_code == 200, resp.text
    for name, correction in CORRECTIONS.items():
        resp = client.put(_url(ws, f"/definition/records/{ids[name]}/correction"), json={"correction_s": correction})
        assert resp.status_code == 200, resp.text
    return ws, ids


def test_zero_instant_is_reference_start_plus_reference_correction():
    start = datetime(2022, 7, 27, 4, 41, 48, 559912, tzinfo=timezone.utc)
    assert reconstruction_zero_instant(reference_origin_start=start, reference_correction_s=0.0) == start
    assert reconstruction_zero_instant(reference_origin_start=start, reference_correction_s=-0.000200) == start - timedelta(microseconds=200)
    assert reconstruction_zero_instant(reference_origin_start=start, reference_correction_s=0.02) == start + timedelta(milliseconds=20)


def test_every_point_keeps_its_corrected_absolute_instant_whichever_record_is_the_reference(client, three):
    ws, ids = three
    by_reference = {}
    for reference in ("a", "b", "c"):
        body = client.put(_url(ws, "/definition/reference"), json={"record_id": ids[reference]}).json()
        members = {m["record_id"]: m for m in body["members"]}
        # The zero is the reference's recorded start plus its own correction.
        ref = members[ids[reference]]
        assert _utc(body["reconstruction_zero_time_utc"]) == _utc(ref["recorded_start_time_utc"]) + timedelta(seconds=ref["correction_s"])
        instants = {}
        for name in OFFSETS:
            member = members[ids[name]]
            expected = _utc(member["recorded_start_time_utc"]) + timedelta(seconds=CORRECTIONS[name])
            # Record start and a sample 0.4 s into the record.
            for elapsed in (0.0, 0.4):
                x = member["source_timings"][0]["reconstruction_start_s"] + elapsed
                got = _absolute(body, x)
                assert abs((got - (expected + timedelta(seconds=elapsed))).total_seconds()) < 1e-6
                instants[(name, elapsed)] = got
        by_reference[reference] = instants
    # Same physical instants for every reference choice (the relative
    # numbers differ; the absolute ones do not).
    for reference in ("b", "c"):
        for key, instant in by_reference["a"].items():
            assert abs((by_reference[reference][key] - instant).total_seconds()) < 1e-6


def test_a_correction_moves_only_its_own_record_in_absolute_time(client, three):
    ws, ids = three
    before = client.get(_url(ws, "/definition")).json()
    absolute = lambda body, name: _absolute(body, {m["record_id"]: m for m in body["members"]}[ids[name]]["start_s"])  # noqa: E731
    # Non-reference record b: +20 ms -> its absolute placement +20 ms, the others unchanged.
    after = client.put(_url(ws, f"/definition/records/{ids['b']}/correction"), json={"correction_s": CORRECTIONS["b"] + 0.020}).json()
    assert abs((absolute(after, "b") - absolute(before, "b")).total_seconds() - 0.020) < 1e-6
    for name in ("a", "c"):
        assert abs((absolute(after, name) - absolute(before, name)).total_seconds()) < 1e-6
    # Reference record a: +5 ms -> the zero moves +5 ms; a's absolute
    # placement +5 ms; b and c keep theirs (their relative x rebased).
    after_ref = client.put(_url(ws, f"/definition/records/{ids['a']}/correction"), json={"correction_s": CORRECTIONS["a"] + 0.005}).json()
    assert abs((_utc(after_ref["reconstruction_zero_time_utc"]) - _utc(after["reconstruction_zero_time_utc"])).total_seconds() - 0.005) < 1e-6
    assert abs((absolute(after_ref, "a") - absolute(after, "a")).total_seconds() - 0.005) < 1e-6
    for name in ("b", "c"):
        assert abs((absolute(after_ref, name) - absolute(after, name)).total_seconds()) < 1e-6


def test_no_zero_without_placements(client, comtrade_fixtures_dir):
    ws = "ws-er-absolute-none"
    assert client.get(_url(ws, "/definition")).json()["reconstruction_zero_time_utc"] is None
    a = _upload(client, ws, comtrade_fixtures_dir, 0.0)
    body = client.put(_url(ws, "/definition"), json={"record_ids": [a], "reference_record_id": a}).json()
    assert body["reconstruction_zero_time_utc"].endswith("Z")
    # The reference's recording removed: placements (and the zero) withheld.
    client.delete(f"/api/v1/workspaces/{ws}/sources/{a}")
    body = client.get(_url(ws, "/definition")).json()
    assert body["placements_available"] is False
    assert body["reconstruction_zero_time_utc"] is None


def test_microsecond_precision_on_the_wire(client, comtrade_fixtures_dir):
    ws = "ws-er-absolute-us"
    a = _upload(client, ws, comtrade_fixtures_dir, 0.000123)
    client.put(_url(ws, "/definition"), json={"record_ids": [a], "reference_record_id": a})
    body = client.put(_url(ws, f"/definition/records/{a}/correction"), json={"correction_s": -0.0002}).json()
    # 10:00:00.000123 local (+08:00) -> 02:00:00.000123Z, minus 200 µs.
    assert body["reconstruction_zero_time_utc"] == "2026-03-06T01:59:59.999923Z"
