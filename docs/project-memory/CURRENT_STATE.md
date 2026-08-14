# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now**. For how it got here, use Git history and
> [HANDOFF.md](HANDOFF.md); do not let this file accumulate into a diary.

Last meaningful update: **2026-08-14**.

## Development phase

`[FACT]` Per [AGENTS.md](../../AGENTS.md): *"Milestone 1 is foundational
hardening only. Not yet in scope: PostgreSQL schemas and migrations,
authentication, object storage, and Powerwave engineering/domain features."*

`[FACT]` **This has now changed for the domain-features part**: Phase 1 —
COMTRADE upload, parsing, and channel discovery — is implemented (2026-08-14),
the first actual Powerwave engineering/domain functionality in this
repository. Authentication, a database, and object storage remain out of
scope, matching Milestone 1. Phase 1 is implemented but **pending owner
UAT/acceptance** — see [HANDOFF.md](HANDOFF.md) for the checklist. No CSV/
Excel, waveform rendering, synchronization, calculated signals, or advanced
analytics exist yet (Phase 1.5 onward).

## Completed foundation work

`[FACT]`, verified against the repository on 2026-08-14:

- **Backend** (`backend/app/`): a FastAPI application (`main.py`) built via
  `create_app()` factory, now with:
  - `/health`, and a versioned COMTRADE source/channel API:
    `POST/GET /api/v1/workspaces/{workspace_id}/sources`,
    `GET/DELETE /api/v1/workspaces/{workspace_id}/sources/{source_id}`,
    `GET .../sources/{source_id}/channels`.
  - `domain/` — `DisturbanceRecord`/`AnalogChannel`/`DigitalChannel`/
    `RecordingMetadata`/`SamplingInformation`/`TimingInformation` ported
    near-verbatim from `powerwave` (commit `3156392`), plus new
    `SourceMetadata`/`AnalogChannelSummary`/`DigitalChannelSummary` for the
    lightweight metadata this API actually returns.
  - `providers/` — `BaseProvider`/`ProviderManager` and `ComtradeProvider`
    ported near-verbatim from `powerwave`. CSV/Excel providers are Phase
    1.5 scope, not present yet (see DECISIONS.md DEC-014).
  - `services/` — `WorkspaceRegistry` (in-memory, ephemeral, keyed by
    `workspace_id`/`source_id` — see DEC-012) and `import_service.py`
    (upload validation, size-limit enforcement, ephemeral parse via a
    per-request `tempfile.TemporaryDirectory()`, metadata extraction).
  - `schemas/` — Pydantic response DTOs (`SourceSummaryOut`,
    `SourceChannelsOut`, etc.) — never include waveform/sample arrays.
  - CORS middleware and a Content-Length pre-check middleware (fast-path
    upload-size rejection) configured from `Settings`.
  - Storage abstraction (`storage.py`, unchanged) — a `LocalStorage`
    backend enforcing filename-escape prevention and write-once `original`
    files. **Not used for event files in Phase 1** — see DEC-015: uploaded
    `.cfg`/`.dat` files are never persistently retained anywhere.
  - Configuration (`config.py`): all environment reads happen here,
    producing a frozen `Settings` dataclass, now including
    `MAX_EVENT_UPLOAD_SIZE_MB` (default 100 — an MVP operating assumption,
    not a hard limit; see DEC-016).
  - Dependencies: `fastapi`, `uvicorn`, `python-multipart` (upload
    parsing), `numpy`/`pandas` (ported COMTRADE provider, pinned to match
    `powerwave`'s own versions), `psycopg[binary]` (still unused, pinned
    for later).
  - Tests: 168 passing (`backend/tests/`) — the original foundation suite
    plus `test_comtrade_provider.py`, `test_comtrade_parity.py` (verified
    against `powerwave`'s canonical provider — see MIGRATION_PLAN.md's
    Phase 1 Implementation Record), `test_workspace_registry.py`,
    `test_sources_api.py` (upload/validation/lifecycle/API coverage).
    Synthetic COMTRADE fixtures live in `backend/tests/fixtures/comtrade/`
    — authored for this migration, not derived from any real/confidential
    event data.
- **Frontend** (`frontend/index.html`): extended from the original
  placeholder into a working single-page upload/channel-list UI —
  workspace identity (per-browser `crypto.randomUUID()`), COMTRADE
  `.cfg`/`.dat` upload (two explicit slots — a temporary Phase 1 choice,
  still `[UAT]`, see below), size guidance, busy/success/error states with
  user-safe messages, a source list with per-source removal, and a channel
  detail view (timebase + full analog/digital channel tables, no waveform
  data). Still no framework, no build step, no routing — that remains an
  open, undecided question for a later phase.
- **Docker/Compose**: unchanged this phase — `compose.yaml` +
  `compose.dev.yaml`/`compose.prod.yaml`, DEV/PROD isolation verified in CI.
  No Dockerfile changes were needed (`backend/Dockerfile` already copies
  the whole `app/` tree; `frontend/Dockerfile` already copies `index.html`).
- **CI/CD**: unchanged this phase (`.github/workflows/{ci,deploy}.yml`).
- **Documentation**: [docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md),
  [docs/development/development-workflow.md](../development/development-workflow.md),
  this project-memory framework, [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md),
  and [MIGRATION_PLAN.md](MIGRATION_PLAN.md) (now including a "Phase 1 —
  Implementation Record" section).

## Current architecture status

`[FACT]` The infrastructure follows the principles in
[docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
(read at the source; not duplicated here): frontend/backend separation,
configuration-driven infrastructure, GitHub as the single source of truth.
**Domain architecture now exists for COMTRADE only**: a ported data
contract, a ported provider, and a new ephemeral-by-design service/API
layer with no persistent storage of event files (DEC-015) and no
process-global mutable state (DEC-012). CSV/Excel, synchronization,
calculated signals, and analytics remain reference-only in `powerwave`, not
yet ported.

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
  (API), VPS checkout `/srv/oruxa/apps/powerwave-dev`, ports 8200/8201.
- PROD: `https://powerwave.oruxa.uk` (frontend), `https://api.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave`, ports 8100/8101.
- See [docs/development/development-workflow.md](../development/development-workflow.md)
  for the full deployment workflow. Phase 1 has **not** been deployed to
  either DEV or PROD as part of this work — implementation and local
  verification only; deployment is a separate, later step.

## Major currently available components

`[FACT]`: FastAPI backend with a working COMTRADE upload → parse →
channel-list API (ephemeral, no persistent storage of event files),
storage abstraction (unused by this feature), CI/CD pipeline, DEV/PROD
deployment isolation, a working single-page frontend for the same flow,
this documentation set. No frontend framework, no database schema, no
authentication, no CSV/Excel/waveform-rendering/synchronization/calculated-
signal features yet.

## Current approved focus

`[FACT]` Phase 1 (COMTRADE-only upload/parse/channel-discovery) is
**implemented** (2026-08-14) — see
[MIGRATION_PLAN.md — Phase 1 Implementation Record](MIGRATION_PLAN.md#phase-1--implementation-record-2026-08-14).
It is pending owner UAT/acceptance using the checklist in
[HANDOFF.md](HANDOFF.md) before being considered complete. `[DECISION]` Six
additional directions were approved and recorded this phase: uploaded event
files are never persistently retained (DEC-015), the upload size ceiling is
configurable with ~100 MB as the current MVP assumption (DEC-016), plus the
governance-cleanup-phase decisions (DEC-006–014, including COMTRADE-only
scope).

## Known blockers

- `[FACT]` The `origin` remote's configured SSH URL for `oruxa_powerwave`
  is not authenticated in these sandboxed sessions — established,
  repeatable workaround (explicit HTTPS push URL) documented in
  [HANDOFF.md](HANDOFF.md). Not an open blocker.
- `[OPEN]` The COMTRADE `.cfg`/`.dat` browser pairing interaction remains
  undecided — Phase 1 shipped the simplest option (two explicit upload
  slots) as a **temporary** choice, not a decision. See UAT-1 in
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md) and the UAT checklist in
  [HANDOFF.md](HANDOFF.md).
- `[OPEN]` A genuinely disk-free (zero temp-file-touch) upload/parse path
  was investigated and found to require rewriting `ComtradeProvider`'s
  file-based I/O — judged disproportionate for this slice per the "don't
  rewrite proven engineering logic" principle. What actually happens
  (Starlette's own multipart spooling above ~1 MB, plus this service's own
  necessary temp-directory staging, both automatically cleaned up) is
  documented in detail in [HANDOFF.md](HANDOFF.md) and
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md). Whether this is sufficient or a
  stronger guarantee is required is an open question for the owner.
- `[OPEN]` No measurement was taken near the ~100 MB configured ceiling
  itself (only up to ~16 MB); extrapolated memory usage suggests a 100 MB
  file could use 1+ GB resident memory during parsing. Worth a real
  measurement before raising the limit in any real deployment.
- `[OPEN]` The long-term persistence architecture (for whatever eventually
  needs to survive a session — not event files, which are now permanently
  ephemeral per DEC-015) remains undecided. Deferred to Phase 8.
- `[OPEN]` Remaining discovery engineering-improvement findings
  (COMTRADE discontinuity detection, raw timestamp traceability,
  timing-mode enforcement, duplicate CSV/Excel classifiers, calculated-signal
  grammar, frequency/ROCOF computation, the suggestions feature) are
  unchanged by Phase 1 — see
  [MIGRATION_PLAN.md — Review of the nine discovery open questions](MIGRATION_PLAN.md#review-of-the-nine-discovery-open-questions).
- `[OPEN]` Whether to commit a larger/richer set of real-event parity
  fixtures (vs. the synthetic ones committed this phase) for stronger
  ongoing regression coverage — not resolved; real `powerwave` sample files
  were deliberately not copied into this repository this phase (see
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md) and [HANDOFF.md](HANDOFF.md) for
  why).

## Next approved activity

`[FACT]` Per this phase's own closing instruction: **stop after Phase 1
implementation and verification**. Phase 1.5 (CSV/Excel), waveform
rendering, calculated signals, and any later phase are explicitly **not**
authorized to begin yet. The next step is for the project owner to work
through the UAT checklist in [HANDOFF.md](HANDOFF.md), and only then decide
what comes next (Phase 1.5, deployment of Phase 1 to DEV, or something
else).
