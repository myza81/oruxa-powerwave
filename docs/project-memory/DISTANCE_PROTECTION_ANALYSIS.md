# Distance Protection Analysis

Status: **v1 implemented** (2026-09-18). Activates a new `Distance
Protection` navigation entry as the **FIFTH** Analysis-menu analyzer
(order preserved: Phasor, Overcurrent, Impedance Locus, Sequence
Components, Distance Protection). See
[DECISIONS.md — DEC-099](DECISIONS.md#dec-099--distance-protection-v1-the-fifth-analysis-menu-analyzer-mho-and-quadrilateral-zone-characteristic-evaluation-on-phase-phase-fault-loop-impedance)
for the approval record.

## Product definition — separate from Impedance Locus

**Impedance Locus = what impedance did the system present?** Distance
Protection = **how does a configured distance-relay characteristic
interpret that impedance?** These are two conceptually distinct
questions and two separate analyzers — own nav entry, own panel id
(`wwDistancePanel`), own state object (`wwDistanceState`), own R-X plot
`<svg>` instance. Distance Protection never mutates, reads, or depends
on any Impedance Locus state, and vice versa.

v1 performs **characteristic/element evaluation only** — phase-phase
(AB/BC/CA) fault-loop impedance, Mho and Quadrilateral zone-
characteristic geometry, and INSTANTANEOUS `Operated`/`Not Operated`
geometric zone-element state, for engineering study.

## Scope of v1

**In scope:** Input Source (Recording|Manual); Fault loop (AB|BC|CA);
Impedance basis (Primary|Secondary); Characteristic (Mho|Quadrilateral);
Zones 1-3; Results (loop impedance R/X/|Z|/angle, zone state, configured
delay).

**Explicitly out of scope this slice** (owner's own instruction,
restated here as the single most important interpretive boundary): no
AG/BG/CG ground loops, no residual-current (k0)/zero-sequence
compensation, no memory/negative-sequence polarization, no load
encroachment, no power swing blocking, no directional supervision beyond
the characteristic itself, no relay trip output, no breaker operation,
no timer accumulation, no vendor-specific relay logic, no fault
classification. `Operated` is a purely GEOMETRIC statement about where
the calculated loop impedance sits relative to a configured
characteristic — it never means a relay tripped, a breaker opened, or
full relay logic completed. `Configured delay` is configuration
information only — never accumulated, never declared elapsed, never
used to assert a trip. A future, SEPARATE enhancement may add
element-operated → timer-running → timer-elapsed → trip-asserted logic
on top of this module's own loop-impedance/zone-state foundation — never
coupled into it here.

## Layered architecture (explicit, for future extensibility)

```text
phasor input -> loop impedance engine -> distance characteristic engine -> zone element state -> visualization
```

Each layer is independent so a future addition (AG/BG/CG, k0,
polarization, timers, load encroachment, power swing, trip logic) can be
added without rewriting the basic loop-impedance or geometry engines:

- **Phasor input**: Recording reuses `compute_phasor_diagram()`
  verbatim (see below); Manual reuses `ManualPhasorRoleInput`/
  `convert_manual_magnitude_to_secondary()` verbatim.
- **Loop impedance engine**: `app.domain.distance_protection.
  compute_loop_impedance()` — pure complex-phasor subtraction/division,
  no characteristic/zone knowledge at all.
- **Distance characteristic engine**: `mho_zone_operated()`/
  `quadrilateral_zone_operated()` — pure geometry, takes an already-
  computed `ImpedancePoint` plus a characteristic's own settings, no
  phasor/loop knowledge.
- **Zone element state**: `evaluate_zone_state()`/`ZoneResult` — the
  thin dispatcher + Enabled/delay bookkeeping layer.
- **Visualization**: the frontend R-X plot, reusing Impedance Locus's
  own coordinate transform.

## Fault-loop impedance — full complex phasor subtraction, never phase impedance

```text
Zab = (Va - Vb) / (Ia - Ib)
Zbc = (Vb - Vc) / (Ib - Ic)
Zca = (Vc - Va) / (Ic - Ia)
```

`app.domain.distance_protection.compute_loop_impedance()` builds each
phasor via `cmath.rect(magnitude, radians(angle))` (the complex-number
convention Sequence Components established — see
[SEQUENCE_COMPONENTS_ANALYSIS.md](SEQUENCE_COMPONENTS_ANALYSIS.md)'s own
"Complex-number representation" section), subtracts the two Voltage legs
and the two Current legs, decomposes each difference back to magnitude/
angle via `cmath.polar()`, then calls the EXISTING `app.domain.impedance.
compute_impedance_point()` on the two loop phasors unchanged — this
module's only new math contribution is the phasor SUBTRACTION step; the
division/low-current guardrail/basis-conversion are entirely reused,
zero duplication. **This is genuinely different from phase impedance**
(`Za = Va/Ia`) — `backend/tests/test_distance_protection_domain.py::
TestLoopImpedanceIsNotPhaseImpedance` proves an asymmetric case where the
two values differ (loop |Z|=8.663∠47.8° vs. phase |Z|=10∠15°), so a
naive `Za`-based implementation could never pass this regression.

`LOOP_ROLE_KEYS = {"AB": ("Va","Vb","Ia","Ib"), "BC": ("Vb","Vc","Ib","Ic"),
"CA": ("Vc","Va","Ic","Ia")}` — AB never resolves/requires phase C, etc.

## Golden loop-impedance result (balanced three-phase set)

```text
Va=100∠0°, Vb=100∠-120°, Vc=100∠120°
Ia=10∠-20°, Ib=10∠-140°, Ic=10∠100°

Zab = Zbc = Zca = 10 Ω ∠20°   (R=9.396926207859085, X=3.4202014332566875)
```

Under perfect balance every phase-phase loop reduces to the SAME
impedance as the phase quantities' own ratio-and-angle-difference (the
line-to-line `+30°` shift cancels between Voltage and Current) — an
independently `cmath`-verified property, hardcoded as the golden
regression in `TestLoopImpedanceGoldenBalanced` (AB/BC/CA, one test
each) and reused as the Manual-mode/API-mode golden flow throughout this
feature's own test suite.

## Recording mode reuses the existing Phasor estimator — no second estimator

`app.services.distance_protection_analysis_service.
compute_distance_analysis()` calls the existing, unchanged
`phasor_analysis_service.compute_phasor_diagram()` exactly once — the
same bay-centric aggregator Impedance Locus's/Sequence Components' own
Recording mode already use — extracts whichever four roles
(`LOOP_ROLE_KEYS[loop]`) the selected fault loop needs, and calls
`compute_loop_impedance()` on their `magnitude_rms`/
`angle_deg_absolute` values. Zero duplicated FFT/DFT/RMS code, automatic
inheritance of `compute_phasor_diagram()`'s own reference-frequency/
timebase/waveform-form guardrails. `_worst_role_status()` generalizes
Impedance's own two-role `_worse_role_status()` precedence helper to
FOUR roles (mirrors how Sequence Components generalized it to three).
`app.domain.analysis_requirements` gained `DISTANCE_VOLTAGE_PHASE_A/B/C`/
`DISTANCE_CURRENT_PHASE_A/B/C` under their own `analysis_kind="distance"`
(per DEC-096's own pre-documented naming; declared for registry
completeness only — the service resolves via `compute_phasor_diagram()`,
never a second `resolve_analysis_inputs()` call).

Engineering Context phase-role resolution uses the durable phase
identities `compute_phasor_diagram()` itself resolves — never inferred
from channel names.

## Mho characteristic

Standard forward mho circle: diameter from the origin (0,0) to
`Z_reach = reach_ohm ∠ characteristic_angle_deg`.

```text
center = Z_reach / 2
radius = reach_ohm / 2
Operated iff |Z - center| <= radius + tolerance
```

`ZONE_BOUNDARY_TOLERANCE_OHM = 1e-6` — the boundary itself counts as
Operated (recommended inclusion, documented here and in
`mho_zone_operated()`'s own docstring). Verified for both `angle=0°`
(axis-aligned) and a non-zero `angle=80°` (rotated) case: clearly
inside/operated, exactly-on-boundary, clearly outside/not-operated, and
a reverse-side point (never operates) — see
`TestMhoCharacteristicGolden`.

Minimum v1 settings per zone: Enabled, Reach `|Z|` (Ω), Characteristic
angle (°), Configured delay (s).

## Quadrilateral characteristic — chosen parameterization, documented

**Generic, non-vendor-specific.** A coherent, self-derived geometry (not
copied from any vendor's proprietary setting model): rotate R/X into a
coordinate system aligned with the characteristic/directional angle,
then apply an axis-aligned rectangle in THAT rotated frame.

```text
theta = characteristic_angle_deg
x' = R*cos(theta) + X*sin(theta)     (along the reach direction)
r' = R*sin(theta) - X*cos(theta)     (perpendicular to it)

Operated iff 0 <= x' <= reactive_reach_ohm
        AND -resistive_reach_reverse_ohm <= r' <= resistive_reach_forward_ohm
```

At `theta = 90°` this degenerates exactly to the classic axis-aligned
box (`0 <= X <= reactive_reach`, `-resistive_reverse <= R <=
resistive_forward`) — verified directly in
`TestQuadrilateralCharacteristicGolden`. A non-90° angle genuinely
rotates the boundary rather than silently behaving like the axis-aligned
case — proven in `TestQuadrilateralRotatedAngle` by cross-checking
against the rotation formula independently at `theta=60°`.

Minimum v1 settings per zone: Enabled, forward reactive reach (Ω),
forward resistive reach (Ω), reverse resistive reach (Ω),
characteristic/directional angle (°), Configured delay (s).
`characteristic_angle_deg` is deliberately the SAME shared field Mho
uses (`ZoneSettings`'s own single angle field) — by this module's own
coherent choice, Mho's classic characteristic angle and Quadrilateral's
reactance-line-tilt/directional angle are the SAME physical angle
concept, never two separate settings; this is also what lets
characteristic switching "preserve relevant shared settings where
sensible" (owner requirement) with zero extra plumbing.

Golden zone-state coverage for BOTH characteristics: clearly operated,
exactly on boundary, clearly not operated, a negative-R case, a
negative-X case — supporting all four quadrants mathematically even
though the forward characteristic itself primarily occupies one region
(`TestQuadrilateralCharacteristicGolden`).

## Zone priority — none; independent evaluation

Zone 1/2/3 are evaluated **completely independently** — more than one
MAY legitimately report Operated simultaneously in a nested
characteristic; Zone 2/3 are never suppressed because Zone 1 operates
(`TestEvaluateZoneState::test_multiple_zones_can_independently_operate`,
and the equivalent API/Playwright regression). No "fastest operated
zone" derived summary exists in v1 (a straightforward addition on top of
this same independent-evaluation foundation if a future slice wants it).

## Operated/Not-Operated terminology — owner decision, never Inside/Outside

**`Operated`/`Not Operated`**, explicitly NEVER `Inside`/`Outside`, for
the primary displayed zone state. `Operated` means the calculated loop
impedance satisfies/breaches the configured zone operating
characteristic GEOMETRICALLY. It does **not** mean relay trip output
asserted, breaker opened, or full relay logic completed. This
distinction is kept explicit in the Results panel copy and this
document; `backend/tests/test_frontend_distance_protection_analysis.py::
TestDistanceOperatedTerminology` guards both the terminology itself and
the absence of any "Relay tripped"/"Trip issued"/"Breaker opened" string
anywhere in the Distance Protection frontend code.

## Configured delay — informational only, never a timer

`ZoneResult.delay_s` (frontend: `Configured delay (s)`) is stored/
displayed per zone but v1 does NOT accumulate a timer, does NOT declare
a timer elapsed, and does NOT declare a trip. A later version MAY add
element-operated → timer-running → timer-elapsed → trip-asserted logic —
NOT now, and not coupled into this module.

## Impedance basis — Primary/Secondary, reusing Impedance Locus's conversion verbatim

An explicit, independent "Impedance basis (Primary|Secondary)" OUTPUT
basis (task's own "N independent bases for N independent physical
quantities" principle, extended: Voltage + Current = 2 independent
INPUT bases, Impedance = a 3rd independent OUTPUT basis — identical
shape to Impedance Locus's own precedent). `app.domain.impedance.
convert_impedance_basis()` is reused **verbatim**, both for Recording
(`recording_basis` → `impedance_basis`) and Manual
(secondary-canonical → `impedance_basis`) — no duplicated ratio math
anywhere in this module.

## Low-current guardrail — reused/adapted from Impedance Locus

`compute_loop_impedance()` calls `compute_impedance_point()` unchanged,
so the loop's own differential current (`Ia - Ib`, etc.) is subject to
the EXACT SAME `MIN_CURRENT_A` numerical-validity floor Impedance
Locus's own guardrail uses — `REASON_LOOP_CURRENT_TOO_SMALL` /
`"Loop current too small for reliable impedance calculation."`.
Numerical validity only, never a relay pickup threshold — the identical
non-claim Impedance Locus's own `MIN_CURRENT_A` docstring already makes.

## Manual Input / Calculator mode — standalone, per-loop phase pair only

Reuses the shared Analysis Input Source shell (`WW_ANALYSIS_INPUT_
SOURCE_RECORDING`/`WW_ANALYSIS_INPUT_SOURCE_MANUAL`) and the three-
region markup separation (always-visible Input Source toggle /
Recording-only section / always-visible Body) verbatim, implemented
correctly from day one (mirrors Impedance Locus's/Sequence Components'
own precedent — see [ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md)).
Fully standalone: no recording/context/Playback/Related-Waveforms
dependency whatsoever. If no recording exists, Manual is auto-selected;
Recording stays visible but disabled, with a hint, mirroring every prior
analyzer's identical empty-workspace behavior.

**Only the selected loop's own relevant phase PAIR is ever asked for**
(e.g. AB needs only Va, Vb, Ia, Ib — never phase C) —
`WW_DISTANCE_LOOP_ROLES` on the frontend and `evaluate_manual_distance()`
on the backend both key off the same `(V1, V2, I1, I2)` 4-leg shape, not
the full six-role Manual Phasor form Phasor/Sequence Components each use.
`wwDistanceUpdateManualRoleLabels()` relabels the two Voltage and two
Current fields live whenever the loop changes.

**Two independent bases total** (Voltage, Current — the same "N
independent bases for N independent physical quantities" principle),
each SHARED by its own loop's two legs (e.g. AB's Va/Vb share ONE
Voltage basis+VT ratio) — never four independent per-leg bases. Backend:
`convert_manual_magnitude_to_secondary()` (`app.domain.phasor`) is
reused verbatim per leg — the SAME Manual Phasor normalization, never a
duplicated conversion formula. A missing/invalid leg is reported
directly (`DISTANCE_STATUS_MISSING`/`NEEDS_CONFIGURATION`) — never a
fabricated partial loop impedance; a loop fundamentally needs all four
legs together (mirrors Impedance's own "no partial-role tolerance"
precedent, extended from a V/I pair to four legs).

`evaluate_manual_distance()` reuses `compute_loop_impedance()` internally
(itself reusing `compute_impedance_point()`), so Recording and Manual
share the exact same loop-impedance/zone-evaluation code — this is the
ONE authoritative loop-impedance implementation for both input sources.

## Results panel — Loop / Basis / R / X / |Z| / Angle, then a separate Zone State section

```text
Loop            Zab
Basis           Secondary
R               9.40 Ω
X               3.42 Ω
|Z|             10.00 Ω
Angle           +20.00°

ZONE STATE
Zone 1          Not Operated    delay 0.00s
Zone 2          Operated        delay 0.40s
Zone 3          Not Operated    delay 1.00s
```

The Zone State section is deliberately SEPARATE from the geometric
R/X/|Z|/Angle block above it — geometric measurement and zone element
state are never mixed into one undifferentiated list. Zone rows always
render (even with all three zones Disabled), so the section is never
structurally empty.

## Related Waveforms — the selected loop's own four source quantities

`AB -> Va, Vb, Ia, Ib` / `BC -> Vb, Vc, Ib, Ic` / `CA -> Vc, Va, Ic, Ia`,
via the existing shared Related Waveforms component
(`wwAnalysisSetRelatedWaveformRoles()`). Gated on channel IDENTITY being
known (`v1_channel_ref`/`v2_channel_ref`/`i1_channel_ref`/
`i2_channel_ref`, populated independent of `status` — mirrors
`ImpedanceAnalysisResult`'s own precedent), never on whether the loop
impedance itself computed, so an engineer diagnosing a
`loop_current_too_small` result still sees the underlying traces. Manual
mode declares zero active roles — double-enforced by the Recording-only
anchor's own parent being hidden.

## R-X plot — reuses Impedance Locus's coordinate transform verbatim

`wwDistanceRenderPlot()` reuses `WW_IMPEDANCE_PLOT_RADIUS`,
`wwImpedanceNiceLimit()`, and `wwImpedanceFormatTick()` from Impedance
Locus's own module directly — the SAME equal-scale (`toSvg = (r, x) =>
[r * pxPerOhm, -x * pxPerOhm]`) coordinate transform, one shared
`pxPerOhm` factor for both axes, never a second inconsistent renderer.
The auto-viewport additionally considers each enabled zone's own reach
extent (`wwDistanceZoneReachExtent()`) alongside the plotted points, so
the active zone characteristics are never clipped out of view. R =
horizontal, X = vertical, all four quadrants (never clamped to one).

Mho zones draw as a true SVG `<circle>` (mathematically guarantees
circularity — never an ellipse via independent axis scaling); Quadrilateral
zones draw as a 4-point SVG `<polygon>` built by mapping the rotated
rectangle's own four corners back to R/X via the inverse rotation
(`R = x'*cos(theta) + r'*sin(theta)`, `X = x'*sin(theta) - r'*cos(theta)`)
before the shared `toSvg` transform. Zone boundaries use the SAME
`--ww-dist-zone1/2/3` color tokens as their own Zone Settings card
(strongest→lightest visual hierarchy — see "Zone colors" below), drawn
Zone 3 → Zone 2 → Zone 1 (Zone 1, the "strongest," painted last/on top).
The current point renders with a distinguishing stroke
(`.ww-dist-point--operated`) whenever ANY zone reports Operated —
deliberately not alarm-red (`--error` stays reserved for genuine
problems app-wide; Operated here is a geometric statement, not an alarm).

## Zone colors — restrained, strongest → lightest

New `frontend/theme.css` tokens `--ww-dist-zone1`/`--ww-dist-zone2`/
`--ww-dist-zone3` — a single-hue slate family (distinct from
`--ww-phase-a/b/c`, `--ww-seq-positive/-negative/-zero`, and `--error`),
Zone 1 strongest, Zone 2 medium, Zone 3 lightest, expressed as
darker→lighter slate in Light mode and lighter→darker (brightened for
dark-surface contrast, same pattern every other dual-theme token in this
file already uses) in Dark mode. Deliberately restrained — never an
arbitrary bright/alarm color.

## Zone Settings UI — compact 3-card responsive grid

`.ww-dist-zone-grid` (`grid-template-columns: repeat(3, minmax(0, 1fr))`,
falling back to one column via the same container-query pattern
`.ww-oc-settings-grid` already established, scoped to the settings
panel's own width) — never a huge vertically-stacked form. Each zone is
one compact card (Enabled / Configured delay / Characteristic angle,
then the characteristic-specific reach field(s)); characteristic
switching shows/hides only the Mho-only vs. Quadrilateral-only fields
(`wwDistanceUpdateCharacteristicFieldsVisibility()`) — the shared
Enabled/delay/angle fields are always visible for both.

## Playback

Recording mode mounts the SAME reusable Playback control surface every
other analyzer mounts — Distance Protection is the FIFTH consumer of the
ONE shared `wwPlayback` controller (DEC-085). `wwDistanceOnPlaybackTick()`
mirrors every prior analyzer's own exact shape: gates on
`wwDistanceState.activeTimeGroupId`/`isOurGroup`, syncs the mounted
transport UI regardless of input source, drives the `/distance-
protection` current-point fetch pipeline (throttled ~10 Hz while
playing, exact/non-throttled on Pause/Restart/seek-commit) only while
Recording is active. Manual mode is fully Playback-independent.

**Recording trajectory** reuses the Impedance Locus locus concept
exactly: the full selected-loop locus is calculated/cached upfront via
`/distance-protection-locus` (signature-based invalidation,
`wwDistanceLocusSignature()`, deliberately EXCLUDING zone/characteristic
settings from the signature — see below), future points hidden, the
visible trail clipped to `wwDistanceVisibleLocusCutoffTime()` (the
current exact-fetch point's own `analysis_time`, the identical
chronological-reveal fix Impedance Locus's own hardening pass
established), current point highlighted. Zones remain static while the
trajectory moves underneath them — no per-frame full-locus backend
fetch, no analyzer-specific timer.

**Locus points intentionally carry NO zone state** (`DistanceLocusPoint`
has no `state` field at all) — only the CURRENT Playback-driven point
(from `/distance-protection`) drives `Operated`/`Not Operated`; the
static trajectory itself is measurement/visualization only. A zone-
SETTING change (reach/angle/enabled/delay) therefore never invalidates
or re-fetches the 120-point locus — only the current-point result (whose
own `zone1/zone2/zone3` fields must reflect the new settings) and the
plot's own static zone-geometry redraw are needed; re-fetching the whole
locus on every keystroke would be exactly the wasteful behavior the
task's own "no per-frame/no redundant backend fetch" guardrail forbids.
(This was caught and fixed during this slice's own Playwright hardening
— see `wwDistanceHandleZoneSettingChanged()`'s own comment.)

**Zone operation during Playback is instantaneous, never latched**: as
the locus crosses a zone boundary, `Not-Operated -> Operated` (and back)
updates at the CURRENT Playback point immediately — v1 has no
relay-latching logic at all (a later, separate enhancement).

## API

```text
GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/distance-protection
    ?loop=AB&analysis_time=1.5&characteristic=mho
    &recording_basis=secondary&impedance_basis=secondary
    &vt_primary=...&vt_secondary=...&ct_primary=...&ct_secondary=...   (only when bases differ)
    &zone1_enabled=true&zone1_reach_ohm=10&zone1_characteristic_angle_deg=0&zone1_delay_s=0
    &zone2_...  &zone3_...                                             (identical shape per zone)
    &reference_frequency_hz=50.0   (optional override)

GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/distance-protection-locus
    ?loop=AB&start_time=0&end_time=2&point_count=120&characteristic=mho
    &recording_basis=secondary&impedance_basis=secondary
    &zone1_...&zone2_...&zone3_...   (accepted for API-shape symmetry with the current-point
                                       endpoint; locus points themselves carry no zone state)

GET /api/v1/workspaces/{workspace_id}/distance-protection-manual
    ?loop_label=AB&voltage_basis=secondary&current_basis=secondary&impedance_basis=secondary
    &characteristic=mho
    &vt_primary=...&vt_secondary=...&ct_primary=...&ct_secondary=...   (only when voltage_basis=primary)
    &v1_enabled=true&v1_magnitude=100&v1_unit=V&v1_angle_deg=0
    &v2_enabled=true&v2_magnitude=100&v2_unit=V&v2_angle_deg=-120
    &i1_enabled=true&i1_magnitude=10&i1_unit=A&i1_angle_deg=-20
    &i2_enabled=true&i2_magnitude=10&i2_unit=A&i2_angle_deg=-140
    &zone1_...&zone2_...&zone3_...
```

All three defined in `app/api/v1/engineering_contexts.py` (same router
file/nesting convention every prior analyzer's own endpoints already
established) — mirrors `.../impedance`/`.../impedance-locus`/
`.../impedance-manual` exactly, extended with the per-zone query-
parameter group (`_zone_settings()` local helper builds a `ZoneSettings`
from the seven flat query params per zone, avoiding 21 hand-repeated
lines per endpoint).

## Response shape

```text
DistanceAnalysisResultOut / ManualDistanceResultOut
├── status                    computed | needs_configuration | missing | ambiguous | not_eligible
├── (Recording only) engineering_context_id, loop, analysis_time,
│   reference_frequency_hz, window_seconds
├── (Manual only) loop_label
├── recording_basis, impedance_basis, vt_primary/secondary, ct_primary/secondary
├── algorithm_version          "distance_protection_v1" | "distance_protection_manual_v1"
├── (Recording only) v1_channel_ref / v2_channel_ref / i1_channel_ref / i2_channel_ref  (nullable)
├── voltage_unit, current_unit
├── resistance_ohm / reactance_ohm / magnitude_ohm / angle_deg   (nullable)
├── characteristic              "mho" | "quadrilateral"
├── zone1 / zone2 / zone3: ZoneResultOut
│     ├── zone_key              "zone1" | "zone2" | "zone3"
│     ├── enabled
│     ├── state                 "operated" | "not_operated"
│     └── delay_s
├── (Recording only) warnings[]
├── reason_code, message

DistanceLocusOut
├── engineering_context_id, loop
└── points[]: DistanceLocusPointOut
      ├── analysis_time, status
      └── resistance_ohm / reactance_ohm / magnitude_ohm / angle_deg / reason_code
      (no zone state -- only the current point drives Operated/Not-Operated)
```

`ManualDistanceResultOut` omits `engineering_context_id`/`analysis_time`/
`reference_frequency_hz`/`window_seconds` (mirrors `ManualImpedanceResultOut`'s
own field-omission rationale).

## Frontend — Input Source shell reuse

`wwDistanceState` mirrors `wwImpedanceState`'s own shape closely
(`contexts`/`selectedContextId`/`lastLoadedContextId`/`analysisTime`/
`anchorDisplaySourceId`/`activeTimeGroupId`/`loop`/`characteristic`/
`settings`/`zones`/`latestResult`/`requestGeneration`/`locusPoints`/
`locusSignature`/`locusRequestGeneration`/`inputSource`/
`recordingAvailable`/`inputSourceAutoSelected`/`manual`/
`manualRequestGeneration`). Every generic helper is reused verbatim
rather than duplicated: `wwPhasorFetchJson()`,
`wwPhasorComputeInitialClaimTime()`, `wwPhasorRoleColor()` (for the
source Va/Vb/Ia/Ib-style Related-Waveforms roles), `WW_IMPEDANCE_PLOT_
RADIUS`/`wwImpedanceNiceLimit()`/`wwImpedanceFormatTick()` (R-X plot
scale). Registers as an Engineering Context consumer
(`wwAnalysisRegisterContextConsumer({ onContexts:
wwDistanceOnAnalysisContexts, ... })`) and a Playback tick subscriber
(`wwPlaybackOnTick(wwDistanceOnPlaybackTick)`) in the Init wiring
section, alongside every other analyzer — never its own
`wwDistanceLoadContexts()`/`wwDistanceDiscoverUncoveredSources()`
bootstrap.

## Recording/Manual state isolation

Manual values/settings never overwrite Recording-derived values and
vice versa: `wwDistanceState.latestResult` (Recording) and
`wwDistanceState.manual.latestResult` (Manual) are two entirely separate
fields, each rendered by its own function
(`wwDistanceRenderResult()`/`wwDistanceRenderManualResult()`, both
gated on `wwDistanceState.inputSource` from their very first line).
**By intentional design, Loop/Characteristic/Zone settings ARE shared**
between Recording and Manual (`wwDistanceState.loop`/`.characteristic`/
`.zones` are single fields, not per-input-source copies) — an engineer
configuring "AB, Mho, Zone 1 reach 10 Ω" expects that SAME relay
configuration to apply whether they are studying a live recording or
running a quick manual what-if calculation; only the measured
V/I/R/X/|Z|/angle results themselves are input-source-specific. See
`browser-tests/distance_protection_analysis.spec.js`'s own "Recording/
Manual state isolation" suite for the end-to-end proof.

## Known limitations / explicitly deferred (not this slice)

- No AG/BG/CG ground loops, no residual-current (k0)/zero-sequence
  compensation, no memory/negative-sequence polarization, no load
  encroachment, no power swing blocking, no directional supervision
  beyond the characteristic itself, no relay trip output, no breaker
  operation, no timer accumulation, no vendor-specific relay logic, no
  fault classification (see "Scope of v1" above — a permanent boundary
  for this feature, not a temporary gap).
- No "fastest operated zone" derived summary (a straightforward addition
  on the existing independent-zone-evaluation foundation).
- No automatic cross-source Engineering Context merging, no manual
  Engineering Context creation/editing UI (unchanged, project-wide
  deferrals every prior analyzer also inherits).
- No Per-Unit display mode (engineering units/ohms only).

## Related documents

- [ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md) — the shared
  Recording/Manual shell this reuses.
- [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) — the shared
  Engineering Context lifecycle / Playback / Related Waveforms
  primitives.
- [IMPEDANCE_LOCUS_ANALYSIS.md](IMPEDANCE_LOCUS_ANALYSIS.md) — the
  loop-impedance/basis-conversion/low-current-guardrail/R-X-plot
  foundation this feature reuses directly, and the "separate analyzer"
  conceptual distinction this document restates.
- [SEQUENCE_COMPONENTS_ANALYSIS.md](SEQUENCE_COMPONENTS_ANALYSIS.md) —
  the complex-number (`cmath`) arithmetic convention this feature reuses
  for the Va-Vb loop subtraction.
- [DECISIONS.md — DEC-099](DECISIONS.md#dec-099--distance-protection-v1-the-fifth-analysis-menu-analyzer-mho-and-quadrilateral-zone-characteristic-evaluation-on-phase-phase-fault-loop-impedance)
  — the approval record.
