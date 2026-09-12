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
the other's own selection or settings) — Overcurrent reads the SAME
workspace-level Engineering Context list Phasor does, via its own
lightweight `GET .../engineering-contexts` call, but **does not**
re-implement Phasor's own automatic-suggestion bootstrap/discovery
machinery — an engineer reaching Overcurrent will typically already have
a usable context from visiting Phasor or another flow first; Overcurrent
simply lists whatever contexts already exist.

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
- [ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md) — the
  Engineering Context + resolver foundation this slice is built on
  entirely unchanged.
