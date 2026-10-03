# Event Reconstruction — Slice 3 renderer design spike

Status: **Option B approved by the owner (DEC-127, 2026-10-01).**

The owner also resolved the §12 open items:
- Event Reconstruction is **analog-only** (native and calculated
  analog). This supersedes the digital parts of §5, §7, §8 and §11 —
  there is no digital region, digital figure builder use or digital
  sub-slice for Event Reconstruction.
- One panel per selected analog channel for the first plotted UAT.
- Engineering units only.
- Provisional Fit All and a relative X axis.

Mixed-duration navigation stays `[OPEN / UAT]`. The rest of this
document is the original spike text.

**Record model (DEC-128, 2026-10-02) — supersedes every "member = Time
Group" assumption below.**
- Waveform continues to use its existing Time Group model. Event
  Reconstruction uses independent imported event/record identities as
  its atomic members. Timestamp overlap alone never merges Event
  Reconstruction members.
- A member is one imported record (`record_id` = its `source_id`), not a
  Waveform Time Group. Where this spike says "several Time Groups",
  "member(s)" or "group", read "records".
- §6's within-group term (`effective_alignment_offset_s`, which includes
  Synchronise Sources) no longer applies. Event Reconstruction does not
  apply Waveform Synchronise Sources corrections; its own per-record
  correction is the cross-record layer.

**Implementation progress.**
- **Slice 3A (done):** the helpers in §5, items 1, 4, 5 and 6 are
  extracted — the native-range fetch core
  `wwFetchWaveformRange(request)` with the offset helpers
  `wwViewportTimeToSourceElapsed`/`wwSourceElapsedToViewportTime`;
  `wwAnalogLineTrace`/`wwAnalogPanelLayout`/`wwPanelMarkupHtml`;
  `wwStepZoomXRange` and the bounds clamps; the cursor pixel↔time
  helpers. Items 2 and 3 (digital) were dropped because Event
  Reconstruction is analog-only. See DEC-127's Slice 3A update for the
  full table.
- **Slice 3B (done):** §6 is implemented, on the record model since
  DEC-128. Each member's `source_timings` carries
  `within_record_offset_s` (0 for every current, single-source record),
  `reconstruction_record_offset_s`, `total_reconstruction_offset_s` and
  `reconstruction_start_s`/`_end_s` (null for stale state). The frontend applies the total through
  `wwErSourceElapsedToReconstructionTime`/
  `wwErReconstructionTimeToSourceElapsed` and resolves a channel's
  timing with `wwErSourceTiming()`. The §6 precision risk is now
  quantified by a fixture test (a float32 step is about 0.49 ms at
  +2 h); it is to be verified in the Slice 3C UAT, with the
  local-plotting-origin mitigation if needed.
- **Slice 3C (done, UAT 1, 2026-10-02):** the first plotted
  reconstruction. Full detail is in DEC-127's Slice 3C update.
  - Scope: one panel per selected analog channel in the browser's
    order, engineering units, a relative X axis, and Fit All as the
    initial view.
  - Box Zoom/Pan are Event Reconstruction's own drag mode; every panel
    follows the one viewport; Pan is clamped to Fit All; a double-click
    returns to Fit All.
  - Fetch: the hybrid visible-range fetch (§7) with the shared point
    budget and envelope.
  - **Coordinate translation** (r = reconstruction seconds, O = the
    canvas's one plotting origin):

    | Value | Coordinate |
    |---|---|
    | viewport, Fit All, pan bounds | r |
    | trace x / `xaxis.range` / `tickvals` handed to Plotly | r − O |
    | displayed tick labels (`ticktext`) and hover (`customdata`) | r |
    | relayout event range from Plotly | x → r = x + O |
    | source fetch range | native = r − `total_reconstruction_offset_s` (open bound at the source's own edge) |
    | returned samples | r = native + `total_reconstruction_offset_s` |

    O is kept while the window stays within 100 spans of it, and is
    otherwise moved to the window start; every trace is remapped at once.
  - **Precision result.** Plotly 3.7's scattergl kept 0.2 ms spacing at
    +7,200 s, +30 days and +10 years (regl-line2d hi/lo split); only its
    auto tick labels degraded. The local origin and Event
    Reconstruction's own ticks remove the dependency on either.
  - Still `[OPEN / UAT]`: mixed-duration navigation (§10). Not built:
    staged zoom, Reset, Autoscale Y (3D); cursors (3F); the ruler;
    grouped/multi-axis panels (6A/6B).
- **Slice 3D (done, 2026-10-02, DEC-129):** navigation controls.
  - Box Zoom and Pan are X-only (`yaxis.fixedrange` on Event
    Reconstruction panels).
  - Zoom In/Out use the shared step (`wwStepZoomXRange`). Zoom Out and
    Pan are both bounded by Fit All (the span-preserving clamp), and
    Zoom Out is disabled at Fit All.
  - Reset Time View = Fit All + autoscale Y on every panel; a
    double-click uses the same function.
  - Autoscale Y covers every panel. Y keeps its range through X
    navigation; an empty panel is left in autorange.
  - **Viewport rebasing:** a zoomed window moves by the change of the
    reconstruction zero, `F_new − F_old` = (old offset of the new
    reference) + (its correction change), so the same physical segment
    stays in view. It is then intersected with the new Fit All.
  - **Fit All span notice:** shown when the widest empty stretch between
    plotted records is ≥ the backend large-gap threshold and ≥ 90 % of
    Fit All. It names the outlying record or group and is advisory only.
  - Every action works in reconstruction time; the plotting origin is
    untouched as a concept.
  - Still `[OPEN / UAT]`: mixed-duration navigation. Next: cursors
    (3E/3F).
- **Slice 3E (done, 2026-10-02, DEC-130):** global A/B cursors (§5,
  item 6; the planned 3F scope delivered as 3E).
  - **State:** `plot.cursors` holds reconstruction seconds. Each panel
    draws the same time in its own overlay, so the lines scroll with
    their panel.
  - **Geometry:** `wwTimeToPageX`/`wwPageXToTime` with the
    reconstruction viewport. The fraction is origin-invariant, so the
    plotting origin never touches cursor state.
  - **Values:** the existing nearest-sample endpoints at native time
    `cursor − total_reconstruction_offset_s` (§7's cursor line, as
    planned): per record for native channels, and per timing source for
    calculated ones. Outside a record's data the value is "No sample";
    there is no interpolation and no rate-based tolerance.
  - **Rebasing:** A and B follow the DEC-129 frame shift, keeping the
    same physical instant. A non-reference correction leaves them
    fixed.
- **Grouped Measurement View (done, 2026-10-02, DEC-131):** this
  replaces §8's provisional one panel per channel.
  - **Panel key:** the backend display axis (`display_axis_key` =
    engineering quantity + normalized unit, through the closed unit
    table; blank unit = own panel).
  - **Panel contents:** traces from several records share a panel, each
    with its own fetch, envelope and timing. A panel is
    `{ key, axis, traces[] }`; a trace is the former per-channel state.
  - **Order:** panels follow `ANALOG_GROUP_ORDER` then first appearance;
    traces follow the browser order.
  - **Y:** Autoscale Y and Reset cover all of a panel's traces.
  - **Cursor values:** moved to the channel tree (Cur A / Cur B / Δ
    columns); the panels draw lines only.
  - **View mode:** `grouped` (default) or `combined` (below).
- **Combined Multi-Axis View (done, 2026-10-02, DEC-132):** one panel,
  one Plotly Y axis per display axis.
  - **One grouping:** `wwErViewPanels(groups, viewMode)` presents
    `wwErPlotGroups()` either as one panel per axis or as one panel with
    every axis. A panel is `{ key, combined, axes[], traces[] }`; an axis
    is `{ key, axis, traceKeys, placement, autoscaleYPending, range }`;
    a trace knows its `panel`, `axisIndex` and `yRef`.
  - **Placement:**
    - `y` on the left and `y2` on the right (overlaying);
    - `y3+` alternate sides with `anchor: "free"` and `autoshift`;
    - `automargin` sizes the margins.

    Nothing is hard-coded and there is no cap. Above 4 axes an advisory
    notice is shown.
  - **Y:** pending/frozen state per axis. An empty axis shows no tick
    values. Autoscale waits until every needed load has started.
  - **Mode switch:** presentation only. Traces move between panels with
    their data. A refetch happens only when the data no longer serves
    the new panel's point budget.
  - **Height:** 420 px combined, 180 px grouped; no resizing.
- **Fit Record (done, 2026-10-02, DEC-133):** the first mixed-duration
  navigation aid (§10).
  - `wwErState.activeRecordId` is an explicit record identity: the
    member header click, never the reference and never inferred from a
    trace.
  - The fit target is the backend member `start_s`/`end_s`. It is
    applied through `wwErClampViewport()` (minimum span only) and the one
    `wwErApplyViewport()` pipeline: origin relocation, per-trace
    visible-range fetch and data reuse, no record-wide data path.
  - X only, Grouped and Combined alike. There is no time compression and
    no axis break.
  - The overview navigator stays deferred until UAT.
- **Individual Y-axis drag zoom (done, 2026-10-02, DEC-134).**
  - Y axes are `fixedrange: false`, so Plotly wires its own per-axis
    `nsdrag` / `ndrag` / `sdrag` regions.
  - `wwErKeepPlotAreaDragXOnly()` marks them fixed for drags that start
    in the plot area, keeping Box Zoom and Pan X-only.
  - Per-axis relayout events (`yaxisN.range[...]` / `.autorange`) become
    manual or automatic axis state. ER's own Y relayouts are flagged.
  - State: `plot.axisStates[mode]` maps a display-axis key to the axis
    entry (manual ranges win over trace changes), pruned with the axes.
- **Relative / Absolute time display (done, 2026-10-02, DEC-135).**
  - The coordinate model is unchanged: Plotly x = r − origin.
  - Absolute labels come from `absolute(r) = reconstruction_zero_time_utc
    + r`. The zero is the backend's reference recorded start + reference
    correction. It is carried as an integer epoch second plus a float
    fraction; calendar fields come from DEC-122's display-timezone
    formatter (whole seconds only).
  - Absolute ticks are calendar-aligned (`wwErAbsoluteTimeAxisTicks`).
  - Hover uses the trace `text`, so `customdata` stays numeric.
  - The cursor readout carries µs.
  - A switch relabels without any fetch.
- **Annotations (done, 2026-10-02, DEC-136; parity 2026-10-03,
  DEC-137).**
  - Waveform's four types over backend-owned `definition.annotations`.
    Text Notes hold `reconstruction_time_s` (rebased by the backend frame
    shift); Callouts/Peaks hold a channel (and a Callout its source
    sample) and are placed at source time + the source's current offset.
  - One `#wwErAnnotationOverlay` + `#wwErCalloutConnectorLayer` inside
    `#wwErPanelsWrap` spans every panel (no per-panel clipping). X from
    Plotly's own axis metrics (`wwPlotMetricsForChart`,
    `wwTimeToPageX`); Y from the trace's own axis
    (`_fullLayout[axis.placement.layoutKey]`) or, for a Text Note, a
    fraction of its panel's plot height.
  - Every cursor redraw path (`wwErDrawPanelCursors`) schedules one
    overlay render (rAF); `wwErApplyViewport` and `wwErRender` trigger
    the live peak recalculation.
  - Each panel's `.ww-er-annotation-layer` is now only the Text Note
    placement capture strip.
- **Per-Unit Display (done, 2026-10-03, DEC-138).**
  - `wwErState.unitMode`; per-channel resolutions in `wwErState.perUnit`
    (backend GET …/per-unit-resolution, re-read per page entry).
  - `wwErPlotItems()` carries each item's unit display; only plottable
    items get traces, all items count for Fit All.
  - A trace's request `unitMode` is "per_unit" only when its resolution is
    configured; its data is cached per unit display (`unitKey`,
    `unitCache`) and the render key includes `unitKey`, so a changed base
    refetches and a switch never shows the other unit's values.
  - Y state lives in `plot.axisStates["<viewMode>|<unitMode>"]`
    (`wwErAxisStore()`).
- **Toolbar consistency (done, 2026-10-03, DEC-139, app-wide rule).**
  Every shared control already matched Waveform's icon/tooltip/class
  exactly (Box Zoom/Pan, Annotate/Annotations, Zoom In/Out, Reset Time
  View, Autoscale Y, A/B Time Cursors, all confirmed against the actual
  Waveform source, not assumed). The one gap -- no grouping separators --
  is fixed with two `.ww-toolbar-sep` (Waveform's own component): before
  the annotation tools in `#wwErToolbar`, and before Fit Record (the one
  page-specific tool) in `#wwErCanvasToolbar`.
- **Global icon system (done, 2026-10-03, DEC-140, app-wide -- not
  Event-Reconstruction-only).** Full record in
  [POWERWAVE_ICON_SYSTEM.md](POWERWAVE_ICON_SYSTEM.md). Every shared
  Waveform/Event Reconstruction icon now comes from one registry
  (`WW_TOOL_ICONS` + `data-ww-icon`/`wwApplyToolIcons()`) instead of
  duplicated inline SVG. Event Reconstruction's Time Display is now the
  full Elapsed/Relative/Absolute family (Elapsed disabled, with a
  tooltip explaining why); its Grouped/Combined are now icon buttons
  (Grouped reused verbatim from Waveform's own; Combined a new composite
  in the same family). No disabled Separate/Custom/Split stubs were
  added here -- Event Reconstruction never had those concepts.

Date: 2026-10-01. Code references are function names in
`frontend/index.html` and `backend/app/` at commit `33f3178`
(`feat/event-reconstruction`). Line numbers drift; the names do not.

Related: DEC-123 (shell), DEC-124 (domain/API and its coordinate-model
update), DEC-125 (selection workflow), DEC-126 (channel browser),
DEC-128 (record model).

## 1. Problem

Event Reconstruction (ER) must plot the selected channels of several
Time Groups on one common reconstruction timeline:
- independently of Waveform;
- reusing Waveform behaviour (pan, box zoom, step zoom, reset,
  cursors, legend, analog and digital plotting, envelope fetching);
- never changing Waveform visibility, Time Groups, Synchronise Sources,
  channel properties or viewport.

Fixed owner constraints for the first plotted slice:
- provisional **Fit All** initial view;
- **relative** reconstruction time on the X axis;
- physically continuous time (no axis break);
- digital channels in scope;
- selection stays session-only;
- mixed-duration navigation stays `[OPEN / UAT]`.

## 2. Current renderer anatomy (`[FACT]`, audited)

**Scale of the shared state.**
- 1,293 top-level functions in `index.html`; **225 reference `ww.`
  directly** (902 references, 53 distinct fields).
- A call-graph closure shows the core panel/canvas functions —
  `wwCreatePanelDom`, `wwInitPanelPlot`, `wwLoadChannelRange`,
  `wwWirePanelRelayout`, `wwApplyAndFetchGroupViewport`,
  `wwStepZoomX`, `wwResetOneTimeGroupView`, `wwRebuildDigitalChart`,
  `wwSyncTimeGroupRuler`, `wwCreateTimeGroupCanvasDom`, `wwRenderLegend`
  — each reach the same **~312-function web touching 44 of the 53 `ww`
  fields**. That includes annotations, t0, layout mode, custom groups,
  per-unit, Split view and playback.

| Area | Functions | Coupling found |
|---|---|---|
| Data fetch | `wwFetchChannelRange`, `wwLoadChannelRange`, `wwPointBudgetForPanel` | `wwFetchChannelRange` already does a **hybrid fetch**: workspace range → source-native via `wwWorkspaceTimeToSourceTime()`, the existing `/sources/{id}/waveform` or `/calculated-channels/{id}/waveform` with `point_budget`, then `time + offset`. Coupled only through `wwAlignmentOffsetForDisplaySourceId()` (`ww.alignmentOffsets`, `ww.calculatedChannels`) and `ww.unitMode`. Abort/sequence bookkeeping lives on the channel entry. `wwLoadChannelRange` writes into the panel and calls Waveform-specific `wwElapsedToPlotlyX()`/legend code. |
| Backend reduction | `waveform_service._clip_and_reduce`, `extract_waveform_range` | Clip to native `[start, end]`. Full resolution up to `FULL_RESOLUTION_DISPLAY_THRESHOLD = 10_000` samples, otherwise a min/max envelope at `min(point_budget, 10_000)`. Frontend budget = 4 points/px, clamped 4,000–20,000 (`WW_POINT_BUDGET_*`). |
| Panels | `wwCreatePanelDom`, `wwInitPanelPlot`, `wwBuildTrace`, `wwBuildLayout`, `wwRenderLegend` | Panels are plain objects (`chartEl`, `channels`, `groupKey`); DOM is class-based, no ids. **But** creation is bound to a Time Group canvas (`wwEnsureTimeGroupCanvasDom(groupId)` inside `#wwTimeGroupCanvases`). Traces/layout resolve the group via `wwTimeGroupIdForDisplaySourceId()`/`wwPanelTimeGroupId()` and read t0 event time, Absolute/Elapsed ticks (`wwTimeAxisTickFormat`, `ww.timeMode`), the group viewport and `ww.dragMode`. The generic part — scattergl line trace, theme colours, spikes, margins, `yaxis2` for angles — is small and pure. |
| Viewport | `ww.timeGroupViewports`, `ww.viewport` (primary mirror), `wwApplyAndFetchGroupViewport`, `wwRefetchChannelsForGroup` | One orchestration per Time Group: relayout panels → peak annotations → ruler → digital chart → slider → zoom controls → refetch → Split view. Every step is keyed by Time Group id and iterates `ww.panels`. |
| Relayout / drag | `wwWirePanelRelayout`, `wwSetDragMode` | Relayout maps Plotly X → elapsed through the group's t0 and debounces into the group viewport; autorange → reset. `wwSetDragMode` iterates `ww.panels` and the global `#dragModeZoomBtn`/`#dragModePanBtn`. |
| Toolbar | `wwWireTimeGroupToolbar(canvasEl, groupId)`, `wwStepZoomX/Y(groupId)`, `wwAutoscaleYForGroup`, `wwResetOneTimeGroupView` | Target resolved by `groupId`. The step math (±20%/±25%, midpoint fixed, min-span floors) is embedded in the functions. The split-menu dismissal queries `.ww-split-menu` document-wide. |
| Digital | `wwAddDigitalChannels`, `wwDigitalHighIntervals`, `wwRebuildDigitalChart(groupId)` | Transitions fetched **once, in full**, from `/sources/{id}/digital-waveform`. The offset is applied at render time in `wwDigitalHighIntervals()` (`wwAlignmentOffsetForSource`, a ~15-line pure algorithm otherwise). Drawn as `layout.shapes` in one shared Plotly chart per canvas (`.ww-tg-digital-chart`); readiness and click wiring are in `ww.*ByGroup` maps. |
| Cursors | `wwCursorPlotMetrics`, `wwCursorTimeToPixelX`, `wwCursorPixelXToTime`, `wwWireTimeGroupCursorOverlay`, `wwUpdateCursorOverlayForGroup`, `wwFetchCursorValuesForSource` | Pixel↔time is **pure arithmetic** given a visible range and a chart's `_fullLayout.xaxis._offset/_length`. Overlay wiring/state (`ww.timeGroupCursorState`) is per canvas and queries `#viewWaveform`. Values come from `/cursor-values` with the same native-time inverse mapping. |
| Axis ticks | `wwNiceTickStep`, `wwTickValuesForRange` | Pure. Labelling (`wwFormatWorkspaceClockTime`) is group/time-mode aware. |
| Presentation | `wwChannelDisplayName(Plotly/Html)`, `wwColorForChannel`, `analogChannelNameCellHtml`, grouping helpers | Already shared with ER (DEC-126). |
| Precedent | `wwAnalysisFetchChannelWaveform` (Analysis Related Waveforms) | A **second copy** of the fetch, written because `wwFetchChannelRange` is `ww`-coupled — exactly the drift risk of a separate renderer. |

**Test pinning.** 56 static frontend test files, plus 29 browser specs.
The candidate functions are each pinned by 1–8 static test files (e.g.
`wwRebuildDigitalChart` 8, `wwApplyAndFetchGroupViewport` 6,
`wwFetchChannelRange` 4).

## 3. Options

### Option A — multi-instance Waveform engine

Turn `ww` into an instance (Waveform, ER) and thread it through the
engine.
- **Scope:** about 225 direct users plus the ~312-function web, the
  per-group maps, the primary-group mirror and global DOM ids. Waveform
  concepts that ER does not have — Time Group canvases, t0, annotations,
  layout modes, custom groups, per-unit, Split view, playback — would
  either live as dead state in the ER instance or need guards.
- **Tests:** most of the 56 static files pin `ww.`-shaped code.
- **Verdict:** clean in the long run, but the highest regression risk
  and size, for features ER does not need. Not now.

### Option B — shared rendering primitives + separate ER adapter/state (recommended)

Extract only the pure, already-generic pieces into shared primitives.
Waveform keeps its engine and calls them through thin wrappers
(identical behaviour); ER gets its own state and orchestration.

### Option C — ER-specific renderer reusing only low-level utilities

Build ER's panels, viewport, digital chart and cursors from scratch on
Plotly. Waveform is untouched, but fetch, trace style, digital
intervals, step-zoom math and cursor math are copied. The Related
Waveforms copy shows how these drift.

### Option D — ER as a pseudo Time Group inside the existing engine (considered, rejected)

Proposed during the first audit: a reconstruction canvas keyed by a
synthetic group id, reusing every per-group path.
- `ww.displayed` is keyed by channel, so a channel could not be shown in
  Waveform and ER at once.
- ER panels would live in `ww.panels`, so Waveform layout mode,
  annotations, Split view, unit mode and resize sweeps would act on
  them.
- ER viewports would sit in `ww.timeGroupViewports`.

That breaks the owner's isolation requirement by construction.

## 4. Decision matrix (descriptive)

| Dimension | A — multi-instance | B — shared primitives + ER adapter | C — separate renderer |
|---|---|---|---|
| Waveform regression risk | High: rewires ~225+ functions and global state | Low: a few leaf functions become wrappers with identical output | None at first; rises later as fixes diverge |
| Code reuse | Maximal, including features ER does not need | Fetch, trace/layout base, panel DOM, digital intervals/figure, step-zoom/reset math, cursor math, ticks, theme, resolvers | Resolvers, grouping and endpoints only; the rest copied |
| State isolation | Good once finished; risky during the migration | Strong: ER state lives in `wwErState`, never `ww` | Strong |
| Common-timeline support | Must un-assume "one canvas per Time Group" across the engine | Natural: ER owns one canvas and its own mapping | Natural |
| Canonical time mapping | Needs a mapping switch inside Waveform's group functions | One ER helper; Waveform keeps its own | One ER helper |
| Analog + digital | Reused as is | Digital interval algorithm and figure builder shared; ER region separate | Re-implemented |
| Performance reuse | Full | Full: same endpoints, `point_budget`, envelope, abort/sequence pattern | Endpoints yes; fetch/abort logic copied |
| Future layouts (grouped, multi-axis, timeline strip, annotations, Fit Selected, auto-sync) | Inherits Waveform layout modes, with Time-Group assumptions | Open: ER owns its panel arrangement; Waveform layout modes are not imported | Open, but each feature built twice |
| Implementation size | Very large | Moderate | Moderate now, growing |
| Testing burden | Rewrite of most static tests | Small updates where helper bodies moved; Waveform browser suites unchanged | Small now; parallel tests later |
| Maintainability | Best eventually, if it lands | Good: one implementation per primitive; ER/Waveform differ only where behaviour truly differs | Weakest: two drifting renderers |

## 5. Recommendation `[PROPOSAL]`: Option B

**Shared primitives** (extracted from existing code; each Waveform
caller becomes a wrapper with byte-identical behaviour):
1. **Native-range fetch core:** `wwFetchWaveformRangeNative({displaySourceId, isCalculated, channelName, nativeStart, nativeEnd, pointBudget, unitMode, entry})`.
   Same URL/endpoint/`point_budget`/abort and sequence handling; returns
   native times. `wwFetchChannelRange` wraps it with the Waveform
   offset. Related Waveforms can later move onto it (not part of
   Slice 3).
2. **Digital intervals:** `wwDigitalHighIntervalsForOffset(entry, offsetSeconds)`,
   the pure algorithm. `wwDigitalHighIntervals(entry)` wraps it with
   `wwAlignmentOffsetForSource`.
3. **Digital figure builder:** lanes + intervals + x-range + colours →
   Plotly traces/layout/shapes, split out of `wwRebuildDigitalChart`.
   The Waveform wrapper keeps its per-group readiness and click wiring.
4. **Trace/layout base:** the scattergl line-trace style, the base panel
   layout (theme colours, margins, spikes, `yaxis2` for angles) and the
   panel DOM template. Waveform's `wwBuildTrace`/`wwBuildLayout` add
   their t0/time-mode/group concerns on top.
5. **Range math:** step zoom (factors, midpoint, min-span floors),
   clamp to bounds, and reset. Taken from `wwStepZoomX`/`Y` and the
   clamp helpers.
6. **Cursor math:** pixel↔time given `(range, metrics)` and
   `metrics(chartEl)` from `wwCursorPlotMetrics`/`wwCursorTimeToPixelX`/
   `wwCursorPixelXToTime`.
7. **Already shared:** `wwPointBudgetForPanel`, `wwNiceTickStep`/
   `wwTickValuesForRange`, `wwThemeColors`, presentation resolvers,
   grouping helpers.

**Stays separate.**
- Waveform's whole orchestration: Time Group canvases, per-group
  viewport pipeline, ruler, slider, annotations, t0, layout modes,
  per-unit, Split view, playback, `ww.*`.
- ER's own:
  - `wwErState` (panels, viewport, drag mode, cursor state, digital
    entries, selection);
  - the `#wwErCanvas` DOM and toolbar wiring;
  - the viewport pipeline (apply → relayout ER panels → refetch ER
    channels → rebuild ER digital → cursors);
  - the time mapping (§6).

**Minimal Waveform refactor:** steps 1–6, each a pure extraction with
the original function kept as a wrapper. Static tests that pin moved
bodies are updated; Waveform browser suites must pass unchanged.

**Why not the others now.**
- A: highest risk, largest size, and imports features ER does not need.
- C: duplicates fetch/abort/digital/zoom/cursor logic that the Related
  Waveforms copy shows will drift.
- D: breaks isolation by construction.

## 6. Canonical time mapping `[PROPOSAL]`

> **As implemented (Slice 3B on the DEC-128 record model).**
>
> ```text
> reconstruction_x = source_elapsed_s + total_reconstruction_offset_s
> total_reconstruction_offset_s = within_record_offset_s              # 0 for every current record
>                               + reconstruction_record_offset_s      # placement(r, ref) + c_r - c_ref
> ```
>
> The proposal below composed a within-Time-Group term including
> Synchronise Sources. That term is superseded: records are independent,
> and Synchronise Sources is never applied. The helper names also
> differ: `wwErSourceTiming()` returns `{ recordId, timingSourceId,
> totalOffsetS, startS, endS }`.

Builds on the DEC-124 coordinate model. Absolute time enters exactly
once: in the backend, as the origin difference.

```text
reconstruction_x = source_elapsed_s + total_offset_s(timing_source)

total_offset_s(s) = effective_alignment_offset_s(s)              # existing, within-group, read only
                  + reconstruction_offset_s(member(s), reference) # DEC-124: placement + c_g - c_ref
```

**Where the offsets are composed — backend.** Each member in
`GET .../definition` gains a per-source list:
`sources: [{source_id, effective_alignment_offset_s, total_offset_s, start_s, end_s}]`.
`start_s`/`end_s` are that source's extent in reconstruction time. The
service already computes both terms (`list_source_alignments()` +
`reconstruction_offset_s`), so the composition gets one tested
implementation, extending `TestCoordinateModel`. This is the only API
change and is additive; it lands in the slice that needs it, not in
this spike.

**Where it is applied — one frontend pure helper:**

```text
wwErSourcePlacement(displaySourceId)
    -> { memberId, timingSourceId, totalOffsetS, startS, endS } | null
wwErElapsedToReconstruction(displaySourceId, elapsed | elapsed[])  -> number | number[] | null
wwErReconstructionToElapsed(displaySourceId, reconstructionSeconds) -> number | null
```

- **Timing parent:** for a calculated channel it is
  `reference_source_id` from ER's own `GET .../calculated-channels`
  list. This is the same rule as `wwTimingSourceIdForDisplaySourceId()`,
  without reading `ww`. Native channels map to their own source.
- **Stale members** have no placement, so the helper returns `null` and
  the channel is not plotted. `wwErSelectedChannelsForPlotting()`
  already excludes them.
- **Precision:** float64 seconds end to end. Offsets come from exact
  `datetime` differences, with no rounding to ms. Values are
  reference-relative, so typical magnitudes are small. **Risk to
  verify:** Plotly `scattergl` stores positions at reduced precision;
  a member hours from the reference at 5 kHz resolution needs about 8
  significant digits. Check this in the first plotted slice with a
  +2 h member. Mitigations if needed: a viewport-local X origin, or the
  SVG `scatter` trace type for small point counts.
- **Before vs after fetch:** the inverse maps the viewport to native
  range **before** the fetch; the forward maps returned times
  **after**. That matches today's Waveform boundary (DEC-053/042).

## 7. Data-fetch strategy `[PROPOSAL]`: Strategy 3 (hybrid)

| Strategy | Assessment |
|---|---|
| 1. Fetch whole source, map in frontend | Simple, but loses visible-range clipping and the envelope: long or high-rate records download everything. Rejected. |
| 2. Reconstruction-aware backend range endpoints | Duplicates the waveform/calculated/digital/cursor endpoints and mixes analysis state into data APIs. Rejected. |
| **3. Hybrid** | Viewport → native per source (inverse helper) → existing `/waveform` with `point_budget` → returned native times + `total_offset_s`. Identical to `wwFetchChannelRange` today; no data-API change. **Recommended.** |

**Details.**
- Skip the request when a source's `[start_s, end_s]` does not
  intersect the viewport.
- Per-channel abort/sequence handling comes from the shared fetch core.
- Unit mode is fixed to `engineering` for Slice 3, like Related
  Waveforms. ER per-unit is `[OPEN]`.
- Digital: fetch transitions once per source and map at render, so a
  correction or reference change needs no refetch.
- Cursor values: `/cursor-values` with native time =
  `reconstruction_x − total_offset_s`.

## 8. Analog and digital on the shared timeline

- **Analog:** ER panels share one X range, the reconstruction viewport.
  The provisional panel arrangement is **`[OPEN]`**. My recommendation
  for the first UAT is one panel per selected analog channel
  (Separate-style), so no axis mixes units; measurement-grouped panels
  remain Slice 6A and the combined multi-axis view Slice 6B.
- **Digital:** one ER digital region below the analog panels, the same
  lane/shape figure as Waveform (via the shared figure builder), sharing
  the X range.
- **Calculated:** plotted like analog, mapped through their timing
  parent.

## 9. Performance

- **Same envelope contract.** Each channel requests only its visible
  native slice with a pixel-based budget (4/px, 4k–20k). The backend
  returns full resolution up to 10k samples, otherwise a min/max
  envelope.
- **Mixed durations under Fit All.** A 5 kHz / 200 ms record (1,000
  samples) and a 1 s / 10 min record (600 samples) are full resolution.
  A 20 Hz / 30 s record is 600 samples. Long high-rate records get an
  envelope. Narrow records simply occupy few pixels; nothing is
  resampled.
- **Many channels:** requests are parallel per channel with abort
  handling, as in Waveform. Non-intersecting sources skip their fetch.
- **Digital:** transitions only, fetched once.

## 10. Provisional Fit All (first UAT)

- The X range is `[min start_s, max end_s]` over the sources owning
  currently plotted channels, using the backend per-source extents from
  §6.
- Stale members are excluded.
- If nothing is plotted yet, use the current members' `start_s`/
  `end_s`.
- No padding and no sampling-rate-based expansion.
- A zero span gets the existing minimum-span floor.
- Reset Time View = Fit All.
- This is provisional. Fit Selected Record is now built (DEC-133);
  overview navigation and automatic focus stay `[OPEN / UAT]`.

**As built (Slice 3C).**
- Fit All uses the plotted channels' sources only. With nothing plotted
  there is no viewport (the empty state shows instead), rather than the
  members' extents.
- Selection changes follow Fit All while the view is at Fit All, and
  keep a manual window otherwise (intersected with the new Fit All).
- Double-click and the Reset Time View button share one path (Slice 3D):
  Fit All, then Y autoscaled on every panel.
- Zoom Out and Pan share Fit All as their bounds (Slice 3D).
- **First UAT observations** (owner YGPN 275 kV records, local run):
  - The same-day records (BAHS 5 kHz / 7.5 s, BTGH 20 Hz / 70 s, PMJY
    20 Hz / 51 s, PMJY about 467 s later) read well under Fit All. The
    5 kHz record arrives as an envelope and resolves to full samples
    when zoomed.
  - One record from a different event (dated 87 days later) turns Fit
    All into an 87-day span where every trace is sub-pixel. The
    large-gap warning is the only cue.
  - Both observations are inputs to the open mixed-duration navigation
    question.

## 11. Proposed Slice 3 sub-slices

| Slice | Content | UAT checkpoint |
|---|---|---|
| **3A** | Shared primitive extraction (§5, steps 1–6). Waveform wrappers, identical behaviour; full Waveform suites unchanged. No ER plotting. | Regression only |
| **3B** | Backend per-source placements (§6) + ER mapping helper + tests (coordinate model extended). No plotting. | — |
| **3C** | ER canvas foundation + analog/calculated plotting + Fit All initial view + Box Zoom/Pan via Plotly drag mode + relayout → refetch. Verify the `scattergl` precision risk. | **UAT 1:** mixed records on one timeline |
| **3D** | Zoom In/Out, Reset (= Fit All), Autoscale Y — toolbar enabled. | Folded into UAT 1 or 2 |
| **3E** | Digital region on the shared timeline. | **UAT 2** |
| **3F** | Cursors A/B and values (reconstruction-time readout). | **UAT 3** |

## 12. `[OPEN]` items for the owner

1. **Approve Option B** (or choose another).
2. **Provisional panel arrangement** for UAT 1 (recommended: one panel
   per selected analog channel).
3. **ER unit mode** for Slice 3 (recommended: engineering units only).
4. **The additive backend field** in §6 (recommended: yes, in Slice 3B).
5. Unchanged: mixed-duration navigation, the initial-view strategy
   beyond provisional Fit All, the final manual sync UX (Slice 4),
   grouped/multi-axis display (6A/6B), and selection persistence.
