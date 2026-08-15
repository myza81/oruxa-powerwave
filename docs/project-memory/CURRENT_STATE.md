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
  instead. **Added this pass (Phase 2B)**: `frontend/waveform-prototype.html`
  — an isolated renderer-UAT prototype (not part of the main channel-browse
  screen) with uPlot and Plotly.js adapters behind a shared contract,
  driven entirely by the existing Phase 2A waveform API; one new
  "Waveform (UAT)" link per analog channel row is the only change to
  `index.html` itself. `frontend/vendor/{uplot,plotly}/` holds the
  vendored (no-build-step, static, MIT-licensed) library bundles this
  prototype uses. **Refined this pass**: Plotly's layout now enables
  native axis spike-lines (`showspikes`/`spikesnap: "data"`/`spikemode:
  "across"`) for a hover crosshair; the relayout handler now correctly
  triggers a full-record re-fetch on Plotly's native Autoscale/Reset-axes
  buttons (previously silently ignored — a real bug found investigating
  the owner's reported lag); the viewport debounce was shortened from
  200ms to 120ms; "Reset View" was relabelled "Reset Time View" throughout
  to keep it terminologically distinct from "Autoscale Y" (DEC-021). uPlot
  is unmodified. Still no framework, no build step, no routing for the
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
  UAT Prototype Implementation Record", and "Phase 2B — Plotly
  Refinement & Workspace-Level Navigation Record" sections).

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
Plotly.js against that same waveform API, this documentation set. No
frontend framework, no database schema, no authentication, no CSV/Excel/
digital-waveform/cursors-measurements/calculated-signal/synchronization/
draggable-panel features yet. A Phase 2 waveform-workspace **design
proposal** exists (see [MIGRATION_PLAN.md](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14))
of which the backend foundation (Phase 2A) and a bounded renderer
comparison prototype (Phase 2B) have been implemented so far — the
plotting-library choice, channel-selection UX, panel model, and Phase 2C/
2D remain unbuilt proposals/UAT candidates, not decided.

## Current approved focus

`[FACT]` Phase 1 (COMTRADE-only) is implemented, deployed to DEV, UAT'd,
refined per that UAT, and has had its whole-workspace reset lifecycle
corrected — see
[MIGRATION_PLAN.md — Phase 1 Implementation Record](MIGRATION_PLAN.md#phase-1--implementation-record-2026-08-14),
[Phase 1 — UAT Refinement Record](MIGRATION_PLAN.md#phase-1--uat-refinement-record-2026-08-14),
and
[Phase 1 — Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14).
Phase 2A (backend waveform data foundation), Phase 2B (renderer UAT
prototype), and a Phase 2B Plotly-refinement pass are all implemented —
see
[MIGRATION_PLAN.md — Phase 2A](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15),
[Phase 2B Implementation](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15),
and
[Phase 2B Refinement Records](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15).
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
"Autoscale Y" are distinct operations, never collapsed. **Not decided by
any of the above**: which chart library wins (Plotly is `[UAT — preferred
pending final refinement confirmation]`, not closed), channel-selection/
add interaction, panel layout, drag/reorder panel UX, digital waveform
handling, and abandoned-session TTL policy — all remain
`[UAT]`/`[COMPARISON]`/`[OPEN]`.

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
waveform data foundation), Phase 2B (renderer UAT prototype), and a
Phase 2B Plotly-refinement pass are all now implemented** — see
[MIGRATION_PLAN.md — Phase 2A](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15),
[Phase 2B Implementation](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15),
and
[Phase 2B Refinement Records](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15).
Per this refinement pass's own closing instruction, **Phase 2C
(draggable/flexible panel workspace) is explicitly not authorized yet**,
and **no plotting library has been chosen** — Plotly is `[UAT — preferred
pending final refinement confirmation]`, still `[DECISION MODE: UAT]`,
for the owner to close out hands-on. The next step is for the project
owner to run the **final** UAT pass specifically: compare the refined
Plotly crosshair against uPlot's own crosshair one more time on DEV, and
either confirm Plotly, ask for one more small refinement, or reopen the
comparison — after which (only if confirmed) a later, separate cleanup
task would record the winner in `DECISIONS.md` and remove the losing
candidate. Also still pending: resolving the abandoned-session TTL
question (`[DECISION MODE: COMPARISON]`) before any further prolonged/
shared-DEV waveform UAT; and scheduling Phase 2C's own panel/interaction
UAT questions once the renderer is settled.
Phase 1.5 (CSV/Excel), synchronization, calculated signals, digital
waveform delivery, authentication, and any other later-phase
functionality remain explicitly **not** authorized.
