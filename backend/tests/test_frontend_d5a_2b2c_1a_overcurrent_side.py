"""D5A-2B2C-1A frontend: recorded Overcurrent shows the measurement side and CT that Recording Details decides, read-only.

The page has no Recording-basis input and its request carries neither a basis nor a CT: the backend takes the side of the
consumed Current channel (Level 1 recording, Level 2 Current Measurement Group) and the CT of that channel's own group
from Recording Details, and enforces it. The page only reads the backend's `overcurrent-recorded-input` report and shows it.

This file supersedes the D5A-OC-001 frontend tests, which exercised the shared Impedance/Distance `wwCtVt*` plan with a
user-chosen Recording basis (a design DEC-216 retires). Every behaviour that file protected and that still applies is kept
here: Manual mode untouched, nothing shown while the read is in flight, stale reads discarded, a reset empties everything,
Related Waveforms stay available for a blocked result, and Impedance/Distance are unaffected.

The consumer logic runs the REAL `D5A-2B2C-1A-BLOCK` of frontend/index.html with Node against a fake network (no
re-implementation).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_frontend_d5a_ctvt_authority import _plan, _quantity, _report as _dist_report, _ct_q

SOURCE = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
BLOCK_START, BLOCK_END = "// D5A-2B2C-1A-BLOCK-START", "// D5A-2B2C-1A-BLOCK-END"


def _block() -> str:
    start = SOURCE.index(BLOCK_START)
    return SOURCE[start:SOURCE.index(BLOCK_END, start)]


def _code_only(text: str) -> str:
    lines = (line for line in text.splitlines() if not line.strip().startswith("//"))
    return "\n".join(re.sub(r"\s//\s.*$", "", line) for line in lines)


def _function(name: str) -> str:
    start = SOURCE.index(f"function {name}(")
    return SOURCE[start:SOURCE.index("\n        }\n", start)]


def _report(**over):
    """What `GET .../overcurrent-recorded-input?phase=A` returns for a Primary recording with a configured CT."""
    base = {
        "status": "ready", "engineering_context_id": "c", "phase": "A",
        "channel_ref": {"kind": "source", "source_id": "s1", "channel_name": "ZBAY_IA", "calculated_channel_id": None},
        "channel_unit": "A", "measurement_group_id": "g2", "measurement_group_name": "KPDN1 CURRENT",
        "measurement_side": {"effective_side": "primary", "authority": "recording_channel_declared", "declared_side": "primary",
                             "usable": True, "strict_usable": True, "inferred": False, "diagnostics": []},
        "ct": {"status": "configured", "consumable": True, "primary": 1200.0, "secondary": 1.0, "ratio": 1200.0,
               "authority": "manual", "reason": None, "group_ids": ["g2"]},
        "conversion": "primary_to_relay_secondary", "reason_code": None, "message": "ready",
    }
    base.update(over)
    return base


def _side(effective="primary", authority="recording_channel_declared", declared="primary", diagnostics=(), inferred=False):
    return {"effective_side": effective, "authority": authority, "declared_side": declared, "usable": effective != "unknown",
            "strict_usable": effective != "unknown" and not inferred, "inferred": inferred, "diagnostics": list(diagnostics)}


def _blocked(code, message, **over):
    return _report(status="needs_configuration", reason_code=code, message=message, conversion=None, **over)


# --------------------------------------------------------------------------- static guarantees


def test_recorded_mode_has_a_read_only_authority_host_and_no_basis_or_ct_editor():
    assert 'id="wwOvercurrentBasisSelect"' not in SOURCE and 'id="wwOvercurrentBasisField"' not in SOURCE
    host = re.search(r'<div class="ww-ctvt-authority[^>]*id="wwOvercurrentCtVtAuthority"[^>]*>', SOURCE).group(0)
    assert "hidden" in host and "<input" not in host and "<select" not in host
    body = _function("wwOvercurrentCtFieldsNeeded")
    assert "if (wwOvercurrentState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_MANUAL) return false;" in body
    # the page keeps no recorded-basis state any more
    state = SOURCE[SOURCE.index("const wwOvercurrentState = {"):SOURCE.index("curveCache: null,")]
    assert "recordingBasis" not in state and "recordedInput:" in state


def test_manual_mode_inputs_and_requests_are_untouched():
    assert 'id="wwOvercurrentCtPrimaryInput"' in SOURCE and 'id="wwOvercurrentCtSecondaryInput"' in SOURCE
    manual = _function("wwOvercurrentRequestManualAnalysis")
    assert 'if (m.inputBasis === "primary" && s.ctPrimary !== null && s.ctSecondary !== null) {' in manual
    assert "recording_basis: m.inputBasis," in manual
    loading = _function("wwOvercurrentRequestManualLoadingAnalysis")
    assert "if (s.ctPrimary !== null && s.ctSecondary !== null) {" in loading
    assert 'id="wwOvercurrentManualBasisSelect"' in SOURCE


def test_the_recorded_request_carries_no_basis_and_no_ct():
    body = _function("wwOvercurrentRequestAnalysis")
    for forbidden in ("recording_basis", "ct_primary", "ct_secondary", "ctPrimary", "ctSecondary", "recordingBasis", "wwCtVtBasisParams"):
        assert forbidden not in body
    assert "wwOcRecordedInputMarkRequested();" in body
    assert "pickup_current_secondary: String(s.pickupCurrentSecondary)" in body


def test_the_page_never_derives_a_side_or_a_ct_itself():
    code = _code_only(_block())
    for forbidden in ("measured_rms_current", "relay_secondary_current", "recording_basis", "recordingBasis", "ratio >", "ratio <",
                      "ct_primary", "* 1000", "/ 1000"):
        assert forbidden not in code
    assert not re.search(r"effective_side\s*=(?!=)", code), "the page must never assign a side"
    # a correction goes through Recording Details only
    assert "wwNavigateToRdForGroup(target.sourceId, target.groupId)" in code and "Configure in Recording Details" in code


def test_every_lifecycle_event_refreshes_or_clears_the_authority():
    assert "wwOcRecordedInputRefresh(true);" in _function("wwOvercurrentLoadForSelectedContext")
    assert "wwOcRecordedInputRefresh(false);" in _function("wwOvercurrentHandleSettingsChanged")
    assert "wwOcRecordedInputRefresh(false);" in _function("wwOvercurrentSetInputSource")
    empty = _function("wwOvercurrentShowEmptyState")
    assert "wwOcRecordedInputReset();" in empty and "wwOcRecordedInputRender();" in empty
    reset = _function("wwOvercurrentResetState")
    for needle in ("wwOcRecordedInputReset();", "settings.ctPrimary = null;", "settings.ctSecondary = null;"):
        assert needle in reset
    assert "BasisSelect" not in reset and "recordingBasis" not in reset
    assert 'getElementById("wwOvercurrentCtVtAuthority").addEventListener("click", (event) => wwOcRecordedInputHandleClick(event));' in SOURCE


def test_a_blocked_result_still_feeds_related_waveforms_and_is_never_plotted():
    roles = _function("wwOvercurrentComputeActiveRelatedWaveformRoles")
    assert 'result.status !== "computed"' not in roles and "!result.channel_ref" in roles
    assert "wwOcRecordedInputBlocksResult() ? null : wwOvercurrentState.latestResult" in _function("wwOvercurrentActiveResult")
    render = _function("wwOvercurrentRenderResult")
    assert "const configurationBlocked = wwOcRecordedInputBlocksResult();" in render
    assert "wwOvercurrentPushRelatedWaveformRoles();" in render and "wwOcRecordedInputMessage()" in render


def test_the_shared_ct_vt_block_serves_impedance_and_distance_only():
    block = SOURCE[SOURCE.index("// ---- D5A: authoritative CT/VT for the RECORDED Impedance Locus and"):SOURCE.index("function wwImpedanceFetchAnalysis(")]
    code = _code_only(block)
    assert "wwOvercurrent" not in code and '"overcurrent"' not in code
    assert "strictSides" not in block and "strict" not in code
    assert 'wwCtVtPanel("overcurrent")' not in SOURCE and 'wwCtVtRefresh("overcurrent"' not in SOURCE


# --------------------------------------------------------------------------- Node harness over the real block


def _node(script: str, payload: dict):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    prelude = """
const WW_ANALYSIS_INPUT_SOURCE_RECORDING = "recording", WW_ANALYSIS_INPUT_SOURCE_MANUAL = "manual";
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
let workspaceId = "w";
function currentWorkspaceId() { return workspaceId; }
function apiBaseUrl() { return ""; }
const navigations = [];
const groupReads = [];
const ww = { measurementGroups: new Map(Object.entries(input.cachedGroups || {})) };
async function wwFetchMeasurementGroupsForSource(sourceId) { groupReads.push(sourceId); ww.measurementGroups.set(sourceId, []); }
function wwNavigateToRdForGroup(sourceId, groupId) { navigations.push([sourceId, groupId, groupReads.length]); }
const fetched = [];
const pending = [];
function wwPhasorFetchJson(url) { fetched.push(url); return new Promise((resolve, reject) => pending.push({ url, resolve, reject })); }
const hosts = {};
const document = { getElementById: (id) => (hosts[id] = hosts[id] || { hidden: true, innerHTML: "" }) };
const reruns = [];
function wwOvercurrentHandleSettingsChanged() { reruns.push("overcurrent"); }
const wwOvercurrentState = {
  selectedContextId: "c", inputSource: input.inputSource || "recording", phase: "A",
  recordedInput: { key: null, status: input.status || "idle", report: input.report || null, error: input.error || "", generation: 0, requestedSignature: null },
};
"""
    done = subprocess.run([node, "-e", prelude + _block() + script], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _plan_of(report, *, status="ready", error=""):
    return _node(
        """
const plan = wwOcRecordedInputPlan(wwOcRecordedInputState());
process.stdout.write(JSON.stringify({ plan, blocks: wwOcRecordedInputBlocksResult(), message: wwOcRecordedInputMessage() }));
""",
        {"report": report, "status": status, "error": error},
    )


def _html(report, *, status="ready", source="recording"):
    return _node(
        """
wwOcRecordedInputRender();
process.stdout.write(JSON.stringify({ html: hosts.wwOvercurrentCtVtAuthority.innerHTML, hidden: hosts.wwOvercurrentCtVtAuthority.hidden }));
""",
        {"report": report, "status": status, "inputSource": source},
    )


# --------------------------------------------------------------------------- what may be shown, and when a result is withheld


def test_a_ready_primary_recording_with_a_ct_blocks_nothing():
    out = _plan_of(_report())
    assert out["plan"]["ready"] is True and out["plan"]["blockers"] == [] and out["blocks"] is False and out["message"] is None
    assert out["plan"]["target"] == {"sourceId": "s1", "groupId": "g2"}


@pytest.mark.parametrize("code,message", [
    ("measurement_side_unresolved", "The measurement side of 'ZBAY_IA' is not defined. Set it in Recording Details."),
    ("measurement_side_inferred", "The measurement side of 'ZBAY_IA' is only inferred from other channels."),
    ("measurement_side_conflict", "The channels of the Current Measurement Group 'KPDN1 CURRENT' declare different measurement sides."),
    ("invalid_ct_values", "CT is not configured for the Current Measurement Group 'KPDN1 CURRENT'."),
    ("calculated_channel_side_unavailable", "The measurement side of a calculated current channel is not resolved yet."),
])
def test_each_backend_blocker_withholds_the_result_with_its_own_message_and_a_link_to_the_group(code, message):
    out = _plan_of(_blocked(code, message))
    assert [(b["code"], b["text"]) for b in out["plan"]["blockers"]] == [(code, message)]
    assert out["blocks"] is True and out["message"] == message and out["plan"]["ready"] is False
    assert out["plan"]["target"] == {"sourceId": "s1", "groupId": "g2"}


def test_a_channel_that_never_resolved_has_nothing_to_configure():
    out = _plan_of(_blocked("missing_role", "No current channel.", channel_ref=None, measurement_group_id=None,
                            measurement_group_name=None, measurement_side=None, ct=None))
    assert out["plan"]["target"] is None and out["blocks"] is True


def test_nothing_is_shown_while_the_read_is_in_flight_or_when_it_failed_and_never_when_idle():
    loading = _plan_of(None, status="loading")
    assert [b["code"] for b in loading["plan"]["blockers"]] == ["CONTEXT_LOADING"] and loading["blocks"] is True
    assert "Checking the measurement side and CT in Recording Details" in loading["message"]
    failed = _plan_of(None, status="error", error="HTTP 500")
    assert [b["code"] for b in failed["plan"]["blockers"]] == ["CONTEXT_UNAVAILABLE"] and "HTTP 500" in failed["message"]
    idle = _plan_of(None, status="idle")
    assert idle["plan"]["blockers"] == [] and idle["blocks"] is False


@pytest.mark.parametrize("authority,diagnostic", [
    ("engineer_group_override", "GROUP_OVERRIDE_OVERRIDES_DECLARATION"),
    ("engineer_recording_correction", "ENGINEER_CORRECTION_OVERRIDES_DECLARATION"),
])
def test_an_engineer_setting_that_contradicts_the_declaration_is_disclosed_and_never_blocks(authority, diagnostic):
    side = _side("secondary", authority, "primary", diagnostics=[{"code": diagnostic, "severity": "warning", "message": "x", "detail": {}}])
    out = _plan_of(_report(measurement_side=side, conversion="none"))
    assert out["blocks"] is False and out["plan"]["ready"] is True
    assert [n["code"] for n in out["plan"]["notes"]] == ["SIDE_OVERRIDES_DECLARATION"]
    assert "declares primary" in out["plan"]["notes"][0]["text"]


# --------------------------------------------------------------------------- reads: keys, stale answers, reset


def test_the_read_asks_for_the_authority_of_the_selected_phase_context_and_workspace():
    out = _node(
        """
(async () => {
  wwOvercurrentState.phase = "B";
  wwOcRecordedInputRefresh(true);
  process.stdout.write(JSON.stringify({ url: fetched[0], status: wwOcRecordedInputState().status }));
})();
""", {})
    assert out == {"url": "/api/v1/workspaces/w/engineering-contexts/c/overcurrent-recorded-input?phase=B", "status": "loading"}


def test_a_change_to_the_workspace_context_or_phase_is_a_different_read_and_an_unchanged_key_is_not_re_read():
    out = _node(
        """
(async () => {
  const keys = [];
  wwOcRecordedInputRefresh(true);            keys.push(wwOcRecordedInputState().key);
  wwOcRecordedInputRefresh(false);                                           // same key, still loading: no new read
  const same = fetched.length;
  workspaceId = "other";  wwOcRecordedInputRefresh(false);  keys.push(wwOcRecordedInputState().key);
  wwOvercurrentState.selectedContextId = "d";  wwOcRecordedInputRefresh(false);  keys.push(wwOcRecordedInputState().key);
  wwOvercurrentState.phase = "C";  wwOcRecordedInputRefresh(false);  keys.push(wwOcRecordedInputState().key);
  process.stdout.write(JSON.stringify({ keys, same, reads: fetched.length }));
})();
""", {})
    assert len(set(out["keys"])) == 4 and out["same"] == 1 and out["reads"] == 4


def test_an_older_read_can_never_overwrite_a_newer_selection():
    out = _node(
        """
(async () => {
  wwOvercurrentState.phase = "B";  const first = wwOcRecordedInputRefresh(true);
  wwOvercurrentState.phase = "C";  const second = wwOcRecordedInputRefresh(true);
  pending[1].resolve(input.newer);  await second;
  pending[0].resolve(input.older);  await first;
  const st = wwOcRecordedInputState();
  process.stdout.write(JSON.stringify({ group: st.report.measurement_group_id, key: st.key, reads: fetched.length }));
})();
""", {"newer": _report(measurement_group_id="newer"), "older": _report(measurement_group_id="older")})
    assert out["group"] == "newer" and out["reads"] == 2 and out["key"].endswith("|C")


def test_an_answer_for_another_workspace_is_discarded():
    out = _node(
        """
(async () => {
  const read = wwOcRecordedInputRefresh(true);
  workspaceId = "elsewhere";
  pending[0].resolve(input.report);  await read;
  process.stdout.write(JSON.stringify({ status: wwOcRecordedInputState().status, report: wwOcRecordedInputState().report }));
})();
""", {"report": _report()})
    assert out == {"status": "loading", "report": None}


def test_a_reset_discards_a_read_still_in_flight_and_empties_the_authority():
    out = _node(
        """
(async () => {
  const read = wwOcRecordedInputRefresh(true);
  wwOcRecordedInputReset();
  pending[0].resolve(input.report);  await read;
  wwOcRecordedInputRender();
  const st = wwOcRecordedInputState();
  process.stdout.write(JSON.stringify({ status: st.status, report: st.report, hidden: hosts.wwOvercurrentCtVtAuthority.hidden, key: st.key }));
})();
""", {"report": _report()})
    assert out == {"status": "idle", "report": None, "hidden": True, "key": None}


def test_no_context_is_an_idle_authority_and_a_failed_read_is_reported_not_swallowed():
    out = _node(
        """
(async () => {
  wwOvercurrentState.selectedContextId = null;
  await wwOcRecordedInputRefresh(true);
  const idle = wwOcRecordedInputState().status;
  wwOvercurrentState.selectedContextId = "c";
  const read = wwOcRecordedInputRefresh(true);
  pending[0].reject(new Error("HTTP 500"));  await read;
  const st = wwOcRecordedInputState();
  process.stdout.write(JSON.stringify({ idle, status: st.status, error: st.error, blocks: wwOcRecordedInputBlocksResult() }));
})();
""", {})
    assert out == {"idle": "idle", "status": "error", "error": "HTTP 500", "blocks": True}


def test_the_analysis_is_requested_again_only_when_the_answer_changes_what_the_backend_computes_from():
    out = _node(
        """
(async () => {
  const read = wwOcRecordedInputRefresh(true);
  wwOcRecordedInputMarkRequested();                       // an analysis was requested while the read was in flight
  pending[0].resolve(input.report);  await read;
  const afterFirst = reruns.length;                        // the answer arrived: the analysis must be requested again
  wwOcRecordedInputMarkRequested();                        // ... and was, under this answer
  const again = wwOcRecordedInputRefresh(true);
  pending[1].resolve(input.report);  await again;          // the same answer a second time
  const afterSame = reruns.length;
  wwOcRecordedInputMarkRequested();
  const changed = wwOcRecordedInputRefresh(true);
  pending[2].resolve(input.changed);  await changed;       // Recording Details now says Secondary
  process.stdout.write(JSON.stringify({ afterFirst, afterSame, afterChange: reruns.length }));
})();
""", {"report": _report(), "changed": _report(measurement_side=_side("secondary", "engineer_group_override"), conversion="none")})
    assert out == {"afterFirst": 1, "afterSame": 1, "afterChange": 2}


def test_the_signature_follows_the_side_its_authority_the_group_and_the_ct():
    base = _report()
    variants = [
        _report(measurement_side=_side("secondary")), _report(measurement_side=_side("primary", "engineer_group_override")),
        _report(measurement_group_id="g9"), _report(ct={**base["ct"], "primary": 600.0}),
        _blocked("measurement_side_unresolved", "x"),
    ]
    out = _node(
        """
const sigs = [input.report].concat(input.variants).map((r) => { wwOcRecordedInputState().status = "ready"; wwOcRecordedInputState().report = r; return wwOcRecordedInputSignature(); });
wwOcRecordedInputState().status = "loading";
process.stdout.write(JSON.stringify({ sigs, loading: wwOcRecordedInputSignature() }));
""", {"report": base, "variants": variants})
    assert len(set(out["sigs"])) == len(out["sigs"]) and out["loading"] == "state:loading"


# --------------------------------------------------------------------------- rendering


def test_the_block_shows_the_side_with_its_provenance_the_ct_with_its_group_and_a_configure_link_read_only():
    out = _html(_report())
    html = out["html"]
    assert out["hidden"] is False and "<input" not in html and "<select" not in html and "<textarea" not in html
    assert "Recorded current — from Recording Details" in html
    side = re.search(r'data-oc-value="side">(.*?)</span></span>|data-oc-value="side">(.*?)</span>', html, re.S).group(0)
    assert "Primary" in side and "declared by the recording" in side
    assert 'data-oc-value="ct"' in html and "1200 A / 1 A" in html and "Manual, KPDN1 CURRENT" in html
    assert 'data-oc-configure="1"' in html and "Configure in Recording Details" in html
    assert "Recording current basis" not in html


@pytest.mark.parametrize("authority,expected", [
    ("recording_channel_declared", "declared by the recording"),
    ("engineer_recording_correction", "set by engineer for the recording"),
    ("engineer_group_override", "set by engineer for KPDN1 CURRENT"),
    ("recording_default", "inferred from the recording"),
])
def test_the_provenance_of_the_side_is_stated(authority, expected):
    html = _html(_report(measurement_side=_side("primary", authority)))["html"]
    assert expected in html


def test_a_secondary_recording_needs_no_ct_and_says_so():
    configured = _html(_report(measurement_side=_side("secondary"), conversion="none"))["html"]
    assert "Secondary" in configured and "1200 A / 1 A" in configured and "not applied to a Secondary current" in configured
    missing = _report(measurement_side=_side("secondary"), conversion="none",
                      ct={"status": "not_configured", "consumable": False, "primary": None, "secondary": None, "ratio": None,
                          "authority": "not_configured", "reason": "x", "group_ids": ["g2"]})
    html = _html(missing)["html"]
    assert "not needed for a Secondary current" in html and "ww-ctvt-missing" not in html


def test_a_primary_recording_without_a_usable_ct_flags_it_and_explains_how_to_fix_it():
    ct = {"status": "not_configured", "consumable": False, "primary": None, "secondary": None, "ratio": None,
          "authority": "not_configured", "reason": "x", "group_ids": ["g2"]}
    html = _html(_blocked("invalid_ct_values", "CT is not configured for the Current Measurement Group 'KPDN1 CURRENT'.", ct=ct))["html"]
    assert 'data-oc-row="ct"' in html and "ww-ctvt-missing" in html and "not configured" in html
    assert 'data-oc-code="invalid_ct_values"' in html and "CT is not configured for the Current Measurement Group" in html
    assert "Configure in Recording Details" in html


def test_an_undefined_side_is_shown_as_such_with_no_ct_row_and_no_invented_value():
    html = _html(_blocked("measurement_side_unresolved", "The measurement side of 'ZBAY_IA' is not defined.",
                          measurement_side=_side("unknown", "unresolved", "unknown"), ct=None))["html"]
    assert 'data-oc-value="side"' in html and "not defined" in html and "ww-ctvt-missing" in html
    assert 'data-oc-row="ct"' not in html and "Primary" not in html and "Secondary" not in html
    assert 'data-oc-code="measurement_side_unresolved"' in html


def test_an_inferred_side_is_labelled_inferred_and_blocks():
    html = _html(_blocked("measurement_side_inferred", "Only inferred.", measurement_side=_side("primary", "recording_default", "unknown", inferred=True)))["html"]
    assert "Primary" in html and "inferred from the recording" in html and 'data-oc-code="measurement_side_inferred"' in html


def test_the_block_is_hidden_in_manual_mode_and_while_idle_and_shows_checking_while_loading():
    assert _html(_report(), source="manual")["hidden"] is True
    assert _html(None, status="idle")["hidden"] is True
    loading = _html(None, status="loading")
    assert loading["hidden"] is False and "ww-ctvt-loading" in loading["html"] and 'data-oc-configure' not in loading["html"]


def test_the_block_never_offers_a_link_for_a_channel_that_did_not_resolve():
    html = _html(_blocked("missing_role", "No current channel.", channel_ref=None, measurement_group_id=None,
                          measurement_group_name=None, measurement_side=None, ct=None))["html"]
    assert "data-oc-configure" not in html and 'data-oc-code="missing_role"' in html


def test_text_from_the_backend_is_escaped():
    html = _html(_blocked("measurement_side_unresolved", "<img src=x onerror=alert(1)>"))["html"]
    assert "<img" not in html and "&lt;img" in html


def test_the_configure_button_opens_the_group_that_owns_the_channel_after_loading_the_recording_groups():
    click = """
const event = { target: { closest: (sel) => (sel === "[data-oc-configure]" ? {} : null) } };
(async () => {
  await wwOcRecordedInputHandleClick(event);
  process.stdout.write(JSON.stringify({ navigations, groupReads }));
})();
"""
    # Recording Details keeps a pre-selected group only when that recording's groups are cached: they are read first.
    uncached = _node(click, {"report": _report(), "status": "ready"})
    assert uncached["groupReads"] == ["s1"] and uncached["navigations"] == [["s1", "g2", 1]]
    cached = _node(click, {"report": _report(), "status": "ready", "cachedGroups": {"s1": []}})
    assert cached["groupReads"] == [] and cached["navigations"] == [["s1", "g2", 0]]


def test_a_channel_in_no_group_opens_the_recording_and_other_clicks_do_nothing():
    click = """
const event = { target: { closest: (sel) => (sel === "[data-oc-configure]" ? {} : null) } };
(async () => {
  await wwOcRecordedInputHandleClick(event);
  process.stdout.write(JSON.stringify({ navigations, groupReads }));
})();
"""
    no_group = _node(click, {"report": _report(measurement_group_id=None, measurement_group_name=None), "status": "ready"})
    assert no_group["navigations"] == [["s1", None, 0]] and no_group["groupReads"] == []
    other = """
(async () => {
  await wwOcRecordedInputHandleClick({ target: { closest: () => null } });
  process.stdout.write(JSON.stringify({ navigations, groupReads }));
})();
"""
    assert _node(other, {"report": _report(), "status": "ready"}) == {"navigations": [], "groupReads": []}


# --------------------------------------------------------------------------- Impedance / Distance are unaffected


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_impedance_and_distance_still_treat_a_contradiction_as_a_warning_and_keep_their_params(kind):
    voltage = _quantity(side="secondary", declared_basis="secondary")
    current = _ct_q(side="secondary", declared_basis="secondary")
    out = _plan(_dist_report(voltage, current), "primary", "primary", kind=kind)
    assert out["plan"]["blockers"] == []
    assert [w["code"] for w in out["plan"]["warnings"]] == ["RECORDING_BASIS_CONTRADICTS_VOLTAGE", "RECORDING_BASIS_CONTRADICTS_CURRENT"]
    needed = _plan(_dist_report(_quantity(), _ct_q()), "primary", "secondary", kind=kind)
    assert needed["params"] == {"recording_basis": "primary", "impedance_basis": "secondary", "vt_primary": "132000",
                                "vt_secondary": "110", "ct_primary": "1200", "ct_secondary": "1"}
    assert needed["plan"]["blockers"] == []
