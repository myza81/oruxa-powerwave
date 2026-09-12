# Analysis Workspace — shared infrastructure

**Status: three shared primitives implemented** — Engineering Context
lifecycle, shared Playback, and shared Related Waveforms. This document
records the architecture common to every Analysis-menu analyzer
(Phasor, Overcurrent, and every future one — Impedance Locus,
Differential, Sequence Components, Directional) so a new analyzer never
needs to re-derive or re-implement any of it. Analyzer-specific
engineering behaviour (role resolution, estimator/characteristic math,
alert semantics) stays documented in each analyzer's own
[PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)/[OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md)
— this document is scoped to the shell/lifecycle infrastructure those
two documents both consume.

## The shape

```text
Analysis
├── Shared Engineering Context lifecycle  (DEC-089 Update, 2026-09-12)
├── Shared Playback                        (DEC-085)
├── Shared Related Waveforms               (DEC-089 Update, 2026-09-12)
└── Analyzer-specific visualization
    ├── Phasor
    ├── Overcurrent
    ├── future Impedance Locus
    ├── future Differential
    └── other analyzers
```

Every shared primitive follows the SAME architectural invariant:

> **The analyzer decides WHAT is relevant to it; the shared Analysis
> workspace decides HOW that is fetched/discovered/rendered and kept in
> sync.**

Concretely:

| Primitive | Analyzer declares | Shared workspace owns |
|---|---|---|
| Engineering Context lifecycle | nothing (pure consumer) | discovery/bootstrap/suggestion, the one published context list |
| Playback | which Time Group it resolved (`activeTimeGroupId`) | the one clock, tick distribution, Play/Pause/Seek/Restart/Speed |
| Related Waveforms | its own currently-active roles (`{roleKey, engineeringType, phase, channelRef, unit, label}`) | fetching, grouping, Plotly rendering, the cursor, the empty state, caching, resize |

## Shared Engineering Context lifecycle

Owned by `wwAnalysisLoadContexts()`/`wwAnalysisDiscoverUncoveredSources()`
and friends (`frontend/index.html`, the module immediately before the
Overcurrent section). `wwRenderAnalysisPage()` calls
`wwAnalysisLoadContexts()` exactly once per Analysis-page visit,
regardless of which analyzer tab is active. Analyzers register as
consumers via `wwAnalysisRegisterContextConsumer({ onContexts,
onLifecyclePhase, onDiscovering, onFreshContextsDiscovered })`.

Full detail, root cause, and migration history:
[PHASOR_ANALYSIS.md — "Ownership moved to the shared Analysis
workspace"](PHASOR_ANALYSIS.md#ownership-moved-to-the-shared-analysis-workspace-2026-09-12-owner-uat-fix)
and
[OVERCURRENT_ANALYSIS.md — "Shared Analysis Engineering Context
lifecycle"](OVERCURRENT_ANALYSIS.md#shared-analysis-engineering-context-lifecycle--uat-fix-2026-09-12).

## Shared Playback

The ONE authoritative frontend-only clock (`wwPlayback`), owning
workspace time for at most one active Time Group at a time — see
[DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock).
Public surface every consumer uses: `wwPlaybackState()` (read the live
object), `wwPlaybackOnTick(callback)` (subscribe), `wwPlayback.
currentTime`/`activeTimeGroupId`, `wwPlaybackPlay/Pause/Restart/
SetSpeed/HandleSeek*()`. `wwDeriveTimeGroupBounds(groupId)` reads a
Time Group's own full extent (workspace time) independently of whether
Playback has ever been started on it. Phasor, Overcurrent, and Related
Waveforms are three independent consumers of this ONE controller — no
analyzer or shared primitive may build a second clock/timer/RAF loop.

## Shared Related Waveforms

A compact, context-aware, analyzer-aware waveform preview living
directly below Playback in each analyzer's own panel — one shared DOM
instance (`#wwAnalysisRelatedWaveformsPanel`), reparented (never
cloned) between `#wwPhasorRelatedWaveformsAnchor`/
`#wwOvercurrentRelatedWaveformsAnchor` as the active analyzer changes
(`wwAnalysisMountRelatedWaveformsInto()`, called from
`wwSetActiveAnalysisType()`). It is explicitly NOT a copy of the full
Waveform page — no channel browser, no Cursor A/B, no RMS controls, no
Split View, no second Playback control surface, no manual channel
picker.

### Role declaration seam

An analyzer calls `wwAnalysisSetRelatedWaveformRoles(roles, contextId,
groupId)` whenever its own active signal set changes, where `roles` is
an array of:

```js
{ roleKey, engineeringType, phase, channelRef, unit, label, color }
```

`channelRef`/`unit` always come straight from that analyzer's own
already-resolved backend response (`/phasor-diagram`'s `roles[key].
channel_ref`/`.unit`, `/overcurrent`'s `channel_ref`/
`measured_rms_current_unit`) — this module never parses a channel name
or bypasses resolver/backend metadata. `engineeringType` is `"Voltage"`
or `"Current"` (the only two supported groups today).

- **Phasor** (`wwPhasorComputeActiveRelatedWaveformRoles()`): every
  role currently `available` AND visible in `wwPhasorState.
  visibleRoles` — the SAME state the vector-visibility eye toggle
  already reads/writes, never a second waveform-visibility state.
  Hiding/showing a vector in the Phasor diagram simultaneously hides/
  shows its own waveform trace, with no separate control.
- **Overcurrent** (`wwOvercurrentComputeActiveRelatedWaveformRoles()`):
  exactly one Current role, for `wwOvercurrentState.phase` — the SAME
  Phase selector already drives resolution/computation. Never declares
  a Voltage role, even though Voltage channels may exist in the same
  Engineering Context — only analyzer-relevant signals are shown.

### Visibility gate (`wwAnalysisActiveType`)

Both analyzers keep computing/re-rendering on every shared Playback
tick regardless of which panel is actually visible (each one's own
tick handler only gates on "is MY OWN Time Group the one moving," never
on panel visibility). Without a gate, two analyzers sharing one Time
Group would overwrite each other's own role push on every single tick,
causing constant re-fetch thrashing — a real regression caught during
this feature's own implementation via a Playback network-request test
that unexpectedly showed waveform fetches firing every tick. The fix:
`wwAnalysisActiveType` (kept in sync exclusively by
`wwSetActiveAnalysisType()`) gates every `wwXxxPushRelatedWaveformRoles()`
call — a hidden analyzer's own tick-driven push is a silent no-op.

### Data-fetch and caching strategy

Reuses the EXISTING `/waveform`/`/calculated-channels/{id}/waveform`
endpoints verbatim (`wwAnalysisFetchChannelWaveform()`) — same URL
shape, same `start_time`/`end_time`/`point_budget` contract, same
`wwWorkspaceTimeToSourceTime()`/alignment-offset conversion boundary
`wwFetchChannelRange()` (the main Waveform page's own fetch function)
already established. No new backend endpoint was added; see
`docs/development/PERFORMANCE_BASELINE.md`'s own finding that the
existing endpoint's min/max-envelope reduction already returns a
bounded ~55-80 KB payload in well under 50 ms regardless of recording
size, exactly the "repeated windowed request" shape this panel needs.
`unit_mode` is always `"engineering"` here — Per-Unit is never silently
applied, independent of the main Waveform page's own `ww.unitMode`.

`wwAnalysisRelatedWaveformsState.channelCache` (keyed by channel
identity, `wwAnalysisChannelRefKey()`) means a role toggled off and
back on within the same Engineering Context/Time Group never re-fetches
— a genuinely new fetch happens only for a channel not already cached
under the CURRENT context. `wwAnalysisSetRelatedWaveformRoles()` itself
short-circuits to a no-op (`s.lastSignature` comparison) whenever the
role set + context + group are unchanged from the last call — this is
what keeps it safe to call on every Playback-driven render (both
analyzers' own render paths do exactly that).

Waveform GEOMETRY is fetched once per (context, group, channel) and
stays static while Playback runs — only the vertical cursor moves on
every tick, via a targeted `Plotly.relayout(chartEl, {"shapes[0].x0":
t, ...})`, never a `Plotly.react()`/re-fetch
(`wwAnalysisRelatedWaveformsOnPlaybackTick()`, the ONE permanent
`wwPlaybackOnTick()` subscriber this panel registers).

### Grouping, rendering, units

Two independent Plotly figures (`Voltage`/`Current`), each with its own
y-axis/unit — never one shared numerical axis between the two
engineering families. Canonical role order is preserved within each
group (`Va,Vb,Vc`/`Ia,Ib,Ic`); partial groups are fully valid (a
group with zero active roles is simply hidden, never a forced
three-phase requirement). Neither group present shows the compact
`#wwAnalysisRelatedWaveformsEmptyState` message, never a blank plot.
Trace colors reuse `wwPhasorRoleColor(roleKey)` verbatim — the SAME
phase-identity tokens (`--ww-phase-a/b/c`) the Phasor diagram's own
vectors already use, so a role reads as visually the same identity in
both places.

**Implementation note — Plotly and CSS custom properties**: Plotly's
own trace/layout color handling parses a color string through its OWN
internal color library before ever setting a real SVG attribute, unlike
this app's existing hand-rolled SVG (Phasor's diagram, the Overcurrent
chart) which sets `var(--x)` directly as an SVG presentation attribute
and lets the BROWSER's own CSS cascade resolve it. Plotly does not
understand `var(--x)` and silently falls back to its own default
palette instead — caught visually during this feature's own
implementation (a real rendered trace's computed stroke was `rgb(31,
119, 180)`, Plotly's own default blue, not the theme's accent color).
Fixed by `wwAnalysisResolveCssColor()`, which resolves every CSS custom
property color to its actual value via `getComputedStyle()` before
handing it to Plotly — the one place in this app a chart genuinely
needs that extra resolution step.

### Context/analyzer switch behavior

- **Analyzer switch** (`wwSetActiveAnalysisType()`): reparents the one
  shared panel node into the newly-active analyzer's own anchor
  (`Node.insertBefore` on an already-attached node — moves it, never
  clones/recreates it) and asks that analyzer to re-push its own
  current roles. Never touches `wwPlayback` in any way — switching
  Phasor → Overcurrent never resets or seeks Playback time.
- **Engineering Context change**: `wwAnalysisSetRelatedWaveformRoles()`
  clears `channelCache` the moment `contextId` differs from the
  panel's own last-known context — a freshly-selected bay never shows
  a stale trace from the previous one. Every async fetch step re-checks
  the same `epochAtStart`/`currentWorkspaceId()` guard every other
  Analysis fetch in this app already uses.
- **Workspace clear**: `wwAnalysisResetRelatedWaveformsState()`, called
  once from `wwClearWorkspace()` alongside `wwAnalysisResetContextState()`/
  `wwPhasorResetState()`/`wwOvercurrentResetState()`. The user's own
  resize height is a UI preference, not workspace data, and is
  deliberately left untouched by this reset.

### User-resizable height

A vertical drag handle at the panel's own bottom edge
(`#wwAnalysisRelatedWaveformsResizeHandle`), reusing the EXISTING
`.ww-resize-handle` CSS class (grip mark, hover/active accent,
`ns-resize` cursor, 8px hit area) the Waveform page's own per-channel-
panel resize already established — no second resize affordance was
invented. `wwAnalysisWireRelatedWaveformsResize()` mirrors that same
function's own drag mechanics (pointer capture, an immediate clamped
style write on every `pointermove` plus a single rAF-flushed Plotly
resize, an authoritative final write on `pointerup`/`pointercancel`) as
a PATTERN, not a literal call — the Waveform page's own resize function
is parameterized on its own per-channel `panel` object shape
(`panel.groupKey`/`panel.chartEl`), which this shared, few-channel
preview panel does not have.

Bounds: `WW_ARW_MIN_HEIGHT = 150`, `WW_ARW_DEFAULT_HEIGHT = 280`,
`WW_ARW_MAX_HEIGHT = 520` (px) — fixed constants, not viewport-relative,
chosen so axes/traces stay usable at the minimum and analyzer-specific
content below is never completely pushed off-screen at the maximum.
Height persists in `wwAnalysisRelatedWaveformsState.height` only —
in-memory, session-local, never `localStorage`/the backend — which is
what makes it survive a Phasor↔Overcurrent switch, a context/bay
change, or any Playback state change for free (none of those paths
ever touch it). A resize never touches `roles`/`channelCache` and never
triggers a network request — purely a frontend, presentation-only
operation (`Plotly.Plots.resize()`, never `Plotly.react()`).

## Future-analyzer contract

A future analyzer (Impedance Locus, Differential, Sequence Components,
Directional) integrating with this shell needs to:

1. Register as an Engineering Context consumer
   (`wwAnalysisRegisterContextConsumer()`).
2. Mount the shared Playback control surface
   (`wwCreatePlaybackControlsHtml()`/`wwWirePlaybackControls()`/
   `wwSyncPlaybackControls()`, and subscribe via `wwPlaybackOnTick()`
   for its own moving visualization).
3. Call `wwAnalysisSetRelatedWaveformRoles(roles, contextId, groupId)`
   whenever its own active/resolved roles change, and add its own
   `#wwXxxRelatedWaveformsAnchor` div directly below its own Playback
   panel markup.

None of the three primitives require the new analyzer to write its own
discovery, clock, fetch, grouping, or Plotly rendering code — that is
precisely the point of this shared shell. Structural regression tests
(`backend/tests/test_frontend_analysis_related_waveforms.py`'s
`TestSharedRendererStatePath`/`TestSharedPanelExistsOnce` classes, and
the equivalent context-lifecycle tests in
`test_frontend_phasor_analysis.py`) assert that no analyzer-specific
bootstrap/renderer function exists, so a future analyzer that tries to
add one is caught immediately.

## Related documents

- [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)
- [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md)
- [DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock)
  (Playback), [DEC-089](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)
  (Context lifecycle + Related Waveforms Updates).
- `docs/development/PERFORMANCE_BASELINE.md` (waveform endpoint
  latency/payload precedent).
