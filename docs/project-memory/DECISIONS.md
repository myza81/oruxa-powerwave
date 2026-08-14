# Decisions

This is the durable decision log for `oruxa_powerwave`. It answers:

> **What have we explicitly decided, and why?**

Only record an entry here as `Status: Approved` if it is already explicitly
established by the project owner or by existing authoritative documentation
(e.g. [../architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md),
[AGENTS.md](../../AGENTS.md)). An agent's own recommendation is a
`[PROPOSAL]`, never a decision — see [README.md](README.md).

Entries below were seeded on 2026-08-14 from rules that were **already**
established in existing repository documentation before this log existed;
the "Date" field reflects when the rule was recorded here, not necessarily
when it was first decided (the underlying rule predates this log in every
case below — see each entry's Source line).

---

## DEC-001 — Migrate and evolve `powerwave`, do not copy-paste or blindly rewrite it

Date: recorded 2026-08-14 (established at the start of the `powerwave` →
`oruxa_powerwave` discovery effort)
Status: Approved
Source: framing given directly by the project owner for the discovery/migration task.

Decision:
`oruxa_powerwave` will retain many capabilities from `powerwave` where mature,
validated engineering logic already exists and is suitable for reuse. However,
workflows, UI/UX, state management, and architecture may intentionally
differ, and new functionality may be introduced. Existing `powerwave`
behaviour must **not** automatically be assumed to be the correct future
behaviour for `oruxa_powerwave`.

Reason:
`powerwave` contains mature, previously-validated engineering/domain logic
(parsers, calculations, signal processing) that would be wasteful to discard
and re-derive from scratch. At the same time, `powerwave` is a single-user
desktop application; its UI, workflow, and state-management design cannot be
assumed correct for a multi-user web backend without review.

Alternatives considered:
Not documented in source beyond this framing.

Impact:
Migration work must explicitly separate "what engineering logic is reusable"
from "what is desktop-specific presentation/workflow," per
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), rather than porting the
whole application 1:1.

---

## DEC-002 — GitHub is the single source of truth for code

Date: recorded 2026-08-14
Status: Approved
Source: [AGENTS.md](../../AGENTS.md) § Ground rules; [README.md](../../README.md) § "GitHub is the single source of truth".

Decision:
Every developer machine and every deployment environment takes its code from
GitHub. A VPS checkout is a deployment artefact, not a workspace — never fix
an environment by editing files on a host.

Reason:
Keeps every environment reproducible and traceable to a specific, known Git
commit.

Alternatives considered:
Not documented in source.

Impact:
Applies to this project-memory documentation too: it is only authoritative
once committed and pushed to GitHub, not while it exists only in an agent's
working copy or a chat session (see [README.md](README.md)).

---

## DEC-003 — Deployment is manual; DEV and PROD stay isolated; PROD gets the commit DEV tested

Date: recorded 2026-08-14
Status: Approved
Source: [AGENTS.md](../../AGENTS.md) § Ground rules; `.github/workflows/deploy.yml`;
[docs/development/development-workflow.md](../development/development-workflow.md).

Decision:
Merging to `main` does not deploy anywhere by itself; a person explicitly
triggers the deploy workflow per target (`dev`/`prod`). DEV and PROD must
remain isolated across containers, ports, database, storage, and
configuration. The preferred release path is to deploy the same Git commit
that was already tested in DEV to PROD.

Reason:
Prevents accidental production impact from a routine merge, and preserves
traceability between what was tested and what is actually released.

Alternatives considered:
Not documented in source.

Impact:
Any new domain feature — including future Powerwave engineering
functionality — must fit this deployment model. No auto-deploy-on-merge, and
no DEV-to-PROD data/config fallback, should be introduced without a separate
decision.

---

## DEC-004 — Configuration is centralized; no scattered `os.environ` reads

Date: recorded 2026-08-14
Status: Approved
Source: [AGENTS.md](../../AGENTS.md) § Ground rules; `backend/app/config.py`.

Decision:
Only `backend/app/config.py` reads the environment; every other module
receives a frozen `Settings` instance. No filesystem/network I/O happens at
import time.

Reason:
Keeps configuration testable and the full set of environment knobs
discoverable in one place; misconfiguration fails clearly at startup instead
of as a `KeyError` somewhere downstream.

Alternatives considered:
Not documented in source.

Impact:
Any new backend module — including future Powerwave domain code — must
receive configuration via `Settings`, not read environment variables
directly.

---

## DEC-005 — Storage invariants are load-bearing and must not be relaxed without an explicit decision

Date: recorded 2026-08-14
Status: Approved
Source: [AGENTS.md](../../AGENTS.md) § Storage invariants; `backend/app/storage.py`.

Decision:
Two rules govern storage: (1) a caller-supplied filename can never escape the
storage root, and (2) files in the `original` category are write-once.

Reason:
Explicitly called load-bearing in existing documentation — these protect the
integrity of as-received engineering input files.

Alternatives considered:
Not documented in source.

Impact:
Any future Powerwave file-import feature (COMTRADE/CSV/Excel originals) must
be built on top of these invariants, not around them.

---

## DEC-006 — Prefer reuse of proven Qt-independent `powerwave` engineering logic

Date: recorded 2026-08-14 (stated as established project direction at the
start of the Phase 0 migration design task)
Status: Approved
Source: framing given directly by the project owner for the Phase 0 task.

Decision:
`oruxa_powerwave` should prefer reuse of proven, Qt-independent `powerwave`
engineering/domain logic where appropriate, rather than rewriting mature
logic unnecessarily.

Reason:
`powerwave`'s domain/engineering core (parsers, timestamp handling, the
alignment engine, calculated signals, analytics) is already Qt-free,
substantially isolated, and validated by a large existing test suite — per
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), rewriting it would
discard real, working engineering value.

Alternatives considered:
Not documented in source beyond this framing.

Impact:
Migration planning (see [MIGRATION_PLAN.md](MIGRATION_PLAN.md)) should
default to porting/adapting existing `powerwave` modules and only
reimplement where discovery specifically identifies a reason to (desktop
coupling, an identified architectural risk, or a deliberate product change).

---

## DEC-007 — Backend authority over engineering data and calculations

Date: recorded 2026-08-14
Status: Approved
Source: framing given directly by the project owner for the Phase 0 task.

Decision:
The Python backend remains authoritative for: file parsing, original source
data, timestamp/timebase interpretation, engineering calculations,
synchronization, signal processing, and analysis.

Reason:
Keeps engineering correctness centralized in one well-tested, Python-native
layer rather than duplicated or reimplemented across client and server.

Alternatives considered:
Not documented in source.

Impact:
No engineering/domain logic should be pushed into the frontend merely for
implementation convenience — see DEC-008.

---

## DEC-008 — Frontend role is presentation, interaction, and visualisation

Date: recorded 2026-08-14
Status: Approved
Source: framing given directly by the project owner for the Phase 0 task.

Decision:
The frontend's role is presentation, interaction, visualisation, workspace
controls, and user selections. Mature engineering logic must not be moved
into JavaScript merely for convenience.

Reason:
Mirrors `powerwave`'s own (mostly successful) separation between Qt-free
engineering logic and its Qt UI layer — see
[POWERWAVE_DISCOVERY.md — GUI / Domain Logic Separation](POWERWAVE_DISCOVERY.md#gui--domain-logic-separation).

Alternatives considered:
Not documented in source.

Impact:
Frontend-side reimplementation of any parsing/calculation/synchronization
logic requires an explicit, separately-justified exception, not a default.

---

## DEC-009 — Original uploaded engineering files remain immutable

Date: recorded 2026-08-14
Status: Approved
Source: framing given directly by the project owner for the Phase 0 task;
consistent with the pre-existing storage invariant already recorded in
DEC-005.

Decision:
Original uploaded engineering files must remain immutable once accepted.

Reason:
Preserves traceability back to the as-received source and matches (and
strengthens beyond) `powerwave`'s own weaker guarantee — see
[POWERWAVE_DISCOVERY.md — Original Source Immutability](POWERWAVE_DISCOVERY.md#original-source-immutability),
which found `powerwave` never mutates originals in place but also does not
retain them for later re-audit the way `oruxa_powerwave`'s existing
write-once `original` storage category already can.

Alternatives considered:
Not documented in source.

Impact:
Any file-import feature must write originals through the existing
write-once `original` storage category (see DEC-005) and never provide an
in-place-edit or re-upload-over-existing-source path.

---

## DEC-010 — Engineering calculations operate on full-resolution backend data

Date: recorded 2026-08-14
Status: Approved
Source: framing given directly by the project owner for the Phase 0 task.

Decision:
Authoritative engineering calculations must operate on full-resolution
backend data. Future display downsampling/decimation must not silently
affect engineering calculations.

Reason:
Matches `powerwave`'s own architectural intent (analytics and calculated
signals already read full-resolution `DisturbanceRecord` data, independent
of what's currently decimated for on-screen display) — see
[POWERWAVE_DISCOVERY.md — Full-Resolution Engineering Data Principle](POWERWAVE_DISCOVERY.md#full-resolution-engineering-data-principle).

Alternatives considered:
Not documented in source.

Impact:
Any future viewport/decimation feature must be implemented as a separate
concern from calculation/analysis/synchronization code paths, not
interleaved with them.

---

## DEC-011 — Migration proceeds in small vertical slices

Date: recorded 2026-08-14
Status: Approved
Source: framing given directly by the project owner for the Phase 0 task.

Decision:
Migration proceeds in small vertical slices. `oruxa_powerwave` should not
attempt to recreate the complete desktop application in one implementation
task.

Reason:
Keeps each implementation step reviewable, testable, and reversible —
consistent with DEC-001's "migrate and evolve, don't blindly rewrite"
principle.

Alternatives considered:
Not documented in source.

Impact:
See [MIGRATION_PLAN.md](MIGRATION_PLAN.md) for the current phase sequencing
and the exact scope of the first approved-candidate slice.

---

## How to add a decision

1. Confirm it is actually approved — by the project owner directly, or
   already established in authoritative documentation — not merely proposed
   by an agent.
2. Add a new `## DEC-XXX — Title` section using the template above (Date,
   Status, Source if applicable, Decision, Reason, Alternatives considered,
   Impact).
3. Cross-reference it from [MIGRATION_PLAN.md](MIGRATION_PLAN.md) and/or
   [CURRENT_STATE.md](CURRENT_STATE.md) if it affects current direction, and
   update [HANDOFF.md](HANDOFF.md).
4. If a decision is later superseded, change its `Status` to `Superseded` and
   add a new entry — do not delete or silently rewrite the old one.
