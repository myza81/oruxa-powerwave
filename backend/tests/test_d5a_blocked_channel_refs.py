"""A recorded Impedance / Distance result that is BLOCKED by a missing or invalid CT/VT ratio, an unsupported unit, or a
strict measurement-side check must still identify the channels that resolved, with their units, so the physical signals
(Related Waveforms) stay plottable. Nothing numerical changes: the status, reason code, message and the absent
impedance values of a blocked result are exactly as before, and an unresolved channel is never given an identity.

The consumer contract is tested by running the REAL frontend functions (read from frontend/index.html, never edited)
against actual API responses with Node.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_d5a2a_protection_instrument_context_api import _clear, _contexts, _ct, _group, _vt
from tests.test_d5a2b1_independent_side_conversion import (  # noqa: F401  (client is the shared fixture)
    CT_P, CT_S, VT_P, VT_S, Z_PRI, Z_SEC,
    _bay, _comtrade, _context, _dist, _dist_locus, _imp, _imp_locus, _strict, _upload, client,
)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
RATIO_MESSAGE = "Valid VT and CT ratios are required to convert between Recording and Impedance basis."
NUMERIC_IMPEDANCE = ("magnitude_ohm", "resistance_ohm", "reactance_ohm", "angle_deg")


def _ref(src: str, name: str) -> dict:
    return {"kind": "source", "source_id": src, "channel_name": name, "calculated_channel_id": None}


def _no_numbers(body: dict) -> None:
    assert body["status"] == "needs_configuration"
    assert all(body[k] is None for k in NUMERIC_IMPEDANCE), body


def _imp_channels(body: dict, src: str, phase: str = "A", units=("V", "A")) -> None:
    assert body["voltage_channel_ref"] == _ref(src, f"ZBAY_V{phase}")
    assert body["current_channel_ref"] == _ref(src, f"ZBAY_I{phase}")
    assert (body["voltage_unit"], body["current_unit"]) == units


def _dist_channels(body: dict, src: str, legs=("VA", "VB", "IA", "IB"), units=("V", "A")) -> None:
    v1, v2, i1, i2 = legs
    assert body["v1_channel_ref"] == _ref(src, f"ZBAY_{v1}") and body["v2_channel_ref"] == _ref(src, f"ZBAY_{v2}")
    assert body["i1_channel_ref"] == _ref(src, f"ZBAY_{i1}") and body["i2_channel_ref"] == _ref(src, f"ZBAY_{i2}")
    assert (body["voltage_unit"], body["current_unit"]) == units


def _legacy(**ratios):
    return dict(recording_basis="primary", impedance_basis="secondary", **ratios)


# =========================================================================== legacy: missing / invalid ratios


def test_legacy_missing_ratios_keep_the_message_and_identify_the_channels(client):
    ws = "refs-legacy-missing"
    src, ctx = _bay(client, ws, groups=False)
    imp = _imp(client, ws, ctx, **_legacy()).json()
    assert (imp["status"], imp["reason_code"], imp["message"]) == ("needs_configuration", "invalid_ratio", RATIO_MESSAGE)
    _no_numbers(imp)
    _imp_channels(imp, src)
    dist = _dist(client, ws, ctx, **_legacy()).json()
    assert (dist["status"], dist["reason_code"], dist["message"]) == ("needs_configuration", "invalid_ratio", RATIO_MESSAGE)
    _no_numbers(dist)
    _dist_channels(dist, src)


@pytest.mark.parametrize("ratios", [
    dict(ct_primary=CT_P, ct_secondary=CT_S),                                  # missing VT
    dict(vt_primary=VT_P, vt_secondary=VT_S),                                  # missing CT
    dict(vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P),                 # incomplete CT
    dict(vt_primary=0.0, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S),     # invalid VT
    dict(vt_primary=VT_P, vt_secondary=VT_S, ct_primary=-1000.0, ct_secondary=CT_S),  # invalid CT
], ids=["missing-vt", "missing-ct", "incomplete-ct", "invalid-vt", "invalid-ct"])
def test_legacy_missing_or_invalid_ratio_cases_identify_the_channels(client, ratios):
    ws = f"refs-legacy-{abs(hash(tuple(sorted(ratios.items())))) % 100000}"
    src, ctx = _bay(client, ws, groups=False)
    imp = _imp(client, ws, ctx, **_legacy(**ratios)).json()
    assert (imp["reason_code"], imp["message"]) == ("invalid_ratio", RATIO_MESSAGE)
    _no_numbers(imp)
    _imp_channels(imp, src)
    dist = _dist(client, ws, ctx, **_legacy(**ratios)).json()
    assert dist["reason_code"] == "invalid_ratio"
    _no_numbers(dist)
    _dist_channels(dist, src)


def test_legacy_other_loops_and_phases_name_their_own_channels(client):
    ws = "refs-legacy-loops"
    src, ctx = _bay(client, ws, groups=False)
    assert _imp(client, ws, ctx, phase="B", **_legacy()).json()["voltage_channel_ref"] == _ref(src, "ZBAY_VB")
    bc = _dist(client, ws, ctx, loop="BC", **_legacy()).json()
    _dist_channels(bc, src, legs=("VB", "VC", "IB", "IC"))
    ca = _dist(client, ws, ctx, loop="CA", **_legacy()).json()
    _dist_channels(ca, src, legs=("VC", "VA", "IC", "IA"))


# =========================================================================== strict: authority and side blocks


def test_strict_missing_vt_and_missing_ct_identify_the_channels(client):
    ws = "refs-strict-missing"
    src, ctx = _bay(client, ws, groups=False)
    vt = _imp(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    assert vt["reason_code"] == "vt_authority_unavailable"
    _no_numbers(vt)
    _imp_channels(vt, src)
    dvt = _dist(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    assert dvt["reason_code"] == "vt_authority_unavailable"
    _dist_channels(dvt, src)

    ws2 = "refs-strict-missing-ct"
    src2, ctx2 = _bay(client, ws2, v_side="secondary", i_side="secondary")
    client.app.state.current_group_config_registry.delete(ws2, f"ig-{src2}")            # VT stays, CT removed
    ct = _imp(client, ws2, ctx2, **_strict("secondary", "secondary", "primary")).json()
    assert ct["reason_code"] == "ct_authority_unavailable"
    _no_numbers(ct)
    _imp_channels(ct, src2)
    assert _dist(client, ws2, ctx2, **_strict("secondary", "secondary", "primary")).json()["reason_code"] == "ct_authority_unavailable"


@pytest.mark.parametrize("ct", [(1000.0, 0.0), (-1000.0, 5.0), (1000.0, None)])
def test_strict_invalid_authoritative_ratio_identifies_the_channels(client, ct):
    ws = f"refs-strict-invalid-{abs(hash(ct)) % 10000}"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary", ct=ct)
    body = _imp(client, ws, ctx, **_strict("secondary", "primary", "secondary")).json()
    assert body["reason_code"] == "ct_authority_unavailable"
    assert body["side_conversion"]["block_detail"]["ratio_status"] == "invalid"
    _no_numbers(body)
    _imp_channels(body, src)


@pytest.mark.parametrize("ps,asserted,code", [
    ({}, ("secondary", "primary"), "voltage_side_contradicts_recording"),            # recording says P, caller asserts S
    ({"IA": ""}, ("primary", "primary"), "current_side_authority_unavailable"),       # undeclared
])
def test_strict_side_blocks_identify_the_channels(client, ps, asserted, code):
    ws = f"refs-side-{code}"
    src, ctx = _bay(client, ws, ps=ps)
    body = _imp(client, ws, ctx, **_strict(*asserted, "primary")).json()
    assert body["reason_code"] == code
    _no_numbers(body)
    _imp_channels(body, src)
    dist = _dist(client, ws, ctx, **_strict(*asserted, "primary")).json()
    assert dist["reason_code"] == code
    _dist_channels(dist, src)


def test_strict_mixed_sides_within_a_loop_identify_the_channels(client):
    ws = "refs-mixed"
    src, ctx = _bay(client, ws, ps={"VA": "P", "VB": "S"})
    body = _dist(client, ws, ctx, **_strict("primary", "primary", "primary")).json()
    assert body["reason_code"] == "voltage_mixed_side_within_quantity"
    _no_numbers(body)
    _dist_channels(body, src)


@pytest.mark.parametrize("params,code", [
    (dict(voltage_side="primary", impedance_basis="primary", recording_basis="primary"), "current_side_required"),
    (dict(voltage_side="both", current_side="primary", impedance_basis="primary"), "invalid_voltage_side"),
    (dict(voltage_side="primary", current_side="primary", impedance_basis="both"), "invalid_impedance_basis"),
], ids=["side-required", "invalid-side", "invalid-output"])
def test_strict_early_validation_blocks_still_identify_resolved_channels(client, params, code):
    """These blocks happen before any conversion check, yet the context's channels are known and must be reported."""
    ws = f"refs-early-{code}"
    src, ctx = _bay(client, ws)
    imp = _imp(client, ws, ctx, **params).json()
    assert imp["reason_code"] == code
    _no_numbers(imp)
    _imp_channels(imp, src)
    dist = _dist(client, ws, ctx, **params).json()
    assert dist["reason_code"] == code
    _dist_channels(dist, src)


# =========================================================================== never invented / identity integrity


def test_an_unresolved_channel_is_never_given_an_identity(client):
    ws = "refs-unresolved"
    src, ctx = _bay(client, ws, members=("VA", "VB", "VC"))        # the context has voltage members only
    body = _imp(client, ws, ctx, voltage_side="both", current_side="primary", impedance_basis="primary").json()
    assert body["reason_code"] == "invalid_voltage_side"
    assert body["voltage_channel_ref"] == _ref(src, "ZBAY_VA") and body["voltage_unit"] == "V"
    assert body["current_channel_ref"] is None and body["current_unit"] is None


def test_an_unknown_context_gets_no_identities_and_keeps_its_previous_response(client):
    body = _imp(client, "refs-no-context", "nope", voltage_side="both", current_side="primary", impedance_basis="primary").json()
    assert body["reason_code"] == "invalid_voltage_side" and body["status"] == "needs_configuration"
    assert body["voltage_channel_ref"] is None and body["current_channel_ref"] is None
    assert _imp(client, "refs-no-context", "nope", **_strict("primary", "primary", "primary")).status_code == 404


def test_each_context_reports_its_own_workspace_source_and_channels(client):
    ws = "refs-identity"
    src1, ctx1 = _bay(client, ws, groups=False)
    cfg, dat = _comtrade(v_rms=66000.0, i_rms=400.0, ps={n: "P" for n in ("VA", "VB", "VC", "IA", "IB", "IC")})
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
    assert src1 != src2
    one = _imp(client, ws, ctx1, **_legacy()).json()
    two = _imp(client, ws, ctx2, **_legacy()).json()
    _imp_channels(one, src1)
    _imp_channels(two, src2)
    assert one["engineering_context_id"] == ctx1 and two["engineering_context_id"] == ctx2
    assert one["voltage_channel_ref"]["source_id"] != two["voltage_channel_ref"]["source_id"]


# =========================================================================== configured cases are unchanged


def test_fully_configured_results_are_unchanged_and_still_identify_the_channels(client):
    ws = "refs-configured"
    src, ctx = _bay(client, ws)
    for out, expected in (("primary", Z_PRI), ("secondary", Z_SEC)):
        strict = _imp(client, ws, ctx, **_strict("primary", "primary", out)).json()
        assert strict["status"] == "computed" and strict["magnitude_ohm"] == pytest.approx(expected, rel=1e-3)
        _imp_channels(strict, src)
        legacy = _imp(client, ws, ctx, recording_basis="primary", impedance_basis=out,
                      vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S).json()
        assert legacy["status"] == "computed" and legacy["magnitude_ohm"] == pytest.approx(expected, rel=1e-3)
        _imp_channels(legacy, src)
        dist = _dist(client, ws, ctx, **_strict("primary", "primary", out)).json()
        assert dist["status"] == "computed" and dist["magnitude_ohm"] == pytest.approx(expected, rel=1e-3)
        _dist_channels(dist, src)


# =========================================================================== locus: response contract unchanged


def test_locus_responses_keep_their_contract_when_blocked(client):
    """Locus responses never carried channel references (computed or blocked); that contract is unchanged."""
    ws = "refs-locus"
    src, ctx = _bay(client, ws, groups=False)
    legacy = _imp_locus(client, ws, ctx, **_legacy()).json()
    assert set(legacy) == {"engineering_context_id", "phase", "points", "side_conversion"}
    assert [(p["status"], p["reason_code"]) for p in legacy["points"]] == [("needs_configuration", "invalid_ratio")] * 3
    assert all(p["magnitude_ohm"] is None for p in legacy["points"]) and legacy["side_conversion"] is None
    strict = _imp_locus(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    assert {p["reason_code"] for p in strict["points"]} == {"vt_authority_unavailable"}
    assert strict["side_conversion"]["block_code"] == "vt_authority_unavailable"
    dl = _dist_locus(client, ws, ctx, **_legacy()).json()
    assert set(dl) == {"engineering_context_id", "loop", "points", "side_conversion"}
    assert {p["reason_code"] for p in dl["points"]} == {"invalid_ratio"}
    ds = _dist_locus(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()
    assert {p["reason_code"] for p in ds["points"]} == {"vt_authority_unavailable"}


# =========================================================================== consumer contract: the real frontend code


def _function_text(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[start:j + 1]
    raise AssertionError(name)


def _frontend_roles(kind: str, result: dict, *, phase: str = "A", loop: str = "AB") -> list[dict]:
    """Run the frontend's own related-waveform role builder on an API response, with Node (no frontend change)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    source = FRONTEND.read_text(encoding="utf-8")
    name = "wwImpedanceComputeActiveRelatedWaveformRoles" if kind == "impedance" else "wwDistanceComputeActiveRelatedWaveformRoles"
    loop_roles = re.search(r"const WW_DISTANCE_LOOP_ROLES = \{.*?\};", source, re.S).group(0)
    script = f"""
const WW_ANALYSIS_INPUT_SOURCE_RECORDING = "recording";
function wwPhasorRoleColor(key) {{ return "color-" + key; }}
{loop_roles}
const wwImpedanceState = {{ inputSource: "recording", latestResult: null, phase: "A" }};
const wwDistanceState = {{ inputSource: "recording", latestResult: null, loop: "AB" }};
{_function_text(source, name)}
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
wwImpedanceState.latestResult = input.result; wwImpedanceState.phase = input.phase;
wwDistanceState.latestResult = input.result; wwDistanceState.loop = input.loop;
process.stdout.write(JSON.stringify({name}()));
"""
    done = subprocess.run([node, "-e", script], input=json.dumps({"result": result, "phase": phase, "loop": loop}),
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_frontend_has_no_signals_without_refs_so_the_test_is_not_vacuous():
    assert _frontend_roles("impedance", {"voltage_channel_ref": None, "current_channel_ref": None}) == []
    assert _frontend_roles("distance", {"v1_channel_ref": None, "v2_channel_ref": None,
                                        "i1_channel_ref": None, "i2_channel_ref": None}) == []


def test_related_waveforms_show_the_physical_signals_of_blocked_impedance_results(client):
    ws = "refs-frontend-imp"
    src, ctx = _bay(client, ws, groups=False)
    for body in (_imp(client, ws, ctx, **_legacy()).json(),                                   # legacy ratio block
                 _imp(client, ws, ctx, **_strict("primary", "primary", "secondary")).json(),   # strict authority block
                 _imp(client, ws, ctx, voltage_side="both", current_side="primary", impedance_basis="primary").json()):
        assert body["status"] == "needs_configuration"
        roles = _frontend_roles("impedance", body)
        assert [r["roleKey"] for r in roles] == ["Va", "Ia"]
        assert [r["engineeringType"] for r in roles] == ["Voltage", "Current"]
        assert [r["channelRef"] for r in roles] == [_ref(src, "ZBAY_VA"), _ref(src, "ZBAY_IA")]
        assert [r["unit"] for r in roles] == ["V", "A"]


def test_related_waveforms_show_the_physical_signals_of_blocked_distance_results(client):
    ws = "refs-frontend-dist"
    src, ctx = _bay(client, ws, groups=False)
    for body in (_dist(client, ws, ctx, **_legacy()).json(),
                 _dist(client, ws, ctx, **_strict("primary", "primary", "secondary")).json()):
        assert body["status"] == "needs_configuration"
        roles = _frontend_roles("distance", body)
        assert [r["roleKey"] for r in roles] == ["Va", "Vb", "Ia", "Ib"]
        assert [r["channelRef"]["channel_name"] for r in roles] == ["ZBAY_VA", "ZBAY_VB", "ZBAY_IA", "ZBAY_IB"]
        assert all(r["channelRef"]["source_id"] == src for r in roles)
        assert [r["unit"] for r in roles] == ["V", "V", "A", "A"]


def test_related_waveforms_never_show_an_unresolved_channel(client):
    ws = "refs-frontend-partial"
    src, ctx = _bay(client, ws, members=("VA", "VB", "VC"))
    body = _imp(client, ws, ctx, voltage_side="both", current_side="primary", impedance_basis="primary").json()
    roles = _frontend_roles("impedance", body)
    assert [r["roleKey"] for r in roles] == ["Va"] and roles[0]["channelRef"] == _ref(src, "ZBAY_VA")
