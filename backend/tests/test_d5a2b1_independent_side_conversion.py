"""D5A-2B1: opt-in independent Voltage/Current side conversion for recorded Impedance and Distance.

Expected values are derived by hand from the physical worked example, never from the production
conversion code:

    VT 110000 V : 110 V  (ratio 1000)        CT 1000 A : 5 A  (ratio 200)
    V_primary = 66 000 V -> V_secondary = 66 V          I_primary = 400 A -> I_secondary = 2 A
    Z_primary = 66 000 / 400 = 165 ohm                  Z_secondary = 66 / 2 = 33 ohm
    Current lags voltage by 30 deg, so Z = |Z| at +30 deg: R = |Z| cos 30, X = |Z| sin 30.

Real app, real ASCII-COMTRADE uploads with a per-channel P/S declaration.
"""

from __future__ import annotations

import io
import itertools
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.domain.side_conversion import SidePlan, convert_to_side
from app.main import create_app
from tests.test_d5a2a_protection_instrument_context_api import _clear, _contexts, _ct, _group, _ref, _vt
from tests.test_distance_protection_analysis_api import _ZONE_DISABLED_PARAMS


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


V_PRI, V_SEC, I_PRI, I_SEC = 66000.0, 66.0, 400.0, 2.0
Z_PRI, Z_SEC = 165.0, 33.0
ANGLE = 30.0
VT_P, VT_S, CT_P, CT_S = 110000.0, 110.0, 1000.0, 5.0
_ALL = ("VA", "VB", "VC", "IA", "IB", "IC")


# --------------------------------------------------------------------------- recording builders


def _comtrade(*, v_rms: float, i_rms: float, ps: dict[str, str], v_unit: str = "V", i_unit: str = "A",
              i_gain: float = 1.0) -> tuple[bytes, bytes]:
    rate, duration, freq = 1000.0, 3.0, 50.0
    n = int(round(rate * duration))
    shift = {"A": 0.0, "B": -120.0, "C": 120.0}
    rows = []
    for name in _ALL:
        quantity, phase = name[0], name[1]
        amp = (v_rms if quantity == "V" else i_rms) * math.sqrt(2)
        angle = shift[phase] + (-ANGLE if quantity == "I" else 0.0)
        rows.append((f"ZBAY_{name}", v_unit if quantity == "V" else i_unit, amp, angle, ps.get(name, "P"), 1.0 if quantity == "V" else i_gain))
    cfg = ["ZSTA,D5A2B1,1999", f"{len(rows)},{len(rows)}A,0D"]
    for i, (name, unit, _a, _p, flag, gain) in enumerate(rows, start=1):
        cfg.append(f"{i},{name},,,{unit},{gain!r},0.0,0,-99999999,99999999,1.0,1.0,{flag}")
    cfg += [str(freq), "1", f"{rate},{n}", "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0"]
    t = np.arange(n) / rate
    vals = [(a / g) * np.cos(2 * np.pi * freq * t + np.radians(p)) for _n, _u, a, p, _f, g in rows]
    dat = [",".join([str(r + 1), f"{r * 1000.0:.1f}"] + [f"{vals[c][r]:.6f}" for c in range(len(rows))]) for r in range(n)]
    return ("\n".join(cfg) + "\n").encode("ascii"), ("\n".join(dat) + "\n").encode("ascii")


def _upload(client, ws: str, cfg: bytes, dat: bytes, stem: str = "d5a2b1") -> str:
    resp = client.post(f"/api/v1/workspaces/{ws}/sources", files={
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _context(client, ws: str, src: str, members=_ALL) -> str:
    resp = client.post(_contexts(ws), json={"display_name": f"bay-{src}", "status": "manual", "members": [
        {"channel_ref": _ref(src, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"} for n in members]})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _bay(client, ws: str, *, v_side="primary", i_side="primary", ps=None, v_rms=None, i_rms=None, groups=True,
         vt=(VT_P, VT_S), ct=(CT_P, CT_S), members=_ALL, v_unit="V", i_unit="A", i_gain=1.0) -> tuple[str, str]:
    """One recording whose P/S flags and magnitudes follow the requested physical sides."""
    flags = {n: ("P" if (v_side if n[0] == "V" else i_side) == "primary" else "S") for n in _ALL}
    flags.update(ps or {})
    cfg, dat = _comtrade(
        v_rms=v_rms if v_rms is not None else (V_PRI if v_side == "primary" else V_SEC),
        i_rms=i_rms if i_rms is not None else (I_PRI if i_side == "primary" else I_SEC),
        ps=flags, v_unit=v_unit, i_unit=i_unit, i_gain=i_gain,
    )
    src = _upload(client, ws, cfg, dat)
    _clear(client, ws)
    ctx = _context(client, ws, src, members)
    if groups:
        _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), f"vg-{src}")
        _group(client, ws, src, KIND_CURRENT, ("IA", "IB", "IC"), f"ig-{src}")
        _vt(client, ws, f"vg-{src}", *vt, note="VT nameplate")
        _ct(client, ws, f"ig-{src}", *ct, note="CT nameplate")
    return src, ctx


# --------------------------------------------------------------------------- request helpers


def _imp(client, ws, ctx, **params):
    q = {"phase": "A", "analysis_time": 1.5}
    q.update(params)
    return client.get(f"{_contexts(ws)}/{ctx}/impedance", params=q)


def _imp_locus(client, ws, ctx, **params):
    q = {"phase": "A", "start_time": 1.0, "end_time": 2.0, "point_count": 3}
    q.update(params)
    return client.get(f"{_contexts(ws)}/{ctx}/impedance-locus", params=q)


def _dist(client, ws, ctx, **params):
    q = {"loop": "AB", "analysis_time": 1.5, "characteristic": "mho", **_ZONE_DISABLED_PARAMS}
    q.update(params)
    return client.get(f"{_contexts(ws)}/{ctx}/distance-protection", params=q)


def _dist_locus(client, ws, ctx, **params):
    q = {"loop": "AB", "start_time": 1.0, "end_time": 2.0, "point_count": 3, "characteristic": "mho", **_ZONE_DISABLED_PARAMS}
    q.update(params)
    return client.get(f"{_contexts(ws)}/{ctx}/distance-protection-locus", params=q)


def _strict(vs, cs, out, **extra):
    return {"voltage_side": vs, "current_side": cs, "impedance_basis": out, **extra}


def _expect(out: str) -> tuple[float, float, float]:
    mag = Z_PRI if out == "primary" else Z_SEC
    return mag, mag * math.cos(math.radians(ANGLE)), mag * math.sin(math.radians(ANGLE))


def _ratios_needed(vs: str, cs: str, out: str) -> tuple[bool, bool]:
    return vs != out, cs != out


# =========================================================================== pure conversion maths


@pytest.mark.parametrize("value,source,out,ratio,expected", [
    (66.0, "secondary", "primary", 1000.0, 66000.0),      # secondary -> primary multiplies
    (66000.0, "primary", "secondary", 1000.0, 66.0),      # primary -> secondary divides
    (2.0, "secondary", "primary", 200.0, 400.0),
    (400.0, "primary", "secondary", 200.0, 2.0),
])
def test_conversion_in_both_directions(value, source, out, ratio, expected):
    assert convert_to_side(value, source, out, ratio) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("side", ["primary", "secondary"])
@pytest.mark.parametrize("ratio", [None, 0.0, -3.0, float("nan")])
def test_same_side_is_an_identity_that_never_reads_the_ratio(side, ratio):
    value = 123.456789
    assert convert_to_side(value, side, side, ratio) == value       # bit-exact, no multiplication


@pytest.mark.parametrize("ratio", [None, 0.0, -3.0, float("nan"), float("inf")])
def test_a_required_conversion_with_an_unusable_ratio_never_fabricates_a_value(ratio):
    with pytest.raises(ValueError):
        convert_to_side(66.0, "secondary", "primary", ratio)


def test_a_plan_scales_each_quantity_independently():
    plan = SidePlan(voltage_side="primary", current_side="secondary", output_side="primary", vt_ratio=None, ct_ratio=200.0)
    assert plan.scale_voltage(66000.0) == 66000.0           # already primary: untouched (no VT needed)
    assert plan.scale_current(2.0) == pytest.approx(400.0)   # secondary -> primary through the CT
    assert plan.current_scale == pytest.approx(200.0)


# =========================================================================== the eight-combination oracle


@pytest.mark.parametrize("vs,cs", list(itertools.product(["primary", "secondary"], repeat=2)))
def test_oracle_impedance_all_output_sides(client, vs, cs):
    ws = f"d5a2b1-imp-{vs[:1]}{cs[:1]}"
    _, ctx = _bay(client, ws, v_side=vs, i_side=cs)
    for out in ("primary", "secondary"):
        body = _imp(client, ws, ctx, **_strict(vs, cs, out)).json()
        mag, r, x = _expect(out)
        assert body["status"] == "computed", body
        assert body["magnitude_ohm"] == pytest.approx(mag, rel=1e-3)
        assert (body["resistance_ohm"], body["reactance_ohm"]) == (pytest.approx(r, rel=1e-3), pytest.approx(x, rel=1e-3))
        assert body["angle_deg"] == pytest.approx(ANGLE, abs=0.05)
        sc = body["side_conversion"]
        vt_needed, ct_needed = _ratios_needed(vs, cs, out)
        assert sc["mode"] == "independent_sides" and (sc["voltage_side"], sc["current_side"], sc["output_side"]) == (vs, cs, out)
        assert sc["vt_ratio_applied"] == (pytest.approx(1000.0) if vt_needed else None)
        assert sc["ct_ratio_applied"] == (pytest.approx(200.0) if ct_needed else None)
        assert sc["block_code"] is None


@pytest.mark.parametrize("vs,cs", list(itertools.product(["primary", "secondary"], repeat=2)))
def test_oracle_impedance_locus_all_output_sides(client, vs, cs):
    ws = f"d5a2b1-loc-{vs[:1]}{cs[:1]}"
    _, ctx = _bay(client, ws, v_side=vs, i_side=cs)
    for out in ("primary", "secondary"):
        body = _imp_locus(client, ws, ctx, **_strict(vs, cs, out)).json()
        assert body["side_conversion"]["mode"] == "independent_sides"
        assert len(body["points"]) == 3
        for p in body["points"]:
            assert p["status"] == "computed" and p["magnitude_ohm"] == pytest.approx(_expect(out)[0], rel=1e-3)


@pytest.mark.parametrize("vs,cs", list(itertools.product(["primary", "secondary"], repeat=2)))
def test_oracle_distance_phase_to_phase_all_output_sides(client, vs, cs):
    """Balanced set: Vab / Iab = (V sqrt3 at +30) / (I sqrt3 at 0) = V/I at +30 deg, so the loop impedance equals Z."""
    ws = f"d5a2b1-dist-{vs[:1]}{cs[:1]}"
    _, ctx = _bay(client, ws, v_side=vs, i_side=cs)
    for out in ("primary", "secondary"):
        for loop in ("AB", "BC", "CA"):
            body = _dist(client, ws, ctx, loop=loop, **_strict(vs, cs, out)).json()
            assert body["status"] == "computed", body
            assert body["magnitude_ohm"] == pytest.approx(_expect(out)[0], rel=1e-3)
            assert body["angle_deg"] == pytest.approx(ANGLE, abs=0.05)
            assert body["side_conversion"]["output_side"] == out


@pytest.mark.parametrize("vs,cs", list(itertools.product(["primary", "secondary"], repeat=2)))
def test_oracle_distance_locus(client, vs, cs):
    ws = f"d5a2b1-dl-{vs[:1]}{cs[:1]}"
    _, ctx = _bay(client, ws, v_side=vs, i_side=cs)
    body = _dist_locus(client, ws, ctx, **_strict(vs, cs, "primary")).json()
    assert body["side_conversion"]["mode"] == "independent_sides"
    assert all(p["status"] == "computed" and p["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3) for p in body["points"])


def test_kilovolt_recording_is_normalised_before_conversion(client):
    ws = "d5a2b1-kv"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary", v_rms=66.0, v_unit="kV")     # 66 kV = 66 000 V
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)


# =========================================================================== no duplicate / unnecessary scaling


def test_quantities_already_on_the_output_side_need_no_ratio_at_all(client):
    ws = "d5a2b1-noratio"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary", groups=False)        # no CT/VT configured anywhere
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)
    assert body["side_conversion"]["vt_ratio_applied"] is None and body["side_conversion"]["ct_ratio_applied"] is None
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    assert body["status"] == "needs_configuration" and body["reason_code"] == "vt_authority_unavailable"


def test_double_scaling_would_be_visible(client):
    """Primary samples to a primary output must stay 165 ohm; a second primary->primary scaling would give 165*200/1000."""
    ws = "d5a2b1-nodouble"
    _, ctx = _bay(client, ws)
    mag = _imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json()["magnitude_ohm"]
    assert mag == pytest.approx(165.0, rel=1e-3) and mag != pytest.approx(165.0 * 200.0 / 1000.0, rel=1e-3)


def test_the_low_current_floor_judges_the_recorded_current_not_the_scaled_one(client):
    """Recorded 0.005 A primary (above the 1 mA floor) is 2.5e-5 A once scaled to secondary; it must still compute."""
    ws = "d5a2b1-floor"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary", v_rms=66.0, i_rms=0.005)
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    assert body["status"] == "computed"
    assert body["magnitude_ohm"] == pytest.approx((66.0 / 0.005) * 200.0 / 1000.0, rel=1e-3)     # 13 200 ohm primary -> 2 640 secondary


def test_a_recorded_current_below_the_floor_is_refused(client):
    ws = "d5a2b1-toosmall"
    _, ctx = _bay(client, ws, v_side="secondary", i_side="secondary", v_rms=66.0, i_rms=0.0005)
    body = _imp(client, ws, ctx, **_strict("secondary", "secondary", "secondary")).json()
    assert (body["status"], body["reason_code"]) == ("needs_configuration", "current_too_small")
    assert body["magnitude_ohm"] is None


# =========================================================================== authority validation (strict mode refuses)


def _blocked(body, code, quantity=None):
    assert body["status"] == "needs_configuration", body
    assert body["reason_code"] == code, body
    assert body["magnitude_ohm"] is None and body["resistance_ohm"] is None
    assert body["side_conversion"]["block_code"] == code
    if quantity is not None:
        assert body["side_conversion"]["block_quantity"] == quantity


def test_missing_vt_blocks_only_when_a_voltage_conversion_is_needed(client):
    ws = "d5a2b1-novt"
    _, ctx = _bay(client, ws, v_side="primary", i_side="secondary", groups=False)
    _blocked(_imp(client, ws, ctx, **_strict("primary", "secondary", "secondary")).json(), "vt_authority_unavailable", "voltage")


def test_missing_ct_blocks_only_when_a_current_conversion_is_needed(client):
    ws = "d5a2b1-noct"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    client.app.state.current_group_config_registry.delete(ws, f"ig-{src}")                       # VT stays, CT gone
    _blocked(_imp(client, ws, ctx, **_strict("secondary", "secondary", "primary")).json(), "ct_authority_unavailable", "current")
    ok = _imp(client, ws, ctx, **_strict("secondary", "secondary", "secondary")).json()       # no conversion: CT never read
    assert ok["status"] == "computed" and ok["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)


@pytest.mark.parametrize("ct", [(1000.0, 0.0), (0.0, 5.0), (-1000.0, 5.0), (1000.0, None)])
def test_invalid_authoritative_ratios_never_produce_a_result(client, ct):
    ws = f"d5a2b1-badct-{abs(hash(ct)) % 10000}"
    _, ctx = _bay(client, ws, v_side="secondary", i_side="primary", ct=ct)
    body = _imp(client, ws, ctx, **_strict("secondary", "primary", "secondary")).json()
    _blocked(body, "ct_authority_unavailable", "current")
    assert body["side_conversion"]["block_detail"]["ratio_status"] == "invalid"


def test_untrusted_ratio_authority_is_not_consumed(client):
    ws = "d5a2b1-untrusted"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    _vt(client, ws, f"vg-{src}", VT_P, VT_S, authority="auto_nominal")
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    _blocked(body, "vt_authority_unavailable", "voltage")
    assert body["side_conversion"]["block_detail"]["ratio_status"] == "untrusted_authority"


def test_nominal_voltage_alone_is_never_a_vt_ratio(client):
    ws = "d5a2b1-nominal"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    client.app.state.voltage_group_config_registry.update_fields(
        ws, f"vg-{src}", nominal_voltage_ll_kv=110.0, update_nominal=True, vt_primary_v=None, vt_secondary_v=None,
        vt_authority="not_configured", update_vt=True)
    _blocked(_imp(client, ws, ctx, **_strict("primary", "primary", "secondary")).json(), "vt_authority_unavailable", "voltage")


def test_unknown_recorded_side_cannot_be_confirmed_by_the_caller(client):
    ws = "d5a2b1-unknown"
    _, ctx = _bay(client, ws, ps={"IA": ""})
    _blocked(_imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json(),
             "current_side_authority_unavailable", "current")


def test_an_asserted_side_that_contradicts_the_recording_blocks_and_never_falls_back_to_legacy(client):
    ws = "d5a2b1-contra"
    _, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    body = _imp(client, ws, ctx, **_strict("primary", "secondary", "secondary"), recording_basis="secondary",
                vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S).json()
    _blocked(body, "voltage_side_contradicts_recording", "voltage")
    assert body["side_conversion"]["block_detail"]["declared_side"] == "secondary"
    # a valid-looking legacy recording_basis was supplied; the strict path must not have used it.
    assert body["recording_basis"] == "secondary" and body["magnitude_ohm"] is None


def test_current_contradiction_is_reported_for_current(client):
    ws = "d5a2b1-contra-i"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    _blocked(_imp(client, ws, ctx, **_strict("primary", "secondary", "primary")).json(), "current_side_contradicts_recording", "current")


def test_a_missing_side_is_never_inferred_from_recording_basis(client):
    ws = "d5a2b1-required"
    _, ctx = _bay(client, ws)
    only_v = _imp(client, ws, ctx, voltage_side="primary", impedance_basis="primary", recording_basis="primary").json()
    _blocked(only_v, "current_side_required", "current")
    only_i = _imp(client, ws, ctx, current_side="primary", impedance_basis="primary", recording_basis="primary").json()
    _blocked(only_i, "voltage_side_required", "voltage")


@pytest.mark.parametrize("params,code", [
    ({"voltage_side": "both", "current_side": "primary"}, "invalid_voltage_side"),
    ({"voltage_side": "primary", "current_side": ""}, "invalid_current_side"),
])
def test_invalid_side_values_are_refused(client, params, code):
    ws = f"d5a2b1-inv-{code}"
    _, ctx = _bay(client, ws)
    assert _imp(client, ws, ctx, impedance_basis="primary", **params).json()["reason_code"] == code


def test_invalid_output_basis_is_refused_in_strict_mode(client):
    ws = "d5a2b1-badout"
    _, ctx = _bay(client, ws)
    assert _imp(client, ws, ctx, **_strict("primary", "primary", "both")).json()["reason_code"] == "invalid_impedance_basis"


def test_request_ratio_that_contradicts_the_authority_blocks_when_it_would_be_consumed(client):
    ws = "d5a2b1-reqconflict"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "secondary"), vt_primary=100000.0, vt_secondary=110.0).json()
    _blocked(body, "request_vt_conflicts_with_authority", "voltage")
    d = body["side_conversion"]["block_detail"]
    assert (d["request_ratio"], d["authoritative_ratio"]) == (pytest.approx(100000.0 / 110.0), pytest.approx(1000.0))


def test_request_ratios_are_never_applied_and_an_equal_pair_is_accepted(client):
    ws = "d5a2b1-reqok"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    ok = _imp(client, ws, ctx, **_strict("primary", "primary", "secondary"),
              vt_primary=11000.0, vt_secondary=11.0, ct_primary=200.0, ct_secondary=1.0).json()   # same 1000 / 200
    assert ok["status"] == "computed" and ok["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)
    # a request ratio for a quantity that is NOT converted is not consumed, so it cannot conflict
    ignored = _imp(client, ws, ctx, **_strict("primary", "primary", "primary"), vt_primary=1.0, vt_secondary=1.0).json()
    assert ignored["status"] == "computed" and ignored["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)


# =========================================================================== mixed sides, unused channels


def test_mixed_voltage_sides_within_a_distance_loop_are_rejected(client):
    ws = "d5a2b1-mixv"
    _, ctx = _bay(client, ws, ps={"VA": "P", "VB": "S"})
    body = _dist(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    _blocked(body, "voltage_mixed_side_within_quantity", "voltage")
    assert "ZBAY_VA=primary" in body["side_conversion"]["block_detail"]["channels"]


def test_mixed_current_sides_within_a_distance_loop_are_rejected(client):
    ws = "d5a2b1-mixi"
    _, ctx = _bay(client, ws, ps={"IA": "P", "IB": "S"})
    _blocked(_dist(client, ws, ctx, **_strict("primary", "primary", "primary")).json(),
             "current_mixed_side_within_quantity", "current")


def test_unrelated_unused_channels_never_reject_a_recording(client):
    ws = "d5a2b1-unused"
    _, ctx = _bay(client, ws, ps={"VC": "S", "IC": ""})            # Vc/Ic are not consumed by loop AB
    ab = _dist(client, ws, ctx, loop="AB", **_strict("primary", "primary", "primary")).json()
    assert ab["status"] == "computed" and ab["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)
    imp_a = _imp(client, ws, ctx, phase="A", **_strict("primary", "primary", "primary")).json()
    assert imp_a["status"] == "computed"
    # ...but a loop that DOES consume them is judged on them
    assert _dist(client, ws, ctx, loop="BC", **_strict("primary", "primary", "primary")).json()["reason_code"] \
        == "voltage_mixed_side_within_quantity"


def test_blocked_strict_locus_reports_the_reason_for_every_point(client):
    ws = "d5a2b1-blocklocus"
    _, ctx = _bay(client, ws, ps={"IA": ""})
    body = _imp_locus(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    assert body["side_conversion"]["block_code"] == "current_side_authority_unavailable"
    assert [(p["status"], p["reason_code"]) for p in body["points"]] == [("needs_configuration", "current_side_authority_unavailable")] * 3
    dist = _dist_locus(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    assert {p["reason_code"] for p in dist["points"]} == {"current_side_authority_unavailable"}


def test_unresolved_channels_report_their_natural_status_not_a_side_block(client):
    ws = "d5a2b1-unres"
    _, ctx = _bay(client, ws, members=("VA", "VB", "VC"))          # no current members
    body = _imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    assert body["status"] != "computed" and body["magnitude_ohm"] is None
    assert body["side_conversion"] is None or body["side_conversion"]["block_code"] is None


# =========================================================================== multi-recording isolation


def test_two_recordings_use_their_own_ct_never_each_others(client):
    ws = "d5a2b1-iso"
    # Recording 1: CT 1000:5 (ratio 200), I = 400 A primary -> 2 A secondary.  Z_sec = 66 V / 2 A = 33 ohm.
    _, ctx1 = _bay(client, ws, v_side="secondary", i_side="primary", ct=(1000.0, 5.0))
    # Recording 2 (same workspace): CT 2000:5 (ratio 400), I = 800 A primary -> 2 A secondary.  Also 33 ohm.
    src2, _ = None, None
    cfg, dat = _comtrade(v_rms=V_SEC, i_rms=800.0, ps={**{n: "S" for n in ("VA", "VB", "VC")}, **{n: "P" for n in ("IA", "IB", "IC")}})
    src2 = _upload(client, ws, cfg, dat, stem="second")
    for auto in client.get(_contexts(ws)).json():
        if auto["id"] != ctx1:
            client.delete(f"{_contexts(ws)}/{auto['id']}")
    st = client.app.state
    for g in st.measurement_group_registry.list_for_source(ws, src2):
        st.measurement_group_registry.remove(ws, g.id)
        st.voltage_group_config_registry.delete(ws, g.id)
        st.current_group_config_registry.delete(ws, g.id)
    ctx2 = _context(client, ws, src2)
    _group(client, ws, src2, KIND_CURRENT, ("IA", "IB", "IC"), "ig-second")
    _ct(client, ws, "ig-second", 2000.0, 5.0)
    one = _imp(client, ws, ctx1, **_strict("secondary", "primary", "secondary")).json()
    two = _imp(client, ws, ctx2, **_strict("secondary", "primary", "secondary")).json()
    assert one["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3) and two["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)
    assert one["side_conversion"]["ct_ratio_applied"] == pytest.approx(200.0)
    assert two["side_conversion"]["ct_ratio_applied"] == pytest.approx(400.0)
    assert two["side_conversion"]["current_group_ids"] == ["ig-second"]


# =========================================================================== legacy path: exact backward compatibility


def test_legacy_same_side_call_matches_the_hand_value_and_the_strict_result(client):
    ws = "d5a2b1-legacy-ss"
    _, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    legacy = _imp(client, ws, ctx, recording_basis="secondary", impedance_basis="secondary").json()
    assert legacy["status"] == "computed" and legacy["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)
    assert legacy["side_conversion"] is None and legacy["recording_basis"] == "secondary"
    strict = _imp(client, ws, ctx, **_strict("secondary", "secondary", "secondary")).json()
    assert strict["magnitude_ohm"] == pytest.approx(legacy["magnitude_ohm"], rel=1e-12)
    assert strict["angle_deg"] == pytest.approx(legacy["angle_deg"], rel=1e-12)


@pytest.mark.parametrize("basis,out,vs,expected", [
    ("primary", "secondary", "primary", Z_SEC),
    ("secondary", "primary", "secondary", Z_PRI),
    ("primary", "primary", "primary", Z_PRI),
])
def test_legacy_single_basis_conversions_are_unchanged_and_agree_with_strict_for_same_side_inputs(client, basis, out, vs, expected):
    ws = f"d5a2b1-legacy-{basis[:1]}{out[:1]}"
    _, ctx = _bay(client, ws, v_side=vs, i_side=vs)
    legacy = _imp(client, ws, ctx, recording_basis=basis, impedance_basis=out,
                  vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S).json()
    assert legacy["magnitude_ohm"] == pytest.approx(expected, rel=1e-3)
    strict = _imp(client, ws, ctx, **_strict(vs, vs, out)).json()
    assert strict["magnitude_ohm"] == pytest.approx(legacy["magnitude_ohm"], rel=1e-9)


def test_legacy_distance_and_locus_are_unchanged(client):
    ws = "d5a2b1-legacy-dist"
    _, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    d = _dist(client, ws, ctx, recording_basis="primary", impedance_basis="secondary",
              vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S).json()
    assert d["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3) and d["side_conversion"] is None
    loc = _dist_locus(client, ws, ctx, recording_basis="primary", impedance_basis="primary").json()
    assert loc["side_conversion"] is None and all(p["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3) for p in loc["points"])


def test_legacy_mixed_side_error_is_the_documented_defect_strict_mode_fixes(client):
    """Characterisation, not an endorsement: legacy cannot represent V primary / I secondary. Strict mode can."""
    ws = "d5a2b1-legacy-mixed"
    _, ctx = _bay(client, ws, v_side="primary", i_side="secondary")
    legacy = _imp(client, ws, ctx, recording_basis="primary", impedance_basis="secondary",
                  vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S).json()
    assert legacy["magnitude_ohm"] == pytest.approx(33000.0 * 200.0 / 1000.0, rel=1e-3)   # 6 600 ohm, wrong by the CT ratio
    strict = _imp(client, ws, ctx, **_strict("primary", "secondary", "secondary")).json()
    assert strict["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)


def test_recording_basis_stays_required_on_the_legacy_path_with_the_same_422(client):
    ws = "d5a2b1-422"
    _, ctx = _bay(client, ws)
    missing_basis = _imp(client, ws, ctx, impedance_basis="secondary")
    missing_out = _imp(client, ws, ctx, recording_basis="secondary")
    assert missing_basis.status_code == missing_out.status_code == 422
    a, b = missing_basis.json()["detail"][0], missing_out.json()["detail"][0]
    assert a["loc"] == ["query", "recording_basis"] and b["loc"] == ["query", "impedance_basis"]
    assert {k: v for k, v in a.items() if k != "loc"} == {k: v for k, v in b.items() if k != "loc"}   # identical error shape
    for route in (_imp_locus, _dist, _dist_locus):
        assert route(client, ws, ctx, impedance_basis="secondary").status_code == 422


def test_unknown_context_is_still_404_in_strict_mode(client):
    assert _imp(client, "d5a2b1-404", "nope", **_strict("primary", "primary", "primary")).status_code == 404
