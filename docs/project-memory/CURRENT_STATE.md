# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now** — what is implemented, what is
> architecturally true, what is intentionally deferred, and what comes
> next. For how the project got here (phase-by-phase implementation
> records, UAT chronology, individual bug fixes), use
> [DECISIONS.md](DECISIONS.md), [HANDOFF.md](HANDOFF.md), and Git history.
> Do not let this file accumulate into a diary — when updating it, replace
> superseded claims, don't append to them.

Last meaningful update: **2026-09-05**. A Preparation Status integrity
fix ([DECISIONS.md — DEC-083](DECISIONS.md#dec-083--preparation-status-must-reflect-the-effective-current-configuration-visible-to-the-user-a-manual-time-axis-is-unconditionally-blocking-never-ready-confirmed-or-not-and-a-time-axis-draft-that-differs-from-the-last-savedapplied-configuration-produces-its-own-blocking-unsaved-changes-issue-computed-live-client-side-with-zero-network-round-trip))
closes a real gap: the `manual` Time Axis interpreter (an engineer
assertion, never a real per-row reading) could previously reach
`is_ready=True`/"Ready for Powerwave" -- `readiness_service` never
encoded the SAME unconditional exclusion `is_time_axis_resolved()`/
`convert_preparation_source()` already both enforce, regardless of
`confirmed`. `readiness_service._time_axis_readiness_issues()` now
blocks any `manual` configuration outright (`ISSUE_TIME_AXIS_MANUAL_
UNRESOLVED`). Separately, the Data Preparation Time Axis form had no
"unsaved draft" concept at all -- a user could change the interpreter/
family/provenance/confirmed/columns without clicking Save while
Preparation Status kept describing the OLD, still-applied
configuration. `frontend/index.html` now compares the form's live
fields against the last-saved configuration client-side
(`wwDataPrepTimeAxisDraftIsDirty()`, zero network round trip) and
layers a synthetic blocking "Unsaved Time Axis changes" issue
(`wwDataPrepEffectiveIssueSummary()`) that the Preparation Status
headline/counts, View Issues, Continue-to-Powerwave, and Export Cleaned
Data ALL now read through, so they can never disagree. See
[Implemented capabilities](#implemented-capabilities). A prior same-day
hardening/transparency enhancement ([DECISIONS.md — DEC-082](DECISIONS.md#dec-082--explicit-time-axis-interpreter-selection-is-authoritative-auto-detection-may-recommend-but-a-central-allowed_families-compatibility-guard-blocks-confirmationmaterialization-whenever-an-explicitly-selected-or-restored-sample-interpreters-own-family-contract-does-not-match-what-was-actually-detected))
closes a real gap: an explicitly-selected sample interpreter (e.g.
`absolute_datetime`) whose own detected family did not actually match
its declared contract (e.g. genuinely bare time-of-day data) previously
reached `is_ready=True` and converted successfully as if nothing were
wrong -- the mismatch was never centrally guaranteed to block. Every
sample interpreter now declares its own `allowed_families` (`app/
services/time_axis_service.py`, right next to `interpreter_id`); a new
`DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH` (routing to the existing
`STATUS_NEEDS_ATTENTION`, added to `readiness_service`'s existing
blocking-code set) is applied centrally at all three `detect()` call
sites (save, live GET, dry-run preview) -- so `is_ready`/conversion/
export are all protected for free via the SAME pre-existing mechanism
`unparseable_datetime` already uses, never a new gate. The selected
interpreter is never silently changed: the Data Preparation Time Axis
panel now shows an inline "Use `<suggested interpreter>`" action on a
mismatch (existing progressive-disclosure diagnostics list, no new
modal) that only switches the dropdown when explicitly clicked.
`repeated_timestamp_precision_loss` is the one interpreter whose own
`allowed_families` genuinely lists two families
(`FAMILY_ABSOLUTE`/`FAMILY_PARTIAL`), matching what `_analyze_buckets()`
already intentionally supports. See
[Implemented capabilities](#implemented-capabilities). A prior same-day
enhancement
([DECISIONS.md — DEC-081](DECISIONS.md#dec-081--csvexcel-absolute-time-support-extended-to-minute-resolution-24-hour-time-of-day-and-explicit-ampm-hour-only-time-plus-fixed-duration-elapsed-units-minuteshoursdaysweeks-bare-hour-only-date-onlyweek-onlymonth-onlyyear-only-absolute-time-elapsed-monthsyears-and-the-existing-iso-reduced-precision-fast-path-gap-all-remain-explicitly-out-of-scope))
closes a real reported gap: `_TIME_PATTERNS` (the shared pattern table
`absolute_datetime`/`split_date_time` both use) had no 24-hour
minute-resolution pattern at all (`"3/6/2026 17:25"` was unparseable,
even though the 12-hour minute-only form already worked), and
`KNOWN_ELAPSED_UNITS` had no fixed-duration minutes/hours/days/weeks
despite the conversion mechanism trivially supporting them. Added:
`%H:%M` (24-hour minute resolution), explicit AM/PM hour-only
(`1pm`/`2am`, case-insensitive, with or without a space), and elapsed
`minutes`(60s)/`hours`(3600s)/`days`(86400s)/`weeks`(604800s) with
fixed, deterministic multipliers. Deliberately NOT added (see DEC-081
for the full boundary): bare 24-hour hour-only, absolute date-only/
week-only/month-only/year-only, and elapsed months/years (no fixed-
seconds factor exists for a calendar-variable unit, and this
interpreter never has an anchor date such a unit could be resolved
against). The pre-existing ISO-8601 reduced-precision fast-path gap
(`datetime.fromisoformat()` silently accepting date-only/week-only ISO
strings) remains unchanged and separately tracked. 55 new tests
(3039 -> 3094 passed). See [Implemented capabilities](#implemented-capabilities).

A prior-day (2026-09-04) correctness fix
(no DEC — a bug fix implementing already-expected behavior, not a new
owner-level product decision) closes a confirmed Data Preparation
Workspace concurrency race: rapid metadata edits (column role/
Engineering Quantity/Measured Unit, header row, data region, cell
edits, row exclusions, undo/redo/reset, worksheet switching) could
previously have their frontend state silently regressed or corrupted
because `wwDataPrepFetchPreview()` (the ONE function ~30 call sites
funnel through) applied whichever `/rows` response arrived last over
the network, not whichever request was fired last. Fixed entirely in
`frontend/index.html`, with **zero backend changes** — the backend's
own `WorkingOverlay` was already correct; every accepted edit was
already durable, just sometimes displayed out of order. Four layered
guards now protect every path through that one function: a monotonic
`previewRequestSeq` counter (only the latest request's response may
ever apply, the same pattern `wwTable.requestSeq`/
`channelEntry.requestSeq` already use elsewhere), explicit source/
worksheet-identity checks captured at request time, and a
`working_revision` monotonicity check (an older revision never
overwrites a newer one, even across the mutation-response path via
`wwDataPrepApplyOverlaySummary()`). A separate, per-column write-
serialization mechanism (`wwDataPrepEnqueueColumnWrite()`) closes the
confirmed Engineering-Quantity/Measured-Unit dependency race (a rapid
Quantity→Unit edit could previously reach the backend out of order and
be rejected with `400 invalid_measured_unit` since Measured Unit
validation depends on the column's current Quantity) — writes for the
SAME column (role/quantity/unit) are now strictly ordered, while
different columns continue to progress fully independently. A tenth
same-day enhancement
([DECISIONS.md — DEC-080](DECISIONS.md#dec-080--csvexcel-waveform-columns-may-carry-an-explicit-measured-unit-quantity-dependent-and-never-guessed-from-engineering-quantity-cleaned-exports-encode-it-as-an-additional-strict-suffix-a-re-upload-restores-analogchannelunit-now-reaches-per-unit-conversion-for-csvexcel-closing-the-dec-077-conversion-gap))
adds an explicit, user-selected **Measured Unit** for CSV/Excel
Waveform columns — a closed, quantity-dependent list (e.g. Voltage:
`V`/`kV`; Active Power: `W`/`kW`/`MW`/`GW`), separate from and never
guessed from Engineering Quantity (DEC-077). This closes a real
conversion gap DEC-077's own investigation had already surfaced:
`AnalogChannel.unit` was hardcoded to `""` for every CSV/Excel channel,
so Per-Unit conversion silently stayed `base_required` even with a base
correctly configured. `preparation_conversion_service.py` now writes
the selected Measured Unit into `AnalogChannel.unit` directly — the
entire fix, since `app.domain.per_unit`'s own conversion functions
already accepted and normalized a measured-unit string; zero changes
were needed to `per_unit.py`, `group_aware_per_unit.py`, or DEC-078's
Angle per-unit guardrail. Cleaned exports encode the unit as an
additional strict suffix (`"<label> (<Quantity>) [<Unit>]"`), restored
on re-upload without requiring the manifest; a blank unit remains valid
and is never a readiness blocker. See
[Implemented capabilities](#implemented-capabilities). A ninth
same-day enhancement
([DECISIONS.md — DEC-079](DECISIONS.md#dec-079--canonical-table-view-v1-a-read-only-one-recording-at-a-time-table-over-the-exact-canonical-disturbancerecord-with-a-new-boundedpaginated-get-sourcesidtable-endpoint-no-cross-source-merging-no-source-format-branching-no-workspace-synchronization-time-offsets))
implements **Canonical Table View v1**, replacing the previously-
disabled sidebar "Table" button and the Waveform|Table|Split
placeholder with a real, read-only table over one recording's exact
canonical `DisturbanceRecord` at a time — never a merge of multiple
recordings, never a reconstruction of the raw source file, never a
second copy of Waveform View's own plotting data. A new
`GET .../sources/{id}/table?offset=&limit=` endpoint returns exact,
unreduced canonical rows (deliberately NOT reusing the waveform
endpoint's point-budget/envelope reduction); a "row" is simply a slice
of the same shared `DisturbanceRecord.waveform_data` DataFrame every
analog and digital channel already lives in, so multi-rate COMTRADE and
irregular CSV/Excel timing both work with zero source-format branching
anywhere in the new code. Table time is always the recording's own
canonical source time — workspace synchronization offsets (manual
alignment, common t0, event sync) are a Waveform-View-only concept and
are never applied here. Pagination reuses the existing Data Preview
pagination UX verbatim; Per-Unit display mode is verified (via a
dedicated regression) to never affect table values. See
[Implemented capabilities](#implemented-capabilities). An eighth
same-day enhancement
([DECISIONS.md — DEC-078](DECISIONS.md#dec-078--voltage-anglecurrent-angle-channels-plot-on-a-secondary-right-y-axis-sharing-their-magnitude-siblings-panel-the-same-two-quantities-are-never-eligible-for-voltagecurrent-per-unit-conversion))
plots Voltage Angle/Current Angle channels on a genuine secondary
(right) Plotly Y-axis while keeping them in the SAME panel as their
magnitude sibling — panel grouping itself (by broad `engineering_type`)
is unchanged; only axis selection within a panel is new, keyed purely
on the canonical `engineering_quantity` (DEC-077), never source format.
A secondary axis appears only when a panel genuinely mixes an angle
channel with a non-angle one; an angle-only panel keeps its one axis,
retitled "Angle." The SAME enhancement closes a real risk the
investigation found: `engineering_quantity` never reached the plotting
layer before this (dropped one hop after the channel list fetch), and
the backend's own per-unit eligibility check keyed on broad
`engineering_type` alone — meaning a Voltage-Angle channel was
previously eligible for kV-scale/Voltage-Base per-unit conversion, a
physically meaningless operation. Voltage Angle/Current Angle are now
always `not_applicable` for per-unit conversion, regardless of
configuration; COMTRADE and calculated channels (whose
`engineering_quantity` stays "Undefined") are completely unaffected.
See [Implemented capabilities](#implemented-capabilities). A seventh
same-day enhancement
([DECISIONS.md — DEC-077](DECISIONS.md#dec-077--csvexcel-waveform-columns-may-carry-an-explicit-engineering-quantity-cleaned-exports-encode-it-as-a-strict-deterministic-label-suffix-that-a-re-upload-restores-without-depending-on-the-manifest))
adds an explicit, user-SELECTED "Engineering Quantity" for CSV/Excel
Waveform columns (Voltage/Voltage Angle/Current/Current Angle/Active
Power/Reactive Power/Frequency/ROCOF/Undefined), fixing the root cause
a prior-session investigation found: the existing channel classifier
(`classify_analog_channel()`) was never broken, CSV/Excel simply never
fed it a signal. Selecting a quantity flows straight into canonical
channel metadata (`AnalogChannel.parameter_type`) at conversion time,
reusing that SAME classifier unchanged — COMTRADE and calculated
channels are completely unaffected. Cleaned exports encode a known
quantity as a strict `<label> (<Engineering Quantity>)` header suffix
(e.g. `CBDK_V1 Magnitude (Voltage)`), which a re-upload restores
deterministically once the column is assigned the Waveform role — the
manifest is never required for restoration. See
[Implemented capabilities](#implemented-capabilities). A same-day UX
refinement (no DECISIONS entry — a straightforward navigation
improvement, not an architectural decision) gives the Data Preparation
Workspace's raw
preview pager First/Last buttons and direct page-number entry
alongside the existing Previous/Next: `[First] [Previous]  Page
[__] of N  [Next] [Last]`. First/Last jump straight to the target page
in one bounded request (reusing the exact same final-offset formula
"Go to Last Rows" already used, which remains a separate, Data-Region-
scoped control), never stepping through intermediate pages; the page
input validates `1 <= page <= total_pages` client-side and rejects
invalid values without a backend request. Purely frontend/render-
derived from the existing `offset`/`limit`/`total_row_count` preview
state — no backend/API change. DEC-075's Configured Time column
remains correctly anchored to the dataset's true first active row
across every navigation path (First/Previous/Next/Last/direct jump),
verified directly (see [Implemented capabilities](#implemented-capabilities)).
A sixth same-day enhancement
([DECISIONS.md — DEC-076](DECISIONS.md#dec-076--cleaned-exports-manifestprovenance-bundle-is-now-optional-the-default-export-cleaned-data-action-returns-the-cleaned-csvxlsx-directly-never-a-zip))
makes cleaned export's manifest/provenance bundle OPTIONAL: the default
"Export Cleaned Data" click now downloads the cleaned CSV/XLSX directly
(no ZIP, no forced `manifest.json`); a new, visually secondary
"Download with manifest" action performs the original DEC-074
ZIP+manifest export unchanged. Provenance capability itself is not
removed, only demoted from the default to an explicit opt-in — see
[Implemented capabilities](#implemented-capabilities). A fifth
same-day enhancement
([DECISIONS.md — DEC-075](DECISIONS.md#dec-075--data-preview-shows-a-read-only-derived-configured-time-column-once-the-time-axis-is-resolved-using-the-same-standardized-representation-and-normalization-semantics-as-cleaned-export-dec-074-and-canonical-conversion))
adds a read-only, virtual "Configured Time" column to the Data
Preparation Workspace's own raw/working preview TABLE (`GET .../rows`
gains an additive `configured_time` field) — once the Time Axis is
resolved, the engineer can directly SEE the exact standardized values
(ISO-8601 for absolute, relative seconds for every other family)
Powerwave will actually use, alongside the still-fully-editable
original source Date/Time columns, on every preview page (always
correctly anchored to the dataset's true first active row, never reset
by pagination). Reuses DEC-074's own representation/normalization
exactly — the two can never disagree. See
[Implemented capabilities](#implemented-capabilities). A fourth
same-day enhancement
([DECISIONS.md — DEC-074](DECISIONS.md#dec-074--cleaned-export-serializes-the-resolvedconfigured-time-axis-a-standardized-timetime-s-column-not-the-original-source-time-axis-columns-a-usable-time-axis-plus-at-least-one-waveform-column-is-now-required-before-a-reusable-cleaned-export-can-be-produced))
supersedes Slice 12's own original export-time policy: cleaned export
now serializes the RESOLVED/CONFIGURED Time Axis (one standardized
`Time`/`Time (s)` column, re-calling the already-confirmed interpreter
exactly like Slice 10's own canonical conversion does) instead of the
original source Time Axis columns verbatim — a reusable cleaned export
now REQUIRES a usable Time Axis plus at least one Waveform column (a
real behavior change from "export available regardless of readiness").
A third same-day UAT fix
([DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export))
simplifies the CSV/Excel column-role model to exactly three roles —
`Not Assigned` (the default), `Time Axis`, `Waveform` — retiring
`Unknown`/`Metadata`/`Quality-Status`/`Ignore` and Slice 4's own
separate boolean ignore/unignore toggle. A second same-day UAT fix
simplifies the Time Axis confirmation UX: the generic "☐ Confirmed"
checkbox now appears ONLY when Powerwave is asking the engineer to
accept a derived/reconstructed timing suggestion — never for a plain
native reading, an ambiguity already resolved by an explicit date-
order/unit choice, or directly user-entered timing, all of which Save
alone already persists as usable. An earlier same-day fix recognized
2-digit years (`3/6/26`, `03-06-26`, etc.) for `dmy`/`mdy` date orders.
CSV/Excel ingestion Slices 1-12 (raw preparation through cleaned data
export) remain the current end of the implemented slice sequence.

## Current status

`oruxa_powerwave` is a working COMTRADE waveform-analysis web app: FastAPI
backend (`backend/app/`) + a single-page vanilla-JS frontend
(`frontend/index.html`, no framework/build step), deployed to DEV
(auto-deploy on `main`) with PROD available but held back manually. Beyond
COMTRADE upload/parse/browse, the app now has a full multi-source,
multi-panel waveform workspace with Time-Group-aware synchronization,
cursors, t0, annotations, a group-aware Per-Unit measurement model,
calculated channels, and digital-channel display. CSV/Excel ingestion is
the current workstream — Slices 1-12 (raw preparation-source upload
through canonical `DisturbanceRecord` conversion, existing-waveform-
integration verification, and cleaned data export) are implemented;
progressive automation (Slice 13) is not (see
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
- **DEC-078 (2026-09-04) gives a waveform panel a genuine secondary
  (right) Plotly `yaxis2`** — used ONLY by a Voltage Angle/Current Angle
  trace (`channel.engineeringQuantity`, DEC-077, now threaded all the
  way to the plotting layer), and ONLY when that panel also contains a
  non-angle channel (an angle-only panel keeps its one axis, retitled
  "Angle"). Panel GROUPING is unchanged — a Voltage magnitude and a
  Voltage Angle channel already shared one panel via the broad
  `engineering_type` grouping key; this only decides which of that
  panel's axes each trace uses. COMTRADE and calculated channels
  (`engineering_quantity` always `"Undefined"`) are structurally
  unaffected — no `yaxis2` is ever created for them.
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
- **Canonical Table View v1 (DEC-079, 2026-09-04)**: a read-only table
  showing one recording's exact canonical `DisturbanceRecord` data at a
  time — canonical Time first, then every analog channel (canonical
  order, with unit/Engineering Quantity), then digital channels; a
  source selector switches which recording is shown, always fully
  replacing the table, never merging. Backed by a new
  `GET .../sources/{id}/table?offset=&limit=` endpoint returning exact
  unreduced rows (no plot-style downsampling); paginated with the same
  First/Previous/direct-page-entry/Next/Last UX as Data Preview. Table
  time is the recording's own canonical source time, never a
  workspace-synchronization-adjusted one. Split View is not
  implemented; the sidebar Table button and the local Waveform|Table|
  Split selector share the same `shell.activeView` state.
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
  **DEC-078 (2026-09-04) adds one additive guardrail on top of both
  paths**: `app.services.waveform_service._resolve_effective_per_unit()`
  (the one dispatch point both the group-aware and legacy paths already
  funneled through) now short-circuits to `not_applicable` whenever a
  channel's own `engineering_quantity` (DEC-077) is `"Voltage Angle"` or
  `"Current Angle"`, regardless of its broad `engineering_type` or
  whether a base is configured — an Angle-quantity channel is never
  eligible for Voltage/Current per-unit conversion. `resolve_per_unit()`/
  `resolve_group_aware_per_unit()` themselves are unchanged; every
  channel with `engineering_quantity = "Undefined"` (every COMTRADE
  channel today, and any CSV/Excel channel the engineer never
  classified) keeps today's exact broad-type-only behavior.
  **DEC-080 (2026-09-04) closes a real conversion gap**: CSV/Excel
  Waveform columns may now carry an explicit, quantity-dependent
  Measured Unit (e.g. Voltage: `V`/`kV`), threaded directly into
  `AnalogChannel.unit` at conversion time — previously always `""`,
  which meant `_measured_unit_scale()` could never recognize a CSV/
  Excel Voltage/Current channel's own unit, leaving Per-Unit `base_
  required` even with a base configured. A CSV/Excel Voltage or
  Current channel with a valid Measured Unit and a configured base now
  resolves `configured` and scales into `pu`, identically to COMTRADE
  — zero changes to `per_unit.py`/`group_aware_per_unit.py` themselves
  were needed. A blank unit still leaves the channel `base_required`
  (fail-closed, unchanged); the DEC-078 Angle guardrail is unaffected
  (a valid `deg`/`rad` unit never makes an Angle channel PU-eligible).
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
- **CSV/Excel preparation-source upload through canonical
  `DisturbanceRecord` conversion (verified to behave like any other
  Powerwave source across Time Groups/synchronization/calculated
  channels) and cleaned-data export (CSV/Excel ingestion Slices 1-12,
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
  exclude/include, and a Reset All action, each a sparse dict/set entry
  proportional to edit COUNT — never a second full copy of the dataset.
  Undo/redo is supported via a bounded (200-entry) operation history; a
  `revision` counter increments on every mutation. New endpoints under
  `.../preparation-sources/{id}/working/...`; each and the existing
  `GET .../preparation-sources` (list/detail) responses now carry a
  `working_overlay` summary (`working_revision`, `edited_cell_count`,
  `excluded_row_count`, `can_undo`, `can_redo`). The existing
  `GET .../rows` preview now returns the WORKING view by default (raw
  merged with the overlay at read time only, never persisted) — each row
  gains `excluded`/`modified_cells` (sparse, provenance-preserving), and
  the page-level response gains `working_revision`. Raw bytes are never
  mutated. The Data Preparation Workspace's table gained click-to-edit
  cells (a plain `<input>`, no spreadsheet-grid library), a per-cell
  reset action, a row toggle button, Undo/Redo, and a "Reset All
  Changes" confirm dialog; the heading switches from "Raw Data Preview"
  to "Data Preview (Edited)" once any change exists. (Slice 4 originally
  also shipped a separate per-column boolean ignore/unignore toggle,
  `ignored_column_count`/`ignored_columns` fields, and its own quick-
  toggle button in the raw preview table — all retired by the
  2026-09-04 UAT fix described under Slice 5 below, once the
  three-role column model made a separate "ignored" axis redundant.)

  **Slice 5** extends the SAME `WorkingOverlay` (not a second model)
  with header-row selection, data-region narrowing, and column
  semantic-role assignment. **A 2026-09-04 UAT fix
  ([DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export))
  simplified the ORIGINAL six-role model
  (`unknown`/`waveform`/`time_axis`/`metadata`/`quality_status`/`ignore`)
  to exactly THREE roles: `not_assigned` (the sparse, implicit default —
  never written explicitly, exactly like the retired `unknown` did),
  `time_axis`, and `waveform`.** Multiple `time_axis` columns are still
  allowed; a role remains a stated intent only, never validated/
  interpreted. All three (header/region/role) participate in the same
  bounded undo/redo history and revision counter Slice 4 already built.
  New endpoints (`PUT`/`DELETE .../working/header`,
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
  Reset All now also clears header/region/role state. Frontend: a
  "Structure" panel (header-row input, data-region start/end inputs, a
  compact Column/Label/Role mapping table listing exactly Not Assigned/
  Time Axis/Waveform) plus a per-row "Header" quick-select button and
  new row styling for the header row and rows outside the active
  region. The Structure panel's own compact summary line reads e.g.
  "3 Not Assigned · 1 Time Axis · 2 Waveform."

  **DEC-075 (2026-09-04) adds a read-only, VIRTUAL "Configured Time"
  column to this same preview table** — once the current Time Axis is
  resolved (`app/domain/time_axis.py`'s new `is_time_axis_resolved()`,
  the SAME shared eligibility check DEC-074's own export gate reuses),
  `GET .../rows` gains an additive `configured_time: {column_name,
  family, values}` field, computed by a NEW `app/services/time_axis_
  service.build_configured_time_values()` (full-active-region, single
  streaming pass, matching `readiness_service`'s own full-region-scan
  shape) narrowed to the requested page by `configured_time_for_
  preview_page()`. Values use the EXACT SAME standardized
  representation DEC-074's cleaned export already established (ISO-8601
  for absolute, fixed 3-decimal relative seconds otherwise) via the
  SAME shared `time_axis_normalization` module (which gained
  `relative_seconds_with_anchor()` for this — a later preview PAGE's
  own relative values stay anchored to the dataset's TRUE first active
  row, never that page's own first row, so row 201 of a paginated
  dataset still reads e.g. `4.000`, never resets to `0.000`). Never
  counted in `column_count`/`column_labels`/`column_roles` and never
  editable/clearable/excludable/role-assignable — a wrong derived value
  is corrected by changing the Time Axis configuration, never by
  editing the derived cell. Frontend: rendered as the FIRST column in
  the preview table (a distinct dimmed/italic style plus a small
  "Derived" badge and tooltip), refreshed immediately after every Time
  Axis Save/Clear (alongside the existing refresh-on-cell-edit
  behavior) so it never shows a stale value.

  **DEC-077 (2026-09-04) adds an explicit, user-selected "Engineering
  Quantity" to a Waveform-role column's own configuration**, shown as a
  fourth column-mapping-table selector (`Voltage`/`Voltage Angle`/
  `Current`/`Current Angle`/`Active Power`/`Reactive Power`/
  `Frequency`/`ROCOF`/`Undefined`), stored sparsely on the working
  overlay's new `column_engineering_quantities` (mirrors `column_roles`
  exactly — absence means `Undefined`, meaningful only for a Waveform
  column, participates in the same undo/redo/revision history). The
  selection flows into `AnalogChannel.parameter_type` at conversion
  time and is classified by the EXISTING, unmodified-in-behavior
  `app.domain.channel_classification.classify_analog_channel()` — the
  same function COMTRADE already used — never a second, CSV-specific
  classifier; a new additive `engineering_quantity` field (default
  `"Undefined"`) rides alongside the existing broad `engineering_type`
  on every channel summary, with a deterministic mapping between the
  two (`broad_engineering_type()`) so every existing downstream
  consumer (channel-browsing groups, calculated-channel type
  inheritance, per-unit measurement-group eligibility) is completely
  unaffected. Cleaned exports encode a known quantity as a strict
  `<label> (<Engineering Quantity>)` header suffix (never `"
  (Undefined)"`); re-uploading that file restores the quantity
  deterministically once the column is (re-)assigned the Waveform role
  — via the SAME suffix grammar the exporter writes, exact-match only,
  never confused with the Configured Time column's own `"(s)"` suffix.
  Role=Waveform itself is never auto-assigned by a self-describing
  label — investigated per the task's own instruction; no existing
  precedent for automatic role assignment was found, so only the
  quantity restores, never the role.

  **A same-day UX refinement (2026-09-04, no DECISIONS entry) adds
  First/Last and direct page-number entry to this same preview's
  pager**, alongside the existing Previous/Next: `[First] [Previous]
  Page [__] of N [Next] [Last]`. Entirely frontend/render-derived from
  the existing `wwDataPrep.offset`/`limit`/`totalRowCount` state (no
  backend/API change) — `currentPage`/`totalPages` are computed fresh
  on every `wwDataPrepRenderPagination()` call, never a second,
  independently-tracked paging source of truth. `First` sets `offset =
  0`; `Last` reuses the EXACT SAME final-offset formula
  (`floor((total-1)/limit)*limit`) `wwDataPrepGoToLastRowsBtn` (Data
  Region's own "Go to Last Rows," a distinct, still-separate control)
  already established, rather than a second "last page" calculation —
  both jump directly in one bounded request, never stepping through
  intermediate pages. `Last`/the page input stay disabled whenever
  `total_row_count` itself is unknown (some Excel worksheets), matching
  "Go to Last Rows"'s own existing guard. The page-number input
  validates `1 <= page <= total_pages` client-side on Enter or blur and
  restores the current page on any invalid value (`0`, negative,
  non-integer, out of range, blank) without ever issuing a backend
  request. DEC-075's Configured Time column stays correctly anchored to
  the dataset's TRUE first active row across every navigation path
  (First/Previous/Next/Last/direct jump) — confirmed directly (e.g. row
  201 of a 0.02s-interval dataset reads `4.000` whether reached via
  repeated `Next` or a direct jump to page 2).

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
  exception, and a real runtime failure never becomes one. Only two
  issue codes exist today (`header_not_selected`,
  `data_region_unconfigured`), produced by a short, linear
  `collect_preparation_issues()` that checks already-known CONFIGURATION
  facts only — no data interpretation — and every one of them is `info`
  severity, never implying invalidity. (A third code,
  `column_roles_unassigned`, existed originally but was retired by the
  2026-09-04 UAT fix — DEC-073 — once the three-role column model made
  a column left `not_assigned` a normal, intentional final state rather
  than incomplete configuration; readiness now blocks on the MEANINGFUL
  `time_axis_unconfigured`/`waveform_channel_missing` issues instead if
  every column is left unassigned.) Issues are derived
  LIVE on every request (no cache, no database); `evaluated_revision`
  always equals `current_revision` and `is_stale` is always `false`
  today. New `GET .../preparation-sources/{id}/issues` endpoint, scoped
  to the selected worksheet the same way `GET .../rows` already is.
  Frontend: a "Preparation Status" panel showing severity counts and a
  grouped Blocking/Warning/Info list (see the UX-refinement paragraph
  below for its own current, collapsed-by-default presentation),
  refetched alongside every preview load (which already covers "refetch
  after every mutation" for free). Recording Events status stays `Needs
  Preparation` throughout — no `Ready`/`Preparation Error` status, no
  "Open in Powerwave" action, and no readiness gate exist anywhere in
  this slice.

  **Post-Slice-6 UX refinement** (owner UAT, 2026-08-31, presentation
  only — no preparation architecture/API/issue-semantics change):
  both the Preparation Status and Structure panels now default to a
  **compact summary**, expanded only on request (progressive
  disclosure), per owner feedback that the fully-expanded default
  layout felt overwhelming. Preparation Status shows its counts line
  plus a "View Issues"/"Hide Issues" toggle — the detailed
  Blocking/Warning/Info list is collapsed until requested (a
  `blocking_count > 0` lead-in text, "Needs Attention — ...", is
  wired into the same counts line as a presentation-only shell for a
  future readiness state; Slice 6 itself never produces a `blocking`
  issue, so this branch is currently unreachable in practice). Structure
  shows a compact `Header: … / Data range: … / Columns: …` summary line
  with a single "Configure"/"Hide" toggle; the header/data-region inputs
  and the full column-role mapping table only render inside that
  toggled section. Both expand/collapse flags are frontend-only,
  session-scoped state (`wwDataPrep.issuesExpanded`/
  `structureExpanded`), reset to collapsed every time the Data
  Preparation Workspace is (re)opened — never persisted, never sent to
  the backend. Every existing interaction (row-level "Set as Header,"
  the column-role `<select>`s, Set/Reset Region, Undo/Redo, Reset All,
  issue-driven worksheet navigation) is unchanged; only its default
  visibility changed.

  **Data-region end-selection UX refinement** (owner UAT, 2026-09-01):
  `DataRegion` gains `end_mode` (`source_end`/`specific`, defaulting to
  `specific` so every pre-refinement call/request shape keeps working
  unchanged) — `end_mode="source_end"` lets the region's own upper
  bound float with the source/worksheet's own end instead of requiring
  a manually-found numeric row; `end_row` stays `None` for that mode
  (never a resolved/guessed value). Still ONE dataset-wide boundary per
  worksheet/source — no per-column end, verified directly against a
  source whose columns end on different rows. A new "Go to Last Rows"
  frontend action is pure navigation (reuses the existing paged-preview
  fetch and the existing `total_row_count`) — it never touches the
  region, the working overlay, or the revision counter. The Structure
  summary's "Data range" line now reads "Rows N–end" for a floating
  boundary, "Rows N–M" for a specific one. An optional per-column
  "last populated row" diagnostic from this same refinement's own scope
  was evaluated and deferred (would need a new, more expensive scan
  than anything already cached/established for either format — see
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md §18](CSV_EXCEL_INGESTION_ARCHITECTURE.md),
  open item 10). Note: commit `db72885` ("fix: resize the font-size")
  unintentionally contains both the owner's own CSS change and the
  completed `app/domain/working_overlay.py` portion of this refinement
  — a commit-history attribution/message mismatch only, not a code
  defect; left as-is per explicit owner direction.

  **Slice 7** (2026-09-01) implements the extensible time-axis
  interpretation FRAMEWORK from
  [CSV_EXCEL_TIME_INTERPRETATION.md](CSV_EXCEL_TIME_INTERPRETATION.md) —
  deliberately zero real datetime/elapsed/sample-index parsing, zero
  reconstruction/confidence-calculation logic, zero readiness gating
  (all Slice 8+). New `app/domain/time_axis.py`: five open-ended
  semantic families (`absolute`/`elapsed`/`sample_index`/`partial`/
  `unknown`), a four-state (not five — "inferred" was deliberately
  excluded) provenance model, a seven-state status model, and a
  `TimeAxisDiagnostic` model kept SEPARATE from `PreparationIssue`
  (never counted into `PreparationIssueSummary`). `TimeAxisConfiguration`
  is stored per-worksheet/source in a new `WorkingOverlay.time_axis`
  dict — the same sparse/frozen-replace pattern as `header_row`/
  `data_region`/`column_roles`, sharing the same bounded undo/redo
  history and revision counter. A configuration may only reference
  columns currently carrying the `time_axis` column role; if that role
  changes later, the stored configuration is left untouched but reported
  as `unsupported` on every live read (no auto-clearing). A small,
  explicit interpreter registry (`app/services/time_axis_service.py`)
  holds exactly two non-parsing interpreters — `manual` (stores whatever
  the user states) and `unsupported` (the universal fallback) — with
  Slice 8 adding real interpreters to the same registry later. New
  endpoints: `GET .../time-axis`, `PUT`/`DELETE .../working/time-axis`,
  `GET .../time-axis/interpreters`. Frontend: a compact,
  progressive-disclosure "Time Axis" panel consuming (never duplicating)
  the Structure panel's own column-role state, supporting multiple Time
  Axis columns. `time_grouping.py` and `DisturbanceRecord` were not
  touched. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 7](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 8A** (2026-09-01) implements the first two of Slice 8's five
  proposed initial interpreters — single-column absolute datetime and
  Date + Time — as REAL, deterministic (non-fuzzy) interpreters
  registered as `absolute_datetime`/`split_date_time` in
  `app/services/time_axis_interpreters.py`, on top of the Slice 7
  framework with zero framework-shape changes beyond what it already
  anticipated. A small, explicit `datetime.strptime` pattern table per
  date order (`dmy`/`mdy`/`ymd`) plus `datetime.fromisoformat`'s own
  ISO-8601 fast path — no fuzzy/`dateutil` parsing. Date-order ambiguity
  is resolved BY ELIMINATION first (`strptime` already rejects an
  invalid calendar date, so a day value over 12 alone makes
  `31/08/2026` unambiguous) and only genuinely 2-or-more-order-valid
  input produces an `ambiguous_date_order` diagnostic and the new
  `review_required` status (Slice 7's own reserved-but-unreachable
  status is now real) — `confirmed=true` is rejected server-side while
  that diagnostic remains. A bare time-of-day column is reported
  `family=partial`, never silently promoted to `absolute`. A new,
  bounded (50-row) sample-fetch reuses the existing paged-preview
  mechanism verbatim; a new `POST .../working/time-axis/interpret`
  dry-run action returns a bounded (20-row) {original, interpreted}
  preview without storing anything. Frontend: the Time Axis panel
  gained an "Interpreter" selector switching between Manual's plain
  fields and a Detect → review ambiguity → preview → Confirm flow. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **`[UAT FIX, 2026-09-04]`** a real owner-reported source
  (`3/6/26`+`18:04:00.000`, Date + Time) previously fell all the way to
  a generic "could not be parsed" failure — root cause: the date-order
  pattern table had NO 2-digit-year (`%y`) candidate at all, only
  4-digit-year, so `strptime` genuinely rejected every candidate before
  ever reaching the ambiguity-by-elimination logic above. Fixed:
  `dmy`/`mdy` (not `ymd` — no reported example uses a year-first
  2-digit shape) gained `%y` candidates, with an explicit century rule
  (`00-69 -> 2000-2069`, `70-99 -> 1970-1999`) applied as one documented
  post-hoc correction to Python's own native `%y` inference (which
  differs by exactly one value, `69`). `3/6/26` now correctly reaches
  the EXISTING `ambiguous_date_order`/`review_required` mechanism above
  — zero new ambiguity system. Diagnostic wording was also sharpened:
  a viable-but-undecided reading now says "Date format needs
  confirmation... Choose the intended date order below" (never the
  generic failure wording), and a genuinely unsupported reading now
  names up to 5 concrete failing `(row_number, value)` examples in its
  own `details`, rendered by the existing Time Axis diagnostics list.
  See `docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md`'s own
  Slice 8A section for the full account.

  **`[UAT FIX, 2026-09-04]`** a second same-day fix: the generic "☐
  Confirmed" checkbox previously appeared under EVERY sample-
  interpreter result, including a plain native reading with nothing
  actually uncertain about it. Investigation (before any code change)
  found `app.domain.time_axis.resolve_status()` already implements the
  desired policy end to end: `provenance == "reconstructed"` (Slice
  8C's own repeated-timestamp suggestion) is the ONLY route to
  `review_required` that function gates on `confirmed` — native
  readings, ambiguities resolved by an explicit date-order/unit choice,
  and direct user-entered interval/rate all ALREADY reach
  `is_ready=True` with `confirmed=False`, verified directly against
  live `set_time_axis_configuration()`/`build_issue_summary()` calls,
  not assumed. Zero backend code changed. Frontend gained one
  centralized rule, `wwDataPrepTimeAxisRequiresExplicitConfirmation()`,
  mirroring that same single condition — the confirmation control now
  appears ONLY for a reconstructed suggestion, labelled "I confirm this
  reconstructed timing" (never the generic word "Confirmed"); every
  other case shows `[Save]` alone. The Manual interpreter (a separate,
  lower-level path, out of this fix's scope) keeps its own original
  always-shown generic checkbox unchanged. See
  `docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md`'s own Slice 8A
  section for the full investigation/fix account and
  `backend/tests/test_time_axis_service.py::TestConfirmationPolicy` for
  the regression coverage locking in the (unchanged) backend policy.

  **Slice 8B** (2026-09-02) implements the next two of Slice 8's five
  proposed initial interpreters — elapsed numeric time and sample
  index — as `elapsed_numeric`/`sample_index` in the SAME
  `app/services/time_axis_interpreters.py`, reusing Slice 8A's own
  interpreter contract unchanged (two new optional `detect()`
  parameters, `requested_unit`/`requested_interval_seconds`, ignored by
  the two Slice 8A interpreters). Neither needed a new stored field:
  `TimeAxisConfiguration.unit`/`.interval_seconds` already existed
  since Slice 7 anticipating exactly this. `elapsed_numeric` requires
  an explicit unit (`seconds`/`milliseconds`/`microseconds`/
  `nanoseconds`, plus `minutes`/`hours`/`days`/`weeks` since DEC-081 —
  fixed, deterministic multipliers only; calendar-variable `months`/
  `years` remain unsupported, deliberately) — an absent unit produces a `missing_elapsed_unit`
  diagnostic reusing Slice 8A's own ambiguity→`review_required`
  mechanism verbatim; `confirmed=true` is rejected while it remains.
  `sample_index` treats an absent `interval_seconds` as
  `provenance=index_only`, a COMPLETE non-error state reusing Slice 7's
  own pre-existing `STATUS_INDEX_FALLBACK` precedent (already forced by
  that exact family/provenance combination before any real interpreter
  existed to produce it) — a present, positive `interval_seconds`
  (user-supplied rate or interval, converted to seconds-per-sample
  CLIENT-SIDE — never a second stored representation) is
  `provenance=user_specified` instead. Both interpreters detect
  backward/repeated/gap/non-numeric/missing findings by comparing each
  sampled value only to the previous one, in original row order —
  never sorting, dropping, or synthesizing a row. Frontend: the
  Interpreter selector gained "Elapsed Time"/"Sample Index" entries;
  Elapsed Time shows a required Unit select, Sample Index shows a
  progressive-disclosure Timing radio group (Unknown / Sampling rate Hz
  / Sample interval ms). See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 8C** (2026-09-02) implements the fifth and final Slice 8
  proposed initial interpreter — repeated-timestamp/precision-loss
  detection and user-approved reconstruction — as
  `repeated_timestamp_precision_loss` in the SAME
  `app/services/time_axis_interpreters.py`, reusing Slice 8A/8B's own
  interpreter contract unchanged. Powerwave may detect, analyse,
  suggest, and preview a reconstructed timing — it never silently
  applies one. Consecutive rows sharing an identical native timestamp
  (in original row order, over the same bounded sample) form a bucket;
  first/last buckets never penalize confidence since they may be
  sample-window-truncated. Confidence is qualitative only (High/Medium/
  Low): High requires ≥2 equal-sized interior buckets, Medium covers too
  few interior buckets to compare (but consistent) or a spread of ≤1,
  Low covers everything else. An accepted suggestion is
  `provenance=reconstructed` and always discloses its anchor assumption
  (first sample aligned to the displayed timestamp, by default) via a
  new `anchor_offset_seconds` option — no new stored field was needed
  otherwise (`unit`/`interval_seconds`/`options` already existed since
  Slice 7). A NEW `resolve_status()` rule routes an unconfirmed
  reconstruction to `review_required` WITHOUT blocking confirmation
  (deliberately separate from the ambiguity mechanism Slice 8A built,
  which WOULD have blocked it forever); a genuinely unreliable cadence
  still uses that existing ambiguity mechanism and correctly blocks
  `confirmed=true`, deferring segmented/variable-cadence reconstruction
  rather than guessing. A manual interval/rate override is
  `provenance=user_specified`, never `reconstructed`; missing/extra-
  sample bucket-count anomalies are diagnostics only, never inserted/
  deleted rows; Sample Index remains the always-available, honest
  fallback. Frontend: the Interpreter selector gained "Repeated
  Timestamp (Precision Loss)"; the compact summary shows the suggested
  interval and anchor assumption in plain language, with a collapsed-
  by-default "Adjust" panel (Timing source radio + First sample offset
  ms) for a manual override. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  Slice 8's five proposed initial interpreters are now all implemented
  (8A/8B/8C).

  **Slice 8D** (2026-09-02) implements Time Irregularity Diagnostics — a
  DIAGNOSTIC-ONLY normalization layer over the irregular-timing
  conditions CSV_EXCEL_TIME_INTERPRETATION.md §11's own table already
  named, never a new interpreter and never readiness policy. The one
  real gap it fills: `absolute_datetime`/`split_date_time` (Slice 8A)
  never checked row-to-row timing quality at all — only
  `elapsed_numeric`/`sample_index` (8B) and `repeated_timestamp_
  precision_loss`'s own bucket cadence (8C) ever did. A new shared
  `_analyze_time_sequence()` fills that gap, called only once a resolved
  (non-ambiguous) reading already exists; for `split_date_time`
  specifically it walks the COMBINED per-row date+time value, never the
  date-only column's own sequence. Five genuinely new diagnostic codes
  (`time_goes_backward`, `large_time_gap`, `timestamp_reset_suspected`,
  `partial_midnight_rollover_suspected`, `non_uniform_interval`) — every
  other condition already had an established code from an earlier
  slice, reused verbatim. The reference "expected local interval" is the
  MINIMUM positive consecutive delta in the bounded sample (robust to a
  large outlier inflating its own comparison point); a transition at
  least 5x that reference is "large" in either direction; a `partial`-
  family transition from near the end of the day to near the start is
  checked FIRST and reported as a midnight rollover instead — never a
  fabricated date, never generic backward-time corruption. Exact repeats
  are deliberately never flagged here (Slice 8C's own interpreter owns
  that). All five new codes are `SEVERITY_WARNING`/`AMBIGUITY_UNAMBIGUOUS`
  (the same combination `elapsed_time_goes_backward` already uses) — no
  new `resolve_status()` rule was needed. A new `category` axis
  (`format`/`ordering`/`gap`/`repeat`/`sampling`/`ambiguity`) is a
  COMPUTED property on every `TimeAxisDiagnostic`, never a stored field,
  so zero existing diagnostic construction anywhere needed to change.
  No new API, no new endpoint. Frontend: the compact Time Axis summary
  gained one "Diagnostics" row ("2 findings," hidden when none) — the
  findings themselves stay inside the existing expanded-review list,
  never a new top-level panel. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 9** (2026-09-02) implements the Full Powerwave Readiness
  Validator — answers exactly one question, is the current prepared
  dataset ready to convert into Powerwave, using the SAME `blocking`/
  `warning`/`info` model Slice 6 already established (never a second,
  parallel readiness model). `app.services.readiness_service` extends
  `preparation_issue_service.build_issue_summary()` (the SAME `GET
  .../issues` endpoint, no new route) with real policy: no Time Axis
  configured/unsupported/unresolved, or zero Waveform Channel columns,
  is BLOCKING; a resolved time-axis reading's own diagnostics are
  promoted into `PreparationIssue`s through one explicit policy table
  (`_BLOCKING_TIME_DIAGNOSTIC_CODES`/`_WARNING_TIME_DIAGNOSTIC_CODES`) —
  interpreters themselves still encode no severity opinion at all.
  Sample Index fallback, an accepted reconstruction, manual/user-
  specified timing, and bare time-of-day (partial) readings are all
  WARNING, never blocking — each can reach `is_ready=True`. Two
  DELIBERATELY different validation scopes: time-axis diagnostics stay
  SAMPLE-based (whatever the interpreter's own bounded ≤50-row window
  already saw), but missing/invalid TIME-AXIS and WAVEFORM CHANNEL cell
  values are checked across the ENTIRE active data region via a new
  single-pass streaming generator,
  `preparation_preview_service.iterate_active_region_rows()` — never a
  second materialized copy of the dataset, never a bounded-sample
  guarantee mistaken for a full one. `ERR`/`N/A`/`#VALUE!`/malformed
  numeric text in a Waveform Channel cell is preserved and reported,
  never coerced to zero. Digital-channel validation is explicitly
  deferred (no dedicated column role exists yet). Nothing here ever
  deletes, sorts, or reorders a row, or synthesizes/interpolates a
  value — readiness only ever reports; the engineer resolves. New
  `PreparationIssueSummary.is_ready` field (`blocking_count == 0`).
  Frontend: the EXISTING Preparation Status panel (which already had a
  Slice-6-era "shell for a future Needs Attention state" comment) now
  shows a real "Needs Attention"/"Ready for Powerwave" headline, with
  deliberately NO "Continue to Powerwave" button (canonical conversion
  is Slice 10, not this one) — detailed issues stay collapsed by
  default, unchanged. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 9](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 10** (2026-09-03) implements canonical `DisturbanceRecord`
  conversion — the third and final stage of "Slice 8 → interpret; Slice
  9 → validate; Slice 10 → convert." New
  `app/services/preparation_conversion_service.py`
  (`convert_preparation_source()`) re-runs readiness against the
  CURRENT working revision at conversion time (never trusts stale
  frontend state — the three owner-approved rules this slice opened
  with), builds the canonical time axis by reusing the SAME
  `TimeAxisInterpreter.build_preview_rows()` the Time Axis review UI
  already calls (over the full active region, never the bounded ≤50-row
  sample) — so conversion never re-implements or re-decides any
  per-family parsing/reconstruction logic Slice 8 already settled — then
  constructs a `DisturbanceRecord` and registers it into the SAME
  `WorkspaceRegistry`/`GET .../sources` a COMTRADE upload uses, with
  zero CSV/Excel-specific plotting page. Canonical time is always
  `raw[i] - raw[0]` (relative to the first active sample) for every
  convertible family; `sample_index` additionally requires a known
  `interval_seconds` — an index-only source with `interval_seconds is
  None` is REFUSED at conversion (`ConversionRequiresIntervalError`),
  not because Slice 9 marks it not-ready (it is still `is_ready=True`,
  Sample Index fallback is only a WARNING) but because converting an
  unscaled index into seconds would fabricate a sample-rate that was
  never confirmed. Canonical-model hardening (deliberately minimal, see
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md](CSV_EXCEL_INGESTION_ARCHITECTURE.md)
  for the full rationale): `TimingInformation.start_time`/`.trigger_time`
  widened from required `datetime` to `datetime | None` (an unknown
  absolute start or trigger is `None`, never a fabricated
  `2000-01-01`/`1970-01-01`/`trigger_time = start_time` sentinel) —
  discovered to be the ONLY required change, since `SourceMetadata`'s
  own `start_time`/`trigger_time` fields were already `Optional`
  (Phase 5B/DEC-048) and every downstream consumer
  (`time_grouping.derive_time_groups()`, `synchronization_service.py`,
  `calculated_channel_service.py`) already branches on `is None` —
  "existing waveform integration" needed zero changes. New
  `SamplingInformation.is_uniform` (defaults `True`, matching COMTRADE's
  existing behavior unchanged) flags genuinely irregular canonical
  timing honestly rather than claiming one fabricated average rate;
  ±1% relative tolerance (matching Slice 8B's own
  `non_uniform_elapsed_interval` precedent) decides uniform vs.
  irregular. `nominal_frequency` was deliberately NOT widened to
  Optional (unlike `start_time`/`trigger_time`) because
  `synchronization_service.py` consumes it as a required float for
  event-detection sensitivity — a converted source instead gets a
  documented conventional default (50 Hz) plus an explicit
  `nominal_frequency_assumed: true` provenance flag. Duplicate channel
  labels never lose a channel: first occurrence keeps its label
  verbatim, every later occurrence gets a `__<spreadsheet-column-letter>`
  suffix (e.g. `Voltage`, `Voltage__C`, `Voltage__D`), with the original
  label preserved as each channel's own `description`. Provenance
  (source format, filename, worksheet, preparation revision, time
  family/provenance, interpreter id, header row, data region, excluded
  row count, etc.) is retained in a new, purely additive
  `SourceMetadata.preparation_provenance` dict — no CSV/Excel-specific
  field added to any core waveform schema. Idempotency needed zero new
  code: a successful conversion removes the `PreparationSession` from
  its registry (mirroring COMTRADE's own upload flow, which never
  leaves a stale row behind either), so a repeated `POST .../convert`
  against the same source naturally 404s via the existing
  `SourceNotFoundError` path. New API: `POST
  .../preparation-sources/{source_id}/convert`, returning the SAME
  `SourceSummaryOut` shape a COMTRADE upload returns — never a bespoke
  response. Frontend: the Preparation Status panel now shows the actual
  "Continue to Powerwave" action when `is_ready` AND conversion-capable,
  or a "Ready with limitations" notice with a "Configure Time Axis"
  shortcut for the index-only-without-interval case (never a misleadingly
  enabled Continue button); on success the user is navigated into the
  EXISTING waveform workflow via `openRecordingForAnalysis()` — the same
  entry point a COMTRADE "Open / Analyse" row uses — never a
  CSV/Excel-specific plotting page; on failure the user stays in Data
  Preparation with every preparation control intact. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 10](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 11** (2026-09-03) implements existing-waveform-integration
  VERIFICATION — zero-new-feature bias: proves a Slice-10-converted
  CSV/Excel source behaves like any other Powerwave source across Time
  Groups, synchronization, and calculated channels, fixing production
  code ONLY where an integration defect was actually demonstrated (per
  this slice's own "observed failure → is conversion wrong? → is
  downstream code unnecessarily COMTRADE-specific? → minimally
  generalize" decision sequence). Verified via a new
  `tests/test_slice11_waveform_integration.py` (24 tests): converted-
  source waveform open/range-fetch/cursor-values; multiple converted
  sources (CSV+CSV, CSV+Excel) coexisting independently; COMTRADE +
  converted-CSV coexistence with COMTRADE completely unaffected;
  absolute+absolute Time Group overlap, absolute+elapsed staying
  separate, two elapsed sources each singleton, `partial`-family
  correctly `elapsed_only`; synchronization alignment views (including
  `trigger_time=None`) raising no exceptions; same-source and aligned
  cross-source calculated-channel Addition; cross-source rejection with
  zero resampling for both an elapsed-vs-absolute mismatch and a
  genuinely-different absolute-start mismatch; irregular-timing
  range-fetch preserving the true time array with no fabricated uniform
  rate; `preparation_provenance` surviving a `WorkspaceRegistry`
  round-trip; convert→open→remove→reopen lifecycle coherence with
  calculated-channel removal cascade; repeated-conversion idempotency
  re-confirmed at this layer; a 50,000-row source converting in well
  under a second with its display range-fetch still using the existing
  min/max-envelope reduction.

  **Two real production defects were found and fixed** (both in
  PRE-EXISTING code, not in Slice 10's own conversion logic, and both
  reproduced by a minimal script BEFORE any fix was written): `app.
  domain.time_grouping` and `app.services.calculated_channel_service`
  implicitly assumed every absolute source's `start_time` shared the
  same naive/timezone-aware status — true by construction while COMTRADE
  was the only absolute-time producer (`app.providers.comtrade` never
  attaches a timezone), false the moment a Slice-10-converted CSV/Excel
  source can honestly preserve a real declared timezone offset. (1) A
  genuine crash — `TypeError: can't compare offset-naive and
  offset-aware datetimes` — from `time_grouping.py`'s own interval-
  overlap comparison and placement-offset subtraction, reachable by any
  workspace mixing one naive absolute source (COMTRADE, or a
  timezone-unspecified CSV/Excel one) with one genuinely timezone-aware
  CSV/Excel absolute source; this would 500 `GET .../synchronization/
  time-groups` and every other Time-Group-aware endpoint. (2) A silent,
  SERVER-TIMEZONE-DEPENDENT correctness defect in `calculated_channel_
  service._source_start_epoch()`, which called the naive
  `datetime.timestamp()` directly (interpreting a naive value as the
  server's own local system timezone) — harmless while both compared
  sources were always naive COMTRADE (the arbitrary offset cancels out
  in the difference), but silently wrong and non-deterministic across
  deployment environments once one side is a genuinely timezone-aware
  converted source; this could have silently accepted a misaligned
  cross-source calculated channel or rejected an aligned one, depending
  purely on the backend server's own local timezone. Fix for both: one
  new pure function, `app.domain.time_grouping.normalize_absolute_
  datetime()` — an aware value's real declared offset is honored
  untouched; a naive value is labelled UTC without converting its
  wall-clock numbers, purely so it becomes comparable — applied at
  every point an absolute `start_time` enters comparison/arithmetic in
  both modules. For the previously-only-reachable all-naive (pure
  COMTRADE) case this is a verified no-op: every value gets the
  identical label, so every comparison/subtraction result is
  numerically unchanged. Regression coverage: `TestMixedTimezone
  AwarenessIntegration` in `tests/test_time_grouping_domain.py` and
  `TestMixedTimezoneAwarenessCrossSourceAlignment` in
  `tests/test_calculated_channel_service.py`.

  Zero new `if source_format == "CSV"/"Excel"` branches exist anywhere
  in `waveform_service.py`, `synchronization_service.py`,
  `time_grouping.py`, or `calculated_channel_service.py` (grepped
  directly). No resampling, interpolation, new synchronization
  algorithm, new calculated-channel operation, new Time Group policy,
  or new readiness policy was added. `preparation_provenance` remains a
  domain-layer-only (`SourceMetadata`) field, deliberately NOT exposed
  via `SourceSummaryOut` or any other waveform-facing schema this slice
  — a legitimate deferred item, not a defect (this slice's own task
  explicitly says downstream waveform services need not understand
  preparation internals). See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 11](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 12** (2026-09-03) implements Cleaned Data Export; a
  2026-09-04 enhancement (DEC-074) then supersedes its own original
  export-time policy (below). Governing principle, unchanged: **"Cleaned
  export = the current Working Dataset as prepared by the engineer"** —
  not the raw source, not a silently repaired dataset. New
  `app/services/preparation_export_service.py`
  (`export_preparation_source()`) exports `active data region - excluded
  rows + working cell overrides`, restricted to Waveform columns plus
  ONE standardized configured Time column (see below) — Not Assigned
  columns are omitted (DEC-073; the manifest's own `omitted_columns`
  entries record each excluded column's `role`), preserving remaining
  Waveform source column order, into a cleaned CSV or single-worksheet
  XLSX bundled with a sidecar `<base>_cleaned.manifest.json` inside one
  `<base>_cleaned.zip`.

  **DEC-074 (2026-09-04): the exported Time column is now the
  RESOLVED/CONFIGURED Time Axis, not the original source Time Axis
  column(s) verbatim.** Originally (Slice 12) a Time Axis column
  exported its own current WORKING value byte-for-byte unchanged; this
  was superseded so a cleaned export becomes genuinely re-upload-
  friendly — an engineer who already resolved date-order ambiguity,
  supplied a sampling interval/rate, or accepted a reconstructed timing
  suggestion should not have to repeat that work on re-upload. The
  exported table is now exactly ONE standardized Time column, ALWAYS
  FIRST (a deliberate exception to "preserve source column order," which
  still governs the Waveform columns among themselves), built by
  re-calling the ALREADY-CONFIRMED interpreter's own `build_preview_
  rows()` — the exact same call Slice 10's own canonical conversion
  makes — over the full active region, through a NEW shared module,
  `app/services/time_axis_normalization.py` (`parse_native_time_value()`/
  `relative_seconds()`/`format_absolute_iso()`/`format_relative_
  seconds()`, extracted out of `preparation_conversion_service.py` as a
  pure refactor so the two features can never disagree about what a
  configured Time Axis means). A resolved `FAMILY_ABSOLUTE` reading
  exports one ISO-8601 timestamp per row (header `Time`; millisecond
  precision by default, widened only when genuine sub-millisecond
  precision exists; a real timezone offset preserved exactly, never
  invented). Every other resolved family (elapsed, sample-index-with-a-
  real-interval, partial, or an ACCEPTED reconstruction) exports fixed
  3-decimal seconds relative to the first active row (header
  `Time (s)`) — the same "relative to first" convention Slice 10's own
  `waveform_data["time"]` already uses. The original source Time Axis
  column(s) never appear in the cleaned table; their raw values remain
  fully intact in the immutable source and in `WorkingOverlay` itself,
  and the manifest's own new `exported_time` section (`column_name`,
  `source_columns` by index+label, `family`, `provenance`,
  `interpreter_id`, `date_order`, `interval_seconds`,
  `export_representation`, `timezone_present`, `source_offset_seconds`,
  `reconstructed`) records exactly which raw column(s) it was consumed
  from, for full traceability.

  **A usable, resolved Time Axis plus at least one Waveform column is
  now REQUIRED for a reusable cleaned export** (DEC-074) — a real
  behavior change from Slice 12's own original "available regardless of
  readiness" policy, since there is no honest standardized Time column
  to build from an unconfigured/unresolved/`manual`-interpreter Time
  Axis. `export_preparation_source()` now reuses `PreparationIssueSummary.
  is_ready` directly as its primary gate (every current `blocking`
  readiness issue is already exactly a Time-Axis or Waveform-Channel
  finding, so this is not a second, narrower readiness policy of its
  own), plus the SAME two additional capability constraints Slice 10's
  own canonical conversion already enforces: `manual`/`unsupported`
  interpreter (`ExportUnsupportedInterpreterError`) and `sample_index`
  with no real interval (`ExportRequiresIntervalError`) — both new
  `app/services/errors.py` classes, alongside `ExportNotReadyError` and
  the defensive `ExportTimeAxisValueError`, all mapped to `409`/`500`
  in `app/api/v1/preparation_sources.py` exactly like the existing
  `conversion_*` codes.

  Row/column selection and column-label fallback logic remain pure REUSE
  of Slice 9's `iterate_active_region_rows()` and `preview_preparation_
  source()`'s own already-computed labels; deduplicating Waveform column
  labels still uses the same `__{SpreadsheetLetter}` suffix strategy
  Slice 10 established. Manifest fields otherwise unchanged from Slice
  12: `manifest_version`, `exported_at`, `exported_file`,
  `source_format`, `original_filename`, `worksheet_name`/`worksheet_
  index`, `preparation_revision`, `header_row`, `data_region`,
  `exported_row_count`, `excluded_row_count`/`excluded_rows` (bounded to
  200 listed rows + a truncation flag)/`omitted_columns`/`column_roles`,
  `edited_cell_count`/`cleared_cell_count`, `time_family`/`time_
  provenance`/`interpreter_id`/`time_unit`/`time_interval_seconds`/
  `reconstructed_timing`, `exported_time` (new), and a live `readiness`
  snapshot (built ONLY when a manifest is actually requested — see
  DEC-076 immediately below). Excel export still writes one clean
  tabular worksheet via `openpyxl.Workbook(write_only=True)` (streaming,
  no original styling/formulas/charts/macros preserved) into a NEW
  workbook; CSV export still uses a normalized comma/UTF-8 dialect.
  Still read-only by construction — no `working_overlay` mutation
  function is ever called; `WorkingOverlay.revision` is still captured
  and re-verified around the export (`ExportRevisionChangedError`).
  API: `POST .../preparation-sources/{source_id}/export` — see DEC-076
  immediately below for its current `include_manifest` query parameter
  and default response shape (superseding this paragraph's original
  "always returns the ZIP bytes" description). Frontend: the "Export
  Cleaned Data" secondary action (same Preparation Status panel
  "Continue to Powerwave" lives in) is disabled-by-default with a short,
  single-line guidance message (`wwDataPrepRenderExportAction()`) until
  a resolved, usable Time Axis plus at least one Waveform column exists
  — mirroring "Continue to Powerwave"'s own limitation-notice pattern,
  never a large new warning panel; still triggers a real browser
  download via a throwaway `<a download>` element and never navigates
  away or mutates preparation state.

  **DEC-076 (2026-09-04): the manifest/provenance bundle is now
  OPTIONAL — the default "Export Cleaned Data" click downloads the
  cleaned CSV/XLSX directly, never a ZIP, never a forced sidecar
  `manifest.json`.** Owner-approved UX problem: an ordinary engineer
  only wants the reusable cleaned file and should never be handed a
  ZIP — let alone be expected to understand `manifest.json` — merely to
  get it. `app/services/preparation_export_service.export_preparation_
  source()` gains an explicit `mode` (`EXPORT_MODE_DATA_ONLY`, the new
  default, vs. `EXPORT_MODE_WITH_PROVENANCE`, the original Slice
  12/DEC-074 ZIP+manifest bundle, byte-for-byte unchanged); the API
  exposes the same choice as `POST .../export?include_manifest=true`
  (default `false`). Both modes share identical gating
  (`_ensure_exportable()`, unchanged from DEC-074) and identical
  cleaned-data construction, so they always produce byte-identical
  cleaned data for the same working-overlay revision — `mode` only
  changes the RETURN SHAPE. `EXPORT_MODE_DATA_ONLY` never builds or
  serializes the manifest at all (an efficiency requirement, not merely
  discarding a built manifest). Data-only responses carry the real
  `Content-Type` (`text/csv` or the XLSX spreadsheet MIME type) and a
  `<name>_cleaned.csv`/`.xlsx` filename; the existing
  `expose_headers=["Content-Disposition"]` CORS fix (below) already
  covers every response shape, no CORS change was needed. Frontend: the
  export action is now a split action — the primary "Export Cleaned
  Data" button (`wwDataPrepExport(false)`) is the data-only default; a
  new, visually secondary, underlined-text "Download with manifest
  (cleaned file + provenance)" button (`wwDataPrepExport(true)`,
  `#wwDataPrepExportWithProvenanceBtn`) performs the with-provenance
  export — both share the exact same gated enabled/disabled state
  (`wwDataPrepRenderExportAction()`), since provenance was never a
  separately-gated capability. The download-handling code no longer
  assumes every export is a ZIP (task's own "old frontend expected
  every export to be ZIP" regression note) — the real filename/
  extension always comes from the server's own `Content-Disposition`
  header regardless of mode. Manifest schema/contents are unchanged;
  provenance capability itself is not removed, only demoted from the
  default to an explicit opt-in. Verified: full backend suite 2731
  passed, 0 failed (the same baseline DEC-075 already established,
  confirming no regression from either same-day enhancement); the
  committed browser smoke test (COMTRADE) still passes unchanged; a
  throwaway (not committed) live-browser Playwright UAT confirmed both
  a CSV and an Excel source's default export downloads the cleaned file
  directly (not a ZIP, correct `Content-Type`, correct source-derived
  filename), "Download with manifest" downloads a real ZIP containing
  both the cleaned file and `manifest.json`, and the two exports'
  cleaned data is byte-identical — all with zero console/page errors.

  **One real defect found and fixed by the browser UAT, invisible to
  every backend-only test**: `Content-Disposition` is not a CORS-
  safelisted response header a browser exposes to JavaScript by
  default. Without an explicit `expose_headers=["Content-Disposition"]`
  on the existing `CORSMiddleware` config (`app/main.py`), the
  frontend's cross-origin download `fetch()` could read the ZIP body
  but not the real filename, silently falling back to a generic
  `recording_cleaned.zip` name — invisible to a same-process
  `TestClient` call (which enforces no CORS at all), caught only by the
  live-browser UAT's genuinely cross-origin request. Fixed with one
  line; regression test added:
  `test_content_disposition_is_exposed_for_cross_origin_downloads` in
  `backend/tests/test_main.py`.

  Verified: full backend suite 2665 passed (52 new on top of Slice 11's
  own 2613: 43 export-service + 8 API + 1 CORS regression), zero
  regressions; the committed browser
  smoke test (COMTRADE) still passes unchanged; a throwaway (not
  committed) live-browser Playwright UAT confirmed export from both a
  not-ready and a Ready source with the correct filename, correct ZIP
  contents (cleaned CSV/XLSX + manifest with an accurate readiness
  snapshot), unchanged preparation state afterward, and "Continue to
  Powerwave" still working normally afterward — all with zero console/
  page errors. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 12](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  Progressive automation (Slice 13) is still explicitly NOT part of any
  slice implemented so far — see
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
- CSV/Excel absolute time-of-day parsing (DEC-081): bare 24-hour
  hour-only (e.g. `"2026-06-03 17"`), and absolute date-only/day-only/
  week-only/month-only/year-only readings — each remains explicitly
  unsupported, needing its own future design/policy decision, not a
  correctness gap in the minute-resolution/AM-PM-hour support DEC-081
  added. Elapsed `months`/`years` are structurally excluded (no
  fixed-seconds factor exists for a calendar-variable unit without an
  anchor date), not merely deferred. The pre-existing ISO-8601
  reduced-precision fast-path gap (`datetime.fromisoformat()` silently
  accepting date-only/week-only ISO strings with no diagnostic) also
  remains open, unaffected by DEC-081.

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
row exclude/include, Reset All, undo/redo; originally also a separate
column ignore/unignore toggle, retired by the 2026-09-04 UAT fix
below), merged into that same preview at read time only — raw bytes are
never mutated, and the overlay never duplicates the dataset. Slice 5
extends that same overlay with manual header-row selection, data-region
narrowing, and column semantic-role assignment — originally six roles
(`unknown`/`waveform`/`time_axis`/`metadata`/`quality_status`/`ignore`),
simplified by a 2026-09-04 UAT fix
([DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export))
to exactly three: `not_assigned` (the sparse default), `time_axis`,
`waveform` — still no time-axis FORMAT interpretation, still no
automatic classification of anything. Slice 6 adds the Readiness Issue
LANGUAGE AND TRANSPORT model (`blocking`/`warning`/`info` severities,
two conservative `info`-only issue codes derived live from configuration
state — originally three, until the same 2026-09-04 fix retired the
third, `column_roles_unassigned`, once `not_assigned` became a normal,
intentional final state) — explicitly NOT the full Readiness Validator,
no readiness gate, no status transition.
Slice 7 (the extensible time-axis interpretation FRAMEWORK), Slice 8A
(the first two deterministic time-axis interpreters), Slice 8B (the
next two -- elapsed numeric time, sample index), Slice 8C (the fifth
and final one -- repeated-timestamp/precision-loss detection and
reconstruction), Slice 8D (Time Irregularity Diagnostics -- a
diagnostic-only normalization layer over Slices 8A-8C's own irregular-
timing conditions, never a new interpreter, never readiness policy),
Slice 9 (the Full Powerwave Readiness Validator -- the REAL
`blocking`/`warning`/`info` policy Slice 6 always deferred, see above),
Slice 10 (canonical `DisturbanceRecord` conversion), Slice 11
(existing-waveform-integration verification, including two real
timezone-awareness defects found and fixed), and Slice 12 (Cleaned Data
Export, including one real CORS defect found and fixed -- see above for
the full summaries) are now implemented. Slice 13 (progressive
automation) remains unimplemented and requires its own explicit owner
go-ahead before starting, per
[Change governance](../../CLAUDE.md#change-governance) — being recorded
in the architecture document's own slice sequence does not itself
authorize starting any of them.

**`[DESIGN COMPLETE, 2026-09-01]`**: the Slice 7/8
design specification —
[CSV_EXCEL_TIME_INTERPRETATION.md](CSV_EXCEL_TIME_INTERPRETATION.md) —
settles semantic time families (absolute/elapsed/
sample_index/partial/unknown), a four-state provenance model (native/
reconstructed/user_specified/index_only), the owner-approved
detect→suggest→confirm fallback hierarchy (never discarding samples for
repeated timestamps, never fabricating an absolute anchor per DEC-072
point 5), a qualitative confidence model, the interpreter-registry
extensibility concept, and a progressive-disclosure Time Axis UI shell
matching the existing Preparation Status/Structure pattern. Slice 7 (the
framework portion) is now implemented, per above; Slice 8A (§19 items
1-2, the two deterministic absolute-time interpreters), Slice 8B (§19
items 3-4, elapsed numeric time + sample index), and Slice 8C (§19
item 5, repeated-timestamp/precision-loss detection and reconstruction)
are also now implemented -- §19's full five-interpreter set is
complete; segmented/variable-cadence reconstruction remains explicitly
deferred, per Slice 8C's own scope note above.
`SourceMetadata.timing_reference` reserving a value other than
`"absolute"` for an importer with no trustworthy absolute recording
timestamp is no longer merely reserved — Slice 10's conversion service
is the first real producer of `"relative_elapsed"` (or `None`
`start_time`), for every non-absolute-family CSV/Excel source (see the
Slice 10 summary above).

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
