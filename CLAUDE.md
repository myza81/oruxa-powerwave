# CLAUDE.md

Read [AGENTS.md](AGENTS.md). It holds the working rules for this repository and
applies in full here.

**Decision preservation and engineering governance.** Before a substantive task,
consult the applicable approved decisions and specifications as set out in
[AGENTS.md — Decision preservation and engineering governance](AGENTS.md#decision-preservation-and-engineering-governance--mandatory)
([DEC-218](docs/project-memory/DECISIONS.md#dec-218--approved-decisions-are-binding-agents-consult-them-before-acting-and-preserve-them-agent-governance)).
Approved decisions are binding until the owner supersedes them; do not reopen a
settled policy. That section is the one authority for Claude Code and Codex and is
not restated here.

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

## Independent product direction

**Read [docs/project-memory/PRODUCT_REFERENCES.md](docs/project-memory/PRODUCT_REFERENCES.md)
before making a major feature-design decision.** It records the owner's
independent product direction and engineering requirements.

Oruxa-Powerwave is an independent engineering waveform analysis platform. Product development is guided by owner-defined engineering requirements, numerical correctness, usability, performance, maintainability and professional software architecture.

Use owner requirements, approved decisions and UAT to define feature scope.
Do not introduce external product comparisons or imitation/surpassing goals
into development guidance.
Validate engineering behaviour against independent numerical evidence and
established regression contracts. Existing `powerwave` code remains read-only
migration evidence under the startup rule above; it does not prescribe the
product's UI or feature scope.

For major features, identify the engineering task, required numerical and timing
semantics, interaction needs, performance constraints and acceptance evidence.
Retain the project's waveform, channel-management and usability requirements.
Design interfaces using Oruxa's own UI standards and shared theme tokens.

This project's [architecture](docs/architecture/oruxa-architecture.md) remains
authoritative. Product design does not override its portability, data ownership
or API boundaries.

## Per-Unit measurement model — mandatory before any Per-Unit work

**Read [docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md](docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md)
before making any change related to Per-Unit, Voltage Base, Current
Base, measurement grouping, voltage-reference detection, PU waveform
display, PU significant-value reporting, or calculated-channel PU
behaviour.** That document is authoritative for this feature area (see
[DECISIONS.md — DEC-050](docs/project-memory/DECISIONS.md#dec-050--per-unit-measurement-model-is-clarified-to-be-measurement-group-aware-the-currently-deployed-source-bound-model-dec-049-is-not-the-final-target)) —
do not reproduce its contents here.

If code, tests, or older DEC-049 material conflict with that document,
do not silently choose one — report the conflict and obtain owner
approval before implementation. Existing behaviour is not automatically
correct merely because it is already implemented or already covered by
passing tests.

## Frontend convention — electrical notation

**Mandatory.** Read the section of the same name in [AGENTS.md](AGENTS.md)
before adding or changing any UI that shows electrical symbols (phase,
line-to-line or sequence voltage/current) or formulas
([DECISIONS.md — DEC-117](docs/project-memory/DECISIONS.md#dec-117--line-to-line-voltage-electrical-notation-is-a-standing-frontend-convention-subscript-notation-in-the-ui-via-one-shared-formatter-plain-vab-internally),
Amendment 2).

- **Supported surfaces:** use true visual subscripts —
  V<sub>A</sub>, V<sub>AB</sub>, V<sub>1</sub>, I<sub>2</sub> — via the
  shared `wwElectricalSymbol*()` formatter and its two CSS rules.
- **Otherwise:** use plain concatenated notation (`VA`, `VAB`, `V1`,
  `I2`).
- **Never** use literal underscore notation.
- **These stay untouched:**
  - source/channel names;
  - editable and custom names;
  - phase classification;
  - internal/API values.
- **New UI** must use the formatter from the start and be verified
  visually with `expectTrueSubscripts()`.
- **Composed labels:** text mixed with symbols or formatted names goes
  through `wwRichLabelHtml()` so word spacing survives flex/grid
  layouts. Readable operation text uses a space before `(`
  (`RMS (channel, ...)`). See AGENTS.md rule 2.
- **Phase display convention**
  ([DEC-118](docs/project-memory/DECISIONS.md#dec-118--context-specific-engineering-notation-inherits-the-phase-display-convention-of-its-measurement-group--engineering-context-canonical-abc-stays-internal)):
  context-specific engineering notation inherits the phase display
  convention of its authoritative Measurement Group / Engineering Context.
  Canonical A/B/C identities remain internal. Generic UI wording remains
  fixed.
  - An R/Y/B bay shows V<sub>R</sub> and V<sub>RY</sub>, and its phase
    currents I<sub>R</sub>/I<sub>Y</sub>/I<sub>B</sub> (same map;
    canonical `Ia/Ib/Ic` stay internal; I<sub>1</sub>/I<sub>2</sub>/
    I<sub>0</sub> never follow a convention).
  - Never hard-code A/B/C into a context-specific result label.
  - Never detect a convention from names in a page.
  - Read AGENTS.md rule 9 before touching such labels.

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
