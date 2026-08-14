# Project Memory — Read Me First

This directory is the **shared living project memory** for the migration from
`powerwave` (the existing desktop application) to `oruxa_powerwave` (this
repository, the new web application).

## Why this exists

This project is worked on from multiple machines (Windows laptop, Mac mini)
and multiple AI agents (Claude, Codex), often in separate sessions that share
no memory with each other. Without a durable, shared record, each new session
has to reconstruct context from scratch, and different sessions can silently
drift into conflicting assumptions about what has been found, decided, or
built.

> **GitHub is the canonical source of truth for this project — not a local
> clone, and not agent conversation memory.**

```text
GitHub repository
        ↓
canonical code
canonical documentation
canonical project memory
        ↓
local clones (Windows laptop, Mac mini)
        ↓
Claude / Codex working sessions
```

Local repositories are working copies only. Agent conversation history and
local-only notes are not authoritative project memory — a chat transcript,
or a file that only exists uncommitted on one machine, does not count as
project knowledge for the next session. Important project knowledge must be
**committed to GitHub** to become real.

## Repository identity — do not confuse the two projects

This project involves **two distinct GitHub repositories**. Never treat one
as a remote for the other, and never assume a local clone's remote without
checking.

- **`oruxa_powerwave`** (this repository, the new web application):
  `git@github.com:myza81/oruxa-powerwave.git` — verified via `git remote -v`
  on 2026-08-14.
- **`powerwave`** (the existing desktop application, reference only):
  `https://github.com/myza81/powerwave.git` — verified via `git remote -v`
  in the local macOS clone on 2026-08-14.

If a local `oruxa_powerwave` clone is ever found with no confirmed GitHub
remote, or a remote that doesn't match the URL above, do not invent one and
do not silently assume it should point at the `powerwave` repository —
report the discrepancy (`[OPEN]`) instead.

## Before relying on local project-memory documents

A local clone can be stale relative to GitHub, especially across machines.
Before treating the documents in this directory as current:

```bash
git status
git branch --show-current
git remote -v
git fetch origin   # read-only, safe
```

Then compare the local branch against `origin` (e.g. `git status -sb` after
fetching). If the local branch is behind, prefer a safe, fast-forward-only
update before relying on these documents for a non-trivial task. If there are
uncommitted local changes, **never** automatically reset, stash, discard,
clean, force-checkout, or rebase to resolve this — preserve the work and
report the condition instead. GitHub being canonical does not mean
potentially valuable uncommitted local work may be destroyed automatically.

## `powerwave`-specific startup rule

For any task that requires inspecting or comparing against the existing
desktop `powerwave` application:

1. Determine which local path exists on the current machine — do not assume
   the OS:
   - Windows: `D:\Programming\powerwave\`
   - macOS: `/Volumes/externalDrive/code-gym/powerwave/`
2. Confirm it is actually a Git repository and that its remote matches the
   canonical URL above (`git remote -v`).
3. Run `git fetch origin` (read-only) and determine whether the local clone
   is current with `origin/main` before relying on it.
4. Read the relevant existing `powerwave` code/tests directly — do not rely
   on remembered `powerwave` behaviour from a previous chat session.
5. Record verified findings in [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md),
   using the finding format defined there.

`powerwave` is a read-only reference for this project. Never modify it, and
never write new project memory, decisions, or migration planning into it —
that all belongs in this `oruxa_powerwave` repository.

## Naming convention (used everywhere in this project)

- **`powerwave`** — the existing desktop application. Reference
  implementation and source of engineering/domain knowledge. Located at
  `D:\Programming\powerwave\` on Windows or
  `/Volumes/externalDrive/code-gym/powerwave/` on macOS — detect which path
  exists on the current machine rather than assuming the OS.
- **`oruxa_powerwave`** — this repository, the new web application being
  built. This is where the shared project memory lives.

Never refer to both applications simply as "Powerwave" — always disambiguate.

## Mandatory reading order

Before acting on any non-trivial `oruxa_powerwave` task, read in this order:

1. This file.
2. [CURRENT_STATE.md](CURRENT_STATE.md) — where the project actually is right now.
3. [DECISIONS.md](DECISIONS.md) — what has already been approved; do not
   re-litigate or silently override these.
4. [HANDOFF.md](HANDOFF.md) — what the last session did and what comes next.
5. [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) — only when the task
   concerns `powerwave` behaviour or migration content.
6. [MIGRATION_PLAN.md](MIGRATION_PLAN.md) — only when the task concerns
   sequencing/phasing of migration work.
7. [../architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
   — the authoritative Oruxa/Powerwave infrastructure architecture. This
   document is not summarised here; read it at the source. It is referenced,
   not duplicated, by every document in this directory.

[CLAUDE.md](../../CLAUDE.md) and [AGENTS.md](../../AGENTS.md) both require this
reading sequence before any task, even one that looks simple.

## How facts, decisions, and proposals are distinguished

Every claim in these documents should be identifiable as one of:

- **`[FACT]`** — observed directly from code, a test, a running system,
  configuration, or existing authoritative documentation. Facts are things
  anyone can re-verify by looking at the same source.
- **`[DECISION]`** — an explicitly approved project direction. Only the
  project owner (or documentation the owner has already established, such as
  [../architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md))
  can create a decision. An agent's own recommendation is never a decision
  until approved.
- **`[PROPOSAL]`** — a suggested direction that has not yet been approved.
  Proposals are welcome, but must never be written as if they were already
  decided.
- **`[OPEN]`** — an unresolved question or item that needs investigation or
  an owner decision before work can proceed.

These labels do not need to prefix every sentence — use them where their
absence could cause a future reader to mistake a proposal for an approved
direction, or a discovery finding for a design requirement (see
[Discovery vs. design](#discovery-vs-design) below).

## Source-of-truth hierarchy

When sources disagree, prefer them in this order:

1. **Current source code and tests** — tells us what currently exists.
2. **Current runtime/configuration**, where relevant.
3. **Approved architectural/decision documentation** — tells us what the
   project owner intends the future to be.
4. **Living project-memory documentation** (this directory).
5. **The current user instruction** in the active session.
6. **Agent chat/session memory** — least durable, never authoritative on its
   own.

Note the distinction in levels 1 and 3: code tells us what *currently
exists*; an approved decision tells us what the architecture is *intended to
become*. If current code conflicts with an approved future decision, neither
one is automatically "wrong" — report the discrepancy accurately rather than
resolving it by assumption.

## Discovery vs. design

This distinction is mandatory and must not be collapsed:

| Document | Answers |
|---|---|
| [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) | What the existing `powerwave` actually does. |
| [DECISIONS.md](DECISIONS.md) | What we have decided `oruxa_powerwave` should do. |
| [MIGRATION_PLAN.md](MIGRATION_PLAN.md) | How we currently intend to get there. |
| [CURRENT_STATE.md](CURRENT_STATE.md) | Where the project is now. |
| [HANDOFF.md](HANDOFF.md) | What the previous agent just did and what comes next. |

A discovery finding does **not** automatically become a design requirement.
Example:

```text
[FACT] powerwave stores X in memory.
```

does **not** imply:

```text
[DECISION] oruxa_powerwave must store X in memory.
```

The second only becomes true if the project owner (or already-approved
architecture) actually decides it.

## Conflict-resolution rules

**When a documented `[FACT]` no longer matches the current implementation:**

1. Verify the implementation carefully before concluding the document is stale.
2. Identify whether the code changed since the fact was recorded, or the
   original fact was simply wrong.
3. Update the project memory to match reality.
4. Note what was corrected and why (a short note in the updated document is
   enough — Git history carries the detailed trail).
5. Do not silently rewrite history — a correction is a visible edit, not a
   deletion of the record that something was once believed true.

**When an agent's own recommendation conflicts with an existing `[DECISION]`:**

1. Do **not** override the decision or act as though the recommendation is
   already approved.
2. Present, per the change-governance rule already established in
   [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md): Issue,
   Evidence, Proposed solution, Benefits, Risks, Expected impact.
3. Wait for owner approval before changing the established direction.

## `powerwave` is a reference system, not the memory location

```text
powerwave  →  reference implementation  →  technical discovery  →  engineering evidence

oruxa_powerwave  →  new application + shared project memory + architecture + migration plan + decisions
```

`powerwave` is read for evidence. It is never the place new project memory,
decisions, or migration planning get written.

## What agents may and may not do with this memory

Agents may: discover, analyse, recommend, implement work that has already
been approved, and document verified state.

Agents may **not**: silently convert their own proposals into approved
architecture, treat a `[PROPOSAL]` as a `[DECISION]`, or use this
documentation system as authority to make major project decisions
independently. This framework supports continuity between sessions and
machines — it does not grant autonomous decision authority.

## When these documents must be updated

Do not update documentation for trivial edits that don't change meaningful
project knowledge. Do update after:

| Kind of work | Update |
|---|---|
| Significant discovery about `powerwave` | [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), [HANDOFF.md](HANDOFF.md), possibly [CURRENT_STATE.md](CURRENT_STATE.md) |
| Approved architecture/design change | [DECISIONS.md](DECISIONS.md), [MIGRATION_PLAN.md](MIGRATION_PLAN.md), [CURRENT_STATE.md](CURRENT_STATE.md), [HANDOFF.md](HANDOFF.md) |
| Completed implementation phase | [CURRENT_STATE.md](CURRENT_STATE.md), [MIGRATION_PLAN.md](MIGRATION_PLAN.md), [HANDOFF.md](HANDOFF.md) |
| New unresolved architectural issue | An `[OPEN]` item in the relevant document |

## Cross-machine continuity

```text
Machine A → git pull → read project memory → do approved work →
update living docs → commit + push → GitHub →
Machine B → git pull → read the same project memory → continue consistently
```

Nothing in this directory should assume a specific machine or OS except where
explicitly documenting an environment difference (e.g. the two candidate
`powerwave` paths above).

## Change governance still applies

This directory does not change or relax the existing change-governance rule
in [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md): before
modifying existing behaviour that appears incorrect or suboptimal, or acting
on an issue outside the agreed scope, stop and report Issue / Evidence /
Proposed solution / Benefits / Risks / Expected impact, and get approval
before implementing.
