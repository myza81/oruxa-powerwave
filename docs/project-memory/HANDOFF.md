# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-14**

## What was most recently done

Completed the **Phase 0 migration design** and wrote it into
[MIGRATION_PLAN.md](MIGRATION_PLAN.md) (replacing the earlier high-level-only
placeholder). This covers: a canonical-runtime reuse mapping (re-verified
directly against `powerwave` code, not assumed from the discovery document),
a Phase-1-minimum domain model (`Workspace`/`Source`/`Channel` family), a
target backend module map, the workspace/session-ownership design (with
options compared, a recommendation given, and a decision-mode
classification), the upload/storage flow, API contract, response-size
discipline, error taxonomy, COMTRADE `.cfg`/`.dat` multi-file upload design,
source-identity scheme, record-aliasing-avoidance approach, full-resolution
data ownership, persistence-boundary scoping, a preserve-vs-improve pass over
every discovered weakness, the Phase 1 vs. Phase 1.5 scope split, frontend
first-slice design, testing strategy and numerical-equivalence definition,
multi-user-readiness-without-premature-auth reasoning, a decision-mode
review of all nine discovery open questions, a dedicated "Candidate
Decisions Requiring Future UAT" section, the exact first-implementation
scope (included/excluded/acceptance criteria), implementation order, and a
rollback strategy.

Also added, as new project-memory governance (not migration-specific):
a **decision-mode framework** (`ANALYSIS` / `COMPARISON` / `UAT` / `DEFER`)
and UAT/prototype governance in
[README.md — Decision modes](README.md#decision-modes), with short pointers
added to [CLAUDE.md](../../CLAUDE.md) and [AGENTS.md](../../AGENTS.md) so
future sessions know not every `[OPEN]` item needs an immediate decision.

Also recorded six new decisions in [DECISIONS.md](DECISIONS.md) (DEC-006
through DEC-011) — these were **explicitly stated as already-approved
project direction** by the task that requested this Phase 0 work (backend
authority over engineering data, frontend's presentation-only role,
original-file immutability, full-resolution-calculation integrity,
preference for reusing `powerwave`'s Qt-free logic, and incremental
vertical-slice migration) — not proposals invented during this task. No
*other* new `[DECISION]` entries were added: every Phase-0-specific design
choice (module structure, API shape, workspace-ownership mechanism, etc.)
stayed `[PROPOSAL]`, per the explicit instruction not to convert
recommendations into approved decisions.

## What was verified

- Every module named in [MIGRATION_PLAN.md](MIGRATION_PLAN.md)'s reuse
  mapping was **re-read directly from `powerwave` at commit `3156392`**
  during this task (not assumed from the discovery document or from
  directory/file names) — `app/models/{disturbance_record,channels,metadata,timing}.py`,
  `app/providers/base/{base_provider,provider_manager,provider_registry,exceptions}.py`,
  `app/providers/comtrade/comtrade_provider.py` (including its
  `_find_dat_file()` companion-file resolution — a load-bearing detail for
  the upload design), `app/providers/{csv,excel}/*.py`, and
  `app/import_wizard/{import_pipeline,normalized_dataset,disturbance_record_bridge}.py`.
  Current test files for each were confirmed present with real line counts,
  not assumed.
- Both repositories' Git/GitHub state was re-checked at the start of this
  task (see "Git/GitHub sync" below) — both were already current, no
  fast-forward was needed this time.
- `oruxa_powerwave`'s current backend module layout was re-confirmed (still
  flat `backend/app/{__init__,config,main,storage}.py`, no subpackages) —
  used directly to ground the proposed target module map rather than
  guessing at what already exists.
- No production application code was changed — only documentation
  (`docs/project-memory/**`) and the two governance files
  (`CLAUDE.md`, `AGENTS.md`).

## Git/GitHub sync (established method, reconfirmed working this session)

Both repositories were re-verified current with GitHub at the start of this
task — no drift, no fast-forward needed:

- **`oruxa_powerwave`**: `origin`'s configured SSH URL
  (`git@github.com:myza81/oruxa-powerwave.git`) is still not authenticated
  in these sandboxed sessions. The established, repeatable workaround:
  push to the **explicit HTTPS URL**
  (`https://github.com/myza81/oruxa-powerwave.git`) as a one-off push
  target — never `git remote set-url`. Verify by fetching from that same
  explicit HTTPS URL into `FETCH_HEAD` and comparing SHAs — do not trust
  the local `origin/main` tracking ref, which stays stale.
- **`powerwave`**: `origin` is HTTPS
  (`https://github.com/myza81/powerwave.git`) and authenticates fine.
  Confirmed still at `3156392`, matching `origin/main`, at the start of
  this task.

## What files were changed this session

Created:
- None new this task — [MIGRATION_PLAN.md](MIGRATION_PLAN.md) already
  existed (as a high-level placeholder) and was rewritten in place.

Modified:
- `docs/project-memory/MIGRATION_PLAN.md` — full Phase 0 design (was
  high-level-only).
- `docs/project-memory/README.md` — added the "Decision modes" governance
  section.
- `docs/project-memory/DECISIONS.md` — added DEC-006 through DEC-011.
- `docs/project-memory/CURRENT_STATE.md` — reflects Phase 0 completion.
- `docs/project-memory/HANDOFF.md` — this file.
- `CLAUDE.md`, `AGENTS.md` — one short paragraph each pointing at the new
  decision-mode governance.

(Earlier sessions built the rest of `docs/project-memory/` and
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) — see Git history, not
repeated here per this document's own "don't become a diary" rule.)

## What remains unresolved

- `[OPEN]` The Phase 0 design itself is not yet approved. Most of it is
  marked `[DECISION MODE: ANALYSIS]` (ready for direct owner approval) in
  [MIGRATION_PLAN.md — Decision status summary](MIGRATION_PLAN.md#decision-status-summary),
  but nothing should be treated as approved until the owner actually says
  so.
- `[OPEN]` Two items need side-by-side comparison before a later phase (not
  blocking Phase 1): the persistence model (Phase 8) and the
  calculated-signal grammar (Phase 6).
- `[OPEN]` Three UAT candidates are proposed but **no prototypes were
  built** (explicitly out of scope for this task): COMTRADE `.cfg`/`.dat`
  pairing UX, error-message wording, and (far future) calculated-signal
  grammar expansion. See
  [MIGRATION_PLAN.md — Candidate Decisions Requiring Future UAT](MIGRATION_PLAN.md#candidate-decisions-requiring-future-uat).
- `[OPEN]` A small licensing/size check on copying sample fixtures from
  `powerwave/samples/` into `oruxa_powerwave`'s own test fixtures is needed
  before Phase 1 implementation starts (not blocking design approval).
- `[OPEN]` Whether Phase 1 includes CSV/Excel (via the direct, non-wizard
  providers) or ships COMTRADE-only is left as an explicit owner choice in
  [MIGRATION_PLAN.md § 16](MIGRATION_PLAN.md) — not decided by this task.

## What should be done next

The project owner should review [MIGRATION_PLAN.md](MIGRATION_PLAN.md),
especially the "Decision status summary" at the end, and:
1. approve (or redirect) the items marked ready for approval;
2. decide the CSV/Excel-in-Phase-1 question (§16);
3. explicitly authorize a first implementation task scoped exactly per
   [MIGRATION_PLAN.md — Exact first implementation scope](MIGRATION_PLAN.md#exact-first-implementation-scope).

No implementation should start before that authorization.

## What must not be assumed

- Do not assume any part of the Phase 0 design in
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md) is approved for implementation —
  it is design/planning output, not a `[DECISION]`, except for DEC-006
  through DEC-011 specifically (the backend/frontend responsibility
  principles), which the task itself stated as already-approved direction.
- Do not assume `powerwave` is still at `3156392` by the time you read
  this — it is actively developed. Re-verify against current `HEAD` before
  relying on specific line numbers for an actual implementation task (this
  Phase 0 design's line citations were accurate as of `3156392`,
  2026-08-14).
- Do not assume `oruxa_powerwave` must reproduce any specific `powerwave`
  behaviour — see [DECISIONS.md — DEC-001](DECISIONS.md#dec-001--migrate-and-evolve-powerwave-do-not-copy-paste-or-blindly-rewrite-it).
- Do not treat a UAT candidate's *recommendation-for-now* (e.g. shipping
  the simpler of two upload-UX options first) as a final decision — it's
  explicitly provisional pending the actual UAT.
- Do not trust a locally-cached `origin/main` ref for `oruxa_powerwave` as
  proof of sync state on a machine with the same SSH problem — see the
  Git/GitHub sync section above.

## Owner approval needed before proceeding?

- Not needed to *read* or *discuss* the Phase 0 design.
- **Yes**, before recording any further `[DECISION]` in
  [DECISIONS.md](DECISIONS.md), before treating any `[DECISION MODE:
  ANALYSIS]` item in [MIGRATION_PLAN.md](MIGRATION_PLAN.md) as approved,
  and before any implementation work begins — per the change-governance
  rule in [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md).
