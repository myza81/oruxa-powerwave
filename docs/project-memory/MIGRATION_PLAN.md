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

Status: **Phase 0 design complete; governance cleanup complete; Phase 1
(COMTRADE-only) approved** — 2026-08-14. See DEC-012 through DEC-014 in
[DECISIONS.md](DECISIONS.md). **Implementation has not yet started** — Phase
1's approved *scope* is not the same as authorization to begin coding; see
[HANDOFF.md](HANDOFF.md) for the actual next step.

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
| **Phase 1 — COMTRADE-only upload + parsing + source/channel discovery** | **`[DECISION]` Approved — see [DECISIONS.md — DEC-014](DECISIONS.md#dec-014--phase-1-is-comtrade-only-csvexcel-and-import-wizard-grade-timestamp-handling-are-deferred-to-phase-15). Implementation not yet started.** |
| Phase 1.5 — CSV/Excel + Import-Wizard-grade timestamp handling | **Planned / not yet implemented.** Scope defined below (§16); not yet approved for implementation — do not begin without a separate, explicit go-ahead. |
| Phases 2–9 | Not started — see [POWERWAVE_DISCOVERY.md — Proposed Migration Phases](POWERWAVE_DISCOVERY.md#proposed-migration-phases) for the original high-level sequencing; Phase 0/1/1.5 below supersede that section's Phase-0/1 framing with concrete detail |

**Important scope correction (2026-08-14 governance cleanup)**: Phase 1 is
**COMTRADE only**. An earlier draft of this document left CSV/Excel
inclusion in Phase 1 as an open owner choice (§16 below originally
presented two options); the owner has since decided explicitly —
COMTRADE-only for Phase 1, with CSV/Excel deferred to Phase 1.5. §16 below
has been updated accordingly; see DEC-014 for the recorded decision.

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

### UAT-1: COMTRADE `.cfg`/`.dat` pairing UX

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

**Ready for owner approval but not yet recorded as `[DECISION]`**
(`[DECISION MODE: ANALYSIS]`, recommendation given, no further
comparison/testing needed to decide — these are implementation *details*
within the already-approved Phase 1 scope above, not yet individually
ratified):
- Provider/domain reuse classifications (§1) and target module map (§3).
- File upload/storage flow and request lifecycle (§5, §6).
- API contract shape (§7) and response-size discipline (§8).
- Error model and taxonomy (§9).
- COMTRADE upload *transport* mechanism — single multipart request (§10) —
  **note: this is the backend transport mechanism only, distinct from the
  frontend pairing UX below, which remains UAT.**
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
- **UAT-1: COMTRADE `.cfg`/`.dat` pairing interaction pattern — remains
  open.** The backend accepts the required pair together (§10's transport
  mechanism, reviewable above); the *browser-side* interaction (auto-pair
  by filename stem vs. two explicit named slots vs. another pattern
  discovered during implementation) is not decided and should be settled
  by hands-on testing, not by this document.
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
