# CLAUDE.md

Read [AGENTS.md](AGENTS.md). It holds the working rules for this repository and
applies in full here.

## Project memory — mandatory before any task

**GitHub is the canonical source of truth for this project — not a local
clone, and not agent conversation memory.** Local repositories on Windows or
macOS are working copies only.

Before responding to or acting on any task concerning `oruxa_powerwave`:

1. Locate the current repository.
2. Check `git status`, the current branch, and `git remote -v`.
3. Run `git fetch origin` (read-only) and determine whether the local branch
   is current with `origin`. If there are uncommitted local changes, do
   **not** automatically reset, stash, discard, clean, force-checkout, or
   rebase to "catch up" — preserve them and report the condition instead.
4. Read [docs/project-memory/README.md](docs/project-memory/README.md).
5. Read every document that `README.md` marks as mandatory reading.
6. Read the relevant architecture/design documentation it points to.
7. Inspect current code, Git state, configuration, or tests where required.
8. Only then analyse, recommend, or implement.

If a task requires inspecting or comparing against the existing desktop
`powerwave` application, additionally follow the `powerwave`-specific startup
rule in [docs/project-memory/README.md](docs/project-memory/README.md) —
`powerwave` and `oruxa_powerwave` are two distinct GitHub repositories; never
conflate them or treat one as a remote for the other.

This applies even when the requested task looks simple. Chat/session memory
and local-only notes are not the authoritative project record — GitHub,
carrying the documents in `docs/project-memory/` alongside the code itself,
is. This keeps work consistent across machines (Windows laptop, Mac mini) and
across agents (Claude, Codex) that share no memory of each other's sessions.

Not every unresolved question needs an immediate decision — see
[Decision modes](docs/project-memory/README.md#decision-modes) for how to
classify an open issue as ready for analysis-based approval, needing
side-by-side comparison, needing hands-on UAT, or simply deferred until a
later phase.

## Authoritative architecture reference

**Read [docs/architecture/oruxa-architecture.md](docs/architecture/oruxa-architecture.md)
before making any change that touches architecture, infrastructure, deployment,
storage, database, API boundaries or portability.**

That document is authoritative for Oruxa and Powerwave infrastructure
decisions. Do not reproduce its contents here — read it at the source, and ask
rather than inferring architecture from the code where it is silent.

## Product/engineering reference framework — the Detego Benchmark Principle

**Read [docs/project-memory/PRODUCT_REFERENCES.md](docs/project-memory/PRODUCT_REFERENCES.md)
before making a major feature-design decision** (Phase 2B/2C waveform-workspace
design in particular). That document quotes the owner-supplied "Detego
Benchmark Principle" verbatim (DEC-020) — summarized here, not duplicated.

`detego.app` is an official product, UI/UX, waveform-workspace, dashboard,
and workflow benchmark for `oruxa_powerwave`. **It is NOT the target
ceiling and NOT a specification to copy blindly.**

Required hierarchy, in order of authority, for major feature design:

1. **Existing `powerwave`** — proven engineering behaviour / reusable
   engineering logic.
2. **`detego.app`** — benchmark for product quality, workflow, UI/UX and
   interaction ideas.
3. **Owner requirements / approved decisions / UAT** — final authority.

The design goal is for `oruxa_powerwave` to become more capable and more
useful to engineers than Detego where justified. **If Detego lacks a
capability required by the owner, do not omit or weaken that capability
merely to stay consistent with Detego.** If Detego's workflow is good,
learn from the public behaviour and implement an independent Oruxa
design.

For major features, ask: *"What does Detego do here, what does existing
powerwave do, and what would make oruxa_powerwave better for the
engineer?"*

This project's own architecture ([docs/architecture/oruxa-architecture.md](docs/architecture/oruxa-architecture.md))
stays authoritative regardless of Detego's technical choices, and any
Detego-inspired UI must be an independent Oruxa implementation — never
reverse-engineered or copied from Detego's own code/assets.

Do not reproduce PRODUCT_REFERENCES.md's contents here — read it at the
source.

## Change governance

Before modifying an existing function, workflow, architecture or behaviour that
appears incorrect or suboptimal, report:

1. Issue
2. Evidence
3. Proposed solution
4. Benefits
5. Risks
6. Expected impact

and obtain approval before implementation.
