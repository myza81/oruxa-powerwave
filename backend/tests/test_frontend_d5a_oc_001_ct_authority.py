"""D5A-OC-001 frontend: recorded Overcurrent takes its CT only from the Recording Details Measurement Group
(read through the D5A-2A `protection-instrument-context` API), read-only, via the SAME shared `wwCtVt*` block
Impedance and Distance use.

The consumer logic is tested by running the REAL helper block of frontend/index.html with Node (no
re-implementation): what a request may carry, what the user is told, when a result is withheld, and how a stale
read is discarded.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from tests.test_frontend_d5a_ctvt_authority import (  # noqa: F401  (shared fixtures and builders)
    GROUPS, SOURCE, _block, _ch, _code_only, _ct_q, _plan, _quantity, _report,
)

CT_GROUPS = {"s1": [{"id": "g2", "display_name": "KPDN1 CURRENT", "kind": "current"}]}


def _oc_report(current, *, group="g2", diagnostics=()):
    """Overcurrent resolves ONE current channel: no voltage quantity at all."""
    return {"analysis": "overcurrent", "channels": [_ch("Ia", "current", group)], "diagnostics": list(diagnostics),
            "voltage": None, "current": current}


def _function(name: str) -> str:
    start = SOURCE.index(f"function {name}(")
    nxt = SOURCE.index("\n        }\n", start)
    return SOURCE[start:nxt]


# --------------------------------------------------------------------------- static guarantees


def test_recorded_mode_has_a_read_only_ct_host_and_no_competing_ct_editor():
    host = re.search(r'<div class="ww-ctvt-authority[^>]*id="wwOvercurrentCtVtAuthority"[^>]*>', SOURCE).group(0)
    assert "hidden" in host and "<input" not in host
    body = _function("wwOvercurrentCtFieldsNeeded")
    assert "if (wwOvercurrentState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_MANUAL) return false;" in body
    assert "settings.recordingBasis" not in body


def test_manual_mode_inputs_and_requests_are_untouched():
    assert 'id="wwOvercurrentCtPrimaryInput"' in SOURCE and 'id="wwOvercurrentCtSecondaryInput"' in SOURCE
    manual = _function("wwOvercurrentRequestManualAnalysis")
    assert 'if (m.inputBasis === "primary" && s.ctPrimary !== null && s.ctSecondary !== null) {' in manual
    loading = _function("wwOvercurrentRequestManualLoadingAnalysis")
    assert "if (s.ctPrimary !== null && s.ctSecondary !== null) {" in loading


def test_the_recorded_request_takes_its_ct_only_from_the_authoritative_plan():
    body = _function("wwOvercurrentRequestAnalysis")
    assert 'wwCtVtBasisParams("overcurrent")' in body
    assert "ctPrimary" not in body and "ctSecondary" not in body and "recording_basis: s.recordingBasis" not in body


def test_the_ct_is_never_derived_from_equipment_or_nominal_data():
    code = _code_only(_block()).lower()
    for forbidden in ("mva", "rated", "nameplate", "capacity", "equipment", "nominal_current"):
        assert forbidden not in code
    assert "wwNavigateToRdForGroup(target.sourceId, target.groupId)" in _code_only(_block())


def test_every_lifecycle_event_refreshes_or_clears_the_authority():
    assert 'wwCtVtRefresh("overcurrent", true);' in _function("wwOvercurrentLoadForSelectedContext")
    assert 'wwCtVtRefresh("overcurrent", false);' in _function("wwOvercurrentHandleSettingsChanged")
    assert 'wwCtVtRefresh("overcurrent", false);' in _function("wwOvercurrentSetInputSource")
    empty = _function("wwOvercurrentShowEmptyState")
    assert 'wwCtVtReset("overcurrent");' in empty and 'wwCtVtRender("overcurrent");' in empty
    reset = _function("wwOvercurrentResetState")
    for needle in ('wwCtVtReset("overcurrent");', "settings.recordingBasisExplicit = false;",
                   "settings.ctPrimary = null;", "settings.ctSecondary = null;", 'basisSelect.value = "secondary"'):
        assert needle in reset


def test_the_basis_choice_is_marked_explicit_and_the_host_is_wired():
    assert re.search(r'wwOvercurrentBasisSelect"\)\.addEventListener\("change".*?wwCtVtNoteRecordingBasisChosen\("overcurrent"\);',
                     SOURCE, re.S)
    assert 'getElementById("wwOvercurrentCtVtAuthority").addEventListener("click"' in SOURCE


def test_a_blocked_result_still_feeds_related_waveforms_and_is_never_plotted():
    roles = _function("wwOvercurrentComputeActiveRelatedWaveformRoles")
    assert 'result.status !== "computed"' not in roles and "!result.channel_ref" in roles
    active = _function("wwOvercurrentActiveResult")
    assert 'wwCtVtPlanFor("overcurrent").blockers.length > 0 ? null' in active
    render = _function("wwOvercurrentRenderResult")
    assert 'wwCtVtPlanFor("overcurrent").blockers.length > 0' in render and "wwOvercurrentPushRelatedWaveformRoles();" in render


def test_impedance_and_distance_are_not_strict():
    assert _function("wwCtVtPlanFor").count("panel.strictSides") == 1
    for kind in ("impedance", "distance"):
        assert re.search(rf'kind: "{kind}".*?strictSides: false', SOURCE, re.S)
    assert re.search(r'kind: "overcurrent".*?strictSides: true', SOURCE, re.S)


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
let workspaceId = "w";
function currentWorkspaceId() { return workspaceId; }
function apiBaseUrl() { return ""; }
const navigations = [];
function wwNavigateToRdForGroup(sourceId, groupId) { navigations.push([sourceId, groupId]); }
const fetched = [];
const pending = [];
function wwPhasorFetchJson(url) { fetched.push(url); return new Promise((resolve, reject) => pending.push({ url, resolve, reject })); }
async function wwFetchMeasurementGroupsForSource() {}
const hosts = {};
const document = { getElementById: (id) => (hosts[id] = hosts[id] || { hidden: true, innerHTML: "", value: "" }) };
const mk = (extra) => Object.assign({ selectedContextId: "c", inputSource: "recording", settings: JSON.parse(JSON.stringify(input.settings || {})),
    ctVt: { key: "k", status: input.status || "ready", report: input.report || null, error: input.error || "", generation: 0, requestedSignature: null } }, extra);
const wwOvercurrentState = mk({ phase: "A" });
const wwImpedanceState = mk({ phase: "A" });
const wwDistanceState = mk({ loop: "AB" });
const reruns = [];
function wwOvercurrentHandleSettingsChanged() { reruns.push("overcurrent"); }
function wwImpedanceHandleSettingsChanged() { reruns.push("impedance"); }
function wwDistanceHandleSettingsChanged() { reruns.push("distance"); }
"""
    done = subprocess.run([node, "-e", prelude + _block() + script], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _oc(report, basis, *, explicit=False, status="ready", error="", groups=None, result=None):
    result = result or {"reason_code": "invalid_ct_values", "status": "needs_configuration"}
    return _node(
        f"""
const plan = wwCtVtPlanFor("overcurrent");
const params = wwCtVtBasisParams("overcurrent");
const message = wwCtVtResultMessage("overcurrent", {json.dumps(result)});
process.stdout.write(JSON.stringify({{ plan, params, message }}));
""",
        {"report": report, "status": status, "error": error, "groups": groups if groups is not None else CT_GROUPS,
         "settings": {"recordingBasis": basis, "recordingBasisExplicit": explicit}},
    )


def _codes(out):
    return [b["code"] for b in out["plan"]["blockers"]]


# --------------------------------------------------------------------------- one conversion, only when needed


def test_a_primary_recording_sends_only_the_ct_and_never_a_vt_or_an_impedance_basis():
    out = _oc(_oc_report(_ct_q()), "primary", explicit=True)
    assert out["params"] == {"recording_basis": "primary", "ct_primary": "1200", "ct_secondary": "1"}
    assert out["plan"]["blockers"] == [] and out["plan"]["warnings"] == [] and out["message"] is None


def test_a_secondary_recording_is_never_converted_so_it_sends_no_ct():
    out = _oc(_oc_report(_ct_q()), "secondary", explicit=True)
    assert out["params"] == {"recording_basis": "secondary"}
    assert out["plan"]["conversionNeeded"] is False and out["plan"]["ratios"] is None


@pytest.mark.parametrize("override", [
    dict(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None),
    dict(ratio_status="invalid", ratio_consumable=False, primary=None, secondary=None),
    dict(ratio_status="untrusted_authority", ratio_consumable=False),
    dict(ratio_status="no_group", ratio_consumable=False, primary=None, secondary=None),
])
def test_an_unusable_ct_blocks_only_when_a_conversion_is_needed(override):
    # each recording declares the side its basis names, so only the CT decides
    secondary = _oc(_oc_report(_ct_q(side="secondary", declared_basis="secondary", **override)), "secondary", explicit=True)
    assert secondary["plan"]["blockers"] == [] and secondary["params"] == {"recording_basis": "secondary"}
    primary = _oc(_oc_report(_ct_q(**override)), "primary", explicit=True)
    assert len(primary["plan"]["blockers"]) == 1 and primary["plan"]["ratios"] is None
    assert primary["params"] == {"recording_basis": "primary"}                      # never a partial or stale CT


def test_each_unusable_ct_names_the_group_that_owns_the_channel_and_links_to_it():
    out = _oc(_oc_report(_ct_q(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None)),
              "primary", explicit=True)
    assert _codes(out) == ["CT_AUTHORITY_MISSING"]
    assert out["message"] == "CT is not configured for 'KPDN1 CURRENT'. Set primary and secondary A in Recording Details."
    assert out["plan"]["blockers"][0]["target"] == {"sourceId": "s1", "groupId": "g2"}


def test_a_ct_held_by_an_unrelated_group_is_named_but_never_used():
    groups = {"s1": [
        {"id": "g2", "display_name": "KPDN1 CURRENT", "kind": "current", "current_config": {"ct_primary_a": None, "ct_secondary_a": None}},
        {"id": "g3", "display_name": "SPARE CURRENT", "kind": "current", "current_config": {"ct_primary_a": 2000, "ct_secondary_a": 1}},
    ]}
    out = _oc(_oc_report(_ct_q(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None)),
              "primary", explicit=True, groups=groups)
    assert "A CT of 2000 A / 1 A is configured on 'SPARE CURRENT', but Ia belongs to 'KPDN1 CURRENT'." in out["message"]
    assert out["params"] == {"recording_basis": "primary"}
    assert out["plan"]["blockers"][0]["target"]["groupId"] == "g2"


def test_an_unresolved_current_channel_is_named():
    report = _oc_report(_ct_q(ratio_status="no_channels", ratio_consumable=False, primary=None, secondary=None),
                        diagnostics=[{"code": "CHANNEL_UNRESOLVED", "quantity": "current", "detail": {"role_key": "Ia"}}])
    report["channels"] = []
    out = _oc(report, "primary", explicit=True)
    assert out["message"] == "Role Ia did not resolve to a channel in this Engineering Context."


# --------------------------------------------------------------------------- measurement side


def test_a_declared_side_preselects_the_basis_only_until_the_user_chooses():
    declared_secondary = _oc_report(_ct_q(side="secondary", declared_basis="secondary"))
    out = _node(
        """
wwCtVtApplyPreselection(wwCtVtPanel("overcurrent"));
process.stdout.write(JSON.stringify({ basis: wwOvercurrentState.settings.recordingBasis, select: hosts.wwOvercurrentBasisSelect && hosts.wwOvercurrentBasisSelect.value }));
""",
        {"report": declared_secondary, "settings": {"recordingBasis": "primary", "recordingBasisExplicit": False}, "groups": CT_GROUPS},
    )
    assert out == {"basis": "secondary", "select": "secondary"}
    chosen = _node(
        """
wwCtVtApplyPreselection(wwCtVtPanel("overcurrent"));
process.stdout.write(JSON.stringify({ basis: wwOvercurrentState.settings.recordingBasis }));
""",
        {"report": declared_secondary, "settings": {"recordingBasis": "primary", "recordingBasisExplicit": True}, "groups": CT_GROUPS},
    )
    assert chosen == {"basis": "primary"}


@pytest.mark.parametrize("declared,basis", [("secondary", "primary"), ("primary", "secondary")])
def test_a_basis_that_contradicts_the_declared_side_is_a_blocker_in_both_directions(declared, basis):
    out = _oc(_oc_report(_ct_q(side=declared, declared_basis=declared)), basis, explicit=True)
    assert _codes(out) == ["RECORDING_BASIS_CONTRADICTS_CURRENT"]
    assert out["plan"]["warnings"] == [] and out["plan"]["ratios"] is None
    assert out["params"] == {"recording_basis": basis}                            # never a CT on a contradicted request
    assert f"declares the current as {declared}, but the Recording basis is {basis}" in out["plan"]["blockers"][0]["text"]
    assert "No result is shown until the Recording basis matches." in out["plan"]["blockers"][0]["text"]
    withheld = _oc(_oc_report(_ct_q(side=declared, declared_basis=declared)), basis, explicit=True,
                   result={"status": "computed", "reason_code": None})
    assert "No result is shown" in withheld["message"]                             # even though the backend could compute


@pytest.mark.parametrize("declared", ["primary", "secondary"])
def test_a_basis_that_agrees_with_the_declared_side_raises_nothing(declared):
    out = _oc(_oc_report(_ct_q(side=declared, declared_basis=declared)), declared, explicit=True)
    assert out["plan"]["blockers"] == [] and out["plan"]["warnings"] == [] and out["plan"]["notes"] == []


UNKNOWN = dict(side="unknown", side_status="unknown", declared_basis=None)


def test_an_undeclared_side_is_never_inferred_and_a_primary_choice_must_be_confirmed():
    report = _oc_report(_ct_q(**UNKNOWN))
    unconfirmed = _oc(report, "primary", explicit=False)
    assert _codes(unconfirmed) == ["BASIS_UNDECLARED"] and unconfirmed["plan"]["confirmBasisNeeded"] is True
    assert unconfirmed["message"] is None or "choose the Recording basis explicitly" in unconfirmed["message"]
    assert "the current channel is primary or secondary" in unconfirmed["plan"]["blockers"][0]["text"]
    assert unconfirmed["params"] == {"recording_basis": "primary"}
    chosen = _oc(report, "primary", explicit=True)
    assert chosen["plan"]["blockers"] == [] and [n["code"] for n in chosen["plan"]["notes"]] == ["BASIS_UNVERIFIED"]
    assert chosen["params"] == {"recording_basis": "primary", "ct_primary": "1200", "ct_secondary": "1"}


def test_an_undeclared_secondary_choice_keeps_its_provenance_and_the_default_stays_silent():
    report = _oc_report(_ct_q(**UNKNOWN))
    assert [n["code"] for n in _oc(report, "secondary", explicit=True)["plan"]["notes"]] == ["BASIS_UNVERIFIED"]
    assert _oc(report, "secondary", explicit=False)["plan"]["notes"] == []


def test_the_ct_ratio_never_decides_the_side():
    for ratio in ((1200.0, 1.0), (1000.0, 1000.0), (5.0, 5.0)):
        out = _oc(_oc_report(_ct_q(primary=ratio[0], secondary=ratio[1], **UNKNOWN)), "primary", explicit=False)
        assert _codes(out) == ["BASIS_UNDECLARED"]
        assert out["plan"]["suggestedBasis"] is None


# --------------------------------------------------------------------------- loading and failure


def test_no_result_is_shown_on_an_unconfirmed_basis_while_the_report_is_loading():
    for basis, explicit, blocked in (("secondary", False, True), ("primary", False, True), ("primary", True, True), ("secondary", True, False)):
        out = _oc(None, basis, explicit=explicit, status="loading")
        assert (_codes(out) == ["CONTEXT_LOADING"]) is blocked, (basis, explicit)


def test_an_unreadable_report_blocks_a_needed_conversion_and_never_a_secondary_recording():
    assert _codes(_oc(None, "primary", explicit=True, status="error", error="boom")) == ["CONTEXT_UNAVAILABLE"]
    assert _codes(_oc(None, "secondary", explicit=False, status="error", error="boom")) == []
    assert _codes(_oc(None, "secondary", explicit=False, status="idle")) == []


def test_the_signature_changes_whenever_the_answer_changes_what_a_request_would_carry():
    sig = lambda *a, **k: _node(  # noqa: E731
        'process.stdout.write(JSON.stringify(wwCtVtSignature("overcurrent")));',
        {"report": a[0], "settings": {"recordingBasis": a[1], "recordingBasisExplicit": True}, "status": k.get("status", "ready"), "groups": CT_GROUPS})
    ok = sig(_oc_report(_ct_q()), "primary")
    assert ok == "ratios:1200/1"
    assert sig(_oc_report(_ct_q(primary=600.0)), "primary") == "ratios:600/1"           # a CT changed in Recording Details
    assert sig(_oc_report(_ct_q(side="secondary", declared_basis="secondary")), "secondary") == "blocked:"   # nothing needed
    assert sig(_oc_report(_ct_q(ratio_status="not_configured", ratio_consumable=False)), "primary") == "blocked:CT_AUTHORITY_MISSING"


# --------------------------------------------------------------------------- stale reads and lifecycle


def test_an_older_read_can_never_overwrite_a_newer_selection():
    out = _node(
        """
(async () => {
  wwOvercurrentState.phase = "B";
  const first = wwCtVtRefresh("overcurrent", true);
  wwOvercurrentState.phase = "C";
  const second = wwCtVtRefresh("overcurrent", true);
  pending[1].resolve({ channels: [], diagnostics: [], voltage: null, current: { ratio_status: "configured", ratio_consumable: true, primary: 600, secondary: 1 } });
  await second;
  pending[0].resolve({ channels: [], diagnostics: [], voltage: null, current: { ratio_status: "configured", ratio_consumable: true, primary: 111, secondary: 1 } });
  await first;
  const st = wwCtVtStateOf(wwCtVtPanel("overcurrent"));
  process.stdout.write(JSON.stringify({ primary: st.report.current.primary, key: st.key, urls: fetched.length }));
})();
""",
        {"settings": {"recordingBasis": "primary", "recordingBasisExplicit": True}, "groups": CT_GROUPS},
    )
    assert out["primary"] == 600 and out["urls"] == 2 and out["key"].endswith("|overcurrent|C|")


def test_a_reset_discards_a_read_still_in_flight_and_empties_the_authority():
    out = _node(
        """
(async () => {
  const read = wwCtVtRefresh("overcurrent", true);
  wwCtVtReset("overcurrent");
  pending[0].resolve({ channels: [], diagnostics: [], voltage: null, current: { ratio_status: "configured", ratio_consumable: true, primary: 111, secondary: 1 } });
  await read;
  const st = wwCtVtStateOf(wwCtVtPanel("overcurrent"));
  wwCtVtRender("overcurrent");
  process.stdout.write(JSON.stringify({ status: st.status, report: st.report, hidden: hosts.wwOvercurrentCtVtAuthority.hidden }));
})();
""",
        {"settings": {"recordingBasis": "primary", "recordingBasisExplicit": True}, "groups": CT_GROUPS, "status": "idle"},
    )
    assert out == {"status": "idle", "report": None, "hidden": True}


def test_the_read_asks_for_the_overcurrent_authority_of_the_selected_phase_and_context():
    out = _node(
        """
(async () => {
  wwOvercurrentState.phase = "B";
  wwCtVtRefresh("overcurrent", true);
  process.stdout.write(JSON.stringify({ url: fetched[0] }));
})();
""",
        {"settings": {"recordingBasis": "secondary"}, "groups": CT_GROUPS, "status": "idle"},
    )
    assert out["url"] == "/api/v1/workspaces/w/engineering-contexts/c/protection-instrument-context?analysis=overcurrent&phase=B"


def test_a_change_to_the_workspace_or_context_is_a_different_read():
    out = _node(
        """
(async () => {
  wwCtVtRefresh("overcurrent", true);
  const first = wwCtVtStateOf(wwCtVtPanel("overcurrent")).key;
  workspaceId = "other";
  wwCtVtRefresh("overcurrent", false);                    // not forced: a new workspace is a new key, so it re-reads
  const second = wwCtVtStateOf(wwCtVtPanel("overcurrent")).key;
  wwOvercurrentState.selectedContextId = "d";
  wwCtVtRefresh("overcurrent", false);
  const third = wwCtVtStateOf(wwCtVtPanel("overcurrent")).key;
  process.stdout.write(JSON.stringify({ keys: [first, second, third], reads: fetched.length }));
})();
""",
        {"settings": {"recordingBasis": "secondary"}, "groups": CT_GROUPS, "status": "idle"},
    )
    assert len(set(out["keys"])) == 3 and out["reads"] == 3


# --------------------------------------------------------------------------- rendering


def _render(report, basis, *, explicit=True, status="ready", source="recording"):
    return _node(
        f"""
wwOvercurrentState.inputSource = "{source}";
wwCtVtRender("overcurrent");
process.stdout.write(JSON.stringify({{ html: hosts.wwOvercurrentCtVtAuthority.innerHTML, hidden: hosts.wwOvercurrentCtVtAuthority.hidden }}));
""",
        {"report": report, "status": status, "groups": CT_GROUPS,
         "settings": {"recordingBasis": basis, "recordingBasisExplicit": explicit}},
    )


def test_the_block_shows_one_read_only_ct_with_its_group_and_provenance():
    out = _render(_oc_report(_ct_q()), "primary")
    html = out["html"]
    assert out["hidden"] is False and "<input" not in html and "<select" not in html and "<textarea" not in html
    assert "CT from Recording Details" in html and "CT / VT" not in html
    assert 'data-ctvt-value="current"' in html and "1200 A / 1 A" in html and "Manual" in html and "KPDN1 CURRENT" in html
    assert 'data-ctvt-quantity="voltage"' not in html
    assert 'data-ctvt-configure="current"' in html and "Configure in Recording Details" in html


def test_an_unneeded_missing_ct_is_explained_rather_than_flagged():
    missing = _oc_report(_ct_q(ratio_status="not_configured", ratio_consumable=False, primary=None, secondary=None))
    secondary = _render(missing, "secondary")["html"]
    assert "not configured" in secondary and "not needed for a secondary recording" in secondary and "ww-ctvt-missing" not in secondary
    primary = _render(missing, "primary")["html"]
    assert "ww-ctvt-missing" in primary and "not needed" not in primary and 'data-ctvt-code="CT_AUTHORITY_MISSING"' in primary


def test_the_block_is_hidden_in_manual_mode_and_while_idle():
    assert _render(_oc_report(_ct_q()), "primary", source="manual")["hidden"] is True
    assert _render(None, "primary", status="idle")["hidden"] is True


def test_the_configure_button_opens_the_group_that_owns_the_channel():
    out = _node(
        """
const event = { target: { closest: (sel) => (sel === "[data-ctvt-configure]" ? { getAttribute: () => "current" } : null) } };
wwCtVtHandleClick("overcurrent", event);
process.stdout.write(JSON.stringify({ navigations }));
""",
        {"report": _oc_report(_ct_q(), group="g2"), "settings": {"recordingBasis": "primary"}, "groups": CT_GROUPS},
    )
    assert out["navigations"] == [["s1", "g2"]]


# --------------------------------------------------------------------------- Impedance / Distance are unaffected


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_impedance_and_distance_still_treat_a_contradiction_as_a_warning_and_keep_their_params(kind):
    voltage = _quantity(side="secondary", declared_basis="secondary")
    current = _ct_q(side="secondary", declared_basis="secondary")
    out = _plan(_report(voltage, current), "primary", "primary", kind=kind)
    assert out["plan"]["blockers"] == []
    assert [w["code"] for w in out["plan"]["warnings"]] == ["RECORDING_BASIS_CONTRADICTS_VOLTAGE", "RECORDING_BASIS_CONTRADICTS_CURRENT"]
    needed = _plan(_report(_quantity(), _ct_q()), "primary", "secondary", kind=kind)
    assert needed["params"] == {"recording_basis": "primary", "impedance_basis": "secondary", "vt_primary": "132000",
                                "vt_secondary": "110", "ct_primary": "1200", "ct_secondary": "1"}
    assert needed["plan"]["blockers"] == []
