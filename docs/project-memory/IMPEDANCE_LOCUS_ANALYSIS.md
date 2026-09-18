# Impedance Locus Analysis

**Status: v1 implemented and UAT-corrected** — the THIRD Analysis-menu
analyzer (Phasor, Overcurrent, then Impedance Locus). Measurement/
visualization only — this is explicitly **NOT Distance Protection**: no
protection zones, mho/quadrilateral characteristics, fault loops,
residual-current (k0) compensation, phase-to-phase loops, directional
logic, or trip evaluation exist anywhere in this feature. **Distance
Protection v1 is now implemented** (2026-09-18, DEC-099) as the fifth,
separate Analysis-menu analyzer, reusing this feature's own
`ImpedancePoint`/R-X-plane foundation exactly as anticipated below — see
[DISTANCE_PROTECTION_ANALYSIS.md](DISTANCE_PROTECTION_ANALYSIS.md) and
"Reusable foundation for a future Distance Protection analyzer" below
(kept for its own historical/architectural record; every "NOT built"
note in that section is now realized).

**2026-09-17 UAT correction** (own section below, "Related Waveforms and
chronological locus reveal — UAT correction"): two owner-reported bugs
were fixed the same day — Related Waveforms rendered blank axes with no
Voltage/Current trace, and the full impedance locus was visible
immediately instead of only up to the current Playback time. Both are
now fixed; see that section for the full root-cause and fix record. This
is the FIRST time this feature received real-browser (Playwright)
verification — the original v1 slice's own "no real-browser coverage"
gap (noted in "Known limitations" below) is what let the Related
Waveforms bug go undetected through static tests alone.

## Product definition

> Powerwave calculates apparent phase impedance `Z = V/I = R + jX`
> directly from a Voltage phasor and a Current phasor's own magnitude
> and angle — never approximated from RMS scalars alone.

```
Za = Va / Ia
Zb = Vb / Ib
Zc = Vc / Ic
```

`R = |Z|·cos(theta_Z)`, `X = |Z|·sin(theta_Z)`, where
`theta_Z = theta_V - theta_I` uses each phasor's own **absolute** angle
(`angle_deg_absolute` in Recording mode) — never independently
zero-referenced, which would destroy the true V-I angular relationship
this calculation depends on. All four quadrants are valid; R/X are never
clamped.

## Scope of v1

Only phase impedances (`Za`/`Zb`/`Zc`). Explicitly out of scope:
`Zab`/`Zbc`/`Zca`, AG/BG/CG fault loops, residual-current compensation,
k0, distance relay zones, mho/quadrilateral characteristics, load
encroachment, power swing, fault classification, trip evaluation — all
future Distance Protection scope, not this analyzer's.

## Recording mode reuses the existing Phasor estimator — no second estimator

`app.services.impedance_analysis_service.compute_impedance_analysis()`
calls the existing, unchanged `phasor_analysis_service.
compute_phasor_diagram()` (the SAME bay-centric aggregator Phasor's own
Analysis page uses) and simply reads out whichever Voltage/Current role
pair the selected phase needs (`Va`/`Ia` for Phase A, etc.). This means:

- Zero duplicated FFT/DFT/RMS estimation code.
- Automatic inheritance of every one of `compute_phasor_diagram()`'s own
  guardrails (reference-frequency conflict, timebase incompatibility,
  waveform-form eligibility) with no Impedance-specific reimplementation.
- Whichever role is not `available` (missing/ambiguous/needs_
  configuration/not_eligible) maps directly to the whole Impedance
  result's own status — Impedance always needs BOTH Voltage and Current
  together for one phase, unlike Phasor's own six-independent-role
  diagram where one role's failure never blocks another.

`app.domain.analysis_requirements` gained
`IMPEDANCE_VOLTAGE_PHASE_A/B/C`/`IMPEDANCE_CURRENT_PHASE_A/B/C` (own
`analysis_kind="impedance"`, identical Voltage/Current-per-phase `RoleSpec`
shape already used by Phasor/Overcurrent) purely so the requirement
registry stays the single closed source of truth for every mode's role
shape — these are declared for documentation/future-reuse purposes; the
Recording-mode service itself resolves roles via `compute_phasor_
diagram()`, never by calling `resolve_analysis_inputs()` a second time
for `Va`/`Ia` independently.

## Low-current guardrail — numerical validity, not a relay pickup threshold

`app.domain.impedance.MIN_CURRENT_A = 1e-3` (1 mA). `Z = V/I` is
numerically unstable/unbounded as `|I| -> 0`; below this floor, the
result reports `status = "needs_configuration"`, `reason_code =
"current_too_small"`, never a fabricated huge/infinite `|Z|`. Chosen
because at 1 mA, `|Z|` is already at least `100,000 Ω` for any realistic
recorded voltage — the result is meaningless for plotting well before
genuine floating-point instability would set in. This is deliberately
**not** an invented relay pickup/sensitivity threshold (Impedance Locus
v1 makes no protection-operation claim of any kind).

## Primary/Secondary basis — two INDEPENDENT concepts per mode

**Recording mode**: `recording_basis` describes the basis the resolved
Va/Vb/Vc/Ia/Ib/Ic channels' own values already represent (an engineer-
entered setting, mirroring Overcurrent's own `recording_basis`/CT
pattern — Powerwave does not auto-detect this from recording metadata,
per the same established precedent DEC-095 already set); `impedance_
basis` is the INDEPENDENT desired OUTPUT basis. If they already match,
`Z = V/I` is returned directly with **zero VT/CT ratio dependency** — no
ratios are required or validated unless a genuine conversion is needed.
This matches the task's own golden example ("same basis," no CT/VT
involved at all) and the basis-conversion test matrix's own trivial
same-basis cases.

**Manual mode**: mirrors Manual Phasor's architecture exactly — Voltage
and Current each carry their OWN independent basis + VT/PT or CT ratio
(`voltage_basis`/`current_basis`, reusing `convert_manual_magnitude_to_
secondary()` **verbatim**, never a duplicated conversion formula), and
BOTH are always normalized to Secondary-canonical internally before
`Z = V/I` is computed — unlike Recording mode, there is no "same-basis
shortcut" here, since Manual's own architecture always routes through
one canonical basis first (consistency with Phasor's own established
Manual-mode design was judged more valuable than optimizing away a
redundant round-trip for the rare case where a Manual engineer's chosen
input and output basis happen to coincide). `impedance_basis` is then a
**third**, independent OUTPUT basis for the calculated impedance (task's
own section 11 requirement) — e.g. Voltage entered Primary, Current
entered Secondary, Impedance requested Primary is a valid, tested
combination (`docs/project-memory/ANALYSIS_INPUT_SOURCE.md`'s own "N
independent bases for N independent physical quantities" principle,
extended here with one more independent axis: the OUTPUT basis).

### Basis conversion formula — verified, not blindly adopted

```
VT_ratio = V_primary / V_secondary
CT_ratio = I_primary / I_secondary

Z_primary   = Z_secondary * (VT_ratio / CT_ratio)
Z_secondary = Z_primary   * (CT_ratio / VT_ratio)
```

Derived from — and confirmed consistent with — this codebase's own
existing ratio convention: `app.domain.overcurrent.convert_to_relay_
secondary()` already treats `I_secondary = I_primary * (ct_secondary /
ct_primary) = I_primary / CT_ratio`; `app.domain.phasor.convert_manual_
magnitude_to_secondary()` already treats `V_secondary = V_primary *
(ratio_secondary / ratio_primary) = V_primary / VT_ratio`. Combining:
`Z_secondary = V_secondary / I_secondary = (V_primary/VT_ratio) /
(I_primary/CT_ratio) = Z_primary * (CT_ratio/VT_ratio)`, i.e.
`Z_primary = Z_secondary * (VT_ratio/CT_ratio)` — exactly the task's own
specified formula, proven against the codebase's actual direction rather
than assumed. Golden tests (`test_impedance_domain.py::TestBasisConversion`)
verify this numerically, including the "equal VT/CT ratio → factor 1"
sanity property.

## Za/Zb/Zc phase selection

A compact `Phase [A|B|C]` selector, default `A`, shared by both Input
Sources (Recording resolves roles through it; Manual uses it purely to
LABEL the result, e.g. "Zb" — Manual's own calculation never depends on
Engineering Context or phase identity at all). Recording mode never
infers phase from a channel name — phase resolution is entirely the
existing Engineering Context / durable canonical-phase-identity
machinery (Slice 1/2), consumed unchanged via `compute_phasor_diagram()`.

## R-X plot — equal geometric scale (hard requirement)

A hand-rolled SVG Cartesian plot (`#wwImpedanceSvg`, mirroring the
Phasor diagram's own "no existing chart precedent fits" reasoning) — one
shared `pxPerOhm` factor (`wwImpedanceRenderPlot()`) derived from a
single `wwImpedanceNiceLimit()` call converts every point's `(R, X)` to
SVG coordinates identically on both axes: **one ohm horizontally is
always the same pixel distance as one ohm vertically**, by construction
(there is structurally no way to set an X scale independently of a Y
scale in this implementation — both read the same variable). Origin at
`R=0/X=0`; `+R` right, `-R` left, `+X` up, `-X` down; axis labels `R (Ω)`
and `X (Ω)`, painted last (on top of every point/path, mirroring the
Phasor diagram's own "labels painted after vectors" fix so a point can
never visually obscure a label).

### Automatic viewport

`wwImpedanceNiceLimit(maxAbs)` picks the smallest "nice" value from the
`1×`/`2×`/`5×`/`10×` × decade sequence that is `>= 1.3 × maxAbs` — 30%
headroom, so the plotted point(s) always occupy a meaningful portion of
the plot without touching the edge. `maxAbs` is the largest `|R|`/`|X|`
across every currently-relevant point (the live current point, plus
every `computed` locus point in Recording mode; just the one point in
Manual mode) — recomputed on every render, so the viewport tracks
whatever data is actually being shown, never a fixed oversized default.

## Manual mode — one point only

Manual mode v1 displays exactly one impedance point (a dashed-ring
marker, `.ww-imp-point--manual`, distinct from Recording's solid-fill
current-point marker — mirrors Overcurrent's own `.ww-oc-manual-marker`
convention so a manual/test point never reads as a genuine recording
result), with an SVG `<title>` tooltip (`Za` / `R = ... / X = ... /
|Z| = ... / ∠ = ...`). No locus/history is ever synthesized from one
manual point.

## Recording mode — current point + static locus

Two logically separate concerns, both backed by dedicated endpoints:

1. **Current point** (`GET .../impedance`) — one selected-time
   calculation, synchronized to the shared `wwPlayback` controller
   exactly like Phasor/Overcurrent (throttled ~10 Hz while playing,
   exact non-throttled fetch on Pause/Restart/seek — identical shape to
   `wwPhasorMaybeFetchForPlayback()`/`wwOvercurrentMaybeFetchForPlayback()`).
   No analyzer-specific timer exists.
2. **Static locus/trajectory** (`GET .../impedance-locus`) — the
   analyzer's own name is "Impedance **Locus**," so Recording mode also
   shows a deterministic trajectory across the active Time Group's own
   full extent (`wwDeriveTimeGroupBounds(groupId)`), sampled server-side
   at up to `point_count` evenly-spaced instants (default 120, hard
   capped at `MAX_LOCUS_POINTS = 300` in `impedance_analysis_service.py`
   — "avoid excessive point counts"). Each sample is an independent
   selected-time Impedance calculation (never a second estimator); a
   point outside the recording's own valid window is still returned,
   carrying whatever `status`/`reason_code` it naturally produces — the
   frontend renders only contiguous `computed` runs as the path,
   starting a new SVG subpath (`M x,y`) after any gap, so an invalid
   stretch is a visible break, never a straight line jumping across it.
   **The full locus may be (and is) computed/cached upfront for
   performance, but only the portion up to `wwPlayback.currentTime` is
   ever displayed** (via the already-fetched exact current point's own
   `analysis_time` as the chronological cutoff — see "Related Waveforms
   and chronological locus reveal — UAT correction" below for the full
   record of this 2026-09-17 fix).

### Locus caching — fetched on settings change, never per Playback tick

`wwImpedanceMaybeFetchLocus()` computes a signature string
(`contextId|groupId|phase|recordingBasis|outputBasis|vt/ct ratios`) and
short-circuits to a no-op whenever that signature is unchanged from the
last successful fetch — the exact same `s.lastSignature` short-circuit
convention the shared Related Waveforms panel already established.
`wwImpedanceOnPlaybackTick()` — the ONE Playback-tick subscriber — never
calls the locus fetch at all (verified directly by a static test,
`test_frontend_impedance_analysis.py::TestImpedanceLocusIsStaticNotPerTick`);
only `wwImpedanceHandleSettingsChanged()`/`wwImpedanceLoadForSelectedContext()`
invalidate and re-fetch it. This mirrors Overcurrent's own
`.../overcurrent-curve` caching precedent (curve geometry fetched only
on a characteristic/TMS change, never per tick) applied to a time-series
locus instead of a characteristic curve.

## Related Waveforms and chronological locus reveal — UAT correction (2026-09-17)

Two owner-reported bugs, found together via the first real-browser
verification this feature ever received, both fixed the same day.

### Bug 1 — Related Waveforms rendered blank axes with no trace

**Root cause**: `wwImpedanceComputeActiveRelatedWaveformRoles()` pushed
role objects with no `channelRef` field at all. The shared Related
Waveforms panel's own cache key
(`wwAnalysisChannelRefKey(role.channelRef)`) collapses `undefined` to
the same synthetic `"none"` string for every role — so BOTH the Voltage
and Current roles collided onto one cache key, only one fetch was ever
attempted (`wwAnalysisFetchChannelWaveform(workspaceId, undefined, ...)`),
and that fetch threw immediately (`channelRef.kind` on `undefined`),
silently caught and left uncached. The axes/grid still rendered (the
Plotly figure itself was created), but no trace data ever populated —
exactly the reported symptom.

**Fix**: `app.domain.impedance.ImpedanceAnalysisResult` gained
`voltage_channel_ref`/`current_channel_ref` fields (populated from
`compute_phasor_diagram()`'s own already-resolved
`PhasorDiagramRoleResult.channel_ref`, which this analyzer already reads
for magnitude/angle — the identity was always available, it simply
wasn't being carried into the result object). Wired through
`ImpedanceAnalysisResultOut` and the `.../impedance` API mapper.
`wwImpedanceComputeActiveRelatedWaveformRoles()` now pushes
`channelRef: result.voltage_channel_ref`/`result.current_channel_ref`
directly from the already-resolved backend response — never re-derived
from a channel name, matching every other analyzer's own established
convention.

**A deliberate additional correction, beyond the literal bug report**:
the role-push gate was relaxed from `result.status === "computed"` to
per-quantity `if (result.voltage_channel_ref)` / `if (result.current_channel_ref)`.
A role's own channel identity is resolved independently of whether the
FULL impedance calculation succeeds (e.g. the low-current guardrail
blocks the Ω result but the Voltage/Current channels themselves are
perfectly real) — gating on overall `status` would have hidden exactly
the waveform traces an engineer most needs when diagnosing *why* a
guardrail tripped. Verified directly:
`test_impedance_analysis_api.py::TestRecordingImpedanceViaHttp::
test_channel_refs_populated_even_when_current_too_small`.

### Bug 2 — the full locus was visible before Playback progressed

**Root cause**: `wwImpedanceRenderPlot()`'s locus-path-drawing loop
iterated the ENTIRE cached `wwImpedanceState.locusPoints` array
unconditionally, with no relationship to `wwPlayback.currentTime` at
all — the whole event's trajectory rendered the instant the locus fetch
resolved, regardless of where Playback actually was.

**Fix**: a new `wwImpedanceVisibleLocusCutoffTime()` returns
`wwImpedanceState.latestResult.analysis_time` (or `null` before any
exact point has ever been fetched) — the SAME already-fetched, already-
throttled current-point result that draws the marker itself (task's own
"use nearest deterministic cached point or existing exact point fetch,
consistently" requirement, satisfied by choosing the SAME source for
both the trail's endpoint and the marker, so they can never disagree
about which instant they represent). The locus-path loop now skips any
point with `analysis_time > cutoffTime` (a small `1e-6` epsilon absorbs
floating-point noise between the independently-sampled locus grid and
the exact-fetched cutoff instant). Both `analysis_time` values are
already in the identical coordinate (native/source-relative elapsed
time, both derived via the SAME `wwImpedanceState.anchorDisplaySourceId`
anchor conversion), so no further conversion was needed.

**The full locus/performance model is completely unchanged** —
`wwImpedanceMaybeFetchLocus()` still fetches/caches the WHOLE locus
exactly once per context/phase/settings/time-range change, still never
refetches per Playback tick (unchanged `signature` short-circuit,
verified by `TestImpedanceLocusIsStaticNotPerTick`). Only the DRAWING
step became chronologically aware; the fetch/cache step was never
touched. Because the current-point fetch is throttled to ~10 Hz while
playing (unchanged, pre-existing architecture — see "Recording mode —
current point + static locus" above), the trail's own visible growth is
tied to that same ~10 Hz cadence, not a separate 60 fps render loop —
deliberately, so the trail's endpoint and the marker are always derived
from the identical fetched instant and can never desynchronize.

**The VIEWPORT (axis scale/headroom) intentionally stays based on the
FULL cached locus**, not just the chronologically-visible portion —
`wwImpedanceCollectRelevantPoints()` (used only for `wwImpedanceNiceLimit()`
sizing) was deliberately left unchanged. This means the R-X axes are
already scaled to the eventual full-event range from the very first
render (satisfying the task's own "show full R-X axes/grid" initial-
state requirement) and never visibly rescale/jump as more of the trail
is progressively revealed — only the PATH drawn within that stable
viewport grows chronologically. Restart/Seek/Play/Pause all fall out of
this one mechanism with zero special-casing: Restart re-lands the exact
fetch at `bounds.start` (collapsing the cutoff, never touching the
cached locus itself — `wwImpedanceInvalidateLocus()` is not called on
Restart); a seek's own exact, non-throttled fetch updates the cutoff
immediately (never animating through skipped history); reaching
`bounds.end` naturally reveals the entire cached locus once the cutoff
exceeds every sampled point's own time.

**Real-browser verification** (`browser-tests/impedance_analysis.spec.js`,
new — 10 scenarios): Related Waveforms Va/Ia trace geometry before Play,
Phase A→B trace switching, 1366px/1024px responsiveness, initial-state
(cached-but-not-drawn) locus, Play growing the trail then Pause freezing
it, Seek immediately expanding the trail, Restart collapsing it (cached
locus count unchanged), full reveal at the event end, zero
`/impedance-locus`/`/waveform` requests during Playback ticks, and
Manual mode's own unaffected one-point/no-trail behavior. Confirmed to
actually catch the Bug 1 regression (verified by temporarily reverting
the `channelRef` fix and re-running — the trace-visibility test failed
exactly as expected, then passed again once restored). New static
regression tests:
`test_frontend_impedance_analysis.py::TestImpedanceRelatedWaveformsChannelRefRegression`/
`TestImpedanceLocusChronologyRegression` (5 tests), plus two new backend
API tests
(`test_impedance_analysis_api.py::TestRecordingImpedanceViaHttp::
test_channel_refs_are_populated_for_related_waveforms`/
`test_channel_refs_populated_even_when_current_too_small`). Two
pre-existing Playwright tests needed fixing as a DIRECT consequence of
this slice (both mirror precedents already established elsewhere in
this project):
`overcurrent_analysis.spec.js`'s own settings-grid-width tests (an
unscoped `.ww-oc-settings-grid` locator now also matches Impedance's own
reuse of that class — scoped to `#wwOvercurrentBody .ww-oc-settings-grid`,
mirroring the earlier `.ww-oc-input-source-panel` collision fix), and
`phasor_analysis.spec.js`'s own analyzer-menu test (previously asserted
the Impedance panel still said "not implemented yet," true before v1
shipped, stale after it). No IEC/RMS/CT/VT/impedance math, basis
conversion, low-current guardrail, or R/X equal-scale geometry was
touched by this correction — see [DECISIONS.md](DECISIONS.md) for
whether this amends DEC-096 formally.

## Validation / guardrails

Handled explicitly, never reaching the plot as a fabricated point:
missing Voltage/Current (`status="missing"`), zero/near-zero current
(`current_too_small`), invalid manual magnitude/angle/ratio/basis
(`needs_configuration`, several distinct `reason_code`s), unsupported
unit (reuses the shared `app.domain.engineering_units` layer — never a
second unit dictionary), NaN/Infinity (rejected by `math.isfinite()`
checks throughout `app.domain.impedance`). See
`backend/tests/test_impedance_domain.py` for the full guardrail matrix.

## Golden mathematical result

```
V = 100 kV ∠ 0°,  I = 1 kA ∠ -30°  (same basis)
→ |Z| = 100 Ω, angle = +30°, R ≈ 86.6025 Ω, X = 50 Ω
```

Verified at every layer:
`test_impedance_domain.py::TestGoldenWorkedExample`,
`test_impedance_analysis_api.py::TestManualImpedanceViaHttp::
test_golden_example_via_http_zero_prior_setup`, and the Recording-mode
equivalent (`TestRecordingImpedanceViaHttp::test_golden_za_via_http`)
via a real three-phase ASCII-COMTRADE upload.

## Reusable foundation for a future Distance Protection analyzer

**Realized 2026-09-18 (DEC-099)** — kept below for its own historical/
architectural record; see
[DISTANCE_PROTECTION_ANALYSIS.md](DISTANCE_PROTECTION_ANALYSIS.md) for
the actual implementation. Deliberately architected in three separable
layers, per the task's own explicit requirement:

```
shared phasor input (compute_phasor_diagram(), unchanged)
       ↓
impedance engine (app.domain.impedance: compute_impedance_point(),
                   convert_impedance_basis())
       ↓
ImpedanceResult (ImpedancePoint / ImpedanceAnalysisResult)
       ↓
R-X visualization (wwImpedanceRenderPlot() -- equal-scale Cartesian SVG)
       ↓
Impedance Locus analyzer (this feature)

then (realized 2026-09-18, DEC-099):
ImpedanceResult
       +
distance characteristic engine (app.domain.distance_protection)
       ↓
Distance Protection analyzer (separate analysis_kind="distance")
```

`app.domain.impedance` never imports or references any zone/
characteristic/fault-loop concept — Distance Protection's own module
(`app/domain/distance_protection.py`, own service, own endpoints, own
`analysis_kind="distance"` requirement constants) sits ALONGSIDE it,
consuming `compute_impedance_point()`/`convert_impedance_basis()` as a
building block, never modifying this module to add zone-specific
fields — confirmed exactly as anticipated. The R-X plot's own
equal-scale SVG geometry (`WW_IMPEDANCE_PLOT_RADIUS`/
`wwImpedanceNiceLimit()`) is reused directly by Distance Protection's
own `wwDistanceRenderPlot()` to draw Mho/Quadrilateral zone shapes on
the SAME coordinate transform — this module itself needed zero changes.

## API

```
GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/impedance
    ?phase=A&analysis_time=1.5&recording_basis=secondary&impedance_basis=secondary
    (&vt_primary=...&vt_secondary=...&ct_primary=...&ct_secondary=..., required only when recording_basis != impedance_basis)
    (&reference_frequency_hz=..., optional override)

GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/impedance-locus
    ?phase=A&start_time=0.0&end_time=2.0&point_count=120&recording_basis=secondary&impedance_basis=secondary
    (&vt_primary=...&vt_secondary=...&ct_primary=...&ct_secondary=...)

GET /api/v1/workspaces/{workspace_id}/impedance-manual
    ?phase_label=A&voltage_basis=primary&vt_primary=132000&vt_secondary=110
    &current_basis=primary&ct_primary=1200&ct_secondary=1&impedance_basis=primary
    &voltage_enabled=true&voltage_magnitude=132&voltage_unit=kV&voltage_angle_deg=0
    &current_enabled=true&current_magnitude=1.2&current_unit=kA&current_angle_deg=-30
```

Same nested/selected-time/never-persisted router convention Phasor's/
Overcurrent's own endpoints already established, in the same
`app/api/v1/engineering_contexts.py` file. `.../impedance-manual` is
workspace-scoped only (never nested under an Engineering Context), like
`.../phasor-manual`/`.../overcurrent-manual`.

## Frontend — Input Source shell reuse

Reuses the `ANALYSIS_INPUT_SOURCE.md` shared shell/pattern verbatim,
its THIRD real implementation:

- `wwImpedanceState.inputSource`/`wwImpedanceState.manual` — own,
  per-analyzer state (never a shared/global input-source object).
- The three-region markup split (`#wwImpedancePanel` → an always-visible
  Input Source toggle → `#wwImpedanceRecordingSection` (Bay/Context,
  Playback, Related Waveforms, recording-only empty state, behind ONE
  `hidden` toggle) → `#wwImpedanceBody` (Phase/basis Settings, Manual
  Input, Results, R-X plot — never hidden by any recording-lifecycle
  callback)) — implemented from day one, never the flawed intermediate
  "Manual coupled to the recording empty state" design Overcurrent
  briefly shipped.
- `WW_ANALYSIS_INPUT_SOURCE_RECORDING`/`WW_ANALYSIS_INPUT_SOURCE_MANUAL`
  reused verbatim (never a `WW_IMPEDANCE_*` re-declaration).
- Recording availability/one-time auto-selection
  (`wwImpedanceUpdateInputSourceAvailability()`), the segmented control
  reusing `.ww-oc-axis-toggle-group`/`-btn`/`--active` verbatim, and the
  "change" event convention for every Manual field — all identical in
  shape to Overcurrent's/Phasor's own implementations.
- Related Waveforms: Recording mode declares the selected phase's own
  Voltage+Current role pair (`Va`+`Ia` for Phase A, etc.), each carrying
  `channelRef` straight from the already-resolved backend response
  (`result.voltage_channel_ref`/`result.current_channel_ref` — see the
  "Related Waveforms and chronological locus reveal — UAT correction"
  section below for why this specific field is what actually makes the
  shared panel's own fetch work) via
  `wwImpedanceComputeActiveRelatedWaveformRoles()`; Manual mode declares
  zero roles (hides/collapses the shared panel, mirroring Overcurrent's/
  Phasor's own corrected choice — never a fabricated manual waveform).
  The full recording waveform geometry renders immediately once
  Recording mode + Engineering Context + phase are all resolved —
  Playback state never controls whether the traces themselves exist,
  only where the shared cursor overlay currently sits (see
  [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md)'s own "Shared Related
  Waveforms" section for that unchanged, pre-existing architecture).
- Playback's own fetch-triggering half is gated off entirely while
  Manual is active (`wwImpedanceOnPlaybackTick()`'s own early return);
  the transport-UI-sync half stays unconditional per DEC-085.

## Known limitations / explicitly deferred (not this slice)

- **Real-browser Playwright coverage now exists** (`browser-tests/
  impedance_analysis.spec.js`, 10 scenarios, added 2026-09-17 alongside
  the "Related Waveforms and chronological locus reveal" UAT correction
  above) — the original v1 slice's own "no real-browser coverage" gap is
  CLOSED. It was this exact gap that let the Related Waveforms blank-
  trace bug ship undetected through static tests alone; see that
  section's own record for the incident this closes.
- Distance Protection (phase-phase `Zab`/`Zbc`/`Zca` fault loops, Mho/
  Quadrilateral zone characteristics) is now implemented as its own,
  separate analyzer — see
  [DISTANCE_PROTECTION_ANALYSIS.md](DISTANCE_PROTECTION_ANALYSIS.md).
  Ground-loop (AG/BG/CG) compensation, directional supervision beyond
  the characteristic itself, and trip interpretation remain unstarted —
  a future, separate enhancement on top of that module's own foundation,
  never this one.
- Manual Engineering Context creation/editing UI — unrelated pre-existing
  gap, unaffected by this slice.
- Automatic Recording-basis detection from a recording's own metadata —
  the engineer always enters VT/CT ratios manually when a conversion is
  needed, matching Overcurrent's/Phasor's own established DEC-095
  precedent.
- Impedance persistence — never persisted, matching every other analyzer.

## Related documents

- [ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md) — the shared
  Recording/Manual shell this feature's own Input Source implementation
  is the third real proof-of-reuse for.
- [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) — the shared
  Engineering Context lifecycle/Playback/Related Waveforms primitives
  this analyzer consumes unchanged.
- [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md) — the estimator/resolver
  foundation (`compute_phasor_diagram()`) Recording mode reuses verbatim.
- [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) — the CT-ratio/
  Manual-Input architectural precedent this feature's own basis handling
  extends to cover Voltage (VT/PT) as well as Current.
- [DECISIONS.md — DEC-096](DECISIONS.md#dec-096--impedance-locus-v1-the-third-analysis-menu-analyzer-apparent-phase-impedance-measurementvisualization-explicitly-not-distance-protection) —
  this slice's approval record.
- [DISTANCE_PROTECTION_ANALYSIS.md](DISTANCE_PROTECTION_ANALYSIS.md) —
  the separate, fifth analyzer that reuses this feature's own
  `compute_impedance_point()`/`convert_impedance_basis()`/R-X-plot
  coordinate transform exactly as anticipated above.
