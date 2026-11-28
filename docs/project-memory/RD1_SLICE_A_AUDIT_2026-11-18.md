# RD-1 Slice A — Recording Details V2.9 Preliminary Audit
**Date:** 2026-11-18  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Status:** `[PROPOSAL]` — awaiting owner approval before any production code changes

---

## 1. Purpose and scope

This document is the read-only Slice A preliminary audit for the Recording
Details V2.9 redesign (RD-1). It establishes the factual baseline — existing
code, API surface, PU dependency map, entry points, and confirmed gaps — that
any implementation must build on. No production files are modified here.

The long-term goal: **Recording Details becomes the central configuration
interface** for recording-related engineering metadata. The declared UX flow
is:

```
Upload → Extract metadata → Detect/suggest groups → Engineer reviews/overrides → Reuse across analyses
```

RD-1 delivers the three-panel workspace (recording metadata, groups list,
group editor). Later phases: RD-2 (nominal frequency / recording identity
editing), RD-3 (CT/VT conversion controls).

---

## 2. Existing Recording Details — factual inventory

### 2.1 Rendering

**`[FACT]`** Recording Details is currently an inline expandable `<tr>` sibling
row beneath each recording's own row in the Recordings table. It is **not** a
separate page or route.

| Element | Location |
|---|---|
| `renderRecordingDetails(source)` | `frontend/index.html:22209` |
| `toggleRecordingDetails(sourceId)` | `frontend/index.html:22750` |
| Toggle button (chevron icon) | Rendered by `renderRecordingsTable()` at `~22635`, COMTRADE only |
| State (expanded set) | `recordingsExpandedDetails` — a `Set<string>` |
| CSS — panel row | `.recording-details-row td` — accent-left-bar, inset padding |
| CSS — zones | `.recording-details-facts`, `.recording-details-timing`, `.recording-details-files` |

### 2.2 Content rendered today

**Zone 1 — Technical:**  
Recorder · Channel counts (Analog/Digital) · Nominal frequency · Timing
reference · Sample count  
(`source.recorder_name`, `source.analog_channel_count`,
`source.nominal_frequency`, `source.timing_reference`, `source.sample_count`)

**Zone 2 — Timing:**  
Trigger time · Imported time  
(+ optional `wwTimeReferenceControl()` when `time_basis === "unknown"`)

**Zone 3 — Files:**  
CFG filename · DAT filename  
(`source.original_filenames`)

### 2.3 Data source

All content comes from the already-fetched `GET .../sources` list response
(`SourceSummaryOut`). Zero additional backend calls are made when the row
expands. The `SourceSummaryOut` schema
(`backend/app/schemas/source.py:182`) carries all displayed fields:
`station_name`, `recorder_name`, `nominal_frequency`, `timing_reference`,
`sample_count`, `analog_channel_count`, `digital_channel_count`,
`timing_reference`, `start_time`, `trigger_time`, `original_filenames`, etc.

### 2.4 Availability guard

**`[FACT]`** The Details toggle and its `<tr>` row are rendered only for
`recordingKind === "comtrade"` sources. CSV/Excel preparation sources have no
Details row at all (`frontend/index.html:22634`, `22656`).

---

## 3. Measurement Groups UI — factual inventory

### 3.1 Current location

**`[FACT]`** Measurement Groups configuration is currently a **modal overlay**
(`#measurementGroupsOverlay` at `frontend/index.html:15036`), opened
exclusively from the **Per-Unit Settings** modal via `wwOpenPerUnitSettingsModal()`
(`frontend/index.html:35024`). There is no entry point from the Recording
Details row.

### 3.2 Key functions

| Function | Location | Description |
|---|---|---|
| `wwFetchMeasurementGroupsForSource(sourceId)` | `~35806` | `GET .../sources/{id}/measurement-groups` → caches into `ww.measurementGroups` |
| `wwMgGroupsForSelectedSource()` | `~35823` | Returns cached groups for `wwMgSelectedSourceId` |
| `wwRenderMeasurementGroupRow(group)` | `~35887` | Renders one group row (name, status badge, PU badge, channels text, base summary) |
| `wwMgBaseSummaryHtml(group)` | `~35863` | Reads `group.voltage_config.nominal_voltage_ll_kv`, `cfg.effective_reference`, `cfg.reference_mode` |
| `wwMgStatusBadge(groupStatus)` | `~35845` | "Suggested" / "Confirmed" / "Needs Review" / "Manual" |
| `wwMgPuBadge(puStatus)` | `~35854` | "Ready" / "N/A" / "Base Required" |
| `wwOpenMgDrawer(groupId)` | `~36306` | Opens the group edit drawer |
| `wwOpenPerUnitSettingsModal()` | `~35024` | Opens Per-Unit Settings modal (parent of Measurement Groups) |

### 3.3 Global state

```
wwMgSourcesList       — sources list for the source-selector dropdown
wwMgSelectedSourceId  — currently selected source in the groups overlay
wwMgEditState         — the currently open group edit state
ww.measurementGroups  — Map<sourceId, groups[]> (fetch cache, lives in `ww`)
```

### 3.4 Auto-import PU check (post-upload hook)

After every upload, `wwCheckAndApplyAutoImportPuMode()` (`~17012`) calls
`wwFetchSourceMeasurementGroupsSummary()` which fetches measurement groups for
the new source and checks `pu_status === "configured"` on voltage groups. This
triggers a compact status banner (linking to Per-Unit Settings) and optionally
auto-switches to `per_unit` mode on first import. This is the **only** upload
integration point that touches groups.

---

## 4. Backend API surface — complete mapping

All measurement-group endpoints share the prefix:  
`/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups`  
(router file: `backend/app/api/v1/measurement_groups.py`)

| Method | Path | Returns |
|---|---|---|
| `GET` | `` (list) | `list[MeasurementGroupOut]` |
| `POST` | `` (create) | `MeasurementGroupOut` (201) |
| `POST` | `/suggest` | `list[MeasurementGroupOut]` |
| `GET` | `/{group_id}` | `MeasurementGroupOut` |
| `PUT` | `/{group_id}` | `MeasurementGroupOut` (update name/status/channels) |
| `DELETE` | `/{group_id}` | 204 |
| `PUT` | `/{group_id}/voltage-config` | `MeasurementGroupOut` |
| `PUT` | `/{group_id}/current-config` | `MeasurementGroupOut` |

**Sources list:**  
`GET /api/v1/workspaces/{workspace_id}/sources` → `list[SourceSummaryOut]`  
(called via `fetchSourcesList()` at `~17151`)

**Per-unit resolution (per channel):**  
`GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/per-unit-resolution?channel_name={name}`  
(called via `wwFetchChannelPerUnitResolution()` at `frontend/index.html:32816`)

**Per-unit coverage (by source):**  
`GET /api/v1/workspaces/{workspace_id}/per-unit/sources/{source_id}/coverage`  
(called via `wwFetchPerUnitCoverage()` at `~35060`)

**`MeasurementGroupOut` / `VoltageGroupConfigOut` fields of interest:**

```
group.id
group.display_name
group.kind                     — "voltage" | "current"
group.status                   — "suggested" | "confirmed" | "needs_review" | "manual"
group.pu_status                — "configured" | "not_applicable" | "base_required"
group.channel_refs             — list[{source_id, channel_name}]
group.voltage_config
  .nominal_voltage_ll_kv
  .reference_mode              — "auto" | "manual"
  .effective_reference         — "line_to_line" | "line_to_ground"
  .base_authority              — "auto_resolved" | "manual" | "legacy_manual" | "needs_review" | "unavailable"
  .manual_conflict_detected    — bool (new in RD-0B commit 5e9113f)
  .manual_conflict_detail      — str | None (new in RD-0B commit 5e9113f)
group.current_config
  .method                      — "none" | "manual" | "equipment_rating"
  .manual_ibase_ka
  .resolved_ibase_ka
  .linked_voltage_group_id
  .equipment_rating_mva
```

---

## 5. PU display dependency map

### 5.1 Resolution storage

PU resolutions are stored per-channel in:
```
wwErState.perUnit.resolutions[key]
```
where `key = "src|{sourceId}|{channelName}"` (or `"calc|{sourceId}"`).

### 5.2 Fetch and cache

`wwFetchChannelPerUnitResolution(sourceId, channelName)` at
`frontend/index.html:32816` fetches `GET .../per-unit-resolution?channel_name=...`
and returns the resolution object immediately. Resolutions are cached in
`wwErState.perUnit.resolutions`.

### 5.3 Invalidation trigger

`wwErEnsurePerUnitResolutions()` (`~18735`) re-fetches resolutions when
`pu.requested[key] !== generation`. The `generation` counter increments only
in specific scenarios (source change, timing change, etc.). **There is no
invalidation path triggered by a voltage-base change via the Measurement
Groups editor.** This is documented as an existing architectural pattern —
the stale resolution persists until the next natural re-fetch.

### 5.4 Render cascade

When a resolution changes:  
`wwErSchedulePerUnitRender()` → `wwErRenderPlot()` + `wwErSyncPerUnitTreeDom()` +
`wwErRefreshAnnotationValues()` + `wwErRenderAnnotations()` + `wwErRenderAnnotationList()`

### 5.5 PU display for Event Reconstruction

`wwErChannelUnitDisplay()` (`~18695`) reads `resolution.status`:
- `"configured"` → plotted in PU
- `"not_applicable"` → unchanged engineering values
- `"base_required"` / other → state `"unavailable"`, not plotted

**Current (DEC-212) behaviour:** Raw source Current channels always stay in
engineering mode; only Voltage (and Calculated) channels follow the unit mode
toggle.

---

## 6. Upload workflow integration point

**`[FACT]`** The upload flow at `frontend/index.html:16852` posts
`FormData` to `POST .../sources`, then calls `refreshAllSourceViews()` to
update the recordings table. No auto-navigation to Recording Details occurs
after upload.

After upload, `wwCheckAndApplyAutoImportPuMode()` (`~17012`):
1. Fetches groups for the new source
2. Counts `pu_status === "configured"` voltage groups
3. Shows a compact banner in Recordings area
4. The banner link calls `wwOpenPerUnitSettingsModal()` → NOT the Recording
   Details row

**Implication for RD-1:** The post-upload flow already has a natural hook
point. After upload, instead of (or in addition to) the existing banner, RD-1
could auto-expand the new source's Recording Details row (or navigate to the
three-panel workspace if that becomes a separate page). No backend changes are
needed for this hook — it is a frontend-only improvement.

---

## 7. Navigation from Waveform → Recording Details

**`[FACT]`** There is no existing navigation path from the Waveform page
directly to a specific source's Recording Details row.

The only Waveform→Recordings navigation is via the main nav:  
`document.getElementById("mainNavRecordingsBtn")` → `shellSetCurrentPage("recordings")`
(line 59993), which shows the Recordings page but does not expand any
particular source's details.

The reverse direction (`Recordings → Waveform`) is `openRecordingForAnalysis(sourceId)`
(`~22796`): `shellSetCurrentPage("waveform")` then `selectSource(sourceId)`.

**Implication for RD-1:** A "Configure" link from the Waveform page to the
source's Recording Details is achievable by calling `shellSetCurrentPage("recordings")`
then `toggleRecordingDetails(sourceId)` — no routing change needed. If the
three-panel layout is a separate page, a small page-state extension would be
needed.

---

## 8. Confirmed gap: `manual_conflict_detected` not consumed by frontend

**`[FACT]`** The fields `manual_conflict_detected` and `manual_conflict_detail`
were added to `VoltageGroupConfigOut` by RD-0B commit `5e9113f`.

A code search across the entire `frontend/index.html` finds **zero references**
to either field. `wwMgBaseSummaryHtml()` (`~35863`) reads
`group.voltage_config.nominal_voltage_ll_kv`, `cfg.effective_reference` and
`cfg.reference_mode`, but does not read `manual_conflict_detected`.

**Impact:** When a voltage base is manually configured to a value that conflicts
with detected channel evidence (e.g., 66 kV set when channels indicate 275 kV),
the backend correctly sets `manual_conflict_detected = True` and blocks PU
resolution. However, the frontend currently:
- Shows "Base Required" via the existing `pu_status` badge (this is correct)
- Does **not** show any explanation of *why* it is blocked
- Does **not** show the `manual_conflict_detail` text
- Does **not** distinguish "conflict" from "base not yet entered"

This is the highest-priority RD-1 gap for safety visibility.

---

## 9. Gap analysis — prototype vs. current implementation

| Feature | Current state | Target (prototype V2.9) |
|---|---|---|
| Recording metadata display | Expandable `<tr>` row (Zone 1/2/3) | Left panel of three-panel workspace |
| Measurement Groups list | Modal overlay (via Per-Unit Settings only) | Middle panel of three-panel workspace |
| Group edit / review | Drawer inside Measurement Groups modal | Right panel (inline editor) |
| `manual_conflict_detected` | Not surfaced | Conflict warning in group panel |
| Navigation from Upload | Banner → Per-Unit Settings | Banner → Recording Details? (or auto-expand) |
| Navigation from Waveform | None direct | "Configure" link (proposal) |
| Nominal frequency editing | No editing | RD-2 (not RD-1 scope) |
| Recording identity editing | No editing | RD-2 (not RD-1 scope) |
| CT/VT conversion controls | No controls | RD-3 (not RD-1 scope) |
| Available for COMTRADE only | Yes | Same guard applies in V2.9 |
| Phase convention display | In group editor | Inherited from measurement group (DEC-118) |

---

## 10. Engineering risks and open questions

### R1 — Layout model: inline expansion vs. separate page (DECISION NEEDED)

**`[OPEN]`** The prototype shows a three-panel workspace. Two layouts are
viable:

**Option A — Inline expansion (replace existing `<tr>` row):**
- Replace the current `<td colspan="8">` expandable row with a wider three-
  panel layout inside the same `<tr>` sibling row
- Pro: no new routing, no navigation disruption, works in current SPA model
- Con: horizontal space is table-constrained; on narrow viewports a three-panel
  layout inside a colspan cell can be cramped; recording table header columns
  still sit above the panel

**Option B — Separate workspace page/panel:**
- Add a new "recordingDetails" page alongside "waveform" and "recordings" in
  `shellSetCurrentPage()`
- Pro: unrestricted layout space, true three-panel workspace
- Con: adds navigation state, needs back-navigation, may confuse table context

**Decision mode: `[DECISION MODE: ANALYSIS]`** — the prototype was provided as
an HTML standalone. The choice depends on whether the three-panel layout must
be visually unencumbered. Option A is recommended if the table-row expansion
is wide enough; Option B if the owner UAT of the prototype requires the
unrestrained layout. This needs an explicit owner decision before Slice B.

### R2 — PU resolution cache invalidation after voltage-base edit

**`[OPEN]`** When an engineer edits a voltage base in Recording Details,
`wwErState.perUnit.resolutions` is not automatically invalidated. The Waveform
view will continue to show the old PU state until the next natural re-fetch
(e.g., channel re-select or page navigation).

This is an existing architectural pattern (backend is stateless per-request;
the frontend staleness is the same as it is for the existing Measurement Groups
modal). RD-1 must include a generation bump or explicit invalidation call when
a group's voltage config changes via the new editor.

**Mitigation:** `wwErState.perUnit.generation++` invalidates all cached
resolutions. This is a one-line change, already established by the existing
`ww.epoch` / `pu.generation` pattern.

### R3 — CSS conflict with existing `.recording-details-row` styles

**`[FACT]`** `.recording-details-row td` currently has:
```css
background: var(--surface-tint);
border-left: 3px solid var(--accent);
padding: 14px 16px 14px 18px;
```

The three-panel layout requires different padding and no accent-bar on the
three-panel container itself (the accent-bar belongs on the row-association
indicator, not the entire panel backdrop). The existing CSS must be extended
or scoped to avoid overriding the new panel interior.

**Risk:** Low — adding a new class (e.g., `.recording-details-row--workspace`)
alongside the existing one handles this cleanly.

### R4 — `manual_conflict_detected` display language

**`[OPEN]`** The `manual_conflict_detail` string is a backend-generated
diagnostic (e.g., `"Detected 275 kV (from channels), manual base is 66 kV —
conflict exceeds 5 % tolerance"`). This is engineering text, not end-user
copy. RD-1 should surface it verbatim in a compact warning band inside the
Group panel, alongside the "Base Required" PU badge, rather than rewriting it.

### R5 — Source selector in Recording Details

**`[OPEN]`** The current Measurement Groups modal has a source-selector
dropdown (`#measurementGroupsSourceSelect`). In the three-panel Recording
Details workspace, the source is already fixed (the row that was expanded).
The source-selector is therefore **not needed** in the new panel — the groups
shown are always those belonging to the recording whose row was opened.

**Risk:** Medium — existing `wwMgSelectedSourceId` logic assumes a user-
controlled source selector. When reusing `wwFetchMeasurementGroupsForSource()`
from the Recording Details panel, the source ID comes from the row, not from
a dropdown. This needs care to avoid modifying `wwMgSelectedSourceId` while
the Measurement Groups modal is open in another context.

### R6 — Reuse of existing group editor vs. new editor

**`[OPEN]`** The existing group editor drawer (`wwOpenMgDrawer()` at ~36306)
was built for the Measurement Groups modal. It uses `wwMgEditState` and
`wwMgSelectedSourceId` globals. If Recording Details reuses this drawer, the
same global state is shared with the modal — opening the drawer from Recording
Details while the modal is open would corrupt state.

**Recommended approach:** Recording Details gets its own scoped state object
(e.g., `wwRdEditState`, `wwRdSourceId`) mirroring the existing shape but
isolated from the modal's globals. The editor drawer HTML markup can be shared
(a single `#wwMgDrawerOverlay` or a new `#wwRdDrawerOverlay`), but it is
driven by whichever state is currently active.

### R7 — Suggest Groups entry point

**`[FACT]`** The "Suggest Groups…" button in the existing modal calls
`POST .../suggest`. The three-panel workspace should expose the same action
in the groups panel header. No backend changes needed.

---

## 11. Proposed implementation plan — Slices B through E

### Slice B — Recording browser + three-panel layout skeleton

**Scope:**
1. Replace the existing `renderRecordingDetails()` output with a three-panel
   workspace container inside the existing `<tr>` sibling row (Option A).
2. Left panel: render the same Technical / Timing / Files content as today,
   using the existing HTML structure and CSS classes.
3. Middle panel: render the groups list for this source (reuse
   `wwFetchMeasurementGroupsForSource()`, `wwRenderMeasurementGroupRow()`).
4. Right panel: empty placeholder — "Select a group to edit."
5. Add CSS tokens for the three-panel layout grid (12-column or three `flex`
   columns with min/max widths).
6. No new backend calls — all data comes from already-fetched sources list
   plus the existing groups fetch.

**Acceptance:**  
- Details row still toggles correctly (expand/collapse).
- Three panels are visible side-by-side on a 1200px+ viewport.
- Existing Recordings table tests continue to pass.
- No changes to any other page (Waveform, Per-Unit Settings).

### Slice C — Group details (read-only panel)

**Scope:**
1. Clicking a group row in the middle panel opens group details in the right
   panel (read-only).
2. Show: group name, status badge, PU badge, channel list, base summary.
3. Show `manual_conflict_detected` warning band when `true`, including
   `manual_conflict_detail` text. This closes the confirmed RD-0B frontend gap.
4. No editing yet.

**Acceptance:**  
- Conflict warning appears when backend returns `manual_conflict_detected=true`.
- Right panel renders correctly for both voltage and current groups.

### Slice D — Editing integration

**Scope:**
1. "Edit" / "Review / Edit" button in the right panel opens the group edit
   form (reuse existing editor markup but driven by scoped `wwRdEditState`).
2. Save → `PUT .../voltage-config` or `PUT .../current-config` → reload group
   in right panel + refresh middle-panel row.
3. On successful save: bump `wwErState.perUnit.generation` to invalidate the
   PU resolution cache (R2 fix).
4. Suggest Groups button in middle panel header.

**Acceptance:**  
- Editing a voltage base updates the right panel immediately.
- Opening the existing Measurement Groups modal still works independently.
- After editing, `wwErState.perUnit.generation` is incremented.

### Slice E — Dependency safety + regression

**Scope:**
1. Playwright browser test for the three-panel layout (open details row →
   panels render → edit group → conflict warning appears/disappears).
2. Verify that `wwErState.perUnit.generation` invalidation correctly triggers
   PU re-fetch in the Event Reconstruction view after a base edit.
3. Verify that the Measurement Groups modal continues to work independently.

---

## 12. Summary of decisions needed before Slice B

| ID | Question | Mode | Recommendation |
|---|---|---|---|
| **D1** | Inline expansion (Option A) vs. separate page (Option B)? | `ANALYSIS` | Option A — inline, same `<tr>` row |
| **D2** | Reuse existing group-editor globals or introduce scoped `wwRdEditState`? | `ANALYSIS` | Scoped state — avoids conflict with modal |
| **D3** | "Configure" link from Waveform → Recording Details? | `DEFER` | RD-2 scope; not needed for RD-1 |
| **D4** | Auto-expand Recording Details row after upload? | `DEFER` | Nice-to-have; can be added in Slice B if trivial |

---

*This audit is read-only. No production files were modified. Awaiting owner
approval before Slice B implementation begins.*
