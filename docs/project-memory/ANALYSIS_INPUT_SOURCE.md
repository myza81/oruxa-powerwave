# Analysis Input Source — shared architecture

**Status: implemented for Overcurrent only** (Manual Input / Calculator
mode, 2026-09-16, see
[DECISIONS.md — DEC-095](DECISIONS.md#dec-095--a-shared-analysis-input-source-concept-recordingmanual-is-introduced-overcurrent-gets-the-first-manual-input--calculator-mode-implementation)).
This document records the shared concept and pattern so a future
analyzer (Phasor, Impedance Locus, Sequence Components, Distance) can
reuse it without re-deriving the design from scratch — mirroring how
[ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) records the other three
shared Analysis-workspace primitives (Engineering Context lifecycle,
Playback, Related Waveforms). Analyzer-specific engineering behavior
(the actual IEC IDMT/CT/unit-normalization calculation) stays documented
in [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) — this document is
scoped to the input-source SHELL/pattern those docs both consume.

## The concept

Every Analysis-menu analyzer's own current INPUT can come from one of
two sources:

```text
recording   -- the existing waveform/Playback-driven behavior. Default
               for every analyzer; unchanged production behavior.
manual      -- a directly-entered engineering value (a standalone
               hypothetical/test calculation), evaluated against the
               SAME analysis settings via the SAME calculation engine,
               with zero waveform/channel/Engineering-Context/Playback
               dependency.
```

The architectural principle, restated from the task that introduced it:

> **The analyzer should not care whether its normalized input came from
> waveform extraction or manual entry — only the SOURCE of the current
> changes; the calculation engine and the chart must serve both.**

```text
Recording source                       Manual source
     |                                       |
waveform extraction / RMS         validation / engineering-unit
     |                                  normalization
     v                                       |
normalized engineering input <---------------+
     |
existing analysis engine (unchanged)
     |
result + chart
```

## Naming convention — shared, not analyzer-specific

`WW_ANALYSIS_INPUT_SOURCE_RECORDING`/`WW_ANALYSIS_INPUT_SOURCE_MANUAL`
(frontend, `frontend/index.html`, declared once near the other shared
Analysis-workspace constants) — deliberately named `WW_ANALYSIS_*`, not
`WW_OC_*`, even though Overcurrent is this concept's first and (this
slice) only implementation. A future analyzer's own manual mode reuses
these SAME two constants rather than inventing its own vocabulary.

**Input-source selection itself is per-analyzer, never shared/global.**
Each analyzer owns its OWN `inputSource` field and its OWN manual-value
state (today: `wwOvercurrentState.inputSource`/`wwOvercurrentState.manual`)
— exactly like `selectedContextId` is already per-analyzer
(`wwOvercurrentState.selectedContextId` is independent of
`wwPhasorState.selectedContextId`). An engineer may run Phasor against
live recording data while Overcurrent runs a Manual what-if calculation
in the very same workspace, or vice versa. A single shared mutable
"current input source" object across all analyzers was considered and
rejected for exactly this reason — see DEC-095's own "Alternatives
considered."

## Backend pattern

No generic backend "Analysis Input Source" abstraction/base class was
introduced — the task's own explicit "do not prematurely build unused
generic abstraction layers beyond what OC needs; keep it progressive"
instruction. What IS shared, and what a future analyzer's own manual
mode should reuse, is:

1. **The existing shared engineering-unit layer**
   (`app.domain.engineering_units.convert_value_to_canonical()`/
   `convert_array_to_canonical()`, see
   [ENGINEERING_UNITS.md](ENGINEERING_UNITS.md)) for normalizing the
   manually-entered value's own declared unit — never a second, local
   unit-conversion dictionary.
2. **The analyzer's own existing calculation primitives**, applied to
   the normalized manual value instead of a waveform-derived RMS
   estimate. For Overcurrent: `convert_to_relay_secondary()` (CT ratio,
   unchanged since DEC-091) and the newly-extracted
   `evaluate_multiple_and_operating_time()` (factored out of the
   recording path's own inline calculation specifically so both paths
   call the identical function — see
   [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) for the full
   detail). **Never duplicate the analyzer's own core formula in a
   second, manual-only engine.**
3. **A dedicated, workspace-scoped (never Engineering-Context-nested)
   endpoint**, since a manual value has no context/channel/phase/time
   at all — for Overcurrent, `GET .../overcurrent-manual`, a sibling of
   the existing context-independent `.../overcurrent-characteristics`/
   `.../overcurrent-curve` endpoints, not a variant of the context-
   nested `.../overcurrent` calculation endpoint.
4. **A result shape reusing the SAME field names** the analyzer's
   existing chart/rendering code already reads (for Overcurrent:
   `multiple_of_pickup`/`relay_secondary_current`/
   `expected_operating_time_seconds`), while genuinely OMITTING fields
   that don't exist for a standalone value (Overcurrent's
   `ManualOvercurrentAnalysisResult` has no `engineering_context_id`/
   `phase`/`analysis_time`/`channel_ref`/`above_pickup_duration_seconds`/
   `threshold_exceeded`) — never forcing an analyzer's manual result
   into the exact same schema as its recording result merely for
   convenience.

## Frontend pattern

1. **A compact segmented control** ("Input Source: Recording | Manual"),
   visually consistent with whatever segmented-control CSS classes the
   analyzer's panel already establishes elsewhere (Overcurrent reused
   its own existing `.ww-oc-axis-toggle-group`/`-btn`/`--active` classes
   verbatim, from the Pickup Multiple/Relay Current toggle) — never a
   second toggle visual language.
2. **Relay/analysis settings are never duplicated** inside the manual
   section — they remain the SAME shared, authoritative configuration in
   both modes; only the manual section's own current-value/unit/basis
   fields are analyzer-specific and mode-specific.
3. **One shared settings-changed dispatcher** decides which pipeline
   fires based on the active input source (`wwOvercurrentHandleSettingsChanged()`
   calls `wwOvercurrentRequestManualAnalysis()` in Manual mode,
   `wwOvercurrentRequestExactPlaybackFetch()` in Recording mode) —
   changing a shared setting always updates the shared state regardless
   of mode; only the RECOMPUTE pipeline differs.
4. **The manual result never auto-applies to an inactive mode's own
   cached values, and vice versa** — a stale/late-resolving recording
   fetch in flight at the moment the user switches to Manual (or a stale
   manual fetch resolving after switching back to Recording) must never
   clobber the OTHER mode's own UI. Both render functions guard on the
   currently active `inputSource` at their own very top.
5. **The manual value's own validity is checked client-side before any
   request is sent** (blank/NaN/Infinity/negative/zero rejected
   locally) — "avoid sending requests while the numeric value is
   incomplete/invalid." Unsupported unit / invalid CT ratio remain
   backend-authoritative (never duplicated client-side).
6. **Debounce via the existing "change" event convention** — every
   manual field fires its own recompute on the native `change` event
   (blur/Enter), exactly like every other settings field in the
   analyzer's own panel already does. No live per-keystroke "input"
   listener and no additional timer/debounce mechanism were introduced;
   this was a deliberate design choice to stay consistent with existing
   UX rather than inventing a new interaction pattern for one field.
7. **The SAME chart renders both modes' own point** — never a second
   chart. A manual point gets a purely cosmetic modifier (Overcurrent:
   `.ww-oc-manual-marker`, a distinct dashed ring, plus an SVG
   `<title>Manual input point</title>` tooltip) so it always reads as
   "a manual/test point," never mistaken for a genuine recording-driven
   result.
8. **Playback stays shared/global but never drives the manual result.**
   The existing Playback tick handler's own fetch-triggering half is
   gated off while Manual is the active input source; the transport-UI-
   sync half (Play/Pause/seek-slider position) stays unconditional,
   since Playback itself remains one authoritative, shared clock
   (DEC-085) regardless of which analyzer or input source is currently
   displayed. No second timer/clock was introduced.
9. **Shared Related Waveforms declares zero active roles in Manual
   mode** — never fabricates a manual waveform. The shared component's
   own EXISTING generic empty state
   (`#wwAnalysisRelatedWaveformsEmptyState`, "No related waveform
   signals available for the current analysis.") already covers this;
   no new UI/text was invented, per the task's own "choose the least
   disruptive implementation consistent with the current shared
   component architecture" instruction. A future analyzer wanting more
   specific wording for its own Manual mode could extend the shared
   empty-state message to accept analyzer-supplied context, but that
   was judged unnecessary for this first implementation.
10. **Manual values are session/UI state only** — never persisted to
    the backend/database, never written to a calculated channel, never
    touching original recording data. Reset to Recording/defaults only
    by the analyzer's own full state-recreation hook (for Overcurrent,
    `wwOvercurrentResetState()`, the same "Start New Workspace"/"Clear
    workspace" hook every other analyzer-local display preference
    already uses).

## What Overcurrent's own implementation looks like end to end

```text
GET /api/v1/workspaces/{workspace_id}/overcurrent-manual
    ?characteristic_id=iec_standard_inverse&tms=0.10
    &pickup_current_secondary=1.0
    &input_current=30000&input_current_unit=A&recording_basis=primary
    (&ct_primary=1200&ct_secondary=1, required only when recording_basis=primary)
```

Golden worked example (owner's own): pickup 1.0 A secondary, CT
1200:1, manual input 30000 A primary → normalizes to 30000 A (already
amperes) → CT ratio applied (`30000 * (1/1200)`) → 25 A secondary → `M
= 25/1.0 = 25` → expected operating time from the selected IEC
characteristic/TMS via the SAME `evaluate_idmt_operating_time()` the
recording path uses. Verified end-to-end via a real HTTP call with zero
prior upload/context/source setup
(`test_overcurrent_analysis_api.py::TestManualAnalysisEndpoint::test_golden_30000_a_primary_via_http`)
and in a real browser
(`browser-tests/overcurrent_analysis.spec.js`'s own "golden example"
scenario).

## Explicitly deferred (not this slice)

- **Phasor Manual mode** (and every other future analyzer's own manual
  mode) — the task's own explicit "do not implement Phasor Manual mode
  yet" instruction. This document exists so that future slice can reuse
  the pattern above without re-deriving it.
- **A generic cross-analyzer "Analysis Input Source" backend
  abstraction/base class** — deliberately not built; see "Backend
  pattern" above for what IS shared today (the engineering-unit layer,
  the analyzer's own existing calculation primitives) versus what stays
  analyzer-specific (the endpoint, the result shape).
- **Persisting manual input values** across a page reload/new session —
  session/UI state only, matching every other Overcurrent chart/settings
  preference's own established ephemeral-by-design precedent.
- **A more specific Related Waveforms empty-state message** for Manual
  mode specifically (e.g. "Related Waveforms are available in Recording
  mode.") — the shared component's own existing generic empty state was
  judged sufficient for this first implementation; a future slice could
  extend it if UAT finds the generic wording insufficiently clear.

## Related documents

- [DECISIONS.md — DEC-095](DECISIONS.md#dec-095--a-shared-analysis-input-source-concept-recordingmanual-is-introduced-overcurrent-gets-the-first-manual-input--calculator-mode-implementation) — this slice's full approval record.
- [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) — Overcurrent's own
  engineering definition/architecture, including the Manual Input
  calculation path's own detailed record.
- [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) — the other three
  shared Analysis-workspace primitives (Engineering Context lifecycle,
  Playback, Related Waveforms) this concept's own frontend pattern
  builds on top of.
- [ENGINEERING_UNITS.md](ENGINEERING_UNITS.md) — the shared
  engineering-unit normalization layer Manual mode reuses for its own
  input-value normalization.
