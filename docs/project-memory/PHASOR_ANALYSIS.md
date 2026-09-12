# Phasor Analysis

**Status: Slice 1 (Core Estimator + Selected-Time API), Slice 2
(Analysis Page + Static Phasor Diagram), the Phasor UAT redesign
(bay-centric aggregation), and Phasor Playback integration are all
implemented** — see
[DECISIONS.md — DEC-088](DECISIONS.md#dec-088--phasor-analysis-slice-1-a-fixed-frequency-one-cycle-trailing-window-rms-fundamental-phasor-estimator-with-an-explicit-guardrail-boundary-and-a-selected-time-only-read-only-api-built-directly-on-the-existing-engineering-context-resolver-foundation),
[DECISIONS.md — DEC-089](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)
(including its own "Update (2026-09-12)" sections, which superseded the
original Bay/Quantity/Mode page design described in DEC-089's own base
entry and then connected the shared Playback controller to it — see the
"Bay-centric Phasor Diagram" and "Phasor Playback integration" sections
below). Every real protection analysis (Distance/Overcurrent/
Differential/Sequence Components) remains unimplemented — this document
records the engineering definition and architecture the audit
established and these slices built, so a later slice does not need to
re-derive it.

## Product definition — what Powerwave means by "a phasor"

> A Powerwave phasor is an RMS fundamental-frequency phasor estimated
> from a sampled Voltage or Current waveform over one trailing cycle at
> a fixed reference frequency.

It is explicitly **NOT**: an instantaneous waveform sample, a
PMU/synchrophasor measurement, frequency-tracked, a precomputed vendor
magnitude/angle channel, an RMS calculated channel, or an arbitrary
magnitude signal.

## Estimator

```
X = (sqrt(2) / N) * sum_n( x_n * exp(-j * 2*pi*f0*t_n) )
magnitude_rms = abs(X)
angle_rad     = arg(X)
```

An explicit complex single-frequency projection (mathematically the
same result as a one-cycle DFT / cosine-sine correlation, framed as one
formula). The RMS normalization (`sqrt(2)/N`, not `2/N`) is proven, not
assumed, in `app/domain/phasor.py`'s own module docstring, and verified
numerically by `backend/tests/test_phasor_domain.py::TestRmsNormalization`
against a hand-derived expected value (`x(t) = sqrt(2)*100*cos(2*pi*50*t)
-> ~100 RMS`, never `141.4` peak).

## Window

Exactly one trailing cycle: `window_seconds = 1/reference_frequency_hz`,
applied as the **half-open** interval `(analysis_time - window_seconds,
analysis_time]` — reusing the exact boundary convention
`app.domain.calculated_channel.evaluate_rms()` already established
(excludes the sample exactly one period before `analysis_time`, which
would otherwise double-count that phase point). Never centered, never
uses future samples, never shortened/shifted near a recording's start —
an incomplete window returns an explicit `unavailable` result instead
(`insufficient_window_history`).

## Angle reference — the critical convention

Absolute phasor angle (`angle_deg_absolute`) is referenced to `t=0` of
one **shared, source-independent absolute-time coordinate**, computed
ONCE per request by the service layer — never reset per sliding window.
Concretely: every resolved role's own sample times are converted to
true absolute time (`source_start_epoch + elapsed_seconds`), then all
shifted by one common `reference_epoch` (the smallest `start_epoch`
among every resolved role's own grounding source, chosen purely to keep
floating-point angle precision high — never changing which physical
instant `angle=0` represents). This is what makes a steady nominal-
frequency sinusoid's own reported angle numerically STABLE as
`analysis_time` advances — verified directly by
`TestMovingAnalysisTimeStability` (domain) and
`TestMovingAnalysisTimeServiceLevel` (service).

For a **three-phase** result, `angle_deg_relative` is additionally
derived — Phase A (or Current Phase A) as the 0° display reference,
`relative_role = angle_deg_absolute(role) - angle_deg_absolute(anchor)`,
normalized to `(-180, 180]`. This is a DISPLAY-level transform layered
on top of the authoritative absolute value (mirroring how Per-Unit is
already a display transform over an authoritative engineering value,
never destructively baked into the raw computation) — a future combined
Voltage+Current analysis (impedance/power-factor angle) still has the
absolute angle of both quantities available to compute their
difference correctly. For a single-phase result, `angle_deg_relative`
is always `null` — there is no other phase to reference against.

**Verified at the start of Slice 2** (owner's own explicit pre-
implementation check): `t_n` inside `estimate_phasor()`'s own
`exp(-j*2*pi*f0*t_n)` is never a raw epoch-scale timestamp.
`phasor_analysis_service.py` already computes `reference_epoch =
min(start_epoch)` across every resolved role's own grounding source —
a per-request constant that depends only on WHICH sources ground the
resolved roles, never on `analysis_time` itself — and passes each
channel `(source_start_epoch - reference_epoch) + elapsed_seconds`
(confirmed directly at that module's own `t_shared`/`analysis_time_shared`
lines) into the pure estimator. This `tau_n = t_n - t_ref` reduction was
already present in Slice 1 (built for floating-point precision, not
realized at the time to also be the exact fix this convention requires)
and satisfies every one of the owner's stated requirements: shared
across all compared roles, independent of the sliding window's own
start, and empirically stable as `analysis_time` advances
(`TestMovingAnalysisTimeStability`/`TestMovingAnalysisTimeServiceLevel`,
both passing, both predating this check). **No production code change
was needed or made** for this verification.

## Reference frequency

1. An explicit `reference_frequency_hz` request override, if supplied
   (validated against `calculated_channel.nominal_frequency_valid()`'s
   own 1–1000 Hz plausibility bound, reused unchanged).
2. Otherwise, every resolved role's own grounding source must declare
   the SAME `nominal_frequency` (`math.isclose`, not exact `==`). If
   they disagree, the result is `needs_configuration` /
   `reference_frequency_conflict` — never the first source's value,
   never an average, never a silent proceed.

Never hard-coded to 50 Hz. 50 Hz and 60 Hz are both explicitly exercised
in the golden test suite.

## Fixed-frequency limitation — documented, not hidden

Phasor v1 uses the selected/reference frequency directly — it never
measures or tracks the actual system frequency. A persistent frequency
offset produces both a small magnitude error and a progressively
drifting angle across successive `analysis_time` calls, proportional to
elapsed time and the offset. `TestOffNominalFrequency` documents (and
numerically predicts, via a closed-form windowed-average derivation)
this exact behavior for a 49 Hz signal analyzed at a 50 Hz reference.
**This is not PMU/synchrophasor-class frequency tracking.**

## Minimum sampling density — an empirically-derived, Phasor-specific threshold

`PHASOR_MIN_SAMPLES_PER_CYCLE = 8` — deliberately **not** copied from
`calculated_channel.MIN_SAMPLES_PER_CYCLE` (`=4`, tuned for a *sliding*
RMS's own accuracy needs). Chosen from
`backend/tests/test_phasor_domain.py::TestSamplingDensityStudy`'s own
empirical sweep at 4/8/16/32 samples/cycle: for a perfectly clean
sinusoid, error is already at floating-point noise level at every
tested density (the correlation sum is discretely exact for a pure
single-frequency signal regardless of window-boundary phase); under a
realistic 0.2%-amplitude noise floor, however, error scales down
roughly with `1/sqrt(N)`, and 8 samples/cycle materially (>25%) reduces
noise-driven magnitude error relative to 4. Chosen as a deliberate
safety margin — double the bare RMS precedent — while remaining a very
low bar for any real COMTRADE recording (8 samples/cycle at 50 Hz is
only 400 Hz; this project's own performance-baseline fixtures use
5–20 kHz). An **application guardrail based on this estimator's own
measured behavior, not a claimed protection-relay industry standard.**

## Waveform-form eligibility

Mirrors `calculated_channel_service.check_rms_eligibility()`'s own
metadata-first, detector-fallback structure — applied more strictly,
since Phasor v1 has no override mechanism:

- `waveform_form == instantaneous` → eligible.
- `waveform_form ∈ {rms, magnitude}` → rejected, no override (unlike
  RMS creation, there is no legitimate reason to phasor-estimate a
  signal already proven non-oscillatory).
- `waveform_form == unknown` (the common case — no current provider
  sets this field away from `unknown` for either raw or calculated
  channels) → falls back to the existing
  `app.domain.rms_detector.classify_waveform_form()` heuristic, run
  once against the candidate's own FULL sample arrays (never restricted
  to one phasor window). `LIKELY_INSTANTANEOUS` → eligible.
  `LIKELY_MAGNITUDE_OR_RMS` **or** `UNCERTAIN` → rejected. Uncertain is
  deliberately treated the same as likely-RMS here — this is a
  reconsidered, STRICTER position than the original audit's own
  "allow uncertain with a warning" suggestion: `check_rms_eligibility()`
  itself already treats `UNCERTAIN` as blocking pending an engineer
  override, and Phasor v1 has no override at all, so honoring that same
  real precedent (rather than the audit's own earlier guess) means
  rejecting, not warning-and-allowing.

Calculated channels follow the identical rule, using their own
`engineering_type`/`waveform_form` metadata — no automatic phase
inheritance is added for a calculated channel (unchanged from Slice 1's
own Engineering Context policy).

## Engineering Context / resolver integration

`app.services.phasor_analysis_service.compute_phasor_analysis()` calls
`resolve_analysis_inputs()` (Slice 2, entirely unchanged) FIRST. If it
does not reach `resolved`, the resolver's own `status`/`reason_code`/
`message`/per-role diagnostics are returned VERBATIM — no estimation is
attempted, no channel is searched by name, no phase is remapped, no
channel is borrowed from another context. Persisted Engineering Context
metadata remains the sole authority.

## Single-phase / three-phase

Reuses the existing `PHASOR_VOLTAGE_PHASE_A/B/C`, `PHASOR_CURRENT_
PHASE_A/B/C`, `PHASOR_VOLTAGE_THREE_PHASE`, `PHASOR_CURRENT_THREE_PHASE`
requirement definitions (Slice 2) unchanged. Single-phase mode requires
only the one selected role — no global three-phase assumption anywhere.
Three-phase mode requires all three roles to resolve, share a
compatible timebase (resolver-proven), agree on reference frequency,
and each produce an available phasor estimate — if any ONE role cannot
be estimated, the WHOLE three-phase result is `needs_configuration`,
never a partial/misleading diagram.

## Multi-source behavior

An Engineering Context may span sources (Slice 1). The resolver already
proves timebase compatibility for whatever roles it resolves together;
this slice ADDITIONALLY requires every resolved role's own source to
agree on `nominal_frequency` (see "Reference frequency" above) — a
check the resolver itself has no reason to know about, since it is
Phasor-specific, not a general role-resolution concern.

## Unit scope

**Engineering units only in Slice 1** — Voltage in V/kV, Current in
A/kA, whatever the resolved channel's own `unit` already is. No
`unit_mode`/Per-Unit parameter exists on the `phasor` endpoint. Per-Unit
phasor display is deliberately deferred to a later slice, after this
slice's own engineering-units behavior is proven correct.

## Selected-time only

Slice 1 computes exactly one phasor at one requested `analysis_time`
per request — never a precomputed time series, never continuously-
updated server state, never persisted. Every result is derived fresh
from current context/channel state on every call.

## Result model

```
PhasorAnalysisResult (app.domain.phasor)
├── status                  "computed" | resolver's own 3 pass-through statuses
├── analysis_kind, mode, engineering_context_id, analysis_time  (echoed)
├── reference_frequency_hz, window_seconds   (only set when computed)
├── algorithm_version        "phasor_estimator_v1"
├── roles: dict[role_key, PhasorRoleResult]
│     ├── channel_ref
│     ├── magnitude_rms, unit
│     ├── angle_deg_absolute
│     └── angle_deg_relative   (three-phase only, else null)
├── warnings[]                (structurally present; empty in most Slice 1 cases)
├── role_reasons: dict[role_key, str]   (per-role diagnostic detail — an
│                                        addition beyond the earlier
│                                        audit's own flat sketch)
├── reason_code, message
```

A concrete, Phasor-owned result — deliberately NOT a generic
cross-analysis `AnalysisResult` framework (nothing in the codebase
needed one before a second real analysis exists to prove what should
actually generalize). Never persisted. **Still the exact shape the
original `GET .../phasor` endpoint returns, unchanged** — the bay-centric
redesign below adds a SEPARATE result shape for its own aggregated
endpoint, it does not replace this one.

## Algorithm version

`algorithm_version = "phasor_estimator_v1"`, a module constant in
`app/domain/phasor.py`, included unconditionally in every computed
result. Bumped only when the estimation algorithm/interpretation itself
changes (e.g. a future frequency-tracked estimator) — never for an
unrelated refactor.

## API

```
GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/phasor
    ?analysis_kind=phasor&mode=voltage_three_phase&analysis_time=1.234
    &reference_frequency_hz=50.0   (optional override)
```

Nested under the Engineering Context it resolves against (mirrors the
existing `input-resolution` endpoint's own precedent), read-only,
engineering units only. `analysis_time` is elapsed seconds since the
start of whichever resolved role's source grounds the FIRST required
role (the "anchor" — e.g. `Va` for every three-phase requirement) — for
the common single-source case this is simply "elapsed seconds since
this recording's own start," identical in spirit to the existing
`cursor-values` endpoint's own per-source convention.

## Performance (measured, not assumed)

`docs/development/PERFORMANCE_BASELINE.md`'s own numbers were about
import/waveform-window latency, not this endpoint — measured directly
instead, on a representative 20 kHz, 10-second (200,000-sample) single-
channel source:

- Pure domain estimator (`estimate_phasor()`): **~0.8 ms/call**.
- Full service (`compute_phasor_analysis()`, including the resolver
  call and a waveform-form-`unknown` detector fallback run): **~19
  ms/call**.
- Full HTTP round trip (`GET .../phasor`, real FastAPI `TestClient`,
  including request handling and JSON serialization): **~33 ms/call**.

All comfortably fast for an on-demand, selected-time request (comparable
to the existing waveform-window-read latencies `PERFORMANCE_BASELINE.md`
already found acceptable). No caching/precomputation was introduced —
"measure first, optimize later" is satisfied by this measurement
itself, not by assumption. The dominant service-layer cost is the
waveform-form eligibility detector's own O(N)-on-a-representative-slice
work, run fresh on every request when a channel's `waveform_form` is
`unknown` (the common case) — a pre-existing cost pattern this slice
inherits from `check_rms_eligibility()`'s own identical behavior, not a
new one it introduces.

## Frontend: the Analysis page

**`Analysis` is a new, permanent top-level main-menu destination** —
`#mainNavAnalysisBtn`, placed immediately after `Calculated Channels`,
opening `#pageAnalysis` via the same `shellSetCurrentPage()` "hide,
don't destroy" mechanism every other page already uses. It is the home
for every future engineering analyzer (Distance Protection/Overcurrent/
Differential/Sequence Components) — a left-hand `.ww-analysis-type-nav`
list is the seam those add their own entry to; today it has exactly one,
`Phasor`, whose own panel renders directly. **The sidebar tooltip and
visible nav label read "Phasor Diagram"** (a UAT fix, 2026-09-11 — the
bare "Analysis" text was too generic with only one analyzer
implemented); the page's own `<h2>` heading deliberately stays
"Analysis," since that is what will read correctly once a second
analyzer exists.

**Normal workflow is bay-centric** (Phasor UAT redesign, 2026-09-12 —
superseded the original Bay/Quantity/Mode workflow; see "Bay-centric
Phasor Diagram" below for the full design): Bay (Engineering Context) is
the ONLY primary control. Selecting one automatically resolves and
computes every supported role (`Va`/`Vb`/`Vc`/`Ia`/`Ib`/`Ic`) together in
one request; the Values list and diagram show whatever is available, a
partial bay included. There is no manual raw-channel picker anywhere in
this page's normal workflow — the engineer never chooses `Va`/`Ib`/etc.
directly; manual correction, when genuinely needed, remains an
Engineering Context metadata edit (Slice 1's own `member-phase`
endpoint), reached outside this page.

### Automatic Engineering Context bootstrap — SOURCE-COVERAGE driven (multi-upload fix, 2026-09-12)

UAT originally found that a workspace with loaded sources but no
Engineering Contexts yet left the Phasor page empty (fixed 2026-09-11,
below). A SECOND UAT root-caused a further gap in that fix: bootstrap
was gated on `contexts.length > 0`, so a source uploaded AFTER the
workspace's first context already existed was silently never covered —
its own suggestion was simply never requested, and it could never appear
in the Bay selector no matter how many times the engineer revisited the
page. Bootstrap is now driven by SOURCE COVERAGE, not context count:

```text
GET engineering-contexts
    ↓
contexts.length > 0? --yes--> render the selector/body from them
    |                         IMMEDIATELY (never blanked), THEN discover
    |                         any uncovered source in the BACKGROUND
    |no                       (non-blocking; see below)
    ↓
discover uncovered sources, BLOCKING (nothing usable to preserve yet --
the original "Identifying engineering contexts…" full-page experience)

---- discovery (shared by both paths above) ----
GET sources
    ↓
any loaded? --no--> "No event sources are available..." (blocking path only)
    |yes
    ↓
coveredSourceIds = source ids referenced by any context member's own
`channel_ref.source_id` (wwPhasorCoveredSourceIds() -- membership only,
NEVER display name/status/context count/source order)
    ↓
uncoveredSources = loaded sources NOT in coveredSourceIds AND not yet
individually attempted this workspace session
    ↓
none uncovered? --yes--> done (blocking path shows "no suggestions found")
    |no
    ↓
POST .../sources/{id}/engineering-contexts/suggest, for EVERY uncovered
source (never assumes one source is "the" bay; one source's own failure
never blocks the others)
    ↓
GET engineering-contexts again -> re-render the selector in place,
preserving whatever was already selected
```

**Reuses the existing Guardrail Slice 1 suggestion endpoint verbatim** —
no new backend detection engine, no frontend channel-name parsing, no
change to `app.domain.engineering_context_detection`. The suggestion
service's own additive/idempotent contract is what the frontend leans on
for safety; the frontend's OWN safety mechanism is
`wwPhasorState.attemptedSourceIds` — a **per-source** `Set`, replacing
the original single workspace-wide `bootstrapAttempted` boolean, which
could not represent "source A was already tried, but source B (uploaded
later) has not been." A source is marked attempted the moment its own
suggestion call is dispatched (mirroring the original boolean's own
timing precedent exactly, including for a transient network failure —
this fix does not invent a new retry policy). Reset only by
`wwPhasorResetState()` (the "Start New Workspace"/"Clear workspace"
hook), so a fresh workspace always starts with an empty attempted set
and a workspace switch never leaks another workspace's own bookkeeping.

**An already-usable bay is never blanked for this.** When at least one
context already exists, the selector/values/diagram render from it
immediately; discovering any OTHER uncovered source runs quietly in the
background (`wwPhasorDiscoverUncoveredSources(..., blocking=false)`),
surfaced only via a small, non-blocking `#wwPhasorDiscoveringIndicator`
text ("Identifying additional engineering contexts…") — never the
full-page `wwPhasorShowEmptyState()` treatment, which remains reserved
for the genuinely-nothing-exists-yet (`blocking=true`) path.

The backend detector also covers the proven UAT file shape where a
source's own COMTRADE channel names are bare role names with no bay
prefix (`VA`/`VB`/`VC`/`IA`/`IB`/`IC`, or R/Y/B equivalents), suggesting
one neutral "Default Context" per source when unambiguous. **Coverage is
keyed by source id, never by display name** — two DIFFERENT bare-role
sources both producing a context literally named "Default Context" are
correctly tracked as two independent, fully-usable bays; duplicate
display names never imply a coverage/identity collision.

**Suggested/needs_review contexts are never hidden or auto-upgraded** —
they populate the Bay selector exactly like a `confirmed`/`manual`
context, with the same `ww-mg-badge` status indicator already
established for Measurement Groups. Detection may suggest; explicit
engineer confirmation (via Engineering Context metadata, outside this
page) remains authoritative, unchanged.

**Auto-selection remains scoped to the fresh, nothing-existed-before
path only.** Immediately after a successful bootstrap from a genuinely
empty starting point, the first newly-suggested context is auto-selected
(so the engineer never needs an extra click merely because the context
was just created) — but discovering an ADDITIONAL uncovered source when
a bay was already open/selected never auto-selects the new one, and
never resets the existing selection: adding source B must never jump the
engineer away from source A's own already-open bay.

**Async/stale protection**: every discovery step (source list fetch,
each per-source suggest call, the final context re-fetch) re-checks the
same `epochAtStart`/`workspaceId` guard every other Phasor fetch already
uses — a workspace change mid-discovery (a new upload, "Start New
Workspace") discards the in-flight attempt rather than populating the
wrong workspace's own selector.

**Removal is naturally correct, with no special-casing needed** —
coverage is recomputed FRESH from current context membership on every
call, never cached beyond the per-source `attemptedSourceIds` guard
(which only ever prevents a REDUNDANT re-suggestion, never blocks
discovery of a DIFFERENT, still-uncovered source). Removing a covered
source's own context does not affect any other source's own coverage
state; a still-uncovered source remains discoverable exactly as before.

**No cross-source automatic merging was added** — each source's own
suggestion request is independent; a genuinely multi-source bay still
requires manual Engineering Context membership correction, exactly as
Slice 1 already established.

**Analysis time is workspace time**, the same coordinate Cursor A/B and
`ww.viewport` already use — converted to the resolved anchor role's own
source-relative elapsed time ONLY at the `GET .../phasor` call boundary
(`wwWorkspaceTimeToSourceTime()`, the exact conversion every other
per-source endpoint in this app already performs). The default analysis
time prefers Cursor A's own time (if enabled/visible/finite and it would
not guarantee "insufficient history"), else the anchor's own Time Group
bounds start plus a small fixed buffer, else 0 — Cursor A is read only
as a convenient starting value; moving the Phasor analysis time never
moves Cursor A, and Cursor A's own t=0/measurement semantics are
untouched.

**Angle display** (revised by the Phasor UAT redesign): the Values list
shows `angle_deg_absolute` ONLY — never `angle_deg_relative` — since the
diagram's own geometry always uses the absolute angle, and showing that
same value in the table is the one choice guaranteed never to mismatch
what the diagram actually draws. Magnitude uses the existing
`wwFormatEngineeringValue()` formatter, true engineering units (no
Per-Unit normalization in this slice).

**Diagram** (extended by the Phasor UAT redesign to support up to six
vectors at once — see "Bay-centric Phasor Diagram" below for the dual-
scale/absolute-angle design in full): lightweight, hand-rolled SVG
(`#wwPhasorSvg`) — axes, magnitude rings, and one `<line>`+arrowhead
`<polygon>`+`<text>` label per AVAILABLE and VISIBLE role. No Plotly —
this diagram has no existing time-series-chart precedent to reuse, and
the vector math (`x=r·cosθ, y=-r·sinθ`) is simple enough that direct SVG
element updates are both simpler and cheaper than a Plotly figure, which
matters directly for the still-deferred Playback smooth-update
requirement. Three phase-identity color tokens (`--ww-phase-a/b/c`,
reusing the app's already-accessible `--accent`/`--warn`/`--ok` trio —
deliberately never Cursor A/B's own `--accent`/`--error` tokens, since no
phase-color convention existed anywhere in this codebase before Slice 2
and the two concepts could plausibly appear on the same future page).

**Stale-request protection**: a single shared `wwPhasorState.
requestGeneration` counter (bumped on every context/time change, or a
selected-context change) plus the existing whole-workspace `ww.epoch`
guard — a slower, superseded response is always discarded, never applied
over a newer selection. No second global time controller was
introduced. A pure visibility toggle never touches this counter at all
— it never issues a request in the first place.

**A caught defect**: `.ww-phasor-body`/`.ww-phasor-time-row` both use an
explicit `display: grid`/`display: flex`, which (as CSS specificity
works) silently overrides the browser's own default `[hidden] {
display: none }` rule for the `hidden` ATTRIBUTE these elements are
toggled with in JS — caught directly by
`browser-tests/phasor_analysis.spec.js`'s own empty-state test (a
real-browser assertion a source-text test cannot make), fixed with an
explicit `.ww-phasor-body[hidden] { display: none }` override.

**Explicitly NOT implemented**: `wwPlayback`/`wwPlaybackOnTick` wiring,
Play/Pause/speed/seek controls (a `#wwPhasorPanel` composition-point
comment marks exactly where Playback adds an embedded control row
without restructuring this page), Per-Unit display,
precomputed-phasor-channel support, frequency tracking, sequence
components, impedance/distance, and every real protection analysis.
Combined Voltage+Current display **was** on this list at Slice 2 — the
Phasor UAT redesign implemented it; see "Bay-centric Phasor Diagram"
below.

## Bay-centric Phasor Diagram (Phasor UAT redesign)

UAT of the Slice 2 Bay/Quantity/Mode page found it too restrictive: an
engineer had to pick one role subset (e.g. "Voltage, Three Phase") at a
time, never seeing Voltage and Current together the way the existing
Waveform display shows every channel at once. Owner instruction: "Once a
bay/context is selected, Powerwave should automatically resolve all
available supported phasor inputs for that bay and show them together
on one diagram. The engineer then hides/shows individual vectors by
clicking their labels/visibility controls." See
[DECISIONS.md — DEC-089's own "Update (2026-09-12)"](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)
for the full approval record; this section is the architecture summary.

### Separation of concerns (must not be conflated)

Three distinct concepts, deliberately kept separate:

1. **Engineering Context** — what signals belong to the bay (Slice 1,
   unchanged).
2. **Analysis Input Resolver** — which signals satisfy each role (Slice
   2, `resolve_analysis_inputs()`, unchanged — called once per role,
   never re-implemented).
3. **Phasor visibility state** — which VALID, already-computed vectors
   are CURRENTLY SHOWN. Pure frontend display preference
   (`wwPhasorState.visibleRoles`). Never modifies context membership,
   phase identity, resolver rules, Measurement Groups, or any backend
   metadata.

### Backend aggregation: `compute_phasor_diagram()`

`app/services/phasor_analysis_service.py` gained a second orchestration
function, alongside the original `compute_phasor_analysis()` (still
present, still tested, still backing `GET .../phasor` unchanged):

```
compute_phasor_diagram(workspace_id, engineering_context_id, analysis_time, reference_frequency_hz_override, ...)
```

For each of the six single-phase requirements
(`PHASOR_VOLTAGE_PHASE_A/B/C`, `PHASOR_CURRENT_PHASE_A/B/C` — reused
unchanged from DEC-087), independently:

1. Call `resolve_analysis_inputs()` (unchanged). Map its outcome to a
   new 5-value role-status vocabulary: `STATUS_AMBIGUOUS` →
   `ambiguous`; `STATUS_NEEDS_CONFIGURATION` with reason
   `phase_identity_missing` → `needs_configuration`; with reason
   `role_missing` (or `STATUS_NOT_APPLICABLE`) → `missing`.
2. For every role that reached `resolved`, fetch its own sample data via
   the existing, unchanged `_fetch_role_candidate()`.
3. Compute ONE reference frequency across every identity-resolved
   candidate — identical policy to `compute_phasor_analysis()` (explicit
   override → else unanimous `nominal_frequency` agreement → else
   CONFLICT). A conflict blocks the WHOLE result.
4. Per-candidate waveform-form eligibility (`_waveform_form_eligible()`,
   unchanged) — an ineligible role gets `not_eligible`, but this does
   NOT block any other role.
5. **A NEW cross-role timebase check** — `timebases_aligned()` (reused
   unchanged from `app.domain.calculated_channel`) pairwise across every
   ELIGIBLE candidate. This does not exist in the original single-
   requirement service because the resolver's own internal timebase
   proof only fires when ONE requirement resolves MULTIPLE roles
   together (e.g. `PHASOR_VOLTAGE_THREE_PHASE`); it never fires for six
   INDEPENDENTLY resolved single-role requirements, so this module adds
   its own check for exactly that combination. Incompatibility also
   blocks the WHOLE result — symmetric treatment with a reference-
   frequency conflict, since both represent "these roles cannot be
   meaningfully combined into one diagram."
6. The shared absolute-time coordinate (`reference_epoch`) and anchor
   role follow the same `reference_epoch = min(start_epoch)` pattern as
   the original service, with the anchor being whichever role is FIRST
   in `PHASOR_DIAGRAM_ROLE_ORDER = ("Va","Vb","Vc","Ia","Ib","Ic")`
   among the ELIGIBLE roles — gracefully degrading for a partial bay
   (e.g. if `Va` is missing but `Vb` exists, `Vb` becomes the anchor).
7. `estimate_phasor()` (unchanged) runs per eligible role against the
   shared coordinate. A role whose estimate itself comes back
   unavailable (e.g. `insufficient_window_history`) gets
   `needs_configuration` with the estimator's own reason — again, this
   does NOT block any other role.

**Whole-result vs. per-role failure, strictly separated**: the top-level
`status` is `computed` even when some roles are `missing`/`ambiguous`/
`not_eligible` — there is still something useful to show. It is only
ever `needs_configuration` for the two genuine cross-role BLOCKING
conditions (reference-frequency conflict, timebase incompatibility) plus
the pre-existing `invalid_reference_frequency`/`absolute_time_
unavailable` edge cases inherited from the original service's own
precedent. When blocked, every role whose channel identity was already
known is reported `needs_configuration` with the SAME blocking reason —
never left without a status, never given a fabricated numeric result.

**New result shape** (`PhasorDiagramResult`, `app/domain/phasor.py` —
additive, `PhasorAnalysisResult` untouched):

```
PhasorDiagramResult
├── status                    "computed" | "needs_configuration"
├── engineering_context_id, analysis_time  (echoed)
├── reference_frequency_hz, window_seconds  (only set when computed)
├── algorithm_version          "phasor_estimator_v1" (same estimator)
├── roles: dict[role_key, PhasorDiagramRoleResult]
│     ├── status               available | missing | needs_configuration
│     │                        | ambiguous | not_eligible
│     ├── channel_ref          (only when identity is known)
│     ├── magnitude_rms, unit  (only when `available`)
│     ├── angle_deg_absolute   (only when `available` -- geometry value)
│     ├── angle_deg_relative   (only when `available`, per-family
│     │                        reference -- secondary/table-only)
│     └── reason_code
├── warnings[], reason_code, message
```

A concrete, Phasor-owned aggregation shape — deliberately NOT persisted,
and NOT a general-purpose "all analysis roles" framework (owner
instruction).

**New endpoint**, alongside the original:

```
GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/phasor-diagram
    ?analysis_time=1.234
    &reference_frequency_hz=50.0   (optional override)
```

No `analysis_kind`/`mode` parameters — every supported role is always
requested together. `analysis_time` semantics match the original
endpoint's own convention (elapsed seconds since the anchor role's own
source start), with the anchor determined dynamically as described
above.

### Frontend: single aggregated fetch, no per-role resolution call

The old two-call flow (`input-resolution`, then `phasor`) is replaced by
ONE call to the new endpoint (`wwPhasorFetchDiagram()`). Selecting a
GENUINELY DIFFERENT context (`wwPhasorLoadForSelectedContext()`) resets
`wwPhasorState.visibleRoles` to empty, then requests the diagram; every
role that computes `available` and has no existing visibility
preference defaults to visible. An analysis-time change — now driven
entirely by the shared Playback controller, see "Phasor Playback
integration" below — re-requests the diagram but never touches
`visibleRoles` — a hidden vector stays hidden throughout playback.

**Values list**: two sections, VOLTAGE and CURRENT, each listing its own
three roles in order. An `available` role's own row is a full
row-as-toggle-button (reusing the EXACT `#channelGroups` row-as-button
convention Waveform channel visibility already established —
`role="button"`, `aria-pressed`, a dimmed `.ww-phasor-value-row--hidden`
state, no tiny icon-only hit target) showing magnitude/unit/
`angle_deg_absolute`/an eye glyph. A non-`available` role's own row shows
its status label (`Missing`/`Needs configuration`/`Ambiguous`/`Not
eligible`) and reason instead, with no toggle control at all — nothing
to show, nothing to hide.

**Visibility toggling is a pure local re-render** — clicking a row
(`wwPhasorToggleRoleVisibility()`) flips one entry in `visibleRoles` and
calls `wwPhasorRenderFromState()`, which re-renders the SAME already-
fetched `wwPhasorState.latestDiagram` with no network request at all.
`wwPhasorRequestDiagram()` (the only function that fetches) and
`wwPhasorRenderFromState()` (the only function that re-renders from
cache) are strictly separate call paths.

**Diagram scaling**: `wwPhasorFamilyMaxMagnitude()` computes ONE maximum
magnitude per family (across every `available` role in that family,
regardless of current visibility, so toggling a vector never rescales
the whole diagram), each normalized independently to the same outer
plot radius (`voltageScale`, `currentScale`). Vector geometry always
uses `role.angle_deg_absolute` — Voltage and Current are NEVER
independently zero-referenced, preserving the true V-I angular
relationship. When both families are present, a transparent scale-ratio
annotation is shown below the diagram (`#wwPhasorScaleNote`, e.g.
"Current vectors scaled ×15.27 for display"); when only one family is
present, no ratio is shown (nothing to compare). Current vectors are
drawn dashed (`.ww-phasor-vector--current`), Voltage solid, both still
colored by their own A/B/C phase swatch — quantity type and phase
identity are both visible without inventing unrelated colors.

**Time-axis anchor for the frontend's own workspace-time conversion**:
`wwPhasorAnchorDisplaySourceIdForContext()` uses the selected context's
own FIRST member (from the already-fetched context list, `GET
.../engineering-contexts`) — never inspecting phase/engineering_type,
i.e. never duplicating the resolver's own role-matching in the frontend.
The backend's own internal anchor role can, in principle, differ (it
depends on which roles end up eligible), but every combination the
backend will actually compute together has already been proven
timebase-compatible, which in practice means an equal absolute start
time — so any member's own source produces the same elapsed-seconds
number for a shared analysis instant.

### Explicit scope exclusions (this redesign)

Playback (unchanged composition-point comment), Per-Unit display,
neutral-phasor roles (`Vn`/`In` — the existing Engineering Role/phase-
identity infrastructure has no dedicated neutral-phasor support to build
on), sequence components, impedance/distance, automatic cross-source
context merging, and a manual raw-channel picker (still never
introduced).

## Phasor Playback integration

Connects the existing, unchanged, shared `wwPlayback` controller (see
[DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock))
to the bay-centric Phasor Diagram above — exactly the "future analysis
overlay" DEC-085 was future-proofed for. **No second Playback controller,
timer, or clock was built.** See
[DECISIONS.md — DEC-089's own "Update" section for this integration](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)
for the full approval record.

### Shared clock, single time control

The separate "Analysis Time" number input + slider are REMOVED entirely.
Phasor mounts the SAME reusable Playback control surface
(`wwCreatePlaybackControlsHtml()`/`wwWirePlaybackControls()`/
`wwSyncPlaybackControls()`/`wwUpdatePlaybackControlsTick()`, all
unchanged). At the time this integration shipped, the Waveform Time
Group toolbar also mounted this surface; a LATER same-day owner product
decision made Playback controls Analysis-only, so the Waveform toolbar
no longer does — see this document's own "Playback controls are now
Analysis-only" section near the end. `wwPhasorMountPlaybackControls(groupId)`
builds a fresh copy of that
markup into `#wwPhasorPlaybackMount` whenever the selected context's own
resolved Time Group changes, mirroring `wwCreateTimeGroupCanvasDom()`'s
own "one canvas per distinct group, wired once" convention (never
re-wiring an existing mount for a different group, which would leave
stale closures). The mounted seek scrubber IS Phasor's own analysis time
control now — `wwPhasorState.analysisTime` is driven entirely from
`wwPlayback.currentTime` whenever the selected context's own group is
the controller's own active group.

### Claiming a context's Time Group vs. the Restart button

Selecting a context whose own resolved Time Group is **already**
`wwPlayback`'s own active group reads its CURRENT time verbatim (never
resets it — satisfies the Waveform↔Phasor interoperability requirement).
Selecting a context whose group is **not yet** active claims it via the
existing, unchanged `wwPlaybackRestart()` (which safely cancels any
OTHER group's own rAF loop first, landing at `bounds.start`, "stopped"),
then — as a Phasor-only, ONE-TIME convenience for a bay's very first
view — refines the landing position via the same real seek-input+commit
pair a native scrubber drag would use
(`wwPhasorComputeInitialClaimTime()`: prefers Cursor A's own current
position if it would not itself guarantee insufficient history, else
`bounds.start + 0.1s`, else `bounds.start`). **This refinement is
Phasor-specific and never applies to the mounted Restart BUTTON itself**
— that button is wired directly to the bare `wwPlaybackRestart()`, with
no follow-up seek, so pressing it always lands honestly at `bounds.start`
(owner instruction: "Playback owns event time... do NOT silently shift
Playback start forward" — that instruction governs the Restart control's
own behavior specifically, not where a bay lands the very first time it
is ever opened).

### The one tick subscriber

`wwPhasorOnPlaybackTick(currentTime, playback)`, registered ONCE at Init
via the existing `wwPlaybackOnTick()` seam, is the only place Phasor
reacts to shared-clock time. It no-ops whenever a DIFFERENT Time Group
than Phasor's own resolved one is what's actually moving (Phasor's own
bay stays static at wherever it last was). A discovered gap in the
shared controller: `wwPlaybackPause()`/`wwPlaybackSetSpeed()` mutate
`wwPlayback` directly but do not call `wwPlaybackNotifyTick()` (unlike
Play/Restart/seek/reset, which all do) — their own effect was already
fully covered for the Waveform toolbar's built-in, directly-wired
consumer, but a second mount point had no other seam to learn about
exactly these two transitions. Fixed entirely within Phasor's own
mounting code (`wwPhasorMountPlaybackControls()` adds its own listener
on the mounted Play/Pause/Restart/Speed controls that re-invokes
`wwPhasorOnPlaybackTick()` directly, AFTER the shared handler already
ran) — the shared controller itself was not modified.

### Throttled, concurrency-safe fetch

**One request in flight, plus the latest desired time — never a growing
queue.** `wwPhasorMaybeFetchForPlayback()` (used only while
`playback.state === "playing"`) skips a new fetch if one is already in
flight or if fewer than `WW_PHASOR_PLAYBACK_THROTTLE_MS` (100 ms, ~10 Hz)
have elapsed since the last one; `wwPhasorRequestExactPlaybackFetch()`
(used for every NON-playing state — Pause, Restart, Playback reaching
its own end, and every seek `input`/`change` event, whether the drag
starts or ends paused) bypasses the elapsed-time floor but still respects
"one in flight." Both funnel into the same `wwPhasorRequestDiagram()`,
whose own trailing call re-invokes the throttle check on completion, so
a desired-time change that arrived mid-flight is picked up immediately,
never left waiting for a tick that (while paused) will never come.
**Deliberately never throttled-by-elapsed-time while paused** — ticks
only arrive from the rAF loop, which only runs while actually playing;
gating a paused seek on an elapsed-time floor risked its own desired time
getting stuck unfetched forever (found and fixed directly, via a real
failing Playwright test, not assumed).

**Measured** (not assumed) aggregated endpoint latency on a demanding
20 kHz/10 s/six-role fixture: ~28–44 ms (p50 ~33 ms) — comfortably under
the 100 ms throttle window even at 4× speed.

### Diagram scaling stability during Playback

`wwPhasorState.frozenVoltageScale`/`frozenCurrentScale` hold each
family's own scale for the current "playback run" — established from the
first valid result, then held FIXED (never silently shrunk merely
because a later magnitude is smaller, which would mask real magnitude
movement) and only ever adjusted to accommodate a magnitude that would
otherwise overflow the plot's own headroom. Released back to `null`
(re-established fresh) specifically when a transition lands exactly at
the Time Group's own `bounds.start` on a real Restart (distinguished from
natural end-of-range completion, which lands at `endTime`) or when the
selected context genuinely changes. Ring labels show the value the outer
ring itself represents under the CURRENT (possibly frozen) scale, not the
live/current family max, so a visually-fixed ring never sits next to a
number that jiggles every tick.

### Visibility persists throughout Playback

`wwPhasorState.visibleRoles` is untouched by every Playback-driven time
change (`wwPhasorOnPlaybackTick()` never writes to it) — reset only on a
GENUINE context change, tracked via a new `wwPhasorState.
lastLoadedContextId` (a pre-existing subtlety fixed in passing: the old
`wwPhasorLoadForSelectedContext()` reset visibility on every mere page
revisit with the SAME context still selected, since that function was
already re-run on every Analysis-page visit; this is now scoped
correctly to an actual context change).

### Partial roles, whole-result blocking, and atomic rendering — unchanged

A bay with fewer than six resolvable roles continues updating whichever
roles ARE available throughout Playback; a role that temporarily becomes
unavailable simply stops being drawn on the next render, without
affecting the others. The two whole-result-BLOCKING conditions
(reference-frequency conflict, timebase incompatibility) are entirely
unchanged — still backend-computed, still per-request. Every accepted
fetch renders the analysis time, Voltage/Current values, SVG geometry,
scale annotation, and role-status messages together from the SAME
response object (`wwPhasorRenderDiagramResult()`), so the table and
diagram can never represent different response times; the estimator's
own one-cycle transition behavior (no instant jumps, no interpolation)
is preserved automatically since nothing here blends between two fetched
results.

### Context switch while playing

Selecting a DIFFERENT context whose own group differs from the currently
active one always claims the new group via `wwPlaybackRestart()` (see
above) — which safely stops whatever the OLD group was doing (playing or
not) before the new group becomes active, landing statically. The
engineer must press Play again to resume; Playback never continues
through an unresolved context transition.

### Explicitly still deferred

Per-Unit display, sequence components, impedance/distance, automatic
cross-source context merging, frequency tracking, and every real
protection analysis (Distance/Overcurrent/Differential).

## Analysis shell visual polish (2026-09-12)

Layout/typography/spacing only — no engineering behavior, resolver,
estimator, or Playback semantics changed. See
[CURRENT_STATE.md](CURRENT_STATE.md)'s own "Analysis page shell received
a visual polish pass" paragraph for the full detail; summarized here:
the outer `.ww-analysis-shell`/`.ww-analysis-type-nav`/
`.ww-analysis-content` structure was already analyzer-agnostic (Phasor
already rendered as one panel nested inside it) — this pass made that
visually obvious (compact nav, restrained borders, a consistent
context-bar → Playback-ribbon → two-column-body vertical rhythm) and is
the pattern a future analyzer (Impedance Locus/Overcurrent/
Differential/Sequence Components) reuses without redesigning the shell.
Normal Analysis-workspace UI text is capped at 0.75rem (owner
instruction); the shared page title/description keep the larger app-wide
scale. The Playback ribbon is now one compact row (Restart/Play/Speed/
seek/time) via `display: contents` + a scoped `order` on the wrapper
only — the shared `wwCreatePlaybackControlsHtml()` markup and every
`.ww-tg-playback-*` class remain byte-for-byte unchanged (as of
2026-09-12 this is Phasor's own mount alone — see "Playback controls are
now Analysis-only" below). No `Polar View`/visualization-mode selector
was added.

## Playback controls are now Analysis-only (2026-09-12)

Owner product decision, later the same day the "Phasor Playback
integration" section above shipped: Playback CONTROLS (Restart/Play/
speed selector/seek slider) are exposed on Analysis pages only — the raw
Waveform Time Group toolbar no longer mounts them. See
[DECISIONS.md — DEC-085's own "Update (2026-09-12)"](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock)
for the full record, including the verification performed before
implementing (no prior task/commit for this removal existed; it directly
reverses a previously-shipped, previously-tested piece of DEC-085's own
original design).

Phasor's own mount (`wwPhasorMountPlaybackControls()`) is completely
unaffected — it never mounted via the Waveform toolbar's own code path,
so this section's own architecture above is unchanged in every respect
except one sentence's own premise ("the Waveform Time Group toolbar
already mounts" this surface — no longer true; corrected in place
above). `wwCreateTimeGroupCanvasDom()`/`wwWireTimeGroupToolbar()` simply
no longer call the shared factory/wiring functions; every other shared
Playback primitive (the controller, the coordinate, the one-active-group
rule, the container-parameterized factory/wiring/sync functions) is
byte-for-byte unchanged, since Phasor's mount already depended on all of
them working exactly as they always have.

**The dedicated Playback Cursor overlay is explicitly preserved** on the
Waveform Time Group canvas — a PASSIVE readout of the shared clock, not
a control, so it is not part of "Playback controls." An engineer can
still watch the moving cursor on the actual waveform trace while driving
Playback entirely from an Analysis page. This surfaced one small,
genuine gap, fixed in the same change: the overlay only actually renders
while the Waveform page itself is the visible one, and nothing
previously re-checked that when merely NAVIGATING to Waveform (only an
active Playback tick, or an action taken while already on that page, did
before) — `shellSetCurrentPage()` now resyncs the active group's own
overlay whenever Waveform newly becomes the visible page, mirroring the
pre-existing `wwScheduleResizeAllVisiblePlots()` call in the same spot.

Future analyzers (Impedance Locus/Overcurrent/Differential/Sequence
Components) mount Playback controls exactly the way Phasor does today —
this decision does not change that reusable pattern, only that Waveform
itself is no longer also a mount point for it.

## Not yet implemented (future slices)

- **Frequency tracking / PMU-class measurement.**
- **Precomputed vendor phasor channel support.**
- **Per-Unit phasor display** (`unit_mode=per_unit`).
- **Manual Engineering Context creation/editing UI** — the UAT fix
  (2026-09-11) added an AUTOMATIC suggestion bootstrap for the empty-
  workspace case, but there is still no frontend affordance to manually
  create a context, edit its membership, correct a phase, or re-run
  suggestions on demand for a source that already has one; the
  Playwright suite for genuinely manual/edge-case scenarios (ambiguous
  membership, phase correction) still seeds state directly via the
  backend API.
- **Distance/Impedance, Overcurrent, Differential, Sequence Components**
  — these slices prove the estimator/resolver/UI integration only.

## Related documents

- [DECISIONS.md — DEC-088](DECISIONS.md#dec-088--phasor-analysis-slice-1-a-fixed-frequency-one-cycle-trailing-window-rms-fundamental-phasor-estimator-with-an-explicit-guardrail-boundary-and-a-selected-time-only-read-only-api-built-directly-on-the-existing-engineering-context-resolver-foundation) — Slice 1's full approval record.
- [DECISIONS.md — DEC-089](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules) — Slice 2's full approval record, including its own "Update (2026-09-12)" section covering the bay-centric redesign.
- [ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md) — the
  Engineering Context + resolver foundation both slices are built on
  entirely unchanged.
