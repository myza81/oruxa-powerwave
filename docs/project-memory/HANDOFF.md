# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-15**

## What was most recently done

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

## What was verified (this pass — Phase 2B renderer UAT prototype)

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

## What files were changed this session (Phase 2B renderer UAT prototype)

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
checks for the Phase 2B prototype. **Production was not touched.**

## What remains unresolved

- `[OPEN]` **Unchanged, still real**: abandoned-workspace cleanup
  (browser tab closed, network lost, or the user never clicks
  `Remove`/`Start new workspace`) still has no automatic expiry/TTL.
  `[DECISION MODE: COMPARISON]` — see
  [MIGRATION_PLAN.md §18](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)
  and DEC-019's Impact section. Phase 2B did not implement TTL (per
  explicit task instruction) — instead documented a **temporary DEV-only
  operational stopgap** for this specific UAT session (owner clicks
  `Start new workspace` when done, or the DEV backend container is
  restarted between separate sessions) — see
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).
  This is a stopgap, not a solution — do not mark this `[OPEN]` item
  resolved.
- `[UAT]`, the whole point of this pass: **the plotting-library choice is
  now ready for the owner's hands-on judgment** (uPlot vs. Plotly,
  prototype live on DEV) — but remains undecided. Also still `[UAT]`/
  `[OPEN]`: zoom/pan interaction feel, autoscale behaviour, and every
  Phase 2C question (draggable/reorderable panels, custom panel
  grouping, independent Y axes).
- `[OPEN]`, unchanged: digital waveform handling (deliberately deferred —
  the waveform endpoint rejects digital channel names by design), the
  ~100 MB real-file memory ceiling (still not directly measured), and
  everything else already listed in
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers)
  (disk-free upload/parse, long-term persistence architecture, discovery
  engineering-improvement findings, richer parity fixtures).

## What should be done next

Per Phase 2B's explicit closing instruction: **stop after the prototype
is live and verified**. Do not begin Phase 2C (draggable/flexible panel
workspace), digital channels, cursors/measurements, calculated signals,
synchronization, or CSV/Excel without explicit owner approval. The next
step is for the **owner to actually run the UAT session**: open the
DEV build, import a COMTRADE source, open the waveform prototype from an
analog channel, compare uPlot and Plotly directly (zoom, pan, reset,
switch renderer repeatedly), and decide — a clear winner, "needs one
small refinement first," or "neither is satisfactory yet" are all valid,
honestly-reportable outcomes; nothing about this prototype should be
read as steering toward a predetermined answer.

## What must not be assumed

- **Do not assume a plotting-library winner has been chosen** — this
  entire pass exists to make that decision possible via hands-on UAT, not
  to make it. `DECISIONS.md` was not touched.
- Do not assume the Phase 2B prototype is the final waveform workspace —
  it is deliberately minimal (one channel, no cursors, no digital, no
  panels) and isolated from `index.html`; it exists to compare renderers,
  not to preview Phase 2C's actual design.
- Do not assume switching renderers in the prototype re-fetches data —
  it deliberately does not; the same already-fetched payload is handed to
  whichever adapter is now active.
- Do not assume TTL is solved — it explicitly is not; only a temporary,
  manual, DEV-only operational stopgap was documented for this specific
  UAT session (see "What remains unresolved" above).
- Do not assume any technical audit of `detego.app` was performed this
  pass beyond one bounded, public-marketing-page fetch (used only for
  high-level UX inspiration, e.g. "Detego's own copy states it uses
  Plotly.js" — noted factually, explicitly **not** used to favor Plotly
  in this UAT, per DEC-020).
- Do not assume the retained `DisturbanceRecord` (Phase 2A, DEC-019) or
  the waveform API's behavior changed this pass — zero backend files were
  touched; all 278 backend tests are unmodified and still pass.
- Do not assume the waveform endpoint serves digital channels — it
  explicitly rejects a digital channel name with `channel_not_analog`;
  digital waveform delivery remains deferred, by design.
- Do not assume `Start new workspace`/`Remove` behavior changed — both
  are unchanged from DEC-018, and (as verified this pass) both correctly
  make the waveform prototype respond safely to a source/workspace that's
  gone.
- Do not assume the COMTRADE upload interaction is still open for UAT — it
  is decided (DEC-017): two explicit slots, not auto-pairing.
- Do not assume Phase 1.5, Phase 2C, or any later phase is authorized.
- Do not assume `powerwave` is still at commit `3156392` by the time you
  read this — re-verify before relying on specific line numbers (it was
  re-confirmed unchanged as of this pass, 2026-08-15).

## Owner approval needed before proceeding?

- Not needed to review or run the Phase 2B UAT prototype itself (it's
  already implemented, deployed to DEV, and live-verified, per explicit
  owner authorization for this exact slice).
- **Yes**, before Phase 2C or any later Phase 2 slice begins, before
  Phase 1.5 or any later phase begins, before a PROD deployment, before
  any change to the ephemeral-storage, upload-size,
  COMTRADE-upload-interaction, workspace-lifecycle, or waveform-data
  decisions recorded in DECISIONS.md, and — the actual point of this
  pass — before a plotting library is chosen for production use. Per the
  change-governance rule in [CLAUDE.md](../../CLAUDE.md) /
  [AGENTS.md](../../AGENTS.md).
- **Recommended before any further prolonged/shared-DEV waveform UAT
  beyond this initial session**: a real decision on the abandoned-session
  TTL question, rather than continuing to rely on the manual DEV stopgap.
