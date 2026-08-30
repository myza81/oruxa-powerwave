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

**Update (2026-08-21, same day, owner-approved clarification — no new
decision entry)**: **In Grouped waveform mode, calculated channels
remain distinct from recorded analog channels and are grouped into
separate waveform panels by inherited engineering type, e.g. Calculated
- Voltage, Calculated - Current, Calculated - Power. Separate and
Custom layout semantics remain unchanged.**

Root cause, confirmed by direct trace before any change was made:
`wwPanelGroupKeyFor(channel)` — the ONE function every panel creation/
reconciliation path (`wwAddSelectedChannels()`'s initial-add path AND
`wwRebuildLayout()`'s own mode-switch regroup path) already funnels
through — returned `channel.engineeringType || "Undefined"` for Grouped
mode, and `channel.engineeringType` for EVERY calculated channel was
(and, deliberately, still is) the hardcoded string `"Calculated"` set
by `wwCalculatedChannelMeta()` (Phase 5A-UAT4's own deliberate choice
to keep sidebar grouping from leaking into panel placement). The result
observed by the owner: every calculated channel, regardless of its own
real inherited type, collapsed into one shared "Calculated" panel.

Fixed by adding a calculated-specific branch to `wwPanelGroupKeyFor()`
and its sibling `wwPanelLabelFor()`, checked ONLY inside the Grouped-
mode fallthrough (after the existing Separate/Custom branches, which
are completely untouched) — `wwIsCalculatedSourceId(channel.sourceId)`
routes to a new `wwCalculatedEngineeringTypeFor(calculatedChannelId)`,
which reads `ww.calculatedChannels.get(id).engineering_type` directly
(the SAME backend-authoritative field Phase 5A-UAT4 introduced) —
never inferred from the calculated channel's own user-editable name,
never re-derived from unit, never read from the sidebar DOM. Group key
is `"calc:" + type` (e.g. `"calc:Voltage"`) — stable and structurally
distinct from a real analog channel's own plain `"Voltage"` key, so the
two origins can never collide into one panel even when they share the
same type name; display title is `"Calculated - " + type`. This was a
small, surgical change to the ONE generic resolver, per the task's own
explicit preference — no scattered special cases were added to any
rendering/reconciliation code, since every panel-forming path already
goes through these two functions.

`ww.displayed` remains the sole visibility authority throughout — a
calculated-type panel is created the moment its first member becomes
visible and removed the moment its last member is hidden/deleted,
exactly like every other panel already behaves; no new lifecycle rule
was introduced. All existing engineering guardrails, calculation
mathematics, input-availability, and dependency logic are completely
unchanged — this is waveform-panel grouping only. A/B, Peak, Callout,
and Absolute/Elapsed time-mode support are all unaffected: channel
identity (`sourceId`/`channelName`) never changes when a channel moves
between panels, so cursor values, annotation anchors, and timing
inheritance (`ww.sourceTiming` via `reference_source_id`) all continue
to resolve correctly regardless of which panel currently holds the
trace — verified directly across a full Grouped → Separate → Grouped →
Custom → Grouped round trip.

Extended `phase5a_check.mjs` with 11 new checks: two same-type
calculated channels sharing exactly one panel, three different types
landing in three separate panels, a recorded and a calculated channel
of the same type confirmed as two genuinely distinct panels (never
merged), hiding the last trace in a type panel removing it cleanly,
`Undefined` classification landing in its own `Calculated - Undefined`
panel (never a generic `Calculated` one), Separate-mode regression (type
grouping does not leak in), Custom-mode regression (existing solo-panel
key convention untouched), a full 5-step mode-switching sequence with
zero duplicate/stale panels or lost traces/visibility, Absolute/Elapsed
switching with two calculated-type panels visible and zero extra
network fetch, A/B cursor values remaining correct after regrouping,
and a Callout surviving a Grouped→Separate→Grouped round trip still
attached to the correct calculated channel — **84/84 passing** in the
file overall (73 prior unchanged). Full frontend suite reconfirmed at
the true 33-failure baseline (zero net new regressions,
`phase4c1`/`phase4c2`/`phase4f`/`phase4g` individually reconfirmed
passing). Backend untouched, full suite green (no backend files
changed — this is a frontend-only panel-grouping fix). See
[MIGRATION_PLAN.md — Phase 5A-UAT5](MIGRATION_PLAN.md#phase-5a-uat5--calculated-waveform-panels-grouped-by-engineering-type-2026-08-21).

**Update (2026-08-21, same day, owner-approved clarification -- no new
decision entry)**: **The Calculated Channels page's lightweight
Waveform Preview follows the same engineering-type separation as
Grouped mode on the main Waveform page. Visible calculated channels are
rendered in separate lightweight Plotly preview panels such as
Calculated - Voltage, Calculated - Current, and Calculated - Power.
Preview rendering remains independent from the main Waveform state and
uses only native Plotly controls.**

The prior single `#wwCcPreviewChart` element (Phase 5A-UAT, extended
Phase 5A-UAT2) overlaid every visible calculated channel into one
Plotly chart regardless of engineering type. Replaced with
`#wwCcPreviewPanels`, populated at render time by
`wwCcRenderWaveformPreview()` with ONE lightweight Plotly panel per
engineering type currently represented among visible calculated
channels -- using the exact SAME `calc.engineering_type` authority,
`ANALOG_GROUP_ORDER` ordering, and `"Calculated - <Type>"` naming
already established for the main Waveform page's own Grouped-mode
panels (the Update immediately above) -- never re-inferred from name/
unit/DOM, and never sharing an actual Plotly instance or state with the
main Waveform page (deliberately independent rendering, per the task's
own explicit "keep rendering state independent" instruction; only the
classification metadata/ordering/naming conventions are shared).

Visibility authority is completely unchanged: `wwCcPreviewVisibleChannels()`
(`wwIsAnalogChannelVisible()` over `ww.calculatedChannels`) still governs
which channels participate -- no new preview-specific visibility state.
The preview contains ONLY calculated channels, never recorded analog
channels, even when a recorded channel of the same type is also
displayed on the main Waveform page (verified directly). Data authority
is unchanged: the existing `GET .../calculated-channels/{id}/waveform`
endpoint, fetched exactly once per visible channel regardless of how
many type panels exist (section 12's own explicit "aim for: visible
channels -> fetch each once -> group by type -> render panels" -- never
a duplicate fetch per panel) -- results are grouped by type client-side
AFTER fetching, never recomputed or re-fetched per panel.

Panel lifecycle is now per-type rather than global: a new
`panelsByType` map (`type -> {containerEl, chartEl, ready}`) tracks each
type's own DOM/Plotly instance across renders -- a type panel already
present on the page is REUSED (`Plotly.react()` updates its data in
place; `appendChild()` on the already-attached container cheaply
re-parents it into the correct `ANALOG_GROUP_ORDER` position without
destroying it) rather than torn down and rebuilt on every render; a
type panel is only ever actually purged (`Plotly.purge()` + DOM
removal) when its last member becomes hidden/deleted, matching the
task's own explicit "no stale canvas/duplicate charts/stale legends"
requirement and avoiding any listener-leak risk from repeatedly
recreating the same still-present chart. The X-axis/timing convention,
theme handling (`wwThemeColors()`), and native-Plotly-only interaction
(`displayModeBar: true`, no custom toolbar) are all completely
unchanged from the original single-chart preview -- this task is panel
separation only, deliberately not coupled to DEC-042's Absolute/Elapsed
main-waveform controls.

Extended `phase5a_check.mjs` with 8 new checks (two same-type channels
sharing one panel, three different types in three separate panels with
`ANALOG_GROUP_ORDER` ordering verified independent of toggle order,
hiding the last member of one type removing only that panel while a
still-present type's own chart instance is proven never torn down/
recreated, `Undefined` classification's own dedicated panel, calculated-
from-calculated landing in the same panel, a single-visible-type
regression, confirmation that preview rendering never touches
`ww.panels`/the main Waveform page's own Grouped-mode state, and
confirmation that a recorded analog channel of the same type never
appears in a calculated-only preview panel) plus rewrote 9 pre-existing
preview tests to the new multi-panel DOM structure (same assertions,
new selectors) -- **92/92 passing** in the file overall (84 prior,
9 rewritten + 8 new). Full frontend suite reconfirmed at the true
33-failure baseline (zero net new regressions). Backend untouched
(no backend files changed -- this is a frontend-only preview-rendering
change). See
[MIGRATION_PLAN.md — Phase 5A-UAT6](MIGRATION_PLAN.md#phase-5a-uat6--calculated-channels-preview-panels-by-engineering-type-2026-08-21).

**Update (2026-08-21, same day, UAT bug fix -- no new decision entry)**:
owner UAT found the Calculated Channels page's new type-separated
Waveform Preview panels (Phase 5A-UAT6) rendering with a white/light
Plotly paper and plot area even while the surrounding Oruxa page was in
Dark mode. Root cause, confirmed by direct trace: two related gaps.
First, `wwCcRenderWaveformPreview()`'s own layout object set
`paper_bgcolor`/`plot_bgcolor`/`font.color` from `wwThemeColors()` but
never set `xaxis.gridcolor`/`yaxis.gridcolor`/`zerolinecolor` at all --
Plotly does not auto-derive axis/grid chrome from the background color,
so those elements silently used Plotly's own light-mode default
regardless of theme. Second, and the primary cause of the reported
symptom: `wwApplyTheme()` -- the ONE existing `powerwave:theme-change`
handler, which already re-themes the main Waveform panels/sticky ruler/
digital chart via `Plotly.relayout()` -- never touched the Calculated
Channels preview's own Plotly instances at all, so a panel created
before a Light->Dark switch (or already open when the user toggles
theme) simply never got re-colored; only a channel add/remove/delete
happened to trigger a fresh `wwCcRenderWaveformPreview()` call, and even
that only mattered if the theme happened to be correct AT THAT MOMENT.
A further, easily-missed detail: `wwApplyTheme()`'s own
`if (ww.panels.length === 0) return;` guard used to exit the WHOLE
function (skipping even the ruler) whenever the main Waveform page had
zero panels -- exactly the state the owner's own repro steps produce
(Calculated Channels page open, nothing shown on the main Waveform).

Fixed with two small, targeted changes, reusing the SAME theme
authority throughout (no second, invented dark-mode palette): (1) the
preview's own initial layout now also sets
`xaxis.gridcolor`/`yaxis.gridcolor`/`zerolinecolor` from
`wwThemeColors().grid` -- the EXACT SAME token the main panel's own
`wwBuildLayout()` already uses for its own `xaxis.gridcolor`/
`yaxis.gridcolor`; axis tick-label/title/legend text color needed no
separate override -- Plotly's own standard inheritance already cascades
the top-level `layout.font.color` to axis and legend text, confirmed
directly (light mode already rendered those correctly even before this
fix). (2) `wwApplyTheme()`'s own early-return now guards only the
main-panel relayout loop (never the whole function), and a new block
iterates `wwCcPreview.panelsByType.values()` applying the exact same
`Plotly.relayout()`-only re-theme (`paper_bgcolor`/`plot_bgcolor`/
`font.color`/`xaxis.gridcolor`/`yaxis.gridcolor`/`xaxis.zerolinecolor`/
`yaxis.zerolinecolor`) the main panels already receive -- never
`Plotly.newPlot`/`Plotly.react`, so no trace data is touched and no
waveform re-fetch is ever triggered by a theme switch, verified
directly. This keeps ONE shared theme-application entry point for the
whole app (already also covering the digital chart and sticky ruler)
rather than a second, competing "theme changed" handler -- the preview
and main Waveform page's own rendering STATE remain completely
independent (verified directly: no `Calculated - <Type>` string ever
appears as a `ww.panels` groupKey); only the theme-token values and the
relayout mechanism are shared.

Extended `phase5a_check.mjs` with 10 new checks, using
`window.PowerwaveTheme.setTheme()` (the real theme-toggle API, not a
source-text pattern match) against jsdom's own `getComputedStyle`
resolution of the actual shipped `theme.css` -- genuine computed-value
verification, not merely a string check: Light mode resolves the exact
light hex tokens, Dark mode (panel created while already dark) resolves
the exact dark hex tokens and is proven genuinely distinct from light,
multiple simultaneous type panels all resolve from the same helper, an
EXISTING panel (created while light) is re-themed immediately on a live
Light->Dark switch via `Plotly.relayout` with no reload/re-toggle/
navigation, the reverse Dark->Light direction, zero network fetches
caused solely by a theme switch, all three type panels updating on one
switch (not only the first), the modebar config surviving a theme
switch (relayout never recreates the chart), and the main Waveform
page's own theme behavior confirmed completely unchanged even while a
calculated preview panel coexists -- **101/101 passing** in the file
overall (92 prior unchanged). Full frontend suite reconfirmed at the
true 33-failure baseline (zero net new regressions). Backend untouched
(no backend files changed -- this is a frontend-only theme-integration
fix). See
[MIGRATION_PLAN.md — Phase 5A-UAT7](MIGRATION_PLAN.md#phase-5a-uat7--calculated-preview-dark-mode-fix-2026-08-21).

## DEC-048 — RMS calculated channels use a trailing one-cycle true-RMS calculation on authoritative full-resolution samples, with metadata-first eligibility and backend-enforced override

Date: 2026-08-22
Status: Approved
Source: explicit owner-approved direction for Phase 5B ("RMS Calculated
Channel"), extending DEC-047's Calculated Channels architecture with
exactly the one operation DEC-047 itself deferred.

Decision:

Oruxa Powerwave's sixth calculated-channel operation, RMS — a guarded,
engineering-correct power-system waveform RMS derivation, never a
generic "RMS of any series" operator:

> RMS calculated channels use a trailing one-cycle true-RMS calculation
> on authoritative full-resolution samples. Nominal frequency is
> explicit (50 Hz default). RMS eligibility is metadata-first:
> trustworthy waveform-form metadata is used when available; otherwise
> Oruxa performs a lightweight waveform-form eligibility analysis and
> returns categorical suitable / likely magnitude-or-RMS / uncertain
> results. COMTRADE is not assumed to contain only instantaneous data.
> The RMS input picker is not hard-filtered solely by engineering type,
> preserving future CSV/Excel compatibility. Explicit RMS metadata
> prevents silent RMS-of-RMS; uncertain algorithmic cases require user
> acknowledgement/override.

- **Mathematical definition**: `RMS(t) = sqrt(mean(x^2))` over a
  trailing window `[t - window, t]`, `window = 1 / nominal_frequency_hz`
  (default 50 Hz; any value in `[1, 1000]` Hz accepted, not a 50/60
  whitelist). TRUE RMS — DC and harmonics are included naturally; no
  fundamental extraction, no bandpass, no phasor estimation. Stored
  explicitly on the channel's `parameters`, never an invisibly
  hard-coded semantic: `nominal_frequency_hz`, `window_mode="trailing"`,
  `rms_kind="true_rms"`.
- **Full-resolution authority preserved, `time` inheritance kept
  verbatim**: `evaluate_rms(time, values, nominal_frequency_hz)` is the
  ONLY evaluator in `app.domain.calculated_channel` that reads `time` as
  well as `values` — a deliberate, narrow exception to every other
  operation's pure `values -> values` contract, because RMS is
  inherently a function of elapsed-time window membership, not a
  per-sample transform. Output has the SAME length as the input, never
  cycle-boundary downsampled — this is what keeps
  `reference_source_id`/`time` inheritance, `timebases_aligned()`'s
  same-reference fast path, `_nearest_sample_index()`, `_peak_in_range()`,
  and `_clip_and_reduce()` all working unmodified, and is what makes
  "calculated-from-calculated RMS is allowed" require no second timebase
  regime.
- **Time-based window, not fixed-N, with a verified-correct half-open
  boundary**: the window is `(t[i] - window, t[i]]` — half-open,
  excluding the exact left boundary sample. A closed interval was tried
  first and rejected: for a source whose window happens to be an exact
  multiple of the sample interval (e.g. 5 kHz sampling, 50 Hz nominal —
  exactly 100 samples/cycle), a closed interval double-counts one sample
  (the boundary and the current sample share the same sinusoidal phase,
  exactly one period apart), producing a spurious ripple in an otherwise
  steady sinusoid's RMS that shrinks linearly as sample rate increases —
  confirmed numerically as a discretization artifact, not signal noise.
  The half-open definition is bit-for-bit flat for a steady nominal-
  frequency sinusoid regardless of sample rate, and matches the task's
  own worked example ("~100 samples per 20 ms" for 5 kHz, not ~101).
  Implementation is a hybrid: a fully vectorized `cumsum`-based rolling
  window (O(N), no Python loop) when sample spacing is near-uniform (the
  common case for one COMTRADE rate section), falling back to an O(N)
  two-pointer sliding accumulator for genuinely irregular/multi-rate
  spacing — correct because `time` is always monotonic non-decreasing,
  so the window's own lower bound is itself monotonic as the trailing
  edge advances. A small floating-point epsilon guards the boundary
  comparison in both paths (subtraction-based threshold vs. the time
  array's own independently-constructed values can differ by a ULP at an
  exact boundary, which would otherwise reintroduce the same ripple by a
  different route).
- **Non-finite handling, exact**: a window containing ANY non-finite
  input sample outputs NaN for that window — never silently dropped and
  renormalized over fewer samples. Implemented by tracking a SEPARATE
  running non-finite count alongside the running sum-of-squares (which
  itself only ever accumulates `0.0` in place of a non-finite sample's
  square) — a naive rolling sum that adds a raw NaN and later "subtracts
  it back out" is broken (`NaN - NaN = NaN` in IEEE754), which would
  poison every subsequent window forever, not just the ones that
  actually contain the bad sample.
- **Beginning-of-record NaN, never a partial window**: before
  `time[i] - time[0] >= window`, output is NaN. Existing display/
  measurement code needed one narrow, deliberate fix to handle this
  safely — see the NaN-serialization bullet below.
- **`waveform_form` metadata — a new, separate taxonomy from
  `engineering_type`**: `unknown` / `instantaneous` / `rms` / `magnitude`,
  added in `app.domain.channel_classification` (sibling to the existing
  `engineering_type` taxonomy, same module). Added as a trailing,
  additive, default-`unknown` field on both `AnalogChannelSummary`
  (source channels — no current provider, i.e. COMTRADE, ever sets it
  away from `unknown`; exists now so a future CSV/Excel importer has
  somewhere trustworthy to write to) and `CalculatedChannel`. A NEW
  operation-aware function, `derive_waveform_form(operation,
  input_forms)`, propagates it — deliberately NOT a reuse of
  `derive_engineering_type()`, since unlike engineering type, waveform
  form propagation genuinely differs per operation: Reverse
  Polarity/Multiply by Constant pass the input's form through unchanged;
  Addition/Subtraction inherit only if every input shares the same known
  form, else unknown (same shape as `derive_engineering_type`'s own
  rule); Absolute Value always resets to unknown (taking an absolute
  value discards bipolarity, one of the detector's own indicators);
  RMS's own output is unconditionally `rms`, defined by the operation
  itself, never inherited.
- **Eligibility hierarchy — metadata first, detector fallback, user
  override last resort**, implemented as ONE shared function,
  `check_rms_eligibility()`, called identically by a new dedicated
  `POST .../calculated-channels/rms-eligibility` endpoint AND internally
  by `create_calculated_channel()`'s own RMS branch — this is what
  structurally prevents the frontend from bypassing eligibility by
  crafting a local result: the backend never trusts a client-supplied
  status, it re-derives eligibility itself at creation time from the
  same code path.
  - Trusted `waveform_form = instantaneous` -> `suitable`, no detector
    run.
  - Trusted `waveform_form` in `{rms, magnitude}` -> blocked by default
    (`likely_already_rms_or_magnitude`), no detector run — explicit
    metadata needs no algorithmic second-guessing.
  - `waveform_form = unknown` -> the algorithmic detector
    (`app.domain.rms_detector.classify_waveform_form`) runs on the
    input's own authoritative data, over a capped representative slice
    (up to 1 second). Five cheap, numpy-only indicators (bipolarity;
    zero-crossing regularity; a targeted two-term correlation against
    `sin(2*pi*f0*t)`/`cos(2*pi*f0*t)`, never a full FFT; one-cycle-vs-
    half-cycle lag periodicity; raw-vs-trial-RMS smoothness, reusing
    `evaluate_rms()` itself rather than a second implementation) combine
    into a transparent VOTE COUNT (never a fabricated precision score —
    no "87.42% instantaneous" anywhere) yielding one of three categories:
    `likely_instantaneous` -> `suitable`; `likely_magnitude_or_rms` ->
    blocked by default; `uncertain` -> blocked by default, override
    allowed, never a hard block (real disturbance data — heavy DC
    offset, clipping, a short-but-usable window — must remain usable via
    deliberate engineer acknowledgement).
  - A separate `override: bool` field on the create request (top-level,
    not inside the operation-specific `parameters` dict — a
    cross-cutting safety flag, independently validated) is REQUIRED
    (not merely accepted) whenever eligibility is non-`suitable`;
    creation is rejected with `rms_override_required` otherwise.
  - Two HARD, NEVER-overridable data-quality gates run independently of
    eligibility: the recording must span more than one full RMS window
    (`rms_recording_too_short` otherwise — never silently produce an
    all-NaN channel), and the median sample spacing must imply at least
    4 samples per cycle (`rms_sampling_too_sparse` otherwise — never a
    misleading RMS from 2-3 points/cycle). These are data-quality floors,
    not judgment calls, so `override=True` does not bypass them.
- **RMS-of-RMS prevention**: an existing RMS output's own
  `waveform_form = rms` is exactly the trusted metadata the hierarchy
  above already handles — selecting it as a new RMS input is
  immediately blocked from metadata alone, with no detector re-run,
  matching "no silent RMS-of-RMS."
- **No engineering-type hard filter, ever** (a permanent regression,
  proven by dedicated tests both directions): an `Undefined`-
  engineering-type channel with explicit `instantaneous` waveform-form
  metadata is fully RMS-eligible; a `Voltage`-engineering-type channel
  with explicit `rms` waveform-form metadata is NOT silently eligible.
  `engineering_type` and `waveform_form` are answering two independent
  questions (what physical quantity vs. how each sample is recorded) and
  neither implies the other — this is what keeps the design compatible
  with a future CSV/Excel importer that may know one without the other.
- **NaN-serialization fix (a genuine, previously-latent correctness
  bug this phase makes necessary to fix, not a redesign)**: FastAPI's
  default `JSONResponse` calls `json.dumps(..., allow_nan=False)` —
  confirmed directly against the installed `starlette` version — so a
  raw NaN reaching a response body 500s the request. Every Phase 5A
  operation happened to never produce NaN from finite input, so this
  was never observed; RMS's leading warm-up region is *routine,
  guaranteed* NaN, the first operation to make this a normal case.
  Fixed at the calculated-channels-only serialization boundary:
  `CalculatedWaveformRangeOut.time`/`.values` are now `list[float |
  None]` (NaN sanitized to `null`), `extract_calculated_cursor_values()`
  and `resolve_calculated_annotation_anchor()` now emit `None` instead
  of a raw NaN float for a non-finite sample. The shared primitives
  reused by real source channels (`_clip_and_reduce`/`_peak_in_range`/
  `_nearest_sample_index` in `waveform_service.py`) are untouched — the
  fix is scoped exactly to the calculated-channels boundary, since
  source channels have never produced NaN and must not be touched
  speculatively. On the frontend, Plotly.js natively renders a `null` in
  a y-array as a gap — this is what makes "no special RMS rendering
  pipeline" actually achievable, confirmed directly in a real browser
  (Playwright/Chromium): the warm-up region shows as a genuine gap, not
  a crash or a spike to zero.
- **No special RMS rendering pipeline, confirmed by direct browser
  verification, not just tests**: an RMS channel is exactly a
  `CalculatedChannel` with an inherited `engineering_type` and a new
  `waveform_form`. It participates in the Waveform sidebar's Calculated
  Channels type-subgroup, Grouped-mode panels ("Calculated - Voltage"),
  the Calculated Channels page's own type-separated preview, A/B cursor
  values, +Peak/-Peak, Callout, and Absolute/Elapsed with ZERO code
  changes to any of those systems — verified end-to-end in a real
  headless-Chromium session (upload a synthetic COMTRADE recording,
  create RMS(VA), confirm sidebar subgroup + panel + A/B values +
  RMS-of-RMS block/override flow + Light/Dark theme switch, zero
  console errors throughout).
- **UI**: an `rms` operation card ("RMS" / "1-cycle true RMS") in the
  existing Signal Builder, a Nominal Frequency numeric field (default
  `50`, any sensible value accepted), read-only Window/Method display
  fields, a categorical eligibility status line (never a numeric
  confidence value) that updates on an async, debounced (~400 ms),
  stale-response-guarded eligibility check (same generation-counter
  idiom already established for `wwCursorValuesGeneration`/
  `wwPeakValuesGeneration`), and a "Calculate anyway" checkbox shown
  only when eligibility is non-`suitable`. Create is enabled only when
  local validation passes AND the eligibility result is current for the
  exact input+frequency the builder now holds AND (suitable OR
  override checked). One new CSS `[hidden]`-cascade bug was found and
  fixed during direct browser verification (same bug class this project
  has hit repeatedly): `.ww-cc-rms-override-row { display: flex }`
  needed an explicit `.ww-cc-rms-override-row[hidden] { display: none }`
  override to actually hide.

Alternatives considered:

- A length-changing, cycle-boundary-output RMS (shorter than its input,
  its own new time axis) — rejected: would require a second timebase-
  compatibility regime alongside `timebases_aligned()`'s existing
  same-`reference_source_id` fast path, and would break
  `_nearest_sample_index()`/`_peak_in_range()`/`_clip_and_reduce()`'s
  shared assumption that `time.shape == values.shape` is a channel's
  whole world — all for no requirement the owner actually asked for.
- Folding an eligibility dry-run into `create_calculated_channel()`
  itself via a preview flag — rejected in favor of a dedicated
  `POST .../rms-eligibility` endpoint, matching the existing
  `/cursor-values`/`/peak-values` literal-segment-POST precedent
  exactly: a dry-run flag would add a second exit path through
  `create_calculated_channel()`'s own documented atomic
  all-checks-then-write guarantee for a purely cosmetic reuse win.
- Reusing `derive_engineering_type()` for `waveform_form` propagation by
  giving it an operation parameter — rejected: forcing already-shipped,
  tested code to accept a parameter it doesn't need, just to share one
  multi-input branch's logic, was judged worse than one small new
  function with its own clear per-operation table.
- A closed-interval `[t - window, t]` RMS window (the initial
  implementation) — rejected after direct numerical verification showed
  a spurious ripple for steady-state sinusoids at exact sample-rate/
  cycle ratios; replaced with the half-open definition described above.

Impact:

New: `app.domain.rms_detector` (the eligibility detector, numpy-only, no
scipy dependency added). Extended: `app.domain.calculated_channel`
(`OP_RMS`, `evaluate_rms`, `nominal_frequency_valid`,
`rms_recording_long_enough`, `rms_sampling_dense_enough`, new
constants), `app.domain.channel_classification` (`waveform_form`
taxonomy, `derive_waveform_form`), `app.domain.source`
(`AnalogChannelSummary.waveform_form`), `app.services.
calculated_channel_service` (`check_rms_eligibility`, `RmsEligibility`,
the OP_RMS branch in `create_calculated_channel`, NaN-safe cursor/
annotation-anchor sanitization via a new `_finite_or_none` helper),
`app.services.errors` (4 new error classes), `app.schemas.
calculated_channel` (`RmsEligibilityRequest`/`Response`, `override` on
the create request, `waveform_form` on `CalculatedChannelOut`, NaN-safe
`list[float | None]` typing), `app.api.v1.calculated_channels` (new
`POST .../rms-eligibility` route, 4 new error-code mappings). Frontend:
`frontend/index.html` only, entirely inside the existing `wwCc*` Signal
Builder block plus one CSS fix — no changes to
`wwIsCalculatedSourceId`/`wwPanelGroupKeyFor`/`wwPanelLabelFor`/
`wwCalculatedEngineeringTypeFor`/`ANALOG_GROUP_ORDER`/preview
panels/the sidebar section. New backend tests:
`test_calculated_channel_domain.py` (`TestEvaluateRms`,
`TestRmsValidators`, `TestDeriveWaveformForm`), new
`test_rms_detector.py`, `test_calculated_channel_service.py`
(`TestRmsOperation`, `TestRmsEligibility`,
`TestNoEngineeringTypeHardFilter`), `test_calculated_channel_api.py`
(`TestRmsOperation`, including an explicit NaN-serialization regression
test), new `test_frontend_rms_calculated_channel.py`. Explicitly out of
scope, same as DEC-047's own boundary: fundamental RMS, phasor RMS,
frequency-tracking/frequency-adaptive RMS, sequence RMS, multi-channel
RMS, CSV/Excel import changes, a broader metadata redesign, a free
formula parser, RMS statistics/reporting. All pre-existing Phase 1-5A
backend tests and frontend static-text regression tests pass unmodified
except one, which was updated (not deleted) to reflect that `rms` is no
longer a rejected operation — it now asserts a genuinely unsupported
operation name is still rejected the same way. See
[MIGRATION_PLAN.md — Phase 5B](MIGRATION_PLAN.md#phase-5b--rms-calculated-channel-2026-08-22).

**Update (2026-08-22, same day, owner UAT refinement — no new decision
entry)**: owner UAT found the RMS parameter form's Nominal Frequency/
Window/Method fields visually indistinguishable — all three rendered as
similar-looking text boxes, giving the engineer no way to tell which
value was user-supplied, metadata-derived, automatically calculated, or
a fixed operation definition. **RMS parameter controls now distinguish
authority explicitly: automatically derived or metadata-backed values
are read-only; user-supplied controlled engineering parameters use
constrained selectors rather than free text. The RMS window is always
derived from nominal frequency, and True RMS remains the fixed Phase 5B
method.** Concretely:

- **Investigation finding, reported before any UI change (owner's own
  explicit requirement)**: `SourceMetadata.nominal_frequency` already
  exists and is already populated for every COMTRADE source, parsed
  directly from the CFG's own mandatory "lf" (line frequency) field —
  already shown as an unhedged fact ("Nominal frequency: 50 Hz") in the
  Recordings page's own detail card. This contradicted the spec's own
  apparent assumption that no such metadata existed yet. Confirmed with
  the owner directly: treat it as trustworthy, exactly like every other
  place in the app already does.
- **Nominal Frequency** is now Category A (user-selectable) or Category B
  (metadata-derived), never both rendered identically: when the selected
  input's own grounding source (resolved through a calculated input's
  `reference_source_id` when needed, never guessed from
  `engineering_type`) has a usable `nominal_frequency`, the field renders
  as a locked, readonly value captioned "From recording metadata"; when
  it does not (no current COMTRADE source realistically hits this today,
  but a future provider might), it renders as a constrained `<select>`
  with exactly two options (50 Hz / 60 Hz, default 50), never free text.
  Switching the RMS input re-resolves this authority fresh every time —
  never leaves a stale value or a stale "metadata" label from a
  previously-selected input.
- **Window** (Category C, automatically calculated) and **Method**
  (Category D, fixed operation definition — "True RMS", never a
  one-item dropdown) were already read-only in the original Phase 5B UI;
  this pass adds a small accessible info-tip (`ⓘ`) beside all three
  labels (Nominal Frequency/Window/Method) with concise explanatory text,
  and makes EVERY read-only field in this panel (Unit included) visually
  distinct via a tinted background (`--bg`, the page's own background,
  deliberately different from an editable input's `--panel` background)
  rather than relying on dimmer text alone — the goal stated plainly by
  the owner: "editable → obvious interaction, automatic → obvious
  information."
- **No existing tooltip framework existed in this codebase** (only
  native `title`/`aria-label` on icon buttons, which does not reliably
  support keyboard-focus disclosure or custom Light/Dark styling) — a
  small, genuinely new but deliberately minimal component was added
  (`wwInfoTipHtml()`, pure CSS show/hide on `:hover`/`:focus-visible` of
  a real `<button>`, reusing existing theme tokens), not a tooltip
  library.
- **The backend receives no new capability and was not touched at
  all** — the create request still always carries an explicit
  `nominal_frequency_hz` regardless of where the value came from
  (metadata or user selection), the frontend never sends a derived
  window duration (the backend remains the sole authority, per DEC-048's
  own existing rule), and no method string is ever submitted (Phase 5B's
  backend still only implements true RMS). This is a pure frontend
  parameter-authority/UX clarification — the half-open trailing-window
  formula, eligibility hierarchy, detector, RMS-of-RMS protection, and
  full-resolution authority are completely unchanged and were
  specifically re-verified, not just assumed unaffected. See
  [MIGRATION_PLAN.md — Phase 5B-UAT](MIGRATION_PLAN.md#phase-5b-uat--clarify-rms-parameter-ui-2026-08-22).

---

## DEC-049 — Global Per-Unit Measurement Mode: workspace-scoped base profiles, backend-only conversion, explicit reassignment, and two-axis (mode/profile) calculated-channel inheritance provenance

Date: 2026-08-22
Status: Approved
Source: explicit owner-approved direction for Phase 5C ("Global Per-Unit
Measurement Mode"), refined through three rounds of plan-review
corrections before implementation began.

Decision:

Oruxa Powerwave gains a global Waveform-page presentation mode —
Engineering Units vs. Per Unit — for Voltage and Current channels only
(Power/Frequency/etc. stay in engineering units this phase; Power/
Reactive-Power/Impedance per-unit is explicitly deferred until a
separate owner-approved phase). Seven locked rules:

1. **Unit mode is pure frontend presentation state** (`ww.unitMode`,
   `"engineering" | "per_unit"`), never persisted server-side — mirrors
   DEC-042's own Absolute/Elapsed precedent. No `GET/PUT .../mode`
   endpoint; every display/measurement endpoint instead takes an
   optional `unit_mode` parameter per request.
2. **The backend is the sole conversion authority.** One shared
   `app/domain/per_unit.py` (`resolve_per_unit()`/`convert_value_to_pu()`/
   `convert_array_to_pu()`/`apply_per_unit_to_value()`/
   `apply_per_unit_to_array()`) is called from every one of the 8
   existing display/measurement endpoints (source + calculated-channel
   waveform/cursor-values/peak-values/annotation-anchor) — never
   duplicated per endpoint, never reimplemented in JS. Each response
   reports one of three statuses per channel: `not_applicable`
   (non-Voltage/Current), `configured` (converted, `unit="pu"`), or
   `base_required` (eligible, no valid base — engineering value/unit
   preserved unchanged). Peak/Callout anchor identity (sample index,
   elapsed time) is never touched by unit mode — only the displayed
   value converts.
3. **No per-channel voltage measurement-basis field exists or is
   needed** — a profile's own declared `voltage_basis` (line-to-line or
   line-to-neutral) is the single source of truth, stated explicitly and
   persistently in the setup UI (not a hover-only tooltip): *"Voltage
   channels assigned to this profile are assumed to use this voltage
   basis."* A measured voltage channel's own per-unit division is always
   a direct `measured / base` — **never an automatic √3 factor**. √3 is
   used **only** internally to normalize a stored line-to-neutral Vbase
   to line-to-line when deriving Ibase
   (`Ibase = Sbase / (√3 × Vbase_LL)`); the MVA Base field is explicitly
   labeled "Three-Phase MVA Base (Sbase)" so this formula's own
   three-phase assumption is never ambiguous.
4. **Profile channel assignment is explicit and never silently steals
   ownership.** `PUT .../profiles/{id}` rejects with a structured
   `channel_already_assigned` error (naming each conflicting channel and
   its current profile) unless a top-level `reassign_conflicting: bool =
   false` field is explicitly set `true` — mirroring RMS's own
   `override` pattern (DEC-048). The frontend's setup modal shows a
   conflicting channel's checkbox disabled with an inline "Already
   assigned to \<profile>" label and a separate, explicit "Move here"
   action; only an explicit confirm-prompt acceptance resubmits with the
   flag set.
5. **Unit normalization is the minimal explicit set**: V/kV for
   voltage, A/kA for current, MVA for apparent power (case-insensitive).
   A measured or base unit outside this set is treated as
   `base_required`-equivalent, never guessed or silently mixed.
6. **Calculated-channel per-unit profile inheritance** (a new
   `derive_per_unit_profile_id(operation, input_profile_ids)` in
   `app/domain/per_unit.py`, structurally parallel to but a SEPARATE
   function from `derive_engineering_type()`, since the rule genuinely
   differs): Reverse Polarity/Absolute Value/Multiply by Constant/RMS
   inherit their single input's own resolved profile verbatim (including
   `None`); Addition/Subtraction inherit only when every input resolves
   to the exact same known profile id, otherwise `None` (never an
   arbitrary pick); a calculated-from-calculated input's own
   already-resolved profile composes transitively through this same
   rule, with no separate recursive-propagation logic.
7. **Two independent axes — `assignment_mode` ("auto" | "manual") ×
   `profile_id`** — track every channel's own per-unit assignment
   (`app/services/per_unit_registry.py`'s `ChannelAssignment`). A single
   `provenance` tag was explicitly rejected during plan review because it
   cannot distinguish "never yet resolved" from "the user deliberately
   unassigned this," and the second case must never silently re-inherit
   later. All four combinations are meaningful and reachable: `auto` +
   profile = currently inherited; `auto` + `None` = unresolved,
   eligible to auto-resolve later; `manual` + profile = explicit
   assignment, never auto-changed; `manual` + `None` = explicit
   unassignment, permanently exempt from auto-inheritance. Source
   channels are always `mode="manual"` from the moment first touched (no
   inheritance concept for them; untouched = no record, unambiguous). A
   calculated channel's record is created in `mode="auto"` at the SAME
   instant the channel itself is created (via
   `derive_per_unit_profile_id()`) and persists for its whole lifetime,
   never absent again. Any direct user interaction with a calculated
   channel's own assignment (assign or unassign) switches it to
   `mode="manual"` permanently. A recompute cascade
   (`recompute_inherited_per_unit_assignments()`) runs whenever any
   channel's resolved profile changes (reassignment, unassignment, or
   profile deletion) — an iterative queue over the EXISTING
   `CalculatedChannel.inputs` list (no new graph structure), skipping any
   dependent whose own mode is `"manual"`, recomputing and cascading
   further for `"auto"` dependents. Profile deletion clears `profile_id`
   to `None` for every affected channel **while preserving its own
   `mode`** — a manually-assigned channel becomes `manual + None`
   (permanently unassigned), an auto one becomes `auto + None` (still
   eligible to resolve again later) — then the cascade runs from there.
   Lifecycle cleanup (Start New Workspace, source removal, calculated-
   channel removal) deletes the assignment record entirely.

**Implementation invariant** (added during final review, before
implementation began): `PerUnitBaseProfile.assigned_channels` and the
registry's own internal reverse index must never diverge — every
mutation path (manual assignment, explicit unassignment, confirmed
reassignment, automatic inherited reassignment, profile deletion,
channel removal) updates both representations atomically, in the same
call, under the registry's own lock. Proven by registry-level tests that
re-check this agreement after every step of the owner's own locked A→G
provenance test sequence (see Reason below).

Reason:

The owner reviewed three successive implementation plans before
approving, each round catching a genuine design gap:

- Round 1: an unguarded profile-reassignment path (silently moving a
  channel's ownership on an ordinary PUT), an ambiguous voltage-basis
  treatment (risking an unwanted automatic √3), and an unlocked
  calculated-channel inheritance rule — all closed by decisions 3/4/6
  above.
- Round 2: an inheritance model that snapshotted a calculated channel's
  profile once at creation and never revisited it — meaning `RMS(VA)`
  would silently go stale the moment `VA` itself moved to a different
  profile. Closed by the recompute-cascade half of decision 7.
- Round 3: the FIRST cascade design used one `provenance` tag
  (`"manual"`/`"inherited"`), which the owner identified as unable to
  distinguish a genuinely never-touched channel from one the user
  explicitly unassigned — the exact case that must NEVER silently
  re-inherit. Closed by the two-axis `mode`/`profile_id` model, verified
  against the owner's own exact worked sequence: `RMS(VA)` inherits A →
  `VA` moves to B, `RMS(VA)` follows → user manually assigns `RMS(VA)`
  to C → `VA` moves again, `RMS(VA)` stays C → user explicitly unassigns
  `RMS(VA)` → `VA` moves again, `RMS(VA)` stays `base_required` → delete
  profile C, `RMS(VA)` becomes `manual + None` and does not
  unexpectedly re-inherit.

Backend-authoritative conversion (decision 2) follows the same
"never duplicate engineering logic across layers" principle already
established for waveform reduction, peak/cursor resolution, and RMS
itself (DEC-047/DEC-048) — the frontend's job is display, never
computation.

Alternatives considered:

- **Per-channel measurement-basis metadata** (rejected, decision 3) —
  no COMTRADE/domain field exists for this today, and inventing one
  would be speculative; the profile's own declared basis, applied
  explicitly and only to Ibase derivation, is simpler and sufficient.
- **Automatic reassignment on channel-conflict** (rejected, decision 4)
  — silently moving ownership on an ordinary save is exactly the kind of
  surprising, hard-to-audit behavior the owner's round-1 correction
  explicitly ruled out.
- **A single `provenance` tag for inheritance** (rejected, decision 7,
  round 3) — cannot represent "explicitly unassigned" as a state
  distinct from "never touched," which is the one case this entire
  design exists to get right.
- **Full per-unit support for Power/Reactive-Power/Impedance in this
  same phase** (rejected/deferred) — the owner's own spec explicitly
  scoped this phase to Voltage/Current only, pending Phase 5C UAT.

Impact:

New: `app/domain/per_unit.py`, `app/services/per_unit_registry.py`
(the `PerUnitRegistry` + co-located `recompute_inherited_per_unit_assignments()`),
`app/api/v1/per_unit.py`, `app/schemas/per_unit.py`,
`app/services/per_unit_service.py`. Modified: `app/main.py` (third
sibling registry, wired the same way as `WorkspaceRegistry`/
`CalculatedChannelRegistry`), `app/api/v1/workspaces.py` (workspace
lifecycle), `app/api/v1/sources.py` and `app/api/v1/calculated_channels.py`
(the 8 endpoints gain `unit_mode`, plus per-unit lifecycle cleanup on
source/calculated-channel removal), `app/services/waveform_service.py`
and `app/services/calculated_channel_service.py` (per-unit resolution
wired into every display/measurement result, and the inheritance-seeding
call at calculated-channel creation time), `app/services/errors.py`
(4 new error classes). Frontend (`frontend/index.html` only): `ww.unitMode`/
`ww.perUnitProfiles` state, the Unit Mode toolbar dropdown (cloned from
the Annotate split-button pattern), the "Manage Per-Unit Bases" modal
(cloned from the Custom Groups editor's working-copy-until-Apply shell),
`unit_mode` wired into every one of the 8 fetch call sites plus the
Calculated Channels preview, and a per-unit-status suffix in
`wwPanelGroupKeyFor()`/`wwPanelLabelFor()` that keeps a `configured`
(pu-converted) channel and a `base_required` (engineering-unit) channel
of the same type in separate panels — the core "never mix pu and
engineering values on one shared axis" safety guarantee. New/updated
tests: `test_per_unit_domain.py`, `test_per_unit_registry.py` (including
the full owner-specified A→G provenance sequence, re-verified against
the assigned_channels/reverse-index invariant after every step),
`test_per_unit_api.py`, `test_per_unit_display_endpoints.py`,
`test_frontend_per_unit_mode.py`. See
[MIGRATION_PLAN.md — Phase 5C](MIGRATION_PLAN.md#phase-5c--global-per-unit-measurement-mode-2026-08-22).

**Update (2026-08-22, same day) — source-bound redesign following owner
UAT**: initial UAT on the profile-based workflow above found it too
complex — the engineer had to create a profile, name it, select it, and
manually assign each ordinary channel to it before Per Unit mode did
anything. The owner approved a simpler model, changing the mental model
from "Profile → assignments → channels → bases" to "File/source → base
values → automatic PU conversion":

- **Every Per-Unit base configuration is now owned 1:1 by a source_id**
  (`workspace_id` + `source_id`, the existing stable identity — never
  the filename, which two uploads can legitimately share). There is no
  separate, independently-created "profile" identity or name any more;
  `PerUnitBaseProfile.source_id` IS the configuration's own key.
  `PUT/DELETE .../per-unit/sources/{source_id}` replace the old
  `/per-unit/profiles` CRUD entirely; `GET .../per-unit/sources` lists
  every source currently in the workspace (configured or not), so the
  engineer never has to "create" anything to see their file listed.
- **Automatic eligible-channel association**: every Voltage/Current
  channel belonging to a configured source now resolves to that
  source's own configuration unconditionally — no assignment record, no
  checklist, no `channel_already_assigned` conflict concept, since a
  channel's owning source is fixed and can never collide with another
  source's configuration. This eliminated the entire channel-assignment
  reverse index for source channels (`PerUnitRegistry.profile_for_channel()`
  now derives the answer directly from `source_id` + `engineering_type`,
  with no bookkeeping to keep in sync — the invariant this same decision
  record used to require is now structurally impossible to violate for
  source channels).
- **Canonical base units**: Voltage Base/Apparent Power Base/Direct
  Current Base are now always kV/MVA/kA respectively — no unit dropdown
  (the setup UI shows a fixed, non-editable suffix instead), matching
  the owner's own explicit UI-simplification request. The MEASURED
  channel's own unit conversion (V/kV, A/kA) is completely unaffected —
  decision 3/5's own unit-normalization rule for a channel's own
  declared unit is untouched.
- **"Voltage Basis" renamed "Voltage Reference"**, with clearer values
  (Line-to-Ground/Line-to-Line, not "line_to_neutral") and, new this
  pass, **automatic detection** (`app.domain.voltage_reference`): a
  small, deterministic, phase-naming pattern matcher (never a
  probabilistic classifier, never waveform-magnitude analysis — both
  explicitly deferred by the owner) that inspects a source's own Voltage
  channel names (VR/VY/VB, VA/VB/VC, VAN et al. → Line-to-Ground;
  VRY/VYB/VBR, VAB/VBC/VCA, VLL/VBUS et al. → Line-to-Line) and reports
  either a confident result with its own evidence (the exact channel
  names that matched, shown verbatim in the UI) or an honest "could not
  determine automatically" — never a silently invented default.
  Contradictory evidence within one source is treated as equally
  inconclusive, never resolved by whichever pattern happened to match
  first.
- **Manual override remains fully available**, tracked with the SAME
  two-axis `mode`/`value` shape this decision record already established
  for calculated-channel inheritance (`voltage_reference_mode:
  "auto"|"manual"`, `voltage_reference_override`) — "Return to Auto"
  reruns the live detection rather than resurrecting a stale manual
  choice.
- **Calculated-channel inheritance (decision 6/7) is UNCHANGED** per the
  owner's own explicit "do not redesign calculated-channel PU
  behaviour" instruction — `derive_per_unit_profile_id()` and the
  recompute cascade operate identically; the only difference is that the
  "profile_id" flowing through them is now always literally a
  `source_id` (a configuration and its owning source share one identity
  now), never a separately-generated id.
- **The proven conversion mathematics are completely unchanged**:
  `measured / base` for a Voltage channel's own division (still never an
  automatic √3), and `Ibase = Sbase / (√3 × Vbase_LL)` for Current,
  where √3 is applied ONLY to normalize a Line-to-Ground Vbase before
  that division — exactly as before, just with the LL/LG determination
  now resolved automatically (or manually overridden) instead of coming
  from a static stored field.

New: `app/domain/voltage_reference.py`. Rewritten:
`app/domain/per_unit.py` (canonical units, `resolve_effective_voltage_reference()`),
`app/services/per_unit_registry.py` (source-keyed storage, automatic
source-channel resolution, calculated-channel assignment retained),
`app/services/per_unit_service.py`, `app/schemas/per_unit.py`,
`app/api/v1/per_unit.py` (new `/per-unit/sources` routes). 3 error
classes retired (`PerUnitProfileNotFoundError`,
`ChannelAlreadyAssignedError`, `InvalidChannelAssignmentError`) — no
longer meaningful once assignment conflicts became structurally
impossible. Frontend (`frontend/index.html` only): the "Manage Per-Unit
Bases" modal fully redesigned (a source select/list replaces the old
profile select + channel checklist; a proportional Voltage Base field
with a fixed unit suffix instead of a cramped-number/wide-dropdown
layout; the Voltage Reference auto/override/ambiguous-fallback UI;
three labeled Current Base radio options replacing the old bare
dropdown) — the toolbar control, every `unit_mode`-carrying fetch call
site, and the per-unit-status panel-grouping logic were all UNCHANGED by
this pass (they never depended on the profile-vs-source distinction).
766 backend tests pass (up from 758; some retired-workflow tests
replaced, new voltage-reference/source-ownership tests added), 17
frontend regression checks, and direct Playwright verification of the
owner's own exact UAT target flow (upload File A, configure it, upload
File B with the identical filename, confirm it stays independently
unconfigured, Start New Workspace clears both). See
[MIGRATION_PLAN.md — Phase 5C-UAT](MIGRATION_PLAN.md#phase-5c-uat--source-bound-per-unit-redesign-2026-08-22).

---

## DEC-050 — Per-Unit measurement model is clarified to be measurement-group-aware; the currently deployed source-bound model (DEC-049) is not the final target

Date: 2026-08-22
Status: Approved — product/engineering direction; **implementation
pending**. This decision authorizes documentation and a canonical
specification only; it does not authorize any code change.
Source: explicit owner-supplied clarification of Per-Unit requirements,
following further reflection after DEC-049's source-bound redesign
shipped and passed initial UAT.

Decision:

The source-bound model DEC-049 describes (`source_id → one PU
configuration`, applied to every eligible Voltage/Current channel of
that source) is **not the final target** for any recording whose
channels span more than one electrical measurement context — which the
owner has clarified is common, not an edge case, for disturbance
recorders installed at multi-voltage-level substations (e.g. a
275/132 kV site recording bus voltages, line currents, and an interbus
transformer's HV and LV currents all in one COMTRADE file).

The authoritative future direction is:

```text
source
→ measurement groups
→ group-specific base configuration
```

replacing the current:

```text
source
→ one Vbase
→ one Ibase
```

The full engineering/product specification for this target — the
Measurement Group concept, per-group Voltage/Current base handling,
voltage-reference interpretation rules, the open review item on
phase-to-ground PU voltage mathematics, calculated-channel implications,
identity model, and known deficiencies in the current implementation —
is recorded in
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md), which
this decision designates **authoritative** for all future Per-Unit work
and is deliberately **not duplicated here**.

Reason:

DEC-049's source-bound model was itself an owner-approved simplification
of an even more complex profile-based design, adopted because the
profile-based workflow was "too complicated for the engineer." That
simplification correctly solved the *workflow* complexity problem, but
in doing so collapsed the base configuration to one-per-source — which
is only valid for a source whose channels all belong to a single
electrical measurement context. The owner has since clarified that this
is not a safe assumption for real disturbance recordings at multi-level
substations, and that the underlying data model — not just the UI —
needs to support multiple measurement groups per source, each with its
own base.

Separately, an explicit code-level review performed while assembling
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) (§8 of
that document) confirmed a genuine mismatch between the currently
deployed Voltage per-unit division and the clarified requirement that a
healthy phase-to-ground measurement on a nominal 275 kV system should
read ≈1.0 pu when 275 kV LL is entered as the base — the current code
divides directly by the raw entered Vbase with no reference-aware
adjustment. This is recorded as an open review item, not resolved by
this decision.

Alternatives considered:

- **Treat DEC-049 as sufficient and defer the multi-group requirement
  indefinitely** — rejected; the owner was explicit that a single
  source spanning multiple voltage levels is a normal case for this
  application's actual users (substation disturbance recordings), not a
  rare exception worth permanently ignoring.
- **Silently extend the current source-bound code to approximate
  grouping without a canonical specification** — rejected; per the
  owner's explicit instruction, this pass is documentation and
  agent-coordination only, specifically so that Claude and Codex share
  one understanding before any implementation begins, rather than each
  independently guessing at the shape of "groups."
- **Rewrite DEC-049's own history to describe the target model as
  already decided that way** — rejected; DEC-049 remains an accurate
  record of what was actually approved and built at the time. This
  decision supersedes DEC-049's *scope* (it is no longer considered the
  final target), not DEC-049's *history*.

Impact:

**No application code, frontend code, or backend test was modified by
this decision.** New:
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) (the
canonical specification, now authoritative for all future Per-Unit
work). Updated: [CURRENT_STATE.md](CURRENT_STATE.md) (PU implementation
work is paused pending alignment),
[MIGRATION_PLAN.md](MIGRATION_PLAN.md) (a new planned migration phase,
stages only, not implementation steps), [HANDOFF.md](HANDOFF.md) (next
session must read the canonical document and perform an independent
architecture/code review before continuing any PU implementation),
[AGENTS.md](../../AGENTS.md) and [CLAUDE.md](../../CLAUDE.md) (explicit
pointer to the canonical document for PU-related work). See
[MIGRATION_PLAN.md — Phase 6](MIGRATION_PLAN.md#phase-6--per-unit-measurement-model-alignment-documentation-only-2026-08-22).

**Update (2026-08-23) — remaining owner decisions clarified; Slice 1
prepared, not started:**

Following further owner review, most items this decision had left
`[OPEN]` in [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md)
are now resolved as **approved product/engineering direction —
implementation still pending**. This update does not change DEC-049's
own history, and does not itself authorize any code change — it records
newly approved decisions and refines the implementation sequence.

Newly approved decisions (full detail in
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md), not
duplicated here):

1. **Nominal voltage base is entered as the familiar nominal system
   line-to-line voltage** (500 kV / 275 kV / 132 kV, etc.) — the
   engineer enters one number regardless of how an individual channel
   happens to be measured.
2. **Phase-to-ground channels derive their applicable base as
   `Vbase_phase = Vbase_LL / √3`** — a healthy phase-to-ground waveform
   on a nominal 275 kV system (≈158.8 kV) should read ≈1.0 pu.
   Line-to-line channels continue to use `Vpu = Vmeasured_LL / Vbase_LL`
   directly. **This supersedes the previous blanket statement "never
   apply √3 to measured voltage division"** — the corrected governing
   principle is: *the PU denominator must match the electrical reference
   of the measured channel.* The original rule's underlying intent (never
   fabricate an LL-equivalent measurement from an LG reading, or vice
   versa) is preserved; what changes is that selecting the correct
   denominator for an LG channel now derives a phase base from the
   entered LL base, rather than dividing directly by the raw LL number.
   `[FACT]`-confirmed via direct code reading that the currently
   deployed `resolve_per_unit()` does not yet do this (§8 of the
   canonical document) — not fixed by this update, Slice 3 work.
3. **Voltage-reference detection must prioritize explicit electrical
   phase/pair representation over generic location/equipment
   vocabulary** — e.g. "NORTH BUS VA/VB/VC" must still be interpreted
   as individual phase-to-ground channels; the word "BUS" must never
   override explicit phase structure. `[FACT]`-confirmed via direct code
   reading that `_classify_one_channel_name()` in
   `backend/app/domain/voltage_reference.py` currently checks its
   `"BUS"/"LL"` substring evidence *before* the single-phase-letter
   case, so a name like "NORTH BUS VA" is misclassified as
   Line-to-Line today — a second, distinct conflict from item 2, also
   not fixed by this update, also Slice 3 work.
4. **A current measurement group's applicable voltage base may either
   link to an existing voltage measurement group, or use an
   independent/manual Vbase** when no suitable voltage group exists in
   the recording — current groups must not be forced to depend on a
   voltage-channel group.
5. **Initial target current-base methods are Equipment Rating (Sbase +
   applicable Vbase → Ibase), Manual Ibase, and Not Configured** — CT
   primary reference is explicitly excluded from the initial
   measurement-group implementation (not merely deprioritized).
6. **CT/VT ratio is measurement scaling, never Per-Unit normalization**
   — a CT/VT-derived primary value is still an engineering-unit value,
   not a PU value; CT/VT rating must never silently become the default
   PU base. A five-layer measurement pipeline (raw/recorder measurement
   → CT/VT scaling → primary engineering value → disturbance analysis →
   PU normalization → pu) is recorded to keep these concerns
   architecturally separate.
7. **Calculated-channel PU inheritance, for the first group-aware
   implementation, is conservative**: a same-group calculation (e.g.
   `-IA`, `abs(IA)`, `IA + IB` where every input resolves to the same
   compatible measurement group) may inherit that group's base;
   cross-group, cross-source, or otherwise incompatible-base
   calculations do not invent a PU base and resolve to `base_required`
   instead. This is the existing source-level
   `derive_per_unit_profile_id()` rule shape, confirmed as the correct
   starting point extended from `source_id` to `measurement_group_id`
   — no new inheritance algorithm needs inventing.
8. **Automatic grouping uses a Suggested → Confirmed lifecycle, not a
   mandatory per-group confirmation step**: high-confidence suggestions
   may appear already grouped in the configuration UI; the engineer's
   own act of reviewing/configuring/saving a group's base promotes it
   from Suggested to Confirmed. Uncertain/contradictory grouping must
   render as `Needs review` and must never silently drive PU conversion
   — it behaves like an unconfigured/`base_required` group until
   resolved.
9. **The target domain model avoids one generic base object with many
   irrelevant nullable fields**, using a `MeasurementGroup` (id,
   source_id, kind, display_name, channel_refs, grouping_status,
   type-specific configuration) with separate `VoltageBaseConfiguration`
   and `CurrentBaseConfiguration` shapes — conceptual, not a forced
   class/file structure.

**Revised implementation sequence** (sequencing only, not a standing
authorization to proceed slice-by-slice without further approval — each
slice still requires its own review):

```text
Slice 1 — Measurement-group domain model + identities + invariants
Slice 2 — Deterministic automatic grouping (suggested/confirmed/ambiguous)
Slice 3 — Voltage groups (corrected detection + LL/LG PU base resolution)
Slice 4 — Current groups (equipment-rating/manual/none + voltage linking)
Slice 5 — Group-aware PU resolution (display/measurement endpoints)
Slice 6 — Frontend group-based configuration workspace
Slice 7 — Calculated-channel same-group inheritance
Slice 8 — migration, regression, performance verification and UAT
```

**The only authorized next implementation step is Slice 1** —
measurement-group domain model, identities, and invariants only. Slice 1
must not change voltage/current PU math, waveform display, frontend UI,
the grouping algorithm, or calculated-channel behaviour, and must not
change API behaviour beyond strictly internal scaffolding. The final
Slice 1 implementation prompt is issued separately; this decision update
does not itself start it.

Mark: **Approved engineering/product direction. Implementation
pending.**

Reason:

Owner review of the initial DEC-050 direction identified that several
items left open for later review had concrete answers the owner already
held (the LL/phase-base relationship, the current-group-to-voltage-group
linking shape, the CT/VT-vs-PU distinction, the conservative calculated-
channel rule, and the grouping-confirmation UX) — recording them now,
before any Slice 1 work begins, avoids each future agent session
re-deriving or re-guessing the same answers independently.

Impact:

**No application code, frontend code, or backend test was modified by
this update.** Updated:
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) (§6, §8,
§9/§10/§11/§12, §15, §18, §19 revised; new §24/§25 implementation-
sequence and Slice-1-scope sections), [CURRENT_STATE.md](CURRENT_STATE.md),
[MIGRATION_PLAN.md](MIGRATION_PLAN.md), [HANDOFF.md](HANDOFF.md). See
[MIGRATION_PLAN.md — Phase 7](MIGRATION_PLAN.md#phase-7--per-unit-measurement-model-decision-clarification-documentation-only-2026-08-23).

---

## DEC-051 — DEC-049/DEC-050 live-endpoint coexistence precedence: group membership, not configuration completeness, decides which resolver applies to a channel

Date: 2026-08-24
Status: Approved — implemented (DEC-050 Slice 5).
Source: the Slice 5 implementation task's own explicit "preferred
compatibility principle" (Slice 5 prompt, section 8), confirmed against
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) and this
document's own DEC-050 entry, neither of which defines any DEC-049/
DEC-050 coexistence rule (verified by direct search before
implementation — the gap was real, not merely unclear wording).

Decision:

Now that DEC-050's group-aware resolver is wired into the live source
display/measurement endpoints (Slice 5) alongside the still-live DEC-049
source-wide resolver, exactly one of them applies to any given channel
per request, decided by a single, simple, structural fact — **channel
membership in a `MeasurementGroup`, never configuration completeness**:

```text
channel IS a member of a MeasurementGroup
    → DEC-050 group-aware resolution is authoritative for that channel
    → its outcome (configured OR base_required) is final
    → DEC-049's source-wide profile is never additionally consulted
      for it, and never silently overrides it

channel is NOT a member of any MeasurementGroup
    → the existing DEC-049 source-wide resolution applies, completely
      unchanged from pre-Slice-5 behaviour
```

Concretely: a channel assigned to a Voltage/Current group whose own
configuration is incomplete (no base set, current method `none`, a
stale/deleted linked-group reference, etc.) resolves as `base_required`
— it does **not** fall back to a source-wide DEC-049 base that happens
to exist on the same source, even though that number is available.
Conversely, a channel with no group membership at all is completely
unaffected by Slice 5 and behaves exactly as it did before this slice,
including using a DEC-049 profile if one is configured.

Reason:

The two systems needed *some* precedence the moment they became live on
the same endpoints for the same requests — silence in the canonical
docs could not be resolved by inventing an ad-hoc rule mid-implementation
(this document's and CLAUDE.md's own change-governance expectation).
The task's own preferred principle ("DEC-050 becomes the correct path
for channels with valid group-specific bases; DEC-049 remains available
for backwards compatibility; DEC-049 must never silently override an
explicit DEC-050 configuration") was verified to not contradict either
canonical document, so it was implemented as given rather than treated
as a fresh invention. Membership (not "did the group happen to resolve
successfully") was chosen as the actual switch because the alternative
— falling back to a source-wide number whenever a channel's own group
configuration is merely incomplete — is exactly the kind of "silently
borrow another base" behaviour `PER_UNIT_MEASUREMENT_MODEL.md` section
21 already forbids, and would make a grouped channel's PU status depend
on ambient, unrelated source-wide state instead of its own group's
explicit configuration.

**A material de-risking fact, confirmed before implementation**: no
frontend UI exists yet (Slice 6) to create a `MeasurementGroup` through
the live application, and no upload-time or display-time auto-grouping
trigger exists (Slice 2's detector remains standalone-only, per its own
scope and per this slice's own explicit "do not invoke the grouping
detector during display requests" instruction). Every `MeasurementGroupRegistry`
is therefore empty for the life of the process unless something calls
`create_group()`/`generate_suggested_groups_for_source()` directly —
which nothing in the live, reachable application does. This decision's
behaviour change is consequently **dormant for every real user session
today**: it cannot retroactively change any already-observed PU output,
since no real session can have populated a measurement group in the
first place. This is why the decision could be implemented directly
rather than deferred pending owner sign-off — the risk profile of "an
additive code path with zero live trigger" is the same one already
established and accepted for Slices 1-4.

Alternatives considered:

- **A brand-new, separate `unit_mode` value (e.g. `"per_unit_group"`)
  that never touches the existing `"per_unit"` behaviour at all** —
  rejected for this slice: every one of the task's own required
  integration-test scenarios (two voltage levels, LG/LL groups,
  transformer HV/LV sides, manual Ibase, etc.) is written against the
  EXISTING `unit_mode="per_unit"` request shape, and the frontend isn't
  being touched to ever send a new mode value regardless — a separate
  mode would have made Slice 5's own required tests impossible to
  satisfy through the live endpoint contract without also touching the
  frontend, which is explicitly out of scope until Slice 6.
- **DEC-049 wins whenever it is configured, DEC-050 only as a fallback**
  — rejected; this is the literal inverse of the task's own explicit
  instruction ("do not allow DEC-049 to silently override an explicit
  DEC-050 group-specific configuration") and would make a grouped
  channel's correct, purpose-built configuration invisible behind
  whatever legacy source-wide profile happens to exist.
- **A grouped-but-`base_required` channel falls back to the DEC-049
  source-wide base if one exists** — rejected; this blends two
  independent configuration authorities for one channel, is exactly the
  "silently borrow another base" pattern the canonical document forbids
  (section 21), and would make a channel's displayed PU value depend on
  unrelated, ambient source-wide state rather than its own explicit
  group configuration.

Impact:

New `backend/app/services/group_aware_per_unit.py` (the resolution
bridge implementing this precedence) and its own test coverage. Modified
`backend/app/services/waveform_service.py` (one new dispatch helper,
`_resolve_effective_per_unit()`, inserted ahead of every existing
`resolve_per_unit()` call site) and `backend/app/api/v1/sources.py`
(the three group-configuration registries threaded through as new
optional dependencies on the four live source display endpoints). No
existing DEC-049 code path (`per_unit.py`/`per_unit_registry.py`/
`per_unit_service.py`/the `/per-unit/sources` API) was modified. See
[MIGRATION_PLAN.md — Phase 11](MIGRATION_PLAN.md#phase-11--dec-050-slice-5-group-aware-per-unit-resolution-in-live-display-endpoints-2026-08-24).

**Update (2026-08-25) — extended to calculated-channel display
endpoints (DEC-050 Slice 7); one new conservative restriction flagged
for owner review, not treated as approved by this update:**

Slice 7 wires the identical precedence rule above one layer up, for a
calculated channel's four `unit_mode`-aware endpoints
(`.../calculated-channels/{id}/waveform`, `.../cursor-values`,
`.../peak-values`, `.../{id}/annotation-anchor`). A calculated channel
is never added to `MeasurementGroupRegistry` (group membership stays
source-channels-only, per Slice 1's own scope) — so "is this channel a
member of a group" is not directly askable for it the way it is for a
source channel. Instead, the equivalent structural fact is **derived**
at request time by walking the calculated channel's own
`inputs: list[ChannelRef]` (reusing `derive_per_unit_profile_id()`
UNCHANGED, per
[PER_UNIT_MEASUREMENT_MODEL.md §19](PER_UNIT_MEASUREMENT_MODEL.md#19-calculated-channel-implications--decision-initial-rule-approved-2026-08-23-implementation-pending)'s
own confirmed direction — "the same function, extended from `source_id`
to `measurement_group_id`... no new inheritance algorithm needs to be
invented"), never persisted onto the channel or the registry:

```text
calculated channel's inputs resolve, unambiguously, to ONE
measurement_group_id (recursing through calculated-on-calculated
chains the same way DEC-049's own inheritance already does)
    → DEC-050 group-aware resolution is authoritative for it
    → its outcome (configured OR base_required) is final
    → the existing DEC-049 calculated-channel-profile inheritance
      is never additionally consulted for it, and never silently
      overrides it

calculated channel's inputs do NOT resolve to one unambiguous
measurement_group_id (any input ungrouped, cross-group, cross-source,
or an operation this update excludes -- see below)
    → the existing DEC-049 calculated-channel-profile resolution
      applies, completely unchanged from pre-Slice-7 behaviour
```

This is the same precedence shape as the base DEC-051 decision above,
applied at the calculated-channel layer instead of the source-channel
layer — not a new coexistence rule requiring separate owner review.

**One additional restriction this update DOES introduce, which was NOT
already decided anywhere and is flagged here for explicit owner
review rather than asserted as approved policy**: even when a
calculated channel's Addition/Subtraction inputs unanimously resolve to
the same Voltage `MeasurementGroup`, this implementation does **not**
inherit that group's base. Reason: this codebase has no metadata
anywhere distinguishing a Voltage group's own phase-to-ground vs.
phase-to-phase reference from the physical reference an Addition/
Subtraction of two of that group's own channels actually produces —
e.g. `VR - VY` on a phase-to-ground group is numerically a
phase-to-phase quantity, but the group's own resolved denominator
remains phase-to-ground; dividing the former by the latter would
silently produce a **wrong** PU value (not merely a missing one),
which is a materially worse failure mode than the `base_required` this
restriction produces instead. A Current group has no equivalent
reference-frame concept (Ibase is one scalar regardless of phase), so
Current-group multi-input arithmetic is unaffected. Unary operations on
a Voltage group (`-VR`, `abs(VR)`, `VR * k`, `RMS(VR)`) are unaffected
too — none of them can change which physical reference the result
represents. See
`backend/app/services/calculated_group_aware_per_unit.py`'s own module
docstring for the full reasoning. **This restriction was flagged here
as implemented-but-not-yet-approved; the owner has since explicitly
approved it as canonical policy (Slice 8, 2026-08-26) — see
[DEC-052](#dec-052--voltage-multi-input-additionsubtraction-calculated-channels-never-inherit-a-dec-050-measurement-group-base)
below, which formalizes this exact rule with no code change (Slice 7's
implementation already matched it verbatim).**

Impact (Slice 7 addition): new
`backend/app/services/calculated_group_aware_per_unit.py` (the
resolution bridge + inheritance derivation) and its own resolver-level
and live-endpoint test coverage. Modified
`backend/app/services/calculated_channel_service.py` (one new dispatch
helper, `_resolve_effective_per_unit_for_calculated_channel()`, mirrors
`waveform_service._resolve_effective_per_unit()` exactly) and
`backend/app/api/v1/calculated_channels.py` (the three group-
configuration registries threaded through as new optional dependencies
on the four calculated-channel display endpoints). `backend/app/services/group_aware_per_unit.py`
had its Voltage/Current config-resolution core extracted into a shared
`resolve_per_unit_for_group()` function (pure refactor, behaviour
unchanged, re-verified by its own full existing test suite) so Slice 7
reuses it rather than duplicating the Voltage/Current resolution logic
a second time. No existing DEC-049 calculated-channel code path was
modified. See
[MIGRATION_PLAN.md — Phase 13](MIGRATION_PLAN.md#phase-13--dec-050-slice-7-calculated-channel-per-unit-inheritance-2026-08-25).

---

## DEC-052 — Voltage multi-input Addition/Subtraction calculated channels never inherit a DEC-050 Measurement Group base

Date: 2026-08-26
Status: Approved — implemented (already shipped, verbatim, in DEC-050
Slice 7; this decision formalizes the rule as canonical, no code
change).
Source: explicit owner approval, issued as the opening instruction of
the DEC-050 Slice 8 task, promoting the restriction Slice 7 had shipped
as an implemented-but-flagged conservative default (see DEC-051's own
Slice 7 addendum) into approved policy.

Decision:

A calculated channel that combines two or more Voltage inputs via
Addition or Subtraction (the only two multi-input operations this
codebase supports) does **not** inherit a DEC-050 `MeasurementGroup`'s
Voltage Base, even when every input unanimously resolves to the exact
same, fully confirmed Voltage group. It resolves `base_required`
instead.

```text
VR, VY both belong to the SAME 275 kV phase-to-ground Voltage group

VR - VY

Physical output: line-to-line voltage
Group's own resolved denominator: 275 / sqrt(3)  (phase-to-ground)

→ dividing the numerically-LL result by the LG denominator would be
  SILENTLY WRONG, not merely unavailable
→ approved behaviour: base_required
```

This applies **only** to Voltage-group multi-input arithmetic. It does
**not** apply to:

- unary Voltage operations on a Voltage-group input (`-VR`, `abs(VR)`,
  `VR * k`, `RMS(VR)`) — none of these can change which physical
  reference (LG vs. LL) the result represents, so they continue to
  inherit the group's base exactly as before;
- Current-group multi-input arithmetic (`IR + IY`, etc.) — a Current
  group's Ibase is one scalar with no phase-reference concept, so no
  equivalent ambiguity exists.

Do not infer LG/LL from a calculated channel's own name, and do not
divide a multi-input Voltage result by the input group's LG denominator
regardless of naming convention — both are explicitly rejected
approaches (see Alternatives below).

Reason:

The current calculated-channel domain model
(`app.domain.calculated_channel`) carries no operation-level metadata
that distinguishes "this Addition/Subtraction of two phase-to-ground
channels produces a phase-to-phase quantity" from any other
Addition/Subtraction. Guessing the correct denominator from context
(group membership, channel naming, or the operation alone) risks a
**silently wrong** displayed PU value, which is a strictly worse
outcome for an engineer reviewing a disturbance recording than an
honest `base_required` state that visibly asks for configuration.
`base_required` is therefore the only behaviour consistent with this
project's own repeated principle (first stated in DEC-049, reaffirmed
throughout DEC-050): never fabricate a PU value from an unproven
electrical reference.

Alternatives considered:

- **Infer LG/LL from calculated-channel or input channel naming
  conventions** (e.g. treat `VR`/`VY`/`VB`-style names as always LG) —
  rejected; naming conventions are not a reliable or verifiable
  electrical fact, and DEC-050's own voltage-reference detection
  principle (§6 of
  [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md)) was
  adopted specifically because generic vocabulary/naming evidence is
  weaker than explicit structure — extending naming-based inference
  into calculated-channel arithmetic would reintroduce exactly the
  class of bug that principle was written to prevent.
- **Divide by the inherited group's own LG denominator regardless of
  the operation** — rejected; this is precisely the silently-wrong
  case this decision exists to prevent (a genuine LL quantity divided
  by an LG base produces a plausible-looking but numerically incorrect
  PU value with no visible warning).
- **Build full operation-level Voltage-reference metadata now** (e.g.
  classify certain Addition/Subtraction pairs as "produces LL") —
  rejected for this decision; the owner's own instruction is explicit
  that this is not authorized in Slice 8 ("do not create broader
  DEC-052 functionality now"). This decision formalizes the
  `base_required` default only; richer metadata remains a genuine
  future option (see
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md) Slice 8 follow-ups list).

Impact:

**No code change** — `app.services.calculated_group_aware_per_unit`
already implements exactly this rule (the `MULTI_OPERATIONS` +
`KIND_VOLTAGE` exclusion in `resolve_calculated_group_aware_per_unit()`,
shipped in Slice 7,
[8ccaf4a](https://github.com/myza81/oruxa-powerwave/commit/8ccaf4ad02ed62cfd715f4cca65983023c3f4cd1)).
This decision's only effect is documentation: it removes the "flagged,
not yet owner-approved" caveat DEC-051's Slice 7 addendum carried, and
gives the existing behaviour a permanent decision record so it is never
mistaken for an oversight or accidentally "fixed" by a future session
into inheriting the group's base. Cross-referenced from
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) and
[CURRENT_STATE.md](CURRENT_STATE.md) (DEC-050 Slice 8).

---

## DEC-053 — Waveform time synchronization Slice 1: manual, per-source alignment offset; first-uploaded source is the deterministic reference; the backend owns the offset value, the frontend applies the transform

Date: 2026-08-26
Status: Approved
Source: explicit project-owner instruction, delivered as a dedicated
"Slice 1 of waveform time synchronization" implementation prompt.

Decision:

**An engineer can manually shift one uploaded source's waveform display
left or right in time, relative to a deterministic reference source, to
visually align two recordings of the same physical event — without
altering any original source timestamps or waveform data, and without
implying a common mathematical sample grid.**

Concretely:

- Core mapping: `workspace_time = source_time + alignment_offset_s`
  (inverse: `source_time = workspace_time - alignment_offset_s`).
  `source_time` (a source's own native elapsed time,
  `waveform_data["time"]`) is never altered. `workspace_time` is the
  synchronized/display coordinate this app already treated as its one
  shared viewport/Plotly-X coordinate system (DEC-036) — prior to this
  slice that coordinate system was implicitly every source's own raw
  elapsed time (an always-zero offset); this slice makes the offset
  explicit and engineer-adjustable per source, without otherwise
  changing that architecture.
- **Backend is the authoritative owner of the offset VALUE only.** A new
  `SynchronizationRegistry` (`app/services/synchronization_registry.py`,
  the same in-memory, ephemeral, workspace-scoped shape as
  `PerUnitRegistry`) stores `alignment_offset_s` keyed by
  `(workspace_id, source_id)`; a new thin API
  (`app/api/v1/synchronization.py`, under
  `/api/v1/workspaces/{workspace_id}/synchronization`) exposes list/get/
  put/reset-one/reset-all. The backend never applies the offset to
  waveform/cursor/digital-waveform data itself — those three existing
  endpoints are completely unmodified.
- **The frontend applies the transform, at the request/response boundary
  of each existing fetch.** This mirrors DEC-042's own established
  "presentation-layer transform, not a backend data authority"
  precedent for Absolute/Elapsed time-mode, applied here to a second,
  independent presentation transform. `wwFetchChannelRange()` converts
  a workspace-time fetch range to source-native before calling
  `.../waveform` (unchanged), then shifts the returned `time` array back
  into workspace time; `wwFetchCursorValuesForSource()` does the
  equivalent inverse mapping for cursor A/B times before calling
  `.../cursor-values` (unchanged). Digital channels are fetched once in
  full (unchanged) and the offset is applied only at RENDER time
  (`wwDigitalHighIntervals()`/`wwRebuildDigitalChart()`), not baked into
  the stored transition data — an offset change therefore never needs a
  digital re-fetch, only a cheap re-render.
- **Reference source rule (deterministic, no selector UI)**: the
  workspace's reference source is always the one with the EARLIEST
  `SourceMetadata.created_at` (`app.domain.synchronization.reference_source_id_for_workspace`,
  ties broken on `source_id` for determinism) — recomputed fresh on
  every request, never cached/persisted, so it never goes stale as
  sources are added/removed. Its own offset is always `0`; the backend
  rejects (`409 reference_source_alignment_not_allowed`) any attempt to
  set it to a non-zero value directly.
- **Reversible everywhere required**: resetting one source
  (`DELETE .../synchronization/sources/{source_id}`), resetting all
  (`DELETE .../synchronization/sources`), source removal
  (`app.api.v1.sources.delete_source` now also calls
  `remove_source_alignment()`), and workspace reset
  (`app.api.v1.workspaces.delete_workspace` now also calls
  `remove_workspace_alignment()`) all correctly clear synchronization
  state — the frontend's own `ww.alignmentOffsets`/`ww.referenceSourceId`
  mirror is cleared only by "Start New Workspace" (same lifecycle policy
  as `ww.perUnitSourceConfigs`), never by the plain "Clear workspace"
  action.
- **Existing calculated-channel timebase validation is completely
  untouched.** `app.domain.calculated_channel.timebases_aligned()` still
  operates purely on `reference_source_id`/native elapsed
  arrays/`start_time` — neither that module nor
  `calculated_channel_service.py` imports anything from this slice's new
  code. Visual alignment never implies (or silently creates) a common
  mathematical sample grid.
- Precision: the offset is stored/transmitted as a `float` number of
  seconds, never rounded to milliseconds; the manual-alignment UI
  displays/accepts milliseconds (the natural unit for disturbance work)
  but converts to/from seconds at exactly one point
  (`wwSyncMsToOffsetSeconds`/`wwSyncOffsetToMsDisplay`).

Reason:

DEC-036's own "synchronization-ready" note (2026-08-19) explicitly
anticipated this: "a future phase can introduce an alignment offset
between source-native bounds and aligned workspace bounds, but no
timestamp alignment... manual offset controls... is implemented by this
decision." This slice is that future phase, deliberately narrow per the
owner's own explicit scope: no automatic `t=0`/trigger/correlation
detection, no clock-drift/timezone correction, no event grouping —
manual, reversible, per-source visual alignment only.

Alternatives considered:

- Store/apply the offset entirely in the backend (shift `time` arrays
  server-side before returning them) — rejected as inconsistent with
  this codebase's own established DEC-042 precedent (Absolute/Elapsed is
  already a frontend-only presentation transform over backend-served
  native data); would also have required threading a new
  workspace-scoped alignment-offset dependency through every one of the
  8 existing `unit_mode`-aware display/measurement endpoints for no
  additional correctness benefit, since the transform is pure
  `+`/`-` arithmetic either way.
- Bake the offset into stored digital-channel data at fetch time (same
  as analog) — rejected: digital data is fetched once, in full, and
  never re-fetched on a viewport change (existing, unrelated
  `extract_digital_waveform` design); baking the offset in at fetch time
  would mean an offset CHANGE for an already-displayed digital channel
  silently would not visually update. Render-time application avoids
  this staleness class entirely, at zero extra fetch cost.
- An explicit reference-source selector control — rejected for this
  slice per the task's own explicit "if not [simple/safe], use the
  smallest deterministic rule" guidance; no reference-selection UI
  infrastructure exists yet, and the first-uploaded-source rule is
  simple, predictable, and matches the task's own worked example.

Impact:

- New backend files: `app/domain/synchronization.py`,
  `app/services/synchronization_registry.py`,
  `app/services/synchronization_service.py`,
  `app/schemas/synchronization.py`, `app/api/v1/synchronization.py`; two
  new error codes (`invalid_alignment_offset`,
  `reference_source_alignment_not_allowed`); a seventh sibling in-memory
  registry wired into `app.main`'s lifespan, `app.api.v1.sources`'s
  source-removal cleanup, and `app.api.v1.workspaces`'s workspace-reset
  cleanup.
- Frontend: a new `ww.alignmentOffsets`/`ww.referenceSourceId` mirror,
  the `wwSourceTimeToWorkspaceTime()`/`wwWorkspaceTimeToSourceTime()`
  conversion helpers, a new "Synchronize Sources" toolbar button/modal
  (`#wwSyncBtn`/`#wwSyncOverlay`), and targeted edits at exactly the
  fetch/render boundaries listed above — no other rendering, layout,
  cursor-mode, or unit-mode code touched.
- **Known, explicitly documented limitation, not silently gapped**:
  Callout/+Peak/-Peak annotation anchoring and the existing
  single-workspace-origin Absolute-time display (DEC-036/DEC-042's own
  prior documented gap) are NOT offset-aware this slice — out of the
  task's own explicit scope (sections 1–10 only); a source carrying a
  non-zero offset can show a misleading annotation anchor or Absolute-
  mode wall-clock label. Documented in-code at the relevant call sites
  (`wwCreateCalloutFromClick`, `wwFormatAbsoluteElapsedTime`) and here;
  fixing this is future work, not part of Slice 1.
- 83 new backend tests (domain/registry/service/API), 16 new frontend
  static-regression tests, zero regressions to the existing 1191-test
  backend suite (1274 total after this slice).

---

## DEC-054 — The Workspace Sidebar becomes source-first: every uploaded source gets its own collapsible hierarchy, replacing the single-source "Active Recording" context; the persistent bottom metadata panel is removed

Date: 2026-08-26
Status: Approved
Source: explicit owner UAT finding after Waveform Time Synchronization
Slice 1 ("the waveform workspace now supports multiple active
recordings, but the left sidebar still visually behaves like a
single-record workspace"), delivered as a dedicated implementation
prompt.

Decision:

**The Workspace Sidebar's Channels area now shows EVERY source
currently uploaded to the workspace at once, each as its own
collapsible section with its own Analog/Digital channel hierarchy —
never merged with another source's channels, never gated behind a
single "selected" source.**

Concretely:

- Hierarchy: `Workspace -> Recording/Source -> Analog/Digital -> Signal
  Category -> Channel`. The old two-section split ("Active Recording"
  read-only identity line + a separate "Channels" panel scoped to
  whichever source was last opened, Phase 3B-UAT8) is replaced by ONE
  section, headed "Recordings (N)" (`N` = live source count), containing
  one `<details class="source-recording">` per source.
  `wwRenderWorkspaceRecordings()` is the new single entry point that
  (re)builds this whole hierarchy; `renderAnalogGroup()`/
  `renderDigitalGroup()`/`renderChannelTable()` and every existing
  channel-row toggle/search mechanism are reused completely unchanged,
  called once per source instead of once total.
- **Data cost**: zero extra requests for the compact per-source summary
  line (`12 analog · 24 digital · 5 kHz · 0.825 s`) — `SourceSummaryOut`
  (the existing `GET .../sources` list response) already carries
  `analog_channel_count`/`digital_channel_count`/`sampling_rates`/
  `duration_seconds`. Each source's own full channel TREE additionally
  needs its existing `GET .../sources/{id}/channels` response (channel
  names/phase/engineering_type/classification aren't on
  `SourceSummaryOut`), fetched once per source in parallel and cached
  (`ww.sourceChannelsData`, `wwEnsureSourceChannelsFetched()`) — a source
  already cached is never re-fetched, since a source's own channel
  metadata is immutable after upload. **No backend change was made or
  needed** — every field this redesign renders was already exposed.
- Sampling rate is formatted compactly (kHz once >= 1000 Hz, e.g. "5
  kHz"; plain Hz below that) from the recording's OWN `sampling_rates`,
  never the nominal grid frequency; a genuinely multi-rate source (more
  than one sampling-rate section) renders "Multi-rate" rather than
  inventing a single misleading value. Duration is formatted to 3
  significant figures (`0.825 s` / `1.30 s` / `12.5 s`) — a NEW,
  sidebar-specific formatter (`wwFormatCompactDuration`); the
  pre-existing Recordings-page duration formatter (fixed 3 decimals) is
  untouched.
- Default expand state (task's own explicit request): the first source
  in the fetched list starts expanded, additional sources start
  collapsed; within each source, Analog Channels defaults open, Digital
  Channels now defaults COLLAPSED (a deliberate change from every
  source's previous both-open default — large digital channel counts,
  e.g. 538, should not dominate the initial view once multiple sources
  can be open at once). A source/group/subgroup's own expand/collapse
  state survives later, unrelated structural rebuilds (another source
  added/removed) via a generic capture/restore pass keyed on each
  `<details>` element's own `data-expand-key`
  (`wwCaptureChannelTreeExpandState()`/`wwRestoreChannelTreeExpandState()`)
  — never silently reset just because the DOM was rebuilt.
- Search (`setupChannelSearch()`) now spans every source's channels at
  once but never flattens ownership: a source with zero matches
  collapses out of the way (same treatment a Voltage/Current sub-group
  with zero matches already got); a source with at least one match
  forces its own section open, with only its matching rows visible
  underneath. Clearing search restores each level's own default state,
  explicitly un-hiding anything a PREVIOUS search had hidden — a real,
  pre-existing gap in the single-source version (clearing search never
  reset a sub-group's own `hidden` flag) fixed as part of extending this
  same logic to the new source level, not left to compound at a second
  level.
- **The persistent bottom-status-bar metadata panel (Station/Sample
  rate/Duration/Displayed channels) is removed outright** — it showed
  one source's own fields in a workspace that can now hold several, and
  duplicated the new inline per-source summary. `shellUpdateStatusBar()`/
  `shellUpdateStatusBarChannelCount()`/`shellSetStatusBarWaveformFieldsVisible()`
  are deleted, not just hidden. The "Workspace" identity field and the
  A/B/Δt cursor readout are untouched. **Underlying metadata is
  unaffected everywhere else** — `SourceSummaryOut`/`TimebaseOut`,
  `ww.sourceChannelsData`/`ww.sourceBounds`/`ww.sourceTiming`, and every
  backend field remain exactly as before; this is a presentation removal
  only.
- **Source participation is no longer gated by a single "selected"
  source.** `selectedSourceId` is retired; a narrower `focusedSourceId`
  remains only as "the source most recently opened via a Recordings
  row," used solely to decide the shared viewport's own reset heuristic
  — never to decide which sources' channels are shown (every uploaded
  source's data is fetched and rendered regardless of focus).
  `wwParticipatingSourceIds()` — previously a bespoke union of the
  selected source plus every source with a currently-displayed channel
  — simplifies to "every key in `ww.sourceBounds`", since every uploaded
  source now has a bounds entry the moment its `/channels` response is
  fetched (task's own explicit "do not reintroduce the single-source
  assumption; all uploaded sources may participate simultaneously").
- **Optional Slice 1 (waveform time synchronization) integration,
  included**: a subtle badge next to each source's name — "Reference"
  for the reference source, `±N.NNN ms` for a non-reference source with
  a non-zero alignment offset, nothing otherwise. Reads
  `ww.alignmentOffsets`/`ww.referenceSourceId`; never mutates
  synchronization state and never touches the Synchronize Sources modal.
  A live-testing finding (not caught by static review): the badge did
  not refresh when an offset changed via the modal, since offset changes
  never rebuild the sidebar tree — fixed with a small, targeted DOM
  patch (`wwRefreshSourceSyncBadges()`, called from
  `wwSyncApplyOffsetChangeSideEffects()`) rather than a full tree
  rebuild, so an offset change never disturbs the engineer's own
  expand/collapse state or an in-progress search.

Reason:

The single-source "Active Recording" model (Phase 3B-UAT8) predates
multi-source waveform display and was a deliberate simplification at the
time ("switching is no longer possible from inside Waveform"). Once
Waveform Time Synchronization Slice 1 made multi-source comparison a
first-class workflow, that simplification became actively misleading —
the sidebar implied only one recording was ever "active" even while two
or more were genuinely participating in the shared viewport. This
decision corrects that without touching Phase 3B-UAT8's own still-valid
product-responsibility split (Recordings = upload/management,
Waveform = analysis) — Recordings still owns Upload/Remove; this redesign
only changes what the Waveform page's OWN sidebar shows once a
recording has been opened into it.

Alternatives considered:

- A dropdown/tab switcher between sources (keep single-source rendering,
  just make switching faster) — rejected: the owner's own target UX
  model (task section 2) explicitly shows every source's hierarchy
  simultaneously, and a switcher would still hide one source's channels
  whenever another was being browsed, the exact problem being fixed.
- Fetching every source's full `/channels` response lazily, only on
  first expand — rejected in favour of eager (parallel, cached-once)
  fetching for every uploaded source: channel search (task's own
  explicit requirement) needs every source's channel list available to
  search across, and `/channels` is metadata-only (no waveform sample
  arrays) so the cost is small even for a large channel count; avoiding
  this kept the implementation simpler with no measured performance
  problem to justify the added complexity of a lazy-fetch/search
  integration.
- Keeping the bottom-status-bar fields but making them multi-source-aware
  (e.g. a per-source dropdown) — rejected per the owner's own explicit
  instruction: "does not carry enough value to justify the complexity of
  making it multi-source aware."

Impact:

- `frontend/index.html` only — no backend file changed (every field this
  redesign needed was already exposed via existing APIs, task section
  18's own "prefer using metadata already exposed" instruction).
- New frontend state: `ww.sourceChannelsData`; `selectedSourceId`
  renamed to the narrower `focusedSourceId`.
- New frontend functions: `wwRenderWorkspaceRecordings()`,
  `wwEnsureSourceChannelsFetched()`, `wwRenderSourceRecordingHtml()`,
  `wwFormatSourceSummaryLine()`, `wwFormatCompactSamplingRate()`,
  `wwFormatCompactDuration()`, `wwSourceSyncBadgeHtml()`,
  `wwRefreshSourceSyncBadges()`,
  `wwCaptureChannelTreeExpandState()`/`wwRestoreChannelTreeExpandState()`,
  `wwResetWorkspaceRecordingsPanel()`. Removed:
  `renderActiveRecording()`, `shellUpdateStatusBar()`,
  `shellUpdateStatusBarChannelCount()`,
  `shellSetStatusBarWaveformFieldsVisible()`.
- **Existing channel-selection/plotting/digital/synchronization/removal/
  reset workflows are unchanged in mechanism** — verified both by 19 new
  static-regression tests and by live-browser verification (Playwright,
  real running app + real backend): two sources uploaded and opened
  together, each with its own correctly-scoped hierarchy; search
  spanning both with ownership preserved and correctly restored on
  clear; one channel from each source toggled and plotted together on
  the same shared viewport; the Synchronize Sources modal opened,
  offset applied, sidebar badge updated live; one source removed
  (`Recordings (2)` → `Recordings (1)`, cleanly); Start New Workspace
  clearing all source/hierarchy state. Zero console errors across this
  realistic click path.
- **Known, explicitly deferred, not silently gapped**: the optional
  source-details popover (task section 14, an info icon exposing
  start/trigger timestamp, COMTRADE revision, detailed sampling-rate
  sections) was not built — the task's own explicit instruction was that
  the inline summary is mandatory and the popover is secondary, not to
  let it delay or complicate the core redesign.

---

## DEC-055 — Waveform time synchronization Slice 2: an explicit, workspace-wide common event `t=0`, reusing Cursor A as the origin picker, independent of and never absorbing per-source alignment offsets

Date: 2026-08-26
Status: Approved
Source: explicit project-owner instruction, delivered as a dedicated
"Slice 2 of waveform time synchronization" implementation prompt,
immediately following DEC-053 (Slice 1).

Decision:

**An engineer can, after manually synchronizing sources (DEC-053), select
one workspace-time instant as a common event origin `t=0`. Every
already-synchronized source's waveform then displays with event-relative
time (negative before the event, `0` at the event, positive after) —
without altering any source's own data, without altering any source's
own alignment offset, and without being reset by "Reset All" alignment
offsets.**

Concretely:

- Core mapping: `event_time = workspace_time - t0_workspace_time`
  (inverse: `workspace_time = event_time + t0_workspace_time`),
  composed with DEC-053's own mapping into
  `event_time = source_time + alignment_offset_s - t0_workspace_time`.
  Implemented as two new pure functions in
  `app/domain/synchronization.py` —
  `workspace_time_to_event_time()`/`event_time_to_workspace_time()` —
  deliberately never a third, separately-coded flat formula; every real
  caller composes them from DEC-053's existing
  `source_time_to_workspace_time()`/`workspace_time_to_source_time()`
  pair.
- **`t=0` is ONE workspace-wide value, never per-source.** A second,
  genuinely independent store (`SynchronizationRegistry._t0`, a plain
  `dict[workspace_id, float]`, alongside DEC-053's existing `_offsets`
  dict in the same registry) backs three new endpoints under the same
  `.../synchronization` router: `GET/PUT/DELETE .../synchronization/t0`.
  Validated with the same finite-number rule DEC-053's offset validator
  already enforces (`alignment_offset_valid()`, reused rather than
  duplicated), under a distinct error code (`invalid_t0`) so a client
  can tell the two failures apart.
- **UI reuses the existing A/B measurement cursor rather than inventing
  a new interaction**: a single toolbar button (`#wwSetT0Btn`, "Set
  Cursor A as t=0" / "Clear t=0", dual-purpose like `#wwCursorModeBtn`)
  promotes Cursor A's current workspace-time position to `t0`. The
  button is `disabled` — never silently uses an arbitrary time —
  whenever there is nothing valid to act on: no already-selected `t0`
  to clear, and no currently-placed Cursor A to promote. Once set, the
  value is surfaced via the button's own title/aria-label and a compact
  bottom-status-bar item (`#statusBarT0`, hidden entirely while unset)
  — no separate always-visible toolbar label.
- **Single choke-point propagation, zero scattered arithmetic**: the
  existing `wwElapsedToPlotlyX()`/`wwPlotlyXToElapsed()` functions (the
  one existing bridge between internal workspace-time coordinates and
  every Plotly-facing X value — traces, axis ranges, ruler, digital
  chart, calculated channels) now delegate to the two new conversion
  helpers above. Both are documented no-op passthroughs when no `t0` is
  selected, so this required zero conditional branching at any of their
  existing call sites. The cursor-overlay/annotation-anchor positioning
  system is a wholly separate, fraction-based coordinate system
  (`(time - viewport.start) / (viewport.end - viewport.start)`),
  mathematically invariant under a constant `t0` shift — confirmed by
  inspection to need no code changes, including the A/B cursor Δt
  readout (a subtraction, so it cancels the shift by construction).
- **Backend source-native queries always receive workspace time, never
  event time.** `wwFetchCursorValuesForSource()`'s existing DEC-053
  inverse-mapping call sites needed zero Slice 2 changes: `Cursor A`/`B`
  positions live in `ww.measurementCursors` as workspace time (the same
  coordinate system as `ww.viewport`), the same coordinate `t0` itself
  is defined in — event time is a display-only presentation layer over
  that.
- **Independence is structural, not merely tested.** `t0` and per-source
  alignment offsets are separate dict stores in the same registry;
  `remove_workspace()` (used by "Reset All") touches only `_offsets`,
  never `_t0`. A combined `remove_workspace_synchronization_state()`
  service function (renamed from DEC-053's
  `remove_workspace_alignment()`) explicitly calls both
  `registry.remove_workspace()` and the new `registry.clear_t0()` for
  full workspace teardown (workspace delete/"Start New Workspace" only).
  Removing a source (including whichever source's cursor originally
  helped select `t0`) never touches `t0` — once defined, `t0` is a pure
  workspace-time coordinate, independent of which source (if any)
  contributed the cursor position that selected it.
- **Digital channels, RMS/derived channels, and calculated-channel
  mathematical-timebase validation are unaffected in substance.**
  Digital transitions move through the same render-time
  `wwElapsedToPlotlyX()` DEC-053 already applies them through — no
  interpolation, exact transitions preserved. RMS/other source-native
  derived calculations remain entirely in source-native time; only the
  display X coordinate becomes event-relative.
  `app.domain.calculated_channel.timebases_aligned()` is untouched —
  visual synchronization plus a common `t=0` still does not imply (or
  create) a common mathematical sample grid.
- **Absolute-time-mode interaction, deliberately minimal**: when `t0` is
  defined, event-relative display takes precedence over Absolute mode's
  wall-clock labels/hover/customdata (`wwTimeAxisTickFormat()`,
  `wwTraceCustomData()`/`wwTraceHoverTemplate()`, the sticky ruler all
  gained a `&& !wwHasT0()` guard on their existing absolute-mode
  branches) — the smallest safe behavior given DEC-053's own
  already-documented multi-source Absolute-time limitation, which this
  slice does not attempt to solve.
- Precision: `t0_workspace_time` is stored/transmitted as a `float`
  number of seconds with sub-millisecond precision, never rounded
  internally; the status-bar/button display formats to milliseconds for
  readability only, the same single-conversion-point pattern DEC-053
  established for the offset value.
- Performance: applying/clearing `t0` re-projects each already-displayed
  channel's existing, unmodified `channel.time` array through
  `wwElapsedToPlotlyX()` via `Plotly.restyle()` — no re-fetch, no
  duplicate arrays, no backend reprocessing (`wwApplyT0ToDisplay()`,
  mirroring `wwSetTimeMode()`'s own established presentation-only
  pattern).

Reason:

DEC-053 was deliberately scoped to per-source visual alignment only,
with a common event origin named as later, separate work. This slice is
that follow-up, kept to the owner's own explicit scope: no automatic
`t=0`/trigger/threshold/fault-inception detection, no
correlation/cross-correlation, no clock-drift/timezone correction, no
event grouping/classification, no resampling, no drag-to-align, no
reference-source redesign — a single, manually-selected, workspace-wide
coordinate shift over already-synchronized display data, reusing
existing infrastructure (Cursor A, the DEC-036/DEC-053
`wwElapsedToPlotlyX()` choke-point, the DEC-053 `SynchronizationRegistry`
shape) end to end.

Alternatives considered:

- A new, dedicated origin-picking interaction (a click-to-place marker
  distinct from the A/B cursors) — rejected per the task's own explicit
  "reuse the existing waveform cursor rather than inventing a new
  interaction" instruction; Cursor A already carries exactly the
  workspace-time-position semantics `t0` needs, and introducing a
  second selection mechanism would be pure UI surface for no additional
  capability.
- Absorbing `t0` into each source's own alignment offset (shifting the
  stored offset itself so the origin lands at zero) — rejected: this
  would conflate two independent concepts the task explicitly requires
  to stay separate (visual pairwise alignment vs. a single shared event
  origin), and would make "Reset All" alignment offsets silently move
  or destroy the event origin, which section 14 of the task explicitly
  forbids.
- Clearing `t0` whenever a source is removed (in case that source's
  cursor originally helped select it) — rejected per the task's own
  explicit section 15 guidance: once defined, `t0` is a pure
  workspace-time coordinate no longer tied to any particular source's
  continued presence, mirroring how `ww.alignmentOffsets` for a
  *different, still-present* source is already unaffected by an
  unrelated source's removal.

Impact:

- Backend: two new pure functions in `app/domain/synchronization.py`; a
  second independent store (`_t0`) and three new methods
  (`get_t0`/`set_t0`/`clear_t0`) in `SynchronizationRegistry`; a new
  `T0View` dataclass and `get_t0()`/`set_t0()`/`clear_t0()` in
  `synchronization_service.py`;
  `remove_workspace_alignment()` renamed to
  `remove_workspace_synchronization_state()` (now clears both stores);
  a new `InvalidT0Error` (code `invalid_t0`); `T0UpdateRequest`/`T0Out`
  schemas; three new REST endpoints. 54 new domain/registry/service/API
  tests plus 13 new frontend-static-regression tests (67 total), zero
  regressions (1294 → 1361 backend tests, the intermediate 1348 figure
  being backend-only before this session's frontend work landed).
- Frontend: `ww.t0WorkspaceTime` mirror; `wwT0WorkspaceTime()`/
  `wwHasT0()`/`wwWorkspaceTimeToEventTime()`/
  `wwEventTimeToWorkspaceTime()` helpers; `wwFetchAlignmentOffsetsForWorkspace()`
  renamed to `wwFetchSynchronizationStateForWorkspace()` (now fetches
  `.../t0` alongside `.../sources` in parallel); the new
  `#wwSetT0Btn`/`#statusBarT0` UI and its `wwSetT0FromCursorA()`/
  `wwClearT0()`/`wwSyncT0Controls()`/`wwApplyT0ToDisplay()` functions;
  `t0WorkspaceTime` cleared in `wwClearWorkspace()`'s "Start New
  Workspace" branch only (same lifecycle policy DEC-053 already
  established for `ww.alignmentOffsets`/`ww.referenceSourceId`), never
  by plain "Clear workspace".
- Live browser UAT (Playwright, backend + static frontend server):
  two-source upload, Source B alignment offset set to 401 ms, Cursor A
  placed via the existing A/B toggle, `t0` set from it, X-axis
  confirmed switching to `-0.00325…0.0065` s straddling `0` with title
  "Event Time (s)", cursor readout confirmed showing signed event time
  (`A +0.000 ms`, `B +3.250 ms`, `Δt 3.250 ms` — Δt unchanged from
  workspace-time as expected), box-zoom confirmed staying event-relative
  after a viewport change, Source B's offset fine-adjusted to 405 ms
  while `t0` stayed fixed, `t0` cleared (offset confirmed unchanged),
  `t0` set again, "Reset All" alignment offsets confirmed leaving `t0`
  unchanged (the core independence regression), "Start New Workspace"
  confirmed clearing `t0`. Zero console errors observed throughout.
- **Known, explicitly documented limitation, not silently gapped**: the
  Callout/+Peak/-Peak annotation-anchor offset-awareness gap DEC-053
  already documented is unchanged by this slice (out of scope); the
  existing multi-source Absolute-time-mode limitation is not solved
  here either — this slice only ensures event-relative display cleanly
  takes precedence over it when `t0` is active, per the task's own
  "smallest safe behavior" instruction.

---

## DEC-056 — Waveform time synchronization Slice 3: assisted event-origin detection is advisory-only, operates on one engineer-selected analog channel's sustained RMS change, and only ever proposes a candidate through Slice 2's existing t0 mechanism on explicit acceptance

Date: 2026-08-27
Status: Approved
Source: explicit project-owner instruction, delivered as a dedicated
"Slice 3 — Assisted Event `t=0` Detection" implementation prompt,
immediately following DEC-055 (Slice 2).

Decision:

**Powerwave may analyse one engineer-selected analog channel and
propose a likely disturbance-onset time as a candidate `t=0` — it never
sets `t=0` itself. The engineer previews the suggestion on the waveform
and explicitly Accepts or Rejects it; a clean "no clear event" result is
a valid, expected outcome, never a manufactured candidate.**

Concretely:

- **Detector**: a change-based RMS detector
  (`app/domain/event_detection.detect_event_onset()`), NOT an
  instantaneous-sample threshold (task section 3's own explicit
  anti-pattern — a raw AC sample crosses zero every cycle and is
  meaningless as a trigger condition). Reuses
  `app.domain.calculated_channel.evaluate_rms()` VERBATIM — the same
  trailing one-cycle true-RMS engine DEC-048's RMS calculated channel
  already uses, already proven correct for both uniform and genuinely
  irregular/multi-rate `time` arrays — so no separate multi-rate
  special-casing was needed (task section 20). Pipeline: establish a
  pre-event RMS baseline from the record's own leading portion (at
  least `MIN_BASELINE_CYCLES` cycles, or the first 25% of the record's
  duration, whichever is larger — the same "first ~25%" fallback rule
  `powerwave`'s own `event_detector.py` already uses when no trigger
  hint narrows things); compare every later RMS sample against that
  baseline as a RATIO (never an absolute/hard-coded value — task
  section 21); require the ratio to stay past a sensitivity-selected
  trigger band for a minimum SUSTAINED duration (persistence is
  duration-based in seconds, never a fixed sample count, so results are
  comparable across native sampling rates) before accepting it as a
  candidate; report the FIRST such sustained onset, or "no clear
  event."
- **Three plain sensitivity tiers** (Conservative/Normal/Sensitive),
  never raw tunable parameters (sigma/window_samples/derivative
  threshold) exposed to the engineer (task section 8). Normal reuses
  `powerwave`'s own validated dip/swell thresholds (0.90/1.10 ratio)
  verbatim as a starting point, not a fresh guess.
- **Quality is a fixed, sensitivity-independent qualitative label**
  (Strong/Moderate/Weak, keyed on the sustained segment's own peak
  `|ratio - 1.0|`) — never a fabricated numeric confidence (task
  section 11).
- **Engineer explicitly selects source AND channel** (task section 5) —
  never an automatic best-channel choice across a source's full channel
  list. Real source analog channels only this slice — no digital-event
  detection, no calculated-channel analysis (task sections 22/30).
- **Advisory only, structurally enforced, not merely by convention**:
  `POST .../synchronization/detect-event` (backend) and the "Detect
  Event Origin" modal (frontend) are both READ-ONLY — neither ever
  calls `set_t0()`/`PUT .../t0` itself. The candidate is composed into
  WORKSPACE time via the EXISTING `source_time_to_workspace_time()`
  (Slice 1, respecting whatever alignment offset is currently set —
  task section 17) and previewed as a distinct dashed marker on the
  waveform (reusing the existing A/B cursor overlay's own pixel-
  projection authority, `wwCursorTimeToPixelX()`, never a second
  X-projection — task section 18) BEFORE acceptance is even possible.
  Acceptance is a SEPARATE, explicit "Set as t=0" action that calls
  Slice 2's existing, completely unmodified `PUT .../synchronization/t0`
  — no second t0 implementation exists anywhere (task section 14).
  Accepting while a t0 already exists requires an explicit inline
  "Replace t=0" confirmation (task section 16) — never silently
  replaced. Rejecting/closing the modal clears only the temporary
  suggestion; `t0` and every source's own alignment offset are
  untouched (task section 15).
- **`No clear disturbance onset detected. Use Cursor A to set t=0
  manually.`** is a first-class, expected response — verified for a
  clean sinusoid, a single-sample spike, and steady/noisy channels
  (task sections 9/28/33): none of these fabricate a candidate.
- **`evaluate_rms()`'s own already-approved DEC-048 correctness for
  irregular/multi-rate `time` arrays is inherited, not re-proven from
  scratch** — no artificial "multi-rate unsupported" rejection was
  added, since doing so would not reflect the detector's actual
  capability (verified directly: a synthetic two-sampling-rate-section
  record detects correctly, see test_event_detection_domain.py's own
  `TestMultiRateSpacing`).
- Source data, source alignment offsets, and Slice 1/2's own
  architecture are completely untouched — this slice reads
  `active.record.waveform_data` (never mutates it, matching every other
  read-only analysis endpoint) and reads (never writes) the current
  alignment offset only to compose the response.

Reason:

DEC-055 (Slice 2) established manual event-origin selection via Cursor
A; the owner's own next-step framing was explicit that assisted
detection must remain a suggestion an engineer reviews and decides on,
never an automatic decision — "Powerwave may say 'this looks like the
likely disturbance inception.' It must never silently say 'this is
definitely the disturbance inception.'" The existing desktop
`powerwave` reference contains TWO detectors
(`app/analytics/events/event_detector.py`,
`app/sessions/alignment_engine.detect_trigger_time`); only the first's
ENGINEERING CONCEPTS (RMS-segment ratio-vs-baseline, sustained-duration
filtering) were reused — the second thresholds raw instantaneous
samples, exactly the anti-pattern task section 3 forbids, and was
deliberately not used as a reference for that reason (documented in
`app/domain/event_detection.py`'s own module docstring).

Alternatives considered:

- A MAD/z-score-based statistical deviation metric instead of a plain
  ratio-vs-baseline — considered during design, rejected in favor of
  the simpler ratio approach once `powerwave`'s own already-validated
  event_detector.py thresholds were found: a ratio (e.g. "40% of
  baseline") is directly interpretable by an engineer in the
  transparency panel (task section 27's own worked example), where a
  z-score/MAD multiple is not, and the ratio approach still satisfies
  every "statistically meaningful, not an absolute threshold"
  requirement (task section 3/6) by construction.
- Analysing only the frontend's current visible viewport by default
  (task section 24's other suggested option) — rejected for this slice
  in favor of full-record analysis: typical COMTRADE event captures are
  short, a full-record search is simpler, and the engineer already
  narrows scope by explicitly choosing which channel to analyse (task
  section 5). Optional `search_start_time`/`search_end_time`
  parameters exist at the domain/service/API layer for future use, but
  the frontend does not expose range-selection controls this slice
  (task section 8's own "avoid a large configuration form" guidance) —
  a documented, deliberate scope trim, not an oversight.
- A single combined Source+Channel grouped `<select>` (mirroring the
  Calculated Channels Signal Builder's own existing input picker) —
  considered, but two dependent selects (Source, then Channel) were
  used instead, matching the task's own explicit section 12 mockup more
  literally while still reusing the same underlying
  `ww.sourceChannelInventory` data the Signal Builder's picker already
  populates from.

Impact:

- New backend files: `app/domain/event_detection.py` (pure detector),
  `app/schemas/event_detection.py`; one new function
  (`detect_event_candidate()`) and one new dataclass (`DetectEventView`)
  in `app/services/synchronization_service.py`; one new error
  (`InvalidDetectionSensitivityError`, code `invalid_sensitivity`); one
  new endpoint, `POST .../synchronization/detect-event`. 43 new backend
  tests (22 domain + 13 service + 8 API) + 14 new frontend
  static-regression tests (57 total), zero regressions (1361 → 1418
  backend tests total).
- Frontend: `ww.suggestedEvent` state; the "Detect Event Origin" modal
  (`#wwDetectEventOverlay`) and its `wwOpenDetectEventModal()`/
  `wwHandleDetectEventAnalyseClick()`/`wwAcceptDetectedEvent()`/
  `wwHandleDetectEventAcceptClick()`/`wwCloseDetectEventModal()`
  functions; a third "Suggested event" marker added to the existing A/B
  cursor overlay system (`wwUpdateCursorOverlay()`, `wwEnsureCursorDom()`
  — dashed, `var(--warn)`-colored, no drag/close interaction of its
  own); the overlay's own drawing gate widened from "cursor mode
  active" to "cursor mode active OR a visible suggestion," so the
  marker can show even with A/B cursor mode off; `ww.suggestedEvent`
  cleared by "Start New Workspace" (same lifecycle policy as
  `ww.t0WorkspaceTime`/`ww.alignmentOffsets`), never by plain "Clear
  workspace."
- Live browser UAT (Playwright, backend + static frontend server, a
  purpose-built synthetic COMTRADE fixture with a genuine sustained
  50%-RMS voltage dip on one channel and a steady second channel):
  18/18 checks passed across the full accept/reject/re-run/replace
  flow — marker previewed before acceptance, Cancel leaves `t0`/offsets
  untouched, Accept correctly activates the event-relative axis
  (screenshot confirmed X-axis spanning `-1…+1` s with `0` exactly at
  the visible amplitude-drop boundary), Clear t=0 leaves the source's
  own alignment offset unchanged, the steady channel correctly returned
  "No clear disturbance onset detected" with "Set as t=0" disabled.
  Zero console errors.
- **Known, explicitly deferred, not silently gapped** (task section 32's
  own non-goals list): no automatic application of `t0`, no automatic
  source alignment, no cross-source correlation, no multi-channel
  voting/automatic best-channel selection, no digital-event detection,
  no clock/timezone/drift correction, no event grouping/classification,
  no machine learning, no resampling. The frontend does not yet expose
  the optional search-range narrowing the backend already supports —
  candidate future UX refinement, not required for this slice.

**Update (2026-08-27, same-day owner UAT refinement — no new decision
entry)**: owner UAT found the modal's original two-step accept flow
confusing — clicking "Set as t=0" while a `t0` already existed hid the
main footer and revealed a SECOND panel with its own "Replace t=0"
button and its own "Cancel" button, so a screenshot mid-flow could show
both accept actions and two Cancel buttons at once. **The Detect Event
modal now exposes exactly one state-appropriate acceptance action —
"Set as t=0" when no event origin exists, "Replace t=0" when one
already does — and exactly one Cancel, decided by
`wwSyncDetectEventAcceptButtonState()` from the CURRENT `wwHasT0()`
state alone, never a second click-to-reveal panel.** The separate
`#wwDetectEventReplaceConfirm` sub-panel (and its own footer/Cancel/
Replace buttons) was removed outright; the "A t=0 is already defined"
explanatory text became inline context (`#wwDetectEventReplaceHint`,
shown only alongside an active, acceptable candidate) rather than a
second footer. Both button states click straight into the SAME
`wwAcceptDetectedEvent()` — still the one unmodified Slice 2 `PUT
.../synchronization/t0` call; no replacement-specific API or logic was
added. A related, same-pass fix: selecting a different source, channel,
or sensitivity after a candidate was already found now invalidates that
stale candidate (`wwInvalidateDetectEventSuggestion()`) so the accept
button can never stay enabled for a selection that was never actually
analysed. Verified by 9 new static-regression tests plus a dedicated
live-browser UAT (9/9 checks passed, zero console errors): the no-t0
case showed only "Set as t=0"; accepting, reopening, and detecting a
second, later event on a different channel showed only "Replace t=0"
plus the inline hint; Cancel left `t0` unchanged; accepting the replace
action moved `t0` from the first candidate to the second, confirmed
numerically and via the event-relative axis re-rendering correctly.
Zero detection/timing/backend logic touched — `backend/` has no diff
for this fix. See [HANDOFF.md](HANDOFF.md) for the full record.

**Update (2026-08-27, same-day owner UAT correction — no new decision
entry)**: owner UAT with real disturbance recordings found that a
**full-record search is insufficient when a recording contains more
than one genuine disturbance** — the detector correctly returns the
FIRST sustained qualifying RMS change, but that is not always the
event the engineer is actually analysing, and the owner confirmed
across all three sensitivity tiers that this is a search-SCOPE problem,
not a threshold-tuning problem. **Event detection now supports
viewport-bounded analysis. "Current visible range" is the preferred/
default search scope; "Full recording" remains available explicitly**
via a compact two-row picker in the Detect Event modal (reusing the
Per-Unit Current Base picker's own existing stacked-radio-row pattern
verbatim — no new UI primitive, no numeric start/end time form). The
engineer already indicates the event of interest by zooming/panning
the waveform; this reuses that existing interaction rather than adding
one.

- **Backend required zero changes.** `POST .../synchronization/detect-event`'s
  existing optional `search_start_time`/`search_end_time` (source-native
  seconds, boundary-inclusive `np.searchsorted` clip) were already
  fully correct — confirmed by 6 new backend tests exercising exactly
  this owner scenario (a synthetic two-genuine-event record: full
  recording selects the earlier event; a range restricted around the
  later event selects that one instead, with the earlier event entirely
  excluded), plus source-bound clipping (a range extending past the
  source's own native coverage clips safely, never rejected), a
  too-short range, and an insufficient-baseline range — all already
  produced clear, honest `found=false` results with no code change
  needed. `backend/app/` has zero diff for this correction; only new
  tests were added.
- **Time mapping reuses existing helpers only, per the task's own "do
  not duplicate hardcoded formulas" instruction.** `ww.viewport` was
  already documented (and confirmed by inspection) to stay in
  WORKSPACE time at all times — every Plotly relayout handler already
  routes the raw range through `wwPlotlyXToElapsed()` (Slice 2's own
  event-time-to-workspace-time inverse) before ever storing it, so no
  event-relative-to-workspace conversion step was needed in this
  correction at all. The ONLY conversion required is Slice 1's own
  `wwWorkspaceTimeToSourceTime(sourceId, workspaceTime)`, applied to
  `ww.viewport.start`/`.end` — the same helper every other
  source-native request in this app already uses.
- **No silent fallback (mandatory).** If "Current visible range" cannot
  produce a usable request (no viewport currently exists) or the
  detector itself rejects the resulting slice (too short, insufficient
  baseline, no clear event), the engineer sees a clear message and
  "Set as t=0"/"Replace t=0" stays disabled — the frontend never
  retries the same request against the full record.
- **Viewport captured at Analyse-click time, not modal-open time**
  (task section 7) — the conversion runs inside the Analyse handler
  itself, reading `ww.viewport` fresh at that moment; confirmed
  `wwOpenDetectEventModal()` never reads it at all.
- **Sensitivity/RMS/persistence/quality logic is completely
  unchanged** — this correction is entirely about selecting the correct
  search REGION, never about re-tuning what counts as a qualifying
  disturbance within it (task section 13).
- The result panel gained one line, "Search range: …", reusing the SAME
  `wwFormatCursorPointTime()` formatter every other time readout in this
  app already uses (so it stays consistent with whatever Elapsed/
  Absolute/event-relative display mode is currently active — confirmed
  in the live UAT with an active `t0`, where the line correctly showed
  signed event-relative bounds).
- Verified by 6 new backend tests (multi-event regression, source-bound
  clipping, too-short range, insufficient baseline) + 11 new frontend
  static-regression tests, plus a dedicated live-browser UAT reproducing
  the owner's own scenario end to end (14/14 checks passed, zero console
  errors): full recording found the earlier event; zooming to the later
  event and reopening Detect Event defaulted to "Current visible range"
  and found the later event, excluding the earlier one entirely, across
  Conservative/Normal/Sensitive; a too-tight zoom produced a clear "no
  clear event"/insufficient-range message with no fallback; behaviour
  was confirmed correct with an active alignment offset and with an
  active `t0` (Replace t=0 moved the origin correctly, search range
  shown in event-relative time). Full backend suite: 1444 passed, zero
  regressions.
- **Deferred, not silently gapped**: multi-event candidate lists,
  automatic event ranking, an event chooser UI, and any other
  multi-candidate workflow remain out of scope for this correction (task
  section 22) — one visible-range search still returns exactly one
  candidate (or none), the same shape as before.

---

## DEC-057 — Timestamp-Based Initial Alignment and Time Groups: COMTRADE sources now place themselves automatically from their own recorded start timestamps, and a waveform panel only ever mixes sources that share a defensible time relationship

Date: 2026-08-28
Status: Approved
Source: explicit project-owner instruction, delivered as a dedicated
"Timestamp-Based Initial Alignment and Time Groups" implementation
prompt, immediately following DEC-056 (Slice 3).

Decision:

**Powerwave must never imply that two sources share one physical time
axis unless it has a defensible reason to do so.** Two COMTRADE sources
with different recorded absolute start timestamps (e.g.
A=13:09:44.000, B=13:09:44.401) now place themselves automatically —
B shifted +401ms relative to A — with **zero manual synchronization
action required**, instead of both silently plotting from their own
elapsed 0 as before. A new **Time Group** concept determines which
sources may ever share one waveform panel; existing manual
synchronization (DEC-053) and the explicit common-event `t0`
(DEC-055/DEC-056) both continue to work exactly as before for the
common single-group case, now scoped per Time Group rather than
per-workspace.

Concretely:

- **Alignment is now three composed parts, computed at read time,
  never stored combined**: `effective_alignment_offset_s =
  timestamp_placement_offset_s (derived from recorded start
  timestamps) + manual_alignment_offset_s (DEC-053's existing engineer
  correction, unchanged semantics)`. `SourceMetadata.timing_reference`
  ("absolute"/"relative_elapsed") — originally dead scaffolding for a
  future CSV importer, always "absolute" by COMTRADE construction — was
  reused directly as the time-reference-type signal (task section 7);
  no new field was needed.
- **Time Groups are derived by recorded-absolute INTERVAL OVERLAP**
  (`app/domain/time_grouping.py`: connected components over an
  overlap graph via union-find), never by mere start-time proximity —
  correctly handles a transitive chain (A-B overlap, B-C overlap, A-C
  don't touch directly) as one group. Two long overlapping records
  with a large start-time difference still share a group; two short,
  near-but-non-overlapping records stay separate by default
  (conservative rule — overlap required, not merely "close enough"). A
  large non-overlapping gap gets a neutral note ("Large timestamp
  separation / no temporal overlap...") rather than a hardcoded
  "difference > N seconds = different event" threshold. A group's own
  `group_id` is its own origin source's `source_id` — recomputed fresh
  from the current source set on every call, never cached/persisted
  (the same "recomputed fresh" precedent DEC-053's own reference-source
  rule already established, now per-group instead of per-workspace).
- **Elapsed-only sources are never assumed to share elapsed-0 with
  anything else** — a source whose `timing_reference != "absolute"`
  defaults to its own solo, unaligned time group, even when several
  elapsed-only sources are uploaded together (each still gets its own
  separate group, not auto-merged just because they all start at 0).
- **Sampling rate never blocks grouping** — verified directly (10 kHz
  and 5 kHz sources share one group; native sample arrays untouched,
  zero resampling anywhere in this feature, consistent with "time
  synchronization ≠ resampling").
- **`t0` is now scoped per Time Group, not workspace-wide** — the
  `SynchronizationRegistry`'s `_t0` store re-keyed from
  `dict[workspace_id, float]` to `dict[(workspace_id,
  time_group_key), float]`. Setting `t0` in one group never touches an
  unrelated group's own `t0` (verified at the service layer and live in
  the browser). Detect Event's own explicit source+channel selection
  (DEC-056) always resolves the CORRECT group regardless of how many
  groups exist in the workspace, unchanged. The shared toolbar's "Set
  Cursor A as t=0" quick action has no explicit source context of its
  own, so it targets one deterministic "primary" source instead (the
  first key in the frontend's own `ww.alignmentOffsets` map) — a
  documented, narrower scope for that ONE shortcut specifically, not a
  gap in Detect Event's own group-correctness.
- **Reset semantics changed in a way that required relabeling** (task's
  own "if labels become misleading, change them minimally"): "Reset
  source"/"Reset All" now return a source to its TIMESTAMP-DERIVED
  position, never to absolute zero. The buttons were relabeled "Reset
  manual adjustment" / "Reset All Manual Adjustments" with explanatory
  tooltips — verified live (Reset returns the manual field to 0 while
  the 401ms timestamp-placement note visibly survives).
- **Grouped-mode panel keys are prefixed with the channel's own current
  time-group id** (`wwPanelGroupKeyFor()`), so two channels of the same
  engineering type from different, unrelated time groups can never
  land on one panel (task section 1/27/34's own "one panel = one
  coherent time domain") — verified live: two overlapping absolute
  sources 401ms apart at different sampling rates rendered on ONE
  shared panel (2 traces); a third, genuinely non-overlapping source
  ~60 seconds away rendered on its OWN separate panel, each keeping its
  own tight x-range (never one giant panel stretched across the gap).
  Separate/Custom layout modes are deliberately untouched — Separate
  already gives every channel its own panel, and Custom is the
  engineer's own explicit grouping choice. A compact "— Time Group N" /
  "— Elapsed / unaligned" panel-label suffix appears ONLY once a
  workspace genuinely has more than one group — the overwhelming
  single-group common case renders identically to before this feature
  existed.
- **Analog and digital channels from one source always share that
  source's own time group** (task section 34) — group membership is
  resolved through the SAME grounding-source lookup
  (`wwTimingSourceIdForDisplaySourceId()`) the alignment-offset
  resolution already used, never a second, per-channel rule.

Reason:

DEC-053 (Slice 1)/DEC-055 (Slice 2)/DEC-056 (Slice 3) all built
correctly on top of an assumption the owner's own next-step framing
identified as no longer safe once multiple independently-timed sources
are involved: that every uploaded source's elapsed-0 origin is a
meaningful, comparable instant across sources. It usually is not — two
COMTRADE files recorded by different relays for the same disturbance
routinely have different recording-start timestamps even though both
happen to start their own elapsed clock at 0. The owner's own governing
principle: "Recorded timestamps may provide [a defensible time
relationship]. Elapsed time alone usually does not."

Alternatives considered:

- Grouping by mere start-timestamp PROXIMITY (e.g. "within 60 seconds
  of each other") instead of actual interval OVERLAP — explicitly
  rejected by the task's own instructions (section 10-13): a long
  overlapping record with a large start-time difference must still
  group with its overlap partner, and a short, near-but-not-overlapping
  record must NOT group with a neighbor it never actually shares time
  with. Overlap is the only rule that gets both cases right without
  inventing a synchronization claim the recorded data doesn't support.
- A new dedicated field for the time-reference-type distinction —
  rejected once `SourceMetadata.timing_reference` was found already
  populated (always "absolute" for COMTRADE) and semantically exactly
  right; adding a second field would have meant keeping two sources of
  truth in sync for no benefit.
- Fully independent per-time-group viewports/zoom/pan/cursor state (a
  much larger rearchitecture of `ww.viewport`, the cursor overlay, the
  sticky ruler, and the digital chart to all become group-scoped) —
  considered, deliberately scoped OUT of this pass. The task's own
  instructions explicitly authorize progressive implementation and list
  automatic event-based cross-group merging as an explicit non-goal;
  panel SPLITTING (rendering incompatible groups on separate panels
  sharing the app's existing single physical viewport) delivers the
  core "one panel = one coherent time domain" requirement without that
  larger rearchitecture, and remains a defensible, documented
  narrower-scope engineering trade-off rather than a silent gap.
- Retroactively fixing `wwWorkspaceRecordingStartMs()`'s pre-existing
  single-workspace-wide Absolute-mode origin (task section 31's other
  half) in this same pass — considered, deliberately deferred. This gap
  predates this phase (documented since DEC-053/DEC-055 as a known
  limitation for the "multiple sources with different recording starts
  displayed together" case) and fixing it correctly requires threading
  a source/channel context through every Absolute-label call site in
  the app, not merely the panel-splitting work this phase actually
  needed; it never fabricates a false wall-clock label for an
  elapsed-only source (structurally excluded already via
  `wwTimeModesForChannel()`), so the higher-risk half of task section
  31 ("do not display false wall-clock timestamps for elapsed-only
  sources") is already satisfied. Left open and explicitly documented
  rather than attempted under time pressure in the same pass as the
  rest of this feature.

Impact:

- New backend file: `app/domain/time_grouping.py` (pure derivation
  logic — `TimeGroup`, `derive_time_groups()`,
  `timestamp_placement_offset_s()`, `time_reference_type_for_source()`)
  plus its own extensive docstrings documenting the full time
  architecture. New tests: `test_time_grouping_domain.py` (17),
  `test_time_grouping_service.py` (8), `test_time_groups_api.py` (3).
- Rewritten: `synchronization_registry.py` (`_t0` re-keyed per time
  group, new `clear_all_t0_for_workspace()`),
  `synchronization_service.py` (`list_time_groups()`,
  `SourceAlignmentView`/`T0View` now group-aware, reference-lock now
  checks against the group's own origin), `schemas/synchronization.py`
  (`SourceAlignmentOut` gained `time_group_id`/
  `timestamp_placement_offset_s`/`manual_alignment_offset_s`; new
  `TimeGroupOut`), `api/v1/synchronization.py` (t0 endpoints now take
  `source_id`; new `GET .../time-groups`) — plus every pre-existing
  Slice 1/2/3 synchronization test file rewritten for group-awareness
  (fixture timestamps adjusted to produce genuine overlap; an
  `_upload_pair()` helper added across several API test files once the
  shared `synth_ascii`/`synth_binary` fixtures' identical timestamps
  were found to make "first-uploaded = reference" no longer a safe test
  assumption — which source becomes the group's own origin is now a
  `source_id` tie-break, not upload order).
- Extensively modified `frontend/index.html`: new per-source-id state
  (`manualAlignmentOffsets`, `timestampPlacementOffsets`,
  `timeGroupBySourceId`, `timeGroups`, `referenceSourceIds` replacing
  the old single-scalar `referenceSourceId`); group-aware
  `wwPanelGroupKeyFor()`/new `wwTimeGroupLabelSuffix()`; group-scoped
  `wwSetT0FromCursorA()`/`wwClearT0()`/Detect-Event-acceptance; the
  Synchronize Sources modal's manual/timestamp-placement split and
  relabeled Reset buttons; a live-UAT-discovered fix,
  `wwRefreshTimeGroupPanelLabels()` (an already-rendered panel's own
  "Time Group N" label could otherwise go stale if the workspace's
  group topology changed later, e.g. a third far-separated source
  uploaded after that panel already existed) — called once every time
  fresh sync/time-group state loads.
- Verified by 1503 passing backend tests (zero regressions, up from
  1476) + 24 new/updated frontend static-regression tests, plus a
  dedicated live-browser UAT (Playwright, purpose-built synthetic
  COMTRADE fixtures) reproducing the owner's own worked example
  end-to-end: 27/27 checks passed, zero console errors — two absolute
  sources 401ms apart at different sampling rates auto-aligned onto one
  shared panel with no manual action (confirmed both via the sidebar's
  own sync badge and the Synchronize Sources modal); a manual +1ms
  correction composed correctly on top and reverted correctly on Reset
  while the timestamp placement itself stayed intact and visibly
  survived the reset; a third, ~60-second-away source rendered as its
  own separate, correctly-labeled panel with no giant empty span;
  Detect Event's acceptance set `t0` for its own source's group only,
  independently confirmed unset for the unrelated group via a direct
  API check; Start New Workspace cleared every recording and all
  Time-Group state.
- **Known, disclosed, NOT solved by this phase**: per-Time-Group
  Absolute-mode wall-clock label origins (see Alternatives above); the
  elapsed-only Time Group path is fully implemented/tested but not
  currently reachable through the live app's own upload flow, since
  COMTRADE (the only importer that exists) always sets
  `timing_reference="absolute"` — a future CSV/Excel importer would be
  the real trigger, and remains out of scope for this task.
- **Deferred, not silently gapped** (task's own explicit non-goals):
  automatic multi-file t0 sync, cross-correlation, event-based
  automatic group merging, clock correction, timezone correction UI,
  clock drift, manual absolute-anchor entry for elapsed files, CSV/
  Excel parsing, automatic multi-event ranking, resampling, and
  cross-group calculations all remain unimplemented, unchanged from
  before this phase.

---

## DEC-058 — Time Range slider: one horizontal two-handle range navigator per Time Group, requiring the single workspace-wide viewport to become genuinely per-Time-Group internally, while every pre-existing single-instance UI surface stays scoped to the primary group

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction, "Add a horizontal
two-handle Time Range slider for each Time Group," delivered
immediately following DEC-057 (Timestamp-Based Initial Alignment and
Time Groups).

Decision:

**Time Range slider is a UX navigation control over an existing Time
Group viewport. It does not alter timing, synchronization, source
data, or sampling.** A compact horizontal two-handle range slider now
renders once per Time Group (never once per panel), reflecting and
controlling that group's own current visible viewport against its own
full recorded extent, bidirectionally synchronized with Plotly
mouse zoom/pan and Reset Time View.

Investigation found a real architectural constraint that materially
changed the approach (task's own explicit ask, section 22): every
panel in the workspace shared exactly ONE global `ww.viewport`/
`ww.workspaceBounds` (DEC-021's own "one shared X/time viewport across
every displayed channel," predating Time Groups entirely, and
explicitly left that way by DEC-057's own "fully independent
per-time-group viewports... deliberately scoped OUT" decision). A
slider genuinely independent per Time Group (task's own hard
requirement — section 3/6/7/8, and a dedicated regression Case G)
could not be built on top of a single shared viewport; it required
generalizing the viewport itself to `ww.timeGroupViewports: Map<groupId,
{start, end}>`, with the corresponding zoom/pan/refetch pipeline
(`wwApplyAndFetchGroupViewport()`, `wwRefetchChannelsForGroup()`,
`wwBroadcastGroupViewportDebounced()`) threaded per group.

**Scope boundary, deliberately drawn**: every pre-existing
single-instance cross-cutting UI surface — the cursor overlay, the
sticky ruler, the digital-channel region, +Peak/-Peak annotation
recalculation, the toolbar Zoom In/Out buttons, Detect Event's
visible-range search, Absolute-mode label origin — stays scoped to the
workspace's own PRIMARY Time Group (`wwPrimaryTimeGroupId()`, the same
"one deterministic source, narrower scope for cross-cutting shared
UI" precedent DEC-057 already established for `wwPrimaryTimeGroupSourceId()`
and the toolbar's own "Set Cursor A as t=0" action). In the common
single-Time-Group workspace this is byte-for-byte identical to
pre-slider behavior (there is only ever one group, so it IS the
primary one). A genuinely multi-Time-Group workspace gets independent
panel navigation per group through the slider itself, while those
specific shared, single-instance surfaces (never split by Time Group
in the underlying architecture to begin with — digital channels, for
one, have never been panel-split by Time Group even for analog's own
sake) continue to reflect only the primary group, exactly as before
this task, not newly regressed by it.

Reason:

The owner's own real-file UAT scenario — a 5 kHz ~1.3 s record and a
20 Hz ~69 s record of the same event, correctly sharing one Time Group
per DEC-057's own overlap rule — makes the short high-speed record
visually compressed to a sliver once Reset Time View shows the full
~69 s extent (correct, per DEC-057, and must not change). The slider
lets an engineer zoom/pan to the short event quickly without
abandoning the correct, non-resampled shared time axis.

Alternatives considered:

- A single zoom-factor slider (`Zoom: 1x —●— 10x`) — explicitly
  rejected by the task's own instructions (section 20): it shows
  neither WHERE within the full record the current view sits nor its
  actual width: a genuine range navigator (position + zoom together)
  is what the owner's own worked example requires.
- Two overlapping native `<input type="range">` elements — considered
  per the task's own explicit "first inspect existing dependencies"
  instruction (no slider/range library exists in this app, only
  Plotly); rejected because overlapping native ranges have no
  reasonable way to represent a draggable-in-the-middle "pan the
  window" gesture and are notoriously hard to grab the correct handle
  on. A lightweight, fully custom pointer-events-based track/handles/
  window implementation was built instead — contained to one new
  section of `frontend/index.html`, no new dependency.
- Fully extending cursor overlay/sticky ruler/digital-chart/Detect-
  Event/Absolute-origin independence to every Time Group in the SAME
  pass — considered, deliberately scoped OUT (see "Scope boundary"
  above): this task's own explicit ask is slider navigation, not a
  full multi-viewport rearchitecture of every UI surface, and DEC-057
  already established the identical narrower-scope precedent for
  exactly this class of cross-cutting single-instance feature.
- Rebasing wall-clock (Absolute-mode-style) labels onto the slider —
  considered, rejected: the slider's own compact label uses ONLY
  `wwFormatCursorDuration()` (a plain, always-correct duration, "Full:
  69.000 s · Visible: 1.299 s"), deliberately sidestepping DEC-057's
  own already-documented, still-open per-Time-Group Absolute-mode
  origin gap rather than extending it into a new surface.

Impact:

- `frontend/index.html` only (no backend/schema/API changes — the
  task's own "do not change backend timing calculations unless
  absolutely necessary" was fully honored; nothing was necessary).
  New per-group viewport state and pipeline
  (`ww.timeGroupViewports`/`ww.timeGroupViewportDebounceTimers`,
  `wwPanelTimeGroupId()`, `wwPrimaryTimeGroupId()`,
  `wwActiveTimeGroupIds()`, `wwDeriveTimeGroupBounds()`,
  `wwClampRangeToTimeGroup()`/`wwClampPanWindowToTimeGroup()`,
  `wwApplyAndFetchGroupViewport()`, `wwRefetchChannelsForGroup()`,
  `wwRefetchAllChannelsAcrossGroups()` replacing the old single-range
  `wwRefetchAllChannels()` at its 3 cross-cutting call sites,
  `wwRefreshTimeGroupViewports()` called from the existing
  `wwRefreshWorkspaceBounds()` without disturbing its own primary-group
  logic). `wwApplyAndFetchViewport()`/`wwResetTimeView()` kept their
  exact signatures as thin, backward-compatible wrappers. New slider UI
  (`#wwTimeGroupSliders`, between the digital region and the sticky
  ruler; `wwRenderTimeGroupSliders()` and its own row-creation/paint/
  drag-wiring functions) using native Pointer Events, no new library.
- Verified by 1533 passing backend tests (26 new
  `test_frontend_time_range_slider.py` + 4 pre-existing frontend
  static-regression tests updated for the renamed/generalized
  functions, zero regressions from 1507) plus two dedicated
  live-browser UAT passes (Playwright, real backend, synthetic COMTRADE
  fixtures matching the owner's own 5 kHz/1.3 s + 20 Hz/69 s scenario
  exactly): 25/25 checks passed across Reset Time View (full ~69 s,
  slider full-width), dragging a handle inward to ~1.3 s with both
  traces still rendering real, non-resampled sample counts, panning the
  selected window preserving span exactly, mouse zoom on the chart
  correctly driving the slider, Grouped and Separate layout parity,
  two independent Time Groups with an isolated drag on one leaving the
  other completely untouched, t0 set/cleared while the slider's own
  physical interval stayed bit-identical, and a source removal cleanly
  updating the slider's own row set and clamping the viewport safely.
- **Known, disclosed limitation, not solved by this task** (matches
  DEC-057's own precedent exactly): the digital-channel region,
  +Peak/-Peak annotation recalculation, the cursor overlay, the sticky
  ruler, and Absolute-mode label origins all remain scoped to the
  primary Time Group only — a genuinely multi-Time-Group workspace's
  non-primary groups get correct, independent WAVEFORM PANEL navigation
  via their own slider, but not yet independent cursors/ruler/digital-
  chart/Absolute labels of their own. This is the same class of gap
  DEC-057 already disclosed for t0's own toolbar quick-action, now
  extended (not newly introduced) to viewport navigation.
- **Deferred, per the task's own explicit non-goals**: Fit Active
  Source, automatic event focus, an overview waveform/minimap,
  source-specific sliders, sampling-rate conversion, waveform
  resampling, automatic t0 synchronization, backend synchronization
  changes, new Time Group derivation rules, clock correction, and CSV/
  Excel import all remain unimplemented, unchanged from before this
  task.

---

## DEC-059 — Time Group Canvas: each Time Group becomes its own structural UI section (header, panels, digital region, slider, sticky ruler), closing DEC-057/DEC-058's own disclosed "primary group only" ruler/digital/Absolute-origin gap for every group, not just the first

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("Slice TG-B+C — Time Group
Canvas foundation + per-group sticky time ruler + per-group digital
panel"), delivered immediately following DEC-058 (Time Range slider).

Decision:

**Each Time Group is now its own complete analysis canvas.** A new DOM
ownership boundary, `<section class="ww-time-group-canvas"
data-time-group-id="...">`, replaces the previously-flat, workspace-
wide singleton containers (`#wwPanels`, `#wwDigitalRegion`,
`#wwStickyRuler`, `#wwTimeGroupSliders`) with one canvas per currently
ACTIVE Time Group (a group backing at least one displayed channel —
`wwActiveTimeGroupIds()`, reading `ww.displayed` directly rather than
`ww.panels`, since the latter can be transiently stale relative to
current topology right after a merge/split). Every per-canvas element
is found via a scoped `canvasEl.querySelector(".ww-tg-...")` against
its own root, never a numbered singleton id.

Each canvas carries: a header (`"Time Group N\n<date> ·
<start>–<end> · N sources"`, numbered by current sorted group-id
order, never `group_id` itself), a minimal local toolbar (Reset Time
View only this slice — Cursor A/B, Set/Clear t0, Detect Event,
Synchronise Sources stay workspace-global, deliberately not migrated),
its own analog panels, its own digital-channel region (generalizing
`wwRebuildDigitalChart()`/`wwAddDigitalChannels()`/
`wwDigitalHighIntervals()` to take a `groupId`), its own Time Range
slider row (DEC-058's slider relocated INTO the canvas, exact owner
CSS `padding: 3px 20px 3px 20px` preserved unchanged), and its own
sticky ruler — all as direct sibling children within the SAME canvas
root, so `position: sticky` naturally bounds itself to that one
canvas's own box (a canvas releases its own sticky slider/ruler
automatically as the next canvas's content scrolls into view, no JS
scroll math).

This closes DEC-057/DEC-058's own explicitly disclosed "primary group
only" limitation for the ruler, digital chart, and Absolute-mode
label origin: `wwTimeGroupRecordingStartMs(groupId)` (resolving via
that group's own origin source) now threads through
`wwFormatAbsoluteElapsedTime()`/`wwAbsoluteTickLabelsForRange()`/
`wwTimeAxisTickFormat()`/`wwTimeAxisRelayout()`, so Group 2's own
ruler shows Group 2's own date, never Group 1's reused. Time Mode
(Absolute/Elapsed) itself stays workspace-global — only the ORIGIN
each ruler computes labels from is per-group.

**Audited and fixed one hard-boundary gap this slice's own explicit
requirement newly introduced**: `wwPanelGroupKeyFor()`'s Custom-mode
branch did not prefix its panel key with the channel's own current
Time Group id (unlike the Grouped-mode branch, which already did, per
DEC-057). This superseded DEC-057's own original Custom-mode
allowance ("the engineer's own explicit, deliberate grouping choice")
with the owner's now-explicit "Time Group remains a hard time-domain
boundary even in Custom mode" — an engineer-defined custom group
spanning two Time Groups now splits into one panel per Time Group,
confirmed live (2 canvases, 1 panel each, 2 traces each, never merged
into one).

**Topology-change-triggered rebuild, scoped to genuine reassignment
only**: `wwSyncTimeGroupCanvases()` reuses the already-proven
`wwRebuildLayout()` (rather than inventing incremental panel-
relocation logic) whenever the active-group-id SET changes — but only
when some previously-active id actually vanished (a merge, a split, or
a source removal), never on a pure ADDITION of a brand-new, disjoint
group (every previously-active id still present): that case needs no
existing panel to move, `wwCreatePanelDom()`'s own lazy per-group
canvas creation already covers it entirely additively, and skipping
the unnecessary rebuild also avoids an uncaught Plotly
`_redrawFromAutoMarginCount` TypeError found live during this slice's
own UAT (purging a panel synchronously right after its own
`Plotly.newPlot()` fired, before Plotly's own deferred auto-margin
callback had run). The remaining, genuinely-necessary rebuild path
(merge/split) still carries a residual version of that same race —
fixed by deferring the panel-purge loop's own `Plotly.purge()` calls
one `requestAnimationFrame`, which reliably runs after any 0-delay
`setTimeout` Plotly had already queued.

Reason:

Sections 1-20 of the owner's own task spec (verbatim, not reproduced
here): the Time Group Canvas boundary is the structural foundation
every subsequent per-group feature (independent cursors, independent
t0, per-group Detect Event/Sync scoping — all explicitly deferred,
see below) will eventually build on; this slice deliberately stops at
establishing that boundary plus the two already-designed-but-still-
primary-only surfaces (ruler, digital) DEC-057/058 had already
disclosed as open gaps.

Alternatives considered:

- Migrating Cursor A/B, t0, Detect Event, and Synchronise Sources to
  be per-canvas in the SAME pass — explicitly rejected by the task's
  own non-goals list (section 25): those remain scoped to the primary
  canvas only, via the same `wwPrimaryTimeGroup*()` compatibility
  resolvers DEC-057/058 already established, unchanged in behavior.
- Persistent Time Group ids surviving a merge/split — considered,
  rejected per the task's own explicit "Time Group identity
  lifecycle" policy: group ids are dynamically derived and may change;
  "derived group state recomputes automatically, ambiguous analysis
  state does not silently migrate" — panels/digital/slider/ruler
  re-route and headers re-render, but cursor/t0 analysis state is not
  attempted to survive a topology change this slice.
- Collapse-by-default for inactive canvases — considered, explicitly
  deferred (task section 20): every active canvas stays expanded by
  default this slice.

Impact:

- `frontend/index.html` only. Replaces 4 singleton containers with
  `#wwTimeGroupCanvases` (JS-populated); new canvas DOM module
  (`wwCreateTimeGroupCanvasDom()`, `wwEnsureTimeGroupCanvasDom()`,
  `wwSyncTimeGroupCanvasHeader()`, `wwSyncTimeGroupCanvases()` as the
  one master per-sync orchestrator); `ww.rulerReadyByGroup`/
  `ww.digitalChartReadyByGroup`/`ww.digitalClickWiredByGroup`
  (`Map<groupId, bool>`) replacing the old single booleans;
  `ww.lastActiveTimeGroupIds` tracking the topology-change baseline.
  `wwActiveTimeGroupIds()`/`wwPrimaryTimeGroupId()` rewritten to read
  `ww.displayed` instead of `ww.panels` (a genuine correctness fix,
  not just a rename — avoids a circular staleness dependency right
  after a topology change). No backend/schema/API changes.
- Verified by the full backend suite (zero regressions; 16
  pre-existing frontend static-regression tests updated for the
  renamed/generalized selectors and functions, 4 new backend
  datetime-invariant regression tests added locking in behaviour that
  was already correct in `app.domain.time_grouping` — different-date-
  same-time-of-day, the exact bridging-long-record merge case,
  same-hour-different-date, and non-overlapping midnight rollover)
  plus four live-browser Playwright UAT passes against a running
  backend with synthetic COMTRADE fixtures: two independent Time
  Groups on genuinely different calendar dates (16/16 checks — correct
  per-group headers/dates, group-exclusive analog/digital routing,
  one slider/ruler per canvas, scroll-based sticky handoff, correct
  per-group Absolute-mode origin, zero console errors); a bridge-
  source merge/split cycle (12/12 checks — one merged canvas
  consolidating all 3 sources' traces/slider/ruler/header, then a
  clean split back to 2 independent canvases with no stale DOM, zero
  console errors); a Grouped/Separate/Custom layout-mode sweep (11/11
  checks — Time Group boundary preserved across all 3 modes,
  including the Custom-mode hard-boundary fix confirmed live).
- **Known, disclosed limitations, not solved by this task** (same
  class of gap DEC-057/058 already established a precedent for, now
  narrowed rather than newly introduced): Cursor A/B, the A-B info
  readout, t0 toolbar state, Detect Event's search scope, and
  Synchronise Sources all remain workspace-global/primary-canvas-only
  — a genuinely multi-Time-Group workspace gets independent panel
  navigation, ruler, and digital-channel display per group, but not
  yet independent cursors/t0/event-detection/sync scoping of its own.
- **Deferred, per the task's own explicit non-goals**: per-group
  Cursor A/B, per-group t0, Detect Event source restriction,
  Synchronise Sources restriction/redesign, cross-group linking,
  annotation redesign, collapse-by-default, CSV/Excel, clock
  correction, timestamp-confidence scoring, and event-name inference
  all remain unimplemented, unchanged from before this task.

## DEC-060 — TG-D1: staged Zoom In/Out, Reset Time View, and Autoscale Y migrate into each Time Group Canvas's own local navigation toolbar, making these four controls genuinely Time-Group-scoped instead of workspace-global

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("TG-D1 — migrate low-risk
navigation controls into each Time Group toolbar"), delivered
immediately following the owner-approved Slice TG-B+C empty-state
lifecycle fix.

Decision:

**A navigation control inside a Time Group Canvas affects only that
Time Group.** Each `.ww-tg-toolbar` shell (established by TG-B+C, one
per canvas) now carries staged Zoom In, staged Zoom Out (both
preserving the exact Phase 4D/DEC-043 X/Y split-button dropdown, the
same ±20%/±25% stepping factors, the same min-span floors, the same
"keep the midpoint fixed" math — no redesign), Reset Time View
(already correctly per-group since TG-B+C — audited and confirmed,
not rewritten), and Autoscale Y (newly generalized to
`wwAutoscaleYForGroup(groupId)`, filtering by
`wwPanelTimeGroupId(panel) === groupId`). The former workspace-wide
functions (`wwStepZoomX`/`wwStepZoomY`) were generalized in place to
take `groupId` as their first parameter (task's own explicit example),
reading/writing that group's own viewport
(`wwTimeGroupVisibleRange()`/`wwApplyAndFetchGroupViewport()`) instead
of the single `ww.viewport`. Y-step-zoom's own "active panel" target
is resolved via a new `wwActivePanelForGroup(groupId)` — the global
active-panel-click mechanism itself is untouched, but a group-scoped
Y-zoom now falls back to that group's OWN first panel, never
`ww.panels[0]` outright, so it can never reach into an unrelated
group.

Each control is wired once per canvas via one reusable
`wwWireTimeGroupToolbar(canvasEl, groupId)`, resolving every element
through `canvasEl.querySelector(...)` — no singleton ids reintroduced,
no per-group duplicated listener logic. The former global split-button
markup/ids and their `wwWireZoomStepSplitButtons()` wiring were
removed outright (not merely hidden), so there is exactly one active
way to invoke each of the four controls. The former global functions
(`wwResetTimeView()`, `wwAutoscaleY()`) are kept as workspace-wide
compatibility wrappers (per the task's own explicit allowance) —
present, correct, but no longer wired to any button. The zoom
split-button's own remembered X/Y axis preference became
`ww.zoomStepAxisByGroup: Map<groupId, {in, out}>` (was a single flat
object) so choosing Y in one group's own dropdown never relabels
another group's button. Plotly's own native double-click-to-autorange
gesture on a panel was also re-pointed at
`wwResetOneTimeGroupView(wwPanelTimeGroupId(panel))` — the same
isolation rule applies to every path that can trigger a reset, not
only the toolbar button.

Reason:

Sections 1-3 of the owner's own task spec: these four controls
operate purely on one group's own viewport/panels/Y-presentation, so
they are the natural next slice after TG-B+C's own structural
boundary work — genuinely low-risk to migrate without touching Cursor
A/B, A-B measurements, t0, Detect Event, or Synchronise Sources
(explicitly deferred, unchanged).

Alternatives considered:

- Redesigning the zoom mechanics (e.g. collapsing the X/Y split-button
  into a single button, or changing the stepping factors) — explicitly
  rejected (task section 2's own "do not simplify or redesign the zoom
  behavior").
- A workspace-wide `zoomStepAxis` preference shared across all groups
  — considered, rejected: would let choosing Y in one group's own menu
  silently redirect another group's button label/behavior, violating
  the task's own "control state must not leak between groups" rule
  (section 14).
- Removing `wwResetTimeView()`/`wwAutoscaleY()` entirely instead of
  keeping them as wrappers — considered, rejected per the task's own
  explicit compatibility allowance (section 10); an existing backend
  test (`test_frontend_source_bounds.py`) also already depends on
  `wwResetTimeView()`'s own documented behavior.

Impact:

- `frontend/index.html` only (no backend/schema/API changes). New:
  `wwActivePanelForGroup()`, `wwAutoscaleYForGroup()`,
  `wwZoomStepAxisForGroup()`, `wwSyncTimeGroupZoomControls()` +
  `wwSyncAllTimeGroupZoomControls()`, `wwWireTimeGroupToolbar()`,
  `wwWireSplitMenuOutsideClickDismissal()`. Generalized in place:
  `wwStepZoomX(groupId, direction)`, `wwStepZoomY(groupId, direction)`,
  `wwPerformZoomStep(groupId, action)`,
  `wwSetZoomStepAxis(groupId, action, axis)`. `ww.zoomStepAxisByGroup`
  replaces the old flat `ww.zoomStepAxis`. Removed as genuinely dead
  code once its only caller was generalized per-group:
  `wwClampZoomWindowToWorkspace()` (superseded by the already-existing,
  now-reused `wwClampPanWindowToTimeGroup()`). Removed global HTML:
  the former `#wwZoomInSplit`/`#wwZoomOutSplit`/`#wwResetViewBtn`/
  `#wwAutoscaleBtn` markup and their init-time wiring calls.
- Verified by the full backend suite (zero regressions; 1 pre-existing
  frontend static-regression test updated for the now-unconditional,
  no-longer-primary-only zoom-controls sync; 46 new tests in
  `test_frontend_time_group_toolbar.py` covering all 12 of the task's
  own required cases) plus two live-browser Playwright UAT passes
  against a running backend: 20/20 checks (one Time Group's own
  toolbar, staged Zoom In/Out narrowing/widening only that group,
  Reset restoring exact full bounds, Autoscale setting
  `yaxis.autorange`, a second Time Group's own toolbar appearing on
  activation, byte-for-byte isolation in both directions for
  zoom/reset/autoscale, slider/ruler/digital staying in sync, and
  toolbar count surviving a Grouped/Separate/Custom layout-mode sweep)
  and 11/11 checks (per-group axis-preference isolation — choosing Y
  in one group's own dropdown never relabels the other's button — and
  a bridge-source merge producing exactly one fresh, correctly-wired,
  non-duplicated toolbar on the newly merged canvas), zero console
  errors throughout both passes.
- **Known, disclosed limitations, not solved by this task** (same
  class of gap DEC-057/058/059 already established a precedent for,
  now narrowed further, not newly introduced): Cursor A/B, the A-B
  info readout, t0 toolbar state, Detect Event's search scope, and
  Synchronise Sources all remain workspace-global/primary-canvas-only
  — deliberately deferred to later slices, per this task's own
  explicit non-goals list (section 22).
- **Deferred, per the task's own explicit non-goals**: per-group
  Cursor A/B, per-group A-B info, per-group t0 UI, Detect Event
  migration, Synchronise Sources migration, annotation redesign,
  collapse behavior, Time/Unit/Layout Mode localization, cross-group
  linking, and CSV/Excel all remain unimplemented, unchanged from
  before this task. Sticky-top behavior for `.ww-tg-toolbar` itself
  was also not introduced this slice (task section 15: "only make it
  sticky if this was already planned/proven safe from TG-B+C" — it was
  not, so the toolbar stays structurally where TG-B+C placed it,
  non-sticky).

---

## DEC-061 — TG-D2: Cursor A/B and A-B measurement/information state migrate into each Time Group Canvas, replacing the single workspace-wide cursor pair with one independent pair per Time Group

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("TG-D2 — migrate Cursor
A/B and A-B measurement/information state into each Time Group
Canvas"), delivered as the correctness-critical successor to TG-D1's
navigation-control migration.

Decision:

**Cursor A/B is meaningful only inside one coherent Time Group. No
cursor state, overlay, value, or A-B measurement may leak across Time
Group boundaries.** The single `ww.measurementCursors` object is
replaced by `ww.timeGroupCursorState: Map<groupId, {enabled,
a:{visible,time}, b:{visible,time}}>`, resolved via the same
default-vs-mutating resolver pair TG-D1 established for
`ww.zoomStepAxisByGroup`: `wwTimeGroupCursorState(groupId)` (read-only,
returns a default for an untouched group, never inserts) and
`wwEnsureTimeGroupCursorStateEntry(groupId)` (get-or-create, used by
every write path). Every projection helper
(`wwCursorPlotMetrics`/`wwCursorTimeToPixelX`/`wwCursorPixelXToTime`)
now REQUIRES an explicit `groupId` — no hidden fallback to the primary
group — reading that group's own `wwTimeGroupVisibleRange()` instead
of the single `ww.viewport`, closing the exact ambiguity the task
exists to fix (a non-primary canvas's cursor line could previously be
drawn at the wrong X position using the primary group's own
viewport).

The Cursor A/B toggle button, the A-B readout (`A`/`B`/`Δt`), and the
cursor/label/ruler overlay DOM all moved from workspace-wide
singletons into each `.ww-time-group-canvas` (`.ww-tg-cursor-mode-btn`,
`.ww-tg-cursor-readout`, `.ww-tg-cursor-overlay`,
`.ww-tg-cursor-label-layer`), wired once per canvas via
`wwWireTimeGroupCursorOverlay(canvasEl, groupId)` — merging the former
`wwEnsureCursorDom()` + `wwWireCursorDrag()` into one per-canvas
function with its own closure-scoped drag state (zero shared mutable
state between groups). The former single ~230-line
`wwUpdateCursorOverlay()` became `wwUpdateCursorOverlayForGroup(groupId)`
plus a thin `wwUpdateAllCursorOverlays()` batch wrapper (mirroring
`wwSyncAllTimeGroupRulers()`'s established convention) — every call
site with a specific group already in scope (drag handlers, panel
resize, ruler/digital sync) calls the per-group function directly;
only genuinely workspace-wide triggers (full resize, layout-mode
rebuild, Detect Event suggestion changes) call the batch sweep, per
the task's own performance requirement that one group's cursor
movement must never touch an unrelated group's canvas. The sidebar's
existing "Cur A"/"Cur B" per-channel value columns stay in their
existing location (not moved — only the A-B readout itself moved) but
`wwCurValueText()`/`wwDigitalCurStateText()` now resolve each
channel's own OWNING Time Group via `wwTimeGroupIdForDisplaySourceId()`
before reading cursor state — the core fix for the task's own
channel-value cross-group-leakage concern.

**State lifecycle changed from viewport-driven to topology-driven**:
the former `wwReinitCursorsForNewViewport()` (reset on any fresh
viewport, even within a still-existing group) and
`wwResetMeasurementCursors()` (Start New Workspace only) are both
retired outright. Per-group cursor state now lives and dies with the
same topology-change lifecycle already proven for
`ww.rulerReadyByGroup`/`ww.digitalChartReadyByGroup`/
`ww.digitalClickWiredByGroup`/`ww.zoomStepAxisByGroup`: pruned in
`wwSyncTimeGroupCanvases()`'s per-group prune loop and its
zero-active-groups branch, and cleared unconditionally by
`wwClearWorkspace()` for BOTH "Clear workspace" and "Start New
Workspace" (a deliberate behavior change from the pre-TG-D2 era, where
plain "Clear workspace" left the single global cursor pair alone —
every canvas, and therefore every group's own overlay DOM, is torn
down by either action alike, so starting each surviving group's own
cursor state clean is the correct, honest behavior rather than
silently reusing now-pixel-stale state).

"Set Cursor A as t=0" stays explicitly primary-group-scoped this
slice (t0 itself remains deferred to TG-E): `wwSyncT0Controls()`/
`wwSetT0FromCursorA()` now read
`wwTimeGroupCursorState(wwPrimaryTimeGroupId())` — byte-identical
behavior for the common single-group case, and a documented,
intentional scope limit for a genuinely multi-group workspace
(consistent with the already-established primary-group-only
precedent DEC-057/058/059/060 set for other still-deferred
cross-cutting features). Detect Event's "Suggested event" preview
marker (which shares the same overlay rendering code) is narrowly
adapted to derive its own owning group from
`ww.suggestedEvent.sourceId` — a minimal scoping fix, not a Detect
Event feature change (unmigrated, per the task's own explicit
non-goal). Annotation reprojection
(`wwAnchoredAnnotationPagePosition()`) now passes
`wwPrimaryTimeGroupId()` explicitly to the now-required-groupId
`wwCursorTimeToPixelX()` — preserving its pre-existing primary-group-
only behavior byte-for-byte (annotations are unmigrated, an explicit
non-goal). The former global bottom-status-bar `#wwCursorReadout`
(`A`/`B`/`Δt`) is removed outright — it would otherwise show whichever
group was clicked last with no indication of which, exactly the
ambiguity this task exists to eliminate.

Reason:

The task's own governing correctness problem: a single workspace-wide
`ww.measurementCursors` pair, combined with a primary/global viewport
projection, could draw a cursor line at the wrong X position on a
non-primary canvas in a multi-group workspace — silently wrong
analysis, not merely a cosmetic gap (unlike TG-D1's four navigation
controls, explicitly called out by the task as "correctness-critical"
for this reason).

Alternatives considered:

- Keeping one hidden global cursor pair underneath multiple canvases
  (e.g. only changing which canvas visually renders it) — explicitly
  rejected by the task's own target-state model (section 3): each
  group must own its own completely independent pair, not share one
  hidden pair.
- Migrating "Set Cursor A as t=0" to be genuinely per-group this same
  slice — rejected per the task's own explicit deferral (section 27);
  the existing primary-group-only read is the smallest safe,
  unambiguous interim behavior, clearly disclosed rather than silently
  left inconsistent.
- Resetting cursor state on every viewport change (preserving the old
  `wwReinitCursorsForNewViewport()` behavior) — rejected: superseded by
  the already-proven topology-based prune/default mechanism, which is
  strictly more correct (a fresh-viewport recalculation within the
  SAME still-existing group no longer needlessly discards a placed
  cursor).

Impact:

- `frontend/index.html` only (no backend/schema/API changes). New:
  `wwTimeGroupCursorState()`, `wwEnsureTimeGroupCursorStateEntry()`,
  `wwAnyTimeGroupCursorsEnabled()`, `wwWireTimeGroupCursorOverlay()`,
  `wwUpdateCursorOverlayForGroup()`, `wwUpdateAllCursorOverlays()`,
  `wwSourceIdsForTimeGroup()`,
  `wwCursorValuesHandleModeDisabledForGroup()`,
  `wwCursorValuesHandleCursorClosedForGroup()`,
  `wwFetchAllCursorValuesForGroup()`,
  `wwScheduleCursorValuesRefreshForGroup()`. Generalized in place to
  require `groupId`: `wwCursorPlotMetrics()`, `wwCursorTimeToPixelX()`,
  `wwCursorPixelXToTime()`, `wwFormatCursorPointTime()`,
  `wwInitMeasurementCursorPositions()`, `wwToggleMeasurementCursors()`,
  `wwSetMeasurementCursorVisible()`, `wwCurValueText()`,
  `wwDigitalCurStateText()`, `wwFetchCursorValuesForSource()`,
  `wwDetectEventSearchRangeLabel()`. `ww.timeGroupCursorState` replaces
  the old flat `ww.measurementCursors`;
  `wwCursorValuesThrottleTimers`/`wwCursorValuesThrottlePending` became
  per-group `Map`s. Removed outright:
  `wwReinitCursorsForNewViewport()`, `wwResetMeasurementCursors()`, the
  old global `#wwCursorModeBtn`/`#wwCursorOverlay`/
  `#wwCursorLabelLayer`/`#wwCursorReadout` HTML and their init-time
  wiring, and 5 now-dead `wwPrimaryTimeGroup*El()` helpers that existed
  only to support the former primary-only overlay.
- Verified by the full backend suite (1606 passed before this task's
  own new tests; 9 pre-existing frontend static-regression tests
  across `test_frontend_detect_event.py` (5),
  `test_frontend_per_unit_mode.py` (1),
  `test_frontend_synchronization.py` (1), and
  `test_frontend_synchronization_t0.py` (2) updated for the renamed/
  regrouped functions; 41 new tests in
  `test_frontend_time_group_cursors.py` covering the task's own
  required cases — final suite: 1647 passed, 0 failed) plus a live-
  browser Playwright UAT pass against a running backend covering two
  genuinely separate Time Groups (non-overlapping absolute time,
  forced via a second synthetic fixture an hour apart): one group's
  cursor mode enabled/placed/zoomed with Δt verified stable across a
  zoom-then-reset cycle, a second group confirmed OFF by default with
  no readout, enabled independently with different A/B values,
  Group 1 confirmed byte-for-byte unaffected throughout (both
  directions), a Grouped/Separate layout-mode round trip confirmed
  Group 1's cursor readout survived, and zero console/page errors
  throughout.
- **Pre-existing bug discovered during this task's UAT, NOT introduced
  by and NOT fixed by this task (out of scope — unrelated to cursor
  state)**: with two Time Groups present, switching layout mode
  (Grouped → Separate → Grouped) leaves a non-primary group's own
  analog-panel X-axis TICK LABELS showing the PRIMARY group's Absolute-
  time origin, even though that panel's own header, trace color, and
  data stay correctly matched to its own group — confirmed
  independently reproducible on unmodified `HEAD` (i.e. before any
  TG-D2 change), root-caused to `wwBuildLayout()` (called from
  `wwRebuildLayout()`'s panel-recreation loop) computing its tick
  format from the single global `ww.viewport` with no `groupId`
  parameter, unlike `wwSetTimeMode()`/`wwApplyT0ToDisplay()` which
  already correctly resolve each panel's own group. Reported here per
  the project's own change-governance requirement rather than silently
  fixed inside a cursor-scoped task; a future slice should pass each
  panel's own `wwPanelTimeGroupId(panel)` into `wwBuildLayout()`'s tick
  computation.
- **Deferred, per the task's own explicit non-goals**: per-group t0 UI
  (t0 itself stays primary-group-scoped), Detect Event migration,
  Synchronise Sources migration, cross-group cursor comparison
  (deliberately prohibited by this task's own design, not merely
  unimplemented), annotation redesign, collapse behavior, CSV/Excel,
  clock correction, and new cursor math/analysis features all remain
  unimplemented/unchanged from before this task.

---

## DEC-062 — TG-E: t0 becomes genuinely Time-Group-scoped throughout the frontend (mirroring the backend's already-group-keyed truth), and Detect Event becomes internally Time-Group-aware while its normal frontend entry point is hidden by owner decision

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("TG-E — Per-Time-Group t0 +
Detect Event migration"), delivered as the direct successor to TG-D2
(DEC-061), which had deliberately deferred full per-group t0 to this
slice.

Decision:

**Each Time Group owns its own t0.** Audit finding that shaped this
entire slice: the BACKEND has been fully Time-Group-scoped for t0
since Slice 2 (`SynchronizationRegistry._t0`, keyed by
`(workspace_id, time_group_key)` — see
`app.services.synchronization_service._resolve_time_group_key()`) —
every GET/PUT/DELETE `.../synchronization/t0` call already resolves
"which group" from the `source_id` it's given and touches only that
group's own key. The FRONTEND was the one place still narrowed to a
single scalar (`ww.t0WorkspaceTime`, fetched only for one resolved
"primary" source). This slice is therefore a frontend mirroring
exercise, not a new architecture: `ww.timeGroupT0State: Map<groupId,
t0_workspace_time>` replaces the scalar, populated by fetching t0 for
every known group in parallel (`Promise.all`) rather than one primary
source. `wwT0ForGroup(groupId)`/`wwHasT0(groupId)` are the resolver
pair every t0-aware function now reads through — both REQUIRE an
explicit `groupId`, no hidden fallback to any one "primary" group,
matching TG-D2's own established convention for cursor state.

The core X-coordinate transform every panel/ruler/digital-chart trace
already funnels through, `wwElapsedToPlotlyX`/`wwPlotlyXToElapsed`, is
generalized to `(groupId, value)` — this is the fix for the actual
correctness gap TG-D2 left open: previously, ANY group's t0 shifted
EVERY panel's plotted X data globally (the single scalar applied
everywhere `wwElapsedToPlotlyX` was called), a latent bug invisible
until a genuinely multi-group workspace with an active t0 was tested.
Every call site already had a `groupId` available in scope (a panel's
own via `wwPanelTimeGroupId()`, a channel's own via
`wwTimeGroupIdForDisplaySourceId(channel.sourceId)`, a ruler/digital
function's own parameter) — this was a mechanical, forced propagation,
not a redesign.

Each Time Group Canvas's own local toolbar gains a `.ww-tg-t0-btn` —
the exact same single dual-purpose "Set Cursor A as t=0"/"Clear t=0"
toggle UX the former global `#wwSetT0Btn` established, preserved
verbatim per task section 7's own "preserve that UX where practical."
The old global button and the `#statusBarT0` bottom-status-bar readout
are both removed outright (not merely hidden) — a single global t0
readout became exactly the same kind of ambiguous surface DEC-061
already eliminated for Cursor A/B ("whose t0 would it show?").

Reason:

Section 1's own governing principle: "There must be no remaining
assumption that one workspace has only one t0." A single global
scalar — even one that already read from a per-group-keyed backend —
still meant every panel's own rendering used ONE group's t0 regardless
of which group it actually belonged to, silently wrong the moment a
second group's t0 was ever set. This is the same class of
correctness-critical gap DEC-061 closed for cursor overlays, now
closed for the coordinate transform underneath them.

Detect Event (task section 17, explicit owner decision): "the
capability remains implemented and fully maintained... but its normal
frontend entry point should be hidden for now." A single named
constant, `WW_DETECT_EVENT_UI_ENABLED = false`, is the one source of
truth — deliberately not a general feature-flag system (none exists in
this codebase, and this task does not need one). The button's own
`.hidden` attribute is set from that constant at init time; the click
listener stays wired regardless, so re-enabling later is a one-line
flip, never a second wiring/architecture pass. Discovered live during
this task's own UAT: `.ww-icon-btn { display: inline-flex; }`'s own
AUTHOR-origin CSS rule silently overrides the browser's UA-stylesheet
`[hidden] { display: none }` default (same origin-precedence mechanism
`#bottomStatusBar .shell-status-item[hidden]` already documents
elsewhere in this file) — without an explicit `.ww-icon-btn[hidden] {
display: none; }` override, setting `.hidden = true` on the button had
zero visual effect despite the attribute genuinely being present in
the DOM. Fixed as part of this slice (the bug is in the SAME hiding
mechanism this task introduces, not a pre-existing unrelated issue).

Even hidden, Detect Event's own internal workflow is migrated to be
genuinely Time-Group-aware (task section 19): `wwOpenDetectEventModal(groupId)`
now requires an explicit groupId and filters the source dropdown to
ONLY that group's own member sources
(`wwDetectEventSourceOptionsHtml(groupId)`); "Current visible range"
now converts the LAUNCHING GROUP's own `wwTimeGroupVisibleRange(groupId)`,
never the single global/primary `ww.viewport`; accepting a candidate
now derives the candidate's own owning group from its `sourceId` and
writes ONLY that group's `ww.timeGroupT0State` entry. No new per-group
Map was introduced for the transient candidate itself (task section 24's
own explicit allowance against overengineering a transient modal's
state) — unambiguous ownership instead falls out structurally from the
group-filtered source dropdown: whichever source a candidate names,
`wwTimeGroupIdForDisplaySourceId(sourceId)` always resolves back to the
SAME group that launched the modal.

Alternatives considered:

- Keeping t0 primary-group-scoped permanently (TG-D2's own interim
  policy) — explicitly rejected: this is the exact deferred work TG-E
  exists to complete, and the governing principle ("no remaining
  assumption that one workspace has only one t0") is incompatible with
  leaving any group second-class.
- A `wwTimeGroupDetectEventState = Map<groupId, {...}>` for the
  candidate itself (task section 24's own suggested "if needed"
  alternative) — considered, rejected as unnecessary: the modal is a
  single transient global overlay (only one can ever be open), and its
  own source-dropdown filtering already makes ownership unambiguous
  without a second piece of state to keep in sync.
- Deleting the Detect Event capability entirely instead of hiding it —
  explicitly rejected by the owner's own instruction ("Do not delete
  the Detect Event implementation. Do not remove its tests.").
- Migrating Detect Event's own entry point into each Time Group
  Canvas's local toolbar (mirroring t0/Cursor A/B) — considered,
  rejected: the owner decision is to HIDE the capability from normal
  use, not to give it a more prominent per-canvas home; the existing
  single global (now-hidden) button remains the one entry point, ready
  to resolve `wwPrimaryTimeGroupId()` if ever re-enabled as-is, or to
  be migrated per-canvas in a genuinely future slice if the owner
  chooses to re-expose it that way instead.
- Not fixing the newly-discovered `.ww-icon-btn[hidden]` CSS-origin bug
  and instead deleting the button's markup outright — rejected: task
  section 27 requires the DOM/workflow to "remain functional," and an
  entirely removed button contradicts "re-enabling later should require
  only a small exposure change."

Impact:

- `frontend/index.html` only (no backend/schema/API changes — the
  backend was already fully group-scoped). New:
  `wwT0ForGroup()`, `wwAnySourceIdForTimeGroup()`,
  `wwApplyT0ToDisplayForGroup()`, `wwSyncT0ControlsForGroup()`,
  `wwSetT0FromCursorAForGroup()`, `wwClearT0ForGroup()`,
  `wwHandleSetOrClearT0ClickForGroup()`, `WW_DETECT_EVENT_UI_ENABLED`.
  Generalized in place to require `groupId`: `wwHasT0()`,
  `wwWorkspaceTimeToEventTime()`, `wwEventTimeToWorkspaceTime()`,
  `wwElapsedToPlotlyX()`, `wwPlotlyXToElapsed()`, `wwTimeAxisTitle()`,
  `wwFormatCursorPointTime()`'s own t0 gate (no longer primary-only),
  `wwApplyTimeAxisChrome()` (optional groupId, mirrors
  `wwVisibleSpanSeconds()`'s own TG-D2 precedent),
  `wwDetectEventSourceOptionsHtml()`,
  `wwDetectEventVisibleSourceNativeRange()`, `wwOpenDetectEventModal()`.
  `ww.timeGroupT0State` replaces the old flat `ww.t0WorkspaceTime`.
  Removed outright: the old global `#wwSetT0Btn`/`#statusBarT0`/
  `#statusBarT0Value` HTML and their wiring, `wwSyncT0Controls()`,
  `wwSetT0FromCursorA()`, `wwClearT0()`, `wwHandleSetOrClearT0Click()`,
  `wwApplyT0ToDisplay()` (workspace-wide form — no "apply to every
  group" batch counterpart was needed; nothing in this slice required
  one).
- New CSS: `.ww-icon-btn[hidden] { display: none; }` (the origin-
  precedence fix described above).
- Verified by the full backend suite (1688 passed, 0 failed — up from
  1647 at TG-D2's own end state; 39 pre-existing frontend static-
  regression tests updated across
  `test_frontend_absolute_time_precision.py`,
  `test_frontend_calculated_channel_time_mode.py`,
  `test_frontend_waveform_adaptive_resolution.py`,
  `test_frontend_synchronization_t0.py`,
  `test_frontend_detect_event.py`, `test_frontend_time_group_cursors.py`,
  `test_frontend_time_group_toolbar.py`, `test_frontend_time_groups.py`;
  63 new tests added across two new files,
  `test_frontend_time_group_t0.py` (Cases A-M) and
  `test_frontend_detect_event_group_scoped.py` (Cases N-W)) plus a
  live-browser Playwright UAT pass covering the task's own full 20-step
  scenario against a running backend: Group 1 set/clear t0 with
  event-relative shift confirmed and original mapping restored; a
  second, genuinely separate Time Group added and given its own,
  different t0; both groups' own local button state confirmed
  independent in both directions (setting/clearing one never affects
  the other); a Grouped/Separate layout-mode round trip preserved
  Group 2's own t0; the Detect Event button confirmed hidden (and, once
  the CSS bug above was found and fixed, genuinely invisible, not just
  attribute-hidden); the modal invoked programmatically
  (`wwOpenDetectEventModal(group2Id)`) with its source list confirmed
  to resolve exclusively to Group 2; and — after manually constructing
  a candidate for Group 2 (the synthetic sawtooth fixtures used for
  this UAT have no genuine RMS-change event for the unmodified
  detection algorithm to find, an expected true-negative, not a
  defect) — accepting it confirmed to set ONLY Group 2's own t0,
  Group 1 unaffected. Zero console/page errors throughout.
- **Deferred, per the task's own explicit non-goals**: Synchronise
  Sources migration (TG-F), cross-group t0 (deliberately prohibited by
  design, not merely unimplemented), automatic cross-file event
  alignment, new event detection algorithms, event classification,
  annotation redesign (still primary-group-scoped, unchanged), collapse
  behavior, CSV/Excel, clock drift correction, and cross-group cursor
  comparison all remain unimplemented/unchanged from before this task.
  The pre-existing, unrelated Absolute-axis layout-round-trip bug
  DEC-061 already documented (`wwBuildLayout()`'s own tick-RANGE source
  still reads global `ww.viewport`, not a per-group range) was
  correctly left untouched — this slice only threaded `groupId` through
  `wwBuildLayout()`'s t0-awareness (a forced, minimal propagation,
  confirmed via `git diff` to touch zero range-source lines), never
  fixing the separate, still-open range-source limitation, exactly as
  instructed.

---

## DEC-063 — TG-F: Synchronise Sources becomes local to each Time Group Canvas, with manual alignment strictly confined to the launching Time Group and never redefining canonical Time Group membership

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("TG-F — migrate Synchronise
Sources into each Time Group Canvas"), delivered as the direct
successor to TG-E (DEC-062), completing the migration of every
remaining per-Time-Group toolbar control.

Decision:

**Synchronise Sources is local to one Time Group.** Audit finding that
shaped this slice's own central safety property: Time Group membership
(`app.domain.time_grouping.derive_time_groups()`, fed exclusively by
`app.services.synchronization_service._group_lookup()` from
`WorkspaceRegistry`'s own `SourceMetadata` — raw recorded
`start_time`/`elapsed_start_seconds`/`elapsed_end_seconds` only) is
structurally UNABLE to read `SynchronizationRegistry`'s own manual-
offset store at all — `list_time_groups()`'s own signature never even
accepts a `registry` parameter. Manual synchronization therefore cannot
redefine Time Group membership by construction, not merely by
convention; this was confirmed both behaviorally (a 60s manual offset
applied inside a group does not change `list_time_groups()`'s own
output) and structurally (an `inspect.signature()` assertion) in
`test_time_grouping_service.py::TestManualSynchronizationNeverRedefinesTimeGroupMembership`.
No backend or domain-layer change was needed for this slice's own
governing safety rule — it already held.

The former global `#wwSyncBtn` moved into each Time Group Canvas's own
local toolbar as `.ww-tg-sync-btn`, wired through the same
`wwWireTimeGroupToolbar(canvasEl, groupId)` every other per-canvas
control already uses. The modal shell itself (`#wwSyncOverlay`) stays
ONE shared, reusable overlay — never cloned per canvas — mirroring
Detect Event's own established pattern (TG-E): opened via
`wwOpenSyncModal(groupId)`, which REQUIRES an explicit groupId (never
`wwPrimaryTimeGroupId()`, never inferred from "whichever source was
selected most recently"). A new `let wwSyncModalGroupId` module-level
variable (mirroring the pre-existing `wwMgEditState` convention for
"whichever modal/drawer is currently open") remembers which group's
own modal is open, so every subsequent action inside it (step, set,
reset, Reset All) re-scopes back to the SAME launching group. A new
`wwSourcesForTimeGroup(groupId, sources)` filters the full workspace
source list to only that group's own members (every source, not just
currently-displayed ones — a source can be a group member worth
synchronizing before any of its channels are toggled on) before
`wwRenderSyncBody()` ever sees it — mirroring
`wwDetectEventSourceOptionsHtml(groupId)`'s own established filtering
convention exactly.

**Reset All is now local to the launching Time Group.** The backend's
own `DELETE .../synchronization/sources` endpoint resets every
workspace source's manual correction at once, with no group-scoped
variant — but per task section 29/30 ("reuse existing source-level
API... do not widen backend scope unnecessarily"), no backend change
was made: the new `wwSyncResetAllForGroup(groupId)` instead loops the
group's own `sourceIds` (from `ww.timeGroups`) calling the ALREADY-
existing, already-validated, already-idempotent per-source `DELETE
.../sources/{source_id}` endpoint in parallel (`Promise.all`) — the
smallest correct implementation, never a duplicated or widened backend
surface.

Offset-change side effects (`wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)`,
replacing the former workspace-wide `wwSyncApplyOffsetChangeSideEffects()`)
are now genuinely group-scoped (task section 16/31's own performance
requirement: "one +/- adjustment should not rebuild every canvas"):
channel refetching reuses the ALREADY-EXISTING, per-channel-filtered
`wwRefetchChannelsForGroup(groupId, startTime, endTime)` (the Time
Range slider's own established helper — an early draft of this task
accidentally shadowed this exact function with a same-named,
worse-signature duplicate; caught via `grep`/`node --check` before
landing, never shipped, and worth recording here as a concrete example
of why "reuse the existing helper" audits matter), digital rebuild
uses the already-per-group `wwRebuildDigitalChart(groupId)`, and cursor
value refresh uses the already-per-group `wwSourceIdsForTimeGroup(groupId)`
— never the workspace-wide `wwRefetchAllChannelsAcrossGroups()`/
`wwRebuildAllTimeGroupDigitalCharts()`/`wwParticipatingSourceIds()`
batch forms (still reserved for genuinely global triggers like a Time
Mode/Unit Mode switch). `wwRefreshWorkspaceBounds()` itself is the one
call this function could not narrow further without touching that
function's own deeply-entangled primary/non-primary viewport machinery
(explicitly out of this task's own scope, per its own DEC-061
precedent for not widening into an unrelated pre-existing
architecture) — but it is already effectively self-limiting in
practice, since a manual offset change inside `groupId` can only ever
change THAT group's own derived bounds (per the topology-safety
finding above), and `wwRefreshTimeGroupViewports()`'s own internal
`wwBoundsEqual()` diff already skips re-fetching a group whose bounds
did not actually move.

Reference-source semantics are unchanged — already correctly per-group
(`app.services.synchronization_service.set_source_alignment_offset()`
already rejects a non-zero manual correction on `group_by_source_id[source_id].origin_source_id`
specifically, not any single workspace-wide reference), audited and
confirmed to require no changes (task section 4's own "preserve
existing... unless current code already has a stronger per-group
rule" — it already did, from DEC-057).

A one-source Time Group's own local button is deliberately NEVER
disabled (task section 8's own "prefer disabled if consistent with
current UX" — the former global button was NEVER disabled either, so
this preserves that exact behavior) — instead, since a Time Group's
own origin/reference is by construction always a group member
(DEC-057), a one-source group's one source IS trivially that group's
own reference, so `wwRenderSyncSourceRow()`'s existing "Reference"
branch (no editable controls, just a note) already renders the
task's own "clear nothing-to-synchronise state" automatically, with no
new disabled-gate needed.

Reason:

Section 1's own governing rule: a manual alignment control that could
reach across Time Group boundaries would let an engineer accidentally
shift a source relative to an unrelated group's own data — the same
class of correctness-critical ambiguity DEC-061/DEC-062 already closed
for Cursor A/B and t0. Section 13's own topology-safety concern is the
single most important property this task depends on; the audit above
confirms it was ALREADY structurally guaranteed by the existing
backend architecture, so this slice's own risk profile is almost
entirely a frontend UI-scoping exercise, not a backend migration.

Alternatives considered:

- A group-scoped `DELETE .../synchronization/sources?group_id=...`
  backend endpoint for Reset All — considered, rejected per task
  section 29/30's own explicit "do not create unnecessary duplicate
  endpoints... if existing source-level API remains sufficient, do not
  widen backend scope": the existing per-source DELETE, looped
  frontend-side over the group's own known membership, is already
  correct and sufficient.
- Disabling the local Sync button for a one-source group — considered,
  rejected: the former global button's own UX was never disabled-based,
  and the existing reference-only row rendering already produces an
  equally clear "nothing to synchronise" result without a new
  disabled-state mechanism to introduce and keep in sync.
- Narrowing `wwRefreshWorkspaceBounds()` itself to accept an explicit
  groupId — considered, rejected as out of this task's own scope: that
  function's primary/non-primary viewport entanglement is a separate,
  pre-existing architecture (the same one DEC-061 already declined to
  widen into for an unrelated reason); its own internal diffing already
  makes the practical effect correctly group-scoped without this
  change.

Impact:

- `frontend/index.html` only (no backend/schema/API changes — audited
  and confirmed the existing per-source/per-group-derivation backend
  architecture already fully supports this migration). New:
  `wwSyncModalGroupId`, `wwSourcesForTimeGroup()`,
  `wwSyncReloadAndRenderForGroup()`, `wwSyncApplyOffsetChangeSideEffectsForGroup()`,
  `wwSyncResetAllForGroup()`. Generalized/renamed in place:
  `wwOpenSyncModal(groupId)` (was no-arg). Removed outright: the old
  global `#wwSyncBtn` HTML/listener, `wwSyncApplyOffsetChangeSideEffects()`
  (workspace-wide form), `wwSyncResetAll()` (workspace-wide form).
- New backend test coverage (no backend code change): `test_time_grouping_service.py::TestManualSynchronizationNeverRedefinesTimeGroupMembership`
  (2 tests) locks in the topology-safety invariant explicitly, both
  behaviorally and structurally.
- Verified by the full backend suite (1718 passed, 0 failed — up from
  1688 at TG-E's own end state; 6 pre-existing frontend static-
  regression tests updated across `test_frontend_multi_source_sidebar.py`,
  `test_frontend_synchronization.py`, `test_frontend_time_groups.py`;
  30 new tests in `test_frontend_time_group_sync.py` covering the
  task's own required Cases A-T) plus a live-browser Playwright UAT
  pass covering the task's own full 26-step scenario against a running
  backend: a one-source group rendering reference-only with no
  editable controls; a second, overlapping source joining the SAME
  canvas (never creating a new one); the modal listing exactly that
  group's own 2 sources; +/-/step/Reset all confirmed source-scoped;
  Reset All confirmed group-scoped (a second, genuinely separate Time
  Group's own +6.4ms manual offset, applied afterward, survived
  untouched); cross-group source-list exclusion confirmed in both
  directions; Group 1's own t0 confirmed stable across a Sync modal
  interaction; Cursor A/B confirmed independently active in both
  groups; a Grouped/Separate layout-mode round trip preserved exactly
  one sync button per canvas; zero console/page errors throughout. One
  genuine, pre-existing (TG-D2-era, unrelated to this task)
  interaction quirk was discovered during UAT and worked around in the
  test script rather than "fixed": the cursor overlay's own hit-area
  spans the full canvas height (top:0 through the ruler), so an active
  Cursor A positioned near a toolbar button's own X coordinate can
  visually/pointer-intercept it — reported here for awareness, not
  addressed (out of this task's own scope).
- **Deferred, per the task's own explicit non-goals**: cross-Time-Group
  synchronization, automatic event matching, waveform correlation sync,
  trigger-time auto-sync, clock correction, timestamp repair, drift
  compensation, resampling, CSV/Excel, annotation redesign (still
  primary-group-scoped, unchanged), cross-group t0, and cross-group
  cursor comparison all remain unimplemented/unchanged from before this
  task. The DEC-061 pre-existing Absolute-axis layout-round-trip bug
  was not touched (this slice never needed to read `wwBuildLayout()`'s
  own tick-range logic at all). Detect Event was not changed (TG-E's
  own hidden-but-internally-group-aware state is untouched).

---

## DEC-064 — TG-G: multi-Time-Group correctness cleanup — the DEC-061 Absolute-time X-axis bug is fixed, and the cursor overlay no longer blocks Time Group toolbar controls

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("TG-G — Multi-Time-Group
correctness cleanup and remaining UI-state hardening"), delivered as
the direct successor to TG-F (DEC-063), the migration's own core slice
being complete.

Decision:

**A Time Group's rendered time axis must never borrow another Time
Group's origin, and analysis overlays must never block interaction
with the owning Time Group's toolbar.** Two priority correctness
fixes, plus a documented audit, no redesign:

**Priority issue A (DEC-061 Absolute-axis bug).** Root-caused to
`wwBuildLayout(panel, colors)`: TG-E had already threaded `groupId`
(via `wwPanelTimeGroupId(panel)`) into this function for t0-awareness,
but its own xaxis `range` and tick-format inputs still came from the
single global `ww.viewport` directly — `const xrange = ww.viewport ?
[wwElapsedToPlotlyX(groupId, ww.viewport.start), ...] : undefined`.
`ww.viewport` is only ever a given panel's own correct range when that
panel belongs to the PRIMARY Time Group; for any other group it is an
unrelated group's own numeric range, silently fed into
`wwAbsoluteTickLabelsForRange()`. This stayed latent for a normal
single-viewport render (`wwApplyAndFetchGroupViewport(groupId, ...)`
already relayouts EXISTING panels correctly, with an explicit
`groupId` and that call's own range) and surfaced specifically on a
layout-mode round trip (Grouped → Separate → Grouped), which tears
down and recreates every panel from scratch via `wwInitPanelPlot()` →
`wwBuildLayout()`. Fixed with a two-line change: `const range =
wwTimeGroupVisibleRange(groupId);` replaces the direct `ww.viewport`
reads for both `xrange` and the tick-format call. `wwTimeGroupVisibleRange()`
is not new — it already backs the ruler (`wwSyncTimeGroupRuler()`) and
the Time Range slider, and already returns `ww.viewport` verbatim for
the primary group (zero behavior change for primary-group panels) or
`ww.timeGroupViewports.get(groupId)` for any other group (the correct,
already-tracked per-group range). `wwPanelTimeGroupId(panel)` already
fails safe (`null` for a channel-less panel, never a primary-group
fallback), so no new guard was needed.

**Priority issue B (cursor overlay vs. toolbar).** The A/B cursor
overlay (`.ww-tg-cursor-overlay`, TG-D2) computed its own height as
`rulerWrapEl.offsetTop`, starting from the canvas's own top (CSS
`top: 0`) — every `.ww-cursor-line`'s own drag hit-strip
(`.ww-cursor-hit`) fills that overlay's full `top/bottom: 0` box.
Since the recently-committed sticky-toolbar patch made
`.ww-tg-sticky-top` (header + toolbar) the canvas's own first child,
the overlay's `top: 0` now started ABOVE the toolbar too, so a cursor
positioned near a toolbar button's own X coordinate could visually and
pointer-intercept it — discovered and disclosed, not fixed, during
TG-F's own UAT (see DEC-063's own Impact section). Fixed by deriving
the overlay's own `top` AND `height` from `.ww-tg-panels`'s own
`offsetTop` instead of `0`: `const panelsEl =
canvasEl.querySelector(".ww-tg-panels"); const overlayTop = panelsEl ?
panelsEl.offsetTop : 0; overlayEl.style.top = overlayTop + "px";
overlayEl.style.height = Math.max(0, rulerWrapEl.offsetTop -
overlayTop) + "px";` — the SAME `offsetTop`-based (scroll/sticky-safe,
per this function's own pre-existing comment) technique already used
for the ruler edge, just also applied to the top edge. Cursor
interaction (both the visible line and its hit-strip) now starts at
the top of the waveform content, never the toolbar. Horizontal (X)
cursor placement is untouched and structurally cannot be affected —
`wwCursorTimeToPixelX()`/`wwCursorPixelXToTime()` derive X purely from
Plotly's own page-absolute `_offset`/`_length` geometry, never the
overlay's own top/height. The separate `.ww-tg-cursor-label-layer`
(the "A"/"B" pill, sticky, offset via `--ww-tg-sticky-top-h` from the
sticky-toolbar patch) was not touched — it already excluded the
toolbar correctly.

**Audit performed** (task section 10/11/12, documented here rather
than mechanically "fixed"):

- *`ww.viewport`/`wwPrimaryTimeGroupId()` audit* (15 total call
  sites): `wwTimeGroupVisibleRange()`'s own primary-group branch,
  `wwApplyAndFetchViewport()`'s backward-compatible primary-only entry
  point, `wwRefreshTimeGroupViewports()`'s own "primary stays owned by
  the unchanged legacy path" branch, and `wwApplyAndFetchGroupViewport()`'s
  own `if (isPrimary)` cursor-overlay/peak-annotation-recalculation
  gate are all **legitimate compatibility wrappers** — each is
  explicitly documented at its own definition, and none affects
  another group's own rendered analog/ruler/digital/slider content
  (those paths are already unconditionally per-group). The hidden
  Detect Event button's own `wwOpenDetectEventModal(wwPrimaryTimeGroupId())`
  click wiring is an intentional, already-disclosed (DEC-062) primary-
  only entry point for a capability whose UI stays hidden by owner
  decision — unchanged, per task section 18's own "only adjust if a
  shared helper signature changes." `wwDiagnoseDigitalAlignment()`'s
  own `wwPrimaryTimeGroupDigitalChartEl()`/`wwPrimaryTimeGroupRulerChartEl()`
  reads are a manual DevTools-console diagnostic, never called from any
  production/UI code path — **legitimately workspace-global** (a dev
  tool, not user-facing analysis rendering).
- *Annotation scope audit* (task section 12): **actively misleading,
  not merely a limitation** — `wwWireAnalogPanelClick(panel)` is wired
  unconditionally on every panel regardless of owning group (no group
  gate), so clicking a NON-primary group's own panel while in
  Callout/Peak placement mode computes the anchor time via
  `wwPlotlyXToElapsed(wwPrimaryTimeGroupId(), point.x)` — the WRONG
  group's own t0/event-relative transform once that group (or the
  actual clicked group) has an active t0, silently anchoring the new
  annotation to the wrong elapsed time. Separately,
  `wwAnchoredAnnotationPagePosition()` computes an existing
  annotation's own page-X from `wwCursorTimeToPixelX(wwPrimaryTimeGroupId(),
  time)` (the PRIMARY group's own plot geometry) while its page-Y comes
  from `entry.panel` (the annotation's ACTUAL, possibly non-primary,
  panel) — a real X/Y geometry mismatch, not just an invisible/absent
  annotation, whenever an annotation exists on a non-primary-group
  channel. **Not fixed this slice** — annotations are an explicit
  TG-G non-goal, and the task's own instruction is to "stop and report
  before broadening scope" once this class of bug is found; needs an
  explicit owner decision on scope/priority before any fix.
- *Singleton DOM audit* (task section 11): `wwPanels`, `wwDigitalRegion`,
  `wwStickyRuler`, `wwCursorOverlay`, `wwCursorReadout`, `wwSetT0Btn`,
  `wwSyncBtn`, `wwCursorModeBtn`, `wwCursorLabelLayer` — zero real
  `getElementById(...)`/`id="..."` references remain anywhere; every
  hit is a historical comment. Confirmed fully migrated, nothing to
  fix.
- *Time Group topology lifecycle / canvas lifecycle* (task section
  13/14): re-confirmed unchanged and correct — no reproducible
  stale-state issue found, so per the task's own "only fix if
  reproducible or structurally clear," nothing was touched here.

Reason:

Both priority issues are the same class of correctness/interaction gap
DEC-061/DEC-062/DEC-063 already closed elsewhere in this migration: a
workspace-global value (`ww.viewport`) or a workspace-spanning DOM
region (the cursor overlay's own full-canvas height) silently reaching
across a Time Group boundary. The task's own governing rules ("a Time
Group's rendered time axis must never borrow another Time Group's
origin" and "analysis overlays must never block interaction with the
owning Time Group's toolbar") are now upheld structurally, not just by
convention, for both the axis-rendering and cursor-interaction paths.

Alternatives considered:

- A brand-new range-resolution helper specific to `wwBuildLayout()` —
  rejected: `wwTimeGroupVisibleRange(groupId)` already exists,
  already correctly implements the primary/non-primary split, and is
  already proven correct by the ruler's own use of it; introducing a
  second resolver would risk the two silently diverging later.
- Fixing the cursor overlay by giving it a large negative top margin or
  an arbitrary z-index below the toolbar instead of narrowing its own
  geometry — rejected per the task's own explicit "do not solve with
  an arbitrary huge z-index unless that is genuinely correct": the
  overlay's own height was already being computed dynamically
  (`rulerWrapEl.offsetTop`), so narrowing its TOP edge the same way is
  the structurally correct fix, not a z-index workaround, and it also
  correctly stops the cursor LINE from visually running through the
  toolbar, not just the hit-testing.
- Fixing the newly-found annotation cross-group-anchoring issue inline
  as a "small, unavoidable correctness fix" — considered, rejected:
  the task's own explicit instruction for this exact scenario ("If
  annotations can appear incorrectly on another Time Group, stop and
  report before broadening scope") takes precedence; reported here
  instead, pending an owner decision.

Impact:

- `frontend/index.html` only (no backend/schema/API changes). Changed
  in place: `wwBuildLayout(panel, colors)` (range source only — no
  signature change), `wwUpdateCursorOverlayForGroup(groupId)` (overlay
  top/height derivation only — no signature change). No new module-
  level state, no new singleton DOM, no new scroll listeners.
- New test file `test_frontend_time_group_layout.py` (13 tests, Cases
  A-M plus the singleton-DOM audit assertion). Updated:
  `test_frontend_time_group_t0.py` (2 pre-existing assertions widened
  to match `wwBuildLayout()`'s own longer body and to assert the new
  `wwTimeGroupVisibleRange(groupId)` call instead of the old direct
  `ww.viewport` read).
- Verified by the full backend suite (1731 passed, 0 failed — up from
  1718 at TG-F's own end state) plus a live-browser Playwright UAT
  pass using two Time Groups on genuinely different dates (27 Jan 2026
  vs 02 Feb 2026, non-overlapping): Cases A-G (Absolute-axis
  correctness — initial render, Grouped→Separate→Grouped,
  Grouped→Custom→Grouped, 3x repeated round trips, zoom/reset on the
  non-primary group, t0 set/clear, Sync modal open/close — read
  directly from Plotly's own `_fullLayout.xaxis.ticktext`, not just
  the header) and Cases H-M (cursor/toolbar interaction — toolbar
  clickable with cursor mode on, Zoom/Sync/t0 clickable with a cursor
  line placed directly under each button's own X, sticky-toolbar
  controls clickable while scrolled, cursor dragging in the waveform
  region unaffected, cursor label offset still tracks
  `--ww-tg-sticky-top-h`) all passed, zero console/page errors
  throughout.
- **Deferred, per the task's own explicit non-goals**: Time Group
  collapse, cross-group synchronization/cursor comparison/t0, Detect
  Event UI exposure, CSV/Excel, automatic event matching, clock
  correction, waveform correlation, and any new analysis feature all
  remain unimplemented/unchanged from before this task. **Flagged, not
  fixed, pending an owner decision**: the annotation cross-group-
  anchoring/reprojection finding above (`wwWireAnalogPanelClick()`'s
  Callout anchor time and `wwAnchoredAnnotationPagePosition()`'s own
  page-X, both still `wwPrimaryTimeGroupId()`-scoped regardless of
  which group's panel an annotation actually belongs to).

---

## DEC-065 — TG-H: per-Time-Group annotation placement/anchoring/reprojection — annotations resolve their own owning Time Group dynamically from source/channel ownership, never wwPrimaryTimeGroupId()

Date: 2026-08-29
Status: Approved
Source: explicit project-owner instruction ("TG-H — Per-Time-Group
Annotation Placement and Reprojection"), delivered as the direct
successor to TG-G (DEC-064), which had flagged this exact cross-group
annotation defect during its own audit but explicitly deferred fixing
it, pending an owner decision.

Decision:

**An annotation must always use the time transform and plot geometry
of the panel and Time Group it actually belongs to — never the
primary Time Group by default.** `groupId` is derived FRESH, every
call, from the annotation's own already-stable `data.sourceId` (via
`wwTimeGroupIdForDisplaySourceId()`) — never stored on the annotation
and never `wwPrimaryTimeGroupId()`. This was a deliberate audit
finding (task section 6/19): the annotation data model already carries
enough ownership information (`sourceId`/`channelName`) to resolve its
current Time Group unambiguously at any time, including after a
merge/split changes which derived group id a source belongs to — so no
new stored field was added, and no annotation schema change was
needed.

Two problems named by the task, plus a third discovered during this
slice's own audit, all fixed by threading the CLICKED/OWNING panel's
own `groupId` through instead of `wwPrimaryTimeGroupId()`:

- **Problem A (placement)**: `wwWireAnalogPanelClick(panel)`'s Callout
  branch converted the click's own Plotly X via
  `wwPlotlyXToElapsed(wwPrimaryTimeGroupId(), point.x)` — wrong
  whenever the clicked panel's own group differs from primary AND
  either group has an active t0 (the search-seed sent to the backend's
  nearest-sample resolver, not merely a display value, so this could
  silently anchor to the wrong physical sample). Fixed:
  `wwPlotlyXToElapsed(wwPanelTimeGroupId(panel), point.x)`.
  `wwCreatePeakFromClick(panel, channel, mode)` had the same class of
  bug for Peak placement's own search RANGE — it used the single
  global `ww.viewport.start/end` unconditionally (`if (!ww.viewport)
  return;`), never the clicked panel's own group. Fixed:
  `wwTimeGroupVisibleRange(wwPanelTimeGroupId(panel))` supplies
  `startTime`/`endTime` instead.
- **Problem B (reprojection)**: `wwAnchoredAnnotationPagePosition(annotation)`
  computed page-X via `wwCursorTimeToPixelX(wwPrimaryTimeGroupId(),
  time)` while page-Y always came from `entry.panel` (the annotation's
  ACTUAL, possibly non-primary, panel) — a real X/Y geometry mismatch
  whenever an annotation belonged to a non-primary group. Fixed: both
  the `inViewport` range check and the X projection now resolve
  through the SAME `groupId` (derived from `data.sourceId`), so X and
  Y structurally can never disagree about which group/panel they
  belong to.
- **Peak recalculation-on-viewport-change (found during this slice's
  own audit, same root class as Problem A)**: `wwRecalculateAllPeakAnnotations(startTime,
  endTime)` recalculated EVERY Peak annotation in the workspace using
  ONE shared range, called only from `wwApplyAndFetchGroupViewport()`'s
  own `if (isPrimary)` branch — meaning a non-primary group's own
  Peak never recalculated on its own zoom/pan/reset at all. Fixed:
  `wwRecalculateAllPeakAnnotations(groupId, startTime, endTime)` now
  requires an explicit `groupId`, filters to only that group's own
  Peak annotations (via `wwTimeGroupIdForDisplaySourceId(data.sourceId)
  !== groupId` exclusion), and is called unconditionally (moved out of
  the `if (isPrimary)` block) with whichever group's viewport just
  changed.
- **Absolute-mode display TEXT (found during this slice's own audit,
  same root class)**: `wwAnnotationMetaLine()`/`wwPeakLabelLines()`
  called `wwFormatAbsoluteElapsedTime(elapsedSeconds)` with no
  `opts.groupId` at all — the underlying stored anchor time was
  already correct (Problem A's own fix), but the DISPLAYED Absolute-
  time text for a non-first-displayed-channel's annotation fell back
  to `wwWorkspaceRecordingStartMs()`'s own "first channel in display
  order" origin, not that annotation's own group's origin. Fixed: both
  now pass `{ groupId, spanSeconds: wwVisibleSpanSeconds(groupId) }`.
- **Callout anchor drag-to-reposition (found during this slice's own
  audit — not merely primary-scoped, a complete pre-existing no-op
  bug)**: `wwWireCalloutAnchorDrag()`'s own `onPointerDown` called
  `wwCursorPlotMetrics()` with NO arguments at all (`groupId` stayed
  `undefined`, which can never match any real group id), and
  `onPointerUp` called `wwCursorPixelXToTime(event.clientX,
  dragMetrics)` — a pixel value in the `groupId` slot and the metrics
  object in the `pageX` slot. Both silently resolved to `null`/no
  match every time, so dragging a Callout's anchor marker to reposition
  it was a complete no-op (always snapped back), regardless of Time
  Groups, predating this slice. Fixed by resolving `dragGroupId =
  wwTimeGroupIdForDisplaySourceId(annotation.data.sourceId)` once at
  pointerdown (the dragged annotation is already resolved there) and
  threading it through both calls — the same "derive fresh from
  source/channel ownership" pattern as everywhere else this slice.

Reason:

Section 2's own governing principle: every anchored annotation belongs
unambiguously to Time Group → Panel → Channel/source → Anchor
time/value, and its time conversion/pixel projection must use that
SAME Time Group/panel, never borrow the primary Time Group's. This is
the exact same class of correctness gap DEC-061 (Absolute-axis)/DEC-064
(cursor overlay) already closed elsewhere in this migration, now
closed for the one remaining annotation surface.

Alternatives considered:

- Storing an explicit `groupId` field on each annotation at creation
  time, updated on merge/split — considered, rejected per the task's
  own section 6/19 explicit guidance: Time Group ids are themselves
  derived/dynamic and can change after a merge/split; a STORED groupId
  would need active invalidation/re-resolution logic to stay correct,
  while deriving it fresh from the already-stable `sourceId` on every
  render is simpler, always correct by construction, and needs no
  merge/split-specific annotation code at all.
- A per-Time-Group annotation overlay/drawer — explicitly rejected by
  the task's own non-goals (section 27); the existing single global
  `#wwAnnotationOverlayMain`/`#wwAnnotationDrawer` already renders each
  annotation's own CORRECT position once the per-annotation group
  resolution above is in place (task section 16's own "a global overlay
  is acceptable only if every annotation's page position is computed
  from its own correct group/panel geometry" — now true).
- Fixing only Problems A/B as literally named by the task and leaving
  the Peak-recalculation/display-text/drag-anchor bugs found during
  this slice's own audit unaddressed — considered, rejected: all three
  are the exact same root defect (annotation code reading
  `wwPrimaryTimeGroupId()`/no groupId/the global `ww.viewport` instead
  of resolving the annotation's own group), directly within this
  task's own explicit framing ("make annotation creation, anchoring,
  rendering, and reprojection use the annotation's own Time Group and
  panel geometry"), not a scope expansion into a new feature area.
- Fixing the general (non-annotation) trace-hover-tooltip gap
  (`wwTraceCustomData()` also omits `groupId` from its own
  `wwFormatAbsoluteElapsedTime()` call) alongside the annotation
  display-text fix above, since both share the same root helper —
  considered, rejected as genuinely out of this task's own scope (a
  waveform hover tooltip, not an annotation); reported here for
  awareness, not fixed.

Impact:

- `frontend/index.html` only (no backend/schema/API changes —
  audited and confirmed the existing per-source `annotation-anchor`/
  `peak-values` backend endpoints already resolve purely from
  `sourceId`/`channel_name`, with no Time Group concept at all, so
  nothing there needed to change). Changed in place (no signature
  change unless noted): `wwWireAnalogPanelClick()`,
  `wwCreatePeakFromClick()`, `wwAnchoredAnnotationPagePosition()`,
  `wwAnnotationMetaLine()`, `wwPeakLabelLines()`,
  `wwWireCalloutAnchorDrag()`. Signature changed:
  `wwRecalculateAllPeakAnnotations(startTime, endTime)` →
  `wwRecalculateAllPeakAnnotations(groupId, startTime, endTime)` (one
  call site, in `wwApplyAndFetchGroupViewport()`, updated to match and
  moved out of its own `if (isPrimary)` gate). No new module-level
  state, no new singleton DOM, no new scroll listeners, no annotation
  schema change.
- New test file `test_frontend_time_group_annotations.py` (18 tests,
  Cases A-O). Updated: `test_frontend_time_group_cursors.py` (the
  former `TestAnnotationProjectionExplicitlyStaysPrimaryGroupScoped`
  class, which asserted the OLD primary-scoped behavior, now asserts
  the reversal; one window-size widen), `test_frontend_time_group_toolbar.py`
  and `test_frontend_time_range_slider.py` (both had a duplicate
  assertion of `wwApplyAndFetchGroupViewport()`'s own old
  primary-gated peak-annotation-recalculation shape, updated to match
  the new unconditional, per-group shape), `test_frontend_time_group_layout.py`
  (one window-size widen only, no assertion change, to accommodate a
  longer in-place comment).
- Verified by the full backend suite (1749 passed, 0 failed — up from
  1731 at TG-G's own end state) plus a live-browser Playwright UAT
  pass using the same two genuinely-different-date Time Groups as
  TG-G's own UAT (27 Jan 2026 vs 02 Feb 2026, non-overlapping): a
  Callout placed in each group resolved to its own correct group
  (verified via `wwTimeGroupIdForDisplaySourceId`, not screen
  position); both callouts stayed visibly positioned through different
  t0 values set in each group, an Absolute→Elapsed→Absolute switch
  (stored anchor value byte-identical throughout both), Group 2's own
  zoom+reset (Group 1's own callout position provably unchanged, exact
  DOM style comparison), a Grouped→Separate→Grouped round trip, and a
  Custom-layout excursion (group ownership unchanged throughout); a
  +Peak annotation placed in Group 2 correctly resolved to Group 2 and
  rendered its own group's correct Absolute-time text (screenshot:
  "+Peak: 900.0 V, t = 13:00:40.00225", Group 2's own origin, not
  Group 1's 13:09:40); the sticky toolbar's own Autoscale button
  confirmed via `document.elementFromPoint()` to be the actual top
  hit-test target with annotations present and the toolbar stuck
  (no z-index/overlay-interception regression, despite
  `.ww-annotation-overlay`'s own z-index:15 nominally exceeding
  `.ww-tg-sticky-top`'s z-index:5 — its pre-existing `pointer-events:
  none` container already prevents interception, confirmed rather than
  assumed); Cursor A dragging in the waveform region confirmed
  unaffected; zero console/page errors throughout.
- **Discovered during this slice's own audit, reported here per the
  project's own change-governance requirement rather than silently
  fixed, and explicitly NOT fixed (out of this task's own scope, a
  general waveform hover tooltip, not an annotation)**:
  `wwTraceCustomData(channel)` (used for the Absolute-mode hover-
  tooltip text on every analog trace) already resolves its own
  `groupId` locally but never passes it to its own
  `wwFormatAbsoluteElapsedTime()` call — the SAME class of "falls back
  to the first-displayed-channel's own origin" gap this slice fixed
  for annotation display text, but for hover tooltips instead. A
  future slice should thread `groupId` through that one call site the
  same way.
- **Deferred, per the task's own explicit non-goals**: Time Group
  collapse, cross-group synchronization/cursor comparison/t0, Detect
  Event UI exposure, a per-Time-Group annotation drawer, new
  annotation types, CSV/Excel, automatic event matching, clock
  correction, waveform correlation, and any new analysis feature all
  remain unimplemented/unchanged from before this task. Synchronise
  Sources' own manual-offset/timestamp-placement semantics were
  audited and confirmed to need no change (annotations already resolve
  their own owning group's current source/time mapping dynamically,
  never a stored group reference, so a manual sync offset inside one
  group can never affect another group's own annotations).

---

## DEC-066 — A/B cursor readout relocated from the top toolbar row to the bottom sticky stack, per Time Group

Date: 2026-08-29
Status: Approved
Source: explicit project-owner UX instruction ("move the A/B cursor
readout summary from the top-right Time Group header area to the
bottom sticky time-axis area of each Time Group Canvas").

Decision:

**Pure DOM-placement/CSS migration — no cursor engineering change.**
`.ww-tg-cursor-readout` moved in `wwCreateTimeGroupCanvasDom(groupId)`'s
own template from a flex item inside `.ww-tg-toolbar-row` (top sticky
area) to a new tier in the bottom sticky stack, in DOM order between
`.ww-tg-slider-slot` and `.ww-tg-ruler` (slider → readout → ruler, per
the owner's own preferred order). The element, its classes, and
`wwUpdateCursorOverlayForGroup(groupId)`'s own read/write path
(`canvasEl.querySelector(".ww-tg-cursor-readout")`, the a/b/delta value
computation, the `hidden` toggle) are byte-for-byte unchanged — only
its position in the template moved, so there was never a second
render path or duplicate element to introduce.

The readout became a third `position: sticky` sibling in the existing
bottom dock (previously two: slider-slot + ruler). `wwSyncTimeGroupCanvasStickyOffset(groupId)`
(the same existing runtime-measurement helper already computing the
slider's own `bottom` from the ruler's live rendered height) was
extended to also measure the readout's own live height and set its own
`bottom` to the ruler's height, then fold both into the slider's own
`bottom` (ruler height + readout height) — the exact same
"never a hardcoded pixel guess, correct even if a sibling's height
changes" technique already established for the ruler/slider pair, now
covering three tiers. Since a `[hidden]` (display:none) element's
`getBoundingClientRect()` returns 0, this naturally collapses back to
the original two-tier offset whenever cursor mode is off, with no
separate visibility branch needed. z-index: ruler=4 (unchanged),
readout=3 (new), slider=2 (down from 3, now the outermost of three
non-overlapping tiers — defensive only, correct `bottom` values already
prevent any visual overlap).

Reason:

Owner UX judgment: the readout is measurement/analysis output tied to
the cursor markers, slider, and ruler — all part of the bottom
time-axis region — not a toolbar control, so it reads more naturally
grouped with them than pinned to the top control row.

Alternatives considered:

- A new shared sticky wrapper spanning slider+readout+ruler (mirroring
  `.ww-tg-sticky-top`'s own header+toolbar wrapper pattern) — rejected:
  the existing bottom dock is deliberately THREE separate sticky
  siblings, not one wrapper, specifically so the ruler keeps its own
  `offsetParent` (the canvas root) for the cursor-overlay height fix
  (Phase 4B-UAT2) — wrapping would have silently broken that; adding a
  third sibling with its own runtime-measured offset preserves it.
- A new scroll listener to reposition the readout — rejected as
  unnecessary; the existing `position: sticky` + JS-measured `bottom`
  approach (already proven for the ruler/slider) required no scroll
  listener before and needed none now.

Impact:

- `frontend/index.html` only (no backend changes). Changed in place:
  `wwCreateTimeGroupCanvasDom()` (template reorder only — no new/
  removed elements), `wwSyncTimeGroupCanvasStickyOffset()` (readout
  height folded into the existing offset calc). CSS: `.ww-tg-cursor-readout`'s
  outer container restyled for the bottom-stack context (position/
  bottom/z-index/background/border/justify-content) — its own inner
  item/label/value rules (including the owner's own manually-set
  `padding: 6px 10px` on `.ww-tg-cursor-readout-item`, font-size, and
  the A-blue/B-red color convention) are byte-for-byte unchanged.
  `.ww-tg-slider-slot`'s own z-index dropped 3→2 to make room.
- New test file `test_frontend_time_group_cursor_readout_placement.py`
  (12 tests, Cases A-H); one pre-existing file updated
  (`test_frontend_time_range_slider.py`, two assertions matching the
  new z-index/offset-calc shape).
- Verified by the full backend suite (1761 passed, 0 failed — up from
  1749 before this task) plus a live-browser Playwright UAT pass:
  readout confirmed absent from the top sticky region and present in
  the bottom stack (DOM order slider < readout < ruler, `position:
  sticky`, gap-free — exact pixel-adjacent `y`+`height` checks);
  dragging Cursor A/B updated the readout live; scrolling within a tall
  Time Group kept the readout visible and gap-free against slider/
  ruler; two Time Groups each showed exactly one independent readout
  (moving Group 2's own cursors left Group 1's own readout values
  byte-identical); a Grouped→Separate→Custom→Grouped layout sweep
  produced exactly 2 readout elements total (no duplication); a narrow
  (760px) viewport showed no horizontal overflow with the readout and
  toolbar both still visible; zero console/page errors throughout.
- **Deferred, per the task's own explicit non-goals**: any cursor
  calculation/redesign, annotation changes, Time Group collapse, the
  hover-tooltip cleanup (DEC-065's own deferred finding), cross-group
  cursor comparison/t0, Synchronise Sources changes, Detect Event
  changes, and CSV/Excel all remain unimplemented/unchanged from before
  this task.

---

## DEC-067 — Bugfix: the bottom sticky stack (Time Range slider + A-B cursor readout) becomes ONE shared sticky wrapper, replacing three independent sticky siblings

Date: 2026-08-29
Status: Approved
Source: owner manual UAT of commit `eb55528` ("fix: move cursor readout
to sticky time axis") — the readout was correctly relocated into the
bottom dock but was NOT actually sticky while scrolling.

Decision:

**Root cause**: DEC-066's own implementation used THREE independent
`position: sticky` siblings (`.ww-tg-slider-slot`, `.ww-tg-cursor-readout`,
`.ww-tg-ruler`), with `wwSyncTimeGroupCanvasStickyOffset()` measuring
the readout's own live height via `getBoundingClientRect()` and folding
it into the slider's own `bottom`. That measurement is only ever as
fresh as the last time the sync function happened to run. Live
Playwright reproduction (headless Chromium) confirmed the readout's own
computed `position`/`bottom` were reported correctly by
`getComputedStyle()` in isolation, yet its own rendered position still
drifted with scroll once real multi-Time-Group layout activity was
introduced — consistent with a stale/late height read that nothing
re-corrected before the user scrolled, not a missing/invalid CSS
property.

**Fix**: `.ww-tg-slider-slot` and `.ww-tg-cursor-readout` are now
normal-flow children of ONE new shared wrapper, `.ww-tg-sticky-bottom`
(mirroring `.ww-tg-sticky-top`'s own established header+toolbar
pattern). The wrapper's own height — and therefore its own correctly
stuck position — is computed by the BROWSER via ordinary block layout,
never JS-measured, structurally eliminating the exact class of
staleness that broke the three-sibling design. `wwSyncTimeGroupCanvasStickyOffset()`
now sets exactly ONE JS-computed value (the wrapper's own `bottom` =
the ruler's own live height) instead of two (the old readout `bottom`
and the folded slider `bottom`).

`.ww-tg-ruler` deliberately stays OUTSIDE the new wrapper, an
independent sticky sibling exactly as before -- wrapping it too would
move its own `offsetTop` to be relative to the new wrapper instead of
the canvas root, breaking `wwUpdateCursorOverlayForGroup()`'s own
`rulerWrapEl.offsetTop`-based cursor-overlay height calculation
(Phase 4B-UAT2's own established fix) — this was audited first and is
explicitly why the fix does not wrap all three elements into one.

Reason:

The task's own governing rule: "The A/B cursor readout must remain
visibly sticky together with the Time Group's bottom time-axis stack
while scrolling through that Time Group." A structural fix (let the
browser compute the wrapper's own height) is more robust against this
exact class of staleness than adding more JS synchronization calls to
chase it, and was the task's own explicitly preferred direction once
three independent sticky siblings proved unreliable.

Alternatives considered:

- Wrapping all three (slider + readout + ruler) into one wrapper —
  rejected: breaks the ruler's own `offsetTop`-relative-to-canvas
  contract the cursor-overlay height calculation depends on (audited
  and confirmed via code inspection before implementing either option).
- Keeping three independent siblings and hardening the height
  measurement with a `ResizeObserver` on the ruler/readout elements —
  considered as a belt-and-suspenders addition; not implemented after
  live UAT showed the wrapper fix alone held rock-solid across repeated
  runs of the exact scenario (two Time Groups, Grouped layout mode)
  that previously reproduced the drift — adding an observer would have
  been unnecessary complexity for an already-resolved root cause.

Impact:

- `frontend/index.html` only. Changed in place:
  `wwCreateTimeGroupCanvasDom()` (slider-slot + cursor-readout now
  nested inside a new `.ww-tg-sticky-bottom` wrapper div; ruler
  markup/position unchanged), `wwSyncTimeGroupCanvasStickyOffset()`
  (sets the wrapper's own `bottom` only). CSS: `.ww-tg-sticky-bottom`
  is new (`position: sticky`, `z-index: 3`, `background: var(--panel)`);
  `.ww-tg-slider-slot:not(:empty)` and `.ww-tg-cursor-readout` both lost
  their own `position: sticky`/`z-index`/`background` (now inherited
  from the wrapper) but kept their own `border-top` divider and every
  owner-set value (item padding `6px 10px`, `font-size: 0.65rem`, the
  A-blue/B-red color convention) byte-for-byte unchanged.
- Test file `test_frontend_time_group_cursor_readout_placement.py`
  extended with a new `TestStickyBottomWrapperBugfix` class (Cases
  A/C/D/E/H/I plus offset-sync-call-site and no-new-scroll-listener
  checks); `test_frontend_time_range_slider.py` updated for the new
  wrapper-owns-stickiness shape (3 assertions replaced/added).
- Verified by the full backend suite (1771 passed, 0 failed — up from
  1761 before this bugfix) plus repeated live-browser Playwright UAT
  runs (3x consecutive, same scenario) against a genuinely tall
  (19-analog-channel) Time Group: the sticky wrapper's own `y` position
  stayed pinned to the SAME pixel value across every sampled scroll
  position strictly within Group 1's own bounds, in every run —
  contrasting sharply with the OLD three-sibling design, which visibly
  drifted (`readoutTop` continuously changing with scroll) in the exact
  same two-Time-Group/Grouped-layout scenario before this fix. Slider/
  readout/ruler confirmed gap-free (adjacent `top`/`bottom` values
  within 1px) at every sampled point; disabling cursor mode collapsed
  the stack to slider-directly-above-ruler with no gap; re-enabling
  restored the 3-tier stack immediately; a narrow (760px) viewport kept
  the stack gap-free with no horizontal overflow; the top sticky
  toolbar remained clickable throughout; two-Time-Group handoff
  confirmed clean (Group 1 released, Group 2 took over, no overlap);
  zero console/page errors throughout.
- **Deferred**: none new — this is a scoped bugfix on top of DEC-066,
  same non-goals apply (cursor calculation/redesign, annotations, Time
  Group collapse, the hover-tooltip cleanup, cross-group cursor/t0,
  Synchronise Sources, Detect Event, CSV/Excel).

---

## DEC-068 — Owner UX correction: numerical A-B/Δt readout returns to the top toolbar row; A/B position badges move into the ruler's own DOM subtree

Date: 2026-08-30
Status: Approved
Source: explicit owner reconsideration, delivered after DEC-066/DEC-067
("the bottom sticky behavior has proven more complex and fragile than
expected... restore the numerical Cursor A/B/ΔT readout to the top
Time Group control area... keep the small A/B position badges at the
bottom attached to the sticky ruler/time-axis region").

Decision:

**Two elements, two different established sticky mechanisms, each
reused as-is rather than building anything new.**

`.ww-tg-cursor-readout` (the numerical "A / B / Δt" summary) moves back
into `.ww-tg-toolbar-row`, its pre-DEC-066 home, as that row's own
right-hand flex item. It now inherits `.ww-tg-sticky-top`'s own
already-proven sticky/bounded-handoff behavior automatically — no new
sticky logic of its own. `.ww-tg-sticky-bottom` (introduced by DEC-067)
is KEPT, not reverted, now wrapping only `.ww-tg-slider-slot` — per the
task's own explicit "do not remove it blindly if it now provides
useful stable slider behavior," it remains the more robust design
(browser-computed wrapper height) even with only one child.

The small "[A ×]"/"[B ×]" position-badge pills (`.ww-cursor-label`,
inside `.ww-tg-cursor-label-layer`) move from being an INDEPENDENT
top-sticky sibling of `.ww-tg-cursor-overlay` into `.ww-tg-ruler`'s own
DOM subtree — a sibling of `.ww-cursor-ruler-overlay`/
`.ww-tg-ruler-chart`. They no longer declare their own `position:
sticky` at all; being a descendant of the already-sticky `.ww-tg-ruler`
is sufficient for them to move/release/hand-off in lockstep with it,
one level of nesting deeper than the ruler's own established (and
otherwise untouched) sticky mechanism. `.ww-tg-ruler` deliberately
stays a sibling of `.ww-tg-sticky-bottom` (never wrapped together with
it or with the badge layer moved anywhere else): DEC-067 already
established why wrapping the ruler breaks
`wwUpdateCursorOverlayForGroup()`'s own `rulerWrapEl.offsetTop`-based
cursor-overlay height calculation, and that reasoning is unchanged.

**X-projection**: since the badge layer's own coordinate-space
reference changed (from the workspace section's own left edge to the
ruler's own left edge), `labelEl.style.left` now reads `(pageX -
rulerRect.left)` at all three call sites (`livePositionUpdate()`'s live
drag update, and both the A/B loop and the "suggested event" marker
inside `wwUpdateCursorOverlayForGroup()`) — the EXACT SAME conversion
`.ww-cursor-ruler-stroke` (the ruler's own thin colored tick mark) was
already using, not a new formula. `wwCursorTimeToPixelX(groupId, time)`
remains the one shared page-X authority everywhere; only the per-
element coordinate-space subtraction changed for this one element.

Dead code removed: `--ww-tg-sticky-top-h`, the CSS custom property
`.ww-tg-sticky-top`'s own JS-measured height used to publish
specifically so the (formerly top-sticky) label layer's own `top: calc(...)`
could avoid rendering underneath the header/toolbar — with the label
layer no longer living there at all, this had no remaining consumer
and was removed from both its JS publisher
(`wwSyncTimeGroupCanvasStickyOffset()`) and its own (now-deleted) CSS
consumer.

Reason:

Owner's own governing rule, verbatim: "Numerical A/B/ΔT values belong
in the proven sticky top Time Group control area, while the small A/B
position badges belong to the sticky ruler/time-axis layer." Both
halves of this correction deliberately AVOID inventing a third sticky
mechanism — the readout reuses the top wrapper's own proven behavior,
the badges reuse the ruler's own proven behavior, closing the exact
"another independent sticky sibling" fragility class DEC-066/DEC-067
already fought once.

Alternatives considered:

- Reverting `.ww-tg-sticky-bottom` back to a bare, independently-sticky
  `.ww-tg-slider-slot` now that it wraps only one child — considered,
  rejected per the task's own explicit "inspect carefully whether it
  should be simplified... do not remove it blindly": the wrapper's own
  browser-computed-height property is still strictly more robust than
  a JS-measured one, at zero extra cost now that it wraps a single
  child, so keeping it is both simpler (smaller diff) and safer.
- Interpreting "A/B position badges" as the pre-existing
  `.ww-cursor-ruler-stroke` marks (already ruler-owned, zero code
  changes needed) rather than the `.ww-cursor-label` pills — considered
  and explicitly ruled out by the owner when asked to disambiguate
  (mid-task clarifying question): the pills are the intended target,
  confirmed to require an actual DOM-ownership change, not merely
  verification.
- Nesting the badge layer inside `.ww-cursor-ruler-overlay` (which
  already holds the stroke marks) instead of as ITS OWN sibling
  directly inside `.ww-tg-ruler` — considered, rejected: the two serve
  different purposes (display-only stroke marks vs. draggable/closable
  interactive pills with their own `pointer-events: auto` opt-in), and
  the task's own target diagram shows the badge layer as a direct
  `.ww-tg-ruler` child, a peer of the ruler-overlay, not nested inside
  it.

Impact:

- `frontend/index.html` only (no backend changes). Changed in place:
  `wwCreateTimeGroupCanvasDom()` (readout markup moved into
  `.ww-tg-toolbar-row`; label-layer markup moved into `.ww-tg-ruler`'s
  own template), `wwSyncTimeGroupCanvasStickyOffset()` (dead
  `--ww-tg-sticky-top-h` publisher removed), `livePositionUpdate()` and
  `wwUpdateCursorOverlayForGroup()` (three `labelEl.style.left` call
  sites switched from `sectionRect.left` to `rulerRect.left`). CSS:
  `.ww-tg-cursor-readout` restored to a toolbar-row flex-item shape
  (`margin-left: auto`, no `position`/`border-top`/`background` of its
  own); `.ww-tg-cursor-label-layer` changed from `position: sticky; top:
  calc(var(--ww-tg-sticky-top-h, 0px) + 6px)` to `position: absolute;
  top: -20px` (empirically tuned via live screenshot inspection to sit
  just above the ruler's own tick labels with no overlap). Every
  owner-set value (readout item padding `6px 10px`, font-size
  `0.65rem`, A-blue/B-red color rules on both the readout and the
  badges, `.ww-tg-ruler`'s own `padding: 2px 14px` and the owner's
  recent `height: 30px` ruler-chart edit) is byte-for-byte unchanged —
  confirmed via `git diff` grep, only relocated.
- Test file `test_frontend_time_group_cursor_readout_placement.py`
  rewritten for the new architecture (Cases A-J per this task's own
  section 20); `test_frontend_time_group_layout.py` updated (one
  TG-G-era test's own now-obsolete `--ww-tg-sticky-top-h` assertion
  replaced).
- Verified by the full backend suite (1776 passed, 0 failed — up from
  1771 before this task) plus a live-browser Playwright UAT pass with
  a genuinely tall (19-analog-channel) Time Group: the numerical
  readout confirmed inside `.ww-tg-sticky-top`, staying pinned together
  with the toolbar across the whole scroll range; the badge layer
  confirmed nested inside `.ww-tg-ruler`; dragging both cursors updated
  the top readout and moved both badges in exact horizontal lockstep
  with their own cursor lines (verified via a coordinate-offset
  comparison, not raw equality, since the two now live in different
  coordinate spaces that happen to share the same origin in this
  layout); zoom/reset/t0 set-clear completed without error; two Time
  Groups showed fully independent readouts/badges (moving Group 2's
  own cursor left Group 1's own readout byte-identical); exactly one
  readout and one badge layer per group survived a Grouped→Separate→
  Custom→Grouped sweep; a narrow (760px) viewport kept both elements
  visible with no horizontal overflow; zero console/page errors
  throughout. Screenshots confirm the badges read cleanly as
  time-axis-attached position markers with no ruler tick-label
  overlap.
- **Deferred**: none new — same non-goals as DEC-066/DEC-067 (cursor
  calculation/redesign, annotation changes, Time Group collapse, the
  hover-tooltip cleanup, cross-group cursor/t0/Sync, Detect Event,
  CSV/Excel).

## DEC-069 — TG-FINAL: Time Group architecture migration is declared complete — the deferred hover-tooltip Absolute-time gap is fixed, and a full primary-group/`ww.viewport`/`ww.workspaceBounds`/singleton-DOM/state-lifecycle audit finds no remaining active correctness defects

Date: 2026-08-30
Status: Approved
Source: owner-requested closure audit ("TG-FINAL — Time Group Architecture
Closure Audit"), following owner UAT passing across every prior Time
Group slice (TG-A through TG-H, DEC-057 through DEC-068).

Decision:

**One real, active correctness bug found and fixed; every other audited
surface confirmed either intentionally workspace-global/compatibility
or already correctly per-group.**

`[FACT]` `wwTraceCustomData()` (the Absolute-mode hover-tooltip text
generator for every waveform trace) computed its own `groupId` via
`wwTimeGroupIdForDisplaySourceId(channel.sourceId)` but used it ONLY to
gate `wwHasT0(groupId)` — it never passed `groupId` through to
`wwFormatAbsoluteElapsedTime()`, so the hover text's actual wall-clock
origin fell back to `wwWorkspaceRecordingStartMs()` (the FIRST
displayed-channel-overall origin, iteration-order dependent), not this
channel's own group's origin. This was the single remaining call site
of `wwFormatAbsoluteElapsedTime()` in the entire file that omitted
`groupId` — axis ticks, annotations (fixed by DEC-065), and the cursor
readout already passed it correctly. Proven live (two Time Groups, 27
Jan 2026 and 02 Feb 2026): before the fix this would have shown the
non-primary group's hover date as "13:09:40" (Group 1's own origin)
instead of its own correct "13:00:40" — a genuinely wrong Absolute
wall-clock value shown to the engineer, not a cosmetic/missing-context
gap as the DEC-065 deferral had left ambiguous. Fixed minimally:
`wwTraceCustomData()` now resolves `wwVisibleSpanSeconds(groupId)` and
passes `{ groupId, spanSeconds: span }` through, matching every other
call site. A stale `wwFormatAbsoluteElapsedTime()` header comment
claiming "hover templates, annotations" still omit `groupId` was
corrected in place (documentation-only, no functional change) — that
claim was already false for annotations since DEC-065 and is now false
for hover text too.

`[FACT]` A second, unrelated stale HTML comment was found and
corrected: the static markup directly above `#wwTimeGroupCanvases`
still claimed Cursor A/B "remain workspace-global and OUTSIDE any
single canvas... a known, disclosed limitation" — this was true before
TG-D2 (DEC-061) but has been false, and directly contradicted by the
TG-D2 comment immediately above it in the same file, since that slice
landed. Corrected in place; no functional change (Cursor A/B has been
genuinely per-Time-Group since DEC-061).

`[FACT]` Full audit results (see the session's own closure report for
full per-item detail):

- **`wwPrimaryTimeGroupId()`** — 6 real call sites (`wwPrimaryTimeGroupCanvasEl()`,
  `wwRefreshTimeGroupViewports()`'s own primary-skip, `wwApplyAndFetchGroupViewport()`'s
  own `isPrimary` mirror-gate, `wwApplyAndFetchViewport()`'s own explicit
  backward-compatible entry point, `wwTimeGroupVisibleRange()`'s own
  primary-mirrors-`ww.viewport` branch, and the hidden/disabled Detect
  Event button's own explicit primary-group resolution). Every one is
  either category A (legitimate, disclosed workspace-global/compatibility
  mirror — `ww.viewport` IS the primary group's own viewport by
  construction, never a silently-wrong fallback for a non-primary group)
  or category B (a currently-hidden, zero-user-facing-impact global
  control, `WW_DETECT_EVENT_UI_ENABLED = false`). No category C found.
- **`ww.viewport`** — every direct read/write audited (workspace-bounds
  refresh, span-seconds fallback, tick-format fallback, initial-channel-
  fetch default, cross-group refetch fallback, reset/clear logic, the
  primary-mirror in `wwTimeGroupVisibleRange()`). All are either the
  intentional primary-group mirror or a documented, self-correcting
  transient fallback (a brand-new non-primary group's very first fetch
  may briefly use the current primary viewport as a default range before
  `wwRefreshWorkspaceBounds()` → `wwRefreshTimeGroupViewports()` →
  `wwApplyAndFetchGroupViewport()` immediately re-fetches with that
  group's own correct bounds in the same awaited call chain — this
  pattern predates Time Groups (Phase 4A) and is explicitly documented
  at each fallback site, not a silent bug). No call site lets a
  non-primary group's own STEADY-STATE rendering/interaction read the
  wrong group's viewport.
- **`ww.workspaceBounds`** — confirmed to be a genuinely distinct,
  legitimately ALL-SOURCES (not primary-only) aggregate
  (`wwDeriveWorkspaceBounds()` iterates every participating source
  across every group), used only for clamping the primary group's own
  viewport, span-seconds/initial-fetch fallbacks, and full-workspace
  reset — never applied to a specific non-primary group's own
  rendering/interaction (that is `wwDeriveTimeGroupBounds`/
  `wwClampRangeToTimeGroup`'s job, confirmed separate).
- **Singleton DOM** — grepped for every legacy id named in the audit
  task (`wwPanels`, `wwDigitalRegion`, `wwStickyRuler`, `wwCursorOverlay`,
  `wwCursorReadout`, `wwCursorModeBtn`, `wwSetT0Btn`, `wwSyncBtn`,
  `wwCursorLabelLayer`, `wwTimeGroupSliders`) — none exist as DOM ids
  anywhere in the file. Confirmed clean.
- **State lifecycle** (`ww.timeGroupViewports`, `ww.timeGroupCursorState`,
  `ww.timeGroupT0State`, `ww.rulerReadyByGroup`, `ww.digitalChartReadyByGroup`,
  `ww.digitalClickWiredByGroup`, `ww.zoomStepAxisByGroup`, cursor-value
  throttle timers) — `wwSyncTimeGroupCanvases()` prunes every one of
  these Maps on topology change (a group id becoming inactive via merge/
  split/last-channel-removal), and the zero-active-groups branch clears
  all of them outright. A pruned group id is never reused (Time Group
  ids are derived from source timestamps), so a later-reappearing group
  necessarily starts with clean state by construction — confirmed via
  direct code reading, consistent with the already-established "ambiguous
  Time-Group analysis state resets on topology change" policy from
  DEC-061/DEC-062.
- **Multi-layout hard boundary** (Grouped/Separate/Custom) —
  `wwPanelGroupKeyFor()` confirmed to still prefix a Custom-mode panel's
  own key with the channel's current Time Group id (DEC-059's own hard
  requirement), so unrelated Time Groups can never share one physical
  panel in any layout mode.
- **Sync/Detect Event/Annotations** — no call site of either
  `wwPrimaryTimeGroupId()` or `ww.viewport` was found anywhere in these
  three subsystems' own code during the exhaustive whole-file greps
  above (Sync and annotations thread an explicit `groupId` throughout,
  per DEC-063/DEC-065; Detect Event's only primary-group dependency is
  its own single hidden global entry-point button, category B) —
  confirming DEC-063/DEC-064/DEC-065's own prior audits still hold with
  zero regression.

Reason:

The owner's own closure criteria required proving, not assuming, that
every remaining `wwPrimaryTimeGroupId()`/`ww.viewport`/`ww.workspaceBounds`
use is either intentional or harmless — "do not declare complete merely
because tests are green." This audit re-derived that proof directly
from current code (not from trusting the prior DEC-064 audit's own
conclusion at face value), and in doing so found one place where the
prior DEC-065 deferral ("found but explicitly NOT fixed... a general
waveform hover tooltip, not an annotation, out of scope") had left an
open question about actual user-facing impact — this audit traced the
call path to prove it WAS an active correctness defect (wrong Absolute
time shown), not a harmless cosmetic gap, and fixed it.

Alternatives considered:

- Leaving `wwTraceCustomData()`'s gap deferred again, on the theory that
  a hover tooltip is a minor surface — rejected once live tracing proved
  it displays an objectively WRONG wall-clock value (not merely an
  unlabeled one), which is exactly the class of defect this closure
  audit exists to catch before declaring the migration done.
- Broader speculative hardening of every `ww.viewport` fallback site
  (e.g., eliminating the documented transient initial-fetch fallback
  pattern) — rejected: those fallbacks are self-correcting by
  construction, predate Time Groups, are already individually
  documented, and touching them would be scope creep beyond this
  audit's own "fix only what is clearly a Time Group correctness defect"
  charter.

Impact:

- `frontend/index.html` only (no backend changes). Changed:
  `wwTraceCustomData()` (now passes `groupId`/`wwVisibleSpanSeconds(groupId)`
  through); `wwFormatAbsoluteElapsedTime()`'s own header comment
  (corrected, no functional change); the stale pre-TG-D2 HTML comment
  above `#wwTimeGroupCanvases` (corrected, no functional change).
- `backend/tests/test_frontend_absolute_time_precision.py`: one new
  regression test (`test_trace_custom_data_resolves_its_own_channels_time_group_origin`)
  locking in the fix and asserting no `wwFormatAbsoluteElapsedTime()`
  call site anywhere may omit `groupId`.
- Verified by the full backend suite (1777 passed, 0 failed — up from
  1776) plus a live-browser Playwright UAT with two Time Groups on
  genuinely different recorded dates (27 Jan 2026 / 02 Feb 2026):
  confirmed the non-primary group's own `wwTraceCustomData()` output now
  reads its own correct origin (proven distinct from the single
  workspace-wide origin, so the scenario genuinely exercises the fixed
  bug, not a coincidental pass); confirmed setting t0 in one group left
  the other group's own hover text unaffected; confirmed both Time Group
  headers/rulers/axes/readouts render with their own correct dates in a
  full-page screenshot; zero console/page errors throughout.
- **Closure verdict: Time Group architecture migration is declared
  ARCHITECTURALLY COMPLETE.** Per-group rendering, navigation, cursor,
  t0, synchronization, annotations, sticky controls, hover text, and
  time-axis behavior are all isolated by Time Group; remaining
  `wwPrimaryTimeGroupId()`/`ww.viewport`/`ww.workspaceBounds` uses are
  proven intentional workspace-global/compatibility surfaces, not hidden
  defects.
- **Deferred (product decisions, not correctness defects)**: cross-group
  sync, cross-group cursor comparison, cross-group t0, Detect Event UI
  exposure (`WW_DETECT_EVENT_UI_ENABLED`), Time Group collapse,
  CSV/Excel ingestion — unchanged from prior slices, listed here for a
  single closure-time reference rather than scattered across DEC-057
  through DEC-068.

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
