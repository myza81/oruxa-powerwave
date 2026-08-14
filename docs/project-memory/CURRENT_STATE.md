# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now**. For how it got here, use Git history and
> [HANDOFF.md](HANDOFF.md); do not let this file accumulate into a diary.

Last meaningful update: **2026-08-14**.

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
further Phase 1 work is expected. Phase 2 (basic web waveform workspace)
is now in its **discovery/design stage only** — see
[MIGRATION_PLAN.md — Phase 2 Waveform Workspace Discovery and
Design](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14).
**No Phase 2 code exists yet** — no waveform API, no chart library
dependency, no backend full-resolution-array retention, no frontend
waveform rendering. Everything in that design section is a `[PROPOSAL]`
or an item explicitly awaiting `[DECISION MODE: ANALYSIS/COMPARISON/UAT]`
resolution — none of it is approved architecture, and none of it should be
treated as authorization to begin implementation.

## Completed foundation work

`[FACT]`, verified against the repository on 2026-08-14:

- **Backend** (`backend/app/`): a FastAPI application (`main.py`) built via
  `create_app()` factory, with:
  - `/health`, and a versioned COMTRADE source/channel API:
    `POST/GET /api/v1/workspaces/{workspace_id}/sources`,
    `GET/DELETE /api/v1/workspaces/{workspace_id}/sources/{source_id}`,
    `GET .../sources/{source_id}/channels`, plus a whole-workspace
    lifecycle endpoint added this pass: `DELETE /api/v1/workspaces/{workspace_id}`
    (`app/api/v1/workspaces.py`) — releases every source the workspace
    owns in one call; idempotent for an unknown/already-empty workspace.
  - `domain/` — `DisturbanceRecord`/`AnalogChannel`/`DigitalChannel`/
    `RecordingMetadata`/`SamplingInformation`/`TimingInformation` ported
    near-verbatim from `powerwave` (commit `3156392`); `SourceMetadata`/
    `AnalogChannelSummary`/`DigitalChannelSummary` for the lightweight
    metadata the API returns; `channel_classification.py` — the
    backend-owned, three-tier analog engineering-type classifier
    (`Voltage`/`Current`/`Power`/`Frequency`/`ROCOF`/`Undefined`) added
    during the UAT refinement pass, exposed as `engineering_type` on every
    analog channel.
  - `providers/` — `BaseProvider`/`ProviderManager` and `ComtradeProvider`
    ported near-verbatim from `powerwave`. CSV/Excel providers are Phase
    1.5 scope, not present yet (see DECISIONS.md DEC-014).
  - `services/` — `WorkspaceRegistry` (in-memory, ephemeral, keyed by
    `workspace_id`/`source_id` — see DEC-012), now also with a
    `remove_workspace(workspace_id)` method (added this pass, DEC-018) that
    releases every source a workspace owns in one call, and
    `import_service.py` (upload validation, size-limit enforcement,
    ephemeral parse via a per-request `tempfile.TemporaryDirectory()`,
    metadata extraction including engineering-type classification).
  - `schemas/` — Pydantic response DTOs (`SourceSummaryOut`,
    `SourceChannelsOut`, etc.) — never include waveform/sample arrays.
    `AnalogChannelOut` still carries `scale`/`offset` (API/domain
    unchanged); the frontend's primary table just stopped displaying them.
  - CORS middleware and a Content-Length pre-check middleware (fast-path
    upload-size rejection) configured from `Settings`.
  - Storage abstraction (`storage.py`, unchanged) — **not used for event
    files** — see DEC-015: uploaded `.cfg`/`.dat` files are never
    persistently retained anywhere.
  - Configuration (`config.py`): `MAX_EVENT_UPLOAD_SIZE_MB` (default 100 —
    an MVP operating assumption, not a hard limit; see DEC-016).
  - Dependencies: `fastapi`, `uvicorn`, `python-multipart`, `numpy`/`pandas`
    (pinned to match `powerwave`'s own versions), `psycopg[binary]` (still
    unused, pinned for later).
  - Tests: **227 passing** (`backend/tests/`) — the original foundation
    suite, COMTRADE provider/parity tests (verified against `powerwave`'s
    canonical provider), workspace-registry tests (including
    `remove_workspace()` coverage added this pass), full API tests
    (including the new `test_workspaces_api.py` for the whole-workspace
    DELETE endpoint, and a `Remove`-regression test confirming sibling
    sources in the same workspace survive a single-source delete), and
    `test_channel_classification.py` (every recognized unit/parameter_type,
    priority ordering, and explicit never-guess-when-ambiguous coverage).
    Synthetic COMTRADE fixtures live in `backend/tests/fixtures/comtrade/`
    — authored for this migration, not derived from any real/confidential
    event data.
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
  and [MIGRATION_PLAN.md](MIGRATION_PLAN.md) (Phase 0 design, "Phase 1 —
  Implementation Record", and "Phase 1 — UAT Refinement Record" sections).

## Current architecture status

`[FACT]` The infrastructure follows the principles in
[docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
(read at the source; not duplicated here): frontend/backend separation,
configuration-driven infrastructure, GitHub as the single source of truth.
**Domain architecture now exists for COMTRADE only**: a ported data
contract, a ported provider, a backend-owned channel-classification module,
and an ephemeral-by-design service/API layer with no persistent storage of
event files (DEC-015) and no process-global mutable state (DEC-012).
CSV/Excel, synchronization, calculated signals, and analytics remain
reference-only in `powerwave`, not yet ported.

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
classify → channel-browse API (ephemeral, no persistent storage of event
files), storage abstraction (unused by this feature), CI/CD pipeline,
DEV/PROD deployment isolation, a working single-page frontend with
collapsible/searchable channel grouping and a removal confirmation, this
documentation set. No frontend framework, no database schema, no
authentication, no CSV/Excel/waveform-rendering/synchronization/calculated-
signal features yet. A Phase 2 waveform-workspace **design proposal**
exists (see [MIGRATION_PLAN.md](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14))
but nothing from it has been implemented.

## Current approved focus

`[FACT]` Phase 1 (COMTRADE-only) is implemented, deployed to DEV, UAT'd,
refined per that UAT, and has had its whole-workspace reset lifecycle
corrected — see
[MIGRATION_PLAN.md — Phase 1 Implementation Record](MIGRATION_PLAN.md#phase-1--implementation-record-2026-08-14),
[Phase 1 — UAT Refinement Record](MIGRATION_PLAN.md#phase-1--uat-refinement-record-2026-08-14),
and
[Phase 1 — Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14).
`[DECISION]` Recorded this pass: `Start new workspace` is retained as a
distinct whole-workspace lifecycle operation, separate from `Remove`'s
single-source scope, and is now backend-enforced rather than client-only
(DEC-018). Recorded previously: the two-slot COMTRADE upload interaction is
formally approved, not a placeholder (DEC-017, resolves UAT-1). No new
architectural decisions were needed for the grouping/search/confirmation
refinements themselves — implementation detail, not decided direction (per
governance, not written to DECISIONS.md).

## Known blockers

- `[FACT]` The `origin` remote's configured SSH URL for `oruxa_powerwave`
  is not authenticated in these sandboxed sessions — established,
  repeatable workaround (explicit HTTPS push URL) documented in
  [HANDOFF.md](HANDOFF.md). Not an open blocker.
- `[OPEN]` A genuinely disk-free (zero temp-file-touch) upload/parse path
  remains unimplemented — judged disproportionate per the "don't rewrite
  proven engineering logic" principle. Unchanged this pass; full
  investigation in [HANDOFF.md](HANDOFF.md) / [MIGRATION_PLAN.md](MIGRATION_PLAN.md).
- `[OPEN]` No measurement was taken near the ~100 MB configured ceiling
  itself (only up to ~16 MB); extrapolated memory usage suggests a 100 MB
  file could use 1+ GB resident memory during parsing. Unchanged this pass.
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
- `[OPEN]` **New this pass**: explicit `Start new workspace` cleanup is now
  correct (DEC-018), but an *abandoned* workspace — browser tab closed,
  network lost, or the user simply never clicks `Remove`/`Start new
  workspace` — still has no automatic expiry/TTL. `WorkspaceRegistry`
  entries in that case live in memory until the backend process restarts.
  Deliberately not solved this pass (explicit reset was the scoped
  problem, not every abandoned-session scenario) — see
  [MIGRATION_PLAN.md — Phase 1 Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14).

## Next approved activity

`[FACT]` Phase 1 is complete and has passed final owner UAT (see above).
Phase 2 waveform-workspace **discovery and design** has been completed
this pass — see
[MIGRATION_PLAN.md — Phase 2 Waveform Workspace Discovery and
Design](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14) —
but per that task's own closing instruction, **no Phase 2 implementation
is authorized yet**: not the waveform API, not a chart library dependency,
not backend full-resolution-array retention, not any frontend rendering.
The next step is for the project owner to review the Phase 2 design
proposal — including the `[DECISION MODE: COMPARISON]` items (data-delivery
architecture, abandoned-session TTL approach) and `[DECISION MODE: UAT]`
items (plotting library, channel-selection interaction, panel-layout
extras) — and decide what to approve before Phase 2A implementation
begins. Phase 1.5 (CSV/Excel), synchronization, calculated signals,
authentication, and any other later-phase functionality remain explicitly
**not** authorized either.
