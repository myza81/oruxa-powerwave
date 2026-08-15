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
