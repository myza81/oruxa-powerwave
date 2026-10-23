"""Session-specific validity of retained calculated results (Slice A)."""
import pytest
from test_ben5k_api import settings_flag_on
from test_time_reference_interpretation import client, upload, url

PAGE_A = {"X-Powerwave-Session": "slice-a"}
PAGE_B = {"X-Powerwave-Session": "slice-b"}
BASE = "/api/v1/workspaces/clock"


def pair(client):
    ids = [upload(client)["source_id"] for _ in range(2)]
    for sid in ids:
        assert client.put(url(sid), headers=PAGE_A, json={"offset_minutes": 480}).status_code == 200
    name = client.app.state.workspace_registry.get("clock", ids[0]).metadata.analog_channels[0].name
    refs = [{"kind": "source", "source_id": sid, "channel_name": name} for sid in ids]
    return ids, refs


def create(client, name, inputs, operation="addition", headers=PAGE_A):
    response = client.post(BASE + "/calculated-channels", headers=headers, json={"name": name, "operation": operation, "inputs": inputs})
    assert response.status_code == 201, response.text
    return response.json()


def waveform(client, cid, headers=PAGE_A):
    return client.get(BASE + f"/calculated-channels/{cid}/waveform", headers=headers)


def test_reset_rejects_retained_result_and_restores_definition(client):
    ids, refs = pair(client)
    channel = create(client, "sum", refs)
    original = waveform(client, channel["id"]).json()["values"]
    assert client.put(url(ids[1]), headers=PAGE_A, json={"offset_minutes": None}).status_code == 200
    response = waveform(client, channel["id"])
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "incompatible_time_base"
    definitions = client.get(BASE + "/calculated-channels", headers=PAGE_A).json()
    assert definitions[0]["id"] == channel["id"]
    assert definitions[0]["timing_status"] == "incompatible"
    assert client.put(url(ids[1]), headers=PAGE_A, json={"offset_minutes": 480}).status_code == 200
    assert waveform(client, channel["id"]).json()["values"] == original


def test_other_session_cannot_read_interpreted_cross_source_result(client):
    _, refs = pair(client)
    channel = create(client, "sum", refs)
    response = waveform(client, channel["id"], PAGE_B)
    assert response.status_code == 400, response.text
    assert waveform(client, channel["id"]).status_code == 200


@pytest.mark.parametrize("endpoint", ["waveform", "per-unit-resolution", "cursor-values", "peak-values", "annotation-anchor"])
def test_every_result_endpoint_checks_requesting_session(client, endpoint):
    ids, refs = pair(client)
    channel = create(client, "sum", refs)
    cid = channel["id"]
    client.put(url(ids[1]), headers=PAGE_A, json={"offset_minutes": None})
    base = BASE + "/calculated-channels"
    if endpoint in ("waveform", "per-unit-resolution"):
        response = client.get(base + f"/{cid}/{endpoint}", headers=PAGE_A)
    elif endpoint == "annotation-anchor":
        response = client.post(base + f"/{cid}/{endpoint}", headers=PAGE_A,
                               json={"approximate_elapsed_seconds": 0})
    elif endpoint == "cursor-values":
        response = client.post(base + "/cursor-values", headers=PAGE_A,
                               json={"calculated_channel_ids": [cid], "cursor_a_time": 0})
    else:
        response = client.post(base + "/peak-values", headers=PAGE_A,
                               json={"start_time": 0, "end_time": 0.1, "requests": [{"calculated_channel_id": cid, "mode": "max"}]})
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "incompatible_time_base"


def test_transitive_input_and_non_reference_source_fingerprint(client):
    ids, refs = pair(client)
    parent = create(client, "parent", refs)
    ref = lambda c: {"kind": "calculated", "calculated_channel_id": c["id"]}
    child = create(client, "child", [ref(parent)], "absolute_value")
    grandchild = create(client, "grandchild", [ref(child), refs[0]])
    original = waveform(client, grandchild["id"]).json()["values"]
    client.put(url(ids[1]), headers=PAGE_A, json={"offset_minutes": None})
    listing = client.get(BASE + "/calculated-channels", headers=PAGE_A).json()
    for c in (parent, child, grandchild):
        current = next(row for row in listing if row["id"] == c["id"])
        assert current["timing_status"] == "incompatible"
        assert set(current["timing_source_ids"]) == set(ids)
        assert current["timing_fingerprint"] != c["timing_fingerprint"]
        assert waveform(client, c["id"]).status_code == 400
    response = client.post(BASE + "/calculated-channels", headers=PAGE_A,
                           json={"name": "new", "operation": "absolute_value", "inputs": [ref(grandchild)]})
    assert response.status_code == 400
    client.put(url(ids[1]), headers=PAGE_A, json={"offset_minutes": 480})
    assert waveform(client, grandchild["id"]).json()["values"] == original


def test_equal_revision_numbers_do_not_authorize_different_session_clocks(client):
    ids, refs = pair(client)
    channel = create(client, "sum", refs)
    for sid, offset in zip(ids, (0, 480)):
        response = client.put(url(sid), headers=PAGE_B, json={"offset_minutes": offset})
        assert response.status_code == 200
    assert waveform(client, channel["id"], PAGE_B).status_code == 400
    assert waveform(client, channel["id"]).status_code == 200
    client.put(url(ids[1]), headers=PAGE_B, json={"offset_minutes": 0})
    assert waveform(client, channel["id"], PAGE_B).status_code == 200


@pytest.mark.parametrize("operation,count", [("absolute_value", 1), ("addition", 2)])
def test_single_source_results_remain_valid_without_absolute_authority(client, operation, count):
    ids, refs = pair(client)
    channel = create(client, "single", [refs[0]] * count, operation)
    original = waveform(client, channel["id"]).json()["values"]
    client.put(url(ids[0]), headers=PAGE_A, json={"offset_minutes": None})
    for headers in (PAGE_A, PAGE_B):
        response = waveform(client, channel["id"], headers)
        assert response.status_code == 200, response.text
        assert response.json()["values"] == original


@pytest.mark.parametrize("reader", ["calculation", "overcurrent", "phasor", "readiness", "compliance"])
def test_analysis_readers_do_not_bypass_transitive_session_validation(client, reader):
    from types import SimpleNamespace
    from app.domain.calculated_channel import ChannelRef
    from app.domain.analysis_input_resolution import AnalysisInputResolution
    from app.services import (calculated_channel_service as calculation,
                              overcurrent_analysis_service as overcurrent,
                              phasor_analysis_service as phasor,
                              analysis_input_resolution_service as readiness,
                              compliance_series as compliance)
    from app.services.errors import IncompatibleTimeBaseError
    from app.services.workspace_session import page_session_id
    ids, refs = pair(client)
    parent = create(client, "parent", refs)
    child = create(client, "child", [{"kind": "calculated", "calculated_channel_id": parent["id"]}], "absolute_value")
    client.put(url(ids[1]), headers=PAGE_A, json={"offset_minutes": None})
    ref = ChannelRef(kind="calculated", calculated_channel_id=child["id"])
    sources, calcs = client.app.state.workspace_registry, client.app.state.calculated_channel_registry
    common = dict(workspace_id="clock", source_registry=sources, calculated_channel_registry=calcs)
    token = page_session_id.set(PAGE_A["X-Powerwave-Session"])
    try:
        if reader == "readiness":
            # Even one resolved calculated role must validate its original inputs.
            resolution = AnalysisInputResolution(status="resolved", analysis_kind="overcurrent", mode="phase",
                engineering_context_id="test", resolved_roles={"Ia": ref})
            result = readiness._apply_timebase_check(resolution, **common)
            assert result.status == "needs_configuration"
            assert result.reason_code == "timebase_incompatible"
        else:
            with pytest.raises(IncompatibleTimeBaseError):
                if reader == "calculation":
                    calculation._resolve_input(ref, workspace_id="clock", source_registry=sources, calc_registry=calcs)
                elif reader == "overcurrent":
                    overcurrent._fetch_current_candidate(ref, **common)
                elif reader == "phasor":
                    # This is also the array reader shared by Impedance, Sequence and Distance.
                    phasor._fetch_role_candidate("Va", ref, **common)
                else:
                    compliance._raw(ref, workspace_id="clock", reg=SimpleNamespace(source=sources, calc=calcs))
    finally:
        page_session_id.reset(token)
