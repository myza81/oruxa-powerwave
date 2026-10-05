"""Event Reconstruction annotations (DEC-136/DEC-137): the same four tools as
Waveform -- Text Note, Callout, Maximum Peak, Minimum Peak -- with
page-specific state owned by the reconstruction (never Waveform's).

* Text Note: reconstruction-level -- `reconstruction_time_s` (current
  frame) + `y_fraction` + `axis_key`; a reference switch / reference
  correction rebases it onto the same physical instant; a non-reference
  correction or membership change leaves it fixed.
* Callout / Peak: channel-attached -- record + source + channel; a
  Callout's sample is stored in SOURCE time, so it follows its record's
  corrections and no frame change can move it.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.event_reconstruction import (
    EventReconstructionDefinition,
    ReconstructionAnnotation,
    ReconstructionChannelRef,
    ReconstructionMember,
    ReconstructionSampleAnchor,
    annotation_problem,
    reconstruction_frame_shift_s,
)
from app.main import create_app

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


@pytest.fixture
def three(client, comtrade_fixtures_dir):
    ids = {name: _upload(client, comtrade_fixtures_dir, offset) for name, offset in {"a": 0.0, "b": 10.0005, "c": 12.25}.items()}
    resp = client.put(_url("/definition"), json={"record_ids": list(ids.values()), "reference_record_id": ids["a"]})
    assert resp.status_code == 200, resp.text
    return ids


def _post(client, body):
    resp = client.post(_url("/definition/annotations"), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _note(r=20.0, text="Fault inception", y=0.25, axis_key="axis:Voltage|V"):
    return {"type": "text_note", "reconstruction_time_s": r, "y_fraction": y, "axis_key": axis_key, "text": text}


def _callout(record, text="Inception sample", index=120, elapsed=0.12, value=97.5):
    return {"type": "callout", "channel": {"record_id": record, "source_id": record, "channel_name": "VA"},
            "anchor": {"sample_index": index, "source_elapsed_s": elapsed, "value": value, "unit": "V"}, "text": text}


def _peak(record, kind="peak_max"):
    return {"type": kind, "channel": {"record_id": record, "source_id": record, "channel_name": "IA"}}


def _by_type(body, kind):
    return [a for a in body["annotations"] if a["type"] == kind]


# ---------------------------------------------------------------- domain


def test_frame_shift_matches_the_viewport_and_cursor_rule():
    at = datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc)
    origins = {"a": at, "b": at + timedelta(seconds=10.0005)}
    a, b = ReconstructionMember("a", ("a",), 0.02), ReconstructionMember("b", ("b",), -0.0005)
    before = EventReconstructionDefinition(members=(a, b), reference_record_id="a")
    assert reconstruction_frame_shift_s(before=before, after=before.with_reference("b"), origin_starts=origins) == pytest.approx(10.0005 - 0.0005 - 0.02, abs=1e-12)
    assert reconstruction_frame_shift_s(before=before, after=before.with_correction("a", 0.025), origin_starts=origins) == pytest.approx(0.005, abs=1e-15)
    assert reconstruction_frame_shift_s(before=before, after=before.with_correction("b", 0.5), origin_starts=origins) == 0.0
    assert reconstruction_frame_shift_s(before=before, after=before.with_reference("b"), origin_starts={"b": origins["b"]}) is None


def test_only_reconstruction_level_annotations_are_rebased():
    channel = ReconstructionChannelRef("a", "a", "VA")
    note = ReconstructionAnnotation("n", "text_note", 1, reconstruction_time_s=20.0, y_fraction=0.5)
    callout = ReconstructionAnnotation("c", "callout", 2, channel=channel, anchor=ReconstructionSampleAnchor(3, 0.003, 1.0, "V"))
    peak = ReconstructionAnnotation("p", "peak_max", 3, channel=channel)
    definition = EventReconstructionDefinition(members=(ReconstructionMember("a", ("a",)),), reference_record_id="a").with_annotations([note, callout, peak])
    shifted = definition.with_frame_shift(10.0)
    assert [a.reconstruction_time_s for a in shifted.annotations] == [10.0, None, None]
    assert shifted.annotations[1] == callout and shifted.annotations[2] == peak


@pytest.mark.parametrize(("annotation", "problem"), [
    (ReconstructionAnnotation("x", "arrow", 1), "Unknown annotation type"),
    (ReconstructionAnnotation("x", "text_note", 1, reconstruction_time_s=1.0, y_fraction=1.5), "y_fraction"),
    (ReconstructionAnnotation("x", "text_note", 1, y_fraction=0.5), "reconstruction_time_s"),
    (ReconstructionAnnotation("x", "callout", 1, channel=ReconstructionChannelRef("a", "a", "VA")), "resolved sample"),
    (ReconstructionAnnotation("x", "peak_min", 1, channel=ReconstructionChannelRef("a", "a", "VA"), text="no"), "no text"),
    (ReconstructionAnnotation("x", "callout", 1, reconstruction_time_s=1.0, channel=ReconstructionChannelRef("a", "a", "VA"),
                              anchor=ReconstructionSampleAnchor(0, 0.0, 1.0, None)), "no reconstruction-level position"),
])
def test_each_type_has_exactly_its_own_fields(annotation, problem):
    assert problem in annotation_problem(annotation)


# ---------------------------------------------------------------- CRUD


def test_all_four_types_round_trip_with_their_own_fields(client, three):
    ids = three
    _post(client, _note())
    _post(client, _callout(ids["b"]))
    _post(client, _peak(ids["c"], "peak_max"))
    body = _post(client, _peak(ids["c"], "peak_min"))
    assert [a["type"] for a in body["annotations"]] == ["text_note", "callout", "peak_max", "peak_min"]  # creation order
    assert [a["sequence"] for a in body["annotations"]] == [1, 2, 3, 4]
    note, callout, peak_max, peak_min = body["annotations"]
    assert (note["reconstruction_time_s"], note["y_fraction"], note["axis_key"], note["channel"], note["anchor"]) == (20.0, 0.25, "axis:Voltage|V", None, None)
    assert callout["channel"] == {"record_id": ids["b"], "source_id": ids["b"], "channel_name": "VA"}
    assert callout["anchor"] == {"sample_index": 120, "source_elapsed_s": 0.12, "value": 97.5, "unit": "V"}
    assert callout["box_offset"] == {"x": 80.0, "y": -60.0}  # Waveform's default
    assert (callout["reconstruction_time_s"], callout["y_fraction"]) == (None, None)
    assert peak_max["channel"]["channel_name"] == "IA" and peak_max["anchor"] is None and peak_max["text"] == ""
    assert peak_min["type"] == "peak_min"
    # Text may be empty (Waveform's placeholder state).
    assert _post(client, _note(text=""))["annotations"][-1]["text"] == ""


def test_updates_touch_only_what_a_type_allows(client, three):
    ids = three
    body = _post(client, _note())
    note_id = body["annotations"][0]["annotation_id"]
    body = _post(client, _callout(ids["b"]))
    callout_id = body["annotations"][1]["annotation_id"]
    body = _post(client, _peak(ids["c"]))
    peak_id = body["annotations"][2]["annotation_id"]
    put = lambda aid, payload: client.put(_url(f"/definition/annotations/{aid}"), json=payload)  # noqa: E731
    # Text Note: text and position.
    note = put(note_id, {"text": "Breaker opened", "reconstruction_time_s": 21.5, "y_fraction": 0.6}).json()["annotations"][0]
    assert (note["text"], note["reconstruction_time_s"], note["y_fraction"], note["axis_key"]) == ("Breaker opened", 21.5, 0.6, "axis:Voltage|V")
    # Callout: text, anchor (same channel), box offset.
    callout = put(callout_id, {"text": "Moved", "anchor": {"sample_index": 130, "source_elapsed_s": 0.13, "value": 99.0, "unit": "V"},
                               "box_offset": {"x": 120, "y": -20}}).json()["annotations"][1]
    assert (callout["text"], callout["anchor"]["sample_index"], callout["box_offset"]) == ("Moved", 130, {"x": 120.0, "y": -20.0})
    # Peak: box offset only.
    assert put(peak_id, {"box_offset": {"x": 10, "y": 10}}).json()["annotations"][2]["box_offset"] == {"x": 10.0, "y": 10.0}
    for aid, payload in [(peak_id, {"text": "x"}), (note_id, {"anchor": {"sample_index": 1, "source_elapsed_s": 0.0, "value": 1.0}}),
                         (callout_id, {"reconstruction_time_s": 1.0}), (note_id, {"y_fraction": 2.0})]:
        resp = put(aid, payload)
        assert resp.status_code == 400 and resp.json()["detail"]["code"] == "invalid_reconstruction_annotation", (aid, payload)
    # The channel can never be changed (not part of an update).
    assert put(callout_id, {"channel": {"record_id": ids["a"], "source_id": ids["a"], "channel_name": "VA"}}).status_code == 422
    resp = client.delete(_url(f"/definition/annotations/{peak_id}"))
    assert [a["type"] for a in resp.json()["annotations"]] == ["text_note", "callout"]
    assert client.delete(_url(f"/definition/annotations/{peak_id}")).status_code == 404


def test_channel_annotations_need_a_member_record(client, three, comtrade_fixtures_dir):
    outsider = _upload(client, comtrade_fixtures_dir, 30.0)
    resp = client.post(_url("/definition/annotations"), json=_callout(outsider))
    assert resp.status_code == 400 and "not in the reconstruction" in resp.json()["detail"]["message"]
    assert client.post(_url("/definition/annotations"), json={"type": "arrow"}).status_code == 422


def test_annotations_need_a_reconstruction(client):
    resp = client.post(_url("/definition/annotations", ws="ws-er-none"), json=_note())
    assert resp.status_code == 404 and resp.json()["detail"]["code"] == "reconstruction_not_defined"


# ---------------------------------------------------------------- frame


def test_reconstruction_level_vs_channel_attached_under_frame_changes(client, three):
    ids = three
    _post(client, _note(r=20.0))
    _post(client, _callout(ids["c"]))
    _post(client, _peak(ids["c"]))
    original = client.get(_url("/definition")).json()["annotations"]

    def note_r(body):
        return _by_type(body, "text_note")[0]["reconstruction_time_s"]

    def channel_attached(body):
        return [a for a in body["annotations"] if a["type"] != "text_note"]

    # Reference switch to b: the Text Note rebases onto the same instant;
    # the channel-attached ones are untouched (stored in source time).
    body = client.put(_url("/definition/reference"), json={"record_id": ids["b"]}).json()
    assert note_r(body) == pytest.approx(20.0 - 10.0005, abs=1e-9)
    assert channel_attached(body) == [a for a in original if a["type"] != "text_note"]
    # Reference correction +5 ms: the note moves with the frame.
    body = client.put(_url(f"/definition/records/{ids['b']}/correction"), json={"correction_s": 0.005}).json()
    assert note_r(body) == pytest.approx(20.0 - 10.0005 - 0.005, abs=1e-9)
    # Non-reference correction on c (the Callout's record): the note stays;
    # the Callout's stored sample is unchanged -- it follows record c
    # because its reconstruction position is source time + c's offset.
    before = note_r(body)
    c_offset_before = next(m for m in body["members"] if m["record_id"] == ids["c"])["reconstruction_offset_s"]
    body = client.put(_url(f"/definition/records/{ids['c']}/correction"), json={"correction_s": 0.015}).json()
    assert note_r(body) == before
    assert channel_attached(body) == [a for a in original if a["type"] != "text_note"]
    c_offset_after = next(m for m in body["members"] if m["record_id"] == ids["c"])["reconstruction_offset_s"]
    assert c_offset_after - c_offset_before == pytest.approx(0.015, abs=1e-12)


def test_membership_changes_keep_every_annotation(client, three):
    ids = three
    _post(client, _note())
    _post(client, _callout(ids["c"]))
    body = client.put(_url("/definition"), json={"record_ids": [ids["a"], ids["b"]], "reference_record_id": ids["a"]}).json()
    # The Callout of the removed record stays (shown as unavailable by the page).
    assert [a["type"] for a in body["annotations"]] == ["text_note", "callout"]
    assert _by_type(body, "text_note")[0]["reconstruction_time_s"] == 20.0


def test_clear_removes_the_annotations_with_the_reconstruction(client, three):
    ids = three
    _post(client, _note())
    _post(client, _peak(ids["a"]))
    assert client.delete(_url("/definition")).status_code == 204
    assert client.get(_url("/definition")).json()["annotations"] == []
    body = client.put(_url("/definition"), json={"record_ids": [ids["a"]], "reference_record_id": ids["a"]}).json()
    assert body["annotations"] == []


def test_a_stale_reference_keeps_the_note_without_inventing_a_shift(client, three):
    ids = three
    _post(client, _note())
    client.delete(f"/api/v1/workspaces/{WS}/sources/{ids['a']}")
    body = client.put(_url("/definition/reference"), json={"record_id": ids["b"]}).json()
    assert _by_type(body, "text_note")[0]["reconstruction_time_s"] == 20.0
