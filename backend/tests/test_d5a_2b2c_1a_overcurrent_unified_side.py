"""D5A-2B2C-1A: recorded Overcurrent consumes the unified effective measurement side of Recording Details.

Level 1 (the recording) and Level 2 (the Current Measurement Group that owns the consumed channel) decide whether the
recorded current is Primary or Secondary; the CT applied to a Primary current is the CT of that same group. The legacy
request parameters (`recording_basis`, `ct_primary`, `ct_secondary`) can no longer decide anything: they are validated
against Recording Details and a contradiction blocks.

Real app, real ASCII-COMTRADE uploads whose per-channel P/S flags are the original recording evidence. Expected values
are derived by hand from the owner's formulas and never read back from the code under test:

    CT 1000 A : 5 A (ratio 200)        recorded 400 A  Primary   ->  400 * 5 / 1000 = 2.0 A relay-secondary
                                       recorded   2 A  Secondary ->  2.0 A (the CT is NOT applied again; a double
                                       conversion would give 2 * 5 / 1000 = 0.01 A)
    IEC standard inverse, TMS 0.1, pickup 1.0 A, relay current 2.0 A  ->  M = 2,  t = 0.1 * 0.14 / (2**0.02 - 1)
"""

from __future__ import annotations

import inspect
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.main import create_app
from app.services.overcurrent_analysis_service import compute_overcurrent_analysis
from app.services.overcurrent_recorded_input import OvercurrentAuthority, evaluate_recorded_current_authority
from tests.test_d5a2a_protection_instrument_context_api import _clear, _contexts, _ct, _group
from tests.test_d5a2b1_independent_side_conversion import _ALL, _comtrade, _context, _upload
from tests.test_d5a_ui_002_group_measurement_side import _gv, _put, _set_g, _set_rec

CT_P, CT_S = 1000.0, 5.0
I_PRI, I_SEC = 400.0, 2.0
RELAY_A = I_PRI * CT_S / CT_P                      # 2.0 A, hand-derived above
IEC_SI_TIME_S = 0.1 * 0.14 / (2.0 ** 0.02 - 1.0)   # M = 2, TMS = 0.1
NUMBERS = (
    "measured_rms_current", "relay_secondary_current", "multiple_of_pickup", "expected_operating_time_seconds",
    "above_pickup_duration_seconds",
)
IA, IB, IC = ("IA",), ("IB",), ("IC",)
I3 = ("IA", "IB", "IC")


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- helpers


def _ws() -> str:
    return f"oc1a-{uuid4().hex[:8]}"


def _recording(client, ws, *, i_rms=I_PRI, i="primary", v="primary", ps=None, stem="oc1a") -> str:
    """One recording; `i`/`v` are the sides its channels DECLARE ('none' = no P/S flag), `i_rms` the recorded current."""
    code = {"primary": "P", "secondary": "S", "none": ""}
    flags = {n: code[v if n[0] == "V" else i] for n in _ALL}
    flags.update(ps or {})
    cfg, dat = _comtrade(v_rms=66000.0, i_rms=i_rms, ps=flags)
    src = _upload(client, ws, cfg, dat, stem=stem)
    _clear(client, ws)                      # drop auto-suggested contexts and groups: each test builds its own
    return src


def _bay(client, ws, src, *, ct=(CT_P, CT_S), gid=None, tag="g"):
    """One bay Context plus one Voltage and one Current group; `ct` configures the Current group (None: no CT)."""
    ctx = _context(client, ws, src)
    gv, gi = gid or f"{tag}-v", gid or f"{tag}-i"
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), gv)
    _group(client, ws, src, KIND_CURRENT, I3, gi)
    if ct is not None:
        _ct(client, ws, gi, *ct)
    return ctx, gv, gi


def _oc(client, ws, ctx, phase="A", **extra):
    q = {"phase": phase, "analysis_time": 1.5, "characteristic_id": "iec_standard_inverse", "tms": 0.1,
         "pickup_current_secondary": 1.0}
    q.update(extra)
    return client.get(f"{_contexts(ws)}/{ctx}/overcurrent", params=q)


def _result(client, ws, ctx, phase="A", **extra):
    resp = _oc(client, ws, ctx, phase, **extra)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _input(client, ws, ctx, phase="A"):
    resp = client.get(f"{_contexts(ws)}/{ctx}/overcurrent-recorded-input", params={"phase": phase})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _computed(body, *, relay, side, authority, ct=None):
    assert body["status"] == "computed", body
    assert body["relay_secondary_current"] == pytest.approx(relay, rel=1e-3), body
    assert body["multiple_of_pickup"] == pytest.approx(relay, rel=1e-3)           # pickup is 1.0 A
    assert body["recording_basis"] == body["measurement_side"] == side
    assert body["measurement_side_authority"] == authority
    assert (body["ct_primary"], body["ct_secondary"]) == (ct if ct else (None, None))
    assert body["reason_code"] is None and body["channel_ref"] is not None


def _blocked(body, reason):
    assert body["status"] == "needs_configuration" and body["reason_code"] == reason, body
    assert all(body[k] is None for k in NUMBERS), body
    assert body["message"]
    # The consumed channel stays identified so its waveform remains available (D5A-OC-001 / Related Waveforms).
    assert body["channel_ref"] is not None and body["measured_rms_current_unit"] == "A", body


def _ct_group_of(body):
    return body["measurement_group_id"]


# =========================================================================== numerical oracles (the four owner examples)


def test_primary_recorded_current_is_converted_once_with_the_ct_of_its_own_group(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gv_id, gi = _bay(client, ws, src)
    body = _result(client, ws, ctx)
    _computed(body, relay=2.0, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))
    assert body["measured_rms_current"] == pytest.approx(400.0, rel=1e-3)
    assert body["expected_operating_time_seconds"] == pytest.approx(IEC_SI_TIME_S, rel=1e-3)
    assert body["measurement_group_id"] == gi and body["ct_authority"] == "manual"


def test_secondary_recorded_current_with_a_ct_is_not_converted_again(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_SEC, i="secondary")
    ctx, _gv_id, _gi = _bay(client, ws, src)                       # the CT exists but must NOT be applied
    body = _result(client, ws, ctx)
    _computed(body, relay=2.0, side="secondary", authority="recording_channel_declared")
    assert body["relay_secondary_current"] != pytest.approx(I_SEC * CT_S / CT_P)    # the 0.01 A double conversion
    assert body["expected_operating_time_seconds"] == pytest.approx(IEC_SI_TIME_S, rel=1e-3)
    assert body["ct_authority"] is None                             # no CT was used


def test_secondary_recorded_current_without_a_ct_is_computed(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_SEC, i="secondary")
    ctx, _gv_id, _gi = _bay(client, ws, src, ct=None)
    _computed(_result(client, ws, ctx), relay=2.0, side="secondary", authority="recording_channel_declared")
    # ... and with no Measurement Group at all
    ws2 = _ws()
    src2 = _recording(client, ws2, i_rms=I_SEC, i="secondary")
    ctx2 = _context(client, ws2, src2)
    _computed(_result(client, ws2, ctx2), relay=2.0, side="secondary", authority="recording_channel_declared")


def test_primary_recorded_current_without_a_ct_blocks_the_conversion(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gv_id, gi = _bay(client, ws, src, ct=None)
    body = _result(client, ws, ctx)
    _blocked(body, "invalid_ct_values")
    assert gi in body["message"] and "Recording Details" in body["message"]
    assert body["measurement_side"] == "primary" and body["measurement_group_id"] == gi
    # A channel in no Current Measurement Group has no CT authority either.
    ws2 = _ws()
    src2 = _recording(client, ws2, i_rms=I_PRI, i="primary")
    ctx2 = _context(client, ws2, src2)
    body2 = _result(client, ws2, ctx2)
    _blocked(body2, "invalid_ct_values")
    assert "not in a Current Measurement Group" in body2["message"] and body2["measurement_group_id"] is None


# =========================================================================== the side comes from Recording Details only


def test_level_2_current_group_secondary_overrides_a_primary_recording(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_SEC, i="primary")           # the recording DECLARES primary ...
    ctx, gv, gi = _bay(client, ws, src)
    _put(client, ws, src, gi, "secondary")                           # ... the engineer says the current group is secondary
    body = _result(client, ws, ctx)
    _computed(body, relay=2.0, side="secondary", authority="engineer_group_override")
    assert body["measurement_group_id"] == gi
    report = _input(client, ws, ctx)
    assert report["status"] == "ready" and report["conversion"] == "none"
    assert report["measurement_side"]["declared_side"] == "primary"           # the original evidence is retained
    assert "GROUP_OVERRIDE_OVERRIDES_DECLARATION" in {d["code"] for d in report["measurement_side"]["diagnostics"]}
    # Clearing the override (selecting the declared side again) returns to the recording: Primary with the CT.
    _put(client, ws, src, gi, "primary")
    wrong = _result(client, ws, ctx)                                  # the 2 A recorded current is now read as primary
    _computed(wrong, relay=I_SEC * CT_S / CT_P, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))


def test_level_1_changes_reach_the_calculation_when_no_group_overrides(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="none", v="none")    # the recording declares nothing
    ctx, _gv_id, _gi = _bay(client, ws, src)
    _blocked(_result(client, ws, ctx), "measurement_side_unresolved")
    _set_rec(client, ws, src, "primary", "from the relay report")
    _computed(_result(client, ws, ctx), relay=2.0, side="primary", authority="engineer_recording_correction", ct=(CT_P, CT_S))
    _set_rec(client, ws, src, "secondary")
    _computed(_result(client, ws, ctx), relay=I_PRI, side="secondary", authority="engineer_recording_correction")
    _set_rec(client, ws, src, None)                                   # back to the (empty) evidence
    _blocked(_result(client, ws, ctx), "measurement_side_unresolved")


def test_voltage_and_current_group_settings_are_independent(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary", v="primary")
    ctx, gv, gi = _bay(client, ws, src)
    _put(client, ws, src, gv, "secondary")                            # an unrelated Voltage group changes ...
    _computed(_result(client, ws, ctx), relay=2.0, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))
    _put(client, ws, src, gi, "secondary")                            # ... only the Current group's own setting counts
    _computed(_result(client, ws, ctx), relay=I_PRI, side="secondary", authority="engineer_group_override")
    _put(client, ws, src, gv, "primary")                              # and a Voltage change back leaves it unchanged
    _computed(_result(client, ws, ctx), relay=I_PRI, side="secondary", authority="engineer_group_override")


def test_an_engineer_correction_supersedes_an_incorrect_declaration_and_keeps_the_evidence(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="secondary", v="secondary")   # declared secondary, but really primary
    ctx, _gv_id, _gi = _bay(client, ws, src)
    _computed(_result(client, ws, ctx), relay=I_PRI, side="secondary", authority="recording_channel_declared")
    _set_rec(client, ws, src, "primary", "the recorder's P/S flag is wrong")
    body = _result(client, ws, ctx)
    _computed(body, relay=2.0, side="primary", authority="engineer_recording_correction", ct=(CT_P, CT_S))
    side = _input(client, ws, ctx)["measurement_side"]
    assert side["effective_side"] == "primary" and side["declared_side"] == "secondary"
    assert side["authority"] == "engineer_recording_correction" and side["strict_usable"] is True
    assert "ENGINEER_CORRECTION_OVERRIDES_DECLARATION" in {d["code"] for d in side["diagnostics"]}


def test_a_side_that_is_only_inferred_does_not_unblock_and_an_engineer_confirmation_does(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary", ps={"IC": ""})   # IC declares nothing: inferred from IA/IB
    ctx, _gv_id, _gi = _bay(client, ws, src)
    _computed(_result(client, ws, ctx, "A"), relay=2.0, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))
    inferred = _result(client, ws, ctx, "C")
    _blocked(inferred, "measurement_side_inferred")
    assert inferred["measurement_side"] == "primary" and inferred["measurement_side_authority"] == "recording_default"
    report = _input(client, ws, ctx, "C")
    assert report["status"] == "needs_configuration" and report["measurement_side"]["inferred"] is True
    assert report["measurement_side"]["strict_usable"] is False
    _set_rec(client, ws, src, "primary")                                    # the engineer confirms what is only inferred
    _computed(_result(client, ws, ctx, "C"), relay=2.0, side="primary", authority="engineer_recording_correction", ct=(CT_P, CT_S))


def test_a_recording_with_no_side_evidence_never_guesses_from_magnitude_or_the_ct_ratio(client):
    ws = _ws()
    for rms in (I_PRI, I_SEC):                       # 400 A "looks primary", 2 A "looks secondary": neither is used
        src = _recording(client, ws, i_rms=rms, i="none", v="none", stem=f"nog{int(rms)}")
        ctx, _gv_id, _gi = _bay(client, ws, src, gid=None, tag=f"n{int(rms)}")
        body = _result(client, ws, ctx)
        _blocked(body, "measurement_side_unresolved")
        assert body["measurement_side"] is None
        # a request basis cannot resolve it either
        for basis in ("primary", "secondary"):
            _blocked(_result(client, ws, ctx, recording_basis=basis), "measurement_side_unresolved")


def test_a_current_group_whose_channels_declare_different_sides_is_contradictory_until_the_engineer_chooses(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary", ps={"IB": "S"})
    ctx, _gv_id, gi = _bay(client, ws, src)
    blocked = _result(client, ws, ctx, "A")                                  # IA declares primary, but its group is split
    _blocked(blocked, "measurement_side_conflict")
    assert gi in blocked["message"]
    assert _gv(client, ws, src, gi)["status"] == "conflict"
    _put(client, ws, src, gi, "primary")                                     # the engineer decides for the whole group
    for phase in ("A", "B", "C"):
        _computed(_result(client, ws, ctx, phase), relay=2.0, side="primary", authority="engineer_group_override", ct=(CT_P, CT_S))


# =========================================================================== legacy request parameters are only assertions


def test_a_legacy_basis_that_contradicts_the_authority_blocks_instead_of_overriding(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gv_id, _gi = _bay(client, ws, src)
    body = _result(client, ws, ctx, recording_basis="secondary", ct_primary=CT_P, ct_secondary=CT_S)
    _blocked(body, "recording_basis_contradicts_measurement_side")
    assert "primary" in body["message"] and "Recording Details" in body["message"]
    assert body["measurement_side"] == "primary"
    # the same request with the matching basis, or with none, is accepted and gives the authoritative number
    for extra in ({"recording_basis": "primary"}, {}, {"recording_basis": "primary", "ct_primary": CT_P, "ct_secondary": CT_S}):
        _computed(_result(client, ws, ctx, **extra), relay=2.0, side="primary", authority="recording_channel_declared", ct=(CT_P, CT_S))
    # an invalid value is rejected before any resolution
    invalid = _result(client, ws, ctx, recording_basis="bogus")
    assert invalid["status"] == "needs_configuration" and invalid["reason_code"] == "invalid_recording_basis"
    assert all(invalid[k] is None for k in NUMBERS)


def test_a_legacy_request_ct_is_validated_never_used(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gv_id, _gi = _bay(client, ws, src)
    differs = _result(client, ws, ctx, recording_basis="primary", ct_primary=2000.0, ct_secondary=5.0)
    _blocked(differs, "request_ct_differs_from_authority")
    assert "Recording Details" in differs["message"]
    _blocked(_result(client, ws, ctx, ct_primary=1000.0), "invalid_ct_values")          # partial pair
    _blocked(_result(client, ws, ctx, ct_primary=0.0, ct_secondary=5.0), "invalid_ct_values")
    # the same ratio written differently (200/1 == 1000/5) is the same conversion and is accepted
    _computed(_result(client, ws, ctx, ct_primary=200.0, ct_secondary=1.0), relay=2.0, side="primary",
              authority="recording_channel_declared", ct=(CT_P, CT_S))
    # no CT in Recording Details: a request CT cannot stand in for it
    ws2 = _ws()
    src2 = _recording(client, ws2, i_rms=I_PRI, i="primary")
    ctx2, _v2, _i2 = _bay(client, ws2, src2, ct=None)
    _blocked(_result(client, ws2, ctx2, recording_basis="primary", ct_primary=CT_P, ct_secondary=CT_S), "invalid_ct_values")
    # a Secondary side needs no CT, so a stray request CT is ignored (and never applied)
    ws3 = _ws()
    src3 = _recording(client, ws3, i_rms=I_SEC, i="secondary")
    ctx3, _v3, _i3 = _bay(client, ws3, src3)
    _computed(_result(client, ws3, ctx3, ct_primary=9999.0, ct_secondary=1.0), relay=2.0, side="secondary",
              authority="recording_channel_declared")


def test_direct_service_callers_cannot_skip_the_authority():
    parameter = inspect.signature(compute_overcurrent_analysis).parameters["authority"]
    assert parameter.default is inspect.Parameter.empty
    # and the legacy parameters are optional assertions
    for name in ("recording_basis", "ct_primary", "ct_secondary"):
        assert inspect.signature(compute_overcurrent_analysis).parameters[name].default is None


# =========================================================================== owning group, phase, recording


def test_each_phase_uses_the_ct_and_the_override_of_its_own_current_group(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx = _context(client, ws, src)
    _group(client, ws, src, KIND_CURRENT, ("IA", "IC"), "ig-ac")
    _group(client, ws, src, KIND_CURRENT, ("IB",), "ig-b")
    _ct(client, ws, "ig-ac", 1000.0, 5.0)
    _ct(client, ws, "ig-b", 2000.0, 1.0)
    for phase, relay, group, ct in (("A", 2.0, "ig-ac", (1000.0, 5.0)), ("B", 0.2, "ig-b", (2000.0, 1.0)),
                                    ("C", 2.0, "ig-ac", (1000.0, 5.0))):
        body = _result(client, ws, ctx, phase)
        _computed(body, relay=relay, side="primary", authority="recording_channel_declared", ct=ct)
        assert body["measurement_group_id"] == group, phase
    _put(client, ws, src, "ig-b", "secondary")                           # only phase B's group changes
    _computed(_result(client, ws, ctx, "B"), relay=I_PRI, side="secondary", authority="engineer_group_override")
    _computed(_result(client, ws, ctx, "A"), relay=2.0, side="primary", authority="recording_channel_declared", ct=(1000.0, 5.0))


def test_a_ct_held_by_another_group_of_the_recording_is_never_borrowed(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx = _context(client, ws, src)
    _group(client, ws, src, KIND_CURRENT, ("IA",), "ig-a")               # phase A's own group has no CT
    _group(client, ws, src, KIND_CURRENT, ("IB", "IC"), "ig-bc")
    _ct(client, ws, "ig-bc", 1000.0, 5.0)
    blocked = _result(client, ws, ctx, "A")
    _blocked(blocked, "invalid_ct_values")
    assert "ig-a" in blocked["message"] and blocked["measurement_group_id"] == "ig-a"
    _computed(_result(client, ws, ctx, "B"), relay=2.0, side="primary", authority="recording_channel_declared", ct=(1000.0, 5.0))


def test_different_recordings_have_separate_authority_and_separate_cts(client):
    ws = _ws()
    s1 = _recording(client, ws, i_rms=I_PRI, i="primary", stem="r1")
    s2 = _recording(client, ws, i_rms=I_SEC, i="secondary", stem="r2")
    c1, _v1, g1 = _bay(client, ws, s1, ct=(1000.0, 5.0), tag="r1")
    c2, _v2, g2 = _bay(client, ws, s2, ct=(600.0, 1.0), tag="r2")
    _computed(_result(client, ws, c1), relay=2.0, side="primary", authority="recording_channel_declared", ct=(1000.0, 5.0))
    _computed(_result(client, ws, c2), relay=2.0, side="secondary", authority="recording_channel_declared")
    _put(client, ws, s1, g1, "secondary")                                # changing recording 1 ...
    _computed(_result(client, ws, c1), relay=I_PRI, side="secondary", authority="engineer_group_override")
    _computed(_result(client, ws, c2), relay=2.0, side="secondary", authority="recording_channel_declared")  # ... not 2
    _set_rec(client, ws, s2, "primary")                                  # and recording 2 uses ITS OWN CT (600:1), not 1000:5
    _computed(_result(client, ws, c2), relay=I_SEC * 1.0 / 600.0, side="primary", authority="engineer_recording_correction", ct=(600.0, 1.0))
    _computed(_result(client, ws, c1), relay=I_PRI, side="secondary", authority="engineer_group_override")
    assert g1 != g2


def test_a_configuration_change_is_visible_on_the_next_request_and_a_workspace_reset_leaves_no_authority(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="none", v="none")
    ctx, _gv_id, gi = _bay(client, ws, src)
    _set_rec(client, ws, src, "primary")
    _put(client, ws, src, gi, "secondary")
    assert client.app.state.measurement_side_registry.count() == 2
    _computed(_result(client, ws, ctx), relay=I_PRI, side="secondary", authority="engineer_group_override")
    assert client.delete(f"/api/v1/workspaces/{ws}").status_code == 204
    assert client.app.state.measurement_side_registry.count() == 0
    # the same workspace id again: nothing of the previous authority survives
    src2 = _recording(client, ws, i_rms=I_PRI, i="none", v="none", stem="again")
    ctx2, _v2, _i2 = _bay(client, ws, src2)
    _blocked(_result(client, ws, ctx2), "measurement_side_unresolved")
    assert _input(client, ws, ctx2)["measurement_side"]["authority"] == "unresolved"


# =========================================================================== blocked results keep the waveform available


@pytest.mark.parametrize("scenario", ["unresolved", "inferred", "group_conflict", "basis_contradiction", "no_ct"])
def test_every_configuration_block_keeps_the_consumed_channel_and_never_a_number(client, scenario):
    ws = _ws()
    kwargs, extra, ct = {}, {}, (CT_P, CT_S)
    if scenario == "unresolved":
        kwargs = dict(i="none", v="none")
    elif scenario == "inferred":
        kwargs = dict(ps={"IA": ""})
    elif scenario == "group_conflict":
        kwargs = dict(ps={"IB": "S"})
    elif scenario == "basis_contradiction":
        extra = {"recording_basis": "secondary"}
    elif scenario == "no_ct":
        ct = None
    src = _recording(client, ws, **kwargs)
    ctx, _gv_id, _gi = _bay(client, ws, src, ct=ct)
    body = _result(client, ws, ctx, "A", **extra)
    assert body["status"] == "needs_configuration" and body["reason_code"], body
    assert all(body[k] is None for k in NUMBERS), body
    assert body["channel_ref"]["channel_name"] == "ZBAY_IA" and body["measured_rms_current_unit"] == "A"
    # the read-only report names the same channel and reason (a request-only contradiction is not part of the report,
    # which reads Recording Details alone: there the configuration is fine and only the request is wrong)
    report = _input(client, ws, ctx, "A")
    assert report["channel_ref"]["channel_name"] == "ZBAY_IA" and report["channel_unit"] == "A"
    if scenario == "basis_contradiction":
        assert report["status"] == "ready" and report["measurement_side"]["effective_side"] == "primary"
    else:
        assert report["status"] == "needs_configuration" and report["reason_code"] == body["reason_code"]


def test_the_report_and_the_calculation_never_disagree(client):
    cases = [
        dict(rec=dict(i="primary"), ct=(CT_P, CT_S)), dict(rec=dict(i="secondary", i_rms=I_SEC), ct=(CT_P, CT_S)),
        dict(rec=dict(i="secondary", i_rms=I_SEC), ct=None), dict(rec=dict(i="primary"), ct=None),
        dict(rec=dict(i="none", v="none"), ct=(CT_P, CT_S)), dict(rec=dict(ps={"IA": ""}), ct=(CT_P, CT_S)),
    ]
    for case in cases:
        ws = _ws()
        src = _recording(client, ws, **case["rec"])
        ctx, _gv_id, _gi = _bay(client, ws, src, ct=case["ct"])
        for phase in ("A", "B", "C"):
            body, report = _result(client, ws, ctx, phase), _input(client, ws, ctx, phase)
            assert (report["status"] == "ready") == (body["status"] == "computed"), (case, phase)
            if body["status"] == "computed":
                assert report["conversion"] == ("primary_to_relay_secondary" if body["measurement_side"] == "primary" else "none")
                assert report["measurement_side"]["effective_side"] == body["measurement_side"]
            else:
                assert report["reason_code"] == body["reason_code"], (case, phase)


# =========================================================================== the read-only report


def test_the_report_names_the_channel_group_side_provenance_and_ct(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gv_id, gi = _bay(client, ws, src)
    report = _input(client, ws, ctx, "B")
    assert (report["status"], report["phase"], report["conversion"]) == ("ready", "B", "primary_to_relay_secondary")
    assert report["channel_ref"]["channel_name"] == "ZBAY_IB" and report["channel_unit"] == "A"
    assert (report["measurement_group_id"], report["measurement_group_name"]) == (gi, gi)
    side = report["measurement_side"]
    assert (side["effective_side"], side["authority"], side["declared_side"], side["strict_usable"]) == (
        "primary", "recording_channel_declared", "primary", True)
    ct = report["ct"]
    assert (ct["status"], ct["consumable"], ct["primary"], ct["secondary"], ct["ratio"], ct["authority"], ct["group_ids"]) == (
        "configured", True, CT_P, CT_S, CT_P / CT_S, "manual", [gi])


def test_the_report_shows_the_ct_even_when_it_is_not_needed_and_the_missing_ct_when_it_is(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_SEC, i="secondary")
    ctx, _gv_id, _gi = _bay(client, ws, src, ct=None)
    report = _input(client, ws, ctx)
    assert (report["status"], report["conversion"]) == ("ready", "none")
    assert (report["ct"]["status"], report["ct"]["consumable"]) == ("not_configured", False)
    _set_rec(client, ws, src, "primary")
    blocked = _input(client, ws, ctx)
    assert blocked["status"] == "needs_configuration" and blocked["reason_code"] == "invalid_ct_values"
    assert blocked["conversion"] is None and blocked["measurement_group_id"] == _gi


def test_the_report_validates_its_request_and_reports_unresolved_roles(client):
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx = _context(client, ws, src, members=("VA", "VB", "VC"))          # a context with no current channel
    resp = client.get(f"{_contexts(ws)}/{ctx}/overcurrent-recorded-input", params={"phase": "A"})
    assert resp.status_code == 200 and resp.json()["status"] != "ready"
    assert resp.json()["measurement_side"] is None and resp.json()["channel_ref"] is None
    assert client.get(f"{_contexts(ws)}/{ctx}/overcurrent-recorded-input", params={"phase": "X"}).status_code == 422
    assert client.get(f"{_contexts(ws)}/nope/overcurrent-recorded-input", params={"phase": "A"}).status_code == 404


# =========================================================================== calculated channels, manual mode


def test_a_calculated_current_channel_is_blocked_because_its_side_is_not_resolved_here(client):
    authority = OvercurrentAuthority.from_app_state(client.app.state)
    recorded = evaluate_recorded_current_authority("ws", ChannelRef(kind="calculated", calculated_channel_id="calc-1"),
                                                   authority=authority, requested_basis="primary", request_ct=(1000.0, 5.0))
    assert recorded.blocker is not None and recorded.blocker.reason_code == "calculated_channel_side_unavailable"
    assert recorded.basis is None and recorded.ct_pair is None


def _manual(client, ws, **params):
    q = {"characteristic_id": "iec_standard_inverse", "tms": 0.1, "pickup_current_secondary": 1.0}
    q.update(params)
    resp = client.get(f"/api/v1/workspaces/{ws}/overcurrent-manual", params=q)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_manual_mode_is_unchanged_and_independent_of_recording_details(client):
    ws = _ws()
    before = _manual(client, ws, input_current=30000.0, input_current_unit="A", recording_basis="primary",
                     ct_primary=1200.0, ct_secondary=1.0)
    assert before["status"] == "computed" and before["relay_secondary_current"] == pytest.approx(25.0)   # 30000 * 1 / 1200
    secondary = _manual(client, ws, input_current=2.0, input_current_unit="A", recording_basis="secondary")
    assert secondary["status"] == "computed" and secondary["relay_secondary_current"] == pytest.approx(2.0)
    missing_ct = _manual(client, ws, input_current=30000.0, input_current_unit="A", recording_basis="primary")
    assert missing_ct["status"] == "needs_configuration" and missing_ct["reason_code"] == "invalid_ct_values"
    # Recording Details configuration (a recording, side overrides) changes none of it.
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    _ctx, _gv_id, gi = _bay(client, ws, src)
    _set_rec(client, ws, src, "secondary")
    _put(client, ws, src, gi, "secondary")
    assert _manual(client, ws, input_current=30000.0, input_current_unit="A", recording_basis="primary",
                   ct_primary=1200.0, ct_secondary=1.0) == before
    assert "measurement_side" not in before and "measurement_group_id" not in before


# =========================================================================== cross-check against the accepted calculation


@pytest.mark.parametrize("side,i_rms,expected", [("primary", I_PRI, 2.0), ("secondary", I_SEC, 2.0), ("primary", 1000.0, 5.0)])
def test_the_recorded_result_equals_the_accepted_manual_calculation_for_the_same_input(client, side, i_rms, expected):
    """`/overcurrent-manual` predates this slice and is unchanged: the recorded path must give the identical relay current,
    multiple of pickup and IEC operating time for the equivalent configuration."""
    ws = _ws()
    src = _recording(client, ws, i_rms=i_rms, i=side)
    ctx, _gv_id, _gi = _bay(client, ws, src)
    recorded = _result(client, ws, ctx)
    manual = _manual(client, ws, input_current=recorded["measured_rms_current"], input_current_unit=recorded["measured_rms_current_unit"],
                     recording_basis=side, **({"ct_primary": CT_P, "ct_secondary": CT_S} if side == "primary" else {}))
    assert recorded["relay_secondary_current"] == pytest.approx(expected, rel=1e-3)
    for key in ("relay_secondary_current", "multiple_of_pickup", "expected_operating_time_seconds"):
        assert recorded[key] == pytest.approx(manual[key], rel=1e-12), key
    assert (recorded["ct_primary"], recorded["ct_secondary"]) == ((CT_P, CT_S) if side == "primary" else (None, None))
    # the hand-derived oracle, independent of both implementations
    m = expected / 1.0
    assert recorded["multiple_of_pickup"] == pytest.approx(m, rel=1e-3)
    assert recorded["expected_operating_time_seconds"] == pytest.approx(0.1 * 0.14 / (m ** 0.02 - 1.0), rel=1e-3)


def test_the_unified_side_never_changes_other_protection_analyses(client):
    """Impedance and Distance are not migrated in this slice: their legacy basis/CT behaviour is untouched."""
    ws = _ws()
    src = _recording(client, ws, i_rms=I_PRI, i="primary")
    ctx, _gv_id, gi = _bay(client, ws, src)
    before = client.get(f"{_contexts(ws)}/{ctx}/protection-instrument-context", params={"analysis": "impedance", "phase": "A",
                                                                                          "recording_basis": "primary"}).json()
    _put(client, ws, src, gi, "secondary")
    after = client.get(f"{_contexts(ws)}/{ctx}/protection-instrument-context", params={"analysis": "impedance", "phase": "A",
                                                                                         "recording_basis": "primary"}).json()
    assert before["current"]["side"] == after["current"]["side"] == "primary"      # that report still reads declarations only
    assert before["current"]["ratio"] == after["current"]["ratio"] == CT_P / CT_S


def test_putting_an_invalid_group_side_is_still_rejected(client):
    ws = _ws()
    src = _recording(client, ws)
    _ctx, _gv_id, gi = _bay(client, ws, src)
    assert _set_g(client, ws, src, gi, "sideways").status_code == 422
