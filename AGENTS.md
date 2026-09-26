# Working in this repository

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
decisions. It is not summarised here and must not be copied into this file —
read it at the source. Where it is silent, ask rather than inferring
architecture from the code.

Its recurring test for any decision: *if this component moves to another server
tomorrow, what needs to change?* The answer should be configuration, DNS,
credentials and network settings — not business logic.

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

## Per-Unit measurement model — mandatory before any Per-Unit work

**Read [docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md](docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md)
before making any change related to Per-Unit, Voltage Base, Current
Base, measurement grouping, voltage-reference detection, PU waveform
display, PU significant-value reporting, or calculated-channel PU
behaviour.** That document is authoritative for this feature area (see
[DECISIONS.md — DEC-050](docs/project-memory/DECISIONS.md#dec-050--per-unit-measurement-model-is-clarified-to-be-measurement-group-aware-the-currently-deployed-source-bound-model-dec-049-is-not-the-final-target)) —
it is not summarised here and must not be copied into this file.

If code, tests, or older DEC-049 material conflict with that document,
do not silently choose one — report the conflict and obtain owner
approval before implementation. Existing behaviour is not automatically
correct merely because it is already implemented or already covered by
passing tests.

## Change governance

Fix what was asked for. Before modifying an existing function, workflow,
architecture or behaviour that appears incorrect or suboptimal — and before
acting on any architectural, behavioural, security, deployment or
data-integrity issue found outside the agreed scope — **stop and report**:

1. Issue
2. Evidence
3. Proposed solution
4. Benefits
5. Risks
6. Expected impact

Then obtain approval before implementing. Do not perform unrelated cleanup or
refactoring along the way.

## Frontend convention — electrical notation

A **mandatory** UI rule for all frontend work, existing and new
([DECISIONS.md — DEC-117](docs/project-memory/DECISIONS.md#dec-117--line-to-line-voltage-electrical-notation-is-a-standing-frontend-convention-subscript-notation-in-the-ui-via-one-shared-formatter-plain-vab-internally),
including Amendment 2):

```text
Use true visual subscripts where supported:
  V<sub>A</sub> V<sub>B</sub> V<sub>C</sub>      phase voltage
  V<sub>AB</sub> V<sub>BC</sub> V<sub>CA</sub>   line-to-line voltage
  V<sub>1</sub> V<sub>2</sub> V<sub>0</sub>      sequence voltage
  I<sub>1</sub> I<sub>2</sub> I<sub>0</sub>      sequence current
If rich subscript is not supported, use plain concatenated notation:
  VA, VAB, V1, I2
Never use literal underscore notation (V_A, V_AB, V_1, I_2) anywhere
user-facing, including fallbacks, accessibility text, logs and tests.

electrical quantity symbol           -> formatted
source/channel name (SLKS VB, KPDN1_VR) -> untouched
editable/custom name (KPDN1 VAB)     -> untouched
phase classification (Phase = A)     -> untouched
internal/API value (Va, VAB, phase_member = AB) -> untouched
```

1. Any new UI that displays a system-owned electrical symbol must use the
   shared formatter in `frontend/index.html` from the start. Never build
   notation locally.
   - Core: `wwElectricalSymbolHtml(quantity, subscript)`,
     `wwElectricalSymbolPlotly()`, `wwElectricalSymbolSvg()` (lowered
     `<tspan>`) and `wwElectricalSymbolText()` (the only plain fallback).
     `quantity` is `V|I`; `subscript` is `A|B|C|AB|BC|CA|1|2|0` for `V`
     and `1|2|0` for `I`.
   - Semantic wrappers: `wwVoltageSymbol*(subscript)`,
     `wwRoleLabelHtml/Plotly/Svg/Text(roleKey)` (for `Va..Vc`,
     `V1/V2/V0`, `I1/I2/I0`), `wwLineToLinePairHtml()`,
     `wwLineToLineFormulaHtml/Text()`, `wwCalculatedChannelName*()` and
     `wwChannelDisplayName*()`.
   - If a new kind of symbol is needed, extend this layer. Do not create
     a page-specific formatter.
2. CSS: only `.ww-electrical-symbol` (the atomic wrapper) and
   `.ww-electrical-sub`. No component-specific `<sub>` rules.
   - Static markup that cannot call the helper must emit the exact shape
     `<span class="ww-electrical-symbol">V<sub class="ww-electrical-sub">A</sub></span>`.
   - Inside a flex container, wrap any text mixed with symbols
     (V<sub>2</sub> / V<sub>1</sub>) in one inline span.
3. Where rich text cannot render (native `<option>` text, `title` and
   `aria-label` attributes, `textContent` pipelines, backend-supplied
   messages), use `wwElectricalSymbolText()` or plain concatenated text,
   and note why in a code comment. Do not build a custom workaround.
4. Never change internal identifiers, API values, domain values, stored
   names or selectors for presentation. Plotly trace identity lives in
   `meta`/`uid`, never in the display name.
5. Drive formatting from semantic metadata (`phase_member`, member,
   role keys, `voltage_representation`), never by parsing names or
   running regexes over free text. A channel name gets notation only
   when metadata proves it is the system-generated default. Formulas use
   the formatter for **every** symbol and every system-generated input
   name, never a mix of rich and plain.
6. Never put rich notation inside editable fields. Do not introduce
   `contenteditable` or rich-text inputs for this.
7. Out of scope, so do not convert:
   - phase currents (`Ia/Ib/Ic`), an owner decision;
   - impedance/fault-loop labels (`Za`, `Zab`, "Fault loop AB");
   - protection-role names;
   - descriptive words such as "Positive Sequence".
8. Verify visually, not just in the DOM. A new surface showing symbols
   needs a browser assertion with
   `expectTrueSubscripts()` (`browser-tests/support/electrical_notation_helpers.js`),
   which measures rendered glyphs. `backend/tests/test_frontend_electrical_notation.py`
   guards the formatter shape, bypasses and underscore forms.

## Ground rules

- **GitHub is the single source of truth.** Never fix an environment by editing
  files on a host. A VPS checkout is a deployment artefact, not a workspace.
- **PROD deployment is manual, always.** Do not deploy to production unless
  explicitly asked, and never by any automated trigger. DEV deploys itself
  automatically after CI succeeds on `main` ([DEC-036](docs/project-memory/DECISIONS.md#dec-036--dev-deployment-is-automatic-after-ci-succeeds-on-main-prod-remains-fully-manual))
  — the manual `workflow_dispatch` deploy workflow remains available as a
  DEV fallback and is the only way to reach PROD.
- **Configuration lives in one place.** Only [backend/app/config.py](backend/app/config.py)
  reads the environment; everything else receives a frozen `Settings`. Do not
  add `os.environ` reads elsewhere, and do not perform I/O at import time.
- **Compose stays portable.** [compose.yaml](compose.yaml) must run unchanged on
  Windows, macOS and Linux — no host paths, no UID/GID, no external networks, no
  provider-specific assumptions. Host-specific detail belongs in
  [compose.prod.yaml](compose.prod.yaml), read from the environment.
- **Four environments must keep working:** Windows laptop (no Docker, no SSH),
  Mac (optional Docker, SSH), VPS DEV, VPS PROD. See [README.md](README.md).
  Changes that only work with Docker, or only on a Mac, are not acceptable.
- **Dependencies are pinned exactly** in [backend/requirements.txt](backend/requirements.txt)
  and [backend/requirements-dev.txt](backend/requirements-dev.txt).

## Storage invariants

Two rules in [backend/app/storage.py](backend/app/storage.py) are load-bearing;
neither may be relaxed without an explicit decision:

1. Caller-supplied filenames can never escape the storage root.
2. Files in the `original` category are write-once.

## Tests

```bash
cd backend
pytest
```

The suite must pass before deployment; CI enforces this. Add tests alongside
behaviour changes — the storage and configuration layers in particular are
covered thoroughly and should stay that way.

## Current milestone

Milestone 1 is foundational hardening only. Not yet in scope: PostgreSQL schemas
and migrations, authentication, object storage, and Powerwave engineering/domain
features.
