# powerwave → oruxa_powerwave Discovery

This is the cumulative technical discovery record for the existing desktop
`powerwave` application. It answers one question only:

> **What does the existing `powerwave` actually do?**

It does **not** decide what `oruxa_powerwave` should do — that belongs in
[DECISIONS.md](DECISIONS.md). A finding recorded here is evidence for a
future decision, not a design requirement by itself. See "Discovery vs.
design" in [README.md](README.md). Anything below marked `[PROPOSAL]` or
`[OPEN]` is exactly that — not approved, not to be acted on without owner
sign-off.

Status: **first full pass complete**, 2026-08-14.

---

## Executive Summary

`powerwave` is a mature, ~46,200-line PyQt6/PyQtGraph desktop application
(`app/`) for power-system disturbance analysis, plus a ~13,800-line legacy
tree (`src/`) that is explicitly reference-only and not architecturally
authoritative (`docs/LEGACY_CODEBASE_POLICY.md`). Its canonical architecture
is unusually well documented (`docs/ARCHITECTURE.md`,
`docs/DATA_CONTRACT.md`, `docs/PROVIDER_PATTERN.md`, and others), and a prior
internal audit (`docs/CODEBASE_AUDIT_REPORT.md`, 2026-05-29) already
identified much of the architectural debt. This discovery pass independently
re-verified and extended that picture against the current code, and turned
up several places where the documentation itself is stale relative to the
implementation — flagged explicitly throughout rather than silently resolved.

Core findings that matter most for migration:

- The domain/engineering core is largely **Qt-free already**: providers
  (COMTRADE/CSV/Excel), the Import Wizard backend, the calculated-signals
  engine, the alignment engine, and most of `app/analytics/` have zero PyQt6
  imports and operate on plain NumPy/pandas/dataclasses. This is good news
  for reuse.
- The **session/state model** (`EventAnalysisSession`) is also Qt-free,
  window-owned (not a process-global singleton), and has genuinely useful
  properties for a backend port (non-destructive offsets, lazy alignment,
  full-resolution calculated signals) — but it has **zero concurrency
  control and no user/tenant concept**, and (until the most recent commit)
  no persistence.
- A commit (`3156392`) landed on `powerwave`'s `main` **during this audit**
  and materially changed the synchronization/session-persistence picture —
  several of this session's own earlier findings had to be corrected. This
  is itself a instructive data point: `powerwave` is actively developed, not
  a frozen reference, and any migration plan should expect to re-sync
  periodically.
- **oruxa_powerwave currently has zero domain code.** It is a clean,
  well-governed infrastructure foundation (FastAPI skeleton, storage
  abstraction, CI/CD, DEV/PROD isolation) with nothing to unwind before
  domain logic is introduced.
- Several genuine architectural debts exist in `powerwave` that a migration
  should **not** carry forward uncritically: a `src/`/`app/` split-brain,
  duplicated session/alignment concepts (`EventAnalysisSession` vs
  `MultiSourceSession`), three-way-fragmented cursor synchronization, dead
  code presented as if live in docs (`VisualizationManager`,
  `FlexiblePlotCanvas`, `FastWaveformWidget` which doesn't exist at all),
  and two non-communicating column/timestamp classification systems for
  CSV/Excel.
- Several **engineering-integrity-relevant gaps** exist today that a
  migration must consciously decide how to handle, not silently inherit:
  raw/original timestamp values are discarded after CSV/Excel normalization
  (no re-derivation path), timezone handling is fully inert, COMTRADE has no
  discontinuity/gap detection (unlike CSV/Excel), and true cancellation does
  not exist anywhere (cancel = disable button, or discard-on-arrival).

---

## Repositories and Versions Inspected

| | `powerwave` | `oruxa_powerwave` |
|---|---|---|
| Local path (macOS, this session) | `/Volumes/externalDrive/code-gym/powerwave/` | `/Volumes/externalDrive/code-gym/oruxa-powerwave` |
| GitHub remote | `https://github.com/myza81/powerwave.git` | `git@github.com:myza81/oruxa-powerwave.git` (config) — pushed via explicit HTTPS URL this session |
| Branch | `main` | `main` |
| HEAD at start of this audit | `a5c7289` | `7f57c16` |
| HEAD verified current with GitHub as of 2026-08-14 | `3156392` (fast-forwarded from `a5c7289` mid-session; see below) | see [HANDOFF.md](HANDOFF.md) for the exact commit this discovery lands on |

`powerwave` advanced by two commits during this project (`5f604ff` "repair
readme", then `3156392` "feat: add absolute multi-source time alignment and
persistence") between the project-memory-setup task and this discovery task.
`3156392` directly rewrote parts of the session/synchronization subsystem;
this document reflects the **re-verified state at `3156392`**, not the
earlier `a5c7289` snapshot — see the Synchronization section for the specific
corrections this required.

`powerwave` is a **read-only reference** for this project — see
[README.md](README.md). Nothing in `powerwave` was modified during this
audit.

---

## Existing `powerwave` Architecture

### Repository shape

- `app/` — canonical architecture. ~46,236 lines across 203 `.py` files.
- `src/` — legacy "PowerWave Analyst" codebase. ~13,757 lines across 33
  files. Per `docs/LEGACY_CODEBASE_POLICY.md`: "reference material,
  migration source, implementation knowledge source... NOT architectural
  authority." `app/` must not import from `src/`.
- `docs/` — an unusually thorough set of architecture-contract documents
  (`ARCHITECTURE.md`, `SYSTEM_OVERVIEW.md`, `REPOSITORY_STRUCTURE.md`,
  `DATA_CONTRACT.md`, `PROVIDER_PATTERN.md`, `VISUALIZATION_CONTRACT.md`,
  `VIEWPORT_RENDERING_POLICY.md`, `COMTRADE_NORMALIZATION_POLICY.md`,
  `CHANNEL_MAPPING_POLICY.md`, `PERFORMANCE_REQUIREMENTS.md`,
  `IMPORT_WORKFLOW_GUIDE.md` and related import docs,
  `CODEBASE_AUDIT_REPORT.md`, `LEGACY_CODEBASE_POLICY.md`). These documents
  describe the *intended* architecture and are frequently, but not always,
  accurate to the current implementation — every discrepancy found is
  flagged explicitly below rather than silently resolved either way.
- `config/*.yaml` (`timestamp_rules.yaml`, `column_mapping_rules.yaml`,
  `source_fingerprints.yaml`) — schemas for a persistent, operator-confirmed
  classification-learning system. All effectively empty at this commit (2
  confirmed rules total across all three files).
- `tests/` — ~4,850 tests total across `unit/`, `integration/`, `runtime/`,
  `acceptance/`, `stress/`, plus legacy-only `test_parsers/`, `test_engine/`,
  `test_ui/` (see Test Coverage section).

### Actual (not aspirational) major-component map

| Component | Location | Qt coupling |
|---|---|---|
| App entry point | `app/main.py` | Yes (bootstraps `QApplication`, sets `pg.setConfigOptions`) |
| Main window / UI orchestration | `app/ui/main_window/main_window.py` | Yes — also owns file-open routing, threading dispatch |
| Data contract | `app/models/*.py` (`DisturbanceRecord`, `AnalogChannel`, `DigitalChannel`, `RecordingMetadata`, `SamplingInformation`, `TimingInformation`, `DisturbanceInformation`) | No |
| Providers (COMTRADE/CSV/Excel) | `app/providers/{base,comtrade,csv,excel}/` | No |
| Import Wizard backend | `app/import_wizard/*.py` (27 files) | No |
| Import Wizard UI | `app/ui/import_wizard/*.py` | Yes |
| Session / alignment state | `app/sessions/*.py` (`EventAnalysisSession`, `session_models.py`, `alignment_engine.py`, `absolute_alignment.py`, `alignment_summary.py`, `timing_compatibility.py`) | No |
| Calculated signals | `app/calculated_signals/*.py` (engine) + `app/ui/calculated_signals/*.py` (dialogs) | Engine: no. UI: yes |
| Visualization / rendering | `app/visualization/{widgets,overlays,managers,rendering}/*.py` | Mostly yes (PyQtGraph-native); pure-computation submodules (`rendering/downsampling.py`, `rendering/digital_transforms.py`, `interaction/measurement_engine.py`, `axis_management.py`, `channel_grouper.py`, `engineering_display.py`, `viewport_policy.py`) are Qt-free |
| Session canvas orchestration | `app/ui/session/*.py` (`session_canvas_controller.py`, `session_panel.py`, `source_row_widget.py`) | Yes |
| Analytics | `app/analytics/{correlation,events,fault,frequency,harmonics,phasor,phasors,protection,quality,rms,rocof,scaling,suggestions}/` | No (except `suggestions/`, which is UI-state-coupled logic without a direct PyQt import) |
| Manifest persistence | `app/data/{manifest_loader,manifest_generator,multi_source_session,display_alignment}.py` | No |
| `app/synchronization/` package | `app/synchronization/`, `cursor/`, `managers/`, `viewport/` | **Empty scaffolding — all four `__init__.py` are 0 bytes.** Do not point migration work here; real sync logic lives in `app/sessions/` and `app/visualization/managers/synchronization_manager.py`. |

**Documentation-vs-implementation discrepancies confirmed** (report both
sides, per governance — not silently resolved):

- `docs/ARCHITECTURE.md`, `docs/VISUALIZATION_CONTRACT.md`,
  `docs/VIEWPORT_RENDERING_POLICY.md` describe `FlexiblePlotCanvas` +
  `DigitalEventTimeline` + `VisualizationManager` + `MultiAxisManager` as the
  canonical rendering architecture. **These are dead code** — `main_window.py`
  never imports or instantiates any of them; the actual live path is
  `SessionCanvasWidget` + `SessionCanvasController` + `EventAnalysisSession`.
  `main_window.py` contains the comment *"Single-record → session loader
  (replaces FlexiblePlotCanvas paths)"*.
- `docs/VIEWPORT_RENDERING_POLICY.md:14` names
  `app/visualization/widgets/fast_waveform_widget.py` as the "authoritative
  implementation reference." **This file does not exist anywhere in the
  repository.**
- `docs/VIEWPORT_RENDERING_POLICY.md` mandates `useOpenGL=True` as REQUIRED.
  Actual code (`app/main.py:11-22`) defaults OpenGL **off**, gated by an
  env var (`POWERWAVE_USE_OPENGL`).
- `docs/REPOSITORY_STRUCTURE.md` documents `app/analytics/` as
  `{phasors,harmonics,frequency,transients,events,impedance,power_quality,common}/`.
  The actual directories are
  `{correlation,events,fault,frequency,harmonics,phasor,phasors,protection,quality,rms,rocof,scaling,suggestions}/`
  — see Measurements section for the full reconciliation, including two
  confirmed-empty stub directories (`phasor/` singular, `rocof/`).
- `docs/CODEBASE_AUDIT_REPORT.md` (2026-05-29) is itself now partially stale
  in places — e.g. it frames COMTRADE loading as lacking any progress UX,
  but the current code has an async `QRunnable` + cancellable progress
  dialog (see File Import Pipeline section). Each such case is flagged at
  point of use below rather than treated as still-current.

### Actual dependency flow (observed, not the idealized layered diagram)

```text
File select (main_window.py, suffix-based routing — the routing DECISION
itself lives inside Qt-coupled code, not a reusable backend router)
        │
        ├── COMTRADE ─→ ComtradeProvider.load() (sync function, dispatched
        │                off the UI thread via QRunnable)
        │
        └── CSV/Excel ─→ ImportWizardWidget (embedded QWidget, not a modal
                          dialog despite the file being named
                          import_wizard_dialog.py) → app/import_wizard/*
                          pipeline (sync functions, dispatched off the UI
                          thread via QRunnable)
                          │
                          ▼
                    DisturbanceRecord (app/models) — the single normalized
                    contract for all three formats
                          │
                          ▼
                    EventAnalysisSession.add_source() — Qt-free session/
                    alignment state, window-owned (one per PowerwaveMainWindow)
                          │
                          ├──→ SessionCanvasController / SessionCanvasWidget
                          │    (PyQtGraph rendering, cursor/X-range sync)
                          │
                          ├──→ app/analytics/* (RMS, harmonics, phasors,
                          │    events, fault, protection, correlation,
                          │    quality, scaling — synchronous, on-demand,
                          │    Qt-free)
                          │
                          └──→ app/calculated_signals/* (Qt-free expression
                               engine, full-resolution, session-scoped)
```

---

## Existing `oruxa_powerwave` Architecture

Verified directly (not via subagent) on 2026-08-14; confirmed unchanged
since an earlier direct inspection this session (`git log` on
`backend/`/`frontend/`/deploy files shows no commits since the last
infrastructure work, only this session's own documentation commits).

### Backend

- FastAPI app via factory (`backend/app/main.py::create_app()`), so
  importing the module has zero side effects — settings resolved and
  storage constructed only inside `create_app()`/`lifespan`.
- One route: `GET /health` → `{"status": "ok", "environment": ...}`.
- Configuration (`backend/app/config.py`): `Settings` is a frozen dataclass;
  `load_settings()` is the **only** place that reads `os.environ`; fails
  fast with `ConfigurationError` on missing `STORAGE_PATH` or missing
  `CORS_ORIGINS` when `ENVIRONMENT=production`.
- Storage (`backend/app/storage.py`): `StorageBackend` ABC, one
  implementation `LocalStorage`. Two invariants enforced in code (not just
  documented): filenames cannot escape the storage root (path-segment
  validation + resolved-path containment check), and files in the
  `original` category are write-once (`ImmutableFileError` on overwrite
  attempt). Categories: `original`, `working`, `exports`, `temporary`.
- Dependencies pinned: `fastapi==0.141.1`, `uvicorn[standard]==0.52.1`,
  `psycopg[binary]==3.3.4` (PostgreSQL driver pinned now; **no schema or
  migrations exist yet**).
- Tests: `backend/tests/{test_config,test_main,test_storage,test_compose_config,test_frontend_entrypoint}.py`
  (783 lines total).

### Frontend

- No framework. `frontend/index.html` + `frontend/config.js`, one button
  that calls `/health` and prints the JSON response. No routing, no state
  management, no charting/plotting library present at all.
- `config.js` is regenerated at container startup from `API_BASE_URL`
  (`frontend/docker-entrypoint.d/10-powerwave-config.sh`), so one built
  image can be promoted DEV → PROD without a rebuild.

### Deployment

- `compose.yaml` (portable base, no host paths/ports/UID/GID) +
  `compose.dev.yaml` / `compose.prod.yaml` overlays. DEV and PROD run as
  isolated Compose projects (`powerwave-dev` / `powerwave-prod`) with
  non-overlapping ports (8200/8201 DEV, 8100/8101 PROD, verified in CI) and
  separate storage paths.
- `.github/workflows/ci.yml`: backend tests + Compose-overlay validation on
  every push/PR, including an explicit assertion that DEV/PROD render as
  isolated projects (distinct image tags, non-overlapping ports, no
  `container_name`).
- `.github/workflows/deploy.yml`: manual `workflow_dispatch` only (`dev` or
  `prod` target); re-runs tests; deploys by Git SHA (`git checkout --detach`
  on the VPS); fails fast if `VPS_APP_PATH` isn't configured for the target
  GitHub Environment.
- PostgreSQL is architecturally planned (per
  `docs/architecture/oruxa-architecture.md`) but not yet provisioned/used by
  this repository's code.

### What's already suitable and should not be rebuilt

- The configuration/storage/deployment foundation is solid and
  Powerwave-domain-agnostic — a future COMTRADE/CSV/Excel upload feature can
  sit directly on top of the existing `StorageBackend` abstraction (the
  `original`/write-once category is already exactly the right shape for
  "immutable original engineering files," see Original Source Immutability
  section) without needing new storage infrastructure.
- CI/CD, DEV/PROD isolation, and the manual-deploy-by-commit-SHA model are
  already fully built and require no changes to support domain features.

---

## File Import Pipeline

Two structurally distinct pipelines exist for getting a file into a
`DisturbanceRecord`, plus a third (manifest reload) that reuses the first
two's backends.

### Direct provider path (`app/providers/{base,comtrade,csv,excel}/`)

- Synchronous functions, no Qt. Raise `ProviderLoadError` on failure
  (`ProviderManager.load()` wraps any exception into a consistent message).
- **COMTRADE** (`comtrade_provider.py`): `_parse_cfg()`, `_parse_ascii_dat()`
  / `_parse_binary_dat()`, `_build_record()`, entry point
  `ComtradeProvider.load()`. Binary DAT read via `np.fromfile` (a fix
  already landed vs. the legacy `src/` parser's full `read_bytes()`); still
  a **full single-shot read**, not chunked/streamed. ASCII DAT is read fully
  into text then re-parsed via `StringIO` (two transient in-memory copies).
  BINARY32 is explicitly rejected before record construction (and
  redundantly checked again inside `_build_record()` — the second check is
  unreachable dead code given the first).
- **CSV/Excel direct providers** (`csv_provider.py`, `excel_provider.py`):
  single full `pd.read_csv`/`pd.read_excel`, no chunking. **Still live**, but
  no longer reachable from interactive file-open (see below) — only reached
  via manifest reload of a raw (non-normalized) `csv`/`excel` source type.
  Automatic Excel sheet selection, no user-facing picker (confirms audit
  M3, still current). `.xls` is nominally accepted by suffix filters but
  `ExcelProvider.load()` immediately raises for it (no `xlrd`); this
  suffix/support mismatch (audit M2) is confirmed still present.

### Import Wizard backend (`app/import_wizard/*.py`, 27 files)

- A "never raises" Result-object pipeline: every stage appends
  `ValidationMessage(severity, code, message)` objects rather than throwing.
  No PyQt imports anywhere in this directory (grep-confirmed) — genuinely
  reusable backend logic, matching `docs/IMPORT_WORKFLOW_GUIDE.md`'s claim.
- Profiling is genuinely sampled (`csv_profiler.profile_csv()` reads only
  `max_scan_rows`≈200 lines; `excel_profiler.profile_excel()` uses
  `openpyxl` `read_only=True` with `iter_rows(max_row=...)`), but the actual
  import-execution stage (`_load_full_dataframe()`) does a full, unchunked
  `pd.read_csv`/`pd.read_excel` — same memory profile as the direct
  providers once execution actually happens.
- Timestamp handling is materially richer than the direct-provider path —
  see Timestamp and Sample-Rate Handling section.
- `NormalizedDataset` (`normalized_dataset.py`) is the intermediate,
  auditable, still-tabular representation before the final
  `disturbance_record_bridge.py` conversion to `DisturbanceRecord`.

### Interactive routing (both paths converge at `main_window.py`)

- Single interactive entry point: `_open_unified_file()` →
  `_on_add_to_session()`. **All interactive CSV/Excel opens now route through
  the wizard** — confirming audit finding H2 is now closed for the
  interactive path specifically (the underlying `CsvProvider`/`ExcelProvider`
  classes are still directly reachable via manifest reload, so the *class*
  isn't fully isolated, but the interactive bypass the audit worried about
  is gone).
- COMTRADE: `_start_comtrade_load()` dispatches an async `_ComtradeLoadWorker(QRunnable)`
  on a `QThreadPool`, with a `QProgressDialog` (indeterminate busy-spinner,
  not a real percentage) offering "Cancel." **Cancellation does not stop
  parsing** — it's request-ID-based discard-on-arrival; the worker may still
  finish in the background and its result is simply ignored. Only one
  COMTRADE load may be in flight at a time (a second request is rejected,
  not queued). No preview/review step exists before the parsed record is
  displayed (confirms audit H4's substance, though the *lack-of-progress-UX*
  framing in the audit is now outdated — there is real async + a progress
  dialog).
- CSV/Excel: `ImportWizardWidget` is a `QWidget` embedded via
  `setCentralWidget()`, **not a modal dialog** — a naming/behavior drift from
  the file's own name (`import_wizard_dialog.py`) and from how the prior
  audit referred to it ("ImportWizardDialog"). Runs `_ProfileWorker`,
  `_PlanAwarePipelineWorker`, `_ExportWorker` on `QThreadPool`. **No
  cancellation exists at all** — the Close/Cancel button is disabled while
  any of these run; the user must wait it out.
- **Error-surfacing asymmetry**: COMTRADE failures show a raw exception
  string in a `QMessageBox.critical` modal. CSV/Excel wizard failures are
  structured `ValidationMessage` objects (severity/code/message) rendered in
  a diagnostics panel — a materially better UX pattern that a web
  redesign should standardize on for both formats, not just carry the
  asymmetry forward.

### `_IntelligentLoadWorker` — confirmed dead code

`main_window.py:254-305` defines this `QRunnable`; its own docstring calls
it "unused dead code," and grep confirms it is never instantiated anywhere.

### Two non-communicating classification systems (new finding, not in the prior audit)

`config/{column_mapping_rules,source_fingerprints,timestamp_rules}.yaml`
back a persistent, operator-confirmed classification-learning system
(`app.data.intelligence.*`, `app.intelligence.rule_manager.RuleManager`).
This system is consumed **only** by the direct `CsvProvider`/`ExcelProvider`
classes — the Import Wizard's own `column_detector.py`/`timestamp_detector.py`
never reference `IntelligenceManager` or these YAML files at all
(grep-confirmed zero hits). Since interactive CSV/Excel opens now always go
through the wizard, **any operator-confirmed rules saved via
`RuleManager.save_confirmed_rows()` currently have no effect on the
interactive import experience.** This is a real, silent architecture gap —
worth a deliberate decision (unify, or drop) rather than porting both
systems as-is.

### Raw data retention

**No raw/source data is retained past normalization in any of the three
formats.** COMTRADE's raw int16/uint16 arrays are local variables, only
scaled physical values reach the `DataFrame`. CSV/Excel's `pd.read_csv`/
`pd.read_excel` result is local to the loader function; the only persisted
"raw" artifact anywhere is a **sampled preview** (`RawPreviewModel`, ≤50
rows), not the full original dataset. There is no "revert to raw" or
re-audit-against-original-file capability anywhere downstream of import
today.

---

## Internal Data Model

### `DisturbanceRecord` (`app/models/disturbance_record.py`) — the single contract

`@dataclass(slots=True)`, mutable, docstring explicitly states
`waveform_data` (a `pandas.DataFrame`) is "stored by reference — never
copied on construction." Fields: `metadata: RecordingMetadata`,
`waveform_data: pd.DataFrame`, `analog_channels: list[AnalogChannel]`,
`digital_channels: list[DigitalChannel]`, `sampling_info: SamplingInformation`,
`timing_info: TimingInformation`, `disturbance_info: DisturbanceInformation | None`.

- Constructed by all three providers plus `disturbance_record_bridge.py`
  (wizard path). Held by reference inside `SessionSource.record` for the
  life of the session.
- Serializability: metadata/channel/timing fields are plain-primitive
  dataclasses (JSON-able as-is, modulo `datetime` → ISO-string conversion).
  `waveform_data` is a `pandas.DataFrame` — needs explicit conversion
  (`.to_dict()`/parquet/etc.) for any web transport or persistence; nothing
  in the codebase does this today except the narrow
  alignment-state-only manifest persistence (see Synchronization section).
- No Qt references anywhere in `app/models/`.
- No global/module-level state — freshly constructed per load.
- **Aliasing risk to carry into a shared backend**: because
  `waveform_data` is never copied on construction and is read (not
  copied-on-write) throughout the session/rendering/analytics layers, a
  backend that ever caches or shares a `DisturbanceRecord` across
  requests/users must ensure nothing mutates it in place — no such mutation
  was found in `app/`, but the aliasing contract makes it easy to
  accidentally introduce one.

### `AnalogChannel` / `DigitalChannel` (`app/models/channels.py`)

Flat, mutable dataclasses — metadata only (`name`, `unit`, `index`, `phase`,
`scale`, `offset`, `primary_ratio`/`secondary_ratio`, `parameter_type` for
analog; `name`, `index`, `normal_state` for digital). No sample data lives
here — samples live only in `DisturbanceRecord.waveform_data` columns keyed
by channel name. Fully JSON-serializable.

### `RecordingMetadata`, `SamplingInformation`, `TimingInformation`, `DisturbanceInformation` (`app/models/{metadata,timing}.py`)

All plain, mutable dataclasses. `TimingInformation.start_time`/`trigger_time`
are `datetime` (need ISO-string conversion for JSON). `TimingInformation.timezone`
exists as a field but **is never set to a non-`None` value by any current
provider** (see Timestamp section).

### `src/models/` (legacy) — confirmed materially different, not just a copy

The legacy `DisturbanceRecord`/`AnalogueChannel`/`DigitalChannel` in `src/`
differ from `app/models/` in **storage model** (per-channel raw
`np.ndarray` ownership on the channel object in `src/`, vs. a single shared
columnar `DataFrame` in `app/`), **validation strictness** (`src/`'s
`__post_init__` raises on invalid nominal frequency/sample rate; `app/`'s
has no `__post_init__` at all, only an opt-in non-raising `validate()`),
and **caching** (`src/`'s record carries stateful `_rms_cache`/`_phasor_cache`
dicts; `app/`'s has none). This is deeper duplication than "same concept,
newer name" — confirms and extends the prior audit's C2/H1 findings. Not
architecturally relevant to migration since `src/` is reference-only, but
important to know so no one accidentally treats a `src/` class signature as
authoritative.

### `app/data/` — a second, largely-independent data/session layer

- `SourceRecord`/`MultiSourceSession` (`multi_source_session.py`) — see
  Session and State Management section for how this relates to
  `EventAnalysisSession`.
- `SignalMetadata` (`signal_metadata.py`) — `@dataclass(frozen=True, slots=True)`,
  per-channel display/classification metadata not storable on the "locked"
  `AnalogChannel` contract (electrical_type, phase_reference,
  nominal_voltage, confidence, measurement_kind). Fully serializable.
- `display_alignment.py` — pure functions
  (`determine_reference_start`/`compute_relative_offsets`/`build_aligned_display_time`),
  a **duplicate** alignment algorithm parallel to `app/sessions/alignment_engine.py`,
  reachable only through the deprecated `VisualizationManager` path. Confirmed
  unchanged by the recent commit.

---

## Session and State Management

### `EventAnalysisSession` (`app/sessions/event_session.py`) — the canonical, live session model

- Plain class (not a dataclass), module docstring states and grep confirms
  it is Qt-free.
- Constructor initializes purely in-memory, per-instance state:
  `_sources: dict[str, SessionSource]` (keyed by a freshly minted
  `uuid.uuid4()` per load — **not** stable across saves, see below),
  `_channels`, `_panels`, `_quality_cache`, `_alignment_notes`, and the
  calculated-signals registry (`_calc_signals` + three dependency-index
  dicts).
- **Ownership: window-owned, not a singleton.** `PowerwaveMainWindow._active_session`
  is (re)assigned per new-session/open action — classic one-instance-per-window
  state, not process-global.
- `build_aligned_data()` — the render-data-production method: reads
  `record.waveform_data` fresh on every call, applies the source's
  `time_offset_s`, clips to the requested range, decimates above
  `max_points` (default 4000). **Not cached** — every pan/zoom/repaint
  recomputes from source arrays. A real cost concern for a web backend
  serving many more, more frequent viewport requests than a single desktop
  repaint loop.
- `SessionSource`, `SessionChannel`, `PanelConfig`, `AlignedChannelData`,
  and related dataclasses (`session_models.py`) are all plain, Qt-free,
  constructed exclusively by `EventAnalysisSession` methods.

### `MultiSourceSession` (`app/data/multi_source_session.py`) — a second, parallel session concept

Reachable only via `app/data/manifest_loader.py::build_session_from_manifest()`
→ the deprecated `VisualizationManager` display path — **not** the live
interactive session flow (which instantiates `EventAnalysisSession`
directly). As of the recent commit, this class's role changed: it is now
also the **carrier of persisted alignment state** across the manifest ↔
live-session boundary (a new `SessionAlignmentState` dataclass — see
Synchronization section) — so the duplication didn't disappear, but its
scope narrowed to specifically bridging saved-manifest alignment data into a
freshly built `EventAnalysisSession`, via a third code path in
`main_window.py` (`_restore_manifest_alignment()`).

> **`[PROPOSAL]`** Any migration should treat `EventAnalysisSession` as the
> canonical session contract to port, and `MultiSourceSession`/
> `display_alignment.py`/the manifest-loader-to-`VisualizationManager` path
> as legacy/compatibility-only — mirroring the existing internal audit's
> guidance on `VisualizationManager`. Not yet an approved decision.

### Risks for reuse inside a shared multi-user web backend process

- **No concurrency control, no tenant concept.** `EventAnalysisSession`
  itself has no static/module-level mutable state (so multiple instances
  can safely coexist in one process), but it also has no locks, no
  async-safety, and no user/session-id boundary anywhere in the domain
  model (`RecordingMetadata`, `DisturbanceRecord`, `SessionSource` all lack
  an owner/user/account field). Multi-user isolation would need to be built
  entirely at the web-backend layer (one session instance per authenticated
  user, never shared).
- **Source identity is fresh-per-load, not stable.** `SessionSource.source_id`
  is a new `uuid.uuid4()` every time a source is added — this is exactly
  why the new manifest-persistence feature needed a separate, stable
  **manifest** `source_id` and an explicit translation map
  (`manifest_id_to_live_id`) at reload time (`main_window.py:1291-1409`). A
  web backend designing its own source-identity scheme should learn from
  this rather than assume the live in-process UUID is a durable identifier.
- **No serialization method exists on the core session/data classes.**
  `dataclasses.asdict()` would not cleanly handle the embedded
  `pd.DataFrame`/`np.ndarray`/`datetime` fields. The one persistence path
  that does exist (alignment state via the manifest) is narrow and
  purpose-built, not a general session-serialization facility.
- **`DisturbanceRecord.waveform_data` aliasing** (see Internal Data Model
  section) — the same caution applies at the session layer: `SessionSource.record`
  holds the same live reference throughout the session's lifetime.

---

## Synchronization Architecture

**Note on scope**: this section was independently re-verified against the
current commit (`3156392`) after a prior investigation (at `a5c7289`) had
already covered this subsystem — the intervening commit directly rewrote
parts of it. Ten specific prior claims were re-checked one by one; the table
below records the outcome. Full detail follows.

### Re-verification outcome

| # | Claim (from the earlier pass) | Verdict at `3156392` |
|---|---|---|
| 1 | Alignment is a lazy per-source scalar offset (`SessionSource.time_offset_s`), never mutates `waveform_data`, fully reversible | **Still accurate** |
| 2 | Global time range = intersection of shifted source ranges, union fallback | **Still accurate** |
| 3 | Offset methods manual/auto_trigger/correlation/imported; `imported` unused | **Now inaccurate** — `imported` is live (see below) |
| 4 | "Set as Reference" re-zeros and re-tags method as `manual` | **Now inaccurate** — this was a bug, now fixed to preserve method |
| 5 | No session/alignment persistence exists anywhere | **Now inaccurate** — full manifest round-trip persistence now exists |
| 6 | `MultiSourceSession` is a second, independent, parallel session/alignment concept | **Now incomplete** — still true, but it also now carries persisted alignment state |
| 7 | Cursor sync fragmented three ways (`_hover_cursor` vs `_cursor_a`/`_cursor_b`) | **Still accurate** |
| 8 | `app/synchronization/` is empty scaffolding | **Still accurate** |
| 9 | No mode-awareness in the alignment/offset code path itself | **Now incomplete** — the new automatic absolute-alignment path does gate on timing-reference class; manual/auto_trigger/correlation offset-setting still has none |
| 10 | Different sample rates: no forced resampling for display | **Still accurate**, and the new viewport-policy code explicitly disclaims resampling too |

### Core mechanism (unchanged, claims 1 and 2)

Multi-source alignment is a **per-source scalar offset**
(`SessionSource.time_offset_s`), applied lazily at render time
(`build_aligned_data()` → `alignment_engine.apply_time_offset()` →
`time_array + offset_s`, a new array each call) — raw `waveform_data` is
never mutated. `EventAnalysisSession.get_global_time_range()` computes the
intersection of offset-shifted source ranges, falling back to the union if
no overlap. Fully reversible via `reset_all_offsets()`.

Offset-determination methods (`ALIGNMENT_METHODS`): `manual` (analyst
typed/dragged), `auto_trigger` (per-source RMS-threshold trigger detection —
independent per source, no cross-source anchor), `correlation` (FFT
cross-correlation, confidence-gated at ≥0.70, `app/analytics/correlation/cross_correlator.py`),
`imported` (now live — see below), and the new `absolute_timestamp` (see
below).

### What changed: absolute multi-source time alignment (`app/sessions/absolute_alignment.py`)

- **New concept**: `EventAnalysisSession.absolute_time_origin: datetime | None`
  — the wall-clock instant session `x = 0` denotes. Established once, from
  the earliest **anchored** source, once ≥2 anchored sources exist. Adding
  an earlier-starting source afterward produces a negative offset rather
  than moving the origin — origin stability is deliberate, so already-placed
  waveforms never silently shift when a new source is added.
- **Not a replacement for the scalar-offset model** — it's a policy layered
  on top: it *derives* offsets for eligible sources and serves as the axis
  reference; `time_offset_s`/`build_aligned_data()` themselves are
  untouched.
- **"Anchored"/"eligible"**: a source is eligible when
  `TimingInformation.start_time` is set and
  `timing_compatibility.classify_timing_reference()` returns
  `ABSOLUTE_AWARE` or `ABSOLUTE_NAIVE` (excludes elapsed/synthetic/
  sample-index/epoch-sentinel-downgraded sources — see Timestamp section for
  how the sentinel check works). This reuses, rather than duplicates, the
  existing timing-classification module.
- **Analyst intent is protected**: only sources whose `alignment_method` is
  `"none"` or `"absolute_timestamp"` get offsets auto-derived; a
  `manual`/`auto_trigger`/`correlation`/`imported` source is explicitly
  skipped and left untouched.
- `rebase_absolute_time_origin(offset_s)` — moves the origin when "Set as
  Reference" translates the whole session (see below); a no-op while no
  origin exists.

### Bug fix confirmed: "Set as Reference" no longer discards alignment method

Previously, "Set as Reference" re-zeroed one source and shifted the others,
re-tagging every source's method as `"manual"` — discarding the fact that a
source's offset had actually come from `auto_trigger`/`correlation`/etc.
This is now fixed: the method (and confidence) is explicitly preserved
across the rebase, and `rebase_absolute_time_origin()` is called so the
absolute-axis origin advances consistently with the translation.

### Bug fix confirmed: axis-label regression (`_compute_session_reference_time`)

Not something either prior investigation was explicitly asked to check, but
directly relevant to engineering integrity. The old implementation
re-derived the X-axis wall-clock label every repaint as
`min(start_time − time_offset_s)` across all sources — meaning adjusting
*one* source's offset by e.g. +250ms would, because of the `min()`, silently
relabel the *entire axis* in the opposite direction, effectively canceling
out the visible effect of the analyst's own adjustment on every other
source's displayed position. This is fixed: when `absolute_time_origin` is
set, that stable value is used directly as the axis origin; the old
`min()`-based derivation survives only as a fallback for sessions with no
explicit origin. Covered by a dedicated regression test suite
(`tests/unit/test_session_time_origin.py`, 15 documented cases).

### Persistence — now real, narrowly scoped

Full round-trip persistence for **alignment state** (not general session
state) now exists via the manifest (a YAML file):

- **Saved**: `absolute_time_origin`, `offsets_seconds`, `methods`,
  `confidences`, `notes` — keyed by a **stable manifest `source_id`**
  (distinct from the fresh-per-load live UUID).
- **Loaded and applied**: `main_window.py` builds a
  `manifest_id_to_live_id` map while adding sources, then translates the
  persisted alignment data onto the live session.
- **Precedence rule, confirmed exactly**: saved geometry always wins over
  re-derivation. A post-reload cross-correlation pass still computes and
  displays results but does not auto-overwrite restored offsets when the
  manifest already carried saved offsets. A legacy/hand-written manifest
  with offsets but no recorded origin is honored verbatim — no origin is
  invented, and automatic absolute-alignment is skipped entirely for that
  load.
- **Import-Wizard sources reload through the wizard backend** (confirmed):
  `normalized_csv`/`normalized_excel` manifest source types re-run
  `run_import_pipeline()` rather than the raw `CsvProvider`/`ExcelProvider`,
  so canonical channel names/units/parameter types survive a save/reopen
  cycle. **Documented limitation** (the code's own comment, not an
  inference): a manual override the analyst made inside the Wizard UI
  (explicit timestamp format, column exclusion) is *not* persisted and gets
  re-derived by auto-detection on reload — a real, acknowledged risk if the
  source file is ambiguous enough for auto-detection to land differently a
  second time.
- `EventAnalysisSession.session_version`/`created_at` — described in the
  class docstring as unused "Persistence hooks (Enhancement 2)." This is
  now only *partially* accurate: real persistence exists, just not via these
  specific fields, and not for general session state (channel selections,
  panel layout, calculated signals) — only for alignment.

### Cursor synchronization — still fragmented three ways, unaffected by the recent commit

Confirmed via a full diff review of `session_canvas_controller.py` (143
changed lines, none touching cursor-sync code) that this is unchanged:

1. **`_hover_cursor`** — a passive crosshair, synced across panels via
   `SynchronizationManager` (`app/visualization/managers/synchronization_manager.py`),
   which extracts `_cursor` first and falls back to `_hover_cursor` (the
   fallback itself was a prior fix, still in place).
2. **`_cursor_a`/`_cursor_b`** — two analyst-placed measurement cursors,
   synced via a **completely separate, hand-wired** mechanism directly
   inside `SessionCanvasController` (custom `cursor_a_moved`/`cursor_b_moved`
   Qt signals, gated by `self._cursor_sync`), bypassing `SynchronizationManager`
   entirely.
3. `app/synchronization/` and subpackages remain empty scaffolding — the
   real logic lives in `app/sessions/` (Qt-free) and
   `app/visualization/managers/synchronization_manager.py` +
   `app/ui/session/session_canvas_controller.py` (both Qt-coupled).

> No single component owns "cursor + range state" for the app as a whole.
> A migration should treat this as a design problem to solve once, not a
> pattern to carry forward — the *algorithms* (rate-limited broadcast,
> avoid-echo-loop via a depth guard) are reusable ideas; the split
> implementation is not.

### Different sample rates — no forced resampling, confirmed still true

`build_aligned_data()` processes each channel independently on its own
native sample positions; there is no shared/common time grid for
**display**. Resampling machinery (`alignment_engine.resample_to_grid()`,
`build_common_time_grid()`) exists but is used only by the Calculated
Signals numeric engine and the correlation module — not the display/sync
path. The new `viewport_policy.py` module explicitly disclaims interpolation
too ("No Qt, no session mutation, no offset writes, no record modification,
no resampling, no interpolation") and its geometry helpers return only real
recorded samples, never interpolated ones.

### New: `viewport_policy.py` — initial camera position only, not data domain

A clean separation the module docstring itself insists on:
`SessionCanvasController._session_window()` (the actual **data domain** fed
to `build_aligned_data`, analytics, the navigator strip, "Fit All") is
completely untouched by this feature. `viewport_policy.select_initial_viewport()`
computes a one-time **initial viewport** (event-focused, for mixed-rate,
≥2-source sessions) applied once per session on first activation and never
re-snapped over an analyst's own zoom/pan afterward — later canvases
created by a panel split/merge inherit whatever range is already on screen.
Zero interaction with the decimation pipeline.

### Mode-awareness — now partially present

The general offset-setting API (`set_time_offset()`) still has zero
awareness of timing mode (absolute/relative_elapsed/synthetic_elapsed/
sample_index) — `alignment_engine.py` is unchanged and doesn't branch on it.
But the *new automatic* absolute-alignment path
(`absolute_alignment.py::is_eligible()`) does gate on
`timing_compatibility.classify_timing_reference()`, reusing rather than
duplicating that classifier. `timing_compatibility.py` itself remains
advisory-only for the general timing-compatibility banner shown to the
analyst — it still does not structurally prevent a sample-index-mode source
from being offset-aligned against a real time-based source; that protection,
where it exists, is workflow/UI discipline plus (now) the new eligibility
gate for the *automatic* path specifically.

**`[OPEN]`** Whether the general `set_time_offset()` API should gain the
same mode-awareness the new automatic path has (or whether relying on UI
discipline plus the automatic-path gate is judged sufficient) was not
addressed by this commit and is worth a product decision before any web port
re-implements offset-setting from scratch.

---

## Timestamp and Sample-Rate Handling

### The five time-axis modes and how they're actually decided

Per `docs/DATA_CONTRACT.md`: auto-detected, absolute, relative elapsed,
synthetic elapsed, sample-index. **This detection machinery is entirely
CSV/Excel Import Wizard territory** — COMTRADE never goes through it (its
`timing_reference` is always the dataclass default, `"absolute"`, by
construction — the provider raises rather than falling back on any
unparseable date, so that default is always trustworthy for COMTRADE
specifically).

- `app/import_wizard/timestamp_detector.py::infer_timestamp_format()` votes
  among a fixed list of `strptime` formats plus epoch-seconds/epoch-ms/Excel-serial
  detection.
- `_detect_elapsed_format()` — the relative-elapsed detector — is
  **name-gated** (column name must suggest elapsed time) plus requires ≥80%
  parse rate and strict monotonicity, and explicitly excludes ranges that
  look like epoch/Excel-serial numbers. This matches `DATA_CONTRACT.md`'s
  "conservative" requirement — confirmed, not just claimed.
- Synthetic-elapsed and sample-index modes are **user-invoked fallback
  strategies**, not auto-detected from data content.
- Strategy execution (12 `TimestampRepairStrategy` values,
  `timestamp_repair_executor.py`) includes: day-first-by-default ambiguous
  date resolution (flagged to the user via an INFO message, not silent), NaT
  interpolation in float-seconds space, reconstruction from a fixed interval
  when no usable column exists (`RECONSTRUCT_FROM_INTERVAL`, falls back to
  Unix epoch with a WARNING if nothing parseable exists at all), and hybrid
  low-res-anchor + sub-interval reconstruction (`RECONSTRUCT_HYBRID`,
  defaults to 50Hz with a WARNING if no rate/interval is given).
- **Diagnostics run on every result** but do not repair the underlying data:
  duplicate count, non-monotonic count, dominant-interval jitter, and a
  gap-based missing-sample estimate are reported, not corrected.
- **COMTRADE has no equivalent repair layer** — `_parse_timestamp()` raises
  `ProviderLoadError` on any unparseable date/time; there is no repair path
  for COMTRADE timestamps at all.

### Timezones — effectively inert

`TimingInformation.timezone` exists as a field but **is never set to a
non-`None` value by any current provider** — verified by the code's own
comment in `timing_compatibility.py`, not an assumption: "every
presently-producible record is timezone-naive." A `TIMEZONE_ALIGNMENT`
repair strategy exists in the executor but is **never referenced anywhere**
in the plan builder or wizard UI — dead/unreachable code. `DATA_CONTRACT.md`
lists timezone as a required metadata field; no current provider honors
that.

### Multi-rate COMTRADE sections — preserved correctly, and not via resampling

`SamplingInformation` correctly preserves per-section rates from the CFG's
`nrates` declaration as metadata. But the actual `waveform_data["time"]`
values are **not reconstructed from those declared rates at all** — each
row's timestamp comes directly from the per-sample `ts` field embedded in
the DAT file itself (scaled by `cfg.timemult`), so a genuine multi-rate
record's true per-sample spacing is preserved naturally, without any
resampling to a common rate. The CFG's declared rates are descriptive
metadata alongside, not the driver of, the empirically-derived time axis.

### Discontinuous sampling — CSV/Excel diagnoses it, COMTRADE does not

CSV/Excel: detected and *reported* (not corrected) via
`interval_inference.infer_interval()`'s gap/jitter analysis. **COMTRADE: no
equivalent discontinuity detection was found anywhere in the provider** — a
genuine data dropout in a COMTRADE record would silently carry into
`waveform_data["time"]` with no diagnostic surfaced, unlike the CSV/Excel
path.

> `[OPEN]` — a genuine gap in current `powerwave`, not something to
> silently fix during migration without a decision: should a web
> re-implementation add discontinuity detection to the COMTRADE path to
> match CSV/Excel's behavior, or is this an accepted current limitation?

### Raw timestamp traceability — discarded after normalization (CSV/Excel)

The original raw timestamp column's string/native values are **not**
carried forward into `NormalizedDataset`/`DisturbanceRecord` — only a
strategy-name string and a format-label string survive as provenance, not
the actual original values. "Raw source data is never mutated" (a real,
verified guarantee — the input DataFrame itself is untouched during
normalization) is not the same claim as "raw values remain available
downstream," and they should not be conflated. COMTRADE similarly discards
the raw integer microsecond `ts` field once converted to float seconds. For
elapsed/synthetic/sample-index modes, an additional linear interpolation
step (`disturbance_record_bridge.py::_build_elapsed_time_array()`) runs on
the elapsed-seconds series before it reaches `waveform_data["time"]` — an
easy-to-miss extra transformation beyond whatever the repair strategy
already applied.

> `[OPEN]` — if a web migration wants full audit/re-derivation capability
> (re-run normalization against the original values, or show an analyst
> exactly what was in the source file before repair), that capability does
> not exist in `powerwave` today and would need to be designed from
> scratch, not ported.

### Cross-check against `docs/DATA_CONTRACT.md`

| Contract requirement | Status |
|---|---|
| Elapsed-time detection conservative | ✅ Confirmed — name-gated + monotonicity + parse-rate gated |
| No absolute calendar meaning inferred from synthetic origin | ✅ Confirmed — sentinel origin (`2000-01-01`) is specifically recognized and excluded from "real anchor" classification |
| Timezone metadata populated | ❌ Never populated by any current provider |
| Timezone-aware handling supported | ❌ The one conversion code path (`TIMEZONE_ALIGNMENT`) is unreachable |
| Sample-index axis unit/labeling | ✅ Confirmed — `"sample"` unit and correct UI relabeling to "Sample Index" when all active sources are sample-index-timed |
| Per-source explicit timing-mode classification | ⚠️ Partial — COMTRADE is implicitly always-absolute by provider construction, never explicitly labeled; only the CSV/Excel wizard path actually sets `timing_reference` to a non-default value |

### The `2000-01-01` sentinel — the load-bearing detail behind "anchored" sources

CSV/Excel direct providers fall back to a fixed sentinel
(`datetime(2000, 1, 1)`) when no usable timestamp exists, **while still
leaving `timing_reference` at its `"absolute"` default** — meaning a naive
`"absolute"` label cannot be trusted at face value. `timing_compatibility.py::_has_real_anchor()`
exists specifically to catch this sentinel and refuse to classify such a
source as genuinely anchored. This is exactly what the new
`absolute_alignment.py` feature relies on for its "anchored source"
eligibility check — **any migration must preserve this sentinel-detection
behavior for equivalent alignment logic to work correctly**, not just the
happy-path timestamp parsing.

---

## Calculated Signals

A deliberately layered, Qt-free (except the creation dialog and
session-panel row widget) expression engine — unaffected by the recent
commit (no `app/calculated_signals/*` files changed).

- **Creation**: `CalculatedSignalDialog` → user binds 1+ analog channels to
  auto-assigned aliases (`A, B, C, …`), types a free-form expression. Grammar
  is a deliberate restricted AST allow-list — `+ - * / abs()` and
  parentheses only, never `eval()`/`exec()`/`compile()`. One bound input is
  the reference; others are linearly interpolated onto its time base.
  **Note**: `signal × signal` is blocked unless one operand is
  dimensionless, so common power-engineering formulas like `P = V × I ×
  cos(θ)` are **not currently expressible** — a real capability gap if a
  migration assumed richer built-in calculations already exist.
- **Cross-source**: explicitly supported — each variable binding is
  `(source_id, channel_name)`, resolved independently against its own
  source's own `time_offset_s`, then aligned onto the reference's time base.
  Calculated-signal-to-calculated-signal chaining is explicitly blocked.
- **Identity**: a `calc_id` UUID, never confused with a real channel —
  special-cased throughout (own registry on `EventAnalysisSession`, `"calc:"`-prefixed
  curve keys, `"ƒ "`-prefixed display names, `"(stale)"` suffix, a
  dedicated Session Panel section).
- **Storage**: purely in-memory on `EventAnalysisSession` (`_calc_signals`
  + forward/reverse dependency-index dicts) — never attached to a source's
  channel list or the `DisturbanceRecord` itself.
- **Full resolution, always**: the resolution service explicitly reads
  `DisturbanceRecord.waveform_data` directly and never calls the
  display-decimating `build_aligned_data()` — computed once over the full
  overlap of the underlying record(s), independent of any viewport.
- **Source removal**: dependent calculated signals are marked `STALE`, never
  silently deleted or recomputed with fabricated data — last-known-good
  results are preserved and keep rendering (labeled stale) until the
  dependency is restored or the user deletes the signal.
- **Deletion**: user-initiated only, with a destructive-action confirmation
  dialog; no automatic garbage collection.
- **Persistence**: **none exists** — the alignment-persistence commit did
  not touch calculated signals; they remain fully ephemeral, lost on
  session close.
- **GUI/backend split**: `app/calculated_signals/{models,expression,units,engine,resolver}.py`
  are entirely Qt-free and directly portable. The creation dialog and
  session-panel row widget are thin PyQt6 orchestration with (by their own
  docstrings) no calculation logic implemented in them at all.

---

## Waveform Rendering

The web frontend will almost certainly use different rendering technology —
this section identifies what behavior must be preserved, not what code to
port.

- **Stack**: PyQtGraph is the sole plotting library. The live path is
  `SessionCanvasWidget` + `SessionCanvasController`, **not** the
  documentation's `FlexiblePlotCanvas`/`VisualizationManager`/
  `DigitalEventTimeline`/`FastWaveformWidget` (dead code / nonexistent file
  — see Existing `powerwave` Architecture section).
- **Panel/channel routing**: decided in `EventAnalysisSession._infer_panel_for_channel()`
  (Qt-free) by priority: explicit parameter type → engineering unit →
  channel-name keyword match. Default panels: voltage, current, power,
  frequency, digital, other. **A second, independently-maintained,
  near-identical classifier** (`app/visualization/channel_grouper.py`)
  exists in parallel, used only by the dead `VisualizationManager` path — a
  duplication risk if a migration accidentally ports both.
- **Add/remove curves**: `SessionCanvasWidget.update_curve()` correctly
  reuses `PlotDataItem`s via `setData()` rather than recreating them (the
  documented "curve lifecycle law" is actually implemented here). Digital
  channels use a separate hi/lo-segment rendering path
  (`app/visualization/rendering/digital_transforms.py`, pure NumPy, no Qt).
- **Zoom/pan and decimation — the most significant documented-vs-actual
  gap found in this subsystem**: the documented policy mandates
  re-decimation on every viewport pan/zoom. The **live** path does not do
  this — `build_aligned_data()` decimates once against the **entire session
  window** (not the live viewport), and relies on PyQtGraph's own
  `setDownsampling`/`setClipToView` for interactive responsiveness — and
  those are applied **only to primary/left-axis curves**, not right-axis
  curves (current/power/frequency, per the routing above), a real, previously
  uncited rendering-fidelity asymmetry. The policy-compliant
  re-decimate-on-zoom implementation exists only in the dead
  `FlexiblePlotCanvas` path.
- **Cursor behavior**: see Synchronization section — three-way fragmented,
  confirmed still current.
- **Full-resolution data is always preserved**: decimation happens on a
  fresh array per call; the original `DisturbanceRecord`/DataFrame is never
  mutated or truncated. Analytics and Calculated Signals both read the same
  full-resolution source independent of what's currently displayed.
- **Multiple sample rates**: each channel keeps its own native sample
  positions on a shared time axis — no forced resampling for display (see
  Synchronization section for the authoritative detail, which applies
  identically here since it's the same `build_aligned_data()` code path).
- **A third, dead overlay abstraction**: `BaseOverlay`/`CurveStore`/
  `OverlayRegistry` (`app/visualization/overlays/`) is a clean,
  well-designed, PyQtGraph-coupled abstraction — but it is used **only by
  its own test suite**. The actual harmonic/phasor overlay rendering is
  duplicate, inline logic directly inside `SessionCanvasWidget`. Worth
  flagging since a migration team could easily mistake `overlays/` for "the"
  overlay architecture when it's unreachable from the live app.
- **`viewport_policy.py`** (new): a one-time initial-camera-position
  decision, cleanly decoupled from the data domain and decimation — see
  Synchronization section for full detail.

---

## Measurements and Engineering Analysis

`docs/REPOSITORY_STRUCTURE.md` documents `app/analytics/` as
`{phasors,harmonics,frequency,transients,events,impedance,power_quality,common}/`.
The **actual** directories, confirmed via `ls`, are
`{correlation,events,fault,frequency,harmonics,phasor,phasors,protection,quality,rms,rocof,scaling,suggestions}/`
— a real, previously-unreconciled discrepancy, reported as-is rather than
resolved. `phasor/` (singular) and `rocof/` are **confirmed-empty stub
directories** (0-byte `__init__.py`, nothing else) — do not confuse with the
populated `phasors/` (plural) or the ROCOF *display/classification* logic
that actually lives inside `frequency/rocof_overlay.py`.

None of these directories changed in the recent commit — unaffected,
findings carried forward as-verified.

| Directory | What it actually does | GUI dep. | Reuse potential |
|---|---|---|---|
| `correlation/` | Cross-source waveform correlation (FFT-based, same-event detection + alignment offset suggestion) | None | Reuse unchanged |
| `events/` | Automatic disturbance detection: voltage dip/swell, overcurrent, frequency deviation, zero-sequence injection, from baseline-relative thresholds | None | Reuse unchanged |
| `fault/` | Fault-type classification (SLG/LL/DLG/3-phase) via single-cycle DFT phasor + symmetrical components | None | Reuse unchanged |
| `frequency/` | **Classification/routing only** — explicitly does *not* compute frequency or ROCOF from waveforms; assumes pre-computed Hz/Hz-s channels arrive from source data | None (but presentation-adjacent) | Classification heuristics reusable; no computation exists to port |
| `harmonics/` | Real DSP: sliding-window FFT, per-order RMS magnitude, THD/individual-harmonic-distortion | None | Reuse unchanged — most substantial, well-specified module in the codebase |
| `phasor/` (singular) | **Empty stub** | — | Nothing to reuse |
| `phasors/` (plural) | DFT phasor extraction, symmetrical components (Fortescue transform), NSVUF unbalance factor | None | Reuse unchanged |
| `protection/` | Relay-timing-milestone extraction (fault inception → pickup → trip → clear → reclose) from digital-channel transitions + current-extinction detection | None | Reuse unchanged; keyword-based digital classification may need per-deployment tuning (a config concern, not a blocker) |
| `quality/` | **Not power-quality metrics** — data-integrity/health checks (NaN%, sample-rate gaps, ADC clipping, SNR, DC offset). Misleading name vs. actual behavior. | None | Reuse unchanged |
| `rms/` | Sliding-window RMS envelope, cycle-based windowing (half/one/two-cycle), causal right-aligned time convention | None | Reuse unchanged — simplest, most foundational module |
| `rocof/` | **Empty stub.** No df/dt computation exists anywhere; ROCOF channels are assumed pre-computed from source data | — | Nothing to reuse |
| `scaling/` | Engineering unit scaling / per-unit normalization (RAW/PRIMARY/SECONDARY/PER_UNIT modes, correct √3 handling for phase-to-phase vs. phase-to-ground) | None | Reuse unchanged |
| `suggestions/` | **Rule-based next-best-action UI hints**, not a signal-analysis module — consumes other analytics' outputs plus current UI/dock-visibility state | No direct PyQt import, but architecturally coupled to desktop UI concepts (dock visibility, action-id→button-label pairs) | Reimplement for web — rule logic is portable, current shape isn't |

**Cursor-based measurement tools** (contrast with the `analytics/`
computation modules): the desktop widget `cursor_readout_bar.py` is
confirmed deleted; its responsibilities now live in
`app/visualization/interaction/measurement_engine.py` — pure NumPy,
explicitly documented as Qt-free, deliberately supports mixed sample rates
within one measurement (each curve keeps its own time array, nothing is
resampled onto a shared grid; energy computation is skipped rather than
approximated when voltage/current time arrays aren't identical). Presented
via the Qt-coupled `app/ui/widgets/measurement_panel.py`. Same clean
computation/presentation split as the rest of `app/analytics/`.

---

## Large Dataset Behaviour

- **Full in-memory loads, no chunking, anywhere**: COMTRADE binary
  (`np.fromfile`, single shot), COMTRADE ASCII (full text read + `StringIO`
  re-parse, two transient copies), CSV/Excel direct providers and the
  wizard's actual execution stage (`pd.read_csv`/`pd.read_excel`, no
  `chunksize`) all fully materialize the dataset. Only the wizard's
  *profiling/preview* stage is genuinely sampled/streaming.
- **Confirmed DataFrame copies** in `app/import_wizard/data_assembler.py`
  (raw dataframe `.copy()`, normalized-timestamp `.copy()`, selected-column
  `.copy()`) — multiple full-frame copies during import for large CSV/XLSX.
- **Rendering**: full-resolution data is always retained; decimation is
  applied to a fresh, freshly-computed array per call, not cached — see
  Waveform Rendering and Synchronization sections. `build_aligned_data()`
  recomputes clip+decimate from raw arrays on **every** call for every
  `(source_id, channel_name)` pair on every repaint — no viewport-slice
  cache exists anywhere.
- **"100MB+" support rests entirely on background-threading UI
  responsiveness plus vectorized NumPy/pandas operations — not on reduced
  memory footprint.** No path in `app/` implements true chunked/streaming
  full-data ingestion.

**Web migration risk translation**:

| Desktop behavior | Web equivalent risk |
|---|---|
| Full in-memory parse of a large COMTRADE/CSV file | Server process memory pressure per concurrent import; no existing chunking pattern to port |
| No viewport-slice caching, full recompute per paint | Would translate to a very chatty backend API (every pan/zoom = a fresh request) unless a caching layer is designed fresh |
| Full-resolution data always available for calculations | Good — this principle is worth preserving explicitly (see Full-Resolution Engineering Data Principle in the risks section) |
| Multiple full DataFrame copies during import | Duplicated-array memory cost would need to be budgeted per concurrent request in a shared backend process, unlike a single-user desktop process |

---

## Background Processing

**Only Qt's `QRunnable`/`QThreadPool` is used anywhere in `app/`** — zero
uses of `threading.Thread`, `multiprocessing`, `asyncio`, or
`concurrent.futures` were found. Two files define workers:

- `main_window.py`: `_ComtradeLoadWorker` (live, one-at-a-time, request-ID-gated
  discard-on-cancel — see File Import Pipeline section) and
  `_IntelligentLoadWorker` (confirmed dead code, never instantiated).
- `import_wizard_dialog.py`: `_ProfileWorker`, `_PlanAwarePipelineWorker`,
  `_ExportWorker` — all with **no cancellation at all**; the Close button is
  disabled while any of them run.
- Progress reporting everywhere is an **indeterminate busy-spinner**
  (`QProgressDialog`/`QProgressBar` with range `(0, 0)`) — never a real
  percentage.
- **Everything else (analytics, calculated signals, alignment, rendering
  decimation) runs synchronously on the UI thread.** `app/calculated_signals/resolver.py`'s
  own docstring states this explicitly: "Synchronous only... No QRunnable,
  QThreadPool, or other worker/thread infrastructure is used or assumed
  here."

> **Migration implication**: the existing async plumbing is not a pattern
> worth porting — it's a thin, imperfect wrapper around Qt's threading
> primitives with no true cancellation and no progress granularity. A web
> backend's job/task model (background workers, real progress, real
> cancellation) will need to be designed from scratch; `powerwave` offers no
> precedent to reuse here beyond "yes, keep parsing off the interactive
> path."

---

## Test Coverage

~4,850 `def test_` functions total across `tests/`. **A key, previously
un-flagged finding**: `tests/test_parsers/`, `tests/test_engine/`, and
`tests/test_ui/` (≈600 tests, ~15% of the corpus) exercise the **legacy
`src/` tree exclusively** — they import `parsers.comtrade_parser`,
`models.channel`, `engine.decimator`, `ui.unified_canvas`, etc., reachable
only because `pytest`'s `pythonpath` still includes `src` (a known
architectural-cleanup item per `docs/CODEBASE_AUDIT_REPORT.md` RC4). **These
are false signal for migration purposes** — green results there say nothing
about `app/`'s correctness and should be excluded from any "migration safety
net" selection. `tests/benchmarks/` contains no test files at all — an empty
placeholder directory.

| Directory | Files | Approx. tests | Character |
|---|---|---|---|
| `tests/unit/` | 130 | ~4,027 | The bulk of real `app/` coverage. 85 files have **zero** Qt import (pure engineering/data-logic — good migration-safety-test candidates: timestamp/timebase, calculations/analytics, parsing/providers, session/alignment). 45 files are Qt-dependent (widget/canvas/dialog tests — will not translate to a web app without a full rewrite). |
| `tests/integration/` | 6 | ~134 | End-to-end pipeline tests (import pipeline, normalized export, semantic-classification parity, manifest pipeline) — largely non-Qt, good candidates. |
| `tests/runtime/` | 12 | ~81 | Mostly Qt runtime/widget-behavior focused — largely GUI-specific. |
| `tests/acceptance/` | 1 | ~6 | — |
| `tests/stress/` | 2 | ~12 | Pure-logic stress tests (large CSV, malformed files) — good candidates. |
| `tests/test_parsers/`, `tests/test_engine/`, `tests/test_ui/` | 13 | ~598 | **Exercise legacy `src/` only — not migration-relevant.** |
| `tests/benchmarks/` | 0 | 0 | Empty placeholder. |

The 5 new test files from the recent commit
(`test_absolute_alignment.py`, `test_alignment_persistence.py`,
`test_manifest_normalized_sources.py`, `test_session_time_origin.py`,
`test_viewport_policy.py` — 121 tests total, none Qt-dependent) are all
good migration-safety candidates for the new alignment feature specifically.

---

## GUI / Domain Logic Separation

Cross-cutting summary (detail already given per-section above):

**Cleanly Qt-free today** (directly portable as backend logic, verified via
grep for PyQt6/pyqtgraph imports, not assumed): `app/models/*`,
`app/providers/*`, `app/import_wizard/*` (all 27 files), `app/sessions/*`
(`event_session.py`, `session_models.py`, `alignment_engine.py`,
`absolute_alignment.py`, `alignment_summary.py`, `timing_compatibility.py`),
`app/calculated_signals/{models,expression,units,engine,resolver}.py`,
`app/analytics/*` (all subdirectories except the UI-state-coupled
`suggestions/`), `app/data/{multi_source_session,display_alignment,manifest_loader,manifest_generator,signal_metadata}.py`,
`app/visualization/{rendering/downsampling,rendering/digital_transforms,interaction/measurement_engine,axis_management,channel_grouper,engineering_display,viewport_policy}.py`.

**Genuinely Qt-coupled, not reusable as-is** (thin orchestration/presentation,
not carrying unique business logic per their own docstrings, where checked):
`app/ui/*` in full, `app/visualization/widgets/*`,
`app/visualization/managers/{visualization_manager,synchronization_manager}.py`,
`app/calculated_signals` dialog files under `app/ui/calculated_signals/`.

**Mixed / worth explicit attention during migration planning**:

| Module | Engineering capability | GUI dependency | Reuse potential | Required refactoring | Regression risk |
|---|---|---|---|---|---|
| `app/ui/main_window/main_window.py` | Owns file-open format routing (COMTRADE vs CSV/Excel), threading dispatch, manifest-reload alignment-restoration orchestration | Heavy (the whole file is a `QMainWindow`) | Low as code; the *routing decisions* and *manifest-restoration precedence rules* it encodes are valuable design reference | Extract routing/threading/restoration decisions into pure functions before any web port; do not port the file itself | High — this file is the seam where COMTRADE's async-no-review path, the wizard's embedding, and manifest-alignment restoration all meet; easy to silently drop a precedence rule during extraction |
| `app/ui/session/session_canvas_controller.py` | Panel layout decisions, `_session_window()` data-domain computation, cursor A/B propagation | Heavy (Qt signals, QSplitter/QScrollArea) | Data-domain and axis-side-routing logic is portable; cursor propagation is not | Separate data-domain computation from rendering orchestration | Medium |
| `app/data/manifest_loader.py` / `manifest_generator.py` | Alignment-state persistence (YAML round-trip), stable source-id mapping | None directly, but tightly bound to `main_window.py`'s restoration orchestration | High for the serialization *shape* (what fields, what precedence rules); the identity-mapping pattern (manifest id vs. live id) is a good reference for a web backend's own persistence design | None needed to reuse the logic itself; needs a decision on whether YAML manifests are the right persistence format for the web app or just a design reference | Medium — precedence rules (saved-geometry-wins, opaque-legacy-geometry handling) are subtle and must be preserved exactly if manifest compatibility ever matters |
| `app/analytics/suggestions/suggestion_engine.py` | Rule-based next-action recommendations | No direct PyQt import, but consumes UI-state booleans (dock visibility, active-mode flags) as input | Rule logic portable; current shape is not | Restructure around whatever UI-state model the web frontend uses | Low |

---

## Reuse Candidates

### Category A — Reuse largely unchanged

`app/models/*` (data contract), `app/providers/{base,comtrade,csv,excel}/*`,
`app/import_wizard/*` (all 27 files — profiling, timestamp detection/repair,
column mapping, assembly, export, bridge), `app/sessions/{event_session,session_models,alignment_engine,absolute_alignment,alignment_summary,timing_compatibility}.py`,
`app/calculated_signals/{models,expression,units,engine,resolver}.py`,
`app/analytics/{correlation,events,fault,frequency*,harmonics,phasors,protection,quality,rms,scaling}/*` (*classification-only, no computation, for `frequency/`),
`app/visualization/{rendering/downsampling,rendering/digital_transforms,interaction/measurement_engine,axis_management,channel_grouper,engineering_display,viewport_policy}.py`.

**Evidence**: all of the above are grep-confirmed Qt-free, operate on
plain dataclasses/NumPy/pandas, and (where checked) have module docstrings
asserting their own independence.

### Category B — Reuse after controlled refactoring

- File-open **routing decisions** and **manifest-restoration precedence
  rules** currently embedded in `main_window.py` — extract into pure
  functions/services before porting; do not port the Qt file.
- The manifest YAML **persistence shape and precedence rules**
  (`manifest_loader.py`/`manifest_generator.py`) — valuable as a design
  reference for a web backend's own session/alignment persistence, whether
  or not YAML itself is reused as the format.
- `app/analytics/suggestions/suggestion_engine.py` — rule logic portable,
  needs restructuring around a web UI-state model.
- The `SynchronizationManager` broadcast-without-echo / rate-limiting
  *algorithm* — reusable as a pattern (e.g. websocket broadcast), not as
  Qt-signal-bound code.

### Category C — Reimplement for the web architecture

All of `app/ui/*`, `app/visualization/widgets/*`, `app/visualization/managers/{visualization_manager,synchronization_manager}.py`
(the dead `visualization_manager.py` should simply not be ported at all —
see Architectural Risks), the calculated-signals creation dialog and
session-panel row widgets, `app/ui/import_wizard/*`. These are desktop
presentation/workflow code with, per their own docstrings where checked, no
unique business logic implemented in them.

---

## Proposed Frontend / Backend Boundary

`[PROPOSAL]` — not yet approved, offered based on the findings above.

The general direction suggested by the task brief — frontend as
presentation/interaction/visualization/workspace-controls/user-selections,
backend as authoritative parsing/calculations/signal-processing/
synchronization/full-resolution source data/analysis logic/persistence — is
**consistent with what was actually found**, not contradicted by it:

- Every piece of Category-A logic above is already Python, already
  Qt-free, and already organized around a `DisturbanceRecord` contract that
  has no inherent reason to live in a browser.
- The existing desktop app *itself* already keeps full-resolution data
  authoritative in the backend-equivalent layer (`app/sessions`,
  `app/analytics`, `app/calculated_signals`) and only decimates for
  **display** — the same separation the task brief proposes for the web app
  already exists conceptually, just not across a network boundary.
- Nothing found in this audit suggests duplicating the mature Python
  engineering logic into JavaScript would be justified — the parsers,
  timestamp handling, alignment engine, and analytics modules are
  substantial, tested, and already isolated from any specific UI framework.

**What the audit adds nuance to, not contradicts**: the existing app's own
line between "authoritative" and "display" is imperfect in a few places
worth deciding on deliberately rather than copying:

- Decimation for display currently happens once per session-window, not
  per-viewport — a web app re-doing this from scratch has a chance to do it
  better (server-side, viewport-aware, and cacheable) rather than
  inheriting the desktop app's own compromise.
- Cursor/measurement interaction state is presentation state and belongs
  entirely client-side in a web app — nothing in `app/analytics`/`app/calculated_signals`
  depends on cursor position (confirmed: `measurement_engine.py` takes
  cursor positions as plain parameters, doesn't own any cursor state
  itself), so this boundary is already clean to draw.
- Session/alignment **persistence** does not yet have a general solution in
  `powerwave` (only alignment state persists, narrowly) — a web app's
  backend-owned persistence model is genuinely new work, not a port.

---

## Full-Resolution Engineering Data Principle

The likely desired principle — backend owns authoritative full-resolution
data, frontend gets an appropriate view representation, decimation stays
separate from calculations/synchronization/measurements/analysis — is
**already substantially true of `powerwave`'s own architecture**:

- `EventAnalysisSession.build_aligned_data()` decimates only the *arrays
  handed to the rendering widget*; it always reads from the untouched
  `DisturbanceRecord.waveform_data` fresh.
- Calculated Signals explicitly bypass `build_aligned_data()` entirely and
  compute over full resolution, by design (documented in the resolver's own
  module docstring).
- Analytics (`app/analytics/*`) consume `DisturbanceRecord`/raw arrays
  directly, never decimated display data.

**Current `powerwave` behaviors that would complicate preserving this
principle in a web port** — flagged, not fixed:

- Decimation is keyed to the **session window**, not the live viewport — a
  literal 1:1 port of `build_aligned_data()`'s decimation policy to a web
  API would mean every viewport request re-decimates over the *entire*
  session span rather than the requested range, which is both wasteful and,
  for a very long recording, could under-serve a narrow zoomed-in view.
  Recommend designing viewport-aware decimation fresh for the web API rather
  than porting this specific behavior.
- No viewport-slice caching exists anywhere — full recompute happens on
  every call. A web API doing the same per-request would be far more
  expensive at typical web request rates than at desktop repaint rates.
- Right-axis curves get materially less client-side rendering optimization
  than left-axis curves in the current PyQtGraph implementation — not
  relevant to a from-scratch web renderer, but worth knowing this asymmetry
  exists so it isn't accidentally reintroduced by analogy.

---

## Original Source Immutability

`[FACT]` Verified directly, not assumed: no current provider or pipeline
stage mutates a source file, its raw arrays, or its metadata in place once
parsed.

- `DisturbanceRecord.waveform_data` is held by reference and never copied
  on construction, but no mutation of it was found anywhere in `app/`
  (session offsets are applied to *copies* at render/query time, never to
  the record itself — verified for every `waveform_data` access site in
  `event_session.py`).
- Import normalization is explicitly documented and verified as
  non-destructive to the caller's input DataFrame ("Raw source data is
  NEVER mutated" — `timestamp_normalizer.py`).
- **However**: "never mutated" is not the same as "preserved for
  traceability." As covered in the Timestamp section, the *original raw
  values* are discarded after normalization in the CSV/Excel path (only a
  strategy-name/format-label survive as provenance) and after unit
  conversion in the COMTRADE path (raw integer `ts` discarded once
  converted to float seconds). If `oruxa_powerwave`'s intended principle is
  "original uploaded disturbance records remain immutable" **in the sense
  of the original file itself being permanently retrievable/re-processable**
  (which is exactly what `backend/app/storage.py`'s `original` write-once
  category already supports, per the Existing `oruxa_powerwave` Architecture
  section above) — that's a stronger and more useful guarantee than
  anything `powerwave` provides today at the parsed-data level, and is
  already achievable with the existing `oruxa_powerwave` storage
  abstraction without needing to reproduce `powerwave`'s in-memory
  behavior.

---

## Web Multi-User Risks

Ranked by severity, with evidence.

| Risk | Rank | Evidence |
|---|---|---|
| No user/tenant concept anywhere in the domain model | **Critical** | `RecordingMetadata`, `DisturbanceRecord`, `SessionSource`, `EventAnalysisSession` have no owner/user/account field anywhere. A shared backend process reusing these classes as-is would need this bolted on entirely at a new layer — nothing in the existing model helps. |
| No concurrency control on session/alignment state | **High** | `EventAnalysisSession`'s dicts (`_sources`, `_channels`, `_calc_signals`, etc.) are plain, unlocked, not async-safe. Safe today only because the desktop app is single-threaded-per-window on the Qt event loop; a web backend serving concurrent requests against a shared session object would need explicit locking or a single-writer model. |
| `DisturbanceRecord.waveform_data` aliasing (never copied on construction) | **High** | Explicit in the class docstring; verified no in-place mutation exists today, but the *contract itself* makes it easy to introduce accidentally in new code that shares a record across requests/users. |
| Source identity is fresh-per-load (UUID), not durable across reloads | **Medium** | Directly caused the need for a separate stable "manifest source_id" + explicit translation map in the new persistence feature — a cautionary precedent for designing any web backend's own identity scheme. |
| No cancellation, only discard-on-arrival or disabled UI | **Medium** | COMTRADE load: request-ID discard, work keeps running server-side regardless. Wizard pipeline/export: no cancel path exists at all. A web backend inheriting this pattern would leak compute on abandoned requests. |
| No serialization for general session state (only alignment persists) | **Medium** | Confirmed no `to_dict`/`from_dict` on `EventAnalysisSession`/`SessionSource`/etc.; `dataclasses.asdict()` wouldn't cleanly handle embedded DataFrame/ndarray/datetime fields anyway. |
| Full in-memory, unchunked file loads for all three formats | **Medium** | Direct memory-pressure-per-concurrent-request risk if backend loading logic is reused as-is without adding limits/streaming. |

---

## Engineering Integrity Risks

Ranked, with why each matters.

| Risk | Rank | Why |
|---|---|---|
| COMTRADE has no discontinuity/gap detection (CSV/Excel does) | **High** | A silent data dropout in a COMTRADE record currently produces no diagnostic at all — a migration that adds a "quality check" layer uniformly across formats could either newly expose this gap (good) or, if built by analogy to the *existing* COMTRADE path, silently perpetuate it (bad). Needs an explicit decision, not an assumption. |
| Raw/original timestamp values discarded after normalization | **High** | No re-audit or re-derivation against the original file is possible downstream of import today. If numerical/timing questions ever arise about a migrated record, there is no existing "check against the source" capability to inherit — this needs to be designed in, not assumed already present. |
| Timezone handling is fully inert | **Medium** | The field exists, is documented as required, and is never populated; the one conversion path is dead code. Any future multi-timezone use case starts from zero, not from an existing (if unused) implementation, despite documentation implying otherwise. |
| Sample-index-mode sources not structurally prevented from cross-record synchronization | **Medium** | `DATA_CONTRACT.md` prohibits this explicitly, but the alignment/offset code path itself doesn't enforce it — only the new automatic-alignment eligibility gate does, and only for that one path. A web re-implementation of the general offset API should decide explicitly whether to add this enforcement rather than silently carrying the gap forward. |
| BEN32 vendor-quirk year-remapping is narrower in code than in policy doc | **Low** | `docs/COMTRADE_NORMALIZATION_POLICY.md` describes remapping "any unrecognized value"; the code only maps two specific literal years. Functionally near-equivalent fallback behavior either way, but worth reconciling doc vs. code rather than assuming the doc's broader framing is what actually runs. |
| Manual Import-Wizard overrides don't persist through manifest save/reload | **Low–Medium** | Acknowledged by the code's own comment. Only a real risk if the source file's content is itself ambiguous enough for auto-detection to land differently on a second run — otherwise the re-derivation is deterministic and harmless. |
| (Now fixed, noted for completeness) Axis-label `min()` regression | **Resolved** | Previously, adjusting one source's offset could silently relabel every other source's displayed position on the axis. Fixed in the commit reviewed for this audit — included here so the fix's existence (and the *class* of bug it represents — a shared derived value being unexpectedly sensitive to one input's change) is on record for the migration team's awareness. |

---

## Architectural Risks

Ranked.

| Risk | Rank | Evidence |
|---|---|---|
| `src/`/`app/` split-brain — duplicate models, duplicate parsers, `pytest` still collects ~600 legacy-only tests | **High** | `docs/LEGACY_CODEBASE_POLICY.md`/`docs/CODEBASE_AUDIT_REPORT.md` (RC4) already track this internally; this audit independently confirmed the duplicate `DisturbanceRecord`/channel classes differ materially (storage model, validation, caching), not just superficially. |
| Documentation describes dead code as canonical (`VisualizationManager`, `FlexiblePlotCanvas`, `DigitalEventTimeline`, `FastWaveformWidget` which doesn't exist at all) | **High** | Confirmed via `main_window.py` import/instantiation search across the whole file — none of these are reachable from the live app. A migration team reading `docs/ARCHITECTURE.md`/`VISUALIZATION_CONTRACT.md` at face value would be planning around code that doesn't run. |
| Cursor synchronization fragmented across two independent mechanisms with no shared owner | **High** | Confirmed unchanged by the most recent commit; see Synchronization section. |
| Two duplicate session/alignment concepts (`EventAnalysisSession` vs `MultiSourceSession`+`display_alignment.py`) | **Medium–High** | The recent commit *narrowed* but did not eliminate this — `MultiSourceSession` gained a new role (persisted-alignment carrier) rather than being retired. |
| Two non-communicating CSV/Excel classification systems (`RuleManager`/YAML rules vs. the wizard's own detectors) | **Medium** | New finding, not previously documented anywhere found in `docs/`. Operator-confirmed rules currently have zero effect on the interactive import path. |
| Two independently-maintained, near-identical panel/channel-classification implementations (`EventAnalysisSession._infer_panel_for_channel` vs. `channel_grouper.py`) | **Medium** | The `event_session.py` code even comments "mirrors channel_grouper logic," confirming the duplication is known/intentional-but-unresolved internally. |
| `app/synchronization/` package is empty scaffolding that could mislead future work | **Low–Medium** | Purely a navigation hazard, not a functional bug — but a real risk that a migration effort (or a future `powerwave` contributor) starts "extending" an empty package instead of finding the real logic in `app/sessions`/`app/visualization`. |
| Dead code left in place and exercised only by tests (`overlays/` abstraction, `_IntelligentLoadWorker`, redundant BINARY32 check, unreachable `TIMEZONE_ALIGNMENT`) | **Low** | Each individually low-severity, but collectively a sign that "what's live" requires active verification rather than trusting file presence or docs — a lesson for how this migration's own future documentation should be maintained (see [README.md](README.md)'s conflict-resolution rules). |
| No true chunked/streaming ingestion anywhere despite "100MB+" performance targets in docs | **Medium** | See Large Dataset Behaviour section — relevant if a web backend inherits the assumption that "it already handles large files" without checking how. |

---

## Migration Comparison Matrix

Facts and recommendations kept separate — the last three columns are
assessments, not decisions.

| Capability | In `powerwave`? | In `oruxa_powerwave`? | Reusable directly? | Needs refactoring? | Needs web reimplementation? | Needs product/design decision? | Risk |
|---|---|---|---|---|---|---|---|
| Data contract (`DisturbanceRecord` + channels/metadata/timing) | Yes | No | Largely (needs JSON/serialization layer added) | Minor (add serialization) | No | No | Low |
| COMTRADE parsing | Yes | No | Yes | No | No | No | Low |
| CSV/Excel parsing (providers) | Yes | No | Yes | No | No | No | Low |
| CSV/Excel Import Wizard backend (profiling/timestamp/mapping/assembly) | Yes | No | Yes | Minor (unify with routing decisions currently in `main_window.py`) | No | Whether to keep the two-tier direct-provider/wizard split or simplify to one path | Low–Medium |
| CSV/Excel Import Wizard UI | Yes | No | No | — | Yes | UX design for web | Low |
| COMTRADE review/preview step before display | No (gap in `powerwave` too) | No | — | — | Yes (new capability, not a port) | Whether to build the review step COMTRADE currently lacks | Low |
| Operator-confirmed classification rules (`RuleManager`/YAML) | Yes, but inert for interactive use | No | Partial | Needs a decision before porting (currently unused by the path that matters) | Possibly | Unify with wizard detectors, or drop entirely | Medium |
| Session / multi-source alignment model | Yes (`EventAnalysisSession`) | No | Yes | Add serialization, concurrency boundaries, user/tenant scoping | No | Persistence format/strategy for the web app | High |
| Absolute multi-source time alignment (new feature) | Yes | No | Yes (algorithm); persistence shape is a reference, not necessarily the format to reuse | Minor | No | Whether YAML-manifest-style persistence is right for the web app | Medium |
| Alignment persistence (manifest round-trip) | Yes (narrow — alignment only) | No (nothing persists yet) | Partial — design reference more than code to port | Significant (general session persistence doesn't exist yet in either app) | Possibly | Full session persistence scope/format | High |
| Cursor / measurement interaction | Yes (fragmented across 2 mechanisms) | No | No | — | Yes | Unify into one client-side model | Medium |
| Calculated signals (expression engine) | Yes | No | Yes (engine); no (dialogs) | No | UI only | Whether to expand the expression grammar (e.g. allow signal×signal for power calcs) | Low–Medium |
| Waveform rendering | Yes (PyQtGraph) | No | No | — | Yes | Decimation strategy (viewport-aware vs. session-window) | Medium |
| Analytics: RMS/harmonics/phasors/events/fault/protection/correlation/quality/scaling | Yes | No | Yes | No | No | No | Low |
| Analytics: frequency/ROCOF computation | No (classification only in `powerwave` too — real computation doesn't exist) | No | — | — | Yes (new capability if needed) | Whether frequency/ROCOF computation from raw waveforms is in scope | Medium |
| Suggestions / next-action hints | Yes | No | Partial (rule logic only) | Significant | Yes (UI shape) | Whether this feature is even wanted in v1 | Low |
| File storage / immutable originals | Partial (no mutation found, but no traceable "original" retained after parse) | Yes (`StorageBackend`, write-once `original` category — arguably stronger than `powerwave`'s guarantee) | N/A — `oruxa_powerwave`'s existing abstraction is already suitable | No | No | No | Low |
| Multi-user / auth | No (single-desktop-process assumption throughout) | No (not in Milestone 1 scope) | No | — | Yes (new capability) | Full scope of auth/isolation | Critical (deferred, per existing `oruxa_powerwave` milestone scoping) |
| Background job processing with real progress/cancellation | No (only Qt-thin async exists, no true cancel) | No | No | — | Yes (new capability, no precedent to port) | Job/task model for the web backend | Medium |
| Deployment/CI/DEV-PROD isolation | N/A (desktop app) | Yes, already solid | N/A | N/A | N/A | N/A | Low |

---

## Proposed Migration Phases

`[PROPOSAL]` — not approved. Based on the findings above, sequenced by risk
and dependency, not copied from any generic template.

### Phase 0 — Backend domain-model extraction

- **Objective**: stand up `DisturbanceRecord` and its channel/metadata/timing
  contracts inside `oruxa_powerwave`'s backend, with a serialization layer
  (the one thing `powerwave` doesn't provide).
- **Functionality**: no user-facing feature yet — this is the foundation
  the rest of the phases build on.
- **Reused `powerwave` modules**: `app/models/*` as direct reference/port.
- **Refactoring required**: add JSON-safe serialization for
  `pandas.DataFrame`/`datetime` fields; decide whether the DataFrame stays
  as the internal representation or becomes something else at rest.
- **Backend work**: new Pydantic/dataclass models under `backend/app/`,
  wired to nothing yet.
- **Frontend work**: none.
- **Dependencies**: none.
- **Risks**: Low — mostly mechanical.
- **Acceptance criteria**: a `DisturbanceRecord`-equivalent object can be
  constructed, serialized, and deserialized round-trip in a backend test.

### Phase 1 — Upload + parsing + source/channel discovery

- **Objective**: prove the fundamental architecture — a real engineering
  file goes from browser upload to a normalized backend representation.
- **Functionality**: upload one COMTRADE or CSV file, get back parsed
  channel metadata via an API.
- **Reused `powerwave` modules**: `app/providers/{base,comtrade,csv,excel}/*`
  ported largely unchanged; storage lands in the existing
  `backend/app/storage.py` `original` category (already suitable, per
  Original Source Immutability section).
- **Refactoring required**: extract the file-open **format-routing decision**
  out of `main_window.py`'s Qt code into a pure backend function.
- **Backend work**: an upload endpoint, a parse endpoint/pipeline, storage
  wiring.
- **Frontend work**: a minimal upload form and a channel-list display — no
  waveform rendering yet.
- **Dependencies**: Phase 0.
- **Risks**: Low–Medium — decide up front whether to also port the
  richer Import Wizard timestamp-repair flow now or defer it (see Phase
  1.5 note below).
- **Acceptance criteria**: an uploaded COMTRADE and an uploaded CSV file
  both produce a normalized channel list via the API, matching
  `powerwave`'s own parsed output for the same file (spot-checked, not
  byte-for-byte, since intentional format differences are expected).

### Phase 1.5 — Import Wizard–equivalent timestamp handling (may fold into Phase 1 or follow it)

- **Objective**: bring across the CSV/Excel timestamp detection/repair
  richness (`powerwave`'s single biggest asymmetry between COMTRADE and
  CSV/Excel import quality).
- **Reused `powerwave` modules**: `app/import_wizard/{timestamp_detector,timestamp_normalizer,timestamp_repair_executor,interval_inference}.py`.
- **Risks**: Medium — this is genuinely complex logic; a straight port
  risks quietly changing which repair strategy fires for edge-case files
  unless ported carefully with the existing test suite (85 non-Qt
  `tests/unit/` files) as a reference.
- **Acceptance criteria**: the existing non-Qt timestamp test suite (or an
  equivalent set of test cases) passes against the ported logic.

### Phase 2 — Basic web waveform workspace

- **Objective**: render one uploaded source's channels as waveforms in the
  browser.
- **Reused `powerwave` modules**: none directly (rendering must be
  reimplemented — different technology), but `app/visualization/rendering/downsampling.py`'s
  *algorithm* (clip + stride-decimate) and the full-resolution-preserved
  principle are worth carrying forward as design guidance.
- **Backend work**: a viewport-aware decimation endpoint — deliberately
  **not** a port of `build_aligned_data()`'s session-window-based
  decimation (see Full-Resolution Engineering Data Principle section).
- **Frontend work**: a charting library integration, panel/channel routing
  logic (a clean reimplementation of the classification-by-unit/name-keyword
  approach, resolving the duplicate-classifier problem `powerwave` itself
  never resolved — port only one implementation, not both).
- **Dependencies**: Phase 1.
- **Risks**: Medium — this is where "what to preserve vs. what to do
  better" decisions concentrate.
- **Acceptance criteria**: a browser can display a decimated view of an
  uploaded record's channels and interactively pan/zoom without
  full-page reloads.

### Phase 3 — Multi-source workspace

- **Objective**: load and display more than one source in one workspace.
- **Reused `powerwave` modules**: `EventAnalysisSession`'s data-model shape
  (source registry, panel routing) as design reference; `get_global_time_range()`'s
  intersection/union logic is directly portable.
- **Refactoring required**: design the backend's session-ownership/concurrency
  model from scratch (Critical/High risk items from the Multi-User Risks
  section land here) — this is new work, not a port, since `powerwave`
  provides no concurrency precedent.
- **Dependencies**: Phase 2.
- **Risks**: High — this is where the "no user/tenant concept, no
  concurrency control" gaps in `powerwave`'s model must be actively solved,
  not inherited.
- **Acceptance criteria**: two uploaded sources can coexist in one
  workspace, correctly isolated per user session.

### Phase 4 — Synchronization

- **Objective**: multi-source time alignment (manual offset, and
  optionally auto-trigger/correlation/absolute-timestamp derivation).
- **Reused `powerwave` modules**: `app/sessions/alignment_engine.py`,
  `absolute_alignment.py`, `app/analytics/correlation/cross_correlator.py` —
  all Qt-free and directly portable algorithms.
- **Refactoring required**: cursor/range synchronization must be designed
  as one owned concept from the start (learn from, don't repeat,
  `powerwave`'s three-way fragmentation).
- **Dependencies**: Phase 3.
- **Risks**: Medium — the algorithms are solid and portable; the risk is
  UI/state-sync design, not the underlying math.
- **Acceptance criteria**: sources can be manually offset, and (if in
  scope for this phase) auto-aligned by trigger or correlation, with the
  result visibly consistent across all panels.

### Phase 5 — Measurements

- **Objective**: cursor-based measurements (value readout, delta, RMS,
  frequency between two cursor positions).
- **Reused `powerwave` modules**: `app/visualization/interaction/measurement_engine.py`
  — directly portable, deliberately mixed-sample-rate-tolerant.
- **Dependencies**: Phase 4 (needs multi-source alignment context) or could
  precede it for single-source measurement only.
- **Risks**: Low.
- **Acceptance criteria**: measurement results for a known test file match
  `powerwave`'s own output for the same cursor positions.

### Phase 6 — Calculated signals

- **Objective**: expression-based derived signals.
- **Reused `powerwave` modules**: `app/calculated_signals/{models,expression,units,engine,resolver}.py`
  — directly portable engine; UI must be reimplemented.
- **Dependencies**: Phase 3 (needs multi-source session model).
- **Risks**: Low–Medium — consider whether to expand the expression
  grammar (e.g. allow `signal × signal` for real power calculations) as
  part of this phase, since the current grammar can't express common
  power-engineering formulas — an explicit product decision, not
  automatically inherited from `powerwave`'s current limitation.
- **Acceptance criteria**: a calculated signal defined the same way as in
  `powerwave` produces matching numerical output.

### Phase 7 — Advanced engineering analysis

- **Objective**: RMS/harmonics/phasors/events/fault/protection/quality
  analysis surfaced in the web UI.
- **Reused `powerwave` modules**: all of `app/analytics/{rms,harmonics,phasors,events,fault,protection,quality,scaling}/*`
  — directly portable, largest single block of reusable engineering logic
  in the whole codebase.
- **Dependencies**: Phase 2 (needs a source loaded); benefits from Phase 5
  (cursor context).
- **Risks**: Low for the computation itself; Medium for deciding UI
  presentation of results (no direct precedent since `powerwave`'s own
  presentation layer isn't being ported).
- **Acceptance criteria**: analysis results match `powerwave`'s output for
  known test files.

### Phase 8 — Persistence / projects

- **Objective**: save and reload a workspace.
- **Reused `powerwave` modules**: the manifest persistence *shape and
  precedence rules* (saved-geometry-wins, stable-id-mapping pattern) as
  design reference — not a literal port, since `powerwave` only persists
  alignment state, not full session state.
- **Refactoring required**: design full session persistence from scratch
  (source list, channel selection, panel layout, calculated signals, not
  just alignment).
- **Dependencies**: Phases 3–6.
- **Risks**: High — this is new scope beyond what `powerwave` demonstrates.
- **Acceptance criteria**: a saved workspace reloads with all sources,
  alignment, and calculated signals intact.

### Phase 9 — Authentication / multi-user isolation

- **Objective**: real per-user isolation, building on the concurrency/tenant
  work already forced into Phase 3.
- **Dependencies**: Phase 3 onward.
- **Risks**: Critical if deferred too long — per `oruxa_powerwave`'s own
  `AGENTS.md` milestone scoping, this is already explicitly out of scope
  for Milestone 1, consistent with this proposed sequencing.

---

## Recommended First Implementation Slice

`[PROPOSAL]` — not approved, not to be started without sign-off.

```text
Engineering file (COMTRADE or CSV)
        ↓
Browser upload
        ↓
oruxa_powerwave backend — storage (existing StorageBackend, original category)
        ↓
Ported provider (app/providers/comtrade or csv, largely unchanged)
        ↓
DisturbanceRecord-equivalent backend model (new: Phase 0's serialization layer)
        ↓
API response: normalized channel/metadata list
        ↓
Minimal frontend: channel list only, no waveform rendering yet
```

**Why this slice, not a larger one**: it proves the single riskiest
structural question — whether `powerwave`'s Qt-free parsing/data-contract
layer really does port cleanly onto a request/response backend — without
touching any of the genuinely new, harder problems (concurrency, session
ownership, decimation strategy, cursor sync) identified above. It
deliberately stops short of waveform rendering (Phase 2), which is a
separate, larger technology decision (charting library, decimation
strategy) that shouldn't gate proving the parsing/model port works. It
mirrors Phase 0 + Phase 1 above but stops at "channel list," matching the
task brief's own suggested minimal-first-slice shape while grounding it in
this audit's actual risk ranking rather than a generic template.

---

## Open Questions

Every `[OPEN]` item raised in the sections above, collected here for visibility:

1. Whether the general `set_time_offset()` API (not just the new automatic
   absolute-alignment path) should gain timing-mode awareness to
   structurally prevent sample-index-mode cross-record synchronization, or
   whether relying on UI discipline is judged acceptable to also carry into
   the web app.
2. Whether a web re-implementation should add COMTRADE discontinuity/gap
   detection to match CSV/Excel's existing behavior, or accept the current
   asymmetry.
3. Whether full raw-value traceability (re-audit against the original file
   after timestamp normalization) is a requirement for `oruxa_powerwave`,
   given that `powerwave` does not provide it today.
4. Whether to unify the two non-communicating CSV/Excel classification
   systems (`RuleManager`/YAML rules vs. the wizard's own detectors) when
   porting, drop the YAML-rules system entirely, or defer the decision.
5. Whether YAML-manifest-style persistence (as `powerwave` uses for
   alignment state) is the right format/approach for `oruxa_powerwave`'s
   session persistence, or purely a design reference.
6. Whether the calculated-signals expression grammar should be expanded
   (e.g. `signal × signal` for real power calculations) as part of porting
   it, given the current grammar can't express common power-engineering
   formulas.
7. Whether frequency/ROCOF *computation* (not just classification/display)
   is in scope for `oruxa_powerwave`, given `powerwave` itself never
   implements it — channels are assumed to arrive pre-computed.
8. Whether the `suggestions/`-style next-action rules feature is wanted at
   all in an initial web version.
9. Scope and timing of Phase 9 (authentication/multi-user isolation) —
   already deferred per `oruxa_powerwave`'s own current milestone scoping,
   flagged here only to keep it visible against the concurrency risks
   surfaced in Phase 3.

---

## Recommendation Before Implementation

This discovery pass found `powerwave`'s domain/engineering core to be
substantially portable — Qt-free, well-isolated, and (mostly) well-tested —
which is the best possible outcome for a migration effort: the highest-value,
hardest-to-redo logic (parsing, timestamp handling, alignment math,
analytics, calculated signals) is exactly the part that doesn't need
reinventing. The harder work is concentrated in exactly the places one
would expect for a desktop-to-web migration: session ownership and
concurrency (`powerwave` has none), decimation/viewport strategy
(`powerwave`'s own compromise shouldn't be copied verbatim), cursor/interaction
state (inherently client-side in a web app, and `powerwave`'s own version of
it is fragmented and worth doing once, correctly, rather than porting), and
general persistence (barely exists in `powerwave` today, beyond the new
narrow alignment-state feature).

Before any implementation begins:

- The `[OPEN]` items above should be resolved or explicitly deferred by the
  project owner.
- `Phase 0` and the recommended first slice should be explicitly approved
  before any code is written, per this project's change-governance rule.
- No `[PROPOSAL]` in this document (phases, boundary, first slice) should be
  treated as approved until recorded in [DECISIONS.md](DECISIONS.md).

This document should be treated as a living record — `powerwave` is
actively developed (as directly demonstrated mid-audit by commit `3156392`),
and this document's findings should be re-verified against `powerwave`'s
current `HEAD` before being relied upon for implementation decisions made
significantly later than 2026-08-14.
