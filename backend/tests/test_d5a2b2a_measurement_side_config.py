"""D5A-2B2A: unified measurement-side configuration (Level 1 recording, Level 2 bay) and the shared resolver.

Real app, real ASCII-COMTRADE uploads whose per-channel P/S flags are the original recording evidence.
Expected sides/authorities are stated by hand from the owner's rules, never read back from the code under
test. The last section proves no existing PU or protection result changes in this slice.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.domain.measurement_side_config import (
    AUTH_BAY_OVERRIDE,
    AUTH_CHANNEL_DECLARED,
    AUTH_RECORDING_CORRECTION,
    AUTH_RECORDING_DEFAULT,
    AUTH_UNRESOLVED,
    EVIDENCE_CONSISTENT,
    EVIDENCE_MIXED,
    EVIDENCE_NONE,
    MEMBERSHIP_CONFIRMED,
    ChannelSideEvidence,
    ChannelSideResolution,
    BaySideState,
    bay_override_to_store,
    derive_recording_side,
    recording_correction_to_store,
    resolve_channel_side,
    resolve_recording_state,
    resolve_side_set,
)
from app.main import create_app
from app.services.measurement_side_service import (
    SideAuthority,
    resolve_consumed_side,
    resolve_effective_measurement_side,
    resolve_effective_side_for_ref,
)
from tests.test_d5a2a_protection_instrument_context_api import _clear, _contexts, _ct, _group, _ref, _vt
from tests.test_d5a2b1_independent_side_conversion import (
    CT_P, CT_S, VT_P, VT_S, _ALL, _comtrade, _context, _imp, _strict, _upload,
)
from tests.test_d5a_oc_001_overcurrent_ct_authority import _oc

V, I = ("VA", "VB", "VC"), ("IA", "IB", "IC")


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- helpers


def _ws() -> str:
    return f"ws-{uuid4().hex[:8]}"


def _flags(v: str = "P", i: str = "P", **per_channel: str) -> dict[str, str]:
    """P/S flags by channel: `v`/`i` for the quantity default (primary -> P, secondary -> S, none -> '')."""
    code = {"primary": "P", "secondary": "S", "none": ""}
    flags = {n: code[v if n[0] == "V" else i] for n in _ALL}
    flags.update(per_channel)
    return flags


def _source(client, ws, *, v="primary", i="primary", ps=None, stem="rec") -> str:
    flags = _flags(v, i)
    flags.update(ps or {})
    cfg, dat = _comtrade(v_rms=66000.0, i_rms=400.0, ps=flags)
    src = _upload(client, ws, cfg, dat, stem=stem)
    _clear(client, ws)                     # drop auto-suggested contexts/groups: each test builds its own bays
    return src


def _bay(client, ws, src, members, *, status="manual", name=None) -> str:
    resp = client.post(_contexts(ws), json={"display_name": name or f"bay-{members[0]}", "status": status, "members": [
        {"channel_ref": _ref(src, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"} for n in members]})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _url(ws, tail=""):
    return f"/api/v1/workspaces/{ws}/measurement-side{tail}"


def _rec(client, ws, src):
    resp = client.get(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-side")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_rec(client, ws, src, side, note=None):
    resp = client.put(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-side", json={"side": side, "note": note})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _context_view(client, ws, ctx):
    resp = client.get(f"{_contexts(ws)}/{ctx}/measurement-side")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _only_source(client, ws, ctx):
    """The single recording a bay contributes channels from (most bays); ambiguous bays must name theirs."""
    associations = _context_view(client, ws, ctx)["associations"]
    assert len(associations) == 1, "this bay spans several recordings: name the one you mean"
    return associations[0]["source_id"]


def _assoc_url(ws, ctx, src):
    return f"/api/v1/workspaces/{ws}/sources/{src}/engineering-contexts/{ctx}/measurement-side"


def _bay_view(client, ws, ctx, src=None):
    """The bay within one recording (the unit a Level 2 setting belongs to)."""
    resp = client.get(_assoc_url(ws, ctx, src or _only_source(client, ws, ctx)))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_bay(client, ws, ctx, side, src=None):
    if src is None:
        found = client.get(f"{_contexts(ws)}/{ctx}/measurement-side")
        src = _only_source(client, ws, ctx) if found.status_code == 200 else "no-such-recording"
    return client.put(_assoc_url(ws, ctx, src), json={"side": side})


def _multi_bay(client, ws, name, parts, *, status="manual"):
    """One Engineering Context holding channels of several recordings: parts = [(source_id, ("VA", "IA")), ...]."""
    members = [{"channel_ref": _ref(src, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"}
               for src, names in parts for n in names]
    resp = client.post(_contexts(ws), json={"display_name": name, "status": status, "members": members})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _chan(client, ws, src, name):
    resp = client.get(_url(ws, "/channel"), params={"source_id": src, "channel_name": f"ZBAY_{name}"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _sides(body):
    return {c["channel_name"].removeprefix("ZBAY_"): c["effective_side"] for c in body["channels"]}


def _codes(body):
    return {d["code"] for d in body["diagnostics"]}


def _deps(client) -> SideAuthority:
    return SideAuthority.from_app_state(client.app.state)


# =========================================================================== pure domain oracles


def _ev(name, side, quantity="voltage"):
    return ChannelSideEvidence(name, quantity, side)


@pytest.mark.parametrize("declared,status,side,counts", [
    (["primary"] * 6, EVIDENCE_CONSISTENT, "primary", (6, 0, 0)),
    (["secondary"] * 6, EVIDENCE_CONSISTENT, "secondary", (0, 6, 0)),
    (["primary", "primary", "unknown"], EVIDENCE_CONSISTENT, "primary", (2, 0, 1)),
    (["unknown"] * 3, EVIDENCE_NONE, None, (0, 0, 3)),
    ([], EVIDENCE_NONE, None, (0, 0, 0)),
    (["primary", "secondary"], EVIDENCE_MIXED, None, (1, 1, 0)),
    (["primary", "secondary", "unknown"], EVIDENCE_MIXED, None, (1, 1, 1)),
])
def test_recording_derivation_oracle(declared, status, side, counts):
    d = derive_recording_side([_ev(f"c{n}", s) for n, s in enumerate(declared)])
    assert (d.status, d.side, (d.primary_count, d.secondary_count, d.undeclared_count)) == (status, side, counts)


def test_voltage_current_split_is_a_legitimate_recording_not_a_mix():
    ev = [_ev("va", "primary"), _ev("vb", "primary"), _ev("ia", "secondary", "current"), _ev("ib", "secondary", "current")]
    d = derive_recording_side(ev)
    assert (d.status, d.side, d.voltage_side, d.current_side) == ("voltage_current_differ", None, "primary", "secondary")
    state = resolve_recording_state(d, None, ev)
    assert (state.effective_side, state.authority) == (None, AUTH_UNRESOLVED)
    assert [(x.code, x.severity) for x in state.diagnostics] == [("RECORDING_VOLTAGE_CURRENT_SIDES_DIFFER", "info")]
    # Disagreement within a quantity is still a genuine mix, even when the other quantity is uniform.
    within = derive_recording_side(ev + [_ev("vc", "secondary")])
    assert (within.status, within.voltage_side) == ("mixed", None)
    # Each channel keeps its own declaration; nothing is inferred for the undeclared ones.
    sub = resolve_channel_side(_ev("ia", "secondary", "current"), state)
    assert (sub.side, sub.authority) == ("secondary", AUTH_CHANNEL_DECLARED)
    undeclared = resolve_channel_side(_ev("ic", "unknown", "current"), state)
    assert (undeclared.side, undeclared.authority) == ("unknown", AUTH_UNRESOLVED)
    assert recording_correction_to_store("primary", d) == "primary"


@pytest.mark.parametrize("selected,derived_status,derived_side,expected", [
    (None, EVIDENCE_CONSISTENT, "primary", None),            # follow the recording
    ("primary", EVIDENCE_CONSISTENT, "primary", None),       # equal to the recording: nothing redundant stored
    ("secondary", EVIDENCE_CONSISTENT, "primary", "secondary"),
    ("primary", EVIDENCE_NONE, None, "primary"),             # no evidence: an engineer value is the only authority
    ("primary", EVIDENCE_MIXED, None, "primary"),
])
def test_recording_correction_to_store_oracle(selected, derived_status, derived_side, expected):
    from app.domain.measurement_side_config import RecordingSideDerivation
    d = RecordingSideDerivation(derived_status, derived_side)
    assert recording_correction_to_store(selected, d) == expected


def test_confirming_the_inferred_side_of_partial_evidence_is_kept():
    from app.domain.measurement_side_config import RecordingSideDerivation
    partial = RecordingSideDerivation(EVIDENCE_CONSISTENT, "secondary", undeclared_count=2)
    assert recording_correction_to_store("secondary", partial) == "secondary"     # engineer confirmation, not redundant
    assert recording_correction_to_store("primary", partial) == "primary"
    assert recording_correction_to_store(None, partial) is None


@pytest.mark.parametrize("selected,inherited,expected", [
    ("primary", "primary", None),          # selecting the inherited value clears the override
    ("secondary", "primary", "secondary"),
    ("primary", None, "primary"),          # nothing single to follow: it is a manual override
    ("secondary", None, "secondary"),
])
def test_bay_override_to_store_oracle(selected, inherited, expected):
    assert bay_override_to_store(selected, inherited) == expected


@pytest.mark.parametrize("bad", ["", "unknown", "PRIMARY", None])
def test_invalid_selections_are_rejected(bad):
    with pytest.raises(ValueError):
        bay_override_to_store(bad, "primary")


def _state(declared, engineer=None):
    evidence = [_ev(f"c{n}", s) for n, s in enumerate(declared)]
    return resolve_recording_state(derive_recording_side(evidence), engineer, evidence)


@pytest.mark.parametrize("declared,engineer,channel,bay,expected_side,expected_auth", [
    # precedence: bay override > recording correction > channel declaration > recording default > unresolved
    ("primary", None, "primary", None, "primary", AUTH_CHANNEL_DECLARED),
    ("secondary", None, "secondary", None, "secondary", AUTH_CHANNEL_DECLARED),
    ("primary", "secondary", "primary", None, "secondary", AUTH_RECORDING_CORRECTION),
    ("primary", "secondary", "primary", "primary", "primary", AUTH_BAY_OVERRIDE),
    ("primary", None, "unknown", None, "primary", AUTH_RECORDING_DEFAULT),
    ("unknown", None, "unknown", None, "unknown", AUTH_UNRESOLVED),
    ("unknown", "primary", "unknown", None, "primary", AUTH_RECORDING_CORRECTION),
])
def test_channel_precedence_oracle(declared, engineer, channel, bay, expected_side, expected_auth):
    # Recording evidence = one channel declaring `declared`, plus the channel under test declaring `channel`.
    evidence = [_ev("other", declared), _ev("subject", channel)]
    state = resolve_recording_state(derive_recording_side(evidence), engineer, evidence)
    res = resolve_channel_side(evidence[1], state, BaySideState("ec-1", MEMBERSHIP_CONFIRMED, bay))
    assert (res.side, res.authority) == (expected_side, expected_auth)
    assert res.declared_side == channel                          # the original evidence is never altered


def test_unconfirmed_bay_override_is_never_applied():
    evidence = [_ev("c", "primary")]
    state = resolve_recording_state(derive_recording_side(evidence), None, evidence)
    res = resolve_channel_side(evidence[0], state, BaySideState("ec-1", "unconfirmed", "secondary"))
    assert (res.side, res.authority, res.bay_override_side) == ("primary", AUTH_CHANNEL_DECLARED, None)
    assert "BAY_MEMBERSHIP_UNCONFIRMED" in {d.code for d in res.diagnostics}


def _res(name, side, quantity="voltage", authority=AUTH_CHANNEL_DECLARED):
    return ChannelSideResolution(name, quantity, side, authority if side != "unknown" else AUTH_UNRESOLVED, side,
                                 None, AUTH_UNRESOLVED)


def test_side_set_oracle():
    ok = resolve_side_set([_res("a", "primary"), _res("b", "primary"), _res("ia", "primary", "current")])
    assert (ok.status, ok.side, ok.voltage_side, ok.current_side) == ("resolved", "primary", "primary", "primary")
    within = resolve_side_set([_res("a", "primary"), _res("b", "secondary")])
    assert (within.status, within.side) == ("conflict", None)
    assert "BAY_MIXED_SIDES_WITHIN_QUANTITY" in {d.code for d in within.diagnostics}
    # B2A-1: voltage Primary + current Secondary is a legitimate mixed reference, NOT a conflict.
    vi = resolve_side_set([_res("a", "primary"), _res("b", "primary"), _res("ia", "secondary", "current")])
    assert (vi.status, vi.side, vi.voltage_side, vi.current_side, vi.usable, vi.reference_sides) == (
        "resolved", None, "primary", "secondary", True, "voltage_current_differ")
    note = next(d for d in vi.diagnostics if d.code == "BAY_VOLTAGE_CURRENT_SIDES_DIFFER")
    assert note.severity == "info"
    # ... but disagreement WITHIN a quantity still is, even alongside a differing other quantity.
    both = resolve_side_set([_res("a", "primary"), _res("b", "secondary"), _res("ia", "secondary", "current")])
    assert (both.status, both.side, both.usable) == ("conflict", None, False)
    part = resolve_side_set([_res("a", "primary"), _res("b", "unknown")])
    assert (part.status, part.side) == ("unresolved", None)       # never guessed from the channels that did resolve
    assert resolve_side_set([]).status == "not_applicable"


# =========================================================================== File Primary / File Secondary


@pytest.mark.parametrize("side", ["primary", "secondary"])
def test_file_side_flows_to_every_bay(client, side):
    ws = _ws()
    src = _source(client, ws, v=side, i=side)
    bay_a = _bay(client, ws, src, ("VA", "IA"))
    bay_b = _bay(client, ws, src, ("VB", "VC", "IB", "IC"))
    rec = _rec(client, ws, src)
    assert rec["recording_derived"] == {"status": "consistent", "side": side, "voltage_side": side, "current_side": side,
                                        "primary_channels": 6 if side == "primary" else 0,
                                        "secondary_channels": 0 if side == "primary" else 6, "undeclared_channels": 0,
                                        "evidence_channels": 6}
    assert (rec["effective_side"], rec["authority"], rec["engineer_correction"]) == (side, AUTH_CHANNEL_DECLARED, None)
    for ctx in (bay_a, bay_b):
        view = _bay_view(client, ws, ctx)
        assert (view["status"], view["effective_side"], view["inherited_recording_side"], view["override"]) == (
            "resolved", side, side, None)
        assert {c["authority"] for c in view["channels"]} == {AUTH_CHANNEL_DECLARED}


# =========================================================================== Level 1 changes; bays follow


def test_level1_change_updates_every_automatic_bay_and_keeps_the_original_evidence(client):
    ws = _ws()
    src = _source(client, ws)                                              # recording declares Primary everywhere
    bays = [_bay(client, ws, src, ("VA", "IA")), _bay(client, ws, src, ("VB", "IB")), _bay(client, ws, src, ("VC", "IC"))]
    body = _set_rec(client, ws, src, "secondary", note="Relay records secondary quantities")
    assert (body["effective_side"], body["authority"]) == ("secondary", AUTH_RECORDING_CORRECTION)
    assert body["engineer_correction"]["side"] == "secondary" and body["engineer_correction"]["note"].startswith("Relay")
    assert body["recording_derived"]["side"] == "primary"                  # the evidence is untouched
    assert "ENGINEER_CORRECTION_OVERRIDES_DECLARATION" in _codes(body)
    for c in body["channels"]:
        assert (c["effective_side"], c["declared_side"], c["authority"]) == ("secondary", "primary", AUTH_RECORDING_CORRECTION)
    for ctx in bays:
        view = _bay_view(client, ws, ctx)
        assert (view["effective_side"], view["inherited_recording_side"], view["override"]) == ("secondary", "secondary", None)
    assert _rec(client, ws, src)["engineer_correction"] is not None        # persisted for the session


def test_selecting_the_recorded_side_or_null_returns_the_recording_to_its_evidence(client):
    ws = _ws()
    src = _source(client, ws)
    _set_rec(client, ws, src, "secondary")
    assert _set_rec(client, ws, src, "primary")["engineer_correction"] is None      # equals the evidence -> nothing stored
    _set_rec(client, ws, src, "secondary")
    body = _set_rec(client, ws, src, None)
    assert (body["engineer_correction"], body["effective_side"], body["authority"]) == (None, "primary", AUTH_CHANNEL_DECLARED)


# =========================================================================== bay overrides


def test_one_overridden_bay_keeps_its_value_while_others_follow_level1(client):
    ws = _ws()
    src = _source(client, ws)
    follower, pinned = _bay(client, ws, src, ("VA", "IA")), _bay(client, ws, src, ("VB", "VC", "IB", "IC"))
    resp = _set_bay(client, ws, pinned, "secondary")
    assert resp.status_code == 200
    view = resp.json()
    assert (view["effective_side"], view["authority"], view["override"]["side"], view["override"]["active"]) == (
        "secondary", AUTH_BAY_OVERRIDE, "secondary", True)
    assert view["inherited_recording_side"] == "primary"
    assert "BAY_OVERRIDE_OVERRIDES_DECLARATION" in _codes(view)             # the P declarations are retained, reported
    assert {c["declared_side"] for c in view["channels"]} == {"primary"}
    assert _bay_view(client, ws, follower)["effective_side"] == "primary"

    _set_rec(client, ws, src, "secondary")                                  # Level 1 changes ...
    assert _bay_view(client, ws, follower)["effective_side"] == "secondary" # ... the follower follows
    pinned_view = _bay_view(client, ws, pinned)
    assert (pinned_view["effective_side"], pinned_view["override"]["side"]) == ("secondary", "secondary")
    _set_rec(client, ws, src, None)                                         # ... and back
    assert _bay_view(client, ws, follower)["effective_side"] == "primary"
    assert _bay_view(client, ws, pinned)["effective_side"] == "secondary"   # the override was retained throughout


def test_manual_override_differing_from_level1_overrides_a_secondary_recording_too(client):
    ws = _ws()
    src = _source(client, ws, v="secondary", i="secondary")
    bay = _bay(client, ws, src, ("VA", "IA"))
    view = _set_bay(client, ws, bay, "primary").json()
    assert (view["effective_side"], view["override"]["side"], view["inherited_recording_side"]) == ("primary", "primary", "secondary")


def test_selecting_the_inherited_value_clears_the_override_so_the_bay_follows_again(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, ("VA", "IA"))
    assert _set_bay(client, ws, bay, "secondary").json()["override"] is not None
    cleared = _set_bay(client, ws, bay, "primary").json()                   # primary == the bay's inherited Level 1 value
    assert (cleared["override"], cleared["effective_side"], cleared["authority"]) == (None, "primary", AUTH_CHANNEL_DECLARED)
    _set_rec(client, ws, src, "secondary")
    assert _bay_view(client, ws, bay)["effective_side"] == "secondary"      # proof it follows Level 1 again
    assert client.app.state.measurement_side_registry.get_bay(ws, bay, src) is None


def test_no_duplicate_per_bay_default_is_stored(client):
    ws = _ws()
    src = _source(client, ws)
    for members in (("VA", "IA"), ("VB", "IB"), ("VC", "IC")):
        _bay(client, ws, src, members)
    _set_rec(client, ws, src, "secondary")
    assert client.app.state.measurement_side_registry.count() == 1          # one Level 1 correction, nothing per bay


# =========================================================================== evidence quality


def test_missing_side_evidence_is_unresolved_until_an_engineer_decides(client):
    ws = _ws()
    src = _source(client, ws, v="none", i="none")
    bay = _bay(client, ws, src, ("VA", "IA"))
    rec = _rec(client, ws, src)
    assert (rec["recording_derived"]["status"], rec["effective_side"], rec["authority"]) == ("none", None, AUTH_UNRESOLVED)
    assert "RECORDING_SIDE_EVIDENCE_MISSING" in _codes(rec)
    view = _bay_view(client, ws, bay)
    assert (view["status"], view["effective_side"]) == ("unresolved", None)
    assert not _chan(client, ws, src, "VA")["usable"]
    # An engineer value is the only authority here, and it is recorded as such.
    body = _set_rec(client, ws, src, "secondary")
    assert (body["effective_side"], body["authority"]) == ("secondary", AUTH_RECORDING_CORRECTION)
    assert not any(d["code"] == "ENGINEER_CORRECTION_OVERRIDES_DECLARATION" for d in body["diagnostics"])  # nothing overridden
    assert _bay_view(client, ws, bay)["effective_side"] == "secondary"


def test_partial_evidence_uses_the_consistent_default_for_undeclared_channels_and_says_so(client):
    ws = _ws()
    src = _source(client, ws, v="secondary", i="none")                     # currents undeclared
    rec = _rec(client, ws, src)
    assert rec["recording_derived"]["undeclared_channels"] == 3 and "RECORDING_PARTIAL_SIDE_EVIDENCE" in _codes(rec)
    by_name = {c["channel_name"]: c for c in rec["channels"]}
    assert (by_name["ZBAY_VA"]["effective_side"], by_name["ZBAY_VA"]["authority"]) == ("secondary", AUTH_CHANNEL_DECLARED)
    assert (by_name["ZBAY_IA"]["effective_side"], by_name["ZBAY_IA"]["authority"]) == ("secondary", AUTH_RECORDING_DEFAULT)
    # B2A-2: the sibling-derived default is displayed, but it is inferred evidence, not strict-usable.
    assert (by_name["ZBAY_VA"]["strict_usable"], by_name["ZBAY_VA"]["inferred"]) == (True, False)
    assert (by_name["ZBAY_IA"]["usable"], by_name["ZBAY_IA"]["strict_usable"], by_name["ZBAY_IA"]["inferred"]) == (True, False, True)
    assert "CHANNEL_SIDE_INFERRED" in {d["code"] for d in by_name["ZBAY_IA"]["diagnostics"]}


def test_inferred_default_blocks_strict_consumption_until_declared_or_engineer_confirmed(client):
    ws = _ws()
    src = _source(client, ws, v="secondary", i="none")
    bay = _bay(client, ws, src, _ALL)
    deps = _deps(client)
    refs = [ChannelRef("source", src, f"ZBAY_{n}") for n in ("VA", "IA")]
    view = _bay_view(client, ws, bay)
    assert (view["status"], view["effective_side"], view["strict_usable"]) == ("resolved", "secondary", False)
    assert sorted(view["inferred_channels"]) == ["ZBAY_IA", "ZBAY_IB", "ZBAY_IC"]
    consumed = resolve_consumed_side(ws, refs, deps=deps)
    assert (consumed.usable, consumed.strict_usable) == (True, False)           # displayable, not strict
    assert resolve_consumed_side(ws, refs[:1], deps=deps).strict_usable         # voltage alone is declared
    # An engineer-confirmed Recording setting makes every channel's side reliable (provenance changes with it).
    _set_rec(client, ws, src, "secondary")
    confirmed = resolve_consumed_side(ws, refs, deps=deps)
    assert (confirmed.usable, confirmed.strict_usable, confirmed.inferred_channels) == (True, True, ())
    assert _bay_view(client, ws, bay)["strict_usable"] is True
    # ... and so does a confirmed Bay setting on a freshly inferred recording.
    ws2 = _ws()
    src2 = _source(client, ws2, v="secondary", i="none")
    bay2 = _bay(client, ws2, src2, _ALL)
    assert _bay_view(client, ws2, bay2)["strict_usable"] is False
    after = _set_bay(client, ws2, bay2, "primary").json()
    assert (after["strict_usable"], after["authority"]) == (True, AUTH_BAY_OVERRIDE)


# =========================================================================== different sides between bays


def test_bays_from_different_recordings_have_independent_sides(client):
    ws = _ws()
    s1 = _source(client, ws, v="primary", i="primary", stem="one")
    s2 = _source(client, ws, v="secondary", i="secondary", stem="two")
    b1, b2 = _bay(client, ws, s1, _ALL), _bay(client, ws, s2, _ALL)
    assert _bay_view(client, ws, b1)["effective_side"] == "primary"
    assert _bay_view(client, ws, b2)["effective_side"] == "secondary"
    _set_rec(client, ws, s1, "secondary")
    assert _bay_view(client, ws, b1)["effective_side"] == "secondary"
    assert _rec(client, ws, s2)["engineer_correction"] is None             # the other source is untouched


def test_one_bay_in_two_recordings_keeps_each_recordings_own_side(client):
    """Owner safety refinement: KPDN1 is Primary in recording A and Secondary in recording B, in ONE Engineering
    Context. A Level 2 change for A never reinterprets B; nothing is inherited across the two."""
    ws = _ws()
    a = _source(client, ws, v="primary", i="primary", stem="a")
    b = _source(client, ws, v="secondary", i="secondary", stem="b")
    kpdn1 = _multi_bay(client, ws, "KPDN1", [(a, ("VA", "IA")), (b, ("VA", "IA"))])
    ctx = _context_view(client, ws, kpdn1)
    assert [x["source_id"] for x in ctx["associations"]] == [a, b]
    assert [x["effective_side"] for x in ctx["associations"]] == ["primary", "secondary"]
    assert [x["inherited_recording_side"] for x in ctx["associations"]] == ["primary", "secondary"]   # no shared value
    assert "BAY_RECORDINGS_DISAGREE" in {d["code"] for d in ctx["diagnostics"]}

    changed = _set_bay(client, ws, kpdn1, "secondary", src=a).json()        # Level 2 for recording A only
    assert (changed["source_id"], changed["effective_side"], changed["override"]["side"]) == (a, "secondary", "secondary")
    other = _bay_view(client, ws, kpdn1, src=b)
    assert (other["effective_side"], other["override"], other["authority"]) == ("secondary", None, AUTH_CHANNEL_DECLARED)
    assert _chan(client, ws, a, "VA")["authority"] == AUTH_BAY_OVERRIDE
    assert _chan(client, ws, b, "VA")["authority"] == AUTH_CHANNEL_DECLARED   # B's channels were not reinterpreted

    flipped = _set_bay(client, ws, kpdn1, "primary", src=b).json()          # and Level 2 for B only
    assert (flipped["effective_side"], flipped["override"]["side"]) == ("primary", "primary")
    assert _bay_view(client, ws, kpdn1, src=a)["effective_side"] == "secondary"

    # clear-on-equal compares with THAT recording's Level 1 (A: Primary), whatever B says
    cleared = _set_bay(client, ws, kpdn1, "primary", src=a).json()
    assert (cleared["override"], cleared["effective_side"]) == (None, "primary")
    assert _bay_view(client, ws, kpdn1, src=b)["override"]["side"] == "primary"        # B keeps its own choice


def test_each_recordings_level1_reaches_only_its_own_non_overridden_bays(client):
    ws = _ws()
    a = _source(client, ws, v="primary", i="primary", stem="a")
    b = _source(client, ws, v="secondary", i="secondary", stem="b")
    k1 = _multi_bay(client, ws, "KPDN1", [(a, ("VA", "IA")), (b, ("VA", "IA"))])
    k2 = _multi_bay(client, ws, "KPDN2", [(a, ("VB", "IB")), (b, ("VB", "IB"))])
    _set_bay(client, ws, k1, "secondary", src=a)                             # K1/A pinned (A's Level 1 is Primary)
    eff = lambda ctx, src: _bay_view(client, ws, ctx, src=src)["effective_side"]  # noqa: E731
    assert (eff(k1, a), eff(k2, a), eff(k1, b), eff(k2, b)) == ("secondary", "primary", "secondary", "secondary")

    _set_rec(client, ws, a, "secondary")                                     # A's Level 1 changes
    assert (eff(k1, a), eff(k2, a)) == ("secondary", "secondary")            # K2/A follows; K1/A keeps its override
    assert _bay_view(client, ws, k1, src=a)["override"]["side"] == "secondary"
    assert (eff(k1, b), eff(k2, b)) == ("secondary", "secondary")            # B untouched
    assert _rec(client, ws, b)["engineer_correction"] is None

    _set_rec(client, ws, b, "primary")                                       # B's Level 1 changes
    assert (eff(k1, b), eff(k2, b)) == ("primary", "primary")                # both of B's bays follow B
    assert (eff(k1, a), eff(k2, a)) == ("secondary", "secondary")            # A's are untouched by B
    assert _bay_view(client, ws, k1, src=b)["inherited_recording_side"] == "primary"


def test_a_bay_setting_names_a_recording_the_bay_actually_holds(client):
    ws = _ws()
    a, b = _source(client, ws, stem="a"), _source(client, ws, stem="b")
    only_a = _bay(client, ws, a, ("VA", "IA"))
    resp = client.put(_assoc_url(ws, only_a, b), json={"side": "secondary"})
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "bay_has_no_measurement_channels")
    assert client.get(_assoc_url(ws, only_a, b)).status_code == 409
    assert client.put(_assoc_url(ws, only_a, "nope"), json={"side": "secondary"}).status_code == 404
    assert client.app.state.measurement_side_registry.count() == 0


# =========================================================================== genuine mixed sides


def test_mixed_phases_within_a_bay_are_reported_not_concealed(client):
    ws = _ws()
    src = _source(client, ws, ps={"VB": "S"})                              # VB declares Secondary, the rest Primary
    bay = _bay(client, ws, src, ("VA", "VB", "VC", "IA", "IB", "IC"))
    rec = _rec(client, ws, src)
    assert (rec["recording_derived"]["status"], rec["effective_side"], rec["authority"]) == ("mixed", None, AUTH_UNRESOLVED)
    assert "RECORDING_MIXED_SIDE_EVIDENCE" in _codes(rec)
    view = _bay_view(client, ws, bay)
    assert (view["status"], view["effective_side"]) == ("conflict", None)
    assert "BAY_MIXED_SIDES_WITHIN_QUANTITY" in _codes(view)
    assert _sides(view) == {"VA": "primary", "VB": "secondary", "VC": "primary", "IA": "primary", "IB": "primary", "IC": "primary"}
    assert {c["declared_side"] for c in view["channels"]} == {"primary", "secondary"}   # evidence kept, no file-wide value


def test_mixed_recording_blocks_a_consumer_that_spans_the_mix(client):
    ws = _ws()
    src = _source(client, ws, ps={"VB": "S"})
    deps = _deps(client)
    blocked = resolve_consumed_side(ws, [ChannelRef("source", src, f"ZBAY_{n}") for n in ("VA", "VB")], deps=deps)
    assert (blocked.status, blocked.side, blocked.usable) == ("conflict", None, False)
    ok = resolve_consumed_side(ws, [ChannelRef("source", src, f"ZBAY_{n}") for n in ("VA", "VC", "IA")], deps=deps)
    assert (ok.status, ok.side, ok.usable) == ("resolved", "primary", True)   # an unaffected selection still resolves


def test_engineer_resolves_a_mixed_recording_and_the_contradicting_declarations_stay_visible(client):
    ws = _ws()
    src = _source(client, ws, ps={"VB": "S"})
    bay = _bay(client, ws, src, _ALL)
    body = _set_rec(client, ws, src, "primary", note="VB flag mis-set by the recorder")
    assert (body["effective_side"], body["authority"]) == ("primary", AUTH_RECORDING_CORRECTION)
    assert "RECORDING_MIXED_SIDE_EVIDENCE" in _codes(body)                 # the contradiction is still reported
    override = next(d for d in body["diagnostics"] if d["code"] == "ENGINEER_CORRECTION_OVERRIDES_DECLARATION")
    assert override["detail"]["channels"] == "ZBAY_VB"
    assert {c["channel_name"]: c["declared_side"] for c in body["channels"]}["ZBAY_VB"] == "secondary"
    view = _bay_view(client, ws, bay)
    assert (view["status"], view["effective_side"]) == ("resolved", "primary")


def test_voltage_and_current_declaring_different_sides_inside_one_bay_is_resolved_not_blocked(client):
    ws = _ws()
    src = _source(client, ws, v="primary", i="secondary")
    bay = _bay(client, ws, src, _ALL)
    view = _bay_view(client, ws, bay)
    assert (view["status"], view["voltage_side"], view["current_side"], view["effective_side"]) == (
        "resolved", "primary", "secondary", None)
    assert (view["reference_sides"], view["strict_usable"]) == ("voltage_current_differ", True)
    assert "BAY_VOLTAGE_CURRENT_SIDES_DIFFER" in _codes(view)
    rec = _rec(client, ws, src)                                           # the recording itself: split, not mixed
    assert (rec["recording_derived"]["status"], rec["recording_derived"]["voltage_side"],
            rec["recording_derived"]["current_side"], rec["effective_side"]) == ("voltage_current_differ", "primary", "secondary", None)
    assert "RECORDING_VOLTAGE_CURRENT_SIDES_DIFFER" in _codes(rec) and "RECORDING_MIXED_SIDE_EVIDENCE" not in _codes(rec)
    assert not any(d["severity"] == "conflict" for d in view["diagnostics"])
    # Each channel resolves from its own evidence, so a consumer can normalise voltage and current independently.
    assert (_chan(client, ws, src, "VA")["effective_side"], _chan(client, ws, src, "IA")["effective_side"]) == (
        "primary", "secondary")


# =========================================================================== bay ownership


def test_channel_in_no_bay_follows_its_recording_and_names_never_create_a_bay(client):
    ws = _ws()
    src = _source(client, ws)
    _bay(client, ws, src, ("VA", "IA"))                                    # VB/IB look like siblings by name only
    free = _chan(client, ws, src, "VB")
    assert (free["bay_membership"], free["engineering_context_id"], free["bay_override_side"]) == ("none", None, None)
    assert (free["effective_side"], free["authority"]) == ("primary", AUTH_CHANNEL_DECLARED)


def test_unconfirmed_bay_membership_is_ambiguous_ownership_no_bay_setting_applies(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, ("VA", "IA"), status="suggested")
    view = _bay_view(client, ws, bay)
    assert (view["bay_membership"], view["context_status"]) == ("unconfirmed", "suggested")
    assert "BAY_MEMBERSHIP_UNCONFIRMED" in _codes(view)
    resp = _set_bay(client, ws, bay, "secondary")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "bay_membership_unconfirmed"
    assert _chan(client, ws, src, "VA")["bay_membership"] == "unconfirmed"
    # B2A-3: normal inheritance keeps working without confirming the bay (information, not a warning).
    assert (view["status"], view["effective_side"], view["strict_usable"]) == ("resolved", "primary", True)
    assert next(d for d in view["diagnostics"] if d["code"] == "BAY_MEMBERSHIP_UNCONFIRMED")["severity"] == "info"
    _set_rec(client, ws, src, "secondary")
    assert _bay_view(client, ws, bay)["effective_side"] == "secondary"         # follows Level 1 with no bay confirmation


def test_an_override_goes_inactive_when_its_bay_is_no_longer_confirmed(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, ("VA", "IA"))
    _set_bay(client, ws, bay, "secondary")
    assert client.patch(f"{_contexts(ws)}/{bay}", json={"status": "needs_review"}).status_code == 200
    view = _bay_view(client, ws, bay)
    assert (view["effective_side"], view["override"]["side"], view["override"]["active"]) == ("primary", "secondary", False)
    assert "BAY_OVERRIDE_INACTIVE_UNCONFIRMED_MEMBERSHIP" in _codes(view)
    client.patch(f"{_contexts(ws)}/{bay}", json={"status": "confirmed"})
    assert _bay_view(client, ws, bay)["effective_side"] == "secondary"     # re-confirmed: the engineer's choice applies again


def test_bay_without_voltage_or_current_channels_cannot_take_a_side(client):
    ws = _ws()
    _source(client, ws)
    empty = client.post(_contexts(ws), json={"display_name": "empty", "status": "manual", "members": []})
    assert empty.status_code == 201, empty.text
    ctx = empty.json()["id"]
    view = _context_view(client, ws, ctx)
    assert view["associations"] == [] and "BAY_HAS_NO_VOLTAGE_CURRENT_MEMBERS" in _codes(view)
    existing = client.get(f"/api/v1/workspaces/{ws}/measurement-side").json()["recordings"][0]["source_id"]
    resp = client.put(_assoc_url(ws, ctx, existing), json={"side": "primary"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "bay_has_no_measurement_channels"


# =========================================================================== CT/VT groups per bay


def test_different_ct_vt_groups_belong_to_different_bays_and_sides_stay_independent(client):
    ws = _ws()
    s1 = _source(client, ws, v="primary", i="primary", stem="one")
    s2 = _source(client, ws, v="secondary", i="secondary", stem="two")
    b1, b2 = _bay(client, ws, s1, _ALL), _bay(client, ws, s2, _ALL)
    for src, tag in ((s1, "1"), (s2, "2")):
        _group(client, ws, src, KIND_VOLTAGE, V, f"vg-{tag}")
        _group(client, ws, src, KIND_CURRENT, I, f"ig-{tag}")
        _vt(client, ws, f"vg-{tag}", VT_P, VT_S, note="VT")
        _ct(client, ws, f"ig-{tag}", CT_P, CT_S, note="CT")
    v1, v2 = _bay_view(client, ws, b1), _bay_view(client, ws, b2)
    assert (v1["voltage_group_ids"], v1["current_group_ids"]) == (["vg-1"], ["ig-1"])
    assert (v2["voltage_group_ids"], v2["current_group_ids"]) == (["vg-2"], ["ig-2"])
    assert (v1["effective_side"], v2["effective_side"]) == ("primary", "secondary")
    _set_bay(client, ws, b1, "secondary")
    assert (_bay_view(client, ws, b1)["effective_side"], _bay_view(client, ws, b2)["effective_side"]) == ("secondary", "secondary")
    assert _bay_view(client, ws, b2)["override"] is None                   # b1's override did not touch b2
    groups_untouched = client.app.state.current_group_config_registry.get(ws, "ig-1")
    assert (groups_untouched.ct_primary_a, groups_untouched.ct_secondary_a) == (CT_P, CT_S)   # the side never edits a ratio


# =========================================================================== isolation


def test_workspaces_are_isolated(client):
    ws1, ws2 = _ws(), _ws()
    s1 = _source(client, ws1)
    s2 = _source(client, ws2)
    b1, b2 = _bay(client, ws1, s1, ("VA", "IA")), _bay(client, ws2, s2, ("VA", "IA"))
    _set_rec(client, ws1, s1, "secondary")
    _set_bay(client, ws1, b1, "primary")                                   # Level 1 is now secondary, so this is an override
    assert _rec(client, ws2, s2)["engineer_correction"] is None
    assert _bay_view(client, ws2, b2)["effective_side"] == "primary" and _bay_view(client, ws2, b2)["override"] is None
    # Identifiers never resolve across workspaces.
    assert client.get(f"/api/v1/workspaces/{ws2}/sources/{s1}/measurement-side").status_code == 404
    assert client.get(f"{_contexts(ws2)}/{b1}/measurement-side").status_code == 404
    assert client.put(f"/api/v1/workspaces/{ws2}/sources/{s1}/measurement-side", json={"side": "primary"}).status_code == 404
    cross = client.get(_url(ws2, "/channel"), params={"source_id": s1, "channel_name": "ZBAY_VA"}).json()
    assert (cross["effective_side"], cross["usable"]) == ("unknown", False)
    overview = client.get(_url(ws2)).json()
    assert [r["source_id"] for r in overview["recordings"]] == [s2] and [b["engineering_context_id"] for b in overview["bays"]] == [b2]


def test_two_recordings_in_one_workspace_keep_separate_corrections(client):
    ws = _ws()
    s1, s2 = _source(client, ws, stem="a"), _source(client, ws, stem="b")
    _set_rec(client, ws, s1, "secondary")
    assert _rec(client, ws, s2)["engineer_correction"] is None
    assert _rec(client, ws, s2)["effective_side"] == "primary"


# =========================================================================== lifecycle


def test_removing_a_source_removes_its_correction_and_a_reupload_starts_clean(client):
    ws = _ws()
    src = _source(client, ws, stem="first")
    _set_rec(client, ws, src, "secondary")
    assert client.app.state.measurement_side_registry.count() == 1
    assert client.delete(f"/api/v1/workspaces/{ws}/sources/{src}").status_code == 204
    assert client.app.state.measurement_side_registry.count() == 0
    assert client.get(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-side").status_code == 404
    again = _source(client, ws, stem="first")
    assert again != src
    body = _rec(client, ws, again)
    assert (body["engineer_correction"], body["effective_side"], body["authority"]) == (None, "primary", AUTH_CHANNEL_DECLARED)


def test_bay_override_follows_the_life_of_its_bay_and_its_recording(client):
    ws = _ws()
    s1, s2 = _source(client, ws, stem="a"), _source(client, ws, stem="b")
    survivor = _bay(client, ws, s1, ("VA", "IA"))
    spanning = _multi_bay(client, ws, "span", [(s1, ("VB",)), (s2, ("VB",))])
    only_s2 = _bay(client, ws, s2, ("VA", "IA"))
    _set_bay(client, ws, survivor, "secondary", src=s1)
    _set_bay(client, ws, spanning, "secondary", src=s1)
    _set_bay(client, ws, spanning, "secondary", src=s2)
    _set_bay(client, ws, only_s2, "secondary", src=s2)
    registry = client.app.state.measurement_side_registry
    assert registry.count() == 4
    client.delete(f"/api/v1/workspaces/{ws}/sources/{s2}")                   # empties only_s2, reduces `spanning`
    assert registry.get_bay(ws, only_s2, s2) is None and registry.get_bay(ws, spanning, s2) is None
    assert registry.get_bay(ws, spanning, s1) is not None and registry.get_bay(ws, survivor, s1) is not None
    client.delete(f"{_contexts(ws)}/{spanning}")                             # deleting a bay releases every override of it
    assert registry.get_bay(ws, spanning, s1) is None and registry.get_bay(ws, survivor, s1) is not None


def test_removing_a_recording_from_a_bay_releases_that_recordings_override_only(client):
    ws = _ws()
    a, b = _source(client, ws, stem="a"), _source(client, ws, stem="b")
    k1 = _multi_bay(client, ws, "KPDN1", [(a, ("VA", "IA")), (b, ("VA", "IA"))])
    _set_bay(client, ws, k1, "secondary", src=a)
    _set_bay(client, ws, k1, "primary", src=b)
    registry = client.app.state.measurement_side_registry
    members = [{"channel_ref": _ref(a, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"} for n in ("VA", "IA")]
    assert client.patch(f"{_contexts(ws)}/{k1}", json={"members": members}).status_code == 200   # B leaves the bay
    assert registry.get_bay(ws, k1, b) is None and registry.get_bay(ws, k1, a) is not None
    assert [x["source_id"] for x in _context_view(client, ws, k1)["associations"]] == [a]


def test_workspace_reset_clears_everything(client):
    ws, other = _ws(), _ws()
    src, keep = _source(client, ws), _source(client, other)
    bay = _bay(client, ws, src, ("VA", "IA"))
    _set_rec(client, ws, src, "secondary")
    _set_rec(client, other, keep, "secondary")
    assert client.delete(f"/api/v1/workspaces/{ws}").status_code == 204
    registry = client.app.state.measurement_side_registry
    assert registry.get_recording(ws, src) is None and registry.count() == 1     # the other workspace is untouched
    assert registry.get_recording(other, keep) is not None


def test_configuration_is_in_memory_only(client, settings):
    ws = _ws()
    src = _source(client, ws)
    _set_rec(client, ws, src, "secondary")
    with TestClient(create_app(settings)) as fresh:                       # a new app instance: nothing carried over
        assert fresh.app.state.measurement_side_registry.count() == 0


# =========================================================================== the shared resolver contract


def test_resolver_returns_side_authority_and_diagnostics_and_never_raises(client):
    ws = _ws()
    src = _source(client, ws)
    deps = _deps(client)
    res = resolve_effective_measurement_side(ws, src, "ZBAY_VA", deps=deps)
    assert (res.side, res.authority, res.usable, res.declared_side) == ("primary", AUTH_CHANNEL_DECLARED, True, "primary")
    missing_channel = resolve_effective_measurement_side(ws, src, "NOPE", deps=deps)
    assert (missing_channel.usable, {d.code for d in missing_channel.diagnostics}) == (False, {"CHANNEL_NOT_FOUND"})
    missing_source = resolve_effective_measurement_side(ws, "nope", "ZBAY_VA", deps=deps)
    assert {d.code for d in missing_source.diagnostics} == {"SOURCE_NOT_FOUND"} and not missing_source.usable
    calc = resolve_effective_side_for_ref(ws, ChannelRef(kind="calculated", calculated_channel_id="calc-1"), deps=deps)
    assert not calc.usable and {d.code for d in calc.diagnostics} == {"CALCULATED_CHANNEL_NOT_RESOLVED"}


def test_resolver_is_stateless_so_changes_reach_every_consumer_immediately(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, ("VA", "IA"))
    deps = _deps(client)
    ref = ChannelRef("source", src, "ZBAY_VA")
    assert resolve_effective_side_for_ref(ws, ref, deps=deps).side == "primary"
    _set_rec(client, ws, src, "secondary")
    assert resolve_effective_side_for_ref(ws, ref, deps=deps).side == "secondary"
    _set_bay(client, ws, bay, "primary")
    now = resolve_effective_side_for_ref(ws, ref, deps=deps)
    assert (now.side, now.authority, now.context_id) == ("primary", AUTH_BAY_OVERRIDE, bay)
    # An API read and a direct resolver call can never disagree.
    api = _chan(client, ws, src, "VA")
    assert (api["effective_side"], api["authority"]) == (now.side, now.authority)


def test_consumed_side_requires_every_channel_to_agree_and_resolve(client):
    ws = _ws()
    src = _source(client, ws, v="primary", i="secondary")
    deps = _deps(client)
    refs = lambda *n: [ChannelRef("source", src, f"ZBAY_{x}") for x in n]  # noqa: E731
    assert resolve_consumed_side(ws, refs("VA", "VB", "VC"), deps=deps).side == "primary"
    cross = resolve_consumed_side(ws, refs("VA", "IA"), deps=deps)             # B2A-1: independent V/I sides are usable
    assert (cross.status, cross.side, cross.voltage_side, cross.current_side, cross.usable, cross.strict_usable) == (
        "resolved", None, "primary", "secondary", True, True)
    assert "CONSUMED_VOLTAGE_CURRENT_SIDES_DIFFER" in {d.code for d in cross.diagnostics}
    assert cross.reference_sides == "voltage_current_differ"
    unknown = resolve_consumed_side(ws, refs("VA") + [ChannelRef("source", src, "NOPE")], deps=deps)
    assert (unknown.status, unknown.usable) == ("unresolved", False)


def test_missing_evidence_is_never_inferred_from_ratios_or_magnitude(client):
    """B2A-4: a recording with no P/S declaration needs an engineer's Level 1 value, whatever CT/VT or magnitude says."""
    ws = _ws()
    cfg, dat = _comtrade(v_rms=66.0, i_rms=2.0, ps=_flags("none", "none"))        # secondary-looking magnitudes
    src = _upload(client, ws, cfg, dat)
    _clear(client, ws)
    bay = _bay(client, ws, src, _ALL)
    _group(client, ws, src, KIND_VOLTAGE, V, "vg-1")
    _group(client, ws, src, KIND_CURRENT, I, "ig-1")
    _vt(client, ws, "vg-1", VT_P, VT_S, note="VT")                                 # a configured VT/CT is not side evidence
    _ct(client, ws, "ig-1", CT_P, CT_S, note="CT")
    rec, view = _rec(client, ws, src), _bay_view(client, ws, bay)
    assert (rec["effective_side"], rec["authority"], rec["recording_derived"]["status"]) == (None, AUTH_UNRESOLVED, "none")
    assert (view["status"], view["effective_side"], view["strict_usable"]) == ("unresolved", None, False)
    assert not resolve_consumed_side(ws, [ChannelRef("source", src, "ZBAY_VA")], deps=_deps(client)).strict_usable
    _set_rec(client, ws, src, "secondary")                                         # the engineer's value is the authority
    assert _bay_view(client, ws, bay)["strict_usable"] is True


def test_explicit_correction_is_consumable_and_fully_disclosed(client):
    """B2A-5: a correction supersedes a wrong declaration, keeps the original evidence and a visible warning, and
    the warning alone never blocks a strict consumer."""
    ws = _ws()
    src = _source(client, ws, v="primary", i="primary")                            # recorder says Primary ...
    bay = _bay(client, ws, src, _ALL)
    body = _set_rec(client, ws, src, "secondary", note="Relay exports secondary quantities")   # ... engineer knows it is not
    assert body["engineer_correction"]["set_at"] and body["engineer_correction"]["note"]
    assert (body["effective_side"], body["authority"]) == ("secondary", AUTH_RECORDING_CORRECTION)
    warn = next(d for d in body["diagnostics"] if d["code"] == "ENGINEER_CORRECTION_OVERRIDES_DECLARATION")
    assert warn["severity"] == "warning"
    assert sorted(o["channel_name"] for o in body["overridden_declarations"]) == sorted(f"ZBAY_{n}" for n in _ALL)
    assert {(o["declared_side"], o["effective_side"]) for o in body["overridden_declarations"]} == {("primary", "secondary")}
    view = _bay_view(client, ws, bay)
    assert (view["status"], view["strict_usable"], view["effective_side"]) == ("resolved", True, "secondary")
    assert len(view["overridden_declarations"]) == 6
    consumed = resolve_consumed_side(ws, [ChannelRef("source", src, f"ZBAY_{n}") for n in _ALL], deps=_deps(client))
    assert (consumed.status, consumed.side, consumed.strict_usable) == ("resolved", "secondary", True)
    # The original evidence is still reported untouched.
    assert body["recording_derived"]["side"] == "primary" and {c["declared_side"] for c in body["channels"]} == {"primary"}
    # The correction's contradiction stays disclosed even when a bay setting later takes over every channel.
    _set_bay(client, ws, bay, "primary")
    pinned = _rec(client, ws, src)
    assert {c["authority"] for c in pinned["channels"]} == {AUTH_BAY_OVERRIDE}
    assert len(pinned["overridden_declarations"]) == 6


# =========================================================================== Confirm bay is a status change only


def test_confirming_a_bay_changes_its_status_and_nothing_else(client):
    """Confirm bay promotes a suggested/needs-review bay explicitly; it never edits membership, phases or the evidence
    behind them, and the Analysis input resolution of the bay is identical before and after."""
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, _ALL, status="needs_review")
    before = client.get(f"{_contexts(ws)}/{bay}").json()
    kinds = [("phasor", "voltage_three_phase"), ("phasor", "voltage_phase_a")]
    resolved_before = [client.get(f"{_contexts(ws)}/{bay}/input-resolution", params={"analysis_kind": k, "mode": m}).json()
                       for k, m in kinds]
    assert _set_bay(client, ws, bay, "secondary").status_code == 409          # not before it is confirmed
    assert client.patch(f"{_contexts(ws)}/{bay}", json={"status": "confirmed"}).status_code == 200
    after = client.get(f"{_contexts(ws)}/{bay}").json()
    assert after["status"] == "confirmed"
    assert {k: v for k, v in after.items() if k != "status"} == {k: v for k, v in before.items() if k != "status"}
    assert [m["phase_source"] for m in after["members"]] == [m["phase_source"] for m in before["members"]]
    assert [client.get(f"{_contexts(ws)}/{bay}/input-resolution", params={"analysis_kind": k, "mode": m}).json()
            for k, m in kinds] == resolved_before
    assert [c["id"] for c in client.get(_contexts(ws)).json()] == [bay]        # still listed for Analysis, same bay
    assert _set_bay(client, ws, bay, "secondary").status_code == 200           # now it can take a manual side


# =========================================================================== CT/VT groups spanning bays


def _ownership(view, group_id):
    return next(o for o in view["group_ownership"] if o["group_id"] == group_id)


def test_a_group_inside_one_bay_or_no_bay_is_unremarkable(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, _ALL)
    _group(client, ws, src, KIND_VOLTAGE, V, "vg-1")
    view = _bay_view(client, ws, bay)
    assert _ownership(view, "vg-1")["status"] == "single_bay" and not _ownership(view, "vg-1")["conversion_authority_ambiguous"]
    assert not {"GROUP_SPANS_BAYS", "GROUP_SPANS_BAYS_AMBIGUOUS"} & _codes(view)
    ws2 = _ws()
    src2 = _source(client, ws2)
    _group(client, ws2, src2, KIND_VOLTAGE, V, "vg-9")
    assert client.app.state.measurement_group_registry.get(ws2, "vg-9") is not None
    from app.services.measurement_side_service import build_group_ownership
    assert build_group_ownership(ws2, "vg-9", deps=_deps(client)).status == "no_bay"


def test_a_group_shared_by_bays_on_one_side_is_flagged_but_not_ambiguous(client):
    ws = _ws()
    src = _source(client, ws)
    b1, b2 = _bay(client, ws, src, ("VA", "IA")), _bay(client, ws, src, ("VB", "IB"))
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB"), "bus-vt")             # one busbar VT serving both feeders
    for bay in (b1, b2):
        view = _bay_view(client, ws, bay)
        owner = _ownership(view, "bus-vt")
        assert (owner["status"], owner["conversion_authority_ambiguous"]) == ("spans_bays", False)
        assert sorted(x["display_name"] for x in owner["bays"]) == ["bay-VA", "bay-VB"]
        assert {"GROUP_SPANS_BAYS"} <= _codes(view) and "GROUP_SPANS_BAYS_AMBIGUOUS" not in _codes(view)
        assert view["strict_usable"] is True
    consumed = resolve_consumed_side(ws, [ChannelRef("source", src, "ZBAY_VA")], deps=_deps(client))
    assert (consumed.strict_usable, consumed.conversion_authority) == (True, "unambiguous")


def test_a_group_spanning_bays_on_different_sides_blocks_conversion_instead_of_borrowing(client):
    ws = _ws()
    src = _source(client, ws)                                                 # recording declares Primary everywhere
    b1, b2 = _bay(client, ws, src, ("VA", "IA")), _bay(client, ws, src, ("VB", "IB"))
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB"), "bus-vt")
    _group(client, ws, src, KIND_CURRENT, ("IC",), "ct-c")                    # unrelated group, unaffected
    _vt(client, ws, "bus-vt", VT_P, VT_S, note="VT")
    assert _set_bay(client, ws, b1, "secondary").status_code == 200            # the two bays now sit on different sides
    view = _bay_view(client, ws, b2)
    owner = _ownership(view, "bus-vt")
    assert (owner["status"], owner["conversion_authority_ambiguous"]) == ("spans_bays_ambiguous", True)
    assert "GROUP_SPANS_BAYS_AMBIGUOUS" in _codes(view)
    assert next(d for d in view["diagnostics"] if d["code"] == "GROUP_SPANS_BAYS_AMBIGUOUS")["severity"] == "conflict"
    assert view["strict_usable"] is False                                       # the bay's side is known; its conversion is not
    assert view["effective_side"] == "primary"
    deps = _deps(client)
    one = resolve_consumed_side(ws, [ChannelRef("source", src, "ZBAY_VB")], deps=deps)
    assert (one.status, one.side, one.usable, one.strict_usable) == ("resolved", "primary", True, False)
    assert (one.conversion_authority, one.ownership_ambiguous_groups) == ("ambiguous", ("bus-vt",))
    assert "CONSUMED_GROUP_SPANS_BAYS_AMBIGUOUS" in {d.code for d in one.diagnostics}
    clean = resolve_consumed_side(ws, [ChannelRef("source", src, "ZBAY_IC")], deps=deps)
    assert (clean.strict_usable, clean.conversion_authority) == (True, "unambiguous")   # an unrelated group still converts
    # the transformer ratio itself is untouched: nothing is borrowed, nothing is edited
    config = client.app.state.voltage_group_config_registry.get(ws, "bus-vt")
    assert (config.vt_primary_v, config.vt_secondary_v) == (VT_P, VT_S)


def test_a_group_spanning_bays_with_an_unresolved_side_is_ambiguous_too(client):
    ws = _ws()
    src = _source(client, ws, v="none", i="none")                              # nothing declared anywhere
    b1, b2 = _bay(client, ws, src, ("VA", "IA")), _bay(client, ws, src, ("VB", "IB"))
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB"), "bus-vt")
    owner = _ownership(_bay_view(client, ws, b1), "bus-vt")
    assert owner["status"] == "spans_bays_ambiguous" and owner["conversion_authority_ambiguous"] is True
    _set_rec(client, ws, src, "primary")                                       # the engineer resolves it: no longer ambiguous
    owner = _ownership(_bay_view(client, ws, b2), "bus-vt")
    assert (owner["status"], owner["conversion_authority_ambiguous"]) == ("spans_bays", False)


# =========================================================================== API contract


def test_api_validation_and_not_found_shapes(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, ("VA", "IA"))
    base = f"/api/v1/workspaces/{ws}/sources/{src}/measurement-side"
    assert client.put(base, json={"side": "unknown"}).status_code == 422
    assert client.put(base, json={"side": "PRIMARY"}).status_code == 422
    assert client.put(base, json={}).status_code == 422
    assert client.put(base, json={"side": "primary", "note": "x" * 501}).status_code == 422
    assert _set_bay(client, ws, bay, None).status_code == 422               # no reset: null is not a bay value
    assert _set_bay(client, ws, bay, "unknown").status_code == 422
    miss = client.put(f"/api/v1/workspaces/{ws}/sources/nope/measurement-side", json={"side": "primary"})
    assert (miss.status_code, miss.json()["detail"]["code"]) == (404, "source_not_found")
    miss = _set_bay(client, ws, "ec-nope", "primary")
    assert (miss.status_code, miss.json()["detail"]["code"]) == (404, "engineering_context_not_found")
    assert client.get(f"/api/v1/workspaces/{ws}/measurement-side").json()["workspace_id"] == ws
    assert client.get(_url("  ")).status_code in (400, 404)


def test_overview_lists_recordings_and_bays_without_channel_detail(client):
    ws = _ws()
    src = _source(client, ws)
    bay = _bay(client, ws, src, ("VA", "IA"))
    body = client.get(_url(ws)).json()
    assert body["recordings"][0]["channels"] is None and body["bays"][0]["channels"] is None
    assert body["bays"][0]["engineering_context_id"] == bay
    assert body["recordings"][0]["bay_ids"] == [bay]


# =========================================================================== existing results unchanged


def _snapshot(client, ws, src, ctx):
    """Every existing PU / protection response this slice must not move."""
    calls = [
        ("oc", lambda: _oc(client, ws, ctx)),
        ("imp_legacy", lambda: _imp(client, ws, ctx, recording_basis="primary", impedance_basis="primary")),
        ("imp_strict", lambda: _imp(client, ws, ctx, **_strict("primary", "primary", "primary"))),
        ("context_oc", lambda: client.get(f"{_contexts(ws)}/{ctx}/protection-instrument-context",
                                          params={"analysis": "overcurrent", "phase": "A"})),
        ("pu_coverage", lambda: client.get(f"/api/v1/workspaces/{ws}/per-unit/sources/{src}/coverage")),
        ("channels", lambda: client.get(f"/api/v1/workspaces/{ws}/sources/{src}")),
        ("groups", lambda: client.get(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups")),
    ]
    return {name: (r.status_code, json.dumps(r.json(), sort_keys=True)) for name, call in calls for r in [call()]}


def test_existing_pu_and_protection_results_are_unchanged_by_side_configuration(client):
    ws = _ws()
    src = _source(client, ws)
    ctx = _bay(client, ws, src, _ALL)
    _group(client, ws, src, KIND_VOLTAGE, V, "vg-1")
    _group(client, ws, src, KIND_CURRENT, I, "ig-1")
    _vt(client, ws, "vg-1", VT_P, VT_S, note="VT")
    _ct(client, ws, "ig-1", CT_P, CT_S, note="CT")
    before = _snapshot(client, ws, src, ctx)
    assert before["oc"][0] == 200 and before["imp_legacy"][0] == 200            # the oracle itself is meaningful
    _set_rec(client, ws, src, "secondary", note="correction")
    assert _snapshot(client, ws, src, ctx) == before
    assert _set_bay(client, ws, ctx, "primary").status_code == 200
    assert _snapshot(client, ws, src, ctx) == before
    _set_rec(client, ws, src, None)
    _set_bay(client, ws, ctx, "secondary")
    assert _snapshot(client, ws, src, ctx) == before
