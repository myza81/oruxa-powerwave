# Migration Plan — `powerwave` → `oruxa_powerwave`

This document answers:

> **How do we currently intend to get from `powerwave` to `oruxa_powerwave`?**

It is sequencing/direction, not discovery (see
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) for what `powerwave`
actually does) and not the decision log itself (see
[DECISIONS.md](DECISIONS.md) for what has been approved). Phase 0 below is
now a concrete, reviewable design — but it is still **`[PROPOSAL]`
throughout unless a subsection is explicitly marked otherwise**. Nothing in
this document authorizes implementation on its own; see
[DECISIONS.md](DECISIONS.md) for what the owner has actually approved.

Status: **Phase 0 designed, Phase 1 (COMTRADE-only) implemented, deployed to
DEV, UAT'd by the owner, and refined per that UAT** — 2026-08-14. See
DEC-012 through DEC-017 in [DECISIONS.md](DECISIONS.md) and "Phase 1 — UAT
Refinement Record" below. Phase 1.5 and later phases remain **not**
authorized; see [HANDOFF.md](HANDOFF.md) for the actual next step.

## Governing principle

`[DECISION]` See [DECISIONS.md — DEC-001](DECISIONS.md#dec-001--migrate-and-evolve-powerwave-do-not-copy-paste-or-blindly-rewrite-it):
`oruxa_powerwave` will retain many capabilities from `powerwave`, but
workflows, UI/UX, architecture, and selected functionality may intentionally
differ. This is not a copy-and-paste conversion, and existing `powerwave`
behaviour must not automatically be assumed to be the correct future
behaviour for `oruxa_powerwave`.

Where mature engineering logic already exists in `powerwave` and is suitable
for reuse, the project prefers reuse or controlled extraction over
unnecessary reimplementation — but this is a preference to weigh per
subsystem once discovery evidence exists, not a blanket mandate to port
everything.

## Approved backend/frontend responsibility principles

`[DECISION]` See [DECISIONS.md — DEC-006 through DEC-011](DECISIONS.md) for
the full record. Summarized here for orientation: the Python backend is
authoritative for parsing, original source data, timestamp/timebase
interpretation, engineering calculations, synchronization, and analysis; the
frontend's role is presentation, interaction, visualization, workspace
controls, and user selections; mature engineering logic must not be
duplicated into JavaScript for convenience; original uploaded files must
remain immutable; engineering calculations must operate on full-resolution
backend data, and future display decimation must never silently affect
those calculations; migration proceeds in small vertical slices, not a
single recreation of the whole desktop app.

## Approved Phase 1 scope and state-scoping principles

`[DECISION]` Recorded 2026-08-14 during governance cleanup — see
[DECISIONS.md — DEC-012](DECISIONS.md#dec-012--phase-1-state-is-scoped-by-workspacesource-identity-never-process-global)
through
[DEC-014](DECISIONS.md#dec-014--phase-1-is-comtrade-only-csvexcel-and-import-wizard-grade-timestamp-handling-are-deferred-to-phase-15).
Summarized: Phase 1 backend state must be scoped by `workspace_id`/`source_id`,
never process-global (DEC-012); small JSON metadata sidecars via the
existing `StorageBackend` are an acceptable *implementation mechanism* for
the early slice's metadata — this is **not** approval of the long-term
persistence architecture, which remains explicitly open (DEC-013); and
**Phase 1 supports COMTRADE only** — general CSV/Excel import, including
any temporary simplified subset, is deferred in full to Phase 1.5, planned
but not yet implemented or approved (DEC-014).

## How unresolved issues are handled — decision-mode framework

Not every open question needs an immediate `[DECISION]`. See
[README.md — Decision modes](README.md#decision-modes) for the full
governance. In short: an issue is tagged `[DECISION MODE: ANALYSIS]`
(enough evidence exists for a recommendation now), `[DECISION MODE:
COMPARISON]` (multiple viable options should be presented before choosing),
`[DECISION MODE: UAT]` (a hands-on prototype/test is needed before the
difference can be judged), or `[DECISION MODE: DEFER]` (not needed for the
current phase). This document uses that classification throughout —
treat it as informational, not as an implicit decision.

---

## Phase status overview

| Phase | Status |
|---|---|
| Discovery | Complete — [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) |
| Phase 0 — backend/domain foundation design | Design complete (this document) |
| **Phase 1 — COMTRADE-only upload + parsing + source/channel discovery** | **Implemented, deployed to DEV, UAT'd, and refined per UAT (2026-08-14)** — see "Phase 1 — Implementation Record" and "Phase 1 — UAT Refinement Record" below. |
| Phase 1.5 — CSV/Excel + Import-Wizard-grade timestamp handling | **Planned / not yet implemented.** Scope defined below (§16); not yet approved for implementation — do not begin without a separate, explicit go-ahead. |
| Phases 2–9 | Not started — see [POWERWAVE_DISCOVERY.md — Proposed Migration Phases](POWERWAVE_DISCOVERY.md#proposed-migration-phases) for the original high-level sequencing; Phase 0/1/1.5 below supersede that section's Phase-0/1 framing with concrete detail |

**Important scope correction (2026-08-14 governance cleanup)**: Phase 1 is
**COMTRADE only**. An earlier draft of this document left CSV/Excel
inclusion in Phase 1 as an open owner choice (§16 below originally
presented two options); the owner has since decided explicitly —
COMTRADE-only for Phase 1, with CSV/Excel deferred to Phase 1.5. §16 below
has been updated accordingly; see DEC-014 for the recorded decision.

---

## Phase 1 — Implementation Record (2026-08-14)

`[FACT]` What was actually built, and how it differs from the Phase 0
design below (kept for its still-accurate reuse mapping and design
reasoning — this section records where implementation deviated and why).
Full detail in this phase's final report; summarized here for project
memory.

### Critical design change vs. the original Phase 0 design: no persistent storage

Before implementation began, the owner decided
[DEC-015](DECISIONS.md#dec-015--uploaded-event-record-files-are-not-persistently-retained):
`oruxa_powerwave` must not persistently retain uploaded event files
anywhere (not `StorageBackend`, not a database, not a long-term directory).
This supersedes the original Phase 0 design's assumption (§5, §13 below)
that uploaded originals would be written through `StorageBackend`'s
write-once `original` category. The implemented design instead:

- Stages uploaded bytes in an ephemeral, per-request
  `tempfile.TemporaryDirectory()` (`backend/app/services/import_service.py`),
  deleted before the request returns, whether parsing succeeded or failed.
  This exists only so the unmodified `ComtradeProvider` (which requires a
  real filesystem path with a same-directory, same-stem `.dat` companion)
  can be reused without rewriting its parsing logic.
- Keeps only lightweight per-source metadata (channel names/units/counts/
  timing — never sample arrays) afterward, in a plain in-memory registry
  (`backend/app/services/workspace_registry.py`), keyed by
  `(workspace_id, source_id)`, for the life of the process. This replaces
  the Phase 0 design's proposed JSON-metadata-sidecar-via-`StorageBackend`
  mechanism (§4, §14 below) — DEC-013's approval of that mechanism is now
  moot for Phase 1 specifically (superseded by the simpler in-memory
  approach), though DEC-013's own text already flagged it as an early-slice
  mechanism only, not the long-term persistence architecture.
- `StorageBackend` itself was not modified and remains available for other
  future uses; it is simply not called anywhere in the Phase 1 upload path.

**Important nuance, investigated and reported in full in this phase's final
report**: "not persistently retained" is not the same as "never touches
disk." Starlette's own multipart parser (a dependency of FastAPI, not
application code) spools any uploaded file part over roughly 1 MB to an
OS-managed, anonymous (unlinked, never directory-listed) temporary file
*before* this application's code runs at all — confirmed empirically, not
assumed. Combined with this service's own temporary-directory staging
(needed for the reason above), a realistic COMTRADE upload touches the OS
temp filesystem twice, transiently, both times automatically cleaned up
(the first by the OS/Python's `tempfile` machinery when the file descriptor
closes, the second by an explicit `with tempfile.TemporaryDirectory()`
block). Achieving zero disk I/O at all would require rewriting
`ComtradeProvider`'s file-based I/O to accept in-memory buffers, which was
judged disproportionate for this slice (see DECISIONS.md DEC-006's reuse
principle) and is flagged as an `[OPEN]` item rather than silently claimed
as already satisfied.

### What was reused vs. adapted (confirms/refines the Sec 1 mapping below)

- `backend/app/domain/{disturbance_record,channels,metadata,timing}.py` —
  ported near-verbatim from `powerwave`'s `app/models/` at commit `3156392`.
- `backend/app/providers/{base,comtrade}.py` — ported near-verbatim from
  `powerwave`'s `app/providers/{base,comtrade}/`; only import paths changed.
  The parsing algorithm, scaling, timestamp handling, and error behaviour
  are byte-for-byte the same logic.
- **New, oruxa_powerwave-specific** (no `powerwave` equivalent, since
  `powerwave` has no web/API layer at all): `backend/app/domain/source.py`
  (lightweight metadata types), `backend/app/services/{workspace_registry,
  import_service,errors}.py`, `backend/app/schemas/source.py`,
  `backend/app/api/v1/sources.py`.
- **Not built this phase** (Phase 1.5+): `CsvProvider`, `ExcelProvider`,
  the Import Wizard backend — excluded per DEC-014.

### Migration parity — verified, not assumed

Cross-checked the ported `ComtradeProvider` against `powerwave`'s canonical
`ComtradeProvider` (same commit, `3156392`) two ways:

1. Two synthetic fixtures (`backend/tests/fixtures/comtrade/synth_{ascii,binary}.{cfg,dat}`,
   authored for this migration, not derived from any real event) — exact
   match on every field checked (station name, channel names/units/scale/
   offset, sample count, duration, start/trigger time, sampling info, and
   full analog/digital array values), committed as
   `backend/tests/test_comtrade_parity.py`.
2. One real `powerwave` sample file
   (`powerwave/samples/comtrade/PTAI_MVLY_relay.CFG`, 4224 samples, 8 analog
   + 32 digital channels) — exact match on station name, channel counts,
   sample count, timing, sampling info, and SHA-256 hashes of five sample
   arrays. **Not committed to this repository or copied into test
   fixtures** — `powerwave/samples/README.md` notes sample files "may be
   large or confidential" (real substation event data); this comparison was
   run locally only, for verification, and is recorded here for
   traceability rather than as a redistributable artifact. `[OPEN]`: if a
   richer, larger, real-event parity fixture set is wanted for ongoing
   regression coverage, that requires an explicit decision about what may
   be committed — not resolved here.

### Performance baseline (measured, not estimated)

Measured against three inputs, from tiny to real-world-sized (again using
the same non-committed `powerwave` sample files locally, plus the committed
synthetic fixture):

| Input | Combined size | Samples × channels | End-to-end upload+parse | Response body |
|---|---|---|---|---|
| Synthetic fixture (committed) | ~1.4 KB | 40 × 5 | ~5 ms | 360 bytes |
| Real sample (local only) | ~562 KB | 4,224 × 40 | ~9 ms | 363 bytes |
| Real sample (local only) | ~15.7 MB | 32,693 × 130 | ~152 ms | 352 bytes |

Parse-only (no HTTP) peak memory for the 15.7 MB / 32,693-sample /
130-channel file: ~229 MB resident, ~209 MB peak footprint (macOS
`/usr/bin/time -l`, this development machine — not a production
measurement). Response size stays flat (~350-360 bytes) regardless of input
size, confirming the response-size discipline design (§8 below) holds in
practice, not just in principle. `[OPEN]`: no measurement was taken at the
~100 MB ceiling itself (no fixture of that size was available); the ~229 MB
memory-for-~16MB-input ratio suggests a 100 MB file could use on the order
of 1+ GB resident memory during parsing (COMTRADE's structured-array
parsing and DataFrame assembly both materialize full-size intermediate
arrays) — worth a real measurement at or near the configured ceiling before
raising `MAX_EVENT_UPLOAD_SIZE_MB` in any real deployment.

### Frontend

Extended the existing static `frontend/index.html` (no framework
introduced — that remains an open, undecided question, noted in the
original Phase 0 design and still not resolved here) with: two explicit
upload slots (`.cfg` / `.dat` — Option B from §16 below, chosen as "the
simplest bounded UI necessary to prove the upload path" per this phase's
own instructions), client-side size guidance and a pre-check (not
authoritative), busy/success/error states with user-safe error messages
mapped from the backend's structured error codes, a per-browser workspace
identity (`crypto.randomUUID()` in `localStorage`, with a "start new
workspace" reset action), a source list with per-source removal, and a
channel-detail view (timebase summary + full analog/digital channel
tables, no waveform data).

### COMTRADE upload interaction — still `[UAT]`, not decided

Per this phase's instructions, Option B (two explicit named upload slots)
was implemented as the concrete Phase 1 UI because it was the simplest to
build and validate correctly — **this is a temporary Phase 1 choice, not a
decision**. UAT-1 (unchanged from the Phase 0 design, § "Candidate
Decisions Requiring Future UAT" below) remains open: whether Option A
(single multi-file selection, auto-paired by filename stem) is actually
better for real usage is a hands-on question this implementation
deliberately did not resolve. The backend API is agnostic to which option
the frontend uses (both are one multipart POST with `cfg_file`/`dat_file`
parts), so switching later requires no backend change.

### Future architectural requirement recorded (not implemented): portable analysis artifacts

`[PROPOSAL]`, per explicit instruction to record but not design this now:
calculated channels and other valuable analysis artifacts (once they exist,
from a future phase) must eventually be exportable so a user can save their
work locally and re-import it in a future session — the server should not
need to retain them permanently, consistent with DEC-015's ephemeral
principle extended to derived work, not just original uploads. The intended
shape: source analog channels → calculation → calculated channel → active
workspace memory → optional export to the user's machine; when the
workspace ends, server-side calculated arrays are released, but already-
exported work is not lost. A future versioned portable artifact format
(potentially containing format version, calculated-channel name/expression/
operation tree, source-channel references, source file hashes for
verification against a re-uploaded original, units, timebase, sampling
metadata, and optionally the derived values themselves) is a real future
requirement, not designed here — no format, extension, or "save result vs.
save recipe" choice is decided. This belongs with Phase 6 (calculated
signals) and should very likely be a `[DECISION MODE: UAT]` or `[DECISION
MODE: COMPARISON]` question once there's a concrete calculated-signal
feature to attach it to, not resolved by inspection alone. Source-hash
verification (SHA-256, so a saved artifact can confirm a re-uploaded file
is the exact original it was computed against) is worth designing into
source identity early if low-cost, per this phase's instructions, but was
not added to Phase 1's `SourceMetadata` since Phase 1 has no consumer for
it yet and speculative fields without a consumer are exactly the kind of
premature complexity this project's governance discourages.

---

## Phase 1 — UAT Refinement Record (2026-08-14)

`[FACT]` The owner completed hands-on UAT of the deployed Phase 1 build at
`https://dev.powerwave.oruxa.uk` and requested a narrow set of UI
refinements — not a redesign. See
[HANDOFF.md](HANDOFF.md) for the owner-facing before/after summary; this
section records the technical detail.

### Approved and retained unchanged

Per direct UAT feedback, none of the following were touched: the two-slot
`.cfg`/`.dat` upload workflow (now formally decided, not just retained —
DEC-017), the loading/parsing indicator, the 100 MB guidance wording, the
source-metadata-before-channels review step, and the overall simple/
single-page UI direction (no navigation, no side menus, no multi-page
flow added).

### Channel organization

The channel-browsing problem UAT surfaced — hundreds of channels in one
long scroll (UAT example: 80 analog, 282 digital) — was addressed with:

- **Collapsible top-level groups**, implemented with native `<details>`/
  `<summary>` elements (zero custom JS needed for the expand/collapse
  mechanic itself, keyboard-operable and accessible for free). Analog
  defaults **open** (smaller, reviewed first); Digital defaults
  **collapsed** (the section that was actually overwhelming in UAT).
  Counts are always shown, open or closed.
- **Analog sub-grouping by engineering type** — `Voltage`/`Current`/
  `Power`/`Frequency`/`ROCOF`/`Undefined`, computed **once, backend-side**
  (`backend/app/domain/channel_classification.py`), never re-derived in
  the frontend. See "Analog classification architecture" below for why
  backend, and the classification rules themselves.
- **Scale/Offset removed from the primary analog table** (UAT: "little
  useful meaning" for browsing) — the primary table now shows Name/Unit/
  Phase only. Both fields are unchanged in the domain model
  (`AnalogChannelSummary`) and the API response (`AnalogChannelOut`) — see
  `backend/app/schemas/source.py`'s docstring — nothing was deleted, only
  hidden from this one table. A future channel-detail view can surface
  them without any backend change.

### Analog classification architecture

Lives in `backend/app/domain/channel_classification.py` — one function,
`classify_analog_channel(parameter_type, unit)`, used by
`import_service.py` at import time and exposed as a new
`engineering_type` field on `AnalogChannelSummary`/`AnalogChannelOut`.
Chosen to live backend-side (not as frontend string matching) because it's
reusable domain knowledge, not a display trick — the same classification
will matter for future channel filtering, waveform channel selection,
calculated signals, and analysis tooling (Phase 1.5+), and this way there
is exactly one implementation to keep correct.

Three-tier rule, most to least reliable, **never guessing**:

1. `AnalogChannel.parameter_type` (powerwave's own `ParameterType` enum
   values — `voltage`, `current`, `mw`, `mvar`, `frequency`, `rocof`,
   `unknown`; sourced from `powerwave/app/import_wizard/column_mapping.py`,
   not invented). Currently **dormant** for Phase 1 — COMTRADE never sets
   this field — but real, tested code, ready for Phase 1.5's CSV/Excel
   providers, which do set it.
2. Unit semantics — the one signal every COMTRADE analog channel actually
   has. Recognizes `V`/`A`/`Hz`/`W`/`VAR`/`VA` (real, reactive, and
   apparent power all grouped under one `Power` category for this
   refinement), tolerant of a metric prefix and case, nothing looser.
3. Channel naming patterns — **deliberately not implemented**. No naming
   convention was judged sufficiently deterministic (the project's own
   bar): e.g. a channel literally named "VA" is genuinely ambiguous
   between "voltage, phase A" and the unit "VA" (apparent power) — exactly
   the kind of vague string match the task that requested this classifier
   said not to guess through.

Anything that doesn't confidently resolve through tiers 1-2 is
`Undefined` — a real, visible category (not "Anonymous" — the channel's
*name* is always known; only its engineering *type* is not confidently
classified).

Tested in `backend/tests/test_channel_classification.py`: every
recognized unit (with case/prefix variants), every recognized
`parameter_type` value, parameter_type-over-unit priority, and — the
governance the task specifically called out — that an ambiguous/unknown
channel is never silently forced into a real category.

### Channel search

Client-side only, over the channel list already fetched for the selected
source — no additional network request per keystroke (or at all). Row
search text (name + unit + phase, lowercased) is computed once at render
time and cached on each row's `data-search` attribute; each keystroke only
toggles `hidden`/`open` on already-built DOM nodes, it never rebuilds the
channel HTML — chosen specifically to stay responsive at the 282-channel
scale UAT exercised without introducing any framework or virtualization
library. A group/sub-group containing at least one match auto-opens
(so a match is never hidden inside a collapsed section); clearing the
search restores the default expansion state (Analog open, Digital
collapsed) rather than whatever arbitrary state the user's own toggling
left things in.

### Remove confirmation and the stale-banner fix

Clicking "Remove" now opens one small confirmation dialog (the app's only
modal) with the exact wording pattern requested; Cancel closes it with
**no** DELETE request issued; Remove issues the DELETE, clears the
selected-source detail panel, and — the reported bug — clears the
success/import banner **only when it was describing the source just
removed** (tracked via a `lastImportedSourceId` variable set on successful
import), not unconditionally. This is deliberately forward-compatible with
a future multi-source workspace: removing source B must never clear a
still-valid banner about source A.

### Verification method

No new frontend test framework was introduced (none existed before this
task, and the task explicitly permitted documenting manual/scripted
verification instead). Verification performed this session:

- A one-off Node script (not committed) loaded the actual shipped
  `frontend/index.html` `<script>` content into a real DOM via `jsdom` —
  not a reimplementation — and exercised: grouping/counts/default
  expansion/column removal against an 80-analog/282-digital synthetic
  dataset matching UAT's own numbers; search filtering (case-insensitive,
  cross-analog/digital, auto-expand-on-match, empty state, clear-restores-
  default); the full remove-confirmation flow including that Cancel issues
  zero DELETE calls; and the stale-banner fix including the
  removing-a-different-source non-interference case. All passed.
- A live local backend (`uvicorn`) was exercised via `curl`: valid upload
  now returns `engineering_type` per channel; all previously-passing
  guardrails (missing companion file → 422, wrong extension → 400
  `unsupported_file_type`, oversized upload — covered by the existing
  automated test) were spot-checked unchanged.
- Full backend suite re-run: 215 passed (168 Phase 1 + 6 new classification-
  adjacent + new API assertions), including the unmodified COMTRADE parity
  tests — no parser/provider code was touched this pass, only new
  read-only classification logic layered on top of already-parsed channel
  metadata.

---

## Phase 1 — Workspace-Reset Record (2026-08-14)

A focused closure fix, following a same-day investigation into whether
`Remove` and `Start new workspace` were genuinely distinct. The owner
decided to **keep** `Start new workspace` and make it a real
whole-workspace lifecycle operation — see DEC-018
([DECISIONS.md](DECISIONS.md)) for the approved decision itself; this
section is the implementation record.

### What was wrong

`Start new workspace` previously only generated a new client-side UUID: no
backend call was made, so every source in the old workspace stayed
resident in `WorkspaceRegistry` (in-memory, no TTL — see
`backend/app/services/workspace_registry.py`) and remained reachable via
the old `workspace_id`. The stale "Imported ..." success banner also
survived the reset, since nothing cleared it on this path (the equivalent
fix for `Remove` shipped in the prior UAT refinement pass never touched
`startNewWorkspace()`).

### Backend: a whole-workspace lifecycle boundary

- `WorkspaceRegistry.remove_workspace(workspace_id)`
  (`backend/app/services/workspace_registry.py`) — finds every
  `(workspace_id, source_id)` entry for the given workspace, deletes those
  dict keys (dropping the process's only references to those
  `SourceMetadata` objects, which hold no waveform/sample arrays per
  DEC-015 — nothing further is needed for them to become eligible for
  garbage collection), and returns the count removed. Safe and idempotent
  for an unknown or already-empty `workspace_id` — a workspace is never
  explicitly "created" server-side, so there is no "not found" case to
  reject.
- `DELETE /api/v1/workspaces/{workspace_id}` (new file
  `backend/app/api/v1/workspaces.py`, separate router from
  `app/api/v1/sources.py`'s per-source endpoints) — thin wrapper over
  `remove_workspace()`. Returns `204 No Content` on success, including for
  an unknown/empty workspace (idempotent-DELETE semantics); `400` with
  `{"detail": {"code": "invalid_workspace", ...}}` for a blank id, matching
  the existing error-shape convention from `app/api/v1/sources.py`.
- Deliberately **not** built: any hook for calculated channels,
  synchronization state, measurements, or waveform/layout state — none of
  those exist yet. The endpoint and registry method are structured so a
  future workspace-owned resource has one lifecycle call to plug into, but
  nothing was added speculatively for resources that don't exist (per this
  task's explicit "future-proof but do not overengineer" instruction).

### Frontend: correct ordering, confirmation, and failure handling

`frontend/index.html`'s `startNewWorkspace()` was split into:

1. `startNewWorkspace()` — the button's click handler. If the workspace
   currently has at least one visible source, shows a new, separate
   confirmation dialog (`#newWorkspaceConfirmOverlay`, distinct from the
   existing per-source `#confirmOverlay` so the two dialogs' wording can
   never drift into each other's blast radius). If the workspace is
   already empty, skips the dialog and calls the reset directly — no data
   would be discarded either way, and this keeps exactly one reset code
   path rather than a separate "empty" branch.
2. `resetToNewWorkspace()` — the actual reset, in the required order:
   `DELETE /api/v1/workspaces/{oldWorkspaceId}` is awaited **first**; only
   on a successful response does it mint a new `workspace_id`
   (`crypto.randomUUID()`), clear `selectedSourceId`/`lastImportedSourceId`,
   clear the upload-success banner, reset the channel panel to its empty
   state, and refresh the (now-empty) source list. If the DELETE fails —
   non-2xx response or a network error — none of that clearing happens:
   the old `workspace_id` stays in `localStorage`, the source list and
   banner are left exactly as they were, and a visible error message
   appears next to the button (`#workspaceResetError`) so the user can
   retry rather than the UI silently pretending a reset occurred.

Confirmation wording (adapted to the app's own on-screen name, "Powerwave" —
the header/title never say "Oruxa Powerwave"):

> **Start a new workspace?**
> All event records currently loaded in this workspace will be removed
> from Powerwave. Your original files on your computer will not be
> affected.
> `[Cancel]` `[Start new workspace]`

`Remove`'s own confirmation dialog, wording, and DELETE call are untouched.

### Verification method

No new frontend test framework was introduced (consistent with the
project's established approach — see the prior UAT refinement pass).
Verification performed this session:

- A one-off `jsdom` script (not committed) loaded the actual shipped
  `frontend/index.html` inline `<script>` into a real DOM and drove the
  **real** upload code path (a mocked-`fetch` form submission, not direct
  variable manipulation — the prior pass's own script had to be corrected
  for exactly this reason, since top-level `let`/`const` in a classic
  script are not reachable via `window.*` from outside, matching real
  browser behaviour). 36 checks across 7 scenarios, all passing:
  non-empty-workspace confirmation shown before any DELETE; Cancel issues
  zero DELETE calls and preserves the old workspace id/source list/banner;
  Confirm issues exactly one workspace-level DELETE against the *old* id,
  then mints a new id, empties the source list and channel panel, and
  clears the banner; a failed DELETE preserves the old workspace id,
  source list, and banner while showing a visible error; an empty
  workspace skips the confirmation but still resets; `Remove` still issues
  only a source-level DELETE (never the workspace-level one) and its
  banner/Cancel/other-source-preserved behaviour is unchanged; removing a
  source that isn't the one the banner describes still leaves that banner
  alone.
- Full backend suite: **227 passed** (215 before this pass + 12 new:
  4 `WorkspaceRegistry.remove_workspace()` unit tests, 7
  `DELETE /api/v1/workspaces/{id}` API tests including multi-source and
  cross-workspace-isolation cases, 1 `Remove`-regression test confirming a
  single-source delete leaves sibling sources in the same workspace
  intact). No COMTRADE parser/provider/classification code was touched
  this pass.

---

## Phase 2 — Waveform Workspace Discovery and Design (2026-08-14)

`[PROPOSAL]` throughout except where explicitly marked `[FACT]` (verified
`powerwave` code evidence) or `[DECISION]` (none newly recorded by this
pass — see the closing note). This section is discovery and design only;
**no waveform code, chart library dependency, or backend memory-model
change was implemented this pass**. Phase 1 is complete: implemented,
deployed to DEV, UAT'd, refined per that UAT, had its workspace-reset
lifecycle corrected (DEC-018), and — per the project owner, opening this
Phase 2 task — **has now passed final owner UAT**. `[FACT]`, owner-stated:
Phase 1 final UAT passed; no further Phase 1 work is expected before
Phase 2 begins.

### 1. Goal and core principle

Design (not build) the first useful web waveform workspace for an
already-imported COMTRADE source: select channel(s) → backend provides
appropriate waveform data → interactive zoom/pan. Scope is deliberately
narrow — basic single-source visualization only. Synchronization,
calculated signals, CSV/Excel, measurements beyond the essential, advanced
analytics, persistence, and authentication are explicitly **out of scope**
for Phase 2 and must not be designed into this slice's data model by
implication.

**Core principle, carried from [POWERWAVE_DISCOVERY.md — Full-Resolution
Engineering Data Principle](POWERWAVE_DISCOVERY.md#full-resolution-engineering-data-principle)
and restated for Phase 2**: the backend's retained sample data is the
*only* authoritative engineering data. Whatever the browser receives and
renders is a **display representation** derived from that authority, never
the other way around. No future engineering calculation (measurements,
calculated signals, analytics — Phases 5-7) may be designed to depend on
decimated/display data; they must always read the same full-resolution
source the display representation was derived from. This mirrors a
principle `powerwave` itself already mostly honors (see §2 below) — Phase
2 must not regress it while crossing a network boundary for the first
time.

---

### 2. Existing `powerwave` waveform architecture — verified findings

Re-verified this session directly against `powerwave` HEAD `3156392`
(unchanged since the original discovery audit — confirmed via
`git log -1`), via live import/call-graph tracing, not documentation. Where
this corrects or sharpens
[POWERWAVE_DISCOVERY.md — Waveform Rendering](POWERWAVE_DISCOVERY.md#waveform-rendering),
the correction is noted.

**Stack**: PyQtGraph 0.14.0 is the sole plotting library
(`requirements.txt`); no `matplotlib` import exists anywhere in `app/`.
`PyOpenGL==3.1.10` is declared and wired (`app/main.py`:
`pg.setConfigOptions(useOpenGL=_USE_OPENGL, ...)`), but **off by default**,
opt-in only via `POWERWAVE_USE_OPENGL` env var — contradicting
`docs/VIEWPORT_RENDERING_POLICY.md`'s claim that it is "REQUIRED." Another
documented-vs-actual mismatch, consistent with the discovery audit's
general finding that `powerwave`'s plotting docs describe aspirational or
superseded behavior in several places.

**Live runtime path** (confirmed via `main_window.py` → `SessionCanvasController`
→ `SessionCanvasWidget`, with zero real imports of the alternatives):
`SessionCanvasWidget` (`app/visualization/widgets/session_canvas.py`) +
`SessionCanvasController` (`app/ui/session/session_canvas_controller.py`).
Three other plotting abstractions exist in the repository but are **dead
code**, reachable only from their own test suites (confirmed by grepping
every import site, not just their existence):

| Dead abstraction | Reachable from live app? |
|---|---|
| `FlexiblePlotCanvas` | No — only its own tests + dead `VisualizationManager` |
| `VisualizationManager` | No — only tests, never imported by `main_window.py` |
| `DigitalEventTimeline` | No — only dead `VisualizationManager` + tests |
| `FastWaveformWidget` | Doesn't exist as a class at all — a superseded name (renamed to `FlexiblePlotCanvas` per `directives/`), survives only in prose |
| `BaseOverlay`/`CurveStore`/`OverlayRegistry` (`app/visualization/overlays/`) | Classes are *loaded* (a transitive import side-effect of an unrelated `overlay_colors` utility import) but never *instantiated* by live code — behaviorally dead |
| `channel_grouper.py` (second panel classifier) | Only imported by the dead `VisualizationManager`; the live classifier is a *different*, independently-maintained function (below) |

**Migration implication, reaffirmed**: any Phase 2 design work that
consulted `powerwave`'s own `docs/VIEWPORT_RENDERING_POLICY.md`,
`docs/ARCHITECTURE.md`, or similar for "the" plotting architecture would be
designing around code that does not run. Every behavioral claim below is
sourced from the live call graph, not those documents.

**Panel/channel routing**: `_infer_panel_for_channel()`
(`app/sessions/event_session.py:145`) — a **module-level function**, not a
method of `EventAnalysisSession` (a minor correction to the original
discovery note, which implied it was a method) — routes by priority:
explicit `parameter_type` → engineering unit → channel-name keyword match,
into default panels `voltage, current, power, frequency, digital, other`.
This is functionally the direct ancestor of `oruxa_powerwave`'s own
already-shipped `backend/app/domain/channel_classification.py` (Phase 1),
which deliberately narrowed the approach to two tiers (dropping the
name-keyword tier as too ambiguous — see DEC-... n/a, just implementation
choice) and renders as `Undefined` rather than guessing. **Recommendation
carried into §9**: Phase 2's waveform panel routing should reuse the
already-shipped `engineering_type` field rather than re-deriving
classification a third time (a fourth, if `channel_grouper.py`'s
independent duplicate is also counted).

**Decimation — the most consequential finding for Phase 2's engineering
safety design**: `build_aligned_data()`
(`app/sessions/event_session.py:822`, signature
`build_aligned_data(source_id, channel_name, t_start, t_end, max_points=4000)`)
clips each channel's raw arrays to `[t_start, t_end]`, and — only if the
clipped length exceeds `max_points` — calls
`decimate_for_display()` (`app/visualization/rendering/downsampling.py:6-47`):

```python
stride = max(1, (len(t_clip) + max_points - 1) // max_points)
return t_clip[::stride], d_clip[::stride]
```

This is **plain nth-point stride sampling — not a min/max envelope, not
peak-preserving in any form**. Every `stride`-th sample survives; everything
between is discarded outright, with no aggregation. **A transient spike or
protection-relevant excursion narrower than `stride` samples can be
silently invisible in the decimated view**, with nothing in the pipeline
to flag that it happened. `PlotDataItem.setDownsampling(auto=True,
method="peak")` (PyQtGraph's own C++-side downsampling) is applied on top,
but only to primary/left-axis curves (voltage), never right-axis curves
(current/power/frequency) — and it can only operate on whatever already
survived the Python-side stride cut; it cannot recover data already
dropped in step one.

`t_start`/`t_end` come from `_session_window(session)` — the **entire
offset-shifted session domain**, not the live pan/zoom viewport — at every
one of the 6 production call sites in `session_canvas_controller.py`, all
called with no `max_points` override. **`powerwave` does not re-decimate on
zoom in its live code path** (a documented-vs-actual gap: its own
`VIEWPORT_RENDERING_POLICY.md` §4.4 mandates viewport-triggered
re-decimation; the live code has no `sigXRangeChanged` connection to any
decimation call — the only such connection drives an unrelated navigator
strip). Zooming in PyQtGraph after the initial `build_aligned_data()` call
is local browser-side... local *desktop*-side pan/zoom over whatever ≤4000
points were already delivered — it does not fetch a fresh, higher-resolution
slice for the new range. **No viewport-slice cache exists anywhere** — every
repaint recomputes from raw arrays fresh, at desktop repaint rates
(acceptable single-process/single-user) not web request rates (would be
expensive at scale).

**Digital channel transitions are at real risk from this same pipeline
ordering**: `update_digital_curve()` receives the **already-strided**
output of `build_aligned_data()` and only then calls `extract_transitions()`
(`app/visualization/rendering/digital_transforms.py`). `extract_transitions()`
is lossless *relative to the input it's given*, but that input has already
had non-kept-stride samples discarded upstream — **a breaker-status pulse
or trip signal narrower than `stride` raw samples can be dropped before
transition-extraction ever sees it.** This is a genuine, previously
uncited engineering-integrity risk in the current desktop app, not merely
a migration concern — recorded here as evidence, not as something Phase 2
needs to fix in `powerwave` itself (out of scope; `powerwave` is read-only
reference), but as a design principle to *not* repeat.

**Cursor behavior — three-way fragmented, confirmed current** (not just
historically true): (1) a dead `FlexiblePlotCanvas._cursor` that
`SynchronizationManager._extract_cursor()` still checks first; (2) a live
`_hover_cursor` crosshair, actually synced through `SynchronizationManager`;
(3) live `_cursor_a`/`_cursor_b` measurement cursors, synced by hand-rolled
signal wiring in `SessionCanvasController` that bypasses
`SynchronizationManager` entirely. No single owner. **Behavior worth
preserving**: two-cursor value/delta/RMS measurement is a real, useful
engineering feature (Phase 5, out of scope for Phase 2). **Implementation
not worth reusing**: any of the three cursor-ownership mechanisms above —
cursor/interaction state is presentation state and belongs entirely
client-side in a fresh, single-owned design, designed once correctly
rather than ported three times.

**Initial viewport**: `viewport_policy.py::select_initial_viewport()` is
**conditionally** trigger-relative — it returns `None` (full session window
used instead) whenever fewer than 2 active sources exist, no source has a
real (non-synthetic) trigger anchor, or the trigger-focused window would
already cover ≥50% of the full domain. **Practical implication directly
relevant to Phase 2's single-source scope: for a single COMTRADE source,
the initial viewport `powerwave` itself would show is always the full
record**, not a trigger-relative window — trigger-focusing only activates
with ≥2 active sources (Phase 3+ territory). This meaningfully simplifies
Phase 2's initial-load design (§16): show the whole record's duration on
first load, no trigger-relative logic needed yet.

**Full-resolution preservation — confirmed genuinely true, not aspirational**:
`waveform_data` is never mutated (verified: `apply_time_offset` returns a
new array; clipping uses boolean-mask indexing producing new arrays;
`decimate_for_display` uses fancy-index slicing producing new arrays).
Calculated Signals and all of `app/analytics/*` read `DisturbanceRecord`
directly, never the decimated display arrays. **This is the one piece of
`powerwave`'s architecture Phase 2 should most directly emulate the
*intent* of** (not the implementation) — see §1's core principle.

**Behavior worth preserving vs. desktop implementation not to reuse** —
systematic summary:

| Behavior worth preserving | Desktop implementation (do not reuse) | Web-native target |
|---|---|---|
| Multiple analog traces share one time axis, grouped by engineering type | `_infer_panel_for_channel()` + PyQtGraph multi-ViewBox per-panel wiring | Reuse Phase 1's already-shipped `engineering_type`; web-native panel/legend components |
| Full-resolution data always authoritative, decimation only for display | `EventAnalysisSession` holding `DisturbanceRecord` in a Qt-event-loop-owned object; recompute-per-repaint | Backend-owned, viewport-aware decimation endpoint (§10), full-resolution array retained separately from the display response |
| Curve reuse rather than recreate on data update | `PlotDataItem.setData()` | Equivalent update-in-place pattern in whatever web library is chosen (§7) |
| Digital channels rendered as clear hi/lo step segments | `digital_transforms.py`'s pure-NumPy segment builder (algorithm is fine; the *pipeline ordering* around it is not — see above) | Reusable *algorithm* reference; must run decimation-safe for transitions (§14) |
| Two-cursor measurement (value/delta/RMS) | Three independent, unsynchronized cursor mechanisms | Single client-owned cursor state (Phase 5, not Phase 2) |
| Initial view starts sensible (whole record for a single source) | `viewport_policy.py`'s conditional logic | For Phase 2 (always single-source): simply show full record duration; revisit trigger-focusing in Phase 3+ |
| GPU-accelerated rendering available for large datasets | PyQtGraph + optional PyOpenGL (off by default) | Canvas/WebGL-capable web library evaluated on its own merits (§7) |

---

### 3. Decimation analysis — is `powerwave`'s algorithm suitable for backend reuse?

**No — not as-is**, for two independent reasons, both evidenced above:

1. **Not viewport-aware.** It decimates against the entire session window
   regardless of what's actually visible, then relies on client-side
   pan/zoom over the already-truncated result. A 1:1 port to a web API
   would mean the *first* request for any zoom level re-decimates the
   *entire* record rather than the requested range — wasteful, and for a
   long recording, could under-serve a narrow zoomed-in request (the
   opposite of what zooming should reveal — see §12/§19).
2. **Not peak-preserving.** Plain `[::stride]` nth-point sampling can
   silently drop a transient spike or narrow digital pulse. This is
   acceptable for a general-purpose dashboard chart; it is **not**
   acceptable for power-system disturbance analysis, where the entire
   point of the tool is surfacing exactly this kind of transient.

**How many points are typically rendered**: `max_points=4000` is the
default and is never overridden at any of the 6 live call sites — so
`powerwave` itself already treats "a few thousand points is enough for
useful visual density" as an established, working assumption. This number
is a reasonable **starting reference** for Phase 2's own point-budget
default (§10), even though the *algorithm* used to reach it should not be
reused.

**Does zooming eventually reveal full-resolution detail?** No, not in the
live desktop path — zoom is purely a local re-view of the same ≤4000
points already fetched for the full session window; there is no re-fetch
at higher resolution for a narrower range. **This is precisely the
behavior Phase 2 must do differently** (§12/§19): a web architecture that
inherited this as-is would leave engineers unable to actually inspect fine
detail by zooming, which defeats a core purpose of disturbance analysis
software.

---

### 4. Web waveform data-delivery architecture options

`[DECISION MODE: COMPARISON]` — the tradeoffs below are grounded in
verified `powerwave` behavior and known web/browser constraints; genuine
alternatives exist and the choice affects nearly everything downstream
(API shape, caching, backend memory model), so it deserves owner
visibility before Phase 2A is scoped in detail. It does **not** need a
hands-on prototype to compare (unlike the plotting-library choice, §7) —
the tradeoffs are analyzable from data volume and network/browser
constraints alone.

**Option A — send complete full-resolution arrays once.**
Backend sends every sample for every selected channel in one response; all
zoom/pan happens entirely client-side against data already in memory.
- Latency: one request, but its size scales with the *entire* record —
  first paint could be slow for anything beyond a small file.
- Payload size: for a single analog channel at even a modest COMTRADE
  sample rate (e.g. 4-20 kHz) over a multi-second record, this is already
  tens of thousands of samples; for multiple channels, multiplies linearly.
  Uncompressed JSON floats are the worst case here (§5).
  Approaching the current 100 MB upload ceiling's *parsed* equivalent
  (unmeasured — see the open item in §22), this could mean single-digit
  millions of samples per channel in the worst case.
- Browser RAM: everything held at once; scales linearly with channels ×
  samples selected. Acceptable for one or a few channels of a modest
  record; risky for many channels or a very long/high-rate record.
- Interaction speed after load: excellent — no network round-trip for
  pan/zoom once loaded.
- Suitability for a typical (<100 MB) COMTRADE file with a *small* number
  of selected channels: good — this is realistically fine for Phase 2's
  smallest slice (§32/§40: one or a few channels).
- Multi-channel/multi-source scaling: poor — does not scale gracefully to
  "select many channels" or (Phase 3+) "multiple sources," since payload
  and RAM grow with every additional selection, unbounded by what's
  actually being looked at.

**Option B — viewport/range requests.**
Browser requests `(source, channel(s), time range, point budget)`; backend
extracts and decimates freshly for exactly that request; browser renders
the response.
- First-load speed: fast — the initial response is bounded by the point
  budget, not the record size.
- Network traffic: scales with interaction (each pan/zoom = a request),
  not with record size — the opposite tradeoff from Option A.
- Backend computation: real, recurring cost per request — extraction +
  decimation must be fast and cheap enough not to make panning feel
  laggy; this is where a fast, viewport-aware decimation implementation
  (§3) matters most.
- Zoom/pan responsiveness: depends entirely on request latency; a
  well-implemented range-extraction endpoint over an already-parsed,
  already-in-memory array (§23) should be sub-100ms for typical requests,
  but this needs to be measured (§29), not assumed.
- Caching: viable and valuable (§23) — a repeated or overlapping range
  request is common during normal zoom/pan exploration.
- Complexity: higher than Option A — requires a real API contract for
  range/point-budget semantics (§10), and requires the backend to retain
  full-resolution arrays across requests (§13/§14), which Phase 1
  currently does not do.

**Option C — multi-resolution/pyramid representation.**
Precompute multiple decimation levels ahead of time (e.g. mipmap-style),
serve the appropriate level per zoom depth.
- Useful for very large, frequently-re-viewed datasets with a stable
  access pattern (e.g. long-term historian/SCADA time series browsed
  repeatedly over days).
- **Premature for Phase 2**: a single COMTRADE disturbance record is
  typically seconds to tens of seconds long — not the kind of "huge,
  long-lived, repeatedly-browsed" dataset pyramiding is built for.
  Precomputing levels for a record that may only be viewed once, in one
  ephemeral session (per DEC-015 — no persistent storage), is speculative
  complexity without a demonstrated need. Revisit only if Option B's
  on-demand decimation proves too slow under real measurement (§29).

**Option D — hybrid: lightweight overview + range requests for zoomed
detail (+ optional local caching of recently-fetched ranges).**
Initial load fetches a decimated overview (Option B's mechanism, applied
once at full-record range and a modest point budget); subsequent zoom/pan
issues further range requests at the new viewport; the browser may cache
recently-fetched ranges to avoid re-fetching an unchanged view.
- Combines Option A's fast/simple initial paint characteristics (a single,
  bounded request) with Option B's scalability (interaction cost scales
  with what's being looked at, not the whole record).
- This is, in effect, "Option B applied consistently from first load
  onward" — there is no meaningfully separate "overview" request type
  needed if the *initial* waveform request is simply Option B's endpoint
  called once with the full-record range and a sensible default point
  budget (see §10, §16). Framing it as "hybrid" mainly signals: don't
  design a *different* mechanism for first load vs. subsequent zoom — one
  endpoint, used the same way both times.

**Recommendation** (offered for owner comparison, not pre-decided):
**Option B/D** (they collapse to essentially the same design, per the note
above) is the strongest fit for Phase 2's actual data shape — single
COMTRADE source, ephemeral per-workspace lifetime, potentially many
channels of which only a few are selected at once, and the explicit
requirement (§19) that zooming must reveal genuinely higher-resolution
detail. Option A remains reasonable as a possible *optimization* for the
narrowest case (one small channel, already-small record) but should not be
the general-purpose mechanism. Option C is not justified yet.

---

### 5. Transfer format — JSON vs. binary

`[DECISION MODE: ANALYSIS]` — enough evidence exists from data volume and
standard web-serialization characteristics to recommend a specific
approach without a hands-on trial; this is a throughput/engineering
question, not a UX one.

| Format | Complexity | Serialize/deserialize cost | Browser support | FastAPI support | Portability/inspectability | Verdict |
|---|---|---|---|---|---|---|
| JSON arrays of floats | Lowest — native everywhere | Non-trivial for large arrays: JSON float encoding/decoding is markedly slower and larger (each float becomes ~15-20 ASCII bytes, e.g. `-123.456789,`) than a packed binary representation | Universal | Native (`response_model`, `JSONResponse`) | Excellent — human-readable, trivially debuggable in devtools/curl | Fine for Phase 1-scale metadata payloads (already in use); **not** the right choice for thousands-of-points-per-channel waveform payloads at scale |
| Raw compact binary (e.g. a small custom header + packed `float32`/`float64` arrays, served as `application/octet-stream`) | Low-moderate — FastAPI/Starlette serve raw bytes trivially (`Response(content=bytes, media_type=...)`); browser reads via `ArrayBuffer`/`Float64Array`/`Float32Array`, both standard | Lowest of any option — no parsing step beyond a typed-array view over the raw bytes | Universal (`TypedArray`/`ArrayBuffer` are baseline Web APIs) | Straightforward — no special library needed | Good — a small fixed header (channel count, point count, dtype) documented once makes it easy to inspect with a short script; less casually readable than JSON in devtools, but not opaque | **Recommended** for the actual sample-value payload once volume matters |
| Arrow / Parquet-style columnar | Moderate-high — needs a library on both sides (`pyarrow` backend, `apache-arrow`/similar frontend) | Good for very large, wide, columnar data; overkill for "a handful of channels' worth of floats + a shared or per-channel time array" | Requires a JS Arrow library (added frontend dependency) | Requires `pyarrow` backend dependency | Good tooling, but a heavier, less-inspectable stack than a documented raw-binary format for this data shape | Not justified for Phase 2's scope — revisit only if a genuinely columnar, wide, multi-source dataset shape emerges later |
| Compressed JSON (e.g. gzip over the existing JSON) | Very low (transport-level, often already automatic via `GZipMiddleware`/reverse-proxy) | Reduces transfer size, does not reduce parse cost — JSON parsing is still the bottleneck, not bytes-over-the-wire, for point-heavy payloads | Universal (`Content-Encoding: gzip` is standard) | Trivial (`GZipMiddleware`) | Same inspectability as JSON once decompressed | Worth keeping as a transport-layer optimization *regardless* of which payload format is chosen — orthogonal, not a replacement for the format decision |

**Recommendation**: **JSON for everything except the actual sample-value
arrays** (metadata, channel lists, error bodies — all continue exactly as
Phase 1 already does it), and **a small, simple, well-documented binary
response for waveform sample data** once payloads exceed a point count
where JSON's parse/size overhead becomes measurable (this should be
confirmed by the benchmark plan, §29, not assumed outright — for a very
small Phase 2A slice at ≤4000 points, plain JSON may honestly be
indistinguishable in practice, and starting with JSON for the *first*
implementation slice, then switching only if the benchmark shows a real
cost, is a defensible, lower-complexity path for a solo developer — see
§40). Do not introduce Arrow or another exotic format without a measured
justification.

---

### 6. Frontend/backend boundary — confirmed, with one addition

The boundary proposed in
[POWERWAVE_DISCOVERY.md — Proposed Frontend/Backend Boundary](POWERWAVE_DISCOVERY.md#proposed-frontend--backend-boundary)
and already implicitly followed by Phase 1 (backend: parsing, channel
classification, structured metadata; frontend: rendering, interaction,
selection) holds for Phase 2 and needs no revision:

```text
Backend:
- authoritative full-resolution arrays (new for Phase 2 — see §13/§14)
- source/timebase (already shipped, Phase 1)
- range extraction + display decimation (new, viewport-aware — see §3/§10)
- engineering-safe waveform preparation (peak-preserving, see §21)

Frontend:
- render (chosen plotting library, §7)
- zoom/pan interaction, requesting the new visible range
- legends, panel layout, visual state (§9/§17)
- channel selection UX (§8)
```

**One addition the evidence surfaces**: cursor/measurement state (§2's
"three-way fragmented" finding) confirms this boundary cleanly extends to
future cursor/measurement work (Phase 5) — `measurement_engine.py`-style
computation takes cursor positions as plain parameters and owns no cursor
state itself, so "cursor state is presentation state, lives entirely
client-side" is not a new boundary decision Phase 2 needs to make, just a
confirmation that the general principle already holds for that
not-yet-built feature too.

---

### 7. Plotting-library candidates

`[DECISION MODE: UAT]` — per the project-memory framework's own guidance,
chart density/readability/interaction responsiveness is exactly the kind
of question that's unreliable to settle from documentation alone. Three
realistic candidates, evaluated on the stated criteria:

| Library | Rendering model | Large time-series performance | Zoom/pan | Multi-panel sync | Digital/step signals | Bundle size | License | Complexity for a solo dev | Notes |
|---|---|---|---|---|---|---|---|---|---|
| **uPlot** | Canvas 2D, purpose-built for time series | Excellent — widely benchmarked as one of the fastest canvas time-series renderers available; handles tens of thousands of points smoothly | Built-in, fast | Manual but straightforward (shared-cursor/shared-range plugins exist) | Native step-line support, well-suited to digital signals | Very small (~45 KB) | MIT | Low-moderate — minimal API surface, but less "batteries included" than a full charting framework (legends/panels are more manual) | Best fit if raw performance and small footprint matter most; least "framework-y" |
| **Plotly.js (with `scattergl`)** | WebGL (via `scattergl` trace type) or SVG/Canvas fallback | Good with `scattergl` for large point counts; SVG mode degrades much sooner | Built-in, including range-slider/range-selector patterns | Native via `plotly.js`'s subplot/shared-axis support | Supported via step-shape line traces | Large (hundreds of KB, more with full bundle) | MIT (core library) | Low to start (very batteries-included: legends, hover, export all built in), but the bundle size and general-purpose-chart surface area is more than Phase 2 strictly needs | Fastest to a polished-looking first result; heaviest dependency |
| **ECharts** | Canvas 2D (SVG optional), WebGL via extension | Good — has explicit large-dataset features (progressive rendering, `dataZoom`) | Built-in `dataZoom` component, well suited to exactly this use case | Native via `dataZoom` + `axisPointer` group linking | Supported via step line type | Large (similar order to Plotly) | Apache 2.0 | Low-moderate — very complete, but a bigger API surface to learn than uPlot | Strong middle ground; `dataZoom` in particular maps closely onto Phase 2's range-request model |

All three: actively maintained, permissively licensed, capable of handling
decimated/range-based data (none require raw full-resolution data
client-side), and viable as a foundation for later custom engineering
overlays (annotations, cursor readouts, calculated-channel traces) — none
of the three rules out later needs. **Not chosen based on popularity
alone** — bundle size and raw time-series throughput were weighted highest
given the stated performance-first requirement (§5 of the task, "Waveform
performance must be designed deliberately from the beginning").

**Recommended bounded prototype** (not to be built without explicit
instruction — described here so the shape is ready when authorized):

```text
Same synthetic COMTRADE fixture (already exists: backend/tests/fixtures/comtrade/synth_ascii)
Same channel count (a small multi-channel selection, e.g. 3 analog + 2 digital)
Same interaction requirements (zoom, pan, reset view, legend, cursor readout)
        ↓
Prototype A: uPlot
Prototype B: ECharts
        ↓
Owner evaluates: zoom/pan feel, readability at typical panel size,
responsiveness on a representative (not toy) point count, visual clarity
of digital step signals alongside analog traces
        ↓
Decision recorded in DECISIONS.md
```

Plotly.js is not included in the bounded prototype recommendation — its
bundle size is hard to justify for Phase 2's scope given the other two
already cover the required criteria; it remains a documented fallback if
both prototypes disappoint on ease-of-polish. Two prototypes, not three,
keeps the bounded trial genuinely bounded.

---

### 8. Basic Phase 2 scope and channel-selection UX

**Smallest useful Phase 2 feature set**: select one or more analog
channels → waveform display → time axis (elapsed seconds, per §11) →
engineering-unit Y axis → zoom → pan → reset view → channel legend →
source identity (station name, already shown in Phase 1's metadata step) →
responsive rendering. **Digital channels are recommended for a small
Phase 2.x refinement, not the very first slice** — reason: digital
step-signal rendering interacts with the decimation-ordering risk
identified in §2/§14 in a way analog channels don't, and folding that
design question into the very first proof-of-concept adds risk to proving
the core architecture (range requests, backend array retention, chosen
library) without a clear benefit — the first slice's job is to prove the
*pipeline*, not the *full channel-type coverage*.

**Channel-selection UX** — `[DECISION MODE: UAT]` (interaction-shaped,
per the framework's own guidance). Phase 1 already ships source metadata
review with Analog/Digital grouping, engineering-type subgroups, and
search — the question is how a channel moves from that browser into the
waveform workspace. Candidates:

- **Checkbox selection + "Open waveform workspace" button** — matches the
  existing browse-then-commit pattern Phase 1 already established (review
  metadata, *then* act), likely the most consistent extension of an
  already-UAT'd interaction model.
- **"Add to waveform" per-channel button** (like the existing per-source
  "Remove" button pattern) — channel-by-channel, immediate.
- **Click-to-toggle channel row** — fewer controls, but less discoverable
  as a multi-select action than a checkbox.
- Drag/drop is **not recommended** for consideration — no evidence this
  serves Phase 2's engineering-focused, keyboard/mouse-basic audience
  better than a checkbox, and it adds real implementation complexity
  (desktop-style interaction the task explicitly warns against
  reproducing).

Recommend the bounded UAT compare checkbox-selection-plus-button against
per-channel-add-button using the same Phase 1 metadata screen, asking
which feels faster/clearer for selecting 1 vs. several channels.

---

### 9. Panel model

**Minimum Phase 2 panel model**: one panel per engineering type actually
selected (Voltage, Current, Power, Frequency — reusing Phase 1's
already-shipped `engineering_type` classification, per §2's recommendation
— never re-derived), stacked vertically, sharing one X (time) axis. This
directly mirrors `powerwave`'s own default-panel behavior (§2) without
porting any of its implementation, and requires no new classification
logic to build.

**Left open for UAT**, since none of these can be confidently settled from
analysis alone and none block the smallest first slice: whether users
should be able to create custom panels (vs. automatic-only), whether
several related channels should ever share one panel by user choice (vs.
one-type-per-panel always), and whether Y axes should ever be
independent per curve within a shared-type panel (vs. always shared within
a panel, per §10). Phase 2's first slice can reasonably hard-code
"automatic grouping by engineering type, one panel per type, shared X
axis" and defer all of the above.

---

### 10. Analog scaling (Y axis)

Compare with `powerwave`: **not directly evidenced in the sections
audited this session** — PyQtGraph's own autoscale-to-visible-data is the
observed default behavior in the general codebase pattern (no explicit
fixed-range or per-record-range logic was found for the default view in
the files inspected). **Recommendation, `[DECISION MODE: ANALYSIS]`**:
autoscale to the *currently visible* (viewport) data, per channel, unless
multiple channels share a panel and a unit — in which case share one Y
axis scaled to the visible data of all curves in that panel (this avoids
a charting-library default silently becoming the engineering decision, per
the task's own instruction — an explicit choice: shared-scale-per-panel,
not per-curve, when units match). Autoscale-to-entire-record is not
recommended as the default, since it would defeat the purpose of zooming
into a transient (a small excursion could remain visually flat against a
Y range sized for the whole record) — this is the Y-axis analog of the
X-axis full-resolution-on-zoom principle in §12.

---

### 11. Time-axis handling

Phase 1's already-shipped `TimebaseOut` (`timing_reference`, `start_time`,
`trigger_time`, `sample_count`, `duration_seconds`, `sampling_rates`,
`samples_per_rate`) is the authoritative source for Phase 2's time axis —
no new backend timing model is needed. For single-source COMTRADE
specifically, `timing_reference` is always `"absolute"` by provider
construction (verified in the earlier discovery pass, §"Timestamp and
Sample-Rate Handling," unchanged). Phase 2 should display **elapsed time
from record start** (seconds) as the primary X-axis label — matching
`powerwave`'s own default behavior and the simplest, most universally
correct representation for a single record — with the absolute `start_time`
and `trigger_time` (if present) shown as context (e.g. in the panel header
or a hover tooltip), not as the axis's primary unit. Trigger-relative
axis framing is not needed for Phase 2 (§2's `viewport_policy.py` finding:
`powerwave` itself doesn't trigger-focus single-source views either).
Full-record duration is simply `duration_seconds` from the existing API;
current viewport is new client-side state (§17), not yet backend-known
until a range request is made.

---

### 12. Full-resolution zoom behavior — the core engineering requirement

> As the user zooms into a smaller time interval, the display should
> reveal appropriately higher-resolution detail rather than remaining
> permanently coarse.

Under **Option A** (send everything once): trivially satisfied, since the
full-resolution data is already client-side — zooming just re-renders a
subset of already-complete data. (This is Option A's one genuine
architectural advantage, and part of why it remains reasonable for a
*small*, bounded selection — §4.)

Under **Option B/D** (range requests, recommended): satisfied *by design*
— each zoom issues a new request for the new, narrower time range with the
same point budget, so the same point budget now represents proportionally
finer time resolution. This is the direct fix for the gap found in
`powerwave` itself (§3): the backend endpoint must decimate against the
**requested range**, never the full session window, which is the one
specific behavior of `build_aligned_data()` this design deliberately does
not port.

Under **Option C** (pyramid): satisfied by design, if built — but not
justified yet (§4).

**This principle should be treated as a hard engineering requirement for
whichever architecture is chosen**, not an optimization — it is what makes
the tool usable for its actual purpose.

---

### 13. Peak preservation

`powerwave`'s own decimator (§3) is confirmed **not** suitable — plain
stride sampling. For Phase 2's backend decimation, three real candidates:

- **Min/max envelope per pixel-bucket** — for each output "bucket" (one
  bucket per horizontal pixel or per point-budget slot), emit both the
  minimum and maximum sample value in that bucket (typically as two
  points, or a filled min-max band). Simple to implement, computationally
  cheap (`numpy`-vectorizable), and **guarantees no excursion is ever
  invisible** — a spike that touches the bucket's max or min is always
  represented, even if its exact index isn't. This is the standard
  approach for oscilloscope-style/disturbance-analysis tooling
  specifically because it cannot silently hide an extremum.
- **LTTB (Largest Triangle Three Buckets)** — a well-known, widely
  implemented algorithm that selects a representative point per bucket by
  maximizing the visual triangle area formed with neighboring buckets,
  producing a smoother, more visually faithful downsampled curve than
  naive stride sampling, while still being fast. Preserves *visual shape*
  well; does **not** guarantee capturing the single extreme min or max
  value in every bucket the way a min/max envelope does — a narrow, sharp
  spike could still be represented by a nearby-but-not-exact point rather
  than dropped, but the *exact peak value* is not guaranteed preserved
  numerically.
- **Pixel-bucket min/max, same as the first option, explicitly framed as
  the general "pixel-bucket" technique** — equivalent to the first
  bullet; listed separately in the task prompt but the same recommendation
  applies.

**Recommendation, `[DECISION MODE: ANALYSIS]`**: **min/max envelope
per bucket** for the analog waveform decimation endpoint. This is a
correctness/engineering-integrity decision, not a UX preference — for
protection/disturbance-event visibility, guaranteeing that a transient's
extremum is always represented outweighs LTTB's smoother visual shape.
LTTB could be offered later as an optional display-smoothing mode if
readability feedback during UAT calls for it, but should not be the
*only* or *default* mechanism given the stated priority on engineering
correctness over general dashboard aesthetics. General dashboard-chart
decimation defaults (as ship with most charting libraries, typically
naive stride or nearest-point sampling — the same category of algorithm
`powerwave`'s own decimator uses) are **not** suitable for this domain and
should not be relied upon as a library default without deliberately
choosing min/max envelope logic server-side.

---

### 14. Digital-signal preservation

If/when digital channels are added (Phase 2.x, per §8): the ordering risk
found in `powerwave` (§2/§3 — decimate-then-extract-transitions, which can
drop a narrow pulse before transition-extraction ever runs) must be
inverted for Phase 2.x: **extract transitions first, from the full-resolution
array, then decimate the resulting transition list (not the raw sample
array) for display** — a transition list is already far smaller than the
raw waveform (typically a handful to a few dozen transitions per channel
per record, versus thousands of raw samples), so it may not need
decimation at all in the typical case, and if it ever does, decimating a
transition list can preserve every transition's existence (just its exact
sub-pixel position) rather than being able to silently drop one entirely.
Digital channels' step-rendering also benefits from a genuinely different
wire representation than analog (a compact transitions-list: `[(time,
new_state), ...]`) rather than forcing digital data through the same
raw-sample-array endpoint shape as analog — this should be reflected in
the API design (§17) once Phase 2.x is scoped, not assumed to share
analog's exact request/response shape.

---

### 15. Browser memory model — estimate

Using representative Phase 2 scenarios rather than the full-file
extremes: a single analog channel decimated to a ~4000-point budget (§3's
observed reference number) is negligible browser memory regardless of the
source record's true sample count — a handful of `Float64Array`s at
thousands of elements each is kilobytes, not megabytes, per selected
channel/panel. **The risk scenario is Option A (§4) applied broadly**: if
a user selects many channels (the task's example: up to ~100 analog
channels) and the architecture sends full-resolution arrays for all of
them, browser memory scales directly with (channels × raw sample count) —
this is exactly the scenario Option B/D avoids by design, since payload
size there scales with (channels selected × point budget), not raw sample
count. **File size does not map directly to parsed/browser size** — do not
extrapolate a "100 MB file → X MB browser memory" figure without measuring
the actual parsed channel/sample-count shape (this is a real gap: Phase
1's own known blockers list already notes no measurement was taken near
the real ~100 MB upload ceiling — see [CURRENT_STATE.md — Known
blockers](CURRENT_STATE.md#known-blockers) — Phase 2's benchmark plan
(§29) should close this gap using a real high-channel-count fixture, not
a guess).

---

### 16. Backend memory model — the major architecture question

`[DECISION MODE: ANALYSIS]` (technical, not a UAT question — see §31).

**The problem, precisely**: Phase 1's `import_service.py` builds a full
`DisturbanceRecord` (including its full-resolution `waveform_data`
DataFrame) during upload, extracts lightweight `SourceMetadata` from it,
and **discards the record** — the `DisturbanceRecord` and its DataFrame go
out of scope at the end of `import_comtrade_source()`
(`backend/app/services/import_service.py`), by explicit design (module
docstring: *"Only lightweight SourceMetadata ... is kept afterward ...
never the DisturbanceRecord or its waveform_data DataFrame"*). Phase 2
range requests need access to the actual sample arrays, which no longer
exist anywhere after the upload request completes.

**What must change**: the active workspace must retain the parsed
`DisturbanceRecord` (or equivalently, its `waveform_data`) for the life of
the source, not just its lightweight summary — **without**:
- **Re-parsing the COMTRADE file per waveform request** — the file itself
  is never persistently stored (DEC-015 stays true; nothing here changes
  that), but the *already-parsed, in-memory* record must survive past the
  upload request so a later range request can slice it directly.
- **Persistent event-file storage** — this is about retaining an
  already-parsed in-memory object for the life of the ephemeral
  workspace/process, not writing anything to disk/database/object
  storage. DEC-015 governs the *file*; it says nothing about retaining
  parsed in-memory arrays, and should not be read as prohibiting that.
- **Unnecessary copies** — `waveform_data` is already held by reference,
  never copied, inside `DisturbanceRecord` (confirmed both in
  `oruxa_powerwave`'s ported domain model and in `powerwave`'s own
  original). A range-extraction implementation must slice/view rather
  than copy-then-slice wherever practical (NumPy/pandas slicing is
  typically a view, not a copy, when done carefully — this should be
  verified for whatever specific extraction code Phase 2A actually
  writes, not assumed).
- **Process-global cross-workspace coupling** — the retained record must
  stay scoped by `(workspace_id, source_id)`, exactly like
  `SourceMetadata` already is (DEC-012), never a bare global.

**Concrete architecture direction**: extend `WorkspaceRegistry`'s stored
value from `SourceMetadata`-only to something that also carries (or can
retrieve) the full `DisturbanceRecord` for that `(workspace_id,
source_id)` — e.g. a wrapper/session object holding both the existing
lightweight summary (already serialized for the channel-browse API, keep
using it there unchanged) and a reference to the parsed record (new,
consumed only by the waveform range-extraction endpoint). This is
additive to Phase 1's model, not a redesign of it — the existing
`SourceSummaryOut`/`SourceChannelsOut` API surface and its tests are
unaffected.

**RAM cost, honestly stated**: this is a real, direct increase in
per-source backend memory versus Phase 1's metadata-only model — the
full-resolution arrays that used to be discarded after upload will now
live for the source's lifetime. This is the necessary and unavoidable
cost of Phase 2's stated goal (serving range requests without re-parsing);
it should be sized against real measurements (§15/§29's benchmark plan),
not assumed acceptable by default, and is the direct reason §18's TTL
question becomes materially more urgent for Phase 2 than it was for
Phase 1.

---

### 17. Revisit Phase 1 source lifecycle

**Source object structure**: extend, don't replace — a new wrapper (name
TBD at implementation time, e.g. an "active source" or "loaded source"
concept) holding the existing `SourceMetadata` plus the retained
`DisturbanceRecord`, keyed identically to today
(`workspace_id`/`source_id`). The existing `WorkspaceRegistry.add/get/
list_for_workspace/remove/remove_workspace` methods (all shipped, tested,
DEC-012/DEC-018-governed) need their *stored value type* widened, not
their *keying/ownership model* redesigned — `remove()` and
`remove_workspace()` (both already correct — see the Phase 1
Workspace-Reset Record above) already do exactly the right thing
structurally: dropping the dict entry drops the only reference to
whatever object is stored there, whether that's today's lightweight
`SourceMetadata` or tomorrow's metadata-plus-record wrapper. **No change
to workspace reset or source-remove *behavior* is anticipated** — both
already correctly release every reference they own; they simply start
owning a larger object.

**Ownership**: unchanged — per-workspace, per-source, exactly as DEC-012
already establishes.

**Cleanup**: unchanged mechanism (`remove()`/`remove_workspace()`), larger
consequence (releasing a full-resolution record instead of a lightweight
summary) — which is exactly why §18's TTL question needs re-weighting now.

**Multiple-source future readiness**: nothing about this extension
forecloses Phase 3's multi-source work — the registry already supports
multiple sources per workspace today (verified by Phase 1's own
multi-source workspace-reset tests); Phase 2 doesn't need to design
anything additional for that scenario, since it was already built into
the registry's shape from Phase 1.

**Conclusion**: **extend the existing model, don't complement it with a
separate parallel structure.** A second, separate "waveform-serving"
registry alongside `WorkspaceRegistry` would duplicate the
workspace/source keying, lifecycle, and cleanup logic already correctly
built and tested — a clear violation of the project's own "don't
introduce abstractions beyond what the task requires" principle.

---

### 18. Abandoned-session TTL — reassessed for Phase 2

`[DECISION MODE: COMPARISON]` — **this becomes materially more important
than it was for Phase 1**, though whether it's an outright *blocker* is a
judgment call the owner should make with the tradeoffs below in view, not
one this analysis can fully settle alone (hence comparison, not pure
analysis).

**Why it matters more now**: Phase 1's abandoned-workspace cost was
bounded — lightweight metadata only (channel names/units/counts/timing,
no sample arrays). Phase 2's abandoned-workspace cost is **the full
retained `DisturbanceRecord`**, potentially per source, per abandoned
workspace, accumulating indefinitely with zero automatic release (per the
existing, still-true `[OPEN]` item in
[CURRENT_STATE.md](CURRENT_STATE.md#known-blockers)) until the backend
process restarts. Every additional abandoned tab/browser session is now a
real, potentially large chunk of resident memory, not a few KB of
metadata.

**Options compared**:

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| Fixed inactivity TTL | Track last-access time per source/workspace; a periodic sweep evicts entries idle beyond a threshold | Simple, predictable, bounded worst-case memory | Picking the right threshold is itself a judgment call (too short: surprises an engineer mid-analysis who stepped away; too long: doesn't bound memory tightly) |
| Periodic cleanup (sweep) | Same as above, framed as the *mechanism* rather than the policy — a background task run on an interval | Same as above; this is really the same option, described from the implementation angle | Same as above |
| Explicit heartbeat | Frontend periodically pings "I'm still here" for its active workspace; absence of heartbeats beyond a threshold triggers cleanup | More accurate signal of genuine abandonment than a fixed TTL (an actively-used-but-idle-on-the-waveform tab still heartbeats) | More moving parts (a new endpoint, a client-side timer); a network blip could cause premature cleanup unless designed with tolerance |
| `sendBeacon` cleanup on tab close | Browser's `navigator.sendBeacon()` fires a best-effort request as the tab closes, triggering explicit cleanup | Catches the common "closed the tab" case cleanly and promptly, complementing (not replacing) a TTL for the cases it can't catch (crash, network loss, force-quit) | Not reliable alone — `sendBeacon` is not guaranteed to fire/arrive in every browser-close scenario, so it cannot be the *only* mechanism |
| Combination (TTL + `sendBeacon`) | `sendBeacon` handles the common graceful-close case promptly; TTL is the backstop for everything else | Best coverage of realistic abandonment scenarios without over-engineering | More to build than any single mechanism alone |
| Defer, with hard memory limits instead | Don't build any expiry mechanism yet; instead cap total registry memory/source count and reject new uploads (or evict oldest) once a ceiling is hit | Least new mechanism to build; converts "unbounded leak" into "bounded but potentially confusing rejection behavior" | Doesn't solve the underlying problem, just bounds its blast radius; a busy shared DEV/demo environment could hit the ceiling and start rejecting legitimate new uploads while genuinely abandoned old ones sit untouched |

**Recommendation for owner comparison, not pre-decided**: the
**combination (TTL + `sendBeacon`)** gives the best realistic coverage for
the least complexity beyond a single mechanism, and directly addresses
the specific new risk Phase 2 introduces (large retained arrays, not just
metadata). **Defer-with-hard-limits** is a legitimate, meaningfully
simpler fallback if the owner judges Phase 2A/2B's actual DEV-environment
usage pattern (a handful of active sessions, not concurrent public
traffic) doesn't yet justify building real expiry — but this should be an
explicit, informed choice given the memory-growth consequence is now
materially different from Phase 1, not an unexamined carry-forward of
Phase 1's "not needed yet" conclusion.

**Is this a hard Phase 2 blocker?** Not for **Phase 2A's own
implementation and testing** (a controlled environment, small number of
manually-driven sessions) — but it should be resolved (one of the options
above, explicitly chosen) **before Phase 2 work is considered
UAT-ready on a shared DEV environment for any extended period**, since
that's exactly the condition under which unbounded retained-array growth
would first become a real, observable problem rather than a theoretical
one.

---

### 19. Session concurrency

Minimum concurrency controls needed for Phase 2, evidenced by the
scenarios in the task prompt:

- **Same browser, multiple tabs, same `workspace_id`** (since
  `workspace_id` is stored in `localStorage`, shared across tabs of the
  same origin): both tabs already correctly share one workspace's sources
  today (Phase 1) — this extends unchanged to waveform requests, since
  reads (`GET` range requests) against a shared in-memory record are
  naturally safe without new locking, the same way Phase 1's existing
  `GET` endpoints already are.
- **Two browsers, different `workspace_id`s**: already fully isolated by
  the existing `(workspace_id, source_id)` keying (DEC-012) — nothing new
  needed.
- **Multiple simultaneous requests against one workspace**: Phase 1's
  `WorkspaceRegistry` already uses a `threading.Lock` for
  add/get/list/remove/remove_workspace — range-extraction reads should
  follow the same pattern (acquire briefly to *retrieve* the record
  reference, then release the lock before doing the actual — potentially
  slower — decimation work against that reference, so a slow decimation
  computation never holds the registry lock and blocks unrelated
  requests).
- **A workspace deleted during a waveform request**: the existing
  `remove()`/`remove_workspace()` already drop the registry entry
  atomically under the lock; an in-flight range request that already
  retrieved its record reference *before* the delete can safely finish
  serving from that reference (Python's GC won't collect an object still
  referenced by a local variable in an in-progress request handler, even
  after the registry's own reference is dropped) — a request that hasn't
  yet retrieved the reference when the delete happens should get the
  existing `source_not_found` 404, exactly like Phase 1's existing
  get-after-delete behavior for metadata.

**No new authentication/session-identity work is needed for Phase 2** —
this analysis only concerns concurrent access to shared in-memory
structures, not per-user isolation (Phase 9, explicitly out of scope,
per DEC-... n/a — already established Milestone 1 scoping).

---

### 20. API proposal

`[DECISION MODE: ANALYSIS]` for the shape below (versioning, resource
naming, and general request/response conventions are ordinary internal
engineering choices, following the same pattern Phase 1 already
established) — **not** a UAT question.

```text
GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform
```

**Request parameters** (query string, matching FastAPI/Phase 1 convention):
- `channels` — one or more channel names (repeated query param, e.g.
  `channels=VA&channels=VB`), required. Mirrors how a specific, bounded
  request is always more scalable than "give me everything" (§4).
- `start_time` / `end_time` — seconds, elapsed from record start (§11),
  optional; default to the full record duration when omitted (this is
  exactly the "initial load" case, §16 — no separate overview endpoint
  needed, per §4's Option D note).
- `max_points` — optional, defaults to a sensible constant (recommend
  starting from `powerwave`'s own proven-in-practice `4000`, §3, subject
  to revision once the benchmark plan, §29, has real numbers).

**Response** (Phase 2A's first implementation, per §5's recommendation —
start with JSON, revisit binary only if measured necessary):
```json
{
  "source_id": "...",
  "start_time": 0.0,
  "end_time": 1.284,
  "channels": [
    {
      "name": "VA",
      "unit": "V",
      "point_count": 3982,
      "time": [0.0, 0.00032, ...],
      "values": [1.02, 1.05, ...]
    }
  ]
}
```
A shared `time` array per channel (not one shared array for all
channels) deliberately preserves §28's "avoid hidden resampling"
principle — each channel keeps its own native sample positions, exactly
matching both `powerwave`'s behavior and Phase 1's existing per-channel
timing model; nothing forces channels onto a common grid even if they
happen to already share one.

**Error cases**, matching Phase 1's existing `{"detail": {"code",
"message"}}` shape:
- `source_not_found` (404) — same as Phase 1's existing sources endpoints.
- `channel_not_found` (400/404 — exact code TBD at implementation, but
  the pattern is established) — requested channel name doesn't exist on
  this source.
- `invalid_time_range` (400) — `start_time`/`end_time` out of bounds or
  inverted.
- `invalid_workspace` (400) — same blank-id validation Phase 1 already has.
- A request-too-large / point-budget-exceeded case is structurally
  prevented by `max_points` being a server-enforced ceiling, not a
  client-trusted value — mirrors the existing upload-size enforcement
  pattern (client value is a courtesy, server value is authoritative).

**Time-range semantics**: half-open-friendly, inclusive of samples whose
time falls within `[start_time, end_time]`, exactly matching the clipping
logic already proven correct in `build_aligned_data()`'s approach (the
*range-clipping* logic, not its *decimation* algorithm — §3's distinction).

**Channel identity**: by name, consistent with how Phase 1's existing
`GET .../channels` response already identifies channels — no new
identity scheme needed.

This is not implementation — the exact error-code strings, response field
names, and default `max_points` value should be finalized during Phase 2A
itself, informed by the benchmark plan (§29).

---

### 21. Avoid hidden resampling

Directly addressed by §20's response shape (a `time` array per channel,
not one shared array) and reaffirmed here as an explicit principle: Phase
2 must **not** resample multiple selected channels from the same source
onto a common time grid, even when they happen to share an identical
native timebase today (COMTRADE's typical case) — doing so silently would
establish an assumption ("channels share a grid") that Phase 3's
multi-source work (genuinely different sample rates across sources) would
then have to either awkwardly preserve or visibly break. Keeping every
channel's own native time array from day one costs nothing now and avoids
a future breaking change.

---

### 22. Caching strategy

`[DECISION MODE: ANALYSIS]` — recommend the minimum that gives clear
benefit, per the task's own instruction against premature complexity:

- **Cache the parsed source arrays**: not really a "cache" so much as the
  core of §16's proposal itself — the retained `DisturbanceRecord` *is*
  this, already recommended, not an additional layer.
- **Cache decimated ranges**: **not recommended for Phase 2A.** Adds real
  complexity (cache key design around channel-set + range + point-budget,
  invalidation on source removal) for a benefit that should be measured,
  not assumed — if range-extraction-plus-decimation against an
  already-in-memory array proves fast (§29's benchmark plan should
  confirm or deny this), a per-request cache buys little. Revisit only if
  benchmarking shows decimation itself (not network/serialization) is the
  bottleneck.
- **Cache a full overview representation**: effectively already covered
  by §20's "omit start/end_time defaults to full record" behavior — no
  separate precomputed/cached overview object is needed unless repeated
  full-record requests are measured to be a real cost, which is unlikely
  given the retained array is already in memory.
- **Cache per-channel recent viewport data**: same reasoning as decimated
  ranges above — defer until measured necessary.

**Recommendation**: build nothing beyond §16's retained-array proposal for
Phase 2A. This keeps the implementation maintainable for a solo developer
(an explicit stated priority) and matches the project's established
pattern of not building speculative infrastructure ahead of a
demonstrated need.

---

### 23. Initial-load UX

Preserves the owner's confirmed Phase 1 preference (DEC-017's underlying
UAT finding: simple, understandable, comfortable workflow; metadata
review before deeper interaction) — this flow does not skip or shortcut
that review step:

```text
Upload COMTRADE (existing Phase 1 flow, unchanged)
        ↓
Review source metadata / channel list (existing Phase 1 flow, unchanged
  — collapsible Analog/Digital groups, engineering-type subgroups, search)
        ↓
Select channel(s) for the waveform workspace (new, §8)
        ↓
"Open waveform workspace" (new)
        ↓
Initial waveform request: GET .../waveform?channels=...  (no start/end_time
  → full record, per §20's default; point budget per the established
  reference constant)
        ↓
Waveform renders — zoom/pan available immediately
```

Nothing about Phase 2 changes the existing upload/metadata screen; it is
purely additive, entered only once the user has already reviewed metadata
and explicitly chosen to proceed — exactly preserving the successful
Phase 1 UX rather than jumping straight to a waveform on upload.

---

### 24. Loading states

- **First waveform load**: a loading indicator matching Phase 1's existing
  spinner pattern (already used for both upload-parsing and
  channel-list-loading) — no new visual language needed, reuse what's
  already UAT'd.
- **Additional channel load** (adding a channel to an already-open
  workspace, if Phase 2B supports it): should not block the
  already-rendered panels — an incremental, per-request loading indicator
  scoped to the new channel/panel only, not a full-page block.
- **Zoom-range fetch**: should feel interactive, not "loading" in the
  traditional sense — a brief, subtle in-panel indicator (not a full
  spinner takeover) if the request takes long enough to be noticeable;
  the performance target (§27) is for this to rarely be needed at all.
  Optimistic local pan (moving the already-rendered points before the
  fresh higher-resolution data arrives) is **not recommended** as a
  default — it risks showing engineering data that doesn't yet reflect
  the true resolution for the new range, which conflicts with §12's core
  correctness requirement; a brief, honest loading state is safer than an
  optimistic one that could visually mislead mid-transition.
- **Failure**: a clear, source-specific error message, following Phase
  1's established `friendlyErrorMessage()` pattern (map structured error
  codes to plain-language text) rather than a generic failure banner.
- **No data**: a channel with zero samples in the requested range (e.g. a
  very narrow zoom past the record's actual extent) should render an
  explicit "no data in this range" state, not an empty/blank panel that
  could be mistaken for a loading or broken state.
- **Very large range**: bounded structurally by `max_points` (§20) — a
  "large range" request is never actually large on the wire, since the
  server always caps the response to the point budget regardless of how
  wide the requested time range is; no special UX case is needed beyond
  the general loading indicator.

---

### 25. Error handling

Matches §20's error cases, presented per Phase 1's existing pattern
(`friendlyErrorMessage()`-style code-to-message mapping, never a raw
traceback):

| Error | User-facing handling |
|---|---|
| Source removed (mid-session, e.g. via `Remove` in another tab) | "This source is no longer available in this workspace." — exact wording already exists in Phase 1's `friendlyErrorMessage()` for `source_not_found`, reusable verbatim |
| Workspace reset/expired | Same `source_not_found`-style handling; if the *workspace* itself was reset, the waveform view should recognize this and return the user to the empty-workspace state rather than showing a persistent error for a source that will never come back |
| Invalid channel | "This channel isn't part of this source." — new, mirrors the existing pattern |
| Invalid time range | "That time range isn't valid for this recording." — new |
| Request too large / server memory limit | Structurally prevented by server-enforced `max_points` (§20) — if it somehow still occurs (e.g. a future very-high-channel-count multi-select), fall back to the existing `internal_error`/generic-failure pattern rather than a new bespoke message, since this should be rare-to-never by design |
| Waveform preparation failure (unexpected parse/extraction error) | Generic "Something went wrong preparing this waveform. Please try again." — matches Phase 1's existing `internal_error` pattern; full detail logged server-side only, never returned to the client (established Phase 1 principle, unchanged) |

---

### 26. Performance targets

Practical, not arbitrary — proposed for measurement during Phase 2A
implementation/UAT, not invented as strict numbers today:

- **Initial visible waveform** should appear quickly (target: comparable
  to Phase 1's already-observed channel-list load feel — no hard
  millisecond figure invented here; measure and compare against that
  existing, already-UAT'd-as-"responsive" baseline) for a representative
  COMTRADE file (the existing synthetic fixtures, plus a larger
  non-confidential sample if one becomes available, §29).
- **Zoom/pan should feel interactive** — the working definition: a
  user's zoom/pan action should not feel like it's "waiting for a page
  load"; this is necessarily a UAT judgment (§7's plotting-library
  prototype is exactly where this gets tested), not a number this
  analysis can set alone.
- **Payload should scale with viewport/point budget, not full file
  size** — this is a structural/architectural guarantee of the
  recommended design (§4/§20), not a soft target — it should hold by
  construction, and the benchmark plan (§29) should confirm it does.
- **Browser should remain responsive with a representative number of
  traces** — "representative" should be defined from real Phase 1 UAT
  data: the owner's own example record had 103 analog / 362 digital
  channels; Phase 2's benchmark should include a realistic *selected*
  subset (a handful of channels open at once, not all 103+362
  simultaneously, since nothing in Phase 2's UX proposes opening every
  channel into the waveform workspace at once).

**What should be measured during implementation/UAT**: time-to-first-render
for the initial waveform request; time-to-render for a zoom/pan-triggered
range request; payload size per request at a few representative
zoom depths; browser memory after opening a representative number of
panels/channels; backend memory added per retained source (§16's honest
cost); and the actual behavior of the chosen decimation algorithm (§13)
against a fixture with a known, deliberately-placed transient, to confirm
it's never silently dropped (this is also an engineering-correctness
test, §27, not just a performance one).

---

### 27. Engineering correctness tests

Design (not implement) test coverage for Phase 2A, extending Phase 1's
established pattern of exact-value parity testing:

- **Waveform values at known indices/times**: a range request for a known
  time window against the existing synthetic COMTRADE fixtures
  (`synth_ascii`/`synth_binary`) should return exactly the expected
  sample values at the expected times — direct extension of the existing
  parity-testing discipline (`test_comtrade_parity.py`) into the new
  range-extraction code path.
- **Range extraction correctness**: requesting `[start_time, end_time]`
  should return only samples within that window (boundary-inclusive per
  §20), verified against hand-computed expected indices for the synthetic
  fixture.
- **First/last sample**: a full-record request (no `start_time`/
  `end_time`) should include the record's true first and last sample —
  an easy off-by-one to introduce in a range-clipping implementation,
  worth a dedicated test.
- **Trigger-relative timing**: not applicable to Phase 2A's elapsed-time
  axis (§11) — defer this test category until/if trigger-relative display
  is actually built (not currently in Phase 2's scope).
- **Min/max preservation**: a fixture with a deliberately-placed,
  narrow (sub-bucket-width) synthetic spike, decimated at a point budget
  that would collapse it under naive stride sampling — the chosen
  min/max-envelope algorithm (§13) must still surface that spike's true
  extreme value in the decimated output. This is the single most
  important new test category Phase 2A introduces, directly testing the
  core engineering-safety finding of this whole design pass (§3/§13).
- **Decimation behavior generally**: point count in the response never
  exceeds the requested/default `max_points`; a request whose raw sample
  count is already under the budget returns full resolution unchanged
  (no decimation artifacts introduced when none are needed).
- **Zoomed-detail recovery**: a narrower time-range request at the same
  point budget should return measurably finer time resolution (smaller
  average inter-sample spacing in the response) than a full-record
  request — a direct, automatable test of §12's core principle.
- **Channel ordering**: response channel order matches the request's
  `channels` parameter order (or another explicit, documented rule) —
  simple but easy to get accidentally wrong.
- **Units**: response reflects the same `unit` already established by
  Phase 1's channel metadata — no unit conversion/mismatch introduced by
  the waveform endpoint.
- **Source cleanup during/after waveform use**: extending Phase 1's
  existing removal/reset test pattern — after `Remove` or `Start new
  workspace`, a subsequent waveform request for the now-gone source
  returns `source_not_found`, exactly like the existing metadata
  endpoints already correctly do; and (per §16/§17) the retained record's
  memory is actually released, not merely inaccessible (a
  reference-counting-style test, matching the rigor already applied to
  Phase 1's `remove_workspace()` — see `test_workspace_registry.py`'s
  existing pattern).

Reuse `powerwave`'s existing fixtures where authorized: the already-committed
synthetic fixtures are sufficient for the above; the one previously-used
real, uncommitted sample (`PTAI_MVLY_relay.CFG`, used for Phase 1's parity
testing, per the confidentiality note already established) could extend
coverage to a higher-channel-count scenario if still available locally,
but this is optional, not required, for Phase 2A's design to proceed.

---

### 28. Performance benchmark plan

Scenarios, using fixtures already available or easily added without new
confidentiality concerns:

- **Small synthetic COMTRADE** (existing `synth_ascii`/`synth_binary`,
  40 samples, 3 analog + 2 digital) — establishes a correctness/speed
  floor; not meaningful for performance conclusions alone given its tiny
  size, but useful as the fast-running default in CI-style checks.
- **Medium, higher-sample-count synthetic fixture** (new — a synthetic
  fixture authored specifically for this benchmark, at a realistic
  COMTRADE sample rate/duration, e.g. a few thousand to tens of thousands
  of samples per channel, generated the same way Phase 1's existing
  synthetic fixtures were, to avoid any confidentiality concern).
- **High-channel-count fixture** — matching the owner's own Phase 1 UAT
  example shape (103 analog / 362 digital) as closely as a synthetic
  fixture reasonably can, to benchmark the "many channels exist on the
  source, only a few are selected for waveform display" scenario
  specifically (§8's scope), not "all channels rendered at once" (not a
  Phase 2 use case).
- **A larger file approaching the currently-supported 100 MB guidance**
  — only if a safe, non-confidential fixture can be produced (synthetic
  generation, scaled up) — this directly closes the existing `[OPEN]` gap
  noted in [CURRENT_STATE.md](CURRENT_STATE.md#known-blockers) about no
  measurement having been taken near the real upload ceiling; worth doing
  as part of Phase 2A specifically because Phase 2A is the point at which
  that ceiling starts to matter for retained backend memory (§16), not
  just upload-time memory.

**What to measure**, per scenario: backend parse-and-retain memory
(confirming/replacing §15's estimate with real numbers); range-extraction
latency; decimation latency (isolated from extraction, to know which step
dominates); serialization time and resulting payload size (confirming or
revising §5's "start with JSON" recommendation); browser render time for
the initial waveform and for a representative zoom/pan sequence; and
browser memory after a representative multi-channel selection is open.

---

### 29. Candidate Phase 2 UAT Decisions

Collected from throughout this document, for owner visibility as a single
list:

- **Plotting library** (§7) — uPlot vs. ECharts, bounded two-prototype
  trial recommended; Plotly.js as a documented fallback, not part of the
  bounded trial.
- **Channel-selection/add interaction** (§8) — checkbox-plus-button vs.
  per-channel add-button, tested against the existing Phase 1 metadata
  screen.
- **Panel layout beyond the Phase 2A minimum** (§9) — custom panels,
  multi-channel-per-panel by user choice, independent-Y-axis-per-curve —
  all deferred, worth a UAT pass once Phase 2A's automatic-grouping
  minimum is in front of the owner and a real opinion can form from
  actual use rather than abstract description.
- **Zoom behavior feel** (§26) — whether the chosen architecture's actual
  zoom/pan responsiveness feels interactive enough in practice; inherently
  a hands-on judgment, not decidable from this document alone.
- **Autoscale behavior** (§10) — the recommended shared-scale-per-panel
  default is offered as `[DECISION MODE: ANALYSIS]`, but if the owner's
  first hands-on impression during the plotting-library prototype (§7)
  suggests otherwise, it's cheap to fold into that same trial rather than
  treating it as fully separate.
- **Legend layout/placement** — not analyzed in depth in this pass (out
  of the highest-priority findings); a natural, low-cost addition to
  whichever plotting-library prototype is run, rather than a
  separate trial.
- **Analog grouping presentation on the waveform page itself** (as
  distinct from the already-decided Phase 1 metadata-screen grouping) —
  whether panel headers/legends should visually echo the same
  Voltage/Current/Power/Frequency grouping language, worth confirming
  feels consistent once a real prototype exists.

---

### 30. Decisions that should be technical, not UAT

Explicitly not burdening the owner with these — all are ordinary
engineering choices with enough evidence for a confident recommendation:

- **API versioning and resource naming** (§20) — follows the exact
  pattern Phase 1 already established (`/api/v1/workspaces/{id}/sources/{id}/...`);
  no new precedent being set.
- **Source ownership / registry keying** (§17) — extends, doesn't change,
  the already-approved `(workspace_id, source_id)` model (DEC-012).
- **Full-resolution backend authority** (§1/§16) — a restatement of a
  principle already implicit in Phase 1's architecture and in
  `powerwave`'s own (mostly honored) design; not a new product question.
- **Lifecycle cleanup mechanics** (§17) — extending the already-correct,
  already-tested `remove()`/`remove_workspace()` pattern; only the *TTL
  policy choice* (§18) rises to owner-visible comparison, not the
  underlying cleanup mechanism itself.
- **Memory safety / concurrency locking pattern** (§19) — a direct,
  low-risk extension of Phase 1's existing `threading.Lock` pattern.
- **Binary-vs-JSON transfer format** (§5) — recommended to start with
  JSON and revisit only if benchmarking (§28) shows a real cost; this is
  a measured-engineering decision, not a product preference.
- **Peak-preservation algorithm choice** (§13) — min/max envelope,
  recommended on engineering-correctness grounds (protection/disturbance
  visibility), not a matter of taste.

---

### 31. Recommended Phase 2 implementation slices

`[PROPOSAL]`, sequenced by risk and dependency, following the same
approach the original discovery audit used for the overall migration
phases:

```text
Phase 2A — Retain full-resolution active source + waveform range API
  Backend only: extend WorkspaceRegistry's stored value (§16/§17),
  add GET .../waveform (§20) with viewport-aware, min/max-envelope
  decimation (§3/§13). No frontend chart yet — verified via API
  tests only (JSON response, inspectable directly), matching Phase
  1's own backend-first sequencing discipline.

Phase 2B — Single-channel web waveform prototype
  Frontend: the chosen (or provisionally chosen, pending §7's UAT)
  plotting library renders one selected analog channel using Phase
  2A's API. Proves the full pipeline end-to-end for the narrowest
  possible case. This is the natural point to actually run the
  bounded plotting-library prototype (§7), since it needs a real
  API to render against anyway.

Phase 2C — Multi-channel / panel interaction
  Multiple channels, automatic panel grouping by engineering_type
  (§9), shared X axis, legend, channel-selection UX (§8) wired to
  the real workspace metadata screen.

Phase 2D — Digital traces / refinements
  Digital channel support (§14's transitions-first approach), any
  UAT findings from 2B/2C folded in (autoscale, legend placement,
  etc.), TTL mechanism (§18) if the owner has by then decided it's
  needed before broader UAT exposure.
```

This sequencing deliberately proves the riskiest new architecture
(backend array retention + range API, §16 — genuinely new work with no
existing precedent in either codebase) before spending effort on the
plotting-library choice (§7 — real work, but lower architectural risk,
and benefits from having a real API to prototype against rather than
mocked data).

---

### 32. Recommended first implementation slice — exact scope

```text
An existing, already-uploaded COMTRADE source (Phase 1, unchanged)
        ↓
Backend retains its full-resolution analog waveform data for the
  life of the workspace (§16/§17 — WorkspaceRegistry extension)
        ↓
New endpoint: GET .../sources/{source_id}/waveform?channels=X
  (§20) — one analog channel, full record range (no start/end_time
  yet), min/max-envelope decimation (§13) capped at a default
  max_points
        ↓
Verified via backend API tests only (§27's correctness tests) —
  no frontend chart rendering yet
```

**Why this slice, not a larger one**: it isolates and proves the single
riskiest, least-precedented piece of Phase 2 — backend retention of
full-resolution arrays plus a correct, viewport-aware, peak-preserving
decimation endpoint — without simultaneously deciding the plotting
library (§7, genuinely needs its own UAT), the channel-selection UX (§8,
also UAT-shaped), or the panel model (§9, partly UAT-shaped). This
mirrors exactly the reasoning the original discovery audit used for
Phase 1's own first slice: prove the hardest new architectural question
first, in isolation, before layering UX decisions on top of it.

**Exact scope exclusions for this first slice**:
- Multi-source synchronization — not touched (Phase 3+).
- Calculated signals — not touched (Phase 6+).
- Measurements/cursors — not touched at all, not even minimally (Phase 5).
- CSV/Excel — not touched (Phase 1.5, separately scoped, still not
  started).
- Advanced analysis — not touched (Phase 7).
- Project persistence — not touched (Phase 8; DEC-015's ephemeral
  principle is unaffected either way).
- Authentication — not touched (Phase 9, Milestone 1 exclusion).
- **Digital signals — explicitly excluded from this first slice** (§8/§14
  — the transitions-first design needs its own care and shouldn't
  complicate proving the core array-retention/range-API architecture).
- Multi-channel selection — the first slice is deliberately **one**
  channel; Phase 2C, not this slice, adds multiple.
- Frontend chart rendering — this slice stops at a verified API; Phase 2B
  is where a browser first renders anything.
- Zoom/pan UI — depends on Phase 2B's chart existing at all; this slice
  proves the *API* supports arbitrary range requests (tested directly,
  not through a UI), not a rendered interactive zoom experience yet.

---

### Closing note on decisions

**No entry was added to DECISIONS.md by this pass.** Every architectural
direction above — the data-delivery architecture (§4), transfer format
(§5), plotting library (§7), decimation algorithm (§13), backend memory
model (§16), and TTL approach (§18) — remains a `[PROPOSAL]` or an item
under one of the three decision modes (`ANALYSIS`/`COMPARISON`/`UAT`),
per this task's explicit instruction not to silently approve any of them.
The one already-true fact recorded elsewhere this pass (Phase 1's final
UAT having passed) is a completion state, not a new architectural
decision, and is recorded in [CURRENT_STATE.md](CURRENT_STATE.md) rather
than here.

---

## Phase 2A — Waveform Data Foundation Implementation Record (2026-08-15)

Implements the backend foundation the Phase 2 design section above
recommended as the first vertical slice (§32). **Backend only — no chart
library, no frontend waveform rendering, no Phase 2B/2C/2D work.** See
DEC-019 ([DECISIONS.md](DECISIONS.md)) for the approved decision this
implements; this section is the implementation record.

### Architecture implemented

```text
ActiveSource (app/domain/source.py)
    metadata: SourceMetadata   -- unchanged Phase 1 shape/behaviour
    record:   DisturbanceRecord -- authoritative, full-resolution,
                                    retained for the source's lifetime
        |
WorkspaceRegistry (app/services/workspace_registry.py)
    stores ActiveSource per (workspace_id, source_id) -- same keying,
    locking, and remove()/remove_workspace() cleanup as Phase 1;
    only the stored value type widened
        |
extract_waveform_range() (app/services/waveform_service.py)
    exact-range extraction (always, from the authoritative record)
        -> full_resolution response, if range fits point_budget
        -> build_min_max_envelope() (app/domain/waveform_reduction.py)
           display representation, otherwise
        |
GET .../sources/{source_id}/waveform (app/api/v1/sources.py)
    -> WaveformRangeOut (app/schemas/waveform.py), JSON
```

`import_service.py` now builds `ActiveSource(metadata=metadata,
record=record)` and stores it via `registry.add(...)`, instead of
discarding `record` after building `metadata` — the one behavioural
change to the upload path; its response contract (`SourceSummaryOut`) is
unchanged. `app/api/v1/sources.py`'s existing endpoints (`list`, `get`,
`channels`, `delete`) were updated only to unwrap `.metadata` from the
now-`ActiveSource`-typed registry value — their request/response
contracts and behaviour are unchanged, confirmed by all 227
previously-passing tests still passing unmodified.

### Authoritative data fidelity

**Confirmed unchanged and never mutated.** `record.waveform_data` is the
exact `DisturbanceRecord` `ComtradeProvider().load()` produced — no copy,
no in-place modification, anywhere in the new code. Verified directly:
`tests/test_waveform_service.py::TestNoMutationOfAuthoritativeData`
extracts a range and then asserts the source DataFrame's values are
byte-for-byte unchanged; `app/domain/waveform_reduction.py`'s own tests
(`TestNoMutation`) separately confirm the reduction function never writes
into or returns a view of its input arrays. `app/providers/comtrade.py`
and `app/providers/base.py` were **not touched** — the existing COMTRADE
parity tests (`tests/test_comtrade_parity.py`) pass unmodified.

### Waveform API

```text
GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform
    ?channel_name=<analog channel name, required>
    &start_time=<float, optional>
    &end_time=<float, optional>
    &point_budget=<int > 0, optional, default 4000>
```

**Channel identity**: `channel_name` — the same stable `name` field
already used as the identity for every analog channel in Phase 1's
`GET .../channels` response; never a display/table position. A digital
channel name is rejected with `channel_not_analog` (400); an unknown name
with `channel_not_found` (404).

**Time semantics**: `start_time`/`end_time` are elapsed seconds on the
source's own native time axis — the exact same values as
`waveform_data["time"]` and the already-shipped `TimebaseOut`
(COMTRADE's `timing_reference` is always `"absolute"` by provider
construction; this endpoint does not introduce a second, trigger-relative
axis). Boundary-inclusive at both ends. Omitting a bound defaults it to
the record's own true start/end — omitting both returns the entire
record. `start_time > end_time` is rejected as `invalid_time_range`
(400). A range fully before or after the record is **not** an error —
defined, tested behaviour: an empty response
(`original_sample_count: 0`, `time: []`, `values: []`).

**Point-budget semantics**: a *display-response budget*, not an
engineering-resolution setting. If the resolved range's raw sample count
is `<= point_budget`, the exact full-resolution range is returned
unchanged (`representation: "full_resolution"`). Otherwise a
peak-preserving min/max envelope is returned instead
(`representation: "min_max_envelope"`) — the returned point count is
close to, but not contractually equal to, `point_budget` (documented in
both the schema and the reduction function's own docstring, per the
task's explicit instruction not to advertise an exact cap the algorithm
intentionally exceeds).

**Response** (JSON, `app/schemas/waveform.py`):
```json
{
  "source_id": "...",
  "channel_name": "VA",
  "unit": "V",
  "start_time": 0.0,
  "end_time": 1.284,
  "original_sample_count": 5001,
  "returned_point_count": 3982,
  "representation": "min_max_envelope",
  "time": [...],
  "values": [...]
}
```

**Errors** (same `{"detail": {"code", "message"}}` shape as every other
Phase 1 endpoint): `source_not_found`/`invalid_workspace` (existing,
reused unchanged), `channel_not_found` (404), `channel_not_analog` (400),
`invalid_time_range` (400); a malformed/non-positive `point_budget` or a
missing `channel_name` is rejected by FastAPI's own query validation
(422), consistent with the existing multipart-upload validation pattern.

### Display preparation

`app/domain/waveform_reduction.py::build_min_max_envelope()` — explicitly
**not** called "decimation" anywhere in code, tests, or this document
(per the task's own terminology instruction): splits the resolved range
into `max(1, point_budget // 2)` **equal-count** buckets (not equal-time
— this needs no uniform-sample-spacing assumption, so it works
identically for single- or multi-rate COMTRADE sections without special
casing); within each non-empty bucket keeps both the minimum and maximum
sample (collapsed to one point if they coincide), emitted in
chronological order; then guarantees the *true* first and last sample of
the requested range are always present, even if neither is its own
bucket's extremum, so an analyst always sees exactly where the visible
range begins and ends. Deterministic (same input + budget always produce
identical output — verified by `TestDeterminism`); never mutates or
aliases its input arrays (verified by `TestNoMutation`).

**Full-resolution is returned, not reduced, whenever the resolved range's
raw sample count already fits the point budget** — this is a hard
decision boundary in `extract_waveform_range()`, not a heuristic, so a
sufficiently narrow request is *never* passed through the reduction
function at all.

### Spike regression — the mandatory test

`tests/test_waveform_reduction.py::TestSyntheticSpikeRegression`:
2000 ordinary samples (~1.0 V) with a single-sample 100 V transient
spike, reduced to a 100-point budget (stride-20 equivalent). First,
`test_naive_stride_sampling_demonstrably_can_miss_the_spike` proves the
risk is real by running the exact algorithm `powerwave`'s own
`decimate_for_display()` uses (`values[::stride]`) against the same
fixture and confirming the spike value never appears in its output.
Second, `test_min_max_envelope_preserves_the_spike` confirms this
project's algorithm returns the spike's true value, correctly paired with
its true sample time (not a fabricated position). A third test confirms
the same for a narrow *negative* spike. **Result: naive stride sampling
misses the spike (as predicted); `build_min_max_envelope` preserves it,
every run (17/17 `test_waveform_reduction.py` tests passing).**

### Zoom/detail behaviour

`tests/test_waveform_service.py::TestZoomFidelity`, against a 100,000-
sample synthetic source: a full-record request at a fixed point budget
returns a reduced envelope with a coarser average inter-sample spacing
than a narrower request (a 0.1s window of the same record, same budget) —
directly testing that narrowing the request increases real time
resolution, not just re-displaying the same coarse data. A sufficiently
narrow sub-range (400 samples at the same 500-point budget) crosses the
full-resolution boundary and returns `representation: "full_resolution"`
with `original_sample_count == returned_point_count`, confirming the API
never permanently locks a caller to whatever coarseness an earlier wide
view happened to produce — each request is independently resolved
against the authoritative record.

### Lifecycle integration

No second waveform-memory registry was introduced — `ActiveSource` is
stored in the same `WorkspaceRegistry`, cleaned up by the same
`remove()`/`remove_workspace()` methods Phase 1's workspace-reset pass
already built and tested (DEC-018), unmodified.

- **Source `Remove`**: `tests/test_waveform_api.py::TestLifecycleCleanupReleasesWaveformData::test_remove_source_makes_its_waveform_unavailable`
  — waveform request succeeds before, `DELETE .../sources/{id}` (204),
  waveform request afterward returns 404 `source_not_found`.
- **Whole-workspace cleanup**: `test_whole_workspace_delete_releases_every_sources_waveform_data`
  — 3 sources uploaded into one workspace, each confirmed to serve
  waveform data, `DELETE /api/v1/workspaces/{id}` (204), every source's
  waveform request afterward returns 404.
- **Actual reference release, not just API inaccessibility**:
  `test_reference_count_drops_after_source_removal` weak-references the
  retained `waveform_data` DataFrame directly (not the `DisturbanceRecord`
  itself, which is a `slots=True` dataclass and doesn't support weakrefs),
  removes the source, forces a GC pass, and asserts the weakref resolves
  to `None` — the authoritative array is provably collected, not merely
  unreachable through the API.
- **Remaining abandoned-session issue, unchanged and explicitly not
  claimed solved**: a browser tab closed without clicking `Remove`/`Start
  new workspace` still leaves that workspace's `ActiveSource` entries
  (now including full-resolution arrays, not just metadata) resident
  until process restart. See DEC-019's Impact section and
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).

### Concurrency

No new locking infrastructure was added. `WorkspaceRegistry.get()`
returns a plain reference under its existing `threading.Lock`, released
immediately after the dict lookup — any real work against the returned
`ActiveSource` (range extraction, reduction) happens *after* the lock is
released, exactly like the existing pattern, so a slow waveform
computation can never block unrelated requests. A concurrent
`remove()`/`remove_workspace()` racing an in-flight `GET .../waveform`
is safe by ordinary Python reference semantics: a request that already
retrieved its `ActiveSource` reference before the delete safely finishes
serving from that reference (the dict entry being dropped doesn't affect
an already-held reference); a request that hasn't retrieved it yet
correctly gets `source_not_found`. `record.waveform_data` is never
mutated by any reader, so concurrent `GET .../waveform` requests against
the same source need no additional synchronization beyond this.

### Memory model — measured, not assumed

Measured via a one-off benchmark script (not committed — synthetic data
only, no real/confidential fixtures) across four scenarios:

| Scenario | Samples | Channels (analog/digital) | DataFrame memory (`.memory_usage(deep=True)`) |
|---|---|---|---|
| Small (existing fixture scale) | 40 | 3 / 2 | ~3 KB |
| Medium (10s @ 4kHz, realistic COMTRADE) | 40,000 | 8 / 16 | 3.52 MB |
| High-channel-count (owner's Phase 1 UAT scale) | 20,000 | 103 / 362 | 23.88 MB |
| Large (approaching 100 MB-file-scale sample counts) | 2,000,000 | 8 / 16 | 176.00 MB |

**`.to_numpy()` on a channel column returned a zero-copy view (`arr.base
is not None`) in every scenario tested** — confirmed empirically, not
assumed (pandas does not guarantee this in general; this is what was
observed for this DataFrame construction pattern). Range extraction
(`time[lo:hi]` / `values[lo:hi]`) is ordinary NumPy slicing, always a
view, never a copy. `build_min_max_envelope()`'s output arrays are the
only newly-allocated (copied) arrays in the request path, by design — see
its own docstring.

**File-size-to-memory ratio, precisely accounted for (analog channels)**:
COMTRADE binary stores analog samples as 2-byte integers on disk;
`ComtradeProvider` converts them to 8-byte `float64` during scaling
(`_apply_analog_scaling`) — a **4x expansion**, confirmed exactly by the
2,000,000-sample scenario's arithmetic (8 analog channels × 2,000,000
samples × 8 bytes = 128 MB, matching the measured total precisely once
the `time` column and digital channels' int8 storage are accounted for).
Digital channels are far cheaper per sample (1-byte `int8` vs. 8-byte
`float64` for analog) — an **8x expansion** from their packed-bit
on-disk representation. **This is a real, measured data point for the
"file size doesn't map directly to parsed memory" question flagged as
`[OPEN]` in [CURRENT_STATE.md](CURRENT_STATE.md)** — it is not, however,
a direct measurement against an actual 100 MB COMTRADE file (only
synthetic data at comparable sample counts), so that specific item
remains only partially closed, not fully resolved — see "Remaining
`[OPEN]`" below.

### Performance — measured, not assumed

Same benchmark script, same four scenarios (all on ordinary development
hardware, single run — indicative, not a rigorous statistical benchmark):

| Scenario | Full-range extraction (no reduction) | Full-range extraction + reduction to 4000-pt budget | Narrow-range (1% of record) extraction | JSON serialize (reduced response) | Payload size (reduced) | Payload size if full-resolution returned (1 channel) |
|---|---|---|---|---|---|---|
| Small | 0.034 ms | 0.023 ms | 0.020 ms | 0.030 ms | 1.4 KB | <1 KB |
| Medium | 0.027 ms | 3.72 ms | 0.025 ms | 1.63 ms | 113.7 KB | 1.15 MB |
| High-channel-count | 0.029 ms | 3.56 ms | 0.023 ms | 1.62 ms | 114.1 KB | 0.58 MB |
| Large (2M samples) | 0.030 ms | 7.58 ms | 3.72 ms | 1.68 ms | 119.8 KB | **61.04 MB** |

**Reading these numbers**: exact-range extraction itself is effectively
free at every scale tested (`searchsorted` on a sorted array plus a NumPy
slice — sub-millisecond even at 2,000,000 samples). The measurable cost is
entirely in the reduction step (the Python-level loop over ~2,000
buckets, each doing a small vectorized `argmin`/`argmax`) — still under
8 ms even at the largest scale tested. JSON serialization of the bounded
(~4,000-point) response is consistently ~1.6-1.7 ms regardless of the
source record's total size, and payload size stays in the 110-120 KB
range regardless of record size, **exactly the structural guarantee the
Phase 2 design's range-request architecture was chosen for** (§4/§26 of
the design section) — contrast the last column: a full-resolution
response for just *one* channel of the 2,000,000-sample scenario would be
61 MB, which is precisely the payload-size risk the bounded, budget-based
endpoint avoids by construction.

### Tests

**278 backend tests pass** (227 before this pass + 51 new), zero
regressions:
- `tests/test_waveform_reduction.py` (17) — the min/max envelope
  algorithm in isolation: the mandatory spike regression (3 tests),
  chronological ordering and true time/value association (2), first/last
  sample handling (2), determinism (1), no-mutation/no-aliasing (2),
  budget-is-not-an-exact-cap (1), small-input edge cases (3), input
  validation (3).
- `tests/test_waveform_service.py` (17) — range extraction against
  precisely known synthetic sources: full-record requests (2), exact-range
  extraction including boundary-inclusive and before/after-record cases
  (6), invalid time range (1), channel identity resolution including
  digital-channel rejection (3), point-budget boundary (2), zoom-fidelity
  (2), no-mutation-of-authoritative-data (1).
- `tests/test_waveform_api.py` (17) — full end-to-end HTTP flow against
  the real COMTRADE fixture: valid requests including exact value/time
  comparison against the provider's own direct output (3), every error
  case from the task's required list (8), point-budget boundary at the
  API layer (2), and the lifecycle-cleanup regressions (3, including the
  weakref reference-release test).
- `tests/test_workspace_registry.py` — updated (not net-new) to build
  `ActiveSource` fixtures instead of bare `SourceMetadata`; all existing
  assertions preserved, none weakened.
- **Zero changes to `tests/test_comtrade_parity.py`,
  `tests/test_comtrade_provider.py`, `tests/test_channel_classification.py`,
  or any parser/provider code** — confirmed passing unmodified.

### Files changed

New: `backend/app/domain/waveform_reduction.py`,
`backend/app/services/waveform_service.py`,
`backend/app/schemas/waveform.py`,
`backend/tests/test_waveform_reduction.py`,
`backend/tests/test_waveform_service.py`,
`backend/tests/test_waveform_api.py`.

Modified: `backend/app/domain/source.py` (new `ActiveSource`),
`backend/app/domain/__init__.py`,
`backend/app/domain/disturbance_record.py` (docstring correction),
`backend/app/services/workspace_registry.py` (stored-value type widened;
docstrings corrected),
`backend/app/services/import_service.py` (builds/stores `ActiveSource`;
docstring corrected),
`backend/app/services/errors.py` (new error classes),
`backend/app/api/v1/sources.py` (new waveform endpoint; existing
endpoints updated to unwrap `.metadata`),
`backend/tests/test_workspace_registry.py` (fixture helper updated).

No `backend/app/providers/*`, `backend/app/main.py`, `frontend/*`, or CI/
deployment file was touched.

---

## Phase 2B — Renderer UAT Prototype Implementation Record (2026-08-15)

Implements exactly the task's own scope: a bounded, isolated browser
prototype letting the owner hands-on compare plotting libraries against
the SAME Phase 2A backend data and the SAME interaction contract. **No
winner chosen — plotting library remains `[DECISION MODE: UAT]`.** No
Phase 2C (drag/reorder/panel) work, no digital channels, no cursors/
measurements, no calculated signals, no synchronization, no CSV/Excel.

### What was built

`frontend/waveform-prototype.html` — a new, self-contained page, isolated
from `index.html` (the main app) and from the Phase 2A backend API (which
remains chart-library-independent — see its own module docstring). Opened
from a new "Waveform (UAT)" link added to each **analog** channel row in
`index.html`'s existing Phase 1 channel browser (digital rows are
untouched — no link, consistent with Phase 2B's analog-only scope), which
carries only already-known identity (`workspace_id`, `source_id`,
`channel_name`, `unit`, `station_name`) via the query string — the
prototype page fetches waveform data itself, this link never embeds it.

**Deliberately not embedded as a panel inside `index.html`**: keeping it a
separate page means the main channel browser's markup/JS is essentially
untouched (one link added, no restructuring), the prototype is trivially
deletable in its entirety later, and nothing about Phase 2B risks
constraining `index.html`'s own future evolution.

### Candidates implemented

**uPlot** (v1.6.32, MIT) — vendored as a static, pre-built, minified IIFE
bundle (`frontend/vendor/uplot/uPlot.iife.min.js`, 51,081 bytes +
`uPlot.min.css`, 1,857 bytes = ~52 KB combined, ~22 KB gzipped). No
build step, no npm dependency at deploy time — matches the project's
existing no-build-step frontend architecture exactly (`frontend/vendor/README.md`
records exact provenance/version for later removal or upgrade).

**Plotly.js** (v3.7.0, MIT) — vendored as the **cartesian-only** minified
distribution (`plotly.js-cartesian-dist-min`,
`frontend/vendor/plotly/plotly-cartesian.min.js`, 1,424,820 bytes ≈
1.36 MB, ~473 KB gzipped), not the full `plotly.js` bundle — this
prototype only needs line/scatter charts, not 3D/maps/every other trace
type the full bundle carries. Per the task's explicit instruction, Plotly
was treated as a full primary candidate, not a fallback.

**ECharts — deliberately omitted.** Reason: two well-implemented, fully
fair prototypes (uPlot and Plotly) already give the owner a genuine
comparison across the size/complexity spectrum (uPlot: ~52 KB, minimal
API; Plotly: ~1.36 MB, batteries-included). Adding a third candidate
would have meant either rushing its adapter to hit the same fairness bar
the other two received, or measurably extending this task — the task's
own guidance ("two good prototypes are better than three rushed ones")
was applied directly.

### Same-data comparison guarantee

Both adapters are driven by **one shared coordinator** (`waveform-prototype.html`'s
inline script) that owns the current fetched payload; a candidate never
fetches its own data independently. Concretely:

- Both call the identical endpoint (`GET .../sources/{id}/waveform`) with
  the identical `channel_name`, and the identical fixed `POINT_BUDGET`
  constant (4000 — matching the backend's own `DEFAULT_POINT_BUDGET`).
- **Switching renderers does not issue a new request** — the coordinator
  passes the already-fetched `{time, values, unit, channelName,
  representation}` payload straight into the newly-selected adapter's
  `init()`. Verified directly (`tests/` below): a renderer switch after
  data has loaded produces zero additional `fetch` calls.
- Both read the same `unit`/`channel_name`/timing fields from the same
  response — neither renders a locally-recomputed or reformatted version
  of anything the backend didn't send.

### Range-request behaviour (zoom/pan → finer backend data)

A shared `requestViewportRangeDebounced(startTime, endTime)` function is
the **only** path either adapter has to request new data — both adapters'
zoom/pan gesture handlers call it, nothing else does:

- **uPlot**: wires uPlot's built-in `cursor.drag` + `hooks.setSelect`
  (horizontal drag-to-zoom-select is uPlot's own native idiom) to compute
  the selected time range and call the shared function.
- **Plotly**: listens to Plotly's own `plotly_relayout` event (fired by
  its native modebar zoom/pan/double-click-autoscale interactions) and
  extracts the new x-axis range from it.

**Debounce + stale-request protection** (`docs/project-memory/MIGRATION_PLAN.md`'s
Phase 2 design §13/§14, this task's explicit "critical" requirement) —
two independent layers, both implemented and both independently tested:

1. A 200ms debounce timer around the viewport-change → fetch pipeline,
   so a drag gesture's intermediate frames never each trigger their own
   request.
2. **`AbortController` + a monotonically increasing sequence number**,
   together: every new range request aborts the previous request's
   in-flight fetch immediately; a response is only ever applied if its
   sequence number still matches the latest request issued, checked both
   right after the fetch settles and again after the response body has
   been read (covering the case where an abort signal doesn't actually
   stop a response already in flight). A jsdom test specifically isolates
   the sequence-number layer from the AbortController layer (by
   simulating a fetch mock where abort does not reject the promise) and
   confirms a later-arriving stale response is still correctly discarded
   in favour of a newer one that resolved first.

Requests are also clamped to the record's own bounds
(`recordBounds.start`/`recordBounds.end`, learned from the initial
unbounded request's own `start_time`/`end_time`) before being issued, so
pan/zoom can never silently request outside the source's actual time
range.

### Waveform fidelity

- **No frontend smoothing/filtering anywhere.** uPlot's default line path
  (`paths.linear`, never overridden) draws straight segments directly
  between real sample points — no spline/curve smoothing is enabled.
  Plotly's trace explicitly sets `line: { shape: "linear" }` (not
  `"spline"`), the same guarantee stated explicitly rather than left to
  an unexamined default.
- **Phase 2A's authoritative data is completely unchanged.** This
  prototype only ever calls the existing, unmodified
  `GET .../sources/{id}/waveform` endpoint — no backend file was touched
  this pass (confirmed: `git diff --stat -- backend/` is empty, and all
  278 existing backend tests, none modified, still pass).
- **Narrower ranges reveal real higher-detail samples**, not a cached or
  re-decimated view of the same coarse data — every viewport change is a
  fresh request against the authoritative record (`app.services.waveform_service.extract_waveform_range`,
  unchanged), which already guarantees (per its own Phase 2A tests) that
  a sufficiently narrow range returns true full-resolution samples
  (`representation: "full_resolution"`) rather than a display envelope.

### Loading/error behaviour

A small, non-blocking loading pill appears over the top-right of the
chart during a range fetch (the previously-rendered chart is left visible
underneath, never blanked) — this is the same "don't freeze/blank the
UI" philosophy the owner approved in Phase 1's loading indicators, applied
here rather than reinvented. Errors map through a `friendlyWaveformError()`
function mirroring `index.html`'s own `friendlyErrorMessage()` pattern —
plain-language messages for `source_not_found`, `channel_not_found`,
`channel_not_analog`, `invalid_time_range`, `invalid_workspace`,
`internal_error`, and a network-unreachable case — never a raw error code
or stack trace.

### Renderer isolation

Both candidates implement one shared adapter contract
(`init(container, payload, callbacks)` / `update(handle, payload)` /
`setViewport(handle, start, end)` / `destroy(handle)`), documented in a
comment block directly above the adapter definitions in
`waveform-prototype.html`. `destroy()` is required to leave zero trace —
verified by a dedicated test that switches renderers repeatedly and
confirms every `init` is matched by a `destroy`/`purge`, with no
duplicate DOM nodes accumulating in the chart container. Deleting a
losing candidate later means removing its adapter object, its `<script>`
tag, its vendored directory under `frontend/vendor/`, and its Dockerfile
`COPY` line — nothing else in the frontend or backend references a
specific library by name.

### Detego benchmark observations

A single, bounded, public-page fetch of `detego.app`'s own marketing
copy (not a technical audit, not an interactive walkthrough, not
reverse-engineered) surfaced these high-level, publicly-stated points,
used only as design-direction inspiration for this prototype, never as a
spec:

- Multi-panel dashboard with waveforms, phasors, and harmonics presented
  as distinct views within one workspace.
- Explicitly advertises "zoom, cursors, and RMS overlay" on waveform
  displays, plus pan.
- Toolbar/chrome described as minimal, favoring direct chart interaction
  over menu-heavy controls — informed this prototype's own choice to keep
  chrome to a renderer selector + Reset View + a small debug panel, no
  more.
- Detego's own marketing copy states it uses "interactive Plotly.js
  charts" — noted factually (it is public marketing text, not something
  inferred from technical inspection) but **not** treated as a reason to
  favor Plotly in this UAT, per DEC-020's explicit "do not favor it
  merely because Detego uses or appears to use it."

No deeper inspection was performed — consistent with
`docs/project-memory/PRODUCT_REFERENCES.md`'s standing `[OPEN]` note that
no full technical audit of Detego exists in this project's memory.

### Performance comparison

Measured directly (not claimed): vendored bundle sizes above (uPlot ≈
52 KB / ~22 KB gzip vs. Plotly-cartesian ≈ 1.36 MB / ~473 KB gzip — Plotly
is roughly 27× larger uncompressed, ~21× larger gzipped, even using the
size-reduced cartesian-only build rather than the full `plotly.js`
bundle). A small DEV-only debug panel on the prototype page itself
(`<details>`, collapsed by default, does not affect the normal UX) reports
per-request: API request duration, payload size (via `Blob` byte-exact
sizing, not a UTF-16 length approximation), render/update duration,
points rendered, original raw sample count in range, and the current
visible time range — for both candidates, using the identical
measurement code path (the coordinator, not the adapters, does the
timing). No synthetic point-count/render-speed numbers are asserted here
as project-memory fact — those depend on real interaction during the
owner's own UAT session against real imported data; the debug panel
exists specifically so that UAT session can observe them directly rather
than trusting a canned benchmark.

### Tests

- **Backend: 278 tests, unchanged, all passing** — zero backend files
  touched this pass.
- **Frontend: 25 scripted checks, all passing** — a one-off `jsdom`
  script (not committed, same established lightweight approach as every
  prior frontend-verification pass in this project) drove the actual
  shipped `waveform-prototype.html` against stub `uPlot`/`Plotly`
  implementations satisfying their real public APIs, covering: initial
  full-record request (correct URL, correct fixed point budget); zoom
  producing a narrower debounced request; the stale-response scenario
  with both protection layers verified independently; Reset View
  restoring the full record and forcing the chart's visible scale;
  error-banner display with friendly wording; renderer switch causing
  zero additional backend requests and reusing the already-fetched data;
  repeated renderer switching with no leaked/duplicated adapter instances
  or DOM nodes; and Plotly's own programmatic-relayout-after-Reset not
  looping back into a spurious second fetch.
- **Manual verification**: visual/interactive correctness (does the zoom
  gesture feel natural, does the chart look clean, is the axis readable)
  is inherently a hands-on concern — that is the explicit purpose of the
  owner's own upcoming UAT session, not something a scripted test can
  substitute for.

### Files changed

New: `frontend/waveform-prototype.html`,
`frontend/vendor/README.md`,
`frontend/vendor/uplot/{uPlot.iife.min.js,uPlot.min.css,LICENSE}`,
`frontend/vendor/plotly/{plotly-cartesian.min.js,LICENSE}`.

Modified: `frontend/index.html` (one new link column on analog channel
rows only; `renderChannelTable`/`renderAnalogGroup` extended with an
optional action-column parameter, backward compatible — digital
channels' call site is unchanged), `frontend/Dockerfile` (serves the new
page + vendored assets), `frontend/.dockerignore` (comment updated to
list the new required paths, no pattern changes).

No `backend/` file, no `docker-entrypoint.d/` script, and no CI/deployment
workflow file was touched.

---

## Phase 2B — Plotly Refinement & Workspace-Level Navigation Record (2026-08-15)

Follows the owner's hands-on UAT of the Phase 2B renderer prototype
(commit `ad6d9d2`). **Plotly is currently preferred but the renderer
choice is deliberately NOT closed** — see DEC-021
([DECISIONS.md](DECISIONS.md)) for the one design decision this pass
actually approves (workspace-level navigation), which is a separate
question from which library wins. No Phase 2C, no multi-channel panels,
no uPlot removal, no Phase 2A backend change.

### Owner UAT result recorded

**uPlot strengths observed**: a useful mouse crosshair (already uPlot's
own default behaviour — nothing was added for it), the crosshair helps
correlate X and Y values, responsive.

**Plotly strengths observed**: better waveform clarity, richer built-in
controls (zoom, pan, zoom in/out, autoscale, reset axes, PNG export),
smooth and confidence-building interaction, hover X/Y values move with
the waveform interaction.

**Plotly weaknesses observed**: no visible crosshair line in the
prototype as shipped (addressed this pass — see below); occasional slight
lag using modebar controls (investigated this pass — see below); no
explicit axis titles noticed but not considered important (not
addressed — axis titles already exist in the current layout via
`xaxis.title`/`yaxis.title`; if the owner still finds this worth revisiting
during final UAT, it's a one-line change, not recorded as a gap needing
separate work).

**Overall**: `[UAT — Plotly preferred pending final refinement
confirmation]`. Not recorded as a final decision — `DECISIONS.md` does not
name a winning renderer.

### Owner UAT requirement recorded — workspace-level waveform navigation

`[DECISION]` DEC-021 (full text in [DECISIONS.md](DECISIONS.md)): **waveform
navigation is workspace-level, not channel-level.** All displayed analog
channels will share one X/time viewport; zoom/pan/Reset Time View act on
the whole workspace, never one channel independently; Y scales may remain
per-channel. A **centralized Powerwave waveform toolbar** (not a
per-channel/per-subplot native modebar) is the required future
architecture — Plotly's native per-chart modebar was useful to review
during UAT specifically *because* it made concrete what the final
multi-channel workspace must NOT become. Terminology fixed by the same
decision: **"Reset Time View"** (X-range only) and **"Autoscale Y"**
(Y-scale only) are different operations, never collapsed into one control.

### Plotly refinement — crosshair/spike-line

Implemented using **Plotly's own native axis spike-line capability** —
no custom crosshair system was built, per the task's explicit preference.
`waveform-prototype.html`'s `PlotlyAdapter.init()` layout now sets, on
both `xaxis` and `yaxis`:

```js
showspikes: true, spikemode: "across", spikesnap: "data",
spikethickness: 1, spikedash: "solid", spikecolor: "#8b96ad",
```

plus `hovermode: "closest"`. Result: hovering the waveform now shows a
vertical guide line (time) and a horizontal guide line (value), both
spanning the full plot area (`spikemode: "across"`), disappearing when
the cursor leaves the chart (no permanent/fixed labels added).

**Deliberate choice: `spikesnap: "data"`, not `"cursor"`.** `"cursor"`
would follow the mouse pixel-for-pixel, which can visually imply a value
*between* two real recorded samples — `"data"` snaps the crosshair to the
nearest actual sample instead, keeping it consistent with the project's
standing "no interpolation that visually changes the waveform signature"
requirement. The existing `hovertemplate` (unchanged) already shows the
moving X/Y value label the owner specifically called out as a Plotly
strength.

**Documented alternative, not implemented**: if the owner finds both
lines together too busy during final UAT, the one-line change is
`yaxis.showspikes: false` (vertical/time-only crosshair, closer to how
uPlot's own default crosshair is typically perceived). Left as a documented
option, not pre-built as a toggle — building a configurable-crosshair UI
would be exactly the "large custom crosshair system" the task said not to
build without clear justification.

**uPlot's crosshair required no change** — it already shows a
vertical+horizontal crosshair by default (uPlot's own `cursor` behaviour,
active whenever not explicitly disabled, which it isn't here). The owner's
positive UAT observation about uPlot's crosshair was simply confirming
already-existing behaviour, not identifying something to add.

### Toolbar lag investigation

**What was measured/inspected** (code review — no real-browser profiling
tool was available in this environment; see "What remains unverified"
below): traced every path that can trigger a backend re-fetch from a
Plotly modebar action.

**Finding 1 — a real correctness gap, not the lag itself**: Plotly's
native **Autoscale** and **Reset axes** modebar buttons do not fire an
explicit `xaxis.range[0]`/`[1]` relayout event — they fire
`{"xaxis.autorange": true, "yaxis.autorange": true}` instead. The
prototype's relayout handler, as originally shipped, only recognized the
explicit-range case and silently ignored the autorange case. Practical
effect: clicking native Autoscale/Reset-axes re-scaled the chart's axes
to fit whatever data was **already loaded** (e.g. a previous zoom's
reduced range) — it never actually re-fetched the true full record from
the backend. This is not what "lag" usually means, but it's exactly the
kind of thing a "why does this feel off" investigation surfaces, and it's
a genuine bug, fixed this pass (the handler now treats an autorange
relayout the same as the app's own Reset Time View — see code comments
in `waveform-prototype.html`).

**Finding 2 — a real, small, avoidable delay source**: the 200ms debounce
around every viewport-change request applies unconditionally, including
to a single discrete modebar button click (zoom-in, zoom-out, autoscale).
Unlike a drag gesture, a single click has no intermediate frames to
coalesce — so for that specific interaction, the debounce was pure added
wait time with zero benefit. **Reduced to 120ms** this pass — still
comfortably long enough to coalesce a real drag gesture's frames (which
was the debounce's actual purpose), but shaves 80ms off every discrete
click's perceived latency. This is a small, targeted, safe change, not a
redesign of the debounce mechanism itself.

**Finding 3 — no evidence found of duplicate relayout events** for a
single discrete action, from code/documentation review. This is
specifically hard to fully rule out without a real browser and real mouse
timing (Plotly's exact event-firing cadence during a live drag can differ
subtly by build/interaction mode) — reported honestly as unconfirmed
either way, not asserted as fixed.

**What was NOT changed**: the interaction layer itself (debounce +
AbortController + sequence-number protection) was not redesigned — only
its one duration constant was tuned, and one real event-handling gap was
closed. Likely remaining sources of any felt lag that this pass did not
and could not address in a sandboxed environment: real network
round-trip time to the DEV backend, and Plotly's own `scattergl` trace
re-render cost — both are inherent to the architecture (a genuine
backend round-trip *should* happen on every real range change, per the
zoom-fidelity requirement) rather than defects to remove.

### Waveform fidelity — confirmed unchanged

- Phase 2A backend: **zero files touched** (`git diff --stat -- backend/`
  empty), all 278 existing tests unmodified and passing.
- Range-request semantics unchanged: same endpoint, same query
  parameters, same fixed `POINT_BUDGET` (4000).
- Linear rendering unchanged: uPlot's default linear path and Plotly's
  explicit `line.shape: "linear"` are both exactly as before — the
  crosshair/spike configuration is purely a hover-interaction feature and
  touches no trace/line-rendering setting.
- Zoom still reveals genuinely finer real backend data — the crosshair
  and lag-fix changes touch only the relayout **event-handling** path
  (which range gets requested and when), never the data returned for a
  given range.

### Future centralized-control readiness

Per DEC-021's own Impact section: `requestViewportRangeDebounced()` was
deliberately left **unrestructured** this pass — it already takes a
plain `(startTime, endTime)` viewport and requests it, with no code
assuming "this channel owns its own private viewport." A new comment
block marks this as the Phase 2C extension point (fan one shared range
across every displayed channel's own fetch), so a future multi-channel
implementation extends this function's *caller*, not its *shape*.
Nothing about this pass's changes narrows that door.

### uPlot status

**Retained, fully functional, unmodified in behaviour.** Verified this
pass: switching back to uPlot after using Plotly still issues zero
additional backend requests and still renders correctly (regression
test, see below). uPlot remains available for the owner's final
side-by-side crosshair comparison before any renderer decision is made.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend: 24 scripted `jsdom` checks, all passing** — extends the
  existing lightweight approach: 10 regression checks confirming every
  Phase 2B behaviour (initial request, zoom, both stale-protection
  layers, Reset Time View, renderer switching including uPlot remaining
  functional, adapter cleanup, error banner) is unchanged, plus 5 new
  checks for this pass specifically: the Plotly layout's spike/crosshair
  configuration (`showspikes`, `spikesnap: "data"`, `spikemode:
  "across"`, no added permanent annotations); and — the most important
  new test — a direct proof that a simulated native
  Autoscale/Reset-axes relayout event now correctly triggers a real
  full-record re-fetch (previously silently ignored), confirming the
  toolbar-lag investigation's Finding 1 fix.
- **What remains unverified**: real-browser visual/interactive
  correctness (does the crosshair look right, does the perceived lag
  actually feel reduced) — no headless browser was available in this
  environment; this is exactly the purpose of the owner's own final UAT
  session.

### Files changed

Modified only: `frontend/waveform-prototype.html` (Plotly spike/crosshair
config; relayout-handler autorange fix; debounce 200ms → 120ms; "Reset
View" → "Reset Time View" label/wording throughout; extension-point and
semantic-distinction comments — no HTML structure change, no new files),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`.

No `frontend/vendor/*`, no `frontend/index.html`, no `backend/` file, and
no CI/deployment workflow file was touched.

---

## Phase 2B — Renderer Closure Record (2026-08-15)

Closes Phase 2B following the owner's final UAT decision. **Plotly.js is
the selected waveform renderer** (DEC-022, [DECISIONS.md](DECISIONS.md)).
uPlot's adapter, vendored assets, and the renderer-switch UI have been
removed. DEC-021 (workspace-level, centralized-toolbar navigation)
remains fully authoritative and unchanged. **Phase 2C has not started.**

### Final renderer decision

> Plotly.js is selected as the waveform rendering foundation for
> `oruxa_powerwave`.

Recorded verbatim, per the owner's final UAT: Plotly's better waveform
clarity, good pan, rich built-in navigation controls (zoom/zoom in/zoom
out/autoscale/reset axes/PNG export), moving hover X/Y values, and
overall better engineering interaction feel outweighed uPlot's own
strength — a very good free-moving crosshair feel. This closes the `[UAT
— Plotly preferred pending final refinement confirmation]` status
recorded in the prior refinement pass; it is no longer pending.

### Crosshair refinement

Plotly's native axis spike-lines (already in place from the prior
refinement pass) were **restyled**, not re-engineered:

| Property | Before | After |
|---|---|---|
| `spikedash` | `"solid"` | `"dash"` |
| `spikecolor` | `#8b96ad` (fully opaque) | `rgba(139, 150, 173, 0.55)` (55% opacity — the same base color, lighter) |
| `spikethickness` | `1` | `1` (unchanged — already the thinnest practical pixel width) |
| `spikesnap` | `"data"` | `"data"` (unchanged — still snaps to real recorded samples, never interpolated) |
| `spikemode` | `"across"` | `"across"` (unchanged — both vertical and horizontal guide lines preserved) |

Net effect: the crosshair now reads as a subtle dashed guide rather than
a solid, heavier line — assisting waveform reading without visually
competing with the trace itself, per the owner's stated visual intent.
Both vertical (time) and horizontal (value) guide lines are still shown;
no permanent/fixed labels were added; the moving hover X/Y value label
(`hovertemplate`, unchanged) is preserved.

### Responsiveness — explicitly not pursued

The owner separately clarified that Plotly's sample-snapped crosshair
feeling slightly less immediate than uPlot's free-moving cursor is *"not
important enough to justify additional implementation complexity or
development time."* Accordingly, this pass built **no** custom
mouse-following overlay, **no** recreation of uPlot's two-layer cursor
mechanics, and **no** custom hover engine. Plotly's native, sample-snapped
hover behaviour is unchanged functionally — only its visual styling
(table above) was refined. This is a deliberate scope boundary, not an
oversight.

### uPlot cleanup

Removed, confirmed via repository-wide search (`grep -ril "uplot"`,
excluding `docs/` which retains historical record intentionally):

- `frontend/vendor/uplot/` — the entire directory (`uPlot.iife.min.js`,
  `uPlot.min.css`, `LICENSE`).
- `UPlotAdapter`, the `ADAPTERS` map, `switchRenderer()`, and both
  renderer-tab buttons (`#tabUplot`/`#tabPlotly`) and their `.renderer-tab`
  CSS from `frontend/waveform-prototype.html`.
- The `<link rel="stylesheet" href="vendor/uplot/uPlot.min.css">` and
  `<script src="vendor/uplot/uPlot.iife.min.js"></script>` tags.
- All uPlot-specific test assertions from the frontend scripted-test
  suite (replaced with Plotly-only equivalents plus explicit
  "no uPlot reference remains" checks — see Tests below).

**Confirmed remaining only as historical record** (not stale, not dead
code): `frontend/vendor/README.md`'s new "History" section (states uPlot
was evaluated and removed, points to this record for the comparison
detail) and this document's own Phase 2B records above. Per the task's
own "do not rewrite unrelated history" instruction, none of the prior
Phase 2B UAT/refinement records above this section were altered.

`frontend/Dockerfile` and `frontend/.dockerignore` needed no structural
change — both already referenced `vendor/` as a whole directory, not
per-library, so removing `vendor/uplot/` requires no build-pipeline edit.
Their comments were updated for accuracy (singular "Plotly.js bundle"
instead of plural "plotting libraries").

### Plotly waveform behavior — confirmed unchanged

- **Zoom**: native box-zoom drag still triggers a debounced (120ms),
  stale-protected range request via the `plotly_relayout` handler.
- **Pan**: native Plotly pan mode (modebar) still triggers the same
  relayout → range-request path.
- **Autoscale / Reset axes**: still correctly re-fetch the full record
  (the fix from the prior refinement pass — treating the native
  `xaxis.autorange` relayout the same as Reset Time View — is unchanged).
- **Reset Time View**: still X-range-only, distinct from Y-autoscale,
  per DEC-021's terminology requirement.
- **Hover**: crosshair (restyled) plus moving X/Y value label, both
  unchanged in mechanism.
- **Range requests**: same endpoint, same query parameters, same fixed
  `POINT_BUDGET` (4000) — unchanged.
- **Fidelity**: linear rendering (`line.shape: "linear"`, never
  `"spline"`) unchanged; zoom still reveals genuinely finer real backend
  data (Phase 2A's `extract_waveform_range` behaviour, untouched); Phase
  2A backend has zero diff this pass, all 278 existing tests unmodified
  and passing.

### Centralized navigation requirement — reconfirmed

DEC-021 is unchanged and remains the authoritative future requirement:
one shared X/time viewport across every displayed channel, a centralized
Powerwave toolbar (not per-channel native modebars), and "Reset Time
View"/"Autoscale Y" kept as distinct concepts. This pass's interaction
hint text, now visible directly on the page, states explicitly that the
current native Plotly modebar is **temporary** and that Phase 2C will
introduce the centralized toolbar — making the requirement visible to
anyone using the page, not just recorded in code comments and
project-memory.

### Detego benchmark note

Per [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)'s standing framework:
**Plotly was selected because of the owner's own hands-on UAT, not
because Detego's public marketing copy happens to mention using
Plotly.js** (that observation was noted factually during the earlier
renderer-comparison pass and explicitly flagged then as not a reason to
favor Plotly — DEC-020). This decision record does not imply otherwise;
the UAT findings above are the entire stated reason.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend: 31 scripted `jsdom` checks, all passing** — covers: three
  static-markup checks confirming no renderer-selector UI, no
  "renderer comparison"/"Phase 2B UAT" wording, and no uPlot code
  references (script tags, CSS link, constructor calls, adapter object,
  `ADAPTERS` map, `switchRenderer`) remain anywhere in the shipped file;
  Plotly-only initialization; the restyled crosshair configuration
  (dashed, thin, reduced-opacity, still sample-snapped, both axes);
  zoom-triggers-narrower-request; the native-autoscale-triggers-refetch
  fix (still correct); Reset Time View; both layers of stale-request
  protection; and safe-failure error handling (covering the
  source-removed/workspace-reset scenarios).

### Files changed

Modified: `frontend/waveform-prototype.html` (uPlot removal, crosshair
restyle, page-text simplification), `frontend/Dockerfile` (comment
accuracy), `frontend/vendor/README.md` (uPlot entry removed, History
section added), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`.

Deleted: `frontend/vendor/uplot/uPlot.iife.min.js`,
`frontend/vendor/uplot/uPlot.min.css`, `frontend/vendor/uplot/LICENSE`.

No `frontend/index.html`, no `backend/` file, and no CI/deployment
workflow file was touched.

---

## Phase 0 — Target Architecture Design

### 1. Canonical runtime implementation mapping

Per discovery's warning about `src/`/`app/` split-brain and stale
documentation, every module below was **re-verified directly against
`powerwave` at commit `3156392`** during this design task (not assumed from
the discovery document or directory names) — current import path, Qt
independence, and current tests were checked freshly.

#### Capability: unified data contract

```text
Current canonical implementation:
  app/models/disturbance_record.py — DisturbanceRecord (dataclass, slots=True)
  app/models/channels.py — AnalogChannel, DigitalChannel
  app/models/metadata.py — RecordingMetadata
  app/models/timing.py — SamplingInformation, TimingInformation, DisturbanceInformation

Evidence:
  Re-read in full 2026-08-14. Confirmed zero PyQt/Qt imports (only
  `dataclasses`, `datetime`, `pandas`). DisturbanceRecord.validate() (lines
  92-138) is non-raising, returns a list of error strings. No hidden mutable
  state — every field is a plain value or a directly-owned pandas.DataFrame.
  Distinct from and NOT to be confused with the structurally different
  `src/models/disturbance_record.py` (legacy, per-channel raw-array
  ownership, raising __post_init__, stateful RMS/phasor caches — see
  POWERWAVE_DISCOVERY.md § Internal Data Model). Confirmed current tests:
  tests/unit/test_disturbance_record.py (257 lines).

Reuse classification: A
Target oruxa_powerwave location: backend/app/domain/{disturbance_record,channels,metadata,timing}.py
Migration treatment: reuse (port near-verbatim; add JSON-serialization
  methods, which powerwave's own DisturbanceRecord does not provide)
Risk: Low. The only real work is adding a serialization boundary; the
  contract itself needs no redesign for Phase 1.
```

#### Capability: provider abstraction / selection

```text
Current canonical implementation:
  app/providers/base/base_provider.py — BaseProvider(ABC): can_load(path), load(path)
  app/providers/base/provider_manager.py — ProviderManager: register_provider(), find_provider(), load()
  app/providers/base/provider_registry.py — ProviderRegistry: insertion-order-based can_load() resolution
  app/providers/base/exceptions.py — ProviderError, ProviderNotFoundError, ProviderLoadError, DuplicateProviderError

Evidence:
  Re-read in full 2026-08-14. Zero Qt imports. find_provider()/load() are
  pure Path-in, DisturbanceRecord-out (or a typed exception). Provider
  selection is deterministic first-match-in-registration-order over
  can_load(path) — no content sniffing beyond suffix matching. Confirmed
  current tests: tests/unit/test_provider_manager.py (323 lines).

Reuse classification: A
Target oruxa_powerwave location: backend/app/providers/base.py (may
  consolidate the four small files into one module, or keep the same
  four-file split for direct traceability — a Phase 0 implementation-detail
  choice, not a design question requiring approval)
Migration treatment: reuse near-verbatim
Risk: Low.
```

#### Capability: COMTRADE parsing

```text
Current canonical implementation:
  app/providers/comtrade/comtrade_provider.py — ComtradeProvider
    provider_name = "comtrade" (line 817)
    can_load(path): path.suffix.lower() in {".cfg", ".comtrade"} (lines 819-820)
    load(path): parses CFG, rejects BINARY32 explicitly, builds DisturbanceRecord (lines 822-844)
    _find_dat_file(cfg_path) (line 312): derives the companion .dat/.DAT file
      by same-stem, same-directory convention — cfg_path.with_suffix(".dat")
      then .DAT — raises ProviderLoadError if neither exists.

Evidence:
  Re-read in full 2026-08-14 (844 lines). Zero Qt imports. Binary DAT read
  via np.fromfile (confirmed, not the legacy read_bytes() pattern). ASCII
  DAT read via full read_text() + np.loadtxt(StringIO(...)). BINARY32
  rejected before record construction. Confirmed current tests:
  tests/unit/test_comtrade_provider.py (806 lines).

  **Critical design input**: load() takes ONE path (the .cfg) and
  internally resolves the companion .dat by filesystem convention
  (same directory, same stem). This means the backend MUST place both
  uploaded files together, with matching stems, in the same directory
  before calling load() — this directly shapes the upload/storage flow
  design below (§5) and the COMTRADE multi-file upload design (§10).

Reuse classification: A
Target oruxa_powerwave location: backend/app/providers/comtrade.py
Migration treatment: reuse; adapt only the call site to first stage both
  uploaded files into one directory with matching stems before invoking load()
Risk: Low for the parser itself. Medium for the upload-orchestration
  adaptation (must preserve the same-directory-same-stem convention exactly,
  or reimplement _find_dat_file's resolution logic explicitly at the
  service layer — see §10).
```

#### Capability: CSV / Excel direct parsing (unwizarded)

```text
Current canonical implementation:
  app/providers/csv/csv_provider.py — CsvProvider
    provider_name = "csv" (line 219); can_load (line 225); load (line 228)
  app/providers/excel/excel_provider.py — ExcelProvider
    provider_name = "excel" (line 259); can_load (line 265); load (line 268)

Evidence:
  Re-read entry points and can_load()/load() signatures 2026-08-14. Zero Qt
  imports (confirmed for the whole file in the earlier discovery pass; entry
  points re-confirmed here). Per POWERWAVE_DISCOVERY.md, this path is what
  powerwave's own interactive UI no longer routes CSV/Excel through — the
  richer Import Wizard backend is used instead for anything user-facing.
  Direct providers still do full pd.read_csv/pd.read_excel with best-effort
  timestamp parsing and no user-facing repair options. Confirmed current
  tests: tests/unit/test_csv_provider.py (832 lines),
  tests/unit/test_excel_provider.py (741 lines).

Reuse classification: B — reusable, but deliberately NOT the recommended
  path for interactive CSV/Excel import (see §15's Phase 1 vs 1.5 framing).
  Useful as a fallback/example, not the primary path.
Target oruxa_powerwave location: backend/app/providers/{csv_provider,excel_provider}.py
  (present for completeness/parity testing; Phase 1's actual CSV/Excel path,
  if included at all, should go through the Import Wizard backend instead —
  see §15)
Migration treatment: adapt (retain for reference/testing; do not expose as
  the interactive CSV/Excel path)
Risk: Low technically; Medium from a UX-fidelity standpoint if accidentally
  used as the primary path (loses timestamp-repair capability entirely).
```

#### Capability: CSV / Excel Import Wizard backend (timestamp detection, repair, normalization)

```text
Current canonical implementation:
  app/import_wizard/import_pipeline.py — run_import_pipeline(path, provider_type=None,
    sheet_name=None, options=None) -> ImportPipelineResult (line 170)
      "always returns, never raises" — check .success and .validation_messages
  app/import_wizard/normalized_dataset.py — NormalizedDataset, ParameterMetadata,
    AssemblyDiagnostics (auditable intermediate representation, not yet a
    DisturbanceRecord)
  app/import_wizard/disturbance_record_bridge.py — build_disturbance_record()
    (line 108) — converts NormalizedDataset -> DisturbanceRecord
  Plus: timestamp_detector.py, timestamp_normalizer.py, timestamp_repair_executor.py,
  interval_inference.py, data_assembler.py, csv_profiler.py, excel_profiler.py
  (27 files total in app/import_wizard/, all confirmed Qt-free in the discovery pass)

Evidence:
  run_import_pipeline()'s signature re-read 2026-08-14 — confirmed it takes
  a plain string path (not a Path object, not a Qt type) and a
  provider_type string, returning a plain dataclass result — directly
  callable from an async FastAPI handler with no adaptation needed for the
  call itself (only for where the path comes from — see §5). Confirmed
  current tests: tests/integration/test_import_pipeline_e2e.py (425 lines),
  plus tests/unit/test_import_pipeline.py and the many timestamp-specific
  unit test files catalogued in POWERWAVE_DISCOVERY.md § Test Coverage.

Reuse classification: A
Target oruxa_powerwave location: backend/app/providers/import_wizard/
  (kept as its own subpackage rather than flattened into providers/, to
  preserve the distinct "never raises, Result-object" pattern discovery
  identified as materially better than the direct-provider error model —
  see §9)
Migration treatment: reuse. This is Phase 1.5 scope, not Phase 1 (see §15)
  — Phase 1 ships with the direct CsvProvider/ExcelProvider only, or with
  CSV/Excel excluded entirely, per the decision in §15.
Risk: Low for the ported logic itself (well-isolated, well-tested). Medium
  for scope discipline — this is the single largest reuse candidate by line
  count and it is tempting to pull the whole Import Wizard UX forward into
  Phase 1; the recommendation below is explicitly to NOT do that.
```

### 2. Domain model design (Phase 1 minimum)

The task brief's suggested names (`Workspace`, `Source`, `SourceFile`,
`Channel`/`AnalogChannel`/`DigitalChannel`, `Timebase`, `ImportResult`) are
kept where they fit; `Timebase` is treated as an **API response shape**
rather than a new backend class, since `powerwave`'s own
`TimingInformation`/`SamplingInformation` already cover that need and
duplicating them would be pure ceremony.

| Concept | Identity | Ownership | Mutability | Lifetime | Serializable API shape | Relation to full-resolution data | Relation to storage | Required now? |
|---|---|---|---|---|---|---|---|---|
| **Workspace** | Client- or server-issued UUID, carried in every request path | No owning object — a scoping key only, not a class with behavior | N/A | For Phase 1: exists only as a grouping key; no explicit create/delete lifecycle | `workspace_id: str` in every URL | None directly | Storage paths and the metadata sidecar (below) are namespaced by it | **Yes** — minimally, as a path-scoping mechanism (see §4) |
| **Source** | Server-generated UUID (`source_id`), minted when an upload is accepted for processing | Belongs to exactly one Workspace | Effectively immutable after creation for Phase 1 (no source-editing endpoints exist yet) | Persists as long as its storage entry does (no expiry logic in Phase 1) | `SourceSummary` DTO: `source_id`, `workspace_id`, `provider_type`, `original_filename(s)`, `status`, `created_at`, `channel_count` | Points at, but does not itself hold, the full-resolution parsed data — see §12 | Backed by files in `StorageBackend`'s `original` category (immutable) plus a small JSON metadata sidecar in `working` | **Yes** |
| **SourceFile** | Not a separate persisted identity in Phase 1 — represented as 1 (CSV/Excel) or 2 (COMTRADE `.cfg`+`.dat`) filenames recorded on the `Source`'s metadata sidecar | Owned by its `Source` | Immutable once written to `original` | Same as `Source` | Included inline in `SourceSummary.original_filenames` | The literal, byte-identical uploaded file(s) — this **is** the authoritative full-resolution artifact for Phase 1 | `StorageBackend` `original` category, write-once | **Yes**, but as a field on `Source`, not a standalone class — see the rationale below |
| **Channel** (base) | `(source_id, channel_name)` pair — never a bare index, per discovery's note that `powerwave` avoids array-address/GUI-object identity | Owned by its `Source`'s metadata sidecar | Immutable | Same as `Source` | Base fields shared by both subtypes: `name`, `unit` (analog only), `index` | Metadata only — never carries sample arrays, matching `powerwave`'s own `AnalogChannel`/`DigitalChannel` design (samples live in the record, not the channel object) | Part of the `Source`'s JSON metadata sidecar | **Yes** |
| **AnalogChannel** | as above | as above | Immutable | as above | Adds `phase`, `scale`, `offset`, `primary_ratio`, `secondary_ratio`, `parameter_type` where known | as above | as above | **Yes** |
| **DigitalChannel** | as above | as above | Immutable | as above | Adds `normal_state` | as above | as above | **Yes** |
| **Timebase** *(response shape, not a new class)* | N/A | N/A | N/A | N/A | `timing_reference`, `start_time`, `trigger_time`, `sample_count`, `duration_seconds`, `sampling_rates`, `samples_per_rate` — a direct, flattened projection of `TimingInformation`+`SamplingInformation` | Describes, doesn't hold, the full-resolution axis | Part of the metadata sidecar | **Yes**, as a response field, not a persisted class |
| **ImportResult** | Not persisted — a synchronous request/response value only | N/A | N/A | One HTTP request | `status` (`"ready"` \| `"failed"` \| `"needs_input"`), `source_id` (when accepted), `validation_messages: list[{severity, code, message}]` | N/A | N/A | **Yes** |

**Why `SourceFile` is not a standalone persisted class in Phase 1**: giving
it its own identity/table now would be premature — Phase 1 has exactly one
relationship (`Source` owns 1–2 files) and no independent lifecycle for a
file apart from its `Source`. Promoting it to a first-class model is cheap
to do later (Phase 8/persistence) if multi-file sources grow more complex;
forcing it now would be exactly the kind of "conventional repository
structure with no genuine product/engineering consequence" the task brief
says not to over-design (§9 of the task brief).

**Why no `EventAnalysisSession`-equivalent yet**: Phase 1 has no
multi-source alignment, no calculated signals, no cursor state — none of
the concerns that class exists to serve. Introducing it now would be
scope creep; `Workspace` as a pure scoping key is deliberately the entire
extent of "session" concept needed for this slice.

### 3. Target module map (backend)

Current `oruxa_powerwave` backend layout (verified 2026-08-14, unchanged
since the discovery pass): a flat `backend/app/{__init__,config,main,storage}.py`
— no subpackages exist yet. Proposed layout for Phase 1/1.5:

```text
backend/app/
├── __init__.py                  (existing)
├── main.py                      (existing — extended to mount new routers)
├── config.py                    (existing — unchanged)
├── storage.py                   (existing — unchanged; already provides exactly
│                                  the categories this design needs: original/
│                                  working/temporary)
│
├── domain/                      (NEW — pure Python, zero framework imports,
│   │                              mirrors powerwave's app/models/ near-verbatim)
│   ├── __init__.py
│   ├── disturbance_record.py    ← ported from app/models/disturbance_record.py
│   ├── channels.py              ← ported from app/models/channels.py
│   ├── metadata.py              ← ported from app/models/metadata.py
│   ├── timing.py                ← ported from app/models/timing.py
│   └── source.py                (NEW — oruxa_powerwave-specific: Source,
│                                  SourceSummary-building helpers)
│
├── providers/                   (NEW — mirrors powerwave's app/providers/,
│   │                              same Qt-free reuse)
│   ├── __init__.py
│   ├── base.py                  ← ported from app/providers/base/*.py
│   ├── comtrade.py              ← ported from app/providers/comtrade/comtrade_provider.py
│   ├── csv_provider.py          ← ported from app/providers/csv/csv_provider.py
│   ├── excel_provider.py        ← ported from app/providers/excel/excel_provider.py
│   └── import_wizard/           (Phase 1.5 — ported from app/import_wizard/,
│                                  27 files, kept as its own subpackage)
│
├── services/                    (NEW — orchestration; the only layer allowed
│   │                              to know about StorageBackend + providers together)
│   ├── __init__.py
│   └── import_service.py        (NEW — upload → stage → provider-select →
│                                  parse → commit-to-storage → metadata-sidecar
│                                  → SourceSummary; owns source_id minting)
│
├── schemas/                     (NEW — Pydantic request/response DTOs;
│   │                              the ONLY layer allowed to import Pydantic/FastAPI
│   │                              types alongside domain types)
│   ├── __init__.py
│   └── source.py                (SourceSummary, ChannelSummary, TimebaseSummary,
│                                  ImportResult, ErrorResponse)
│
└── api/                         (NEW — FastAPI routers only; thin, no business logic)
    ├── __init__.py
    └── v1/
        ├── __init__.py
        └── sources.py           (the four endpoints in §7 below)
```

**Dependency direction** (enforced by convention, matching
`powerwave`'s own "UI must not implement analytics" layering philosophy,
translated to this stack): `api/` → `schemas/` + `services/`; `services/` →
`domain/` + `providers/` + `storage.py` + `config.py`; `providers/` →
`domain/` only. `domain/` has **zero** outward dependencies — no Pydantic,
no FastAPI, no storage awareness. This mirrors discovery's own finding that
`powerwave`'s most reusable code is exactly the code with the fewest
outward dependencies.

### 4. Workspace/session ownership

`[DECISION MODE: ANALYSIS]` — enough evidence exists from discovery (no
concurrency model, no tenant concept, source-identity-instability lessons
from the `absolute_alignment` feature) to make a confident recommendation
without needing a hands-on comparison.

Options considered, per the task brief's framework:

```text
A. Request-scoped stateless parsing only
   No source_id survives past one request; every "get channels" call
   would have to re-upload and re-parse. Rejected: the API contract in
   §7 needs a second GET call after upload, which is impossible without
   some persisted identity.

B. Generated workspace/session ID with in-memory backend ownership
   A process-global dict keyed by workspace_id/source_id. Rejected as the
   PRIMARY mechanism: this is exactly the "server-global state that would
   later require architectural rework" the task brief warns against (§15) —
   lost on restart, unsafe across multiple worker processes, and a direct
   repeat of powerwave's own single-process assumption that discovery
   flagged as a multi-user risk.

C. Generated workspace/session ID with lightweight persistence
   Recommended, with one adaptation: use the EXISTING StorageBackend
   (already built, already tested) as the lightweight persistence layer —
   a small JSON metadata sidecar per source, written to the `working`
   category, keyed by workspace_id/source_id in its path — rather than
   introducing a database (out of scope per Milestone 1) or a cache
   service (unjustified new infrastructure for this slice's actual needs).

D. Another justified approach (e.g. a database-backed session table)
   Rejected for Phase 1 specifically: PostgreSQL is architecturally
   planned but explicitly out of Milestone 1 scope; introducing it now
   only to store a handful of small metadata records would be
   disproportionate. Revisit at Phase 8 (persistence/projects), where a
   database becomes clearly justified by richer requirements (full
   session state, not just import metadata).
```

**Recommendation**: **C, using the existing `StorageBackend` rather than a
new database or in-memory cache.** `workspace_id` and `source_id` are UUIDs;
no server-global mutable dict is introduced; a process restart loses
nothing beyond what's already in storage (the sidecar files persist right
alongside the original uploaded files); concurrent requests are naturally
isolated by their distinct storage paths, with no shared mutable state to
guard. This is the minimum structure needed now to keep state scoped as
*"request or workspace/session"* rather than *"single process-global
current session"* (per §15 of the task brief), without building any
authentication/tenancy infrastructure this phase doesn't need.

**How `workspace_id` originates**: the frontend generates it client-side
(e.g. `crypto.randomUUID()`) on first use and includes it in every request
path. No `POST /workspaces` "create" endpoint exists in Phase 1 — a
workspace is simply "whatever storage/metadata exists under this UUID," an
implicit, ceremony-free grouping. This keeps Phase 1 minimal; introducing a
real workspace lifecycle (list, rename, delete, expire) is deferred (`[DECISION
MODE: DEFER]`) until a phase that actually needs it (e.g. Phase 8).

### 5. File upload / storage flow

```text
Browser upload (multipart/form-data)
        │
        ▼
POST /api/v1/workspaces/{workspace_id}/sources   (api/v1/sources.py — thin)
        │
        ▼
import_service.import_source(workspace_id, uploaded_files)
        │
        ├─ 1. Validate request shape (≥1 file; for COMTRADE, exactly one
        │      .cfg and one .dat with matching stems — see §10). Malformed
        │      request → 422 with `invalid_file`/`missing_companion_file`.
        │
        ├─ 2. Mint source_id = uuid4().
        │
        ├─ 3. Stage: write uploaded bytes into StorageBackend's `temporary`
        │      category under `{workspace_id}/{source_id}/{original_filename}`
        │      for every file in the request. (For COMTRADE, both .cfg and
        │      .dat land in the SAME temporary subdirectory with their
        │      original stems preserved — satisfying ComtradeProvider's
        │      `_find_dat_file` same-directory/same-stem requirement with NO
        │      adaptation to that parser needed.)
        │
        ├─ 4. Select provider: suffix-based, mirroring ProviderManager's
        │      insertion-order can_load() resolution (ported near-verbatim).
        │      No provider found → 400 `unsupported_file_type`.
        │
        ├─ 5. Parse: provider.load(staged_path). Exceptions map to the
        │      error taxonomy in §9. On any failure: delete the temporary
        │      files, return the error — nothing is written to `original`
        │      or `working`.
        │
        ├─ 6. On success: move (not copy — avoid a redundant duplicate
        │      write) the staged file(s) from `temporary` to `original`
        │      under `{workspace_id}/{source_id}/...`. `original` is
        │      write-once (already enforced by StorageBackend), so this can
        │      only ever happen once per source_id — a structural guarantee
        │      against accidental re-parse-and-overwrite.
        │
        ├─ 7. Extract lightweight metadata (channel list, timing summary,
        │      sample counts — NOT the waveform arrays) from the parsed
        │      DisturbanceRecord and write it as a small JSON file into
        │      `working` under the same {workspace_id}/{source_id} path.
        │      The full DisturbanceRecord object is then discarded — Phase 1
        │      does not hold parsed waveform arrays in memory beyond the
        │      single request that produced them (see §12).
        │
        └─ 8. Return 201 with ImportResult(status="ready", source_id, ...).
```

**Design decisions made explicit here**:

- **Temporary vs retained**: staged files in `temporary` are always
  transient — deleted on failure, moved (not duplicated) into `original` on
  success. Nothing in `temporary` is ever considered authoritative.
- **Source identity**: minted before parsing (§11) so failure cleanup has a
  stable key to delete by, without depending on parse success.
- **File naming**: original filenames are preserved as-is inside each
  source's own `{workspace_id}/{source_id}/` directory — collisions across
  different sources are structurally impossible because of the `source_id`
  path segment, so no renaming/sanitization scheme beyond `StorageBackend`'s
  existing filename-validation (already enforced — see
  `backend/app/storage.py`) is needed.
- **Duplicate upload handling**: `[DECISION MODE: DEFER]`. Phase 1 performs
  no content-hash-based deduplication — two uploads of byte-identical files
  get two distinct `source_id`s. Whether duplicate detection should warn,
  merge, or be ignored is a product/UX question with no clear technical
  forcing function yet; revisit if/when it becomes a real user complaint
  rather than designing for a hypothetical now.
- **Cleanup**: failure-path cleanup (step 5) is the only cleanup Phase 1
  needs. No expiry/garbage-collection of abandoned workspaces is included —
  `[DECISION MODE: DEFER]`, not required to prove the architecture.
- **Cancellation implications**: discovery found `powerwave` itself has no
  real cancellation (only discard-on-arrival or a disabled Cancel button).
  Phase 1's upload+parse is a single synchronous request/response cycle for
  reasonably sized test files — there is nothing to cancel mid-flight yet.
  A real job/cancellation model is explicitly out of scope until background
  processing is needed (see §14's note on large files).
- **Future large-file implications**: `[DECISION MODE: DEFER]`. Phase 1's
  synchronous parse-in-request-handler approach will not scale to very
  large COMTRADE files without blocking a worker process; discovery already
  found `powerwave` itself has no chunked-parsing precedent to lean on. This
  is explicitly deferred rather than solved speculatively — Phase 1's own
  acceptance criteria (§8) do not require large-file performance.

### 6. Request lifecycle summary

`POST` (upload) is synchronous end-to-end for Phase 1 — accept → stage →
parse → commit → respond, all within one request/response cycle. `GET`
requests are pure reads against the `working`-category metadata sidecars,
with no parsing performed on the read path (the sidecar already contains
everything the channel-list response needs).

### 7. API contract (versioned, domain-oriented)

```text
POST /api/v1/workspaces/{workspace_id}/sources
  Purpose: upload and parse one engineering source (1 file for CSV/Excel,
    2 files — .cfg + .dat — for COMTRADE, see §10).
  Request: multipart/form-data, one or more `files` parts.
  Response: 201 Created, ImportResult (status, source_id, validation_messages).
    202 Accepted is NOT used — Phase 1 has no async job model (see §5's
    cancellation note); parsing completes within the request.
  Errors: 400 unsupported_file_type / missing_companion_file / invalid_file,
    422 malformed request shape, 500 storage_error / internal_error.
  Ownership/security: none in Phase 1 (no auth) — workspace_id is a bare
    capability token (anyone with the UUID can read/write that workspace).
    Explicitly acceptable for Phase 1 per the multi-user readiness framing
    in §18; NOT acceptable once real users/data are involved (Phase 9).
  Required in first slice: Yes.

GET /api/v1/workspaces/{workspace_id}/sources
  Purpose: list sources uploaded into this workspace.
  Request: none beyond the path parameter.
  Response: 200, list[SourceSummary].
  Errors: 200 with an empty list for an unknown/empty workspace_id (no
    "workspace not found" error — a workspace has no separate existence
    beyond "sources that happen to exist under this ID," per §4).
  Required in first slice: Yes (needed for a usable channel-list frontend,
    even a single-source one — see §16).

GET /api/v1/workspaces/{workspace_id}/sources/{source_id}
  Purpose: retrieve one source's summary/status.
  Response: 200, SourceSummary. 404 if unknown.
  Required in first slice: Optional — GET .../sources already returns this
    shape per-item; a dedicated single-item endpoint is a small convenience,
    not a hard requirement. Recommend including it since it's nearly free
    once the list endpoint exists.

GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/channels
  Purpose: the actual first-slice payload — channel metadata for one source.
  Response: 200, { source: SourceSummary, timebase: TimebaseSummary,
    analog_channels: list[AnalogChannelSummary], digital_channels: list[DigitalChannelSummary] }.
  Errors: 404 if source_id unknown within the workspace.
  Required in first slice: Yes — this is the slice's actual deliverable.
```

No generic table-style endpoints (e.g. no `/api/v1/db/sources`) — every
route names a domain concept, per the task brief's explicit guidance.

### 8. API response size discipline

Per the task brief: **no waveform arrays in Phase 1 responses at all.**
`GET .../channels` returns only:

- Source identity, provider type, original filename(s), status.
- Timing mode (`timing_reference`), start/trigger time (when meaningful —
  omit or null for non-absolute modes, matching discovery's finding that
  synthetic/sample-index origins must not be presented as real calendar
  time), sample count, duration.
- Sampling information (rate list, samples-per-rate list — supports
  COMTRADE multi-rate display even at this early stage).
- Per channel: name, unit (analog only), analog-vs-digital, index, and
  (analog only) phase/scale/offset/ratios/parameter_type where known.

This keeps every Phase 1 response small regardless of the underlying
recording's sample count — a multi-hundred-thousand-sample COMTRADE file
and a 10-sample CSV produce responses of near-identical size.

### 9. Error model

```text
unsupported_file_type      — no registered provider's can_load() accepted the upload
invalid_file                — file present but structurally unreadable (e.g. corrupt CFG)
parse_error                 — provider raised during load() for a reason not covered below
missing_companion_file      — COMTRADE .cfg uploaded without a matching .dat (or vice versa)
unsupported_comtrade_variant — e.g. BINARY32 (mirrors powerwave's own explicit rejection)
ambiguous_timestamp         — Phase 1.5 only; Import Wizard could not confidently resolve
                               a timestamp column and the request did not opt into a
                               specific repair strategy (see §15)
storage_error                — StorageBackend raised (e.g. ImmutableFileError on an
                               unexpected re-parse attempt, disk failure)
invalid_workspace            — malformed workspace_id or source_id (not a well-formed UUID)
internal_error                — catch-all; full detail logged server-side, generic
                               message returned to the client
```

Every error response is a small structured JSON object
(`{"code": "...", "message": "...", "details": {...}}`), never a raw
Python traceback or exception string — this is a **required behaviour
change relative to `powerwave`**, not an optional improvement: discovery
found `powerwave`'s COMTRADE path shows raw exception text in a
`QMessageBox`, which was tolerable in a single-analyst desktop tool but is
not acceptable for a public API (see §14's "exceptions where preserving
current behaviour would itself be unsafe"). Full exception detail is still
logged server-side for debugging — nothing is lost, just not exposed.

### 10. COMTRADE multi-file upload

`[DECISION MODE: ANALYSIS]` for the **transport mechanism** (clear
technical winner); `[DECISION MODE: UAT]` for the **pairing UX** (genuine
usability question).

```text
A. Single multipart POST with both files attached in one request
   Atomic: either both files are accepted together or nothing is written.
   Matches ComtradeProvider._find_dat_file's own same-directory expectation
   with zero adaptation needed at the parser boundary — the service layer
   just stages both files into one directory before calling load().
   Recommended for the transport mechanism.

B. Staged upload (POST .cfg, then a follow-up POST referencing it for .dat)
   Rejected: two round trips, a new "pending upload" concept and expiry
   policy to design, no compensating benefit over A for files of the size
   COMTRADE records typically are.

C. Zip/package upload
   Rejected: adds a compression/extraction dependency and an unfamiliar
   manual step (creating a zip) that is not how COMTRADE files are
   normally handled by engineers already familiar with .cfg/.dat pairs.
```

**Recommendation for transport**: **A** — one multipart request, both
files as separate `files` parts, staged into one temporary directory by the
service layer. This is confident enough to treat as ready for approval
without a hands-on comparison; the alternatives have no offsetting
advantage.

**What genuinely needs UAT**: how the *browser-side selection UX* pairs
`.cfg`+`.dat` files before that single request is sent — e.g., does the
frontend (a) let the user drag-and-drop or multi-select both files at once
and auto-pair them by matching stem, surfacing a clear error for any
orphaned file; or (b) present two explicit named drop targets ("Config
file" / "Data file")? Both are technically trivial to implement; which
one an actual engineer finds natural is a real hands-on usability question,
not something resolvable by code inspection alone — see the UAT candidates
section below.

### 11. Source identity

`source_id = uuid4()`, generated server-side at the moment an upload is
accepted for processing (before parsing, so failure-path cleanup has a
stable key — see §5). Never derived from filename, array address, or any
GUI-object-identity equivalent — directly avoiding the exact anti-pattern
discovery flagged in `powerwave`'s own live-session UUIDs (fresh-per-load,
not stable across reloads, which forced `powerwave`'s newest feature to
build a whole separate stable "manifest source_id" + translation-map
mechanism after the fact). By minting a stable, storage-path-embedded ID
from the start, `oruxa_powerwave` avoids needing to retrofit that same fix
later — this ID is inherently stable across process restarts (unlike
`powerwave`'s in-memory session UUIDs) because it is embedded directly in
the storage path, not held only in process memory.

This ID is deliberately proportionate to Phase 1: no separate "content
hash" or "version" concept is attached to it yet (see the Duplicate upload
handling note in §5) — just enough to support future multi-source
workspace, calculated signals, synchronization, persistence, and
auditability without over-designing now.

### 12. Record aliasing risk

**What aliasing currently means in `powerwave`**: `DisturbanceRecord.waveform_data`
is explicitly documented as "stored by reference — never copied on
construction" (`app/models/disturbance_record.py:23`, re-confirmed
2026-08-14). Every consumer (session, analytics, calculated signals) reads
the same underlying `pandas.DataFrame` object. No mutation-in-place was
found anywhere in `powerwave`'s `app/` tree, but the *contract itself* makes
it structurally easy to introduce one accidentally — nothing prevents a
future contributor from doing `record.waveform_data["VA"] *= 2` in place.

**How accidental shared mutation could occur in a web backend
specifically**: if a parsed `DisturbanceRecord` (or its DataFrame) were ever
cached and handed out to multiple concurrent requests/users — e.g. as a
"performance optimization" to avoid re-parsing — any in-place mutation by
one request would silently corrupt what every other holder sees. This is a
categorically bigger risk in a shared server process than in a single-user
desktop process.

**How the target design avoids it**: Phase 1 sidesteps the entire risk
class structurally, not by convention — **no parsed `DisturbanceRecord` or
its DataFrame is ever cached, shared, or held across requests.** Each
`POST .../sources` parses once, extracts small immutable metadata
(names/units/counts — never the arrays themselves) into the JSON sidecar,
and discards the full record at the end of that single request (see §5
step 7 and §3's `services/import_service.py`). There is no in-process
object for two requests to ever alias.

**Should arrays be immutable by convention or enforcement, and where is
copying genuinely required?** For Phase 1: moot — no array ever leaves a
single request's scope, so there is nothing to protect against aliasing
across requests. The one place a copy is unavoidable and appropriate is the
provider's own parse step (`np.fromfile`/`pd.read_csv` producing a fresh
array from bytes on disk) — this is required work, not defensive
over-copying. `[DECISION MODE: DEFER]` for later phases: once a phase
introduces a genuine need to hold parsed waveform data across multiple
requests (e.g. Phase 2's viewport decimation), that phase must explicitly
decide whether cached records are made read-only by convention (matching
`powerwave`'s own — unenforced — approach) or by stricter enforcement
(e.g. read-only numpy array views). Not a Phase 1 concern since Phase 1
never retains the arrays at all.

### 13. Full-resolution data ownership

For Phase 1, the **immutable stored original file itself** (in
`StorageBackend`'s `original` category) is the authoritative full-resolution
data owner — not any in-memory object. Any future phase needing the actual
waveform arrays (Phase 2's decimated viewport delivery, Phase 6's
calculated signals, Phase 7's analytics) re-derives them by re-parsing the
stored original on demand (or introduces an explicit, deliberately-designed
cache at that point — not assumed now). This is a direct, intentional
parallel to how `powerwave` itself keeps `DisturbanceRecord.waveform_data`
authoritative and untouched while decimating only for display — except
`oruxa_powerwave`'s version of "the untouched authoritative copy" is a
write-once file on disk, which is a *stronger* immutability guarantee than
`powerwave` provides (see [POWERWAVE_DISCOVERY.md — Original Source
Immutability](POWERWAVE_DISCOVERY.md#original-source-immutability)).

No detailed waveform-delivery mechanism is designed here, per the task
brief's explicit instruction — this section only establishes *ownership*,
not delivery.

### 14. Persistence boundary

`[DECISION MODE: DEFER]` for the broader session/workspace persistence
question (do NOT prematurely commit to YAML-manifest-style persistence, per
the task brief). For Phase 1 specifically, the **minimum state that must
persist** is exactly the small JSON metadata sidecar described in §5/§4 —
enough to answer `GET .../sources` and `GET .../sources/{id}/channels`
without re-parsing. Nothing else needs to persist yet: no session/workspace
object beyond the implicit path-scoping, no calculated signals, no
alignment state, no user preferences. The broader question of "what is
`oruxa_powerwave`'s general persistence model" (matching or diverging from
`powerwave`'s narrow manifest-based alignment persistence) is explicitly
carried forward as discovery Open Question #5 (see the review below) and
should be addressed at Phase 8, not forced now.

### 15. Preserve behaviour vs improve behaviour

Applying discovery's own weaknesses through the lens the task brief
requires — migration compatibility vs. future engineering improvement —
with exceptions called out where preserving current behaviour would itself
be unsafe:

| Discovered weakness | Treatment | Reasoning |
|---|---|---|
| COMTRADE has no discontinuity/gap detection | **Preserve for now** (migration compatibility); tracked as discovery Open Question #2 for future improvement | Adding new detection during a migration silently changes engineering-visible behaviour without a separate approval — exactly what §19 of the task brief warns against |
| Raw exception strings shown to the user (COMTRADE path) | **Must NOT preserve — safety exception** | A public API leaking Python tracebacks is a real security/quality issue, not a stylistic preference; §26 of the task brief explicitly forbids this regardless of migration-fidelity concerns |
| Two non-communicating CSV/Excel classification systems (`RuleManager`/YAML vs. wizard detectors) | **Do not port `RuleManager`/YAML rules system into Phase 1.5 at all** | It already has zero effect on `powerwave`'s own interactive path (confirmed in discovery); porting dead-weight infrastructure "for fidelity" would be actively worse than omitting it. Final unify-or-drop decision remains discovery Open Question #4 |
| BEN32 vendor-quirk year remapping narrower in code than in policy doc | **Preserve the code's actual (narrower) behaviour** | This is a pre-existing, low-severity discrepancy between `powerwave`'s own doc and code; not a migration decision at all — just don't accidentally implement the doc's broader claim instead of the code's actual behaviour when porting |
| No COMTRADE review/preview step before display | **Preserve absence for Phase 1** | Phase 1 has no display step yet at all (channel-list only) — not applicable until a later phase; not a data-integrity issue for this slice |
| Manual Import-Wizard overrides don't survive save/reload | **Not applicable to Phase 1/1.5** | This is a `powerwave`-desktop persistence-specific gap tied to its manifest feature; `oruxa_powerwave` has no equivalent persistence yet (§14) so the gap doesn't exist to inherit |

### 16. Import Wizard handling — Phase 1 vs Phase 1.5

`[DECISION]` **Settled — see [DECISIONS.md — DEC-014](DECISIONS.md#dec-014--phase-1-is-comtrade-only-csvexcel-and-import-wizard-grade-timestamp-handling-are-deferred-to-phase-15).**
This section originally presented Phase 1's CSV/Excel inclusion as an open
`[DECISION MODE: ANALYSIS]` choice between two options; the owner has since
decided explicitly. Kept here (rather than deleted) so the reasoning behind
the choice stays visible — the original comparison is preserved below for
context.

**Decided**: Phase 1 ships with **COMTRADE support only**, using the direct
`ComtradeProvider` (Category A, no timestamp ambiguity concern — COMTRADE's
timestamps either parse or the provider raises, per discovery). **General
CSV/Excel import is explicitly excluded from Phase 1** — not a temporary
best-effort subset, not the direct providers, not the Import Wizard. CSV/Excel
support, together with Import-Wizard-grade timestamp detection/repair, is
**Phase 1.5** — planned, scope defined below, not yet implemented and not
yet approved for implementation.

**Why**: pulling the full Import Wizard (27 files, a multi-page interactive
UX) into the very first slice would violate the "prove the architecture
without unnecessary complexity" goal that motivated choosing this slice in
the first place (see [POWERWAVE_DISCOVERY.md — Recommended First
Implementation Slice](POWERWAVE_DISCOVERY.md#recommended-first-implementation-slice)).
`powerwave`'s direct CSV/Excel providers bypass the richer timestamp
classification/repair behaviour that only the Import Wizard backend
provides (per [POWERWAVE_DISCOVERY.md — File Import Pipeline](POWERWAVE_DISCOVERY.md#file-import-pipeline));
shipping a temporary, simplified CSV/Excel path in Phase 1 would either
silently under-serve real files or require re-deriving part of the
Wizard's complexity ahead of schedule. COMTRADE alone already exercises
every architectural question Phase 0 needs answered (provider selection,
multi-file upload, storage boundary, metadata API) without also requiring a
decision about how to represent an interactive, multi-step,
potentially-blocking timestamp-repair workflow in a stateless
request/response API — that design problem (does the API return a "needs
input" state and a follow-up endpoint? per-request override parameters?
something else?) is deliberately left for Phase 1.5's own dedicated design
pass, not solved ahead of schedule here. **CSV/Excel are not being
dropped** — only sequenced after COMTRADE proves the architecture.

**When Phase 1.5 is designed**, the "needs input" approach originally
sketched here remains a reasonable starting point: unresolved timestamp
ambiguity should produce an explicit `needs_input` `ImportResult.status`
with a structured `ambiguous_timestamp` message — never a silent best-guess
that could misrepresent engineering time — over either "reject unresolved
imports" (too harsh — the file did parse, just with a specific unresolved
decision) or "provide minimum metadata only" (misleading — it would imply
confidence the system doesn't have). This is **not** approved Phase 1.5
design, only a carried-forward starting point for whoever designs that
phase.

### 17. Frontend first-slice design

`[PROPOSAL]`, kept intentionally small:

- **Page/component structure**: one page. An upload area + a source list +
  a channel-list detail view for the selected source. No routing complexity
  needed yet (a single-page component tree is sufficient).
- **Upload interaction**: a file picker/drop zone; for COMTRADE, either
  accepting a multi-select of both `.cfg`+`.dat` (auto-paired by stem
  client-side) or two explicit slots — this exact choice is a UAT candidate
  (§10, and listed again below).
- **Progress/loading state**: since Phase 1's upload is synchronous
  request/response (no job polling), a simple busy indicator for the
  duration of the POST is sufficient — no percentage progress is
  needed yet (matches the honesty discovery found in `powerwave`'s own
  indeterminate-busy-spinner pattern, which is fine for a bounded,
  synchronous operation).
- **Parse errors**: rendered from the structured error taxonomy (§9) as a
  plain, specific message per `code` — never a raw exception string,
  matching the backend's own error-model discipline.
- **Source summary**: filename(s), provider type, status, channel counts
  (analog/digital), duration, once available.
- **Channel grouping**: mirror `powerwave`'s own proven
  voltage/current/power/frequency/digital/other classification-by-unit/name
  approach (discovery flagged `powerwave` itself has two duplicate,
  independently-maintained implementations of this — `oruxa_powerwave`
  should port the *idea*, implemented once, not either specific duplicate).
- **Analog/digital distinction**: a clear visual/structural separation
  (e.g. two lists or two tabs), matching the domain model's own separation.

Explicitly **not** in scope for this slice's frontend: any chart/waveform
rendering, any multi-source workspace UI, any cursor/measurement UI.

### 18. Testing strategy

**Migration parity tests**: for each ported provider (COMTRADE first,
CSV/Excel if included), run the same fixture file through
`powerwave`'s own canonical provider and `oruxa_powerwave`'s ported
provider, and assert equivalence per the Numerical Equivalence definition
below. `[OPEN — new, not one of the original nine]`: whether to physically
copy 2–3 small representative sample fixtures from `powerwave`'s `samples/`
directory into `oruxa_powerwave`'s own `backend/tests/fixtures/` (recommended,
to avoid a runtime cross-repo dependency in CI) needs a quick licensing/size
check before doing so — flagged here, not blocking Phase 0 approval, but
worth resolving before Phase 1 implementation starts.

**Unit tests**: provider selection (suffix routing, unknown-type
rejection), source-identity minting, channel-metadata extraction/shape,
storage staging/commit/rollback-on-failure, `DisturbanceRecord` validation,
API DTO serialization.

**API tests**: valid COMTRADE upload → 201 + correct channel list; upload
with only `.cfg` (no `.dat`) → `missing_companion_file`; unsupported
extension → `unsupported_file_type`; a deliberately corrupted `.cfg` →
`invalid_file`/`parse_error`; a BINARY32 COMTRADE file →
`unsupported_comtrade_variant`; duplicate upload of the same file → two
distinct `source_id`s, both listed (confirming the deferred-dedup decision
from §5 behaves as intended, not as a bug); `GET .../channels` for an
unknown `source_id` → 404.

**Regression fixtures**: use more than one sample event per format (COMTRADE
ASCII, COMTRADE Binary, at minimum) — per the task brief's explicit warning
against designing around a single sample event (see also
[POWERWAVE_DISCOVERY.md — Do Not Design Around Sample Files](POWERWAVE_DISCOVERY.md)
principle, carried forward here).

### 19. Numerical equivalence

"Same behaviour" for migration parity is defined as:

| Field | Equivalence rule |
|---|---|
| Channel count, channel names, units | Exact match |
| Sample count | Exact match |
| Start time, trigger time | Exact match (same `datetime`, same precision) |
| Sampling information (rates, samples-per-rate lists) | Exact match |
| Scale/offset/ratio metadata | Exact match |
| Analog/digital sample arrays | `numpy.allclose` with a tight tolerance (`rtol=1e-12`, `atol=1e-12`) rather than bitwise equality — since the *same* ported Python arithmetic is expected to run, any difference beyond floating-point noise (e.g. from a NumPy/pandas version difference) is a signal worth investigating, not an expected outcome to tolerate loosely |

Exact equality is not used for float arrays specifically because different
NumPy/pandas versions between the two environments could theoretically
produce sub-epsilon differences in summation order — the tolerance is
intentionally tight enough that a real bug still fails the test.

### 20. Multi-user readiness without premature authentication

No authentication is implemented in Phase 0/1, matching the task brief and
`oruxa_powerwave`'s own existing Milestone 1 scoping. What *is* deliberately
built now to avoid future rework: every piece of state introduced in this
design is scoped by `workspace_id`/`source_id` path segments — never a
bare, unscoped process-global — and no in-memory cache/registry is
introduced at all (§4). The only "identity" concept in Phase 1 is a bare
capability-token-style UUID with no ownership verification — adequate for a
single-operator development/demo phase, explicitly **not** adequate once
real users and real data are involved (that gap is exactly what Phase 9 is
for). This satisfies the brief's instruction to avoid overengineering
auth/tenant infrastructure while still not painting the architecture into a
corner.

### 21. State isolation

Concurrent requests against different `workspace_id`s touch entirely
disjoint storage paths and disjoint sidecar files — no shared mutable
object exists for them to contend over. Concurrent requests against the
*same* `workspace_id` (e.g. two near-simultaneous uploads) are isolated by
each getting its own freshly-minted `source_id` and thus its own storage
path — no write-write conflict is possible at the file level.
`StorageBackend`'s existing filename-validation and write-once enforcement
(already built, already tested) do the rest. No new locking primitive is
needed for Phase 1's actual request shapes.

### 22. Future extensibility

This design deliberately leaves room, without building ahead of need, for:
Phase 2's viewport-decimation endpoint (would re-parse from the same
`original`-category file this design already established as authoritative);
Phase 3's multi-source workspace (the `Workspace`/`Source` split already
exists — Phase 3 mainly needs to add the alignment/session-state concept on
top, not restructure what's here); Phase 6's calculated signals (would
consume the same `Source`/channel identity scheme); Phase 8's real
persistence (would likely promote the JSON sidecar mechanism into a proper
database-backed model, or replace it outright — either is a contained
change since nothing else in this design depends on the sidecar's *storage
mechanism*, only on the `SourceSummary`/`ChannelSummary` *shapes* it
produces).

---

## Review of the nine discovery open questions

Per [POWERWAVE_DISCOVERY.md — Open Questions](POWERWAVE_DISCOVERY.md#open-questions).
None are forced to a final answer here — each gets a decision-mode
classification and a recommendation for *now* (Phase 0/1), not necessarily
forever.

**1. Timing-mode enforcement in the general offset API**
Why it matters: prevents sample-index-mode sources from being
cross-record-synchronized as if they were real time. When it becomes
blocking: Phase 4 (Synchronization) — not before. Decision mode: `[DECISION
MODE: ANALYSIS]` when it comes up, but not needed now. Recommendation for
now: no action; Phase 1 has no synchronization/offset concept at all.

**2. COMTRADE discontinuity/gap detection**
Why it matters: silent data dropouts currently produce no diagnostic.
When it becomes blocking: whenever engineering trust in imported COMTRADE
data becomes a live concern — arguably as early as Phase 1, as a
*diagnostic*, though not as a blocker to import. Decision mode: `[DECISION
MODE: ANALYSIS]` — recommend adding a simple diagnostic-only gap check to
`ChannelSummary`/`SourceSummary`'s validation_messages in Phase 1 itself
(non-fatal, informational), since discovery already flagged this as a real
current gap and it's cheap to surface without changing parse behaviour.
Not a blocker either way — flagged as a nice-to-have for the first
implementation task to consider, not a hard requirement.

**3. Raw timestamp traceability after normalization**
Why it matters: no re-audit-against-original-file capability exists
downstream of import today. When it becomes blocking: only if/when an
audit or re-derivation feature is actually requested. Decision mode:
`[DECISION MODE: DEFER]`. Recommendation for now: Phase 1's
write-once `original` storage already provides a *stronger* guarantee than
`powerwave` has (the literal original bytes are always retrievable) — this
substantially de-risks the concern even without a dedicated "raw value"
field in the parsed metadata.

**4. Duplicate CSV/Excel classification systems**
Why it matters: `RuleManager`/YAML rules currently have zero effect on the
interactive path they're meant to serve. When it becomes blocking: Phase
1.5, when CSV/Excel Import-Wizard-grade handling is actually built.
Decision mode: `[DECISION MODE: ANALYSIS]` — recommendation already made in
§15/§18: don't port `RuleManager`/YAML into Phase 1.5 at all.

**5. Persistence model**
Why it matters: determines whether `oruxa_powerwave` needs a database, a
manifest-file equivalent, both, or neither, and when. When it becomes
blocking: Phase 8. Decision mode: `[DECISION MODE: COMPARISON]` when Phase
8 arrives — a database vs. file-based approach both have real tradeoffs
worth laying out side by side once the actual persistence requirements
(what exactly needs to survive a reload) are concrete. Recommendation for
now: `[DECISION MODE: DEFER]` — Phase 1's own minimal sidecar mechanism
(§14) is sufficient and does not commit the project to either future
direction.

**6. Calculated-signal expression grammar**
Why it matters: current grammar can't express common power-engineering
formulas like real power from V×I. When it becomes blocking: Phase 6.
Decision mode: `[DECISION MODE: COMPARISON]` at that time — weighing
grammar-expansion complexity against engineering usefulness deserves a
side-by-side look at specific candidate formulas, not a snap judgement.
Recommendation for now: no action needed.

**7. Frequency/ROCOF computation scope**
Why it matters: `powerwave` itself never computes these from raw
waveforms — only classifies/displays pre-computed channels. When it
becomes blocking: Phase 7 (or earlier if a specific engineering workflow
needs it sooner). Decision mode: `[DECISION MODE: ANALYSIS]` when it comes
up — the DSP approach is well-understood engineering, not something that
needs hands-on comparison to decide *whether* to build, though the specific
algorithm choice might. Recommendation for now: no action needed.

**8. Suggestions/next-action feature**
Why it matters: purely a UX-convenience feature, not core engineering
capability. When it becomes blocking: never, structurally — it's additive.
Decision mode: `[DECISION MODE: DEFER]`, likely indefinitely until there's
a specific product reason to build it. Recommendation for now: no action.

**9. Authentication/multi-user isolation timing**
Why it matters: `powerwave`'s domain model has zero user/tenant concept
anywhere; discovery ranked this the top Critical multi-user risk. When it
becomes blocking: Phase 9 by the existing proposed sequencing, but the
*architecture* must not make Phase 9 harder than necessary — which is
exactly why §4/§20/§21 above insist on workspace/source-scoped state now
rather than process-global state that would need retrofitting later.
Decision mode: `[DECISION MODE: DEFER]` for implementation timing (already
out of `oruxa_powerwave`'s own current Milestone 1 scope per
[AGENTS.md](../../AGENTS.md)); `[DECISION MODE: ANALYSIS]` for the
architectural preparation, which this Phase 0 design already addresses.
Recommendation for now: no auth implementation; the state-scoping
discipline in this design is the concrete preparation for it.

---

## Candidate Decisions Requiring Future UAT

For each: why analysis alone is insufficient, what to test, when, what the
user should compare, and what decision it feeds. **No prototypes are built
as part of this task** — proposal only, per the task brief.

### UAT-1: COMTRADE `.cfg`/`.dat` pairing UX — `[DECISION]` RESOLVED 2026-08-14

**Resolved by owner UAT — see [DECISIONS.md — DEC-017](DECISIONS.md#dec-017--comtrade-two-slot-cfgdat-upload-is-the-approved-interaction-resolves-uat-1).**
Option B (two explicit named slots, already shipped) is approved as the
COMTRADE upload interaction, not a placeholder. Kept below, unmodified, for
the historical reasoning — this is no longer an open UAT item.

- **Why analysis alone is insufficient**: whether an engineer finds
  drag-and-drop auto-pairing-by-stem intuitive, or prefers two explicit
  named slots, is a genuine hands-on usability question — both are
  technically sound, and reasoning about "which feels natural" from a
  design doc alone is unreliable.
- **Alternatives to test**: (a) single multi-file drop zone with client-side
  auto-pairing by filename stem and a clear error for orphaned files; (b)
  two explicit labeled drop targets ("Configuration file (.cfg)" / "Data
  file (.dat)").
- **When to build the prototype**: at the start of Phase 1's actual
  frontend implementation — cheap to build both variants since the backend
  contract (§7, §10) is identical either way.
- **What the user should observe/compare**: upload a real `.cfg`+`.dat`
  pair using both interaction patterns; note which one is faster, less
  error-prone, and which produces a clearer error when a file is
  mismatched or missing.
- **Decision it informs**: which upload interaction pattern ships in Phase
  1's frontend (does not affect the backend API contract either way).

### UAT-2: Error message wording/specificity for the error taxonomy

- **Why analysis alone is insufficient**: the error *codes* in §9 are
  well-grounded in `powerwave`'s actual failure modes, but the exact
  user-facing *wording* for each (how much technical detail an engineer
  wants vs. finds noisy) is a product-voice question best judged by
  showing real error states to a real user, not guessed at.
- **Alternatives to test**: terse ("Unsupported file type") vs. more
  explanatory ("This file doesn't look like a COMTRADE, CSV, or Excel
  file we recognize — check the extension and try again") message styles
  per error code.
- **When to build the prototype**: alongside Phase 1's frontend, once real
  error responses exist to react to.
- **What the user should observe/compare**: trigger each error case (bad
  extension, missing companion file, corrupt file, BINARY32) and judge
  which message style is actually helpful in the moment, not in the
  abstract.
- **Decision it informs**: final frontend copy for the error taxonomy —
  does not affect the backend `code` values themselves, only the
  `message` text and any frontend-side presentation layer on top.

### UAT-3 (carried forward from discovery, restated here): calculated-signal expression grammar expansion

- **Why analysis alone is insufficient**: whether adding `signal × signal`
  support (to express real power `P = V × I × cos(θ)`) is worth the added
  grammar complexity and validation surface depends on how often engineers
  actually reach for that formula vs. how much added UI/validation
  complexity it costs — best judged by watching real usage of the simpler
  grammar first.
- **Alternatives to test**: current restricted grammar (`+ - * / abs()`,
  no signal×signal) vs. an expanded grammar with explicit dimensional
  multiplication support.
- **When to build the prototype**: not before Phase 6 — far outside
  Phase 0/1 scope; listed here only to keep it visible as a UAT candidate
  rather than let it silently become an ANALYSIS-only decision later.
- **What the user should observe/compare**: try to express a handful of
  real disturbance-analysis formulas under each grammar; note which ones
  are blocked by the restriction and how often that actually matters in
  practice.
- **Decision it informs**: discovery Open Question #6.

---

## Exact first implementation scope

`[DECISION]` Scope below is COMTRADE-only per
[DECISIONS.md — DEC-014](DECISIONS.md#dec-014--phase-1-is-comtrade-only-csvexcel-and-import-wizard-grade-timestamp-handling-are-deferred-to-phase-15).

### Included

- Backend `domain/` package: `DisturbanceRecord`, `AnalogChannel`,
  `DigitalChannel`, `RecordingMetadata`, `SamplingInformation`,
  `TimingInformation`, `DisturbanceInformation` — ported, with JSON
  serialization added.
- Backend `providers/` package: `BaseProvider`/`ProviderManager`/`ProviderRegistry`
  and `ComtradeProvider` — ported. (`CsvProvider`/`ExcelProvider` are
  explicitly **not** part of Phase 1 — see Excluded below.)
- Backend `services/import_service.py`: upload staging, provider selection,
  parse orchestration, storage commit, metadata-sidecar read/write,
  source-id minting.
- Backend `api/v1/sources.py`: all four endpoints from §7.
- Backend `schemas/source.py`: `SourceSummary`, `ChannelSummary` (analog +
  digital variants), `TimebaseSummary`, `ImportResult`, `ErrorResponse`.
- Frontend: single-page upload + source list + channel-list view, per §17.
  COMTRADE `.cfg`/`.dat` upload uses whichever pairing interaction ships
  first while UAT-1 (§ Candidate Decisions Requiring Future UAT) remains
  open — see the note there; the choice is not blocking Phase 1 approval.
- Tests: unit (providers, services, schemas), API (all error cases in §18),
  migration parity tests for COMTRADE.
- Documentation: this design (already written), plus whatever the
  implementation task itself needs to update per its own findings.

### Excluded

- **CSV/Excel import of any kind** — direct providers, Import Wizard, and
  any temporary/simplified subset. Deferred to Phase 1.5 in full — see §16
  and DEC-014. Do not introduce a partial CSV/Excel path into Phase 1
  without a separate, explicit approval.
- Waveform plotting/charting of any kind.
- Synchronization / multi-source alignment / any UI for it.
- Measurements.
- Calculated signals.
- Advanced analysis/analytics (RMS/harmonics/phasors/events/fault/protection/etc.).
- The full interactive Import Wizard UX (Phase 1.5, not Phase 1 — see §16).
- Full session/workspace persistence architecture beyond the minimal
  metadata sidecar (§14) — the long-term persistence model remains `[OPEN]`
  per DEC-013's companion note.
- Authentication / multi-user login.
- Any background-job/async-processing infrastructure (§5's cancellation
  note).
- Content-hash-based duplicate detection (§5).
- Workspace lifecycle management (create/list/rename/delete/expire).
- Chart/viewport rendering optimisation (decimation strategy etc. — Phase 2).

### Acceptance criteria

1. A `.cfg`+`.dat` COMTRADE pair uploaded via `POST .../sources` returns
   `201` with a `source_id` and `status: "ready"`.
2. `GET .../sources/{source_id}/channels` for that source returns a channel
   list whose count, names, units, and analog/digital split exactly match
   what `powerwave`'s own `ComtradeProvider` produces for the same file
   (verified by the migration parity test).
3. Each error case in §9 that's reachable from a COMTRADE-only Phase 1
   (`unsupported_file_type`, `missing_companion_file`,
   `unsupported_comtrade_variant`, `invalid_file`/`parse_error`) returns
   the correct structured error — never a raw exception string.
4. The uploaded original file(s) are present, unmodified, and write-once
   in `StorageBackend`'s `original` category after a successful import.
5. No parsed waveform array (only metadata) is present in any API response
   or held in server memory once the originating request completes.
6. All new backend code has unit test coverage; all four API endpoints
   have passing tests for both success and the applicable error cases.
7. `git diff --check` clean, no production code outside this scope
   touched, CI (`ci.yml`) passes.

---

## Files expected to change (for the future implementation task — not touched now)

```text
backend/app/domain/                new (7 files, per §3)
backend/app/providers/             new — base.py + comtrade.py only for Phase 1.
                                    csv_provider.py/excel_provider.py/import_wizard/
                                    are Phase 1.5 scope, NOT part of this
                                    implementation task (per DEC-014)
backend/app/services/              new (import_service.py)
backend/app/schemas/               new (source.py)
backend/app/api/v1/                new (sources.py)
backend/app/main.py                modified (mount the new v1 router)
backend/requirements.txt           modified (python-multipart for FastAPI file uploads;
                                    numpy/pandas for the ported COMTRADE provider —
                                    neither is currently a backend dependency, per the
                                    current oruxa_powerwave state. openpyxl is NOT
                                    needed for Phase 1 — it's a Phase 1.5 dependency)
backend/tests/                     new test modules mirroring the above, plus
                                    backend/tests/fixtures/ (sample files, pending the
                                    licensing/size check noted in §18)
frontend/                          new upload/source-list/channel-list components
                                    (current oruxa_powerwave frontend is a single static
                                    index.html with no framework — the implementation task
                                    should also decide, as its own small ANALYSIS-mode
                                    question, whether Phase 1 introduces a minimal
                                    framework or extends the existing plain-JS approach;
                                    not resolved here since it has no bearing on this
                                    document's backend-focused design)
docs/project-memory/CURRENT_STATE.md, MIGRATION_PLAN.md, HANDOFF.md
                                    updated to reflect Phase 1 completion, once done
```

## Implementation order (for the future task)

```text
1. Establish domain contracts (backend/app/domain/) with serialization + tests
2. Port the provider layer — base + COMTRADE only (per DEC-014; CSV/Excel is
   Phase 1.5, a separate future task)
3. Add storage integration to the service layer (staging/commit/rollback)
4. Service layer: import_service.py orchestration + source-id minting +
   metadata-sidecar read/write
5. API layer: schemas, then the four v1 endpoints
6. Migration parity tests (powerwave vs. oruxa_powerwave provider output)
7. Frontend: upload interaction (informed by UAT-1 if it has run by then;
   otherwise ship the simpler of the two options and revisit)
8. Frontend: channel-list display
9. End-to-end verification against the acceptance criteria above
```

COMTRADE is ordered first throughout (provider port, tests, frontend
plumbing) since it's Category A with no timestamp-ambiguity complexity —
the fastest path to proving the whole vertical slice works before any
CSV/Excel scope decision needs to be finalized.

## Rollback strategy

The first slice is deliberately low-risk and reversible:

- **`powerwave`**: never touched by any part of this design — it remains a
  read-only reference throughout. Nothing here can harm it.
- **`oruxa_powerwave`'s existing foundation**: every new module lives in
  new files/directories (`domain/`, `providers/`, `services/`, `schemas/`,
  `api/`) — the only modification to an existing file is `main.py` gaining
  one router-mount line and `requirements.txt` gaining new pinned
  dependencies. Both are trivially revertible via Git if the slice needs to
  be abandoned.
- **Stored user files**: Phase 1 introduces upload/storage behaviour for
  the first time, but it is strictly additive to `StorageBackend`, which
  already exists and is already tested — no existing storage behaviour
  changes. If the slice is abandoned, uploaded files simply become orphaned
  data under their `workspace_id`/`source_id` paths; no other part of the
  system depends on them existing, so cleanup (if ever needed) is a simple,
  isolated deletion with no cascading effects.
- **Future migration work**: nothing in Phase 2 onward is assumed to exist
  yet by this design, and nothing here forecloses a different approach
  later — the `[PROPOSAL]` status of every design choice here means a
  future task can revise any part of it (e.g. the workspace-ownership
  mechanism, the error taxonomy) without having built anything that other
  features already depend on, since nothing beyond this slice has been
  approved to build on top of it yet.
- **Abandon-and-redesign path**: if Phase 0's specific choices (e.g. the
  JSON-sidecar persistence mechanism) turn out to be wrong once real
  implementation experience accumulates, the blast radius is contained to
  `services/import_service.py` and `schemas/source.py` — the `domain/` and
  `providers/` layers (the highest-value, most directly-ported code) are
  unaffected by a service-layer redesign, since they have no knowledge of
  storage or API concerns at all (per the dependency direction in §3).

---

## Decision status summary

Updated 2026-08-14 after a governance-cleanup pass — this section now
distinguishes what the owner has **actually approved** (recorded in
[DECISIONS.md](DECISIONS.md)) from what is still only a reviewable
recommendation. Nothing in the "recommendation" tier below is approved
merely by appearing in this document.

**Approved** (`[DECISION]`, recorded in [DECISIONS.md](DECISIONS.md)):
- Prefer reuse of Qt-independent `powerwave` engineering logic — DEC-006.
- Backend authority over parsing/timestamps/calculations/synchronization/analysis — DEC-007.
- Frontend limited to presentation/interaction/visualisation/workspace controls/selections — DEC-008.
- Original uploaded files remain immutable — DEC-009.
- Engineering calculations operate on full-resolution backend data, decimation stays separate — DEC-010.
- Migration proceeds in small vertical slices — DEC-011.
- Phase 1 state is scoped by `workspace_id`/`source_id`, never process-global — DEC-012.
- Lightweight JSON metadata sidecars are acceptable for the early migration
  slice's metadata persistence **(implementation mechanism only — see the
  `[OPEN]` companion note in DEC-013; this is not approval of the long-term
  persistence architecture)** — DEC-013.
- **Phase 1 is COMTRADE-only.** CSV/Excel and Import-Wizard-grade timestamp
  handling are deferred in full to Phase 1.5 (planned, not yet implemented,
  not yet approved for implementation) — DEC-014.
- Uploaded event-record files are never persistently retained anywhere
  (ephemeral-only handling) — DEC-015.
- Upload size ceiling is configuration (`MAX_EVENT_UPLOAD_SIZE_MB`), ~100 MB
  the current MVP assumption, not a hard-coded limit — DEC-016.
- **COMTRADE two-slot `.cfg`/`.dat` upload is the approved interaction**,
  resolved by owner UAT of the deployed Phase 1 build — DEC-017. (This
  resolves UAT-1 below; kept in the UAT list only for its historical
  reasoning, not as an open item.)

**Ready for owner approval but not yet recorded as `[DECISION]`**
(`[DECISION MODE: ANALYSIS]`, recommendation given, no further
comparison/testing needed to decide — these are implementation *details*
within the already-approved Phase 1 scope above, not yet individually
ratified):
- Provider/domain reuse classifications (§1) and target module map (§3).
- File upload/storage flow and request lifecycle (§5, §6).
- API contract shape (§7) and response-size discipline (§8).
- Error model and taxonomy (§9).
- COMTRADE upload transport mechanism — single multipart request (§10) —
  now fully approved together with the frontend pairing UX itself (DEC-017).
- Source identity scheme (§11).
- Record-aliasing avoidance approach — no cross-request caching (§12).
- Full-resolution data ownership — the stored original file (§13).
- Testing strategy and numerical-equivalence definition (§18, §19).
- Exact first implementation scope, acceptance criteria, implementation
  order, and rollback strategy.

**Needs comparison** (`[DECISION MODE: COMPARISON]`):
- Discovery Open Question #5 (persistence model) — deferred to Phase 8,
  not needed now. **The long-term persistence architecture remains
  explicitly `[OPEN]`** — DEC-013's JSON-sidecar approval does not resolve
  this.
- Discovery Open Question #6 (calculated-signal grammar expansion) —
  deferred to Phase 6.

**Recommended for UAT** (`[DECISION MODE: UAT]` — explicitly **not**
decided):
- ~~UAT-1: COMTRADE pairing interaction~~ — **resolved**, see DEC-017 above.
- UAT-2: error message wording/specificity.
- UAT-3 (far future): calculated-signal grammar expansion, carried forward
  from discovery Open Question #6.

**Deferred** (`[DECISION MODE: DEFER]`, explicitly not needed for this
phase):
- Duplicate-upload/content-hash deduplication (§5).
- Workspace lifecycle management (§4).
- Background job/cancellation infrastructure for large files (§5).
- Engineering-improvement findings — kept separate from migration scope,
  status unchanged by Phase 1 approval: COMTRADE discontinuity/gap
  detection, raw timestamp traceability, timing-mode enforcement in the
  general offset API, duplicate CSV/Excel classifiers, calculated-signal
  grammar expansion, frequency/ROCOF computation, the suggestions feature —
  discovery Open Questions #1 (Phase 4), #2, #3 (mitigated by write-once
  storage, revisit only if requested), #4, #6 (Phase 6), #7 (Phase 7), #8
  (no committed timeline), #9 (authentication timing — Phase 9,
  architecture already prepared for it per §20/§21).
