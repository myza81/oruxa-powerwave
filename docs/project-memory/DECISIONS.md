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
