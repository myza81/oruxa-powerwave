"""D5A frontend: recorded Impedance Locus / Distance Protection take CT/VT only from the Recording Details
Measurement Group (read through the D5A-2A `protection-instrument-context` API), read-only.

The consumer logic is tested by running the REAL helper block of frontend/index.html with Node (no re-implementation),
including against real API responses.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from tests.test_d5a2a_protection_instrument_context_api import _contexts, _ct, _group, _vt
from tests.test_d5a2b1_independent_side_conversion import (  # noqa: F401  (client is the shared fixture)
    CT_P, CT_S, VT_P, VT_S, Z_PRI, Z_SEC, _bay, _dist, _imp, client,
)

SOURCE = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
BLOCK_START = "// ---- D5A: authoritative CT/VT for the RECORDED Impedance Locus and"
BLOCK_END = "function wwImpedanceFetchAnalysis("
PANELS = (("impedance", "Impedance"), ("distance", "Distance"))


def _block() -> str:
    start = SOURCE.index(BLOCK_START)
    return SOURCE[start:SOURCE.index(BLOCK_END, start)]


def _code_only(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


# --------------------------------------------------------------------------- static guarantees


@pytest.mark.parametrize("kind,name", PANELS)
def test_recorded_mode_has_no_competing_vt_ct_editor(kind, name):
    for field in ("VtPrimary", "VtSecondary", "CtPrimary", "CtSecondary"):
        assert f'id="ww{name}{field}Input"' not in SOURCE and f'id="ww{name}{field}Field"' not in SOURCE
    assert f'id="ww{name}CtVtAuthority"' in SOURCE
    host = re.search(rf'<div class="ww-ctvt-authority[^>]*id="ww{name}CtVtAuthority"[^>]*>', SOURCE).group(0)
    assert "hidden" in host and "<input" not in host


@pytest.mark.parametrize("kind,name", PANELS)
def test_manual_mode_inputs_are_untouched(kind, name):
    for field in ("VtPrimary", "VtSecondary", "CtPrimary", "CtSecondary"):
        assert f'id="ww{name}Manual{field}Input"' in SOURCE


def test_the_panels_keep_no_local_ratio_state_and_send_only_the_authoritative_plan():
    assert "s.vtPrimary" not in SOURCE and '"vtPrimary"' not in SOURCE
    for name in ("Impedance", "Distance"):
        body = re.search(rf"function ww{name}BasisParams\(s\) \{{(.*?)\n        \}}", SOURCE, re.S).group(1)
        assert "wwCtVtBasisParams" in body and "vt_primary" not in body and "ct_primary" not in body


def test_the_frontend_never_derives_a_vt_itself():
    """The auto-derived VT is the BACKEND's (owner decision 2026-11-21); the page only displays and sends what the
    API reports as consumable, and never calls a valid derived VT assumed, provisional, unverified or display-only."""
    code = _code_only(_block())
    for forbidden in ("vt_effective", "nominal_voltage", "* 1000", "110"):
        assert forbidden not in code.replace("110 V secondary", "")
    assert "vt_primary: String(voltage.primary)" in code
    for word in ("display-only", "assumed", "provisional"):
        assert word not in code.lower()
    assert "Auto-derived" in code
    # the nominal appears only inside the not-usable explanation, never in a request value
    blocker = re.search(r"function wwCtVtRatioBlocker.*?\n        }\n", code, re.S).group(0)
    assert "nominal_ll_kv" in blocker and "nominal_ll_kv" not in code.replace(blocker, "")


def test_correction_goes_through_recording_details_only():
    code = _code_only(_block())
    assert "wwNavigateToRdForGroup(target.sourceId, target.groupId)" in code
    assert "Configure in Recording Details" in code
    assert ".value =" not in code.replace("el.value = s.recordingBasis", "")


# --------------------------------------------------------------------------- Node harness over the real block


def _node(script: str, payload: dict):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    prelude = """
const WW_ANALYSIS_INPUT_SOURCE_RECORDING = "recording", WW_ANALYSIS_INPUT_SOURCE_MANUAL = "manual";
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const ww = { measurementGroups: new Map(Object.entries(input.groups || {})) };
function wwRoleLabelText(key) { return key; }
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
function currentWorkspaceId() { return "w"; }
function apiBaseUrl() { return ""; }
const navigations = [];
function wwNavigateToRdForGroup(sourceId, groupId) { navigations.push([sourceId, groupId]); }
const hosts = {};
const document = { getElementById: (id) => (hosts[id] = hosts[id] || { hidden: true, innerHTML: "", value: "" }) };
const mk = (extra) => Object.assign({ selectedContextId: "c", inputSource: "recording", settings: JSON.parse(JSON.stringify(input.settings || {})),
    ctVt: { key: "k", status: input.status || "ready", report: input.report || null, error: input.error || "", generation: 0, requestedSignature: null } }, extra);
const wwImpedanceState = mk({ phase: "A" });
const wwDistanceState = mk({ loop: "AB" });
function wwImpedanceHandleSettingsChanged() { reruns.push("impedance"); }
function wwDistanceHandleSettingsChanged() { reruns.push("distance"); }
const reruns = [];
"""
    done = subprocess.run([node, "-e", prelude + _block() + script], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _plan(report, recording, output, *, explicit=False, status="ready", error="", groups=None, kind="impedance"):
    return _node(
        f"""
const kind = "{kind}";
const state = kind === "distance" ? wwDistanceState : wwImpedanceState;
const plan = wwCtVtPlanFor(kind);
const params = wwCtVtBasisParams(kind);
const message = wwCtVtResultMessage(kind, {{ reason_code: "invalid_ratio", status: "needs_configuration" }});
process.stdout.write(JSON.stringify({{ plan, params, message }}));
""",
        {"report": report, "status": status, "error": error, "groups": groups or {},
         "settings": {"recordingBasis": recording, "outputBasis": output, "recordingBasisExplicit": explicit}},
    )


def _quantity(**over):
    base = dict(ratio_status="configured", ratio_consumable=True, primary=132000.0, secondary=110.0, authority="manual",
                side="primary", side_status="recording_declared", declared_basis="primary", nominal_ll_kv=None, nominal_refused_reason=None, reason=None)
    base.update(over)
    return base


def _ch(role, quantity, gid):
    return {"role_key": role, "quantity": quantity, "measurement_group_id": gid, "declared_side": "unknown",
            "channel": {"kind": "source", "source_id": "s1", "channel_name": role}}


def _report(voltage, current, *, diagnostics=()):
    return {"channels": [_ch("Va", "voltage", "g1"), _ch("Ia", "current", "g2")], "diagnostics": list(diagnostics),
            "voltage": voltage, "current": current}


def _ct_q(**over):
    return _quantity(**{"primary": 1200.0, "secondary": 1.0, **over})


GROUPS = {"s1": [{"id": "g1", "display_name": "KPDN1 VOLTAGE"}, {"id": "g2", "display_name": "KPDN1 CURRENT"}]}
BASES = ("secondary", "primary")  # (wrong default recording basis for these tests' declared side, output)


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_authoritative_ratios_are_sent_only_when_conversion_needs_them(kind):
    report = _report(_quantity(), _ct_q())
    needed = _plan(report, "primary", "secondary", kind=kind)
    assert needed["params"] == {"recording_basis": "primary", "impedance_basis": "secondary", "vt_primary": "132000",
                                "vt_secondary": "110", "ct_primary": "1200", "ct_secondary": "1"}
    assert needed["plan"]["blockers"] == [] and needed["message"] is None
    same = _plan(report, "primary", "primary", kind=kind)
    assert same["params"] == {"recording_basis": "primary", "impedance_basis": "primary"}


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_an_auto_derived_vt_is_used_like_any_other_valid_vt(kind):
    vt = _quantity(primary=275000.0, secondary=110.0, authority="auto_nominal", nominal_ll_kv=275.0)
    out = _plan(_report(vt, _ct_q()), "primary", "secondary", groups=GROUPS, kind=kind)
    assert out["plan"]["blockers"] == [] and out["plan"]["warnings"] == [] and out["message"] is None
    assert out["params"] == {"recording_basis": "primary", "impedance_basis": "secondary", "vt_primary": "275000",
                             "vt_secondary": "110", "ct_primary": "1200", "ct_secondary": "1"}


@pytest.mark.parametrize("kind", ["impedance", "distance"])
@pytest.mark.parametrize("reason,fragment", [
    ("manual_conflict", "cannot be derived from its nominal voltage (275 kV): it conflicts with the channel evidence. "
                        "Resolve the nominal voltage in Recording Details, or enter the VT."),
    ("base_not_accepted", "cannot be derived from its nominal voltage (275 kV): the voltage base has not been accepted. "
                          "Accept it in Recording Details, or enter the VT."),
])
def test_a_nominal_that_cannot_be_used_explains_why_and_sends_no_ratio(kind, reason, fragment):
    vt = _quantity(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None, authority="not_configured",
                   nominal_ll_kv=275.0, nominal_refused_reason=reason)
    out = _plan(_report(vt, _ct_q()), "primary", "secondary", groups=GROUPS, kind=kind)
    assert out["params"] == {"recording_basis": "primary", "impedance_basis": "secondary"}
    assert [b["code"] for b in out["plan"]["blockers"]] == ["VT_NOMINAL_NOT_USABLE"]
    assert out["message"] == "The VT of 'KPDN1 VOLTAGE' " + fragment


def test_no_vt_and_no_nominal_asks_for_the_nominal_or_the_vt():
    vt = _quantity(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None, authority="not_configured")
    out = _plan(_report(vt, _ct_q()), "primary", "secondary", groups=GROUPS)
    assert [b["code"] for b in out["plan"]["blockers"]] == ["VT_AUTHORITY_MISSING"]
    assert out["message"] == ("VT is not configured for 'KPDN1 VOLTAGE'. Set the nominal voltage, or the VT primary kV and secondary V, "
                              "in Recording Details.")


@pytest.mark.parametrize("override,code,fragment", [
    (dict(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None), "CT_AUTHORITY_MISSING",
     "CT is not configured for 'KPDN1 CURRENT'. Set primary and secondary A in Recording Details."),
    (dict(ratio_status="invalid", ratio_consumable=False, primary=None, secondary=None, reason="non-positive secondary"),
     "CT_UNUSABLE", "The CT in 'KPDN1 CURRENT' is not usable (non-positive secondary). Correct it in Recording Details."),
    (dict(ratio_status="untrusted_authority", ratio_consumable=False, reason="unrecognised authority"), "CT_UNUSABLE",
     "The CT in 'KPDN1 CURRENT' is not usable (unrecognised authority). Correct it in Recording Details."),
    (dict(ratio_status="conflict", ratio_consumable=False), "CT_CONFLICT",
     "Phases use groups with different CT ratios (KPDN1 CURRENT). Align them in Recording Details."),
])
def test_each_unusable_ct_state_gets_its_own_actionable_message(override, code, fragment):
    out = _plan(_report(_quantity(), _ct_q(**override)), "primary", "secondary", groups=GROUPS)
    assert [b["code"] for b in out["plan"]["blockers"]] == [code]
    assert out["message"] == fragment
    assert "vt_primary" not in out["params"] and "ct_primary" not in out["params"]


def test_a_ct_held_by_another_current_group_is_pointed_out():
    ct = _ct_q(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None)
    report = _report(_quantity(), ct)
    groups = {"s1": [
        {"id": "g1", "display_name": "KPDN1 VOLTAGE", "kind": "voltage"},
        {"id": "g2", "display_name": "KPDN1 CURRENT", "kind": "current", "current_config": {"ct_primary_a": None, "ct_secondary_a": None}},
        {"id": "g3", "display_name": "KPDN1 CURRENT 2", "kind": "current", "current_config": {"ct_primary_a": 1200, "ct_secondary_a": 1}},
    ]}
    out = _plan(report, "primary", "secondary", groups=groups)
    assert out["message"] == ("CT is not configured for 'KPDN1 CURRENT'. Set primary and secondary A in Recording Details. "
                              "A CT of 1200 A / 1 A is configured on 'KPDN1 CURRENT 2', but Ia belongs to 'KPDN1 CURRENT'.")
    none = _plan(report, "primary", "secondary", groups={"s1": groups["s1"][:2]})
    assert none["message"] == "CT is not configured for 'KPDN1 CURRENT'. Set primary and secondary A in Recording Details."


def test_a_channel_outside_any_group_is_named():
    ct = _ct_q(ratio_status="no_group", ratio_consumable=False, primary=None, secondary=None)
    report = _report(_quantity(), ct)
    report["channels"][1]["measurement_group_id"] = None
    out = _plan(report, "primary", "secondary", groups=GROUPS)
    assert [b["code"] for b in out["plan"]["blockers"]] == ["CT_NO_GROUP"]
    assert out["message"] == "Ia is not in a Current Measurement Group. Add it in Recording Details."


def test_an_unresolved_channel_is_named_and_blocks():
    vt = _quantity(ratio_status="no_channels", ratio_consumable=False, primary=None, secondary=None)
    report = _report(vt, _ct_q(), diagnostics=[{"code": "CHANNEL_UNRESOLVED", "quantity": "voltage", "detail": {"role_key": "Va"}}])
    out = _plan(report, "primary", "secondary")
    assert out["message"] == "Role Va did not resolve to a channel in this Engineering Context."


def test_a_missing_vt_and_ct_are_both_reported():
    bad = dict(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None)
    out = _plan(_report(_quantity(**bad), _ct_q(**bad)), "primary", "secondary", groups=GROUPS)
    assert [b["code"] for b in out["plan"]["blockers"]] == ["VT_AUTHORITY_MISSING", "CT_AUTHORITY_MISSING"]


# --------------------------------------------------------------------------- measurement sides


def test_consistent_declared_sides_preselect_the_recording_basis():
    out = _node(
        """
wwCtVtApplyPreselection(wwCtVtPanel("impedance"));
process.stdout.write(JSON.stringify({ basis: wwImpedanceState.settings.recordingBasis, select: hosts.wwImpedanceRecordingBasisSelect.value }));
""",
        {"report": _report(_quantity(declared_basis="secondary", side="secondary"), _ct_q(declared_basis="secondary", side="secondary")),
         "settings": {"recordingBasis": "primary", "outputBasis": "primary", "recordingBasisExplicit": False}},
    )
    assert out == {"basis": "secondary", "select": "secondary"}


@pytest.mark.parametrize("settings,voltage,current", [
    ({"recordingBasisExplicit": True}, dict(declared_basis="secondary"), dict(declared_basis="secondary")),       # user chose it
    ({"recordingBasisExplicit": False}, dict(declared_basis=None, side_status="unknown"), dict(declared_basis=None, side_status="unknown")),
    ({"recordingBasisExplicit": False}, dict(declared_basis="secondary"), dict(declared_basis="primary")),         # sides differ
    ({"recordingBasisExplicit": False}, dict(declared_basis=None, side_status="mixed"), dict(declared_basis="primary")),
    ({"recordingBasisExplicit": False}, dict(declared_basis="secondary"), dict(declared_basis=None, side_status="unknown")),
])
def test_the_recording_basis_is_never_preselected_without_consistent_evidence(settings, voltage, current):
    out = _node(
        """
wwCtVtApplyPreselection(wwCtVtPanel("impedance"));
process.stdout.write(JSON.stringify(wwImpedanceState.settings.recordingBasis));
""",
        {"report": _report(_quantity(**voltage), _ct_q(**current)),
         "settings": {"recordingBasis": "primary", "outputBasis": "primary", **settings}},
    )
    assert out == "primary"


def test_conversion_across_different_sides_is_refused_with_the_independent_side_message():
    report = _report(_quantity(declared_basis="primary"), _ct_q(declared_basis="secondary", side="secondary"))
    out = _plan(report, "secondary", "primary", explicit=True)
    assert [b["code"] for b in out["plan"]["blockers"]] == ["SIDES_DIFFER"]
    assert "ratios" not in out["plan"] or out["plan"]["ratios"] is None
    assert "vt_primary" not in out["params"]
    assert ("Voltage and current are recorded on different sides (voltage: primary, current: secondary), so one Recording basis "
            "cannot describe both. This single-basis analysis cannot convert them; Independent-side mode is required.") == out["message"]


def test_mixed_sides_refuse_conversion_even_when_the_user_chose_a_basis():
    report = _report(_quantity(declared_basis=None, side_status="mixed", side="mixed"), _ct_q())
    out = _plan(report, "primary", "secondary", explicit=True)
    assert [b["code"] for b in out["plan"]["blockers"]] == ["SIDES_MIXED"] and "vt_primary" not in out["params"]


def test_an_undeclared_side_needs_an_explicit_choice_and_stays_marked_unverified():
    unknown = dict(declared_basis=None, side_status="unknown", side="unknown")
    report = _report(_quantity(**unknown), _ct_q(**unknown))
    pending = _plan(report, "primary", "secondary", explicit=False)
    assert pending["plan"]["confirmBasisNeeded"] is True and "vt_primary" not in pending["params"]
    assert pending["message"] == ("The recording does not declare whether the voltage/current channels are primary or secondary "
                                  "— choose the Recording basis explicitly.")
    chosen = _plan(report, "primary", "secondary", explicit=True)
    assert chosen["params"]["vt_primary"] == "132000" and chosen["params"]["ct_secondary"] == "1"
    assert [n["code"] for n in chosen["plan"]["notes"]] == ["BASIS_UNVERIFIED"]


def test_a_declared_side_contradicted_by_the_chosen_basis_is_shown_not_overridden():
    out = _plan(_report(_quantity(), _ct_q()), "secondary", "secondary", explicit=True)
    assert {w["code"] for w in out["plan"]["warnings"]} == {"RECORDING_BASIS_CONTRADICTS_VOLTAGE", "RECORDING_BASIS_CONTRADICTS_CURRENT"}
    assert out["params"] == {"recording_basis": "secondary", "impedance_basis": "secondary"}


def test_loading_and_failed_reads_never_convert():
    loading = _plan(None, "primary", "secondary", status="loading")
    assert loading["params"] == {"recording_basis": "primary", "impedance_basis": "secondary"}
    assert loading["message"] == "Checking the CT/VT configuration in Recording Details…"
    failed = _plan(None, "primary", "secondary", status="error", error="Request failed.")
    assert failed["message"] == "The CT/VT configuration could not be read from Recording Details (Request failed.). Conversion is not applied."
    assert "vt_primary" not in failed["params"]


def test_a_blocked_plan_only_rewrites_the_ratio_message():
    out = _node(
        """
const bad = { status: "needs_configuration", reason_code: "voltage_unit_unsupported", message: "x" };
process.stdout.write(JSON.stringify({ other: wwCtVtResultMessage("impedance", bad), none: wwCtVtResultMessage("impedance", null) }));
""",
        {"report": _report(_quantity(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None), _ct_q()),
         "settings": {"recordingBasis": "primary", "outputBasis": "secondary"}},
    )
    assert out == {"other": None, "none": None}


# --------------------------------------------------------------------------- rendering and navigation


def test_the_block_is_read_only_shows_values_and_navigates_to_the_group():
    out = _node(
        """
wwCtVtRender("impedance");
const html = hosts.wwImpedanceCtVtAuthority.innerHTML;
const hidden = hosts.wwImpedanceCtVtAuthority.hidden;
const event = (which) => ({ target: { closest: (sel) => (sel === "[data-ctvt-configure]" ? { getAttribute: () => which } : null) } });
wwCtVtHandleClick("impedance", event("voltage"));
wwCtVtHandleClick("impedance", event("current"));
wwImpedanceState.inputSource = "manual";
wwCtVtRender("impedance");
process.stdout.write(JSON.stringify({ html, hidden, navigations, hiddenInManual: hosts.wwImpedanceCtVtAuthority.hidden }));
""",
        {"report": _report(_quantity(), _ct_q()), "groups": GROUPS,
         "settings": {"recordingBasis": "primary", "outputBasis": "secondary"}},
    )
    html = out["html"]
    assert out["hidden"] is False and out["hiddenInManual"] is True
    assert "<input" not in html and "<select" not in html
    assert "132 kV / 110 V" in html and "1200 A / 1 A" in html and "Manual, KPDN1 VOLTAGE" in html
    assert html.count("Configure in Recording Details") == 2
    assert out["navigations"] == [["s1", "g1"], ["s1", "g2"]]


def test_the_block_shows_the_specific_warning_and_the_confirm_action():
    unknown = dict(declared_basis=None, side_status="unknown", side="unknown")
    out = _node(
        """
wwCtVtRender("distance");
process.stdout.write(JSON.stringify(hosts.wwDistanceCtVtAuthority.innerHTML));
""",
        {"report": _report(_quantity(**unknown), _ct_q(**unknown)), "groups": GROUPS,
         "settings": {"recordingBasis": "primary", "outputBasis": "secondary", "recordingBasisExplicit": False}},
    )
    assert 'data-ctvt-code="BASIS_UNDECLARED"' in out and "data-ctvt-confirm-basis" in out and "Use primary as the Recording basis" in out


# --------------------------------------------------------------------------- real API reports -> the real plan -> the real analyzers


def _api_report(client, ws, ctx, **params):
    resp = client.get(f"{_contexts(ws)}/{ctx}/protection-instrument-context", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_a_configured_recording_calculates_without_typing_and_matches_the_authoritative_ratios(client):
    ws = "ctvt-fe-configured"
    src, ctx = _bay(client, ws)                                   # VT 110000/110 and CT 1000/5 in the Measurement Groups
    report = _api_report(client, ws, ctx, analysis="impedance", phase="A")
    out = _plan(report, "primary", "secondary")
    assert out["plan"]["blockers"] == [] and out["plan"]["suggestedBasis"] == "primary"
    params = out["params"]
    assert (params["vt_primary"], params["vt_secondary"], params["ct_primary"], params["ct_secondary"]) == (
        f"{VT_P:g}", f"{VT_S:g}", f"{CT_P:g}", f"{CT_S:g}")
    body = _imp(client, ws, ctx, **params).json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)
    dist_report = _api_report(client, ws, ctx, analysis="distance_protection", loop="AB")
    dist_params = _plan(dist_report, "primary", "secondary", kind="distance")["params"]
    dist = _dist(client, ws, ctx, **dist_params).json()
    assert dist["status"] == "computed" and dist["impedance_basis"] == "secondary"


def test_a_nominal_only_vt_calculates_with_no_confirmation(client):
    """Owner decision 2026-11-21: nominal kV / 110 V is a valid VT; no Edit -> Save is needed."""
    ws = "ctvt-fe-nominal"
    src, ctx = _bay(client, ws, groups=False)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), f"vg-{src}")
    _group(client, ws, src, KIND_CURRENT, ("IA", "IB", "IC"), f"ig-{src}")
    _ct(client, ws, f"ig-{src}", CT_P, CT_S, note="CT nameplate")
    client.app.state.voltage_group_config_registry.update_fields(ws, f"vg-{src}", nominal_voltage_ll_kv=110.0, update_nominal=True)
    report = _api_report(client, ws, ctx, analysis="impedance", phase="A")
    assert report["voltage"]["authority"] == "auto_nominal" and report["voltage"]["ratio_consumable"] is True
    groups = {src: client.get(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups").json()}
    out = _plan(report, "primary", "secondary", groups=groups)
    assert out["plan"]["blockers"] == [] and out["message"] is None
    assert (out["params"]["vt_primary"], out["params"]["vt_secondary"]) == ("110000", "110")
    body = _imp(client, ws, ctx, **out["params"]).json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)


def test_a_refused_nominal_blocks_with_its_reason_and_keeps_the_waveform_channels(client):
    ws = "ctvt-fe-nominal-refused"
    src, ctx = _bay(client, ws, groups=False)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), f"vg-{src}")
    _group(client, ws, src, KIND_CURRENT, ("IA", "IB", "IC"), f"ig-{src}")
    _ct(client, ws, f"ig-{src}", CT_P, CT_S, note="CT nameplate")
    reg = client.app.state.voltage_group_config_registry
    reg.update_fields(ws, f"vg-{src}", nominal_voltage_ll_kv=132.0, update_nominal=True)
    config = reg.get(ws, f"vg-{src}")
    config.manual_conflict_detected = True
    reg.upsert(config)
    report = _api_report(client, ws, ctx, analysis="impedance", phase="A")
    groups = {src: client.get(f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups").json()}
    out = _plan(report, "primary", "secondary", groups=groups)
    assert out["params"] == {"recording_basis": "primary", "impedance_basis": "secondary"}
    assert out["message"] == (f"The VT of 'vg-{src}' cannot be derived from its nominal voltage (132 kV): it conflicts with the "
                              "channel evidence. Resolve the nominal voltage in Recording Details, or enter the VT.")
    body = _imp(client, ws, ctx, **out["params"]).json()                    # the page still asks, so waveforms stay visible
    assert body["status"] == "needs_configuration" and body["reason_code"] == "invalid_ratio"
    assert body["voltage_channel_ref"]["channel_name"] == "ZBAY_VA" and body["current_channel_ref"]["channel_name"] == "ZBAY_IA"


def test_a_missing_ct_blocks_with_the_specific_message(client):
    ws = "ctvt-fe-no-ct"
    src, ctx = _bay(client, ws, groups=False)
    _group(client, ws, src, KIND_VOLTAGE, ("VA", "VB", "VC"), f"vg-{src}")
    _vt(client, ws, f"vg-{src}", VT_P, VT_S, note="VT nameplate")
    out = _plan(_api_report(client, ws, ctx, analysis="impedance", phase="A"), "primary", "secondary")
    assert [b["code"] for b in out["plan"]["blockers"]] == ["CT_NO_GROUP"]
    assert out["message"] == "ZBAY_IA is not in a Current Measurement Group. Add it in Recording Details."


def test_real_recordings_with_different_declared_sides_are_not_converted(client):
    ws = "ctvt-fe-sides"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    report = _api_report(client, ws, ctx, analysis="impedance", phase="A")
    out = _plan(report, "secondary", "primary", explicit=True)
    assert [b["code"] for b in out["plan"]["blockers"]] == ["SIDES_DIFFER"] and "vt_primary" not in out["params"]


def test_real_recordings_without_declared_sides_need_an_explicit_basis(client):
    ws = "ctvt-fe-undeclared"
    src, ctx = _bay(client, ws, ps={n: "" for n in ("VA", "VB", "VC", "IA", "IB", "IC")})
    report = _api_report(client, ws, ctx, analysis="impedance", phase="A")
    pending = _plan(report, "primary", "secondary", explicit=False)
    assert pending["plan"]["confirmBasisNeeded"] is True and "vt_primary" not in pending["params"]
    chosen = _plan(report, "primary", "secondary", explicit=True)
    assert "vt_primary" in chosen["params"] and [n["code"] for n in chosen["plan"]["notes"]] == ["BASIS_UNVERIFIED"]


def _refresh(report, settings, *, groups_on_server, cached=None, kind="impedance"):
    return _node(
        f"""
const calls = [];
async function wwPhasorFetchJson(url) {{ calls.push(["report", url]); return input.report; }}
async function wwFetchMeasurementGroupsForSource(sourceId) {{ calls.push(["groups", sourceId]); ww.measurementGroups.set(sourceId, input.serverGroups[sourceId]); }}
const kind = "{kind}";
const state = kind === "distance" ? wwDistanceState : wwImpedanceState;
state.ctVt = null;
(async () => {{
    await wwCtVtRefresh(kind, true);
    const first = {{ status: state.ctVt.status, basis: state.settings.recordingBasis, reruns: reruns.slice(), calls: calls.slice() }};
    await wwCtVtRefresh(kind, false);                       // same key: no second read
    process.stdout.write(JSON.stringify({{ first, again: calls.length, html: hosts[kind === "distance" ? "wwDistanceCtVtAuthority" : "wwImpedanceCtVtAuthority"].innerHTML }}));
}})();
""",
        {"report": report, "settings": settings, "groups": cached or {}, "serverGroups": groups_on_server},
    )


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_refresh_reads_the_context_once_loads_group_names_preselects_and_rerequests(kind):
    report = _report(_quantity(declared_basis="secondary", side="secondary"), _ct_q(declared_basis="secondary", side="secondary"))
    out = _refresh(report, {"recordingBasis": "primary", "outputBasis": "primary", "recordingBasisExplicit": False},
                   groups_on_server=GROUPS, kind=kind)
    first = out["first"]
    assert first["status"] == "ready" and first["basis"] == "secondary"           # preselected from consistent declared sides
    assert first["reruns"] == [kind]                                               # the request changed, so it is re-sent
    analysis, scope = ("distance_protection", "loop=AB") if kind == "distance" else ("impedance", "phase=A")
    assert first["calls"][0][1] == f"/api/v1/workspaces/w/engineering-contexts/c/protection-instrument-context?analysis={analysis}&{scope}"
    assert [c for c in first["calls"] if c[0] == "groups"] == [["groups", "s1"]]
    assert out["again"] == len(first["calls"])                                     # cached: nothing re-read
    assert "KPDN1 VOLTAGE" in out["html"] and "KPDN1 CURRENT" in out["html"]


def test_refresh_never_touches_a_basis_the_user_chose_and_skips_cached_group_names():
    report = _report(_quantity(declared_basis="secondary", side="secondary"), _ct_q(declared_basis="secondary", side="secondary"))
    out = _refresh(report, {"recordingBasis": "primary", "outputBasis": "primary", "recordingBasisExplicit": True},
                   groups_on_server=GROUPS, cached=GROUPS)
    assert out["first"]["basis"] == "primary"
    assert [c[0] for c in out["first"]["calls"]] == ["report"]                     # names already cached
