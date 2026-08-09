# Working in this repository

## Authoritative architecture reference

**Read [docs/architecture/oruxa-architecture.md](docs/architecture/oruxa-architecture.md)
before making any change that touches architecture, infrastructure, deployment,
storage, database, API boundaries or portability.**

That document is authoritative for Oruxa and Powerwave infrastructure
decisions. It is not summarised here and must not be copied into this file —
read it at the source. Where it is silent, ask rather than inferring
architecture from the code.

Its recurring test for any decision: *if this component moves to another server
tomorrow, what needs to change?* The answer should be configuration, DNS,
credentials and network settings — not business logic.

## Change governance

Fix what was asked for. Before modifying an existing function, workflow,
architecture or behaviour that appears incorrect or suboptimal — and before
acting on any architectural, behavioural, security, deployment or
data-integrity issue found outside the agreed scope — **stop and report**:

1. Issue
2. Evidence
3. Proposed solution
4. Benefits
5. Risks
6. Expected impact

Then obtain approval before implementing. Do not perform unrelated cleanup or
refactoring along the way.

## Ground rules

- **GitHub is the single source of truth.** Never fix an environment by editing
  files on a host. A VPS checkout is a deployment artefact, not a workspace.
- **Deployment is manual.** Do not deploy to production unless explicitly asked.
- **Configuration lives in one place.** Only [backend/app/config.py](backend/app/config.py)
  reads the environment; everything else receives a frozen `Settings`. Do not
  add `os.environ` reads elsewhere, and do not perform I/O at import time.
- **Compose stays portable.** [compose.yaml](compose.yaml) must run unchanged on
  Windows, macOS and Linux — no host paths, no UID/GID, no external networks, no
  provider-specific assumptions. Host-specific detail belongs in
  [compose.prod.yaml](compose.prod.yaml), read from the environment.
- **Four environments must keep working:** Windows laptop (no Docker, no SSH),
  Mac (optional Docker, SSH), VPS DEV, VPS PROD. See [README.md](README.md).
  Changes that only work with Docker, or only on a Mac, are not acceptable.
- **Dependencies are pinned exactly** in [backend/requirements.txt](backend/requirements.txt)
  and [backend/requirements-dev.txt](backend/requirements-dev.txt).

## Storage invariants

Two rules in [backend/app/storage.py](backend/app/storage.py) are load-bearing;
neither may be relaxed without an explicit decision:

1. Caller-supplied filenames can never escape the storage root.
2. Files in the `original` category are write-once.

## Tests

```bash
cd backend
pytest
```

The suite must pass before deployment; CI enforces this. Add tests alongside
behaviour changes — the storage and configuration layers in particular are
covered thoroughly and should stay that way.

## Current milestone

Milestone 1 is foundational hardening only. Not yet in scope: PostgreSQL schemas
and migrations, authentication, object storage, and Powerwave engineering/domain
features.
