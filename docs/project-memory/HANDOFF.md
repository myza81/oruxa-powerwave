# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-14**

## What was most recently done

A **narrow UI refinement pass** on the already-implemented, already-deployed
Phase 1, driven directly by the owner's completed hands-on UAT of
`https://dev.powerwave.oruxa.uk`. No redesign, no scope expansion — see
[MIGRATION_PLAN.md — Phase 1 UAT Refinement Record](MIGRATION_PLAN.md#phase-1--uat-refinement-record-2026-08-14)
for full technical detail; summarized here for continuation purposes.

**What UAT approved and left alone**: the two-slot `.cfg`/`.dat` upload
workflow (now formally decided — DEC-017, not just a temporary Phase 1
choice), the loading/parsing indicator, the 100 MB guidance text, the
source-metadata-review-before-channels step, and the overall simple
single-page UI direction. None of these were touched.

**What UAT asked to change, and what was built**:

1. **Channel organization** — the reported problem was scrolling through
   hundreds of channels in one long table (UAT's own example: 80 analog,
   282 digital). Fixed with native `<details>`/`<summary>` collapsible
   sections (Analog defaults open, Digital defaults collapsed — the
   section that was actually overwhelming), always showing counts.
2. **Analog sub-grouping by engineering type** — `Voltage`/`Current`/
   `Power`/`Frequency`/`ROCOF`/`Undefined`. Classification is computed
   **once, backend-side** (new `backend/app/domain/channel_classification.py`),
   exposed as `engineering_type` on every analog channel — never
   re-derived or duplicated in the frontend. Three-tier rule (explicit
   `parameter_type` → unit semantics → nothing else — naming-pattern
   classification was deliberately not implemented, since no pattern was
   judged unambiguous enough): anything that doesn't confidently resolve
   is `Undefined`, never guessed into a real category.
3. **Channel search** — client-side only, over the already-fetched channel
   list, no network calls per keystroke. Auto-expands groups containing a
   match; clearing search restores the default expansion state.
4. **Scale/Offset removed from the primary analog table** — UAT found them
   low-value for browsing. Both fields are **unchanged** in the domain
   model and API response (`AnalogChannelSummary`/`AnalogChannelOut`) —
   only this one table stopped displaying them.
5. **Removal confirmation** — clicking "Remove" now opens one small
   confirmation dialog before the DELETE request is ever issued.
6. **Stale-banner bug fixed** — the import-success banner previously stayed
   visible after its source was removed. Now cleared, but only when it
   actually described the source just removed (tracked precisely, not a
   blanket clear-on-any-removal) — deliberately forward-compatible with a
   future multi-source workspace.

## What was verified

- **215 backend tests pass** (`cd backend && pytest`), up from 168 — new:
  `test_channel_classification.py` (every recognized unit/parameter_type,
  priority ordering, explicit ambiguous-channel-stays-Undefined coverage)
  plus a new API assertion that `engineering_type` appears correctly in
  live channel responses. No provider/parser code was touched this pass —
  COMTRADE parity is structurally unaffected (confirmed by the unmodified
  parity tests still passing).
- **Frontend logic verified against the actual shipped code**, not a
  reimplementation: a one-off Node script (not committed — no frontend
  test framework existed before this task, and none was introduced, per
  the task's explicit allowance to document manual/scripted verification
  instead) loaded `frontend/index.html`'s real inline `<script>` into a
  `jsdom`-backed DOM and exercised: grouping/counts/default-expansion/
  column-removal against an 80-analog/282-digital dataset matching UAT's
  own numbers; search (case-insensitive, cross-analog/digital,
  auto-expand-on-match, no-match empty state, clear-restores-default);
  the full remove-confirmation flow, explicitly confirming **Cancel issues
  zero DELETE requests**; the stale-banner fix; and — the task's explicit
  forward-compat check — that removing a *different* source never clears
  an unrelated still-valid banner. All passed. (One bug was caught and
  fixed in the *test script itself* during this process — an attempt to
  read a `let`-scoped JS variable via `window.X` from outside the script,
  which correctly doesn't work in real browsers either; the fix was to
  drive the real upload/removal code paths instead of poking at internal
  state, which is also the more faithful test.)
- **Live guardrail regression check** against a local `uvicorn` server:
  missing-companion-file (422), wrong-extension (400
  `unsupported_file_type`), and successful upload-then-delete-then-404 all
  behave exactly as before; the new `engineering_type` field appears
  correctly (`VA`/`VB` → `Voltage`, `IA` → `Current` for the synthetic
  fixture).
- No production code outside the intended scope was touched — see "Files
  changed" below.

## What files were changed this session

New:
- `backend/app/domain/channel_classification.py`
- `backend/tests/test_channel_classification.py`

Modified:
- `backend/app/domain/source.py` — `AnalogChannelSummary` gained
  `engineering_type: str`.
- `backend/app/domain/__init__.py` — exports the new classifier.
- `backend/app/schemas/source.py` — `AnalogChannelOut` gained
  `engineering_type`.
- `backend/app/services/import_service.py` — calls the classifier when
  building each analog channel's summary.
- `backend/tests/test_sources_api.py` — added an assertion that
  `engineering_type` is present and correct in the live API response.
- `frontend/index.html` — collapsible grouping, analog sub-grouping,
  search, Scale/Offset removed from the primary table, remove
  confirmation dialog, stale-banner fix.
- `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
  — this work (DEC-017 added, resolving UAT-1).

No backend parser/provider/config/storage file was touched.

## GitHub / deployment status

See the "GitHub persistence" and "Dev deployment" sections of this task's
final report (delivered in-conversation) for the exact commit hash(es),
push confirmation, GitHub Actions run, and live-endpoint verification for
this refinement pass. As of this write-up: committed and pushed to `main`,
and deployed to DEV via the existing "Deploy Powerwave" `workflow_dispatch`
(`target=dev`) — the same established, version-controlled process used for
every previous deployment this project. **Production was not touched.**

## What remains unresolved

Unchanged from before this pass — see
[CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers):
disk-free upload/parse (not solved, judged disproportionate), no
measurement near the real ~100 MB ceiling, long-term persistence
architecture (Phase 8), the discovery engineering-improvement findings,
and whether to commit richer real-event parity fixtures.

## What should be done next

Per this task's explicit closing instruction: **stop here**. Do not begin
Phase 1.5 (CSV/Excel), waveform rendering, synchronization, calculated
signals, advanced analysis, persistence redesign, or authentication. The
owner should review the refined DEV build and decide the next step.

## What must not be assumed

- Do not assume the COMTRADE upload interaction is still open for UAT — it
  is decided (DEC-017): two explicit slots, not auto-pairing.
- Do not assume Scale/Offset were removed from the backend or API — only
  from the frontend's primary browsing table.
- Do not assume digital channels received any sub-classification — none
  was added, deliberately (out of this refinement's scope).
- Do not assume the classification rules include a naming-pattern tier —
  they deliberately don't; only `parameter_type` and unit-based
  classification exist.
- Do not assume Phase 1.5 or any later phase is authorized.
- Do not assume `powerwave` is still at commit `3156392` by the time you
  read this — re-verify before relying on specific line numbers.

## Owner approval needed before proceeding?

- Not needed to review the refined DEV build.
- **Yes**, before Phase 1.5 or any later phase begins, before a PROD
  deployment, and before any change to the ephemeral-storage, upload-size,
  or COMTRADE-upload-interaction decisions recorded in DECISIONS.md — per
  the change-governance rule in [CLAUDE.md](../../CLAUDE.md) /
  [AGENTS.md](../../AGENTS.md).
