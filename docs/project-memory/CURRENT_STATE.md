# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now**. For how it got here, use Git history and
> [HANDOFF.md](HANDOFF.md); do not let this file accumulate into a diary.

Last meaningful update: **2026-08-21** (Phase 5A-UAT — Calculated
Channel Waveform Preview, on top of Phase 5A UAT Fix — Page
Navigation Isolation, Phase 5A — Calculated Channels /
Basic Signal Builder, Phase 4G-UAT Bug Fix — Guidance
Dismissal, Phase 4G-UAT — Persistent Annotation Placement
Guidance Ribbon, Phase 4G — Dynamic Maximum/Minimum Peak Annotation,
Phase 4F-UAT2 — Free 2D Callout Anchor Drag Preview, Phase 4F-UAT —
Movable Callout Anchor,
Phase 4F — Analog Waveform Callout Annotation, Phase 4E-UAT2 — Free Text
Notes restricted to the main waveform workspace, Phase 4E-UAT —
Annotation Scroll Anchoring fix, Phase 4E — Annotation Framework + Free
Text Note, Phase 4D — Precision Step Zoom + Icon Toolbar Refinement,
Waveform Time-Axis Sub-ms Precision, Waveform Adaptive Resolution, Phase
4C2, Phase 4C1, Phase 4B-UAT3, Phase 4B-UAT2, Phase 4B-UAT1, Phase 4B,
Phase 4A-UAT9, and Phase 4A-UAT10).

`[DECISION]` **Calculated Channels / Basic Signal Builder — DEC-047**
(2026-08-21): Oruxa Powerwave's first mathematical signal-derivation
system, NOT an annotation tool — a new main-sidebar page (`Calculated
Channels`, immediately below `Table`), both a Signal Builder and a
Calculated Channel Manager. Phase 1 supports exactly five basic
operations: Reverse Polarity (`y=-x`), Absolute Value (`y=|x|`),
Multiply by Constant (`y=k*x`, dimensionless `k`), N-input Addition
(`y=x1+x2+...+xN`), and ordered N-input Subtraction
(`y=x1-x2-...-xN`, explicitly left-associative, order preserved end to
end) — RMS and every advanced calculation (sequence/power/frequency/
impedance/differential/protection) are explicitly deferred, not even a
disabled RMS card is shown. **Full-resolution authority is
non-negotiable**: every operation evaluates against
`active.record.waveform_data` directly (or another calculated channel's
own already-evaluated result), eagerly, once, at creation — retained
server-side in a new workspace-scoped `CalculatedChannelRegistry`
(mirrors `WorkspaceRegistry`'s own shape), never Plotly trace arrays or
the reduced display envelope, never re-evaluated later.
**The owner's own explicit time-alignment guardrail is a hard rule,
tightened mid-implementation**: multi-input operations require every
operand to be PROVEN to share the same authoritative synchronized
sample-time axis — same-source channels are provably aligned without
array comparison (one `DisturbanceRecord` has exactly one shared
`waveform_data["time"]` column per source, verified directly against
the domain model, not assumed); different-source channels are rejected
UNLESS their true ABSOLUTE instants (`source.start_time + elapsed`, NOT
raw elapsed arrays, which two independently-triggered recordings could
trivially share by coincidence) are proven identical within a
deliberately tight `1e-9`-second tolerance. Equal sample count or
equal sampling rate ALONE are explicitly, deliberately insufficient.
No interpolation/resampling/time-shifting/crop-to-overlap is ever
performed — an unproven pair is rejected outright with a plain-language
message. Units must match exactly (no dimensional conversion layer).
**Calculated-from-calculated is supported from Phase 1**: a calculated
channel may be an input to a further calculation, subject to the same
rules — every calculated channel carries a `reference_source_id`
(the real source ultimately grounding its own inherited time array,
propagated transitively) that lets both timebase-checking and
source-removal cascade collapse to a simple identity/filter check,
never a graph walk; a generic, independently-testable
`would_create_cycle()` guard is implemented as defense in depth (real
cycles are structurally unreachable via the immutable, one-shot
creation API). **A calculated channel is treated as an analog-like
PSEUDO-SOURCE channel everywhere in the existing rendering/layout/
annotation machinery**: its own server-generated id (`"calc-" + <hex>`)
is used AS `sourceId`, its own name AS `channelName`, so
`wwAddSelectedChannels()`/`ww.displayed`/`ww.channelColors`/Grouped-
Separate-Custom/the Annotation List's own `sourceId`+`channelName`
fields all work COMPLETELY UNCHANGED — the only new code is
`wwIsCalculatedSourceId()`, a single dispatch helper at the small set of
network-request call sites (waveform/cursor-values/peak-values/
Callout) that route to a new `/calculated-channels/...` endpoint family
instead of `/sources/{id}/...` — a deliberate, reported structural
shortcut over threading a fully generic `ChannelRef` type through the
entire existing call graph (explicitly avoided as disproportionate
refactor scope for this phase). A/B cursor values, +Peak/-Peak (with
full dynamic viewport recalculation), and Callout (the task's own
"SHOULD" tier — included, not deferred, since it required the same
small increment as the others) all work identically to a real source
channel; adaptive resolution (full-resolution-threshold + peak-
preserving reduction) is reused via two small pure helpers
(`_clip_and_reduce()`/`_peak_in_range()`) extracted from
`waveform_service.py`'s own existing source-channel functions — one
reduction algorithm, one peak-search algorithm in the whole codebase,
verified zero behavior change for the existing source-channel paths.
Default-hidden on creation (DEC-038, unchanged). Immutable after
creation (create another rather than editing); delete is dependency-
aware (BLOCKED, never a silent cascade, while another calculated
channel depends on it). Source removal cascades transitively; "Clear
workspace" preserves definitions (display-only, same established
policy as every other workspace-scoped collection); "Start New
Workspace" clears them completely through the SAME
`DELETE /api/v1/workspaces/{id}` call already used for that purpose
(anticipated by that endpoint's own pre-existing docstring). No
permanent database/cloud persistence. **Bug fix (2026-08-21, same
day)**: owner UAT found the Calculated Channels page rendering STACKED
underneath Recording Events (and separately Waveform) instead of being
hidden — the SAME CSS-cascade bug class as the guidance-ribbon fix
(`#pageCalculatedChannels { display: flex; }` beat the UA `[hidden]`
rule by origin alone; `shellSetCurrentPage()` itself was already
correctly toggling `.hidden`). Fixed with
`#pageCalculatedChannels[hidden] { display: none; }`, the same pattern
`#pageRecordings`/`#workspaceRow` already use. **Waveform Preview
(2026-08-21, same day, straightforward extension)**: a lightweight
**Waveform Preview** panel now sits below the manager list on the same
page -- a completely standalone Plotly instance
(`#wwCcPreviewChart`), never added to `ww.panels`/`ww.viewport`/layout
mode/A-B cursors/annotations, with native Plotly modebar/pan/zoom only
(no custom Powerwave toolbar). Reuses every existing DEC-047 authority
rather than introducing anything new: visibility is
`wwIsAnalogChannelVisible()` (the SAME `ww.displayed`-backed authority
the manager list's own eye icon and the Waveform sidebar group already
share), data is the existing `GET .../calculated-channels/{id}/waveform`
endpoint (no new backend work), color is `wwColorForChannel()`, theme is
`wwThemeColors()`. Wired into the same 3 lifecycle call sites that
already refresh the manager list, so create/delete/toggle/Start New
Workspace/Clear Workspace all behave identically to the manager list's
own established behavior -- no new rule invented. The new
`.ww-cc-preview-chart` CSS class deliberately declares no `display`
property (proactively avoiding a fourth occurrence of the
`[hidden]`-cascade bug this session already hit three times). See
[DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations)
(including both its 2026-08-21 Update notes) and
[MIGRATION_PLAN.md — Phase 5A](MIGRATION_PLAN.md#phase-5a--calculated-channels--basic-signal-builder-2026-08-21)
/ [Phase 5A UAT Fix](MIGRATION_PLAN.md#phase-5a-uat-fix--page-navigation-isolation-2026-08-21)
/ [Phase 5A-UAT — Waveform Preview](MIGRATION_PLAN.md#phase-5a-uat--calculated-channel-waveform-preview-2026-08-21).

`[DECISION]` **Dynamic Maximum/Minimum Peak Annotation — DEC-046**
(2026-08-21; **persistent placement guidance ribbon, addendum,
2026-08-21**): Oruxa Powerwave's THIRD and FOURTH annotation types,
`type: "peak_max"`/`type: "peak_min"` (`+Peak`/`-Peak`), reusing DEC-044/
DEC-045's exact generic framework. Generic recorded-analog-channel
semantics (never instantaneous-voltage/RMS/power/frequency-specific) —
the maximum or minimum of whatever a channel's own recorded Y-axis
values are, over the engineer's CURRENT VISIBLE X VIEWPORT
(`ww.viewport`), never the whole recording. The engineer selects
`Annotate -> Maximum Peak (+Peak)` or `Minimum Peak (-Peak)` (one-shot
placement mode) and clicks an analog trace — the exact clicked channel
resolves via the SAME stable `"sourceId::channelName"` trace `meta`
Callout already uses, but unlike Callout, the click's own X position is
irrelevant to the result. **The key behavioral difference from Callout's
deliberately fixed anchor: a Peak is a LIVE viewport measurement.**
Channel identity (`sourceId`/`channelName`/`mode`/`boxOffset`) is fixed
after creation, but `sampleIndex`/`peakElapsedSeconds`/`peakValue`/`unit`
are dynamic and are RECALCULATED IN PLACE (same annotation id, never a
new one) whenever the X viewport genuinely changes — zoom, pan, step
zoom, Reset Time View, all funneled through the ONE existing
`wwApplyAndFetchViewport()` call site via a new
`wwRecalculateAllPeakAnnotations()`, which batches every active Peak
annotation by its own source into exactly ONE `POST
.../sources/{source_id}/peak-values` request per viewport change (a new,
batched, per-source endpoint mirroring `.../cursor-values`' own
established shape — deliberately NOT an overload of Callout's
`.../annotation-anchor`, whose one-shot-fixed-anchor contract doesn't fit
this genuinely different shape). Y-range changes (Y step zoom, Autoscale
Y), Absolute/Elapsed presentation switching, and Peak box drags never
trigger recalculation — verified directly via before/after request
counts. **Full-resolution authority and tie behaviour are reused, not
reimplemented**: a new `resolve_peak_value()` backend function reads
`active.record.waveform_data` directly (the same authoritative record
`resolve_annotation_anchor`/`extract_waveform_range` already read),
boundary-inclusive range-clips via the same `np.searchsorted` technique,
masks non-finite samples via `np.isfinite` before the max/min search (an
interval with zero finite samples resolves to `available: false`, never
a fabricated peak), and relies on `numpy.argmax`/`argmin`'s own
documented first-occurrence-on-tie behaviour for the owner's required
earliest-sample tie rule — no second nearest-sample or tie-break
definition anywhere in the codebase. **The Peak anchor marker is
calculated and deliberately NOT draggable** (the key interaction
difference from Callout's own now-movable anchor) — the shared
`wwWireCalloutAnchorDrag()` pointerdown handler now checks
`annotation.type === "callout"` before starting any drag preview, and a
Peak's own hit circle is non-hit-testable with no grab cursor; the label
BOX remains fully draggable via the identical `wwWireCalloutBoxDrag()`
mechanics Callout's own box already uses (offset-only, never touches the
anchor, never calls the backend, never triggers recalculation). Rendering
reuses Callout's shared connector/marker/box geometry engine rather than
a second implementation (`wwAnchoredAnnotationContentPosition()`/
`wwAnchoredAnnotationPagePosition()`/`wwAnchorValueToPixelY()`,
generalized from their Callout-only predecessors via two small
type-dispatching getters) — a new `--annotation-peak-accent` token
(muted teal-green, both themes, distinct from A/B cursor blue/red and
Callout's own amber) and a filled-triangle header glyph (apex up/down)
give +Peak/-Peak a recognizable but restrained identity; the canvas label
is a system-computed two-line `.textContent`-only rendering (never
`.innerHTML`, never user-editable — no `text` field, no textarea path).
An anchor currently unprojectable, or a viewport with no valid sample for
the channel (`available: false`), is hidden from canvas but stays fully
intact in `ww.annotations`/the Annotation List, exactly like Callout's
own out-of-viewport handling — recalculation always runs on every genuine
viewport commit regardless of the channel's current display visibility,
so a re-shown channel's Peak is already current by construction, with no
separate "recalculate on show" code path needed. Source removal deletes
a source's Peak annotations outright (extends DEC-045's own sweep,
`wwRemoveAnchoredAnnotationsForSource()`, renamed/generalized from its
Callout-only predecessor). Stale-response protection reuses the SAME
per-source generation-counter pattern `wwCursorValuesGeneration` already
established. No Peak-to-Peak this phase (explicitly out of scope), nor
RMS-from-waveform/cycle-RMS, phasor angle, delta measurement, event
marker, cross-channel peak, digital peak, peak anchor dragging, automatic
A/B placement at peaks, a whole-record/current-window toggle, a custom
search interval independent of the viewport, annotation import/export, or
permanent database persistence. **Owner UAT refinement (2026-08-21, same
day)**: engineering behavior passed, but nothing told the engineer what
to do after selecting a Peak tool. A persistent placement-guidance
ribbon (`#wwAnnotationGuidance`, a normal-layout sibling row between the
waveform toolbar and `#activeViewArea` — never an overlay) is now driven
entirely by `ww.annotationPlacementType` via one generic
`WW_ANNOTATION_PLACEMENT_GUIDANCE` map + `wwUpdateAnnotationPlacementGuidance()`,
called only from `wwEnterAnnotationPlacementMode()`/
`wwExitAnnotationPlacementMode()` — never per-render, no auto-dismiss
timer, `role="status"`. Mandatory for `peak_max`/`peak_min`; also enabled
for `text_note`/`callout` since the same map covered them cleanly.
**Peak's own placement-mode completion timing was corrected as part of
this fix**: it previously exited immediately on any valid trace click
(inherited from Callout's own established one-shot pattern), meaning a
failed/no-data result already silently ended guidance; it now exits ONLY
on a successful creation, guarded by a new `ww.annotationPlacementBusy`
flag against a second concurrent request while one is in flight. Callout's
own exit-immediately timing is explicitly UNCHANGED (not redesigned).
**Bug fix (2026-08-21, same day)**: owner UAT found the ribbon did not
visually disappear after a successful Peak creation, nor on Escape.
Root cause for both: a CSS-cascade bug, not a state bug —
`.ww-annotation-guidance { display: flex; }` (author CSS) beat the UA
stylesheet's own `[hidden] { display: none }` rule by ORIGIN alone, so
`el.hidden = true` had zero visible effect even though
`ww.annotationPlacementType` was already correctly `null` in both cases.
Fixed with `.ww-annotation-guidance[hidden] { display: none; }` — the
same already-established pattern this codebase uses for
`#workspaceRow[hidden]`/`.ww-toolbar[hidden]`/etc. A second, genuine race
found while investigating Escape (a Peak request already in flight when
Escape/tool-switch/reselect fired could still silently create an
annotation afterward) was fixed with a new monotonic
`ww.annotationPlacementGeneration` counter, checked by
`wwCreatePeakFromClick()` before creating anything — a stale/superseded
request's result is now discarded silently. See
[DECISIONS.md — DEC-046](DECISIONS.md#dec-046--maximumminimum-peak-annotations-are-generic-recorded-channel-measurements-over-the-current-visible-x-viewport-dynamically-recalculated-on-genuine-x-viewport-changes)
(including its 2026-08-21 addendum and same-day Update note) and
[MIGRATION_PLAN.md — Phase 4G](MIGRATION_PLAN.md#phase-4g--dynamic-maximum--minimum-peak-annotation-2026-08-21)
/ [Phase 4G-UAT](MIGRATION_PLAN.md#phase-4g-uat--persistent-annotation-placement-guidance-ribbon-2026-08-21)
/ [Phase 4G-UAT Bug Fix](MIGRATION_PLAN.md#phase-4g-uat-bug-fix--guidance-dismissal-2026-08-21).

`[DECISION]` **Analog Waveform Callout — DEC-045** (2026-08-21; anchor
became user-movable, same-channel only, addendum, 2026-08-21; **drag
preview became free 2D, addendum, 2026-08-21**): Oruxa
Powerwave's SECOND annotation type, `type: "callout"`, reusing DEC-044's
exact generic framework (`ww.annotations` remains the sole authority, no
parallel Callout state). Unlike `text_note` (workspace-content-anchored),
a Callout is waveform/data-anchored: one authoritative analog sample
anchor, one editable floating text box, one connector line, one anchor
marker. The engineer selects `Annotate -> Callout` (one-shot placement
mode) and clicks directly on an analog trace -- Grouped/Custom panels
with several traces, and Separate-mode lanes, all resolve the EXACT
clicked channel via each trace's own stable `"sourceId::channelName"`
`meta` field, never curveNumber alone. The clicked approximate elapsed
time is resolved SERVER-SIDE, exactly once, to the nearest ACTUAL
full-resolution recorded sample -- `POST .../sources/{source_id}/annotation-anchor`,
a focused endpoint reusing the EXACT nearest-sample/tie-break logic
`.../cursor-values` (DEC-040) already established (never a second
nearest-sample definition, never the displayed/possibly-reduced Plotly
trace, never interpolated). The resolved `{sampleIndex,
anchorElapsedSeconds, anchorValue, unit}` is the Callout's engineering
anchor -- unchanged by zoom, pan, Y-range changes, Absolute/Elapsed
switching, adaptive display reduction, or Grouped/Separate/Custom layout
changes; only its PROJECTED screen position is recomputed on those
triggers, via the same shared X-projection authority
(`wwCursorTimeToPixelX`) A/B cursors already use plus a per-panel
Y-projection authority built from that panel's own live Plotly
`_fullLayout.yaxis`. **The anchor marker itself is now draggable too
(owner UAT refinement)**: dragging it moves the anchor to a different
sample on its OWN existing source/channel ONLY -- never a different
channel, even when the pointer visually crosses another trace in a
Grouped/Custom panel (cross-channel re-anchoring is explicitly out of
scope). During the drag, the preview marker follows the pointer FREELY
in both X and Y (owner UAT refinement: the original horizontal-only
preview -- X drove the marker, Y stayed pinned to the current
`anchorValue`'s own projection -- felt constrained "like dragging along
a rail" even though the final result was already correct) --
`annotation.data` stays untouched throughout the preview either way.
Final resolution reads ONLY `event.clientX` (via the existing
`wwCursorPixelXToTime()`); pointer Y is NEVER read at release, so it can
never become engineering value authority regardless of how freely the
preview itself moves. Exactly ONE `.../annotation-anchor` request fires
on release, reusing the creation path's own request/error/stale-response
handling verbatim; the marker then visibly SNAPS from its free preview
position to the real resolved waveform sample. A failed resolution,
Escape, or `pointercancel`
restores the original anchor exactly (trivial, since the preview never
wrote to `annotation.data` in the first place). The label box remains
presentation-only and independently draggable via a screen-independent
`data.boxOffset` from the anchor's own current projection (so the box
tracks the anchor through zoom/pan rather than drifting into an
unrelated position, and this offset is preserved through an anchor move
too) -- dragging the box never touches the anchor, never calls the
backend, never rebuilds Plotly. A connector line +
anchor marker render in a lightweight SVG layer
(`#wwCalloutConnectorLayer`, a genuine DOM child of the same
content-anchored overlay the `.ww-annotation` boxes already live in) --
deliberately not Plotly shapes (would need a rebuild on every drag/zoom/
pan). A Callout whose anchor is currently unprojectable (outside the X
viewport, outside the panel's current Y range, or its channel not
displayed) is hidden from canvas but stays fully intact in
`ww.annotations`/the Annotation List, reappearing once projectable again.
Removing the anchor's own source deletes its Callouts outright (their
anchor no longer exists server-side) -- never silently rebound to a
same-named channel on a different source. Analog channels only this
phase (digital Callout, RMS/phasor/peak/delta/event-marker types,
cross-channel annotation, callout import/export, and permanent database
persistence are all explicitly out of scope). Lifecycle otherwise
identical to Text Note: Clear Workspace preserves, Start New Workspace
clears, XSS-safe `.textContent` rendering, centralized deletion via the
Annotation List (which shows Callout's own channel/time/value metadata
line, section 42, refreshed immediately after an anchor move too). No
backend change was needed for the anchor-move refinement, or for making
its drag preview free 2D -- the existing `.../annotation-anchor`
endpoint already accepted an arbitrary `approximate_elapsed_seconds` and
never read a Y value at all. See
[DECISIONS.md — DEC-045](DECISIONS.md#dec-045--callout-is-a-waveform-anchored-annotation-type-analog-only-this-phase-with-a-fixed-engineering-anchor-and-a-movable-presentation-box)
(including both its 2026-08-21 addenda -- movable anchor, then free 2D
drag preview) and
[MIGRATION_PLAN.md — Phase 4F](MIGRATION_PLAN.md#phase-4f--analog-waveform-callout-annotation-2026-08-21).

`[DECISION]` **Annotation Framework + Free Text Note — DEC-044**
(2026-08-20; region-aware scroll anchoring added 2026-08-21; **placement
restricted to the main waveform workspace, refinement, 2026-08-21**):
Oruxa Powerwave's first annotation capability. A GENERIC framework
(`ww.annotations`, `{id, type, workspaceId, region, position, createdAt,
zIndex, data}` records, a type-dispatching Annotation List drawer) with
exactly one type implemented, `text_note` -- a floating note the engineer
places via `Annotate -> Text Note` (one-shot placement mode, click
anywhere inside `#activeViewArea` -- analog panels, digital region,
shared ruler, empty waveform workspace), edits inline (double-click to
edit, blur commits, Escape reverts, multiline via a `<textarea>`), and
drags freely within that same area. **Owner UAT refinement (2026-08-21)**:
placement and dragging in the left Workspace Sidebar were REMOVED --
hands-on UAT of the region-aware scroll-anchoring fix found the sidebar's
own scrolling/resizing/channel-toggle interactions made precise
placement/dragging there unreliable. A click over the sidebar or the
toolbar while placement mode is active is a no-op (mode stays active);
dragging toward the sidebar clamps cleanly at `#activeViewArea`'s own
left content boundary via the same bounds check used for every other
edge. `region` remains a generic per-annotation field (kept for a
possible future annotation type with its own placement rule), but
`"main"` is `text_note`'s only valid value now -- the sidebar-only
overlay DOM, cross-region pointer classification, and mid-drag
reparenting that existed solely to support `text_note`'s prior sidebar
placement were removed entirely, not left dormant. A note carries a RAW
CONTENT-PIXEL `position: {x, y}` measured from `#activeViewArea`'s own
scrollable content origin (`scrollLeft`/`scrollTop` space) -- NOT
normalized 0..1 against `#workspaceRow`. **Notes remain region-aware
content annotations, not fixed to the workspace viewport**: a note
scrolls natively with `#activeViewArea`'s own content via
`#wwAnnotationOverlayMain`, a genuine DOM child of that scroll container
-- zero manual JS scroll-offset compensation. Toolbar exclusion is
structural (the overlay is a sibling of `#wwToolbar`, never a container
of it), not a computed toolbar-rect clamp. Resize re-clamps each note
within `#activeViewArea`'s current `scrollWidth`/`scrollHeight` on every
render, never proportionally rescaling the stored position. An annotation
carrying a stale `region: "sidebar"` from before this refinement (the
sidebar overlay it belonged to no longer exists) is coerced to `"main"`
the next time it renders, rather than crashing or disappearing.
Deliberately NOT waveform/data-anchored (zoom/pan/Absolute-Elapsed/
Grouped-Separate-Custom never move it; a future `callout_note` type with
real time/channel anchoring is a separate later phase). Annotations
belong to the current workspace/session: preserved by the plain "Clear
workspace" button (display-only, confirmed via direct inspection of
`wwClearWorkspace()`'s existing `resetSourceBounds` branch -- the exact
same branch that already preserves A/B cursor state for the identical
reason), cleared only by "Start New Workspace" (a genuinely new
`workspace_id`). The Annotation List is a right-side overlay drawer
(never consumes/reflows workspace width) showing every annotation
newest-first with a delete button per row (centralized deletion, no
permanent × on the floating note itself) and a toolbar count badge.
Pointer isolation via `pointer-events: none` on the overlay's empty space
and `auto` on individual notes -- Plotly zoom/pan, A/B cursor drag, and
sidebar controls are unaffected. Text renders via `.textContent` only,
never `.innerHTML` -- verified XSS-safe. **Visual refinement (2026-08-21,
same day)**: the note's own surface now uses semantic `--annotation-bg`/
`--annotation-border` tokens (a subtle warm cream in Light, a muted warm
dark surface in Dark) instead of `--panel`/`--panel-border`, so it no
longer visually blends into the waveform panel behind it; no A/B cursor
or waveform trace colors used. No backend change. See
[DECISIONS.md — DEC-044](DECISIONS.md#dec-044--generic-annotation-framework-first-type-is-a-workspace-scoped-work-area-relative-free-text-note)
(including both its 2026-08-21 addenda) and
[MIGRATION_PLAN.md — Phase 4E](MIGRATION_PLAN.md#phase-4e--annotation-framework--free-text-note-2026-08-20).

`[DECISION]` **Precision Step Zoom + Icon Toolbar Refinement — DEC-043**
(2026-08-20): two new split-button controls, Zoom In and Zoom Out, add
precise ~20% step zoom for X and Y without four permanent X+/X-/Y+/Y-
buttons. X step zoom is workspace-global (reuses `ww.viewport`/
`ww.workspaceBounds` and the exact same `wwApplyAndFetchViewport()`
authority every other X-viewport change already uses, so DEC-041's
adaptive-resolution fetch genuinely re-runs -- never a bare Plotly
relayout of stale data -- and every panel/the digital region/the ruler
move together while A/B cursor engineering time stays exactly unchanged).
Y step zoom is ACTIVE-PANEL-LOCAL only -- a new `wwActivePanel()` concept
(click, not hover, establishes authority; a subtle border-accent shows
which panel; self-heals across a Grouped/Separate/Custom layout switch so
it can never target a destroyed panel). Autoscale Y is unchanged, still
global across every panel. Separately, the waveform toolbar's major
controls (Box Zoom, Pan, Zoom In/Out, Absolute/Elapsed, Reset Time View,
Autoscale Y, A/B Cursors, Grouped/Separate/Custom, Clear Workspace) are
now SVG icon-primary with title/aria-label tooltips, reusing
`#mainSidebarMenu`'s existing `.shell-nav-icon` visual language rather
than a new one or an external icon library. No backend change; no
engineering-behavior change to any pre-existing control. See
[DECISIONS.md — DEC-043](DECISIONS.md#dec-043--precision-step-zoom-x-step-is-workspace-global-y-step-is-active-panel-local-waveform-toolbar-is-icon-primary)
and [MIGRATION_PLAN.md — Phase 4D](MIGRATION_PLAN.md#phase-4d--precision-step-zoom--icon-toolbar-refinement-2026-08-20).

`[DECISION]` **Waveform Time-Axis Sub-ms Precision — DEC-042**
(2026-08-20): Absolute and Elapsed modes now share one numeric elapsed
engineering X coordinate all the way into Plotly. Absolute Time is
presentation-only: tick labels, hover labels, and A/B cursor readouts format
`recording_start + elapsed`, while waveform sample coordinates, digital
transition positions, the sticky ruler domain, `sourceBounds`,
`workspaceBounds`, `viewport`, zoom/pan relayout values, and backend request
times all remain elapsed floating-point seconds. This corrects the proven
5 kHz Absolute-mode precision loss where date-string Plotly coordinates
collapsed five 0.2 ms samples into each 1 ms x bucket. See
[DECISIONS.md — DEC-042](DECISIONS.md#dec-042--absolute-and-elapsed-waveform-modes-share-numeric-elapsed-plotly-x-coordinates)
and [MIGRATION_PLAN.md — Waveform Time-Axis Sub-ms Precision](MIGRATION_PLAN.md#waveform-time-axis-sub-ms-precision-2026-08-20).

`[DECISION]` **Waveform Adaptive Resolution — DEC-041** (2026-08-20):
waveform reduction is now explicitly an overview rendering optimization only.
For requested analog ranges containing `<= 10,000` original samples per
channel, Oruxa Powerwave returns the complete original sample sequence for
display. Above that threshold, the existing peak-preserving min/max envelope is
still used. The frontend request budget for reduced ranges is pixel-aware
(`plot_width_px * 4`, clamped `4000..20000`) and based on the actual Plotly
plot-domain width, not browser width. Backend full-resolution authority,
sourceBounds/workspaceBounds/viewport, Cur A/B value authority, digital cursor
state, digital transition rendering, and COMTRADE parsing are unchanged. See
[DECISIONS.md — DEC-041](DECISIONS.md#dec-041--waveform-reduction-is-an-overview-rendering-optimization-with-a-10000-sample-full-resolution-display-threshold)
and [MIGRATION_PLAN.md — Waveform Adaptive Resolution](MIGRATION_PLAN.md#waveform-adaptive-resolution-2026-08-20).

## Development phase

`[FACT]` Per [AGENTS.md](../../AGENTS.md): *"Milestone 1 is foundational
hardening only. Not yet in scope: PostgreSQL schemas and migrations,
authentication, object storage, and Powerwave engineering/domain features."*

`[FACT]` **This has changed for the domain-features part**: Phase 1 —
COMTRADE upload, parsing, and channel discovery — is implemented, deployed
to the DEV environment, has completed a full owner UAT pass, has been
refined per that UAT's feedback (channel grouping/search, removal
confirmation, a stale-banner fix), and has had `Start new workspace`
corrected into a real, backend-enforced whole-workspace reset (DEC-018).
This is the first actual Powerwave engineering/domain functionality in
this repository. Authentication, a database, and object storage remain out
of scope, matching Milestone 1. No CSV/Excel, waveform rendering,
synchronization, calculated signals, or advanced analytics exist yet
(Phase 1.5 onward).

`[FACT]`, owner-stated at the start of the Phase 2 discovery/design task
(2026-08-14): **Phase 1 is complete and has passed final owner UAT.** No
further Phase 1 work is expected. Phase 2 discovery/design was completed
that day — see [MIGRATION_PLAN.md — Phase 2 Waveform Workspace Discovery
and Design](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14) —
and **Phase 2A (backend waveform data foundation) is now implemented**
(2026-08-15) — see
[MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15)
and DEC-019 ([DECISIONS.md](DECISIONS.md)). Phase 2A is **backend only**:
the active workspace now retains each source's full-resolution
`DisturbanceRecord` (not just lightweight metadata), and a new
`GET .../sources/{source_id}/waveform` endpoint serves bounded,
peak-preserving (never naively decimated) waveform ranges for one analog
channel at a time.

`[FACT]` **Phase 2B (renderer UAT prototype) is now implemented**
(2026-08-15) — see
[MIGRATION_PLAN.md — Phase 2B Implementation Record](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15).
A new, isolated page (`frontend/waveform-prototype.html`, opened from a
new link on each analog channel row in the existing Phase 1 channel
browser) lets the owner hands-on compare **uPlot** and **Plotly.js**
against the identical Phase 2A backend data/interaction contract — same
endpoint, same channel, same fixed point budget, same debounced/
stale-request-protected range-request pipeline, switching renderers
reuses already-fetched data rather than re-fetching. **No winner has been
chosen — the plotting library remains `[DECISION MODE: UAT]`.**
Digital-channel rendering, cursors/measurements, calculated signals,
synchronization, and Phase 2C's draggable/panel UX remain explicitly
**not** implemented and not authorized by this pass.

`[FACT]` **A focused Phase 2B refinement pass followed the owner's UAT**
(2026-08-15) — see
[MIGRATION_PLAN.md — Phase 2B Plotly Refinement & Workspace-Level
Navigation Record](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15).
Owner UAT result: **Plotly is currently preferred** (better waveform
clarity, richer native controls, smooth interaction) over uPlot (whose
own strength was its built-in crosshair), but **the renderer choice
remains `[UAT — Plotly preferred pending final refinement confirmation]`,
not a closed decision**. This pass added a native Plotly crosshair
(axis spike-lines, snapped to real recorded samples — no custom crosshair
system built), investigated and partly fixed the owner's reported
modebar lag (a real bug: native Autoscale/Reset-axes clicks weren't
triggering a backend re-fetch at all; also shortened the viewport
debounce from 200ms to 120ms), and clarified "Reset Time View" vs.
"Autoscale Y" as distinct operations in both UI text and code. `[DECISION]`
**DEC-021**: waveform navigation is workspace-level (one shared X/time
viewport across every displayed channel), never channel-level — recorded
now, ahead of Phase 2C, specifically so its architecture doesn't
accidentally build per-channel navigation controls. **uPlot was
deliberately retained, unmodified, fully functional** for a final
side-by-side comparison. No Phase 2A backend change, no Phase 2C work.

`[FACT]` **Phase 2B is now complete — the owner's final UAT selected
Plotly.js as the waveform renderer** (2026-08-15) — see
[MIGRATION_PLAN.md — Phase 2B Renderer Closure Record](MIGRATION_PLAN.md#phase-2b--renderer-closure-record-2026-08-15).
`[DECISION]` **DEC-022**: Plotly.js is the waveform rendering foundation;
uPlot was evaluated and is not selected. uPlot's adapter, vendored
assets (`frontend/vendor/uplot/`), and the renderer-switch UI have been
**removed**. The Plotly crosshair was restyled (dashed, thin, reduced-
opacity) to feel visually subtler, closer to uPlot's own visual character
— but crosshair *responsiveness* parity with uPlot was explicitly **not**
pursued (owner judged it not worth the added complexity); Plotly's native
sample-snapped hover behaviour is otherwise unchanged. **DEC-021 remains
fully authoritative and unweakened** — Plotly's native per-channel
modebar, kept for this single-channel page, is explicitly documented (in
the page's own visible text, not just code comments) as temporary, ahead
of Phase 2C's required centralized toolbar. No Phase 2A backend change
(278 tests unmodified, all passing). **Phase 2C has not started.**

`[FACT]` **Phase 2C discovery/design (flexible multi-channel waveform
workspace) is now complete — design only, nothing implemented**
(2026-08-15) — see [MIGRATION_PLAN.md — Phase 2C](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15)
and the "Current approved focus" section below for the summary. **Phase 2C
implementation has not started** — no multi-channel API, no panel model
code, no drag/drop, no digital signals, no cursors exist anywhere in the
repository as of this pass.

`[FACT]` **A small, general-application UX refinement — Light/Dark theme
support and a further Plotly crosshair refinement — is now implemented**
(2026-08-15), **not** Phase 2C work — see
[MIGRATION_PLAN.md — Light/Dark Theme & Crosshair Refinement Record](MIGRATION_PLAN.md#lightdark-theme--crosshair-refinement-record-2026-08-15).
`[DECISION]` **DEC-023**: the application supports Light and Dark
appearance, Light is the preferred/default direction, theme is a general
application preference (not waveform-page-only), and Detego is used only
as a UI/UX benchmark — its palette was not consulted or copied; the light
theme is an original Oruxa palette. Implemented as a shared, reusable
CSS-custom-property token system (`frontend/theme.css`) and preference
module (`frontend/theme.js`) included by every static frontend page —
applied coherently to the main app, channel browser, tables, buttons,
dialogs, banners, the waveform page, and the Plotly chart itself. Dark is
preserved through the same token system (same layout/behavior, different
appearance), not a second CSS implementation. Plotly's chart colors update
via `Plotly.relayout`/`Plotly.restyle` on a theme change — no waveform
data is refetched. The crosshair's `spikethickness` was further reduced
from `1` to `0.5` (a genuine, natively-supported thinner SVG stroke-width
value — the prior pass's "practical minimum" claim was not fully
substantiated) and its alpha reduced further (`0.55` → `0.42`); dashed
style and sample-snapping (`spikesnap: "data"`) are unchanged; no custom
crosshair/cursor engine was built. No backend file changed; 278 backend
tests unmodified and passing. **Phase 2C remains not started.**

`[FACT]` **Theme UAT passed; a small crosshair visual UAT follow-up is now
implemented** (2026-08-15, same day) — see
[MIGRATION_PLAN.md's follow-up subsection](MIGRATION_PLAN.md#follow-up-crosshair-visual-uat-refinement-2026-08-15-same-day)
and the "Update" note appended to
[DEC-023](DECISIONS.md#dec-023--application-supports-light-and-dark-appearance-light-is-the-preferreddefault-direction)
(no new decision entry — a refinement of the same crosshair-styling
concern DEC-023 already covers). `spikethickness` reduced again, `0.5` →
`0.35`; `spikedash` changed from the named `"dash"` style to a custom
native Plotly dash-length string, `"3px,2px"` (Plotly's own `dash`
attribute documents this `"px,px,..."` syntax as first-class native
configuration). **Native limitation, documented honestly**: Plotly's
built-in `"dash"` style has no stable, documented internal pixel
definition to reverse-engineer and halve exactly, so a deliberately
shorter native value was chosen instead — the closest clean native
option, not a mathematically exact half. `--spike-color` strengthened in
both themes for stronger contrast, stopping short of full opacity: Light
`rgba(60, 68, 87, 0.6)` (was `rgba(92, 101, 121, 0.42)`); Dark
`rgba(168, 178, 199, 0.6)` (was `rgba(139, 150, 173, 0.42)`). Grid
styling untouched. No custom crosshair/cursor overlay; no manual SVG
manipulation. No backend file changed; 278 backend tests unmodified and
passing; 19 frontend `jsdom` checks updated in place and passing.
**Phase 2C remains not started.**

`[FACT]` **Phase 2C-A — the first real synchronized multi-channel
waveform display — is now implemented** (2026-08-15) — see
[MIGRATION_PLAN.md — Phase 2C-A Implementation Record](MIGRATION_PLAN.md#phase-2c--synchronized-multi-channel-waveform-display-implementation-record-2026-08-15)
and [DEC-024](DECISIONS.md#dec-024--phase-2c-a-multi-channel-waveform-workspace-architecture-confirmed-and-implemented).
Built directly into `frontend/index.html` (not an isolated page): analog
channel checkboxes + "Add N selected" → panels grouped, on initial
placement only, by the already-computed `engineering_type` → one
independent Plotly instance per panel (never a single figure with fixed
subplots) → one shared, Oruxa-owned X/time viewport driving every panel
(DEC-021, now actually implemented, not just specified) → a single
central 4-button toolbar (Zoom, Pan, Reset Time View, Autoscale Y) with
every native per-panel Plotly modebar disabled. Autoscale Y is
viewport-aware Fit only; Proportional/shared-unit scaling remains
deferred. The existing Phase 2A single-channel waveform endpoint is
reused unmodified — N displayed channels means N existing requests, no
new batching endpoint. A channel can be removed from display (its source
import is untouched); "Clear workspace," source removal, and "Start new
workspace" all correctly clear the relevant part of the waveform display.
Theme switching re-colors every panel without refetching waveform data;
the crosshair (DEC-022/DEC-023) is unchanged, applied per-panel, with
cross-panel crosshair sync explicitly out of scope. No backend file
changed (278 tests unmodified and passing); 19 new + 4 re-verified
existing frontend `jsdom` checks passing (23 total this pass), including
a loop-prevention test against a Plotly test double that faithfully
re-fires relayout events, and a 12-channel/4-panel structural scale
check. **Phase 2C-B (drag/reorder between panels, panel resize,
Proportional Y scaling, mixed-unit handling, digital channels, shared
crosshair) remains explicitly not started.**

`[FACT]` **Phase 2C-A manual UAT passed** (2026-08-15) — shared waveform
synchronization, horizontal zoom, Reset Time View, pan synchronization,
Voltage/Current grouping, and Autoscale Y all confirmed working. Two
findings noted, deliberately not addressed yet: a small amount of
interaction latency, currently bearable; and vertical (Y-axis) zoom is
less intuitive than the rest of the toolbar, flagged for a **later** UX
refinement pass. **Following that UAT, Phase 2C-B1 — Grouped/Separate
analog waveform layout — is now implemented** — see
[MIGRATION_PLAN.md — Phase 2C-B1 Implementation Record](MIGRATION_PLAN.md#phase-2c-b1--grouped--separate-analog-waveform-layout-implementation-record-2026-08-15)
and [DEC-025](DECISIONS.md#dec-025--groupedseparate-analog-waveform-layout-modes-confirmed-and-implemented-phase-2c-b1).
A small Grouped/Separate toggle on the existing central toolbar: Grouped
(the Phase 2C-A default, `engineering_type`-based) is unchanged; Separate
gives every displayed analog channel its own panel/lane. Switching modes
never changes which channels are displayed, never issues a new waveform
request (already-fetched data is reused), and preserves the current
shared X/time viewport exactly — verified directly, not just asserted.
The underlying model (`ww.panels`: displayed channels + panel membership
+ panel order) was already shaped this way since Phase 2C-A; what's new
is `wwPanelGroupKeyFor`/`wwPanelLabelFor` (layout-mode-aware panel
identity) and `wwRebuildLayout()` (re-derives panels from the flat
channel list under the current mode) — deliberately built so a future
direct vertical-drag/reorder/overlay/split interaction (the owner's
stated next direction) doesn't require restructuring this. No backend
file changed (278 tests unmodified and passing); 16 new + 19 + 4
re-verified existing frontend `jsdom` checks passing (39 total this
pass). **Direct drag/reorder, drag-to-overlay/group, drag-out-to-
separate, Custom layout mode, and panel resize all remain explicitly not
started.**

`[FACT]` **Phase 2C-B1 manual UAT passed for synchronization/zoom/pan but
flagged Separate mode's visual layout as not the desired appearance**
(2026-08-15) — Separate mode looked like a stack of individually
bordered/headed cards rather than one continuous analog canvas. **Phase
2C-B2 — a unified analog canvas visual refinement of Separate mode — is
now implemented** — see
[MIGRATION_PLAN.md — Phase 2C-B2 Implementation Record](MIGRATION_PLAN.md#phase-2c-b2--unified-analog-canvas-layout-implementation-record-2026-08-15)
and [DEC-026](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2).
`#wwPanels` gains a `ww-panels-unified` CSS class only while Separate mode
is active: one shared outer background/border replaces N repeated panel
cards, each lane becomes a CSS-grid row (narrow left label column, the
waveform chart taking the maximum remaining width) separated by a
hairline divider instead of a card border, and only the bottom-most lane
shows X-axis tick labels/title (every other lane suppresses them, since
all lanes already share one X/time viewport, DEC-021). **Each channel
keeps its own independent lane and its own independent Y axis — channels
are never merged onto one shared Y axis**, an explicit distinction from
the visual chrome change. Grouped mode's own panel styling is completely
untouched. This is a pure visual/CSS + chrome-relayout layer: no change
to the shared-viewport synchronization mechanism, the panel data model, or
the waveform data contract — switching into or out of unified mode issues
zero new waveform requests, verified directly. No backend file changed
(278 tests unmodified and passing); 20 new + 16 + 19 + 4 re-verified
existing frontend `jsdom` checks passing (59 total this pass). **Direct
drag/reorder, drag-to-overlay/group, drag-out-to-separate, digital-channel
rendering, panel resize, and Custom layout mode all remain explicitly not
started.**

`[FACT]` **Phase 2C-B2 manual UAT passed — the unified analog canvas
direction is accepted** ("Separate view now feels much better") — see the
"Update" note appended to
[DEC-026](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2)
(no new decision entry — a refinement of the same visual-presentation
concern DEC-026 already covers). The owner's next requested refinement —
moving the Separate-mode lane label to a small compact tag on the RIGHT
side, similar in placement/feel to Detego (used only as a layout
reference, never for exact colors/typography/icons) — **is now
implemented (Phase 2C-B3)** — see
[MIGRATION_PLAN.md — Phase 2C-B3 Implementation Record](MIGRATION_PLAN.md#phase-2c-b3--right-side-compact-lane-labels-implementation-record-2026-08-15).
The existing compact legend chip (dot + channel name + unit + remove
button, unchanged since Phase 2C-A) moved from the lane's left edge to its
right edge via a CSS grid-column swap and is now styled as a small pill
(subtle border/background from existing Oruxa theme tokens, not Detego
colors) with `max-width`/ellipsis truncation so the waveform column keeps
maximum width. No panel/data model change, no synchronization change, no
backend change; the remove control still works inside the tag. No backend
file changed (278 tests unmodified and passing); 16 new + 20 + 16 + 19 + 4
re-verified existing frontend `jsdom` checks passing (75 total this pass).
**Direct drag/reorder, drag-to-overlay/group, drag-out-to-separate,
digital-channel rendering, and lane resize all remain explicitly not
started.**

`[FACT]` **The Phase 2C-B3 right-side-column label was still not the
owner's intended layout** — see the further "Update" note appended to
[DEC-026](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2)
(no new decision entry). The owner clarified the label must be **overlaid
on the waveform lane itself**, not placed in a dedicated right-side
layout column, and should follow **Detego's own separate-waveform label
style as closely as practical** for this specific placement — Detego
treated as the explicit layout benchmark here, not just loose
inspiration. **This correction is now implemented (Phase 2C-B3A)** — see
[MIGRATION_PLAN.md — Phase 2C-B3A Implementation Record](MIGRATION_PLAN.md#phase-2c-b3a--overlay-right-side-lane-labels-implementation-record-2026-08-15).
The dedicated fixed-width grid column was removed; the same label DOM
(dot + channel name + unit + remove button) is now absolutely positioned
over the chart area — pinned near the right edge, vertically centered, a
`z-index` above the chart so it floats over the waveform rather than
occupying its own layout space. The waveform column fills the full lane
width. Oruxa theme tokens, the remove control, and Grouped mode's own
presentation remain unchanged. No panel/data model change, no
synchronization change, no backend change. No backend file changed (278
tests unmodified and passing); 17 new + 16 (2 checks corrected in place
for the new overlay mechanism) + 20 + 19 + 4 re-verified existing
frontend `jsdom` checks passing (92 total this pass). **Direct
drag/reorder, drag-to-overlay/group, drag-out-to-separate,
digital-channel rendering, and lane resize all remain explicitly not
started.**

`[FACT]` **The owner chose to skip vertical lane drag/reorder for now and
requested Custom Analog Channel Groups instead — now implemented (Phase
2C-C1)** — see
[MIGRATION_PLAN.md — Phase 2C-C1 Implementation Record](MIGRATION_PLAN.md#phase-2c-c1--custom-analog-channel-groups-implementation-record-2026-08-15)
and [DEC-027](DECISIONS.md#dec-027--custom-analog-channel-groups-added-as-a-third-layout-mode-dragreorder-deferred-phase-2c-c1).
**`[ Grouped ] [ Separate ] [ Custom ]`** — a third layout mode, resolving
the Phase 2C design record's own previously-deferred "Custom grouping"
question (Detego's third grouping mode). Detego's own "Edit Channel
Groups" workflow is the explicit reference (workflow/layout only — no
Detego branding/colors/icons copied). A new **Edit Channel Groups**
dialog (visible only in Custom mode) lets the user create groups and
assign/unassign displayed channels into them (no drag-and-drop; a
two-step unassign-then-assign mechanic instead), with Apply/Cancel.
**Chosen group-assignment rule**: any channel not placed in a group
automatically becomes its own single-channel panel — Apply is never
blocked on complete assignment. Rendering reuses the exact same panel
machinery every other mode already uses (`wwRebuildLayout()` itself
needed zero changes); Custom panels visually resemble Grouped's card
layout, not Separate's unified/overlay treatment, since a Custom panel
can hold multiple channels. Switching modes preserves the displayed
channel set and the current shared X/time viewport exactly (verified
directly, including across Apply); the last-applied custom grouping
persists across mode switches within the session and is only reset by a
whole-workspace clear. No backend change — Custom grouping is frontend-
only, in-memory, ephemeral session state. No backend file changed (278
tests unmodified and passing); 30 new + 17 + 16 + 20 + 16 + 19 + 4
re-verified existing frontend `jsdom` checks passing (122 total this
pass). **Direct vertical lane drag/reorder and drag-to-overlay/group by
direct lane dragging remain explicitly not started — deliberately set
aside in favor of Custom Groups this pass, not abandoned.**

`[FACT]` **Phase 2C-C1 Custom Groups manual UAT passed** — "the workflow
is smooth and easy to understand." Before digital channels, the owner
requested one more analog-workspace refinement, **now implemented
(Phase 2C-C2)**: every waveform panel/lane is independently resizable by
dragging, in all three layout modes — see
[MIGRATION_PLAN.md — Phase 2C-C2 Implementation Record](MIGRATION_PLAN.md#phase-2c-c2--adjustable-waveform-panel-heights-implementation-record-2026-08-15)
and [DEC-028](DECISIONS.md#dec-028--adjustable-waveform-panel-heights-added-to-all-three-layout-modes-phase-2c-c2).
Detego's vertical panel-resize interaction is the named UX benchmark
(placement/feel only — no branding/colors/icons copied). A thin
theme-token-styled handle at each panel's bottom edge, dragged via native
Pointer Events + Pointer Capture, resizes continuously (rAF-coalesced) via
`Plotly.Plots.resize()` only — presentation-only, **zero waveform
refetches, no viewport/Y-range reset, verified directly**. Height is
explicit state (`ww.panelHeights`, keyed by the same `groupKey` panel
derivation already uses — no new identity concept), clamped to
**100–600px** (documented reasoning: 100px keeps a usable plot area above
`wwBuildLayout()`'s own 44px fixed margins; 600px prevents pathological
growth); defaults match each mode's pre-existing height (Grouped/Custom
260px, Separate 140px). A panel's remembered height survives round-
tripping to the SAME mode and back (e.g. Separate→Grouped→Separate
restores VA's own height) without any cross-mode height mapping;
different modes' keys never collide. Session-only (no backend/database
persistence); a whole-workspace reset clears remembered heights, while
individual channel/panel removal deliberately does not (same policy as
Phase 2C-C1's `ww.customGroups`). Separate mode's unified canvas, overlay
label, and bottom-only shared X-axis are all fully preserved under
arbitrary resizing (verified directly); Custom group membership and the
group-editing workflow itself are untouched. No backend file changed
(278 tests unmodified and passing); 23 new + 30 + 17 + 16 + 20 + 16 + 19
+ 4 re-verified existing frontend `jsdom` checks passing (145 total this
pass). **Keyboard resizing was not implemented this slice** (documented
accessibility limitation — `role="separator"` + `aria-label` only, not
`tabindex="0"`/`role="slider"`). **Digital-channel rendering, lane
drag/reorder, and drag-to-group all remain explicitly not started.**

`[FACT]` **Phase 2C-C2's own manual UAT passed functionally** (100–600px
bounds accepted as-is), but the owner **observed a bearable, low-priority
live-resize lag** ("the waveform does not visually follow the panel
resize immediately... a delay of perhaps a few hundred milliseconds").
An investigation (**Phase 2C-C2A**, no code-change assumption going in)
identified the cause and applied one small, low-risk refinement — see
[MIGRATION_PLAN.md — Phase 2C-C2A Investigation Record](MIGRATION_PLAN.md#phase-2c-c2a--panel-resize-responsiveness-investigation-2026-08-15)
and the "Update" note appended to
[DEC-028](DECISIONS.md#dec-028--adjustable-waveform-panel-heights-added-to-all-three-layout-modes-phase-2c-c2)
(no new decision entry). **Bottleneck identified by code-path tracing**:
the cheap DOM height write and the expensive `Plotly.Plots.resize()`
call were bundled inside the same synchronous `requestAnimationFrame`
callback, so the browser could not paint the panel's new box size until
Plotly's own redraw finished, every frame during a drag — confirmed
structurally via jsdom instrumentation with a simulated-cost Plotly mock
(no real browser was available or installed for this one-off
diagnostic; real paint-timing/tactile evidence remains for owner UAT).
**Refinement applied**: the cheap write (`wwSetPanelHeightImmediate`) now
runs on every raw `pointermove`, decoupled from the still-rAF-coalesced
`Plotly.Plots.resize()` call (`wwResizePanelPlot`) — the box now
visually tracks the pointer immediately while Plotly's redraw catches up
a frame behind, still coalesced to at most once per frame (Plotly call
counts unchanged, confirmed by test). The 100–600px bounds, independent
per-panel sizing, the panel-height state model, and all Grouped/
Separate/Custom/synchronization/theme/crosshair behavior are all
unchanged — confirmed **zero waveform refetches** and **zero
synchronization regression**, both by test. No backend file changed
(278 tests unmodified and passing); 9 new + 23 + 30 + 17 + 16 + 20 + 16
+ 19 + 4 re-verified existing frontend `jsdom` checks passing (154 total
this pass).

`[FACT]` **Phase 2C-C2A's owner UAT passed and the resize lag was
reported improved; that issue is closed.** The next feature implemented
was **Phase 2C-C3 — COMTRADE Time-Axis Modes**: two selectable,
workspace-level time-axis representations, **Absolute Time** (real
recording timestamp per sample, sourced from the existing
`timebase.start_time`/`timing_reference` fields already exposed by
`GET .../channels` — **zero backend changes**) and **Elapsed Time**
(the pre-existing 0-based behavior, now explicit/selectable) — see
[MIGRATION_PLAN.md — Phase 2C-C3 Record](MIGRATION_PLAN.md#phase-2c-c3--comtrade-time-axis-modes-2026-08-15).
Absolute is the new COMTRADE default. The shared physical viewport
(elapsed-seconds, DEC-021) is the sole internal authority and is never
touched by a mode switch — only Plotly's X presentation is transformed
at render time, confirmed **zero waveform refetches** on a mode switch.
Trigger timestamp does **not** define the elapsed-time origin (sample 0
= `start_time`, confirmed against real parsed COMTRADE metadata, never
`trigger_time`) — this task's own explicit warning against that
assumption held up under investigation. Timestamps are timezone-naive
end to end (parser never attaches one); the frontend uses only UTC-based
arithmetic and labels the axis context neutrally ("Record time"), never
inferring or silently converting to browser-local time. Works
identically across Grouped/Separate/Custom, preserving Separate's
bottom-lane-only shared axis exactly. `Synthetic Elapsed Time` and
`Sample Index` are reserved names in the time-mode model for future
CSV/Excel work but are **not implemented**; multi-source sync remains
out of scope, with a documented (not fixed) limitation that Absolute
labels would use only the first-displayed channel's origin if multiple
sources were ever combined. No backend file changed (278 tests
unmodified and passing); 26 new + 193 re-verified existing frontend
`jsdom` checks passing (2 pre-existing checks in the non-committed
`phase2ca_check.mjs` now assert an outdated raw-elapsed-number
`xaxis.range` and are the **expected** consequence of the new Absolute
default, not a regression). Verified against a real synthetic COMTRADE
record (including a deliberate midnight/date-rollover case) imported
through the actual FastAPI app.

`[FACT]` **Phase 2C-C3's owner UAT passed**: Absolute Time correct,
Elapsed Time correct, mode switching preserves the physical waveform
window. The next owner-identified usability problem was that with many
displayed channels, the shared time-axis labels were only visible at
the very bottom of the panel stack — solved by **Phase 2C-C4 — Sticky
Shared Waveform Time Axis** — see
[MIGRATION_PLAN.md — Phase 2C-C4 Record](MIGRATION_PLAN.md#phase-2c-c4--sticky-shared-waveform-time-axis-2026-08-15).
ONE workspace-level, Oruxa-owned sticky ruler now stays visible near the
bottom of the viewport while scrolling through the waveform stack —
implemented as a second, lightweight, trace-less Plotly instance
(`wwSyncStickyRuler()`) rather than a hand-rolled SVG axis, deliberately
reusing Phase 2C-C3's own `wwTimeAxisTickFormat()` unmodified so there
is no second, independently-drifting time-formatting implementation.
Alignment with every waveform panel's own plot area is guaranteed by a
new shared constant, `WW_PANEL_MARGIN`, used by both `wwBuildLayout()`
and the ruler. Pure CSS `position: sticky` (not `fixed`, no scroll
listener) — it remains visible only while some part of the workspace is
still below the viewport, and scrolls away naturally once the whole
workspace has been scrolled past. Driven entirely by the existing
`ww.viewport`/`ww.timeMode` state (DEC-021, DEC-029) at the same call
sites that already mutate them (zoom, pan, Reset Time View, mode switch,
channel add/remove, workspace clear, theme switch) — confirmed **zero
new synchronization loop** and **zero waveform refetches**, including
during scrolling itself. Works across Grouped/Separate/Custom.
**Superseding note**: Separate mode's per-lane axis chrome, described
above as "bottom-lane-only," is now suppressed on **every** lane — the
sticky ruler is the primary shared reference, making that lone
remaining bottom-lane axis redundant. Grouped/Custom panels'
own per-panel axis labels are **deliberately left unchanged** this
slice (still shown on every panel, now duplicating the ruler when both
are visible) — a documented, known duplication left for a future
cleanup pass rather than a larger, riskier restructuring. No backend
file changed (278 tests unmodified and passing); 24 new frontend
`jsdom` checks passing, plus the existing suites re-verified with 9 new
failures, all explained by the two changes above (an off-by-one Plotly
call count from the ruler's own extra instance, and the superseded
bottom-lane-only assumption) — not regressions, documented in the
Phase 2C-C4 implementation record.

`[FACT]` **Phase 2C-C4's owner manual UAT passed functionally**: sticky
ruler stays visible while scrolling, alignment good, zoom/pan sync
good, Absolute/Elapsed switching good, resizing does not break the
ruler. The next request was **cosmetic only — Phase 2C-C4A, sticky
time-axis title placement and unit label** — see
[MIGRATION_PLAN.md — Phase 2C-C4A Record](MIGRATION_PLAN.md#phase-2c-c4a--sticky-time-axis-title-placement-and-unit-label-2026-08-16).
A small title now sits at the TOP of the sticky ruler (never under the
ticks): **Absolute mode shows a fixed "Record time"**; the ruler's own
date-context line is simplified to just the date (the toolbar's own
copy keeps its full "<date> · Record time" wording, unchanged).
**Elapsed mode's title is now genuinely unit-aware** — "Time (ms)",
"Time (s)", or "Time (min)" depending on the visible span — derived
from a single new shared decision function
(`wwStickyRulerElapsedUnit()`) that ALSO drives a real rescale of the
ruler's own (independent, trace-less) tick values, so the title can
never disagree with what the ticks actually show. This rescale is
scoped entirely to the ruler's own Plotly instance — `ww.viewport`,
every real waveform panel's own axis, and Phase 2C-C3's timing
semantics are all completely untouched; confirmed zero new
synchronization loop and zero waveform refetches. Works across
Grouped/Separate/Custom, and updates automatically on zoom/pan/mode
switch via the same existing call sites as Phase 2C-C4 (no new
wiring). No backend file changed (278 tests unmodified and passing);
23 new frontend `jsdom` checks passing, plus the existing suites
re-verified with 20 failures across the Phase 2C-A through 2C-C4
suites, all explained (the pre-existing Phase 2C-C3/2C-C4 divergences
already documented in those phases, plus a new — and equally
expected — divergence where several older, pre-COMTRADE-timing test
fixtures' "last relayout call" assumption now sometimes resolves to
the ruler's own correctly-rescaled value instead of a panel's raw
value) — not regressions. **Honest, unverified caveat**: the claim
that rescaling the ruler's own axis domain preserves tick-pixel
alignment with the real (unrescaled) waveform panels was reasoned
through carefully but could not be visually confirmed in this
sandbox (no real browser) — flagged explicitly for owner UAT.

`[FACT]` **Phase 2C-C4's sticky ruler functionality passed owner UAT
— Phase 2C-C4A's visual LAYOUT failed owner UAT.** The custom DOM
title placed above the Plotly tick chart, plus an Absolute-only date
line also above it, produced a tall strip with a large blank vertical
gap — an "information card" appearance, not a compact X-axis. The
owner supplied a reference screenshot and exact desired layout: ticks
first, a small title directly below them, no date in the ruler at all.
Fixed by **Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction**
— see
[MIGRATION_PLAN.md — Phase 2C-C4B Record](MIGRATION_PLAN.md#phase-2c-c4b--compact-sticky-time-axis-layout-correction-2026-08-16).
The custom `#wwStickyRulerTitle`/`#wwStickyRulerContext` DOM elements
were deleted entirely; the ruler now uses Plotly's OWN native
`xaxis.title` — the exact same mechanism every real waveform panel
already uses for its own title — which places ticks first and the
title below them automatically, with no bespoke CSS positioning
needed. The root cause of the blank area was traced to the ruler's own
Plotly margin (`t:4, b:24` inside a 46px chart left an 18px genuinely
empty invisible plot-area gap, stacked under the DOM title/date lines)
— fixed with `margin: {t:2, b:34}` (the SAME b:34 every real panel's
own title already uses successfully) and a reduced 40px chart height.
Resulting total ruler height: **~43–45px**, down from ~63–80px.
Absolute mode's exact wording is now **"Record Time"** (capital T, per
the owner's explicit instruction); no date text appears in the ruler
at all — the toolbar's own date-context label is unchanged. The
unit-aware Elapsed rescaling introduced in Phase 2C-C4A
(`wwStickyRulerElapsedUnit()`) is completely unchanged — same single
source of truth for tick values and title, still scoped entirely to
the ruler's own independent Plotly instance. Sticky CSS mechanism,
alignment (`WW_PANEL_MARGIN`), Separate mode's tick suppression,
Grouped/Custom's unchanged per-panel axes, zoom/pan sync, Reset Time
View, Autoscale Y, panel resize, and the waveform API are all
unaffected — confirmed by test. No backend file changed (278 tests
unmodified and passing); the existing verification script
(`phase2cc4a_check.mjs`) was rewritten (per this correction task's own
explicit instruction) since its old assertions read a DOM element that
no longer exists — 25/25 passing, broader coverage than before. The
existing Phase 2C-A through 2C-C4 suites show the exact same 20
pre-existing, already-documented failures — zero new divergences
introduced by this correction. **Still-outstanding, unverified**:
whether the compact layout visually matches the owner's reference
screenshot, and the Phase 2C-C4A tick-alignment-at-rescaled-units claim
(unchanged, not re-touched by this pass) — both flagged for owner UAT.

`[FACT]` **Phase 3A — Application Shell Redesign Foundation** is the
first STRUCTURAL redesign of the frontend: the whole-page-scrolling,
2-column centered layout is replaced by a full-viewport app shell — see
[MIGRATION_PLAN.md — Phase 3A Record](MIGRATION_PLAN.md#phase-3a--application-shell-redesign-foundation-2026-08-16)
and [DECISIONS.md DEC-031](DECISIONS.md#dec-031--application-shell-architecture-global-header-full-height-main-sidebar-menu-work-area-workspace-row--bottom-status-bar-phase-3a).
Corrected shell hierarchy (the owner explicitly corrected an earlier,
wrong interpretation mid-specification): `Global Header` (full width)
above `Body`, which splits into `Main Sidebar Menu` (FULL Body height —
by construction, since it's a direct flex-row sibling of `Work Area`
inside `Body`) and `Work Area`, which itself splits into `Workspace Row`
(Workspace Sidebar ⇆ Main Workspace) above the `Bottom Status Bar` —
this nesting depth is what structurally guarantees the Status Bar can
never render beneath Main Sidebar Menu, not careful pixel matching.
**Explicitly an INITIAL shell** — exact widths/heights/spacing are
expected to be tuned by owner UAT.
Main Sidebar Menu: narrow icon rail, collapsed by default, toggled
(never drag-resizable — independent state from Workspace Sidebar
width). Workspace Sidebar (Import/Sources/Channels, relocated
unredesigned): horizontally drag-resizable via a new small, reusable
split-pane helper (`shellCreateHorizontalSplit()`, default 320px/min
240px/max 520px, explicit state persisted to `localStorage` for the
session) — the SAME function a future Waveform ⇆ Table split is
expected to reuse. Main Workspace: Workspace Toolbar (unchanged
controls, "Clear workspace" relocated into it) above an Active View
Area holding `shell.activeView` (`"waveform"`|`"table"`|`"split"` —
app-shell state, deliberately separate from waveform-domain state `ww`,
per section 28's own explicit instruction); Waveform is real, Table/
Split are structural placeholders only (confirmed by test: zero fake
data, zero new fetches). Bottom Status Bar: real values only (workspace
id, station, sample rate, duration, displayed-channel count — sourced
from data already fetched for other reasons, never fabricated).
Responsive: desktop/laptop is the unconditional primary target; under
~900px Main Sidebar Menu force-collapses and Workspace Sidebar becomes
a reopenable overlay drawer (pure CSS, no JS breakpoint duplication);
phone is treated as a secondary companion mode, not fully designed this
phase, only structurally un-blocked. **Every existing Phase 2C waveform
feature (Grouped/Separate/Custom, Custom Groups, synchronized zoom/pan,
Reset Time View, Autoscale Y, Absolute/Elapsed, the sticky ruler,
panel-height resize, Light/Dark theme, crosshair) was relocated, not
rewritten** — every element kept its exact ID; confirmed unchanged by
the FULL existing jsdom regression suite showing the exact same
pre-existing pass/fail counts as immediately before this phase (zero
new divergences, independently verified before/after, not assumed). No
backend file changed (278 tests unmodified and passing); 40 new
frontend `jsdom` checks passing (`phase3a_check.mjs`). **Unverified**:
actual visual proportions, resize feel, and responsive behavior at real
narrow widths — no real browser in this sandbox; explicitly flagged for
owner UAT, consistent with this phase's own "initial, UAT-refined"
framing.

`[FACT]` **Phase 3A's shell STRUCTURE passed owner UAT — one child-
layout bug was found**: when the Workspace Sidebar widened, Main
Workspace correctly became narrower, but the Plotly waveform canvas
didn't reflow to fit, and could visually overflow its own panel frame.
Fixed by **Phase 3A-UAT1 — Responsive Waveform Width Reflow** — see
[MIGRATION_PLAN.md — Phase 3A-UAT1 Record](MIGRATION_PLAN.md#phase-3a-uat1--responsive-waveform-width-reflow-2026-08-16).
**Root cause**: Plotly's own `responsive: true` config only reliably
reacts to actual `window` resize events, not a container that changed
size because a sibling flex item (the Workspace Sidebar) resized — the
CSS itself was already correctly shrinking the container (`min-width:
0` was already present everywhere it mattered); Plotly was simply never
told to redraw, so its stale, wider SVG bled past the (correctly sized)
`.ww-chart-wrap`. **Fix**: a new `wwResizeAllVisiblePlots()` (reuses the
existing `wwResizePanelPlot()` per panel, plus the sticky ruler) is now
called from three trigger points — the Workspace Sidebar's own resize
(rAF-coalesced, one authoritative final call on pointerup/pointercancel,
reusing the exact Phase 2C-C2A scheduling pattern), Main Sidebar Menu's
`transitionend` event (the correct signal an animated collapse/expand's
width has actually finished changing), and window resize (added
defensively, rAF-coalesced). `.ww-chart-wrap` also gained `overflow:
hidden` as a defense-in-depth safety net (a no-op once the resize fix
itself is correct). Confirmed by test: zero waveform refetches, the
physical viewport is byte-identical before/after any width-only change,
works identically in Grouped/Separate/Custom. **Test-infrastructure
fix, not an application change**: six older jsdom scratch scripts were
missing a `requestAnimationFrame` polyfill this fix's own rAF-
coalescing now unconditionally depends on at Init time (every real
browser has this natively) — patched with the same polyfill later
scripts already use; the full suite returns to the identical
pre-existing 20-failure baseline, zero new divergences. No backend file
changed (278 tests unmodified and passing); 20 new frontend `jsdom`
checks passing (`phase3auat1_check.mjs`). **Unverified**: actual visual
containment and reflow smoothness in a real browser — no real browser
in this sandbox; flagged for owner UAT.

`[FACT]` **Phase 3A-UAT1's width-reflow fix passed owner UAT; that issue
is closed. Phase 3A-UAT2 — Remove Duplicate Header Theme Control — is
now implemented** (2026-08-16) — see
[MIGRATION_PLAN.md — Phase 3A-UAT2 Record](MIGRATION_PLAN.md#phase-3a-uat2--remove-duplicate-header-theme-control-2026-08-16).
The Global Header's own `#themeToggle` Light/Dark segmented control was
removed (element + its `mountThemeToggle()` call in Init) since it
duplicated the Main Sidebar Menu's existing "Settings" item, which
already toggles the same preference — **the Main Sidebar Menu is now the
single theme/settings entry point** in `index.html`. `theme.js`'s shared
`mountThemeToggle()` function itself, and `.theme-toggle` (a CSS class
also used by the unrelated `#shellViewToggle` view selector), were left
untouched — `frontend/waveform-prototype.html` (a separate page, out of
scope) still mounts its own theme toggle unchanged. All underlying theme
mechanics (persistence, cross-tab sync, Plotly re-color, zero-refetch)
are confirmed unchanged by test. No backend file changed (278 tests
unmodified and passing); 11 new frontend `jsdom` checks passing
(`phase3auat2_check.mjs`); one pre-existing check in
`theme_crosshair_check.mjs` was corrected in place (it asserted the
now-intentionally-removed `#themeToggle` exists in `index.html`) rather
than left broken. **Unverified**: visual header spacing and Main Sidebar
Menu Settings usability in a real browser — flagged for owner UAT.

`[FACT]` **Phase 3A-UAT3 — Targeted Overflow and Containment Fixes — is
now implemented** (2026-08-16) — see
[MIGRATION_PLAN.md — Phase 3A-UAT3 Record](MIGRATION_PLAN.md#phase-3a-uat3--targeted-overflow-and-containment-fixes-2026-08-16).
An independent Codex audit (run against a local tree that could not
reach GitHub) identified seven candidate overflow/containment risks in
the Phase 3A shell; per this task's own explicit instruction, every
finding was independently re-verified against canonical `main` before
anything was implemented — **all seven were confirmed still present and
fixed**, none were rejected as invalid. Fixes: (A) corrected a CSS
source-order bug that permanently hid the responsive Workspace Sidebar
reopen button (`#shellSidebarToggleBtn`) even inside its own `@media
(max-width: 900px)` breakpoint; (B) gave the Workspace Sidebar's channel
table (`.group-body`) an intentional `overflow-x: auto` so a table too
wide for a 240px sidebar scrolls instead of being silently clipped by
the outer `overflow: hidden` group container; (C) added
`overflow-wrap: anywhere`/`min-width: 0` to source/detail metadata
(station name, filenames, recorder name, sampling-rate list) so long
unbroken tokens wrap in place instead of forcing the Sidebar wider; (D)
gave Custom Groups chips a dedicated, shrinkable `.group-chip-label`
span (`max-width: 100%` on the chip, `overflow-wrap: anywhere` on the
label) and confirm-dialog text the same wrap treatment; (E)
`shellSetActiveView()` now schedules a Plotly resize pass (reusing Phase
3A-UAT1's own `wwScheduleResizeAllVisiblePlots()`) whenever the active
view becomes `"waveform"`, so charts that went stale while hidden behind
the Table/Split placeholder catch up; (F) the Workspace Sidebar's
persisted desktop width (an inline style, highest CSS specificity short
of `!important`) is now cleared on entering the drawer breakpoint (so
the CSS `min(320px, 82vw)` rule governs) and restored exactly on
returning to desktop, via a `window.matchMedia` listener — the
persisted preference itself is never mutated; (G) gave the base
(Grouped/Custom) `.ww-legend-item`/`.ww-legend-label` the same
containment/ellipsis technique the already-owner-approved Separate-mode
overlay tag uses, without touching that more-specific, already-UAT'd
rule at all. No shell restructuring, no Table/Split/digital-channel
work, no backend change. No backend file changed (278 tests unmodified
and passing); 29 new frontend `jsdom` checks passing
(`phase3auat3_check.mjs`), using deterministic long-unbroken-token
fixtures for every named content type. **Test-infrastructure fix, not
an application change**: 16 existing scratch scripts needed a
`window.matchMedia` polyfill (jsdom has none at all) since Finding F's
fix now calls it unconditionally at Init; one of them
(`frontend_logic_check.mjs`) also needed a `requestAnimationFrame`
polyfill it had never previously required — full suite returns to the
identical pre-existing 20-failure baseline, zero new divergences.
**Unverified**: real-browser visual confirmation at continuous (not just
discrete simulated) viewport widths — flagged for owner UAT.

`[FACT]` **Owner UAT of Phase 3A-UAT3 exposed one remaining real
overflow case — Phase 3A-UAT4 — Channel Filename Containment — is now
implemented** (2026-08-16) — see
[MIGRATION_PLAN.md — Phase 3A-UAT4 Record](MIGRATION_PLAN.md#phase-3a-uat4--channel-filename-containment-2026-08-16).
The affected area is the Workspace Sidebar's Channels → source-detail
section: uploaded CFG/DAT filenames (e.g. `260725_1309444309_Tanjung
Bin BEN6K.cfg`/`.dat`) could still visibly overflow at a narrowed
Sidebar width, even after Phase 3A-UAT3's Finding C already added
`overflow-wrap: anywhere` to the filename text elements. **Root cause**:
`.detail-header`'s flex-item child (holding the station name +
filenames) never had its own `min-width: 0` — the same `min-width:auto`
flex trap already fixed at the shell level, recurring one level deeper
inside this specific card. Text-level wrap rules only matter once the
box around the text can actually shrink; without that, the whole block
stayed at full width regardless of the text's own settings. **Fix**:
the previously-unnamed wrapper now has a real class,
`.detail-header-info` (`min-width: 0; max-width: 100%;`), with
`.detail-header h3`/`.meta` additionally gaining explicit `white-space:
normal; max-width: 100%;` alongside their existing `overflow-wrap:
anywhere`. Filename text must now wrap fully within the Sidebar at
every width down to the 240px minimum — full text always remains
visible, nothing truncated/ellipsized/hidden. This is a targeted
correction that does **not** reopen the wider Phase 3A shell design —
Workspace Sidebar resize bounds, Main Workspace reflow, Grouped/
Separate/Custom, the sticky ruler, panel-height resize, the responsive
drawer, Custom Groups, and header/status-bar layout are all confirmed
unchanged by test. No backend file changed (278 tests unmodified and
passing); 12 new frontend `jsdom` checks passing
(`phase3auat4_check.mjs`), using the owner's own exact reported
filenames plus a longer underscore-heavy/unbroken-token stress fixture,
verified across a 520px/320px/240px Sidebar-width matrix. **Unverified**:
whether the filename now visibly wraps exactly as the owner's own
reference example showed in a real browser — flagged for owner UAT.

`[FACT]` **Phase 3B — Recordings Page and Upload Workflow — is now
implemented** (2026-08-16) — see
[MIGRATION_PLAN.md — Phase 3B Record](MIGRATION_PLAN.md#phase-3b--recordings-page-and-upload-workflow-2026-08-16)
and [DECISIONS.md DEC-032](DECISIONS.md#dec-032--recordings-page-as-a-first-class-application-page-one-recording--one-logical-event-cfgdat-sessionworkspace-backed-not-a-persistent-cloud-library-phase-3b).
The Main Sidebar Menu's "Workspace" item was renamed "Waveform" and a
new, real "Recordings" item was added alongside it (`shell.currentPage`,
new app-shell state kept separate from `shell.activeView`). Recordings
(heading "Recording Events") is a dedicated page with no contextual
Workspace Sidebar — a searchable table listing every source currently
active in the workspace (one row per CFG+DAT pair, never separate rows
for the companion files), with real columns only (Recording name +
filenames, Station, Recorder, Channels, Duration, Imported, Actions) and
an "Upload New" button. The always-visible "Import COMTRADE Event" form
was removed from the Workspace Sidebar; its logic was refactored into
ONE extensible upload modal (provider/format-driven via a small
`RECORDING_FORMATS` model — COMTRADE the only enabled format, CSV/Excel
listed as real but `disabled` options, proving forward-readiness without
implementing either parser) shared by the Recordings page's "Upload New"
button and the Global Header's "Import" shortcut. Navigating Waveform ⇆
Recordings never destroys or rebuilds the waveform workspace — confirmed
by test that the physical viewport, layout mode, Custom Groups, panel
heights, and time mode all survive the round-trip exactly, with zero
waveform refetch; returning to Waveform schedules a Plotly resize pass
(reusing the Phase 3A-UAT1/UAT3 mechanism) in case available width
changed while away. "Open / Analyse" reuses the existing `selectSource()`
unchanged and navigates to Waveform; "Remove" reuses the existing
confirmation-and-delete flow unchanged, now consistently updating the
Recordings list, the Workspace Sidebar, and the waveform-displayed-
channel state from one shared refresh. **Storage philosophy explicitly
unchanged**: the Recordings page is session/workspace-backed only — no
database table, no persistent cloud file library, no upload history
across sessions were added; this remains a separate future decision.
**One small, additive backend change**: `SourceSummaryOut` gained
`duration_seconds`/`sample_count` (both already computed, no new storage)
so the Recordings list's Duration column doesn't require a per-row
`.../channels` fetch. 279 backend tests passing (278 + 1 new, zero
regressions); 30 new frontend `jsdom` checks passing
(`phase3b_check.mjs`); two existing test files' assertions were updated
in place where Phase 3B's own deliberate UX changes (no persistent
success banner outside the modal; the old sidebar upload form's removal)
made their prior assertions test since-removed behavior, not a
regression — full suite otherwise at the same pre-existing 20-failure
baseline, zero new divergences. **A real CSS bug was caught and fixed
before shipping**: `#workspaceRow` and the Status Bar's waveform-only
items both had author `display: flex` CSS that would have silently
defeated the `hidden` attribute (author CSS beats the UA stylesheet's
default `[hidden]` rule by origin, regardless of specificity) — explicit
`[hidden]` override rules were added for both. **Unverified**: real-
browser visual confirmation of the Recordings page layout, the upload
modal's format selector, and long-filename wrapping in the Recording
column — flagged for owner UAT.

`[FACT]` **Owner UAT of the Recordings page found one cosmetic issue —
Phase 3B-UAT1 — Recording Row Divider Alignment — is now implemented**
(2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT1 Record](MIGRATION_PLAN.md#phase-3b-uat1--recording-row-divider-alignment-2026-08-17).
The Actions column's bottom row divider sat higher than the divider
under the other columns. **Root cause**: the Actions `<td>` carried the
`.recording-actions` flex class directly, overriding its `display`
away from `table-cell` and removing it from the browser's normal
same-row-height cell stretching. **Fix**: the flex layout now lives on
an inner `<div>` inside a plain, unclassed `<td>`, so every cell in a
row shares one border position again. No workflow, column widths, or
containment behavior changed. No backend file changed (279 tests
unmodified and passing); 7 new frontend `jsdom` checks passing
(`phase3buat1_check.mjs`). **Unverified**: real-browser visual
confirmation that the divider now reads as one continuous line —
flagged for owner UAT.

`[FACT]` **Owner established a clearer Recordings/Waveform
responsibility split — Phase 3B-UAT2 — Remove Duplicate Waveform-Page
Import / New-Workspace Actions — is now implemented** (2026-08-17) —
see
[MIGRATION_PLAN.md — Phase 3B-UAT2 Record](MIGRATION_PLAN.md#phase-3b-uat2--remove-duplicate-waveform-page-import--new-workspace-actions-2026-08-17).
Recordings is now the sole recording/session-management surface
(upload/import, Open/Analyse, Remove, and whole-workspace lifecycle);
Waveform stays analysis-only. The Global Header's own "Import"
shortcut was removed entirely (Recordings' "Upload New" already covers
it); "Start new workspace" was relocated (same element ID, same
unchanged `startNewWorkspace()`/`resetToNewWorkspace()` logic) from the
Global Header onto the Recordings page's own header row, grouped
beside "Upload New". "Clear workspace" (Waveform toolbar, displayed-
channels-only) remains untouched and distinct. No backend file changed
(279 tests unmodified and passing); 14 new frontend `jsdom` checks
passing (`phase3buat2_check.mjs`). **Unverified**: real-browser visual
confirmation of the simplified Waveform header and the grouped
Recordings actions — flagged for owner UAT.

`[FACT]` **Phase 3B-UAT3 — Recordings Header Action Cleanup — is now
implemented** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT3 Record](MIGRATION_PLAN.md#phase-3b-uat3--recordings-header-action-cleanup-2026-08-17).
"Start new workspace" and "Upload New" (already grouped together since
Phase 3B-UAT2) were reordered to `[ Start new workspace ] [ Upload New
]` — Upload New remains visually primary (unclassed button style),
Start new workspace remains `.secondary`. No "Import" button exists
anywhere (confirmed, not re-added). A small button-typography
inconsistency was also fixed: `.secondary` (0.8rem) and `.danger`
(0.78rem) — two near-duplicate literal font sizes for the same
"compact action" tier — now share one CSS token,
`--button-font-size-compact: 0.8rem`; the primary button size (0.9rem)
and the toolbar/segmented-control size (0.76rem) remain their own
deliberately distinct, untouched tiers. No backend file changed (279
tests unmodified and passing); 13 new frontend `jsdom` checks passing
(`phase3buat3_check.mjs`). **Unverified**: real-browser visual
confirmation of the reordered actions and the (intentionally very
small) font-size unification — flagged for owner UAT.

`[FACT]` **Recordings is now the application's default fresh-entry page
— Phase 3B-UAT4 — Recordings as Default Entry Page — is now
implemented** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT4 Record](MIGRATION_PLAN.md#phase-3b-uat4--recordings-as-default-entry-page-2026-08-17)
and [DECISIONS.md DEC-033](DECISIONS.md#dec-033--recordings-is-the-applications-default-fresh-entry-page-no-separate-landingdashboard-page-phase-3b-uat4).
Visiting the application fresh now shows the Recordings page ("Recording
Events") instead of an empty Waveform workspace, reflecting the intended
product flow: choose/upload a recording → Open / Analyse → Waveform.
**No separate Powerwave landing/dashboard page was added** — Recording
Events itself remains the operational entry page; a future dashboard
remains an open, undecided future question, not built now. **No routing
framework was introduced** — the app has no URL-aware navigation at
all, so the implementation is a single default-state change
(`shell.currentPage` now initializes to `"recordings"`), applied via
the same `shellSetCurrentPage()` every other navigation already uses,
with the static HTML's own default visibility/`aria-current` attributes
kept hand-in-sync to avoid any flash of the old Waveform default.
`shellSetCurrentPage()` itself is unmodified, so the already-established
"hide, don't destroy" navigation behavior (Recordings ⇆ Waveform
preserves viewport, layout mode, Custom Groups, panel heights, and time
mode, with zero waveform refetch) is unaffected — confirmed by test with
a full multi-hop round trip. The Global Header is unaffected by this
specific change (Phase 3B-UAT2/UAT3 had already relocated all page-
specific actions off it) and remains reserved for genuinely global
application/user-level functions. No backend file changed (279 tests
unmodified and passing); 8 new frontend `jsdom` checks passing
(`phase3buat4_check.mjs`). **Unverified**: real-browser visual
confirmation that fresh page loads show Recordings with no visible
flash — flagged for owner UAT.

`[FACT]` **Recording metadata now lives on the Recordings page, not the
Waveform sidebar — Phase 3B-UAT5 — Move Recording Metadata from Waveform
to Recordings — is now implemented** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT5 Record](MIGRATION_PLAN.md#phase-3b-uat5--move-recording-metadata-from-waveform-to-recordings-2026-08-17).
The Waveform Workspace Sidebar's `.stat-grid` metadata card stack
(Recorder, Nominal Frequency, Timing Mode, Samples, Duration, Sampling
Rate(s), Start Time, Trigger Time) was removed; the `.detail-header`
identity block (station name + filenames) stays. Each Recordings row
gained a `[ Details ]` button that expands a sibling table row showing
that exact recording's metadata, reusing the existing `.stat-grid`
pattern — multiple rows may be expanded at once (documented design
choice, not a single-open accordion). `SourceSummaryOut` gained
`timing_reference`/`start_time`/`trigger_time`/`sampling_rates` (purely
additive, already-computed domain fields) so the Details panel renders
entirely from the already-fetched `GET .../sources` list response —
zero extra fetch, zero reparse, zero re-upload. **Timing Mode
investigation (owner's explicit ask)**: confirmed via code inspection
that `timing_reference` is genuine, permanent, source-level recording
metadata (from the parsed COMTRADE record, gating which Waveform display
modes are even offered) — architecturally distinct from the user's live
Absolute/Elapsed view toggle (`ww.timeMode`) — safe to relocate, but
relabeled "Timing reference" (was "Timing mode") to remove the exact
ambiguity risk the owner flagged. 280/280 backend tests passing (279
baseline + 1 new); 14 new frontend `jsdom` checks passing
(`phase3buat5_check.mjs`). **Unverified**: real-browser visual
confirmation of the expanded Details panel's layout/spacing and Light/
Dark appearance — flagged for owner UAT.

`[FACT]` **Recording Details no longer repeats main-table metadata —
Phase 3B-UAT6 — No Duplicate Metadata in Recording Details — is now
implemented** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT6 Record](MIGRATION_PLAN.md#phase-3b-uat6--no-duplicate-metadata-in-recording-details-2026-08-17).
Owner clarification after Phase 3B-UAT5: the expanded Details panel had
been repeating Recorder and Duration, both already visible as their own
columns in the main Recordings table. Rule applied: main table = quick
identification/summary; expanded Details = supplementary technical
metadata only. `renderRecordingDetails()` now shows just Nominal
frequency, Timing reference, Samples, Sampling rate(s), Start time,
Trigger time, plus a separate "Files" section for CFG/DAT — Recorder,
Duration, and Channels are never repeated. The layout also switched from
vertical `.stat-grid` cards to one compact horizontal `<table>` row
(owner's own mockup), inside an `overflow-x: auto` wrapper so it scrolls
rather than breaks Work Area's width at narrow viewports. The now-fully-
unused `.stat-grid`/`.stat`/`statCard()` machinery (its last caller was
this same Details panel) was deleted rather than left as dead code. The
main Recordings table itself was not redesigned; Open/Analyse, Remove,
search, and the expand/collapse mechanism are unchanged. Zero backend
diff (no new field needed — Recorder/Duration/Channels were already in
`SourceSummaryOut`; this only changed which already-available fields
render where). 9 new frontend `jsdom` checks passing
(`phase3buat6_check.mjs`). **Unverified**: real-browser visual
confirmation of the compact horizontal table's readability and
horizontal-scroll behavior at narrow widths — flagged for owner UAT.

`[FACT]` **UAT6's table layout was accepted technically but rejected on
UX grounds; a redesigned structured details panel is now implemented —
Phase 3B-UAT7 — Recording Details UX Redesign** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT7 Record](MIGRATION_PLAN.md#phase-3b-uat7--recording-details-ux-redesign-2026-08-17).
An analysis-first design-review turn preceded implementation (three
alternatives compared; owner approved Option B, "structured two-zone
details," plus a rule to remove CFG/DAT filenames from the main
Recordings table). What changed: the main Recording cell now shows only
the logical recording name (`.recording-files` sub-line deleted; the
search index still includes filenames even though they're no longer
visibly rendered); the UAT6 `<table>`/`<thead>` details grammar was
replaced by three plain zones — a wrapping "facts" strip (Nominal
frequency/Timing reference/Samples/Sampling rate(s)), dedicated
full-width Start/Trigger timing lines, and a Files group separated by a
quiet divider; a thin `--accent` left bar on the details panel plus a
`--accent-wash-soft` tint on the parent row (via a new
`tr.recording-row-expanded` class) visually tie an open panel to its own
row, even with several expanded at once; the Details toggle now keeps a
stable "Details" label and reuses the app's existing `.chevron`
disclosure glyph (already used for Analog/Digital channel groups)
instead of swapping button text, visually demoted (transparent border)
below Open/Analyse and Remove. Zero backend diff, 280/280 backend tests
passing (unchanged). 19 new frontend `jsdom` checks passing
(`phase3buat7_check.mjs`). **Unverified**: real-browser visual
confirmation of the accent-bar/row-tint association, chevron rotation
smoothness, and overall polish — flagged for owner UAT.

`[FACT]` **Two further owner refinements were folded into the same
Phase 3B-UAT7 pass before it went through another UAT round** — see
[MIGRATION_PLAN.md — Phase 3B-UAT7 (continued) Record](MIGRATION_PLAN.md#phase-3b-uat7-continued--final-table-restructuring-and-row-click-to-open-2026-08-17)
(2026-08-17). **Final main-table columns**: Recording | Start Time |
Duration | Sampling Rate(s) | Actions — Station/Recorder/Channels/
Imported removed as columns; Sampling Rate(s) and Start Time promoted
from Details (both purely additive frontend formatting, zero backend
change; `formatSamplingRates()` renders every real rate, never
simplifying a genuine multi-rate source). **Details reorganized into
Technical** (Recorder, Channels, Nominal frequency, Timing reference,
Samples) **/ Timing** (Trigger, Imported — Start Time moved out, the
opposite direction from Sampling Rate(s)) **/ Files** (CFG, DAT) zones,
each with a quiet zone-title caption. **Row-click-to-open**: the
explicit "Open / Analyse" button was removed; the recording `<tr>`
itself (`tabindex="0"`, `role="button"`, `aria-label`) is now the
primary Open/Analyse target, reusing the same `openRecordingForAnalysis()`
call — no second implementation. Actions is icon-only now (Details'
`.chevron` glyph + Remove's `&times;`, both already-established glyphs
elsewhere in this app), with `event.stopPropagation()` on both buttons'
click handlers plus an `event.target !== row` guard on the row's own
keydown handler isolating them from the row's click/Enter/Space
activation. Zero backend diff, 280/280 backend tests passing
(unchanged). 22 frontend `jsdom` checks passing (`phase3buat7_check.mjs`,
substantially rewritten for the final state). **Unverified**: whether
row-click-to-open feels natural versus accidental, and whether the
icon-only Actions column reads clearly without visible tooltips — both
flagged for owner UAT.

`[FACT]` **Waveform sidebar management UI removed (Recordings-only now)
and Main Sidebar reordered/bug-fixed — Phase 3B-UAT8 — Waveform Sidebar
Cleanup + Main Navigation Refinement** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT8 Record](MIGRATION_PLAN.md#phase-3b-uat8--waveform-sidebar-cleanup--main-navigation-refinement-2026-08-17).
Owner product-responsibility rule: Recordings = management, Waveform =
active recording context + analysis only. The Waveform sidebar's old
"Sources in this Workspace" (a clickable multi-source list with a
per-row Remove button) was replaced by a compact, read-only "Active
Recording" section showing only whichever source is currently selected
(name + analog/digital counts, no list, no Remove, no source-switching
— switching now happens exclusively via Recordings' own row click).
`renderChannels()`'s repeated station-name/CFG/DAT identity block was
removed (that identity now lives in Active Recording, directly above
Channels). **Bug found and fixed**: the Main Sidebar's active-item CSS
rule (`[aria-current="page"]`) had never actually matched anything since
Phase 3B introduced page navigation — the JS was writing the string
`"true"`/`"false"` instead of the token `"page"`, so the active-page
accent tint/background was silently broken the whole time; fixed via a
shared `setShellNavCurrent()` helper (writes `"page"` when active,
removes the attribute when not — the ARIA APG convention), plus a new
narrow left accent bar. Main Sidebar reordered to Recordings first,
Waveform second (matching the actual product flow); Recordings/Waveform
got new, more semantically correct icons (a record-list icon, a
zigzag/waveform icon) — Table/Tools/Reports/Settings icons unchanged.
Zero backend diff, 280/280 backend tests passing (unchanged). 24 new
frontend `jsdom` checks passing (`phase3buat8_check.mjs`); one
pre-existing script (`phase3auat4_check.mjs`) substantially rewritten
since its entire original premise — CFG/DAT filename containment inside
the Waveform Channels panel — no longer applies (filenames don't render
in Waveform at all anymore; retargeted to the equivalent long-name
containment concern in Active Recording). **Unverified**: whether the
accent-bar/tint combination and the new icons read clearly, and whether
the lighter (non-card) Active Recording section still feels sufficiently
present — flagged for owner UAT.

`[FACT]` **All scrollbars across the frontend are now slim and
borderless — Phase 3B-UAT9 — Slim Borderless Scrollbars** (2026-08-17)
— see
[MIGRATION_PLAN.md — Phase 3B-UAT9 Record](MIGRATION_PLAN.md#phase-3b-uat9--slim-borderless-scrollbars-2026-08-17).
A single shared rule set was added to `frontend/theme.css` (already
shared with `waveform-prototype.html`) — a universal `*` selector
covering both the Firefox path (`scrollbar-width: thin`/
`scrollbar-color`) and the Chromium/WebKit path
(`::-webkit-scrollbar` family), 6px thumb, transparent border-free
track/corner, fully rounded thumb using two new theme tokens
(`--scrollbar-thumb`/`--scrollbar-thumb-hover`, defined in both Light
and Dark, following the same alpha-over-neutral-base convention as
`--hover-tint`/`--surface-tint` — no hardcoded colors). CSS only, no
browser-specific JavaScript. Zero scrolling functionality removed —
all seven identified scrollable containers
(`#mainSidebarMenu`/`#workspaceSidebar`/`#activeViewArea`/
`#pageRecordings`/`.recordings-table-wrap`/`.group-body`/
`.group-editor-box`) keep their existing `overflow: auto` and layout
borders untouched. Zero backend diff (backend untouched). 18 new
frontend `jsdom` checks passing (`phase3buat9_check.mjs`, source-level
only — jsdom has no scrollbar rendering). **Unverified**: actual
rendered slimness/hover-contrast/theme legibility — flagged for owner
UAT (requires a real browser).

`[FACT]` **Scrollbar track gutters in the reported border-line areas
now blend with their local surfaces — Phase 3B-UAT10 — Targeted
Scrollbar Track / Divider Fix** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT10 Record](MIGRATION_PLAN.md#phase-3b-uat10--targeted-scrollbar-track--divider-fix-2026-08-17).
The global Phase 3B-UAT9 slim scrollbar baseline remains unchanged:
6px WebKit scrollbar dimensions, borderless rounded thumbs, and theme
thumb tokens are still shared from `frontend/theme.css`. The follow-up
fix adds only targeted local track colors for `#mainSidebarMenu`,
`#workspaceSidebar`, `.group-editor-box`, and `.group-body`, including
`::-webkit-scrollbar-track-piece` plus Firefox `scrollbar-color` track
colors. This addresses the diagnosed cause: a transparent scrollbar
gutter could make adjacent real panel/divider borders read like a
scrollbar rail. Structural borders and overflow/layout rules are
preserved. Lightweight committed source-level coverage now lives in
`backend/tests/test_frontend_scrollbar_css.py`; `git diff --check`,
the focused test (4/4), and the full backend suite (309/309, two
existing warnings) pass. Real rendered visual confirmation remains for
owner UAT in a browser.

`[FACT]` **The remaining hard line immediately right of the Workspace
Sidebar scrollbar has been corrected — Phase 3B-UAT11 — Workspace
Sidebar Divider / Scrollbar Line Cleanup** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 3B-UAT11 Record](MIGRATION_PLAN.md#phase-3b-uat11--workspace-sidebar-divider--scrollbar-line-cleanup-2026-08-17).
Owner real-browser UAT after UAT10 showed the thumb/track were acceptable
but a thin line remained immediately to the scrollbar's right. Source
inspection identified that line as the structural
`#workspaceSidebar { border-right: 1px solid var(--panel-border); }`,
not a scrollbar pseudo-element; the adjacent `.shell-split-handle::after`
already provided a centered resize/divider affordance. The fix removes
the sidebar's hard right border on both desktop and drawer variants and
keeps the resize handle as the single desktop separator. The drawer
keeps its existing shadow boundary. UAT9/UAT10 scrollbar size, thumb,
track, track-piece, and Firefox rules are unchanged; sidebar width,
resize bounds, overflow, and Plotly resize callback are unchanged.
Focused UAT11 source checks pass (6/6), committed/tracked backend tests
pass (286/286, two existing warnings), and `git diff --check` is clean;
a raw full pytest against this dirty local worktree fails only on
pre-existing untracked digital-waveform tests outside UAT11 scope.

`[FACT]` **Digital (binary/state) channels now render in the Waveform
workspace — Phase 4A — Digital Channels Rendering** (2026-08-17) — see
[MIGRATION_PLAN.md — Phase 4A Implementation Record](MIGRATION_PLAN.md#phase-4a--digital-channels-rendering-implementation-record-2026-08-17)
and [DECISIONS.md — DEC-034](DECISIONS.md#dec-034--digital-channel-rendering-shared-batched-full-record-transition-api-one-shared-multi-trace-plotly-figure-not-one-instance-per-channel-phase-4a).
A new backend endpoint (`GET .../sources/{id}/digital-waveform`,
batched via repeated `channel_names` params) serves each displayed
digital channel's full-record transition list (never point-budget/range-
reduced — digital transitions are inherently sparse, so full delivery is
both the most truthful and the smallest-payload representation);
classification (Triggered/Never Triggered/Spare, with the owner's exact
required precedence — name-contains-"spare" beats any observed high
state, and "any non-zero sample across the full record" is Triggered
even with zero 0→1 transitions) is computed once at import time, never
re-scanned per request. The frontend renders every displayed digital
channel as one true step (`line_shape: "hv"`) trace inside a SINGLE
shared Plotly figure — a genuinely different architecture from analog's
own one-instance-per-panel model (DEC-024/DEC-026), chosen because a
COMTRADE record may carry hundreds of digital channels and the owner
explicitly required them ALL displayed by default. The digital region
sits in its own vertically-scrollable area strictly below all analog
panels and strictly above the existing shared sticky ruler (DEC-030),
which remains the one authoritative bottom time reference. **Opening a
source now displays every analog AND digital channel by default**
(previously analog required a manual checkbox + "Add selected"); this
is scoped per source-open (`ww.sourceDefaultsApplied`), never reapplied
merely by navigating Waveform → Recordings → Waveform back to an
already-open recording, so a manually-hidden channel stays hidden. This
is a deliberate owner-directed UAT experiment, not a claim that it
scales indefinitely without limits — see the Phase 4A record's own
performance section and the open owner-UAT questions in its final
report. Full existing frontend regression suite returned to exactly its
established pre-existing baseline (17 failures, all independently
confirmed as pre-existing and unrelated to this phase); backend suite
311/311 passing (286 pre-existing + 25 new). Not yet owner-UAT'd in a
real browser — flagged, per this task's own explicit closing
instruction, as **not** ready for any further waveform feature work
until that UAT completes.

`[FACT]` **Digital waveform rendering corrected/redesigned per owner UAT
— Phase 4A-UAT1B — Digital Waveform UX / Correctness Refinement**
(2026-08-18) — see
[MIGRATION_PLAN.md — Phase 4A-UAT1B Record](MIGRATION_PLAN.md#phase-4a-uat1b--digital-waveform-ux--correctness-refinement-2026-08-18).
Owner UAT on Phase 4A found: (1) the rendered digital region looked
purely alphabetical rather than classification-grouped (root cause: the
sort/classification data was ALREADY correct end to end, verified fresh
against both the ASCII and BINARY COMTRADE provider paths — the
rendered chart simply never showed any group header/separator, unlike
the channel browser, so a numerically-dominant group made the whole
thing read as flat), (2) digital traces did not visually line up with
analog traces (root cause: a real bug — the digital chart's own Plotly
left margin, 150px, differed from every analog panel's and the shared
ruler's 55px, so identical X values rendered at different pixel
positions), (3) opening a recording with everything displayed by
default could lag with no visible loading state, (4) constant-HIGH vs
constant-LOW digital signals were hard to tell apart. All four are now
fixed: rendered group headers with counts mirror the channel browser
exactly; the digital chart's margin now exactly matches
`WW_PANEL_MARGIN` (true pixel alignment, not approximate); and the
rendering itself was redesigned to the owner's own visual benchmark — a
thin muted baseline line always present, with a bold/thick band drawn
only during HIGH intervals (derived from `initialState` + the sparse
`transitions` list), making constant-HIGH (full-width bold band) and
constant-LOW (no band, thin line only) immediately distinguishable
without relying on color alone; channel name labels are now small
opaque pill annotations overlaid directly on each lane (pinned to the
plot area's left edge via `xref: "paper"`), not a wide Y-axis tick
column — this is also what made the margin fix possible. A new
`#wwWorkspaceLoading` overlay appears as the very first thing
`selectSource()` does (before any fetch starts), reports a REAL
per-channel "N / total" progress count (never a fake percentage), and
is always cleared via `try/finally` regardless of success or failure.
Pure frontend change — no backend file touched, no new architecture
decision (refines DEC-034's existing rendering approach, does not
change it). Frontend regression suite still exactly the established
17-failure pre-existing baseline; backend 311/311 unchanged. Not yet
owner-UAT'd in a real browser — flagged as **not** ready for further
waveform feature work until that UAT completes.

`[FACT]` **Phase 4A-UAT2 — Fix Remaining Digital Waveform UAT
Failures** (2026-08-18) — see
[MIGRATION_PLAN.md — Phase 4A-UAT2 Record](MIGRATION_PLAN.md#phase-4a-uat2--fix-remaining-digital-waveform-uat-failures-2026-08-18).
Real-browser owner UAT on the Phase 4A-UAT1B build reported grouping/
ordering as PASS, but four criteria as FAILED: alignment, loader
visibility, label overlay, and HIGH-band boldness — treated as
authoritative over any prior "code exists that was intended to solve
this" claim. Root causes found via direct source investigation: (1)
alignment — `wwResizeAllVisiblePlots()` (the established Phase 3A-UAT1
catch-up path for Plotly's own `responsive:true` not reliably detecting
non-window container resizes) had never been updated to include the
digital chart, so any Workspace Sidebar drag, Main Sidebar collapse,
window resize, or even ordinary Recordings→Waveform navigation left
digital's rendered width stale relative to analog/ruler, independent of
the UAT1B margin fix; (2) loader — this project's own Phase 2C-C2A
finding ("the browser cannot paint until synchronous work returns
control") applies here too; fixed with an explicit double-`requestAnimationFrame`
paint-yield plus reordering `openRecordingForAnalysis()` so the page
becomes visible before `selectSource()`'s loader does; (3) labels — the
label annotation was vertically offset above its own trace rather than
centered on it, now fixed to `yanchor:"middle"` at the trace's exact Y;
(4) HIGH band — no concrete logic bug was found after exhaustive
re-audit of the interval-generation code (re-verified correct via jsdom
against constant-HIGH/constant-LOW/transitioned fixtures both before and
after), so HIGH bands were switched from a second gapped line trace to
`layout.shapes` — the same simpler, already-proven-working primitive
already used for the group-divider lines in the same chart — removing
an entire class of possible trace-rendering risk. A new
`wwDiagnoseDigitalAlignment()` diagnostic (run in the browser console)
reads Plotly's own real `_fullLayout` geometry for the owner to verify
directly. Pure frontend change, no backend file touched, no new
architecture decision. Frontend regression suite still the established
17-failure baseline; backend 311/311 unchanged. **Explicitly cannot be
accepted as visually fixed from this sandbox alone** — no real browser
is available here; every fix is evidence-backed but owner real-browser
UAT remains required before any further waveform feature work.

`[FACT]` **Deployed build provenance is now exposed — Phase 4A-UAT3 —
Build SHA / Version Provenance** (2026-08-18) — see
[MIGRATION_PLAN.md — Phase 4A-UAT3 Record](MIGRATION_PLAN.md#phase-4a-uat3--build-sha--version-provenance-2026-08-18).
`APP_VERSION` (already `deploy.yml`'s own `github.sha`, already used to
tag Docker images) is now also passed as a runtime environment variable
into both containers. `GET /health` returns `version`
(short 7-char) and `git_sha` (full 40-char), sourced only from that
variable — never by running `git` inside a container. The frontend's
existing `config.js` runtime-config mechanism (regenerated at container
start by `frontend/docker-entrypoint.d/10-powerwave-config.sh`, never at
Docker build time) now also carries `environment`/`buildVersion`; on
startup the app logs one console line
(`Oruxa Powerwave — <environment> — build <version>`) and sets
`document.documentElement.dataset.build` from the same value, so a
stale browser tab truthfully shows the stale build it actually loaded —
deliberately never re-fetched from GitHub at runtime, which would hide
exactly the mismatch this feature exists to surface. A container/process
started without `APP_VERSION` set reports the truthful `"local"`
fallback (matching `scripts/deploy.sh`'s own pre-existing convention),
never a fabricated hash. Pure additive change, no backend behavior
otherwise altered, no new architecture decision. Backend 321/321 (311
pre-existing + 10 new); frontend regression suite at 18 failures (the
established 17 plus one pre-existing, independently-confirmed-unrelated
failure from an external toolbar/font-size commit, not from this
phase's own work). No DEV/PROD deployment dispatched from this sandbox
this pass (no deploy credentials available here) — structural
verification only; owner end-to-end confirmation remains the next step.

`[FACT]` **The Channels sidebar is now the primary analog waveform
legend — Phase 4A-UAT4 — Channel Sidebar as Analog Legend** (2026-08-18)
— see
[MIGRATION_PLAN.md — Phase 4A-UAT4 Record](MIGRATION_PLAN.md#phase-4a-uat4--channel-sidebar-as-analog-legend-2026-08-18).
The obsolete per-channel "Waveform (UAT)" control is removed (no dead
column, no dead handler). Each analog channel row in the sidebar now
shows a small color dot beside its name — the SAME color
(`wwColorForChannel()`, keyed by `sourceId::channelName`, the one color
authority) driving both that dot and its Plotly trace, never two
independently-assigned colors; a channel not currently displayed keeps
its real color visible but dimmed, never hidden entirely, so an
engineer can see what color it will use when re-added. Colors are
stable through remove+re-add, layout-mode switches, time-mode switches,
and navigation — a `ww.channelColors` map persists for the workspace
session (cleared only by a whole-workspace reset, the same lifecycle
policy already established for `ww.customGroups`/`ww.panelHeights`).
**Grouped and Custom modes** no longer render the duplicated per-channel
chip-legend strip above the canvas (the sidebar is their legend now;
group/custom-group headings are unchanged); their removal affordance
moved into the sidebar row itself, reusing the pre-existing
`wwRemoveChannelByKey()`. **Separate mode's existing per-lane legend
chip (dot, name/unit, overlay position, remove control) is explicitly
UNCHANGED** — one lane = one channel there, so it was never the same
duplication the owner asked to remove; this was clarified mid-task after
an initial uniform-removal attempt, which was reverted before this
record was written. Full frontend regression suite: still exactly the
established 18-failure baseline (all independently reconfirmed
pre-existing by comparison against untouched canonical `main`); backend
321/321 unchanged (no backend file touched — pure frontend UX
consolidation). Not yet owner-UAT'd in a real browser — flagged as
**not** ready for further waveform feature work until that UAT
completes.

`[FACT]` **Analog channel sidebar rows are now the display toggle
directly — Phase 4A-UAT5 — Simplify Analog Channel Toggle Rows**
(2026-08-18) — see
[MIGRATION_PLAN.md — Phase 4A-UAT5 Record](MIGRATION_PLAN.md#phase-4a-uat5--simplify-analog-channel-toggle-rows-2026-08-18).
The analog checkbox and the UAT4-era sidebar remove button are both
gone: clicking (or Enter/Space-activating) a channel's own row toggles
its display directly, reusing the existing `wwAddSelectedChannels()`/
`wwRemoveChannelByKey()` paths and `wwColorForChannel()` unchanged — no
new color logic, no second active/inactive map. A displayed row is
100% opacity; a hidden row dims to 25% (rising to 55% on hover/focus for
discoverability) across the WHOLE row, not only the dot. The color dot
grew from 7px to 10px. Name and Unit are combined into one "Channel"
column (`"GT4 VB (kV)"`, or bare `"GT4 VB"` when unit is empty) — the
Unit column is gone. **Analog checkbox selection is removed outright**:
"Add N selected"/"Clear selection" now refer to DIGITAL selection only
(button text unchanged — still truthful, since N can only ever reflect
a digital pick now); digital's own checkbox/selection workflow,
`renderDigitalGroup()`, and `digitalChannelCheckboxHtml()` are
byte-for-byte untouched. **Separate mode is explicitly NOT redesigned**
— `wwRenderLegend()` and every `.ww-legend*` rule are unchanged; the
sidebar row toggle and the Separate lane's own local remove control
coexist safely, both reading/writing the same `ww.displayed` state.
Default-all-display-on-open and hide/show persistence across ordinary
navigation are both preserved. Full frontend regression suite: still
exactly the established 18-failure baseline (reconfirmed file-by-file
against pre-UAT5 `main`); backend 321/321 unchanged (no backend file
touched). Landed on `origin/main` via a concurrent session's own commits
(`e51b647`, `be201d3`, titled "adjusting padding") rather than a
dedicated commit — see the MIGRATION_PLAN.md record's own "A note on how
this landed in Git history" for what happened and how it was verified;
nothing was lost, but `git log`/`git blame` alone will not describe this
change accurately. Not yet owner-UAT'd in a real browser.

`[DECISION]` **Analog channel visibility is workspace-global; layout
mode governs arrangement only, never visibility — Phase 4A-UAT6 —
Global Analog Channel Visibility Across Layout Modes** (2026-08-19,
[DEC-035](DECISIONS.md#dec-035--analog-channel-visibility-is-workspace-global-layout-mode-governs-arrangement-only-never-visibility-phase-4a-uat6))
— see
[MIGRATION_PLAN.md — Phase 4A-UAT6 Record](MIGRATION_PLAN.md#phase-4a-uat6--global-analog-channel-visibility-across-layout-modes-2026-08-19).
`ww.displayed` was confirmed (via a direct reproduction of the owner's
own reported sequence, which already passed against pre-UAT6 code) to
already be the one correct global visibility authority every layout
renderer derives from — no state-duplication bug existed in the simple
Grouped/Separate/Custom hide-and-switch path. The REAL, concrete bug was
in the Custom Groups editor: opening it silently filtered a group's
membership down to only currently-displayed channels, and Applying
committed that filtered (i.e. pruned) copy back — permanently losing a
hidden channel's group assignment, so re-enabling it later dropped it
into its own auto-solo panel instead of its original group. Fixed by no
longer filtering membership at open time; a new `ww.channelMeta` map
(same lifecycle as `ww.channelColors`/`ww.customGroups`/`ww.panelHeights`
— survives hide, cleared only by a whole-workspace reset) lets the
editor still describe a hidden member's name/unit/color (rendered
dimmed via `.group-chip--hidden`) without requiring it to be displayed.
`wwColorForChannel()` and the Separate-mode local `x` (which was already
routing through the same global `wwRemoveChannelByKey()` path) are both
unchanged. **A separate, unrelated, pre-existing rendering bug was
discovered but deliberately NOT fixed in this pass** — `wwAddSelectedChannels()`
can double-add a Plotly trace for the 2nd..Nth channel of a brand-new
panel when 2+ new channels join the same group in one batch call (most
commonly triggered by default-display-on-open); flagged for the owner as
its own separate task. Full frontend regression suite: still exactly the
established 18-failure baseline; backend 321/321 unchanged (no backend
file touched). Not yet owner-UAT'd in a real browser.

`[FACT]` **Duplicate analog trace rendering is fixed — Phase 4A-UAT7 —
Fix Duplicate Analog Trace Rendering** (2026-08-19), resolving the
out-of-scope defect DEC-035 flagged and deliberately left unfixed — see
[MIGRATION_PLAN.md — Phase 4A-UAT7 Record](MIGRATION_PLAN.md#phase-4a-uat7--fix-duplicate-analog-trace-rendering-2026-08-19)
and [DECISIONS.md — DEC-035's own "UAT7 resolution"](DECISIONS.md#dec-035--analog-channel-visibility-is-workspace-global-layout-mode-governs-arrangement-only-never-visibility-phase-4a-uat6).
Confirmed root cause: `wwAddSelectedChannels()`'s incremental-add loop
used a per-meta flag that incorrectly treated a panel created moments
earlier by an EARLIER channel in the SAME batch as "pre-existing,"
causing that panel's 2nd..Nth channel to be drawn twice (once via the
new panel's own complete `Plotly.newPlot()`, once more via a redundant
`Plotly.addTraces()`) — most commonly triggered by default-display-on-
open for any source whose first-populated engineering-type group has
2+ channels. Reproduced directly (3-channel batch produced 5 traces,
`A, B, C, B, C`, with exactly 3 correct network requests — the
duplication was rendering-only, never a duplicate fetch). Fixed by
gating the incremental-add loop on membership in `newlyCreatedPanels`
(already correctly tracked, just not consulted at the right point)
instead of the incorrect per-meta flag — one panel, one clear trace-
ownership path (new-panel creation owns its complete set; incremental
add owns only channels joining an ALREADY-existing panel). Also added a
stable `meta: wwChannelKey(...)` field on every built trace and an
on-demand `wwDiagnoseDuplicateAnalogTraces()` console helper (mirrors
the established `wwDiagnoseDigitalAlignment()` pattern). Separate mode
was confirmed never affected (structurally one channel per lane) and is
untouched; `wwColorForChannel()`, DEC-035's global visibility, and
Custom Group membership are all unaffected and reverified. Digital
rendering confirmed untouched (architecturally distinct code path, no
shared trace-ownership logic). Full frontend regression suite: still
exactly the established 18-failure baseline; backend 321/321 unchanged
(no backend file touched). Not yet owner-UAT'd in a real browser.

`[DECISION]` **DEV deployment is now automatic after CI succeeds on
main; PROD remains fully manual, forever, by construction —
[DEC-036](DECISIONS.md#dec-036--dev-deployment-is-automatic-after-ci-succeeds-on-main-prod-remains-fully-manual)**
(2026-08-19), narrowing
[DEC-003](DECISIONS.md#dec-003--deployment-is-manual-dev-and-prod-stay-isolated-prod-gets-the-commit-dev-tested)
— see
[MIGRATION_PLAN.md — CI/CD Record](MIGRATION_PLAN.md#cicd--automatic-dev-deployment-after-ci-2026-08-19).
Followed an owner-requested investigation into why pushes to `main`
stopped auto-deploying DEV: the original `deploy.yml` (2026-08-09) DID
trigger on `push`, but was deliberately replaced with
`workflow_dispatch`-only the same day when the single dev/prod-selectable
workflow was introduced, and formalized 5 days later as DEC-003 — not a
regression, but the owner approved restoring automation for DEV
specifically. New `.github/workflows/deploy-dev.yml` (the existing
`deploy.yml` is byte-for-byte untouched): triggers on `workflow_run` of
the "CI" workflow completing on `main` (never a bare `push`, which would
race CI rather than wait for it), its one job gated on
`conclusion == 'success'` so a failing commit is never deployed, and
deploys the EXACT SHA CI validated
(`github.event.workflow_run.head_sha`, not `github.sha`, which is
unreliable in a `workflow_run` context) — preserving the existing build-
provenance chain (Phase 4A-UAT3) unchanged. The new file is DEV-only by
construction: no `target` input exists at all, every value the manual
workflow selects via `${{ inputs.target }}` is the literal string `"dev"`
in this file, and it shares its concurrency group with `deploy.yml`'s own
dev-targeted runs so the two paths can never race the same VPS. The
manual `deploy.yml` (`workflow_dispatch`, `dev`/`prod` choice) remains
completely unchanged and is still the only way to reach PROD. Governance
updated: DECISIONS.md (new DEC-036; DEC-003 annotated in place, not
rewritten), `development-workflow.md`, `HANDOFF.md`, this file.
`AGENTS.md`'s existing wording already named only PROD as requiring
explicit deployment, so it was left as-is. Validated via `yamllint` +
Python YAML parsing (both clean); no live GitHub Actions run could be
observed from this sandbox (no `gh`/API credentials available) — flagged
for owner verification after this push.

`[FACT]` **Digital channel visibility now uses direct row toggles
matching the analog interaction model — Phase 4A-UAT8 — Digital Channel
Row Toggle** (2026-08-19) — see
[MIGRATION_PLAN.md — Phase 4A-UAT8 Record](MIGRATION_PLAN.md#phase-4a-uat8--digital-channel-row-toggle-2026-08-19).
Visible digital rows are 100% opacity; hidden rows 25% (rising to ~55%
on hover/focus for discoverability, same as analog). Digital uses a
neutral 10px dark-grey dot (`.channel-color-dot--neutral`, the
`--text-dim` theme token, never `wwColorForChannel()`) — never confused
with an analog trace-color dot. Digital checkboxes and the sidebar's
"Normal state" column are both removed from the UI (the underlying
`normal_state` field is untouched everywhere digital rendering itself
still needs it). **With digital now also a direct row toggle, the shared
"Add N selected"/"Clear selection" workflow had no remaining consumer of
any kind and was removed entirely** — `selectedDigitalChannels`,
`channelSelectionKey()`, `digitalChannelCheckboxHtml()`, the
`.selection-row` HTML/CSS, and the button handlers are all deleted;
`setupSelectionControls()` was renamed `setupChannelRowToggles()` (now
just wires the shared click/keydown row-toggle listeners for both
channel kinds). `ww.digitalDisplayed` (pre-existing) remains the one
digital visibility authority, completely independent of `ww.displayed`
(analog) — confirmed via tests that switching analog layout mode
(Grouped/Separate/Custom) never touches digital visibility, and vice
versa. Triggered/Never Triggered/Spare classification and sort order are
unchanged; hiding a channel never moves it out of its classification
subgroup. The later default-hidden source-open policy is covered by the
Phase 4A-UAT9 fact below. Full frontend regression suite:
still exactly the established 18-failure baseline; backend 321/321
unchanged (no backend file touched). Not yet owner-UAT'd in a real
browser.

`[FACT]` **Waveform channels default to hidden on open; per-group
Show all/Hide all controls added — Phase 4A-UAT9 — Default-Hidden
Channels + Group Visibility Toggles** (2026-08-19) — see
[MIGRATION_PLAN.md — Phase 4A-UAT9 Record](MIGRATION_PLAN.md#phase-4a-uat9--default-hidden-channels--group-visibility-toggles-2026-08-19)
and [DECISIONS.md DEC-038](DECISIONS.md#dec-038--waveform-channels-default-to-hidden-on-open-group-level-showhide-controls-added-phase-4a-uat9).
**Supersedes DEC-034's "display everything by default" experiment** (that
bullet in DEC-034 is now marked superseded in place; the rest of DEC-034
is unaffected). Opening a recording — a genuinely new source or a fresh
workspace — now displays **zero** analog and **zero** digital channels;
no waveform data is fetched merely by opening a source. Every channel row
starts deactivated (`aria-pressed="false"`, 25% opacity via the existing
`.channel-row--hidden` treatment). Each engineering-classification
subgroup (analog: Voltage/Current/Power/Frequency/ROCOF/Undefined/etc.;
digital: Triggered/Never Triggered/Spare) gained a compact "Show all"/
"Hide all" toggle on its own group header, derived live from the existing
per-row `aria-pressed` state — no separate group-selection state exists.
Toggling a group is one batched Plotly update per affected panel, never
one rebuild per channel. Once the engineer manually shows/hides a channel
or group, that choice persists across layout-mode switching, Absolute/
Elapsed switching, and Waveform ↔ Recordings navigation while the same
source stays open (DEC-034/DEC-035's persistence guarantee, unchanged);
only a genuinely new source-open or fresh workspace resets to zero again.
Custom Group membership remains independent of visibility (DEC-035),
unaffected by this change. `ww.sourceDefaultsApplied` and
`wwApplyDefaultChannelDisplay()` were removed entirely. No dedicated
`phase4a_uat9_check.mjs` file was created; coverage is folded into the
existing `phase4a_check.mjs`/`phase4a_uat4_check.mjs`–`phase4a_uat8_check.mjs`
suites. Frontend regression suite: back to exactly the established
18-failure baseline (621 passed) after a follow-up audit resolved fallout
from layering Phase 4A-UAT10's bounds rewrite on top (see that fact below);
backend 328 passed, no backend file touched by this phase. Owner has
completed real-browser UAT.

`[FACT]` **Waveform time bounds are now source-aware — Phase 4A-UAT10 —
Source-Aware Time Bounds** (2026-08-19) — see
[MIGRATION_PLAN.md — Phase 4A-UAT10 Record](MIGRATION_PLAN.md#phase-4a-uat10--source-aware-time-bounds-2026-08-19)
and [DECISIONS.md DEC-037](DECISIONS.md#dec-037--waveform-time-domain-state-is-source-aware-source-bounds-workspace-bounds-and-viewport-are-distinct-phase-4a-uat10).
This fixes the UAT-proven stale-domain bug where a COMTRADE source could
show correct source metadata duration (`7.020 s`) while waveform full/reset
view inherited an older source's shorter extent (`~1.3 s`). Backend
timebase metadata now exposes explicit `elapsed_start_seconds` and
`elapsed_end_seconds` from the retained source time column. Frontend state
is split into `ww.sourceBounds` (source-id scoped native elapsed bounds),
derived `ww.workspaceBounds` (union of currently participating selected/
displayed sources), and `ww.viewport` (user zoom/pan only). `ww.recordBounds`
has been removed; waveform responses no longer become full-record
authority. `Reset Time View` now restores `workspaceBounds`. Opening a
recording establishes source/workspace bounds immediately even when zero
analog and zero digital channels are displayed. Analog and digital displays
share this same derived viewport; neither channel kind is privileged as a
timing authority. This is intentionally synchronization-ready, but no
cross-source timestamp alignment, trigger matching, correlation, manual
offset, or resampling was implemented. **Fully completed**: committed,
pushed, CI green, automatic DEV deployment verified live at the deployed
SHA. A follow-up audit found the frontend regression count had temporarily
risen from the established 18-failure baseline to 34 after this bounds
rewrite landed; 16 were obsolete test expectations (updated) and one was a
genuine bug — `wwClearWorkspace()` incorrectly cleared `sourceBounds` for a
still-open source — fixed in commit `a0da033` ("fix: preserve source
bounds on display clear"). Frontend suite is back to exactly the
established 18-failure baseline (621 passed); backend 328 passed. Owner
has completed real-browser UAT of the BEN5K 7.020 s case and all UAT10
checks passed.

`[FACT]` **A/B time measurement cursors are implemented — Phase 4B — A/B
Time Measurement Cursors** (2026-08-19) — see
[MIGRATION_PLAN.md — Phase 4B Record](MIGRATION_PLAN.md#phase-4b--ab-time-measurement-cursors-2026-08-19)
and [DECISIONS.md DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b).
A/B workspace-level time measurement cursors overlay the entire waveform
stack, including analog, digital, and shared time ruler. Cursor state is
stored in the shared elapsed engineering-time domain; A is blue, B red;
Δt is adaptive-formatted. Implemented as ONE DOM overlay per cursor (plus
a second, sticky-nested segment crossing the ruler) — never a Plotly
`layout.shapes` entry duplicated into every analog panel. Off by default;
first activation places A/B at 1/3 and 2/3 of the current viewport.
Cursor state is global across Grouped/Separate/Custom (owner mid-task
clarification) — a layout-mode switch recomputes only the overlay's pixel
projection, never the stored engineering time. Dragging is DOM-only
(cached plot metrics + `style.left`/textContent writes), never a Plotly
redraw or waveform refetch. Zoom/pan/Reset Time View preserve cursor
engineering time exactly; an out-of-viewport cursor goes off-screen
rather than being silently relocated. Absolute/Elapsed switching changes
only the A/B text, never the underlying time. Cursor mode works even with
zero displayed channels (the readout only needs `ww.viewport`, already
valid per Phase 4A-UAT10 as soon as a source is opened); the visual line
additionally needs a rendered plotting surface to project onto. A
genuinely new source selection (reusing DEC-037's own "fresh viewport"
signal) reinitializes A/B to the new source's 1/3-2/3; re-selecting the
same already-open source does not; "Start New Workspace" resets cursor
state completely, while the plain "Clear workspace" button leaves it
alone. No amplitude/value-at-cursor measurement, sample snapping, or
cursor-linked table was implemented — explicitly out of scope, left for a
future measurement phase to build on this same architecture. New
dedicated `phase4b_check.mjs` (22 checks, scratch convention). Full
frontend regression suite: back to exactly the established 18-failure
baseline (one pre-existing check's assertion about the ruler wrapper's
child count was updated to account for the new, intentional
`#wwCursorRulerOverlay` element). Backend: 328/328 passed, unchanged (no
backend file touched). **Owner UAT passed** — functional behaviour above
fully confirmed in a real browser.

`[FACT]` **Post-UAT cosmetic refinement — thinner A/B lines + range
highlight band** (2026-08-19) — see
[MIGRATION_PLAN.md — Phase 4B Cosmetic Refinement Record](MIGRATION_PLAN.md#phase-4b-cosmetic-refinement--thinner-ab-lines--range-highlight-band-2026-08-19)
(addendum to DEC-039, not its own decision — purely visual, no
architecture/behaviour change). Visible A/B stroke width reduced 2px →
1px (10px drag hit target unchanged). A subtle blue-tinted band fills the
region between A and B — new theme token `--cursor-range-fill`, the same
accent-blue base `--accent-wash` already uses per theme — spanning analog
panels, digital region, and the sticky ruler continuously via the SAME
two-segment overlay the cursor lines already use, shown only when both A
and B are visible, updating live during drag with zero waveform fetches.
**This token's alpha was raised again shortly after** — see the
Phase 4B-UAT1 fact immediately below for the current value.

`[FACT]` **Phase 4B-UAT1 — stronger range highlight + sticky cursor
labels** (2026-08-19) — see
[MIGRATION_PLAN.md — Phase 4B-UAT1 Record](MIGRATION_PLAN.md#phase-4b-uat1--stronger-range-highlight--sticky-cursor-labels-2026-08-19)
(second addendum to DEC-039, not its own decision). `--cursor-range-fill`
raised from ~5% to ~20% alpha at the time — **superseded again, see the
Phase 4B-UAT2 fact below for the current 0.08 value and a fixed bug that
initially made this token appear undefined in DevTools**. The A/B label pills ("[A ×]"/"[B ×]")
are now `position: sticky`, staying visible near the top of the visible
waveform viewport while scrolling a tall waveform stack — the vertical
cursor lines themselves remain full-height and non-sticky, unchanged
(only the label became viewport-relative, never the engineering cursor
or its line). Structurally, the label markup moved out of
`#wwCursorOverlay` (`overflow: hidden`, incompatible with sticky escaping
to the real `#activeViewArea` scroll container) into a new sibling,
`#wwCursorLabelLayer`, living directly inside `.workspace-section`
(`overflow: visible`). Both the line overlay and the new sticky label
layer are driven by the identical `wwCursorTimeToPixelX()` projection —
no second horizontal-positioning implementation. Dragging from the label
and the individual × close buttons continue to work unchanged (same
pointer-capture/live-update path, now wired to both
`#wwCursorOverlay`/`#wwCursorLabelLayer`). No manual scroll listener was
added — CSS `position: sticky` only. `phase4b_check.mjs` extended to 37
checks (from 29); full frontend suite still exactly the established
18-failure baseline; backend 328/328 unchanged.

`[FACT]` **Phase 4B-UAT2 — cursor range-fill + full-scroll line
continuity bug fixes** (2026-08-20) — see
[MIGRATION_PLAN.md — Phase 4B-UAT2 Record](MIGRATION_PLAN.md#phase-4b-uat2--cursor-range-fill--full-scroll-line-continuity-fix-2026-08-20)
(third addendum to DEC-039, not its own decision). Two owner-confirmed
bugs in Phase 4B-UAT1's own work, fixed. **Bug 1** — DevTools showed
`--cursor-range-fill` as undefined. Investigation found the source
declaration and the live-deployed `theme.css` were both byte-correct
(re-verified via a jsdom test exercising the real CSS cascade engine,
`getComputedStyle(realElement).getPropertyValue(...)`, not source-text
matching) — no code-level bug found; the best-supported explanation is
browser-side caching of a stale pre-Phase-4B-cosmetic-refinement copy of
`theme.css` (no cache-busting exists on that static asset reference),
flagged to the owner as an out-of-scope possible follow-up rather than
fixed unilaterally. `--cursor-range-fill` is now, current value,
**`rgba(53,104,212,0.08)` (Light) / `rgba(79,141,253,0.08)` (Dark)** — the
owner's final acceptance target after three rounds (0.05 → 0.20 → 0.08).
**Bug 2** — cursor lines disappeared further down a tall (e.g. Separate
mode) waveform stack while sticky labels stayed correct. Root cause: the
overlay height was computed from two `getBoundingClientRect()` values
(viewport-relative), and `#wwStickyRuler`'s (`position: sticky`) current
on-screen paint position diverges from its true scroll-content position
once pinned. Fixed by reading `rulerWrapEl.offsetTop` instead — a stable
layout metric immune to scroll position and to sticky's paint-time
displacement. The A-B range band, living inside the same corrected
overlay, is fixed by the same change. **This geometry fix, on its own,
turned out to be necessary but not sufficient — see the Phase 4B-UAT3
fact immediately below, which is the current, complete state.**
`phase4b_check.mjs` extended to 43 checks (from 37); full frontend suite
still exactly the established 18-failure baseline; backend 328/328
unchanged.

`[FACT]` **Phase 4B-UAT3 — fix for A/B main cursor lines disappearing
after vertical scroll (Phase 4B-UAT2 alone did not fully resolve this)**
(2026-08-20) — see
[MIGRATION_PLAN.md — Phase 4B-UAT3 Record](MIGRATION_PLAN.md#phase-4b-uat3--fix-ab-main-cursor-lines-disappearing-after-vertical-scroll-2026-08-20)
(fourth addendum to DEC-039, not its own decision). Owner real-browser
UAT of Phase 4B-UAT2 found its `offsetTop` geometry fix necessary but not
sufficient: with cursor mode already ON in a tall (Separate-mode,
many-channel) stack, scrolling deep into the waveform made the MAIN
vertical lines disappear while the sticky A/B labels and the ruler's own
A/B segments (separate rendering paths) stayed correct — and toggling
cursor mode OFF then ON reliably restored the lines immediately. Since
scrolling alone triggers no application code by design, and OFF→ON's only
meaningfully different action is re-invoking `wwUpdateCursorOverlay()`
(reassigning line/range `style.left`/`style.height`, even where the
numeric value is unchanged), the most consistent explanation is a browser
paint/compositing staleness for this `overflow: hidden`,
absolutely-positioned overlay as its scrolling ancestor moves — not a DOM
geometry error (Phase 4B-UAT2's `offsetTop` fix is retained, unchanged,
and confirmed still correct). No real browser was available in this
sandbox to directly confirm the exact paint mechanism; this is disclosed
as reasoned analysis, not an observed fact. Fix: a `scroll` listener on
`#activeViewArea`, rAF-coalesced like the existing window-resize handler,
re-invokes the same proven `wwUpdateCursorOverlay()` pass — a deliberate,
owner-authorized exception to the original "prefer CSS sticky, no scroll
listener" preference, gated to a no-op whenever cursor mode is disabled,
performing only cheap DOM/CSS writes (never Plotly, never a waveform
fetch). `phase4b_check.mjs` extended to 45 checks (from 43); full
frontend suite still exactly the established 18-failure baseline; backend
328/328 unchanged. **Known test limitation, disclosed**: jsdom cannot
observe real paint/compositing, so only the lifecycle gap (scroll now
re-syncs geometry) and the performance contract are verified here —
real-browser owner UAT remains authoritative for the visual symptom.

`[FACT]` **Phase 4C1 — A/B cursor channel values (Cur A / Cur B)**
(2026-08-20) — see
[MIGRATION_PLAN.md — Phase 4C1](MIGRATION_PLAN.md#phase-4c1--ab-cursor-channel-values-cur-a--cur-b-2026-08-20)
and
[DEC-040](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1).
The first VALUE measurement built on the DEC-039 cursor-time overlay: the
Channels sidebar's analog table gained two new compact columns, "Cur A"
and "Cur B", showing each displayed channel's recorded value at cursor
A/B — a generic channel Y-axis value, agnostic to whether the channel
represents an instantaneous waveform, RMS, frequency, power, or anything
else (same-day owner clarification of this phase's original
"Instantaneous Cursor Values" working title; a code audit confirmed the
implementation never branched on `engineering_type`, so no production
code changed, only terminology/docs — see the DEC-040 addendum). Values
are always computed backend-side
(`extract_cursor_values()`, `app/services/waveform_service.py`) from the
source's true full-resolution `waveform_data` at the nearest actual
sample (binary search, documented earlier-sample tie-break, never
interpolated, never clamped across a source's own bounds) — never from a
Plotly trace or a downsampled display representation, so a chart can show
a reduced envelope while Cur A/B still reports the real underlying
sample. One new batched endpoint, `POST
.../sources/{source_id}/cursor-values` (`app/api/v1/sources.py`,
`app/schemas/cursor_values.py`) — always one request per source covering
every currently-displayed analog channel for it, never one request per
channel. Frontend: new `ww.cursorValues` cache (pure derived state,
`ww.measurementCursors` from DEC-039 remains the one cursor-time
authority); `wwCurValueText()` is the single gating function every render
path uses, forcing "—" whenever cursor mode is off, that cursor is
closed, or the channel is hidden; live dragging is throttled (~50ms
leading+trailing) with per-source generation-counter stale-response
protection and one guaranteed unthrottled request on `pointerup`; hooked
into the existing channel-visibility "core mutation" functions
(`wwAddSelectedChannels()`/`wwRemoveChannel()`/`wwRemoveChannelsByKeys()`)
so individual toggles and group Show-all/Hide-all both get correct
batched fetch/clear behavior with no separate hook needed. Digital
sidebar unchanged — no Cur A/B columns added to digital channels this
phase. RMS, angle, delta angle, ΔY, interpolation, on-canvas annotations,
cross-source synchronization, resampling, and phasor calculation are all
explicitly deferred. Backend: 27 new tests (18 service-level + 9
API-level), full suite 355/355 passing. Frontend: new `phase4c1_check.mjs`
(26 checks, covering formatting, all four gating conditions, batching,
multi-source identity/bounds, drag throttling/stale-response protection,
layout-mode independence, Absolute/Elapsed and zoom/pan non-refetch,
source-switch and Start New Workspace clearing, and digital
non-interference); full frontend regression suite reconfirmed at exactly
the established 18-failure baseline (two pre-existing Phase 4A-UAT4/UAT5
column-count assertions were updated in place to expect the new 4-column
analog table, since the extra columns are this phase's own intended
change).

`[FACT]` **Phase 4C2 — Digital A/B cursor state** (2026-08-20) — see
[MIGRATION_PLAN.md — Phase 4C2](MIGRATION_PLAN.md#phase-4c2--digital-ab-cursor-state-2026-08-20)
and
[DEC-040's second addendum](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1).
Extends Phase 4C1's A/B cursor channel values to digital channels: every
displayed digital channel now shows its recorded state (0/1) at Cursor A
and Cursor B as compact inline "A:0 B:1" badges appended to the existing
Channel cell — deliberately NOT a full-width Cur A/Cur B column like
analog's own (owner's explicit instruction). Investigation confirmed
digital channels are stored the SAME way analog channels are — a dense,
per-sample column in the shared `waveform_data` DataFrame, sharing the
same `"time"` array — so digital state reuses the exact same
`_nearest_sample_index()` nearest-actual-sample search Phase 4C1 already
built, with no separate transition-interval-search algorithm;
`extract_digital_waveform`'s own sparse transition list is a DERIVED,
display-oriented representation of that same dense data, not a second
source of truth. The exact-transition-timestamp rule ("state at T = the
NEW state beginning at T") falls out for free from this — no
special-casing needed. Backend: `POST .../sources/{source_id}/cursor-values`
(same endpoint, not a new one) extended with `digital_channel_names`
alongside the renamed `analog_channel_names` (was `channel_names` — a
clean rename, internal-only API); one source's request still costs
exactly one pair of resolved indices regardless of channel kind mix.
Frontend: new `ww.digitalCursorValues` (a deliberately SEPARATE Map from
analog's `ww.cursorValues` — never a shared key space, so an analog
`0.0` and digital `0` can never collide); `wwFetchCursorValuesForSource()`
now sends analog AND digital channel names together in ONE request per
source; hooked into digital's own existing "core mutation" functions
(`wwAddDigitalChannels()`/`wwRemoveDigitalChannelByKey()`/
`wwRemoveDigitalChannelsByKeys()`/`wwRemoveChannelsForSource()`'s digital
branch) mirroring Phase 4C1's analog hook pattern exactly; mode OFF/
individual cursor closed/drag throttling all reuse Phase 4C1's existing
shared mechanisms — no second throttle, no second stale-response
protection. Neutral badge styling only (no red/green, no alarm/healthy
implication — digital semantics vary by signal); Triggered/Never
Triggered/Spare classification (DEC-034) is completely unread/unaffected
by this measurement. Backend: 19 new tests (12 service-level including
the exact-transition-timestamp rule on both edges, 7 API-level using
synth_ascii's own real BRK_A/BRK_B digital channels), full suite 374/374
passing. Frontend: new `phase4c2_check.mjs` (24 checks); full frontend
regression suite reconfirmed at exactly the established 18-failure
baseline, and Phase 4C1's own `phase4c1_check.mjs` (26 checks) still
passes fully after updating its mock to the renamed request field.

## Completed foundation work

`[FACT]`, verified against the repository on 2026-08-15:

- **Backend** (`backend/app/`): a FastAPI application (`main.py`) built via
  `create_app()` factory, with:
  - `/health`, and a versioned COMTRADE source/channel/waveform API:
    `POST/GET /api/v1/workspaces/{workspace_id}/sources`,
    `GET/DELETE /api/v1/workspaces/{workspace_id}/sources/{source_id}`,
    `GET .../sources/{source_id}/channels`,
    `GET .../sources/{source_id}/waveform` (**new, Phase 2A** — bounded
    time-range analog waveform data for one channel, peak-preserving
    display reduction when needed — see DEC-019), and a whole-workspace
    lifecycle endpoint: `DELETE /api/v1/workspaces/{workspace_id}`
    (`app/api/v1/workspaces.py`) — releases every source the workspace
    owns in one call; idempotent for an unknown/already-empty workspace.
  - `domain/` — `DisturbanceRecord`/`AnalogChannel`/`DigitalChannel`/
    `RecordingMetadata`/`SamplingInformation`/`TimingInformation` ported
    near-verbatim from `powerwave` (commit `3156392`); `SourceMetadata`/
    `AnalogChannelSummary`/`DigitalChannelSummary` for the lightweight
    metadata the API returns; `channel_classification.py` — the
    backend-owned, three-tier analog engineering-type classifier
    (`Voltage`/`Current`/`Power`/`Frequency`/`ROCOF`/`Undefined`); `ActiveSource`
    (**new, Phase 2A**) — pairs `SourceMetadata` with the authoritative,
    full-resolution `DisturbanceRecord`, now retained for the source's
    lifetime (see DEC-019); `waveform_reduction.py`
    (**new, Phase 2A**) — the peak-preserving min/max envelope display-reduction
    algorithm, deliberately not `powerwave`'s own plain stride-sampling
    decimator (see the Phase 2 design section's §3/§13 findings).
  - `providers/` — `BaseProvider`/`ProviderManager` and `ComtradeProvider`
    ported near-verbatim from `powerwave`, **untouched by Phase 2A**.
    CSV/Excel providers are Phase 1.5 scope, not present yet (see
    DECISIONS.md DEC-014).
  - `services/` — `WorkspaceRegistry` (in-memory, ephemeral, keyed by
    `workspace_id`/`source_id` — see DEC-012), storing `ActiveSource` since
    Phase 2A (was `SourceMetadata`-only; keying/locking/cleanup methods
    unchanged), with `remove_workspace(workspace_id)` (DEC-018) releasing
    every source (including its retained record) a workspace owns in one
    call; `import_service.py` (upload validation, size-limit enforcement,
    ephemeral parse via a per-request `tempfile.TemporaryDirectory()`,
    metadata extraction including engineering-type classification, and —
    Phase 2A — retaining the parsed record via `ActiveSource`);
    `waveform_service.py` (**new, Phase 2A**) — exact time-range
    extraction from the authoritative record, then display reduction only
    when the range exceeds the requested point budget.
  - `schemas/` — Pydantic response DTOs (`SourceSummaryOut`,
    `SourceChannelsOut`, etc.) — never include waveform/sample arrays.
    `AnalogChannelOut` still carries `scale`/`offset` (API/domain
    unchanged); the frontend's primary table just stopped displaying them.
    `waveform.py` (**new, Phase 2A**) — `WaveformRangeOut`, the one
    deliberate exception to "never include waveform arrays," always
    bounded (full-resolution only when already small enough; a display
    representation otherwise).
  - CORS middleware and a Content-Length pre-check middleware (fast-path
    upload-size rejection) configured from `Settings`.
  - Storage abstraction (`storage.py`, unchanged) — **not used for event
    files** — see DEC-015: uploaded `.cfg`/`.dat` files are never
    persistently retained anywhere. (Unaffected by Phase 2A's *in-memory*
    record retention — see DEC-019's note on DEC-015.)
  - Configuration (`config.py`): `MAX_EVENT_UPLOAD_SIZE_MB` (default 100 —
    an MVP operating assumption, not a hard limit; see DEC-016).
  - Dependencies: `fastapi`, `uvicorn`, `python-multipart`, `numpy`/`pandas`
    (pinned to match `powerwave`'s own versions), `psycopg[binary]` (still
    unused, pinned for later). **No new dependency was added for Phase 2A**
    (no charting/binary-serialization/Arrow library — JSON-first, per
    DEC-019).
  - Tests: **278 passing** (`backend/tests/`) — up from 227: 51 new
    (`test_waveform_reduction.py` 17, `test_waveform_service.py` 17,
    `test_waveform_api.py` 17, including the mandatory synthetic-spike
    regression test and a weakref-based lifecycle-cleanup test), plus the
    original foundation suite, COMTRADE provider/parity tests (verified
    against `powerwave`'s canonical provider, **unchanged this pass**),
    workspace-registry tests (updated to build `ActiveSource` fixtures,
    no assertions weakened), full API tests, and
    `test_channel_classification.py`. Synthetic COMTRADE fixtures live in
    `backend/tests/fixtures/comtrade/` — authored for this migration, not
    derived from any real/confidential event data.
- **Frontend** (`frontend/index.html`): a single-page upload/channel-browse
  UI. Per completed UAT: the two-slot `.cfg`/`.dat` upload, loading
  indicator, 100 MB guidance, and source-metadata-review step are
  **approved and unchanged** (DEC-017 formally approves the upload
  interaction specifically). Refined this pass: collapsible Analog
  (default open)/Digital (default collapsed) channel groups with counts;
  analog channels sub-grouped by `engineering_type` (backend-computed,
  never re-derived in JS); a client-side channel search (name/unit/phase,
  no network calls, auto-expands groups containing a match); Scale/Offset
  removed from the primary analog table; a confirmation dialog before
  source removal; and a fix so the import-success banner clears only when
  it actually described the just-removed source. Added this pass:
  `Start new workspace` now calls the backend's whole-workspace DELETE
  endpoint (with its own confirmation dialog, shown only when the
  workspace is non-empty) and only rotates the client-side `workspace_id`
  after that call succeeds; a failed cleanup leaves the old workspace,
  its source list, and its banner untouched and shows a visible error
  instead. `frontend/waveform-prototype.html` — an isolated single-channel
  waveform preview (not part of the main channel-browse screen), driven
  entirely by the existing Phase 2A waveform API; one "Waveform (UAT)"
  link per analog channel row in `index.html` is the only integration
  point. **Started as a Phase 2B side-by-side uPlot/Plotly comparison,
  now closed**: following the owner's UAT (DEC-022), **Plotly.js is the
  selected and only renderer** — uPlot's adapter, its vendored assets, and
  the renderer-switch UI were removed; `frontend/vendor/plotly/` is now
  the only vendored library. Plotly's native axis spike-lines
  (`showspikes`/`spikesnap: "data"`/`spikemode: "across"`) provide the
  hover crosshair, restyled at Phase 2B closure to `spikedash: "dash"` and
  further refined (DEC-023, 2026-08-15) to `spikethickness: 0.5` (down
  from `1`) and a further-reduced `spikecolor` alpha (`0.42`, down from
  `0.55`); sample-snapping and both vertical/horizontal lines are
  unchanged. The relayout handler correctly triggers a full-record
  re-fetch on Plotly's native Autoscale/Reset-axes buttons; the viewport
  debounce is 120ms; "Reset Time View" stays terminologically distinct
  from "Autoscale Y" (DEC-021, unweakened). **Light/Dark appearance**
  (DEC-023, 2026-08-15): both `index.html` and `waveform-prototype.html`
  now include shared `frontend/theme.css`/`frontend/theme.js` — Light is
  the default/preferred theme, Dark is user-selectable via a small header
  toggle, the preference persists in `localStorage` and applies
  immediately across both pages (including live cross-tab sync via the
  `storage` event); Plotly's chart colors update via
  `Plotly.relayout`/`Plotly.restyle` on a theme change without refetching
  waveform data. Still no framework, no build step, no routing for the
  main app — that remains an open, undecided question for a later phase.
- **Docker/Compose**: unchanged — `compose.yaml` +
  `compose.dev.yaml`/`compose.prod.yaml`, DEV/PROD isolation verified in CI.
- **CI/CD**: unchanged (`.github/workflows/{ci,deploy}.yml`) — used as-is
  (via `workflow_dispatch`) to deploy this work to DEV twice (initial Phase
  1, then this refinement pass).
- **Documentation**: [docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md),
  [docs/development/development-workflow.md](../development/development-workflow.md),
  this project-memory framework, [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md),
  [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) (new, 2026-08-15 — the
  `powerwave`/`detego.app`/owner-authority feature-design reference
  framework, DEC-020), and [MIGRATION_PLAN.md](MIGRATION_PLAN.md) (Phase 0 design, "Phase 1 —
  Implementation Record", "Phase 1 — UAT Refinement Record", "Phase 1 —
  Workspace-Reset Record", "Phase 2 — Waveform Workspace Discovery and
  Design", "Phase 2A — Implementation Record", "Phase 2B — Renderer
  UAT Prototype Implementation Record", "Phase 2B — Plotly
  Refinement & Workspace-Level Navigation Record", "Phase 2B —
  Renderer Closure Record", "Phase 2C — Flexible Multi-Channel
  Waveform Workspace: Discovery and Design", "Light/Dark Theme &
  Crosshair Refinement Record", "Phase 2C-A — Synchronized
  Multi-Channel Waveform Display Implementation Record", "Phase 2C-B1 —
  Grouped / Separate Analog Waveform Layout Implementation Record", "Phase
  2C-B2 — Unified Analog Canvas Layout Implementation Record", "Phase
  2C-B3 — Right-Side Compact Lane Labels Implementation Record", "Phase
  2C-B3A — Overlay Right-Side Lane Labels Implementation Record", "Phase
  2C-C1 — Custom Analog Channel Groups Implementation Record", "Phase
  2C-C2 — Adjustable Waveform Panel Heights Implementation Record", and
  "Phase 2C-C2A — Panel Resize Responsiveness Investigation" sections).

## Current architecture status

`[FACT]` The infrastructure follows the principles in
[docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
(read at the source; not duplicated here): frontend/backend separation,
configuration-driven infrastructure, GitHub as the single source of truth.
**Domain architecture now exists for COMTRADE only**: a ported data
contract, a ported provider, a backend-owned channel-classification module,
and an ephemeral-by-design service/API layer with no persistent storage of
event *files* (DEC-015) and no process-global mutable state (DEC-012).
Since Phase 2A (DEC-019), the active workspace's in-memory model
additionally retains each source's full-resolution parsed record
(`ActiveSource`) — an approved, deliberate exception to Phase 1's
metadata-only retention, not a relaxation of DEC-015 (which governs the
uploaded *file*, untouched). CSV/Excel, synchronization, calculated
signals, and analytics remain reference-only in `powerwave`, not yet
ported.

## Repository identity

`[FACT]`, verified 2026-08-14 via `git remote -v` in each local clone:

- `oruxa_powerwave` (this repo): `git@github.com:myza81/oruxa-powerwave.git`
  (SSH), branch `main`.
- `powerwave` (reference desktop app, macOS clone at
  `/Volumes/externalDrive/code-gym/powerwave/`): `https://github.com/myza81/powerwave.git`
  (HTTPS), branch `main`, at commit `3156392` (unchanged this phase); one
  pre-existing untracked 0-byte file (`Make`) remains, still untouched.

These are two distinct GitHub repositories. See
[README.md — Repository identity](README.md#repository-identity--do-not-confuse-the-two-projects)
for the full rule against confusing them.

## Known infrastructure

`[FACT]`:

- DEV: `https://dev.powerwave.oruxa.uk` (frontend), `https://api.dev.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave-dev`, ports 8200/8201. **This
  is where the Phase 1 COMTRADE workflow, including this refinement pass, is
  actually running** — verified live, see [HANDOFF.md](HANDOFF.md).
- PROD: `https://powerwave.oruxa.uk` (frontend), `https://api.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave`, ports 8100/8101. **Still
  serving the pre-Phase-1 placeholder build** — Phase 1 has not been
  deployed to PROD, deliberately (not requested; DEV-only per every Phase 1
  task so far).
- See [docs/development/development-workflow.md](../development/development-workflow.md)
  for the full deployment workflow.

## Major currently available components

`[FACT]`: FastAPI backend with a working, UAT'd COMTRADE upload → parse →
classify → channel-browse API (no persistent storage of event *files*),
plus (Phase 2A) a bounded, peak-preserving waveform range API serving one
analog channel at a time from a retained full-resolution record, storage
abstraction (unused by the event-file path), CI/CD pipeline, DEV/PROD
deployment isolation, a working single-page frontend with
collapsible/searchable channel grouping and a removal confirmation, plus
(Phase 2B) an isolated renderer-UAT prototype page comparing uPlot and
Plotly.js against that same waveform API, (DEC-023) a shared Light/
Dark appearance system applied across the whole frontend including the
Plotly chart, and (Phase 2C-A/B1, DEC-024/DEC-025) a real synchronized
multi-channel waveform workspace — checkbox channel selection, initial
engineering-type panel grouping, one Plotly instance per panel sharing
one workspace-level X/time viewport, a central Zoom/Pan/Reset-Time-
View/Autoscale-Y toolbar, and a Grouped/Separate layout toggle (Separate
= one panel per displayed channel, switchable without losing the
displayed channel set or the current zoomed viewport) — built into the
main app itself, this documentation set. **(Phase 2C-B2, DEC-026)**
Separate mode now visually presents as one unified analog canvas (shared
outer frame, borderless/hairline-divided lanes, a maximum-width chart
column per lane, only the bottom lane shows the shared time axis) — each
lane still keeps its own independent Y axis; Grouped mode's own visual
presentation is unchanged. **(Phase 2C-B3A, correcting Phase 2C-B3)** The
Separate-mode lane label is now a small compact pill/tag **overlaid
directly on the waveform lane itself** near its right edge, vertically
centered (Detego's own separate-waveform label placement used as the
explicit layout benchmark for this treatment) — not a dedicated right-side
layout column (Phase 2C-B3's own approach, since superseded). The
waveform chart fills the full lane width; Oruxa theme tokens are
unchanged. **(Phase 2C-C1, DEC-027)** A third layout mode, **Custom**,
lets the user manually decide which displayed analog channels share a
waveform panel via a new Edit Channel Groups dialog (create groups,
assign/unassign channels, Apply/Cancel) — Detego's own "Edit Channel
Groups" workflow used as the explicit layout/workflow benchmark, no
branding/styling copied. Any channel left unassigned automatically
becomes its own single-channel panel (the documented rule — Apply is
never blocked on complete assignment); the last-applied custom grouping
persists across mode switches within the current workspace/session.
**(Phase 2C-C2, DEC-028)** Every waveform panel/lane, in all three layout
modes, is independently resizable by dragging a bottom-edge handle
(Detego's own vertical panel-resize interaction named as the UX
benchmark, no branding/styling copied) — clamped 100–600px, presentation-
only (zero waveform refetches, no viewport/Y-range reset), height kept as
explicit state keyed by the same panel-derivation identity so a panel's
height survives round-tripping back to the same mode without any
cross-mode mapping. No frontend framework, no database schema, no
authentication, no CSV/Excel/digital-waveform/cursors-measurements/
calculated-signal/synchronization features yet; **direct drag/reorder of
panels and drag-to-overlay/group by direct lane dragging remain not yet
built** (the owner's own choice to pursue Custom Groups and then panel
resize first, not an oversight). A Phase 2 waveform-workspace **design
proposal** exists (see [MIGRATION_PLAN.md](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)),
and the Phase 2C flexible multi-channel workspace **design proposal**
(see [MIGRATION_PLAN.md — Phase 2C](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15))
has now had its core architecture (panel model, channel-add workflow,
shared viewport, minimal toolbar, viewport-aware Autoscale Y) implemented
as Phase 2C-A (DEC-024), and its own previously-open grouping-mode
question (§9, "whether several related channels should ever share one
panel by user choice") fully resolved: Grouped/Separate (Phase 2C-B1,
DEC-025), and Custom — Detego's own third grouping mode, at the time
explicitly deferred — now also implemented (Phase 2C-C1, DEC-027). The
backend foundation (Phase 2A), the renderer choice (Phase 2B, DEC-022),
and all three multi-channel layout slices (Phase 2C-A/DEC-024, Phase
2C-B1/DEC-025, Phase 2C-C1/DEC-027) are all implemented/decided, and
adjustable panel heights (Phase 2C-C2/DEC-028) are now implemented across
all three. Direct drag/reorder of panels, drag-to-overlay/group by direct
lane dragging, Proportional Y scaling, mixed-unit handling, and
digital-channel display remain unbuilt/undecided design-proposal items
(`[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`) — the owner's
own choice, across these passes, to pursue Custom Groups and panel resize
ahead of drag/reorder.

## Current approved focus

`[FACT]` Phase 1 (COMTRADE-only) is implemented, deployed to DEV, UAT'd,
refined per that UAT, and has had its whole-workspace reset lifecycle
corrected — see
[MIGRATION_PLAN.md — Phase 1 Implementation Record](MIGRATION_PLAN.md#phase-1--implementation-record-2026-08-14),
[Phase 1 — UAT Refinement Record](MIGRATION_PLAN.md#phase-1--uat-refinement-record-2026-08-14),
and
[Phase 1 — Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14).
Phase 2A (backend waveform data foundation) and Phase 2B (renderer UAT,
refinement, and closure) are all implemented — see
[MIGRATION_PLAN.md — Phase 2A](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15),
[Phase 2B Implementation](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15),
[Phase 2B Refinement](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15),
and
[Phase 2B Closure Records](MIGRATION_PLAN.md#phase-2b--renderer-closure-record-2026-08-15).
`[DECISION]` Recorded earlier: DEC-019 — the active workspace retains
each source's full-resolution `DisturbanceRecord`, delivered only via
bounded time-range requests with peak-preserving (never naive-stride)
display reduction when needed; JSON-first transport for Phase 2A.
Recorded previously: `Start new workspace` is a distinct whole-workspace
lifecycle operation, backend-enforced (DEC-018); the two-slot COMTRADE
upload interaction is formally approved (DEC-017, resolves UAT-1). No new
architectural decisions were needed for the grouping/search/confirmation
refinements themselves — implementation detail, not decided direction (per
governance, not written to DECISIONS.md). `[DECISION]` Recorded
2026-08-15: **DEC-021** — waveform navigation is workspace-level (one
shared X/time viewport across every displayed channel, never
channel-level); a centralized Powerwave toolbar (not per-channel native
modebars) is the required future architecture; "Reset Time View" and
"Autoscale Y" are distinct operations, never collapsed. `[DECISION]`
Recorded 2026-08-15: **DEC-022** — **Plotly.js is selected as the
waveform rendering foundation**; uPlot was evaluated and is not used
going forward (removed from the codebase). This closes the plotting-
library `[UAT]` — it is no longer open. **Not decided by any of the
above**: channel-selection/add interaction, panel layout, drag/reorder
panel UX, digital waveform handling, and abandoned-session TTL policy —
all remain `[UAT]`/`[COMPARISON]`/`[OPEN]`.

`[FACT]` Recorded 2026-08-15: **Phase 2C discovery/design is complete —
design only, nothing implemented** — see
[MIGRATION_PLAN.md — Phase 2C Flexible Multi-Channel Waveform Workspace:
Discovery and Design](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15).
Re-verified `powerwave`'s live multi-channel/panel behavior directly (a
genuinely new finding: `powerwave` already has live channel-to-panel drag,
but no panel-reordering mechanism at all anywhere in the codebase —
flagged as the single clearest opportunity for Oruxa to exceed both
`powerwave` and Detego at once), and consulted Detego's own public
documentation (per DEC-020's benchmark framework — no proprietary
code/assets inspected) for its waveform viewer's channel grouping/toolbar/
cursor/Y-scaling behavior. Produced a full `[PROPOSAL]`-level design: the
panel abstraction (shared X inherited from DEC-021, independent Y per
panel), an `engineering_type` auto-grouping default that never permanently
constrains placement, a drag/reorder model, a recommended
one-independent-Plotly-instance-per-panel architecture (extending Phase
2B's already-proven relayout-broadcast/stale-request-protection mechanism
rather than fighting Plotly's native multi-subplot domain math), a
Fit-vs-Proportional Y-scaling model (deliberately viewport-aware — an
explicit, evidenced improvement over `powerwave`'s own stale
full-session-window autoscale), and a recommended implementation slicing.
**Nothing here is a `[DECISION]`** — every substantive choice remains
`[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`/`[DEFER]`; DEC-021
and DEC-022 are reaffirmed unweakened throughout. TTL and the ~100 MB
real-file memory validation were reassessed — neither escalates to a Phase
2C design/first-slice blocker; both remain recommended before Phase 2C
reaches broader/prolonged shared-DEV UAT, unchanged reasoning from Phase
2A/2B. **Phase 2C has not started implementation.**

`[DECISION]` Recorded 2026-08-15: **DEC-023** — the application supports
Light and Dark appearance, Light is the preferred/default direction,
theme is a general application preference (not waveform-page-only), and
Detego was used only as a UI/UX benchmark for this decision — its palette
was not consulted or copied; the light theme is an original Oruxa
palette. Implemented via a shared CSS-token system
(`frontend/theme.css`/`theme.js`) applied coherently across the whole
frontend, including the Plotly waveform chart (colors update on theme
change via `Plotly.relayout`/`Plotly.restyle`, no data refetch). The
Plotly crosshair was further refined (`spikethickness` 1→0.5,
`spikecolor` alpha 0.55→0.42); no custom crosshair/cursor engine was
built. This is a general-app UX refinement, **not** Phase 2C — see
[MIGRATION_PLAN.md — Light/Dark Theme & Crosshair Refinement Record](MIGRATION_PLAN.md#lightdark-theme--crosshair-refinement-record-2026-08-15).

`[DECISION]` Recorded 2026-08-15: **DEC-024** — Phase 2C-A's multi-channel
waveform workspace architecture is confirmed and implemented: one
independent Plotly instance per panel (never a single figure with fixed
subplots); checkbox + "Add N selected" as the approved channel-add
workflow; initial-only `engineering_type` panel grouping (never a
permanent lock); one shared, Oruxa-owned X/time viewport driving every
panel (DEC-021, now actually built); a single central 4-button toolbar
(Zoom/Pan/Reset Time View/Autoscale Y) with every native per-panel
modebar disabled; Autoscale Y as viewport-aware Fit only; the existing
Phase 2A single-channel endpoint reused unmodified (N channels = N
requests, no batching). This confirms/selects specific options the Phase
2C design pass had left as `[PROPOSAL]`/`[ANALYSIS]`/`[NEEDS UAT]` — see
[MIGRATION_PLAN.md — Phase 2C-A Implementation Record](MIGRATION_PLAN.md#phase-2c--synchronized-multi-channel-waveform-display-implementation-record-2026-08-15).
**Phase 2C-B (drag/reorder between panels, panel resize, Proportional Y
scaling, mixed-unit handling, digital channels, shared crosshair) remains
not started and not authorized by this decision.**

`[DECISION]` Recorded 2026-08-15: **DEC-025** — Grouped/Separate analog
waveform layout modes are confirmed and implemented (Phase 2C-B1),
resolving the Phase 2C design record's own previously-open "should
several channels ever share one panel by user choice" question: Grouped
(existing `engineering_type` default) and Separate (one panel per
channel) are both available via a small toolbar toggle; **Custom** mode
is explicitly not built. Switching modes never changes which channels are
displayed, never issues a new waveform request, and preserves the current
shared X/time viewport exactly — verified by test. The panel data model
(displayed channels + panels + channel membership + panel order) was
kept general specifically so a future direct vertical-drag/reorder/
overlay/split interaction (the owner's stated next direction) doesn't
require restructuring it — see
[MIGRATION_PLAN.md — Phase 2C-B1 Implementation Record](MIGRATION_PLAN.md#phase-2c-b1--grouped--separate-analog-waveform-layout-implementation-record-2026-08-15).
**Direct drag/reorder, drag-to-overlay/group, drag-out-to-separate, and
Custom layout mode remain not started and not authorized by this
decision.**

`[DECISION]` Recorded 2026-08-15: DEC-020 — `detego.app` is adopted as an
official product/UI-UX/waveform-workspace/dashboard/workflow **benchmark**
(not a ceiling, not a spec to copy blindly) for feature design, especially
Phase 2B/2C waveform-workspace work. [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)
now quotes the owner-supplied canonical "Detego Benchmark Principle"
verbatim (three-way hierarchy: `powerwave` = engineering behaviour,
`detego.app` = UI/UX benchmark, owner requirements/DECISIONS/UAT = final
authority). `oruxa_powerwave` should aim to become more capable and
useful to engineers than Detego where justified; if Detego lacks a
capability the owner requires, do not omit or weaken it just to stay
consistent with Detego. No technical audit of `detego.app` has been
performed — this decision establishes the reference relationship and its
limits, not a feature comparison. Documentation-only; no production code
changed.

`[FACT]` Recorded 2026-08-15 (same day, third pass): [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)
was expanded with a four-way feature-design method (`powerwave` /
Detego / owner requirements / proposed superior Oruxa approach),
worked examples (waveform workspace, multi-source synchronization,
calculated signals), an explicit "owner-specific capabilities may exceed
Detego" list, and explicit "architecture stays Oruxa-owned" /
"independent implementation, not reverse engineering" sections. This is
elaboration and documentation of the already-approved DEC-020, not a new
decision — no new `DECISIONS.md` entry was added for this pass, per
governance (only add a decision entry for something not already
captured). Phase 1 and Phase 2A content were not touched.

## Known blockers

- `[FACT]` The `origin` remote's configured SSH URL for `oruxa_powerwave`
  is not authenticated in these sandboxed sessions — established,
  repeatable workaround (explicit HTTPS push URL) documented in
  [HANDOFF.md](HANDOFF.md). Not an open blocker.
- `[OPEN]` A genuinely disk-free (zero temp-file-touch) upload/parse path
  remains unimplemented — judged disproportionate per the "don't rewrite
  proven engineering logic" principle. Unchanged this pass; full
  investigation in [HANDOFF.md](HANDOFF.md) / [MIGRATION_PLAN.md](MIGRATION_PLAN.md).
- `[OPEN]` **Partially informed this pass, still not fully closed**: no
  measurement was taken against an actual ~100 MB COMTRADE file itself
  (only up to ~16 MB, and Phase 2A's own benchmarking used synthetic data
  at comparable sample counts, not a real 100 MB file). Phase 2A did
  establish a precise, measured ratio for *parsed* memory scaling at the
  DataFrame level: COMTRADE binary analog samples (2-byte integers on
  disk) become 8-byte `float64` once parsed — a measured 4x expansion;
  digital channels (packed bits on disk) become 1-byte `int8` per
  channel — an 8x expansion. See
  [MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15)'s
  memory-model measurements. Extrapolating from these ratios, a 100 MB
  file could still plausibly use several hundred MB to 1+ GB of resident
  memory during/after parsing, but this remains an estimate, not a direct
  measurement — closing it fully would need an actual near-100-MB fixture
  run through the real parser.
- `[OPEN]` The long-term persistence architecture (for whatever eventually
  needs to survive a session — not event files, permanently ephemeral per
  DEC-015) remains undecided. Deferred to Phase 8.
- `[OPEN]` Remaining discovery engineering-improvement findings
  (COMTRADE discontinuity detection, raw timestamp traceability,
  timing-mode enforcement, duplicate CSV/Excel classifiers, calculated-signal
  grammar, frequency/ROCOF computation, the suggestions feature) are
  unchanged — see
  [MIGRATION_PLAN.md — Review of the nine discovery open questions](MIGRATION_PLAN.md#review-of-the-nine-discovery-open-questions).
- `[OPEN]` Whether to commit a larger/richer set of real-event parity
  fixtures for stronger ongoing regression coverage — unchanged, still not
  resolved.
- `[OPEN]` **Elevated in severity this pass**: explicit `Start new
  workspace`/`Remove` cleanup is correct (DEC-018), but an *abandoned*
  workspace — browser tab closed, network lost, or the user simply never
  clicks either — still has no automatic expiry/TTL. `WorkspaceRegistry`
  entries in that case live in memory until the backend process restarts.
  Since Phase 2A (DEC-019), those entries now include full-resolution
  waveform arrays, not just lightweight metadata — measured at up to
  176 MB per source for a 2,000,000-sample/24-channel synthetic scenario
  (see the Phase 2A Implementation Record's memory-model table) — so
  abandoned sessions now have a materially larger memory consequence than
  in Phase 1. Deliberately still not solved (Phase 2A's task scope was
  explicit-reset correctness and API-level verification, not TTL) — see
  [MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15)
  and DEC-019's Impact section. Should be resolved (a specific policy
  chosen from the Phase 2 design's compared options) before any prolonged
  or shared-DEV waveform UAT — see "Next approved activity" below.
  **Temporary DEV-only operational policy proposed for the Phase 2B UAT
  session specifically** (not a TTL implementation, not a substitute for
  deciding the real policy): the owner's bounded UAT session should end
  with an explicit `Start new workspace` click (already correct, DEC-018)
  to release whatever sources were imported during that session; if DEV
  is used for multiple separate UAT sessions before a real TTL/expiry
  decision is made, restarting the `powerwave-dev` backend container
  between sessions is a safe, simple, fully-effective reset (the registry
  is in-memory only, per DEC-015/DEC-019) that requires no code change.
  This is a documented stopgap for a short, controlled UAT window, not a
  claim that the underlying `[OPEN]` item is solved.

## Next approved activity

`[FACT]` Phase 1 is complete and has passed final owner UAT. Phase 2
waveform-workspace discovery/design is complete. **Phase 2A (backend
waveform data foundation) and Phase 2B (renderer UAT, refinement, and now
closure) are all complete** — see
[MIGRATION_PLAN.md — Phase 2A](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15),
[Phase 2B Implementation](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15),
[Phase 2B Refinement](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15),
and
[Phase 2B Closure Records](MIGRATION_PLAN.md#phase-2b--renderer-closure-record-2026-08-15).
**Plotly.js is the selected waveform renderer (DEC-022)** — no longer
`[UAT]`. Phase 2C discovery/design (flexible multi-channel waveform
workspace) — see
[MIGRATION_PLAN.md — Phase 2C](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15)
— produced a full design proposal, and **its recommended first
implementation slice is now built: Phase 2C-A (DEC-024)** — see
[MIGRATION_PLAN.md — Phase 2C-A Implementation Record](MIGRATION_PLAN.md#phase-2c--synchronized-multi-channel-waveform-display-implementation-record-2026-08-15).
Checkbox channel-add, initial engineering-type panel grouping, one
independent Plotly instance per panel, one shared X/time viewport across
every panel, and a central 4-button toolbar (Zoom/Pan/Reset Time
View/Autoscale Y, viewport-aware Fit only) are all implemented, directly
in `frontend/index.html`. **Phase 2C-A passed its own manual owner UAT**
(synchronization, zoom, pan, Reset Time View, grouping, Autoscale Y all
confirmed working; minor bearable latency and a vertical-zoom-
discoverability note both deliberately deferred), and the owner's
requested next enhancement — waveform layout flexibility — is now also
implemented: **Phase 2C-B1 (DEC-025), a Grouped/Separate layout toggle**
— see
[MIGRATION_PLAN.md — Phase 2C-B1 Implementation Record](MIGRATION_PLAN.md#phase-2c-b1--grouped--separate-analog-waveform-layout-implementation-record-2026-08-15).
Switching layout mode preserves the displayed channel set and the
current shared viewport, and never issues a new waveform request. Phase
2C-B1's own manual UAT passed for synchronization/zoom/pan but flagged
Separate mode's visual layout as not the desired appearance (individually
carded/headed panels rather than one continuous canvas), and the owner's
requested refinement is now also implemented: **Phase 2C-B2 (DEC-026), a
unified analog canvas visual layer for Separate mode** — see
[MIGRATION_PLAN.md — Phase 2C-B2 Implementation Record](MIGRATION_PLAN.md#phase-2c-b2--unified-analog-canvas-layout-implementation-record-2026-08-15).
A shared outer frame replaces N repeated panel cards, lanes are separated
by a hairline divider instead of a card border, and only the bottom-most
lane shows the shared time axis — each lane still keeps its own
independent Y axis, and Grouped mode's own visual presentation is
unchanged. Phase 2C-B2's own manual UAT passed and confirmed the unified-
canvas direction is accepted ("Separate view now feels much better"), and
the owner's next requested refinement — moving the lane label to a small
compact tag on the right side, similar in placement/feel to Detego (used
only as a layout reference) — is now also implemented: **Phase 2C-B3, a
right-side compact label tag for Separate mode** — see
[MIGRATION_PLAN.md — Phase 2C-B3 Implementation Record](MIGRATION_PLAN.md#phase-2c-b3--right-side-compact-lane-labels-implementation-record-2026-08-15).
The existing legend chip (dot + channel name + unit + remove button) moved
from the lane's left edge to its right edge and is now styled as a small
pill using existing Oruxa theme tokens; the waveform column still keeps
maximum width. **This right-side-column placement was still not the
owner's intended layout** — the owner clarified the label must be
overlaid on the waveform lane itself, following Detego's own
separate-waveform label style as closely as practical for this specific
placement, and this correction is now also implemented: **Phase 2C-B3A**
— see
[MIGRATION_PLAN.md — Phase 2C-B3A Implementation Record](MIGRATION_PLAN.md#phase-2c-b3a--overlay-right-side-lane-labels-implementation-record-2026-08-15).
The dedicated grid column was removed; the same label DOM is now
absolutely positioned over the chart area (right-pinned, vertically
centered, `z-index` above the chart) instead of occupying its own layout
space — the chart fills the full lane width. Rather than authorizing the
drag/reorder work that had been flagged as the owner's likely next
direction since Phase 2C-A, **the owner instead chose to skip it for now
and requested Custom Analog Channel Groups** — now implemented: **Phase
2C-C1 (DEC-027), a third layout mode** — see
[MIGRATION_PLAN.md — Phase 2C-C1 Implementation Record](MIGRATION_PLAN.md#phase-2c-c1--custom-analog-channel-groups-implementation-record-2026-08-15).
`[ Grouped ] [ Separate ] [ Custom ]`, with a new Edit Channel Groups
dialog (Detego's own workflow named as the explicit benchmark) letting
the user manually decide channel-to-panel membership; any unassigned
channel automatically becomes its own single-channel panel (the
documented, chosen rule); the last-applied custom grouping persists
across mode switches within the session. **Direct vertical drag/reorder
of panels and drag-to-overlay/group by direct lane dragging remain
explicitly not started and not authorized** — the owner's own choice to
defer them in favor of Custom Groups this pass, along with Proportional
Y scaling, mixed-unit handling, digital channels, and shared crosshair.
Phase 2C-C1's own manual UAT passed ("the Custom Groups workflow is
smooth and easy to understand"), and the owner's next requested
refinement, before digital channels — every waveform panel/lane
independently resizable by dragging — is now also implemented: **Phase
2C-C2 (DEC-028)** — see
[MIGRATION_PLAN.md — Phase 2C-C2 Implementation Record](MIGRATION_PLAN.md#phase-2c-c2--adjustable-waveform-panel-heights-implementation-record-2026-08-15).
Applies uniformly to Grouped/Separate/Custom, via a theme-token-styled
bottom-edge handle (Detego's own vertical panel-resize interaction named
as the UX benchmark), clamped 100–600px, presentation-only (zero
waveform refetches, verified directly), with height kept as explicit
state keyed by the same panel-derivation groupKey so it survives
round-tripping back to the same mode without any cross-mode mapping.
**Direct vertical drag/reorder of panels and drag-to-overlay/group by
direct lane dragging remain explicitly not started and not authorized** —
the owner's own choice to defer them in favor of Custom Groups and then
panel resize, along with Proportional Y scaling, mixed-unit handling,
digital channels, and shared crosshair. Phase 2C-C2's own manual UAT
passed functionally (100–600px accepted as-is), with one bearable,
low-priority observation — a slight live-resize lag — and the owner's
preference for a fix only if low-cost/low-risk led to a focused
investigation, **now complete (Phase 2C-C2A)**: see
[MIGRATION_PLAN.md — Phase 2C-C2A Investigation Record](MIGRATION_PLAN.md#phase-2c-c2a--panel-resize-responsiveness-investigation-2026-08-15).
A small refinement was found justified and applied — decoupling the
cheap DOM height write (now immediate, every pointermove) from the
still-coalesced, comparatively expensive `Plotly.Plots.resize()` call —
with zero change to the 100–600px bounds, the state model, or any
Grouped/Separate/Custom/synchronization behavior (all reconfirmed by
test). **Phase 2C-C2A's owner UAT passed and the resize lag was
reported improved — that issue is closed.** The owner's next requested
feature, before digital channels — COMTRADE time-axis representation —
is now also implemented: **Phase 2C-C3, Absolute/Elapsed time-axis
modes** — see
[MIGRATION_PLAN.md — Phase 2C-C3 Record](MIGRATION_PLAN.md#phase-2c-c3--comtrade-time-axis-modes-2026-08-15).
Absolute Time (real recording timestamp) and Elapsed Time (the
pre-existing 0-based behavior) are both selectable via a compact toolbar
control; Absolute is the new COMTRADE default; Synthetic Elapsed Time
and Sample Index are reserved in the time-mode model but **not**
implemented (for future CSV/Excel timing modes). The shared physical
viewport stays authoritative in elapsed-seconds internally — a mode
switch is presentation-only and never refetches waveform data. Trigger
timestamp does **not** define the elapsed-time origin (confirmed against
real COMTRADE metadata: sample 0 = `start_time`, independent of
`trigger_time`'s offset) unless a future source's own semantics
genuinely require it. Any future multi-source display work will need to
resolve the documented (not fixed) limitation that Absolute-mode labels
currently use only the first-displayed channel's recording-start origin
if channels from different sources were ever combined. **Phase 2C-C3's owner UAT passed** — Absolute Time correct, Elapsed
Time correct, mode switching preserves the physical window. The next
owner-identified usability problem (many displayed channels making the
bottom-only shared time axis invisible while scrolling) is now also
solved: **Phase 2C-C4, a sticky shared waveform time-axis ruler** — see
[MIGRATION_PLAN.md — Phase 2C-C4 Record](MIGRATION_PLAN.md#phase-2c-c4--sticky-shared-waveform-time-axis-2026-08-15).
ONE workspace-level ruler (a lightweight, trace-less second Plotly
instance, reusing Phase 2C-C3's own tick-formatting logic verbatim) now
stays visible near the bottom of the viewport via CSS `position: sticky`
while scrolling through any layout mode, driven entirely by the same
`ww.viewport`/`ww.timeMode` state — confirmed zero new synchronization
loop, zero waveform refetches (including during scrolling itself), and
pixel-aligned tick positions with every panel via a new shared
`WW_PANEL_MARGIN` constant. Separate mode's per-lane axis chrome now
suppresses ticks on every lane (not just the bottom one, now redundant
with the ruler); Grouped/Custom panels' own per-panel axis labels are
deliberately left unchanged this slice — a documented, known
duplication left for a future cleanup pass. **Phase 2C-C4's owner
manual UAT passed functionally.** The next request was cosmetic
only: **Phase 2C-C4A, sticky time-axis title placement and unit
label** — see
[MIGRATION_PLAN.md — Phase 2C-C4A Record](MIGRATION_PLAN.md#phase-2c-c4a--sticky-time-axis-title-placement-and-unit-label-2026-08-16).
A small title now sits at the top of the sticky ruler, above the
ticks: "Record time" (Absolute, fixed) or "Time (ms)"/"Time (s)"/
"Time (min)" (Elapsed, unit-aware, derived from the same shared
decision that also rescales the ruler's own tick values, so title and
ticks can never disagree). The ruler's date-context line simplified to
just the date, since "Record time" now appears as the title just
above it. No timing semantics or synchronization changed; the rescale
is scoped entirely to the ruler's own independent Plotly instance.
**Phase 2C-C4A's visual LAYOUT then failed owner UAT** — the custom
title/date DOM elements above the chart produced a tall, blank-feeling
"information card," not the compact conventional X-axis the owner
wanted (ticks first, small title below, no date in the ruler). Fixed
by **Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction** — see
[MIGRATION_PLAN.md — Phase 2C-C4B Record](MIGRATION_PLAN.md#phase-2c-c4b--compact-sticky-time-axis-layout-correction-2026-08-16).
The custom DOM title/date elements were deleted; the ruler now uses
Plotly's own native `xaxis.title` (the same mechanism every real panel
already uses), which places ticks first and the title below them for
free. Total ruler height dropped from ~63–80px to ~43–45px. Absolute
mode's exact wording is now "Record Time" (capital T); no date appears
in the ruler at all. The Elapsed unit-rescaling logic from Phase
2C-C4A is completely unchanged.
**The owner's next request, ahead of any further waveform-domain
refinement, was the first structural application-layout redesign**:
**Phase 3A — Application Shell Redesign Foundation** — see
[MIGRATION_PLAN.md — Phase 3A Record](MIGRATION_PLAN.md#phase-3a--application-shell-redesign-foundation-2026-08-16)
and [DECISIONS.md DEC-031](DECISIONS.md#dec-031--application-shell-architecture-global-header-full-height-main-sidebar-menu-work-area-workspace-row--bottom-status-bar-phase-3a).
The single centered page is now a full-viewport shell: a full-width
Global Header, a full-height collapsible Main Sidebar Menu, a
drag-resizable contextual Workspace Sidebar, a dominant Main Workspace
(unchanged waveform functionality, just relocated), and a Bottom Status
Bar structurally confined beside Workspace Row only (never beneath Main
Sidebar Menu — the owner's own explicit correction to an earlier, wrong
interpretation). Explicitly an INITIAL shell, subject to UAT-driven
dimension/spacing refinement.
**Phase 3A's shell structure passed owner UAT; one child-layout bug was
found and fixed**: the Plotly waveform canvas did not reflow when the
Workspace Sidebar widened, and could visually overflow its own panel
frame — see **Phase 3A-UAT1 — Responsive Waveform Width Reflow**,
[MIGRATION_PLAN.md — Phase 3A-UAT1 Record](MIGRATION_PLAN.md#phase-3a-uat1--responsive-waveform-width-reflow-2026-08-16).
Root cause: Plotly's own `responsive: true` reliably reacts to
`window` resize, but not to a sibling flex item resizing the container
— the CSS itself already shrank correctly; Plotly was simply never
told to redraw. Fixed with a new `wwResizeAllVisiblePlots()`, called
from Workspace Sidebar drag (rAF-coalesced), Main Sidebar Menu's
`transitionend` event, and window resize — confirmed zero waveform
refetches and a byte-identical physical viewport before/after any
width-only change, in Grouped/Separate/Custom alike. **Phase 3A-UAT1's
width-reflow fix passed owner UAT; that issue is closed.** The owner
then requested one small isolated UI cleanup — **Phase 3A-UAT2 — Remove
Duplicate Header Theme Control** — see
[MIGRATION_PLAN.md — Phase 3A-UAT2 Record](MIGRATION_PLAN.md#phase-3a-uat2--remove-duplicate-header-theme-control-2026-08-16).
The Global Header's own `#themeToggle` Light/Dark control was removed
(it duplicated the Main Sidebar Menu's existing "Settings" item); the
Main Sidebar Menu is now the **single** theme entry point. All
underlying theme mechanics (persistence, cross-tab sync, Plotly
re-color, zero-refetch) are unchanged, confirmed by test. Following that,
an independent Codex overflow/containment audit of the Phase 3A shell
(seven findings, all independently re-verified against canonical `main`
before implementation — none rejected) was addressed by **Phase 3A-UAT3
— Targeted Overflow and Containment Fixes** — see
[MIGRATION_PLAN.md — Phase 3A-UAT3 Record](MIGRATION_PLAN.md#phase-3a-uat3--targeted-overflow-and-containment-fixes-2026-08-16).
Fixed: the responsive Workspace Sidebar reopen button's CSS cascade bug
(it was permanently hidden), channel-table/source-metadata/Custom-Groups-
chip containment at a narrowed (240px) Sidebar or with long COMTRADE-
sourced identifiers, Plotly staleness when returning to Waveform after
the view was hidden behind a Table/Split placeholder, the responsive
drawer width being overridden by a persisted desktop inline width, and
missing containment on Grouped/Custom legend chips (Separate's own
already-UAT'd overlay tag was left untouched). **Owner manual UAT of
Phase 3A-UAT3 found one remaining real overflow case**: uploaded CFG/DAT
filenames in the Channels source-detail section could still visibly
overflow the Workspace Sidebar at narrow widths — fixed by **Phase
3A-UAT4 — Channel Filename Containment** — see
[MIGRATION_PLAN.md — Phase 3A-UAT4 Record](MIGRATION_PLAN.md#phase-3a-uat4--channel-filename-containment-2026-08-16).
Root cause: the flex-item wrapper holding the station name + filenames
never had `min-width: 0` — text-level `overflow-wrap` alone couldn't
help until the box around the text was itself allowed to shrink. Now
fixed (`.detail-header-info` class added with `min-width: 0; max-width:
100%`), filename text wraps fully within the Sidebar at every width
down to 240px, nothing truncated. Following the owner's own "finish this
area before introducing additional features" direction, **Phase 3B —
Recordings Page and Upload Workflow** — is now implemented — see
[MIGRATION_PLAN.md — Phase 3B Record](MIGRATION_PLAN.md#phase-3b--recordings-page-and-upload-workflow-2026-08-16)
and [DECISIONS.md DEC-032](DECISIONS.md#dec-032--recordings-page-as-a-first-class-application-page-one-recording--one-logical-event-cfgdat-sessionworkspace-backed-not-a-persistent-cloud-library-phase-3b).
Recordings is now a first-class Main Sidebar Menu page (alongside the
renamed "Waveform"), with its own upload workflow replacing the old
always-visible sidebar form; see the summary a few paragraphs above for
the full detail. The next step is for the project owner to review Phase
3A-UAT2 through Phase 3B together via live DEV UAT — see the "Owner UAT"
checklist in each task's own final report (header gap, Settings
reachability, Sidebar at 240px with CFG/DAT filenames fully contained,
long source/channel names if available, Grouped/Custom long legends,
narrow-browser behavior around the responsive threshold, sidebar drawer
reopen, Waveform → placeholder → Waveform, no panel overflow, Recordings
page simplicity/readability, the Upload New modal, Open/Analyse, and
Waveform ⇆ Recordings state preservation) — plus the still-open Phase 3A
proportions/dimensions review (Global Header height, Main Sidebar Menu
width in both states, Workspace Sidebar width/resize feel, Main
Workspace dominance, Status Bar geometry) — and either request further
refinement or move on to whichever comes next (digital channels remains
the owner's other previously-stated next area; Table/Split view and real
CSV/Excel parsing remain explicitly not authorized until a separate
request).
Separately, resolving the
abandoned-session TTL question (`[DECISION MODE: COMPARISON]`, reassessed
but not resolved by Phase 2C-A/B1 — neither changes the backend memory-
retention shape) and the ~100 MB real-file memory validation remain
recommended before any further prolonged/shared-DEV waveform UAT.
**Separately, a small general-application UX refinement — Light/Dark
theme support (DEC-023) and a further Plotly crosshair refinement — has
been implemented** (2026-08-15), see
[MIGRATION_PLAN.md — Light/Dark Theme & Crosshair Refinement Record](MIGRATION_PLAN.md#lightdark-theme--crosshair-refinement-record-2026-08-15).
No further theming work is authorized beyond what's described there
(e.g. no settings-page redesign, no additional theme modes) without a
separate request.
Phase 1.5 (CSV/Excel), synchronization, calculated signals, digital
waveform delivery, authentication, and any other later-phase
functionality remain explicitly **not** authorized.
