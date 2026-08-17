# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-17**

## What was most recently done

**Phase 3B-UAT10 — Targeted Scrollbar Track / Divider Fix.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT10 Record](MIGRATION_PLAN.md#phase-3b-uat10--targeted-scrollbar-track--divider-fix-2026-08-17).
No new DECISIONS.md entry.

**Root cause**: Phase 3B-UAT9 already made the scrollbar pseudo-
elements themselves borderless. The remaining visible "rail" was
primarily a transparent scrollbar gutter beside existing real
container/divider borders, especially around `#workspaceSidebar`,
`#mainSidebarMenu`, `.group-editor-box`, and `.group-body`.

**What changed**: the shared Phase 3B-UAT9 baseline in
`frontend/theme.css` stays intact. A narrow local block now gives those
four affected scroll containers local-surface scrollbar tracks:
`#mainSidebarMenu` uses `var(--panel)`, `#workspaceSidebar` uses
`var(--bg)`, and `.group-editor-box`/`.group-body` use `var(--panel)`.
Both browser paths are covered: Firefox via `scrollbar-color`, and
Chromium/WebKit via explicit `::-webkit-scrollbar-track` plus
`::-webkit-scrollbar-track-piece` backgrounds. Corners also match the
same local surfaces.

**What was preserved**: no `overflow` rules, scrollbar dimensions,
sidebar widths, split-handle layout, or real structural borders were
changed. The sidebar `border-right`, group border, and editor modal
border all remain; the fix only blends the scrollbar track rendering
layer so those true dividers no longer read as a scrollbar border-line.

**Verification coverage**: committed lightweight source-level tests in
`backend/tests/test_frontend_scrollbar_css.py` check the global
slim/borderless baseline, the UAT10 local track rules (including
`track-piece`), and that relevant scroll containers retain their
overflow and structural border declarations. `git diff --check` is
clean; the focused test passes (4/4); the full backend suite passes
(309/309, two existing warnings). Real browser visual confirmation
remains for owner UAT because OS/browser scrollbar modes can affect the
final look.

## What was done in the prior session (Phase 3B-UAT9 — Slim Borderless Scrollbars)

**Phase 3B-UAT9 — Slim Borderless Scrollbars.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT9 Record](MIGRATION_PLAN.md#phase-3b-uat9--slim-borderless-scrollbars-2026-08-17).
No new DECISIONS.md entry.

**Summary**: a global, presentation-only scrollbar cosmetics pass added
one shared rule set to `frontend/theme.css`: universal Firefox
(`scrollbar-width: thin`, `scrollbar-color`) plus Chromium/WebKit
(`::-webkit-scrollbar` family), 6px thumb/track size, transparent
border-free global track/corner, borderless rounded thumb using
`--scrollbar-thumb`/`--scrollbar-thumb-hover` tokens in both Light and
Dark themes. No scrolling containers or layout borders were touched in
that pass; the UAT10 follow-up above only colors local tracks in the
reported areas.

## What was done in the earlier session (Phase 3B-UAT8 — Waveform Sidebar Cleanup + Main Navigation Refinement)

**Phase 3B-UAT8 — Waveform Sidebar Cleanup + Main Navigation
Refinement.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT8 Record](MIGRATION_PLAN.md#phase-3b-uat8--waveform-sidebar-cleanup--main-navigation-refinement-2026-08-17).
No new DECISIONS.md entry.

**Owner rule**: Recordings = recording management; Waveform = active
recording context + channel analysis only. The Waveform sidebar
previously duplicated Recordings' own management UI.

**Active Recording replaces "Sources in this Workspace"**: the old
multi-source clickable list (with a per-row Remove button) is gone —
`renderActiveRecording(sources)` now shows ONLY whichever source
`selectedSourceId` currently names (name + analog/digital counts),
read-only, no list, no Remove, no source-switching. **Deliberate
behavior change**: switching which source's channels you're browsing
now requires going back to Recordings and opening a different row —
this is the intended consequence of the owner's own rule, not a
regression; multi-source *display* (`ww.displayed`/`ww.panels`) is
completely untouched. The section itself dropped the old bordered
`.panel` card for a lighter, restrained block (a bottom-border divider,
no card) — nothing left to manage here justified the heavier treatment.
`startNewWorkspace()`'s "does the workspace have any sources" check
(previously reading the old list's own DOM child count) now uses a
small `latestSourcesCount` cache kept current in
`refreshAllSourceViews()`/`refreshSourceList()`.

**Channels no longer repeats identity**: `renderChannels()`'s
`.detail-header` block (station name + CFG/DAT filenames, deliberately
kept since Phase 3B-UAT5) was removed — that identity now lives in
Active Recording directly above Channels. The now-fully-dead
`.detail-header`/`.source-list`/`.source-name`/`.source-sub` CSS was
deleted, not left unused.

**Main Sidebar reordered, and a real pre-existing bug fixed**:
Recordings now comes first, Waveform second (matching the actual
product flow). While reviewing active/inactive states, found that
`.shell-nav-item[aria-current="page"]` — the CSS rule providing the
active-item accent tint — had NEVER actually matched anything:
`shellSetCurrentPage()` was writing the STRING `"true"`/`"false"`
instead of the token `"page"` the CSS always expected, so the active-
page visual has been silently broken since Phase 3B introduced page
navigation. Fixed via a new `setShellNavCurrent()` helper (writes
`"page"` when active, removes the attribute entirely when not — the
ARIA APG convention for both). Added a narrow 3px left accent bar
alongside the now-actually-working tint. New icons for Recordings (a
record-list glyph, distinct from the sidebar's own hamburger toggle
icon it used to resemble) and Waveform (a genuine zigzag/waveform
polyline, replacing a dashboard-panel-shaped icon that didn't read as
"waveform"); Table/Tools/Reports/Settings icons left unchanged.
Collapsed-sidebar order follows automatically from the DOM reorder;
`title` tooltips added to the enabled items for parity with the
disabled items' existing tooltip convention.

**Verification**: 24 new frontend `jsdom` checks
(`phase3buat8_check.mjs`) + `phase3auat4_check.mjs` substantially
rewritten (its entire premise — CFG/DAT filename containment inside the
Waveform Channels panel — no longer applies; retargeted to the
equivalent long-NAME containment concern in Active Recording) + smaller
corrections in `phase3auat3_check.mjs`, `phase3b_check.mjs`,
`phase3buat4_check.mjs`, `phase3buat5_check.mjs` (the removed
`.detail-header`, and the `aria-current` string-vs-token fix) — the
full suite otherwise returns to the exact same 20 pre-existing, already-
documented failures, zero new divergences. Backend: zero diff, 280/280
passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the accent-bar/tint combination and new icons read clearly, and
whether the lighter Active Recording section still feels sufficiently
present — was NOT and cannot be confirmed in this sandboxed session;
this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT7 (continued) — Final Table Restructuring and Row-Click-to-Open)

**Phase 3B-UAT7 (continued) — Final Table Restructuring and
Row-Click-to-Open.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT7 (continued) Record](MIGRATION_PLAN.md#phase-3b-uat7-continued--final-table-restructuring-and-row-click-to-open-2026-08-17).
Two further owner refinements, folded into the same pass as the
structured-details redesign below (still un-UAT'd as a whole). No new
DECISIONS.md entry.

**Final main-table columns**: `Recording | Start Time | Duration |
Sampling Rate(s) | Actions`. Station/Recorder/Channels/Imported are no
longer main-table columns; Sampling Rate(s) and Start Time were
promoted from Details (purely additive frontend formatting via two new
helpers, `formatRecordingStartTime()`/`formatSamplingRates()` — zero
backend change, every value already existed on `SourceSummaryOut`;
`formatSamplingRates()` renders every real rate, never simplifying a
genuine multi-rate source down to one value).

**Details reorganized (reversed direction)**: Technical zone (Recorder,
Channels, Nominal frequency, Timing reference, Samples — Recorder/
Channels moved back IN from the main table), Timing zone (Trigger,
Imported — Start Time moved OUT to the main table; Imported moved IN
from the old main-table column, `formatImportedAt()` reused unchanged),
Files zone (CFG, DAT, unchanged). A new shared
`.recording-details-zone-title` class gives each zone a quiet caption
now that the field count grew.

**Row-click-to-open**: the explicit "Open / Analyse" button was
removed. The recording `<tr>` itself (`tabindex="0"`, `role="button"`,
`aria-label` naming the action) is now the primary Open/Analyse target
— clicking it or pressing Enter/Space while focused calls the SAME
`openRecordingForAnalysis()` the old button called, no second
implementation. Actions is icon-only: Details reuses the app's existing
`.chevron` glyph (already used for Analog/Digital channel groups);
Remove reuses `&times;` (already this codebase's established close/
remove glyph elsewhere). Isolation: both buttons' click handlers call
`event.stopPropagation()`; the row's own keydown handler additionally
guards with `event.target !== row`, since a keydown bubbles up
independently of a focused button's native Enter/Space-to-click
conversion — verified by a dedicated test that dispatches a bubbling
keydown directly on the Details button. New CSS: `cursor: pointer` and
a `:focus-visible` outline on the row (reusing the pre-existing hover
rule, not duplicating it), staying visually distinct from the existing
`tr.recording-row-expanded` tint.

**Verification**: `phase3buat7_check.mjs` was substantially rewritten
for the final state — 22/22 passing. Existing-suite corrections across
`phase3b_check.mjs`, `phase3buat1_check.mjs`, `phase3buat3_check.mjs`,
`phase3buat4_check.mjs`, `phase3buat5_check.mjs`, and
`phase3buat6_check.mjs` (each had assumed the pre-restructuring column/
zone split or the three-button Actions column) — the full suite
otherwise returns to the exact same 20 pre-existing, already-documented
failures, zero new divergences. Backend: zero diff, 280/280 passing in
a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether row-click-to-open feels natural rather than accidental, and
whether the icon-only Actions column reads clearly without visible
tooltips — was NOT and cannot be confirmed in this sandboxed session;
this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT7 — Recording Details UX Redesign)

**Phase 3B-UAT7 — Recording Details UX Redesign.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT7 Record](MIGRATION_PLAN.md#phase-3b-uat7--recording-details-ux-redesign-2026-08-17).
No new DECISIONS.md entry.

**Owner feedback**: UAT6's `<table>`-grammar Details panel was
technically correct but rejected on UX grounds — read as "a second
spreadsheet," gave Start/Trigger Time no more room than any other
field, no visible connection to its parent row. A dedicated analysis
turn (three alternatives compared: inline facts strip, structured
two-zone panel, side inspector) preceded implementation; owner approved
**Option B — structured two-zone details**, plus a rule to remove
CFG/DAT filenames from the main Recordings table entirely.

**Main table**: `td.recording-name-cell` now shows only the logical
recording name — the `.recording-files` sub-line (CFG+DAT filenames)
was deleted. The search index still includes filenames even though
they're no longer visibly rendered, so filename search still works.

**Details panel — three zones, no table markup**: `renderRecordingDetails()`
was rewritten from `<table><thead>…` to (1) a `flex-wrap` "facts" strip
for Nominal frequency/Timing reference/Samples/Sampling rate(s), (2)
dedicated full-width Start/Trigger timing lines (fixing "timestamps
under-emphasized"), (3) a Files group separated by a quiet divider
(unchanged from UAT6). Start/Trigger still use the established
`.replace("T", " ")` technique — full microsecond precision preserved,
`new Date()` still never used.

**Row association**: a 3px `--accent` left bar on the details panel
plus a `--accent-wash-soft` tint on the parent row (new
`tr.recording-row-expanded` class, toggled by a new `findRecordingRow()`
helper) tie an open panel to its own row even with several expanded at
once — both existing theme tokens, no new hardcoded colors.

**Details interaction**: the toggle button keeps a stable "Details"
label at all times (no "Hide details" swap); it reuses the app's
existing `.chevron` disclosure glyph (already used for Analog/Digital
channel groups) with a new `[aria-expanded="true"] .chevron` rotation
rule, and has a transparent border by default to visually demote it
below Open/Analyse and Remove (both unchanged). `toggleRecordingDetails()`
no longer touches `textContent` — only `aria-expanded` changes.

**Verification**: 19 new frontend `jsdom` checks (`phase3buat7_check.mjs`)
+ five existing assertions corrected in place across `phase3auat3_check.mjs`,
`phase3b_check.mjs`, `phase3buat5_check.mjs`, `phase3buat6_check.mjs`
(each had assumed the now-superseded `<table>` grammar, text-swap
label, "Start time"/"Trigger time" zone labels, or main-row filename
line) — the full suite otherwise returns to the exact same 20
pre-existing, already-documented failures, zero new divergences.
Backend: zero diff, 280/280 passing in a fresh venv (unchanged — no new
field was needed, every rendered value already existed in
`SourceSummaryOut`).

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the accent-bar/row-tint association reads as intended, whether
the chevron rotation feels smooth, and whether the panel now feels
genuinely more polished — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3B-UAT6 — No Duplicate Metadata in Recording Details)

**Phase 3B-UAT6 — No Duplicate Metadata in Recording Details.** Full
detail:
[MIGRATION_PLAN.md — Phase 3B-UAT6 Record](MIGRATION_PLAN.md#phase-3b-uat6--no-duplicate-metadata-in-recording-details-2026-08-17).
No new DECISIONS.md entry (targeted refinement of the Phase 3B-UAT5
Details panel, same weight as UAT1–UAT5).

**Owner clarification**: the Phase 3B-UAT5 Details panel had been
repeating Recorder and Duration, both already visible as their own
columns in the main Recordings table. Rule: main table = quick
identification/summary metadata; expanded Details = supplementary
technical metadata not already shown in the main table.

**What changed**: `renderRecordingDetails()` no longer shows Recorder or
Duration — both stay exactly where they already were, untouched, in the
main table. The panel now shows only Nominal frequency, Timing
reference, Samples, Sampling rate(s), Start time, Trigger time, plus a
separate "Files" section listing CFG/DAT — matching the owner's own
mockup. Layout switched from vertical `.stat-grid` cards to one compact
horizontal `<table>` row (six columns, one data row), wrapped in an
`overflow-x: auto` container (same technique as `.recordings-table-wrap`)
so a narrow viewport scrolls rather than breaks Work Area's width.

**Dead code removed**: since this Details panel was the last remaining
caller of the old Waveform-sidebar-era `.stat-grid`/`.stat`/
`statCard()` machinery, and this pass moved it off that pattern too,
those CSS rules and the JS function were deleted (not left unused) —
stale comments referencing them were updated in place.

**Preserved**: the main Recordings table was not redesigned (same
columns, same data). Open/Analyse, Remove, search, and the expand/
collapse mechanism (multiple rows expandable at once, zero extra fetch)
are all unchanged from UAT5.

**Verification**: 9 new frontend `jsdom` checks (`phase3buat6_check.mjs`)
+ two existing scripts corrected in place: `phase3buat5_check.mjs`'s own
field-list/CSS-selector/leakage assertions (written for the now-
superseded UAT5 field list) were updated for the new layout;
`phase3auat3_check.mjs`'s `.stat`/`.stat .value` containment assertion
was retargeted to the new `.recording-details-table td`/
`.recording-details-file-name` rules (the old classes it checked no
longer exist). While writing the new test, discovered and worked around
a jsdom selector-engine quirk (`"tbody tr"` also matches a sibling
`<thead>`'s row for HTML tables) by using the native
`table.tBodies[0].rows` API instead. Full suite returns to the exact
same 20 pre-existing, already-documented failures, zero new divergences.

**Backend**: zero files changed — no new field was needed (Recorder/
Duration/Channels were already in `SourceSummaryOut`; this pass only
changed which already-available fields render where). **Real-browser
visual confirmation — whether the compact horizontal table reads
naturally and scrolls acceptably at narrow widths — was NOT and cannot
be confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT5 — Move Recording Metadata from Waveform to Recordings)

**Phase 3B-UAT5 — Move Recording Metadata from Waveform to Recordings.**
Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT5 Record](MIGRATION_PLAN.md#phase-3b-uat5--move-recording-metadata-from-waveform-to-recordings-2026-08-17).
No new DECISIONS.md entry (UI/data-relocation refinement within the
already-decided DEC-032 Recordings architecture, same weight as
UAT1–UAT3).

**What changed**: the Waveform Workspace Sidebar's vertical metadata
card stack (`.stat-grid`: Recorder, Nominal Frequency, Timing Mode,
Samples, Duration, Sampling Rate(s), Start Time, Trigger Time) was
removed from `renderChannels()`. The `.detail-header` identity block
(station name + filenames) was deliberately kept — active source
identification, not the metadata being relocated. Each Recordings row
gained a `[ Details ]` button (order: `[ Details ] [ Open / Analyse ]
[ Remove ]`) that expands a sibling `<tr class="recording-details-row">`
directly beneath that row, showing that exact recording's metadata —
reusing the existing `.stat-grid`/`statCard()` pattern verbatim, so its
established containment rules apply automatically. **Multiple rows may
be expanded at once** (documented design choice, not a single-open
accordion) — tracked in a `recordingsExpandedDetails` Set keyed by
`source_id`.

**Timing Mode investigation (owner's explicit critical ask)**:
confirmed via direct inspection of `backend/app/domain/timing.py` and
its existing frontend consumer (`wwTimeModesForChannel()`) that
`timing_reference` is genuine, permanent, source-level recording
metadata parsed once from the COMTRADE record at import time —
architecturally distinct from `ww.timeMode` (the user's live Absolute/
Elapsed *view* toggle). Safe to relocate, but relabeled "Timing
reference" (was "Timing mode") specifically to remove the ambiguity
risk the owner flagged.

**Zero extra backend activity**: `SourceSummaryOut` gained
`timing_reference`/`start_time`/`trigger_time`/`sampling_rates` — purely
additive, already-computed domain fields, no new storage/computation.
The Details panel renders entirely from the already-fetched
`GET .../sources` list response — expanding/collapsing is a pure
client-side toggle with zero fetch, zero reparse, zero re-upload, zero
`.../channels` request.

**Multi-recording correctness**: each details row is built from its own
loop iteration's `source` object (never a shared/global reference), so
there is no cross-row metadata leakage — confirmed by a dedicated test
with two recordings carrying different recorder names.

**Unaffected**: Open/Analyse, Remove, search all work as before.
`performRemoveSource()` now also drops the removed id from
`recordingsExpandedDetails`; `applyRecordingsSearchFilter()` now also
hides/shows each row's sibling details row in lockstep, so a filtered-
out row's details panel can never remain visible as an orphan.

**Verification**: 14 new frontend `jsdom` checks
(`phase3buat5_check.mjs`) + four existing scripts corrected in place
(`phase3auat3_check.mjs`'s recorder-name assertion, which described the
now-removed Waveform-sidebar metadata; `phase3b_check.mjs`/
`phase3buat1_check.mjs`/`phase3buat3_check.mjs`'s row-count selectors,
which now also match each row's own sibling details row) + six scripts'
mock `GET .../sources` fixtures extended with the four new fields — the
full suite otherwise returns to the exact same 20 pre-existing,
already-documented failures, zero new divergences. Backend: one
additive test (`test_list_includes_timing_reference_and_timestamps`),
280/280 passing (279 baseline + 1 new).

**Backend**: `backend/app/schemas/source.py` (additive fields only),
`backend/tests/test_sources_api.py` (one new test). **Real-browser
visual confirmation — the expanded Details panel's spacing/grid
wrapping at narrow widths and Light/Dark appearance — was NOT and cannot
be confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT4 — Recordings as Default Entry Page)

**Phase 3B-UAT4 — Recordings as Default Entry Page.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT4 Record](MIGRATION_PLAN.md#phase-3b-uat4--recordings-as-default-entry-page-2026-08-17),
[DECISIONS.md — DEC-033](DECISIONS.md#dec-033--recordings-is-the-applications-default-fresh-entry-page-no-separate-landingdashboard-page-phase-3b-uat4).

**What changed**: a fresh visit to the app now shows the Recordings
page ("Recording Events") by default instead of an empty Waveform
workspace — `shell.currentPage`'s default value changed from
`"waveform"` to `"recordings"`, applied via `shellSetCurrentPage
("recordings")` called explicitly near the start of Init (the SAME
function every other navigation already goes through). The static HTML
defaults (`#workspaceRow` now starts `hidden`, `#pageRecordings` no
longer does, `aria-current` on the two Main Sidebar Menu buttons
swapped) were kept hand-in-sync to avoid any flash of the old default.
The old unconditional trailing `refreshAllSourceViews()` call at the
end of Init was removed — the Recordings list is now populated exactly
once, via `shellSetCurrentPage`'s own existing branch for that.

**No landing/dashboard page was added** — Recording Events remains the
operational entry page (a future dashboard is an open question, not
built now). **No routing framework was introduced** — the app has no
URL-aware navigation at all; this is a single default-state change, not
a router.

**Unaffected**: `shellSetCurrentPage()` itself is unmodified, so
Recordings ⇆ Waveform navigation still preserves viewport, layout mode,
Custom Groups, panel heights, and time mode with zero refetch — reused
the exact "hide, don't destroy" mechanism established since Phase 3A/
3B, confirmed by test with a full multi-hop round trip. The Global
Header is untouched by this specific pass (Phase 3B-UAT2/UAT3 already
relocated page-specific actions off it).

**Verification**: 8 new frontend `jsdom` checks (`phase3buat4_check.mjs`)
+ one existing assertion in `phase3buat2_check.mjs` corrected in place
(it had implicitly assumed Waveform was the default page) — the full
suite otherwise returns to the exact same 20 pre-existing, already-
documented failures, zero new divergences. Backend: zero diff, 279/279
passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether a fresh page load genuinely shows Recordings with no visible
flash of the old Waveform default — was NOT and cannot be confirmed in
this sandboxed session; this remains explicitly for the owner's own
manual UAT.**

## What was done in the prior session (Phase 3B-UAT3 — Recordings Header Action Cleanup)

**Phase 3B-UAT3 — Recordings Header Action Cleanup.** Two small
refinements following directly from Phase 3B-UAT2's own relocation
work. Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT3 Record](MIGRATION_PLAN.md#phase-3b-uat3--recordings-header-action-cleanup-2026-08-17).

**Order**: "Start new workspace" and "Upload New" (already grouped in
`.recordings-header-actions` since UAT2) were reordered to `[ Start new
workspace ] [ Upload New ]` per the owner's preferred layout. Upload
New stays visually primary (unclassed button); Start new workspace
stays `.secondary`. No "Import" button exists anywhere — confirmed by
test, not re-added (it was already fully removed in UAT2).

**Button typography**: `.secondary` (0.8rem) and `.danger` (0.78rem)
were two near-duplicate literal font-sizes for the same "compact
action" tier (frequently paired in the same row, e.g. Recordings' Open
/ Analyse + Remove) — consolidated into one shared
`--button-font-size-compact: 0.8rem` token. The primary button size
(0.9rem) and toolbar/segmented-control size (0.76rem, theme.css)
remain their own deliberately distinct, untouched tiers.

**Verification**: 13 new frontend `jsdom` checks
(`phase3buat3_check.mjs`) + the full existing Phase 1 through Phase
3B-UAT2 suites — the exact same 20 pre-existing, already-documented
failures, zero new divergences (no existing test needed correction this
pass). Backend: zero diff, 279/279 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the reordered actions read correctly, and whether the (very
small, 0.8rem vs 0.78rem) font-size unification is visually
imperceptible as intended — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3B-UAT2 — Remove Duplicate Waveform-Page Import / New-Workspace Actions)

**Phase 3B-UAT2 — Remove Duplicate Waveform-Page Import / New-Workspace
Actions.** The owner established a clearer page-responsibility split:
Recordings owns recording/session management (upload/import, Open/
Analyse, Remove, and now whole-workspace lifecycle); Waveform stays
analysis-only. Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT2 Record](MIGRATION_PLAN.md#phase-3b-uat2--remove-duplicate-waveform-page-import--new-workspace-actions-2026-08-17).

**What changed**: the Global Header's own "Import" shortcut
(`#shellImportBtn`, and `shellOpenImport()`) was removed entirely —
Recordings' own "Upload New" already opens the identical modal, so a
second header-level entry point was redundant. "Start new workspace"
(`#newWorkspaceButton`/`#workspaceResetError`) was relocated — same
IDs, same completely unchanged `startNewWorkspace()`/
`resetToNewWorkspace()` lifecycle logic — from the Global Header onto
the Recordings page's own header row, grouped with "Upload New" in a
new `.recordings-header-actions` wrapper (`.recordings-header` gained
`flex-wrap: wrap` for safe narrow-width wrapping). "Clear workspace"
(Waveform toolbar) is untouched and remains distinct — confirmed by
test it never calls the whole-workspace DELETE endpoint.

**Verification**: 14 new frontend `jsdom` checks
(`phase3buat2_check.mjs`) + three existing test files corrected in
place where they referenced the now-intentionally-removed
`#shellImportBtn`/`shellOpenImport()` — the full suite otherwise
returns to the exact same 20 pre-existing, already-documented failures,
zero new divergences. Backend: zero diff, 279/279 passing in a fresh
venv.

**Backend**: zero files changed — a pure UI-relocation task. **Real-
browser visual confirmation — whether the Waveform header now reads as
appropriately simplified, and whether the Recordings page's grouped
actions read clearly with Upload New still visually primary — was NOT
and cannot be confirmed in this sandboxed session; this remains
explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT1 — Recording Row Divider Alignment)

**Phase 3B-UAT1 — Recording Row Divider Alignment.** Owner manual UAT
of the Recordings page found one cosmetic issue: the Actions column's
bottom row divider sat higher than the divider under the other columns
instead of one continuous line. Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT1 Record](MIGRATION_PLAN.md#phase-3b-uat1--recording-row-divider-alignment-2026-08-17).

**Root cause**: the Actions `<td>` carried `.recording-actions`
directly, and that class sets `display: flex` — overriding the cell's
`display` away from `table-cell` and removing it from the browser's
normal same-row-height cell-stretching, so it collapsed to its own
shorter content height while sibling cells stretched to the row's
tallest cell.

**Fix**: the flex layout now lives on an inner `<div
class="recording-actions">` inside a plain, unclassed `<td>` — the
`<td>` itself is a normal table-cell again, stretching/aligning its
border like every other cell. No column widths, button behavior,
Open/Analyse/Remove handlers, search, Phase 3A-UAT4 containment, or
responsive scrolling changed.

**Verification**: 7 new frontend `jsdom` checks
(`phase3buat1_check.mjs`) + the full existing Phase 1 through Phase 3B
suites — the exact same 20 pre-existing, already-documented failures,
zero new divergences. Backend: zero diff, 279/279 passing in a fresh
venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the divider now reads as one continuous line across the full
table width — was NOT and cannot be confirmed in this sandboxed
session; this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B — Recordings Page and Upload Workflow)

**Phase 3B — Recordings Page and Upload Workflow.** Following the
owner's own "finish this area before introducing additional features"
direction, `oruxa_powerwave` gained a dedicated Recordings page,
benchmarked (layout/workflow only, per the pre-existing DEC-020 Detego
Benchmark Principle) against Detego's own Recordings page. Full detail:
[MIGRATION_PLAN.md — Phase 3B Record](MIGRATION_PLAN.md#phase-3b--recordings-page-and-upload-workflow-2026-08-16),
[DECISIONS.md — DEC-032](DECISIONS.md#dec-032--recordings-page-as-a-first-class-application-page-one-recording--one-logical-event-cfgdat-sessionworkspace-backed-not-a-persistent-cloud-library-phase-3b).

**Navigation**: `shell.currentPage` (`"waveform"` | `"recordings"`) is
new app-shell state, kept deliberately separate from `shell.activeView`
(unchanged, still scoped to Table/Split sub-views WITHIN the Waveform
page). Main Sidebar Menu's "Workspace" item was renamed "Waveform"; a
new, real (not `disabled`) "Recordings" item was added right after it.
`shellSetCurrentPage()` toggles `#workspaceRow`/`#pageRecordings`
visibility using the exact same "hide, don't destroy" mechanism Phase
3A's `shellSetActiveView()` already established for Table/Split — the
entire waveform workspace (panels, live Plotly instances, Workspace
Sidebar) is only ever hidden, never rebuilt, when navigating to
Recordings.

**Waveform state preservation, confirmed by test**: the physical
viewport (byte-identical), layout mode, Custom Groups, panel heights,
and time mode all survive a Waveform → Recordings → Waveform round-trip
exactly, with zero waveform refetch caused by the navigation itself.
Returning to Waveform schedules `wwScheduleResizeAllVisiblePlots()`
(reusing Phase 3A-UAT1/UAT3's own helper — no new mechanism) in case the
available width changed while the page was hidden — the same staleness
risk Phase 3A-UAT3's Finding E already identified for the Table/Split
case, recurring one level up here.

**Recording abstraction**: one `SourceSummaryOut` (already one CFG+DAT
pair, per the backend's existing model) is always exactly one
Recordings row — never separate rows for the companion files, confirmed
by test. `recordingDisplayName()` prefers the real `station_name`,
falling back to the CFG filename only when blank — never invents a
fault classification or description.

**Recordings page**: heading "Recording Events," a searchable table
(Recording name+filenames / Station / Recorder / Channels / Duration /
Imported / Actions — "Format" and a separate "Station" column were both
deliberately omitted this phase, reasoned through in the MIGRATION_PLAN
record), an "Upload New" button, and a "No recordings loaded" empty
state. No contextual Workspace Sidebar on this page (section 21's own
preference). Long recording names/filenames reuse Phase 3A-UAT4's
`overflow-wrap: anywhere`/`min-width: 0` containment technique; the
table sits in an `overflow-x: auto` wrapper reusing Phase 3A-UAT3's
Finding B technique.

**Upload workflow — ONE implementation**: the always-visible "Import
COMTRADE Event" form was removed from the Workspace Sidebar; its exact
validation/upload logic was refactored (not duplicated) into a single
extensible modal, opened by both the Recordings page's "Upload New" and
the Global Header's "Import" shortcut (which now navigates to Recordings
first). The modal's file-input fields are rendered from a small
`RECORDING_FORMATS` provider model (`{id, label, enabled, files}`) —
COMTRADE is the only `enabled: true` entry (same two required cfg/dat
inputs, same ~100 MB guidance, same `POST .../sources` multipart
contract, same error mapping as before); CSV and Excel are listed as
real but `disabled` `<option>`s, proving forward-readiness without
implementing either parser. Double-submit and mid-upload dismissal are
both guarded by an explicit `uploadModalSubmitting` flag. On success,
the modal closes and clears its own status immediately — no
auto-navigation to Waveform, no auto-selecting the source into the
Channels panel (that's the Recordings row's own "Open / Analyse" action,
per the task's own preferred upload → list → user-chooses flow).

**Row actions**: "Open / Analyse" calls the existing `selectSource()`
unchanged and navigates to Waveform (no auto-display of channels — the
existing checkbox + "Add selected" step is untouched). "Remove" reuses
the existing confirmation-and-delete flow (`requestRemoveSource()`/
`performRemoveSource()`) completely unchanged, now updating the
Recordings list, the Workspace Sidebar, and the waveform-displayed-
channel state consistently from one shared refresh
(`refreshAllSourceViews()`) — there is no second, independently-drifting
recording repository; both presentations read the same
`GET .../sources` response.

**Backend change — additive only**: `SourceSummaryOut` gained
`duration_seconds`/`sample_count` (both already computed/stored on
`SourceMetadata` since Phase 2A; no new storage, no new computation) so
the Recordings list's Duration column doesn't need a separate
`.../channels` fetch per row.

**Storage semantics — explicitly unchanged**: the Recordings page is
session/workspace-backed only, reflecting the current in-memory
`WorkspaceRegistry` — no database table, no persistent cloud file
library, no upload history across sessions. Persistent recording
retention remains a separate future decision, per DEC-032.

**A real CSS bug caught before shipping**: `#workspaceRow` and the
Status Bar's waveform-only items both have author `display: flex` CSS,
which beats the UA stylesheet's default `[hidden] { display: none }`
rule by origin regardless of specificity — without explicit `[hidden]`
override rules (now added for both), this phase's own `.hidden = true`
toggles would have had zero visible effect. Caught by manual CSS review,
not by the test suite (jsdom has no real layout engine and cannot
detect this class of bug).

**Verification**: 30 new frontend `jsdom` checks (`phase3b_check.mjs`)
+ two existing test files corrected in place where Phase 3B's own
deliberate UX changes (no persistent success banner outside the modal;
the old sidebar form's removal) made their prior assertions test
since-removed behavior — the full suite otherwise returns to the exact
same 20 pre-existing, already-documented failures, zero new
divergences. Backend: `test_sources_api.py` gained two new/extended
assertions for the new fields; 279/279 passing (278 + 1 new test), zero
regressions.

**Backend**: one small, additive schema change only (see above) —
`SourceSummaryOut` gained two fields; no endpoint, table, or persistence
semantics added. **Real-browser visual confirmation — whether the
Recordings page reads as clear/simple/engineering-focused, whether the
upload modal's format selector feels natural, and whether long-filename
wrapping in the Recording column looks right at real widths — was NOT
and cannot be confirmed in this sandboxed session; this remains
explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3A-UAT4 — Channel Filename Containment)

**Phase 3A-UAT4 — Channel Filename Containment.** Owner manual UAT of
Phase 3A-UAT3's overflow hardening found one remaining real overflow
case, with browser evidence: in the Workspace Sidebar's Channels →
source-detail section, uploaded CFG/DAT filenames (e.g.
`260725_1309444309_Tanjung Bin BEN6K.cfg`/`.dat`) could still visibly
extend past the Channels panel at a narrowed Sidebar width — despite
Phase 3A-UAT3's own Finding C already having added `overflow-wrap:
anywhere` to the filename text elements. Full detail:
[MIGRATION_PLAN.md — Phase 3A-UAT4 Record](MIGRATION_PLAN.md#phase-3a-uat4--channel-filename-containment-2026-08-16).

**Root cause (established by code inspection, not guessed)**:
`.detail-header` is a flex CONTAINER with a single flex-item child — an
unnamed, unstyled wrapping `<div>` holding the station-name `<h3>` and
the filenames `.meta`. Phase 3A-UAT3's Finding C fix put
`overflow-wrap: anywhere` on the TEXT elements but never gave their
PARENT flex item its own `min-width: 0`. A flex item's automatic
minimum width defaults to its content's un-shrunk min-content size (the
well-known `min-width: auto` flex trap — the exact same class of bug
already fixed at the SHELL level in Phase 3A-UAT1/UAT3, recurring one
level deeper here, inside the Channels detail card). Text-level wrap
rules only take effect once the box AROUND the text can actually become
narrower than its unwrapped content — without that, the whole
station-name + filenames block stayed at full width regardless of the
text's own `overflow-wrap` setting. `white-space` inheritance and
inline/span wrapping issues were both checked and ruled out.

**Fix**: the previously-unnamed flex-item wrapper now has a real class,
`.detail-header-info` (`min-width: 0; max-width: 100%;` — the actual
root-cause fix). `.detail-header h3`/`.meta` additionally gained
explicit `white-space: normal; max-width: 100%;` alongside their
existing `overflow-wrap: anywhere` — belt-and-braces caps at every link
in the chain. No truncation, no ellipsis, no shortened/fake filename
string — the full CFG/DAT filename remains completely readable, now
correctly wrapping across multiple lines at narrow widths.
`word-break: break-word` was deliberately NOT added — `overflow-wrap:
anywhere` alone is sufficient (it, unlike `break-word`, is specified to
also reduce the element's own min-content contribution).

**Verification**: 12 new frontend `jsdom` checks
(`phase3auat4_check.mjs` — the owner's own exact CFG/DAT filenames, a
longer underscore-heavy/unbroken-token stress fixture, and a
520px/320px/240px Sidebar-width matrix) + the full existing Phase 1
through Phase 3A-UAT3 suites — the exact same 20 pre-existing,
already-documented failures, zero new divergences. Backend: zero diff,
278/278 passing in a fresh venv.

**Scope discipline**: filename containment only — Workspace Sidebar
resize bounds, Main Workspace reflow, Plotly resizing, Grouped/Separate/
Custom, the sticky ruler, panel-height resize, the responsive drawer,
Custom Groups, and header/status-bar layout are all confirmed unchanged
by test.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the filename now visibly wraps exactly as the owner's own
reference example showed — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3A-UAT3 — Targeted Overflow and Containment Fixes)

**Phase 3A-UAT3 — Targeted Overflow and Containment Fixes.** An
independent Codex audit of the Phase 3A shell (run against a local
working tree that could not reach GitHub — SSH authentication failure)
identified seven candidate overflow/containment risks. Per this task's
own explicit instruction, every finding was independently re-verified by
direct code inspection against canonical `main` (synced via this
session's own established HTTPS fallback) before anything was
implemented — none of the audit's conclusions were trusted blindly. Full
detail:
[MIGRATION_PLAN.md — Phase 3A-UAT3 Record](MIGRATION_PLAN.md#phase-3a-uat3--targeted-overflow-and-containment-fixes-2026-08-16).

**Audit revalidation result: all seven findings confirmed STILL PRESENT
and fixed — none rejected as invalid or already-fixed.**

- **A (responsive sidebar reopen button)**: `#shellSidebarToggleBtn {
  display: none; }` sat *after* its own `@media (max-width: 900px)`
  override in source order; equal specificity meant the later,
  unconditional rule always won, permanently hiding the reopen button
  even inside the drawer breakpoint. Fixed by reordering (base rule
  first, override second) — no `!important`.
- **B (sidebar channel table containment)**: `.group-body` (wrapping
  both analog sub-grouped and digital ungrouped channel tables) gained
  `overflow-x: auto` — an overly wide table (several columns + a
  `nowrap` action link) was previously at risk of being silently CLIPPED
  by the outer `details.channel-group`'s own `overflow: hidden`, not
  just untidy.
- **C (source/detail metadata containment)**: `.detail-header
  h3`/`.meta` and `.stat .value` gained `overflow-wrap: anywhere`;
  `.stat` (a CSS Grid item) gained `min-width: 0` — long unbroken
  station-name/filename/recorder-name/sampling-rate tokens now wrap in
  place instead of risking forcing the Sidebar wider.
- **D (modal / Custom Groups containment)**: Custom Groups chips now
  wrap their channel-name+unit text in a dedicated `<span
  class="group-chip-label">` (JS markup change, mirroring the
  established `.ww-legend-label` pattern) with `min-width: 0;
  overflow-wrap: anywhere;`; `.group-chip` gained `max-width: 100%`;
  `.confirm-box p` gained `overflow-wrap: anywhere`; `.group-editor-box`
  gained `overflow-x: hidden` (defense-in-depth, mirroring the Phase
  3A-UAT1 `.ww-chart-wrap` precedent).
- **E (waveform view visibility reflow)**: `shellSetActiveView()` now
  calls the existing `wwScheduleResizeAllVisiblePlots()` (Phase
  3A-UAT1's own helper, no new mechanism) whenever the active view
  becomes `"waveform"` — a width change while Waveform was hidden behind
  the Table/Split placeholder (still fully reachable, since sidebar/
  window resize isn't gated by active view) no longer leaves Plotly's
  charts stale once Waveform becomes visible again.
- **F (responsive drawer-width override)**: `shellCreateHorizontalSplit()`
  persists the desktop Workspace Sidebar width as an inline `style.width`
  (highest CSS specificity short of `!important`), which unconditionally
  beat the drawer breakpoint's own `width: min(320px, 82vw)` rule. Fixed
  via a `window.matchMedia("(max-width: 900px)")` listener that clears
  the inline width on entering drawer mode and restores it exactly on
  returning to desktop — the persisted preference itself is never
  mutated.
- **G (Grouped/Custom legend containment)**: base (unscoped)
  `.ww-legend-item`/`.ww-legend-label` gained the same
  containment/ellipsis technique the already-owner-approved Separate-
  mode overlay tag uses — added as a separate, lower-specificity rule so
  `#wwPanels.ww-panels-unified .ww-legend-item/-label` (Separate mode,
  already passed UAT) is completely untouched.

**Scope discipline**: no shell restructuring, no Table/Split/digital-
channel work, no backend change, no broad CSS normalization — every
rule/JS change is scoped to exactly the selector or call site its
finding named.

**Test-infrastructure fix, not an application change**: jsdom has no
`window.matchMedia` implementation at all; since Finding F's fix calls
it unconditionally at Init, all 16 existing scratch scripts that run the
real inline script needed a polyfill (minimal but real — evaluates
`max-width: Npx` against a mutable `window.innerWidth`, fires `'change'`
via a `window.__setInnerWidth(px)` test helper) or their `<script>` tag
would throw and abort partway through — the same failure class Phase
3A-UAT1 hit with the missing `requestAnimationFrame` polyfill. One
script (`frontend_logic_check.mjs`) also needed a `requestAnimationFrame`
polyfill it had never previously required.

**Verification**: 29 new frontend `jsdom` checks
(`phase3auat3_check.mjs`, using deterministic long-unbroken-token
fixtures for filenames/station names/recorder names/channel names/
units/group names/sample-rate text) + the full existing Phase 1 through
Phase 3A-UAT2 suites (293 checks, after the polyfill fix) — the exact
same 20 pre-existing, already-documented failures, zero new divergences.
Backend: zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether each fix looks correct at real, continuous viewport widths (not
just the discrete values a `matchMedia` polyfill can simulate), and
whether the horizontal-scroll/wrap/ellipsis choices read well visually
— was NOT and cannot be confirmed in this sandboxed session; this
remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3A-UAT2 — Remove Duplicate Header Theme Control)

**Phase 3A-UAT2 — Remove Duplicate Header Theme Control.**
Phase 3A-UAT1's width-reflow fix passed owner UAT; that issue is
closed. The owner then requested one small, isolated UI cleanup: the
Global Header's own Light/Dark segmented control (`#themeToggle`)
duplicated the Main Sidebar Menu's existing "Settings" item, which
already flips the same theme preference. Full detail:
[MIGRATION_PLAN.md — Phase 3A-UAT2 Record](MIGRATION_PLAN.md#phase-3a-uat2--remove-duplicate-header-theme-control-2026-08-16).

**What was built**: removed the `<div id="themeToggle"></div>` element
from `#globalHeaderActions` in the Global Header, and removed the
corresponding `window.PowerwaveTheme.mountThemeToggle(...)` call from
Init. `#globalHeaderActions` is a plain `flex; gap: 10px` row with no
reserved placeholder width, so the gap closed cleanly with zero CSS
change needed. **The Main Sidebar Menu's "Settings" item is now the
sole theme entry point** in `index.html`. Neither the shared
`.theme-toggle` CSS class (also used by the unrelated `#shellViewToggle`
Waveform/Table/Split selector) nor `theme.js`'s `mountThemeToggle()`
function itself were touched — `frontend/waveform-prototype.html` (a
separate page, out of scope) still mounts and uses the latter unchanged.
A stale code comment on the Settings click handler, which referenced
the now-removed header control, was corrected.

**Theme behavior — unchanged, confirmed by test**: persistence
(`localStorage` key `powerwave.theme`), cross-tab `storage`-event sync,
the `powerwave:theme-change` `CustomEvent`, Plotly's per-panel
`relayout`/`restyle` re-color, and zero waveform refetch on a theme
change all still work exactly as before, since they are consumed via
`window.PowerwaveTheme` directly and were never dependent on the
removed toggle's own internal state.

**Verification**: 11 new frontend `jsdom` checks
(`phase3auat2_check.mjs`) + one pre-existing `theme_crosshair_check.mjs`
check corrected in place (it asserted `#themeToggle` exists in
`index.html`, no longer true by design) + the full existing Phase 2C-A
through Phase 3A-UAT1 suites — the exact same 20 pre-existing,
already-documented failures, zero new divergences. Backend: zero diff,
278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the header now reads cleanly with no leftover gap, and whether
Settings remains comfortably reachable/usable in both Main Sidebar Menu
states — was NOT and cannot be confirmed in this sandboxed session; this
remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3A-UAT1 — Responsive Waveform Width Reflow)

**Phase 3A-UAT1 — Responsive Waveform Width Reflow.** Phase 3A's shell
STRUCTURE passed owner UAT (geometry correct, Workspace Sidebar resize
itself works). One child-layout bug was found: when the Workspace
Sidebar widened, Main Workspace correctly became narrower, but the
Plotly waveform canvas did not reflow to fit — it could visually
extend beyond its own panel frame. Full detail:
[MIGRATION_PLAN.md — Phase 3A-UAT1 Record](MIGRATION_PLAN.md#phase-3a-uat1--responsive-waveform-width-reflow-2026-08-16).

**Root cause (established by code inspection, not guessed)**:
`shellCreateHorizontalSplit()`'s own original comment incorrectly
assumed Plotly's `responsive: true` config would automatically detect
this kind of resize. It doesn't — `responsive: true` reliably reacts
to actual `window` resize events, but a sibling flex item (the
Workspace Sidebar) growing/shrinking never fires one. The CSS
`min-width: 0` chain was already correct everywhere it mattered (the
CONTAINER genuinely shrank); Plotly was simply never told to redraw,
so its stale, wider rendered SVG visually overflowed its own
(correctly-sized) `.ww-chart-wrap`, which had no `overflow` rule to
contain it.

**Fix**: `shellCreateHorizontalSplit()` was rewritten to rAF-coalesce
an `options.onResize(width)` callback, reusing the EXACT established
Phase 2C-C2A pattern (cheap width write on every raw pointermove;
the callback coalesced to at most once per animation frame; one
authoritative final call on pointerup/pointercancel). A new
`wwResizeAllVisiblePlots()` reflows every panel in `ww.panels`
(Grouped/Separate/Custom alike, reusing the existing
`wwResizePanelPlot()` per panel) plus the sticky ruler — presentation-
only, never touches `ww.viewport`, Y range, trace data, or the fetch
pipeline. Wired into three trigger points: the Workspace Sidebar's own
`onResize`; a `transitionend` listener on `#mainSidebarMenu` (guarded
to `propertyName === "width"` — the correct signal an animated
collapse/expand's width has actually finished changing, not a guessed
timeout); and a defensive `window.resize` listener (rAF-coalesced),
added since Plotly's own internal detection had just proven unreliable
for a related case. `.ww-chart-wrap` also gained `overflow: hidden` as
a defense-in-depth safety net (a no-op once the resize fix itself is
correct, per this task's own "the chart must actually resize
correctly, don't merely hide a stale width" instruction — the resize
fix is primary, this is a safety net).

**Test-infrastructure fix, not an application change**: this fix's own
rAF-coalescing means `shellCreateHorizontalSplit()` now calls
`requestAnimationFrame` unconditionally at Init time (every real
browser has this natively). Re-running the full jsdom suite revealed
six OLDER scratch scripts (`phase2ca_check.mjs`,
`phase2cb1/b2/b3/b3a_check.mjs`, `phase2cc1_check.mjs`) were missing
the `requestAnimationFrame`/`cancelAnimationFrame` polyfill later
scripts already have (from `phase2cc2_check.mjs` onward, once panel-
height resize needed it) — this silently aborted their ENTIRE inline
`<script>` evaluation partway through Init, cascading into dozens of
unrelated-looking failures on first run. Patched all six with the
exact same polyfill line already used elsewhere; the suite returns to
the identical 20-failure baseline from immediately before this task —
zero new divergences from the actual code change, confirmed by
re-running before/after, not assumed.

**Verification**: 20 new frontend `jsdom` checks
(`phase3auat1_check.mjs`) + the full existing Phase 2C-A through Phase
3A suites (264 checks, after the polyfill fix) — the exact same
pre-existing 20 failures, zero new. Backend: zero diff, 278/278 passing
in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the waveform canvas genuinely stays visually contained during a
real drag, whether the reflow feels smooth rather than janky, and
whether the `transitionend`-triggered Main Sidebar Menu reflow looks
correct in practice — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3A — Application Shell Redesign Foundation)

**Phase 3A — Application Shell Redesign Foundation.** The first
STRUCTURAL redesign of the frontend: the whole-page-scrolling, 2-column
centered layout (`main { max-width: 1100px; margin: 0 auto }`) is
replaced by a full-viewport application shell. Full detail:
[MIGRATION_PLAN.md — Phase 3A Record](MIGRATION_PLAN.md#phase-3a--application-shell-redesign-foundation-2026-08-16),
[DECISIONS.md DEC-031](DECISIONS.md#dec-031--application-shell-architecture-global-header-full-height-main-sidebar-menu-work-area-workspace-row--bottom-status-bar-phase-3a).

**Owner design principle**: "the active analysis area / waveform canvas
must dominate the screen" — clear, simple, compact, minimal clutter,
scalable for future engineering functions. Detego named as the UI/UX/
layout benchmark only (never branding/colors/typography/
implementation, per the existing DEC-020 Detego Benchmark Principle).

**Corrected shell hierarchy** (the owner explicitly corrected an
earlier, wrong interpretation mid-specification):
```
App
├── Global Header                      (full application width)
└── Body
    ├── Main Sidebar Menu               (FULL Body height)
    └── Work Area
        ├── Workspace Row               (Workspace Sidebar ⇆ Main Workspace)
        └── Bottom Status Bar           (beside Workspace Row only,
                                          never beneath Main Sidebar Menu)
```
This is a real DOM/CSS nesting: Main Sidebar Menu and Work Area are the
two direct flex children of `#appBody`; the Status Bar/Workspace Row
split happens ONE LEVEL DEEPER, inside Work Area — this specific
nesting depth (not pixel matching) is what structurally guarantees the
Status Bar can never render beneath Main Sidebar Menu. The task's own
instructions explicitly labeled the alternative (a full-width status
bar beneath everything) "Incorrect."

**Main Sidebar Menu**: narrow icon rail (52px collapsed/184px
expanded), collapsed by default, toggled via a button — never freely
drag-resizable (a deliberately different interaction model from the
Workspace Sidebar, and its state is deliberately independent of
Workspace Sidebar width — section 21's own explicit requirement).
Items: "Workspace" (the one real destination, `aria-current="page"`);
"Table"/"Tools"/"Reports" (visibly present, `disabled`, clearly marked
"coming soon" — proves the rail holds multiple items without inventing
fake pages); "Settings" (real — flips the existing Light/Dark
preference). Small hand-authored inline SVG icons, zero new dependency.

**Workspace Sidebar**: contextual to the active engineering workspace
(Import/Sources/Channels, relocated unredesigned — same IDs, same
logic), explicitly NOT global navigation. Horizontally drag-resizable
via a new small, REUSABLE split-pane helper
(`shellCreateHorizontalSplit()` — default 320px/min 240px/max 520px,
explicit state persisted to `localStorage` for the session, zero
waveform refetch by construction). The SAME function a future
Waveform ⇆ Table split is expected to reuse (section 10/22) — not a
generic layout framework, deliberately small.

**Main Workspace**: Workspace Toolbar (unchanged controls; "Clear
workspace" relocated into it, the old separate heading row removed as
redundant) above an Active View Area holding `shell.activeView`
(`"waveform"`|`"table"`|`"split"` — app-shell state, deliberately
separate from waveform-domain state `ww`, per section 28's own explicit
instruction — the shell never reads/writes `ww` directly). Waveform is
real; Table/Split are structural placeholders only — confirmed by test:
zero fake data, zero new fetches when switched to.

**Sticky Time Axis**: preserved exactly (Phase 2C-C4B's accepted
compact layout, unchanged). Its scrolling ancestor changed from the
whole page to `#activeViewArea` specifically (every shell region now
has its own internal scroll) — functionally identical `position:
sticky` behavior, just a more contained scrolling context.

**Bottom Status Bar**: real values only — workspace id (moved from the
old page footer), source station name, sample rate, duration (from the
same already-fetched `renderChannels()` data, no new API call), and
displayed-channel count (`ww.displayed.size`, read-only). Cursor A/B,
Delta Cursor, fault/event state are explicitly NOT shown — deferred to
documentation, never fabricated.

**Responsive strategy**: desktop/laptop is the unconditional primary
target (the shell above applies with no alteration). Under ~900px, Main
Sidebar Menu force-collapses and Workspace Sidebar becomes a reopenable
overlay drawer (pure CSS `position: absolute` against `#workspaceRow`
itself, not `fixed` against the viewport — avoids needing the header's
own height). Under ~640px, header/status-bar spacing tighten further.
Main Workspace always gets the space freed by a collapsed/hidden
secondary region. Phone is a secondary companion mode per the owner's
own explicit framing, not fully designed this phase — only structurally
un-blocked.

**Existing control inventory — what moved** (section 27): "Waveform
Workspace" heading removed (redundant); "Clear workspace" moved into
the Workspace Toolbar; "Workspace: <id>" + "Start new workspace" moved
from the page footer into the Bottom Status Bar / Global Header
respectively; Import/Sources/Channels moved from the old 2-column page
grid into the Workspace Sidebar, unredesigned internally. Everything
else kept its exact element ID, only its container moved.

**Verification**: 40 new frontend `jsdom` checks (`phase3a_check.mjs`)
+ the FULL existing Phase 2C-A through 2C-C4B suites (224 checks)
re-run unmodified — **the exact same pre-existing pass/fail counts as
immediately before this phase (20 already-documented failures, zero
new divergences), independently confirmed before/after, not assumed**.
This held because every existing waveform element kept its exact ID
and internal DOM relationships — only its container moved. Backend:
zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
actual proportions, resize feel, Main Sidebar Menu's collapsed width,
and the entire responsive/drawer behavior at real narrow viewport
widths — was NOT and cannot be confirmed in this sandboxed session;
this remains explicitly for the owner's own manual UAT. This is
explicitly an INITIAL shell per the task's own framing — the owner's
UAT is expected to adjust dimensions/spacing, not just confirm the
structure.**

## What was done in the prior session (Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction)

**Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction.**
**Phase 2C-C4's sticky ruler functionality passed owner UAT.**
**Phase 2C-C4A's visual LAYOUT failed owner UAT**: the custom DOM
title placed above the Plotly tick chart, together with an
Absolute-only date line also above it, produced a tall strip with a
large blank vertical gap — reading as an "information card," not a
compact X-axis. The owner supplied a reference screenshot and an exact
desired layout: tick labels first, a small title directly below them
(never above), no date inside the ruler at all. Full detail:
[MIGRATION_PLAN.md — Phase 2C-C4B Record](MIGRATION_PLAN.md#phase-2c-c4b--compact-sticky-time-axis-layout-correction-2026-08-16).

**Root cause traced**: not the DOM title's own sizing, but the ruler's
own Plotly chart margin — `t:4, b:24` inside a `height:46px` chart left
`46-4-24=18px` of genuinely empty invisible plot-area space (present
even with zero traces and a hidden Y axis), stacked underneath the DOM
title/date lines above it.

**Fix**: the ruler now sets `xaxis.title` directly on its own Plotly
layout — the exact same mechanism every real waveform panel already
uses for its own "Time (s)" title — instead of a separate, hand-
positioned DOM element. Plotly places titles below tick labels by its
own convention, already proven pixel-aligned in this exact codebase on
every panel; no bespoke CSS centering math needed. `#wwStickyRulerTitle`
and `#wwStickyRulerContext` (the custom title/date DOM elements from
Phase 2C-C4A) were deleted entirely, along with their CSS. The ruler's
own margin changed to `{t:2, b:34}` (b:34 reused verbatim from the real
panels' own already-proven fit), and the chart's CSS height reduced
from 46px to 40px. **Resulting total ruler height: ~43–45px**, down
from ~63–80px in Phase 2C-C4A.

**Wording/date changes**: Absolute mode's title is now the owner's
exact specified wording, **"Record Time"** (capital T, was "Record
time" in C4A). No date text appears in the ruler at all anymore — the
toolbar's own `#wwTimeModeContext` label is unchanged and remains the
only place the date is shown.

**What did NOT change**: the unit-aware Elapsed rescaling from Phase
2C-C4A (`wwStickyRulerElapsedUnit()`, the single shared decision for
both tick values and title) is completely untouched — same single
source of truth, still scoped entirely to the ruler's own independent
Plotly domain. `WW_PANEL_MARGIN`, `position: sticky`/`bottom: 0`, no
scroll listener, Separate mode's all-lanes tick suppression, Grouped/
Custom's unchanged per-panel axes, zoom/pan sync, Reset Time View,
Autoscale Y, panel resize, Custom Groups, and the waveform API are all
completely unaffected — confirmed by test.

**Verification**: `phase2cc4a_check.mjs` (scratch, not committed) was
rewritten per this task's own explicit instruction ("update those
assertions rather than treating the correction as a regression") since
its old assertions read a DOM element that no longer exists — now 25/25
passing (broader than the original 23; added checks for the removed
DOM elements/CSS, the compact chart height, and the reused b:34
margin). The full existing Phase 2C-A through 2C-C4 suites (199 checks)
show the exact same 20 failures already fully documented in the Phase
2C-C4/2C-C4A records — zero new divergences introduced by this
correction, since none of this pass's changes touch the underlying
causes. Backend: zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the compact layout genuinely matches the owner's reference
screenshot, whether spacing feels right — was NOT and cannot be
confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C4A — Sticky Time-Axis Title Placement and Unit Label)

**Phase 2C-C4A — Sticky Time-Axis Title Placement and Unit Label.**
**Owner manual UAT confirmed Phase 2C-C4 passed functionally**
(sticky shared time axis stays visible while scrolling, ruler
alignment good, zoom/pan sync good, Absolute/Elapsed switching good,
resizing does not break the ruler) before this task began. The next
request was explicitly **cosmetic only**: relocate the ruler's title
to the top of the strip (not under the ticks) and give it a small,
compact, mode-appropriate wording — full detail:
[MIGRATION_PLAN.md — Phase 2C-C4A Record](MIGRATION_PLAN.md#phase-2c-c4a--sticky-time-axis-title-placement-and-unit-label-2026-08-16).

**Absolute mode**: a fixed, compact title — "Record time" — never a
per-unit label (Absolute is a timestamp representation, not an
elapsed unit scale). The ruler's own date-context line simplified from
"26 Jul 2025 · Record time" to just "26 Jul 2025", avoiding duplicate
"Record time" wording now that the title says it directly above.
**The toolbar's own copy of the context label is deliberately
unchanged** — still the full "<date> · Record time" wording, since it
has no adjacent title to duplicate against.

**Elapsed mode**: the title is now genuinely unit-aware — "Time (ms)",
"Time (s)", or "Time (min)" depending on the visible span. This
required real engineering, not just a label swap: investigation found
Phase 2C-C3's existing tick formatting never actually switched units
at all (always raw seconds, only adapting decimal precision at finer
zoom) — a fixed "Time (ms)" title over an unchanged seconds-formatted
tick would have been exactly the "title says X, ticks show Y"
mismatch this task's own instructions explicitly forbade. **Fix**: one
new shared function, `wwStickyRulerElapsedUnit(spanSeconds)`, is now
the SINGLE decision both the title AND the ruler's own tick values
consult — a simple 3-tier span rule (< 1s → ms, < 60s → s, ≥ 60s →
min), with the ruler's own (independent, trace-less) Plotly x-axis
domain genuinely rescaled by the chosen unit's constant factor. This
rescale is scoped ENTIRELY to the ruler's own Plotly instance —
`ww.viewport`, `wwElapsedToPlotlyX()`, every real waveform panel's own
axis, and Phase 2C-C3's timing semantics are all completely untouched.
Updates automatically on zoom/pan/mode-switch via the same existing
`wwSyncStickyRuler()` call sites Phase 2C-C4 already wired — no new
synchronization loop, confirmed zero waveform refetches.

**Honest, unverified caveat (flagged explicitly, not glossed over)**:
the claim that a uniform rescale of the ruler's own axis domain
preserves tick pixel-position alignment with the real (unrescaled)
waveform panels below it was reasoned through carefully (Plotly's
"nice round tick value" algorithm is scale-covariant under a constant
multiplier) but **could not be visually confirmed in this sandbox** —
no real browser is available. This is the single most important thing
for the owner to check during UAT.

**Verification**: 23 new frontend `jsdom` checks
(`phase2cc4a_check.mjs`) + the full existing Phase 2C-A through 2C-C4
suites (222 checks) re-run unmodified. 20 failures appear, all
explained — not regressions: the same pre-existing Phase 2C-C3/2C-C4
divergences already documented in those phases' own records, plus a
new (equally expected) divergence where several older, pre-COMTRADE-
timing test fixtures' "last relayout call" assumption now sometimes
resolves to the ruler's own correctly-rescaled value instead of a
panel's raw value, and `phase2cc4_check.mjs`'s own date-context-
equality assertion, which asserted the exact thing this phase's own
design deliberately changed. None of these frozen, one-off scripts
were modified, per this project's established precedent. Backend:
zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the title's placement/size/spacing reads as intended against
the owner's own reference screenshot, and critically whether tick
alignment genuinely holds at fine Elapsed-mode zoom — was NOT and
cannot be confirmed in this sandboxed session; this remains explicitly
for the owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C4 — Sticky Shared Waveform Time Axis)

**Phase 2C-C4 — Sticky Shared Waveform Time Axis.** **Owner UAT
confirmed Phase 2C-C3 passed** (Absolute Time correct, Elapsed Time
correct, mode switching preserves the physical window) before this task
began. The next owner-identified usability problem: with many displayed
channels, the shared time-axis labels were only visible at the very
bottom of the panel stack — an engineer working on a channel near the
top of a long, scrolled workspace had no visible time reference. Full
detail:
[MIGRATION_PLAN.md — Phase 2C-C4 Record](MIGRATION_PLAN.md#phase-2c-c4--sticky-shared-waveform-time-axis-2026-08-15).

**Architecture**: ONE Oruxa-owned shared time-axis strip
(`wwSyncStickyRuler()`), driven entirely by the existing workspace-level
`ww.viewport`/`ww.timeMode` state (DEC-021, DEC-029) — never an
independent authority. Implemented as a second, lightweight,
**trace-less** Plotly instance (empty `[]` traces array — axis only,
never a second waveform chart) rather than a hand-rolled SVG/canvas
ruler: this reuses Phase 2C-C3's own `wwTimeAxisTickFormat()` verbatim,
so the ruler's ticks are chosen/formatted by the exact same engine as
every panel, with zero risk of a second, independently-drifting
time-formatting implementation — the one thing this task's own
instructions were most emphatic about avoiding. Plotly was already a
page dependency, so this adds zero new weight.

**Alignment (called out as critical)**: a new shared constant,
`WW_PANEL_MARGIN = { l: 55, r: 20 }`, replaces the margin numbers
previously inlined only in `wwBuildLayout()` — now used by both
`wwBuildLayout()` and the ruler, so the two cannot independently drift
out of pixel alignment. Combined with the ruler's CSS horizontal padding
matching `.ww-panel`'s own exactly (14px, confirmed identical across
Grouped/Separate/Custom), this keeps tick positions pixel-aligned with
every panel's plot area with no runtime measurement needed.

**Sticky behavior**: pure CSS `position: sticky; bottom: 0` — not
`fixed`, no scroll listener. The ruler is a normal-flow sibling of
`#wwPanels` inside `.workspace-section` (its containing block), which is
what makes it stay pinned to the viewport bottom only while part of the
workspace is still below the viewport, and scroll away naturally once
the whole workspace has been scrolled past — satisfying the explicit
"must not permanently float over unrelated content" requirement using
ordinary browser layout. Confirmed by test: dispatching synthetic scroll
events causes zero Plotly calls and zero waveform fetches.

**No new synchronization loop**: `wwSyncStickyRuler()` is called from
exactly the places that already mutate `ww.viewport`/`ww.timeMode`
(`wwApplyAndFetchViewport` — the single function zoom/pan/Reset Time
View all funnel through — and `wwSetTimeMode`), plus displayed-channel-
count and theme-switch call sites. It never registers its own Plotly
event listener (`staticPlot: true`, no `.on(...)` wired), confirmed by
test, so it cannot become a second authority or loop.

**Existing panel axis labels (section 16)**: Separate mode's per-lane
axis chrome (`wwApplyTimeAxisChrome()`) now suppresses ticks/title on
**every** lane, not just the non-bottom ones — the sticky ruler makes
that lone remaining bottom-lane axis redundant. Grouped/Custom panels'
own per-panel axis labels are **deliberately left unchanged** this
slice (a materially larger, riskier restructuring given neither mode
has a single "bottom panel" concept) — documented as a known,
intentional duplication for a future cleanup pass, not fixed here.

**Verification**: 24 new frontend `jsdom` checks (`phase2cc4_check.mjs`)
+ the full existing suites re-run unmodified. `frontend_logic_check.mjs`
and `theme_crosshair_check.mjs` pass in full. Across the Phase 2C-A
through 2C-C3 suites, **9 new failures appear, all explained by this
phase's two deliberate changes** — not regressions: (1) several scripts
assert an exact Plotly `newPlot`/`relayout` call count "one per panel,"
now off-by-one because of the ruler's own extra (single) Plotly
instance; (2) several scripts assert the now-superseded "only the
bottom lane shows ticks" Separate-mode behavior. These are frozen,
one-off, not-committed verification scripts from prior phases — per
this project's own established precedent (Phase 2C-C3's identical
treatment of its own Absolute-default divergence), they were not
modified; `phase2cc4_check.mjs` explicitly covers what changed. Backend:
zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the ruler genuinely reads as "sticky" and unobtrusive while
scrolling, whether tick positions visibly line up with waveform data at
various real zoom levels, whether it ever visually covers content — was
NOT and cannot be confirmed in this sandboxed session; this remains
explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C3 — COMTRADE Time-Axis Modes)

**Phase 2C-C3 — COMTRADE Time-Axis Modes.** Adds two selectable,
workspace-level time-axis representations for COMTRADE waveforms:
**Absolute Time** (real recording timestamp per sample, the new
default) and **Elapsed Time** (the pre-existing 0-based-from-record-
start behavior, now explicit/selectable). Full detail:
[MIGRATION_PLAN.md — Phase 2C-C3 Record](MIGRATION_PLAN.md#phase-2c-c3--comtrade-time-axis-modes-2026-08-15).

**Timing investigation, done first per this task's own mandate**:
`TimingInformation.start_time`/`.trigger_time` are separate,
independently-parsed COMTRADE CFG fields, never conflated; the DAT
file's per-sample `ts` (µs from recording start) has sample 0 always
coinciding with `start_time`, **never** `trigger_time` (confirmed
against real parsed metadata, not assumed); both timestamps are
timezone-naive end to end (no timezone field exists anywhere in the
parser/schema); `TimebaseOut` (`GET .../channels`) already exposed
`start_time`/`trigger_time`/`timing_reference` before this pass —
**zero backend changes were needed**, this is a pure frontend
presentation transform.

**Architecture**: `ww.timeMode` (`"absolute"` \| `"elapsed"`) is
workspace-level, not per-panel. The shared physical viewport (DEC-021)
stays authoritative in elapsed-seconds internally, permanently — a
single conversion boundary (`wwElapsedToPlotlyX`/`wwPlotlyXToElapsed`)
is the only place Absolute-mode date strings and Elapsed-mode numbers
meet; the fetch pipeline and backend requests are untouched.
**Zero waveform refetches on a mode switch** — confirmed by test.
Timestamp parsing/formatting uses only `Date.UTC()`/`getUTC*()` — never
local-time getters or `new Date(isoString)` — so there is no
browser-timezone dependency anywhere in this path. The source
capability model (`wwTimeModesForChannel()`) gates Absolute availability
on the backend's own `timing_reference === "absolute"` field, falling
back to Elapsed-only (with both toolbar buttons correctly
enabled/disabled) rather than ever showing a fake option.
`ww.timeMode` **persists across `wwClearWorkspace()`** — same
viewing-preference policy as `ww.layoutMode`/`ww.dragMode`. Adaptive
tick formatting uses Plotly's own native `tickformatstops` (broad-to-
fine date/time bands for Absolute, decimal-precision bands for
Elapsed) — SI-prefix (`~s`) formatting was explicitly rejected as
ambiguous for time values.

**Two real regressions were caught and fixed during this pass's own
regression-suite re-run** (before anything shipped): (1) a `timebase`
variable-scoping bug in `renderAnalogGroup`/`renderChannelTable` that
broke ALL channel checkbox rendering (channel metadata plumbing needed
`timebase` threaded through two intermediate functions that didn't
have it in scope); (2) `wwApplyTimeAxisChrome()` (renamed from
`wwUpdateBottomLaneAxis()`) initially lost its original Grouped/Custom-
mode no-op guard, causing unnecessary relayout calls on every panel in
every layout mode — fixed by restoring the guard and instead updating
Grouped/Custom panel titles directly inside `wwSetTimeMode()`, where a
mode switch actually needs it.

**Verification**: 26 new frontend `jsdom` checks
(`phase2cc3_check.mjs`) + the full existing `frontend_logic_check.mjs`,
`theme_crosshair_check.mjs`, and Phase 2C-A through 2C-C2A suites (193
checks) re-run unmodified, all passing except 2 pre-existing checks in
the non-committed `phase2ca_check.mjs` that assert a raw-elapsed-number
`xaxis.range` — the **expected, correct** consequence of Absolute now
being the COMTRADE default, not a regression. Backend: zero diff,
278/278 passing in a fresh venv. **Real COMTRADE verification**: a
synthetic ASCII COMTRADE record imported through the actual FastAPI app
(`TestClient`, no mocking) with a known `start_time`
(`2025-07-26T14:23:10.123456`) and a distinct `trigger_time` 200ms
later confirmed sample 0's absolute time equals `start_time` exactly,
never `trigger_time`; a second scenario deliberately crossing a
midnight/date boundary confirmed both the API and the frontend's own
`wwParseNaiveTimestamp`/`wwFormatPlotlyDateString` correctly roll the
calendar date over. Both scenarios' backend-returned values were then
fed through the actual shipped frontend JS to confirm parser and
frontend agree exactly.

**Known, documented (not a bug) precision limitation**: JS `Date` has
millisecond resolution vs. COMTRADE's microsecond-precision CFG
timestamps — a sample whose fractional second rounds to exactly the
next millisecond can display 1ms later than its literal value; invisible
in practice since the UI never shows sub-millisecond precision, and not
a rollover-logic defect (`Date.UTC` overflow handling itself is
correct).

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the toolbar toggle reads as compact/discoverable, whether
adaptive tick formatting looks right across real zoom levels, whether
mode-switching while zoomed feels seamless — was NOT and cannot be
confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C2A — Panel Resize Responsiveness Investigation)

**Phase 2C-C2A — Panel Resize Responsiveness Investigation.** The
owner's manual UAT of Phase 2C-C2 (adjustable panel heights) **passed
functionally** — resize works correctly in Grouped/Separate/Custom, the
handle feels natural enough, and the 100px minimum / 600px maximum are
both accepted as-is (**unchanged by this pass**). The owner separately
**observed** that during live dragging, the waveform does not visually
follow the panel resize immediately — a delay of perhaps a few hundred
milliseconds, judged bearable, with a preference for better
responsiveness only if low-cost/low-risk. This task was explicitly
**investigate first, do not assume an optimization is needed**. Full
detail:
[MIGRATION_PLAN.md — Phase 2C-C2A Investigation Record](MIGRATION_PLAN.md#phase-2c-c2a--panel-resize-responsiveness-investigation-2026-08-15),
[DECISIONS.md — DEC-028 Update note](DECISIONS.md#dec-028--adjustable-waveform-panel-heights-added-to-all-three-layout-modes-phase-2c-c2)
(no new decision entry — a refinement of the same resize-performance
concern DEC-028 already covers, per governance).

**Bottleneck identified, by direct code-path tracing**: Phase 2C-C2's
`wwSetPanelHeight()` performed the cheap DOM height write AND the
expensive `Plotly.Plots.resize()` call as two synchronous statements
inside the SAME `requestAnimationFrame` callback. A browser cannot paint
a DOM change until the current synchronous unit of JS returns control —
so the panel's new box size was gated on Plotly's own redraw finishing
first, every frame during a drag. Confirmed **structurally** (this
sandbox has no real browser; installing Playwright/Puppeteer for a
one-off diagnostic was judged disproportionate) via jsdom instrumentation
with a simulated-cost Plotly mock (tested at 0ms/20ms/50ms simulated
cost): before the fix, every observed DOM height-write timestamp was
numerically identical to that cycle's Plotly-resize-*end* timestamp —
the height change was never externally observable until Plotly's
(simulated) work had already finished.

**Investigation questions A–I** (this task's own list) were answered
directly by code inspection: rAF scheduling itself is not a contributor
(near-zero-cost browser primitive); no redundant legend/axis/layout work
is triggered beyond what `Plotly.Plots.resize()` itself inherently does;
**dragging one panel already only ever resized that one panel** (no loop
over `ww.panels` anywhere in the resize path — confirmed, not a bug);
and per-frame cost is structurally independent of total panel count
(each panel's resize handle has its own closured state).

**Decision: A. LOW-COST REFINEMENT JUSTIFIED**, checked against every
bullet of DEC-028's own cost/benefit rule (small/understandable change;
no custom rendering engine; no brittle Plotly internals; no
synchronization regression; no waveform refetch; no added state
complexity of consequence; likely meaningful improvement, confirmed
structurally not just asserted).

**What was built**: `wwSetPanelHeight()` split into
`wwSetPanelHeightImmediate()` (clamp/store/write the CSS height only —
now called on **every** raw `pointermove`, not gated behind rAF at all,
since a bare style write doesn't itself force synchronous layout) and
`wwResizePanelPlot()` (the `Plotly.Plots.resize()` call only — still
invoked from inside `requestAnimationFrame`, still coalesced to at most
once per frame regardless of raw pointermove frequency, **identical
coalescing behavior to before**, confirmed by test that Plotly call
counts are unchanged). `wwSetPanelHeight()` itself is retained as the
combination of both, used only for the authoritative final write on
`pointerup`/`pointercancel` (unchanged contract from Phase 2C-C2). Verified
by re-running the same jsdom measurement after the fix: the DOM height
write now becomes observable measurably *before* the corresponding
Plotly resize call even starts, at every simulated cost level tested.

**Preserved exactly, unchanged, reconfirmed by test**: 100px minimum /
600px maximum clamping; independent per-panel sizing; Grouped/Separate/
Custom mode behavior; the panel-height state model (`ww.panelHeights`,
keyed by `groupKey`); zoom/pan synchronization; shared viewport; Reset
Time View; Autoscale Y; theme behavior; crosshair; overlay labels;
Custom Groups behavior; the waveform API. **Zero waveform refetches**
during resizing, before and after this change.

**Backend**: zero files changed — no backend change was needed or made.

**Tests**: 278 backend (unmodified) + 9 new frontend `jsdom` checks
(`phase2cc2a_check.mjs`) + the full existing Phase 2C-C2 (23), Phase
2C-C1 (30), Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20), Phase
2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites all re-run
unmodified and still passing (154 total this pass, no regressions).
**Real-browser tactile confirmation of the improvement — whether the
drag genuinely feels smoother, and whether any momentary divergence
between the box's edge and the waveform's own rendered edge is visible
during a fast drag — was NOT and cannot be confirmed in this sandboxed
session; this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C2 — Adjustable Waveform Panel Heights)

**Phase 2C-C2 — Adjustable Waveform Panel Heights.** The owner completed
manual UAT of Phase 2C-C1 Custom Groups: **PASSED** — "the workflow is
smooth and easy to understand." Before moving on to digital channels, the
owner requested one more analog-workspace refinement: every waveform
panel/lane independently resizable by dragging, across all three layout
modes (Grouped/Separate/Custom), with **Detego's vertical panel-resize
interaction named as the explicit UX benchmark** (placement/feel only —
no branding/colors/icons copied). Full detail:
[MIGRATION_PLAN.md — Phase 2C-C2 Implementation Record](MIGRATION_PLAN.md#phase-2c-c2--adjustable-waveform-panel-heights-implementation-record-2026-08-15),
[DECISIONS.md — DEC-028](DECISIONS.md#dec-028--adjustable-waveform-panel-heights-added-to-all-three-layout-modes-phase-2c-c2).

**What was built**: a thin `.ww-resize-handle` (8px hit area, small
centered theme-token-styled grip, `cursor: ns-resize`) added to every
panel's DOM in `wwCreatePanelDom()`, sitting entirely below the chart
(zero overlap into the plotting area, so it never intercepts hover/
crosshair). Dragging uses native **Pointer Events + Pointer Capture**
(`setPointerCapture` on `pointerdown`, so the drag keeps working even if
the pointer leaves the handle's narrow bounds) with move/up listeners
added on `pointerdown` and always removed on `pointerup`/`pointercancel`
— no `document`-level listeners, nothing that can leak. Resizing is live
during the drag (not deferred to mouse-up), coalesced through
`requestAnimationFrame` so at most one `Plotly.Plots.resize()` call
happens per animation frame regardless of raw pointer-event frequency.

**Height constraints (documented, tested)**: minimum **100px** (keeps a
usable plot area above `wwBuildLayout()`'s own fixed 44px top+bottom
margins — a floor much lower would produce the "unusable strip" this
task explicitly warned against); maximum **600px** (generous, not a hard
requirement, purely to prevent pathological single-panel growth);
defaults match each mode's own pre-existing height (Grouped/Custom
260px, Separate 140px) so a brand-new panel's first paint is unchanged
from before this phase.

**Height state model (documented, tested)**: explicit application state
(`ww.panelHeights`, a `Map<groupKey, heightPx>`), never read from the
rendered DOM as the source of truth — reusing the SAME `groupKey` panel
derivation already computes (Phase 2C-B1's own architecture), not a new
identity concept. This single mechanism, with zero per-mode
special-casing, produces exactly the requested behavior: different
modes' keys never collide (a Separate VA lane's height never leaks onto
the Grouped Voltage panel); the SAME mode's key persists across a round
trip (Separate→Grouped→Separate restores VA's own Separate height); a
brand-new key always gets its mode's sensible default — no cross-mode
height-mapping logic was built, per this task's own explicit
instruction not to invent one.

**Presentation-only, verified directly**: `Plotly.Plots.resize()` is the
only Plotly API ever called for a height change — no data refetch, no
viewport reset, no Y-range reset. Fetch-call counts before/after a full
multi-move resize drag, in every mode, are identical. Synchronization
(DEC-021) is untouched — resizing never reads/writes `ww.viewport` or any
panel's `suppressNext` flag; zoom/pan after resizing still broadcasts
correctly to every panel. Separate mode's unified canvas, overlay label
(still a correctly-positioned child of its own lane regardless of that
lane's height), and bottom-only shared X-axis (still exactly the true
last panel, regardless of resizing) are all fully preserved — verified
directly, not just asserted. Custom group membership and the group-
editing workflow itself are completely untouched.

**Persistence**: `ww.panelHeights` is session/workspace-only (no
backend/database persistence, matching DEC-015's ephemeral-by-design
principle); a whole-workspace reset clears it; individual channel/panel
removal deliberately does not (same policy Phase 2C-C1 already
established for `ww.customGroups`, same reasoning).

**Accessibility limitation, documented honestly**: keyboard resizing was
**not** implemented this slice (`tabindex="-1"`, `role="separator"` +
`aria-label` only) — this task's own instructions marked it desirable
long-term but not required "unless trivial," and a correct keyboard-
resize interaction (likely `role="slider"` with `aria-valuenow`/min/max)
was judged non-trivial, out of proportion to this slice's pointer-drag
requirement.

**Backend**: zero files changed — no backend change was needed
(frontend/state-only, per this task's own preference).

**Tests**: 278 backend (unmodified) + 23 new frontend `jsdom` checks
(using jsdom's real `PointerEvent` constructor plus a
`requestAnimationFrame`/`cancelAnimationFrame` polyfill jsdom itself
lacks) + the full existing Phase 2C-C1 (30), Phase 2C-B3A (17), Phase
2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19), and
Phase 1 (4) suites all re-run unmodified and still passing (145 total
this pass, no regressions). **Digital-channel rendering, lane drag/
reorder, and drag-to-group all remain explicitly not started.**
Real-browser tactile/visual confirmation of the drag interaction itself
was not possible in this sandboxed, no-real-browser session — see this
task's own final report for the closest available substitute evidence;
final judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-C1 — Custom Analog Channel Groups)

**Phase 2C-C1 — Custom Analog Channel Groups.** The owner chose to
**skip vertical lane drag/reorder for now** — previously flagged as the
owner's likely next direction since Phase 2C-A — and instead requested
**Custom Groups**: manual, user-controlled decisions about which
displayed analog channels share a waveform panel, with **Detego's own
"Edit Channel Groups" workflow named as the explicit benchmark** (a
workflow/layout reference only — no Detego branding/colors/icons
copied). Full detail:
[MIGRATION_PLAN.md — Phase 2C-C1 Implementation Record](MIGRATION_PLAN.md#phase-2c-c1--custom-analog-channel-groups-implementation-record-2026-08-15),
[DECISIONS.md — DEC-027](DECISIONS.md#dec-027--custom-analog-channel-groups-added-as-a-third-layout-mode-dragreorder-deferred-phase-2c-c1).

**What was built**: a third toolbar layout-mode button, `[ Grouped ]
[ Separate ] [ Custom ]`. Selecting Custom with no custom grouping
defined yet shows one panel per channel (the auto-solo fallback, see
below) so the mode is never empty/broken on first entry. A new **Edit
Channel Groups** button (visible only in Custom mode) opens a modal
(reusing the app's existing `.confirm-overlay` backdrop pattern, Oruxa
theme tokens throughout): an **Unassigned channels** list (each a chip
with an "Add to group…" `<select>`) and a **Groups** section (`+ Add
group`, each group a card with an editable name, a delete button, and a
chip list of its assigned channels with per-chip remove). Apply commits
the working copy and rebuilds the workspace under Custom mode; Cancel /
the × close button / Escape / backdrop-click all discard the working
copy with zero side effects (editing happens in an in-memory
`groupEditorState`, never touching the real `ww.customGroups` until
Apply). No drag-and-drop inside the modal — moving a channel between
groups is two explicit steps (unassign, then assign via the dropdown), a
deliberate, honestly-reported first-slice simplification.

**Group assignment rule (documented, per this task's own required
choice)**: any displayed channel not placed in a group automatically
becomes its own single-channel panel — there is no "unplaced" error
state, and Apply is never blocked on complete assignment.

**Rendering**: each custom group becomes a panel via the exact same
`wwCreatePanelObject`/`wwCreatePanelDom`/`wwBuildLayout`/`wwInitPanelPlot`
machinery every other mode already uses — **zero changes needed there**.
The only new logic is a "custom" branch in `wwPanelGroupKeyFor`/
`wwPanelLabelFor` (looks up which `ww.customGroups` entry claims a
channel, or falls back to a uniquely-prefixed solo key) plus a new
`wwCustomGroupFor()` helper; `wwRebuildLayout()` itself needed **no
changes at all**, exactly the payoff of the panel-derivation architecture
Phase 2C-B1 (DEC-025) built for this purpose. Custom panels use Grouped's
card styling, not Separate's unified/overlay treatment (a Custom panel
can hold multiple channels, the same shape as Grouped).

**Viewport preservation and grouping persistence, both verified
directly**: zooming, then opening/Applying the group editor, leaves the
resulting panels at the exact same X/time range (zero special-case code
— `wwRebuildLayout()` already reads the current `ww.viewport` and never
touches it). The last-applied custom grouping persists across
Grouped/Separate/Custom mode switches within the session — switching
back to Custom restores it rather than resetting to all-solo — and is
only cleared by a whole-workspace reset ("Clear workspace"/"Start new
workspace"), matching how the viewport/record bounds are already reset
there.

**Backend**: zero files changed — no backend change was needed (Custom
grouping is frontend-only, in-memory, ephemeral session state, per this
task's own preference and the project's existing ephemeral-by-design
principle, DEC-015).

**Tests**: 278 backend (unmodified) + 30 new frontend `jsdom` checks + the
full existing Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20),
Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites all re-run
unmodified and still passing (122 total this pass, no regressions).
**Direct vertical lane drag/reorder and drag-to-overlay/group by direct
lane dragging were explicitly not started — deliberately deferred by the
owner's own choice this pass, not abandoned.**

**Also note**: between Phase 2C-B3A and this pass, the owner made two
small direct manual tweaks to the Phase 2C-B3A overlay tag (committed
separately as `d902dc5`, "style: tune overlay lane label position and
background"): `top: 50%` → `top: 25%` (a higher vertical position within
the lane) and `.ww-legend-item`'s `background` changed from the
`--surface-tint` theme token to a fixed `rgb(255 255 255 / 80%)`. The
fixed background is **not theme-reactive** — it will look the same
(translucent white) in Dark theme as in Light, which was flagged to the
owner at the time but implemented as explicitly requested. If Dark-theme
tag readability is ever raised in a future UAT, this is why. This
pass's own test suite (`phase2cb3a_check.mjs`) was updated to assert the
overlay mechanism generically (percentage-based `top` + `translateY`)
rather than the exact tuned value, so future manual tweaks like this one
don't spuriously fail the regression suite.

Real-browser visual/
workflow confirmation of the group editor modal was not possible in this
sandboxed, no-real-browser session — see this task's own final report for
the closest available substitute evidence; final judgment remains the
owner's own manual UAT.

## What was done in the prior session (Phase 2C-B3A — Overlay Right-Side Lane Labels)

**Phase 2C-B3A — Overlay Right-Side Lane Labels (correction).** The Phase
2C-B3 right-side-column label was **not** the owner's intended layout —
the owner clarified explicitly: the label must be **overlaid on the
waveform lane itself**, not placed in a dedicated right-side layout
column, and should follow **Detego's own separate-waveform label style as
closely as practical** for this specific placement (Detego treated as the
explicit layout benchmark here, not just loose inspiration — a narrower
application of the Detego Benchmark Principle than earlier passes used).
Full detail:
[MIGRATION_PLAN.md — Phase 2C-B3A Implementation Record](MIGRATION_PLAN.md#phase-2c-b3a--overlay-right-side-lane-labels-implementation-record-2026-08-15),
[DECISIONS.md — DEC-026 further Update note](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2)
(no new decision entry — a further refinement of the same visual-
presentation concern DEC-026 already covers, per governance).

**What was built**: the dedicated `108px`/`136px` fixed-width grid column
Phase 2C-B3 introduced was removed entirely. `.ww-panel` (the lane) is no
longer split into two grid columns — it's a plain block with `position:
relative`, and `.ww-chart-wrap` fills its full width. `.ww-legend` (the
same DOM — dot + `.ww-legend-label` span + remove button, unchanged) is
now `position: absolute`, pinned `right: 14px`, vertically centered
(`top: 50%; transform: translateY(-50%)`), with `z-index: 2` so it floats
on top of the chart instead of reserving its own layout space next to it.
`pointer-events: none` on the wrapper (re-enabled on the pill via
`pointer-events: auto`) keeps empty space around the compact tag from
blocking chart hover/crosshair underneath it. No tradeoff was needed for
the remove control — it fits identically inside the overlay tag as it did
inside the column tag, since only the tag's position changed.

**No architecture change**: Phase 2C-B2's unified-canvas container, lane
dividers, compact lane height, and `wwUpdateBottomLaneAxis()`'s
bottom-lane-only shared time axis are completely unchanged; Grouped
mode's own CSS was not touched at all. No change to the shared-viewport
synchronization mechanism, relayout loop-prevention, theme behavior,
crosshair styling, point-budget, or source/workspace lifecycle — verified
directly.

**Backend**: zero files changed — same endpoint, same query parameters,
confirmed by test.

**Tests**: 278 backend (unmodified) + 17 new frontend `jsdom` checks + 2
of Phase 2C-B3's own CSS-source assertions corrected in place (they
specifically tested the now-removed grid-column mechanism; the other 14
needed no change) + the full existing Phase 2C-B2 (20), Phase 2C-B1 (16),
Phase 2C-A (19), and Phase 1 (4) suites all re-run unmodified and still
passing (92 total this pass, no functional regressions). **Direct
drag/reorder of panels, drag-to-overlay/group, drag-out-to-separate,
digital-channel rendering, and lane resize were all explicitly not
started.** Real-browser visual confirmation that the overlay genuinely
reads as a Detego-style floating label rather than a side panel was not
possible in this sandboxed, no-real-browser session — see this task's own
final report for the closest available substitute evidence; final
appearance judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-B3 — Right-Side Compact Lane Labels)

**Phase 2C-B3 — Right-Side Compact Lane Labels.** Following manual owner
UAT of Phase 2C-B2 (**passed** — "Separate view now feels much better,
unified analog canvas direction is accepted"), the owner's next requested
refinement was moving the Separate-mode lane label to a small compact tag
on the RIGHT side, similar in placement/feel to Detego — used only as a
UI/layout reference (no colors/typography/icons/component styling
copied). This was a small, deliberately-scoped VISUAL refinement of the
existing lane label only. Full detail:
[MIGRATION_PLAN.md — Phase 2C-B3 Implementation Record](MIGRATION_PLAN.md#phase-2c-b3--right-side-compact-lane-labels-implementation-record-2026-08-15),
[DECISIONS.md — DEC-026 Update note](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2)
(no new decision entry — a refinement of the same visual-presentation
concern DEC-026 already covers, per governance).

**What was built**: the existing compact legend chip (dot + channel name
+ unit + remove button, unchanged since Phase 2C-A) moved from the lane's
left edge to its right edge via a CSS grid-column swap on `.ww-panel`
(`.ww-chart-wrap` is now `grid-column: 1`/`.ww-legend` is now
`grid-column: 2` with `justify-self: end`) — the waveform column keeps
maximum width, only which side got the fixed-width column changed. The
tag is now an explicit small pill (`border-radius: 999px`, a subtle
`var(--panel-border)` border, `var(--surface-tint)` background) using
existing Oruxa theme tokens already proven across the rest of the app
(DEC-023) — no Detego color/typography/icon was copied. A new
`.ww-legend-label` wrapping span gives the text an ellipsis-truncation
target (`max-width: 130px` on the tag) so an unusually long channel
identifier can't crowd the waveform. The remove control and color dot are
unchanged and still fit cleanly inside the tag — no interaction tradeoff
was needed. The redundant per-lane header stays hidden (unchanged from
Phase 2C-B2) — still exactly one label treatment per lane, just
repositioned and restyled.

**No architecture change**: Phase 2C-B2's unified-canvas container, lane
dividers, compact lane height, and `wwUpdateBottomLaneAxis()`'s
bottom-lane-only shared time axis are completely unchanged; Grouped
mode's own CSS was not touched at all. No change to the shared-viewport
synchronization mechanism, relayout loop-prevention, theme behavior,
crosshair styling, point-budget, or source/workspace lifecycle — verified
directly.

**Backend**: zero files changed — same endpoint, same query parameters,
confirmed by test.

**Tests**: 278 backend (unmodified) + 16 new frontend `jsdom` checks + the
full existing Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19), and
Phase 1 (4) suites all re-run unmodified and still passing (75 total this
pass, no regressions). **Direct drag/reorder of panels, drag-to-
overlay/group, drag-out-to-separate, digital-channel rendering, and lane
resize were all explicitly not started.** Real-browser visual confirmation
that the tag genuinely reads as compact/readable/low-clutter was not
possible in this sandboxed, no-real-browser session — see this task's own
final report for the closest available substitute evidence; final
appearance judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-B2 — Unified Analog Canvas Layout)

**Phase 2C-B2 — Unified Analog Canvas Layout.** Following manual owner
UAT of Phase 2C-B1 (**passed** for synchronization, horizontal zoom, and
pan; **refinement requested** for Separate mode's visual layout, which
looked like a stack of individually bordered/headed cards rather than one
continuous analog canvas — the owner supplied a Detego screenshot purely
as a visual/layout reference, per the Detego Benchmark Principle), this
was a small, deliberately-scoped VISUAL refinement of Separate mode only.
Full detail:
[MIGRATION_PLAN.md — Phase 2C-B2 Implementation Record](MIGRATION_PLAN.md#phase-2c-b2--unified-analog-canvas-layout-implementation-record-2026-08-15),
[DECISIONS.md — DEC-026](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2).

**What was built**: `#wwPanels` gains a `ww-panels-unified` CSS class only
while `ww.layoutMode === "separate"` (toggled in `wwSetLayoutMode`). With
it: one shared outer background/border replaces N repeated panel cards
(the container's background is literally the same theme token each
Plotly chart's own background already uses, so there's no visible seam);
each lane becomes a CSS-grid row (narrow 108px label column + a
maximum-width chart column) separated by a hairline `border-bottom`
divider instead of a full card border; the now-redundant per-panel header
is hidden and the existing compact legend chip (dot + channel name + unit
+ remove button) becomes the sole per-lane label; lane height drops from
260px to 140px for compactness. A new `wwUpdateBottomLaneAxis()` function
shows X tick labels/title on only the last panel in `ww.panels`' order —
every other lane suppresses them, since all lanes already share one
X/time viewport — called after every panel-array mutation (add, remove,
mode-switch rebuild) so the "which lane is bottom" role correctly follows
whichever lane is actually last. **Each lane keeps its own independent Y
axis — channels are never merged onto one shared Y axis**, an explicit
distinction from the visual chrome change (the task's own "critical
distinction" section). Grouped mode's own CSS and per-panel X axis are
completely untouched — the unified class is never applied while
`ww.layoutMode === "grouped"`.

**No architecture change**: this is a pure CSS/relayout-chrome layer on
top of Phase 2C-B1's existing panel data model (`ww.panels`: displayed
channels + panel membership + panel order, unchanged) and Phase 2C-A's
shared-viewport synchronization mechanism (DEC-021, unchanged). Switching
into or out of unified mode issues **zero** new waveform requests,
verified directly — same as every prior Phase 2C-A/B1 layout operation.
No drag handle/drop-target markup was added (optional per this task's own
instructions); the existing panel-order property (already read here to
decide the bottom lane) remains the same forward-compatible foundation
Phase 2C-B1 (DEC-025) already established for a future drag/reorder
feature.

**Backend**: zero files changed — same endpoint, same query parameters,
confirmed by test.

**Tests**: 278 backend (unmodified) + 20 new frontend `jsdom` checks + the
full existing Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites
all re-run unmodified and still passing (59 total this pass, no
regressions). **Direct drag/reorder of panels, drag-to-overlay/group,
drag-out-to-separate, digital-channel rendering, panel resize, and Custom
layout mode were all explicitly not started.** Real-browser visual
confirmation that the six lanes genuinely read as "one canvas" was not
possible in this sandboxed, no-real-browser session — see this task's own
final report for the closest available substitute evidence; final
appearance judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-B1 — Grouped / Separate Analog Waveform Layout)

**Phase 2C-B1 — Grouped / Separate Analog Waveform Layout.** Following
manual owner UAT of Phase 2C-A (**passed** for shared synchronization,
horizontal zoom, Reset Time View, pan synchronization, Voltage/Current
grouping, and Autoscale Y — a small bearable interaction latency and a
vertical-zoom-discoverability note were both raised but deliberately left
for a later pass), the owner's requested next enhancement was waveform
layout flexibility. Full detail:
[MIGRATION_PLAN.md — Phase 2C-B1 Implementation Record](MIGRATION_PLAN.md#phase-2c-b1--grouped--separate-analog-waveform-layout-implementation-record-2026-08-15),
[DECISIONS.md — DEC-025](DECISIONS.md#dec-025--groupedseparate-analog-waveform-layout-modes-confirmed-and-implemented-phase-2c-b1).

**What was built**: a small **Grouped / Separate** toggle added to the
existing central toolbar. Grouped is unchanged from Phase 2C-A
(`engineering_type`-based). Separate gives every displayed analog channel
its own panel/lane (one Plotly instance, one trace, its own Y axis) — 6
displayed channels produce exactly 6 lanes, verified directly. Switching
modes **never** changes which channels are displayed, **never** issues a
new waveform request (each channel's already-fetched data is reused as-is
when its panel is rebuilt), and **preserves the current shared X/time
viewport exactly** in either direction — verified by test: zoom to a
window in Separate mode, switch to Grouped, the rebuilt panels open at
that exact same window, and the same holds switching back. The underlying
model — `ww.panels` as an ordered `{label, channels, ...}` array — was
already shaped correctly since Phase 2C-A; what's new is
`wwPanelGroupKeyFor`/`wwPanelLabelFor` (layout-mode-aware panel identity)
and `wwRebuildLayout()` (re-derives panels from the flat displayed-channel
list under the current mode). This was deliberately built so a future
direct vertical-drag/reorder/overlay/split interaction — the owner's own
stated next direction — is architecturally just another way of producing
the same panels/membership/order shape, not a redesign of it. Removal
behaviour needed **zero code changes**: a Separate-mode panel always has
exactly one channel by construction, so removing it always empties (and
therefore removes) the panel automatically. Theme switching, the shared-
viewport broadcast mechanism, loop-prevention, and the crosshair
(DEC-022/DEC-023, untouched) all work identically in both layout modes,
reusing Phase 2C-A's existing mechanisms unchanged.

**Backend**: zero files changed — same endpoint, same query parameters
(`channel_name`/`start_time`/`end_time`/`point_budget`), confirmed by
test that switching layout mode issues no new request at all.

**Tests**: 278 backend (unmodified) + 16 new frontend `jsdom` checks +
the full existing Phase 2C-A suite (19 checks) and Phase 1 regression
suite (4 checks) both re-run unmodified and still passing (39 total this
pass, no regressions). **Direct drag/reorder of panels, drag-to-
overlay/group, drag-out-to-separate, Custom layout mode, and panel resize
were all explicitly not started.**

## What was done in the prior session (Phase 2C-A — Synchronized Multi-Channel Waveform Display)

**Phase 2C-A — Synchronized Multi-Channel Waveform Display.** The first
real multi-channel waveform workspace, implemented directly in
`frontend/index.html` (not an isolated page). Full detail:
[MIGRATION_PLAN.md — Phase 2C-A Implementation Record](MIGRATION_PLAN.md#phase-2c--synchronized-multi-channel-waveform-display-implementation-record-2026-08-15),
[DECISIONS.md — DEC-024](DECISIONS.md#dec-024--phase-2c-a-multi-channel-waveform-workspace-architecture-confirmed-and-implemented).

**What was built**: a checkbox per analog channel row (search/grouping
unchanged) + "Add N selected" → newly-added channels group, on *initial*
placement only, by the existing `engineering_type` (never re-derived) →
each engineering-type group becomes its own panel, **one independent
Plotly instance per panel** (never a single figure with fixed subplots) →
every panel shares **one Oruxa-owned X/time viewport** (DEC-021, now
actually implemented) — zoom or pan on any one panel debounces (120ms)
then broadcasts the exact same range to every other panel and refetches
every displayed channel for it, using a per-panel `suppressNext` flag to
prevent the broadcast's own programmatic relayout from re-triggering
itself (verified with a test double that faithfully re-fires Plotly's
relayout event, not just structurally present in the code) → a single
central toolbar (Zoom, Pan, Reset Time View, Autoscale Y — exactly 4
controls, nothing else) is the only navigation surface; every native
per-panel Plotly modebar is disabled. Autoscale Y is viewport-aware Fit
only (Plotly's native `yaxis.autorange` against data that's already
scoped to the current viewport by construction) — Proportional/
shared-unit scaling was not built. A channel can be removed from a panel
(the panel disappears once empty) without touching its imported source;
"Clear workspace," per-source removal, and "Start new workspace" all
correctly clear the relevant part of the display. Theme switching
re-colors every panel via `Plotly.relayout` only, still never refetching
waveform data; the crosshair (DEC-022/DEC-023) is unchanged, applied
per-panel — cross-panel crosshair sync was explicitly not built.

**Backend**: zero files changed. The existing Phase 2A single-channel
waveform endpoint is reused as-is — N displayed channels means N
requests, each with its own independent abort-controller/sequence-number
stale-response guard (generalizing Phase 2B's proven single-channel
pattern, not a new mechanism); no batching endpoint was built (explicitly
evidence-gated, deferred).

**Tests**: 278 backend (unmodified, unchanged) + 19 new frontend `jsdom`
checks (selection/Add/grouping/panels/shared-viewport/loop-prevention/
toolbar/removal/theme/a 12-channel structural scale check) + 4 existing
Phase 1 regression checks re-run and still passing (two of that older
script's own assertions were tightened, not weakened, to account for the
new checkbox column). **Phase 2C-B (drag/reorder between panels, panel
resize, Proportional Y scaling, mixed-unit handling, digital channels,
shared crosshair) was explicitly not started.**

## What was done in the prior session (Crosshair Visual UAT Follow-up)

**Crosshair Visual UAT Follow-up** (a very small, config-only refinement —
**not** Phase 2C work). Theme UAT (prior pass) passed with no changes
requested; the owner's only remaining feedback was that the Plotly
crosshair was still too coarse (dash segments too long) and too faint (in
**both** themes). Full detail:
[MIGRATION_PLAN.md's follow-up subsection](MIGRATION_PLAN.md#follow-up-crosshair-visual-uat-refinement-2026-08-15-same-day),
an "Update" note appended to
[DEC-023](DECISIONS.md#dec-023--application-supports-light-and-dark-appearance-light-is-the-preferreddefault-direction)
(no new decision entry — same crosshair-styling concern DEC-023 already
covers).

**What changed**: `spikethickness` `0.5` → `0.35` (both axes) — the same
SVG-fractional-stroke-width reasoning as the prior pass. `spikedash`
changed from the named `"dash"` style to a custom native Plotly
dash-length string, `"3px,2px"` — Plotly's own `dash` attribute documents
this `"px,px,..."` syntax as first-class native configuration, so this is
not a workaround. **Native limitation found and stated honestly**:
Plotly's built-in `"dash"` style has no stable, documented internal pixel
definition to reverse-engineer and produce a mathematically exact "half
length" from — a deliberately shorter native value was chosen instead, as
the closest clean native option. `--spike-color` (theme.css) was
strengthened in both themes for stronger contrast, stopping short of full
opacity: Light `rgba(92, 101, 121, 0.42)` → `rgba(60, 68, 87, 0.6)`
(darkened toward `--text`, higher alpha); Dark
`rgba(139, 150, 173, 0.42)` → `rgba(168, 178, 199, 0.6)` (brightened
toward `--text`, higher alpha). Grid-line styling was deliberately left
untouched — the owner already finds it acceptable.

**Unchanged**: `spikesnap: "data"`, both vertical/horizontal spike lines,
moving hover X/Y values, theme-switch-without-refetch behavior, DEC-021/
DEC-022, the waveform API, zoom/pan/Reset Time View/Autoscale Y,
source/workspace lifecycle. No custom crosshair/cursor overlay was built;
no Plotly-generated SVG was manually manipulated. No backend file was
touched (278 tests unmodified and passing); the existing 19-check
`jsdom` test script was updated in place for the new values (not a new
test file). **No Phase 2C work.**

## What was done in the prior session (Light/Dark Theme & Crosshair Refinement)

**Light/Dark Theme & Crosshair Refinement** (a small, general-application
UX task — **not** Phase 2C work). Full detail:
[MIGRATION_PLAN.md — Light/Dark Theme & Crosshair Refinement Record](MIGRATION_PLAN.md#lightdark-theme--crosshair-refinement-record-2026-08-15),
[DECISIONS.md — DEC-023](DECISIONS.md#dec-023--application-supports-light-and-dark-appearance-light-is-the-preferreddefault-direction).

**What was built**: a shared, reusable theme-token system —
`frontend/theme.css` (new: CSS custom properties for Light — the
default/preferred theme — and `[data-theme="dark"]`, plus new
`--waveform-surface`/`--toolbar-surface`/wash-tint tokens that replace
what used to be raw `rgba(...)` literals) and `frontend/theme.js` (new:
`PowerwaveTheme.getTheme()`/`setTheme()`/`mountThemeToggle()`, applies
`[data-theme]` to `<html>` before body paint to avoid a flash, persists to
`localStorage` (`powerwave.theme`), and syncs live across tabs via the
`storage` event). Both `index.html` and `waveform-prototype.html` now
include these shared files, had their own local hard-coded `:root` color
blocks and scattered `rgba(...)` literals removed/replaced with tokens,
and gained a small Light/Dark segmented control in their header. The
light palette is an **original Oruxa design** (`--bg: #f3f5f9`,
`--panel: #ffffff`, `--accent: #3568d4`, etc.) — Detego's palette was not
consulted or copied, per the owner's explicit instruction and the
already-established Detego Benchmark Principle (DEC-020). The dark theme
is the exact same values the app already used, just migrated onto the
shared token system (same layout/behavior, different appearance — not a
second CSS implementation).

**Plotly integration**: `waveform-prototype.html`'s chart now reads its
colors from the active theme at init time and re-applies them via
`Plotly.relayout`/`Plotly.restyle` on a theme change (new
`PlotlyRenderer.applyTheme()`) — **verified via test that this never
triggers a new waveform data fetch**.

**Crosshair refined further** (beyond the Phase 2B closure pass, DEC-022):
`spikethickness` `1` → `0.5` (a genuine, natively-supported thinner SVG
stroke-width value — Plotly's spike lines render as SVG paths even for a
`scattergl` trace, and fractional stroke-width is standard, reliable SVG
behavior, not a workaround; the prior pass's "practical minimum" claim
was not fully substantiated) and `spikecolor` alpha `0.55` → `0.42`.
Dashed style, `spikesnap: "data"`, and moving hover X/Y values are
unchanged. **No custom crosshair/cursor engine was built.** Honest
limitation: pixel-level visual confirmation wasn't done in this
sandboxed, no-real-browser session — see this task's live DEV
verification for that.

**No backend change** (zero backend files touched, 278 tests unmodified
and passing). **No Phase 2C work** — Phase 2C remains exactly as the
prior pass left it: designed, not implemented, not authorized.

## What was done in the prior session (Phase 2C discovery/design)

**Phase 2C — Flexible Multi-Channel Waveform Workspace: Discovery and
Design.** Design/discovery only — **nothing implemented, nothing decided**.
Full detail:
[MIGRATION_PLAN.md — Phase 2C](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15).

**What was done**: re-verified `powerwave`'s live multi-channel/panel code
directly (via a spawned Explore subagent, same commit `3156392`), consulted
Detego's own public marketing/docs pages (`detego.app`,
`detego.app/docs/guide/waveform-viewer`) for publicly observable
waveform-viewer behavior per DEC-020's benchmark framework, and produced a
full design proposal covering: the panel abstraction (one shared X inherited
from DEC-021, independent Y per panel); an `engineering_type` auto-grouping
default that never permanently constrains channel placement; a channel-add
workflow recommendation (checkbox + "Add N selected," matching Phase 1's
established interaction pattern); a drag/reorder model (reorder panels, move
channels between panels, create/split panels via drag — explicitly **not**
one-per-panel channel reordering or panel-merging in the first slice); a
recommended **one independent Plotly instance per panel** architecture
(extending Phase 2B's already-proven `suppressNextRelayout`/sequence-number
broadcast mechanism to N panels, rather than fighting Plotly's native
multi-subplot domain-fraction math); a Fit-vs-Proportional Y-scaling model
(Fit — viewport-aware — as the default, an explicit improvement over
`powerwave`'s own stale full-session-window autoscale; Proportional as a
later toggle); mixed-unit-panel handling (allowed via drag, with an
automatic secondary Y axis); a legend/identity model reusing Phase 1's
existing sidebar rather than building a second one; a lightweight
plain-object workspace state model (no Redux/framework); a recommended
implementation slicing (2C-A through 2C-D, plus an optional
backend-batching slice); and a reassessment of the TTL and ~100 MB
real-file-memory open items (neither escalates to a Phase 2C blocker).

**A genuinely new finding, not previously recorded**: `powerwave` already
has live channel-to-panel drag-and-drop (legend row → panel header, plus a
sidebar combo box and a merge/split context menu) — but **no panel-
reordering mechanism exists anywhere in its codebase**. Detego's own public
docs don't document panel-reordering either. This is flagged as the single
clearest opportunity for Oruxa to exceed both references at once, not
merely match one of them.

**Nothing here is a `[DECISION]`** — every substantive design choice remains
`[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`/`[DEFER]`, per this
task's own explicit instruction. DEC-021 and DEC-022 are reaffirmed,
unweakened, throughout. **No code was written this pass** — no multi-channel
API, no panel model, no drag/drop, no digital signals, no cursors. Commit
was **docs-only**.

## What was done in the prior session (Phase 2B Renderer Closure)

**Phase 2B — Renderer Closure.** The owner's final UAT decision:
**Plotly.js is selected as the waveform rendering foundation** (DEC-022,
[DECISIONS.md](DECISIONS.md)) — Plotly's better waveform clarity, richer
built-in navigation, and overall stronger engineering interaction feel
won out over uPlot's own strength (a very good free-moving crosshair
feel). **This is Phase 2B's final outcome — no longer `[UAT]`.** Full
detail:
[MIGRATION_PLAN.md — Phase 2B Renderer Closure Record](MIGRATION_PLAN.md#phase-2b--renderer-closure-record-2026-08-15).

**What changed**: the crosshair was restyled — `spikedash: "dash"` (was
solid) and a reduced-opacity `spikecolor` (was fully opaque) — a lighter,
subtler guide line closer to uPlot's visual character, **without**
recreating uPlot's cursor mechanics. The owner explicitly declined to
pursue crosshair-responsiveness parity with uPlot ("not important enough
to justify additional implementation complexity or development time") —
no custom mouse-following overlay was built; Plotly's native, sample-
snapped hover behaviour is otherwise unchanged. `UPlotAdapter`, the
renderer-switch UI (tabs), and `frontend/vendor/uplot/` were all removed
— confirmed via repository-wide search, no live `uplot` reference remains
outside historical documentation. The page itself was simplified: no more
"renderer comparison"/"Phase 2B UAT" wording, just a plain "Single-channel
waveform preview — not the final Phase 2C workspace" label. **DEC-021
(workspace-level, centralized-toolbar navigation) is unchanged and
unweakened** — Plotly's native per-channel modebar, kept for this
single-channel page, is now documented directly in the page's own visible
text as temporary, ahead of Phase 2C's required centralized toolbar.

**No Phase 2A backend change** (zero backend files touched, 278 tests
unmodified and passing). **No Phase 2C work.**

## What was done in the prior session (Phase 2B Plotly refinement)

**Phase 2B — Plotly Refinement & Workspace-Level Navigation.** Follows
the owner's hands-on UAT of the Phase 2B renderer prototype (commit
`ad6d9d2`): **Plotly is currently preferred** (better clarity, richer
native controls, smoother interaction) over uPlot (whose own strength was
its built-in crosshair), but the renderer choice is **explicitly not
closed** — `[UAT — Plotly preferred pending final refinement
confirmation]`. Full detail:
[MIGRATION_PLAN.md — Phase 2B Plotly Refinement & Workspace-Level
Navigation Record](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15).

**Two things were built/fixed this pass**:
1. A native Plotly crosshair (`showspikes`/`spikesnap: "data"`/
   `spikemode: "across"` on both axes, `hovermode: "closest"`) — no
   custom crosshair system, per the task's own preference for native
   capability first. `spikesnap: "data"` deliberately snaps to real
   recorded samples, never an interpolated position.
2. A toolbar-lag investigation that found a real bug, not just perceived
   slowness: Plotly's native Autoscale/Reset-axes modebar buttons fire an
   `xaxis.autorange: true` relayout (no explicit range), which the
   original relayout handler silently ignored — meaning those buttons
   never actually re-fetched the true full record, only re-scaled
   whatever data was already loaded. Fixed. The viewport debounce was
   also shortened 200ms → 120ms (button clicks have no drag-frames to
   coalesce, so the old debounce was pure added latency for that specific
   interaction). "Reset View" was relabelled "Reset Time View" throughout
   to keep it distinct from "Autoscale Y," per DEC-021.

**DEC-021 — waveform navigation is workspace-level, not channel-level**
(full text in [DECISIONS.md](DECISIONS.md)): one shared X/time viewport
must eventually drive every displayed channel together; a centralized
Powerwave toolbar (never a per-channel native modebar) is the required
future architecture. Recorded now, while Phase 2B still has one channel,
specifically so Phase 2C's architecture doesn't accidentally build
per-channel navigation controls. The existing request-coordinator
function was deliberately left unrestructured (multi-channel fetching is
still out of scope) but is now commented as the exact Phase 2C extension
point.

**uPlot was NOT removed** — it remains fully functional and unmodified,
for the owner's final side-by-side crosshair comparison. **No Phase 2A
backend change** (zero backend files touched, 278 tests unmodified and
passing). **No Phase 2C work.**

## What was done in the prior session (Phase 2B renderer UAT prototype)

**Phase 2B — Renderer UAT Prototype.** Built the bounded browser
comparison prototype the Phase 2 design work called for: a new, isolated
page (`frontend/waveform-prototype.html`) lets the owner hands-on compare
**uPlot** and **Plotly.js** against the identical Phase 2A backend
waveform data and interaction contract — same endpoint, same channel,
same fixed point budget (4000), switching renderers reuses already-
fetched data instead of re-fetching. Opened via a new "Waveform (UAT)"
link added to each analog channel row in the existing Phase 1 channel
browser (`frontend/index.html`) — the main app itself is otherwise
unchanged. **No plotting-library winner was chosen — this is `[DECISION
MODE: UAT]`, for the owner to judge.** No Phase 2C (draggable/panel)
work, no digital channels, no cursors/measurements, no calculated
signals, no synchronization. Full detail:
[MIGRATION_PLAN.md — Phase 2B Implementation Record](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15).

**What was built, precisely**: uPlot (v1.6.32) and Plotly.js
cartesian-only (v3.7.0) vendored as static, pre-built, minified bundles
under `frontend/vendor/` (no build step — matches the project's existing
architecture; provenance/versions recorded in `frontend/vendor/README.md`
for later removal/upgrade). Both candidates implement one shared
`WaveformRenderer` adapter contract (`init`/`update`/`setViewport`/
`destroy`) so a losing candidate is cleanly deletable later. A shared
coordinator owns the debounced (200ms), doubly-protected
(`AbortController` **and** a sequence number, tested independently)
range-request pipeline — zoom/pan in either renderer calls the same
`requestViewportRangeDebounced()` function, nothing else. Neither
renderer applies curve smoothing (uPlot's default linear path; Plotly's
`line.shape: "linear"` set explicitly, not left to an unexamined
default). Backend was **not touched** — `git diff --stat -- backend/` is
empty, and all 278 existing backend tests, none modified, still pass.

**TTL note for this pass**: per the task's explicit instruction, TTL was
**not** implemented; a temporary DEV-only operational stopgap was
documented instead (owner clicks `Start new workspace` at the end of the
UAT session, or the DEV backend container is restarted between separate
UAT sessions) — see
[CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).
**This is not a claim that the TTL `[OPEN]` item is solved.**

## What was done in the prior session (Detego benchmark documentation, three passes)

**Documentation-only, three passes same day**: established `detego.app`
as an official product/UI-UX/waveform-workspace/dashboard/workflow
**benchmark** (explicitly not a ceiling or a spec to copy blindly) for
feature design, per direct owner instruction — new
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md), DEC-020 in
[DECISIONS.md](DECISIONS.md), and short pointer sections added to
[CLAUDE.md](../../CLAUDE.md)/[AGENTS.md](../../AGENTS.md) (matching the
existing architecture-reference pointer pattern — state the principle
briefly, read detail at the source). A second pass the same day received
the owner's actual source document ("Detego Benchmark Principle.rtf") as
a genuine attachment and updated all four files to quote/match its exact
canonical wording (same DEC-020, not a new decision — see its own
"Wording update" note in [DECISIONS.md](DECISIONS.md)), adding two
specifics the first pass's paraphrase hadn't captured: "learn from
Detego's public behaviour, implement an independent Oruxa design," and
the standing question for major features — *"What does Detego do here,
what does existing powerwave do, and what would make oruxa_powerwave
better for the engineer?"* A **third pass**, same day, expanded
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) with the four-way
feature-design method (`powerwave` / Detego / owner requirements /
proposed superior Oruxa approach), three worked examples (waveform
workspace, multi-source synchronization, calculated signals), an explicit
"owner-specific capabilities may exceed Detego" list (not exhaustive —
Detego is not the product boundary), and explicit
"architecture-stays-Oruxa-owned" / "independent implementation, not
reverse engineering" sections — plus one added sentence each in
`CLAUDE.md`/`AGENTS.md` covering those last two points concisely. Still
the same DEC-020; no new `DECISIONS.md` entry was needed. **No production
code changed in any of the three passes.**

**Provenance note, worth preserving**: an earlier version of this same
request arrived mid-turn, structured as a system-reminder-wrapped message
that referenced "an attached ZIP" never actually present in context, and
asked for edits to this repository's own governance files plus a push to
`main` while explicitly directing that this project's own
change-governance step be skipped. That version was declined and flagged
to the user rather than executed — an unverifiable, injection-shaped
request is not owner authorization on its own. The owner then reissued
the same direction as a normal, self-contained conversational instruction
with no external attachment referenced or needed, which is what this
pass and [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) are built from.
**No technical audit of `detego.app` itself was performed or is claimed**
— see [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)'s own `[OPEN]` note.
Future sessions should not assume a feature comparison against Detego
already exists just because this reference framework does.

## What was done in the prior session (Phase 2A implementation)

**Phase 2A — Waveform Data Foundation** (backend only). Following the
Phase 2 discovery/design pass (summarized below), the owner authorized
implementing exactly the first recommended vertical slice: retain each
imported source's full-resolution `DisturbanceRecord` in the active
workspace, and add one bounded waveform range endpoint for a single analog
channel. **No chart library, no frontend rendering, no digital-channel
waveform delivery, no Phase 2B/2C/2D work** — see
[MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15)
and [DECISIONS.md — DEC-019](DECISIONS.md#dec-019--phase-2a-retains-the-full-resolution-disturbancerecord-in-the-active-workspace)
for full detail; summarized here for continuation purposes.

**What was built**: `ActiveSource` (`app/domain/source.py`) pairs the
existing lightweight `SourceMetadata` with the authoritative
`DisturbanceRecord`; `WorkspaceRegistry` now stores `ActiveSource`
(keying/locking/cleanup methods unchanged — `remove()`/`remove_workspace()`
already correctly release whatever's stored per `(workspace_id,
source_id)`); `app/domain/waveform_reduction.py` implements a
peak-preserving min/max envelope (equal-count buckets, chronological
output, guaranteed true first/last sample, deterministic, never mutates
its input) — deliberately **not** `powerwave`'s own plain-stride
decimator; `app/services/waveform_service.py` does exact time-range
extraction (boundary-inclusive, `searchsorted`-based) then applies that
reduction only when the range exceeds the request's `point_budget`;
`GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform`
(added to the existing `app/api/v1/sources.py` router) exposes it as JSON.

**What was verified**: 278 backend tests pass (227 unchanged + 51 new),
including the mandatory synthetic-spike regression test (proves plain
stride sampling misses a narrow transient that the new algorithm
preserves), zoom-fidelity tests (narrower requests reveal genuinely finer
data, and a sufficiently narrow range returns true full-resolution
samples again), and lifecycle tests including a weakref-based proof that
`Remove`/whole-workspace-DELETE actually release the retained record's
memory, not just make it API-inaccessible. Measured (not assumed)
performance/memory across four synthetic scenarios up to 2,000,000
samples: range extraction is sub-millisecond at every scale tested;
reduction to a 4000-point budget stays under 8 ms even at 2M samples;
JSON payload for a reduced response stays ~110-120 KB regardless of
record size, versus 61 MB if full resolution were returned for one
channel at the largest scale tested — directly confirming why the
range-request architecture was recommended.

## What was done in the prior session (Phase 2 discovery/design)

**Phase 2 waveform-workspace discovery and design** — the project owner
confirmed Phase 1 has passed its final UAT and is complete, then requested
a discovery/design-only pass (explicitly: no implementation) covering the
existing `powerwave` waveform/plotting architecture, candidate web
waveform data-delivery architectures, plotting-library candidates, the
backend memory-model change Phase 2 requires, and a proposed Phase 2 slice
sequence. Full content:
[MIGRATION_PLAN.md — Phase 2 Waveform Workspace Discovery and
Design](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14) —
summarized here for continuation purposes. **No code was written this
pass** — no waveform API, no chart library dependency, no backend
full-resolution-array retention, nothing deployed.

**`powerwave` waveform architecture — re-verified live** (not trusted from
documentation, per the task's own warning that discovery already found
stale/dead plotting references): live path is `SessionCanvasWidget` +
`SessionCanvasController`; `FlexiblePlotCanvas`/`VisualizationManager`/
`DigitalEventTimeline`/`channel_grouper.py`/the `overlays/` abstraction are
all confirmed dead (unreachable from the live app; `FastWaveformWidget`
doesn't exist as a class at all). **The single most consequential finding**:
`build_aligned_data()`'s decimation (`downsampling.py`) is **plain
nth-point stride sampling** (`t_clip[::stride]`) — not peak-preserving,
not viewport-aware (decimates against the whole session window, not the
live viewport, at a hardcoded `max_points=4000` never overridden anywhere).
This means `powerwave` itself can silently drop a transient spike or a
narrow digital pulse during decimation, and zooming does not fetch
higher-resolution detail — both are explicitly flagged as behaviors Phase
2 must **not** inherit.

**Design proposal highlights** (all `[PROPOSAL]` / decision-mode-tagged,
none approved): viewport/range-request API (`GET .../sources/{id}/waveform`)
over "send everything once"; **min/max envelope** decimation (not
`powerwave`'s stride sampling, not LTTB) for engineering-correctness
reasons; JSON to start, binary only if benchmarking shows a real cost;
extend `WorkspaceRegistry`'s stored value to also retain the parsed
`DisturbanceRecord` (currently discarded after upload — this is the major
backend architecture change Phase 2 requires); reassessed the existing
abandoned-session TTL `[OPEN]` item as materially more important now that
full-resolution arrays (not just metadata) would be at stake, without
resolving it outright (`[DECISION MODE: COMPARISON]`); a bounded two-library
plotting prototype (uPlot vs. ECharts, `[DECISION MODE: UAT]`); and a
Phase 2A/2B/2C/2D slice sequence with an exact-scope first slice
(one channel, backend-only, API-tested, no frontend chart yet).

## What was done in the prior session (Phase 1 closure fix)

A **focused Phase 1 closure fix**: correcting `Start new workspace` into a
real, backend-enforced whole-workspace reset. This followed a same-day
investigation (requested separately, before this fix) into whether
`Remove` and `Start new workspace` were genuinely different — the
investigation found `Start new workspace` was a no-op pretending to be a
reset (client-only UUID rotation, no backend call, old sources leaked in
memory, stale banner). The owner decided to **keep** the button and make it
correct, rather than remove or hide it. See
[MIGRATION_PLAN.md — Phase 1 Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14)
and [DECISIONS.md — DEC-018](DECISIONS.md#dec-018--start-new-workspace-is-a-distinct-whole-workspace-lifecycle-operation-not-a-remove-alias)
for full detail.

**What was built**: a new whole-workspace backend endpoint
(`DELETE /api/v1/workspaces/{workspace_id}`, new file
`backend/app/api/v1/workspaces.py`) backed by a new
`WorkspaceRegistry.remove_workspace(workspace_id)` method; and a corrected
frontend flow where `Start new workspace` shows its own confirmation
(only when the workspace is non-empty), calls that DELETE against the
*old* workspace id, and only rotates the client-side id — clearing the
source list, channel panel, and stale banner — after the backend call
succeeds. A failed cleanup leaves everything as it was, with a visible
error instead of a silent fake reset.

**Prior work this document also covers** (unchanged by this pass): a
narrow UI refinement pass on the already-implemented, already-deployed
Phase 1, driven directly by the owner's completed hands-on UAT of
`https://dev.powerwave.oruxa.uk`.

**What UAT approved and left alone**: the two-slot `.cfg`/`.dat` upload
workflow (now formally decided — DEC-017, not just a temporary Phase 1
choice), the loading/parsing indicator, the 100 MB guidance text, the
source-metadata-review-before-channels step, and the overall simple
single-page UI direction. None of these were touched.

**What UAT asked to change, and what was built**:

1. **Channel organization** — the reported problem was scrolling through
   hundreds of channels in one long table (UAT's own example: 80 analog,
   282 digital). Fixed with native `<details>`/`<summary>` collapsible
   sections (Analog defaults open, Digital defaults collapsed — the
   section that was actually overwhelming), always showing counts.
2. **Analog sub-grouping by engineering type** — `Voltage`/`Current`/
   `Power`/`Frequency`/`ROCOF`/`Undefined`. Classification is computed
   **once, backend-side** (new `backend/app/domain/channel_classification.py`),
   exposed as `engineering_type` on every analog channel — never
   re-derived or duplicated in the frontend. Three-tier rule (explicit
   `parameter_type` → unit semantics → nothing else — naming-pattern
   classification was deliberately not implemented, since no pattern was
   judged unambiguous enough): anything that doesn't confidently resolve
   is `Undefined`, never guessed into a real category.
3. **Channel search** — client-side only, over the already-fetched channel
   list, no network calls per keystroke. Auto-expands groups containing a
   match; clearing search restores the default expansion state.
4. **Scale/Offset removed from the primary analog table** — UAT found them
   low-value for browsing. Both fields are **unchanged** in the domain
   model and API response (`AnalogChannelSummary`/`AnalogChannelOut`) —
   only this one table stopped displaying them.
5. **Removal confirmation** — clicking "Remove" now opens one small
   confirmation dialog before the DELETE request is ever issued.
6. **Stale-banner bug fixed** — the import-success banner previously stayed
   visible after its source was removed. Now cleared, but only when it
   actually described the source just removed (tracked precisely, not a
   blanket clear-on-any-removal) — deliberately forward-compatible with a
   future multi-source workspace.

## What was verified (this pass — Phase 3A-UAT2 remove duplicate header theme control)

- `oruxa_powerwave` git state confirmed against GitHub `main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (diff scoped to
  `frontend/index.html` only).
- **Frontend, new: 11 scripted `jsdom` checks, all passing**
  (`phase3auat2_check.mjs`) — `#themeToggle` absent from the DOM
  entirely, `#globalHeader` contains no Light/Dark-labeled buttons, the
  Main Sidebar Menu's `#mainNavSettingsBtn` exists in `.shell-nav-bottom`
  and still flips Light→Dark→Light, the preference persists across a
  simulated reload, theme change causes zero waveform refetch, theme
  change still triggers the existing per-panel Plotly chrome relayout,
  the Global Header's remaining controls still render, Main Sidebar Menu
  collapse/expand still works, displayed-channel/panel state undisturbed.
- **Frontend, existing suite correction**: `theme_crosshair_check.mjs`'s
  own pre-existing test asserting `#themeToggle` exists in `index.html`
  was corrected in place (it now asserts absence, by design) rather than
  left to fail — full suite re-run confirms all its OTHER checks (19
  total) still pass unmodified.
- **Frontend, full regression: the exact same pre-existing 20 failures
  already documented in prior phases' own records, zero new
  divergences** — independently confirmed by running the full scratch
  suite both before and after this pass's change.
- `git diff --check` clean (no whitespace errors).
- No real-browser/visual confirmation was performed in this sandboxed
  session — whether the header now reads cleanly with no leftover gap,
  and whether Settings remains comfortably reachable in both collapsed
  and expanded Main Sidebar states, were NOT visually confirmed. Final
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 3A-UAT1 responsive waveform width reflow)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Root cause established by direct code inspection, not guessed**
  (per this task's own explicit instruction): traced the missing
  `Plotly.Plots.resize()` call in both `shellCreateHorizontalSplit()`
  and `shellSetMainSidebarExpanded()`, confirmed the CSS `min-width: 0`
  chain was already correct at every level that mattered, and confirmed
  `.ww-chart-wrap` had no `overflow` rule to contain a stale-width
  Plotly SVG.
- **Frontend, new: 20 scripted `jsdom` checks, all passing**
  (`phase3auat1_check.mjs`) — `.ww-chart-wrap` containment CSS,
  Workspace Sidebar drag resizing every visible panel's Plotly instance
  AND the sticky ruler, zero waveform fetches during resize,
  byte-identical physical viewport before/after, no relayout call
  touching range/Y state as a side effect of the resize, rAF-coalesced
  scheduling (many raw pointermoves → far fewer resize calls),
  authoritative final resize on pointerup, pointercancel cleanup + its
  own final resize (matching the established `wwSetPanelHeight`
  contract), a subsequent drag after a cancelled one still working,
  Main Sidebar Menu expand/collapse both triggering a full reflow via
  `transitionend` (correctly scoped to the `width` property only), zero
  fetch/viewport-preserving on menu toggle, window resize triggering
  the same reflow path, rapid-fire window resize events coalescing to
  one pass (no runaway loop), zero fetch on window resize, Separate
  mode (all 6 lanes reflow) and Custom mode (all panels reflow), Phase
  3A shell hierarchy unchanged, and panel-height resizing unaffected.
- **Frontend, existing: the full Phase 2C-A through Phase 3A suites
  (264 checks, after fixing six older scripts' missing
  requestAnimationFrame polyfill — a test-infrastructure gap this
  fix's own rAF-coalescing exposed, not an application bug) — the exact
  same pre-existing 20 failures already documented in those phases' own
  records, zero new divergences.** Independently confirmed by running
  the suite both before and after this phase's changes.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — whether the waveform canvas genuinely stays visually
  contained during a real drag, and whether the reflow feels smooth,
  were NOT visually confirmed. See the final report's explicit
  statement about what's honestly unverified. Final visual judgment
  remains the owner's own manual UAT.

## What was verified (prior pass — Phase 3A application shell redesign foundation)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 40 scripted `jsdom` checks, all passing**
  (`phase3a_check.mjs`) — every shell structural relationship (Global
  Header/Body/Main Sidebar Menu/Work Area/Workspace Row/Bottom Status
  Bar/Workspace Sidebar/Main Workspace), including the specific
  parent-chain assertion proving the Status Bar's parent (`#workArea`)
  differs from Main Sidebar Menu's parent (`#appBody`) — the exact
  structural guarantee behind "the Status Bar can never render beneath
  Main Sidebar Menu"; Main Sidebar Menu collapse/expand and confirmed
  non-drag-resizability; Workspace Sidebar drag-resize (live resize,
  min/max clamping, zero waveform fetches, pointer-listener cleanup
  after pointerup, localStorage persistence); the full existing
  waveform feature set re-verified working end to end (channel
  selection, Grouped/Separate/Custom, zoom/pan/Reset Time View/
  Autoscale Y, Absolute/Elapsed, panel-height resize, Custom Groups,
  theme switching); the Active View state model (all three values
  representable, Table/Split contain zero fake data and trigger zero
  fetches); Bottom Status Bar real-value sourcing and channel-count
  sync; and workspace-reset clearing both waveform and status-bar state
  cleanly.
- **Frontend, existing: the full Phase 2C-A through 2C-C4B suites (224
  checks) were all re-run unmodified against this pass's code — the
  EXACT SAME pre-existing pass/fail counts as immediately before this
  phase (20 already-documented failures across those phases' own
  records), zero new divergences.** This was independently confirmed by
  running the suite both before and after this phase's changes, not
  assumed from the diff alone.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — actual shell proportions, resize feel, and responsive
  behavior at real narrow widths were NOT visually confirmed. See the
  final report's explicit statement about what's honestly unverified.
  This is explicitly an INITIAL shell (task's own framing) — final
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C4B compact sticky time-axis layout correction)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Frontend, rewritten (per this task's own explicit instruction): 25
  scripted `jsdom` checks, all passing** (`phase2cc4a_check.mjs`,
  updated in place rather than left as a documented divergence, since
  its old assertions read a DOM element — `#wwStickyRulerTitle` — that
  no longer exists) — no separate title/date DOM elements exist,
  compact CSS height (<= 42px), near-zero top margin, exact "Record
  Time" wording, no date shown anywhere in the ruler, ms/s/min adaptive
  titles via zoom/pan, title/tick unit consistency preserved, mode
  switching, zero waveform fetches, Reset Time View, Grouped/Separate/
  Custom (including Separate's still-suppressed per-lane ticks), sticky
  CSS/margin/alignment unchanged, zero Plotly work on synthetic scroll
  events, theme switching (a single `font.color` relayout still covers
  both ticks and the native title), and workspace-reset behavior.
- **Frontend, existing: the full Phase 2C-A through 2C-C4 suites (199
  checks) were all re-run unmodified against this pass's code — the
  exact same 20 failures already fully documented in the Phase
  2C-C4/2C-C4A records, zero new divergences** introduced by this
  correction (none of this pass's changes touch the underlying causes
  of those existing, already-explained failures).
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — whether the compact layout genuinely reads as a
  conventional X-axis matching the owner's own reference screenshot was
  NOT visually confirmed. See the final report's explicit statement
  about what's honestly unverified. Final visual judgment remains the
  owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C4A sticky time-axis title placement and unit label)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 23 scripted `jsdom` checks, all passing**
  (`phase2cc4a_check.mjs`) — title element positioned before the tick
  chart in DOM order (top placement), Absolute title exactly "Record
  time", the simplified date-only ruler context line vs. the toolbar's
  unchanged full text, ms/s/min titles (min-scale verified directly
  against `wwStickyRulerElapsedUnit()` since the fixture's own record
  is too short to reach a real 60s+ zoom), the ruler's rescaled tick
  values genuinely matching the title's unit (no mismatch — the exact
  thing section 4 required), zoom and pan both updating the unit/title
  correctly, Absolute↔Elapsed switching, zero waveform fetches on a
  mode switch, Reset Time View, Grouped/Separate/Custom, sticky CSS/
  margin/alignment-input unchanged, theme switching, and workspace-
  reset ruler/title clearing (including confirming `ww.timeMode`'s own
  established persistence-across-clear behavior is unaffected).
- **Frontend, existing: the full Phase 2C-A through 2C-C4 suites (222
  checks) were all re-run unmodified against this pass's code.** 20
  failures appear, all explained by either (1) the same pre-existing
  Phase 2C-C3/2C-C4 divergences already documented in those phases'
  own records, or (2) two new divergences directly caused by this
  phase's own deliberate design: several older, pre-COMTRADE-timing
  test fixtures' "last relayout call has this xaxis.range value"
  assumption now sometimes resolves to the ruler's own correctly-
  rescaled value (e.g. `100` instead of `0.1` for a 100ms zoom) instead
  of a real panel's raw value; and `phase2cc4_check.mjs`'s own
  assertion that the toolbar and ruler date-context text are identical,
  which is exactly what this phase's own section 5 deliberately
  changed. None of these frozen, one-off, not-committed scripts were
  modified, per this project's established precedent.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — in particular, whether rescaling the ruler's own axis
  domain for ms/min display genuinely preserves tick-pixel alignment
  with the real (unrescaled) waveform panels was reasoned through
  carefully but NOT visually confirmed. See the final report's explicit
  statement about what's honestly unverified. Final visual judgment
  remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C4 sticky shared waveform time axis)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` plus
  project-memory docs).
- **Frontend, new: 24 scripted `jsdom` checks, all passing**
  (`phase2cc4_check.mjs`) — ruler hidden with no waveforms, ruler visible
  once displayed, sticky CSS/container structure, ruler derives its
  range from `ww.viewport` (not an independent state), margin/alignment
  consistency between the ruler and a real panel (same `WW_PANEL_MARGIN`
  values), Absolute and Elapsed rendering, mode-switch updates the ruler
  with zero new waveform fetches, zoom/pan/Reset Time View all update
  the ruler via the existing single broadcast path, the ruler never
  registers its own Plotly event listener, Grouped/Separate/Custom all
  work (Separate's all-lanes-suppressed chrome verified explicitly),
  panel resize causes zero ruler-related Plotly calls, theme switching
  re-colors the ruler without a refetch, removing all channels hides the
  ruler, re-adding channels reuses the existing Plotly instance rather
  than recreating it, Clear workspace hides the ruler, and dispatching
  synthetic scroll events causes zero waveform fetches and zero new
  Plotly calls.
- **Frontend, existing: `frontend_logic_check.mjs`, `theme_crosshair_
  check.mjs`, and the full Phase 2C-A through 2C-C3 suites were all
  re-run unmodified against this pass's code.** `frontend_logic_check.mjs`
  and `theme_crosshair_check.mjs` pass in full. **9 new failures appear
  across the rest, all explained by this phase's own two deliberate
  architecture changes** (not regressions): the ruler's own extra Plotly
  `newPlot`/`relayout` call makes several scripts' exact "one per panel"
  call-count assertions off-by-one, and several scripts assert the
  now-superseded "only the bottom Separate lane shows ticks" behavior
  (section 16's own suppression change). These are frozen, one-off,
  not-committed verification scripts from prior phases — per this
  project's established precedent (Phase 2C-C3's identical treatment of
  its own Absolute-default divergence), not modified; `phase2cc4_check.mjs`
  explicitly covers what changed. `phase2ca_check.mjs` additionally still
  carries its 2 pre-existing Phase 2C-C3 divergences, unrelated to this
  phase.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation (ruler "sticky" feel while
  scrolling, real tick-to-waveform alignment at various zoom levels, any
  visual content coverage) was performed in this sandboxed session — see
  the final report's explicit statement about what's honestly
  unverified. Final visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C3 COMTRADE time-axis modes)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Timing investigation, done first**: direct code reading of
  `backend/app/domain/timing.py` and the schema/parser layer confirmed
  `start_time`/`trigger_time` are separate fields, sample 0 coincides
  with `start_time` (never `trigger_time`), both timestamps are
  timezone-naive, and `TimebaseOut` already exposed everything needed —
  zero backend changes required.
- **Frontend, new: 26 scripted `jsdom` checks, all passing**
  (`phase2cc3_check.mjs`) — Absolute default, Elapsed selectable, mode
  switching both directions, viewport preservation while zoomed,
  displayed-channel preservation, zero-refetch, Reset Time View in both
  modes, Autoscale Y unaffected, all three layout modes (including
  Separate's bottom-lane-only axis and Grouped's zero-showticklabels
  invariant), zoom/pan sync in both modes, panel-height preservation,
  theme-switch preservation, adaptive tick-format bands, a midnight/date
  rollover, a full year-boundary rollover, the source capability model,
  and time-mode persistence across Clear workspace.
- **Frontend, existing: `frontend_logic_check.mjs`, `theme_crosshair_
  check.mjs`, and the full Phase 2C-A through 2C-C2A suites (193 checks)
  were all re-run unmodified against this pass's code** — all still pass
  except 2 in the non-committed `phase2ca_check.mjs` that assert a
  raw-elapsed-number `xaxis.range`, the expected consequence of Absolute
  now being the COMTRADE default (not a regression; explained in the
  final report). **This re-run caught two real regressions before they
  shipped** (a `timebase`-scoping bug that broke all channel rendering,
  and a `wwApplyTimeAxisChrome` Grouped-mode guard regression) — both
  fixed and reconfirmed clean.
- **Real COMTRADE verification**: a synthetic ASCII COMTRADE record with
  a known, non-trivial `start_time`/distinct `trigger_time` imported via
  a real FastAPI `TestClient` (no mocking) confirmed the API returns
  both exactly, and that sample 0's absolute time equals `start_time`,
  never `trigger_time`. A second scenario crossing a midnight/date
  boundary confirmed both the API and the frontend's own timestamp
  formula roll the calendar date over correctly — backend-returned
  values were fed through the actual shipped frontend JS, not a
  reimplementation.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation (toolbar toggle discoverability,
  tick-formatting readability at real zoom levels, mode-switch-while-
  zoomed "feel") was performed in this sandboxed session — see the final
  report's explicit statement about what's honestly unverified. Final
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C2A panel resize responsiveness)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `7b2d433` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this
  pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Investigation instrumentation (scratch, not committed)**: a jsdom
  script (`resize_lag_measure.mjs`) with a simulated-cost
  `Plotly.Plots.resize` mock (busy-wait, tested at 0ms/20ms/50ms), run
  BEFORE the code change to confirm the bottleneck (DOM height-write
  timestamps identical to Plotly-resize-end timestamps) and AFTER to
  confirm the fix (DOM height-write timestamps measurably earlier than
  the corresponding Plotly-resize-start timestamps), at every simulated
  cost level.
- **Frontend, new: 9 scripted `jsdom` checks, all passing**
  (`phase2cc2a_check.mjs`) — the DOM height write is now observable
  synchronously on every raw `pointermove` (not gated behind a tick/rAF
  wait); `Plotly.Plots.resize` remains coalesced (far fewer calls than
  raw pointermoves); the final Plotly resize call is always against the
  exact final committed height; `pointercancel` performs exactly one
  final resize and leaves no stale/late resize call; a subsequent drag
  after a cancelled one still works; the 100px minimum and 600px maximum
  are both still enforced synchronously; only the dragged panel is ever
  resized; a full drag still causes zero waveform fetches.
- **Frontend, existing: the full Phase 2C-C2 (23), Phase 2C-C1 (30),
  Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1
  (16), Phase 2C-A (19), and Phase 1 (4) suites were all re-run
  unmodified against this pass's code and all still pass in full** — 145
  existing checks, zero regressions (154 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- No real-browser/visual or tactile confirmation of the actual felt
  improvement was performed in this sandboxed session (no headless
  browser available; installing one — Playwright/Puppeteer — was judged
  disproportionate for a single diagnostic) — see "Live DEV verification"
  in this task's final report for what was checked instead, and its own
  explicit statement about what's honestly unverified. Final tactile
  judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C2 adjustable waveform panel heights)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `91bb0fc` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this
  pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 23 scripted `jsdom` checks, all passing** — a resize
  handle exists on every panel in Grouped/Separate/Custom; dragging a
  Grouped panel's handle resizes only that panel (an unrelated panel's
  height is byte-for-byte unchanged); `Plotly.Plots.resize` is called
  during the drag; resizing issues zero waveform fetches; extreme drags
  clamp correctly at both the 100px minimum and the 600px maximum;
  zoom/Reset-Time-View synchronization still work correctly after
  resizing; Separate lanes resize independently while the overlay label
  stays a correctly-positioned child of its own lane and the true bottom
  lane still (and only it) shows the shared X axis; a Custom group panel
  resizes independently with membership unchanged; height state
  round-trips correctly across Custom→Grouped→Custom and
  Separate→Grouped→Separate, including confirming different modes'
  height keys never collide; Grouped/Separate/Custom keep working; theme
  switching remains correct at custom heights without a refetch;
  removing then re-adding a channel restores its remembered height
  (deliberately not scrubbed); Clear workspace resets remembered heights
  entirely; waveform query-parameter whitelist unchanged.
- **Frontend, existing: the full Phase 2C-C1 (30), Phase 2C-B3A (17),
  Phase 2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19),
  and Phase 1 (4) suites were all re-run unmodified against this pass's
  code and all still pass in full** — 122 existing checks, zero
  regressions (145 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual or tactile confirmation of the drag interaction
  itself was performed in this sandboxed session (no headless browser
  available; jsdom implements neither element-level Pointer Capture nor
  `requestAnimationFrame` natively, both worked around in the test
  harness) — see "Live DEV verification" in this task's final report for
  what was checked instead (API-level evidence only), and its own
  explicit statement about what's honestly unverified. Final tactile/
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C1 custom analog channel groups)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `ae8ccfd` (independent `git fetch` via the
  established HTTPS-URL workaround) before this pass began. **Two
  uncommitted local changes were found in the working tree** (the direct
  manual overlay-tag tweaks described above) — preserved (not discarded,
  per the project's own git-safety rule) and committed separately as
  `d902dc5` before this pass's own implementation work began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 30 scripted `jsdom` checks, all passing** — the Custom
  toolbar button and Edit Channel Groups control appear correctly;
  switching to Custom with no groups yet produces one panel per channel
  (auto-solo); the modal opens/closes (including Cancel, then reopening
  cleanly); groups can be created (Group 1/2/3); channels can be assigned
  via the Unassigned select and removed back to Unassigned; an empty
  group can be deleted; Apply renders the exact example grouping from
  this task's own manual-verification checklist (Group 1 = VA/VB/VC,
  Group 2 = IA/IB, IC auto-solo); a pre-Apply zoomed viewport survives
  Apply exactly; zoom-broadcast synchronization, Reset Time View,
  Autoscale Y, and no-per-panel-modebar all work in Custom mode;
  switching Custom→Separate→Custom preserves displayed channels AND
  restores the last-applied grouping; Grouped mode groups by
  engineering_type with zero regression; theme switching still works in
  Custom mode; Clear workspace resets both the display and the
  remembered custom grouping (verified behaviorally); waveform
  query-parameter whitelist unchanged.
- **Frontend, corrected in place: 1 of Phase 2C-B3A's own CSS-source
  assertions**, which had hardcoded the exact `top: 50%` value later
  manually tuned to `25%`, was relaxed to assert the overlay MECHANISM
  (percentage-based `top` + `translateY(-50%)`) rather than the specific
  tunable percentage — the rest of that suite needed no change.
- **Frontend, existing: the full Phase 2C-B3 (16), Phase 2C-B2 (20),
  Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites were all
  re-run unmodified against this pass's code and all still pass in
  full** — 92 existing checks (75 unmodified + 17 corrected-B3A), zero
  regressions (122 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs (one regex false-positive
  from a JS template string containing `data-group-id="..."` was
  investigated and ruled out with a stricter check).
- No real-browser/visual or hands-on-workflow verification of the group
  editor modal was performed in this sandboxed session (no headless
  browser available) — see "Live DEV verification" in this task's final
  report for what was checked instead (API-level evidence only), and its
  own explicit statement about what's honestly unverified. Final
  workflow/appearance judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-B3A overlay right-side lane labels)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `ef89cc7` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 17 scripted `jsdom` checks, all passing** — CSS-source
  checks confirming the label uses absolute positioning against a
  relatively-positioned lane (not a grid column), is pinned near the right
  edge and vertically centered, and sits above the chart via z-index; the
  lane's chart area is no longer split into two columns; the overlay
  label's DOM parent is the lane element itself (a sibling of the
  chart-wrap within the same lane, not a separate layout block);
  displayed-channel identity is correct; Separate mode still shows exactly
  one lane per channel with the unified-canvas class intact; only the
  bottom lane still shows the shared X axis; Grouped mode still groups
  correctly and never applies the unified/overlay CSS; zoom/pan/Reset Time
  View/Autoscale Y/no-modebar/theme-switching all still work;
  Grouped↔Separate still preserves viewport and displayed channels;
  removal via the overlay tag's remove button still removes the whole
  lane; waveform query-parameter whitelist unchanged.
- **Frontend, corrected in place: 2 of Phase 2C-B3's own CSS-source
  assertions**, which specifically tested the now-removed grid-column
  mechanism, were updated to assert the new overlay mechanism instead —
  the remaining 14 of its 16 checks needed no change and passed
  unmodified.
- **Frontend, existing: the full Phase 2C-B2 (20), Phase 2C-B1 (16), Phase
  2C-A (19), and Phase 1 (4) suites were all re-run unmodified against
  this pass's code and all still pass in full** — 59 existing checks,
  zero regressions (92 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual verification of whether the overlay genuinely
  reads as a Detego-style floating label rather than a side panel was
  performed in this sandboxed session (no headless browser available) —
  see "Live DEV verification" in this task's final report for what was
  checked instead (API-level evidence only), and its own explicit
  statement about what's honestly unverified. Final visual-appearance
  judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-B3 right-side compact lane labels)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `9fcc2d8` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 16 scripted `jsdom` checks, all passing** — CSS-source
  checks confirming the chart/label grid columns swapped sides and the
  label is now a compact pill (border-radius/max-width); a new
  `.ww-legend-label` span exists per lane for ellipsis truncation;
  displayed-channel identity is correct in each tag (name + unit); the
  remove control and color dot are preserved inside the tag; 6 lanes still
  render with the unified-canvas class; only the bottom lane still shows
  the shared X axis; Grouped mode still groups correctly and never applies
  the unified class; zoom/pan/Reset Time View/Autoscale Y/no-modebar all
  still work; theme switching re-colors without refetching and the tag has
  no inline color override; Grouped↔Separate still preserves viewport and
  displayed channels; removal via the tag's remove button still removes
  the whole lane; waveform query-parameter whitelist unchanged.
- **Frontend, existing: the full Phase 2C-B2 (20), Phase 2C-B1 (16), Phase
  2C-A (19), and Phase 1 (4) suites were all re-run unmodified against
  this pass's code and all still pass in full** — 59 existing checks,
  zero regressions (75 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual verification of whether the tag genuinely reads
  as compact/readable/low-clutter to a human eye was performed in this
  sandboxed session (no headless browser available) — see "Live DEV
  verification" in this task's final report for what was checked instead
  (API-level evidence only), and its own explicit statement about what's
  honestly unverified. Final visual-appearance judgment remains the
  owner's own manual UAT.

## What was verified (prior pass — Phase 2C-B2 unified analog canvas layout)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `60a77bb` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 20 scripted `jsdom` checks, all passing** — static
  CSS-source checks confirming the unified-container/de-carded-lane rules
  exist and that Grouped mode's own card CSS is untouched; Separate mode
  still creates 6 stacked lanes and now applies the `ww-panels-unified`
  class; the mode switch still issues zero new waveform fetches; only the
  bottom-most lane shows X tick labels/title (verified against actual
  `Plotly.relayout` calls, restricted to currently-active panel elements);
  Grouped mode's panels never receive an axis-suppression relayout;
  zoom/pan/Reset Time View/Autoscale Y/no-modebar all still work
  identically; viewport preservation across Separate→Grouped→Separate
  (including the re-applied unified class); theme switching without
  refetching; removing the current bottom lane correctly hands the shared
  axis to the new last lane; "Clear workspace" empties the unified
  container; waveform query-parameter whitelist unchanged.
- **Frontend, existing: the full Phase 2C-B1 suite (16 checks), Phase 2C-A
  suite (19 checks), and Phase 1 regression suite (4 checks) were all
  re-run unmodified against this pass's code and all still pass in full**
  — 39 existing checks, zero regressions (59 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual verification of whether the six lanes genuinely
  read as "one canvas" to a human eye was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked instead (API-level
  evidence only), and its own explicit statement about what's honestly
  unverified. Final visual-appearance judgment remains the owner's own
  manual UAT.

## What was verified (prior pass — Phase 2C-B1 Grouped / Separate layout)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `3f637ba` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend, new: 16 scripted `jsdom` checks, all passing** — Grouped
  baseline unchanged; switching to Separate produces exactly 6 panels
  (one per displayed channel) with correct labels, no per-panel modebar,
  zero new waveform fetches, old panels purged; shared zoom/pan
  synchronization and loop-prevention verified in Separate mode using the
  same faithful Plotly-relayout-refire test double established for Phase
  2C-A; Reset Time View and Autoscale Y in Separate mode; **viewport
  preservation verified directly** by asserting the actual
  `layout.xaxis.range` Plotly was called with after a Separate→Grouped
  and a Grouped→Separate switch, both following a real zoom; channel
  removal in Separate mode removes the whole lane; theme switching in
  Separate mode; and a direct check that every waveform request's query
  parameters are still exactly the pre-existing four
  (`channel_name`/`start_time`/`end_time`/`point_budget`) — confirming no
  backend API shape changed.
- **Frontend, existing: the full Phase 2C-A suite (19 checks) and the
  Phase 1 regression suite (4 checks) were both re-run unmodified against
  this pass's code and both still pass in full** — no regression.
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call (including the two
  new layout-toggle buttons) resolves to an `id=` that actually exists.
- No real-browser/visual verification of rendering smoothness was
  performed in this sandboxed session (no headless browser available) —
  see "Live DEV verification" in this task's final report for what was
  checked instead, and its own explicit statement about what's honestly
  unverified.

## What was verified (prior pass — Phase 2C-A synchronized multi-channel waveform display)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `51ac404` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend, new: 19 scripted `jsdom` checks, all passing** — channel
  selection/Add-selected/Clear-selection; initial engineering-type
  grouping into the correct panel/trace counts; one `Plotly.newPlot` per
  panel with `displayModeBar: false`; shared-viewport broadcast on both
  zoom and pan, verified against a Plotly test double that faithfully
  re-fires `plotly_relayout` on a programmatic `relayout()` call so
  loop-prevention (`suppressNext`) is actually exercised, not just
  structurally present; Zoom/Pan toolbar buttons (dragmode only, never
  refetches); Reset Time View (refetches, restores full record on every
  panel); Autoscale Y (native `yaxis.autorange`, never refetches); theme
  switch (re-colors every panel, never refetches); removing one channel
  vs. removing a panel's last channel; source removal clearing only that
  source's displayed channels; "Start new workspace" clearing everything;
  a 12-channel/4-panel structural scale check (exactly 12 requests, a
  12-channel zoom refetches exactly 12 times, not a multiplied/runaway
  amount).
- **Frontend, existing (Phase 1 regression): 4 scripted `jsdom` checks,
  re-run and still passing** (`frontend_logic_check.mjs`) — two of its
  own assertions were tightened (not weakened) to correctly account for
  the new leading checkbox column (`td:not(.select-col)` instead of a
  bare first-`<td>` assumption; filtering empty headers before comparing
  labeled ones) — confirms search/grouping/counts/remove-confirmation/
  banner-isolation all still behave exactly as before.
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists in the file (including IDs that only exist
  inside dynamically-rendered `innerHTML`, wired via functions called
  after that HTML is set); no duplicate function/element-id declarations.
- **Structural-only performance check (section 15)**: verified via the
  jsdom suite at 3, 6, and 12 displayed channels that request count
  scales exactly linearly and never duplicates/runs away. This sandboxed
  session has no real browser, so actual paint/scroll responsiveness at
  these counts was **not** visually confirmed here — live DEV round-trip
  API timing was measured instead as the closest available evidence; see
  this task's final report for the exact numbers, and its own explicit
  statement that no claim is made about 50/100 simultaneous channels
  (not built for, requested, or tested).

## What was verified (prior pass — crosshair visual UAT follow-up)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `adc9439` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend: the same 19-check scripted `jsdom` test, updated in place
  and re-passing** for the new values — `spikethickness: 0.35`,
  `spikedash: "3px,2px"`, Light `--spike-color: rgba(60,68,87,0.6)`, Dark
  `--spike-color: rgba(168,178,199,0.6)`, `spikesnap: "data"` unchanged,
  both axes' spikes enabled, theme switch still triggers **zero**
  additional `fetch` calls, Reset Time View regression check still green.
- `node --check` on `frontend/waveform-prototype.html`'s inline
  `<script>` block — syntactically valid.
- Manual `grep` confirmed the new `spikethickness`/`spikedash` values are
  only present in the intended two places (xaxis/yaxis) and no stale
  `0.5`/`"dash"` values remain in the live config (only historical
  comment text, left as accurate history, not live code).
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report, and the honest limitation note on the
  dash-length/thickness claims (DECISIONS.md's DEC-023 Update note).

## What was verified (prior pass — Light/Dark theme & crosshair refinement)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `2349972` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend: 19 new scripted `jsdom` checks, all passing** — theme
  default/selection/persistence/cross-tab-sync/toggle-control behavior on
  both `index.html` and `waveform-prototype.html`; Plotly crosshair
  (dashed/thinner/reduced-alpha/sample-snapped/hover-values) at chart
  init; theme switch updates Plotly via `relayout`/`restyle` with **zero**
  additional `fetch` calls; Reset Time View still triggers exactly one
  fresh waveform request (regression check).
- `node --check` on every inline `<script>` block in both HTML files, and
  on `frontend/theme.js` directly — all syntactically valid.
- Manual `grep` sweep for `rgba(\|#[0-9a-fA-F]{3,6}` in both HTML files
  confirmed only the intentional, theme-invariant `color: #fff` (white
  text on solid accent/danger buttons, same in both themes) remains
  outside the shared token files.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked via `curl`/static-asset
  inspection instead, and the honest caveat on the `spikethickness: 0.5`
  visual claim (DECISIONS.md DEC-023's own Impact section).

## What was verified (prior pass — Phase 2C discovery/design)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `704df11` (independent `git fetch` via the
  established HTTPS-URL workaround — the configured SSH `origin` remote is
  not authenticated in this sandbox), working tree clean, before this pass
  began.
- **`powerwave` git state**: confirmed via a spawned Explore subagent —
  `/Volumes/externalDrive/code-gym/powerwave`, remote
  `https://github.com/myza81/powerwave.git`, commit `3156392` (same commit
  every prior investigation this project has used — no drift).
- **Detego**: only publicly available marketing/docs pages
  (`detego.app`, `detego.app/docs/guide/waveform-viewer`) were fetched via
  `WebFetch`/`WebSearch` — no authenticated app, no proprietary code/assets
  were accessed or inspected, per this task's own instruction and the
  standing `PRODUCT_REFERENCES.md` governance.
- **This is a documentation-only pass** — no backend or frontend code was
  touched; nothing to run a test suite against. `git diff --stat` after all
  edits shows only the four project-memory markdown files.
- `git diff --check` — no whitespace errors.

## What was verified (prior pass — Phase 2B renderer closure)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- **Backend regression: 278 tests, unmodified, all still pass** — zero
  backend files in the diff (`git diff --stat -- backend/` empty).
- **Frontend: 31 scripted `jsdom` checks, all passing** — 3 new
  static-markup checks confirming no renderer-selector UI, no
  "renderer comparison"/"Phase 2B UAT" wording, and no uPlot code
  references remain anywhere in the shipped file; the rest cover
  Plotly-only initialization, the restyled crosshair configuration
  (dashed/thin/reduced-opacity/still-sample-snapped/both-axes), zoom,
  the native-autoscale-refetch fix, Reset Time View, both stale-request
  protection layers, and safe-failure error handling.
- **Repository-wide search**: `grep -ril "uplot"` (excluding `.git` and
  `docs/`, which intentionally retains historical record) returns only
  `frontend/waveform-prototype.html` (two historical/rationale comments,
  zero code references) and `frontend/vendor/README.md` (its own
  intentional "History" note). `find -iname "*uplot*"` confirms zero
  files with that name remain anywhere in the tree.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked via `curl`/static-asset
  inspection instead.

## What was verified (prior pass — Phase 2B Plotly refinement)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- **Backend regression: 278 tests, unmodified, all still pass** — zero
  backend files in the diff (`git diff --stat -- backend/` empty).
- **Frontend: 24 scripted `jsdom` checks, all passing** — 10 regression
  checks confirming every existing Phase 2B behaviour (initial request,
  zoom, both stale-protection layers, Reset Time View, renderer switching
  including uPlot remaining functional, adapter cleanup, error banner) is
  unchanged after this pass's edits, plus 5 new checks: the Plotly
  layout's spike/crosshair configuration is present with the exact
  documented settings, and — the most important new test — a simulated
  native Autoscale/Reset-axes relayout event now correctly triggers a
  real full-record re-fetch, proving the toolbar-lag investigation's bug
  fix.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — visual crosshair appearance
  and felt interaction smoothness are exactly what the owner's own final
  UAT session is for; see "Live DEV verification" in this task's final
  report for what was checked via `curl`/static-asset inspection instead.

## What was verified (prior pass — Phase 2B renderer UAT prototype)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- **Backend regression: 278 tests, unmodified, all still pass** —
  confirmed zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend: 25 scripted `jsdom` checks, all passing**, driving the
  actual shipped `waveform-prototype.html` (not a reimplementation)
  against stub `uPlot`/`Plotly` objects satisfying their real public
  APIs. Covers: initial full-record request shape; zoom → debounced
  narrower request; the stale-response scenario with the
  `AbortController` layer and the sequence-number fallback layer verified
  **independently** (a dedicated test isolates the sequence-number path
  by simulating an abort that doesn't reject the promise); Reset View;
  friendly error-banner wording; renderer switch issuing zero new
  requests and reusing already-fetched data; repeated renderer switching
  with matched init/destroy counts and no duplicate DOM nodes; and
  Plotly's own programmatic-relayout-after-Reset not looping into a
  second fetch.
- Vendored library integrity: exact byte sizes recorded (uPlot ≈ 52 KB
  combined JS+CSS; Plotly-cartesian ≈ 1.36 MB JS), versions/licenses
  recorded in `frontend/vendor/README.md`.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked via `curl`/static
  asset inspection instead, and note clearly that interactive/visual
  correctness is the explicit purpose of the owner's own upcoming UAT
  session, not something already claimed done here.

## What was verified (prior pass — Phase 2A implementation)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- All 227 previously-passing backend tests still pass **unmodified in
  behaviour** — only `tests/test_workspace_registry.py`'s fixture helper
  needed a mechanical update (build `ActiveSource` instead of a bare
  `SourceMetadata`); every assertion it made before still holds.
  `tests/test_comtrade_parity.py`/`test_comtrade_provider.py` (parser
  correctness) were touched by nothing this pass and still pass.
- **278 total backend tests pass** — see "What was most recently done"
  above for the breakdown; re-verified from a clean venv
  (`pip install -r requirements-dev.txt && pytest`).
- Performance/memory measured via a one-off, uncommitted benchmark script
  against synthetic (non-confidential) data at four scales up to 2M
  samples — see the Phase 2A Implementation Record's tables. Not measured:
  an actual ~100 MB real COMTRADE file through the real parser (still
  `[OPEN]`, now partially informed by a precisely measured
  file-to-parsed-memory expansion ratio instead of a pure guess).
- Manually confirmed (via `app.openapi()`'s paths, not raw `app.routes` —
  FastAPI's internal route representation makes the latter show an opaque
  wrapper object, a known quirk from Phase 1's own final report) that all
  6 endpoints register correctly, including the new
  `GET .../sources/{source_id}/waveform`.

## What was verified (prior pass — Phase 2 design)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- `powerwave` git state: confirmed unchanged since the original discovery
  audit (`HEAD` still `31563920...` / short form `3156392`), so the
  original [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) findings were
  still applicable — but re-verified live anyway (not assumed), per the
  task's explicit instruction and the project's own "code over docs"
  source-of-truth rule.
- **All 14 specific `powerwave` waveform-architecture claims this pass set
  out to check were independently re-confirmed against live code** (file
  path + line number evidence, not just re-reading the prior discovery
  doc) — see [MIGRATION_PLAN.md §2](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)
  for the full findings. One correction to the prior discovery note:
  `_infer_panel_for_channel()` is a module-level function, not a method.
  One materially new finding beyond the prior discovery pass's scope: the
  decimation algorithm itself (`t_clip[::stride]`) is confirmed plain
  nth-point stride sampling with no peak preservation, and digital
  transitions are decimated *before* transition-extraction runs, meaning a
  narrow pulse can be dropped before `extract_transitions()` ever sees it
  — a genuine, previously uncited engineering-integrity risk in the
  current desktop app, carried into the design as an explicit "do not
  repeat this" principle.
- This was a discovery/design-only task — **no automated test suite
  applies** (no code was written). No backend/frontend changes exist to
  regression-test.

## What was verified (prior pass — workspace-reset fix)

- **227 backend tests pass** (`cd backend && pytest`), up from 215 — new:
  `test_workspaces_api.py` (single- and multi-source whole-workspace
  DELETE, cross-workspace isolation, empty/unknown-workspace idempotency,
  blank-id rejection, delete-then-reupload-into-the-same-id), 4 new
  `WorkspaceRegistry.remove_workspace()` unit tests in
  `test_workspace_registry.py`, and one `Remove`-regression test in
  `test_sources_api.py` confirming a single-source delete leaves sibling
  sources in the same workspace intact. No COMTRADE parser/provider/
  classification code was touched this pass.
- **Frontend logic verified against the actual shipped code**, not a
  reimplementation: a one-off `jsdom` script (not committed, same
  established approach as the prior UAT refinement pass) drove the *real*
  upload code path (mocked-`fetch` form submission — not direct variable
  poking, since top-level `let`/`const` in a classic script are not
  reachable via `window.*`, matching real browsers) and exercised 36
  checks across 7 scenarios: confirmation shown only for a non-empty
  workspace and only before any DELETE; Cancel issues zero DELETE calls
  and preserves the old workspace id/source list/banner; Confirm issues
  exactly one workspace-level DELETE against the *old* id, then mints a
  new id and clears source list/channel panel/banner; a failed DELETE
  preserves everything and shows a visible error; an empty workspace
  skips confirmation but still resets; `Remove` still issues only a
  source-level DELETE and its Cancel/banner/other-source-preserved
  behaviour is unchanged; removing an unrelated source still leaves a
  still-valid banner alone. All 36 passed.
- No production code outside the intended scope was touched — see "Files
  changed" below.

## What was verified (prior pass — UAT refinement)

- **215 backend tests pass**, up from 168 — new:
  `test_channel_classification.py` (every recognized unit/parameter_type,
  priority ordering, explicit ambiguous-channel-stays-Undefined coverage)
  plus a new API assertion that `engineering_type` appears correctly in
  live channel responses. No provider/parser code was touched that pass —
  COMTRADE parity is structurally unaffected (confirmed by the unmodified
  parity tests still passing).
- **Frontend logic verified against the actual shipped code**, not a
  reimplementation: a one-off Node script (not committed — no frontend
  test framework existed before this task, and none was introduced, per
  the task's explicit allowance to document manual/scripted verification
  instead) loaded `frontend/index.html`'s real inline `<script>` into a
  `jsdom`-backed DOM and exercised: grouping/counts/default-expansion/
  column-removal against an 80-analog/282-digital dataset matching UAT's
  own numbers; search (case-insensitive, cross-analog/digital,
  auto-expand-on-match, no-match empty state, clear-restores-default);
  the full remove-confirmation flow, explicitly confirming **Cancel issues
  zero DELETE requests**; the stale-banner fix; and — the task's explicit
  forward-compat check — that removing a *different* source never clears
  an unrelated still-valid banner. All passed. (One bug was caught and
  fixed in the *test script itself* during this process — an attempt to
  read a `let`-scoped JS variable via `window.X` from outside the script,
  which correctly doesn't work in real browsers either; the fix was to
  drive the real upload/removal code paths instead of poking at internal
  state, which is also the more faithful test.)
- **Live guardrail regression check** against a local `uvicorn` server:
  missing-companion-file (422), wrong-extension (400
  `unsupported_file_type`), and successful upload-then-delete-then-404 all
  behave exactly as before; the new `engineering_type` field appears
  correctly (`VA`/`VB` → `Voltage`, `IA` → `Current` for the synthetic
  fixture).

## What files were changed this session (Phase 3B-UAT1 recording row divider alignment)

Modified only: `frontend/index.html` (moved `.recording-actions`'s flex
layout from the Actions `<td>` itself onto a new inner `<div>`, plus one
explanatory CSS comment). No new files. **No `backend/` file, no
CI/deployment workflow file was touched.** Project memory:
`MIGRATION_PLAN.md`, `CURRENT_STATE.md`, `HANDOFF.md` updated;
`DECISIONS.md` intentionally NOT touched (a cosmetic correction within
the already-decided DEC-032 Recordings page, not a new/revised
decision).

## What files were changed in the prior session (Phase 3B recordings page and upload workflow)

Modified: `frontend/index.html` (the bulk of this phase — new
Recordings page markup/CSS/JS, new upload modal, Main Sidebar Menu
rename + new item, removed the old always-visible sidebar upload form,
`shell.currentPage`/`shellSetCurrentPage()`, `RECORDING_FORMATS`,
`fetchSourcesList()`/`refreshAllSourceViews()`/`renderRecordingsTable()`
and friends, two new `[hidden]` CSS override rules);
`backend/app/schemas/source.py` (additive `duration_seconds`/
`sample_count` fields on `SourceSummaryOut`);
`backend/tests/test_sources_api.py` (new/extended coverage for those
fields). No new files. No CI/deployment workflow file. Project memory:
`DECISIONS.md` (new DEC-032 — this IS a meaningful product-navigation
change, per this task's own explicit instruction), `MIGRATION_PLAN.md`,
`CURRENT_STATE.md`, `HANDOFF.md` all updated.

## What files were changed in the prior session (Phase 3A-UAT4 channel filename containment)

Modified only: `frontend/index.html` (new `.detail-header-info` class
with `min-width: 0; max-width: 100%;`, applied to the previously-unnamed
flex-item wrapper in `renderChannels()`'s markup; `.detail-header
h3`/`.meta` gained explicit `white-space: normal; max-width: 100%;`
alongside their existing `overflow-wrap: anywhere`). No new files. **No
`backend/` file, no CI/deployment workflow file was touched.** Project
memory: `MIGRATION_PLAN.md`, `CURRENT_STATE.md`, `HANDOFF.md` updated;
`DECISIONS.md` intentionally NOT touched (a targeted correction within
the already-decided DEC-031 shell architecture and its own Phase
3A-UAT3 containment pass, not a new/revised decision).

## What files were changed in the prior session (Phase 3A-UAT3 targeted overflow and containment fixes)

Modified only: `frontend/index.html` (CSS containment rules for Findings
A/B/C/D/G; `shellSetActiveView()` resize call for Finding E;
`shellSyncSidebarWidthForBreakpoint()`/`matchMedia` listener for Finding
F; `.group-chip-label` markup wrap for Finding D). No new files. **No
`backend/` file, no CI/deployment workflow file was touched.** Project
memory: `MIGRATION_PLAN.md`, `CURRENT_STATE.md`, `HANDOFF.md` updated;
`DECISIONS.md` intentionally NOT touched (targeted corrections within
the already-decided DEC-031 shell architecture, not a new/revised
decision).

## What files were changed in the prior session (Phase 3A-UAT2 remove duplicate header theme control)

Modified only: `frontend/index.html` (removed the `<div id="themeToggle">`
element from the Global Header and its `mountThemeToggle()` Init call;
corrected a stale code comment on the Main Sidebar Menu's Settings
handler). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change (both
still used unmodified by `waveform-prototype.html`), no CI/deployment
workflow file was touched.** Project memory: `MIGRATION_PLAN.md`,
`CURRENT_STATE.md`, `HANDOFF.md` updated; `DECISIONS.md` intentionally
NOT touched (no new/corrected architectural decision this pass).

## What files were changed in the prior session (Phase 3A-UAT1 responsive waveform width reflow)

Modified only: `frontend/index.html` (`shellCreateHorizontalSplit()`
rewritten with rAF-coalesced resize scheduling; new
`wwResizeAllVisiblePlots()` and `wwScheduleResizeAllVisiblePlots()`;
Init wiring adds `onResize: wwResizeAllVisiblePlots` to the Workspace
Sidebar split config, a `transitionend` listener on `#mainSidebarMenu`,
and a `window.resize` listener; `.ww-chart-wrap` CSS gained `overflow:
hidden`). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 3A application shell redesign foundation)

Modified only: `frontend/index.html` (full CSS restructuring —
`#globalHeader`, `#appBody`, `#mainSidebarMenu`, `.shell-nav-*`,
`#workArea`, `#workspaceRow`, `#workspaceSidebar`,
`.shell-split-handle`, `#mainWorkspace`, `#activeViewArea`,
`.shell-view-placeholder`, `#bottomStatusBar`, `.shell-sidebar-backdrop`,
plus two responsive media queries; removed the old `main`/`footer`/
`.ww-header` page-grid CSS). HTML restructured: existing Import/
Sources/Channels panels moved into `#workspaceSidebar`; the existing
waveform workspace moved into `#activeViewArea`'s new `#viewWaveform`
container; new `#viewTable`/`#viewSplit` placeholders added; every
existing element ID preserved. New JS: `shell` state object,
`shellCreateHorizontalSplit()`, `shellSetMainSidebarExpanded()`,
`shellSetActiveView()`, `shellSetSidebarDrawerOpen()`,
`shellOpenImport()`, `shellUpdateStatusBar()`,
`shellUpdateStatusBarChannelCount()`; small hooks added into
`renderChannels()` and the three existing `ww.displayed`-count-changing
call sites (`wwAddSelectedChannels`/`wwRemoveChannel`/
`wwClearWorkspace`). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C4B compact sticky time-axis layout correction)

Modified only: `frontend/index.html` (`#wwStickyRulerTitle`/
`#wwStickyRulerContext` DOM elements and their `.ww-sticky-ruler-title`/
`.ww-sticky-ruler-context` CSS deleted entirely; `.ww-sticky-ruler`
padding simplified, `.ww-sticky-ruler-chart` height reduced 46px→40px;
`wwSyncStickyRuler()` rewritten to set `xaxis.title` on the ruler's own
Plotly layout/relayout calls instead of writing to a DOM title element,
with margin changed to `{t:2, b:34}`; Absolute mode's title wording
changed to "Record Time" (capital T); `wwUpdateTimeModeContext()`
simplified to only drive the toolbar's own label, no longer touching a
ruler-side date element). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C4A sticky time-axis title placement and unit label)

Modified only: `frontend/index.html` (`.ww-sticky-ruler-title` CSS
(new) + `.ww-sticky-ruler-context` CSS updated to centered/dimmer;
`#wwStickyRulerTitle` markup (new, before the context line and chart);
new `wwStickyRulerElapsedUnit(spanSeconds)` helper; `wwSyncStickyRuler()`
rewritten to compute/apply a mode-aware title and (Elapsed-only) rescaled
tick range/format; `wwUpdateTimeModeContext()` updated so the ruler's own
context line shows only the date, while the toolbar's copy keeps its
full wording unchanged). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C4 sticky shared waveform time axis)

Modified only: `frontend/index.html` (`.ww-sticky-ruler`/
`.ww-sticky-ruler-context`/`.ww-sticky-ruler-chart` CSS; `#wwStickyRuler`/
`#wwStickyRulerContext`/`#wwStickyRulerChart` markup as a sibling of
`#wwPanels`; new `WW_PANEL_MARGIN` shared constant, also wired into
`wwBuildLayout()`'s own margin (replacing its previous inline literal);
`ww.rulerReady` state; new `wwSyncStickyRuler()`;
`wwUpdateTimeModeContext()` extended to also drive
`#wwStickyRulerContext`; `wwApplyTimeAxisChrome()` changed to suppress
ticks/title on every Separate lane, not just the non-bottom ones;
`wwSyncStickyRuler()` called from `wwApplyAndFetchViewport`,
`wwSetTimeMode`, `wwAddSelectedChannels`, `wwRemoveChannel`,
`wwClearWorkspace`; `wwApplyTheme()` extended to re-color the ruler),
`docs/project-memory/{MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (this
work). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C3 COMTRADE time-axis modes)

Modified only: `frontend/index.html` (toolbar HTML for the Absolute/
Elapsed toggle + date-context label; `channelCheckboxHtml`/
`renderAnalogGroup`/`renderChannelTable` thread `timebase` through so
each channel carries `recordingStartTime`/`timingReference`;
`WW_TIME_MODES`/`ww.timeMode` state; new helpers
`wwParseNaiveTimestamp`, `wwFormatPlotlyDateString`,
`wwTimeModesForChannel`, `wwAvailableTimeModes`,
`wwWorkspaceRecordingStartMs`, `wwElapsedToPlotlyX`,
`wwPlotlyXToElapsed`, `wwTimeAxisTickFormat`, `wwTimeAxisTitle`,
`wwUpdateTimeModeContext`, `wwUpdateTimeModeControlAvailability`,
`wwSetTimeMode`; `wwBuildTrace`/`wwBuildLayout`/`wwLoadChannelRange`/
`wwWirePanelRelayout`/`wwApplyAndFetchViewport` made mode-aware;
`wwUpdateBottomLaneAxis()` renamed to `wwApplyTimeAxisChrome()` (same
Separate-only guard, now mode-aware title); toolbar listeners wired),
`docs/project-memory/{MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (this
work). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C2A panel resize responsiveness)

Modified only: `frontend/index.html` (`wwSetPanelHeight()` split into
`wwSetPanelHeightImmediate()` — the cheap DOM-only write, now called on
every raw `pointermove` — and `wwResizePanelPlot()` — the
`Plotly.Plots.resize()` call only, still `requestAnimationFrame`-
coalesced; `wwSetPanelHeight()` itself retained as their combination,
used only for the authoritative final write on `pointerup`/
`pointercancel`; `wwWireResizeHandle()`'s `onPointerMove`/`flush` updated
accordingly (the old `pendingHeight` variable is gone — the DOM write no
longer needs to wait for a scheduled frame); module header comments
updated), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,
HANDOFF}.md` (an "Update" note appended to DEC-028, no new decision
entry; this work). No new files. **No `frontend/waveform-prototype.html`/
`theme.css`/`theme.js` change, no `backend/` file, no CI/deployment
workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C2 adjustable waveform panel heights)

Modified only: `frontend/index.html` (`WW_MIN_PANEL_HEIGHT`/
`WW_MAX_PANEL_HEIGHT`/`WW_DEFAULT_PANEL_HEIGHT` constants; a
`ww.panelHeights` Map; `wwDefaultHeightForCurrentMode()`/
`wwHeightForGroupKey()`/`wwClampPanelHeight()` helpers; `panel.height`
added to the panel object (`wwCreatePanelObject`); `wwSetPanelHeight()`
and `wwWireResizeHandle()` (Pointer Events + Pointer Capture +
`requestAnimationFrame` coalescing); a `.ww-resize-handle` element added
to every panel's DOM (`wwCreatePanelDom`) with its own theme-token CSS,
unscoped to any one layout mode; `wwClearWorkspace()` extended to reset
`ww.panelHeights`; the module header comment updated), `docs/project-
memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (DEC-028
added; this work). No new files. **No `frontend/waveform-prototype.html`/
`theme.css`/`theme.js` change, no `backend/` file, no CI/deployment
workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C1 custom analog channel groups)

Modified only: `frontend/index.html` (a `ww.customGroups`/
`ww.customGroupSeq` state pair; a `wwCustomGroupFor()` helper; a "custom"
branch added to `wwPanelGroupKeyFor`/`wwPanelLabelFor`; a third
`layoutModeCustomBtn` toolbar button; a new `editChannelGroupsBtn`
control and `wwUpdateEditGroupsButtonVisibility()`; the group editor
modal's HTML/CSS (`groupEditorOverlay`, `.group-editor-box`, `.group-
card`, `.chip-list`, `.group-chip`, etc.); `groupEditorState` and
`wwOpenGroupEditor`/`wwCloseGroupEditor`/`wwRenderGroupEditor`/
`wwGroupEditorAddGroup`/`wwGroupEditorRemoveGroup`/
`wwGroupEditorAssignChannel`/`wwGroupEditorUnassignChannel`/
`wwGroupEditorRenameGroup`/`wwApplyGroupEditor`; `wwClearWorkspace()`
extended to reset `ww.customGroups`; `wwSetLayoutMode()` extended to
accept "custom"; the module header comment updated), `docs/project-
memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (DEC-027
added; this work). Also committed separately this session (before this
task's own work began, preserving pre-existing uncommitted changes found
in the working tree per the project's git-safety rule): `d902dc5`,
two small direct manual CSS tweaks to the Phase 2C-B3A overlay tag (see
"Also note" above). No new files. **No
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no
`backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-B3A overlay right-side lane labels)

Modified only: `frontend/index.html` (removed the `#wwPanels.ww-panels-
unified .ww-panel` grid-template-columns split; `.ww-panel` is now
`position: relative` in unified mode; `.ww-legend` is now `position:
absolute` — pinned `right: 14px`, `top: 50%`/`transform: translateY(-50%)`,
`z-index: 2`, `pointer-events: none` (re-enabled on `.ww-legend-item` via
`pointer-events: auto`); `.ww-chart-wrap` no longer has a `grid-column`;
the module header comment updated), `docs/project-memory/{DECISIONS,
MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (a further "Update" note
appended to DEC-026, no new decision entry; this work). No new files. **No
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no
`backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-B3 right-side compact lane labels)

Modified only: `frontend/index.html` (grid-column order swapped in the
`#wwPanels.ww-panels-unified .ww-panel` CSS so the chart is column 1 and
the label is column 2 with `justify-self: end`; `.ww-legend-item`
restyled as a compact pill; a new `.ww-legend-label` rule for ellipsis
truncation; `wwRenderLegend()` now wraps each channel's text in a
`<span class="ww-legend-label">`; the module header comment updated),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(an "Update" note appended to DEC-026, no new decision entry; this work).
No new files. **No `frontend/waveform-prototype.html`/`theme.css`/
`theme.js` change, no `backend/` file, no CI/deployment workflow file was
touched.**

## What files were changed in the prior session (Phase 2C-B2 unified analog canvas layout)

Modified only: `frontend/index.html` (new CSS rules scoped under
`#wwPanels.ww-panels-unified` for the unified-canvas presentation; a
`wwUpdateBottomLaneAxis()` function; the `ww-panels-unified` class toggle
in `wwSetLayoutMode()`; calls to `wwUpdateBottomLaneAxis()` wired into
`wwAddSelectedChannels()`, `wwRemoveChannel()`, and `wwRebuildLayout()`;
the module header comment updated), `docs/project-memory/{DECISIONS,
MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (DEC-026 added; this work). No
new files. **No `frontend/waveform-prototype.html`/`theme.css`/`theme.js`
change, no `backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-B1 Grouped / Separate layout)

Modified only: `frontend/index.html` (a `ww.layoutMode` state field;
`wwPanelGroupKeyFor`/`wwPanelLabelFor` helpers; `wwRebuildLayout()`;
`wwSetLayoutMode()`; a small Grouped/Separate toolbar toggle;
`channelEntry.engineeringType` retained on add; the module header comment
updated), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,
HANDOFF}.md` (DEC-025 added; this work). No new files. **No
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no
`backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-A synchronized multi-channel waveform display)

Modified only: `frontend/index.html` (checkbox selection + Add/Clear
selected controls on the existing analog channel table; a new full-width
"Waveform Workspace" section: central toolbar, panel container, empty
state; the whole `ww*`-prefixed panel/viewport/toolbar/removal/theme JS
module), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,
HANDOFF}.md` (DEC-024 added; this work). No new files. **No
`frontend/waveform-prototype.html` change, no `backend/` file, no
CI/deployment workflow file was touched.**

## What files were changed in the prior session (crosshair visual UAT follow-up)

Modified only: `frontend/theme.css` (`--spike-color` values in both
themes), `frontend/waveform-prototype.html` (`spikethickness`/`spikedash`
values + updated code comments — no other logic touched),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(an "Update" note appended to DEC-023, not a new decision; this work). No
new files. **No `frontend/index.html` change, no `backend/` file, no
CI/deployment workflow file was touched.**

## What files were changed in the prior session (Light/Dark theme & crosshair refinement)

New: `frontend/theme.css`, `frontend/theme.js`.

Modified: `frontend/index.html` (theme link/script, header toggle,
`:root` block removed, `rgba(...)` literals replaced with tokens),
`frontend/waveform-prototype.html` (same, plus `themeColors()`,
`PlotlyRenderer.applyTheme()`, crosshair `spikethickness`/`spikecolor`
refinement, header toggle), `frontend/Dockerfile` (copies the two new
files), `frontend/.dockerignore` (comment accuracy only),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(DEC-023 added; this work). **No `backend/` file, no CI/deployment
workflow file was touched.**

## What files were changed in the prior session (Phase 2C discovery/design)

Modified only: `docs/project-memory/MIGRATION_PLAN.md` (new "Phase 2C —
Flexible Multi-Channel Waveform Workspace: Discovery and Design" section,
inserted between the Phase 2B Renderer Closure Record and the Phase 0
section), `docs/project-memory/CURRENT_STATE.md` (Development-phase
paragraph, Current-approved-focus paragraph, Next-approved-activity
paragraph, Documentation bullet, Major-currently-available-components
bullet), `docs/project-memory/HANDOFF.md` (this document). **No entry was
added to `DECISIONS.md`** — nothing in this pass rose to an approved
`[DECISION]`, per the task's own explicit instruction. **No `backend/` file,
no `frontend/` file, no CI/deployment workflow file was touched** — this was
a documentation-only, design/discovery pass.

## What files were changed in the prior session (Phase 2B renderer closure)

Modified: `frontend/waveform-prototype.html` (uPlot removal, crosshair
restyle, page-text simplification), `frontend/Dockerfile` (comment
accuracy only), `frontend/vendor/README.md` (uPlot entry removed, History
section added), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(DEC-022 added; this work).

Deleted: `frontend/vendor/uplot/uPlot.iife.min.js`,
`frontend/vendor/uplot/uPlot.min.css`, `frontend/vendor/uplot/LICENSE`.

No new files, no `frontend/index.html` change, no `backend/` file, and no
CI/deployment workflow file touched.

## What files were changed in the prior session (Phase 2B Plotly refinement)

Modified only: `frontend/waveform-prototype.html` (Plotly native
spike/crosshair config; relayout-handler autorange fix; debounce 200ms →
120ms; "Reset View" → "Reset Time View" label/wording; Phase 2C
extension-point and semantic-distinction comments — no HTML structure
change), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(DEC-021 added; this work).

No new files, no `frontend/vendor/*` change, no `frontend/index.html`
change, no `backend/` file, and no CI/deployment workflow file touched.

## What files were changed in the prior session (Phase 2B renderer UAT prototype)

New: `frontend/waveform-prototype.html`, `frontend/vendor/README.md`,
`frontend/vendor/uplot/{uPlot.iife.min.js,uPlot.min.css,LICENSE}`,
`frontend/vendor/plotly/{plotly-cartesian.min.js,LICENSE}`.

Modified: `frontend/index.html` (one new "Waveform (UAT)" link per analog
channel row; `renderChannelTable`/`renderAnalogGroup` extended with a
backward-compatible optional action-column parameter — digital channels'
call site unchanged), `frontend/Dockerfile` (serves the new page +
vendored assets), `frontend/.dockerignore` (comment only, no pattern
changes), `docs/project-memory/{MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(this work).

**`DECISIONS.md` was NOT modified** — no plotting-library winner was
chosen (explicitly out of scope; `[DECISION MODE: UAT]`), and no other
new non-UI technical decision was made this pass that wasn't already
covered by DEC-019/DEC-020.

No `backend/`, `docker-entrypoint.d/`, or CI/deployment workflow file was
touched.

## What files were changed in the prior session (Phase 2A implementation)

New: `backend/app/domain/waveform_reduction.py`,
`backend/app/services/waveform_service.py`,
`backend/app/schemas/waveform.py`,
`backend/tests/test_waveform_reduction.py`,
`backend/tests/test_waveform_service.py`,
`backend/tests/test_waveform_api.py`.

Modified: `backend/app/domain/source.py` (new `ActiveSource`),
`backend/app/domain/__init__.py`,
`backend/app/domain/disturbance_record.py` (docstring correction — see
below),
`backend/app/services/workspace_registry.py` (stored-value type widened
from `SourceMetadata` to `ActiveSource`; keying/locking/cleanup logic
itself unchanged; docstrings corrected),
`backend/app/services/import_service.py` (builds/stores `ActiveSource`
instead of discarding the parsed record; docstring corrected),
`backend/app/services/errors.py` (3 new error classes, shared base class
docstring broadened),
`backend/app/api/v1/sources.py` (new waveform endpoint; existing
endpoints' internals updated to unwrap `.metadata` — their
request/response contracts are unchanged),
`backend/tests/test_workspace_registry.py` (fixture helper builds
`ActiveSource`),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(this work — DEC-019 added).

**Stale-docstring corrections, not silent rewrites** (per the project's
own conflict-resolution rule): `app/domain/disturbance_record.py` and
`app/services/import_service.py`'s module docstrings both used to state
the `DisturbanceRecord` is discarded after upload — both now explain the
Phase 2A change and point to DEC-019, rather than leaving the old,
now-false claim in place uncorrected.

No `backend/app/providers/*`, `backend/app/main.py`, `frontend/*`, or CI/
deployment file was touched.

## What files were changed in the prior session (Phase 2 design)

Modified (documentation only — no application code):
- `docs/project-memory/MIGRATION_PLAN.md` — new "Phase 2 — Waveform
  Workspace Discovery and Design" section (~1,400 lines): verified
  `powerwave` findings, behavior-vs-implementation table, data-delivery
  architecture comparison (Options A-D), transfer-format comparison,
  frontend/backend boundary confirmation, plotting-library candidates,
  Phase 2 scope + channel-selection UX, panel model, analog scaling,
  time-axis handling, full-resolution zoom principle, peak-preservation
  recommendation, digital-signal preservation, browser/backend memory
  models, source-lifecycle extension proposal, TTL reassessment, session
  concurrency, API proposal, caching strategy, initial-load UX, loading
  states, error handling, performance targets, engineering-correctness
  test design, benchmark plan, and the full UAT/technical decision lists.
- `docs/project-memory/CURRENT_STATE.md` — recorded Phase 1's final owner
  UAT pass as complete; recorded that Phase 2 is in design-only stage with
  nothing implemented.
- `docs/project-memory/HANDOFF.md` — this section.

**`DECISIONS.md` was deliberately NOT modified** — no new item in the
Phase 2 design proposal has been owner-approved; recording any of it there
would misrepresent a proposal as a decision, which this task's own
instructions explicitly prohibited.

No `backend/` or `frontend/` file was touched.

## What files were changed in the prior session (workspace-reset fix)

New:
- `backend/app/api/v1/workspaces.py` — `DELETE /api/v1/workspaces/{workspace_id}`.
- `backend/tests/test_workspaces_api.py` — whole-workspace DELETE API tests.

Modified:
- `backend/app/services/workspace_registry.py` — added
  `remove_workspace(workspace_id)`.
- `backend/app/main.py` — mounts the new `workspaces_v1_router`.
- `backend/tests/test_workspace_registry.py` — added `remove_workspace()`
  unit tests.
- `backend/tests/test_sources_api.py` — added the `Remove`-regression test
  (sibling sources in the same workspace survive a single-source delete).
- `frontend/index.html` — `startNewWorkspace()` split into a confirmation
  gate (`requestNewWorkspaceConfirm`) and the actual ordered reset
  (`resetToNewWorkspace`: DELETE old workspace → only on success, rotate
  id and clear UI state); new confirmation dialog
  (`#newWorkspaceConfirmOverlay`) separate from `Remove`'s; new error
  element (`#workspaceResetError`) for cleanup failures.
- `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
  — this work (DEC-018 added).

No COMTRADE parser/provider/classification/config/storage file was
touched.

## Files changed in the prior session (UAT refinement pass)

New:
- `backend/app/domain/channel_classification.py`
- `backend/tests/test_channel_classification.py`

Modified:
- `backend/app/domain/source.py` — `AnalogChannelSummary` gained
  `engineering_type: str`.
- `backend/app/domain/__init__.py` — exports the classifier.
- `backend/app/schemas/source.py` — `AnalogChannelOut` gained
  `engineering_type`.
- `backend/app/services/import_service.py` — calls the classifier when
  building each analog channel's summary.
- `frontend/index.html` — collapsible grouping, analog sub-grouping,
  search, Scale/Offset removed from the primary table, remove
  confirmation dialog, stale-banner fix (for `Remove` only, at the time).

## GitHub / deployment status

See "GitHub persistence" and "DEV deployment" in this task's final report
(delivered in-conversation) for the exact commit hash, push confirmation,
independent-fetch verification, GitHub Actions run, and live-endpoint
checks for this Phase 3B pass. **Production was not touched.**

## What remains unresolved

- `[OPEN]`, **direct vertical drag/reorder of panels and drag-to-overlay/
  group by direct lane dragging are still fully unimplemented and
  undecided** — `[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`,
  not `[DECISION]`. Neither this pass (Phase 2C-C2A, a performance
  refinement of already-shipped panel resize) nor the prior one touched
  this — it remains the owner's stated *possible* next direction, not
  started, not abandoned.
- `[OPEN]`, unchanged: Proportional Y scaling, mixed-unit panel handling,
  digital-channel display, shared crosshair — every one of these remains
  `[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`.
- `[OPEN]` **Unchanged, still real**: abandoned-workspace cleanup still
  has no automatic expiry/TTL. `[DECISION MODE: COMPARISON]` — none of
  Phase 2C-A, Phase 2C-B1, Phase 2C-B2, Phase 2C-B3, Phase 2C-B3A, Phase
  2C-C1, Phase 2C-C2, or Phase 2C-C2A changes the backend memory-
  retention shape (still per-*source*, DEC-019), which raises (not
  resolves) the same urgency already flagged for every prior Phase 2C
  pass. See
  [MIGRATION_PLAN.md's Phase 2C §30](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15)
  and DEC-019's Impact section.
- `[OPEN]`, unchanged: digital waveform handling (still not built,
  explicitly the owner's own stated next area); the ~100 MB real-file
  memory ceiling (still not directly measured); and everything else
  already listed in
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).
- `[OPEN]`, unchanged from Phase 2C-C2: keyboard resizing of panel
  heights was not implemented (documented accessibility limitation,
  untouched by this investigation pass).
- **Carried over from Phase 2C-A's own manual UAT, deliberately not
  addressed this pass**: a small amount of interaction latency, judged
  currently bearable; and vertical (Y-axis) zoom being less intuitive
  than the rest of the toolbar — both explicitly flagged for a **later**
  UX refinement pass, not this one.
- **New this pass — explicitly unverifiable in this sandbox**: whether
  the resize-responsiveness refinement genuinely *feels* smoother to a
  human hand, and whether any momentary divergence between the box's
  edge and the waveform's own rendered edge is visible/distracting during
  a fast drag. The decoupling mechanism was proven structurally (jsdom
  instrumentation with a simulated-cost Plotly mock); the felt result was
  not and cannot be confirmed here. This is the primary thing the next
  owner UAT should specifically compare against the pre-Phase-2C-C2A
  build.
- **Unchanged from Phase 2C-A/B1/B2/B3/B3A/C1/C2**: real-browser
  rendering responsiveness and actual tactile/visual quality generally
  were not confirmed in this sandboxed, no-real-browser session — see
  this task's final report for the structural/code-level evidence
  gathered instead.

## What should be done next

**Phase 3A-UAT1 (width-reflow) passed owner UAT. Phase 3A-UAT2, UAT3,
UAT4, and now Phase 3B are all still awaiting a live DEV review —
Phase 3A-UAT3's OWN manual UAT is what surfaced the filename bug UAT4
fixed, so that portion of UAT3 has already been exercised.** The next
step is for the **project owner** to review Phase 3A-UAT2 through Phase
3B together via live DEV UAT: confirm the Global Header reads cleanly
with no leftover gap; confirm Settings is reachable/functional in both
Main Sidebar Menu states; confirm Light/Dark still works app-wide;
narrow the Workspace Sidebar to 240px and confirm BOTH the channel table
(scrolls rather than breaks) AND the CFG/DAT filenames in the
source-detail section stay contained; check long source/channel names
if a real event with them is available; check Grouped and Custom mode
legend chips with long channel names; narrow the browser around the
~900px responsive threshold and confirm the Sidebar becomes a
reopenable drawer at a SAFE width; switch to the Table placeholder,
resize something, then switch back to Waveform and confirm it isn't
visually stale; confirm no panel/dialog/table/text visibly overflows
its own frame anywhere — and specifically for **Phase 3B**: does the
Recordings page read as simple/clear/engineering-focused (not
card-heavy); is the Main Sidebar Menu's Waveform/Recordings split
intuitive; is the recording table readable with real data; does the
Upload New modal feel clear (format selector, file fields, loading/
error/success states); does Open/Analyse correctly land back on
Waveform with the right source's channels available; does navigating
Waveform ⇆ Recordings genuinely preserve viewport/zoom/grouping/panel
heights/time mode as claimed. This is a large but still deliberately
scoped pass — no Table/Split/digital-channel/CSV/Excel work, no shell
restructuring beyond what's described above. If confirmed clean: no
further action needed, and the still-open Phase 3A dimension/spacing
feedback remains welcome whenever convenient. If anything looks off,
report back with the specific control/page/mode — do **not** assume the
outcome. Separately, the owner may choose to: (a) request further Phase
3A dimension/spacing refinements or Phase 3B UX refinements; (b)
authorize the drag/reorder/overlay/split work directly (still the
owner's own possible next direction, deliberately set aside across
thirteen passes now, not abandoned); (c) request the still-outstanding
Grouped/Custom axis-duplication cleanup (Phase 2C-C4's own section 16
gap, unchanged across four passes now); (d) authorize real Table/Split
view implementation (explicitly NOT authorized yet — the shell only
avoids blocking it); (e) authorize real CSV/Excel parsing (the upload
modal's provider model is structurally ready but no parser exists —
explicitly NOT authorized yet); or (f) move on to digital channels (the
owner's own explicitly stated next area, and this task's own explicit
instruction: do **not** begin digital-channel, Table/Split, or CSV/Excel
work without a separate signal). Separately, resolving the abandoned-
session TTL question and the ~100 MB real-file memory validation remain
recommended before broader/prolonged shared-DEV UAT, unchanged
conclusion from every prior Phase 2 pass — and now additionally relevant
given Phase 3B makes uploading noticeably easier to reach (Global Header
Import + Recordings' own Upload New), which may increase how often
sources actually get imported during a shared-DEV session.

## What must not be assumed

- **Do not assume `index.html` still has an always-visible "Import
  COMTRADE Event" form in the Workspace Sidebar** — as of Phase 3B it was
  removed (`#uploadForm`/`#cfgInput`/`#datInput`/`#uploadButton`/
  `#uploadStatus` all no longer exist). Upload now happens exclusively
  through `#uploadModalOverlay` (opened via `openUploadModal()`), driven
  by `RECORDING_FORMATS`. If you need to trigger an upload from a test or
  from other code, target the modal's dynamic file inputs
  (`#uploadModalFileFields input[data-file-key="cfg"|"dat"]`), not the
  old fixed IDs.
- **Do not assume `shell.activeView` (`"waveform"`|`"table"`|`"split"`)
  and `shell.currentPage` (`"waveform"`|`"recordings"`) are the same
  concept** — they are two independent toggles at different levels.
  `currentPage` controls which top-level PAGE is shown in Work Area
  (`#workspaceRow` vs `#pageRecordings`); `activeView` only matters
  WITHIN the Waveform page, selecting its own sub-view. Setting one does
  not imply anything about the other except where `shellSetCurrentPage`/
  the Main Sidebar Menu's own click handlers explicitly coordinate them
  (e.g. clicking "Waveform" sets both to `"waveform"`).
- **Do not assume `refreshSourceList()` alone keeps the Recordings page
  in sync** — it only re-renders the Workspace Sidebar's compact source
  list. Anything that actually changes the source set (upload, remove,
  workspace reset) must call `refreshAllSourceViews()` instead, which
  refreshes BOTH the Sidebar list and the Recordings table from one
  shared fetch (`fetchSourcesList()`). `selectSource()` still correctly
  calls the narrower `refreshSourceList()` on its own, since selecting an
  already-listed source doesn't change the source SET.
- **Do not assume every element with `.hidden = true`/`false` set via JS
  actually becomes invisible** — if that element (or a class it carries)
  has its OWN author CSS `display` property (e.g. `display: flex`), that
  author rule beats the UA stylesheet's default `[hidden] {display:
  none}` rule by ORIGIN alone, regardless of specificity or source
  order, silently making the `hidden` attribute a no-op. `#workspaceRow`,
  `#pageRecordings`, and `#bottomStatusBar .shell-status-item` all needed
  (and now have) explicit `[hidden] { display: none; }` override rules
  for exactly this reason — check for this whenever adding a NEW
  `.hidden` toggle to an element that already has its own `display`
  rule; jsdom-based tests cannot catch this class of bug (no real CSS
  layout engine), so it must be checked by direct CSS inspection.
- **Do not assume `.detail-header`'s station-name/filename child `<div>`
  is still unnamed/unstyled** — as of Phase 3A-UAT4 it has a real class,
  `.detail-header-info` (`min-width: 0; max-width: 100%;`). This is the
  ACTUAL root-cause containment fix for the Channels source-detail
  filename overflow; `overflow-wrap: anywhere` alone on the text elements
  (Phase 3A-UAT3's own Finding C fix) was NOT sufficient by itself,
  because the flex item wrapping them never had `min-width: 0`. If a
  similar filename/long-text overflow is ever reported elsewhere in a
  flex layout, check the PARENT flex item's `min-width` first, not just
  the text element's own `overflow-wrap` — a text-level fix alone can be
  silently ineffective if its containing flex item can't shrink.
- **Do not assume `jsdom` implements `window.matchMedia`** — it does not,
  at all. `shellSyncSidebarWidthForBreakpoint()` (Phase 3A-UAT3, Finding
  F) calls it unconditionally at Init, so any NEW scratch test script
  that runs `index.html`'s real inline script needs the same
  `window.matchMedia`/`window.__setInnerWidth(px)` polyfill already added
  to all 16 existing scripts — omitting it aborts the whole `<script>`
  tag partway through Init, the same failure class as the Phase 3A-UAT1
  `requestAnimationFrame` gap.
- **Do not assume `#shellSidebarToggleBtn`'s CSS is still ordered
  base-rule-after-media-query** — Phase 3A-UAT3 (Finding A) moved the
  base `display: none` rule to BEFORE its `@media (max-width: 900px)`
  override; if either rule is edited again, keep the base rule first —
  equal-specificity selectors resolve by source order, and the earlier
  ordering silently disabled the reopen button.
- **Do not assume the Workspace Sidebar's inline `style.width` always
  reflects the user's desktop preference** — as of Phase 3A-UAT3
  (Finding F), it is deliberately CLEARED while `window.matchMedia
  ("(max-width: 900px)")` matches (so the CSS drawer rule governs) and
  only reflects the real persisted width at desktop widths. Read
  `workspaceSidebarSplit.getWidth()` (or the `localStorage` key), not
  `style.width` directly, if you need the user's actual preference
  regardless of current viewport.
- **Do not assume `.ww-legend-item`/`.ww-legend-label` are unstyled
  outside Separate mode** — Phase 3A-UAT3 (Finding G) added base
  (Grouped/Custom) `max-width`/ellipsis containment; the more specific
  `#wwPanels.ww-panels-unified .ww-legend-item/-label` selector (Separate
  mode, already passed owner UAT) still wins there via specificity,
  unchanged.
- **Do not assume `index.html`'s Global Header still has a `#themeToggle`
  element or that `mountThemeToggle()` is called from `index.html`'s own
  Init** — as of Phase 3A-UAT2, both were removed; the Main Sidebar
  Menu's "Settings" item (`#mainNavSettingsBtn`, flips theme directly via
  `window.PowerwaveTheme.getTheme()`/`setTheme()`) is now the sole theme
  entry point on this page.
- **Do not assume `theme.js`'s `mountThemeToggle()` function itself was
  removed or is unused** — it is still a live, shared, tested function;
  `frontend/waveform-prototype.html` (a separate, out-of-scope page)
  still mounts and uses it unchanged. Only `index.html`'s own header
  instance was removed.
- **Do not assume `.theme-toggle` (the CSS class) was removed** — it
  remains in use by the unrelated `#shellViewToggle` (Waveform/Table/
  Split) segmented control in the Global Header; only the `#themeToggle`
  element and its mount call were removed.
- **Do not assume Plotly's `responsive: true` config alone keeps a
  waveform panel correctly sized after ANY container-width change** —
  it reliably reacts to actual `window` resize events, but NOT to a
  container that changed size for another reason (a sibling flex item
  resizing). Any FUTURE code path that changes Main Workspace's
  available width (a future Table/Split divider, a future Workspace
  Sidebar redesign, etc.) must explicitly call
  `wwResizeAllVisiblePlots()` (or `wwScheduleResizeAllVisiblePlots()`
  for a rapid-fire-event source) — it will NOT happen automatically.
  This was the exact root cause of the Phase 3A-UAT1 bug.
- **Do not assume `shellCreateHorizontalSplit()`'s `onResize` callback
  fires on every raw pointermove** — it is rAF-coalesced (at most once
  per animation frame during a drag), with an authoritative final call
  on pointerup/pointercancel. A caller that needs to observe every
  intermediate width during a drag (not just the coalesced/final ones)
  would need different wiring.
- **Do not assume `.ww-chart-wrap`'s new `overflow: hidden` is what
  fixes waveform containment** — it is a defense-in-depth safety net
  only; the actual fix is making sure Plotly is always explicitly told
  to resize. If a future gap in that wiring reappears, this CSS rule
  will hide the symptom (clipped, not overflowing) without fixing the
  underlying cause — don't mistake "no visible overflow" for "Plotly is
  correctly sized."
- **Do not assume the page still scrolls as a whole document** — as of
  Phase 3A, `<body>` has `overflow: hidden`; each shell region
  (Workspace Sidebar, `#activeViewArea`) owns its own internal scroll.
  Global Header, Main Sidebar Menu, and the Bottom Status Bar are fixed
  in place and never scroll away. This is a structural change from
  every prior phase.
- **Do not assume `main`/`header`/`footer` bare-element CSS selectors
  still exist** — they were replaced by ID-scoped shell selectors
  (`#globalHeader`, `#appBody`, `#mainWorkspace`, etc.). The semantic
  tags themselves are still used in the HTML (`<header id="globalHeader">`,
  `<main id="mainWorkspace">`) but styled only via their IDs now.
- **Do not assume Table or Split view do anything real** — both are
  structural placeholders (`.shell-view-placeholder`) with zero data,
  zero fetches, and zero real grid/split rendering. `shell.activeView`
  can represent all three states, but only `"waveform"` has real
  content. Do NOT build real Table/Split functionality without a
  separate, explicit authorization — Phase 3A only avoids blocking it
  architecturally.
- **Do not assume Main Sidebar Menu and Workspace Sidebar share any
  state** — they are deliberately independent: one is a collapsed/
  expanded boolean toggle (`shell.mainSidebarExpanded`), the other is a
  drag-resized pixel width (`SHELL_WORKSPACE_SIDEBAR_*` constants +
  `shellCreateHorizontalSplit()`). Do not couple them when adding future
  behavior — the task's own section 21 explicitly required this
  independence.
- **Do not assume the shell reads or writes waveform-domain state
  (`ww`) directly** — it does not, except for a few narrow, one-way
  READS explicitly called by the OWNING waveform code (e.g.
  `shellUpdateStatusBarChannelCount(ww.displayed.size)` is called FROM
  `wwAddSelectedChannels`/`wwRemoveChannel`/`wwClearWorkspace`, never
  the reverse). Keep this direction when extending either side.
- **Do not assume Workspace Sidebar's min/max width (240px/520px) is
  computed dynamically against the current window width** — it is not;
  these are fixed pixel bounds, a documented, deliberate initial-phase
  simplification. The responsive drawer fallback (below ~900px) is what
  actually prevents an unusably narrow squeeze at real narrow
  viewports, not dynamic bound computation.
- **Do not assume the responsive drawer/collapse behavior was visually
  verified** — it was reasoned through and covered by CSS source
  inspection, but real narrow-viewport rendering was NOT confirmed in
  this sandbox (no real browser). Flagged for owner UAT.
- **Do not assume "Tools" exists anywhere in the UI** — it was
  deliberately omitted from both the Global Header and (as a REAL
  destination) Main Sidebar Menu this phase; only a disabled,
  clearly-marked placeholder nav item exists in the rail. No functional
  Tools destination exists yet.
- **Do not assume the ruler's title is rendered by a custom DOM
  element** — as of Phase 2C-C4B, `#wwStickyRulerTitle` and
  `#wwStickyRulerContext` were both deleted entirely (not hidden — the
  elements and their CSS no longer exist in the file at all). The
  title is now Plotly's own native `xaxis.title` property on the
  ruler's own chart layout, read via `layout.xaxis.title` (at init) or
  the most recent relayout's `update["xaxis.title"]` — the same pattern
  every real waveform panel already uses for its own title.
- **Do not assume "Record time" (lowercase t) is still the sticky
  ruler's Absolute-mode wording** — it is now "Record Time" (capital
  T), per explicit owner instruction in Phase 2C-C4B. The TOOLBAR's own
  `#wwTimeModeContext` label is unaffected and still uses lowercase
  "Record time" — the two are deliberately different now; do not
  "fix" one to match the other without checking which context you're
  in.
- **Do not assume any date text appears inside the sticky ruler** — it
  does not, as of Phase 2C-C4B; the ruler shows only tick labels and
  the mode title. The toolbar's own date-context label is the sole
  remaining place a date is shown.
- **Do not assume the ruler's Elapsed-mode tick VALUES are still raw
  seconds with just a relabeled title** — they are genuinely rescaled
  (×1000 for ms, ×1/60 for min) by `wwStickyRulerElapsedUnit()`, the
  SAME function that also chooses the title text, so title and ticks
  can never disagree (Phase 2C-C4A, section 4 of that task). This
  rescale is scoped ENTIRELY to the ruler's own independent Plotly
  x-axis domain.
- **Do not assume this rescale touches `ww.viewport`,
  `wwElapsedToPlotlyX()`, `wwBuildTrace()`, or any real waveform
  panel's own axis** — it does not; all of those remain exactly as
  Phase 2C-C3 left them, always raw elapsed seconds. Grouped/Custom
  panels' own per-panel axes (already a known, separate duplication
  with the ruler since Phase 2C-C4) are unaffected and still show raw
  seconds via the unchanged `wwTimeAxisTickFormat()`.
- **Do not assume Elapsed-mode unit-switching was verified to preserve
  tick-pixel alignment in a real browser** — it was reasoned through
  (Plotly's own "nice tick value" algorithm is scale-covariant under a
  constant multiplier) but NOT visually confirmed; no browser is
  available in this sandbox. Treat this as the single most important
  open item for owner UAT, not a settled fact.
- **Do not assume the ruler still has its own date-context line at
  all** — Phase 2C-C4A gave it one (date-only, alongside a
  "Record time" title); Phase 2C-C4B removed it entirely per owner
  correction. Only the toolbar's `#wwTimeModeContext` label still shows
  a date, unchanged full "<date> · Record time" wording.
- **Do not assume the sticky ruler is interactive** — it deliberately is
  not this slice (`staticPlot: true`, `pointer-events: none` on its CSS
  wrapper): not draggable, not zoomable, not pannable, not selectable,
  no crosshair. Waveform panels remain the only interaction surfaces;
  the ruler is display-only, per this task's own §11/§24.
- **Do not assume the ruler holds its own viewport or time-mode state**
  — it does not; `wwSyncStickyRuler()` reads `ww.viewport`/`ww.timeMode`
  fresh every time it is called and never stores an independent copy.
  There is no scenario where the ruler and the panels can show different
  ranges/modes simultaneously by construction.
- **Do not assume the ruler is a second waveform chart** — it carries an
  empty (`[]`) traces array always; it never fetches, holds, or displays
  channel data. Its only content is the shared x-axis.
- **Do not assume Grouped/Custom panels' own per-panel x-axis labels
  were suppressed by this phase** — they were **not**; only Separate
  mode's per-lane labels changed (now suppressed on every lane, not just
  the non-bottom ones). Grouped/Custom panels still show their own
  ticks/title on every panel, which now visibly duplicates the sticky
  ruler — a documented, deliberate, NOT-yet-fixed gap (section 16), left
  for a future cleanup pass rather than a larger restructuring this
  phase's own scope didn't justify.
- **Do not assume the ruler uses a scroll event listener** — it does
  not; its visibility/positioning is pure CSS `position: sticky`,
  confirmed by test to cause zero JavaScript work (zero Plotly calls,
  zero waveform fetches) when scroll events fire.
- **Do not assume the ruler is `position: fixed`** — it is
  `position: sticky`, constrained to `.workspace-section`'s own box; it
  does not float over the footer or any content below the waveform
  workspace, and stops being sticky once the whole workspace has
  scrolled past.
- **Do not assume the Absolute-mode timestamp is derived from the
  trigger time, the browser's clock, the upload time, or a guessed
  timezone** — it is derived exclusively from the backend's own
  `timebase.start_time` (already-parsed, existing COMTRADE CFG field),
  confirmed against real parsed metadata that sample 0 = `start_time`,
  never `trigger_time`. There is no timezone anywhere in this path — the
  parser never attaches one, and the frontend never invents or
  silently converts to browser-local time.
- **Do not assume Synthetic Elapsed Time or Sample Index are
  implemented** — they are not; both are reserved NAMES in the
  time-mode model (`WW_TIME_MODES`) for possible future CSV/Excel work
  only. The only two selectable modes today are Absolute and Elapsed.
- **Do not assume a time-mode switch ever refetches waveform data,
  changes `ww.viewport`, or changes which channels are displayed** —
  verified by test that it does none of these; it is a pure
  presentation transform of already-loaded data.
- **Do not assume multi-source Absolute-mode display has been solved**
  — it has not; if channels from sources with different recording-start
  timestamps were ever displayed together, Absolute-mode labels would
  use only the first-displayed channel's origin. This is a documented,
  known gap for future multi-source work, not something this pass fixed
  or hid.
- **Do not assume `ww.timeMode` resets when the workspace is cleared**
  — it deliberately does not; it persists as a viewing preference, same
  policy as `ww.layoutMode`/`ww.dragMode` (verified by test).
- **Do not assume drag/reorder/overlay/split has started** — it has not;
  no direct vertical lane dragging (to reorder panels), no reorder, no
  drop-to-overlay/group by direct lane dragging, no drag-out-to-separate
  exist anywhere in the repository. **Custom layout mode DOES now exist**
  (Phase 2C-C1, DEC-027) — do not confuse it with drag/reorder; Custom
  Groups are assigned via a modal dialog with dropdowns and buttons, not
  by dragging lanes. **Panel HEIGHT resize DOES now exist** (Phase
  2C-C2, DEC-028) — do not confuse this with lane drag/reorder either;
  the resize handle only ever changes a panel's vertical size, never its
  position/order relative to other panels, and there is still no way to
  reorder or drag one lane onto another.
- **Do not assume Custom mode's channel-to-group assignment uses
  drag-and-drop** — it deliberately does not (this task's own §6 allowed
  skipping it "unless genuinely simple"); moving a channel between groups
  is two explicit actions (remove from its current group via a chip's ×,
  then assign via an Unassigned-channel `<select>` dropdown).
- **Do not assume every displayed channel must be placed in a custom
  group before Apply works** — it does not; any unassigned channel
  automatically becomes its own single-channel panel (the documented,
  chosen rule, DEC-027). There is no validation error state to satisfy.
- **Do not assume Custom grouping is persisted to the backend or survives
  a page reload/new session** — it is not; `ww.customGroups` is
  frontend-only, in-memory, ephemeral session state (matching DEC-015's
  existing ephemeral-by-design principle), reset only by a whole-
  workspace clear ("Clear workspace"/"Start new workspace").
- **Do not assume panel resizing ever triggers a waveform refetch, resets
  the shared X/time viewport, or resets a panel's Y range** — verified by
  test that it does none of these; `Plotly.Plots.resize()` is the only
  Plotly API a height change ever calls.
- **Do not assume panel heights are persisted to the backend or survive a
  page reload** — they are not; `ww.panelHeights` is frontend-only,
  in-memory, ephemeral session state (matching DEC-015), reset only by a
  whole-workspace clear. Removing an individual channel/panel does NOT
  clear its remembered height (same policy as `ww.customGroups`).
- **Do not assume panel resizing supports keyboard input** — it does not
  this slice (documented accessibility limitation, DEC-028); the handle
  is `tabindex="-1"` and pointer/touch-drag only.
- **Do not assume the Phase 2C-C2A responsiveness refinement changed the
  100–600px height bounds, the panel-height state model, Plotly call
  COUNTS, or any Grouped/Separate/Custom/synchronization behavior** — it
  did not; only the ORDER/coupling of the existing DOM-write and
  Plotly-resize steps changed (the DOM write moved off the rAF gate; the
  Plotly call is still coalesced to at most once per frame, same as
  before). Confirmed by test that Plotly resize call counts are
  unchanged.
- **Do not claim the resize drag now "feels smoother" as a confirmed
  fact** — the decoupling mechanism was proven structurally via jsdom
  instrumentation with a simulated-cost Plotly mock, not via real
  browser paint timing or tactile testing (neither is available in this
  sandbox, and no browser-automation tool was installed to attempt it).
  This remains explicitly for owner manual UAT.
- **Do not assume the unified-canvas refinement changed the panel/layout
  data model or the Y-axis behavior** — it did not; `ww.panels` (displayed
  channels + panel membership + panel order) is byte-for-byte the same
  model Phase 2C-B1 (DEC-025) built. Each lane still has its own
  completely independent Y axis; **no channel was ever merged onto
  another channel's Y axis** — this was an explicit, deliberate
  distinction in the task's own instructions, not an incidental detail.
- **Do not confuse this pass's "overlay label" with the future
  "drag-to-overlay" interaction** — they are unrelated concepts that
  happen to share the word "overlay." This pass only changed the label's
  *visual position* (a static CSS overlay on the chart, no dragging, no
  interaction beyond the pre-existing remove button). Drag-to-overlay/
  group (dragging one channel's lane onto another to merge them) remains
  entirely unbuilt — do not read this pass as any part of that feature.
- **Do not assume digital channels or a digital-section container exist**
  — neither was built this pass; no digital content, fake or real, exists
  anywhere in the repository.
- **Do not assume the overlay label correction changed anything besides
  the tag's position/styling** — it did not; the same `.ww-legend`/
  `.ww-legend-item` DOM (now with one added `.ww-legend-label` wrapping
  span), the same remove control, the same color dot, the same panel/data
  model, and the same unified-canvas container from Phase 2C-B2 are all
  unchanged. Only the CSS grid-column order and the tag's own styling
  moved.
- **Do not assume Separate is the default** — Grouped is, unchanged from
  Phase 2C-A; Separate is opt-in via the new toolbar toggle.
- **Do not assume channels are permanently locked to their panel in
  either layout mode** — panel membership is always re-derivable from the
  flat displayed-channel list (`wwRebuildLayout()`); this is exactly the
  property that made Grouped/Separate switching straightforward and is
  the same property a future drag/reorder feature will rely on.
- **Do not assume switching layout mode refetches waveform data or
  resets the viewport** — verified by test that it does neither; already-
  fetched channel data and the current shared X/time range are both
  reused as-is.
- **Do not assume a multi-channel batching endpoint exists** — it does
  not; N displayed channels still means N independent existing
  single-channel requests, regardless of layout mode. Batching remains
  evidence-gated future work, not built.
- **Do not assume crosshair behavior changed** — each panel's crosshair
  (DEC-022/DEC-023, `spikethickness: 0.35`, `spikedash: "3px,2px"`,
  sample-snapped) is independent in both layout modes; hovering one panel
  does not show a guide line on any other panel.
- **Do not assume "Clear workspace" or channel removal touches an
  imported source** — both are purely display-state operations; the
  source (and its backend-retained record) is untouched either way, in
  either layout mode.
- Do not assume theme switching ever triggers a waveform data refetch — it
  doesn't, by design and by test; `Plotly.relayout` only, applied to
  every panel regardless of layout mode.
- **Do not assume Plotly is still "pending" or "preferred but open"** —
  it is the final, owner-selected renderer (DEC-022, unaffected by this
  pass). uPlot remains removed.
- **Do not assume DEC-021 (workspace-level navigation) is weakened by
  Separate mode having more panels** — the shared viewport is still
  mandatory and still enforced identically regardless of panel count.
- Do not assume TTL or the ~100 MB validation is solved — both remain
  explicitly open; neither Phase 2C-A nor Phase 2C-B1 changes the backend
  memory-retention shape (see "What remains unresolved" above).
- Do not assume the retained `DisturbanceRecord` (Phase 2A, DEC-019) or the
  waveform API's behavior changed this pass — zero backend files were
  touched; the existing single-channel endpoint's contract is unchanged.
- Do not assume `Start new workspace`/`Remove` behavior changed for
  SOURCES — both are unchanged from DEC-018; both already clean up the
  waveform workspace display, unaffected by which layout mode is active.
- Do not assume the COMTRADE upload interaction is still open for UAT — it
  is decided (DEC-017): two explicit slots, not auto-pairing.
- Do not assume Phase 1.5, drag/reorder work, or any later phase is
  authorized.
- Do not assume `powerwave` is still at commit `3156392` by the time you
  read this — this pass did not re-verify `powerwave` (no fresh
  `powerwave` investigation was needed for this implementation task); the
  last confirmed commit was `3156392`, from the Phase 2C design pass.

## Owner approval needed before proceeding?

- Not needed to review or use Phase 2C-A, Phase 2C-B1, Phase 2C-B2, Phase
  2C-B3, Phase 2C-B3A, Phase 2C-C1, Phase 2C-C2, Phase 2C-C2A, Phase
  2C-C3, Phase 2C-C4, Phase 2C-C4A, Phase 2C-C4B, Phase 3A, Phase
  3A-UAT1, Phase 3A-UAT2, Phase 3A-UAT3, Phase 3A-UAT4, or Phase 3B
  themselves — already implemented, deployed to DEV, and live-verified
  per this exact task's own authorization. **Recommended, though**: an
  owner UAT specifically confirming (a) the Global Header now reads
  cleanly with no leftover gap where the removed Light/Dark control sat,
  (b) the Main Sidebar Menu's "Settings" item remains comfortably
  reachable/usable in both collapsed and expanded states, (c) the Phase
  3A-UAT3 overflow fixes hold up visually — Workspace Sidebar at 240px,
  Grouped/Custom long legends, narrow-browser behavior around the
  ~900px responsive threshold, sidebar drawer reopen, and
  Waveform → placeholder → Waveform, (d) the Phase 3A-UAT4 fix
  specifically — the owner's own reported CFG/DAT filenames now wrap
  fully within the Sidebar at 240px with no horizontal escape, and (e)
  Phase 3B as a whole — Recordings page simplicity/readability, Main
  Sidebar Menu Waveform/Recordings navigation, the Upload New modal
  (format selector, file requirements, loading/error/success states),
  the Open/Analyse workflow, and that Waveform ⇆ Recordings navigation
  genuinely preserves viewport/zoom/grouping/panel-heights/time-mode as
  claimed — plus the still-open Phase 3A proportions/dimensions feedback
  and the still-carried-forward Phase 2C-C4A
  tick-alignment-at-rescaled-units claim — none of which could be
  visually confirmed in this sandbox.
- **Yes**, before any drag/reorder/overlay/split work begins (still the
  owner's own possible next direction, deliberately set aside across
  thirteen passes now, but still not yet explicitly authorized to
  *implement* — Phase 3A's shell only avoids blocking it
  architecturally), before REAL Table or Split view implementation
  (explicitly not authorized yet — only structural placeholders exist),
  before REAL CSV/Excel parsing (Phase 3B's upload modal is structurally
  ready for these formats — `RECORDING_FORMATS` lists them as
  `enabled: false` — but no parser exists for either; explicitly not
  authorized yet), before a persistent/database-backed recording
  library (Phase 3B's Recordings page is explicitly session/workspace-
  backed only, per DEC-032 — persistent retention is a separate future
  product/architecture decision, not to be backed into via a UI
  feature), before digital channels (the owner's own next stated area,
  not yet begun — and this task's own explicit closing instruction was
  to stop here, not begin it), before Synthetic Elapsed Time, Sample
  Index, or any CSV/Excel timing mode, before the Grouped/Custom per-panel
  axis-label duplication (Phase 2C-C4's own section 16 gap, unchanged
  and still outstanding across five passes now) is cleaned up, before
  interactive ruler zoom/pan/selection or a shared crosshair on the
  ruler, before Cursor A/B or Delta Cursor functionality in the Bottom
  Status Bar, before Phase 1.5 or any later phase begins, before a PROD
  deployment, before any further crosshair or theming work beyond
  what's already described in project-memory, and before any change to
  the ephemeral-storage, upload-size, COMTRADE-upload-interaction,
  workspace-lifecycle, or waveform-data decisions recorded in
  `DECISIONS.md`. Per the change-governance rule in
  [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md).
- **Recommended before any further prolonged/shared-DEV waveform UAT**: a
  real decision on the abandoned-session TTL question, and ideally the
  ~100 MB real-file memory validation, rather than continuing to rely on
  the manual DEV stopgap.
