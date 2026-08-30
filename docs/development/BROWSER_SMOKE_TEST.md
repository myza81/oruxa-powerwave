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

## What it covers

One sequential walkthrough (a fresh backend process + fresh page load
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
- Broader UAT coverage (multi-source, Grouped/Separate/Custom, Change
  colour, digital channels, annotations, etc.) — this stays a small
  foundation, not a replacement for manual/live UAT on larger features.
