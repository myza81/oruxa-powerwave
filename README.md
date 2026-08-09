# Powerwave

Powerwave is an Oruxa application. Architecture decisions are recorded in
[docs/architecture/oruxa-architecture.md](docs/architecture/oruxa-architecture.md),
which is the authoritative reference for anything structural.

## GitHub is the single source of truth

Every developer machine and every deployment environment takes its code from
GitHub. Nothing else is authoritative.

- Changes reach an environment by being committed, pushed and deployed — never
  by editing files on a host.
- A VPS checkout is a *deployment artefact*, not a workspace. `scripts/deploy.sh`
  runs against a commit the deploy workflow checked out; local edits there will
  be discarded by the next deployment.
- Secrets are the one exception: each host owns its own `.env`, which is never
  committed. [.env.example](.env.example) documents every variable.
- Deployment is manual. Merging to `main` runs tests but does not reach any
  environment; someone triggers the **Deploy Powerwave** workflow and picks a
  target.

## Supported environments

Powerwave has to run in four places. The application architecture stays
portable across all of them: no macOS-specific and no VPS-provider-specific
assumptions live in shared configuration.

| # | Environment | Docker | SSH | Purpose |
|---|-------------|--------|-----|---------|
| 1 | Windows company laptop | no | no | Lightweight local development and testing |
| 2 | MacBook / Mac mini | optional | yes | Local development, plus VPS administration |
| 3 | VPS DEV | yes | yes | Browser-accessible integrated development |
| 4 | VPS PROD | yes | yes | Production |

### Tooling

| Environment | Tooling | Notes |
|---|---|---|
| Windows company laptop | VS Code, Git, browser, Python/Node where permitted | No Docker and no SSH. Lightweight local execution and testing only. |
| MacBook / Mac mini | VS Code, Git, Python/Node, browser | Docker optional. SSH available for VPS administration. |
| VPS DEV / PROD | Docker, Linux | Integration and deployment environments. **Not a coding workspace** — see below. |

Both developer machines are equal peers: neither is the authoritative copy of
the codebase, and neither is required to build or run the other's work. The VPS
is where code *runs*, never where it is written.

### 1. Windows company laptop (no Docker, no SSH)

Everything except container behaviour can be developed and tested natively.

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements-dev.txt
```

Run the tests:

```bat
cd backend
pytest
```

Run the API (from `backend\`), pointing storage at any writable directory:

```bat
set STORAGE_PATH=%CD%\..\.local-data
uvicorn app.main:create_app --factory --reload --port 8000
```

Serve the frontend in a second terminal (from `frontend\`):

```bat
python -m http.server 8101
```

Then open <http://127.0.0.1:8101>. The checked-in
[frontend/config.js](frontend/config.js) already points at
`http://127.0.0.1:8000`, and port 8101 is in the default `CORS_ORIGINS`, so the
**Check Backend API** button works without further configuration.

What cannot be verified here: image builds, Compose overlays and container
networking. CI validates those on every push.

### 2. MacBook / Mac mini

The native workflow is identical to Windows:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt

cd backend && pytest
```

With Docker Desktop installed, the DEV stack can also be run locally — the same
command used on the VPS:

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

This machine is also where VPS administration happens over SSH.

### 3. VPS DEV

```bash
cp .env.example .env   # first time only, then edit
TARGET=dev ./scripts/deploy.sh
```

Or trigger the **Deploy Powerwave** workflow with target `dev`.

The DEV overlay mounts `backend/app` read-only and runs uvicorn with `--reload`,
and keeps the portable named volume for storage.

### 4. VPS PROD

```bash
TARGET=prod ./scripts/deploy.sh
```

Or trigger the **Deploy Powerwave** workflow with target `prod`.

The PROD overlay is the only file carrying host-specific detail, and it reads
all of it from the environment. These must be set in the production `.env`:

| Variable | Purpose |
|----------|---------|
| `POWERWAVE_DATA_PATH` | Host directory bind-mounted at `/data` |
| `POWERWAVE_UID` / `POWERWAVE_GID` | Owner of that directory |
| `CORS_ORIGINS` | Required when `ENVIRONMENT=production` |
| `API_BASE_URL` | Base URL the browser uses to reach the API |

Deployment fails fast if any of them is missing.

## Configuration

[backend/app/config.py](backend/app/config.py) is the only place that reads the
environment. It produces a frozen `Settings` dataclass; everything else receives
that object. Reading configuration performs no I/O, so importing the application
is side-effect free and misconfiguration fails at startup with a clear message
rather than a `KeyError`.

## Compose layout

| File | Role |
|------|------|
| [compose.yaml](compose.yaml) | Portable base. No host paths, no UID/GID, no external networks. Runs anywhere. |
| [compose.dev.yaml](compose.dev.yaml) | Development: reload, named volume, permissive CORS. Used locally *and* on VPS DEV. |
| [compose.prod.yaml](compose.prod.yaml) | Production: host bind mount, UID/GID, external `oruxa-backend` network. |

Always pass the base plus exactly one overlay.

## Storage

[backend/app/storage.py](backend/app/storage.py) provides a category-scoped
filesystem abstraction that object storage will later implement unchanged. Two
rules are enforced:

- **No escape.** Caller-supplied filenames are validated and the resolved path
  is confirmed to sit inside the category root.
- **Originals are write-once.** Files in the `original` category are as-received
  engineering inputs; overwriting one raises `ImmutableFileError`.

## Tests

```bash
cd backend
pytest
```

CI runs the same suite on every push and pull request, and the deploy workflow
runs it again before touching any environment.
