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
