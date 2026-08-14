# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-14**

## What was most recently done

A **governance cleanup and approval-alignment pass** — no production code
was touched. Two things happened:

1. **Corrected a premature-decision issue.** DEC-006 through DEC-011 (added
   during the earlier Phase 0 design task) had cited "framing given
   directly by the project owner" as their source, but that framing was
   actually conditional/instructional phrasing, not a crisp unconditional
   approval — recording them as `Status: Approved` at that point was
   premature. Their *content* was reviewed and is now genuinely,
   explicitly approved by the project owner, so all six entries were
   **retained** (not deleted or reversed) with corrected `Date`/`Source`
   fields and a visible provenance-correction note explaining what changed
   and why, per this project's own conflict-resolution rule (correct in
   place, don't silently rewrite history).
2. **Recorded newly, explicitly approved decisions**: DEC-012 (Phase 1
   state must be scoped by `workspace_id`/`source_id`, never
   process-global), DEC-013 (lightweight JSON metadata sidecars are an
   acceptable *early-slice implementation mechanism* — paired with an
   explicit `[OPEN]` note that the long-term persistence architecture is
   **not** thereby decided), and DEC-014 (**Phase 1 is COMTRADE-only**;
   CSV/Excel and Import-Wizard-grade timestamp handling are deferred in
   full to Phase 1.5, planned but not yet implemented).

[MIGRATION_PLAN.md](MIGRATION_PLAN.md) was updated throughout to match:
the Phase status table, §16 (Import Wizard handling), the Included/Excluded
lists, the files-expected-to-change and implementation-order sections, and
the "Decision status summary" at the end all now correctly distinguish
**approved** (DEC-006–014) from **ready for approval but not yet recorded**
from **needs comparison** from **UAT** from **deferred** — most
importantly, the COMTRADE `.cfg`/`.dat` **backend transport mechanism**
(single multipart request) is reviewable-but-not-yet-a-`[DECISION]`, while
the **frontend pairing UX** remains explicitly open for UAT — these two are
easy to conflate and the document now keeps them visibly separate.
[CURRENT_STATE.md](CURRENT_STATE.md) was updated to reflect all of the
above.

## What was verified

- Repository state was re-checked at the start of this task — both
  `oruxa_powerwave` and (implicitly, via the documents already recording
  it) `powerwave` were confirmed current with GitHub before any edits.
- Every `[DECISION]` added or corrected in this task was checked against
  the exact wording of the task that requested this cleanup (which stated
  the newly-approved directions explicitly) — nothing here is an inferred
  or assumed approval.
- No production application code was changed — only documentation
  (`docs/project-memory/**`).

## Git/GitHub sync (established method, still the only way to push here)

- **`oruxa_powerwave`**: `origin`'s configured SSH URL
  (`git@github.com:myza81/oruxa-powerwave.git`) is not authenticated in
  these sandboxed sessions. Push to the **explicit HTTPS URL**
  (`https://github.com/myza81/oruxa-powerwave.git`) as a one-off push
  target — never `git remote set-url`. Verify by fetching from that same
  explicit HTTPS URL into `FETCH_HEAD` and comparing SHAs — the local
  `origin/main` tracking ref stays stale and should not be trusted alone.

## What files were changed this session

Modified:
- `docs/project-memory/DECISIONS.md` — corrected DEC-006–011 provenance;
  added DEC-012, DEC-013, DEC-014.
- `docs/project-memory/MIGRATION_PLAN.md` — Phase status table, §16, scope
  lists, and the "Decision status summary" all updated to match the
  corrected/newly-approved decisions.
- `docs/project-memory/CURRENT_STATE.md` — reflects governance cleanup and
  approved Phase 1 (COMTRADE-only) scope.
- `docs/project-memory/HANDOFF.md` — this file.

No files were created or deleted this task.

## What remains unresolved

- `[OPEN]` COMTRADE `.cfg`/`.dat` **browser pairing UX** — explicitly not
  decided, recommended for UAT (UAT-1 in
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md)). Does not block starting Phase 1
  implementation; only the exact frontend interaction is open.
- `[OPEN]` Long-term persistence architecture — DEC-013 approves JSON
  sidecars for the early slice only; the broader question (database vs.
  manifest vs. combination) is untouched and deferred to Phase 8.
- `[OPEN]` All engineering-improvement findings from discovery
  (discontinuity detection, raw timestamp traceability, timing-mode
  enforcement, duplicate classifiers, calculated-signal grammar,
  frequency/ROCOF computation, the suggestions feature) — unchanged by this
  task, deliberately kept separate from migration scope per the task's own
  instruction.
- `[OPEN]` The sample-fixture licensing/size check noted in
  [MIGRATION_PLAN.md § Testing strategy](MIGRATION_PLAN.md) — small,
  worth resolving before Phase 1 implementation starts.

## What should be done next

**Ready to prepare the Phase 1 COMTRADE-only implementation task.** Scope
is approved and documented in
[MIGRATION_PLAN.md — Exact first implementation scope](MIGRATION_PLAN.md#exact-first-implementation-scope):
domain model port, COMTRADE-only provider port, storage-backed service
layer (workspace/source-scoped, JSON sidecars), the four v1 API endpoints,
and a minimal frontend upload/channel-list view — CSV/Excel explicitly
excluded. The COMTRADE frontend pairing UX (UAT-1) can be resolved during
that task's frontend work, or the simpler of the two options can ship first
and be revisited, per [MIGRATION_PLAN.md § 17](MIGRATION_PLAN.md). No
implementation should begin without a separate, explicit go-ahead for that
task specifically — scope approval is not the same as an implementation
go-ahead.

## What must not be assumed

- Do not assume Phase 1's approved *scope* is the same as approval to
  *begin coding* — a separate go-ahead for the implementation task itself
  is still needed.
- Do not assume CSV/Excel are dropped — they are deferred to Phase 1.5,
  which is planned (scope defined in [MIGRATION_PLAN.md § 16](MIGRATION_PLAN.md))
  but not yet implemented or scheduled.
- Do not assume the COMTRADE pairing UX is decided — only the backend
  transport mechanism (single multipart request) is reviewable; the
  frontend interaction pattern is explicitly open for UAT.
- Do not assume DEC-013 settles the persistence question — it approves an
  early-slice mechanism only; the long-term architecture is untouched.
- Do not assume any engineering-improvement finding from discovery has
  changed status — none were touched by this task.
- Do not assume `powerwave` is still at the commit referenced throughout
  [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md)/[MIGRATION_PLAN.md](MIGRATION_PLAN.md)
  by the time you read this — it is actively developed; re-verify before an
  implementation task relies on specific line numbers.
- Do not trust a locally-cached `origin/main` ref for `oruxa_powerwave` as
  proof of sync state on a machine with the same SSH problem.

## Owner approval needed before proceeding?

- Not needed to *read* or *discuss* this governance cleanup.
- **Yes**, before any implementation work begins on Phase 1 — scope is
  approved, but the implementation task itself still needs an explicit
  go-ahead, per the change-governance rule in
  [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md).
