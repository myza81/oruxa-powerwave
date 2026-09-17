# Impedance Locus Analysis

**Status: v1 implemented** — the THIRD Analysis-menu analyzer (Phasor,
Overcurrent, then Impedance Locus). Measurement/visualization only — this
is explicitly **NOT Distance Protection**: no protection zones, mho/
quadrilateral characteristics, fault loops, residual-current (k0)
compensation, phase-to-phase loops, directional logic, or trip
evaluation exist anywhere in this feature. A future, separate Distance
Protection analyzer is expected to reuse this same `ImpedancePoint`/R-X-
plane foundation — see "Reusable foundation for a future Distance
Protection analyzer" below.

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

Deliberately architected in three separable layers, per the task's own
explicit requirement:

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

later:
ImpedanceResult
       +
distance characteristic engine (NOT built)
       ↓
Distance Protection analyzer (NOT built, separate analysis_kind)
```

`app.domain.impedance` never imports or references any zone/
characteristic/fault-loop concept — a future Distance Protection module
would sit ALONGSIDE it (its own `app/domain/distance_protection.py`,
own service, own endpoints, own `analysis_kind="distance"` requirement
constants), consuming `ImpedancePoint`/`compute_impedance_point()` as a
building block, never modifying this module to add zone-specific
fields. The R-X plot's own equal-scale SVG geometry
(`wwImpedanceRenderPlot()`'s `pxPerOhm` mechanism) is likewise written
generically enough that a future zone-characteristic overlay could draw
its own shapes on the SAME coordinate transform, without this module
needing to change.

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
  Voltage+Current role pair (`Va`+`Ia` for Phase A, etc.) via
  `wwImpedanceComputeActiveRelatedWaveformRoles()`; Manual mode declares
  zero roles (hides/collapses the shared panel, mirroring Overcurrent's/
  Phasor's own corrected choice — never a fabricated manual waveform).
- Playback's own fetch-triggering half is gated off entirely while
  Manual is active (`wwImpedanceOnPlaybackTick()`'s own early return);
  the transport-UI-sync half stays unconditional per DEC-085.

## Known limitations / explicitly deferred (not this slice)

- **No real-browser Playwright coverage was added this slice** — only
  static structural regression tests
  (`backend/tests/test_frontend_impedance_analysis.py`) exist for the
  frontend; visual rendering, real pointer interaction, and the
  Playback-integration timing behavior were reasoned through and unit/
  API-tested at the backend layer, but not confirmed in a real browser.
  Flagged for owner UAT, mirroring the honesty precedent this project
  already applies to every prior slice that shipped without a browser
  available.
- Distance Protection (zones, mho/quadrilateral, fault loops, ground
  compensation, directional logic, trip interpretation) — not started;
  a future, separate analyzer.
- `Zab`/`Zbc`/`Zca` (phase-to-phase loops) — not started.
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
