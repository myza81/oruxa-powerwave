"""Event Reconstruction annotations (DEC-136): reconstruction-level event
markers owned by the reconstruction (never Waveform annotations, never a
record), stored in reconstruction seconds of the current frame. A
reference switch or reference correction rebases them onto the same
physical instant; a non-reference correction or a membership change
leaves them fixed. Cleared with the reconstruction."""

from __future__ import annotations

import io
import math
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.event_reconstruction import (
    EventReconstructionDefinition,
    ReconstructionAnnotation,
    ReconstructionMember,
    reconstruction_frame_shift_s,
)
from app.main import create_app
from app.services.errors import InvalidReconstructionAnnotationError
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.event_reconstruction_service import add_reconstruction_annotation

FIXTURE_START = datetime(2026, 3, 6, 10, 0, 0)
_TIMESTAMP_LINE = re.compile(rb"^\d{2}/\d{2}/\d{4},\d{2}:\d{2}:\d{2}\.\d{6}(\r?)$", re.MULTILINE)
WS = "ws-er-annotations"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload(client, comtrade_fixtures_dir, offset_s: float, ws: str = WS) -> str:
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


def _url(path="", ws: str = WS):
    return f"/api/v1/workspaces/{ws}/event-reconstruction{path}"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _absolute(body, r: float) -> datetime:
    return _utc(body["reconstruction_zero_time_utc"]) + timedelta(seconds=r)


@pytest.fixture
def three(client, comtrade_fixtures_dir):
    ids = {name: _upload(client, comtrade_fixtures_dir, offset) for name, offset in {"a": 0.0, "b": 10.0005, "c": 12.25}.items()}
    resp = client.put(_url("/definition"), json={"record_ids": list(ids.values()), "reference_record_id": ids["a"]})
    assert resp.status_code == 200, resp.text
    return ids


def _create(client, r: float, text: str):
    resp = client.post(_url("/definition/annotations"), json={"reconstruction_time_s": r, "text": text})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _annotation(body, text: str) -> dict:
    return next(a for a in body["annotations"] if a["text"] == text)


# ---------------------------------------------------------------- domain


def test_frame_shift_matches_the_viewport_and_cursor_rule():
    at = datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc)
    origins = {"a": at, "b": at + timedelta(seconds=10.0005)}
    a, b = ReconstructionMember("a", ("a",), 0.02), ReconstructionMember("b", ("b",), -0.0005)
    before = EventReconstructionDefinition(members=(a, b), reference_record_id="a")
    # Reference switch: the new reference's old offset (placement + its correction - old reference correction).
    assert reconstruction_frame_shift_s(before=before, after=before.with_reference("b"), origin_starts=origins) == pytest.approx(10.0005 - 0.0005 - 0.02, abs=1e-12)
    # Reference correction: its change. Non-reference correction: 0.
    assert reconstruction_frame_shift_s(before=before, after=before.with_correction("a", 0.025), origin_starts=origins) == pytest.approx(0.005, abs=1e-15)
    assert reconstruction_frame_shift_s(before=before, after=before.with_correction("b", 0.5), origin_starts=origins) == 0.0
    # No common anchor (stale reference): no shift is invented.
    assert reconstruction_frame_shift_s(before=before, after=before.with_reference("b"), origin_starts={"b": origins["b"]}) is None
    shifted = before.with_annotations([ReconstructionAnnotation("x", 20.0, "Fault")]).with_frame_shift(10.0)
    assert shifted.annotations[0].reconstruction_time_s == 10.0


# ---------------------------------------------------------------- CRUD


def test_create_edit_move_delete(client, three):
    body = _create(client, 20.0, "  Fault inception  ")
    fault = _annotation(body, "Fault inception")  # label trimmed
    assert fault["reconstruction_time_s"] == 20.0
    _create(client, 18.5, "Protection operated")
    body = client.get(_url("/definition")).json()
    assert [a["text"] for a in body["annotations"]] == ["Protection operated", "Fault inception"]  # by time
    # Relabel only; then move only.
    body = client.put(_url(f"/definition/annotations/{fault['annotation_id']}"), json={"text": "Breaker opened"}).json()
    assert _annotation(body, "Breaker opened")["reconstruction_time_s"] == 20.0
    body = client.put(_url(f"/definition/annotations/{fault['annotation_id']}"), json={"reconstruction_time_s": 20.123456789}).json()
    assert _annotation(body, "Breaker opened")["reconstruction_time_s"] == 20.123456789  # full float precision
    body = client.delete(_url(f"/definition/annotations/{fault['annotation_id']}")).json()
    assert [a["text"] for a in body["annotations"]] == ["Protection operated"]
    resp = client.delete(_url(f"/definition/annotations/{fault['annotation_id']}"))
    assert resp.status_code == 404 and resp.json()["detail"]["code"] == "reconstruction_annotation_not_found"


@pytest.mark.parametrize("payload", [
    {"reconstruction_time_s": 1.0, "text": "   "},
    {"reconstruction_time_s": 1.0, "text": "x" * 201},
])
def test_invalid_annotations_are_rejected(client, three, payload):
    resp = client.post(_url("/definition/annotations"), json=payload)
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "invalid_reconstruction_annotation"
    assert client.get(_url("/definition")).json()["annotations"] == []


def test_non_finite_time_is_rejected():
    registry = EventReconstructionRegistry()
    registry.put("w", EventReconstructionDefinition(members=(ReconstructionMember("a", ("a",)),), reference_record_id="a"))
    with pytest.raises(InvalidReconstructionAnnotationError):
        add_reconstruction_annotation(workspace_id="w", reconstruction_time_s=math.inf, text="x", registry=registry,
                                      source_registry=None, large_gap_threshold_s=3600.0)


def test_annotations_need_a_reconstruction(client):
    resp = client.post(_url("/definition/annotations", ws="ws-er-none"), json={"reconstruction_time_s": 0.0, "text": "x"})
    assert resp.status_code == 404 and resp.json()["detail"]["code"] == "reconstruction_not_defined"
    assert client.get(_url("/definition", ws="ws-er-none")).json()["annotations"] == []


# ---------------------------------------------------------------- frame


def test_reference_changes_rebase_onto_the_same_physical_instant(client, three):
    ids = three
    body = _create(client, 20.0, "Fault inception")
    instant = _absolute(body, _annotation(body, "Fault inception")["reconstruction_time_s"])

    def check(body, expected_r):
        r = _annotation(body, "Fault inception")["reconstruction_time_s"]
        assert r == pytest.approx(expected_r, abs=1e-9)
        assert abs((_absolute(body, r) - instant).total_seconds()) < 1e-6  # same physical instant

    # Reference switch to b (10.0005 s later): the marker moves to 20 - 10.0005.
    body = client.put(_url("/definition/reference"), json={"record_id": ids["b"]}).json()
    check(body, 20.0 - 10.0005)
    # Reference correction +5 ms: the frame moves by 5 ms, the marker with it.
    body = client.put(_url(f"/definition/records/{ids['b']}/correction"), json={"correction_s": 0.005}).json()
    check(body, 20.0 - 10.0005 - 0.005)
    # Non-reference correction: the marker stays; only that record moves.
    before = _annotation(body, "Fault inception")["reconstruction_time_s"]
    body = client.put(_url(f"/definition/records/{ids['c']}/correction"), json={"correction_s": 0.015}).json()
    assert _annotation(body, "Fault inception")["reconstruction_time_s"] == before
    # Reference correction reset: back by 5 ms.
    body = client.delete(_url(f"/definition/records/{ids['b']}/correction")).json()
    check(body, 20.0 - 10.0005)
    # Back to a: the original number again.
    body = client.put(_url("/definition/reference"), json={"record_id": ids["a"]}).json()
    check(body, 20.0)


def test_membership_changes_keep_the_storyline(client, three):
    ids = three
    _create(client, 20.0, "Fault inception")
    # Remove record c (not the reference): unchanged.
    body = client.put(_url("/definition"), json={"record_ids": [ids["a"], ids["b"]], "reference_record_id": ids["a"]}).json()
    assert _annotation(body, "Fault inception")["reconstruction_time_s"] == 20.0
    # Replace with b as the reference: rebased like a reference switch.
    body = client.put(_url("/definition"), json={"record_ids": [ids["a"], ids["b"]], "reference_record_id": ids["b"]}).json()
    assert _annotation(body, "Fault inception")["reconstruction_time_s"] == pytest.approx(20.0 - 10.0005, abs=1e-9)


def test_clear_removes_the_annotations_with_the_reconstruction(client, three):
    ids = three
    _create(client, 20.0, "Fault inception")
    assert client.delete(_url("/definition")).status_code == 204
    assert client.get(_url("/definition")).json()["annotations"] == []
    body = client.put(_url("/definition"), json={"record_ids": [ids["a"]], "reference_record_id": ids["a"]}).json()
    assert body["annotations"] == []  # a new reconstruction starts empty


def test_a_stale_reference_keeps_the_markers_without_inventing_a_shift(client, three):
    ids = three
    _create(client, 20.0, "Fault inception")
    client.delete(f"/api/v1/workspaces/{WS}/sources/{ids['a']}")  # the reference's recording
    body = client.get(_url("/definition")).json()
    assert body["placements_available"] is False
    assert _annotation(body, "Fault inception")["reconstruction_time_s"] == 20.0
    # A new reference without a common anchor: the marker keeps its number.
    body = client.put(_url("/definition/reference"), json={"record_id": ids["b"]}).json()
    assert _annotation(body, "Fault inception")["reconstruction_time_s"] == 20.0
