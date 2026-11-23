"""D5A-2B2C-1B frontend: recorded Impedance Locus and Distance Protection show the measurement sides and VT/CT that Recording
Details decides, read-only.

The pages have no Recording-basis input and their requests carry only the requested OUTPUT side (`impedance_basis`): the backend
takes the side of the consumed Voltage and Current channels (Level 1 recording, Level 2 Measurement Group) and the VT/CT of the
groups that own them from Recording Details, and enforces it. The pages only read the backend's `protection-recorded-input`
report and show it.

This file supersedes `test_frontend_d5a_ctvt_authority.py`, which exercised the shared `wwCtVt*` plan with a user-chosen Recording
basis and request-carried ratios (a design DEC-216 retires). Every behaviour that file protected and that still applies is kept
here: Manual mode untouched, nothing shown while the read is in flight, stale reads discarded, a reset empties everything,
Related Waveforms stay available for a blocked result, correction only through Recording Details, no frontend derivation of a
side or a ratio, an auto-derived VT shown like any other VT, and the specific actionable message per unusable VT/CT state (now
produced by the backend and asserted in `test_d5a_2b2c_1b_authority_enforcement.py`).

The consumer logic runs the REAL `D5A-2B2C-1B-BLOCK` of frontend/index.html with Node against a fake network (no re-implementation),
and against reports produced by the real backend endpoint.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_d5a2a_protection_instrument_context_api import _contexts
from tests.test_d5a2b1_independent_side_conversion import _ALL, _bay, client  # noqa: F401  (client is the shared fixture)
from tests.test_d5a_ui_002_group_measurement_side import _put

SOURCE = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
BLOCK_START, BLOCK_END = "// D5A-2B2C-1B-BLOCK-START", "// D5A-2B2C-1B-BLOCK-END"
PANELS = (("impedance", "Impedance"), ("distance", "Distance"))


def _block() -> str:
    start = SOURCE.index(BLOCK_START)
    return SOURCE[start:SOURCE.index(BLOCK_END, start)]


def _code_only(text: str) -> str:
    lines = (line for line in text.splitlines() if not line.strip().startswith("//"))
    return "\n".join(re.sub(r"\s//\s.*$", "", line) for line in lines)


def _function(name: str) -> str:
    start = SOURCE.index(f"function {name}(")
    return SOURCE[start:SOURCE.index("\n        }\n", start)]


def _async_function(name: str) -> str:
    start = SOURCE.index(f"async function {name}(")
    return SOURCE[start:SOURCE.index("\n        }\n", start)]


# --------------------------------------------------------------------------- report builders (the backend's shape)


def _channel(name, group="g", unit="V"):
    return {"kind": "source", "source_id": "s1", "channel_name": name, "calculated_channel_id": None}


def _side(effective="secondary", authority="recording_channel_declared", declared="secondary", diagnostics=()):
    return {"effective_side": effective, "authority": authority, "declared_side": declared, "usable": True, "strict_usable": True,
            "inferred": False, "diagnostics": list(diagnostics)}


def _transformer(quantity="voltage", primary=110000.0, secondary=110.0, authority="manual", consumable=True, status="configured"):
    ratio = primary / secondary if consumable else None
    return {"status": status, "consumable": consumable, "primary": primary if consumable else None,
            "secondary": secondary if consumable else None, "ratio": ratio, "authority": authority, "reason": None,
            "group_ids": ["g-" + quantity[:1]], "nominal_ll_kv": None}


def _quantity(quantity, *, side="secondary", authority="recording_channel_declared", declared=None, required=True, transformer=True,
              problem=None, message=None, group="KPDN1 VOLTAGE", target=True, diagnostics=()):
    name = "ZBAY_VA" if quantity == "voltage" else "ZBAY_IA"
    gid = "g-" + quantity[:1]
    known = side in ("primary", "secondary")
    return {
        "quantity": quantity, "channels": [_channel(name)],
        "channel_sides": [_side(side, authority, declared or side, diagnostics)] if known else [],
        "effective_side": side if known else None, "authority": authority if known else None,
        "declared_sides": [declared or side] if side else [], "group_ids": [gid] if group else [], "group_names": [group] if group else [],
        "ratio_required": required,
        "transformer": (_transformer(quantity, *((110000.0, 110.0) if quantity == "voltage" else (1000.0, 5.0)))
                        if transformer is True else transformer),
        "configure_target": {"source_id": "s1", "group_id": gid} if target else None,
        "problem_code": problem, "problem_message": message,
    }


def _report(**over):
    """What `GET .../protection-recorded-input` returns for a Secondary recording converted to Primary."""
    base = {
        "status": "ready", "analysis": "impedance", "engineering_context_id": "c", "phase": "A", "loop": None, "output_side": "primary",
        "voltage": _quantity("voltage"), "current": _quantity("current", group="KPDN1 CURRENT"),
        "voltage_conversion": "secondary_to_primary", "current_conversion": "secondary_to_primary", "reason_code": None, "message": "The recorded input is ready.",
    }
    base.update(over)
    return base


def _blocked(code, message, **over):
    return _report(status="needs_configuration", reason_code=code, message=message, voltage_conversion=None, current_conversion=None, **over)


# --------------------------------------------------------------------------- static guarantees


@pytest.mark.parametrize("kind,name", PANELS)
def test_recorded_mode_has_no_recording_basis_input_and_a_read_only_authority_host(kind, name):
    assert f'id="ww{name}RecordingBasisSelect"' not in SOURCE and f'id="ww{name}RecordingBasisField"' not in SOURCE
    assert "Recording basis (as recorded)" not in SOURCE
    host = re.search(rf'<div class="ww-ctvt-authority[^>]*id="ww{name}CtVtAuthority"[^>]*>', SOURCE).group(0)
    assert "hidden" in host and "<input" not in host and "<select" not in host
    for field in ("VtPrimary", "VtSecondary", "CtPrimary", "CtSecondary"):
        assert f'id="ww{name}{field}Input"' not in SOURCE and f'id="ww{name}{field}Field"' not in SOURCE


@pytest.mark.parametrize("kind,name", PANELS)
def test_the_impedance_output_selector_stays_editable_and_drives_the_next_computation(kind, name):
    select = re.search(rf'<select id="ww{name}OutputBasisSelect"[^>]*>(.*?)</select>', SOURCE, re.S)
    assert select is not None and "disabled" not in select.group(0).split(">")[0]
    assert 'value="primary"' in select.group(1) and 'value="secondary"' in select.group(1)
    listener = re.search(rf'getElementById\("ww{name}OutputBasisSelect"\)\.addEventListener\("change", \(event\) => \{{(.*?)\n        \}}\);', SOURCE, re.S)
    assert listener is not None and f"ww{name}State.settings.outputBasis = event.target.value;" in listener.group(1)
    assert f"ww{name}HandleSettingsChanged();" in listener.group(1)
    # a settings change re-reads the authority (the output side decides whether a VT/CT is needed) and re-requests both results
    handler = _function(f"ww{name}HandleSettingsChanged")
    assert f'wwCtVtRefresh("{kind}", false);' in handler and f"ww{name}RequestExactPlaybackFetch();" in handler
    assert f"ww{name}MaybeFetchLocus();" in handler and f"ww{name}InvalidateLocus();" in handler


@pytest.mark.parametrize("kind,name", PANELS)
def test_manual_mode_keeps_every_input(kind, name):
    for field in ("VtPrimary", "VtSecondary", "CtPrimary", "CtSecondary"):
        assert f'id="ww{name}Manual{field}Input"' in SOURCE
    for field in ("ManualVoltageBasisSelect", "ManualCurrentBasisSelect", "OutputBasisSelect"):
        assert f'id="ww{name}{field}"' in SOURCE


@pytest.mark.parametrize("kind,name", PANELS)
def test_the_panels_keep_only_the_output_side_as_a_recorded_setting(kind, name):
    state = SOURCE[SOURCE.index(f"const ww{name}State = {{"):]
    state = state[:state.index("latestResult:")]
    settings = re.search(r"settings: \{(.*?)\n            \},", state, re.S).group(1)
    assert "outputBasis:" in settings and "recordingBasis" not in settings and "Explicit" not in settings
    assert f'ww{name}State.settings = {{ outputBasis: "secondary" }};' in SOURCE
    assert "recordingBasis" not in SOURCE and "RecordingBasis" not in SOURCE


@pytest.mark.parametrize("kind,name", PANELS)
def test_the_recorded_requests_carry_only_the_output_side(kind, name):
    params = _function(f"ww{name}BasisParams")
    assert f'return wwCtVtBasisParams("{kind}");' in params
    helper = _function("wwCtVtBasisParams")
    assert "return { impedance_basis: panel.state.settings.outputBasis };" in helper
    for fn in (f"ww{name}RequestAnalysis", f"ww{name}MaybeFetchLocus"):
        body = (_async_function(fn))
        assert f"ww{name}BasisParams(s)" in body
        for forbidden in ("recording_basis", "voltage_side", "current_side", "vt_primary", "vt_secondary", "ct_primary", "ct_secondary",
                          "recordingBasis"):
            assert forbidden not in body, (fn, forbidden)
    signature = _function(f"ww{name}LocusSignature")
    assert f'wwCtVtSignature("{kind}")' in signature and "s.outputBasis" in signature


def test_the_page_never_derives_a_side_or_a_ratio_itself():
    code = _code_only(_block())
    # whole-word: the reason codes (`voltage_side_inferred`) are legitimate, the REQUEST parameters (`voltage_side`) are not
    for forbidden in ("recording_basis", "recordingBasis", "voltage_side", "current_side", "vt_primary", "ct_primary", "magnitude"):
        assert not re.search(rf"\b{forbidden}\b", code), forbidden
    for forbidden in ("nominal_voltage", "nameplate", "rated", "* 1000", "ratio >", "ratio <", "ratio *", "/ ctx.secondary"):
        assert forbidden not in code
    assert not re.search(r"effective_side\s*=(?!=)", code), "the page must never assign a side"
    assert "Auto-derived" in code
    for word in ("display-only", "assumed", "provisional"):
        assert word not in code.lower()


def test_correction_goes_through_recording_details_only():
    code = _code_only(_block())
    assert "wwNavigateToRdForGroup(target.source_id, target.group_id)" in code and "Configure in Recording Details" in code
    assert ".value =" not in code and "<input" not in code and "<select" not in code


def test_the_block_is_independent_of_the_overcurrent_block():
    code = _code_only(_block())
    assert "wwOvercurrent" not in code and "wwOc" not in code and "WW_OC_" not in code and '"overcurrent"' not in code


@pytest.mark.parametrize("kind,name", PANELS)
def test_every_lifecycle_event_refreshes_or_clears_the_authority(kind, name):
    assert f'wwCtVtRefresh("{kind}", true);' in _function(f"ww{name}LoadForSelectedContext")
    assert f'wwCtVtRefresh("{kind}", false);' in _function(f"ww{name}HandleSettingsChanged")
    assert f'wwCtVtRefresh("{kind}", false);' in _function(f"ww{name}SetInputSource")
    assert f'wwCtVtReset("{kind}");' in _function(f"ww{name}ResetState")
    assert f'getElementById("ww{name}CtVtAuthority").addEventListener("click", (event) => wwCtVtHandleClick("{kind}", event));' in SOURCE


@pytest.mark.parametrize("kind,name", PANELS)
def test_a_blocked_result_still_feeds_related_waveforms_and_is_never_plotted(kind, name):
    roles = _function(f"ww{name}ComputeActiveRelatedWaveformRoles")
    assert f"const result = ww{name}State.latestResult;" in roles and 'status !== "computed"' not in roles
    assert f'wwCtVtBlocksResult("{kind}") ? null : ww{name}State.latestResult' in _function(f"ww{name}RecordedResult")
    assert f'wwCtVtBlocksResult("{kind}") ? [] : ww{name}State.locusPoints' in _function(f"ww{name}RecordedLocusPoints")
    assert f"ww{name}RecordedResult()" in _function(f"ww{name}CollectRelevantPoints")
    assert f"ww{name}RecordedLocusPoints()" in _function(f"ww{name}CollectRelevantPoints")
    assert f"ww{name}RecordedResult()" in _function(f"ww{name}VisibleLocusCutoffTime")
    plot = _function(f"ww{name}RenderPlot")
    assert f"ww{name}RecordedLocusPoints()" in plot and f"ww{name}RecordedResult()" in plot and f"ww{name}State.locusPoints" not in plot
    render = _function(f"ww{name}RenderResult")
    assert f'const configurationBlocked = wwCtVtBlocksResult("{kind}");' in render and f"ww{name}PushRelatedWaveformRoles();" in render


def test_a_blocked_distance_result_never_shows_a_zone_classification():
    render = _function("wwDistanceRenderResult")
    assert "wwDistanceRenderZoneStateList(result && !sideBlocked ? wwDistanceZoneResultMap(result) : null);" in render
    assert "result.side_conversion.block_code" in render


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
function wwImpedanceHandleSettingsChanged() { reruns.push("impedance"); }
function wwDistanceHandleSettingsChanged() { reruns.push("distance"); }
const mk = (extra) => Object.assign({
  selectedContextId: "c", inputSource: input.inputSource || "recording", settings: { outputBasis: input.outputBasis || "primary" },
  ctVt: { key: null, status: input.status || "idle", report: input.report || null, error: input.error || "", generation: 0, requestedSignature: null },
}, extra);
const wwImpedanceState = mk({ phase: "A" });
const wwDistanceState = mk({ loop: "AB" });
"""
    done = subprocess.run([node, "-e", prelude + _block() + script], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _plan_of(report, *, status="ready", error="", kind="impedance"):
    return _node(
        f"""
const plan = wwCtVtPlanFor("{kind}");
process.stdout.write(JSON.stringify({{ plan, blocks: wwCtVtBlocksResult("{kind}"), message: wwCtVtResultMessage("{kind}", null) }}));
""",
        {"report": report, "status": status, "error": error},
    )


def _html(report, *, status="ready", source="recording", kind="impedance"):
    name = kind.capitalize()
    return _node(
        f"""
wwCtVtRender("{kind}");
process.stdout.write(JSON.stringify({{ html: hosts.ww{name}CtVtAuthority.innerHTML, hidden: hosts.ww{name}CtVtAuthority.hidden }}));
""",
        {"report": report, "status": status, "inputSource": source},
    )


# --------------------------------------------------------------------------- what may be shown, and when a result is withheld


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_a_ready_report_blocks_nothing(kind):
    out = _plan_of(_report(), kind=kind)
    assert out["plan"]["ready"] is True and out["plan"]["blockers"] == [] and out["blocks"] is False and out["message"] is None


@pytest.mark.parametrize("code,message", [
    ("voltage_side_authority_unavailable", "The measurement side of the voltage channel 'ZBAY_VA' is not defined. Set it in Recording Details."),
    ("current_side_inferred", "The measurement side of the current channel 'ZBAY_IA' is only inferred from other channels."),
    ("voltage_group_side_conflict", "The channels of the Voltage Measurement Group 'KPDN1 VOLTAGE' declare different measurement sides."),
    ("current_side_contradicts_recording", "The asserted current side contradicts the current side defined in Recording Details."),
    ("vt_authority_unavailable", "Converting the voltage to the Primary side needs its VT from Recording Details. VT is not configured."),
    ("ct_authority_unavailable", "Converting the current to the Primary side needs its CT from Recording Details. CT is not configured."),
])
def test_each_backend_blocker_withholds_the_result_with_its_own_message(code, message):
    out = _plan_of(_blocked(code, message))
    assert [(b["code"], b["text"]) for b in out["plan"]["blockers"]] == [(code, message)]
    assert out["blocks"] is True and out["message"] == message and out["plan"]["ready"] is False


def test_nothing_is_shown_while_the_read_is_in_flight_or_when_it_failed_and_never_when_idle():
    loading = _plan_of(None, status="loading")
    assert [b["code"] for b in loading["plan"]["blockers"]] == ["CONTEXT_LOADING"] and loading["blocks"] is True
    assert "Checking the measurement sides and CT/VT in Recording Details" in loading["message"]
    failed = _plan_of(None, status="error", error="HTTP 500")
    assert [b["code"] for b in failed["plan"]["blockers"]] == ["CONTEXT_UNAVAILABLE"] and "HTTP 500" in failed["message"]
    idle = _plan_of(None, status="idle")
    assert idle["plan"]["blockers"] == [] and idle["blocks"] is False


@pytest.mark.parametrize("authority,diagnostic", [
    ("engineer_group_override", "GROUP_OVERRIDE_OVERRIDES_DECLARATION"),
    ("engineer_recording_correction", "ENGINEER_CORRECTION_OVERRIDES_DECLARATION"),
])
def test_an_engineer_setting_that_contradicts_the_declaration_is_disclosed_and_never_blocks(authority, diagnostic):
    diag = [{"code": diagnostic, "severity": "warning", "message": "x", "detail": {}}]
    out = _plan_of(_report(voltage=_quantity("voltage", side="primary", authority=authority, declared="secondary", diagnostics=diag)))
    assert out["blocks"] is False and out["plan"]["ready"] is True
    assert [n["code"] for n in out["plan"]["notes"]] == ["SIDE_OVERRIDES_DECLARATION_VOLTAGE"]
    assert "declares the voltage as secondary" in out["plan"]["notes"][0]["text"]


# --------------------------------------------------------------------------- what is shown


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_a_ready_report_shows_both_sides_their_provenance_and_the_transformers_that_convert(kind):
    out = _html(_report(), kind=kind)
    html = out["html"]
    assert out["hidden"] is False and "Recorded input — from Recording Details" in html
    assert 'data-ctvt-row="voltage-side"' in html and 'data-ctvt-row="current-side"' in html
    assert "Secondary" in html and "declared by the recording" in html
    assert "110 kV / 110 V" in html and "1000 A / 5 A" in html and "KPDN1 VOLTAGE" in html and "KPDN1 CURRENT" in html
    assert "Manual" in html and "data-ctvt-configure=\"voltage\"" in html and "data-ctvt-configure=\"current\"" in html
    assert "data-ctvt-code" not in html                                          # nothing to explain when everything is fine


def test_a_quantity_already_on_the_output_side_needs_no_ratio_and_says_so():
    report = _report(voltage=_quantity("voltage", side="primary", required=False),
                     current=_quantity("current", side="secondary", group="KPDN1 CURRENT"))
    html = _html(report)["html"]
    assert 'data-ctvt-row="voltage-ratio"' in html and "not needed" in html and "voltage is already Primary" in html
    assert 'data-ctvt-row="current-ratio"' in html and "1000 A / 5 A" in html


def test_voltage_and_current_sides_are_shown_independently():
    report = _report(voltage=_quantity("voltage", side="secondary", authority="engineer_group_override", group="KPDN1 VOLTAGE"),
                     current=_quantity("current", side="primary", required=False, group="KPDN1 CURRENT"))
    html = _html(report)["html"]
    assert "set by engineer for KPDN1 VOLTAGE" in html and "declared by the recording" in html
    voltage = re.search(r'data-ctvt-value="voltage-side">(.*?)</span></span>', html, re.S).group(1)
    current = re.search(r'data-ctvt-value="current-side">(.*?)</span></span>', html, re.S).group(1)
    assert "Secondary" in voltage and "Primary" in current


def test_an_auto_derived_vt_is_shown_like_any_other_vt():
    transformer = _transformer("voltage", 110000.0, 110.0, authority="auto_nominal")
    html = _html(_report(voltage=_quantity("voltage", transformer=transformer)))["html"]
    assert "110 kV / 110 V" in html and "Auto-derived" in html and "ww-ctvt-missing" not in html


@pytest.mark.parametrize("problem,text", [
    ("voltage_group_side_conflict", "conflicting declarations"),
    ("voltage_mixed_side_within_quantity", "conflicting declarations"),
    ("voltage_side_inferred", "only inferred, not usable"),
    ("voltage_side_authority_unavailable", "not defined"),
])
def test_an_unusable_side_is_named_for_what_it_is_and_links_to_the_group_that_can_resolve_it(problem, text):
    report = _blocked(problem, "msg", voltage=_quantity("voltage", side=None, authority=None, problem=problem, transformer=None))
    html = _html(report)["html"]
    assert text in html and 'data-ctvt-configure="voltage"' in html and f'data-ctvt-code="{problem}"' in html
    assert 'data-ctvt-row="voltage-ratio"' not in html                       # no claim about a ratio while the side is unknown
    assert "ww-ctvt-missing" in html


def test_a_needed_vt_that_is_not_configured_is_shown_as_a_defect():
    report = _blocked("vt_authority_unavailable", "VT is not configured.",
                      voltage=_quantity("voltage", transformer=_transformer(consumable=False, status="not_configured", authority="not_configured")))
    html = _html(report)["html"]
    assert 'data-ctvt-value="voltage-ratio"' in html and "not configured" in html and "ww-ctvt-missing" in html


def test_a_calculated_channel_says_the_support_is_not_available_and_never_suggests_configuring_anything():
    report = _blocked("calculated_channel_side_unavailable", "Measurement-side support for calculated channels is not available yet.",
                      voltage=_quantity("voltage", side=None, authority=None, problem="calculated_channel_side_unavailable",
                                        transformer=None, group=None, target=False))
    out = _html(report)
    html = out["html"]
    assert "not available for a calculated channel" in html and "not defined" not in html
    assert 'data-ctvt-configure="voltage"' not in html                         # no link: nothing there can fix it
    assert 'data-ctvt-row="voltage-ratio"' not in html
    assert 'data-ctvt-code="calculated_channel_side_unavailable"' in html
    odd = _report(status="needs_configuration", reason_code="calculated_channel_side_unavailable", message="x",
                  voltage=_quantity("voltage", side=None, authority=None, problem="calculated_channel_side_unavailable",
                                    transformer=None, target=True))
    assert 'data-ctvt-configure="voltage"' not in _html(odd)["html"]            # keyed on the reason, not only on a target


def test_the_authority_is_hidden_outside_recording_mode_and_when_idle():
    assert _html(_report(), source="manual")["hidden"] is True
    assert _html(None, status="idle")["hidden"] is True


# --------------------------------------------------------------------------- reads: keys, requests, stale answers, reset


@pytest.mark.parametrize("kind,scope", [("impedance", "phase=B"), ("distance", "loop=CA")])
def test_the_read_asks_for_the_authority_of_the_selected_scope_output_side_context_and_workspace(kind, scope):
    name = kind.capitalize()
    key = scope.split("=")[0]
    out = _node(
        f"""
(async () => {{
  ww{name}State.{key} = "{scope.split('=')[1]}";
  wwCtVtRefresh("{kind}", true);
  process.stdout.write(JSON.stringify({{ url: fetched[0], status: wwCtVtStateOf(wwCtVtPanel("{kind}")).status }}));
}})();
""", {"outputBasis": "secondary"})
    analysis = "impedance" if kind == "impedance" else "distance_protection"
    assert out["status"] == "loading"
    assert out["url"].startswith("/api/v1/workspaces/w/engineering-contexts/c/protection-recorded-input?")
    query = dict(p.split("=") for p in out["url"].split("?")[1].split("&"))
    assert query == {"analysis": analysis, "impedance_basis": "secondary", key: scope.split("=")[1]}


@pytest.mark.parametrize("kind", ["impedance", "distance"])
def test_a_change_of_workspace_context_scope_or_output_side_is_a_different_read_and_an_unchanged_key_is_not_re_read(kind):
    name = kind.capitalize()
    scope = "phase" if kind == "impedance" else "loop"
    other = "C" if kind == "impedance" else "CA"
    out = _node(
        f"""
(async () => {{
  const keys = [];
  const st = () => wwCtVtStateOf(wwCtVtPanel("{kind}"));
  wwCtVtRefresh("{kind}", true);   keys.push(st().key);
  wwCtVtRefresh("{kind}", false);                                           // same key, still loading: no new read
  const same = fetched.length;
  workspaceId = "other";  wwCtVtRefresh("{kind}", false);  keys.push(st().key);
  ww{name}State.selectedContextId = "d";  wwCtVtRefresh("{kind}", false);  keys.push(st().key);
  ww{name}State.{scope} = "{other}";  wwCtVtRefresh("{kind}", false);  keys.push(st().key);
  ww{name}State.settings.outputBasis = "secondary";  wwCtVtRefresh("{kind}", false);  keys.push(st().key);
  process.stdout.write(JSON.stringify({{ keys, same, reads: fetched.length }}));
}})();
""", {})
    assert len(set(out["keys"])) == 5 and out["same"] == 1 and out["reads"] == 5


def test_an_older_read_can_never_overwrite_a_newer_selection():
    out = _node(
        """
(async () => {
  wwImpedanceState.phase = "B";  const first = wwCtVtRefresh("impedance", true);
  wwImpedanceState.phase = "C";  const second = wwCtVtRefresh("impedance", true);
  pending[1].resolve(input.newer);  await second;
  pending[0].resolve(input.older);  await first;
  const st = wwCtVtStateOf(wwCtVtPanel("impedance"));
  process.stdout.write(JSON.stringify({ phase: st.report.phase, key: st.key, reads: fetched.length }));
})();
""", {"newer": _report(phase="C"), "older": _report(phase="B")})
    assert out["phase"] == "C" and out["reads"] == 2 and "|C|" in out["key"]


def test_an_answer_for_another_workspace_is_discarded():
    out = _node(
        """
(async () => {
  const read = wwCtVtRefresh("impedance", true);
  workspaceId = "elsewhere";
  pending[0].resolve(input.report);  await read;
  const st = wwCtVtStateOf(wwCtVtPanel("impedance"));
  process.stdout.write(JSON.stringify({ status: st.status, report: st.report }));
})();
""", {"report": _report()})
    assert out == {"status": "loading", "report": None}


def test_a_reset_discards_a_read_still_in_flight_and_empties_the_authority():
    out = _node(
        """
(async () => {
  const read = wwCtVtRefresh("distance", true);
  wwCtVtReset("distance");
  pending[0].resolve(input.report);  await read;
  wwCtVtRender("distance");
  const st = wwCtVtStateOf(wwCtVtPanel("distance"));
  process.stdout.write(JSON.stringify({ status: st.status, report: st.report, hidden: hosts.wwDistanceCtVtAuthority.hidden, key: st.key }));
})();
""", {"report": _report()})
    assert out == {"status": "idle", "report": None, "hidden": True, "key": None}


def test_no_context_is_an_idle_authority_and_a_failed_read_is_reported_not_swallowed():
    out = _node(
        """
(async () => {
  wwImpedanceState.selectedContextId = null;
  await wwCtVtRefresh("impedance", true);
  const idle = wwCtVtStateOf(wwCtVtPanel("impedance")).status;
  wwImpedanceState.selectedContextId = "c";
  const read = wwCtVtRefresh("impedance", true);
  pending[0].reject(new Error("HTTP 500"));  await read;
  const st = wwCtVtStateOf(wwCtVtPanel("impedance"));
  process.stdout.write(JSON.stringify({ idle, status: st.status, error: st.error, blocks: wwCtVtBlocksResult("impedance") }));
})();
""", {})
    assert out == {"idle": "idle", "status": "error", "error": "HTTP 500", "blocks": True}


def test_the_request_params_are_the_output_side_only_and_remember_what_they_were_built_from():
    out = _node(
        """
const st = wwCtVtStateOf(wwCtVtPanel("impedance"));
st.status = "ready"; st.report = input.report;
const params = wwCtVtBasisParams("impedance");
process.stdout.write(JSON.stringify({ params, remembered: st.requestedSignature, now: wwCtVtSignature("impedance") }));
""", {"report": _report(), "outputBasis": "secondary"})
    assert out["params"] == {"impedance_basis": "secondary"} and out["remembered"] == out["now"]


def test_the_analysis_is_requested_again_only_when_the_answer_changes_what_the_backend_computes_from():
    script = """
(async () => {
  const st = wwCtVtStateOf(wwCtVtPanel("impedance"));
  st.status = "ready"; st.report = input.before; wwCtVtBasisParams("impedance");           // a request was built from `before`
  const read = wwCtVtRefresh("impedance", true);
  pending[0].resolve(input.after);  await read;
  process.stdout.write(JSON.stringify({ reruns }));
})();
"""
    same = _node(script, {"before": _report(), "after": _report(message="different wording only")})
    assert same["reruns"] == []                                                         # nothing the calculation depends on changed
    changed_side = _node(script, {"before": _report(), "after": _report(voltage=_quantity("voltage", side="primary", required=False))})
    assert changed_side["reruns"] == ["impedance"]
    changed_ratio = _node(script, {"before": _report(), "after": _report(voltage=_quantity(
        "voltage", transformer=_transformer(primary=132000.0, secondary=110.0)))})
    assert changed_ratio["reruns"] == ["impedance"]
    now_blocked = _node(script, {"before": _report(), "after": _blocked("voltage_group_side_conflict", "x")})
    assert now_blocked["reruns"] == ["impedance"]
    manual = _node(script.replace('const st =', 'wwImpedanceState.inputSource = "manual"; const st ='),
                   {"before": _report(), "after": _blocked("voltage_group_side_conflict", "x")})
    assert manual["reruns"] == []                                                        # Manual mode is never driven by Recording Details


def test_a_configure_click_reads_the_groups_once_then_opens_the_owning_group_and_never_for_a_calculated_channel():
    out = _node(
        """
(async () => {
  const st = wwCtVtStateOf(wwCtVtPanel("impedance"));
  st.status = "ready"; st.report = input.report;
  const click = (q) => wwCtVtHandleClick("impedance", { target: { closest: () => ({ getAttribute: () => q }) } });
  await click("voltage");  await click("voltage");  await click("current");
  process.stdout.write(JSON.stringify({ navigations, groupReads }));
})();
""", {"report": _report()})
    assert out["navigations"] == [["s1", "g-v", 1], ["s1", "g-v", 1], ["s1", "g-c", 1]] and out["groupReads"] == ["s1"]
    calculated = _node(
        """
(async () => {
  const st = wwCtVtStateOf(wwCtVtPanel("distance"));
  st.status = "ready"; st.report = input.report;
  await wwCtVtHandleClick("distance", { target: { closest: () => ({ getAttribute: () => "voltage" }) } });
  process.stdout.write(JSON.stringify({ navigations, groupReads }));
})();
""", {"report": _blocked("calculated_channel_side_unavailable", "x", voltage=_quantity(
        "voltage", side=None, authority=None, problem="calculated_channel_side_unavailable", transformer=None, group=None, target=False))})
    assert calculated == {"navigations": [], "groupReads": []}


# --------------------------------------------------------------------------- against reports of the REAL backend endpoint


def _real_report(client, ws, ctx, analysis, out):
    params = {"analysis": analysis, "impedance_basis": out, **({"phase": "A"} if analysis == "impedance" else {"loop": "AB"})}
    resp = client.get(f"{_contexts(ws)}/{ctx}/protection-recorded-input", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("analysis,kind", [("impedance", "impedance"), ("distance_protection", "distance")])
def test_a_real_secondary_recording_is_shown_with_its_group_names_and_the_ratios_that_convert(client, analysis, kind):
    ws = f"1b-fe-{kind}"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    report = _real_report(client, ws, ctx, analysis, "primary")
    html = _html(report, kind=kind)["html"]
    assert _plan_of(report, kind=kind)["blocks"] is False
    assert "110 kV / 110 V" in html and f"vg-{src}" in html and "declared by the recording" in html
    assert 'data-ctvt-row="current-ratio"' in html and "not needed" in html and "current is already Primary" in html
    out = _node(
        f"""
const st = wwCtVtStateOf(wwCtVtPanel("{kind}"));
st.status = "ready"; st.report = input.report;
const click = wwCtVtHandleClick("{kind}", {{ target: {{ closest: () => ({{ getAttribute: () => "voltage" }}) }} }});
click.then(() => process.stdout.write(JSON.stringify({{ navigations }})));
""", {"report": report})
    assert out["navigations"] == [[src, f"vg-{src}", 1]]                       # the REAL group that owns the consumed channel


def test_a_real_engineer_setting_is_shown_as_the_effective_side_and_disclosed(client):
    ws = "1b-fe-override"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    _put(client, ws, src, f"vg-{src}", "secondary")
    report = _real_report(client, ws, ctx, "impedance", "primary")
    plan = _plan_of(report)
    assert plan["blocks"] is False and [n["code"] for n in plan["plan"]["notes"]] == ["SIDE_OVERRIDES_DECLARATION_VOLTAGE"]
    html = _html(report)["html"]
    assert f"set by engineer for vg-{src}" in html and "110 kV / 110 V" in html


def test_a_real_mixed_group_blocks_names_the_group_and_links_to_it(client):
    ws = "1b-fe-mixed"
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={"VB": "S"})
    report = _real_report(client, ws, ctx, "distance_protection", "primary")
    out = _plan_of(report, kind="distance")
    assert out["blocks"] is True and [b["code"] for b in out["plan"]["blockers"]] == ["voltage_group_side_conflict"]
    assert f"vg-{src}" in out["message"]
    html = _html(report, kind="distance")["html"]
    assert "conflicting declarations" in html and 'data-ctvt-configure="voltage"' in html


def test_a_real_missing_vt_blocks_with_the_specific_message_and_keeps_the_resolved_channels(client):
    ws = "1b-fe-novt"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    client.app.state.voltage_group_config_registry.delete(ws, f"vg-{src}")
    report = _real_report(client, ws, ctx, "impedance", "primary")
    out = _plan_of(report)
    assert out["blocks"] is True and out["plan"]["blockers"][0]["code"] == "vt_authority_unavailable"
    assert "VT is not configured" in out["message"] and "Recording Details" in out["message"]
    assert [c["channel_name"] for c in report["voltage"]["channels"]] == ["ZBAY_VA"]       # identities survive a blocker
