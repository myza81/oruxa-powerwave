# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-15**

## What was most recently done

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

## What was verified (this pass — Phase 2C-B1 Grouped / Separate layout)

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

## What files were changed this session (Phase 2C-B1 Grouped / Separate layout)

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
checks for this Phase 2C-B1 pass. **Production was not touched.**

## What remains unresolved

- `[OPEN]`, **the remainder of the Phase 2C design proposal is still
  fully unimplemented and undecided**: direct vertical drag/reorder of
  panels, drag-to-overlay/group, drag-out-to-separate, Custom layout
  mode, panel resize, Proportional Y scaling, mixed-unit panel handling,
  digital-channel display, shared crosshair — every one of these remains
  `[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`, not
  `[DECISION]`. This pass (Phase 2C-B1) implemented and confirmed
  Grouped/Separate layout switching (DEC-025) — it did **not** touch any
  of the drag/reorder/overlay items above, which remain the owner's own
  stated *next* direction, not started.
- `[OPEN]` **Unchanged, still real**: abandoned-workspace cleanup still
  has no automatic expiry/TTL. `[DECISION MODE: COMPARISON]` — neither
  Phase 2C-A nor Phase 2C-B1 changes the backend memory-retention shape
  (still per-*source*, DEC-019, unaffected by how many panels/channels or
  which layout mode a UI displays against it), but a real, now-more-
  flexible multi-channel workspace is plausibly a richer, longer-lived
  thing to explore than Phase 2B's single-channel preview was, which
  raises (not resolves) the same urgency already flagged for Phase
  2A/2B/2C-A. See
  [MIGRATION_PLAN.md's Phase 2C §30](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15)
  and DEC-019's Impact section.
- `[OPEN]`, unchanged: digital waveform handling; the ~100 MB real-file
  memory ceiling (still not directly measured); and everything else
  already listed in
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).
- **Carried over from Phase 2C-A's own manual UAT, deliberately not
  addressed this pass**: a small amount of interaction latency, judged
  currently bearable; and vertical (Y-axis) zoom being less intuitive
  than the rest of the toolbar — both explicitly flagged for a **later**
  UX refinement pass, not this one.
- **Unchanged from Phase 2C-A**: real-browser rendering responsiveness at
  higher displayed-channel counts was not visually confirmed in this
  sandboxed, no-real-browser session — see this task's final report for
  the live DEV evidence gathered instead.

## What should be done next

The next step is for the **project owner** to review Phase 2C-B1 via live
DEV UAT (this task's own checklist) and choose a direction — none is
assumed here: (a) authorize the drag/reorder/overlay/split work directly
(the owner's own explicitly stated next direction, §13 of this task's own
instructions — vertical lane drag, reorder, drop-to-overlay/group,
drag-out-to-separate); (b) request refinements to Grouped/Separate itself
first (e.g. Custom mode, panel height); or (c) address the Phase 2C-A UAT
findings (interaction latency, vertical-zoom discoverability) before
further layout work. Do **not** begin any drag/reorder/overlay
implementation without an explicit signal — this task's own closing
instruction was to stop after Grouped/Separate. Separately, resolving the
abandoned-session TTL question and the ~100 MB real-file memory
validation remain recommended before broader/prolonged shared-DEV UAT,
unchanged conclusion from every prior Phase 2 pass.

## What must not be assumed

- **Do not assume drag/reorder/overlay/split has started** — it has not;
  no direct vertical lane dragging, no reorder, no drop-to-overlay/group,
  no drag-out-to-separate, no Custom layout mode, no panel resize exist
  anywhere in the repository.
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

- Not needed to review or use Phase 2C-A or Phase 2C-B1 themselves —
  already implemented, deployed to DEV, and live-verified per this exact
  task's own authorization.
- **Yes**, before any drag/reorder/overlay/split work begins (the owner's
  own stated next direction, but still not yet explicitly authorized to
  *implement*), before Custom layout mode or panel resize, before Phase
  1.5 or any later phase begins, before a PROD deployment, before any
  further crosshair or theming work beyond what's already described in
  project-memory, and before any change to the ephemeral-storage,
  upload-size, COMTRADE-upload-interaction, workspace-lifecycle, or
  waveform-data decisions recorded in `DECISIONS.md`. Per the change-
  governance rule in [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md).
- **Recommended before any further prolonged/shared-DEV waveform UAT**: a
  real decision on the abandoned-session TTL question, and ideally the
  ~100 MB real-file memory validation, rather than continuing to rely on
  the manual DEV stopgap.
