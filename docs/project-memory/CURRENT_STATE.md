# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now**. For how it got here, use Git history and
> [HANDOFF.md](HANDOFF.md); do not let this file accumulate into a diary.

Last meaningful update: **2026-08-15**.

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
  2C-B3A — Overlay Right-Side Lane Labels Implementation Record", and
  "Phase 2C-C1 — Custom Analog Channel Groups Implementation Record"
  sections).

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
persists across mode switches within the current workspace/session. No
frontend framework, no database schema, no authentication, no CSV/Excel/
digital-waveform/cursors-measurements/calculated-signal/synchronization
features yet; **direct drag/reorder of panels, drag-to-overlay/group by
direct lane dragging, and panel resize all remain not yet built** (the
owner's own choice to pursue Custom Groups first, not an oversight). A
Phase 2 waveform-workspace **design
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
2C-B1/DEC-025, Phase 2C-C1/DEC-027) are all implemented/decided. Direct
drag/reorder of panels, drag-to-overlay/group by direct lane dragging,
panel resize, Proportional Y scaling, mixed-unit handling, and
digital-channel display remain unbuilt/undecided design-proposal items
(`[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`) — the owner's
own choice, this pass, to pursue Custom Groups ahead of drag/reorder.

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
defer them in favor of Custom Groups this pass, along with panel resize,
Proportional Y scaling, mixed-unit handling, digital channels, and shared
crosshair. The next step is for the project owner to review Phase 2C-C1
via live DEV UAT and either request refinements to Custom Groups,
authorize the drag/reorder work directly, or defer further Phase 2C
work. Separately, resolving the
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
