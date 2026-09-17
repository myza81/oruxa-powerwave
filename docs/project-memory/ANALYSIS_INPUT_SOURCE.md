# Analysis Input Source — shared architecture

**Status: implemented for Overcurrent, Phasor, and Impedance Locus.**
Overcurrent shipped first (Manual Input / Calculator mode, 2026-09-16,
see
[DECISIONS.md — DEC-095](DECISIONS.md#dec-095--a-shared-analysis-input-source-concept-recordingmanual-is-introduced-overcurrent-gets-the-first-manual-input--calculator-mode-implementation),
amended 2026-09-16 by the architectural correction below); Phasor is
the second implementation, reusing the SAME shared shell from day one
(DEC-095's own second amendment, same day — see "What Phasor's own
implementation looks like end to end" below); Impedance Locus is the
third, same-day-shape implementation
([DECISIONS.md — DEC-096](DECISIONS.md#dec-096--impedance-locus-v1-the-third-analysis-menu-analyzer-apparent-phase-impedance-measurementvisualization-explicitly-not-distance-protection),
2026-09-17), extending Phasor's own "N independent bases for N
independent physical quantities" principle with one more independent
axis — see
[IMPEDANCE_LOCUS_ANALYSIS.md](IMPEDANCE_LOCUS_ANALYSIS.md)'s own
"Primary/Secondary basis" section for the full detail.
This document records the shared concept and pattern so a future
analyzer (Sequence Components, Distance) can
reuse it without re-deriving the design from scratch — mirroring how
[ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) records the other three
shared Analysis-workspace primitives (Engineering Context lifecycle,
Playback, Related Waveforms). Analyzer-specific engineering behavior
(the actual IEC IDMT/CT/unit-normalization calculation) stays documented
in [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) — this document is
scoped to the input-source SHELL/pattern those docs both consume.

## Governing invariant (owner requirement, 2026-09-16 architectural correction)

> **Manual Input is a standalone engineering-calculator path and MUST
> NOT depend on recordings, Engineering Context, Time Groups, Playback,
> or waveform availability.**
>
> **Recording prerequisites are mode-specific and must never globally
> disable Manual-capable analyzers.**

`Manual mode = standalone engineering calculator`;
`Recording mode = recording-dependent analysis`. Manual is never a
sub-mode of an already-active recording analysis, and a recording-side
prerequisite (no source uploaded, no Engineering Context resolvable, no
Time Group, no Playback) must gate ONLY the Recording half of an
analyzer's own panel — never the analyzer as a whole. An analyzer's own
first implementation of this concept (Overcurrent, below) is the
reference pattern any future Manual-capable analyzer should copy.

The first implementation shipped this same day (2026-09-16) briefly got
this wrong: `wwOvercurrentShowEmptyState()` hid the WHOLE analyzer body
(`#wwOvercurrentBody`), which at the time also contained Manual's own
controls, whenever no Engineering Context existed yet. That coupling
was found and corrected the same day — see "Markup separation" below
for the structural fix, and DEC-095's own amendment note.

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
`WW_OC_*`, even though Overcurrent was this concept's first
implementation. **Confirmed reusable exactly as designed**: Phasor's own
Manual Input slice imports these SAME two constants verbatim (asserted
directly by a static test that both declarations count to exactly `1`
in the file) rather than inventing its own vocabulary — the first real
proof this concept generalizes beyond its original analyzer.

**Input-source selection itself is per-analyzer, never shared/global.**
Each analyzer owns its OWN `inputSource` field and its OWN manual-value
state (`wwOvercurrentState.inputSource`/`wwOvercurrentState.manual`,
`wwPhasorState.inputSource`/`wwPhasorState.manual`) — exactly like
`selectedContextId` is already per-analyzer
(`wwOvercurrentState.selectedContextId` is independent of
`wwPhasorState.selectedContextId`). An engineer may run Phasor against
live recording data while Overcurrent runs a Manual what-if calculation
in the very same workspace, or vice versa. A single shared mutable
"current input source" object across all analyzers was considered and
rejected for exactly this reason — see DEC-095's own "Alternatives
considered."

**A per-analyzer manual state object may itself need MULTIPLE
independent bases, not just one.** Overcurrent's own manual value has
exactly one basis (Primary/Secondary current). Phasor's manual state
has TWO, genuinely independent of each other:
`wwPhasorState.manual.voltageBasis` (governs Va/Vb/Vc, with its own
VT/PT ratio) and `wwPhasorState.manual.currentBasis` (governs Ia/Ib/Ic,
with its own CT ratio) — changing one never touches the other's own
basis, ratio, or values. **This is a hard rule, not a stylistic
preference**: a single shared "Primary | Secondary" switch covering
both quantities was considered and explicitly rejected (see "What
Phasor's own implementation looks like end to end" below), since
Voltage and Current are measured through physically different
instrument transformers (VT/PT vs. CT) with independently-chosen
ratios — an engineer must be able to enter, for example, Primary-basis
voltages alongside Secondary-basis currents in the same diagram. **A
future analyzer with N independent physical quantities should expect N
independent bases in its own manual state, not one shared switch,
whenever those quantities are measured through independent
instrumentation.**

**Manual basis controls must never reinterpret Recording data.**
Recording mode's own interpretation of a resolved channel's values
continues to come entirely from that channel's own recording/
configuration metadata (or, for Overcurrent, its own separate
`recordingBasis` field, populated independently of Manual's `manual.*`
state) — Manual's own basis/ratio fields are a completely separate
piece of state that the Recording pipeline never reads, and vice versa.
Toggling `wwPhasorState.manual.voltageBasis` has ZERO effect on how the
currently-selected Engineering Context's own Va/Vb/Vc are computed, and
toggling Recording's own basis/settings has zero effect on Manual's own
entered values.

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
9. **Shared Related Waveforms panel is hidden/collapsed entirely in
   Manual mode, never shown with a fabricated or generic-empty-state
   waveform** (revised 2026-09-16 — supersedes this document's original
   "reuse the shared generic empty state" choice). Both options were
   considered again during the architectural correction: showing the
   panel with a generic "no waveform" message still implies the panel
   is *relevant* to Manual mode, when it structurally never can be (a
   manual value has no waveform, ever, not just none available right
   now). Hiding/collapsing the whole panel — the same visibility gate
   that already hides the rest of the Recording-only section — was
   judged the cleaner, less misleading design, and is what ships today.
   Overcurrent still declares zero active roles in Manual mode as a
   defense-in-depth (`wwOvercurrentComputeActiveRelatedWaveformRoles()`
   returns `[]` whenever `inputSource !== recording`), so even if a
   future change re-exposed the panel by mistake, it could never render
   a fabricated waveform.
10. **Manual values are session/UI state only** — never persisted to
    the backend/database, never written to a calculated channel, never
    touching original recording data. Reset to Recording/defaults only
    by the analyzer's own full state-recreation hook (for Overcurrent,
    `wwOvercurrentResetState()`, the same "Start New Workspace"/"Clear
    workspace" hook every other analyzer-local display preference
    already uses).

## Markup separation (2026-09-16 architectural correction)

The concrete structural fix behind the invariant above. An analyzer's
own panel must split into three independent regions, not two:

```text
#<analyzer>Panel
├── Input Source toggle          -- ALWAYS visible, a direct child of
│                                    the panel itself, never nested
│                                    inside the Recording-only section
│                                    below it (otherwise hiding that
│                                    section would also hide the only
│                                    control that could switch back out
│                                    of Manual mode).
├── #<analyzer>RecordingSection  -- Bay/Context selector, Playback
│   (single `hidden` toggle,        panel, Related Waveforms anchor,
│    driven by `inputSource`)       and the Recording-only empty state
│                                    all live INSIDE this one wrapper.
│                                    Its `hidden` attribute is the ONE
│                                    place Recording-vs-Manual
│                                    visibility is decided — every
│                                    control inside it may assume a
│                                    recording is the active source.
└── #<analyzer>Body              -- Relay/analysis settings, Manual
    (never hidden by any             Input's own fields, results list,
     recording-lifecycle              and chart. Requires NEITHER a
     callback)                        recording NOR Manual's own state
                                       to render — visible the instant
                                       the analyzer's panel itself is
                                       open.
```

For Overcurrent specifically: `#wwOvercurrentRecordingSection` wraps
the Bay/Context bar, `#wwOvercurrentPlaybackPanel`,
`#wwOvercurrentRelatedWaveformsAnchor`, `#wwOvercurrentStatusRow`, and
`#wwOvercurrentEmptyState`; `#wwOvercurrentBody` (Settings/Manual
Input/Results/Chart) sits outside it as a sibling.
`wwOvercurrentShowEmptyState()` — the callback every recording-lifecycle
phase (`NO_SOURCES`/`NO_SUGGESTIONS`/`UNREACHABLE`/no context selected)
funnels through — now touches only `#wwOvercurrentRecordingSection`'s
own empty-state paragraph, never `#wwOvercurrentBody`. A CSS
`[hidden]` pitfall already documented elsewhere in this codebase
(`.ww-phasor-body[hidden]`, `.ww-phasor-panel[hidden]`,
`.ww-phasor-field[hidden]`) applies here too: giving the Recording
section its own `display: flex` requires an explicit
`#wwOvercurrentRecordingSection[hidden] { display: none; }` override,
since a class's own `display` declaration otherwise defeats the
browser's native `[hidden]` behavior.

## Recording availability and mode auto-selection

Recording is "available" once at least one Engineering Context exists
for the analyzer to select — the same signal the Bay/Context selector
itself needs to be useful. This availability drives three things:

1. The Recording segment's own `disabled` state — **never fully
   hidden**, so the two-input-source concept stays understandable even
   when Recording is temporarily unusable ("Recording (disabled) |
   Manual", with hint text such as "No recording loaded. Manual mode is
   available.").
2. The supporting hint text's visibility.
3. A **one-time automatic correction** of the current selection — but
   only while the engineer has never deliberately clicked either
   segment themselves for this analyzer instance (`inputSourceAutoSelected`
   stays `true` until the first explicit click). A workspace with zero
   recordings auto-selects Manual; a workspace where a recording later
   becomes available auto-selects Recording — but only ever as long as
   the engineer hasn't already chosen a side. A deliberate user choice
   is never overridden merely because availability changed later.

The auto-switch check itself only ever fires while the analyzer's own
tab is genuinely the visible one (`wwAnalysisActiveType === "overcurrent"`
for Overcurrent) — never eagerly at global page-load time, since
`contexts` starts empty on every raw page load and an eager check would
fire a real Manual-mode calculation request in the background before
the user ever opens Analysis at all. It re-runs lazily at three natural
trigger points: whenever the shared Engineering Context lifecycle
publishes a fresh context list or phase, and once more the moment the
engineer actually switches onto the analyzer's own tab (so a change
that happened while the tab was hidden is still reflected promptly).

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

## What Phasor's own implementation looks like end to end

```text
GET /api/v1/workspaces/{workspace_id}/phasor-manual
    ?voltage_basis=primary&vt_primary=132000&vt_secondary=110
    &current_basis=primary&ct_primary=1200&ct_secondary=1
    &va_enabled=true&va_magnitude=132&va_unit=kV&va_angle_deg=0
    &vb_enabled=true&vb_magnitude=132&vb_unit=kV&vb_angle_deg=-120
    &vc_enabled=true&vc_magnitude=132&vc_unit=kV&vc_angle_deg=120
    &ia_enabled=true&ia_magnitude=1200&ia_unit=A&ia_angle_deg=-30
    &ib_enabled=true&ib_magnitude=1200&ib_unit=A&ib_angle_deg=-150
    &ic_enabled=true&ic_magnitude=1200&ic_unit=A&ic_angle_deg=90
```

Workspace-scoped only (like `.../overcurrent-manual`) — never nested
under an Engineering Context. Every one of the six roles
(Va/Vb/Vc/Ia/Ib/Ic) is independently optional (`*_enabled=false`, or a
missing magnitude, simply reports that role `missing` — never blocking
the other five, task's own explicit partial-input policy). `roles` in
the response reuses `PhasorDiagramRoleResultOut` VERBATIM — the exact
same type Recording mode's own `/phasor-diagram` response uses — so the
SAME frontend renderer (`wwPhasorRenderDiagramResult()`/
`wwPhasorRenderDiagramSvg()`) consumes either result unmodified, with
zero new rendering code.

**Canonical internal phasor representation: Secondary**, matching
Overcurrent's own DEC-095 precedent (never a Phasor-specific reason to
prefer one basis — Phasor's Recording-mode result carries no basis
concept at all to match against, so consistency across analyzers was
the only real constraint). `convert_manual_magnitude_to_secondary()`
(`app/domain/phasor.py`) normalizes a Primary-basis entry via its own
family's VT/PT or CT ratio (`secondary = primary_value_in_canonical_unit
* (ratio_secondary / ratio_primary)`) before it ever reaches the
renderer; a Secondary-basis entry skips the ratio step entirely. One
function serves BOTH Voltage and Current (parameterized on
`engineering_quantity`) — Overcurrent never needed this generalization
since it only ever deals with one quantity.

**Per-role, per-family failure isolation** (`evaluate_manual_phasor_role()`):
an invalid or missing role never affects any other role's own
independent evaluation. An invalid Voltage basis or VT/PT ratio blocks
every role in the VOLTAGE family only (`ROLE_STATUS_NEEDS_CONFIGURATION`,
the SAME role status Recording mode already uses for its own per-role
failures) — Current roles are completely unaffected, and vice versa for
an invalid CT ratio. A role that is simply not entered reuses the
EXISTING `ROLE_STATUS_MISSING` status. **No new role-status vocabulary
was introduced** — the shared renderer needed zero changes to support
Manual mode's own failure modes.

**Angle normalization** reuses the EXISTING, previously-private
`_normalize_angle_deg()` Recording mode's own `angle_deg_relative`
computation already established (`(-180, 180]` convention) — never a
second, Manual-only normalization function. `240°` entered reports as
`-120°`, exactly as the owner's own example specifies.

**Alternatives considered** for the Voltage/Current basis question
(see "Naming convention" above for the resulting hard rule): a single
shared `wwPhasorState.manual.basis` covering both quantities was
considered and rejected — VT/PT and CT are physically independent
instrument transformers with independently-chosen ratios, and an
engineer must be able to mix Primary-basis voltages with Secondary-
basis currents (or vice versa) in the same diagram; forcing one shared
switch would make that combination impossible to express.

Golden worked example (owner's own): VT 132000/110, CT 1200/1, Primary
Va/Vb/Vc = 132 kV ∠ 0°/-120°/+120°, Primary Ia/Ib/Ic = 1200 A ∠
-30°/-150°/+90° → normalizes to 110 V / 1 A Secondary-equivalent for
every role, angles unchanged. Verified end-to-end via a real HTTP call
with zero prior upload/context/source setup
(`test_phasor_diagram_api.py::TestManualPhasorDiagramEndpoint::test_golden_owner_worked_example_via_http`)
and in a real browser
(`browser-tests/phasor_analysis.spec.js`'s own "golden owner worked
example" scenario) — both independently confirm the same normalized
values. The task's own mixed-basis case (Voltage Primary, Current
Secondary) is separately golden-tested at every layer, proving the two
basis selectors are genuinely independent, not merely independently
labeled.

## Explicitly deferred (not this slice)

- **Sequence Components and Distance's own Manual mode** — not started;
  this document exists so those future slices can reuse the pattern
  above (including, where relevant, Phasor's own "N independent bases
  for N independent physical quantities" extension, and Impedance
  Locus's own further extension to a THIRD, independent OUTPUT basis)
  without re-deriving it.
- **A generic cross-analyzer "Analysis Input Source" backend
  abstraction/base class** — deliberately not built; see "Backend
  pattern" above for what IS shared today (the engineering-unit layer,
  the analyzer's own existing calculation primitives) versus what stays
  analyzer-specific (the endpoint, the result shape).
- **Persisting manual input values** across a page reload/new session —
  session/UI state only, matching every other analyzer's own
  established ephemeral-by-design precedent.
- **Automatic CT/VT ratio lookup from a Recording's own metadata** —
  the engineer always enters VT/PT and CT ratios manually in this
  slice; Recording-basis auto-detection remains a separate, unstarted
  problem, deliberately not solved here (task's own explicit "if
  Recording basis is genuinely unknown, preserve current behavior; do
  not solve that separate problem in this task" instruction).

## Related documents

- [DECISIONS.md — DEC-095](DECISIONS.md#dec-095--a-shared-analysis-input-source-concept-recordingmanual-is-introduced-overcurrent-gets-the-first-manual-input--calculator-mode-implementation) — this slice's full approval record, including the Phasor amendment.
- [DECISIONS.md — DEC-096](DECISIONS.md#dec-096--impedance-locus-v1-the-third-analysis-menu-analyzer-apparent-phase-impedance-measurementvisualization-explicitly-not-distance-protection) — Impedance Locus's own approval record, the third implementation.
- [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) — Overcurrent's own
  engineering definition/architecture, including the Manual Input
  calculation path's own detailed record.
- [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md) — Phasor's own engineering
  definition/architecture, including the Manual Input / Calculator
  mode's own detailed record.
- [IMPEDANCE_LOCUS_ANALYSIS.md](IMPEDANCE_LOCUS_ANALYSIS.md) — Impedance
  Locus's own engineering definition/architecture, including the third,
  independent OUTPUT basis extension this feature adds.
- [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) — the other three
  shared Analysis-workspace primitives (Engineering Context lifecycle,
  Playback, Related Waveforms) this concept's own frontend pattern
  builds on top of.
- [ENGINEERING_UNITS.md](ENGINEERING_UNITS.md) — the shared
  engineering-unit normalization layer Manual mode reuses for its own
  input-value normalization.
