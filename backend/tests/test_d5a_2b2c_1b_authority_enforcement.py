"""D5A-2B2C-1B: backend enforcement of the unified measurement side for recorded Impedance and Distance Protection.

Direct API clients cannot choose the side or the transformer ratio of a recorded calculation: Recording Details does. The legacy
request parameters (`recording_basis`, `voltage_side`, `current_side`, `vt_*`, `ct_*`) are validated ASSERTIONS only. These tests
pin the contract, the reason-code matrix, the no-bypass guarantee (omitting parameters never falls back to the legacy path), the
group-ownership rule for CT/VT, request/recording isolation and the read-only `protection-recorded-input` report.
"""

from __future__ import annotations

import pytest

from app.services import independent_side_service
from tests.test_d5a2a_protection_instrument_context_api import _contexts, _ct, _group, _vt
from tests.test_d5a2b1_independent_side_conversion import (  # noqa: F401  (client is the shared fixture)
    CT_P, CT_S, I_PRI, I_SEC, V_PRI, V_SEC, VT_P, VT_S, _ALL, _bay, _comtrade, _context, _dist, _dist_locus, _imp, _imp_locus, _upload,
    client,
)
from tests.test_d5a_ui_002_group_measurement_side import _put, _set_rec

SIDES = ("primary", "secondary")


def _blocked(body, code, quantity=None):
    assert body["status"] == "needs_configuration", body
    assert body["reason_code"] == code, body
    for key in ("magnitude_ohm", "resistance_ohm", "reactance_ohm", "angle_deg"):
        assert body[key] is None, (key, body)                     # never a fabricated zero / infinite / valid impedance
    info = body["side_conversion"]
    assert info["block_code"] == code
    if quantity is not None:
        assert info["block_quantity"] == quantity
    return info


def _both(client, ws, ctx, **params):
    """The four recorded endpoints with identical request parameters: (impedance, impedance locus pts, distance, distance locus pts)."""
    return (_imp(client, ws, ctx, **params).json(), _imp_locus(client, ws, ctx, **params).json(),
            _dist(client, ws, ctx, **params).json(), _dist_locus(client, ws, ctx, **params).json())


def _report(client, ws, ctx, analysis="impedance", **params):
    q = {"analysis": analysis, "impedance_basis": "primary", **params}
    q.setdefault("phase" if analysis == "impedance" else "loop", "A" if analysis == "impedance" else "AB")
    resp = client.get(f"{_contexts(ws)}/{ctx}/protection-recorded-input", params=q)
    assert resp.status_code == 200, resp.text
    return resp.json()


# =========================================================================== legacy parameters are validated assertions only


@pytest.mark.parametrize("vs,cs", [(v, c) for v in SIDES for c in SIDES])
def test_matching_assertions_cause_no_extra_conversion(client, vs, cs):
    """Asserting exactly what Recording Details says changes nothing (same numbers, same conversions)."""
    ws = f"1b-assert-ok-{vs[:1]}{cs[:1]}"
    _src, ctx = _bay(client, ws, v_side=vs, i_side=cs)
    for out in SIDES:
        plain = _imp(client, ws, ctx, impedance_basis=out).json()
        asserted = _imp(client, ws, ctx, impedance_basis=out, voltage_side=vs, current_side=cs).json()
        assert plain["status"] == asserted["status"] == "computed"
        for key in ("magnitude_ohm", "resistance_ohm", "reactance_ohm", "angle_deg"):
            assert asserted[key] == plain[key]
        assert asserted["side_conversion"] == plain["side_conversion"]
        if vs == cs:
            assert _imp(client, ws, ctx, impedance_basis=out, recording_basis=vs).json()["magnitude_ohm"] == plain["magnitude_ohm"]


@pytest.mark.parametrize("truth,wrong", [("primary", "secondary"), ("secondary", "primary")])
def test_a_wrong_voltage_side_assertion_blocks_in_both_directions(client, truth, wrong):
    ws = f"1b-assert-v-{truth[:1]}"
    _src, ctx = _bay(client, ws, v_side=truth, i_side=truth)
    for body in _both(client, ws, ctx, impedance_basis="primary", voltage_side=wrong)[::2]:
        info = _blocked(body, "voltage_side_contradicts_recording", "voltage")
        assert info["block_detail"]["asserted_side"] == wrong and info["block_detail"]["effective_side"] == truth
    for point in _imp_locus(client, ws, ctx, impedance_basis="primary", voltage_side=wrong).json()["points"]:
        assert point["reason_code"] == "voltage_side_contradicts_recording" and point["magnitude_ohm"] is None


@pytest.mark.parametrize("truth,wrong", [("primary", "secondary"), ("secondary", "primary")])
def test_a_wrong_current_side_assertion_blocks_in_both_directions(client, truth, wrong):
    ws = f"1b-assert-i-{truth[:1]}"
    _src, ctx = _bay(client, ws, v_side=truth, i_side=truth)
    for body in _both(client, ws, ctx, impedance_basis="secondary", current_side=wrong)[::2]:
        _blocked(body, "current_side_contradicts_recording", "current")
    for point in _dist_locus(client, ws, ctx, impedance_basis="secondary", current_side=wrong).json()["points"]:
        assert point["reason_code"] == "current_side_contradicts_recording" and point["magnitude_ohm"] is None


def test_the_legacy_recording_basis_is_checked_against_both_quantities(client):
    ws = "1b-assert-rb"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="secondary")       # a mixed bay: no single recording basis is true
    for basis in SIDES:
        body = _imp(client, ws, ctx, impedance_basis="primary", recording_basis=basis).json()
        assert body["status"] == "needs_configuration" and body["reason_code"] in (
            "voltage_side_contradicts_recording", "current_side_contradicts_recording")
        assert body["magnitude_ohm"] is None
    assert _imp(client, ws, ctx, impedance_basis="primary").json()["status"] == "computed"      # the bay itself is fine


def test_an_assertion_is_judged_against_the_engineer_setting_not_the_declaration(client):
    """The recorder's flags say Primary; the engineer set the group to Secondary. Echoing the FLAG is the contradiction."""
    ws = "1b-assert-eng"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    _put(client, ws, src, f"vg-{src}", "secondary")
    _blocked(_imp(client, ws, ctx, impedance_basis="primary", voltage_side="primary").json(),
             "voltage_side_contradicts_recording", "voltage")
    body = _imp(client, ws, ctx, impedance_basis="primary", voltage_side="secondary").json()
    assert body["status"] == "computed" and body["side_conversion"]["voltage_side"] == "secondary"


@pytest.mark.parametrize("params,code", [
    ({"voltage_side": "sideways"}, "invalid_voltage_side"),
    ({"current_side": "up"}, "invalid_current_side"),
    ({"recording_basis": "both"}, "invalid_recording_basis"),
    ({"impedance_basis": "ohms"}, "invalid_impedance_basis"),
])
def test_invalid_side_values_are_refused_with_a_reason(client, params, code):
    ws = f"1b-invalid-{code}"
    _src, ctx = _bay(client, ws)
    body = _imp(client, ws, ctx, **{"impedance_basis": "primary", **params}).json()
    assert body["status"] == "needs_configuration" and body["reason_code"] == code and body["magnitude_ohm"] is None


def test_omitting_every_legacy_parameter_never_falls_back_to_a_request_side(client):
    """The old bypass: no voltage_side/current_side -> the request basis and ratios decided. Now Recording Details always does."""
    ws = "1b-no-bypass"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")      # 66 V and 2 A; flags truthful
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)
    assert body["side_conversion"]["mode"] == "independent_sides"
    # Even a request that tries to steer the old path with a basis and ratios cannot change what the recording says.
    steered = _imp(client, ws, ctx, impedance_basis="primary", recording_basis="primary",
                   vt_primary=1, vt_secondary=1, ct_primary=1, ct_secondary=1).json()
    assert steered["status"] == "needs_configuration" and steered["magnitude_ohm"] is None
    # Distance and both loci obey the same rule.
    assert _dist(client, ws, ctx, impedance_basis="primary").json()["side_conversion"]["mode"] == "independent_sides"
    assert _imp_locus(client, ws, ctx, impedance_basis="primary").json()["side_conversion"]["mode"] == "independent_sides"
    assert _dist_locus(client, ws, ctx, impedance_basis="primary").json()["side_conversion"]["mode"] == "independent_sides"


# =========================================================================== request ratios are assertions too


def test_an_equal_ratio_assertion_is_accepted_even_with_a_different_pair(client):
    ws = "1b-ratio-equal"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    plain = _imp(client, ws, ctx, impedance_basis="primary").json()
    asserted = _imp(client, ws, ctx, impedance_basis="primary", vt_primary=220000, vt_secondary=220, ct_primary=2000, ct_secondary=10).json()
    assert asserted["status"] == "computed" and asserted["magnitude_ohm"] == plain["magnitude_ohm"]
    assert (asserted["vt_primary"], asserted["vt_secondary"]) == (VT_P, VT_S)         # the AUTHORITATIVE pair is echoed, not the request's


@pytest.mark.parametrize("params,code,quantity", [
    ({"vt_primary": 66000, "vt_secondary": 110}, "request_vt_conflicts_with_authority", "voltage"),
    ({"vt_primary": 110, "vt_secondary": 110000}, "request_vt_conflicts_with_authority", "voltage"),          # reversed
    ({"ct_primary": 400, "ct_secondary": 5}, "request_ct_conflicts_with_authority", "current"),
    ({"ct_primary": 5, "ct_secondary": 1000}, "request_ct_conflicts_with_authority", "current"),              # reversed
    ({"vt_primary": 110000}, "request_vt_invalid", "voltage"),                                                # half a pair
    ({"ct_secondary": 5}, "request_ct_invalid", "current"),
    ({"vt_primary": 0, "vt_secondary": 110}, "request_vt_invalid", "voltage"),
    ({"ct_primary": -1000, "ct_secondary": 5}, "request_ct_invalid", "current"),
])
def test_a_wrong_request_ratio_blocks_when_a_conversion_needs_it(client, params, code, quantity):
    ws = f"1b-ratio-wrong-{code[:10]}-{quantity}-{abs(hash(str(params))) % 9999}"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")      # both must convert to a Primary output
    for body in _both(client, ws, ctx, impedance_basis="primary", **params)[::2]:
        _blocked(body, code, quantity)


def test_request_ratios_are_ignored_where_no_conversion_is_needed(client):
    """Nothing converts (everything already on the output side), so an unnecessary -- even absurd -- ratio assertion is harmless."""
    ws = "1b-ratio-unneeded"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    body = _imp(client, ws, ctx, impedance_basis="primary", vt_primary=1, vt_secondary=1, ct_primary=7, ct_secondary=3).json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)
    assert body["side_conversion"]["vt_ratio_applied"] is None and body["side_conversion"]["ct_ratio_applied"] is None
    # ... but a ratio the conversion DOES need is still checked (CT converts here, VT does not)
    mixed_ws = "1b-ratio-half-needed"
    _s, mixed_ctx = _bay(client, mixed_ws, v_side="primary", i_side="secondary")
    bad = _imp(client, mixed_ws, mixed_ctx, impedance_basis="primary", vt_primary=1, vt_secondary=1, ct_primary=1000, ct_secondary=5).json()
    assert bad["status"] == "computed"                                               # the absurd VT is not needed; the CT matches
    wrong_ct = _imp(client, mixed_ws, mixed_ctx, impedance_basis="primary", ct_primary=1, ct_secondary=1).json()
    _blocked(wrong_ct, "request_ct_conflicts_with_authority", "current")


@pytest.mark.parametrize("drop,needed_for,code,quantity", [
    ("vt", dict(v_side="secondary", i_side="primary"), "vt_authority_unavailable", "voltage"),
    ("ct", dict(v_side="primary", i_side="secondary"), "ct_authority_unavailable", "current"),
])
def test_a_request_ratio_cannot_stand_in_for_a_missing_authoritative_ratio(client, drop, needed_for, code, quantity):
    ws = f"1b-ratio-missing-{drop}"
    src, ctx = _bay(client, ws, **needed_for)
    registry = client.app.state.voltage_group_config_registry if drop == "vt" else client.app.state.current_group_config_registry
    registry.delete(ws, f"{'vg' if drop == 'vt' else 'ig'}-{src}")
    request = dict(vt_primary=VT_P, vt_secondary=VT_S) if drop == "vt" else dict(ct_primary=CT_P, ct_secondary=CT_S)
    for body in _both(client, ws, ctx, impedance_basis="primary", **request)[::2]:
        _blocked(body, code, quantity)
    for point in _imp_locus(client, ws, ctx, impedance_basis="primary", **request).json()["points"]:
        assert point["reason_code"] == code and point["magnitude_ohm"] is None


@pytest.mark.parametrize("authority,note", [("manual", None)])
def test_an_untrusted_or_invalid_group_ratio_is_not_consumed(client, authority, note):
    ws = "1b-ratio-untrusted"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    _vt(client, ws, f"vg-{src}", VT_P, VT_S, authority="not_a_real_authority")
    _blocked(_imp(client, ws, ctx, impedance_basis="primary").json(), "vt_authority_unavailable", "voltage")
    _vt(client, ws, f"vg-{src}", VT_P, VT_S)
    _ct(client, ws, f"ig-{src}", -5.0, 5.0)
    _blocked(_imp(client, ws, ctx, impedance_basis="primary").json(), "ct_authority_unavailable", "current")


# =========================================================================== blockers: the authority is unavailable or ambiguous


def test_an_undeclared_and_uncorrected_side_blocks_every_endpoint(client):
    ws = "1b-undeclared"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={n: "" for n in _ALL})
    for body in _both(client, ws, ctx, impedance_basis="primary")[::2]:
        assert body["status"] == "needs_configuration" and body["reason_code"] in (
            "voltage_side_authority_unavailable", "voltage_side_inferred")
        assert body["magnitude_ohm"] is None
    for points in (_imp_locus(client, ws, ctx, impedance_basis="primary").json()["points"],
                   _dist_locus(client, ws, ctx, impedance_basis="primary").json()["points"]):
        assert len(points) == 3 and all(p["magnitude_ohm"] is None and p["reason_code"] for p in points)


def test_a_voltage_problem_is_reported_for_voltage_and_a_current_problem_for_current(client):
    ws = "1b-which-quantity"
    _src, ctx = _bay(client, ws, ps={"IA": "", "IB": "", "IC": ""})            # voltage declared, current not
    # A declared voltage does not make the current "primary": a recording-level inference is not strict-usable, so it blocks.
    info = _blocked(_imp(client, ws, ctx, impedance_basis="primary").json(), "current_side_inferred", "current")
    assert info["voltage_side"] == "primary" and info["current_side"] is None
    ws2 = "1b-which-quantity-v"
    _s, ctx2 = _bay(client, ws2, ps={"VA": "", "VB": "", "VC": ""})
    info = _blocked(_imp(client, ws2, ctx2, impedance_basis="primary").json(), "voltage_side_inferred", "voltage")
    assert info["current_side"] == "primary" and info["voltage_side"] is None


def test_an_engineer_setting_resolves_what_the_recording_leaves_undefined(client):
    ws = "1b-engineer-fills-gap"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary", ps={n: "" for n in _ALL})
    assert _imp(client, ws, ctx, impedance_basis="primary").json()["status"] == "needs_configuration"
    _set_rec(client, ws, src, "secondary", "recorder did not flag sides")
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)
    assert body["side_conversion"]["voltage_side_authority"] == "engineer_recording_correction"


def test_mixed_declarations_inside_one_measurement_group_block_until_the_engineer_resolves_them(client):
    ws = "1b-mixed-group"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={"VB": "S"})      # VA/VC primary, VB secondary
    _blocked(_imp(client, ws, ctx, impedance_basis="primary").json(), "voltage_group_side_conflict", "voltage")
    body = _dist(client, ws, ctx, impedance_basis="primary").json()                         # the AB loop consumes VA and VB
    _blocked(body, "voltage_group_side_conflict", "voltage")
    _put(client, ws, src, f"vg-{src}", "primary")                                           # one decision resolves the group
    assert _imp(client, ws, ctx, impedance_basis="primary").json()["status"] == "computed"
    assert _dist(client, ws, ctx, impedance_basis="primary").json()["status"] == "computed"


def test_mixed_sides_across_the_two_legs_of_a_loop_without_groups_are_rejected(client):
    ws = "1b-mixed-legs"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={"VB": "S", "IB": "S"}, groups=False)
    for body, code in ((_dist(client, ws, ctx, impedance_basis="primary").json(), "voltage_mixed_side_within_quantity"),):
        _blocked(body, code, "voltage")
    # The A-phase impedance reads only VA and IA, which agree, so it is not affected by the B-phase disagreement.
    assert _imp(client, ws, ctx, impedance_basis="primary").json()["status"] == "computed"


def test_voltage_and_current_need_not_share_a_side_and_a_group_may_span_contexts(client):
    ws = "1b-independent-quantities"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="secondary")
    assert _dist(client, ws, ctx, impedance_basis="primary").json()["status"] == "computed"
    assert _dist(client, ws, ctx, impedance_basis="secondary").json()["status"] == "computed"


def test_unrelated_unused_channels_never_block_a_recording(client):
    ws = "1b-unrelated"
    _src, ctx = _bay(client, ws, members=("VA", "IA"))
    assert _imp(client, ws, ctx, impedance_basis="primary").json()["status"] == "computed"


def test_unresolved_roles_keep_their_natural_status_not_a_side_block(client):
    ws = "1b-unresolved-role"
    _src, ctx = _bay(client, ws, members=("VA", "VB", "VC"))                               # no current channel in the context
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert body["status"] != "computed" and body["reason_code"] not in (None, "current_side_authority_unavailable")
    assert body["magnitude_ohm"] is None


def test_a_blocked_response_still_identifies_the_consumed_channels(client):
    """Related Waveforms keep working while the calculation is blocked: the resolved channel identities and units stay."""
    ws = "1b-blocked-refs"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={n: "" for n in _ALL})
    imp = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert imp["status"] == "needs_configuration"
    assert imp["voltage_channel_ref"]["channel_name"] == "ZBAY_VA" and imp["current_channel_ref"]["channel_name"] == "ZBAY_IA"
    assert (imp["voltage_unit"], imp["current_unit"]) == ("V", "A")
    dist = _dist(client, ws, ctx, impedance_basis="primary").json()
    assert [dist[k]["channel_name"] for k in ("v1_channel_ref", "v2_channel_ref", "i1_channel_ref", "i2_channel_ref")] == [
        "ZBAY_VA", "ZBAY_VB", "ZBAY_IA", "ZBAY_IB"]
    for point in _imp_locus(client, ws, ctx, impedance_basis="primary").json()["points"]:
        assert point["magnitude_ohm"] is None and point["reason_code"]


def test_a_calculated_channel_is_blocked_because_its_side_is_unresolved_and_is_never_inferred(client, monkeypatch):
    from app.domain.calculated_channel import ChannelRef
    ws = "1b-calculated"
    _src, ctx = _bay(client, ws)
    real = independent_side_service.resolve_analysis_roles

    def with_calculated_voltage(**kw):
        roles, unresolved = real(**kw)
        return [(k, ChannelRef(kind="calculated", calculated_channel_id="calc-1") if k.startswith("V") else r) for k, r in roles], unresolved

    monkeypatch.setattr(independent_side_service, "resolve_analysis_roles", with_calculated_voltage)
    for body in (_imp(client, ws, ctx, impedance_basis="primary").json(), _dist(client, ws, ctx, impedance_basis="primary").json()):
        _blocked(body, "calculated_channel_side_unavailable", "voltage")
    report = _report(client, ws, ctx, impedance_basis="primary")
    assert report["status"] == "needs_configuration" and report["reason_code"] == "calculated_channel_side_unavailable"
    assert report["voltage"]["configure_target"] is None            # no Measurement Group exists to send the engineer to


# =========================================================================== group ownership: CT/VT are never borrowed


def _second_recording(client, ws, first_ctx, *, v_side, i_side, ct=None, with_ct_group=True):
    """A second recording in the SAME workspace (the shared `_bay` clears the workspace, so it cannot be called twice)."""
    cfg, dat = _comtrade(v_rms=V_SEC if v_side == "secondary" else V_PRI, i_rms=I_SEC if i_side == "secondary" else I_PRI,
                         ps={n: ("P" if (v_side if n[0] == "V" else i_side) == "primary" else "S") for n in _ALL})
    src = _upload(client, ws, cfg, dat, stem="second")
    for auto in client.get(_contexts(ws)).json():
        if auto["id"] != first_ctx:
            client.delete(f"{_contexts(ws)}/{auto['id']}")
    st = client.app.state
    for g in st.measurement_group_registry.list_for_source(ws, src):
        st.measurement_group_registry.remove(ws, g.id)
        st.voltage_group_config_registry.delete(ws, g.id)
        st.current_group_config_registry.delete(ws, g.id)
    ctx = _context(client, ws, src)
    _group(client, ws, src, "voltage", ("VA", "VB", "VC"), "vg-second")
    _vt(client, ws, "vg-second", VT_P, VT_S)
    if with_ct_group:
        _group(client, ws, src, "current", ("IA", "IB", "IC"), "ig-second")
        _ct(client, ws, "ig-second", *(ct or (CT_P, CT_S)))
    return src, ctx


def test_two_recordings_in_one_workspace_use_their_own_transformers(client):
    ws = "1b-own-transformers"
    src_a, ctx_a = _bay(client, ws, v_side="secondary", i_side="secondary")
    src_b, ctx_b = _second_recording(client, ws, ctx_a, v_side="secondary", i_side="secondary", ct=(2000.0, 5.0))   # ratio 400, not 200
    assert src_a != src_b
    a = _imp(client, ws, ctx_a, impedance_basis="primary").json()
    b = _imp(client, ws, ctx_b, impedance_basis="primary").json()
    assert a["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)
    assert b["magnitude_ohm"] == pytest.approx(66.0 * 1000.0 / (2.0 * 400.0), rel=1e-3)
    assert (a["ct_primary"], b["ct_primary"]) == (CT_P, 2000.0)
    assert (a["side_conversion"]["current_group_names"], b["side_conversion"]["current_group_names"]) == ([f"ig-{src_a}"], ["ig-second"])


def test_a_recording_without_a_ct_never_borrows_the_ct_of_another_recording(client):
    ws = "1b-no-borrow"
    _src_a, ctx_a = _bay(client, ws, v_side="primary", i_side="secondary")                     # fully configured neighbour
    _src_b, ctx_b = _second_recording(client, ws, ctx_a, v_side="primary", i_side="secondary", with_ct_group=False)
    _blocked(_imp(client, ws, ctx_b, impedance_basis="primary").json(), "ct_authority_unavailable", "current")
    _blocked(_dist(client, ws, ctx_b, impedance_basis="primary").json(), "ct_authority_unavailable", "current")
    assert _imp(client, ws, ctx_a, impedance_basis="primary").json()["status"] == "computed"


def test_the_ct_comes_from_the_group_that_owns_the_consumed_channels_not_an_unrelated_group(client):
    """A second current group (other channels) carries a different CT; it must not influence the bay's calculation."""
    ws = "1b-group-ownership"
    src, ctx = _bay(client, ws, v_side="primary", i_side="secondary", groups=False)
    _group(client, ws, src, "voltage", ("VA", "VB", "VC"), "vg-bay")
    _group(client, ws, src, "current", ("IA", "IB"), "ig-bay")
    _group(client, ws, src, "current", ("IC",), "ig-other")
    _ct(client, ws, "ig-bay", CT_P, CT_S)
    _ct(client, ws, "ig-other", 3000.0, 5.0)
    body = _imp(client, ws, ctx, impedance_basis="primary").json()                                # phase A reads IA only
    assert body["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)
    assert (body["ct_primary"], body["ct_secondary"]) == (CT_P, CT_S)
    assert body["side_conversion"]["current_group_names"] == ["ig-bay"]
    # phase C reads IC, which `ig-other` owns, so it is converted with ITS ratio (600), never the neighbour's 200
    c_phase = _imp(client, ws, ctx, impedance_basis="primary", phase="C").json()
    assert c_phase["side_conversion"]["ct_ratio_applied"] == pytest.approx(600.0)


def test_workspaces_are_isolated(client):
    ws1, ws2 = "1b-iso-1", "1b-iso-2"
    src1, ctx1 = _bay(client, ws1, v_side="primary", i_side="primary")
    src2, ctx2 = _bay(client, ws2, v_side="primary", i_side="primary")
    _put(client, ws1, src1, f"vg-{src1}", "secondary")                                            # only workspace 1 is re-labelled
    assert _imp(client, ws1, ctx1, impedance_basis="primary").json()["side_conversion"]["voltage_side"] == "secondary"
    assert _imp(client, ws2, ctx2, impedance_basis="primary").json()["side_conversion"]["voltage_side"] == "primary"
    assert _imp(client, ws2, ctx2, impedance_basis="primary").json()["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)


# =========================================================================== one authority evaluation per request


def test_every_request_evaluates_the_authority_once_and_a_locus_shares_one_snapshot(client, monkeypatch):
    ws = "1b-single-eval"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    calls = []
    real = independent_side_service.evaluate_recorded_input
    monkeypatch.setattr(independent_side_service, "evaluate_recorded_input", lambda **kw: calls.append(kw["analysis"]) or real(**kw))
    from app.api.v1 import engineering_contexts as routes
    monkeypatch.setattr(routes, "evaluate_recorded_input", independent_side_service.evaluate_recorded_input)
    monkeypatch.setattr(independent_side_service, "resolve_side_plan", lambda **kw: independent_side_service.evaluate_recorded_input(**kw).outcome)
    monkeypatch.setattr(routes, "resolve_side_plan", independent_side_service.resolve_side_plan)
    for call in (lambda: _imp(client, ws, ctx, impedance_basis="primary"),
                 lambda: _imp_locus(client, ws, ctx, impedance_basis="primary", point_count=25),
                 lambda: _dist(client, ws, ctx, impedance_basis="primary"),
                 lambda: _dist_locus(client, ws, ctx, impedance_basis="primary", point_count=25)):
        calls.clear()
        resp = call()
        assert resp.status_code == 200, resp.text
        assert len(calls) == 1, calls          # not once per locus point


# =========================================================================== the read-only report agrees with the calculation


def test_the_report_describes_what_the_calculation_consumes(client):
    ws = "1b-report"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    report = _report(client, ws, ctx, impedance_basis="primary")
    assert report["status"] == "ready" and report["output_side"] == "primary" and report["reason_code"] is None
    assert (report["voltage_conversion"], report["current_conversion"]) == ("secondary_to_primary", "none")
    volt, cur = report["voltage"], report["current"]
    assert (volt["effective_side"], volt["authority"], volt["declared_sides"]) == ("secondary", "recording_channel_declared", ["secondary"])
    assert (cur["effective_side"], cur["ratio_required"]) == ("primary", False)
    assert volt["ratio_required"] is True and volt["transformer"]["ratio"] == pytest.approx(1000.0)
    assert volt["group_ids"] == [f"vg-{src}"] and cur["group_ids"] == [f"ig-{src}"]
    assert volt["configure_target"] == {"source_id": src, "group_id": f"vg-{src}"}
    assert [c["channel_name"] for c in volt["channels"]] == ["ZBAY_VA"]
    secondary = _report(client, ws, ctx, impedance_basis="secondary")
    assert (secondary["voltage_conversion"], secondary["current_conversion"]) == ("none", "primary_to_secondary")


def test_the_report_and_the_calculation_never_disagree(client):
    ws = "1b-report-agree"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    scenarios = [
        lambda: None,
        lambda: client.app.state.voltage_group_config_registry.delete(ws, f"vg-{src}"),
        lambda: _put(client, ws, src, f"ig-{src}", "primary"),
        lambda: _set_rec(client, ws, src, "secondary"),
    ]
    for step in scenarios:
        step()
        for out in SIDES:
            report = _report(client, ws, ctx, impedance_basis=out)
            body = _imp(client, ws, ctx, impedance_basis=out).json()
            assert (report["status"] == "ready") == (body["status"] == "computed"), (report, body)
            assert report["reason_code"] == body["reason_code"]
            dist_report = _report(client, ws, ctx, analysis="distance_protection", impedance_basis=out)
            dist = _dist(client, ws, ctx, impedance_basis=out).json()
            assert (dist_report["status"] == "ready") == (dist["status"] == "computed")
            assert dist_report["reason_code"] == dist["reason_code"]


def test_the_report_names_the_group_that_can_resolve_a_conflict(client):
    ws = "1b-report-conflict"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={"VB": "S"})
    report = _report(client, ws, ctx, analysis="distance_protection", impedance_basis="primary")
    assert report["status"] == "needs_configuration" and report["reason_code"] == "voltage_group_side_conflict"
    assert report["voltage"]["problem_code"] == "voltage_group_side_conflict"
    assert report["voltage"]["configure_target"] == {"source_id": src, "group_id": f"vg-{src}"}
    assert report["voltage_conversion"] is None and report["current_conversion"] is None
    assert sorted(set(report["voltage"]["declared_sides"])) == ["primary", "secondary"]


def test_the_report_requires_the_phase_or_loop_of_its_analysis(client):
    ws = "1b-report-params"
    _src, ctx = _bay(client, ws)
    for params in ({"analysis": "impedance", "impedance_basis": "primary"},
                   {"analysis": "distance_protection", "impedance_basis": "primary"}):
        assert client.get(f"{_contexts(ws)}/{ctx}/protection-recorded-input", params=params).status_code == 422
    assert client.get(f"{_contexts(ws)}/nope/protection-recorded-input",
                      params={"analysis": "impedance", "phase": "A", "impedance_basis": "primary"}).status_code == 404


# =========================================================================== the specific, actionable blocker messages


def test_a_channel_outside_any_measurement_group_is_named_and_the_group_to_add_it_to_is_stated(client):
    ws = "1b-msg-nogroup"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="primary", groups=False)
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    _blocked(body, "vt_authority_unavailable", "voltage")
    assert "ZBAY_VA is not in a Voltage Measurement Group. Add it in Recording Details." in body["message"]
    assert body["message"].startswith("Converting the voltage to the primary side needs its VT from Recording Details.")


def test_an_unconfigured_vt_and_an_unusable_vt_each_get_their_own_message(client):
    ws = "1b-msg-vt"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary", vt=(None, None))
    _vt(client, ws, f"vg-{src}", None, None, authority="not_configured")
    missing = _imp(client, ws, ctx, impedance_basis="primary").json()
    _blocked(missing, "vt_authority_unavailable", "voltage")
    assert f"VT is not configured for 'vg-{src}'. Set the nominal voltage, or the VT primary kV and secondary V, in Recording Details." in missing["message"]
    _vt(client, ws, f"vg-{src}", -110000.0, 110.0)
    unusable = _imp(client, ws, ctx, impedance_basis="primary").json()
    _blocked(unusable, "vt_authority_unavailable", "voltage")
    assert f"The VT in 'vg-{src}' is not usable" in unusable["message"] and "Correct it in Recording Details." in unusable["message"]


def test_a_nominal_voltage_that_cannot_yield_a_vt_says_why(client):
    ws = "1b-msg-nominal"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    reg = client.app.state.voltage_group_config_registry
    reg.update_fields(ws, f"vg-{src}", nominal_voltage_ll_kv=110.0, update_nominal=True, vt_primary_v=None,
                      vt_secondary_v=None, vt_authority="not_configured", update_vt=True)
    config = reg.get(ws, f"vg-{src}")
    config.manual_conflict_detected = True
    reg.upsert(config)
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    _blocked(body, "vt_authority_unavailable", "voltage")
    assert "cannot be derived from its nominal voltage (110 kV)" in body["message"]
    assert "conflicts with the channel evidence" in body["message"] and "enter the VT" in body["message"]


def test_a_ct_held_by_another_current_group_of_the_recording_is_pointed_out(client):
    ws = "1b-msg-othergroup"
    src, ctx = _bay(client, ws, v_side="primary", i_side="secondary", groups=False)
    _group(client, ws, src, "voltage", ("VA", "VB", "VC"), "vg-bay")
    _group(client, ws, src, "current", ("IA", "IB"), "ig-bay")
    _group(client, ws, src, "current", ("IC",), "ig-other")
    _ct(client, ws, "ig-other", 3000.0, 5.0)                            # only the OTHER group has a CT
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    _blocked(body, "ct_authority_unavailable", "current")
    assert "CT is not configured for 'ig-bay'. Set primary and secondary A in Recording Details." in body["message"]
    assert "A CT of 3000 A / 5 A is configured on 'ig-other', but ZBAY_IA belongs to 'ig-bay'." in body["message"]
    # phase C belongs to the group that HAS the CT, which therefore converts with its own ratio and never the neighbour's
    c_phase = _imp(client, ws, ctx, impedance_basis="primary", phase="C").json()
    assert c_phase["side_conversion"]["ct_ratio_applied"] == pytest.approx(600.0)


def test_a_measurement_group_spanning_several_engineering_contexts_is_not_ambiguous(client):
    """Group membership, not the Engineering Context, is the authority: two contexts of one recording (phase A and phase B) share
    the Voltage group and the Current group, and each converts with that one group's VT/CT -- never a 'which bay' ambiguity."""
    ws = "1b-two-contexts"
    src, ctx_a = _bay(client, ws, v_side="secondary", i_side="secondary", members=("VA", "IA"))
    ctx_b = _context(client, ws, src, members=("VB", "IB"))
    assert ctx_a != ctx_b
    for ctx, phase in ((ctx_a, "A"), (ctx_b, "B")):
        for out in SIDES:
            body = _imp(client, ws, ctx, impedance_basis=out, phase=phase).json()
            assert body["status"] == "computed", body
            assert body["magnitude_ohm"] == pytest.approx(165.0 if out == "primary" else 33.0, rel=1e-3)
            assert body["side_conversion"]["voltage_group_ids"] == [f"vg-{src}"] and body["side_conversion"]["current_group_ids"] == [f"ig-{src}"]
    report = _report(client, ws, ctx_b, impedance_basis="primary", phase="B")
    assert report["status"] == "ready" and report["voltage"]["group_ids"] == [f"vg-{src}"]
