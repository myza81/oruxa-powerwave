"""D5A-2B2C-1A final hardening (owner review of `a6adcbd`).

A. A calculated current channel stays safely blocked, says plainly that calculated-channel measurement-side support is not
   available yet, offers nothing to configure, keeps its identity (Related Waveforms) and is never modified; the legacy
   basis cannot be used to get around it.
B. A Secondary current is calculated without a CT whenever the side is authoritative, whatever the state of the CT; a
   Primary current without a usable CT of its own group keeps blocking.
C. A Current group with mixed P/S declarations blocks until an engineer resolves it, then is consumable, and the original
   declarations and the discrepancy warning are retained, never rewritten.
D. A missing CT is explained when another Current group of the recording holds one, and that CT is never borrowed.

Real app, real COMTRADE uploads. Expected values are hand-derived: CT 1000:5, 400 A Primary -> 400 * 5 / 1000 = 2.0 A.
"""

from __future__ import annotations

import json

import pytest

from app.domain.measurement_group import KIND_CURRENT
from tests.test_d5a2a_protection_instrument_context_api import _contexts, _ct, _group
from tests.test_d5a_2b2c_1a_overcurrent_unified_side import (  # noqa: F401  (client is the shared fixture)
    CT_P, CT_S, I3, I_PRI, I_SEC, NUMBERS, _bay, _blocked, _computed, _input, _oc, _recording, _result, _ws, client,
)
from tests.test_d5a_ui_002_group_measurement_side import _gv, _put, _set_rec


def _calculated_current_context(client, ws, src, *, name="IA_scaled"):
    """A calculated current channel (IA x 1.0) as the only current of its own Engineering Context."""
    created = client.post(f"/api/v1/workspaces/{ws}/calculated-channels", json={
        "name": name, "operation": "multiply_constant", "parameters": {"constant": 1.0},
        "inputs": [{"kind": "source", "source_id": src, "channel_name": "ZBAY_IA"}]})
    assert created.status_code == 201, created.text
    calc_id = created.json()["id"]
    context = client.post(_contexts(ws), json={"display_name": "calculated bay", "status": "manual", "members": [
        {"channel_ref": {"kind": "calculated", "calculated_channel_id": calc_id}, "phase": "A", "phase_source": "engineer_confirmed"}]})
    assert context.status_code == 201, context.text
    return calc_id, context.json()["id"]


def _calculated_list(client, ws):
    return client.get(f"/api/v1/workspaces/{ws}/calculated-channels").json()


# =========================================================================== A. calculated current channels


def test_a_calculated_current_is_blocked_with_an_explicit_not_available_yet_reason(client):
    ws = _ws()
    src = _recording(client, ws, i="primary")
    calc_id, ctx = _calculated_current_context(client, ws, src)
    body = _result(client, ws, ctx)
    assert body["status"] == "needs_configuration" and body["reason_code"] == "calculated_channel_side_unavailable"
    assert all(body[k] is None for k in NUMBERS), body
    message = body["message"]
    assert "calculated channels is not available yet" in message and "nothing to set there" in message
    assert calc_id in message                                                      # names the channel it is about
    assert "Measurement Group" not in message and "Configure" not in message      # nothing to configure is suggested
    assert body["measurement_group_id"] is None and body["measurement_side"] is None and body["ct_authority"] is None


def test_the_report_for_a_calculated_current_has_no_group_side_ct_or_configure_target(client):
    ws = _ws()
    src = _recording(client, ws, i="primary")
    calc_id, ctx = _calculated_current_context(client, ws, src)
    report = _input(client, ws, ctx)
    assert (report["status"], report["reason_code"]) == ("needs_configuration", "calculated_channel_side_unavailable")
    assert report["measurement_group_id"] is None and report["measurement_group_name"] is None
    assert report["measurement_side"] is None and report["ct"] is None and report["conversion"] is None
    assert report["channel_ref"] == {"kind": "calculated", "source_id": None, "channel_name": None, "calculated_channel_id": calc_id}
    assert report["channel_unit"] == "A"                                           # identity and unit kept: Related Waveforms


def test_a_blocked_calculated_current_keeps_its_identity_for_related_waveforms(client):
    ws = _ws()
    src = _recording(client, ws, i="primary")
    calc_id, ctx = _calculated_current_context(client, ws, src)
    body = _result(client, ws, ctx)
    assert body["channel_ref"] == {"kind": "calculated", "source_id": None, "channel_name": None, "calculated_channel_id": calc_id}
    assert body["measured_rms_current_unit"] == "A"


@pytest.mark.parametrize("extra", [
    {"recording_basis": "secondary"}, {"recording_basis": "primary", "ct_primary": CT_P, "ct_secondary": CT_S},
    {"ct_primary": CT_P, "ct_secondary": CT_S},
])
def test_the_legacy_basis_and_ct_cannot_get_around_the_calculated_channel_block(client, extra):
    ws = _ws()
    src = _recording(client, ws, i="primary")
    _calc_id, ctx = _calculated_current_context(client, ws, src)
    body = _result(client, ws, ctx, **extra)
    assert (body["status"], body["reason_code"]) == ("needs_configuration", "calculated_channel_side_unavailable")
    assert all(body[k] is None for k in NUMBERS), body


def test_evaluating_a_calculated_current_never_deletes_or_modifies_calculated_channels_or_side_configuration(client):
    ws = _ws()
    src = _recording(client, ws, i="primary")
    _bay(client, ws, src)                                                          # groups, CT and a source bay exist too
    calc_id, ctx = _calculated_current_context(client, ws, src)
    before = json.dumps(_calculated_list(client, ws), sort_keys=True)
    state = client.app.state
    registries = (len(_calculated_list(client, ws)), state.measurement_side_registry.count(),
                  len(state.measurement_group_registry.list_for_workspace(ws)))
    for _ in range(3):
        _result(client, ws, ctx)
        _input(client, ws, ctx)
        _result(client, ws, ctx, recording_basis="primary", ct_primary=CT_P, ct_secondary=CT_S)
    assert json.dumps(_calculated_list(client, ws), sort_keys=True) == before                # same channels, byte for byte
    assert [c["id"] for c in _calculated_list(client, ws)] == [calc_id]
    assert (len(_calculated_list(client, ws)), state.measurement_side_registry.count(),
            len(state.measurement_group_registry.list_for_workspace(ws))) == registries


def test_a_source_current_beside_a_calculated_one_is_unaffected(client):
    ws = _ws()
    src = _recording(client, ws, i="primary")
    ctx, _gv_id, _gi = _bay(client, ws, src)
    _calculated_current_context(client, ws, src)
    _computed(_result(client, ws, ctx), relay=2.0, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))


# =========================================================================== B. Secondary needs no CT; Primary does


def _ct_states():
    """How a Current group can fail to hold a usable CT."""
    return ["no_group", "not_configured", "untrusted_authority", "invalid_pair"]


def _prepare_ct_state(client, ws, src, state):
    """Context + Current group in the requested CT state. Returns (ctx, group_id or None)."""
    from app.domain.measurement_group import KIND_VOLTAGE
    ctx = _context_for(client, ws, src)
    if state == "no_group":
        return ctx, None
    _group(client, ws, src, KIND_CURRENT, I3, "ig")
    if state == "untrusted_authority":
        _ct(client, ws, "ig", CT_P, CT_S, authority="engineer_unverified")
    elif state == "invalid_pair":
        _ct(client, ws, "ig", 0.0, CT_S)
    return ctx, "ig"


def _context_for(client, ws, src):
    from tests.test_d5a2b1_independent_side_conversion import _context
    return _context(client, ws, src)


@pytest.mark.parametrize("state", _ct_states())
def test_a_secondary_current_is_calculated_whatever_the_state_of_the_ct(client, state):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_SEC, i="secondary", v="secondary")
    ctx, _gid = _prepare_ct_state(client, ws, src, state)
    _computed(_result(client, ws, ctx), relay=2.0, side="secondary", authority="recording_channel_declared")
    report = _input(client, ws, ctx)
    assert (report["status"], report["conversion"], report["reason_code"]) == ("ready", "none", None)
    assert report["ct"]["consumable"] is False                                     # no usable CT, and nothing is flagged
    # no CT appears as an applied CT anywhere in the result
    result = _result(client, ws, ctx)
    assert (result["ct_primary"], result["ct_secondary"], result["ct_authority"]) == (None, None, None)


@pytest.mark.parametrize("state", _ct_states())
def test_a_primary_current_without_a_usable_ct_of_its_own_group_still_blocks(client, state):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gid = _prepare_ct_state(client, ws, src, state)
    for extra in ({}, {"recording_basis": "primary"}, {"recording_basis": "primary", "ct_primary": CT_P, "ct_secondary": CT_S}):
        body = _result(client, ws, ctx, **extra)
        _blocked(body, "invalid_ct_values")
        assert body["measurement_side"] == "primary"
    report = _input(client, ws, ctx)
    assert (report["status"], report["reason_code"], report["conversion"]) == ("needs_configuration", "invalid_ct_values", None)


def test_the_secondary_side_is_what_removes_the_ct_requirement_and_the_primary_side_restores_it(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_SEC, i="none", v="none")
    ctx, _gv_id, _gi = _bay(client, ws, src, ct=None)
    _set_rec(client, ws, src, "secondary")
    _computed(_result(client, ws, ctx), relay=2.0, side="secondary", authority="engineer_recording_correction")
    _set_rec(client, ws, src, "primary")
    _blocked(_result(client, ws, ctx), "invalid_ct_values")
    _set_rec(client, ws, src, "secondary")
    _computed(_result(client, ws, ctx), relay=2.0, side="secondary", authority="engineer_recording_correction")


# =========================================================================== C. mixed declarations and engineer correction


def _mixed(client, ws):
    """One Current group declaring IA Primary, IB Secondary, IC Primary; 400 A recorded."""
    src = _recording(client, ws, i_rms=I_PRI, i="primary", ps={"IB": "S"})
    ctx, _gv_id, gi = _bay(client, ws, src)
    return src, ctx, gi


def _declared(client, ws, src):
    body = client.get(f"/api/v1/workspaces/{ws}/sources/{src}/channels").json()
    return {c["name"]: c["measurement_side"] for c in body["analog_channels"] if c["name"].startswith("ZBAY_I")}


ORIGINAL = {"ZBAY_IA": "primary", "ZBAY_IB": "secondary", "ZBAY_IC": "primary"}


def test_a_group_with_mixed_declarations_blocks_every_phase_until_resolved(client):
    ws = _ws()
    src, ctx, gi = _mixed(client, ws)
    assert _declared(client, ws, src) == ORIGINAL
    for phase in ("A", "B", "C"):
        body = _result(client, ws, ctx, phase)
        _blocked(body, "measurement_side_conflict")
        assert gi in body["message"]
        report = _input(client, ws, ctx, phase)
        assert (report["status"], report["reason_code"]) == ("needs_configuration", "measurement_side_conflict")
    assert _gv(client, ws, src, gi)["status"] == "conflict"


def test_an_engineer_group_correction_makes_it_consumable_and_the_declarations_and_warning_are_retained(client):
    ws = _ws()
    src, ctx, gi = _mixed(client, ws)
    _put(client, ws, src, gi, "primary")                                           # the engineer resolves the group
    for phase in ("A", "B", "C"):
        _computed(_result(client, ws, ctx, phase), relay=2.0, side="primary", authority="engineer_group_override", ct=(CT_P, CT_S))
    # the original declarations are untouched ...
    assert _declared(client, ws, src) == ORIGINAL
    group = _gv(client, ws, src, gi)
    declared = {c["channel_name"]: c["declared_side"] for c in group["channels"]}
    assert declared == ORIGINAL
    # ... and the discrepancy is disclosed, for exactly the channel that disagrees
    assert [(o["channel_name"], o["declared_side"], o["effective_side"]) for o in group["overridden_declarations"]] == [
        ("ZBAY_IB", "secondary", "primary")]
    assert "GROUP_OVERRIDE_OVERRIDES_DECLARATION" in {d["code"] for c in group["channels"] for d in c["diagnostics"]}
    # the Overcurrent report carries the same evidence for the phase whose channel disagrees, and none for the others
    b = _input(client, ws, ctx, "B")["measurement_side"]
    assert (b["effective_side"], b["declared_side"], b["authority"]) == ("primary", "secondary", "engineer_group_override")
    assert "GROUP_OVERRIDE_OVERRIDES_DECLARATION" in {d["code"] for d in b["diagnostics"]}
    a = _input(client, ws, ctx, "A")["measurement_side"]
    assert a["declared_side"] == "primary" and "GROUP_OVERRIDE_OVERRIDES_DECLARATION" not in {d["code"] for d in a["diagnostics"]}


def test_a_recording_wide_correction_also_makes_it_consumable_and_retains_the_evidence(client):
    ws = _ws()
    src, ctx, gi = _mixed(client, ws)
    _set_rec(client, ws, src, "primary", "IB's flag is wrong")
    for phase in ("A", "B", "C"):
        _computed(_result(client, ws, ctx, phase), relay=2.0, side="primary", authority="engineer_recording_correction", ct=(CT_P, CT_S))
    assert _declared(client, ws, src) == ORIGINAL
    b = _input(client, ws, ctx, "B")["measurement_side"]
    assert (b["declared_side"], b["effective_side"]) == ("secondary", "primary")
    assert "ENGINEER_CORRECTION_OVERRIDES_DECLARATION" in {d["code"] for d in b["diagnostics"]}


def test_removing_the_correction_restores_the_conflict_and_the_declarations_never_moved(client):
    ws = _ws()
    src, ctx, gi = _mixed(client, ws)
    _set_rec(client, ws, src, "primary")
    _computed(_result(client, ws, ctx, "B"), relay=2.0, side="primary", authority="engineer_recording_correction", ct=(CT_P, CT_S))
    _set_rec(client, ws, src, None)
    assert _declared(client, ws, src) == ORIGINAL
    _blocked(_result(client, ws, ctx, "B"), "measurement_side_conflict")


def test_a_secondary_correction_of_a_mixed_group_is_consumable_without_a_ct(client):
    ws = _ws()
    src, ctx, gi = _mixed(client, ws)
    _put(client, ws, src, gi, "secondary")
    for phase in ("A", "B", "C"):
        _computed(_result(client, ws, ctx, phase), relay=I_PRI, side="secondary", authority="engineer_group_override")


# =========================================================================== D. a missing CT is explained, never borrowed


def test_a_missing_ct_names_another_group_that_holds_one_and_never_borrows_it(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx = _context_for(client, ws, src)
    _group(client, ws, src, KIND_CURRENT, ("IA",), "ig-a")
    _group(client, ws, src, KIND_CURRENT, ("IB", "IC"), "ig-bc")
    _ct(client, ws, "ig-bc", CT_P, CT_S)
    body = _result(client, ws, ctx, "A")
    _blocked(body, "invalid_ct_values")
    assert "CT is not configured for the Current Measurement Group 'ig-a'" in body["message"]
    assert "A CT of 1000 A / 5 A is configured on 'ig-bc'" in body["message"] and "never borrowed" in body["message"]
    assert body["measurement_group_id"] == "ig-a" and all(body[k] is None for k in NUMBERS)
    _computed(_result(client, ws, ctx, "B"), relay=2.0, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))


def test_no_hint_is_given_when_no_other_group_holds_a_ct(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx = _context_for(client, ws, src)
    _group(client, ws, src, KIND_CURRENT, ("IA",), "ig-a")
    _group(client, ws, src, KIND_CURRENT, ("IB", "IC"), "ig-bc")
    body = _result(client, ws, ctx, "A")
    _blocked(body, "invalid_ct_values")
    assert "is configured on" not in body["message"] and "never borrowed" not in body["message"]


def test_the_hint_never_looks_at_another_recording(client):
    ws = _ws()
    s1 = _recording(client, ws, i_rms=I_PRI, i="primary", stem="r1")
    s2 = _recording(client, ws, i_rms=I_PRI, i="primary", stem="r2")
    _c1, _v1, _g1 = _bay(client, ws, s1, ct=(CT_P, CT_S), tag="r1")               # recording 1 has a CT
    ctx2 = _context_for(client, ws, s2)
    _group(client, ws, s2, KIND_CURRENT, I3, "r2-i")                              # recording 2's group has none
    body = _result(client, ws, ctx2)
    _blocked(body, "invalid_ct_values")
    assert "is configured on" not in body["message"]


# =========================================================================== E. coverage kept from the retired D5A-OC-001 UI tests


@pytest.mark.parametrize("declared,asserted,i_rms,wrong_number", [
    ("primary", "secondary", I_PRI, I_PRI),             # applying no CT to a Primary current would show 400 A
    ("secondary", "primary", I_SEC, I_SEC * CT_S / CT_P),   # applying the CT to a Secondary current would show 0.01 A
])
def test_a_legacy_basis_that_contradicts_the_declared_side_is_rejected_in_both_directions(client, declared, asserted, i_rms, wrong_number):
    ws = _ws()
    src = _recording(client, ws, i_rms=i_rms, i=declared, v=declared)
    ctx, _gv_id, _gi = _bay(client, ws, src)
    body = _result(client, ws, ctx, recording_basis=asserted, ct_primary=CT_P, ct_secondary=CT_S)
    _blocked(body, "recording_basis_contradicts_measurement_side")
    assert body["relay_secondary_current"] is None                                  # the misleading number is never produced
    assert wrong_number not in [body[k] for k in NUMBERS]
    # the agreeing assertion raises nothing and gives the authoritative number
    agreeing = _result(client, ws, ctx, recording_basis=declared)
    assert agreeing["status"] == "computed" and agreeing["relay_secondary_current"] == pytest.approx(2.0, rel=1e-3)
