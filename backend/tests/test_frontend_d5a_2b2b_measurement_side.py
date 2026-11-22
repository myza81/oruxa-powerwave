"""D5A-2B2B / D5A-UI-002 frontend: measurement side in Recording Details.

Level 1 (the recording) is rendered in Recording Information; Level 2 (the selected Measurement Group of that recording,
voltage OR current, all its phases) in Group Details.

The REAL helper block of frontend/index.html is run with Node (no re-implementation) against a fake network: what is
rendered, which requests a selection sends and in what order, and that a stale or foreign response can never replace a
newer view. The page keeps no side model of its own; everything it shows is the backend's.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
BLOCK_START, BLOCK_END = "// D5A-2B2B-BLOCK-START", "// D5A-2B2B-BLOCK-END"


def _block() -> str:
    start = SOURCE.index(BLOCK_START)
    return SOURCE[start:SOURCE.index(BLOCK_END, start)]


def _code_only(text: str) -> str:
    """The block without whole-line and trailing `//` comments (a comment may legitimately say "reset")."""
    lines = (line for line in text.splitlines() if not line.strip().startswith("//"))
    return "\n".join(re.sub(r"\s//\s.*$", "", line) for line in lines)


PRELUDE = r"""
const payload = JSON.parse(require("fs").readFileSync(0, "utf8"));
const log = [];
const pending = [];
let workspaceId = "ws-1";
function currentWorkspaceId() { return workspaceId; }
function apiBaseUrl() { return "http://api"; }
function escapeHtml(v) {
  return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
const GROUP = { id: "g1", source_id: "s1", kind: "voltage", display_name: "KPDN1 VOLTAGE" };
const GROUP_I = { id: "g2", source_id: "s1", kind: "current", display_name: "KPDN1 CURRENT" };
const ww = { measurementGroups: new Map([["s1", [GROUP, GROUP_I]]]) };
const wwRdState = { selectedSourceId: "s1" };
const rendered = { recording: null, group: null };
const sectionEl = { set outerHTML(v) { rendered.recording = v; } };
const groupEl = { set outerHTML(v) { rendered.group = v; }, getAttribute() { return payload.shownGroup || "g1"; }, classList: { contains() { return true; } } };
const document = {
  handlers: {},
  getElementById(id) { return id === "wwRdSideSection" ? sectionEl : id === "wwRdSideGroupSection" ? groupEl : null; },
  querySelector() { return null; },
  addEventListener(type, fn) { this.handlers[type] = fn; },
};
function fetch(url, init) {
  return new Promise(function(resolve) {
    const method = (init && init.method) || "GET";
    const entry = { method, url: url.replace("http://api/api/v1/workspaces/", ""), body: init && init.body, resolve };
    log.push(method + " " + entry.url + (entry.body ? " " + entry.body : ""));
    pending.push(entry);
  });
}
function settle(entry, body, status) {
  status = status || 200;
  entry.resolve({ ok: status < 400, status, json: async function() { return body; } });
}
const flush = async function() { for (let i = 0; i < 12; i++) await new Promise(function(r) { setImmediate(r); }); };
function ready(data) {
  wwRdSide.workspaceId = "ws-1"; wwRdSide.sourceId = "s1"; wwRdSide.status = "ready"; wwRdSide.data = data;
}
"""


def _node(script: str, payload: dict):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    # Run from a file: the block plus the prelude is longer than the Windows command-line limit.
    with tempfile.TemporaryDirectory() as folder:
        entry = Path(folder) / "harness.js"
        entry.write_text(PRELUDE + _block() + script, encoding="utf-8")
        done = subprocess.run([node, str(entry)], input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# --------------------------------------------------------------------------- payload builders


def _derived(status="consistent", side="primary", p=6, s=0, undeclared=0, v=None, i=None):
    return {"status": status, "side": side, "voltage_side": v or side, "current_side": i or side,
            "primary_channels": p, "secondary_channels": s, "undeclared_channels": undeclared, "evidence_channels": p + s + undeclared}


def _recording(source_id="s1", *, effective="primary", authority="recording_declared", derived=None, correction=None,
               overridden=()):
    return {"source_id": source_id, "recording_derived": derived or _derived(side=effective or "primary"),
            "engineer_correction": correction, "effective_side": effective, "authority": authority, "group_ids": [],
            "overridden_declarations": list(overridden), "diagnostics": [], "channels": None}


def _group(gid="g1", kind="voltage", name=None, *, source="s1", effective="primary", status="resolved", override=None,
           inferred=(), overridden=(), diagnostics=()):
    return {"measurement_group_id": gid, "source_id": source, "kind": kind,
            "display_name": name or ("KPDN1 VOLTAGE" if kind == "voltage" else "KPDN1 CURRENT"),
            "inherited_side": "primary", "recording_side": "primary", "override": override, "status": status,
            "effective_side": effective, "strict_usable": not inferred, "inferred_channels": list(inferred),
            "authority": "recording_channel_declared", "overridden_declarations": list(overridden),
            "diagnostics": list(diagnostics), "channels": None}


def _overview(recording, groups=()):
    return {"workspace_id": "ws-1", "recordings": [recording], "groups": list(groups)}


def _render(data, *, optimistic=None):
    """The Level 1 section (Recording Information)."""
    script = """
    ready(payload.data);
    if (payload.optimistic) Object.assign(wwRdSide.optimistic, payload.optimistic);
    console.log(JSON.stringify({ html: wwRdSideRenderHtml("s1") }));
    """
    return _node(script, {"data": data, "optimistic": optimistic})["html"]


def _render_group(data, *, kind="voltage", optimistic=None):
    """The Level 2 section (Group Details of the voltage group g1, or the current group g2)."""
    script = """
    ready(payload.data);
    if (payload.optimistic) Object.assign(wwRdSide.optimistic, payload.optimistic);
    console.log(JSON.stringify({ html: wwRdSideGroupRenderHtml(payload.kind === "current" ? GROUP_I : GROUP) }));
    """
    return _node(script, {"data": data, "optimistic": optimistic, "kind": kind})["html"]


def _active(html, row):
    """The Primary/Secondary label(s) shown active inside one row (`recording` or a group id)."""
    marker = 'data-ww-side-row="recording"' if row == "recording" else f'data-ww-side-row="group" data-ww-side-group="{row}"'
    chunk = html[html.index(marker):]
    chunk = chunk[:chunk.index('</span>', chunk.index('radiogroup'))]   # the segmented control closes first
    return re.findall(r'ww-rd-side-btn--active"[^>]*>(\w+)</button>', chunk)


def _buttons(html):
    return re.findall(r"<button[^>]*>([^<]*)</button>", html)


# --------------------------------------------------------------------------- static guarantees


def test_level1_lives_in_recording_info_and_level2_in_group_details():
    code = _code_only(_block())
    assert code.count('wwRdSideSegmentHtml("recording"') == 1 and code.count('wwRdSideSegmentHtml("group"') == 1
    data = _overview(_recording(), [_group("g1")])
    html1 = _render(data)
    assert 'data-ww-side-row="recording"' in html1 and 'data-ww-side-row="group"' not in html1      # no group control in Recording Info
    html2 = _render_group(data)
    assert 'data-ww-side-row="group"' in html2 and 'data-ww-side-row="recording"' not in html2      # no recording row in Group Details
    assert "return headerHtml + wwRdSideGroupSectionHtml(g)" in SOURCE and "html += wwRdSideSectionHtml(s);" in SOURCE


def test_never_per_phase_no_reset_and_no_confirm_bay_in_the_card():
    code = _code_only(_block())
    for forbidden in ("R/Y/B", "side-phase", 'SegmentHtml("phase"', 'SegmentHtml("voltage"', 'SegmentHtml("current"', "reset", "Reset", "Revert",
                      "Confirm", "review", "engineering-contexts", "data-ww-side-bay", "bay_membership"):
        assert forbidden not in code, forbidden


def test_no_second_authority_model_in_the_page():
    code = _code_only(_block())
    for forbidden in ("measurement_side", "ps_flag", "channel_name.", "vt_ratio", "ct_ratio", "localStorage"):
        assert forbidden not in code
    assert {"/measurement-side", "/sources/", "/measurement-groups/"} <= set(re.findall(r'"(/(?:sources|measurement-groups)/|/measurement-side)"', code))


def test_hooks_invalidate_the_view_on_every_lifecycle_boundary():
    assert "wwRdSideInvalidate(); // D5A-2B2B: the source set changed" in SOURCE
    assert "wwRdSideInvalidate(); // D5A-2B2B: bays/recordings may have changed on another page; always re-read" in SOURCE
    assert "wwRdSideInvalidate(); // D5A-2B2B: a different recording has its own measurement-side state" in SOURCE


def test_notation_uses_words_not_electrical_symbols():
    assert not re.search(r"\bV_[A-Z0-9]|\bI_[A-Z0-9]", _code_only(_block()))


# --------------------------------------------------------------------------- Level 1 rendering


def test_recording_from_evidence_shows_the_declared_side_without_a_status_line():
    # UI-REC-001: the normal state is the heading, the one-line description and the pill control, nothing else.
    html = _render(_overview(_recording(), [_group("g1")]))
    assert _active(html, "recording") == ["Primary"]
    assert html.count('role="radiogroup"') == 1
    assert "From recording" not in html and "Detected from" not in html and "Applies to the recording" not in html
    assert "Set by engineer" not in html and 'data-ww-side-notice="recording-override"' not in html
    assert "ww-rd-provenance" not in html
    assert re.search(r">Measurement Side</div>", html)
    assert "Measurement side values for voltage and current." in html
    assert 'class="ww-rd-side-row-label"' not in html               # no redundant "Recording" label beside the selector
    assert "ww-rd-side-group--pill" in html


def test_exceptional_recording_states_keep_a_compact_message():
    inferred = _render(_overview(_recording(derived=_derived("consistent", "primary", 4, 0, 2))))
    assert "ww-rd-provenance--suggested" in inferred and "Select it to confirm" in inferred
    none = _render(_overview(_recording(effective=None, derived=_derived("none", None, 0, 0, 6))))
    assert "ww-rd-provenance--unresolved" in none and "does not declare a measurement side" in none


def test_engineer_correction_discloses_the_contradicted_declarations():
    overridden = [{"source_id": "s1", "channel_name": f"ALPHA1_{n}", "declared_side": "primary", "effective_side": "secondary"}
                  for n in ("VA", "VB", "VC")]
    rec = _recording(effective="secondary", authority="engineer_recording_correction",
                     correction={"side": "secondary", "note": "n", "set_at": "2026-11-22T00:00:00Z"}, overridden=overridden)
    html = _render(_overview(rec))
    assert _active(html, "recording") == ["Secondary"] and "Set by engineer" in html
    notice = re.search(r'data-ww-side-notice="recording-override"[^>]*>([^<]*)<', html).group(1)
    assert "declares Primary on 3 channels" in notice and "original declarations are kept" in notice
    assert "ALPHA1_VA, ALPHA1_VB, ALPHA1_VC" in html


@pytest.mark.parametrize("derived,expected", [
    (_derived("mixed", None, 5, 1), "declare different sides (5 Primary, 1 Secondary)"),
    (_derived("none", None, 0, 0, 6), "does not declare a measurement side"),
    (_derived("voltage_current_differ", None, 3, 3, 0, "primary", "secondary"), "Recorded: voltage primary, current secondary"),
])
def test_unresolved_or_split_recordings_show_no_active_side(derived, expected):
    html = _render(_overview(_recording(effective=None, authority="unresolved", derived=derived)))
    assert _active(html, "recording") == [] and expected in html


def test_inferred_recording_side_asks_for_confirmation():
    html = _render(_overview(_recording(derived=_derived(undeclared=2, p=4))))
    assert _active(html, "recording") == ["Primary"] and "Inferred from the recording's declared channels (2 declare no side)" in html


# --------------------------------------------------------------------------- Level 2 rendering (Group Details)


def test_a_voltage_group_card_is_about_voltage_and_a_current_group_card_about_current():
    data = _overview(_recording(), [_group("g1", "voltage"), _group("g2", "current")])
    volt, cur = _render_group(data), _render_group(data, kind="current")
    assert re.search(r">Measurement Value</div>", volt) and "Primary or secondary values for voltage." in volt
    assert re.search(r">Measurement Value</div>", cur) and "Primary or secondary values for current." in cur
    assert 'data-ww-side-kind="voltage"' in volt and 'data-ww-side-kind="current"' in cur
    assert 'id="wwRdSideGroupSection"' in volt and 'data-ww-side-group="g1"' in volt and 'data-ww-side-group="g2"' in cur
    for html, own, other in ((volt, "g1", "g2"), (cur, "g2", "g1")):
        assert html.count('role="radiogroup"') == 1                       # one control for the group, never per phase
        assert f'data-ww-side-row="group" data-ww-side-group="{own}"' in html and f'data-ww-side-group="{other}"' not in html
        assert "ww-rd-side-group--pill" in html and "Bay" not in html and "bay" not in html


def test_voltage_and_current_groups_of_one_bay_show_their_own_independent_sides():
    data = _overview(_recording(), [
        _group("g1", "voltage", effective="primary"),
        _group("g2", "current", effective="secondary", override={"side": "secondary", "set_at": "x"}),
    ])
    volt, cur = _render_group(data), _render_group(data, kind="current")
    assert _active(volt, "g1") == ["Primary"] and _active(cur, "g2") == ["Secondary"]
    assert "Set manually" in cur and "Set manually" not in volt
    # Optimistic choices are per group: choosing for the voltage group never moves the current group's control.
    chosen = _render_group(data, optimistic={"recording": None, "groups": {"s1|g1": "secondary"}})
    assert _active(chosen, "g1") == ["Secondary"]
    assert _active(_render_group(data, kind="current", optimistic={"recording": None, "groups": {"s1|g1": "secondary"}}), "g2") == ["Secondary"]
    other = _overview(_recording(), [_group("g1", "voltage"), _group("g2", "current", effective="primary")])
    assert _active(_render_group(other, kind="current", optimistic={"recording": None, "groups": {"s1|g1": "secondary"}}), "g2") == ["Primary"]


def test_group_states_follow_override_inferred_unresolved_and_conflict():
    plain = _render_group(_overview(_recording(), [_group("g1")]))
    assert _active(plain, "g1") == ["Primary"] and "ww-rd-provenance" not in plain            # normal: no status line
    manual = _render_group(_overview(_recording(), [_group(
        "g1", effective="secondary", override={"side": "secondary", "set_at": "x"},
        overridden=[{"source_id": "s1", "channel_name": "c", "declared_side": "primary", "effective_side": "secondary"}])]))
    assert _active(manual, "g1") == ["Secondary"] and "Set manually" in manual
    notice = re.search(r'data-ww-side-notice="group-override"[^>]*>([^<]*)<', manual).group(1)
    assert "Differs from the side declared by 1 channel" in notice and "original declarations are kept" in notice
    inferred = _render_group(_overview(_recording(), [_group("g1", inferred=("c1", "c2"))]))
    assert _active(inferred, "g1") == ["Primary"] and "ww-rd-provenance--suggested" in inferred and "Select it to confirm" in inferred
    unresolved = _render_group(_overview(_recording(), [_group("g1", effective=None, status="unresolved")]))
    assert _active(unresolved, "g1") == [] and "ww-rd-provenance--unresolved" in unresolved                 # no false highlight
    conflict = _render_group(_overview(_recording(), [_group("g1", effective=None, status="conflict")]))
    assert _active(conflict, "g1") == [] and "The voltage channels in this group declare different sides" in conflict
    cur_conflict = _render_group(_overview(_recording(), [_group("g2", "current", effective=None, status="conflict")]), kind="current")
    assert "The current channels in this group declare different sides" in cur_conflict


def test_only_this_groups_entry_for_this_recording_is_shown_and_names_are_escaped():
    data = _overview(_recording(), [_group("g1", source="s2"), _group("g1", name='<img src=x onerror=alert(1)>')])
    html = _render_group(data)
    assert "<img" not in html and html.count('role="radiogroup"') == 1
    assert 'aria-label="&lt;img src=x onerror=alert(1)&gt; measurement side"' in html
    none = _render_group(_overview(_recording(), [_group("g1", source="s2")]))
    assert "radiogroup" not in none and "not available" in none


def test_optimistic_choice_shows_immediately_until_the_view_is_re_read():
    data = _overview(_recording(), [_group("g1")])
    assert _active(_render(data, optimistic={"recording": "secondary", "groups": {}}), "recording") == ["Secondary"]
    assert _active(_render_group(data, optimistic={"recording": None, "groups": {"s1|g1": "secondary"}}), "g1") == ["Secondary"]


# --------------------------------------------------------------------------- requests, ordering, stale responses


def test_selection_sends_the_chosen_side_and_nothing_else():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectRecording("secondary");
      await flush();
      const first = log.slice();
      settle(pending[0], {});
      await flush();
      console.log(JSON.stringify({ first, all: log }));
    })();
    """, {"data": _overview(_recording())})
    assert out["first"] == ['PUT ws-1/sources/s1/measurement-side {"side":"secondary"}']
    assert out["all"][-1] == "GET ws-1/measurement-side"                   # re-read once the selection settled


def test_a_group_selection_writes_only_that_group_and_is_scoped_to_the_recording_on_screen():
    data = _overview(_recording(), [_group("g1", "voltage"), _group("g2", "current"), _group("g1", source="s2")])
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectGroup("g1", "secondary");
      await flush(); settle(pending[0], {}); await flush(); settle(pending[1], payload.data); await flush();
      console.log(JSON.stringify({ log }));
    })();
    """, {"data": data})
    assert out["log"] == ['PUT ws-1/sources/s1/measurement-groups/g1/measurement-side {"side":"secondary"}',
                          "GET ws-1/measurement-side"]                    # never the bay, never the sibling current group
    only_other = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectGroup("g1", "secondary");
      await flush();
      console.log(JSON.stringify({ log }));
    })();
    """, {"data": _overview(_recording(), [_group("g1", source="s2")])})
    assert only_other["log"] == []                                           # another recording's group is not addressable


def test_selections_are_sent_in_order_and_the_view_is_re_read_once_after_the_last():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectRecording("secondary");
      wwRdSideSelectRecording("primary");
      await flush();
      const queued = log.slice();                                       // only the first is in flight
      settle(pending[0], {});
      await flush();
      const afterFirst = log.slice();                                   // no re-read yet: a newer choice is queued
      settle(pending[1], {});
      await flush();
      const afterSecond = log.slice();
      settle(pending[2], payload.after);
      await flush();
      console.log(JSON.stringify({ queued, afterFirst, afterSecond, active: rendered.recording, optimistic: wwRdSide.optimistic }));
    })();
    """, {"data": _overview(_recording()), "after": _overview(_recording())})
    put = lambda side: f'PUT ws-1/sources/s1/measurement-side {{"side":"{side}"}}'  # noqa: E731
    assert out["queued"] == [put("secondary")]
    assert out["afterFirst"] == [put("secondary"), put("primary")]
    assert out["afterSecond"] == [put("secondary"), put("primary"), "GET ws-1/measurement-side"]
    assert _active(out["active"], "recording") == ["Primary"] and out["optimistic"] == {"recording": None, "groups": {}}


def test_voltage_and_current_choices_queue_in_order_and_each_reaches_only_its_own_group():
    data = _overview(_recording(), [_group("g1", "voltage"), _group("g2", "current")])
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectGroup("g1", "secondary");
      wwRdSideSelectGroup("g2", "secondary");
      await flush(); settle(pending[0], {}); await flush(); settle(pending[1], {}); await flush();
      console.log(JSON.stringify({ log, optimistic: wwRdSide.optimistic }));
    })();
    """, {"data": data})
    assert out["log"] == [
        'PUT ws-1/sources/s1/measurement-groups/g1/measurement-side {"side":"secondary"}',
        'PUT ws-1/sources/s1/measurement-groups/g2/measurement-side {"side":"secondary"}',
        "GET ws-1/measurement-side"]
    assert out["optimistic"]["groups"] == {"s1|g1": "secondary", "s1|g2": "secondary"}   # until the server view is read


def test_a_slow_older_read_can_never_replace_a_newer_view():
    older, newer = _overview(_recording(effective="secondary", authority="engineer_recording_correction")), _overview(_recording())
    out = _node("""
    (async function() {
      wwRdSide.workspaceId = "ws-1"; wwRdSide.sourceId = "s1";
      wwRdSideLoad("s1"); wwRdSideLoad("s1");
      await flush();
      settle(pending[1], payload.newer);                                // the newer read answers first
      await flush();
      settle(pending[0], payload.older);                                // the older one limps in afterwards
      await flush();
      console.log(JSON.stringify({ effective: wwRdSide.data.recordings[0].effective_side }));
    })();
    """, {"older": older, "newer": newer})
    assert out["effective"] == "primary"


def test_a_response_for_another_workspace_or_recording_is_discarded():
    out = _node("""
    (async function() {
      wwRdSide.workspaceId = "ws-1"; wwRdSide.sourceId = "s1";
      wwRdSideLoad("s1");
      await flush();
      workspaceId = "ws-2";                                             // the workspace was reset meanwhile
      settle(pending[0], payload.data);
      await flush();
      const afterWorkspace = wwRdSide.data;
      workspaceId = "ws-1"; wwRdSide.workspaceId = "ws-1"; wwRdSide.sourceId = "s1";
      wwRdSideLoad("s1");
      await flush();
      wwRdState.selectedSourceId = "s2";                                // the engineer opened another recording
      settle(pending[1], payload.data);
      await flush();
      console.log(JSON.stringify({ afterWorkspace, afterSource: wwRdSide.data }));
    })();
    """, {"data": _overview(_recording())})
    assert out["afterWorkspace"] is None and out["afterSource"] is None


def test_a_group_save_in_flight_when_the_recording_changes_never_refreshes_the_old_view():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectGroup("g1", "secondary");
      await flush();
      wwRdSideInvalidate(); wwRdState.selectedSourceId = "s2";          // switched recording before the answer
      settle(pending[0], {});
      await flush();
      console.log(JSON.stringify({ log, data: wwRdSide.data }));
    })();
    """, {"data": _overview(_recording(), [_group("g1")])})
    assert out["log"] == ['PUT ws-1/sources/s1/measurement-groups/g1/measurement-side {"side":"secondary"}'] and out["data"] is None


def test_a_late_answer_re_renders_only_the_group_that_is_on_screen():
    data = _overview(_recording(), [_group("g1", "voltage"), _group("g2", "current", effective="secondary")])
    out = _node("""
    (async function() {
      ready(payload.data);
      payload.shownGroup = "g2";                                        // the engineer has since selected the current group
      wwRdSideSelectGroup("g1", "secondary");
      await flush(); settle(pending[0], {}); await flush(); settle(pending[1], payload.data); await flush();
      console.log(JSON.stringify({ group: rendered.group }));
    })();
    """, {"data": data, "shownGroup": "g2"})
    assert 'data-ww-side-group="g2"' in out["group"] and 'data-ww-side-group="g1"' not in out["group"]
    assert _active(out["group"], "g2") == ["Secondary"]


def test_reselecting_what_is_shown_sends_nothing_except_to_confirm_an_inferred_side():
    out = _node("""
    (async function() {
      ready(payload.plain);
      wwRdSideSelectRecording("primary");
      wwRdSideSelectGroup("g1", "primary");
      wwRdSideSelectGroup("g-missing", "secondary");                    // unknown group: refused client-side as well
      const none = log.slice();
      ready(payload.inferred);
      wwRdSideSelectRecording("primary");
      wwRdSideSelectGroup("g1", "primary");
      await flush(); settle(pending[0], {}); await flush();             // the group choice is queued behind the recording's
      console.log(JSON.stringify({ none, log }));
    })();
    """, {"plain": _overview(_recording(), [_group("g1")]),
          "inferred": _overview(_recording(derived=_derived(undeclared=2, p=4)), [_group("g1", inferred=("c1", "c2"))])})
    assert out["none"] == []
    assert out["log"] == ['PUT ws-1/sources/s1/measurement-side {"side":"primary"}',
                          'PUT ws-1/sources/s1/measurement-groups/g1/measurement-side {"side":"primary"}']


def test_a_refused_save_is_shown_and_the_view_is_re_read():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectRecording("secondary");
      await flush();
      settle(pending[0], { detail: { code: "x", message: "That group has no voltage or current channel." } }, 409);
      await flush();
      const reread = log[log.length - 1];
      settle(pending[1], payload.data);
      await flush();
      console.log(JSON.stringify({ reread, html: rendered.recording, optimistic: wwRdSide.optimistic }));
    })();
    """, {"data": _overview(_recording())})
    assert out["reread"] == "GET ws-1/measurement-side"
    assert "That group has no voltage or current channel." in out["html"] and out["optimistic"] == {"recording": None, "groups": {}}
    assert _active(out["html"], "recording") == ["Primary"]                # the server's truth, not the rejected choice


def test_every_rendered_button_is_a_side_choice():
    states = [_group("g1"), _group("g2", "current", effective="secondary", override={"side": "secondary", "set_at": "x"})]
    data = _overview(_recording(), states)
    html = _render_group(data) + _render_group(data, kind="current") + _render(data)
    assert set(_buttons(html)) <= {"Primary", "Secondary"}
