# Phasor Analysis

**Status: Slice 1 (Core Estimator + Selected-Time API) is implemented**
— see [DECISIONS.md — DEC-088](DECISIONS.md#dec-088--phasor-analysis-slice-1-a-fixed-frequency-one-cycle-trailing-window-rms-fundamental-phasor-estimator-with-an-explicit-guardrail-boundary-and-a-selected-time-only-read-only-api-built-directly-on-the-existing-engineering-context-resolver-foundation).
Frontend, Playback integration, and every real protection analysis
(Distance/Overcurrent/Differential/Sequence Components) remain
unimplemented — this document records the engineering definition and
architecture the audit established and this slice built, so a later
slice does not need to re-derive it.

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
actually generalize). Never persisted.

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

## Not yet implemented (future slices)

- **Frontend** — no Phasor Analysis page, no diagram, no Analysis menu.
- **Playback integration** — no `wwPlayback` subscription; `analysis_time`
  is a plain request parameter, not driven by a moving clock yet.
- **Frequency tracking / PMU-class measurement.**
- **Precomputed vendor phasor channel support.**
- **Per-Unit phasor display** (`unit_mode=per_unit`).
- **Distance/Impedance, Overcurrent, Differential, Sequence Components**
  — this slice proves the estimator/resolver integration only.

## Related documents

- [DECISIONS.md — DEC-088](DECISIONS.md#dec-088--phasor-analysis-slice-1-a-fixed-frequency-one-cycle-trailing-window-rms-fundamental-phasor-estimator-with-an-explicit-guardrail-boundary-and-a-selected-time-only-read-only-api-built-directly-on-the-existing-engineering-context-resolver-foundation) — this slice's full approval record.
- [ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md) — the
  Engineering Context + resolver foundation this slice is built on
  entirely unchanged.
