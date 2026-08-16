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

## Reference hierarchy

```text
1. existing powerwave
   = proven engineering behaviour, reusable engineering logic,
     and existing workflow reference

2. detego.app
   = official benchmark for product quality, UI/UX, waveform
     workspace, dashboard composition, layout, interaction design,
     process flow, and engineering-analysis workflow

3. owner requirements / approved decisions / UAT
   = FINAL authority for oruxa_powerwave
```

### 1. Existing `powerwave` — proven engineering behaviour, reusable engineering logic, and existing workflow reference

The existing desktop application. Read-only reference; see
[README.md's `powerwave`-specific startup rule](README.md#powerwave-specific-startup-rule)
before inspecting or comparing against it, and record findings in
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), not here.

**Detego does not replace `powerwave` as the engineering reference.**
`powerwave` remains the authority for:

- verified engineering behaviour;
- parser/provider logic;
- signal calculations;
- timing semantics;
- source handling;
- multi-source concepts;
- existing calculations (analytics, alignment, calculated signals);
- reusable Qt-free domain logic.

**Not** authoritative for UI/UX, desktop-specific presentation, or
interaction design — see
[MIGRATION_PLAN.md's Phase 2 design section, §8](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)
for the "behaviour worth preserving vs. desktop implementation not to
reuse" distinction this already established.

**Where `powerwave` behaviour is technically weak or flawed, improve it
rather than copy it.** The intended philosophy: *reference existing
behaviour → identify weakness → improve it.* This is already demonstrated
in this codebase, not just a stated intention: `powerwave`'s own
desktop waveform-display reduction is plain nth-point stride sampling,
which can hide a narrow transient peak entirely. Phase 2A deliberately
did **not** port that algorithm — it retains full-resolution authoritative
data and uses a peak-preserving min/max envelope for display instead (see
[MIGRATION_PLAN.md's Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15)
and DEC-019). Every future comparison against `powerwave` should apply the
same pattern: preserve what's proven, improve what's weak, don't
reproduce a flaw just because it's the existing behaviour.

### 2. `detego.app` — official product, UI/UX, waveform-workspace, dashboard, and workflow benchmark

`detego.app` is an **official benchmark for product quality, UI/UX,
waveform workspace, dashboard composition, layout, interaction design,
process flow, and engineering-analysis workflow** — to be consulted
**routinely** during Phase 2B/2C waveform and workspace design in
particular, and for other significant feature-design decisions generally.

**Detego is a benchmark, not a ceiling.** It is explicitly **not**:

- a specification to copy exactly;
- an architectural authority;
- a feature ceiling;
- a reason to reject functionality Detego does not have;
- a replacement for existing `powerwave` engineering logic;
- a substitute for owner requirements.

The goal is **not** "make `oruxa_powerwave` identical to Detego." The goal
is: study what Detego does well, combine that with existing `powerwave`'s
engineering strengths and the owner's specific requirements, and build an
**independent** `oruxa_powerwave` that can become more capable and more
useful to engineers than Detego. **If Detego lacks a capability required
by the owner, do not omit or weaken that capability merely to stay
consistent with Detego** — engineering requirements and owner direction
decide scope, not parity with Detego.

Useful Detego ideas may include (as inspiration, not obligation):

- clean and simple engineering UI;
- strong dashboard/layout composition;
- smooth workflow progression;
- waveform workspace organization;
- draggable/reorderable interaction concepts;
- flexible signal grouping;
- zoom/pan interaction quality;
- cursor UX;
- analog/digital/computed signal organization;
- analysis-view integration;
- overall perceived responsiveness and polish.

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

## Owner-specific capabilities may exceed Detego

`oruxa_powerwave`'s eventual requirements may include capabilities Detego
does not have, or does differently. Detego is **not the boundary of the
product**. Examples that may apply (this list is deliberately not
exhaustive — do not assume it is complete, and do not treat an idea's
absence from this list as a reason to reject it):

- richer multi-source disturbance comparison;
- COMTRADE + CSV + Excel in one engineering workspace;
- source-native sampling-rate preservation;
- exact/nearest timestamp alignment;
- transparent synchronization;
- calculated channels across files;
- reusable engineering calculations;
- user-arrangeable waveform layouts;
- specialized grid/protection analysis;
- future functions introduced by the owner.

## Architecture remains Oruxa-owned

Detego implementing something with a particular technical architecture is
**not** evidence that `oruxa_powerwave` should use the same architecture.
[docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md)
remains authoritative for `oruxa_powerwave`'s own technical principles —
read at the source, not summarised here — including (not an exhaustive
restatement, just the categories most likely to tempt a Detego-shaped
shortcut):

- frontend/backend separation;
- backend engineering authority (full-resolution data stays backend-owned
  — see DEC-019);
- portability;
- configuration-driven infrastructure;
- ephemeral event handling (DEC-015);
- API boundaries;
- source immutability;
- provider independence;
- no hidden assumptions.

Detego's UI may inspire `oruxa_powerwave` even when the two applications'
backend architectures are, and remain, different.

## Independent implementation, not reverse engineering

Do not reverse-engineer or copy Detego's proprietary implementation. Use
only:

- publicly observable behaviour;
- public documentation;
- legitimate feature references;
- independent engineering implementation.

The resulting `oruxa_powerwave` UI should be an **Oruxa design**, informed
by what Detego does well, never a pixel-for-pixel clone or a
reverse-engineered copy of Detego's actual code/assets.

## Feature-design method

For a significant feature-design question (not an ordinary internal
engineering choice — see
[README.md's guidance on decision modes](README.md#decision-modes) for
that distinction), compare across **four** points, the fourth being the
actual design output the first three inform:

```text
Powerwave                    : what proven engineering behaviour or
                                workflow already exists here, and is
                                any of it technically weak enough to
                                improve rather than preserve?
Detego                       : what does the benchmark do well here,
                                as inspiration -- not obligation?
Owner requirements            : what has the owner actually asked for,
                                or what does approved DECISIONS.md /
                                UAT evidence already say?
Proposed superior Oruxa      : given the above three, what independent
approach                       oruxa_powerwave design would be more
                                capable/useful for the engineer than
                                simply matching either reference?
```

This is the same question the Detego Benchmark Principle itself poses —
*"What does Detego do here, what does existing powerwave do, and what
would make oruxa_powerwave better for the engineer?"* — expressed as an
explicit four-column comparison so a design write-up captures all four
answers, not just the first three. Present findings using the existing
`[FACT]`/`[DECISION]`/`[PROPOSAL]`/`[OPEN]`/`[UAT]` labels — a Detego (or
`powerwave`) comparison is evidence for a `[PROPOSAL]`, never itself a
`[DECISION]`.

## Examples

These are illustrative applications of the method above, not decisions —
none of the following approves a specific Phase 2B/2C design; each would
still need its own `[PROPOSAL]`/`[DECISION MODE: ...]` treatment when
actually designed.

**Waveform workspace** (Phase 2B/2C):
- study Detego's UX for panel/workspace organization, zoom/pan feel, and
  signal grouping;
- inspect `powerwave`'s engineering behaviour for what actually needs
  preserving (multi-rate timing, per-channel native time arrays, cursor
  measurement semantics);
- preserve Oruxa's already-decided full-resolution fidelity principle
  (DEC-019) regardless of what either reference does for display;
- design an independent, potentially superior workspace — informed by
  both, dictated by neither.

**Application shell** (Phase 3A, 2026-08-16) — this one is no longer
illustrative; it is now a real, owner-approved decision
([DECISIONS.md DEC-031](DECISIONS.md#dec-031--application-shell-architecture-global-header-full-height-main-sidebar-menu-work-area-workspace-row--bottom-status-bar-phase-3a)),
recorded here because it applied this exact four-column method: Detego
named explicitly as the UI/UX/layout benchmark for the overall
Global-Header/Main-Sidebar-Menu/Workspace-Sidebar/Main-Workspace/
Status-Bar arrangement (never its branding, colors, typography, or
implementation); `powerwave`'s own engineering behaviour was not
directly relevant to this specific decision (a shell/navigation
question, not a signal-processing one); the owner's own corrected shell
geometry (Main Sidebar Menu spans the full Body height, the Status Bar
never runs beneath it) was final authority over any benchmark
inspiration; and the resulting Oruxa design is an independent
implementation, informed by the benchmark, dictated by neither
reference. This does not supersede the "Waveform workspace" example
above, which still governs the internal panel/zoom/grouping design
living inside the shell's own Main Workspace region.

**Recordings page** (Phase 3B, 2026-08-16) — also no longer illustrative;
a real, owner-approved decision
([DECISIONS.md DEC-032](DECISIONS.md#dec-032--recordings-page-as-a-first-class-application-page-one-recording--one-logical-event-cfgdat-sessionworkspace-backed-not-a-persistent-cloud-library-phase-3b)),
recorded here because it applied the same four-column method a second
time: the owner supplied a screenshot of Detego's own Recordings page,
named explicitly as the layout/workflow benchmark for the overall
page shape (a compact table with a prominent-but-compact "Upload New"
action, real columns, no card-heavy dashboard feel — never its
branding, colors, icons, or exact column set); `powerwave`'s own
engineering behaviour was not directly relevant here either (a page/
navigation and upload-workflow question, not a signal-processing one);
owner requirements were final authority over the benchmark in the two
places they diverged — the written instruction to PREFER the real
station/event name over the filename for the Recording column's display
name (opposite of what Detego's own screenshot shows, which uses the
filename as primary), and the explicit, repeated instruction not to
imply a persistent cloud recording library, which Detego's own
"Recordings" framing could otherwise suggest; and the resulting design
(a session/workspace-backed list, a single extensible upload modal, a
`recording = one CFG+DAT pair` abstraction general enough for future
CSV/Excel formats) is an independent Oruxa implementation, informed by
the benchmark, dictated by neither reference.

**Multi-source synchronization** (Phase 3+, not yet scoped):
- Detego may offer useful workflow inspiration for how synchronized
  sources are presented;
- do not automatically adopt a resampling approach just because Detego
  (or `powerwave`) might use one — see
  [MIGRATION_PLAN.md's Phase 2 design §21/§28](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)'s
  "avoid hidden resampling" principle, which already governs this;
- preserve Oruxa's own source-integrity and timing requirements over
  either reference's convenience.

**Calculated signals** (Phase 6, not yet scoped):
- use any good Detego UX ideas for how a calculated signal is defined/
  displayed;
- preserve/extend `powerwave`'s existing expression-engine engineering
  capability (see
  [POWERWAVE_DISCOVERY.md — Reuse Candidates](POWERWAVE_DISCOVERY.md#reuse-candidates));
- owner requirements may call for capability beyond what either reference
  provides (e.g. an expanded expression grammar — already flagged as an
  open discovery question).

## Repository/access note

`detego.app` is an external product, not a repository this project
controls or that lives in this codebase. Unlike `powerwave`, there is no
local clone or canonical Git remote for it recorded in this project's
[README.md — Repository identity](README.md#repository-identity--do-not-confuse-the-two-projects) —
it is a reference product, not a reference *repository*. Do not conflate
it with `powerwave` or treat it as a third canonical codebase.
