# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now**. For how it got here, use Git history and
> [HANDOFF.md](HANDOFF.md); do not let this file accumulate into a diary.

Last meaningful update: **2026-08-14**.

## Development phase

`[FACT]` Per [AGENTS.md](../../AGENTS.md): *"Milestone 1 is foundational
hardening only. Not yet in scope: PostgreSQL schemas and migrations,
authentication, object storage, and Powerwave engineering/domain features."*

This repository currently contains infrastructure and deployment foundation
only. No Powerwave engineering/domain functionality (COMTRADE/CSV/Excel
parsing, waveform models, calculated signals, synchronization, analytics) has
been introduced yet. The `powerwave` → `oruxa_powerwave` discovery audit is
now complete (see below) and did not change this — discovery is analysis
only, no implementation has started.

## Completed foundation work

`[FACT]`, verified against the repository on 2026-08-14:

- **Backend**: a minimal FastAPI application (`backend/app/main.py`) built via
  `create_app()` factory, with:
  - a single `/health` route,
  - CORS middleware configured from `Settings`,
  - a storage abstraction (`backend/app/storage.py`) with a `LocalStorage`
    backend enforcing two invariants: caller-supplied filenames can never
    escape the storage root, and files in the `original` category are
    write-once.
  - centralized configuration (`backend/app/config.py`): all environment
    reads happen here, producing a frozen `Settings` dataclass; nothing else
    reads `os.environ` directly, and importing the app performs no I/O.
  - Dependencies: `fastapi`, `uvicorn`, `psycopg[binary]` (PostgreSQL driver
    pinned now; no schema/migrations exist yet — see Milestone 1 note above).
  - Tests: `backend/tests/` — `test_config.py`, `test_main.py`,
    `test_storage.py`, `test_compose_config.py`, `test_frontend_entrypoint.py`
    (783 lines total).
- **Frontend**: a single static `index.html` + `config.js`, no framework, no
  routing, no state management, no charting library. `config.js` is
  regenerated at container startup from `API_BASE_URL` so one image can be
  promoted from DEV to PROD without a rebuild.
- **Docker/Compose**: `compose.yaml` (portable base) + `compose.dev.yaml` /
  `compose.prod.yaml` (environment-specific overlays). DEV and PROD run as
  isolated Compose projects (`powerwave-dev` / `powerwave-prod`) with
  non-overlapping ports (8200/8201 DEV, 8100/8101 PROD) and separate storage
  paths (`/srv/oruxa/data/powerwave-dev` / `/srv/oruxa/data/powerwave`) —
  verified in CI (`.github/workflows/ci.yml`), which asserts this isolation
  by rendering both overlays and checking project names, image tags, and
  ports.
- **CI/CD**: `.github/workflows/ci.yml` runs backend tests and validates both
  Compose overlays on every push/PR. `.github/workflows/deploy.yml` is a
  manual, `workflow_dispatch`-triggered deploy (target `dev` or `prod`) that
  re-runs tests, checks out the chosen Git commit by SHA on the VPS, and
  fails fast if `VPS_APP_PATH` is not configured for the target GitHub
  Environment.
- **Documentation**:
  - [docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
    — authoritative Oruxa/Powerwave infrastructure architecture.
  - [docs/development/development-workflow.md](../development/development-workflow.md)
    — branch/PR/CI/DEV/PROD workflow reference.
  - This project-memory framework (`docs/project-memory/`), created
    2026-08-14.
  - [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) — full technical
    discovery of `powerwave` at commit `3156392`, completed 2026-08-14.

## Current architecture status

`[FACT]` The infrastructure follows the principles in
[docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
(read at the source; not duplicated here): frontend/backend separation,
configuration-driven infrastructure, a portable storage abstraction, DEV/PROD
isolation, and GitHub as the single source of truth for code. No
Powerwave-specific domain architecture (data contracts, provider pattern,
session/synchronization model, calculated signals) exists in this repository
yet — those exist only in the reference `powerwave` desktop application.

## Repository identity

`[FACT]`, verified 2026-08-14 via `git remote -v` in each local clone:

- `oruxa_powerwave` (this repo): `git@github.com:myza81/oruxa-powerwave.git`
  (SSH), branch `main`.
- `powerwave` (reference desktop app, macOS clone at
  `/Volumes/externalDrive/code-gym/powerwave/`): `https://github.com/myza81/powerwave.git`
  (HTTPS), branch `main`. Fast-forwarded to `3156392` (from `a5c7289`) on
  2026-08-14 and reconfirmed current with `origin/main` at that commit; one
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
  for the full deployment workflow. Note (recorded there already): the exact
  DNS names and DEV database name live in VPS/Caddy config and database
  provisioning outside this repository, not in code.

## Major currently available components

`[FACT]`: FastAPI skeleton, storage abstraction, CI/CD pipeline, DEV/PROD
deployment isolation, this documentation set. No frontend framework, no
database schema, no authentication, no domain/engineering features.

## Current approved focus

`[FACT]` The `powerwave` → `oruxa_powerwave` discovery audit is complete
(2026-08-14) — see [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md). No
implementation work is approved yet. The project is now waiting on owner
review of that document's `[OPEN]` questions and `[PROPOSAL]` migration
phases before any design decisions get recorded in
[DECISIONS.md](DECISIONS.md) or any implementation begins.

## Known blockers

- `[FACT]` The `origin` remote's configured SSH URL for `oruxa_powerwave`
  (`git@github.com:myza81/oruxa-powerwave.git`) is not authenticated in these
  sandboxed sessions (`Permission denied (publickey)`, confirmed multiple
  times on 2026-08-14). The established workaround is pushing to the
  explicit HTTPS URL instead (without changing `origin`'s config) — see
  [HANDOFF.md](HANDOFF.md) for the exact method and the caveat that
  `origin/main`'s local tracking ref stays stale until SSH is actually fixed
  or a plain `git fetch origin` succeeds. This is now a known, repeatable
  workaround, not an open blocker to future work.
- `[OPEN]` Nine open questions from the discovery audit need owner decisions
  before related implementation phases can be approved — see "Open
  Questions" in [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) for the
  full list (spans timing-mode enforcement, COMTRADE discontinuity
  detection, raw-value traceability, classification-system unification,
  session persistence format, calculated-signal expression scope,
  frequency/ROCOF computation scope, the suggestions feature, and
  authentication/multi-user timing).

## Next approved activity

`[FACT]` None yet approved beyond discovery. The natural next step —
per [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md)'s own closing
recommendation — is for the project owner to review that document's open
questions and proposed phases, record any approved decisions in
[DECISIONS.md](DECISIONS.md), and only then approve a first implementation
slice. `[PROPOSAL]` (not yet approved): the discovery document recommends
upload → parse → normalize → channel-list API as the first vertical slice,
deliberately stopping short of waveform rendering.
