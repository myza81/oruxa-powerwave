# Browser smoke test

A minimal, committed real-browser safety net for the critical path
CSV/Excel ingestion is about to start touching: upload -> parsing ->
source model -> RECORDINGS sidebar -> waveform rendering -> Time Group
behavior. It runs against **local code only** (never a deployed
hostname) via Playwright + a real headless Chromium.

This is intentionally small — a survival check, not a QA framework. See
[DECISIONS.md — DEC-071](../project-memory/DECISIONS.md#dec-071--a-minimal-committed-real-browser-smoke-test-foundation-playwright--local-backendfrontend-is-added-ahead-of-csvexcel-ingestion-ci-integration-deliberately-deferred)
for the governing decision and what was deliberately left out.

## Install (one-time)

```bash
cd browser-tests
npm install
npx playwright install chromium
```

## Run

```bash
cd browser-tests
npm run test:browser-smoke
```

(equivalently: `npx playwright test`)

This starts a real backend (`uvicorn`, the same `app.main:create_app`
factory the real app uses, against a fresh temp `STORAGE_PATH`) and
serves the real `frontend/index.html` statically on `127.0.0.1:8101`
(matching the backend's own default CORS allowlist — no config
changes needed), launches Chromium, runs the smoke walkthrough, and
tears both servers down automatically. No Docker, no deployed
environment. Override ports via `PW_BACKEND_PORT`/`PW_FRONTEND_PORT`
if 8000/8101 are already in use locally.

## Original smoke walkthrough

`smoke.spec.js` is one sequential walkthrough (a fresh backend process + fresh page load
already gives each run a clean workspace, so later steps intentionally
build on earlier ones rather than each re-uploading from scratch):

1. App loads, RECORDINGS area exists.
2. Upload the existing `synth_ascii` COMTRADE fixture (already used by
   the backend's own test suite,
   `backend/tests/fixtures/comtrade/synth_ascii.{cfg,dat}`, ~1.3 KB) —
   source appears in RECORDINGS.
3. Display one analog channel — a real waveform trace renders.
4. That channel belongs to a rendered Time Group canvas.
5. Cursor A/B mode toggles on for that Time Group.
6. Right-click the channel row — native browser menu suppressed,
   Powerwave's own context menu appears.
7. Rename... opens, targeting the correct original channel name.
8. Zero unexpected browser console/page errors across the whole run.

Assertions test survival (does it render, does it respond), never pixel
layout, fonts, colors, or screenshots — those stay owner-tuned and
untouched.

## Not included (yet)

- **CI integration** was evaluated and deliberately deferred — it would
  need a second runtime (Node + Chromium download/caching) orchestrated
  alongside the existing Python-only CI job, which the current
  `.github/workflows/ci.yml` doesn't do for anything today. Adding it
  is a reasonable next step once this local foundation has proven
  itself, not part of this slice.
- The original foundation has since expanded to the complete browser regression
  suite (waveform, analyser, reconstruction, calculated-channel, relay import and
  session timing coverage). See the four-worker release command below. Browser
  regression coverage complements owner engineering UAT.

## Relay setting sheets (DEC-199)

Relay-import specs never build relay sheets in JavaScript. `relaySheet(id, overrides)`
(`support/relay_import_helpers.js`) runs `python -m tests.relay_conformance.sheet_cli` from `backend/` with `PW_PYTHON`
(the same interpreter that starts the backend), so the sheets are the backend's single-source specs
(`backend/tests/relay_conformance/sheets`). `relay_import_conformance.spec.js` checks every relay's review against
`backend/tests/relay_conformance/expectations`.


## Complete release regression (Slice B)

The historical smoke default remains one worker. Release validation runs **all specs
with four workers**, no retries, against fresh local backend/frontend processes:

```powershell
cd browser-tests
$env:PW_PYTHON = '<absolute path to backend Python>'
$env:BEN5K_EXPERIMENTAL_ENABLED = '1'
$env:CI = '1'
$env:PLAYWRIGHT_JUNIT_OUTPUT_FILE = "$env:TEMP/powerwave-browser-full.xml"
npx playwright test --workers=4 --reporter=line,junit
```

Every spec imports `test` from `support/test.js`. Each test receives Playwright's
fresh browser context and a fresh app-generated workspace UUID. The automatic
fixture records local workspace UUIDs used by that context; after the test, it
closes the context (stopping playback and pending requests) and deletes only those
workspaces through the API. Already-deleted workspaces are allowed; other cleanup
failures fail the test. No shared registry reset, retry, production page-close
workspace deletion or interpretation persistence is introduced. Reload and
cross-session tests retain their workspace for the entire test.

Sequence manual-input helpers wait for the final input parameters' API response
and its acceptance into rendered state. Phasor bootstrap gates its request until
the temporary identification state is asserted. Playback tests wait for actual trail
growth; numerical and pause-stability assertions remain. A serial rerun is useful
to diagnose failures but never replaces this full parallel release check.


Slice B follow-up readiness checks await matching accepted Distance results,
annotation redraw coordinates and actual bootstrap transport completion. Axis
readiness polls inspect only pending-axis metadata; PU comparisons retain the
same tolerance over every sample with a maximum-error assertion and length check.
The navigation/removal console-error regression includes failed-response paths in
its assertion message. Final release evidence and unresolved blockers are recorded
in [SLICE_B_RELEASE_HARDENING.md](../project-memory/SLICE_B_RELEASE_HARDENING.md).


## Slice C local diagnostics

Set `PW_DIAGNOSTICS_DIR` to a new local temporary directory to opt into safe
client/server JSONL diagnostics. The backend wrapper calls the same `create_app`
factory and retains the installed default HTTP protocol and five-second keep-alive.
Events correlate PID, peer/client socket ports, reuse, FIN/close, method/path/status,
request cancellation and worker/context/application/cleanup lifetimes. No headers,
query strings, body contents or page-session nonces are recorded. Diagnostic errors
do not retry or suppress the failed operation. With the variable absent, startup
uses the original Uvicorn command and diagnostics perform no logging.

`PW_FRONTEND_DIR` optionally serves a temporary frontend copy for controlled
baseline comparisons; normal validation leaves it unset and serves this checkout.
These are test controls, with no deployment or application configuration effect.


## Local API idle socket ownership

The shared fixture and runner register only their loopback backend port with
`support/local_backend_transport.js`. Free API sockets retire at four seconds,
before Uvicorn's unchanged five-second idle expiry. Warm connections still pool;
active request/header/body budgets are restored on reuse. The wrapper also retires
expired free sockets synchronously before dispatch if worker load delayed timers.
No request is retried, no Connection header is forced, and other ports are untouched.
This corrects the reproduced Node pool/server idle-expiry race, rather than changing
engineering assertions or request timeouts. Context disposal alone does not empty
Playwright's shared agent pool. See
[Slice C evidence](../project-memory/SLICE_C_TRANSPORT_LIFECYCLE.md).
