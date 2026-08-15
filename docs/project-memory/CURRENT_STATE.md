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
channel at a time. **No chart library, no frontend waveform rendering,
digital-channel waveform delivery, panel/layout UX, or Phase 2B/2C/2D
work exists yet** — those remain `[PROPOSAL]`/`[UAT]`/`[OPEN]`, per the
Phase 2 design section, and Phase 2A does not authorize starting them.

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
  instead. Still no framework, no build step, no routing — that remains an
  open, undecided question for a later phase.
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
  Design", and "Phase 2A — Implementation Record" sections).

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
collapsible/searchable channel grouping and a removal confirmation, this
documentation set. No frontend framework, no database schema, no
authentication, no CSV/Excel/frontend-waveform-rendering/digital-waveform/
synchronization/calculated-signal features yet. A Phase 2 waveform-workspace
**design proposal** exists (see [MIGRATION_PLAN.md](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14))
of which only the backend foundation slice (Phase 2A) has been implemented
so far — chart library, channel-selection UX, panel model, and Phase
2B/2C/2D remain unbuilt proposals/UAT candidates.

## Current approved focus

`[FACT]` Phase 1 (COMTRADE-only) is implemented, deployed to DEV, UAT'd,
refined per that UAT, and has had its whole-workspace reset lifecycle
corrected — see
[MIGRATION_PLAN.md — Phase 1 Implementation Record](MIGRATION_PLAN.md#phase-1--implementation-record-2026-08-14),
[Phase 1 — UAT Refinement Record](MIGRATION_PLAN.md#phase-1--uat-refinement-record-2026-08-14),
and
[Phase 1 — Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14).
Phase 2A (backend waveform data foundation) is implemented — see
[MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15).
`[DECISION]` Recorded this pass: DEC-019 — the active workspace retains
each source's full-resolution `DisturbanceRecord`, delivered only via
bounded time-range requests with peak-preserving (never naive-stride)
display reduction when needed; JSON-first transport for Phase 2A.
Recorded previously: `Start new workspace` is a distinct whole-workspace
lifecycle operation, backend-enforced (DEC-018); the two-slot COMTRADE
upload interaction is formally approved (DEC-017, resolves UAT-1). No new
architectural decisions were needed for the grouping/search/confirmation
refinements themselves — implementation detail, not decided direction (per
governance, not written to DECISIONS.md). **Not decided by any of the
above**: chart library, channel-selection/add interaction, panel layout,
drag/reorder panel UX, digital waveform handling, and abandoned-session
TTL policy — all remain `[UAT]`/`[COMPARISON]`/`[OPEN]`, per the Phase 2
design section and DEC-019's own Impact notes.

`[DECISION]` Recorded 2026-08-15: DEC-020 — `detego.app` is adopted as a
UI/UX/workflow/dashboard/product **benchmark** (not a ceiling) for feature
design, especially Phase 2B/2C waveform-workspace work — see
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) for the full three-way
comparison framework (`powerwave` = engineering behaviour,
`detego.app` = UI/UX benchmark, owner requirements/DECISIONS/UAT = final
authority). `oruxa_powerwave` should aim to exceed Detego where the
owner's engineering requirements justify it; a feature Detego lacks is
never on its own a reason to withhold it. No technical audit of
`detego.app` has been performed — this decision establishes the reference
relationship and its limits, not a feature comparison. Documentation-only;
no production code changed.

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

## Next approved activity

`[FACT]` Phase 1 is complete and has passed final owner UAT. Phase 2
waveform-workspace discovery/design is complete, and **Phase 2A (backend
waveform data foundation) is now implemented** — see
[MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15).
Per that task's own closing instruction, **Phase 2B is explicitly not
authorized yet**: no chart library dependency, no frontend waveform
rendering, no channel-selection UX, no panel model. The next step is for
the project owner to review Phase 2A (the new API, its tests, and its
measured memory/performance numbers) and decide: whether to proceed to
Phase 2B; how to resolve the now-more-urgent abandoned-session TTL
question (`[DECISION MODE: COMPARISON]`, per the Phase 2 design section
and DEC-019) before any prolonged/shared-DEV waveform UAT; and which
`[DECISION MODE: UAT]` items (plotting library, channel-selection
interaction, panel-layout extras) to schedule bounded prototypes for.
Phase 1.5 (CSV/Excel), synchronization, calculated signals, digital
waveform delivery, authentication, and any other later-phase
functionality remain explicitly **not** authorized.
