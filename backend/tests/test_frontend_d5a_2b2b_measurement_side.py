"""D5A-2B2B frontend: measurement side in Recording Details.

Level 1 (recording) is rendered in Recording Information; Level 2 (the bay, within the selected recording) in Group Details.

The REAL helper block of frontend/index.html is run with Node (no re-implementation) against a fake network: what is
rendered, which requests a selection sends and in what order, the explicit bay-confirmation review, and that a stale or
foreign response can never replace a newer view. The page keeps no side model of its own; everything it shows is the backend's.
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
const ww = { measurementGroups: new Map([["s1", [GROUP]]]) };
const wwRdState = { selectedSourceId: "s1" };
const rendered = { recording: null, bay: null };
const sectionEl = { set outerHTML(v) { rendered.recording = v; } };
const bayEl = { set outerHTML(v) { rendered.bay = v; }, getAttribute() { return "g1"; } };
const document = {
  handlers: {},
  getElementById(id) { return id === "wwRdSideSection" ? sectionEl : id === "wwRdSideBaySection" ? bayEl : null; },
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
            "engineer_correction": correction, "effective_side": effective, "authority": authority, "bay_ids": [],
            "overridden_declarations": list(overridden), "diagnostics": [], "channels": None}


def _ownership(status="single_bay", bays=(("ec-1", "KPDN1"),)):
    return {"group_id": "g1", "kind": "voltage", "display_name": "KPDN1 VOLTAGE", "status": status,
            "conversion_authority_ambiguous": status == "spans_bays_ambiguous",
            "bays": [{"engineering_context_id": i, "display_name": n} for i, n in bays]}


def _bay(ctx, name, *, source="s1", membership="confirmed", effective="primary", status="resolved", override=None,
         reference_sides="uniform", v="primary", i="primary", inferred=(), overridden=(), diagnostics=(), groups=("g1",),
         ownership=None):
    return {"engineering_context_id": ctx, "source_id": source, "display_name": name,
            "context_status": "confirmed" if membership == "confirmed" else "suggested",
            "bay_membership": membership, "inherited_recording_side": "primary", "override": override, "status": status,
            "effective_side": effective, "voltage_side": v, "current_side": i, "reference_sides": reference_sides,
            "strict_usable": True, "inferred_channels": list(inferred), "authority": "recording_channel_declared",
            "overridden_declarations": list(overridden), "voltage_group_ids": list(groups), "current_group_ids": [],
            "group_ownership": [ownership or _ownership(bays=((ctx, name),))], "diagnostics": list(diagnostics), "channels": None}


def _overview(recording, bays=()):
    return {"workspace_id": "ws-1", "recordings": [recording], "bays": list(bays)}


def _render(data, *, optimistic=None):
    """The Level 1 section (Recording Information)."""
    script = """
    ready(payload.data);
    if (payload.optimistic) Object.assign(wwRdSide.optimistic, payload.optimistic);
    console.log(JSON.stringify({ html: wwRdSideRenderHtml("s1") }));
    """
    return _node(script, {"data": data, "optimistic": optimistic})["html"]


def _render_group(data, *, optimistic=None, review=None):
    """The Level 2 section (Group Details of group g1)."""
    script = """
    ready(payload.data);
    if (payload.optimistic) Object.assign(wwRdSide.optimistic, payload.optimistic);
    if (payload.review) wwRdSide.review = payload.review;
    console.log(JSON.stringify({ html: wwRdSideBayRenderHtml(GROUP) }));
    """
    return _node(script, {"data": data, "optimistic": optimistic, "review": review})["html"]


def _active(html, row):
    """The Primary/Secondary label(s) shown active inside one row (`recording` or a bay id)."""
    marker = 'data-ww-side-row="recording"' if row == "recording" else f'data-ww-side-row="bay" data-ww-side-bay="{row}"'
    chunk = html[html.index(marker):]
    chunk = chunk[:chunk.index('</span></span>')]
    return re.findall(r'ww-rd-side-btn--active"[^>]*>(\w+)</button>', chunk)


def _buttons(html):
    return re.findall(r"<button[^>]*>([^<]*)</button>", html)


# --------------------------------------------------------------------------- static guarantees


def test_level1_lives_in_recording_info_and_level2_in_group_details():
    code = _code_only(_block())
    assert code.count('wwRdSideSegmentHtml("recording"') == 1 and code.count('wwRdSideSegmentHtml("bay"') == 1
    html1 = _render(_overview(_recording(), [_bay("ec-1", "KPDN1")]))
    assert 'data-ww-side-row="recording"' in html1 and 'data-ww-side-row="bay"' not in html1      # no bays in Recording Info
    html2 = _render_group(_overview(_recording(), [_bay("ec-1", "KPDN1")]))
    assert 'data-ww-side-row="bay"' in html2 and 'data-ww-side-row="recording"' not in html2      # no recording row in Group Details
    assert "return headerHtml + wwRdSideBaySectionHtml(g)" in SOURCE and "html += wwRdSideSectionHtml(s);" in SOURCE


def test_never_per_phase_never_separate_voltage_and_current_group_settings_and_no_reset():
    code = _code_only(_block())
    for forbidden in ("R/Y/B", "side-phase", 'SegmentHtml("phase"', 'SegmentHtml("voltage"', 'SegmentHtml("current"', "reset", "Reset", "Revert"):
        assert forbidden not in code
    # a voltage group and a current group of the SAME bay show the very same bay setting (one association)
    current = _bay("ec-1", "KPDN1", groups=("g1",))
    current["voltage_group_ids"], current["current_group_ids"] = [], ["g1"]
    assert 'data-ww-side-bay="ec-1"' in _render_group(_overview(_recording(), [current]))


def test_no_second_authority_model_in_the_page():
    code = _code_only(_block())
    for forbidden in ("measurement_side", "ps_flag", "channel_name.", "vt_ratio", "ct_ratio", "localStorage"):
        assert forbidden not in code
    assert {"/measurement-side", "/sources/", "/engineering-contexts/"} <= set(re.findall(r'"(/(?:sources|engineering-contexts)/|/measurement-side)"', code))


def test_hooks_invalidate_the_view_on_every_lifecycle_boundary():
    assert "wwRdSideInvalidate(); // D5A-2B2B: the source set changed" in SOURCE
    assert "wwRdSideInvalidate(); // D5A-2B2B: bays/recordings may have changed on another page; always re-read" in SOURCE
    assert "wwRdSideInvalidate(); // D5A-2B2B: a different recording has its own measurement-side state" in SOURCE


def test_notation_uses_words_not_electrical_symbols():
    assert not re.search(r"\bV_[A-Z0-9]|\bI_[A-Z0-9]", _code_only(_block()))


# --------------------------------------------------------------------------- Level 1 rendering


def test_recording_from_evidence_shows_the_declared_side_and_discreet_provenance():
    html = _render(_overview(_recording(), [_bay("ec-1", "ALPHA1")]))
    assert _active(html, "recording") == ["Primary"] and "From recording" in html
    assert html.count('role="radiogroup"') == 1
    assert "Set by engineer" not in html and 'data-ww-side-notice="recording-override"' not in html


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


def test_bay_rows_follow_unconfirmed_manual_split_and_conflict_states():
    bays = [
        _bay("ec-follow", "KPDN1"),
        _bay("ec-manual", "KPDN2", effective="secondary", override={"side": "secondary", "set_at": "x", "active": True},
             overridden=[{"source_id": "s1", "channel_name": "c", "declared_side": "primary", "effective_side": "secondary"}]),
        _bay("ec-new", "KPDN3", membership="suggested"),
        _bay("ec-split", "KPDN4", effective=None, reference_sides="voltage_current_differ", v="primary", i="secondary"),
        _bay("ec-conflict", "KPDN5", effective=None, status="conflict", reference_sides=None, v=None, i="primary",
             diagnostics=[{"code": "BAY_MIXED_SIDES_WITHIN_QUANTITY", "severity": "conflict", "message": "m",
                           "detail": {"quantity": "voltage"}}]),
    ]
    html = _render_group(_overview(_recording(), bays))
    assert _active(html, "ec-follow") == ["Primary"] and _active(html, "ec-manual") == ["Secondary"]
    assert "Set manually" in html and 'data-ww-side-notice="bay-override"' in html
    unconfirmed = html[html.index('data-ww-side-row="bay" data-ww-side-bay="ec-new"'):]
    unconfirmed = unconfirmed[:unconfirmed.index('data-ww-side-row="bay" data-ww-side-bay="ec-split"')]
    assert unconfirmed.count(" disabled") == 2 and "Confirm bay…" in unconfirmed
    assert "Bay not confirmed; it follows the recording." in unconfirmed
    assert _active(html, "ec-split") == [] and "Recorded: voltage primary, current secondary" in html
    assert _active(html, "ec-conflict") == [] and "The voltage channels in this bay declare different sides" in html
    assert html.count("Confirm bay…") == 1
    assert html.count('role="radiogroup"') == 5                            # one per bay, never per phase


def test_only_this_recordings_association_is_shown_and_names_are_escaped():
    bays = [_bay("ec-other", "OTHER", source="s2"), _bay("ec-x", '<img src=x onerror=alert(1)>')]
    html = _render_group(_overview(_recording(), bays))
    assert "OTHER" not in html and "<img" not in html and "&lt;img src=x" in html


def test_a_group_in_no_bay_says_so_and_offers_no_control():
    html = _render_group(_overview(_recording(), [_bay("ec-1", "KPDN1", groups=("other",))]))
    assert "not part of a bay, so it follows the recording" in html and "radiogroup" not in html


def test_a_group_spanning_bays_is_disclosed_and_ambiguity_says_conversion_is_blocked():
    own = _ownership("spans_bays", (("ec-1", "KPDN1"), ("ec-2", "KPDN2")))
    html = _render_group(_overview(_recording(), [_bay("ec-1", "KPDN1", ownership=own), _bay("ec-2", "KPDN2", ownership=own)]))
    assert html.count('role="radiogroup"') == 2 and html.count('data-ww-side-notice="group-spans"') == 1
    assert "KPDN1, KPDN2) that share one measurement side" in html and "group-ambiguous" not in html
    amb = _ownership("spans_bays_ambiguous", (("ec-1", "KPDN1"), ("ec-2", "KPDN2")))
    html = _render_group(_overview(_recording(), [_bay("ec-1", "KPDN1", ownership=amb), _bay("ec-2", "KPDN2", ownership=amb)]))
    notice = re.search(r'data-ww-side-notice="group-ambiguous"[^>]*>([^<]*)<', html).group(1)
    assert "different or unresolved measurement sides" in notice and "is blocked until this is resolved" in notice
    assert "not shared across them" in notice


def test_optimistic_choice_shows_immediately_until_the_view_is_re_read():
    data = _overview(_recording(), [_bay("ec-1", "ALPHA1")])
    assert _active(_render(data, optimistic={"recording": "secondary", "bays": {}}), "recording") == ["Secondary"]
    html = _render_group(data, optimistic={"recording": None, "bays": {"s1|ec-1": "secondary"}})
    assert _active(html, "ec-1") == ["Secondary"]


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
    assert _active(out["active"], "recording") == ["Primary"] and out["optimistic"] == {"recording": None, "bays": {}}


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


def test_a_selection_in_flight_when_the_recording_changes_never_refreshes_the_old_view():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectRecording("secondary");
      await flush();
      wwRdSideInvalidate(); wwRdState.selectedSourceId = "s2";          // switched recording before the answer
      settle(pending[0], {});
      await flush();
      console.log(JSON.stringify({ log, data: wwRdSide.data }));
    })();
    """, {"data": _overview(_recording())})
    assert out["log"] == ['PUT ws-1/sources/s1/measurement-side {"side":"secondary"}'] and out["data"] is None


def test_reselecting_what_is_shown_sends_nothing_except_to_confirm_an_inferred_side():
    out = _node("""
    (async function() {
      ready(payload.plain);
      wwRdSideSelectRecording("primary");
      wwRdSideSelectBay("ec-1", "primary");
      wwRdSideSelectBay("ec-new", "secondary");                         // unconfirmed bay: refused client-side as well
      const none = log.slice();
      ready(payload.inferred);
      wwRdSideSelectRecording("primary");
      await flush();
      console.log(JSON.stringify({ none, log }));
    })();
    """, {"plain": _overview(_recording(), [_bay("ec-1", "A"), _bay("ec-new", "B", membership="suggested")]),
          "inferred": _overview(_recording(derived=_derived(undeclared=2, p=4)))})
    assert out["none"] == []
    assert out["log"] == ['PUT ws-1/sources/s1/measurement-side {"side":"primary"}']


def test_a_bay_choice_is_scoped_to_the_recording_on_screen():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectBay("ec-1", "secondary");
      await flush(); settle(pending[0], {}); await flush(); settle(pending[1], payload.data); await flush();
      console.log(JSON.stringify({ log }));
    })();
    """, {"data": _overview(_recording(), [_bay("ec-1", "A"), _bay("ec-1", "A", source="s2")])})
    assert out["log"] == ['PUT ws-1/sources/s1/engineering-contexts/ec-1/measurement-side {"side":"secondary"}',
                          "GET ws-1/measurement-side"]
    # the other recording's association of the same bay is neither shown nor addressable from this recording
    only_other = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectBay("ec-1", "secondary");
      await flush();
      console.log(JSON.stringify({ log }));
    })();
    """, {"data": _overview(_recording(), [_bay("ec-1", "A", source="s2")])})
    assert only_other["log"] == []


# --------------------------------------------------------------------------- Confirm bay: explicit, reviewed, status only


def _members(*rows):
    return [{"channel_ref": {"kind": "source", "source_id": src, "channel_name": name}, "phase": phase,
             "phase_source": evidence, "original_phase_label": label} for name, phase, evidence, label, src in rows]


REVIEW_CONTEXT = {"id": "ec-new", "display_name": "KPDN3", "status": "suggested", "members": _members(
    ("KPDN3_VA", "A", "detected_from_name", "R", "s1"), ("KPDN3_VB", "B", "structured_metadata", None, "s1"),
    ("KPDN3_IA", "unknown", "unknown", None, "s2"))}


def test_confirming_a_bay_is_a_two_step_review_then_a_status_only_patch():
    data = _overview(_recording(), [_bay("ec-new", "KPDN3", membership="suggested")])
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideOpenReview("ec-new");
      await flush();
      const afterOpen = log.slice();                                    // review: reads the bay's channels, changes nothing
      settle(pending[0], payload.context);
      await flush();
      const panel = rendered.bay;
      wwRdSideConfirmBay("ec-new");
      await flush();
      const afterConfirm = log.slice();
      settle(pending[1], {});
      await flush();
      console.log(JSON.stringify({ afterOpen, panel, afterConfirm, all: log, review: wwRdSide.review }));
    })();
    """, {"data": data, "context": REVIEW_CONTEXT})
    assert out["afterOpen"] == ["GET ws-1/engineering-contexts/ec-new"]
    panel = out["panel"]
    assert "Confirm that these channels belong to <strong>KPDN3</strong>?" in panel
    assert "KPDN3_VA" in panel and ">R<" in panel and "from channel name" in panel          # evidence shown, not hidden
    assert "from recording metadata" in panel and "not determined" in panel and "(other recording)" in panel
    assert "The channels and phases are not changed." in panel
    assert 'data-ww-side-notice="needs-review"' not in panel                                 # only for a needs-review bay
    assert _buttons(panel).count("Confirm bay") == 1 and "Cancel" in _buttons(panel)
    assert out["afterConfirm"] == ['GET ws-1/engineering-contexts/ec-new', 'PATCH ws-1/engineering-contexts/ec-new {"status":"confirmed"}']
    assert out["all"][-1] == "GET ws-1/measurement-side" and out["review"] is None


def test_a_needs_review_bay_is_flagged_in_the_review():
    data = _overview(_recording(), [_bay("ec-new", "KPDN3", membership="suggested")])
    ctx = dict(REVIEW_CONTEXT, status="needs_review")
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideOpenReview("ec-new"); await flush(); settle(pending[0], payload.context); await flush();
      console.log(JSON.stringify({ panel: rendered.bay }));
    })();
    """, {"data": data, "context": ctx})
    notice = re.search(r'data-ww-side-notice="needs-review"[^>]*>([^<]*)<', out["panel"]).group(1)
    assert "Automatic detection flagged this bay for review" in notice


def test_cancelling_or_confirming_without_a_review_changes_nothing():
    data = _overview(_recording(), [_bay("ec-new", "KPDN3", membership="suggested")])
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideConfirmBay("ec-new");                                     // never confirmable without the review
      await flush();
      const direct = log.slice();
      wwRdSideOpenReview("ec-new"); await flush(); settle(pending[0], payload.context); await flush();
      wwRdSideCancelReview(); await flush();
      console.log(JSON.stringify({ direct, log, review: wwRdSide.review }));
    })();
    """, {"data": data, "context": REVIEW_CONTEXT})
    assert out["direct"] == [] and out["log"] == ["GET ws-1/engineering-contexts/ec-new"] and out["review"] is None


def test_a_review_for_another_recording_is_discarded_and_a_failed_review_cannot_confirm():
    data = _overview(_recording(), [_bay("ec-new", "KPDN3", membership="suggested")])
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideOpenReview("ec-new"); await flush();
      wwRdSideInvalidate(); wwRdState.selectedSourceId = "s2";          // the engineer moved to another recording
      settle(pending[0], payload.context); await flush();
      const discarded = wwRdSide.review;
      wwRdState.selectedSourceId = "s1"; ready(payload.data);
      wwRdSideOpenReview("ec-new"); await flush(); settle(pending[1], {}, 500); await flush();
      wwRdSideConfirmBay("ec-new"); await flush();
      console.log(JSON.stringify({ discarded, status: wwRdSide.review.status, log, panel: rendered.bay }));
    })();
    """, {"data": data, "context": REVIEW_CONTEXT})
    assert out["discarded"] is None and out["status"] == "error"
    assert not any(line.startswith("PATCH") for line in out["log"])
    assert "cannot be confirmed now" in out["panel"]


def test_a_refused_save_is_shown_and_the_view_is_re_read():
    out = _node("""
    (async function() {
      ready(payload.data);
      wwRdSideSelectRecording("secondary");
      await flush();
      settle(pending[0], { detail: { code: "x", message: "That bay needs confirmation first." } }, 409);
      await flush();
      const reread = log[log.length - 1];
      settle(pending[1], payload.data);
      await flush();
      console.log(JSON.stringify({ reread, html: rendered.recording, optimistic: wwRdSide.optimistic }));
    })();
    """, {"data": _overview(_recording())})
    assert out["reread"] == "GET ws-1/measurement-side"
    assert "That bay needs confirmation first." in out["html"] and out["optimistic"] == {"recording": None, "bays": {}}
    assert _active(out["html"], "recording") == ["Primary"]                # the server's truth, not the rejected choice


def test_every_rendered_button_is_a_side_choice_or_an_explicit_confirmation_step():
    states = [_bay("ec-a", "A"), _bay("ec-b", "B", membership="suggested"),
              _bay("ec-c", "C", effective="secondary", override={"side": "secondary", "set_at": "x", "active": True})]
    html = _render_group(_overview(_recording(), states)) + _render(_overview(_recording(), states))
    assert set(_buttons(html)) <= {"Primary", "Secondary", "Confirm bay…"}
