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
Status: Approved — **narrowed by [DEC-036](#dec-036--dev-deployment-is-automatic-after-ci-succeeds-on-main-prod-remains-fully-manual)
(2026-08-19): DEV deployment is no longer required to be manually triggered.**
Everything else below (PROD is always manual; DEV/PROD isolation; PROD gets
the exact commit DEV tested) remains fully in force — see DEC-036 for the
precise, current DEV-automation rule.
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
decision. **(2026-08-19: the owner approved exactly this — see DEC-036 — for
DEV only; PROD remains governed by this decision unmodified.)**

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

## Provenance correction — DEC-006 through DEC-011 (2026-08-14)

DEC-006 through DEC-011 were originally entered during the Phase 0 design
task, citing "framing given directly by the project owner for the Phase 0
task" as their source. On review during a subsequent governance-cleanup
task, that framing was found to be **conditional/instructional phrasing**
("treat the following as established project direction *unless* current
project-memory documentation records otherwise") rather than a crisp,
unconditional owner approval — recording them as `Status: Approved` at that
point was premature per this project's own rule that an agent's
recommendation does not become a `[DECISION]` automatically.

The substance of all six was subsequently reviewed and **explicitly
approved by the project owner on 2026-08-14** (the same governance-cleanup
task). The six entries below are therefore **retained** (their content was
correct) with their `Date`/`Source` fields corrected to reflect when
genuine approval actually happened, rather than backdating it to the
original Phase 0 task. This note stays here as the visible correction —
see [README.md — Conflict-resolution rules](README.md#conflict-resolution-rules)
for why this is corrected in place rather than silently rewritten.

---

## DEC-006 — Prefer reuse of proven Qt-independent `powerwave` engineering logic

Date: recorded 2026-08-14; corrected 2026-08-14 (see provenance-correction
note above) — approval confirmed during governance cleanup, not the earlier
Phase 0 task
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14); originally proposed during the Phase 0 migration design task.

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

Date: recorded 2026-08-14; corrected 2026-08-14 — see provenance-correction
note above DEC-006
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14); originally proposed during the Phase 0 migration design task.

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

Date: recorded 2026-08-14; corrected 2026-08-14 — see provenance-correction
note above DEC-006
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14); originally proposed during the Phase 0 migration design task.

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

Date: recorded 2026-08-14; corrected 2026-08-14 — see provenance-correction
note above DEC-006
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14); originally proposed during the Phase 0 migration design task;
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
Any file-import feature must never mutate an accepted original in place or
provide a re-upload-over-existing-source path. **Superseded in part by
DEC-015** (2026-08-14): this entry's original Impact text said originals
must be written through `StorageBackend`'s write-once `original` category —
the owner has since decided Phase 1 does not persist event files through
`StorageBackend` (or anywhere) at all. Immutability here now means "never
mutated while it exists," not "must be written to persistent storage." If a
later phase does introduce persistent storage for event files, DEC-005's
write-once category is still the right mechanism and this decision's intent
still applies to it.

---

## DEC-010 — Engineering calculations operate on full-resolution backend data

Date: recorded 2026-08-14; corrected 2026-08-14 — see provenance-correction
note above DEC-006
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14); originally proposed during the Phase 0 migration design task.

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

Date: recorded 2026-08-14; corrected 2026-08-14 — see provenance-correction
note above DEC-006
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14); originally proposed during the Phase 0 migration design task.

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

## DEC-012 — Phase 1 state is scoped by workspace/source identity, never process-global

Date: 2026-08-14
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14).

Decision:
Phase 1 backend state must be scoped using concepts equivalent to
`workspace_id` and `source_id` — never held as process-global session/source
state. The exact long-term authentication/tenant model remains deferred
(see DEC-013's companion `[OPEN]` pattern and
[MIGRATION_PLAN.md § 20](MIGRATION_PLAN.md)).

Reason:
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) found `powerwave`'s own
session model has no concurrency control and no user/tenant concept
anywhere — ranked as a Critical multi-user risk. Scoping state now, even
without building authentication yet, avoids a future architectural rework
of the kind `powerwave` itself was forced into for source identity (see
[POWERWAVE_DISCOVERY.md — Session and State Management](POWERWAVE_DISCOVERY.md#session-and-state-management)).

Alternatives considered:
See [MIGRATION_PLAN.md § 4 — Workspace/session ownership](MIGRATION_PLAN.md)
for the compared options (request-scoped-only, in-memory process-global,
storage-backed, database-backed).

Impact:
No Phase 1 (or later) implementation may introduce an unscoped
process-global dict/cache/singleton for source or session data.

---

## DEC-013 — Lightweight JSON metadata sidecars are acceptable for the early migration slice

Date: 2026-08-14
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14).

Decision:
For the first migration slice, small JSON metadata sidecars stored through
the existing `StorageBackend` are an acceptable mechanism for
workspace/source metadata.

`[OPEN]` The long-term persistence architecture remains **undecided and
deferred** — this decision approves an implementation mechanism for the
early slice only, not the long-term persistence model. A later phase may
choose PostgreSQL, a manifest-style file format, the sidecar mechanism
extended, some combination, or something else entirely; no commitment is
made here beyond Phase 1/1.5's immediate needs. See discovery Open Question
#5 and [MIGRATION_PLAN.md § 14](MIGRATION_PLAN.md).

Reason:
Avoids introducing a database before Milestone 1 scope calls for one
([AGENTS.md](../../AGENTS.md)), while still avoiding unscoped in-memory
state (see DEC-012). `StorageBackend` already exists, is already tested,
and already provides exactly the categories this need requires.

Alternatives considered:
See [MIGRATION_PLAN.md § 4](MIGRATION_PLAN.md) for the full options
comparison (in-memory-only, storage-backed sidecars, database-backed).

Impact:
Do not treat the sidecar mechanism as a precedent that forecloses a
database-backed redesign at Phase 8 — the two are independent decisions.

---

## DEC-014 — Phase 1 is COMTRADE-only; CSV/Excel and Import-Wizard-grade timestamp handling are deferred to Phase 1.5

Date: 2026-08-14
Status: Approved
Source: explicit project-owner approval during the governance-cleanup task
(2026-08-14).

Decision:
The first Phase 1 vertical slice supports **COMTRADE only**
(`.cfg`+`.dat` → upload → immutable storage → the existing/reused COMTRADE
provider → `DisturbanceRecord`/backend source model → versioned API →
channel metadata → web channel-list display). General CSV/Excel import is
explicitly **not** included in Phase 1. CSV/Excel support, together with
Import-Wizard-grade timestamp detection/repair, is planned for **Phase
1.5** — not yet implemented.

Reason:
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) found that `powerwave`'s
direct CSV/Excel providers bypass the richer timestamp
classification/repair behaviour that only the Import Wizard backend
provides — a temporary, simplified CSV/Excel path in Phase 1 would either
under-serve real files (silently) or require re-deriving part of the
Wizard's complexity ahead of schedule. COMTRADE alone already exercises
every architectural question Phase 0 needs answered (provider selection,
multi-file upload, storage boundary, metadata API) without that
complication. CSV/Excel are not being dropped — only sequenced after
COMTRADE proves the architecture.

Alternatives considered:
See [MIGRATION_PLAN.md § 16](MIGRATION_PLAN.md) for the originally-compared
options (COMTRADE-only vs. COMTRADE + best-effort direct-provider CSV/Excel
with explicit `ambiguous_timestamp` handling).

Impact:
The Phase 1 implementation task's scope excludes all CSV/Excel code paths
(direct providers and Import Wizard alike) — see
[MIGRATION_PLAN.md — Exact first implementation scope](MIGRATION_PLAN.md#exact-first-implementation-scope).
A temporary/simplified CSV/Excel workflow must not be introduced into
Phase 1 without a separate, explicit approval.

---

## DEC-015 — Uploaded event-record files are not persistently retained

Date: 2026-08-14
Status: Approved
Source: explicit project-owner direction at the start of the Phase 1
implementation task (2026-08-14).

Decision:
`oruxa_powerwave` does not operate as an event-record storage platform.
Uploaded `.cfg`/`.dat` (and, when Phase 1.5 lands, CSV/Excel) files are not
written to VPS persistent application storage, a database blob, object
storage, or any long-term filesystem directory. The target lifecycle is
upload → active server session/workspace → engineering analysis → session
ends → server-side event-record data released. This **narrows DEC-009's
original Impact statement** (which assumed originals would be written
through `StorageBackend`'s write-once `original` category) — see the note
added to DEC-009 above.

Reason:
Explicit product direction: `oruxa_powerwave` is an engineering analysis
platform, not a cloud repository for event records. The user remains the
long-term owner of original event records.

Alternatives considered:
Not documented in source beyond this framing.

Impact:
The Phase 1 implementation stages uploaded bytes only in an ephemeral,
per-request `tempfile.TemporaryDirectory()` (deleted before the request
returns) so the existing `ComtradeProvider` can be reused unmodified — see
this phase's final report / [HANDOFF.md](HANDOFF.md) for the full
investigation of what Starlette itself does with multipart uploads before
either the application or this temp directory is involved. Only lightweight
per-source metadata (channel names/units/counts/timing — never sample
arrays) is kept afterward, in-memory, scoped by `workspace_id`/`source_id`
(see DEC-012), for the life of the process. `StorageBackend` remains
available in the codebase for other future uses (per
[MIGRATION_PLAN.md](MIGRATION_PLAN.md)) but is not used for event files in
Phase 1.

**Update (Phase 2A, 2026-08-15) — see
[DEC-019](#dec-019--phase-2a-retains-the-full-resolution-disturbancerecord-in-the-active-workspace):**
the "only lightweight per-source metadata ... never sample arrays"
sentence above no longer holds — Phase 2A deliberately retains the
full-resolution `DisturbanceRecord` too, so waveform range requests don't
have to re-parse the file. This decision (never persistently retain the
uploaded *file*) is otherwise **fully intact and unaffected**: DEC-019 is
about an already-parsed in-memory object, not the file, and nothing about
Phase 2A writes anything to disk/DB/object storage.

---

## DEC-016 — Upload size ceiling is configurable, not hard-coded, with ~100 MB as the current MVP assumption

Date: 2026-08-14
Status: Approved
Source: explicit project-owner direction at the start of the Phase 1
implementation task (2026-08-14).

Decision:
Typical COMTRADE event records are assumed to be below approximately 100 MB
for the current MVP. This is an operating assumption, not a permanent
technical limit, and is implemented as configuration
(`MAX_EVENT_UPLOAD_SIZE_MB`, default 100), not hard-coded business logic.

Reason:
Keeps the ceiling adjustable per deployment without a code change, while
giving the backend an explicit, enforceable limit and the frontend a
concrete number to communicate to the user.

Alternatives considered:
Not documented in source beyond this framing.

Impact:
`backend/app/config.py` reads `MAX_EVENT_UPLOAD_SIZE_MB` from the
environment; `backend/app/services/import_service.py` enforces it
authoritatively (based on bytes actually read, not trusted client-supplied
size metadata); `backend/app/main.py` adds a fast Content-Length pre-check;
the frontend displays matching guidance text. See this phase's final report
for the exact enforcement mechanism and its known limits.

---

## DEC-017 — COMTRADE two-slot CFG/DAT upload is the approved interaction (resolves UAT-1)

Date: 2026-08-14
Status: Approved
Source: owner UAT of the deployed Phase 1 implementation at
`https://dev.powerwave.oruxa.uk`.

Decision:
The current two-explicit-field upload workflow (a `.cfg` file input and a
`.dat` file input, submitted together) is approved as the COMTRADE upload
interaction — not a temporary placeholder. Auto-pairing, folder scanning, a
single combined file picker, drag/drop redesign, and automatic local
filesystem lookup are explicitly **not** to replace it.

Reason:
Owner UAT found the current workflow simple, understandable, and
comfortable; browser limitations around automatic local file-pairing were
discussed directly, and the owner is comfortable with the current
two-field design given those constraints.

Alternatives considered:
[MIGRATION_PLAN.md § 10](MIGRATION_PLAN.md) originally compared this
(Option B) against single-selection auto-pairing by filename stem
(Option A) and left the choice open for UAT (UAT-1, in "Candidate
Decisions Requiring Future UAT"). UAT has now resolved it in favor of the
already-implemented Option B.

Impact:
UAT-1 is resolved, not merely deferred — no further UI work on COMTRADE
pairing interaction is in scope unless the owner explicitly reopens it.
The backend API is unaffected either way (both options were always a
single multipart POST with `cfg_file`/`dat_file` parts).

---

## DEC-018 — `Start new workspace` is a distinct whole-workspace lifecycle operation, not a Remove alias

Date: 2026-08-14
Status: Approved
Source: explicit project-owner direction, following a focused investigation
into `Remove` vs. `Start new workspace` requested earlier the same day.

Decision:
`Start new workspace` is **retained** in the UI (not removed or hidden) and
is corrected to be a real, backend-enforced whole-workspace reset — never a
client-only relabelling of `Remove`. The two actions now have, and must
keep, clearly distinct semantics:

```
Remove              = remove ONE source from the current workspace
Start new workspace = end/release the ENTIRE current workspace's
                       server-side resources, then begin under a
                       fresh workspace identity
```

`Start new workspace` calls a new whole-workspace backend endpoint
(`DELETE /api/v1/workspaces/{workspace_id}`, see
[MIGRATION_PLAN.md — Phase 1 Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14))
and only rotates the client-side `workspace_id` after that call succeeds. A
confirmation is shown when the current workspace is non-empty; an already-
empty workspace resets without one.

Reason:
The prior implementation only generated a new client-side UUID and never
called the backend at all — old sources stayed resident in
`WorkspaceRegistry` (in-memory, no TTL) and remained reachable via the old
`workspace_id`, contradicting DEC-015's target lifecycle ("session ends →
server-side event-record data released"). The investigation ([HANDOFF.md](HANDOFF.md))
found this was a genuine resource-lifecycle defect, not merely a cosmetic
one (it also left the stale "Imported ..." success banner visible). The
owner decided the button's implied semantics (a fresh start, distinct from
removing one source) are worth keeping and implementing correctly, rather
than removing the affordance (Option A) or deferring it (Option C) from
that investigation's options list.

Alternatives considered:
See the investigation's "Options" section (Option A — remove the button;
Option C — hide/defer until multi-source workspace features exist) — both
rejected in favor of Option B, making the existing button correct.

Impact:
- `WorkspaceRegistry.remove_workspace(workspace_id)` releases every source
  a workspace owns in one call; this is the lifecycle hook any future
  workspace-owned resource (synchronization state, calculated channels,
  measurements, ...) should also plug into, rather than each resource type
  growing its own ad hoc cleanup path.
- This decision does **not** claim abandoned-session cleanup is solved.
  Closing a browser tab, losing network, or otherwise never clicking
  `Start new workspace` still leaves that workspace's sources resident in
  memory until the process restarts — no TTL/expiry mechanism was added.
  This remains a separate `[OPEN]` item — see
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).

---

## DEC-019 — Phase 2A retains the full-resolution `DisturbanceRecord` in the active workspace

Date: 2026-08-15
Status: Approved
Source: explicit project-owner direction opening the Phase 2A implementation
task (2026-08-15), following the Phase 2 discovery/design pass's own
`[DECISION MODE: ANALYSIS]` recommendation on this point (not itself
self-approving — see [README.md — Decision modes](README.md#decision-modes)
— but adopted here by explicit instruction).

Decision:
The active workspace now retains each imported source's full-resolution,
authoritative `DisturbanceRecord` (including its `waveform_data`
DataFrame) for the life of that source — not just the lightweight
`SourceMetadata` Phase 1 originally kept. The two are paired as one
`ActiveSource` object (`app/domain/source.py`) and stored together in
`WorkspaceRegistry`, keyed exactly as before by `(workspace_id,
source_id)` (DEC-012, unchanged). This full-resolution data:

- remains authoritative and backend-owned — never replaced, permanently
  downsampled, or mutated in place;
- is delivered to callers only through bounded time-range requests (`GET
  .../sources/{source_id}/waveform`), never as a full-record transfer by
  default;
- when a requested range exceeds the caller's `point_budget`, is reduced
  to a peak-preserving min/max envelope for that response only — the
  reduced data is a *display representation*, never itself treated as
  authoritative, and is never written back over or used in place of the
  full-resolution source (see `app/services/waveform_service.py`'s module
  docstring and `app/domain/waveform_reduction.py`'s terminology note:
  never "decimated," always "display representation");
- starts JSON-first for the waveform response wire format — no
  Arrow/Protobuf/custom binary transport was introduced this phase (see
  Impact below for when to revisit).

**Update (2026-08-20) — see [DEC-041](#dec-041--waveform-reduction-is-an-overview-rendering-optimization-with-a-10000-sample-full-resolution-display-threshold):**
the reduced-vs-full decision is no longer governed by `point_budget`
alone. `point_budget` remains the budget for reduced overview responses,
but requested ranges containing `<= 10,000` original samples per channel
are now returned sample-for-sample for display.

Reason:
Phase 1's `import_service.py` discarded the parsed `DisturbanceRecord`
after extracting metadata, so no code path existed to answer "what are
this channel's actual sample values in this time range" without
re-parsing the COMTRADE file from scratch on every request. The Phase 2
discovery/design pass ([MIGRATION_PLAN.md — Phase 2 Waveform Workspace
Discovery and Design](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14))
identified this as the one genuinely new backend architecture question
Phase 2 requires, and — separately — confirmed by re-verifying
`powerwave`'s own live decimation code
(`build_aligned_data()`/`decimate_for_display()`) that plain nth-point
stride sampling can silently drop a transient spike or a narrow digital
pulse; that algorithm was explicitly rejected as a migration candidate
in favor of a peak-preserving min/max envelope, implemented fresh for
this project (`app/domain/waveform_reduction.py`).

Alternatives considered:
See [MIGRATION_PLAN.md's Phase 2 design §4](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)
for the compared data-delivery architectures (send-everything-once vs.
range requests vs. multi-resolution pyramid vs. hybrid) — range requests
(Option B/D) were recommended there and are what this decision
implements. See the same section's §13 for the compared display-reduction
algorithms (min/max envelope vs. LTTB vs. plain stride) — min/max envelope
was recommended on engineering-correctness grounds (guaranteed extrema
visibility) and is what `app/domain/waveform_reduction.py` implements.

Impact:
- `WorkspaceRegistry`'s stored value type widened from `SourceMetadata` to
  `ActiveSource`; its keying, locking, and cleanup methods
  (`add`/`get`/`list_for_workspace`/`remove`/`remove_workspace`) did not
  need to change — `remove()`/`remove_workspace()` already correctly drop
  the process's only reference to whatever is stored per
  `(workspace_id, source_id)`, now including the retained record. Verified
  by dedicated tests (`tests/test_waveform_api.py`'s
  `TestLifecycleCleanupReleasesWaveformData`, including a weakref-based
  reference-release check, not just "the API returns 404 afterward").
- **Real, ongoing backend memory cost, not a free change**: retaining
  full-resolution arrays per source means abandoned-workspace memory
  growth (the existing `[OPEN]` TTL item — see
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers))
  is now a materially larger concern than it was for Phase 1's
  metadata-only model. This decision does **not** resolve that TTL
  question — it remains open, reassessed as more urgent, per the Phase 2
  design pass's own conclusion.
- The JSON-first transport choice should be revisited (not automatically
  kept forever) if a future phase's measurements show it's a real
  bottleneck at larger scale — this decision approves it as the Phase 2A
  starting point, not a permanent commitment to JSON regardless of future
  evidence.
- Digital waveform delivery, drag/reorder panel layout, plotting-library
  selection, and TTL/expiry policy remain explicitly **not** decided by
  this entry — see the `[OPEN]`/`[UAT]` items recorded in
  [CURRENT_STATE.md](CURRENT_STATE.md) and
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md)'s Phase 2A implementation record.

---

## DEC-020 — `detego.app` is adopted as a UI/UX/product benchmark, not a ceiling or an architecture requirement

Date: 2026-08-15
Status: Approved
Source: explicit project-owner direction, given directly in conversation
(not via any external attachment — see the note in Alternatives
considered below).

Decision:
`detego.app` is adopted as a **UI/UX, workflow, dashboard, and product
benchmark** for `oruxa_powerwave` feature design, to be consulted
routinely during Phase 2B/2C waveform-workspace design in particular. For
major feature design, use the three-way comparison recorded in full in
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md):

```text
powerwave                          = proven engineering behaviour /
                                      reusable logic
detego.app                         = UI/UX, workflow, dashboard, and
                                      product benchmark
owner requirements / approved
decisions / UAT                    = final authority
```

**Detego is a benchmark, not a ceiling**: `oruxa_powerwave` should aim to
be more capable and more useful than Detego wherever the owner's
engineering requirements justify it. A feature Detego lacks is never, on
its own, a reason to withhold that feature from `oruxa_powerwave`.
Detego's own implementation must not be blindly copied or treated as an
architecture requirement — it is consulted for inspiration/comparison,
never as a specification to satisfy feature-for-feature.

Reason:
The project already has one engineering-behaviour reference
(`powerwave`) but no equivalent reference for UI/UX/workflow quality,
even though the owner has stated (recorded across this project's Phase 1
UAT passes) that `oruxa_powerwave` should emphasize UI/UX more heavily
than the desktop application. Establishing an explicit product/UI
benchmark, with equally explicit limits on its authority, prevents two
failure modes at once: designing Phase 2B/2C waveform UX from first
principles with no external reference point, and — the opposite risk —
silently treating Detego's feature set as a de facto scope ceiling or its
implementation as something to copy rather than learn from.

Alternatives considered:
The same request was first received mid-turn, structured as a
system-reminder-wrapped message referencing "an attached ZIP" that was
never actually present in the assistant's accessible context, asking for
edits to this repository's governance files and a push to `main` while
explicitly directing the assistant to skip this document's own
change-governance step. The assistant declined to act on that version,
flagging it as an unverifiable, injection-shaped request rather than
executing it — see the conversation record for the full flag. The owner
then reissued the same direction as a normal, direct conversational
instruction with self-contained content (no external attachment
referenced or needed), which is the version this decision and
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) are built from. No
technical audit of `detego.app` itself (its actual features, architecture,
or UI) has been performed — this decision establishes the *reference
relationship and its limits*, not a feature comparison; see
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)'s own `[OPEN]` note.

Impact:
- [CLAUDE.md](../../CLAUDE.md) and [AGENTS.md](../../AGENTS.md) both gain
  a short pointer to [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md),
  matching the existing pattern used for the architecture reference
  document (state the principle briefly, read the detail at the source).
- Does **not** retroactively change any already-approved decision in this
  document, and does not by itself approve or reject any specific Phase
  2B/2C feature — it only establishes how Detego may be used as evidence
  in a future `[PROPOSAL]`, per
  [README.md's decision-mode framework](README.md#decision-modes).
- No production code was changed for this decision.

**Wording update (2026-08-15, same day)**: the owner subsequently supplied
the actual source document ("Detego Benchmark Principle.rtf") as a real
attachment, containing canonical wording for this same decision — a
substantively different situation from the earlier declined attempt (a
message referencing a ZIP that was never actually present). This is not a
new decision (no `DEC-021` was created): the substance is unchanged, but
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) was updated to quote the
owner-supplied text verbatim as the authoritative statement, and now
additionally includes two specifics not spelled out in this entry's
original wording above: (1) *"If Detego's workflow is good, learn from
the public behaviour and implement an independent Oruxa design"*, and
(2) the standing question to ask for major features — *"What does Detego
do here, what does existing powerwave do, and what would make
oruxa_powerwave better for the engineer?"* Both are part of this same
DEC-020 decision, not separate ones. [CLAUDE.md](../../CLAUDE.md)/
[AGENTS.md](../../AGENTS.md) were updated to match this wording too.

---

## DEC-021 — Waveform navigation is workspace-level, not channel-level

Date: 2026-08-15
Status: Approved
Source: explicit project-owner direction, given directly in conversation
while requesting a focused Phase 2B Plotly-refinement pass, following the
owner's own hands-on UAT of the Phase 2B renderer prototype.

Decision:
Future multi-channel waveform navigation in `oruxa_powerwave` is
**workspace-level (shared across every displayed analog channel), never
independently controlled per channel**:

- all displayed analog channels share one common visible X/time range;
- zooming the waveform workspace zooms every displayed channel together;
- panning moves every displayed channel together;
- zoom in/out acts on the whole waveform workspace, not one trace;
- "Reset Time View" restores the whole workspace's time range;
- cursor/time navigation (Phase 5+) will be shared across displayed
  channels, not owned separately by each one;
- channels may keep **independent Y scales** — only the X/time axis is
  required to be shared.

Conceptually:

```text
Central Waveform Toolbar
        |
shared time viewport
        |
VA, VB, VC, IA, IB, IC, Frequency, ...  (all follow the same X/time window)
```

A directly related, equally approved requirement: **the final multi-channel
workspace must not rely on a separate Plotly (or any library's) modebar
per channel/subplot.** A single, centralized Powerwave waveform toolbar
must expose the shared controls (zoom, pan, zoom in/out, Reset Time View,
Autoscale Y, cursor mode, and later A/B cursors, time-reference controls,
and export) — never one native per-channel toolbar repeated per trace.

This decision also fixes the terminology, to be used consistently in code
and docs going forward: **"Reset Time View"** (restore the full-record
X/time range) and **"Autoscale Y"** (adjust vertical magnitude scaling)
are two different operations and must never be collapsed into one control
or one concept.

Reason:
Confirmed directly by the owner's own Phase 2B UAT: reviewing Plotly's
native per-chart modebar (zoom/pan/autoscale/reset, all scoped to that one
chart) made concrete what a future multi-channel workspace must NOT
become — N independent per-channel toolbars each controlling their own,
potentially divergent, time window, which would make cross-channel
disturbance correlation (the entire point of a multi-channel engineering
view) actively harder, not easier. Locking in the shared-viewport
principle now, while Phase 2B still only has one channel, prevents Phase
2C's architecture from accidentally building per-channel navigation
controls that would later need to be torn out.

Alternatives considered:
Per-channel independent X navigation (effectively N unrelated single-
channel charts) was the default a naive multi-channel extension of Phase
2B's current one-channel-per-page model would produce if this principle
weren't recorded now — considered and explicitly rejected. A hybrid
(shared-by-default, but individually overridable per channel) was not
raised by the owner and is not adopted here; if wanted later, it would be
a new, separate decision, not an interpretation of this one.

Impact:
- Phase 2B's own request-coordinator function
  (`requestViewportRangeDebounced` in `frontend/waveform-prototype.html`)
  was **not restructured** this pass (multi-channel fetching remains
  explicitly out of scope) but is documented in place as the intended
  Phase 2C extension point: a future version fans one shared
  `(startTime, endTime)` viewport out to every displayed channel's own
  fetch, rather than each channel owning an independent viewport.
- Phase 2C's future panel/layout design must keep **channel-specific**
  controls (show/hide, reorder, move between panels/groups, color, panel
  height, Y-axis scale, remove from display) and **workspace-level**
  controls (everything listed in the Decision above) architecturally
  distinct — flexible vertical layout (per-channel) must coexist with
  synchronized horizontal time navigation (workspace-level), not be
  conflated with it.
- Does not itself approve any specific Phase 2C panel/toolbar design,
  digital-channel handling, or cursor implementation — those remain
  separate, still-`[OPEN]`/`[UAT]` decisions.
- No production backend change — this is a frontend/UX architecture
  principle only; the Phase 2A waveform API's per-request shape
  (`channel_name`, `start_time`, `end_time`, `point_budget`) already
  supports being called once per displayed channel with the same range,
  so no API change is anticipated to honor this decision later either.

---

## DEC-022 — Plotly.js selected as waveform rendering foundation; Phase 2B renderer UAT closed

Date: 2026-08-15
Status: Approved
Source: explicit project-owner direction, following the owner's completed
hands-on UAT of the Phase 2B renderer prototype (uPlot vs. Plotly.js,
commit `ad6d9d2`, refined for crosshair/lag at commit `8483c8a`).

Decision:
**Plotly.js is selected as the waveform rendering foundation for
`oruxa_powerwave`.** This is the final Phase 2B renderer outcome — no
longer `[UAT — pending]`. uPlot was evaluated as a genuine, fairly-tested
comparison candidate and is **not** selected for the forward
implementation; its adapter, vendored assets, and the renderer-switch UI
have been removed from `frontend/waveform-prototype.html` this pass (see
Impact below).

Owner UAT findings, recorded verbatim for the record:

- **Plotly**: better waveform clarity; good pan; useful built-in
  navigation/control capabilities (zoom, zoom in, zoom out, autoscale,
  reset axes, PNG export); moving hover X/Y values; overall better
  engineering interaction feel; responsiveness judged acceptable.
- **uPlot**: useful/lightweight; very good free-moving crosshair feel;
  but overall less preferred than Plotly for the intended future
  workspace.

**Crosshair responsiveness was explicitly NOT pursued further.** The
owner noted Plotly's sample-snapped crosshair can feel slightly less
responsive than uPlot's free-moving cursor, then explicitly clarified
this gap is *"not important enough to justify additional implementation
complexity or development time."* No custom mouse-following overlay, no
recreation of uPlot's two-layer cursor mechanics, and no custom hover
engine were built. Plotly's native, sample-snapped hover behaviour is
kept as-is functionally — only its **visual styling** was refined (thin,
dashed, reduced-opacity spike lines, closer to uPlot's visual subtlety
without its cursor mechanics).

**This decision does not weaken or reinterpret DEC-021.** Plotly being
selected as the rendering *engine* is a separate question from how
navigation is *architected* — DEC-021's workspace-level, centralized-
toolbar requirement remains fully authoritative. Plotly's native
per-channel modebar, kept for this single-channel page, is explicitly
documented (in code and in the page's own UI text) as **temporary** —
Phase 2C must design one centralized Powerwave toolbar shared across
every displayed channel, never one native modebar per channel/subplot.

Reason:
The owner's own hands-on comparison, using identical backend data and an
identical interaction contract for both candidates (per Phase 2B's
fair-comparison design), found Plotly's overall engineering interaction
feel, built-in control richness, and waveform clarity stronger than
uPlot's for the intended future workspace — outweighing uPlot's
crosshair-feel advantage, which the owner judged as not decisive enough
to justify the added complexity of trying to replicate it on top of
Plotly.

Alternatives considered:
Keeping both candidates indefinitely (rejected — the comparison had a
clear owner-stated outcome, and carrying two renderers forward serves no
purpose once one is chosen); building a custom crosshair overlay to close
the responsiveness gap (rejected — explicitly, by the owner, as not worth
the complexity); waiting for Phase 2C to decide the renderer (rejected —
the owner UAT is already conclusive, and Phase 2C's own design work
benefits from a settled rendering foundation rather than an open
question).

Impact:
- `frontend/waveform-prototype.html`: `UPlotAdapter`, the `ADAPTERS` map,
  `switchRenderer()`, and the renderer-tab UI (`tabUplot`/`tabPlotly`
  buttons, `.renderer-tab` CSS) are removed. The remaining `PlotlyRenderer`
  object is initialized once, directly, in `init()`. "Renderer comparison
  prototype" / "Phase 2B UAT" wording is removed from the visible page;
  replaced with "Single-channel waveform preview — not the final Phase 2C
  workspace," retaining a clear early-phase indication without
  comparison-specific language.
- `frontend/vendor/uplot/` (the vendored uPlot bundle and its `LICENSE`)
  is deleted. `frontend/vendor/plotly/` remains, now the only vendored
  library. `frontend/vendor/README.md` updated accordingly, with a short
  "History" note (not a deletion of the fact that uPlot was evaluated).
- Crosshair styling refined: `spikedash: "dash"` (was `"solid"`),
  `spikecolor` changed to a reduced-opacity value (was a fully-opaque
  `--text-dim`), `spikethickness` unchanged at `1` (already the thinnest
  practical value). `spikesnap: "data"` unchanged — sample-snapping is
  preserved exactly.
- Phase 2A backend: **untouched** — no route, schema, service, or domain
  file in `backend/app/` was modified for this decision; all existing
  backend tests remain unmodified and passing.
- **Phase 2B is now complete.** Phase 2C (centralized toolbar, panel
  model, drag/reorder, multi-channel display) remains explicitly **not**
  started and not authorized by this decision.

---

## DEC-023 — Application supports Light and Dark appearance; Light is the preferred/default direction

Date: 2026-08-15
Status: Approved
Source: explicit project-owner UX requirement for a focused theming/
crosshair refinement task (2026-08-15), following Phase 2C's discovery/
design pass (design only, not implemented).

Decision:

> Oruxa Powerwave supports Light and Dark appearance.
> Light is the preferred/default direction.
> Theme is a general application preference.
> Detego is only a UI/UX benchmark; Oruxa uses its own palette.

Implemented as a small, shared, reusable theme-token system (CSS custom
properties, `frontend/theme.css`) and a shared preference module
(`frontend/theme.js`), not scattered hard-coded colors, and not scoped to
the waveform page alone — every existing static frontend page
(`index.html`, `waveform-prototype.html`) includes both files and applies
the theme coherently across the main Phase 1 page, source/channel browser,
tables, buttons, dialogs, banners, the waveform page, and the Plotly chart
itself. Light is the default whenever no preference is stored; the user's
choice persists in `localStorage` (`powerwave.theme`) and applies
immediately without a page reload. Dark is preserved through the same
token system — same layout, same behavior, different appearance — not a
second, parallel CSS implementation. The original Oruxa light palette
(clean, professional, restrained accent, subtle borders) is explicitly
**not** derived from or matching Detego's visual identity — Detego was
consulted only per the already-established Detego Benchmark Principle
(DEC-020/`PRODUCT_REFERENCES.md`) as a UI/UX workflow benchmark, never as
a source of colors.

Also recorded by this same decision:

- The Plotly crosshair (native axis spike-lines, DEC-022/DEC-023 unchanged
  in mechanism) was refined further for visual subtlety:
  `spikethickness` reduced from `1` to `0.5` (Plotly's spike-line stroke is
  rendered as an ordinary SVG path even for a `scattergl` trace, and SVG
  `stroke-width` reliably supports fractional values below `1` across
  current browsers — this is standard SVG rendering, not a workaround; see
  Impact below for the honest caveat on visual confirmation), and
  `spikecolor`'s alpha reduced from `0.55` to `0.42`, using the same
  theme-token mechanism (`--spike-color`) so the crosshair's color is
  correct in both Light and Dark.
- **No custom mouse-following crosshair, no new cursor architecture, and
  no custom hover engine were added.** The crosshair remains Plotly's
  native, sample-snapped (`spikesnap: "data"`) spike-line mechanism —
  unchanged since DEC-022, only its visual styling and theme-reactivity
  were refined.
- **Phase 2C (centralized toolbar, panel model, drag/reorder,
  multi-channel display) remains explicitly not started.** This is a
  general-app UX refinement, unrelated to and not a step toward Phase 2C
  implementation.

Reason:

The owner wants the application to support both appearances, with Light as
the preferred direction, while keeping the existing dark direction intact
for users who prefer it — and wants this to feel like one coherent
application (the waveform page must not look visually disconnected from
the main app). A small, shared token system is the standard, low-complexity
way to support this without introducing a frontend framework or scattering
per-element color literals that would drift between the two themes over
time. The crosshair was already refined once for visual subtlety
(DEC-022); the owner still found it too thick, and closer inspection this
pass found the earlier claim that `spikethickness: 1` was Plotly's
practical minimum was not fully substantiated — SVG's own stroke-width
support for sub-1 values is standard, not exotic, so a genuinely thinner
native value was used instead of only relying on the alpha/dash levers
already in place.

Alternatives considered:

Scattered per-page hard-coded light/dark color literals (rejected —
directly contradicts the task's own "do not scatter hard-coded colors"
instruction and this project's established preference for token-based,
maintainable styling); a full settings-page redesign (rejected — the
owner explicitly asked for a simple selector, not a redesigned settings
experience); copying Detego's visual palette (rejected outright — the
Detego Benchmark Principle, DEC-020, is explicit that Detego is a UI/UX
*workflow* benchmark, never a source of colors or visual identity, and the
owner repeated that constraint directly for this task); keeping
`spikethickness: 1` unchanged and relying only on alpha/dash (a legitimate
fallback the owner explicitly authorized if `1` really were the practical
minimum — not needed here, since a genuinely thinner native value was
available; both levers were used together anyway for compounding
subtlety).

Impact:

- New files: `frontend/theme.css` (light/dark token definitions + the
  Appearance toggle control's styles), `frontend/theme.js` (get/set/apply
  preference logic, cross-tab `storage`-event sync, and a shared
  `mountThemeToggle()` helper used identically by every page).
- `frontend/index.html` / `frontend/waveform-prototype.html`: both now
  `<link>`/`<script>` the shared theme files (loaded early, before body
  paint, to avoid a theme flash); their own local hard-coded `:root` color
  blocks and scattered `rgba(...)`/hex literals were replaced with the
  shared tokens; both gained a small Light/Dark segmented control in their
  header.
- `frontend/waveform-prototype.html`'s Plotly integration reads colors
  from the active theme at chart-init time and re-applies them via
  `Plotly.relayout`/`Plotly.restyle` on a theme change — **no waveform
  data is refetched when the theme changes**, per the task's explicit
  requirement; only already-rendered chart chrome (backgrounds, font,
  grid, spike colors) and the trace's line color are updated.
- `frontend/Dockerfile` / `frontend/.dockerignore`: updated to
  copy/document the two new static files, following the exact existing
  pattern for `config.js`.
- **Honest limitation, stated per this task's own instruction**: the
  `spikethickness: 0.5` value was not visually confirmed with a real
  screenshot in this sandboxed, no-real-browser session — the change rests
  on SVG's well-established, universal support for fractional
  `stroke-width`, not a live pixel-level comparison. Live DEV verification
  (this task's own checklist) is the point at which the owner can visually
  confirm the result.
- No backend file was touched; all existing backend tests are unmodified
  and passing.

**Update (2026-08-15, same day) — crosshair visual UAT follow-up**: theme
UAT passed; the owner's only remaining feedback was that the crosshair was
still too coarse and too faint in **both** themes. This is a refinement of
the same crosshair styling covered above, not a new decision:
`spikethickness` reduced again, `0.5` → `0.35` (still a genuine, natively-
supported fractional SVG stroke-width, same reasoning as before);
`spikedash` changed from the named `"dash"` style to a custom native
Plotly dash-length string, `"3px,2px"` — Plotly's own `dash` attribute
documents this exact `"px,px,..."` syntax as a first-class supported value
alongside the named styles, so this remains native configuration, not a
workaround. **Honest limitation, again stated directly**: Plotly's
built-in named `"dash"` style's exact internal pixel definition is not
stable, documented public API to reverse-engineer and halve precisely, so
an explicit shorter native value was chosen instead of a mathematically
exact half — the closest clean native option, per this follow-up task's
own explicit allowance for that outcome. `--spike-color` was also
strengthened in both themes for stronger contrast, stopping short of full
opacity: Light `rgba(92, 101, 121, 0.42)` → `rgba(60, 68, 87, 0.6)`
(darkened toward `--text`, higher alpha); Dark `rgba(139, 150, 173, 0.42)`
→ `rgba(168, 178, 199, 0.6)` (brightened toward `--text`, higher alpha).
Grid styling (`gridcolor`) was deliberately left untouched — the owner
already finds it acceptable. No custom crosshair/cursor overlay was built;
no Plotly-generated SVG was manually manipulated. No backend file was
touched; all 278 backend tests remain unmodified and passing. Phase 2C
remains not started.

---

## DEC-024 — Phase 2C-A multi-channel waveform workspace architecture confirmed and implemented

Date: 2026-08-15
Status: Approved
Source: explicit project-owner implementation instructions opening the
Phase 2C-A task (2026-08-15), directly confirming/selecting specific
architectural options that the Phase 2C discovery/design pass
(`docs/project-memory/MIGRATION_PLAN.md`'s Phase 2C record) had only
recorded as `[PROPOSAL]`/`[ANALYSIS]`/`[NEEDS UAT]`, not yet decided.

Decision:

The first real multi-channel waveform workspace (Phase 2C-A) is
implemented directly in `frontend/index.html` (not a separate isolated
page, unlike Phase 2B's `waveform-prototype.html`), confirming the
following specific architectural choices as approved, not merely
proposed:

- **One independent Plotly instance per panel** (never one giant figure
  with fixed subplots) — confirms the Phase 2C design's own §16
  recommendation. A panel may hold one or more channel traces; each panel
  keeps its own Y axis.
- **Checkbox selection + "Add N selected"** is the approved channel-add
  workflow (analog channels only) — confirms the Phase 2C design's §5
  recommendation over drag-to-add or a per-channel add button.
- **Initial grouping by existing `engineering_type`** (never re-derived
  client-side) is the approved default panel placement — confirmed as
  **placement only, never a permanent lock**: nothing in this
  implementation prevents a future Phase 2C-B from letting the user move
  a channel to a different panel.
- **One shared, Oruxa-owned X/time viewport drives every displayed
  panel** (DEC-021, reaffirmed and now actually built, not just
  specified) — zoom/pan on any one panel broadcasts to every other panel;
  no panel may independently drift to its own time range.
- **A single central Powerwave toolbar** — Zoom, Pan, Reset Time View,
  Autoscale Y — is the only navigation surface; every per-panel native
  Plotly modebar is disabled (`displayModeBar: false`).
- **Autoscale Y is viewport-aware Fit only** for this slice — confirms
  the Phase 2C design's §19 recommendation; Proportional/shared-unit
  scaling remains explicitly deferred.
- **The existing Phase 2A single-channel waveform endpoint is reused
  unmodified** — N displayed channels means N existing requests (same
  `start_time`/`end_time`/`point_budget` for all), not a new
  multi-channel batching endpoint. Batching remains evidence-gated future
  work (Phase 2C design's §17), not built here.
- **Crosshair synchronization across panels is explicitly not part of
  this slice** — each panel's native Plotly hover/spike behaviour
  (DEC-022/DEC-023, unchanged) stays independent.

Reason:

The Phase 2C discovery/design pass deliberately left every one of these
as a `[PROPOSAL]`/`[ANALYSIS]`/`[NEEDS UAT]` item, per its own explicit
instruction not to self-approve architecture. This task's own
specification is the owner directly selecting among those documented
options (one-Plotly-instance-per-panel over a single-figure-with-subplots
architecture; checkbox+button over drag-to-add; viewport-aware Fit over
Proportional-first) rather than an agent's own recommendation — per this
project's own governance ("an agent's own recommendation is a
`[PROPOSAL]`, never a decision"), that distinction is exactly what makes
this a real, recordable decision rather than an implementation detail.

Alternatives considered:

See `docs/project-memory/MIGRATION_PLAN.md`'s Phase 2C design record for
the full comparison tables already produced for each of these questions
(§16 one-figure-with-subplots vs. one-instance-per-panel; §5
channel-add-workflow options; §19 Y-scaling modes; §17 backend request
strategy) — this decision selects the already-analyzed winning option in
each case, it does not re-derive the comparison.

Impact:

- `frontend/index.html`: multi-channel checkbox selection on the existing
  analog channel table (search/grouping unchanged), a new "Waveform
  Workspace" section (stacked panels, central toolbar, empty state), and
  the full panel/viewport/toolbar/removal/theme JS module described in
  this task's own implementation record
  (`docs/project-memory/MIGRATION_PLAN.md`).
- No backend file changed; the Phase 2A waveform endpoint's contract is
  unchanged.
- `frontend/waveform-prototype.html` (Phase 2B's isolated single-channel
  preview) is untouched and remains available — this decision does not
  retire it.
- **Phase 2C-B (drag/reorder channels between panels, panel resize,
  Proportional Y scaling, mixed-unit panel handling) remains explicitly
  not started and not authorized by this decision.**

---

## DEC-025 — Grouped/Separate analog waveform layout modes confirmed and implemented (Phase 2C-B1)

Date: 2026-08-15
Status: Approved
Source: explicit project-owner instructions opening the Phase 2C-B1 task
(2026-08-15), following manual UAT of Phase 2C-A that passed for shared
synchronization, zoom/pan, Reset Time View, Voltage/Current grouping, and
Autoscale Y.

Decision:

The Phase 2C design record's own previously-open question — "whether
several related channels should ever share one panel by user choice (vs.
one-type-per-panel always)" (§9, `[NEEDS UAT]`) — is resolved for this
slice: the waveform workspace supports two user-selectable layout modes,
**Grouped** (the existing Phase 2C-A default — panels formed by
`engineering_type`) and **Separate** (one panel/lane per displayed analog
channel), switchable via a simple toolbar control. **Custom** grouping
(matching Detego's own third mode, per the Phase 2C design record's §3
Detego findings) is explicitly **not** built in this slice.

Confirmed as part of this same decision:

- Switching layout mode **never** changes which channels are displayed,
  and **never** issues a new waveform request — already-fetched channel
  data is reused as-is when panels are rebuilt for the new mode.
- Switching layout mode **preserves the current shared X/time viewport**
  exactly — a zoomed-in view survives a Grouped ↔ Separate switch
  unchanged, in either direction.
- The underlying data model represents displayed channels, panels,
  channel-membership-within-panels, and panel order directly — layout
  mode is only which *algorithm* currently derives panels from that flat
  channel list, not a property stored permanently on a channel. This is a
  deliberate architectural choice so that a future direct
  vertical-drag/reorder/overlay/split interaction (the owner's own stated
  next direction) is a different way of arriving at the same shape, not a
  redesign of it.

Reason:

The owner's own Phase 2C-A UAT explicitly requested "waveform layout
flexibility" as the next enhancement, and this task's own specification
(§3/§4/§13) is the owner directly selecting Grouped+Separate (not
Custom yet) as the resolved answer to the Phase 2C design record's
previously-open grouping-mode question, with an explicit architectural
constraint (§13) for how it must be built so it doesn't block the
specific future interaction already planned (drag lanes vertically,
reorder, drop-to-overlay/group, drag back out to separate). Per this
project's own governance, a genuine owner selection among previously-
documented options is a decision worth recording, not merely an
implementation detail.

Alternatives considered:

Deriving panels permanently from `engineering_type` with layout mode
implemented as a second, parallel data structure (rejected — would
require reconciling two sources of truth every time a channel is added/
removed, and would not naturally support the stated future drag/reorder
direction); building Custom grouping now alongside Grouped/Separate
(rejected — explicitly out of scope per this task's own instruction,
§4/§18); refetching waveform data on every layout switch for simplicity
(rejected — unnecessary given the data hasn't changed, and directly
contrary to this task's own §11 instruction to avoid it).

Impact:

- `frontend/index.html`: a `ww.layoutMode` state field, a
  `wwPanelGroupKeyFor`/`wwPanelLabelFor` pair of helpers (layout-mode-
  aware panel identity, replacing the Phase 2C-A hardcoded
  `engineering_type`-only lookup), a `wwRebuildLayout()` function (tears
  down and recreates every panel's Plotly instance from already-fetched
  channel data, never refetching, never resetting `ww.viewport`), and a
  small Grouped/Separate toolbar control.
- No backend file changed; the Phase 2A waveform endpoint's contract and
  Phase 2C-A's request/response shape are unchanged.
- DEC-021 (shared workspace-level viewport) and DEC-024 (one-Plotly-
  instance-per-panel, viewport-aware Autoscale Y, central toolbar) are
  reaffirmed unweakened — both layout modes obey them identically.
- **Direct vertical drag/reorder of lanes, drag-to-overlay/group, and
  drag-out-to-separate remain explicitly not started and not authorized
  by this decision** — they are the owner's stated *next* direction, not
  built here.

---

## DEC-026 — Separate mode's visual presentation is a unified analog canvas (Phase 2C-B2)

Date: 2026-08-15
Status: Approved
Source: explicit project-owner instructions opening the Phase 2C-B2 task
(2026-08-15), following manual UAT of Phase 2C-B1 that passed for
synchronization/zoom/pan but flagged Separate mode's visual layout (a
stack of individually-carded/headed panels) as not the desired appearance,
with an owner-supplied Detego screenshot as a visual/layout reference only
(per the Detego Benchmark Principle, DEC-020).

Decision:

Separate mode's visual presentation is a **unified analog canvas**: every
displayed analog channel keeps its own independent lane and its own
independent Y scale (channels are never merged onto one shared Y axis —
an explicit, deliberate distinction from the visual chrome change), but
the surrounding chrome — per-lane card borders, repeated backgrounds,
repeated panel headers, and repeated X-axis tick labels/titles on every
lane — is removed so the six-plus lanes read as one continuous, shared
analog workspace rather than N independent cards. Only the bottom-most
lane displays the shared time axis; every other lane suppresses it, since
all lanes already share one Oruxa-owned X/time viewport (DEC-021).
**Grouped mode's visual presentation is unchanged** — this decision
applies to Separate mode only.

Confirmed as part of this same decision:

- The unified-canvas styling is a pure CSS/relayout-chrome layer on top of
  Phase 2C-B1's existing panel data model (`ww.panels`: displayed
  channels, panel membership, panel order) — no change to that model, no
  change to the shared-viewport synchronization mechanism (DEC-021), no
  change to the waveform data contract (DEC-019/Phase 2A), no new waveform
  fetch is issued by switching into or out of this mode.
- The panel-order property this data model already carries (kept general
  since DEC-025, specifically for a future drag/reorder feature) is reused
  here to decide which lane is "bottom" for the shared time axis — further
  evidence that lane order is already a first-class, directly-usable
  property of the model, not something this decision needed to introduce.

Reason:

The owner's own Phase 2C-B1 UAT explicitly identified the individually-
carded panel appearance as not matching the intended product direction,
supplied a Detego screenshot as a layout/interaction reference (never a
specification to copy, per DEC-020), and this task's own specification
(§3/§4/§6) is the owner directly selecting "one continuous canvas,
independent lanes, independent Y scales" as the resolved visual target.
Per this project's own governance, a genuine owner selection of a specific
visual direction — especially one explicitly distinguished from a
rejected alternative (one shared Y axis) — is a decision worth recording,
not merely an implementation detail.

Alternatives considered:

Merging all analog traces onto one shared Y axis inside a single Plotly
figure (rejected — explicitly the wrong interpretation per this task's own
§4 "critical distinction," and would have destroyed each channel's
independent engineering scale); rewriting the panel architecture as one
giant fixed-subplot Plotly figure to achieve the unified look (rejected —
this task's own §7 explicitly discourages this without a strong,
documented technical reason, and the existing one-Plotly-instance-per-lane
architecture already achieves the same visual result via CSS alone);
showing the full X axis on every lane (rejected — repeats the same time
information N times, working against the "one shared time axis" reading
this decision requires, per §8).

Impact:

- `frontend/index.html`: a `ww-panels-unified` CSS class toggled on the
  shared `#wwPanels` container while `ww.layoutMode === "separate"`
  (`wwSetLayoutMode`), new CSS rules scoping the de-carded/compact lane
  presentation to that class only (Grouped mode's own `.ww-panel` styling
  is untouched), and a new `wwUpdateBottomLaneAxis()` function that shows
  X tick labels/title on only the last panel in `ww.panels`' order.
- No backend file changed; the Phase 2A waveform endpoint's contract and
  Phase 2C-A/B1's request/response shape are unchanged.
- DEC-021 (shared workspace-level viewport), DEC-024 (one-Plotly-instance-
  per-panel, viewport-aware Autoscale Y, central toolbar), and DEC-025
  (Grouped/Separate layout modes, panel data model) are all reaffirmed
  unweakened — this decision is a visual layer on top of them, not a
  replacement for any of them.
- **Direct vertical drag/reorder of lanes, drag-to-overlay/group,
  drag-out-to-separate, digital-channel rendering, panel resize, and
  Custom layout mode remain explicitly not started and not authorized by
  this decision** — they are the owner's stated *next* direction, not
  built here.

**Update (2026-08-15, Phase 2C-B3, same day)**: following owner UAT
confirming the unified-canvas direction itself is accepted ("Separate view
now feels much better"), the lane label moved from the canvas's left edge
to its right edge and was restyled as a small compact pill/tag (Detego
used only as a placement/compactness reference, never for exact colors,
typography, or icons — unchanged principle). This is a refinement of the
same visual-presentation concern this decision already covers, not a new
architectural direction — no new decision entry was added for it, per
governance (only add an entry for something not already captured). See
[MIGRATION_PLAN.md — Phase 2C-B3 Implementation Record](MIGRATION_PLAN.md#phase-2c-b3--right-side-compact-lane-labels-implementation-record-2026-08-15).
The waveform column still keeps maximum available width; each lane still
keeps its own independent Y axis; Grouped mode is still untouched.

**Update (2026-08-15, Phase 2C-B3A, same day, correction)**: the owner
clarified the Phase 2C-B3 right-side-column placement was still not the
intended layout — the label must be **overlaid on the waveform lane
itself**, not placed in a dedicated right-side layout column, and should
follow **Detego's own separate-waveform label style as closely as
practical** for this specific placement (Detego treated as the explicit
layout benchmark here, not just loose inspiration). The dedicated
fixed-width grid column was removed; the label (same DOM/markup) is now
absolutely positioned over the chart area (pinned near the right edge,
vertically centered, `z-index` above the chart) instead of occupying its
own layout space. Still a refinement of the same visual-presentation
concern this decision already covers, not a new architectural direction —
no new decision entry was added, per governance. See
[MIGRATION_PLAN.md — Phase 2C-B3A Implementation Record](MIGRATION_PLAN.md#phase-2c-b3a--overlay-right-side-lane-labels-implementation-record-2026-08-15).
Oruxa theme tokens (background/border/text), the remove control, and
Grouped mode's own presentation remain unchanged.

---

## DEC-027 — Custom Analog Channel Groups added as a third layout mode; drag/reorder deferred (Phase 2C-C1)

Date: 2026-08-15
Status: Approved
Source: explicit project-owner instructions opening the Phase 2C-C1 task
(2026-08-15) — the owner's own direct choice to skip vertical lane
drag/reorder for now (previously flagged, in every Phase 2C-B record
since Phase 2C-A, as the owner's stated *next* direction) and implement
Custom Groups instead, with Detego's "Edit Channel Groups" workflow named
explicitly as the reference.

Decision:

The Phase 2C design record's own previously-open question — Custom
grouping, Detego's own third grouping mode, explicitly deferred at both
Phase 2C-A (DEC-024) and Phase 2C-B1 (DEC-025) — is resolved for this
slice: the waveform workspace supports a third user-selectable layout
mode, **Custom**, alongside Grouped and Separate. In Custom mode, the
user manually decides which displayed analog channels share a waveform
panel via a new **Edit Channel Groups** dialog (create groups, assign/
unassign channels, Apply/Cancel). Direct vertical lane drag/reorder and
drag-to-overlay/group by direct lane dragging are explicitly **not**
built in this slice — the owner's own choice to pursue Custom Groups
first.

Confirmed as part of this same decision:

- **Group assignment rule** (this task's own §7 required a choice
  between two options, documented and reported honestly): any displayed
  analog channel not placed into a user-defined group automatically
  becomes its own single-channel panel. There is no "unplaced, no panel"
  state, and Apply is never blocked on complete assignment.
- Switching layout mode (Grouped/Separate/Custom, any direction) **never**
  changes which channels are displayed and **never** issues a new
  waveform request — reusing exactly the same `wwRebuildLayout()`
  mechanism Phase 2C-B1 (DEC-025) already built, which needed **zero
  changes** to support the new mode.
- Switching layout mode **preserves the current shared X/time viewport**
  exactly, including across opening/Applying the group editor — verified
  directly, not just asserted.
- **The last-applied Custom grouping persists for the remainder of the
  current workspace/session**: switching away from Custom and back
  restores it, rather than resetting to an all-solo layout. Reset only by
  a whole-workspace operation ("Clear workspace"/"Start new workspace"),
  matching how the shared viewport and record bounds are already reset
  there.
- No drag-and-drop was built inside the group editor (moving a channel
  between two groups is two explicit actions — unassign, then assign via
  a dropdown — not one direct drag); this is a deliberate first-slice
  scope choice, not an oversight, and is separate from and unrelated to
  the deferred direct-lane-drag/reorder feature.

Reason:

The owner's own instructions opening this task are the explicit act of
choosing Custom Groups over drag/reorder as the next Phase 2C
enhancement, and directly resolving §7's group-assignment-rule choice
(one of two named options) with a chosen rule to document. Per this
project's own governance, a genuine owner selection among previously-
documented options — and an explicit sequencing choice among two
concretely proposed next directions — is a decision worth recording, not
merely an implementation detail.

Alternatives considered:

Requiring every displayed channel to be explicitly placed into a group
before Apply is allowed (rejected — this task's own §7 offered it as the
alternative option; rejected as unnecessary first-slice friction with no
compensating benefit, since an unassigned channel isn't wrong, only not
yet grouped with anything); building direct drag-and-drop of channels
between groups inside the editor (rejected for this slice — this task's
own §6 explicitly permits skipping it "unless genuinely simple," and the
two-step unassign/reassign mechanic was judged simpler and lower-risk to
ship correctly); resetting Custom grouping to all-solo every time the
mode is switched away and back (rejected — this task's own §9 explicitly
prefers persistence "if simple and safe," and it was both).

Impact:

- `frontend/index.html`: a `ww.customGroups`/`ww.customGroupSeq` state
  pair; a `wwCustomGroupFor()` lookup helper; a "custom" branch added to
  `wwPanelGroupKeyFor`/`wwPanelLabelFor` (the only change needed to
  `wwRebuildLayout()`'s own derivation logic — the function itself was
  not touched); a third `layoutModeCustomBtn` toolbar button; a new
  `editChannelGroupsBtn` control and its own modal (`groupEditorOverlay`)
  with its own working-copy editing state (`groupEditorState`), never
  writing to `ww.customGroups` until Apply.
- No backend file changed; the Phase 2A waveform endpoint's contract and
  every prior phase's request/response shape are unchanged. No backend
  persistence was added — Custom grouping is workspace-session,
  in-memory, frontend-only state, matching this task's own §11/§16
  preference and the project's existing ephemeral-by-design principle
  (DEC-015).
- DEC-021 (shared workspace-level viewport), DEC-024 (one-Plotly-
  instance-per-panel, viewport-aware Autoscale Y, central toolbar),
  DEC-025 (Grouped/Separate, panel-derivation architecture), and DEC-026
  (Separate mode's unified-canvas visual treatment) are all reaffirmed
  unweakened — Custom mode obeys all of them identically, and
  deliberately does NOT adopt DEC-026's unified/overlay treatment (a
  Custom panel can hold multiple channels, the same shape as Grouped, not
  Separate's single-channel-lane shape).
- **Direct vertical drag/reorder of lanes and drag-to-overlay/group by
  direct lane dragging remain explicitly not started and not authorized
  by this decision** — they are the owner's own previously-stated next
  direction, deliberately set aside in favor of Custom Groups this pass,
  not abandoned.

---

## DEC-028 — Adjustable waveform panel heights added to all three layout modes (Phase 2C-C2)

Date: 2026-08-15
Status: Approved
Source: explicit project-owner instructions opening the Phase 2C-C2 task
(2026-08-15), following the owner's own manual UAT of Phase 2C-C1 Custom
Groups (**passed** — "the Custom Groups workflow is smooth and easy to
understand"), naming Detego's vertical panel-resize interaction as the
explicit UX benchmark for this specific feature.

Decision:

Every waveform panel/lane, in all three layout modes (Grouped, Separate,
Custom), can be independently resized vertically by dragging a handle at
its bottom edge. This applies uniformly — the same handle mechanism,
height-clamping rule, and state model work identically regardless of
which layout mode is active, and regardless of how many channels a given
panel holds.

Confirmed as part of this same decision:

- **Height constraints** (this task's own §6 required a chosen,
  documented, tested minimum, with an optional maximum): minimum **100px**
  (chosen after inspecting `wwBuildLayout()`'s own fixed 44px top+bottom
  margin overhead and Separate mode's existing 140px default — a floor
  much lower would leave an unusable strip); maximum **600px** (a
  deliberate, generous, non-mandatory bound purely to prevent pathological
  single-panel dimensions, per this task's own guidance for the
  no-maximum case). Defaults match each mode's own pre-existing fixed CSS
  height (Grouped/Custom 260px, Separate 140px) so a new panel's first
  paint is unchanged from before this phase.
- **Height state model** (this task's own §13 required resolving "how
  should height behave when switching modes" cleanly): panel height is
  explicit application state (`ww.panelHeights`, keyed by the SAME
  `groupKey` the existing panel-derivation architecture already computes
  — no new "stable panel identity" concept was invented). A panel's
  remembered height survives round-tripping away from and back to the
  SAME layout mode (e.g. Separate → Grouped → Separate restores VA's own
  Separate height); different modes' groupKeys never collide (a Separate
  VA lane's height never leaks onto the Grouped Voltage panel); a
  brand-new groupKey always receives its mode's sensible default — no
  cross-mode height mapping was built.
- **Resizing is presentation-only**: `Plotly.Plots.resize()` is the only
  Plotly API ever called for a height change — no data refetch, no
  X/time viewport reset, no Y-range reset, no relayout-loop interaction.
  Verified directly, not just asserted.
- **Workspace/session-only persistence**: `ww.panelHeights` lives in
  memory for the current browser tab only, reset by a whole-workspace
  clear; no backend/database persistence was added. Individual channel/
  panel removal deliberately does not scrub a height entry — the same
  policy Phase 2C-C1 (DEC-027) already established for `ww.customGroups`,
  for the same reason (a channel re-added later naturally regains its old
  height).
- Detego's placement/feel (subtle discoverable handle, direct drag, clear
  vertical-resize cursor) was used as the interaction reference only — no
  Detego branding, colors, icons, or implementation were copied; the
  handle's own styling uses existing Oruxa theme tokens exclusively.

Reason:

The owner's own instructions opening this task are the explicit act of
requesting this feature next (ahead of digital channels), naming Detego
as the specific UX benchmark, and this task's own §6/§13 required
concrete, documented, tested choices (height bounds; cross-mode height
behavior) rather than leaving them open. Per this project's own
governance, resolving named required choices with an owner-directed
feature request is a decision worth recording, not merely an
implementation detail.

Alternatives considered:

Reading the rendered DOM height as the source of truth instead of
explicit JS state (rejected — this task's own §13 explicitly required
NOT treating rendered DOM height as the only source of truth, and DOM
height cannot survive a full `wwRebuildLayout()` teardown/recreate cycle
across a mode switch, which explicit state can); building a
cross-mode height-mapping system (e.g. deriving a Grouped panel's height
from the average of its member channels' Separate heights) (rejected —
this task's own §13 explicitly discouraged "complicated cross-mode
height mapping," and per-groupKey state already produces the desired
behavior with no mapping logic at all); adding `localStorage`
persistence for panel heights (rejected for this slice — not required,
judged unnecessary first-slice scope per this task's own
"do not overengineer" guidance; can be reconsidered later); relying
solely on Plotly's `responsive: true` auto-resize (ResizeObserver-driven)
instead of an explicit `Plotly.Plots.resize()` call (rejected as the sole
mechanism — an explicit, directly-triggered, testable call is more
predictable across browsers/Plotly versions than depending entirely on
internal auto-detection timing, though `responsive: true` itself remains
enabled as a redundant safety net, unchanged from every prior phase).

Impact:

- `frontend/index.html`: `WW_MIN_PANEL_HEIGHT`/`WW_MAX_PANEL_HEIGHT`/
  `WW_DEFAULT_PANEL_HEIGHT` constants; a `ww.panelHeights` Map plus
  `wwDefaultHeightForCurrentMode()`/`wwHeightForGroupKey()`/
  `wwClampPanelHeight()` helpers; `panel.height` added to the panel
  object; `wwSetPanelHeight()` and `wwWireResizeHandle()` (Pointer Events
  + Pointer Capture + `requestAnimationFrame` coalescing); a
  `.ww-resize-handle` element added to every panel's DOM
  (`wwCreatePanelDom()`) with its own CSS (theme-token-driven, unscoped
  to any one layout mode); `wwClearWorkspace()` extended to reset
  `ww.panelHeights`.
- No backend file changed; the Phase 2A waveform endpoint's contract and
  every prior phase's request/response shape are unchanged. No layout
  persistence beyond the current browser tab was added, matching the
  project's existing ephemeral-by-design principle (DEC-015).
- DEC-021 (shared workspace-level viewport), DEC-024–DEC-027 (panel
  architecture, Grouped/Separate/Custom modes, unified-canvas visual
  treatment) are all reaffirmed unweakened — resizing is a presentation-
  only layer on top of all of them, verified to interact with none of
  their mechanisms.
- **Digital-channel rendering, lane drag/reorder, drag-to-overlay/group,
  and backend layout persistence remain explicitly not started and not
  authorized by this decision.**

**Update (2026-08-15, Phase 2C-C2A, same day)**: the owner's manual UAT
of this decision's own implementation passed functionally (100–600px
bounds accepted as-is, unchanged), but observed a bearable, low-priority
live-resize lag. An investigation (code-path tracing plus jsdom
instrumentation with a simulated-cost Plotly mock, at multiple simulated
cost levels — no real browser was available or installed for this
one-off diagnostic) identified the cause: the cheap DOM height write and
the expensive `Plotly.Plots.resize()` call were bundled inside the same
synchronous `requestAnimationFrame` callback, so the browser could not
paint the panel's new size until Plotly's own redraw had finished, every
frame during a drag. A small, low-risk refinement was judged justified
against this decision's own established cost/benefit bar and
implemented: the cheap write (`wwSetPanelHeightImmediate`) now runs on
every raw `pointermove`, decoupled from the still-rAF-coalesced
`Plotly.Plots.resize()` call (`wwResizePanelPlot`) — confirmed
structurally to decouple the two (the height change becomes externally
observable before the corresponding Plotly call even starts, instead of
being indistinguishable from its finish time). Plotly call counts,
zero-refetch behavior, the 100–600px bounds, per-panel independence, and
all Grouped/Separate/Custom/synchronization/theme/crosshair behavior are
all unchanged and reconfirmed by test. This is a refinement of the same
resize-performance concern this decision already covers, not a new
architectural direction — no new decision entry was added, per
governance. See
[MIGRATION_PLAN.md — Phase 2C-C2A Investigation Record](MIGRATION_PLAN.md#phase-2c-c2a--panel-resize-responsiveness-investigation-2026-08-15).
Real-browser tactile confirmation of the improvement remains for owner
manual UAT — the jsdom evidence proves the mechanism was fixed, not the
felt result.

---

## DEC-029 — COMTRADE Absolute/Elapsed time-axis modes; Absolute is the default (Phase 2C-C3)

Date: 2026-08-15
Status: Approved
Source: explicit project-owner instructions opening the Phase 2C-C3 task
(2026-08-15), following the owner's own manual UAT of Phase 2C-C2A
(**passed** — resize lag reported improved, that issue closed), naming
this as the next feature ahead of digital channels.

Decision:

The waveform workspace gains a workspace-level (not per-panel) X-axis
time representation, selectable via a compact toolbar control: **Absolute
Time** (each sample's real recording timestamp, derived from the
backend's already-existing `timebase.start_time`) and **Elapsed Time**
(time from record start = 0, the exact pre-existing unlabeled behavior,
now made explicit). **Absolute Time is the default for COMTRADE.**

Confirmed as part of this same decision:

- **Trigger timestamp does NOT define the elapsed-time origin.** Sample
  0 always corresponds to `start_time`, never `trigger_time` — confirmed
  by direct investigation of the parser/domain layer and against real
  parsed COMTRADE metadata before any UI work began, per this task's own
  explicit mandate not to assume otherwise.
- **The shared physical viewport (DEC-021) remains authoritative in
  elapsed-seconds internally, permanently.** A time-mode switch is a
  presentation-only transform of already-loaded data at a single
  conversion boundary (`wwElapsedToPlotlyX`/`wwPlotlyXToElapsed`); the
  backend `waveform` API, the fetch pipeline, and the sync/broadcast
  logic are entirely unaware of time mode and unchanged by this
  decision. **Zero waveform refetches on a mode switch** — verified by
  test, not merely intended.
- **Zero backend changes.** `TimebaseOut` (`GET .../channels`) already
  exposed `start_time`/`trigger_time`/`timing_reference` before this
  pass — this entire feature is a frontend presentation transform.
- **Timezone handling**: both COMTRADE timestamps are timezone-naive as
  parsed by this codebase (no timezone field exists in the parser or
  schema) — the frontend never invents, assumes, or silently converts to
  browser-local time; all parsing/formatting uses only UTC-based
  arithmetic (`Date.UTC()`/`getUTC*()`), and the axis context is labeled
  neutrally ("Record time").
- **Source capability model**: Absolute is only offered when every
  currently-displayed channel's backend `timing_reference` field equals
  `"absolute"` and a recording-start timestamp exists; otherwise the
  toolbar falls back to Elapsed-only with the Absolute button visibly
  disabled — never a fake/non-functional option.
- **`Synthetic Elapsed Time` and `Sample Index` are reserved names** in
  the time-mode model, for possible future CSV/Excel timing work — **not
  implemented this phase**.
- **`ww.timeMode` persists across a workspace clear** — a viewing
  preference, the same policy already established for
  `ww.layoutMode`/`ww.dragMode`.
- **Multi-source limitation, explicitly not solved**: if channels from
  sources with different recording-start timestamps were ever displayed
  together, Absolute-mode labels would use only the first-displayed
  channel's origin. Documented as a known gap for future multi-source
  work, not addressed by this decision.

Reason:

The owner's own instructions opening this task are the explicit act of
requesting this feature next (ahead of digital channels), and this
task's own emphatic requirements (investigate timing semantics before
any UI work; never let trigger time silently redefine the axis; never
invent a timezone; preserve the shared viewport exactly across a mode
switch) are architectural commitments worth recording, not merely
implementation detail — consistent with this project's own governance
for owner-directed feature decisions (DEC-024–DEC-028 precedent).

Alternatives considered:

Elapsed Time as the default, with Absolute opt-in (rejected — this
task's own §2/§3 explicitly designated Absolute as the COMTRADE
default); deriving the Absolute origin from `trigger_time` instead of
`start_time` (rejected — this task's own §4/§9 explicitly warned against
this exact assumption, and the parser/DAT-format semantics confirm
sample 0 = `start_time` by COMTRADE spec definition, independent of
where the trigger falls); converting naive timestamps to the browser's
local timezone for display (rejected — this task's own §11 explicitly
forbids this; no timezone information exists to convert with in the
first place); maintaining two parallel authoritative viewport
representations, one elapsed and one absolute (rejected — this task's
own §7/§8 required a single conversion boundary with the existing
elapsed-seconds coordinate system remaining sole authority, avoiding
duplicated waveform data and any risk of the two representations
drifting out of sync); implementing Synthetic Elapsed Time or Sample
Index this phase (rejected — explicitly out of scope per this task's
own §31, reserved as names only for a clean future extension).

Impact:

- `frontend/index.html`: toolbar HTML for the Absolute/Elapsed toggle +
  date-context label; `WW_TIME_MODES`/`ww.timeMode` state;
  `channelCheckboxHtml`/`renderAnalogGroup`/`renderChannelTable` thread
  `timebase` so each channel carries `recordingStartTime`/
  `timingReference`; new helpers `wwParseNaiveTimestamp`,
  `wwFormatPlotlyDateString`, `wwTimeModesForChannel`,
  `wwAvailableTimeModes`, `wwWorkspaceRecordingStartMs`,
  `wwElapsedToPlotlyX`, `wwPlotlyXToElapsed`, `wwTimeAxisTickFormat`,
  `wwTimeAxisTitle`, `wwUpdateTimeModeContext`,
  `wwUpdateTimeModeControlAvailability`, `wwSetTimeMode`;
  `wwBuildTrace`/`wwBuildLayout`/`wwLoadChannelRange`/
  `wwWirePanelRelayout`/`wwApplyAndFetchViewport` made mode-aware;
  `wwUpdateBottomLaneAxis()` renamed to `wwApplyTimeAxisChrome()` (same
  Separate-only no-op guard for Grouped/Custom, now mode-aware title).
  No backend file changed. See
  [MIGRATION_PLAN.md — Phase 2C-C3 Record](MIGRATION_PLAN.md#phase-2c-c3--comtrade-time-axis-modes-2026-08-15).

**Update (2026-08-20) — see [DEC-042](#dec-042--absolute-and-elapsed-waveform-modes-share-numeric-elapsed-plotly-x-coordinates):**
the decision's elapsed-authority rule remains correct, but the original
implementation detail that converted Absolute-mode Plotly X coordinates into
date strings is superseded. Plotly now receives numeric elapsed seconds in
both Absolute and Elapsed modes; Absolute Time changes labels only.

---

## DEC-030 — Sticky shared waveform time-axis ruler, implemented as a lightweight trace-less Plotly instance (Phase 2C-C4)

Date: 2026-08-15
Status: Approved
Source: explicit project-owner instructions opening the Phase 2C-C4 task
(2026-08-15), following the owner's own manual UAT of Phase 2C-C3
(**passed** — Absolute Time correct, Elapsed Time correct, mode
switching preserves the physical window), identifying that with many
displayed channels the shared time-axis labels were only visible at the
very bottom of the panel stack.

Decision:

ONE Oruxa-owned, workspace-level sticky time-axis strip/ruler now stays
visible near the bottom of the viewport while vertically scrolling
through the waveform workspace, in all three layout modes. It is a
**presentation layer only** over the existing authoritative shared
viewport (DEC-021) and time-mode state (Phase 2C-C3, DEC-029) — it
never becomes an independent synchronization authority, never holds its
own viewport/mode state, and is **display-only** this slice (not
draggable/zoomable/pannable/selectable, no crosshair).

Confirmed as part of this same decision:

- **Implementation: a lightweight, trace-less Plotly instance**, not a
  hand-rolled SVG/canvas ruler. This task's own §25 explicitly invited
  evaluating this tradeoff. Chosen because: Plotly is already a page
  dependency (zero new weight); it lets the ruler call the EXACT same
  `wwTimeAxisTickFormat()` function every waveform panel already uses,
  guaranteeing identical tick selection/formatting/rollover handling by
  construction, with zero risk of a second, independently-drifting
  time-formatting implementation — the single thing this task's own
  instructions were most emphatic about avoiding. The empty (`[]`)
  traces array means it never fetches, holds, or renders channel data —
  it is not "another waveform chart."
- **Sticky mechanism: CSS `position: sticky; bottom: 0`**, not `fixed`
  and not a scroll-event listener. The ruler is a normal-flow sibling of
  `#wwPanels` inside `.workspace-section` (its containing block) — this
  is what makes it remain pinned to the viewport bottom only while part
  of the workspace is still below the viewport, and scroll away
  naturally once the whole workspace has been scrolled past, satisfying
  the explicit "must not permanently float over unrelated content"
  requirement using ordinary browser layout. Confirmed by test that
  dispatching scroll events causes zero JavaScript work (zero Plotly
  calls, zero waveform fetches).
- **Alignment**: a new shared constant, `WW_PANEL_MARGIN = { l: 55,
  r: 20 }`, is now the single source of truth for both `wwBuildLayout()`
  (every waveform panel) and the ruler's own margin — replacing what was
  previously a literal inlined only in `wwBuildLayout()`. Combined with
  matching CSS horizontal padding (14px, confirmed identical to
  `.ww-panel`'s own across every layout mode), this keeps tick positions
  pixel-aligned with every panel's plot area without any runtime
  measurement of Plotly's own rendered layout.
- **No new synchronization loop**: the ruler-update function
  (`wwSyncStickyRuler()`) is called only from the places that already
  mutate `ww.viewport`/`ww.timeMode` (the single viewport-mutation
  function every zoom/pan/Reset Time View funnels through, plus
  `wwSetTimeMode`) and the displayed-channel-count/theme-switch call
  sites — it never registers its own Plotly event listener, confirmed
  by test.
- **Separate mode's per-lane axis chrome changed**: every lane now
  suppresses its own tick labels/title (previously only the non-bottom
  lanes did, with the bottom lane keeping the one visible shared axis).
  The sticky ruler makes that lone remaining bottom-lane axis redundant.
  Judged low-risk: a single boolean-scope change in an already-existing,
  already-tested function.
- **Grouped/Custom panels' own per-panel axis labels are deliberately
  left UNCHANGED this slice** — every panel still shows its own full
  x-axis, which now visibly duplicates the sticky ruler whenever both
  are on screen simultaneously. This is a documented, known, INTENTIONAL
  gap, not an oversight: unlike Separate's uniform "one lane per
  channel" structure, Grouped/Custom has no single "bottom panel"
  concept, and panel count/order varies with channel grouping — treated
  as a materially larger restructuring than this task's own scope
  justified, per this task's own explicit permission to leave it
  documented for a later cleanup pass rather than force a fix now.

Reason:

The owner's own instructions opening this task are the explicit act of
requesting this feature next, with several requirements stated
emphatically enough (architecture must not create a second sync
authority; alignment is "critical"; must reuse Phase 2C-C3's own
formatting logic rather than build a second implementation) that they
constitute real architectural commitments worth recording, not merely
implementation detail — consistent with this project's own governance
for owner-directed feature decisions (DEC-024–DEC-029 precedent).

Alternatives considered:

A hand-rolled SVG/canvas axis with an independent "nice tick value"
algorithm (rejected — would need to reimplement Plotly's own tick-
selection logic to stay visually consistent with every panel, a second,
independently-drifting implementation of exactly what this task's own
instructions were most explicit about avoiding); `position: fixed`
instead of `position: sticky` (rejected — this task's own §4 explicitly
asked to avoid a globally fixed element "unless there is a strong
reason," and `position: sticky` achieves the same visible-while-
scrolling effect with the desired "releases once you scroll past the
workspace" behavior for free, via ordinary browser layout); a raw
`scroll` event listener repositioning the ruler manually (rejected —
this task's own §27 explicitly discouraged this when CSS sticky alone
can do the job, and it would add exactly the JavaScript-during-scroll
cost this task asked to avoid); making the sticky ruler itself
interactive (draggable/zoomable) in this slice (rejected — explicitly
out of scope per this task's own §11/§31, reserved for a future slice if
ever pursued); suppressing Grouped/Custom's own per-panel axis labels in
this same pass (rejected — judged a materially larger, riskier
restructuring than this task's own scope justified, per the explicit
"keep them temporarily and report the duplication" permission in §16).

Impact:

- `frontend/index.html`: `.ww-sticky-ruler`/`.ww-sticky-ruler-context`/
  `.ww-sticky-ruler-chart` CSS; `#wwStickyRuler`/`#wwStickyRulerContext`/
  `#wwStickyRulerChart` markup (sibling of `#wwPanels`); new
  `WW_PANEL_MARGIN` shared constant (also now used by `wwBuildLayout()`);
  `ww.rulerReady` state; new `wwSyncStickyRuler()`;
  `wwUpdateTimeModeContext()` extended to also drive the ruler's own
  context label; `wwApplyTimeAxisChrome()` changed (Separate mode
  suppresses every lane's own ticks/title now, not just the non-bottom
  ones); `wwApplyTheme()` extended to re-color the ruler. No backend
  file changed. See
  [MIGRATION_PLAN.md — Phase 2C-C4 Record](MIGRATION_PLAN.md#phase-2c-c4--sticky-shared-waveform-time-axis-2026-08-15).

**Update (2026-08-16, Phase 2C-C4A, cosmetic follow-up)**: the owner's
manual UAT of this decision's own implementation passed functionally
(sticky behavior, alignment, zoom/pan sync, Absolute/Elapsed switching,
resize interaction all confirmed working). The owner's next request was
a cosmetic title-placement refinement: a small title at the TOP of the
ruler (never under the ticks) — a fixed "Record time" for Absolute mode,
and a genuinely unit-aware "Time (ms)"/"Time (s)"/"Time (min)" for
Elapsed mode. Implementing the Elapsed title correctly required real
(not purely cosmetic) work: Phase 2C-C3's existing tick formatting never
actually switched units, only decimal precision, always in raw seconds
— so a naive title-only change would have produced exactly the "title
says ms, ticks show seconds" mismatch this follow-up task's own
instructions explicitly forbade. **Resolution**: one new shared function,
`wwStickyRulerElapsedUnit(spanSeconds)`, is now the single decision both
the title and the ruler's own tick values consult (a simple 3-tier
span-based rule: <1s → ms, <60s → s, ≥60s → min), with the ruler's own
independent numeric x-axis domain genuinely rescaled by the chosen
unit's constant factor. This rescale is scoped entirely to the ruler's
own Plotly instance — `ww.viewport`, `wwElapsedToPlotlyX()`, every real
waveform panel's own axis, and Phase 2C-C3's timing semantics are all
completely untouched, preserving this decision's own "presentation
layer only, never an independent authority" principle exactly. The
reasoning that a uniform multiplicative rescale preserves tick pixel-
position alignment (Plotly's own "nice round tick value" algorithm is
scale-covariant under a constant multiplier) was worked through
carefully but **could not be visually confirmed in this sandbox** — no
real browser is available — and is flagged explicitly for owner UAT.
This is a refinement of the same sticky-ruler feature this decision
already covers, not a new architectural direction — no new decision
entry was added, per governance. See
[MIGRATION_PLAN.md — Phase 2C-C4A Record](MIGRATION_PLAN.md#phase-2c-c4a--sticky-time-axis-title-placement-and-unit-label-2026-08-16).

**Update (2026-08-16, Phase 2C-C4B, cosmetic correction)**: the owner's
manual UAT of Phase 2C-C4A's own visual layout **failed** — the custom
DOM title (plus an Absolute-only date line, both placed above the
Plotly tick chart) produced a tall strip with a large blank vertical
gap, reading as an "information card" rather than a compact
conventional X-axis. The owner supplied a reference screenshot and an
exact desired layout: tick labels first, a small title directly below
them, no date inside the ruler at all. **Resolution**: the custom
`#wwStickyRulerTitle`/`#wwStickyRulerContext` DOM elements (and their
CSS) were deleted entirely; the ruler now sets `xaxis.title` directly
on its own Plotly layout — the exact same native mechanism every real
waveform panel already uses for its own title — which places the title
below the tick labels by Plotly's own convention, already proven
pixel-aligned in this codebase. The ruler's own margin changed to
`{t:2, b:34}` (reusing the real panels' own already-proven b:34 fit)
and its chart height reduced 46px→40px, bringing total ruler height
from ~63–80px down to ~43–45px. Absolute mode's wording changed to the
owner's exact specification, "Record Time" (capital T); the ruler no
longer shows any date text (the toolbar's own date-context label is
unaffected). The Elapsed unit-rescaling logic and its single-source-of-
truth principle from the entry above are completely unchanged — this
correction only affects HOW the resulting title text is rendered
(Plotly-native vs. custom DOM) and the chart's own compactness, not
what decides the text or values themselves. Still a refinement of the
same sticky-ruler feature — no new decision entry. See
[MIGRATION_PLAN.md — Phase 2C-C4B Record](MIGRATION_PLAN.md#phase-2c-c4b--compact-sticky-time-axis-layout-correction-2026-08-16).

---

## DEC-031 — Application shell architecture: Global Header, full-height Main Sidebar Menu, Work Area (Workspace Row + Bottom Status Bar) (Phase 3A)

Date: 2026-08-16
Status: Approved
Source: explicit project-owner instructions opening the Phase 3A task
(2026-08-16), with an owner correction to an earlier interpretation of
the shell geometry, plus two owner follow-up messages establishing the
responsive/small-screen strategy (tablet as adaptive secondary target,
phone as a simplified companion mode, desktop/laptop as the primary,
non-negotiable target).

Decision:

`oruxa_powerwave`'s frontend moves from a single centered page (`main {
max-width: 1100px; margin: 0 auto }`, the whole document scrolling
together) to a full-viewport application shell with this exact
structural hierarchy — a real DOM/CSS nesting, not a simulated one:

```
App
├── Global Header                      (#globalHeader, full width)
└── Body                                (#appBody)
    ├── Main Sidebar Menu               (#mainSidebarMenu, FULL Body height)
    └── Work Area                       (#workArea)
        ├── Workspace Row               (#workspaceRow)
        │   ├── Workspace Sidebar       (#workspaceSidebar, drag-resizable)
        │   └── Main Workspace          (#mainWorkspace)
        │       ├── Workspace Toolbar   (#wwToolbar, existing, relocated)
        │       └── Active View Area    (#activeViewArea)
        └── Bottom Status Bar           (#bottomStatusBar)
```

Confirmed as part of this same decision:

- **Main Sidebar Menu spans the FULL Body height** by construction, not
  by careful pixel matching: it and Work Area are the two direct flex
  children of `#appBody` (a flex row), so a flex column split ONE LEVEL
  DEEPER (inside Work Area, splitting Workspace Row from the Status Bar)
  is what confines the Status Bar to Work Area's own width — it can
  never render beneath Main Sidebar Menu, because it isn't a sibling of
  it in the DOM at all. This was the owner's own explicit correction to
  an earlier, wrong interpretation, and is the single most important
  geometry rule in this decision.
- **Main Sidebar Menu is collapsed/expanded via a TOGGLE, never freely
  drag-resizable** — a deliberately different interaction model from the
  Workspace Sidebar, which is drag-resizable and never has a
  collapsed/expanded state. These are two independent layout regions
  with two independent state models, on purpose (never coupled).
- **Workspace Sidebar is contextual to the active engineering
  workspace** (Sources/Channels/Import today; Values/Groups/Table
  controls later), explicitly NOT global application navigation — that
  role belongs to Main Sidebar Menu instead. Horizontally resizable via
  a small, REUSABLE split-pane helper (`shellCreateHorizontalSplit()`),
  not a one-off resize mechanism — the same function is intended to
  drive a future Waveform ⇆ Table split inside Main Workspace, called a
  second time with different arguments, not a reason to build a larger
  generic layout framework now.
- **Layout state is explicit, not DOM-derived**: Workspace Sidebar width
  (default 320px, min 240px, max 520px — fixed pixel bounds, not
  dynamically computed against the current window width; a documented,
  deliberate initial-phase simplification) persists to `localStorage`
  for the active session; Main Sidebar Menu's collapsed/expanded state
  is a separate, independently-persisted boolean. No backend
  persistence for either.
- **Active View concept**: `shell.activeView` (`"waveform"` | `"table"`
  | `"split"`) is app-shell state, kept deliberately separate from
  waveform-domain state (`ww`) — the shell never reads or writes `ww`
  directly; the reverse direction (waveform code calling a narrow shell
  setter like `shellUpdateStatusBarChannelCount()`) is the only coupling
  allowed, and even that is a one-way read, never a mutation of `ww`
  from shell code. Table and Split are structural placeholders only
  this phase — no fake grid data, no real Split rendering — proving the
  Active View Area can host a future mode without needing to be
  redesigned later.
- **Existing waveform functionality is relocated, not rewritten**: the
  entire Phase 2C waveform workspace (Grouped/Separate/Custom, Custom
  Groups editor, synchronized zoom/pan, Reset Time View, Autoscale Y,
  Absolute/Elapsed time modes, the sticky shared time-axis ruler,
  panel-height resizing, Light/Dark theme, crosshair) moved into the
  Active View Area's Waveform container with every existing element ID
  preserved — confirmed unchanged by the full existing jsdom regression
  suite (224 checks, the exact same pre-existing pass/fail counts as
  before this phase, zero new divergences).
- **Bottom Status Bar shows only real, already-available values**
  (workspace id, source station name, sample rate, duration, displayed-
  channel count) — sourced from data the app already fetches for other
  reasons (the same `renderChannels()` payload, and `ww.displayed.size`)
  — never a fabricated value for a feature that doesn't exist yet
  (Cursor A/B, Delta Cursor, fault/event state are explicitly deferred
  to documentation, not fake live UI).
- **Responsive strategy — desktop/laptop primary, tablet adaptive,
  phone a simplified companion mode, never mobile-first**: the shell
  defined above is unconditionally the default (no media query alters
  it). Two breakpoints adapt the SAME DOM/state, not separate markup:
  under ~900px, Main Sidebar Menu is forced to its collapsed icon rail
  and the Workspace Sidebar becomes a reopenable overlay drawer (pure
  CSS `position: absolute` against `#workspaceRow` itself, not `fixed`
  against the viewport — deliberately avoids needing to know the Global
  Header's own height); under ~640px, the header/status bar tighten
  further. Main Workspace (the waveform canvas) always receives the
  space freed by a collapsed/hidden secondary region — it is never
  itself the thing that shrinks first. A future Waveform ⇆ Table Split
  is expected to similarly avoid forcing an unusably narrow side-by-side
  layout at insufficient width, though the actual fallback behavior for
  that specific future feature is not decided now.

Reason:

The owner's own instructions opening this task are the explicit act of
requesting this shell (ahead of any Table/Split implementation), with
an owner CORRECTION to the shell geometry mid-specification (the
Main-Sidebar-Menu-vs-Status-Bar nesting) that this document exists
specifically to prevent from being silently re-litigated by a future
session — see [README.md — Conflict-resolution rules](README.md#conflict-resolution-rules).
Per this project's own governance, resolving an owner-corrected,
load-bearing structural decision is worth recording explicitly, not
left as implicit CSS.

Alternatives considered:

A full-width Status Bar beneath everything, including Main Sidebar Menu
(rejected — this was the owner's own explicitly corrected, INCORRECT
prior interpretation; the task's own instructions labeled this
structure "Incorrect" in so many words); coupling Main Sidebar Menu's
collapsed/expanded state to Workspace Sidebar width, e.g. auto-
collapsing one when the other resizes (rejected — the task's own
section 21 explicitly required these stay independent); a large,
generic, reusable layout/splitter framework covering arbitrary future
panel arrangements (rejected — explicitly out of proportion to this
phase's own "keep it small and understandable" instruction; a small
function reusable for exactly the two known future cases, Workspace
Sidebar and a future Waveform/Table split, is sufficient); dynamically
computing Workspace Sidebar's maximum width as a function of the
current window width rather than a fixed pixel cap (rejected for this
initial phase — judged more complexity than an INITIAL shell,
explicitly framed as subject to UAT-driven refinement, justified;
mitigated instead by the drawer-mode responsive fallback, which removes
the squeeze concern entirely at genuinely narrow widths); building a
fully polished phone-specific UI in this phase (rejected — the owner's
own explicit instruction: phone is a secondary companion/review mode,
not a target for full parity, and desktop workspace quality must not be
sacrificed to accommodate it).

Impact:

- `frontend/index.html`: full CSS restructuring (`#globalHeader`,
  `#appBody`, `#mainSidebarMenu`, `#workArea`, `#workspaceRow`,
  `#workspaceSidebar`, `.shell-split-handle`, `#mainWorkspace`,
  `#activeViewArea`, `.shell-view-placeholder`, `#bottomStatusBar`, plus
  two responsive media queries); HTML restructured to move existing
  Import/Sources/Channels panels into `#workspaceSidebar` and the
  existing waveform workspace into `#activeViewArea`'s `#viewWaveform`,
  with every existing element ID preserved; new `shell` state object,
  `shellCreateHorizontalSplit()`, `shellSetMainSidebarExpanded()`,
  `shellSetActiveView()`, `shellSetSidebarDrawerOpen()`,
  `shellOpenImport()`, `shellUpdateStatusBar()`,
  `shellUpdateStatusBarChannelCount()`. No backend file changed. See
  [MIGRATION_PLAN.md — Phase 3A Record](MIGRATION_PLAN.md#phase-3a--application-shell-redesign-foundation-2026-08-16).

**Update (2026-08-16, Phase 3A-UAT1, owner UAT bug fix)**: the owner's
manual UAT of this decision's own shell STRUCTURE passed, but found a
child-layout bug — the Plotly waveform canvas did not reflow when the
Workspace Sidebar widened, and could visually extend beyond its own
panel frame. Root cause: this decision's own original implementation
comment incorrectly asserted that Plotly's `responsive: true` config
would automatically detect this kind of resize; it does not — that
config reliably reacts to actual `window` resize events, not a
container that changed size because a sibling flex item (the Workspace
Sidebar) resized. The CSS `min-width: 0` chain introduced by this
decision was already correct at every level that mattered; only the
never-notified Plotly instance was the problem. Fixed by adding an
explicit, rAF-coalesced `Plotly.Plots.resize()` call
(`wwResizeAllVisiblePlots()`) triggered from the Workspace Sidebar's
own resize, Main Sidebar Menu's `transitionend` event, and window
resize (defensive). `WW_PANEL_MARGIN`, the sticky ruler's own
alignment mechanism, and every other Phase 3A structural element are
unaffected. This is a bug fix within the same decision's own
implementation, not a new architectural direction — no new decision
entry was added, per governance. See
[MIGRATION_PLAN.md — Phase 3A-UAT1 Record](MIGRATION_PLAN.md#phase-3a-uat1--responsive-waveform-width-reflow-2026-08-16).

---

## DEC-032 — Recordings page as a first-class application page; one recording = one logical event (CFG+DAT); session/workspace-backed, not a persistent cloud library (Phase 3B)

Date: 2026-08-16
Status: Approved
Source: explicit project-owner instructions opening the Phase 3B task
(2026-08-16), benchmarked against Detego's own Recordings page (layout
reference only, per DEC-020's Detego Benchmark Principle — no Detego
branding/colors/icons copied).

Decision:

`oruxa_powerwave` gains a dedicated **Recordings** page (heading
"Recording Events"), registered as a first-class Main Sidebar Menu
destination alongside the renamed **Waveform** page (`shell.currentPage`
= `"waveform"` | `"recordings"`, deliberately separate from
`shell.activeView`, which stays scoped to sub-views WITHIN the Waveform
page — Table/Split remain sub-views of waveform analysis, not top-level
pages). Confirmed as part of this same decision:

- **Page navigation never destroys or rebuilds the waveform analysis
  workspace.** `#workspaceRow` (the entire Workspace Sidebar + Main
  Workspace + every live Plotly instance) is only ever `hidden`, never
  removed/recreated, when navigating to Recordings — the exact same
  "hide, don't destroy" mechanism `shellSetActiveView()` already
  established for Table/Split in Phase 3A. `ww`'s own state (viewport,
  layout mode, Custom Groups, panel heights, time mode) is untouched by
  navigation; returning to Waveform schedules a Plotly resize pass
  (reusing Phase 3A-UAT1/UAT3's `wwScheduleResizeAllVisiblePlots()`) in
  case the available width changed while away, with zero waveform
  refetch — confirmed by test.
- **One logical recording = one CFG+DAT pair**, never two separate rows.
  This already held at the backend/API level before this decision (one
  `SourceMetadata`/`SourceSummaryOut` per imported COMTRADE source, both
  companion files listed under `original_filenames`) — this decision
  formalizes it as the FRONTEND'S recording abstraction too, deliberately
  described in terms general enough for future formats: a CSV file, or
  an Excel file, will each also be exactly one recording/event when
  those providers exist later.
- **No second, independently-drifting recording repository.** The
  Recordings page renders from the SAME `GET .../sources` response the
  Workspace Sidebar's own source list already fetches
  (`fetchSourcesList()`); a shared `refreshAllSourceViews()` keeps both
  presentations in sync at every point that actually changes the source
  set (upload success, remove, workspace reset).
- **The Recordings page is session/workspace-backed, not a persistent
  cloud recording library.** It reflects whatever the CURRENT
  browser/workspace session's `WorkspaceRegistry` holds — the same
  ephemeral-by-design in-memory model DEC-012/DEC-015/DEC-019 already
  established for the whole application. No database table, no
  object-storage retention, no user-account recording history, no
  upload history across sessions were added. UI wording was written to
  avoid implying otherwise.
- **One upload implementation.** The always-visible "Import COMTRADE
  Event" form that previously lived in the Workspace Sidebar was
  removed; its actual upload/validation logic was refactored (not
  duplicated) into one extensible "Upload Recording" modal, opened by
  the Recordings page's own "Upload New" button AND the Global Header's
  "Import" shortcut (which now navigates to Recordings and opens the
  same modal, rather than maintaining a second independent import path).
- **The upload modal is provider/format-driven, not hard-coded to
  COMTRADE**, via a small `RECORDING_FORMATS` definition (id, label,
  `enabled`, required files) the modal's file-input fields are rendered
  from. COMTRADE is the only `enabled: true` entry this phase — CSV and
  Excel are listed as real, visible, `disabled` `<option>`s (the same
  visible-but-disabled convention Phase 3A already established for
  Table/Tools/Reports in the Main Sidebar Menu), proving the
  architecture without pretending those formats already parse. No CSV
  or Excel parser was implemented; this is structural readiness only.
- **Backend change: additive only.** `SourceSummaryOut` gained
  `duration_seconds`/`sample_count` (both already computed and stored on
  `SourceMetadata` since Phase 2A — no new storage, no new computation,
  no change to any existing field) so the Recordings list's Duration
  column doesn't require a separate `.../channels` request per listed
  row. No new endpoint, no new table, no new persistence semantics.
- **Open / Analyse reuses `selectSource()` unchanged** (same
  parser/import semantics, never re-uploads, never creates a duplicate
  source) and navigates to Waveform — it does not auto-display any
  channels; the existing checkbox + "Add selected" step is unchanged.
  **Remove reuses the existing `requestRemoveSource()`/
  `performRemoveSource()` confirmation flow unchanged**, updating the
  Recordings list, the Workspace Sidebar's source list, and the
  waveform-displayed-channel state consistently from one call.

Reason:

The owner's own instructions opening this task are the explicit request
for this page, framed as "finish this area before introducing
additional features," with Detego's Recordings page named as the
layout/workflow benchmark (per the pre-existing DEC-020 Detego
Benchmark Principle) and an explicit, repeated instruction not to
silently change the project's existing no-persistent-event-storage
philosophy while doing so.

Alternatives considered:

A persistent, database-backed recording library surviving across
sessions (rejected — explicitly out of scope this phase per the task's
own instructions; a separate future product/architecture decision, not
one to back into via a UI feature); keeping the always-visible Workspace
Sidebar upload form AND adding a second upload modal (rejected — the
task's own explicit "one upload implementation only" instruction; two
equally-prominent flows would drift and confuse); building the upload
modal as COMTRADE-hard-coded with no format concept (rejected — the
task's own explicit forward-compatibility requirement for CSV/Excel,
even though neither is implemented now); fetching `.../channels` per row
to populate a Duration column instead of any backend change (rejected —
would multiply network calls just to render a list, contrary to this
phase's own "Recordings page should not refetch... merely by opening"
performance instruction; the additive `SourceSummaryOut` field change is
lower-risk and lower-cost); implementing folders/sharing/upload-history
now because Detego has them (rejected — the task's own explicit
instruction that folders are future work, and DEC-020 already
establishes that Detego is a benchmark, not a specification to copy
blindly); auto-navigating to Waveform immediately after a successful
upload (rejected — the task's own explicit preferred flow is
upload → list → user chooses Open/Analyse).

Impact:

- `frontend/index.html`: Main Sidebar Menu gains a "Recordings" item and
  renames "Workspace" to "Waveform"; new `#pageRecordings` page section
  (sibling of `#workspaceRow`), new `#uploadModalOverlay` (replacing the
  removed always-visible sidebar upload form); new `shell.currentPage`
  state, `shellSetCurrentPage()`, `shellSetStatusBarWaveformFieldsVisible()`,
  `RECORDING_FORMATS`, the upload-modal open/close/submit functions,
  `fetchSourcesList()`/`refreshAllSourceViews()`/`renderRecordingsTable()`/
  `recordingDisplayName()`/`openRecordingForAnalysis()`/
  `applyRecordingsSearchFilter()`. Two CSS `[hidden]`-override rules
  (`#workspaceRow[hidden]`, `#bottomStatusBar .shell-status-item[hidden]`)
  were added where needed — author CSS's own `display: flex` on those
  elements would otherwise beat the UA stylesheet's default `[hidden]`
  rule by origin, silently making `.hidden = true` a no-op.
- `backend/app/schemas/source.py`: `SourceSummaryOut` gained
  `duration_seconds`/`sample_count` (additive only).
  `backend/tests/test_sources_api.py`: two new/extended assertions for
  the new fields. 279 backend tests passing (278 + 1 new), zero
  regressions.
- See [MIGRATION_PLAN.md — Phase 3B Record](MIGRATION_PLAN.md#phase-3b--recordings-page-and-upload-workflow-2026-08-16).

---

## DEC-033 — Recordings is the application's default fresh-entry page; no separate landing/dashboard page (Phase 3B-UAT4)

Date: 2026-08-17
Status: Approved
Source: explicit project-owner instructions opening the Phase 3B-UAT4
task (2026-08-17).

Decision:

Visiting the application fresh (e.g. `https://dev.powerwave.oruxa.uk/`
with no prior in-session navigation) now shows the **Recordings** page
(heading "Recording Events") by default, not an empty Waveform
workspace. The intended product flow is:

```
Recording Events → choose/upload a recording → Open / Analyse → Waveform
```

not the reverse. Confirmed as part of this same decision:

- **No separate Powerwave landing/dashboard page was added.** Recording
  Events itself is the operational entry page — there is not yet enough
  meaningful dashboard content (no saved workspaces, persistent history,
  shared recordings, reports, or notifications) to justify an
  intermediate step before it. A future landing/dashboard page remains
  open for later consideration if/when the product gains that content,
  not decided now.
- **Implementation is the smallest robust option, not a routing
  framework.** The app has no URL-aware navigation at all; building one
  purely to satisfy "fresh entry = Recordings" was judged out of
  proportion to this change. The fix is a single default-state value —
  `shell.currentPage` now initializes to `"recordings"` instead of
  `"waveform"` — applied through the SAME `shellSetCurrentPage()`
  function every other in-app navigation already uses (not a separate
  "initial page" code path), with the static HTML's own default
  visibility/`aria-current` attributes kept hand-in-sync to avoid a
  visible flash to the old Waveform-default state before that Init call
  runs.
- **Fresh entry vs. in-session navigation stay distinct.** Only the
  DEFAULT/INITIAL state changed — `shellSetCurrentPage()` itself is
  completely unmodified, so the already-established "hide, don't
  destroy" behavior (Recordings ⇆ Waveform navigation never rebuilds or
  refetches the waveform workspace; viewport, layout mode, Custom
  Groups, panel heights, and time mode all survive any number of round
  trips) is unaffected — confirmed by test.
- **The Global Header stays general-purpose.** This decision did not
  add or remove any Global Header control on its own — Phase 3B-UAT2/
  UAT3 had already relocated all page-specific management actions
  (Import removed entirely; Start new workspace + Upload New living in
  the Recordings page's own header row) off the Global Header, which
  this decision's own product-flow framing endorses as the correct
  standing arrangement: the Global Header is reserved for genuinely
  global application/user-level functions (identity, future account/
  settings), not page-specific actions, regardless of which page
  happens to be the default.

Reason:

The owner's own instructions frame this as reflecting how an engineer
actually works: choosing or uploading the recording to analyse comes
first, opening it in Waveform comes second. Landing on an empty
Waveform workspace put the product's own natural entry step (browsing/
importing recordings) one unnecessary click away from where the session
actually starts.

Alternatives considered:

A dedicated Powerwave landing/dashboard page shown before Recordings
(rejected — explicitly out of scope per the owner's own instruction;
there is not yet enough real dashboard content to justify it, and
inventing placeholder dashboard content was explicitly disallowed); a
real URL-based router (`/`, `/recordings`, `/waveform` each resolving
independently, with `history.pushState`/`popstate` handling) (rejected
for this pass — the task's own explicit "do not build a routing
framework just for this if the current app does not need one"; the
single default-state change is sufficient for the stated requirement
and does not block a future router from being introduced when the
product actually needs shareable/bookmarkable URLs); defaulting
`shell.currentPage` in the JS state object alone without also updating
the static HTML defaults (considered, but rejected as less robust — it
would rely on script-execution-before-first-paint timing to avoid a
visible flash rather than guaranteeing it structurally).

Impact:

- `frontend/index.html`: `shell.currentPage`'s default value changed
  from `"waveform"` to `"recordings"`; `shellSetCurrentPage("recordings")`
  is now called explicitly near the start of Init (replacing a
  redundant unconditional trailing `refreshAllSourceViews()` call, so
  a fresh load still fetches the source list exactly once); the static
  HTML defaults for `#workspaceRow` (now `hidden`), `#pageRecordings`
  (no longer `hidden`), and the Main Sidebar Menu's `aria-current`
  attributes on `#mainNavWaveformBtn`/`#mainNavRecordingsBtn` were
  updated to match. No other function's behavior changed. No backend
  file touched.
- See [MIGRATION_PLAN.md — Phase 3B-UAT4 Record](MIGRATION_PLAN.md#phase-3b-uat4--recordings-as-default-entry-page-2026-08-17).

---

## DEC-034 — Digital channel rendering: shared batched full-record transition API; one shared multi-trace Plotly figure, not one instance per channel (Phase 4A)

Date: 2026-08-17
Status: Approved
Source: explicit project-owner instructions opening the Phase 4A task
(2026-08-17), pausing cosmetic UX work to return to core waveform
functionality — rendering COMTRADE digital (binary/state) channels
alongside the existing analog waveform architecture, with an explicit
directive to display ALL analog and digital channels by default after a
recording is opened and evaluate real performance/usability via owner
UAT before considering any default filtering.

Decision:

**Backend — a new batched, full-record digital-waveform endpoint,
architecturally distinct from the analog waveform endpoint:**

- `GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/digital-waveform?channel_names=A&channel_names=B...`
  (repeated query param) returns, per channel: `classification`,
  `normal_state`, `initial_state`, a sparse `transitions: [{time, state}]`
  list, `start_time`/`end_time`/`sample_count` — always the FULL record,
  never `point_budget`/range-scoped like the existing analog `.../waveform`
  endpoint (DEC-019). Reasoning: a digital channel's transition COUNT is
  inherently small/sparse regardless of total sample count (COMTRADE
  digital channels are step/state signals, not continuous analog
  waveforms), so full-record delivery is simultaneously the most
  truthful representation (zero risk of losing a real state transition,
  satisfying the owner's explicit "never downsample digital data" and
  "preserve exact transition timing" requirements) AND, in practice, the
  smallest payload — a point-budget/range-based contract modeled on
  analog would have added complexity for no real benefit here.
  `extract_digital_waveform()` (`app/services/waveform_service.py`)
  vectorizes transition-finding via `np.diff`, independent of raw sample
  count.
- **Classification is computed ONCE, at import time**, in
  `_build_source_metadata()` (`app/services/import_service.py`) —
  `classify_digital_channel()` (new `app/domain/digital_classification.py`,
  pure/stateless) implements the owner's exact required precedence:
  name contains "spare" (case-insensitive, anywhere) → **Spare**
  (takes precedence over any observed high state); else any non-zero
  sample across the FULL record → **Triggered** (a channel that starts
  high and never transitions is still Triggered — not defined as
  "contains a 0→1 transition"); else → **Never Triggered**. Stored on
  `DigitalChannelSummary`/`DigitalChannelOut` (`classification: str`),
  never re-derived from a full-record scan at request or render time —
  matching the established "compute once at import" pattern
  `duration_seconds`/`sampling_rates`/analog `engineering_type` already
  use.

**Frontend — ONE shared Plotly figure with many step traces, a
genuinely different rendering architecture from analog's own
one-Plotly-instance-per-panel model (DEC-024, DEC-026):**

- `wwRebuildDigitalChart()` renders every displayed digital channel as
  one `line_shape: "hv"` (true step, exact transition timing preserved)
  trace inside a SINGLE Plotly figure, at incrementing Y-axis lane
  offsets; Y-axis ticks ARE the (truncated) channel names via
  `tickmode: "array"` (full name always available per-trace via
  `hovertext`, since a native Plotly axis tick has no tooltip mechanism
  of its own); X-axis tick labels are suppressed entirely (the existing
  DEC-030 sticky ruler remains the one authoritative bottom time
  reference — no second/duplicated bottom axis). `fixedrange: true` on
  both axes — the digital chart never independently drives the shared
  viewport, only follows it, so it needs no relayout listener or
  feedback-loop guard. A single `Plotly.react`-based update path is
  reused for every change type (channel add/remove, viewport change,
  Absolute/Elapsed switch, theme switch) rather than three separately
  optimized paths, a deliberate simplification justified by digital
  trace data's inherently small size (sparse transitions, not dense
  samples).
- **Rejected: one Plotly instance per digital channel** — the same
  per-panel-instance approach analog already uses (DEC-024) — because a
  COMTRADE record may carry hundreds of digital channels, and the owner
  explicitly required them ALL displayed by default; hundreds of
  independent Plotly instances was judged a real, foreseeable
  performance risk not worth taking when a single shared figure serves
  every stated requirement (compact lanes, shared viewport, readable
  step transitions) without it.
- **Digital region placement**: a dedicated, independently
  vertically-scrollable region (`#wwDigitalRegion` → `#wwDigitalScroll`,
  fixed `max-height: 260px`) strictly below all analog panels and above
  the shared sticky ruler — the ruler itself is never nested inside the
  scrolling container, so it cannot scroll out of view. Digital lanes
  are NEVER mixed into analog panels, and remain in this one dedicated
  region regardless of the analog Grouped/Separate/Custom layout mode
  (DEC-025/DEC-027) — those three modes continue to govern ONLY analog
  arrangement.
- **Default-all-display, scoped per source-open, not per navigation**
  (**Superseded 2026-08-19 by [DEC-038](#dec-038--waveform-channels-default-to-hidden-on-open-group-level-showhide-controls-added-phase-4a-uat9);
  see that entry for the current behaviour. The rest of this decision —
  endpoint architecture, shared Plotly figure, classification precedence,
  digital region placement — is unaffected and remains current.**):
  `ww.sourceDefaultsApplied: Set<sourceId>`, checked/set only inside
  `selectSource()`, reset only by `wwClearWorkspace()`. A genuinely new
  source-open displays every analog AND every digital channel (same
  policy for both — the owner was explicit that analog and digital must
  not get different default policies); manually hiding/removing a
  channel afterward is never undone merely by navigating
  Waveform → Recordings → Waveform and re-opening the same already-open
  recording. This is a deliberate, owner-directed UAT experiment (owner's
  own words: "do not prematurely optimize the product behavior by hiding
  channels automatically") — not a claim that this scales indefinitely;
  see the Phase 4A implementation record's own performance section.
- **Per-lane removal**: digital lanes have no individual DOM row (one
  shared Plotly figure, Y-axis-tick labels, not real per-channel
  elements), so a `plotly_click` listener on the digital chart (wired
  once, re-deriving the current sorted entry list fresh on every click
  so `curveNumber` always maps correctly even as the displayed set
  changes) removes the clicked lane's channel via the same
  `wwRemoveDigitalChannelByKey()` used by the workspace-reset/
  source-removal paths — keeping "hide/remove/re-add" meaningful for
  digital the same way analog's per-panel legend remove button already
  is, per this task's own explicit requirement that channel-visibility
  interaction stay meaningful for both kinds.

Reason:

The owner's own task-opening instructions are the explicit act of
requesting digital-channel rendering next, with several requirements
stated prescriptively enough (full-resolution transition timing must
never be lost; hundreds of digital channels must not create hundreds of
Plotly instances without first analysing the performance impact; digital
must share the exact analog X viewport with no second synchronization
authority; classification precedence and display ordering are given as
exact, testable rules) that they constitute real architectural
commitments worth recording — consistent with this project's own
governance for owner-directed feature decisions (DEC-024–DEC-030
precedent), and explicitly required by this task's own "architecture
decision threshold" instruction (report + record rather than bury a
genuinely new API/rendering pattern inside implementation).

Alternatives considered:

- **One Plotly instance per digital channel** (rejected — see above;
  the direct opposite of what DEC-024/026 established for analog would
  have been reused unexamined, without regard for digital's very
  different potential channel count).
- **A range/`point_budget`-scoped digital-waveform endpoint, mirroring
  the analog contract exactly** (considered, rejected — digital
  transition data is inherently sparse regardless of sample count, so a
  full-record response is both simpler and, in the vast majority of
  real recordings, smaller than a range-scoped one; it also trivially
  guarantees zero data loss across a zoom, satisfying the "never
  downsample digital data" requirement without needing separate
  full-resolution-vs-display-representation bookkeeping the way analog's
  min/max envelope logic (DEC-019) needs).
- **A separate DOM label column instead of Plotly Y-axis ticks for
  channel names** (considered — would have made the "full name via
  hover" requirement moot since a real DOM element can just show the
  full name — but rejected in favor of keeping the digital chart a
  single self-contained Plotly figure, avoiding a second layout system
  that would need to stay pixel-aligned with the chart's own lane rows
  on every resize/theme change).
- **Automatically hiding Spare (or any group) by default** (explicitly
  rejected — the owner's own instruction was to observe real UAT
  evidence before making that product decision, not to pre-empt it).

Impact:

- New backend files: `app/domain/digital_classification.py`,
  `app/schemas/digital_waveform.py`. Modified:
  `app/domain/source.py` (`DigitalChannelSummary.classification`),
  `app/schemas/source.py` (`DigitalChannelOut.classification`),
  `app/services/import_service.py` (classify once at import),
  `app/services/waveform_service.py` (`extract_digital_waveform`),
  `app/services/errors.py` (`ChannelNotDigitalError`),
  `app/api/v1/sources.py` (new endpoint). New tests:
  `backend/tests/test_digital_classification.py` (17 cases),
  `backend/tests/test_digital_waveform_api.py` (8 cases).
- `frontend/index.html`: new digital-workspace state
  (`ww.digitalDisplayed`, `ww.digitalChartReady`, `ww.digitalClickWired`,
  `ww.sourceDefaultsApplied`), new DOM region, new CSS, and the digital
  add/remove/rebuild/sort functions described above; the existing
  analog checkbox/"Add selected"/"Clear selection" UI now acts on
  whichever kind(s) currently have checkboxes checked, via a second,
  parallel `selectedDigitalChannels` map (never merged with the
  existing analog-only `selectedChannels`). New dedicated test coverage:
  `phase4a_check.mjs` (not committed — this project's established
  scratch-verification convention, see MIGRATION_PLAN.md's own Phase
  4A record for the full test list).
- See [MIGRATION_PLAN.md — Phase 4A Implementation Record](MIGRATION_PLAN.md#phase-4a--digital-channels-rendering-implementation-record-2026-08-17).

---

## DEC-035 — Analog channel visibility is workspace-global; layout mode governs arrangement only, never visibility (Phase 4A-UAT6)

Date: 2026-08-19
Status: Approved
Source: explicit project-owner UAT feedback (2026-08-19) — hiding an
analog channel while in one layout mode (Grouped) was observed to not
consistently persist when switching to another (Separate/Custom); the
owner's own task text states the required rule verbatim ("CHANNEL
VISIBILITY = global workspace state. LAYOUT MODE = presentation/
arrangement of currently-visible channels... Switching layout modes must
never implicitly re-enable it") and explicitly asked for a DECISION entry
if this rises to architecture/state-model weight.

Decision:

**Channel visibility and layout mode are two independent axes of state,
never conflated:**

- `ww.displayed` (pre-existing since Phase 2C-A) is confirmed and
  formalized as the ONE authoritative "is this analog channel currently
  visible" state — global across the whole workspace, never
  per-layout-mode. A new helper, `wwIsAnalogChannelVisible(sourceId,
  channelName)`, wraps the existing `ww.displayed.has(wwChannelKey(...))`
  check so call sites read as intent, matching the owner's own requested
  naming; it introduces no new/parallel state.
- `wwRebuildLayout()` (pre-existing) already derives every layout
  renderer's panels from this SAME flat `ww.displayed` set, intersected
  with that mode's own grouping rule (`wwPanelGroupKeyFor()`) — Grouped
  by `engineering_type`, Separate by channel identity (one lane each),
  Custom by `ww.customGroups` membership (auto-solo when unassigned).
  There is deliberately no second Grouped-visible/Separate-visible/
  Custom-visible map to keep in sync — the rejected alternative this
  decision explicitly forecloses for all future waveform work.
- Direct verification (dedicated jsdom reproduction, `frontend`
  regression suite) confirmed the simple "hide in Grouped → switch to
  Separate/Custom" flow was ALREADY correct against this architecture —
  no separate bug existed there. The one CONCRETE, reproducible violation
  found was in the Custom Groups editor: `wwOpenGroupEditor()` seeded its
  working copy filtered to only currently-displayed channels, so a
  hidden group member was silently and PERMANENTLY dropped from
  `ww.customGroups` the next time the editor was opened and Applied
  (even without touching that channel) — conflating "hidden" with
  "unassign from group," a direct violation of "group membership !=
  visibility." Fixed by no longer filtering at open time; membership is
  preserved in full regardless of a member's current visibility.
- **Group membership metadata now survives a channel being hidden**: a
  new `ww.channelMeta: Map<"sourceId::channelName", {sourceId,
  sourceName, channelName, unit, engineeringType}>`, same lifecycle
  policy as `ww.channelColors`/`ww.customGroups`/`ww.panelHeights`
  (populated on every add, never deleted by hide/remove, cleared only by
  `wwClearWorkspace()`). This exists purely so the Custom Groups editor
  can still describe a hidden member's name/unit (rendered dimmed, via a
  new `.group-chip--hidden` CSS class) without needing that channel to be
  in `ww.displayed` — visibility state and display metadata are
  explicitly two different concerns now, not implicitly coupled via
  "is it currently in `ww.displayed`."
- Re-enabling a previously-hidden channel (from the sidebar, or via a
  Separate-mode lane's own local remove, which already routed through
  the same `wwRemoveChannelByKey()`/`wwAddSelectedChannels()` global
  paths before this decision) restores it into whichever Custom Group
  last claimed it — never auto-solo — and reuses its existing
  `wwColorForChannel()` color, never reassigning one.

Reason: a channel's visibility is a property of the ENGINEER'S CURRENT
VIEWING DECISION (workspace-scoped), not a property of any one
arrangement of that workspace. Letting layout mode implicitly own
visibility — even accidentally, via a UI feature that only LOOKED at
currently-visible channels and silently forgot the rest — breaks the
owner's basic trust that hiding a channel is a durable action, not a
per-view toggle that quietly resets itself.

Alternatives considered:

- **A separate visible-state map per layout mode** (Grouped-visible/
  Separate-visible/Custom-visible) — explicitly rejected by the owner's
  own task text ("the latter is explicitly rejected") and would have
  been a straightforward way to REINTRODUCE exactly the class of bug
  this decision fixes, for any future feature that touches per-mode
  state.
- **Deleting a hidden channel from its Custom Group entirely (treating
  hide as unassign)** — rejected; this was the ACTUAL prior (buggy)
  behavior of the group editor before this fix, and it violates the
  owner's explicit "membership != visibility, do not delete from the
  Custom Group definition" instruction.
- **Caching a hidden channel's already-fetched waveform data for reuse
  on re-enable** — considered (section 19 of the owner's own task text
  raised it) but not implemented: existing fetch/cache semantics
  (refetch on every add, established since Phase 2B) are preserved
  unchanged, per the same task text's own "preserve current fetch/cache
  semantics unless a correction is necessary" — introducing a new cache
  layer was judged out of scope for a visibility-consistency fix.

Impact:

- `frontend/index.html` only: `wwIsAnalogChannelVisible()` (new),
  `ww.channelMeta` (new map + population in `wwAddSelectedChannels()` +
  clearing in `wwClearWorkspace()`), `wwOpenGroupEditor()`/
  `wwRenderGroupEditor()` (membership preservation fix), `.group-chip--hidden`
  CSS (new). `analogChannelRowAttrs()`/`wwSyncChannelBrowserDisplayState()`
  refactored to call the new helper (no behavior change). No backend
  file touched.
- New dedicated `phase4a_uat6_check.mjs` (scratch convention, not
  committed, 13 checks) covering the cross-mode visibility matrix
  (A-F from the owner's own task text), state persistence across
  layout/time-mode/navigation, source isolation, and digital isolation.
- **Separately discovered, out-of-scope pre-existing bug, NOT fixed by
  this decision** (RESOLVED — see "UAT7 resolution" below):
  `wwAddSelectedChannels()` can double-invoke `Plotly.addTraces()` for
  the 2nd..Nth channel of a brand-new panel when 2+ new channels are
  added in a single batch call destined for the same group (the most
  common real trigger being default-display-on-open for a source with
  2+ channels sharing one `engineering_type`) — `isNewPanel` is computed
  per-meta within the SAME batch loop, so a panel created moments
  earlier by an EARLIER meta in that same batch is incorrectly treated
  as "already existed before this call" for every later meta that joins
  it, triggering a redundant `addTraces` on top of the trace `newPlot`
  already drew. Flagged for the owner per this project's own
  change-governance process (issue/evidence/proposed fix/benefits/
  risks/impact) rather than fixed here, since it is a
  rendering-duplication concern unrelated to visibility state and this
  decision's own scope.
- See [MIGRATION_PLAN.md — Phase 4A-UAT6 Record](MIGRATION_PLAN.md#phase-4a-uat6--global-analog-channel-visibility-across-layout-modes-2026-08-19).

**UAT7 resolution (2026-08-19, owner-approved follow-up, no new DECISION
entry needed — same root cause, same architecture, a rendering-layer
correction only):** confirmed via a direct jsdom reproduction against
the code exactly as this decision left it (new empty Grouped panel +
A/B/C added in one `wwAddSelectedChannels()` batch produced 5 traces —
`A, B, C, B, C` — not 3; confirmed exactly 3 waveform network requests
in the same batch, proving the duplication was rendering-only, never a
duplicate fetch). Root cause exactly as diagnosed above. Fixed by
changing the second loop's gating condition from the per-meta
`isNewPanel` flag to membership in `newlyCreatedPanels` (already
correctly built, just not consulted at the right point) — a channel
whose panel is in `newlyCreatedPanels` is fully drawn by the
`wwInitPanelPlot()` loop immediately above (single clear owner: **new**
panels' complete trace set), and is now correctly skipped by the
incremental `wwAddTraceToPanel()` loop (single clear owner:
**pre-existing** panels' incremental additions) — the two ownership
paths can no longer both draw the same channel. Also added: a stable
per-trace `meta: wwChannelKey(sourceId, channelName)` field (Plotly's
own documented metadata property, never used for rendering) on every
built trace, and an on-demand console diagnostic,
`wwDiagnoseDuplicateAnalogTraces()`, mirroring the established
`wwDiagnoseDigitalAlignment()` (Phase 4A-UAT2) pattern. New dedicated
`phase4a_uat7_check.mjs` (18 checks) — including the exact regression
case, confirmed to genuinely fail against pre-fix code (14 of 18 checks
failed) before the fix and pass after. Full existing frontend
regression suite: unchanged at the established 18-failure baseline;
backend 321/321 unchanged. See
[MIGRATION_PLAN.md — Phase 4A-UAT7 Record](MIGRATION_PLAN.md#phase-4a-uat7--fix-duplicate-analog-trace-rendering-2026-08-19).

---

## DEC-036 — DEV deployment is automatic after CI succeeds on main; PROD remains fully manual

Date: 2026-08-19
Status: Approved
Source: explicit owner instruction (2026-08-19), following a requested
investigation into why pushes to `main` no longer auto-deployed DEV (the
owner recalled this working early in the project). The investigation
found the original `deploy.yml` (commit `b6dba53`, 2026-08-09) DID trigger
on `push: branches: [main]`; that trigger was deliberately replaced with
`workflow_dispatch` + a `dev`/`prod` target choice input the same day
(commit `af0c78a`), and formalized five days later as DEC-003. The owner,
on reviewing that history, approved restoring automatic DEV deployment —
scoped narrowly and safely — rather than reverting to the original
trigger.

Decision:

- **A routine push/merge to `main` automatically deploys DEV**, but only
  after the "CI" workflow has completed on that exact commit with
  `conclusion == success`. A commit that fails CI (or whose CI run is
  cancelled) is never auto-deployed.
- **A routine push/merge to `main` NEVER deploys PROD**, under any
  circumstance, by construction (see "DEV isolation" below) — not merely
  by convention.
- **PROD always requires an explicit, manual `workflow_dispatch`** —
  unchanged from DEC-003.
- **The existing manual `deploy.yml` (`workflow_dispatch`, `dev`/`prod`
  choice) remains fully available, unchanged, as the fallback path for
  DEV** (e.g. re-deploying an older commit, redeploying after a
  transient VPS issue, or deploying DEV without waiting for a fresh push)
  **and remains the only way to reach PROD.**

### Architecture

New, separate `.github/workflows/deploy-dev.yml` — `deploy.yml` itself is
untouched (verified: zero diff).

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    if: github.event.workflow_run.conclusion == 'success'
    environment: dev
    # APP_VERSION: ${{ github.event.workflow_run.head_sha }}
```

**Why `workflow_run`, not `push` on the new file directly**: a `push`
trigger on `deploy-dev.yml` itself would start deployment in *parallel*
with CI, not *after* it — exactly the race condition section 10 of the
owner's own task text explicitly forbade ("Do not create a race where
deployment begins before CI has validated the commit"). `workflow_run`
only fires once GitHub has recorded the referenced workflow ("CI",
matched by exact `name:` string) as fully `completed` for that specific
run, which structurally cannot happen before CI itself has finished.

**CI gating, precisely**: the `workflow_run` event fires for EVERY
completion of CI on `main` (success, failure, or cancelled alike) — the
job-level `if: github.event.workflow_run.conclusion == 'success'` is
what turns "CI finished" into "CI passed." A failing commit still
triggers this workflow, but its one job is skipped, never deploying a
red build.

**Exact-SHA guarantee (section 11/12 of the owner's task text)**:
`github.event.workflow_run.head_sha` is the exact commit CI validated —
deliberately NOT `github.sha`, which in a `workflow_run`-triggered run
reflects this (unrelated) workflow's own default-branch checkout and is
not guaranteed to equal the commit that triggered the run, especially if
another push lands in the gap between CI completing and this workflow
starting. That SHA becomes `APP_VERSION`, passed through unchanged to
`scripts/deploy.sh` exactly as the manual path already does — preserving
the existing build-provenance chain (frontend `buildVersion()` == backend
`/health.git_sha` == this exact deployed commit, Phase 4A-UAT3) with no
new mechanism.

### DEV isolation (why this cannot deploy PROD)

`deploy-dev.yml` has no `target`/environment input of any kind — no
`inputs:` block exists at all under `workflow_run:` (GitHub does not
even populate `inputs.*` for non-`workflow_dispatch` events). Every value
that, in the manual `deploy.yml`, is selected via `${{ inputs.target }}`
is instead the **literal string `"dev"`**, appearing three places:
`environment: dev` (job-level), `TARGET=dev` (the SSH command passed to
`scripts/deploy.sh`), and the shared `concurrency.group:
powerwave-deploy-dev`. There is no expression, variable, or code path in
this file capable of evaluating to `prod` — it is not merely configured
for dev, it is structurally incapable of targeting anything else.

The concurrency group deliberately matches what `deploy.yml`'s own
`powerwave-deploy-${{ inputs.target }}` resolves to when a human manually
dispatches `target: dev` — so a manual DEV deploy and an automatic one
can never run concurrently against the same VPS path (queued, not
cancelled, matching the existing "a half-applied deployment is worse than
a slow one" policy).

Reason:
The owner's own explanation for approving this: routine DEV deployment
after every merge is valuable feedback (matches the original, pre-DEC-003
intent) and is safe to automate now that it can be gated on CI and
structurally prevented from ever reaching PROD — neither of which was
true of the original 2026-08-09 `push`-triggered workflow (which had no
CI gate and, more importantly, predates the single dev/prod-selectable
`deploy.yml` entirely, so the "could this resolve to prod" question never
even applied to it).

Alternatives considered:

- **A bare `push: branches: [main]` trigger added directly to the
  existing `deploy.yml`** — rejected: `deploy.yml`'s steps all read
  `${{ inputs.target }}`, which is only populated for `workflow_dispatch`
  events; a push-triggered run would hit an empty/undefined target,
  which is exactly the kind of subtle, unpredictable risk the owner's own
  task text warned against introducing carelessly into a workflow also
  capable of deploying PROD.
- **A reusable workflow (`workflow_call`) shared between `deploy.yml`
  and `deploy-dev.yml`** — considered, rejected as unnecessary
  abstraction for this scope: it would still require SOME mechanism to
  fix the reused workflow's own target to `dev` for the automatic
  caller, and a small amount of structural duplication (the SSH/deploy
  steps, ~25 lines) is a smaller, more auditable risk than introducing a
  shared workflow that a future change could accidentally invoke with an
  unsafe input.
- **Re-running the backend test suite again inside `deploy-dev.yml`
  itself** (mirroring `deploy.yml`'s own `needs: test` job) — rejected:
  CI's own `test` job already ran the identical suite against this exact
  SHA, and the `if: conclusion == 'success'` gate already requires that
  to have passed; re-running it would be redundant work, not additional
  safety.

Impact:

- New `.github/workflows/deploy-dev.yml`. `deploy.yml` unchanged (byte-
  for-byte, verified via diff).
- `docs/project-memory/DECISIONS.md` (this entry; DEC-003 annotated with
  a pointer, not rewritten or marked Superseded — most of DEC-003 remains
  in force verbatim), `CURRENT_STATE.md`, `MIGRATION_PLAN.md`,
  `HANDOFF.md`, `docs/development/development-workflow.md` all updated to
  describe the new automatic-DEV / manual-PROD reality.
  `AGENTS.md`'s existing "Deployment is manual. Do not deploy to
  production unless explicitly asked." already only names PROD
  explicitly — read literally it was already compatible with this
  decision, so it was left as-is rather than reworded.
- **GitHub Environment protection** (required reviewers, branch
  restrictions on the `prod` environment) is a repository-UI setting this
  agent cannot inspect or configure from a local clone — flagged for the
  owner to independently confirm the `prod` GitHub Environment still (or
  now) has appropriate protection rules; this decision's own code-level
  guarantee (no `target` expression, hardcoded `dev` throughout
  `deploy-dev.yml`) does not depend on that UI setting, but defense in
  depth is still worth the owner's own five-minute check.
- See [MIGRATION_PLAN.md — CI/CD: Automatic DEV Deployment After CI](MIGRATION_PLAN.md#cicd--automatic-dev-deployment-after-ci-2026-08-19).

---

## DEC-037 — Waveform time-domain state is source-aware: source bounds, workspace bounds, and viewport are distinct (Phase 4A-UAT10)

Date: 2026-08-19
Status: Approved
Source: explicit project-owner approval in the Phase 4A-UAT10 task arising
from "COMTRADE Duration Investigation — Part 2".

Decision:
The waveform workspace separates time-domain state into three concepts:

- **Source bounds** — each recording's true native elapsed extent, keyed by
  stable `source_id` and supplied by backend timebase metadata.
- **Workspace bounds** — the derived min/max union of the currently
  participating source set.
- **Viewport** — the user's current zoom/pan window inside workspace bounds.

`Reset Time View` restores the derived workspace bounds. A waveform response,
an analog channel, a digital channel, or the first request to finish must never
be promoted into a later source's full-record time authority. Absolute/Elapsed
remains presentation-only over the same internal elapsed coordinate system.

Reason:
Owner UAT exposed a real stale-state bug: one COMTRADE source reported
`7.020 s` in source metadata while the waveform and Reset Time View showed
only approximately `0 -> 1.3 s`. Investigation found the backend duration
path and waveform endpoint both use the retained source time column; the
visible mismatch came from frontend `ww.recordBounds`/`ww.viewport` being
workspace-global mutable state without source ownership, so a newly opened
recording could inherit a previous source's bounds.

Alternatives considered:

- Keep `ww.recordBounds` as the full-record authority and clear it on source
  switch only — rejected as too narrow; it preserves the same conflation that
  caused the bug and does not prepare for multi-source comparison.
- Infer frontend bounds as `0 -> duration_seconds` only — rejected as the
  primary authority because backend already owns the engineering time axis;
  the frontend may use that shape only as a legacy additive-schema fallback.
- Implement cross-source synchronization/alignment now — explicitly rejected
  by the owner for this phase.

Impact:

- Backend source/timebase metadata exposes explicit elapsed start/end seconds
  in addition to duration.
- Frontend stores source bounds in `ww.sourceBounds`, derives
  `ww.workspaceBounds`, and keeps `ww.viewport` as user view only.
- Zero-channel source-open can still establish correct time bounds without
  rendering any analog or digital waveform.
- Digital-only displays use the same workspace bounds; analog is not a timing
  authority.
- This is synchronization-ready: a future phase can introduce an alignment
  offset between source-native bounds and aligned workspace bounds, but no
  timestamp alignment, trigger matching, correlation, manual offset controls,
  or resampling is implemented by this decision.
- See [MIGRATION_PLAN.md — Phase 4A-UAT10](MIGRATION_PLAN.md#phase-4a-uat10--source-aware-time-bounds-2026-08-19).

---

## DEC-038 — Waveform channels default to hidden on open; group-level Show/Hide controls added (Phase 4A-UAT9)

Date: 2026-08-19
Status: Approved
Source: explicit project-owner instruction, delivered as the Phase 4A-UAT9
task, directing evaluation of real UAT evidence gathered under DEC-034's
"display everything by default" experiment before deciding the product's
lasting default.

Decision:

**Waveform channels are opt-in by default to reduce initial rendering
cost. Group-level visibility controls allow efficient bulk display/hide.**

Concretely:

- Opening a recording (a genuinely new source or a fresh workspace)
  displays **zero** analog channels and **zero** digital channels.
  `ww.displayed` and `ww.digitalDisplayed` both start empty; no waveform
  data is fetched merely by opening a source.
- Every analog and digital channel row in the sidebar starts
  deactivated: `aria-pressed="false"`, 25% opacity (`.channel-row--hidden`),
  same visual/interaction language DEC-034/UAT5/UAT8 already established
  for an explicitly-hidden row — there is no separate "default" visual
  state.
- Each engineering-classification subgroup (analog: Voltage, Current,
  Power, Frequency, ROCOF, Undefined, etc.; digital: Triggered, Never
  Triggered, Spare) gained a compact **Show all** / **Hide all** toggle
  on its own group header, computed live from the existing per-row
  `aria-pressed` state (none/partial visible → "Show all"; all visible →
  "Hide all") — no separate group-selection state is stored anywhere.
  Toggling a group is one batched update (one `Plotly.newPlot`/
  `deleteTraces` pass per affected panel), not N individual per-channel
  rebuilds.
- Once the engineer manually shows or hides a channel or group — by
  either the sidebar or a Separate-mode lane's own remove control — that
  choice persists exactly as DEC-034/DEC-035 already required: surviving
  layout-mode switching (Grouped/Separate/Custom), Absolute/Elapsed
  switching, and Waveform ↔ Recordings navigation while the same source
  stays open. Only a genuinely new source-open or a fresh workspace
  resets to zero again.
- Custom Group membership (`ww.customGroups`) remains completely
  independent of visibility (DEC-035); hiding a group member never
  drops it from its group.

Reason:

DEC-034 explicitly scoped "display everything by default" as a
deliberate, time-boxed UAT experiment, not a permanent product
commitment ("not a claim that this scales indefinitely"). Owner UAT
against that experiment showed the default-all-display cost is real and
avoidable: every source-open unconditionally fetched and rendered every
analog and digital channel's full waveform data before the engineer had
chosen to look at any of it, regardless of how many of a recording's
channels the engineer actually cared about in a given session. Group-level
Show all/Hide all replaces the removed "select everything up front" cost
with an explicit, still-efficient bulk action the engineer reaches for
only when they actually want a whole group.

Alternatives considered:

- **Keep default-all-display, add a way to hide unwanted channels faster**
  — rejected; it does not address the real cost, which is the unconditional
  fetch/render of every channel on every source-open, not merely the
  effort of hiding channels afterward.
- **Default some groups visible (e.g. Voltage/Current) and others hidden**
  — rejected; an inconsistent default is harder to reason about than a
  single "nothing until you choose" rule, and the owner's original
  requirement that analog and digital never get different default
  policies (DEC-034) still applies by extension.
- **Pre-fetch waveform data in the background for instant display on
  first click, without rendering it** — rejected as out of scope; this
  decision addresses the render/fetch policy only, not a caching
  strategy, and would reintroduce the same unconditional-fetch cost this
  decision removes.

Impact:

- Supersedes DEC-034's "Default-all-display, scoped per source-open, not
  per navigation" bullet only; the rest of DEC-034 (digital-waveform
  endpoint architecture, shared single-Plotly-figure rendering,
  classification precedence, digital region placement) is unaffected and
  remains current. See the amendment note on that bullet in
  [DEC-034](#dec-034--digital-channel-rendering-shared-batched-full-record-transition-api-one-shared-multi-trace-plotly-figure-not-one-instance-per-channel-phase-4a).
- `frontend/index.html`: `ww.sourceDefaultsApplied` and
  `wwApplyDefaultChannelDisplay()` removed entirely; new
  `groupToggleButtonHtml()`, `wwChannelGroupRows()`,
  `wwToggleChannelGroupDisplay()`, `wwRemoveChannelsByKeys()`,
  `wwRemoveDigitalChannelsByKeys()`, `analogMetaFromRow()`/
  `digitalMetaFromRow()`. No backend change.
- See [MIGRATION_PLAN.md — Phase 4A-UAT9](MIGRATION_PLAN.md#phase-4a-uat9--default-hidden-channels--group-visibility-toggles-2026-08-19).

---

## DEC-039 — A/B time measurement cursors are ONE workspace-level DOM overlay over the shared elapsed-time domain, never a per-panel Plotly shape (Phase 4B)

Date: 2026-08-19
Status: Approved
Source: explicit project-owner task specification opening Phase 4B ("A/B
Time Cursors"), the first dedicated measurement feature built on top of
the shared-viewport architecture DEC-021/DEC-024/DEC-030/DEC-037 already
established.

Decision:

A/B workspace-level time measurement cursors overlay the entire waveform
stack, including analog, digital, and shared time ruler. Cursor state is
stored in the shared elapsed engineering-time domain; A is blue, B red;
Δt is adaptive-formatted.

Concretely:

- **Architecture**: a plain absolutely-positioned DOM overlay
  (`#wwCursorOverlay`, a sibling of `#wwPanels`/`#wwDigitalRegion` inside
  `.workspace-section`) plus one nested sibling overlay
  (`#wwCursorRulerOverlay`, a child of `#wwStickyRuler` itself so it
  inherits that element's own `position: sticky` pinning automatically) —
  never a Plotly `layout.shapes` entry duplicated into every analog panel.
  The two segments are driven by the identical time→pixel conversion
  (`wwCursorPlotMetrics()`/`wwCursorTimeToPixelX()`, reading a real
  rendered surface's own `_fullLayout.xaxis._offset`/`_length`, the same
  established technique `wwDiagnoseDigitalAlignment()` already proved in
  Phase 4A-UAT2) and abut exactly at the ruler's top edge, so they read as
  one continuous line without needing a second synchronization mechanism.
- **State**: `ww.measurementCursors = { enabled, a: {visible, time}, b:
  {visible, time} }`. `a.time`/`b.time` are ALWAYS elapsed engineering
  seconds in the exact same coordinate system as `ww.viewport`/
  `ww.workspaceBounds` (DEC-037) — never pixels, never a Plotly paper
  coordinate, never an absolute timestamp string. Absolute-mode display
  is a pure formatting transform at render time only, exactly parallel to
  how `ww.viewport` itself is already treated.
- **Global across layout modes**: cursor state is workspace-level, never
  per-layout — switching Grouped/Separate/Custom recomputes ONLY the
  overlay's pixel projection (panel geometry changed) and never touches
  `a.time`/`b.time`, matching the same "layout mode governs arrangement
  only" principle DEC-035 already established for analog visibility.
- **Default off; 1/3-2/3 initial placement**: a source/workspace starts
  with cursor mode disabled. First activation places A at
  `viewport.start + width/3` and B at `viewport.start + 2*width/3`.
  Toggling OFF then ON again within the same source/workspace restores
  whatever positions were last set (including un-hiding an individually
  closed cursor) rather than re-initializing — only a genuinely new
  source selection (reusing the exact same "fresh viewport" signal
  `wwRefreshWorkspaceBounds()` already computes for DEC-037) or "Start New
  Workspace" reinitializes/fully resets.
- **Dragging is DOM-only**: pointer-capture drag on a wide invisible hit
  strip or the compact "[A ×]"/"[B ×]" label updates `style.left`/
  textContent directly, using plot metrics cached once at drag-start —
  never a Plotly redraw, backend fetch, or full layout rebuild per
  pointermove, which is the actual reason this is a DOM overlay and not
  Plotly shapes (the fragmented-state/redraw-cost risk the owner's task
  spec explicitly called out).
- **Readout**: A/B/Δt shown at the right side of the bottom status bar
  (a flex spacer, not a floating dialog), Δt signed
  (`B.time - A.time`), adaptive µs/ms/s text formatting via a new,
  dedicated `wwFormatCursorDuration()` — deliberately separate from
  `wwStickyRulerElapsedUnit()`/`wwTimeAxisTickFormat()`, which configure a
  Plotly axis for an entire visible span, a different job from formatting
  one scalar duration as status-bar text.
- **Works with zero displayed channels**: the readout only needs a valid
  `ww.viewport` (established immediately on source-open per DEC-037, even
  with nothing displayed); the visual line additionally needs a rendered
  plotting surface to project onto, so it simply stays undrawn (never
  guessed/approximated) until one exists.

Reason:

This is the first dedicated measurement feature in the product, and its
own task specification was explicit that a naive per-panel-shapes
implementation would create exactly the fragmentation, alignment risk,
and duplicated-state problems this project's shared-viewport work
(DEC-021 onward) already spent several phases eliminating for the
waveform itself — worth recording as a decision, not just an
implementation detail, because every future measurement feature
(amplitude/value-at-cursor, a cursor-linked table, multi-source
comparison) will build on this same overlay/state architecture rather
than reinventing it.

Alternatives considered:

- **A Plotly `layout.shapes` vertical line per panel** — rejected per the
  owner's own explicit instruction (section 9 of the task spec): N
  independent lines to keep pixel-aligned across every analog panel, the
  digital chart, and the ruler on every zoom/pan/resize/layout change,
  the exact duplicated-state risk a workspace-level overlay avoids by
  construction.
- **A single overlay spanning the ruler's own row too (no separate
  sticky-nested segment)** — rejected: since the ruler is `position:
  sticky`, a plain non-sticky overlay's line would visually detach from
  the ruler the moment it becomes pinned mid-scroll (the analog/digital
  portion scrolls normally, the ruler does not) — the two-segment design
  is the direct fix for that, not a workaround chosen for its own sake.
- **Recomputing pixel projection continuously via a scroll/resize
  listener loop** — rejected in favor of hooking into the small number of
  EXISTING functions that already run on every event that can move a
  cursor's projection (`wwSyncStickyRuler()`, `wwRebuildLayout()`,
  `wwResizeAllVisiblePlots()`, `wwRebuildDigitalChart()`), avoiding a
  second, independent trigger mechanism alongside ones that already exist
  for the exact same class of "something about the plot geometry changed"
  event.

Impact:

- `frontend/index.html` only — no backend change. New state:
  `ww.measurementCursors`. New DOM: `#wwCursorModeBtn` (toolbar),
  `#wwCursorOverlay`/`#wwCursorRulerOverlay` (workspace/ruler overlays),
  status-bar A/B/Δt readout. New functions: `wwCursorPlotMetrics()`,
  `wwCursorTimeToPixelX()`/`wwCursorPixelXToTime()`,
  `wwFormatCursorDuration()`/`wwFormatCursorPointTime()`,
  `wwEnsureCursorDom()`, `wwUpdateCursorOverlay()`,
  `wwToggleMeasurementCursors()`, `wwSetMeasurementCursorVisible()`,
  `wwInitMeasurementCursorPositions()`, `wwReinitCursorsForNewViewport()`,
  `wwResetMeasurementCursors()`, `wwWireCursorDrag()`.
- No amplitude/value-at-cursor measurement, ΔY, sample snapping, value
  interpolation, cursor-linked table, cross-source synchronization, event
  annotations, or calculated signals were implemented — explicitly out of
  scope for this phase, left for a future measurement phase to build on
  this same architecture.
- See [MIGRATION_PLAN.md — Phase 4B](MIGRATION_PLAN.md#phase-4b--ab-time-measurement-cursors-2026-08-19).

**Addendum (2026-08-19, post-UAT cosmetic refinement)**: after owner UAT
passed the functional behaviour above, the visible A/B stroke width was
reduced from 2px to 1px (the 10px drag hit target is unchanged), and a
subtle A-B range-highlight band (new theme token `--cursor-range-fill`,
the same accent-blue base as `--accent-wash` at ~5% alpha) was added as
one more element in the SAME overlay system (`.ww-cursor-range`/
`.ww-cursor-ruler-range`, positioned/hidden by the same
`wwUpdateCursorOverlay()` pass and the drag path's own live-update
function). Purely cosmetic — no change to this decision's architecture,
state model, or any of the behaviour it records above; not significant
enough to warrant its own decision number. See
[MIGRATION_PLAN.md — Phase 4B cosmetic refinement addendum](MIGRATION_PLAN.md#phase-4b-cosmetic-refinement--thinner-ab-lines--range-highlight-band-2026-08-19).

**Addendum 2 (2026-08-19, Phase 4B-UAT1)**: two more owner-requested
refinements, both still cosmetic. (1) `--cursor-range-fill`'s alpha raised
from 0.05 to 0.20 (owner: 5% read as too faint) — same blue base per
theme, no other change. (2) The A/B label pills ("[A ×]"/"[B ×]") are now
`position: sticky`, so they stay visible near the top of the visible
waveform viewport while the user scrolls a tall waveform stack — the
vertical cursor LINES themselves remain full-height and non-sticky,
unchanged (owner's own explicit constraint: only the label, never the
engineering cursor, becomes viewport-relative). Structurally, the label
markup moved out of `#wwCursorOverlay` (which has `overflow: hidden`,
incompatible with `position: sticky` escaping to the real scroll
container) into a new sibling element, `#wwCursorLabelLayer`, living
directly inside `.workspace-section` where no `overflow: hidden` ancestor
sits between it and `#activeViewArea` (the actual scrolling container).
Both the vertical-line overlay and the new sticky label layer are driven
by the identical `wwCursorTimeToPixelX()` pixel-projection authority — no
second/independent horizontal positioning logic was introduced. Dragging
from the label (pointer-capture, live update, zero waveform fetch) and
the individual × close buttons both continue to work unchanged, now
wired via the same two delegated handlers attached to both
`#wwCursorOverlay` and `#wwCursorLabelLayer`. No manual scroll listener
was added — this is CSS `position: sticky` only, per the owner's own
explicit preference. See
[MIGRATION_PLAN.md — Phase 4B-UAT1 Record](MIGRATION_PLAN.md#phase-4b-uat1--stronger-range-highlight--sticky-cursor-labels-2026-08-19).

**Addendum 3 (2026-08-20, Phase 4B-UAT2 — bug fixes)**: two confirmed bugs
in Addendum 2's own work, fixed (not redesigned). (1) Owner reported
DevTools showed `--cursor-range-fill` as undefined. Investigation
confirmed the source declaration (both themes) and the live-deployed
`theme.css` were byte-correct and reachable via real CSS cascade
(`getComputedStyle(...).getPropertyValue("--cursor-range-fill")`,
re-verified with a jsdom test exercising the real cascade engine, not
source-text matching) — no code-level cascade/scope/typo bug was found.
The best-supported explanation is browser-side caching of a pre-Addendum-2
copy of `theme.css` (no cache-busting exists on that static asset
reference); fixing that is a deployment/infra change outside this bug
fix's own scope and was NOT made unilaterally — flagged to the owner as a
possible follow-up. In the same pass, the range-fill alpha was also
changed to the owner's now-final target, 0.08 (having gone
0.05 → 0.20 → 0.08 across three UAT rounds). (2) Owner reported the
vertical cursor lines disappearing further down a tall (e.g. Separate
mode, many lanes) waveform stack while the sticky labels stayed correct.
Root cause: the overlay's height was computed as
`rulerRect.getBoundingClientRect().top - sectionRect.getBoundingClientRect().top`
— both VIEWPORT-relative, and `#wwStickyRuler` is `position: sticky`,
whose `getBoundingClientRect()` reflects its current on-screen (possibly
pinned) paint position rather than its true position in the scroll
content. Fixed by reading `rulerWrapEl.offsetTop` instead — a stable
layout metric, by definition unaffected by scroll position or by
`position: sticky`'s paint-time displacement, since `.workspace-section`
is confirmed to be `#wwStickyRuler`'s `offsetParent`. No scroll listener
was added; the existing recompute hooks (viewport/layout/resize changes)
remain sufficient since `offsetTop` doesn't change with scroll. The range
band, living inside the same now-correctly-sized overlay, is fixed by the
same change. See
[MIGRATION_PLAN.md — Phase 4B-UAT2 Record](MIGRATION_PLAN.md#phase-4b-uat2--cursor-range-fill--full-scroll-line-continuity-fix-2026-08-20).

**Addendum 4 (2026-08-20, Phase 4B-UAT3 — Addendum 3's geometry fix did
NOT fully resolve the real-browser defect)**: owner real-browser UAT of
Addendum 3 confirmed the `offsetTop` geometry fix was necessary but
**not sufficient**. Precise evidence: with cursor mode already ON and a
tall (Separate-mode, many-channel) stack, scrolling deep into the
waveform made the MAIN vertical lines (through the analog/digital panels)
disappear, while the sticky A/B labels and the ruler's own A/B segments —
both driven by entirely separate rendering paths — stayed correctly
visible throughout. Toggling cursor mode OFF then ON reliably restored
the lines immediately. This is stated plainly, not hidden: Addendum 3's
own diagnosis (a stale/incorrect overlay *height*) was real and is
retained (still fixed, still correct, not reverted), but it was not the
complete explanation for the owner's actual reported symptom.

Root-cause reasoning: since scrolling alone triggers NO code in this
application (by design, no scroll listener existed before this
addendum), and the OFF→ON toggle's only meaningfully different action is
re-invoking `wwUpdateCursorOverlay()` (reassigning every line/range
element's `style.left`/`style.height`, even where the numeric value is
unchanged) — the DOM geometry itself was very likely already correct
after scrolling, but the browser was not reliably repainting this
`overflow: hidden`, absolutely-positioned overlay as its scrolling
ancestor moved, until a style reassignment forced a fresh style/layout/
paint pass. No real browser was available in this sandbox to directly
confirm the exact paint/compositing mechanism (e.g. via
`document.elementFromPoint()` or DevTools stacking-context inspection,
both explicitly requested); this is disclosed as reasoned analysis from
the available evidence, not a directly observed fact.

Fix: a `scroll` listener on `#activeViewArea` (the real scroll
container), rAF-coalesced exactly like the existing
`wwScheduleResizeAllVisiblePlots()`, re-invokes the same, already-proven
`wwUpdateCursorOverlay()` pass — a deliberate, evidence-driven exception
to the original "prefer CSS sticky, avoid a scroll listener" preference,
explicitly authorized once real-browser evidence showed CSS alone was
insufficient. The listener is a no-op whenever cursor mode is disabled,
and only ever performs cheap DOM/CSS geometry writes — never a Plotly
call, waveform fetch, or panel rebuild — staying within the same
performance contract every other recompute hook already honors. See
[MIGRATION_PLAN.md — Phase 4B-UAT3 Record](MIGRATION_PLAN.md#phase-4b-uat3--fix-ab-main-cursor-lines-disappearing-after-vertical-scroll-2026-08-20).

---

## DEC-040 — A/B cursor channel values are computed from authoritative full-resolution source data at the nearest actual sample, agnostic to channel semantics (Phase 4C1)

Date: 2026-08-20
Status: Approved
Source: explicit project-owner task specification opening Phase 4C1
("Instantaneous Cursor Values, Cur A / Cur B"), the first VALUE
measurement feature built on top of DEC-039's cursor-TIME architecture.
**Terminology amended by explicit owner clarification, same day — see the
addendum at the end of this entry: "instantaneous" in the original task
title was shorthand for "the recorded value at this instant," not a
claim that every analog channel represents an instantaneous waveform.**

Decision:

Cur A/Cur B — the recorded Y-axis value of every displayed analog
channel at the shared workspace cursor times `ww.measurementCursors.a/b.time`
(DEC-039) — are always computed backend-side from the SAME full-resolution
`DisturbanceRecord.waveform_data` the record was parsed with, read at the
NEAREST ACTUAL SAMPLE to the requested cursor time (never interpolated,
never a `round(time * nominal_rate)` index guess, never taken from a
Plotly trace, a peak-preserving min/max envelope point, or any other
downsampled/reduced/rendered representation `extract_waveform_range`
(DEC's own Phase 2A precedent) may have produced for DISPLAY purposes).
Display resolution and measurement resolution are two independent
concerns from this decision forward — a chart may legitimately show a
reduced envelope while Cur A/B still reports the true underlying sample.

**Cur A/B is agnostic to what a channel's recorded values actually
represent.** It always returns whatever that channel's own recorded
sample is at the nearest actual time — nothing about the extraction path
assumes the channel is an instantaneous waveform. A channel recorded as
instantaneous voltage/current yields the instantaneous value at that
sample; a channel already recorded as RMS voltage/current, frequency,
power, or ROCOF yields THAT recorded value at that sample, unchanged —
Cur A/B never re-derives, re-computes, or re-interprets a value from a
different channel type. Confirmed by code audit (see addendum): neither
`extract_cursor_values()` nor any frontend cursor-value code path
branches on `engineering_type`/`engineeringType` at all — the same
nearest-sample lookup is applied uniformly to every displayed analog
channel regardless of what it physically represents.

Concretely:

- **Backend authority, batched per source**: one new service function,
  `extract_cursor_values()` (`app/services/waveform_service.py`), and one
  new batched endpoint, `POST .../sources/{source_id}/cursor-values`
  (`app/api/v1/sources.py`, `app/schemas/cursor_values.py`) — never one
  request per channel. For a given source, both cursors' nearest-sample
  indices are computed ONCE via `np.searchsorted`-based
  `_nearest_sample_index()` against that source's own shared `time` column,
  then every requested channel reads its value at those same two indices.
  Values are read directly from `waveform_data[name].to_numpy()`, which is
  already scale/offset-applied at COMTRADE parse time — no further
  transform.
- **Nearest-sample tie-break**: on an exact tie between two adjacent
  samples, the EARLIER sample wins (`<=` comparison, documented in
  `_nearest_sample_index()`'s own docstring and covered by
  `TestTieBehaviour` in `backend/tests/test_cursor_values_service.py`).
- **Bounds, never clamped**: a cursor time outside a given source's own
  valid time bounds returns `sample_time: null` / value `null` for THAT
  source — even if another source in the same multi-source workspace has a
  valid sample at that same elapsed time. A source is never asked to
  pretend a boundary sample belongs to a cursor time it doesn't actually
  reach.
- **Multi-source / multi-rate safety**: each source's own native time
  array is authoritative only for itself — a batch request is always
  scoped to one source; two sources are never combined into one lookup,
  and same-named channels from different sources are keyed by
  `source_id + channel_name`, never display name alone (frontend
  `wwChannelKey()`/backend route path parameter).
- **Frontend cache, not authority**: `ww.cursorValues` (a
  `Map<"sourceId::channelName", {aValue, bValue, aSampleTime, bSampleTime}>`)
  is a pure derived cache. `ww.measurementCursors` (DEC-039) remains the
  one cursor-TIME authority; this decision only adds a VALUE layer read
  from it, never restructures it. `wwCurValueText()` is the single
  gating+formatting function every render path goes through — mode
  disabled, a specific cursor closed/absent, or the channel hidden all
  independently force "—", regardless of cache contents (defense in
  depth, not reliant on the cache being actively purged in every case).
- **Never floods the network**: a leading+trailing throttle
  (`wwScheduleCursorValuesRefresh()`, ~50ms) coalesces live-drag
  pointermoves into far fewer backend requests than raw pointer events,
  while the visual cursor line itself still moves at full pointermove
  speed (unthrottled, DOM/CSS only, per DEC-039). `pointerup` always
  issues one final, unthrottled request for the exact settled position.
  A monotonically increasing per-source generation counter discards any
  response that is no longer the latest outstanding request for that
  source, so a fast drag can never let a stale response overwrite a newer
  cursor position's values.
- **Hidden-channel discipline preserved**: a hidden channel's value is
  never fetched just because it exists in the sidebar (DEC-038's
  default-hidden performance policy extends naturally to this feature) —
  only currently-DISPLAYED analog channels are ever included in a batch
  request.

Reason:

This is the first VALUE (as opposed to time-position) measurement built on
the DEC-039 cursor architecture, and it establishes the engineering
integrity rule every future measurement (RMS, angle, delta-amplitude,
phasor) must also follow: a number an engineer reads off this tool must
always trace back to a real recorded sample, never to whatever the chart
happened to render for display efficiency at the current zoom level. That
distinction is invisible in the UI (both look like "the value at this
time") but is a correctness-critical implementation detail worth recording
as a decision, not leaving as an unstated implementation detail future
work could silently violate by reusing a display-path helper for
convenience.

Alternatives considered:

- **Reading the value directly from the already-rendered Plotly trace at
  the nearest visible point** — rejected: a zoomed-out or long recording
  is displayed via `extract_waveform_range`'s peak-preserving min/max
  envelope (Phase 2A), whose points are display-optimized extrema, not
  necessarily the sample nearest the cursor's actual time. This is exactly
  the failure mode `TestFullResolutionAuthority` in
  `test_cursor_values_service.py` was written to catch: a reduced-envelope
  point can differ from the true full-resolution sample at the same
  nominal time.
- **Linear interpolation between the two nearest samples** — rejected per
  the owner's explicit "nearest actual sample, no interpolation" rule: an
  interpolated value is a synthetic number that was never actually
  recorded, unacceptable for engineering measurement even though it would
  look smoother while dragging.
- **One request per channel** — rejected: a source with dozens of
  displayed channels (or a group "Show all") would multiply into dozens of
  simultaneous requests during live dragging; the batched, source-scoped
  endpoint was chosen specifically so N displayed channels always cost
  exactly one request.

Impact:

- Backend: new `extract_cursor_values()` + supporting dataclasses in
  `app/services/waveform_service.py`; new
  `app/schemas/cursor_values.py`; new route in `app/api/v1/sources.py`.
  18 + 9 new tests (`test_cursor_values_service.py`,
  `test_cursor_values_api.py`), full suite 355/355 passing, no
  regressions.
- Frontend (`frontend/index.html` only): new `ww.cursorValues` cache;
  `wwFormatEngineeringValue()`, `wwCurValueText()`,
  `wwCurValueCellHtml()`, `wwUpdateCursorValueCellsForChannels()`,
  `wwUpdateAllCursorValueCells()`, `wwClearCursorValuesForChannels()`,
  `wwCursorValuesHandleModeDisabled()`, `wwCursorValuesHandleCursorClosed()`,
  `wwFetchCursorValuesForSource()`, `wwFetchAllCursorValues()`,
  `wwScheduleCursorValuesRefresh()`; sidebar analog table extended from
  Channel/Phase to Channel/Phase/Cur A/Cur B (`renderChannelTable()` now
  accepts an optional per-column `className`). Digital sidebar
  deliberately unchanged — no Cur A/B columns added to digital channels
  this phase.
- Does NOT alter DEC-039's cursor-time architecture or state shape in any
  way — `ww.measurementCursors` is read-only from this feature's
  perspective.
- Explicitly NOT implemented this phase (deferred): CALCULATED RMS A/B
  (deriving an RMS value from an instantaneous waveform channel via some
  window/algorithm — a separate derived-measurement feature requiring an
  explicitly defined calculation, distinct from Cur A/B simply reading a
  channel that is ALREADY recorded as RMS, which this phase already
  supports per the addendum below), angle A/B, delta angle, amplitude
  delta (ΔY), interpolation options, on-canvas value annotations, digital
  state at cursor, cross-source time synchronization, resampling, phasor
  calculation.
- See [MIGRATION_PLAN.md — Phase 4C1](MIGRATION_PLAN.md#phase-4c1--ab-cursor-channel-values-cur-a--cur-b-2026-08-20).

**Addendum (2026-08-20, owner terminology clarification, same day as
initial implementation)**: the owner clarified that "Instantaneous Cursor
Values," this phase's original working title, was too restrictive a name
for what was actually built. Cur A/Cur B are GENERIC CHANNEL Y-AXIS
VALUES at cursor A/B — the recorded value of whatever channel is
selected, at the nearest actual sample — never an assumption that every
analog channel represents an instantaneous waveform. Examples the owner
gave directly: an instantaneous-voltage channel's Cur A/B is the recorded
instantaneous voltage; an RMS-voltage channel's Cur A/B is the recorded
RMS voltage (not a re-derivation); a frequency channel's Cur A/B is the
recorded frequency; a power channel's Cur A/B is the recorded power — in
every case, Cur A/B is simply "whatever this channel's own recorded
sample is at this time," with zero interpretation of what that number
physically represents. A dedicated code audit at this same clarification
(grep across `backend/app/services/waveform_service.py`,
`backend/app/api/v1/sources.py`, `backend/app/schemas/cursor_values.py`,
and every cursor-value function in `frontend/index.html`) confirmed **no
functional change was required** — `extract_cursor_values()` and its
frontend callers never reference `engineering_type`/`engineeringType`
anywhere; the nearest-sample lookup already applies uniformly to any
analog channel by name, regardless of what it represents. This addendum
is a terminology/documentation correction only: the heading above, the
Decision section's "recorded Y-axis value... agnostic to channel
semantics" language, and this note are the amendment; no production code
in `backend/` or `frontend/` changed as a result. UI labels remain
exactly "Cur A"/"Cur B", unchanged. Calculated RMS/angle/phasor
measurements (deriving a new value from an instantaneous waveform) remain
explicitly out of scope, per the bullet immediately above.

**Addendum 2 (2026-08-20, Phase 4C2 — digital A/B cursor state)**: this
decision's own authority principle extends, by reference, to digital
channels: **digital A/B cursor measurement reports the authoritative
recorded digital state (0/1) at the cursor time. It is source-native,
full-resolution, and independent of displayed/rendered waveform
representation.** Recorded as an addendum here, not a new decision
number, because the underlying engineering rule is IDENTICAL to this
decision's own core principle above — only the channel kind (digital
instead of analog) and the value type (an integer state instead of a
float) differ.

Concretely:

- **Same backend endpoint, same shared index computation**: `POST
  .../sources/{source_id}/cursor-values` (unchanged path) now accepts
  `digital_channel_names` alongside `analog_channel_names`, and
  `extract_cursor_values()` resolves BOTH kinds from the SAME two
  already-computed nearest-sample indices for that source — a source
  with both analog and digital channels displayed still costs exactly
  one request, one pair of index lookups, never a second lookup for
  digital.
- **No separate transition-search algorithm**: digital channels are
  confirmed (by direct inspection of
  `app.providers.comtrade._build_dataframe`) to live in the SAME dense,
  per-sample `waveform_data` DataFrame and the SAME shared `"time"`
  column analog channels use — `extract_digital_waveform`'s own sparse
  transition list is a DERIVED, display-oriented representation
  (`np.diff` over that same dense array), not a second source of truth.
  Reading the dense digital column at the nearest-sample index is
  therefore both the full-resolution authority AND the correct
  implementation of the exact-transition-timestamp rule ("state at T =
  the NEW state beginning at T") for free, with no special-casing.
- **Compact inline presentation, never a table column**: "Cur A"/"Cur B"
  full-width sidebar columns (Phase 4C1) remain analog-only. Digital rows
  instead get compact inline "A:0 B:1" badges appended to the existing
  Channel cell (`.digital-cur-badges`, pushed to the row's right edge via
  `margin-left: auto`) — an explicit, deliberate UI distinction from
  analog, per the owner's own instruction, not an oversight.
- **Separate cache, same key shape**: `ww.digitalCursorValues` (a second
  `Map<"sourceId::channelName", {aState, bState}>`) is deliberately never
  the same Map as `ww.cursorValues` — avoids any risk of an analog float
  `0.0` and a digital state `0` colliding under a shared key, even though
  both reuse the identical `wwChannelKey()` shape.
- **Neutral badge styling**: no red/green, no alarm/healthy implication —
  digital semantics vary by signal (a channel's own `classification`/
  `normal_state` are UNCHANGED by and UNUSED by this measurement, exactly
  as DEC-034's Triggered/Never Triggered/Spare classification already is
  computed once at import time and never re-derived per request).

Reason: the owner's own Phase 4C2 task specification investigated
digital's internal storage FIRST (rather than assuming a
transition-interval-search design) and confirmed it is sample-dense, not
sparse — the smallest-maintainable design was therefore to extend this
decision's existing mechanism, not build a parallel one.

Impact:

- Backend: `extract_cursor_values()` extended (`analog_channel_names`/
  `digital_channel_names` request params, `digital_channels` response
  list); new `DigitalChannelCursorState` dataclass/
  `DigitalChannelCursorStateOut` schema. Request field renamed
  `channel_names` -> `analog_channel_names` for symmetry/type clarity (an
  internal-only API with no external consumers; a clean rename, not a
  versioned/back-compat change, per this project's own established
  convention of preferring clean renames over compatibility shims). 19
  new backend tests (12 service-level, 7 API-level), full suite 374/374
  passing.
- Frontend: new `ww.digitalCursorValues`, `wwDigitalCurStateText()`,
  `wwDigitalCurBadgeHtml()`, `wwUpdateDigitalCursorBadgesForChannels()`,
  `wwUpdateAllDigitalCursorBadges()`,
  `wwClearDigitalCursorValuesForChannels()`,
  `wwDisplayedDigitalSourceIds()`/
  `wwDisplayedDigitalChannelNamesForSource()`; `wwFetchCursorValuesForSource()`/
  `wwFetchAllCursorValues()` extended to cover both kinds together, one
  combined request per source; hooked into the existing digital "core
  mutation" functions (`wwAddDigitalChannels()`,
  `wwRemoveDigitalChannelByKey()`, `wwRemoveDigitalChannelsByKeys()`,
  `wwRemoveChannelsForSource()`'s own digital branch) mirroring Phase
  4C1's analog hook pattern exactly. New `phase4c2_check.mjs` (24 checks).
  Full frontend regression suite reconfirmed at exactly the established
  18-failure baseline.
- Does NOT alter DEC-034's digital classification/grouping architecture,
  DEC-035's analog-visibility-is-workspace-global principle, or DEC-039's
  cursor-TIME architecture in any way.
- Explicitly NOT implemented: digital transition count between A/B,
  digital duration-HIGH between A/B, a sequence-of-events table, digital
  normal/abnormal interpretation, RMS, angle, delta angle, calculated
  analog measurements, or cross-source synchronization.
- See [MIGRATION_PLAN.md — Phase 4C2](MIGRATION_PLAN.md#phase-4c2--digital-ab-cursor-state-2026-08-20).

---

## DEC-041 — Waveform reduction is an overview rendering optimization with a 10,000-sample full-resolution display threshold

Date: 2026-08-20
Status: Approved
Source: explicit project-owner approval after the waveform zoom-resolution
investigation.

Decision:

Waveform reduction is an overview rendering optimization only. For requested
ranges containing `<= 10,000` original samples per analog channel, Oruxa
Powerwave returns the complete original sample sequence for display. Ranges
above that threshold continue to use the existing peak-preserving min/max
display reduction.

The frontend's requested `point_budget` is now adaptive for reduced ranges:
`point_budget = clamp(plot_width_px * 4, 4000, 20000)`, where
`plot_width_px` is the actual shared Plotly plotting-domain width, not the
browser/window width. The backend owns the exact sample-count decision because
only the backend knows the clipped source-slice count authoritatively.

Reason:

Owner UAT of analog zoom raised an engineering-integrity concern: a 5 kHz
recording zoomed to roughly one second contains about 5,001 source samples,
which is a manageable event interval and should be displayed as the actual
recorded waveform, not as a sparse 4,000-point envelope. Broad overviews may
still be reduced for payload/render performance, but once the engineer zooms
into a manageable interval, the chart should transition to full source
resolution automatically.

Impact:

- `DisturbanceRecord.waveform_data` remains the full-resolution backend
  authority; it is not mutated, replaced, or cached as a display
  representation.
- `extract_waveform_range()` now bypasses reduction at or below the named
  `FULL_RESOLUTION_DISPLAY_THRESHOLD = 10_000`, regardless of a lower request
  `point_budget`.
- Above that threshold, the backend still returns
  `representation="min_max_envelope"` and caps the effective reduction budget
  by the threshold so an unusually wide plot cannot turn an overview range
  back into an unrestricted full-sample transfer.
- `representation` remains truthful: `full_resolution` means sample-for-sample
  source arrays; `min_max_envelope` means display-reduced output.
- Frontend zoom/pan/source-bounds/time-mode/cursor/digital-transition
  architecture is unchanged. Absolute/Elapsed remains presentation-only over
  elapsed request ranges. Cur A/B and digital measurement values still read
  full-resolution source data independently from display traces.
- Payload implication: one visible channel can now receive up to 10,000 exact
  samples for manageable ranges; 20 visible analog channels can therefore
  receive up to about 200,000 exact points for the same viewport; many
  displayed channels remain bounded by the 20,000 requested-budget cap and the
  backend's 10,000 full-resolution threshold rather than switching to
  unbounded full-record transfer.
- See [MIGRATION_PLAN.md — Waveform Adaptive Resolution](MIGRATION_PLAN.md#waveform-adaptive-resolution-2026-08-20).

---

## DEC-042 — Absolute and Elapsed waveform modes share numeric elapsed Plotly X coordinates

Date: 2026-08-20
Status: Approved
Source: explicit project-owner approval after the Absolute-Time waveform
precision investigation.

Decision:

Absolute and Elapsed waveform modes share one numeric elapsed engineering X
coordinate from backend response through Plotly rendering. Time mode is
presentation-only:

- Elapsed mode labels and hover text display elapsed time.
- Absolute mode labels, hover text, and A/B cursor readouts display
  `recording_start + elapsed`.
- Analog trace `x`, digital transition positions, sticky-ruler coordinates,
  `sourceBounds`, `workspaceBounds`, `viewport`, zoom/pan relayout values, and
  backend `start_time`/`end_time` request parameters remain elapsed
  floating-point seconds.

Reason:

The owner observed that a 5 kHz waveform, zoomed to roughly 14-15 ms, stayed
smooth in Elapsed mode but became visibly stepped in Absolute mode. The
analysis proved adaptive resolution and backend range extraction were already
correct: a 14 ms 5 kHz range returns 71/71 full-resolution samples and a
15 ms range returns 76/76 full-resolution samples. The precision loss happened
only in the frontend Absolute presentation path: high-resolution elapsed
seconds were converted to millisecond-formatted date strings before Plotly
received them. At 5 kHz, five 0.2 ms samples can therefore collapse onto one
millisecond X coordinate while retaining distinct Y values, producing the
stepped/vertical geometry reported in UAT.

Alternatives considered:

Continuing to use Plotly date axes/date strings for Absolute mode (rejected:
the current JavaScript `Date`/formatted-string path is millisecond-granular and
cannot preserve 0.2 ms sample spacing); numeric epoch milliseconds (rejected:
still invites millisecond-oriented date-axis behavior and would split the
engineering coordinate model); adding an Absolute source-bounds/viewport model
(rejected: DEC-021/DEC-037 require one elapsed viewport authority); redesigning
timezone or multi-source alignment semantics (rejected as out of scope).

Impact:

- `frontend/index.html`: `wwElapsedToPlotlyX()` and `wwPlotlyXToElapsed()` are
  identity helpers; panel and digital Plotly axes are always linear numeric
  elapsed seconds; `wwSetTimeMode()` no longer rewrites trace X/Y arrays;
  Absolute hover uses per-point `customdata`; Absolute tick labels are generated
  from elapsed tick coordinates and `wwWorkspaceRecordingStartMs()`; the sticky
  ruler keeps the same elapsed coordinate domain in both modes; A/B cursor
  geometry remains elapsed and only its Absolute text formatter changes.
- `backend/tests/test_frontend_absolute_time_precision.py`: permanent static
  regressions cover identity coordinate conversion, no date-axis/date-string
  Plotly coordinates, no geometry rewrite on mode switch, 5 kHz 76/76 unique-X
  preservation, sub-ms precision tiers, and numeric-domain sticky ruler
  behavior.
- No backend behavior, waveform reduction policy, COMTRADE parsing,
  source-aware bounds, digital transitions, Cur A/B values, or cross-source
  synchronization semantics changed.
- See [MIGRATION_PLAN.md — Waveform Time-Axis Sub-ms Precision](MIGRATION_PLAN.md#waveform-time-axis-sub-ms-precision-2026-08-20).

---

## DEC-043 — Precision step zoom: X step is workspace-global, Y step is active-panel-local; waveform toolbar is icon-primary

Date: 2026-08-20
Status: Approved
Source: explicit project-owner task specification for Phase 4D
("Precision Step Zoom + Icon Toolbar Refinement").

Decision:

**X step zoom is workspace-global; Y step zoom is active-panel-local.**

Two new step-zoom actions, Zoom In and Zoom Out, are added as one split
button EACH (never four permanent X+/X-/Y+/Y- buttons) — a main icon
that repeats whichever axis (X or Y) was last chosen for that action, plus
a small dropdown to choose the axis. Both use the same +/-20% stepping
rule (new span = current span × 0.8 for Zoom In, × 1.25 for Zoom Out,
current midpoint held fixed), applied to two structurally different
targets:

- **X**: reuses `ww.viewport`/`ww.workspaceBounds` exactly as drag-zoom/
  pan/Reset Time View already do, via the SAME `wwApplyAndFetchViewport()`
  authority — every analog panel, the digital region, the shared ruler,
  and A/B cursor projection move together, and the normal adaptive-
  resolution range fetch (DEC-041) runs again for the new range. Zoom Out
  is bounded by `ww.workspaceBounds` (shifting the window to preserve the
  requested span when it still fits, never silently truncating it) and
  becomes a genuine no-op — no refetch, button reads disabled — once the
  viewport already covers the full workspace.
- **Y**: applies ONLY to a newly-introduced ACTIVE waveform panel concept
  (`ww.activePanelGroupKey`, resolved via `wwActivePanel()`) — never every
  panel globally. The most recently CLICKED panel (its header specifically,
  not hover — hover alone would be ambiguous while using toolbar controls)
  becomes active, shown via a subtle border-accent only
  (`.ww-panel--active`). Reads/writes `Plotly`'s own resolved
  `_fullLayout.yaxis.range` directly on that one panel, taking it out of
  autorange — Autoscale Y (unchanged, still global across every panel) is
  the one action that restores automatic scaling. Works identically in
  Grouped (active GROUP panel), Separate (active per-channel LANE), and
  Custom (active CUSTOM GROUP panel) — the same generic panel-click model
  applies regardless of mode, since a "panel" already means whichever of
  those three things is currently on screen. A layout-mode switch fully
  discards and recreates every panel object (pre-existing behavior,
  unchanged) — `wwActivePanel()` self-heals by falling back to the first
  current panel whenever the remembered key no longer matches, so Y step
  zoom can never operate on a destroyed/purged Plotly instance.

**The waveform toolbar is icon-primary.** Every major control (Box Zoom,
Pan, the two new Zoom In/Out split buttons, Absolute Time, Elapsed Time,
Reset Time View, Autoscale Y, A/B Time Cursors, Grouped/Separate/Custom
Layout, Clear Workspace) is now an SVG icon with a `title`/`aria-label`
tooltip pair instead of a text label — reusing the EXACT SAME
`viewBox="0 0 18 18"`/`stroke="currentColor"`/`fill="none"` convention
`#mainSidebarMenu`'s `.shell-nav-icon` already established, so the app's
navigation rail and waveform toolbar read as one icon family rather than
two visual languages. Grouped into Navigation / Zoom step / Time / View /
Measurement / Layout / Workspace clusters via thin `.ww-toolbar-sep`
separators. No engineering behavior of any existing control changed by
this — only its rendered content and (for the two new actions) precision.

Reason:

Drag-based zoom/pan already worked correctly but offered no way to take
one small, exact, repeatable step — an engineer inspecting a specific
transient often wants "narrow the window by about 20% around what I'm
already looking at," repeatably, without a mouse-precision drag each
time. Y-axis vertical inspection is inherently per-signal (different
engineering panels carry unrelated magnitudes), so a global Y step would
either do nothing useful for most panels or require re-deriving a
combined scale — an explicit active-panel concept was needed regardless
of the icon-toolbar work, and the owner approved scoping it to exactly
one panel at a time rather than inventing a multi-select model. The icon
conversion was requested separately, purely as a toolbar usability/
appearance refinement, riding along in the same phase because both touch
the same toolbar markup.

Alternatives considered:

- **Four permanent X+/X-/Y+/Y- toolbar buttons** — rejected per the
  owner's own explicit instruction: doubles the visible control count for
  a capability two split buttons already cover cleanly.
- **One shared remembered axis for both Zoom In and Zoom Out** — rejected
  in favor of remembering them separately (the task's own primary
  recommendation): sharing risked a surprising cross-action jump (e.g.
  choosing Y for Zoom In silently redirecting a later Zoom Out click too).
- **Y step zoom applied globally to every panel** — rejected per the
  owner's own explicit instruction (section 9 of the task spec): distinct
  engineering panels legitimately need independent vertical inspection.
- **Hover-based active-panel selection** — rejected per the owner's own
  explicit instruction: ambiguous the moment the pointer is over a
  toolbar control instead of any panel, exactly when a Y step click
  happens.
- **A large/heavy external icon library** — rejected: the project already
  had an established lightweight inline-SVG icon convention
  (`.shell-nav-icon`); reusing it kept the toolbar in the same visual
  family for free and avoided an unnecessary dependency (task's own
  explicit "do not add a heavy icon dependency unnecessarily" instruction).

Impact:

- `frontend/index.html` only — no backend change; X step zoom reuses the
  existing `GET .../waveform` endpoint and DEC-041's adaptive-resolution
  policy completely unmodified.
- New state: `ww.activePanelGroupKey`, `ww.zoomStepAxis` (`{in, out}`,
  both default `"x"`). New functions: `wwActivePanel()`,
  `wwSetActivePanel()`, `wwSyncActivePanelVisual()`,
  `wwWireActivePanelSelection()`, `wwClampZoomWindowToWorkspace()`,
  `wwStepZoomX()`, `wwStepZoomY()`, `wwPerformZoomStep()`,
  `wwSetZoomStepAxis()`, `wwSyncZoomStepControls()`,
  `wwWireZoomStepSplitButtons()`. New CSS: `.ww-icon`/`.ww-icon-btn`/
  `.ww-icon-group`/`.ww-split-btn`(+`-main`/`-trigger`/`-menu`/
  `-menu-item`)/`.ww-toolbar-sep`/`.ww-panel--active`.
  `digitalChannelNameCellHtml()`/`renderDigitalGroup()` (Phase 4C2) and
  every existing toolbar button `id` are otherwise unchanged.
- Does NOT alter DEC-021 (workspace-level navigation), DEC-034 (digital
  classification), DEC-037 (source-aware bounds), DEC-039 (A/B cursor
  architecture), DEC-040 (Cur A/B measurement authority), DEC-041
  (adaptive resolution), or DEC-042 (numeric elapsed Plotly coordinates)
  in any way — X step zoom is a new CALLER of the exact same authoritative
  paths those decisions already established, never a parallel one.
- Explicitly NOT implemented: configurable zoom percentage, new keyboard
  shortcuts beyond the split-button dropdown's own Tab/Enter/Escape,
  wheel-step customization, RMS/angle/synchronization, toolbar
  personalization/reordering, or migration to an external icon library.
- See [MIGRATION_PLAN.md — Phase 4D](MIGRATION_PLAN.md#phase-4d--precision-step-zoom--icon-toolbar-refinement-2026-08-20).

---

## DEC-044 — Generic annotation framework; first type is a workspace-scoped, work-area-relative Free Text Note

Date: 2026-08-20
Status: Approved
Source: explicit project-owner task specification for Phase 4E
("Annotation Framework + Free Text Note").

Decision:

Oruxa Powerwave gains a GENERIC annotation framework, with exactly one
supported annotation type this phase: `text_note`. The framework, not
just the one type, is the architecture being approved:

- **One authority, one shape**: `ww.annotations` (`Map<id, Annotation>`)
  is the sole state; every rendered note, every drawer row, and the
  toolbar count badge are derived from it via
  `wwRenderAnnotations()`/`wwRenderAnnotationList()`, never a second
  competing state. An `Annotation` is `{id, type, workspaceId, position:
  {x, y}, createdAt, zIndex, data}` — `data` is a type-specific payload
  (`{text}` for `text_note`) so a future type (e.g. `callout_note`) adds
  its own fields there without restructuring the record shape, and every
  presentation function that varies by type (`wwAnnotationCategoryLabel()`/
  `wwAnnotationSummary()`) dispatches on `annotation.type` rather than
  being hard-wired to `text_note`'s own DOM shape.
- **Workspace/session-scoped, not data-anchored**: `position` is
  NORMALIZED (0..1) relative to `#workspaceRow`'s own stable bounding
  rect — never a waveform time/Y value, never relative to a Plotly panel
  or trace. This first note type is a deliberately FLOATING work-area
  note (section 6 of the task): zoom, pan, Absolute/Elapsed, and
  Grouped/Separate/Custom never move or touch it. A future
  waveform-anchored type (`callout_note`, with its own `anchorTime`/
  `anchorChannel`/connector line) is a SEPARATE future phase this
  decision explicitly does not implement or pre-build fields for.
- **Placement area (section 7, "Option C")**: the full permitted analysis
  work area — the left Workspace Sidebar AND the main waveform area
  (analog panels, digital region, sticky ruler) — but never the toolbar
  itself. Achieved via ONE overlay (`#wwAnnotationOverlay`, a child of
  `#workspaceRow`) for rendering, with toolbar exclusion enforced by
  checking `#wwToolbar`'s own live bounding rect at click-time and during
  drag clamping — not a CSS clip-path, which would need constant
  recomputation since the toolbar wraps to a taller height at narrow
  widths (Phase 4D's own `flex-wrap: wrap`).
- **Pointer isolation**: the overlay's empty space is `pointer-events:
  none`; only an individual `.ww-annotation` note is
  `pointer-events: auto`. Plotly zoom/pan, A/B cursor drag, and every
  sidebar control are provably unaffected by the overlay's presence.
- **Lifecycle**: cleared ONLY by "Start New Workspace" (a genuinely new
  `workspace_id` — see `wwClearWorkspace({resetSourceBounds:true})`'s
  existing branch, which already resets `ww.measurementCursors` for the
  identical reason). The plain "Clear workspace" button is DISPLAY-ONLY
  (removes displayed panels/channels, keeps the same source/session
  context) and deliberately does NOT touch `ww.annotations` — inspected
  and confirmed as the correct, already-established precedent (cursors
  get the exact same treatment) rather than assumed.
- **Annotation List is generic**, not a text-note-only drawer: it renders
  `wwAnnotationCategoryLabel()`/`wwAnnotationSummary()` for whatever
  annotations exist, sorted newest-first (a deliberate, documented
  ordering choice), with delete centralized there (never a permanent ×
  on the floating note itself, keeping the canvas clean per the owner's
  own explicit instruction).

Reason:

The owner's own stated goal was a framework, not a one-off text-note
feature — future types (callout notes, event/channel markers, delta/RMS/
peak/amplitude stamps) are explicitly anticipated. Building `type`/`data`-
based extensibility and a type-dispatching drawer NOW, while implementing
only `text_note`, avoids a second architecture pass when the next
annotation type arrives, while staying strictly within this phase's own
scope exclusions (no callout/anchoring UI or fields built prematurely).

Alternatives considered:

- **A one-off "text note" DOM/state structure** — rejected per the
  owner's own explicit instruction; would require redesigning the whole
  feature for the next annotation type.
- **True native scroll-following** for notes placed over
  `#workspaceSidebar`/`#activeViewArea` (both independently-scrolling
  `overflow-y: auto` containers) — evaluated and NOT implemented this
  phase. Achieving it while preserving section 32's "seamlessly draggable
  between sidebar and main area" requirement would need either dynamic
  DOM re-parenting of a note between two different scroll containers
  mid-drag, or manual `scrollTop` tracking duplicating native scroll
  mechanics for both containers independently — meaningfully more complex
  and not verifiable without live-browser testing in this environment.
  Chose instead to anchor notes to `#workspaceRow`'s own STABLE (never-
  scrolling) viewport frame: one simple shared coordinate system, full
  Option C coverage, and provably correct cross-region dragging, at the
  documented cost of a note not visually scrolling away when its
  container's internal content is scrolled. Reported as a deliberate,
  reasoned tradeoff, not a silent fallback — see MIGRATION_PLAN.md's own
  Phase 4E record for the full analysis.
- **A permanently-visible delete × on every note** — rejected per the
  owner's own explicit instruction: deletion is centralized through the
  Annotation List, keeping the floating note's own canvas appearance
  clean.
- **A confirmation dialog before deleting one note** — rejected per the
  owner's own explicit instruction: unnecessary friction for a small,
  individually-reversible-by-recreation action; reserved for a possible
  future "Clear All Annotations" the owner did not ask for this phase.
- **Backend/database persistence** — rejected as out of scope this phase
  (section 70): frontend workspace/session state already satisfies the
  owner-approved persistence requirement (survives view/mode changes and
  Recordings↔Waveform navigation within the same workspace; cleared on a
  genuinely new one), matching this project's own existing precedent that
  session-scoped UI state (cursors, custom groups, panel heights) lives
  in frontend memory, not a database.

Impact:

- `frontend/index.html` only — no backend endpoint, schema, or database
  change.
- New state: `ww.annotations`, `ww.annotationSelectedId`,
  `ww.annotationPlacementType`, `ww.annotationZCounter`. New functions
  (non-exhaustive): `wwCreateAnnotation()`/`wwUpdateAnnotation()`/
  `wwDeleteAnnotation()`/`wwSelectAnnotation()`/`wwRenderAnnotations()`/
  `wwRenderAnnotationList()`/`wwEnterAnnotationPlacementMode()`/
  `wwExitAnnotationPlacementMode()`/`wwBeginAnnotationEdit()`/
  `wwEndAnnotationEdit()`/`wwClampAnnotationPixelPosition()`/
  `wwAnnotationWorkAreaRect()`. New toolbar controls: Annotate (dropdown,
  currently one item: Text Note) and Annotations (opens the drawer, shows
  a count badge). New DOM: `#wwAnnotationOverlay` (child of
  `#workspaceRow`), `#wwAnnotationDrawer` (a right-side, `position: fixed`
  overlay panel — never consumes/reflows `#workspaceRow`'s own width, so
  opening/closing it can never distort normalized annotation positions).
- Hooked into `wwResizeAllVisiblePlots()` (repositions notes from their
  unchanged normalized coordinates whenever workspace geometry actually
  resizes) and `wwClearWorkspace()`'s `resetSourceBounds` branch (clears
  annotations on a genuinely new workspace) — and deliberately NOT hooked
  into `wwRebuildLayout()`, `wwSetTimeMode()`, `wwApplyAndFetchViewport()`,
  or any cursor function, confirming by absence that none of those paths
  can move/touch/recreate an annotation.
- Does NOT alter DEC-021 (workspace-level navigation), DEC-034/037/039/040
  (digital classification, source-aware bounds, cursor architecture, Cur
  A/B authority), DEC-041/042 (adaptive resolution, numeric elapsed
  coordinates), or DEC-043 (step zoom/icon toolbar) in any way.
- Explicitly NOT implemented: callout connector line, waveform-point/
  time/channel anchoring, delta measurement, event/channel markers, RMS/
  peak/amplitude stamps, cross-channel delta, import/export, cloud/
  database persistence, a colors/theme chooser, rich text/Markdown,
  image annotations, or a "Clear All Annotations" action.
- See [MIGRATION_PLAN.md — Phase 4E](MIGRATION_PLAN.md#phase-4e--annotation-framework--free-text-note-2026-08-20).

### ADDENDUM (2026-08-21) — Region-aware content-scroll anchoring (Phase 4E-UAT)

Status: Approved
Source: owner UAT finding — floating Text Notes stayed visually FIXED
while the left Workspace Sidebar or the main waveform area was scrolled,
instead of moving with the content they were placed beside.

Supersedes DEC-044's own "Alternatives considered" entry that rejected
true native scroll-following in favor of a `#workspaceRow`-relative
stable-viewport model. That tradeoff is now reversed:

> Floating Text Notes are region-aware content annotations. They are not
> fixed to the workspace viewport. Sidebar-owned notes scroll with sidebar
> content; main-workspace notes scroll with main content. Cross-region
> drag transfers coordinate ownership.

Decision:

- Each `Annotation` now additionally carries a `region: "sidebar" |
  "main"` field. `position: {x, y}` is no longer normalized 0..1 against
  `#workspaceRow` — it is a RAW CONTENT-PIXEL offset from the owning
  region's own scrollable content origin (`#workspaceSidebar`'s or
  `#activeViewArea`'s own `scrollLeft`/`scrollTop`-relative space).
- Two region-specific overlays (`#wwAnnotationOverlaySidebar`,
  `#wwAnnotationOverlayMain`) replace the single `#wwAnnotationOverlay`,
  each a genuine DOM CHILD of its own region's scroll container (both now
  `position: relative`). This lets a note's absolute `left`/`top` extend
  that region's native CSS "scrollable overflow" area, so the browser's
  own scrolling carries the note correctly with ZERO manual JS
  scroll-offset compensation — the "true native scroll-following" DEC-044
  evaluated and declined is now achieved without the dynamic re-parenting
  complexity DEC-044 was worried about, because that re-parenting is now
  needed ONLY at the moment a drag crosses a region boundary (see below),
  not continuously.
- Toolbar exclusion is now STRUCTURAL rather than computed:
  `#activeViewArea` and `#wwToolbar` are siblings under `#mainWorkspace`,
  so a note that is a DOM child of `#activeViewArea` can never occupy the
  toolbar's screen space. The old `wwAnnotationToolbarRect()`/toolbar-rect
  clamping code is removed.
- Cross-region dragging (Option C) is preserved: a live pointer-position
  check (`wwDetermineAnnotationRegion()`) reparents the note's DOM element
  into the destination region's own overlay the instant the pointer
  crosses a region boundary, updates `annotation.region`, and recomputes
  its position in the new region's content-coordinate space using the
  same pointer position — no visible jump.
- Resize behavior: notes are RE-CLAMPED within their region's current
  `scrollWidth`/`scrollHeight` on every render (reusing the existing
  `wwResizeAllVisiblePlots()` → `wwRenderAnnotations()` hook) — never
  proportionally rescaled. Raw content-pixel storage was chosen over
  normalizing-by-scrollHeight because the region's content height can
  change for reasons unrelated to the note (e.g. channels shown/hidden
  elsewhere in the same scrollable region); scroll correctness was
  prioritized over normalized-viewport elegance.
- Auto-scroll while dragging near a region's edge remains explicitly OUT
  OF SCOPE, same exclusion as DEC-044's own original scope list.

Impact:

- `frontend/index.html` only. Removed: `wwAnnotationWorkAreaRect()`,
  `wwAnnotationToolbarRect()`, `wwClampAnnotationPixelPosition()`,
  `wwClamp01()`. Added: `wwAnnotationRegionEl()`, `wwAnnotationOverlayEl()`,
  `wwDetermineAnnotationRegion()`, `wwClampAnnotationContentPosition()`.
  Rewritten: `wwCreateAnnotation()` (new `region` parameter),
  `wwUpdateAnnotation()` (no longer clamps `position` to 0..1),
  `wwRenderAnnotations()`, `wwWireAnnotationDrag()`,
  `wwAnnotationPlacementClickHandler()`.
- Does not change annotation lifecycle semantics (Clear Workspace
  preserves, Start New Workspace clears), the Annotation List's own
  rendering, XSS-safe text handling, or pointer isolation — only the
  position/region model and its two rendering surfaces.
- See [MIGRATION_PLAN.md — Phase 4E-UAT](MIGRATION_PLAN.md#phase-4e-uat--annotation-scroll-anchoring-fix-2026-08-21).

### ADDENDUM (2026-08-21, refinement) — Free Text Notes restricted to the main waveform workspace (Phase 4E-UAT2)

Status: Approved
Source: owner UAT finding on the region-aware scroll-anchoring fix above —
placing and dragging notes over the left sidebar was difficult to
control because the sidebar is its own interaction-heavy region
(scrolling, resizing, channel toggles).

Supersedes the immediately preceding ADDENDUM's "Option C" placement
scope (sidebar + main area) for `text_note` specifically. This is a
deliberate UX simplification, not a temporary workaround:

> Following owner UAT, Free Text Notes are restricted to the main
> waveform workspace. Sidebar placement and cross-region dragging were
> removed because the sidebar is an interaction-heavy control region and
> did not provide precise note placement. Main-workspace notes remain
> content-scroll anchored.

Decision:

- `text_note` may be placed, and dragged, ONLY inside `#activeViewArea`
  (analog panels, digital region, shared ruler, empty waveform workspace)
  — never the Workspace Sidebar, the toolbar, the Annotation List drawer,
  or any other page chrome. A click over the sidebar while placement mode
  is active is a no-op (placement mode stays active, same as a click over
  the toolbar), not a cancel.
- `region` remains a generic field on `Annotation` (kept for a possible
  future annotation type with its own placement rule — DEC-044's own
  extensibility goal), but `"main"` is the only valid value for
  `text_note`. The DEAD complexity that existed ONLY to support
  `text_note`'s sidebar placement is removed entirely, not left dormant:
  the sidebar-owned overlay DOM (`#wwAnnotationOverlaySidebar`),
  `wwDetermineAnnotationRegion()` (cross-region pointer classification),
  mid-drag reparenting, and the region-switching branch of
  `wwWireAnnotationDrag()`/`wwRenderAnnotations()` are all gone.
- Dragging a note toward the sidebar clamps cleanly at
  `#activeViewArea`'s own left content boundary — the SAME
  `wwClampAnnotationContentPosition()` bounds check already used for
  every other edge does this for free; no new boundary-detection code was
  needed.
- Content-scroll anchoring (the prior addendum's own core fix) is fully
  preserved for the one remaining region: a main-workspace note still
  scrolls natively with `#activeViewArea`'s own content, with zero manual
  JS scroll-offset compensation.
- Existing session state: an annotation created under the prior
  region-aware fix with `region: "sidebar"` (the sidebar overlay it
  belonged to no longer exists in the DOM) is coerced to `region: "main"`
  the next time it renders, rather than crashing or disappearing — a
  render-time safety net, not a migration system, matching this
  project's own "session-local frontend state, not a database" precedent
  for annotations.

Reason:

Direct owner hands-on UAT found the sidebar's own scrolling/resizing/
channel-toggle interactions made precise note placement and dragging
there unreliable, outweighing the "whole permitted analysis area" breadth
the original Option C decision valued. Removing the sidebar-specific
code paths (rather than merely disabling them) avoids leaving dead
complexity behind for a capability the owner explicitly does not want —
consistent with this project's own "avoid unnecessary complexity"
convention elsewhere in the codebase.

Alternatives considered:

- **Keep sidebar placement but improve its precision** (e.g. a
  placement-lock or snap-to-grid) — rejected; the owner's own decision
  was to remove sidebar placement outright, not to make it more precise.
- **Delete the generic `region` field entirely** — rejected; DEC-044's
  own stated goal is a framework for FUTURE annotation types, and a
  future type may need its own placement rule (e.g. a callout/
  data-anchored type is expected to be waveform-area based but will be
  designed separately, per the task's own explicit note) — keeping
  `region` as a per-annotation field is cheap and avoids re-adding it
  later, while the sidebar-specific MACHINERY (overlay, cross-region
  classification, reparenting) that had no other consumer was removed.

Impact:

- `frontend/index.html`/`frontend/theme.css` only. Removed:
  `#wwAnnotationOverlaySidebar` (HTML), `wwDetermineAnnotationRegion()`,
  the sidebar branches of `wwAnnotationRegionEl()`/`wwAnnotationOverlayEl()`,
  `#workspaceSidebar`'s annotation-only `position: relative`, the
  sidebar-targeting placement-mode cursor rule. Simplified:
  `wwWireAnnotationDrag()` (no `liveRegion`/reparenting), `wwRenderAnnotations()`
  (one overlay, one region, plus the sidebar→main coercion above),
  `wwAnnotationPlacementClickHandler()` (main-only target check).
- Does not change the generic annotation framework, record shape (beyond
  `region`'s narrowed valid-value set for `text_note`), lifecycle,
  Annotation List, editing, or XSS-safe rendering.
- See [MIGRATION_PLAN.md — Phase 4E-UAT2](MIGRATION_PLAN.md#phase-4e-uat2--free-text-notes-restricted-to-main-waveform-workspace-2026-08-21).

---

## DEC-045 — Callout is a waveform-anchored annotation type, analog only this phase, with a fixed engineering anchor and a movable presentation box

Date: 2026-08-21
Status: Approved
Source: explicit owner-approved direction for Phase 4F ("Analog Waveform
Callout Annotation").

Decision:

Oruxa Powerwave's SECOND annotation type, `type: "callout"`, reusing the
EXACT SAME generic framework DEC-044 established (`ww.annotations` remains
the sole state authority — no parallel Callout registry) rather than a
purpose-built callout subsystem:

> Callout annotations are analog waveform/data-anchored annotations. The
> anchor snaps once at creation to the nearest authoritative full-
> resolution recorded sample for the clicked source/channel. Anchor
> engineering identity remains fixed through zoom, pan, time-mode
> changes, adaptive display reduction, and layout changes. The Callout
> box is presentation-only and may be dragged relative to the fixed
> anchor.

- **Fundamentally different anchoring model from Text Note**: DEC-044's
  `text_note` is workspace-content-anchored (a `#activeViewArea`
  content-pixel position, immune to zoom/pan). `callout` is
  waveform/data-anchored — it consists of one authoritative analog
  sample anchor, one editable floating text box, one connector line, and
  one anchor marker. `Annotation.data` for `callout` is
  `{text, sourceId, channelName, sampleIndex, anchorElapsedSeconds,
  anchorValue, unit, boxOffset: {x, y}}` — `anchorElapsedSeconds`/
  `anchorValue` are the fixed engineering anchor (never Absolute
  timestamp, which stays derived as recording start + elapsed, per the
  project's own existing convention); `boxOffset` is a screen-independent
  pixel offset from the anchor's own current projection (preferred over
  a fixed content-anchored box position specifically so the label stays
  spatially near its anchor through zoom/pan instead of drifting into an
  unrelated position with an ever-lengthening connector).
- **Analog only this phase** — digital Callout, RMS/phasor/peak/delta/
  event-marker annotation types, cross-channel annotation, rich text/
  Markdown, callout import/export, and permanent database persistence
  are all explicitly out of scope (see Impact).
- **Anchor resolution authority**: snaps to the nearest ACTUAL full-
  resolution recorded sample — never the displayed (possibly min/max-
  envelope-reduced) Plotly trace, never interpolated, never raw pointer-X
  alone. Reuses the EXACT nearest-sample/earlier-sample-on-tie logic
  `.../cursor-values` (DEC-040) already established, via a new backend
  service function (`resolve_annotation_anchor`) and a new endpoint
  (`POST .../sources/{source_id}/annotation-anchor`) — deliberately not a
  second nearest-sample definition, and deliberately not a persistent
  annotation backend (this endpoint answers ONE question: "what is the
  nearest real sample to this approximate time, on this channel," called
  exactly once per Callout, at creation time only).
- **Trace identity resolution**: clicking a Grouped/Custom panel with
  multiple traces, or a Separate-mode lane, resolves the EXACT clicked
  channel via each trace's own stable `"sourceId::channelName"` `meta`
  field (already stamped on every trace by `wwBuildTrace()`, an existing
  Phase 4A-UAT7 convention) — never curveNumber alone, never "the first
  trace in the panel."
- **Anchor is fixed after creation; the box alone is draggable**: no
  re-anchoring/move-anchor capability this phase (a future "Move Anchor"
  is a separate design). Dragging the box updates ONLY `data.boxOffset`
  — never the anchor, never a backend call, never a Plotly rebuild.
- **Reprojection, not re-resolution**: the anchor's screen position is
  recomputed on every relevant geometry change (X viewport, Y range,
  panel layout, resize, scroll, channel visibility) via the SAME shared
  X-projection authority (`wwCursorTimeToPixelX`) A/B cursors already use
  plus a new per-panel Y-projection authority built the same way from
  that panel's own live Plotly `_fullLayout.yaxis` — never a second
  backend round trip.
- **Visibility, not deletion, for a currently-unprojectable anchor**: a
  Callout whose anchor is outside the current X viewport, outside the
  panel's current Y range, or whose channel is not currently displayed,
  is hidden from canvas (box/connector/marker) but stays fully intact in
  `ww.annotations` and the Annotation List — reappearing the moment it
  becomes projectable again.
- **Source removal deletes its Callouts outright** (not merely hides
  them) — their anchor no longer exists server-side once the source is
  removed, and no other source is ever silently substituted for a
  same-named channel.

Reason:

Detego-benchmark-informed (per the project's own Detego Benchmark
Principle, DEC-020) but an independent Oruxa implementation: a data-
anchored callout is standard waveform-analysis tooling, and the owner's
own explicit requirement (full-resolution sample authority, never a
reduced/approximate anchor) mirrors the SAME engineering-integrity bar
DEC-040 already set for A/B cursor measurements — reusing that exact
nearest-sample logic keeps the codebase with ONE nearest-sample
definition, not two that could silently drift apart.

Alternatives considered:

- **A separate Callout-specific annotation subsystem** (own Map, own
  drawer, own render pass) — rejected per the owner's own explicit
  instruction; `ww.annotations` remains the one authority, with
  `wwRenderAnnotations()` dispatching on `annotation.type` (section 52 of
  the task) exactly as DEC-044 already established for a future type.
- **Storing the box at a fixed content-anchored position** (like Text
  Note) instead of an anchor-relative offset — rejected: a zoom/pan would
  move the anchor while the box stayed put, producing an arbitrarily long
  or nonsensical connector; the anchor-relative `boxOffset` model keeps
  the engineer's chosen spatial relationship stable instead.
- **Reusing/overloading `.../cursor-values` for anchor resolution** —
  rejected as an awkward semantic overload (that endpoint's own contract
  is "value at an EXISTING cursor time for N channels," not "resolve and
  return sample IDENTITY for one channel at one approximate time"); a
  small, focused `.../annotation-anchor` endpoint reusing the SAME
  underlying nearest-sample function is cleaner without duplicating logic.
- **Plotly shapes/annotations for the connector and marker** — rejected
  (section 54 of the task): would require a Plotly rebuild/restyle on
  every drag/zoom/pan, violating the "zero Plotly calls during
  reprojection" performance requirement; a lightweight SVG layer
  (`#wwCalloutConnectorLayer`), a genuine DOM child of the same
  content-anchored overlay `.ww-annotation` boxes already live in, gives
  precise geometry with plain style/attribute writes instead.

Impact:

- Backend: `app/services/waveform_service.py` (`AnnotationAnchorResult`,
  `resolve_annotation_anchor`, reusing `_resolve_analog_channel`/
  `_nearest_sample_index`), `app/schemas/annotation_anchor.py` (new),
  `app/api/v1/sources.py` (`POST .../annotation-anchor`). No new
  persistent storage; `WorkspaceRegistry`'s existing in-memory
  `ActiveSource` retention is the only "backend state" touched, read-only.
- Frontend: `frontend/index.html` (Annotate menu's second item; the
  `plotly_click`-based placement path, wired per analog panel via
  `wwWireAnalogPanelClick()`; `wwRenderAnnotations()` extended to
  dispatch box/connector/marker geometry for `callout`; a new
  `#wwCalloutConnectorLayer` SVG; `wwWireCalloutBoxDrag()`, a genuinely
  different drag model from Text Note's own `wwWireAnnotationDrag()`;
  reprojection hooked into the SAME trigger surface
  `wwUpdateCursorOverlay()` and `wwWirePanelRelayout()`'s Y-range branch
  already react to, plus the 3 channel-visibility call sites and source
  removal), `frontend/theme.css` (`--annotation-callout-accent`, Light +
  Dark).
- Does NOT change DEC-044's own Text Note behavior, DEC-040 (A/B cursor
  architecture — Callout is fully independent of it, never reads/writes
  `ww.measurementCursors`), DEC-041/042 (adaptive resolution, numeric
  elapsed coordinates — Callout's anchor deliberately bypasses adaptive
  reduction, reading full-resolution data directly), or DEC-043 (step
  zoom/icon toolbar).
- Explicitly NOT implemented this phase: digital Callout, draggable/
  re-anchorable anchor, RMS/phasor/peak/delta/event-marker annotation
  types, cross-channel annotation, rich text/Markdown, callout import/
  export, permanent database persistence, elbow/auto-routed connectors,
  auto-scroll-to-annotation navigation from the Annotation List.
- See [MIGRATION_PLAN.md — Phase 4F](MIGRATION_PLAN.md#phase-4f--analog-waveform-callout-annotation-2026-08-21).

### ADDENDUM (2026-08-21, refinement) — Callout anchors became movable, same-channel only (Phase 4F-UAT)

Status: Approved
Source: owner-approved direction following Phase 4F UAT ("Movable Analog
Callout Anchor").

Supersedes DEC-045's own Impact bullet listing "draggable/re-anchorable
anchor" as explicitly not implemented -- that line is left as-is above
(historical record of the original decision, not rewritten); this
addendum records the refinement on top of it:

> Callout anchors became user-movable following owner UAT. Anchor
> movement is restricted to the Callout's existing source/channel.
> During drag, pointer X is only a presentation preview; on release the
> anchor is re-resolved to the nearest authoritative full-resolution
> recorded sample. Source/channel identity remains unchanged. Cross-
> channel re-anchoring is not implemented.

Decision:

- The anchor marker itself (not just the label box) is now draggable, via
  a larger (~16px) invisible hit target laid over the small (~8px)
  visible marker -- the marker's own visual size is unchanged.
- **Same-channel only**: dragging can move the anchor to a different
  sample on its OWN existing `sourceId`/`channelName`, never to a
  different channel, even when the pointer visually crosses another
  trace in a Grouped/Custom panel. Cross-channel re-anchoring would
  create real engineering ambiguity in exactly that scenario and is
  deliberately deferred to a possible future "Change Anchor Channel"
  interaction, not built now.
- **Preview, then authoritative snap**: during the drag, pointer X maps
  to an approximate elapsed time (via the SAME `wwCursorPixelXToTime()`
  authority A/B cursor dragging already uses, which already clamps to
  the current `ww.viewport`) and moves the marker/connector/box as a
  purely visual preview -- `annotation.data` is never written to during
  this phase, and pointer Y is never read at all (the marker's preview Y
  stays pinned to the CURRENT authoritative `anchorValue`'s own
  projection, since engineering Y must always come from a real recorded
  sample, never the pointer). Exactly ONE backend request
  (`POST .../annotation-anchor`, the SAME endpoint and nearest-sample
  logic DEC-045 already established) fires on pointer release, reusing
  the existing source's own bounds as an additional clamp. On success,
  only `sampleIndex`/`anchorElapsedSeconds`/`anchorValue`/`unit` are
  committed -- `sourceId`/`channelName`/`boxOffset` are untouched. On
  failure, Escape, or `pointercancel`, the original authoritative anchor
  is restored by simply re-rendering from the never-touched
  `annotation.data` (there is nothing to "undo" a snapshot for, since
  nothing was written during the preview).
- **Stale-response protection reused verbatim**: workspace epoch/id
  checks plus a live `ww.annotations.has(id)` check (new, for "the
  Callout itself was deleted mid-request") guard the resolution
  response, matching the exact pattern DEC-045's own creation path
  already established.

Reason:

The owner's own explicit engineering-integrity rule from DEC-045 itself
("a Callout anchor must always resolve to an actual full-resolution
recorded sample") extends naturally to a MOVED anchor -- the only
addition needed was routing a drag interaction through the exact same
authoritative resolution path already built for creation, never a
second, looser one.

Alternatives considered:

- **Allow cross-channel re-anchoring now** (drag onto a different trace
  entirely) -- rejected: Grouped/Custom panels may contain multiple
  traces close together or crossing, and silently reassigning a Callout
  to whichever trace the pointer happens to be nearest at release would
  create real ambiguity about which channel's data a Callout actually
  represents. Deferred to a separate future design.
- **Resolve on every pointermove** -- rejected on both engineering and
  performance grounds: it would flood the backend with requests during a
  single drag gesture and make the visible marker briefly show
  potentially-stale intermediate resolutions; a frontend-only preview
  plus one resolution on release is both cheaper and always shows either
  a clearly-provisional preview or a fully authoritative result, never
  something in between presented as authoritative.

Impact:

- `frontend/index.html` only. New: `wwWireCalloutAnchorDrag()` (event
  delegation on `#wwCalloutConnectorLayer`, the same convention
  `wwWireCursorDrag()` established for A/B cursors), `wwResolveCalloutAnchorMove()`
  (reuses the creation path's own request/error/stale-response shape).
  `wwUpdateCalloutConnectorGeometry()` extended with an invisible hit-
  target circle and a `dragging` visual-state parameter.
- `frontend/theme.css`: no new tokens -- reuses `--annotation-callout-accent`.
- Does not change DEC-044 (Text Note), DEC-045's own creation path,
  trace-identity resolution, rendering architecture, or any other
  Callout lifecycle rule (visibility, source removal, workspace
  lifecycle) established by the original decision above.
- See [MIGRATION_PLAN.md — Phase 4F-UAT](MIGRATION_PLAN.md#phase-4f-uat--movable-callout-anchor-2026-08-21).

### ADDENDUM (2026-08-21, refinement) — Anchor drag preview became free 2D (Phase 4F-UAT2)

Status: Approved
Source: owner UAT result on the movable-anchor addendum directly above --
"Engineering outcome: PASS. User experience: FAIL" (constraining the
preview marker to horizontal-only movement felt like dragging along a
rail, even though the final snap was already correct).

> Anchor drag preview became free 2D following owner UAT. Pointer X and
> Y both control temporary visual preview, but only pointer X
> participates in authoritative re-anchoring. Pointer Y never becomes
> engineering value authority; on release the anchor snaps to the
> nearest full-resolution sample on the existing source/channel.

Decision:

- During drag, the preview marker/connector/box now follow the pointer
  FREELY in both X and Y (previously: X followed the pointer, Y stayed
  pinned to the current authoritative `anchorValue`'s own projection).
  Purely a presentation change -- `annotation.data` is still never
  written to during the preview (unchanged from the addendum above).
- **Final resolution is completely unchanged**: `onPointerUp()` still
  reads `event.clientX` alone (via `wwCursorPixelXToTime()`) to derive
  the approximate elapsed time sent to `POST .../annotation-anchor`;
  `event.clientY` is never read there, at any point. The backend's
  resolved `value` (a real recorded sample) becomes the new
  `anchorValue` -- never anything derived from where the pointer
  happened to be vertically.
- Preview X/Y are each clamped to "sensible bounds" for pure visual
  containment (X to the shared plot X domain, Y to the anchored
  channel's own current panel rect) -- never used as, or conflated
  with, engineering authority.
- Added a subtle translucency to the existing "stronger ring while
  dragging" visual state, so the free-floating preview reads as visibly
  provisional right up until it snaps to the authoritative sample on
  release.

Reason:

The underlying engineering model (DEC-045 itself, and the same-channel-
only movable-anchor addendum above) was already correct and did not
need to change -- only the PRESENTATION of the drag felt wrong. Since
pointer Y was already discarded before any engineering decision was
made, letting it drive the VISUAL preview costs nothing to correctness:
the exact same `onPointerUp()` code path, unmodified, still ignores it.

Alternatives considered:

- **Keep Y pinned to the current value's projection, only smooth the
  transition** -- rejected: this was the exact behavior the owner
  explicitly reported as feeling constrained ("like dragging along a
  rail"); a smoother transition would not address the root complaint
  that the marker didn't follow the mouse.
- **Let released Y somehow influence the resolved sample** (e.g. as a
  tie-breaker or secondary signal) -- rejected outright per the task's
  own explicit instruction and DEC-045's own engineering-integrity rule:
  `anchorValue` must always come from an actual recorded sample on the
  channel's own real waveform, never from where the pointer happened to
  be released vertically.

Impact:

- `frontend/index.html` only. `wwWireCalloutAnchorDrag()`'s own
  `livePreviewUpdate()` simplified to take an already-resolved
  `{previewPageX, previewPageY}` pair instead of deriving Y from
  `wwCalloutValueToPixelY()`+the current `anchorValue`; a new
  `clampPreviewPoint()` helper provides the X/Y visual bounds.
  `onPointerUp()` itself is textually unchanged (still X-only).
  `frontend/theme.css`: no new tokens.
- Does not change DEC-045's own creation path, the same-channel
  restriction, the `/annotation-anchor` endpoint, nearest-sample/tie-
  break semantics, or any other Callout lifecycle rule.
- See [MIGRATION_PLAN.md — Phase 4F-UAT2](MIGRATION_PLAN.md#phase-4f-uat2--free-2d-callout-anchor-drag-preview-2026-08-21).

## DEC-046 — Maximum/Minimum Peak annotations are generic recorded-channel measurements over the current visible X viewport, dynamically recalculated on genuine X-viewport changes

Date: 2026-08-21
Status: Approved
Source: explicit owner-approved direction for Phase 4G ("Dynamic Maximum /
Minimum Peak Annotation").

Decision:

Oruxa Powerwave's THIRD and FOURTH annotation types, `type: "peak_max"`
and `type: "peak_min"`, reusing the EXACT SAME generic framework DEC-044/
DEC-045 established (`ww.annotations` remains the sole state authority —
no parallel Peak registry):

> Maximum Peak (+Peak) and Minimum Peak (-Peak) are generic recorded
> analog channel annotations calculated from authoritative full-resolution
> source samples within the current visible X viewport. Channel identity
> is fixed after creation, but peak sample/time/value are dynamic and are
> recalculated whenever the X viewport changes. Exact ties select the
> earliest sample. Peak anchors are calculated/non-draggable; label boxes
> are movable. Y-range changes and Absolute/Elapsed presentation changes
> do not trigger recalculation.

- **Generic recorded-channel semantics, no waveform-type assumption**: a
  +Peak/-Peak is the maximum/minimum of whatever a channel's own recorded
  Y-axis values are — MW, kV, Hz, pu, instantaneous voltage, RMS, or any
  other recorded analog quantity. No Peak-to-Peak type this phase.
- **Live viewport measurement, not a one-time snapshot** (the key
  difference from Callout, DEC-045, whose anchor is fixed forever after
  creation): the search interval is always the CURRENT `ww.viewport` —
  never the whole recording, never the reduced/adaptive display
  representation, never an A/B cursor interval. `Annotation.data` for
  `peak_max`/`peak_min` is `{sourceId, channelName, mode, sampleIndex,
  peakElapsedSeconds, peakValue, unit, available, boxOffset: {x, y}}` —
  `sourceId`/`channelName`/`mode`/`boxOffset` are STABLE for the
  annotation's lifetime; `sampleIndex`/`peakElapsedSeconds`/`peakValue`/
  `unit`/`available` are DYNAMIC, recalculated in place (same annotation
  id, never a new one) whenever the X viewport genuinely changes (zoom,
  pan, step zoom, Reset Time View) — reusing the ONE existing call site
  every such change already funnels through, `wwApplyAndFetchViewport()`.
  Y-range changes, Autoscale Y, Absolute/Elapsed presentation switching,
  and box drags never trigger recalculation (they don't change the search
  interval).
- **Full-resolution authority, boundary-inclusive range clipping**: a new
  backend service function (`resolve_peak_value`) reads
  `active.record.waveform_data` directly — the SAME authoritative record
  `resolve_annotation_anchor`/`extract_waveform_range` already read —
  never the reduced display envelope, clipped to the requested interval
  via the SAME `np.searchsorted` technique already established, further
  narrowed to the channel's own recorded bounds when the viewport extends
  beyond them (never fabricating samples).
- **Earliest-tie rule**: exact ties select the EARLIEST sample — satisfied
  for free by `numpy.argmax`/`argmin`'s own documented first-occurrence
  behaviour on ties, not a second hand-rolled tie-break implementation.
- **Non-finite samples are ignored, never selected**: `np.isfinite`
  masking before the max/min search; if every sample in the interval is
  non-finite (or the intersection is empty), the result is
  `available: false` — never a fabricated/NaN peak.
- **Batched per source, one request per viewport change** — a NEW,
  separate endpoint, `POST .../sources/{source_id}/peak-values`, accepting
  a list of `{channel_name, mode}` pairs plus one shared
  `start_time`/`end_time`, mirroring `.../cursor-values`' own established
  per-source batching (never one request per annotation, never merging two
  sources' requests together). Deliberately a NEW endpoint, not an awkward
  overload of `.../annotation-anchor` (peak semantics — dynamic,
  viewport-scoped, batched — are genuinely distinct from Callout's
  one-shot fixed-anchor resolution).
- **Unavailable, not deleted, when a viewport has no valid sample**: a
  per-item `available: false` in the batch response (never failing the
  whole batch for one bad/out-of-range channel) preserves the
  annotation's identity in `ww.annotations`/the Annotation List, hides its
  canvas representation, and is replaced by a fresh valid result the
  moment a later viewport change resolves one again.
- **Peak anchor is calculated and NOT draggable** (the key interaction
  difference from Callout's own now-movable anchor, DEC-045's addenda):
  the SAME shared connector/marker geometry engine
  (`wwUpdateCalloutConnectorGeometry()`, extended with an `isPeak` flag)
  renders both types, but the global anchor-drag pointer handler now
  checks `annotation.type === "callout"` before starting any drag preview
  — a Peak's hit circle presents no grab cursor and is not hit-testable at
  all (`pointer-events: none`). The label BOX remains fully draggable,
  identical mechanics to Callout's own `wwWireCalloutBoxDrag()` (offset-
  only, never touches the anchor, never calls the backend).
- **Trace identity resolution**: identical mechanism to Callout — each
  trace's own stable `"sourceId::channelName"` `meta` field, never
  curveNumber alone; unlike Callout, the CLICKED X position is irrelevant
  to a Peak's own value (only the clicked trace's channel identity
  matters — the search interval is always the current viewport).
- **Source removal deletes its Peak annotations outright**, generalizing
  the SAME sweep DEC-045 already established for Callout
  (`wwRemoveAnchoredAnnotationsForSource()`, renamed from its Callout-only
  predecessor to cover both waveform-anchored types) — no rebinding by
  same channel name on a different source.
- **Distinct accent, not alarm red or A/B cursor colors**: a new shared
  `--annotation-peak-accent` token (muted teal-green, both themes) —
  deliberately not `--error` (A/B cursor "B"/red — section 25's own
  explicit "do not use alarm red just because it is a maximum/minimum"),
  not `--accent` (A/B cursor "A"/blue), and not Callout's own amber. The
  `+Peak`/`-Peak` label prefix and header glyph (filled triangle, apex
  up/down), not color, is what distinguishes maximum from minimum.

Reason:

The owner's own explicit direction: Peak annotations must be GENERIC
recorded-channel measurements (never an instantaneous-voltage-only or
similar type-specific assumption), and must be LIVE viewport measurements
(recalculating as the engineer zooms/pans), unlike Callout's deliberately
fixed anchor — this is the fundamental behavioral difference driving most
of the design above. Reusing Callout's shared geometry/rendering
infrastructure (per the task's own explicit "do not duplicate an entirely
separate geometry engine" instruction) keeps the codebase with ONE
anchored-annotation projection system, dispatching by type only where the
two genuinely differ (interaction — draggable vs. not; and engineering
authority — fixed vs. dynamically recalculated).

Alternatives considered:

- **One request per annotation, always** — rejected as the default
  design; a source-scoped BATCH request (mirroring `.../cursor-values`)
  was chosen from the outset per the task's own "preferred scalable
  design" guidance, since a workspace can reasonably hold several active
  Peak annotations on one source.
- **Overloading `.../annotation-anchor` for Peak resolution too** —
  rejected: that endpoint's own contract (single fixed sample identity at
  an approximate time) doesn't fit Peak's genuinely different shape
  (a channel/mode pair resolved over an INTERVAL, batched, called
  repeatedly for the SAME annotation's lifetime) — a small, focused new
  endpoint stays clearer than forcing two different semantics through one
  contract.
- **Failing the whole batch when one channel is unavailable** — rejected:
  would blank out every other channel's otherwise-valid peak in the same
  request; a per-item `available` flag (section 12/67 of the task)
  preserves independence, matching `extract_cursor_values`' own
  established per-channel resilience philosophy.
- **Making the Peak anchor draggable like Callout's** — rejected outright
  per explicit owner instruction (section 21); a Peak's position is
  entirely a function of viewport + source data, never a user override.
- **Persisting recalculation results even through a channel-hidden
  state (skip recalculation while hidden, resolve only on re-show)** —
  rejected in favor of the simpler, more consistent policy actually
  implemented: recalculation runs on every genuine viewport commit
  REGARDLESS of the annotation's channel's current display visibility (the
  backend computation is cheap array-index work, independent of Plotly);
  visibility only gates whether the already-current result is PROJECTED
  onto canvas. This guarantees a re-shown channel's Peak is always current
  for the present viewport with zero extra "on-show recalculate" logic.

Impact:

- Backend: `app/services/waveform_service.py` (`PeakValueResult`,
  `resolve_peak_value`, reusing `_resolve_analog_channel`), a new
  `app/schemas/peak_value.py`, `app/api/v1/sources.py`
  (`POST .../peak-values`). No new persistent storage.
- Frontend: `frontend/index.html` (2 new Annotate menu items; `plotly_click`
  extended in `wwWireAnalogPanelClick()` to dispatch peak creation;
  `wwCreatePeakFromClick()`, `wwRecalculatePeakAnnotationsForSource()`,
  `wwRecalculateAllPeakAnnotations()` — hooked into the ONE
  `wwApplyAndFetchViewport()` call site; `wwAnchoredAnnotationContentPosition()`/
  `wwAnchoredAnnotationPagePosition()`/`wwAnchorValueToPixelY()` generalized
  from their Callout-only predecessors to serve both types via 2 small
  type-dispatching getters; `wwUpdateCalloutConnectorGeometry()` extended
  with an `isPeak` parameter; `wwRemoveAnchoredAnnotationsForSource()`
  renamed/extended from its Callout-only predecessor; `wwPeakBodyHtml()`,
  `wwPeakValueLineText()`, `wwPeakLabelLines()`), `frontend/theme.css`
  (`--annotation-peak-accent`, Light + Dark).
- Does NOT change DEC-044's Text Note behavior, DEC-045's Callout behavior
  (creation, anchor-drag, box-drag all unchanged — Peak shares rendering
  infrastructure but never its own request/state), DEC-040/041/042
  (A/B cursors, adaptive resolution, numeric elapsed coordinates), or
  DEC-043 (step zoom/icon toolbar) — Peak recalculation reuses the step
  zoom/Reset Time View call sites read-only, adding no new synchronization
  loop.
- Explicitly NOT implemented this phase: peak-to-peak, RMS-from-waveform/
  cycle-RMS calculation, phasor angle, delta measurement, event marker,
  cross-channel peak, digital peak, peak anchor dragging, automatic A/B
  placement at peaks, a whole-record/current-window toggle, a custom peak
  search interval independent of the viewport, annotation import/export,
  permanent database persistence.
- See [MIGRATION_PLAN.md — Phase 4G](MIGRATION_PLAN.md#phase-4g--dynamic-maximum--minimum-peak-annotation-2026-08-21).

### ADDENDUM (2026-08-21, refinement) — Persistent annotation placement guidance ribbon (Phase 4G-UAT)

Status: Approved
Source: owner UAT result on Phase 4G directly above — "Engineering
behavior: PASS" but "after the user selects Maximum Peak or Minimum Peak
from the Annotate dropdown, there is no clear guidance telling them what
to do next."

> Annotation placement modes that require a subsequent user action
> provide persistent inline guidance while active. For +Peak/-Peak, the
> guidance instructs the user to click an analog waveform channel and
> remains until successful selection or Escape cancellation. Invalid
> clicks do not dismiss the active placement mode.

Decision:

- **One generic ribbon, driven entirely by `ww.annotationPlacementType`**
  (the SAME single authority `wwEnterAnnotationPlacementMode()`/
  `wwExitAnnotationPlacementMode()` already are) — a new
  `WW_ANNOTATION_PLACEMENT_GUIDANCE` map (`{icon, message}` per type) plus
  `wwAnnotationPlacementGuidance(type)`/
  `wwUpdateAnnotationPlacementGuidance()`, called ONLY from the two
  existing state-transition functions, never per-render and never a
  second competing state or timer.
- **Mandatory for `peak_max`/`peak_min`** (the owner's explicit
  requirement); **also enabled for `text_note`/`callout`** — the same
  generic map covers them with no extra branching, and the task's own
  section 5 invited this "if extremely straightforward and clearly
  generic," which it was.
- **A normal-layout sibling row**, `#wwAnnotationGuidance`, placed between
  the waveform toolbar and `#activeViewArea` — never `position:
  absolute/fixed`, so it structurally cannot overlay/intercept Plotly,
  the channel sidebar, or the toolbar (section 6/20); it simply narrows
  the waveform area's own available height by one compact row while
  visible.
- **Peak's own completion timing changed to match the ribbon's semantics
  (section 10/17 of the task)**: unlike Callout, whose established
  one-shot "exit immediately on click, regardless of outcome" timing
  (Phase 4F) is UNCHANGED, `wwCreatePeakFromClick()` now exits placement
  mode ONLY upon reaching a successful creation — a failed request, a
  no-valid-samples (`available: false`) result, or a network error all
  leave placement mode (and the ribbon) active so the engineer can retry
  immediately, without reselecting the tool. A new `ww.annotationPlacementBusy`
  flag (set/cleared via `try/finally` around the whole request) is the
  one-request-at-a-time guard this longer-lived active window now needs —
  a second click while a Peak request is in flight is silently ignored,
  never a duplicate concurrent request.
- **No auto-dismiss timer anywhere** — the ribbon's only visibility
  authority is `ww.annotationPlacementType`; verified directly (many
  ticks/re-renders while mode stays active, ribbon never disappears).
- **Accessibility**: `role="status"` (implicit `aria-live="polite"`) —
  informational, never an aggressive alert — updated only on the two
  state transitions, so assistive tech is never re-announced on ordinary
  waveform re-renders (zoom/pan/recalculation).
- **Styling reuses existing semantic tokens only** (`--accent-wash-soft`,
  `--panel-border`, `--text`, `--text-dim`, `--accent`, `--radius`) — no
  new theme tokens, no red/alarm styling.

Reason:

The owner's own explicit UAT finding: engineering behavior was correct,
but the UX left the engineer with no indication of what a just-selected
tool expected next. A persistent, generic, placement-mode-driven ribbon
closes that gap for every current (and future) annotation type with one
small, reusable mechanism rather than a scattered per-type banner.

Alternatives considered:

- **A toast/notification framework** — rejected per the task's own
  explicit scope exclusion; a single always-in-place ribbon element is
  sufficient and simpler.
- **Auto-dismiss after a fixed delay** — rejected outright; the owner's
  own explicit requirement is persistence until successful completion or
  Escape, with no drifting timer-based state.
- **Keeping Callout's exit-immediately timing for Peak too** (simpler,
  no new busy-flag) — rejected: it would make the new ribbon
  disappear the instant the engineer clicks, even on a failed/no-data
  result, defeating the entire purpose of "so user may try again"
  (section 17's own explicit instruction).
- **A close/dismiss "X" on the ribbon** — rejected per the task's own
  explicit scope exclusion (a user-dismissable close that leaves
  placement mode active would desynchronize the ribbon from the single
  state authority it is meant to mirror exactly).

Impact:

- `frontend/index.html` only. New: `#wwAnnotationGuidance` markup (a
  sibling between `#wwToolbar` and `#activeViewArea`), its CSS,
  `WW_ANNOTATION_PLACEMENT_GUIDANCE`, `wwAnnotationPlacementGuidance()`,
  `wwUpdateAnnotationPlacementGuidance()`, `ww.annotationPlacementBusy`.
  Modified: `wwEnterAnnotationPlacementMode()`/
  `wwExitAnnotationPlacementMode()` (call the new guidance updater;
  reset the busy flag on entry), `wwWireAnalogPanelClick()` (Peak no
  longer exits mode before dispatching creation; Callout's own timing
  untouched), `wwCreatePeakFromClick()` (busy-flag guard,
  exit-only-on-success). No backend change.
- Does not change DEC-044's Text Note engineering behavior, DEC-045's
  Callout engineering behavior (its own placement-mode exit timing is
  explicitly, deliberately unchanged), or DEC-046's own Peak
  calculation/recalculation/tie-rule/full-resolution semantics — this
  addendum is a UX/completion-timing refinement only.
- See [MIGRATION_PLAN.md — Phase 4G-UAT](MIGRATION_PLAN.md#phase-4g-uat--persistent-annotation-placement-guidance-ribbon-2026-08-21).

**Update (2026-08-21, same day, bug fix — no new decision entry)**: owner
UAT on the ribbon above found it visually did not disappear after a
successful Peak creation, and separately that Escape did not visually
dismiss it either. Root cause (identical for both symptoms): a CSS-cascade
bug, not a state bug — `.ww-annotation-guidance { display: flex; }`
(author CSS) beat the UA stylesheet's own `[hidden] { display: none }`
rule by ORIGIN alone, so `wwUpdateAnnotationPlacementGuidance()`'s own
`el.hidden = true` (already correctly reached on both the successful-
creation path and the Escape path — confirmed directly, `ww.annotation
PlacementType` was already `null` in both cases) had zero visible effect.
Fixed with one line, `.ww-annotation-guidance[hidden] { display: none;
}`, the SAME already-established pattern this codebase uses for
`#workspaceRow[hidden]`/`.shell-status-item[hidden]`/`#pageRecordings[hidden]`/
`.ww-toolbar[hidden]`. While investigating the Escape case specifically, a
second, genuine (non-CSS) race was found and fixed: a Peak creation
request already in flight when Escape (or any new placement session) was
initiated could still resolve successfully afterward and create an
annotation from a session the engineer had already left. Fixed with a new
monotonic `ww.annotationPlacementGeneration` counter, bumped on every
genuine placement-mode transition (entering fresh/switching tools,
exiting via success or Escape — never a same-tool reselect no-op) and
checked by `wwCreatePeakFromClick()` before creating anything; a stale/
superseded request's result — success or failure — is now discarded
silently, with zero UI side effect for a session the user already
abandoned. `frontend/index.html` only; no backend change; extended
`phase4g_check.mjs` with 13 new checks (a structural regression guard for
the CSS `[hidden]` override rule itself, the full async successful-
creation path, -Peak Escape, invalid-click-then-Escape, API-failure-then-
Escape, Escape-during-an-in-flight-request with stale-result discard, a
same-tool retry after an Escape-cancelled request, toolbar-active-state +
busy-flag invariants, and Text Note/Callout Escape regressions) —
**66/66 passing** in the file overall. Full frontend suite reconfirmed at
the true 33-failure baseline; backend untouched, 436/436 unchanged.

## DEC-047 — Calculated Channels are workspace-scoped derived analog channels from authoritative full-resolution inputs, requiring proven synchronized sample-time alignment for multi-input operations

Date: 2026-08-21
Status: Approved
Source: explicit owner-approved direction for Phase 5A ("Calculated
Channels / Basic Signal Builder"), tightened mid-implementation by an
explicit owner time-alignment guardrail message.

Decision:

Oruxa Powerwave's first mathematical signal-derivation system — NOT an
annotation tool. A new main-sidebar page, "Calculated Channels" (placed
immediately below Table), is both a Signal Builder and a Calculated
Channel Manager on one page:

> Calculated Channels are workspace-scoped derived analog channels
> generated from authoritative full-resolution analog/calculated inputs.
> Phase 5A supports Reverse Polarity, Absolute Value, Multiply by
> Constant, N-input Addition, and ordered N-input Subtraction.
> Multi-input operations require compatible units and a compatible
> authoritative time base; no interpolation/resampling is performed.
> Calculated channels may depend on other calculated channels, with
> explicit dependency tracking and cycle prevention. Original recording
> data remains immutable.

> Multi-input calculated channels are permitted only when every operand
> is proven to share the same authoritative synchronized sample-time
> axis. Equal sample count, equal sampling rate, or visual overlap alone
> are insufficient. Phase 5A does not interpolate, resample, time-shift,
> crop-to-overlap, or otherwise align incompatible inputs.

- **Five basic operations only** (section 6/71/72): Reverse Polarity
  (`y = -x`), Absolute Value (`y = |x|`), Multiply by Constant
  (`y = k*x`, `k` dimensionless — output unit unchanged), N-input
  Addition (`y = x1+x2+...+xN`, `N>=2`), and ordered N-input Subtraction
  (`y = x1-x2-...-xN`, `N>=2`, explicitly left-associative, order
  preserved end to end). RMS, sequence/power/frequency/impedance/
  differential/protection calculations, min/max-across-channels,
  derivative/integration/filtering, and a free-form formula parser are
  ALL explicitly out of scope this phase — not even a disabled RMS card
  is shown.
- **Generic operation-descriptor architecture, never hard-coded to
  "Channel A/Channel B"** (section 7/8): unary operations take exactly 1
  input; Addition/Subtraction take 2-or-more ORDERED inputs (an explicit
  list with add/remove/reorder controls, never an arbitrary 2-channel
  model). Duplicate inputs are explicitly allowed (`A+A`/`A-A` are
  mathematically valid, never silently deduplicated).
- **Full-resolution authority, non-negotiable** (section 15/48/49): every
  operation evaluates against `active.record.waveform_data` directly (or
  another calculated channel's own already-evaluated full-resolution
  result) — never Plotly trace arrays, the `min_max_envelope` display
  representation, or any other reduced/browser-rendered samples. Eager
  evaluation at creation time (section 46) — computed ONCE, retained
  server-side in a workspace-scoped in-memory registry exactly like
  `ActiveSource.record` retains a source's own arrays; never
  re-evaluated on a later waveform/cursor/peak/annotation-anchor
  request.
- **The owner's explicit time-alignment guardrail is a hard engineering
  rule, tightened mid-implementation**: same-source channels are
  provably aligned WITHOUT array comparison (verified directly against
  the actual domain model: one `DisturbanceRecord` has exactly one
  shared `waveform_data["time"]` pandas column for every one of its
  analog channels — no per-channel time array exists anywhere in this
  codebase's source model). Different-source channels are rejected
  UNLESS their true ABSOLUTE instants (`source.start_time + elapsed`, not
  raw elapsed arrays, which two independently-triggered recordings could
  trivially share by coincidence) are proven identical within a
  deliberately tight tolerance (`1e-9` seconds — sub-microsecond, far
  tighter than any realistic sample spacing). Equal sample count or
  equal nominal sampling rate are explicitly, deliberately insufficient
  and never used as a shortcut. No interpolation, resampling, time-
  shifting, or crop-to-overlap is ever performed to make an otherwise-
  incompatible pair usable — an unproven pair is rejected outright, with
  a plain-language message ("These channels cannot be combined because
  their sample times are not aligned.").
- **Unit compatibility** (section 32/33): multi-input operands' unit
  strings must be identical (no dimensional conversion layer exists or
  is introduced) — all-missing is allowed (blank output unit); a mixture
  of known and missing is rejected. Multiply-by-constant's `k` is always
  dimensionless (section 29) — output unit is simply the input's own,
  unchanged.
- **Calculated-from-calculated is supported from Phase 1** (section 22):
  a calculated channel may be selected as an input to a further
  calculation immediately, subject to the SAME timebase/unit
  compatibility rules. Every calculated channel carries a
  `reference_source_id` — the real source that ultimately grounds its
  own (inherited, never modified by any of the 5 operations) time array
  — inherited transitively through arbitrarily deep chains, which is
  what lets both timebase-compatibility checking AND source-removal
  cascade collapse to a simple identity/filter check rather than a graph
  walk at every call site.
- **Explicit dependency tracking + cycle prevention** (section 23/24):
  each calculated channel stores its own DIRECT `dependency_ids`
  (never flattened away). A generic, independently-testable
  `would_create_cycle()` reachability check guards every creation —
  structurally unreachable via the real one-shot creation API today
  (calculated channels are immutable after creation and every referenced
  dependency must already exist before the new id is even minted), but
  implemented as defense in depth per the task's own explicit
  instruction, and unit-tested directly against a hand-constructed graph
  since the real API cannot produce a genuine cycle to test against.
- **Immutable after creation** (section 47): no edit-in-place this
  phase — create another calculated channel for a different formula.
  Delete is dependency-aware (section 25/63): BLOCKED, never a silent
  cascade, while another calculated channel still depends on it, with a
  concise message naming the dependent(s).
- **Source removal cascades transitively** (section 64): removing a
  source removes every calculated channel grounded on it, directly or
  transitively, via the SAME `reference_source_id` filter described
  above — no separate graph-walk implementation.
- **Workspace/session-scoped only** (section 17/65/66): calculated
  channels persist across Waveform &lt;-&gt; Calculated Channels &lt;-&gt;
  Recordings navigation (same workspace, same "hide, don't destroy"
  shell-page mechanism Waveform/Recordings already use — zero
  destruction, zero refetch on ordinary navigation), across Grouped/
  Separate/Custom, Absolute/Elapsed, and zoom/pan. The plain "Clear
  workspace" button is display-only and preserves calculated-channel
  DEFINITIONS (same established policy as every other workspace-scoped
  collection). "Start New Workspace" clears them completely, backend and
  frontend both, through the SAME `DELETE /api/v1/workspaces/{id}`
  endpoint call already used for that purpose (that endpoint's own
  existing docstring had explicitly anticipated calculated channels as a
  future workspace-owned resource needing exactly this one lifecycle
  hook). No permanent database/cloud persistence is introduced.
- **Treated as analog-like PSEUDO-SOURCE channels everywhere in the
  existing rendering/layout/annotation machinery** (section 53/57/58):
  a calculated channel's own server-generated id (`"calc-" + <uuid
  hex>`) is used AS `sourceId`, its own display name AS `channelName` --
  so `wwAddSelectedChannels()`/`wwRemoveChannelByKey()`/`ww.displayed`/
  `ww.channelColors`/Grouped-Separate-Custom/the Annotation List's own
  `sourceId`+`channelName` fields all work COMPLETELY UNCHANGED, with
  zero new branching in any of them (never a second, parallel
  renderer). Waveform display, visibility (ONE authority — the manager's
  own eye icon and the Waveform sidebar's own row both drive/read the
  SAME `ww.displayed`), Grouped/Separate/Custom, and A/B cursor
  values/+Peak/-Peak all work identically to a real source channel.
  Default-hidden on creation (DEC-038's own existing policy, unchanged).
  Callout is ALSO included this phase (the task's own "SHOULD" tier) —
  extending the existing `/annotation-anchor` pattern to a calculated
  channel turned out to require the SAME small increment as A/B and
  Peak, not a disproportionate refactor, so it was not deferred.
- **The one deliberate structural shortcut, reported per section 58's
  own explicit instruction rather than silently taken**: dispatching a
  network request to the calculated-channel endpoint family
  (`/calculated-channels/...`) instead of the source endpoint family
  (`/sources/{id}/...`) is done via ONE small helper,
  `wwIsCalculatedSourceId(sourceId)`, checking the id's own
  `"calc-"` prefix — a lighter-weight mechanism than introducing a fully
  structured `ChannelRef` type (section 57's own suggestion) throughout
  the ENTIRE existing frontend call graph, which section 58 explicitly
  warned against as disproportionate ("do not turn Phase 5A into a
  massive refactor of every existing analog API unless necessary").
  Confined to exactly the request-URL/request-shape dispatch points
  (waveform fetch, cursor-values fetch, peak-values fetch/recalculation,
  Callout creation/anchor-move) — the rendering/layout/state layer never
  needed to know the difference at all.
- **The Signal Builder's own input picker is scoped to `ww.channelMeta`**
  (channels the engineer has already brought into this workspace's
  Waveform at least once this session) plus existing calculated channels
  — a deliberate, reported Phase 1 scope trim (section 58) rather than
  eagerly fetching every channel of every imported source up front.
  After a first input is chosen for a multi-input operation, candidates
  from a different `reference_source_id` are shown DISABLED (never
  silently hidden) in the picker (section 13) — a client-side UX
  shortcut only; the backend remains the sole compatibility authority
  regardless of what the picker allows.

Reason:

The owner's own explicit requirement: calculated channels must be
first-class, full-resolution-authoritative analog channels usable
everywhere a real channel is (section 12), while never compromising the
engineering-integrity guarantee that a calculation only ever combines
samples that genuinely represent the same physical instant. Reusing the
existing waveform/cursor/peak/annotation-anchor pipelines (never a
parallel implementation) keeps this addition proportionate to the rest
of the codebase's own established conventions.

Alternatives considered:

- **A fully structured `ChannelRef` type threaded through every existing
  analog code path** (section 57's own suggestion) — rejected for THIS
  phase per section 58's own explicit "do not turn this into a massive
  refactor" instruction; the pseudo-source-id approach achieves the same
  practical generality (calculated channels participate in every
  existing analog tool unmodified) with a small, contained,
  well-documented shortcut instead.
- **Comparing raw elapsed-time arrays for cross-source alignment** —
  rejected outright per the owner's own explicit correction: two
  independently-triggered recordings can trivially share identical
  elapsed arrays (e.g. both starting at `t=0` at the same rate) without
  representing the same physical instants at all; only true ABSOLUTE
  instants (`start_time + elapsed`) are compared.
- **A loose/generous timing tolerance** — rejected; a `1e-9` second
  tolerance absorbs only genuine floating-point representation noise,
  never a real timing difference, per the owner's own explicit "do not
  use a loose tolerance" instruction.
- **Silently deduplicating a repeated input channel** (`A+A`) — rejected
  per the task's own explicit instruction; mathematically valid,
  reproducible, and the owner's own recommended default.
- **Eagerly fetching every channel of every imported source for the
  input picker** — rejected as disproportionate scope for Phase 1;
  `ww.channelMeta` (already-known channels) is the smallest clean
  abstraction that keeps the builder useful without a new "list every
  channel in every source" subsystem.
- **Cascading delete when a dependent exists** — rejected for Phase 1
  per the task's own explicit preference; blocking is simpler and safer,
  with a clear, actionable message.

Impact:

- Backend (new): `app/domain/calculated_channel.py` (`ChannelRef`,
  `CalculatedChannel`, the five evaluation functions, `units_compatible`,
  `timebases_aligned`, `would_create_cycle`), `app/services/
  calculated_channel_registry.py` (workspace-scoped in-memory registry,
  mirrors `WorkspaceRegistry`'s own shape), `app/services/
  calculated_channel_service.py` (creation orchestration, delete,
  source-removal cascade, display/cursor/peak/annotation-anchor
  pipelines), `app/schemas/calculated_channel.py`, `app/api/v1/
  calculated_channels.py` (new router,
  `/api/v1/workspaces/{id}/calculated-channels...`).
- Backend (modified): `app/services/waveform_service.py` (`_clip_and_reduce`/
  `_peak_in_range` extracted as shared pure array-level helpers, reused
  by BOTH the existing source-channel functions and the new calculated-
  channel service — verified zero behavior change via the full existing
  test suite before adding any new tests), `app/services/errors.py` (9
  new error codes), `app/main.py` (new registry + router wiring),
  `app/api/v1/workspaces.py` (`DELETE /workspaces/{id}` also clears the
  calculated-channel registry), `app/api/v1/sources.py` (`DELETE
  /sources/{id}` also cascades calculated-channel removal).
- Frontend: `frontend/index.html` only — new main-sidebar nav item + page
  (Signal Builder + Manager), new Workspace Sidebar "Calculated Channels"
  group, `ww.calculatedChannels` metadata mirror, `wwIsCalculatedSourceId()`
  dispatch at the waveform/cursor-values/peak-values/Callout-creation/
  Callout-anchor-move network-call sites, `wwClearWorkspace()`/
  `performRemoveSource()` lifecycle hooks. No changes to
  `ww.displayed`/`ww.channelMeta`/`wwColorForChannel()`/
  `wwAddSelectedChannels()`/`wwRemoveChannelByKey()`/panel/layout code —
  all reused completely unmodified.
- Does not change DEC-019 (full-resolution authority — extended, not
  altered), DEC-038 (default-hidden — reused as-is), DEC-040/044/045/046
  (A/B cursors, annotations, Callout, Peak — their own engineering rules
  are unchanged; calculated channels simply became eligible inputs to
  all of them), or DEC-015/009 (original-file/source immutability —
  verified directly by test that creating a calculated channel never
  mutates a source's own `waveform_data`).
- Explicitly NOT implemented this phase: RMS (any variant), peak-to-peak,
  a free-form formula editor, interpolation/resampling/cross-source
  synchronization, sequence/power/frequency/impedance/differential/
  protection calculations, permanent database/cloud persistence, editing
  a calculated-channel definition after creation, and calculated-channel
  export/import/templates.
- See [MIGRATION_PLAN.md — Phase 5A](MIGRATION_PLAN.md#phase-5a--calculated-channels--basic-signal-builder-2026-08-21).

**Update (2026-08-21, same day, bug fix — no new decision entry)**: owner
UAT found the Recording Events page (and, separately, Waveform) showing
the Calculated Channels page STACKED underneath it at the same time.
Root cause: the SAME CSS-cascade bug class already caught and fixed once
this session for the annotation placement guidance ribbon —
`#pageCalculatedChannels { display: flex; }` (author CSS) beat the UA
stylesheet's own `[hidden] { display: none }` rule by ORIGIN alone.
`shellSetCurrentPage()` — the sole navigation authority, confirmed by
direct trace to correctly toggle `.hidden` on all three page containers
(`workspaceRow`/`pageRecordings`/`pageCalculatedChannels`) and all three
nav buttons' own `aria-current` in one exclusive pass — was never wrong;
`#pageCalculatedChannels.hidden` was already `true` whenever a different
page was selected, but that had zero visible effect. `#pageRecordings`
itself already carried its own `[hidden]` override from when IT was
first added; `#pageCalculatedChannels` simply never received the same
treatment when this session added it. DOM nesting was independently
confirmed correct (`#pageCalculatedChannels` is a genuine sibling
`<section>`, not nested inside `#pageRecordings`) — ruling out a missing/
misplaced closing tag as a contributing cause. Fixed with one line,
`#pageCalculatedChannels[hidden] { display: none; }`, the same
established pattern already used for `#workspaceRow[hidden]`/
`#pageRecordings[hidden]`/`.ww-annotation-guidance[hidden]`. Extended
`phase5a_check.mjs` with 6 new checks: a structural regression guard
confirming the `[hidden]` override rule is present in the shipped
stylesheet (verified directly to fail without the fix and pass with it —
jsdom cannot render CSS cascade, so this is the only check capable of
catching a regression here), an exactly-one-page-visible +
exactly-one-nav-item-active assertion for each of the three real pages,
a rapid-switching sequence across all three, and a hide-don't-destroy
check confirming in-progress builder state (selected operation + partial
input list) survives a round trip through Waveform and back —
**32/32 passing** in the file overall (26 prior unchanged). Full
frontend suite reconfirmed at the true 33-failure baseline; backend
untouched, 519/519 unchanged.

**Update (2026-08-21, same day, straightforward extension — no new
decision entry)**: owner-requested addition of a lightweight **Waveform
Preview** panel to the Calculated Channels page, sitting below the
existing Calculated Channels manager list. Not a new architectural
decision — every authority it depends on is one already established by
this same DEC-047: **visibility** is `wwIsAnalogChannelVisible(sourceId,
channelName)` reading `ww.displayed` — the SAME single authority the
manager list's own eye icon and the Waveform sidebar group already
share (no second, conflicting visibility state introduced); **data** is
the existing `GET .../calculated-channels/{id}/waveform` endpoint (no
new backend work — the full-resolution-or-reduced pipeline this phase
already built was already sufficient); **color** is the existing
`wwColorForChannel()` (visually consistent with the main Waveform
page); **theme** is the existing `wwThemeColors()`. A completely
standalone Plotly instance (`#wwCcPreviewChart`) — never added to
`ww.panels`, never touching `ww.viewport`/layout mode/A-B cursor state/
annotations — with native Plotly modebar/pan/zoom only
(`displayModeBar: true`, explicit rather than a bare omission, the
opposite of the main panels' own `displayModeBar: false` convention,
since Powerwave's own centralized toolbar deliberately does not extend
to this preview). Rendering strategy is a full rebuild on every change
(refetch all currently-visible calculated channels, `Plotly.newPlot()`
on first render / `Plotly.react()` after) rather than incremental trace
diffing — simpler and adequately efficient for a small-channel-count
Phase 1 preview, matching the task's own "do not overengineer caching
unless necessary" instruction — guarded by a monotonic generation
counter (the same stale-response idiom already used by
`wwCursorValuesGeneration`/`wwPeakValuesGeneration`/
`ww.annotationPlacementGeneration`) so a rapid sequence of visibility
toggles can never let an earlier fetch overwrite a later one. Called
from the exact same 3 sites that already refresh the manager list
(`wwRenderCalculatedChannelsPage()` — page-open/post-creation/Start New
Workspace; `wwToggleCalculatedChannelDisplay()`; `wwCcDeleteChannel()`'s
success branch) — so its own lifecycle (create/delete/toggle/Start New
Workspace/Clear Workspace) exactly mirrors the manager list's own
established behavior with no new rule invented. Proactively avoided a
FOURTH occurrence of the `[hidden]`-CSS-cascade bug this session had
already hit three times (guidance ribbon, `#pageCalculatedChannels`
page-stacking): the new `.ww-cc-preview-chart` CSS class deliberately
declares no `display` property at all (matching `.empty-state`/
`.ww-cc-panel`'s own existing safe pattern elsewhere on this same page),
so there is nothing in author CSS to override the UA stylesheet's own
`[hidden] { display: none }` rule. Extended `phase5a_check.mjs` with 14
new checks covering panel placement, default-hidden-on-creation
(reusing DEC-038), visibility toggle both directions, delete, multiple
channels with distinct colors sourced from the real authoritative
calculated-channel arrays (never re-derived from Plotly traces), native
`displayModeBar: true` config, non-interference with the main Waveform
page's own panels/viewport, page-navigation isolation (including a
structural regression guard that `.ww-cc-preview-chart` still carries no
`display` property), and Start New Workspace / plain Clear Workspace
lifecycle behavior — **44/44 passing** in the file overall (32 prior
unchanged). Full frontend suite reconfirmed at the true 33-failure
baseline; backend untouched, 519/519 unchanged. See
[MIGRATION_PLAN.md — Phase 5A-UAT](MIGRATION_PLAN.md#phase-5a-uat--calculated-channel-waveform-preview-2026-08-21).

**Update (2026-08-21, same day, frontend consistency fix — no new decision
entry)**: owner UAT found the main Waveform page's own Calculated
Channels sidebar group showing no Cur A / Cur B measurement columns at
all, unlike real Analog Channel rows. Root cause was purely
presentational, never a backend or data-authority gap: the Phase 5A
`/calculated-channels/cursor-values` endpoint and its frontend dispatch
(`wwFetchCursorValuesForSource()`'s own `isCalculated` branch,
`wwFetchAllCursorValues()`/`wwScheduleCursorValuesRefresh()`'s
source-id-driven fan-out) were already fully wired and already
populating `ww.cursorValues` for calculated channels correctly (proven
directly by the pre-existing A/B cursor test, unchanged) — the gap was
that `wwRenderCalculatedChannelsSidebarSection()` built its own bespoke
`<tr>` markup (a lone name `<td>`, inside an entirely unstyled
`class="channel-table"` — a class with no CSS rule anywhere in the
stylesheet) instead of reusing `renderChannelTable()`, the SAME generic
table builder `renderAnalogGroup()` already uses for the real Channel
Browser's own Channel/Phase/Cur A/Cur B columns. Fixed by switching
`wwRenderCalculatedChannelsSidebarSection()` to call `renderChannelTable()`
with `[Channel, Cur A, Cur B]` columns (no Phase column — calculated
channels carry no phase field), reusing `analogChannelNameCellHtml()`
and `wwCurValueCellHtml()`/`wwCurValueText()` verbatim (both were
already fully generic — keyed by `sourceId`/`channelName` via
`wwChannelKey()`, gated by the SAME `wwIsAnalogChannelVisible()`/
`ww.measurementCursors` authority every analog cell already uses —
calling them with a calculated channel's own id/name was the entire
fix). A new `calculatedChannelRowAttrs(calc)` mirrors
`analogChannelRowAttrs()`'s shape and additionally tags each row with
`data-channel-kind="analog"`/`data-source-id`/`data-channel-name` — the
SAME triad real analog rows already carry — so calculated-channel rows
are picked up, entirely for free, by the EXISTING generic Cur A/Cur B
live-update sweeps (`wwUpdateCursorValueCellsForChannels()`/
`wwUpdateAllCursorValueCells()`, both global DOM queries, not scoped to
the Channel Browser) that already drive cursor-drag/cursor-move/mode-
toggle updates for real channels — no new update plumbing was written.
Confirmed safe: the ONLY other consumer of `data-channel-kind`
(`setupChannelRowToggles()`'s click dispatch) is delegated on
`#channelGroups` specifically, a different DOM subtree from
`#calculatedChannelsSidebarBody`, so it never sees these rows; the
sidebar's own pre-existing dedicated click handler
(`wwCalculatedChannelsSidebarRowClickHandler`, keyed off
`data-calculated-channel-id`, kept unchanged) still owns the toggle
interaction. One small, closely-related pre-existing bug fixed in the
same change, discovered by this task's own "delete → measurement row
disappears cleanly" acceptance check:
`wwRenderCalculatedChannelsSidebarSection()`'s zero-channels early
return used to skip clearing `bodyEl.innerHTML`, leaving the last
channel's stale `<tr>` sitting in the DOM (invisible only because the
ancestor `<section>` itself was hidden) — inconsistent with
`wwRenderCalculatedChannelManagerList()`'s own sibling convention two
functions away, which already replaces its body with the empty-state
paragraph at zero; now matches it. No calculation mathematics, dependency
model, adaptive resolution, Peak, or Callout code touched. Extended
`phase5a_check.mjs` with 10 new checks (A/B-off em dash parity, A/B-on
values matching the authoritative calculated array via the same
nearest-sample rule, moving A/moving B independently, calculated-from-
calculated, out-of-range em dash, delete removing the row entirely,
Grouped/Separate/Custom producing no duplicate/stale rows, and a
structural guard confirming the sidebar reuses `table.channels`, the
real theme-token-driven analog style) — **53/53 passing** in the file
overall (44 prior unchanged). Full frontend suite reconfirmed at the
true 33-failure baseline (zero net new regressions, including
`phase4c1_check.mjs`/`phase4c2_check.mjs`'s own A/B cursor coverage,
`phase4f_check.mjs`'s Callout coverage, and `phase4g_check.mjs`'s Peak
coverage, all unaffected). Backend untouched, 519/519 unchanged (no
backend files touched — the existing `/calculated-channels/cursor-values`
endpoint needed no changes). See
[MIGRATION_PLAN.md — Phase 5A-UAT2](MIGRATION_PLAN.md#phase-5a-uat2--standard-ab-measurements-for-calculated-channels-2026-08-21).

**Update (2026-08-21, same day, owner-approved clarification — no new
decision entry)**: **Calculated-channel input availability is
independent of Waveform visibility.** All valid analog source channels
and calculated analog channels in the active workspace may be used as
calculation inputs even when hidden from the waveform. Visibility is
presentation state only and is never an engineering eligibility
criterion. This clarifies (does not alter) the original DEC-047 text —
nothing about the five operations, the time-alignment guardrail, unit
compatibility, dependency tracking, or full-resolution authority
changed.

Root cause of the pre-clarification gap: `wwCcAvailableCandidates()`
(the Signal Builder's own input-picker candidate list) read from
`ww.channelMeta` — a Map deliberately scoped, per its own original
Phase 5A comment, to "every analog channel the engineer has brought
into this workspace's Waveform **at least once**" (populated solely by
`wwAddSelectedChannels()`, i.e. only on first DISPLAY). A source
channel never individually toggled visible — even though its SOURCE had
been opened and its full channel list was already known to the backend
— was simply absent from the picker, silently coupling calculation
eligibility to display history. Not a backend gap: the backend's own
`ChannelRef` validation already accepts any valid source/calculated
channel id regardless of visibility (visibility is not backend state at
all) — confirmed by investigation before any change was made, per this
clarification's own explicit "only touch backend if an authoritative
inventory API is missing" instruction. No backend files were touched.

Fixed with a new `ww.sourceChannelInventory` (`sourceId -> {sourceId,
sourceName, analogChannels}`), populated directly from the SAME `GET
.../sources/{id}/channels` response `selectSource()` already fetches
for the Channel Browser (zero new network calls in the common case) —
covering EVERY analog channel of a source the engineer has opened this
session, independent of which individual channels were ever toggled
visible. `wwCcAvailableCandidates()` now reads from this inventory
instead of `ww.channelMeta` (which is left completely untouched --
still used, unmodified, by the unrelated Custom Groups chip editor).
Same lifecycle as the existing `ww.sourceBounds`: deleted per-source on
source removal (`performRemoveSource()`), cleared entirely only by
"Start New Workspace" — deliberately NOT cleared by the plain "Clear
workspace" button (unlike `ww.channelMeta`/`ww.channelColors`, which
that button already clears unconditionally): plain Clear is
display-only and keeps the still-selected source fully loaded, so
wiping its known channel list there would have silently reintroduced
the same visibility-coupling bug this fix removes. The client-side
"same-source" candidate-disable heuristic (`wwCcCandidateOptionsHtml()`,
already documented as a UX shortcut only, never the real compatibility
authority) needed no change — it already compares
`referenceSourceId`, unaffected by where the candidate list itself
comes from; the backend remains the sole real unit/time-alignment
authority, exactly as before. The picker's own single flat "Source
Analog Channels" optgroup was split into one optgroup per source
(labelled by that source's own station name) to keep a now-larger,
multi-source candidate list navigable — the smallest change matching
the owner's own preferred "Source 1 / Source 2 / Calculated Channels"
structure without a disproportionate nested-grouping rewrite (a native
`<select>` has no second grouping level to exploit for engineering-type
sub-groups). Extended `phase5a_check.mjs` with 11 new checks: Reverse
Polarity/Absolute Value/Multiply-by-Constant from a never-displayed
channel, N-input Addition/Subtraction with some or all inputs hidden, a
hidden calculated channel remaining available as a further input, an
incompatible hidden cross-source channel still correctly disabled by
the picker (compatibility, not visibility), hiding/re-showing every
analog channel leaving the candidate inventory unchanged, source
removal dropping exactly that source's own candidates, the waveform
preview's own unrelated visibility authority confirmed unaffected, the
A/B sidebar presentation confirmed unaffected, and the per-source
optgroup grouping — **65/65 passing** in the file overall (53 prior
unchanged, zero pre-existing test's behavior changed). Full frontend
suite reconfirmed at the true 33-failure baseline (zero net new
regressions, `phase2cc*`'s own pre-existing failures independently
confirmed unrelated to `ww.channelMeta`/Custom Groups, still failing
for the SAME pre-existing Absolute/Elapsed time-mode reasons as before;
`phase4c1`/`phase4c2`/`phase4f`/`phase4g` individually reconfirmed
passing). Backend untouched, 519/519 passing. See
[MIGRATION_PLAN.md — Phase 5A-UAT3](MIGRATION_PLAN.md#phase-5a-uat3--calculated-channel-input-availability-2026-08-21).

Update note (2026-08-21, Phase 5A UAT — Absolute Time after adding a
calculated channel):

No new decision. This is a correction to DEC-047's own
`reference_source_id` implementation and preserves DEC-042's
presentation-only Absolute/Elapsed model.

Owner UAT found that adding a calculated channel to an Absolute-capable
recording made the Absolute Time toolbar option become unavailable.
Root cause was frontend timing eligibility, not rendering or a backend
calculation problem: `wwCalculatedChannelMeta()` gave calculated
channels `recordingStartTime: null` and `timingReference: null` even
though DEC-047 says their inherited sample-time array is grounded by
`reference_source_id`. `wwAvailableTimeModes()` correctly intersects
capabilities across displayed analog-like channels, so the single
null-timed calculated trace legitimately removed `absolute` from the
available mode set.

Fixed by caching each opened real source's absolute timing metadata in
`ww.sourceTiming`, populated from the same `/sources/{id}/channels`
timebase response that already populates source bounds. Calculated
channels keep their pseudo-source display identity (`calc-*`) for
`wwAddSelectedChannels()`/`ww.displayed`/colors/layout/annotations, but
their `recordingStartTime` and `timingReference` now inherit from
`calc.reference_source_id`. Workspace bounds likewise resolve a
displayed calculated channel through its reference source, so an
only-calculated view remains grounded in the real recording's elapsed
extent. If the reference source's timing is unknown, the fallback stays
conservative: Absolute is not invented.

`wwSetTimeMode()` remains unchanged in principle: it does not fetch
waveform data and does not rewrite trace X/Y arrays; Absolute/Elapsed
still changes labels, hover text, cursor readouts, and axis
presentation only.

See [MIGRATION_PLAN.md — Phase 5A UAT Absolute Time](MIGRATION_PLAN.md#phase-5a-uat--absolute-time-after-adding-a-calculated-channel-2026-08-21).

**Update (2026-08-21, same day, owner-approved clarification — no new
decision entry)**: **Calculated channels remain under a dedicated
Calculated Channels group in the Waveform sidebar. Within that group,
channels are subdivided by their inherited engineering classification
using the same classification vocabulary as source analog channels (for
example Voltage, Current, Power, Frequency, ROCOF, Undefined).
Classification is derived from authoritative input metadata and
operation semantics, never from the user-editable calculated-channel
name. Unknown classification falls back to Undefined.**

Investigation, per this clarification's own explicit instruction:
`CalculatedChannel` had NO classification field of any kind before this
change (confirmed by direct inspection of `app.domain.calculated_channel`).
Source analog channels are classified by the existing, unrelated
`app.domain.channel_classification.classify_analog_channel()` (three
tiers: explicit `parameter_type` metadata, recognized unit, else
`Undefined` — never a naming-pattern guess), computed once at import
time and stored on `AnalogChannelSummary.engineering_type`. This
clarification adds a NEW, distinct backend field/function
(`CalculatedChannel.engineering_type`,
`app.domain.calculated_channel.derive_engineering_type()`) that
INHERITS from that existing classification rather than re-classifying
anything — the canonical classification authority is reused, never
duplicated.

`derive_engineering_type(input_types)` is deliberately ONE rule, not
five: every input must share the exact same KNOWN (non-`Undefined`)
type for that type to be inherited; an empty list, any `Undefined`
input, or a genuine mismatch all conservatively yield `Undefined`. This
single rule correctly covers every current Phase 5A operation without
per-operation branching — unary (Reverse Polarity/Absolute Value/
Multiply by Constant) trivially has exactly one input, so "the common
type" IS that input's own type; multi-input (Addition/Subtraction)
requires genuine agreement across 2+ inputs. Calculated-from-calculated
composes correctly through arbitrarily deep chains for free: a
calculated channel used as an input passes its OWN already-derived
`engineering_type` back into the same function, verified transitively
(`Sum = VA+VB` → Voltage → `Scaled = Sum×0.5` → Voltage → `AbsScaled =
abs(Scaled)` → Voltage). Classification is metadata/grouping only and
never a second eligibility gate — the existing unit-compatibility and
time-alignment guardrails (unchanged) remain the sole authority over
whether a calculation is even allowed; a unit-valid combination with an
unknown/mismatched type still succeeds, just classified `Undefined`
rather than rejected, per this clarification's own explicit "do not
invent a stronger rejection rule" instruction. A calculated channel
created before this field existed (or any other missing/unrecognized
value) safely renders as `Undefined`, never crashes.

Frontend: the Waveform sidebar's existing `#calculatedChannelsSidebarSection`
is now itself a collapsible `<details class="channel-group" data-group=
"calculated">` (the SAME nested-group visual language Analog/Digital
Channels already use — no new sidebar pattern), containing nested
per-type `<details class="channel-subgroup">` blocks ordered by the
EXACT SAME `ANALOG_GROUP_ORDER` Analog Channels already uses — never a
second, invented category list. A type with zero current calculated
channels renders no subgroup at all, matching `renderAnalogGroup()`'s
own "only present types" convention. Each subgroup's own table is still
built via the SAME `renderChannelTable()`/`analogChannelNameCellHtml()`/
`wwCurValueCellHtml()` Phase 5A-UAT2 already established — the Cur A/Cur
B presentation fix is completely preserved, just rendered once per
subgroup. New parent ("Calculated Channels") and per-subgroup Show
all/Hide all buttons reuse the same `.group-toggle-btn` visual language
as Analog/Digital's own subgroup buttons, dispatched by a new
`wwToggleCalculatedChannelGroupDisplay()` that reads scope directly from
`ww.calculatedChannels` (never a DOM row scan) and builds metas via the
SAME `wwCalculatedChannelMeta()` a single-channel toggle already uses —
`ww.displayed` remains the sole visibility authority throughout, no
second visibility state introduced.

**Deliberately, explicitly separate from Grouped-mode PANEL placement**:
`wwPanelGroupKeyFor()`'s own Grouped-mode grouping key
(`wwCalculatedChannelMeta().engineeringType`, hardcoded `"Calculated"`)
is UNTOUCHED — calculated channels continue to land in their own
dedicated "Calculated" panel in Grouped mode, exactly as before this
clarification. Only the SIDEBAR's own presentational tree structure
changed; no separate rendering pipeline by engineering type was created,
and Grouped/Separate/Custom/A-B/Peak/Callout are all unaffected (verified
directly — the full existing calculated-channel regression suite passes
unchanged). Manager-page rows (optional, per this clarification's own
"if trivial" allowance) now append the inherited type to their existing
operation-summary line (e.g. "Addition (VA + VB) · Voltage") — no new
row, no new CSS class.

Extended `phase5a_check.mjs` with 8 new checks (top-level group stays
distinct from Analog Channels, Voltage/Current/Power/Undefined
calculated channels each land in the correct subgroup, no empty
subgroups for absent types, A/B measurements work inside a subgroup,
parent vs. per-subgroup Show all/Hide all scope correctly, new channels
appear under the correct subgroup immediately with no reload, deleting
the last channel of a type removes that subgroup cleanly with no stale
row, and subgroup placement has zero dependency on source-channel
visibility) — **73/73 passing** in the file overall (65 prior
unchanged). New backend tests: `TestDeriveEngineeringType` (pure
function, `test_calculated_channel_domain.py`) and
`TestEngineeringTypeInheritance` (full create-flow including transitive
calculated-from-calculated propagation, `test_calculated_channel_service.py`),
plus one additive API-response assertion
(`test_calculated_channel_api.py`) — full backend suite green. Full
frontend suite reconfirmed at the true 33-failure baseline (zero net new
regressions, `phase4c1`/`phase4c2`/`phase4f`/`phase4g` individually
reconfirmed passing).

See [MIGRATION_PLAN.md — Phase 5A-UAT4](MIGRATION_PLAN.md#phase-5a-uat4--calculated-channel-type-subgroups-2026-08-21).

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
