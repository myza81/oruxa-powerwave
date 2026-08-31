# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now** — what is implemented, what is
> architecturally true, what is intentionally deferred, and what comes
> next. For how the project got here (phase-by-phase implementation
> records, UAT chronology, individual bug fixes), use
> [DECISIONS.md](DECISIONS.md), [HANDOFF.md](HANDOFF.md), and Git history.
> Do not let this file accumulate into a diary — when updating it, replace
> superseded claims, don't append to them.

Last meaningful update: **2026-08-30**. The Time Group architecture
migration is declared **architecturally complete** (DEC-069, "TG-FINAL"
closure audit — see [Architecture](#architecture) below), and the
RECORDINGS sidebar now shows each source's canonical recording-start
timestamp (see [Implemented capabilities](#implemented-capabilities)).

## Current status

`oruxa_powerwave` is a working COMTRADE waveform-analysis web app: FastAPI
backend (`backend/app/`) + a single-page vanilla-JS frontend
(`frontend/index.html`, no framework/build step), deployed to DEV
(auto-deploy on `main`) with PROD available but held back manually. Beyond
COMTRADE upload/parse/browse, the app now has a full multi-source,
multi-panel waveform workspace with Time-Group-aware synchronization,
cursors, t0, annotations, a group-aware Per-Unit measurement model,
calculated channels, and digital-channel display. CSV/Excel ingestion is
the current workstream — Slices 1-3 (raw CSV/Excel preparation-source
upload, Excel worksheet discovery/selection, and a paged raw-data
preview Data Preparation Workspace, no waveform conversion yet) are
implemented; the remaining slices are not (see
[Current next workstream](#current-next-workstream)).

## Architecture

**Backend** (`backend/app/`): FastAPI app via `create_app()`. Key domain
modules beyond the original COMTRADE port (`domain/source.py`,
`domain/timing.py`, `channel_classification.py`,
`digital_classification.py`): `time_grouping.py` (Time Group derivation),
`synchronization.py` (manual alignment offsets + t0), `calculated_channel.py`,
`measurement_group.py` / `measurement_group_detection.py` /
`voltage_group_config.py` / `current_group_config.py` / `voltage_reference.py`
/ `per_unit.py` (the Per-Unit measurement model), `event_detection.py` /
`rms_detector.py`. `providers/` still holds only `base.py` and
`comtrade.py` — no CSV/Excel provider exists yet. No persistent storage of
uploaded event files (DEC-015, unchanged); the active workspace retains
each source's full-resolution parsed record in memory only (DEC-019).

**Time Groups** (DEC-057 and its follow-on TG-A…TG-H/TG-FINAL slices,
DEC-058 through DEC-069) are the current backbone of the multi-source
waveform workspace:

- Groups are derived by **overlap of sources' own raw recorded absolute
  intervals** (connected components over an overlap graph on
  `start_time`/duration), never mere start-time proximity. An elapsed-only
  source (no trustworthy `start_time`) always becomes its own solo,
  unaligned group — never auto-merged with another elapsed-only source.
- Placement is layered and composed only at read time, never stored
  combined: `effective_alignment_offset_s = timestamp_placement_offset_s`
  (automatic, derived from each source's own recorded start time)
  `+ manual_alignment_offset_s` (the engineer's own Synchronise Sources
  correction, DEC-053's original mechanism, unchanged semantics).
- A **Time Group Canvas** exists only for a group with at least one
  currently displayed channel (created lazily, removed when its last
  channel is removed) — never one for every possible group up front.
- Each Time Group Canvas owns its **own**: waveform panels, navigation
  toolbar (Zoom/Pan/Reset Time View/Autoscale Y), Cursor A/B (and the A-B/Δt
  readout), t0, Synchronise Sources context (its own local sync button and
  group-filtered source list), Time Range slider, ruler (including its own
  Absolute-mode wall-clock origin), and annotation placement/anchoring/
  reprojection context (every annotation resolves its own owning group
  dynamically from `data.sourceId`, never a cached group id and never a
  "primary group" fallback).
- **Detect Event** remains fully implemented and is internally Time-Group-
  aware (group-filtered source list, group's own visible range, writes only
  its own group's t0), but its normal UI entry point is deliberately hidden
  behind `WW_DETECT_EVENT_UI_ENABLED = false` — a one-line flip re-enables
  it; this is a product decision, not a missing feature.
- Sticky UI (current, DEC-068/069): the numerical A/B/Δt cursor readout
  lives in each canvas's own top sticky toolbar row; the small A/B position
  badges are nested inside that canvas's own ruler, inheriting the ruler's
  sticky behavior; a separate bottom-sticky wrapper holds only the Time
  Range slider. All of this is per-Time-Group, not shared.
- The **TG-FINAL closure audit** (DEC-069) re-verified every
  `wwPrimaryTimeGroupId()`/`ww.viewport`/`ww.workspaceBounds` use, every
  legacy singleton DOM id, and every per-group state Map's lifecycle. It
  found and fixed exactly one remaining active correctness defect (an
  Absolute-mode hover tooltip that read the wrong group's wall-clock
  origin) and confirmed every other surface was already either correctly
  per-group or intentionally workspace-global. **No known active Time
  Group correctness defect remains.**

**Intentionally workspace-global** (not migration gaps — by design, and
re-confirmed by the TG-FINAL audit):

- Layout Mode (Grouped/Separate/Custom) — a workspace-wide display
  preference; Time Group stays a hard panel boundary inside every mode,
  including Custom.
- Time Mode (Absolute/Elapsed) — a workspace-wide display preference; only
  the wall-clock *origin* each ruler computes labels from is per-group.
- Unit Mode (Per-Unit toggle).
- Upload / workspace lifecycle actions (`Start new workspace`, source
  removal) — these clear every per-group Map at once, by design.
- The annotation review drawer — reads each annotation's own (now
  correctly per-group) computed position; a per-group drawer was
  considered and explicitly rejected.
- Global navigation/shell (Global Header, Main Sidebar Menu, Bottom Status
  Bar).

## Implemented capabilities

- **COMTRADE ingestion**: two-slot `.cfg`/`.dat` upload, parse, engineering-
  type channel classification (backend-computed), ephemeral per-request
  parsing (no event files ever persisted to disk/storage).
- **Application shell**: full-viewport Global Header, collapsible Main
  Sidebar Menu, drag-resizable Workspace Sidebar (source-first hierarchy:
  Recording → Analog/Digital → Category → Channel), a dominant Main
  Workspace, and a Bottom Status Bar. **Recordings** and **Waveform** are
  separate top-level pages; Recordings has its own upload modal
  (`RECORDING_FORMATS`-driven) and per-recording detail/Open-Analyse flow.
  Light/Dark theme is a single, app-wide, `localStorage`-persisted,
  cross-tab-synced preference.
- **RECORDINGS sidebar recording-start timestamp**: each source card's
  metadata line now reads `N analog · N digital · rate · duration ·
  recording-start-timestamp`, e.g. `139 analog · 538 digital · 5 kHz ·
  0.825 s · 2026-07-25 13:09:44.2106`. The timestamp is the source's raw,
  immutable `start_time` (`SourceSummaryOut.start_time` /
  `TimingInformation.start_time`) — never `trigger_time`, never a manual
  synchronization offset, never a Time-Group-derived placement or t0. An
  elapsed-only source (no absolute `start_time`) simply omits the segment.
  Truncated (never rounded/padded) to 4 fractional digits; no timezone
  conversion is applied.
- **Multi-source waveform display**: one independent Plotly instance per
  panel (never one figure with fixed subplots); Grouped (by
  `engineering_type`)/Separate (one panel per channel)/Custom (user-defined
  via an Edit Channel Groups dialog) layout modes, all Time-Group-bounded;
  every panel independently resizable (100–600px, presentation-only).
- **Adaptive resolution**: ≤10,000 original samples per channel per
  requested range returns full resolution; above that, a peak-preserving
  min/max envelope reduction with a pixel-aware point budget
  (`clamp(plot_width_px*4, 4000, 20000)`). Backend full-resolution
  authority and COMTRADE parsing are unaffected.
- **Synchronization & timing**: automatic timestamp-based initial
  placement composed with an engineer's own manual alignment offset (see
  [Architecture](#architecture)); Absolute (real recording wall-clock) and
  Elapsed time-axis modes, both group-correct; per-Time-Group t0 with
  internally-supported, UI-hidden Detect Event.
- **Per-Unit measurement model**: the group-aware model (DEC-050's target)
  has its core implemented — automatic measurement-group detection,
  group-aware Voltage and Current PU conversion, a frontend Measurement
  Groups configuration UI, and calculated-channel same-group inheritance.
  The older source-wide conversion (DEC-049) remains as the fallback for
  channels outside any detected group — a deliberate coexistence, not a
  bug. See [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md)
  (authoritative) and [DECISIONS.md — DEC-050](DECISIONS.md#dec-050--per-unit-measurement-model-is-clarified-to-be-measurement-group-aware-the-currently-deployed-source-bound-model-dec-049-is-not-the-final-target).
- **Calculated channels**: workspace-scoped derived analog channels —
  Reverse Polarity, Absolute Value, Multiply-by-Constant, N-input Addition,
  ordered N-input Subtraction, and trailing one-cycle RMS. Multi-input
  operations require proven synchronized sample-time alignment (no
  interpolation/resampling). Immutable after creation, with dependency-
  aware delete/cascade.
- **Annotations**: `text_note` (floating, content-anchored), `callout`
  (waveform-anchored with a movable label box), and `peak_max`/`peak_min`
  (dynamically viewport-recalculated) — all resolve their own owning Time
  Group dynamically; a workspace-global review drawer lists every
  annotation from its own (correct) rendered position.
- **Digital channels**: shared batched full-record transition rendering
  (one multi-trace figure, not one instance per channel), Triggered/Never
  Triggered/Spare classification, and compact inline A/B cursor-value
  badges reusing the analog cursor pipeline.
- **CI/CD**: DEV auto-deploys after CI succeeds on `main`; PROD deployment
  remains a manual `workflow_dispatch`, deliberately not automatic.
- **Channel presentation customization**: right-click an analog RECORDINGS-
  sidebar channel row for `Rename…`/`Change colour…`. Both are pure
  presentation overrides keyed by the same stable `sourceId::channelName`
  identity every engineering lookup already uses (cursor values,
  calculated-channel inputs, Per-Unit membership, annotations, waveform
  trace identity) — canonical parsed names are never mutated, never sent
  to the backend, and never used as a lookup key. Reset restores the
  original name / the exact original auto-assigned color. Workspace-local
  (survives rerenders/layout/Time-Group changes, not a page refresh);
  resets on Start New Workspace/Clear workspace. Calculated channels and
  digital channels are explicitly excluded this slice — see
  [DECISIONS.md — DEC-070](DECISIONS.md#dec-070--channel-presentation-customization-recordings-sidebar-rename--color-override-is-implemented-as-a-pure-presentation-layer-above-canonical-channel-identity-analog-source-channels-only-this-slice).
- A minimal committed real-browser smoke-test foundation now protects
  critical upload/render/interaction paths — see
  [docs/development/BROWSER_SMOKE_TEST.md](../development/BROWSER_SMOKE_TEST.md).
- **CSV/Excel preparation-source upload, Excel worksheet discovery, a
  paged data-preview Data Preparation Workspace, a non-destructive
  Working Dataset overlay, header/data-region/column-role mapping, and
  a Preparation Readiness Issue model (CSV/Excel ingestion Slices 1-6,
  DEC-072)**:
  the Upload Recording modal's CSV and
  Excel options are both enabled (`RECORDING_FORMATS`,
  `frontend/index.html`), each with its own "Upload & Prepare" action,
  posting to `POST .../preparation-sources` (`app/api/v1/preparation_sources.py`
  — one endpoint, `csv_file` xor `excel_file`, exactly one per request)
  that validates and accepts a raw `.csv` or `.xlsx` file into a new,
  purely in-memory `PreparationSession` (`app/domain/preparation_session.py`
  + `app/services/preparation_session_registry.py`, an eighth sibling
  registry alongside `WorkspaceRegistry` and friends) — never a
  `DisturbanceRecord`, never anything a waveform request can reach.
  Excel workbooks additionally get their worksheet structure discovered
  at upload time (`openpyxl`, `read_only=True` streaming — no temp
  files, no full-sheet materialization): name/order/visible-hidden state
  and best-effort row/column counts, stored as `WorksheetInfo` on the
  same `PreparationSessionSummary`; a one-worksheet workbook is
  auto-selected, a multi-worksheet workbook requires an explicit
  `PATCH .../preparation-sources/{id}` selection. Legacy `.xls` is
  deliberately not supported (would need a separate, unmaintained
  `xlrd` dependency). Both formats appear in Recording Events (File
  Format/File Size/Status columns, populated for COMTRADE too via an
  additive `SourceMetadata.file_size_bytes` field) with status `Needs
  Preparation`; Start Time/Duration/Sampling Rate(s) show `—` rather
  than fabricated values. A `Needs Preparation` row is structurally
  excluded from `GET .../sources` (so the Workspace Sidebar's
  channel-selection list never sees it at all).

  Clicking a `Needs Preparation` row now opens a new, fourth top-level
  page — the **Data Preparation Workspace** (`#pageDataPreparation`,
  `shell.currentPage = "data-preparation"`, its own `wwDataPrep` state
  object completely separate from the waveform workspace's `ww`) —
  instead of opening a waveform (that row-click gate is still
  `status === "ready"`, unchanged). It shows the source's filename/
  format/size/status, a worksheet `<select>` for Excel (superseding
  Slice 2's own standalone Worksheet Selection modal, now removed —
  switching sheets resets the preview and re-fetches), and a paged raw
  table (spreadsheet-style column letters, 1-based row numbers, no
  header-row assumption) backed by a new
  `GET .../preparation-sources/{id}/rows?offset=&limit=` endpoint
  (default 200/max 1000 rows per page, server-enforced). CSV rows are
  streamed via `csv.reader` (never a full `pandas.read_csv`); Excel rows
  reuse `openpyxl`'s `read_only=True` `iter_rows(min_row=, max_row=)`,
  reopened fresh per request. Released on its own
  `DELETE .../preparation-sources/{id}` or on whole-workspace
  `DELETE /api/v1/workspaces/{id}` (cascades into this registry too).

  **Slice 4** adds a non-destructive Working Dataset overlay
  (`app/domain/working_overlay.py` + `app/services/working_overlay_service.py`)
  layered on top of each `PreparationSession`: cell edit/clear/reset, row
  exclude/include, column ignore/unignore, and a Reset All action, each
  a sparse dict/set entry proportional to edit COUNT — never a second
  full copy of the dataset. Undo/redo is supported via a bounded
  (200-entry) operation history; a `revision` counter increments on
  every mutation. Seven new endpoints under
  `.../preparation-sources/{id}/working/...`; each and the existing
  `GET .../preparation-sources` (list/detail) responses now carry a
  `working_overlay` summary (`working_revision`, `edited_cell_count`,
  `excluded_row_count`, `ignored_column_count`, `can_undo`, `can_redo`).
  The existing `GET .../rows` preview now returns the WORKING view by
  default (raw merged with the overlay at read time only, never
  persisted) — each row gains `excluded`/`modified_cells` (sparse,
  provenance-preserving), and the page-level response gains
  `ignored_columns`/`working_revision`. Raw bytes are never mutated. The
  Data Preparation Workspace's table gained click-to-edit cells (a plain
  `<input>`, no spreadsheet-grid library), a per-cell reset action,
  row/column toggle buttons, Undo/Redo, and a "Reset All Changes"
  confirm dialog; the heading switches from "Raw Data Preview" to "Data
  Preview (Edited)" once any change exists.

  **Slice 5** extends the SAME `WorkingOverlay` (not a second model)
  with header-row selection, data-region narrowing, and column
  semantic-role assignment (`unknown`/`waveform`/`time_axis`/
  `metadata`/`quality_status`/`ignore` — multiple `time_axis` columns
  allowed; a role is a stated intent only, never validated/interpreted).
  All three participate in the same bounded undo/redo history and
  revision counter Slice 4 already built. Slice 4's own separate
  `ignored_columns` set is retired — `column_roles`'s `ignore` value is
  now the single authoritative representation, with Slice 4's own
  boolean ignore endpoint kept working unchanged as a thin alias. Six
  new endpoints (`PUT`/`DELETE .../working/header`,
  `.../working/data-region`,
  `.../working/columns/{column_index}/role`); the `working_overlay`
  summary gains `header_row_number`/`data_start_row`/`data_end_row`;
  the `GET .../rows` preview gains the same three plus
  `column_labels`/`column_roles`, and each row gains `is_header`/
  `in_active_region` flags (independent of, never conflated with,
  `excluded`). Column labels come from the header row's own WORKING
  values (Slice 4 edits included); a blank header cell falls back to
  `"Column {letter}"`, no header at all falls back to the plain letter,
  and duplicate header text is allowed verbatim (never disambiguated).
  Reset All now also clears header/region/role state. Frontend: a new
  "Structure" panel (header-row input, data-region start/end inputs, a
  compact Column/Label/Role mapping table) plus a per-row "Header"
  quick-select button and new row styling for the header row and rows
  outside the active region.

  **Slice 6** adds the preparation-specific Readiness Issue LANGUAGE AND
  TRANSPORT model — explicitly NOT the full Readiness Validator (still
  Slice 9's own scope). New `app/domain/preparation_issue.py`:
  `PreparationIssue{severity, code, message, location, suggested_action,
  details}` (severity one of `blocking`/`warning`/`info`;
  `location`'s four fields — `worksheet_index`/`row_number`/
  `column_index`/`field` — are each independently optional, so a
  dataset-level issue is valid) and `PreparationIssueSummary{
  evaluated_revision, current_revision, is_stale, blocking_count,
  warning_count, info_count, issues}`. `ImportServiceError` itself is
  untouched — a `PreparationIssue` is a structured finding, never an
  exception, and a real runtime failure never becomes one. Only three
  issue codes exist today (`header_not_selected`,
  `data_region_unconfigured`, `column_roles_unassigned`), produced by a
  short, linear `collect_preparation_issues()` that checks already-known
  CONFIGURATION facts only — no data interpretation — and every one of
  them is `info` severity, never implying invalidity. Issues are derived
  LIVE on every request (no cache, no database); `evaluated_revision`
  always equals `current_revision` and `is_stale` is always `false`
  today. New `GET .../preparation-sources/{id}/issues` endpoint, scoped
  to the selected worksheet the same way `GET .../rows` already is.
  Frontend: a new "Preparation Status" panel showing severity counts and
  a grouped Blocking/Warning/Info list, refetched alongside every
  preview load (which already covers "refetch after every mutation" for
  free). Recording Events status stays `Needs Preparation` throughout —
  no `Ready`/`Preparation Error` status, no "Open in Powerwave" action,
  and no readiness gate exist anywhere in this slice.

  Time-axis interpretation and the full readiness validator are still
  explicitly NOT part of any of these six slices — see
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md §14](CSV_EXCEL_INGESTION_ARCHITECTURE.md).

## Known intentional constraints / deferred items

These are product decisions or explicitly out-of-scope items, **not**
correctness defects:

- Cross-Time-Group synchronization, cross-Time-Group cursor comparison,
  and a shared cross-Time-Group t0 — deliberately not built; each Time
  Group is an intentional isolation boundary, not merely an unfinished one.
- Detect Event's UI entry point stays hidden (`WW_DETECT_EVENT_UI_ENABLED
  = false`) even though the underlying feature is fully implemented and
  group-aware.
- Time Group collapse (a UI affordance to collapse/hide a group's canvas)
  has never been built — every active canvas stays expanded.
- Direct vertical drag/reorder of panels and drag-to-overlay/group by
  direct lane dragging — still fully unimplemented and undecided
  (`[PROPOSAL]`/`[NEEDS UAT]`, not `[DECISION]`).
- Real Table/Split view and CSV/Excel parsing/normalization — not yet
  implemented (see [Current next workstream](#current-next-workstream)).
- Advanced Per-Unit group move/split/merge UI, CT/VT scaling as a PU base,
  and DEC-049's eventual retirement — each needs its own separate,
  explicit owner-approved implementation prompt; none is authorized yet.

Genuinely open engineering/operational items (not yet resolved either
way):

- No automatic TTL/expiry for an abandoned workspace — `WorkspaceRegistry`
  entries (now including full-resolution waveform data, DEC-019) live in
  memory until the backend process restarts. `[DECISION MODE: COMPARISON]`.
- The ~100 MB real-COMTRADE-file memory ceiling has not been directly
  measured (only extrapolated from smaller synthetic benchmarks).
- A genuinely disk-free (zero temp-file-touch) upload/parse path remains
  unimplemented — judged disproportionate so far against "don't rewrite
  proven engineering logic."
- The long-term persistence architecture (for whatever eventually needs to
  survive a session — not event files, which stay permanently ephemeral
  per DEC-015) remains undecided, deferred to a later phase.

## Current next workstream

**CSV/Excel ingestion and normalization** is the current area of work,
per owner direction, now in progress following the owner-revised 13-slice
sequence recorded in
[CSV_EXCEL_INGESTION_ARCHITECTURE.md §14](CSV_EXCEL_INGESTION_ARCHITECTURE.md)
(itself grounded in [DECISIONS.md — DEC-072](DECISIONS.md#dec-072--csv-excel-ingestion-six-architectural-clarifications-approved--temporary-preparation-state-retention-preparation-scoped-severity-model-hybrid-rawworking-overlay-architecture-deferred-disturbancerecord-hardening-honest-non-absolute-time-preservation-and-an-open-ended-time-axis-format-list)).
**Slices 1-6 (Preparation-session foundation + raw CSV ingestion; Excel
ingestion + worksheet discovery; paged raw-data preview + Data
Preparation Workspace shell; Working Dataset / non-destructive overlay;
Header/Data Region + Column Role Mapping; Preparation Readiness Issue
model) are implemented (2026-08-31)**
— see [Implemented capabilities](#implemented-capabilities) below for
exactly what that covers. All six deliberately produce **no
`DisturbanceRecord` and no waveform**: a CSV or Excel file is accepted
as raw, immutable input into a new `PreparationSession` (in-memory,
`app.services.preparation_session_registry`) and surfaced in Recording
Events with status `Needs Preparation` — structurally excluded from
`GET .../sources` so it can never reach the Workspace Sidebar's
channel-selection list or normal waveform loading. Excel additionally
gets worksheet structure discovered (name/order/visible/best-effort
row-column counts) and a selectable current worksheet. Slice 3 adds a
dedicated Data Preparation Workspace page where the user can page
through the rows of a CSV or the currently selected Excel worksheet —
server-paginated (≤1000 rows/request), no header-row assumption, no
column-role/time-axis interpretation. Slice 4 layers a sparse,
non-destructive Working Dataset overlay on top (cell edit/clear/reset,
row exclude/include, column ignore/unignore, Reset All, undo/redo),
merged into that same preview at read time only — raw bytes are never
mutated, and the overlay never duplicates the dataset. Slice 5 extends
that same overlay with manual header-row selection, data-region
narrowing, and column semantic-role assignment (`unknown`/`waveform`/
`time_axis`/`metadata`/`quality_status`/`ignore`) — still no time-axis
FORMAT interpretation, still no automatic classification of anything.
Slice 6 adds the Readiness Issue LANGUAGE AND TRANSPORT model
(`blocking`/`warning`/`info` severities, three conservative `info`-only
issue codes derived live from configuration state) — explicitly NOT the
full Readiness Validator, no readiness gate, no status transition.
Slices 7–13 (the extensible time-axis framework, initial time-axis
interpreters, the full Readiness Validator, canonical `DisturbanceRecord`
conversion, existing waveform integration, export, and progressive
automation) remain unimplemented and require their own explicit owner
go-ahead before starting, per
[Change governance](../../CLAUDE.md#change-governance) — being recorded
in the architecture document's own slice sequence does not itself
authorize starting any of them.
`SourceMetadata.timing_reference` still reserves a value other than
`"absolute"` for a future importer with no trustworthy absolute
recording timestamp — a CSV/Excel preparation source does not reach
`SourceMetadata` at all yet (see above), so this remains genuinely
unreached until a later slice actually produces a `DisturbanceRecord`.

## Repository identity

`[FACT]`, verified 2026-08-14 via `git remote -v` in each local clone:

- `oruxa_powerwave` (this repo): `git@github.com:myza81/oruxa-powerwave.git`
  (SSH), branch `main`.
- `powerwave` (reference desktop app, macOS clone at
  `/Volumes/externalDrive/code-gym/powerwave/`): `https://github.com/myza81/powerwave.git`
  (HTTPS), branch `main`, at commit `3156392`.

These are two distinct GitHub repositories. See
[README.md — Repository identity](README.md#repository-identity--do-not-confuse-the-two-projects)
for the full rule against confusing them.

## Known infrastructure

`[FACT]`:

- DEV: `https://dev.powerwave.oruxa.uk` (frontend), `https://api.dev.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave-dev`, ports 8200/8201.
  Auto-deploys after CI succeeds on `main` (DEC-036) — this is where the
  live application, including all work described above, actually runs.
- PROD: `https://powerwave.oruxa.uk` (frontend), `https://api.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave`, ports 8100/8101. Deployed
  only via manual `workflow_dispatch`, deliberately kept behind DEV.
- See [docs/development/development-workflow.md](../development/development-workflow.md)
  for the full deployment workflow.
