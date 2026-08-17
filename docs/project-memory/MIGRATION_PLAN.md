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

## Phase 2C — Flexible Multi-Channel Waveform Workspace: Discovery and Design (2026-08-15)

`[PROPOSAL]` throughout except where explicitly marked `[FACT]` (verified code
evidence) or `[DECISION]` (none newly recorded by this pass — all of Phase 2C's
UX/architecture questions remain open, per this task's explicit instruction).
**This section is discovery and design only — no Phase 2C code, no multi-channel
API, no drag/drop, no digital signals, no cursors were implemented this pass.**
Phase 2B is complete (DEC-022: Plotly.js selected). Phase 2C has **not** started.

### 1. Goal and core principle

Design (not build) the first flexible multi-channel waveform workspace: select
several analog channels → display together on one synchronized time axis →
rearrange freely (vertical layout) while staying synchronized (horizontal time).
Owner's own framing, carried verbatim as the organizing principle for this whole
section:

```text
VERTICAL:                          HORIZONTAL:
flexible                           shared
user-arrangeable                   synchronized
reorderable                        common X/time viewport
groupable
```

This is a direct, natural extension of **DEC-021** (already approved,
2026-08-15): waveform navigation is workspace-level, never channel-level; a
centralized toolbar, never one native modebar per channel. Phase 2C's entire
job is to design the *vertical* half of the model DEC-021 didn't need to
specify yet, without ever weakening the *horizontal* half it already settled.

---

### 2. Existing `powerwave` findings — multi-channel/panel behavior

Re-verified this session directly against `powerwave` HEAD `3156392`
(unchanged — confirmed via `git -C powerwave log -1`, same commit the Phase 2
discovery/design pass already used), via live import/call-graph tracing, not
documentation.

`[FACT]`, live-code evidence, with file:line references:

- **Panel/subplot model**: no hard cap on channels per panel — any number of
  channels can be assigned to one `SessionPanel`/`SessionCanvasWidget` (one
  `pg.PlotItem`) via `panel.channel_refs`
  (`app/sessions/event_session.py:707-718`). Multiple channels sharing a
  panel share one `ViewBox`, grouped by unit (see Y-axis finding below).
- **`powerwave` already has live channel↔panel drag-and-drop** — a genuinely
  new finding this pass, not previously recorded. A channel's legend row
  (`app/ui/session/legend_widget.py:257-289`) can be dragged and dropped onto
  another panel's header (`app/visualization/widgets/session_canvas.py:163-181`),
  wired through to `session.set_channel_panel(...)`
  (`session_canvas_controller.py:563-575`). A sidebar combo box per channel
  row offers the same move, plus a `"+ New panel…"` sentinel
  (`app/ui/session/channel_tree_widget.py:186-233`). A right-click panel menu
  additionally offers **"Merge with →" / "Split by source" / "Split by
  type"** (`session_canvas.py:653-703`, `session_canvas_controller.py:581-654`)
  — all confirmed **live** (wired in `main_window.py`).
- **No panel reordering exists anywhere** — confirmed by both grep and
  direct inspection: `session.list_panels()` returns plain dict-insertion
  order (`event_session.py:707`), `add_panel()` always appends
  (`event_session.py:710`); there is no `move_panel_up`/reorder-panels API
  in the entire repository. **No within-panel channel reordering** either —
  legend rows render in the order channels were assigned, no drag-reorder or
  up/down control. This is the single biggest gap between `powerwave`'s own
  proven UX and the owner's explicit Phase 2C requirement ("owner explicitly
  wants waveform channels not fixed in one location") — `powerwave` solved
  "move a channel to a different panel" years ago, but never solved
  "reorder the panels themselves."
- **A real, previously-unflagged dead-code bug**: the legend's own
  right-click **"Move to panel…" menu item is wired on the UI side but its
  signal (`move_to_panel_requested`) is connected nowhere** — confirmed by
  grepping every connection site in `session_canvas_controller.py`'s
  `_wire_canvas` (`lines 1729-1780`, which wires six sibling signals but not
  this one). Clicking it is a silent no-op. Worth citing as evidence for why
  a fresh, correctly-wired Oruxa implementation is preferable to porting this
  particular mechanism as-is.
- **Panel resizing**: live, via a standard Qt `QSplitter` drag handle
  (`session_canvas_controller.py:246`, default behavior, not custom-built).
  **Confirmed weakness, not worth reusing**: `rebuild_layout()` constructs a
  **brand-new** `QSplitter` on every structural change — including an
  ordinary channel-panel move — so any manually-dragged panel height is
  silently discarded and reset to a fixed heuristic (`_resize_digital_panels()`,
  `session_canvas_controller.py:951-984`: digital panels
  `min(n_rows*30+65, 220)`px, analog panels a flat `250`px) every time. The
  method's own docstring implicitly concedes this ("the user can still drag
  splitter handles freely **after** this initial sizing").
- **Y-axis behavior — a significant, previously-unrecorded finding**:
  autoscale is **always on**, computed from **all of a `ViewBox`'s curve
  data across the full session window** (`SessionCanvasWidget._refresh_y_ranges()`,
  `session_canvas.py:810-836` — matches the earlier finding that `powerwave`
  doesn't re-decimate/re-view on zoom either), **not** viewport-aware. More
  importantly: **shared-scale-by-engineering-unit is a live, always-on,
  non-toggleable structural mechanism** — `axis_group_for_signal()`
  (`app/visualization/axis_management.py:91-131`) groups same-unit channels
  onto one shared `ViewBox`/axis at both live call sites
  (`session_canvas_controller.py:891`, `session_canvas.py:803`), hardcoded to
  `AxisDisplayMode.SHARED`. The alternative `DEDICATED` (one axis per
  channel) mode exists in the same function but is **only reachable from
  confirmed-dead code** (`visualization_manager.py`, `flexible_plot_canvas.py`).
  In other words: `powerwave` already behaves like Detego's "Proportional"
  mode **permanently, with no "Fit" equivalent ever exposed to the user** —
  the reverse of what §19 below initially proposes as Oruxa's own default.
  This tension is addressed directly in §19.
- **Legend / channel identity**: a real, always-visible per-panel legend
  strip (`ChannelLegendWidget`, `app/ui/session/legend_widget.py:379-673`,
  a scrollable list of rows below each panel — colour swatch, display name,
  source badge, unit), not hover-only. A separate hover-crosshair readout
  also exists, additively.
- **Trace show/hide without closing the session**: multiple live mechanisms
  (sidebar checkbox, legend right-click "Hide," Ctrl-click batch hide) all
  correctly leave the session/panel intact — worth preserving the *concept*
  (§21).
- **Digital/analog panel separation — a real, unguarded gap**: default
  routing puts digital channels in their own panel, but **nothing in the
  code prevents a user from dragging a digital channel into an analog panel**
  (or vice versa) via the same live drag mechanism above. When that happens,
  `update_digital_curve()` draws the digital hi/lo segments onto the
  **same** `ViewBox` used for left-axis analog curves
  (`session_canvas.py:1000-1057`), and the digital row-offset values
  participate in the same shared-autoscale computation as real analog
  physical values — the digital-only special-casing (fixed `-0.5..n-0.5`
  Y-range, autorange disabled) only activates when *every* channel in the
  panel is digital (`session_canvas_controller.py:912-933`); a mixed panel
  silently produces a broken, uninterpretable shared scale. This is direct,
  concrete evidence supporting §25's recommendation to keep digital and
  analog structurally separate in Oruxa's own panel model, not just a
  cautious default.

**Behavior worth preserving vs. desktop implementation not to reuse**,
specific to Phase 2C's own concerns (extending the equivalent table from the
original Phase 2 discovery/design pass, not repeating it):

| Behavior worth preserving | Desktop implementation (do not reuse) | Oruxa web-native target |
|---|---|---|
| Channels can be moved between panels via direct manipulation | Qt `QDrag`/MIME-type drag, a sidebar combo box, and a separate merge/split context menu — three overlapping mechanisms for one concept | One HTML5 drag mechanism (§10/§11), not three redundant ones |
| Panels can be resized by the user | `QSplitter` native handles, but sizes silently discarded on every structural rebuild (a confirmed bug) | Persist explicit panel heights in Oruxa's own state model (§27) across every re-render, not just until the next structural change |
| Same-unit channels can share one Y scale for direct comparison | Always-on, non-toggleable — no "independent/Fit" mode ever reachable live | Offer both, viewport-aware Fit as the default (§19) — an explicit, deliberate improvement over `powerwave`'s own stale, full-session-window autoscale |
| A visible, per-panel legend for channel identity | Custom `QScrollArea`+`_LegendRow` widget stack | Reuse Phase 1's already-shipped sidebar instead of building a second, duplicate legend widget (§21) |
| Digital and analog channels are routed to separate panels by default | No structural guard against mixing them — a real, confirmed rendering bug when a user does | Keep digital and analog as structurally distinct panel *types* in Oruxa's own model (§25), not just a soft default |

---

### 3. Detego benchmark findings

Gathered from Detego's own public marketing page (`detego.app`) and its public
documentation page (`detego.app/docs/guide/waveform-viewer`) — publicly
observable behavior only, per this task's instruction; no proprietary code or
assets were inspected or reverse-engineered.

`[FACT]`, from Detego's public docs, classified per this task's §6 scheme:

- **Channel list sidebar** — three collapsible sections (Analog/Digital/
  Computed), per-section count badge, per-channel visibility toggle, bulk
  show/hide-all. **[USEFUL BENCHMARK]** — closely matches Phase 1's
  already-shipped collapsible Analog/Digital grouping; extending it with
  visibility toggles (rather than building a separate legend) is a natural fit.
- **Grouping modes**: *Separate subplots* (no overlay), *Group by type*
  (auto-detects voltage/current and overlays related channels, e.g. Ia/Ib/Ic),
  *Custom groups* (a dedicated editor dialog; saved per-recording). **[USEFUL
  BENCHMARK]** for the three-mode concept itself; **[ORUXA SHOULD DO BETTER]**
  for the *mechanism* — a modal "custom groups editor" duplicates what direct
  drag-and-drop already gives Oruxa for free once panels are draggable (see
  §13) — a second, separate grouping UI would be redundant complexity Detego
  needs (no drag/reorder is documented) but Oruxa does not.
- **Panel resize**: per-channel drag dividers, plus toolbar-level
  increase/decrease/reset-height buttons; a draggable analog/digital split
  divider. **[USEFUL BENCHMARK]** for the toolbar-level global controls
  (simple to build first); the per-panel divider is a reasonable **[NEEDS
  UAT]** refinement once the coarser global control is validated.
- **Y-axis scaling**: exactly two modes, "Fit" (each channel scaled to its own
  space) and "Proportional" (same-unit channels share one scale). **[USEFUL
  BENCHMARK]** — directly reusable naming and concept; see §22.
- **Toolbar**: five groups separated by dividers — Navigation (zoom/pan/reset),
  Measurement (A/B cursors, hover mode), Channel display (height, Y-scale),
  Export (report/COMTRADE export), Annotate. **[USEFUL BENCHMARK]** for the
  *grouping-by-concern* structure; **[NOT NEEDED]** for Phase 2C specifically —
  Measurement/Export/Annotate are Phase 5+/out of scope here (§28 of this doc).
- **Cursors**: single hover cursor (click to place, sidebar shows readouts at
  that time) plus dual A/B measurement cursors with Δt and a t₀
  time-reference re-basing feature. Both snap to the nearest recorded sample,
  never interpolate. **[USEFUL BENCHMARK]**, explicitly **[NOT NEEDED]** for
  Phase 2C's own scope (cursors are Phase 5) — but the sample-snapping
  principle already matches Oruxa's existing Plotly `spikesnap: "data"`
  configuration (DEC-022), so no future rework is implied.
- **Legend**: no separate legend panel is documented — channel identity comes
  from the sidebar's phase-colored dots plus a group-hover tooltip showing
  every visible channel's value at that time. **[USEFUL BENCHMARK]** — directly
  informs §23's recommendation to avoid building a second, separate legend UI.
- **Drag-and-drop channel/panel reordering**: **not documented anywhere** in
  Detego's own public guide. **[ORUXA SHOULD DO BETTER]** — this is exactly
  the capability the owner has explicitly asked for (§13) that Detego itself
  does not appear to offer; per DEC-020/PRODUCT_REFERENCES.md's own explicit
  rule ("if Detego lacks a capability required by the owner, do not omit or
  weaken it merely to stay consistent with Detego"), this is not a reason to
  skip it — it is a specific, named opportunity for Oruxa to exceed the
  benchmark.
- **Rendering library**: Detego's own marketing copy states its charts are
  "driven by interactive Plotly.js" — `[FACT]`, noted for completeness only.
  **This is explicitly not evidence for, or repetition of, DEC-022** — Plotly
  was selected in Phase 2B purely from the owner's own hands-on UAT
  (DEC-022's Reason section), before this Detego docs page was even
  consulted for Phase 2C. Recorded here only so a future reader doesn't
  mistake the coincidence for a justification neither decision actually used.

`[OPEN]` No further Detego audit (its actual client-side code, exact visual
styling, or authenticated-app-only behavior) was performed — this reflects
only what its own public marketing/docs pages state, per governance.

---

### 4. Proposed Oruxa workspace model — core interaction model

```text
                    Central Powerwave Toolbar
              (Reset Time View · Autoscale Y · Add channels · Reset Layout)
                              |
                    one shared X/time viewport   <- DEC-021, unchanged
                              |
        +---------------------------------------------+
        |  Panel: Voltage        [drag grip] [–] [x]   |   <- reorderable,
        |    VA  VB  VC  (own Y axis)                  |      resizable,
        +---------------------------------------------+      collapsible
        |  Panel: Current        [drag grip] [–] [x]   |
        |    IA  IB  IC  (own Y axis)                  |
        +---------------------------------------------+
        |  Panel: Frequency      [drag grip] [–] [x]   |
        |    F   (own Y axis)                          |
        +---------------------------------------------+
```

A **panel** (§10) is the unit of vertical flexibility: it owns its own Y axis
and its own set of traces, but never its own X axis or its own native
modebar — those stay workspace-level (DEC-021). Automatic grouping (by
`engineering_type`, already backend-computed, never re-derived — Phase 1)
produces a sensible *default* panel layout the moment channels are added, but
every panel is then freely reorderable, and every channel is freely
movable between panels, via drag — **the automatic placement is a starting
point, never a constraint** (a direct requirement from §9 of the task).

---

### 5. Channel-add workflow — comparison and recommendation

`[DECISION MODE: ANALYSIS]` — leaning strongly on evidence already gathered
during the original Phase 2 discovery/design pass (§8 there), which reached
the same conclusion independently: this doesn't need a fresh UAT before a
confident recommendation, though the *feel* of the final implementation is
worth a quick sanity check once built (folded into the first slice's own
dev-verification, not a separate formal trial).

| Option | Discoverability | Speed selecting many | Clutter | Fits future drag/drop | Verdict |
|---|---|---|---|---|---|
| A. Checkbox + "Add to workspace" button | High — checkboxes are a familiar, self-explanatory affordance | Fast — select N, click once | Low — one button, appears only once ≥1 selected | Yes — selected rows can later also support drag as an *additional*, not exclusive, path | **Recommended** |
| B. Direct click (click a row = added) | Low — no visible "selected" state before commit; easy to misclick | Slow for many — one added source-of-truth per click, no batching | Low | Poor — no natural drag handle | Rejected |
| C. Per-channel "Add" button (mirrors existing "Remove" pattern) | High | Slow for many — N separate clicks, no batch | Higher — a button per row, always visible | Fine, orthogonal | Reasonable fallback, not first choice |
| D. Drag channel row into workspace | Low without prior exposure; discoverable only after first use | Slow for many (one drag per channel) unless combined with multi-select-then-drag (added complexity) | Low | N/A — this *is* the drag mechanism | Rejected as the *primary* mechanism (see reasoning) |
| E. Multi-select + add | Same as A, described from the multi-select angle | Same as A | Same as A | Same as A | Same recommendation as A — A already *is* this option |

**Recommendation**: **Option A** — a checkbox per channel row (added to Phase
1's already-shipped, already-UAT'd collapsible/searchable channel table) plus
one "Add N selected to workspace" button that appears once ≥1 channel is
checked. This directly extends an interaction model the owner has already
approved (DEC-017's underlying UAT: simple, understandable, comfortable) and
requires no new interaction language to learn. Drag-to-add (Option D) is
**not recommended** as the primary channel-add path — the same reasoning the
original Phase 2 discovery pass already gave (no evidence it serves this
engineering-focused, keyboard/mouse-basic audience better, and it adds real
implementation complexity for what checkbox-select already does simply) still
holds and is reaffirmed here. Drag *within* the workspace (reordering panels,
moving channels between panels) is a completely different, and much more
valuable, use of drag — see §13 — and should not be conflated with "getting a
channel into the workspace in the first place."

---

### 6. Initial default layout — comparison and recommendation

`[DECISION MODE: ANALYSIS]`:

| Option | Behavior | Assessment |
|---|---|---|
| A. One channel per panel | Every selected channel gets its own panel | Simplest to reason about, but defeats the entire point of grouped-phase comparison (VA/VB/VC) that engineers actually want by default |
| B. Auto-group by engineering type | Voltage together, Current together, etc. — already Phase 1's backend-computed `engineering_type` | **Recommended** — matches `powerwave`'s own default-panel intent (§2), matches Detego's own "Group by type" default, requires zero new classification logic |
| C. Auto-group by source/phase family | Group by detected phase (A/B/C) across engineering types | More sophisticated, but riskier — would require inferring phase *relationships* across types, a stronger claim than the existing conservative classifier makes; not justified for a first slice |
| D. All selected channels in one plot | Single panel, everything overlaid | Rejected outright — mixes incompatible units by default (V and A superimposed) with no engineering justification |
| E. Smart heuristic (beyond type) | E.g. combine B + C + naming similarity | Speculative complexity beyond what evidence supports; `_infer_panel_for_channel()`'s own third tier (name-keyword matching) was already deliberately *dropped* when Phase 1's classifier was built, favoring `Undefined` over a guess — repeating that mistake here would contradict an already-established project convention |
| F. Ask the user every time | A modal/dialog on every add | Rejected — adds friction to the single most common action (adding channels) for a decision the automatic default already gets right most of the time |

**Recommendation**: **Option B**, exactly as already recorded in the original
Phase 2 discovery/design pass (§9) — one panel per `engineering_type` actually
selected, stacked vertically. The critical addition Phase 2C's design makes
explicit: **this placement is provisional, never load-bearing** — §13's drag
model lets the user immediately move any channel to any panel, so a
misclassified or unwanted grouping costs one drag, not a dead end. This
directly satisfies the task's own explicit requirement (§9): *"initial
automatic placement must never permanently constrain the user."* Uncertain
classifications land in the existing `Undefined` panel (same conservative
principle already established for the channel classifier itself — never guess).

---

### 7. Panel concept — assessment

**Panel = one visual waveform region, with one shared X/time axis (inherited
from the workspace-level viewport, DEC-021), containing one or more traces,
with its own independent Y axis.**

This is the right abstraction — confirmed by evidence from all three
reference points:

- **`powerwave`**: `_infer_panel_for_channel()` already routes multiple
  channels into one shared panel by default (voltage, current, power,
  frequency, digital, other) — the same "one region, several traces, shared
  X" shape, just without a user-facing reorder mechanism (§2).
- **Detego**: "Group by type... overlays related ones" is the identical
  concept under a different name.
- **DEC-021**: already establishes the shared-X/independent-Y split at the
  *workspace* level; a panel is simply the *unit* that owns one of those
  independent Y axes.

Do not overgeneralize the panel abstraction beyond what's needed now: a panel
holds **analog channels only** for Phase 2C's own scope (§28 — digital is a
future panel *type*, not a Phase 2C concern); mixed units within one panel is
addressed directly, not left implicit (§23).

---

### 8. One channel per panel vs. grouped channels — recommendation

`[DECISION MODE: ANALYSIS]`, resolved by the same evidence as §6:

| | One-per-panel | Grouped (auto by type) |
|---|---|---|
| Scale clarity | Best — no shared-axis compromise | Good when units match; needs care when they don't (§23) |
| Vertical space | Poor at scale — 12 channels = 12 panels = a very long page | Good — a handful of panels for the same 12 channels |
| Phase comparison (VA/VB/VC) | Requires manual cross-panel visual alignment | Native — same Y axis, same panel, directly comparable |
| Compactness | Poor | Good |

**Recommendation**: **grouped-by-type as the default (§6), with one-channel
panels available on demand via drag** (dragging a channel out of a group
panel into empty space creates its own single-channel panel — §13's "split"
behavior). This gives every engineer both modes without forcing a
project-wide choice: compact-by-default for the common phase-comparison case,
one-per-panel available in one drag whenever a specific channel needs
undivided attention.

---

### 9. Grouping behavior — modes

Adopting Detego's three-mode *concept* (§3), with an Oruxa-specific mechanism
for the third mode:

- **Separate** — every channel gets its own panel (§6 Option A), available as
  an explicit workspace-level toggle for a user who wants maximum clarity
  over compactness.
- **Automatic** — group by `engineering_type` (§6 Option B, the default).
- **Custom** — **not** a separate modal editor (Detego's own mechanism,
  **[ORUXA SHOULD DO BETTER]** per §3) — Oruxa's "custom" state is simply
  *whatever the user has manually rearranged via drag* (§13). No dedicated
  "custom groups" UI needs to be built at all; dragging *is* the custom-group
  editor, which is both simpler to build and more directly manipulable than a
  separate dialog.

Automatic grouping rules, explicitly conservative (matching the owner's
already-established preference — see the existing `channel_classification.py`
`Undefined`-over-guessing principle, carried over verbatim into this design):
group by **`engineering_type` only**. Do **not** silently infer phase-family
or source relationships beyond what the already-shipped classifier states.
An ungroupable/`Undefined` channel gets its own panel (or an "Undefined"
panel if more than one exists) rather than a guessed placement.

---

### 10. Drag/reorder design

`[FACT]` directly informs this section: `powerwave` already has a live,
proven channel-to-panel drag mechanism (§2) — but **no panel-reordering
mechanism at all**, confirmed absent by both grep and direct inspection.
Detego's own public docs (§3) document neither. **This makes panel
reordering itself the single clearest opportunity for Oruxa to exceed both
references at once**, not merely match one of them — `powerwave` proves
channel-to-panel movement is a real, validated engineering need (its users
have had this for years), while panel-level reordering has apparently never
been built in either reference product.

Assessing the task's own six candidate behaviors:

| # | Behavior | First-slice? | Reasoning |
|---|---|---|---|
| 1 | Reorder whole panels | **Yes** | Cheapest, safest — pure DOM/array reordering, no cross-panel state migration; proves the drag mechanism itself in isolation |
| 2 | Reorder channels within a panel | Defer | Low value until multi-trace-per-panel legend ordering is an actual, observed complaint |
| 3 | Move a channel from one panel to another | **Yes, same slice as split/create** | This *is* the "vertical flexibility" the owner explicitly asked for — the single most important drag behavior in this whole list |
| 4 | Create a new panel by dragging into empty space | **Yes, same slice as #3** | Natural counterpart of #3 — moving a channel "out" has to go *somewhere*; empty space is the simplest valid target |
| 5 | Merge panels | Defer | Lower-priority edge case; achievable manually today by dragging every channel from one panel into another one at a time |
| 6 | Split a channel into its own panel | Covered by #3+#4 together | Dragging a channel out of a multi-channel panel onto empty space already produces exactly this outcome — no separate mechanism needed |

**Recommendation**: implement **#1 (reorder panels)** and **#3+#4 (move/split
channels)** together as Phase 2C's drag slice (§28 — 2C-B); defer #2 and #5,
which are refinements achievable indirectly (or not yet requested) rather
than blocking capabilities.

---

### 11. Drag interaction safety

Direct manipulation must never fight the chart's own zoom/pan drag gesture
(Plotly's `dragmode: "zoom"`, already in use — DEC-022). Design:

- **Drag handle only, never the chart canvas** — a small, explicit grip icon
  (⋮⋮) on each panel's header and on each channel's legend-row entry (§23) is
  the only draggable surface. The waveform trace area itself remains 100%
  reserved for Plotly's own zoom/pan/hover, exactly as today.
- **Drop indicators** — a visible insertion line (between panels) or a
  highlighted target-panel border (when dropping a channel onto an existing
  panel) during drag, so the outcome is always visible before release, never
  a surprise after the fact.
- **Reversibility over confirmation dialogs** — a misplaced drag is
  trivially undone by dragging it back (state is just an ordered array —
  moving something back is symmetric with moving it away); no modal
  confirmation is needed for every drag (that would violate this design's own
  "smooth, not overloaded" principle, §26), but see §31 for the one
  workspace-level safety net (**Reset Layout**).
- **Accidental-movement prevention** — a small drag-start threshold (a few
  pixels of movement before a drag is recognized as a drag rather than a
  click) is a standard, low-cost safeguard against a slightly-off click being
  misread as a reorder attempt.

---

### 12. Panel resizing

- **First slice**: **global height controls only** — toolbar-level
  "Decrease/Increase/Reset heights" (directly reusing Detego's own observed
  pattern, §3 — a genuinely useful, low-cost benchmark idea), applied to
  every panel at once. Simple to build, no per-panel state to persist yet.
- **`[DECISION MODE: NEEDS UAT]` refinement, not first slice**: per-panel
  drag dividers (Detego also has this, as a finer-grained option layered on
  top of its global controls, not a replacement for them; `powerwave` also
  has this, via its native `QSplitter` handles, §2) — worth adding once
  the coarser global control is in front of the owner and a real opinion can
  form about whether individual panels actually need independent heights in
  practice.
- **A specific pitfall to avoid, directly evidenced by `powerwave`'s own
  confirmed bug (§2)**: whatever panel-height mechanism ships must persist
  explicit heights in Oruxa's own state model (§27) across every re-render —
  `powerwave`'s `QSplitter` resize is a live, working *interaction*, but its
  *result* is silently discarded on the next structural rebuild (a new
  `QSplitter` is constructed from scratch on every channel-panel move).
  Oruxa's array-based state model (§27) should store `height` per panel
  entry explicitly, so a reorder/move elsewhere in the workspace never
  resets a size the user deliberately set.
- Scope: **global** control ships first; **per-panel** is a later, evidence-
  gated addition; nothing here is deferred to "never."

---

### 13. Centralized waveform toolbar — recommended Phase 2C minimum

Per the task's own explicit instruction not to pack every future control into
Phase 2C, and DEC-021's already-approved requirement that this toolbar (not
per-panel modebars) is the *only* place these controls live:

**Recommended Phase 2C minimum**:

```text
[ Reset Time View ]  [ Autoscale Y ]     [ + Add channels ]  [ Reset Layout ]
        Navigation         Y/display          Workspace
```

- **Reset Time View** — restores the full-record X range across every panel
  at once (DEC-021, unchanged terminology).
- **Autoscale Y** — recomputes each panel's Y range from its own currently
  visible data (§22); kept as its own, separate button from Reset Time View,
  per DEC-021's explicit requirement never to collapse the two.
- **Add channels** — opens/returns focus to the channel browser (§5); the
  workspace-level equivalent of what today is a per-channel link.
- **Reset Layout** — discards manual panel/channel rearrangement and
  recomputes the automatic grouping fresh (§9's Automatic mode) — the
  reversibility safety net referenced in §11/§31.

Zoom/Pan/Zoom In/Zoom Out are **not** separate toolbar buttons in this
minimum — they're already native drag/scroll interactions on the chart
canvas itself (unchanged from Phase 2B), consistent with keeping the toolbar
itself minimal (§26). Layout/grouping-mode picker (Separate/Automatic), a
finer channel-height control, and Y-scale-mode toggle (§22) are explicitly
**deferred to a later Phase 2C slice** (§28's 2C-D), once the core
interaction model above is validated. Export, cursor, A/B cursor, t0, and
annotation controls are explicitly **out of scope** for Phase 2C entirely
(Phase 5+).

---

### 14. Plotly native modebar transition — recommendation

`[DECISION MODE: ANALYSIS]` — evidence-grounded, directly reusing an
already-shipped, already-tested Phase 2B mechanism rather than inventing a
new one:

Assessing the task's own options:

- **A. One hidden/shared Plotly control chart + custom toolbar** — rejected;
  an extra, purely-synthetic Plotly instance with no visible data adds
  complexity for no benefit once Option B (below) already solves the same
  problem directly.
- **B. Call Plotly APIs directly from the Powerwave toolbar** —
  **recommended** (full reasoning in §17/18 below).
- **C. Retain one modebar on an overall parent plot** — rejected; this is
  exactly the "one figure with subplots" architecture (§18's Option A), and
  inherits its drag/reorder/resize costs (below) without a compensating
  benefit specific to the modebar question.
- **D. Another approach** — none identified with a clear advantage over B.

**Recommendation**: **Option B**. Every panel's own Plotly instance has its
native modebar explicitly disabled (`config.displayModeBar: false` — a
one-line change from Phase 2B's current `modeBarButtonsToRemove` approach),
and the centralized Powerwave toolbar's buttons call the exact same Plotly
API functions (`Plotly.relayout`, already used by today's `setViewport`)
against **every currently-displayed panel's Plotly instance**, not just one.
This is a direct, mechanical extension of code that already exists, is
already tested, and is already proven correct in Phase 2B — not a new
mechanism.

---

### 15. Shared X/time synchronization — architecture

This is the single most consequential Phase 2C architecture question. Full
comparison in §16.

---

### 16. One Plotly figure vs. multiple coordinated figures

`[DECISION MODE: ANALYSIS]` — this is a technical architecture question with
enough evidence (from Plotly's own documented API surface and Phase 2B's
already-proven, already-tested code) for a confident recommendation; it does
not need a hands-on UAT to resolve, unlike the *visual/interaction feel*
questions elsewhere in this document.

**Option A — one Plotly figure, several stacked subplots** (via
`layout.grid` / manually assigned `xaxis`/`yaxis` pairs with `matches: "x"`
for the shared axis):

- Shared X: free, native (`matches: "x"` propagates zoom/pan across subplots
  automatically).
- Independent Y: also native (each subplot keeps its own `yaxis`).
- Reorder a panel: **not a native Plotly primitive** — moving a subplot to a
  new vertical position means recomputing every subplot's `yaxis.domain`
  fraction and re-assigning every trace's axis references, then a full
  `Plotly.react` — effectively hand-building the same reorder logic Option B
  needs anyway, just against a harder API surface (domain-fraction math
  instead of DOM order).
- Move a channel between panels: same problem — no native "move this trace
  to a different subplot" operation; requires deleting and re-adding traces
  with new axis assignments while also touching the domain math above.
- Resize a panel: same domain-fraction recomputation across *every* subplot
  on every resize (they all share the available vertical space).
- Cost: one WebGL/canvas context total; marginally lower baseline memory.

**Option B — one independent Plotly figure (instance) per panel, each its own
`<div>`, coordinated by a thin Oruxa-owned shared-viewport layer**:

- Shared X: **not native**, but already built and tested — Phase 2B's
  `setViewport()`/`suppressNextRelayout` pattern already broadcasts one
  `(startTime, endTime)` to a Plotly instance without re-triggering its own
  relayout handler; extending this from "one instance" to "every displayed
  panel's instance" is a loop around already-proven code, not new
  architecture.
- Independent Y: trivial — separate figures have separate `yaxis` by
  construction, no domain math at all.
- Reorder a panel: **trivial** — panels are plain DOM nodes; reordering is a
  DOM operation (native browser drag-and-drop or a small reorder library),
  with zero interaction with any chart's internal state.
- Move a channel between panels: **native Plotly API** —
  `Plotly.deleteTraces(sourceFigure, index)` +
  `Plotly.addTraces(targetFigure, trace)`, both well-documented, no
  domain/axis-fraction math involved.
- Resize a panel: resize its container `<div>`, call the built-in
  `Plotly.Plots.resize(container)` — cheap, native, per-panel only (no other
  panel is touched).
- Cost: N WebGL/canvas contexts (one per visible panel). For the realistic
  panel counts this design targets (a handful of panels, §32's "6-12
  visible traces" target), this is a well-established, unremarkable browser
  workload — not a documented Plotly.js concern at this scale.

**Recommendation**: **Option B.** Every one of Phase 2C's *hardest* stated
requirements — reorder panels, move channels between panels, create/split
panels, resize panels — is a native, well-documented Plotly API operation
under Option B and a hand-built, domain-fraction-math problem under Option A.
Option A's only genuine advantage (native shared-X) is **already achieved**
under Option B by extending Phase 2B's own proven broadcast mechanism, so
Option A buys nothing Phase 2C doesn't already have another good way to get,
while costing significantly more implementation complexity on exactly the
features the owner cares about most. This recommendation should be spot-
checked for interaction feel during the first implementation slice's own
development (does synchronized relayout broadcast across N instances feel
smooth?) — not gated behind a separate formal UAT, since the underlying
mechanism is already proven, only its *fan-out* is new.

---

### 17. Multi-channel backend request strategy

`[DECISION MODE: ANALYSIS]`:

`[FACT]` — verified directly against `backend/app/api/v1/sources.py` and
`backend/app/services/waveform_service.py` this session: the current Phase 2A
endpoint (`GET .../sources/{source_id}/waveform`) takes exactly **one**
`channel_name` per request; there is no multi-channel request shape today.

Assessing the task's own options, given DEC-021's guarantee that every
displayed channel always shares the identical `(start_time, end_time,
point_budget)`:

- **A. One HTTP request per channel** (today's shape, fanned out N times
  client-side) — works with **zero backend change**; Phase 2B's coordinator
  pattern already proves the per-request mechanics. Cost: N connections, N
  JSON envelopes (repeated `source_id`, error-shape boilerplate, etc.) for
  every single viewport change, growing linearly with displayed-channel
  count.
- **B. A bounded multi-channel waveform endpoint** — one request carrying a
  repeated `channel_name` parameter (matching the original Phase 2 design's
  own §20 sketch, which already anticipated this before Phase 2A's first
  slice deliberately narrowed to one channel), same `start_time`/`end_time`/
  `point_budget` applied to all, returning a list of per-channel results.
  Backend cost: **none new** — the route handler simply calls the existing,
  already-tested `extract_waveform_range()` once per requested channel
  server-side and packs the results into one response list; no change to the
  extraction/reduction logic itself.
- **C. Batch requests per panel** — rejected as an unnecessary middle tier:
  since every panel already shares the *same* workspace-level range (DEC-021),
  batching at the panel level buys nothing over batching at the
  whole-workspace level (Option B), which is simpler.
- **D. A request coordinator with concurrency limits** — a valid *client-side*
  pattern regardless of A vs. B, but doesn't answer *how the backend serves
  multiple channels*; if B is adopted, there's no fan-out left to limit
  (one request = one response for the whole viewport).
- **E. Another approach** — none identified with a clear advantage.

**Recommendation**: **Option B**, added as its own small, additive backend
slice (§28 — optional 2C-C) once real multi-panel usage (from the first
frontend slice, built against Option A with zero backend change) shows the
N-separate-requests overhead is actually felt — not a hard prerequisite for
Phase 2C's *first* slice. The existing single-channel endpoint remains
unchanged and continues to serve `waveform-prototype.html`'s single-channel
preview page unaffected.

---

### 18. Point-budget semantics with many panels

Every panel shares the same horizontal container width (they're stacked
vertically, not side-by-side), so **panel *count* does not, by itself,
demand a smaller point budget per channel** — each panel's X axis still
spans the same pixel width regardless of how many other panels exist above
or below it. The actual lever on total payload is **per-channel payload
size**, which the existing `point_budget` mechanism (already fixed at a
sensible default, §Phase 2A's `DEFAULT_POINT_BUDGET = 4000`) already bounds
correctly, independent of channel count.

**Recommendation**: keep `point_budget` tied to a bound derived from the
shared panel's rendered pixel width (already an established target — "payorad
should scale with pixel width, not full record size," carried forward from
the original Phase 2 design's §26/this task's own §44) — **not** divided
further by however many channels or panels happen to be open. A dozen
channels at the existing ~4000-point ceiling each is a few hundred KB total
JSON, comfortably within the performance targets already established; this
should be confirmed, not assumed, by the existing open benchmark action item
(§Phase 2 design's §28) once real multi-channel payloads exist to measure —
Phase 2C's design does not need to pre-solve this by inventing a new formula
today.

---

### 19. Shared X but independent Y — Y-axis scaling model

`[DECISION MODE: ANALYSIS]` for the first-slice default (already reasoned in
the original Phase 2 discovery pass, §10, reaffirmed here), `[DECISION MODE:
NEEDS UAT]` for the Fit/Proportional toggle:

| Option | First-slice default? | Reasoning |
|---|---|---|
| A. Per-panel autoscale to the panel's *entire* record | No | Defeats the purpose of zooming — a small excursion could stay visually flat against a Y range sized for the whole record |
| B. Per-panel autoscale to the *currently visible* (viewport) data | **Yes** | Matches the already-recorded ANALYSIS-mode recommendation; keeps zoom meaningful for both X and Y together |
| C. Whole-record autoscale | No | Same problem as A |
| D. Same-unit proportional/shared scaling (Detego's "Proportional") | Later, as a toggle | Genuinely useful for direct magnitude comparison across same-unit channels (e.g. comparing VA/VB/VC peak values) but its value is best judged once real multi-channel panels exist to react to — `[NEEDS UAT]` |
| E. Manually locked scale | Defer | No evidence of need yet; an edge case worth revisiting only if UAT surfaces a real request for it |

**A real tension surfaced by the `powerwave` investigation (§2), addressed
directly rather than glossed over**: `powerwave`'s own live behavior is the
*reverse* of this recommendation — its shared-scale-by-unit grouping
(Detego's "Proportional" concept) is **always on**, with no per-channel/
"Fit" mode ever reachable from live code, and its autoscale is computed from
the **entire session window**, not the live viewport. This recommendation
deliberately departs from `powerwave`'s own default, for a stated reason
consistent with DEC-020's "improve what's weak" principle (already applied
once this same way for decimation, DEC-019): `powerwave`'s always-shared,
never-viewport-aware Y behavior means a zoomed-in transient can still sit
against a Y range sized for the whole record's other channels — the exact
same "defeats the purpose of zooming" problem already identified and fixed
for the X axis (§Phase 2 design's §12). Shipping viewport-aware **Fit** as
Oruxa's own default is a specific, evidenced improvement over the existing
desktop app, not an arbitrary choice — while still offering **Proportional**
(matching both Detego's naming and `powerwave`'s own always-on default) as a
toggle once real feedback justifies it.

**Recommendation**: ship **B ("Fit," Detego's own naming is a reasonable,
reusable label, computed viewport-aware — an explicit improvement over
`powerwave`'s own stale, full-session-window autoscale) as the only mode in
the first slice**; add a **Fit ↔ Proportional** toggle (Detego's exact
two-mode naming, directly reusable; matches `powerwave`'s own always-on
behavior when set to Proportional) as a later, evidence-gated refinement
(§28 — 2C-D) once real multi-channel comparison feedback exists to judge it
by.

---

### 20. Mixed-unit grouping

The task's own worked example — "a current channel dragged into a voltage
panel" — makes the answer concrete, not abstract:

- **Automatic grouping never mixes units** (§9) — this stays a safe,
  conservative default.
- **Manual placement (drag) allows it** — this is a direct requirement of
  the owner's own stated flexibility goal (§9 of the task prompt gives this
  exact scenario). Prohibiting it outright would contradict the explicit
  worked example the owner supplied.
- **Readability is handled automatically, not left to the user**: when a
  second distinct unit appears in one panel (via drag), a second Y axis
  (Plotly's native `yaxis2`, right-side) is created automatically for it —
  the two traces get visually distinct scales without the user configuring
  anything. A subtle, dismissible panel-header note ("Mixed units — separate
  scales") keeps this visible without demanding a confirmation click on every
  drag (consistent with §11's "reversibility over confirmation dialogs"
  principle).
- **Cap at two distinct units per panel** — beyond that, a third/fourth axis
  starts crowding the panel edge with diminishing readability; recommend a
  soft nudge (an inline suggestion to split into another panel) rather than
  a hard block, keeping the flexibility principle intact while still steering
  toward readable defaults.

**Recommendation**: **allow, with automatic secondary-Y-axis creation**,
never a prohibition — this is `[DECISION MODE: ANALYSIS]`, directly resolved
by the owner's own worked example plus Plotly's native secondary-axis
support (no new mechanism needed).

---

### 21. Legend / channel identity

Directly informed by Detego's own observed minimalism (§3: "no separate
legend panel is documented... sidebar phase-colored dots plus tooltip"):

- **Full metadata (unit, phase, source) stays in the existing Phase 1
  sidebar** — already built, already searchable/collapsible/grouped, and now
  additionally reflects which channels are currently added to the workspace
  (a checked/highlighted state, extending §5's checkbox mechanism rather than
  building a second "what's displayed" list).
- **Panel header**: the grouping label only (e.g. "Voltage," or a
  user-renamed custom label once panels can be freely composed) — compact,
  never oversized (§26).
- **Per-trace legend row**: a colored dot + channel name only, directly under
  or beside the panel header — enough to distinguish VA from VB from VC at a
  glance, without repeating unit/phase/source already shown in the sidebar.
- **Hover tooltip**: full detail (name, exact time, exact value, unit) —
  already implemented via Plotly's `hovertemplate` (DEC-022, unchanged).

**Recommendation**: this three-tier split (sidebar = full metadata, panel
header/legend-row = compact identity, hover = full instantaneous detail)
avoids ever building a second, separate, competing legend UI — directly
matching Detego's own observed approach and reusing Phase 1's already-shipped
sidebar rather than duplicating it.

---

### 22. Colors

`[DECISION MODE: ANALYSIS]`, with one small `[DECISION MODE: COMPARISON]`
detail deferred to actual implementation time:

**Recommendation**: automatic, deterministic per-channel color assignment
(the same channel always renders in the same color within one workspace
session, regardless of panel membership or reorder), with **phase-aware
coloring applied automatically whenever a channel's `phase` metadata is known**
(Phase 1's already-shipped `phase` field on the analog channel model) —
falling back to a plain deterministic color cycle when phase is null/
`Undefined`. This is closer to an industry-standard convention (Detego's own
IEC/ANSI phase-color scheme, §3) than a stylistic preference, so it's treated
as `[ANALYSIS]`, not `[UAT]`. **The exact hex values / which convention (IEC
60446 vs. ANSI/IEEE)** is a small, low-risk detail worth a quick
`[COMPARISON]` at actual implementation time, not resolved here. User-editable
color is explicitly **deferred** — no evidence of need yet, not requested by
the owner.

---

### 23. Shared crosshair design — concept only

Not implemented this pass; concept only, to keep future compatibility clean
(§24):

- **Vertical time guide**: shared across every visible panel — hovering any
  one panel broadcasts the hovered time to every other panel's own Plotly
  instance (the same broadcast mechanism §16/§18 already builds for the
  shared X viewport, reused for a "current hover time" instead of "current
  visible range").
- **Value readout**: each panel shows its own trace's value(s) at that shared
  time (matches both Detego's own single-cursor sidebar readout and Oruxa's
  already-existing `spikesnap: "data"` sample-snapped hover, DEC-022,
  unchanged).
- **Horizontal guide**: stays **local** to the panel actually being hovered —
  broadcasting a horizontal (Y-value) guide line across panels with unrelated
  units/scales would be meaningless.

`[DECISION MODE: NEEDS UAT]` for the exact interaction feel once built; the
*architecture* above (reuse the same shared-viewport broadcast mechanism for
hover-time as for visible-range) is `[DECISION MODE: ANALYSIS]` and should be
treated as settled now, precisely so a future implementation doesn't invent a
second, parallel synchronization mechanism.

---

### 24. Future A/B cursors — architectural compatibility (not implemented)

Confirming, not building: the shared-viewport coordinator object recommended
throughout this section (owning "current shared X range" today, and "current
shared hover time" per §23 later) is generic enough that named A/B cursor
times (Phase 5+) are simply two more named instances of the same underlying
concept — a `cursorA: time | null`, `cursorB: time | null` pair alongside the
existing shared range/hover-time state, broadcast the same way. Nothing in
this section's panel/toolbar/synchronization design forecloses that; no
architecture needs to change later to accommodate it.

---

### 25. Digital waveform compatibility (not implemented)

`[DECISION MODE: DEFER]` — matching digital rendering's own existing deferred
status (Phase 2.x/2D, per the original Phase 2 discovery pass §14). Comparing
the task's own candidate designs:

- **Separate digital section, collapsible, below the analog panels** —
  **recommended direction** (not decided/implemented) — matches both
  `powerwave`'s own default panel list (which already includes a distinct
  "digital" panel, §2) and Detego's own sidebar (a distinct "Digital"
  section). The existing "panel = shared X + own Y + one or more traces"
  abstraction (§7) already accommodates this without modification — a digital
  panel simply holds step-rendered traces instead of continuous-line ones,
  with a boolean hi/lo range instead of an engineering-unit Y axis.
- **Mixed into individual analog panels** — not recommended; a boolean
  signal has no meaningful shared Y scale with an engineering-unit trace.
  **This is not a hypothetical concern** — the `powerwave` investigation
  (§2) found a confirmed, unguarded live-code gap where exactly this mixing
  is reachable (drag a digital channel into an analog panel) and produces a
  broken, uninterpretable shared autoscale, because the digital-only
  special-casing only activates when *every* channel in a panel is digital.
  Oruxa's own panel model should structurally prevent this outcome (e.g. a
  panel's declared trace-type governs what can be dropped into it) rather
  than leaving it silently reachable the way `powerwave` currently does.
- **Attached to analog groups** (e.g. a trip signal shown alongside the
  voltage panel it relates to) — an interesting future refinement, not
  decided now; nothing in the panel abstraction blocks it later (a panel
  *could* hold a digital-only trace type if a future UAT wants that).

No implementation, no API design commitment — this subsection exists only to
confirm Phase 2C's own panel model doesn't quietly foreclose a good digital
design later.

---

### 26. Source identity and multi-source future compatibility

Every panel's internal trace state should carry `source_id` alongside
`channel_name` (§27's state model) — trivial to include now, and directly
protects against Phase 3's multi-source future without redesigning the panel
model later, per this task's own explicit instruction. The backend API is
already scoped by `source_id` per request (Phase 1/2A, unchanged), so no API
change is implied by this. No hidden resampling or forced common-time-grid
assumption is introduced anywhere in this design (directly reaffirming the
already-established principle, MIGRATION_PLAN's Phase 2 design §21) — each
channel keeps its own native `time` array exactly as today.

---

### 27. Workspace state model

Lightweight, no new framework (the project's own established architecture
principle, `docs/architecture/oruxa-architecture.md` / AGENTS.md — "no
build step, no framework," reaffirmed for the frontend specifically):

```js
{
  panels: [
    {
      id,                     // stable client-generated id, survives reorder
      label,                  // "Voltage" (auto) or user-renamed (custom)
      channels: [
        { sourceId, channelName, unit, phase, color }
      ],
      height,                 // shared default unless overridden (§12)
      yScaleMode: "fit",      // "fit" | "proportional" (§19)
    },
    // ... order in this array IS the display order (drag-reorder = array
    // reorder, §13)
  ],
  sharedViewport: { startTime, endTime },  // drives every panel's X, DEC-021
  layoutMode: "automatic",    // "separate" | "automatic" | "custom" (§9;
                               // "custom" is simply "the user has dragged
                               // something," not a distinct stored mode)
  hoveredTime: null,          // future shared-crosshair anchor (§23), unused
                               // by Phase 2C's own first slices
}
```

No Redux, no global store library — this is a plain object owned by one
coordinator module (the direct, multi-panel-aware descendant of Phase 2B's
already-existing single-channel coordinator functions), matching the existing
`waveform-prototype.html`'s own established pattern of plain functions over a
shared `let` state, just widened from one channel to N panels.

---

### 28. Recommended Phase 2C implementation slices

`[PROPOSAL]`, sequenced by risk/dependency — **not** the exact 2C-A..2C-E
draft order the task itself offered as an example; re-derived from this
section's own evidence:

```text
2C-A — Channel-add UX + synchronized multi-panel display + minimal toolbar
  Checkbox-select channels from the existing Phase 1 browser (§5) -> "Add N
  selected" -> automatic engineering_type grouping into stacked panels
  (§6/§9), one independent Plotly instance per panel (§16's Option B),
  native per-instance modebars disabled, a minimal centralized toolbar
  (§13: Reset Time View + Autoscale Y only) driving every panel's Plotly
  instance via the extended broadcast mechanism (§16). Still N separate
  single-channel backend requests (§17 Option A) -- no backend change.
  NO drag/reorder, NO panel resize UI, NO grouping-mode picker, NO digital,
  NO cursors.

2C-B -- Drag/reorder + move-channel-between-panels + create/split panels
  The "vertical flexibility" layer itself (S10/S11): reorder whole panels,
  move a channel to another panel, create a panel by dropping into empty
  space. Depends on 2C-A's static multi-panel view already being proven
  and ideally UAT'd once.

2C-C (optional, evidence-gated) -- Backend multi-channel batching endpoint
  Only if 2C-A/2C-B's real usage shows the N-separate-requests pattern is
  an actually-felt cost (S17 Option B) -- additive, backend-only, doesn't
  block or require rework of 2C-A/2C-B's frontend.

2C-D -- Refinements
  Y-scale mode toggle (Fit <-> Proportional, S19), panel resize (global
  first, per-panel divider as a further NEEDS-UAT refinement, S12),
  layout-mode picker (Separate/Automatic, S9). Polish, once the core
  interaction model from 2C-A/2C-B is validated by real use.

(Beyond Phase 2C -- confirmed architecturally compatible, not scheduled)
  Shared crosshair broadcast (S23), digital panels (S25), A/B cursors
  (S24) -- Phase 2D+/Phase 5, per DEC-021's own already-established
  scope boundary.
```

**Why this sequencing**: 2C-A proves the riskiest new *architecture*
(N-synchronized-Plotly-instances, extending Phase 2B's already-tested
broadcast pattern) together with just enough UX (checkbox-add, minimal
toolbar) to be a coherent, demonstrable slice on its own — deliberately
*not* shipping a multi-panel view with zero shared controls, which would be a
worse intermediate state than doing both together. 2C-B is then a genuinely
separate, more novel UI-interaction slice (real drag-and-drop), correctly
kept apart from 2C-A's architecture-proving concern. 2C-C is explicitly
optional and evidence-gated, matching this project's established
"don't build speculative infrastructure ahead of a demonstrated need"
principle. 2C-D is deliberately last — pure refinement, safest to defer.

---

### 29. Recommended first Phase 2C implementation slice — exact scope

```text
An existing, already-uploaded COMTRADE source (Phase 1, unchanged)
        |
Checkbox-select several analog channels from the existing channel
  browser (S5) -> "Add N selected to workspace"
        |
Automatic engineering_type grouping (S6/S9) into stacked panels --
  one independent Plotly instance per panel (S16), native per-instance
  modebar disabled
        |
Minimal centralized toolbar: Reset Time View + Autoscale Y only (S13),
  driving every panel via the extended Phase 2B broadcast mechanism
        |
Still N separate single-channel GET .../waveform requests (S17 Option A)
  -- zero backend change
```

**Exact scope exclusions for this slice** (mirroring the discipline the
original Phase 2A/2B slices already used):

- Drag/reorder/move/split — S28's 2C-B, not this slice.
- Panel resize UI — S28's 2C-D, not this slice.
- Layout-mode picker (Separate/Custom) — Automatic only for this slice.
- Y-scale mode toggle (Fit/Proportional) — Fit only for this slice.
- Backend multi-channel batching — S28's optional 2C-C, not this slice.
- Digital channels, cursors/measurements, calculated signals,
  synchronization across sources, shared crosshair broadcast, CSV/Excel,
  TTL implementation — none touched, all explicitly out of scope per this
  task's own S45/S17.

**Why this slice, not a larger one**: it proves the two genuinely new,
highest-risk pieces of Phase 2C -- multi-panel synchronized rendering (S16)
and a real, checkbox-driven multi-channel selection flow (S5) -- without
simultaneously building the drag-interaction layer (S28's 2C-B, itself
substantial, separately novel UI work) or any backend change. This mirrors
exactly the reasoning the original Phase 2 discovery/design pass used for
sequencing 2A before 2B: prove the riskiest new architecture first, in as
small a slice as still produces something coherently demonstrable, before
layering the next genuinely new capability on top.

---

### 30. TTL / abandoned-session issue — reassessed for Phase 2C

`[DECISION MODE: COMPARISON]` — unchanged decision mode from Phase 2A's own
assessment; reassessed, not re-litigated, for Phase 2C's specific addition.

`[FACT]`: Phase 2C's own design does **not** change the backend
memory-retention shape at all — the full-resolution `DisturbanceRecord` is
already retained per *source* (DEC-019), regardless of how many channels are
ever queried against it or how many panels a user happens to display. Adding
more panels to an already-open source costs backend memory only in the sense
that more distinct range-request payloads get computed and returned (bounded,
transient, per-request — not retained), never in the sense of retaining more
per-source memory.

**What Phase 2C does change**: the *likelihood* and *typical duration* of
real UAT/exploration sessions — a flexible, multi-channel, drag-arrangeable
workspace is a materially richer thing to explore than Phase 2B's
single-channel preview, so sessions are plausibly longer and more numerous
once Phase 2C actually ships, which raises the *probability* of an abandoned
session accumulating (unchanged per-source cost, more sources/sessions likely
open at once).

**Is this a hard blocker for Phase 2C's own design or first implementation
slice?** No — same reasoning already established for Phase 2A/2B (a
controlled, small number of manually-driven sessions). It should be resolved
(one of the already-compared options from the Phase 2 design's §18 — TTL,
`sendBeacon`, hard limits, or the recommended combination) **before Phase 2C
reaches broader or longer-duration shared-DEV UAT**, for the same reason as
before, now modestly more urgent given the plausibly longer sessions a real
multi-panel workspace invites. This reassessment does not escalate TTL to a
design blocker; it reaffirms the existing urgency assessment is still
accurate and has not been resolved by anything in this pass.

---

### 31. ~100 MB real-file memory validation — reassessed for Phase 2C

Same reasoning as §30: Phase 2C's design does not change the per-source
backend memory shape (only Phase 2A's already-existing retention does), so
this remains an **independent, parallel action item**, not a Phase 2C design
blocker. **Recommendation**: worth doing before Phase 2C reaches broader/
prolonged shared-DEV UAT (same timing rationale as TTL, §30) — more sessions
opened for longer, more exploratory multi-panel use raises the chance of
actually discovering a real large-file memory cliff during a live UAT rather
than in a controlled benchmark — but it does not block Phase 2C's own design
or first implementation slice.

---

### 32. Performance design targets

Practical, extending the already-established Phase 2 design targets (§26
there) rather than inventing new hard numbers:

- **Zoom/pan should remain interactive** across every displayed panel at
  once, not just the panel being directly dragged (a direct consequence of
  the shared-viewport-broadcast architecture, §16).
- **Shared-viewport updates must not trigger a request storm**: the
  broadcast mechanism triggers one *debounce cycle* per viewport change,
  which then fans out to N per-channel requests (or, once §17's optional
  batching endpoint exists, one request) — never N independently-debounced,
  staggered timers.
- **Payload scales with pixel width, not full record size or channel
  count** (§18) — an architectural guarantee, confirmed by construction, not
  a soft aspiration.
- **6–12 visible analog traces should remain comfortable** — matches this
  task's own suggested figure and the existing Phase 2 design's "a handful
  of channels open at once" framing.
- **Larger channel sets rely on hide/collapse rather than rendering
  everything at once** — no scenario in this design proposes opening
  50-100+ channels simultaneously; search/filter (Phase 1, already shipped)
  and per-panel collapse (a natural, low-cost future refinement — collapsing
  a panel's chart should also stop it from receiving viewport-range fetches
  while collapsed) are the intended mechanisms for large channel counts, not
  raw on-screen density.

---

### Closing note on decisions

**No entry was added to `DECISIONS.md` by this pass.** Every architectural
direction above — the panel model (§7), grouping modes (§9), drag/reorder
scope (§10), the one-Plotly-instance-per-panel architecture (§16), the
multi-channel backend strategy (§17), Y-axis scaling (§19), mixed-unit
handling (§20), and the implementation slicing (§28/§29) — remains a
`[PROPOSAL]` or an item under one of the four decision modes (`ANALYSIS`/
`COMPARISON`/`NEEDS UAT`/`DEFER`), per this task's explicit instruction not
to silently approve any of them or begin implementation. `DEC-021` and
`DEC-022` (already approved) are reaffirmed, unweakened, and unchanged
throughout — this pass builds on them, not around them.

---

### 33. Detego vs. `powerwave` vs. proposed Oruxa direction

| Behavior | Detego benchmark | Existing `powerwave` | Owner requirement | Proposed Oruxa direction |
|---|---|---|---|---|
| Channel browser | Sidebar: Analog/Digital/Computed sections, count badges, visibility toggles | Sidebar channel tree with per-channel visibility checkboxes | (none stated beyond general flexibility) | Extend Phase 1's already-shipped, already-UAT'd collapsible/searchable browser with checkboxes + "Add N selected" (§5) — reuse, don't rebuild |
| Grouping | Separate / Group-by-type / Custom (modal editor) | Auto-routes by `_infer_panel_for_channel()`; manual move via drag+combo+merge/split menu | "Groupable," "flexible vertically," never permanently constrained | Auto-group by `engineering_type` (§6/§9) as default; "custom" = drag state, no separate editor dialog (**exceeds Detego** — one less UI to learn) |
| Panel arrangement | Not documented (no reorder found) | Channel↔panel move is live (drag/combo/menu); **panel reorder does not exist** | Owner explicitly wants panels "not fixed in one location" | Both channel↔panel move **and** panel reorder (§10) — **exceeds both references at once**, the clearest opportunity in this whole design |
| Zoom/pan | Zoom (drag), Pan, Reset | Zoom/pan is local PyQtGraph re-view over a once-decimated array; no viewport re-fetch | DEC-021: workspace-level, shared across every channel | Shared X viewport broadcast across all panels (§15/§16), each zoom/pan re-fetches genuinely finer detail (already true since Phase 2A, DEC-019) — improves on `powerwave`'s own non-re-fetching zoom |
| Toolbar | 5 grouped sections (Nav/Measurement/Display/Export/Annotate), one shared toolbar | No single toolbar — controls are distributed across sidebar/legend/context-menus/splitters | DEC-021: centralized, never one modebar per channel | Minimal centralized toolbar (§13): Reset Time View, Autoscale Y, Add channels, Reset Layout — grows later per §28, never one native modebar per panel |
| Crosshair | Single hover cursor (click-placed) + A/B measurement cursors, sample-snapped | Three-way fragmented cursor ownership (confirmed, unresolved in `powerwave` itself) | Native, sample-snapped (already shipped, DEC-022) | Extend the already-proven single-owner Plotly spike-line mechanism to a shared, broadcast hover time across panels (§23) — avoids reproducing `powerwave`'s own fragmentation |
| Y scaling | Two explicit modes: Fit / Proportional | One mode only, always-on, non-toggleable shared-by-unit, non-viewport-aware | (none stated beyond general readability) | Viewport-aware Fit as default (**improves on `powerwave`'s stale full-record autoscale**), Proportional as a later toggle (matches Detego's naming; matches `powerwave`'s own default when toggled) — §19 |
| Panel resize | Per-panel drag divider + global height presets | Native `QSplitter` drag, but **sizes silently discarded on every rebuild** (confirmed bug) | (none stated) | Global height controls first (§12), explicit persisted per-panel height in Oruxa's own state model (§27) — avoids `powerwave`'s own confirmed data-loss bug |
| Multi-source readiness | Not documented | Native — session model already supports multiple sources with independent native sample rates | "Do not build assumptions that later prevent" multi-source | Every panel's trace state already carries `source_id` (§26); no shared-time-grid assumption anywhere (unchanged Phase 2 principle) |

---

### 34. Candidate Phase 2C UAT decisions

Following the same lightweight per-candidate format the original Phase 2
discovery pass used (§29 there) — alternatives, why UAT matters, smallest
useful prototype:

- **Channel-add workflow feel** (§5) — checkbox+button is the ANALYSIS-mode
  recommendation; worth a quick sanity check once the first slice exists
  (does selecting e.g. 8 channels feel fast/clear?), not a separate formal
  trial. Smallest test: the first slice itself, used hands-on.
- **Drag interaction feel** (§10/§11) — whether the grip-handle-only drag,
  drop indicators, and reversibility-over-confirmation approach genuinely
  feels safe and predictable (not accidentally destructive) is inherently a
  hands-on judgment. Smallest prototype: 2C-B itself, the first time it's
  built.
- **Fit vs. Proportional Y-scaling** (§19) — whether Proportional mode is
  actually wanted, and how often, can only be judged once real multi-channel
  panels exist to react to. Smallest prototype: a toggle added to an
  already-working 2C-A/2C-B workspace, not a standalone trial.
- **Panel/global height defaults** (§12) — whether the default panel height
  is comfortable for 3-6 stacked panels on a typical screen. Smallest test:
  visual review of the first slice's default layout.
- **Legend/label density** (§21) — whether the compact panel-header +
  colored-dot-and-name legend row carries enough identity without the
  sidebar open, or whether it needs slightly more (e.g. unit inline). Smallest
  test: the first slice's own panel headers, reviewed hands-on.
- **Centralized toolbar layout** (§13) — button order/grouping/labels, once
  more than the first slice's two buttons exist (§28's 2C-D). Smallest test:
  a quick placement review once the Y-scale toggle/layout-mode picker are
  actually added.
- **Shared crosshair behavior** (§23) — explicitly deferred past Phase 2C
  entirely; not a near-term UAT candidate, listed here only for completeness
  per the task's own suggested list.

---

### 35. Technical decisions ready for analysis (no UAT needed)

Explicitly not burdening the owner with these — each has enough evidence
above for a confident recommendation, consistent with this project's own
"ordinary engineering choices don't need UAT" guidance
([README.md](README.md#decision-modes)):

- **Shared X/time state ownership** (§15/§16) — one Oruxa-owned coordinator
  object, not per-panel state, not a third-party state library.
- **Chart API isolation** (§16) — one independent Plotly instance per panel,
  native per-instance modebar disabled, centralized toolbar calls Plotly
  APIs directly (§14/§16).
- **Request cancellation** — unchanged from Phase 2B's already-proven
  `AbortController` + sequence-number pattern (§17), extended per-panel, not
  redesigned.
- **Waveform data authority** — unchanged; full-resolution backend data
  stays authoritative (DEC-019), display reduction stays presentation-only
  regardless of how many panels request it (§Phase 2A, unaffected by this
  design).
- **Source identity** (§26) — every panel's trace state carries `source_id`,
  not just `channel_name`; no API change implied.
- **Lifecycle cleanup** — unchanged mechanism (`remove()`/`remove_workspace()`,
  DEC-018); Phase 2C introduces no new resource type needing its own cleanup
  path (a panel is pure frontend presentation state, never registered
  backend-side).
- **Point-budget-vs-panel-count reasoning** (§18) — panel count doesn't by
  itself demand a smaller per-channel budget, since panels share one
  container width; the existing `DEFAULT_POINT_BUDGET` mechanism already
  bounds per-channel payload correctly.

---

## Light/Dark Theme & Crosshair Refinement Record (2026-08-15)

`[FACT]` throughout except where explicitly marked `[DECISION]` (DEC-023).
This is a small, general-application UX refinement — **not** Phase 2C work.
Phase 2C (centralized toolbar, panel model, drag/reorder, multi-channel
display) remains explicitly not started; nothing in this record touches it.

### Scope

Two owner-requested goals only:

1. Light/Dark appearance support, Light preferred/default, persisted per
   browser, coherent across the whole app (not waveform-page-only).
2. A further, config-only refinement to the Plotly crosshair (already
   restyled once in the Phase 2B closure pass, DEC-022) to make it visually
   thinner/subtler, closer to uPlot's own crosshair weight.

### Theme system

A small, shared, reusable token system — not scattered hard-coded colors,
not a frontend framework:

- **`frontend/theme.css`** (new): defines every color as a CSS custom
  property under a base `:root` (Light — the default, no `[data-theme]`
  attribute needed) and `:root[data-theme="dark"]` (Dark — opt-in).
  Tokens: `--bg`, `--panel`, `--panel-border`, `--text`, `--text-dim`,
  `--accent`, `--accent-dim`, `--ok`, `--warn`, `--error` (the pre-existing
  names, reused rather than renamed — they already meant exactly "page
  background"/"surface"/"border"/etc.), plus new tokens added for this
  pass: `--waveform-surface`, `--toolbar-surface` (distinct surfaces for
  the chart/toolbar, per the task's own conceptual list), and a set of
  "wash"/tint tokens (`--hover-tint`, `--surface-tint`, `--accent-wash`,
  `--accent-wash-soft`, `--ok-wash`, `--error-wash`, `--overlay-backdrop`,
  `--chart-overlay-bg`) that replace what used to be raw
  `rgba(255,255,255,...)`/`rgba(0,0,0,...)` literals scattered per-page —
  those literals were only ever correct against a dark background and
  would have looked wrong (near-invisible or inverted) under Light without
  this change. Also defines `--spike-color` (the Plotly crosshair color,
  theme-sensitive) and the `.theme-toggle` control's own styling.
- **`frontend/theme.js`** (new): `PowerwaveTheme.getTheme()`/`setTheme()`/
  `mountThemeToggle()`. Applies `[data-theme]` to `<html>` synchronously,
  before `<body>` paints (script runs early in `<head>`), to avoid a theme
  flash. Default is `"light"` whenever nothing is stored. Persists via
  `localStorage` key `powerwave.theme`. Also listens for the `storage`
  event so a preference change in one tab (e.g. the main app) is reflected
  live in another already-open tab (e.g. an open waveform-preview tab) —
  both pages share one origin and one key, consistent with this being a
  general application preference, not a per-page setting.
- **`frontend/index.html`** / **`frontend/waveform-prototype.html`**: both
  `<link rel="stylesheet" href="theme.css">` + `<script src="theme.js">`
  early in `<head>` (same static-file pattern already used for
  `config.js`); their own local hard-coded `:root { --bg: #0f1420; ... }`
  blocks were removed (now supplied by the shared file); every
  `rgba(...)`/hex color literal outside the theme tokens themselves was
  replaced with a token (verified via `grep -n "rgba(\|#[0-9a-fA-F]{3,6}"` —
  the only literals remaining in either file are `color: #fff` on solid
  accent/danger buttons, which is intentionally the same value in both
  themes, not a light/dark-sensitive color). Both pages gained a small
  Light/Dark segmented control (`#themeToggle`, mounted via
  `PowerwaveTheme.mountThemeToggle()`) in their header — a simple
  two-button appearance selector, not a settings-page redesign, per the
  task's own explicit scope limit.
- Applies coherently to: the main Phase 1 page, source/channel browser,
  channel tables, buttons, both confirmation dialogs, upload-status
  banners, the waveform page, and the Plotly chart itself (below) — the
  full list the task asked for.

### Light-theme palette (original Oruxa direction, not Detego's)

`--bg: #f3f5f9`, `--panel: #ffffff`, `--panel-border: #d9dfea`,
`--text: #1b2333`, `--text-dim: #5c6579`, `--accent: #3568d4`,
`--accent-dim: #c7d7f7`, `--ok: #1f9d63`, `--warn: #b8720a`,
`--error: #d23c44`. Design intent: clean, professional, engineering-
focused, bright without being harsh (an off-white page background with
pure-white panel surfaces gives subtle depth without shadows/gradients),
subtle low-alpha borders, a restrained mid-blue accent, and high enough
text/background contrast for extended reading. No technical audit of
Detego's actual palette was performed for this task (nor was one needed) —
per DEC-020/`PRODUCT_REFERENCES.md`, Detego is a UI/UX *workflow* benchmark
only, never a source of colors, and the owner repeated that constraint
directly.

### Dark theme

Unchanged values, migrated onto the same token system rather than kept as
a second, parallel implementation: `--bg: #0f1420`, `--panel: #161d2e`,
`--panel-border: #2a3348`, `--text: #e7ecf5`, `--text-dim: #8b96ad`,
`--accent: #4f8dfd`, `--accent-dim: #2c4a80`, `--ok: #3ecf8e`,
`--warn: #f5a623`, `--error: #f2545b` — every one of these is the exact
value the app already used before this pass; only their *location*
changed (from two independent per-page `:root` blocks to one shared
`:root[data-theme="dark"]` block). Same layout, same behavior, different
appearance, exactly as the task required.

### Plotly theme integration

`waveform-prototype.html`'s `PlotlyRenderer` now reads colors from the
active theme (`themeColors()`, via `getComputedStyle(document.documentElement)`)
at chart-init time (`paper_bgcolor`/`plot_bgcolor` ← `--waveform-surface`,
`font.color` ← `--text`, `xaxis`/`yaxis.gridcolor` ← `--panel-border`,
trace `line.color` ← `--accent`, spike color ← `--spike-color`). A new
`PlotlyRenderer.applyTheme(handle)` method re-applies these to an
**already-rendered** chart on a `powerwave:theme-change` event, using only
`Plotly.relayout` (layout-level: backgrounds, font, grid, spike colors)
and `Plotly.restyle` (trace-level: line color) — **never**
`Plotly.newPlot`/`Plotly.react` with fresh data, and **no new waveform
range request is made**. Verified directly (see Tests below): switching
theme after a chart is loaded triggers zero additional `fetch` calls.

### Crosshair refinement (further pass beyond DEC-022)

- `spikethickness`: `1` → `0.5`. **Technical finding**: Plotly's spike
  lines are rendered as ordinary SVG stroke paths even for a `scattergl`
  (WebGL) trace — the spike-line overlay itself is not part of the WebGL
  trace layer — and SVG `stroke-width` reliably supports fractional values
  below `1` across every current browser (standard SVG rendering, not an
  exotic workaround). This means the prior pass's claim that
  `spikethickness: 1` was Plotly's practical minimum was not fully
  substantiated; `0.5` is used here as a genuine, natively-supported
  thinner value, per the task's own explicit "if a smaller valid native
  value works reliably, use it" instruction.
- `spikecolor` alpha: `0.55` → `0.42` (both Light's and Dark's
  `--spike-color`), applied via the same theme-token mechanism as every
  other color — reduced further, compounding with the thickness change,
  per the task's "aim closer to uPlot's crosshair visual weight" direction.
- Unchanged: `spikedash: "dash"`, `spikesnap: "data"` (still snaps to real
  recorded samples, never interpolated), `spikemode: "across"` (both
  vertical and horizontal guide lines preserved), `hovermode: "closest"`
  (moving X/Y hover values via `hovertemplate`, unchanged).
- **No custom mouse-following overlay, no new cursor architecture, no
  custom hover engine were built** — explicitly out of scope per the task,
  consistent with DEC-022's same prior constraint.
- **Honest limitation, stated per the task's own instruction**: pixel-level
  visual confirmation of the thinner line was not performed in this
  sandboxed, no-real-browser session — the change rests on SVG's
  well-established fractional-stroke-width support, not a live screenshot
  comparison. This is exactly what the task's "Live DEV verification"
  section is for.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched (`git diff --stat -- backend/` empty), confirmed by a fresh
  regression run.
- **Frontend: 19 new scripted `jsdom` checks, all passing** (a new,
  uncommitted one-off script, per this project's established testing
  pattern — not a new permanent test framework), covering: Light is
  default with no stored preference; Dark is selectable; Light is
  restorable; the preference persists across a simulated page reload (the
  real `theme.js` source is re-evaluated against the same `localStorage`
  state, exactly as a real reload would re-run it); `[data-theme]` is
  applied to `<html>`; the shared toggle control renders exactly two
  buttons and updates `aria-pressed` state on click; the waveform page
  independently picks up an already-saved preference via the same shared
  mechanism; the waveform page's own toggle reflects that preference; the
  Plotly chart initializes with the dashed/thinner/theme-colored/
  sample-snapped crosshair configuration; hover X/Y values remain
  configured; a theme switch triggers `Plotly.relayout`/`Plotly.restyle`
  with the new theme's colors and **zero** additional `fetch` calls; and
  Reset Time View still triggers exactly one fresh waveform request
  (zoom/pan/reset behavior unchanged).

### Preserved, unchanged

Per the task's explicit requirement, none of the following changed: Plotly
as the selected renderer (DEC-022); the waveform range API/its query
parameters; full-resolution backend authority; the min/max display
representation; zoom/pan interaction; Reset Time View / Autoscale Y
semantics and their DEC-021 terminology split; sample snapping; the
backend source/workspace lifecycle. **DEC-021's workspace-level,
centralized-toolbar requirement is unaffected** — this pass touched only
color/theme concerns on the existing single-channel preview page, not its
navigation architecture. No backend file was modified.

### Files changed

Modified: `frontend/index.html`, `frontend/waveform-prototype.html`,
`frontend/Dockerfile`, `frontend/.dockerignore` (comment only),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`.
New: `frontend/theme.css`, `frontend/theme.js`. No `backend/` file, no
CI/deployment workflow file touched.

### Follow-up: crosshair visual UAT refinement (2026-08-15, same day)

`[FACT]`. Theme UAT (above) passed with no changes requested. The owner's
only remaining feedback was that the Plotly crosshair was still too
coarse (dash segments too long) and too faint (in **both** themes). A
small, config-only follow-up refinement — no new `DECISIONS.md` entry, an
"Update" note was appended to DEC-023 instead, since this is the same
crosshair-styling concern DEC-023 already covers, not a new decision.

- **Thickness**: `spikethickness` `0.5` → `0.35` — the same reasoning as
  the prior pass (Plotly's spike-line overlay renders as an ordinary SVG
  stroke path, and SVG `stroke-width` reliably supports fractional values
  across current browsers).
- **Dash pattern**: `spikedash` changed from the named `"dash"` style to
  a custom native Plotly dash-length string, `"3px,2px"`. Plotly's own
  `dash` attribute documents the `"px,px,..."` custom-length syntax as a
  first-class supported value alongside the named styles
  (solid/dot/dash/longdash/dashdot/longdashdot) — this is native
  configuration, not manually-generated SVG or a workaround.
  **Native-limitation finding**: Plotly's built-in named `"dash"` style's
  exact internal pixel definition is not stable, documented public API,
  so it cannot be reliably reverse-engineered and halved to produce a
  mathematically exact "half length." A custom dash-length string was
  used instead — a deliberately shorter, still-reads-as-dashes-not-dots
  value — as the closest clean native option, per this task's own
  explicit allowance for that outcome when an exact match isn't possible.
- **Contrast**: `--spike-color` strengthened in both themes (theme.css),
  stopping short of full opacity to keep the crosshair visually secondary
  to the waveform trace: Light `rgba(92, 101, 121, 0.42)` →
  `rgba(60, 68, 87, 0.6)` (darkened toward `--text`, higher alpha); Dark
  `rgba(139, 150, 173, 0.42)` → `rgba(168, 178, 199, 0.6)` (brightened
  toward `--text`, higher alpha). Grid-line styling (`gridcolor`) was
  deliberately left untouched — the owner already finds it acceptable.
- **Unchanged**: `spikesnap: "data"`, `spikemode: "across"`,
  `showspikes: true` on both axes, `hovermode: "closest"`, moving hover
  X/Y values, theme-switch-without-refetch behavior (`Plotly.relayout`/
  `Plotly.restyle` only), DEC-021/DEC-022, waveform API, zoom/pan/Reset
  Time View/Autoscale Y, source/workspace lifecycle. No custom crosshair
  or cursor overlay was built. No backend file was touched.
- **Honest limitation, restated**: pixel-level visual confirmation of
  both the thickness and dash-length changes was not performed in this
  sandboxed, no-real-browser session — the live DEV verification step is
  where the owner can confirm the result directly.
- Tests: 19 scripted `jsdom` checks (the same script from the theme pass,
  updated in place for the new thickness/dash/color values — not a new
  test file), all passing; 278 backend tests, unmodified, all passing.
- Files changed: `frontend/theme.css` (`--spike-color` in both themes),
  `frontend/waveform-prototype.html` (`spikethickness`/`spikedash`
  values + updated comments), `docs/project-memory/{DECISIONS,
  MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`. No `backend/` file, no
  `frontend/index.html` change, no CI/deployment workflow file touched.

---

## Phase 2C-A — Synchronized Multi-Channel Waveform Display Implementation Record (2026-08-15)

`[FACT]` throughout except where explicitly marked `[DECISION]` (DEC-024).
This is a small, deliberately scoped first Phase 2C implementation slice —
matches the recommended first slice from the Phase 2C discovery/design
pass's own §29, though re-derived/re-confirmed directly against this
task's own specification rather than assumed unchanged. **Phase 2C-B
(drag/reorder between panels, panel resize, Proportional Y scaling,
mixed-unit handling, digital channels, shared crosshair) is explicitly
not started.**

### Scope

Built directly into `frontend/index.html` (not a new isolated page) — the
existing Phase 1 channel browser (search/grouping unchanged) gains
checkbox selection; a new "Waveform Workspace" section below the existing
upload/browse layout renders synchronized, multi-panel Plotly charts.
`frontend/waveform-prototype.html` (Phase 2B's single-channel isolated
preview) is untouched and remains available.

### Channel selection

A checkbox is added as the first column of the analog channel table only
(digital channels are unaffected — no checkbox, no selection). Selection
state (`selectedChannels`, a `Map` keyed by `"sourceId::channelName"`)
lives in JS, not the DOM, so it survives the channel table being rebuilt
when the user switches which source they're browsing (existing
`selectSource()`/`renderChannels()` behaviour, unchanged). A
"selection-row" above the channel groups shows `"Add N selected"`
(disabled at N=0) and `"Clear selection"` (also disabled at N=0), wired
fresh on every render via `setupSelectionControls()` — the same
re-wire-after-innerHTML-replace pattern the existing channel search
already used. Clicking "Add N selected" hands the current selection to
`wwAddSelectedChannels()` and clears the selection immediately.

### Initial grouping

`wwAddSelectedChannels()` groups newly-added channels by the
already-backend-computed `engineering_type` (never re-derived
client-side) — an existing panel whose label matches receives the new
channel via `Plotly.addTraces()`; no matching panel creates a new one.
**This is placement only** — the panel object model has no concept of a
channel being permanently bound to its panel; a future Phase 2C-B move
operation would simply be `Plotly.deleteTraces()` on the source panel +
`Plotly.addTraces()` on the target panel + updating `panel.channels`,
using mechanisms this slice already exercises for add/remove.

### Panel architecture

One independent Plotly instance per panel (`wwInitPanelPlot()` /
`Plotly.newPlot`), never a single figure with fixed subplots — confirms
the Phase 2C design's own §16 recommendation (DEC-024). A panel may hold
one or more channel traces (added via `Plotly.addTraces`, removed via
`Plotly.deleteTraces`, always looked up by current array position —
`panel.channels.indexOf(channel)` — rather than a cached index, avoiding
stale-index bugs after a removal shifts the remaining traces). Every
panel's own native Plotly modebar is disabled
(`config.displayModeBar: false`) — the central toolbar (below) is the
only navigation surface. Each panel keeps its own independent Y axis;
crosshair/hover behaviour (DEC-022/DEC-023, unchanged: dashed, thin,
theme-driven, sample-snapped) is also independent per panel — **crosshair
synchronization across panels is explicitly not part of this slice**.

### Shared X/time viewport (DEC-021)

Every panel's Plotly instance is wired with the same relayout-handling
pattern Phase 2B already proved for one channel (`wwWirePanelRelayout()`),
now fanned out to N panels: an explicit range change (`xaxis.range[0]`/
`[1]`, from either drag-zoom or pan) is debounced (120ms, unchanged from
Phase 2B) and then broadcast to **every** panel via
`wwApplyAndFetchViewport()`, which relayouts every panel to the exact
same clamped range and refetches every displayed channel for it.

**Loop prevention**: each panel object carries its own `suppressNext`
flag, set immediately before the broadcast's own `Plotly.relayout()` call
on that panel and consumed (checked-and-cleared) first thing inside that
panel's own relayout handler — a broadcast-driven relayout can never
re-trigger another broadcast. This was verified with a test double that
faithfully simulates Plotly's real behaviour (a programmatic
`Plotly.relayout()` call does re-fire `plotly_relayout` listeners — that
is the entire reason this guard exists) rather than a mock that would
silently make the loop-prevention question untestable; see Tests below.

A native double-click-to-reset gesture (`xaxis.autorange: true` — still
reachable on the plot area itself even with the modebar hidden) is
treated the same as clicking "Reset Time View" (X-range broadcast only,
matching the honest limitation already documented in Phase 2B: Plotly's
own double-click conflates X-reset and Y-autorange for that one panel;
the other panels only receive the X-range broadcast, not a Y reset).

### Central toolbar

Four controls, matching this task's exact specification, no more:

- **Zoom** / **Pan** — a two-button segmented pair (reusing the existing
  `.theme-toggle` visual pattern) setting `dragmode` on every panel via
  `Plotly.relayout`. A pure layout-level change — never touches
  `xaxis.range`, so it cannot trigger the viewport broadcast.
- **Reset Time View** — restores the full-record range (learned once,
  `ww.recordBounds`) on every panel and refetches every channel for it.
- **Autoscale Y** — `Plotly.relayout(panel, {"yaxis.autorange": true})`
  on every panel.

No cursor, A/B cursor, annotation, export, or grouping control was added
— explicitly out of scope per this task.

### Autoscale Y — viewport-aware Fit, confirmed

Every panel's currently-loaded trace data already covers exactly the
current shared viewport, by construction — each channel is re-fetched
per range change (§ above), never held as a full-record array
client-side once zoomed. Plotly's own native `yaxis.autorange`
therefore recomputes the Y range from data that is already
viewport-scoped — no custom Y-range math was written, no whole-record
fallback exists. Proportional/shared-unit scaling remains explicitly
deferred (not implemented).

### Backend / API

**No backend file was changed.** The existing Phase 2A single-channel
`GET .../sources/{source_id}/waveform` endpoint is reused, called once
per displayed channel (`wwFetchChannelRange()`), each with its own
independent `AbortController` + monotonic sequence number — the same
stale-request-protection pattern Phase 2B already proved for one channel,
now generalized to N channels each guarding their own fetch lifecycle
independently, not a new shared mechanism. Every channel uses the same
`start_time`/`end_time` (the shared viewport) and the same
`point_budget` (`WW_POINT_BUDGET = 4000`, matching the backend's existing
`DEFAULT_POINT_BUDGET` and Phase 2A/2B's own established policy) — no new
point-budget formula was invented; panel/channel count does not by
itself reduce the per-channel budget, since every panel shares the same
horizontal pixel width regardless of how many other panels exist (already
reasoned through in the Phase 2C design record's §18). Zooming inward
continues to reveal genuinely finer real detail — this is unchanged Phase
2A behaviour (`extract_waveform_range`'s own range-then-reduce logic),
not something this frontend-only slice could alter even if it wanted to.

### Removing displayed channels / clearing the workspace

A small "×" per channel in each panel's compact legend row
(`wwRemoveChannelByKey`/`wwRemoveChannel`) removes exactly that trace
(`Plotly.deleteTraces`) and, if it was the panel's last channel, removes
the whole panel (`Plotly.purge` + DOM removal). **Never removes the
imported source itself** — this is purely display state. A "Clear
workspace" button (in the section header, deliberately kept separate from
the 4-button central toolbar so that toolbar stays exactly as specified)
removes every panel at once. Both `performRemoveSource()` (existing
per-source removal) and `resetToNewWorkspace()` (existing whole-workspace
reset, DEC-018) now also clean up the waveform workspace:
`wwRemoveChannelsForSource(sourceId)` removes only that source's
displayed channels (a different displayed source's channels, if any,
are left alone); `wwClearWorkspace()` removes everything unconditionally.
An `ww.epoch` counter, incremented by `wwClearWorkspace()`, guards against
an in-flight "Add selected" batch resolving after the user cleared/reset
the workspace mid-flight and trying to draw into now-detached DOM — a
small, cheap guard modeled on the same stale-response-protection idea
already used per-request (sequence numbers), applied here at the
whole-workspace level.

### Labels

Compact, matching this task's own "do not create large legends" limit: a
panel header shows only the engineering-type label (e.g. "Voltage"); a
small pill-style legend row below it shows each channel's color dot, name,
and unit (e.g. "VA (V)") plus its own remove control. Full detail (exact
time/value) stays in the existing native Plotly hover tooltip, not
repeated in the legend. No metadata card, no source name/phase repeated
per panel (that detail remains in the existing Phase 1 sidebar).

### Theme / crosshair (DEC-022/DEC-023, preserved)

Every panel is included in the existing `powerwave:theme-change` handling
(`wwApplyTheme()`): on a Light/Dark switch, every panel's chart chrome
(backgrounds, font, grid, spike colors) is re-applied via
`Plotly.relayout` only — **verified by test that this never triggers a
new waveform fetch**, extending Phase 2B's own already-proven behaviour
from one chart to N. Trace line colors are **not** theme-reactive (unlike
Phase 2B's single-channel page) — they are per-channel identity colors
(a small fixed palette, cycled in the order channels are added), which
stay the same across a theme switch by design, since a channel's color is
its own identity, not a semantic theme color. Light remains the default
theme; the crosshair remains `spikethickness: 0.35`, `spikedash:
"3px,2px"`, sample-snapped, theme-driven contrast — unchanged from the
prior pass, applied identically to every panel now instead of one chart.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend, new: 19 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern) — channel selection/Add/Clear;
  initial engineering-type grouping into the correct panel count; one
  `Plotly.newPlot` per panel with the correct trace count; no per-panel
  modebar; shared-viewport broadcast on zoom AND pan, verified against a
  Plotly test double that faithfully re-fires `plotly_relayout` on a
  programmatic `relayout()` call (so loop-prevention is actually
  exercised, not just structurally present); Zoom/Pan toolbar buttons
  (dragmode only, never refetches); Reset Time View (refetches, restores
  full record on every panel); Autoscale Y (native `yaxis.autorange`,
  never refetches); theme switch (re-colors every panel, never refetches);
  removing one channel (panel survives); removing every channel (panel
  removed, `Plotly.purge` called); source removal clears only that
  source's displayed channels; "Start new workspace" clears everything;
  a 12-channel/4-panel structural scale check (exactly 12 requests, no
  duplication, a 12-channel zoom refetches exactly 12 times, not a
  multiplied or runaway amount).
- **Frontend, existing (Phase 1 regression): 4 scripted `jsdom` checks,
  re-run and still passing** (`frontend_logic_check.mjs`, from the
  original Phase 1 UAT-refinement pass) — grouping/counts/expansion/
  columns, search filtering (analog + digital, cross-group auto-expand),
  remove confirmation + stale-banner fix, unrelated-removal banner
  isolation. Two of this script's own assertions were updated in place
  (not weakened) to account for the new, intentional leading checkbox
  column — an empty `<th>`/`<td class="select-col">` that a purely
  positional "first cell" assertion would otherwise misread; the updated
  assertions are strictly more precise (`td:not(.select-col)`,
  filtering empty headers before comparing labeled ones), not looser.

### Performance (section 15)

Structurally verified via the jsdom suite above at 3, 6, and 12 displayed
channels: request count scales exactly linearly (N channels → N initial
requests, N channels → N refetch requests per shared-viewport change),
never duplicated, never a multiplied/runaway amount even at 12 channels
across 4 panels. This is a structural/request-count guarantee, not a
browser-rendering-smoothness measurement — this sandboxed session has no
real browser, so actual paint/scroll/interaction responsiveness at these
channel counts was **not** visually confirmed here; live DEV round-trip
API timing (payload size, latency) was measured instead as the closest
available evidence — see this task's own final report for the exact
numbers. **Per this task's own explicit instruction, no claim is made
about 50/100 simultaneous visible channels** — that scenario was not
built for, requested, or tested.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no `frontend/waveform-prototype.html`
change.

---

## Phase 2C-B1 — Grouped / Separate Analog Waveform Layout Implementation Record (2026-08-15)

`[FACT]` throughout except where explicitly marked `[DECISION]` (DEC-025).
A small, deliberately scoped slice — matches this task's own explicit
"keep the scope intentionally small" instruction. **Direct vertical
drag/reorder of lanes, drag-to-overlay/group, drag-out-to-separate, and
Custom layout mode are explicitly not started.**

### Phase 2C-A manual UAT result (recorded here, this pass)

Before this slice began, the owner manually UAT'd the completed Phase
2C-A implementation and confirmed it **passed** for: shared waveform
synchronization, horizontal zoom, Reset Time View, pan synchronization,
Voltage/Current grouping, and Autoscale Y. Two findings noted for later,
**deliberately not addressed in this slice**:

- A small amount of interaction latency was noticed but judged currently
  bearable — not a blocker, no performance work was requested or done
  this pass.
- Vertical zoom (Y-axis zoom/drag interaction) is less intuitive than the
  rest of the toolbar — explicitly flagged for a **later** UX refinement
  pass, not this one.

The next requested enhancement, and this slice's entire scope, was
waveform layout flexibility — specifically Grouped vs. Separate panel
arrangement.

### Layout selector

A small two-button segmented control — **Grouped** / **Separate** —
added to the existing central toolbar (reusing the same `.theme-toggle`
visual pattern already used for the Zoom/Pan pair), visible whenever the
toolbar itself is visible (i.e. whenever at least one channel is
displayed). Grouped is the default, matching Phase 2C-A's existing
behaviour exactly. **Custom** mode (Detego's own third grouping mode, per
the Phase 2C design record's Detego findings) was deliberately not built.

### Grouped mode — confirmed unchanged

Verified via the full existing Phase 2C-A test suite (19 checks) re-run
unmodified against this pass's code, all still passing: adding channels
still groups them by the backend-computed `engineering_type` into shared
panels, still only an initial placement (never a permanent lock), zoom/
pan/reset/autoscale/theme/removal all still behave exactly as Phase 2C-A
shipped them.

### Separate mode — one channel per lane

Each displayed analog channel gets its own panel/lane (one Plotly
instance, one trace, its own Y axis) — verified structurally: 6 displayed
channels produce exactly 6 Separate panels. Panel label is the channel
name (e.g. "VA"); the existing compact legend row (channel name + unit +
remove control, unchanged from Phase 2C-A) still appears beneath it, so
name and unit are both visible without an oversized header or card.

### Architecture — displayed channels / panels / membership / order (not `engineering_type`-derived)

Per this task's own explicit forward-compatibility requirement (§13),
the underlying model was generalized rather than hard-coded for two
modes:

- `ww.panels` is still exactly what Phase 2C-A already had — an ordered
  array of `{id, label, channels: [...]}` objects. This already *is* the
  "panels + channel membership + panel order" shape the task asks for;
  nothing about it needed to change.
- What's new: `wwPanelGroupKeyFor(channel)` / `wwPanelLabelFor(channel)`
  — two small functions that derive a panel's identity/label from the
  *current* `ww.layoutMode` (`engineering_type` for Grouped, the
  channel's own unique key for Separate) rather than Phase 2C-A's
  previous hard-coded `p.label === meta.engineeringType` lookup. Channels
  themselves gained one new retained field, `engineeringType` (present on
  every channel entry since the moment it's added, not re-fetched later),
  so a later regroup never needs to re-derive or re-request metadata.
- `wwRebuildLayout()` — the actual mode-switch mechanism: snapshots the
  flat list of currently displayed channels from `ww.displayed` (already
  the authoritative "what's on screen" map, unchanged from Phase 2C-A),
  tears down every current panel's Plotly instance, and re-derives
  `ww.panels` from that flat list under the (now current) layout mode,
  before creating fresh Plotly instances for the result.

This means a future direct-manipulation feature (drag a lane vertically,
reorder, drop one channel's lane onto another to overlay/group them, drag
a channel back out to separate it again) is architecturally just another
way of producing the same `{panels, channel membership, panel order}`
shape `wwRebuildLayout()` already produces algorithmically — not a
redesign of the data model. This slice does not build any of those
interactions, but was written so they don't require restructuring what's
here.

### Shared X/time synchronization (DEC-021) — reused, not reimplemented

Both layout modes use the exact same relayout-wiring mechanism Phase
2C-A already proved (`wwWirePanelRelayout`, the debounced 120ms
broadcast, the per-panel `suppressNext` loop-prevention flag) — nothing
about the synchronization mechanism itself changed; it simply now runs
against however many panels the current layout mode happens to produce
(2 in Grouped for a 6-channel Voltage/Current selection, 6 in Separate
for the same selection). Verified directly: zooming any one Separate lane
broadcasts to all 6 lanes with exactly 6 relayout calls (not a runaway
loop, using the same faithful Plotly-relayout-refires-event test double
Phase 2C-A's own suite already established); panning a different lane
does the same; Reset Time View and Autoscale Y both correctly operate
across all 6 lanes.

### Viewport preservation across layout switches

**Verified, not merely asserted**: after zooming to a specific window in
Separate mode, switching to Grouped rebuilds the 2 grouped panels with
`layout.xaxis.range` already set to that exact same window — because
`wwBuildLayout()` (unchanged from Phase 2C-A) already reads the *current*
`ww.viewport` for a new panel's initial X range, and `wwRebuildLayout()`
never touches `ww.viewport` itself. No special-case code was needed for
this requirement — it falls out directly from `ww.viewport` already being
workspace-level state, independent of any individual panel, since Phase
2C-A. Switching back to Separate again preserves the same window a second
time, and all 6 channels remain displayed throughout every switch in
either direction.

### Data / API behaviour — zero refetches on layout switch

**No waveform request is issued by a layout-mode switch, in either
direction.** Verified directly: the fetch-call count before and after
`wwSetLayoutMode()`/`wwRebuildLayout()` is identical. Each channel's
already-fetched `.time`/`.values` (from whatever the last successful
fetch was, at the current viewport) is reused as-is when its new panel is
built via `Plotly.newPlot`. No backend file was touched; the Phase 2A
waveform endpoint's query parameters are unchanged (`channel_name`,
`start_time`, `end_time`, `point_budget` — confirmed by test, no other
parameter is ever sent); no batching endpoint was added.

### Removal behaviour in both modes

No changes were needed to `wwRemoveChannel()` itself — it was already
layout-mode-agnostic from Phase 2C-A (look up the channel's current
position in its panel's `channels` array, delete that trace, remove the
whole panel if it's now empty). Because a Separate-mode panel always has
exactly one channel by construction, removing that channel always empties
(and therefore removes) its panel — exactly the required "its lane
disappears" behaviour, achieved with zero special-casing. Grouped-mode
removal is unchanged: only the trace is removed unless the panel becomes
empty. Removing a channel never touches its imported source (unchanged
principle, DEC-018/Phase 2C-A).

### Theme / crosshair — unchanged

No crosshair styling was touched (`spikethickness: 0.35`,
`spikedash: "3px,2px"`, current Light/Dark contrast, sample-snapped,
unchanged from DEC-022/DEC-023). Theme switching re-colors every visible
panel via `Plotly.relayout` only, regardless of layout mode, still never
refetching waveform data — verified directly against a 5-lane Separate
workspace (after one channel had been removed) as well as the original
2-panel Grouped case.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend, new: 16 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern) — Grouped-mode baseline;
  switching to Separate produces exactly 6 panels with correct labels, no
  per-panel modebar, zero new waveform fetches, old panels purged; shared
  zoom/pan synchronization and loop-prevention in Separate mode; Reset
  Time View and Autoscale Y in Separate mode; viewport preservation across
  Separate→Grouped→Separate (asserted via the actual `layout.xaxis.range`
  Plotly was called with, not just visual inspection); channel removal in
  Separate mode removes the whole lane; theme switching in Separate mode;
  and a direct check that every waveform request's query parameters are
  still exactly the existing four (`channel_name`/`start_time`/
  `end_time`/`point_budget`) — confirming no backend API shape changed.
- **Frontend, existing: the full Phase 2C-A suite (19 checks) and the
  Phase 1 regression suite (4 checks) were both re-run unmodified against
  this pass's code and both still pass in full** — no regression in
  either the Phase 2C-A synchronized-workspace behaviour or the original
  Phase 1 channel-browser behaviour.

### Performance

Structural evidence only (this sandboxed session has no real browser):
switching layout mode issues zero network requests (confirmed by test) —
the operation is pure DOM/Plotly reconstruction from already-in-memory
data, so its cost is bounded by however expensive `Plotly.newPlot` is for
the resulting panel count, not by any new fetch latency. At 6 Separate
panels this remains the same channel count already performance-checked
in the Phase 2C-A implementation record (parallel-fetch wall time ~150ms
at 6 channels on live DEV) — this slice adds no new fetches on top of
that baseline for a mode switch specifically. Real browser rendering
responsiveness for the rebuild itself was not visually measured here;
see this task's own live DEV verification for hands-on observation.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

---

## Phase 2C-B2 — Unified Analog Canvas Layout Implementation Record (2026-08-15)

`[FACT]` throughout except where explicitly marked `[DECISION]` (DEC-026).
A small, deliberately-scoped **visual/layout refinement of Separate mode
only** — no panel/data model change, no synchronization change, no backend
change. **Direct vertical drag/reorder, drag-to-overlay/group,
drag-out-to-separate, digital-channel rendering, and Custom layout mode
are explicitly not started.**

### Phase 2C-B1 manual UAT result (recorded here, this pass)

The owner manually UAT'd the completed Phase 2C-B1 (Grouped/Separate
toggle) implementation. **Passed**: Separate-mode waveform synchronization,
horizontal zoom, pan, shared X/time movement. **Refinement required**:
Separate mode's *visual layout* looked like a stack of independently
bordered, individually-headed dedicated cards/panels (one per channel) —
not the single continuous analog canvas the owner wanted. The owner
supplied a Detego screenshot purely as a visual/layout reference (per the
Detego Benchmark Principle, DEC-020) for what "one continuous canvas with
independent lanes" should look like, and this task's own specification is
the resolved target: **each analog channel keeps its own lane and its own
Y scale (never merged onto one shared Y axis), but the surrounding visual
chrome — card borders, repeated backgrounds, repeated headers — should
disappear so all lanes read as one shared workspace.**

### Unified analog canvas — new Separate-mode visual structure

`#wwPanels` (the container all panel DOM nodes are appended to, unchanged
from Phase 2C-A) gains a new `ww-panels-unified` class **only while
`ww.layoutMode === "separate"`** (toggled in `wwSetLayoutMode`, CSS-only —
no DOM restructuring). With that class present:

- the container itself supplies ONE shared background
  (`var(--waveform-surface)` — the same token each Plotly chart's own
  `paper_bgcolor`/`plot_bgcolor` already reads via `wwThemeColors()`, so
  the container's background and every chart's own background are
  literally the same color — no visible seam) and ONE shared outer border/
  radius, replacing N repeated per-panel cards with one workspace-level
  frame;
- each `.ww-panel` loses its own border/background/border-radius/
  margin-bottom entirely and instead becomes one row of a CSS grid
  (`grid-template-columns: 108px 1fr`) with a single hairline
  `border-bottom` divider between lanes (omitted on the last lane) — a
  subtle horizontal separator, not a repeated card;
- the (now-redundant, since a Separate-mode panel's header text always
  equals its one channel's name — the same string the legend chip already
  shows) `.ww-panel-header` block is hidden; the existing compact legend
  chip (colored dot + channel name + unit + remove control, unchanged
  markup from Phase 2C-A/B1) becomes the sole per-lane label, placed in the
  narrow 108px left column;
- `.ww-chart-wrap` loses its own border/background and occupies the wide
  right column (`1fr`) — **the waveform plot area gets the maximum
  available width**, exactly as required;
- lane height (`.ww-chart`) is reduced from 260px to 140px for this mode
  only — compact enough that six lanes read as one stacked canvas, still
  tall enough to inspect waveform shape (per this task's own §10 guidance;
  no user-resizing was built, matching the explicit exclusion).

**Grouped mode's own CSS is completely untouched** (the original, unscoped
`.ww-panel` rule still declares its full card border/background/margin) —
`#wwPanels` never gains `ww-panels-unified` while `ww.layoutMode ===
"grouped"`, so Grouped mode continues to render exactly as Phase 2C-A
shipped it. Nothing here changes what "grouping" means — it is purely
which CSS class is toggled on the shared container, driven by the same
`ww.layoutMode` flag Phase 2C-B1 already introduced.

### Lane presentation — borders, spacing, labels, axes

- **Borders**: no card border/background repeats per lane; one hairline
  `border-bottom` divider between lanes (omitted on the last), one shared
  outer container border.
- **Spacing**: `.ww-panel` padding reduced to `2px 14px`, `margin-bottom:
  0` — lanes stack tightly with no large vertical gaps.
- **Labels**: the per-lane header text is hidden (redundant in Separate
  mode); the existing legend chip (dot + channel name + unit + remove
  button) is the one compact label, in a fixed-width left column so every
  lane's label column — and therefore every lane's chart column — starts
  at the same horizontal position, keeping the Y-axis regions visually
  aligned across all six lanes.
- **X-axis**: per this task's own §8, only the bottom-most lane (last in
  `ww.panels`' order) shows X tick labels and the "Time (s)" title; every
  other lane suppresses both via a new `wwUpdateBottomLaneAxis()` function
  — a pure chrome `Plotly.relayout({"xaxis.showticklabels", "xaxis.title"})`
  call per panel, never touching `xaxis.range`, so it cannot interact with
  the existing viewport-broadcast loop-prevention path. Called after every
  panel-array mutation that could change which lane is "last": adding
  channels, removing a channel (removing the current bottom lane correctly
  hands the shared-axis role to the new last lane — verified by test), and
  rebuilding the layout on a mode switch. **Grouped mode never calls this
  function's suppression path** — every Grouped panel keeps its own full
  X axis, unchanged.
- **Y-axis**: completely untouched — each lane still gets its own
  independent Y axis and its own unit label (Plotly's native `yaxis.title`,
  set once at panel creation in `wwBuildLayout`, unaffected by any of this
  pass's CSS/axis-visibility work). **Channels are never merged onto one
  shared Y axis** — this was the task's own explicit critical distinction
  (§4), and nothing in this implementation touches trace-to-axis
  assignment; each panel is still exactly one independent Plotly instance
  with exactly one Y axis, exactly as Phase 2C-A/B1 already built it.

### Synchronization preserved exactly

No change to the shared-viewport mechanism itself: `wwWirePanelRelayout`,
the 120ms debounced broadcast, per-panel `suppressNext` loop-prevention,
and the stale-request-protected per-channel fetch pipeline are all
byte-for-byte unchanged from Phase 2C-A/B1. Verified directly (jsdom):
zooming any one Separate lane still broadcasts to all 6 lanes with exactly
6 relayout calls (no runaway loop) and exactly 6 refetches; panning a
different lane does the same; Reset Time View and Autoscale Y both still
operate correctly across all 6 lanes without a stray refetch from
Autoscale. The new `xaxis.showticklabels`/`xaxis.title` relayout calls are
a disjoint code path from the range-broadcast relayout calls and were
verified not to trigger it.

### Grouped mode — no regression

Verified via the full existing Phase 2C-A (19 checks) and Phase 2C-B1 (16
checks) suites, re-run unmodified against this pass's code, both still
passing in full, plus a new dedicated check that Grouped mode's panels
never receive a `showticklabels` relayout call at all (its panels' X axes
are simply never touched by the new suppression logic).

### Future drag readiness (section 15)

No new architecture was needed here beyond what Phase 2C-B1 (DEC-025)
already built: `ww.panels` is still an ordered array of `{id, groupKey,
label, channels: [...]}` objects — stable identity (`panel.id`), explicit
channel membership (`panel.channels`), and explicit order (array position,
which a future drag/reorder feature would mutate directly instead of the
current algorithmic `wwRebuildLayout()` derivation). This pass's only
addition — reading `ww.panels`' order to decide which lane is "last" for
the shared X axis — is itself evidence that lane order is already a
first-class, directly-inspectable property of the data model, not
something baked into CSS or DOM position independently. No drag handle or
drop-target markup was added (this task's own §15 explicitly said "if
useful," and the existing `.ww-panel-header`'s flex row already has room
for one later without restructuring); nothing here narrows that option.

### Digital-section readiness (section 16)

**Digital rendering was NOT implemented — no digital content, fake or
real, exists anywhere in this pass.** No dedicated "digital section"
container was introduced either, since nothing yet needs to attach to one
(no digital data flows through Phase 2A/2C at all currently) — introducing
an empty semantic boundary with nothing inside it was judged unnecessary
scope for this slice. `#wwPanels` remains a single, self-contained
container; adding a sibling digital section beneath it later does not
require restructuring anything built in this pass, since `#wwPanels`
already sits inside its own `<section class="workspace-section">` with
room for additional siblings.

### Data / API behavior — zero refetches, unchanged contract

**This is a visual-only refinement; it does not touch data loading at
all.** No waveform request is issued by the new CSS class toggle or the
new axis-visibility relayout calls — verified directly: fetch-call counts
before/after switching into Separate/unified mode are identical, exactly
as Phase 2C-B1 already established. The Phase 2A waveform endpoint's query
contract is unchanged (`channel_name`/`start_time`/`end_time`/
`point_budget` only, confirmed by test); no backend file was touched; no
batching endpoint was added.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend, new: 20 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern) — covering this task's own
  §18 list: static-CSS-source checks that the unified-container and
  de-carded-lane rules exist and that Grouped's own card CSS is untouched;
  Separate mode still creates one lane per channel and now also applies
  the `ww-panels-unified` class; the mode switch still issues zero new
  waveform fetches; only the bottom-most lane shows X tick labels/title
  (verified against the actual `Plotly.relayout` calls, restricted to the
  currently-active panel elements to avoid counting stale elements from
  earlier torn-down layouts); Grouped mode's panels never receive an
  axis-suppression relayout; zoom/pan/Reset Time View/Autoscale Y/no
  per-lane modebar all still work identically; viewport preservation
  across Separate→Grouped→Separate switches (including the re-applied
  `ww-panels-unified` class); theme switching re-colors every lane without
  refetching; removing the current bottom lane correctly hands the shared
  axis to the new last lane; "Clear workspace" still empties the unified
  container completely; and the waveform query-parameter whitelist is
  unchanged.
- **Frontend, existing: the full Phase 2C-B1 suite (16 checks), Phase 2C-A
  suite (19 checks), and Phase 1 regression suite (4 checks) were all
  re-run unmodified against this pass's code and all still pass in full**
  — 39 existing checks, zero regressions. 59 total frontend checks this
  pass.

### Performance

Structural evidence only (this sandboxed session has no real browser): the
new CSS class toggle and axis-visibility relayout calls issue zero network
requests (confirmed by test) — the visual refinement's cost is bounded by
CSS reflow/paint and a handful of lightweight `Plotly.relayout` chrome
calls (2 per lane at most: one on creation, one more only for lanes whose
bottom-lane status actually changed), not by any new fetch latency. No
change to the six-channel parallel-fetch baseline already measured in the
Phase 2C-A/B1 records. Real browser rendering responsiveness and the
actual visual appearance (whether the six lanes genuinely read as "one
canvas" to a human eye) were **not** visually confirmed in this sandboxed,
no-real-browser session — see this task's own live DEV verification
section for the closest available substitute evidence, and the owner's
own manual UAT remains the authority on whether the visual goal was
actually achieved.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

---

## Phase 2C-B3 — Right-Side Compact Lane Labels Implementation Record (2026-08-15)

`[FACT]` throughout. A small, deliberately-scoped **visual refinement of
Separate mode's existing lane label only** — no panel/data model change,
no synchronization change, no backend change, no change to the unified
analog canvas container introduced by Phase 2C-B2. **Direct vertical
drag/reorder, drag-to-overlay/group, drag-out-to-separate, digital-channel
rendering, and lane resize are explicitly not started.**

### Phase 2C-B2 manual UAT result (recorded here, this pass)

The owner manually UAT'd the completed Phase 2C-B2 (unified analog canvas)
implementation and confirmed: **Separate view now feels much better; the
unified analog canvas direction is accepted.** The next refinement
requested was label placement: in Separate mode, the lane label should
appear as a small compact label tag on the RIGHT side, similar in
placement/feel to Detego — used only as a UI/layout reference (per the
Detego Benchmark Principle, DEC-020), never as a source of exact colors,
typography, icons, or component styling to copy.

### Right-side label refinement

The existing compact legend chip (Phase 2C-A's original "one channel per
lane" legend, unchanged markup pattern: colored dot + channel name + unit
+ remove button) moved from the lane's left edge to its right edge. In CSS
terms: `.ww-panel`'s grid column order flipped from `[108px label][1fr
chart]` to `[1fr chart][136px label]`, `.ww-chart-wrap` is now `grid-column:
1` (was 2) and `.ww-legend` is now `grid-column: 2` with `justify-self:
end` (was 1, left-aligned by default) so the tag hugs the lane's right
edge, matching the ASCII layout in this task's own §3
(`-------- waveform -------- [ TBIN1 VR ]`). **The waveform column keeps
maximum available width** — this did not regress; only which side gets
the fixed-width column changed, not its size relative to the chart.

### Visual treatment

The tag is now an explicit small pill (`border-radius: 999px`, a subtle
1px `var(--panel-border)` border, `var(--surface-tint)` background,
compact padding, `0.72rem` font) rather than the previous unstyled/
transparent text row — per this task's own §7 "subtle border or pill/tag
treatment if useful." Both colors are existing Oruxa theme tokens already
used elsewhere in this file (`--surface-tint` for the search-highlight/
group-header background, `--panel-border` for every existing hairline
divider) — **no Detego color, typography, or icon was copied**; the tag's
own CSS was re-verified this pass to have no inline style override, so
Light/Dark readability comes entirely from the same token system already
proven across the rest of the app (DEC-023). The tag has a `max-width`
(130px) so an unusually long channel identifier truncates with an
ellipsis (a new `.ww-legend-label` wrapping span, `text-overflow:
ellipsis`) rather than growing the label column or crowding the waveform
— the waveform retains visual priority, per this task's own §5/§7.

### Existing labels — simplified, not duplicated

No new redundant label was introduced. The per-lane `.ww-panel-header`
(Phase 2C-A's original panel title, already hidden in unified/Separate
mode since Phase 2C-B2 because it duplicated the legend chip's text) stays
hidden — there is still exactly **one** label treatment per lane, per this
task's own §6 ("prefer one clear primary label treatment"), it simply now
sits on the right instead of the left, and looks like a tag instead of
plain text.

### Interaction behavior — remove control preserved cleanly

The existing remove (×) control is unchanged and still sits inside the
tag — it fits the compact pill without crowding (verified directly: the
tag's flex layout is dot + `.ww-legend-label` (flexible, truncating) +
remove button (fixed size), so the remove control never needs to be
dropped or relocated). No tradeoff was needed here; no new interaction was
added beyond what already existed.

### Separate mode — unified analog canvas preserved

The Phase 2C-B2 outer canvas (`#wwPanels.ww-panels-unified`'s shared
background/border, the hairline lane dividers, the fixed-height compact
lanes, and `wwUpdateBottomLaneAxis()`'s bottom-lane-only shared time axis)
are **completely unchanged** by this pass — only the label column's side
and the tag's own styling moved. Verified via the full existing Phase
2C-B2 suite (20 checks), re-run unmodified, all still passing.

### Grouped mode — no regression

Grouped mode's own CSS is untouched (the unscoped `.ww-panel-header`/
`.ww-legend`/`.ww-legend-item` rules, used only when `ww-panels-unified`
is absent, were not touched at all this pass); `#wwPanels` never gains
`ww-panels-unified` while `ww.layoutMode === "grouped"`. Verified via the
full existing Phase 2C-A (19 checks) and Phase 2C-B1 (16 checks) suites,
re-run unmodified, all still passing.

### Functionality preserved

No change to: the waveform API contract (`channel_name`/`start_time`/
`end_time`/`point_budget`, confirmed by test), the shared X/time viewport
mechanism (DEC-021), relayout loop-prevention (`suppressNext`), theme
behavior (DEC-023), crosshair styling (`spikethickness: 0.35`,
`spikedash: "3px,2px"`), point-budget behavior (`WW_POINT_BUDGET = 4000`,
untouched), or source/workspace lifecycle (DEC-018). Verified directly:
zoom/pan still broadcast to all 6 lanes with exactly 6 relayout calls (no
loop) and 6 refetches; Reset Time View and Autoscale Y still work across
all 6 lanes; no per-lane modebar; theme switching still re-colors every
lane without a waveform refetch; switching Separate→Grouped→Separate
still preserves the exact zoomed viewport and all 6 displayed channels.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend, new: 16 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern) — covering this task's own
  §12 list: CSS-source checks that the chart/label columns swapped sides
  and the label tag is a compact pill; the DOM now wraps each tag's text
  in a `.ww-legend-label` span; displayed-channel identity is correct in
  each tag (channel name + unit); the remove control and color dot are
  preserved inside the tag; 6 lanes still render with the unified-canvas
  class; only the bottom lane still shows the shared X axis; Grouped mode
  still groups correctly and never applies the unified class; zoom/pan/
  Reset Time View/Autoscale Y/no-modebar all still work; theme switching
  re-colors without refetching and the tag has no inline color override;
  Grouped↔Separate still preserves viewport and displayed channels;
  removal via the tag's remove button still removes the whole lane; and
  the waveform query-parameter whitelist is unchanged.
- **Frontend, existing: the full Phase 2C-B2 (20), Phase 2C-B1 (16),
  Phase 2C-A (19), and Phase 1 (4) suites were all re-run unmodified
  against this pass's code and all still pass in full** — 59 existing
  checks, zero regressions. 75 total frontend checks this pass.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

### Honest limitation

This sandboxed session has no real browser. Whether the right-side tag
genuinely reads as compact/readable/low-clutter to a human eye — the
actual visual goal of this task — was **not** visually confirmed here;
only structural/CSS-source evidence (grid column order, pill styling
rules, DOM truncation target) was verified. Final visual-appearance
judgment remains the owner's own manual UAT, per this task's own §13.

---

## Phase 2C-B3A — Overlay Right-Side Lane Labels Implementation Record (2026-08-15)

`[FACT]` throughout. A corrective, deliberately-scoped **visual refinement
of Phase 2C-B3's label placement mechanism only** — no panel/data model
change, no synchronization change, no backend change, no change to the
unified analog canvas container introduced by Phase 2C-B2. **Direct
vertical drag/reorder, drag-to-overlay/group, drag-out-to-separate,
digital-channel rendering, and lane resize are explicitly not started.**

### Owner clarification (recorded here, this pass)

The Phase 2C-B3 right-side label pass was **not** the owner's intended
layout, even though it moved the label to the correct side. The owner
clarified explicitly:

- the label must be **overlaid ON the waveform lane itself**, not placed
  in a dedicated right-side layout column;
- it should follow **Detego's own separate-waveform label style as
  closely as practical** — for this specific placement treatment, Detego
  is the explicit layout benchmark, not just loose inspiration (a
  narrower, more literal application of the Detego Benchmark Principle,
  DEC-020, than earlier Phase 2C-B2/B3 passes used it for).

### Overlay label correction

The dedicated `108px`/`136px` fixed-width grid column Phase 2C-B3
introduced was removed entirely. `.ww-panel` (the lane element) is no
longer `display: grid` with two columns — it is a plain block with
`position: relative`, and `.ww-chart-wrap` fills its full width (the
chart area is no longer split). `.ww-legend` (the existing label element,
unchanged DOM/markup — dot + `.ww-legend-label` span + remove button) is
now `position: absolute`, pinned `right: 14px`, vertically centered
(`top: 50%; transform: translateY(-50%)`), with an explicit `z-index: 2`
so it visually floats on top of the chart rather than reserving its own
layout space next to it. `pointer-events: none` on the wrapper (re-enabled
on the pill itself via `pointer-events: auto`) keeps the small amount of
empty space around the compact tag from blocking chart hover/crosshair
interaction underneath it.

### Detego alignment

For this specific Separate-mode label placement, Detego's own compact
overlay-tag style (floating near the right edge of the waveform trace
itself, not in a side panel) was used as the direct layout benchmark, per
the owner's own explicit instruction (§4 of this task). What was
followed: the **placement** (overlaid on the trace, right-aligned,
roughly vertically centered) and the **compactness** (small pill, low
visual weight relative to the waveform). What was **not** copied: Detego's
color palette, typography, toolbar, branding, or icons — the tag's
background/border/text still use the same Oruxa theme tokens already
established (`--surface-tint`, `--panel-border`, `--text-dim`), unchanged
from Phase 2C-B3, and no Detego asset or code was inspected to build this
(per DEC-020's "independent implementation, not reverse engineering"
principle, unchanged).

### Interaction behavior — remove control preserved cleanly

No tradeoff was needed: the same remove (×) control that fit cleanly
inside the right-side-column tag in Phase 2C-B3 fits identically inside
the overlay tag now, since only the tag's *position* changed, not its
internal layout (dot + label + button, unchanged flex row).

### Separate mode — unified analog canvas preserved

Phase 2C-B2's outer canvas (`#wwPanels.ww-panels-unified`'s shared
background/border, hairline lane dividers, compact lane height) and
`wwUpdateBottomLaneAxis()`'s bottom-lane-only shared time axis are
**completely unchanged**. Verified via the full existing Phase 2C-B2 suite
(20 checks), re-run unmodified, all still passing. The lane's own Y axis
remains fully independent per lane — untouched by this pass, as it was
never part of the label-placement CSS.

### Grouped mode — no regression

Grouped mode's own CSS is untouched (the unscoped `.ww-panel-header`/
`.ww-legend`/`.ww-legend-item` rules, used only when `ww-panels-unified`
is absent, were not touched at all this pass); `#wwPanels` never gains
`ww-panels-unified` while `ww.layoutMode === "grouped"`. Verified via the
full existing Phase 2C-A (19 checks) and Phase 2C-B1 (16 checks) suites,
re-run unmodified, all still passing.

### Functionality preserved

No change to: the waveform API contract (`channel_name`/`start_time`/
`end_time`/`point_budget`, confirmed by test), point-budget behavior
(`WW_POINT_BUDGET = 4000`, untouched), zoom/pan synchronization (DEC-021),
relayout loop-prevention (`suppressNext`), Reset Time View, Autoscale Y,
theme switching behavior (DEC-023), crosshair styling (`spikethickness:
0.35`, `spikedash: "3px,2px"`), or source/workspace lifecycle (DEC-018).
Verified directly: zoom/pan still broadcast to all 6 lanes with exactly 6
relayout calls (no loop) and 6 refetches; Reset Time View and Autoscale Y
still work across all 6 lanes; no per-lane modebar; theme switching still
re-colors every lane without a waveform refetch; switching
Separate→Grouped→Separate still preserves the exact zoomed viewport and
all 6 displayed channels.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched.
- **Frontend, new: 17 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern) — covering this task's own
  §12 list: CSS-source checks confirming the label uses absolute
  positioning against a relatively-positioned lane (not a grid column),
  is pinned near the right edge and vertically centered, and sits above
  the chart via z-index; the lane's chart area is no longer split into two
  columns; the overlay label's DOM parent is the lane element itself (a
  sibling of the chart-wrap within the same lane, not a separate layout
  block); displayed-channel identity is correct; Separate mode still
  shows exactly one lane per channel with the unified-canvas class intact;
  only the bottom lane still shows the shared X axis; Grouped mode still
  groups correctly and never applies the unified/overlay CSS; zoom/pan/
  Reset Time View/Autoscale Y/no-modebar/theme-switching all still work;
  Grouped↔Separate still preserves viewport and displayed channels;
  removal via the overlay tag's remove button still removes the whole
  lane; the waveform query-parameter whitelist is unchanged.
- **Frontend, updated in place: 2 of Phase 2C-B3's own CSS-source
  assertions** (which specifically tested the now-removed grid-column
  mechanism) were corrected to assert the new overlay mechanism instead —
  the remaining 14 of its 16 checks needed no change and continued to pass
  unmodified throughout, confirming this pass is a placement-mechanism
  correction, not a functional regression. **Frontend, existing: the full
  Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4)
  suites were all re-run unmodified against this pass's code and all
  still pass in full** — 59 existing checks, zero regressions. 92 total
  frontend checks this pass (17 new + 16 corrected-B3 + 59 unmodified
  regression).

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

### Honest limitation

This sandboxed session has no real browser. Whether the overlay tag
genuinely reads as a Detego-style floating label rather than a dedicated
side panel to a human eye — the actual visual goal of this task — was
**not** visually confirmed here; only structural/CSS-source evidence
(absolute positioning, z-index stacking, right/top offsets, single-lane
DOM parentage) was verified. Final visual-appearance judgment remains the
owner's own manual UAT, per this task's own §13.

---

## Phase 2C-C1 — Custom Analog Channel Groups Implementation Record (2026-08-15)

`[FACT]` throughout except where explicitly marked `[DECISION]` (DEC-027).
Adds the third and final grouping mode the Phase 2C design record's own
§9/§3 left open ("Custom" — Detego's own third grouping mode — was
explicitly deferred at both Phase 2C-A and Phase 2C-B1). **Direct
vertical drag/reorder, drag-to-overlay/group by direct lane dragging,
digital-channel rendering, lane resize, and backend persistence remain
explicitly not started.**

### Owner direction (recorded here, this pass)

The owner explicitly chose to **skip vertical lane drag/reorder for now**
— the previously-stated "owner's own next direction" from every prior
Phase 2C-B record — and instead requested **Custom Groups**: manual,
user-controlled decisions about which displayed analog channels share a
waveform panel, with Detego's own "Edit Channel Groups" workflow as the
explicit reference (a workflow/layout benchmark only, per the Detego
Benchmark Principle, DEC-020 — no Detego branding/colors/icons copied).

### Layout modes

`[ Grouped ] [ Separate ] [ Custom ]` — a third button added to the
existing toolbar toggle. Grouped and Separate are byte-for-byte unchanged
from Phase 2C-A/B1/B2/B3A. Custom is new: the user decides channel
membership directly, via a new **Edit Channel Groups** dialog (visible
only while Custom is the active mode — parallels how the whole toolbar
itself is hidden when nothing is displayed).

### Custom group workflow

1. Displayed analog channels exist (any mode).
2. User clicks **Custom** — with no custom grouping defined yet, this
   renders one panel per channel (the documented auto-solo rule, see
   below) so Custom is never an empty or broken state on first entry.
3. User clicks **Edit Channel Groups**, opening a modal (Oruxa styling
   throughout — `.confirm-overlay` backdrop reused from the app's existing
   one-and-only prior modal pattern, no Detego palette/typography/icons).
4. The modal shows an **Unassigned channels** list (compact chips, each
   with a `<select>` "Add to group…" control) and a **Groups** section
   (`+ Add group` button; each group is a card with an editable name
   input, a delete-group button, and a chip list of its assigned
   channels, each removable with a small ×).
5. **Apply** commits the working copy into the workspace and switches to/
   stays on Custom mode; **Cancel** (or the × close button, Escape, or a
   backdrop click) discards all changes to the working copy, leaving
   whatever grouping was already active completely untouched.

Editing happens entirely in an in-memory working copy
(`groupEditorState`), never touching the real `ww.customGroups` until
Apply — this is why Cancel/close/Escape/backdrop-click all correctly
"preserve previous grouping" with zero extra bookkeeping: there is
nothing to undo, since the real state was never written to.

**No drag-and-drop was implemented inside the modal** (per this task's
own §6, "do NOT require drag-and-drop unless genuinely simple") — moving
a channel between two existing groups is a two-step action (remove it
from its current group, which returns it to Unassigned, then assign it
via the `<select>`) rather than one direct drag. This is a deliberate,
honestly-reported first-slice tradeoff, not an oversight.

### Group assignment rule `[DECISION]` (part of DEC-027)

Per this task's own §7, one of two options had to be chosen and
documented. **Chosen: any unassigned channel automatically becomes its
own single-channel panel** — there is no third "unplaced, no panel" state,
and Apply is never blocked waiting for full assignment. Reasoning: this
keeps the first entry into Custom mode immediately usable (every
displayed channel is visible in *some* panel from the moment Custom is
selected, before the user has edited anything), matches the same
principle Separate mode already established (every channel always gets a
panel), and avoids validation-error UX entirely. The alternative
(require every channel to be explicitly placed before Apply) was
considered and rejected as unnecessary first-slice friction with no
compensating benefit — an unassigned channel isn't wrong, it's simply not
grouped with anything yet.

### Rendering behavior

Each custom group becomes one waveform panel via the same
`wwCreatePanelObject`/`wwCreatePanelDom`/`wwBuildLayout`/`wwInitPanelPlot`
machinery every other layout mode already uses — **zero changes were
needed to any of those functions**, since a Custom-mode panel is
structurally identical to a Grouped-mode panel (one or more channel
traces, one shared Y axis... independent per panel, one legend row
listing every member channel). The only new logic is in
`wwPanelGroupKeyFor`/`wwPanelLabelFor` (a "custom" branch: look up which
`ww.customGroups` entry currently claims the channel, or fall back to a
uniquely-prefixed solo key) and a new `wwCustomGroupFor()` lookup helper.
`wwRebuildLayout()` itself — already proven by Phase 2C-B1/B2/B3A to
correctly re-derive panels from a flat channel list under whichever mode
is active — needed **no changes at all** to support Custom mode; this is
exactly the payoff of that architecture decision. `#wwPanels` never gains
the Separate-only `ww-panels-unified` class in Custom mode (per this
task's own §8, "Custom may visually resemble Grouped mode in panel
structure" — confirmed and implemented exactly that way, since a
multi-channel panel doesn't fit the single-channel-lane overlay
treatment Phase 2C-B2/B3A built specifically for Separate).

### Viewport preservation

Verified directly (not just asserted): zooming to a specific window,
then opening Edit Channel Groups and clicking Apply, produces the new
panels with `layout.xaxis.range` already set to that exact same window.
No special-case code was needed — `wwApplyGroupEditor()` calls the same
`wwRebuildLayout()` every other mode switch already relies on, which
reads the current `ww.viewport` for each new panel's initial X range and
never touches `ww.viewport` itself.

### Custom grouping persistence within the session

Per this task's own §9 ("prefer yes, if simple and safe"): **switching
away from Custom and back restores the last-applied custom grouping**,
verified directly (zoom → Apply a 3-group layout → switch to Separate →
switch back to Custom → the same 3 groups reappear, not a fresh
all-solo layout). `ww.customGroups` is workspace-session state,
independent of which mode is currently active — it is only reset by a
whole-workspace operation (`wwClearWorkspace()`, i.e. "Clear workspace" /
"Start new workspace"), matching how `ww.viewport`/`ww.recordBounds` are
already reset there. Individual channel/source removal deliberately does
**not** scrub stale channel keys out of `ww.customGroups` — a channel
re-added later (same source, same channel name, same session) naturally
rejoins its old group with zero extra code, a harmless and arguably
pleasant side effect of not over-engineering cleanup that was never
required.

### Existing modes preserved

Grouped and Separate are unchanged — verified via the full existing Phase
2C-A (19 checks), Phase 2C-B1 (16 checks), Phase 2C-B2 (20 checks), Phase
2C-B3 (16 checks, 2 already-corrected-in-place assertions from the prior
pass), and Phase 2C-B3A (17 checks) suites, all re-run unmodified against
this pass's code and all still passing. Switching between all three modes
(Grouped/Separate/Custom, in any order) preserves the displayed channel
set, verified directly.

### Functionality preserved

No change to: the waveform API contract (`channel_name`/`start_time`/
`end_time`/`point_budget`, confirmed by test), point-budget behavior
(`WW_POINT_BUDGET = 4000`, untouched), the shared X/time viewport
mechanism (DEC-021), relayout loop-prevention (`suppressNext`), Reset
Time View, Autoscale Y, theme switching (DEC-023), crosshair styling
(DEC-022/023, untouched), or source/workspace lifecycle (DEC-018).
Verified directly: zooming one panel in Custom mode broadcasts to every
resulting panel with no relayout loop and one refetch per *channel*
(same policy as every prior mode — panel count doesn't change the
per-channel request policy); Reset Time View and Autoscale Y both work
across custom groups; no per-panel native Plotly modebar; theme switching
re-colors every custom-group panel without a waveform refetch.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched; no backend change was needed for this slice (frontend/state-
  only, per this task's own §11 preference).
- **Frontend, new: 30 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern) — covering this task's own
  §13 list: the Custom button and Edit Channel Groups control appear
  correctly; switching to Custom with no groups yet produces one panel
  per channel (auto-solo); the modal opens/closes (Cancel, reopen);
  groups can be created (Group 1/2/3); channels can be assigned via the
  Unassigned select and removed from a group back to Unassigned; an empty
  group can be deleted; Apply renders the exact example grouping from
  this task's own §14 (Group 1 = VA/VB/VC, Group 2 = IA/IB, IC
  auto-solo); the pre-Apply zoomed viewport survives Apply exactly;
  zoom/pan-equivalent synchronization, Reset Time View, Autoscale Y, and
  no-per-panel-modebar all work in Custom mode; switching Custom→
  Separate→Custom preserves displayed channels AND restores the
  last-applied grouping; Grouped mode still groups by engineering_type
  with zero regression; theme switching still works in Custom mode; Clear
  workspace resets both the display and the remembered custom grouping
  (verified behaviorally, by re-adding the same channel keys and
  confirming they come back auto-solo rather than pre-grouped); and the
  waveform query-parameter whitelist is unchanged.
- **Frontend, existing: the full Phase 2C-B3A (17), Phase 2C-B3 (16),
  Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4)
  suites were all re-run unmodified against this pass's code and all
  still pass in full** — 92 existing checks, zero regressions. 122 total
  frontend checks this pass.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

### Honest limitation

This sandboxed session has no real browser. Whether the group editor
modal's workflow genuinely feels clear/engineering-focused, and whether
the resulting Custom-mode panels read correctly to a human eye, was
**not** visually confirmed here; only structural/behavioral evidence
(jsdom DOM assertions, API-level live-DEV checks) was verified. Final
appearance/workflow judgment remains the owner's own manual UAT, per this
task's own §14.

---

## Phase 2C-C2 — Adjustable Waveform Panel Heights Implementation Record (2026-08-15)

`[FACT]` throughout except where explicitly marked `[DECISION]` (DEC-028).
Adds independent vertical resizing to every waveform panel/lane, in all
three analog layout modes. **Digital-channel rendering, lane drag/
reorder, drag-to-group, and backend layout persistence remain explicitly
not started.**

### Owner direction (recorded here, this pass)

The owner completed manual UAT of Phase 2C-C1 (Custom Groups):
**PASSED** — "the Custom Groups workflow is smooth and easy to
understand." Before moving on to digital channels, the owner requested
one more analog-workspace refinement: every waveform panel/lane should be
vertically resizable by dragging, across all three layout modes
(Grouped/Separate/Custom), with **Detego's vertical panel-resize
interaction named as the explicit UX benchmark** — placement/feel only,
per the Detego Benchmark Principle (DEC-020); no Detego branding, colors,
icons, or implementation copied.

### Resize interaction

A thin horizontal handle sits at the bottom of every panel's chart, in
every layout mode (the CSS rule is deliberately unscoped to any one
mode's container class). The handle's hit area is 8px tall and spans the
panel's full content width — comfortable to acquire without needing a
large visible bar — while the visible affordance is a small centered
32px pill using existing theme tokens (`--panel-border` at rest,
`--accent` and a wider 48px on hover/active-drag). `cursor: ns-resize`
signals vertical resizing. The handle sits entirely **below** the chart
area with zero overlap into the plotting region, so it never intercepts
Plotly hover/crosshair outside its own small strip (this task's own
§4 requirement).

Dragging is implemented with native **Pointer Events** and **Pointer
Capture** (`setPointerCapture` on `pointerdown`) — once captured, the
same handle element keeps receiving `pointermove`/`pointerup` even if the
pointer strays outside the handle's narrow bounds mid-drag (this task's
own §17 requirement), and no `document`-level listeners are ever
attached — move/up handlers are added on `pointerdown` and always removed
on `pointerup`/`pointercancel`, so there is nothing that can leak.
Resizing is **continuous, not deferred to mouse-up** — every `pointermove`
updates the panel's height live — but raw pointer events are coalesced
through `requestAnimationFrame` (at most one applied height + one
`Plotly.Plots.resize()` call per animation frame, regardless of how many
raw events fire in that frame) to keep the drag responsive without
issuing excessive expensive Plotly operations (§18).

### Height constraints `[DECISION]` (part of DEC-028)

- **Minimum: 100px.** `wwBuildLayout()`'s own fixed top/bottom margins
  (`t: 10, b: 34`) already consume 44px of any panel regardless of its
  height, so a floor much below 100px would leave little to no visible
  plot area — exactly the "unusable strip" this task's own §6 warns
  against. 100px leaves roughly 56px of genuine plotting area at the
  floor, still small but usable, and sits inside the task's own suggested
  ~80–100px range after inspecting the existing lane design (Separate
  mode's own pre-existing default is 140px; a much smaller floor than
  100 would feel disproportionate against that baseline).
- **Maximum: 600px.** Not a hard product requirement — a deliberate,
  generous upper bound (~2.3× the largest existing default, Grouped's
  260px) chosen purely to prevent a pathological single-panel height from
  breaking page layout, per this task's own §6 ("prevent pathological
  dimensions or obvious browser/UI breakage" when no maximum is
  mandated).
- **Defaults, per layout mode**: Grouped 260px, Custom 260px, Separate
  140px — exactly each mode's own pre-existing fixed CSS height before
  this phase, so a brand-new panel's first paint is visually unchanged
  from before Phase 2C-C2; only an explicitly-dragged panel ever departs
  from its mode's default.

### Grouped mode

A Grouped panel (e.g. Voltage: VA/VB/VC) is resized as one visual unit —
dragging its handle changes the height available to the whole panel
(and therefore every trace inside it), never resizing individual traces
independently, exactly as this task's own §10 requires. No code
distinguishes "how many traces are in this panel" when resizing — the
height applies to `panel.chartEl` itself, which is what Plotly renders
every trace of that panel into.

### Separate mode

Each of the (up to six, tested) lanes resizes independently. **The
unified analog canvas is fully preserved**: the shared outer frame,
subtle hairline lane dividers, and — critically — the overlay right-side
label are all untouched by this phase; the label remains an absolutely-
positioned child of its own lane regardless of that lane's height
(verified directly, not just asserted, since the label's CSS position
is `top`/`right`-anchored to its own `.ww-panel`, not the chart's pixel
dimensions). **The true current bottom lane is still the only lane
showing the shared X/time axis after arbitrary resizing** — resizing
never changes panel order or count, so `wwUpdateBottomLaneAxis()`'s own
"last panel in `ww.panels`' order" logic (unchanged from Phase 2C-B2)
continues to identify the correct lane regardless of any lane's height,
verified directly.

### Custom mode

Each Custom group's panel resizes independently, exactly like a Grouped
panel (a Custom panel can hold multiple channels, the same shape as
Grouped — see DEC-026's already-established reasoning for why Custom
never uses Separate's single-channel overlay/unified treatment).
**Resizing never touches group membership** — verified directly: a
2-channel custom group's panel still lists exactly its own 2 channels
after being dragged to a different height. The Custom Groups editing
workflow itself (Edit Channel Groups modal, Apply/Cancel, the
group-assignment rule) is completely untouched by this phase, per this
task's own explicit "do NOT alter the group-editing workflow" instruction.

### State behavior across mode switches `[DECISION]` (part of DEC-028)

Panel height is explicit application state (`ww.panelHeights`, a
`Map<groupKey, heightPx>`), never read from the rendered DOM as the
source of truth (`panel.height`, a plain JS property, is what every
resize operation reads/writes; the DOM's inline `style.height` is only
ever a reflection of it, applied by `wwSetPanelHeight()`). The key is the
**same `groupKey` `wwPanelGroupKeyFor()` already computes** for panel
derivation itself (Phase 2C-B1's own architecture) — no new "stable
panel identity" concept was invented, per this task's own §13 guidance
to use the identity that already exists.

This single, mode-agnostic mechanism produces exactly the documented,
desired behavior with zero per-mode special-casing:

- A Grouped "Voltage" panel's height, a Separate "`src::VA`" lane's
  height, and a Custom "`custom:cg1`" group's height never collide —
  different key namespaces (verified: Separate → Grouped → Separate does
  **not** carry VA's Separate height onto the Grouped Voltage panel).
- Separate → Grouped → Separate **does** restore VA's own previously-
  dragged Separate height, because `"src::VA"` is the identical key both
  times — verified directly.
- Custom → Grouped → Custom similarly restores a custom group's own
  dragged height, because a Custom group's `id` (and therefore its
  `groupKey`) is itself already session-stable state (`ww.customGroups`,
  Phase 2C-C1) — verified directly.
- A brand-new panel (a groupKey never seen before) always receives its
  mode's sensible default height — no complicated cross-mode height
  mapping was built, matching this task's own explicit "do not invent
  complicated cross-mode height mapping" instruction.

### Workspace/session persistence

Panel heights persist only in memory for the current browser
tab/workspace (`ww.panelHeights`), matching this task's own explicit "do
NOT add database/backend persistence" instruction and the project's
existing ephemeral-by-design principle (DEC-015). No `localStorage`/
`sessionStorage` persistence was added either — judged unnecessary
first-slice scope per this task's own "do not overengineer" guidance;
this can be revisited later if the owner finds losing custom heights on
a full page reload undesirable.

Removing an individual channel/panel **deliberately does not** scrub its
entry out of `ww.panelHeights` — the exact same policy, and the exact
same reasoning, Phase 2C-C1 already established for `ww.customGroups`
(a channel/group re-added later within the same session naturally
regains its old height, a harmless, arguably pleasant side effect of not
over-engineering cleanup that was never required). A **whole-workspace
reset** ("Clear workspace"/"Start new workspace") **does** clear
`ww.panelHeights` entirely, alongside the already-existing reset of
`ww.customGroups`/`ww.viewport`/`ww.recordBounds` — verified directly.

### Plotly behavior

Resizing calls **`Plotly.Plots.resize(panel.chartEl)`** exclusively — the
supported, minimal, documented Plotly API for "the container's size
changed, redraw to fit it." It does not touch trace data, the X/time
range, or the Y range, so switching a panel's height never resets the
zoomed viewport and never issues a waveform refetch. **Verified directly
by test, not merely asserted**: fetch-call counts before and after a full
resize drag sequence (multiple pointer moves, both directions, across
Grouped/Separate/Custom) are identical. No `Plotly.newPlot`/`Plotly.react`
call is ever made for a resize — the existing plot instance is reused in
place.

### Synchronization

DEC-021 is fully preserved. Resizing never touches `ww.viewport`, never
calls `wwBroadcastViewportDebounced`/`wwApplyAndFetchViewport`, and never
sets/clears any panel's `suppressNext` flag — a completely disjoint code
path from the shared-viewport mechanism. Verified directly, after
resizing panels to arbitrary/mixed heights in every mode: zooming any one
panel still broadcasts to every other panel with exactly the expected
number of relayout calls (no runaway loop) and exactly one waveform
refetch per displayed **channel** (not per panel — unchanged policy);
Reset Time View still restores the full record range on every panel.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched; no backend change was needed (frontend/state-only, matching
  this task's own preference).
- **Frontend, new: 23 scripted `jsdom` checks, all passing** (a new
  one-off script, same established pattern, using jsdom's real
  `PointerEvent` constructor plus a `requestAnimationFrame`/
  `cancelAnimationFrame` polyfill jsdom itself doesn't provide) —
  covering this task's own §20 list: a resize handle exists on every
  panel in Grouped/Separate/Custom; a Grouped panel resizes and an
  unrelated Grouped panel is untouched; minimum (100px) and maximum
  (600px) clamping both enforced under extreme drags; `Plotly.Plots.resize`
  is called during a drag; resizing issues zero waveform fetches;
  zoom/Reset-Time-View synchronization still works correctly after
  resizing; Separate lanes resize independently while the overlay label
  stays a correctly-positioned child of its own lane and the true bottom
  lane still (and only it) shows the shared X axis; a Custom group panel
  resizes independently with membership unchanged; height state
  round-trips correctly across Custom→Grouped→Custom and
  Separate→Grouped→Separate (including cross-mode non-collision);
  Grouped/Separate/Custom keep working; theme switching remains correct
  at custom heights without a refetch; removing then re-adding a channel
  restores its remembered height (not scrubbed); Clear workspace resets
  remembered heights entirely; and the waveform query-parameter whitelist
  is unchanged.
- **Frontend, existing: the full Phase 2C-C1 (30), Phase 2C-B3A (17),
  Phase 2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19),
  and Phase 1 (4) suites were all re-run unmodified against this pass's
  code and all still pass in full** — 122 existing checks, zero
  regressions. 145 total frontend checks this pass.

### Performance

Structural evidence only (this sandboxed session has no real browser):
the rAF-coalescing mechanism guarantees at most one `Plotly.Plots.resize()`
call per animation frame per actively-dragged panel, regardless of raw
pointermove event frequency — verified by test that a multi-move drag
sequence still produces the correct final state without runaway resize
calls. Exercised structurally at 2 Grouped panels, 6 Separate lanes, and
a mixed Custom-group layout, per this task's own §18 guidance; no
per-scenario slowdown was observed in the (non-visual) jsdom checks, and
no additional dependency was added for the resize mechanism (native
Pointer Events + `requestAnimationFrame` only).

### Accessibility

The handle has `role="separator"`, `aria-orientation="horizontal"`, and a
descriptive `aria-label` ("Resize *panel name* panel height"). **Honest
limitation, documented per this task's own §19**: keyboard resizing was
**not** implemented this slice (`tabindex="-1"`, not in the tab order) —
this task's own instructions explicitly mark keyboard support as
desirable long-term but not required now "unless trivial," and it was
judged non-trivial to do correctly (a real keyboard-resize interaction
needs its own value/step semantics, likely `role="slider"` with
`aria-valuenow`/`min`/`max`, which is a meaningfully larger scope than
this slice's pointer-drag-only requirement). A future slice can add it
without restructuring anything built here.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

### Honest limitation

This sandboxed session has no real browser. Whether the drag interaction
itself feels direct/discoverable/subtle to a human hand on a real
pointing device — the actual tactile UX goal of this task — was **not**
confirmed here; only structural/behavioral evidence (jsdom DOM/state
assertions using synthetic PointerEvents, since jsdom implements neither
element-level Pointer Capture nor `requestAnimationFrame` natively) was
verified. Final tactile/visual UAT remains the owner's own, per this
task's own §21.

---

## Phase 2C-C2A — Panel Resize Responsiveness Investigation (2026-08-15)

`[FACT]` throughout. An investigation-first task into a specific
owner-observed performance characteristic of Phase 2C-C2 (adjustable
panel heights), resulting in one small, low-risk refinement. **Digital
channels, lane reorder, drag-to-group, and every other Phase 2C-C2
scope exclusion remain untouched by this pass.**

### Owner UAT baseline (Phase 2C-C2)

The owner's manual UAT of Phase 2C-C2 **passed functionally**: resize
works correctly in Grouped, Separate, and Custom modes; the resize
handle feels natural enough; the 100px minimum and 600px maximum are
both accepted as-is (**unchanged by this pass**). The owner separately
**observed** that during live dragging, the waveform does not visually
follow the panel resize immediately — a delay of perhaps a few hundred
milliseconds, judged bearable, with a preference for better
responsiveness only if the fix is low-cost and low-risk.

### Investigation — current resize path

Traced exactly, by direct code reading (`wwWireResizeHandle`/
`wwSetPanelHeight` as shipped in Phase 2C-C2): every `pointermove`
computed a pending height and scheduled (at most one) `requestAnimation
Frame` callback; that callback's ONLY job was `wwSetPanelHeight()`, which
performed BOTH the cheap DOM step (clamp, store, `panel.chartEl.style.
height = ...px`) AND the expensive step (`Plotly.Plots.resize(panel.
chartEl)`) as two synchronous statements inside the same function call.

### Bottleneck

**The two steps being bundled inside one synchronous rAF callback is the
bottleneck** — not `requestAnimationFrame` scheduling itself (a
near-zero-cost browser primitive), not excessive Plotly call counts (already
correctly coalesced to at most once per frame), and not any redundant
legend/axis/layout work (confirmed by code inspection: `wwSetPanelHeight`
calls nothing beyond the clamp/store/style-write and
`Plotly.Plots.resize()` — no `wwRenderLegend`, `wwBuildLayout`, or
`wwUpdateBottomLaneAxis` call anywhere in the resize path). A browser
cannot paint a DOM change until the current synchronous unit of JavaScript
returns control to it. Because the cheap height write and the expensive
Plotly redraw were both inside the SAME synchronous callback, the
browser's paint of the panel's new box size was gated on Plotly's own
(potentially tens-of-milliseconds) redraw finishing first, every single
animation frame during a drag — exactly the "wait for Plotly before the
box visually follows" pattern this task's own §7 asked to check for, and
exactly what produces the observed lag.

**Investigation questions A–I, answered directly**:
- A (pointer → state/height calc): trivial, O(1) arithmetic, not a
  contributor.
- B (state → CSS height write): a bare `style.height` write; does not by
  itself force synchronous layout (only reading a layout-dependent
  property like `getBoundingClientRect()` would) — not a contributor on
  its own.
- C (CSS write → layout/reflow): the write itself is lazy/batched by the
  browser; the actual forced-layout cost is triggered by Plotly's own
  internal work when it reads the container's computed size, not by our
  write.
- D/E (`Plotly.Plots.resize()` execution / SVG/WebGL redraw): the
  confirmed bottleneck — real cost, inherent to redrawing a chart's axes/
  traces at a new size, and outside this codebase's control.
- F (rAF scheduling cost): negligible; not a contributor.
- G (unnecessary resize of other panels): **not present** — confirmed by
  code inspection, `wwSetPanelHeight`/`wwResizePanelPlot` only ever
  operate on the single `panel` argument passed to them; there is no loop
  over `ww.panels` anywhere in the resize path.
- H (expensive axis/legend/layout work triggered per frame): none beyond
  what `Plotly.Plots.resize()` itself inherently does (recomputing axis
  tick layout for the new size is part of "resize," not an avoidable
  extra cost stacked on top).
- I (cost vs. panel count — 2 Grouped / 6 Separate / 3 Custom): **cost is
  independent of total panel count**, confirmed structurally — each
  panel's resize handle is wired with its own closured state
  (`wwWireResizeHandle(panel)`), and a drag on one panel's handle only
  ever calls `wwResizePanelPlot`/`wwSetPanelHeightImmediate` on that same
  panel object, regardless of how many other panels exist.

### Measurements

**This sandbox has no real browser** (no Chromium/Chrome-CLI binary, and
installing Playwright/Puppeteer was judged disproportionate for a
one-off diagnostic — a new heavy dependency footprint for a single
investigation). Real frame-paint timing, actual `Plotly.Plots.resize()`
millisecond cost on real chart data, and genuine tactile "does it feel
smoother" evidence **cannot** be produced here and remain for owner
manual UAT, exactly as this task's own §11/§16 anticipates.

What **was** measured, precisely, with jsdom + a simulated-cost Plotly
mock (`resize_lag_measure.mjs`, scratch instrumentation, not committed):
using a synchronous "busy-wait" mock standing in for `Plotly.Plots.
resize()`'s real cost (tested at 0ms, 20ms, and 50ms simulated cost) and
an external poller observing exactly when `panel.chartEl.style.height`
became externally observable relative to the mock's own start/end
timestamps (`performance.now()`), across a simulated 5-move drag
gesture:

- **Before this pass's fix**: every observed DOM height-write timestamp
  was numerically identical (within measurement noise) to that same
  cycle's Plotly-resize-**end** timestamp — e.g. write at 22.3ms vs.
  Plotly end at 22.3ms; write at 45.1ms vs. Plotly end at 45.0ms. The
  height change was never externally observable until Plotly's
  (simulated) work had already finished.
- **After this pass's fix**: the same measurement showed the height
  write becoming observable measurably *before* the corresponding
  Plotly resize call even *started* (e.g. write at 23.7ms vs. Plotly
  start at 24.9ms), consistently across all three simulated cost levels,
  with the gap holding steady (~1.2–1.3ms, the minimal JS-scheduling
  overhead between the pointermove handler and the next macrotask) — a
  structural proof that the DOM change is decoupled from Plotly's work,
  not proof of a specific real-world millisecond improvement.
- Plotly resize call counts were identical before/after (6 calls for a
  5-move-plus-pointerup drag in the measurement script) — confirming the
  fix does not increase how often the expensive operation runs.
- Network requests: **zero**, before and after, confirmed by the existing
  and new test suites (see Tests below) — resizing remains
  presentation-only.

### Options evaluated

- **Option A** (immediate container height, decoupled/coalesced Plotly
  call): this is what was implemented — see Decision below.
- **Option B** (rAF only for the expensive Plotly call, cheap state/DOM
  immediate): functionally the same mechanism as Option A for this
  codebase's specific structure; implemented.
- **Option C** (continuous height + controlled-cadence Plotly + one final
  resize on pointerup): considered and rejected as unnecessary
  additional complexity — Option A/B's simple "immediate write, rAF-
  coalesced Plotly call, authoritative final write on pointerup" already
  achieves the same practical effect (Plotly redraws at most once per
  frame during the drag, plus one guaranteed-correct final call) without
  introducing a separate cadence/timer concept.
- **Option D** (a more appropriate Plotly resize/relayout API): none
  found — `Plotly.Plots.resize()` is already the correct, minimal,
  official API for "container size changed, redraw to fit it"; no
  Plotly-internal manipulation was considered or used.

### Decision

**A. LOW-COST REFINEMENT JUSTIFIED.** Checked against every bullet of
this task's own §6 cost/benefit rule: the change is small and
understandable (splitting one function into an immediate cheap half and
a coalesced expensive half, ~15 lines net); no custom rendering engine;
no brittle Plotly internals (still only the same official
`Plotly.Plots.resize()` call, same call sites conceptually); no
synchronization regression (the shared-viewport/zoom/pan mechanism is
untouched — resizing was and remains a fully disjoint code path); no
waveform refetch (confirmed zero, before and after); no additional state
complexity of consequence (one existing function split into two, no new
state field); and a likely meaningful improvement to perceived
responsiveness, since removing an expensive synchronous call from the
browser's per-frame paint-blocking path is a well-established technique
for exactly this class of problem — confirmed structurally here (not
merely asserted) via the decoupling measurement above.

### Implementation

`wwSetPanelHeight(panel, height)` (the original, doing both the cheap
write and the expensive Plotly call together) was split into:

- **`wwSetPanelHeightImmediate(panel, height)`** — clamp, store
  `panel.height`, write `panel.chartEl.style.height`, update
  `ww.panelHeights`. No Plotly call. Now invoked on **every** raw
  `pointermove`, not gated behind `requestAnimationFrame` at all (safe:
  a bare style write does not itself force synchronous layout).
- **`wwResizePanelPlot(panel)`** — the `Plotly.Plots.resize()` call only,
  with the same `panel.plotlyReady` guard as before. Still invoked from
  inside the `requestAnimationFrame` callback, still coalesced to at
  most once per animation frame regardless of how many raw pointermoves
  land inside that frame — **identical coalescing behavior to Phase
  2C-C2**, confirmed by test (Plotly call counts unchanged).
- **`wwSetPanelHeight(panel, height)`** — retained as the combination of
  both, used only for the authoritative final write on `pointerup`/
  `pointercancel` (unchanged from Phase 2C-C2: guarantees the committed
  height and the Plotly-rendered content exactly match where the pointer
  ended, regardless of whether the last scheduled frame had already run).

`wwWireResizeHandle()`'s `onPointerMove` now calls
`wwSetPanelHeightImmediate()` directly (every move) and separately
schedules `wwResizePanelPlot()` via `requestAnimationFrame` (still at
most once per frame) — replacing the old `pendingHeight` variable/
`flush()` pattern, which no longer needs to track a pending height value
at all since the DOM write already happened synchronously; the scheduled
callback's only remaining job is "resize Plotly once."

**Preserved exactly, unchanged**: the 100px minimum / 600px maximum
clamping (still applied inside `wwClampPanelHeight`, called from the same
place); independent per-panel sizing (still one closured handler per
panel, still only ever touches its own panel); Grouped/Separate/Custom
mode behavior; the panel-height state model (`ww.panelHeights`, keyed by
`groupKey`); zoom/pan synchronization, shared viewport, Reset Time View,
Autoscale Y, theme behavior, crosshair, overlay labels, and Custom
Groups behavior — none of these functions were touched at all. The
waveform API and point-budget logic are untouched; no backend file was
modified.

### Zero-refetch verification

Confirmed by test, before and after: a full resize drag (single-panel
and multi-move variants) issues **zero** `/waveform` requests. This was
true before this pass and remains true after — resizing (in both its
old and new internal structure) never calls any of the fetch-issuing
functions (`wwFetchChannelRange`/`wwLoadChannelRange`/
`wwApplyAndFetchViewport`).

### Synchronization regression

**None.** The shared-viewport broadcast mechanism (`wwWirePanelRelayout`,
`wwBroadcastViewportDebounced`, `panel.suppressNext`) is a completely
separate code path from the resize handle's own pointer-event wiring;
neither `wwSetPanelHeightImmediate` nor `wwResizePanelPlot` reads or
writes `ww.viewport` or any panel's `suppressNext` flag. Verified
directly by the full existing Phase 2C-C2 suite (which includes explicit
"zoom/pan after resizing still synchronizes correctly" checks),
re-run unmodified against the patched code and still passing in full.

### Tests

- **Backend: 278 tests, unmodified, all passing** — zero backend files
  touched; no backend change was needed or made.
- **Frontend, new: 9 scripted `jsdom` checks, all passing**
  (`phase2cc2a_check.mjs`, a new one-off script, same established
  pattern) — covering this task's own §10 list specific to what changed:
  the DOM height write is now observable synchronously on every raw
  `pointermove` (not gated behind a tick/rAF wait); `Plotly.Plots.resize`
  remains coalesced (far fewer calls than raw pointermoves, not 1:1);
  the final Plotly resize call is always against the exact final
  committed height; `pointercancel` performs exactly one final resize
  and leaves no stale/late rAF-driven resize call; a subsequent drag
  after a cancelled one still works correctly; the 100px minimum and
  600px maximum are both still enforced, applied synchronously on the
  move itself; only the dragged panel is ever resized; and a full drag
  still causes zero waveform fetches.
- **Frontend, existing: the full Phase 2C-C2 (23), Phase 2C-C1 (30),
  Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1
  (16), Phase 2C-A (19), and Phase 1 (4) suites were all re-run
  unmodified against this pass's code and all still pass in full** —
  145 existing checks, zero regressions. 154 total frontend checks this
  pass.

### Files changed

Modified only: `frontend/index.html`. No new files, no `backend/` file,
no CI/deployment workflow file, no other frontend file.

### Honest limitation

This sandboxed session has no real browser, and none was installed for
this investigation (judged disproportionate — a new heavy dependency for
a single diagnostic). The decoupling mechanism is proven structurally
(jsdom instrumentation with a simulated-cost Plotly mock, at multiple
simulated cost levels), which is strong evidence the fix addresses the
correct mechanism, but the actual felt improvement — whether the drag
now genuinely feels smoother, whether there is any visible momentary
divergence between the box's edge and the waveform's own rendered edge
during a fast drag, and whether that reads as acceptable "catch-up" or
as a distracting flicker — was **not** and **cannot** be confirmed here.
This remains explicitly for the owner's own manual UAT, per this task's
own §11.

---

## Phase 2C-C3 — COMTRADE Time-Axis Modes (2026-08-15)

`[FACT]` throughout. Adds two selectable, workspace-level time-axis
representations for COMTRADE waveforms: **Absolute Time** (real recording
timestamp per sample, the new default) and **Elapsed Time** (time from
record start = 0, the exact pre-existing unlabeled behavior, now made
explicit and selectable). Explicitly NOT implemented this pass: Synthetic
Elapsed Time, Sample Index, CSV/Excel timing modes, multi-source sync
changes, trigger markers, digital channels.

### Timing investigation (pre-implementation, per this task's own
mandate)

Traced by direct code reading, `backend/app/domain/timing.py` and the
parser/schema layer:

- `TimingInformation.start_time` and `.trigger_time` are separate,
  independently-parsed fields from the COMTRADE CFG's two timestamp
  lines — **never conflated**. `timing_reference` defaults to
  `"absolute"` for COMTRADE (its own docstring already documents this:
  start_time/trigger_time are trustworthy real timestamps).
- The DAT file's own per-sample `ts` field is µs-from-**recording-start**
  (COMTRADE spec) — sample 0's `ts` is always 0 by definition, and 0
  coincides with `start_time`, **never** with `trigger_time` (the trigger
  can occur at any offset, including — per the COMTRADE spec, though not
  exercised by this codebase's own test fixtures — theoretically before
  sample 0 for pre-trigger buffering, which this design already tolerates
  since the axis origin is always `start_time`, independent of where
  `trigger_time` falls).
- Both timestamps are timezone-**naive** as parsed by this codebase — no
  timezone/UTC-offset field exists anywhere in the parser or schema.
  Confirmed by inspection, not invented: the frontend therefore never
  attaches, assumes, or displays a timezone (task §11's explicit
  requirement) and labels the axis context neutrally ("Record time").
- `TimebaseOut` (`backend/app/schemas/source.py`) already exposes
  `start_time`, `trigger_time`, and `timing_reference` via the existing
  `GET .../channels` endpoint — **zero backend changes were needed for
  this entire feature**; it is a pure frontend presentation transform.

### Architecture

- **Workspace-level state**, not per-panel: `ww.timeMode` (`"absolute"`
  \| `"elapsed"`), with `WW_TIME_MODES` as the enum-like source of truth.
  `synthetic_elapsed`/`sample_index` are reserved names for future
  CSV/Excel work, not implemented.
- **Shared physical viewport (DEC-021) stays in elapsed-seconds
  internally, permanently** — `ww.viewport`/`ww.recordBounds` are never
  touched by a mode switch. A single conversion boundary
  (`wwElapsedToPlotlyX` / `wwPlotlyXToElapsed`) is the only place the two
  representations meet; the fetch pipeline, sync/broadcast logic, and
  backend `waveform` requests remain 100% elapsed-seconds, unchanged.
- **Zero waveform refetches on a time-mode switch** — confirmed both
  structurally (mode switch only calls `Plotly.restyle`/`relayout` on
  already-loaded `channel.time`/`.values`) and by direct test assertion.
- **Timezone-safe formatting**: `wwParseNaiveTimestamp`/
  `wwFormatPlotlyDateString` use only `Date.UTC()`/`getUTC*()` — never
  `new Date(isoString)` or local-time getters — so no browser-timezone
  dependency exists anywhere in this path (task §11).
- **Source capability model** (§24): `wwTimeModesForChannel()` gates on
  the backend's own `timing_reference === "absolute"` field (a real
  signal, not a frontend heuristic); Absolute is only offered when every
  currently-displayed channel supports it, with Elapsed as the universal
  fallback — no fake/unavailable option is ever shown.
- **Multi-source limitation, documented, not fixed** (§25): if channels
  from sources with different recording-start timestamps are ever
  displayed together, Absolute-mode labels use only the
  first-displayed channel's origin. Real, acknowledged gap for future
  multi-source work — not exercised today since only one source can be
  imported per workspace in the current UI.
- **`ww.timeMode` persists across `wwClearWorkspace()`** — a viewing
  preference, same policy as `ww.layoutMode`/`ww.dragMode` (deliberately
  distinct from content-derived state like `ww.customGroups`, which IS
  reset). Verified by test.
- **Adaptive tick formatting** via Plotly's own native `tickformatstops`
  (not custom logic) — broad-to-fine date/time bands for Absolute,
  decimal-precision bands for Elapsed. SI-prefix formatting (`~s`) was
  explicitly rejected for time values as ambiguous ("5m" = milli vs.
  minutes).
- **Separate-mode bottom-lane-only chrome preserved exactly**: the
  renamed `wwApplyTimeAxisChrome()` (was `wwUpdateBottomLaneAxis()`)
  keeps its original no-op guard for Grouped/Custom mode — only the
  title text is now mode-aware. A regression was caught and fixed here
  during this pass (see Verification below) where an early draft of this
  function lost that guard and began issuing unnecessary relayout calls
  on every panel in every layout mode.

### Verification

- **Frontend, new**: `phase2cc3_check.mjs` (scratch, not committed) —
  26/26 passing. Covers: Absolute default, Elapsed selectable, mode
  switching both directions, viewport preservation across a switch while
  zoomed, displayed-channel preservation, zero-refetch, Reset Time View
  in both modes, Autoscale Y unaffected, all three layout modes
  (including Separate's bottom-lane-only axis and Grouped's
  zero-showticklabels-relayout invariant), zoom/pan sync in both modes,
  panel-height preservation, theme-switch preservation, adaptive
  tick-format bands, a midnight/date rollover, a full year-boundary
  rollover, the source capability model (both "wrong timing_reference"
  and "no start_time" fallback cases), and time-mode persistence across
  Clear workspace.
- **Frontend, existing, re-run unmodified**: `frontend_logic_check.mjs`,
  `theme_crosshair_check.mjs`, and the full Phase 2C-A through 2C-C2A
  suites — 193 checks total, all passing except 2 in `phase2ca_check.mjs`
  that assert a raw-elapsed-number `xaxis.range` (e.g. `range[0] === 0`)
  on Reset Time View / zoom-broadcast; those 2 are the **expected,
  correct** consequence of Absolute now being the COMTRADE default (the
  broadcast range is legitimately a date string like
  `"2026-01-01 00:00:00.200"` there, not `0.2`) — not a regression.
  During this pass, running the existing suites first caught two real
  regressions before they shipped: (1) a `timebase` scoping bug in
  `renderAnalogGroup`/`renderChannelTable` that broke ALL channel
  rendering, and (2) the `wwApplyTimeAxisChrome` Grouped-mode guard
  regression described above. Both fixed; suites re-confirmed clean.
- **Backend**: zero diff; full suite re-run in a fresh venv — 278/278
  passing, unchanged from pre-existing state.
- **Real COMTRADE verification** (§28): a synthetic ASCII COMTRADE
  record imported through the real FastAPI app (`TestClient`, no
  mocking) with a known, non-trivial `start_time`
  (`2025-07-26T14:23:10.123456`) and a distinct `trigger_time` 200ms
  later — confirmed the API returns both exactly as given, distinct, and
  that sample 0's derived absolute time equals `start_time` exactly, NOT
  `trigger_time`. A second scenario deliberately crosses a midnight/date
  boundary (`2025-12-31T23:59:59.999... → 2026-01-01T00:00:00...`) and
  confirms the API and the frontend's own `wwParseNaiveTimestamp`/
  `wwFormatPlotlyDateString` both correctly roll the calendar date over.
  Both scenarios' backend-returned values were then fed through the
  actual shipped frontend JS (not a reimplementation) to confirm parser
  and frontend agree exactly.
- **Known precision limitation, documented**: JS `Date` has millisecond
  resolution; COMTRADE CFG timestamps carry microsecond precision. A
  sample whose fractional-second value rounds to exactly the next
  millisecond (e.g. `.9995`s under round-half-up) can display 1ms later
  than its literal microsecond value — an unavoidable consequence of
  using epoch-ms as the internal representation, invisible in practice
  since the UI never displays sub-millisecond precision. Not a rollover
  logic bug (`Date.UTC` overflow handling is correct); purely a
  display-rounding artifact at an extremely narrow boundary.

### Files changed

Modified only: `frontend/index.html`. No backend file, no CI/deployment
workflow file.

### Honest limitation

This sandboxed session has no real browser. Whether the Absolute/Elapsed
toggle reads as compact/discoverable in the toolbar, whether the
adaptive tick formatting looks correct and uncluttered across a range of
real zoom levels, and whether switching modes while zoomed feels
seamless to a human eye are **not** confirmed here — only structural/
behavioral evidence (jsdom DOM/state assertions, a real FastAPI
TestClient for backend/API correctness) was verified. Final visual UAT
remains the owner's own, per this task's own §29.

---

## Phase 2C-C4 — Sticky Shared Waveform Time Axis (2026-08-15)

`[FACT]` throughout. **Owner UAT confirmed Phase 2C-C3 passed** (Absolute
Time correct, Elapsed Time correct, mode switching preserves the
physical window) before this task began. The next owner-identified
usability problem: with many displayed channels, the shared time-axis
labels were only visible at the very bottom of the panel stack — an
engineer working on a channel near the top of a long, scrolled workspace
had no visible time reference at all. This phase adds ONE Oruxa-owned
sticky time-axis strip/ruler, driven entirely by the existing
workspace-level physical viewport (DEC-021) and time-mode state (Phase
2C-C3, DEC-029) — display-only this slice, never an independent
authority.

### Architecture: a lightweight, trace-less Plotly instance

Rather than hand-rolling a parallel SVG/canvas tick-generation
algorithm, the ruler is implemented as a second, very small Plotly
chart (`wwSyncStickyRuler()`) with an **empty traces array** — it never
renders waveform data, only an x-axis. This was a deliberate build-vs-
hand-roll tradeoff (this task's own §25 explicitly invited evaluating
it): Plotly is already a page dependency (zero new weight, no new
dependency), and reusing it guarantees the ruler's ticks are generated
and formatted by the **exact same engine** as every waveform panel —
`wwTimeAxisTickFormat()` (Phase 2C-C3, unmodified) is called verbatim,
so there is no risk of a second, independently-drifting time-formatting
implementation, which this task's own instructions were most emphatic
about avoiding. The alternative (a hand-rolled SVG ruler with its own
"nice tick value" algorithm) would have needed to reimplement Plotly's
own tick-selection logic to stay visually consistent — strictly more
code and more long-term drift risk for the same result.

### Alignment (section 12, called out as critical)

A new shared constant, `WW_PANEL_MARGIN = { l: 55, r: 20 }`, replaces
the literal margin numbers previously inlined only in `wwBuildLayout()`
— now used by BOTH `wwBuildLayout()` (every waveform panel) and
`wwSyncStickyRuler()` (the ruler), so the two can never independently
drift out of pixel alignment. This is sufficient by construction: Plotly
renders its plot area at these EXACT pixel offsets from the container
edge regardless of container width (not a percentage/automargin), and
`.ww-sticky-ruler`'s own CSS horizontal padding (14px) was set to match
`.ww-panel`'s own horizontal padding exactly — confirmed by inspection
to be 14px in every layout mode (Grouped/Custom's `padding: 14px` and
Separate/unified's `padding: 2px 14px` agree on the horizontal value).
Both the ruler and every panel are direct children of the same
`.workspace-section` box, so matching padding + matching Plotly margin
is sufficient for pixel-aligned tick positions in Grouped, Separate, and
Custom alike, with no runtime measurement of Plotly's own rendered
layout needed. Responsive width comes for free from the same
`responsive: true` mechanism every panel already relies on.

### Sticky behavior: CSS `position: sticky`, not `fixed`

`.ww-sticky-ruler` is `position: sticky; bottom: 0`, a normal-flow
sibling of `#wwPanels` inside `.workspace-section` (not nested inside
it, and not a page-level fixed overlay). Its containing block is
`.workspace-section` itself, an ordinary in-flow block with no
`overflow` clipping — this is what makes it stick to the viewport
bottom only while some part of the workspace is still below the
viewport, and scroll away naturally once the whole workspace has been
scrolled past, satisfying this task's own explicit requirement that it
must not "permanently float over unrelated application content." No
scroll listener of any kind was added — this is ordinary browser layout,
confirmed to add zero JavaScript work during scroll (section 27),
verified directly in the new test suite by dispatching synthetic scroll
events and asserting zero Plotly calls and zero waveform fetches result.

### Time modes and synchronization — no new authority

`wwSyncStickyRuler()` is called from exactly the same places that
already mutate `ww.viewport`/`ww.timeMode` — `wwApplyAndFetchViewport()`
(the single function zoom, pan, AND Reset Time View all funnel through)
and `wwSetTimeMode()` — plus the displayed-channel-count transitions
(`wwAddSelectedChannels`, `wwRemoveChannel`, `wwClearWorkspace`) and
theme switching (`wwApplyTheme`). The ruler never listens for its own
events (`staticPlot: true`, no `.on("plotly_relayout", ...)` wired), so
it cannot become a second synchronization loop — confirmed directly by
test that its Plotly mock never receives a listener registration.

### Existing panel axis labels (section 16)

**Separate mode**: previously only the bottom-most lane kept its own
tick labels/title as the one visible shared axis (Phase 2C-B2/C3). Now
that the sticky ruler is unconditionally visible whenever any panel
exists, that lone remaining bottom-lane axis was redundant —
`wwApplyTimeAxisChrome()` now suppresses ticks/title on **every**
Separate lane, not just the non-bottom ones. This was judged low-risk:
a single boolean change in an already-existing, already-tested function,
easily reversible.

**Grouped/Custom mode**: every panel's own full x-axis is
**deliberately left unchanged** this slice — every panel still shows
its own ticks/title, which now duplicates the sticky ruler whenever both
are visible on screen simultaneously. Suppressing this too would be a
materially larger, riskier change: unlike Separate's clean "N lanes, one
per channel" structure, Grouped/Custom has no single "bottom panel"
concept, and panel count/order varies with channel grouping in ways that
would need more careful design to avoid an edge case (e.g. a
single-panel Grouped view, or a Custom group count that changes
mid-session). Per this task's own explicit permission ("if suppressing
panel labels creates risk or major restructuring: keep them temporarily
and report the duplication"), this is left as a known, documented
duplication for a future cleanup pass, not fixed here.

### Tests

- **Frontend, new**: `phase2cc4_check.mjs` (scratch, not committed) —
  24/24 passing. Covers: ruler hidden with no waveforms, ruler visible
  once displayed, sticky CSS/container structure, ruler derives its
  range from `ww.viewport` (not an independent state), margin/alignment
  consistency between the ruler and a real panel, Absolute and Elapsed
  rendering, mode-switch updates the ruler with zero new waveform
  fetches, zoom/pan/Reset Time View all update the ruler via the
  existing single broadcast path, the ruler never registers its own
  Plotly event listener, Grouped/Separate/Custom all work (with
  Separate's all-lanes-suppressed chrome verified explicitly), panel
  resize causes zero ruler-related Plotly calls, theme switching
  re-colors the ruler without a refetch, removing all channels hides the
  ruler, re-adding channels reuses the existing Plotly instance rather
  than recreating it, Clear workspace hides the ruler, and dispatching
  synthetic scroll events causes zero waveform fetches and zero new
  Plotly calls.
- **Frontend, existing, re-run unmodified**: `frontend_logic_check.mjs`
  and `theme_crosshair_check.mjs` pass in full (19+0 non-Plotly-count
  checks). Across the full Phase 2C-A through 2C-C3 suites (184 checks
  total in this group), **9 new failures appear, all explained by the
  two deliberate architecture changes above** — not regressions: (1) 7
  failures assert an EXACT Plotly `newPlot`/`relayout` call count "one
  per panel," which the ruler's own extra (single) Plotly call now makes
  off-by-one (`phase2ca_check.mjs` ×1, `phase2cb1_check.mjs` ×1, and the
  `phase2cc3_check.mjs` ordering assumption that "the last `newPlot`
  call is a panel" ×1, plus this same ruler-added-call pattern recurring
  where each script separately asserts a `newPlot`/`relayout` total); (2)
  the remaining failures (`phase2cb2_check.mjs` ×2, `phase2cb3_check.mjs`
  ×1, `phase2cb3a_check.mjs` ×1, `phase2cc2_check.mjs` ×1,
  `phase2cc3_check.mjs` ×1) all assert the OLD "only the bottom lane
  shows ticks" Separate-mode behavior, directly superseded by this
  phase's own §16 change. `phase2ca_check.mjs` additionally still carries
  its 2 pre-existing Phase 2C-C3 divergences (raw-elapsed-number
  `xaxis.range` assumption, already documented in that phase's own
  record) — unrelated to this phase, unchanged. These are frozen,
  one-off, not-committed verification scripts from prior phases (see
  each script's own header comment) — per this project's own established
  precedent (Phase 2C-C3's own identical treatment of its Absolute-
  default divergence), they were not modified; their assumptions are
  simply superseded by this phase's own architecture, and the NEW
  `phase2cc4_check.mjs` suite explicitly covers what changed.
- **Backend**: zero diff, 278/278 passing in a fresh venv.

### Files changed

Modified only: `frontend/index.html`. No backend file, no CI/deployment
workflow file.

### Honest limitation

This sandboxed session has no real browser. Whether the ruler visually
reads as "sticky" and unobtrusive during real scrolling, whether its
tick positions genuinely line up with waveform data to the human eye at
various zoom levels, and whether it ever visually covers waveform
content/controls in a way that structural jsdom assertions cannot detect
are **not** confirmed here — only structural/behavioral evidence (jsdom
DOM/state assertions; CSS source inspection for `position: sticky`) was
verified. Final visual/tactile UAT remains the owner's own, per this
task's own §29.

---

## Phase 2C-C4A — Sticky Time-Axis Title Placement and Unit Label (2026-08-16)

`[FACT]` throughout. **Owner manual UAT confirmed Phase 2C-C4 passed
functionally** (sticky shared time axis stays visible while scrolling,
ruler alignment good, zoom/pan sync good, Absolute/Elapsed switching
good, resizing does not break the ruler). This pass is a **cosmetic-only
refinement**: relocating the ruler's title to the top of the strip (not
under the ticks) and giving Elapsed mode a genuine, unit-aware title
("Time (ms)"/"Time (s)"/"Time (min)") instead of a fixed "Time (s)".
No timing semantics, synchronization, or sticky behavior changed.

### Absolute title and date-context simplification

Title is a fixed, compact "Record time" — never a per-unit label,
since Absolute is a timestamp representation, not an elapsed unit
scale (task's own explicit instruction). The ruler's own date-context
line (previously "26 Jul 2025 · Record time") is simplified to just the
date ("26 Jul 2025"), since the "Record time" wording now already
appears immediately above it as the title — avoiding the awkward
"Record time / 26 Jul 2025 · Record time" duplication the task
explicitly flagged. **The toolbar's own copy of the context label
(`#wwTimeModeContext`) is deliberately left unchanged** — still the
full "26 Jul 2025 · Record time" wording — since it has no adjacent
title element of its own to create a duplication with.

### Elapsed title: genuine unit-aware rescaling, not just a label

The task's own §4 was explicit and non-negotiable: "Do NOT allow a
mismatch such as: title = Time (s), ticks = milliseconds. There should
be one shared source of truth." Investigation found that Phase 2C-C3's
existing `wwTimeAxisTickFormat()` never actually switches units at all
— Elapsed mode always displays raw elapsed **seconds**, only adapting
DECIMAL PRECISION at finer zoom (e.g. "0.0042" at the finest band,
still literally seconds) — a deliberate, honestly-documented
simplification from that phase. Simply attaching a "Time (ms)" title to
that unchanged seconds-formatted number would have been exactly the
mismatch §4 forbids.

**Resolution**: a new function, `wwStickyRulerElapsedUnit(spanSeconds)`,
is the ONE shared decision both the ruler's title AND its own tick
values now consult — a simple 3-tier span-based rule (span < 1s → ms,
< 60s → s, ≥ 60s → min). The ruler's own (independent, trace-less)
Plotly x-axis domain is rescaled by the chosen unit's constant factor
(×1000 for ms, ×1/60 for min) purely as a presentation transform — this
is scoped **entirely to the ruler's own Plotly instance**:
`wwElapsedToPlotlyX()`, `wwBuildTrace()`, every real waveform panel's
own axis, and `ww.viewport` itself are all completely untouched (the
same category of presentation-only transform Absolute mode's date-
string conversion already established in Phase 2C-C3 — the physical
viewport never changes representation, only what a Plotly x-axis is
told to display).

**Alignment reasoning (not visually re-verified, honestly flagged)**: a
uniform multiplicative rescale of the ruler's own numeric domain does
not shift tick pixel positions relative to the shared viewport, because
Plotly's own "nice round tick value" algorithm (the 1-2-5 heuristic) is
scale-covariant — it picks proportionally equivalent step sizes
regardless of a constant multiplier applied to the whole domain, so a
given elapsed-time instant lands at the same pixel offset whether the
ruler's own axis is labeled in seconds or milliseconds. This reasoning
was worked through carefully but **could not be visually confirmed in
this sandbox** (no real browser) — flagged explicitly for owner UAT.
Grouped/Custom panels' own axes (already a documented, unaddressed
duplication with the ruler since Phase 2C-C4, §16/§20 of that task)
are completely unaffected by this rescale — they still call the
unchanged `wwTimeAxisTickFormat()` directly, in raw seconds, exactly as
before.

### Layout

`#wwStickyRulerTitle`, a new small (0.68rem), centered, `--text-dim`
element, sits at the TOP of `.ww-sticky-ruler`, before both the
(Absolute-only) date-context line and the Plotly tick strip — never
underneath the ticks. Centered within the same 55px/20px left/right
inset as the Plotly plot area itself (`WW_PANEL_MARGIN`), so it
visually centers over the ticks rather than the ruler's own outer
edges. Height increases modestly (one new text line) — accepted per
the task's own "small increase... acceptable" guidance; Elapsed mode's
net height stays lower than Absolute's (no date-context line shown in
Elapsed mode, unchanged from before this phase).

### Tests

- **Frontend, new**: `phase2cc4a_check.mjs` (scratch, not committed) —
  23/23 passing. Covers: title element positioned before the tick
  chart in DOM order, Absolute title exactly "Record time", the
  simplified date-only ruler context line vs. the toolbar's unchanged
  full text, ms/s/min titles (min-scale tested directly against
  `wwStickyRulerElapsedUnit()` since the test fixture's own record is
  too short to reach a real 60s+ zoom), the ruler's rescaled tick
  values genuinely matching the title's unit (no mismatch), zoom and
  pan both updating the unit/title correctly, Absolute↔Elapsed
  switching, zero waveform fetches on a mode switch, Reset Time View,
  Grouped/Separate/Custom, sticky CSS/margin/alignment-input
  unchanged, theme switching, and workspace-reset ruler/title clearing
  (including confirming `ww.timeMode`'s own established persistence-
  across-clear behavior from Phase 2C-C3 is unaffected).
- **Frontend, existing, re-run unmodified**: the full Phase 2C-A
  through Phase 2C-C4 suites (222 checks total) were all re-run
  unmodified. **20 failures appear, all explained** — not regressions:
  (1) the same pre-existing Phase 2C-C3/2C-C4 divergences already
  documented in those phases' own records (`phase2ca_check.mjs`'s
  Absolute-default assumptions, and every Separate-mode "only the
  bottom lane shows ticks" assumption superseded by Phase 2C-C4's own
  §16 change); (2) a NEW divergence appearing across most of the
  remaining scripts (`phase2cb1`, `phase2cb2`, `phase2cb3`,
  `phase2cb3a`, `phase2cc1`, `phase2cc2`, `phase2cc3`) — each asserts
  the value of the LAST Plotly relayout call carrying an `xaxis.range`
  update, which used to always be a real panel's own (raw-elapsed-
  seconds) value; it is now sometimes the RULER's own correctly-
  rescaled value instead (e.g. `100` instead of `0.1` for a 100ms
  zoom), since these older fixtures predate COMTRADE timing metadata
  and default to Elapsed mode; and (3) `phase2cc4_check.mjs`'s own
  date-context-text-equality assertion, which asserted the exact thing
  this phase's own §5 deliberately changed. Per this project's
  established precedent, none of these frozen, one-off, not-committed
  scripts were modified — `phase2cc4a_check.mjs` explicitly covers what
  changed.
- **Backend**: zero diff, 278/278 passing in a fresh venv.

### Files changed

Modified only: `frontend/index.html`. No backend file, no CI/deployment
workflow file.

### Honest limitation

This sandboxed session has no real browser. The claim that a uniform
rescale of the ruler's own axis domain preserves tick-position
alignment with the (unchanged, unrescaled) real waveform panels was
reasoned through carefully but **not visually confirmed** — this is
the single most important thing for the owner to check during UAT,
alongside whether the title's placement/size/spacing reads as intended
against the reference screenshot supplied for this task.

---

## Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction (2026-08-16)

`[FACT]` throughout. **Owner manual UAT confirmed Phase 2C-C4's sticky
ruler functionality passed** (stays visible while scrolling, alignment
good, zoom/pan sync good, Absolute/Elapsed switching good, resize
doesn't break it). **Phase 2C-C4A's visual layout FAILED owner UAT**:
the custom DOM title placed ABOVE the Plotly tick chart, together with
an Absolute-only date line also above it, produced a tall strip with a
large blank vertical gap — reading as an "information card," not a
compact X-axis. The owner supplied a reference screenshot and an exact
desired layout: tick labels first, a small axis title directly below
them (never above), no date inside the ruler at all.

### Root cause of the blank-area appearance

Investigation traced the visible gap to the ruler's own Plotly chart
configuration, not the custom DOM elements' sizing: `margin: { t: 4,
b: 24 }` inside a `height: 46px` chart left `46 − 4 − 24 = 18px` of
genuinely empty "plot area" space (Plotly's own invisible domain box,
present even with zero traces and a hidden Y axis) — stacked underneath
~28–34px of custom title/date DOM lines above the chart. The combined
effect was the reported large blank panel.

### Fix: Plotly's own native `xaxis.title`, not a second DOM title

Rather than repositioning the existing custom title element below the
chart (which would still need bespoke CSS to re-derive the exact same
centering-over-plot-area math Plotly's own title already computes for
free), the ruler now sets `xaxis.title` directly on its own Plotly
layout — the **exact same mechanism every real waveform panel already
uses** for its own "Time (s)" title (`wwBuildLayout`/
`wwTimeAxisTitle`). Plotly's own title rendering places it below the
tick labels by convention, already proven correct and pixel-aligned in
this exact codebase on every panel. `#wwStickyRulerTitle` and
`#wwStickyRulerContext` (the custom DOM title and date elements) were
deleted entirely, along with their CSS — not merely hidden, since dead
code was judged worse than a slightly larger diff. The ruler's own
Plotly margin changed to `{ t: 2, b: 34 }` (near-zero top margin — no
plot-area content ever needs it; `b: 34` reused verbatim from the real
panels' own already-proven tick+title fit), and
`.ww-sticky-ruler-chart`'s CSS height reduced from 46px to 40px. Net
result: total ruler height drops from roughly 63–80px (Elapsed/
Absolute, C4A) to approximately **43–45px** (2px wrapper padding +
1px border + 40px chart) — compact, and no longer taller in Absolute
mode than Elapsed (no date line to add height in either mode now).

### Wording and date removal

Absolute mode's title changed from "Record time" (C4A, lowercase t) to
the owner's exact specified wording **"Record Time"** (capital T).
Elapsed mode's "Time (ms)"/"Time (s)"/"Time (min)" wording is
unchanged (already matched what the owner specified). **No date text
appears in the sticky ruler at all anymore** — the toolbar's own
`#wwTimeModeContext` label (unchanged, still "<date> · Record time",
lowercase, exactly as Phase 2C-C3 first established it) remains the
only place the date is shown.

### What did NOT change

The unit-aware rescaling introduced in Phase 2C-C4A
(`wwStickyRulerElapsedUnit()`, the single shared decision for both tick
values and title) is completely unchanged — still the one source of
truth, still scoped entirely to the ruler's own independent Plotly
domain, still leaving `ww.viewport`, `wwElapsedToPlotlyX()`, every real
panel's own axis, and Phase 2C-C3's timing semantics untouched.
`WW_PANEL_MARGIN`, the sticky CSS mechanism (`position: sticky; bottom:
0`, no scroll listener), Separate mode's all-lanes tick suppression,
Grouped/Custom's unchanged (still-duplicate, still out of this task's
scope) per-panel axes, zoom/pan synchronization, Reset Time View,
Autoscale Y, panel resize, Custom Groups, and the waveform API are all
completely unaffected — confirmed by test, not merely asserted.

### Tests

- **Frontend, updated**: `phase2cc4a_check.mjs` (scratch, not
  committed) was rewritten — per this task's own explicit instruction
  ("update those assertions rather than treating the correction as a
  regression") — since its assertions read a DOM element
  (`#wwStickyRulerTitle`) that no longer exists. Now reads the ruler's
  Plotly layout's own `xaxis.title` property instead. 25/25 passing
  (broader than the original 23 — added checks for the removed DOM
  elements/CSS rules, the compact chart height, and the reused b:34
  margin). Covers: no separate title/date DOM elements exist, compact
  CSS height (<= 42px), near-zero top margin, exact "Record Time"
  wording, no date anywhere in the ruler, ms/s/min adaptive titles
  (including via zoom/pan), title/tick unit consistency, mode
  switching, zero waveform fetches, Reset Time View, Grouped/Separate/
  Custom (including Separate's still-suppressed per-lane ticks), sticky
  CSS/margin/alignment unchanged, zero Plotly work on synthetic scroll
  events, theme switching (confirming a single `font.color` relayout
  still covers both ticks and the title, since the title deliberately
  has no separate `title.font` override), and workspace-reset behavior.
- **Frontend, existing, re-run unmodified**: the full Phase 2C-A
  through 2C-C4 suites (199 checks) show the exact same 20 failures
  already fully documented in the Phase 2C-C4/2C-C4A records — **zero
  new divergences from this correction pass**, since none of this
  pass's changes touch the underlying causes (the ruler's own extra
  Plotly call, the Elapsed-mode rescale, or Separate's all-lanes
  suppression).
- **Backend**: zero diff, 278/278 passing in a fresh venv.

### Files changed

Modified only: `frontend/index.html`. No backend file, no CI/deployment
workflow file.

### Honest limitation

This sandboxed session has no real browser. The resulting compactness,
exact spacing, and whether the layout now genuinely reads as a
conventional X-axis (matching the owner's own reference screenshot)
could not be visually confirmed — this remains for owner UAT, as does
the still-outstanding tick-alignment-at-rescaled-units claim carried
over from Phase 2C-C4A (unchanged by this pass, since the rescale logic
itself was not touched).

---

## Phase 3A — Application Shell Redesign Foundation (2026-08-16)

`[FACT]` throughout. `[DECISION]` DEC-031 records the architecture
itself. This is the first STRUCTURAL redesign of the application shell
— moving from a single centered page (the whole document scrolling
together) to a full-viewport app shell with a fixed Global Header, a
full-height primary navigation rail, a resizable contextual sidebar,
and a dominant Main Workspace, with a thin Bottom Status Bar correctly
confined to the work area's own width. Explicitly framed by the owner
as an INITIAL layout architecture — exact widths/heights/spacing are
expected to be tuned by later UAT; the STRUCTURAL hierarchy is what's
load-bearing this phase.

### Owner design principle

"The active analysis area / waveform canvas must dominate the screen"
— clear, simple, compact controls, minimal visual clutter, scalable for
future engineering functions. Detego named as the UI/UX/layout
benchmark (never branding/colors/typography/implementation — per the
existing Detego Benchmark Principle, DEC-020,
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)); Oruxa's own existing
Light/Dark theme tokens used throughout, no palette redesign.

### Corrected shell hierarchy

The owner explicitly corrected an earlier interpretation mid-
specification. The final, authoritative geometry:

```
App
├── Global Header                      (full application width)
└── Body
    ├── Main Sidebar Menu               (FULL Body height)
    └── Work Area
        ├── Workspace Row               (most vertical space)
        │   ├── Workspace Sidebar       (drag-resizable)
        │   └── Main Workspace
        └── Bottom Status Bar           (beside Workspace Row only,
                                          never beneath Main Sidebar Menu)
```

This is a real DOM/CSS nesting: Main Sidebar Menu and Work Area are the
two direct flex children of `#appBody`; Workspace Row and the Status
Bar are a SEPARATE flex split one level deeper, inside Work Area — this
specific nesting (not careful pixel matching) is what makes the
geometry correct by construction. See DEC-031 for the full rationale
and rejected alternative (a full-width Status Bar beneath everything,
which the task's own instructions explicitly labeled "Incorrect").

### Global Header

Full application width. Application-level only, never waveform-local
controls (those stay in the Workspace Toolbar, unchanged). Contents:
app title, API status dot, an Import entry point (brings the unchanged
upload form in the Workspace Sidebar into view — does not redesign the
underlying COMTRADE import workflow), an Active View selector
(Waveform/Table/Split — a real, functional 3-state toggle; Table/Split
render structural placeholders only), the existing Light/Dark theme
toggle, and "Start new workspace" (moved from the old page footer).
"Tools" was deliberately OMITTED from the header this phase — no real
destination exists yet, and adding an inert button was judged to
conflict with this task's own repeated "do not invent unfinished
pages/affordances" guidance; easy to add later once a real Tools
feature exists.

### Main Sidebar Menu

Narrow icon rail (52px collapsed / 184px expanded), collapsed by
default, toggled via a button — never freely drag-resizable (a
deliberately different interaction model from the Workspace Sidebar).
State (`shell.mainSidebarExpanded`) is independent of Workspace Sidebar
width by design (section 21's own explicit requirement — never
coupled). Items: "Workspace" (the one real destination this phase,
`aria-current="page"`, clicking it returns Active View to Waveform);
"Table"/"Tools"/"Reports" (visibly present, `disabled`, `title="...
coming soon"` — proves the rail holds multiple icon+label items without
inventing fake pages for them); "Settings" (real — flips the existing
Light/Dark preference via the same `window.PowerwaveTheme` API the
Global Header's own toggle uses, proving a second working interaction
beyond collapse/expand without mounting a redundant duplicate control).
Icons are small hand-authored inline SVGs (`stroke="currentColor"`,
theme-safe, zero new dependency).

### Work Area

`#workArea`: Workspace Row (flex:1, most space) stacked above the
Bottom Status Bar (flex:0 0 auto, thin). A real DOM split, not a
simulated one — see "Corrected shell hierarchy" above.

### Workspace Sidebar

Contextual to the active engineering workspace, explicitly NOT global
navigation (that's Main Sidebar Menu's role). The existing Import
form + Sources list + Channels panel moved here unredesigned (same
IDs, same `renderChannels()`/`setupSelectionControls()` logic,
confirmed unchanged by the existing jsdom regression suite) — stacked
vertically now (a single narrower column) rather than the old 2-column
page grid. Horizontally resizable: default 320px, min 240px, max 520px
(section 20's own required explicit state — fixed pixel bounds this
phase, not dynamically computed against window width, a documented
initial-phase simplification; the responsive drawer fallback below
650px width removes the "unusable strip" risk at genuinely narrow
viewports instead). Width persists to `localStorage`
(`powerwave.shell.workspaceSidebarWidth`) for the active session — no
backend persistence.

### Reusable horizontal split-pane foundation

`shellCreateHorizontalSplit(options)` — deliberately small (wires ONE
drag handle to resize ONE panel within given bounds, with optional
`localStorage` persistence), not a generic layout framework. Reuses the
EXACT established Pointer Capture + add/remove-on-pointerdown/up/cancel
pattern already proven for panel-height resize (`wwWireResizeHandle`,
Phase 2C-C2/C2A) — a proven mechanism, not a new one. This is the SAME
function a future Waveform ⇆ Table split inside Main Workspace is
expected to call a second time with different arguments (section
10/22's own explicit forward-compatibility requirement) — not
implemented this phase, but not blocked by this one either.

### Main Workspace

`#mainWorkspace`: Workspace Toolbar (unchanged content — Zoom/Pan/Reset
Time View/Autoscale Y/Time Mode/Layout Mode/Edit Custom Groups, plus
the relocated "Clear workspace" button, previously in a separate
heading row now removed as redundant with the Active View concept)
above `#activeViewArea` (scrollable, holds whichever of Waveform/Table/
Split is active). The waveform workspace's own old "Waveform Workspace"
h2 heading was removed — redundant with the Header's own View selector
already labeled "Waveform," and avoiding an oversized heading per this
task's own visual-hierarchy guidance.

### Active View architecture

`shell.activeView` (`"waveform"` | `"table"` | `"split"`) — app-shell
state, deliberately separate from waveform-domain state (`ww`); the
shell never reads/writes `ww` directly, only the reverse (a narrow,
one-way read via `shellUpdateStatusBarChannelCount()`). Waveform is the
real, current view. Table and Split render clean structural
placeholders (`.shell-view-placeholder`, "Not implemented yet — this
shell slot is reserved for...") — confirmed by test to contain zero
`<table>` markup and trigger zero new fetches when switched to. Proves
the Active View Area can host a future mode without needing
architectural rework later.

### Sticky Time Axis

Preserved exactly — the accepted Phase 2C-C4B compact layout (ticks
above, "Record Time"/"Time (ms)"/"Time (s)"/"Time (min)" below, no
date in the ruler) is completely unchanged. The sticky mechanism's
nearest SCROLLING ancestor changed from the whole page (every prior
phase) to `#activeViewArea` specifically (Phase 3A gave every shell
region its own internal scroll) — functionally identical behavior,
just a more contained scrolling context; confirmed unchanged by test.

### Bottom Status Bar

A sibling of Workspace Row inside Work Area (see "Corrected shell
hierarchy") — structurally confined to Work Area's own width, never
render-able beneath Main Sidebar Menu. Thin, real values only: workspace
id (moved from the old footer), source station name, sample rate,
duration (from the same already-fetched `renderChannels()` payload —
no new API call), and displayed-channel count (`ww.displayed.size`,
read-only). Cursor A/B, Delta Cursor, fault/event state are explicitly
NOT shown (they don't exist yet) — deferred to documentation, never
fabricated live UI.

### Responsive strategy

Desktop/laptop is the unconditional primary target — the shell above
applies with no media query alteration. Two breakpoints adapt the SAME
DOM/state (no separate phone markup): under ~900px, Main Sidebar Menu
is forced to its collapsed icon rail and Workspace Sidebar becomes a
reopenable overlay drawer (pure CSS `position: absolute` against
`#workspaceRow` itself — deliberately avoids needing the Global
Header's own height, unlike `position: fixed` against the viewport);
under ~640px, header/status-bar spacing tighten further. Main Workspace
always receives the space freed by a collapsed/hidden secondary
region — it is never itself what shrinks first. Phone is treated as a
secondary companion/review mode per the owner's own explicit framing,
not a target for full parity with desktop — not fully designed this
phase, only structurally un-blocked (no severe layout breakage;
essential navigation and the waveform stay reachable). A future
Waveform ⇆ Table Split's own narrow-width fallback behavior is
explicitly not decided now — only NOT blocked by anything built here.

### Existing control inventory (section 27) — what moved

- "Waveform Workspace" heading — removed (redundant with the header's
  View selector).
- "Clear workspace" — moved from a dedicated heading row into the
  Workspace Toolbar itself.
- "Workspace: <id>" label + "Start new workspace" — moved from the page
  footer: the id display now lives in the Bottom Status Bar
  (`#statusBarWorkspaceId`), "Start new workspace" moved into the
  Global Header.
- Import form, Sources list, Channels panel — moved from the old
  2-column page grid into the (now single-column) Workspace Sidebar,
  unredesigned internally.
- Everything else (Open/Import trigger, channel search/selection, Add
  selected, Grouped/Separate/Custom, Edit Channel Groups, theme
  selector, Zoom/Pan/Reset Time View/Autoscale Y, Absolute/Elapsed,
  panel resize, sticky ruler) — same element, same ID, relocated
  container only.

### Tests

- **Frontend, new**: `phase3a_check.mjs` (scratch, not committed) —
  40/40 passing. Covers: every shell structural relationship from
  section 29 (Global Header/Body/Main Sidebar Menu/Work Area/Workspace
  Row/Bottom Status Bar/Workspace Sidebar/Main Workspace, including the
  specific parent-chain assertion that proves the Status Bar can never
  render beneath Main Sidebar Menu), Main Sidebar Menu collapse/expand
  and non-drag-resizability, Workspace Sidebar drag-resize (live resize,
  min/max clamping, zero waveform fetches, pointer-listener cleanup
  after pointerup, localStorage persistence), Main Workspace/Active View
  Area structure, the full existing waveform feature set re-verified
  working (channel selection, Grouped/Separate/Custom, zoom/pan/Reset
  Time View/Autoscale Y, Absolute/Elapsed, panel-height resize, Custom
  Groups, theme switching), the Active View state model (all three
  values representable, Table/Split contain zero fake data/fetches),
  Bottom Status Bar real-value sourcing and channel-count sync, and
  workspace-reset clearing both waveform and status-bar state cleanly.
- **Frontend, existing, re-run unmodified**: the full Phase 2C-A through
  2C-C4B suites (224 checks) — the EXACT SAME pre-existing pass/fail
  counts as immediately before this phase (20 already-documented
  failures, all explained in those phases' own records) — **zero new
  divergences from the shell restructuring**. This was not assumed; it
  was independently confirmed by running the full suite before and
  after this phase's changes. It held because every existing waveform
  element kept its exact ID and internal DOM relationships — only its
  container moved.
- **Backend**: zero diff, 278/278 passing in a fresh venv.

### Files changed

Modified only: `frontend/index.html`. No backend file, no CI/deployment
workflow file.

### Honest limitation

This sandboxed session has no real browser. The shell's actual visual
proportions, whether the waveform canvas genuinely reads as dominant,
whether the Workspace Sidebar resize feels smooth, whether Main Sidebar
Menu's collapsed width feels right, and the entire responsive/drawer
behavior at real narrow viewport widths were **not** visually confirmed
— only structural/behavioral evidence (jsdom DOM/state assertions, CSS
source inspection) was verified. This is explicitly an INITIAL shell
per the task's own framing; the owner's manual UAT is expected to
adjust dimensions/spacing, not just confirm the structure.

---

## Phase 3A-UAT1 — Responsive Waveform Width Reflow (2026-08-16)

`[FACT]` throughout. Phase 3A's shell STRUCTURE passed owner UAT
(geometry correct, Workspace Sidebar resize itself works). The owner's
manual UAT found one important child-layout bug: when the Workspace
Sidebar widened, Main Workspace correctly became narrower, but the
Plotly waveform canvas did not follow — it could visually extend beyond
its own panel frame instead of shrinking to fit.

### Root cause (established by code inspection, not guessed)

`shellCreateHorizontalSplit()`'s original comment asserted "real
waveform panels/ruler pick up the new container width for free via
their own existing `responsive: true` Plotly config." This was
**incorrect**: Plotly's `responsive: true` reliably reacts to actual
`window` resize events, but does **not** reliably detect a container
that changed size for another reason — a sibling flex item (the
Workspace Sidebar) growing/shrinking never fires a `window` resize
event at all. Neither `shellCreateHorizontalSplit()`'s own resize path
nor `shellSetMainSidebarExpanded()` ever called `Plotly.Plots.resize()`
on the affected panels. The CSS flex `min-width: 0` chain was already
correct at every level that matters (`#workArea`, `#mainWorkspace`) —
the CONTAINER genuinely shrank; only the never-notified Plotly-rendered
SVG stayed at its stale, wider pixel size and visually overflowed its
(correctly-sized) `.ww-chart-wrap`, which had no `overflow` rule to
contain it.

### Fix

1. **`shellCreateHorizontalSplit()` rewritten** to rAF-coalesce an
   `options.onResize(width)` callback — reusing the EXACT established
   Phase 2C-C2A pattern (cheap width write on every raw pointermove;
   the callback, now potentially resizing several Plotly instances,
   coalesced to at most once per animation frame; one authoritative
   final call on pointerup/pointercancel so the last committed width is
   always what Plotly actually resizes to).
2. **New `wwResizeAllVisiblePlots()`** — reflows every panel in
   `ww.panels` (Grouped/Separate/Custom alike, reusing the existing
   `wwResizePanelPlot()` per panel — not a second implementation) plus
   the sticky ruler if ready. Presentation-only: never touches
   `ww.viewport`, Y range, trace data, or the fetch pipeline.
3. **Wired into three trigger points**: the Workspace Sidebar's own
   `onResize` option; a `transitionend` listener on `#mainSidebarMenu`
   (guarded to `propertyName === "width"`) — the correct signal that an
   animated collapse/expand's width has actually finished changing,
   rather than resizing against a mid-transition value; and a
   `window.resize` listener (rAF-coalesced via a small shared
   `wwScheduleResizeAllVisiblePlots()` helper) as defensive, redundant
   coverage for real browser window resizes, given Plotly's own
   internal detection had just proven unreliable for a related case.
4. **CSS defense-in-depth**: `.ww-chart-wrap` gained `overflow: hidden`
   — a no-op once the resize fix above is correct (Plotly's own SVG
   already exactly fills the wrapper), but ensures any FUTURE gap in
   the resize wiring fails safely (clipped) instead of visually
   bleeding out of the panel frame, per this task's own explicit
   "the chart must actually resize correctly, don't merely hide a
   stale width with clipping" instruction — the resize fix is primary,
   this is a safety net, not a substitute.

### Test-infrastructure fix (not an application change)

`shellCreateHorizontalSplit()` now calls `requestAnimationFrame`
unconditionally at Init time (every real browser has this natively).
Re-running the full jsdom regression suite revealed six OLDER scratch
scripts (`phase2ca_check.mjs`, `phase2cb1/b2/b3/b3a_check.mjs`,
`phase2cc1_check.mjs`) were missing the `requestAnimationFrame`/
`cancelAnimationFrame` polyfill that later scripts (from
`phase2cc2_check.mjs` onward, once panel-height resize needed it)
already have — this silently aborted their entire inline `<script>`
evaluation partway through Init, cascading into dozens of unrelated-
looking failures. Patched all six with the exact same polyfill line
already used elsewhere (test infrastructure only) — confirmed the full
suite returns to the identical 20-failure baseline from immediately
before this task, zero new divergences from the actual code change.

### Tests

- **Frontend, new**: `phase3auat1_check.mjs` (scratch, not committed) —
  20/20 passing. Covers: `.ww-chart-wrap` containment CSS, Workspace
  Sidebar drag resizing every visible panel's Plotly instance AND the
  sticky ruler, zero waveform fetches during resize, byte-identical
  physical viewport before/after, no relayout call touching range/Y
  state as a side effect, rAF-coalesced scheduling (many raw
  pointermoves → far fewer resize calls), authoritative final resize on
  pointerup, pointercancel cleanup + its own final resize (matching the
  established `wwSetPanelHeight` contract), a subsequent drag after a
  cancelled one still working, Main Sidebar Menu expand/collapse both
  triggering a full reflow via `transitionend` (correctly scoped to the
  `width` property only), zero fetch/viewport-preserving on menu
  toggle, window resize triggering the same reflow path, rapid-fire
  window resize events coalescing to one pass (no runaway loop), zero
  fetch on window resize, Separate mode (all 6 lanes reflow) and Custom
  mode (all panels reflow), Phase 3A shell hierarchy unchanged, and
  panel-height resizing unaffected.
- **Frontend, existing**: the full Phase 2C-A through Phase 3A suites
  (264 checks, after the six-script polyfill fix) — the exact same
  20 pre-existing, already-documented failures, zero new divergences.
- **Backend**: zero diff, 278/278 passing in a fresh venv.

### Files changed

Modified only: `frontend/index.html`. No backend file, no CI/deployment
workflow file.

### Honest limitation

This sandboxed session has no real browser. Whether the waveform
canvas now genuinely stays visually contained during a real drag,
whether the reflow feels smooth (not janky) during continuous dragging,
and whether the `transitionend`-triggered Main-Sidebar-Menu reflow
looks correct in practice were **not** visually confirmed — only
structural/behavioral evidence (jsdom DOM/state assertions, CSS source
inspection) was verified. This remains for owner manual UAT.

---

## Phase 3A-UAT2 — Remove Duplicate Header Theme Control (2026-08-16)

`[FACT]` throughout. Phase 3A-UAT1's width-reflow fix passed owner UAT —
that issue is closed. The owner then requested one small, isolated UI
cleanup: the Global Header carried its own Light/Dark segmented control
(`#themeToggle`, mounted via `window.PowerwaveTheme.mountThemeToggle()`)
that duplicated the Main Sidebar Menu's existing "Settings" item (which
already flips the same Light/Dark preference). The owner wanted only one
theme entry point, keeping the Main Sidebar Menu's.

### Change

`frontend/index.html` only:

1. Removed the `<div id="themeToggle"></div>` element from
   `#globalHeaderActions` in the Global Header markup.
2. Removed the corresponding
   `window.PowerwaveTheme.mountThemeToggle(document.getElementById("themeToggle"))`
   call from Init.
3. Updated a stale code comment on the Main Sidebar Menu's "Settings"
   click handler that referenced the now-removed header control as "the
   primary, full segmented control" — it now correctly describes
   Settings as the sole theme entry point.

`#globalHeaderActions` is a plain `display: flex; gap: 10px` row with no
fixed widths or placeholder reserved for the removed element, so the gap
closes cleanly with zero CSS change needed. The shared `.theme-toggle`
CSS class was **not** touched or removed — it is also the class used by
the unrelated `#shellViewToggle` (Waveform/Table/Split) segmented
control, and `theme.js`'s `mountThemeToggle()` function itself was **not**
touched or removed — `frontend/waveform-prototype.html` (an isolated,
separate page, out of this task's scope) still mounts and uses it
unchanged.

### Theme behavior — unchanged, verified

All underlying theme mechanics are untouched: `theme.js`'s
`getTheme()`/`setTheme()`, the `powerwave.theme` `localStorage` key, the
cross-tab `storage`-event sync, the `powerwave:theme-change`
`CustomEvent`, and Plotly's own theme re-color via `relayout`/`restyle`
(zero waveform refetch) all work exactly as before — confirmed by test,
not just assumed, since removing only a UI mount point could not by
itself change any of these (they are consumed via `window.PowerwaveTheme`
directly by the Settings handler, never through the removed toggle's own
internal state).

### Tests

- **Frontend, new**: `phase3auat2_check.mjs` (scratch, not committed) —
  11/11 passing. Covers: `#themeToggle` absent from the DOM entirely,
  `#globalHeader` contains no Light/Dark-labeled buttons, Main Sidebar
  Menu's `#mainNavSettingsBtn` exists inside `.shell-nav-bottom` and
  still flips Light→Dark→Light on click, the preference persists across
  a simulated reload, theme change causes zero waveform refetch, theme
  change still triggers the existing per-panel Plotly chrome relayout
  (`paper_bgcolor`), the Global Header's remaining controls (Sources
  drawer toggle, Import, Waveform/Table/Split selector, Start new
  workspace) still render, Main Sidebar Menu collapse/expand still
  works, and the displayed-channel/panel state is undisturbed.
- **Frontend, existing suite fix**: `theme_crosshair_check.mjs`'s own
  pre-existing "theme toggle control renders and switches theme on
  click" test asserted `#themeToggle` exists in `index.html`'s real
  header markup — no longer true by design, so it was corrected in
  place (not deleted) to assert the element's absence instead, with a
  comment pointing to `phase3auat2_check.mjs` for full coverage and
  noting `mountThemeToggle()` itself remains proven functional via the
  very next block in the same file (`waveform-prototype.html`, unchanged).
- **Frontend, full regression suite**: re-ran every existing scratch
  script (Phase 2C-A through Phase 3A-UAT1) — the exact same 20
  pre-existing, already-documented failures, zero new divergences.
- **Backend**: zero diff, 278/278 passing in a fresh venv (no backend
  file touched).

### Files changed

Modified: `frontend/index.html` (application change), plus this record
and `CURRENT_STATE.md`/`HANDOFF.md` (project memory). No backend file,
no CI/deployment workflow file. `DECISIONS.md` DEC-031 was **not**
updated — this is a UI-cleanup refinement within an already-decided
architecture, not a new or corrected architectural decision, so no
governance update note was needed for this pass.

### Honest limitation

No real browser is available in this sandbox — visual confirmation that
the header now reads cleanly with no leftover gap, and that the Main
Sidebar Menu's Settings control remains comfortably reachable/usable in
both collapsed and expanded states, was reasoned through via the DOM/CSS
inspection above but not visually confirmed. Flagged for owner UAT.

---

## Phase 3A-UAT3 — Targeted Overflow and Containment Fixes (2026-08-16)

`[FACT]` throughout. An independent Codex audit of the Phase 3A shell
identified seven candidate overflow/containment risks (Findings A–G). The
audit's own local working tree could not reach GitHub (SSH authentication
failure), so per this task's explicit instruction, every finding was
independently re-verified by direct code inspection against canonical
`main` (fetched via the same HTTPS fallback used throughout this session)
before anything was implemented — none of the audit's own conclusions
were trusted blindly.

### Audit revalidation matrix

| Finding | Verdict | Evidence |
|---|---|---|
| A — responsive sidebar reopen button | **STILL PRESENT → FIXED** | `#shellSidebarToggleBtn { display: none; }` sat *after* the `@media (max-width: 900px)` override in source order; both selectors share identical specificity, so the later, unconditional rule always won — the reopen button was unreachable inside the drawer breakpoint. |
| B — sidebar channel table containment | **STILL PRESENT → FIXED** | `table.channels` (several columns + a `white-space: nowrap` action link) had no horizontal-scroll wrapper; the outer `details.channel-group` already has `overflow: hidden`, so an overly wide table would be silently CLIPPED (unreachable), not merely untidy. |
| C — source/detail metadata containment | **STILL PRESENT → FIXED** | `.detail-header h3`/`.meta` (station name, filenames) and `.stat .value` (recorder name, sampling-rate list) had no `overflow-wrap`; `.stat` (a CSS Grid item) had no `min-width: 0`. A long unbroken token could force the Workspace Sidebar's content wider. |
| D — modal / Custom Groups long-content containment | **STILL PRESENT → FIXED** | `.group-chip` wrote channel name + unit as raw text with no dedicated, shrinkable label element and no `max-width`; `.confirm-box p` had no `overflow-wrap`. |
| E — Waveform view visibility reflow | **STILL PRESENT → FIXED** | `shellSetActiveView()` only toggled the `hidden` attribute — it never called any resize function, so a width change while Waveform was hidden (still fully reachable from Table/Split, since sidebar/window resize isn't gated by active view) would leave Plotly's charts stale once Waveform became visible again. |
| F — responsive drawer-width override | **STILL PRESENT → FIXED** | `shellCreateHorizontalSplit()` persists the desktop width as an inline `style.width` (highest specificity short of `!important`), which unconditionally beat the drawer breakpoint's own `width: min(320px, 82vw)` CSS rule — a persisted desktop width could render as an unusably wide, viewport-overflowing drawer on a narrow screen. |
| G — Grouped/Custom legend containment | **STILL PRESENT → FIXED** | `.ww-legend-item`/`.ww-legend-label` (used by `wwRenderLegend()` in every layout mode) had no containment at all in the base/unscoped rule; only the Separate-mode overlay tag (`#wwPanels.ww-panels-unified .ww-legend-item/-label`) had `max-width`/ellipsis, confirming the audit's own framing exactly. |

No finding was rejected as invalid or found already-fixed — all seven were
confirmed present against current canonical `main` and fixed.

### Fixes implemented (frontend/index.html only)

- **A**: reordered the CSS so the base `display: none` rule now precedes
  the `@media (max-width: 900px)` override — no `!important`, pure
  source-order correction.
- **B**: `.group-body` (the wrapper both analog sub-grouped and digital
  ungrouped channel tables render into) gained `overflow-x: auto` — an
  intentional, scoped horizontal scroll; nothing truncated or hidden.
- **C**: `.detail-header h3`/`.meta` and `.stat .value` gained
  `overflow-wrap: anywhere` (full text stays visible, wraps in place);
  `.stat` (a grid item) gained `min-width: 0`.
- **D**: the channel-name+unit text inside a Custom Groups chip is now
  wrapped in its own `<span class="group-chip-label">` (JS markup change,
  mirroring the established `.ww-legend-label` pattern) with
  `min-width: 0; overflow-wrap: anywhere;`; `.group-chip` gained
  `max-width: 100%`; `.confirm-box p` gained `overflow-wrap: anywhere`;
  `.group-editor-box` gained `overflow-x: hidden` (defense-in-depth,
  mirroring the Phase 3A-UAT1 `.ww-chart-wrap` precedent — the chip fix
  is the actual containment mechanism); `.group-editor-header`/`-footer`
  gained `flex-wrap: wrap`.
- **E**: `shellSetActiveView()` now calls the existing
  `wwScheduleResizeAllVisiblePlots()` (Phase 3A-UAT1's own rAF-coalesced
  helper — no new resize mechanism) whenever the active view becomes
  `"waveform"`. Presentation-only; never touches `ww.viewport`, Y range,
  or the fetch pipeline.
- **F**: a `window.matchMedia("(max-width: 900px)")` listener (matching
  the CSS breakpoint exactly) now clears `#workspaceSidebar`'s inline
  width on entering drawer mode (letting the CSS `min(320px, 82vw)` rule
  govern) and reapplies the split helper's own remembered desktop width
  on returning to desktop — the persisted preference itself
  (`localStorage`/in-memory `width`) is never mutated, only the inline
  style is toggled around it.
- **G**: base (unscoped) `.ww-legend-item` gained `max-width: 220px`; a
  new base `.ww-legend-label` rule adds the same
  `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  min-width: 0;` ellipsis technique the already-UAT'd Separate-mode
  overlay tag uses — kept as a separate, lower-specificity rule so
  `#wwPanels.ww-panels-unified .ww-legend-item/-label` (Separate mode)
  is completely untouched and still wins there.

None of these are a broad CSS rewrite: every rule/JS change is scoped to
the exact selector or call site the corresponding finding named.

### Long-content behavior

Deterministic long-content fixtures (deliberately long, UNBROKEN tokens —
the actual containment risk, not just long normal text) were used for
filenames, station names, recorder/device names, channel names, units,
custom group names, and sample-rate text. In every case the FULL value
remains present in the DOM/data (confirmed by test) — only its visual
presentation changes (wrap-in-place for Sidebar/dialog metadata and
tables, so nothing is ever hidden; ellipsis for Grouped/Custom legend
chips specifically, mirroring the already-owner-approved Separate
treatment and consistent with `wwRenderLegend()`'s own existing design
note that full detail is always available via Plotly's native hover
tooltip).

### Small-screen containment

Only the seven targeted fixes above; no phone-UX redesign was performed.
Finding F's fix specifically prevents a persisted desktop width from
producing an oversized, viewport-overflowing drawer at the existing
`@media (max-width: 900px)` breakpoint — the breakpoint's own already-
designed `min(320px, 82vw)` safe width can now actually take effect.
Finding A restores the already-designed reopen affordance at that same
breakpoint. No new breakpoint, no new small-screen layout, no phone-
specific UI was added.

### Test-infrastructure fix (not an application change)

`window.matchMedia` is not implemented in jsdom at all. Since Finding
F's fix calls it unconditionally at Init, every existing scratch script
that runs the real inline script needed a polyfill or its `<script>` tag
would throw and abort partway through — the same failure class Phase
3A-UAT1 hit with the missing `requestAnimationFrame` polyfill. A
minimal, real (not a stub) `matchMedia` polyfill — evaluates `max-width:
Npx` against a mutable `window.innerWidth`, fires registered `'change'`
listeners via a `window.__setInnerWidth(px)` test helper — was added to
all 16 existing scripts that execute `index.html`'s inline script, plus
one script (`frontend_logic_check.mjs`) that also needed a
`requestAnimationFrame` polyfill it had never previously required (this
fix's initial sync call now reaches `shellCreateHorizontalSplit()`'s own
rAF-coalesced path unconditionally at Init, even at desktop width).
Confirmed by re-running the full suite before and after: the exact same
20 pre-existing, already-documented failures — zero new divergences.

### Tests

- **Frontend, new**: `phase3auat3_check.mjs` (scratch, not committed) —
  29/29 passing. Covers every finding (A–G) via CSS source-rule
  inspection plus DOM/state assertions with the long-content fixtures
  above, the Phase 3A-UAT1 Plotly containment invariant re-verified after
  all fixes, and regression checks (Main Sidebar Menu collapse/expand,
  panel-height resize, Grouped/Separate/Custom, Absolute/Elapsed, theme,
  Phase 3A shell hierarchy).
- **Frontend, existing**: the full Phase 1 through Phase 3A-UAT2 suites
  (293 checks, after the matchMedia/rAF polyfill fix) — the exact same 20
  pre-existing, already-documented failures, zero new divergences.
- **Backend**: zero diff, 278/278 passing in a fresh venv (no backend
  file touched).

### Files changed

Modified: `frontend/index.html` only (CSS + two small JS additions —
`shellSetActiveView()`'s resize call, and the Finding F
`matchMedia`/`shellSyncSidebarWidthForBreakpoint` block — plus the
`.group-chip-label` markup wrap). No backend file, no CI/deployment
workflow file. `DECISIONS.md` intentionally **not** touched — every fix
here is a targeted correction within the already-decided Phase 3A shell
architecture (DEC-031), not a new or revised architectural decision.

### Honest limitation

No real browser is available in this sandbox. Whether each fix looks
correct at real, continuous viewport widths (not just the discrete
values a `matchMedia` polyfill can simulate), whether the horizontal
scroll on the channel table feels usable in practice at 240px, and
whether the ellipsis/wrap choices read well visually were reasoned
through and verified structurally but not visually confirmed — flagged
for owner UAT.

---

## Phase 3A-UAT4 — Channel Filename Containment (2026-08-16)

`[FACT]` throughout. Owner manual UAT of Phase 3A-UAT3's overflow
hardening found ONE remaining real overflow case, with browser evidence:
in the Workspace Sidebar's Channels → source details section, the
uploaded CFG/DAT filenames (e.g. `260725_1309444309_Tanjung Bin
BEN6K.cfg` / `.dat`) could visibly extend past the Channels panel at a
narrowed Sidebar width, despite Phase 3A-UAT3's own Finding C already
having added `overflow-wrap: anywhere` to `.detail-header h3`/`.meta`.

### Root cause (established by code inspection, not guessed)

`.detail-header` is a flex CONTAINER (`display: flex`) with a single
flex ITEM child — an unnamed, unstyled wrapping `<div>` holding the
station-name `<h3>` and the filenames `.meta`. Phase 3A-UAT3's Finding C
fix put `overflow-wrap: anywhere` on the TEXT elements (`h3`/`.meta`)
but never gave their PARENT flex item its own `min-width: 0`. A flex
item's automatic minimum width defaults to its content's un-shrunk
("min-content") size (the well-known `min-width: auto` flex trap — the
exact same class of bug already fixed at the SHELL level in Phase
3A-UAT1/UAT3, just one level deeper here, inside the Channels detail
card rather than the shell's own regions). Text-level wrap rules only
take effect once the box AROUND the text is actually permitted to
become narrower than its unwrapped content — without `min-width: 0` on
that flex item, the whole station-name + filenames block stayed at its
full, un-shrunk width and visibly overflowed the Workspace Sidebar
regardless of the text's own `overflow-wrap` setting. `white-space`
inheritance was checked and ruled out (no ancestor of `.detail-header`
sets `white-space: nowrap`/`pre`); no `inline`/`span` wrapping issue was
found (`.meta` is already a block-level `<div>`); the actual filename
element already had the correct `overflow-wrap` property, just on a box
whose parent refused to shrink.

### Fix

The previously unnamed flex-item wrapper now has a real class,
`.detail-header-info` (`renderChannels()`'s own markup:
`'<div class="detail-header"><div class="detail-header-info">'`), with
`min-width: 0; max-width: 100%;` — the actual root-cause fix.
`.detail-header h3`/`.meta` additionally gained explicit `white-space:
normal; max-width: 100%;` alongside their existing `overflow-wrap:
anywhere` — `white-space: normal` documents (and guards against any
future accidental override) the already-default wrapping behavior;
`max-width: 100%` is a belt-and-braces cap at every link in the chain so
no element in this path can ever exceed its parent's width, even if a
future change reintroduces an oversized child. No truncation, no
ellipsis, no shortened/fake filename string — the full CFG/DAT filename
remains completely readable, wrapping across multiple lines at narrow
widths exactly as the owner's own example showed. `.group-body`'s
`overflow-x: auto` (Phase 3A-UAT3, Finding B, the channel TABLE's own
containment) is untouched and unrelated — this is a different element
in the same Channels section.

### Filename behavior at each Sidebar width

Verified structurally (no real browser in this sandbox) at 520px, the
320px default, and the 240px minimum: the filename text is always fully
present in the DOM (nothing truncated at the data level) and every
element in the containment chain (`.detail-header-info` → `.meta`) is
bounded by `min-width: 0`/`max-width: 100%`, so it cannot force its
parent — the Sidebar itself, or Main Workspace beside it — any wider.
At 240px the filename is expected to wrap across several lines, which
this task's own spec explicitly accepts as correct behavior; what is
not acceptable, and is now prevented, is horizontal escape.

### Long-token handling

Underscore-heavy segments and one deliberately long unbroken token
(stress fixture: `260725_1309444309_VERY_LONG_TANJUNG_BIN_GENERATING_
STATION_RECORDER_EVENT.cfg`/`.dat`) are handled by `overflow-wrap:
anywhere`, which (unlike `overflow-wrap: break-word`) is specified to
also reduce the element's own min-content contribution — meaning it
genuinely allows the box to shrink, not just visually wrap once already
narrow. `word-break: break-word` was deliberately NOT added — this
task's own instruction to use it "only if genuinely needed," and
`overflow-wrap: anywhere` alone is sufficient and already the modern,
well-supported mechanism for this.

### Regression preservation

Confirmed unchanged by test: Workspace Sidebar resize behavior and its
240–520px bounds, Main Workspace width reflow and Plotly resizing,
Grouped/Separate/Custom layout modes, the sticky time ruler, panel-
height resizing, the responsive drawer breakpoint, Custom Groups, and
header/status-bar layout. This is filename containment only — no other
Phase 3A shell rule was touched.

### Tests

- **Frontend, new**: `phase3auat4_check.mjs` (scratch, not committed) —
  12/12 passing. Covers: the root-cause CSS chain (`.detail-header-info`
  min-width/max-width, `.detail-header .meta` overflow-wrap/white-space/
  max-width), the markup change actually applying, the owner's own exact
  CFG and DAT filenames rendering in full, the longer underscore-heavy/
  unbroken-token stress fixture (CFG and DAT) rendering in full, a
  520px/320px/240px Sidebar-width matrix confirming the filename stays
  fully present and the Sidebar's own committed width is never altered
  by filename content, and confirmation that Main Workspace gains no
  inline width as a side effect of rendering long filenames.
- **Frontend, existing**: the full Phase 1 through Phase 3A-UAT3 suites
  re-run — the exact same 20 pre-existing, already-documented failures,
  zero new divergences.
- **Backend**: zero diff, 278/278 passing in a fresh venv (no backend
  file touched).

### Files changed

Modified: `frontend/index.html` only (CSS + one markup class addition).
No backend file, no CI/deployment workflow file. `DECISIONS.md`
intentionally **not** touched — a targeted correction within the
already-decided Phase 3A shell architecture (DEC-031) and its own Phase
3A-UAT3 containment pass, not a new or revised architectural decision.

### Honest limitation

No real browser is available in this sandbox. Whether the filename now
visibly wraps exactly as the owner's own reference example showed (e.g.
`260725_1309444309_` / `Tanjung Bin BEN6K.cfg` as two lines, or another
natural browser wrapping result) was reasoned through and verified
structurally (CSS rule inspection, DOM/data-level assertions) but not
visually confirmed — flagged for owner UAT.

---

## Phase 3B — Recordings Page and Upload Workflow (2026-08-16)

`[FACT]` throughout. See
[DECISIONS.md — DEC-032](DECISIONS.md#dec-032--recordings-page-as-a-first-class-application-page-one-recording--one-logical-event-cfgdat-sessionworkspace-backed-not-a-persistent-cloud-library-phase-3b)
for the full decision record (owner instruction, reasoning, alternatives
considered, impact) — this section is the implementation detail.

### Navigation

`shell.currentPage` (`"waveform"` | `"recordings"`) is new app-shell
state, deliberately separate from `shell.activeView` (`"waveform"` |
`"table"` | `"split"`, unchanged, still scoped to sub-views WITHIN the
Waveform page). `shellSetCurrentPage()` toggles `#workspaceRow`/
`#pageRecordings` visibility — the same "hide, don't destroy" mechanism
Phase 3A's `shellSetActiveView()` already established for Table/Split,
now applied one level up. Main Sidebar Menu's "Workspace" item was
renamed "Waveform" (`#mainNavWaveformBtn`); a new, ENABLED "Recordings"
item (`#mainNavRecordingsBtn`) was added right after it — both real
destinations now, unlike the still-`disabled` Table/Tools/Reports
placeholders. The Global Header's Waveform/Table/Split selector
(`#shellViewToggle`) and the responsive Sources drawer toggle
(`#shellSidebarToggleBtn`) are both scoped to the Waveform page
specifically — hidden via a direct `.style.display` toggle (not the
`hidden` attribute) while on Recordings, mirroring Phase 3A-UAT3's
Finding F pattern, since `#shellSidebarToggleBtn` already has
higher-specificity `#id` CSS rules governing its own responsive display
that only an inline style can reliably beat regardless of viewport.

### Waveform state preservation

Confirmed by test, not assumed: navigating Waveform → Recordings →
Waveform preserves the physical viewport (byte-identical), layout mode
(Grouped/Separate/Custom), Custom Groups, panel heights, and time mode
(Absolute/Elapsed) exactly, with **zero waveform refetch** caused by the
navigation itself. Returning to Waveform schedules
`wwScheduleResizeAllVisiblePlots()` (Phase 3A-UAT1/UAT3's own helper,
no new mechanism) in case the available width changed while
`#workspaceRow` was hidden — the exact same staleness risk Phase
3A-UAT3's Finding E already identified and fixed for the Table/Split
placeholder case, recurring one level up here.

### Bottom Status Bar

Preserves its Phase 3A geometry exactly (no redesign). The four
waveform-specific items (Station/Sample rate/Duration/Displayed
channels) are hidden via `shellSetStatusBarWaveformFieldsVisible()`
while on Recordings — their underlying VALUES are never cleared, only
hidden, so returning to Waveform shows the correct last-known values
instantly with zero recomputation. The "Workspace" item (workspace-level
identity, not waveform-specific) stays visible on both pages.

### Recording abstraction

One `SourceSummaryOut` (one CFG+DAT pair, as the backend has always
modeled it) is always exactly one Recordings row — confirmed by test,
not merely assumed from the existing API shape. `recordingDisplayName()`
prefers the real `station_name`; falls back to the CFG filename (or the
first filename) only when the station name itself is blank/missing —
never invents a fault classification or description.

### Recordings page

Heading: "Recording Events" (compact Main Sidebar label: "Recordings").
Columns, using only real backend metadata (`Do NOT show empty
decorative columns`, per this task's own instruction — a separate
"Station" column was deliberately OMITTED since `recordingDisplayName()`
already prefers station_name as the primary Recording label in the
common case, which would make a same-content Station column genuinely
redundant by this design's own choice, not merely incomplete data):
**Recording** (display name + the full CFG/DAT filenames as contained
secondary text, reusing Phase 3A-UAT4's `overflow-wrap: anywhere`/
`min-width: 0` containment technique), **Station**, **Recorder**,
**Channels** (`NA + MD`, mirroring Detego's own compact convention —
layout only, no Detego colors/branding), **Duration**, **Imported**
(`created_at`, a real timezone-aware backend timestamp — distinct from
the deliberately timezone-naive per-sample COMTRADE timestamps
elsewhere in this app), **Actions**. "Format" was deliberately NOT its
own column this phase — with only COMTRADE currently enabled it would
read identically on every row today; format-readiness for CSV/Excel
lives in the upload modal's own provider model instead (section 14).
Empty state: "No recordings loaded in this session." + an Upload New
button — never implies a permanent library is empty. Search: a simple
client-side substring filter across recording name/station/filename/
format, using the exact same `data-search` + hidden-toggle technique
`setupChannelSearch()` already established. The table sits inside an
intentional `overflow-x: auto` wrapper — the same Phase 3A-UAT3 Finding
B containment technique — so it never forces the page, and by extension
Work Area, any wider.

### Upload workflow

"Upload New" (Recordings page, top-right) and the Global Header's
"Import" shortcut both open the SAME modal (`openUploadModal()`/
`shellOpenImport()` respectively — `shellOpenImport()` now navigates to
Recordings first, then opens the modal, rather than maintaining a
separate import path). The modal's file-input fields are rendered from
`RECORDING_FORMATS` — a small array of `{ id, label, enabled, files:
[{key, label, accept}] }` definitions. COMTRADE (`enabled: true`)
renders the exact same two required inputs (cfg/dat) the old
always-visible sidebar form used, with unchanged validation, unchanged
~100 MB client-side size guidance, and the exact same
`POST .../sources` multipart contract, `friendlyErrorMessage()`
mapping, and ephemeral-upload/staging semantics as before — this is a
UI relocation and structural generalization, not a parser or backend
contract change. CSV and Excel are listed (`enabled: false`) as real,
visible, `disabled` `<option>`s — the browser natively prevents
selecting a disabled option, so they cannot be falsely accepted; no
parser exists for either. Loading/error/success states reuse the
existing `setUploadStatus()`/`clearUploadStatus()` mechanism, retargeted
to the modal's own status element. Double-submit is prevented by an
explicit `uploadModalSubmitting` guard, which also blocks Cancel/
close/Escape/backdrop-click while an upload is actively processing
(section 25) — the same safe-dismissal pattern already established for
the Custom Groups editor. **On success**: the modal closes and clears
its own status immediately; the recording appears in the list; NO
auto-navigation to Waveform and NO auto-selecting the new source into
the Channels panel — that remains the Recordings row's own explicit
"Open / Analyse" action, per this task's own preferred
upload → list → user-chooses-Open/Analyse flow.

### Row actions

**Open / Analyse** calls the existing `selectSource(sourceId)`
unchanged (same parser/import semantics; never re-uploads; never
creates a duplicate source entry) and then `shellSetCurrentPage
("waveform")`. It does not auto-display any channels — the existing
checkbox + "Add selected" step is unchanged. **Remove** reuses the
existing `requestRemoveSource()`/`performRemoveSource()` confirmation
flow completely unchanged (same dialog, same wording, same DELETE
call), now also called from the Recordings row — updating the
Recordings list, the Workspace Sidebar's source list, and the
waveform-displayed-channel state for that source consistently from one
call (`refreshAllSourceViews()`), confirmed by test.

### Backend change (additive only)

`SourceSummaryOut` gained `duration_seconds`/`sample_count` — both
already computed and stored on `SourceMetadata` at import time since
Phase 2A; no new storage, no new computation, no change to any existing
field, no new endpoint. This avoids the Recordings list needing a
separate `.../channels` fetch per listed row just to show Duration,
which would have multiplied network calls on every list render.

### Session recording list (no second repository)

The Recordings page renders from the SAME `GET .../sources` response
the Workspace Sidebar's own source list already fetches
(`fetchSourcesList()`, extracted from the pre-existing
`refreshSourceList()`). A new shared `refreshAllSourceViews()` refreshes
BOTH presentations together from one fetch, called at every point that
actually changes the source set (upload success, remove, workspace
reset, and initial page load) — confirmed by test that an uploaded
source appears in the Recordings list and that Remove updates both the
list and the waveform-displayed-channel state consistently, regardless
of which page is currently active.

### Storage semantics (unchanged philosophy)

The Recordings page reflects the current browser/workspace session's
`WorkspaceRegistry` state — the same ephemeral, in-memory,
never-persisted-to-disk model DEC-012/DEC-015/DEC-019 already
established. No database table, no object-storage retention, no
user-account recording history, no upload history across sessions were
added. UI copy avoids implying a permanent cloud library.

### A real CSS bug caught and fixed before shipping

`#workspaceRow` and `#bottomStatusBar .shell-status-item` both have
`display: flex` as their own author CSS — which beats the UA
stylesheet's default `[hidden] { display: none }` rule by ORIGIN alone
(author always wins over UA, regardless of specificity or source
order). Without an explicit `[hidden]` override on each, this phase's
own `.hidden = true` toggles (hiding the Waveform page; hiding the
waveform-only Status Bar fields) would have had NO visible effect at
all. Caught by manual review (not by the jsdom test suite, which has no
real CSS layout engine and cannot detect this class of bug) and fixed
with two targeted `[hidden]` override rules, mirroring the pattern this
project already uses elsewhere (`.confirm-overlay[hidden]`,
`details.channel-group[hidden]`, `#pageRecordings[hidden]`, which was
added proactively and correctly the first time).

### Tests

- **Frontend, new**: `phase3b_check.mjs` (scratch, not committed) —
  30/30 passing. Covers navigation (Recordings enabled in the Main
  Sidebar Menu, Waveform ⇆ Recordings round-trip, viewport/layout-mode/
  panel-height/time-mode preservation, zero refetch, Status Bar field
  visibility, Plotly resize-on-return), the recording list (empty state,
  one-row-per-CFG+DAT-pair, real metadata, no fabricated fields, long-
  name/filename containment, search, Remove updating both the list and
  waveform source state), and the upload modal (open/Cancel/Escape/
  backdrop/close, COMTRADE file-field rendering, CSV/Excel listed-but-
  disabled, CFG/DAT required, the full success path closing the modal
  and adding one row, error state, double-submit prevention, mid-upload
  dismissal guard, the Header Import shortcut opening the same modal).
- **Frontend, existing suite corrections**: `frontend_logic_check.mjs`'s
  TEST 3/4 (originally testing a "stale success banner" that persisted
  outside the old always-visible upload form) were updated in place —
  Phase 3B's own modal now closes and clears its own status immediately
  on success, so that specific persistent-banner premise no longer
  applies by design; the underlying remove-confirmation-flow and
  cross-source-isolation properties they protected are still tested,
  now driven through the modal. `phase3a_check.mjs`'s own Import-button
  test was similarly updated (it asserted the old `#cfgInput` element,
  removed by design) to confirm the new Recordings-navigation-plus-
  modal behavior instead. Both corrections follow this project's
  established precedent (e.g. Phase 2C-C4B, Phase 3A-UAT2) of updating
  assertions in place rather than leaving them failing.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures across the full suite, zero new
  divergences, confirmed by running the whole suite before and after.
- **Backend**: `test_sources_api.py` gained two new/extended assertions
  for the new `duration_seconds`/`sample_count` fields, cross-checked
  against the pre-existing `.../channels` endpoint's own `timebase.*`
  values rather than a hardcoded number. 279/279 passing (278 + 1 new
  test), zero regressions.

### Files changed

Modified: `frontend/index.html` (the bulk of this phase),
`backend/app/schemas/source.py` (additive DTO fields),
`backend/tests/test_sources_api.py` (new coverage for those fields).
No CI/deployment workflow file, no other backend file.

### Honest limitation

No real browser is available in this sandbox. Whether the Recordings
page reads as clear/simple/engineering-focused in practice, whether the
upload modal's format selector and file-field rendering feel natural,
and whether the long-filename wrapping in the Recording column looks
right at real widths were reasoned through and verified structurally
(DOM/state assertions, CSS rule inspection) but not visually confirmed
— flagged for owner UAT.

---

## Phase 3B-UAT1 — Recording Row Divider Alignment (2026-08-17)

`[FACT]`. Owner manual UAT of the Recordings page found one cosmetic
issue: the Actions column's bottom row divider sat visibly higher than
the divider under every other column, instead of one continuous line
across the full row width.

**Root cause (established by code inspection, not guessed)**: the
Actions `<td>` carried the `.recording-actions` class directly
(`<td class="recording-actions">`), and that class sets
`display: flex` — overriding the cell's `display` away from the
default `table-cell`. That removed it from the browser's normal
same-row-height cell-stretching behavior every OTHER (unstyled-display)
`<td>` in the row still received, so the Actions cell collapsed to its
own shorter content height while sibling cells stretched to the row's
tallest cell. Its `border-bottom` (the same shared rule every cell
already uses, `table.recordings th, td { border-bottom: ... }`) was
therefore drawn at a different, higher position whenever any other cell
in that row was taller — which is also why the misalignment was
reported as inconsistent/cosmetic rather than a hard layout break.

**Fix**: the flex layout (`display: flex; gap: 8px;`) now lives on an
inner `<div class="recording-actions">` wrapping the two action
buttons, inside a plain, unclassed `<td>`. The `<td>` itself is once
again a normal table-cell, so it stretches and aligns its border
exactly like every other cell in the row — the row (`<tr>`), not
independent per-cell styling, is what makes every cell share one bottom
boundary. No column widths, button behavior, Open/Analyse/Remove
handlers, search, containment (Phase 3A-UAT4's `overflow-wrap`/
`min-width` technique on `.recording-name`/`.recording-files` is
untouched), or responsive horizontal scrolling were changed.

### Tests

- **Frontend, new**: `phase3buat1_check.mjs` (scratch, not committed) —
  7/7 passing. Confirms no CSS/markup ties the flex class to a `<td>`
  anywhere in the source; the Actions cell in a rendered row is a plain,
  unclassed `<td>` wrapping the inner flex div; the shared
  `border-bottom` rule is the only one that applies (no competing,
  more-specific rule for the Actions column); the same corrected
  structure holds across multiple rows; a long/wrapping recording name
  doesn't change the Actions cell's structure; and Open/Analyse and
  Remove both remain fully functional after the change.
- **Frontend, existing**: the full Phase 1 through Phase 3B suites
  re-run — the exact same 20 pre-existing, already-documented failures,
  zero new divergences.
- **Backend**: zero diff, 279/279 passing in a fresh venv (no backend
  file touched).

### Files changed

Modified: `frontend/index.html` only (one CSS comment, one markup
change moving `.recording-actions` from the `<td>` to an inner `<div>`).
No backend file, no CI/deployment workflow file. `DECISIONS.md` not
touched — a cosmetic correction within the already-decided Phase 3B
Recordings page (DEC-032), not a new/revised decision.

### Honest limitation

No real browser is available in this sandbox. Whether the row divider
now visually reads as one continuous line across the full table width,
exactly as the owner's own reference evidence called for, was reasoned
through via the CSS/markup root-cause fix above but not visually
confirmed — flagged for owner UAT.

---

## Phase 3B-UAT2 — Remove Duplicate Waveform-Page Import / New-Workspace Actions (2026-08-17)

`[FACT]`. The owner established a clearer page-responsibility split:
Recordings owns recording/session management (upload/import, Open/
Analyse, Remove, and now whole-workspace lifecycle); Waveform stays
engineering-analysis-only. Two Global Header controls previously visible
regardless of page — "Import" and "Start new workspace" — duplicated
what Recordings already provides.

**Change**: the Global Header's own "Import" shortcut
(`#shellImportBtn`, and the now-unused `shellOpenImport()` function)
was removed entirely — Recordings' own "Upload New" button already
opens the identical Upload Recording modal, so a second header-level
entry point to the same action was redundant. "Start new workspace"
(`#newWorkspaceButton` + its `#workspaceResetError` banner) was
relocated — same element IDs, same `startNewWorkspace()`/
`resetToNewWorkspace()` logic, completely unchanged — from the Global
Header into the Recordings page's own header row, grouped with "Upload
New" in a new `.recordings-header-actions` wrapper. `.recordings-header`
gained `flex-wrap: wrap` so the now-larger action group wraps safely at
narrow widths instead of overflowing.

**Explicitly unchanged**: the whole-workspace reset lifecycle itself
(confirmation, DELETE-then-rotate order, failure handling, DEC-018) —
only WHERE the trigger button lives moved. `startNewWorkspace()`'s own
`document.getElementById("sourceList").children.length > 0` check still
works correctly regardless of page, since the Workspace Sidebar's
`#sourceList` stays in the DOM (only hidden, never removed) when
navigating to Recordings. "Clear workspace" (`#clearWorkspaceBtn`, in
the Waveform toolbar) is untouched and remains the distinct,
displayed-channels-only operation it always was — confirmed by test
that it never calls the whole-workspace DELETE endpoint.

### Tests

- **Frontend, new**: `phase3buat2_check.mjs` (scratch, not committed) —
  14/14 passing. Covers: no Import control anywhere in the document;
  `#newWorkspaceButton` no longer inside `#globalHeader`; Recordings
  page contains both Upload New and Start new workspace; exactly one
  `<form>`/upload modal and exactly one `#newWorkspaceButton`/
  `#newWorkspaceConfirmOverlay` exist (no duplicate implementations);
  Upload New still opens the one modal; Start new workspace still opens
  the existing confirmation (not an immediate reset); Cancel is a true
  no-op; a successful confirm still issues exactly one whole-workspace
  DELETE and clears/rotates state (waveform-displayed-channels included);
  a failed reset leaves sources untouched with the existing error shown;
  Waveform → Recordings and Recordings → Waveform navigation both cause
  zero workspace-DELETE calls and leave displayed channels/sources
  untouched; Clear workspace remains present, functional, and distinct
  from Start new workspace.
- **Frontend, existing suite corrections**: `phase3b_check.mjs`,
  `phase3a_check.mjs`, and `phase3auat2_check.mjs` each had one
  assertion updated in place where it referenced the now-intentionally-
  removed `#shellImportBtn`/`shellOpenImport()` — following this
  project's established precedent of updating assertions rather than
  leaving them failing.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.
- **Backend**: zero diff, 279/279 passing in a fresh venv (no backend
  file touched — this is a pure UI-relocation task).

### Files changed

Modified: `frontend/index.html` only. No backend file, no CI/deployment
workflow file. `DECISIONS.md` not touched — a UI relocation within the
already-decided DEC-032 Recordings/Waveform architecture, not a new or
revised decision.

### Honest limitation

No real browser is available in this sandbox. Whether the Global
Header now reads as appropriately simplified on the Waveform page, and
whether the Recordings page's two grouped actions (Upload New, Start
new workspace) read clearly with Upload New still visually primary,
were reasoned through but not visually confirmed — flagged for owner
UAT.

---

## Phase 3B-UAT3 — Recordings Header Action Cleanup (2026-08-17)

`[FACT]`. Two small refinements to the Recordings page header, following
directly from Phase 3B-UAT2's own relocation work.

**Order**: "Start new workspace" and "Upload New" were already grouped
together in `.recordings-header-actions` (Phase 3B-UAT2); this pass
reordered them to `[ Start new workspace ] [ Upload New ]` (secondary
action first, primary action last, closest to the table it affects) per
the owner's preferred layout. Visual weight (`.secondary` vs. the
unclassed/primary `#recordingsUploadBtn`) is what marks Upload New as
the stronger action, not DOM order — confirmed unchanged: Upload New
remains unclassed (primary button style), Start new workspace remains
explicitly `.secondary`. No "Import" button exists anywhere in the
document (it was already fully removed in Phase 3B-UAT2, not just
hidden) — confirmed by test, not re-added.

**Button typography**: reviewed font-size across every button class
app-wide (base/primary `button`, `.secondary`, `.danger`,
`.danger-solid`, `.theme-toggle button` in theme.css, `.shell-nav-item`).
Found one real, small inconsistency: `.secondary` (0.8rem) and `.danger`
(0.78rem) were two separate, near-duplicate literal values for the same
"smaller than the primary action" tier — the two classes are frequently
paired in the same row (e.g. Recordings' own Open / Analyse +
Remove). Consolidated into one shared token, `--button-font-size-compact:
0.8rem`, referenced by both. The primary/base `button` size (0.9rem) and
`.theme-toggle button`'s own toolbar/segmented-control size (0.76rem,
theme.css, deliberately the most compact tier) were left untouched —
both are intentionally distinct tiers, not accidental drift, matching
the owner's own "consistent hierarchy, not necessarily identical size"
instruction. No other typography was touched.

`.recordings-header` gained no new CSS beyond what Phase 3B-UAT2 already
added (`flex-wrap: wrap`); the action group still wraps safely at
narrow widths with the reordered buttons.

### Tests

- **Frontend, new**: `phase3buat3_check.mjs` (scratch, not committed) —
  13/13 passing. Covers: no Import control anywhere; Upload New and
  Start new workspace both present on Recordings; both sit in the same
  `.recordings-header-actions` group with Start new workspace preceding
  Upload New; Upload New stays unclassed/primary, Start new workspace
  stays `.secondary`; both still call their existing, completely
  unchanged handlers (opens the one upload modal / opens the existing
  confirmation dialog); no duplicate `<form>`/upload-modal/
  `#newWorkspaceButton`/`#newWorkspaceConfirmOverlay`/`shellOpenImport`
  exist; the action group's `flex-wrap` containment rule is present;
  the shared `--button-font-size-compact` token exists and both
  `.secondary`/`.danger` reference it; the primary and toolbar/segmented
  button sizes remain their own distinct, untouched tiers; and the full
  existing Recordings workflow (search, Open/Analyse, Remove) remains
  functional.
- **Frontend, existing**: the full Phase 1 through Phase 3B-UAT2 suites
  re-run — the exact same 20 pre-existing, already-documented failures,
  zero new divergences (this pass needed no corrections to any existing
  test file).
- **Backend**: zero diff, 279/279 passing in a fresh venv (no backend
  file touched).

### Files changed

Modified: `frontend/index.html` only (one CSS token + two font-size
references, one markup reorder). No backend file, no CI/deployment
workflow file. `DECISIONS.md` not touched — a cosmetic/ordering
refinement within the already-decided DEC-032 Recordings/Waveform
architecture, not a new or revised decision.

### Honest limitation

No real browser is available in this sandbox. Whether the reordered
`[ Start new workspace ] [ Upload New ]` layout reads correctly, and
whether the small font-size unification is visually imperceptible (as
intended — 0.8rem vs. 0.78rem is a very small change) rather than
introducing any visible shift, were reasoned through but not visually
confirmed — flagged for owner UAT.

---

## Phase 3B-UAT4 — Recordings as Default Entry Page (2026-08-17)

`[FACT]` throughout. See
[DECISIONS.md — DEC-033](DECISIONS.md#dec-033--recordings-is-the-applications-default-fresh-entry-page-no-separate-landingdashboard-page-phase-3b-uat4)
for the full decision record — this section is the implementation
detail.

### Default entry

`shell.currentPage`'s default value changed from `"waveform"` to
`"recordings"`. `shellSetCurrentPage("recordings")` is now called
explicitly near the start of Init — the SAME function every other
in-app page navigation already goes through, not a separate "initial
page" code path. That call's own existing `if (page === "recordings")
refreshAllSourceViews();` branch now supplies the Init-time Recordings
list fetch, so the old unconditional trailing `refreshAllSourceViews();`
call at the very end of Init was removed — a fresh load still fetches
the source list exactly once, not twice.

### No visible flash

The static HTML defaults were updated to match, rather than relying
solely on script-execution-before-first-paint timing: `#workspaceRow`
now starts with the `hidden` attribute, `#pageRecordings` no longer
does, and `#mainNavWaveformBtn`/`#mainNavRecordingsBtn`'s
`aria-current` attributes were swapped (`"false"`/`"true"`) to match
what `shellSetCurrentPage()` itself would set at runtime. This is
belt-and-suspenders robustness, not strictly required by browser
script-execution timing, but removes any dependency on that timing
being reliable.

### No routing framework

The app has no URL-aware navigation at all. Per this task's own
explicit "do not build a routing framework just for this if the
current app does not need one," no `history.pushState`/`popstate`
handling or path-based routing was introduced — the single default-
state change is the smallest robust implementation of "fresh entry
opens Recordings." This does not block a real router being introduced
later if the product needs shareable/bookmarkable URLs.

### No landing/dashboard page

No separate Powerwave landing/dashboard page was added ahead of
Recordings — Recording Events itself is the operational entry page, per
the owner's own explicit instruction. No placeholder/fake dashboard
content (recent activity, saved workspaces, etc.) was invented.

### Fresh entry vs. in-session navigation

`shellSetCurrentPage()` itself was not modified — only its default
INITIAL value changed. The already-established "hide, don't destroy"
navigation behavior (Recordings ⇆ Waveform preserves viewport, layout
mode, Custom Groups, panel heights, and time mode across any number of
round trips, with zero waveform refetch) is unaffected — confirmed by
test with a full Recordings → Open/Analyse → Waveform → Recordings →
Waveform round trip building up real analysis state first.

### Global Header

Unaffected by this specific change — Phase 3B-UAT2/UAT3 had already
relocated every page-specific management action (Import removed
entirely; Start new workspace + Upload New living in the Recordings
page's own header row) off the Global Header. This decision's own
product-flow framing (recorded in DEC-033) endorses that standing
arrangement as correct going forward: the Global Header stays reserved
for genuinely global application/user-level functions, not page-
specific actions, regardless of which page is the default.

### Tests

- **Frontend, new**: `phase3buat4_check.mjs` (scratch, not committed) —
  8/8 passing. Covers: fresh initialization selects Recordings with no
  click; the Recordings Main Sidebar Menu item is active initially
  (Waveform is not); `#workspaceRow` starts hidden and `#pageRecordings`
  starts visible; zero waveform panels/displayed channels/waveform
  fetches are constructed on fresh entry, and the waveform-only Status
  Bar fields start correctly hidden; the Recordings list is fetched
  exactly once at Init (not twice); navigating to Waveform and back to
  Recordings both still work correctly from the new default; and a full
  Recordings → Open/Analyse → Waveform → Recordings → Waveform round
  trip (with real viewport/layout-mode/panel-height/time-mode state
  built up first) preserves all of it with zero refetch. No URL-path
  tests were added, since none were implemented (per this task's own
  instruction to only test paths actually implemented).
- **Frontend, existing suite correction**: one assertion in
  `phase3buat2_check.mjs` that had implicitly assumed Waveform was the
  default page (a sanity check, not the test's actual subject) was
  updated to explicitly navigate to Waveform first — following this
  project's established precedent of updating assertions in place
  rather than leaving them failing.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.
- **Backend**: zero diff, 279/279 passing in a fresh venv (no backend
  file touched — this is a pure frontend default-state change).

### Files changed

Modified: `frontend/index.html` only. No backend file, no CI/deployment
workflow file.

### Honest limitation

No real browser is available in this sandbox. Whether a fresh page load
genuinely shows Recordings with no visible flash of the old Waveform
default, and whether the product flow reads naturally in practice, were
reasoned through structurally but not visually confirmed — flagged for
owner UAT.

---

## Phase 3B-UAT5 — Move Recording Metadata from Waveform to Recordings (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry — this is a UI/data-
relocation refinement within the already-decided DEC-032 Recordings
architecture, similar in weight to UAT1–UAT3 (none of which needed a new
DEC entry either).

### Owner request

The Waveform Workspace Sidebar's vertical metadata card stack (Recorder,
Nominal Frequency, Timing Mode, Samples, Duration, Sampling Rate(s),
Start Time, Trigger Time) was relocated to the Recordings page, attached
to the exact recording it describes, via a per-row expandable "Details"
panel — not a modal, drawer, or separate page.

### Waveform sidebar

`renderChannels()`'s `.stat-grid` block (built from `statCard()` calls)
was removed entirely. The `.detail-header` identity block (station name
+ original filenames) was deliberately KEPT — this is active source
identification still needed while analysing waveforms, not the
enumerated metadata the owner asked to relocate. Channels
section/search/selection/Add-selected and all analysis controls are
untouched.

### Recording Details UX

A `[ Details ]` button was added to each Recordings row's existing
`.recording-actions` (order: `[ Details ] [ Open / Analyse ] [ Remove ]`).
Clicking it toggles a sibling `<tr class="recording-details-row">`
(`<td colspan="7">`) directly beneath that row — reusing the existing
`.stat-grid`/`.stat`/`statCard()` machinery verbatim (inheriting its
established Phase 3A-UAT3 containment rules — `min-width: 0` on `.stat`,
`overflow-wrap: anywhere` on `.stat .value` — automatically, since
nothing about that CSS is scoped to the Waveform sidebar).

**Design choice — multiple rows may be expanded simultaneously** (not a
single-open accordion). Chosen as the simpler implementation, and
consistent with this codebase's own existing collapsible `<details>`
elements (Analog/Digital channel groups), which likewise never enforce
single-open-at-a-time behavior anywhere else in the app. Tracked in a
small module-level `recordingsExpandedDetails` Set, keyed by
`source_id`, so an open panel survives an unrelated list refresh (e.g.
removing a *different* recording) instead of silently collapsing.

### Metadata fields

Recorder, Nominal frequency, Timing reference, Samples, Duration,
Sampling rate(s), Start time, Trigger time, CFG filename, DAT filename.
Start/Trigger Time use the same `.replace("T", " ")` string technique
already established for the old Waveform-sidebar rendering — deliberately
NOT `new Date(...)`, which would silently round COMTRADE's microsecond-
precision timestamps to JS Date's millisecond precision.

### Timing Mode investigation (Step 14 — critical)

Confirmed via direct code inspection of `backend/app/domain/timing.py`'s
own docstring and its existing frontend consumer,
`wwTimeModesForChannel(channel)`:

`TimingInformation.timing_reference` is genuine, permanent, backend-
computed, source-level recording metadata — parsed once from the
COMTRADE record at import time ("absolute" when start_time/trigger_time
are real recording timestamps, "relative_elapsed" when the waveform
data's own time axis is authoritative). It already gates which display
modes the Waveform page even offers via `wwTimeModesForChannel()`. This
is architecturally and semantically **distinct** from `ww.timeMode` (the
user's live, in-session Absolute/Elapsed display-toggle selection in the
Waveform page) — the two have never shared storage or a code path.

**Conclusion**: safe and correct to relocate as recording metadata. The
field was relabeled "Timing reference" (was "Timing mode" in the old
Waveform sidebar) specifically to remove the exact ambiguity risk the
owner flagged — "Timing mode" reads too easily as if it were describing
the current view toggle rather than a source-level capability flag.

### Metadata authority / zero-refetch

`SourceSummaryOut` (`backend/app/schemas/source.py`) gained
`timing_reference`/`start_time`/`trigger_time`/`sampling_rates` —
purely additive; all four already existed on the domain `SourceMetadata`
(computed once at import time, already mirrored on `TimebaseOut`); no
new storage, no new computation. This lets the Details panel render
entirely from the SAME already-fetched `GET .../sources` list response
that already powers the Recordings table — expanding/collapsing a
Details panel is a pure client-side toggle: zero fetch, zero reparse,
zero re-upload, zero `.../channels` request. Recorder/Station come
straight from backend metadata (never inferred from filenames); missing
fields fall back to "—" per existing convention.

### Multi-recording correctness

Each details `<tr>` is built from that same loop iteration's own
`source` object — never a shared/global "current source" reference — so
there is no possible cross-row leakage; confirmed by a dedicated test
with two recordings carrying different recorder names.

### Open/Analyse, Remove, search

Unchanged. `performRemoveSource()` now also deletes the removed
source's id from `recordingsExpandedDetails` (hygiene — the row won't be
re-rendered anyway, but this avoids a stale Set entry). Removing a
recording removes its details row along with it (both are the same
`<tr>` subtree). `applyRecordingsSearchFilter()` now also hides/shows
each recording's sibling details row in lockstep with its own row, so a
filtered-out row's (possibly still-expanded) details panel can never
remain visible as an orphan; clearing the search restores it.

### Responsive / theme

No new hardcoded colors — `.recording-details-row td` uses
`var(--surface-tint)`; everything else rides the reused `.stat-grid`
tokens. Long filenames wrap via the same established containment, never
ellipsized.

### Tests

- **Backend**: one additive test,
  `test_list_includes_timing_reference_and_timestamps` (cross-checks the
  list endpoint's new fields against the `.../channels` endpoint's own
  `timebase.*` values, avoiding a hardcoded-value guess). 280/280
  passing (279 baseline + 1 new).
- **Frontend, new**: `phase3buat5_check.mjs` (scratch, not committed) —
  14/14 passing. Covers: `.stat-grid` gone from the Waveform Channels
  panel while `.detail-header` remains; zero new fetches on entering
  Waveform; a Details control exists per row, collapsed by default;
  expand/collapse toggles the correct row and button label/
  `aria-expanded`; multiple rows can be expanded at once; every field
  (including the relabeled "Timing reference" and full-precision Start/
  Trigger Time) renders correctly; CFG/DAT filenames shown; long
  filenames contained; two recordings' details never leak into each
  other; Remove clears expanded state and the row cleanly; search hides
  and restores an orphan-free details panel; expand/collapse causes zero
  network requests of any kind.
- **Frontend, existing suite correction**: three pre-existing scripts
  (`phase3auat3_check.mjs`, `phase3b_check.mjs`, `phase3buat1_check.mjs`,
  `phase3buat3_check.mjs`) had assertions that implicitly assumed either
  the old Waveform-sidebar recorder-name rendering (now relocated) or
  that `#recordingsTableBody tr` selects only real recording rows (now
  also matches each row's own sibling `.recording-details-row`) —
  updated in place, following this project's established precedent,
  rather than left failing. Six other pre-existing scripts' mock
  `GET .../sources` fixtures were extended with the four new
  `SourceSummaryOut` fields (matching the real backend response shape)
  since the new Details panel now reads them unconditionally on every
  Recordings render.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.

### Files changed

`frontend/index.html`, `backend/app/schemas/source.py`,
`backend/tests/test_sources_api.py`.

### Honest limitation

No real browser is available in this sandbox — the visual layout of the
expanded Details panel (spacing, grid wrapping at narrow widths, Light/
Dark appearance) was reasoned through structurally against existing
`.stat-grid` CSS but not visually confirmed — flagged for owner UAT.

---

## Phase 3B-UAT6 — No Duplicate Metadata in Recording Details (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry — a targeted content/
layout refinement of the Phase 3B-UAT5 Details panel just shipped, same
weight as UAT1–UAT5.

### Owner clarification

The Phase 3B-UAT5 Details panel repeated fields the main Recordings
table already shows (Recorder, Duration, and implicitly Channels never
appeared there but Recorder/Duration did). Owner's rule: **main table =
quick identification/summary metadata; expanded Details = supplementary
technical metadata not already shown in the main table.**

### What changed

`renderRecordingDetails()` no longer renders Recorder or Duration — both
stay exactly where they already were, as their own columns in the main
Recordings table (untouched, not redesigned). The panel now shows only:
Nominal frequency, Timing reference, Samples, Sampling rate(s), Start
time, Trigger time — followed by a separate "Files" section listing CFG
and DAT filenames, matching the owner's own mockup layout.

### Layout — compact horizontal table, not vertical cards

Per the owner's explicit "avoid metadata cards... make the remaining
technical metadata compact and easy to scan" direction, the panel
switched from the vertical `.stat-grid`/`.stat` card layout (Phase
3B-UAT5's reuse of the old Waveform-sidebar pattern) to one real
`<table class="recording-details-table">` with a `<thead>` label row and
a single `<tbody>` data row — six columns read left-to-right in one
compact line, exactly as the owner's own ASCII table mockup showed. The
table sits inside a `.recording-details-table-wrap` (`overflow-x: auto`)
using the same containment technique already established for
`.recordings-table-wrap` — a narrow viewport scrolls the row
horizontally rather than breaking Work Area's own width or silently
truncating a value. The Files section is a simple compact label/value
list (`.recording-details-files`/`.recording-details-file`), not a
second table.

### Dead code removed

Since UAT5's Recordings Details panel was the last remaining caller of
the old Waveform-sidebar-era `.stat-grid`/`.stat`/`statCard()` machinery
(the Waveform sidebar itself stopped using it as of UAT5), and this pass
moved the Details panel off it too, `.stat-grid`/`.stat`/`.stat .label`/
`.stat .value` (CSS) and `statCard()` (JS) are now unused anywhere in
the app and were deleted rather than left as dead code. Comments
referencing the old machinery were updated in place rather than left
stale.

### Preserved

The main Recordings table itself was not redesigned — same columns
(Recording, Station, Recorder, Channels, Duration, Imported, Actions),
same data, same behavior. Open/Analyse, Remove, search, and the
Details-expand/collapse mechanism itself (multiple rows expandable at
once, `recordingsExpandedDetails` Set, zero extra fetch) are all
unchanged from UAT5 — this pass only changed what content renders
inside an already-expanded panel.

### Tests

- **Frontend, new**: `phase3buat6_check.mjs` (scratch, not committed) —
  9/9 passing. Covers: Recorder/Duration/Channels remain in the main
  table; none of the three are repeated in Details (value AND label
  both absent); the six supplementary fields render correctly; CFG/DAT
  stay correctly associated per recording with no cross-row leakage;
  the technical metadata renders as one real `<table>` with exactly one
  horizontal data row (using the native `table.tBodies[0].rows` API,
  not a "tbody tr" CSS selector -- jsdom's selector engine has a known
  quirk where that selector also matches a sibling `<thead>`'s row for
  HTML tables, discovered and worked around while writing this test).
- **Frontend, existing suite correction**: `phase3buat5_check.mjs`'s own
  field-list/CSS-selector/cross-leakage assertions (written for the
  now-superseded UAT5 layout) were updated in place for the new field
  list and markup, following this project's established precedent.
  `phase3auat3_check.mjs`'s `.stat`/`.stat .value` containment assertion
  was updated to check the new `.recording-details-table td`/
  `.recording-details-file-name` rules instead (the CSS classes it used
  to check no longer exist).
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.
- **Backend**: zero diff -- no new field was needed (Recorder/Duration/
  Channels were already in `SourceSummaryOut` since Phase 3B/3B-UAT5;
  this pass only changed which already-available fields the frontend
  chooses to render where).

### Files changed

`frontend/index.html` only.

### Honest limitation

No real browser is available in this sandbox — whether the compact
horizontal table reads naturally at typical widths, and whether it
scrolls acceptably rather than feeling cramped at narrow widths, was
reasoned through structurally but not visually confirmed — flagged for
owner UAT.

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
