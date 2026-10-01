"""DEC-122: the API carries each recording's canonical UTC instant.

`start_time`/`trigger_time` stay exactly as stored; `start_time_utc`/
`trigger_time_utc` resolve the source timezone (DEC-121) so the display
layer converts every source to one display timezone.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

URL = "/api/v1/workspaces/ws-tz/sources"
BEN_FIXTURES = Path(__file__).parent / "fixtures" / "ben"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _comtrade(client, cfg: bytes, dat: bytes):
    files = {"cfg_file": ("e.cfg", io.BytesIO(cfg), "x"), "dat_file": ("e.dat", io.BytesIO(dat), "x")}
    resp = client.post(URL, files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _ben(client, data: bytes):
    resp = client.post(URL, files={"ben_file": ("r.ben", io.BytesIO(data), "x")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_naive_comtrade_keeps_stored_digits_and_gains_a_canonical_utc_instant(client, comtrade_fixtures_dir):
    body = _comtrade(
        client,
        (comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes(),
        (comtrade_fixtures_dir / "synth_ascii.dat").read_bytes(),
    )
    assert body["start_time"] == "2026-03-06T10:00:00"  # stored, unchanged
    assert body["start_time_utc"] == "2026-03-06T02:00:00Z"  # Asia/Kuala_Lumpur -> UTC
    assert body["trigger_time"] == "2026-03-06T10:00:00.005000"
    assert body["trigger_time_utc"] == "2026-03-06T02:00:00.005000Z"
    timebase = client.get(f"{URL}/{body['source_id']}/channels").json()["timebase"]
    assert (timebase["start_time"], timebase["start_time_utc"]) == (body["start_time"], body["start_time_utc"])
    assert timebase["trigger_time_utc"] == body["trigger_time_utc"]


def test_ben_canonical_instant_is_its_stored_utc(client):
    body = _ben(client, (BEN_FIXTURES / "synthetic_fast.ben").read_bytes())
    assert body["start_time"] == body["start_time_utc"] == "2024-03-05T06:07:08.023456Z"
    assert body["trigger_time_utc"] == "2024-03-05T06:07:08.123456Z"


def test_declared_offset_comtrade_resolves_to_utc(client, comtrade_fixtures_dir):
    cfg = (comtrade_fixtures_dir / "synth_ascii.cfg").read_text().replace(",1999", ",2013", 1) + "-5,-5\n"
    body = _comtrade(client, cfg.encode(), (comtrade_fixtures_dir / "synth_ascii.dat").read_bytes())
    assert body["start_time"] == "2026-03-06T10:00:00-05:00"
    assert body["start_time_utc"] == "2026-03-06T15:00:00Z"


def test_ben_and_its_ben32_export_share_one_canonical_instant(client):
    ben = _ben(client, (BEN_FIXTURES / "synthetic_fast.ben").read_bytes())
    export = _comtrade(
        client,
        (BEN_FIXTURES / "synthetic_fast_export.cfg").read_bytes(),
        (BEN_FIXTURES / "synthetic_fast_export.dat").read_bytes(),
    )
    assert export["start_time"] == "2024-03-05T14:07:08.023456"  # BEN32's local digits
    assert export["start_time_utc"] == ben["start_time_utc"]
    assert export["trigger_time_utc"] == ben["trigger_time_utc"]
    placements = client.get("/api/v1/workspaces/ws-tz/synchronization/sources").json()
    assert [p["timestamp_placement_offset_s"] for p in placements] == [0.0, 0.0]


def test_no_stored_timestamp_means_no_canonical_instant():
    # e.g. an elapsed-only CSV/Excel source: nothing is fabricated.
    from app.schemas.source import _canonical

    assert _canonical(None) is None
