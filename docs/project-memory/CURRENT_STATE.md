# Current State — `oruxa_powerwave`

> This document is operational truth, not a history log. It describes where
> the project **is right now** — what is implemented, what is
> architecturally true, what is intentionally deferred, and what comes
> next. For how the project got here (phase-by-phase implementation
> records, UAT chronology, individual bug fixes), use
> [DECISIONS.md](DECISIONS.md), [HANDOFF.md](HANDOFF.md), and Git history.
> Do not let this file accumulate into a diary — when updating it, replace
> superseded claims, don't append to them.

Last meaningful update: **2026-09-20** (fixed a genuine production race
— toggling a channel display immediately after opening a just-uploaded
recording could wipe the entire channel sidebar with a misleading
"Could not reach the backend" message; see its own entry below in
[Implemented capabilities](#implemented-capabilities)).
**Event Playback
([DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock),
its own 2026-09-11 revision) is implemented as a shared, reusable
WORKSPACE CAPABILITY — never a standalone top-level page.** Following
owner UAT of the original Slice 1/2 controls (Play/Pause/Resume/
Restart/speed/seek all signed off) and subsequent workflow discussion,
the owner reversed Playback's original top-level-menu placement: **no
`Playback` main-menu item or page exists** (removed outright — no
`Analysis` menu was created in its place either). ONE authoritative,
frontend-only Playback Controller (`wwPlayback`, `frontend/index.html`)
owns the current playback time for at most ONE active Time Group at a
time — pressing Play on a different Time Group's own toolbar cleanly
stops the previous one, never two simultaneous `requestAnimationFrame`
loops; every source/channel in that group shares the same playback
time, channels are never independently played. Canonical coordinate is
**workspace time** (the same coordinate `ww.viewport`/Cursor A-B
already use); `t=0`/Time Mode affect display only (reuses
`wwFormatCursorPointTime()` verbatim, no new clock). Playback range is
the active Time Group's own full union extent
(`wwDeriveTimeGroupBounds(groupId)`, the existing DEC-037 function).
Timing is `requestAnimationFrame` + a `performance.now()` wall-clock
anchor, recomputed fresh every frame. The **Playback Cursor is
architecturally separate from Cursor A/B** — its own dedicated DOM
overlay (`.ww-tg-playback-cursor-overlay`), reusing Cursor A/B's
pixel-conversion primitives but never touching
`ww.timeGroupCursorState`. Digital-channel state at the current
playback time resolves entirely from already-loaded local transition
data (zero backend requests per frame). A fixed seven-value speed
selector (0.05×/0.10×/0.25×/0.5×/1×/2×/4×, default 1×, never free-entry
— extended below 0.25× on 2026-09-12 for slow engineering-event/fault
inspection — ONE controller-wide `wwPlayback.speed`, persists across Play/Pause/
Restart/seek) and a seek scrubber (a native `<input type="range">`,
the dedicated seek mechanism — never a drag on the Playback Cursor
itself, never Cursor A/B; suspends the clock during a drag/keyboard
gesture, re-anchors and resumes automatically on release only if it
was playing before, otherwise lands "paused"; selects a TIME only,
never fabricates/interpolates engineering data) round out the everyday
transport. **Playback CONTROLS are Analysis-only (owner product
decision, 2026-09-12) — the raw Waveform Time Group toolbar no longer
mounts them at all**, reversing the earlier "waveform toolbar is
Playback's built-in consumer" shape (see [DECISIONS.md — DEC-085's own
"Update (2026-09-12)"](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock)
for the full record). The everyday transport is a shared, reusable
control-surface API — `wwCreatePlaybackControlsHtml()` (markup factory),
`wwWirePlaybackControls(containerEl, groupId)` (wiring),
`wwSyncPlaybackControls(containerEl, groupId)` (state-transition sync),
`wwUpdatePlaybackControlsTick(containerEl, groupId)` (per-tick
refresh) — all four container-parameterized (never an internal "the
Time Group canvas" lookup), mounted today ONLY by Phasor
(`wwPhasorMountPlaybackControls()`); a future engineering-analysis page
(Distance Protection/Overcurrent/Differential, none implemented yet)
mounts the exact same markup/wiring/sync into its own container and
subscribes via the existing `wwPlaybackOnTick()` seam for its own moving
operating point, without needing to know
`requestAnimationFrame`/`performance.now()`/how the shared cursor works.
The Waveform Time Group canvas still shows the **passive** Playback
Cursor overlay (a readout of the shared clock, not a control) —
`shellSetCurrentPage()` resyncs it for the active group whenever the
Waveform page newly becomes visible, so it never shows a stale position
after Playback was driven from elsewhere while Waveform was hidden.
**Frontend/session state only — no backend Playback
endpoint exists or was added**; state resets on `wwClearWorkspace()`
(both "Clear workspace" and "Start New Workspace", including speed
back to 1×) and whenever the active Time Group's own topology
disappears. Deferred to a later slice (not implemented, not decided
against): Follow Playback, Split View `center_time` integration,
throttled current-value polling, keyboard shortcuts, event sub-range
selection, looping, reverse playback, frame-by-frame stepping, and
every future analysis overlay (impedance/overcurrent/differential/
etc.), which must consume this controller rather than build an
independent clock and which Playback itself must stay ignorant of
(no Va/Vb/Vc, impedance, phasor, or differential knowledge anywhere in
the controller). The full existing Playwright suite
(`browser-tests/playback.spec.js`, 12 tests) passes UNMODIFIED after
the navigation-removal/reusability refactor — the strongest evidence
this was a pure internal reorganization with zero externally-visible
behavior change; `backend/tests/test_frontend_playback.py` (51 static
structural tests) was revised to assert the new reality (no dedicated
menu/page, genuinely container-parameterized reusable functions,
zero duplicated timing/seek logic); full backend regression passes
unchanged. See [Implemented capabilities](#implemented-capabilities)
for the full per-decision rationale (mirrors DEC-085, not duplicated
twice).

**Analysis Guardrail Slice 1 — Engineering Context + durable phase
identity ([DECISIONS.md — DEC-086](DECISIONS.md#dec-086--analysis-guardrail-slice-1-engineering-context-physicallogical-bay-identity-and-durable-canonical-phase-are-established-as-a-new-additive-metadata-layer-kept-fully-independent-of-measurement-groupsper-unit-and-of-no-fixed-value-until-a-later-slices-automatic-analysis-input-resolver-reads-it),
2026-09-11) is implemented as a new, purely additive backend metadata
layer.** `EngineeringContext` (`app.domain.engineering_context`)
identifies a physical/logical bay/equipment — deliberately a SEPARATE
concept from `MeasurementGroup`, which stays a kind-specific
Per-Unit-base-configuration concern; the two coexist independently and
a channel may belong to both. A context is **workspace-scoped, not
source-scoped** — it may span more than one uploaded source/file, since
a physical bay's Voltage and Current channels may legitimately arrive
in separate files for the same event. Membership uses `ChannelRef`
(unchanged shape) plus a separate `EngineeringContextMember` wrapper
carrying durable, canonical phase identity
(`app.domain.phase_identity`: `A`/`B`/`C`/`N`/`AB`/`BC`/`CA`/`unknown`/
`not_applicable`) and provenance
(`engineer_confirmed`/`manual`/`structured_metadata`/
`detected_from_name`/`unknown`, an ordering — never a numerical
confidence score — that guarantees a confirmed/manual assignment is
never silently overwritten). Convention-aware normalization resolves
the genuinely ambiguous raw token `"B"` (canonical B under A/B/C,
canonical C under R/Y/B) from the OTHER phase evidence present in the
same context, never guessing when evidence is absent/conflicting.
Automatic single-source-only detection
(`app.domain.engineering_context_detection`) clusters Voltage AND
Current channels sharing one name-derived root into ONE candidate
context (cross-kind, unlike Measurement Group detection's own
kind-scoped clustering), reuses the exact same
`suggested`/`confirmed`/`needs_review`/`manual` status vocabulary
Measurement Groups already established, and is additive-only/idempotent
— and has a narrow source-local fallback for bare role-only channel
names (`VA`/`VB`/`VC`/`IA`/`IB`/`IC`, plus R/Y/B equivalents) that
creates one neutral "Default Context" when unambiguous; duplicate or
conflicting bare roles still produce `needs_review`, never a silent
choice. A channel already claimed by any existing context is never
reconsidered on a re-run. No completeness requirement and no
engineering-type restriction on membership (a single "Va" is a valid
context; a calculated channel may be a member). New workspace-scoped
REST surface: `GET/POST .../engineering-contexts`, `GET/PATCH/DELETE
.../engineering-contexts/{id}`, `PATCH .../engineering-contexts/{id}/
member-phase`, and the source-scoped, explicit-trigger-only `POST
.../sources/{source_id}/engineering-contexts/suggest` — **no
`/analysis/...` resolver endpoint exists yet**, out of scope for this
slice. In-memory `EngineeringContextRegistry` mirrors
`MeasurementGroupRegistry`'s own lifecycle discipline; removing one
source prunes only the affected members (a context may still have
valid members from other sources) rather than deleting the whole
context. **No frontend changes in this slice** (deliberately deferred —
backend/API capability was the explicit requirement; a minimal UI is
future-slice scope). No `MeasurementGroup`/`ChannelRef`/Per-Unit/
calculated-channel/Playback/Time-Group behavior changed — 111 new
focused tests (`test_phase_identity.py`,
`test_engineering_context_domain.py`,
`test_engineering_context_detection.py`,
`test_engineering_context_registry.py`,
`test_engineering_context_service.py`,
`test_engineering_context_api.py`) plus the full existing regression
suite all pass unmodified. See
[ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md) for the
full architecture — the automatic resolver/requirement-definition layer
this foundation was built for is now implemented too, see immediately
below.

**Analysis Guardrail Slice 2 — Analysis Requirements + Automatic Input
Resolver ([DECISIONS.md — DEC-087](DECISIONS.md#dec-087--analysis-guardrail-slice-2-a-small-typed-analysisrequirementrolespec-domain-plus-a-pure-backend-authoritative-resolver-automatically-match-an-analysis-modes-required-engineering-roles-against-one-engineering-contexts-own-membership-role-identity-and-numerical-readiness-are-kept-strictly-separate),
2026-09-11) is implemented on top of Slice 1's foundation.** A small,
typed `AnalysisRequirement`/`RoleSpec` domain
(`app.domain.analysis_requirements`) declares eight representative
Phasor input-role requirements (single-phase A/B/C + three-phase, for
both Voltage and Current) — never a general-purpose rules engine; these
identify which waveform samples a future phasor engine needs, they do
NOT calculate a phasor. A pure resolver
(`app.domain.analysis_input_resolution.resolve_requirement()`) matches
each required role against one Engineering Context's own membership by
`engineering_type` + canonical `phase` **only — never by channel name**;
an unresolved (`unknown`) phase structurally never matches any
concrete-phase role, so "never guess an unconfirmed phase" falls out of
exact-value matching rather than needing a special case. Status
vocabulary: `resolved` (every role maps to exactly one candidate and,
for cross-source roles, a proven-compatible timebase); `needs_configuration`
(role-level diagnostics distinguish `role_missing` from
`phase_identity_missing` from `timebase_incompatible`);
`ambiguous` (more than one candidate matches one role — **never
resolved by preference**, not by raw-vs-calculated origin, name, or
detection confidence; every candidate is returned for the engineer to
disambiguate via Slice 1's own phase/membership-correction endpoints,
which are sufficient — no new override subsystem was introduced);
`not_applicable` (reserved, not reachable by any current requirement).
**Role identity and numerical calculation readiness are kept strictly
separate**: a blank-unit channel still resolves as its role (Powerwave
knows what signal it is) but a whole-resolution `numerically_ready: bool`
flag separately reports readiness; Per-Unit display mode has zero
effect on resolution (the resolver never reads `ww.unitMode` or any
presentation state). Timebase compatibility reuses
`app.domain.calculated_channel.timebases_aligned()` completely
unchanged, applied by the SERVICE layer
(`app.services.analysis_input_resolution_service`) only AFTER role
matching has already narrowed things to one candidate per role — same-
source roles short-circuit instantly, never resamples/interpolates. One
new read-only endpoint: `GET .../engineering-contexts/{id}/
input-resolution?analysis_kind=...&mode=...`, nested under the
Engineering Context it resolves against (mirrors Measurement Groups'
own nested-derived-view precedent) rather than a new top-level
`/analysis/...` router. **No generic frontend UI was built** — the
owner decided the first resolver-driven UI will be Phasor Analysis
itself, to avoid a placeholder that would be immediately replaced; this
slice is backend/domain/API only. Automatic cross-source context
detection remains deferred (Slice 1 stays single-source-only; a
manually-confirmed multi-source context is sufficient to exercise every
multi-source resolver scenario). 40 new focused tests
(`test_analysis_requirements.py`, `test_analysis_input_resolution_domain.py`,
`test_analysis_input_resolution_service.py`,
`test_analysis_input_resolution_api.py`) plus the full existing
regression suite pass unmodified. See
[ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md) for the
full architecture, including what's still deferred (frontend UX,
Playback integration, digital-channel roles, Voltage↔Current
association).

**Phasor Analysis Slice 1 — Core Estimator + Selected-Time API
([DECISIONS.md — DEC-088](DECISIONS.md#dec-088--phasor-analysis-slice-1-a-fixed-frequency-one-cycle-trailing-window-rms-fundamental-phasor-estimator-with-an-explicit-guardrail-boundary-and-a-selected-time-only-read-only-api-built-directly-on-the-existing-engineering-context-resolver-foundation),
2026-09-11) is implemented — the first real analysis engine built on
the Slice 1/2 guardrail foundation.** Product definition: an RMS
fundamental-frequency phasor estimated from a sampled Voltage/Current
waveform over one trailing cycle at a FIXED reference frequency —
explicitly not an instantaneous sample, not PMU/synchrophasor-class,
not frequency-tracked. Estimator (`app.domain.phasor.estimate_phasor()`):
`X = (sqrt(2)/N) * sum(x_n * exp(-j*2*pi*f0*t_n))`, `magnitude_rms =
abs(X)`, `angle = arg(X)` — the RMS normalization proven algebraically
and confirmed against independently hand-derived golden values, never
self-referential ones. Window: exactly one trailing cycle, half-open
`(analysis_time - 1/f0, analysis_time]`, reusing `evaluate_rms()`'s own
boundary convention exactly; an incomplete window is explicitly
`unavailable`, never shortened/shifted. **Angle is referenced to one
shared, source-independent absolute-time coordinate computed once per
request — never reset per sliding window** (proven numerically stable
as `analysis_time` advances); a three-phase result additionally derives
a Phase-A-referenced `angle_deg_relative` as a pure display transform
over the authoritative absolute value. Reference frequency: an explicit
override, else every resolved role's own source must agree on
`nominal_frequency` or the result is `needs_configuration`/
`reference_frequency_conflict` — never hard-coded to 50 Hz, both 50 Hz
and 60 Hz validated explicitly; off-nominal behavior (magnitude error,
progressive angle drift) is measured and documented via a closed-form
golden test, never hidden. `PHASOR_MIN_SAMPLES_PER_CYCLE = 8` is a
Phasor-SPECIFIC threshold empirically derived from a 4/8/16/32-
samples/cycle sweep (never blindly copied from RMS's own `=4`) — an
application guardrail based on measured behavior, not a claimed
industry standard. Waveform-form eligibility mirrors `check_rms_
eligibility()`'s own metadata-first/detector-fallback structure, but
STRICTER: both `likely_magnitude_or_rms` and `uncertain` detector
outcomes are rejected outright (no override exists in this slice) — a
deliberate revision of the original audit's own earlier "allow
uncertain with a warning" suggestion, corrected after re-examining what
the real RMS precedent actually does. Integrates the unchanged Slice 2
resolver as the sole authority: any non-`resolved` status is returned
verbatim, with zero name-based channel search/phase remapping/cross-
context borrowing. Engineering units only (no Per-Unit `unit_mode` in
this slice); selected-time-only (one phasor per request, never a
time series, never persisted). One new read-only endpoint: `GET
.../engineering-contexts/{id}/phasor?analysis_kind=...&mode=...&
analysis_time=...&reference_frequency_hz=...(optional)`. Measured
performance on a representative 20 kHz/10 s (200,000-sample) source:
~0.8 ms/call for the pure estimator, ~19 ms/call for the full service
(resolver + waveform-form detector fallback), ~33 ms/call full HTTP
round trip — all comfortably fast for an on-demand request; no
caching/precomputation introduced. **No Playback integration, no real
protection analysis (Distance/Overcurrent/Differential/Sequence
Components)** — explicitly out of scope for this slice (frontend/the
Analysis menu were out of scope for Slice 1 specifically and are now
implemented by Slice 2, immediately below). 55 new focused tests (`test_phasor_
domain.py` 30 — golden RMS/angle/three-phase/50-60Hz/moving-analysis-
time-stability/off-nominal-frequency/edge-of-recording/invalid-samples/
irregular-sampling/sampling-density-study vectors, `test_phasor_
analysis_service.py` 18, `test_phasor_analysis_api.py` 7 — including a
real hand-written ASCII-COMTRADE upload carrying a known three-phase
sinusoid through the full HTTP stack) plus the full existing regression
suite pass unmodified. See [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md) for
the full architecture.

**Phasor Analysis page (`Analysis > Phasor Diagram`) is implemented and
is BAY-CENTRIC, not Quantity/Mode-centric** — see
[PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md) for the full architecture and
[DECISIONS.md — DEC-089](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)
(base entry, 2026-09-11) and its own "Update (2026-09-12)" section (the
bay-centric redesign) for the approval history. `Analysis` is a
PERMANENT top-level main-menu destination (`#mainNavAnalysisBtn`, after
Calculated Channels; sidebar tooltip/label read "Phasor Diagram", the
page's own `<h2>` heading stays "Analysis"), hosting a left-hand
analysis-type list that will grow to Distance Protection/Overcurrent/
Differential/Sequence Components later — only `Phasor` exists today.

**Selecting an Engineering Context (Bay) is the ONLY primary control** —
there is no Quantity/Mode selector. Selecting a context requests all six
supported single-phase roles (`Va`/`Vb`/`Vc`/`Ia`/`Ib`/`Ic`) together via
ONE aggregated backend call (`GET .../phasor-diagram`, backed by the new
`compute_phasor_diagram()` service function, alongside the original,
still-unchanged `compute_phasor_analysis()`/`GET .../phasor`). A partial
bay (e.g. only `Va`+`Ia`) is a normal, useful result — one role being
`missing`/`ambiguous`/`needs_configuration`/`not_eligible` never blocks
any other role's own row; a combined-diagram-blocking condition
(reference-frequency conflict, timebase incompatibility) is the ONLY
thing that produces a whole-result `needs_configuration` banner. There
is **no manual raw-channel picker** anywhere in this workflow.

**Individual vector visibility is a pure frontend display preference**
(`wwPhasorState.visibleRoles`) — clicking a role's own row (reusing the
exact `#channelGroups` row-as-toggle-button convention Waveform channel
visibility already established) hides/shows it with a cheap local
re-render only, never a new backend request. Default: every role that
computes `available` starts visible; visibility persists throughout
Playback (Play/Pause/Seek/Speed/Restart/an analysis-time change) and
resets to "all available roles visible" only when the selected
Engineering Context genuinely changes (tracked via
`wwPhasorState.lastLoadedContextId`, since the context-load function
itself also re-runs on every mere page revisit). This state never
touches Engineering Context membership, phase identity, resolver rules,
or Measurement Groups.

**The combined diagram's vector geometry uses `angle_deg_absolute`
only** — Voltage and Current are never independently zero-referenced
against their own family, preserving the true V-I angular relationship;
the redesigned Values list shows only that same absolute angle (never
`angle_deg_relative`), guaranteeing the table can never disagree with
what the diagram draws. **Voltage and Current use SEPARATE graphical
magnitude scales** (`Va`/`Vb`/`Vc` share one, `Ia`/`Ib`/`Ic` share
another, both normalized to the same outer plot radius) — GRAPHICAL
ONLY, `magnitude_rms` itself is never altered, and the scale ratio
between the two families is always shown transparently alongside the
diagram (e.g. "Current vectors scaled ×15.27 for display"). Current
vectors are drawn dashed, Voltage solid, both still colored by the
existing `--ww-phase-a/b/c` tokens (reusing the app's own accent/warn/ok
trio, deliberately not Cursor A/B's tokens) — phase identity and
quantity type are both visible without inventing unrelated colors.

**Phasor's analysis time is now driven by the ONE shared, pre-existing
`wwPlayback` controller (DEC-085) — no separate "Analysis Time" input
exists any more.** Phasor mounts the SAME reusable Playback control
surface (`wwCreatePlaybackControlsHtml()`/`wwWirePlaybackControls()`/
`wwSyncPlaybackControls()`) the Waveform Time Group toolbar already
mounts; the seek scrubber IS Phasor's own time control. Selecting a
context whose own resolved Time Group is already `wwPlayback`'s active
group reads its current time verbatim (Waveform and Phasor share one
clock across page navigation); selecting a not-yet-active group claims
it via the existing, unchanged `wwPlaybackRestart()` (landing at
`bounds.start`, honestly reporting insufficient history there if
applicable), then refines the landing position to a more useful starting
time as a one-time convenience — never applied to the mounted Restart
BUTTON itself, which always uses the bare function and lands at
`bounds.start`. A Playback tick drives a throttled (~10 Hz,
measured endpoint latency ~28–44 ms), concurrency-safe fetch
(`wwPhasorRequestDiagram()`, "one request in flight + latest desired
time, never a growing queue"); Pause/Restart/a seek release/Playback
reaching its own end all converge to an EXACT (non-throttled) fetch at
the settled time. Each family's own diagram scale is established from
its first valid result and held fixed for the "playback run" (never
silently shrunk, to keep real magnitude movement visible), released only
on Restart or a genuine context switch. Analysis time is still workspace
time under the hood (the same coordinate Cursor A/B already use),
converted to source-relative elapsed time only at the API call boundary
— the conversion anchor is the selected context's own first member (a
coordinate-conversion convenience, never a role-matching decision). A
single shared `requestGeneration` counter plus the existing `ww.epoch`
guard protect every fetch against a stale response overwriting a newer
selection; a pure visibility toggle never touches this counter, since it
never issues a request. See [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)'s
own "Phasor Playback integration" section for the full architecture.

**Phasor auto-bootstraps Engineering Context suggestions, SOURCE-
COVERAGE driven, not workspace-empty-driven.** `wwPhasorLoadContexts()`
fetches the context list; whenever at least one context already exists,
the selector/body render from it IMMEDIATELY (never blanked), while any
OTHER loaded source not yet covered by any context's own membership
(`channel_ref.source_id`, determined via `wwPhasorCoveredSourceIds()` —
never display name/status/count/order) is discovered quietly in the
background (a subtle `#wwPhasorDiscoveringIndicator` text, never the
full-page empty state). If NO context exists yet, discovery runs
blocking, exactly like the original "Identifying engineering contexts…"
experience. Either way: the existing, unchanged Guardrail Slice 1
suggestion endpoint is called once per UNCOVERED source (never
assuming one source is "the" bay); a fresh, nothing-existed-before
bootstrap auto-selects the first newly-created context, but discovering
an ADDITIONAL uncovered source while a bay was already open never
auto-selects the new one and never resets the existing selection. A
PER-SOURCE `Set` (`wwPhasorState.attemptedSourceIds`, reset only on
"Start New Workspace"/"Clear workspace") replaces the original single
workspace-wide `bootstrapAttempted` boolean — a source uploaded AFTER
the workspace's first context already existed is no longer silently
skipped forever; only a source that was individually already attempted
is not immediately re-suggested on every mere page revisit. Suggested/
needs_review contexts are never hidden or auto-upgraded — detection
still only suggests, engineer confirmation remains authoritative. The
backend detector also handles the real-UAT bare role-only source shape
(`VA`/`VB`/`VC`/`IA`/`IB`/`IC`) by creating one suggested "Default
Context" per source when the roles are unambiguous — two different
bare-role sources correctly produce two independently-tracked contexts
even though both share that same display name (coverage is keyed by
source id, never by name). See [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)'s
own "Automatic Engineering Context bootstrap" section for the full
architecture.

**The Analysis page shell received a visual polish pass (2026-09-12) —
layout/typography/spacing only, no workflow/behavior change.** The
outer shell (`.ww-analysis-shell`/`.ww-analysis-type-nav`/
`.ww-analysis-content`) was already analyzer-agnostic; this pass made it
visibly so, establishing the reusable pattern a future analyzer
(Impedance Locus/Overcurrent/Differential/Sequence Components) follows:
its own panel (today `#wwPhasorPanel`) stacks context bar → Playback
ribbon → two-column body with one consistent vertical rhythm
(`.ww-phasor-panel { display:flex; flex-direction:column; gap:12px }`,
replacing several ad-hoc `margin-top` rules). Normal Analysis-workspace
UI text (nav items, field labels, selectors, Playback controls, table
values, badges, annotations) is capped at **0.75rem** — only the shared
page title/description keep the app's larger heading scale. The context
bar restructures the Bay selector and its status badge onto one aligned
row below the "Bay / Engineering Context" label (previously the badge
sat next to the label text, reading detached from the control it
describes). The Playback ribbon is now one compact row — Restart/Play/
Speed/seek slider/time-readout — via `display: contents` on the mounted
transport wrapper plus a scoped `order` on the (still byte-for-byte
unchanged) shared `.ww-tg-playback-seek-row`/`.ww-tg-playback-time-
readout` classes, never altering the shared markup/behavior those
classes also serve for the Waveform Time Group toolbar. The Inputs/
Values rows got a small, additive markup change (the magnitude text is
now its own `<span class="ww-phasor-value-magnitude">`, alongside the
pre-existing `.ww-phasor-value-angle`) purely so both align to
consistent column stops — the computed values themselves are untouched.
The Phasor Diagram panel gained more breathing room (max width 460px →
500px). No `Polar View`/visualization-mode selector was added — deferred
until a genuine second view exists. See this task's own final report and
`backend/tests/test_frontend_phasor_analysis.py::TestAnalysisShellVisualPolish`
for the full before/after and verification detail.

**No Per-Unit display, no neutral-phasor roles (`Vn`/`In`), no sequence
components/impedance/distance, no automatic cross-source context
merging, no MANUAL Engineering Context creation/editing UI** —
explicitly out of scope. The dedicated ASCII-COMTRADE test fixture
(`phasor_smoke_three_phase.cfg/.dat`, a known three-phase sinusoid) backs
both the static structural suite (test_frontend_phasor_analysis.py) and
the real-browser Playwright suite (`phasor_analysis.spec.js` — the
bay-centric scenario plus a dedicated Playback-integration describe
block: Play/repeated-aggregated-results/no-context-mutation, Pause exact
convergence, seek-while-paused exact convergence, 4× speed throttling,
Restart honesty, context-switch-while-playing, and Waveform↔Phasor
shared-clock interoperability). No backend files were touched for the
Playback integration itself (frontend-only, consuming the existing
`/phasor-diagram` endpoint and the existing, unchanged `wwPlayback`
controller) — full backend regression, full frontend static suite, and
full Playwright suite all pass. A real `[hidden]`-vs-`display:grid/flex`
CSS bug was found and fixed during Slice 2's own Playwright testing
(unrelated to the redesign, still in effect).

**Engineering Context discovery/bootstrap is owned by the shared
Analysis WORKSPACE, not by any individual analyzer (2026-09-12 owner
UAT fix, [DECISIONS.md — DEC-089's own "Update (2026-09-12)"](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)).**
Fixes a UAT-reported bug: opening `Overcurrent` directly after an
upload (never visiting Phasor first) could leave the Bay/Engineering
Context selector empty, since discovery/bootstrap used to live entirely
inside Phasor's own code path. `wwRenderAnalysisPage()` now calls one
shared `wwAnalysisLoadContexts()` regardless of which analyzer tab is
active; Phasor/Overcurrent (and every future analyzer) register as
CONSUMERS via `wwAnalysisRegisterContextConsumer()` rather than
independently fetching/discovering contexts — **this is the pattern any
future analyzer (Impedance Locus/Differential/Sequence Components) must
follow; a `wwXxxLoadContexts()` of its own would reintroduce this same
bug.** Selection/empty-state-message/discovering-indicator stayed
analyzer-specific by design. No backend files touched. See
[OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md)'s own "Shared
Analysis Engineering Context lifecycle" section for the full
architecture.

**Shared Analysis "Related Waveforms" panel is implemented — a third
shared Analysis workspace primitive (2026-09-12,
[DECISIONS.md — DEC-089's own "Update (2026-09-12)"](DECISIONS.md#dec-089--phasor-analysis-slice-2-analysis-is-a-new-permanent-top-level-menu-hosting-a-growing-family-of-engineering-analyzers-phasor-is-the-first-rendering-the-existing-slice-1-backend-as-a-static-selected-time-page-with-a-lightweight-svg-diagram-never-reimplementing-backend-engineering-rules)).**
A compact, context-aware, analyzer-aware waveform preview directly
below Playback in each analyzer's own panel — one shared DOM instance
reparented (never cloned) between analyzers, grouped by engineering
family (Voltage/Current, each its own y-axis/unit), driven by a shared
vertical Playback-time cursor (`Plotly.relayout()` only, never a
re-fetch on tick). Core invariant: **the analyzer decides WHAT signals
are relevant (`wwAnalysisSetRelatedWaveformRoles(roles, contextId,
groupId)`); the shared Analysis workspace decides HOW those are
fetched, grouped, rendered, and synchronized.** Phasor's own existing
vector-visibility toggle now also controls its waveform trace (no
second visibility control); Overcurrent's own existing Phase selector
drives its one Current role (no second channel selector, never a
Voltage role). Reuses the EXISTING `/waveform` endpoint verbatim (no
new backend endpoint), per-channel cached, never refetched per Playback
tick. User-resizable height (a vertical drag handle reusing the
EXISTING `.ww-resize-handle` class the Waveform page's own per-channel-
panel resize already established) is session-local frontend state
only. A real regression was caught and fixed during implementation:
both analyzers' own tick handlers kept computing while hidden, causing
the two to fight over the shared state and thrash waveform re-fetches
every tick — fixed via an explicit `wwAnalysisActiveType` visibility
gate. See [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) (new document,
consolidating all three shared Analysis primitives) for the full
architecture.

**Overcurrent Analysis v1 (2026-09-12,
[DECISIONS.md — DEC-090](DECISIONS.md#dec-090--overcurrent-analysis-v1-the-second-analysis-menu-analyzer-iec-idmt-characteristic-evaluation-against-a-one-cycle-trailing-rms-current-at-the-shared-playback-driven-analysis-time))
is implemented as the SECOND Analysis-menu analyzer** — Phasor remains
the first. Evaluates a recorded event's own one-cycle trailing RMS
current, at the shared Playback-driven `analysis_time`, against a
configured IEC IDMT characteristic (Standard/Very/Extremely Inverse;
`t = TMS * k / ((I/Is)^alpha - 1)`, IEC 60255-151, constants cross-
verified against multiple independent sources and a worked-example
numerical check — see
[OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md)). Current-role
resolution reuses the unchanged Analysis Input Resolver via three new
`OVERCURRENT_CURRENT_PHASE_A/B/C` requirement constants (the identical
single-phase-current role shape Phasor's own `PHASOR_CURRENT_PHASE_A/B/C`
already use, under a distinct `analysis_kind`). A NEW selected-time
trailing-RMS estimator (`estimate_trailing_rms_at_time()`) mirrors
`estimate_phasor()`'s own window/guardrail shape (inspected `evaluate_
rms()` first, per explicit task instruction, and confirmed its own
array-sliding-window interface does not fit an arbitrary continuous
Playback-driven instant); a separate `continuous_duration_above_pickup()`
DOES reuse `evaluate_rms()`'s own array form directly, and is a
deterministic, Playback-speed-independent pure function of `analysis_time`
and the full recorded array (verified by seeking directly to a point
with no prior call). Pickup is always relay-secondary amperes;
`recording_basis="primary"` requires validated CT primary/secondary
values, `"secondary"` performs no conversion. `expected_operating_time_
seconds` is `None` whenever at or below pickup — never a fabricated
Infinity/NaN/0. **Powerwave never claims a relay operated, should have
operated, or failed to operate** — "expected operating time"
(characteristic-derived) and "above-pickup duration" (event-recording-
derived) are kept strictly separate; a qualified `threshold_exceeded`
comparison of the two is the only "alert," always worded as an
observation, never a relay-operation claim. Mounts the SAME shared
Playback control surface Phasor already uses (the THIRD consumer of the
ONE `wwPlayback` controller, DEC-085) — switching Phasor <-> Overcurrent
never creates an unrelated time position. Curve geometry (characteristic
+ TMS only) is cached and refetched only on a settings change, never per
Playback tick. A second `[hidden]`-vs-`display:flex` CSS bug (this time
on `.ww-phasor-panel`/`.ww-phasor-field`, both now shared by Overcurrent
too) was found and fixed the same way Slice 2's own equivalent bug was.
API: `GET .../overcurrent-characteristics`, `GET .../overcurrent-curve`,
`GET .../engineering-contexts/{id}/overcurrent` — same router file/
nesting convention as Phasor's own endpoints. No backend files outside
the new `app/domain/overcurrent.py`/`app/services/
overcurrent_analysis_service.py`/`app/schemas/overcurrent_analysis.py`
modules were touched; full backend regression, full frontend static
suite, and full Playwright suite all pass.

**Shared engineering-unit normalization is implemented (2026-09-13,
[DECISIONS.md — DEC-091](DECISIONS.md#dec-091--shared-engineering-unit-normalization-appengineeringunits-becomes-the-one-authoritative-parsingnormalizationcanonical-conversion-layer-for-every-analyzer-fixing-a-real-overcurrent-uat-defect)),
fixing a real Overcurrent UAT defect** — a `2.4 kA` primary current
through a `1200:1` CT produced `0.002 A` instead of the correct `2.0 A`,
because `convert_to_relay_secondary()` applied the CT ratio to the raw
`2.4` without ever normalizing it to amperes first. Per explicit owner
instruction, this was fixed as a shared architecture gap (`backend/app/
domain/engineering_units.py`, new), not a private `kA * 1000` special
case: one authoritative module now owns parsing/alias-normalization/
canonical-unit lookup/scalar-array conversion for Voltage (V/kV/MV),
Current (A/kA), Active Power (W/kW/MW/GW), Reactive Power (var/kvar/
Mvar/Gvar), Apparent Power (VA/kVA/MVA/GVA — newly first-class, was only
reachable via the generic broad `POWER` category before), Frequency
(Hz), and ROCOF (Hz/s). A deliberate closed, quantity-aware alias
table — never generic `.lower()` SI-prefix parsing — since real files
carry inconsistent casing (`KA`/`ka`, `mw` meaning megawatt not
milliwatt); lowercase `m`/`M`/`g`/`G` always means mega/giga in this
domain, never milli, and anything not explicitly listed is `unsupported`,
never guessed. Overcurrent's `convert_to_relay_secondary()`/new
`convert_array_to_relay_secondary()` now normalize the measured current
to amperes via this module BEFORE applying the CT ratio, for both the
selected-time RMS and the full array driving `continuous_duration_
above_pickup()` (golden scenario verified end-to-end: 2.4 kA primary, CT
1200:1, pickup 0.8 A secondary -> relay current 2.0 A, multiple 2.5x); an
unresolvable unit is a new `needs_configuration`/`unsupported_current_unit`
guardrail, never a silently-wrong number. Per Unit's own multiplier
VALUES are now sourced from this module (its own more-permissive
case-folded lookup breadth is deliberately unchanged, preserving all
existing PU tests byte-for-byte). Phasor (never does cross-unit
arithmetic) and Calculated Channels (`units_compatible()` requires exact
unit-string equality — safe but restrictive) were audited and left
unchanged by design. See [ENGINEERING_UNITS.md](ENGINEERING_UNITS.md)
for the full architecture, per-consumer audit table, and the
future-analyzer invariant a later analyzer (Distance/Differential/
further Power calculations) must follow.

**Overcurrent chart UX enhancement is implemented (2026-09-13,
[DECISIONS.md — DEC-092](DECISIONS.md#dec-092--overcurrent-chart-ux-enhancement-a-pickup-multiplerelay-current-x-axis-representation-toggle-and-independently-toggleable-majorminor-logarithmic-grid-controls)),
frontend-only, no IDMT/pickup/TMS/CT/RMS/Playback/engineering-unit
behavior changed.** A compact toggle switches the chart's X axis
between the existing normalized Pickup Multiple representation
(`M = Irelay / Ipickup`, default, unchanged) and a new Relay Current
representation (amperes), via the exact `Irelay = M * Ipickup`
relationship — switching is a pure re-render (reuses the already-
fetched curve geometry and already-computed result, zero backend
requests); the exact analytic curve-boundary solve established by the
prior "Curve/viewport boundary alignment" work stays authoritative in
the M domain and is transformed to amperes for display, never
re-solved numerically. Each representation remembers its own X range
independently (Y stays shared, since operating time means the same
thing in both) so switching never lands on an unusable range. A new
pickup-boundary reference line makes the M=1/pickup-amps threshold
visible on the chart for the first time. Major gridlines remain always
visible; two new independently-toggleable minor-gridline checkboxes
(both default OFF) add the classic log-log graph-paper 1-2-5 (X) /
`2..9 x 10^decade` (Y) subdivision convention, unlabeled to avoid
clutter. All new state is session-local, following the exact precedent
`viewport`/`settings` already established. See
[OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md)'s own "Chart X-axis
representation toggle and minor grid controls" section for the full
architecture.

**Overcurrent chart-axis simplification (2026-09-17, frontend-only).** The cosmetic zero-origin/origin-gap convention and the DEC-093 compressed/broken sub-pickup X-axis treatment are retired. Overcurrent charts now use true logarithmic axes that start at positive values only: Pickup Multiple X defaults to `0.1 -> 100`, Relay Current X defaults to `0.1 * pickup -> 100 * pickup`, and Y defaults to `0.1 -> 100 s`. Reset restores those deterministic defaults and no longer depends on `expected_operating_time_seconds`, a stable reference operating time, `0.9 x reference`, or a YMax/10 cap. Relay Current ticks derive from the same M-domain positions scaled by pickup, so M=1 aligns pixel-for-pixel with I=pickup and M=10 aligns with I=10*pickup. Viewport, axis-mode, zoom, and grid changes remain frontend-only and cause zero backend requests; manual custom X/Y ranges still survive playback and settings changes until Reset. IDMT equations, characteristic generation, pickup semantics, operating-point calculation, Manual Input, and Recording Input are unchanged. See [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) and [DECISIONS.md — DEC-094](DECISIONS.md#dec-094--overcurrent-uat-correction-the-x-axis-representation-toggles-real-root-cause-was-css-visibility-not-event-wiring-and-the-pickup-multiple-default-viewport-moves-to-09x-100x) for the current axis policy and retired-history note.

**A shared Analysis Input Source concept (Recording/Manual) is
introduced, with Manual Input / Calculator mode implemented for
Overcurrent only (2026-09-16, [DECISIONS.md — DEC-095](DECISIONS.md#dec-095--a-shared-analysis-input-source-concept-recordingmanual-is-introduced-overcurrent-gets-the-first-manual-input--calculator-mode-implementation)).**
An engineer can type a hypothetical/test current value directly (e.g.
"30000 A Primary") and see it evaluated against the SAME relay settings
via the SAME calculation engine and the SAME chart Recording mode
already uses — no waveform/channel/Engineering-Context/Playback
dependency. A new workspace-scoped `GET .../overcurrent-manual`
endpoint reuses the existing `convert_to_relay_secondary()` and a
newly-extracted `evaluate_multiple_and_operating_time()` (factored out
of the recording path's own previously-inline calculation so both paths
call the identical function) — never a second, manual-only calculation
engine. The new `ManualOvercurrentAnalysisResult` omits recording-only
concepts (`engineering_context_id`/`phase`/`analysis_time`/
`channel_ref`/`above_pickup_duration_seconds`/`threshold_exceeded`) but
shares the recording result's own `multiple_of_pickup`/
`relay_secondary_current`/`expected_operating_time_seconds` field names,
so the existing chart-rendering code needed zero changes beyond a
cosmetic `isManual` flag for a distinct dashed marker. Playback's own
fetch-triggering half is gated off entirely while Manual is active
(never drives the manual result); shared Related Waveforms declares
zero active roles in Manual mode, reusing its own existing generic
empty state. Manual values are session/UI state only. The shared
concept itself (`WW_ANALYSIS_INPUT_SOURCE_RECORDING`/
`WW_ANALYSIS_INPUT_SOURCE_MANUAL`) is deliberately named `WW_ANALYSIS_*`,
not `WW_OC_*`, for future analyzer reuse — Phasor/other analyzers' own
manual mode is explicitly NOT implemented this slice. See
[ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md) (new document) and
[OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md)'s own "Manual Input /
Calculator mode" section for the full architecture.

**Architectural correction, same day (2026-09-16) — Manual Input
decoupled from recordings entirely; DEC-095 amended.** The initial
implementation above shipped with an unintended coupling:
`wwOvercurrentShowEmptyState()` hid the WHOLE analyzer body (Manual
Input's own controls included) whenever no Engineering Context existed
yet, so a genuinely empty workspace (no upload, no source, no context)
could not actually reach Manual mode — contradicting the "standalone
engineering calculator" premise. **Manual Input is a standalone
engineering-calculator path and MUST NOT depend on recordings,
Engineering Context, Time Groups, Playback, or waveform availability;
recording prerequisites are mode-specific and must never globally
disable Manual-capable analyzers.** Fixed by splitting
`#wwOvercurrentPanel` into three independent regions: the Input Source
toggle (always visible, a permanent sibling), a new
`#wwOvercurrentRecordingSection` wrapper holding everything that
genuinely needs a recording (Bay/Context selector, Playback, Related
Waveforms anchor, the recording-only empty state) behind ONE `hidden`
toggle, and `#wwOvercurrentBody` (Settings/Manual Input/Results/Chart)
outside it, never hidden by any recording-lifecycle callback. New
`recordingAvailable`/`inputSourceAutoSelected` state drives the
Recording segment's disabled state (shown, never hidden, with hint text)
and a one-time auto-selection a deliberate user click always overrides.
Related Waveforms is now hidden/collapsed entirely in Manual mode
(superseding the original "generic empty state" choice) since a manual
value structurally never has a waveform. A new empty-workspace golden
Playwright suite (95 OC scenarios total now) exercises this without any
upload at all. See
[ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md#governing-invariant-owner-requirement-2026-09-16-architectural-correction)
and DEC-095's own amendment note for the full record.

**Phasor becomes the second Analysis Input Source implementation, same
day (2026-09-16) — DEC-095 amended a second time.** Manual Input /
Calculator mode implemented for Phasor, reusing the shared shell the
architectural correction above established from day one (never the
flawed intermediate design). Phasor's own manual value spans six
independent roles (Va/Vb/Vc/Ia/Ib/Ic) across TWO genuinely independent
bases — `voltageBasis` (its own VT/PT ratio) and `currentBasis` (its
own CT ratio), a hard requirement since Voltage and Current are
measured through physically independent instrument transformers (an
engineer can mix Primary-basis voltages with Secondary-basis currents
in the same diagram — proven by a dedicated mixed-basis golden test).
This extends DEC-095 with a new general principle: **a future analyzer
with N independent physical quantities should expect N independent
bases in its own manual state, not one shared switch.** A new
workspace-scoped `GET .../phasor-manual` endpoint reuses the shared
engineering-unit layer via a new, generalized
`convert_manual_magnitude_to_secondary()` (`app/domain/phasor.py`,
parameterized on Voltage/Current so ONE function serves both) and
evaluates each role fully independently
(`evaluate_manual_phasor_role()`) — a role not entered reports the
EXISTING `missing` status, an invalid basis/ratio blocks only its OWN
family (`needs_configuration`), never cross-contaminating Voltage and
Current. The result reuses `PhasorDiagramRoleResult` VERBATIM, so the
SAME frontend renderer draws either Recording's or Manual's own result
with zero new rendering code. Canonical internal basis is Secondary,
matching Overcurrent's own precedent. See
[PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)'s own "Manual Input /
Calculator mode" section and
[ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md)'s own "What
Phasor's own implementation looks like end to end" for the full record.

**Bug fix (2026-09-17) — Phasor's Voltage/Current graphical diagram
scales are now fully isolated per Input Source; a Scale-legend
enhancement adds a per-ring breakdown.** Owner-reported defect: Manual
`Va=110V∠45°`/`Ia=10A∠90°` rendered correctly in the Values panel but
under a stale diagram scale (e.g. `I: ... 11500.0 A`) inherited from
elsewhere, collapsing the Current vector to a near-invisible sliver.
Root cause: `wwPhasorState.frozenVoltageScale`/`frozenCurrentScale` —
DEC-089's own Recording-Playback-stability freeze (established from the
first valid result, held fixed for the "playback run") — were shared,
unconditional fields `wwPhasorRenderDiagramSvg()` read/wrote regardless
of `inputSource`, so a scale established under one Input Source (a large
Recording current, or an earlier, larger Manual test value) silently
carried into the other; Voltage had the identical vulnerability. Fixed
by gating the freeze on `inputSource`: Manual now always derives its own
scale fresh from its own currently-enabled values every render (never
reads/writes the Recording-owned frozen fields); Recording's own freeze
policy is completely unchanged. **Invariant going forward: Voltage and
Current graphical scales are independent and derive only from the valid
active phasors of their own family and active Input Source — never from
stale/default/other-mode/other-basis data.** Disabled/missing/
`needs_configuration` roles were already excluded from scale derivation
(`wwPhasorFamilyMaxMagnitude()` only considers `available` roles) and
remain so; an all-zero-magnitude family already safely produces no
Scale-legend line for itself (no divide-by-zero) without affecting the
other family, and was unaffected by this bug. Separately, the corner
Scale legend (owner UAT clarification, 2026-09-16 — replaced a bare
numeric ring label that sat next to the Imaginary axis and read like an
axis tick) now shows each present family's inner/middle/outer ring value
(e.g. `V: 36.7 / 73.3 / 110.0 V`) instead of only the outermost one, via
one shared `wwPhasorRingFracs` fraction set also used by the grid lines/
rings themselves — deliberately NOT reintroducing on-ring numeric labels
(that removed design stays removed) and never implying one shared unit
between the Real/Imaginary axes, which still carry two independent
physical quantities at two independent scales. Frontend-only
(`frontend/index.html`); no backend files touched. New static coverage:
`backend/tests/test_frontend_phasor_analysis.py::TestManualScaleNeverSharesRecordingFrozenState`
plus a revised `TestScaleLegendReplacesImaginaryAxisNumbers`. New/revised
`browser-tests/phasor_analysis.spec.js` scenarios: the owner's exact
repro (Recording's known 100V/40A fixture scale must not survive into
Manual's 110V/10A, and switching back to Recording restores its own
scale exactly), a disabled-large-vector isolation case, an all-zero-
Voltage-family safety case, and a Primary-basis scale-uses-canonical-
secondary assertion added to the existing golden worked-example test.
The full existing backend regression suite and the full Playwright suite
(159 scenarios across all specs, phasor_analysis.spec.js's own 37) pass.
See
[PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)'s own "Diagram scaling stability
during Playback" section for the full technical record.

**Impedance Locus v1 is implemented (2026-09-17,
[DECISIONS.md — DEC-096](DECISIONS.md#dec-096--impedance-locus-v1-the-third-analysis-menu-analyzer-apparent-phase-impedance-measurementvisualization-explicitly-not-distance-protection)),
the THIRD Analysis-menu analyzer** — activates the pre-existing
`Impedance Locus` navigation placeholder (preserving analyzer order:
Phasor, Overcurrent, Impedance Locus, Sequence Components). Calculates
apparent phase impedance `Za=Va/Ia`/`Zb=Vb/Ib`/`Zc=Vc/Ic` via direct
phasor division (`R=|Z|cos(theta)`, `X=|Z|sin(theta)`, using each
phasor's own absolute angle — never an RMS-scalar approximation), and
visualizes it on an equal-scale R-X Cartesian plane, all four quadrants
valid, never clamped. **Explicitly measurement/visualization only — NOT
Distance Protection**: no protection zones, mho/quadrilateral
characteristics, fault loops, residual-current (k0) compensation,
phase-to-phase loops, directional logic, or trip evaluation exist
anywhere in this slice. Recording mode reuses the existing, unchanged
`phasor_analysis_service.compute_phasor_diagram()` verbatim (zero
duplicated FFT/DFT/RMS estimation code) — extracting whichever Voltage/
Current role pair the selected phase (`A`/`B`/`C`, default `A`,
Engineering-Context-resolved, never inferred from a channel name) needs.
A numerical-validity low-current guardrail
(`app.domain.impedance.MIN_CURRENT_A = 1e-3`, 1 mA — explicitly not a
relay pickup threshold) reports `needs_configuration`/
`current_too_small` rather than an unbounded `|Z|`. `recording_basis`
(what the resolved channels already represent) and `impedance_basis`
(the independent desired output basis) require VT/CT ratios only when
they genuinely differ — matching the trivial same-basis case the task's
own golden example uses; Manual mode mirrors Manual Phasor's own two-
independent-basis architecture (Voltage/VT, Current/CT), always
normalized to Secondary-canonical first via the SAME, verbatim-reused
`convert_manual_magnitude_to_secondary()`, with `impedance_basis` acting
as a THIRD, independent output basis on top. The R-X plot uses one
shared px-per-ohm factor for both axes (structurally impossible to
scale R and X independently) and an automatic nice-tick viewport with
headroom. Recording mode adds a genuine locus/trajectory — a new
`GET .../impedance-locus` endpoint samples up to 300 evenly-spaced,
independent, deterministic Impedance calculations across the active
Time Group's own extent, fetched by the frontend only on a context/
phase/settings/time-range change (never per Playback tick, verified by
a static test) — while the live current point remains a separate,
~10 Hz-throttled, Playback-synchronized fetch identical in shape to
Phasor's/Overcurrent's own. Analysis Input Source (Recording/Manual) is
the THIRD real implementation of the DEC-095 shared shell, reusing
`WW_ANALYSIS_INPUT_SOURCE_RECORDING`/`WW_ANALYSIS_INPUT_SOURCE_MANUAL`
and the three-region markup separation verbatim, implemented correctly
from day one. New backend modules only
(`app/domain/impedance.py`/`app/services/impedance_analysis_service.py`/
`app/schemas/impedance_analysis.py`); `app/domain/analysis_requirements.py`
and `app/api/v1/engineering_contexts.py` gained additive-only entries —
zero existing Phasor/Overcurrent/Playback/Engineering-Context production
behavior changed. 33 new domain tests, 16 new API tests (via a real
three-phase ASCII-COMTRADE upload), and 23 new frontend structural tests
pass; two pre-existing structural tests (shared-consumer-count,
mounted-transport-count) were updated for the third registered
analyzer, mirroring the identical precedent Overcurrent's own addition
already set. Full backend regression suite (5247 tests) passes. **No
real-browser Playwright coverage was added this slice** — flagged
honestly for owner UAT, not claimed as verified; see
[IMPEDANCE_LOCUS_ANALYSIS.md](IMPEDANCE_LOCUS_ANALYSIS.md)'s own "Known
limitations" section. `Zab`/`Zbc`/`Zca`, Distance Protection (zones/
mho/quadrilateral/ground compensation/directional logic/trip
interpretation), and automatic Recording-basis detection from recording
metadata all remain unimplemented, reserved for future, separate slices
that this feature's own `ImpedancePoint`/R-X-plane foundation is
deliberately structured to support without requiring this module itself
to change. (Sequence Components, listed here as unimplemented in the
prior revision of this document, is now implemented — see below.)

**Impedance Locus UAT correction, same day (2026-09-17) — Related
Waveforms blank-trace bug and premature full-locus display both
fixed.** The first real-browser (Playwright) verification this feature
ever received (`browser-tests/impedance_analysis.spec.js`, new, 10
scenarios) surfaced two owner-reported bugs the original v1 slice's own
static-tests-only coverage had missed. **(1)** Related Waveforms
rendered empty axes with no Va/Ia trace in Recording mode — root cause:
the pushed role objects never carried `channelRef`, so the shared
panel's own cache key collapsed every role onto the same synthetic
`"none"` key, one (failing) fetch was attempted, and both traces stayed
uncached. Fixed by adding `voltage_channel_ref`/`current_channel_ref` to
`ImpedanceAnalysisResult` (sourced from `compute_phasor_diagram()`'s
own already-resolved channel identity — never re-derived from a channel
name) and threading them through to the frontend role push, which now
also gates on channel-identity-known rather than the whole impedance
`status`, so the Voltage/Current traces stay visible even when the
low-current guardrail blocks the Ω result. **(2)** The full impedance
locus was visible immediately instead of only up to the current
Playback time — fixed with a new `wwImpedanceVisibleLocusCutoffTime()`
that chronologically clips the DRAWN locus path to the already-fetched
exact current point's own `analysis_time` (the same instant that draws
the marker, so trail and marker can never disagree) — the full locus is
still computed/cached upfront exactly as before (zero change to the
fetch/cache/no-per-tick-refetch performance model), and the R-X
viewport intentionally stays sized from the FULL cached locus (a
stable, non-jumping scale from the first render) while only the drawn
path itself grows chronologically. Restart/Seek/Play/Pause/end-of-event
all fall out of this one mechanism with zero special-casing. Two
pre-existing Playwright tests needed scoping fixes as a direct
consequence (an unscoped `.ww-oc-settings-grid` locator in
`overcurrent_analysis.spec.js` now also matches Impedance's own reuse of
that class; `phasor_analysis.spec.js`'s own analyzer-menu test still
asserted the Impedance panel said "not implemented yet"), mirroring
precedents already established elsewhere in this project. Full backend
suite (5254 tests) and full Playwright suite (169 scenarios across every
spec) pass. No IEC/RMS/CT/VT/impedance math, basis conversion,
low-current guardrail, or R/X equal-scale geometry was touched. See
[IMPEDANCE_LOCUS_ANALYSIS.md](IMPEDANCE_LOCUS_ANALYSIS.md)'s own
"Related Waveforms and chronological locus reveal — UAT correction"
section for the full record.

**Sequence Components v1 is implemented (2026-09-18,
[DECISIONS.md — DEC-097](DECISIONS.md#dec-097--sequence-components-v1-the-fourth-analysis-menu-analyzer-positivenegativezero-sequence-voltage-and-current-calculationvisualization)),
the FOURTH Analysis-menu analyzer** — activates the pre-existing
`Sequence Components` navigation placeholder (order preserved: Phasor,
Overcurrent, Impedance Locus, Sequence Components). Calculates the
classical Fortescue symmetrical-component transform
(`a = exp(j*120deg)`, `X0=(Xa+Xb+Xc)/3`, `X1=(Xa+a*Xb+a^2*Xc)/3`,
`X2=(Xa+a^2*Xb+a*Xc)/3`) independently for Voltage (Va/Vb/Vc → V0/V1/V2)
and Current (Ia/Ib/Ic → I0/I1/I2), visualized on one combined polar
phasor diagram with two independent per-family graphical scales.
**Explicitly measurement/calculation/visualization only — NOT protection
interpretation**: no unbalance limits, negative-sequence relay operation
claims, ground-fault analysis, fault classification, sequence-network
diagrams, or sequence impedance exist anywhere in this slice. Recording
mode reuses the existing, unchanged `phasor_analysis_service.
compute_phasor_diagram()` verbatim (zero duplicated FFT/DFT/RMS
estimation code) — the SAME bay-centric aggregator Phasor's own page and
Impedance Locus's own Recording mode already use. Unlike Phasor's own
per-role-independent diagram, Sequence Components mathematically
requires a COMPLETE three-phase set per family before computing anything
(`app.services.sequence_components_analysis_service._evaluate_family()`)
— Voltage and Current families are evaluated fully independently, one
family's own incompleteness (missing/needs_configuration/ambiguous/
not_eligible) never blocking the other. Introduces this codebase's first
genuine complex-number arithmetic (`app.domain.sequence_components`,
stdlib `complex`/`cmath`) — every prior module hand-rolled real/
imaginary bookkeeping for a hot per-sample loop this feature does not
have. Manual mode reuses the Manual Phasor architecture verbatim
(identical six-role, two-independent-basis phase-domain entry form —
never a direct V0/V1/V2 field, since a sequence value is only ever
meaningful when derived from a genuine phase-domain set) via
`evaluate_manual_phasor_role()`/`convert_manual_magnitude_to_secondary()`
(both `app.domain.phasor`, reused verbatim); both Recording and Manual
funnel through the identical `_evaluate_family()` helper, so there is
exactly ONE authoritative symmetrical-component implementation for both
input sources. Sequence ratios (`|V2|/|V1|`, `|V0|/|V1|`, `|I2|/|I1|`,
`|I0|/|I1|`, all percentages) are purely descriptive, guarded against a
near-zero positive-sequence denominator
(`MIN_POSITIVE_SEQUENCE_MAGNITUDE = 1e-9`, numerical validity only,
never a protection threshold) — reports an explicit "Unavailable"
rather than `Infinity`/`NaN`. Color identity is sequence-based
(`--ww-seq-positive`/`--ww-seq-negative`/`--ww-seq-zero`, new dedicated
`frontend/theme.css` tokens), deliberately never reusing the
`--ww-phase-a/b/c` phase-identity tokens. The Recording-Playback-
stability diagram-scale freeze is gated on `inputSource` from day one —
this analyzer never had the Manual/Recording scale-leak bug Phasor's own
diagram once had and later fixed; there was nothing to fix here, only a
precedent to follow. API: `GET .../engineering-contexts/{id}/
sequence-components`, `GET .../sequence-components-manual` — same
router file/nesting convention as every prior analyzer's own endpoints.
No backend files outside the new `app/domain/sequence_components.py`/
`app/services/sequence_components_analysis_service.py`/`app/schemas/
sequence_components_analysis.py` modules were touched (plus additive-
only entries in `app/domain/analysis_requirements.py` and `app/api/v1/
engineering_contexts.py`); full backend regression, full frontend
structural suite, and full Playwright suite all pass. **Real-browser
Playwright coverage was added from day one**
(`browser-tests/sequence_components_analysis.spec.js`, 14 scenarios) —
deliberately closing the exact "no Playwright coverage" gap Impedance
Locus v1's own first slice left open. Two pre-existing, unrelated flaky
Playwright tests (one in `phasor_analysis.spec.js`, one in
`impedance_analysis.spec.js`) were found, diagnosed, and reported
(not silently fixed) during this session's own regression verification
— see [DECISIONS.md — DEC-097](DECISIONS.md#dec-097--sequence-components-v1-the-fourth-analysis-menu-analyzer-positivenegativezero-sequence-voltage-and-current-calculationvisualization)'s
own closing section for the original diagnosis. **Both items are now
closed** (2026-09-19,
[DECISIONS.md — DEC-098](DECISIONS.md#dec-098--analysis-browser-testruntime-hardening-shared-playback-follows-a-time-group-relabel-transparently-the-impedance-locus-cache-race-was-test-only)):
the Phasor Time-Group-ID reassignment was a genuine production race (a
Time Group relabel — DEC-057's own already-approved, unchanged
"`group_id` recomputed fresh, never cached" design — left the shared
`wwPlayback` controller's own cached `activeTimeGroupId` stale, forcing
an unwanted Restart-to-`bounds.start`); fixed with one new reconciliation
function, `wwPlaybackReconcileActiveGroupIdAfterSync()`, called from the
existing `wwFetchSynchronizationStateForWorkspace()` choke point,
re-following a relabel without ever resetting `currentTime`/`state`. The
Impedance locus-cache item was confirmed TEST-ONLY after a full code
audit found the existing `requestGeneration`/`ww.epoch`/workspace
stale-response guard already correct; the test itself now waits on the
real `/impedance-locus` HTTP response deterministically rather than
polling state against an independently-tightened timeout. Both fixes
validated with 10 consecutive isolated runs of their own regression
tests (20/20 passed) plus 3 complete runs of the full Analysis
Playwright suite (168/168 passed every run, 504/504 total, zero flaky
failures); no backend Python files touched; no calculation logic
(Phasor/Impedance/Sequence Components math) touched. See
[SEQUENCE_COMPONENTS_ANALYSIS.md](SEQUENCE_COMPONENTS_ANALYSIS.md) for
the Sequence Components v1 architecture this hardening pass built no
new features on top of.

**Distance Protection v1 is implemented (2026-09-18,
[DECISIONS.md — DEC-099](DECISIONS.md#dec-099--distance-protection-v1-the-fifth-analysis-menu-analyzer-mho-and-quadrilateral-zone-characteristic-evaluation-on-phase-phase-fault-loop-impedance)),
the FIFTH Analysis-menu analyzer** — new nav entry (order preserved:
Phasor, Overcurrent, Impedance Locus, Sequence Components, Distance
Protection). **A separate analyzer from Impedance Locus** (own panel/
state/R-X plot instance) — "Impedance Locus = what impedance did the
system present?" vs "Distance Protection = how does a configured
distance characteristic interpret it?". Calculates phase-phase
fault-loop impedance via full complex phasor subtraction
(`Zab=(Va-Vb)/(Ia-Ib)`, `Zbc=(Vb-Vc)/(Ib-Ic)`, `Zca=(Vc-Va)/(Ic-Ia)`,
`app.domain.distance_protection.compute_loop_impedance()`, reusing
`app.domain.impedance.compute_impedance_point()` unchanged for the
division/low-current-guardrail/basis-conversion step — its only new
math is the phasor subtraction), then evaluates Mho (standard forward
circle, diameter from origin to `reach_ohm ∠ characteristic_angle_deg`)
and Quadrilateral (a self-derived, non-vendor-specific rotated-rectangle
geometry, documented exactly how it is constructed) zone characteristics
for Zones 1-3, evaluated fully independently (more than one may
legitimately report Operated at once). **`Operated`/`Not Operated`**
(explicitly never `Inside`/`Outside`) is PURE geometric element state —
never a relay trip claim; `Configured delay` is informational only, v1
accumulates no timer. Recording mode reuses the existing, unchanged
`phasor_analysis_service.compute_phasor_diagram()` verbatim (zero
duplicated estimation code) and resolves only the selected loop's own
four roles (`LOOP_ROLE_KEYS[loop]` — AB never needs phase C, etc.).
Manual mode is fully standalone, asking only for the selected loop's own
relevant phase pair (never the full six-role Manual Phasor shape Phasor/
Sequence Components use), with two independent bases (Voltage, Current)
each shared by its own loop's two legs. R-X plot reuses Impedance
Locus's own equal-scale coordinate transform (`WW_IMPEDANCE_PLOT_
RADIUS`/`wwImpedanceNiceLimit()`) verbatim — Mho zones draw as a true
SVG `<circle>`, Quadrilateral zones as a 4-point `<polygon>`; new
restrained slate-family `--ww-dist-zone1/2/3` color tokens (strongest→
lightest). Recording trajectory reuses the Impedance Locus locus concept
exactly (locus points carry no zone state — only the current point
drives Operated/Not-Operated). Two genuine implementation bugs were
caught and fixed during this slice's own Playwright hardening (both
scoped entirely to new Distance Protection code, zero pre-existing
selectors/functions touched): a zone-setting change was wastefully
invalidating/re-fetching the full 120-point locus (fixed to only
re-request the current point); a `.ww-dist-zone-field[hidden]` CSS
override bug (the same `[hidden]`-beaten-by-author-`display`-origin
class already documented/fixed elsewhere in this codebase). API: `GET
.../engineering-contexts/{id}/distance-protection`, `GET .../
distance-protection-locus`, `GET .../distance-protection-manual` — same
router file/nesting convention as every prior analyzer's own endpoints.
No backend files outside the new `app/domain/distance_protection.py`/
`app/services/distance_protection_analysis_service.py`/`app/schemas/
distance_protection_analysis.py` modules were touched (plus additive-
only entries in `app/domain/analysis_requirements.py` and `app/api/v1/
engineering_contexts.py`); full backend regression (all tests),
full frontend structural suite, and a combined multi-spec Playwright
regression (Phasor/Overcurrent/Impedance/Sequence/Distance/Playback/
Related-Waveforms/bare-context) all pass. **Real-browser Playwright
coverage was added from day one**
(`browser-tests/distance_protection_analysis.spec.js`, 19 scenarios,
run 2x clean in isolation plus as part of the combined regression) —
continuing the "no Playwright coverage gap" discipline Sequence
Components' own slice established. Three pre-existing, unrelated flaky
Playwright tests (two in `phasor_analysis.spec.js`, one in
`playback.spec.js` — none touching any Distance Protection code path,
all confirmed passing in isolation) were found and reported (not
silently fixed) during this session's own regression verification — see
[DECISIONS.md — DEC-099](DECISIONS.md#dec-099--distance-protection-v1-the-fifth-analysis-menu-analyzer-mho-and-quadrilateral-zone-characteristic-evaluation-on-phase-phase-fault-loop-impedance)'s
own closing section for the full diagnosis; `[OPEN]` for a future,
separate task, per the exact precedent DEC-097/DEC-098 already
established.

**Flake cleanup (2026-09-19) — two of the three DEC-099 items above are
now `[CLOSED]`.** The Phasor Manual Input timing flake was a test-
synchronization bug (a too-weak readiness wait in
`phasor_analysis.spec.js`, fixed there — no production code changed).
The Playback stray-404 flake was a genuine production race (an
in-flight `/phasor-diagram` request could still complete, and log to
the browser console, after `resetToNewWorkspace()`'s workspace DELETE)
— fixed with one shared, reused `AbortController` wired into the
existing `wwPhasorFetchJson()`/`wwClearWorkspace()` choke points in
`frontend/index.html`. Both verified with 20/20 consecutive targeted
passes and a 5x full-Analysis-suite regression. The third item ("Speed
selection 4x") remained outside this task's named scope and was still
`[OPEN]` at that point.

**Bug fix (2026-09-20) — toggling a channel display immediately after
opening a just-uploaded recording could wipe the entire channel
sidebar.** Discovered as an intermittent (~40-50% under natural timing)
failure while validating Compliance Slice 1; confirmed pre-existing and
unrelated to Compliance (reproduced identically on a clean pre-
Compliance baseline). Root cause, confirmed by direct reproduction (a
console-error listener caught the actual uncaught exception, not
assumed): opening a recording (`selectSource()`) refreshes the
workspace viewport (`wwRefreshWorkspaceBounds()` →
`wwApplyAndFetchGroupViewport()`), which calls `Plotly.relayout()` on
every current panel's chart element. A channel toggled ON at almost the
same moment (`wwAddSelectedChannels()`) already has a panel in
`ww.panels` (so the relayout loop sees it) but its own
`Plotly.newPlot()` hasn't run yet (only after that channel's own
waveform fetch resolves) — `Plotly.relayout()` on an uninitialized
chart throws (`Cannot read properties of undefined (reading
'_guiEditing')`), and that uncaught exception propagated into
`selectSource()`'s own catch block, which misidentified it as "could
not reach the backend" and wiped the entire sidebar, discarding the
engineer's own just-completed toggle along with every other channel's
row. **Real production bug** (a real user could hit this), not test-
only. Every OTHER Plotly-touching loop over `ww.panels` in this file
already guards on `panel.plotlyReady` first (15+ call sites) — this was
the one missed site. **Fix**: one guard line
(`if (!panel.plotlyReady || !panel.chartEl) continue;`) in
`wwApplyAndFetchGroupViewport()`'s own relayout loop, matching the
established convention exactly. Verified via disable-fix-then-verify:
6/12 failures with the guard removed, 0/55 with it restored. New
regression added to `browser-tests/smoke.spec.js` (the same natural-
timing reproduction — a genuine same-tick synchronous-ordering race
that an injected network delay could not reliably force wider, tried
directly — with stronger assertions than a bare aria-pressed check):
20/20 consecutive passes. Full backend suite, relevant frontend
structural tests, and a 74-test Analysis/Compliance/Playback/smoke
regression all pass. No DECISIONS.md entry — a scoped bug fix, not an
architectural change.

**Compliance & Capability Slice 1 (2026-09-19) — a new, SIXTH top-level
page, deliberately independent of Analysis (workspace shell only, see
[DEC-100](DECISIONS.md#dec-100--compliance--capability-is-a-top-level-application-function-independent-of-analysis-slice-1-is-a-workspace-shell-only)
and [COMPLIANCE_CAPABILITY.md](COMPLIANCE_CAPABILITY.md)).** Main-menu
order: Recordings, Waveform, Table, Calculated Channels, Analysis,
**Compliance**. `#pageCompliance` has no Engineering Context lifecycle,
no shared Playback mount, no Analysis Input Source, and no
Phasor/Overcurrent/Impedance/Sequence/Distance coupling — opening it
never initializes or alters any of that state (verified directly).
Reuses Analysis's own `.ww-analysis-type-nav` sub-nav component for its
own function list (currently one entry, "Voltage" — conceptually
`Compliance └── Voltage`), same visual language, no second design
system. Slice 1 renders a static five-section workflow shell
(Measurement → Reference Layers → Event Alignment → Comparison Chart →
Results, in that visual top-to-bottom order — Measurement/Reference
Layers/Event Alignment sit compactly side by side, Comparison Chart is
deliberately the single largest section, `aspect-ratio: 16/7` with
`min-height: 320px`, never a tiny fixed height), every section showing
a neutral empty state only — no fabricated values, no fake LVRT/HVRT
curves, no fabricated compliance verdict. A few controls exist as
visibly disabled layout-UAT placeholders only (quantity select, "+ Add
Reference," Shift/t0 alignment buttons) — none wired to real behavior.
No profile JSON, no backend evaluation, no normalization, no alignment
logic, no persistence, no new backend endpoint anywhere in this slice.
UI/UX (workflow order, section placement, chart prominence,
terminology, density, spacing, responsive behavior) is explicitly
subject to owner UAT and expected to change. New structural coverage
(`backend/tests/test_frontend_compliance.py`) and real-browser coverage
(`browser-tests/compliance.spec.js`, 10 scenarios: menu order, page
open/close, Voltage sub-nav, all five sections in order, chart
dominance, navigation lifecycle/isolation from Analysis and every other
top-level page, 1366px/1024px responsive/no-overflow checks) — all
passing, run repeatedly clean. One PRE-EXISTING, unrelated flake
(`smoke.spec.js`'s own recording-row-click assertion) was investigated
and confirmed NOT caused by this slice — reproduced identically (5/5
failures) on a clean pre-Compliance baseline checkout, reported per
Change Governance, not silently patched, left for a future separate
task.

**Owner UAT CSS refinement (2026-09-20, frontend-only, no logic
change).** `#pageCompliance` gained the same page-level `display: flex;
flex-direction: column; gap: 16px; padding: 20px 24px; overflow-y:
auto; height: 100%;` block (plus the required paired `[hidden] {
display: none; }` override — this codebase's own recurring `[hidden]`-
vs-author-`display`-property gotcha, already hit twice before for
`#pageAnalysis`/`#pageCalculatedChannels`) every other flex-column
top-level page already had; it had none before. `#wwComplianceMeasurementSelect`
used to overflow the Measurement card and encroach into Reference
Layers at narrower widths — real root cause: `.ww-compliance-measurement-field`'s
own `min-width: 0` override never actually took effect, since `.ww-
phasor-field`'s own conflicting `min-width: 220px` rule is declared
LATER in the file and wins an equal-specificity tie by source order;
fixed by re-targeting the override at the element's own ID
(`#wwComplianceMeasurementField`, which wins unconditionally regardless
of source order) and adding an explicit `width`/`min-width`/`box-sizing`
rule on the select itself. `.ww-compliance-config-row` also gained a
missing `min-width: 0` (a flex item of `.ww-compliance-panel` with no
override otherwise refuses to shrink below its own content's intrinsic
width). New Playwright regression (`browser-tests/compliance.spec.js`):
the select's own bounding box stays contained within the Measurement
card (and never overlaps Reference Layers) at 1024px/800px. Commit
`3447f24`.

**Compliance & Capability Slice 2 — Measurement Selection + Normalization
Foundation (2026-09-20).** Implements ONLY the Measurement section +
underlying normalization; Reference Layers/Event Alignment/Comparison
Chart/Results remain exactly Slice 1's own static placeholders. The
engineer chooses the assessment quantity FIRST from a fixed nine-entry
Voltage catalogue (Phase A/B/C, Line-Line AB/BC/CA, Min/Max Three-Phase,
Positive Sequence — `app.domain.compliance_measurement.VOLTAGE_
QUANTITIES`, the one source of truth, never duplicated as static
frontend HTML). **Channel/phase resolution reuses the Engineering
Context Detection ALGORITHM directly
(`app.domain.engineering_context_detection.detect_engineering_contexts()`),
never the Engineering Context FEATURE** — Compliance still does not
register as an Engineering Context consumer (DEC-100, unchanged); no
Bay selector, no `wwAnalysisRegisterContextConsumer()`, no Playback, no
Analysis Input Source, no `EngineeringContext` object ever created/
read/persisted by Compliance. See
[DECISIONS.md — DEC-101](DECISIONS.md#dec-101--compliance-slice-2-resolves-voltage-phase-roles-by-independently-re-running-the-engineering-context-detection-algorithm-never-by-becoming-an-engineering-context-consumer)
for the full architectural record of this distinction.

**Instantaneous vs RMS input representation is read from authoritative
metadata, never guessed from a channel name** — reuses the EXACT
metadata-first/detector-fallback hierarchy `check_rms_eligibility()`/
Phasor's own `_waveform_form_eligible()` already established
(`AnalogChannelSummary.waveform_form` wins when trusted; otherwise
`app.domain.rms_detector.classify_waveform_form()` on the channel's own
full sample array); an `UNCERTAIN` verdict or disagreeing resolved
roles is `STATUS_AMBIGUOUS_METADATA`, never a guess. **Normalization
order** (raw recording → engineering units → RMS/fundamental
representation → phase/line-line/sequence quantity → per-unit
conversion) reuses, unchanged: `app.domain.phasor.estimate_phasor()`
for an instantaneous input's own fundamental RMS (never a second DFT/
RMS engine); `app.domain.sequence_components.compute_symmetrical_
components()` for Positive Sequence (never a second Fortescue
transform); and — the task's own explicit disturbance-time
prohibition — a derived line-line quantity (no direct Vab/Vbc/Vca
channel) is computed ONLY from two genuine complex phase phasors
(`Vab = Va - Vb`), **never the `VLL = sqrt(3) * VLN` shortcut**, which
requires both phases to carry angle information (i.e. both
instantaneous) — an already-RMS, angle-less pair is `STATUS_
UNSUPPORTED_REPRESENTATION`. A direct Vab/Vbc/Vca channel, when
present, is used verbatim, never re-derived even when the individual
phases also resolve. Base/Assessment Unit reuse the existing
group-aware Per-Unit model verbatim via `measurement_group_view_
service.build_group_view()` (task section 7 — no second Compliance-
specific base model): a shared, configured Voltage Measurement Group
across every resolved role yields `pu` + nominal LL kV + L-G/L-L;
no group is a normal Engineering-Units state, never an error; roles
spanning two DIFFERENT groups is `STATUS_INVALID_BASE`.

**The live "switch assessment quantity" endpoint never actually computes
a numeric value** — `evaluate_voltage_measurement()` (backing
`GET .../compliance/voltage/measurement`) determines status/resolved-
input-channels/Instantaneous-vs-RMS/"Derived As"/Base entirely from
channel-level metadata; it never calls `estimate_phasor()` or the new
`compute_voltage_quantity_value()`, since Compliance has no selected-
time/Playback concept yet (Event Alignment/t0 is still out of scope)
and the Measurement UI itself shows no numeric reading this slice
either. `compute_voltage_quantity_value()`/`estimate_phasor()`/
`compute_symmetrical_components()` are fully implemented and golden-
tested directly against synthetic waveforms
(`backend/tests/test_compliance_measurement_domain.py`), proving the
computation path correct and ready for a later slice's actual
selected-time wiring without prematurely exposing it.

Two new workspace-scoped, read-only endpoints in a dedicated router
(`app/api/v1/compliance.py`, never Engineering-Context-scoped):
`GET .../compliance/voltage/quantities` and `GET .../compliance/
voltage/measurement?quantity_id=...`. New `app/domain/compliance_
measurement.py`, `app/services/compliance_measurement_service.py`,
`app/schemas/compliance.py` — zero changes to any existing domain/
service/endpoint. Frontend: the Measurement select is now real and
backend-populated (`wwComplianceLoadQuantities()`); selecting a
quantity renders a compact Status/Input/Input Type/Derived As/Base/
Assessment Unit summary (`.ww-compliance-measurement-summary`, reusing
`.ww-phasor-status-row` verbatim — no new status-color system),
re-evaluated on every Compliance page visit so a source uploaded/
removed elsewhere never leaves a stale result. New tests: `test_
compliance_measurement_domain.py` (13 golden vectors), `test_compliance_
measurement_service.py` (13 eligibility/guardrail scenarios), `test_
compliance_measurement_api.py` (4 HTTP wiring), `test_frontend_
compliance.py`'s new Slice 2 structural classes (9 tests), and
`browser-tests/compliance_measurement.spec.js` (14 real-browser
scenarios: dropdown catalogue, quantity switching, single-phase/
three-phase cases, Instantaneous/RMS summaries, Base metadata display,
1366/1024/800px responsive, Analysis/Playback isolation) — two new
committed ASCII COMTRADE fixtures (`compliance_smoke_three_phase`,
`compliance_smoke_rms_phase_a`, the latter hand-verified against the
real `classify_waveform_form()` detector before being committed, since
COMTRADE never sets `waveform_form` metadata). Full backend regression,
full frontend structural suite, and the full Playwright suite (149
scenarios) all pass.

**Compliance & Capability Slice 2 UAT correction — role resolution is
now scoped to an explicitly SELECTED Bay/Measurement Group, same day
(2026-09-20).** Owner UAT identified that the Slice 2 flow above was
ambiguous the moment a workspace contains more than one Voltage
Measurement Group (bay): a `Va` in Bay A and an independently-owned
`Va` in Bay B are both real, valid channels — reporting this as
`ambiguous_measurement_metadata` ("Multiple channels match Va across
the loaded recordings...") was the wrong diagnosis, since there was no
naming conflict, only a missing selection step. **Corrected workflow:
select a Bay/Measurement Group FIRST (a new "Bay / Measurement Group"
select sits above Assessment Quantity in the same Measurement card),
then role resolution/normalization runs only against that group's own
`channel_refs`.** Reuses the EXISTING `app.domain.measurement_group`
model verbatim (`MeasurementGroup.channel_refs`, the same model the
group-aware Per-Unit feature already uses) — no second, Compliance-
specific bay concept was introduced. See
[DECISIONS.md — DEC-102](DECISIONS.md#dec-102--compliance-measurement-scopes-role-resolution-to-an-explicitly-selected-measurement-group-bay-reusing-the-existing-measurement-group-model-verbatim--never-a-second-bay-concept-never-engineering-context)
for the full record; DEC-100/DEC-101 are both unaffected (Compliance
still does not open/depend on Advanced Analysis, Playback, or
Engineering Context — the new Bay picker is a completely different,
pre-existing model).

A new, lean, read-only, Compliance-only endpoint, `GET .../compliance/
voltage/measurement-groups`, lists every Voltage-kind group in the
workspace whose own grouping is not itself contested (`status !=
needs_review`), built by reusing the already-existing `MeasurementGroupRegistry.
list_for_workspace()` (previously present at the service layer, not
previously exposed workspace-wide over REST — the existing `app.api.v1.
measurement_groups` router stays source-scoped and unchanged for its
own CRUD/configuration purpose). `GET .../compliance/voltage/measurement`
now REQUIRES an explicit `measurement_group_id` query parameter.
Auto-selects when exactly one valid group exists; requires an explicit
choice for two or more; never guesses. A duplicate `Va` genuinely
WITHIN one selected group's own membership (two differently-named
member channels that both parse to phase A) remains `ambiguous_
measurement_metadata`, reworded "...within the selected Measurement
Group." Because every resolved role is now, by construction, a member
of the ONE selected group, the former cross-group `STATUS_INVALID_BASE`
trigger is structurally unreachable through this path and was removed
from `_base_for_group()` (a single `build_group_view()` lookup on the
selected group). Switching a quantity that becomes invalid in the newly
selected group never silently substitutes another quantity — the
select's own value is preserved and the summary reports whatever status
genuinely applies (e.g. `missing_inputs`).

**Files**: `app/services/compliance_measurement_service.py`
(`resolve_voltage_role_catalogue_for_group()` replaces the former
workspace-wide function; `list_compliance_voltage_groups()` new),
`app/api/v1/compliance.py` (new group-list endpoint;
`measurement_group_id` now required), `app/schemas/compliance.py` (new
`ComplianceMeasurementGroupOut`), `app/services/errors.py` (new
`ComplianceMeasurementGroupNotVoltageKindError`). `frontend/index.html`
(new `#wwComplianceGroupField`/`#wwComplianceGroupSelect` above
Assessment Quantity, sharing the same ID-scoped containment fix
pattern the owner's own earlier CSS refinement, commit `3447f24`,
established; `wwComplianceLoadGroups()`/`wwComplianceRenderGroupOptions()`/
`wwComplianceOnGroupChange()`/`wwComplianceRenderMeasurementCardState()`).
`app.domain.compliance_measurement` (normalization math) is completely
unchanged — this was explicitly a selection-scope correction, not a
math correction. Tests substantially reworked: `test_compliance_
measurement_service.py` (17 tests, including "cross-bay duplication is
not ambiguous"/"same-group duplication is still ambiguous"/"group
controls base"), `test_compliance_measurement_api.py` (11 tests),
`test_frontend_compliance.py`'s new `TestComplianceMeasurementGroupSelectorStructure`
(6 tests), and a reworked `browser-tests/compliance_measurement.spec.js`
(18 real-browser scenarios: one-group auto-select, two-groups-
duplicate-Va, group-specific missing phase with kept quantity
selection, full group-switch summary update, both selects' responsive
containment). `test_compliance_measurement_domain.py`'s 13 golden tests
are completely unchanged. Full backend suite (5480 tests) and full
Playwright suite (151 scenarios) pass.

**Compliance & Capability Slice 2 UAT correction #2 — Bay/Measurement
Group discovery/bootstrap (2026-09-23).** Owner UAT found a further
real workflow gap: a workspace containing obvious multi-bay Voltage
channel sets (e.g. `KPDN1`/`KPDN2`/`SLKS`/`MCRS`/`SGT1`, each a full
phase triplet) still showed "No Measurement Group is available for
this workspace." on Compliance. **Exact root cause, confirmed by direct
reproduction: `app.services.measurement_group_service.generate_
suggested_groups_for_source()` — the ONE function that ever creates a
`MeasurementGroup` from automatic detection — has never had ANY
automatic trigger anywhere in this codebase** (its own docstring
already said so: "deferred to whichever later slice first needs the
result to be observable"). Before this correction, a group was only
ever created manually or by explicitly opening "Manage Measurement
Groups" and clicking "Suggest" per source. Compliance's own group-list
endpoint/filtering were already correct — the registry was simply
empty. Classified as root cause A (groups never materialized) + E
(Compliance had no bootstrap of its own).

**Fix: Compliance is the "later slice" the existing function's own
docstring anticipated.** `wwComplianceLoadGroups()` now calls the
EXISTING, unchanged `POST .../measurement-groups/suggest` endpoint for
every loaded source not yet attempted this session, BEFORE listing
groups — mirroring the Analysis workspace's own proven
`wwAnalysisDiscoverUncoveredSources()` bootstrap for Engineering
Context. Safe because that endpoint is already idempotent/additive-
only. No new detection algorithm was written — `detect_measurement_
groups()` is unchanged; this was a missing CALLER, not a missing
engine. See
[DECISIONS.md — DEC-103](DECISIONS.md#dec-103--compliances-baymeasurement-group-picker-automatically-bootstraps-the-existing-measurement-group-detection-for-every-loaded-source-mirroring-the-analysis-workspaces-own-proven-engineering-context-bootstrap)
for the full record.

**A second, related gap fixed the same day**: `GET .../compliance/
voltage/measurement-groups` used to exclude `needs_review` groups
entirely, making a "discovered but uncertain" workspace look identical
to a genuinely empty one. The endpoint now returns every Voltage-kind
group of any status; the frontend buckets into `wwComplianceUsableGroups()`/
`wwComplianceReviewRequiredGroups()`. The Measurement card now shows
three distinct states: no groups discovered ("No Voltage Measurement
Group is available for this workspace." + "Manage Measurement Groups"),
groups discovered but all need review ("Voltage Measurement Groups were
found, but they require review before use." + "Review Measurement
Groups"), or usable groups available (normal Bay selector flow). A
`needs_review` group is still never selectable in the dropdown and
never silently trusted for role resolution — DEC-102's own guardrail is
unchanged. The "Manage/Review Measurement Groups" button reuses the
EXISTING Measurement Groups management modal verbatim (an overlay, not
a navigation, so Compliance's own state is never disturbed); closing
that modal now refreshes Compliance's own group list when Compliance is
the active page.

**Files**: `app/services/compliance_measurement_service.py`
(`list_compliance_voltage_groups()` no longer filters by status),
`app/api/v1/compliance.py` (docstrings only, response shape unchanged).
`frontend/index.html` (new `wwComplianceBootstrapGroupsIfNeeded()`/
`wwComplianceSuggestGroupsForSource()`/`wwComplianceUsableGroups()`/
`wwComplianceReviewRequiredGroups()`/`wwComplianceOpenManageGroups()`,
new `#wwComplianceManageGroupsBtn`, `wwComplianceRenderMeasurementCardState()`
extended for the three-way state, one added line in
`wwCloseMeasurementGroupsModal()`). Two new committed ASCII COMTRADE
fixtures (`compliance_smoke_multibay`: four clean bays verified
directly against `detect_measurement_groups()` to produce four
independent `suggested` groups; `compliance_smoke_review_required`: one
bay with deliberately mixed representation, verified directly to
produce `needs_review`). New tests: `test_compliance_measurement_api.py`'s
new `TestMeasurementGroupBootstrapDiscovery` class (4 tests) plus one
needs_review-inclusion test, `test_frontend_compliance.py`'s new
`TestComplianceMeasurementGroupBootstrapAndReviewState` class (6 tests),
and 6 new `browser-tests/compliance_measurement.spec.js` scenarios
(direct-to-Compliance multi-bay discovery with no prior page visit,
re-visiting never duplicates groups, review-required empty state +
action, Manage action open/return-intact, review-then-confirm moves a
group from review-required to usable). Zero changes to `app.domain.
measurement_group_detection`, `app.services.measurement_group_service`,
`app.services.measurement_group_registry`, or any existing Measurement
Groups endpoint/UI. Full backend suite (5491 tests) and full Playwright
suite (156 scenarios) pass.

**Shared post-upload workspace preparation (2026-09-23).** Owner UAT
generalized the previous two fixes into an application-wide invariant:
*"Once an event file is uploaded successfully, every function that can
operate on that file should be ready to use independently. No function
should require the user to first open Waveform, Analysis, Manage
Measurement Groups, or any other page merely to trigger hidden
preparation/bootstrap work."* DEC-103's own Compliance-specific frontend
bootstrap, and Analysis's pre-existing `wwAnalysisDiscoverUncoveredSources()`,
both fixed their OWN page's independence but were still page-owned, not
workspace/source-lifecycle-owned — a third or fourth page (Table,
Calculated Channels) needing the same independence would have meant a
third or fourth duplicated bootstrap.

**Fix: one authoritative backend choke point**, `app.services.workspace_
preparation_service.prepare_workspace_source()`, called from BOTH — and
the only two — source-registration call sites in the backend
(`app.api.v1.sources.upload_comtrade_source()` for COMTRADE, `app.api.v1.
preparation_sources.post_convert_preparation_source()` for CSV/Excel),
immediately after each one's own `WorkspaceRegistry.add()` succeeds. It
runs the EXACT SAME two existing functions the two page-owned bootstraps
already called (`generate_suggested_groups_for_source()`, `generate_
suggested_contexts_for_source()`) — no new detection algorithm, only the
WHEN moved from "whenever a page happens to open" to "the moment the
source exists." Never turns a discovery failure/uncertainty into an
upload failure (both calls wrapped independently, upload already
succeeded and is never rolled back); idempotent by construction (both
underlying functions already skip a cluster entirely if any one of its
channels is already claimed, by any status); synchronous (pure
sub-millisecond channel-name pattern matching, no I/O). See
[DECISIONS.md — DEC-104](DECISIONS.md#dec-104--successful-source-upload-triggers-shared-workspacesource-preparation-measurement-group--engineering-context-discovery-no-top-level-function-may-depend-on-another-page-having-been-opened-first)
for the full record, including the audit that confirmed Measurement
Group and Engineering Context discovery are the ONLY two genuine shared-
metadata lifecycle gaps in the codebase (Time Groups are pure/stateless
and need no preparation step at all).

**DEC-103's and Analysis's own frontend bootstraps are KEPT, reclassified
as fallback-only** (doc comments only, no behavior change) — by the time
either page opens, the backend has normally already done the work, so
both are now pure no-ops on the common path; they remain as defense-in-
depth for a group/context deleted after upload, or a pre-DEC-104
workspace. Neither Compliance's nor Analysis's own readiness depends on
these functions running any more.

**Files**: new `app/services/workspace_preparation_service.py`
(`prepare_workspace_source()`, `WorkspaceSourcePreparationResult`).
`app/api/v1/sources.py` and `app/api/v1/preparation_sources.py` (three
new `Depends()` params each, one call each). `frontend/index.html`
(doc-comment reclassification only). New `browser-tests/post_upload_
readiness.spec.js` (4 scenarios: direct upload-to-Compliance, direct
upload-to-Analysis, both in one session, multi-source idempotency) — none
seed any Measurement Group/Engineering Context via a direct API call,
unlike every other Playwright suite in this repo, since the point is that
upload alone is sufficient. A significant, EXPECTED ripple across ~15
existing backend test files (and `browser-tests/compliance_measurement.spec.js`)
that manually construct Measurement Groups/Engineering Contexts on
realistic, phase-detectable channel names — each updated to clear
whatever the now-automatic discovery created immediately after upload.
Zero changes to `app.domain.measurement_group_detection`, `app.domain.
engineering_context_detection`, or `app.domain.time_grouping`. Full
backend suite and full Playwright suite pass.

**Production regression fix (2026-09-23, same day) — Analysis stopped
auto-selecting a bay after DEC-104.** Owner UAT: *"Analysis/Analyzer
worked before DEC-104, but does not work after DEC-104."* **Root cause,
confirmed by direct reproduction (real browser, real backend, zero test
workarounds), NOT a data/API defect**: every analyzer's own "auto-select
the first usable bay" behavior was wired to `wwAnalysisPublishFreshContextsDiscovered()`,
which fired ONLY from inside `wwAnalysisDiscoverUncoveredSources()`'s own
BLOCKING branch — the branch that only runs when Analysis's very first
fetch for a workspace returns an EMPTY context list. Before DEC-104 that
was always true on a fresh upload (nothing could exist yet); after
DEC-104 a freshly-uploaded source's context is normally already fully
formed by the time Analysis opens, so that first fetch returns a
non-empty list immediately, the blocking branch never runs, and the
"fresh" signal never fires for any of the five analyzers — each one fell
through to its own "Select an Engineering Context to begin." empty
state, requiring a manual click before ANY analyzer would resolve or
compute anything, even though the bay was already fully listed in the
selector. The Engineering Context itself (id/status/members/phase) is
byte-for-byte identical either way — confirmed by diffing the two
creation paths directly.

**Fix**: `wwAnalysisPublishContexts()` is now the ONE place deciding
whether a published list is "fresh" — the first time THIS workspace
session ever has a usable list, tracked via a new
`wwAnalysisContextState.everPublishedUsableContexts` flag — firing the
same `wwAnalysisPublishFreshContextsDiscovered()` regardless of whether
the list came from the immediate fetch (DEC-104's upload-time
preparation), the blocking bootstrap (pre-DEC-104/fallback path), or the
background pass adding a later source. The now-redundant explicit
fresh-fire call inside `wwAnalysisDiscoverUncoveredSources()`'s own
blocking branch was removed. See
[DECISIONS.md — DEC-105](DECISIONS.md#dec-105--dec-104-follow-up-analysiss-own-auto-select-the-first-bay-signal-is-decoupled-from-whenhow-an-engineering-context-was-created)
for the full record, including why `needs_review`/"covered source"
semantics and early-discovery/calculated-channel timing were both
investigated and confirmed NOT contributory (both pre-existing,
unchanged by DEC-104).

**Why DEC-104's own acceptance test missed this**: its "upload -> directly
to Analysis" scenario manually called `selectOption()` before checking
values rendered — the SAME "clear/replace before testing" blind spot
this fix's own task specification warned about, just with a manual
SELECT instead of a manual CLEAR. `browser-tests/post_upload_readiness.spec.js`
now asserts auto-selection directly (no manual `selectOption()`) and
gained a dedicated `phasor_smoke_three_phase`-based suite (6 new tests)
proving all five analyzers (Phasor/Overcurrent/Impedance Locus/Sequence
Components/Distance Protection) independently auto-resolve, auto-compute,
and auto-render immediately after upload with zero manual context
selection — all seven new/changed assertions verified to FAIL against
the pre-fix code and PASS against the fix. `test_frontend_phasor_analysis.py`'s
two structural tests asserting the OLD fresh-fire location were updated
to assert the new one. Full backend suite and full Playwright suite pass.

**Production regression fix, part 2 (2026-09-23, same day) — DEC-105
only partially restored Analysis.** Owner UAT: *"some analyzers now
work, Overcurrent still has an issue, Impedance Locus still has an
issue."* **Root cause, confirmed by direct reproduction with a new
mixed-capability fixture — NOT a data/API defect**: DEC-105 restored the
"fresh context available" SIGNAL but every analyzer still blindly picked
`contexts[0]`, the first context in list order, regardless of whether it
actually satisfied that analyzer's own required roles. Invisible for
Phasor/Sequence Components (both degrade gracefully to a partial result
-- resolved roles render, unresolved ones show "Missing", never a hard
failure), but silently broken for Overcurrent (needs one Current role
for its own selected phase), Impedance Locus (needs a matching Voltage+
Current pair), and Distance Protection (needs the full four-role
Voltage+Current set its own selected fault loop requires) whenever
`contexts[0]` happened to lack what they needed. Reproduced directly:
new fixture `mixed_capability_multibay.cfg/.dat` (KPDN1 Voltage-only
listed first, KPDN2 full Voltage+Current, SLKS Current-only) uploaded
with zero manual seeding -- Overcurrent/Impedance/Distance all
auto-selected KPDN1 and rendered nothing, while Phasor/Sequence
Components auto-selected the SAME KPDN1 and rendered correctly-partial
results.

**Fix**: new shared frontend helpers `wwAnalysisFetchInputResolution()`/
`wwAnalysisFindFirstCompatibleContext()` reuse the EXISTING `GET
.../engineering-contexts/{id}/input-resolution` endpoint (`app.services.
analysis_input_resolution_service`, completely unchanged) to ask, for
each candidate context in order, whether it resolves every role the
analyzer's own currently-selected phase/loop needs -- the frontend never
re-implements Voltage/Current/phase matching itself, only decides WHICH
`(analysis_kind, mode)` pairs to ask about. Overcurrent's/Impedance's/
Distance's own `onFreshContextsDiscovered()` handlers are now `async`,
using this to skip incompatible contexts and select the first genuinely
usable one; if none qualify, a new analyzer-specific message is shown
("No Engineering Context contains the required Current input for
Overcurrent." / "...required Voltage and Current inputs for Impedance
Locus." / "...for Distance Protection.") instead of silently rendering
nothing. Phasor and Sequence Components are unchanged -- confirmed
already correct by direct reproduction. The existing "never steal a
manual selection" guardrail is preserved, checked both before and after
the now-async compatibility search. See
[DECISIONS.md — DEC-106](DECISIONS.md#dec-106--dec-105-follow-up-initial-engineering-context-auto-selection-is-analyzer-compatibility-aware-reusing-the-existing-input-resolution-endpoint--never-merely-the-first-context)
for the full record.

**Files**: `frontend/index.html` only (new shared helpers; three
analyzers' fresh-context handlers made async; three new
`WW_XXX_MSG_NO_COMPATIBLE_CONTEXT` messages; one new
`wwDistanceRoleKeyToInputResolutionMode()` helper). Zero backend
changes. New fixture `backend/tests/fixtures/comtrade/mixed_capability_multibay.cfg/.dat`.
`browser-tests/post_upload_readiness.spec.js` gained 7 new scenarios (5
verified to FAIL against the pre-fix code and PASS against the fix).
`backend/tests/test_frontend_phasor_analysis.py` (one structural
assertion updated for the now-async Overcurrent handler). Full backend
suite and full Playwright suite pass.

**Production regression fix, part 3 (2026-09-23, same day) — DEC-106
fixed role compatibility but not analyzer input eligibility.** Owner
UAT, against a context DEC-106 had already auto-selected as "role-
compatible": Overcurrent — *"The resolved current channel is not an
eligible instantaneous waveform input for RMS evaluation."* Impedance
Locus — *"One or both required phasors are not available for this
phase."* **Root cause, confirmed by direct reproduction with a new
fixture — NOT a data/API defect**: DEC-106's own compatibility check
(`GET .../input-resolution`) only proves a role EXISTS (Level 1 — role
identity); it never checked whether the resolved channel's own waveform
REPRESENTATION (instantaneous vs. RMS/magnitude) is eligible for the
requesting analyzer's actual computation (Level 2) — a separate check
`compute_overcurrent_analysis()`/`compute_phasor_diagram()` themselves
already perform, just AFTER role resolution. A context whose Current
channel is RMS-shaped passes DEC-106's role check every time yet still
fails real computation every time. Reproduced directly: new fixture
`representation_eligibility_multibay.cfg/.dat` (RMSBAY — proper Voltage,
RMS-shaped Current, listed first; INSTBAY — both proper) uploaded with
zero manual seeding — Overcurrent/Impedance/Distance all auto-selected
RMSBAY and rendered nothing (or, computed directly, the exact owner-
reported messages verbatim); Phasor/Sequence Components auto-selected
the SAME RMSBAY and rendered correctly-partial results.

**Compatibility levels established** (now the standing vocabulary for
this feature area): Level 1 — role compatibility (DEC-106). Level 2 —
analyzer input eligibility / waveform representation (this fix). Level
3 — runtime computation availability at a PARTICULAR playback instant
(deliberately never checked by auto-selection, at any level — a
momentarily-quiet window must never permanently disqualify an otherwise-
good context).

**Fix**: new backend-authoritative preflight `GET .../engineering-contexts/{id}/input-readiness`
(mirrors `/input-resolution`'s own `analysis_kind`+`mode` shape),
backed by two new functions each mirroring their own existing
computation function's FIRST phase precisely (role resolution ->
candidate fetch -> reference frequency -> waveform-form eligibility)
while never performing the time-windowed estimate itself (no
`analysis_time` parameter at all): `app.services.overcurrent_analysis_service.check_overcurrent_readiness()`
and `app.services.phasor_analysis_service.check_phasor_diagram_readiness()`
(the SAME function Impedance/Distance/Sequence Components all reuse
under their own `analysis_kind` — one shared phasor-eligibility rule,
never a per-analyzer copy). The frontend's own `wwAnalysisFindFirstCompatibleContext()`
needed no logic change at all -- only its own fetch helper repointed
from `/input-resolution` to `/input-readiness`, a strict superset check.
See
[DECISIONS.md — DEC-107](DECISIONS.md#dec-107--dec-106-follow-up-initial-context-auto-selection-must-also-check-analyzer-input-eligibility-waveform-representation-not-merely-role-identity--a-new-backend-authoritative-input-readiness-preflight-distinct-from-role-compatibility-and-from-runtime-computation-availability)
for the full record, including why calling the full analyzer
computation as the selector test was explicitly rejected (a transient
Level 3 failure must never disqualify a genuinely good context).

**Files**: `backend/app/services/overcurrent_analysis_service.py`/
`phasor_analysis_service.py` (new readiness functions), `backend/app/schemas/analysis_input_resolution.py`
(`AnalysisInputReadinessOut`), `backend/app/api/v1/engineering_contexts.py`
(new endpoint). Zero changes to any existing computation/detection
function -- confirmed by the full existing backend suite passing
unmodified. `frontend/index.html` (one fetch helper repointed). New
fixtures `representation_eligibility_multibay.cfg/.dat` and
`representation_eligibility_none.cfg/.dat`. New backend test file
`test_analysis_input_readiness_api.py` plus new test classes in
`test_overcurrent_analysis_service.py`/`test_phasor_diagram_service.py`.
`browser-tests/post_upload_readiness.spec.js` gained 6 new scenarios (5
verified to FAIL against the pre-fix frontend and PASS against the
fix). Full backend suite and full Playwright suite pass.

**Production regression fix, part 4 (2026-09-23, same day) — the shared
waveform-form fallback detector itself was corrected to multi-window
classification.** Owner UAT: *"KPDN1 Overcurrent is rejected as non-
instantaneous, even though the waveform display clearly shows a genuine
instantaneous AC current waveform... becomes heavily disturbed around
the fault/event, then collapses close to zero."* Preceded by a
dedicated investigation-only session (no production change) that
confirmed the root cause with hard evidence: `app.domain.rms_detector.classify_waveform_form()`
evaluated its five indicators ONCE over ONE long aggregate slice (the
first up to 1 second of the record); a genuine disturbance record
legitimately mixes multiple physical states within that same slice
(clean pre-fault, fault, near-zero post-clearance collapse), and the
collapse tail diluted the slice-wide zero-crossing-ratio and targeted-
frequency-correlation indicators enough to drop a genuinely
instantaneous current below confidence (2 instantaneous votes / 0
magnitude votes, short of the 4-vote floor) — even though a clean
pre-fault 5-cycle window and a disturbance-centered 5-cycle window each
independently scored 5/5 confident votes.

**Fix**: cycle-based multi-window classification, reusing the EXISTING
five indicators/thresholds verbatim (the confirmed problem was window
AGGREGATION, never threshold tuning). The representative region (still
capped at 1 second, unchanged) is tiled with deterministic, non-
overlapping, `nominal_frequency_hz`-derived 5-cycle windows; each is
classified independently via the SAME original per-window vote logic
(extracted, unchanged, into `_classify_slice()`); the channel-level
result requires at least 2 informative windows agreeing with zero
opposing votes (the same "more evidence, no contradicting evidence"
shape one level up). A window whose own RMS is below 10% of the whole
region's RMS (scale-relative, never an absolute unit threshold) is
skipped as uninformative -- proven necessary directly, since a real
collapse tail's own measurement noise could otherwise accumulate
spurious votes. When fewer than two windows fit, this falls back to the
original single-slice classification unchanged, so short-record
behavior is completely unaffected -- all 10 pre-existing detector tests
pass unmodified. Four adversarial genuine-RMS/magnitude shapes (a slow
positive envelope, a stepped RMS-output shape, a full-wave-rectified
signal, a mostly-flat noisy signal) were proven to never become falsely
instantaneous under the new design. See
[DECISIONS.md — DEC-108](DECISIONS.md#dec-108--dec-107-follow-up-the-shared-waveform-form-fallback-detector-is-corrected-to-cycle-based-multi-window-classification-so-a-genuine-disturbance-record-pre-fault--fault--post-clearance-collapse-is-no-longer-misclassified-uncertain-merely-because-one-long-aggregate-slice-mixes-its-own-multiple-physical-states)
for the full record, including the sensitivity-sweep evidence, the
rejected "any instantaneous window" rule, and the conservative single-
window boundary this design deliberately does NOT relax.

**Propagates through the ONE shared detector to every consumer, no
analyzer-specific bypass**: Overcurrent's real one-cycle RMS
calculation, Impedance's real phasor+impedance-point calculation,
Distance Protection's real loop calculation, and calculated-channel RMS
creation all now succeed end to end for a genuine disturbance record,
proven directly through the real API with a new committed fixture
(`disturbance_record_multibay.cfg/.dat`).

**Files**: `backend/app/domain/rms_detector.py` only for production
logic. Zero changes to `evaluate_rms()`, `estimate_trailing_rms_at_time()`,
`estimate_phasor()`, `compute_impedance_point()`, or Distance Protection
math. New test coverage: `test_rms_detector.py` (`TestMultiWindowDetection`,
`TestMultiWindowDoesNotWeakenGenuineRmsSafety`), `test_calculated_channel_service.py`
(`TestRmsEligibilityDisturbanceRecord`), new
`test_dec108_disturbance_record_integration.py` (13 scenarios), new
fixture `disturbance_record_multibay.cfg/.dat`, and 4 new
`browser-tests/post_upload_readiness.spec.js` scenarios -- all 17
behavior-changing assertions verified to FAIL against the pre-fix
detector (via a temporary `git stash` of `rms_detector.py` alone) and
PASS against the fix. DEC-107's own RMSBAY/INSTBAY fixture regression
preserved exactly. Full backend suite and full Playwright suite pass.

**Compliance & Capability Slice 3 — Reference Profiles, Reference
Layers, and static Comparison Chart rendering (2026-09-23).** Owner UAT
for the DEC-104 through DEC-108 Analysis regression chain passed
(closed); work resumed on Compliance. A generic `ReferenceProfile`
domain model (`app/domain/reference_profile.py` — never Grid-Code-
specific; category/quantity/unit/display-window/evaluation-window/
tolerance/lower-and-upper-boundary fields, `constant`/`linear` segments,
frozen right-continuity discontinuity semantics, "never silently repair
bad data" validation), a built-in catalogue loader that ships with ZERO
production profiles (task's own explicit "do not fabricate Malaysia
Grid Code values" constraint — no authoritative verified source exists
in this repo), two new in-memory workspace-scoped registries (custom
profiles, active layers — mirroring `MeasurementGroupRegistry`'s exact
shape), a new dedicated router (`/reference-profiles`, `/reference-
layers`, `/reference-layers/chart-data`), an active Reference Layers
card, three new modals (Add Reference / Manage Profiles / a table-first
numeric profile editor — no freehand curve dragging anywhere), and a
real Plotly-rendered Comparison Chart (reference curves only, no
measured waveform, no evaluation).

**Mid-implementation product-requirement amendment — Reference Layers
must work without an uploaded recording.** The owner sent this as a
genuine correction while the slice was already in progress: Reference
Profiles/Layers/the Comparison Chart's static rendering must never be
gated behind a source/Bay/Measurement Group/quantity existing.
Compliance is now architecturally two independent inputs (Measurement,
Reference Layers) joined only at the Comparison Chart. Compatibility is
three-way (`compatible` / `incompatible` / `not_yet_applicable`) — "no
Measurement selected" is its OWN state, never collapsed into
"incompatible". Uploading a source into a workspace with already-
configured Reference Layers never resets them (the two new registries
are wired into the "Start New Workspace" DELETE lifecycle hook only,
never into any upload endpoint — persistence-across-upload is the
DEFAULT behavior of the existing in-memory-registry-keyed-by-workspace-id
pattern, DEC-015/DEC-019, not a special case). The Comparison Chart's
own axes derive entirely from the active, visible layers' own profiles
(x-axis: union of display windows; y-axis: the first visible layer's own
unit, with a genuine unit mismatch handled explicitly — excluded from
plotting but never hidden from the layer list).

See [DECISIONS.md — DEC-109](DECISIONS.md#dec-109--compliance-slice-3-a-generic-reference-profilereference-layer-domain-model-static-comparison-chart-rendering-and-a-reference-subsystem-lifecycle-fully-independent-of-any-uploaded-recording)
and [COMPLIANCE_CAPABILITY.md](COMPLIANCE_CAPABILITY.md) for the full
architectural record. New tests: `test_reference_profile_domain.py`
(31), `test_reference_profile_builtins.py` (8), `test_reference_profile_service.py`
(35), `test_reference_profile_api.py` (22), `test_frontend_compliance.py`
updates (`TestComplianceOutOfScopeSlice3`, `TestComplianceReferenceLayersStructure`),
and `browser-tests/reference_profiles.spec.js` (9 real-browser
scenarios, inspecting actual Plotly trace data). Full backend suite and
full Playwright suite pass. Event Alignment, Results, and every
evaluation/breach/tolerance/verdict concept remain out of scope, exactly
as before.

**Compliance & Capability architecture refinement — Assessment
Definition separates ReferenceProfile from HOW a measured quantity is
derived (DEC-110, 2026-09-24).** Owner product review, after Slice 3
UAT passed conceptually: `ReferenceProfile.evaluation_quantity` (one of
Slice 2's own nine canonical quantity ids) was too tightly coupled to
one measured convention — a real grid-code/utility/OEM requirement
often specifies only the boundary curve, leaving HOW to reduce a
three-phase recording to one comparable value (minimum of VAB/VBC/VCA,
minimum of VA/VB/VC, positive-sequence voltage, each phase
independently, or genuinely unstated) to a separate, sometimes entirely
unstated, convention.

**New, standalone `AssessmentDefinition` domain model**
(`app/domain/assessment_definition.py`, zero dependency on `app.domain.
reference_profile` to avoid a circular import): `quantity_family`
(`voltage`), `representation` (`line_line_rms`/`phase_ground_rms`/
`positive_sequence_rms`/`unspecified`), `phase_treatment`
(`minimum`/`maximum`/`each_phase`/`single`/`unspecified`), an optional
`member` (`A`/`B`/`C`/`AB`/`BC`/`CA`, only meaningful for a `single`
line-line/phase-ground pick), `measurement_location`, and `provenance` —
every field defaults to `unspecified`, a fully valid "not yet confirmed"
state, never an error, never silently guessed. `ReferenceProfile.
evaluation_quantity` is retired, replaced by `assessment_definition:
AssessmentDefinition`. Validated combinations carry real engineering
meaning (an aggregate treatment never takes a member; positive-sequence
has no member concept; `single` with line-line/phase-ground REQUIRES a
member; `each_phase` is not yet supported for `line_line_rms`).

**Canonical Slice 2 measurement quantities are completely unchanged**
(`app.domain.compliance_measurement.VOLTAGE_QUANTITIES`, zero lines
touched) — the frozen distinction, in the owner's own words: "canonical
measurement quantities = what Powerwave CAN CALCULATE; assessment
definition = what a REQUIREMENT tells Powerwave to use." All nine
legacy `evaluation_quantity` ids migrate unambiguously to an
`AssessmentDefinition`; an unrecognized one becomes fully `unspecified`
with the original string preserved as `legacy_quantity_hint`. JSON
schema bumped to v2 (`assessment_definition` object) — v1
(`evaluation_quantity` string) remains a read-only, import-only
migration path; every new export always writes v2.

**Compatibility is now ALWAYS `not_yet_applicable`** — there is no
measurement resolver yet to determine whether a profile's own required
assessment trace can actually be derived from a selected Measurement, so
`compute_layer_compatibility()` never returns `compatible`/`incompatible`
in this codebase today; this is the direct, necessary consequence of the
model split, not a regression. The profile editor's old "Evaluation
quantity" select is retired, replaced by a compact "Assessment
Definition" section (Voltage representation / Phase treatment / Specific
member (shown only when applicable) / Measurement location /
Interpretation source, human labels only, never raw enum names); the
Reference Layers card and Add Reference picker both gained a one-line
assessment summary (e.g. "Assessment: Minimum Line-Line RMS at
Connection Point" / "Assessment convention not specified").

**A genuine, pre-existing regression was discovered (not caused) during
full-Playwright validation for this refinement**:
`analysis_related_waveforms.spec.js` and every Analysis analyzer's own
Playwright suite (Phasor/Overcurrent/Impedance/Distance/Sequence
Components) upload a fixture then manually `POST .../engineering-
contexts` to seed a bay — this now 409s (`channel_already_in_context`)
because DEC-104's own shared post-upload preparation already
auto-creates an Engineering Context for the same channels before the
test's own manual POST runs. Confirmed reproducible on a byte-identical,
disposable `git worktree` checkout of the prior commit (`667159d`, zero
DEC-110 changes present) via a raw HTTP request, no browser involved —
this is an Analysis-area regression, unrelated to Compliance, and
explicitly out of this refinement's own task scope ("implement a
targeted architecture refinement only"); reported to the owner rather
than fixed here. See [COMPLIANCE_CAPABILITY.md](COMPLIANCE_CAPABILITY.md)'s
own "Assessment Definition (DEC-110)" section for the full account,
including the one directly-Compliance-related casualty of the same
investigation that WAS fixed (`browser-tests/compliance.spec.js` still
asserted Slice 1's own retired disabled "+ Add Reference" state, missed
when DEC-109 activated it).

See [DECISIONS.md — DEC-110](DECISIONS.md#dec-110--compliance-slice-3-refinement-referenceprofile-is-separated-from-how-a-measured-quantity-is-derived--a-new-assessmentdefinition-model-bridges-the-reference-boundarycurve-to-compliance-slice-2s-canonical-measurement-quantities-with-unspecified-as-a-first-class-state-and-no-measurement-resolver-implemented-yet)
for the full architectural record. New tests: `test_assessment_
definition.py` (32), plus updates across `test_reference_profile_
domain.py`, `test_reference_profile_service.py`, `test_reference_
profile_api.py`, `test_frontend_compliance.py`
(`TestAssessmentDefinitionEditorStructure`), and `browser-tests/
reference_profiles.spec.js` (new `test.describe("Compliance Slice 4
(DEC-110)")`, 5 scenarios). Full backend suite passes; full Playwright
suite passes with the one pre-existing, unrelated Analysis-area
exception noted above.

**Update (2026-09-24) — the pre-existing Analysis-area regression above is
now CLOSED, in a dedicated session (DEC-112).** Root cause confirmed
exactly as suspected here: a stale test-harness assumption in six
Analysis Playwright spec files, predating DEC-104, never a production
defect. Fixed test-only via a new shared helper
(`browser-tests/support/engineering_context_helpers.js`) that discovers
and reuses the context DEC-104's own upload-time preparation already
created, rather than duplicating it. Two separate, genuine, pre-existing
issues were found and reported (not fixed, out of scope) during the same
investigation: a narrow Phasor Playback claim/refine timing race, and an
O(point_count) performance characteristic in the Impedance Locus/Distance
Protection locus endpoints (~13s per 120-point request, measured directly
against a freshly-started backend). Full Playwright: ~125 pre-existing
failures reduced to 7, all traced to those two separate findings, zero
remaining DEC-104 conflicts. See
[DECISIONS.md — DEC-112](DECISIONS.md#dec-112--pre-existing-analysis-playwright-regression-dec-104-onward-browser-suites-that-manually-post-an-engineering-context-now-discoverreuse-the-one-upload-time-preparation-already-created-instead-of-duplicating-it)
for the full record.

**Compliance & Capability jurisdiction-neutrality architecture invariant
+ portable-persistence lifecycle + provenance metadata expansion
(DEC-111, same day, 2026-09-24).** Owner UAT and follow-up product/
engineering review, continuing directly from DEC-110: *"Powerwave must
remain country-neutral, utility-neutral, OEM-neutral. Do not hardcode
Malaysian Grid Code, GB Grid Code, ENTSO-E, AEMO, Huawei, etc. into
production calculation code... For this application there is currently
no user account, no per-user profile storage. Therefore do NOT introduce
a 'User Library' database or localStorage."*

**Jurisdiction-neutrality was already true in substance (the built-in
catalogue has always shipped empty, DEC-109; nothing in production code
has ever branched on a jurisdiction name) — DEC-111 makes it an
explicit, enforced, regression-proof invariant.** New `backend/tests/
test_reference_profile_jurisdiction_neutrality.py` tokenizes every
production Reference Profile source file (`app.domain.reference_profile`/
`reference_profile_builtins`/`assessment_definition`/`reference_layer`,
`app.services.reference_profile_registry`/`reference_layer_registry`/
`reference_profile_service`, `app.schemas.reference_profile`, `app.api.
v1.reference_profiles`) and strips every COMMENT and STRING token
(docstrings included) before checking the remainder for named
jurisdictions/OEMs (Malaysia, GB Grid Code, ENTSO-E, AEMO, Huawei) --
deliberately NOT a brittle whole-repo string ban (which would
immediately false-positive on this project's own extensive DEC-109/110/
111 documentation that names these same terms as examples of what must
never be hardcoded). A profile's own DATA may legitimately say "Malaysia
Grid Code 2025" (task's own "bundled profile != hardcoded requirement"
distinction); a CODE BRANCH keyed on that name may not, ever.

**Bundled profiles remain architecturally possible and are explicitly
distinct from a hardcoded requirement**: a future deployment could ship
`reference_profiles/malaysia_grid_code_2025.json` while another ships
`gb_grid_code_xxx.json`, both validated through the identical, unchanged
parser — production ships zero by default today, both because no
authoritative verified source exists in this repo (DEC-109, unchanged)
and because defaulting to any ONE jurisdiction would itself violate
neutrality.

**Provenance/version metadata expanded** (`ReferenceProfileMetadata`):
`jurisdiction`, `authority`, `document_title`, `document_revision`,
`effective_date`, `source_section`, `source_page`, `manufacturer`
(renamed from Slice 3's `brand`/`source_document`/`source_revision` --
a safe rename, custom profiles are session-scoped only). Every field
stays optional. **Never assume a newer revision replaces an older one**
-- two profiles representing different revisions of the same
jurisdiction/document (e.g. "2025" and "2027") coexist as entirely
independent `ReferenceProfile` objects, each addable as its own
Reference Layer simultaneously; no "latest version" concept exists
anywhere in this codebase, proven by dedicated coexistence tests at the
domain/service/API/browser layers. Schema stays at `schema_version = 2`
(DEC-110's own bump) -- the metadata expansion is purely additive.

**Portable JSON is the persistence mechanism, named as an explicit
product lifecycle** (the mechanics were already exactly DEC-109's own
architecture): Portable Reference Profile JSON -> user keeps it locally
-> Import into Powerwave -> validate -> temporary session/workspace
profile -> add as Reference Layer. An imported/custom profile exists
only for the current app/workspace lifecycle; Export is the durable save
mechanism the engineer actually controls -- no server-side persistence
was added, none should be until a genuine account/database requirement
exists.

**UI terminology aligned to generic, jurisdiction-neutral wording**:
"Manage Profiles" -> "Reference Library", "+ New Custom Profile" -> "+
Create Custom Reference", "Import JSON…" -> "Import Reference…" --
never "My Profiles"/"User Library"/a jurisdiction-specific label, since
there are no user identities in this application. Empty-state wording
revised to read as an intentional product state ("No reference profiles
loaded. Create a custom reference or import one below.") rather than a
loading failure.

**Real local-file download/upload flow directly browser-tested**:
`reference_profiles.spec.js` gained scenarios using `download.saveAs()`
+ `setInputFiles()` against the real `<input type="file">` element
(never bypassing the UI via a direct API call) -- a full local round
trip, a malformed local file rejected inline, and a v1-schema local file
still migrating correctly.

See [DECISIONS.md — DEC-111](DECISIONS.md#dec-111--compliance-is-architecturally-jurisdiction-neutral-reference-requirements-are-portable-json-data-never-engine-code-provenanceversion-metadata-lets-independent-revisions-coexist-importedcustom-profiles-are-session-scoped-only-json-is-the-durable-persistence-mechanism)
and [COMPLIANCE_CAPABILITY.md](COMPLIANCE_CAPABILITY.md) for the full
architectural record. New tests: `test_reference_profile_jurisdiction_
neutrality.py` (9), plus `TestProvenanceMetadataDEC111`/
`TestRevisionCoexistenceDEC111` in the domain/service test files,
`TestProvenanceMetadataAndRevisionCoexistenceHttp` in the API tests,
`TestReferenceLibraryTerminologyDEC111`/`TestJurisdictionNeutralUiDEC111`
in the frontend structural tests, and a new
`test.describe("Compliance Slice 4/5 (DEC-111)")` block in
`reference_profiles.spec.js` (5 real-browser scenarios). Full backend
suite passes; every Compliance-specific Playwright suite passes; the
pre-existing, unrelated Analysis engineering-context regression DEC-110
already reported remains unaddressed here too (still out of scope,
still awaiting a dedicated session).

**Flake cleanup (2026-09-19, continued) — the third and final DEC-099
item ("Speed selection 4x") is now `[CLOSED]`; DEC-099 has zero
remaining `[OPEN]` items.** Test-synchronization bug, no production
defect: the authoritative Playback engine (`wwPlaybackTick`/
`wwPlaybackSetSpeed`/Play/Pause/Restart/Seek) was audited end to end
and found already correct — `speed` is one controller-wide field,
untouched by Play/Pause/Restart/Seek, end-of-range clamps exactly with
a clean stop. The actual failure was reproduced directly: the original
test's own FIXED 600ms request-counting window occasionally lets the
first throttled `/phasor-diagram` fetch (throttle ~100ms, wall-clock-
paced, independent of `speed`) land just outside that window by
scheduling jitter (`diagramFetchCount === 0`, 1/30 isolated runs) — not
a production race. Fixed by waiting authoritatively for the first fetch
before measuring the rate over a further bounded window
(`browser-tests/phasor_analysis.spec.js`, test-only). Five new
deterministic 4x tests added to `browser-tests/playback.spec.js`
(state+UI+actual engine rate, mid-play switch, Pause/Resume, Seek,
end-of-range clamp) — all 30/30 consecutive passes. Full diagnosis and
fix details:
[DECISIONS.md — DEC-099](DECISIONS.md#dec-099--distance-protection-v1-the-fifth-analysis-menu-analyzer-mho-and-quadrilateral-zone-characteristic-evaluation-on-phase-phase-fault-loop-impedance)'s
own final `[CLOSED]` closure note.

**Bug fix (2026-09-18) — Sequence Components vector shaft/color
rendering (owner UAT, renderer/style only, no math changed).** Owner
report: sequence values appeared to calculate correctly, but the
diagram showed a dominant component (e.g. V1, far from the origin) as
an isolated arrowhead with no visible connecting shaft, and the
intended Positive/Negative/Zero sequence-identity colors did not appear
applied. Root cause, confirmed by direct reproduction (not assumed):
`wwSequenceRoleColor()` returned a bare `var(--ww-seq-positive)` with
no fallback — unlike this codebase's own established `var(x, fallback)`
defensive-CSS convention (see `.ww-annotation`'s own comment on exactly
this risk: a stale/version-mismatched cached `theme.css` predating a
recently-added token). With `--ww-seq-positive/-negative/-zero`
unresolved, the shaft `<line>`'s own `stroke="var(...)"` (its ONLY
color source) degrades to SVG's own initial value `none` — an
invisible shaft, even though its own geometry is completely correct —
while the arrowhead `<polygon>`'s `fill="var(...)"` degrades to
`black` (stays visible, wrong color); the `<text>` label survives only
because a separate stylesheet rule (`fill: var(--text)`) always
outranks the inline attribute. Reproduced exactly (screenshot
pixel-for-pixel matches the owner's description) by directly unsetting
the three tokens in a real browser. **Fix**: each of the three lookups
in `wwSequenceRoleColor()` now carries `var(--ww-seq-x, var(--text-dim))`
— the same defensive pattern this codebase already uses elsewhere,
falling back to the SAME `--text-dim` token this function already used
for an unrecognized role. The healthy/normal rendering path (a
present, up-to-date `theme.css`) is unchanged — same colors as before.
`wwPhasorRoleColor()` (Phasor's own function) was deliberately left
untouched, out of this fix's explicit narrow scope. No domain math,
Recording calculation, Manual calculation, ratio, basis-conversion, or
Playback behavior touched — exactly one function (a pure color-string
builder) changed. New Playwright coverage
(`browser-tests/sequence_components_analysis.spec.js`, +9 scenarios:
dominant V1/pure V2/pure V0/dominant I1/all-six-roles shaft-and-color
geometry assertions in Manual, an equivalent Recording-mode check, a
responsive check at 1366px/1024px, and one dedicated test that directly
reproduces the degraded-token scenario) — the dedicated regression test
was verified to genuinely fail before the fix
(`lineStroke === "none"`) and pass after it. Full backend regression,
full frontend structural suite, and Phasor/Analysis-shared Playwright
regression all pass. See
[SEQUENCE_COMPONENTS_ANALYSIS.md](SEQUENCE_COMPONENTS_ANALYSIS.md)'s
own "Vector rendering invariant and the shaft/color rendering bug fix"
section for the full record. No DECISIONS.md entry — a bug fix, not an
architecture change.

**Sequence Components closure/hardening pass (2026-09-18) — CLOSED as a
stable feature, zero remaining Sequence-specific open bugs/debt.** A
complete audit of every Sequence-specific implementation path (domain
math, service layer, API/schema, frontend state machine, Recording/
Manual input, Playback, Related Waveforms, vector renderer, scale
logic, visibility, ratios, angle convention, responsive layout, theme
tokens, tests, docs) — not assumed complete merely because existing
tests passed. **Result: no production defects found** beyond the
vector-shaft/color bug already fixed the same day (see above); every
other path was verified correct by direct code reading AND real-browser
testing. Two behaviors were **confirmed-and-documented, not changed**
(per the task's own "if changed, explain; if not, confirm and document"
framing): (1) hiding a role via the eye toggle never rescales the
remaining visible vectors — `wwSequenceFamilyMaxMagnitude()` includes
every `available` role regardless of its own visibility, identical to
`wwPhasorFamilyMaxMagnitude()`'s own precedent; (2) a sequence ratio's
own magnitude is never capped, only guarded against `Infinity`/`NaN` —
capping an extreme-but-real ratio would itself be an implicit
threshold/compliance judgment, which this feature explicitly excludes.
Naming/ordering (`V1`/`V2`/`V0`, positive→negative→zero) was found
already consistent everywhere — no `0,1,2` vs `1,2,0` mismatch existed.
No Sequence-specific `[OPEN]`/pending/TODO/FIXME items existed in the
codebase or `docs/project-memory/` before this pass (confirmed by
direct search) — there was nothing pending to close going in.
**Backend golden tests strengthened**: the unbalanced-input golden test
now asserts real/imaginary/magnitude/angle (was magnitude-only), plus a
new equivalent Current-domain unbalanced golden case. **Real-browser
coverage extended from 20 to 33 scenarios**
(`browser-tests/sequence_components_analysis.spec.js`): individual
dominant-color golden cases for all six roles (closing the I2/I0 gap),
a mixed-all-six-visible simultaneous-color case, dark-theme color
resolution, the visibility/scale-isolation rule, angle-wrap-around
display, the ratio-unavailable guardrail at the UI layer, context-
switch staleness (a genuinely different source/context, not a channel-
ref collision), and scale-legend/vector non-overlap at 1366px/1024px.
**Validation**: full Sequence Playwright suite run 10 consecutive times
(330/330, zero flaky failures); full backend regression; full frontend
structural suite; Phasor/Playback/Related-Waveforms/Analysis-context
regression; `git diff --check` clean. See
[SEQUENCE_COMPONENTS_ANALYSIS.md](SEQUENCE_COMPONENTS_ANALYSIS.md)'s
own "Closure-pass audit summary" section for the full record. No
DECISIONS.md entry — no architecture changed, confirmation/hardening
only.

**Pre-advanced-features Slice
F2 (realistic performance baseline, no DEC — measurement/test
infrastructure only, zero production code changed) establishes the
reproducible import/parse/waveform performance baseline the project
previously lacked.** The pre-existing `test_dec050_slice8_performance.py`
only ever measured the Per-Unit conversion overhead RATIO at the
`extract_waveform_range()` service layer against an in-memory
`ActiveSource` — never real upload/parse/HTTP. Slice F2 adds a
separate, standalone (never pytest-collected) benchmark,
`backend/tests/perf/baseline_runner.py`, plus deterministic synthetic
COMTRADE (BINARY, real row layout) and CSV fixture generators
(`backend/tests/perf/synthetic_comtrade.py`/`synthetic_csv.py`, no
committed large binaries), measuring three representative scenarios —
15 MB/40+16-channel and 75 MB/64+32-channel COMTRADE, 12 MB/20-channel
CSV — through the REAL upload → parse → in-memory registry → waveform
endpoint path, each phase isolated in its own fresh subprocess so peak
memory (`backend/tests/perf/mem_probe.py`: stdlib-only
`resource.getrusage()`/`ctypes` `GetProcessMemoryInfo`, cross-platform,
no new dependency) is never contaminated by fixture generation or a
prior scenario. Findings (full baseline, methodology, and caveats in
[docs/development/PERFORMANCE_BASELINE.md](../development/PERFORMANCE_BASELINE.md)):
import completes in under 1.7 s even for the 75 MB/562K-sample
scenario at ≈1.2 GB peak memory (well under the task's own "100 MB
→ >2 GB" concern bar); every waveform request (full-range AND a
reduced 2 s window, all three scenarios) completes under 50 ms with a
55-80 KB payload, bounded by the existing min/max-envelope reduction
regardless of recording size — read as no immediate architectural
concern for a future Event Playback consumer, though a genuine
playback loop was deliberately not simulated this slice. No
production code changed; small, fast correctness tests
(`backend/tests/test_performance_baseline.py`) run in normal
regression, the 10-100 MB benchmark itself does not (explicit command
only). Pre-advanced performance-readiness blocker closed.

**Pre-advanced-features Slice
F1 (calculated-channel dimensional-safety guardrail, no DEC — a
narrow bug fix closing an audit-identified gap, not a new product
decision) closes a real reachable fail-open case**:
`app.domain.calculated_channel.units_compatible()` used to allow any
multi-input operation (Addition/Subtraction) whenever EVERY input's
unit string was blank/missing, regardless of engineering type -- e.g.
a blank-unit Voltage channel plus a blank-unit Current channel was
previously accepted, which is numerically possible but dimensionally
meaningless. `units_compatible()` gained an optional
`engineering_types` argument (default `None`, fully backward-
compatible -- every pre-existing 1-arg call/test is unchanged) that is
consulted ONLY in the all-units-blank case, applying the exact same
"known value(s) present -> every input must share it" shape the unit
check itself already uses: a genuine mismatch among KNOWN
(non-`Undefined`) engineering types, including a known type mixed with
an unclassified one, is rejected; all-`Undefined` preserves the
original permissive behavior. The one call site,
`app.services.calculated_channel_service.create_calculated_channel()`,
now raises `IncompatibleUnitError` with an engineering-facing message
naming the actual conflicting channels/types for this new blank-unit
rejection path (e.g. "Cannot combine BRDC_VA and BRDC_IA: their units
are unspecified and their engineering types differ (Voltage vs
Current)."); the pre-existing known-unit-mismatch message is
unchanged. No unit system was introduced; per-unit measurement
grouping (DEC-050/DEC-051/DEC-052), time alignment, dependency
handling, unit prefix conversion, the operation set, and persistence
are all untouched. 4158 backend tests pass (up from 4144). See
[Implemented capabilities](#implemented-capabilities) (Calculated
channels entry).

**DEC-084 (Explicit Null
Resolution and Calculated-Channel Missing-Data Policy) is now an
IMPLEMENTED BASELINE end to end, including Data Preparation's own
algorithmic estimation and bulk constant fill** — Data Preparation
Slices 1-5 (explicit null as a distinct, resolved `WorkingOverlay`
state; single-cell and backend-scope-authoritative bulk Mark as Null; a
Data Issues panel + Data Quality summary; explicit-null preservation
through cleaned export, canonical conversion, and every downstream
display/cursor/annotation path), the Data Preparation missing-value
Fill/Estimate slice (single-cell **Estimate Missing Value** and
group-level **Fill / Estimate Missing Values** — the four algorithmic
methods plus issue-scoped **Constant Value** — reusing the SAME shared
`app.domain.missing_data_estimation` engine Calculated Channels
already used, gap-based scope transparency for mixed missing/invalid
gaps, and estimated/constant-fill visual states in the Raw Data
Preview), and Calculated Channel Slices 1-4 (per-channel `null_policy`
— Propagate Null/Treat Null as Zero/Require Manual Value/Estimate
Missing Data with a Hold Last/Nearest/Linear/Local Mean estimation
engine, always calculation-local and never mutating source or parent
arrays; Signal Builder UI; channel-level traceability). PCHIP
interpolation and a handful of other extensions remain intentionally
deferred — see the Calculated Channels and Data Preparation entries
under
[Implemented capabilities](#implemented-capabilities) for the full
record, the DEC-084 entry under
[Known intentional constraints](#known-intentional-constraints--deferred-items)
for exactly what remains deferred, and [HANDOFF.md](HANDOFF.md) for the
full implementation commit chain. A prior (2026-09-05) Preparation
Status integrity fix
([DECISIONS.md — DEC-083](DECISIONS.md#dec-083--preparation-status-must-reflect-the-effective-current-configuration-visible-to-the-user-a-manual-time-axis-is-unconditionally-blocking-never-ready-confirmed-or-not-and-a-time-axis-draft-that-differs-from-the-last-savedapplied-configuration-produces-its-own-blocking-unsaved-changes-issue-computed-live-client-side-with-zero-network-round-trip))
closes a real gap: the `manual` Time Axis interpreter (an engineer
assertion, never a real per-row reading) could previously reach
`is_ready=True`/"Ready for Powerwave" -- `readiness_service` never
encoded the SAME unconditional exclusion `is_time_axis_resolved()`/
`convert_preparation_source()` already both enforce, regardless of
`confirmed`. `readiness_service._time_axis_readiness_issues()` now
blocks any `manual` configuration outright (`ISSUE_TIME_AXIS_MANUAL_
UNRESOLVED`). Separately, the Data Preparation Time Axis form had no
"unsaved draft" concept at all -- a user could change the interpreter/
family/provenance/confirmed/columns without clicking Save while
Preparation Status kept describing the OLD, still-applied
configuration. `frontend/index.html` now compares the form's live
fields against the last-saved configuration client-side
(`wwDataPrepTimeAxisDraftIsDirty()`, zero network round trip) and
layers a synthetic blocking "Unsaved Time Axis changes" issue
(`wwDataPrepEffectiveIssueSummary()`) that the Preparation Status
headline/counts, View Issues, Continue-to-Powerwave, and Export Cleaned
Data ALL now read through, so they can never disagree. See
[Implemented capabilities](#implemented-capabilities). A prior same-day
hardening/transparency enhancement ([DECISIONS.md — DEC-082](DECISIONS.md#dec-082--explicit-time-axis-interpreter-selection-is-authoritative-auto-detection-may-recommend-but-a-central-allowed_families-compatibility-guard-blocks-confirmationmaterialization-whenever-an-explicitly-selected-or-restored-sample-interpreters-own-family-contract-does-not-match-what-was-actually-detected))
closes a real gap: an explicitly-selected sample interpreter (e.g.
`absolute_datetime`) whose own detected family did not actually match
its declared contract (e.g. genuinely bare time-of-day data) previously
reached `is_ready=True` and converted successfully as if nothing were
wrong -- the mismatch was never centrally guaranteed to block. Every
sample interpreter now declares its own `allowed_families` (`app/
services/time_axis_service.py`, right next to `interpreter_id`); a new
`DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH` (routing to the existing
`STATUS_NEEDS_ATTENTION`, added to `readiness_service`'s existing
blocking-code set) is applied centrally at all three `detect()` call
sites (save, live GET, dry-run preview) -- so `is_ready`/conversion/
export are all protected for free via the SAME pre-existing mechanism
`unparseable_datetime` already uses, never a new gate. The selected
interpreter is never silently changed: the Data Preparation Time Axis
panel now shows an inline "Use `<suggested interpreter>`" action on a
mismatch (existing progressive-disclosure diagnostics list, no new
modal) that only switches the dropdown when explicitly clicked.
`repeated_timestamp_precision_loss` is the one interpreter whose own
`allowed_families` genuinely lists two families
(`FAMILY_ABSOLUTE`/`FAMILY_PARTIAL`), matching what `_analyze_buckets()`
already intentionally supports. See
[Implemented capabilities](#implemented-capabilities). A prior same-day
enhancement
([DECISIONS.md — DEC-081](DECISIONS.md#dec-081--csvexcel-absolute-time-support-extended-to-minute-resolution-24-hour-time-of-day-and-explicit-ampm-hour-only-time-plus-fixed-duration-elapsed-units-minuteshoursdaysweeks-bare-hour-only-date-onlyweek-onlymonth-onlyyear-only-absolute-time-elapsed-monthsyears-and-the-existing-iso-reduced-precision-fast-path-gap-all-remain-explicitly-out-of-scope))
closes a real reported gap: `_TIME_PATTERNS` (the shared pattern table
`absolute_datetime`/`split_date_time` both use) had no 24-hour
minute-resolution pattern at all (`"3/6/2026 17:25"` was unparseable,
even though the 12-hour minute-only form already worked), and
`KNOWN_ELAPSED_UNITS` had no fixed-duration minutes/hours/days/weeks
despite the conversion mechanism trivially supporting them. Added:
`%H:%M` (24-hour minute resolution), explicit AM/PM hour-only
(`1pm`/`2am`, case-insensitive, with or without a space), and elapsed
`minutes`(60s)/`hours`(3600s)/`days`(86400s)/`weeks`(604800s) with
fixed, deterministic multipliers. Deliberately NOT added (see DEC-081
for the full boundary): bare 24-hour hour-only, absolute date-only/
week-only/month-only/year-only, and elapsed months/years (no fixed-
seconds factor exists for a calendar-variable unit, and this
interpreter never has an anchor date such a unit could be resolved
against). The pre-existing ISO-8601 reduced-precision fast-path gap
(`datetime.fromisoformat()` silently accepting date-only/week-only ISO
strings) remains unchanged and separately tracked. 55 new tests
(3039 -> 3094 passed). See [Implemented capabilities](#implemented-capabilities).

A prior-day (2026-09-04) correctness fix
(no DEC — a bug fix implementing already-expected behavior, not a new
owner-level product decision) closes a confirmed Data Preparation
Workspace concurrency race: rapid metadata edits (column role/
Engineering Quantity/Measured Unit, header row, data region, cell
edits, row exclusions, undo/redo/reset, worksheet switching) could
previously have their frontend state silently regressed or corrupted
because `wwDataPrepFetchPreview()` (the ONE function ~30 call sites
funnel through) applied whichever `/rows` response arrived last over
the network, not whichever request was fired last. Fixed entirely in
`frontend/index.html`, with **zero backend changes** — the backend's
own `WorkingOverlay` was already correct; every accepted edit was
already durable, just sometimes displayed out of order. Four layered
guards now protect every path through that one function: a monotonic
`previewRequestSeq` counter (only the latest request's response may
ever apply, the same pattern `wwTable.requestSeq`/
`channelEntry.requestSeq` already use elsewhere), explicit source/
worksheet-identity checks captured at request time, and a
`working_revision` monotonicity check (an older revision never
overwrites a newer one, even across the mutation-response path via
`wwDataPrepApplyOverlaySummary()`). A separate, per-column write-
serialization mechanism (`wwDataPrepEnqueueColumnWrite()`) closes the
confirmed Engineering-Quantity/Measured-Unit dependency race (a rapid
Quantity→Unit edit could previously reach the backend out of order and
be rejected with `400 invalid_measured_unit` since Measured Unit
validation depends on the column's current Quantity) — writes for the
SAME column (role/quantity/unit) are now strictly ordered, while
different columns continue to progress fully independently. A tenth
same-day enhancement
([DECISIONS.md — DEC-080](DECISIONS.md#dec-080--csvexcel-waveform-columns-may-carry-an-explicit-measured-unit-quantity-dependent-and-never-guessed-from-engineering-quantity-cleaned-exports-encode-it-as-an-additional-strict-suffix-a-re-upload-restores-analogchannelunit-now-reaches-per-unit-conversion-for-csvexcel-closing-the-dec-077-conversion-gap))
adds an explicit, user-selected **Measured Unit** for CSV/Excel
Waveform columns — a closed, quantity-dependent list (e.g. Voltage:
`V`/`kV`; Active Power: `W`/`kW`/`MW`/`GW`), separate from and never
guessed from Engineering Quantity (DEC-077). This closes a real
conversion gap DEC-077's own investigation had already surfaced:
`AnalogChannel.unit` was hardcoded to `""` for every CSV/Excel channel,
so Per-Unit conversion silently stayed `base_required` even with a base
correctly configured. `preparation_conversion_service.py` now writes
the selected Measured Unit into `AnalogChannel.unit` directly — the
entire fix, since `app.domain.per_unit`'s own conversion functions
already accepted and normalized a measured-unit string; zero changes
were needed to `per_unit.py`, `group_aware_per_unit.py`, or DEC-078's
Angle per-unit guardrail. Cleaned exports encode the unit as an
additional strict suffix (`"<label> (<Quantity>) [<Unit>]"`), restored
on re-upload without requiring the manifest; a blank unit remains valid
and is never a readiness blocker. See
[Implemented capabilities](#implemented-capabilities). A ninth
same-day enhancement
([DECISIONS.md — DEC-079](DECISIONS.md#dec-079--canonical-table-view-v1-a-read-only-one-recording-at-a-time-table-over-the-exact-canonical-disturbancerecord-with-a-new-boundedpaginated-get-sourcesidtable-endpoint-no-cross-source-merging-no-source-format-branching-no-workspace-synchronization-time-offsets))
implements **Canonical Table View v1**, replacing the previously-
disabled sidebar "Table" button and the Waveform|Table|Split
placeholder with a real, read-only table over one recording's exact
canonical `DisturbanceRecord` at a time — never a merge of multiple
recordings, never a reconstruction of the raw source file, never a
second copy of Waveform View's own plotting data. A new
`GET .../sources/{id}/table?offset=&limit=` endpoint returns exact,
unreduced canonical rows (deliberately NOT reusing the waveform
endpoint's point-budget/envelope reduction); a "row" is simply a slice
of the same shared `DisturbanceRecord.waveform_data` DataFrame every
analog and digital channel already lives in, so multi-rate COMTRADE and
irregular CSV/Excel timing both work with zero source-format branching
anywhere in the new code. Table time is always the recording's own
canonical source time — workspace synchronization offsets (manual
alignment, common t0, event sync) are a Waveform-View-only concept and
are never applied here. Pagination reuses the existing Data Preview
pagination UX verbatim; Per-Unit display mode is verified (via a
dedicated regression) to never affect table values. See
[Implemented capabilities](#implemented-capabilities). An eighth
same-day enhancement
([DECISIONS.md — DEC-078](DECISIONS.md#dec-078--voltage-anglecurrent-angle-channels-plot-on-a-secondary-right-y-axis-sharing-their-magnitude-siblings-panel-the-same-two-quantities-are-never-eligible-for-voltagecurrent-per-unit-conversion))
plots Voltage Angle/Current Angle channels on a genuine secondary
(right) Plotly Y-axis while keeping them in the SAME panel as their
magnitude sibling — panel grouping itself (by broad `engineering_type`)
is unchanged; only axis selection within a panel is new, keyed purely
on the canonical `engineering_quantity` (DEC-077), never source format.
A secondary axis appears only when a panel genuinely mixes an angle
channel with a non-angle one; an angle-only panel keeps its one axis,
retitled "Angle." The SAME enhancement closes a real risk the
investigation found: `engineering_quantity` never reached the plotting
layer before this (dropped one hop after the channel list fetch), and
the backend's own per-unit eligibility check keyed on broad
`engineering_type` alone — meaning a Voltage-Angle channel was
previously eligible for kV-scale/Voltage-Base per-unit conversion, a
physically meaningless operation. Voltage Angle/Current Angle are now
always `not_applicable` for per-unit conversion, regardless of
configuration; COMTRADE and calculated channels (whose
`engineering_quantity` stays "Undefined") are completely unaffected.
See [Implemented capabilities](#implemented-capabilities). A seventh
same-day enhancement
([DECISIONS.md — DEC-077](DECISIONS.md#dec-077--csvexcel-waveform-columns-may-carry-an-explicit-engineering-quantity-cleaned-exports-encode-it-as-a-strict-deterministic-label-suffix-that-a-re-upload-restores-without-depending-on-the-manifest))
adds an explicit, user-SELECTED "Engineering Quantity" for CSV/Excel
Waveform columns (Voltage/Voltage Angle/Current/Current Angle/Active
Power/Reactive Power/Frequency/ROCOF/Undefined), fixing the root cause
a prior-session investigation found: the existing channel classifier
(`classify_analog_channel()`) was never broken, CSV/Excel simply never
fed it a signal. Selecting a quantity flows straight into canonical
channel metadata (`AnalogChannel.parameter_type`) at conversion time,
reusing that SAME classifier unchanged — COMTRADE and calculated
channels are completely unaffected. Cleaned exports encode a known
quantity as a strict `<label> (<Engineering Quantity>)` header suffix
(e.g. `CBDK_V1 Magnitude (Voltage)`), which a re-upload restores
deterministically once the column is assigned the Waveform role — the
manifest is never required for restoration. See
[Implemented capabilities](#implemented-capabilities). A same-day UX
refinement (no DECISIONS entry — a straightforward navigation
improvement, not an architectural decision) gives the Data Preparation
Workspace's raw
preview pager First/Last buttons and direct page-number entry
alongside the existing Previous/Next: `[First] [Previous]  Page
[__] of N  [Next] [Last]`. First/Last jump straight to the target page
in one bounded request (reusing the exact same final-offset formula
"Go to Last Rows" already used, which remains a separate, Data-Region-
scoped control), never stepping through intermediate pages; the page
input validates `1 <= page <= total_pages` client-side and rejects
invalid values without a backend request. Purely frontend/render-
derived from the existing `offset`/`limit`/`total_row_count` preview
state — no backend/API change. DEC-075's Configured Time column
remains correctly anchored to the dataset's true first active row
across every navigation path (First/Previous/Next/Last/direct jump),
verified directly (see [Implemented capabilities](#implemented-capabilities)).
A sixth same-day enhancement
([DECISIONS.md — DEC-076](DECISIONS.md#dec-076--cleaned-exports-manifestprovenance-bundle-is-now-optional-the-default-export-cleaned-data-action-returns-the-cleaned-csvxlsx-directly-never-a-zip))
makes cleaned export's manifest/provenance bundle OPTIONAL: the default
"Export Cleaned Data" click now downloads the cleaned CSV/XLSX directly
(no ZIP, no forced `manifest.json`); a new, visually secondary
"Download with manifest" action performs the original DEC-074
ZIP+manifest export unchanged. Provenance capability itself is not
removed, only demoted from the default to an explicit opt-in — see
[Implemented capabilities](#implemented-capabilities). A fifth
same-day enhancement
([DECISIONS.md — DEC-075](DECISIONS.md#dec-075--data-preview-shows-a-read-only-derived-configured-time-column-once-the-time-axis-is-resolved-using-the-same-standardized-representation-and-normalization-semantics-as-cleaned-export-dec-074-and-canonical-conversion))
adds a read-only, virtual "Configured Time" column to the Data
Preparation Workspace's own raw/working preview TABLE (`GET .../rows`
gains an additive `configured_time` field) — once the Time Axis is
resolved, the engineer can directly SEE the exact standardized values
(ISO-8601 for absolute, relative seconds for every other family)
Powerwave will actually use, alongside the still-fully-editable
original source Date/Time columns, on every preview page (always
correctly anchored to the dataset's true first active row, never reset
by pagination). Reuses DEC-074's own representation/normalization
exactly — the two can never disagree. See
[Implemented capabilities](#implemented-capabilities). A fourth
same-day enhancement
([DECISIONS.md — DEC-074](DECISIONS.md#dec-074--cleaned-export-serializes-the-resolvedconfigured-time-axis-a-standardized-timetime-s-column-not-the-original-source-time-axis-columns-a-usable-time-axis-plus-at-least-one-waveform-column-is-now-required-before-a-reusable-cleaned-export-can-be-produced))
supersedes Slice 12's own original export-time policy: cleaned export
now serializes the RESOLVED/CONFIGURED Time Axis (one standardized
`Time`/`Time (s)` column, re-calling the already-confirmed interpreter
exactly like Slice 10's own canonical conversion does) instead of the
original source Time Axis columns verbatim — a reusable cleaned export
now REQUIRES a usable Time Axis plus at least one Waveform column (a
real behavior change from "export available regardless of readiness").
A third same-day UAT fix
([DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export))
simplifies the CSV/Excel column-role model to exactly three roles —
`Not Assigned` (the default), `Time Axis`, `Waveform` — retiring
`Unknown`/`Metadata`/`Quality-Status`/`Ignore` and Slice 4's own
separate boolean ignore/unignore toggle. A second same-day UAT fix
simplifies the Time Axis confirmation UX: the generic "☐ Confirmed"
checkbox now appears ONLY when Powerwave is asking the engineer to
accept a derived/reconstructed timing suggestion — never for a plain
native reading, an ambiguity already resolved by an explicit date-
order/unit choice, or directly user-entered timing, all of which Save
alone already persists as usable. An earlier same-day fix recognized
2-digit years (`3/6/26`, `03-06-26`, etc.) for `dmy`/`mdy` date orders.
CSV/Excel ingestion Slices 1-12 (raw preparation through cleaned data
export) remain the current end of the implemented slice sequence.

## Current status

`oruxa_powerwave` is a working COMTRADE waveform-analysis web app: FastAPI
backend (`backend/app/`) + a single-page vanilla-JS frontend
(`frontend/index.html`, no framework/build step), deployed to DEV
(auto-deploy on `main`) with PROD available but held back manually. Beyond
COMTRADE upload/parse/browse, the app now has a full multi-source,
multi-panel waveform workspace with Time-Group-aware synchronization,
cursors, t0, annotations, a group-aware Per-Unit measurement model,
calculated channels, and digital-channel display, an `Analysis` page
hosting five engineering analyzers (Phasor/Overcurrent/Impedance Locus/
Sequence Components/Distance Protection), and — as of 2026-09-19 — a
SEPARATE, independent `Compliance` top-level page (see
[DEC-100](DECISIONS.md#dec-100--compliance--capability-is-a-top-level-application-function-independent-of-analysis-slice-1-is-a-workspace-shell-only)),
now with a real Voltage Measurement Selection + Normalization
Foundation as of 2026-09-20 (Slice 2, corrected the same day to scope
role resolution to an explicitly selected Bay/Measurement Group, and
corrected again 2026-09-23 so opening Compliance directly on a
multi-bay workspace auto-bootstraps Measurement Group discovery rather
than dead-ending, and — also 2026-09-23 — a real Reference Profile/
Reference Layer engine with static Comparison Chart rendering (Slice 3;
generic reference-profile domain model, built-in/custom profile
lifecycle, table-first profile editor, the Comparison Chart rendering
active reference boundaries via Plotly). **Reference Layers/Reference
Profiles work in a workspace that has never had a source uploaded at
all** — a deliberate, explicit product requirement, not an oversight;
Measurement stays a separate, optional input that becomes available
once a source/Bay/quantity exist, and uploading a source never resets
already-configured Reference Layers. Event Alignment/Results remain
Slice 1's own placeholders. As of 2026-09-24, a `ReferenceProfile` no
longer bakes in WHICH canonical measurement quantity it evaluates —
that is now a separate `AssessmentDefinition` (representation/phase
treatment/member/measurement location/provenance, DEC-110), so a
profile can express conventions like "minimum of the three line-line
RMS values" that Slice 2's own nine canonical quantities alone could
never represent, and can legitimately stay fully `unspecified` when a
requirement genuinely does not state one. No measurement resolver
exists yet to actually derive/compare a trace — compatibility is
therefore always `not_yet_applicable` today. As of 2026-09-24 (same
day), Compliance's own jurisdiction-neutrality became an explicit,
tested architectural invariant rather than an incidental fact (DEC-111):
production Reference Profile domain/service code is proven, by a
tokenizer-based structural test, to contain no named grid code/utility/
OEM as part of actual code (as opposed to documentation/comments
explaining the constraint itself); bundled profiles remain
architecturally possible but production still ships zero by default;
provenance/version metadata (`jurisdiction`, `authority`,
`document_title`, `document_revision`, `effective_date`,
`source_section`, `source_page`, `manufacturer`) lets independent
revisions of the same requirement coexist without Powerwave ever
assuming a newer one replaces an older one; and the portable-JSON-
import/export lifecycle (session-scoped only, no database, no
localStorage, no account system) was named as an explicit product model
with a real local-file download/upload flow browser-tested end-to-end.
UI terminology was aligned to generic wording ("Reference Library",
"Create Custom Reference", "Import Reference…") — never "My Profiles"/
"User Library"/a jurisdiction-specific label, since there are no user
identities in this application. See
[COMPLIANCE_CAPABILITY.md](COMPLIANCE_CAPABILITY.md),
[DEC-109](DECISIONS.md#dec-109--compliance-slice-3-a-generic-reference-profilereference-layer-domain-model-static-comparison-chart-rendering-and-a-reference-subsystem-lifecycle-fully-independent-of-any-uploaded-recording),
[DEC-110](DECISIONS.md#dec-110--compliance-slice-3-refinement-referenceprofile-is-separated-from-how-a-measured-quantity-is-derived--a-new-assessmentdefinition-model-bridges-the-reference-boundarycurve-to-compliance-slice-2s-canonical-measurement-quantities-with-unspecified-as-a-first-class-state-and-no-measurement-resolver-implemented-yet),
and
[DEC-111](DECISIONS.md#dec-111--compliance-is-architecturally-jurisdiction-neutral-reference-requirements-are-portable-json-data-never-engine-code-provenanceversion-metadata-lets-independent-revisions-coexist-importedcustom-profiles-are-session-scoped-only-json-is-the-durable-persistence-mechanism).
CSV/Excel ingestion is the current workstream — Slices 1-12 (raw preparation-source upload
through canonical `DisturbanceRecord` conversion, existing-waveform-
integration verification, and cleaned data export) are implemented;
progressive automation (Slice 13) is not (see
[Current next workstream](#current-next-workstream)).

## Architecture

**Backend** (`backend/app/`): FastAPI app via `create_app()`. Key domain
modules beyond the original COMTRADE port (`domain/source.py`,
`domain/timing.py`, `channel_classification.py`,
`digital_classification.py`): `time_grouping.py` (Time Group derivation),
`synchronization.py` (manual alignment offsets + t0), `calculated_channel.py`,
`measurement_group.py` / `measurement_group_detection.py` /
`voltage_group_config.py` / `current_group_config.py` / `voltage_reference.py`
/ `per_unit.py` (the Per-Unit measurement model), `event_detection.py` /
`rms_detector.py`. `providers/` still holds only `base.py` and
`comtrade.py` — no CSV/Excel provider exists yet. No persistent storage of
uploaded event files (DEC-015, unchanged); the active workspace retains
each source's full-resolution parsed record in memory only (DEC-019).

**Time Groups** (DEC-057 and its follow-on TG-A…TG-H/TG-FINAL slices,
DEC-058 through DEC-069) are the current backbone of the multi-source
waveform workspace:

- Groups are derived by **overlap of sources' own raw recorded absolute
  intervals** (connected components over an overlap graph on
  `start_time`/duration), never mere start-time proximity. An elapsed-only
  source (no trustworthy `start_time`) always becomes its own solo,
  unaligned group — never auto-merged with another elapsed-only source.
- Placement is layered and composed only at read time, never stored
  combined: `effective_alignment_offset_s = timestamp_placement_offset_s`
  (automatic, derived from each source's own recorded start time)
  `+ manual_alignment_offset_s` (the engineer's own Synchronise Sources
  correction, DEC-053's original mechanism, unchanged semantics).
- A **Time Group Canvas** exists only for a group with at least one
  currently displayed channel (created lazily, removed when its last
  channel is removed) — never one for every possible group up front.
- Each Time Group Canvas owns its **own**: waveform panels, navigation
  toolbar (Zoom/Pan/Reset Time View/Autoscale Y), Cursor A/B (and the A-B/Δt
  readout), t0, Synchronise Sources context (its own local sync button and
  group-filtered source list), Time Range slider, ruler (including its own
  Absolute-mode wall-clock origin), and annotation placement/anchoring/
  reprojection context (every annotation resolves its own owning group
  dynamically from `data.sourceId`, never a cached group id and never a
  "primary group" fallback).
- **DEC-078 (2026-09-04) gives a waveform panel a genuine secondary
  (right) Plotly `yaxis2`** — used ONLY by a Voltage Angle/Current Angle
  trace (`channel.engineeringQuantity`, DEC-077, now threaded all the
  way to the plotting layer), and ONLY when that panel also contains a
  non-angle channel (an angle-only panel keeps its one axis, retitled
  "Angle"). Panel GROUPING is unchanged — a Voltage magnitude and a
  Voltage Angle channel already shared one panel via the broad
  `engineering_type` grouping key; this only decides which of that
  panel's axes each trace uses. COMTRADE and calculated channels
  (`engineering_quantity` always `"Undefined"`) are structurally
  unaffected — no `yaxis2` is ever created for them.
- **Detect Event** remains fully implemented and is internally Time-Group-
  aware (group-filtered source list, group's own visible range, writes only
  its own group's t0), but its normal UI entry point is deliberately hidden
  behind `WW_DETECT_EVENT_UI_ENABLED = false` — a one-line flip re-enables
  it; this is a product decision, not a missing feature.
- Sticky UI (current, DEC-068/069): the numerical A/B/Δt cursor readout
  lives in each canvas's own top sticky toolbar row; the small A/B position
  badges are nested inside that canvas's own ruler, inheriting the ruler's
  sticky behavior; a separate bottom-sticky wrapper holds only the Time
  Range slider. All of this is per-Time-Group, not shared.
- The **TG-FINAL closure audit** (DEC-069) re-verified every
  `wwPrimaryTimeGroupId()`/`ww.viewport`/`ww.workspaceBounds` use, every
  legacy singleton DOM id, and every per-group state Map's lifecycle. It
  found and fixed exactly one remaining active correctness defect (an
  Absolute-mode hover tooltip that read the wrong group's wall-clock
  origin) and confirmed every other surface was already either correctly
  per-group or intentionally workspace-global. **No known active Time
  Group correctness defect remains.**

**Intentionally workspace-global** (not migration gaps — by design, and
re-confirmed by the TG-FINAL audit):

- Layout Mode (Grouped/Separate/Custom) — a workspace-wide display
  preference; Time Group stays a hard panel boundary inside every mode,
  including Custom.
- Time Mode (Absolute/Elapsed) — a workspace-wide display preference; only
  the wall-clock *origin* each ruler computes labels from is per-group.
- Unit Mode (Per-Unit toggle).
- Upload / workspace lifecycle actions (`Start new workspace`, source
  removal) — these clear every per-group Map at once, by design.
- The annotation review drawer — reads each annotation's own (now
  correctly per-group) computed position; a per-group drawer was
  considered and explicitly rejected.
- Global navigation/shell (Global Header, Main Sidebar Menu, Bottom Status
  Bar).

## Implemented capabilities

- **COMTRADE ingestion**: two-slot `.cfg`/`.dat` upload, parse, engineering-
  type channel classification (backend-computed), ephemeral per-request
  parsing (no event files ever persisted to disk/storage).
- **Application shell**: full-viewport Global Header, collapsible Main
  Sidebar Menu, drag-resizable Workspace Sidebar (source-first hierarchy:
  Recording → Analog/Digital → Category → Channel), a dominant Main
  Workspace, and a Bottom Status Bar. **Recordings** and **Waveform** are
  separate top-level pages; Recordings has its own upload modal
  (`RECORDING_FORMATS`-driven) and per-recording detail/Open-Analyse flow.
  Light/Dark theme is a single, app-wide, `localStorage`-persisted,
  cross-tab-synced preference.
- **RECORDINGS sidebar recording-start timestamp**: each source card's
  metadata line now reads `N analog · N digital · rate · duration ·
  recording-start-timestamp`, e.g. `139 analog · 538 digital · 5 kHz ·
  0.825 s · 2026-07-25 13:09:44.2106`. The timestamp is the source's raw,
  immutable `start_time` (`SourceSummaryOut.start_time` /
  `TimingInformation.start_time`) — never `trigger_time`, never a manual
  synchronization offset, never a Time-Group-derived placement or t0. An
  elapsed-only source (no absolute `start_time`) simply omits the segment.
  Truncated (never rounded/padded) to 4 fractional digits; no timezone
  conversion is applied.
- **Multi-source waveform display**: one independent Plotly instance per
  panel (never one figure with fixed subplots); Grouped (by
  `engineering_type`)/Separate (one panel per channel)/Custom (user-defined
  via an Edit Channel Groups dialog) layout modes, all Time-Group-bounded;
  every panel independently resizable (100–600px, presentation-only).
- **Canonical Table View v1 (DEC-079, 2026-09-04)**: a read-only table
  showing one recording's exact canonical `DisturbanceRecord` data at a
  time — canonical Time first, then every analog channel (canonical
  order, with unit/Engineering Quantity), then digital channels; a
  source selector switches which recording is shown, always fully
  replacing the table, never merging. Backed by a new
  `GET .../sources/{id}/table?offset=&limit=` endpoint returning exact
  unreduced rows (no plot-style downsampling); paginated with the same
  First/Previous/direct-page-entry/Next/Last UX as Data Preview. Table
  time is the recording's own canonical source time, never a
  workspace-synchronization-adjusted one. Split View is not
  implemented; the sidebar Table button and the local Waveform|Table|
  Split selector share the same `shell.activeView` state.
- **Adaptive resolution**: ≤10,000 original samples per channel per
  requested range returns full resolution; above that, a peak-preserving
  min/max envelope reduction with a pixel-aware point budget
  (`clamp(plot_width_px*4, 4000, 20000)`). Backend full-resolution
  authority and COMTRADE parsing are unaffected.
- **Synchronization & timing**: automatic timestamp-based initial
  placement composed with an engineer's own manual alignment offset (see
  [Architecture](#architecture)); Absolute (real recording wall-clock) and
  Elapsed time-axis modes, both group-correct; per-Time-Group t0 with
  internally-supported, UI-hidden Detect Event.
- **Default/auto-fit waveform time extent (DEC-037, hardened
  2026-09-10)**: the workspace/per-Time-Group default extent Reset Time
  View restores is the union min/max of every currently CONTRIBUTING
  source's own effective (offset-applied) bounds — never "longest
  duration wins," and a non-contained pair of source ranges unions
  correctly. A source contributes if it is currently displayed, or has
  never yet had a channel displayed at all (DEC-037's own original
  zero-channel-source-open case, preserved); a source that WAS displayed
  and is now fully hidden stops contributing until re-shown, and a fully
  removed source never contributes. This is narrower than, and separate
  from, "which sources participate in the workspace" generally (still
  every opened source, unchanged, e.g. for the Synchronise Sources
  source list) — see
  [DECISIONS.md — DEC-037's own 2026-09-10 update](DECISIONS.md#dec-037--waveform-time-domain-state-is-source-aware-source-bounds-workspace-bounds-and-viewport-are-distinct-phase-4a-uat10)
  for the full rule. Synchronization/reference-source ownership (the
  first-uploaded-source rule) is unaffected. The viewport itself only
  auto-resets the engineer's current zoom when the contributing set's own
  bounds actually change value.
- **Per-Unit measurement model**: the group-aware model (DEC-050's target)
  has its core implemented — automatic measurement-group detection,
  group-aware Voltage and Current PU conversion, a frontend Measurement
  Groups configuration UI, and calculated-channel same-group inheritance.
  The older source-wide conversion (DEC-049) remains as the fallback for
  channels outside any detected group — a deliberate coexistence, not a
  bug. See [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md)
  (authoritative) and [DECISIONS.md — DEC-050](DECISIONS.md#dec-050--per-unit-measurement-model-is-clarified-to-be-measurement-group-aware-the-currently-deployed-source-bound-model-dec-049-is-not-the-final-target).
  **DEC-078 (2026-09-04) adds one additive guardrail on top of both
  paths**: `app.services.waveform_service._resolve_effective_per_unit()`
  (the one dispatch point both the group-aware and legacy paths already
  funneled through) now short-circuits to `not_applicable` whenever a
  channel's own `engineering_quantity` (DEC-077) is `"Voltage Angle"` or
  `"Current Angle"`, regardless of its broad `engineering_type` or
  whether a base is configured — an Angle-quantity channel is never
  eligible for Voltage/Current per-unit conversion. `resolve_per_unit()`/
  `resolve_group_aware_per_unit()` themselves are unchanged; every
  channel with `engineering_quantity = "Undefined"` (every COMTRADE
  channel today, and any CSV/Excel channel the engineer never
  classified) keeps today's exact broad-type-only behavior.
  **DEC-080 (2026-09-04) closes a real conversion gap**: CSV/Excel
  Waveform columns may now carry an explicit, quantity-dependent
  Measured Unit (e.g. Voltage: `V`/`kV`), threaded directly into
  `AnalogChannel.unit` at conversion time — previously always `""`,
  which meant `_measured_unit_scale()` could never recognize a CSV/
  Excel Voltage/Current channel's own unit, leaving Per-Unit `base_
  required` even with a base configured. A CSV/Excel Voltage or
  Current channel with a valid Measured Unit and a configured base now
  resolves `configured` and scales into `pu`, identically to COMTRADE
  — zero changes to `per_unit.py`/`group_aware_per_unit.py` themselves
  were needed. A blank unit still leaves the channel `base_required`
  (fail-closed, unchanged); the DEC-078 Angle guardrail is unaffected
  (a valid `deg`/`rad` unit never makes an Angle channel PU-eligible).
  **Per-Unit Settings hierarchy, Slice 1 (2026-09-10, UI-only formalization
  of [DECISIONS.md — DEC-051](DECISIONS.md#dec-051--dec-049dec-050-live-endpoint-coexistence-precedence-group-membership-not-configuration-completeness-decides-which-resolver-applies-to-a-channel)'s
  existing precedence, no engine/API change)**: the Unit Mode toolbar menu
  no longer exposes Measurement Groups and the source-wide modal as two
  directly-competing items. Both are now reached through one new parent
  surface, `#perUnitSettingsOverlay` (`wwOpenPerUnitSettingsBtn`), which
  explains the relationship before routing into whichever the engineer
  picks: **Measurement Groups** (`Recommended` badge — DEC-050, the
  specific path for a channel a group actually covers) and **Source
  Default** (`Fallback` badge — DEC-049's existing source-wide modal,
  user-facing title changed from "Manage Per-Unit Bases" to "Source
  Default — Per-Unit"; internal id `#perUnitProfilesOverlay` and every
  function/endpoint unchanged). The word "Legacy" no longer appears
  anywhere user-facing. The Source Default modal's own hint text — which
  had claimed "every eligible Voltage/Current channel of that recording
  uses its own configuration automatically" — was stale since DEC-051
  (a grouped channel does not use it) and is corrected to state its
  actual current scope. Each child modal gets a small "← Per-Unit
  Settings" link back to the parent (close-then-reopen, no nested modal
  stacking). Backend precedence itself (DEC-051) is completely
  unchanged — this is presentation only. Coverage counts and per-channel
  active-configuration traceability remain deferred to a future UAT
  slice (not implemented). See `test_frontend_per_unit_settings.py` plus
  updated assertions in `test_frontend_measurement_groups.py`/
  `test_frontend_per_unit_mode.py`.
  **Same-day UAT fix**: selecting **Per Unit** from the dropdown had
  been auto-opening the Source Default modal whenever no source yet had
  a configured DEC-049 profile (a pre-existing "Section 68" convenience
  that predates this hierarchy) — this undermined the new
  Recommended/Fallback framing by making Source Default look like the
  automatic path. Removed outright: selecting Per Unit now only changes
  display mode; opening any configuration surface is always the
  separate, explicit "Per-Unit Settings…" action. Zero backend/API
  change.
  **Slice 2 (Per-Unit Settings hierarchy, coverage) adds a read-only
  "Per-unit coverage" section to the parent surface** — for the
  selected recording, how many applicable Voltage/Current channels are
  covered by a Measurement Group, how many fall to Source Default, and
  how many currently need configuration. New
  `app/services/per_unit_coverage_service.py` (`build_per_unit_coverage_summary()`)
  classifies each of a source's own `AnalogChannelSummary` entries by
  calling the SAME public building blocks
  `waveform_service._resolve_effective_per_unit()` already dispatches
  through (`resolve_group_aware_per_unit()` first, falling through to
  the DEC-049 `resolve_per_unit()` only when the channel is not grouped)
  — DEC-051's own precedence is never re-implemented, only mirrored in
  orchestration order; a grouped-but-incomplete channel is
  `needs_configuration`, never silently counted as Source Default, even
  when a fully usable Source Default exists on the same source. Voltage/
  Current Angle channels (DEC-078) and digital channels are excluded
  from every count; `applicable_channel_count` always equals the sum of
  the three category counts. Pure metadata/registry read — no waveform
  sample data touched, nothing persisted, no existing registry mutated.
  New additive endpoint `GET .../per-unit/sources/{source_id}/coverage`
  (`app/api/v1/per_unit.py`, `PerUnitCoverageOut` in
  `app/schemas/per_unit.py`) — no existing endpoint/schema changed.
  Frontend: the Per-Unit Settings parent surface (`#perUnitSettingsOverlay`,
  previously pure static routing copy) gained its own "Recording"
  selector (mirroring the two child modals' own selector) and a compact
  three-row coverage stat list, refetched on source-select change.
  Empty/edge states are explicit: "Upload a recording to see Per-Unit
  coverage" (no sources), "No applicable Voltage/Current channels for
  per-unit conversion" (zero applicable, neutral wording, never a
  zero-count warning), and a distinct fetch-failure message. Only the
  "Needs configuration" row's own count gets a proportional `--warn`
  treatment when it is `> 0` — Measurement Groups and Source Default
  rows are always neutral, and Source Default usage is never shown as
  an error, matching the existing badge palette's own established
  never-`--error` convention.
  **Slice 3 (Per-Unit Settings hierarchy, channel-level traceability)
  adds per-channel "why does this show this pu value" provenance.**
  New `app/services/per_unit_provenance_service.py`
  (`build_source_channel_provenance()`/`build_calculated_channel_provenance()`)
  — its own "one source of truth" guarantee: every field is read
  directly off the exact `PerUnitResolution` that would convert the
  channel's own displayed value (`resolve_group_aware_per_unit()`/
  `resolve_calculated_group_aware_per_unit()` first, DEC-049
  `resolve_per_unit()` fallback otherwise — the identical dispatch order
  `waveform_service._resolve_effective_per_unit()`/
  `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`
  already use), so the shown explanation can never disagree with the
  actual conversion. The richer Measurement Group display fields
  (nominal LL kV, effective L-G/L-L reference, equipment rating,
  applicable voltage) are obtained by calling the SAME
  `measurement_group_view_service.build_group_view()` Slice 6's own
  modal already renders from — no new resolution math anywhere.
  DEC-052's Voltage multi-input restriction is fully respected for
  calculated channels (verified directly: unary inherits, multi-input
  Voltage Add/Subtract never does, multi-input Current does, a
  cross-group case falls back to legacy exactly like DEC-051 already
  specifies). **Source Default is displayed truthfully, never
  "corrected"**: its own resolved base is one plain amount with no
  fabricated L-L/L-G annotation and no separate nominal-vs-effective
  split, matching DEC-049's own actual (unadjusted) arithmetic exactly
  — the known, separately-governed LL/LG gap is neither fixed nor
  hidden by this slice. New additive endpoints,
  `GET .../sources/{source_id}/per-unit-resolution?channel_name=...`
  (`app/api/v1/sources.py`) and
  `GET .../calculated-channels/{id}/per-unit-resolution`
  (`app/api/v1/calculated_channels.py`), both returning
  `PerUnitResolutionOut` (`app/schemas/per_unit.py`) — read-only channel
  METADATA, fetched lazily on explicit engineer request only, never
  attached to any waveform/cursor/peak response; no existing
  endpoint/schema/resolver changed. **Frontend (source channels only
  this slice — see below for the calculated-channel UI boundary)**: a
  third RECORDINGS-sidebar channel-context-menu item, "Per-Unit
  Details…" (alongside DEC-070's existing Rename/Change colour),
  opens a small popover reusing the Calculated Channels page's own
  established label/value info-strip pattern
  (`.ww-cc-preview-info-strip`) — no new visual system. Not-applicable
  channels show a single fixed neutral line, never fabricated base
  info; a monotonic request-sequence guard (mirroring this file's own
  established `requestSeq` convention) discards a stale response if the
  popover is closed/retargeted before its fetch resolves. **Deliberate
  boundary**: the backend fully supports calculated-channel provenance
  (tested end-to-end, including DEC-052), but no frontend affordance was
  added for it this slice — the Calculated Channels/Signal Builder page
  is a structurally separate surface whose existing preview info strip
  is rendered synchronously from already-known static fields, so adding
  an async per-unit fetch there safely needs its own stale-response
  guarding (the same class of race this slice's own source-channel
  popover already handles) — reported as a small, separately-schedulable
  follow-up rather than rushed in.
  **Slice 4 (2026-09-11) corrects Source Default Voltage-base
  interpretation**, closing the exact gap
  [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) §8 had
  documented as a confirmed `[FACT]` since 2026-08-22: `voltage_base_value`
  is now uniformly the nominal SYSTEM LINE-TO-LINE voltage (identical
  semantics to `VoltageBaseConfiguration.nominal_voltage_ll_kv`) —
  a line-to-ground channel's own effective base is now correctly
  `Vbase_LL / √3`, a line-to-line channel's is `Vbase_LL` unchanged. A
  resolved reference is now required for VOLTAGE to resolve `configured`
  at all (mirrors the Measurement Group resolver's own long-standing
  gate). **The derived current-base formula
  (`Ibase = Sbase / (√3 × Vbase_LL)`) is unchanged in its own governing
  principle** — always the raw nominal `Vbase_LL`, regardless of
  reference; the old helper that multiplied by `√3` for a line-to-ground
  reference is removed outright (it would now silently double-convert).
  This intentionally changes numeric pu results for any existing
  line-to-ground Source Default configuration (e.g. `≈0.577 pu` → the
  correct `≈1.0 pu` for a 275 kV/≈158.8 kV worked example) — deliberate,
  not preserved for backward compatibility, per explicit owner
  instruction. DEC-051 precedence, DEC-052 inheritance, Measurement
  Group arithmetic, and direct/manual current-base mode are all
  byte-for-byte unchanged (calculated channels that fall back to Source
  Default inherit the fix automatically via the same, now-corrected
  `resolve_per_unit()` — no separate correction needed). Slice 2
  coverage and Slice 3 provenance reflect the corrected arithmetic with
  zero code changes of their own. Frontend: the Source Default modal's
  own cosmetic Ibase preview had the identical bug and is now corrected
  to match; its Voltage Reference tooltip (which previously, and now
  incorrectly, claimed the reference is never applied to a displayed
  channel's own value) is corrected; a new secondary "Nominal system
  voltage / Effective L-G base" preview line was added. See
  [DECISIONS.md — DEC-049's own 2026-09-11 update](DECISIONS.md#dec-049--global-per-unit-measurement-mode-workspace-scoped-base-profiles-backend-only-conversion-explicit-reassignment-and-two-axis-modeprofile-calculated-channel-inheritance-provenance)
  for the full record, including the complete test-file update list.
  **Same-day follow-up: Source Default Voltage provenance now shows the
  same three concepts a Measurement Group already shows** — Nominal
  voltage / Channel interpretation / Effective base — reusing the
  identical `nominal_base_kv`/`nominal_reference` `PerUnitResolutionOut`
  fields (never a second Source-Default-specific structure), since
  Slice 4 gave the entered Source Default Voltage Base the same fixed
  nominal-LL meaning a Measurement Group's own configuration already
  has. Source Default Current is unaffected (no equivalent "nominal LL"
  concept, so those two fields stay `null` for it). The Per-Unit Details
  popover's three-row presentation is no longer gated to Measurement
  Groups — it renders generically off `nominal_base_kv`'s presence; the
  Source Default editor's own preview (from the same-day Slice 4 UI fix
  above) is refined from one combined sentence into the same three
  separate lines. Presentation/provenance only — no arithmetic,
  resolver, precedence, or persistence change. See
  [DECISIONS.md — DEC-049's own 2026-09-11 same-day update](DECISIONS.md#dec-049--global-per-unit-measurement-mode-workspace-scoped-base-profiles-backend-only-conversion-explicit-reassignment-and-two-axis-modeprofile-calculated-channel-inheritance-provenance).
- **Calculated channels**: workspace-scoped derived analog channels —
  Reverse Polarity, Absolute Value, Multiply-by-Constant, N-input Addition,
  ordered N-input Subtraction, and trailing one-cycle RMS. Multi-input
  operations require proven synchronized sample-time alignment (no
  interpolation/resampling), and a unit-compatibility check
  (`app.domain.calculated_channel.units_compatible()`) that (Slice F1,
  2026-09-11) no longer fails open when every input's unit string is
  blank — it falls back to engineering_type compatibility in that case
  only, rejecting e.g. a blank-unit Voltage input combined with a
  blank-unit Current input, while all-`Undefined`/known-matching-unit
  behavior is unchanged (no new unit system, no dimensional-conversion
  layer). Immutable after creation, with dependency-
  aware delete/cascade. **Missing-data (null) input policy (DEC-084,
  Calc Slices 1-4, 2026-09-09) is implemented**: each calculated channel
  explicitly declares its own `null_policy` at creation time —
  `propagate_null` (backward-compatible default), `treat_null_as_zero`,
  `require_manual_value` (rejects creation outright if any required
  RESOLVED input contains a non-finite value — never creates an
  unresolved/half-created channel), or `estimate_missing_data`. Zero-
  substitution and estimation are always CALCULATION-LOCAL — the source
  array and any parent calculated channel's own retained array are
  never mutated; a channel may consume another calculated channel's own
  already-resolved output, but tracks no per-sample record of which of
  that parent's samples were themselves estimated (channel-level
  traceability only, not a provenance graph). `estimate_missing_data`
  requires an explicit `estimation_method` — Hold Last Value, Nearest
  Value, Linear Interpolation (using the aligned channel's own actual
  time coordinates, never assumed-uniform sample spacing), or Local
  Mean (additionally requires a positive-integer `local_mean_radius`,
  samples on each side of the gap) — plus a positive-integer
  `max_gap_value` (`max_gap_unit` supports `samples` only; a gap longer
  than the maximum is left entirely unfilled, never partially
  estimated). PCHIP is a recognized `estimation_method` value for
  forward compatibility only — rejected outright at creation, no SciPy
  dependency exists, never offered in the frontend. Frontend: the
  Signal Builder's Null Handling control (defaulting to Propagate Null)
  with conditional Estimation Method/Maximum Gap/Local Mean Radius
  fields; the manager's existing compact one-line summary; and full
  channel-level detail (Missing Data Handling/Method/Maximum
  Gap/Local Mean Radius) on the existing selected-channel preview info
  strip — always sourced from the API-returned channel object, never
  from in-progress builder state. Backend error responses (e.g.
  `require_manual_value_null`, `invalid_estimation_method`,
  `estimation_method_not_implemented`) are shown verbatim through the
  existing structured error area. See
  [DECISIONS.md — DEC-084](DECISIONS.md#dec-084--explicit-null-resolution-and-calculated-channel-missing-data-policy-unresolved-emptyinvalid-cells-remain-blocking-an-explicit-user-marked-null-becomes-a-distinct-resolved-state-for-waveformdata-columns-time-axis-stays-blocking-each-calculated-channel-independently-declares-its-own-null-handling-policy-never-inheriting-automatic-propagation-from-its-source)
  for the full approved policy and
  [Known intentional constraints](#known-intentional-constraints--deferred-items)
  for what remains deferred (PCHIP/SciPy, non-`samples` max-gap units,
  per-sample provenance, export, edit/update). This is layered on top
  of, and never relaxes, the existing DEC-047 time-alignment guardrail
  above (which governs whether operand SAMPLE TIMES may be combined at
  all, not how a null VALUE within an already-aligned series is
  filled).
- **Annotations**: `text_note` (floating, content-anchored), `callout`
  (waveform-anchored with a movable label box), and `peak_max`/`peak_min`
  (dynamically viewport-recalculated) — all resolve their own owning Time
  Group dynamically; a workspace-global review drawer lists every
  annotation from its own (correct) rendered position.
- **Digital channels**: shared batched full-record transition rendering
  (one multi-trace figure, not one instance per channel), Triggered/Never
  Triggered/Spare classification, and compact inline A/B cursor-value
  badges reusing the analog cursor pipeline.
- **CI/CD**: DEV auto-deploys after CI succeeds on `main`; PROD deployment
  remains a manual `workflow_dispatch`, deliberately not automatic.
- **Channel presentation customization**: right-click an analog RECORDINGS-
  sidebar channel row for `Rename…`/`Change colour…`. Both are pure
  presentation overrides keyed by the same stable `sourceId::channelName`
  identity every engineering lookup already uses (cursor values,
  calculated-channel inputs, Per-Unit membership, annotations, waveform
  trace identity) — canonical parsed names are never mutated, never sent
  to the backend, and never used as a lookup key. Reset restores the
  original name / the exact original auto-assigned color. Workspace-local
  (survives rerenders/layout/Time-Group changes, not a page refresh);
  resets on Start New Workspace/Clear workspace. Calculated channels and
  digital channels are explicitly excluded this slice — see
  [DECISIONS.md — DEC-070](DECISIONS.md#dec-070--channel-presentation-customization-recordings-sidebar-rename--color-override-is-implemented-as-a-pure-presentation-layer-above-canonical-channel-identity-analog-source-channels-only-this-slice).
- A minimal committed real-browser smoke-test foundation now protects
  critical upload/render/interaction paths — see
  [docs/development/BROWSER_SMOKE_TEST.md](../development/BROWSER_SMOKE_TEST.md).
- **A reproducible real import/parse/waveform performance baseline
  (Slice F2, 2026-09-11)** — `backend/tests/perf/baseline_runner.py`
  (explicit `python tests/perf/baseline_runner.py run --scenario ...`
  command, never pytest-collected) measures 15 MB/75 MB synthetic
  COMTRADE and 12 MB synthetic CSV scenarios through the real upload →
  parse → waveform-endpoint path — see
  [docs/development/PERFORMANCE_BASELINE.md](../development/PERFORMANCE_BASELINE.md)
  for the full methodology, results, and interpretation. No production
  code changed.
- **Event Playback — a shared, reusable workspace capability (2026-09-11,
  [DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock)
  and its own 2026-09-11/2026-09-12 revisions).** No dedicated
  `Playback` main-menu item or page exists (removed after owner UAT —
  see the revision note in DEC-085) — the everyday Restart/Play↔Pause/
  speed/seek transport + current-time readout is a shared control
  surface, mounted on Analysis pages only (Phasor today, via
  `wwPhasorMountPlaybackControls()`) since the 2026-09-12 owner product
  decision that reversed the original "waveform toolbar is Playback's
  built-in mount point" shape — the Waveform Time Group toolbar itself
  now shows only the passive Playback Cursor overlay, never the
  controls. ONE authoritative,
  frontend-only `wwPlayback` Playback Controller drives at most one
  active Time Group at a time (switching groups cleanly stops the
  previous one — never two simultaneous `requestAnimationFrame` loops);
  every source/channel in that group shares the same playback time,
  channels are never independently played; canonical time is
  **workspace time** (t=0/Time Mode affect display only, via the
  existing `wwFormatCursorPointTime()`); range is the active Time
  Group's own full union extent (`wwDeriveTimeGroupBounds()`, the
  existing DEC-037 function); timing is `requestAnimationFrame` + a
  `performance.now()` wall-clock anchor, recomputed fresh every frame.
  A **dedicated Playback Cursor overlay is architecturally separate
  from Cursor A/B** — reuses Cursor A/B's own pixel-conversion
  primitives but never reads/writes `ww.timeGroupCursorState`.
  Digital-channel state at the current playback time resolves entirely
  from already-loaded local transition data (zero backend requests per
  animation frame). A fixed seven-value speed selector (0.05×/0.10×/
  0.25×/0.5×/1×/2×/4×, default 1×, never free-entry — extended below
  0.25× on 2026-09-12 for slow engineering-event/fault inspection —
  ONE controller-wide value,
  never per-group, persists across Play/Pause/Restart/seek; a
  playing-state change re-anchors from the already-correct
  `currentTime` under the new speed with the SAME rAF chain left
  running — no jump, no restart, no second loop) and a seek scrubber
  (a native `<input type="range">`, the dedicated seek mechanism —
  never a drag on the Playback Cursor itself, never Cursor A/B; the
  first `input` event of a drag/keyboard gesture suspends the clock,
  `change` re-anchors and resumes automatically on release only if it
  was playing before, otherwise lands "paused"; selects a TIME only,
  never fabricates/interpolates engineering data — Playback itself
  knows nothing of Va/Vb/Vc, impedance, phasors, or differential
  logic). **Reusable control-surface API**
  (`wwCreatePlaybackControlsHtml()`/`wwWirePlaybackControls()`/
  `wwSyncPlaybackControls()`/`wwUpdatePlaybackControlsTick()`, all
  container-parameterized, near `wwClearWorkspace()`) — the waveform
  toolbar's own wiring/sync functions are thin wrappers delegating to
  these, never a duplicated implementation; a future engineering-
  analysis page (Distance Protection/Overcurrent/Phasors/Differential,
  none implemented yet) mounts the same markup/wiring/sync into its own
  container and subscribes via `wwPlaybackOnTick()`. Frontend/session
  state only — no backend Playback endpoint exists; resets on
  workspace clear (including speed back to 1×) and whenever the active
  Time Group's own topology disappears. Deferred to a later slice (not
  implemented, not decided against): Follow Playback, Split View
  integration, current-value polling, keyboard shortcuts, event
  sub-range selection, looping, reverse playback, frame-by-frame
  stepping, and every future analysis overlay (impedance/overcurrent/
  differential/etc. — none exist yet; they will consume this
  controller, never build their own clock). Committed test fixtures
  (`backend/tests/fixtures/comtrade/synth_playback*.{cfg,dat}`, a
  deterministic 4-second-duration COMTRADE pair — long enough for a
  real-browser test to reliably observe motion); `browser-tests/
  playback.spec.js` (12 Playwright tests, unmodified by the navigation-
  removal/reusability refactor — the strongest evidence it changed no
  externally-visible behavior); `backend/tests/test_frontend_playback.py`
  (51 static structural tests, revised to assert no dedicated menu/page
  exists and that the reusable functions are genuinely container-
  parameterized). See
  [DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock)
  for the full per-decision rationale, including the revision note.
- **CSV/Excel preparation-source upload through canonical
  `DisturbanceRecord` conversion (verified to behave like any other
  Powerwave source across Time Groups/synchronization/calculated
  channels) and cleaned-data export (CSV/Excel ingestion Slices 1-12,
  DEC-072)**:
  the Upload Recording modal's CSV and
  Excel options are both enabled (`RECORDING_FORMATS`,
  `frontend/index.html`), each with its own "Upload & Prepare" action,
  posting to `POST .../preparation-sources` (`app/api/v1/preparation_sources.py`
  — one endpoint, `csv_file` xor `excel_file`, exactly one per request)
  that validates and accepts a raw `.csv` or `.xlsx` file into a new,
  purely in-memory `PreparationSession` (`app/domain/preparation_session.py`
  + `app/services/preparation_session_registry.py`, an eighth sibling
  registry alongside `WorkspaceRegistry` and friends) — never a
  `DisturbanceRecord`, never anything a waveform request can reach.
  Excel workbooks additionally get their worksheet structure discovered
  at upload time (`openpyxl`, `read_only=True` streaming — no temp
  files, no full-sheet materialization): name/order/visible-hidden state
  and best-effort row/column counts, stored as `WorksheetInfo` on the
  same `PreparationSessionSummary`; a one-worksheet workbook is
  auto-selected, a multi-worksheet workbook requires an explicit
  `PATCH .../preparation-sources/{id}` selection. Legacy `.xls` is
  deliberately not supported (would need a separate, unmaintained
  `xlrd` dependency). Both formats appear in Recording Events (File
  Format/File Size/Status columns, populated for COMTRADE too via an
  additive `SourceMetadata.file_size_bytes` field) with status `Needs
  Preparation`; Start Time/Duration/Sampling Rate(s) show `—` rather
  than fabricated values. A `Needs Preparation` row is structurally
  excluded from `GET .../sources` (so the Workspace Sidebar's
  channel-selection list never sees it at all).

  Clicking a `Needs Preparation` row now opens a new, fourth top-level
  page — the **Data Preparation Workspace** (`#pageDataPreparation`,
  `shell.currentPage = "data-preparation"`, its own `wwDataPrep` state
  object completely separate from the waveform workspace's `ww`) —
  instead of opening a waveform (that row-click gate is still
  `status === "ready"`, unchanged). It shows the source's filename/
  format/size/status, a worksheet `<select>` for Excel (superseding
  Slice 2's own standalone Worksheet Selection modal, now removed —
  switching sheets resets the preview and re-fetches), and a paged raw
  table (spreadsheet-style column letters, 1-based row numbers, no
  header-row assumption) backed by a new
  `GET .../preparation-sources/{id}/rows?offset=&limit=` endpoint
  (default 200/max 1000 rows per page, server-enforced). CSV rows are
  streamed via `csv.reader` (never a full `pandas.read_csv`); Excel rows
  reuse `openpyxl`'s `read_only=True` `iter_rows(min_row=, max_row=)`,
  reopened fresh per request. Released on its own
  `DELETE .../preparation-sources/{id}` or on whole-workspace
  `DELETE /api/v1/workspaces/{id}` (cascades into this registry too).

  **Slice 4** adds a non-destructive Working Dataset overlay
  (`app/domain/working_overlay.py` + `app/services/working_overlay_service.py`)
  layered on top of each `PreparationSession`: cell edit/clear/reset, row
  exclude/include, and a Reset All action, each a sparse dict/set entry
  proportional to edit COUNT — never a second full copy of the dataset.
  Undo/redo is supported via a bounded (200-entry) operation history; a
  `revision` counter increments on every mutation. New endpoints under
  `.../preparation-sources/{id}/working/...`; each and the existing
  `GET .../preparation-sources` (list/detail) responses now carry a
  `working_overlay` summary (`working_revision`, `edited_cell_count`,
  `excluded_row_count`, `can_undo`, `can_redo`). The existing
  `GET .../rows` preview now returns the WORKING view by default (raw
  merged with the overlay at read time only, never persisted) — each row
  gains `excluded`/`modified_cells` (sparse, provenance-preserving), and
  the page-level response gains `working_revision`. Raw bytes are never
  mutated. The Data Preparation Workspace's table gained click-to-edit
  cells (a plain `<input>`, no spreadsheet-grid library), a per-cell
  reset action, a row toggle button, Undo/Redo, and a "Reset All
  Changes" confirm dialog; the heading switches from "Raw Data Preview"
  to "Data Preview (Edited)" once any change exists. (Slice 4 originally
  also shipped a separate per-column boolean ignore/unignore toggle,
  `ignored_column_count`/`ignored_columns` fields, and its own quick-
  toggle button in the raw preview table — all retired by the
  2026-09-04 UAT fix described under Slice 5 below, once the
  three-role column model made a separate "ignored" axis redundant.)

  **Slice 5** extends the SAME `WorkingOverlay` (not a second model)
  with header-row selection, data-region narrowing, and column
  semantic-role assignment. **A 2026-09-04 UAT fix
  ([DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export))
  simplified the ORIGINAL six-role model
  (`unknown`/`waveform`/`time_axis`/`metadata`/`quality_status`/`ignore`)
  to exactly THREE roles: `not_assigned` (the sparse, implicit default —
  never written explicitly, exactly like the retired `unknown` did),
  `time_axis`, and `waveform`.** Multiple `time_axis` columns are still
  allowed; a role remains a stated intent only, never validated/
  interpreted. All three (header/region/role) participate in the same
  bounded undo/redo history and revision counter Slice 4 already built.
  New endpoints (`PUT`/`DELETE .../working/header`,
  `.../working/data-region`,
  `.../working/columns/{column_index}/role`); the `working_overlay`
  summary gains `header_row_number`/`data_start_row`/`data_end_row`;
  the `GET .../rows` preview gains the same three plus
  `column_labels`/`column_roles`, and each row gains `is_header`/
  `in_active_region` flags (independent of, never conflated with,
  `excluded`). Column labels come from the header row's own WORKING
  values (Slice 4 edits included); a blank header cell falls back to
  `"Column {letter}"`, no header at all falls back to the plain letter,
  and duplicate header text is allowed verbatim (never disambiguated).
  Reset All now also clears header/region/role state. Frontend: a
  "Structure" panel (header-row input, data-region start/end inputs, a
  compact Column/Label/Role mapping table listing exactly Not Assigned/
  Time Axis/Waveform) plus a per-row "Header" quick-select button and
  new row styling for the header row and rows outside the active
  region. The Structure panel's own compact summary line reads e.g.
  "3 Not Assigned · 1 Time Axis · 2 Waveform."

  **DEC-075 (2026-09-04) adds a read-only, VIRTUAL "Configured Time"
  column to this same preview table** — once the current Time Axis is
  resolved (`app/domain/time_axis.py`'s new `is_time_axis_resolved()`,
  the SAME shared eligibility check DEC-074's own export gate reuses),
  `GET .../rows` gains an additive `configured_time: {column_name,
  family, values}` field, computed by a NEW `app/services/time_axis_
  service.build_configured_time_values()` (full-active-region, single
  streaming pass, matching `readiness_service`'s own full-region-scan
  shape) narrowed to the requested page by `configured_time_for_
  preview_page()`. Values use the EXACT SAME standardized
  representation DEC-074's cleaned export already established (ISO-8601
  for absolute, fixed 3-decimal relative seconds otherwise) via the
  SAME shared `time_axis_normalization` module (which gained
  `relative_seconds_with_anchor()` for this — a later preview PAGE's
  own relative values stay anchored to the dataset's TRUE first active
  row, never that page's own first row, so row 201 of a paginated
  dataset still reads e.g. `4.000`, never resets to `0.000`). Never
  counted in `column_count`/`column_labels`/`column_roles` and never
  editable/clearable/excludable/role-assignable — a wrong derived value
  is corrected by changing the Time Axis configuration, never by
  editing the derived cell. Frontend: rendered as the FIRST column in
  the preview table (a distinct dimmed/italic style plus a small
  "Derived" badge and tooltip), refreshed immediately after every Time
  Axis Save/Clear (alongside the existing refresh-on-cell-edit
  behavior) so it never shows a stale value.

  **DEC-077 (2026-09-04) adds an explicit, user-selected "Engineering
  Quantity" to a Waveform-role column's own configuration**, shown as a
  fourth column-mapping-table selector (`Voltage`/`Voltage Angle`/
  `Current`/`Current Angle`/`Active Power`/`Reactive Power`/
  `Frequency`/`ROCOF`/`Undefined`), stored sparsely on the working
  overlay's new `column_engineering_quantities` (mirrors `column_roles`
  exactly — absence means `Undefined`, meaningful only for a Waveform
  column, participates in the same undo/redo/revision history). The
  selection flows into `AnalogChannel.parameter_type` at conversion
  time and is classified by the EXISTING, unmodified-in-behavior
  `app.domain.channel_classification.classify_analog_channel()` — the
  same function COMTRADE already used — never a second, CSV-specific
  classifier; a new additive `engineering_quantity` field (default
  `"Undefined"`) rides alongside the existing broad `engineering_type`
  on every channel summary, with a deterministic mapping between the
  two (`broad_engineering_type()`) so every existing downstream
  consumer (channel-browsing groups, calculated-channel type
  inheritance, per-unit measurement-group eligibility) is completely
  unaffected. Cleaned exports encode a known quantity as a strict
  `<label> (<Engineering Quantity>)` header suffix (never `"
  (Undefined)"`); re-uploading that file restores the quantity
  deterministically once the column is (re-)assigned the Waveform role
  — via the SAME suffix grammar the exporter writes, exact-match only,
  never confused with the Configured Time column's own `"(s)"` suffix.
  Role=Waveform itself is never auto-assigned by a self-describing
  label — investigated per the task's own instruction; no existing
  precedent for automatic role assignment was found, so only the
  quantity restores, never the role.

  **A same-day UX refinement (2026-09-04, no DECISIONS entry) adds
  First/Last and direct page-number entry to this same preview's
  pager**, alongside the existing Previous/Next: `[First] [Previous]
  Page [__] of N [Next] [Last]`. Entirely frontend/render-derived from
  the existing `wwDataPrep.offset`/`limit`/`totalRowCount` state (no
  backend/API change) — `currentPage`/`totalPages` are computed fresh
  on every `wwDataPrepRenderPagination()` call, never a second,
  independently-tracked paging source of truth. `First` sets `offset =
  0`; `Last` reuses the EXACT SAME final-offset formula
  (`floor((total-1)/limit)*limit`) `wwDataPrepGoToLastRowsBtn` (Data
  Region's own "Go to Last Rows," a distinct, still-separate control)
  already established, rather than a second "last page" calculation —
  both jump directly in one bounded request, never stepping through
  intermediate pages. `Last`/the page input stay disabled whenever
  `total_row_count` itself is unknown (some Excel worksheets), matching
  "Go to Last Rows"'s own existing guard. The page-number input
  validates `1 <= page <= total_pages` client-side on Enter or blur and
  restores the current page on any invalid value (`0`, negative,
  non-integer, out of range, blank) without ever issuing a backend
  request. DEC-075's Configured Time column stays correctly anchored to
  the dataset's TRUE first active row across every navigation path
  (First/Previous/Next/Last/direct jump) — confirmed directly (e.g. row
  201 of a 0.02s-interval dataset reads `4.000` whether reached via
  repeated `Next` or a direct jump to page 2).

  **Slice 6** adds the preparation-specific Readiness Issue LANGUAGE AND
  TRANSPORT model — explicitly NOT the full Readiness Validator (still
  Slice 9's own scope). New `app/domain/preparation_issue.py`:
  `PreparationIssue{severity, code, message, location, suggested_action,
  details}` (severity one of `blocking`/`warning`/`info`;
  `location`'s four fields — `worksheet_index`/`row_number`/
  `column_index`/`field` — are each independently optional, so a
  dataset-level issue is valid) and `PreparationIssueSummary{
  evaluated_revision, current_revision, is_stale, blocking_count,
  warning_count, info_count, issues}`. `ImportServiceError` itself is
  untouched — a `PreparationIssue` is a structured finding, never an
  exception, and a real runtime failure never becomes one. Only two
  issue codes exist today (`header_not_selected`,
  `data_region_unconfigured`), produced by a short, linear
  `collect_preparation_issues()` that checks already-known CONFIGURATION
  facts only — no data interpretation — and every one of them is `info`
  severity, never implying invalidity. (A third code,
  `column_roles_unassigned`, existed originally but was retired by the
  2026-09-04 UAT fix — DEC-073 — once the three-role column model made
  a column left `not_assigned` a normal, intentional final state rather
  than incomplete configuration; readiness now blocks on the MEANINGFUL
  `time_axis_unconfigured`/`waveform_channel_missing` issues instead if
  every column is left unassigned.) Issues are derived
  LIVE on every request (no cache, no database); `evaluated_revision`
  always equals `current_revision` and `is_stale` is always `false`
  today. New `GET .../preparation-sources/{id}/issues` endpoint, scoped
  to the selected worksheet the same way `GET .../rows` already is.
  Frontend: a "Preparation Status" panel showing severity counts and a
  grouped Blocking/Warning/Info list (see the UX-refinement paragraph
  below for its own current, collapsed-by-default presentation),
  refetched alongside every preview load (which already covers "refetch
  after every mutation" for free). Recording Events status stays `Needs
  Preparation` throughout — no `Ready`/`Preparation Error` status, no
  "Open in Powerwave" action, and no readiness gate exist anywhere in
  this slice.

  **Post-Slice-6 UX refinement** (owner UAT, 2026-08-31, presentation
  only — no preparation architecture/API/issue-semantics change):
  both the Preparation Status and Structure panels now default to a
  **compact summary**, expanded only on request (progressive
  disclosure), per owner feedback that the fully-expanded default
  layout felt overwhelming. Preparation Status shows its counts line
  plus a "View Issues"/"Hide Issues" toggle — the detailed
  Blocking/Warning/Info list is collapsed until requested (a
  `blocking_count > 0` lead-in text, "Needs Attention — ...", is
  wired into the same counts line as a presentation-only shell for a
  future readiness state; Slice 6 itself never produces a `blocking`
  issue, so this branch is currently unreachable in practice). Structure
  shows a compact `Header: … / Data range: … / Columns: …` summary line
  with a single "Configure"/"Hide" toggle; the header/data-region inputs
  and the full column-role mapping table only render inside that
  toggled section. Both expand/collapse flags are frontend-only,
  session-scoped state (`wwDataPrep.issuesExpanded`/
  `structureExpanded`), reset to collapsed every time the Data
  Preparation Workspace is (re)opened — never persisted, never sent to
  the backend. Every existing interaction (row-level "Set as Header,"
  the column-role `<select>`s, Set/Reset Region, Undo/Redo, Reset All,
  issue-driven worksheet navigation) is unchanged; only its default
  visibility changed.

  **Data-region end-selection UX refinement** (owner UAT, 2026-09-01):
  `DataRegion` gains `end_mode` (`source_end`/`specific`, defaulting to
  `specific` so every pre-refinement call/request shape keeps working
  unchanged) — `end_mode="source_end"` lets the region's own upper
  bound float with the source/worksheet's own end instead of requiring
  a manually-found numeric row; `end_row` stays `None` for that mode
  (never a resolved/guessed value). Still ONE dataset-wide boundary per
  worksheet/source — no per-column end, verified directly against a
  source whose columns end on different rows. A new "Go to Last Rows"
  frontend action is pure navigation (reuses the existing paged-preview
  fetch and the existing `total_row_count`) — it never touches the
  region, the working overlay, or the revision counter. The Structure
  summary's "Data range" line now reads "Rows N–end" for a floating
  boundary, "Rows N–M" for a specific one. An optional per-column
  "last populated row" diagnostic from this same refinement's own scope
  was evaluated and deferred (would need a new, more expensive scan
  than anything already cached/established for either format — see
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md §18](CSV_EXCEL_INGESTION_ARCHITECTURE.md),
  open item 10). Note: commit `db72885` ("fix: resize the font-size")
  unintentionally contains both the owner's own CSS change and the
  completed `app/domain/working_overlay.py` portion of this refinement
  — a commit-history attribution/message mismatch only, not a code
  defect; left as-is per explicit owner direction.

  **Slice 7** (2026-09-01) implements the extensible time-axis
  interpretation FRAMEWORK from
  [CSV_EXCEL_TIME_INTERPRETATION.md](CSV_EXCEL_TIME_INTERPRETATION.md) —
  deliberately zero real datetime/elapsed/sample-index parsing, zero
  reconstruction/confidence-calculation logic, zero readiness gating
  (all Slice 8+). New `app/domain/time_axis.py`: five open-ended
  semantic families (`absolute`/`elapsed`/`sample_index`/`partial`/
  `unknown`), a four-state (not five — "inferred" was deliberately
  excluded) provenance model, a seven-state status model, and a
  `TimeAxisDiagnostic` model kept SEPARATE from `PreparationIssue`
  (never counted into `PreparationIssueSummary`). `TimeAxisConfiguration`
  is stored per-worksheet/source in a new `WorkingOverlay.time_axis`
  dict — the same sparse/frozen-replace pattern as `header_row`/
  `data_region`/`column_roles`, sharing the same bounded undo/redo
  history and revision counter. A configuration may only reference
  columns currently carrying the `time_axis` column role; if that role
  changes later, the stored configuration is left untouched but reported
  as `unsupported` on every live read (no auto-clearing). A small,
  explicit interpreter registry (`app/services/time_axis_service.py`)
  holds exactly two non-parsing interpreters — `manual` (stores whatever
  the user states) and `unsupported` (the universal fallback) — with
  Slice 8 adding real interpreters to the same registry later. New
  endpoints: `GET .../time-axis`, `PUT`/`DELETE .../working/time-axis`,
  `GET .../time-axis/interpreters`. Frontend: a compact,
  progressive-disclosure "Time Axis" panel consuming (never duplicating)
  the Structure panel's own column-role state, supporting multiple Time
  Axis columns. `time_grouping.py` and `DisturbanceRecord` were not
  touched. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 7](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 8A** (2026-09-01) implements the first two of Slice 8's five
  proposed initial interpreters — single-column absolute datetime and
  Date + Time — as REAL, deterministic (non-fuzzy) interpreters
  registered as `absolute_datetime`/`split_date_time` in
  `app/services/time_axis_interpreters.py`, on top of the Slice 7
  framework with zero framework-shape changes beyond what it already
  anticipated. A small, explicit `datetime.strptime` pattern table per
  date order (`dmy`/`mdy`/`ymd`) plus `datetime.fromisoformat`'s own
  ISO-8601 fast path — no fuzzy/`dateutil` parsing. Date-order ambiguity
  is resolved BY ELIMINATION first (`strptime` already rejects an
  invalid calendar date, so a day value over 12 alone makes
  `31/08/2026` unambiguous) and only genuinely 2-or-more-order-valid
  input produces an `ambiguous_date_order` diagnostic and the new
  `review_required` status (Slice 7's own reserved-but-unreachable
  status is now real) — `confirmed=true` is rejected server-side while
  that diagnostic remains. A bare time-of-day column is reported
  `family=partial`, never silently promoted to `absolute`. A new,
  bounded (50-row) sample-fetch reuses the existing paged-preview
  mechanism verbatim; a new `POST .../working/time-axis/interpret`
  dry-run action returns a bounded (20-row) {original, interpreted}
  preview without storing anything. Frontend: the Time Axis panel
  gained an "Interpreter" selector switching between Manual's plain
  fields and a Detect → review ambiguity → preview → Confirm flow. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **`[UAT FIX, 2026-09-04]`** a real owner-reported source
  (`3/6/26`+`18:04:00.000`, Date + Time) previously fell all the way to
  a generic "could not be parsed" failure — root cause: the date-order
  pattern table had NO 2-digit-year (`%y`) candidate at all, only
  4-digit-year, so `strptime` genuinely rejected every candidate before
  ever reaching the ambiguity-by-elimination logic above. Fixed:
  `dmy`/`mdy` (not `ymd` — no reported example uses a year-first
  2-digit shape) gained `%y` candidates, with an explicit century rule
  (`00-69 -> 2000-2069`, `70-99 -> 1970-1999`) applied as one documented
  post-hoc correction to Python's own native `%y` inference (which
  differs by exactly one value, `69`). `3/6/26` now correctly reaches
  the EXISTING `ambiguous_date_order`/`review_required` mechanism above
  — zero new ambiguity system. Diagnostic wording was also sharpened:
  a viable-but-undecided reading now says "Date format needs
  confirmation... Choose the intended date order below" (never the
  generic failure wording), and a genuinely unsupported reading now
  names up to 5 concrete failing `(row_number, value)` examples in its
  own `details`, rendered by the existing Time Axis diagnostics list.
  See `docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md`'s own
  Slice 8A section for the full account.

  **`[UAT FIX, 2026-09-04]`** a second same-day fix: the generic "☐
  Confirmed" checkbox previously appeared under EVERY sample-
  interpreter result, including a plain native reading with nothing
  actually uncertain about it. Investigation (before any code change)
  found `app.domain.time_axis.resolve_status()` already implements the
  desired policy end to end: `provenance == "reconstructed"` (Slice
  8C's own repeated-timestamp suggestion) is the ONLY route to
  `review_required` that function gates on `confirmed` — native
  readings, ambiguities resolved by an explicit date-order/unit choice,
  and direct user-entered interval/rate all ALREADY reach
  `is_ready=True` with `confirmed=False`, verified directly against
  live `set_time_axis_configuration()`/`build_issue_summary()` calls,
  not assumed. Zero backend code changed. Frontend gained one
  centralized rule, `wwDataPrepTimeAxisRequiresExplicitConfirmation()`,
  mirroring that same single condition — the confirmation control now
  appears ONLY for a reconstructed suggestion, labelled "I confirm this
  reconstructed timing" (never the generic word "Confirmed"); every
  other case shows `[Save]` alone. The Manual interpreter (a separate,
  lower-level path, out of this fix's scope) keeps its own original
  always-shown generic checkbox unchanged. See
  `docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md`'s own Slice 8A
  section for the full investigation/fix account and
  `backend/tests/test_time_axis_service.py::TestConfirmationPolicy` for
  the regression coverage locking in the (unchanged) backend policy.

  **Slice 8B** (2026-09-02) implements the next two of Slice 8's five
  proposed initial interpreters — elapsed numeric time and sample
  index — as `elapsed_numeric`/`sample_index` in the SAME
  `app/services/time_axis_interpreters.py`, reusing Slice 8A's own
  interpreter contract unchanged (two new optional `detect()`
  parameters, `requested_unit`/`requested_interval_seconds`, ignored by
  the two Slice 8A interpreters). Neither needed a new stored field:
  `TimeAxisConfiguration.unit`/`.interval_seconds` already existed
  since Slice 7 anticipating exactly this. `elapsed_numeric` requires
  an explicit unit (`seconds`/`milliseconds`/`microseconds`/
  `nanoseconds`, plus `minutes`/`hours`/`days`/`weeks` since DEC-081 —
  fixed, deterministic multipliers only; calendar-variable `months`/
  `years` remain unsupported, deliberately) — an absent unit produces a `missing_elapsed_unit`
  diagnostic reusing Slice 8A's own ambiguity→`review_required`
  mechanism verbatim; `confirmed=true` is rejected while it remains.
  `sample_index` treats an absent `interval_seconds` as
  `provenance=index_only`, a COMPLETE non-error state reusing Slice 7's
  own pre-existing `STATUS_INDEX_FALLBACK` precedent (already forced by
  that exact family/provenance combination before any real interpreter
  existed to produce it) — a present, positive `interval_seconds`
  (user-supplied rate or interval, converted to seconds-per-sample
  CLIENT-SIDE — never a second stored representation) is
  `provenance=user_specified` instead. Both interpreters detect
  backward/repeated/gap/non-numeric/missing findings by comparing each
  sampled value only to the previous one, in original row order —
  never sorting, dropping, or synthesizing a row. Frontend: the
  Interpreter selector gained "Elapsed Time"/"Sample Index" entries;
  Elapsed Time shows a required Unit select, Sample Index shows a
  progressive-disclosure Timing radio group (Unknown / Sampling rate Hz
  / Sample interval ms). See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 8C** (2026-09-02) implements the fifth and final Slice 8
  proposed initial interpreter — repeated-timestamp/precision-loss
  detection and user-approved reconstruction — as
  `repeated_timestamp_precision_loss` in the SAME
  `app/services/time_axis_interpreters.py`, reusing Slice 8A/8B's own
  interpreter contract unchanged. Powerwave may detect, analyse,
  suggest, and preview a reconstructed timing — it never silently
  applies one. Consecutive rows sharing an identical native timestamp
  (in original row order, over the same bounded sample) form a bucket;
  first/last buckets never penalize confidence since they may be
  sample-window-truncated. Confidence is qualitative only (High/Medium/
  Low): High requires ≥2 equal-sized interior buckets, Medium covers too
  few interior buckets to compare (but consistent) or a spread of ≤1,
  Low covers everything else. An accepted suggestion is
  `provenance=reconstructed` and always discloses its anchor assumption
  (first sample aligned to the displayed timestamp, by default) via a
  new `anchor_offset_seconds` option — no new stored field was needed
  otherwise (`unit`/`interval_seconds`/`options` already existed since
  Slice 7). A NEW `resolve_status()` rule routes an unconfirmed
  reconstruction to `review_required` WITHOUT blocking confirmation
  (deliberately separate from the ambiguity mechanism Slice 8A built,
  which WOULD have blocked it forever); a genuinely unreliable cadence
  still uses that existing ambiguity mechanism and correctly blocks
  `confirmed=true`, deferring segmented/variable-cadence reconstruction
  rather than guessing. A manual interval/rate override is
  `provenance=user_specified`, never `reconstructed`; missing/extra-
  sample bucket-count anomalies are diagnostics only, never inserted/
  deleted rows; Sample Index remains the always-available, honest
  fallback. Frontend: the Interpreter selector gained "Repeated
  Timestamp (Precision Loss)"; the compact summary shows the suggested
  interval and anchor assumption in plain language, with a collapsed-
  by-default "Adjust" panel (Timing source radio + First sample offset
  ms) for a manual override. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  Slice 8's five proposed initial interpreters are now all implemented
  (8A/8B/8C).

  **Slice 8D** (2026-09-02) implements Time Irregularity Diagnostics — a
  DIAGNOSTIC-ONLY normalization layer over the irregular-timing
  conditions CSV_EXCEL_TIME_INTERPRETATION.md §11's own table already
  named, never a new interpreter and never readiness policy. The one
  real gap it fills: `absolute_datetime`/`split_date_time` (Slice 8A)
  never checked row-to-row timing quality at all — only
  `elapsed_numeric`/`sample_index` (8B) and `repeated_timestamp_
  precision_loss`'s own bucket cadence (8C) ever did. A new shared
  `_analyze_time_sequence()` fills that gap, called only once a resolved
  (non-ambiguous) reading already exists; for `split_date_time`
  specifically it walks the COMBINED per-row date+time value, never the
  date-only column's own sequence. Five genuinely new diagnostic codes
  (`time_goes_backward`, `large_time_gap`, `timestamp_reset_suspected`,
  `partial_midnight_rollover_suspected`, `non_uniform_interval`) — every
  other condition already had an established code from an earlier
  slice, reused verbatim. The reference "expected local interval" is the
  MINIMUM positive consecutive delta in the bounded sample (robust to a
  large outlier inflating its own comparison point); a transition at
  least 5x that reference is "large" in either direction; a `partial`-
  family transition from near the end of the day to near the start is
  checked FIRST and reported as a midnight rollover instead — never a
  fabricated date, never generic backward-time corruption. Exact repeats
  are deliberately never flagged here (Slice 8C's own interpreter owns
  that). All five new codes are `SEVERITY_WARNING`/`AMBIGUITY_UNAMBIGUOUS`
  (the same combination `elapsed_time_goes_backward` already uses) — no
  new `resolve_status()` rule was needed. A new `category` axis
  (`format`/`ordering`/`gap`/`repeat`/`sampling`/`ambiguity`) is a
  COMPUTED property on every `TimeAxisDiagnostic`, never a stored field,
  so zero existing diagnostic construction anywhere needed to change.
  No new API, no new endpoint. Frontend: the compact Time Axis summary
  gained one "Diagnostics" row ("2 findings," hidden when none) — the
  findings themselves stay inside the existing expanded-review list,
  never a new top-level panel. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 9** (2026-09-02) implements the Full Powerwave Readiness
  Validator — answers exactly one question, is the current prepared
  dataset ready to convert into Powerwave, using the SAME `blocking`/
  `warning`/`info` model Slice 6 already established (never a second,
  parallel readiness model). `app.services.readiness_service` extends
  `preparation_issue_service.build_issue_summary()` (the SAME `GET
  .../issues` endpoint, no new route) with real policy: no Time Axis
  configured/unsupported/unresolved, or zero Waveform Channel columns,
  is BLOCKING; a resolved time-axis reading's own diagnostics are
  promoted into `PreparationIssue`s through one explicit policy table
  (`_BLOCKING_TIME_DIAGNOSTIC_CODES`/`_WARNING_TIME_DIAGNOSTIC_CODES`) —
  interpreters themselves still encode no severity opinion at all.
  Sample Index fallback, an accepted reconstruction, manual/user-
  specified timing, and bare time-of-day (partial) readings are all
  WARNING, never blocking — each can reach `is_ready=True`. Two
  DELIBERATELY different validation scopes: time-axis diagnostics stay
  SAMPLE-based (whatever the interpreter's own bounded ≤50-row window
  already saw), but missing/invalid TIME-AXIS and WAVEFORM CHANNEL cell
  values are checked across the ENTIRE active data region via a new
  single-pass streaming generator,
  `preparation_preview_service.iterate_active_region_rows()` — never a
  second materialized copy of the dataset, never a bounded-sample
  guarantee mistaken for a full one. `ERR`/`N/A`/`#VALUE!`/malformed
  numeric text in a Waveform Channel cell is preserved and reported,
  never coerced to zero. Digital-channel validation is explicitly
  deferred (no dedicated column role exists yet). Nothing here ever
  deletes, sorts, or reorders a row, or synthesizes/interpolates a
  value — readiness only ever reports; the engineer resolves. New
  `PreparationIssueSummary.is_ready` field (`blocking_count == 0`).
  Frontend: the EXISTING Preparation Status panel (which already had a
  Slice-6-era "shell for a future Needs Attention state" comment) now
  shows a real "Needs Attention"/"Ready for Powerwave" headline, with
  deliberately NO "Continue to Powerwave" button (canonical conversion
  is Slice 10, not this one) — detailed issues stay collapsed by
  default, unchanged. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 9](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 10** (2026-09-03) implements canonical `DisturbanceRecord`
  conversion — the third and final stage of "Slice 8 → interpret; Slice
  9 → validate; Slice 10 → convert." New
  `app/services/preparation_conversion_service.py`
  (`convert_preparation_source()`) re-runs readiness against the
  CURRENT working revision at conversion time (never trusts stale
  frontend state — the three owner-approved rules this slice opened
  with), builds the canonical time axis by reusing the SAME
  `TimeAxisInterpreter.build_preview_rows()` the Time Axis review UI
  already calls (over the full active region, never the bounded ≤50-row
  sample) — so conversion never re-implements or re-decides any
  per-family parsing/reconstruction logic Slice 8 already settled — then
  constructs a `DisturbanceRecord` and registers it into the SAME
  `WorkspaceRegistry`/`GET .../sources` a COMTRADE upload uses, with
  zero CSV/Excel-specific plotting page. Canonical time is always
  `raw[i] - raw[0]` (relative to the first active sample) for every
  convertible family; `sample_index` additionally requires a known
  `interval_seconds` — an index-only source with `interval_seconds is
  None` is REFUSED at conversion (`ConversionRequiresIntervalError`),
  not because Slice 9 marks it not-ready (it is still `is_ready=True`,
  Sample Index fallback is only a WARNING) but because converting an
  unscaled index into seconds would fabricate a sample-rate that was
  never confirmed. Canonical-model hardening (deliberately minimal, see
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md](CSV_EXCEL_INGESTION_ARCHITECTURE.md)
  for the full rationale): `TimingInformation.start_time`/`.trigger_time`
  widened from required `datetime` to `datetime | None` (an unknown
  absolute start or trigger is `None`, never a fabricated
  `2000-01-01`/`1970-01-01`/`trigger_time = start_time` sentinel) —
  discovered to be the ONLY required change, since `SourceMetadata`'s
  own `start_time`/`trigger_time` fields were already `Optional`
  (Phase 5B/DEC-048) and every downstream consumer
  (`time_grouping.derive_time_groups()`, `synchronization_service.py`,
  `calculated_channel_service.py`) already branches on `is None` —
  "existing waveform integration" needed zero changes. New
  `SamplingInformation.is_uniform` (defaults `True`, matching COMTRADE's
  existing behavior unchanged) flags genuinely irregular canonical
  timing honestly rather than claiming one fabricated average rate;
  ±1% relative tolerance (matching Slice 8B's own
  `non_uniform_elapsed_interval` precedent) decides uniform vs.
  irregular. `nominal_frequency` was deliberately NOT widened to
  Optional (unlike `start_time`/`trigger_time`) because
  `synchronization_service.py` consumes it as a required float for
  event-detection sensitivity — a converted source instead gets a
  documented conventional default (50 Hz) plus an explicit
  `nominal_frequency_assumed: true` provenance flag. Duplicate channel
  labels never lose a channel: first occurrence keeps its label
  verbatim, every later occurrence gets a `__<spreadsheet-column-letter>`
  suffix (e.g. `Voltage`, `Voltage__C`, `Voltage__D`), with the original
  label preserved as each channel's own `description`. Provenance
  (source format, filename, worksheet, preparation revision, time
  family/provenance, interpreter id, header row, data region, excluded
  row count, etc.) is retained in a new, purely additive
  `SourceMetadata.preparation_provenance` dict — no CSV/Excel-specific
  field added to any core waveform schema. Idempotency needed zero new
  code: a successful conversion removes the `PreparationSession` from
  its registry (mirroring COMTRADE's own upload flow, which never
  leaves a stale row behind either), so a repeated `POST .../convert`
  against the same source naturally 404s via the existing
  `SourceNotFoundError` path. New API: `POST
  .../preparation-sources/{source_id}/convert`, returning the SAME
  `SourceSummaryOut` shape a COMTRADE upload returns — never a bespoke
  response. Frontend: the Preparation Status panel now shows the actual
  "Continue to Powerwave" action when `is_ready` AND conversion-capable,
  or a "Ready with limitations" notice with a "Configure Time Axis"
  shortcut for the index-only-without-interval case (never a misleadingly
  enabled Continue button); on success the user is navigated into the
  EXISTING waveform workflow via `openRecordingForAnalysis()` — the same
  entry point a COMTRADE "Open / Analyse" row uses — never a
  CSV/Excel-specific plotting page; on failure the user stays in Data
  Preparation with every preparation control intact. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 10](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 11** (2026-09-03) implements existing-waveform-integration
  VERIFICATION — zero-new-feature bias: proves a Slice-10-converted
  CSV/Excel source behaves like any other Powerwave source across Time
  Groups, synchronization, and calculated channels, fixing production
  code ONLY where an integration defect was actually demonstrated (per
  this slice's own "observed failure → is conversion wrong? → is
  downstream code unnecessarily COMTRADE-specific? → minimally
  generalize" decision sequence). Verified via a new
  `tests/test_slice11_waveform_integration.py` (24 tests): converted-
  source waveform open/range-fetch/cursor-values; multiple converted
  sources (CSV+CSV, CSV+Excel) coexisting independently; COMTRADE +
  converted-CSV coexistence with COMTRADE completely unaffected;
  absolute+absolute Time Group overlap, absolute+elapsed staying
  separate, two elapsed sources each singleton, `partial`-family
  correctly `elapsed_only`; synchronization alignment views (including
  `trigger_time=None`) raising no exceptions; same-source and aligned
  cross-source calculated-channel Addition; cross-source rejection with
  zero resampling for both an elapsed-vs-absolute mismatch and a
  genuinely-different absolute-start mismatch; irregular-timing
  range-fetch preserving the true time array with no fabricated uniform
  rate; `preparation_provenance` surviving a `WorkspaceRegistry`
  round-trip; convert→open→remove→reopen lifecycle coherence with
  calculated-channel removal cascade; repeated-conversion idempotency
  re-confirmed at this layer; a 50,000-row source converting in well
  under a second with its display range-fetch still using the existing
  min/max-envelope reduction.

  **Two real production defects were found and fixed** (both in
  PRE-EXISTING code, not in Slice 10's own conversion logic, and both
  reproduced by a minimal script BEFORE any fix was written): `app.
  domain.time_grouping` and `app.services.calculated_channel_service`
  implicitly assumed every absolute source's `start_time` shared the
  same naive/timezone-aware status — true by construction while COMTRADE
  was the only absolute-time producer (`app.providers.comtrade` never
  attaches a timezone), false the moment a Slice-10-converted CSV/Excel
  source can honestly preserve a real declared timezone offset. (1) A
  genuine crash — `TypeError: can't compare offset-naive and
  offset-aware datetimes` — from `time_grouping.py`'s own interval-
  overlap comparison and placement-offset subtraction, reachable by any
  workspace mixing one naive absolute source (COMTRADE, or a
  timezone-unspecified CSV/Excel one) with one genuinely timezone-aware
  CSV/Excel absolute source; this would 500 `GET .../synchronization/
  time-groups` and every other Time-Group-aware endpoint. (2) A silent,
  SERVER-TIMEZONE-DEPENDENT correctness defect in `calculated_channel_
  service._source_start_epoch()`, which called the naive
  `datetime.timestamp()` directly (interpreting a naive value as the
  server's own local system timezone) — harmless while both compared
  sources were always naive COMTRADE (the arbitrary offset cancels out
  in the difference), but silently wrong and non-deterministic across
  deployment environments once one side is a genuinely timezone-aware
  converted source; this could have silently accepted a misaligned
  cross-source calculated channel or rejected an aligned one, depending
  purely on the backend server's own local timezone. Fix for both: one
  new pure function, `app.domain.time_grouping.normalize_absolute_
  datetime()` — an aware value's real declared offset is honored
  untouched; a naive value is labelled UTC without converting its
  wall-clock numbers, purely so it becomes comparable — applied at
  every point an absolute `start_time` enters comparison/arithmetic in
  both modules. For the previously-only-reachable all-naive (pure
  COMTRADE) case this is a verified no-op: every value gets the
  identical label, so every comparison/subtraction result is
  numerically unchanged. Regression coverage: `TestMixedTimezone
  AwarenessIntegration` in `tests/test_time_grouping_domain.py` and
  `TestMixedTimezoneAwarenessCrossSourceAlignment` in
  `tests/test_calculated_channel_service.py`.

  Zero new `if source_format == "CSV"/"Excel"` branches exist anywhere
  in `waveform_service.py`, `synchronization_service.py`,
  `time_grouping.py`, or `calculated_channel_service.py` (grepped
  directly). No resampling, interpolation, new synchronization
  algorithm, new calculated-channel operation, new Time Group policy,
  or new readiness policy was added. `preparation_provenance` remains a
  domain-layer-only (`SourceMetadata`) field, deliberately NOT exposed
  via `SourceSummaryOut` or any other waveform-facing schema this slice
  — a legitimate deferred item, not a defect (this slice's own task
  explicitly says downstream waveform services need not understand
  preparation internals). See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 11](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  **Slice 12** (2026-09-03) implements Cleaned Data Export; a
  2026-09-04 enhancement (DEC-074) then supersedes its own original
  export-time policy (below). Governing principle, unchanged: **"Cleaned
  export = the current Working Dataset as prepared by the engineer"** —
  not the raw source, not a silently repaired dataset. New
  `app/services/preparation_export_service.py`
  (`export_preparation_source()`) exports `active data region - excluded
  rows + working cell overrides`, restricted to Waveform columns plus
  ONE standardized configured Time column (see below) — Not Assigned
  columns are omitted (DEC-073; the manifest's own `omitted_columns`
  entries record each excluded column's `role`), preserving remaining
  Waveform source column order, into a cleaned CSV or single-worksheet
  XLSX bundled with a sidecar `<base>_cleaned.manifest.json` inside one
  `<base>_cleaned.zip`.

  **DEC-074 (2026-09-04): the exported Time column is now the
  RESOLVED/CONFIGURED Time Axis, not the original source Time Axis
  column(s) verbatim.** Originally (Slice 12) a Time Axis column
  exported its own current WORKING value byte-for-byte unchanged; this
  was superseded so a cleaned export becomes genuinely re-upload-
  friendly — an engineer who already resolved date-order ambiguity,
  supplied a sampling interval/rate, or accepted a reconstructed timing
  suggestion should not have to repeat that work on re-upload. The
  exported table is now exactly ONE standardized Time column, ALWAYS
  FIRST (a deliberate exception to "preserve source column order," which
  still governs the Waveform columns among themselves), built by
  re-calling the ALREADY-CONFIRMED interpreter's own `build_preview_
  rows()` — the exact same call Slice 10's own canonical conversion
  makes — over the full active region, through a NEW shared module,
  `app/services/time_axis_normalization.py` (`parse_native_time_value()`/
  `relative_seconds()`/`format_absolute_iso()`/`format_relative_
  seconds()`, extracted out of `preparation_conversion_service.py` as a
  pure refactor so the two features can never disagree about what a
  configured Time Axis means). A resolved `FAMILY_ABSOLUTE` reading
  exports one ISO-8601 timestamp per row (header `Time`; millisecond
  precision by default, widened only when genuine sub-millisecond
  precision exists; a real timezone offset preserved exactly, never
  invented). Every other resolved family (elapsed, sample-index-with-a-
  real-interval, partial, or an ACCEPTED reconstruction) exports fixed
  3-decimal seconds relative to the first active row (header
  `Time (s)`) — the same "relative to first" convention Slice 10's own
  `waveform_data["time"]` already uses. The original source Time Axis
  column(s) never appear in the cleaned table; their raw values remain
  fully intact in the immutable source and in `WorkingOverlay` itself,
  and the manifest's own new `exported_time` section (`column_name`,
  `source_columns` by index+label, `family`, `provenance`,
  `interpreter_id`, `date_order`, `interval_seconds`,
  `export_representation`, `timezone_present`, `source_offset_seconds`,
  `reconstructed`) records exactly which raw column(s) it was consumed
  from, for full traceability.

  **A usable, resolved Time Axis plus at least one Waveform column is
  now REQUIRED for a reusable cleaned export** (DEC-074) — a real
  behavior change from Slice 12's own original "available regardless of
  readiness" policy, since there is no honest standardized Time column
  to build from an unconfigured/unresolved/`manual`-interpreter Time
  Axis. `export_preparation_source()` now reuses `PreparationIssueSummary.
  is_ready` directly as its primary gate (every current `blocking`
  readiness issue is already exactly a Time-Axis or Waveform-Channel
  finding, so this is not a second, narrower readiness policy of its
  own), plus the SAME two additional capability constraints Slice 10's
  own canonical conversion already enforces: `manual`/`unsupported`
  interpreter (`ExportUnsupportedInterpreterError`) and `sample_index`
  with no real interval (`ExportRequiresIntervalError`) — both new
  `app/services/errors.py` classes, alongside `ExportNotReadyError` and
  the defensive `ExportTimeAxisValueError`, all mapped to `409`/`500`
  in `app/api/v1/preparation_sources.py` exactly like the existing
  `conversion_*` codes.

  Row/column selection and column-label fallback logic remain pure REUSE
  of Slice 9's `iterate_active_region_rows()` and `preview_preparation_
  source()`'s own already-computed labels; deduplicating Waveform column
  labels still uses the same `__{SpreadsheetLetter}` suffix strategy
  Slice 10 established. Manifest fields otherwise unchanged from Slice
  12: `manifest_version`, `exported_at`, `exported_file`,
  `source_format`, `original_filename`, `worksheet_name`/`worksheet_
  index`, `preparation_revision`, `header_row`, `data_region`,
  `exported_row_count`, `excluded_row_count`/`excluded_rows` (bounded to
  200 listed rows + a truncation flag)/`omitted_columns`/`column_roles`,
  `edited_cell_count`/`cleared_cell_count`, `time_family`/`time_
  provenance`/`interpreter_id`/`time_unit`/`time_interval_seconds`/
  `reconstructed_timing`, `exported_time` (new), and a live `readiness`
  snapshot (built ONLY when a manifest is actually requested — see
  DEC-076 immediately below). Excel export still writes one clean
  tabular worksheet via `openpyxl.Workbook(write_only=True)` (streaming,
  no original styling/formulas/charts/macros preserved) into a NEW
  workbook; CSV export still uses a normalized comma/UTF-8 dialect.
  Still read-only by construction — no `working_overlay` mutation
  function is ever called; `WorkingOverlay.revision` is still captured
  and re-verified around the export (`ExportRevisionChangedError`).
  API: `POST .../preparation-sources/{source_id}/export` — see DEC-076
  immediately below for its current `include_manifest` query parameter
  and default response shape (superseding this paragraph's original
  "always returns the ZIP bytes" description). Frontend: the "Export
  Cleaned Data" secondary action (same Preparation Status panel
  "Continue to Powerwave" lives in) is disabled-by-default with a short,
  single-line guidance message (`wwDataPrepRenderExportAction()`) until
  a resolved, usable Time Axis plus at least one Waveform column exists
  — mirroring "Continue to Powerwave"'s own limitation-notice pattern,
  never a large new warning panel; still triggers a real browser
  download via a throwaway `<a download>` element and never navigates
  away or mutates preparation state.

  **DEC-076 (2026-09-04): the manifest/provenance bundle is now
  OPTIONAL — the default "Export Cleaned Data" click downloads the
  cleaned CSV/XLSX directly, never a ZIP, never a forced sidecar
  `manifest.json`.** Owner-approved UX problem: an ordinary engineer
  only wants the reusable cleaned file and should never be handed a
  ZIP — let alone be expected to understand `manifest.json` — merely to
  get it. `app/services/preparation_export_service.export_preparation_
  source()` gains an explicit `mode` (`EXPORT_MODE_DATA_ONLY`, the new
  default, vs. `EXPORT_MODE_WITH_PROVENANCE`, the original Slice
  12/DEC-074 ZIP+manifest bundle, byte-for-byte unchanged); the API
  exposes the same choice as `POST .../export?include_manifest=true`
  (default `false`). Both modes share identical gating
  (`_ensure_exportable()`, unchanged from DEC-074) and identical
  cleaned-data construction, so they always produce byte-identical
  cleaned data for the same working-overlay revision — `mode` only
  changes the RETURN SHAPE. `EXPORT_MODE_DATA_ONLY` never builds or
  serializes the manifest at all (an efficiency requirement, not merely
  discarding a built manifest). Data-only responses carry the real
  `Content-Type` (`text/csv` or the XLSX spreadsheet MIME type) and a
  `<name>_cleaned.csv`/`.xlsx` filename; the existing
  `expose_headers=["Content-Disposition"]` CORS fix (below) already
  covers every response shape, no CORS change was needed. Frontend: the
  export action is now a split action — the primary "Export Cleaned
  Data" button (`wwDataPrepExport(false)`) is the data-only default; a
  new, visually secondary, underlined-text "Download with manifest
  (cleaned file + provenance)" button (`wwDataPrepExport(true)`,
  `#wwDataPrepExportWithProvenanceBtn`) performs the with-provenance
  export — both share the exact same gated enabled/disabled state
  (`wwDataPrepRenderExportAction()`), since provenance was never a
  separately-gated capability. The download-handling code no longer
  assumes every export is a ZIP (task's own "old frontend expected
  every export to be ZIP" regression note) — the real filename/
  extension always comes from the server's own `Content-Disposition`
  header regardless of mode. Manifest schema/contents are unchanged;
  provenance capability itself is not removed, only demoted from the
  default to an explicit opt-in. Verified: full backend suite 2731
  passed, 0 failed (the same baseline DEC-075 already established,
  confirming no regression from either same-day enhancement); the
  committed browser smoke test (COMTRADE) still passes unchanged; a
  throwaway (not committed) live-browser Playwright UAT confirmed both
  a CSV and an Excel source's default export downloads the cleaned file
  directly (not a ZIP, correct `Content-Type`, correct source-derived
  filename), "Download with manifest" downloads a real ZIP containing
  both the cleaned file and `manifest.json`, and the two exports'
  cleaned data is byte-identical — all with zero console/page errors.

  **One real defect found and fixed by the browser UAT, invisible to
  every backend-only test**: `Content-Disposition` is not a CORS-
  safelisted response header a browser exposes to JavaScript by
  default. Without an explicit `expose_headers=["Content-Disposition"]`
  on the existing `CORSMiddleware` config (`app/main.py`), the
  frontend's cross-origin download `fetch()` could read the ZIP body
  but not the real filename, silently falling back to a generic
  `recording_cleaned.zip` name — invisible to a same-process
  `TestClient` call (which enforces no CORS at all), caught only by the
  live-browser UAT's genuinely cross-origin request. Fixed with one
  line; regression test added:
  `test_content_disposition_is_exposed_for_cross_origin_downloads` in
  `backend/tests/test_main.py`.

  Verified: full backend suite 2665 passed (52 new on top of Slice 11's
  own 2613: 43 export-service + 8 API + 1 CORS regression), zero
  regressions; the committed browser
  smoke test (COMTRADE) still passes unchanged; a throwaway (not
  committed) live-browser Playwright UAT confirmed export from both a
  not-ready and a Ready source with the correct filename, correct ZIP
  contents (cleaned CSV/XLSX + manifest with an accurate readiness
  snapshot), unchanged preparation state afterward, and "Continue to
  Powerwave" still working normally afterward — all with zero console/
  page errors. See
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md item 12](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
  for the full implementation summary.

  Progressive automation (Slice 13) is still explicitly NOT part of any
  slice implemented so far — see
  [CSV_EXCEL_INGESTION_ARCHITECTURE.md §14](CSV_EXCEL_INGESTION_ARCHITECTURE.md).

  **DEC-084 Data Preparation Slices 1-5 (2026-09-09) implement Explicit
  Null Resolution** on top of this same `WorkingOverlay` — a THIRD,
  distinct per-cell state (`OVERRIDE_KIND_NULL`) alongside a value
  override and a clear: an unresolved empty/invalid cell still stays
  `blocking` (Slice 9's own guardrail, unchanged), but an explicit
  user-marked null is a resolved, non-blocking state for an active
  Waveform/data cell — **Time Axis explicit null still blocks** (no
  valid x-coordinate for that row, DEC-084's own permanent asymmetry).
  Single-cell Mark as Null (`set_cell_null()`) and bulk Mark as Null
  (`bulk_set_cells_null()`, one grouped undo/redo entry covering every
  marked cell) both ride the SAME bounded Undo/Redo/Reset All history
  every other `WorkingOverlay` mutation already used — no second
  history. A new Data Issues persistent review panel plus a compact
  Data Quality summary (frontend) surface unresolved/explicit-null
  cells for browsing; `MAX_CELL_ISSUES = 2000` bounds only that BROWSE
  list's own response payload — bulk resolution always re-derives its
  eligible scope from a separate, uncapped, authoritative backend scan
  (`eligible_bulk_null_rows()`), never limited to whatever the browse
  list happened to have loaded. An explicit null survives cleaned
  CSV/Excel export as the target format's own literal `null`
  representation (never a blank/empty cell indistinguishable from
  "never looked at") and survives canonical conversion into a real
  waveform gap; the downstream min/max envelope display reduction,
  cursor-value, and annotation-anchor paths were all hardened to
  recover the true finite extrema around a gap (never silently
  resolving to the first NaN) and to report the gap itself as
  `null`/`None` rather than a raw NaN — the Time Axis itself stays
  strictly finite throughout every one of these paths (never
  null-eligible). See
  [DECISIONS.md — DEC-084](DECISIONS.md#dec-084--explicit-null-resolution-and-calculated-channel-missing-data-policy-unresolved-emptyinvalid-cells-remain-blocking-an-explicit-user-marked-null-becomes-a-distinct-resolved-state-for-waveformdata-columns-time-axis-stays-blocking-each-calculated-channel-independently-declares-its-own-null-handling-policy-never-inheriting-automatic-propagation-from-its-source)
  for the full approved policy and [HANDOFF.md](HANDOFF.md) for the
  five-commit chain. The Calculated Channels entry above covers the
  separate (later) calculated-channel side of the same decision.

  **DEC-084 Data Preparation missing-value Fill/Estimate slice
  (2026-09-10, `e60e830` backend + `4882ed9` frontend) extends the
  above from three single-cell resolution paths to four, plus a bulk
  algorithmic/constant-fill action.** Single-cell actions are now Mark
  as Null / Fill Manually / **Estimate Missing Value** / Set Column to
  Not Assigned (renamed from "Change Column Role"; column-level even
  when launched from one cell's issue, with an explicit whole-column
  confirmation naming the column). Group actions are Mark matching
  issues as Null / **Fill / Estimate Missing Values** / Set Column to
  Not Assigned — there is no separate "Bulk Fill Manually" action;
  same-value bulk filling is **Constant Value**, one method inside Fill
  / Estimate Missing Values, not a fifth top-level action. Two new
  `WorkingOverlay` override kinds (`OVERRIDE_KIND_ESTIMATED`,
  `OVERRIDE_KIND_CONSTANT_FILL`) extend the same tri-state model above
  to five states, riding the identical bounded Undo/Redo/Reset All
  history (one grouped entry per action, no second history). Algorithmic
  estimation reuses the SAME shared engine Calculated Channels already
  used (`app.domain.missing_data_estimation` — Hold Last Value / Nearest
  Value / Linear Interpolation / Local Mean, samples-only max gap;
  PCHIP recognized but rejected, no SciPy) and is gap-based: a
  contiguous non-finite run (e.g. `blank / invalid / blank`) is one
  mathematical unit regardless of whether members are individually
  classified `waveform_value_missing` or `waveform_value_invalid` —
  selecting or scoping from one member/issue-type resolves the whole
  eligible gap, and the UI shows both the originally-requested
  `matching_count` and the true gap-expanded `affected_count`
  transparently whenever they differ (never silent scope expansion).
  **Constant Value is not interpolation** and stays strictly scoped to
  the requested issue type — it never expands across the rest of a
  mixed gap the way algorithmic estimation does. Every preview/apply
  count is backend-authoritative (`preview_estimate`/`apply_estimate`/
  `preview_bulk_constant_fill`/`apply_bulk_constant_fill` in
  `working_overlay_service.py`, six new
  `.../working/cells/...` API routes), never derived from the capped
  Data Issues browse list; apply re-evaluates eligibility fresh and
  reports any preview-vs-apply drift transparently. Time Axis issues
  (`time_value_missing`/`time_value_invalid`) are structurally
  ineligible for both new actions — the frontend reuses the same
  waveform-only eligibility gate the existing Mark-as-Null guardrail
  already relied on. Estimated and constant-filled cells are resolved/
  non-blocking, export as their concrete numeric value, and convert
  downstream as ordinary finite samples; the Raw Data Preview marks
  them with distinct "Estimated"/"Filled" badges (never color alone,
  Constant Value never labelled "Estimated"). See
  [DECISIONS.md — DEC-084](DECISIONS.md#dec-084--explicit-null-resolution-and-calculated-channel-missing-data-policy-unresolved-emptyinvalid-cells-remain-blocking-an-explicit-user-marked-null-becomes-a-distinct-resolved-state-for-waveformdata-columns-time-axis-stays-blocking-each-calculated-channel-independently-declares-its-own-null-handling-policy-never-inheriting-automatic-propagation-from-its-source)
  for the full policy-level update and [HANDOFF.md](HANDOFF.md) for the
  commit chain.

## Known intentional constraints / deferred items

These are product decisions or explicitly out-of-scope items, **not**
correctness defects:

- Cross-Time-Group synchronization, cross-Time-Group cursor comparison,
  and a shared cross-Time-Group t0 — deliberately not built; each Time
  Group is an intentional isolation boundary, not merely an unfinished one.
- Detect Event's UI entry point stays hidden (`WW_DETECT_EVENT_UI_ENABLED
  = false`) even though the underlying feature is fully implemented and
  group-aware.
- Time Group collapse (a UI affordance to collapse/hide a group's canvas)
  has never been built — every active canvas stays expanded.
- Direct vertical drag/reorder of panels and drag-to-overlay/group by
  direct lane dragging — still fully unimplemented and undecided
  (`[PROPOSAL]`/`[NEEDS UAT]`, not `[DECISION]`).
- Real Table/Split view and CSV/Excel parsing/normalization — not yet
  implemented (see [Current next workstream](#current-next-workstream)).
- Advanced Per-Unit group move/split/merge UI, CT/VT scaling as a PU base,
  and DEC-049's eventual retirement — each needs its own separate,
  explicit owner-approved implementation prompt; none is authorized yet.
- CSV/Excel absolute time-of-day parsing (DEC-081): bare 24-hour
  hour-only (e.g. `"2026-06-03 17"`), and absolute date-only/day-only/
  week-only/month-only/year-only readings — each remains explicitly
  unsupported, needing its own future design/policy decision, not a
  correctness gap in the minute-resolution/AM-PM-hour support DEC-081
  added. Elapsed `months`/`years` are structurally excluded (no
  fixed-seconds factor exists for a calendar-variable unit without an
  anchor date), not merely deferred. The pre-existing ISO-8601
  reduced-precision fast-path gap (`datetime.fromisoformat()` silently
  accepting date-only/week-only ISO strings with no diagnostic) also
  remains open, unaffected by DEC-081.
- **DEC-084 (Explicit Null Resolution and Calculated-Channel
  Missing-Data Policy) — IMPLEMENTED BASELINE (2026-09-10)**, across
  Data Preparation Slices 1-5, the Data Preparation missing-value
  Fill/Estimate slice, and Calculated Channel Slices 1-4; see
  [Implemented capabilities](#implemented-capabilities) for the full
  behavioral record and [HANDOFF.md](HANDOFF.md) for the commit chain.
  The following EXTENSIONS remain intentionally deferred, not yet
  approved to begin:
  - PCHIP interpolation — recognized as a valid `estimation_method`
    wire value for forward compatibility in both Calculated Channels
    and Data Preparation, but creation/estimation with it is rejected
    outright (`estimation_method_not_implemented`); no SciPy dependency
    exists in this codebase, and it is never offered in either frontend.
  - `max_gap_unit` values other than `samples` (milliseconds/seconds),
    for both Calculated Channels and Data Preparation.
  - Time Axis interpolation — algorithmic estimation only ever fills a
    Waveform/data cell using the Time Axis's own already-resolved
    values; there is no mechanism to estimate a missing/invalid Time
    Axis value itself (DEC-084 point 4's original "no Time-Axis-null
    workaround is defined by this decision," unchanged).
  - A per-sample provenance EXPORT format — Data Preparation's own
    `WorkingOverlay` DOES track which method estimated a given cell
    (`CellOverride.estimation_method`, surfaced through the preview
    API's `is_estimated`/`estimation_method` fields and the Raw Data
    Preview's own badge), but cleaned export/conversion still carries
    only the resolved numeric value, never an annotation of which cells
    were estimated or by which method. Calculated channels track only
    channel-level policy/method/max-gap/radius metadata, no per-sample
    record at all.
  - A cross-channel provenance graph (e.g. "did Calc B's result depend
    on an estimated sample in upstream Calc A").
  - Calculated-channel export.
  - Edit/update of an existing calculated channel — still immutable
    after creation (DEC-047); changing policy means creating a new
    channel.
  See [DECISIONS.md — DEC-084](DECISIONS.md#dec-084--explicit-null-resolution-and-calculated-channel-missing-data-policy-unresolved-emptyinvalid-cells-remain-blocking-an-explicit-user-marked-null-becomes-a-distinct-resolved-state-for-waveformdata-columns-time-axis-stays-blocking-each-calculated-channel-independently-declares-its-own-null-handling-policy-never-inheriting-automatic-propagation-from-its-source)
  for the full approved policy (unchanged by this implementation —
  implementation completing does not itself alter what was decided).

Genuinely open engineering/operational items (not yet resolved either
way):

- No automatic TTL/expiry for an abandoned workspace — `WorkspaceRegistry`
  entries (now including full-resolution waveform data, DEC-019) live in
  memory until the backend process restarts. `[DECISION MODE: COMPARISON]`.
- The ~100 MB real-COMTRADE-file memory ceiling has not been directly
  measured (only extrapolated from smaller synthetic benchmarks).
- A genuinely disk-free (zero temp-file-touch) upload/parse path remains
  unimplemented — judged disproportionate so far against "don't rewrite
  proven engineering logic."
- The long-term persistence architecture (for whatever eventually needs to
  survive a session — not event files, which stay permanently ephemeral
  per DEC-015) remains undecided, deferred to a later phase.

## Current next workstream

**CSV/Excel ingestion and normalization** is the current area of work,
per owner direction, now in progress following the owner-revised 13-slice
sequence recorded in
[CSV_EXCEL_INGESTION_ARCHITECTURE.md §14](CSV_EXCEL_INGESTION_ARCHITECTURE.md)
(itself grounded in [DECISIONS.md — DEC-072](DECISIONS.md#dec-072--csv-excel-ingestion-six-architectural-clarifications-approved--temporary-preparation-state-retention-preparation-scoped-severity-model-hybrid-rawworking-overlay-architecture-deferred-disturbancerecord-hardening-honest-non-absolute-time-preservation-and-an-open-ended-time-axis-format-list)).
**Slices 1-6 (Preparation-session foundation + raw CSV ingestion; Excel
ingestion + worksheet discovery; paged raw-data preview + Data
Preparation Workspace shell; Working Dataset / non-destructive overlay;
Header/Data Region + Column Role Mapping; Preparation Readiness Issue
model) are implemented (2026-08-31)**
— see [Implemented capabilities](#implemented-capabilities) below for
exactly what that covers. All six deliberately produce **no
`DisturbanceRecord` and no waveform**: a CSV or Excel file is accepted
as raw, immutable input into a new `PreparationSession` (in-memory,
`app.services.preparation_session_registry`) and surfaced in Recording
Events with status `Needs Preparation` — structurally excluded from
`GET .../sources` so it can never reach the Workspace Sidebar's
channel-selection list or normal waveform loading. Excel additionally
gets worksheet structure discovered (name/order/visible/best-effort
row-column counts) and a selectable current worksheet. Slice 3 adds a
dedicated Data Preparation Workspace page where the user can page
through the rows of a CSV or the currently selected Excel worksheet —
server-paginated (≤1000 rows/request), no header-row assumption, no
column-role/time-axis interpretation. Slice 4 layers a sparse,
non-destructive Working Dataset overlay on top (cell edit/clear/reset,
row exclude/include, Reset All, undo/redo; originally also a separate
column ignore/unignore toggle, retired by the 2026-09-04 UAT fix
below), merged into that same preview at read time only — raw bytes are
never mutated, and the overlay never duplicates the dataset. Slice 5
extends that same overlay with manual header-row selection, data-region
narrowing, and column semantic-role assignment — originally six roles
(`unknown`/`waveform`/`time_axis`/`metadata`/`quality_status`/`ignore`),
simplified by a 2026-09-04 UAT fix
([DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export))
to exactly three: `not_assigned` (the sparse default), `time_axis`,
`waveform` — still no time-axis FORMAT interpretation, still no
automatic classification of anything. Slice 6 adds the Readiness Issue
LANGUAGE AND TRANSPORT model (`blocking`/`warning`/`info` severities,
two conservative `info`-only issue codes derived live from configuration
state — originally three, until the same 2026-09-04 fix retired the
third, `column_roles_unassigned`, once `not_assigned` became a normal,
intentional final state) — explicitly NOT the full Readiness Validator,
no readiness gate, no status transition.
Slice 7 (the extensible time-axis interpretation FRAMEWORK), Slice 8A
(the first two deterministic time-axis interpreters), Slice 8B (the
next two -- elapsed numeric time, sample index), Slice 8C (the fifth
and final one -- repeated-timestamp/precision-loss detection and
reconstruction), Slice 8D (Time Irregularity Diagnostics -- a
diagnostic-only normalization layer over Slices 8A-8C's own irregular-
timing conditions, never a new interpreter, never readiness policy),
Slice 9 (the Full Powerwave Readiness Validator -- the REAL
`blocking`/`warning`/`info` policy Slice 6 always deferred, see above),
Slice 10 (canonical `DisturbanceRecord` conversion), Slice 11
(existing-waveform-integration verification, including two real
timezone-awareness defects found and fixed), and Slice 12 (Cleaned Data
Export, including one real CORS defect found and fixed -- see above for
the full summaries) are now implemented. Slice 13 (progressive
automation) remains unimplemented and requires its own explicit owner
go-ahead before starting, per
[Change governance](../../CLAUDE.md#change-governance) — being recorded
in the architecture document's own slice sequence does not itself
authorize starting any of them.

**`[DESIGN COMPLETE, 2026-09-01]`**: the Slice 7/8
design specification —
[CSV_EXCEL_TIME_INTERPRETATION.md](CSV_EXCEL_TIME_INTERPRETATION.md) —
settles semantic time families (absolute/elapsed/
sample_index/partial/unknown), a four-state provenance model (native/
reconstructed/user_specified/index_only), the owner-approved
detect→suggest→confirm fallback hierarchy (never discarding samples for
repeated timestamps, never fabricating an absolute anchor per DEC-072
point 5), a qualitative confidence model, the interpreter-registry
extensibility concept, and a progressive-disclosure Time Axis UI shell
matching the existing Preparation Status/Structure pattern. Slice 7 (the
framework portion) is now implemented, per above; Slice 8A (§19 items
1-2, the two deterministic absolute-time interpreters), Slice 8B (§19
items 3-4, elapsed numeric time + sample index), and Slice 8C (§19
item 5, repeated-timestamp/precision-loss detection and reconstruction)
are also now implemented -- §19's full five-interpreter set is
complete; segmented/variable-cadence reconstruction remains explicitly
deferred, per Slice 8C's own scope note above.
`SourceMetadata.timing_reference` reserving a value other than
`"absolute"` for an importer with no trustworthy absolute recording
timestamp is no longer merely reserved — Slice 10's conversion service
is the first real producer of `"relative_elapsed"` (or `None`
`start_time`), for every non-absolute-family CSV/Excel source (see the
Slice 10 summary above).

## Repository identity

`[FACT]`, verified 2026-08-14 via `git remote -v` in each local clone:

- `oruxa_powerwave` (this repo): `git@github.com:myza81/oruxa-powerwave.git`
  (SSH), branch `main`.
- `powerwave` (reference desktop app, macOS clone at
  `/Volumes/externalDrive/code-gym/powerwave/`): `https://github.com/myza81/powerwave.git`
  (HTTPS), branch `main`, at commit `3156392`.

These are two distinct GitHub repositories. See
[README.md — Repository identity](README.md#repository-identity--do-not-confuse-the-two-projects)
for the full rule against confusing them.

## Known infrastructure

`[FACT]`:

- DEV: `https://dev.powerwave.oruxa.uk` (frontend), `https://api.dev.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave-dev`, ports 8200/8201.
  Auto-deploys after CI succeeds on `main` (DEC-036) — this is where the
  live application, including all work described above, actually runs.
- PROD: `https://powerwave.oruxa.uk` (frontend), `https://api.powerwave.oruxa.uk`
  (API), VPS checkout `/srv/oruxa/apps/powerwave`, ports 8100/8101. Deployed
  only via manual `workflow_dispatch`, deliberately kept behind DEV.
- See [docs/development/development-workflow.md](../development/development-workflow.md)
  for the full deployment workflow.
