# Overcurrent Analysis v1

**Status: implemented** — see
[DECISIONS.md — DEC-090](DECISIONS.md#dec-090--overcurrent-analysis-v1-the-second-analysis-menu-analyzer-iec-idmt-characteristic-evaluation-against-a-one-cycle-trailing-rms-current-at-the-shared-playback-driven-analysis-time).
Overcurrent is the **second** analyzer in the reusable Analysis workspace
(Phasor is the first — see [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)). This
document records the engineering definition and architecture this slice
established, mirroring how PHASOR_ANALYSIS.md documents its own slice, so
a later analyzer (Impedance Locus/Differential/Sequence Components) does
not need to re-derive the same resolver/Playback/Analysis-shell
integration pattern.

## Product definition — what Powerwave means by "Overcurrent Analysis"

> Powerwave evaluates a recorded event's own one-cycle trailing RMS
> current, at a selected/Playback-driven instant, against a CONFIGURED
> IEC IDMT (Inverse Definite Minimum Time) protection characteristic.

This is **recorded-event analysis against a configured characteristic**.
It is explicitly **NOT** a claim to reproduce a physical relay's own
internal filters, timing accumulator, reset algorithm, manufacturer
tolerances, or proprietary logic. Powerwave never reports "relay
operated," "relay tripped," "relay should have tripped," or "relay
failed to trip" — only:

- **Expected operating time** — a characteristic-derived figure computed
  from the PRESENT measured RMS current only. Never accumulates/
  integrates across a variable-current history.
- **Above-pickup duration** — an event-recording-derived measurement of
  how long the recorded current has continuously stayed above pickup.

These two concepts are kept explicitly separate everywhere in this
feature — a qualified "threshold exceeded" observation compares them at
the present operating point only; it is never a relay-operation claim.

## Standard / formulation

IEC 60255-151:2009 ("Measuring relays and protection equipment — Part
151: Functional requirements for over/under current protection"), the
current edition of the dependent-time (IDMT) overcurrent characteristic
originally published as IEC 60255-3:1989 (itself descended from the
legacy BS 142 curve definitions):

```
t = TMS * (k / ((I / Is)^alpha - 1) + c)
```

`t` = operating time (s), `TMS` = Time Multiplier Setting, `I` = measured
current, `Is` = pickup/current setting, `k`/`alpha`/`c` = curve-defining
constants (`k`/`c` in seconds, `alpha` dimensionless). `c = 0` for all
three curves this slice supports.

**Constants** (cross-verified against multiple independent secondary
sources describing the IEC 60255 curve table — the primary IEC standard
text itself is not freely reproducible here — since this project's own
implementation could not rely on remembered constants alone per the
task's own explicit instruction):

| Characteristic | `k` | `alpha` |
|---|---|---|
| IEC Standard Inverse | 0.14 | 0.02 |
| IEC Very Inverse | 13.5 | 1.0 |
| IEC Extremely Inverse | 80.0 | 2.0 |

Sources cross-checked (web search, this session): an ABB relay technical
reference manual (REJ 523), an OPAL-RT HYPERSIM protection-block
documentation page, the European Arc Guide's own IDMT relay guide, and
several independent IDMT trip-time calculator references — all agree on
the same `k`/`alpha` values and the same general formula shape (also
noted as matching IEEE C37.112's own equation form, with different
constants). **Verified numerically**: the Standard Inverse worked
example independently found during this cross-check (11 kV feeder,
pickup 100 A primary, fault current 2000 A primary → M=20, TMS=0.10) —
expected `t ≈ 0.2267 s` — reproduced exactly
(`0.226736…`) by `evaluate_idmt_operating_time()`, a genuine independent
verification, not a value re-derived from the implementation itself. See
`backend/tests/test_overcurrent_domain.py::TestIdmtOperatingTime` for
the full golden-value test suite.

IEC 60255-151 Annex A also defines Long Time Inverse (`k=120,
alpha=1.0`) and the standard additionally cross-references ANSI/IEEE
C37.112 curves with their own constants — both are explicitly **out of
this v1's scope** (see "Not yet implemented" below).

## Below-pickup semantics

`M = I / Is <= 1` has no finite theoretical operating time (the
characteristic's own denominator `M^alpha - 1` is non-positive) —
`evaluate_idmt_operating_time()` returns `None`, **never**
`Infinity`/`NaN`/`0`. The frontend renders this as an explicit "Below
pickup — —" value, never a fabricated number.

## Extensible characteristic model

`OvercurrentCharacteristicDefinition` (`app/domain/overcurrent.py`) is a
small, explicit, closed registry — owner instruction: "a simple explicit
registry/definition model is sufficient... do not overengineer a plugin
framework." Each entry names its own `family` (`"iec_idmt"` today),
`display_name`, and `IdmtConstants` (`k`/`alpha`/`c`). Adding a future
characteristic (e.g. IEC Long Time Inverse, or an ANSI/IEEE curve) is
adding one more module-level constant to this registry — mirroring
`app.domain.analysis_requirements`'s own established registry precedent
— **not** a redesign of the analyzer. `evaluate_idmt_operating_time()`
itself is specific to the IEC IDMT formula shape above; a future
genuinely different formulation (e.g. definite time, which has no
current-dependent curve at all) would need its own evaluation function
alongside a `family` discriminator — an intentional, documented
boundary, not an oversight.

## Current role resolution — reuses the existing resolver, unchanged

`app/domain/analysis_requirements.py` gained three new constants —
`OVERCURRENT_CURRENT_PHASE_A/B/C` — reusing the **identical**
single-phase-current `RoleSpec` shape Phasor's own
`PHASOR_CURRENT_PHASE_A/B/C` already established (same `_current_role`
helper, same `Ia`/`Ib`/`Ic` role keys), just under a distinct
`analysis_kind="overcurrent"`. The existing, unchanged
`resolve_analysis_inputs()` (`app.services.
analysis_input_resolution_service`) is called with these requirements
exactly the way Phasor already calls it — **no new resolver, no
frontend channel-name parsing, no weakened ambiguity safeguards**. A
context with multiple candidates satisfying the same role still resolves
`ambiguous`, verbatim passed through to the caller. A partial Engineering
Context (e.g. only Phase A's own current member exists) remains fully
valid for that one phase.

## One-cycle trailing RMS — a NEW selected-time estimator, not `evaluate_rms()` reused directly

**Investigated first, per the task's own explicit instruction**:
`app.domain.calculated_channel.evaluate_rms()` already implements
exactly the required window semantics — half-open trailing interval
`(t - T, t]`, `T = 1/reference_frequency_hz` — but its own INTERFACE is a
whole-array SLIDING-window evaluator (one output per INPUT sample), never
a selected-single-time evaluator for an arbitrary continuous
Playback-driven `analysis_time` that generally falls BETWEEN samples.
This is the exact gap `app.domain.phasor.estimate_phasor()` already
solved for Phasor's own selected-time need.

**`estimate_trailing_rms_at_time()`** (`app/domain/overcurrent.py`)
therefore mirrors `estimate_phasor()`'s own window/guardrail SHAPE
exactly (identical half-open window, identical boundary-epsilon/
regular-spacing/minimum-density guardrails, identical `available`/
`reason_code` result shape) — but computes `sqrt(mean(x^2))` (true RMS)
instead of a phasor correlation sum, since Overcurrent needs a scalar
CURRENT MAGNITUDE, never a magnitude+angle. `OVERCURRENT_MIN_SAMPLES_
PER_CYCLE = 4` reuses `calculated_channel.MIN_SAMPLES_PER_CYCLE`'s own
value (a plain RMS magnitude's own accuracy needs), deliberately **not**
Phasor's stricter 8-samples-per-cycle bound (tuned for phasor ANGLE
accuracy, a different concern).

**`continuous_duration_above_pickup()`**, a SEPARATE sub-problem, DOES
reuse `evaluate_rms()`'s own ARRAY form directly — this genuinely needs
the RMS value at EVERY sample time up to `analysis_time` to find where
the current last crossed below pickup, exactly the shape `evaluate_
rms()` already provides. It is a pure function of `analysis_time` and
the full recorded array — **deterministic for any seek**, never
path-dependent on "how long Play has been pressed," and **never affected
by Playback speed** (owner's own explicit requirement, verified directly
by `backend/tests/test_overcurrent_domain.py::TestContinuousDurationAbovePickup`).
Resets to `0.0` the instant the current is at or below pickup. Cannot
claim a duration further back than there is trailing-RMS data for — the
earliest sample with a valid RMS value is treated as the onset of an
already-ongoing episode, never silently extended further back than the
data actually supports.

## Reference frequency

Identical disciplined philosophy to Phasor: an explicit
`reference_frequency_hz` override (validated via the existing,
unchanged `nominal_frequency_valid()`), else the resolved current role's
own source-declared `nominal_frequency` (never hard-coded to 50 Hz — 50
Hz and 60 Hz are both exercised in the test suite). Since Overcurrent
resolves exactly ONE role (unlike Phasor's multi-role requirements),
there is no cross-source frequency-AGREEMENT check to perform — only the
override-validity check applies.

## Waveform-form eligibility

Mirrors `phasor_analysis_service._waveform_form_eligible()`'s own
structure and STRICT policy exactly (trusted `instantaneous` metadata
passes; explicit `rms`/`magnitude` fails with no override; `unknown`
metadata falls back to the existing `app.domain.rms_detector.
classify_waveform_form()` detector, with `UNCERTAIN` REJECTED — there is
no override mechanism anywhere in this v1's read-only, selected-time
analysis, the same reasoning Phasor's own docstring already establishes).

## Pickup basis and CT conversion

**Pickup is always specified in relay-secondary amperes** — an explicit,
unambiguous basis (owner instruction: "do not leave the pickup basis
ambiguous... do not implement `% plug setting` yet"). The engineer
separately declares whether the RECORDING itself represents primary or
secondary current (`recording_basis`):

- **`recording_basis = "secondary"`** — no conversion; the recorded
  current IS already what the relay would see. `relay_secondary_current
  == measured_rms_current` numerically, so the UI never misleadingly
  implies a CT conversion occurred that didn't.
- **`recording_basis = "primary"`** — requires `ct_primary`/
  `ct_secondary` (both validated `> 0`, both finite) and computes
  `relay_secondary_current = recorded_current * (ct_secondary /
  ct_primary)`.

`ct_primary`/`ct_secondary` must already be expressed in the SAME base
unit as the resolved current channel's own declared `unit` — mirrors how
Phasor never separately re-units a channel's own `magnitude_rms` (the
raw channel value is used directly; any kA-style display prefixing is a
FRONTEND `wwFormatEngineeringValue()` concern, exactly like Phasor's own
Voltage/Current magnitudes, never a backend unit-normalization step).

## Runtime calculation (selected-time only, never a time series, never persisted)

```
recorded waveform
        v
one-cycle trailing RMS (estimate_trailing_rms_at_time())
        v
recording-basis conversion (convert_to_relay_secondary())
        v
relay-equivalent secondary current
        v
M = Irelay / Ipickup
        v
selected IEC IDMT equation (evaluate_idmt_operating_time())
        v
expected operating time (None if M <= 1)
```

`continuous_duration_above_pickup()` runs alongside, independently, over
the SAME relay-secondary-converted array (CT conversion is a linear
scalar, applied once to the whole array rather than re-derived per
sample). `threshold_exceeded = above_pickup_duration_seconds >
expected_operating_time_seconds` (only when both are available) — the
one and only "alert" this feature computes, always qualified in its own
UI wording (see "Explicit non-emulation boundary" below).

## Guardrails — every failure mode returns a result, never a fabricated value

Reject or clearly report (as an `OvercurrentAnalysisResult` with an
explicit `status`/`reason_code`, mirroring `PhasorAnalysisResult`'s own
never-raise-for-a-guardrail-failure precedent): missing current role,
ambiguous current role, an ineligible waveform representation, invalid
pickup/TMS/CT values, an unrecognized characteristic id, an invalid
reference-frequency override, insufficient RMS window history/sampling
density, and an analysis time outside the usable range. `TMS` is bounded
`0.025`–`1.2` — a typical/practical application guardrail commonly cited
across IDMT relay manufacturer documentation (cross-checked during this
implementation), **never** claimed as an IEC 60255-151-mandated numeric
bound (mirroring how `PHASOR_MIN_SAMPLES_PER_CYCLE` is honestly framed
as an application guardrail elsewhere in this codebase).

## Result model

```
OvercurrentAnalysisResult (app.domain.overcurrent)
├── status                          "computed" | resolver's own pass-through statuses
├── engineering_context_id, phase, analysis_time   (echoed)
├── characteristic_id, tms, pickup_current_secondary,
│   recording_basis, ct_primary, ct_secondary       (echoed)
├── reference_frequency_hz, window_seconds          (only set when computed)
├── algorithm_version                "overcurrent_idmt_v1"
├── channel_ref
├── measured_rms_current, measured_rms_current_unit  (RECORDED basis/unit)
├── relay_secondary_current                          (always A secondary)
├── multiple_of_pickup
├── expected_operating_time_seconds   (None below pickup -- never fabricated)
├── above_pickup_duration_seconds
├── threshold_exceeded                (qualified observation only)
├── warnings[], reason_code, message
```

A concrete, Overcurrent-owned shape — never persisted, never a generic
cross-analysis framework (matching Phasor's own established precedent).

## API

```
GET /api/v1/workspaces/{workspace_id}/overcurrent-characteristics
    -- static registry metadata (id/family/display_name/k/alpha/c/source),
       never context-nested since it depends on nothing workspace-specific

GET /api/v1/workspaces/{workspace_id}/overcurrent-curve
    ?characteristic_id=iec_standard_inverse&tms=0.1
    -- characteristic curve geometry (log-spaced M -> t points), depends
       ONLY on characteristic/TMS, never analysis_time -- the frontend
       fetches this ONLY when those two settings change, never on every
       Playback tick (owner instruction: "avoid shipping thousands of
       redundant curve points on every Playback tick")

GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/overcurrent
    ?phase=A&analysis_time=1.234&characteristic_id=iec_standard_inverse
    &tms=0.10&pickup_current_secondary=1.0&recording_basis=secondary
    (&ct_primary=1000&ct_secondary=1, required only when recording_basis=primary)
    (&reference_frequency_hz=50.0, optional override)
    -- the one selected-time calculation endpoint, identical URL-nesting
       convention as .../phasor
```

Registered in the SAME router file/module as the Phasor endpoints
(`backend/app/api/v1/engineering_contexts.py`) — the established
convention that analysis-derived-view endpoints nest under the
Engineering Context router rather than get their own top-level router;
the two metadata endpoints are workspace-scoped siblings of the
context-nested calculation endpoint, following the exact same router
prefix (`/api/v1/workspaces/{workspace_id}`). No new `include_router`
call was needed.

## Performance (measured, not assumed)

Measured directly against the real FastAPI `TestClient` during
implementation (the same "measure first, optimize later" discipline
Phasor's own documentation already established) — full request/response
round trips for `.../overcurrent`, `.../overcurrent-curve`, and
`.../overcurrent-characteristics` all complete well within the existing
~10 Hz (100 ms) Playback-throttle window this feature reuses unchanged
from Phasor's own precedent; no caching/precomputation beyond the
frontend's own curve-geometry cache (recomputed only on a characteristic/
TMS change, never per tick) was needed for acceptable responsiveness.

## Frontend: the second Analysis-menu analyzer

**Overcurrent is the second entry in the reusable Analysis shell's own
analyzer nav** (`.ww-analysis-type-nav`) — Phasor remains the first,
completely unaffected. `wwSetActiveAnalysisType(type)` is the one shared
switcher both analyzer nav buttons call, toggling nav-button active state
AND the matching panel's own `hidden` attribute
(`wwAnalysisPanelsByType = { phasor: "wwPhasorPanel", overcurrent:
"wwOvercurrentPanel" }`) — a future third analyzer adds its own button/
panel plus one more `panelsByType` entry, never a restructure of this
function.

**A real, caught defect**: `.ww-phasor-panel`/`.ww-phasor-field` both use
an explicit `display: flex` (from the Analysis-shell visual-polish
pass), which silently overrides the browser's own default `[hidden] {
display: none }` rule for the `hidden` ATTRIBUTE `wwSetActiveAnalysisType()`
and `wwOvercurrentUpdateCtFieldsVisibility()` toggle these elements with
— caught directly by real-browser Playwright assertions (not assumed),
fixed with explicit `.ww-phasor-panel[hidden]`/`.ww-phasor-field[hidden]`
overrides, the exact same fix shape `.ww-phasor-body[hidden]` already
needed for the identical reason (see PHASOR_ANALYSIS.md's own "A caught
defect" note).

**Bay/Engineering Context + Phase is the entire input surface** — never
a manual raw-channel picker. `wwOvercurrentState.selectedContextId` is
entirely independent of `wwPhasorState.selectedContextId` (each analyzer
owns its own context selection; switching between them never discards
the other's own selection or settings). **Superseded (2026-09-12 owner
UAT fix)**: Overcurrent used to merely list whatever contexts already
existed via its own `GET .../engineering-contexts` call, deliberately
not re-implementing Phasor's own bootstrap/discovery — this assumed "an
engineer reaching Overcurrent will typically already have a usable
context from visiting Phasor first," which UAT proved false (opening
Overcurrent directly after an upload, without ever visiting Phasor,
left the Bay selector empty). See "Shared Analysis Engineering Context
lifecycle" below for the fix — Overcurrent is now a pure CONSUMER of
the shared, Analysis-workspace-owned context list, exactly like Phasor,
and no longer fetches or discovers contexts itself at all.

**Phase selectability**: v1 keeps all three phases (A/B/C) always
selectable, rather than pre-checking resolver availability with three
extra round trips per context selection. Selecting a phase with no
resolvable current role surfaces the resolver's own `status`/`message`
via the existing `.ww-phasor-status-row` guardrail-reporting pattern
Phasor already established — equivalent guardrail correctness (no
fabricated results, no silent failure) without the extra request
complexity. A future slice could add a lightweight resolver-preview call
per phase if UAT finds this insufficiently discoverable.

### Shared clock, single time control — identical pattern to Phasor

Overcurrent mounts the SAME reusable Playback control surface
(`wwCreatePlaybackControlsHtml()`/`wwWirePlaybackControls()`/
`wwSyncPlaybackControls()`/`wwUpdatePlaybackControlsTick()`, all
unchanged) via `wwOvercurrentMountPlaybackControls(groupId)` — the THIRD
consumer of the ONE shared `wwPlayback` controller (Waveform's own
passive cursor overlay and Phasor's own mount are the other two
established consumers; see [DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock)).
No second Playback controller, timer, or `requestAnimationFrame` loop
was built. `wwOvercurrentOnPlaybackTick()` is the ONE tick subscriber,
registered once at Init via the existing `wwPlaybackOnTick()` seam — an
exact structural mirror of `wwPhasorOnPlaybackTick()`, including the same
"safety net" listeners for the two shared-controller transitions
(Pause/Speed-change) that do not themselves call
`wwPlaybackNotifyTick()`.

**Switching Phasor -> Overcurrent (or the reverse) never creates an
unrelated time position** — both analyzers read the SAME
`wwPlayback.currentTime`/`activeTimeGroupId`; selecting a context whose
own resolved Time Group is ALREADY `wwPlayback`'s active group reads its
current time verbatim (claiming a not-yet-active group reuses
`wwPlaybackRestart()` + the same `wwPhasorComputeInitialClaimTime()`
one-time landing-position convenience Phasor's own first-view logic
already established — a genuinely analyzer-agnostic UX heuristic, reused
directly rather than duplicated, since it reads only `groupId`/`bounds`/
Cursor A, never any Phasor-owned state).

### Throttled, concurrency-safe fetch — identical shape to Phasor

`WW_OVERCURRENT_PLAYBACK_THROTTLE_MS = 100` (~10 Hz), "one request in
flight + latest desired time, never a growing queue" —
`wwOvercurrentMaybeFetchForPlayback()` (used only while playing) vs.
`wwOvercurrentRequestExactPlaybackFetch()` (used for every non-playing
transition AND every discrete settings change — characteristic/pickup/
TMS/basis/CT/phase — treated exactly like a seek: an immediate, exact,
non-throttled re-fetch, since Playback may currently be paused with no
further tick to trigger a refresh otherwise). `wwPlayback.currentTime`
remains the sole authoritative clock throughout — the computation
throttle was never changed merely because Playback speed changed
elsewhere (owner instruction), since neither the throttle nor the
estimator reads `wwPlayback.speed` at all.

### Curve caching — never refetched per tick

`wwOvercurrentState.curveCache` holds `{characteristicId, tms, points}`;
`wwOvercurrentEnsureCurveAndRenderPoint()` only issues a new
`.../overcurrent-curve` request when EITHER setting differs from the
cache — every Playback-driven re-render reuses the already-cached curve
geometry and re-draws only the moving operating point + dashed guides,
directly satisfying "avoid shipping thousands of redundant curve points
on every Playback tick... only update the dynamic operating point where
practical."

### Chart — hand-rolled SVG, log(M) x log(t)

Mirrors Phasor's own `#wwPhasorSvg` precedent (no existing
time-series-chart precedent to reuse for this shape; the geometry is
simple enough that direct SVG element updates are both simpler and
cheaper than a Plotly figure). X axis: Current/Pickup Multiple (M), log
scale; Y axis: Expected Operating Time (s), log scale. The curve itself
renders as one `<path>`; the moving operating point (`<circle>`) and thin
dashed X/Y guide lines to the axes are omitted entirely, without
generating any invalid coordinate, whenever the current instant is below
pickup (`expected_operating_time_seconds === null`) — "handle the visual
state gracefully" per the owner's own instruction. A point outside the
curve's own fixed `[m_min, m_max]` display range is clamped to the
nearest edge rather than distorting the axis scale (the curve's own
range is intentionally fixed per characteristic/TMS, never recomputed to
fit one instant's own M value, since that would defeat the "recompute
only on settings change" caching requirement above) — documented here as
a deliberate v1 display boundary, not a bug: the exact numeric "Multiple
of pickup" value is always shown correctly in the live-values panel
regardless of where the point clamps on the chart.

## Configuration persistence

Settings (`characteristicId`/`tms`/`pickupCurrentSecondary`/
`recordingBasis`/`ctPrimary`/`ctSecondary`/`phase`) live in
`wwOvercurrentState.settings`, in-memory only, for the lifetime of the
current workspace/session — stable across a Playback time change, a
context re-selection, or switching to Phasor and back. Reset only by
`wwOvercurrentResetState()` (the same "Start New Workspace"/"Clear
workspace" hook every other analyzer's own state uses). **No backend
persistence was added** — settings do not survive a page reload or a
new workspace, matching the existing app-wide precedent (Phasor's own
`visibleRoles`/frozen-scale state is equally session-only) and the
task's own explicit "if persistence beyond current workspace/session is
deferred, document that boundary" instruction.

## Explicit non-emulation boundary

Restated here, not just in `app/domain/overcurrent.py`'s own module
docstring, since this is the single most important interpretive boundary
of the whole feature:

- **"Expected operating time"** — CHARACTERISTIC-derived, computed at
  the PRESENT measured RMS current only. Never accumulates/integrates
  across a variable-current history.
- **"Above-pickup duration"** — EVENT-RECORDING-derived, a plain
  measurement of how long the recorded current has continuously stayed
  above pickup.
- **`threshold_exceeded`** — a QUALIFIED comparison of those two numbers
  at the PRESENT operating point only. It is NOT: "the relay operated,"
  "the relay should have operated," or "the relay failed to operate."
  Powerwave does not know a real relay's own internal filters/timing
  accumulator/reset algorithm/manufacturer tolerances/proprietary logic,
  and does not attempt to emulate them. The frontend's own alert wording
  states this explicitly every time it is shown, never abbreviated to a
  bare "threshold exceeded" without the qualifying sentence.
- **Variable-current limitation**: if current changes while remaining
  above pickup, a real IDMT relay may accumulate/reset operating
  progress according to its own implementation. v1 does NOT emulate this
  — "expected operating time" and "above-pickup duration" are kept
  strictly separate concepts for exactly this reason; a future,
  separately-named mathematical characteristic-accumulation ESTIMATE
  (never a relay-emulation claim) may be introduced later if justified,
  not implemented now.

## Chart UX refinement: full axis frame, fixed log grid, below-pickup position marker (2026-09-12)

Visual/chart-readability only — the IDMT equations/constants, resolver
behavior, RMS calculation semantics, CT conversion, and the expected-
operating-time/above-pickup-duration/threshold-alert semantics above are
all byte-for-byte unchanged (see `backend/tests/test_overcurrent_domain.py`/
`test_overcurrent_analysis_service.py`/`test_overcurrent_analysis_api.py`,
all still passing unmodified). The refinement is entirely in
`wwOvercurrentRenderChart()` and its own small set of new geometry
helpers, frontend-only.

**A FIXED axis domain, never derived from the fetched curve's own data
range.** Previously the chart's own log-scale X/Y bounds were computed
from `Math.min`/`Math.max` over the fetched curve points themselves —
meaning the visible axis range silently shifted per characteristic/TMS.
The chart now uses a fixed, owner-specified tick set instead — exactly
like a real printed TCC (Time-Current Characteristic) chart, whose axis
grid never rescales itself per curve:

```
X ticks (Current / Pickup Multiple):  0.1, 0.2, 0.5, 1, 2, 5, 10, 20
Y ticks (Expected Operating Time, s): 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10
```

Grid lines and tick labels are drawn at each of these values' own TRUE
`Math.log10()`-transformed pixel position — never uniformly/linearly
spaced, confirmed directly by
`backend/tests/test_frontend_overcurrent_analysis.py::TestChartAxesGridAndTicks::test_ticks_use_the_log_transform_never_linear_spacing`.

**The visual "0" origin labels are NOT part of the logarithmic
transform.** `log10(0)` is undefined, so a `0` position cannot be
computed the way every other tick is — the owner's own instruction is
explicit that these are visual chart-origin annotations only. A small
fixed-width "origin gap" (`WW_OC_ORIGIN_GAP`) is reserved at the
lower-left of the plot rectangle, entirely OUTSIDE the log-mapped
region; the two `0` labels (one per axis) sit at fixed pixel positions
within that gap, never touched by `Math.log10()`. The real log-mapped
plotting region begins immediately after the gap, at the chart's own
first genuine tick (X: 0.1, Y: 0.01) — matching the owner's own "the
valid log plotting region begins at X:0.1, Y:0.01" instruction exactly.
The full axis frame (the two `.ww-oc-axis` lines) still spans the WHOLE
plot rectangle, including the origin-gap strip, so the chart never looks
visually truncated.

**The curve itself is CLIPPED, never clamped or distorted, at the plot
edges.** A real IDMT curve legitimately runs outside the fixed display
window near `M=1` for a slow TMS (`t -> ` a large value as `M -> 1`) —
exactly like a real printed TCC chart, where curves routinely run off
the visible grid near the origin. The curve path uses the SAME
unclamped pixel-mapping functions the grid/ticks use, then an SVG
`<clipPath>` restricted to the log-mapped plot rectangle cuts it
cleanly at the frame edge — the underlying engineering values (the
actual `points` array from `.../overcurrent-curve`) are never
re-scaled, clamped, or otherwise altered to force the whole curve to
fit.

**Below-pickup visualization — a genuine UX improvement, not a
semantic change.** Previously, `M <= 1` simply omitted the operating
point and both guides entirely. The owner found this insufficient for
locating "where is the current, even below pickup" — the chart now
additionally shows, whenever `currentM` is finite (a real measured
value exists) but `currentT` is `null` (below pickup, no finite
operating time):

- a full-height vertical dashed guide at the current's own (clamped-if-
  necessary) X position, and
- a small marker sitting ON the X axis itself (`.ww-oc-position-marker`
  — deliberately a DIFFERENT class/color than `.ww-oc-operating-point`,
  so it never reads as "a computed result").

**No y-coordinate is ever fabricated** — the below-pickup code path
never calls the Y pixel-mapping function at all (confirmed directly by
`TestBelowPickupPositionMarker::test_below_pickup_never_calls_pixel_y_with_a_fabricated_time`),
and the live-values panel continues to show "Below pickup — —" exactly
as before. If the true `M` value is smaller than the chart's own first
real X tick (0.1), only the MARKER's own pixel position clamps to that
edge — the true numeric `Multiple of pickup` value shown in the
live-values panel is never distorted; only where the dot is drawn is
ever adjusted.

**Above-pickup behavior is otherwise unchanged**: a genuine computed
operating point still renders a filled circle plus X+Y dashed guides to
their own tick coordinates, using the exact same clamp-only-the-marker
policy already established (see "OC chart frame and spacing" — clamping
was already in place before this refinement for a point outside the
curve's own former data-derived range; it now clamps to the new FIXED
tick range instead).

## Adjustable chart viewport — UAT follow-up (2026-09-12)

Owner UAT on the "Chart UX refinement" work above raised six points: the
Phasor axis labels weren't reliably visible (see
[PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)), the chart was capped at 20×
pickup / 10 s with no user control over the visible range, the grid was
too busy, and there was no zoom in/out/reset. This follow-up replaces the
single FIXED tick set described above with a **user-adjustable, but
strictly display-only, viewport** — nothing below changes the IDMT
calculation, pickup, TMS, measured current, CT conversion, expected
operating time, or above-pickup duration; those all remain covered by
the byte-for-byte-unchanged domain/service/API tests referenced above.

**Default viewport and absolute bounds.** `wwOvercurrentState.viewport`
(`{ xMin, xMax, yMin, yMax }`) replaces the old fixed tick arrays as the
chart's source of truth, initialized to and resettable to
`WW_OC_VIEWPORT_DEFAULT = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 }`
— X now defaults to 100× pickup (was 20×) and Y to 100 s (was 10 s). The
user's own X/Y Min/Max inputs and the Zoom Out control are hard-bounded
by `WW_OC_VIEWPORT_ABSOLUTE = { xMin: 0.1, xMax: 200, yMin: 0.01, yMax: 1000 }`
via `wwOvercurrentViewportValid()` — `0.1 <= xMin < xMax <= 200`,
`0.01 <= yMin < yMax <= 1000`, all four values finite. `0` is never a
valid log minimum on either axis. An invalid candidate range is rejected
and every input reverts to the last-known-good viewport (never a
partial/silent apply).

**Dynamic major-tick generation, not a hard-coded table.**
`wwOvercurrentGeneratePow125Ticks()` (X: 1-2-5 engineering progression)
and `wwOvercurrentGenerateDecadeTicks()` (Y: decades) generate the full
candidate tick set for whatever `[min, max]` the CURRENT viewport
defines — default or custom — always through `Math.log10()`, ticks
outside the selected range simply omitted. `wwOvercurrentClassifyMajors()`
then applies one small rule uniformly to both axes: **the axis's own
current minimum is the sole minor/reference tick; every other candidate
value strictly greater than 2× that minimum is major.** This single
dynamic rule reproduces the owner's own curated default lists exactly —

```
X majors (default 0.1 -> 100): 0.5, 1, 2, 5, 10, 20, 50, 100
Y majors (default 0.01 -> 100): 0.1, 1, 10, 100
```

— while remaining generic for any custom viewport (e.g. X 2 -> 20 yields
majors `5, 10, 20`; Y 0.1 -> 10 yields majors `1, 10`). Only the major
set gets a gridline (`.ww-oc-gridline`) — deliberately a simpler grid
than the previous full fixed-tick version, per owner feedback that the
old grid was too busy.

**The "0" origin annotation appears ONLY at the exact default viewport.**
`wwOvercurrentIsDefaultViewport(v)` checks the current viewport for
EXACT equality with `WW_OC_VIEWPORT_DEFAULT`. When true, the chart
reserves the same origin-gap strip the original refinement introduced,
draws the two visual `0` labels in it (still never passed through
`Math.log10()`), and additionally shows the axis's own true minimum
(0.1×/0.01 s) as a lighter `.ww-oc-tick-label-minor` reference label just
inside the real log-mapped region. In ANY custom/zoomed viewport — even
one a user happens to set back to `xMin: 0.1`/`yMin: 0.01` by hand
without pressing Reset — there is no origin gap and no fake `0`; the
viewport's own true minimum renders directly, in normal tick styling, at
the frame edge (e.g. "2" and "0.1 s" for a `X: 2->20, Y: 0.1->10` view) —
the lower-left corner always reflects the actual selected minimum.

**Zoom in/out/reset.** `wwOvercurrentZoom(factor)` (0.5 for Zoom In, 2
for Zoom Out) scales the viewport around its own geometric CENTER in
log-space on both axes simultaneously, then clamps the result to
`WW_OC_VIEWPORT_ABSOLUTE` — centering on the viewport's own midpoint
rather than the current operating point keeps zoom well-defined even
below pickup or before a context is selected. `wwOvercurrentResetViewport()`
returns to `WW_OC_VIEWPORT_DEFAULT` by exact assignment (not an
approximation), which also restores the default major-grid labeling
described above. All three controls, plus the X/Y Min/Max number inputs
(`wwOvercurrentApplyViewportFromInputs()`), are wired to call
`wwOvercurrentSyncViewportInputs()` + `wwOvercurrentRerenderChartFromState()`
only — never `wwOvercurrentHandleSettingsChanged()`, never
`wwPlaybackSeek()`/any other `wwPlayback` mutator, and never
`wwOvercurrentFetchCurve()`. A viewport change is a pure re-render from
whatever curve/result data is already cached in
`wwOvercurrentState.curveCache`/`latestResult` — confirmed directly by
`browser-tests/overcurrent_analysis.spec.js`'s
"viewport changes never alter wwPlayback.currentTime or trigger a new
curve fetch" test, which counts `/overcurrent-curve` network requests
across a zoom-in/zoom-out/reset sequence and asserts zero.

**Curve data now spans the full 200× display domain in one fetch.**
`generate_idmt_curve_points()` (`backend/app/domain/overcurrent.py`)
default `m_max` widened from 20.0 to 200.0 (`num_points` 60 -> 90) — a
display-rendering-support boundary only; `evaluate_idmt_operating_time()`
itself, and every value it can be called with, is unchanged (see
`test_overcurrent_domain.py::TestIdmtCurvePoints::test_default_domain_covers_the_full_200x_display_bound`).
This means every possible zoom/pan the user can reach is drawn from the
SAME already-fetched curve array — the existing "only refetch when
`characteristicId`/`tms` differ from cache" rule (see "Curve caching"
above) is untouched and still the only thing that triggers a network
call; the viewport itself was never part of that cache key and still
isn't.

**Off-chart values (§10/§11): never falsify, never fabricate, never
falsely clamp-and-present as a boundary value.** If the true `M` or `T`
value now falls outside the user's currently selected viewport (whether
below-pickup X-position or an above-pickup operating point), the
marker's PIXEL position still clamps to the visible frame edge, but its
SHAPE changes from a circle to a small outward-pointing
`.ww-oc-edge-indicator` triangle (`wwOvercurrentEdgeArrowSvg()`) instead
— so an edge case is never visually indistinguishable from "the value
genuinely sits at this boundary." The true numeric value shown in the
live-values panel is never touched by any of this; only the marker
drawn on the chart changes. Below-pickup off-chart additionally omits
the full-height vertical guide (its direction would mislead once the
true X position is off-screen). The curve `<path>` itself continues to
be clipped (via the existing `<clipPath>`), never distorted, to
whatever the current viewport's plot rectangle is.

**Persistence — frontend state only, no database.** `viewport` lives on
`wwOvercurrentState` exactly like `settings`/`curveCache` — it survives
a Playback time change, a phase change, and a Phasor<->Overcurrent
switch (nothing in those paths touches it), and resets only on an
explicit Reset-view press or `wwOvercurrentResetState()` (the same full
analyzer-state-recreation hook `settings`/`curveCache`/etc. already
reset on). Per the task's own explicit instruction, **no new database
persistence was added** for this — same boundary as `settings` (see
"Configuration persistence" above).

## Curve/viewport boundary alignment — UAT follow-up (2026-09-12)

Further owner UAT on the adjustable-viewport work directly above: near
pickup, the rendered curve appeared to "start" at a finite time, because
the polyline was built from whichever coarse pre-fetched/pre-sampled
point happened to fall inside the current Y range — not the true
mathematical Y-boundary intersection. **The IDMT characteristic is
mathematically unbounded as `M -> 1+` (`t -> infinity`) — this is not
altered or capped anywhere.** What changed is only how the FINITE
visible segment is generated for display: the curve now enters/exits
the visible plot exactly at the configured X/Y viewport boundaries,
never at an arbitrary sampled point. Changing Y Max from, say, 1000 s to
500 s changes only the visible characteristic segment; it does not
alter the underlying protection equation, and no protection-facing
value (measured current, multiple of pickup, expected operating time,
above-pickup duration, threshold alert) is recomputed because the chart
viewport changed.

**New backend domain helper: `solve_multiple_of_pickup_for_operating_time()`**
(`app/domain/overcurrent.py`) — the exact closed-form algebraic inverse
of `evaluate_idmt_operating_time()`:

```
t = TMS * (k / (M^alpha - 1) + c)        (forward, unchanged, existing)
M = (1 + k / (t/TMS - c)) ** (1/alpha)   (inverse, new)
```

Solved algebraically, never a numeric root-find, so
`evaluate_idmt_operating_time(inverse(t)) == t` to tight floating-point
tolerance for every valid `t` — proved directly by
`test_overcurrent_domain.py::TestSolveMultipleOfPickupForOperatingTime`
(round-trips across all three IEC characteristics × 5 TMS values × 5
target times: 1000/500/100/10/1 s). Returns `None` (never NaN/Infinity)
for a non-finite/non-positive `t`, a non-finite/non-positive `TMS`, or
any input that would not yield a finite `M > 1`. This is a pure function
of the same `IdmtConstants`/`TMS` the forward formula already takes —
it changes no existing constant, no existing evaluation, no protection
semantics; it is the identical formula solved for the other variable.

**Frontend: a direct, deliberately-mirrored copy of both formulas**
(`wwOvercurrentEvalT()`/`wwOvercurrentSolveMForT()` in `frontend/
index.html`), used ONLY for chart-rendering geometry — finding exact
viewport-boundary intersections without a backend round-trip on every
viewport change (a hard requirement: viewport/zoom changes must stay
frontend-only and instantaneous, per the adjustable-viewport work
above). This is the first place the frontend evaluates the IDMT formula
itself, so three safeguards keep it from becoming a second, drifting
implementation: (1) it is a tiny, single-formula mirror, not a
duplicate of any guardrail/RMS/CT/validation logic; (2) its `k`/`alpha`/
`c` constants are ALWAYS read from `wwOvercurrentState.characteristics`
— the same values the backend itself returned via
`/overcurrent-characteristics` — never hand-typed; (3) it is
cross-checked against the backend's own expected values in
`backend/tests/test_frontend_overcurrent_analysis.py::
TestForwardInverseFormulaMatchesBackend` (executes the extracted JS via
Node, asserts exact numeric agreement with the same 75
characteristic/TMS/target-time combinations the backend's own inverse
test covers). Every protection-facing value shown to the engineer
continues to come exclusively from the backend's own computed
`wwOvercurrentState.latestResult` — these two functions never derive or
display any of those; they only decide where the drawn curve line goes.

**`wwOvercurrentVisibleCurveSegment(viewport)`** computes the exact
visible portion of the curve for the CURRENT viewport. Because `t(M)`
is strictly monotonically DECREASING for `M > 1`, the visible M-range
collapses to a simple closed form:

```
mTop    = the M where t(M) = viewport.yMax   (solved via the inverse)
mBottom = the M where t(M) = viewport.yMin   (solved via the inverse)
startM  = max(mTop, viewport.xMin)
endM    = min(mBottom, viewport.xMax)
```

If `startM >= endM`, no portion of the curve is visible for this
viewport (returns `null` — e.g. the whole curve is above Y Max, below Y
Min, or the X range doesn't reach M > 1 at all) — no curve is drawn,
never a distorted one. Otherwise, the exact start/end points are
included verbatim (`startM === mTop` — an exact equality, since
`Math.max`/`Math.min` return one of their own input values unchanged —
tells the code WHICH boundary was actually crossed: the Y boundary uses
the viewport's own exact `yMax`/`yMin`; the X boundary evaluates the
exact time AT that X position via the forward formula), and the points
between them are sampled log-spaced (60 points) for a smooth curve at
every supported scale — from a tight custom zoom to the full 200x/1000s
absolute domain.

**Rendering sequence, corrected** — `wwOvercurrentRenderChart()` no
longer builds the curve `<path>` by mapping the raw fetched `points`
array through the pixel functions and relying on the SVG `<clipPath>`
to cut it to size. The `<clipPath>` remains, purely as a rendering
safety net; it is no longer the mechanism that determines where the
visible curve starts or ends:

```
exact mathematical viewport intersection
  -> sample the visible characteristic (log-spaced)
  -> render the path
  -> clipPath as a safety net
```

The already-fetched backend curve (`wwOvercurrentState.curveCache.points`,
still fetched/cached exactly as before — see "Curve caching" above,
completely unchanged fetch/cache timing and the same
"only refetch on characteristic/TMS change" invariant) is retained only
as an availability GATE (curve data confirmed fetched for this
characteristic/TMS) — its own array values no longer determine the
rendered coordinates.

**Performance**: computing two inverse-solves plus two forward-evals
(for the four boundary checks) plus 60 forward-evals (for the smooth
in-between samples) is O(1) per render — no measurable rendering-
latency change from the prior direct-array-mapping approach, and, as
before, zero network requests on any viewport/zoom change (confirmed by
`browser-tests/overcurrent_analysis.spec.js`'s existing
"viewport changes never alter wwPlayback.currentTime or trigger a new
curve fetch" test, still passing unmodified).

## Shared Analysis Engineering Context lifecycle — UAT fix (2026-09-12)

**Owner UAT symptom**: after uploading an event, opening Overcurrent
directly (without ever visiting Phasor first) could leave the Bay/
Engineering Context selector empty even though the recording was
already loaded and ready. **Root cause**: Engineering Context
discovery/bootstrap (the automatic-suggestion machinery — see
PHASOR_ANALYSIS.md's own "Automatic Engineering Context bootstrap"
section for the algorithm) lived entirely inside Phasor's own code
path; Overcurrent only ever read whatever contexts already existed.
`wwRenderAnalysisPage()` started both analyzers' own loaders in
parallel, so Overcurrent could fetch the (still-empty) context list
before Phasor's own discovery pass ever ran, and nothing then told
Overcurrent to refresh once Phasor's discovery finished. An order-
dependent bug: the fix in place before this UAT round implicitly
required visiting Phasor first.

**Fix — new architectural rule**: Engineering Context discovery/
bootstrap is owned by the shared Analysis workspace, never by any
individual analyzer. `wwRenderAnalysisPage()` now calls
`wwAnalysisLoadContexts()` exactly ONCE per Analysis-page visit,
regardless of which analyzer tab is active. Overcurrent registers
itself as a CONSUMER of the one shared, published context list —

```javascript
wwAnalysisRegisterContextConsumer({
    onContexts: wwOvercurrentOnAnalysisContexts,
    onLifecyclePhase: wwOvercurrentOnAnalysisLifecyclePhase,
    onDiscovering: wwOvercurrentOnAnalysisDiscovering,
    onFreshContextsDiscovered: wwOvercurrentOnAnalysisFreshContextsDiscovered,
});
```

— exactly mirroring Phasor's own registration (see PHASOR_ANALYSIS.md's
own "Ownership moved to the shared Analysis workspace" section for the
full architecture, algorithm, and relocated-function inventory; not
duplicated here). Overcurrent's own four consumer callbacks are thin:
`onContexts` sets `wwOvercurrentState.contexts` and re-renders the
selector/reloads-or-shows-no-selection exactly as before;
`onLifecyclePhase` maps each of the four shared lifecycle phases
(`identifying`/`no_sources`/`no_suggestions`/`unreachable`) to
Overcurrent's own message constants (`WW_OVERCURRENT_MSG_
IDENTIFYING_CONTEXTS`/`_NO_SOURCES`/`_NO_SUGGESTIONS`/
`_BACKEND_UNREACHABLE`, new — Overcurrent previously only had
`_SELECT_CONTEXT`/`_BACKEND_UNREACHABLE`) via
`wwOvercurrentShowEmptyState()`; `onDiscovering` toggles a new
`#wwOvercurrentDiscoveringIndicator` element (added to the panel
markup, reusing the existing `.ww-phasor-discovering-indicator` CSS
class Phasor's own equivalent element already uses); `onFreshContextsDiscovered`
auto-selects the first context ONLY if Overcurrent doesn't already have
a selection of its own (never steals a selection Phasor's own fresh-
discovery hook already made, or vice versa — each analyzer's auto-
select policy checks only its OWN `selectedContextId`).

**Dead code removed**: `wwOvercurrentLoadContexts()`/
`wwOvercurrentHandleContextsFetched()`/the standalone
`wwOvercurrentFetchContexts()` helper are gone entirely — replaced by
the thin consumer functions above.
`wwOvercurrentEnsureCharacteristicsLoaded()` (renamed from
`wwOvercurrentLoadContexts()`) keeps its own small, unrelated entry
point for the Overcurrent-specific IDMT characteristic dropdown fetch,
called separately from `wwRenderAnalysisPage()`.

**Selection/state behavior preserved exactly**: `wwOvercurrentState.
selectedContextId` remains fully independent of `wwPhasorState.
selectedContextId`; a context already selected in Overcurrent is never
disturbed by a later background discovery pass finding an unrelated
source; duplicate display-name labels (two bare-role sources both
suggesting "Default Context") remain independently selectable by
context id, never deduplicated by name; a source already covered by a
manual/partial context is never re-suggested; one source's own
suggestion failure never blocks or blanks an already-usable bay; a
workspace change mid-discovery discards the stale in-flight result via
the same `ww.epoch`/`currentWorkspaceId()` guard every shared-lifecycle
async step already re-checks.

**No backend changes** — this was purely a frontend ownership/lifecycle
issue; the existing `GET .../engineering-contexts`/
`POST .../sources/{id}/engineering-contexts/suggest` endpoints are
reused verbatim, unchanged.

**Tests**: `browser-tests/overcurrent_analysis.spec.js`'s new "shared
Analysis Engineering Context lifecycle" describe block covers the exact
reported bug (fresh workspace, upload, open Overcurrent directly,
Bay selector populates automatically — never visiting Phasor), the
existing-Phasor-behavior-unchanged case, later-upload discovery with
selection preservation, Overcurrent-first-with-a-later-source, duplicate
display names, manual-coverage non-re-suggestion, and the stale-
workspace-discard guard.
`backend/tests/test_frontend_phasor_analysis.py`'s old Phasor-only
`TestContextBootstrap` was migrated (algorithm assertions unchanged) to
`TestSharedAnalysisContextLifecycle`, plus a new
`TestSharedAnalysisContextConsumers` class asserting BOTH analyzers
register via `wwAnalysisRegisterContextConsumer()` and that neither one
defines its own independent `wwXxxLoadContexts()`/
`wwXxxDiscoverUncoveredSources()`/`wwXxxFetchContexts()` again — a
structural regression seam intended to catch a future analyzer
(Impedance Locus, Differential, Sequence Components) that tries to
invent its own bootstrap instead of registering as a consumer.

## Analysis chart styling tokens (shared with Phasor)

See [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)'s own matching section —
`.ww-oc-axis`/`.ww-oc-gridline`/`.ww-oc-tick-label`/`.ww-oc-axis-label`/
`.ww-oc-guide` all consume the same shared `--ww-chart-*` CSS custom
properties the Phasor diagram's own new grid/axis-title rules use, so
the two charts read as one consistent visual language without
duplicating the same values twice. Every existing, already-tested class
name on this chart (`.ww-oc-curve`, `.ww-oc-operating-point`, ...) is
unchanged — only the underlying token VALUES are now centralized.

## Related Waveforms integration (shared Analysis primitive, 2026-09-12)

Overcurrent's own `phase` selector (see "Frontend: the second Analysis-
menu analyzer" above) drives the shared Related Waveforms panel's ONE
active Current role — no second waveform-channel selector was
introduced. `wwOvercurrentComputeActiveRelatedWaveformRoles()` (called
from the end of `wwOvercurrentRenderResult()`) declares exactly one
role, `"I" + phase.toLowerCase()` (e.g. `"Ia"`), using the
already-resolved `channel_ref`/`measured_rms_current_unit` from the
`/overcurrent` response — never re-derived from a channel name. No
Voltage role is ever declared here, even though Voltage channels may
exist in the same Engineering Context — Related Waveforms only ever
shows what is analyzer-relevant, never everything the Bay happens to
contain. Full shared-panel architecture (grouping, fetching, rendering,
the Playback cursor, resize) is NOT Overcurrent's own — see
[ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md).

## Not yet implemented (future slices)

- **ANSI/IEEE curves** (C37.112 and its own distinct constants).
- **Definite time** and **instantaneous/high-set stages**.
- **Earth-fault elements.**
- **Multiple relay coordination curves / protection grading studies.**
- **Manufacturer-specific curves.**
- **Relay tolerance bands, reset characteristics, thermal memory.**
- **Actual relay trip-state emulation** or dynamic accumulation
  estimation under variable current (see "Explicit non-emulation
  boundary" above).
- **`% plug setting` pickup entry** (v1 is relay-secondary-amperes only).
- **A lightweight per-phase resolver-preview call** to grey out an
  unresolvable phase in the selector before the engineer picks it (see
  "Phase selectability" above).
- **Backend-persisted per-workspace Overcurrent settings** (currently
  session-only, matching Phasor's own equivalent state).

## Related documents

- [DECISIONS.md — DEC-090](DECISIONS.md#dec-090--overcurrent-analysis-v1-the-second-analysis-menu-analyzer-iec-idmt-characteristic-evaluation-against-a-one-cycle-trailing-rms-current-at-the-shared-playback-driven-analysis-time) — this slice's full approval record.
- [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md) — the first Analysis-menu
  analyzer; the resolver/Playback-integration/Analysis-shell patterns
  this document reuses throughout.
- [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) — the shared Analysis
  shell infrastructure (Engineering Context lifecycle, Playback,
  Related Waveforms) every analyzer, including Overcurrent, consumes.
- [ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md) — the
  Engineering Context + resolver foundation this slice is built on
  entirely unchanged.
