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

## Phase 3B-UAT7 — Recording Details UX Redesign (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry (governance did not
require one for this UX-presentation refinement, per the task's own
instruction) — a design-review-then-implementation pass on the already-
decided DEC-032 Recordings architecture, following the same
analysis-first pattern the project already uses for `[DECISION MODE:
COMPARISON]` items, but resolved as an approved implementation task
rather than a formal decision record.

### Owner feedback that triggered this phase

Phase 3B-UAT6's horizontal `<table>`-grammar Details panel was
technically correct (right fields, no duplication, exact association)
but the owner rejected it on UX grounds: it read as "a second
spreadsheet" embedded under the main table, gave Start/Trigger Time no
more visual room than any other field, and had no visible connection to
its own parent row. A dedicated analysis turn preceded this
implementation (three alternatives compared: an inline facts strip, a
structured two-zone panel, and a side inspector pane) — the owner
approved **Option B, structured two-zone details**, plus an additional
rule: CFG/DAT filenames must be removed from the main Recordings table
entirely and shown only inside expanded Details.

### Main Recordings table

`td.recording-name-cell` now renders only the logical recording name
(`recordingDisplayName()`, unchanged) — the `.recording-files` sub-line
that used to print `original_filenames.join(" + ")` beneath it was
deleted, and its now-unused CSS rule removed. Station, Recorder,
Channels, Duration, Imported, Actions are all unchanged. The search
index (`searchText`) still includes `filenames` even though they're no
longer rendered — a filename search still finds the right row; only the
*visible* duplication was removed, not the searchability.

### Recording Details — structured two-zone panel

`renderRecordingDetails()` was rewritten from `<table><thead>…` markup
to three plain-HTML zones, none of them a table:

- **Zone 1 (facts)** — Nominal frequency, Timing reference, Samples,
  Sampling rate(s) as `label`/`value` pairs in a `flex-wrap` strip
  (`.recording-details-facts`/`.recording-details-fact`) — each pair is
  an atomic unit that wraps as a whole at narrow widths, unlike a rigid
  `<table>` column.
- **Zone 2 (timing)** — Start/Trigger get dedicated full-width lines
  (`.recording-details-timing`), each on its own row with a
  fixed-width "Start"/"Trigger" label so both timestamps align — this
  is the direct fix for "timestamps not receiving enough emphasis."
  Still formatted via the established `.replace("T", " ")` string
  technique (never `new Date()`), so full microsecond precision is
  unchanged.
- **Zone 3 (files)** — unchanged from UAT6's own Files styling
  (`.recording-details-files`/`.recording-details-file`), now separated
  from Zone 2 by a quiet `.recording-details-divider` rule instead of a
  second heading system.

The `.recording-details-table`/`.recording-details-table-wrap`/
`.recording-details-title` CSS (UAT6's table grammar) was deleted
outright — confirmed via grep to have no other caller before removal.

### Parent-row association

Two halves of one restrained visual cue, both using the existing
`--accent`/`--accent-wash-soft` theme tokens (no new hardcoded colors):
a 3px `border-left: var(--accent)` on the details panel's own `<td>`,
and a `tr.recording-row-expanded td { background: var(--accent-wash-soft); }`
tint applied to the *parent* row (not the details row) while its panel
is open, toggled by `toggleRecordingDetails()`'s own new
`findRecordingRow()` lookup. With multiple rows expanded at once, each
panel remains attributable to its own row by this same visual family
plus DOM adjacency.

### Details interaction refinement

The Details button keeps a **stable "Details" label** at all times (no
"Details"/"Hide details" swap) — `button.recording-details-toggle`
reuses the app's own pre-existing `.chevron` glyph (already used for
Analog/Digital channel groups' `<details>`/`<summary>` disclosure), with
a new `button.recording-details-toggle[aria-expanded="true"] .chevron`
rule providing the same 90°-rotation convention in this non-`<details>`
context. The button's border is transparent by default (visually
demoting it below the two real actions, Open/Analyse and Remove, which
keep their existing `.secondary`/`.danger` styling untouched) and
appears on hover. `toggleRecordingDetails()` no longer touches
`textContent` at all — only `aria-expanded` changes, which both the
chevron-rotation CSS and assistive technology key off directly. Open/
Analyse and Remove semantics, placement, and confirmation flow are
completely unchanged.

### Responsive/theme behavior

Zone 1's `flex-wrap` strip reflows to fewer columns at narrow widths
without any horizontal scrollbar (unlike UAT6's `<table>`, which had no
reflow option). Zone 2's timing lines are already full-width blocks, so
they were never at risk of squeezing. Zone 3 reuses UAT6's own
already-established filename containment
(`overflow-wrap: anywhere`/`min-width: 0`). All new colors are existing
Light/Dark theme tokens (`--accent`, `--accent-wash-soft`,
`--panel-border`) — no new hardcoded values.

### Tests

- **Frontend, new**: `phase3buat7_check.mjs` (scratch, not committed) —
  19/19 passing. Covers: main-table filename removal + summary-field
  preservation (7 checks), Details presentation (chevron/stable label/
  no table grammar/parent-row class/correct row attribution/multiple-
  open, 7 checks), metadata preservation (exact fields, no Recorder/
  Duration/Channels duplication, no cross-recording leakage, 3 checks),
  and Files (removed from main row, present + correctly associated +
  long-filename-safe in Details, zero network activity on toggle, 2
  checks).
- **Frontend, existing suite correction**: five pre-existing assertions
  across `phase3auat3_check.mjs`, `phase3b_check.mjs` (two),
  `phase3buat5_check.mjs` (five), and `phase3buat6_check.mjs` (two) had
  implicitly assumed either the UAT6 `<table>` grammar, the old
  "Details"/"Hide details" text-swap, the old "Start time"/"Trigger
  time" zone labels, or the old main-row filename sub-line — all
  updated in place with explanatory comments, following this project's
  established precedent, rather than left failing.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.
- **Backend**: zero diff, 280/280 passing in a fresh venv (no backend
  file touched — this is a pure frontend presentation change; no new
  field was needed since every rendered value already existed in
  `SourceSummaryOut`).

### Files changed

`frontend/index.html` only.

### Honest limitation

No real browser is available in this sandbox — whether the accent-bar/
row-tint association genuinely reads as intended, whether the chevron
rotation is visually smooth, and whether the overall panel now feels
"polished" rather than merely structurally different, were reasoned
through but not visually confirmed — flagged for owner UAT.

---

## Phase 3B-UAT7 (continued) — Final Table Restructuring and Row-Click-to-Open (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry. Two further owner
refinements, delivered in the same working session before the prior
Phase 3B-UAT7 record's structured-details redesign had its next UAT
round — both folded into one implementation pass and one commit.

### 1. Final main-table column set

The main Recordings table's columns were finalized to:

```
Recording | Start Time | Duration | Sampling Rate(s) | Actions
```

Station, Recorder, Channels, and Imported were removed as main-table
columns. Sampling Rate(s) was **promoted** into the main table (it had
lived in expanded Details since Phase 3B-UAT5/UAT6) as primary
recording-characteristic information; Start Time was promoted for the
first time (previously Details-only). Two new formatting helpers back
these: `formatRecordingStartTime()` (the established
`.replace("T", " ")` string technique — never `new Date()`, preserving
full microsecond precision and COMTRADE's timezone-naive semantics) and
`formatSamplingRates()` (renders EVERY real rate `SourceSummaryOut`
reports, verified with a genuine multi-rate fixture — never assumes or
collapses to exactly one rate). Both are purely additive frontend
functions; no backend change was needed since every value was already
present on `SourceSummaryOut`.

### 2. Details reorganized into Technical / Timing / Files

Reflecting the reversed non-duplication rule (Recorder/Channels moved
OUT of the main table and INTO Details; Sampling Rate(s)/Start Time
moved the opposite direction), `renderRecordingDetails()`'s zones became:

- **Technical** (facts strip): Recorder, Channels ("N Analog / M
  Digital" — a fuller phrase than the main table's old compact "NA +
  MD" summary, since it's no longer competing for column width),
  Nominal frequency, Timing reference, Samples.
- **Timing** (dedicated lines): Trigger, Imported — Start Time moved
  OUT (now main-table-only); Imported moved IN (previously a main-table
  column, `formatImportedAt()` reused unchanged, preserving its
  established distinction from timezone-naive per-sample COMTRADE
  timestamps).
- **Files** (unchanged): CFG, DAT.

A shared `.recording-details-zone-title` class (generalized from the
old Files-only title) gives each zone a quiet, uppercase, dim caption —
added specifically because the zone count/field count grew enough
(5 + 2 + 2) that implicit grouping via spacing alone was judged
insufficient for scanability.

### 3. Row-click-to-open

The explicit "Open / Analyse" button was removed. The recording `<tr>`
itself is now the primary Open/Analyse target — clicking (or pressing
Enter/Space while focused) an ordinary part of the row calls the SAME
`openRecordingForAnalysis()` the old button called; no second
implementation.

**Accessible semantics** (the task's own flagged concern — "a `<tr>`
cannot automatically inherit all correct native `<button>` semantics"):
the row gets `tabindex="0"`, `role="button"`, and an `aria-label`
naming the action (e.g. `"Open Tanjung Bin BEN6K for analysis"`). This
is one of the task's own suggested approaches, chosen over a heavier
full ARIA grid/roving-tabindex pattern (disproportionate for a small
recordings table) and over inventing genuinely invalid markup. The two
real nested `<button>` elements (Details, Remove) remain independently
focusable/operable; their own `click` handlers call
`event.stopPropagation()` so a button click never also reaches the
row's listener, and the row's own `keydown` handler additionally
guards with `event.target !== row` — a `keydown` on a focused child
button bubbles up independently of the button's native Enter/Space-to-
click conversion, so this guard is what actually stops it from
double-firing the row's own action (confirmed by a dedicated test that
dispatches a bubbling `keydown` directly on the Details button).

**Actions column** is now icon-only: Details (the existing `.chevron`
disclosure glyph, reused verbatim from Analog/Digital channel groups,
rotating via the pre-existing `[aria-expanded="true"]` CSS rule) and
Remove (`&times;`, the SAME glyph this codebase already uses for every
other close/remove control — modal close buttons, channel remove tags,
group delete). Neither button has visible text anymore; both carry
`aria-label`/`title` (Details' swaps between "Show details"/"Hide
details" in `toggleRecordingDetails()`, since there's no longer a
visible label to keep stable; Remove's is the fixed "Remove recording").

**Row interaction states**: `cursor: pointer` and the pre-existing
`table.recordings tr:hover td { background: var(--hover-tint); }` rule
(reused, not duplicated) signal "this row opens something"; a new
`:focus-visible` outline (`var(--accent)`) gives keyboard users a
visible indicator without flashing on an ordinary mouse click; the
pre-existing `tr.recording-row-expanded` tint (from the earlier UAT7
pass) remains a visually distinct, separate state in the same accent
family. All three states use only existing Light/Dark theme tokens.

### Tests

- **Frontend**: `phase3buat7_check.mjs` (scratch, not committed) was
  substantially rewritten for the final state — 22/22 passing. Covers:
  final main-table column presence/absence (Recording/Start Time/
  Duration/Sampling Rate(s) present; Station/Recorder/Channels/Imported/
  Nominal Frequency/Timing Reference/Samples/CFG/DAT absent), a genuine
  multi-rate source rendered truthfully (not simplified to one rate),
  Details' final field set (present/absent per the reversed rule),
  multi-recording no-leakage, the explicit Open/Analyse button's
  removal, row click selecting the correct source among multiple
  recordings and navigating to Waveform with zero re-upload/duplicate-
  source/workspace-reset, Details/Remove/expanded-Details-content clicks
  never triggering row navigation, keyboard Enter and Space opening the
  focused row, the row's accessible semantics, the keydown-bubbling
  isolation guard specifically, Details/Remove remaining independently
  keyboard-operable real `<button>` elements, and the presence of the
  intended hover/focus/expanded CSS rules.
- **Frontend, existing suite correction**: assertions across
  `phase3b_check.mjs`, `phase3buat1_check.mjs` (two), `phase3buat3_check.mjs`,
  `phase3buat4_check.mjs`, `phase3buat5_check.mjs` (three), and
  `phase3buat6_check.mjs` (five) had assumed either the pre-restructuring
  main-table/Details field split, the three-button Actions column, or
  the explicit Open/Analyse button — all updated in place with
  explanatory comments, following this project's established precedent.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.
- **Backend**: zero diff, 280/280 passing in a fresh venv (no backend
  file touched — every rendered value already existed on
  `SourceSummaryOut`).

### Files changed

`frontend/index.html` only.

### Honest limitation

No real browser is available in this sandbox — whether row-click-to-
open feels natural (vs. accidentally clicking a row while scanning
text), whether the icon-only Actions column reads clearly without
tooltips visible at a glance, and whether the final Technical/Timing/
Files zone grouping scans well with the fuller field set, were reasoned
through but not visually confirmed — flagged for owner UAT.

---

## Phase 3B-UAT8 — Waveform Sidebar Cleanup + Main Navigation Refinement (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry (a UI/presentation
refinement within the already-decided DEC-031/DEC-032 shell/Recordings
architecture).

### Owner product-responsibility rule

Recordings = recording management (upload, metadata, Remove, choose/
open for analysis). Waveform = active recording context + channel
analysis only. The Waveform sidebar's old "Sources in this Workspace"
section (a clickable, multi-source list with its own per-row Remove
button) duplicated exactly that Recordings-owned management surface.

### Waveform sidebar: Active Recording replaces the source list

`renderSourceListItems()` (which rendered EVERY source in the workspace
as a switchable, removable list item) was replaced by
`renderActiveRecording(sources)` — read-only, renders ONLY whichever
source `selectedSourceId` currently names (the same selection
`selectSource()` already manages, completely unchanged), reusing
`recordingDisplayName()` for identity-naming consistency with
Recordings. No list, no click-to-switch, no Remove button. The old
`.panel` bordered-card treatment was replaced with a lighter, restrained
block (`.active-recording`, a plain bottom-border divider, no card) — a
direct application of section 19's own "is the heavy card still
necessary?" review, now that there's nothing left to manage here.

**Deliberate behavior change, called out explicitly**: switching which
source's channels are being browsed can no longer happen from inside
Waveform — the user goes back to Recordings and opens a different row.
This is the intended consequence of the owner's own product-
responsibility rule, not an accidental regression; multi-source
**display** (multiple different sources' channels shown together in
`ww.displayed`/`ww.panels`) is completely untouched — only the
single-source **browsing/selection** UI moved.

**"Active Recording" terminology** (section 10's own conflict check):
`selectedSourceId` already represents exactly one source at a time for
channel browsing, even though the workspace may hold several — "Active
Recording" is therefore an accurate, truthful label for current
behavior, not an invented concept; no terminology conflict found.

**`startNewWorkspace()` fix**: its "does the workspace have ANY sources
at all" check used to read `#sourceList.children.length` (the now-
removed list's own DOM child count) — replaced with a small module-
level `latestSourcesCount` cache, kept current inside
`refreshAllSourceViews()`/`refreshSourceList()` (the only two places
that actually refetch the source set), so the workspace-reset
confirmation lifecycle is unaffected by removing the list.

### Channels section: no more repeated identity

`renderChannels()`'s `.detail-header` block (station name + CFG/DAT
filenames, deliberately KEPT since Phase 3B-UAT5 as "active source
identification... still needed for analysis") was removed outright —
that identification now lives in Active Recording, directly above
Channels, so repeating it inside Channels was exactly the redundancy
the owner flagged. The Channels section now begins directly with
channel interaction (search, Add selected/Clear selection, the channel
tree) — unchanged in every other respect. The now-fully-unused
`.detail-header`/`.detail-header-info`/`.source-list`/`.source-name`/
`.source-sub` CSS (all fully dead once their only markup was removed)
was deleted rather than left as dead code.

### Main Sidebar: reordered, and a real bug fixed

Reordered to Recordings first, Waveform second (matching the actual
product flow: fresh entry → Recordings → choose/open → Waveform), then
unchanged Table/Tools/Reports.

**Bug found and fixed while reviewing active/inactive states (section
13's own ask)**: `.shell-nav-item[aria-current="page"]` (the CSS rule
providing the accent tint/background for the active nav item) had
NEVER actually matched anything — `shellSetCurrentPage()` was writing
the STRING `"true"`/`"false"` to `aria-current`, a value the CSS
selector (which always expected the literal token `"page"`) could never
match. The active-state visual has therefore been silently broken since
Phase 3B first introduced page-level navigation. Fixed via a new shared
`setShellNavCurrent(id, isCurrent)` helper: writes `aria-current="page"`
when active, REMOVES the attribute entirely when not (the ARIA APG
convention for both — never `aria-current="false"`). A narrow 3px left
accent bar (`border-left`, reserved as transparent on every item so
gaining/losing it never shifts layout) was added alongside the now-
actually-working background/text-color tint, giving the "combination of
cues, not text color alone" the task asked for.

**Icons reviewed**: Recordings gained a new "list of records" icon
(three rows, each with a small leading marker dot) — deliberately
distinct from the Main Sidebar's own hamburger toggle icon (also
3 plain lines), which the OLD Recordings icon was visually confusable
with. Waveform gained a genuine zigzag/oscillation polyline icon,
replacing a dashboard-panel-shaped rectangle icon that didn't read as
"waveform" at all. Table/Tools/Reports/Settings icons were left
unchanged — already correct or already within the task's own explicit
"as appropriate" allowance (Tools' magnifying-glass icon reads as
"search," one of the task's own listed acceptable options).

**Collapsed state**: unaffected structurally — the same DOM order is
what the icon-only rail reflects, so reordering alone fixes collapsed
order too. `title` attributes were added to the two enabled items
(Recordings/Waveform/Settings) for a hover tooltip, matching the
disabled items' pre-existing `title="… -- coming soon"` convention;
`.shell-nav-label` text stays in the DOM (only `opacity: 0` while
collapsed, never `display:none`/`aria-hidden`), so accessible names
were already available in collapsed state before this pass too.

### Tests

- **Frontend, new**: `phase3buat8_check.mjs` (scratch, not committed) —
  24/24 passing. Covers Main Sidebar order/active-state/aria-current/
  disabled-state/collapsed-order/icons (11 checks), Waveform sidebar
  cleanup — no "Sources in this Workspace", Active Recording present
  with correct name/counts exactly once, no Remove button, no CFG/DAT
  or repeated heading inside Channels, Search/Add-selected/Clear-
  selection/channel-groups preserved, the empty state, and removing the
  active source leaving no stale identity (9 checks), and no-regression
  checks — row-click-to-open still selects the right source among
  multiple recordings, Active Recording reflects it, channel browsing
  uses the right source, navigation state (layout mode/time mode)
  survives, and zero extra fetch for Active Recording (4 checks).
- **Frontend, existing suite correction**: `phase3auat4_check.mjs` was
  substantially rewritten (its entire original premise — long CFG/DAT
  filename containment inside the Waveform Channels panel — no longer
  applies now that filenames don't render there at all; retargeted to
  the equivalent concern that DOES still apply, long recording-NAME
  containment inside Active Recording). `phase3auat3_check.mjs`,
  `phase3b_check.mjs`, `phase3buat4_check.mjs`, and
  `phase3buat5_check.mjs` each had one or two assertions corrected in
  place (the removed `.detail-header`, and the `aria-current`
  string-vs-token fix) — all with explanatory comments, following this
  project's established precedent.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences.
- **Backend**: zero diff, 280/280 passing in a fresh venv (this is a
  pure frontend presentation/navigation change).

### Files changed

`frontend/index.html` only.

### Honest limitation

No real browser is available in this sandbox — whether the accent bar
+ tint combination reads clearly at a glance, whether the new
Recordings/Waveform icons are visually distinguishable enough from each
other and from Table's icon, and whether the lighter (non-card) Active
Recording section still feels sufficiently "present" rather than
easy to miss, were reasoned through but not visually confirmed —
flagged for owner UAT.

---

## CI/CD — Automatic DEV Deployment After CI (2026-08-19)

`[DECISION]` See
[DECISIONS.md — DEC-036](DECISIONS.md#dec-036--dev-deployment-is-automatic-after-ci-succeeds-on-main-prod-remains-fully-manual),
narrowing [DEC-003](DECISIONS.md#dec-003--deployment-is-manual-dev-and-prod-stay-isolated-prod-gets-the-commit-dev-tested).
Infrastructure/CI work, not a waveform-workspace feature phase — recorded
here outside the Phase 4A sequence since it's cross-cutting.

### Owner direction

Investigate (separately, see the investigation this decision followed)
why pushing to `main` no longer auto-deployed DEV, then, on reviewing
that history, approved restoring it -- narrowly: DEV auto-deploys after
CI succeeds on `main`; PROD stays fully manual, forever, by construction
(not merely by convention); the existing manual `deploy.yml` remains
available unchanged as a DEV/PROD fallback.

### What changed

New `.github/workflows/deploy-dev.yml` only -- `deploy.yml` is untouched
(verified: zero diff). Trigger: `workflow_run` on the "CI" workflow's
completion, filtered to `branches: [main]`; the job itself gates on
`if: github.event.workflow_run.conclusion == 'success'`, so a failed or
cancelled CI run never deploys. The exact SHA deployed is
`github.event.workflow_run.head_sha` (the commit CI actually validated),
threaded through as `APP_VERSION` into the same `scripts/deploy.sh` path
the manual workflow already uses -- preserving the existing build-
provenance chain (Phase 4A-UAT3: frontend `buildVersion()` == backend
`/health.git_sha` == deployed commit) with no new mechanism.

DEV-only by construction: no `inputs:` block exists at all (GitHub
doesn't populate `inputs.*` outside `workflow_dispatch`), so every value
that the manual workflow selects via `${{ inputs.target }}` is instead
the literal string `"dev"` in three places -- `environment: dev`,
`TARGET=dev` in the deploy command, and `concurrency.group:
powerwave-deploy-dev` (deliberately the same group name
`deploy.yml`'s own `powerwave-deploy-${{ inputs.target }}` resolves to
when a human dispatches `target: dev`, so a manual and an automatic DEV
deploy can never race against the same VPS path). There is no
expression, variable, or branch anywhere in the new file capable of
evaluating to `prod`.

### Why `workflow_run`, not a bare `push` trigger

A `push` trigger added directly to a new file would start deployment in
*parallel* with CI, not *after* it -- the exact race the owner's own
task text explicitly forbade. `workflow_run` structurally cannot fire
until GitHub has recorded CI as fully completed for that run. A bare
`push` added to the EXISTING `deploy.yml` was considered and rejected
for a sharper reason: that file's steps all read `${{ inputs.target }}`,
populated only for `workflow_dispatch` -- a push-triggered run would hit
an empty/undefined target, an unpredictable risk not worth taking on a
workflow also capable of deploying PROD.

### Validation

`python3 -m yamllint` (default ruleset, truthy/line-length/document-start
disabled to match the existing two workflow files' own style) passes
clean on all three workflow files. `python3 -c "import yaml; ..."`
confirms the new file parses as valid YAML with the expected structure
(the `on:` key resolving to PyYAML's boolean `True` under `safe_load` is
a pre-existing, harmless YAML-1.1-vs-1.2 parser quirk -- `deploy.yml`
exhibits the identical artifact; GitHub's own Actions parser treats `on:`
as the literal string key). No `gh`/GitHub Actions API access is
available in this sandbox, so the actual live run sequence (CI -> DEV
deploy -> SHA match) could not be directly observed here; see the final
report's own "Verification" section for what was and wasn't confirmed
this way.

### Governance docs updated

`DECISIONS.md` (new DEC-036; DEC-003 annotated in place with a pointer,
not rewritten -- everything DEC-003 says about PROD/isolation/commit
traceability remains in force verbatim), `CURRENT_STATE.md`,
`MIGRATION_PLAN.md` (this record), `HANDOFF.md`,
`docs/development/development-workflow.md` (workflow diagram and DEV
deployment section updated to describe automatic-after-CI). `AGENTS.md`'s
existing "Deployment is manual. Do not deploy to production unless
explicitly asked." already names only PROD explicitly -- left as-is,
already compatible with this decision.

### Files changed

`.github/workflows/deploy-dev.yml` (new). No other application code
touched.

### Honest limitations

GitHub Environment protection rules (required reviewers, branch
restrictions) on the `prod` environment are a repository-UI setting this
agent cannot inspect from a local clone -- this decision's own safety
guarantee doesn't depend on that setting (the new file is structurally
incapable of a `prod` deploy regardless), but the owner should
independently confirm `prod` still has appropriate protection as defense
in depth. No real GitHub Actions run of the new workflow could be
observed from this sandbox (no `gh`/API credentials) -- flagged for
owner UAT after this push.

---

## Phase 5A-UAT3 — Calculated Channel Input Availability (2026-08-21)

### Scope

Owner-approved clarification: Calculated Channels must be able to use
ALL available analog channels from the active workspace/source
inventory, regardless of whether those channels are currently visible
on the main Waveform page. Waveform visibility is presentation state
only and must never control whether a recorded analog channel (or an
existing calculated channel) is eligible as a calculation input. This
applies to original/source analog channels and to calculated channels
used as inputs to later calculations alike.

### Investigation / root cause

Traced `wwCcAvailableCandidates()` (the Signal Builder's own candidate-
list authority) directly: it read from `ww.channelMeta`, a Map
deliberately scoped, per its own pre-existing Phase 5A comment, to
"every analog channel the engineer has brought into this workspace's
Waveform **at least once**" -- populated SOLELY by
`wwAddSelectedChannels()`, i.e. only the moment a channel is first
DISPLAYED. A source channel never individually toggled visible was
therefore simply absent from the picker, even though its own SOURCE had
already been opened and its full channel list was already known to the
backend -- confirming the bug is exactly what was expected:
calculated-input availability was coupled to Waveform display history,
not to the authoritative source/workspace inventory. Not a backend gap:
the backend's `ChannelRef` validation already accepts any valid source/
calculated channel id regardless of visibility (visibility is not
backend state at all) -- confirmed by inspection before any change was
made; no backend files were touched, per this task's own "only touch
backend if an authoritative inventory API is missing" instruction (the
existing `GET .../sources/{id}/channels` endpoint already provides
everything needed).

### Required separation of concerns (now established)

SOURCE/WORKSPACE ANALOG INVENTORY -> determines whether a channel
exists and can be considered for calculation. WAVEFORM VISIBILITY ->
determines only whether that channel is currently plotted. These are
now genuinely independent: a new `ww.sourceChannelInventory` (`sourceId
-> {sourceId, sourceName, analogChannels}`) is the sole authority for
the first; `ww.displayed` remains the sole authority for the second, as
before, and is never consulted by the calculated-channel builder at
all.

### Input inventory authority

`ww.sourceChannelInventory` is populated directly from the SAME `GET
.../sources/{id}/channels` response `selectSource()` already fetches
for the Channel Browser -- zero new network calls in the common case --
covering EVERY analog channel of a source the engineer has opened this
session, independent of which individual channels were ever toggled
visible, hidden via "Hide all," or hidden individually.
`wwCcAvailableCandidates()` now reads from this inventory instead of
`ww.channelMeta`. `ww.channelMeta` itself is left completely untouched
-- still used, unmodified, by the unrelated Custom Groups chip editor
(`groupsHtml` rendering), which has its own, deliberately different,
"survives hide, describes a possibly-hidden group member" purpose.

### Visibility separation (confirmed by test)

A hidden (never-displayed) source channel is now a fully eligible
calculation input, and selecting it as an input never auto-displays it,
never adds it to `ww.displayed`, never changes Grouped/Separate/Custom,
viewport, or its sidebar eye state -- calculation input selection and
waveform display remain genuinely separate concerns, verified directly:
creating `-VA` from a VA that was never shown leaves `ww.displayed`
untouched and VA still hidden afterward.

### Calculated-as-input

An existing calculated channel that is itself hidden (its own default
state per DEC-038, or explicitly hidden afterward) remains fully
available as an input to a further calculation -- `Scaled Sum = Sum x
0.5` succeeds correctly even while `Sum` itself stays hidden, verified
directly against the mock backend's own authoritative stored array.

### Compatibility filtering (unchanged)

All existing Phase 5A engineering guardrails remain mandatory and
untouched: multi-input operands still require the same authoritative
synchronized sample-time axis (no interpolation/resampling/time-shift/
crop-to-overlap/equal-sample-count-or-rate shortcut) and compatible
units, enforced server-side exactly as before. The client-side
"same-source" candidate-disable heuristic
(`wwCcCandidateOptionsHtml()`) needed no change -- it already compares
`referenceSourceId` against the first-chosen input, unaffected by where
the candidate list itself comes from; a hidden, cross-source,
time-incompatible channel is still correctly shown-but-disabled after a
first input is chosen, and an attempt to force-combine it anyway is
still rejected by the backend, belt-and-braces, verified directly.

### Unary / N-input operations (verified by test)

Reverse Polarity, Absolute Value, and Multiply by Constant all succeed
from a channel that has never been displayed, producing the correct
full-resolution result. N-input Addition succeeds with only one of
three inputs visible; N-input ordered Subtraction succeeds with ALL
inputs hidden -- in every case the hidden channels remain hidden
afterward, and results match hand-computed expectations against the
authoritative full-resolution arrays.

### Source lifecycle

Removing a source drops exactly that source's own channels from the
candidate inventory (`ww.sourceChannelInventory.delete(sourceId)` inside
`performRemoveSource()`) -- no stale options; other sources' own
candidates are unaffected. "Start New Workspace" clears the inventory
entirely (mirrors `ww.sourceBounds`'s own scoping: "every old source was
just released server-side"). The plain "Clear workspace" button
deliberately does NOT clear it (unlike `ww.channelMeta`/
`ww.channelColors`, which it already clears unconditionally) -- Clear is
display-only and keeps the still-selected source fully loaded, so
wiping its known channel list there would have silently reintroduced
the exact visibility-coupling bug this fix removes.

### UX: per-source grouping

The picker's single flat "Source Analog Channels" optgroup was split
into one optgroup per source (labelled by that source's own station
name), matching the owner's own preferred "Source 1 / Source 2 /
Calculated Channels" structure -- the smallest change that keeps a now
potentially much larger candidate list navigable, without a
disproportionate nested-by-engineering-type rewrite (a native
`<select>` has no second grouping level to exploit for that, and the
task's own guidance was explicit not to over-invest here).

### Regressions confirmed unaffected

The Calculated Channels waveform preview (Phase 5A-UAT) still follows
its own, separate visibility authority (`ww.displayed`) unchanged --
verified directly that a channel newly eligible as a candidate does NOT
leak into the preview merely by being creatable; it still only appears
once explicitly toggled visible, exactly as before. The Cur A/Cur B
sidebar presentation (Phase 5A-UAT2) is unaffected, verified directly.

### Tests

Extended `phase5a_check.mjs` with 11 new checks (hidden-channel unary
x3, hidden-input N-addition, all-hidden N-subtraction, hidden
calculated-channel-as-input, incompatible hidden cross-source channel
still correctly disabled, hide-all/show-all leaving the candidate
inventory unchanged, source removal dropping exactly that source's
candidates, waveform-preview regression, A/B-sidebar regression, and
per-source optgroup grouping) -- **65/65 passing** in the file overall
(53 prior unchanged, zero pre-existing test's own expected behavior
changed). Full frontend suite reconfirmed at the true 33-failure
baseline across the same 15 pre-existing files (zero net new
regressions -- `phase2cc*`'s own pre-existing failures individually
re-inspected and confirmed unrelated: still failing for the SAME
pre-existing Absolute/Elapsed time-mode reasons as before, not
`ww.channelMeta`/Custom Groups, which this change never touched;
`phase4c1_check.mjs`/`phase4c2_check.mjs`/`phase4f_check.mjs`/
`phase4g_check.mjs` individually reconfirmed passing). Backend
untouched, 519/519 passing (`git status --short backend/` empty
throughout).

### Decision

No new decision. See the "Update" note appended to
[DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations)
(an explicit clarification of existing intent, not a new architectural
decision).

### Files changed

`frontend/index.html` only -- new `ww.sourceChannelInventory` field,
populated in `selectSource()`, cleaned up in `performRemoveSource()`
and `wwClearWorkspace()`'s Start-New-Workspace branch;
`wwCcAvailableCandidates()` rewritten to read from it with per-source
optgroup grouping. No backend files touched.

---

## Phase 5A-UAT2 — Standard A/B Measurements for Calculated Channels (2026-08-21)

### Scope

Owner UAT: on the main Waveform page, the Calculated Channels sidebar
group showed no Cur A / Cur B measurement columns at all, unlike real
Analog Channel rows -- calculated channels are analog-like engineering
channels and should use the identical standard measurement design.
Frontend presentation/integration only; no calculation mathematics,
time-alignment guardrails, dependency model, adaptive resolution, Peak,
or Callout code touched.

### Investigation / root cause

Not a missing backend binding. The Phase 5A
`/calculated-channels/cursor-values` endpoint and its frontend dispatch
(`wwFetchCursorValuesForSource()`'s own `isCalculated` branch,
`wwFetchAllCursorValues()`/`wwScheduleCursorValuesRefresh()`'s
source-id-driven fan-out over `ww.displayed`) were already fully wired
and already correctly populating `ww.cursorValues` for calculated
channels -- proven directly by the pre-existing A/B cursor test
(`[99]`), unchanged and still passing. The gap was purely a row-
template/separate-rendering-function difference:
`wwRenderCalculatedChannelsSidebarSection()` hand-built its own bespoke
`<tr>` markup -- a single name `<td>`, wrapped in `class="channel-table"`,
a class with NO CSS rule anywhere in the stylesheet (completely
unstyled) -- instead of reusing `renderChannelTable()`, the SAME generic
table builder `renderAnalogGroup()` already uses to produce the real
Channel Browser's own Channel/Phase/Cur A/Cur B columns.
`wwCurValueCellHtml()`/`wwCurValueText()` themselves were already fully
generic (keyed by `sourceId`/`channelName` via `wwChannelKey()`, gated
by the SAME `wwIsAnalogChannelVisible()`/`ww.measurementCursors`
authority every analog cell already uses) -- they had simply never been
called with a calculated channel's own id/name.

### UI standardization

`wwRenderCalculatedChannelsSidebarSection()` now calls
`renderChannelTable()` with `[Channel, Cur A, Cur B]` columns (no
"Phase" column -- calculated channels carry no phase field in DEC-047's
own schema, an honest omission, not a layout shortcut), reusing
`analogChannelNameCellHtml()` and `wwCurValueCellHtml()` verbatim. The
rendered table now carries `class="channels"` -- the real, theme-token-
driven analog sidebar style (`var(--text)`/`var(--panel-border)`/
`var(--text-dim)`, `font-size: 0.7rem` -- already exactly the recently-
approved work-area sidebar typography, inherited automatically, no new
rule written) -- not a second, invented visual pattern.

### Shared row design (section 15)

A new `calculatedChannelRowAttrs(calc)` mirrors `analogChannelRowAttrs()`'s
shape (class/tabindex/role/aria-pressed/aria-label/title) and
additionally tags each row with `data-channel-kind="analog"`/
`data-source-id`/`data-channel-name` -- the SAME triad real analog rows
already carry. This makes calculated-channel rows citizens of the
EXISTING generic Cur A/Cur B live-update sweeps
(`wwUpdateCursorValueCellsForChannels()`/`wwUpdateAllCursorValueCells()`,
both global `document.querySelectorAll` queries, not scoped to the
Channel Browser) that already drive cursor-drag/cursor-move/mode-toggle
updates for real channels -- **no new update plumbing was written for
calculated channels at all**. Verified safe: the only other consumer of
`data-channel-kind` (`setupChannelRowToggles()`'s click dispatch) is
delegated on `#channelGroups` specifically, a different DOM subtree
from `#calculatedChannelsSidebarBody`, so it never sees these rows; the
sidebar's own pre-existing dedicated click handler
(`wwCalculatedChannelsSidebarRowClickHandler`, keyed off
`data-calculated-channel-id`) is unchanged and still owns the toggle
interaction.

### Related small fix

`wwRenderCalculatedChannelsSidebarSection()`'s zero-channels early
return used to skip clearing `bodyEl.innerHTML`, leaving the last
channel's stale `<tr>` in the DOM (invisible only because the ancestor
`<section>` itself was hidden) -- discovered by this task's own
"delete -> measurement row disappears cleanly" acceptance check.
Inconsistent with `wwRenderCalculatedChannelManagerList()`'s own sibling
convention two functions away (already replaces its body with the
empty-state paragraph at zero); now matches it.

### Measurement authority / cursor authority / formatting

Unchanged from Phase 5A: full-resolution authoritative calculated
arrays via the SAME nearest-sample rule; ONE shared workspace-global
`ww.measurementCursors` state (no separate calculated-channel cursor
position); `wwFormatEngineeringValue()` (unchanged) for precision;
out-of-range renders as em dash (`—`), never fabricated/extrapolated --
identical to real analog channels, verified directly by test.

### Calculated-from-calculated

Verified directly: a channel derived from another calculated channel
(`Scaled = Sum x 0.5`, `Sum = VA + VB`) shows correct Cur A and Cur B,
computed from ITS OWN authoritative stored array (already Phase 5A's
own eager-evaluation guarantee -- no new evaluation code needed).

### Tests

Extended `phase5a_check.mjs` with 10 new checks: A/B-off em dash parity
with analog, A/B-on values matching the authoritative array via the
nearest-sample rule, moving A/moving B independently (each leaves the
other cursor's own cell untouched), calculated-from-calculated,
out-of-range em dash, delete removing the row entirely (not just
blanking it), Grouped/Separate/Custom producing exactly one row per
channel with no duplicate/stale rows, and a structural guard confirming
`table.channels`/exactly 3 columns -- **53/53 passing** in the file
overall (44 prior unchanged). Full frontend suite reconfirmed at the
true 33-failure baseline across the same 15 pre-existing files (zero
net new regressions, including `phase4c1_check.mjs`/
`phase4c2_check.mjs`'s own A/B cursor coverage, `phase4f_check.mjs`'s
Callout coverage, and `phase4g_check.mjs`'s Peak coverage, all
individually reconfirmed passing). Backend untouched, 519/519 passing
(no backend files changed -- `git status --short backend/` empty
throughout).

### Decision

No new decision. See the "Update" note appended to
[DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations)
(a frontend consistency fix, not a new architectural decision).

### Files changed

`frontend/index.html` only -- `wwRenderCalculatedChannelsSidebarSection()`
rewritten to reuse `renderChannelTable()`, new
`calculatedChannelRowAttrs()` helper, one small related bug fix (empty-
state body clearing). No backend files touched.

---

## Phase 5A-UAT — Calculated Channel Waveform Preview (2026-08-21)

### Scope

Owner-requested addition: a lightweight **Waveform Preview** panel on
the Calculated Channels page, sitting below the existing Calculated
Channels manager list -- explicitly NOT the full Waveform workspace,
only a simple preview chart using native Plotly interaction tools. No
new decision entry -- a straightforward extension, documented as an
"Update" note on DEC-047 (see below).

### Design approach

Every authority the preview depends on is one DEC-047 already
established -- nothing new was introduced:

- **Visibility**: `wwIsAnalogChannelVisible(sourceId, channelName)`
  reading `ww.displayed` -- the SAME single authority the manager
  list's own eye icon and the Waveform sidebar group already share. No
  second, conflicting visibility state.
- **Data**: the existing `GET .../calculated-channels/{id}/waveform`
  endpoint (already built by Phase 5A) -- no new backend work at all.
  Plotted values/times come directly from that authoritative response,
  never re-derived from Plotly's own trace objects.
- **Color**: the existing `wwColorForChannel()` -- visually consistent
  with the main Waveform page's own channel colors.
- **Theme**: the existing `wwThemeColors()`.

A completely standalone Plotly instance (`#wwCcPreviewChart`) -- never
added to `ww.panels`, never touching `ww.viewport`/layout mode/A-B
cursor state/annotations. Native Plotly modebar/pan/zoom only
(`displayModeBar: true`, explicit rather than a bare omission -- the
opposite of the main panels' own `displayModeBar: false` convention,
since Powerwave's centralized toolbar deliberately does not extend to
this preview). No custom Powerwave toolbar of any kind.

### Rendering strategy

Full rebuild on every change: refetch data for every currently-visible
calculated channel, then `Plotly.newPlot()` on first render /
`Plotly.react()` on every subsequent one -- rather than incremental
trace add/remove diffing. Simpler and adequately efficient for a
small-channel-count Phase 1 preview, matching the task's own "do not
overengineer caching unless necessary" instruction. Guarded by a
monotonic generation counter (the same stale-response idiom already
used by `wwCursorValuesGeneration`/`wwPeakValuesGeneration`/
`ww.annotationPlacementGeneration`) so a rapid sequence of visibility
toggles can never let an earlier fetch overwrite a later one.

### Lifecycle wiring

Called from the exact same 3 sites that already refresh the manager
list -- `wwRenderCalculatedChannelsPage()` (page-open/post-creation/
Start New Workspace), `wwToggleCalculatedChannelDisplay()` (visibility
toggle), and `wwCcDeleteChannel()`'s success branch (delete) -- so the
preview's own lifecycle (create/delete/toggle/Start New Workspace/Clear
Workspace) exactly mirrors the manager list's own established behavior.
No new rule invented for Clear Workspace: the plain "Clear workspace"
button clears `ww.displayed` (same as every other channel) but
preserves calculated-channel definitions, same established policy;
"Start New Workspace" clears both, same as the manager list.

### Page isolation

Proactively avoided a FOURTH occurrence of the `[hidden]`-CSS-cascade
bug this session had already hit three times (the annotation guidance
ribbon, `#pageCalculatedChannels` page-stacking): the new
`.ww-cc-preview-chart` CSS class deliberately declares NO `display`
property at all -- matching `.empty-state`/`.ww-cc-panel`'s own existing
safe pattern already used elsewhere on this same page -- so there is
nothing in author CSS to override the UA stylesheet's own
`[hidden] { display: none }` rule. If a future change ever needs to
give this element an explicit `display` value, a matching
`#wwCcPreviewChart[hidden] { display: none; }` override must be added
in the same change.

### Tests

Extended `phase5a_check.mjs` with 14 new checks: panel placement below
the manager list section with the correct default empty-state message;
a newly created channel stays out of the preview until made visible
(matches DEC-038's own default-hidden policy); visibility toggle both
directions (shows/hides, purges the chart when it goes back to empty);
delete removes a visible channel from the preview; multiple visible
channels plotted together with distinct colors sourced from
`wwColorForChannel()`; plotted `x`/`y` arrays match the authoritative
calculated-channel array exactly (never re-derived from traces); native
`displayModeBar: true` Plotly config; non-interference with the main
Waveform page's own panel count/viewport (confirming the ONE expected,
pre-existing side effect -- toggling visibility legitimately adds the
channel to the shared `ww.panels` via the SAME reused authority -- while
the pre-existing real channel's own panel stays undisturbed, never
duplicated); a structural regression guard confirming
`.ww-cc-preview-chart` still carries no `display` property and
`#pageCalculatedChannels[hidden]` is still present; and Start New
Workspace / plain Clear Workspace lifecycle behavior -- **44/44
passing** in the file overall (32 prior unchanged). Full frontend suite
reconfirmed at the true 33-failure baseline across the same 15
pre-existing files (zero net new regressions). Backend untouched,
519/519 passing (no backend files changed).

### Decision

No new decision. See the "Update" note appended to
[DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations)
(a straightforward extension of that decision's own implementation, not
a new architectural decision).

### Files changed

`frontend/index.html` only -- new HTML section + CSS rule inside
`#pageCalculatedChannels`, plus `wwCcPreview` state and its three
helper functions (`wwCcPreviewVisibleChannels()`,
`wwCcFetchPreviewWaveform()`, `wwCcRenderWaveformPreview()`), plus one
trailing call added to each of the 3 existing lifecycle functions named
above. No backend files touched.

---

## Phase 5A UAT Fix — Page Navigation Isolation (2026-08-21)

### Scope

Owner UAT on the page below found the Recording Events page (and,
separately, Waveform) showing the Calculated Channels page STACKED
underneath it at the same time. No new decision entry -- an "Update"
note was appended to DEC-047 instead (see below).

### Root cause

The SAME CSS-cascade bug class already caught and fixed once this
session for the annotation placement guidance ribbon:
`#pageCalculatedChannels { display: flex; }` (author CSS) beats the UA
stylesheet's own `[hidden] { display: none }` rule by ORIGIN alone.
`shellSetCurrentPage()` -- confirmed by direct trace to be the SOLE
navigation authority, correctly toggling `.hidden` on all three page
containers and all three nav buttons' `aria-current` in one exclusive
pass -- was never wrong; `#pageCalculatedChannels.hidden` was already
`true` whenever a different page was active, but that had zero visible
effect. `#pageRecordings` itself already carried its own `[hidden]`
override from when it was first added (Phase 3B); the new Calculated
Channels page simply never received the same treatment.

### Ruled out

DOM nesting was independently inspected and confirmed correct --
`#pageCalculatedChannels` is a genuine sibling `<section>` of
`#pageRecordings`/`#workspaceRow`, never nested inside either, ruling
out a missing/misplaced closing tag as a contributing cause.

### Fix

One line: `#pageCalculatedChannels[hidden] { display: none; }`, the
same established pattern already used for `#workspaceRow[hidden]`/
`#pageRecordings[hidden]`/`.ww-annotation-guidance[hidden]`.

### Tests

Extended `phase5a_check.mjs` with 6 new checks: a structural regression
guard confirming the `[hidden]` override rule is present in the shipped
stylesheet (verified directly to fail without the fix and pass with it
-- jsdom cannot render CSS cascade, so this is the only check capable of
catching a regression of this specific kind), an exactly-one-page-
visible + exactly-one-nav-item-active assertion for each of the three
real pages (Recordings/Waveform/Calculated Channels), a rapid-switching
sequence across all three, and a hide-don't-destroy check confirming
in-progress builder state (selected operation + partial input list)
survives a round trip through Waveform and back -- **32/32 passing** in
the file overall (26 prior unchanged). Full frontend suite reconfirmed
at exactly the true 33-failure baseline across the same pre-existing
files (zero net new regressions). Backend untouched, 519/519 unchanged.

### Decision

No new decision. See the "Update" note appended to
[DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations)
(a bug fix to that decision's own implementation, not a new decision).

## Phase 5A UAT — Absolute Time after adding a calculated channel (2026-08-21)

### Scope

Owner UAT regression: in the main Waveform workspace, Absolute Time
worked for a normal source channel, then stopped being selectable after
adding a calculated channel. The requested investigation had to prove
whether the problem was a calculated-channel timing eligibility issue,
a trace rendering issue, or an unintended Absolute/Elapsed refetch or
X/Y rewrite.

### Investigation / root cause

Headless browser reproduction against `frontend/index.html` proved the
failure path. With only the real source channel displayed,
`wwAvailableTimeModes()` returned `["absolute", "elapsed"]` and
`wwSetTimeMode("absolute")` worked. After adding a calculated channel,
`wwCalculatedChannelMeta()` supplied `recordingStartTime: null` and
`timingReference: null`; `wwAddSelectedChannels()` parsed those into a
null `recordingStartMs`, and `wwTimeModesForChannel()` therefore
returned only `["elapsed"]` for the calculated trace. The workspace-wide
intersection in `wwAvailableTimeModes()` then correctly disabled
Absolute for the whole visible workspace. Plotly trace X arrays stayed
numeric elapsed seconds, and switching time modes did not fetch or
rewrite X/Y data.

### Fix

Added `ww.sourceTiming`, populated from the same
`GET .../sources/{id}/channels` timebase response that already feeds
`ww.sourceBounds`. Calculated channels still use their own `calc-*` id
as display identity, but `wwCalculatedChannelMeta()` now inherits
`recordingStartTime` and `timingReference` through
`calc.reference_source_id`, the real timing authority established by
DEC-047. `wwParticipatingSourceIds()` also resolves displayed
calculated channels through that same reference source for workspace
bounds, so a view containing only calculated traces remains grounded in
the original recording's elapsed extent. Source removal and Start New
Workspace clear `ww.sourceTiming` with the matching source/inventory
lifecycle; plain Clear remains display-only.

### Verification

Static regression tests cover the source timing cache, calculated
metadata inheritance, reference-source bounds resolution, and DEC-042's
"mode switch does not rewrite trace geometry" invariant. A browser
probe confirmed that after adding a calculated channel,
`wwAvailableTimeModes()` remains `["absolute", "elapsed"]`,
Absolute can be selected again, calculated channel
`timingReference` is `absolute`, participating source ids resolve to
the real source, and elapsed/absolute mode switching triggers no
additional waveform fetch.

## Phase 5A — Calculated Channels / Basic Signal Builder (2026-08-21)

### Scope

Owner-approved direction: Oruxa Powerwave's first mathematical signal-
derivation system, NOT an annotation tool -- a new main-sidebar page
below Table, both a Signal Builder and a Calculated Channel Manager.
Phase 1 supports exactly five basic arithmetic operations (Reverse
Polarity, Absolute Value, Multiply by Constant, N-input Addition,
ordered N-input Subtraction); RMS and every advanced calculation are
explicitly deferred.

### Navigation

A new enabled main-sidebar item, `Calculated Channels`, immediately
below `Table`. Uses the SAME `shellSetCurrentPage()` "hide, don't
destroy" mechanism Waveform/Recordings already established -- navigating
away and back never loses builder state, refetches the registry, or
disturbs waveform state (viewport/displayed channels/layout mode all
verified unchanged across a round trip).

### Signal Builder

One page: operation cards (five, no RMS) -> a dynamic configuration
panel (fields shown depend on the selected operation's own arity) ->
Signal Name/Unit -> Create. Never a formula text parser (section 74) --
structured operation forms only.

### Supported operations

Reverse Polarity (`y=-x`), Absolute Value (`y=|x|`), Multiply by
Constant (`y=k*x`, dimensionless `k`, output unit unchanged), N-input
Addition (`y=x1+x2+...+xN`), ordered N-input Subtraction
(`y=x1-x2-...-xN`, explicitly left-associative).

### N-input model

Addition/Subtraction take an ORDERED LIST of 2-or-more inputs -- never a
hard-coded 2-channel model. Add/remove/reorder (up/down) controls;
duplicate inputs explicitly allowed (`A+A` valid, never silently
deduplicated, section 41).

### Ordered subtraction

Input order is preserved end to end -- builder state, expression
preview, and the stored definition's own `inputs` array all agree.
Reordering (verified: A-B-C -> A-C-B) updates the preview immediately
and the eventual created channel's own `inputs` order matches exactly.

### Full-resolution authority

Every operation evaluates against `active.record.waveform_data`
directly (never Plotly trace arrays / the reduced display envelope).
Eager evaluation at creation (section 46) -- computed once, retained
server-side in a new workspace-scoped `CalculatedChannelRegistry`
(mirrors `WorkspaceRegistry`'s own shape/locking policy), never
re-evaluated on a later request. `_clip_and_reduce()`/`_peak_in_range()`
were extracted from `waveform_service.py`'s own existing source-channel
functions into shared, pure, array-level helpers -- reused by BOTH the
existing source-channel endpoints (verified zero behavior change via the
full pre-existing backend suite before any new test was added) and the
new calculated-channel service, so there is exactly one reduction
algorithm and one peak-search algorithm in the codebase.

### Compatibility rules (the owner's own explicit time-alignment guardrail)

Same-source channels are provably aligned WITHOUT array comparison --
verified directly against the actual domain model: one
`DisturbanceRecord` has exactly one shared `waveform_data["time"]`
pandas column for every one of its analog channels. Different-source
channels are rejected UNLESS their true ABSOLUTE instants
(`source.start_time + elapsed`, not raw elapsed arrays -- two
independently-triggered recordings can trivially share identical
elapsed arrays without representing the same physical instant) are
proven identical within a deliberately tight `1e-9` second tolerance.
Equal sample count or equal sampling rate alone are explicitly
insufficient. No interpolation/resampling/time-shifting/crop-to-overlap
is ever performed -- an unproven pair is rejected outright with a plain-
language message. Units: multi-input operands' unit strings must be
identical (no dimensional conversion layer); all-missing allowed
(blank output unit), mixed known/missing rejected.

### Calculated channel model

`ChannelRef {kind: "source"|"calculated", source_id?, channel_name?,
calculated_channel_id?}` -- one structured reference type, reused for
builder inputs, stored dependencies, and resolution. `CalculatedChannel
{id, workspace_id, name, unit, operation, inputs, parameters,
dependency_ids, reference_source_id, time, values, created_at}` --
`reference_source_id` is the real source that ultimately grounds a
channel's own (inherited, never modified) time array, propagated
transitively through arbitrarily deep calculated-from-calculated chains
-- what lets both timebase-compatibility checking and source-removal
cascade collapse to a simple identity/filter check rather than a graph
walk.

### Calculated-from-calculated

Supported from Phase 1 (section 22): a calculated channel is selectable
as input to a further calculation immediately, subject to the same
compatibility rules. Verified: `Sum = A+B`, `Scaled = Sum*2`,
`AbsScaled = abs(Scaled)` all produce correct full-resolution values.
Explicit `dependency_ids` (direct only, never flattened) + a generic,
independently-testable `would_create_cycle()` reachability guard
(structurally unreachable via the real one-shot creation API today --
calculated channels are immutable and every dependency must already
exist -- but implemented and tested against a hand-constructed graph as
defense in depth per the task's own explicit instruction).

### Waveform integration

A calculated channel is treated as an analog-like PSEUDO-SOURCE channel
everywhere in the existing rendering/layout/annotation machinery
(section 53/58): its own server-generated id (`"calc-" + <hex>`) is used
AS `sourceId`, its own name AS `channelName` -- so
`wwAddSelectedChannels()`/`wwRemoveChannelByKey()`/`ww.displayed`/
`ww.channelColors`/Grouped-Separate-Custom/the Annotation List's own
`sourceId`+`channelName` fields all work COMPLETELY UNCHANGED, zero new
branching. A new "Calculated Channels" group in the Workspace Sidebar
(workspace-scoped, always rendered regardless of which source is
selected) mirrors the analog channel row's own toggle convention.
Default-hidden on creation (DEC-038, unchanged policy). ONE visibility
authority (section 52): the manager's own eye icon and the sidebar row
both read/write the SAME `ww.displayed` -- verified directly, toggling
from either side updates the other.

### A/B values

New batched `POST .../calculated-channels/cursor-values` (workspace-
scoped, mirrors `.../cursor-values`' own per-source batching shape),
reusing `_nearest_sample_index()` directly. Verified: nearest full-
resolution calculated sample, matching hand-computed expected values.

### +Peak/-Peak

New batched `POST .../calculated-channels/peak-values`, reusing
`_peak_in_range()` directly -- same earliest-tie/non-finite-masking
behaviour as source channels. Dynamic viewport recalculation (Phase 4G's
own `wwRecalculateAllPeakAnnotations()`) already naturally covers
calculated channels once `wwRecalculatePeakAnnotationsForSource()`'s own
fetch dispatches correctly -- verified directly (peak value changes
after a viewport change).

### Callout

Included THIS phase (the task's own "SHOULD" tier) -- a new
`POST .../calculated-channels/{id}/annotation-anchor`, reusing
`_nearest_sample_index()` directly, extending the exact same dispatch
pattern the other endpoints already needed. Turned out to be the same
small increment as A/B and Peak, not a disproportionate refactor, so it
was not deferred. Verified: Callout anchors to the correct calculated
full-resolution sample.

### Adaptive resolution

Calculated-channel display range extraction reuses `_clip_and_reduce()`
directly -- verified: a >10,000-sample calculated channel returns
`min_max_envelope` for a broad view and `full_resolution` for a deep
zoom, exactly the same threshold/behaviour as a source channel.

### Delete/dependency lifecycle

Immutable after creation (section 47, no edit-in-place). Delete is
dependency-aware -- BLOCKED (never a silent cascade) while another
calculated channel still depends on it, with a concise inline message
naming the dependent(s) (verified directly: delete `Sum` while `Scaled`
depends on it is rejected; delete succeeds once `Scaled` is removed
first).

### Source removal

Removing a source removes every calculated channel grounded on it,
directly or transitively, via a flat `reference_source_id` filter (no
graph walk) -- both backend (`DELETE .../sources/{id}` now cascades) and
frontend (`performRemoveSource()` reconciles its own
`ww.calculatedChannels` mirror + cleans up any now-invalid display
state) verified directly.

### Workspace lifecycle

"Clear workspace" (display-only) preserves calculated-channel
DEFINITIONS -- same established policy as every other workspace-scoped
collection. "Start New Workspace" clears them completely through the
SAME `DELETE /api/v1/workspaces/{id}` call already used for that purpose
-- that endpoint's own pre-existing docstring had explicitly anticipated
calculated channels as a future workspace-owned resource needing exactly
this one lifecycle hook. Verified both directly.

### Original recording immutability

Verified directly: creating a calculated channel never mutates a
source's own `waveform_data` array (DEC-009/DEC-015 preserved).

### Performance/memory

Eager evaluation means one array-transform pass per creation (O(n) in
the largest input's own sample count for all five operations); N-input
Addition/Subtraction is O(n*N), a single pass per input, never a
per-sample nested loop. Calculated channels retain their own
full-resolution arrays server-side for the life of the workspace
(acceptable for Phase 1, same policy as `ActiveSource.record` already
established) -- no premature disk persistence introduced.

### The one deliberate structural shortcut (reported, not silent)

Network-request dispatch (source endpoints vs. `/calculated-channels/...`)
is one small helper, `wwIsCalculatedSourceId()`, checking a `"calc-"` id
prefix -- chosen over threading a fully structured `ChannelRef` type
through the ENTIRE existing frontend call graph, which section 58 of the
task explicitly warned against as disproportionate for this phase.
Confined to exactly the request-URL/shape dispatch points; the
rendering/layout/state layer never needed to know the difference.

### Scope trim (reported)

The Signal Builder's input picker is scoped to `ww.channelMeta`
(channels already brought into this workspace's Waveform this session)
plus existing calculated channels, rather than eagerly fetching every
channel of every imported source up front -- a deliberate, smallest-
clean-abstraction Phase 1 choice (section 58).

### Tests

Backend: 3 new test files -- `test_calculated_channel_domain.py` (63
pure-function tests: the 5 evaluation functions, unit compatibility, the
full time-alignment guardrail matrix A-H from the owner's own follow-up
message, cycle detection), `test_calculated_channel_service.py`
(service-layer tests against synthetic `ActiveSource` fixtures --
creation/validation/dependency-chains/delete-blocking/source-removal-
cascade/immutability/display-cursor-peak-anchor pipelines),
`test_calculated_channel_api.py` (20 end-to-end API tests via a real
COMTRADE upload). **83 new backend tests, 519/519 passing overall**
(436 previously existing, unmodified, confirmed via a pre-change
baseline run before any new test was added). Frontend: new
`phase5a_check.mjs`, **26/26 passing** -- navigation, operation cards,
dynamic forms, N-input add/remove/reorder + expression preview,
subtraction reordering, validation (arity/units/timebase), manager list,
Waveform sidebar group + default-hidden + shared visibility authority,
Grouped/Separate/Custom, A/B values, +Peak/-Peak dynamic recalculation,
Callout, adaptive resolution, calculated-from-calculated dependencies,
dependency-blocked delete, source-removal cascade, Start New Workspace/
Clear Workspace lifecycle, and original-source immutability. One
pre-existing `phase3buat8_check.mjs` assertion (enabled main-sidebar
item list) updated in place to include the new nav item -- the expected
consequence of this phase's own navigation requirement, not a
regression (same precedent as Phase 4G's own menu-count update). Full
frontend suite reconfirmed at exactly the true 33-failure baseline
across the same pre-existing files (zero net new regressions).

### Decision

See [DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations).

## Phase 4G-UAT Bug Fix — Guidance Dismissal (2026-08-21)

### Scope

Owner UAT on the ribbon below found two symptoms: it did not disappear
after a successful +Peak/-Peak creation, and it did not disappear on
Escape either. No new decision entry -- an "Update" note was appended to
DEC-046's addendum instead (see below).

### Root cause

Identical for both symptoms, and NOT a state/lifecycle bug: a CSS-
cascade bug. `.ww-annotation-guidance { display: flex; }` (author CSS)
beats the UA stylesheet's own `[hidden] { display: none }` rule by
ORIGIN alone (author declarations always outrank user-agent declarations
in the normal cascade, regardless of selector specificity or source
order) -- so `wwUpdateAnnotationPlacementGuidance()`'s own `el.hidden =
true` had zero visible effect, even though `ww.annotationPlacementType`
was already correctly `null` on both paths (confirmed directly, not
inferred). This is the SAME class of bug already caught and fixed
elsewhere in this file for `#workspaceRow[hidden]`/
`.shell-status-item[hidden]`/`#pageRecordings[hidden]`/
`.ww-toolbar[hidden]` -- this new ribbon simply hadn't received the same
treatment when it was first added. jsdom cannot render CSS cascade, so
no jsdom-based assertion against the DOM `hidden` property (which was
already correct) could ever have caught this.

### Fix

One line: `.ww-annotation-guidance[hidden] { display: none; }`.

### A second, genuine race found while investigating Escape

A Peak creation request already in flight when Escape (or a switch to a
different tool, or even re-entering the SAME tool after Escape) fired
could still resolve successfully afterward and silently create an
annotation from a placement session the engineer had already left. Fixed
with a new monotonic `ww.annotationPlacementGeneration` counter, bumped
on every genuine placement-mode transition (fresh entry/tool switch,
exit via success or Escape -- deliberately NOT on a same-tool reselect
no-op) and captured by `wwCreatePeakFromClick()` at its own start; a
stale/superseded request's eventual result -- success OR failure -- is
now discarded silently before touching any state or showing any error
toast, mirroring the SAME staleness-guard pattern already established
for `ww.epoch` (workspace resets) and `wwPeakValuesGeneration` (per-
source recalculation). Verified directly: cancelling an in-flight
request via Escape, then releasing it, creates nothing; a fresh SAME-
tool session started immediately afterward is not blocked by the old
request's own busy state and completes normally on its own.

### Tests

Extended `phase4g_check.mjs` with 13 new checks: a structural regression
guard asserting the `.ww-annotation-guidance[hidden]` CSS override rule
is actually present in the shipped stylesheet source (the only
meaningful regression guard for a jsdom-invisible CSS-cascade bug), the
full asynchronous successful-+Peak-creation path (never calling
`wwExitAnnotationPlacementMode()` directly -- exercising the real
request-completion path only), -Peak Escape, invalid-click-then-Escape,
API-failure-then-Escape, Escape-during-an-in-flight-request (ribbon
hides immediately, stale success creates nothing), a same-tool retry
succeeding normally after an Escape-cancelled request, Annotate toolbar
active-state + `annotationPlacementBusy` invariants on Escape, and
Text Note/Callout Escape regressions (confirming the fix is Peak-
specific where it needed to be and did not disturb their own established
one-shot behavior) -- **66/66 passing** in the file overall (56 prior
Phase 4G/4G-UAT checks unchanged). Full frontend suite reconfirmed at
exactly the true 33-failure baseline across the same pre-existing files
(zero net new regressions). Backend: untouched, 436/436 unchanged.

### Decision

No new decision. See the "Update" note appended to
[DECISIONS.md — DEC-046's Phase 4G-UAT addendum](DECISIONS.md#addendum-2026-08-21-refinement--persistent-annotation-placement-guidance-ribbon-phase-4g-uat)
(a bug fix to that addendum's own implementation, not a new decision).

## Phase 4G-UAT — Persistent Annotation Placement Guidance Ribbon (2026-08-21)

### Scope

Owner UAT result on Phase 4G directly below: "Engineering behavior:
PASS" but no guidance told the engineer what to do after selecting
Maximum Peak/Minimum Peak from the Annotate dropdown. This refinement
adds a persistent inline guidance ribbon, mandatory for `peak_max`/
`peak_min`, and also (the task's own "if extremely straightforward and
clearly generic" invitation) enabled for `text_note`/`callout`.

### Guidance architecture

One generic component, driven entirely by the SAME single authority
`wwEnterAnnotationPlacementMode()`/`wwExitAnnotationPlacementMode()`
already are (`ww.annotationPlacementType`) -- a new
`WW_ANNOTATION_PLACEMENT_GUIDANCE` map (`{icon, message}` per type),
`wwAnnotationPlacementGuidance(type)`, and
`wwUpdateAnnotationPlacementGuidance()`, called ONLY from those two
existing state-transition functions -- never per-render, never a second
competing state or timer. Extending to a future annotation type is one
more map entry, never scattered per-type banner code.

### Maximum Peak

"Maximum Peak active — click an analog waveform channel to find the
maximum in the current view. Press Esc to cancel." Shown the instant
`peak_max` placement mode is entered.

### Minimum Peak

"Minimum Peak active — click an analog waveform channel to find the
minimum in the current view. Press Esc to cancel."

### Text Note / Callout (optional, enabled)

"Text Note active — click in the waveform workspace to place a note.
Press Esc to cancel." / "Callout active — click an analog waveform trace
to place a callout. Press Esc to cancel." Enabled because the same
generic map already covered them cleanly with zero extra branching.

### Persistence

No auto-dismiss timer anywhere in the file -- the ribbon's only
visibility authority is `ww.annotationPlacementType`; verified directly
across many ticks/re-renders while mode stays active.

### Invalid clicks

Sidebar, toolbar, digital region, and empty-waveform-area clicks all
leave placement mode -- and the ribbon -- untouched; verified directly
for +Peak.

### Peak completion-timing correction (engineering-adjacent fix required by the task)

Callout's own established one-shot "exit placement mode immediately on
click, regardless of outcome" timing (Phase 4F) is UNCHANGED. Peak's own
timing was corrected: `wwCreatePeakFromClick()` previously relied on
`wwWireAnalogPanelClick()` exiting mode BEFORE the async request even
started (inherited from Callout's own pattern) -- meaning a failed/no-
data Peak result already left the user with no active tool and no
guidance. Now Peak placement mode exits ONLY on a successful creation;
a failed request, a no-valid-samples result, or a network error all keep
placement mode (and the ribbon) active so the engineer can simply click
again. A new `ww.annotationPlacementBusy` flag (set/cleared via
`try/finally` around the whole request) guards against a second
concurrent request while one is already in flight -- the SAME "no
double-fire" protection Callout's own comment originally described,
adapted to Peak's now longer-lived active window. Verified directly: a
forced API failure and a no-data (out-of-bounds viewport) result both
leave mode active and the ribbon visible with zero annotation created;
retrying the SAME click afterward succeeds normally; a second click
while a request is in flight produces zero additional backend requests
and never a duplicate annotation.

### Tool switching / re-select

Switching from +Peak to -Peak updates the SAME ribbon element in place
(never a duplicate, never stale Maximum Peak text left behind) --
verified directly, including confirming exactly one
`#wwAnnotationGuidance` element exists at all times. Reselecting the
already-active tool is the pre-existing no-op
(`wwEnterAnnotationPlacementMode()`'s own early return), so the ribbon
is untouched, never re-rendered.

### Escape

Unchanged, reconfirmed: cancels placement mode, removes the toolbar
active state, hides the ribbon, creates nothing.

### Annotate dropdown

Opening/closing the dropdown while a placement mode is active never
dismisses it -- verified directly (toggling the dropdown twice while
+Peak is active leaves mode and the ribbon untouched).

### Dynamic recalculation is unrelated

Verified directly: after a successful Peak creation (ribbon dismissed),
subsequent zoom/pan viewport changes recalculate the annotation
normally, and the ribbon never reappears -- it is scoped entirely to
initial channel-selection placement mode, never touched by
`wwRecalculateAllPeakAnnotations()`.

### Layout / accessibility / theme

A normal-flow sibling row (`#wwAnnotationGuidance`) between the waveform
toolbar and `#activeViewArea` -- never `position: absolute/fixed`, so it
cannot overlay/intercept Plotly, the sidebar, or the toolbar (confirmed
by construction: it occupies distinct layout space, not overlapping
screen space with any of them). `role="status"` (informational, never an
aggressive alert), updated only on the two state transitions so
assistive tech isn't re-announced on ordinary waveform re-renders. Text
wraps via `overflow-wrap: break-word` rather than forcing a fixed width.
Styling reuses existing semantic tokens only (`--accent-wash-soft`,
`--panel-border`, `--text`, `--text-dim`, `--accent`, `--radius`) -- no
new theme tokens, no red/alarm styling, both themes covered by
construction (no theme-specific hardcoded colors).

### Tests

Extended `phase4g_check.mjs` with 19 new checks (Maximum/Minimum Peak
guidance content, ribbon absent before any placement mode, invalid
clicks never dismiss, successful creation hides the ribbon, Escape
hides it, API-failure and no-data-unavailable both keep mode/ribbon
active with zero annotations created, a failed attempt's SAME mode
successfully retries afterward, tool switching updates one ribbon in
place, re-select-same-tool no-op, dropdown toggling doesn't dismiss,
toolbar active state + ribbon coexist, no-timeout across many
ticks/renders, dynamic recalculation never re-shows the ribbon,
`role="status"` present, a concurrent second click during an in-flight
request is ignored, a regression check confirming Callout's own
exit-immediately timing is unchanged, and optional Text Note/Callout
guidance) -- **56/56 passing** in the file overall (37 prior Phase 4G
checks unchanged). Full frontend suite reconfirmed at exactly the true
33-failure baseline across the same pre-existing files (zero net new
regressions). Backend: untouched, 436/436 unchanged (no backend file
touched this refinement).

### Decision

See [DECISIONS.md — DEC-046 addendum](DECISIONS.md#addendum-2026-08-21-refinement--persistent-annotation-placement-guidance-ribbon-phase-4g-uat)
(a refinement of DEC-046, not a new major decision).

## Phase 4G — Dynamic Maximum / Minimum Peak Annotation (2026-08-21)

### Scope

Owner-approved direction: the third and fourth annotation types,
`type: "peak_max"`/`type: "peak_min"` (`+Peak`/`-Peak`), generic recorded-
analog-channel measurements (never instantaneous-voltage/RMS/power/
frequency-specific) calculated over the engineer's CURRENT VISIBLE X
VIEWPORT and dynamically RECALCULATED whenever that viewport genuinely
changes. No Peak-to-Peak this phase.

### Creation UX

`Annotate -> Maximum Peak (+Peak)` (or `Minimum Peak (-Peak)`) enters
one-shot placement mode; the next valid click on an analog trace resolves
the exact clicked channel via its trace's own stable
`"sourceId::channelName"` `meta` field (the SAME mechanism Callout already
established, DEC-045) and immediately calculates that channel's max/min
over `ww.viewport`. Unlike Callout, the click's own X position is
irrelevant to the result -- only channel identity matters. A viewport with
no valid (finite) samples for the clicked channel shows a concise error
and creates nothing (never a partial/broken annotation).

### Search interval: current visible X viewport

Always `ww.viewport.start`/`ww.viewport.end` -- never the whole
recording, never an A/B cursor interval, never the (possibly reduced)
displayed Plotly trace. At full-record view this naturally covers the
whole visible record.

### Dynamic recalculation

Hooked into the ONE existing call site every genuine X-viewport change
already funnels through, `wwApplyAndFetchViewport()` (zoom, pan, step
zoom via `wwStepZoomX()`, and Reset Time View via `wwResetTimeView()`
all reach it) -- a new `wwRecalculateAllPeakAnnotations(startTime,
endTime)` groups every active +Peak/-Peak annotation by its own
`sourceId` and fires exactly ONE batched `POST .../peak-values` request
per distinct source, updating each affected annotation's SAME id in
place (never a new annotation, never reordering the Annotation List --
`createdAt` is untouched). Y-range changes (Y step zoom, Autoscale Y),
Absolute/Elapsed presentation switching, and Peak box drags never call
this function at all -- verified directly via before/after
`peak-values` request counts (zero in every case).

### Full-resolution authority

A new backend service function, `resolve_peak_value()`
(`app/services/waveform_service.py`), reads
`active.record.waveform_data` directly -- the SAME authoritative record
`resolve_annotation_anchor`/`extract_waveform_range` already read --
never the reduced `min_max_envelope` display representation, regardless
of how many samples fall in the requested interval. Boundary-inclusive
range clipping via the SAME `np.searchsorted` technique
`extract_waveform_range` already established; the requested interval is
narrowed to the channel's own recorded time bounds when the viewport
extends beyond them (never fabricating samples). Non-finite samples
(`NaN`/`inf`) are masked out via `np.isfinite` before the max/min search
-- if every sample in the interval is non-finite (or the intersection is
empty), the result is `available: false`, never a fabricated peak.

### Tie rule

Exact ties select the EARLIEST sample -- satisfied for free by
`numpy.argmax`/`argmin`'s own documented first-occurrence-on-tie
behaviour, not a second hand-rolled implementation. Verified against the
task's own regression fixtures: `[1, 5, 3, 5, 2]` -> max value 5 at
index 1 (the first 5); `[-2, -7, -3, -7]` -> min value -7 at index 1.

### Peak payload

Stable for the annotation's lifetime: `id`, `type`, `workspaceId`,
`sourceId`, `channelName`, `mode` (`"max"`/`"min"`), `boxOffset`.
Dynamic, recalculated in place: `sampleIndex`, `peakElapsedSeconds`,
`peakValue`, `unit`, `available`. No `text` field -- section 27's own
explicit "do not turn the computed value lines into arbitrary editable
text" -- a Peak never enters `wwBeginAnnotationEdit()`'s textarea path
(no dblclick listener is ever wired for it).

### Rendering

Reuses Callout's shared connector/marker/box geometry engine rather than
a second implementation (section 24 of the task): `wwAnchoredAnnotationContentPosition()`/
`wwAnchoredAnnotationPagePosition()`/`wwAnchorValueToPixelY()` (renamed,
generalized from their Callout-only predecessors via two small
type-dispatching getters, `wwAnchoredAnnotationTime()`/
`wwAnchoredAnnotationValue()`) and `wwUpdateCalloutConnectorGeometry()`
(extended with an `isPeak` parameter) serve BOTH `callout` and
`peak_max`/`peak_min` identically. The canvas label shows a two-line
system-computed text (`"+Peak: 230.4 MW"` / `"t = 219.400 ms"`, or the
Absolute-mode clock-time equivalent via the SAME
`wwFormatAbsoluteElapsedTime()`/`wwFormatCursorDuration()` authority
Callout's own Annotation List meta-line already uses), rendered via
`.textContent` into two dedicated child elements
(`.ww-peak-value-line`/`.ww-peak-time-line`), never `.innerHTML`. A small
filled-triangle header glyph (apex up for +Peak, apex down for -Peak) and
a new shared `--annotation-peak-accent` token (muted teal-green, both
themes -- deliberately not alarm red, not A/B cursor blue/red, not
Callout's own amber) give it a recognizable but restrained identity.

### Label dragging: movable box, fixed calculated marker

The label box is fully draggable via the SAME `wwWireCalloutBoxDrag()`
Callout's own box already uses (offset-only, never touches the anchor,
never calls the backend, never triggers recalculation) -- verified
directly. The anchor MARKER itself is deliberately non-draggable, the
key interaction difference from Callout's own now-movable anchor
(DEC-045's addenda): the global anchor-drag pointerdown handler
(`wwWireCalloutAnchorDrag()`'s `onPointerDown()`) now checks
`annotation.type === "callout"` before starting any drag preview, and a
Peak's own hit circle is `pointer-events: none` with a `cursor: default`
CSS override -- no draggable affordance at all, verified by attempting a
drag on it and confirming zero state change and zero backend call.

### Visibility

An anchor currently unprojectable (outside the X viewport, outside the
panel's current Y range, or its channel not displayed) is hidden from
canvas exactly like Callout's own (box + connector + marker), staying
fully intact in `ww.annotations`/the Annotation List. A viewport with no
valid sample for the channel marks the annotation `available: false`
(same hidden-from-canvas treatment, preserved identity) rather than
deleting it -- the next viewport change with a valid intersection
restores it automatically. Hiding/re-showing the anchored channel never
needs a separate "recalculate on show" code path: recalculation always
runs on every genuine viewport commit regardless of current display
visibility (the backend computation is independent of Plotly), so a
re-shown channel's Peak is already current for the present viewport by
construction -- a deliberate, documented policy choice (DEC-046's own
"Alternatives considered"). Layout-mode switches (Grouped/Separate/
Custom) preserve the same annotation id and reproject against whichever
panel currently renders its channel, verified directly (no duplicate
marker).

### Source removal / workspace lifecycle

Removing a source deletes its Peak annotations outright (extends the
SAME sweep DEC-045 established for Callout,
`wwRemoveAnchoredAnnotationsForSource()`, renamed/generalized from its
Callout-only predecessor `wwRemoveCalloutsForSource()`) -- no rebinding
by same channel name on a different source. "Clear workspace" preserves
Peak annotations (display-only, matching every other annotation type's
established semantics); "Start new workspace" clears them along with
every other type.

### Stale-response protection

A per-source generation counter (`wwPeakValuesGeneration`, the SAME
pattern `wwCursorValuesGeneration` already established for A/B cursor
values) ensures a slower earlier-viewport batch response can never
overwrite a faster later-viewport one; a per-annotation
`ww.annotations.has(id)` re-check before applying each batch item's
result discards updates for an annotation deleted while its request was
in flight (verified directly for both cases).

### Performance

Recalculation is fire-and-forget from `wwApplyAndFetchViewport()` --
never awaited, so it cannot delay the existing waveform-refetch
lifecycle. Multiple Peak annotations on ONE source share exactly ONE
batched request per viewport change (verified directly: 3 annotations on
one source -> 1 request, 3 channel/mode pairs in its body), never one
request per annotation. Zero Plotly rebuilds, zero waveform refetches,
zero cursor-value requests, and zero `ww.measurementCursors` reads/writes
from any Peak code path -- confirmed by test.

### Existing annotations unaffected

Text Note and Callout behavior (including Callout's own movable anchor
and free 2D drag preview, Phase 4F-UAT/4F-UAT2) are completely
unchanged -- confirmed by re-running `phase4f_check.mjs` unmodified
(46/46 still passing) alongside the new Phase 4G suite.

### Tests

New `phase4g_check.mjs`: **37/37 passing** -- menu presence/order/no-
Peak-to-Peak, exact trace identity, viewport-only search interval
(click-X-irrelevant + narrower-viewport-returns-local-not-global-
extremum), full-resolution authority, earliest-tie regression, dynamic
recalculation on zoom/pan/step-zoom/Reset-Time-View (same annotation id,
`createdAt` unchanged), zero recalculation on Y-zoom/Autoscale/Absolute-
Elapsed/box-drag, stale-viewport-response rejection, deletion-mid-flight
discard, unavailable-for-viewport handling, hidden-channel/re-show/
layout-mode behavior, non-draggable-marker + draggable-box, multi-type
and multi-source coexistence with one-batched-request-per-source, source
removal, workspace lifecycle, and safe `.textContent`-only rendering.
One pre-existing `phase4e_check.mjs` assertion (`Annotate menu has
exactly 2 items`) was updated in place to `4` -- the EXPECTED consequence
of this phase's own required menu additions, not a regression (same
precedent as Phase 2C-C3's own outdated-assertion updates). Full frontend
suite reconfirmed at exactly the true 33-failure baseline across the same
pre-existing files (zero net new regressions). Backend: **436/436
passing** (24 new -- `test_peak_value_service.py`,
`test_peak_value_api.py` -- + 412 previously existing, unmodified).

### Decision

See [DECISIONS.md — DEC-046](DECISIONS.md#dec-046--maximumminimum-peak-annotations-are-generic-recorded-channel-measurements-over-the-current-visible-x-viewport-dynamically-recalculated-on-genuine-x-viewport-changes).

## Phase 4F-UAT2 — Free 2D Callout Anchor Drag Preview (2026-08-21)

### Scope

Owner UAT result on the movable-anchor refinement directly below:
"Engineering outcome: PASS. User experience: FAIL." Constraining the
preview marker to horizontal-only movement (pointer X drove the
preview, pointer Y stayed pinned to the current anchorValue's own
projection) felt like dragging along a rail even though the final snap
was already correct. This refinement changes ONLY the drag PREVIEW's
own presentation -- the engineering model (DEC-045, and the same-
channel-only movable-anchor addendum) is completely unchanged.

### Previous UX issue

`livePreviewUpdate()` computed the preview Y from
`wwCalloutValueToPixelY(panel, annotation.data.anchorValue)` -- the
CURRENT, still-authoritative value's own projection -- rather than from
the pointer. Visually, the marker only ever moved left/right; a
vertical mouse movement had zero visible effect until release.

### New preview behavior: free X/Y visual drag

`onPointerMove()` now computes a clamped `{x, y}` page-pixel point
directly from `event.clientX`/`event.clientY` (via a new
`clampPreviewPoint()` helper) and passes BOTH into `livePreviewUpdate()`,
which no longer touches `wwCalloutValueToPixelY()`/`anchorValue` at all
during the preview -- it simply converts the given page point to
content coordinates and positions the marker/connector/box there.
Verified directly: an X-only pointermove changes the marker's `cx` and
leaves `cy` unchanged; a Y-only pointermove changes `cy` and leaves `cx`
unchanged; a diagonal pointermove changes both.

### Engineering authority: X-only final resolution, Y preview-only

`onPointerUp()` is textually UNCHANGED from the movable-anchor
refinement below -- it still reads `event.clientX` alone (via the
existing `wwCursorPixelXToTime()`, which already clamps to
`ww.viewport`) to derive the approximate elapsed time sent to
`POST .../annotation-anchor`; `event.clientY` is never read there, at
any point, before or after this refinement. Verified directly with a
wide diagonal drag (Y swinging from well above to well below the panel,
finishing back near the target X): the resolved `sampleIndex`/
`anchorElapsedSeconds`/`anchorValue` exactly match the nearest full-
resolution sample at the target elapsed time, completely independent of
where the pointer's Y excursion went.

### Snap behavior

Because `onPointerUp()` is unchanged, the "snap" itself is unchanged
too: once the backend resolves the real sample, `wwUpdateAnnotation()`
commits `sampleIndex`/`anchorElapsedSeconds`/`anchorValue`/`unit` and
the SAME generic `wwRenderAnnotations()` pass redraws the marker at its
TRUE projected position (X from `wwCursorTimeToPixelX()`, Y from
`wwCalloutValueToPixelY()` against the newly-committed `anchorValue`) --
this is the visible "snap from free position to exact waveform sample"
the task's own section 5 describes as desirable feedback, achieved with
zero new snap-specific code (the existing render pass already produces
it as a side effect of committing the new anchor).

### Box/connector

`boxOffset` is read and applied exactly as before -- unaffected by this
refinement (the box still follows whatever anchor position
`livePreviewUpdate()`/the post-snap render pass computes, by the same
stored relative offset). The connector's own `x2`/`y2` endpoint is
verified to equal the marker's own `cx`/`cy` at every step of a
multi-move drag, both during the free preview and after the snap.

### Bounds

`clampPreviewPoint()` clamps X to the shared plot X domain
(`dragMetrics`, the exact same bounds `wwCursorPixelXToTime()` itself
uses) and Y to the anchored channel's own CURRENT panel rect
(`panel.chartEl.getBoundingClientRect()`) -- purely a visual containment
measure so the marker never wanders permanently off-canvas; neither
clamp is engineering authority, and the clamped Y is never read by
`onPointerUp()` at all.

### Same-channel visual meaning

Unchanged: the free preview may temporarily appear away from the actual
waveform trace during drag (expected/intentional), and on release it
snaps back onto the SAME channel's real waveform -- the same-channel
restriction from the movable-anchor addendum is untouched by this
refinement (no new code path could ever substitute a different
channel).

### Failure/cancel

Unchanged behavior, reconfirmed: because the preview never writes to
`annotation.data` (true both before and after this refinement -- only
WHERE the preview visually sits changed, not WHETHER it's written to
state), a forced backend failure, Escape mid-drag, or `pointercancel`
all still restore the original authoritative anchor exactly by simply
re-rendering from the untouched truth.

### Visual feedback

Added a subtle translucency (`opacity: 0.82`) to the marker and
connector while the drag-active visual state is applied, on top of the
already-existing stronger ring -- distinguishes the free-floating
preview as visibly provisional. No animation/transition added; the
snap-to-authoritative-position on release remains immediate, per the
task's own explicit "prefer immediate snap first" preference.

### Interaction isolation

Unaffected -- the anchor hit target, A/B cursor hit targets, Plotly's
own canvas, and the Callout box's own drag handle remain four
structurally separate interaction surfaces; this refinement only
changed what happens once the anchor hit target's own drag is already
in progress.

### Tests

Extended `phase4f_check.mjs` with atomic `pointerDownOn()`/
`pointerMoveOn()`/`pointerUpOn()` helpers (allowing a single test to
inspect marker/connector state BETWEEN moves within one unreleased
drag) plus 7 new checks: X-only preview movement, Y-only preview
movement, diagonal preview movement, authoritative-state-untouched-
during-preview, connector-follows-preview-at-every-step, the drag-active
visual state's own presence/clearing, and a wide-diagonal-drag
end-to-end resolution check (same channel, preserved boxOffset, value
from the real recorded sample, never from pointer Y) -- **46/46 passing**
in the file overall (39 prior + 7 new). Full frontend suite reconfirmed
at exactly the true 33-failure baseline across the same 14 pre-existing
files (zero net new regressions). Backend: untouched, 412/412 unchanged
(no backend change needed -- the existing endpoint already accepted an
arbitrary approximate elapsed time and never read a Y value in the
first place).

### Decision

See [DECISIONS.md — DEC-045 addendum (refinement)](DECISIONS.md#addendum-2026-08-21-refinement--anchor-drag-preview-became-free-2d-phase-4f-uat2)
(a refinement of DEC-045's own movable-anchor addendum, not a new major
decision).

## Phase 4F-UAT — Movable Callout Anchor (2026-08-21)

### Scope

Owner UAT direction on top of Phase 4F below: make the Callout ANCHOR
POINT itself draggable (previously only the label box was). The
engineering-integrity rule from DEC-045 stays fully intact: an anchor
must always resolve to an actual full-resolution recorded sample -- this
refinement does not turn it into a free arbitrary X/Y point. Same-
channel only this phase: dragging may move the anchor to a different
sample on its OWN existing source/channel, never a different channel
(cross-channel re-anchoring is explicitly out of scope, deferred to a
possible future "Change Anchor Channel" interaction).

### Movement model: same-channel re-anchoring

`sourceId`/`channelName` are read from the existing annotation and
passed UNCHANGED into the resolution request -- the drag interaction has
no code path that could ever substitute a different channel, even when
the pointer visually crosses another trace in a Grouped/Custom panel
(section 19/20/21 of the task). Verified directly: dragging a Callout
anchored to channel B through channel A's own screen space and releasing
still resolves against channel B's own recorded data.

### Drag preview: frontend-only

`wwWireCalloutAnchorDrag()` is wired ONCE via event delegation on
`#wwCalloutConnectorLayer` (`pointerdown` -> `event.target.closest("[data-callout-anchor-hit]")`),
the exact same delegation convention `wwWireCursorDrag()` already
established for A/B cursor dragging on `#wwCursorOverlay` -- so every
current and future Callout is draggable with zero per-annotation wiring.
During `pointermove`, pointer X maps to an approximate elapsed time via
`wwCursorPixelXToTime()` (reused, not reimplemented -- it already clamps
to the current `ww.viewport`, exactly the "clamp preview to current
viewport edge" section 13 asks for) and repositions the marker/
connector/box as a PURE visual preview: `annotation.data` is never
written to during this phase. Pointer Y is deliberately never read
(section 6/15) -- the marker's preview Y stays pinned to the panel's own
projection of the CURRENT (still-authoritative) `anchorValue`, so the
preview can never fabricate an engineering reading; only X moves during
preview, matching section 7's own "move the anchor preview horizontally
with the pointer" instruction literally. `boxOffset` is read and applied
unchanged throughout (section 11) -- the box tracks the preview anchor
by its existing relative offset, never reset.

### Authoritative snap: one backend request on release

`wwResolveCalloutAnchorMove()` fires exactly once, on `pointerup`, reusing
the EXACT request/error/stale-response shape `wwCreateCalloutFromClick()`
(Phase 4F's own creation path) already established -- not a second
implementation. Additionally clamps the requested time against the
anchored source's own `ww.sourceBounds` entry (section 14 -- `ww.viewport`
can span multiple sources; one source's own recorded range may be
narrower). Verified directly: many `pointermove` events during a drag
cause ZERO `.../annotation-anchor` requests; exactly ONE fires on
`pointerup`.

### Engineering state: fields changed vs. preserved

On success, ONLY `sampleIndex`/`anchorElapsedSeconds`/`anchorValue`/`unit`
are committed via `wwUpdateAnnotation()`'s existing generic `data` merge
-- `sourceId`/`channelName`/`boxOffset` are read from the response/patch
but never overwritten by it (the response is never even asked for
`source_id`/`channel_name` values to write back). Verified directly:
`sourceId`/`channelName`/`boxOffset` byte-identical before/after a
successful move; `sampleIndex`/`anchorElapsedSeconds`/`anchorValue` all
changed to the newly resolved sample.

### Box/connector: offset preservation, snap-on-release

The box's stored `boxOffset` is read, never reset, throughout the drag
(section 11) -- confirmed unchanged after a successful move. During the
drag the connector follows the temporary preview anchor; the instant a
successful resolution commits, the SAME generic `wwRenderAnnotations()`
pass (triggered by `wwUpdateAnnotation()`) redraws the connector/marker
from the NEW authoritative anchor position, which is section 12's own
"After pointerup: connector snaps to the newly resolved authoritative
sample" -- no special-cased snap code needed beyond the existing generic
render pass already reacting to a `data` update.

### Failure/cancel: full restoration semantics

Because the preview never wrote to `annotation.data`, "restoring the
original anchor" on failure, Escape, or `pointercancel` is simply calling
`wwRenderAnnotations()` again -- there is no snapshot to restore FROM,
since nothing was ever mutated to begin with. Verified for all three
paths: a forced-failure response, an Escape keypress mid-drag (capture-
phase `keydown` listener, the same convention
`wwAnnotationPlacementKeydownHandler()` already uses), and `pointercancel`
all leave `annotation.data` byte-identical to its pre-drag value, and
Escape additionally issues zero backend calls.

### A/B cursor and Plotly interaction: confirmed isolation

The anchor's hit target is a SEPARATE DOM element/subtree
(`#wwCalloutConnectorLayer`, a child of `#activeViewArea`) from both
Plotly's own chart canvas and A/B cursor's own hit targets
(`#wwCursorOverlay`/`#wwCursorLabelLayer`) -- structurally, a pointerdown
on the Callout hit target can never reach Plotly's internal handlers
(they are not ancestors of the hit target) or vice versa. Where the two
overlays' hit areas could visually coincide on screen, ordinary browser
pointer-event hit-testing (topmost hit-testable element wins) already
provides deterministic priority (section 26) with no extra conflict-
resolution code -- the connector layer's `pointer-events: none` root
with a `pointer-events: all` override only on the small (~16px) hit
circle means every other pixel in the layer is transparent to whatever
is beneath it. Verified directly: A/B cursor dragging still works
identically after a Callout anchor drag, Callout anchor dragging never
touches `ww.measurementCursors`, and normal Plotly pan/zoom (via
`plotly_relayout`) still works with a Callout anchor present.

### Annotation List: metadata refresh

`wwAnnotationMetaLine()` already reads `annotation.data` live (Phase 4F's
own existing design) -- a successful anchor move is reflected immediately
with no extra code, confirmed directly: the drawer row's channel/time/
value line updates to the new resolved values, no duplicate row appears.

### Performance

Confirmed directly (section 50): anchor drag preview causes zero Plotly
calls, zero waveform refetch, zero cursor-value requests, and zero
`.../annotation-anchor` requests until `pointerup` -- only SVG attribute
writes and a handful of style writes, matching the same performance bar
Phase 4F's own box-drag path already established.

### Tests

Extended `phase4f_check.mjs` with a `dragCalloutAnchorThroughTimes()`
helper (drives the anchor hit target through a sequence of elapsed-time
targets converted to page pixels via the app's own
`wwCursorTimeToPixelX()`, so tests target exact engineering times rather
than guessed pixel offsets) and controllable delay/forced-failure hooks
on the `/annotation-anchor` fetch mock (for the stale-response and
failure-restoration tests). 16 new checks (sections 37-49, including a
3-way split of section 49's workspace-lifecycle-during-drag scenario)
-- **39/39 passing** in the file overall. Full frontend suite reconfirmed
at exactly the true 33-failure baseline across the same 14 pre-existing
files (zero net new regressions). Backend: untouched, 412/412 unchanged
(no backend file needed for this refinement -- the existing
`.../annotation-anchor` endpoint already accepted an arbitrary
`approximate_elapsed_seconds`, so no new route/schema was needed).

### Existing unrelated working-tree edit

Re-inspected at this task's own mandatory startup step: the
`--accent` edit flagged in the two prior sessions was found FULLY
RESOLVED -- the owner committed it (`f1354f4`) and then reverted it back
to its original value in a follow-up commit (`1653a97`), both already on
`main` before this task began. The working tree was genuinely clean at
startup; no preserve-and-exclude staging was needed this time.

### Decision

See [DECISIONS.md — DEC-045 addendum (refinement)](DECISIONS.md#addendum-2026-08-21-refinement--callout-anchors-became-movable-same-channel-only-phase-4f-uat)
(a refinement of DEC-045, not a new major decision).

## Phase 4F — Analog Waveform Callout Annotation (2026-08-21)

### Scope

The second annotation type (DEC-044's own generic framework, extended
per its own "future type" design goal): `type: "callout"`, a
waveform/data-anchored annotation, in contrast to `text_note`'s
workspace-content anchoring. Analog channels only this phase. Explicitly
excluded: digital Callout, RMS/phasor/peak/delta/event-marker annotation
types, cross-channel annotation, rich text/Markdown, callout import/
export, permanent database persistence, draggable/re-anchorable anchor,
elbow/auto-routed connectors, and auto-scroll/pan-to-annotation
navigation.

### Engineering model: full-resolution sample authority

A Callout's anchor is `{sourceId, channelName, sampleIndex,
anchorElapsedSeconds, anchorValue, unit}`, resolved ONCE at creation
time against the source's own authoritative full-resolution
`active.record.waveform_data` -- never the displayed/possibly-reduced
Plotly trace, never interpolated, never derived from raw pointer-X or
visual pixel geometry. Same engineering-integrity principle DEC-040
already established for A/B cursor measurements, reusing (not
reimplementing) that exact nearest-sample logic:
`backend/app/services/waveform_service.py`'s `_nearest_sample_index()`
(binary search via `np.searchsorted`, earlier-sample-on-exact-tie) and
`_resolve_analog_channel()` (analog-only validation, raises
`ChannelNotFoundError`/`ChannelNotAnalogError`) are both called directly
by the new `resolve_annotation_anchor()` function, not duplicated.

### Creation UX: Annotate -> Callout -> trace click

The Annotate dropdown's SAME data-driven `.ww-split-menu-item[data-annotation-type]`
loop that already wires Text Note (section 70) wires Callout for free --
a second `<button data-annotation-type="callout">`, zero new menu event
architecture. Selecting it enters the SAME `ww.annotationPlacementType`
one-shot placement mode; Escape cancels it exactly like Text Note's own.

Callout creation is NOT routed through the existing generic
`wwAnnotationPlacementClickHandler()` (document-level click listener) --
that handler explicitly no-ops for `type === "callout"`, since only a
real Plotly `plotly_click` event (Plotly's own internal event system,
independent of native DOM `click` bubbling/capturing) can identify WHICH
trace was clicked. `wwWireAnalogPanelClick(panel)` wires a
`plotly_click` listener on every analog panel's `chartEl` (called from
`wwInitPanelPlot()`, unconditionally -- panels are always torn down and
recreated with a fresh `chartEl` on a layout-mode switch, never reused in
place, so there is no double-wiring risk unlike the digital chart's own
persistent `chartEl`, which needs its own `ww.digitalClickWired` guard
for exactly that reason); it no-ops instantly unless placement mode is
`"callout"`, so normal Plotly click/zoom/pan is completely unaffected
outside it.

### Trace identity: Grouped/Separate/Custom

Every trace already carries a stable `"sourceId::channelName"` `meta`
field (`wwBuildTrace()`, an existing Phase 4A-UAT7 convention) --
`wwWireAnalogPanelClick()` reads `eventData.points[0].data.meta` and
matches it against `panel.channels` to resolve the EXACT clicked
channel, never curveNumber alone (not guaranteed stable across
rerenders) and never "the first trace in the panel" (Grouped/Custom
panels may hold several channels; a Separate-mode lane is the
single-channel case of the exact same mechanism). Verified directly:
clicking channel B on a 2-trace Grouped panel attaches to B, not A or a
group default.

### Anchor resolution: backend/service path

`POST /api/v1/workspaces/{workspace_id}/sources/{source_id}/annotation-anchor`
(`app/api/v1/sources.py`), request `{channel_name,
approximate_elapsed_seconds}`, response `{source_id, channel_name, unit,
sample_index, elapsed_seconds, value}` (`app/schemas/annotation_anchor.py`).
Deliberately NOT an overload of `.../cursor-values` (that endpoint's own
contract -- "value at an EXISTING cursor time for N channels" -- is a
different question from "resolve and return sample IDENTITY for one
channel at one approximate time"); a small, focused endpoint reusing the
same underlying nearest-sample function is cleaner. Deliberately NOT a
persistent annotation backend -- this endpoint is called exactly ONCE per
Callout, at creation time, and answers nothing else. Frontend call site:
`wwCreateCalloutFromClick()`, which also implements section 67's stale-
response protection (captures `ww.epoch`/`currentWorkspaceId()` before
the request, discards the response if either changed by the time it
resolves) and section 66's "no partial Callout on failure" (a failed/
network-error resolution creates nothing, shows a concise error via the
existing per-panel `wwShowError()`, never an approximate fallback).

### Callout payload

`Annotation.data` for `callout`: `{text, sourceId, channelName,
sampleIndex, anchorElapsedSeconds, anchorValue, unit, boxOffset: {x, y}}`.
`Annotation.position` itself stays an unused `{x: 0, y: 0}` placeholder
for `callout` (the top-level generic shape is unchanged; Callout's real
screen position is entirely derived, never stored as a raw position).
Absolute timestamp is never stored as separate engineering authority --
it stays derived as recording start + `anchorElapsedSeconds`, the
project's own existing convention, computed on demand (Annotation List
presentation only) via the SAME `wwFormatAbsoluteElapsedTime()` A/B
cursors already use.

### Rendering: box/connector/marker architecture

One generic render pass, `wwRenderAnnotations()` (section 52 -- never a
second annotation rendering system), extended with an `isCallout` branch
alongside the existing `text_note` one. The box (`.ww-annotation--callout`,
same semantic surface family as Text Note, distinguished by a small
anchor glyph in its header) is a genuine DOM child of the SAME
`#wwAnnotationOverlayMain` Text Note boxes already live in -- native
main-workspace scroll-following for free (Phase 4E-UAT's own core fix,
fully preserved). The connector line + anchor marker render in a NEW,
lightweight SVG layer, `#wwCalloutConnectorLayer` (`position: absolute;
inset: 0; overflow: visible; pointer-events: none;`), added as a DOM
child of `#activeViewArea` immediately before the annotation overlay in
source order -- deliberately no `z-index` on it, so plain "auto"
stacking already keeps it visually behind every z-indexed `.ww-annotation`
box with zero bookkeeping. Deliberately NOT Plotly shapes (section 54):
a Plotly-shape-based connector would need a rebuild/restyle on every
drag/zoom/pan, violating the "zero Plotly calls during reprojection"
performance requirement (section 55/88) -- plain SVG attribute writes
(`x1`/`y1`/`x2`/`y2`/`cx`/`cy`) are cheap and precise instead.
`wwCalloutRectEdgePoint()` computes the connector's box-side endpoint as
the intersection of a ray from the box's own center toward the anchor
with the box's rectangular border (section 21's own "center/nearest-edge
implementation is acceptable" -- deliberately not more elaborate).

### Box dragging: anchor-relative offset, fixed anchor

`wwWireCalloutBoxDrag()` is a genuinely different drag model from Text
Note's own `wwWireAnnotationDrag()` (content-position-clamped), not a
parameterization of it -- dragging updates ONLY `data.boxOffset`
(`boxLeft/Top - anchorContent.x/y` at drag-end), computed via the SAME
`grabOffsetX/Y` technique (pointer's fixed screen-pixel offset from the
box's own corner, captured once at drag-start) Text Note already
established. The anchor's engineering identity is verified UNTOUCHED by
a drag (source/channel/sampleIndex/anchorElapsedSeconds/anchorValue all
byte-identical before/after), and the drag path is verified to issue
ZERO backend requests, ZERO `Plotly.newPlot`, ZERO `Plotly.relayout`,
and ZERO `Plotly.restyle` calls (section 79/88) -- only annotation
overlay/SVG geometry and state change.

### Zoom/Pan/Y-scaling: reprojection, not re-resolution

The anchor's projected X pixel reuses `wwCursorTimeToPixelX()`, the SAME
shared X-projection authority A/B cursors already use (one X-conversion
authority, project-wide). A NEW `wwCalloutValueToPixelY(panel, value)`
builds the equivalent Y authority per-panel, from that panel's own live
`_fullLayout.yaxis.range`/`_offset`/`_length` -- mirroring
`wwCursorTimeToPixelX()`'s own X-axis technique exactly, just per-panel
instead of shared (Y ranges are independent per panel; X viewport is
shared workspace-wide). Reprojection is triggered by reusing the EXACT
SAME trigger surface `wwUpdateCursorOverlay()` already reacts to (X
viewport change via `wwRebuildDigitalChart()`, resize, layout-mode
switch, digital-region height change, scroll via
`wwScheduleCursorOverlayRefresh()`) -- `wwRenderAnnotations()` is now
called FIRST, unconditionally, inside `wwUpdateCursorOverlay()`, so none
of that function's own cursor-specific early returns (cursor mode off,
nothing rendered yet) can skip Callout reprojection, which has nothing
to do with A/B cursor state. A NEW branch was added specifically for
Y-range changes, since A/B cursors (pure vertical lines) never needed
one: `wwWirePanelRelayout()`'s existing `plotly_relayout` listener now
also checks `eventData["yaxis.range[0]"]`/`["yaxis.autorange"]` (fired
identically whether the user drag-zooms the Y axis directly, or
`wwStepZoomY()`/`wwAutoscaleY()` call `Plotly.relayout()`
programmatically -- Plotly's own relayout event does not distinguish the
two) and calls `wwRenderAnnotations()` when either fires. Verified
directly: `anchorValue` itself never changes on a Y-zoom/autoscale; only
the marker's projected pixel Y does.

### Absolute/Elapsed: confirmed presentation-only

`anchorElapsedSeconds` is always numeric elapsed seconds (the ONE
authoritative coordinate system, matching `ww.viewport`'s own
convention, per DEC-042). Switching Absolute <-> Elapsed touches NONE of
`sourceId`/`channelName`/`sampleIndex`/`anchorElapsedSeconds`/
`anchorValue`/waveform geometry -- verified directly, `annotation.data`
byte-identical before/after. Only the Annotation List's own time
presentation (via `wwAnnotationMetaLine()`) switches between
`wwFormatAbsoluteElapsedTime()` and `wwFormatCursorDuration()`.

### Adaptive resolution: anchor bypasses display reduction

Verified directly with a broad viewport whose displayed waveform uses
`min_max_envelope` (well above `FULL_RESOLUTION_DISPLAY_THRESHOLD`): the
resolved anchor's `anchorElapsedSeconds` is confirmed to be a time value
NOT present in the reduced n=50-point displayed trace's own x-values --
the anchor genuinely comes from the full-resolution source, independent
of whatever the Plotly trace currently happens to show. This is
CORRECT, not a bug: the visual anchor position is rendered from the
engineering time/value through the panel's own axes, regardless of
which points the displayed trace array happens to contain.

### Visibility rules

- **Anchor outside the current X viewport** (section 35): hidden from
  canvas (`el.style.display = "none"` on the box, the connector/marker
  group hidden the same way), annotation stays in `ww.annotations`/the
  Annotation List, reappears the instant the viewport includes it again.
- **Anchor value outside the panel's current Y range** (section 36):
  same hidden/reappear treatment -- computed by
  `wwCalloutValueToPixelY()` returning `null` when the value's fraction
  of the current range falls outside `[0, 1]`, never pinned to the
  Y-axis boundary.
- **Anchored channel hidden** (section 37): same treatment, driven
  entirely by `ww.displayed.get(wwChannelKey(...))` returning `undefined`
  -- no separate "channel visibility" bookkeeping needed, since this Map
  is already the ONE authoritative "is this channel currently displayed,
  and on which panel" lookup every layout-mode rebuild keeps current.

### Layout-mode changes

`wwRebuildLayout()` (Grouped/Separate/Custom switch) already ended with
`wwUpdateCursorOverlay()` before this phase -- since that function now
calls `wwRenderAnnotations()` first and unconditionally, EVERY layout
switch automatically reprojects every Callout onto its channel's new
current panel, with zero additional call sites needed. Verified: no
duplicate box/connector/marker appears after Grouped -> Separate ->
Grouped.

### Annotation List

`wwAnnotationCategoryLabel()` needed no change (the existing generic
`String(annotation.type).toUpperCase()` fallback already produces
"CALLOUT" correctly). `wwAnnotationSummary()` gained a `callout` branch
(text preview, "(empty callout)" when blank, mirroring Text Note's own
"(empty note)"). A NEW `wwAnnotationMetaLine()` is the ONE dispatch point
for Callout's own extra channel/time/value line (section 42/43) -- empty
string for `text_note`, so the drawer row structure itself needed only
one small additive change (an optional `.ww-annotation-list-item-meta`
div), not a redesign. Selection/delete reuse the exact same generic
paths every other annotation already uses.

### Coexistence with Text Note

Verified directly: 2 Text Notes + 3 Callouts coexist in `ww.annotations`
(count = 5), the drawer renders all 5 rows with correct
category/preview/meta-line per type, and deleting one type never
disturbs the other.

### Workspace lifecycle / source removal

Clear Workspace (display-only) preserves Callouts, matching DEC-044's
own established semantics -- confirmed unchanged, no special-casing
needed since the generic `ww.annotations` authority doesn't distinguish
types for this path. Start New Workspace clears all annotation types via
the same existing `ww.annotations.clear()` call. Source removal is the
ONE Callout-specific lifecycle rule: `wwRemoveChannelsForSource()` now
also calls a new `wwRemoveCalloutsForSource(sourceId)`, which deletes
(not merely hides) every Callout anchored to that source -- its sample
no longer exists server-side once the source is gone, and no other
source is ever silently substituted for a same-named channel (section
57's own explicit "do not silently rebind" instruction).

### Performance

Verified directly (section 88): a box drag issues zero waveform API
calls, zero cursor-value API calls, and zero `Plotly.newPlot`/
`Plotly.relayout`/`Plotly.restyle` calls -- only annotation overlay/SVG
geometry and `data.boxOffset` state change. Anchor resolution itself
(the one real backend call) happens exactly once, at creation.

### Tests

New `phase4f_check.mjs` -- an extended jsdom harness adding per-panel
`_fullLayout.yaxis` geometry (`range`/`_offset`/`_length`, updated by a
`Plotly.relayout` mock that also fires a realistic `plotly_relayout`
`eventData` back, mirroring several existing Phase 2C-B/C test files'
own established pattern for this), a `POST .../annotation-anchor` fetch
mock backed by a deliberately finer-grained (901-sample) "full-
resolution" dataset than the existing coarse (50-point) `/waveform`
display mock, and a `triggerPlotlyClick()` helper simulating a real
Plotly `plotly_click` event. 23/23 checks passing, covering the task's
own required list (sections 71-88: anchor resolution + tie-break,
reduced-display independence, Grouped/Separate/Custom exact-trace
identity, zoom/pan/Y-zoom/Absolute-Elapsed anchor invariance, box drag
performance/offset-only semantics, out-of-viewport/hidden-channel
visibility, layout-mode reprojection with no duplicates, multi-type
coexistence, source removal, workspace lifecycle, safe text, and pointer
isolation) plus placement-mode/menu basics. `phase4e_check.mjs`'s own
"Annotate dropdown" test updated (1 item -> 2, Text Note first) to match
the new menu, its remaining 36 checks unaffected. Full frontend suite
reconfirmed at exactly the true 33-failure baseline across the same 14
pre-existing files (zero net new regressions). Backend: 19 new tests
(`test_annotation_anchor_service.py`, `test_annotation_anchor_api.py`,
reusing the established `_active_source()`/COMTRADE-fixture-upload
patterns from `test_cursor_values_service.py`/`test_cursor_values_api.py`),
412/412 passing (393 prior + 19 new), zero regressions.

### Decision

See [DECISIONS.md — DEC-045](DECISIONS.md#dec-045--callout-is-a-waveform-anchored-annotation-type-analog-only-this-phase-with-a-fixed-engineering-anchor-and-a-movable-presentation-box).

## Phase 4E-UAT2 — Free Text Notes Restricted to Main Waveform Workspace (2026-08-21)

### Scope

Owner UAT finding on the Phase 4E-UAT scroll-anchoring fix below: placing
and dragging Free Text Notes over the left Workspace Sidebar was
difficult to control, since the sidebar is its own interaction-heavy
region (independent scrolling, resizing, channel-visibility toggles).
Owner decision: remove sidebar placement support for `text_note`
entirely -- a deliberate UX simplification, not a temporary workaround.
Explicitly NOT a redesign of the generic annotation framework: `ww.
annotations`, ids, types, the Annotation List, editing, dragging,
deleting, and workspace/session persistence are all unchanged.

### Placement scope: main waveform workspace only

`text_note` may be placed, and dragged, ONLY inside `#activeViewArea` --
analog waveform panels, the digital waveform region, the shared sticky
ruler, and usable empty waveform workspace, all part of the same main
scrollable container. Excluded: the left Workspace Sidebar, the toolbar,
the Annotation List drawer, and any other page chrome.
`wwAnnotationPlacementClickHandler()`'s own toolbar-then-main containment
checks were simplified to a single "inside `#activeViewArea`" test; a
click over the sidebar is now a no-op exactly like a click over the
toolbar already was (placement mode stays active, not cancelled).

### Position model: simplified to one region

Every `Annotation` still carries a `region` field (kept generic -- see
"Future annotation types" below), but `text_note` now has exactly one
valid value, `"main"`. `position: {x, y}` is a RAW CONTENT-PIXEL offset
from `#activeViewArea`'s own scrollable content origin, unchanged from
the prior fix's own model, just with the sidebar branch removed.

### Dragging: main-only, boundary clamp, no reparenting

Existing notes remain fully draggable, but only within
`#activeViewArea`'s own scrollable content bounds.
`wwClampAnnotationContentPosition()` -- already the shared clamp for
placement, drag, and resize -- is the ENTIRE mechanism: dragging the
pointer toward (or into) the sidebar simply produces a raw content
position outside `#activeViewArea`'s own `[0, scrollWidth]`/
`[0, scrollHeight]` bounds, which the existing clamp pins back to the
region's own edge. No new boundary-detection code was needed. Confirmed
by direct test: dragging a note's pointer deep into the sidebar's own
screen-space coordinates leaves the note's stored `position.x` clamped
to `0` (the region's own left content edge) and its DOM element still a
child of `#wwAnnotationOverlayMain` -- never reparented.
`wwWireAnnotationDrag()` dropped its `liveRegion`/mid-drag-reparenting
logic entirely; the `grabOffsetX`/`grabOffsetY` technique itself (capturing
the pointer's fixed offset from the note's own corner at drag-start, so
the note doesn't jump to align its corner with the pointer on the first
move) was KEPT, since it is not region-switching logic -- just a general
drag-smoothness technique with a single remaining consumer.

### Removed complexity (not merely disabled)

Per the owner's own explicit instruction to avoid dead code for a
capability that was removed:

- `#wwAnnotationOverlaySidebar` -- the DOM element itself deleted from
  `frontend/index.html`, not emptied/hidden.
- `wwDetermineAnnotationRegion()` -- the cross-region pointer
  classification helper -- deleted (had exactly one caller, the drag
  handler's own region-switching branch, also deleted).
- The sidebar branches of `wwAnnotationRegionEl()`/`wwAnnotationOverlayEl()`
  -- both now resolve only `"main"`, returning `null` for anything else.
  Kept as functions (not inlined) since a future annotation type may add
  its own region back.
- `#workspaceSidebar`'s `position: relative` declaration -- it existed
  ONLY to be the positioning context for the now-deleted sidebar overlay;
  reverted to the base rule with no `position` set, matching pre-Phase-4E
  behavior.
- The placement-mode crosshair cursor rule's sidebar selector --
  `body.ww-annotation-placing #workspaceSidebar` removed, leaving only
  `#activeViewArea`.
- `wwRenderAnnotations()`'s dual-overlay/`seenByOverlay` bookkeeping and
  its "note might exist under the OTHER region's overlay" fallback --
  collapsed to a single overlay, single `seen` set.

### Existing notes: safe handling, no migration system

A workspace/session created under the prior region-aware fix could still
hold an annotation with `region: "sidebar"` in `ww.annotations` (frontend
in-memory/session state, no backend persistence -- see DEC-044's own
Impact section). Rather than crash (the sidebar overlay it referenced no
longer exists in the DOM) or silently disappear (never re-attached to any
overlay), `wwRenderAnnotations()` coerces `annotation.region` to `"main"`
the moment it is next rendered, then renders it normally into
`#wwAnnotationOverlayMain` at its existing raw `{x, y}` (clamped, like
every other note, to `#activeViewArea`'s own current bounds). This is
deliberately NOT a data-migration system -- it is a one-line render-time
correction sufficient for frontend session-local state, matching the
project's own existing precedent that this state never needs a database
migration path.

### Annotation model: region kept generic, dead machinery removed

Per the task's own explicit framing: `Annotation.region` remains useful
for a FUTURE annotation type that might need its own placement rule (a
callout/data-anchored type is expected to be waveform-area based but will
be designed separately, per the task's own note -- this refinement does
NOT assume every future type is main-only). What was removed is the
MACHINERY that existed solely because `text_note` used to support two
regions: cross-region classification, mid-drag reparenting, and the
dual-overlay render path. If and when a second annotation type needs a
different placement rule, that machinery (or a purpose-built version of
it) can be reintroduced scoped to that type, rather than kept dormant now
on the chance it might be needed.

### Sidebar interaction: fully unaffected

Verified directly, with Text Note placement mode left ACTIVE (not merely
inactive) during the check: channel row click/toggle, and a plain
`scrollTop` write on `#workspaceSidebar`, both behave exactly as they did
before Phase 4E existed. Sidebar resizing and Show All/Hide All are
untouched code paths (never referenced by any annotation function, before
or after this change) and were not directly exercised beyond this.

### Main scroll anchoring: preserved

The Phase 4E-UAT fix's own core mechanism -- a note is a genuine DOM
child of `#activeViewArea`, so native browser scrolling carries it with
zero manual JS scroll-offset compensation -- is completely unchanged for
the one remaining region. Re-verified: a note's `style.top` is
byte-identical before and after `#activeViewArea.scrollTop` changes, and
also byte-identical when `#workspaceSidebar.scrollTop` changes instead
(independence, now trivially true since the sidebar owns no notes at
all).

### Resize

`wwResizeAllVisiblePlots()` -> `wwRenderAnnotations()` re-clamps every
note within `#activeViewArea`'s current `scrollWidth`/`scrollHeight` on
every call, unchanged from the prior fix -- notes can never move into the
sidebar via a resize, since `wwAnnotationRegionEl("main")` is the only
region a note is ever rendered against.

### Annotation List / editing / workspace lifecycle

No redesign to any of: newest-first ordering, count badge, selection,
delete, text preview, generic future-type dispatch (Annotation List);
immediate edit-on-creation, double-click re-edit, multiline, wrapping,
safe `.textContent` rendering, Escape-cancels behavior (editing); Clear
Workspace preserves / Start New Workspace clears, Recordings ->
Waveform -> back retains annotations in the same workspace, Grouped/
Separate/Custom and Absolute/Elapsed independence (workspace lifecycle).
All re-verified by the updated test suite below.

### Tests

Rewrote `phase4e_check.mjs`'s placement/drag tests for the main-only
model. Removed tests whose only purpose was sidebar note creation,
sidebar scroll anchoring, and sidebar<->main cross-region transfer (both
directions), since that behavior is no longer a requirement. Added the
task's own required coverage (A-O): placement in main succeeds (A),
placement in sidebar does nothing and leaves placement mode active (B),
placement on the toolbar does nothing (C), a main note scrolls with main
content (D), sidebar scroll does not affect the note (E), drag stays
inside main (F), drag toward the sidebar clamps at the boundary with no
reparenting (G), resize keeps a note reachable without moving it into the
sidebar (H), edit works after scrolling (I), delete from the Annotation
List works (J), multiple notes work (K), mode switches preserve notes
(L), Start New Workspace clears (M), Clear Workspace preserves (N), and
the pointer-transparent empty overlay still allows Plotly interactions
with the sidebar overlay confirmed gone entirely (O) -- 36/36 passing.
Full frontend suite reconfirmed at exactly the true 33-failure baseline
across the same 14 pre-existing files (zero net new regressions);
`phase4d_check.mjs` (38), `phase4b_check.mjs` (44/45, unchanged
pre-existing failure), `phase4c1_check.mjs` (26), `phase4c2_check.mjs`
(24) all still pass in full. Backend: 393/393, unchanged (no backend file
touched).

### Same-day visual refinement (separately requested, folded into this record)

The note's own `background`/`border` switched from `--panel`/
`--panel-border` to new semantic `--annotation-bg`/`--annotation-border`
tokens added to `theme.css` -- a subtle warm cream surface in Light
(`#fbf3df` bg / `#e3d3a0` border), a muted warm dark surface in Dark
(`#2b2416` bg / `#4a3f26` border), deliberately short of a bright
saturated yellow/brown "sticky note" look and never reusing the A/B
cursor blue/red or any waveform trace color. Border radius, box-shadow,
min/max width, drag/edit behavior, the Annotation List, and the existing
accent-colored `.ww-annotation--selected` border/glow are all unchanged.
Verified via `getComputedStyle()` in both themes (own token, differs from
`--panel`, differs between Light and Dark).

### Decision

See [DECISIONS.md — DEC-044 addendum (refinement)](DECISIONS.md#addendum-2026-08-21-refinement--free-text-notes-restricted-to-the-main-waveform-workspace-phase-4e-uat2)
(a refinement of DEC-044's own prior addendum, not a new major decision).

## Phase 4E-UAT — Annotation Scroll Anchoring Fix (2026-08-21)

### Scope

Owner UAT finding on Phase 4E: floating Text Notes stayed visually FIXED
while `#workspaceSidebar`/`#activeViewArea` were scrolled, instead of
moving with the content they were placed beside. Scoped fix only —
Text Note remains floating/non-waveform-time/non-channel/non-Y-value-
anchored; no callout/anchoring UI, no auto-scroll-while-dragging, no
import/export, no database persistence, no new annotation type.

### Root cause (confirmed via direct DOM/CSS inspection before editing)

Position was normalized (0..1) against `#workspaceRow`'s own STABLE
bounding rect, per Phase 4E's own recorded architecture decision above.
`#workspaceSidebar` and `#activeViewArea` each scroll independently
(`overflow-y: auto`, confirmed again directly) while `#workspaceRow`
itself never scrolls — so content moved underneath a note that stayed
fixed relative to the row. This is exactly the tradeoff Phase 4E's own
"Scroll-following, a documented tradeoff" section flagged for owner UAT;
this record supersedes that tradeoff, not silently overwrites it.

### New position model: region-aware content coordinates

Every annotation now carries `region: "sidebar" | "main"` plus a RAW
CONTENT-PIXEL `position: {x, y}` measured from that region's own
scrollable content origin (`regionEl.scrollLeft`/`scrollTop`-relative),
replacing the normalized-0..1-against-`#workspaceRow` model entirely.
Raw pixels (not normalized-by-scrollHeight) were chosen because the
region's content height can change for reasons unrelated to the note
(e.g. channels shown/hidden elsewhere in the same scrollable region); a
normalized fraction would then silently remap to a different absolute
offset and the note would appear to jump on an unrelated content change
— scroll correctness was prioritized over normalized-viewport elegance,
per the task's own explicit preference.

Two region-specific overlays (`#wwAnnotationOverlaySidebar`,
`#wwAnnotationOverlayMain`) replace the single `#wwAnnotationOverlay`,
each a genuine DOM CHILD of its own region's scroll container
(`#workspaceSidebar`/`#activeViewArea`, both now `position: relative`).
The overlay's own CSS changed from `overflow: hidden` to
`overflow: visible` — this was the one open implementation detail this
fix had to resolve: `overflow: hidden` on the overlay would clip a note
positioned beyond the overlay's own (viewport-sized) box, exactly the
"off-screen until scrolled into view" case a note needs to support;
`overflow: visible` lets the note's box still count toward its region's
native CSS scrollable-overflow computation without being clipped. Result:
native browser scrolling carries a note with its region's content with
ZERO manual JS scroll-offset compensation — no scroll listener exists
for this at all, deliberately, so there is nothing to keep in sync.

This also makes toolbar exclusion STRUCTURAL instead of computed:
`#activeViewArea` and `#wwToolbar` are siblings under `#mainWorkspace`
(re-confirmed directly), so a note that is a DOM child of
`#activeViewArea` can never occupy the toolbar's screen space regardless
of the toolbar's own wrap height. `wwAnnotationToolbarRect()`,
`wwAnnotationWorkAreaRect()`, `wwClampAnnotationPixelPosition()`, and
`wwClamp01()` were removed; the toolbar-click-target check in
`wwAnnotationPlacementClickHandler()` (event.target inside `#wwToolbar`)
is unchanged and still the first, explicit guard.

### Cross-region dragging (Option C) — now genuinely native, not a shared-frame simplification

Phase 4E's own record noted true scroll-following would need "dynamically
re-parenting a note's DOM element between the two independently-scrolling
containers mid-drag" and judged that too complex to verify at the time.
This fix implements exactly that, scoped to the moment a drag crosses a
region boundary (not continuously): `wwDetermineAnnotationRegion(clientX,
clientY)` classifies the live pointer position against both regions' own
`getBoundingClientRect()` on every `pointermove`. Crossing a boundary
`appendChild`s the note's DOM element into the destination region's own
overlay, updates `annotation.region`, and immediately recomputes its
position in the new region's content-coordinate space — using a
`grabOffsetX`/`grabOffsetY` captured ONCE at drag-start via
`el.getBoundingClientRect()` (the pointer's fixed screen-pixel offset
from the note's own top-left corner), not a delta-from-drag-start model.
The delta model was rejected because it reads `el.offsetLeft`/`offsetTop`
at drag-start and adds a running delta — correct only while `offsetParent`
stays the same, which a mid-drag reparent breaks; `grabOffset` never
re-reads `offsetLeft`/`offsetTop`, so it stays correct across the
reparent. `setPointerCapture` was confirmed to keep targeting the
captured handle element correctly after `appendChild` moves it elsewhere
in the DOM, as long as it stays in the document, so the reparent never
interrupts the drag gesture. A pointer over NEITHER region (e.g. the
toolbar) freezes the note's region for that frame instead of losing it or
snapping into invalid space — the toolbar is structurally never a valid
drop target since it is not a descendant of either region overlay, so no
toolbar-specific freeze logic was needed beyond this.

### Resize: re-clamp only, never proportional rescale

`wwRenderAnnotations()` re-clamps every note within its region's CURRENT
`scrollWidth`/`scrollHeight` on every call (reusing the existing
`wwResizeAllVisiblePlots()` → `wwRenderAnnotations()` hook, unchanged),
but never proportionally rescales the STORED raw position. This is a
render-time safety net only: shrinking a region temporarily re-clamps a
note's rendered position; growing it back restores the original stored
position exactly, with no data loss — the same precedent already
established for A/B cursor state.

### Pointer isolation, lifecycle, security — unaffected

Each overlay keeps `pointer-events: none` on its own empty space and
`auto` on individual `.ww-annotation` notes — re-verified with both
overlays present (Plotly relayout handler and a sidebar row toggle both
still fire normally). Lifecycle (Clear Workspace preserves annotations,
Start New Workspace clears them), the Annotation List's own rendering/
selection/delete, and `.textContent`-only XSS-safe text rendering are all
untouched by this fix — `region` is internal state, not a new
user-facing concept, and none of these paths needed to become
region-aware.

### Tests

Reconfirmed the TRUE baseline directly against `main` before starting (33
pre-existing failures across the same 14 files, not the stale "18").
Rewrote `phase4e_check.mjs`'s position-model assumptions (region +
content-pixel, not normalized 0..1) and added new coverage: sidebar/main
scroll anchoring (a note's rendered position is provably unaffected by
its OWN region's `scrollTop`/`scrollLeft` change, with zero app-code
scroll listener involved), independent scroll (scrolling one region never
moves the other's notes), horizontal scroll (the same content-relative
model, exercised even though neither region has real horizontal overflow
in the shipped app today), cross-region drag both directions (region/DOM-
parent transfer, no coordinate jump, frozen-region when the pointer is
over neither region), resize re-clamp without proportional rescale
(including after a scroll, proving the clamp keys off content bounds, not
scroll offset), delete/edit/drawer-selection after a scroll, and both
region overlays' pointer transparency — 39/39 passing. Full frontend
suite reconfirmed at exactly the true 33-failure baseline (zero net new
regressions); `phase4d_check.mjs` (38), `phase4b_check.mjs` (44/45,
unchanged pre-existing failure), `phase4c1_check.mjs` (26),
`phase4c2_check.mjs` (24) all still pass in full. Backend: 393/393,
unchanged (no backend file touched).

### chrome-extension://invalid investigation (owner-reported alongside this fix)

Owner saw `HEAD chrome-extension://invalid/ net::ERR_FAILED` in the
browser console during UAT, with an explicit instruction not to assume
it belongs to the application. Exhaustive static-analysis search of the
entire canonical frontend: zero occurrences of the literal string
`chrome-extension` anywhere in `frontend/index.html` or any
`frontend/*.js`/`*.css`; zero `XMLHttpRequest` usage anywhere; the one
`new URL(` call site and all 9 `fetch(` call sites are backend-API-scoped
via `apiBaseUrl()`, which can only ever return an `http(s)://` string;
only 4 static same-origin `src=`/`href=` references in the whole
document, zero dynamic JS assignment; the `<head>` block has no favicon/
manifest/icon reference that could trigger an independent resource probe.
The console error's own cited line is `event.stopPropagation()` inside
the annotation-edit textarea's `keydown` handler (`wwBeginAnnotationEdit()`)
— unrelated to any network/URL code. Conclusion: Oruxa application code
is NOT responsible; this bears the well-known signature of a
browser-extension/devtools artifact. No Oruxa code was changed to
suppress it, per the task's own explicit instruction not to introduce
speculative workarounds for external browser-extension behavior. Live
incognito-vs-normal-browser reproduction could not be performed — no
browser automation capability exists in this sandboxed CLI environment;
disclosed as a limitation, with the recommendation that the owner verify
in a clean profile with extensions disabled since only they have the
browser session where it was observed.

### Decision

See [DECISIONS.md — DEC-044 addendum](DECISIONS.md#addendum-2026-08-21--region-aware-content-scroll-anchoring-phase-4e-uat)
(a refinement of DEC-044, not a new major decision — the annotation
framework itself, its record shape's non-position fields, its lifecycle,
and its Annotation List are all unchanged).

## Phase 4E — Annotation Framework + Free Text Note (2026-08-20)

### Scope

The first annotation capability: a GENERIC framework (`ww.annotations`,
typed records, a type-dispatching drawer) with exactly one supported
type implemented this phase, `text_note` — a floating, work-area-relative
note the engineer places, edits, drags, and deletes. Explicitly excluded:
callout/data-anchored notes, event/channel markers, delta/RMS/peak/
amplitude stamps, import/export, and cloud persistence (see DEC-044's own
exclusion list).

### DOM/architecture investigation before implementing

Read the existing shell structure (`#workArea` -> `#workspaceRow` ->
[`#workspaceSidebar`, `#mainWorkspace` -> [`#wwToolbar`, `#activeViewArea`]])
before writing any placement/overlay code. Two structural facts drove
every subsequent design decision:

1. **The toolbar and the sidebar occupy the SAME vertical band** (the
   toolbar is only the top strip of the `#mainWorkspace` column, sitting
   beside the sidebar's own top edge, not below it) -- a naive single
   rectangle spanning "sidebar top to activeViewArea bottom" would
   necessarily also cover the toolbar's own screen footprint. Resolved by
   checking `#wwToolbar`'s own live `getBoundingClientRect()` at
   placement-click time and during drag clamping, rather than attempting
   a CSS clip-path cutout -- the toolbar's height is not fixed (Phase
   4D's own `flex-wrap: wrap` lets it grow at narrow widths), so a static
   clip-path would need constant, error-prone recomputation; a live
   rect-containment check is simpler and always correct regardless of
   toolbar height.
2. **`#workspaceSidebar` and `#activeViewArea` are two INDEPENDENTLY
   scrolling containers** (`overflow-y: auto` on both, confirmed by
   reading their own CSS directly), while `#workspaceRow` itself never
   scrolls. This created a real tension with section 31's own "preferred"
   behavior (notes scroll with the analysis content) versus section 32's
   requirement (a note must be seamlessly draggable between the sidebar
   and the main area, implying ONE shared coordinate system). Evaluated
   and documented as a deliberate architecture decision -- see this
   record's own "Position model" section below and DEC-044's own
   "Alternatives considered" for the full reasoning; NOT a silent
   fallback.

### Placement area: Option C achieved

Option C (task section 7: sidebar + main waveform area, excluding global
nav and the toolbar itself) IS implemented, via one overlay
(`#wwAnnotationOverlay`, a child of `#workspaceRow`, spanning its full
bounding rect) combined with an explicit toolbar-exclusion check (not a
geometric cutout) in both the placement-click handler and the shared
drag/render clamp function. A note can be placed over, and dragged
between, the sidebar and the main waveform area with zero special-casing,
since both live under the same single coordinate system. This was
evaluated as clean and not architecturally costly (a single overlay +
one exclusion check, versus e.g. two separate overlay DOM trees with
their own pointer-event wiring), so Option C was implemented directly
rather than falling back to a narrower area.

### Position model: work-area-relative, not waveform/data-anchored

Every annotation's `position` is `{x, y}` normalized (0..1) against
`#workspaceRow`'s own bounding rect at read/write time -- resilient to
sidebar-resize/window-resize/laptop-width changes (section 17), and
NEVER derived from `ww.viewport`, a Plotly trace, or any panel geometry
(section 6 -- this is the floating/non-data-anchored requirement).
`wwClampAnnotationPixelPosition()` is the ONE shared clamp used by
placement, live drag, and render/resize repositioning -- it keeps a
note's top-left corner inside the work area AND deflects it below the
toolbar's own rectangle if a drag would otherwise push it underneath.

**Scroll-following, a documented tradeoff**: the task's own "preferred"
behavior (section 31) is for notes to scroll with `#workspaceSidebar`'s/
`#activeViewArea`'s own internal content. Implementing this correctly
while also satisfying section 32 (seamless cross-region dragging with
one coordinate system) was evaluated to require either (a) dynamically
re-parenting a note's DOM element between the two independently-
scrolling containers mid-drag, or (b) manually tracking both containers'
own `scrollTop` and recomputing note position on every scroll event,
duplicating native scroll mechanics for two containers independently.
Both add real complexity this sandboxed environment cannot verify
against a live browser. Chose instead: notes anchor to `#workspaceRow`'s
own STABLE, never-scrolling viewport frame -- one simple, always-correct
coordinate system, full Option C placement/dragging, but a note does NOT
visually scroll away when the user scrolls deep into a tall waveform
stack or a long channel list. Recorded as a deliberate, disclosed
architecture decision (DEC-044), not a silent shortcut -- flagged for
owner UAT specifically (see this record's own Owner UAT list) and
revisitable in a future phase if true scroll-following is wanted badly
enough to justify the added complexity.

### Text Note: creation, editing, wrapping, dragging

`Annotate -> Text Note` enters a one-shot placement mode
(`ww.annotationPlacementType`): a document-level CAPTURE-phase click
listener validates the click is inside `#workspaceSidebar` or
`#activeViewArea` and NOT inside `#wwToolbar` before creating a note and
exiting placement mode automatically (section 10/11) -- Escape cancels
via a parallel capture-phase keydown listener, both removed the instant
placement mode ends so they never coexist with normal interaction. A
newly-placed note enters edit mode immediately (section 12) via
`wwBeginAnnotationEdit()`, swapping the read-only body `<div>` for a
`<textarea>` in place. Single click selects (bring-to-front via a
monotonic `zIndex` counter, section 21); double-click on the body enters
edit; blur commits; Escape while editing reverts to the pre-edit text
(`wwEndAnnotationEdit(id, false)`) -- Enter is never treated as save
(textarea's own native newline behavior is left alone, section 14).
Dragging is wired on the header (always) and the body (only while NOT
editing) via `wwWireAnnotationDrag()`, mirroring this project's own
established pointer-capture drag pattern (`wwWireResizeHandle()`); the
active `<textarea>` itself never initiates a drag (`stopPropagation()` on
its own `pointerdown`). Text wraps via `white-space: pre-wrap` +
`overflow-wrap: break-word` inside a `min-width: 160px` / `max-width:
320px` note, height grows with content, no giant shadow, no bright
palette (section 13).

### Annotation List drawer

A right-side, `position: fixed` OVERLAY panel (never consumes/reflows
`#workspaceRow`'s own width -- chosen specifically so opening/closing it
can never distort normalized annotation positions, section 30's own
explicit concern; no existing right-drawer precedent existed in this
codebase to reuse, so this is a new, minimal one using the same theme
tokens as every other panel). Body content is entirely DERIVED from
`ww.annotations` via `wwRenderAnnotationList()` -- generic across
annotation types (`wwAnnotationCategoryLabel()`/`wwAnnotationSummary()`
dispatch on `type`, never hard-wired to `text_note`'s own shape), sorted
newest-first (a deliberate, documented ordering choice, section 68).
Each row: category label ("NOTE"), text preview (line-clamped), and a
delete button (trash icon -- appropriate here, since this genuinely
deletes the annotation, unlike Clear Workspace's own eraser icon).
Clicking a row selects the matching note (border highlight on both the
note and the row, from the SAME `ww.annotationSelectedId`) and calls the
note's own `scrollIntoView({block: "nearest"})` if it exists (standard
DOM API, correctly handles whichever scrolling ancestor currently
contains it). Delete is immediate, no confirmation dialog (section 28 --
a small, individually-reversible-by-recreation action; reserved for a
possible future "Clear All," not implemented).

### Pointer isolation

`.ww-annotation-overlay { pointer-events: none; }` with `.ww-annotation {
pointer-events: auto; }` -- the standard, well-established CSS technique
for "empty overlay space passes clicks through, but specific children
remain interactive." Verified directly: a Plotly panel's own
`plotly_relayout` handler still fires correctly with the overlay present
and a note elsewhere on screen; a channel sidebar row's own toggle click
still works normally.

### Mode/navigation persistence

Annotation state is untouched by `wwRebuildLayout()` (Grouped/Separate/
Custom), `wwSetTimeMode()` (Absolute/Elapsed), or any X/Y step-zoom/pan/
Reset-Time-View path -- confirmed both by code inspection (none of those
functions read/write `ww.annotations`) and by direct test (position
JSON-stable across a full Grouped -> Separate -> Custom -> Grouped cycle,
an Absolute <-> Elapsed round-trip, and a zoom-then-pan sequence).
Recordings -> Waveform -> Recordings -> Waveform navigation within the
same workspace was not separately re-tested with a full page-navigation
harness this phase (out of proportion to add for this task), but is
architecturally guaranteed by construction: `ww.annotations` lives on the
same persistent `ww` object every other session-scoped state
(`ww.customGroups`/`ww.panelHeights`/`ww.channelColors`) already survives
that exact navigation with, and Phase 4E adds no annotation-clearing
call anywhere in the Waveform<->Recordings page-switch path.

### Workspace lifecycle: Clear Workspace vs. Start New Workspace

Inspected `wwClearWorkspace(options)` directly rather than assuming:
confirmed it is ALREADY a single function serving both actions, and that
the plain "Clear workspace" toolbar button (no `resetSourceBounds`)
already preserves `ww.measurementCursors` (cursor time/state) via the
SAME `if (options.resetSourceBounds)` branch annotations were added to --
an existing, direct precedent for "survives display-clear, cleared only
on a genuinely new workspace." Annotations follow that exact same
branch: PRESERVED by the plain Clear Workspace button (display-only,
same source/session context), CLEARED only when `resetSourceBounds` is
true (Start New Workspace, which rotates `WORKSPACE_STORAGE_KEY` to a new
UUID before calling this function -- a genuinely new `workspace_id`).

### Security

Annotation text is rendered via `.textContent` assignment exclusively --
never `.innerHTML` with user text interpolated. Verified directly:
entering `<script>window.__xssFired = true;</script><b>hello</b>` as note
text renders as inert literal text (no `<script>`/`<b>` element is ever
parsed into the DOM, no script execution occurs) in both the floating
note's own body AND the drawer's preview.

### Future extensibility

A future `callout_note` (or any other type) needs: (1) one more
`.ww-split-menu-item` in the Annotate dropdown with its own
`data-annotation-type`; (2) a branch in
`wwAnnotationCategoryLabel()`/`wwAnnotationSummary()` for its own
category/preview text; (3) its own `data` payload shape (e.g.
`{anchorTime, anchorChannel, text}`) stored under the SAME generic
`Annotation.data` field, never a parallel record type; (4) its own note-
body renderer if its DOM differs from `text_note`'s. No change to
`ww.annotations`'s own shape, `wwCreateAnnotation()`/`wwUpdateAnnotation()`/
`wwDeleteAnnotation()`, the drawer's list-rendering loop, or the overlay/
pointer-isolation architecture would be needed -- confirming the
framework goal (section 3) was met, not just the one type.

### Tests

Determined the TRUE current baseline directly against `main` (not the
stale "18" figure retired during the Phase 4D session) before making any
change: unchanged from Phase 4D's own verified 33 failures across 14
pre-existing files. New `phase4e_check.mjs` (28 checks) covering: Annotate
dropdown contents + placement-mode entry/exit + Escape cancel + toolbar-
click/outside-click rejection + sidebar placement (Option C); multiple
notes with unique ids/independent state/drawer membership; edit (canvas/
state/drawer sync, Escape-reverts, Enter-is-not-save); drag (normalized
position update, work-area + toolbar-avoidance clamping); resize
(normalized position preserved, pixel position recalculated); delete
(state/canvas/drawer/count, other notes untouched); mode persistence
(layout/Absolute-Elapsed/zoom-pan); Clear Workspace preserves vs. Start
New Workspace clears; pointer isolation (Plotly relayout handler and
sidebar row toggle both still fire correctly with the overlay present);
XSS-safe text rendering; and the drawer's own open/close, stable
newest-first ordering with no duplicate rows on rerender, and row-click
selection. Full frontend regression suite reconfirmed at exactly the
true 33-failure baseline (zero net regressions); `phase4b_check.mjs` (44/45,
unchanged pre-existing), `phase4c1_check.mjs` (26), `phase4c2_check.mjs`
(24), and `phase4d_check.mjs` (38) all still pass in full. Backend:
393/393, unchanged (no backend file touched this phase).

### Decision

Recorded as a new decision,
[DEC-044](DECISIONS.md#dec-044--generic-annotation-framework-first-type-is-a-workspace-scoped-work-area-relative-free-text-note)
-- the generic annotation framework and its first type, `text_note`,
extending DEC-021/DEC-039 by reference (workspace-level navigation, one
overlay not per-panel state) without altering either.

---

## Phase 4D — Precision Step Zoom + Icon Toolbar Refinement (2026-08-20)

### Scope

Two related, owner-approved refinements to the waveform toolbar, riding
together since both touch the same markup: (1) precise stepped Zoom
In/Zoom Out controls for X and Y, without adding four permanent X+/X-/
Y+/Y- buttons; (2) converting the toolbar's major text-labeled controls
to a compact, professional, SVG icon-primary language. Engineering
semantics of every EXISTING control (drag-based Zoom/Pan, Reset Time
View, Autoscale Y, Absolute/Elapsed, A/B cursors, Grouped/Separate/
Custom, Clear Workspace) are explicitly unchanged -- this phase adds
precision and appearance, never redesigns behavior.

### Pre-work investigation: two intervening sessions had already landed

Before touching anything, per the mandatory startup sequence, discovered
(via `git log`) that two commits had landed on `main` since the last
Phase 4C2 session, neither authored in this session: `cfdfb3a`
("Improve waveform zoom display resolution", DEC-041 -- the 10,000-sample
full-resolution display threshold + pixel-adaptive point_budget) and
`915111c` ("fix: preserve sub-ms waveform precision in absolute time",
DEC-042 -- Absolute/Elapsed now share one numeric elapsed Plotly X
coordinate; `wwElapsedToPlotlyX()`/`wwPlotlyXToElapsed()` are now identity
functions, `wwSetTimeMode()` no longer rewrites trace geometry). Both were
read in full (DECISIONS.md DEC-041/DEC-042, their own MIGRATION_PLAN.md
records) before any Phase 4D code was written, since the X step-zoom
work explicitly needed to reuse -- not reinvent or accidentally bypass --
the CURRENT adaptive-resolution fetch path and numeric-coordinate model,
not the pre-DEC-041/042 one this agent last worked against.

**Also discovered while establishing the frontend regression baseline**:
the previously-tracked "18-failure baseline" (established across Phase
4A/4B/4C sessions) was stale -- the two intervening commits' own
architecture changes (numeric-coordinate Plotly axes, adaptive resolution)
broke several OLDER verification scripts' assumptions (date-typed axis
checks, date-string X-coordinate checks) that predate DEC-041/DEC-042.
Re-measured directly against current `main` before writing any Phase 4D
code: the TRUE current baseline is **33 pre-existing failures across 14
files** (`phase2cb1/cb2/cb3/cb3a_check.mjs`, `phase2cc2/cc3/cc4/cc4a_check.mjs`,
`phase3a_check.mjs`, `phase3auat1/auat3_check.mjs`, `phase3b_check.mjs`,
`phase3buat3/buat4_check.mjs`, `phase4b_check.mjs`) -- none caused by this
phase, all pre-existing artifacts of the DEC-041/DEC-042 session's own
architecture changes to older, unrelated test files. This is the baseline
verified against below, not the stale "18" figure -- see this record's
own Tests section for the full accounting, including the two
`phase4b_check.mjs`/mock-related fixes applied along the way (a silently
crash-truncated file, unrelated to Phase 4D, fixed so the suite genuinely
executes to completion) and the exactly two test files whose STRICT
assertions became stale specifically because of Phase 4D's own new,
intended behavior (updated, not treated as regressions).

### Step zoom architecture: one split button per action, not four buttons

Two new controls, Zoom In and Zoom Out, each a compact split button: a
main icon that performs whichever axis (X or Y) was last chosen for that
specific action, plus a small dropdown trigger opening a 2-item axis menu
("Horizontal (X)" / "Vertical (Y)"). Choosing an axis from the dropdown
both remembers the preference AND performs that exact step immediately
(the user just explicitly asked for it -- treating the click as
selection-only would be the surprising outcome, not the safe one);
every subsequent main-icon click then repeats that same axis with zero
further dropdown interaction. `ww.zoomStepAxis = { in: "x", out: "x" }`
remembers the two actions' preferences SEPARATELY (the owner task's own
primary recommendation over one shared axis) -- defaulting both to X
(precise time-window inspection is the most common case).

### X zoom: workspace-global, ~20% step, workspace-bounds clamp

`wwStepZoomX(direction)`: reads the CURRENT `ww.viewport`, computes
`newSpan = span * 0.8` (Zoom In) or `span * 1.25` (Zoom Out) around the
UNCHANGED midpoint, then calls the exact same `wwApplyAndFetchViewport()`
every other X-viewport-changing path already uses (drag-zoom, pan, Reset
Time View) -- this is what guarantees every analog panel, the digital
region, and the shared sticky ruler move together, and that DEC-041's
adaptive-resolution range fetch genuinely re-runs for the new range
rather than a bare Plotly relayout of stale trace data. Zoom Out is
bounded by a NEW dedicated clamp, `wwClampZoomWindowToWorkspace()` --
deliberately separate from the pre-existing `wwClampRangeToWorkspace()`
(unchanged, still used by drag-zoom/pan broadcast) because that helper's
independent-endpoint clamping would asymmetrically truncate a Zoom-Out
step's SPAN whenever the window sits near one edge of the workspace; the
new clamp instead SHIFTS the window to preserve the exact requested span
whenever it still fits within `ww.workspaceBounds`, falling back to the
full workspace bounds only once the requested span can no longer fit at
all. At full workspace range, Zoom Out is a genuine no-op (no refetch)
and the button reads `disabled` (only when the remembered axis for "out"
is X; a Y preference has no comparable hard limit). A `WW_MIN_X_SPAN_SECONDS
= 1e-6` floor exists purely to stop pathological zero/negative-span
underflow after an extreme number of clicks -- not a practical inspection
limit (real COMTRADE sample spacing is essentially never below 1
microsecond).

### Y zoom: active-panel-local only

`wwStepZoomY(direction)` operates on exactly ONE panel -- whichever
`wwActivePanel()` currently resolves to -- never every panel globally
(owner's explicit rationale: distinct engineering panels need independent
vertical inspection). Reads the panel's CURRENTLY RESOLVED Y range from
Plotly's own `_fullLayout.yaxis.range` (not `layout.yaxis.range`, which
can be `undefined` while still auto-ranging -- the same `_fullLayout`
precedent `wwPanelPlotWidth()` already established for reading Plotly's
resolved geometry), applies the identical 0.8/1.25 stepping math around
the current Y midpoint, then writes an explicit `yaxis.range` back via
`Plotly.relayout()` with `yaxis.autorange: false` -- taking the panel out
of autorange, exactly "manual range as appropriate." A `WW_MIN_Y_SPAN =
1e-9` epsilon floor prevents span collapse the same way the X floor does.

### Active panel: click (not hover) establishes authority

New state `ww.activePanelGroupKey` -- stores the active panel's STABLE
`groupKey` (the same key namespace `ww.panelHeights`/`ww.customGroups`
already use), never a raw panel object reference, because
`wwRebuildLayout()` fully discards and recreates every panel object on
every Grouped/Separate/Custom switch (pre-existing, unchanged behavior).
`wwActivePanel()` is the ONE resolver every call site reads through --
self-healing by design: if the remembered key no longer matches any
CURRENT panel, it falls back to the first/primary panel and adopts that
panel's key as the new active one, so the fallback itself becomes sticky
rather than re-triggering on every subsequent read. This means a layout
switch, or the active panel's last channel being removed, can never leave
Y step zoom targeting a destroyed/purged Plotly instance. Click
authority is wired on the panel HEADER specifically (`.ww-panel-header`,
now `tabindex="0" role="button"` with Enter/Space keyboard support) --
not the whole panel card -- so it never intercepts a Plotly box-zoom/pan
drag gesture, a legend-chip click, or the resize handle's own
pointer-capture drag. Visual feedback is deliberately understated: one
additive CSS class, `.ww-panel--active`, tinting only the panel's own
border (`border-color: var(--accent-dim)`) -- no background fill, no
shadow, no large selection state.

### Icon toolbar: reuses the existing `.shell-nav-icon` visual language

Every major control (Box Zoom, Pan, Zoom In/Out, Absolute Time, Elapsed
Time, Reset Time View, Autoscale Y, A/B Time Cursors, Grouped/Separate/
Custom Layout, Clear Workspace) is now an inline SVG icon with a
`title`/`aria-label` tooltip pair, instead of a text label. Per the
task's own explicit "inspect for an existing icon pattern first"
instruction, found and reused `#mainSidebarMenu`'s `.shell-nav-icon`
convention verbatim: `viewBox="0 0 18 18"`, `stroke="currentColor"`,
`fill="none"`, `stroke-width: 1.5`, round linecap/linejoin -- so the
app's navigation rail and waveform toolbar now read as ONE icon family,
not two visual languages, and no external icon library was introduced.
Concepts used: Box Zoom/Zoom In/Zoom Out share one magnifier-glass base
(matching the existing Tools nav icon's own magnifier), with a `+`/`-`
added inside the lens for the two step actions; Pan is a minimal open-hand
glyph; Absolute Time is a clock face, Elapsed Time a stopwatch (same
circle-body family, distinguished by the stopwatch's crown stub), rendered
as a segmented `.theme-toggle` pair so they read as mutually-exclusive
modes, not independent commands; Reset Time View and Autoscale Y are a
matched horizontal/vertical "axis with outward arrows" pair (fit-to-extent,
never a generic circular refresh icon), visually distinct from each other
by axis orientation; A/B Time Cursors is two vertical lines with small
solid `<text>` "A"/"B" glyphs INSIDE the SVG (the one deliberate exception
to "no text," per the task's own explicit allowance, readable at 18px
since they use `fill="currentColor"` rather than an outlined stroke);
Grouped/Separate/Custom are a filled-panel-with-two-traces / three-stacked-
lanes / asymmetric-grid-with-adjustment-tick trio; Clear Workspace is an
eraser wedge (deliberately not a trash icon -- clears the DISPLAYED
workspace, never deletes the imported source recording). The X/Y axis
menu items reuse the same horizontal/vertical arrow shapes as Reset Time
View/Autoscale Y (SVG, not Unicode arrows, matching the rest of the
toolbar). Toolbar controls are grouped into Navigation / Zoom step / Time
/ View / Measurement / Layout / Workspace clusters via thin
`.ww-toolbar-sep` hairline separators, instead of one undifferentiated
row of icons.

### Accessibility

Every icon-only control keeps both a non-empty `title` and `aria-label`
(never forces memorizing an icon). The split-button dropdowns use
`role="menu"`/`role="menuitemradio"` with `aria-checked` reflecting the
current axis selection; keyboard support: Tab reaches the main action
then the trigger (natural DOM order, no tabindex tricks needed), Enter/
Space activates either (native `<button>` behavior), opening a menu moves
focus to its first item so Tab can reach both X/Y items directly, Escape
closes the menu and returns focus to the trigger, and a `focusout`
listener closes the menu if keyboard focus leaves the split button
entirely. Mouse users additionally get click-outside-to-close and
"opening one split button's menu closes the other's."

### Adaptive resolution (DEC-041) -- confirmed genuinely reused, not bypassed

X step zoom's only contribution is the new `[start, end]` math; the
actual fetch/render lifecycle is 100% the pre-existing
`wwApplyAndFetchViewport()` -> `wwRefetchAllChannels()` ->
`wwLoadChannelRange()` -> `wwFetchChannelRange()` chain, meaning
DEC-041's own threshold/adaptive-point-budget logic
(`FULL_RESOLUTION_DISPLAY_THRESHOLD`/`WW_POINT_BUDGET_MIN/MAX/PER_PIXEL`)
applies automatically and unmodified. Verified directly: zooming into a
sub-10,000-sample interval switches a channel's own `representation` to
`full_resolution`; a broad overview range still returns
`min_max_envelope`, capped by the plot-width-adaptive `point_budget`
DEC-041 already established.

### A/B cursors

X step zoom never touches `ww.measurementCursors.a.time`/`.b.time` --
only the shared viewport moves, so cursor engineering time (and
therefore Cur A/B analog values and digital A/B states, both keyed on
cursor TIME, not pixel position) is provably unchanged; only the
cursor's on-screen pixel projection updates, via the SAME
`wwUpdateCursorOverlay()` hook `wwApplyAndFetchViewport()` already calls
for every other viewport change.

### Layout modes

Grouped/Separate/Custom all resolve `wwActivePanel()` the same generic
way -- "whichever panel object currently exists and was last clicked" --
since a Grouped "Voltage" panel, a Separate "src::VA" lane, and a Custom
group panel are all just `ww.panels` entries with their own stable
`groupKey`; no per-mode special-casing was needed. Verified a full
Grouped -> Separate -> Custom -> Grouped cycle never leaves the active
panel pointing at a purged Plotly instance, and that a Y step zoom
immediately after a layout switch operates on a real, currently-rendered
panel without throwing.

### Tests

New `phase4d_check.mjs` (38 checks): X step math + workspace clamp +
edge-shift-preserves-span behavior + 5-in/5-out round-trip + min-span
floor; X global synchronization (panels + A/B cursor time unchanged);
adaptive-resolution representation switching verified against a
purpose-built 10 kHz-equivalent source fixture (a 1s range = exactly the
10,000-sample threshold, a 5s range well past it); active-panel
click/keyboard selection + visual class; Y step zoom isolation between
two panels, active-panel redirection, min-span floor; layout-mode
active-panel remapping; Autoscale Y still hitting every panel (not just
the active one); icon-toolbar text removal (with the A/B cursor icon's
own in-SVG glyphs as the one documented exception) + title/aria-label
presence + shared viewBox family; existing mode-state `aria-pressed`
preservation for Box Zoom/Pan, Absolute/Elapsed, Grouped/Separate/Custom,
A/B cursors; the full split-button dropdown lifecycle (select-and-act,
remembered-per-action axis, checkmark sync, Escape, click-outside,
mutual-exclusivity between the two split buttons).

Two PRE-EXISTING tests needed updating because Phase 4D's own intended
changes made their strict assertions stale (not regressions -- confirmed
via direct `git stash` comparison against the unmodified `main` baseline
both before and after each fix): `phase2cc1_check.mjs`'s "Custom button"
check asserted literal `textContent === "Custom"` (now an icon -- updated
to check `title`/`aria-label` instead); `phase2cb3a_check.mjs`'s DOM
check asserted literal `className === "ww-panel"` (the first panel now
also carries the additive `ww-panel--active` class by default -- updated
to `classList.contains("ww-panel")`, the robust form of the same check).
Also fixed, while establishing the true baseline: `phase4b_check.mjs` had
been silently crash-truncating after only 2 checks since the earlier
Phase 4C1 session (an unguarded `/cursor-values` mock gap, unrelated to
Phase 4D) -- patched with a minimal non-crashing mock so its own 45
Phase-4B checks genuinely execute again (44 pass; the one remaining
failure, an Absolute-mode cursor-readout format assertion, is a
DEC-042-era pre-existing mismatch, confirmed via the same stash
comparison to predate this phase entirely -- left untouched as out of
scope).

Full frontend regression suite reconfirmed at exactly the TRUE 33-failure
baseline (same 14 files, same per-file counts, verified both before and
after every fix above via direct `git stash` comparison against
unmodified `main`) -- zero net regressions from Phase 4D. Phase 4C1's own
`phase4c1_check.mjs` (26 checks) and Phase 4C2's own `phase4c2_check.mjs`
(24 checks) both still pass in full, confirming section 45's "do not
change engineering behavior of existing tools" for the measurement
system specifically. Backend: 393/393 passing, unchanged (no backend file
touched this phase).

### Decision

Recorded as a new decision,
[DEC-043](DECISIONS.md#dec-043--precision-step-zoom-x-step-is-workspace-global-y-step-is-active-panel-local-waveform-toolbar-is-icon-primary)
-- establishes the X-global/Y-active-panel-local step-zoom split and the
icon-first toolbar language as durable architecture, extending DEC-021/
DEC-039/DEC-041/DEC-042 by reference without altering any of them.

---

## Waveform Time-Axis Sub-ms Precision (2026-08-20)

### Scope

Implements the owner-approved follow-up from the Absolute-Time waveform
precision investigation. The fix is frontend-only and changes the Absolute
time-axis representation from "date strings as Plotly X coordinates" to
"numeric elapsed Plotly X coordinates with Absolute labels."

Recorded as [DEC-042](DECISIONS.md#dec-042--absolute-and-elapsed-waveform-modes-share-numeric-elapsed-plotly-x-coordinates).

### Problem proven

Adaptive resolution was already correct after DEC-041. A 5 kHz source zoomed
to 14 ms returns 71 original samples and a 15 ms range returns 76 original
samples, both as `representation="full_resolution"`. Backend responses are
mode-agnostic because the waveform API always receives elapsed `start_time` and
`end_time`.

The remaining owner-observed stair-step in Absolute mode was caused by the old
frontend conversion:

```text
elapsed seconds -> JavaScript Date / millisecond date string -> Plotly date X
```

At 5 kHz, sample spacing is 0.2 ms, so five samples can collapse into each
1 ms Absolute X coordinate even though their Y values remain distinct.

### Implementation

`frontend/index.html` now keeps Plotly waveform coordinates numeric and elapsed
in both modes:

- `wwElapsedToPlotlyX()` returns the elapsed value unchanged.
- `wwPlotlyXToElapsed()` returns `Number(x)`.
- Analog trace `x` arrays are the backend `body.time[]` elapsed floats in both
  Absolute and Elapsed modes.
- `wwSetTimeMode()` updates hover/customdata and axis presentation only; it
  does not rewrite trace X/Y arrays and does not refetch waveforms.
- Absolute hover text uses per-point `customdata` formatted as
  `recording_start + elapsed`.
- Absolute tick labels are generated from numeric elapsed tick positions.
- The sticky ruler no longer rescales its coordinate domain or switches to a
  date axis; it uses elapsed seconds in both modes and changes tick text/title
  only.
- Digital transition positions remain elapsed numeric values. Absolute mode
  does not change digital geometry, state-at-cursor, or vertical alignment.
- A/B cursor state and projection remain elapsed floating-point seconds; only
  the Absolute readout formatter changes.

### Precision behavior

Absolute presentation uses viewport-aware fractional precision:

- broad ranges: whole seconds where sufficient;
- sub-2 s ranges: milliseconds;
- sub-100 ms ranges: four fractional second digits, enough to distinguish
  0.2 ms samples;
- sub-10 ms ranges: five fractional second digits.

For the 5 kHz regression case, a 15 ms range now preserves:

```text
76 source points -> 76 unique Elapsed Plotly X values
76 source points -> 76 unique Absolute Plotly X values
```

Absolute and Elapsed waveform geometry are therefore sample-for-sample
identical; only tick labels, hover labels, and cursor time text differ.

### Verification

Focused regression run:

```bash
pytest backend/tests/test_waveform_service.py backend/tests/test_waveform_reduction.py backend/tests/test_cursor_values_service.py backend/tests/test_cursor_values_api.py backend/tests/test_frontend_source_bounds.py backend/tests/test_frontend_waveform_adaptive_resolution.py backend/tests/test_frontend_absolute_time_precision.py
```

Result: 106 passed.

Permanent coverage added in
`backend/tests/test_frontend_absolute_time_precision.py` for identity
coordinate conversion, no date-axis/date-string Plotly coordinates, no trace
geometry rewrite on mode switch, 5 kHz 76/76 unique-X preservation,
sub-millisecond Absolute label precision tiers, and sticky-ruler numeric-domain
behavior.

---

## Waveform Adaptive Resolution (2026-08-20)

### Scope

Implements the owner-approved follow-up from the waveform zoom-resolution
investigation: analog display reduction remains allowed for broad overviews,
but manageable zoomed event intervals now return the actual source samples
for display.

### Approved rule

Recorded as [DEC-041](DECISIONS.md#dec-041--waveform-reduction-is-an-overview-rendering-optimization-with-a-10000-sample-full-resolution-display-threshold):

> Waveform reduction is an overview rendering optimization only. For requested
> ranges containing `<= 10,000` original samples per channel, Oruxa Powerwave
> returns the complete original sample sequence for display.

### Backend implementation

`app.services.waveform_service.extract_waveform_range()` still clips the
authoritative `active.record.waveform_data` by the requested elapsed
`start_time`/`end_time` first. It now compares the exact clipped sample count
against the named `FULL_RESOLUTION_DISPLAY_THRESHOLD = 10_000`.

- `original_sample_count == 0` or `<= 10,000`: return the clipped arrays
  unchanged with `representation="full_resolution"`.
- `original_sample_count > 10,000`: return the existing peak-preserving
  `min_max_envelope` display representation.
- For above-threshold ranges, the effective reduction budget is capped by the
  same threshold so a large pixel budget cannot accidentally make an overview
  range a full-sample transfer again.

The backend authority, COMTRADE parsing, source bounds, cursor values, and
digital measurement paths were not changed.

### Frontend implementation

`frontend/index.html` replaces the old fixed `WW_POINT_BUDGET = 4000` with
named adaptive constants:

- `WW_POINT_BUDGET_MIN = 4000`
- `WW_POINT_BUDGET_MAX = 20000`
- `WW_POINT_BUDGET_PER_PIXEL = 4`

Each analog channel fetch now sends a panel-specific `point_budget` calculated
from the actual Plotly plotting-domain width (`_fullLayout.xaxis._length`)
when available, with a chart-element-width-minus-panel-margins fallback for a
newly-created panel before Plotly has painted. Browser/window width is not
used. Width changes alone do not trigger waveform requests; the next genuine
channel load or zoom/pan request uses the current budget.

### Expected 5 kHz behavior

At 5 kHz with a 7.0 s inclusive synthetic source:

- 7.0 s / 35,001 samples: reduced overview.
- 3.0 s / 15,001 samples: reduced.
- 1.0 s / 5,001 samples: full resolution, sample-for-sample.
- 100 ms / 501 samples: full resolution, sample-for-sample.
- 20 ms / 101 samples: full resolution.
- 5 ms / 26 samples: full resolution.

### Verification

Focused regression run:

```bash
pytest backend/tests/test_waveform_service.py backend/tests/test_waveform_reduction.py backend/tests/test_cursor_values_service.py backend/tests/test_frontend_source_bounds.py backend/tests/test_frontend_waveform_adaptive_resolution.py
```

Result: 82 passed.

Permanent coverage added for the 5 kHz examples, full-resolution
sample-for-sample equality, threshold-capped overview reduction, pixel-aware
frontend budget constants/clamping, use of Plotly plot-domain width, zoom
elapsed-range request semantics, and existing Cur A/B full-resolution
independence.

---

## Phase 4C2 — Digital A/B Cursor State (2026-08-20)

### Scope

Extends Phase 4C1's A/B cursor channel values to digital channels: every
displayed digital channel now shows its recorded state (0/1) at Cursor A
and Cursor B, as compact inline "A:0 B:1" badges appended to the existing
Channel cell -- deliberately NOT a full-width Cur A/Cur B table column
like analog's (owner's explicit instruction). Scope exclusions:
transition count between A/B, duration-HIGH between A/B, a
sequence-of-events table, normal/abnormal interpretation, RMS, angle,
delta angle, calculated analog measurements, cross-source
synchronization.

### Investigation: how digital channels are actually stored

Before implementing, inspected `app.providers.comtrade._build_dataframe`
and `extract_digital_waveform` directly (per the task's own explicit
instruction to check this before choosing a sample-vs-transition
lookup strategy). Confirmed: digital channels live in the SAME dense,
per-sample `waveform_data` DataFrame as analog channels, sharing the
identical `"time"` column -- `int8` values (0/1), one column per digital
channel. `extract_digital_waveform`'s own sparse transition list
(`DigitalTransition`) is DERIVED from this dense array via `np.diff` at
request time, purely for compact wire-transfer of the full-record
digital waveform to the frontend chart -- it is a display-oriented
representation of the same underlying full-resolution data, not a second
source of truth. This means digital cursor state can reuse the EXACT
SAME `_nearest_sample_index()` nearest-actual-sample search Phase 4C1
already built for analog, with zero need for a second
transition-interval-search algorithm.

### Exact-transition-timestamp rule

A cursor landing exactly ON a transition's own timestamp reads the NEW
state beginning at that timestamp (e.g. transition 0 -> 1 at t=0.500,
cursor=0.500 -> reads 1). This falls out for free from the nearest-sample
read: the recorded sample AT a transition's own timestamp already holds
the new state by construction (the transition is defined as "the first
sample where the value differs from the previous sample" -- see
`_extract_digital_channels`/`_build_dataframe`), so no special-casing was
needed in `extract_cursor_values()` beyond the existing nearest-sample
search. Verified with dedicated tests using a 0.01s-step dense fixture
(0 until 0.5, 1 from 0.5 until 1.0, 0 from 1.0 onward) against the task's
own worked examples: 0.49->0, 0.50->1, 0.75->1, 1.00->0, 1.20->0.

### Backend (`backend/`)

- `app/services/waveform_service.py`: `extract_cursor_values()` extended
  to accept `digital_channel_names` alongside the renamed
  `analog_channel_names` (was `channel_names` -- clean rename for
  symmetry/type clarity, internal-only API, no back-compat shim needed
  per this project's own convention), and to resolve digital state
  from the SAME two already-computed nearest-sample indices used for
  analog -- one source's request costs exactly one pair of index lookups
  regardless of how many channels of either kind are requested. New
  `DigitalChannelCursorState` dataclass (`channel_name`, `a_state`,
  `b_state` -- plain `int | None`, no `unit` field, deliberately distinct
  shape from `ChannelCursorValues`).
- `app/schemas/cursor_values.py`: `CursorValuesRequest` gained
  `digital_channel_names: list[str] = []`; `CursorValuesOut` gained
  `digital_channels: list[DigitalChannelCursorStateOut]`.
- `app/api/v1/sources.py`: same route (`POST .../cursor-values`), updated
  docstring; no new endpoint (Option A from the task's own "extend
  existing endpoint vs. dedicated endpoint" choice -- chosen because both
  channel kinds share the identical time-lookup mechanism, so a second
  endpoint would only duplicate that logic).
- Unknown/wrong-kind digital channel names are silently skipped (not
  raised), symmetric with analog's own established precedent.

### Sidebar UI (`frontend/index.html`)

- `digitalChannelNameCellHtml(sourceId, channel)` (now takes `sourceId`)
  appends `wwDigitalCurBadgeHtml(sourceId, channel.name)` inside the
  existing `.channel-name-cell` flex row -- `.digital-cur-badges` gets
  `margin-left: auto`, pushing it to the row's right edge without
  touching `.channel-name-cell`'s own shared CSS (which analog's cell
  also uses). No new `<td>`, no new table column, no header label added
  to the digital `<thead>` -- `renderDigitalGroup()`'s own
  `renderChannelTable()` call is otherwise unchanged (still just the one
  "Channel" column).
- Neutral badge styling only (`--surface-tint`/`--panel-border`/
  `--text-dim` for the "A:"/"B:" label, `--text` for the state digit) --
  deliberately never `--ok`/`--error`, since digital semantics vary by
  signal and 0/1 must never visually imply healthy/alarm (owner's
  explicit instruction).
- Hidden-row opacity (25%/55% hover, unchanged CSS) already cascades to
  the badges automatically; the badge TEXT itself independently reads
  "–"/"–" for a hidden channel via `wwDigitalCurStateText()`'s own
  `wwIsDigitalChannelVisible()` gate -- never relies on opacity alone to
  hide a stale value (same defense-in-depth contract as analog's
  `wwCurValueText()`).

### Frontend state / batching

- New `ww.digitalCursorValues` (`Map<"sourceId::channelName", {aState,
  bState}>`) -- a DELIBERATELY separate Map from `ww.cursorValues`
  (analog), never sharing key space, so an analog `0.0` and a digital `0`
  can never collide even though both reuse the identical
  `wwChannelKey()` shape.
- `wwFetchCursorValuesForSource(sourceId)` (Phase 4C1's own function)
  extended to gather BOTH `wwDisplayedAnalogChannelNamesForSource()` and
  the new `wwDisplayedDigitalChannelNamesForSource()`, sending both in
  ONE POST body (`analog_channel_names`/`digital_channel_names`) -- a
  source with both kinds displayed costs exactly one request, never two.
  No-op only when BOTH lists are empty.
- Hooked into digital's own existing "core mutation" functions
  (`wwAddDigitalChannels()` -- fetch on newly-shown channels;
  `wwRemoveDigitalChannelByKey()`/`wwRemoveDigitalChannelsByKeys()` --
  clear+re-render badges on hide, individual and group-batched;
  `wwRemoveChannelsForSource()`'s own digital branch -- clear on full
  source removal), mirroring Phase 4C1's analog hook pattern exactly, no
  new hook points invented.
- Mode OFF/individual cursor closed (`wwCursorValuesHandleModeDisabled()`/
  `wwCursorValuesHandleCursorClosed()`, both pre-existing Phase 4C1
  functions) extended to also clear/redraw digital state -- ONE shared
  per-source generation counter already protects both kinds (they are
  always fetched together), so no second stale-response mechanism was
  needed.
- Drag: no second throttle -- `wwScheduleCursorValuesRefresh()` (Phase
  4C1's existing ~50ms leading+trailing throttle) already calls the
  now-combined `wwFetchAllCursorValues()`, so digital state rides the
  exact same coalesced cadence as analog, with the same guaranteed final
  `pointerup` settle.

### Tests

Backend: 19 new tests -- 12 service-level (`TestDigitalStaticState`,
`TestDigitalTransitions` incl. the exact-transition-timestamp rule on
both rising and falling edges, `TestDigitalOutsideBounds`,
`TestDigitalBatchedWithAnalog`, `TestDigitalUnknownChannelHandling`,
`TestDigitalSourceIsolation`, `TestDigitalClassificationPreservation`
incl. a normal_state=1/state=1 non-inversion test) + 7 API-level
(`TestDigitalValidRequests` using synth_ascii's own real `BRK_A`/`BRK_B`
channels -- hand-verified exact-transition anchor at t=0.005s,
`TestDigitalBoundsAndUnknownChannels`). Full backend suite: 374/374
passing (355 prior + 19 new), no regressions.

Frontend: new `phase4c2_check.mjs` (24 checks) covering sidebar structure
(no new table column), all gating conditions, 100-channel batch
efficiency, combined analog+digital single-request batching, cross-source
non-collision, drag-throttle reuse (including dragging across a real
state transition), layout-mode/Absolute-Elapsed independence,
classification-group preservation, source-switch/Start-New-Workspace
clearing, zero-channels no-request behavior, error handling, and analog
(Phase 4C1) preservation. Full frontend regression suite reconfirmed at
exactly the established 18-failure baseline -- no regressions from this
phase's changes (verified both by direct count and by re-running
`phase4c1_check.mjs`'s own 26 checks, all still passing, after updating
its mock to the renamed request field).

### Decision

Recorded as
[DEC-040's own second addendum](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1)
-- the same core authority principle extended to a second channel kind,
not a new decision number, since the underlying rule is identical (only
channel kind and value type differ).

---

## Phase 4C1 — A/B Cursor Channel Values (Cur A / Cur B) (2026-08-20)

### Scope

Extends the DEC-039 A/B time measurement cursors with the first VALUE
measurement: the Channels sidebar now shows each displayed analog
channel's recorded Y-axis value at Cursor A and Cursor B, in two new
compact "Cur A"/"Cur B" columns. Cur A/B is agnostic to what a channel's
recorded values represent (instantaneous, RMS, frequency, power, ROCOF,
etc. -- it simply reads that channel's own recorded sample; see the
"owner terminology clarification" note below). Explicitly out of scope
this phase: CALCULATED RMS/angle (deriving a new value from an
instantaneous waveform), delta angle, amplitude delta, interpolation,
on-canvas annotations, digital state at cursor, cross-source
synchronization, resampling, and phasor calculation.

### Engineering authority

Cur A/B are always read from the authoritative full-resolution
`DisturbanceRecord.waveform_data` at the NEAREST ACTUAL SAMPLE to the
cursor's engineering time -- never from a Plotly trace, a downsampled/
peak-preserving display representation, or interpolation between samples.
Each source's own native time array is searched independently (no shared/
assumed sample-rate math across sources). A cursor time outside a given
source's own valid bounds returns no value for that source (never
clamped to the boundary).

**Owner terminology clarification (same day)**: this phase's original
working title, "Instantaneous Cursor Values," was too restrictive. Cur
A/B are GENERIC CHANNEL Y-AXIS VALUES at cursor A/B -- the recorded value
of whatever channel is selected, at the nearest actual sample -- never an
assumption that every analog channel represents an instantaneous
waveform. A channel already recorded as RMS voltage/current, frequency,
or power yields THAT recorded value unchanged; Cur A/B never
re-interprets it. A dedicated code audit (grep across every cursor-value
function in both `backend/` and `frontend/index.html` for
`engineering_type`/`engineeringType`) confirmed the implementation was
already generic -- no functional code change was required, only this
terminology correction. See
[DECISIONS.md — DEC-040's own addendum](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1)
for the full record.

### Backend (`backend/`)

- `app/services/waveform_service.py`: new `extract_cursor_values()` plus
  `CursorPointResult`/`ChannelCursorValues`/`CursorValuesResult`
  dataclasses and `_nearest_sample_index()` (binary-search nearest-sample
  with an earlier-sample tie-break, documented and tested).
- `app/schemas/cursor_values.py` (new): `CursorValuesRequest`/
  `CursorValuesOut` wire shapes.
- `app/api/v1/sources.py`: new `POST
  /api/v1/workspaces/{workspace_id}/sources/{source_id}/cursor-values` --
  one batched request per source (channel list + both cursor times in one
  body), never one request per channel. Unknown/non-analog channel names
  are silently omitted from the response (a deliberate departure from
  `extract_digital_waveform`'s all-or-nothing precedent, justified by
  live-dragging reliability).

### Frontend (`frontend/index.html`)

- New cache `ww.cursorValues` (`Map<"sourceId::channelName", {aValue,
  bValue, aSampleTime, bSampleTime}>`) -- pure derived state;
  `ww.measurementCursors` (DEC-039) remains the one cursor-TIME authority,
  only ever read from here.
- `wwFormatEngineeringValue()`: adaptive formatting (1 decimal for
  |value| >= 1, 3 decimals for |value| in [0.001, 1), exponential below
  that) -- matches every owner-supplied worked example exactly.
- `wwCurValueText()`: the single gating+formatting authority every render
  path goes through -- returns "—" whenever cursor mode is off, that
  specific cursor is closed/absent, or the channel itself is hidden,
  regardless of cache contents.
- Sidebar analog table extended from Channel/Phase to Channel/Phase/Cur
  A/Cur B (`renderChannelTable()` now accepts an optional per-column
  `className` for the new columns' compact/right-aligned/tabular-nums
  styling). Digital sidebar unchanged -- no Cur A/B columns added there.
- Batching: `wwFetchCursorValuesForSource()`/`wwFetchAllCursorValues()`
  issue exactly one POST per source with every currently-DISPLAYED analog
  channel for that source (respecting DEC-038's default-hidden policy --
  a hidden channel is never fetched). Hooked into the existing "core
  mutation" functions (`wwAddSelectedChannels()`, `wwRemoveChannel()`,
  `wwRemoveChannelsByKeys()`) so both individual row toggles and group
  Show-all/Hide-all (`wwToggleChannelGroupDisplay()`) get correct
  batched behavior for free, with no separate group-specific hook needed.
- Live drag: `wwScheduleCursorValuesRefresh()` is a leading+trailing
  throttle (~50ms) coalescing rapid pointermoves into far fewer backend
  requests, while the visual cursor line itself still moves at full
  pointermove speed (unchanged from DEC-039, unthrottled). `pointerup`
  always issues one final, unthrottled request for the exact settled
  position. A per-source monotonically increasing generation counter
  (`wwCursorValuesGeneration`) discards any response that is no longer
  the latest outstanding request for that source.
- Clear points: cursor mode disabled
  (`wwCursorValuesHandleModeDisabled()`), an individual cursor closed
  (`wwCursorValuesHandleCursorClosed()`), a channel hidden
  (`wwClearCursorValuesForChannels()` from both the single-channel and
  batched-removal paths), source switch/reinit
  (`wwReinitCursorsForNewViewport()`), and Start New Workspace
  (`wwResetMeasurementCursors()`) -- never let a previous source's or a
  hidden channel's values leak into what is currently rendered.

### Tests

Backend: 18 new tests in `test_cursor_values_service.py` (nearest-sample
search, documented tie-break, bounds behaviour, a dedicated full-
resolution-authority test proving a reduced-envelope display point can
differ from the true value used for measurement, multi-rate sources,
batched-index reuse, unknown-channel handling) + 9 new tests in
`test_cursor_values_api.py` (end-to-end upload -> cursor-values flow,
source-identity non-collision). Full backend suite: 355/355 passing (328
prior + 27 new), no regressions.

Frontend: new `phase4c1_check.mjs` (26 checks) covering numeric
formatting, all four gating conditions, batching (including a 20-channel
group Show-all producing exactly one request), source identity/bounds
across two sources, drag throttling and stale-response protection,
layout-mode independence (Grouped/Separate/Custom report identical
values), Absolute/Elapsed and zoom/pan non-refetch, source-switch and
Start New Workspace clearing, zero-channels no-request behavior, error
handling, and digital-sidebar non-interference. Full frontend regression
suite reconfirmed at exactly the established 18-failure baseline (two
older Phase 4A-UAT4/UAT5 assertions were updated in place to expect the
now-4-column analog table, since the extra columns are this phase's own
intended change, not a regression).

### Decision

Recorded as a new decision,
[DEC-040](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1)
-- the first VALUE measurement built on DEC-039's cursor-time
architecture, which it extends by reference and does not alter.

---

## Phase 4B-UAT3 — Fix A/B Main Cursor Lines Disappearing After Vertical Scroll (2026-08-20)

### Owner confirmed: the previous fix did not resolve the bug

Owner real-browser UAT of Phase 4B-UAT2 below found its `offsetTop`
geometry fix necessary but **not sufficient**. Stated plainly, not
hidden: this phase is a correction of an incomplete prior fix, not a
brand-new independent bug.

**Precise owner evidence**: with cursor mode already ON and a tall
(Separate-mode, many-channel) waveform stack, scrolling deep into the
canvas made the MAIN vertical lines (through the analog/digital panels)
disappear -- while the sticky A/B labels and the ruler's own A/B segments
(both driven by entirely separate rendering paths from the main overlay)
stayed correctly visible throughout. Toggling cursor mode OFF then ON
reliably restored the lines immediately.

### Reproduction (followed exactly)

1. Open a recording with enough analog channels to require substantial
   vertical scrolling in Separate mode.
2. Display all of them (Separate mode, many single-channel lanes).
3. Enable A/B -- both main lines correctly cross every panel.
4. Scroll `#activeViewArea` substantially downward.
5. Main lines disappear; sticky labels and ruler segments remain correct.
6. Toggle cursor mode OFF then ON -- main lines return immediately.

### Root-cause reasoning

Scrolling triggers NO application code by design (no scroll listener
existed before this phase) -- the DOM/CSS state (every line/range
element's `style.left`/`style.height`/`hidden`) is therefore
byte-identical immediately before and after the user scrolls; nothing
programmatically changes it. The ONE thing the OFF-then-ON toggle does
differently from mere scrolling is re-invoke `wwUpdateCursorOverlay()`,
which reassigns those same style properties -- including cases where the
newly-computed value is numerically IDENTICAL to what was already there.

Given the DOM geometry was very likely already correct (Phase 4B-UAT2's
own `offsetTop`-based height fix is retained here, unchanged, and
confirmed still correct -- see the "still eliminated" note below), the
most consistent explanation is that the browser was not reliably
repainting this `overflow: hidden`, absolutely-positioned overlay as its
scrolling ancestor (`#activeViewArea`) moved, until a genuine style
reassignment forced a fresh style/layout/paint pass for that element.
**This sandbox has no real browser available** to directly confirm the
exact paint/compositing mechanism via `document.elementFromPoint()` or
DevTools stacking-context inspection (both explicitly requested
diagnostics) -- this reasoning is disclosed as the best-supported
analysis from the available evidence, not a directly observed fact.

### Confirmed: Phase 4B-UAT2's geometry fix was NOT reverted

Re-inspected per this task's own explicit instruction. `overlayEl.style.height`
is still computed from `rulerWrapEl.offsetTop`, never from
`rulerWrapEl.getBoundingClientRect().top` (the disproven, sticky-affected
source). This remains correct and necessary -- it is retained unchanged;
this phase adds a second, independent fix on top of it rather than
replacing it.

### Fix: a proven, targeted scroll-triggered refresh

A `scroll` listener on `#activeViewArea` (the real scroll container),
rAF-coalesced exactly like the pre-existing
`wwScheduleResizeAllVisiblePlots()` (`window resize`), re-invokes the
SAME, already-proven `wwUpdateCursorOverlay()` pass -- the ONE action
already proven (by the OFF/ON toggle itself) to restore the lines,
regardless of the precise underlying browser mechanism. New
`wwScheduleCursorOverlayRefresh()`: an early return whenever
`ww.measurementCursors.enabled` is false (ordinary scrolling with cursors
off costs nothing extra), otherwise schedules at most one
`wwUpdateCursorOverlay()` call per animation frame. Wired via
`document.getElementById("activeViewArea").addEventListener("scroll",
wwScheduleCursorOverlayRefresh, { passive: true })`.

This is a deliberate, evidence-driven exception to the original "prefer
CSS sticky, avoid a scroll listener" preference from Phase 4B-UAT1 --
explicitly authorized by the owner once real-browser evidence
(the OFF/ON behavior) proved CSS alone insufficient. `wwUpdateCursorOverlay()`
itself remains cheap (a handful of `getBoundingClientRect()`/`offsetTop`
reads and `style`/`textContent` writes) -- never a Plotly call, waveform
fetch, or panel rebuild -- so this stays within the same performance
contract every other recompute hook already honors, even at native
scroll-event frequency.

### Range band / ruler / sticky labels

The A-B range band lives inside the same `#wwCursorOverlay` container as
the lines, so it is fixed by the exact same change, with no separate code
path. The ruler segment (`#wwCursorRulerOverlay`, inside the sticky
`#wwStickyRuler`) and the sticky label layer (`#wwCursorLabelLayer`,
`position: sticky`) were never part of the buggy lifecycle -- both
already worked correctly throughout scrolling, per the owner's own
evidence, and neither needed any change.

### Tests

`phase4b_check.mjs` extended to 45 checks (from 43): the one test whose
premise ("no scroll listener exists") is now the OPPOSITE of the correct,
owner-authorized behavior was rewritten (not deleted) to confirm the
listener exists, is rAF-coalesced, and stays within its performance
contract (no engineering-time change, no Plotly call of any kind, no
waveform fetch); a new test confirms the refresh is a genuine no-op while
cursor mode is disabled; a new test proves the actual LIFECYCLE gap this
phase closes, by changing the mocked ruler geometry after cursor mode is
already enabled (simulating geometry that becomes stale without a
toggle) and confirming a bare `scroll` event alone -- with no OFF/ON --
picks up the new value. **Explicitly disclosed limitation**: jsdom has no
real layout/paint/compositing engine, so this suite cannot observe the
actual real-browser symptom (a paint-staleness question, not a DOM-state
one) -- only the lifecycle gap and the performance contract are
genuinely verifiable here; real-browser owner UAT remains authoritative
for the visual symptom itself. Full frontend regression suite
reconfirmed at exactly the established 18-failure baseline. Backend:
328/328 passed, unchanged (no backend file touched).

### Decision

Recorded as a fourth addendum to
[DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b)
-- a corrective bug fix within the already-approved overlay architecture,
not a new decision.

---

## Phase 4B-UAT2 — Cursor Range Fill + Full-Scroll Line Continuity Fix (2026-08-20)

### Owner-reported bugs

Two confirmed bugs in Phase 4B-UAT1's own work below, fixed -- not
redesigned. (1) DevTools showed `--cursor-range-fill` as undefined,
so the 20% blue A-B range fill was not visible at all. (2) The sticky
A/B labels correctly stayed visible while scrolling down a tall waveform
stack, but the vertical cursor LINES disappeared further down the same
stack -- violating the core requirement that A/B span the complete
waveform (analog + digital + ruler) throughout vertical scrolling.

**Owner mid-task clarification**: while this fix was in progress, the
range-fill opacity target changed from 20% to a final 8% (`rgba(53, 104,
212, 0.08)` Light / `rgba(79, 141, 253, 0.08)` Dark) -- applied in the
same pass as the undefined-variable investigation below.

### Bug 1 investigation and fix (`--cursor-range-fill` undefined)

Checked, in order: the `:root`/`:root[data-theme="dark"]` declarations in
`theme.css` (both present, both syntactically correct, no typo); whether
`index.html`'s own inline `:root { --button-font-size-compact: ... }`
block (a genuine, pre-existing, unrelated page-specific token -- see
DEC-023's own history) could shadow/reset the theme.css declaration (it
cannot -- CSS custom properties are declared independently per property
name; a `:root` rule that doesn't mention a given property never resets
it, regardless of cascade/source order); the `data-theme` selector
mechanism against `theme.js`'s actual `setAttribute("data-theme", ...)`
call (confirmed matching); and the `.ww-cursor-range`/
`.ww-cursor-ruler-range` rules' own `background: var(--cursor-range-fill)`
consumption (confirmed correct, unchanged since Phase 4B's own cosmetic
refinement). The live DEV-deployed `theme.css` was fetched directly
(`curl https://dev.powerwave.oruxa.uk/theme.css`) and found byte-correct,
containing the token at both declarations. No code-level declaration,
cascade, scope, or consumption bug was found.

Given the source and the deployed artifact are both provably correct, the
best-supported explanation for a real user's DevTools showing "undefined"
is browser-side caching of a stale, pre-Phase-4B-cosmetic-refinement copy
of `theme.css` -- that static asset reference (`<link rel="stylesheet"
href="theme.css">`) carries no cache-busting mechanism, and the server
sets no explicit `Cache-Control` header (confirmed via `curl -I`, only
`ETag`/`Last-Modified` passive validators are present), so a browser that
loaded the app once before `--cursor-range-fill` existed could plausibly
continue serving that cached copy via heuristic freshness on later
navigations, even though index.html itself (a separate resource, and one
the owner's own concurrent report confirms was fresh, since the
Phase 4B-UAT1 sticky-label behavior it introduced was already working
correctly) had already updated. **This is a real, but genuinely
out-of-scope-for-this-bug-fix, deployment/caching gap** -- flagged to the
owner as a possible follow-up rather than fixed unilaterally (a
cache-busting mechanism would need to touch the shared
`docker-entrypoint.d/10-powerwave-config.sh` entrypoint and/or nginx
config, affecting every static asset and both HTML pages, well beyond
this one CSS token).

What WAS changed in this pass: `--cursor-range-fill`'s alpha value, to
the owner's now-final target of 0.08 (`theme.css`, both themes) --
unrelated to the "undefined" investigation itself, just the concurrent
opacity-target correction. Verified via a jsdom test that exercises the
REAL CSS cascade engine end-to-end
(`getComputedStyle(realElement).getPropertyValue("--cursor-range-fill")`
on the actual `.ww-cursor-range`/`.ww-cursor-ruler-range` elements the
feature builds, toggling `data-theme` between calls) rather than
source-text regex matching alone -- the strongest verification available
without a real browser.

### Bug 2 root cause and fix (lines disappearing during deep scroll)

`wwUpdateCursorOverlay()`'s overlay-height computation was
`rulerRect.top - sectionRect.top`, both from `getBoundingClientRect()` --
VIEWPORT-relative coordinates. `#wwStickyRuler` is `position: sticky`,
which repaints the ruler at a roughly constant on-screen position once
"stuck," decoupling `rulerRect.top` from the ruler's TRUE position in the
scroll content, while `sectionRect.top` (`.workspace-section`'s own
viewport-relative top) keeps changing with scroll -- a height computed
from that pair is not a reliable stand-in for the true content height
once/while the ruler's paint position and its true document-flow position
diverge, silently under- or over-sizing the `overflow: hidden` overlay
and clipping the lines/range-band partway down a tall stack.

Fixed by reading `rulerWrapEl.offsetTop` instead of
`rulerWrapEl.getBoundingClientRect().top` for the height computation --
`offsetTop` reflects an element's position in NORMAL LAYOUT FLOW relative
to its `offsetParent`, a value that is, by CSS specification, unaffected
by scroll position and unaffected by `position: sticky`'s paint-time
displacement (sticky positioning is a compositing-time adjustment; it
never changes the element's underlying layout box). `.workspace-section`
(`#viewWaveform`, `position: relative`) is confirmed to be
`#wwStickyRuler`'s `offsetParent` (its direct parent, and the nearest
positioned ancestor) -- the same reference frame `#wwCursorOverlay`'s own
`top: 0` already uses, so no other coordinate needed changing.
`rulerRect` (`getBoundingClientRect()`) is still used, unchanged, for the
ruler SEGMENT's own horizontal positioning (`#wwCursorRulerOverlay`,
inside the sticky ruler, where the CURRENT on-screen position is exactly
what's wanted). No scroll listener was added -- `offsetTop` does not
change with scroll, so the existing recompute hooks
(`wwSyncStickyRuler()`/`wwRebuildLayout()`/`wwResizeAllVisiblePlots()`/
`wwRebuildDigitalChart()`) remain sufficient, matching this task's own
"prefer structural/CSS geometry... do not add an expensive scroll
listener" requirement. The A-B range band, living inside the same
now-correctly-sized `#wwCursorOverlay`, is fixed by the same change with
no separate code path.

### Tests

`phase4b_check.mjs` extended to 43 checks (from 37): the stale 0.20-alpha
assertion updated to 0.08 (an intentional value change); new checks cover
`getComputedStyle` resolving `--cursor-range-fill` to the correct,
theme-distinct, non-empty value on the real `.ww-cursor-range`/
`.ww-cursor-ruler-range` elements; the overlay height using the ruler's
stable `offsetTop` rather than its live/sticky-affected
`getBoundingClientRect().top` (a new `wireCursorGeometry()` fixture knob
lets the test independently control the ruler's "current on-screen
position" vs. "true content position," reproducing the exact bug
scenario -- the old formula would have produced 460px where the fixed one
correctly produces 2000px/3500px/2400px across the new checks); overlay
height stability across a dispatched `scroll` event; the range band
sharing the same corrected height/container as the lines; and horizontal
(X) positioning of lines/labels/ruler segment remaining unaffected by the
height fix. Full frontend regression suite reconfirmed at exactly the
established 18-failure baseline. Backend: 328/328 passed, unchanged (no
backend file touched).

### Decision

Recorded as a third addendum to
[DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b)
-- bug fixes within the already-approved overlay architecture, not a new
decision.

---

## Phase 4B-UAT1 — Stronger Range Highlight + Sticky Cursor Labels (2026-08-19)

### Owner-approved scope

A narrowly-scoped follow-up to Phase 4B and its cosmetic-refinement
addendum below, both already owner-UAT'd. Two requests: (1) raise the A-B
range-highlight band's opacity from ~5% to ~20% (5% read as too faint);
(2) make the top "[A ×]"/"[B ×]" label pills remain visible near the top
of the visible waveform viewport while scrolling a tall waveform stack --
explicitly NOT making the engineering cursor or its vertical line sticky,
only the label. Reuse the existing overlay architecture (DEC-039); no
redesign, no new heavy re-render path, no scroll-event pixel loops.

### What changed (`frontend/index.html` + `frontend/theme.css` only)

**Range opacity**: `--cursor-range-fill` raised from `rgba(53, 104, 212,
0.05)`/`rgba(79, 141, 253, 0.05)` (Light/Dark) to `0.20` for both --
`theme.css` only, no other property touched. Geometry, positioning,
drag-live-update behavior, and `pointer-events: none` are all byte-for-
byte unchanged.

**Sticky labels**: investigated the actual scroll container first, per
this task's own instruction. `#activeViewArea` (a sibling of the fixed
`#wwToolbar`, `overflow-y: auto`) is the real scrolling ancestor for the
whole waveform workspace -- unchanged since Phase 3A. `#wwCursorOverlay`
(the line/hit-target overlay) has `overflow: hidden`, which per the CSS
Overflow spec establishes ITS OWN box as the nearest "scroll container"
for any `position: sticky` descendant, breaking the intended stick-to-
`#activeViewArea` behavior entirely -- CSS sticky could not simply be
added to the existing `.ww-cursor-label` in place.

Fix: the label markup was extracted into a NEW sibling element,
`#wwCursorLabelLayer` (`position: sticky; top: 6px;`), living directly
inside `.workspace-section` (`overflow: visible`, no scroll-container
ancestor between it and `#activeViewArea`) -- so it sticks correctly to
the top of the actual scrolled viewport, with a 6px offset keeping it
just below the true top edge (section 7's "small top offset is
acceptable"; no fixed page-wide coordinate needed since `#wwToolbar`
lives OUTSIDE `#activeViewArea` entirely, so there is no header height to
subtract). `height: 0` so the layer adds no scrollable space of its own;
its label children remain `position: absolute` (a `position: sticky`
element is a valid containing block for absolutely-positioned
descendants), positioned via the SAME `pageX - sectionRect.left`
conversion `wwCursorTimeToPixelX()` already produces for the lines
(section 5/19 -- one X-projection authority, never a second
implementation). `wwEnsureCursorDom()` now builds three things instead
of two (line overlay, ruler segment, label layer); `wwUpdateCursorOverlay()`
and the drag path's own `livePositionUpdate()` both write the label's
`style.left`/`hidden` alongside the line's, in the same pass. The line
overlay (`.ww-cursor-line`, full `top:0`/`bottom:0`) is completely
unchanged -- still spans analog through digital through the ruler
segment exactly as before (section 9); only the label pill moved.

Interaction: `.ww-cursor-close` and the label's own `data-cursor-drag`
now live inside `#wwCursorLabelLayer` instead of `#wwCursorOverlay`.
`wwWireCursorDrag()`'s pointerdown/click handlers were extracted into
named functions and attached to BOTH elements (no duplicated drag logic)
so pointer-capture drag and the × close buttons work identically whether
triggered from the invisible hit strip (still in `#wwCursorOverlay`) or
the sticky label itself (section 11/12/21). Z-index: label layer above
both cursor overlays (section 13) so it always renders on top; it never
blocks unrelated controls since its own `pointer-events: none` only opts
back in on the label pills themselves, same policy the line overlay
already used.

No manual scroll event listener was added anywhere -- CSS `position:
sticky` handles the entire behavior natively (section 6/16's own explicit
preference), so scrolling costs nothing beyond ordinary browser
compositing.

### Tests

`phase4b_check.mjs` extended to 37 checks (from 29): the range-opacity
assertion updated from 0.05 to 0.20 (an intentional value change, not a
regression); new checks confirm the label layer is `position: sticky`
and a genuine sibling of (not nested inside) `#wwCursorOverlay`, the
label markup no longer appears inside a `.ww-cursor-line` template, all
three overlay pieces (line overlay/ruler segment/label layer) render
distinctly when cursor mode is active, the sticky label's X stays
pixel-identical to its cursor line's X after pan/layout-switch/resize,
a dispatched `scroll` event never changes `a.time`/`b.time` and no
`addEventListener("scroll"` exists anywhere in the shipped script,
dragging directly from the label element itself (not only the hit strip)
updates the correct cursor with zero waveform fetch, the × close button
remains functional while living in the sticky layer and only affects its
own cursor, and the label layer's z-index exceeds both cursor overlays
while the line's own full-height CSS is unchanged. Full frontend
regression suite reconfirmed at exactly the established 18-failure
baseline. Backend: 328/328 passed, unchanged (no backend file touched).

### Decision

Recorded as an addendum to
[DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b)
-- cosmetic/structural refinement within the already-approved overlay
architecture, not a new decision.

---

## Phase 4B — A/B Time Measurement Cursors (2026-08-19)

### Owner-approved scope

The first dedicated measurement feature: two draggable, workspace-level A
(blue)/B (red) TIME cursors (never amplitude cursors) that visually span
the entire waveform workspace -- every analog panel, the digital region,
and the shared time ruler -- so an engineer can mark two times, compare
event timing, and read a live Δt. Explicitly out of scope: amplitude
measurement, ΔY, sample snapping, value interpolation, a cursor-linked
table, cross-source synchronization, event annotations, calculated
signals.

**Owner mid-task clarification**: cursor state is GLOBAL across
Grouped/Separate/Custom (never per-layout state) -- switching layout mode
must recompute only the overlay's pixel projection, never the stored
engineering time.

### Architecture (DEC-039)

One workspace-level DOM overlay, never a Plotly `layout.shapes` entry
duplicated into every panel -- see
[DECISIONS.md DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b)
for the full architecture, alternatives considered, and reasoning; not
duplicated here.

### Implementation (`frontend/index.html` only, no backend change)

**State**: `ww.measurementCursors = { enabled, a: {visible, time}, b:
{visible, time} }`, appended to the `ww` object literal. `time` values are
always elapsed engineering seconds -- the same coordinate system as
`ww.viewport`/`ww.workspaceBounds` (DEC-037), never pixels or a Plotly
paper coordinate.

**DOM**: `#wwCursorModeBtn` (a `.secondary` toolbar toggle, same visual
language as Zoom/Pan/Reset Time View, living inside the EXISTING
`#wwToolbar` so it naturally follows `wwUpdateEmptyState()`'s established
show/hide-when-empty gate -- a deliberate simplification permitted by the
task's own section 27 fallback language, not an oversight).
`#wwCursorOverlay` (a sibling of `#wwPanels`/`#wwDigitalRegion` inside
`.workspace-section`, `position: absolute`, height set by JS to reach
exactly the top of the ruler -- never further, to avoid a double line
where the ruler sits in its natural, non-stuck flow position).
`#wwCursorRulerOverlay` (a child of `#wwStickyRuler` itself, inheriting
its `position: sticky` automatically -- the fix for the ruler's sticky
pinning otherwise detaching the line from it mid-scroll). Right side of
`#bottomStatusBar`: A/B/Δt readout, pushed there via a flex spacer
(`.ww-status-spacer`), the same technique `.toolbar-spacer` already uses.

**Pixel<->time conversion (one authority, section 12)**:
`wwCursorPlotMetrics()` reads a REAL rendered Plotly surface's own
`_fullLayout.xaxis._offset`/`_length` (preferring the ruler chart, falling
back to the digital chart, then the first analog panel) -- the exact
technique `wwDiagnoseDigitalAlignment()` (Phase 4A-UAT2) already
established, never a guessed/hard-coded margin.
`wwCursorTimeToPixelX()`/`wwCursorPixelXToTime()` are the two directions;
the inverse clamps to the plot's own bounds during drag (section 15),
equivalent to clamping engineering time to `[viewport.start,
viewport.end]` since the plot's own xaxis range already IS that viewport.
A cursor outside the current viewport is explicitly hidden (not merely
positioned beyond the visible plot area) -- its engineering time is
untouched either way (section 15/16: "do NOT silently move the cursor").

**Dragging (section 13/14/38)**: pointer-capture on a wide (~10px)
invisible hit strip or the compact "[A ×]"/"[B ×]" label -- plot metrics
are measured ONCE at pointerdown and reused for the whole gesture (nothing
that would change plot geometry can happen mid-drag, since this never
touches `ww.viewport`/panels/layout); each pointermove only writes
`style.left`/textContent, never a Plotly call, backend fetch, or layout
rebuild. `wwUpdateCursorOverlay()` (the one authoritative recompute-and-
render pass) runs once on pointerup, mirroring the same "cheap during
drag, one full pass at the end" shape `wwWireResizeHandle()` already
established for panel-height dragging.

**Recompute hook points (section 39)**: rather than a new, independent
resize/scroll listener, `wwUpdateCursorOverlay()` is called from the
small number of EXISTING functions that already run on every event that
can move a cursor's pixel projection: `wwSyncStickyRuler()` (viewport/
time-mode/channel add-remove/clear), `wwRebuildLayout()` (Grouped/
Separate/Custom switch, Custom Groups editor Apply -- deliberately never
touches cursor TIME, per the owner's clarification above),
`wwResizeAllVisiblePlots()` (window resize, Workspace Sidebar drag, Main
Sidebar Menu collapse/expand), `wwResizePanelPlot()` (individual panel-
height drag), and `wwRebuildDigitalChart()` (digital region height
changes).

**Source-aware bounds integration (section 25, reusing DEC-037's own
"fresh viewport" signal)**: `wwRefreshWorkspaceBounds()` already computes
`isFreshViewport` (true on a genuinely new source selection, the first
viewport ever, or source bounds that actually changed -- the SAME
condition that already decides "reset vs. clamp existing" for
`ww.viewport` itself). `wwReinitCursorsForNewViewport()` is called
exactly when that flag is true AND cursor mode is enabled, reinitializing
A/B to the new viewport's 1/3-2/3 -- stale times from a previous
recording never carry over. Re-selecting the SAME already-open source
(the flag is false) never reinitializes. When the workspace becomes
genuinely empty (no participating source left), cursor mode is disabled
automatically. "Start New Workspace" (`wwClearWorkspace({
resetSourceBounds: true })`) is the one place cursor state resets
completely (`wwResetMeasurementCursors()`); the plain "Clear workspace"
button deliberately leaves cursor state alone (it keeps the still-
selected source's bounds/viewport).

**Formatting**: `wwFormatCursorDuration()` (three tiers -- µs/ms/s,
signed, so Δt's sign per section 21 is preserved) is a NEW, dedicated
function -- deliberately not a reuse of `wwStickyRulerElapsedUnit()`/
`wwTimeAxisTickFormat()`, which configure an entire Plotly axis for a
visible span, a different job from formatting one scalar duration as
status-bar text. `wwFormatCursorPointTime()` (A/B's own point-in-time
text) reuses `wwFormatPlotlyDateString()` -- the same naive-UTC formatter
every other Absolute-mode surface already uses -- for Absolute mode,
falling back to `wwFormatCursorDuration()` in Elapsed mode or when no
trustworthy recording origin exists, matching `wwElapsedToPlotlyX()`'s own
existing fallback.

**Colors**: A reuses the existing `--accent` token, B reuses `--error` --
both already theme-aware blue/red-ish tokens (Light and Dark), not new
hard-coded hex values, satisfying the owner's "distinct A=blue/B=red
identity... accessible in both themes" requirement without introducing a
third color system alongside the existing waveform trace palette.

### Tests

New dedicated `phase4b_check.mjs` (22 checks, scratch convention -- not
committed to the repo): default-off activation and 1/3-2/3 init (including
with zero displayed channels), structural verification of exactly one A/B
overlay pair for the whole workspace (never one per panel) and the
overlay's own height/parentage, dragging (time update, no waveform
refetch, edge clamping), zoom/pan preserving cursor engineering time while
an out-of-viewport cursor goes off-screen and reappears correctly on
Reset Time View, individual close (Δt unavailable, toolbar mode stays
on) and the OFF->ON restore path, adaptive µs/ms/s formatting and signed
Δt, Absolute/Elapsed presentation-only, the owner's own Grouped ->
Separate -> Custom -> Grouped global-persistence acceptance scenario
(drag A/B in Grouped, assert identical time/Δt after each subsequent
layout switch), digital-region continuity, default-hidden non-
interference (zero waveform fetches from merely enabling cursor mode),
confirmation `ww.recordBounds` was never reintroduced, source-switch
reinit vs. same-source-reselect non-reinit, and Start New Workspace's
full reset vs. plain Clear workspace's preservation.

Verification against the existing regression suite: adding
`#wwCursorRulerOverlay` as a second child of `#wwStickyRuler` made one
pre-existing `phase2cc4a_check.mjs` check's "the ruler wrapper contains
ONLY the chart element" assertion obsolete (a foreseeable, intentional
consequence of this phase's own architecture, not a regression -- the
title/date-context elements that check actually guards against are still
confirmed absent) -- updated to assert exactly two children (the chart
plus the new cursor overlay) instead of one. Full frontend regression
suite confirmed back to exactly the established 18-failure baseline after
that update (verified both ways: 19 failures with the stale assertion
still in place, 18 after correcting it, and cross-checked against
canonical pre-Phase-4B `frontend/index.html` via `git stash` to confirm
the 9 other still-failing files were already failing beforehand,
unrelated to this phase). Backend: 328/328 passed, unchanged (no backend
file touched).

### Decision

Recorded as [DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b).

---

## Phase 4B Cosmetic Refinement — Thinner A/B Lines + Range Highlight Band (2026-08-19)

### Owner-approved scope

A small, low-risk cosmetic-only refinement requested AFTER Phase 4B above
had already passed owner UAT. Explicitly not a redesign: reuse the
existing cursor overlay architecture unchanged, no new heavy re-render
path, no change to A/B off-by-default, initial 1/3-2/3 placement, close
buttons, live readout, adaptive units, engineering-time authority,
cross-layout/cross-mode persistence, drag smoothness, zero-refetch
dragging, or channel-visibility non-interference.

### What changed (`frontend/index.html` + `frontend/theme.css` only)

1. **Thinner lines**: `.ww-cursor-stroke`/`.ww-cursor-ruler-stroke` width
   reduced from 2px to 1px (with their centering `left`/`margin-left`
   halved to match). `.ww-cursor-hit`'s 10px drag hit target is
   byte-for-byte unchanged -- only the visible stroke got slimmer, drag
   usability is unaffected.
2. **A-B range highlight band**: a new `.ww-cursor-range`/
   `.ww-cursor-ruler-range` element pair, built once in the SAME
   `wwEnsureCursorDom()` call (prepended before the two cursor lines so it
   paints behind them) and positioned/hidden by the SAME
   `wwUpdateCursorOverlay()` pass plus the drag path's own
   `livePositionUpdate()` -- never a second overlay system. Shown only
   when BOTH A and B are visible (the same "needs both endpoints" rule
   the Δt readout already used); its two edges use UNCLAMPED pixel
   positions (an off-screen endpoint still has a real position on the
   same line; the overlay's own pre-existing `overflow: hidden`
   containment clips the band to whatever portion of `[A, B]` is
   currently in view, rather than the band vanishing the moment either
   endpoint scrolls out of the viewport).
3. **New theme token**: `--cursor-range-fill` in `theme.css`, Light
   `rgba(53, 104, 212, 0.05)` / Dark `rgba(79, 141, 253, 0.05)` -- the
   same accent-blue RGB base `--accent-wash` already uses for each theme,
   at the owner-specified ~5% alpha, faint enough to sit behind both the
   cursor lines and every waveform trace. `pointer-events: none`
   throughout -- the band is display-only, identical to the ruler
   segment's own established non-interactive treatment.

### Tests

`phase4b_check.mjs` extended with 7 new checks (29 total, up from 22):
line width (1px, hit target unchanged), the new theme token existing for
both themes, the band's structural presence/position in both overlay
segments, its non-interactivity and paint order, closing either cursor
hiding it, live tracking during a drag with zero waveform fetches, and a
spot-check that engineering time/layout/time-mode persistence are all
otherwise unaffected. Full frontend regression suite reconfirmed at
exactly the established 18-failure baseline (unchanged from before this
refinement -- no test needed adjusting). Backend: 328/328 passed,
unchanged (no backend file touched).

---

## Phase 4A-UAT10 — Source-Aware Time Bounds (2026-08-19)

### Owner-approved scope

Owner approved the fix from **COMTRADE Duration Investigation — Part 2**:
establish a source-aware time-domain foundation without implementing
cross-record synchronization. Explicitly out of scope: absolute timestamp
alignment between recordings, trigger alignment, nearest-sample matching,
correlation, manual sync tools, resampling, or changing COMTRADE's DAT-vs-CFG
timestamp authority.

This pass also preserves the already-present
[Phase 4A-UAT9](#phase-4a-uat9--default-hidden-channels--group-visibility-toggles-2026-08-19)
product direction in the working tree: opening a recording starts with zero
analog and zero digital channels displayed. Source bounds therefore cannot
depend on a rendered waveform request.

### Proven bug

Owner UAT showed one active COMTRADE recording (`GPTH 275kV - BEN5K`) with
status metadata reporting `Duration = 7.020 s` while the waveform and Reset
Time View showed only approximately `0 -> 1.3 s`. The follow-up investigation
confirmed backend metadata duration and waveform extraction both derive from
the retained `waveform_data["time"]` path; the mismatch was frontend state:
`ww.recordBounds` was a workspace-global full-record authority learned from
the first unbounded waveform response and not owned by a source.

### Implementation

Backend:

- `DisturbanceRecord` now exposes `elapsed_start_seconds()` and
  `elapsed_end_seconds()` from the retained time column (falling back to
  `0 -> duration_seconds()` only when no time column exists).
- `SourceMetadata`, `SourceSummaryOut`, and `TimebaseOut` carry
  `elapsed_start_seconds` / `elapsed_end_seconds` as additive fields.
- `import_service` populates those fields once at import time from the
  authoritative `DisturbanceRecord`.

Frontend:

- Removed `ww.recordBounds` entirely.
- Added `ww.sourceBounds: Map<source_id, {start, end}>`, populated from
  `/channels.timebase.elapsed_start_seconds` /
  `elapsed_end_seconds` as soon as a recording is opened, even when no
  channels are displayed.
- Added derived `ww.workspaceBounds`, computed from the currently
  participating source set: the selected source plus any source with displayed
  analog or digital channels. This preserves existing multi-source display
  semantics without inventing alignment.
- Kept `ww.viewport` as the user's zoom/pan window only. Zoom/pan clamps to
  `workspaceBounds`; `Reset Time View` restores `workspaceBounds`.
- Analog and digital add paths fetch the current viewport if one exists. A
  waveform response no longer establishes permanent full-record bounds.
- Source removal deletes that source's `sourceBounds` entry and recomputes
  workspace bounds from remaining participants. Start New Workspace clears
  source bounds, workspace bounds, viewport, and display state.

### Behaviour

Opening a source with duration `7.020 s` now immediately establishes:

```text
sourceBounds[source_id] = 0 -> 7.020
workspaceBounds         = 0 -> 7.020
viewport                = 0 -> 7.020
```

with zero displayed channels and zero waveform fetches required to discover
that extent. If a `7 s` source and a `15 s` source both participate under the
current unaligned elapsed model, `workspaceBounds` is `0 -> 15`; the shorter
source is not stretched, padded, held, or resampled. Absolute/Elapsed remains
presentation-only over this same internal elapsed viewport.

### Tests

Added/updated backend tests for explicit elapsed bounds flowing through the
COMTRADE provider, source metadata/list responses, and existing `SourceMetadata`
fixtures. Added static frontend regression checks proving:

- `sourceBounds` / `workspaceBounds` / `viewport` exist as distinct state;
- `recordBounds` is absent from `frontend/index.html`;
- source bounds are read from backend elapsed timebase metadata;
- opening a source records bounds before channel display/fetch;
- Reset Time View uses workspace bounds;
- waveform responses no longer establish full bounds;
- zoom/pan clamps through `wwClampRangeToWorkspace`.

Targeted verification during implementation:

```bash
cd backend
pytest tests/test_sources_api.py tests/test_comtrade_parity.py \
  tests/test_waveform_service.py tests/test_workspace_registry.py \
  tests/test_frontend_source_bounds.py
```

Result: `57 passed`, with the existing FastAPI/TestClient deprecation warning
and one known malformed-CFG warning.

### Decision

Recorded as [DEC-037](DECISIONS.md#dec-037--waveform-time-domain-state-is-source-aware-source-bounds-workspace-bounds-and-viewport-are-distinct-phase-4a-uat10).

## Phase 4A-UAT9 — Default-Hidden Channels + Group Visibility Toggles (2026-08-19)

### Owner-approved scope

Follow-up to DEC-034's deliberate "display everything by default" UAT
experiment (Phase 4A). Owner direction: reverse the default so opening a
recording displays zero analog and zero digital channels, add compact
per-group Show all/Hide all controls so bulk display/hide stays efficient
without the unconditional default-render cost, and preserve every prior
UAT5–UAT8 row-toggle behaviour (10px dots, opacity states, direct toggle,
DEC-035 global visibility, Grouped/Separate/Custom correctness, no
duplicate traces, no checkboxes) exactly as-is. Explicitly out of scope:
the COMTRADE duration/timing investigation (picked up separately by
UAT10 above), cursor tools, calculated signals, annotations,
multi-recording sync, channel reorder, user-selected colors, digital
custom groups.

### What changed (`frontend/index.html` only)

- `selectSource()` no longer calls any default-display path.
  `wwApplyDefaultChannelDisplay()` and `ww.sourceDefaultsApplied` are
  removed entirely — a freshly opened source renders its channel browser
  (metadata/classification) without fetching or drawing any waveform.
- Every analog and digital row starts with `aria-pressed="false"` and
  the pre-existing `.channel-row--hidden` (25% opacity) treatment — the
  same visual state DEC-034/UAT5/UAT8 already used for an explicitly
  hidden channel, not a new state.
- New `groupToggleButtonHtml(kind, groupLabel)` renders a compact
  "Show all"/"Hide all" `<button>` inside each analog and digital
  subgroup's `<summary>` (skipped for an empty group). New
  `wwChannelGroupRows(button)` derives that group's member rows live from
  the DOM (`tr.channel-row--toggle` inside the closest
  `details.channel-subgroup`) — there is no separate group-selection
  state; the button's own label/`aria-pressed` is recomputed by the
  existing `wwSyncChannelBrowserDisplayState()` sync pass, run from every
  mutation point.
- New `wwToggleChannelGroupDisplay(button)` is the batched group
  handler: "Show all" reuses `wwAddSelectedChannels()`/
  `wwAddDigitalChannels()`'s existing batch-safe single-`newPlot`-per-panel
  behaviour (UAT7); "Hide all" uses new `wwRemoveChannelsByKeys()`/
  `wwRemoveDigitalChannelsByKeys()`, which group targeted channels by
  panel and issue exactly one `Plotly.deleteTraces()` per affected panel
  plus one pass of the tail-end refresh functions for the whole batch —
  never N individual per-channel rebuilds. Large groups reuse the
  existing `wwSetWorkspaceLoading`/`wwSetWorkspaceLoadingProgress`/
  `wwYieldToPaint` progress path so the UI stays responsive and truthful.
- The row-toggle click listener checks `.group-toggle-btn` first, calling
  `event.preventDefault()`/`stopPropagation()` before the row-toggle
  check, so clicking the group control never also expands/collapses the
  `<details>` subgroup.
- `#wwEmptyState` copy changed to "Select channels from the sidebar to
  display waveforms." — a guidance message, not an error state.
- `analogMetaFromRow(row)`/`digitalMetaFromRow(row)` extracted (shared by
  the single-row toggles and the new group toggle, removing triplicated
  object-construction code).
- `ww.recordBounds`/viewport establishment inside `wwLoadChannelRange()`
  was deliberately left unchanged — see that function's own comment —
  to avoid conflating this task with the separate COMTRADE
  duration/timing investigation UAT10 later resolved.

### Tests

Existing scratch-convention jsdom suites (`phase4a_check.mjs`,
`phase4a_uat4_check.mjs` through `phase4a_uat8_check.mjs`) were updated:
every test whose actual subject requires channels to already be visible
now calls a `showAllAnalog(window, sourceId)`/`showAllDigital(window,
sourceId)` helper directly (built from that file's own fixtures, calling
`wwAddSelectedChannels`/`wwAddDigitalChannels`) immediately after
`selectSource()`, rather than relying on the old default-display; the
handful of tests originally about default-display-on-open itself were
rewritten to assert the new zero-default policy instead. A dedicated
`phase4a_uat9_check.mjs` covering the group-toggle matrix specifically
was not created as a separate file; its behaviour is exercised inline
across the updated files above (including a large-group, 33-channel
"Loading channels… 33 / 33" progress-batching check in
`phase4a_check.mjs`).

Layering UAT10's `ww.sourceBounds`/`workspaceBounds`/`viewport` rewrite on
top of this change (both landed in the same push) temporarily elevated the
frontend regression count from the established 18-failure baseline to 34;
a follow-up audit found 16 of those were obsolete test expectations from
the bounds rewrite (updated) and one was a genuine bug — `wwClearWorkspace()`
incorrectly clearing `sourceBounds` for a source that was still open — fixed
separately (commit `a0da033`, "fix: preserve source bounds on display
clear"). Frontend suite is back to exactly the established 18-failure
baseline (621 passed); backend 328 passed, no backend file touched by this
phase.

### Decision

Recorded as [DEC-038](DECISIONS.md#dec-038--waveform-channels-default-to-hidden-on-open-group-level-showhide-controls-added-phase-4a-uat9).

## Phase 4A-UAT8 — Digital Channel Row Toggle (2026-08-19)

`[FACT]` throughout. No new DECISIONS.md entry -- a UI-consistency pass
applying the already-approved analog row-toggle interaction model
(UAT5/UAT6) to digital, within already-approved architecture.

### Owner direction

Digital channels should use the SAME direct row-click show/hide model
analog already uses: 100%/25% row opacity, 10px dot, no checkbox, no
separate "selected but not added" state. Remove the sidebar's "Normal
state" column (owner-determined dead weight there). Preserve digital
waveform rendering, Triggered/Never Triggered/Spare classification, and
default-all-on-open exactly as they are -- sidebar interaction only.

### Digital row interaction

`digitalChannelRowAttrs(source, channel, timebase)` (new) mirrors
`analogChannelRowAttrs()` exactly in shape (`class="channel-row--toggle[
channel-row--hidden]"`, `tabindex="0" role="button" aria-pressed`,
`aria-label`/`title` "Hide/Show `<name>`") but carries DIGITAL metadata
(`channelIndex`/`classification`) and a `data-channel-kind="digital"`
marker (analog rows now carry `data-channel-kind="analog"` too, added
purely for this dispatch). `wwToggleDigitalChannelDisplay(row)` (new)
mirrors `wwToggleAnalogChannelDisplay()`, calling the SAME pre-existing
`wwRemoveDigitalChannelByKey()`/`wwAddDigitalChannels()` paths the old
checkbox + "Add selected" used -- no new fetch/cache mechanism, no
second visibility map. A new one-line dispatcher,
`wwToggleChannelRowDisplay(row)`, routes a click/keydown to the correct
kind's own handler by `data-channel-kind` -- the ONLY place analog and
digital interaction logic touches at all; visibility state, fetch path,
and (analog-only) color assignment stay fully separate beyond that
dispatch point.

### Visibility state

No new visibility state introduced -- `ww.digitalDisplayed` (pre-existing
since Phase 4A) was already the global, workspace-scoped digital
visibility authority; `wwIsDigitalChannelVisible(sourceId, channelName)`
(new) is a pure readability wrapper around it, mirroring
`wwIsAnalogChannelVisible()`. `wwSyncChannelBrowserDisplayState()`
(pre-existing) is generalized to dispatch by `data-channel-kind` when
syncing row opacity/`aria-pressed`/label -- now called from
`wwAddDigitalChannels()`, `wwRemoveDigitalChannelByKey()`, and
`wwRemoveChannelsForSource()`'s digital branch (previously analog-only
call sites), so the sidebar reflects digital state changes from EVERY
mutation path -- including the digital waveform region's own pre-existing
"click a lane's baseline trace to remove it" affordance
(`wwRebuildDigitalChart()`'s `plotly_click` handler), which already
called `wwRemoveDigitalChannelByKey()` and now automatically keeps the
sidebar in sync too, with zero changes to that canvas-click code itself.

### Dot

10px, reusing the exact `.channel-color-dot` sizing/shape analog already
established (UAT5) via a shared CSS class -- but with a NEW
`.channel-color-dot--neutral` modifier (`background: var(--text-dim)`,
the same token already used for dimmed/secondary text everywhere in this
file) instead of an inline per-channel color. No `wwColorForChannel()`
involvement anywhere in the digital path -- confirmed by a dedicated
regression test. `--text-dim` is a theme-adaptive CSS custom property
(distinct Light/Dark values), so the dot is readable in both by
construction, not by manual tuning.

### Normal state column removed

`renderDigitalGroup()`'s `renderChannelTable()` call drops the `["Normal
state", (c) => c.normal_state]` column entirely -- digital's own table
is now a single `["Channel", ...]` column (dot + plain name, via new
`digitalChannelNameCellHtml()`), matching the preferred compact structure
from the owner's own task text. UI-only removal: `chan.normal_state` is
still fetched from the backend, still flows into `ww.digitalDisplayed`
entries (`normalState`), and is still used exactly as before wherever
digital rendering itself needs it (HIGH/LOW baseline logic) -- nothing
about the domain model, API response, or `renderDigitalGroup()`'s own
`channels` argument shape changed.

### Selection workflow removed entirely

With digital now also a direct row toggle, the shared "Add N
selected"/"Clear selection" workflow had no remaining checkbox-driven
consumer of any kind -- removed completely, not merely simplified
further: `selectedDigitalChannels` Map, `channelSelectionKey()`,
`digitalChannelCheckboxHtml()`, the `.selection-row` HTML block (and its
now-dead `.selection-row`/`.channel-select-cb`/`td.select-col` CSS), and
`setupSelectionControls()`'s checkbox `change` listener + `addBtn`/
`clearBtn` handlers are ALL deleted. `setupSelectionControls()` itself
was renamed to `setupChannelRowToggles()` (it now does exactly one
thing: wire the shared delegated click/keydown listeners for every
channel row, analog and digital alike) and takes no parameter (the
`source` argument it used to receive was already unused before this
phase). A stale `#wwEmptyState` message ("Select channels and click
'Add selected'...") was also caught and corrected to describe the
current row-click model -- the one piece of USER-FACING copy that had
gone stale, found by grepping the whole file for "Add selected"
afterward; several purely-internal comments referencing the old
mechanism by name were updated too, for the same reason.

### Classification / source identity / analog preservation

`DIGITAL_GROUP_LABELS`/`DIGITAL_GROUP_ORDER`/`wwDigitalSortChannels()`/
classification precedence (Spare wins on name match, even if the signal
went HIGH) are completely untouched -- confirmed by dedicated tests
(hiding a Triggered/Spare channel leaves it in its own subgroup with its
own count badge unchanged). `wwChannelKey(sourceId, channelName)` remains
the identity for `ww.digitalDisplayed`, confirmed source-isolated (two
sources sharing a digital channel name stay independent). Every UAT5/
UAT6/UAT7 analog guarantee (row toggle, 10px trace-colored dot, Name
(unit), global visibility across Grouped/Separate/Custom, Separate's
local lane label/`x`, stable color, no duplicate traces) reconfirmed
passing unchanged by the full existing regression suite.

### Tests

New dedicated `phase4a_uat8_check.mjs` (scratch convention, not
committed, 15 checks): structure (1-column table, no checkbox, 10px
neutral dot with no inline style, focusable/role=button, no Add-selected/
Clear-selection anywhere); toggle (default-all-visible on open, click
hides with the digital chart's own trace count dropping by exactly one,
click again restores it with no duplicate lane, Enter/Space keyboard
parity, re-show issues exactly one batched fetch -- same as the old
checkbox+Add-selected path, no cache redesign); persistence (hidden
channel survives a full Grouped->Separate->Custom->Absolute/Elapsed->
Recordings/Waveform round trip; analog layout switches alone never touch
`ww.digitalDisplayed`); classification (hidden Triggered/Spare channels
stay in their own subgroup, count badges unaffected by visibility);
source isolation. Existing suites required targeted updates for the
same reason UAT5's own analog checkbox removal did the first time:
several pre-existing tests asserted "digital keeps its checkbox" as an
explicit isolation guarantee for THAT phase's own scope --
`phase2ca_check.mjs`, `phase3buat8_check.mjs`, `phase4a_check.mjs`
(a column-position selector broke once the checkbox column disappeared,
fixed to read `row.dataset.channelName` directly instead),
`phase4a_uat4_check.mjs`, `phase4a_uat5_check.mjs`,
`phase4a_uat6_check.mjs` were each updated in place to verify the
CURRENT, still-true invariant (digital and analog visibility state stay
fully independent) via the new row-toggle mechanism, rather than left
describing removed behavior. Every correction was verified to genuinely
reflect intentional behavior change (not mask a new regression). Full
existing frontend regression suite: still exactly the established
18-failure baseline. Backend: 321/321 unchanged (no backend file
touched).

### Files changed

`frontend/index.html` only.

### Honest limitations

No real browser is available in this sandbox -- the actual visual
confirmation (neutral dot legibility/contrast against the analog color
dots in both themes, the 25%/55% hidden-row opacity read for digital
rows specifically) was reasoned through and structurally exercised via
jsdom, but not visually confirmed -- flagged for owner UAT.

---

## Phase 4A-UAT7 — Fix Duplicate Analog Trace Rendering (2026-08-19)

`[FACT]` throughout, resolving the out-of-scope defect DEC-035 flagged
and deliberately did not fix. No new DECISIONS.md entry — a rendering-
layer correction within DEC-035's own already-approved scope; DEC-035
itself was updated in place with the confirmed resolution.

### Owner direction

Fix the duplicate-analog-trace defect DEC-035 discovered and
deliberately left unfixed during Phase 4A-UAT6. Narrowly scoped:
duplicate trace REMOVAL only — no channel-visibility, layout-mode, or
digital-rendering redesign.

### Reproduction

A dedicated jsdom repro (new empty Grouped panel, `wwAddSelectedChannels()`
called ONCE with A/B/C) against code exactly as DEC-035 left it: the
panel's real Plotly-tracked trace list came back as `A, B, C, B, C` (5
entries, not 3) — B and C each doubled. The SAME batch's waveform
network requests were confirmed to be exactly 3 (one per channel) —
proving the duplication was purely a rendering artifact, never a
duplicate fetch. Also confirmed via the broader matrix (see Tests
below): Separate mode was NOT affected (already one trace per lane,
confirmed both before and after); default-display-on-open (5 channels,
2 groups) was affected exactly the same way as any other multi-channel
batch.

### Root cause

`wwAddSelectedChannels()`'s per-meta loop pushes every new channel into
`panel.channels` unconditionally (regardless of which meta happened to
create the panel object), so by the time the function's SECOND phase
runs, a brand-new panel's `panel.channels` already holds its COMPLETE
final channel set. `wwInitPanelPlot()` (called once per entry in
`newlyCreatedPanels`) therefore already draws that complete set in a
single `Plotly.newPlot()` call. The bug: the function's own SECOND loop
— meant to handle channels joining a panel that already existed BEFORE
this call — used a per-meta `isNewPanel` flag computed as "was a panel
object already present in `ww.panels` at the exact moment this meta was
processed." For the 2nd, 3rd, ... Nth channel destined for a panel an
EARLIER meta in the SAME batch had just created, that flag incorrectly
read `false` (the panel object WAS already present — just moments
earlier, within this identical call) — so those channels also received
an incremental `Plotly.addTraces()` call, redrawing them on top of what
`newPlot()` had already drawn. `wwRebuildLayout()` (used for every
layout-mode switch and Custom Groups Apply) was never affected — it has
no such split ownership, only a single `wwInitPanelPlot()` call per
panel, always drawing that panel's complete, final channel list.

### Fix — one unambiguous trace-ownership path

The smallest change consistent with the existing architecture: the
second loop's gating condition changed from the per-meta `isNewPanel`
flag (removed entirely — no longer meaningful) to membership in
`newlyCreatedPanels` itself (already correctly built, just not
consulted at the right point). A channel's panel being in
`newlyCreatedPanels` now unambiguously means "already fully drawn by
`wwInitPanelPlot()` above, in this exact call" — skip the incremental
add. A channel's panel NOT being in `newlyCreatedPanels` means "this
panel existed before this batch call" — it still correctly receives
exactly one incremental `Plotly.addTraces()` call. The two ownership
paths (Option A: new-panel creation owns its complete trace set; Option
B: incremental add owns pre-existing-panel additions) can no longer
both draw the same channel, by construction.

### Verification helper

Every built trace (`wwBuildTrace()`) now carries a `meta:
wwChannelKey(sourceId, channelName)` field — Plotly's own documented,
purely-informational trace property (never consulted by Plotly for
rendering), giving a stable per-channel identity to verify against
directly, rather than proxying through the display `name` (which two
different sources can legitimately share — DEC-035's own
source-isolation requirement). A new on-demand console diagnostic,
`wwDiagnoseDuplicateAnalogTraces()`, reads every rendered panel's REAL
`chartEl.data` (Plotly's own live trace array) via that `meta` field and
reports any channel appearing more than once in the same panel —
mirrors the established `wwDiagnoseDigitalAlignment()` pattern (Phase
4A-UAT2) for a sandbox with no real browser available to this agent;
never called automatically, no production logging.

### Grouped

Full A-E matrix verified: new panel + 1 channel → 1 trace; new panel +
N channels in one batch → exactly N traces (the key regression, 3-of-3
not 3-of-5); existing panel + 1 → +1; existing panel + N in one batch →
exactly +N; hide then re-enable → exactly one trace (not zero, not two).

### Custom

Verified: a brand-new Custom group populated with multiple members in
one batch (via the group editor's Apply → `wwRebuildLayout()` path,
which was never affected by this bug in the first place, confirmed
directly); an existing Custom group receiving more members via a second
Apply; a hidden Custom-group member re-enabled via the sidebar rejoining
its group without a duplicate. Custom Group membership (DEC-035)
remains fully independent of visibility — untouched by this phase.

### Separate

Confirmed unaffected both before and after this fix — one channel = one
lane = one Plotly instance = one trace, structurally incapable of the
multi-channel-batch-into-one-panel scenario this bug required (Separate
panels only ever hold exactly one channel each). Left completely
untouched, per the owner's own "if Separate is not affected, preserve
it untouched" instruction.

### Default-all source open

Verified directly: opening a fresh 5-analog-channel source produces
`ww.displayed.size === 5` and exactly 5 unique rendered trace keys
across the whole workspace (2 panels: Voltage with 4, Current with 1) —
no duplicates, matching one-for-one.

### Network/render impact

No duplicate network requests were ever occurring — confirmed via the
key-regression repro (3 channels, exactly 3 waveform fetches, both
before and after this fix) and via the broader matrix. The fix
eliminates the EXTRA, duplicate `Plotly.addTraces()` calls and the
resulting doubled trace objects (structurally: fewer Plotly operations,
smaller in-memory trace arrays per multi-channel panel) — a real,
measurable reduction in rendering work for any multi-channel
default-display-on-open or multi-channel Add, though actual browser
paint/responsiveness cannot be measured in this sandbox (no real browser
available) and is flagged for owner UAT.

### State preservation

`wwColorForChannel()` untouched and reused unchanged — verified a
channel's Plotly trace color still exactly matches its sidebar dot after
this fix. Global visibility (DEC-035, `ww.displayed`) unaffected —
verified hide-in-Grouped → stays hidden in Separate/Custom → re-enable
→ exactly one trace, end to end. Custom Group membership (DEC-035)
independent of visibility, unaffected. Sidebar/legend state (UAT5/UAT6:
10px dot, row toggle, 100%/25% opacity, Name (unit), no analog checkbox,
no sidebar remove control, Grouped/Custom no duplicate chip legend,
Separate local lane label/remove retained) — none of these surfaces were
touched by this change; no regression expected or observed in the
existing UAT5/UAT6 test suites (both still pass unchanged).

### Digital preservation

`wwAddDigitalChannels()`/`wwRebuildDigitalChart()` — confirmed, by
direct source inspection, to never call `wwAddTraceToPanel()` and to
have no `newlyCreatedPanels`-style concept at all (one shared Plotly
figure, `Plotly.react()`-based, architecturally distinct since Phase 4A
— DEC-034). Untouched by this phase; a source with digital channels
still renders its digital region correctly.

### Tests

New dedicated `phase4a_uat7_check.mjs` (scratch convention, not
committed, 18 checks): the key regression (new Grouped panel + A/B/C in
one batch → exactly 3 unique traces, zero duplicates, exactly 3 waveform
requests); the full Grouped A-E matrix; Custom (new panel multi-add,
existing panel receiving more members, hidden-member re-enable, group-
editor Apply/rebuild path); Separate (one trace per lane, confirmed
unaffected); default-all-on-open (displayed count == unique trace
count); source isolation (two sources sharing a channel name remain two
distinct trace identities); DEC-035 global-visibility non-regression
(hide/switch-modes/re-enable → exactly one trace); color-mapping
non-regression (trace color == sidebar dot color); digital isolation (2
checks); the new `wwDiagnoseDuplicateAnalogTraces()` diagnostic itself.
**Confirmed as a genuine regression guard**: 14 of these 18 checks fail
against the code exactly as DEC-035/Phase 4A-UAT6 left it, and all 18
pass after this fix (the other 4 — Separate mode and digital isolation —
correctly pass either way, since those paths were never affected).

Full existing frontend regression suite: still exactly the established
18-failure baseline (independently reconfirmed, including UAT5/UAT6's
own dedicated suites passing unchanged). Backend: 321/321 unchanged (no
backend file touched).

### Files changed

`frontend/index.html` only.

### Honest limitations

No real browser is available in this sandbox — the actual visual
confirmation (no doubled/thicker traces, responsiveness improvement on
a large real recording) was reasoned through and structurally exercised
via jsdom (trace-count/identity assertions, request-count assertions),
but not visually or performance-confirmed in a real browser — flagged
for owner UAT.

---

## Phase 4A-UAT6 — Global Analog Channel Visibility Across Layout Modes (2026-08-19)

`[DECISION]` See
[DECISIONS.md — DEC-035](DECISIONS.md#dec-035--analog-channel-visibility-is-workspace-global-layout-mode-governs-arrangement-only-never-visibility-phase-4a-uat6):
analog channel visibility is workspace-global across Grouped, Separate,
and Custom; layout mode controls arrangement only, never visibility.
Everything below is `[FACT]` implementation detail of that decision.

### Owner direction

Real-browser UAT observation: hiding an analog channel while in Grouped
mode did not consistently persist when switching to Separate or Custom
(the channel could reappear). Required rule: `ww.displayed` (channel
visibility) is the ONE global authority; layout mode is a pure
presentation/arrangement derivation from it, never a second source of
truth. Diagnose the exact state duplication, fix it, and add permanent
cross-mode tests.

### Root cause

Two investigation paths, one dead end and one real bug:

- **The simple flow (hide in Grouped → switch layout) was NOT actually
  broken.** `wwRebuildLayout()` (pre-existing since Phase 2C-B1) already
  derives every layout's panels from `Array.from(ww.displayed.values())`
  fresh on every call — there was never a second Grouped/Separate/Custom
  visible-state to fall out of sync. A dedicated jsdom reproduction of
  the owner's own literal example (hide B in Grouped → Separate → Custom
  → back to Grouped) was written FIRST, against the pre-UAT6 code, and
  it already passed — confirming this path was architecturally sound
  before any fix was applied.
- **The real, concrete, reproducible bug: the Custom Groups editor.**
  `wwOpenGroupEditor()` seeded its working copy via
  `group.channelKeys.filter((key) => displayedKeys.has(key))` —
  filtering OUT any group member that happened to be hidden at the
  moment the editor was opened. `wwApplyGroupEditor()` then committed
  that FILTERED copy straight back into `ww.customGroups`, permanently
  losing the hidden member's group assignment. Reproduced directly: add
  A/B/C to a Custom Group → hide B → open + Apply the editor without
  touching anything → `ww.customGroups` silently drops `B` → re-enabling
  B afterward puts it in its own auto-solo panel instead of rejoining
  the group. This is exactly "group membership != visibility" being
  violated by treating "currently invisible" as "currently unassigned."
  Plausibly the actual mechanism behind at least some of what the owner
  observed as "Custom doesn't consistently respect hidden state."

### Global visibility authority

No new state introduced for visibility itself — `ww.displayed` already
was, and remains, the one global authority (confirmed correct by the
root-cause investigation above). A new `wwIsAnalogChannelVisible(sourceId,
channelName)` helper wraps the existing `ww.displayed.has(wwChannelKey(...))`
check purely for readability/intent at call sites
(`analogChannelRowAttrs()`, `wwSyncChannelBrowserDisplayState()`) — pure
refactor, zero behavior change.

### Grouped / Separate / Custom

All three already deriving from `wwPanelGroupKeyFor()` intersecting
`ww.displayed` with that mode's own grouping rule — unchanged by this
phase, confirmed correct by tests. Separate mode's own local lane `x`
was already routing through `wwRemoveChannelByKey()` (the same global
removal path the sidebar uses) since it was introduced in Phase 2C-B1 —
already satisfied "Separate's local x updates global visibility" before
this phase; verified, not newly implemented.

### Custom Group membership survives hide/re-enable

`wwOpenGroupEditor()` no longer filters `channelKeys` to displayed-only
at open time — the full membership is preserved in the working copy
regardless of a member's current visibility. New `ww.channelMeta: Map<
"sourceId::channelName", {sourceId, sourceName, channelName, unit,
engineeringType}>` (same lifecycle as `ww.channelColors`/
`ww.customGroups`/`ww.panelHeights` — populated on every add in
`wwAddSelectedChannels()`, never deleted by hide/remove, cleared only by
`wwClearWorkspace()`) lets `wwRenderGroupEditor()`'s group-card chip loop
describe a hidden member's name/unit/color without needing it in
`ww.displayed` — reads `ww.channelMeta`/`wwColorForChannel()` instead of
`ww.displayed.get(key)`, which would have silently skipped rendering that
chip entirely. A hidden member's chip renders with a new
`.group-chip--hidden` class (opacity 0.5, `title="Hidden -- not
currently displayed"`) — a visual cue, per the owner's own "optionally
show hidden state subtly... but do not expand scope" guidance, not a new
interaction. The "Unassigned" picker itself remains scoped to
currently-displayed channels only (unchanged, out of scope to expand).

### Re-enable behavior

Clicking a hidden row (or the Separate lane's own local `x`, or any
future control built on the same primitives) calls the SAME
`wwAddSelectedChannels()`/`wwRemoveChannelByKey()` paths as before —
`wwColorForChannel()` is untouched and reused unchanged, so color never
resets on hide/re-enable/layout-switch. Because `wwPanelGroupKeyFor()`
already looks up `wwCustomGroupFor()` fresh from the current
`ww.customGroups` on every call, and that data is no longer pruned by
the editor, a re-enabled channel automatically rejoins its ORIGINAL
Custom Group with zero additional code — this "just works" once the
editor stopped corrupting the underlying membership data.

### A separately discovered, out-of-scope bug (not fixed here)

While writing cross-mode tests, a genuine, unrelated, pre-existing
rendering bug surfaced: `wwAddSelectedChannels()` can double-invoke
`Plotly.addTraces()` for the 2nd..Nth channel of a brand-new panel when
2+ NEW channels destined for the same group are added in a single batch
call (`isNewPanel` is computed per-meta WITHIN that same loop, so a
panel created moments earlier by an earlier meta in the SAME batch looks
"pre-existing" to every later meta that joins it) — the most common
real-world trigger being default-display-on-open for a source whose
first-ever-displayed engineering-type group has 2+ channels. Confirmed
via a dedicated jsdom reproduction (a fresh source open showed 7
tracked Plotly calls for a 4-channel Voltage group, not 4). This is
unrelated to visibility state and out of scope for this phase (a
rendering-duplication concern, not a state-duplication one) — flagged
for the owner per this project's own change-governance process rather
than fixed here. This project's own test suite's assertions were
adjusted to check ground-truth `ww.displayed`/`panel.channels` rather
than the affected Plotly-call-derived counts, so this phase's own
cross-mode correctness claims do not depend on that separate bug being
fixed.

### Tests

New dedicated `phase4a_uat6_check.mjs` (scratch convention, not
committed, 13 checks): A. Grouped hide propagates to Separate/Custom;
B. Separate's local `x` hide propagates globally (Grouped/Custom too);
C. hiding from the sidebar while Custom is active propagates back to
Grouped/Separate; D. re-enabling from the sidebar restores the channel
in every layout; E. Custom Group membership survives hide, survives an
editor open+Apply cycle while hidden, and a re-enabled member rejoins
its original group (not auto-solo) — plus the editor's own chip list
still rendering a hidden member, dimmed; F. color identity stable
through hide/re-enable/every layout switch; state persistence across
Grouped→Separate→Custom→Absolute/Elapsed→Recordings→Waveform; source
isolation (hiding `src1::A` never touches `src2::A`); digital isolation
(digital's checkbox/selection workflow provably untouched). Full
existing frontend regression suite: still exactly the established
18-failure baseline (independently reconfirmed). Backend: 321/321
unchanged (no backend file touched).

### Files changed

`frontend/index.html` only.

### Honest limitations

No real browser is available in this sandbox — the actual visual
correctness (hidden-chip dimming legibility, the owner's original
real-browser reproduction sequence) was reasoned through and
structurally exercised via jsdom, but not visually confirmed — flagged
for owner UAT. The separately-discovered double-`addTraces` bug (see
above) was deliberately NOT fixed in this pass; it remains present in
the shipped app and should be evaluated as its own, separate task.

---

## Phase 4A-UAT5 — Simplify Analog Channel Toggle Rows (2026-08-18)

`[FACT]` throughout. No new DECISIONS.md entry -- a UX simplification of
the analog sidebar row's own interaction model within already-approved
architecture, not a new architectural commitment.

### Owner direction

Increase the analog color dot from 7px to 10px; dim the ENTIRE row (not
only the dot) to 25% opacity when a channel is not displayed; remove
both the analog checkbox and the sidebar remove button, replacing them
with direct row-click-to-toggle display; combine Name + Unit into one
"Channel" column (e.g. "GT4 VB (kV)", omitting empty parens when unit is
missing), removing the Unit column entirely; analog checkbox selection
state is removed outright -- "Add N selected"/"Clear selection" now
refer to DIGITAL selection only; preserve default-all-display-on-open
and hide/show persistence across ordinary navigation; reuse
`wwColorForChannel()` unchanged (no new color logic); do not redesign
Separate mode (its existing local lane label/dot/remove `x` stays
exactly as UAT4 left it) or digital's checkbox/selection workflow.

### Row-as-toggle (replaces checkbox + sidebar remove button)

`analogChannelRowAttrs(source, channel, timebase)` (new) builds the
extra attributes spliced onto the analog `<tr>` itself --
`class="channel-row--toggle[ channel-row--hidden]"`, `tabindex="0"
role="button" aria-pressed`, plus the same `data-*` channel-identity
fields the old checkbox used to carry (`unit`, `engineering-type`,
`recording-start-time`, `timing-reference`) so no metadata is lost.
Mirrors the pre-existing `table.recordings tr[data-source-id]`
row-as-button pattern rather than inventing a new interaction
primitive. `renderChannelTable()` gained an opt-in `rowAttrsFn(channel)`
parameter for this -- digital's own call site never passes it, so
digital rows are structurally unaffected.

`wwToggleAnalogChannelDisplay(row)` (new) reads the row's own `data-*`
fields and calls the SAME pre-existing `wwRemoveChannelByKey()` /
`wwAddSelectedChannels()` paths the old checkbox + button used --
section 9's "no second active/inactive map, no new color logic" is
satisfied by construction (`wwAddSelectedChannels` already calls
`wwColorForChannel()` internally). Wired via delegated `click` and
`keydown` (Enter and Space, mirroring the existing recordings-row
keyboard pattern) listeners on `#channelGroups` in
`setupSelectionControls()`, scoped to `tr.channel-row--toggle` so
digital rows (which never carry that class) can never be affected.

`wwSyncChannelBrowserDisplayState()` reworked to iterate
`tr.channel-row--toggle` elements (previously `.channel-name-cell`),
toggling the `channel-row--hidden` class, `aria-pressed`, and a
`title`/`aria-label` of "Hide `<name>`" / "Show `<name>`" -- called from
the same mutation points as before (`wwAddSelectedChannels`,
`wwRemoveChannel`, `wwClearWorkspace`, and unconditionally after
`renderChannels()` in `selectSource()`).

### Name/Unit consolidation

`analogChannelNameCellHtml(source, channel)` reworked: renders only the
10px color dot + one combined text label (`"name (unit)"`, or bare
`name` when unit is empty/missing) -- no more `data-*` attributes or
remove-button markup on this cell (both moved to the row, see above).
`renderAnalogGroup()`'s columns dropped from `[Name, Unit, Phase]` to
`[Channel, Phase]`; the analog `renderChannelTable()` call now passes
`checkboxColumn: null` (no checkbox) and the new `rowAttrsFn`.
`channelCheckboxHtml()` and the `selectedChannels` Map were deleted
entirely -- there is nothing left in the DOM for an analog `change`
event to populate. `digitalChannelCheckboxHtml()`/
`selectedDigitalChannels` are completely untouched.

### Selection controls: digital-only now

`setupSelectionControls()`'s `change` listener no longer branches on
`channel-kind` (every remaining `.channel-select-cb` is digital's own);
`syncButtons()` now counts `selectedDigitalChannels.size` only;
`addBtn`/`clearBtn` handlers touch only `selectedDigitalChannels`/
`wwAddDigitalChannels`. Button TEXT is unchanged ("Add N selected"/
"Clear selection") -- still truthful, since N can now only ever reflect
a digital selection; no UI copy change was made to avoid introducing
new strings for a count that was already exclusively meaningful once
analog's own contribution became structurally impossible. The delegated
`.channel-remove-btn` click listener was removed (that button no longer
exists for analog; digital never used it).

### CSS

`.channel-color-dot`: 7px -> 10px. New `.channel-row--toggle` (cursor:
pointer, `:hover td` background tint via `var(--hover-tint)`,
`:focus-visible` outline matching the recordings-row pattern). New
`.channel-row--hidden` (opacity 0.25; `:hover`/`:focus-visible` raise it
to 0.55 so a hidden row stays discoverable without ever reading as
"displayed" -- owner's explicit 45-60% guidance). Removed entirely:
`.channel-color-dot--dim` (dimming is now row-level) and
`.channel-remove-btn`/`:hover`/`[hidden]` (control is gone for analog).

### Layout modes

Grouped/Custom: unchanged behavior from UAT4 (sidebar is the legend, no
canvas chip strip, group headings remain) -- only the row's own
interaction model changed. Separate mode: `wwRenderLegend()`, every
`.ww-legend*` CSS rule, and the Separate-mode overlay overrides are
completely untouched -- verified by a dedicated coexistence test (the
sidebar row toggle and the Separate lane's own local `x` both read/
write the same `ww.displayed` state without corruption, in either
order). Digital: `renderDigitalGroup()`/`digitalChannelCheckboxHtml()`/
`selectedDigitalChannels`/the digital `change`-listener branch are all
byte-for-byte unaffected; a dedicated test confirms digital rows never
receive the `channel-row--toggle` class.

### Tests

New dedicated `phase4a_uat5_check.mjs` (scratch convention, not
committed, 21 checks): row structure (2-column table, no checkbox, no
"Waveform (UAT)", no sidebar remove button, 10px dot, Name+Unit
combined with correct empty-unit handling, group headings preserved);
row-click display state (default-all-on-open, click-to-hide drops the
trace + dims the row + `aria-pressed=false`, click-to-show restores it,
color identity stable across the toggle, hide state persists across a
Recordings<->Waveform navigation round trip); keyboard accessibility
(focusable, `role="button"`, Enter and Space both toggle,
`aria-label`/`title` flip Hide<->Show, `:focus-visible` CSS exists);
digital isolation (checkbox/Add-selected/Clear-selection workflow fully
intact, clicking analog rows never changes the digital-only count,
digital's checkbox template never calls the analog color authority,
digital rows never carry `channel-row--toggle`); Separate-mode
coexistence (existing lane chip unchanged; sidebar toggle and the
lane's own local remove both correctly read/write `ww.displayed`).

`phase4a_uat4_check.mjs` (UAT4's own dedicated suite) was updated in
place rather than left describing removed behavior: its `dotFor()`
helper now reads the color dot via the new `tr.channel-row--toggle`
identity instead of the retired `.channel-name-cell` data attributes;
its own checkbox/remove-button-specific checks were rewritten to use
row clicks; its "4 columns"/"6-9px dot" assertions were updated to the
new 2-column/10px reality. All of UAT4's still-applicable coverage
(color authority stability, Grouped/Custom legend removal, Separate
mode's unchanged chip, digital isolation) re-verified passing
unchanged. `phase2ca_check.mjs` (the oldest checkbox-driven analog
selection suite), `phase3a_check.mjs`, and `phase3buat8_check.mjs` each
had their own analog-checkbox-specific assertions rewritten to the
row-click model for the same reason; every correction was verified, via
the established stash-and-rerun-against-canonical-`main` technique, to
be describing a genuinely CHANGED behavior rather than masking a new
regression. Full existing frontend regression suite: still exactly the
established 18-failure baseline (17 pre-existing + 1 pre-existing
button-size-tier issue), independently reconfirmed against pre-UAT5
`main` (`d16fb91`) file-by-file. Backend: 321/321, unchanged (no backend
file touched this pass).

### Files changed

`frontend/index.html` only.

### A note on how this landed in Git history

This is a shared local clone (see [README.md](README.md) on why GitHub,
not any one local working copy, is canonical): while this phase's edits
were still in progress and unreviewed, a concurrent session on the same
machine committed and pushed the in-progress working tree twice, under
the commit messages **"adjusting padding"** (`e51b647`, `be201d3`) --
each swept up this phase's own CSS/JS edits alongside a few small,
unrelated spacing tweaks (`.shell-view-placeholder` padding,
`.ww-panel`/`#wwDigitalRegion` margin-bottom, `#wwDigitalScroll`
max-height) made by that other session. The resulting `HEAD` was
verified, edit-by-edit, against this phase's own intended diff (syntax
check, full regression suite, and a line-level diff against `d16fb91`)
before this record was written -- nothing was lost or corrupted, but
the commit messages on `origin/main` do **not** describe this phase's
actual change. This document is the authoritative record of what
`e51b647`/`be201d3` actually contain; no history rewrite (amend/rebase/
force-push) was performed, per this project's own git safety rules.

### Honest limitations

No real browser is available in this sandbox -- the actual rendered
appearance (10px dot legibility, the row hover/focus tint, the 25%/55%
hidden-row opacity reading as "clearly hidden but discoverable", keyboard
focus ring visibility) was reasoned through and structurally exercised
via jsdom, but not visually confirmed -- flagged for owner UAT.

---

## Phase 4A-UAT4 — Channel Sidebar as Analog Legend (2026-08-18)

`[FACT]` throughout. No new DECISIONS.md entry -- a UX consolidation
(one legend authority instead of two duplicated ones) within already-
approved architecture, not a new architectural commitment.

### Owner direction

Remove the obsolete "Waveform (UAT)" per-channel control; remove the
duplicated analog waveform legend/chip strip above the canvas; use the
existing Channels sidebar as the analog waveform legend instead (a small
color dot beside each channel name, driven by the exact same color the
Plotly trace uses); preserve all existing selection/display/removal
behavior.

**Mid-task owner clarification** (received after the initial Grouped/
Custom/Separate-uniform removal was already implemented and tested):
the chip-strip removal applies to **Grouped and Custom modes only**.
**Separate mode's existing per-lane legend chip (color dot, name/unit,
overlay position, remove control) is explicitly preserved unchanged** --
one lane = one channel there, so the local label is not the same kind
of duplication a multi-channel Grouped/Custom panel's chip strip was.
The implementation below reflects the corrected, final behavior; the
initial uniform-removal attempt (which briefly moved Separate mode's
identity onto `.ww-panel-header` instead) was reverted before this
record was written.

### Color authority (the one thing every other change here depends on)

New `ww.channelColors: Map<"sourceId::channelName", color>` and
`wwColorForChannel(sourceId, channelName)` -- the ONE color authority
both the Plotly trace (`wwAddSelectedChannels`'s `channelEntry.color`)
and the Channels sidebar's color dot
(`analogChannelNameCellHtml()`) read from; never a second,
independently-assigned sidebar color. Assigns a fresh palette color
(the pre-existing `wwNextColor()`) the FIRST time a given channel
identity (the same `wwChannelKey()` `"sourceId::channelName"`
convention used everywhere else in this codebase -- two sources with an
identically-named channel never collide) is ever seen, and reuses that
SAME color on every later lookup -- including after the channel is
removed and re-added. Same lifecycle policy as the pre-existing
`ww.customGroups`/`ww.panelHeights`: individual channel/source removal
deliberately leaves it alone, only `wwClearWorkspace()` clears it (a
brand-new workspace has no color history to remember). Colors are
pre-assigned for EVERY analog channel at channel-LIST-render time (not
lazily only once displayed), so a not-yet-displayed row still shows the
real color it will use if re-added (owner's own explicit requirement).

### Channel sidebar legend (Grouped/Custom)

`analogChannelNameCellHtml(source, channel)` replaces the plain-text
"Name" column accessor with a small raw-HTML cell:
`<dot> <name> <remove-button-if-currently-displayed>`, reusing the
existing "Name" column (`renderChannelTable()` gained an opt-in `{raw:
true}` column flag for this, since its own auto-escaping is otherwise
still the default for every other column, digital included). This
directly replaces the freed "Waveform (UAT)" action-column slot (never
a 5th column). The dot is `aria-hidden` (a color->identity mapping aid,
not new information; the channel name text remains the real accessible
label). Compact (7px diameter, matching section 18's 6-9px preference),
a subtle theme-token border for contrast in both Light/Dark without
altering the trace color itself.

**Displayed vs not-displayed**: `.channel-color-dot--dim` (35% opacity,
toggled, never baked into the stored color) for a channel not currently
displayed -- the real color stays visible, never removed entirely
(owner's own explicit requirement, section 8). `wwSyncChannelBrowserDisplayState()`
(new) does a lightweight DOM pass over already-rendered
`.channel-name-cell` elements, toggling the dot's dimmed class and the
remove button's `hidden` state from `ww.displayed` -- called from every
mutation point (`wwAddSelectedChannels`, `wwRemoveChannel`,
`wwClearWorkspace`, and unconditionally after `renderChannels()` in
`selectSource()` to cover re-opening an already-open source, whose
default-display branch is skipped and would otherwise leave the
sidebar showing stale "not displayed" state for channels that actually
already are). Checkbox-checked state (queued for "Add selected") and
displayed state are explicitly kept distinct, per the owner's own
section 9 -- merely checking a box never dims/undims a dot.

**Removal**: a `.channel-remove-btn` (visually identical to the
existing `.ww-legend-remove` chip button, just relocated/duplicated
into the sidebar row) is Grouped/Custom's ONLY removal affordance now
(they have no canvas-side chip anymore); wired via one delegated click
listener on `#channelGroups` (same technique the existing checkbox
`change` listener already used), calling the SAME pre-existing
`wwRemoveChannelByKey()` -- no new removal mechanism.

### Canvas legend removal (Grouped/Custom only)

`wwRenderLegend()` (pre-existing, unchanged in its own implementation)
is now called ONLY when `ww.layoutMode === "separate"` -- from
`wwAddSelectedChannels()` and `wwRebuildLayout()` (the two call sites
where Grouped/Custom panels could otherwise still have received a
freshly-rendered chip). `wwRemoveChannel()`'s own former
"panel still has channels, re-render its legend" branch was removed
entirely: Separate panels always hold exactly one channel (removing it
always empties the whole panel, never hits that branch), and Grouped/
Custom never show the chip at all now, so the branch was dead code for
both cases. Group/custom-group HEADINGS ("Voltage", "Current", "Group
1") are unaffected -- those come from `.ww-panel-label`/
`wwPanelLabelFor()`, a completely separate mechanism never touched.

### Separate mode (unchanged, per the owner's clarification)

`.ww-legend`, `.ww-legend-item`, `.ww-legend-dot`, `.ww-legend-label`,
`.ww-legend-remove`, and their Separate-mode overlay-positioning
overrides (`#wwPanels.ww-panels-unified .ww-legend`, etc., including
the Detego-benchmarked right-side overlay placement from Phase
2C-B3A) are all present in the CSS exactly as before this phase --
zero changes. `panel.legendEl`/`wwRenderLegend()`'s own implementation
are unchanged; only the CALL SITES became conditional on layout mode
(see above).

### Tests

Full existing frontend regression suite required substantial updates
given the scale of this refactor -- several pre-existing tests directly
asserted on `.ww-legend-item` counts inside GROUPED/CUSTOM panels
(`phase2ca_check.mjs`, `phase2cb1_check.mjs`, `phase2cc1_check.mjs`,
`phase2cc2_check.mjs`, `phase3auat3_check.mjs`), which no longer exist
there by design; each was corrected in place to verify the same
underlying fact (channel membership/removal/long-name-containment)
through the channel's own Plotly trace count or the new sidebar
`.channel-name-cell`/`.channel-remove-btn` elements instead, with an
explanatory comment. One cascading failure (`phase2cc2_check.mjs`'s own
custom-group-height-persistence check) resolved automatically once its
own upstream `.ww-legend-item` assertion was fixed (the early throw had
been skipping a resize drag entirely). Every correction was verified,
before being treated as "pre-existing baseline, not to touch," by
stashing this phase's changes and re-running the identical test file
against untouched canonical `main` -- confirming the SAME failures
already existed there, completely unrelated to this phase's own work
(all trace to the pre-existing DEC-030 sticky-ruler relayout-counting
pattern already documented in prior phases' own records).

New dedicated `phase4a_uat4_check.mjs` (scratch convention, not
committed, 21 checks): obsolete-control removal (no "Waveform (UAT)"
text/link anywhere, no leftover 5th column, checkbox/Add-selected
behavior preserved); color mapping (every analog row has a dot, a
displayed channel's dot color exactly equals its own Plotly trace
color, distinct channels get distinct colors, color survives remove +
re-add, color stable across Grouped/Separate/Custom, stable across
Absolute/Elapsed, stable across a Recordings<->Waveform navigation
round trip re-selecting the same open source, two sources with an
identically-named channel get non-colliding colors); displayed-vs-not
dot treatment (dimmed-but-visible, real color never removed, checkbox
state never itself changes dimmed state); waveform legend removal
(Grouped/Custom: zero `.ww-legend-item` chips, group headings remain;
Separate: its existing chip -- dot, name/unit, remove control -- is
verified completely unchanged, per the owner's clarification); removal/
re-add workflow via the sidebar end to end; layout containment (name
ellipsis CSS present, dot diameter within the 6-9px range, digital rows
provably untouched by the new color-authority code).

Full existing frontend regression suite: still exactly the established
18-failure baseline (17 pre-existing + 1 pre-existing-but-newly-
surfaced button-size-tier issue from an external, unrelated commit,
first confirmed in the Phase 4A-UAT3 record). Backend: 321/321,
unchanged (no backend file touched this pass -- pure frontend UX
consolidation).

### Files changed

`frontend/index.html` only.

### Honest limitations

No real browser is available in this sandbox -- the actual rendered
appearance of the color dots (contrast against both themes, compact
sizing as perceived by eye), the freed canvas vertical space "feeling"
noticeably cleaner, and Separate mode's continued visual correctness
were reasoned through and structurally exercised via jsdom, but not
visually confirmed -- flagged for owner UAT.

---

## Phase 4A-UAT3 — Build SHA / Version Provenance (2026-08-18)

`[FACT]` throughout. No new DECISIONS.md entry -- a small, operationally-
focused provenance mechanism reusing the deployment's own already-existing
`APP_VERSION`/`github.sha` value end to end, not a new architectural
commitment.

### Owner requirement

Make it easy to verify exactly which Git commit is currently deployed and
served by DEV/PROD, preventing the specific class of confusion where
GitHub `main` is newer than what a deployment (or a stale browser tab) is
actually running, with no fast way to tell.

### Build identity source of truth

`APP_VERSION` -- already set by `deploy.yml` to `${{ github.sha }}` (the
full 40-character commit SHA) and already used by `scripts/deploy.sh`/
`compose.yaml` to tag the `powerwave-backend`/`powerwave-frontend`
Docker images -- is now ALSO passed straight through as a runtime
environment variable to both running containers. Nothing computes Git
state by executing `git` inside a container; a plain `docker run` or
local `docker compose up` without `deploy.sh` truthfully reports
`"local"` (matching `scripts/deploy.sh`'s own pre-existing
`APP_VERSION="${APP_VERSION:-local}"` fallback convention exactly, not a
new one invented for this feature).

### Backend

- `app/config.py`: `Settings` gained `git_sha: str` and `version: str`.
  `load_settings()` reads `APP_VERSION` from the environment (blank/unset
  -> `"local"`); `version` is simply its short (7-char) form, `"local"`
  passed through unchanged rather than sliced into nonsense.
- `app/main.py`: `GET /health` now returns
  `{"status": "ok", "environment": ..., "version": ..., "git_sha": ...}`.

### Frontend

- `frontend/docker-entrypoint.d/10-powerwave-config.sh` (the SAME
  mechanism that already regenerates `config.js` from `API_BASE_URL` at
  container start, never at Docker build time -- see its own module
  comment) now also writes `environment` and `buildVersion` (from
  `APP_VERSION`, default `"local"`) into `window.POWERWAVE_CONFIG`. The
  checked-in default `frontend/config.js` (used for a bare local
  file-serve with no Docker) mirrors the same shape with
  `buildVersion: "local"`.
- `frontend/index.html`: new `buildVersion()` helper (mirrors
  `apiBaseUrl()`'s own established pattern exactly -- reads
  `window.POWERWAVE_CONFIG.buildVersion`, `"local"` fallback). At Init,
  logs exactly ONE console line --
  `Oruxa Powerwave — <environment> — build <version>` -- and sets
  `document.documentElement.dataset.build` from the same value, so a
  human in DevTools and an audit script
  (`document.documentElement.dataset.build`) always agree, and both
  reflect whatever build the browser ACTUALLY loaded (including a stale
  cached one -- the entire point, per the owner's own explicit
  instruction not to fetch the latest SHA from GitHub at runtime, which
  would hide exactly the problem this feature exists to surface).

### Deployment wiring

`compose.yaml` (the portable base, unchanged for DEV/PROD -- only the
deployment-supplied `APP_VERSION` value differs) now passes
`APP_VERSION: ${APP_VERSION:-local}` into both the `frontend` and
`backend` services' `environment:` blocks, alongside the image-tag usage
that already existed. Frontend and backend therefore always receive the
exact same SHA from the exact same deploy-time value -- never two
separately-maintained version strings.

### Local development fallback

Any container or process started without `APP_VERSION` set (bare
`docker run`, local `docker compose up` without `deploy.sh`, the
checked-in `frontend/config.js` used for a no-Docker file-serve) reports
`"local"` for both `version`/`git_sha` (backend) and `buildVersion`
(frontend) -- never a fabricated commit hash.

### Tests

Backend: `test_config.py` gained a `TestBuildProvenance` class (5 cases
-- full SHA recorded verbatim, short 7-char `version`, blank ->
`"local"`, unset in production too, whitespace stripped);
`test_main.py` gained a build-provenance `/health` case (`test_defaults_are_development`'s
own fallback assertions extended, not duplicated); `test_frontend_entrypoint.py`
gained a `TestBuildProvenance` class (4 cases -- `APP_VERSION` written
verbatim, missing -> `"local"`, `ENVIRONMENT` written, both fields
present). Three pre-existing tests that constructed `Settings(...)`
directly (`test_storage.py`, `test_sources_api.py`) were updated for the
two new required fields -- `test_storage.py`'s own case switched to
`dataclasses.replace(settings, ...)`, more robust against any future
field addition. Backend suite: 321/321 (311 pre-existing + 10 new), zero
regressions.

Frontend: new `phase4a_uat3_check.mjs` (scratch convention, not
committed, 5 checks) -- exactly one startup console message per load
(never spammed), the DOM marker matches the injected config value
exactly, a different injected SHA produces a different marker (never
hardcoded), the truthful `"local"` fallback when no `buildVersion` was
configured at all, and `buildVersion()` itself reads live from
`window.POWERWAVE_CONFIG`. Full existing frontend regression suite
re-run: **18** failures, not the previously-established 17 -- the
extra one (`phase3buat3_check.mjs`'s own button-size-tier assertion) was
independently confirmed, by stashing this phase's own changes and
re-running against untouched canonical `main`, to ALREADY exist there,
introduced by an external "adjusting the header toolbar and button font
size" commit made outside this task's own session -- unrelated to and
not introduced by this phase's own changes, which touch none of that
CSS.

### Files changed

`backend/app/config.py`, `backend/app/main.py`,
`backend/tests/conftest.py`, `backend/tests/test_config.py`,
`backend/tests/test_frontend_entrypoint.py`, `backend/tests/test_main.py`,
`backend/tests/test_sources_api.py`, `backend/tests/test_storage.py`,
`compose.yaml`, `frontend/config.js`,
`frontend/docker-entrypoint.d/10-powerwave-config.sh`,
`frontend/index.html`.

### Honest limitations

No DEV/PROD deployment was dispatched from this sandbox this pass (no
`gh` CLI or token available, consistent with every prior phase in this
session) -- the mechanism is verified structurally (backend unit tests,
frontend jsdom checks, the entrypoint script's own real-`sh` test
harness) but not yet confirmed end-to-end against a real deployed
container. Owner verification (the exact commands below) is the
remaining step.

---

## Phase 4A-UAT2 — Fix Remaining Digital Waveform UAT Failures (2026-08-18)

`[FACT]` throughout. No new DECISIONS.md entry -- root-cause fixes and a
more robust rendering primitive within DEC-034's already-approved
architecture (one shared Plotly figure, batched full-record delivery),
not a new architectural commitment.

### Owner real-browser UAT on the deployed Phase 4A-UAT1B build

**PASS**: digital classification/group ordering (Triggered -> Never
Triggered -> Spare, alphabetical within each) -- preserved unchanged
this pass, not touched.

**FAILED** (owner real-browser observation, authoritative over any
jsdom/source-level check): (1) digital waveform still not visually
time-aligned with analog/shared ruler despite UAT1B's margin.l fix; (2)
loading animation/progress not visible during initial all-channel
loading; (3) digital channel labels not overlaid on the signal lanes,
still read as a separate label column; (4) HIGH state not rendered as an
obvious bold/thick band -- "effectively uniform thin blue lines."

### Root cause investigation (source-level; no real browser available in
this sandbox -- see "Honest limitations" below)

**Failure A (alignment) -- confirmed root cause**:
`wwResizeAllVisiblePlots()` (the established Phase 3A-UAT1 catch-up path
for "Plotly's own `responsive: true` only reliably reacts to actual
`window` resize events, not a container that changed size for another
reason") resized every analog panel and the shared ruler, but was NEVER
updated when Phase 4A introduced the digital chart -- it simply never
existed in that function. This function is called from FIVE real,
everyday interaction paths: Workspace Sidebar drag-resize, Main Sidebar
Menu collapse/expand, actual browser window resize, switching among
Waveform/Table/Split, and (critically) every Recordings -> Waveform
navigation (`shellSetCurrentPage("waveform")`'s own "any width change
that happened while away" catch-up). Any one of these leaves the digital
chart's rendered Plotly SVG stale at its old width while analog/ruler
correctly redraw at the new one -- a structural cause of misalignment
independent of the margin VALUES themselves (UAT1B's own fix), matching
the task's own explicit warning not to assume equal `margin.l` implies
equal rendered alignment. A second, smaller gap: `#wwDigitalChart` (unlike
`.ww-chart`/`.ww-sticky-ruler-chart`) never had an explicit CSS
`width: 100%` rule, silently relying on default block-level sizing
inside a scrolling parent -- a less certain layout context than the
other two surfaces' own explicit declarations.

**Failure B (loader invisible) -- confirmed root cause**: this project's
own Phase 2C-C2A investigation already documented the exact underlying
mechanism -- "the browser cannot paint a new [DOM state] until the
CURRENT synchronous unit of work returns control." `wwSetWorkspaceLoading(true,
...)`'s DOM write is not itself a guarantee the browser painted it; on a
fast local/DEV connection, the gap between "loader shown" and the next
heavy synchronous block (channel-browser HTML, `wwApplyDefaultChannelDisplay`)
can be too short for the browser to actually rasterize an intermediate
frame, even across a real `await fetch()`. A second, independent
contributor: `openRecordingForAnalysis(sourceId)` called
`selectSource(sourceId)` (whose very first statement shows the loader)
BEFORE `shellSetCurrentPage("waveform")` (which un-hides the loader's
own ancestor container, `#workspaceRow`) -- ordering that, even though
it did not ultimately block the eventual paint once traced through
carefully, left avoidable ambiguity about a hidden-ancestor state.

**Failure C (labels not overlaid) -- confirmed contributing bug**: the
label annotation's `y`/`yanchor` (`y: y + 0.32, yanchor: "bottom"`)
anchored the label's bottom edge ABOVE the trace's own Y, placing label
and trace in two visually distinct vertical bands within the same lane
instead of genuinely overlapping -- close enough to still read as
"attached to this lane" in isolation, but not the "sits ON TOP OF /
INSIDE the lane" treatment the owner's reference image shows, especially
compounded by Failures A/B making the whole composition look
disconnected.

**Failure D (HIGH band not visible) -- investigated exhaustively,
no logic bug found; root cause presumed to be a real-browser Plotly.js
rendering behavior this sandbox cannot reproduce**: `wwDigitalHighIntervals()`
and the band-trace-building code were re-audited line by line (interval
generation, state tracking, `null`-gap segmentation, trace ordering,
line width 7 vs 1, hover config, `colors.accent` resolution, Absolute/
Elapsed conversion, initial-state semantics) and, separately, re-proven
correct end to end against realistic fixture data covering a
constant-HIGH channel, a constant-LOW channel, and a channel with a real
transition -- all passing in the jsdom harness both before and after
this investigation. Since jsdom cannot render Plotly.js at all (no
canvas/SVG rendering engine, and the mock only records the arguments
Plotly was CALLED with), a jsdom pass proves the DATA reaching Plotly was
correct but cannot prove anything about what a real browser actually
painted from it -- exactly the gap the owner's real-browser UAT is
catching. No further logic bug was found through static analysis alone.

### What changed

**A. Alignment**: `wwResizeAllVisiblePlots()` now also calls
`Plotly.Plots.resize()` on the digital chart when `ww.digitalChartReady`,
alongside every analog panel and the ruler -- the SAME shared authority
all three already funnel through for every non-window-resize geometry
change. `#wwDigitalChart` gained an explicit `width: 100%` CSS rule,
matching `.ww-chart`/`.ww-sticky-ruler-chart`'s own pattern exactly.
`wwRebuildDigitalChart()` also schedules one additional, defensive
`requestAnimationFrame`-deferred `Plotly.Plots.resize()` after every
rebuild (a cheap no-op if the width was already correct) as a further
belt-and-braces measure against any remaining first-render timing risk.
A new `wwDiagnoseDigitalAlignment()` function (exposed globally, run as
`wwDiagnoseDigitalAlignment()` in the browser DevTools console) reads
each surface's REAL rendered geometry -- `getBoundingClientRect()` plus
Plotly's own internal `_fullLayout.xaxis._offset`/`._length` (the
ACTUAL computed layout after any automargin/annotation adjustment, not
just the `margin` value originally requested) -- and prints a
side-by-side comparison table of analog/digital/ruler's absolute
page-pixel plot-left and plot-right edges, since no real browser is
available in this sandbox to verify pixel geometry directly.

**B. Loader**: a new `wwYieldToPaint()` helper
(`requestAnimationFrame` nested inside a second `requestAnimationFrame`
-- the standard "wait until the DOM mutation I just made has genuinely
been painted, not merely scheduled" pattern) is awaited immediately
after `wwSetWorkspaceLoading(true, ...)` in `selectSource()`, before
`refreshSourceList()` or any other work begins -- reusing this
codebase's own established Phase 2C-C2A "separate the cheap DOM write
from the expensive work, let the browser breathe between them"
principle, applied here to a loading overlay instead of a resize
handle. `openRecordingForAnalysis()` now calls
`shellSetCurrentPage("waveform")` BEFORE `selectSource(sourceId)`
(previously the other order), so the loader's own ancestor container is
unconditionally already visible by the time the loader itself becomes
visible.

**C. Labels**: the label annotation's `y`/`yanchor` changed to `y: y,
yanchor: "middle"` -- centered exactly on the trace's own Y (previously
offset 0.32 units above it), so the trace visibly runs behind/through
the label, matching the reference image's "label sits ON the lane"
treatment rather than a separate row above it.

**D. HIGH/LOW rendering**: HIGH-interval bars are now rendered as
`layout.shapes` (`type: "line"`, from the interval's own start/end X to
the lane's own Y, `line: {width: 7, color: accent}`) -- the exact same
Plotly primitive already used (and, per the owner's own PASS on
grouping, already working) for the group-divider lines in this SAME
chart -- rather than a second, `null`-gapped line TRACE per channel.
This removes trace-diffing/hover-configuration/multi-segment-gap
handling as a variable entirely, in favor of a simpler, more predictable
primitive for "a static colored bar from x0 to x1," given no concrete
logic bug could be found in the previous trace-based approach through
exhaustive static analysis. The thin baseline trace is unchanged (one
per channel, full record width, real hovertext). Each channel now
produces exactly ONE trace again (not two) -- the digital-lane
click-to-remove handler's `curveNumber` mapping simplified back to
`entries[curveNumber]` directly (no more `/2`).

### Tests

`phase4a_check.mjs` (scratch convention, not committed) grew from 31 to
35 checks: `wwResizeAllVisiblePlots()` includes the digital chart;
`wwDiagnoseDigitalAlignment()` runs without error and reports on all
three surfaces (values are necessarily null/zero in jsdom -- no real
layout engine -- confirmed as an expected, explicitly-acknowledged
limitation, not a bug); the label annotation's `y`/`yanchor` matches the
trace's own Y exactly; `openRecordingForAnalysis()` navigates to
Waveform before `selectSource()` starts, so the loader's own container
is already visible; HIGH-interval boundaries are exact transition
timestamps via `layout.shapes` (re-verified against a known
constant-HIGH channel, a known constant-LOW channel, and a channel with
a real transition, per the task's own explicit "prove with at least
one of each" instruction); the HIGH-band shape's line width (7) is
visibly greater than the baseline trace's (1); one trace per channel in
one shared Plotly figure (never one-per-channel). Every pre-existing
Phase 4A/UAT1B check (classification, ordering, default-display
persistence, source isolation, loading-overlay progress/clearing) still
passes unchanged. Full existing frontend regression suite: still exactly
the established 17-failure pre-existing baseline. Backend: 311/311,
unchanged (no backend file touched this pass).

### Files changed

`frontend/index.html` only.

### Honest limitations (owner real-browser verification still required)

**This pass cannot be accepted based solely on jsdom/source-level
checks** -- no real browser is available in this sandbox, matching this
task's own explicit instruction. Every fix above is backed by a
concrete, well-evidenced root cause found through direct source-code
investigation (not a guess), and jsdom confirms the DATA/CONFIG reaching
Plotly is now structurally correct in every case -- but jsdom cannot
render Plotly.js at all, so it cannot independently confirm any of the
four failures are now visually resolved, particularly Failure D (HIGH
band visibility), where no logic bug was found and the fix (switching to
a simpler rendering primitive) is a well-reasoned but unproven-in-browser
change. `wwDiagnoseDigitalAlignment()` is provided specifically so the
owner (or a future session with real browser access) can independently
verify Failure A's resolution with real numbers, not just re-read this
record's own reasoning.

---

## Phase 4A-UAT1B — Digital Waveform UX / Correctness Refinement (2026-08-18)

`[FACT]` throughout. No new DECISIONS.md entry -- this refines the
*presentation* (trace geometry, label placement, margins) within the
architecture DEC-034 already approved (one shared Plotly figure, batched
full-record digital-waveform delivery); it does not change either of
those two architectural commitments.

### Owner UAT findings addressed

1. Digital sorting/grouping looked purely alphabetical rather than
   respecting classification order.
2. Digital traces did not visually line up with analog traces.
3. Opening a recording with all analog + digital displayed by default
   could lag with no visible loading state.
4. Constant-HIGH vs constant-LOW digital signals were hard to tell apart.
5. New owner visual direction (screenshot benchmark): small overlaid
   pill labels directly on each lane; HIGH shown as a bold/thick band;
   LOW as a thin line; no two-plateau step trace as the primary visual.

### Root cause investigation (before any change)

- **Finding 1 (sorting)**: `wwDigitalSortChannels()`/`wwSortedDigitalEntries()`
  were re-audited end to end (frontend sort function, the
  `ww.digitalDisplayed` population path in `wwAddDigitalChannels()`, and
  the backend `classify_digital_channel()`/import-time computation) and
  found CORRECT -- confirmed against both the ASCII and BINARY COMTRADE
  provider paths directly (`ComtradeProvider().load(...)` +
  `classify_digital_channel()` on `tests/fixtures/comtrade/synth_binary.*`,
  not just the ASCII fixture Phase 4A's own tests used). The real gap:
  the RENDERED digital region had **zero visual indication of group
  boundaries** -- no header, no separator, no count -- so a recording
  where one classification (typically Never Triggered) numerically
  dominates reads as "just alphabetical" even though the underlying
  order was already correct. The channel browser already showed this
  via its `<details>` subgroup structure; the rendered chart never did.
- **Finding 2 (alignment)**: confirmed as a real, reproducible bug.
  `wwRebuildDigitalChart()`'s own Plotly `margin.l` was `150` (sized for
  a wide Y-axis tick-label column), while every analog panel and the
  shared sticky ruler use `WW_PANEL_MARGIN.l` (`55`) -- two genuinely
  different left margins meant the digital plot area's actual pixel
  origin was offset from analog/ruler's, so identical X values rendered
  at different screen positions. A second, smaller contributor: analog
  panels (`.ww-chart-wrap`, inside `.ww-panel`'s 14px padding) and the
  ruler (`.ww-sticky-ruler`'s own 14px padding) both had 14px of
  horizontal CSS padding around their chart element; `#wwDigitalScroll`
  had none.
- **Finding 4 (HIGH/LOW ambiguity)**: the previous two-plateau `hv`-step
  trace (LOW at one Y, HIGH at a second Y, same line width/color)
  required noticing a Y-position shift to tell state apart -- a real,
  legitimate readability gap, independent of the owner's separate visual
  redesign request.

### What changed

**A. Group headers in the rendered digital region** (fixes Finding 1):
`wwDigitalLayoutRows()` (new) interleaves a header row (group name,
UPPERCASE, count) between each non-empty classification block on top of
the already-correct `wwSortedDigitalEntries()` order; a subtle divider
`shape` marks each boundary. Same three groups, same order, same counts
as the channel browser -- never a second, independently-computed
grouping.

**B. True pixel alignment** (fixes Finding 2): `wwRebuildDigitalChart()`'s
margin is now `WW_PANEL_MARGIN.l`/`.r` -- identical to every analog panel
and the shared ruler. `#wwDigitalScroll` gained `padding: 0 14px`,
matching `.ww-sticky-ruler`'s own horizontal padding exactly. This was
only possible because of change C below (labels no longer need a wide
Y-axis tick column).

**C. Rendering redesign to the owner's visual benchmark** (fixes
Finding 4, delivers the new visual direction): each digital lane is now
ONE flat Y position (not two), carrying exactly two traces --
`wwDigitalHighIntervals(entry)` (new) derives the channel's HIGH-state
time intervals from `initialState` + the sparse `transitions` list
(never a full per-sample array, which digital delivery never carries at
all):
- A thin, muted **baseline** trace (`line.width: 1`, `colors.grid`)
  spans the entire record -- always present, representing "this channel
  exists, LOW unless marked otherwise."
- A thick, bold **HIGH band** trace (`line.width: 7`, `colors.accent`),
  `null`-gapped between separate HIGH runs, drawn ONLY during the
  channel's actual HIGH intervals -- a constant-HIGH channel now shows a
  bold band spanning the FULL record width; a constant-LOW channel shows
  no band at all, only the thin line. Exact transition timestamps are
  preserved exactly (a straight segment's own start/end IS the real
  transition time).

Channel name labels moved from Y-axis ticks to Plotly **annotations**
(`xref: "paper"`, so they stay pinned to the plot area's left edge
regardless of X zoom/pan -- never drifting with the data), rendered as a
small opaque pill (`colors.panel` background, `colors.grid` border,
9px font) directly overlaid on the lane, matching the owner's screenshot
benchmark. Truncation budget shrank from 26 to 18 characters (a smaller
overlay pill, not a wide column); the FULL name remains available via
the baseline trace's own hovertext, unchanged in spirit from before.
The Y axis itself is now fully hidden (`visible: false`) -- it carried
no real engineering scale before either, only tick labels, which are
gone.

The per-lane click-to-remove interaction (Phase 4A) still works: each
channel now produces 2 traces instead of 1, so `curveNumber` maps to
`entries[Math.floor(curveNumber / 2)]`, regardless of which of the two
(thin baseline or bold band) the user actually clicked.

**D. Immediate loading feedback** (fixes Finding 3): a new
`#wwWorkspaceLoading` overlay (absolute-positioned over
`.workspace-section`, `role="status"`/`aria-live="polite"`) is shown as
the VERY FIRST statement in `selectSource()` -- before
`refreshSourceList()`'s own fetch even starts -- with the text "Loading
recording…", then "Loading channels…" once the default-display fetch
pipeline begins. A `try/finally` guarantees it is always cleared,
success or failure (including a 404/network-error path), never left
stuck. `wwAddSelectedChannels()`/`wwAddDigitalChannels()` gained
optional `onChannelLoaded`/`onBatchLoaded` callbacks (unused by every
pre-existing call site -- backward compatible) that
`wwApplyDefaultChannelDisplay()` uses to drive a REAL "N / total"
channel-loaded counter (analog channels each resolve independently, one
fetch per channel, so each bumps the counter as it lands; digital is one
batched request per source, so it reports its whole batch's count at
once) -- never a fake percentage or fabricated stage count, per this
task's own explicit instruction.

### Files changed

`frontend/index.html` only. No backend file touched (pure frontend
presentation/UX refinement; the batched digital-waveform API and
import-time classification from Phase 4A are unchanged and already
correct).

### Tests

`phase4a_check.mjs` (scratch convention, not committed) extended from 25
to 31 checks: the HIGH-band trace's segment boundaries are the exact
transition timestamps; a constant-HIGH channel's band spans the full
record while a constant-LOW channel has no band at all; the digital
chart's left/right margin now exactly matches the analog panel's own
margin; the Y axis is fully hidden (no more tick-based label column);
the rendered region shows one header + count per non-empty group in the
exact required order, with a divider shape at each boundary; the long
channel name's overlaid annotation is truncated with the full name still
in hover text; the loading overlay appears synchronously (before the
`/channels` fetch resolves), reports a real per-channel progress count
reaching the true total, and is cleared even on a fetch failure. Every
pre-existing Phase 4A check (classification, ordering, default-display
persistence, shared-viewport sync, source isolation) re-verified passing
unchanged. Full existing frontend regression suite re-run: still exactly
the established 17-failure pre-existing baseline (`phase2cb1/cb2/cb3/
cb3a/cc1/cc2/cc3/cc4_check.mjs`, all independently unrelated to digital
channels -- none of those fixtures carry any digital channel or call
`selectSource()` at all). Backend: 311/311 passing, unchanged (no
backend file touched this pass).

### Honest limitations

No real browser is available in this sandbox -- the actual rendered
appearance of the bold HIGH band / thin baseline / overlaid pill labels
against the owner's screenshot benchmark, real pixel alignment as
perceived by eye (not just asserted equal margin values), and the
loading overlay's real-world timing/feel were reasoned through and
structurally exercised via jsdom, but not visually confirmed --
flagged for owner UAT.

---

## Phase 4A — Digital Channels Rendering Implementation Record (2026-08-17)

`[FACT]` throughout. New architecture decision — see
[DECISIONS.md — DEC-034](DECISIONS.md#dec-034--digital-channel-rendering-shared-batched-full-record-transition-api-one-shared-multi-trace-plotly-figure-not-one-instance-per-channel-phase-4a).

### Owner directive

Pause cosmetic UX work (Phase 3B-UAT7–UAT11) and return to core waveform
functionality: render COMTRADE digital (binary/state) channels alongside
the existing analog waveform architecture. Explicit instruction: display
ALL analog and digital channels by default once a recording is opened,
then evaluate real performance/usability through owner UAT before
deciding whether any default channel filtering is needed — do not
prematurely optimize by hiding channels automatically.

### Mandatory startup investigation (completed before implementation)

Reviewed the existing full-resolution analog waveform API
(`extract_waveform_range`, DEC-019), the analog rendering architecture
(one Plotly instance per panel, DEC-024/DEC-026), Grouped/Separate/Custom
layouts (DEC-025/DEC-027), the shared X viewport (DEC-021), the shared
sticky time-axis ruler (DEC-030), the channel browser, and the COMTRADE
digital-channel domain representation. Confirmed via direct source
inspection: digital sample values are `np.int8` 0/1 (normal-state
inversion NOT applied — raw bits preserved,
`app/providers/comtrade.py`), retained only in
`DisturbanceRecord.waveform_data` (never on lightweight metadata), and
that no existing API path served them at all — `_resolve_analog_channel`
explicitly rejected digital channel names
(`ChannelNotAnalogError`). This confirmed digital-waveform delivery was
genuinely undecided architecture, not an oversight to quietly extend.

### Backend

- `app/domain/digital_classification.py` (new): pure, stateless
  `classify_digital_channel(*, name, values)` — Spare (name contains
  "spare", case-insensitive, anywhere) → precedence over Triggered even
  when the channel does go high; else any non-zero sample across the
  FULL record → Triggered (a channel that starts high and stays high the
  whole record, never transitioning, is still Triggered); else Never
  Triggered.
- `app/services/import_service.py`: `_build_source_metadata()` now
  computes `classification` once per digital channel at import time
  (same established pattern as `duration_seconds`/`sampling_rates`/
  analog `engineering_type`) — never re-scanned per request.
- `app/domain/source.py` / `app/schemas/source.py`:
  `DigitalChannelSummary`/`DigitalChannelOut` gained a `classification:
  str` field.
- `app/services/errors.py`: new `ChannelNotDigitalError`, symmetric with
  the existing `ChannelNotAnalogError`.
- `app/services/waveform_service.py`: new
  `extract_digital_waveform(active, *, channel_name)` — vectorized
  (`np.diff`) transition-finding, always full-record (no `start_time`/
  `end_time`/`point_budget`), returning `classification`, `normal_state`,
  `initial_state`, a sparse `transitions: [{time, state}]` list, and
  `start_time`/`end_time`/`sample_count`.
- `app/schemas/digital_waveform.py` (new):
  `DigitalTransitionOut`/`DigitalWaveformOut`/`DigitalWaveformBatchOut`.
- `app/api/v1/sources.py`: new
  `GET .../sources/{source_id}/digital-waveform?channel_names=A&channel_names=B...`
  (repeated query param — batched, one request per source among
  newly-displayed channels, not one request per channel).
- **Tests**: `backend/tests/test_digital_classification.py` (17 cases —
  every Triggered/Never-Triggered/Spare scenario including "starts high,
  never transitions" and the "SPARE TRIP" name-precedence-despite-going-
  high edge case, parametrized case-insensitive/substring Spare-name
  matching, stable ordering of `KNOWN_GROUPS`).
  `backend/tests/test_digital_waveform_api.py` (8 cases — classification
  exposed via `GET .../channels`, exact transition timestamps against
  the `synth_ascii` fixture (`BRK_A`/`BRK_B`), batch order preservation,
  404/400 error mapping, two-source isolation). Full backend suite:
  **311/311 passing** (286 pre-existing + this phase's 25 new), zero
  regressions.

### Frontend

- New `ww` state: `digitalDisplayed: Map<"sourceId::channelName", entry>`
  (fully separate from the analog-only `ww.displayed`/`ww.panels`),
  `digitalChartReady`, `digitalClickWired`, `sourceDefaultsApplied:
  Set<sourceId>`.
- New DOM: `#wwDigitalRegion` (hidden when empty) → `.ww-digital-title`
  → `#wwDigitalScroll` (fixed `max-height: 260px`, `overflow-y: auto`) →
  `#wwDigitalChart` — positioned strictly below `#wwPanels`, strictly
  above the existing `#wwStickyRuler`; the ruler is never nested inside
  the scroll container, so it cannot scroll out of view.
- `wwRebuildDigitalChart()`: one shared Plotly figure, one `line_shape:
  "hv"` step trace per displayed digital channel at incrementing Y-axis
  lane offsets; Y-axis ticks are the (truncated, 26-char max) channel
  names via `tickmode: "array"`, full name always available via
  per-trace `hovertext`; X-axis tick labels suppressed entirely (the
  sticky ruler remains the one bottom time reference — no duplicated
  axis); `fixedrange: true` on both axes. Always updated via
  `Plotly.react`, called from every site that changes the displayed
  digital set, `ww.viewport`, `ww.timeMode`, or the theme.
  `wwDigitalSortChannels()`/`wwSortedDigitalEntries()`: group (Triggered
  → Never Triggered → Spare) → case-insensitive alphabetical → stable
  original-index tiebreak — the SAME function drives both the rendered
  lanes and the channel browser's own digital grouping, so the two can
  never disagree.
- `wwAddDigitalChannels(channelMetas)`: batches by source, calls the new
  `/digital-waveform` endpoint with repeated `channel_names` params.
  `wwRemoveDigitalChannelByKey(key)`: used by workspace/source-removal
  AND by a new `plotly_click` listener on the digital chart (wired once,
  re-deriving the current sorted entry list on every click) — the
  lowest-cost per-lane remove affordance available given digital lanes
  have no individual DOM row of their own, keeping "hide/remove/re-add"
  meaningful for digital the same way analog's per-panel legend remove
  button already is.
- `renderDigitalGroup()` (channel browser) rewritten: previously a flat,
  collapsed-by-default, checkbox-less table; now sub-grouped by
  Triggered/Never Triggered/Spare (each `<details open>`, group counts
  shown), each subgroup alphabetically sorted via the same
  `wwDigitalSortChannels()`, each row carrying a checkbox
  (`digitalChannelCheckboxHtml`, `data-channel-kind="digital"`) —
  Phase 4A is the first time digital channels could be added to the
  display at all.
- `selectedDigitalChannels` (new Map, parallel to the existing
  `selectedChannels`): the shared "Add N selected"/"Clear selection" UI
  now acts on whichever kind(s) currently have checkboxes checked,
  routing into the correct add path (`wwAddSelectedChannels` for analog,
  `wwAddDigitalChannels` for digital) without a second set of buttons.
- **Default display policy**: `wwApplyDefaultChannelDisplay(data)`
  (new, `async`) builds the same `channelMetas` shape the existing
  checkbox-driven add paths already expect, straight from the
  just-fetched channel list, and `await`s both `wwAddSelectedChannels`/
  `wwAddDigitalChannels` concurrently (`Promise.all`). `selectSource()`
  calls this ONLY the first time a given `sourceId` is opened this
  session (`ww.sourceDefaultsApplied`), and awaits it — a fire-and-forget
  version was caught and fixed during implementation because it created
  a real race against any fast subsequent action (another `selectSource`
  call, a manual "Add selected" click, or a test's own scripted
  follow-up). Reset only by `wwClearWorkspace()`, so a manually-hidden
  channel is never reapplied merely by navigating
  Waveform → Recordings → Waveform and re-opening the same already-open
  recording.
- Autoscale Y remains analog-only (`ww.panels` only) — never touches the
  digital chart. Reset Time View resets both analog and digital X
  viewport to the same full-record range (both funnel through
  `wwApplyAndFetchViewport`). Absolute/Elapsed switching restyles the
  digital chart's presentation via the same `wwElapsedToPlotlyX`
  boundary analog uses, with zero additional `/digital-waveform` fetch.

### Digital display ordering (owner's exact required precedence)

1. **Triggered**, 2. **Never Triggered**, 3. **Spare** (always last) —
   both in the rendered lanes and the channel browser, identically.
   Within a group: case-insensitive alphabetical, stable original-index
   tiebreak on ties. Verified with a mixed fixture (`alarm`, `ALARM_B`,
   `Breaker`, `cb_trip` sort to that exact order) and the exact "SPARE
   TRIP still classified Spare despite a real high sample" and
   "ALWAYS_HIGH still classified Triggered despite zero transitions"
   edge cases from the owner's own worked examples.

### Tests

- New dedicated frontend verification script (not committed — this
  project's established scratch-verification convention):
  `phase4a_check.mjs`, 25 checks covering: default display policy
  (new-source = all displayed; manual per-lane removal via
  `plotly_click` persists across a Waveform → Recordings → Waveform
  round trip; default is never reapplied on re-navigation);
  classification precedence as delivered (Triggered via any high
  sample; Triggered despite zero transitions; Never Triggered;
  Spare-name-precedence-despite-going-high); ordering (group order,
  case-insensitive alphabetical, channel-browser/rendered-region
  agreement, full classified-set group counts); digital region
  placement (document order strictly below analog panels, strictly
  above the shared ruler); digital rendering (`line_shape: "hv"` step
  geometry with exact transition timestamps, no duplicated bottom axis
  labels, HIGH/LOW distinguishable via geometry not color alone, one
  shared Plotly figure never one-per-channel); shared viewport (analog
  zoom broadcasts to the digital chart's X range, Reset Time View
  resets both, Autoscale Y never touches digital, Absolute/Elapsed
  switch causes zero additional digital fetch); large channel count (40
  displayed lanes genuinely exceed the fixed 260px scroll viewport,
  forcing real scrolling — not just declared CSS — while the ruler
  stays outside the scroll container); long channel names (truncated
  tick label, full name always available via hover); source isolation
  (two sources' digital channels never leak, per-entry key always
  matches its own recorded `sourceId`, removing one source's channels
  leaves the other's completely untouched).
- **Full existing frontend regression suite re-run**: total failures
  returned to exactly the established pre-existing baseline (**17**,
  across `phase2cb1/cb2/cb3/cb3a/cc1/cc2/cc3/cc4_check.mjs` only — every
  one independently confirmed, by running the identical test files
  against the untouched canonical `frontend/index.html` from `HEAD`, to
  already fail identically with ZERO Phase 4A involvement; all trace to
  the pre-existing DEC-030 sticky ruler's own relayout/newPlot calls
  being counted by hardcoded assertions written before the ruler
  existed). `phase2ca_check.mjs` went from its own previously-documented
  3-failure baseline to **0** — three genuinely pre-existing,
  ruler-related assertion bugs were fixed in place as an unavoidable
  side effect of correctly accounting for `selectSource()`'s new
  earlier-firing default-display flow, not scope creep.
  `phase3buat8_check.mjs`'s one zero-fetch assertion was corrected in
  place (selecting a source now legitimately fetches waveform data as
  part of opening it — the assertion now checks that a pure navigation
  round trip adds no ADDITIONAL fetch, which is what it always actually
  meant to verify). `phase3buat9_check.mjs`'s one border-value assertion
  was corrected in place to match the already-committed, unrelated
  Phase 3B-UAT11 divider change (`#workspaceSidebar`'s `border-right`
  intentionally became `0` in that separate, already-shipped commit).
- **Backend**: 311/311 passing in a fresh venv (286 pre-existing +
  17 classification + 8 digital-waveform-API = 311), zero regressions.

### Files changed

- `backend/app/domain/digital_classification.py` (new)
- `backend/app/schemas/digital_waveform.py` (new)
- `backend/app/domain/source.py`
- `backend/app/schemas/source.py`
- `backend/app/services/errors.py`
- `backend/app/services/import_service.py`
- `backend/app/services/waveform_service.py`
- `backend/app/api/v1/sources.py`
- `backend/tests/test_digital_classification.py` (new)
- `backend/tests/test_digital_waveform_api.py` (new)
- `frontend/index.html`
- `docs/project-memory/DECISIONS.md` (new DEC-034)
- `docs/project-memory/CURRENT_STATE.md`
- `docs/project-memory/HANDOFF.md`
- `docs/project-memory/MIGRATION_PLAN.md`

### Performance observations (representative source: the 40-digital-channel
test fixture used by `phase4a_check.mjs` — no real large COMTRADE file
with hundreds of digital channels was available in this sandbox, so
these are structural/qualitative jsdom-harness observations, not
real-browser timing measurements; explicitly labeled as such rather than
claimed as "fast")

- Analog channels: 1. Digital channels: 40 (5 Triggered / 33 Never
  Triggered / 2 Spare). Plotly figures: 3 total (1 analog panel, 1
  shared digital figure, 1 sticky ruler) — never 41. Digital trace
  count: 40 traces inside that one shared figure. Network requests for
  the default-display open: 1 `.../channels` + 1 analog `.../waveform` +
  1 batched `.../digital-waveform` (all 40 digital channels in one
  request, not 40). Digital chart height at 40 lanes: computed at
  `40 * 22px + 16px = 896px`, comfortably exceeding the fixed 260px
  `#wwDigitalScroll` viewport — confirmed to genuinely require
  scrolling, not just declare `overflow: auto` untested. Zoom/pan:
  `fixedrange: true` on the digital chart means it never independently
  drives relayout, so its own responsiveness is bounded entirely by one
  `Plotly.react` call per shared-viewport change — structurally bounded
  regardless of displayed digital channel count, but real 100+/300+
  channel responsiveness was NOT measured in a real browser and remains
  an open owner-UAT question (see the final report).

### Honest limitations

- No real browser is available in this sandbox — actual rendered
  readability of the digital step traces in Light/Dark themes, hover
  tooltip legibility, real scroll feel inside `#wwDigitalScroll`, and
  real zoom/pan responsiveness at 100+/300+ simultaneously-displayed
  digital channels were reasoned through and structurally exercised via
  jsdom, but not visually confirmed — flagged for owner UAT.
- No COMTRADE fixture with hundreds of real digital channels was
  available; the 40-channel synthetic fixture used for the scrolling/
  performance checks is a stand-in, not a claim that behavior at
  hundreds of channels was directly measured.
- Digital channels have no drag-to-reorder and no custom-grouping
  editor this phase (owner's own explicit scope exclusion) — only the
  Triggered/Never-Triggered/Spare presentation grouping exists.

---

## Phase 3B-UAT11 — Workspace Sidebar Divider / Scrollbar Line Cleanup (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry (targeted visual follow-up
inside the already-approved Phase 3A/3B shell structure; no architecture,
navigation, or behavior decision).

### Owner UAT evidence

After Phase 3B-UAT10, owner real-browser UAT confirmed the scrollbar thumb
looked slim/acceptable and the track was largely blended, but a thin hard
vertical line remained immediately to the right of the Workspace Sidebar
scrollbar. The line still read visually as a scrollbar rail.

### Confirmed source

Source inspection found the remaining line was not a scrollbar
pseudo-element. It was the Workspace Sidebar's structural divider:

```css
#workspaceSidebar {
    border-right: 1px solid var(--panel-border);
}
```

The adjacent resize handle already drew a second separator via
`.shell-split-handle::after` (`width: 2px`, `left: 2px`,
`background: var(--panel-border)`) inside the 6px drag target. The
desktop boundary therefore had an avoidable multi-line appearance:
scrollbar thumb/gutter, the sidebar's own border flush against it, and
then the handle's centered divider.

No `#mainWorkspace` border-left, parent border, pseudo-element, or inset
shadow was found at that boundary. The only drawer-specific extra boundary
was the existing shadow used when the Workspace Sidebar becomes an overlay
under 900px.

### Fix

The fix removes the Workspace Sidebar's hard right border in both its
desktop/base rule and the <=900px drawer override:

```css
#workspaceSidebar {
    border-right: 0;
}
```

Desktop separation is now provided by the existing resize handle's centered
divider, so there is one visual separator instead of a border directly
hugging the scrollbar plus a handle line. Narrow-screen drawer separation
is still provided by the existing overlay shadow/backdrop, without
reintroducing the hard scrollbar-adjacent border.

### What deliberately did not change

UAT9/UAT10 scrollbar styling is unchanged: 6px WebKit dimensions,
borderless rounded thumb, targeted local track blending,
`::-webkit-scrollbar-track-piece`, and Firefox `scrollbar-color` remain as
implemented. No scrollbar was hidden.

Workspace layout geometry is unchanged: `#workspaceSidebar` keeps
`width: 320px`, the JS resize constants remain 320/240/520, the 6px
`.shell-split-handle` drag target remains, the pointer-capture resize
helper remains, and `onResize: wwResizeAllVisiblePlots` remains wired.
No Plotly data path, viewport state, channel tree behavior, Recordings
page behavior, theme behavior, or responsive shell state was changed.

### Tests

- **Committed source-level checks updated**:
  `backend/tests/test_frontend_scrollbar_css.py` now verifies the UAT9
  scrollbar baseline, UAT10 track blending, the UAT11 rule that
  `#workspaceSidebar` no longer carries the hard
  `border-right: 1px solid var(--panel-border)`, the resize handle still
  exists and provides the centered divider/hover affordance, the sidebar
  overflow/background/width rules remain, the resize constants and
  Plotly resize callback remain wired, and the <=900px drawer keeps its
  overlay/shadow behavior while also avoiding the hard right border.
- **Verification run**: `git diff --check` clean;
  `cd backend && /private/tmp/oruxa-powerwave-pytest-venv/bin/python -m pytest tests/test_frontend_scrollbar_css.py`
  passed (6/6); committed/tracked backend tests passed (286/286, two
  existing warnings). A raw `cd backend && pytest` against the whole
  dirty local worktree failed 8 unrelated untracked digital-waveform
  tests (`tests/test_digital_waveform_api.py`) because those tests expect
  unmerged digital-waveform backend behavior not present in canonical
  `HEAD`; those files were pre-existing and not touched by UAT11.

### Files changed

- `frontend/index.html`
- `backend/tests/test_frontend_scrollbar_css.py`
- `docs/project-memory/CURRENT_STATE.md`
- `docs/project-memory/HANDOFF.md`
- `docs/project-memory/MIGRATION_PLAN.md`

### Honest limitation

The source diagnosis is clear, and the committed checks protect against
reintroducing the hard scrollbar-adjacent border. Actual perception of
the softened boundary still depends on real browser/OS scrollbar rendering,
so final confirmation remains an owner DEV UAT item.

---

## Phase 3B-UAT10 — Targeted Scrollbar Track / Divider Fix (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry (targeted cosmetic
follow-up to Phase 3B-UAT9; no architecture, data, or behaviour
decision).

### Root cause diagnosed

Phase 3B-UAT9 correctly removed borders from the scrollbar pseudo-
elements themselves: the shared `::-webkit-scrollbar-track` rule is
transparent and borderless, and the thumb is borderless and rounded.
The remaining owner-visible "line" was therefore not a scrollbar
border in the CSS. It was primarily the combination of a transparent
scrollbar gutter/track beside existing real container/divider borders
(`border-right` on the main/workspace sidebars, `border`/`overflow:
hidden` on grouped channel containers, and the modal border around the
group editor). With a transparent track, those structural lines could
visually read as a rail beside the thumb.

### What changed

The global Phase 3B-UAT9 baseline in `frontend/theme.css` remains
unchanged: universal Firefox/WebKit scrollbar styling, 6px dimensions,
transparent global track, borderless rounded theme-token thumb, and
transparent global corner.

A small targeted follow-up block was added after the global rules:

- `#mainSidebarMenu` uses `var(--panel)` as the local track surface.
- `#workspaceSidebar` uses `var(--bg)` as the local track surface.
- `.group-editor-box` uses `var(--panel)` as the local track surface.
- `.group-body` uses `var(--panel)` as the local track surface.

For each targeted area, the Firefox path (`scrollbar-color:
var(--scrollbar-thumb) <local-surface>`) now supplies a non-transparent
track color, and the Chromium/WebKit path explicitly styles both
`::-webkit-scrollbar-track` and `::-webkit-scrollbar-track-piece` with
the same local background and `border: 0`. Local scrollbar corners were
also matched to the same local surface to avoid a boxed corner when
both axes are present.

### What deliberately did not change

No `overflow`/`overflow-x`/`overflow-y` declaration was changed. No
scrollbar size, width, layout dimension, sidebar width, split handle,
or scrolling behaviour was changed. No structural border was removed:
`#mainSidebarMenu` and `#workspaceSidebar` keep their `border-right`,
`details.channel-group` keeps its real group border, and
`.group-editor-box` keeps its modal border. The fix is scoped to the
scrollbar pseudo-element rendering layer and Firefox scrollbar track
color only.

### Tests

- **Committed source-level regression checks**:
  `backend/tests/test_frontend_scrollbar_css.py` verifies the global
  scrollbar baseline remains slim/borderless, the four targeted
  containers have local-surface track colors, the UAT10 block does not
  introduce width/height/overflow/layout-border rules, and the relevant
  existing scroll containers still retain their overflow declarations
  and structural borders in `frontend/index.html`.
- **Verification run**: `git diff --check` clean;
  `cd backend && /private/tmp/oruxa-powerwave-pytest-venv/bin/python -m pytest tests/test_frontend_scrollbar_css.py`
  passed (4/4); full backend suite passed (309/309, two existing
  warnings: Starlette `httpx` deprecation and the malformed-CFG test's
  expected COMTRADE warning).

### Files changed

- `frontend/theme.css`
- `backend/tests/test_frontend_scrollbar_css.py`
- `docs/project-memory/CURRENT_STATE.md`
- `docs/project-memory/HANDOFF.md`
- `docs/project-memory/MIGRATION_PLAN.md`

### Honest limitation

The fix is based on CSS diagnosis and source-level regression checks.
Actual browser rendering can still vary by operating system scrollbar
mode (overlay vs classic scrollbars), so final confirmation that the
visible border-line impression is gone remains an owner UAT item in a
real browser.

---

## Phase 3B-UAT9 — Slim Borderless Scrollbars (2026-08-17)

`[FACT]` throughout. No new DECISIONS.md entry (a global cosmetic
refinement, no architecture/behavior change).

### What changed

A single shared scrollbar rule set was added to `frontend/theme.css`
(the file already shared between `index.html` and
`waveform-prototype.html` via a plain `<link>`) — a universal `*`
selector declares both the Firefox path (`scrollbar-width: thin`,
`scrollbar-color`) and the Chromium/WebKit path
(`::-webkit-scrollbar`/`-track`/`-thumb`/`-thumb:hover`/`-corner`) for
every element unconditionally, since these properties are no-ops on
non-scrolling elements. No per-panel/per-page duplication, matching the
task's own "one reusable/shared style" preference. Two new theme
tokens, `--scrollbar-thumb`/`--scrollbar-thumb-hover`, were added to
both the Light `:root` and Dark `:root[data-theme="dark"]` blocks,
following the SAME alpha-over-neutral-base convention already
established for `--hover-tint`/`--surface-tint`
(`rgba(27,35,51,...)` in Light, `rgba(255,255,255,...)` in Dark) — not
an unrelated new color, just a stronger alpha of the existing neutral
scale, and no hardcoded literal color anywhere in the rule set itself.

- Vertical/horizontal scrollbar size: 6px (within the requested 5-7px
  range).
- Track: `transparent`, `border: 0`.
- Thumb: theme-derived neutral color, `border: 0`, `border-radius:
  999px` (fully rounded), strengthens to `--scrollbar-thumb-hover` on
  hover — never the loud `--accent` color.
- Corner (where a vertical and horizontal scrollbar meet): transparent,
  so no boxed appearance there either.
- No browser-specific JavaScript — CSS only, per the task's own
  explicit instruction.

### Scrollable containers preserved

No `overflow`/`overflow-x`/`overflow-y` declaration was touched on any
container — `#mainSidebarMenu`, `#workspaceSidebar`, `#activeViewArea`,
`#pageRecordings`, `.recordings-table-wrap`, `.group-body`, and
`.group-editor-box` (the seven actual scrollable containers identified
in `frontend/index.html` before making this change) all keep their
existing `overflow: auto` (or `-x`/`-y` variant) unchanged — this is a
scrollbar-cosmetics-only pass, never a scrolling-functionality change.
Non-scrollbar layout borders (e.g. `#workspaceSidebar`'s
`border-right`, `.group-editor-box`'s `border`) are untouched — the new
rules only ever target the `::-webkit-scrollbar-*` pseudo-elements,
which are a separate rendering layer from an element's own box border.

### Tests

- **Frontend, new**: `phase3buat9_check.mjs` (scratch, not committed) —
  18/18 passing. Source-level checks only (jsdom has no scrollbar
  rendering at all, so real visual slimness/contrast is for owner
  UAT): the rule set exists exactly once in the shared `theme.css` (not
  duplicated in either HTML page), both the Firefox and Chromium/WebKit
  paths are present, size is within 5-7px, track/thumb/corner have no
  border and use theme tokens (no hardcoded hex), hover uses the
  dedicated hover token (not `--accent`), both theme blocks define
  genuinely different token values, and every one of the seven
  identified scrollable containers still declares its own
  `overflow: auto` with its own layout border untouched.
- **Frontend, full regression**: the exact same 20 pre-existing,
  already-documented failures, zero new divergences (a purely additive
  CSS change touches no JS behavior).
- **Backend**: zero diff, 280/280 passing in a fresh venv (no backend
  file touched).

### Files changed

`frontend/theme.css` only.

### Honest limitation

No real browser is available in this sandbox — actual scrollbar
rendering (slimness, hover contrast, whether 6px genuinely reads as
"slim" rather than "hard to grab," and whether the thumb is
sufficiently visible against both Light and Dark surfaces) could only
be reasoned through at the CSS-source level, not visually confirmed —
flagged for owner UAT.

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
