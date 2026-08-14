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
been introduced yet.

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
  (HTTPS), branch `main`. Local clone was **2 commits behind `origin/main`**
  at verification time (`a5c7289..3156392`), with one pre-existing untracked
  0-byte file (`Make`) — neither was touched.

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

`[FACT]` Establishing the shared living project-memory framework
(`docs/project-memory/`) so Claude and Codex, working from either the Windows
laptop or the Mac mini, share the same project knowledge without depending on
individual chat/session memory. This document set is that framework.

## Known blockers

- `[FACT]` The account running the `powerwave` → `oruxa_powerwave` discovery
  work hit its **monthly spend limit** during the first discovery pass
  (2026-08-14), causing two of seven planned subsystem investigations (file
  import pipeline; background processing/tests/timestamp handling) to fail
  partway through. Five of seven subsystem investigations (data model &
  session state, synchronization, calculated signals, visualization
  rendering, analytics/measurement catalog) completed with substantial,
  citation-backed findings, but those findings have **not yet** been written
  into [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) — per the setup
  instructions for this framework, discovery findings are populated in a
  dedicated follow-up pass, not during framework setup. `[OPEN]` Resume/retry
  is blocked until spend limit headroom is available.
- `[FACT]` The `origin` remote's configured SSH URL for `oruxa_powerwave`
  (`git@github.com:myza81/oruxa-powerwave.git`) is not authenticated in these
  sandboxed sessions (`Permission denied (publickey)`, confirmed twice on
  2026-08-14). A follow-up session worked around this by pushing to the
  explicit HTTPS URL instead (without changing `origin`'s config) — see
  [HANDOFF.md](HANDOFF.md) for the exact method and the caveat that
  `origin/main`'s local tracking ref stays stale until SSH is actually fixed
  or a plain `git fetch origin` succeeds.

## Next approved activity

`[FACT]` Per the instructions that created this framework: *"Run the
detailed `powerwave` → `oruxa_powerwave` discovery audit and populate
POWERWAVE_DISCOVERY.md."* This was explicitly deferred to a separate,
subsequent task and has not been started as part of this framework-setup
work (see the blocker above regarding partially-completed prior discovery
work that is not yet reflected in this repository's documentation).
