"""D5A-2A: `GET .../engineering-contexts/{id}/protection-instrument-context`.

Real app, real ASCII-COMTRADE uploads with a per-channel P/S declaration. Expected ratios are
hand-derived from the configured primary/secondary values. The endpoint is read-only: the last
group of tests proves the legacy compute endpoints are unchanged by it.
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- fixtures / helpers

_ALL = ("VA", "VB", "VC", "IA", "IB", "IC")


def _comtrade(ps: dict[str, str]) -> tuple[bytes, bytes]:
    """Balanced 3-phase: V = 100 V RMS, I = 1 A RMS lagging 30 deg. `ps` maps VA..IC to 'P'/'S'/''."""
    rate, duration, freq = 1000.0, 3.0, 50.0
    n = int(round(rate * duration))
    amp = {"V": 100.0 * math.sqrt(2), "I": 1.0 * math.sqrt(2)}
    shift = {"A": 0.0, "B": -120.0, "C": 120.0}
    rows = []
    for name in _ALL:
        kind, ph = name[0], name[1]
        lag = -30.0 if kind == "I" else 0.0
        rows.append((f"ZBAY_{name}", "V" if kind == "V" else "A", amp[kind], shift[ph] + lag, ps.get(name, "P")))
    cfg = [f"ZSTA,D5A2A,1999", f"{len(rows)},{len(rows)}A,0D"]
    for i, (name, unit, _a, _p, flag) in enumerate(rows, start=1):
        cfg.append(f"{i},{name},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,{flag}")
    cfg += [str(freq), "1", f"{rate},{n}", "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0"]
    t = np.arange(n) / rate
    vals = [a * np.cos(2 * np.pi * freq * t + np.radians(p)) for _n, _u, a, p, _f in rows]
    dat = [",".join([str(r + 1), f"{r * 1000.0:.1f}"] + [f"{vals[c][r]:.6f}" for c in range(len(rows))]) for r in range(n)]
    return ("\n".join(cfg) + "\n").encode("ascii"), ("\n".join(dat) + "\n").encode("ascii")


def _contexts(ws: str) -> str:
    return f"/api/v1/workspaces/{ws}/engineering-contexts"


def _ref(src: str, name: str) -> dict:
    return {"kind": "source", "source_id": src, "channel_name": name}


def _clear(client, ws: str) -> None:
    st = client.app.state
    for ctx in client.get(_contexts(ws)).json():
        client.delete(f"{_contexts(ws)}/{ctx['id']}")
    for g in st.measurement_group_registry.list_for_workspace(ws):
        st.measurement_group_registry.remove(ws, g.id)
        st.voltage_group_config_registry.delete(ws, g.id)
        st.current_group_config_registry.delete(ws, g.id)


def _bay(client, ws: str, *, ps: dict[str, str] | None = None, members=_ALL) -> tuple[str, str]:
    cfg, dat = _comtrade(ps or {})
    resp = client.post(f"/api/v1/workspaces/{ws}/sources", files={
        "cfg_file": ("d5a2a.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("d5a2a.dat", io.BytesIO(dat), "application/octet-stream"),
    })
    assert resp.status_code == 201, resp.text
    src = resp.json()["source_id"]
    _clear(client, ws)
    created = client.post(_contexts(ws), json={"display_name": f"bay-{src}", "status": "manual", "members": [
        {"channel_ref": _ref(src, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"} for n in members
    ]})
    assert created.status_code == 201, created.text
    return src, created.json()["id"]


def _group(client, ws: str, src: str, kind: str, names, gid: str) -> None:
    client.app.state.measurement_group_registry.add(MeasurementGroup(
        id=gid, workspace_id=ws, source_id=src, kind=kind, display_name=gid, status=STATUS_CONFIRMED,
        channel_refs=[ChannelRef(kind="source", source_id=src, channel_name=f"ZBAY_{n}") for n in names],
    ))


def _vt(client, ws, gid, primary, secondary, *, authority="manual", note=None, nominal=None):
    kw = dict(vt_primary_v=primary, vt_secondary_v=secondary, vt_authority=authority, vt_provenance_note=note, update_vt=True)
    if nominal is not None:
        kw.update(nominal_voltage_ll_kv=nominal, update_nominal=True)
    client.app.state.voltage_group_config_registry.update_fields(ws, gid, **kw)


def _ct(client, ws, gid, primary, secondary, *, authority="manual", note=None):
    client.app.state.current_group_config_registry.update_fields(
        ws, gid, ct_primary_a=primary, ct_secondary_a=secondary, ct_authority=authority, ct_provenance_note=note, update_ct=True)


def _full_setup(client, ws, *, ps=None):
    src, ctx = _bay(client, ws, ps=ps)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), "vg-1")
    _group(client, ws, src, KIND_CURRENT, ("IA", "IB", "IC"), "ig-1")
    _vt(client, ws, "vg-1", 132000.0, 110.0, note="VT nameplate")   # ratio 1200
    _ct(client, ws, "ig-1", 1200.0, 5.0, note="CT nameplate")        # ratio 240
    return src, ctx


def _ctx(client, ws, ctx, **params):
    return client.get(f"{_contexts(ws)}/{ctx}/protection-instrument-context", params=params)


def _codes(body) -> list[str]:
    return [d["code"] for d in body["diagnostics"]]


def _diag(body, code):
    return next(d for d in body["diagnostics"] if d["code"] == code)


# --------------------------------------------------------------------------- association & provenance


def test_impedance_context_reports_the_owning_groups_ratios_and_provenance(client):
    ws = "d5a2a-assoc"
    src, ctx = _full_setup(client, ws)
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    assert body["read_only"] is True
    by_role = {c["role_key"]: c for c in body["channels"]}
    assert set(by_role) == {"Va", "Ia"}
    assert by_role["Va"]["channel"] == {"kind": "source", "source_id": src, "channel_name": "ZBAY_VA", "calculated_channel_id": None}
    assert by_role["Va"]["measurement_group_id"] == "vg-1" and by_role["Va"]["measurement_group_kind"] == "voltage"
    assert by_role["Ia"]["measurement_group_id"] == "ig-1" and by_role["Ia"]["measurement_group_kind"] == "current"
    v, c = body["voltage"], body["current"]
    assert (v["ratio_status"], v["ratio"], v["primary"], v["secondary"], v["group_ids"]) == ("configured", pytest.approx(1200.0), 132000.0, 110.0, ["vg-1"])
    assert (c["ratio_status"], c["ratio"], c["group_ids"]) == ("configured", pytest.approx(240.0), ["ig-1"])
    assert (v["authority"], v["provenance_note"], v["ratio_origin"]) == ("manual", "VT nameplate", "recording_details_measurement_group")
    assert (c["authority"], c["provenance_note"]) == ("manual", "CT nameplate")


def test_overcurrent_uses_current_only(client):
    ws = "d5a2a-oc"
    _, ctx = _full_setup(client, ws)
    body = _ctx(client, ws, ctx, analysis="overcurrent", phase="B").json()
    assert body["voltage"] is None
    assert [c["role_key"] for c in body["channels"]] == ["Ib"]
    assert body["current"]["ratio"] == pytest.approx(240.0)


def test_distance_loop_resolves_both_voltage_and_both_current_roles(client):
    ws = "d5a2a-dist"
    _, ctx = _full_setup(client, ws)
    body = _ctx(client, ws, ctx, analysis="distance_protection", loop="BC").json()
    assert [c["role_key"] for c in body["channels"]] == ["Vb", "Vc", "Ib", "Ic"]
    assert body["voltage"]["ratio"] == pytest.approx(1200.0) and body["current"]["ratio"] == pytest.approx(240.0)


# --------------------------------------------------------------------------- isolation, no synthetic VT


def test_two_recordings_in_one_workspace_never_share_configuration(client):
    ws = "d5a2a-iso"
    _, ctx1 = _full_setup(client, ws)
    cfg, dat = _comtrade({})
    second = client.post(f"/api/v1/workspaces/{ws}/sources", files={
        "cfg_file": ("other.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("other.dat", io.BytesIO(dat), "application/octet-stream"),
    }).json()["source_id"]
    st = client.app.state
    for auto in client.get(_contexts(ws)).json():          # drop only the 2nd upload's automatic artifacts
        if auto["id"] != ctx1:
            client.delete(f"{_contexts(ws)}/{auto['id']}")
    for g in st.measurement_group_registry.list_for_source(ws, second):
        st.measurement_group_registry.remove(ws, g.id)
        st.voltage_group_config_registry.delete(ws, g.id)
        st.current_group_config_registry.delete(ws, g.id)
    resp = client.post(_contexts(ws), json={"display_name": "bay-2", "status": "manual", "members": [
        {"channel_ref": _ref(second, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"} for n in _ALL]})
    ctx2 = resp.json()["id"]
    one = _ctx(client, ws, ctx1, analysis="impedance", phase="A").json()
    two = _ctx(client, ws, ctx2, analysis="impedance", phase="A").json()
    assert one["current"]["ratio_consumable"] and one["voltage"]["ratio_consumable"]
    assert two["voltage"]["ratio_status"] == "no_group" and two["current"]["ratio_status"] == "no_group"
    assert two["voltage"]["ratio"] is None and two["current"]["ratio"] is None
    assert {"VT_AUTHORITY_MISSING", "CT_AUTHORITY_MISSING"} <= set(_codes(two))


def test_nominal_voltage_alone_is_reported_as_a_consumable_auto_derived_vt(client):
    ws = "d5a2a-nominal"
    src, ctx = _bay(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), "vg-1")
    client.app.state.voltage_group_config_registry.update_fields(ws, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    v = body["voltage"]
    assert (v["ratio_status"], v["ratio"], v["primary"], v["secondary"], v["ratio_consumable"]) == ("configured", 1200.0, 132000.0, 110.0, True)
    assert v["authority"] == "auto_nominal" and v["nominal_ll_kv"] == 132.0 and v["nominal_refused_reason"] is None
    assert "VT_AUTHORITY_MISSING" not in _codes(body) and "VT_NOMINAL_NOT_USABLE" not in _codes(body)


def test_a_refused_nominal_is_reported_with_its_reason(client):
    ws = "d5a2a-nominal-refused"
    src, ctx = _bay(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), "vg-1")
    reg = client.app.state.voltage_group_config_registry
    reg.update_fields(ws, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    config = reg.get(ws, "vg-1")
    config.manual_conflict_detected = True
    reg.upsert(config)
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    v = body["voltage"]
    assert (v["ratio_status"], v["ratio_consumable"], v["nominal_ll_kv"], v["nominal_refused_reason"]) == ("not_configured", False, 132.0, "manual_conflict")
    assert {"VT_AUTHORITY_MISSING", "VT_NOMINAL_NOT_USABLE"} <= set(_codes(body))


def test_a_request_vt_is_checked_against_the_auto_derived_vt(client):
    ws = "d5a2a-nominal-req"
    src, ctx = _bay(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), "vg-1")
    client.app.state.voltage_group_config_registry.update_fields(ws, "vg-1", nominal_voltage_ll_kv=132.0, update_nominal=True)
    same = _ctx(client, ws, ctx, analysis="impedance", phase="A", vt_primary=132000.0, vt_secondary=110.0).json()
    assert "REQUEST_VT_NOT_VERIFIED_BY_AUTHORITY" not in _codes(same) and "REQUEST_VT_DIFFERS_FROM_AUTHORITY" not in _codes(same)
    other = _ctx(client, ws, ctx, analysis="impedance", phase="A", vt_primary=66000.0, vt_secondary=110.0).json()
    assert "REQUEST_VT_DIFFERS_FROM_AUTHORITY" in _codes(other)


# --------------------------------------------------------------------------- measurement sides


def test_each_channel_reports_its_own_declared_side(client):
    ws = "d5a2a-sides"
    _, ctx = _full_setup(client, ws, ps={"VA": "P", "VB": "S", "IA": "S", "IB": "P"})
    body = _ctx(client, ws, ctx, analysis="distance_protection", loop="AB").json()
    sides = {c["role_key"]: c["declared_side"] for c in body["channels"]}
    assert sides == {"Va": "primary", "Vb": "secondary", "Ia": "secondary", "Ib": "primary"}
    assert all(c["side_evidence"] == "recording_declared" and c["provider_type"] == "COMTRADE" for c in body["channels"])
    assert body["voltage"]["side_status"] == "mixed" and body["voltage"]["declared_basis"] is None
    assert body["current"]["side_status"] == "mixed"
    assert {"VOLTAGE_SIDE_MIXED", "CURRENT_SIDE_MIXED"} <= set(_codes(body))


def test_unknown_side_is_reported_as_missing_evidence_not_assumed(client):
    ws = "d5a2a-unknown"
    _, ctx = _full_setup(client, ws, ps={"VA": "", "IA": ""})
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    assert {c["declared_side"] for c in body["channels"]} == {"unknown"}
    assert {c["side_evidence"] for c in body["channels"]} == {"none"}
    assert body["voltage"]["declared_basis"] is None and body["current"]["declared_basis"] is None
    assert {"VOLTAGE_SIDE_UNKNOWN", "CURRENT_SIDE_UNKNOWN"} <= set(_codes(body))
    assert body["voltage"]["ratio_consumable"] and body["current"]["ratio_consumable"]   # ratio is not a side


def test_voltage_and_current_may_be_recorded_on_different_sides(client):
    ws = "d5a2a-differ"
    _, ctx = _full_setup(client, ws, ps={"VA": "P", "IA": "S"})
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    assert (body["voltage"]["declared_basis"], body["current"]["declared_basis"]) == ("primary", "secondary")
    assert _diag(body, "VOLTAGE_CURRENT_SIDES_DIFFER")["detail"] == {"voltage_side": "primary", "current_side": "secondary"}


# --------------------------------------------------------------------------- request-vs-authority diagnostics


def test_request_ratio_that_differs_is_flagged_with_both_values(client):
    ws = "d5a2a-diff"
    _, ctx = _full_setup(client, ws)
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A", ct_primary=2000.0, ct_secondary=5.0,
                vt_primary=132000.0, vt_secondary=110.0).json()
    d = _diag(body, "REQUEST_CT_DIFFERS_FROM_AUTHORITY")
    assert d["severity"] == "warning" and d["quantity"] == "current"
    assert (d["detail"]["request_ratio"], d["detail"]["authoritative_ratio"]) == (pytest.approx(400.0), pytest.approx(240.0))
    assert "REQUEST_VT_DIFFERS_FROM_AUTHORITY" not in _codes(body)


def test_same_ratio_expressed_differently_is_not_a_difference(client):
    ws = "d5a2a-same"
    _, ctx = _full_setup(client, ws)
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A", ct_primary=240.0, ct_secondary=1.0,
                vt_primary=13200.0, vt_secondary=11.0).json()
    assert not [c for c in _codes(body) if c.startswith("REQUEST_") and c.endswith("DIFFERS_FROM_AUTHORITY")]


def test_incomplete_and_invalid_request_ratios_are_flagged(client):
    ws = "d5a2a-bad"
    _, ctx = _full_setup(client, ws)
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A", ct_primary=1200.0, vt_primary=-1.0, vt_secondary=110.0).json()
    assert "REQUEST_CT_INCOMPLETE" in _codes(body) and "REQUEST_VT_INVALID" in _codes(body)


def test_request_basis_contradicting_declared_side_is_flagged_per_quantity(client):
    ws = "d5a2a-contra"
    _, ctx = _full_setup(client, ws, ps={"VA": "P", "IA": "S"})
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A", recording_basis="primary", impedance_basis="secondary").json()
    codes = _codes(body)
    assert "REQUEST_RECORDING_BASIS_CONTRADICTS_CURRENT_SIDE" in codes
    assert "REQUEST_RECORDING_BASIS_CONTRADICTS_VOLTAGE_SIDE" not in codes
    assert _diag(body, "REQUEST_RECORDING_BASIS_CONTRADICTS_CURRENT_SIDE")["detail"] == {"recording_basis": "primary", "declared_side": "secondary"}


def test_invalid_recording_basis_is_flagged(client):
    ws = "d5a2a-basis"
    _, ctx = _full_setup(client, ws)
    assert "REQUEST_RECORDING_BASIS_INVALID" in _codes(_ctx(client, ws, ctx, analysis="impedance", phase="A", recording_basis="unknown").json())


def test_conversion_without_authority_or_side_is_flagged(client):
    ws = "d5a2a-conv"
    src, ctx = _bay(client, ws, ps={"IA": ""})            # no groups at all, current side unknown
    body = _ctx(client, ws, ctx, analysis="overcurrent", phase="A", recording_basis="primary").json()
    codes = _codes(body)
    assert {"CT_AUTHORITY_MISSING", "CURRENT_SIDE_UNKNOWN", "CONVERSION_REQUESTED_WITHOUT_AUTHORITY",
            "CONVERSION_REQUESTED_WITH_UNKNOWN_SIDE", "REQUEST_RECORDING_BASIS_UNVERIFIABLE_CURRENT"} <= set(codes)


def test_no_conversion_diagnostic_when_request_needs_no_conversion(client):
    ws = "d5a2a-noconv"
    _, ctx = _full_setup(client, ws, ps={"VA": "S", "IA": "S"})
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A", recording_basis="secondary", impedance_basis="secondary").json()
    assert body["diagnostics"] == []


def test_unresolved_channel_is_reported(client):
    ws = "d5a2a-unres"
    _, ctx = _bay(client, ws, members=("VA", "VB", "VC"))   # no current members
    body = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    d = _diag(body, "CHANNEL_UNRESOLVED")
    assert d["detail"]["role_key"] == "Ia" and d["quantity"] == "current"
    assert body["current"]["ratio_status"] == "no_channels"


def test_untrusted_authority_is_not_consumable(client):
    ws = "d5a2a-untrusted"
    src, ctx = _bay(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), "vg-1")
    _vt(client, ws, "vg-1", 132000.0, 110.0, authority="auto_nominal")
    v = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()["voltage"]
    assert (v["ratio_status"], v["ratio"]) == ("untrusted_authority", None)


# --------------------------------------------------------------------------- errors


def test_unknown_engineering_context_is_404(client):
    assert _ctx(client, "d5a2a-404", "nope", analysis="impedance", phase="A").status_code == 404


def test_bad_analysis_and_missing_phase_or_loop_are_rejected(client):
    ws = "d5a2a-422"
    _, ctx = _full_setup(client, ws)
    assert _ctx(client, ws, ctx, analysis="phasor", phase="A").status_code == 422
    assert _ctx(client, ws, ctx, analysis="overcurrent").status_code == 422
    assert _ctx(client, ws, ctx, analysis="impedance").status_code == 422
    assert _ctx(client, ws, ctx, analysis="distance_protection").status_code == 422
    assert _ctx(client, ws, ctx, analysis="distance_protection", loop="XY").status_code == 422


# --------------------------------------------------------------------------- legacy behaviour untouched


def _impedance(client, ws, ctx, **extra):
    params = {"phase": "A", "analysis_time": 1.5, "recording_basis": "primary", "impedance_basis": "secondary",
              "vt_primary": 110000.0, "vt_secondary": 110.0, "ct_primary": 1000.0, "ct_secondary": 5.0}
    params.update(extra)
    return client.get(f"{_contexts(ws)}/{ctx}/impedance", params=params)


def test_request_ratios_never_replace_the_authority_and_the_read_only_report_changes_nothing(client):
    """D5A-2B2C-1B reverses the old rule. Authoritative VT 1200 / CT 240 differ from the request's 1000 / 200: the compute endpoint
    must NOT use the request values (it blocks, because the request ratios contradict Recording Details), and the read-only
    context report neither changes the calculation nor is changed by it."""
    ws = "d5a2a-legacy"
    _, ctx = _full_setup(client, ws)
    before = _impedance(client, ws, ctx).json()
    assert (before["status"], before["reason_code"]) == ("needs_configuration", "request_vt_conflicts_with_authority")
    assert before["magnitude_ohm"] is None
    report = _ctx(client, ws, ctx, analysis="impedance", phase="A", recording_basis="primary", impedance_basis="secondary",
                  vt_primary=110000.0, vt_secondary=110.0, ct_primary=1000.0, ct_secondary=5.0).json()
    after = _impedance(client, ws, ctx).json()
    assert before == after
    assert {"REQUEST_CT_DIFFERS_FROM_AUTHORITY", "REQUEST_VT_DIFFERS_FROM_AUTHORITY"} <= set(_codes(report))
    # Without the contradicting ratios the AUTHORITATIVE ones decide: Z_sec = (100 V / 1 A) * ct_ratio 240 / vt_ratio 1200.
    plain = client.get(f"{_contexts(ws)}/{ctx}/impedance", params={"phase": "A", "analysis_time": 1.5, "impedance_basis": "secondary"}).json()
    assert plain["status"] == "computed" and plain["magnitude_ohm"] == pytest.approx(100.0 * 240.0 / 1200.0, rel=1e-2)
    assert (plain["vt_primary"], plain["vt_secondary"], plain["ct_primary"], plain["ct_secondary"]) == (132000.0, 110.0, 1200.0, 5.0)


def test_context_resolves_the_same_channels_as_the_compute_path(client):
    ws = "d5a2a-parity"
    _, ctx = _full_setup(client, ws)
    compute = _impedance(client, ws, ctx).json()
    report = _ctx(client, ws, ctx, analysis="impedance", phase="A").json()
    by_role = {c["role_key"]: c["channel"] for c in report["channels"]}
    assert by_role["Va"]["channel_name"] == compute["voltage_channel_ref"]["channel_name"]
    assert by_role["Ia"]["channel_name"] == compute["current_channel_ref"]["channel_name"]
