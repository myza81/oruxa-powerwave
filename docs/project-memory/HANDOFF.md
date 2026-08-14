# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-14**

## ✓ Push resolved (2026-08-14, follow-up session)

The `origin` remote's configured SSH URL (`git@github.com:myza81/oruxa-powerwave.git`)
is still not authenticated in these sandboxed sessions (`Permission denied
(publickey)`, confirmed again on retry). However, a credential helper made
**HTTPS write access work** without touching `origin`'s config: pushing
directly to the explicit URL `https://github.com/myza81/oruxa-powerwave.git`
(as a one-off push target, not by running `git remote set-url`) succeeded as
a normal fast-forward push, `7f57c16..b04d7ab`. This was independently
verified by fetching `main` from that same HTTPS URL into `FETCH_HEAD` (not
by trusting the local `origin/main` tracking ref, which stays stale since
`git fetch origin` over SSH still fails) — GitHub's actual `main` branch
contains `b04d7ab` and all six `docs/project-memory/` files plus the updated
`CLAUDE.md`/`AGENTS.md`.

**Caveat for the next session**: the local `origin/main` remote-tracking ref
will read stale (`7f57c16`) until a `git fetch` actually succeeds — don't
trust `git status -sb`/`origin/main` alone to judge sync state on a machine
with the same SSH problem. Prefer `git ls-remote` or `git fetch <https-url>`
against the explicit HTTPS URL to check real GitHub state, same as done here.
If a future machine has a working SSH key instead, `git fetch origin` will
work normally and this caveat won't apply there.

## What was most recently done

Created the shared living project-memory framework in
`docs/project-memory/`: this file, [README.md](README.md),
[CURRENT_STATE.md](CURRENT_STATE.md),
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) (skeleton only),
[MIGRATION_PLAN.md](MIGRATION_PLAN.md) (high level only), and
[DECISIONS.md](DECISIONS.md) (seeded with rules already established in
existing repo documentation). Also updated [CLAUDE.md](../../CLAUDE.md) and
[AGENTS.md](../../AGENTS.md) to require reading this framework's
`README.md` before acting on any `oruxa_powerwave` task.

## What was verified

- Existing repository documentation was read before writing anything new:
  [CLAUDE.md](../../CLAUDE.md), [AGENTS.md](../../AGENTS.md),
  [docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md),
  [docs/development/development-workflow.md](../development/development-workflow.md).
  No competing/duplicate documentation was found for what this framework
  provides, so nothing existing was replaced.
- Current `oruxa_powerwave` backend/frontend/CI/deploy state was inspected
  directly (not assumed) and is reflected in
  [CURRENT_STATE.md](CURRENT_STATE.md).
- No production application code was changed in this task — only
  documentation (`docs/project-memory/**`) and governance files
  (`CLAUDE.md`, `AGENTS.md`).

## What files were changed

Created:
- `docs/project-memory/README.md`
- `docs/project-memory/CURRENT_STATE.md`
- `docs/project-memory/POWERWAVE_DISCOVERY.md`
- `docs/project-memory/MIGRATION_PLAN.md`
- `docs/project-memory/DECISIONS.md`
- `docs/project-memory/HANDOFF.md` (this file)

Modified:
- `CLAUDE.md` — added mandatory project-memory startup reading rule.
- `AGENTS.md` — added the equivalent rule, aligned wording.

## What remains unresolved

- `[OPEN]` **The `powerwave` → `oruxa_powerwave` discovery audit itself is
  not complete and is not yet reflected in
  [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md).** A first discovery pass
  was started earlier in the same session that built this framework (before
  this framework-setup task was requested): five of seven planned subsystem
  investigations completed with detailed, citation-backed findings (data
  model & session state, synchronization architecture, calculated signals,
  waveform visualization/rendering, analytics/measurement catalog), but two
  (file import pipeline; background processing, tests, and timestamp/timebase
  handling) **failed partway through because the account hit its monthly
  spend limit.** None of that work — completed or failed — has been written
  into this repository's documentation yet, by design: the task that created
  this framework explicitly said not to populate detailed `powerwave`
  findings during framework setup.
- `[OPEN]` Whether to resume the two failed investigations, redo the whole
  discovery pass fresh (recommended, so the final `POWERWAVE_DISCOVERY.md` is
  self-consistent and doesn't mix an old partial pass with a new one), or
  proceed with only the five completed areas plus a smaller follow-up for the
  remaining two, is a decision for whoever runs the next discovery session —
  it depends on available spend-limit headroom at that time.

## What should be done next

Per the instructions that created this framework: run the detailed
`powerwave` → `oruxa_powerwave` discovery audit and populate
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), one verified section at a
time, following the finding format already documented there. This was
deliberately **not** started as part of the framework-setup work.

## What must not be assumed

- Do not assume [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) is complete
  or even started — it is a skeleton only.
- Do not assume the five subsystem investigations mentioned above under
  "What remains unresolved" are captured anywhere in this repository — they
  exist only as prior in-session agent output and have not been transcribed,
  verified against the finding format, or committed. Treat that prior work as
  a possible starting point to re-derive from, not as an existing citable
  record.
- Do not assume any phase of [MIGRATION_PLAN.md](MIGRATION_PLAN.md) is
  approved — no phases have been proposed yet, on purpose.
- Do not assume `oruxa_powerwave` must reproduce any specific `powerwave`
  behaviour — see [DECISIONS.md — DEC-001](DECISIONS.md#dec-001--migrate-and-evolve-powerwave-do-not-copy-paste-or-blindly-rewrite-it).

## Owner approval needed before proceeding?

- Not for continuing the discovery audit itself (already the agreed next
  step).
- **Yes**, for any implementation work, any architecture/design decision
  beyond what's already recorded in [DECISIONS.md](DECISIONS.md), and for any
  change to existing behaviour that appears incorrect or suboptimal — per the
  change-governance rule in [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md)
  (Issue, Evidence, Proposed solution, Benefits, Risks, Expected impact,
  then wait for approval).
