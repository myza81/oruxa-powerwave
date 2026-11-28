"""D5A-UI-002: unified measurement-side configuration -- Level 1 per recording, Level 2 per MEASUREMENT GROUP.

A Voltage group and a Current group are two groups and two independent settings (Primary voltage with Secondary current is
legitimate); Engineering Context membership and status play no part in the side. Real app, real ASCII-COMTRADE uploads
whose per-channel P/S flags are the original recording evidence. Expected sides/authorities are stated by hand from the
owner's rules, never read back from the code under test. The last section proves no existing PU or protection result
changes.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.domain.measurement_side_config import (
    AUTH_CHANNEL_DECLARED,
    AUTH_GROUP_OVERRIDE,
    AUTH_RECORDING_CORRECTION,
    AUTH_RECORDING_DEFAULT,
    AUTH_UNRESOLVED,
    EVIDENCE_CONSISTENT,
    EVIDENCE_MIXED,
    EVIDENCE_NONE,
    ChannelSideEvidence,
    ChannelSideResolution,
    GroupSideState,
    RecordingSideDerivation,
    derive_recording_side,
    group_override_is_redundant,
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
    CT_P, CT_S, VT_P, VT_S, _ALL, _comtrade, _imp, _strict, _upload,
)

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
    _clear(client, ws)                     # drop auto-suggested contexts/groups: each test builds its own
    return src


def _groups(client, ws, src, tag="g"):
    """One Voltage and one Current Measurement Group (ids `<tag>-v`, `<tag>-i`) over the recording's phases."""
    _group(client, ws, src, KIND_VOLTAGE, V, f"{tag}-v")
    _group(client, ws, src, KIND_CURRENT, I, f"{tag}-i")
    return f"{tag}-v", f"{tag}-i"


def _bay(client, ws, parts, *, status="manual", name="bay") -> str:
    """One Engineering Context over channels of one or several recordings: parts = [(source_id, ("VA", "IA")), ...]."""
    members = [{"channel_ref": _ref(src, f"ZBAY_{n}"), "phase": n[1], "phase_source": "engineer_confirmed"}
               for src, names in parts for n in names]
    resp = client.post(_contexts(ws), json={"display_name": name, "status": status, "members": members})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _url(ws, tail=""):
    return f"/api/v1/workspaces/{ws}/measurement-side{tail}"


def _rec_url(ws, src):
    return f"/api/v1/workspaces/{ws}/sources/{src}/measurement-side"


def _grp_url(ws, src, gid):
    return f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups/{gid}/measurement-side"


def _rec(client, ws, src):
    resp = client.get(_rec_url(ws, src))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_rec(client, ws, src, side, note=None):
    resp = client.put(_rec_url(ws, src), json={"side": side, "note": note})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _gv(client, ws, src, gid):
    resp = client.get(_grp_url(ws, src, gid))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_g(client, ws, src, gid, side):
    return client.put(_grp_url(ws, src, gid), json={"side": side})


def _put(client, ws, src, gid, side):
    resp = _set_g(client, ws, src, gid, side)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _chan(client, ws, src, name):
    resp = client.get(_url(ws, "/channel"), params={"source_id": src, "channel_name": f"ZBAY_{name}"})
    assert resp.status_code == 200, resp.text
    return resp.json()


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
    within = derive_recording_side(ev + [_ev("vc", "secondary")])
    assert (within.status, within.voltage_side) == ("mixed", None)
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
    assert recording_correction_to_store(selected, RecordingSideDerivation(derived_status, derived_side)) == expected


def test_confirming_the_inferred_side_of_partial_evidence_is_kept():
    partial = RecordingSideDerivation(EVIDENCE_CONSISTENT, "secondary", undeclared_count=2)
    assert recording_correction_to_store("secondary", partial) == "secondary"     # engineer confirmation, not redundant
    assert recording_correction_to_store("primary", partial) == "primary"
    assert recording_correction_to_store(None, partial) is None


def _state(declared, engineer=None):
    evidence = [_ev(f"c{n}", s) for n, s in enumerate(declared)]
    return resolve_recording_state(derive_recording_side(evidence), engineer, evidence)


@pytest.mark.parametrize("declared,engineer,channel,group,expected_side,expected_auth", [
    # precedence: group override > recording correction > channel declaration > recording default > unresolved
    ("primary", None, "primary", None, "primary", AUTH_CHANNEL_DECLARED),
    ("secondary", None, "secondary", None, "secondary", AUTH_CHANNEL_DECLARED),
    ("primary", "secondary", "primary", None, "secondary", AUTH_RECORDING_CORRECTION),
    ("primary", "secondary", "primary", "primary", "primary", AUTH_GROUP_OVERRIDE),
    ("primary", None, "primary", "secondary", "secondary", AUTH_GROUP_OVERRIDE),
    ("primary", None, "unknown", None, "primary", AUTH_RECORDING_DEFAULT),
    ("unknown", None, "unknown", None, "unknown", AUTH_UNRESOLVED),
    ("unknown", "primary", "unknown", None, "primary", AUTH_RECORDING_CORRECTION),
    ("unknown", None, "unknown", "secondary", "secondary", AUTH_GROUP_OVERRIDE),
])
def test_channel_precedence_oracle(declared, engineer, channel, group, expected_side, expected_auth):
    evidence = [_ev("other", declared), _ev("subject", channel)]
    state = resolve_recording_state(derive_recording_side(evidence), engineer, evidence)
    res = resolve_channel_side(evidence[1], state, GroupSideState("mg-1", group))
    assert (res.side, res.authority) == (expected_side, expected_auth)
    assert res.declared_side == channel                          # the original evidence is never altered
    assert (res.group_id, res.group_override_side) == ("mg-1", group)


def _res(name, side, quantity="voltage", authority=AUTH_CHANNEL_DECLARED):
    return ChannelSideResolution(name, quantity, side, authority if side != "unknown" else AUTH_UNRESOLVED, side,
                                 None, AUTH_UNRESOLVED)


def test_side_set_oracle():
    ok = resolve_side_set([_res("a", "primary"), _res("b", "primary"), _res("c", "primary")])
    assert (ok.status, ok.side, ok.voltage_side, ok.current_side) == ("resolved", "primary", "primary", None)
    within = resolve_side_set([_res("a", "primary"), _res("b", "secondary")])
    assert (within.status, within.side) == ("conflict", None)
    assert "GROUP_MIXED_SIDES" in {d.code for d in within.diagnostics}
    # Voltage Primary + current Secondary is a legitimate mixed reference (only reachable for a consumed set).
    vi = resolve_side_set([_res("a", "primary"), _res("b", "primary"), _res("ia", "secondary", "current")])
    assert (vi.status, vi.side, vi.voltage_side, vi.current_side, vi.usable, vi.reference_sides) == (
        "resolved", None, "primary", "secondary", True, "voltage_current_differ")
    assert next(d for d in vi.diagnostics if d.code == "CONSUMED_VOLTAGE_CURRENT_SIDES_DIFFER").severity == "info"
    both = resolve_side_set([_res("a", "primary"), _res("b", "secondary"), _res("ia", "secondary", "current")])
    assert (both.status, both.side, both.usable) == ("conflict", None, False)
    part = resolve_side_set([_res("a", "primary"), _res("b", "unknown")])
    assert (part.status, part.side) == ("unresolved", None)       # never guessed from the channels that did resolve
    assert resolve_side_set([]).status == "not_applicable"


def _resolved(declared, engineer=None):
    evidence = [_ev(f"c{n}", s) for n, s in enumerate(declared)]
    state = resolve_recording_state(derive_recording_side(evidence), engineer, evidence)
    return [resolve_channel_side(e, state) for e in evidence]


@pytest.mark.parametrize("selected,declared,engineer,redundant", [
    ("primary", ["primary"] * 3, None, True),                  # reliable evidence already gives it: follow Level 1 again
    ("secondary", ["primary"] * 3, None, False),               # a real override
    ("secondary", ["primary"] * 3, "secondary", True),         # the engineer's recording correction already gives it
    ("primary", ["primary"] * 3, "secondary", False),          # would expose the contradiction again: keep it
    ("primary", ["primary", "primary", "unknown"], None, False),  # one channel would only be inferred: keep the confirmation
    ("primary", ["primary", "secondary"], None, False),        # mixed declarations: the engineer's choice must be kept
    ("primary", ["unknown"] * 3, None, False),                 # nothing resolves without it
])
def test_group_override_redundancy_oracle(selected, declared, engineer, redundant):
    assert group_override_is_redundant(selected, _resolved(declared, engineer)) is redundant


def test_group_override_redundancy_edge_cases():
    assert group_override_is_redundant("primary", []) is False       # an empty group has nothing to follow
    for bad in ("", "unknown", "PRIMARY", None):
        with pytest.raises(ValueError):
            group_override_is_redundant(bad, _resolved(["primary"]))


# =========================================================================== File Primary / File Secondary


@pytest.mark.parametrize("side", ["primary", "secondary"])
def test_file_side_flows_to_every_group(client, side):
    ws = _ws()
    src = _source(client, ws, v=side, i=side)
    gv, gi = _groups(client, ws, src)
    rec = _rec(client, ws, src)
    assert rec["recording_derived"] == {"status": "consistent", "side": side, "voltage_side": side, "current_side": side,
                                        "primary_channels": 6 if side == "primary" else 0,
                                        "secondary_channels": 0 if side == "primary" else 6, "undeclared_channels": 0,
                                        "evidence_channels": 6}
    assert (rec["effective_side"], rec["authority"], rec["engineer_correction"]) == (side, AUTH_CHANNEL_DECLARED, None)
    assert sorted(rec["group_ids"]) == sorted([gv, gi])
    for gid, kind in ((gv, "voltage"), (gi, "current")):
        view = _gv(client, ws, src, gid)
        assert (view["kind"], view["status"], view["effective_side"], view["inherited_side"], view["override"]) == (
            kind, "resolved", side, side, None)
        assert {c["authority"] for c in view["channels"]} == {AUTH_CHANNEL_DECLARED}


# =========================================================================== independent Voltage / Current settings


@pytest.mark.parametrize("v_side,i_side", [
    ("primary", "primary"), ("primary", "secondary"), ("secondary", "primary"), ("secondary", "secondary"),
])
def test_voltage_and_current_group_sides_are_independent_in_all_four_combinations(client, v_side, i_side):
    ws = _ws()
    src = _source(client, ws, v="primary", i="primary")
    gv, gi = _groups(client, ws, src)
    _put(client, ws, src, gv, v_side)
    _put(client, ws, src, gi, i_side)
    vv, vi = _gv(client, ws, src, gv), _gv(client, ws, src, gi)
    assert (vv["effective_side"], vi["effective_side"]) == (v_side, i_side)
    # Only a side that differs from what the recording declares is stored as an override.
    assert (vv["override"] is not None, vi["override"] is not None) == (v_side != "primary", i_side != "primary")
    # Mixed references are NOT a conflict anywhere: each channel resolves, and the bay-level combination is usable.
    assert (vv["status"], vi["status"]) == ("resolved", "resolved")
    refs = [ChannelRef("source", src, f"ZBAY_{n}") for n in ("VA", "IA")]
    consumed = resolve_consumed_side(ws, refs, deps=_deps(client))
    assert (consumed.usable, consumed.voltage_side, consumed.current_side) == (True, v_side, i_side)
    assert consumed.reference_sides == ("uniform" if v_side == i_side else "voltage_current_differ")
    assert "CONSUMED_VOLTAGE_CURRENT_SIDES_DIFFER" in {d.code for d in consumed.diagnostics} or v_side == i_side
    # The shared per-channel resolver reports each channel from its own group.
    assert _chan(client, ws, src, "VB")["effective_side"] == v_side
    assert _chan(client, ws, src, "IB")["effective_side"] == i_side


def test_changing_the_voltage_group_never_changes_the_current_group_and_back(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    _put(client, ws, src, gv, "secondary")
    current = _gv(client, ws, src, gi)
    assert (current["effective_side"], current["override"], current["authority"]) == ("primary", None, AUTH_CHANNEL_DECLARED)
    _put(client, ws, src, gi, "secondary")
    _put(client, ws, src, gv, "primary")                       # back to the declared side: the voltage override goes ...
    assert _gv(client, ws, src, gv)["override"] is None
    assert _gv(client, ws, src, gi)["override"]["side"] == "secondary"   # ... the current override is untouched
    assert client.app.state.measurement_side_registry.group_keys(ws) == [(src, gi)]


def test_two_groups_of_one_kind_in_one_bay_have_independent_overrides(client):
    ws = _ws()
    src = _source(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA",), "vg-a")
    _group(client, ws, src, KIND_VOLTAGE, ("VB", "VC"), "vg-b")
    _group(client, ws, src, KIND_CURRENT, I, "ig-1")
    _bay(client, ws, [(src, _ALL)], name="one bay")
    _put(client, ws, src, "vg-a", "secondary")
    assert _gv(client, ws, src, "vg-a")["effective_side"] == "secondary"
    b = _gv(client, ws, src, "vg-b")
    assert (b["effective_side"], b["override"]) == ("primary", None)
    assert _chan(client, ws, src, "VB")["effective_side"] == "primary"
    assert _chan(client, ws, src, "VA")["effective_side"] == "secondary"
    _put(client, ws, src, "vg-b", "secondary")
    _put(client, ws, src, "vg-a", "primary")
    assert (_gv(client, ws, src, "vg-a")["effective_side"], _gv(client, ws, src, "vg-b")["effective_side"]) == ("primary", "secondary")


def test_a_group_override_covers_every_phase_of_its_group_and_nothing_else(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    view = _put(client, ws, src, gv, "secondary")
    assert {c["channel_name"] for c in view["channels"]} == {f"ZBAY_{n}" for n in V}
    assert {(c["effective_side"], c["authority"]) for c in view["channels"]} == {("secondary", AUTH_GROUP_OVERRIDE)}
    assert all(c["measurement_group_id"] == gv for c in view["channels"])
    assert {c["declared_side"] for c in view["channels"]} == {"primary"}              # the evidence is untouched
    assert "GROUP_OVERRIDE_OVERRIDES_DECLARATION" in _codes(view)
    assert {_chan(client, ws, src, n)["effective_side"] for n in I} == {"primary"}


# =========================================================================== Level 1 changes; groups follow


def test_level1_change_updates_every_following_group_and_keeps_the_original_evidence(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    body = _set_rec(client, ws, src, "secondary", note="Relay records secondary quantities")
    assert (body["effective_side"], body["authority"]) == ("secondary", AUTH_RECORDING_CORRECTION)
    assert body["engineer_correction"]["side"] == "secondary" and body["engineer_correction"]["note"].startswith("Relay")
    assert body["recording_derived"]["side"] == "primary"                  # the evidence is untouched
    assert "ENGINEER_CORRECTION_OVERRIDES_DECLARATION" in _codes(body)
    for gid in (gv, gi):
        view = _gv(client, ws, src, gid)
        assert (view["effective_side"], view["inherited_side"], view["recording_side"], view["override"]) == (
            "secondary", "secondary", "secondary", None)
        assert {(c["effective_side"], c["declared_side"], c["authority"]) for c in view["channels"]} == {
            ("secondary", "primary", AUTH_RECORDING_CORRECTION)}


def test_selecting_the_recorded_side_or_null_returns_the_recording_to_its_evidence(client):
    ws = _ws()
    src = _source(client, ws)
    _set_rec(client, ws, src, "secondary")
    assert _set_rec(client, ws, src, "primary")["engineer_correction"] is None      # equals the evidence -> nothing stored
    _set_rec(client, ws, src, "secondary")
    body = _set_rec(client, ws, src, None)
    assert (body["engineer_correction"], body["effective_side"], body["authority"]) == (None, "primary", AUTH_CHANNEL_DECLARED)


def test_level1_changes_while_one_group_is_manually_overridden(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    pinned = _put(client, ws, src, gv, "secondary")
    assert (pinned["effective_side"], pinned["authority"], pinned["override"]["side"]) == ("secondary", AUTH_GROUP_OVERRIDE, "secondary")
    assert pinned["inherited_side"] == "primary"
    _set_rec(client, ws, src, "secondary")                                  # Level 1 changes ...
    assert _gv(client, ws, src, gi)["effective_side"] == "secondary"       # ... the follower follows
    still = _gv(client, ws, src, gv)
    assert (still["effective_side"], still["authority"], still["override"]["side"]) == ("secondary", AUTH_GROUP_OVERRIDE, "secondary")
    _set_rec(client, ws, src, None)                                         # ... and back
    assert _gv(client, ws, src, gi)["effective_side"] == "primary"
    assert _gv(client, ws, src, gv)["effective_side"] == "secondary"        # the override was retained throughout


def test_manual_override_differing_from_a_secondary_recording_overrides_it_too(client):
    ws = _ws()
    src = _source(client, ws, v="secondary", i="secondary")
    gv, _gi = _groups(client, ws, src)
    view = _put(client, ws, src, gv, "primary")
    assert (view["effective_side"], view["override"]["side"], view["inherited_side"]) == ("primary", "primary", "secondary")


def test_selecting_the_inherited_value_clears_the_override_so_the_group_follows_again(client):
    ws = _ws()
    src = _source(client, ws)
    gv, _gi = _groups(client, ws, src)
    assert _put(client, ws, src, gv, "secondary")["override"] is not None
    cleared = _put(client, ws, src, gv, "primary")                          # primary == what the evidence gives the group
    assert (cleared["override"], cleared["effective_side"], cleared["authority"]) == (None, "primary", AUTH_CHANNEL_DECLARED)
    _set_rec(client, ws, src, "secondary")
    assert _gv(client, ws, src, gv)["effective_side"] == "secondary"        # proof it follows Level 1 again
    assert client.app.state.measurement_side_registry.get_group(ws, src, gv) is None


def test_no_inherited_value_is_duplicated_per_group(client):
    ws = _ws()
    src = _source(client, ws)
    _groups(client, ws, src)
    _set_rec(client, ws, src, "secondary")
    assert client.app.state.measurement_side_registry.count() == 1          # one Level 1 correction, nothing per group


def test_an_override_is_kept_when_dropping_it_would_expose_a_contradicted_declaration(client):
    """The recording says Primary, the engineer set the RECORDING to Secondary. A group the engineer pins to Primary
    restores the declared side: that is a real override (not redundant) while Level 1 stays Secondary."""
    ws = _ws()
    src = _source(client, ws)
    gv, _gi = _groups(client, ws, src)
    _set_rec(client, ws, src, "secondary")
    pinned = _put(client, ws, src, gv, "primary")
    assert (pinned["effective_side"], pinned["override"]["side"], pinned["inherited_side"]) == ("primary", "primary", "secondary")
    # Choosing what Level 1 gives (reliable: the engineer's own correction) is redundant and is cleared; the side is unchanged.
    followed = _put(client, ws, src, gv, "secondary")
    assert (followed["effective_side"], followed["override"], followed["authority"]) == ("secondary", None, AUTH_RECORDING_CORRECTION)


# =========================================================================== evidence quality


def test_missing_side_evidence_is_unresolved_until_an_engineer_decides(client):
    ws = _ws()
    src = _source(client, ws, v="none", i="none")
    gv, _gi = _groups(client, ws, src)
    rec = _rec(client, ws, src)
    assert (rec["recording_derived"]["status"], rec["effective_side"], rec["authority"]) == ("none", None, AUTH_UNRESOLVED)
    assert "RECORDING_SIDE_EVIDENCE_MISSING" in _codes(rec)
    view = _gv(client, ws, src, gv)
    assert (view["status"], view["effective_side"], view["inherited_side"]) == ("unresolved", None, None)
    assert "GROUP_SIDE_UNRESOLVED" in _codes(view)
    assert not _chan(client, ws, src, "VA")["usable"]
    # A group choice is the authority for ITS channels; the recording and the other group stay unresolved.
    chosen = _put(client, ws, src, gv, "secondary")
    assert (chosen["effective_side"], chosen["authority"], chosen["override"]["side"]) == ("secondary", AUTH_GROUP_OVERRIDE, "secondary")
    assert _gv(client, ws, src, "g-i")["status"] == "unresolved"
    assert _rec(client, ws, src)["effective_side"] is None
    # An engineer value at Level 1 is the only authority for everything else, and is recorded as such.
    body = _set_rec(client, ws, src, "secondary")
    assert (body["effective_side"], body["authority"]) == ("secondary", AUTH_RECORDING_CORRECTION)
    assert not any(d["code"] == "ENGINEER_CORRECTION_OVERRIDES_DECLARATION" for d in body["diagnostics"])   # nothing overridden
    assert _gv(client, ws, src, "g-i")["effective_side"] == "secondary"


def test_partial_evidence_uses_the_consistent_default_for_undeclared_channels_and_says_so(client):
    ws = _ws()
    src = _source(client, ws, v="secondary", i="none")                     # currents undeclared
    rec = _rec(client, ws, src)
    assert rec["recording_derived"]["undeclared_channels"] == 3 and "RECORDING_PARTIAL_SIDE_EVIDENCE" in _codes(rec)
    by_name = {c["channel_name"]: c for c in rec["channels"]}
    assert (by_name["ZBAY_VA"]["effective_side"], by_name["ZBAY_VA"]["authority"]) == ("secondary", AUTH_CHANNEL_DECLARED)
    assert (by_name["ZBAY_IA"]["effective_side"], by_name["ZBAY_IA"]["authority"]) == ("secondary", AUTH_RECORDING_DEFAULT)
    assert (by_name["ZBAY_VA"]["strict_usable"], by_name["ZBAY_VA"]["inferred"]) == (True, False)
    assert (by_name["ZBAY_IA"]["usable"], by_name["ZBAY_IA"]["strict_usable"], by_name["ZBAY_IA"]["inferred"]) == (True, False, True)
    assert "CHANNEL_SIDE_INFERRED" in {d["code"] for d in by_name["ZBAY_IA"]["diagnostics"]}


def test_inferred_default_blocks_strict_consumption_until_declared_or_engineer_confirmed(client):
    ws = _ws()
    src = _source(client, ws, v="secondary", i="none")
    gv, gi = _groups(client, ws, src)
    deps = _deps(client)
    refs = [ChannelRef("source", src, f"ZBAY_{n}") for n in ("VA", "IA")]
    vview, iview = _gv(client, ws, src, gv), _gv(client, ws, src, gi)
    assert (vview["strict_usable"], iview["status"], iview["effective_side"], iview["strict_usable"]) == (True, "resolved", "secondary", False)
    assert sorted(iview["inferred_channels"]) == ["ZBAY_IA", "ZBAY_IB", "ZBAY_IC"]
    consumed = resolve_consumed_side(ws, refs, deps=deps)
    assert (consumed.usable, consumed.strict_usable) == (True, False)           # displayable, not strict
    assert resolve_consumed_side(ws, refs[:1], deps=deps).strict_usable         # voltage alone is declared
    # A confirmed GROUP setting makes that group's side reliable; selecting the inferred side is kept as a confirmation.
    confirmed = _put(client, ws, src, gi, "secondary")
    assert (confirmed["strict_usable"], confirmed["authority"], confirmed["override"]["side"]) == (True, AUTH_GROUP_OVERRIDE, "secondary")
    assert resolve_consumed_side(ws, refs, deps=deps).strict_usable
    # ... and so does an engineer-confirmed Recording setting.
    ws2 = _ws()
    src2 = _source(client, ws2, v="secondary", i="none")
    _groups(client, ws2, src2)
    _set_rec(client, ws2, src2, "secondary")
    assert resolve_consumed_side(ws2, [ChannelRef("source", src2, f"ZBAY_{n}") for n in ("VA", "IA")], deps=_deps(client)).strict_usable


# =========================================================================== contradictory declarations


def test_mixed_declarations_within_one_group_are_reported_not_concealed(client):
    ws = _ws()
    src = _source(client, ws, ps={"VB": "S"})                              # VA, VC declare P; VB declares S
    gv, gi = _groups(client, ws, src)
    view = _gv(client, ws, src, gv)
    assert (view["status"], view["effective_side"]) == ("conflict", None)
    assert "GROUP_MIXED_SIDES" in _codes(view) and not view["strict_usable"]
    sides = {c["channel_name"]: c["effective_side"] for c in view["channels"]}
    assert sides == {"ZBAY_VA": "primary", "ZBAY_VB": "secondary", "ZBAY_VC": "primary"}        # each keeps its own
    assert _gv(client, ws, src, gi)["status"] == "resolved"                # the current group is untouched by the voltage mix
    assert _rec(client, ws, src)["recording_derived"]["status"] == "mixed"
    # The engineer resolves THIS group; the contradicting declaration stays visible.
    fixed = _put(client, ws, src, gv, "primary")
    assert (fixed["status"], fixed["effective_side"], fixed["strict_usable"]) == ("resolved", "primary", True)
    assert [(o["channel_name"], o["declared_side"], o["effective_side"]) for o in fixed["overridden_declarations"]] == [
        ("ZBAY_VB", "secondary", "primary")]
    assert "GROUP_OVERRIDE_OVERRIDES_DECLARATION" in _codes(fixed)
    # Once resolved, a consumer spanning the whole voltage group agrees; before it, the mix was a conflict (nothing guessed).
    whole = resolve_consumed_side(ws, [ChannelRef("source", src, f"ZBAY_{n}") for n in V], deps=_deps(client))
    assert (whole.status, whole.side, whole.strict_usable) == ("resolved", "primary", True)
    ws2 = _ws()
    mixed = _source(client, ws2, ps={"VB": "S"})
    blocked = resolve_consumed_side(ws2, [ChannelRef("source", mixed, f"ZBAY_{n}") for n in V], deps=_deps(client))
    assert (blocked.status, blocked.usable, blocked.side) == ("conflict", False, None)


def test_engineer_corrections_supersede_wrong_declarations_and_keep_the_original_evidence(client):
    ws = _ws()
    src = _source(client, ws, v="primary", i="primary")                    # recorder says Primary ...
    gv, gi = _groups(client, ws, src)
    body = _set_rec(client, ws, src, "secondary", note="Relay exports secondary quantities")   # ... engineer knows it is not
    assert body["engineer_correction"]["set_at"] and body["engineer_correction"]["note"]
    assert (body["effective_side"], body["authority"]) == ("secondary", AUTH_RECORDING_CORRECTION)
    warn = next(d for d in body["diagnostics"] if d["code"] == "ENGINEER_CORRECTION_OVERRIDES_DECLARATION")
    assert warn["severity"] == "warning"
    assert sorted(o["channel_name"] for o in body["overridden_declarations"]) == sorted(f"ZBAY_{n}" for n in _ALL)
    view = _gv(client, ws, src, gv)
    assert (view["status"], view["strict_usable"], view["effective_side"]) == ("resolved", True, "secondary")
    assert len(view["overridden_declarations"]) == 3
    consumed = resolve_consumed_side(ws, [ChannelRef("source", src, f"ZBAY_{n}") for n in _ALL], deps=_deps(client))
    assert (consumed.status, consumed.side, consumed.strict_usable) == ("resolved", "secondary", True)
    assert body["recording_derived"]["side"] == "primary" and {c["declared_side"] for c in body["channels"]} == {"primary"}
    # The correction's contradiction stays disclosed even when a group setting later takes over every channel of a group.
    _put(client, ws, src, gv, "primary")
    pinned = _rec(client, ws, src)
    assert {c["authority"] for c in pinned["channels"] if c["channel_name"].startswith("ZBAY_V")} == {AUTH_GROUP_OVERRIDE}
    assert len(pinned["overridden_declarations"]) == 6


# =========================================================================== Engineering Context plays no part


def test_engineering_context_status_and_membership_do_not_gate_a_group_setting(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    ctx = _bay(client, ws, [(src, _ALL)], status="needs_review", name="suggested bay")      # unconfirmed on purpose
    view = _put(client, ws, src, gv, "secondary")                          # accepted: no Confirm-bay step is needed
    assert (view["effective_side"], view["authority"]) == ("secondary", AUTH_GROUP_OVERRIDE)
    assert client.patch(f"{_contexts(ws)}/{ctx}", json={"status": "confirmed"}).status_code == 200
    assert _gv(client, ws, src, gv)["effective_side"] == "secondary"       # unchanged by the status change
    assert client.delete(f"{_contexts(ws)}/{ctx}").status_code == 204
    assert _gv(client, ws, src, gv)["override"]["side"] == "secondary"     # ... and by the bay's deletion


def test_setting_a_group_side_leaves_engineering_contexts_and_analysis_inputs_untouched(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    ctx = _bay(client, ws, [(src, _ALL)], status="confirmed")
    before = client.get(f"{_contexts(ws)}/{ctx}").json()
    _put(client, ws, src, gv, "secondary")
    _put(client, ws, src, gi, "secondary")
    assert client.get(f"{_contexts(ws)}/{ctx}").json() == before          # members, phases, status: identical


def test_the_old_bay_level_endpoints_are_gone(client):
    ws = _ws()
    src = _source(client, ws)
    ctx = _bay(client, ws, [(src, ("VA", "IA"))])
    assert client.get(f"{_contexts(ws)}/{ctx}/measurement-side").status_code == 404
    assert client.get(f"/api/v1/workspaces/{ws}/sources/{src}/engineering-contexts/{ctx}/measurement-side").status_code == 404
    assert client.put(f"/api/v1/workspaces/{ws}/sources/{src}/engineering-contexts/{ctx}/measurement-side",
                      json={"side": "primary"}).status_code in (404, 405)


# =========================================================================== several recordings


def test_one_bay_in_two_recordings_keeps_each_recordings_groups_separate(client):
    """The KPDN1 case: one Engineering Context holding channels of two recordings, Primary in A and Secondary in B."""
    ws = _ws()
    a, b = _source(client, ws, stem="a"), _source(client, ws, stem="b")
    av, ai = _groups(client, ws, a, "a")
    bv, bi = _groups(client, ws, b, "b")
    _bay(client, ws, [(a, _ALL), (b, _ALL)], name="KPDN1")
    assert _put(client, ws, a, av, "primary")["override"] is None
    assert _put(client, ws, b, bv, "secondary")["effective_side"] == "secondary"
    assert _gv(client, ws, a, av)["effective_side"] == "primary"
    assert _gv(client, ws, b, bi)["effective_side"] == "primary"           # B's current group follows B's own Level 1
    _set_rec(client, ws, b, "secondary")                                    # Level 1 of B reaches only B's followers
    assert _gv(client, ws, b, bi)["effective_side"] == "secondary"
    assert _gv(client, ws, a, ai)["effective_side"] == "primary"
    assert _rec(client, ws, a)["engineer_correction"] is None


def test_a_group_is_only_addressable_through_its_own_recording(client):
    ws = _ws()
    a, b = _source(client, ws, stem="a"), _source(client, ws, stem="b")
    av, _ai = _groups(client, ws, a, "a")
    wrong = client.get(_grp_url(ws, b, av))
    assert (wrong.status_code, wrong.json()["detail"]["code"]) == (404, "measurement_group_not_found")
    assert _set_g(client, ws, b, av, "secondary").status_code == 404
    assert client.app.state.measurement_side_registry.count() == 0


def test_bays_from_different_recordings_have_independent_sides(client):
    ws = _ws()
    s1 = _source(client, ws, v="primary", i="primary", stem="one")
    s2 = _source(client, ws, v="secondary", i="secondary", stem="two")
    v1, _ = _groups(client, ws, s1, "a")
    v2, _ = _groups(client, ws, s2, "b")
    assert _gv(client, ws, s1, v1)["effective_side"] == "primary"
    assert _gv(client, ws, s2, v2)["effective_side"] == "secondary"
    _set_rec(client, ws, s1, "secondary")
    assert _gv(client, ws, s1, v1)["effective_side"] == "secondary"
    assert _rec(client, ws, s2)["engineer_correction"] is None


def test_workspaces_are_isolated(client):
    ws1, ws2 = _ws(), _ws()
    s1, s2 = _source(client, ws1), _source(client, ws2)
    v1, _ = _groups(client, ws1, s1)
    v2, _ = _groups(client, ws2, s2)
    _set_rec(client, ws1, s1, "secondary")
    _put(client, ws1, s1, v1, "primary")                                   # Level 1 is now secondary, so this is an override
    assert _rec(client, ws2, s2)["engineer_correction"] is None
    assert _gv(client, ws2, s2, v2)["effective_side"] == "primary" and _gv(client, ws2, s2, v2)["override"] is None
    assert client.get(_rec_url(ws2, s1)).status_code == 404
    assert client.get(_grp_url(ws2, s1, v1)).status_code == 404
    assert client.put(_rec_url(ws2, s1), json={"side": "primary"}).status_code == 404
    cross = client.get(_url(ws2, "/channel"), params={"source_id": s1, "channel_name": "ZBAY_VA"}).json()
    assert (cross["effective_side"], cross["usable"]) == ("unknown", False)
    overview = client.get(_url(ws2)).json()
    assert [r["source_id"] for r in overview["recordings"]] == [s2] and sorted(g["measurement_group_id"] for g in overview["groups"]) == sorted([v2, "g-i"])


# =========================================================================== lifecycle


def test_removing_a_source_removes_its_correction_and_group_overrides_and_a_reupload_starts_clean(client):
    ws = _ws()
    src = _source(client, ws, stem="first")
    gv, _gi = _groups(client, ws, src)
    _set_rec(client, ws, src, "secondary")
    _put(client, ws, src, gv, "primary")
    assert client.app.state.measurement_side_registry.count() == 2
    assert client.delete(f"/api/v1/workspaces/{ws}/sources/{src}").status_code == 204
    assert client.app.state.measurement_side_registry.count() == 0
    assert client.get(_rec_url(ws, src)).status_code == 404
    again = _source(client, ws, stem="first")
    assert again != src
    body = _rec(client, ws, again)
    assert (body["engineer_correction"], body["effective_side"], body["authority"]) == (None, "primary", AUTH_CHANNEL_DECLARED)


def test_group_deletion_releases_its_override_only(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    _put(client, ws, src, gv, "secondary")
    _put(client, ws, src, gi, "secondary")
    registry = client.app.state.measurement_side_registry
    assert client.delete(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups/{gv}").status_code == 204
    assert registry.get_group(ws, src, gv) is None and registry.get_group(ws, src, gi) is not None
    assert client.get(_grp_url(ws, src, gv)).status_code == 404
    assert _chan(client, ws, src, "VA")["effective_side"] == "primary"      # the channel follows its recording again


def test_group_reassignment_keeps_the_override_with_the_group_and_not_with_the_channel(client):
    ws = _ws()
    src = _source(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB"), "vg-a")
    _group(client, ws, src, KIND_VOLTAGE, ("VC",), "vg-b")
    _put(client, ws, src, "vg-a", "secondary")
    assert _chan(client, ws, src, "VB")["effective_side"] == "secondary"
    registry = client.app.state.measurement_group_registry
    a, b = registry.get(ws, "vg-a"), registry.get(ws, "vg-b")
    a.channel_refs = [ChannelRef("source", src, "ZBAY_VA")]                 # VB leaves A ...
    b.channel_refs = [ChannelRef("source", src, "ZBAY_VC"), ChannelRef("source", src, "ZBAY_VB")]   # ... and joins B
    registry.update(a)
    registry.update(b)
    assert _chan(client, ws, src, "VB")["effective_side"] == "primary"      # B has no override: the channel left A's
    assert _chan(client, ws, src, "VA")["effective_side"] == "secondary"    # A keeps its own
    assert _gv(client, ws, src, "vg-a")["override"]["side"] == "secondary"


def test_workspace_reset_clears_everything(client):
    ws, other = _ws(), _ws()
    src, keep = _source(client, ws), _source(client, other)
    gv, _ = _groups(client, ws, src)
    _set_rec(client, ws, src, "secondary")
    _put(client, ws, src, gv, "primary")
    _set_rec(client, other, keep, "secondary")
    assert client.delete(f"/api/v1/workspaces/{ws}").status_code == 204
    registry = client.app.state.measurement_side_registry
    assert registry.get_recording(ws, src) is None and registry.group_keys(ws) == []
    assert registry.count() == 1 and registry.get_recording(other, keep) is not None      # the other workspace is untouched


def test_configuration_is_in_memory_only(client, settings):
    ws = _ws()
    src = _source(client, ws)
    gv, _ = _groups(client, ws, src)
    _set_rec(client, ws, src, "secondary")
    _put(client, ws, src, gv, "primary")
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
    gv, _gi = _groups(client, ws, src)
    deps = _deps(client)
    ref = ChannelRef("source", src, "ZBAY_VA")
    assert resolve_effective_side_for_ref(ws, ref, deps=deps).side == "primary"
    _set_rec(client, ws, src, "secondary")
    assert resolve_effective_side_for_ref(ws, ref, deps=deps).side == "secondary"
    _put(client, ws, src, gv, "primary")
    now = resolve_effective_side_for_ref(ws, ref, deps=deps)
    assert (now.side, now.authority, now.group_id) == ("primary", AUTH_GROUP_OVERRIDE, gv)
    api = _chan(client, ws, src, "VA")                                      # an API read and a direct call never disagree
    assert (api["effective_side"], api["authority"], api["measurement_group_id"]) == (now.side, now.authority, gv)


def test_a_channel_in_no_group_follows_its_recording(client):
    ws = _ws()
    src = _source(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("VA",), "vg-a")
    _put(client, ws, src, "vg-a", "secondary")
    free = _chan(client, ws, src, "VB")
    assert (free["effective_side"], free["authority"], free["measurement_group_id"]) == ("primary", AUTH_CHANNEL_DECLARED, None)
    _set_rec(client, ws, src, "secondary")
    assert _chan(client, ws, src, "VB")["authority"] == AUTH_RECORDING_CORRECTION


def test_consumed_side_requires_every_channel_to_agree_and_resolve(client):
    ws = _ws()
    src = _source(client, ws, v="primary", i="secondary")
    deps = _deps(client)
    refs = lambda *n: [ChannelRef("source", src, f"ZBAY_{x}") for x in n]  # noqa: E731
    assert resolve_consumed_side(ws, refs("VA", "VB", "VC"), deps=deps).side == "primary"
    cross = resolve_consumed_side(ws, refs("VA", "IA"), deps=deps)             # independent V/I sides are usable
    assert (cross.status, cross.side, cross.voltage_side, cross.current_side, cross.usable, cross.strict_usable) == (
        "resolved", None, "primary", "secondary", True, True)
    assert "CONSUMED_VOLTAGE_CURRENT_SIDES_DIFFER" in {d.code for d in cross.diagnostics}
    assert cross.reference_sides == "voltage_current_differ"
    unknown = resolve_consumed_side(ws, refs("VA") + [ChannelRef("source", src, "NOPE")], deps=deps)
    assert (unknown.status, unknown.usable) == ("unresolved", False)


def test_missing_evidence_is_never_inferred_from_ratios_or_magnitude(client):
    """A recording with no P/S declaration needs an engineer's value, whatever CT/VT or magnitude says."""
    ws = _ws()
    cfg, dat = _comtrade(v_rms=66.0, i_rms=2.0, ps=_flags("none", "none"))        # secondary-looking magnitudes
    src = _upload(client, ws, cfg, dat)
    _clear(client, ws)
    gv, gi = _groups(client, ws, src)
    _vt(client, ws, gv, VT_P, VT_S, note="VT")                                     # a configured VT/CT is not side evidence
    _ct(client, ws, gi, CT_P, CT_S, note="CT")
    rec, view = _rec(client, ws, src), _gv(client, ws, src, gv)
    assert (rec["effective_side"], rec["authority"], rec["recording_derived"]["status"]) == (None, AUTH_UNRESOLVED, "none")
    assert (view["status"], view["effective_side"], view["strict_usable"]) == ("unresolved", None, False)
    assert not resolve_consumed_side(ws, [ChannelRef("source", src, "ZBAY_VA")], deps=_deps(client)).strict_usable
    _set_rec(client, ws, src, "secondary")                                         # the engineer's value is the authority
    assert _gv(client, ws, src, gv)["strict_usable"] is True


# =========================================================================== API contract


def test_api_validation_and_not_found_shapes(client):
    ws = _ws()
    src = _source(client, ws)
    gv, _gi = _groups(client, ws, src)
    assert client.put(_rec_url(ws, src), json={"side": "unknown"}).status_code == 422
    assert client.put(_rec_url(ws, src), json={"side": "PRIMARY"}).status_code == 422
    assert client.put(_rec_url(ws, src), json={}).status_code == 422
    assert client.put(_rec_url(ws, src), json={"side": "primary", "note": "x" * 501}).status_code == 422
    assert _set_g(client, ws, src, gv, None).status_code == 422                # no reset: null is not a group value
    assert _set_g(client, ws, src, gv, "unknown").status_code == 422
    assert _set_g(client, ws, src, gv, "PRIMARY").status_code == 422
    miss = client.put(_rec_url(ws, "nope"), json={"side": "primary"})
    assert (miss.status_code, miss.json()["detail"]["code"]) == (404, "source_not_found")
    miss = _set_g(client, ws, src, "mg-nope", "primary")
    assert (miss.status_code, miss.json()["detail"]["code"]) == (404, "measurement_group_not_found")
    miss = _set_g(client, ws, "nope", gv, "primary")
    assert miss.status_code == 404
    assert client.get(f"/api/v1/workspaces/{ws}/measurement-side").json()["workspace_id"] == ws
    assert client.get(_url("  ")).status_code in (400, 404)


def test_a_group_with_no_recorded_voltage_or_current_channel_cannot_take_a_side(client):
    ws = _ws()
    src = _source(client, ws)
    _group(client, ws, src, KIND_VOLTAGE, ("NOT_A_CHANNEL",), "vg-empty")
    resp = _set_g(client, ws, src, "vg-empty", "secondary")
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "group_has_no_measurement_channels")
    view = _gv(client, ws, src, "vg-empty")
    assert (view["status"], view["effective_side"]) == ("not_applicable", None) and "GROUP_HAS_NO_VOLTAGE_CURRENT_MEMBERS" in _codes(view)
    assert client.app.state.measurement_side_registry.count() == 0


def test_overview_lists_recordings_and_groups_without_channel_detail(client):
    ws = _ws()
    src = _source(client, ws)
    gv, gi = _groups(client, ws, src)
    body = client.get(_url(ws)).json()
    assert body["recordings"][0]["channels"] is None and all(g["channels"] is None for g in body["groups"])
    assert sorted(g["measurement_group_id"] for g in body["groups"]) == sorted([gv, gi])
    assert {g["kind"] for g in body["groups"]} == {"voltage", "current"}
    assert sorted(body["recordings"][0]["group_ids"]) == sorted([gv, gi])
    assert "bays" not in body


# =========================================================================== existing results unchanged


def _snapshot(client, ws, src, ctx):
    """Every existing PU / protection response this slice must not move. Recorded Overcurrent is deliberately NOT in this
    list since D5A-2B2C-1A, and recorded Impedance / Distance are not since D5A-2B2C-1B: they consume the unified side by design
    (see test_d5a_2b2c_1a_overcurrent_unified_side.py and test_d5a_2b2c_1b_*). PU and the protection-context report are not
    migrated and must stay exactly as they were."""
    calls = [
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
    gv, gi = _groups(client, ws, src)
    ctx = _bay(client, ws, [(src, _ALL)], status="confirmed")
    _vt(client, ws, gv, VT_P, VT_S, note="VT")
    _ct(client, ws, gi, CT_P, CT_S, note="CT")
    before = _snapshot(client, ws, src, ctx)
    assert before["context_oc"][0] == 200 and before["pu_coverage"][0] == 200   # the oracle itself is meaningful
    _set_rec(client, ws, src, "secondary", note="correction")
    assert _snapshot(client, ws, src, ctx) == before
    _put(client, ws, src, gv, "primary")
    _put(client, ws, src, gi, "secondary")                                      # mixed references, independent
    assert _snapshot(client, ws, src, ctx) == before
    _set_rec(client, ws, src, None)
    _put(client, ws, src, gv, "secondary")
    assert _snapshot(client, ws, src, ctx) == before
