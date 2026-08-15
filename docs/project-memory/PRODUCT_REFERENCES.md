# Product References — `oruxa_powerwave`

This document establishes the reference framework used when designing a
significant feature for `oruxa_powerwave`: what the feature should behave
like (engineering correctness), what it should feel like to use (UI/UX,
workflow, dashboard/product shape), and who has the final say when those
pull in different directions. It exists alongside, not instead of, the
other project-memory documents — see
[README.md — Discovery vs. design](README.md#discovery-vs-design) for how
this fits the rest of the framework.

## Authoritative statement — the Detego Benchmark Principle

`[DECISION]` (2026-08-15, owner-approved — see DEC-020 in
[DECISIONS.md](DECISIONS.md)). The wording below is the owner-supplied
canonical text ("Detego Benchmark Principle"), reproduced verbatim as the
authoritative statement of this decision — everything else in this
document is explanatory scaffolding around it, not a replacement for it.

> Detego.app is an official product, UI/UX, waveform-workspace, dashboard,
> and workflow benchmark for oruxa_powerwave.
>
> It is NOT the target ceiling and NOT a specification to copy blindly.
>
> When designing a feature, agents should compare:
>
> 1. existing powerwave
>    = proven engineering behaviour / reusable logic
>
> 2. detego.app
>    = benchmark for product quality, workflow, UI/UX and interaction ideas
>
> 3. owner requirements / approved decisions / UAT
>    = final authority
>
> The design goal is for oruxa_powerwave to become more capable and more
> useful to engineers than detego.app where justified.
>
> If detego.app lacks a capability required by the owner, do not omit or
> weaken that capability merely to stay consistent with Detego.
>
> If Detego's workflow is good, learn from the public behaviour and
> implement an independent Oruxa design.
>
> For major features, ask:
> "What does Detego do here, what does existing powerwave do, and what
> would make oruxa_powerwave better for the engineer?"

## The three references, in order of authority

### 1. Existing `powerwave` — proven engineering behaviour / reusable engineering logic

The existing desktop application. Read-only reference; see
[README.md's `powerwave`-specific startup rule](README.md#powerwave-specific-startup-rule)
before inspecting or comparing against it, and record findings in
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), not here.

Authoritative for **engineering correctness and domain behaviour worth
preserving** — parsing, timestamp handling, alignment math, analytics,
calculated signals, and (per the Phase 2 waveform design work) which
display-fidelity properties (e.g. peak preservation) actually matter for
disturbance analysis. **Not** authoritative for UI/UX, desktop-specific
presentation, or interaction design — see
[MIGRATION_PLAN.md's Phase 2 design section, §8](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)
for the "behaviour worth preserving vs. desktop implementation not to
reuse" distinction this already established.

### 2. `detego.app` — official product, UI/UX, waveform-workspace, dashboard, and workflow benchmark

`detego.app` is an **official product, UI/UX, waveform-workspace,
dashboard, and workflow benchmark** for `oruxa_powerwave` — a source of
product quality, workflow, and interaction ideas, to be consulted
**routinely** during Phase 2B/2C waveform and workspace design in
particular, and for other significant feature-design decisions generally.

**Detego is a benchmark, not a ceiling.** `oruxa_powerwave` should aim to
become **more capable and more useful to engineers than Detego** where
justified. **If Detego lacks a capability required by the owner, do not
omit or weaken that capability merely to stay consistent with Detego** —
engineering requirements and owner direction decide scope, not parity
with Detego.

Detego's own implementation **is not a specification to copy blindly**.
**If Detego's workflow is good, learn from the public behaviour and
implement an independent Oruxa design** — consult it for how it organizes
a waveform workspace, presents a dashboard, or sequences a workflow, never
as something `oruxa_powerwave` must match feature-for-feature or
pixel-for-pixel.

`[OPEN]` No specific technical audit of `detego.app`'s actual features,
architecture, or UI has been performed as part of this project-memory
record — this document establishes the **reference relationship**, not a
feature inventory or comparison matrix. Record concrete findings/
comparisons here (or in the relevant `MIGRATION_PLAN.md` design section)
as they are actually made during real feature-design work, not
speculatively in advance. Do not assume a future session has done this
audit just because this document exists.

### 3. Owner requirements / approved decisions / UAT — final authority

Regardless of what `powerwave` does or what Detego does, **the project
owner's stated requirements, the decisions already recorded in
[DECISIONS.md](DECISIONS.md), and actual UAT findings are final** — see
[README.md — How facts, decisions, and proposals are distinguished](README.md#how-facts-decisions-and-proposals-are-distinguished)
and [Decision modes](README.md#decision-modes) for how an open
feature-design question should be classified and resolved. Neither
`powerwave` nor Detego can override an explicit owner decision; both are
inputs to a recommendation, never a substitute for owner approval.

## How to use this during feature design

For a significant feature-design question (not an ordinary internal
engineering choice — see
[README.md's guidance on decision modes](README.md#decision-modes) for
that distinction), ask the question the Detego Benchmark Principle
itself specifies:

> "What does Detego do here, what does existing powerwave do, and what
> would make oruxa_powerwave better for the engineer?"

Present findings from all three references where relevant, using the
existing `[FACT]`/`[DECISION]`/`[PROPOSAL]`/`[OPEN]`/`[UAT]` labels — a
Detego comparison is evidence for a `[PROPOSAL]`, never itself a
`[DECISION]`.

## Repository/access note

`detego.app` is an external product, not a repository this project
controls or that lives in this codebase. Unlike `powerwave`, there is no
local clone or canonical Git remote for it recorded in this project's
[README.md — Repository identity](README.md#repository-identity--do-not-confuse-the-two-projects) —
it is a reference product, not a reference *repository*. Do not conflate
it with `powerwave` or treat it as a third canonical codebase.
