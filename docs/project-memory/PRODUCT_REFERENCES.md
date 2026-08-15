# Product References — `oruxa_powerwave`

This document establishes the reference framework used when designing a
significant feature for `oruxa_powerwave`: what the feature should behave
like (engineering correctness), what it should feel like to use (UI/UX,
workflow, dashboard/product shape), and who has the final say when those
pull in different directions. It exists alongside, not instead of, the
other project-memory documents — see
[README.md — Discovery vs. design](README.md#discovery-vs-design) for how
this fits the rest of the framework.

## The three references, in order of authority

### 1. `powerwave` — proven engineering behaviour, reusable logic

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

### 2. `detego.app` — UI/UX, workflow, dashboard, and product benchmark

`[DECISION]` (2026-08-15, owner-approved — see DEC-020 in
[DECISIONS.md](DECISIONS.md)): `detego.app` is adopted as a **UI/UX,
workflow, dashboard, and product benchmark** for `oruxa_powerwave` feature
design — to be consulted **routinely** during Phase 2B/2C waveform and
workspace design in particular, and for other significant feature-design
decisions generally.

`[DECISION]` **Detego is a benchmark, not a ceiling.** `oruxa_powerwave`
should aim to be **more capable and more useful than Detego** wherever the
owner's engineering requirements justify it. **Do not constrain a feature
merely because Detego does not have it.** A feature Detego lacks is not
evidence that `oruxa_powerwave` shouldn't build it — engineering
requirements and owner direction decide that, not parity with Detego.

`[DECISION]` Detego's own implementation **must not be blindly copied or
treated as an architecture requirement**. Consult it for inspiration and
comparison — how it organizes a waveform workspace, presents a dashboard,
sequences a workflow — never as a specification `oruxa_powerwave` must
match feature-for-feature or pixel-for-pixel.

`[OPEN]` No specific technical audit of `detego.app`'s actual features,
architecture, or UI has been performed as part of this project-memory
record — this document establishes the **reference relationship**, not a
feature inventory or comparison matrix. Record concrete findings/
comparisons here (or in the relevant `MIGRATION_PLAN.md` design section)
as they are actually made during real feature-design work, not
speculatively in advance. Do not assume a future session has done this
audit just because this document exists.

### 3. Owner requirements, approved decisions, and UAT — final authority

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
that distinction), frame it using all three references:

```text
powerwave:        what proven engineering behaviour must be preserved?
detego.app:       what does a strong UI/UX/workflow benchmark suggest,
                   as inspiration -- not obligation?
owner/DECISIONS/
UAT:              what has actually been approved or found, and does
                   it call for matching, exceeding, or diverging from
                   either reference?
```

Present findings from all three where relevant, using the existing
`[FACT]`/`[DECISION]`/`[PROPOSAL]`/`[OPEN]`/`[UAT]` labels — a Detego
comparison is evidence for a `[PROPOSAL]`, never itself a `[DECISION]`.

## Repository/access note

`detego.app` is an external product, not a repository this project
controls or that lives in this codebase. Unlike `powerwave`, there is no
local clone or canonical Git remote for it recorded in this project's
[README.md — Repository identity](README.md#repository-identity--do-not-confuse-the-two-projects) —
it is a reference product, not a reference *repository*. Do not conflate
it with `powerwave` or treat it as a third canonical codebase.
