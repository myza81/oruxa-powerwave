# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-22**

## What was most recently done

**Phase 5C — Global Per-Unit Measurement Mode (DEC-049).** Owner-approved
direction: a global Waveform-page presentation mode, Engineering Units
vs. Per Unit, for Voltage/Current channels, backed by workspace-scoped
base profiles (Vbase/Ibase/three-phase Sbase). Full detail:
[DECISIONS.md — DEC-049](DECISIONS.md#dec-049--global-per-unit-measurement-mode-workspace-scoped-base-profiles-backend-only-conversion-explicit-reassignment-and-two-axis-modeprofile-calculated-channel-inheritance-provenance),
[MIGRATION_PLAN.md — Phase 5C](MIGRATION_PLAN.md#phase-5c--global-per-unit-measurement-mode-2026-08-22).

**Plan review took three owner correction rounds before any code was
written** — each caught a genuine design gap, not a nitpick: (1) an
unguarded profile-reassignment path and an ambiguous voltage-basis
treatment risking an unwanted automatic √3 factor; (2) a calculated-
channel inheritance model that only snapshotted once at creation and
never revisited it, so `RMS(VA)` would silently go stale the moment `VA`
moved to a different profile; (3) the first fix for that used a single
`provenance` tag, which the owner identified as unable to distinguish
"never yet resolved" from "the user deliberately unassigned this" — the
one case that must never silently re-inherit. The final design uses two
independent axes, `{mode: "auto"|"manual", profile_id}`, verified
against the owner's own exact worked A→G sequence.

**Backend (Slices A-C)**: new `app/domain/per_unit.py` (pure conversion
math, including `Ibase = Sbase / (√3 × Vbase_LL)` and its
line-to-neutral normalization — √3 is used ONLY there, never on a
measured channel's own division), `app/services/per_unit_registry.py`
(`PerUnitRegistry` + the `recompute_inherited_per_unit_assignments()`
cascade), `app/services/per_unit_service.py`, `app/api/v1/per_unit.py`
(profile CRUD), 4 new error classes, and an optional `unit_mode`
parameter added to all 8 existing display/measurement endpoints (source
+ calculated-channel waveform/cursor-values/peak-values/annotation-
anchor) — one shared conversion function, never duplicated per endpoint.
A registry-level invariant (`assigned_channels` and the reverse index
can never diverge) is enforced by every mutation path and proven by
tests re-checking it after every step of the A→G sequence. 79 new
backend tests; 758 total, zero regressions.

**Frontend (Slices D-G, `frontend/index.html` only)**: `ww.unitMode`/
`ww.perUnitProfiles` state; a Unit Mode toolbar dropdown cloned from the
Annotate split-button pattern; a "Manage Per-Unit Bases" setup modal
cloned from the Custom Groups editor's working-copy-until-Apply shell
(with a disabled-checkbox + explicit "Move here" action implementing the
reassignment-confirmation flow); `unit_mode` wired into every one of the
8 fetch call sites plus the Calculated Channels preview; a per-unit-
status suffix in `wwPanelGroupKeyFor()`/`wwPanelLabelFor()` that keeps a
converted ("pu") channel and an unconverted ("base_required") channel of
the same type in separate panels, never mixed on one shared axis.
13 new static regression tests, plus direct Playwright verification
against a real running backend+frontend: profile creation + assignment,
conversion correctness, panel separation, byte-for-byte restoration on
switching back to Engineering, the full conflict/"Move here"/confirm/
reassign flow, and Start New Workspace resetting both `ww.unitMode` and
`ww.perUnitProfiles`. Zero console errors throughout.

**Known, honestly-flagged UI polish gaps** (engineering correctness —
the actual displayed/measured values — is unaffected by any of these;
see MIGRATION_PLAN.md's Phase 5C entry for the full list): the
reassignment confirm uses a native `window.confirm()` rather than a
styled dialog; the sidebar's own static channel-name "(unit)" label
doesn't relabel to "(pu)" on a mode switch (the actual A/B values ARE
correctly converted); a channel added to the display for the first time
while Per Unit is already active groups by plain type until the next
regroup event; the Calculated Channels preview doesn't yet carry the
same panel-separation suffix the main Waveform page has.

**Not yet done** (as of this section being written): commit/push, CI/
automatic DEV deployment verification — see the final report delivered
alongside this update for whether those have since completed.

## What was done in the prior session (Phase 5B-UAT-series — Parameter UI, Tooltip Positioning, Workspace Lifecycle Fix)

**Workspace Lifecycle UAT Fix — Start New Workspace does not fully
reset.** Owner UAT: after "Start New Workspace," the Calculated
Channels/RMS Signal Builder form still showed the previous session's
input/name/unit/eligibility, and the footer workspace id appeared not
to rotate. **Investigated empirically in a real browser before changing
anything** (per the task's own explicit "do not guess" / "prove each
one" requirement), using the exact reproduction steps given:

- **Workspace id rotation: could NOT reproduce as broken.**
  `resetToNewWorkspace()`'s existing DELETE-then-rotate-then-render-footer
  sequence, and `currentWorkspaceId()`'s always-fresh
  `localStorage.getItem()` read, both already work correctly -- proven
  directly (`before != after`, both the JS variable and the rendered
  footer text). No frontend/backend change was needed for this half of
  the report.
- **Calculated Channels registry / source inventory: also already
  correct.** `wwClearWorkspace({resetSourceBounds: true})` (called by
  Start New Workspace) already clears `ww.calculatedChannels` and
  `ww.sourceChannelInventory` and the backend's own
  `DELETE /api/v1/workspaces/{id}` already releases both its
  `WorkspaceRegistry` and `CalculatedChannelRegistry` entries (added new
  backend regression tests in `test_workspaces_api.py` proving this,
  since none previously existed for the calculated-channel side).
- **The actual, confirmed bug**: the Signal Builder's own TRANSIENT form
  state (`wwCcBuilder`/`wwCcRmsEligibility`) was never reset by Start New
  Workspace at all, even though `wwClearWorkspace()` already calls
  `wwRenderCalculatedChannelsPage()` right after clearing the registry --
  that re-render is driven BY `wwCcBuilder`'s own (never-invalidated)
  state, so it faithfully redrew the stale session (old input, old
  suggested name, old "From recording metadata"/"Input appears suitable"
  copy, Create button still enabled) pointing at a source that branch had
  just released server-side. Screenshotted directly, reproducing the
  owner's exact complaint.

**Fix**: one call, `wwCcResetBuilder()` (the SAME function already used
after every successful channel creation -- not a new one), plus
`wwCcListErrors.clear()`, added inside `wwClearWorkspace()`'s
`resetSourceBounds` branch only -- confirmed NOT added to the plain
"Clear Workspace" branch, preserving that operation's own established
display-only semantics (re-verified directly: Clear Workspace still
neither rotates the workspace id nor touches `ww.calculatedChannels`).
`wwCcResetBuilder()` already internally calls `wwCcResetRmsEligibility()`,
which bumps the async generation counter -- this was verified to also
correctly discard a genuinely in-flight RMS eligibility request from the
old workspace if its response lands after the reset (tested directly:
selected an input, reset before the debounce even fired, confirmed the
generation counter advanced and no stale eligibility state leaked into
the fresh session).

Pure frontend fix, one file (`frontend/index.html`), no backend change.
New tests: `test_frontend_workspace_reset_calculated_channels.py` (6
checks) plus 2 new backend tests in `test_workspaces_api.py` for
calculated-channel registry isolation on workspace delete. Full backend
and frontend suites re-run, zero regressions.

**Phase 5B UAT Fix — RMS Info Tooltip Positioning.** Owner UAT found the
new RMS info-tips (Nominal Frequency/Window/Method) rendering clipped/
partially hidden near the app's global header instead of cleanly above
the form. **Root cause, confirmed by direct browser measurement, not
guessed**: the tooltip bubble's original design (`position: absolute`
inline sibling of its trigger) was silently clipped by
`#pageCalculatedChannels`'s own `overflow: auto` whenever there wasn't
enough room above the trigger within that scroll container -- NOT a
z-index or stacking-context problem (verified directly: neither the
tooltip nor the main sidebar had any competing stacking context at all,
so a bigger z-index alone could never have fixed this). **Fix**: a
single shared, body-level tooltip node (`#wwInfoTipPortal`), positioned
via `position: fixed` with coordinates computed fresh from the
trigger's own `getBoundingClientRect()` on each show (below-right
preferred, falling back to above/clamped-horizontal only when genuinely
out of room) -- escapes every ancestor's overflow/scroll/transform by
construction, needing no exceptional z-index (uses `50`, one step above
this app's own previous highest fixed-layer z-index of `40`). Event
delegation on `document` (mouseover/mouseout/focusin/focusout) replaces
the old CSS-only `:hover`/`:focus-visible` + sibling-selector approach,
since RMS parameter fields are wholesale re-rendered on every input/
frequency change. Hover, keyboard focus, ARIA (`aria-label`/
`aria-describedby`/`role="tooltip"`), and Light/Dark theming all
re-verified directly in a real headless-Chromium session after the fix
(including re-running the exact scrolled reproduction that originally
caught the bug). Pure frontend fix, no backend file touched, no RMS
engineering semantics affected. 36/36 frontend regression checks pass
(6 new/updated for this fix); full backend suite unaffected.

**Phase 5B-UAT — Clarify RMS Parameter UI.** Owner UAT feedback on Phase
5B: the RMS parameter form's Nominal Frequency/Window/Method fields all
looked like similar text boxes, with no visual cue for parameter
authority (user-supplied vs. metadata-derived vs. automatically
calculated vs. fixed). Full detail:
[DECISIONS.md — DEC-048 Update note](DECISIONS.md#dec-048--rms-calculated-channels-use-a-trailing-one-cycle-true-rms-calculation-on-authoritative-full-resolution-samples-with-metadata-first-eligibility-and-backend-enforced-override),
[MIGRATION_PLAN.md — Phase 5B-UAT](MIGRATION_PLAN.md#phase-5b-uat--clarify-rms-parameter-ui-2026-08-22).

**Investigation finding, reported before any UI change** (the task's own
explicit requirement): `SourceMetadata.nominal_frequency` already exists
for every COMTRADE source (parsed from the CFG's own mandatory "lf"
line), and is already shown as an unhedged fact in the Recordings page's
own detail card -- but was never wired into the RMS builder, which just
hardcoded a `"50"` default. This directly contradicted an assumption in
the owner's own written task ("Later COMTRADE importer improvements can
populate a trusted value" implied it didn't exist yet). Confirmed with
the owner directly before proceeding, since this determined a materially
different resulting UI for essentially every real COMTRADE recording:
treat it as trustworthy, consistent with how the app already presents it
elsewhere.

**Changes, frontend only, no backend file touched**: Nominal Frequency
now renders as either a locked readonly display ("From recording
metadata") when the selected input's grounding source has a usable
value, or a constrained 50/60 Hz `<select>` (never free text, never a
hardcoded assumption) when it does not -- resolved fresh on every input
change, including through a calculated-channel input's own
`reference_source_id` (never guessed from `engineering_type`). Window
and Method stay read-only/fixed as before. A new small, keyboard-and-
mouse-accessible info-tip component (`wwInfoTipHtml()`) was added --
this codebase had no prior tooltip framework, and native `title` alone
doesn't reliably support keyboard-focus disclosure or Light/Dark custom
styling. Every read-only field in the panel (Unit included) now gets a
tinted background, not just dimmer text, so "automatic" fields are
visually obvious before interaction, not just on click/hover.

**Guardrails re-verified, not just assumed unaffected**: metadata-first
`waveform_form` eligibility, the detector fallback, RMS-of-RMS blocking,
and the override checkbox were all re-tested end-to-end in a real
headless-Chromium session (same Playwright-based approach as Phase 5B's
own verification) -- all confirmed unchanged. Also verified: the
"no trustworthy metadata" dropdown path (simulated, since no real
COMTRADE source can currently lack this field), 60 Hz selection
immediately updating the Window display, full create round trip, and
Light/Dark theming of the new tinted/tooltip styling. Zero console
errors throughout.

**Tests**: `test_frontend_rms_calculated_channel.py` gained 13 new
static source-text checks (one pre-existing test updated for the
retired free-text input id); full backend suite re-run and unaffected
(zero backend files touched this pass).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification -- see the final report
delivered alongside this update for whether those have since completed.

## What was done in the prior session (Phase 5B — RMS Calculated Channel)

**Phase 5B — RMS Calculated Channel.** Owner-approved direction: add
exactly one new Calculated Channels operation, RMS -- a guarded,
trailing one-cycle true-RMS derivation, extending DEC-047's Phase 5A
architecture with the one operation that phase explicitly deferred. No
prior chat/session context on this phase existed anywhere in project
memory -- this was implemented directly from the owner's own detailed
Phase 5B task specification. Full detail:
[DECISIONS.md — DEC-048](DECISIONS.md#dec-048--rms-calculated-channels-use-a-trailing-one-cycle-true-rms-calculation-on-authoritative-full-resolution-samples-with-metadata-first-eligibility-and-backend-enforced-override),
[MIGRATION_PLAN.md — Phase 5B](MIGRATION_PLAN.md#phase-5b--rms-calculated-channel-2026-08-22).

**Core design**: trailing one-cycle true RMS (`sqrt(mean(x^2))` over a
HALF-OPEN window `(t-window, t]`, `window = 1/nominal_frequency_hz`,
default 50 Hz) computed via a vectorized cumsum fast path for uniform
sampling or an O(N) two-pointer accumulator for irregular/multi-rate
spacing -- never a fixed sample count. The half-open boundary was
chosen only after direct numerical verification showed a closed
interval produces a spurious ripple for a steady sinusoid at an exact
sample-rate/cycle ratio (confirmed to shrink linearly with sample rate,
i.e. a genuine discretization artifact); the half-open definition is
bit-for-bit flat regardless of sample rate. `time`/`reference_source_id`
inheritance stays VERBATIM (same length output, leading NaN for the
warm-up region) -- this is what keeps every existing shared primitive
(`_nearest_sample_index`/`_peak_in_range`/`_clip_and_reduce`/
`timebases_aligned`'s same-reference fast path) working with zero code
changes and lets an RMS channel feed a further calculation with no
second timebase regime.

**Eligibility is metadata-first**: a new `waveform_form` taxonomy
(separate from `engineering_type`) on both source and calculated
channels; trusted `instantaneous`/`rms`/`magnitude` metadata is used
directly (no detector run) when present; `unknown` falls back to a new
lightweight numpy-only detector (`app.domain.rms_detector`, 5 cheap
indicators combined into a transparent vote, never a fabricated
confidence score). A non-`suitable` result requires an explicit,
backend-re-derived `override` -- the backend never trusts a
client-supplied eligibility result, closing off a real bypass path a
naive implementation could have left open. RMS is never gated by
`engineering_type` in either direction (a permanent regression test
proves both directions), keeping this compatible with a future
CSV/Excel importer.

**A genuine latent bug was found and fixed**: FastAPI's default JSON
response rejects raw NaN (`allow_nan=False`) -- every Phase 5A operation
happened to never trigger this; RMS's routine warm-up-region NaN is the
first to. Fixed by sanitizing NaN to `null` at the calculated-channels
serialization boundary only; source-channel code paths are untouched.

**No special RMS rendering pipeline was needed, confirmed by DIRECT
BROWSER VERIFICATION** (a real headless-Chromium session via Playwright
against the actual running backend+frontend, not just automated tests
-- installed for this pass, not yet a committed project dependency): an
RMS channel participates in every existing calculated-channel display/
measurement system (sidebar subgroup, Grouped panel, preview panel, A/B,
Peak, Callout, Absolute/Elapsed) unmodified. This same verification pass
found and fixed one more CSS `[hidden]`-cascade bug (the recurring bug
class this project keeps hitting) on the new override checkbox, and
also caught a false-alarm cosmetic Plotly autorange artifact on a
perfectly noiseless test signal (not a real defect -- resolved by
testing with a more realistic noisy signal instead of chasing it).

**Tests**: full backend pytest suite passes with zero regressions to
Phase 1-5A coverage; new coverage across `test_calculated_channel_domain.py`,
new `test_rms_detector.py`, `test_calculated_channel_service.py`,
`test_calculated_channel_api.py`, and new
`test_frontend_rms_calculated_channel.py` (17 static source-text
checks, the established no-browser-runner pattern for this single-file
frontend). One pre-existing Phase 5A test was updated (not deleted) to
reflect that `rms` is no longer a rejected operation name.

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and full owner UAT against
the checklist in MIGRATION_PLAN.md's own Phase 5B section (+Peak/-Peak
and Callout on an RMS channel were verified at the service-test level
and by architectural reuse, not by a direct browser click -- flagged
explicitly for the owner to confirm visually) -- see the final report
delivered alongside this update for whether those have since completed.

## What was done in the prior session (Phase 5A-UAT7 — Calculated Preview Dark Mode Fix)

**Phase 5A-UAT7 — Calculated Preview Dark Mode Fix.** Owner UAT bug:
the Calculated Channels page's new type-separated Waveform Preview
panels (Phase 5A-UAT6) rendered with a white/light Plotly paper and
plot area even while the surrounding Oruxa page was in Dark mode. No
new decision -- an "Update" note appended to DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT7](MIGRATION_PLAN.md#phase-5a-uat7--calculated-preview-dark-mode-fix-2026-08-21).

**Root cause, confirmed by direct trace, two related gaps**: (1) the
preview's own layout object never set `xaxis.gridcolor`/
`yaxis.gridcolor`/zeroline color at all -- Plotly does not auto-derive
axis/grid chrome from the background color. (2) `wwApplyTheme()` -- the
app's ONE shared `powerwave:theme-change` handler, which already
re-themes the main Waveform panels/ruler/digital chart -- never touched
the preview's own Plotly instances, so an already-open panel simply
never got re-colored on a live theme switch. A further compounding
detail: `wwApplyTheme()`'s own `if (ww.panels.length === 0) return;`
guard used to skip the WHOLE function (even the ruler) whenever the
main Waveform page had zero panels -- exactly the state the owner's own
repro produces.

**Fix**: the preview's initial layout now also sets `xaxis.gridcolor`/
`yaxis.gridcolor`/zeroline color from `wwThemeColors().grid` -- the
SAME token the main panel already uses (axis tick/legend text needed no
separate override; Plotly's own inheritance already cascades
`layout.font.color`). `wwApplyTheme()`'s early-return now guards only
the main-panel loop, and a new block re-themes
`wwCcPreview.panelsByType` via `Plotly.relayout()` only -- never
`newPlot`/`react`, so no waveform re-fetch. One shared theme-
application entry point for the whole app, no second competing
handler; preview and main-page rendering STATE remain fully
independent, only theme tokens/mechanism are shared.

**Verified directly** (via `window.PowerwaveTheme.setTheme()` against
jsdom's real `getComputedStyle` resolution of the actual shipped
`theme.css` -- genuine computed hex-value checks, not source-text
matching): Light->Dark and Dark->Light both re-theme an already-open
panel immediately with no reload/re-toggle/navigation; all simultaneous
type panels update on one switch; zero network fetches from a theme
switch; modebar/config survive (relayout never recreates the chart);
main Waveform page's own theme behavior unchanged even with a preview
panel coexisting.

**Tests**: extended `phase5a_check.mjs` with 10 new checks -- **101/101
passing** in the file overall (92 prior unchanged). Full frontend suite
reconfirmed at the true 33-failure baseline. Backend untouched (no
backend files touched).

**Browser verification**: no headless Chrome/Puppeteer available in
this sandbox; jsdom's own CSS engine against the real `theme.css` was
used to resolve genuine computed custom-property values instead --
flagged for owner UAT (a real-browser visual check).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this fix
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A-UAT6 — Calculated Channels Preview Panels by Engineering Type)

**Phase 5A-UAT6 — Calculated Channels Preview Panels by Engineering
Type.** Owner requirement, extending the same-day Phase 5A-UAT5 work:
the Calculated Channels page's own lightweight Waveform Preview
previously overlaid every visible calculated channel into one Plotly
chart regardless of type. No new decision -- an "Update" note appended
to DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT6](MIGRATION_PLAN.md#phase-5a-uat6--calculated-channels-preview-panels-by-engineering-type-2026-08-21).

**Fix**: `#wwCcPreviewChart` (one shared chart) replaced by
`#wwCcPreviewPanels`, populated by `wwCcRenderWaveformPreview()` with
one lightweight Plotly panel per engineering type currently represented
among visible calculated channels -- the SAME `calc.engineering_type`
authority, `ANALOG_GROUP_ORDER` ordering, and `"Calculated - <Type>"`
naming already established for the main Waveform page's own Grouped-
mode panels (Phase 5A-UAT5), never re-inferred here. A new
`panelsByType` map tracks each type's own DOM/Plotly instance across
renders -- a still-present type is REUSED (`Plotly.react()` + a cheap
`appendChild()` re-parent for ordering) rather than torn down and
rebuilt; a type is only purged (`Plotly.purge()` + DOM removal) when
its last member is hidden/deleted -- no stale canvas, duplicate charts,
or orphaned resize wiring.

**Preserved exactly**: the preview remains calculated-only (never
recorded analog channels, verified directly even when a recorded
channel of the same type is also displayed on the main Waveform page);
visibility authority (`wwCcPreviewVisibleChannels()`) is unchanged, no
new preview-specific visibility state; each visible channel is still
fetched exactly once via the existing batch, regardless of how many
type panels the results span (grouped by type client-side AFTER
fetching, never a duplicate fetch per panel); native-Plotly-only
interaction, theme handling, X-axis convention, and the 3 existing
lifecycle call sites are all unchanged. Rendering state is deliberately
independent from the main Waveform page's own `ww.panels` -- verified
directly that no `"Calculated - <Type>"` string ever appears as a
`ww.panels` groupKey; only classification metadata/ordering/naming is
shared, never an actual Plotly instance.

**Tests**: extended `phase5a_check.mjs` with 8 new checks (same-type
sharing one panel, different types in separate panels with order
verified independent of toggle order, hiding the last member of one
type removing only that panel while a still-present type's chart
instance is proven never torn down/recreated, Undefined's own panel,
calculated-from-calculated landing in the same panel, single-type
regression, main-Waveform-independence regression, calculated-only
regression) plus 9 pre-existing preview tests rewritten to the new
multi-panel DOM structure -- **92/92 passing** in the file overall. Full
frontend suite reconfirmed at the true 33-failure baseline. Backend
untouched (no backend files touched).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this feature
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A-UAT5 — Calculated Waveform Panels Grouped by Engineering Type)

**Phase 5A-UAT5 — Calculated Waveform Panels Grouped by Engineering
Type.** Owner observation: the Waveform sidebar was already correctly
grouped (Phase 5A-UAT4) by engineering type, but the actual WAVEFORM
PANELS in Grouped mode still combined every calculated channel into one
generic "Calculated" panel. No new decision -- an "Update" note appended
to DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT5](MIGRATION_PLAN.md#phase-5a-uat5--calculated-waveform-panels-grouped-by-engineering-type-2026-08-21).

**Root cause, confirmed by direct trace**: `wwPanelGroupKeyFor(channel)`
-- the ONE function every panel creation/reconciliation path already
funnels through -- returned `channel.engineeringType || "Undefined"`
for Grouped mode, and every calculated channel's own `engineeringType`
was (deliberately, per Phase 5A-UAT4) the hardcoded string
`"Calculated"`. Every calculated channel, regardless of its real
inherited type, collapsed into one shared panel.

**Fix**: a calculated-specific branch added to `wwPanelGroupKeyFor()`
and `wwPanelLabelFor()`, checked only inside the Grouped-mode
fallthrough (Separate/Custom branches untouched) --
`wwIsCalculatedSourceId(channel.sourceId)` routes to a new
`wwCalculatedEngineeringTypeFor()`, reading
`ww.calculatedChannels.get(id).engineering_type` directly (the SAME
backend-authoritative field Phase 5A-UAT4 introduced) -- never inferred
from the channel's own name, never re-derived from unit, never read
from the sidebar DOM. Group key `"calc:" + type`, display title
`"Calculated - " + type`. One small, surgical change to the generic
resolver -- no scattered special cases elsewhere.

**Confirmed unaffected**: Separate mode (each calculated channel still
its own panel), Custom mode (existing solo-panel key convention
untouched), A/B cursor values, Callout attachment across a mode round
trip, and Absolute/Elapsed switching (zero extra fetch) -- channel
identity never changes when a channel moves between panels, so
`ww.cursorValues`/`ww.annotations`/`ww.sourceTiming` all keep resolving
correctly regardless of which panel currently holds the trace.

**Tests**: extended `phase5a_check.mjs` with 11 new checks (same-type
sharing one panel, different types in separate panels, recorded vs.
calculated of the same type staying distinct, empty-panel cleanup on
last-hide, Undefined classification's own dedicated panel, Separate/
Custom regressions, a full 5-step mode-switching sequence, Absolute/
Elapsed regression, A/B regression, Callout-attachment regression) --
**84/84 passing** in the file overall (73 prior unchanged). Full
frontend suite reconfirmed at the true 33-failure baseline (zero net
new regressions). Backend untouched, full suite green (no backend files
touched).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this feature
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A-UAT4 — Calculated Channel Type Subgroups)

**Phase 5A-UAT4 — Calculated Channel Type Subgroups.** Owner-approved
clarification: on the main Waveform page, calculated channels remain
under their own top-level "Calculated Channels" group (never merged
into the real Analog Channels groups), but now with nested engineering-
type subgroups (Voltage/Current/Power/Frequency/ROCOF/Undefined) mirror-
ing the Analog Channels hierarchy. No new decision -- an "Update" note
appended to DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT4](MIGRATION_PLAN.md#phase-5a-uat4--calculated-channel-type-subgroups-2026-08-21).

**Classification authority**: `CalculatedChannel` had no classification
field before this change. Source analog channels are classified by the
existing `app.domain.channel_classification.classify_analog_channel()`
(unrelated, unchanged, three-tier: explicit metadata, recognized unit,
else `Undefined`). This change adds a NEW inherited field,
`CalculatedChannel.engineering_type`, computed by a new pure function,
`derive_engineering_type(input_types)`: every input must share the same
KNOWN type for it to be inherited, else `Undefined` -- ONE rule covering
unary (trivially one input) and multi-input (2+ inputs must agree)
identically, with calculated-from-calculated propagating for free (an
input passes its own already-derived type back through the same
function -- verified transitively through a two-level chain). Never
guessed from the user-editable channel name. Classification never
blocks or alters a calculation -- the existing unit-compatibility and
time-alignment guardrails (completely unchanged) remain the sole
eligibility authority.

**Sidebar**: `#calculatedChannelsSidebarSection` is now itself a
collapsible `<details class="channel-group">` (same visual language as
Analog/Digital Channels), containing nested per-type `<details
class="channel-subgroup">` blocks ordered by the same `ANALOG_GROUP_ORDER`
Analog Channels already use. Absent types render no subgroup. Each
subgroup's own table still uses the SAME `renderChannelTable()`/
`wwCurValueCellHtml()` machinery Phase 5A-UAT2 established -- the Cur A/
Cur B fix is fully preserved. New parent + per-subgroup Show all/Hide
all buttons reuse the existing `.group-toggle-btn` visual language and
`ww.displayed` as the sole visibility authority -- no second visibility
state.

**Deliberately unchanged**: `wwPanelGroupKeyFor()`'s own Grouped-mode
panel-placement key stays hardcoded `"Calculated"` -- sidebar grouping
is presentation-only and never touches Grouped/Separate/Custom/A-B/
Peak/Callout, verified directly by the full existing regression suite.

**Tests**: extended `phase5a_check.mjs` with 8 new checks -- **73/73
passing** in the file overall (65 prior unchanged). New backend tests
(`TestDeriveEngineeringType`, `TestEngineeringTypeInheritance`, plus one
additive API assertion) -- full backend suite green. Full frontend
suite reconfirmed at the true 33-failure baseline (zero net new
regressions).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this feature
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A UAT — Absolute Time after adding a calculated channel)

**Phase 5A UAT — Absolute Time after adding a calculated channel.**
Bug fix to DEC-047's frontend implementation, preserving DEC-042.
Owner UAT found that Absolute Time stopped being selectable after a
calculated channel was displayed. Root cause was not Plotly rendering,
not a backend calculation issue, and not a time-mode refetch: calculated
channel metadata was being added to `ww.displayed` with
`recordingStartTime: null` and `timingReference: null`, so
`wwAvailableTimeModes()` correctly intersected the workspace down to
Elapsed only.

**Fix**: `ww.sourceTiming` now caches real source timing metadata from
the same `/sources/{id}/channels` timebase response as `ww.sourceBounds`.
Calculated channels keep their `calc-*` pseudo-source id for
display/layout/annotation identity, but `wwCalculatedChannelMeta()`
inherits `recordingStartTime` and `timingReference` through
`reference_source_id`. `wwParticipatingSourceIds()` also resolves
calculated traces through that reference source for workspace bounds,
so only-calculated views stay grounded in the original recording.
Source removal and Start New Workspace clear the timing cache with the
same lifecycle as source inventory/bounds; plain Clear remains
display-only.

**Verified**: targeted static tests pass; a headless browser probe
confirmed `wwAvailableTimeModes()` remains `["absolute", "elapsed"]`
after adding a calculated channel, Absolute can be selected again,
the calculated trace's `timingReference` is `absolute`, participating
source ids resolve to the real source, and elapsed/absolute mode
switches trigger no additional waveform fetch. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A UAT Absolute Time](MIGRATION_PLAN.md#phase-5a-uat--absolute-time-after-adding-a-calculated-channel-2026-08-21).

**Phase 5A-UAT3 — Calculated Channel Input Availability.**
Owner-approved clarification: Calculated Channels can now use ALL
available analog channels (source and calculated) from the active
workspace, regardless of whether those channels are currently visible
on the main Waveform page. Waveform visibility is presentation state
only and is never an engineering eligibility criterion. No new decision
-- an "Update" note appended to DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT3](MIGRATION_PLAN.md#phase-5a-uat3--calculated-channel-input-availability-2026-08-21).

**Root cause: `wwCcAvailableCandidates()` read from `ww.channelMeta`**,
a Map scoped, per its own original comment, to "every analog channel
the engineer has brought into this workspace's Waveform at least once"
-- populated solely by `wwAddSelectedChannels()`, i.e. only on first
DISPLAY. A source channel never individually toggled visible was
therefore absent from the picker even though its own SOURCE had already
been opened and its full channel list was already known to the backend.
Not a backend gap -- confirmed by inspection that the backend's own
`ChannelRef` validation never depended on visibility at all; no backend
files touched.

**Fix**: a new `ww.sourceChannelInventory` (`sourceId -> {sourceId,
sourceName, analogChannels}`), populated directly from the SAME `GET
.../sources/{id}/channels` response `selectSource()` already fetches
for the Channel Browser -- zero new network calls -- covering every
analog channel of every source opened this session, independent of
display history. `wwCcAvailableCandidates()` now reads from this
inventory instead of `ww.channelMeta`, which is left completely
untouched (still used, unmodified, by the unrelated Custom Groups chip
editor). Lifecycle mirrors `ww.sourceBounds`: deleted per-source on
source removal, cleared entirely only by Start New Workspace --
deliberately NOT cleared by plain "Clear workspace" (unlike
`ww.channelMeta`/`ww.channelColors`), since that button is display-only
and keeps the still-selected source fully loaded; clearing the
inventory there would have silently reintroduced the same bug. The
existing client-side same-source candidate-disable heuristic needed no
change (it already compares `referenceSourceId`, unaffected by where
candidates come from) -- real unit/time-alignment compatibility remains
entirely backend-enforced, unchanged. The picker's single flat group
was split into one optgroup per source, matching the owner's preferred
"Source 1 / Source 2 / Calculated Channels" structure.

**Tests**: extended `phase5a_check.mjs` with 11 new checks (hidden-
channel Reverse Polarity/Absolute Value/Multiply-by-Constant, N-input
Addition/Subtraction with hidden inputs, a hidden calculated channel
remaining available as a further input, an incompatible hidden
cross-source channel still correctly disabled, hide-all/show-all
leaving the candidate inventory unchanged, source removal dropping
exactly that source's own candidates, waveform-preview regression, A/B-
sidebar regression, and per-source grouping) -- **65/65 passing** in the
file overall (53 prior unchanged). Full frontend suite reconfirmed at
the true 33-failure baseline (zero net new regressions -- `phase2cc*`'s
own pre-existing failures individually re-inspected and confirmed
unrelated to `ww.channelMeta`/Custom Groups). Backend untouched,
519/519 unchanged (no backend files touched).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this feature
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A-UAT2 — Standard A/B Measurements for Calculated Channels)

**Phase 5A-UAT2 — Standard A/B Measurements for Calculated Channels.**
On the main Waveform page, the Calculated Channels sidebar group now
shows Cur A / Cur B measurement columns identical to real Analog
Channel rows -- a frontend consistency fix, no calculation mathematics
touched. No new decision -- an "Update" note appended to DEC-047. Full
detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT2](MIGRATION_PLAN.md#phase-5a-uat2--standard-ab-measurements-for-calculated-channels-2026-08-21).

**Root cause: purely presentational, never a data/backend gap.** The
Phase 5A `/calculated-channels/cursor-values` endpoint and its frontend
dispatch (`wwFetchCursorValuesForSource()`'s `isCalculated` branch,
`wwFetchAllCursorValues()`'s source-id-driven fan-out over
`ww.displayed`) were already fully wired and already correctly
populating `ww.cursorValues` for calculated channels -- proven directly
by the pre-existing, unchanged A/B cursor test (`[99]`).
`wwRenderCalculatedChannelsSidebarSection()` simply built its own
bespoke, entirely unstyled `<tr>` markup (a lone name cell, wrapped in
a `class="channel-table"` with no CSS rule anywhere in the stylesheet)
instead of reusing `renderChannelTable()`, the SAME generic table
builder real analog rows already use for their own Channel/Phase/Cur A/
Cur B columns.

**Fix**: `wwRenderCalculatedChannelsSidebarSection()` now calls
`renderChannelTable()` with `[Channel, Cur A, Cur B]` (no Phase --
calculated channels carry none), reusing `analogChannelNameCellHtml()`/
`wwCurValueCellHtml()`/`wwCurValueText()` verbatim -- all were already
fully generic (keyed by `sourceId`/`channelName`, gated by the SAME
`wwIsAnalogChannelVisible()`/`ww.measurementCursors` authority). A new
`calculatedChannelRowAttrs()` mirrors `analogChannelRowAttrs()`'s shape
and additionally tags each row with `data-channel-kind="analog"`/
`data-source-id`/`data-channel-name` -- the SAME triad real analog rows
carry -- so calculated-channel rows are picked up, entirely for free,
by the EXISTING generic Cur A/Cur B live-update sweeps
(`wwUpdateCursorValueCellsForChannels()`/`wwUpdateAllCursorValueCells()`)
that already drive cursor-drag/cursor-move/mode-toggle updates for real
channels -- **no new update plumbing was written for calculated
channels at all**. Verified safe against the shared `data-channel-kind`
attribute's other consumer (`setupChannelRowToggles()`'s click
dispatch, delegated on `#channelGroups` only, a different DOM subtree).
The sidebar's own pre-existing dedicated click handler
(`wwCalculatedChannelsSidebarRowClickHandler`) is unchanged.

**One small related bug fixed in the same change**: the sidebar
section's zero-channels early return used to skip clearing
`bodyEl.innerHTML`, leaving the last channel's stale `<tr>` in the DOM
(invisible only because the ancestor `<section>` itself was hidden) --
discovered by this task's own "delete -> row disappears cleanly"
acceptance check. Now matches `wwRenderCalculatedChannelManagerList()`'s
own sibling convention (already clears its body at zero).

**Tests**: extended `phase5a_check.mjs` with 10 new checks (A/B-off em
dash parity, A/B-on values matching the authoritative array via the
nearest-sample rule, moving A/moving B independently, calculated-from-
calculated, out-of-range em dash, delete removing the row entirely,
Grouped/Separate/Custom producing no duplicate/stale rows, and a
structural guard for `table.channels`/3 columns) -- **53/53 passing**
in the file overall (44 prior unchanged). Full frontend suite
reconfirmed at the true 33-failure baseline (zero net new regressions,
`phase4c1`/`phase4c2`/`phase4f`/`phase4g` individually reconfirmed
passing). Backend untouched, 519/519 unchanged (no backend files
touched).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this feature
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A-UAT — Calculated Channel Waveform Preview)

**Phase 5A-UAT — Calculated Channel Waveform Preview.** Owner-requested
addition of a lightweight **Waveform Preview** panel to the Calculated
Channels page, sitting below the existing manager list -- explicitly
NOT the full Waveform workspace, only a simple preview chart using
native Plotly interaction tools. No new decision -- a straightforward
extension, documented as an "Update" note on DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations),
[MIGRATION_PLAN.md — Phase 5A-UAT](MIGRATION_PLAN.md#phase-5a-uat--calculated-channel-waveform-preview-2026-08-21).

**Every authority reused from the existing DEC-047 implementation --
nothing new introduced.** Visibility: `wwIsAnalogChannelVisible()`
reading `ww.displayed`, the SAME authority the manager list's own eye
icon and the Waveform sidebar group already share -- no second,
conflicting visibility state. Data: the existing
`GET .../calculated-channels/{id}/waveform` endpoint (Phase 5A already
built it -- zero new backend work). Color: `wwColorForChannel()`. Theme:
`wwThemeColors()`. A completely standalone Plotly instance
(`#wwCcPreviewChart`) -- never added to `ww.panels`, never touching
`ww.viewport`/layout mode/A-B cursor state/annotations. Native Plotly
modebar/pan/zoom only (`displayModeBar: true`, explicit) -- no custom
Powerwave toolbar.

**Rendering**: full rebuild on every change (refetch all currently-
visible calculated channels, `Plotly.newPlot()`/`Plotly.react()`)
rather than incremental trace diffing -- simpler, adequate for a small-
channel-count Phase 1 preview, matching the task's own "do not
overengineer caching" instruction. Guarded by a monotonic generation
counter (same stale-response idiom as `wwCursorValuesGeneration`/
`wwPeakValuesGeneration`/`ww.annotationPlacementGeneration`).

**Lifecycle**: wired into the exact same 3 sites that already refresh
the manager list (`wwRenderCalculatedChannelsPage()`,
`wwToggleCalculatedChannelDisplay()`, `wwCcDeleteChannel()`'s success
branch) -- create/delete/toggle/Start New Workspace/Clear Workspace all
behave identically to the manager list's own established behavior, no
new rule invented.

**Page isolation**: proactively avoided a FOURTH occurrence of the
`[hidden]`-CSS-cascade bug this session had already hit three times --
`.ww-cc-preview-chart` deliberately declares no `display` property at
all (matching `.empty-state`/`.ww-cc-panel`'s own existing safe pattern
on this same page), so there is nothing in author CSS to override the
UA stylesheet's own `[hidden]` rule.

**Tests**: extended `phase5a_check.mjs` with 14 new checks (panel
placement, default-hidden-on-creation, visibility toggle both
directions, delete, multiple channels with distinct colors sourced from
the real authoritative array, native `displayModeBar: true`, non-
interference with the main Waveform page's own panels/viewport, a
structural CSS regression guard, and Start New Workspace / Clear
Workspace lifecycle behavior) -- **44/44 passing** in the file overall
(32 prior unchanged). Full frontend suite reconfirmed at the true
33-failure baseline (zero net new regressions). Backend untouched,
519/519 unchanged (no backend files touched).

**Not yet done** (as of this section being written): commit/push,
CI/automatic DEV deployment verification, and owner UAT of this feature
specifically -- see the final report delivered alongside this update for
whether those have since completed.

## What was done in the prior session (Phase 5A UAT Fix — Page Navigation Isolation)

**Phase 5A UAT Fix — Page Navigation Isolation.** Owner UAT on the page
below found Recording Events (and separately Waveform) showing the
Calculated Channels page STACKED underneath it. No new decision -- an
"Update" note appended to DEC-047. Full detail:
[DECISIONS.md — DEC-047 Update note](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations).

**Root cause: the SAME CSS-cascade bug class already caught and fixed
once this session for the annotation placement guidance ribbon.**
`#pageCalculatedChannels { display: flex; }` (author CSS) beat the UA
stylesheet's own `[hidden] { display: none }` rule by ORIGIN alone.
`shellSetCurrentPage()` -- confirmed by direct trace to be the SOLE
navigation authority, correctly toggling `.hidden` on all three page
containers (`workspaceRow`/`pageRecordings`/`pageCalculatedChannels`)
and all three nav buttons' own `aria-current` in one exclusive pass --
was NEVER wrong; `#pageCalculatedChannels.hidden` was already `true`
whenever a different page was active, but that had zero visible effect.
`#pageRecordings` itself already carried its own `[hidden]` override
from when it was first added (Phase 3B); the new Calculated Channels
page simply never received the same treatment when this session added
it. **DOM nesting was independently inspected and confirmed correct**
(`#pageCalculatedChannels` is a genuine sibling `<section>`, never
nested inside `#pageRecordings`) -- ruling out a missing/misplaced
closing tag as a contributing cause.

**Fixed with one line**: `#pageCalculatedChannels[hidden] { display:
none; }`, the same established pattern already used for
`#workspaceRow[hidden]`/`#pageRecordings[hidden]`/
`.ww-annotation-guidance[hidden]`.

**Tests**: extended `phase5a_check.mjs` with 6 new checks -- a
structural regression guard confirming the `[hidden]` override rule is
present in the shipped stylesheet (verified directly to FAIL without
the fix and PASS with it -- jsdom cannot render CSS cascade, so this is
the only check capable of catching a regression of this specific kind),
an exactly-one-page-visible + exactly-one-nav-item-active assertion for
each of the three real pages, a rapid-switching sequence across all
three, and a hide-don't-destroy check confirming in-progress builder
state (selected operation + partial input list) survives a round trip
through Waveform and back -- **32/32 passing** in the file overall (26
prior unchanged). Full frontend suite reconfirmed at exactly the true
33-failure baseline (zero net new regressions). Backend untouched,
519/519 unchanged.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this fix specifically.

## What was done in the prior session (Phase 5A — Calculated Channels / Basic Signal Builder, DEC-047)

**Phase 5A — Calculated Channels / Basic Signal Builder (DEC-047).**
Owner-approved direction: Oruxa Powerwave's first mathematical signal-
derivation system, NOT an annotation tool -- a new main-sidebar page
(`Calculated Channels`, immediately below `Table`), both a Signal
Builder and a Calculated Channel Manager on one page. Full detail:
[DECISIONS.md — DEC-047](DECISIONS.md#dec-047--calculated-channels-are-workspace-scoped-derived-analog-channels-from-authoritative-full-resolution-inputs-requiring-proven-synchronized-sample-time-alignment-for-multi-input-operations).

**Five basic operations only** (no RMS, not even a disabled card):
Reverse Polarity (`y=-x`), Absolute Value (`y=|x|`), Multiply by
Constant (`y=k*x`, dimensionless `k`), N-input Addition
(`y=x1+x2+...+xN`, 2+ inputs, never hard-coded to 2), and ordered
N-input Subtraction (`y=x1-x2-...-xN`, explicitly left-associative,
order preserved end to end via add/remove/up-down-reorder controls).
Duplicate inputs explicitly allowed (`A+A` valid, never deduplicated).

**Full-resolution authority, eager evaluation**: every operation
evaluates against `active.record.waveform_data` directly (or another
calculated channel's own already-evaluated result), ONCE at creation --
retained server-side in a new workspace-scoped
`CalculatedChannelRegistry` (mirrors `WorkspaceRegistry`'s own shape/
locking policy), never re-evaluated later, never touching Plotly trace
arrays or the reduced display envelope. `_clip_and_reduce()`/
`_peak_in_range()` were extracted from `waveform_service.py`'s own
EXISTING source-channel functions into shared pure array-level helpers
-- reused by both the pre-existing source-channel endpoints (verified
zero behavior change via the full backend suite before any new test was
added) and the new calculated-channel service, so there is exactly ONE
reduction algorithm and ONE peak-search algorithm in the codebase.

**The owner's own explicit time-alignment guardrail is a hard
engineering rule** (a mid-turn correction that meaningfully tightened
the original "compatible time base" wording): multi-input operations
require every operand to be PROVEN to share the same authoritative
synchronized sample-time axis -- same-source channels are provably
aligned WITHOUT array comparison (verified directly: one
`DisturbanceRecord` has exactly one shared `waveform_data["time"]`
column per source, no per-channel time array exists anywhere in this
codebase's model); different-source channels are rejected UNLESS their
TRUE ABSOLUTE instants (`source.start_time + elapsed`, never raw
elapsed arrays -- two independently-triggered recordings can trivially
share identical elapsed arrays without representing the same physical
instant) are proven identical within a deliberately tight `1e-9`-second
tolerance. Equal sample count/sampling rate ALONE are explicitly
insufficient. No interpolation/resampling/time-shifting/crop-to-overlap
is ever performed -- an unproven pair is rejected outright.

**Calculated-from-calculated is supported from Phase 1**: verified
`Sum=A+B`, `Scaled=Sum*2`, `AbsScaled=abs(Scaled)` all produce correct
full-resolution values. Every calculated channel carries a
`reference_source_id` (propagated transitively) that lets BOTH
timebase-compatibility checking AND source-removal cascade collapse to
a simple identity/filter check, never a graph walk. Explicit
`dependency_ids` + a generic, independently-testable
`would_create_cycle()` reachability guard (structurally unreachable via
the real immutable, one-shot creation API today, but implemented and
tested against a hand-constructed graph as defense in depth, per the
task's own explicit instruction).

**Treated as an analog-like PSEUDO-SOURCE channel everywhere in the
existing rendering/layout/annotation machinery** -- its own server-
generated id (`"calc-" + <hex>`) is used AS `sourceId`, its own name AS
`channelName`, so `wwAddSelectedChannels()`/`ww.displayed`/
`ww.channelColors`/Grouped-Separate-Custom/the Annotation List's own
`sourceId`+`channelName` fields all work COMPLETELY UNCHANGED, zero new
branching. The ONE reported structural shortcut: `wwIsCalculatedSourceId()`,
a single `"calc-"`-prefix dispatch helper at the small set of network-
request call sites (waveform/cursor-values/peak-values/Callout) that
route to a new `/calculated-channels/...` endpoint family -- chosen over
threading a fully generic `ChannelRef` type through the ENTIRE existing
frontend call graph, which the task's own section 58 explicitly warned
against as disproportionate refactor scope. A/B cursor values, +Peak/
-Peak (full dynamic viewport recalculation reused unmodified), and
Callout (the task's own "SHOULD" tier -- included, not deferred, since
it required the same small increment as the others) all verified
working identically to a real source channel; adaptive resolution
verified (min_max_envelope for a >10,000-sample broad view,
full_resolution on deep zoom).

**Lifecycle**: default-hidden on creation (DEC-038, unchanged).
Immutable after creation (create another rather than editing); delete
is dependency-aware (BLOCKED, never silent cascade, with a message
naming the dependent(s)). Source removal cascades transitively (a flat
`reference_source_id` filter, both backend and frontend verified). Plain
"Clear workspace" preserves calculated-channel DEFINITIONS
(display-only, same established policy as every other workspace-scoped
collection); "Start New Workspace" clears them completely through the
SAME `DELETE /api/v1/workspaces/{id}` call already used for that purpose
(anticipated by that endpoint's own pre-existing docstring -- "any
future workspace-owned resource... has one lifecycle hook to plug
into"). No permanent database/cloud persistence. Original recording
immutability verified directly (creating a calculated channel never
mutates a source's own `waveform_data`).

**Tests**: backend -- 3 new test files, **83 new tests, 519/519 passing
overall** (436 previously existing, unmodified, confirmed via a
pre-change baseline run before any new test was added):
`test_calculated_channel_domain.py` (63 pure-function tests including
the full time-alignment guardrail matrix A-H from the owner's own
follow-up message), `test_calculated_channel_service.py` (service-layer
tests against synthetic fixtures), `test_calculated_channel_api.py` (20
end-to-end API tests via a real COMTRADE upload). Frontend -- new
`phase5a_check.mjs`, **26/26 passing** (navigation, operations, dynamic
forms, N-input add/remove/reorder + expression preview, subtraction
reordering, validation, manager list, Waveform sidebar group +
default-hidden + shared visibility authority, Grouped/Separate/Custom,
A/B values, +Peak/-Peak, Callout, adaptive resolution,
calculated-from-calculated, dependency-blocked delete, source-removal
cascade, workspace lifecycle, original-source immutability). One
pre-existing `phase3buat8_check.mjs` assertion (enabled main-sidebar
item list) updated in place -- the expected consequence of the new nav
item, not a regression (same precedent as Phase 4G's own menu-count
update). Full frontend suite reconfirmed at exactly the true
33-failure baseline (zero net new regressions).

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this phase specifically.

## What was done in the prior session (Phase 4G-UAT Bug Fix — Guidance Dismissal)

**Phase 4G-UAT Bug Fix — Guidance Dismissal.** Owner UAT on the ribbon
below found two symptoms: it did not disappear after a successful
+Peak/-Peak creation, and separately, Escape did not dismiss it either.
No new decision -- an "Update" note appended to DEC-046's own addendum.
Full detail:
[DECISIONS.md — DEC-046 addendum Update note](DECISIONS.md#addendum-2026-08-21-refinement--persistent-annotation-placement-guidance-ribbon-phase-4g-uat).

**Root cause (identical for both symptoms): a CSS-cascade bug, not a
state/lifecycle bug.** `.ww-annotation-guidance { display: flex; }`
(author CSS) beats the UA stylesheet's own `[hidden] { display: none }`
rule by ORIGIN alone (author always outranks UA in the normal cascade,
regardless of specificity or source order) -- so
`wwUpdateAnnotationPlacementGuidance()`'s own `el.hidden = true` had
ZERO visible effect, even though `ww.annotationPlacementType` was
already correctly `null` on both the successful-creation path AND the
Escape path (confirmed directly, not inferred -- traced the exact
success-path line where `wwExitAnnotationPlacementMode()` was reached,
and the Escape handler's own call to it). This is the SAME class of bug
this codebase already caught and fixed for `#workspaceRow[hidden]`/
`.shell-status-item[hidden]`/`#pageRecordings[hidden]`/`.ww-toolbar[hidden]`
-- the new ribbon simply hadn't received the same treatment. **Fixed with
one line**: `.ww-annotation-guidance[hidden] { display: none; }`.

**A second, genuine (non-CSS) race was found while investigating
Escape**: a Peak creation request already in flight when Escape (or a
tool switch, or even re-selecting the SAME tool after Escape) fired
could still resolve successfully afterward and silently create an
annotation from a placement session the engineer had already left.
Fixed with a new monotonic `ww.annotationPlacementGeneration` counter,
bumped on every genuine placement-mode transition (fresh entry/tool
switch, exit via success or Escape -- never a same-tool reselect no-op)
and captured by `wwCreatePeakFromClick()` at its own start; a stale/
superseded request's result -- success OR failure -- is now discarded
silently before touching any state or showing any error toast. Same
staleness-guard pattern already established for `ww.epoch`/
`wwPeakValuesGeneration`.

**Tests**: extended `phase4g_check.mjs` with 13 new checks -- a
structural regression guard asserting the CSS `[hidden]` override rule
is literally present in the shipped stylesheet source (the only
meaningful guard for a jsdom-invisible CSS-cascade bug -- jsdom does not
implement CSS cascade/rendering), the full asynchronous successful-
+Peak-creation path (never calling `wwExitAnnotationPlacementMode()`
directly), -Peak Escape, invalid-click-then-Escape, API-failure-then-
Escape, Escape-during-an-in-flight-request (ribbon hides immediately,
stale success creates nothing), a same-tool retry succeeding normally
after an Escape-cancelled request, toolbar-active-state +
`annotationPlacementBusy` invariants, and Text Note/Callout Escape
regressions -- **66/66 passing** in the file overall (56 prior checks
unchanged). Full frontend suite reconfirmed at exactly the true
33-failure baseline across the same pre-existing files (zero net new
regressions). Backend: untouched, 436/436 unchanged.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this fix specifically.

## What was done in the prior session (Phase 4G-UAT — Persistent Annotation Placement Guidance Ribbon, DEC-046 addendum)

**Phase 4G-UAT — Persistent Annotation Placement Guidance Ribbon (DEC-046
addendum).** Owner UAT result on Phase 4G below: "Engineering behavior:
PASS" but no guidance told the engineer what to do after selecting
Maximum Peak/Minimum Peak. Full detail:
[DECISIONS.md — DEC-046 addendum](DECISIONS.md#addendum-2026-08-21-refinement--persistent-annotation-placement-guidance-ribbon-phase-4g-uat).

**One generic ribbon, driven entirely by `ww.annotationPlacementType`**
(the SAME single authority `wwEnterAnnotationPlacementMode()`/
`wwExitAnnotationPlacementMode()` already are) -- a new
`WW_ANNOTATION_PLACEMENT_GUIDANCE` map (`{icon, message}` per type) plus
`wwAnnotationPlacementGuidance(type)`/`wwUpdateAnnotationPlacementGuidance()`,
called ONLY from those two existing state-transition functions, never
per-render, never a second competing state or timer. **Mandatory for
`peak_max`/`peak_min`**; also enabled for `text_note`/`callout` since the
same generic map covered them cleanly with zero extra branching.

**Ribbon (`#wwAnnotationGuidance`) is a normal-layout sibling row**
between the waveform toolbar and `#activeViewArea` -- never `position:
absolute/fixed`, so it structurally cannot overlay/intercept Plotly, the
sidebar, or the toolbar. `role="status"`, updated only on state
transitions (never re-announced on ordinary re-renders). No auto-dismiss
timer anywhere -- persistence is a direct, single-authority consequence
of `ww.annotationPlacementType` alone.

**Peak's own placement-mode completion timing was corrected** (the one
engineering-adjacent change this refinement required): it previously
exited immediately on any valid trace click (inherited from Callout's
own established one-shot pattern via `wwWireAnalogPanelClick()`), so a
failed/no-data result already silently ended guidance with no way to
retry without reselecting the tool. `wwCreatePeakFromClick()` now exits
placement mode ONLY on a successful creation; a new
`ww.annotationPlacementBusy` flag (`try/finally`-guaranteed) guards
against a second concurrent request while one is already in flight.
**Callout's own exit-immediately timing is explicitly UNCHANGED** --
this task's own section 5 scoped Callout's guidance as optional, and its
engineering behavior was never redesigned.

**Tests**: extended `phase4g_check.mjs` with 19 new checks (Maximum/
Minimum Peak guidance content and Esc hint, no ribbon before placement
mode, invalid clicks never dismiss, successful creation hides the
ribbon, Escape hides it, API-failure and no-data-unavailable both keep
mode/ribbon active with zero annotations created, a failed attempt
retries successfully afterward, tool switching updates one ribbon in
place with no stale text, re-select-same-tool no-op, dropdown toggling
doesn't dismiss, toolbar active state + ribbon coexist, no-timeout
across many ticks/renders, dynamic recalculation never re-shows the
ribbon, `role="status"` present, a concurrent second click during an
in-flight request is ignored, a Callout-timing regression check, and
optional Text Note/Callout guidance) -- **56/56 passing** in the file
overall (37 prior Phase 4G checks unchanged). Full frontend suite
reconfirmed at exactly the true 33-failure baseline across the same
pre-existing files (zero net new regressions). Backend: untouched,
436/436 unchanged.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this refinement specifically.

## What was done in the prior session (Phase 4G — Dynamic Maximum/Minimum Peak Annotation, DEC-046)

**Phase 4G — Dynamic Maximum/Minimum Peak Annotation (DEC-046).**
Owner-approved direction on top of Phase 4F-UAT2 below: two new generic
recorded-analog-channel annotation types, `+Peak`/`-Peak`. Full detail:
[DECISIONS.md — DEC-046](DECISIONS.md#dec-046--maximumminimum-peak-annotations-are-generic-recorded-channel-measurements-over-the-current-visible-x-viewport-dynamically-recalculated-on-genuine-x-viewport-changes).

**The key difference from Callout (Phase 4F)**: a Peak is a LIVE
viewport measurement, not a one-shot fixed anchor. `Annotate -> Maximum
Peak (+Peak)`/`Minimum Peak (-Peak)` -> click an analog trace -> the
clicked TRACE resolves channel identity (same stable
`"sourceId::channelName"` `meta` mechanism Callout uses), but the
click's own X position is irrelevant -- the value is always calculated
over the CURRENT `ww.viewport`. Whenever the X viewport genuinely
changes (zoom, pan, step zoom, Reset Time View -- all funneled through
the one existing `wwApplyAndFetchViewport()` call site), every active
Peak annotation is recalculated IN PLACE (same annotation id, `createdAt`
unchanged) via a new batched-per-source endpoint,
`POST .../sources/{source_id}/peak-values`. Y-range changes, Autoscale
Y, Absolute/Elapsed switching, and Peak box drags never trigger
recalculation -- verified directly (zero new requests in each case).

**Full-resolution authority, tie rule, NaN handling**: a new backend
`resolve_peak_value()` reads `active.record.waveform_data` directly (the
same authoritative source Callout's own anchor resolution reads),
boundary-inclusive range-clips via the same `np.searchsorted` technique
`extract_waveform_range` already uses, masks non-finite samples via
`np.isfinite` before the max/min search (an interval with zero finite
samples resolves to `available: false`), and relies on
`numpy.argmax`/`argmin`'s own first-occurrence-on-tie behaviour for the
owner's required earliest-sample tie rule -- no second nearest-sample or
tie-break definition anywhere in the codebase.

**Rendering reuses Callout's shared geometry engine, not a second
implementation**: `wwAnchoredAnnotationContentPosition()`/
`wwAnchoredAnnotationPagePosition()`/`wwAnchorValueToPixelY()`
(generalized from their Callout-only predecessors via two small
type-dispatching getters) and `wwUpdateCalloutConnectorGeometry()`
(extended with an `isPeak` flag) serve both `callout` and
`peak_max`/`peak_min`. **The Peak anchor marker is calculated and
deliberately NOT draggable** (the opposite of Callout's own now-movable
anchor) -- the shared anchor-drag pointerdown handler now checks
`annotation.type === "callout"` before starting any preview, and a
Peak's own hit circle is non-hit-testable with no grab cursor. The label
BOX remains fully draggable via the identical `wwWireCalloutBoxDrag()`
mechanics (offset-only, never touches the anchor/backend/recalculation).
The canvas label is a system-computed two-line `.textContent`-only
rendering (`"+Peak: 230.4 MW"` / `"t = 219.400 ms"`) -- never
`.innerHTML`, never user-editable (no `text` field, no textarea path).
A new `--annotation-peak-accent` token (muted teal-green, both themes)
and a filled-triangle header glyph distinguish it, deliberately avoiding
alarm red and A/B cursor blue/red.

**Visibility/unavailable/source-removal**: an unprojectable anchor, or a
viewport with no valid sample for the channel (`available: false`), is
hidden from canvas but stays fully intact in `ww.annotations`/the
Annotation List -- recalculation always runs on every genuine viewport
commit regardless of the channel's current display visibility, so a
re-shown channel's Peak is already current by construction. Source
removal deletes that source's Peak annotations outright, extending
DEC-045's own sweep (`wwRemoveAnchoredAnnotationsForSource()`, renamed/
generalized from its Callout-only predecessor). Stale-response
protection reuses the same per-source generation-counter pattern
`wwCursorValuesGeneration` already established, plus a per-annotation
`ww.annotations.has(id)` check for deletion-mid-flight.

**No Peak-to-Peak this phase** (explicitly out of scope), nor RMS-from-
waveform/cycle-RMS, phasor angle, delta measurement, event marker,
cross-channel peak, digital peak, peak anchor dragging, automatic A/B
placement at peaks, a whole-record/current-window toggle, a custom
search interval independent of the viewport, annotation import/export,
or permanent database persistence.

**Tests**: new `phase4g_check.mjs`, **37/37 passing** -- menu presence/
order/no-Peak-to-Peak, exact trace identity, viewport-only search
interval, full-resolution authority, earliest-tie regression, dynamic
recalculation on zoom/pan/step-zoom/Reset-Time-View, zero recalculation
on Y-zoom/Autoscale/Absolute-Elapsed/box-drag, stale-viewport-response
rejection, deletion-mid-flight discard, unavailable-for-viewport
handling, hidden-channel/re-show/layout-mode behavior, non-draggable-
marker + draggable-box, multi-type/multi-source coexistence with
one-batched-request-per-source, source removal, workspace lifecycle, and
safe rendering. One pre-existing `phase4e_check.mjs` assertion (menu
item count) updated in place from 2 to 4 items -- the expected
consequence of this phase's own menu additions, not a regression. Full
frontend suite reconfirmed at exactly the true 33-failure baseline
across the same pre-existing files (zero net new regressions). Backend:
**436/436 passing** (24 new -- `test_peak_value_service.py`,
`test_peak_value_api.py` -- + 412 previously existing, unmodified).

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this phase specifically.

## What was done in the prior session (Phase 4F-UAT2 — Free 2D Callout Anchor Drag Preview, DEC-045 addendum #2)

**Phase 4F-UAT2 — Free 2D Callout Anchor Drag Preview (DEC-045 addendum
#2).** Owner UAT direction on top of Phase 4F-UAT below: "Engineering
outcome: PASS. User experience: FAIL" -- dragging the anchor marker
upward/downward felt constrained to a horizontal rail (Y was pinned to
the current `anchorValue`'s own projection during preview), even though
the final snap was already correct. Full detail:
[DECISIONS.md — DEC-045 addendum #2](DECISIONS.md#addendum-2026-08-21-refinement--anchor-drag-preview-became-free-2d-phase-4f-uat2).

**Preview now follows the pointer freely in both X and Y** -- purely a
presentation change. `livePreviewUpdate()` was rewritten to take the
already-resolved page-pixel coordinates directly
(`previewPageX`/`previewPageY`) instead of internally reprojecting a
single elapsed-time value; the marker, connector, and box (via its
existing `boxOffset`) all follow the free preview point. A new
`clampPreviewPoint()` helper clamps the VISUAL preview only -- X to
`dragMetrics.plotLeftPage`/`plotWidth` (the same bounds
`wwCursorPixelXToTime()` already applies internally), Y to the anchored
channel's own current panel rect via `ww.displayed` -- so the marker can
never visually disappear off-canvas, but this clamped Y is presentation
only and never reaches engineering state.

**Engineering authority is completely unchanged.** `onPointerUp()` is
textually unchanged from Phase 4F-UAT: it still reads `event.clientX`
only, via the same `wwCursorPixelXToTime()`, and calls the same
`wwResolveCalloutAnchorMove()` -- `event.clientY` is never consulted, at
any point, during release. `annotation.data` is never written to during
`pointermove` either way (verified: authoritative `sampleIndex`/
`anchorElapsedSeconds`/`anchorValue`/`sourceId`/`channelName`/
`boxOffset` all byte-identical throughout a wide diagonal preview drag).
Same-channel-only resolution, the nearest-full-resolution-sample
backend authority, the `/annotation-anchor` endpoint, and the
deterministic tie-break rule are all untouched -- no backend file was
modified this phase.

**Snap behavior**: on release, the marker visibly snaps from its free
preview position to the real resolved waveform sample -- verified via a
test that drags through Y positions spanning most of the mocked panel's
height (60 → 230 → 60) while holding the final X constant, and asserts
the resolved `anchorValue` exactly equals the recorded sample at that
elapsed time, never a value derived from pointer Y.

**Visual feedback**: the existing `.ww-callout-connector-group--anchor-
dragging` stronger-ring rule gained `opacity: 0.82` on both the marker
and the connector line during an active drag, so the free-floating
preview reads as a provisional unit distinct from the settled/selected
state -- no glow, no animation, cleared immediately on release.

**Failure/cancel restores the original anchor exactly** -- same
trivially-correct mechanism as Phase 4F-UAT (the preview never mutated
`annotation.data`, so restoring is just re-rendering from the
never-touched truth). Verified for forced backend failure, Escape
mid-drag (zero backend calls), and `pointercancel`.

**Tests**: extended `phase4f_check.mjs` with 7 new checks (X-only preview
moves X only, Y-only preview moves Y only, diagonal preview moves both,
authoritative data untouched throughout, connector tracks the free
preview marker at every step, active-drag visual state present during
drag and cleared after release, and a combined wide-diagonal-drag test
proving final resolution uses X alone) -- **46/46 passing** in the file
overall (39 prior Phase 4F/4F-UAT checks unchanged). Full frontend suite
reconfirmed at exactly the true 33-failure baseline across the same 14
pre-existing files (zero net new regressions). Backend: untouched,
412/412 unchanged.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this refinement specifically.

## What was done in the prior session (Phase 4F-UAT — Movable Callout Anchor, DEC-045 addendum)

**Phase 4F-UAT — Movable Callout Anchor (DEC-045 addendum).** Owner UAT
direction on top of Phase 4F below: the Callout anchor MARKER itself is
now draggable (previously only the label box was). Full detail:
[DECISIONS.md — DEC-045 addendum](DECISIONS.md#addendum-2026-08-21-refinement--callout-anchors-became-movable-same-channel-only-phase-4f-uat).

**Movement model**: same-channel only -- dragging moves the anchor to a
different sample on its OWN existing `sourceId`/`channelName`, never a
different channel, even when the pointer visually crosses another trace
in a Grouped/Custom panel. Verified directly (dragging channel B's
anchor through channel A's own screen space still resolves against B's
own recorded data). Cross-channel re-anchoring remains explicitly out of
scope, deferred to a possible future "Change Anchor Channel" design.

**Drag preview is frontend-only**: `wwWireCalloutAnchorDrag()` is wired
ONCE via event delegation on `#wwCalloutConnectorLayer` (the exact same
delegation convention `wwWireCursorDrag()` already established for A/B
cursors), so every current and future Callout is draggable with zero
per-annotation wiring. During the drag, pointer X maps to an approximate
elapsed time via `wwCursorPixelXToTime()` (reused, not reimplemented --
already clamps to `ww.viewport`), moving the marker/connector/box as a
pure visual preview; `annotation.data` is never written to during this
phase. Pointer Y is deliberately never read -- the preview Y stays
pinned to the panel's own projection of the CURRENT (still-authoritative)
`anchorValue`, so the preview can never fabricate an engineering reading.
`boxOffset` is preserved throughout (the box tracks the preview anchor
by its existing relative offset, never reset).

**Authoritative snap on release**: exactly ONE `POST .../annotation-anchor`
request fires, on `pointerup`, reusing the creation path's own request/
error/stale-response handling verbatim -- not a second implementation.
Additionally clamps against the anchored source's own `ww.sourceBounds`.
Verified directly: many `pointermove` events cause zero requests; exactly
one fires on release. On success, only `sampleIndex`/
`anchorElapsedSeconds`/`anchorValue`/`unit` are committed --
`sourceId`/`channelName`/`boxOffset` are untouched (verified byte-
identical before/after).

**Failure/cancel restores the original anchor exactly** -- trivially
correct, since the preview never mutated `annotation.data` in the first
place, so "restoring" is just `wwRenderAnnotations()` reading the
never-touched truth again. Verified for a forced backend failure, an
Escape keypress mid-drag (zero backend calls), and `pointercancel`.

**A/B cursor and Plotly coexistence confirmed isolated**: the anchor hit
target lives in a completely separate DOM subtree from both Plotly's own
canvas and A/B cursor's own hit targets -- structurally unreachable from
either, and where hit areas could visually overlap, ordinary browser
pointer-event hit-testing already provides deterministic priority with
zero extra conflict-resolution code (the connector layer stays
`pointer-events: none` everywhere except a small ~16px circle directly
over each anchor marker). Verified directly: A/B cursor dragging still
works identically, Callout anchor dragging never touches
`ww.measurementCursors`, and normal Plotly pan/zoom still works with a
Callout anchor present.

**No backend change was needed** -- the existing `.../annotation-anchor`
endpoint (Phase 4F) already accepted an arbitrary
`approximate_elapsed_seconds`, so the same endpoint serves both creation
and anchor-move requests.

**Pre-existing unrelated theme.css concern, re-checked and found
resolved**: the `--accent` edit flagged in the two prior sessions was
found FULLY committed-and-reverted by the owner (`f1354f4` then
`1653a97`, both already on `main`) -- the working tree was genuinely
clean at this task's own mandatory startup step; no preserve-and-exclude
staging was needed this time.

**Tests**: extended `phase4f_check.mjs` with a
`dragCalloutAnchorThroughTimes()` helper (targets exact elapsed times via
the app's own `wwCursorTimeToPixelX()`, not guessed pixel offsets) and
controllable delay/forced-failure hooks on the anchor-resolution fetch
mock. 16 new checks covering the task's own required list (same-channel
authority, nearest-full-resolution-sample, reduced-display independence,
one-backend-request-on-release, field-level before/after verification,
failed-resolution restoration, Escape cancellation, Absolute/Elapsed
equivalence, Annotation List refresh, box-drag isolation, A/B cursor
isolation, Plotly pan/zoom isolation, and workspace-lifecycle-during-
drag for Start New Workspace/source removal/Callout deletion) --
**39/39 passing** in the file overall. Full frontend suite reconfirmed at
exactly the true 33-failure baseline across the same 14 pre-existing
files (zero net new regressions). Backend: untouched, 412/412 unchanged.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this refinement specifically.

## What was done in the prior session (Phase 4F — Analog Waveform Callout Annotation, DEC-045)

Owner-approved direction: the second annotation type, `type: "callout"`,
reusing DEC-044's exact generic framework (`ww.annotations` remains the
sole state authority, no parallel Callout registry). Unlike `text_note`
(workspace-content-anchored), a Callout is waveform/data-anchored: one
authoritative analog sample anchor, one editable floating text box, one
connector line, one anchor marker. Full detail:
[DECISIONS.md — DEC-045](DECISIONS.md#dec-045--callout-is-a-waveform-anchored-annotation-type-analog-only-this-phase-with-a-fixed-engineering-anchor-and-a-movable-presentation-box).

**Creation UX**: `Annotate -> Callout` enters the same one-shot placement
mode Text Note already established; the next click on an analog trace
resolves the exact clicked source/channel (via each trace's own stable
`"sourceId::channelName"` `meta` field, never curveNumber alone --
verified correct for Grouped multi-trace panels, Separate lanes, and
Custom-equivalent multi-trace panels), then resolves the nearest
ACTUAL full-resolution recorded sample server-side, exactly once, via a
new focused endpoint (`POST .../sources/{source_id}/annotation-anchor`)
that reuses -- never reimplements -- the exact nearest-sample/tie-break
logic `.../cursor-values` (DEC-040) already established. A failed
resolution creates nothing (no approximate fallback, a concise error
only); a successful one enters immediate edit, exactly like Text Note.

**Anchor is fixed after creation; only the label box is draggable.** The
resolved `{sampleIndex, anchorElapsedSeconds, anchorValue, unit}` never
changes afterward -- confirmed directly unchanged across zoom, pan, Y
zoom/autoscale, and Absolute/Elapsed switching. Only the anchor's
PROJECTED screen position is recomputed on those triggers (reprojection,
never re-resolution, never a second backend call): X reuses the exact
shared `wwCursorTimeToPixelX()` authority A/B cursors already use; a new
per-panel `wwCalloutValueToPixelY()` mirrors that same technique for Y,
reading each panel's own live Plotly `_fullLayout.yaxis`. Reprojection
piggybacks on the EXACT same trigger surface `wwUpdateCursorOverlay()`
already reacts to (now calling `wwRenderAnnotations()` first,
unconditionally, so none of that function's own cursor-specific early
returns can skip it), plus a new Y-range branch in
`wwWirePanelRelayout()`'s existing relayout listener (Y zoom/autoscale
never touched X before, so A/B cursors never needed this branch) and 3
new channel-visibility call sites (add/remove/batch-remove channels).
Dragging the box updates ONLY a screen-independent `data.boxOffset` from
the anchor's own current projection (so the label tracks the anchor
through zoom/pan instead of drifting into an unrelated position with an
ever-lengthening connector) -- verified directly to cause ZERO backend
requests and ZERO `Plotly.newPlot`/`relayout`/`restyle` calls.

**Rendering**: the box lives in the SAME `#wwAnnotationOverlayMain` Text
Note boxes already occupy (native main-workspace scroll-following
preserved for free); the connector line + anchor marker render in a NEW
lightweight SVG layer, `#wwCalloutConnectorLayer`, deliberately NOT
Plotly shapes (would force a rebuild on every drag/zoom/pan). A new
`--annotation-callout-accent` token (amber family, distinct from A/B
cursor blue/red and from the note surface itself) colors both.

**Visibility, not deletion, when currently unprojectable**: a Callout
whose anchor is outside the X viewport, outside the panel's current Y
range, or whose channel isn't displayed, is hidden from canvas but stays
fully intact in `ww.annotations`/the Annotation List -- reappearing the
moment it becomes projectable again. Verified for all three cases, plus
layout-mode switching (Grouped/Separate/Custom, no duplicate boxes) and
Text Note/Callout coexistence (2 notes + 3 callouts, count=5, drawer
renders all 5 correctly with Callout's own channel/time/value metadata
line).

**Source removal deletes its Callouts outright** (not merely hides them)
-- their anchor no longer exists server-side once the source is gone,
and no other source is ever silently substituted for a same-named
channel. Clear Workspace/Start New Workspace lifecycle otherwise
unchanged from DEC-044's own established semantics.

**Backend**: `resolve_annotation_anchor()` (new,
`app/services/waveform_service.py`) reuses `_resolve_analog_channel()`/
`_nearest_sample_index()` directly rather than duplicating either; new
schema `app/schemas/annotation_anchor.py`; new route in
`app/api/v1/sources.py`. No new persistent storage.

**Pre-existing unrelated uncommitted change found and preserved**:
`frontend/theme.css`'s `--accent` token (`#3568d4` -> `#c1d5ff`) was
already modified, uncommitted, in the working tree at this task's own
mandatory startup step -- left completely untouched, not staged, not
committed, per explicit instruction; this Phase 4F commit stages only
the specific new/changed hunks it actually needed.

**Tests**: new `phase4f_check.mjs` (23/23 passing) covering the task's
own required list (anchor resolution + tie-break, reduced-display
independence, Grouped/Separate/Custom exact-trace identity, zoom/pan/
Y-zoom/Absolute-Elapsed anchor invariance, box-drag performance/offset-
only semantics, visibility rules, layout-mode reprojection, multi-type
coexistence, source removal, workspace lifecycle, safe text, pointer
isolation) plus placement-mode/menu basics; `phase4e_check.mjs`'s own
"Annotate dropdown" test updated for the new 2-item menu (36 -> 37
checks, all passing). Full frontend suite reconfirmed at exactly the
true 33-failure baseline across the same 14 pre-existing files (zero net
new regressions). Backend: 19 new tests, 412/412 passing (393 prior + 19
new), zero regressions.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this phase specifically.

## What was done in the prior session (Phase 4E-UAT2 — Free Text Notes restricted to the main waveform workspace, + a same-day annotation surface color refinement)

Owner UAT finding on the Phase 4E-UAT scroll-anchoring fix below:
placing/dragging notes over the left Workspace Sidebar was hard to
control, since the sidebar is its own interaction-heavy region
(scrolling, resizing, channel toggles). Owner decision: remove sidebar
placement for `text_note` entirely -- a deliberate UX simplification,
not a temporary workaround. Full detail:
[DECISIONS.md — DEC-044 addendum](DECISIONS.md#addendum-2026-08-21-refinement--free-text-notes-restricted-to-the-main-waveform-workspace-phase-4e-uat2).

**What changed**: `text_note` may now be placed and dragged ONLY inside
`#activeViewArea` (analog panels, digital region, shared ruler, empty
waveform workspace) -- never `#workspaceSidebar`, the toolbar, the
Annotation List drawer, or other page chrome. A click over the sidebar
while placement mode is active is a no-op (mode stays active, exactly
like a click over the toolbar already was) rather than a cancel.
Dragging toward the sidebar clamps cleanly at `#activeViewArea`'s own
left content boundary -- the SAME `wwClampAnnotationContentPosition()`
bounds check already used for every other edge does this for free, no
new boundary-detection code needed.

**Generic architecture preserved, dead complexity removed (not just
disabled)**: `ww.annotations`, ids, types, the Annotation List, editing,
dragging, deleting, and workspace/session persistence are all unchanged.
`Annotation.region` remains a generic field (kept for a possible future
annotation type with its own placement rule -- DEC-044's own
extensibility goal), but `"main"` is `text_note`'s only valid value now.
Removed entirely: `#wwAnnotationOverlaySidebar` (the DOM element, not
just its content), `wwDetermineAnnotationRegion()` (cross-region pointer
classification), the region-switching/reparenting branch of
`wwWireAnnotationDrag()`, the dual-overlay logic in
`wwRenderAnnotations()`, `#workspaceSidebar`'s annotation-only `position:
relative`, and the placement-mode crosshair cursor rule that used to
target the sidebar too.

**Existing session state**: an annotation carrying `region: "sidebar"`
from before this refinement (its overlay no longer exists in the DOM) is
coerced to `region: "main"` the next time `wwRenderAnnotations()` runs,
rather than crashing or disappearing -- a render-time safety net, not a
migration system, matching the project's own "session-local frontend
state, not a database" precedent for annotations.

**Content-scroll anchoring preserved**: a main-workspace note still
scrolls natively with `#activeViewArea`'s own content, with zero manual
JS scroll-offset compensation -- the core fix from the Phase 4E-UAT
record below is fully intact for the one remaining region.

**Same-day, separately-requested visual refinement**: the note's own
background/border switched from the generic `--panel`/`--panel-border`
tokens (which visually blended a note into the waveform panel behind it)
to new semantic `--annotation-bg`/`--annotation-border` tokens defined in
`theme.css` -- a subtle warm cream surface in Light, a muted warm dark
surface in Dark, deliberately short of a bright/saturated "sticky note"
look and never reusing A/B cursor blue/red or waveform trace colors.
Border radius, shadow, dimensions, drag/edit behavior, the Annotation
List, and the existing accent-colored selected-state border/glow are all
unchanged.

**Tests**: rewrote `phase4e_check.mjs` for the main-only model (removed
tests whose only purpose was sidebar note creation, sidebar scroll
anchoring, and sidebar<->main cross-region transfer, since that behavior
is no longer a requirement) and added the task's own required coverage
(A-O: placement in main succeeds, placement in sidebar/toolbar does
nothing, main note scrolls with main content, sidebar scroll doesn't
affect it, drag stays inside main, drag toward the sidebar clamps at the
boundary, resize keeps a note reachable, edit works after scrolling,
delete from the Annotation List works, multiple notes work, mode
switches preserve notes, Start New Workspace clears, Clear Workspace
preserves, the pointer-transparent empty overlay still allows Plotly
interactions) plus 2 new checks for the annotation color tokens -- 36/36
passing. Full frontend suite reconfirmed at exactly the true 33-failure
baseline across the same 14 pre-existing files (zero net new
regressions); `phase4d_check.mjs` (38), `phase4b_check.mjs` (44/45,
unchanged pre-existing failure), `phase4c1_check.mjs` (26),
`phase4c2_check.mjs` (24) all still pass in full. Backend: 393/393,
unchanged (no backend file touched).

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this refinement specifically.

## What was done in the prior session (Phase 4E-UAT — Annotation Scroll Anchoring fix)

Owner UAT finding on Phase 4E: floating Text Notes stayed visually FIXED
while `#workspaceSidebar`/`#activeViewArea` were scrolled, instead of
moving with the content they were placed beside. Full detail:
[DECISIONS.md — DEC-044 addendum](DECISIONS.md#addendum-2026-08-21--region-aware-content-scroll-anchoring-phase-4e-uat).

**Root cause (confirmed via direct DOM/CSS inspection before editing, per
the task's own mandatory step)**: annotation position was normalized
against `#workspaceRow`'s own STABLE bounding rect, while
`#workspaceSidebar` and `#activeViewArea` each scroll independently
(`overflow-y: auto`) — so content moved underneath a note that stayed
fixed relative to the row.

**Fix**: replaced the one shared viewport coordinate system with
REGION-AWARE CONTENT coordinates. Each annotation now carries
`region: "sidebar" | "main"` plus a RAW CONTENT-PIXEL `position: {x, y}`
measured from that region's own scrollable content origin. Two overlays
(`#wwAnnotationOverlaySidebar`, `#wwAnnotationOverlayMain`) replace the
single `#wwAnnotationOverlay`, each a genuine DOM CHILD of its own
region's scroll container (`#workspaceSidebar`/`#activeViewArea`, both
now `position: relative`; the overlay's own `overflow: hidden` was
changed to `overflow: visible` so a note positioned beyond the overlay's
own box still extends the region's native scrollable-overflow area
instead of being clipped). Result: native browser scrolling carries a
note with its region's content with ZERO manual JS scroll-offset
compensation — no scroll listener was added.

**Cross-region dragging (Option C)** still works both directions:
`wwDetermineAnnotationRegion(clientX, clientY)` classifies the live
pointer position against both regions' own `getBoundingClientRect()` on
every `pointermove`; crossing a boundary reparents the note's DOM element
into the destination overlay, updates `region`, and recomputes its
position in the new region's content-coordinate space from a
`grabOffsetX`/`grabOffsetY` captured once at drag-start (not a
delta-from-drag-start model, which would break once `offsetParent`
changes mid-drag) — no visible jump. A pointer over neither region (e.g.
the toolbar) freezes the note's region for that frame rather than losing
it or snapping into invalid space.

**Toolbar exclusion is now structural**, not computed: `#activeViewArea`
and `#wwToolbar` are siblings under `#mainWorkspace`, so a note that is a
DOM child of `#activeViewArea` can never occupy the toolbar's screen
space. `wwAnnotationToolbarRect()`/`wwAnnotationWorkAreaRect()`/
`wwClampAnnotationPixelPosition()`/`wwClamp01()` were removed entirely.

**Resize**: notes are RE-CLAMPED within their region's current
`scrollWidth`/`scrollHeight` on every render (reusing the existing
`wwResizeAllVisiblePlots()` → `wwRenderAnnotations()` hook), never
proportionally rescaled — raw content-pixel storage was chosen over
normalizing-by-scrollHeight specifically so a note never jumps when the
region's content height changes for an unrelated reason (e.g. channels
shown/hidden elsewhere in the same region). Matches the task's own stated
preference: scroll correctness over normalized-viewport elegance.

**Unchanged**: lifecycle (Clear Workspace preserves, Start New Workspace
clears), Annotation List rendering/selection/delete, XSS-safe
`.textContent` rendering, pointer isolation (`pointer-events: none` on
each overlay's empty space, `auto` on individual notes), Absolute/
Elapsed and Grouped/Separate/Custom independence. Auto-scroll while
dragging near a region's edge remains explicitly out of scope.

**Tests**: reconfirmed the TRUE baseline directly against `main` before
starting (33 pre-existing failures across the same 14 files, not the
stale "18"). Rewrote `phase4e_check.mjs`'s position-model assumptions and
added new checks for sidebar/main scroll anchoring, independent scroll
between regions, horizontal scroll, cross-region drag both directions
(region/DOM-parent transfer, no coordinate jump, frozen-region-over-
toolbar), resize re-clamp without proportional rescale (including after a
scroll), delete/edit/drawer-selection after a scroll, and both region
overlays' pointer transparency — 39/39 passing. Full frontend suite
reconfirmed at exactly the true 33-failure baseline (zero net new
regressions); `phase4d_check.mjs` (38), `phase4b_check.mjs` (44/45,
unchanged pre-existing failure), `phase4c1_check.mjs` (26),
`phase4c2_check.mjs` (24) all still pass in full. Backend: 393/393,
unchanged (no backend file touched).

**chrome-extension://invalid investigation (owner-reported, alongside
this fix)**: owner saw `HEAD chrome-extension://invalid/ net::ERR_FAILED`
in the browser console during UAT. Exhaustive static-analysis search of
the entire canonical frontend found: zero occurrences of the literal
string `chrome-extension` anywhere in `frontend/index.html` or any
`frontend/*.js`/`*.css`; zero `XMLHttpRequest` usage; the one `new URL(`
call site and all 9 `fetch(` call sites are backend-API-scoped via
`apiBaseUrl()`, which can never produce an extension-scheme URL; only 4
static same-origin `src=`/`href=` references in the whole document with
zero dynamic JS assignment; the `<head>` block has no favicon/manifest/
icon reference that could trigger an independent resource probe. The
console error's own cited line is `event.stopPropagation()` inside the
annotation-edit textarea's `keydown` handler — unrelated to any
network/URL code. Conclusion: Oruxa application code is NOT responsible;
this bears the well-known signature of a browser-extension/devtools
artifact (an extension's own content script running with an invalidated
runtime context). **No Oruxa code was changed to suppress it**, per the
task's own explicit instruction. Live incognito-vs-normal-browser
reproduction (the investigation's own step 4) could not be performed —
no browser automation capability exists in this sandboxed CLI
environment; the owner should verify seeing this in a clean profile with
extensions disabled, since only they have the browser session where it
was observed.

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this fix specifically.

## What was done in the prior session (Phase 4E — Annotation Framework + Free Text Note)

Full detail:
[MIGRATION_PLAN.md — Phase 4E Record](MIGRATION_PLAN.md#phase-4e--annotation-framework--free-text-note-2026-08-20),
[DECISIONS.md — DEC-044](DECISIONS.md#dec-044--generic-annotation-framework-first-type-is-a-workspace-scoped-work-area-relative-free-text-note).

**Small cosmetic follow-up landed between Phase 4D and this phase, same
day**: commit `42c5f2c` ("ui: match cursor icon to A/B colors") -- the
A/B Time Cursors toolbar icon's two lines/letters now use
`var(--accent)`/`var(--error)`, the SAME tokens the real waveform cursor
lines already use, instead of generic `currentColor`. No functional
change; not separately documented beyond this note and its own commit
message (a narrowly-scoped owner request with no governance-doc
requirement attached).

**Owner direction (Phase 4E)**: the first annotation capability -- a
GENERIC framework (future types: callout notes, event/channel markers,
delta/RMS/peak/amplitude stamps), with only `text_note` implemented this
phase. `Annotate -> Text Note` enters one-shot placement mode; one click
in the permitted analysis area creates a note, which enters edit mode
immediately; notes are draggable, editable, and deletable (centrally,
via a new Annotation List drawer).

**DOM investigation before implementing (per the task's own mandatory
step)**: found the toolbar and the Workspace Sidebar occupy the SAME
vertical band (toolbar is only the top strip of the `#mainWorkspace`
column, beside the sidebar) -- resolved by checking `#wwToolbar`'s own
live rect at click/drag time rather than a CSS clip-path (the toolbar's
height isn't fixed, it wraps at narrow widths per Phase 4D's own
`flex-wrap`). Also found `#workspaceSidebar` and `#activeViewArea` are
TWO INDEPENDENTLY-scrolling containers (`overflow-y: auto` on both,
confirmed via their own CSS) -- this created real tension between the
task's "preferred" scroll-following behavior and its "seamlessly
draggable between sidebar and main area" requirement (which wants ONE
shared coordinate system). Resolved as a documented, disclosed tradeoff
(see below), not a silent shortcut.

**Placement area: Option C (sidebar + main area, never the toolbar) WAS
achieved** -- one overlay (`#wwAnnotationOverlay`, a child of
`#workspaceRow`) plus an explicit toolbar-rect-exclusion check (not a
geometric cutout) in the placement-click handler and the shared drag/
render clamp function. A note drags seamlessly between the sidebar and
main area with zero special-casing, since both share one coordinate
system.

**Position model**: normalized `{x, y}` (0..1) relative to
`#workspaceRow`'s own STABLE (never-scrolling) bounding rect --
deliberately NOT waveform/data-anchored (zoom/pan/Absolute-Elapsed/
Grouped-Separate-Custom never move a note; that's reserved for a future
`callout_note` type). **Documented limitation, flagged for owner UAT**:
notes do NOT scroll with `#workspaceSidebar`'s/`#activeViewArea`'s own
internal content -- true scroll-following was evaluated and found to
need either mid-drag DOM re-parenting between two different scroll
containers or manual dual-`scrollTop` tracking, both meaningfully more
complex than verifiable without live-browser testing in this sandboxed
environment. The chosen model still fully satisfies workspace/session
persistence and cross-region dragging with one simple coordinate system.

**Text Note**: `wwBeginAnnotationEdit()`/`wwEndAnnotationEdit()` swap the
read-only body `<div>` for a `<textarea>` in place -- single click
selects/brings-to-front (monotonic `zIndex` counter), double-click on
the body edits, blur commits, Escape reverts (never Enter-as-save, so
multiline notes work naturally). Dragging wired on the header (always)
and body (only while not editing), mirroring the project's own
established `wwWireResizeHandle()` pointer-capture pattern; the active
textarea itself never initiates a drag. Text wraps (`pre-wrap` +
`break-word`) inside a 160-320px note, no giant shadow, no bright
palette.

**Annotation List drawer**: a right-side `position: fixed` OVERLAY (never
consumes/reflows `#workspaceRow`'s own width, so it can never distort
normalized positions) -- no existing right-drawer precedent in this
codebase, so this is new, using the same theme tokens as every other
panel. Fully generic: `wwAnnotationCategoryLabel()`/
`wwAnnotationSummary()` dispatch on `annotation.type`, never hard-wired
to `text_note`'s own shape -- a future type needs one more dropdown menu
item plus a branch in those two functions, nothing else. Newest-first
ordering (deliberate, documented). Delete is centralized there (trash
icon, appropriate since it genuinely deletes) with no confirmation
dialog and no permanent × on the floating note itself, both per the
owner's own explicit instructions.

**Lifecycle**: annotations are PRESERVED by the plain "Clear workspace"
button (confirmed via direct inspection of `wwClearWorkspace()`'s
existing code -- it already preserves A/B cursor state via the same
`if (options.resetSourceBounds)` branch, for the identical "still the
same session/source context" reasoning; annotations follow that exact
precedent) and CLEARED only by "Start New Workspace" (confirmed to
rotate `WORKSPACE_STORAGE_KEY` to a genuinely new UUID before calling
`wwClearWorkspace({resetSourceBounds:true})`).

**Security**: text renders via `.textContent` only, never `.innerHTML`
with user text interpolated -- verified directly that
`<script>...</script><b>hello</b>` entered as note text renders as inert
plain text in both the note and the drawer preview, no execution.

**Tests**: determined the TRUE current baseline directly against `main`
before starting (unchanged from Phase 4D's own verified 33 failures
across 14 pre-existing files, not the stale "18"). New
`phase4e_check.mjs` (28 checks) covering placement mode + Escape cancel +
toolbar/outside-click rejection + sidebar placement, multiple notes,
edit sync, drag + bounds/toolbar clamping, resize repositioning, delete,
mode/navigation persistence, Clear-Workspace-preserves vs.
Start-New-Workspace-clears, pointer isolation (Plotly relayout handler
and sidebar row toggle both still fire normally with the overlay
present), XSS-safe rendering, and drawer open/close/order/selection.
Full frontend suite reconfirmed at exactly the true 33-failure baseline
(zero net regressions); `phase4b_check.mjs` (44/45, unchanged
pre-existing), `phase4c1_check.mjs` (26), `phase4c2_check.mjs` (24), and
`phase4d_check.mjs` (38) all still pass in full. Backend: 393/393,
unchanged (no backend file touched).

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this phase specifically (including the disclosed
scroll-following limitation above).

## What was done in the prior session (Phase 4D — Precision Step Zoom + Icon Toolbar Refinement)

**Phase 4D — Precision Step Zoom + Icon Toolbar Refinement.** Full detail:
[MIGRATION_PLAN.md — Phase 4D Record](MIGRATION_PLAN.md#phase-4d--precision-step-zoom--icon-toolbar-refinement-2026-08-20),
[DECISIONS.md — DEC-043](DECISIONS.md#dec-043--precision-step-zoom-x-step-is-workspace-global-y-step-is-active-panel-local-waveform-toolbar-is-icon-primary).

**Pre-work finding, important for the next session**: two commits had
landed on `main` since the last Phase 4C2 session, authored elsewhere,
not by this session -- `cfdfb3a` (DEC-041, waveform adaptive resolution)
and `915111c` (DEC-042, sub-ms Absolute-time precision -- Plotly X
coordinates are now numeric elapsed seconds in BOTH time modes,
`wwElapsedToPlotlyX()`/`wwPlotlyXToElapsed()` are now identity
functions). Both were read in full before writing any Phase 4D code.
Also discovered while establishing the regression baseline: the
previously-tracked "18-failure" figure was stale -- those two commits'
own architecture changes broke several OLDER verification scripts'
pre-DEC-041/042 assumptions. **The TRUE current baseline, verified
directly against `main` before this phase started, is 33 failures across
14 files** (`phase2cb1/cb2/cb3/cb3a`, `phase2cc2/cc3/cc4/cc4a`, `phase3a`,
`phase3auat1/auat3`, `phase3b`, `phase3buat3/buat4`, `phase4b`) -- treat
33, not 18, as the baseline to preserve going forward.

**Owner direction**: (1) add precise ~20% step Zoom In/Zoom Out for X and
Y as two split buttons (never four permanent X+/X-/Y+/Y- buttons); (2)
convert the toolbar's major text controls to SVG icons. No engineering
behavior of any existing control changed.

**X step zoom** (`wwStepZoomX()`): workspace-global -- reuses
`ww.viewport`/`ww.workspaceBounds` and the exact same
`wwApplyAndFetchViewport()` authority every other X-viewport change
already uses, so DEC-041's adaptive-resolution fetch genuinely re-runs
(verified: a sub-10,000-sample zoom switches a channel's own
`representation` to `full_resolution`; a broad range stays
`min_max_envelope`) -- never a bare Plotly relayout of stale data. Every
panel/digital/ruler move together; A/B cursor engineering time is
provably unchanged (only pixel projection moves). Zoom Out uses a NEW
dedicated clamp, `wwClampZoomWindowToWorkspace()` (deliberately separate
from the pre-existing `wwClampRangeToWorkspace()`, unchanged, still used
by drag-zoom/pan) that SHIFTS the window to preserve the requested span
near a workspace edge instead of asymmetrically truncating it; becomes a
genuine no-op (no refetch, button `disabled`) at full workspace range.

**Y step zoom** (`wwStepZoomY()`): ACTIVE-PANEL-LOCAL only -- new
`wwActivePanel()`/`ww.activePanelGroupKey` concept. Click (not hover) on
a panel's HEADER establishes authority; a subtle `.ww-panel--active`
border-accent shows which one; self-heals across a Grouped/Separate/
Custom layout switch (falls back to the first current panel when the
remembered key no longer matches any live panel) so it can never target
a destroyed/purged Plotly instance. Reads/writes Plotly's own resolved
`_fullLayout.yaxis.range` directly, taking the panel out of autorange.
Autoscale Y is UNCHANGED, still global across every panel (the one action
that restores autorange).

**Split-button dropdown**: `ww.zoomStepAxis = {in: "x", out: "x"}` --
remembered SEPARATELY per action (owner's own primary recommendation over
a shared axis). Choosing an axis from the dropdown menu both remembers it
AND performs that exact step immediately; every later main-icon click
repeats the same axis with zero further dropdown interaction. Full
keyboard support (Tab/Enter/Escape/focusout-closes) and click-outside/
mutual-exclusivity between the two split buttons' own menus.

**Icon toolbar**: reused the EXISTING `#mainSidebarMenu` `.shell-nav-icon`
visual language verbatim (`viewBox="0 0 18 18"`, `stroke="currentColor"`,
`fill="none"`, 1.5 stroke-width, round linecap/join) -- no external icon
library introduced. Every icon-only control keeps `title`+`aria-label`.
Box Zoom/Zoom In/Zoom Out share one magnifier base (+/- added inside the
lens for the two step actions); Pan is a minimal open-hand glyph;
Absolute/Elapsed are a clock/stopwatch segmented pair; Reset Time
View/Autoscale Y are a matched horizontal/vertical fit-to-extent arrow
pair; A/B Time Cursors is two lines with small in-SVG "A"/"B" `<text>`
glyphs (the one deliberate text exception, task-permitted); Grouped/
Separate/Custom are a filled-panel-with-traces / stacked-lanes /
asymmetric-grid trio; Clear Workspace is an eraser (not a trash icon).
Grouped into Navigation/Zoom step/Time/View/Measurement/Layout/Workspace
clusters via thin `.ww-toolbar-sep` separators.

**Tests**: new `phase4d_check.mjs` (38 checks) covering X step math +
clamp + round-trip + min-span floor, X global sync, adaptive-resolution
representation switching, active-panel click/keyboard selection, Y step
isolation between panels + active-panel redirection + min-span floor,
layout-mode active-panel remapping (never a destroyed panel), Autoscale Y
still global, icon-toolbar text removal + tooltip/aria-label presence,
existing mode-state preservation, and the full split-button dropdown
lifecycle. Two pre-existing tests were updated because Phase 4D's own
intended changes made their STRICT assertions stale (not regressions,
confirmed via `git stash` comparison both ways): `phase2cc1_check.mjs`'s
`textContent === "Custom"` check (now checks title/aria-label) and
`phase2cb3a_check.mjs`'s `className === "ww-panel"` check (now
`classList.contains`, since the active panel now also carries
`ww-panel--active`). Also fixed a pre-existing, unrelated gap discovered
along the way: `phase4b_check.mjs` had been silently crash-truncating
after 2 checks since the Phase 4C1 session (a missing `/cursor-values`
mock) -- patched so its own 45 checks genuinely run again (44 pass; the
one remaining failure is a DEC-042-era pre-existing mismatch, confirmed
via stash comparison to predate Phase 4D, left untouched as out of
scope). Full frontend suite reconfirmed at exactly the TRUE 33-failure
baseline (zero net regressions); `phase4c1_check.mjs` (26) and
`phase4c2_check.mjs` (24) both still pass in full. Backend: 393/393,
unchanged (no backend file touched).

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this phase specifically.

## What was done in the prior session (Waveform Time-Axis Sub-ms Precision)

**Waveform Time-Axis Sub-ms Precision.** Full detail:
[MIGRATION_PLAN.md — Waveform Time-Axis Sub-ms Precision](MIGRATION_PLAN.md#waveform-time-axis-sub-ms-precision-2026-08-20),
[DECISIONS.md — DEC-042](DECISIONS.md#dec-042--absolute-and-elapsed-waveform-modes-share-numeric-elapsed-plotly-x-coordinates).

Owner approved the follow-up from the Absolute-Time precision investigation.
The problem was proven frontend-only: adaptive resolution and backend range
extraction already returned full-resolution data for the observed 5 kHz
deep-zoom range, but Absolute mode converted elapsed samples into
millisecond-formatted date strings before Plotly received them. At 5 kHz, that
collapsed five 0.2 ms samples into each 1 ms X coordinate while keeping
distinct Y values, producing stepped/vertical geometry.

Implemented the approved model: Absolute and Elapsed modes now share numeric
elapsed Plotly X coordinates. `wwElapsedToPlotlyX()` and
`wwPlotlyXToElapsed()` are identity helpers; panel and digital axes are linear
numeric elapsed seconds in both modes; `wwSetTimeMode()` updates
hover/customdata and axis presentation only, with no trace X/Y rewrite and no
waveform refetch; Absolute ticks/hover/cursor labels format
`recording_start + elapsed` with viewport-aware sub-ms precision; the sticky
ruler keeps the same elapsed coordinate domain and changes labels/title only.
Backend requests, sourceBounds/workspaceBounds/viewport, adaptive resolution,
digital transitions, Cur A/B values, and cross-source semantics are unchanged.

Focused verification for this pass:
`backend/tests/test_waveform_service.py`,
`backend/tests/test_waveform_reduction.py`,
`backend/tests/test_cursor_values_service.py`,
`backend/tests/test_cursor_values_api.py`,
`backend/tests/test_frontend_source_bounds.py`,
`backend/tests/test_frontend_waveform_adaptive_resolution.py`, and
`backend/tests/test_frontend_absolute_time_precision.py` — 106/106 passing.

Permanent coverage added in
`backend/tests/test_frontend_absolute_time_precision.py` for identity
coordinate conversion, no date-axis/date-string Plotly coordinates, no trace
geometry rewrite on mode switch, 5 kHz 76/76 unique-X preservation,
sub-millisecond Absolute label precision tiers, and sticky-ruler numeric-domain
behavior.

## What was done in the prior session

**Waveform Adaptive Resolution.** Full detail:
[MIGRATION_PLAN.md — Waveform Adaptive Resolution](MIGRATION_PLAN.md#waveform-adaptive-resolution-2026-08-20),
[DECISIONS.md — DEC-041](DECISIONS.md#dec-041--waveform-reduction-is-an-overview-rendering-optimization-with-a-10000-sample-full-resolution-display-threshold).

Owner approved the zoom-resolution follow-up after the analysis-only
investigation. Implemented the rule: waveform reduction is an overview
rendering optimization only; requested analog ranges containing `<= 10,000`
original samples per channel now return the complete original sample sequence
for display. Ranges above that threshold remain peak-preserving min/max
display representations. The backend owns the exact sample-count threshold via
`FULL_RESOLUTION_DISPLAY_THRESHOLD = 10_000`; frontend request budgets for
reduced ranges are now pixel-aware (`plot_width_px * 4`, clamped
`4000..20000`) using actual Plotly plot-domain width when available, not
browser/window width.

Expected 5 kHz behavior is now covered permanently: 7.0 s / 35,001 samples
and 3.0 s / 15,001 samples are reduced; 1.0 s / 5,001 samples, 100 ms / 501
samples, 20 ms / 101 samples, and 5 ms / 26 samples are full-resolution.
Backend full-resolution authority, sourceBounds/workspaceBounds/viewport,
Absolute/Elapsed elapsed-range semantics, Cur A/B value authority, digital
cursor state, digital transition rendering, and COMTRADE parsing were not
changed. Focused verification at implementation time:
`backend/tests/test_waveform_service.py`,
`backend/tests/test_waveform_reduction.py`,
`backend/tests/test_cursor_values_service.py`,
`backend/tests/test_frontend_source_bounds.py`, and
`backend/tests/test_frontend_waveform_adaptive_resolution.py` — 82/82
passing.

Full in-repo verification for this pass: backend `pytest` 385/385 passing;
committed frontend/static regression subset `pytest backend/tests/test_frontend_*.py`
35/35 passing; `git diff --check` clean before commit.

## What was done in the prior session (Phase 4C2 — Digital A/B Cursor State)

**Phase 4C2 — Digital A/B Cursor State.** Full detail:
[MIGRATION_PLAN.md — Phase 4C2 Record](MIGRATION_PLAN.md#phase-4c2--digital-ab-cursor-state-2026-08-20),
[DECISIONS.md — DEC-040's second addendum](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1).

**Owner direction**: extend Phase 4C1's A/B cursor channel values to
digital channels -- every displayed digital channel shows its recorded
state (0/1) at Cursor A/B, as compact inline "A:0 B:1" badges (Detego-
style) appended to the existing Channel cell, explicitly NOT a full-width
Cur A/Cur B table column like analog's own.

**Investigation first, per the task's own explicit instruction**:
inspected `app.providers.comtrade._build_dataframe`/
`extract_digital_waveform` before choosing an implementation. Confirmed
digital channels live in the SAME dense, per-sample `waveform_data`
DataFrame as analog, sharing the identical `"time"` column --
`extract_digital_waveform`'s own sparse transition list is DERIVED
(`np.diff`) from that same dense array for compact wire transfer, not a
second source of truth. This meant digital state could reuse Phase 4C1's
existing `_nearest_sample_index()` unchanged, with NO separate
transition-interval-search algorithm needed -- and the owner's own
exact-transition-timestamp rule ("state at T = the NEW state beginning at
T") falls out for free from a plain nearest-sample read, since the
recorded sample AT a transition's own timestamp already holds the new
state by construction.

**Backend**: same endpoint (`POST .../sources/{source_id}/cursor-values`,
no new route) -- `extract_cursor_values()` extended to accept
`digital_channel_names` alongside the renamed `analog_channel_names` (was
`channel_names`, a clean rename for symmetry/type clarity -- internal-only
API, no back-compat shim per this project's own convention), resolving
BOTH kinds from the SAME two already-computed nearest-sample indices per
source. New `DigitalChannelCursorState` dataclass/
`DigitalChannelCursorStateOut` schema (plain `int | None`, no `unit`).
19 new tests (12 service-level incl. the exact-transition-timestamp rule
on both rising/falling edges, static-state/bounds/multi-source-isolation/
classification-preservation coverage; 7 API-level using synth_ascii's own
real `BRK_A`/`BRK_B` channels, hand-verified anchor at t=0.005s); full
suite 374/374 passing.

**Frontend**: new `ww.digitalCursorValues` -- a DELIBERATELY separate Map
from analog's `ww.cursorValues` (never shared key space, so an analog
`0.0` and digital `0` can never collide despite reusing the identical
`wwChannelKey()` shape). `wwFetchCursorValuesForSource()` (Phase 4C1's
own function) now gathers both displayed analog AND digital channel
names for a source and sends them in ONE combined request -- a source
with both kinds displayed still costs exactly one request. Hooked into
digital's own existing "core mutation" functions
(`wwAddDigitalChannels()`/`wwRemoveDigitalChannelByKey()`/
`wwRemoveDigitalChannelsByKeys()`/`wwRemoveChannelsForSource()`'s digital
branch), mirroring Phase 4C1's analog hook pattern exactly -- no new hook
points invented. Mode OFF/individual cursor closed/drag throttling/
stale-response protection all REUSE Phase 4C1's existing shared
mechanisms (`wwCursorValuesHandleModeDisabled()`/
`wwCursorValuesHandleCursorClosed()`/`wwScheduleCursorValuesRefresh()`/
the per-source generation counter) -- extended to also touch digital
state, never a second parallel mechanism. Badges: `digitalChannelNameCellHtml()`
appends `wwDigitalCurBadgeHtml()` inside the existing `.channel-name-cell`
flex row (`margin-left: auto` pushes it right) -- no new `<td>`, no new
digital table column. Neutral styling only (`--surface-tint`/
`--panel-border`/`--text-dim`, never `--ok`/`--error` -- digital
semantics vary by signal, 0/1 must never imply healthy/alarm).
Triggered/Never Triggered/Spare classification (DEC-034) completely
unread/unaffected.

**Verification**: new `phase4c2_check.mjs` (24 checks) covering sidebar
structure (confirmed no new table column), all gating conditions,
100-channel batch efficiency, combined analog+digital single-request
batching, cross-source non-collision (via the pure `wwDigitalCurStateText()`
gating function, since selecting a source replaces the sidebar's rendered
rows with that source's own channels only -- DOM row lookups alone can't
verify cross-source cache isolation), drag-throttle reuse (dragging
across a real 0->1 transition, verified against an analog panel's
geometry since cursor dragging needs a rendered Plotly surface to project
pixel position from, per DEC-039), layout-mode/Absolute-Elapsed
independence, classification-group preservation, source-switch/Start-New-
Workspace clearing, zero-channels no-request behavior, error handling,
and full Phase 4C1 (analog) preservation. Full frontend regression suite
reconfirmed at exactly the established 18-failure baseline; Phase 4C1's
own `phase4c1_check.mjs` (26 checks) still passes fully after updating
its mock to the renamed request field (`channel_names` ->
`analog_channel_names`, `digital_channels: []` added to every mocked
response).

**Not yet done**: commit/push, CI/automatic DEV deployment verification,
and owner UAT of this phase specifically.

## What was done in the prior session (Phase 4C1 — A/B Cursor Channel Values (Cur A / Cur B))

**Phase 4C1 — A/B Cursor Channel Values (Cur A / Cur B).** Full
detail:
[MIGRATION_PLAN.md — Phase 4C1 Record](MIGRATION_PLAN.md#phase-4c1--ab-cursor-channel-values-cur-a--cur-b-2026-08-20),
[DECISIONS.md — DEC-040](DECISIONS.md#dec-040--ab-cursor-channel-values-are-computed-from-authoritative-full-resolution-source-data-at-the-nearest-actual-sample-agnostic-to-channel-semantics-phase-4c1).

**Owner direction**: the first VALUE measurement built on the DEC-039
A/B cursor-time overlay — show each displayed analog channel's recorded
Y-axis value at Cursor A and Cursor B in the Channels sidebar, as compact
"Cur A"/"Cur B" columns. **Same-day owner clarification**: the original
"Instantaneous Cursor Values" working title was too restrictive -- Cur
A/B is a GENERIC channel Y-axis value, agnostic to what the channel
represents (instantaneous, RMS, frequency, power, etc. -- it simply
reads that channel's own recorded sample). A dedicated code audit
confirmed this was already the actual behavior; only terminology/docs
were corrected, no production code changed (see the DEC-040 addendum).
Explicitly out of scope this phase: CALCULATED RMS/angle (deriving a new
value from an instantaneous waveform, as opposed to reading a
already-RMS channel's own recorded value), delta angle, ΔY,
interpolation, on-canvas annotations, digital-at-cursor, cross-source
sync, resampling, and phasor calculation, all deliberately deferred.
Hard engineering-integrity rule from the task spec: values must always
come from the authoritative full-resolution source data at the nearest
ACTUAL sample — never from a Plotly trace, a downsampled/peak-preserving
display representation, or interpolation.

**Backend** (new): `extract_cursor_values()` +
`CursorPointResult`/`ChannelCursorValues`/`CursorValuesResult`
(`app/services/waveform_service.py`) with `_nearest_sample_index()`
(binary-search nearest-sample, documented earlier-sample tie-break,
bounds check before the search — a cursor time outside a source's own
bounds returns `null`, never clamped). New
`app/schemas/cursor_values.py`. New batched route,
`POST /api/v1/workspaces/{workspace_id}/sources/{source_id}/cursor-values`
(`app/api/v1/sources.py`) — one request per source, both cursors' nearest
indices computed once and reused across every requested channel; unknown/
non-analog channel names are silently skipped (a deliberate departure
from `extract_digital_waveform`'s all-or-nothing precedent, for
live-dragging reliability). 27 new backend tests (18 service-level
covering nearest-sample/tie-break/bounds/multi-rate/full-resolution-
authority, 9 API-level covering the real upload→cursor-values flow and
source-identity non-collision); full suite 355/355 passing.

**Frontend** (`frontend/index.html` only): new `ww.cursorValues` cache
(`Map<"sourceId::channelName", {aValue, bValue, aSampleTime,
bSampleTime}>`) — pure derived state; `ww.measurementCursors` (DEC-039)
remains the one cursor-TIME authority, only ever read here.
`wwCurValueText()` is the single gating+formatting function every render
path goes through (mode off / that cursor closed / channel hidden all
force "—" regardless of cache contents — defense in depth).
`wwFormatEngineeringValue()` gives adaptive formatting (1 decimal for
|value| >= 1, 3 decimals for [0.001, 1), exponential below that) matching
every owner-supplied worked example exactly. Sidebar analog table
extended Channel/Phase -> Channel/Phase/Cur A/Cur B
(`renderChannelTable()` gained an optional per-column `className`).
Batching: `wwFetchCursorValuesForSource()`/`wwFetchAllCursorValues()`
issue exactly one POST per source for every currently-displayed analog
channel — hooked into the existing "core mutation" functions
(`wwAddSelectedChannels()`, `wwRemoveChannel()`,
`wwRemoveChannelsByKeys()`) so both individual row toggles and group
Show-all/Hide-all get correct batched behavior with no extra hook needed.
Live drag: `wwScheduleCursorValuesRefresh()` is a leading+trailing
~50ms throttle coalescing rapid pointermoves into far fewer backend
requests (the visual line itself stays unthrottled, per DEC-039);
`pointerup` always issues one final unthrottled request; a per-source
generation counter discards stale in-flight responses. Clear points:
mode disabled, individual cursor closed, channel hidden (single or
batched-group removal), source switch/reinit, and Start New Workspace —
never let a stale/previous-source value leak into what's rendered.
Digital sidebar deliberately unchanged (no Cur A/B columns there this
phase).

**Verification**: new `phase4c1_check.mjs` (26 checks, scratch
convention) covering numeric formatting, all four gating conditions
(mode off/cursor closed/channel hidden/both), batching (20-channel group
Show-all -> exactly one request), source identity and bounds across two
sources (no collision, no cross-source clamping), drag throttling and
stale-response protection, layout-mode independence
(Grouped/Separate/Custom identical values), Absolute/Elapsed and
zoom/pan non-refetch, source-switch and Start New Workspace clearing,
zero-channels no-request behavior, request failure handling, and
digital-sidebar non-interference. `CSS.escape()` (used by the new
targeted-cell-update code) is a real, universally-supported browser API
that jsdom simply does not implement -- a `window.CSS.escape` polyfill
was added to every scratchpad harness's `buildDom()` (test-only, no
production code change) once this surfaced as `ReferenceError: CSS is
not defined` across several older suites. Full frontend regression suite
reconfirmed at exactly the established 18-failure baseline (two
pre-existing Phase 4A-UAT4/UAT5 column-count assertions were updated in
place to expect the new 4-column analog table — this phase's own
intended change, not a regression).

**Update (Phase 4C2 session, 2026-08-20)**: Phase 4C1 was committed and
pushed as two commits -- `3da102f` ("feat: add instantaneous A B cursor
values") and `b7245d8` (the terminology-clarification docs follow-up).
Both confirmed CI-green and DEV-deployed (backend `/health` `git_sha` and
frontend `buildVersion` both matched `b7245d8` exactly at verification
time). The line below is superseded by this update, retained for the
historical record of what was true when originally written.

**Not yet done** *(as originally written, now superseded above)*:
commit/push (six local commits, `9080aa9`..`7b14e4f` for Phase 4B through
UAT3, are already confirmed pushed/CI-green/DEV-deployed at `7b14e4f` —
see the prior-session note below; only this Phase 4C1 work itself remains
uncommitted), CI/automatic DEV deployment verification of the Phase 4C1
commit specifically, and owner UAT.

## What was done in the prior session (Phase 4B — A/B Time Measurement Cursors, incl. cosmetic refinement + UAT1/UAT2/UAT3)

**Phase 4B — A/B Time Measurement Cursors.** Full detail:
[MIGRATION_PLAN.md — Phase 4B Record](MIGRATION_PLAN.md#phase-4b--ab-time-measurement-cursors-2026-08-19),
[DECISIONS.md — DEC-039](DECISIONS.md#dec-039--ab-time-measurement-cursors-are-one-workspace-level-dom-overlay-over-the-shared-elapsed-time-domain-never-a-per-panel-plotly-shape-phase-4b).

**Owner direction**: the first dedicated measurement feature -- two
draggable, workspace-level A (blue)/B (red) TIME cursors spanning the
entire waveform workspace (every analog panel, the digital region, and
the shared time ruler), with a live A/B/Δt readout. Mid-task
clarification: cursor state must be GLOBAL across Grouped/Separate/Custom
(never per-layout), and layout switching must only recompute pixel
projection, never the stored engineering time.

**What changed** (`frontend/index.html` only): new `ww.measurementCursors
= { enabled, a: {visible, time}, b: {visible, time} }` state, storing
elapsed engineering seconds in the exact same coordinate system as
`ww.viewport`/`ww.workspaceBounds` (DEC-037) -- never pixels. Rendered as
ONE workspace-level DOM overlay (`#wwCursorOverlay`, absolutely positioned
inside `.workspace-section`, height computed to reach exactly the ruler's
top edge) plus a second segment nested inside `#wwStickyRuler` itself
(`#wwCursorRulerOverlay`, inheriting that element's own `position: sticky`
automatically) -- never a Plotly `layout.shapes` entry per panel. Both
segments read pixel geometry from a real rendered Plotly surface's own
`_fullLayout.xaxis._offset`/`_length` (`wwCursorPlotMetrics()`, the same
technique `wwDiagnoseDigitalAlignment()` already established in Phase
4A-UAT2), so they stay pixel-aligned with every panel/the ruler with no
guessed offsets. New compact `#wwCursorModeBtn` toggle lives inside the
existing `#wwToolbar` (so it naturally follows the toolbar's own
show/hide-when-empty gate); new A/B/Δt readout sits at the right edge of
the bottom status bar via a flex spacer.

Dragging is pointer-capture on a wide invisible hit strip or the compact
"[A ×]"/"[B ×]" label, with plot metrics cached once at drag-start --
every pointermove is a `style.left`/textContent write only, never a
Plotly redraw or waveform fetch. First activation places A/B at 1/3 and
2/3 of the current viewport; toggling the toolbar mode OFF then ON within
the same source restores prior positions (including un-hiding an
individually-closed cursor) rather than reinitializing. A genuinely new
source selection reuses `wwRefreshWorkspaceBounds()`'s own existing
"fresh viewport" signal (DEC-037) to reinitialize A/B to 1/3-2/3 of the
NEW source -- re-selecting the same already-open source does not, and
"Start New Workspace" resets cursor state completely while the plain
"Clear workspace" button leaves it alone. A cursor outside the current
viewport is explicitly hidden rather than silently relocated, and
reappears at its exact original time once the viewport includes it again
(zoom back out / Reset Time View). Absolute/Elapsed switching changes
only the A/B text (new `wwFormatCursorPointTime()`, reusing the existing
`wwFormatPlotlyDateString()` naive-UTC formatter for Absolute), never the
underlying time; Δt uses a new, dedicated three-tier (µs/ms/s, signed)
`wwFormatCursorDuration()` -- deliberately separate from the ruler's own
axis-formatting functions, which answer a different question (configuring
an entire Plotly axis, not formatting one scalar duration as text). Cursor
mode works even with zero displayed channels (the readout only needs
`ww.viewport`; the visual line additionally needs a rendered plotting
surface, so it just stays undrawn until one exists, never approximated).
A reuses the existing `--accent` theme token, B reuses `--error` -- both
already theme-aware, no new hard-coded colors.

**Verification**: new dedicated `phase4b_check.mjs` (22 checks, scratch
convention) covering activation/1/3-2/3 init (including with zero
channels displayed), the one-overlay-not-per-panel structural guarantee,
dragging (time update/no refetch/edge clamping), zoom/pan preserving
cursor time with correct off-screen/reappear behavior, individual close
and the OFF->ON restore path, adaptive formatting and signed Δt,
Absolute/Elapsed presentation-only, the owner's own Grouped->Separate->
Custom->Grouped global-persistence scenario, digital continuity,
default-hidden non-interference, and source-switch reinit vs.
same-source-reselect non-reinit. Adding `#wwCursorRulerOverlay` as a
second child of `#wwStickyRuler` made one PRE-EXISTING
`phase2cc4a_check.mjs` check's "ruler wrapper has exactly one child"
assertion obsolete (an intentional, foreseeable consequence of this
phase's own architecture -- the title/date-context elements that check
actually guards against are still confirmed absent) -- updated
accordingly. Full frontend regression suite reconfirmed back to exactly
the established 18-failure baseline both by direct count and by
`git stash`-comparing against canonical pre-Phase-4B `frontend/index.html`
(the same 9 files/18 failures were already failing beforehand). Backend:
328/328 passed, unchanged (no backend file touched).

**Fully completed and owner-UAT'd.** Committed, pushed, CI green, automatic
DEV deployment verified live at the deployed SHA (`9080aa9`). Owner
confirmed all Phase 4B UAT checks passed in a real browser.

**Post-UAT cosmetic refinement (same day)**: owner requested two small,
purely visual follow-ups on top of the already-approved architecture above
-- see
[MIGRATION_PLAN.md — Phase 4B Cosmetic Refinement Record](MIGRATION_PLAN.md#phase-4b-cosmetic-refinement--thinner-ab-lines--range-highlight-band-2026-08-19)
(recorded as an addendum to DEC-039, not a new decision). (1) The visible
A/B stroke width was reduced from 2px to 1px -- the 10px drag hit target
is unchanged. (2) A subtle blue-tinted band (new theme token
`--cursor-range-fill`, the same accent-blue RGB base `--accent-wash`
already uses per theme, at ~5% alpha) now fills the region between A and
B, spanning analog panels, digital region, and the sticky ruler
continuously via the SAME two-segment overlay the cursor lines already
use (`.ww-cursor-range`/`.ww-cursor-ruler-range`, built once in the
existing `wwEnsureCursorDom()`, positioned by the existing
`wwUpdateCursorOverlay()` pass and the drag path's own live-update
function -- never a second overlay system). Shown only when both A and B
are visible; updates live during drag with zero waveform fetches. No
change to state model, initial placement, toggle behaviour, persistence,
or any other approved Phase 4B behaviour. `phase4b_check.mjs` extended to
29 checks (from 22); full frontend regression suite still exactly the
established 18-failure baseline; backend 328/328 unchanged.

**Fully completed.** Committed and pushed as `07d4633`; CI succeeded;
automatic DEV deployment verified live at that exact SHA.

**Phase 4B-UAT1 (same day) — stronger range highlight + sticky cursor
labels**: two more owner-requested cosmetic/structural refinements on top
of the same already-approved architecture -- see
[MIGRATION_PLAN.md — Phase 4B-UAT1 Record](MIGRATION_PLAN.md#phase-4b-uat1--stronger-range-highlight--sticky-cursor-labels-2026-08-19)
(second addendum to DEC-039, not a new decision). (1) `--cursor-range-fill`
raised from ~5% to ~20% alpha (Light/Dark both) -- theme.css only, no
geometry/behavior change. (2) The A/B label pills are now `position:
sticky`, staying visible near the top of the visible waveform viewport
while scrolling a tall waveform stack; the vertical cursor lines
themselves remain full-height and non-sticky, unchanged -- only the label
became viewport-relative, never the engineering cursor. Investigated the
real scroll container first (`#activeViewArea`); found `#wwCursorOverlay`'s
own `overflow: hidden` would break CSS sticky for any descendant (it
becomes the nearest "scroll container" for sticky-positioning purposes
per the CSS Overflow spec, even though it doesn't itself scroll) --
solved by extracting the label markup into a new sibling element,
`#wwCursorLabelLayer` (`position: sticky; top: 6px;`), living directly
inside `.workspace-section` (`overflow: visible`) with no scroll-container
ancestor between it and `#activeViewArea`. Both the line overlay and the
new label layer share the identical `wwCursorTimeToPixelX()` projection
authority -- no second horizontal-positioning implementation, per the
owner's own explicit instruction. Dragging from the label and the
individual × close buttons continue to work unchanged (same pointer-
capture/live-update path, `wwWireCursorDrag()`'s handlers now attached to
both `#wwCursorOverlay` and `#wwCursorLabelLayer`). No manual scroll
listener anywhere -- CSS `position: sticky` only, per the owner's
explicit preference; scrolling costs nothing extra.

**Verification**: `phase4b_check.mjs` extended to 37 checks (from 29) --
the stale 0.05-alpha assertion updated to 0.20 (an intentional value
change); new checks cover the label layer's sticky positioning and true
sibling relationship to `#wwCursorOverlay`, the label markup no longer
living inside a `.ww-cursor-line` template, all three overlay pieces
rendering distinctly, sticky-label-X-matches-line-X after pan/layout-
switch/resize, a dispatched `scroll` event never touching `a.time`/
`b.time` (plus confirming no `addEventListener("scroll"` exists anywhere
in the script), dragging directly from the label itself, the × close
button remaining functional from inside the sticky layer, and the label
layer's z-index/the line's still-full-height CSS. Full frontend
regression suite reconfirmed at exactly the established 18-failure
baseline; backend 328/328 unchanged (no backend file touched).

**Fully completed.** Committed and pushed as `fdde0c3`; CI succeeded;
automatic DEV deployment verified live at that exact SHA.

**Phase 4B-UAT2 (2026-08-20) — bug fixes**: owner real-browser UAT of the
above found two bugs -- see
[MIGRATION_PLAN.md — Phase 4B-UAT2 Record](MIGRATION_PLAN.md#phase-4b-uat2--cursor-range-fill--full-scroll-line-continuity-fix-2026-08-20)
(third addendum to DEC-039, not a new decision). **Bug 1**: DevTools
showed `--cursor-range-fill` as undefined. Both the source declaration
and the LIVE deployed `theme.css` (fetched directly via `curl`) were
confirmed byte-correct; a jsdom test exercising the real CSS cascade
engine (`getComputedStyle` on the actual `.ww-cursor-range` element, not
source-text matching) confirms the token resolves correctly in both
themes. No code-level bug was found -- the best-supported explanation is
browser-side caching of a stale copy of `theme.css` (that static asset
has no cache-busting mechanism, and the server sets no explicit
`Cache-Control`); **this caching gap is real but was deliberately left
unfixed**, since resolving it would mean editing the shared
`docker-entrypoint.d/10-powerwave-config.sh` entrypoint and/or nginx
config -- a deployment-wide change affecting every static asset and both
HTML pages, outside this bug-fix's own scope, and flagged to the owner as
a possible follow-up rather than made unilaterally. In the same pass,
`--cursor-range-fill`'s alpha was set to the owner's final target, 0.08
(Light `rgba(53,104,212,0.08)` / Dark `rgba(79,141,253,0.08)`), having
gone 0.05 -> 0.20 -> 0.08 across three UAT rounds. **Bug 2**: the vertical
cursor lines disappeared further down a tall (e.g. Separate mode)
waveform stack while the sticky labels remained correctly visible. Root
cause: the overlay's height was computed as
`rulerRect.getBoundingClientRect().top - sectionRect.getBoundingClientRect().top`
-- both viewport-relative, and `#wwStickyRuler`'s `position: sticky`
paint-time position (once pinned) diverges from its true position in the
scroll content. Fixed by reading `rulerWrapEl.offsetTop` instead -- a
stable layout metric immune to both scroll position and sticky's
paint-time displacement, using `.workspace-section` (confirmed
`#wwStickyRuler`'s `offsetParent`) as the reference frame -- the same one
`#wwCursorOverlay`'s own `top: 0` already uses. No scroll listener was
added; the existing content/layout recompute hooks remain sufficient
since `offsetTop` doesn't change with scroll. The range band, living
inside the same corrected overlay, is fixed by the same change.

**Verification**: `phase4b_check.mjs` extended to 43 checks (from 37) --
the stale 0.20-alpha assertion updated to 0.08; new checks cover
`getComputedStyle` resolving the token correctly in both themes on the
real elements, the overlay height using the ruler's stable `offsetTop`
rather than its live/sticky-affected `getBoundingClientRect().top` (a new
test-fixture knob independently controls "current on-screen position" vs.
"true content position" to reproduce the exact bug), height stability
across a dispatched `scroll` event, the range band sharing the corrected
height, and horizontal positioning remaining unaffected. Full frontend
regression suite reconfirmed at exactly the established 18-failure
baseline; backend 328/328 unchanged (no backend file touched).

**Committed, pushed, deployed** as `839fa43`; CI succeeded; automatic DEV
deployment verified live at that exact SHA. **Owner real-browser UAT then
found this fix was necessary but NOT sufficient** -- see the Phase
4B-UAT3 entry immediately below, which is the current, complete state.
This is stated plainly, not hidden.

**Phase 4B-UAT3 (2026-08-20) — the real fix for the scroll-visibility
bug**: see
[MIGRATION_PLAN.md — Phase 4B-UAT3 Record](MIGRATION_PLAN.md#phase-4b-uat3--fix-ab-main-cursor-lines-disappearing-after-vertical-scroll-2026-08-20)
(fourth addendum to DEC-039, not a new decision). **Precise owner
evidence**: with cursor mode already ON in a tall (Separate-mode,
many-channel) waveform stack, scrolling deep into the canvas made the
MAIN vertical lines disappear while the sticky A/B labels and the ruler's
own A/B segments (both separate rendering paths) stayed correctly
visible throughout -- and toggling cursor mode OFF then ON reliably
restored the lines immediately.

**Root-cause reasoning**: scrolling triggers no application code by
design (no scroll listener existed before this phase), so the DOM/CSS
state is byte-identical immediately before and after a scroll -- nothing
programmatically changes it. The ONE thing OFF→ON does differently is
re-invoke `wwUpdateCursorOverlay()`, reassigning every line/range
element's `style.left`/`style.height` even where the value is numerically
unchanged. Given the DOM geometry was very likely already correct
(Phase 4B-UAT2's `offsetTop` fix is retained here, unchanged, confirmed
still correct -- re-inspected specifically to make sure it hadn't been
silently reverted), the most consistent explanation is that the browser
was not reliably repainting this `overflow: hidden`, absolutely-
positioned overlay as its scrolling ancestor moved, until a genuine style
reassignment forced a fresh paint. **No real browser was available in
this sandbox** to directly confirm the exact paint/compositing mechanism
(`document.elementFromPoint()`, DevTools stacking-context inspection --
both explicitly requested diagnostics were not possible here); this is
disclosed as the best-supported reasoned analysis, not a directly
observed fact.

**Fix**: a `scroll` listener on `#activeViewArea` (the real scroll
container), rAF-coalesced exactly like the pre-existing window-resize
handler, re-invokes the SAME already-proven `wwUpdateCursorOverlay()`
pass. New `wwScheduleCursorOverlayRefresh()` early-returns whenever
`ww.measurementCursors.enabled` is false (ordinary scrolling with
cursors off costs nothing extra). This is a deliberate, owner-authorized
exception to Phase 4B-UAT1's original "prefer CSS sticky, avoid a scroll
listener" preference -- explicitly permitted once real-browser evidence
proved CSS alone insufficient. `wwUpdateCursorOverlay()` itself remains
cheap (a handful of geometry reads and style/textContent writes) -- never
a Plotly call, waveform fetch, or panel rebuild. The range band (same
container as the lines) is fixed by the same change with no separate
code path; the ruler segment and sticky labels were never part of the
buggy lifecycle and needed no change.

**Verification**: `phase4b_check.mjs` extended to 45 checks (from 43) --
the one test whose premise ("no scroll listener exists") is now the
OPPOSITE of the correct, owner-authorized behavior was rewritten (not
deleted) to confirm the listener exists, is rAF-coalesced, and stays
within its performance contract; a new test confirms the refresh is a
genuine no-op while cursor mode is disabled; a new test proves the actual
lifecycle gap this phase closes by changing mocked ruler geometry AFTER
cursor mode is already enabled and confirming a bare `scroll` event alone
(no OFF/ON) picks up the new value. **Explicitly disclosed limitation**:
jsdom has no real layout/paint/compositing engine, so this suite cannot
observe the actual real-browser symptom (a paint-staleness question, not
a DOM-state one) -- real-browser owner UAT remains authoritative for the
visual symptom itself. Full frontend regression suite reconfirmed at
exactly the established 18-failure baseline; backend 328/328 unchanged
(no backend file touched).

**Update (Phase 4C1 session, 2026-08-20)**: confirmed via `git fetch` over
HTTPS (SSH auth still fails in this sandbox), the public GitHub Actions
API, and a live `curl` of `/health` that this fix WAS already committed
and pushed as `7b14e4f`, CI succeeded, and automatic DEV deployment
succeeded and is live (`git_sha` starting `7b14e4f6...` confirmed at
`https://api.dev.powerwave.oruxa.uk/health`). The line below is
superseded by this update — retained for the historical record of what
was true at the moment this entry was originally written. Owner
real-browser UAT status for this specific fix remains unconfirmed either
way.

**Not yet done** *(as originally written, now superseded above)*:
commit/push, CI/automatic DEV deployment verification, and owner
real-browser UAT of this fix specifically.

## What was done in the prior session (Phase 4A-UAT10 — Source-Aware Time Bounds)

**Phase 4A-UAT10 — Source-Aware Time Bounds.** Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT10 Record](MIGRATION_PLAN.md#phase-4a-uat10--source-aware-time-bounds-2026-08-19),
[DECISIONS.md — DEC-037](DECISIONS.md#dec-037--waveform-time-domain-state-is-source-aware-source-bounds-workspace-bounds-and-viewport-are-distinct-phase-4a-uat10).

**Owner direction**: fix the UAT-proven COMTRADE duration/domain mismatch
without implementing cross-record synchronization. The specific bug:
backend/source metadata knew the active recording duration was `7.020 s`,
but waveform full/reset view could remain around `0 -> 1.3 s` because
frontend `ww.recordBounds`/`ww.viewport` could be inherited from a
previous source.

**What changed**: backend timebase metadata now exposes explicit
`elapsed_start_seconds` and `elapsed_end_seconds`, derived from the
retained `DisturbanceRecord` time column at import time. Frontend
`ww.recordBounds` was removed. Time-domain state is now:
`ww.sourceBounds` (source-id scoped native elapsed bounds),
`ww.workspaceBounds` (derived union of the currently participating
selected/displayed source set), and `ww.viewport` (user zoom/pan only).
Opening a source records its source bounds immediately from `/channels`
metadata, even when zero analog and zero digital channels are displayed.
`Reset Time View` restores `workspaceBounds`; waveform responses no
longer establish permanent full bounds.

**Participation semantics**: the current selected source participates even
with zero visible channels; any source with displayed analog or digital
channels also participates. This preserves current multi-source display
ability without adding timestamp alignment. If a `7 s` and a `15 s`
source both participate in today's unaligned elapsed model, workspace
bounds are `0 -> 15`; the shorter source is never stretched, padded, or
resampled.

**Existing local prerequisite preserved**: the working tree already
contained the approved Phase 4A-UAT9 default-hidden/group-toggle changes
before this task began. UAT10 was implemented on top of that state rather
than reverting it; source bounds therefore do not depend on rendered
channels.

**Verification**: frontend/static regression slice passed:
`pytest tests/test_frontend_source_bounds.py tests/test_frontend_entrypoint.py
tests/test_frontend_scrollbar_css.py` -> `29 passed`. Targeted source-bounds
suite passed:
`pytest tests/test_sources_api.py tests/test_comtrade_parity.py
tests/test_waveform_service.py tests/test_workspace_registry.py
tests/test_frontend_source_bounds.py` -> `57 passed` with the existing
FastAPI/TestClient deprecation warning and one malformed-CFG warning. Full
backend suite passed: `pytest` -> `327 passed`, same two warnings.

**Fully completed.** Committed and pushed as `02c3fce`; CI ran and
succeeded; `Deploy Powerwave (DEV, automatic)` fired via `workflow_run` and
succeeded; `curl https://api.dev.powerwave.oruxa.uk/health` returned
`git_sha` matching the pushed commit exactly. Layering this bounds rewrite
on top of the already-present, not-yet-committed Phase 4A-UAT9 work (see
the session note below) temporarily elevated the frontend jsdom regression
suite from the established 18-failure baseline to 34 failures — a
follow-up audit found 16 were obsolete test expectations from the bounds
rewrite (updated) and one was a genuine bug, `wwClearWorkspace()`
incorrectly clearing `ww.sourceBounds` for a source that was still open,
fixed and pushed as `a0da033` ("fix: preserve source bounds on display
clear"). Frontend suite is back to exactly the established 18-failure
baseline (`621 passed`); backend `328 passed`. **Owner has completed
real-browser UAT of the BEN5K 7.020 s case and all UAT10 checks passed.**

## What was done in the earlier session (Phase 4A-UAT9 — Default-Hidden Channels + Group Visibility Toggles)

**Phase 4A-UAT9 — Default-Hidden Channels + Group Visibility Toggles.**
Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT9 Record](MIGRATION_PLAN.md#phase-4a-uat9--default-hidden-channels--group-visibility-toggles-2026-08-19),
[DECISIONS.md — DEC-038](DECISIONS.md#dec-038--waveform-channels-default-to-hidden-on-open-group-level-showhide-controls-added-phase-4a-uat9).

**Owner direction**: DEC-034's "display everything by default" policy was
an explicit, time-boxed UAT experiment, not a permanent commitment. Real
UAT evidence showed the unconditional fetch/render of every channel on
every source-open is a real, avoidable cost. Reverse the default so a
newly opened recording displays zero analog and zero digital channels, add
compact per-group "Show all"/"Hide all" controls so bulk display/hide
stays efficient, and preserve every prior UAT5–UAT8 row-toggle behaviour
exactly as-is.

**What changed** (`frontend/index.html` only): `ww.sourceDefaultsApplied`
and `wwApplyDefaultChannelDisplay()` removed entirely — `selectSource()`
no longer displays anything by default. Every row starts
`aria-pressed="false"` / 25% opacity (the pre-existing hidden-row
treatment, not a new state). New `groupToggleButtonHtml()` renders a
"Show all"/"Hide all" button on each analog/digital subgroup header; new
`wwChannelGroupRows()` derives that group's membership live from the DOM
(no separate group-selection state); new `wwToggleChannelGroupDisplay()`
is the batched handler — "Show all" reuses UAT7's existing
one-`newPlot`-per-panel batch path, "Hide all" uses new
`wwRemoveChannelsByKeys()`/`wwRemoveDigitalChannelsByKeys()` (one
`Plotly.deleteTraces()` per affected panel, one refresh pass for the whole
batch, never per-channel). The group button's click handler
`stopPropagation()`s so it never also toggles the `<details>` subgroup.
Empty-state copy changed to "Select channels from the sidebar to display
waveforms." Visibility persistence (layout-mode/time-mode/navigation) and
Custom Group membership independence (DEC-035) are both unchanged — this
only changes what an engineer sees at the very first open.

**Verification**: existing scratch-convention jsdom suites
(`phase4a_check.mjs`, `phase4a_uat4_check.mjs`–`phase4a_uat8_check.mjs`)
updated so every test whose subject needs channels already visible calls a
`showAllAnalog`/`showAllDigital` helper explicitly, rather than relying on
the removed default; the handful of tests that were originally about
default-display-on-open itself were rewritten for the new zero-default
policy. No dedicated `phase4a_uat9_check.mjs` file was created — group-
toggle coverage (including a 33-channel batched-progress check) is folded
into the files above. Frontend suite returned to exactly the established
18-failure baseline; backend unaffected (no backend file touched).

**Not yet done at the time this task ended**: this work was left committed
locally but unpushed when a new owner request (Phase 4A-UAT10, above)
arrived and was implemented on top of it; both were pushed together in
commit `02c3fce`. Real-browser owner UAT of the group-toggle controls
specifically has not been separately confirmed (folded into the general
UAT10 DEV verification above).

## What was done in the earlier session (CI/CD — Automatic DEV Deployment After CI, DEC-036)

**CI/CD — Automatic DEV Deployment After CI (DEC-036).** Full detail:
[MIGRATION_PLAN.md — CI/CD Record](MIGRATION_PLAN.md#cicd--automatic-dev-deployment-after-ci-2026-08-19),
[DECISIONS.md — DEC-036](DECISIONS.md#dec-036--dev-deployment-is-automatic-after-ci-succeeds-on-main-prod-remains-fully-manual).

**Owner report**: DEV deployment stopped auto-starting after a push to
`main`; owner recalled it working previously. **Investigation finding**
(not a regression): the original `deploy.yml` (2026-08-09) genuinely did
trigger on `push`, but was deliberately replaced with
`workflow_dispatch`-only that same day when DEV/PROD environment
selection was introduced, and formalized 5 days later as DEC-003 ("no
auto-deploy-on-merge... without a separate decision"). On reviewing this
history, the owner approved restoring DEV automation specifically.

**What changed**: new `.github/workflows/deploy-dev.yml` only --
`deploy.yml` is byte-for-byte untouched, remains the manual `dev`/`prod`
fallback, and remains the only path to PROD. Trigger: `workflow_run` on
"CI" completing on `main` (never a bare `push`, which would race CI
rather than wait for it); the one job gates on `conclusion == 'success'`
so a failing commit is never deployed; deploys the EXACT SHA CI
validated (`github.event.workflow_run.head_sha`, not the unreliable
`github.sha` in this context), preserving the existing build-provenance
chain unchanged. DEV-only by construction: no `target` input exists at
all in the new file -- every value the manual workflow selects via
`${{ inputs.target }}` is the literal string `"dev"` here (job
`environment:`, `TARGET=`, and the concurrency group, which deliberately
matches `deploy.yml`'s own dev-targeted group so the two paths queue
instead of racing each other).

**Verified live after push** (commit `93168a3`): CI ran and succeeded,
`Deploy Powerwave (DEV, automatic)` fired via `workflow_run` and
succeeded, and `curl https://api.dev.powerwave.oruxa.uk/health` returned
`git_sha` matching the pushed commit exactly -- the full chain confirmed
working end to end via the public GitHub API (no `gh` CLI needed, the
repo is public).

## What was done in the earlier session (Phase 4A-UAT7 — Fix Duplicate Analog Trace Rendering)

**Phase 4A-UAT7 — Fix Duplicate Analog Trace Rendering.** Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT7 Record](MIGRATION_PLAN.md#phase-4a-uat7--fix-duplicate-analog-trace-rendering-2026-08-19),
[DECISIONS.md — DEC-035's own "UAT7 resolution"](DECISIONS.md#dec-035--analog-channel-visibility-is-workspace-global-layout-mode-governs-arrangement-only-never-visibility-phase-4a-uat6).

**Owner direction**: fix the duplicate-analog-trace defect DEC-035
discovered during UAT6 and deliberately left unfixed. Narrowly scoped to
duplicate-trace removal only -- no visibility/layout/digital redesign.

**Reproduction**: a new empty Grouped panel + `wwAddSelectedChannels()`
called ONCE with A/B/C produced 5 real Plotly traces (`A, B, C, B, C`),
not 3 -- but exactly 3 waveform network requests, proving the
duplication was rendering-only, never a duplicate fetch. Separate mode
and `wwRebuildLayout()` (layout switches, Custom Groups Apply) were
confirmed NOT affected.

**Root cause**: `wwAddSelectedChannels()`'s per-meta loop pushes every
new channel into `panel.channels` unconditionally, so a brand-new
panel's `panel.channels` is already COMPLETE by the time
`wwInitPanelPlot()` draws it via one `Plotly.newPlot()` call. The bug
was the function's SEPARATE incremental-add loop, which used a per-meta
`isNewPanel` flag meaning "was the panel object already present when I
was processed" -- true for a panel an EARLIER channel in the SAME batch
had just created, so the 2nd..Nth channel of that panel ALSO got a
redundant `Plotly.addTraces()` call on top of what `newPlot()` had
already drawn.

**What changed** (`frontend/index.html` only): the incremental-add
loop's gating condition changed from the per-meta `isNewPanel` flag
(removed) to membership in `newlyCreatedPanels` (already correctly
tracked, just not consulted at the right point) -- one unambiguous
trace-ownership path per panel. Also added: a stable `meta:
wwChannelKey(sourceId, channelName)` field on every built trace (Plotly's
own documented metadata property), and an on-demand
`wwDiagnoseDuplicateAnalogTraces()` console helper (mirrors
`wwDiagnoseDigitalAlignment()`, Phase 4A-UAT2).

**Verification**: new dedicated `phase4a_uat7_check.mjs` (18 checks) --
the key regression, the full Grouped A-E matrix, Custom (new/existing
group multi-add, hidden-member re-enable, editor Apply path), Separate
(confirmed unaffected), default-all-on-open (displayed count == unique
trace count), source isolation, DEC-035 global-visibility non-regression,
color-mapping non-regression, digital isolation, and the new diagnostic
itself. Confirmed as a genuine regression guard: 14 of 18 checks fail
against pre-fix code, all 18 pass after. Full regression suite still
exactly the established 18-failure baseline; backend 321/321 unchanged.

**Not yet done**: real-browser visual/performance confirmation -- flagged
for owner UAT.

## What was done in the earlier session (Phase 4A-UAT6 — Global Analog Channel Visibility Across Layout Modes)

**Phase 4A-UAT6 — Global Analog Channel Visibility Across Layout Modes.**
Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT6 Record](MIGRATION_PLAN.md#phase-4a-uat6--global-analog-channel-visibility-across-layout-modes-2026-08-19),
[DECISIONS.md — DEC-035](DECISIONS.md#dec-035--analog-channel-visibility-is-workspace-global-layout-mode-governs-arrangement-only-never-visibility-phase-4a-uat6).

**Owner report**: hiding an analog channel in Grouped mode did not
reliably persist when switching to Separate/Custom. Required rule:
`ww.displayed` is the ONE global visibility authority; layout mode is
presentation-only, never a second source of truth.

**Root cause**: the simple hide-then-switch-mode flow was ALREADY
correct (`wwRebuildLayout()` always re-derives every layout from
`ww.displayed` fresh) -- confirmed by reproducing the owner's own
example against pre-UAT6 code, which passed. The REAL bug was in the
Custom Groups editor: `wwOpenGroupEditor()` filtered a group's
membership down to only currently-displayed channels, and Apply
committed that pruned copy back into `ww.customGroups` -- permanently
losing a hidden channel's group assignment (so re-enabling it later
dropped it into its own auto-solo panel instead of its original group).

**What changed** (`frontend/index.html` only): `wwOpenGroupEditor()` no
longer filters membership by visibility at open time. New
`ww.channelMeta` map (same lifecycle as `ww.channelColors`/
`ww.customGroups`/`ww.panelHeights` -- survives hide, cleared only by
`wwClearWorkspace()`) lets the editor's group chips still show a hidden
member's name/unit/color (dimmed via new `.group-chip--hidden`) without
needing it in `ww.displayed`. New `wwIsAnalogChannelVisible()` helper
(pure readability wrapper around the pre-existing `ww.displayed.has(...)`
check, zero behavior change). `wwColorForChannel()` and the Separate-mode
local `x` (already routing through the same global removal path) are
unchanged.

**Separately discovered, then NOT fixed here (fixed the following
session, Phase 4A-UAT7 above)**: a genuine, unrelated pre-existing
rendering bug -- `wwAddSelectedChannels()` can double-add a Plotly trace
for the 2nd..Nth channel of a brand-new panel when 2+ new channels join
the same group in one batch call (most commonly default-display-on-open).

**Verification**: new dedicated `phase4a_uat6_check.mjs` (13 checks,
scratch convention) covers the full A-F cross-mode visibility matrix,
state persistence, source isolation, and digital isolation. Full
regression suite still exactly the established 18-failure baseline;
backend 321/321 unchanged.

## What was done in the earlier session (Phase 4A-UAT5 — Simplify Analog Channel Toggle Rows)

**Phase 4A-UAT5 — Simplify Analog Channel Toggle Rows.** Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT5 Record](MIGRATION_PLAN.md#phase-4a-uat5--simplify-analog-channel-toggle-rows-2026-08-18).

**Owner direction**: remove the analog checkbox and the UAT4-era sidebar
remove button; clicking (or Enter/Space-activating) a channel's own row
now toggles its display directly. Dim the WHOLE row (not just the dot)
to 25% opacity when hidden, rising to ~55% on hover/focus for
discoverability. Grow the color dot from 7px to 10px. Combine Name+Unit
into one "Channel" column, dropping the Unit column entirely (omit empty
parens when unit is missing). Analog checkbox SELECTION is removed
outright -- "Add N selected"/"Clear selection" now describe DIGITAL
selection only. Reuse `wwColorForChannel()` unchanged (no new color
logic). Do NOT redesign Separate mode (its existing local lane label/
dot/remove stays exactly as UAT4 left it) or digital's own checkbox/
selection workflow.

**What changed** (`frontend/index.html` only): new
`analogChannelRowAttrs()` makes the analog `<tr>` itself the
interactive toggle (`tabindex`, `role="button"`, `aria-pressed`, the
same `data-*` metadata the old checkbox carried), mirroring the
pre-existing `table.recordings` row-as-button pattern; new
`wwToggleAnalogChannelDisplay()` calls the SAME
`wwRemoveChannelByKey()`/`wwAddSelectedChannels()` paths the old
checkbox+button used. `renderChannelTable()` gained an opt-in
`rowAttrsFn` parameter (digital's own call site never passes it, so
digital is structurally unaffected). `analogChannelNameCellHtml()` now
renders just the 10px dot + combined "name (unit)" text.
`channelCheckboxHtml()` and `selectedChannels` were deleted entirely;
`setupSelectionControls()` simplified to digital-only counting/adding/
clearing (button text unchanged -- still truthful). CSS:
`.channel-color-dot` 7px->10px; new `.channel-row--toggle`/
`.channel-row--hidden` (25%, 55% on hover/focus); removed
`.channel-color-dot--dim`/`.channel-remove-btn` entirely.
`wwRenderLegend()`/every `.ww-legend*` rule: untouched.

**Verification**: `phase2ca_check.mjs`, `phase3a_check.mjs`, and
`phase3buat8_check.mjs` had their own analog-checkbox-specific
assertions rewritten to the row-click model; `phase4a_uat4_check.mjs`
was updated in place (its `dotFor()` helper now reads the new row
identity) rather than left describing removed behavior -- all of UAT4's
still-applicable coverage re-verified passing unchanged. New dedicated
`phase4a_uat5_check.mjs` (21 checks, scratch convention) covers row
structure, click/keyboard toggling, color stability, default-all +
navigation persistence, digital isolation, and Separate-mode
coexistence. Full regression suite still exactly the established
18-failure baseline (reconfirmed against pre-UAT5 `main`); backend
321/321 unchanged.

**Git note**: this phase's edits landed on `origin/main` via a
concurrent session's own commits (`e51b647`, `be201d3`, titled
"adjusting padding") rather than a dedicated commit from this session --
see the MIGRATION_PLAN.md record's own note for what happened and how it
was verified intact. No history rewrite was performed.

**Not yet done**: real-browser confirmation (10px dot legibility, the
25%/55% hidden-row opacity read, hover/focus tint, keyboard focus ring)
-- flagged for owner UAT before any further waveform feature work.

## What was done in the earlier session (Phase 4A-UAT4 — Channel Sidebar as Analog Legend)

**Phase 4A-UAT4 — Channel Sidebar as Analog Legend.** Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT4 Record](MIGRATION_PLAN.md#phase-4a-uat4--channel-sidebar-as-analog-legend-2026-08-18).

**Owner direction**: remove the obsolete "Waveform (UAT)" per-channel
control; remove the duplicated analog waveform legend/chip strip above
the canvas; use the existing Channels sidebar as the analog legend
instead (color dot beside each channel name, driven by the exact same
color the Plotly trace uses); preserve all selection/display/removal
behavior. **Mid-task clarification**: this applies to Grouped/Custom
modes ONLY -- Separate mode's existing per-lane legend chip (dot,
name/unit, overlay position, remove control) is explicitly preserved
unchanged, since one lane = one channel there is not the same
duplication a multi-channel Grouped/Custom panel's chip strip was. An
initial uniform-removal attempt was reverted before finishing, once
this clarification arrived.

**What changed** (`frontend/index.html` only): new `wwColorForChannel()`
-- the ONE color authority both the Plotly trace and the sidebar's new
color dot read from, keyed by the existing `sourceId::channelName`
identity convention, backed by a `ww.channelColors` map that persists
for the workspace session (cleared only by a whole-workspace reset,
same policy as `ww.customGroups`/`ww.panelHeights`). Each analog
sidebar row (`analogChannelNameCellHtml()`) now shows a small (7px)
color dot + the name + (only while displayed) a compact remove button
reusing the pre-existing `wwRemoveChannelByKey()`; a not-currently-
displayed channel's dot stays visible but dimmed (35% opacity), never
hidden. `wwRenderLegend()` (the pre-existing chip-strip renderer,
implementation untouched) is now called ONLY when
`ww.layoutMode === "separate"` -- Grouped/Custom simply stop rendering
it, dropping the duplicated per-channel chips while their group/custom-
group HEADINGS (a separate, untouched mechanism) remain.
`wwSyncChannelBrowserDisplayState()` (new) keeps the sidebar's dots/
remove-buttons live-accurate as the displayed set changes through any
path (add, remove, workspace clear, re-opening an already-open source).

**Verification**: several pre-existing frontend tests asserted directly
on `.ww-legend-item` chip counts inside Grouped/Custom panels -- all
corrected in place (verified via each channel's own Plotly trace count
or the new sidebar elements instead), each one independently confirmed
NOT a regression by re-running the identical test against untouched
canonical `main` first. New `phase4a_uat4_check.mjs` (21 checks, scratch
convention) covers obsolete-control removal, color-authority/stability
across every navigation path, displayed-vs-dimmed dot treatment,
Grouped/Custom legend removal vs Separate's unchanged chip, the full
removal/re-add workflow, and layout containment. Full regression suite
still exactly the established 18-failure baseline; backend 321/321
unchanged (no backend file touched).

**Not yet done**: real-browser confirmation (color contrast/dot sizing
as perceived by eye, whether the canvas genuinely "feels" cleaner) --
flagged for owner UAT before any further waveform feature work.

## What was done in the earlier session (Phase 4A-UAT3 — Build SHA / Version Provenance)

**Phase 4A-UAT3 — Build SHA / Version Provenance.** Full detail:
[MIGRATION_PLAN.md — Phase 4A-UAT3 Record](MIGRATION_PLAN.md#phase-4a-uat3--build-sha--version-provenance-2026-08-18).

**Owner requirement**: make it trivial to verify exactly which Git
commit DEV/PROD is actually serving, so "GitHub main is newer than the
deployment" or "the browser is showing a stale build" is immediately
detectable instead of a source of confusion.

**Source of truth**: `APP_VERSION` -- already set by `deploy.yml` to
`github.sha` and already used to tag the `powerwave-backend`/
`powerwave-frontend` Docker images -- is now ALSO passed straight
through as a runtime env var into both containers. Nothing runs `git`
inside a container; an un-deployed local container truthfully reports
`"local"` (reusing `scripts/deploy.sh`'s own existing fallback
convention, not a new one).

**What changed**: `GET /health` now returns `version` (short 7-char) and
`git_sha` (full 40-char) alongside `status`/`environment`. The
frontend's existing `config.js` runtime-config mechanism (regenerated at
container START by `frontend/docker-entrypoint.d/10-powerwave-config.sh`,
never at Docker build time) now also carries `environment`/
`buildVersion`; on startup the app logs exactly ONE console line
(`Oruxa Powerwave — <environment> — build <version>`) and sets
`document.documentElement.dataset.build` from the same value.
`compose.yaml` (the portable base -- unchanged shape for DEV/PROD, only
the value differs) passes `APP_VERSION` into both services'
`environment:` blocks, so frontend and backend always report the exact
same SHA from the exact same deploy-time source, never two
independently-maintained version strings.

**Verification**: backend 321/321 (311 pre-existing + 10 new, covering
full-SHA passthrough, short-version truncation, the `"local"` fallback
in both dev and production, and the entrypoint script writing both new
fields via its own real-`sh` test harness). New `phase4a_uat3_check.mjs`
(5 checks, scratch convention) covers the console message firing exactly
once, the DOM marker matching the injected value, and the same truthful
fallback frontend-side. Full frontend regression suite: 18 failures --
the established 17 plus one PRE-EXISTING, independently-confirmed-
unrelated failure (`phase3buat3_check.mjs`'s button-size-tier
assertion) traced to an external "adjusting the header toolbar and
button font size" commit made outside this task's own session, not
introduced by this phase's own (CSS-untouched) changes.

**Not yet done**: no DEV/PROD deployment dispatched from this sandbox
(no deploy credentials available here) -- the mechanism is structurally
verified but not yet confirmed end-to-end against a real running
deployment. Owner verification commands are in the MIGRATION_PLAN.md
record.

## What was done in the earlier session (Phase 4A-UAT2 — Fix Remaining Digital Waveform UAT Failures)

**Phase 4A-UAT2 — Fix Remaining Digital Waveform UAT Failures.** Full
detail:
[MIGRATION_PLAN.md — Phase 4A-UAT2 Record](MIGRATION_PLAN.md#phase-4a-uat2--fix-remaining-digital-waveform-uat-failures-2026-08-18).

**Real-browser owner UAT on the Phase 4A-UAT1B build**: grouping/
ordering PASSED (unchanged this pass); alignment, loader visibility,
label overlay, and HIGH-band boldness all FAILED despite UAT1B's code
existing to address them -- owner real-browser observation treated as
authoritative, not reinterpreted as already solved.

**Root causes found (source investigation, no real browser available in
this sandbox)**: (1) **alignment** -- `wwResizeAllVisiblePlots()` (the
established Phase 3A-UAT1 catch-up for Plotly's `responsive:true` not
reliably detecting non-window container resizes) was never updated to
include the digital chart when Phase 4A introduced it -- ANY Workspace
Sidebar drag, Main Sidebar collapse, window resize, or even a plain
Recordings→Waveform navigation left digital's rendered width stale
relative to analog/ruler, independent of UAT1B's own margin.l fix. (2)
**loader** -- this codebase's own Phase 2C-C2A finding ("the browser
cannot paint until synchronous work returns control") applies here too;
a bare `await fetch()` on a fast DEV connection was not a reliable paint
guarantee. (3) **labels** -- the label annotation was vertically
anchored ABOVE its own trace, not centered on it, so it read as a
separate band rather than a true overlay. (4) **HIGH band** -- no
concrete logic bug was found after exhaustive re-audit (re-verified
correct via jsdom against constant-HIGH/LOW/transitioned fixtures); the
fix was switching to a simpler, more robust rendering primitive rather
than continuing to guess at an undetectable-from-here bug.

**What changed** (`frontend/index.html` only): `wwResizeAllVisiblePlots()`
now resizes the digital chart alongside every analog panel and the
ruler; `#wwDigitalChart` gained an explicit `width:100%` CSS rule; a new
`wwYieldToPaint()` (double `requestAnimationFrame`) is awaited right
after the loader becomes visible, before any other work starts;
`openRecordingForAnalysis()` now navigates to Waveform BEFORE calling
`selectSource()` (previously the other order); the label annotation is
now `yanchor:"middle"` at the trace's exact Y; HIGH-interval bars are
now `layout.shapes` (matching the already-working group-divider lines
in the same chart) instead of a second gapped line trace -- each channel
is back to one trace. A new `wwDiagnoseDigitalAlignment()` console
diagnostic reads Plotly's real `_fullLayout` geometry for the owner to
verify directly.

**Verification**: `phase4a_check.mjs` grew from 31 to 35 checks. Full
frontend regression suite still exactly the established 17-failure
baseline. Backend: 311/311, unchanged (no backend file touched).

**Not yet done, explicitly**: real-browser confirmation of all four
fixes -- this pass cannot be accepted as visually correct from jsdom/
source-level checks alone; the next required step is the owner running
`wwDiagnoseDigitalAlignment()` and eyes-on verification in a real
browser.

## What was done in the earlier session (Phase 4A-UAT1B — Digital Waveform UX / Correctness Refinement)

**Phase 4A-UAT1B — Digital Waveform UX / Correctness Refinement.** Full
detail:
[MIGRATION_PLAN.md — Phase 4A-UAT1B Record](MIGRATION_PLAN.md#phase-4a-uat1b--digital-waveform-ux--correctness-refinement-2026-08-18).

**Owner UAT on Phase 4A found four issues**: (1) digital sorting/grouping
looked purely alphabetical, (2) digital traces didn't visually line up
with analog, (3) opening a recording with everything displayed by
default could lag with no loading feedback, (4) constant-HIGH vs
constant-LOW signals were hard to tell apart -- plus a new visual
direction (screenshot benchmark): small overlaid pill labels on each
lane, HIGH as a bold band, LOW as a thin line, not a two-plateau step
trace.

**Root causes, confirmed before changing anything**: (1) was NOT a
sort/classification bug -- re-verified end to end including the BINARY
COMTRADE provider path Phase 4A's own tests never exercised; the real
gap was that the rendered chart never showed group headers/separators
(the channel browser already did). (2) WAS a real bug: the digital
chart's own Plotly left margin (150px) differed from every analog
panel's and the shared ruler's (55px, `WW_PANEL_MARGIN.l`), so identical
X values rendered at different pixel positions. (4) was a genuine
readability gap in the old two-plateau step-trace design.

**What changed** (pure frontend, `frontend/index.html` only -- no
backend file touched, no new architecture decision): the rendered
digital region now shows a header + count for each non-empty
classification group, in the required order, with a divider at each
boundary. Each digital lane is now ONE flat Y position carrying two
traces: a thin muted baseline (always present) and a bold/thick band
(drawn only during HIGH intervals, derived from `initialState` +
transitions) -- constant-HIGH now shows a full-width bold band,
constant-LOW shows no band at all. Channel labels moved from Y-axis
ticks to small opaque pill annotations overlaid directly on each lane
(`xref: "paper"`, pinned to the plot area's left edge regardless of
zoom/pan) -- this is what let the margin become identical to
`WW_PANEL_MARGIN`, fixing the alignment bug. A new
`#wwWorkspaceLoading` overlay is shown as the very first statement in
`selectSource()` (before any fetch starts), reports a REAL per-channel
"N / total" progress count (never fake), and is always cleared via
`try/finally`.

**Verification**: `phase4a_check.mjs` grew from 25 to 31 checks (scratch
convention, not committed). Full frontend regression suite still exactly
the established 17-failure pre-existing baseline (unrelated files, none
of which touch digital channels or call `selectSource()`). Backend:
311/311, unchanged (no backend file touched). `git diff --check` clean.

**Not yet done**: real-browser owner UAT of the new visual design and
alignment/loading fixes -- explicitly flagged as the next required step
before any further waveform feature work.

## What was done in the earlier session (Phase 4A — Digital Channels Rendering)

**Phase 4A — Digital Channels Rendering.** Full detail:
[MIGRATION_PLAN.md — Phase 4A Implementation Record](MIGRATION_PLAN.md#phase-4a--digital-channels-rendering-implementation-record-2026-08-17)
and [DECISIONS.md — DEC-034](DECISIONS.md#dec-034--digital-channel-rendering-shared-batched-full-record-transition-api-one-shared-multi-trace-plotly-figure-not-one-instance-per-channel-phase-4a)
(new architecture decision).

**Owner directive**: pause the cosmetic UX passes (UAT7–UAT11 above) and
return to core waveform functionality — render COMTRADE digital
(binary/state) channels alongside the existing analog waveform
architecture. Explicit instruction: display ALL analog and digital
channels by default once a recording is opened, then evaluate real
performance/usability through owner UAT before deciding whether any
default channel filtering is needed.

**What changed (backend)**: a new batched
`GET .../sources/{id}/digital-waveform?channel_names=A&channel_names=B...`
endpoint serves each requested digital channel's classification
(Triggered/Never Triggered/Spare — computed once at import time, never
per-request) and its full-record transition list (`{time, state}`,
never point-budget/range-reduced — digital transitions are inherently
sparse, so full delivery is both the most truthful and, in practice, the
smallest payload). New `app/domain/digital_classification.py` implements
the owner's exact required precedence (name contains "spare" beats any
observed high state; "any non-zero sample across the full record" is
Triggered even with zero transitions).

**What changed (frontend)**: every displayed digital channel now
renders as one true-step (`line_shape: "hv"`) trace inside a SINGLE
shared Plotly figure — deliberately NOT one Plotly instance per digital
channel, a genuinely different architecture from analog's own
one-instance-per-panel model (DEC-024/DEC-026), chosen because a
COMTRADE record may carry hundreds of digital channels. The digital
region (`#wwDigitalRegion` → `#wwDigitalScroll`, independently
vertically scrollable) sits strictly below all analog panels and
strictly above the existing shared sticky ruler (DEC-030), which is
never nested inside the scroll container and remains the one
authoritative bottom time reference. Digital shares the exact analog X
viewport (zoom/pan/Reset Time View/Absolute-Elapsed all stay in sync,
zero second synchronization authority); Autoscale Y remains
analog-only. A `plotly_click` listener on the digital chart gives each
lane a remove affordance (mirroring analog's per-panel legend remove
button), since digital lanes have no individual DOM row of their own.

**Default display policy (the owner's explicit UAT experiment)**:
opening/re-opening a source that hasn't been auto-defaulted THIS
SESSION (`ww.sourceDefaultsApplied`) now displays every analog AND
every digital channel — same policy for both. Manually hiding/removing
a channel afterward is never undone merely by navigating
Waveform → Recordings → Waveform back to the same already-open
recording (reset only by a whole-workspace clear). This intentionally
does NOT solve "what if a source has hundreds of channels" by hiding
anything automatically — that is exactly what owner UAT is meant to
evaluate.

**Verification**: new dedicated `phase4a_check.mjs` (25 checks, not
committed — this project's established scratch-verification
convention) covers classification precedence, display ordering,
default-display persistence across navigation, digital rendering
structure, shared-viewport sync, large-channel-count scrolling, long
channel names, and multi-source isolation. Full existing frontend
regression suite returned to exactly its established pre-existing
17-failure baseline (independently re-confirmed against the untouched
canonical `HEAD`, unrelated to this phase — all trace to the
pre-existing DEC-030 sticky ruler's relayout/newPlot calls being
undercounted by assertions written before the ruler existed);
`phase2ca_check.mjs`'s own previously-documented 3-failure baseline was
fixed to 0 as an unavoidable side effect of correctly accounting for
`selectSource()`'s new default-display flow. Backend: 311/311 passing
(286 pre-existing + 25 new), zero regressions. `git diff --check`
clean.

**Not yet done**: real-browser owner UAT (readability of digital step
traces in Light/Dark, hover tooltip legibility, real scroll feel, real
zoom/pan responsiveness at 100+/300+ simultaneously-displayed digital
channels) — explicitly flagged as the next required step before any
further waveform feature work (cursor/measurement tools etc.) begins.

## What was done in the earlier session (Phase 3B-UAT11 — Workspace Sidebar Divider / Scrollbar Line Cleanup)

**Phase 3B-UAT11 — Workspace Sidebar Divider / Scrollbar Line Cleanup.**
Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT11 Record](MIGRATION_PLAN.md#phase-3b-uat11--workspace-sidebar-divider--scrollbar-line-cleanup-2026-08-17).
No new DECISIONS.md entry.

**Confirmed remaining line source**: owner real-browser UAT after UAT10
showed the remaining hard line immediately to the right of the Workspace
Sidebar scrollbar. Source inspection identified that line as
`#workspaceSidebar { border-right: 1px solid var(--panel-border); }`,
not a scrollbar pseudo-element. The adjacent 6px
`#workspaceSplitHandle` already had its own centered divider via
`.shell-split-handle::after`, so desktop showed scrollbar/gutter +
sidebar border + resize-handle divider.

**What changed**: `#workspaceSidebar` now has `border-right: 0` in the
base/desktop rule and in the <=900px drawer override. The existing resize
handle remains unchanged and is now the single desktop visual separator;
the drawer keeps its existing shadow/backdrop boundary instead of
reintroducing a hard line at the scrollbar edge.

**What was preserved**: UAT9/UAT10 scrollbar baseline and local track
blending are unchanged. `#workspaceSidebar` still has `width: 320px`,
`overflow-y: auto`, `background: var(--bg)`, and the JS resize bounds
remain 320/240/520 with `onResize: wwResizeAllVisiblePlots`. The handle's
6px drag target, centered 2px divider, hover/active accent affordance,
and `role="separator"` markup are still present. No Recordings,
channel-tree, Plotly data, theme, or responsive shell behavior was
otherwise changed.

**Verification coverage**: `backend/tests/test_frontend_scrollbar_css.py`
now checks UAT9 baseline, UAT10 track blending, UAT11 no-hard-border
rules for `#workspaceSidebar`, handle/divider presence, resize constants,
Plotly resize callback wiring, and drawer shadow/overlay behavior. Real
browser perception remains for owner DEV UAT. `git diff --check` is
clean; the focused test passes (6/6); committed/tracked backend tests pass
(286/286, two existing warnings). A raw full pytest against the dirty
local worktree fails 8 unrelated untracked digital-waveform tests because
those local tests expect backend behavior not present in canonical `HEAD`.

## What was done in the earlier session (Phase 3B-UAT10 — Targeted Scrollbar Track / Divider Fix)

**Phase 3B-UAT10 — Targeted Scrollbar Track / Divider Fix.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT10 Record](MIGRATION_PLAN.md#phase-3b-uat10--targeted-scrollbar-track--divider-fix-2026-08-17).
No new DECISIONS.md entry.

**Summary**: UAT10 kept the shared UAT9 slim scrollbar baseline intact
and added local-surface track colors for `#mainSidebarMenu`,
`#workspaceSidebar`, `.group-editor-box`, and `.group-body`, including
Firefox `scrollbar-color` and WebKit `::-webkit-scrollbar-track-piece`.
It deliberately preserved structural dividers; UAT11 above is the
follow-up that removes the one hard Workspace Sidebar border owner UAT
still saw as a scrollbar-adjacent rail.

## What was done in the earlier session (Phase 3B-UAT9 — Slim Borderless Scrollbars)

**Phase 3B-UAT9 — Slim Borderless Scrollbars.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT9 Record](MIGRATION_PLAN.md#phase-3b-uat9--slim-borderless-scrollbars-2026-08-17).
No new DECISIONS.md entry.

**Summary**: a global, presentation-only scrollbar cosmetics pass added
one shared rule set to `frontend/theme.css`: universal Firefox
(`scrollbar-width: thin`, `scrollbar-color`) plus Chromium/WebKit
(`::-webkit-scrollbar` family), 6px thumb/track size, transparent
border-free global track/corner, borderless rounded thumb using
`--scrollbar-thumb`/`--scrollbar-thumb-hover` tokens in both Light and
Dark themes. No scrolling containers or layout borders were touched in
that pass; the UAT10 follow-up above only colors local tracks in the
reported areas.

## What was done in the earlier session (Phase 3B-UAT8 — Waveform Sidebar Cleanup + Main Navigation Refinement)

**Phase 3B-UAT8 — Waveform Sidebar Cleanup + Main Navigation
Refinement.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT8 Record](MIGRATION_PLAN.md#phase-3b-uat8--waveform-sidebar-cleanup--main-navigation-refinement-2026-08-17).
No new DECISIONS.md entry.

**Owner rule**: Recordings = recording management; Waveform = active
recording context + channel analysis only. The Waveform sidebar
previously duplicated Recordings' own management UI.

**Active Recording replaces "Sources in this Workspace"**: the old
multi-source clickable list (with a per-row Remove button) is gone —
`renderActiveRecording(sources)` now shows ONLY whichever source
`selectedSourceId` currently names (name + analog/digital counts),
read-only, no list, no Remove, no source-switching. **Deliberate
behavior change**: switching which source's channels you're browsing
now requires going back to Recordings and opening a different row —
this is the intended consequence of the owner's own rule, not a
regression; multi-source *display* (`ww.displayed`/`ww.panels`) is
completely untouched. The section itself dropped the old bordered
`.panel` card for a lighter, restrained block (a bottom-border divider,
no card) — nothing left to manage here justified the heavier treatment.
`startNewWorkspace()`'s "does the workspace have any sources" check
(previously reading the old list's own DOM child count) now uses a
small `latestSourcesCount` cache kept current in
`refreshAllSourceViews()`/`refreshSourceList()`.

**Channels no longer repeats identity**: `renderChannels()`'s
`.detail-header` block (station name + CFG/DAT filenames, deliberately
kept since Phase 3B-UAT5) was removed — that identity now lives in
Active Recording directly above Channels. The now-fully-dead
`.detail-header`/`.source-list`/`.source-name`/`.source-sub` CSS was
deleted, not left unused.

**Main Sidebar reordered, and a real pre-existing bug fixed**:
Recordings now comes first, Waveform second (matching the actual
product flow). While reviewing active/inactive states, found that
`.shell-nav-item[aria-current="page"]` — the CSS rule providing the
active-item accent tint — had NEVER actually matched anything:
`shellSetCurrentPage()` was writing the STRING `"true"`/`"false"`
instead of the token `"page"` the CSS always expected, so the active-
page visual has been silently broken since Phase 3B introduced page
navigation. Fixed via a new `setShellNavCurrent()` helper (writes
`"page"` when active, removes the attribute entirely when not — the
ARIA APG convention for both). Added a narrow 3px left accent bar
alongside the now-actually-working tint. New icons for Recordings (a
record-list glyph, distinct from the sidebar's own hamburger toggle
icon it used to resemble) and Waveform (a genuine zigzag/waveform
polyline, replacing a dashboard-panel-shaped icon that didn't read as
"waveform"); Table/Tools/Reports/Settings icons left unchanged.
Collapsed-sidebar order follows automatically from the DOM reorder;
`title` tooltips added to the enabled items for parity with the
disabled items' existing tooltip convention.

**Verification**: 24 new frontend `jsdom` checks
(`phase3buat8_check.mjs`) + `phase3auat4_check.mjs` substantially
rewritten (its entire premise — CFG/DAT filename containment inside the
Waveform Channels panel — no longer applies; retargeted to the
equivalent long-NAME containment concern in Active Recording) + smaller
corrections in `phase3auat3_check.mjs`, `phase3b_check.mjs`,
`phase3buat4_check.mjs`, `phase3buat5_check.mjs` (the removed
`.detail-header`, and the `aria-current` string-vs-token fix) — the
full suite otherwise returns to the exact same 20 pre-existing, already-
documented failures, zero new divergences. Backend: zero diff, 280/280
passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the accent-bar/tint combination and new icons read clearly, and
whether the lighter Active Recording section still feels sufficiently
present — was NOT and cannot be confirmed in this sandboxed session;
this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT7 (continued) — Final Table Restructuring and Row-Click-to-Open)

**Phase 3B-UAT7 (continued) — Final Table Restructuring and
Row-Click-to-Open.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT7 (continued) Record](MIGRATION_PLAN.md#phase-3b-uat7-continued--final-table-restructuring-and-row-click-to-open-2026-08-17).
Two further owner refinements, folded into the same pass as the
structured-details redesign below (still un-UAT'd as a whole). No new
DECISIONS.md entry.

**Final main-table columns**: `Recording | Start Time | Duration |
Sampling Rate(s) | Actions`. Station/Recorder/Channels/Imported are no
longer main-table columns; Sampling Rate(s) and Start Time were
promoted from Details (purely additive frontend formatting via two new
helpers, `formatRecordingStartTime()`/`formatSamplingRates()` — zero
backend change, every value already existed on `SourceSummaryOut`;
`formatSamplingRates()` renders every real rate, never simplifying a
genuine multi-rate source down to one value).

**Details reorganized (reversed direction)**: Technical zone (Recorder,
Channels, Nominal frequency, Timing reference, Samples — Recorder/
Channels moved back IN from the main table), Timing zone (Trigger,
Imported — Start Time moved OUT to the main table; Imported moved IN
from the old main-table column, `formatImportedAt()` reused unchanged),
Files zone (CFG, DAT, unchanged). A new shared
`.recording-details-zone-title` class gives each zone a quiet caption
now that the field count grew.

**Row-click-to-open**: the explicit "Open / Analyse" button was
removed. The recording `<tr>` itself (`tabindex="0"`, `role="button"`,
`aria-label` naming the action) is now the primary Open/Analyse target
— clicking it or pressing Enter/Space while focused calls the SAME
`openRecordingForAnalysis()` the old button called, no second
implementation. Actions is icon-only: Details reuses the app's existing
`.chevron` glyph (already used for Analog/Digital channel groups);
Remove reuses `&times;` (already this codebase's established close/
remove glyph elsewhere). Isolation: both buttons' click handlers call
`event.stopPropagation()`; the row's own keydown handler additionally
guards with `event.target !== row`, since a keydown bubbles up
independently of a focused button's native Enter/Space-to-click
conversion — verified by a dedicated test that dispatches a bubbling
keydown directly on the Details button. New CSS: `cursor: pointer` and
a `:focus-visible` outline on the row (reusing the pre-existing hover
rule, not duplicating it), staying visually distinct from the existing
`tr.recording-row-expanded` tint.

**Verification**: `phase3buat7_check.mjs` was substantially rewritten
for the final state — 22/22 passing. Existing-suite corrections across
`phase3b_check.mjs`, `phase3buat1_check.mjs`, `phase3buat3_check.mjs`,
`phase3buat4_check.mjs`, `phase3buat5_check.mjs`, and
`phase3buat6_check.mjs` (each had assumed the pre-restructuring column/
zone split or the three-button Actions column) — the full suite
otherwise returns to the exact same 20 pre-existing, already-documented
failures, zero new divergences. Backend: zero diff, 280/280 passing in
a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether row-click-to-open feels natural rather than accidental, and
whether the icon-only Actions column reads clearly without visible
tooltips — was NOT and cannot be confirmed in this sandboxed session;
this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT7 — Recording Details UX Redesign)

**Phase 3B-UAT7 — Recording Details UX Redesign.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT7 Record](MIGRATION_PLAN.md#phase-3b-uat7--recording-details-ux-redesign-2026-08-17).
No new DECISIONS.md entry.

**Owner feedback**: UAT6's `<table>`-grammar Details panel was
technically correct but rejected on UX grounds — read as "a second
spreadsheet," gave Start/Trigger Time no more room than any other
field, no visible connection to its parent row. A dedicated analysis
turn (three alternatives compared: inline facts strip, structured
two-zone panel, side inspector) preceded implementation; owner approved
**Option B — structured two-zone details**, plus a rule to remove
CFG/DAT filenames from the main Recordings table entirely.

**Main table**: `td.recording-name-cell` now shows only the logical
recording name — the `.recording-files` sub-line (CFG+DAT filenames)
was deleted. The search index still includes filenames even though
they're no longer visibly rendered, so filename search still works.

**Details panel — three zones, no table markup**: `renderRecordingDetails()`
was rewritten from `<table><thead>…` to (1) a `flex-wrap` "facts" strip
for Nominal frequency/Timing reference/Samples/Sampling rate(s), (2)
dedicated full-width Start/Trigger timing lines (fixing "timestamps
under-emphasized"), (3) a Files group separated by a quiet divider
(unchanged from UAT6). Start/Trigger still use the established
`.replace("T", " ")` technique — full microsecond precision preserved,
`new Date()` still never used.

**Row association**: a 3px `--accent` left bar on the details panel
plus a `--accent-wash-soft` tint on the parent row (new
`tr.recording-row-expanded` class, toggled by a new `findRecordingRow()`
helper) tie an open panel to its own row even with several expanded at
once — both existing theme tokens, no new hardcoded colors.

**Details interaction**: the toggle button keeps a stable "Details"
label at all times (no "Hide details" swap); it reuses the app's
existing `.chevron` disclosure glyph (already used for Analog/Digital
channel groups) with a new `[aria-expanded="true"] .chevron` rotation
rule, and has a transparent border by default to visually demote it
below Open/Analyse and Remove (both unchanged). `toggleRecordingDetails()`
no longer touches `textContent` — only `aria-expanded` changes.

**Verification**: 19 new frontend `jsdom` checks (`phase3buat7_check.mjs`)
+ five existing assertions corrected in place across `phase3auat3_check.mjs`,
`phase3b_check.mjs`, `phase3buat5_check.mjs`, `phase3buat6_check.mjs`
(each had assumed the now-superseded `<table>` grammar, text-swap
label, "Start time"/"Trigger time" zone labels, or main-row filename
line) — the full suite otherwise returns to the exact same 20
pre-existing, already-documented failures, zero new divergences.
Backend: zero diff, 280/280 passing in a fresh venv (unchanged — no new
field was needed, every rendered value already existed in
`SourceSummaryOut`).

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the accent-bar/row-tint association reads as intended, whether
the chevron rotation feels smooth, and whether the panel now feels
genuinely more polished — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3B-UAT6 — No Duplicate Metadata in Recording Details)

**Phase 3B-UAT6 — No Duplicate Metadata in Recording Details.** Full
detail:
[MIGRATION_PLAN.md — Phase 3B-UAT6 Record](MIGRATION_PLAN.md#phase-3b-uat6--no-duplicate-metadata-in-recording-details-2026-08-17).
No new DECISIONS.md entry (targeted refinement of the Phase 3B-UAT5
Details panel, same weight as UAT1–UAT5).

**Owner clarification**: the Phase 3B-UAT5 Details panel had been
repeating Recorder and Duration, both already visible as their own
columns in the main Recordings table. Rule: main table = quick
identification/summary metadata; expanded Details = supplementary
technical metadata not already shown in the main table.

**What changed**: `renderRecordingDetails()` no longer shows Recorder or
Duration — both stay exactly where they already were, untouched, in the
main table. The panel now shows only Nominal frequency, Timing
reference, Samples, Sampling rate(s), Start time, Trigger time, plus a
separate "Files" section listing CFG/DAT — matching the owner's own
mockup. Layout switched from vertical `.stat-grid` cards to one compact
horizontal `<table>` row (six columns, one data row), wrapped in an
`overflow-x: auto` container (same technique as `.recordings-table-wrap`)
so a narrow viewport scrolls rather than breaks Work Area's width.

**Dead code removed**: since this Details panel was the last remaining
caller of the old Waveform-sidebar-era `.stat-grid`/`.stat`/
`statCard()` machinery, and this pass moved it off that pattern too,
those CSS rules and the JS function were deleted (not left unused) —
stale comments referencing them were updated in place.

**Preserved**: the main Recordings table was not redesigned (same
columns, same data). Open/Analyse, Remove, search, and the expand/
collapse mechanism (multiple rows expandable at once, zero extra fetch)
are all unchanged from UAT5.

**Verification**: 9 new frontend `jsdom` checks (`phase3buat6_check.mjs`)
+ two existing scripts corrected in place: `phase3buat5_check.mjs`'s own
field-list/CSS-selector/leakage assertions (written for the now-
superseded UAT5 field list) were updated for the new layout;
`phase3auat3_check.mjs`'s `.stat`/`.stat .value` containment assertion
was retargeted to the new `.recording-details-table td`/
`.recording-details-file-name` rules (the old classes it checked no
longer exist). While writing the new test, discovered and worked around
a jsdom selector-engine quirk (`"tbody tr"` also matches a sibling
`<thead>`'s row for HTML tables) by using the native
`table.tBodies[0].rows` API instead. Full suite returns to the exact
same 20 pre-existing, already-documented failures, zero new divergences.

**Backend**: zero files changed — no new field was needed (Recorder/
Duration/Channels were already in `SourceSummaryOut`; this pass only
changed which already-available fields render where). **Real-browser
visual confirmation — whether the compact horizontal table reads
naturally and scrolls acceptably at narrow widths — was NOT and cannot
be confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT5 — Move Recording Metadata from Waveform to Recordings)

**Phase 3B-UAT5 — Move Recording Metadata from Waveform to Recordings.**
Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT5 Record](MIGRATION_PLAN.md#phase-3b-uat5--move-recording-metadata-from-waveform-to-recordings-2026-08-17).
No new DECISIONS.md entry (UI/data-relocation refinement within the
already-decided DEC-032 Recordings architecture, same weight as
UAT1–UAT3).

**What changed**: the Waveform Workspace Sidebar's vertical metadata
card stack (`.stat-grid`: Recorder, Nominal Frequency, Timing Mode,
Samples, Duration, Sampling Rate(s), Start Time, Trigger Time) was
removed from `renderChannels()`. The `.detail-header` identity block
(station name + filenames) was deliberately kept — active source
identification, not the metadata being relocated. Each Recordings row
gained a `[ Details ]` button (order: `[ Details ] [ Open / Analyse ]
[ Remove ]`) that expands a sibling `<tr class="recording-details-row">`
directly beneath that row, showing that exact recording's metadata —
reusing the existing `.stat-grid`/`statCard()` pattern verbatim, so its
established containment rules apply automatically. **Multiple rows may
be expanded at once** (documented design choice, not a single-open
accordion) — tracked in a `recordingsExpandedDetails` Set keyed by
`source_id`.

**Timing Mode investigation (owner's explicit critical ask)**:
confirmed via direct inspection of `backend/app/domain/timing.py` and
its existing frontend consumer (`wwTimeModesForChannel()`) that
`timing_reference` is genuine, permanent, source-level recording
metadata parsed once from the COMTRADE record at import time —
architecturally distinct from `ww.timeMode` (the user's live Absolute/
Elapsed *view* toggle). Safe to relocate, but relabeled "Timing
reference" (was "Timing mode") specifically to remove the ambiguity
risk the owner flagged.

**Zero extra backend activity**: `SourceSummaryOut` gained
`timing_reference`/`start_time`/`trigger_time`/`sampling_rates` — purely
additive, already-computed domain fields, no new storage/computation.
The Details panel renders entirely from the already-fetched
`GET .../sources` list response — expanding/collapsing is a pure
client-side toggle with zero fetch, zero reparse, zero re-upload, zero
`.../channels` request.

**Multi-recording correctness**: each details row is built from its own
loop iteration's `source` object (never a shared/global reference), so
there is no cross-row metadata leakage — confirmed by a dedicated test
with two recordings carrying different recorder names.

**Unaffected**: Open/Analyse, Remove, search all work as before.
`performRemoveSource()` now also drops the removed id from
`recordingsExpandedDetails`; `applyRecordingsSearchFilter()` now also
hides/shows each row's sibling details row in lockstep, so a filtered-
out row's details panel can never remain visible as an orphan.

**Verification**: 14 new frontend `jsdom` checks
(`phase3buat5_check.mjs`) + four existing scripts corrected in place
(`phase3auat3_check.mjs`'s recorder-name assertion, which described the
now-removed Waveform-sidebar metadata; `phase3b_check.mjs`/
`phase3buat1_check.mjs`/`phase3buat3_check.mjs`'s row-count selectors,
which now also match each row's own sibling details row) + six scripts'
mock `GET .../sources` fixtures extended with the four new fields — the
full suite otherwise returns to the exact same 20 pre-existing,
already-documented failures, zero new divergences. Backend: one
additive test (`test_list_includes_timing_reference_and_timestamps`),
280/280 passing (279 baseline + 1 new).

**Backend**: `backend/app/schemas/source.py` (additive fields only),
`backend/tests/test_sources_api.py` (one new test). **Real-browser
visual confirmation — the expanded Details panel's spacing/grid
wrapping at narrow widths and Light/Dark appearance — was NOT and cannot
be confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT4 — Recordings as Default Entry Page)

**Phase 3B-UAT4 — Recordings as Default Entry Page.** Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT4 Record](MIGRATION_PLAN.md#phase-3b-uat4--recordings-as-default-entry-page-2026-08-17),
[DECISIONS.md — DEC-033](DECISIONS.md#dec-033--recordings-is-the-applications-default-fresh-entry-page-no-separate-landingdashboard-page-phase-3b-uat4).

**What changed**: a fresh visit to the app now shows the Recordings
page ("Recording Events") by default instead of an empty Waveform
workspace — `shell.currentPage`'s default value changed from
`"waveform"` to `"recordings"`, applied via `shellSetCurrentPage
("recordings")` called explicitly near the start of Init (the SAME
function every other navigation already goes through). The static HTML
defaults (`#workspaceRow` now starts `hidden`, `#pageRecordings` no
longer does, `aria-current` on the two Main Sidebar Menu buttons
swapped) were kept hand-in-sync to avoid any flash of the old default.
The old unconditional trailing `refreshAllSourceViews()` call at the
end of Init was removed — the Recordings list is now populated exactly
once, via `shellSetCurrentPage`'s own existing branch for that.

**No landing/dashboard page was added** — Recording Events remains the
operational entry page (a future dashboard is an open question, not
built now). **No routing framework was introduced** — the app has no
URL-aware navigation at all; this is a single default-state change, not
a router.

**Unaffected**: `shellSetCurrentPage()` itself is unmodified, so
Recordings ⇆ Waveform navigation still preserves viewport, layout mode,
Custom Groups, panel heights, and time mode with zero refetch — reused
the exact "hide, don't destroy" mechanism established since Phase 3A/
3B, confirmed by test with a full multi-hop round trip. The Global
Header is untouched by this specific pass (Phase 3B-UAT2/UAT3 already
relocated page-specific actions off it).

**Verification**: 8 new frontend `jsdom` checks (`phase3buat4_check.mjs`)
+ one existing assertion in `phase3buat2_check.mjs` corrected in place
(it had implicitly assumed Waveform was the default page) — the full
suite otherwise returns to the exact same 20 pre-existing, already-
documented failures, zero new divergences. Backend: zero diff, 279/279
passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether a fresh page load genuinely shows Recordings with no visible
flash of the old Waveform default — was NOT and cannot be confirmed in
this sandboxed session; this remains explicitly for the owner's own
manual UAT.**

## What was done in the prior session (Phase 3B-UAT3 — Recordings Header Action Cleanup)

**Phase 3B-UAT3 — Recordings Header Action Cleanup.** Two small
refinements following directly from Phase 3B-UAT2's own relocation
work. Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT3 Record](MIGRATION_PLAN.md#phase-3b-uat3--recordings-header-action-cleanup-2026-08-17).

**Order**: "Start new workspace" and "Upload New" (already grouped in
`.recordings-header-actions` since UAT2) were reordered to `[ Start new
workspace ] [ Upload New ]` per the owner's preferred layout. Upload
New stays visually primary (unclassed button); Start new workspace
stays `.secondary`. No "Import" button exists anywhere — confirmed by
test, not re-added (it was already fully removed in UAT2).

**Button typography**: `.secondary` (0.8rem) and `.danger` (0.78rem)
were two near-duplicate literal font-sizes for the same "compact
action" tier (frequently paired in the same row, e.g. Recordings' Open
/ Analyse + Remove) — consolidated into one shared
`--button-font-size-compact: 0.8rem` token. The primary button size
(0.9rem) and toolbar/segmented-control size (0.76rem, theme.css)
remain their own deliberately distinct, untouched tiers.

**Verification**: 13 new frontend `jsdom` checks
(`phase3buat3_check.mjs`) + the full existing Phase 1 through Phase
3B-UAT2 suites — the exact same 20 pre-existing, already-documented
failures, zero new divergences (no existing test needed correction this
pass). Backend: zero diff, 279/279 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the reordered actions read correctly, and whether the (very
small, 0.8rem vs 0.78rem) font-size unification is visually
imperceptible as intended — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3B-UAT2 — Remove Duplicate Waveform-Page Import / New-Workspace Actions)

**Phase 3B-UAT2 — Remove Duplicate Waveform-Page Import / New-Workspace
Actions.** The owner established a clearer page-responsibility split:
Recordings owns recording/session management (upload/import, Open/
Analyse, Remove, and now whole-workspace lifecycle); Waveform stays
analysis-only. Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT2 Record](MIGRATION_PLAN.md#phase-3b-uat2--remove-duplicate-waveform-page-import--new-workspace-actions-2026-08-17).

**What changed**: the Global Header's own "Import" shortcut
(`#shellImportBtn`, and `shellOpenImport()`) was removed entirely —
Recordings' own "Upload New" already opens the identical modal, so a
second header-level entry point was redundant. "Start new workspace"
(`#newWorkspaceButton`/`#workspaceResetError`) was relocated — same
IDs, same completely unchanged `startNewWorkspace()`/
`resetToNewWorkspace()` lifecycle logic — from the Global Header onto
the Recordings page's own header row, grouped with "Upload New" in a
new `.recordings-header-actions` wrapper (`.recordings-header` gained
`flex-wrap: wrap` for safe narrow-width wrapping). "Clear workspace"
(Waveform toolbar) is untouched and remains distinct — confirmed by
test it never calls the whole-workspace DELETE endpoint.

**Verification**: 14 new frontend `jsdom` checks
(`phase3buat2_check.mjs`) + three existing test files corrected in
place where they referenced the now-intentionally-removed
`#shellImportBtn`/`shellOpenImport()` — the full suite otherwise
returns to the exact same 20 pre-existing, already-documented failures,
zero new divergences. Backend: zero diff, 279/279 passing in a fresh
venv.

**Backend**: zero files changed — a pure UI-relocation task. **Real-
browser visual confirmation — whether the Waveform header now reads as
appropriately simplified, and whether the Recordings page's grouped
actions read clearly with Upload New still visually primary — was NOT
and cannot be confirmed in this sandboxed session; this remains
explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B-UAT1 — Recording Row Divider Alignment)

**Phase 3B-UAT1 — Recording Row Divider Alignment.** Owner manual UAT
of the Recordings page found one cosmetic issue: the Actions column's
bottom row divider sat higher than the divider under the other columns
instead of one continuous line. Full detail:
[MIGRATION_PLAN.md — Phase 3B-UAT1 Record](MIGRATION_PLAN.md#phase-3b-uat1--recording-row-divider-alignment-2026-08-17).

**Root cause**: the Actions `<td>` carried `.recording-actions`
directly, and that class sets `display: flex` — overriding the cell's
`display` away from `table-cell` and removing it from the browser's
normal same-row-height cell-stretching, so it collapsed to its own
shorter content height while sibling cells stretched to the row's
tallest cell.

**Fix**: the flex layout now lives on an inner `<div
class="recording-actions">` inside a plain, unclassed `<td>` — the
`<td>` itself is a normal table-cell again, stretching/aligning its
border like every other cell. No column widths, button behavior,
Open/Analyse/Remove handlers, search, Phase 3A-UAT4 containment, or
responsive scrolling changed.

**Verification**: 7 new frontend `jsdom` checks
(`phase3buat1_check.mjs`) + the full existing Phase 1 through Phase 3B
suites — the exact same 20 pre-existing, already-documented failures,
zero new divergences. Backend: zero diff, 279/279 passing in a fresh
venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the divider now reads as one continuous line across the full
table width — was NOT and cannot be confirmed in this sandboxed
session; this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3B — Recordings Page and Upload Workflow)

**Phase 3B — Recordings Page and Upload Workflow.** Following the
owner's own "finish this area before introducing additional features"
direction, `oruxa_powerwave` gained a dedicated Recordings page,
benchmarked (layout/workflow only, per the pre-existing DEC-020 Detego
Benchmark Principle) against Detego's own Recordings page. Full detail:
[MIGRATION_PLAN.md — Phase 3B Record](MIGRATION_PLAN.md#phase-3b--recordings-page-and-upload-workflow-2026-08-16),
[DECISIONS.md — DEC-032](DECISIONS.md#dec-032--recordings-page-as-a-first-class-application-page-one-recording--one-logical-event-cfgdat-sessionworkspace-backed-not-a-persistent-cloud-library-phase-3b).

**Navigation**: `shell.currentPage` (`"waveform"` | `"recordings"`) is
new app-shell state, kept deliberately separate from `shell.activeView`
(unchanged, still scoped to Table/Split sub-views WITHIN the Waveform
page). Main Sidebar Menu's "Workspace" item was renamed "Waveform"; a
new, real (not `disabled`) "Recordings" item was added right after it.
`shellSetCurrentPage()` toggles `#workspaceRow`/`#pageRecordings`
visibility using the exact same "hide, don't destroy" mechanism Phase
3A's `shellSetActiveView()` already established for Table/Split — the
entire waveform workspace (panels, live Plotly instances, Workspace
Sidebar) is only ever hidden, never rebuilt, when navigating to
Recordings.

**Waveform state preservation, confirmed by test**: the physical
viewport (byte-identical), layout mode, Custom Groups, panel heights,
and time mode all survive a Waveform → Recordings → Waveform round-trip
exactly, with zero waveform refetch caused by the navigation itself.
Returning to Waveform schedules `wwScheduleResizeAllVisiblePlots()`
(reusing Phase 3A-UAT1/UAT3's own helper — no new mechanism) in case the
available width changed while the page was hidden — the same staleness
risk Phase 3A-UAT3's Finding E already identified for the Table/Split
case, recurring one level up here.

**Recording abstraction**: one `SourceSummaryOut` (already one CFG+DAT
pair, per the backend's existing model) is always exactly one
Recordings row — never separate rows for the companion files, confirmed
by test. `recordingDisplayName()` prefers the real `station_name`,
falling back to the CFG filename only when blank — never invents a
fault classification or description.

**Recordings page**: heading "Recording Events," a searchable table
(Recording name+filenames / Station / Recorder / Channels / Duration /
Imported / Actions — "Format" and a separate "Station" column were both
deliberately omitted this phase, reasoned through in the MIGRATION_PLAN
record), an "Upload New" button, and a "No recordings loaded" empty
state. No contextual Workspace Sidebar on this page (section 21's own
preference). Long recording names/filenames reuse Phase 3A-UAT4's
`overflow-wrap: anywhere`/`min-width: 0` containment technique; the
table sits in an `overflow-x: auto` wrapper reusing Phase 3A-UAT3's
Finding B technique.

**Upload workflow — ONE implementation**: the always-visible "Import
COMTRADE Event" form was removed from the Workspace Sidebar; its exact
validation/upload logic was refactored (not duplicated) into a single
extensible modal, opened by both the Recordings page's "Upload New" and
the Global Header's "Import" shortcut (which now navigates to Recordings
first). The modal's file-input fields are rendered from a small
`RECORDING_FORMATS` provider model (`{id, label, enabled, files}`) —
COMTRADE is the only `enabled: true` entry (same two required cfg/dat
inputs, same ~100 MB guidance, same `POST .../sources` multipart
contract, same error mapping as before); CSV and Excel are listed as
real but `disabled` `<option>`s, proving forward-readiness without
implementing either parser. Double-submit and mid-upload dismissal are
both guarded by an explicit `uploadModalSubmitting` flag. On success,
the modal closes and clears its own status immediately — no
auto-navigation to Waveform, no auto-selecting the source into the
Channels panel (that's the Recordings row's own "Open / Analyse" action,
per the task's own preferred upload → list → user-chooses flow).

**Row actions**: "Open / Analyse" calls the existing `selectSource()`
unchanged and navigates to Waveform (no auto-display of channels — the
existing checkbox + "Add selected" step is untouched). "Remove" reuses
the existing confirmation-and-delete flow (`requestRemoveSource()`/
`performRemoveSource()`) completely unchanged, now updating the
Recordings list, the Workspace Sidebar, and the waveform-displayed-
channel state consistently from one shared refresh
(`refreshAllSourceViews()`) — there is no second, independently-drifting
recording repository; both presentations read the same
`GET .../sources` response.

**Backend change — additive only**: `SourceSummaryOut` gained
`duration_seconds`/`sample_count` (both already computed/stored on
`SourceMetadata` since Phase 2A; no new storage, no new computation) so
the Recordings list's Duration column doesn't need a separate
`.../channels` fetch per row.

**Storage semantics — explicitly unchanged**: the Recordings page is
session/workspace-backed only, reflecting the current in-memory
`WorkspaceRegistry` — no database table, no persistent cloud file
library, no upload history across sessions. Persistent recording
retention remains a separate future decision, per DEC-032.

**A real CSS bug caught before shipping**: `#workspaceRow` and the
Status Bar's waveform-only items both have author `display: flex` CSS,
which beats the UA stylesheet's default `[hidden] { display: none }`
rule by origin regardless of specificity — without explicit `[hidden]`
override rules (now added for both), this phase's own `.hidden = true`
toggles would have had zero visible effect. Caught by manual CSS review,
not by the test suite (jsdom has no real layout engine and cannot
detect this class of bug).

**Verification**: 30 new frontend `jsdom` checks (`phase3b_check.mjs`)
+ two existing test files corrected in place where Phase 3B's own
deliberate UX changes (no persistent success banner outside the modal;
the old sidebar form's removal) made their prior assertions test
since-removed behavior — the full suite otherwise returns to the exact
same 20 pre-existing, already-documented failures, zero new
divergences. Backend: `test_sources_api.py` gained two new/extended
assertions for the new fields; 279/279 passing (278 + 1 new test), zero
regressions.

**Backend**: one small, additive schema change only (see above) —
`SourceSummaryOut` gained two fields; no endpoint, table, or persistence
semantics added. **Real-browser visual confirmation — whether the
Recordings page reads as clear/simple/engineering-focused, whether the
upload modal's format selector feels natural, and whether long-filename
wrapping in the Recording column looks right at real widths — was NOT
and cannot be confirmed in this sandboxed session; this remains
explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3A-UAT4 — Channel Filename Containment)

**Phase 3A-UAT4 — Channel Filename Containment.** Owner manual UAT of
Phase 3A-UAT3's overflow hardening found one remaining real overflow
case, with browser evidence: in the Workspace Sidebar's Channels →
source-detail section, uploaded CFG/DAT filenames (e.g.
`260725_1309444309_Tanjung Bin BEN6K.cfg`/`.dat`) could still visibly
extend past the Channels panel at a narrowed Sidebar width — despite
Phase 3A-UAT3's own Finding C already having added `overflow-wrap:
anywhere` to the filename text elements. Full detail:
[MIGRATION_PLAN.md — Phase 3A-UAT4 Record](MIGRATION_PLAN.md#phase-3a-uat4--channel-filename-containment-2026-08-16).

**Root cause (established by code inspection, not guessed)**:
`.detail-header` is a flex CONTAINER with a single flex-item child — an
unnamed, unstyled wrapping `<div>` holding the station-name `<h3>` and
the filenames `.meta`. Phase 3A-UAT3's Finding C fix put
`overflow-wrap: anywhere` on the TEXT elements but never gave their
PARENT flex item its own `min-width: 0`. A flex item's automatic
minimum width defaults to its content's un-shrunk min-content size (the
well-known `min-width: auto` flex trap — the exact same class of bug
already fixed at the SHELL level in Phase 3A-UAT1/UAT3, recurring one
level deeper here, inside the Channels detail card). Text-level wrap
rules only take effect once the box AROUND the text can actually become
narrower than its unwrapped content — without that, the whole
station-name + filenames block stayed at full width regardless of the
text's own `overflow-wrap` setting. `white-space` inheritance and
inline/span wrapping issues were both checked and ruled out.

**Fix**: the previously-unnamed flex-item wrapper now has a real class,
`.detail-header-info` (`min-width: 0; max-width: 100%;` — the actual
root-cause fix). `.detail-header h3`/`.meta` additionally gained
explicit `white-space: normal; max-width: 100%;` alongside their
existing `overflow-wrap: anywhere` — belt-and-braces caps at every link
in the chain. No truncation, no ellipsis, no shortened/fake filename
string — the full CFG/DAT filename remains completely readable, now
correctly wrapping across multiple lines at narrow widths.
`word-break: break-word` was deliberately NOT added — `overflow-wrap:
anywhere` alone is sufficient (it, unlike `break-word`, is specified to
also reduce the element's own min-content contribution).

**Verification**: 12 new frontend `jsdom` checks
(`phase3auat4_check.mjs` — the owner's own exact CFG/DAT filenames, a
longer underscore-heavy/unbroken-token stress fixture, and a
520px/320px/240px Sidebar-width matrix) + the full existing Phase 1
through Phase 3A-UAT3 suites — the exact same 20 pre-existing,
already-documented failures, zero new divergences. Backend: zero diff,
278/278 passing in a fresh venv.

**Scope discipline**: filename containment only — Workspace Sidebar
resize bounds, Main Workspace reflow, Plotly resizing, Grouped/Separate/
Custom, the sticky ruler, panel-height resize, the responsive drawer,
Custom Groups, and header/status-bar layout are all confirmed unchanged
by test.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the filename now visibly wraps exactly as the owner's own
reference example showed — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3A-UAT3 — Targeted Overflow and Containment Fixes)

**Phase 3A-UAT3 — Targeted Overflow and Containment Fixes.** An
independent Codex audit of the Phase 3A shell (run against a local
working tree that could not reach GitHub — SSH authentication failure)
identified seven candidate overflow/containment risks. Per this task's
own explicit instruction, every finding was independently re-verified by
direct code inspection against canonical `main` (synced via this
session's own established HTTPS fallback) before anything was
implemented — none of the audit's conclusions were trusted blindly. Full
detail:
[MIGRATION_PLAN.md — Phase 3A-UAT3 Record](MIGRATION_PLAN.md#phase-3a-uat3--targeted-overflow-and-containment-fixes-2026-08-16).

**Audit revalidation result: all seven findings confirmed STILL PRESENT
and fixed — none rejected as invalid or already-fixed.**

- **A (responsive sidebar reopen button)**: `#shellSidebarToggleBtn {
  display: none; }` sat *after* its own `@media (max-width: 900px)`
  override in source order; equal specificity meant the later,
  unconditional rule always won, permanently hiding the reopen button
  even inside the drawer breakpoint. Fixed by reordering (base rule
  first, override second) — no `!important`.
- **B (sidebar channel table containment)**: `.group-body` (wrapping
  both analog sub-grouped and digital ungrouped channel tables) gained
  `overflow-x: auto` — an overly wide table (several columns + a
  `nowrap` action link) was previously at risk of being silently CLIPPED
  by the outer `details.channel-group`'s own `overflow: hidden`, not
  just untidy.
- **C (source/detail metadata containment)**: `.detail-header
  h3`/`.meta` and `.stat .value` gained `overflow-wrap: anywhere`;
  `.stat` (a CSS Grid item) gained `min-width: 0` — long unbroken
  station-name/filename/recorder-name/sampling-rate tokens now wrap in
  place instead of risking forcing the Sidebar wider.
- **D (modal / Custom Groups containment)**: Custom Groups chips now
  wrap their channel-name+unit text in a dedicated `<span
  class="group-chip-label">` (JS markup change, mirroring the
  established `.ww-legend-label` pattern) with `min-width: 0;
  overflow-wrap: anywhere;`; `.group-chip` gained `max-width: 100%`;
  `.confirm-box p` gained `overflow-wrap: anywhere`; `.group-editor-box`
  gained `overflow-x: hidden` (defense-in-depth, mirroring the Phase
  3A-UAT1 `.ww-chart-wrap` precedent).
- **E (waveform view visibility reflow)**: `shellSetActiveView()` now
  calls the existing `wwScheduleResizeAllVisiblePlots()` (Phase
  3A-UAT1's own helper, no new mechanism) whenever the active view
  becomes `"waveform"` — a width change while Waveform was hidden behind
  the Table/Split placeholder (still fully reachable, since sidebar/
  window resize isn't gated by active view) no longer leaves Plotly's
  charts stale once Waveform becomes visible again.
- **F (responsive drawer-width override)**: `shellCreateHorizontalSplit()`
  persists the desktop Workspace Sidebar width as an inline `style.width`
  (highest CSS specificity short of `!important`), which unconditionally
  beat the drawer breakpoint's own `width: min(320px, 82vw)` rule. Fixed
  via a `window.matchMedia("(max-width: 900px)")` listener that clears
  the inline width on entering drawer mode and restores it exactly on
  returning to desktop — the persisted preference itself is never
  mutated.
- **G (Grouped/Custom legend containment)**: base (unscoped)
  `.ww-legend-item`/`.ww-legend-label` gained the same
  containment/ellipsis technique the already-owner-approved Separate-
  mode overlay tag uses — added as a separate, lower-specificity rule so
  `#wwPanels.ww-panels-unified .ww-legend-item/-label` (Separate mode,
  already passed UAT) is completely untouched.

**Scope discipline**: no shell restructuring, no Table/Split/digital-
channel work, no backend change, no broad CSS normalization — every
rule/JS change is scoped to exactly the selector or call site its
finding named.

**Test-infrastructure fix, not an application change**: jsdom has no
`window.matchMedia` implementation at all; since Finding F's fix calls
it unconditionally at Init, all 16 existing scratch scripts that run the
real inline script needed a polyfill (minimal but real — evaluates
`max-width: Npx` against a mutable `window.innerWidth`, fires `'change'`
via a `window.__setInnerWidth(px)` test helper) or their `<script>` tag
would throw and abort partway through — the same failure class Phase
3A-UAT1 hit with the missing `requestAnimationFrame` polyfill. One
script (`frontend_logic_check.mjs`) also needed a `requestAnimationFrame`
polyfill it had never previously required.

**Verification**: 29 new frontend `jsdom` checks
(`phase3auat3_check.mjs`, using deterministic long-unbroken-token
fixtures for filenames/station names/recorder names/channel names/
units/group names/sample-rate text) + the full existing Phase 1 through
Phase 3A-UAT2 suites (293 checks, after the polyfill fix) — the exact
same 20 pre-existing, already-documented failures, zero new divergences.
Backend: zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether each fix looks correct at real, continuous viewport widths (not
just the discrete values a `matchMedia` polyfill can simulate), and
whether the horizontal-scroll/wrap/ellipsis choices read well visually
— was NOT and cannot be confirmed in this sandboxed session; this
remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3A-UAT2 — Remove Duplicate Header Theme Control)

**Phase 3A-UAT2 — Remove Duplicate Header Theme Control.**
Phase 3A-UAT1's width-reflow fix passed owner UAT; that issue is
closed. The owner then requested one small, isolated UI cleanup: the
Global Header's own Light/Dark segmented control (`#themeToggle`)
duplicated the Main Sidebar Menu's existing "Settings" item, which
already flips the same theme preference. Full detail:
[MIGRATION_PLAN.md — Phase 3A-UAT2 Record](MIGRATION_PLAN.md#phase-3a-uat2--remove-duplicate-header-theme-control-2026-08-16).

**What was built**: removed the `<div id="themeToggle"></div>` element
from `#globalHeaderActions` in the Global Header, and removed the
corresponding `window.PowerwaveTheme.mountThemeToggle(...)` call from
Init. `#globalHeaderActions` is a plain `flex; gap: 10px` row with no
reserved placeholder width, so the gap closed cleanly with zero CSS
change needed. **The Main Sidebar Menu's "Settings" item is now the
sole theme entry point** in `index.html`. Neither the shared
`.theme-toggle` CSS class (also used by the unrelated `#shellViewToggle`
Waveform/Table/Split selector) nor `theme.js`'s `mountThemeToggle()`
function itself were touched — `frontend/waveform-prototype.html` (a
separate page, out of scope) still mounts and uses the latter unchanged.
A stale code comment on the Settings click handler, which referenced
the now-removed header control, was corrected.

**Theme behavior — unchanged, confirmed by test**: persistence
(`localStorage` key `powerwave.theme`), cross-tab `storage`-event sync,
the `powerwave:theme-change` `CustomEvent`, Plotly's per-panel
`relayout`/`restyle` re-color, and zero waveform refetch on a theme
change all still work exactly as before, since they are consumed via
`window.PowerwaveTheme` directly and were never dependent on the
removed toggle's own internal state.

**Verification**: 11 new frontend `jsdom` checks
(`phase3auat2_check.mjs`) + one pre-existing `theme_crosshair_check.mjs`
check corrected in place (it asserted `#themeToggle` exists in
`index.html`, no longer true by design) + the full existing Phase 2C-A
through Phase 3A-UAT1 suites — the exact same 20 pre-existing,
already-documented failures, zero new divergences. Backend: zero diff,
278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the header now reads cleanly with no leftover gap, and whether
Settings remains comfortably reachable/usable in both Main Sidebar Menu
states — was NOT and cannot be confirmed in this sandboxed session; this
remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 3A-UAT1 — Responsive Waveform Width Reflow)

**Phase 3A-UAT1 — Responsive Waveform Width Reflow.** Phase 3A's shell
STRUCTURE passed owner UAT (geometry correct, Workspace Sidebar resize
itself works). One child-layout bug was found: when the Workspace
Sidebar widened, Main Workspace correctly became narrower, but the
Plotly waveform canvas did not reflow to fit — it could visually
extend beyond its own panel frame. Full detail:
[MIGRATION_PLAN.md — Phase 3A-UAT1 Record](MIGRATION_PLAN.md#phase-3a-uat1--responsive-waveform-width-reflow-2026-08-16).

**Root cause (established by code inspection, not guessed)**:
`shellCreateHorizontalSplit()`'s own original comment incorrectly
assumed Plotly's `responsive: true` config would automatically detect
this kind of resize. It doesn't — `responsive: true` reliably reacts
to actual `window` resize events, but a sibling flex item (the
Workspace Sidebar) growing/shrinking never fires one. The CSS
`min-width: 0` chain was already correct everywhere it mattered (the
CONTAINER genuinely shrank); Plotly was simply never told to redraw,
so its stale, wider rendered SVG visually overflowed its own
(correctly-sized) `.ww-chart-wrap`, which had no `overflow` rule to
contain it.

**Fix**: `shellCreateHorizontalSplit()` was rewritten to rAF-coalesce
an `options.onResize(width)` callback, reusing the EXACT established
Phase 2C-C2A pattern (cheap width write on every raw pointermove;
the callback coalesced to at most once per animation frame; one
authoritative final call on pointerup/pointercancel). A new
`wwResizeAllVisiblePlots()` reflows every panel in `ww.panels`
(Grouped/Separate/Custom alike, reusing the existing
`wwResizePanelPlot()` per panel) plus the sticky ruler — presentation-
only, never touches `ww.viewport`, Y range, trace data, or the fetch
pipeline. Wired into three trigger points: the Workspace Sidebar's own
`onResize`; a `transitionend` listener on `#mainSidebarMenu` (guarded
to `propertyName === "width"` — the correct signal an animated
collapse/expand's width has actually finished changing, not a guessed
timeout); and a defensive `window.resize` listener (rAF-coalesced),
added since Plotly's own internal detection had just proven unreliable
for a related case. `.ww-chart-wrap` also gained `overflow: hidden` as
a defense-in-depth safety net (a no-op once the resize fix itself is
correct, per this task's own "the chart must actually resize
correctly, don't merely hide a stale width" instruction — the resize
fix is primary, this is a safety net).

**Test-infrastructure fix, not an application change**: this fix's own
rAF-coalescing means `shellCreateHorizontalSplit()` now calls
`requestAnimationFrame` unconditionally at Init time (every real
browser has this natively). Re-running the full jsdom suite revealed
six OLDER scratch scripts (`phase2ca_check.mjs`,
`phase2cb1/b2/b3/b3a_check.mjs`, `phase2cc1_check.mjs`) were missing
the `requestAnimationFrame`/`cancelAnimationFrame` polyfill later
scripts already have (from `phase2cc2_check.mjs` onward, once panel-
height resize needed it) — this silently aborted their ENTIRE inline
`<script>` evaluation partway through Init, cascading into dozens of
unrelated-looking failures on first run. Patched all six with the
exact same polyfill line already used elsewhere; the suite returns to
the identical 20-failure baseline from immediately before this task —
zero new divergences from the actual code change, confirmed by
re-running before/after, not assumed.

**Verification**: 20 new frontend `jsdom` checks
(`phase3auat1_check.mjs`) + the full existing Phase 2C-A through Phase
3A suites (264 checks, after the polyfill fix) — the exact same
pre-existing 20 failures, zero new. Backend: zero diff, 278/278 passing
in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the waveform canvas genuinely stays visually contained during a
real drag, whether the reflow feels smooth rather than janky, and
whether the `transitionend`-triggered Main Sidebar Menu reflow looks
correct in practice — was NOT and cannot be confirmed in this
sandboxed session; this remains explicitly for the owner's own manual
UAT.**

## What was done in the prior session (Phase 3A — Application Shell Redesign Foundation)

**Phase 3A — Application Shell Redesign Foundation.** The first
STRUCTURAL redesign of the frontend: the whole-page-scrolling, 2-column
centered layout (`main { max-width: 1100px; margin: 0 auto }`) is
replaced by a full-viewport application shell. Full detail:
[MIGRATION_PLAN.md — Phase 3A Record](MIGRATION_PLAN.md#phase-3a--application-shell-redesign-foundation-2026-08-16),
[DECISIONS.md DEC-031](DECISIONS.md#dec-031--application-shell-architecture-global-header-full-height-main-sidebar-menu-work-area-workspace-row--bottom-status-bar-phase-3a).

**Owner design principle**: "the active analysis area / waveform canvas
must dominate the screen" — clear, simple, compact, minimal clutter,
scalable for future engineering functions. Detego named as the UI/UX/
layout benchmark only (never branding/colors/typography/
implementation, per the existing DEC-020 Detego Benchmark Principle).

**Corrected shell hierarchy** (the owner explicitly corrected an
earlier, wrong interpretation mid-specification):
```
App
├── Global Header                      (full application width)
└── Body
    ├── Main Sidebar Menu               (FULL Body height)
    └── Work Area
        ├── Workspace Row               (Workspace Sidebar ⇆ Main Workspace)
        └── Bottom Status Bar           (beside Workspace Row only,
                                          never beneath Main Sidebar Menu)
```
This is a real DOM/CSS nesting: Main Sidebar Menu and Work Area are the
two direct flex children of `#appBody`; the Status Bar/Workspace Row
split happens ONE LEVEL DEEPER, inside Work Area — this specific
nesting depth (not pixel matching) is what structurally guarantees the
Status Bar can never render beneath Main Sidebar Menu. The task's own
instructions explicitly labeled the alternative (a full-width status
bar beneath everything) "Incorrect."

**Main Sidebar Menu**: narrow icon rail (52px collapsed/184px
expanded), collapsed by default, toggled via a button — never freely
drag-resizable (a deliberately different interaction model from the
Workspace Sidebar, and its state is deliberately independent of
Workspace Sidebar width — section 21's own explicit requirement).
Items: "Workspace" (the one real destination, `aria-current="page"`);
"Table"/"Tools"/"Reports" (visibly present, `disabled`, clearly marked
"coming soon" — proves the rail holds multiple items without inventing
fake pages); "Settings" (real — flips the existing Light/Dark
preference). Small hand-authored inline SVG icons, zero new dependency.

**Workspace Sidebar**: contextual to the active engineering workspace
(Import/Sources/Channels, relocated unredesigned — same IDs, same
logic), explicitly NOT global navigation. Horizontally drag-resizable
via a new small, REUSABLE split-pane helper
(`shellCreateHorizontalSplit()` — default 320px/min 240px/max 520px,
explicit state persisted to `localStorage` for the session, zero
waveform refetch by construction). The SAME function a future
Waveform ⇆ Table split is expected to reuse (section 10/22) — not a
generic layout framework, deliberately small.

**Main Workspace**: Workspace Toolbar (unchanged controls; "Clear
workspace" relocated into it, the old separate heading row removed as
redundant) above an Active View Area holding `shell.activeView`
(`"waveform"`|`"table"`|`"split"` — app-shell state, deliberately
separate from waveform-domain state `ww`, per section 28's own explicit
instruction — the shell never reads/writes `ww` directly). Waveform is
real; Table/Split are structural placeholders only — confirmed by test:
zero fake data, zero new fetches when switched to.

**Sticky Time Axis**: preserved exactly (Phase 2C-C4B's accepted
compact layout, unchanged). Its scrolling ancestor changed from the
whole page to `#activeViewArea` specifically (every shell region now
has its own internal scroll) — functionally identical `position:
sticky` behavior, just a more contained scrolling context.

**Bottom Status Bar**: real values only — workspace id (moved from the
old page footer), source station name, sample rate, duration (from the
same already-fetched `renderChannels()` data, no new API call), and
displayed-channel count (`ww.displayed.size`, read-only). Cursor A/B,
Delta Cursor, fault/event state are explicitly NOT shown — deferred to
documentation, never fabricated.

**Responsive strategy**: desktop/laptop is the unconditional primary
target (the shell above applies with no alteration). Under ~900px, Main
Sidebar Menu force-collapses and Workspace Sidebar becomes a reopenable
overlay drawer (pure CSS `position: absolute` against `#workspaceRow`
itself, not `fixed` against the viewport — avoids needing the header's
own height). Under ~640px, header/status-bar spacing tighten further.
Main Workspace always gets the space freed by a collapsed/hidden
secondary region. Phone is a secondary companion mode per the owner's
own explicit framing, not fully designed this phase — only structurally
un-blocked.

**Existing control inventory — what moved** (section 27): "Waveform
Workspace" heading removed (redundant); "Clear workspace" moved into
the Workspace Toolbar; "Workspace: <id>" + "Start new workspace" moved
from the page footer into the Bottom Status Bar / Global Header
respectively; Import/Sources/Channels moved from the old 2-column page
grid into the Workspace Sidebar, unredesigned internally. Everything
else kept its exact element ID, only its container moved.

**Verification**: 40 new frontend `jsdom` checks (`phase3a_check.mjs`)
+ the FULL existing Phase 2C-A through 2C-C4B suites (224 checks)
re-run unmodified — **the exact same pre-existing pass/fail counts as
immediately before this phase (20 already-documented failures, zero
new divergences), independently confirmed before/after, not assumed**.
This held because every existing waveform element kept its exact ID
and internal DOM relationships — only its container moved. Backend:
zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
actual proportions, resize feel, Main Sidebar Menu's collapsed width,
and the entire responsive/drawer behavior at real narrow viewport
widths — was NOT and cannot be confirmed in this sandboxed session;
this remains explicitly for the owner's own manual UAT. This is
explicitly an INITIAL shell per the task's own framing — the owner's
UAT is expected to adjust dimensions/spacing, not just confirm the
structure.**

## What was done in the prior session (Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction)

**Phase 2C-C4B — Compact Sticky Time-Axis Layout Correction.**
**Phase 2C-C4's sticky ruler functionality passed owner UAT.**
**Phase 2C-C4A's visual LAYOUT failed owner UAT**: the custom DOM
title placed above the Plotly tick chart, together with an
Absolute-only date line also above it, produced a tall strip with a
large blank vertical gap — reading as an "information card," not a
compact X-axis. The owner supplied a reference screenshot and an exact
desired layout: tick labels first, a small title directly below them
(never above), no date inside the ruler at all. Full detail:
[MIGRATION_PLAN.md — Phase 2C-C4B Record](MIGRATION_PLAN.md#phase-2c-c4b--compact-sticky-time-axis-layout-correction-2026-08-16).

**Root cause traced**: not the DOM title's own sizing, but the ruler's
own Plotly chart margin — `t:4, b:24` inside a `height:46px` chart left
`46-4-24=18px` of genuinely empty invisible plot-area space (present
even with zero traces and a hidden Y axis), stacked underneath the DOM
title/date lines above it.

**Fix**: the ruler now sets `xaxis.title` directly on its own Plotly
layout — the exact same mechanism every real waveform panel already
uses for its own "Time (s)" title — instead of a separate, hand-
positioned DOM element. Plotly places titles below tick labels by its
own convention, already proven pixel-aligned in this exact codebase on
every panel; no bespoke CSS centering math needed. `#wwStickyRulerTitle`
and `#wwStickyRulerContext` (the custom title/date DOM elements from
Phase 2C-C4A) were deleted entirely, along with their CSS. The ruler's
own margin changed to `{t:2, b:34}` (b:34 reused verbatim from the real
panels' own already-proven fit), and the chart's CSS height reduced
from 46px to 40px. **Resulting total ruler height: ~43–45px**, down
from ~63–80px in Phase 2C-C4A.

**Wording/date changes**: Absolute mode's title is now the owner's
exact specified wording, **"Record Time"** (capital T, was "Record
time" in C4A). No date text appears in the ruler at all anymore — the
toolbar's own `#wwTimeModeContext` label is unchanged and remains the
only place the date is shown.

**What did NOT change**: the unit-aware Elapsed rescaling from Phase
2C-C4A (`wwStickyRulerElapsedUnit()`, the single shared decision for
both tick values and title) is completely untouched — same single
source of truth, still scoped entirely to the ruler's own independent
Plotly domain. `WW_PANEL_MARGIN`, `position: sticky`/`bottom: 0`, no
scroll listener, Separate mode's all-lanes tick suppression, Grouped/
Custom's unchanged per-panel axes, zoom/pan sync, Reset Time View,
Autoscale Y, panel resize, Custom Groups, and the waveform API are all
completely unaffected — confirmed by test.

**Verification**: `phase2cc4a_check.mjs` (scratch, not committed) was
rewritten per this task's own explicit instruction ("update those
assertions rather than treating the correction as a regression") since
its old assertions read a DOM element that no longer exists — now 25/25
passing (broader than the original 23; added checks for the removed
DOM elements/CSS, the compact chart height, and the reused b:34
margin). The full existing Phase 2C-A through 2C-C4 suites (199 checks)
show the exact same 20 failures already fully documented in the Phase
2C-C4/2C-C4A records — zero new divergences introduced by this
correction, since none of this pass's changes touch the underlying
causes. Backend: zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the compact layout genuinely matches the owner's reference
screenshot, whether spacing feels right — was NOT and cannot be
confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C4A — Sticky Time-Axis Title Placement and Unit Label)

**Phase 2C-C4A — Sticky Time-Axis Title Placement and Unit Label.**
**Owner manual UAT confirmed Phase 2C-C4 passed functionally**
(sticky shared time axis stays visible while scrolling, ruler
alignment good, zoom/pan sync good, Absolute/Elapsed switching good,
resizing does not break the ruler) before this task began. The next
request was explicitly **cosmetic only**: relocate the ruler's title
to the top of the strip (not under the ticks) and give it a small,
compact, mode-appropriate wording — full detail:
[MIGRATION_PLAN.md — Phase 2C-C4A Record](MIGRATION_PLAN.md#phase-2c-c4a--sticky-time-axis-title-placement-and-unit-label-2026-08-16).

**Absolute mode**: a fixed, compact title — "Record time" — never a
per-unit label (Absolute is a timestamp representation, not an
elapsed unit scale). The ruler's own date-context line simplified from
"26 Jul 2025 · Record time" to just "26 Jul 2025", avoiding duplicate
"Record time" wording now that the title says it directly above.
**The toolbar's own copy of the context label is deliberately
unchanged** — still the full "<date> · Record time" wording, since it
has no adjacent title to duplicate against.

**Elapsed mode**: the title is now genuinely unit-aware — "Time (ms)",
"Time (s)", or "Time (min)" depending on the visible span. This
required real engineering, not just a label swap: investigation found
Phase 2C-C3's existing tick formatting never actually switched units
at all (always raw seconds, only adapting decimal precision at finer
zoom) — a fixed "Time (ms)" title over an unchanged seconds-formatted
tick would have been exactly the "title says X, ticks show Y"
mismatch this task's own instructions explicitly forbade. **Fix**: one
new shared function, `wwStickyRulerElapsedUnit(spanSeconds)`, is now
the SINGLE decision both the title AND the ruler's own tick values
consult — a simple 3-tier span rule (< 1s → ms, < 60s → s, ≥ 60s →
min), with the ruler's own (independent, trace-less) Plotly x-axis
domain genuinely rescaled by the chosen unit's constant factor. This
rescale is scoped ENTIRELY to the ruler's own Plotly instance —
`ww.viewport`, `wwElapsedToPlotlyX()`, every real waveform panel's own
axis, and Phase 2C-C3's timing semantics are all completely untouched.
Updates automatically on zoom/pan/mode-switch via the same existing
`wwSyncStickyRuler()` call sites Phase 2C-C4 already wired — no new
synchronization loop, confirmed zero waveform refetches.

**Honest, unverified caveat (flagged explicitly, not glossed over)**:
the claim that a uniform rescale of the ruler's own axis domain
preserves tick pixel-position alignment with the real (unrescaled)
waveform panels below it was reasoned through carefully (Plotly's
"nice round tick value" algorithm is scale-covariant under a constant
multiplier) but **could not be visually confirmed in this sandbox** —
no real browser is available. This is the single most important thing
for the owner to check during UAT.

**Verification**: 23 new frontend `jsdom` checks
(`phase2cc4a_check.mjs`) + the full existing Phase 2C-A through 2C-C4
suites (222 checks) re-run unmodified. 20 failures appear, all
explained — not regressions: the same pre-existing Phase 2C-C3/2C-C4
divergences already documented in those phases' own records, plus a
new (equally expected) divergence where several older, pre-COMTRADE-
timing test fixtures' "last relayout call" assumption now sometimes
resolves to the ruler's own correctly-rescaled value instead of a
panel's raw value, and `phase2cc4_check.mjs`'s own date-context-
equality assertion, which asserted the exact thing this phase's own
design deliberately changed. None of these frozen, one-off scripts
were modified, per this project's established precedent. Backend:
zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the title's placement/size/spacing reads as intended against
the owner's own reference screenshot, and critically whether tick
alignment genuinely holds at fine Elapsed-mode zoom — was NOT and
cannot be confirmed in this sandboxed session; this remains explicitly
for the owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C4 — Sticky Shared Waveform Time Axis)

**Phase 2C-C4 — Sticky Shared Waveform Time Axis.** **Owner UAT
confirmed Phase 2C-C3 passed** (Absolute Time correct, Elapsed Time
correct, mode switching preserves the physical window) before this task
began. The next owner-identified usability problem: with many displayed
channels, the shared time-axis labels were only visible at the very
bottom of the panel stack — an engineer working on a channel near the
top of a long, scrolled workspace had no visible time reference. Full
detail:
[MIGRATION_PLAN.md — Phase 2C-C4 Record](MIGRATION_PLAN.md#phase-2c-c4--sticky-shared-waveform-time-axis-2026-08-15).

**Architecture**: ONE Oruxa-owned shared time-axis strip
(`wwSyncStickyRuler()`), driven entirely by the existing workspace-level
`ww.viewport`/`ww.timeMode` state (DEC-021, DEC-029) — never an
independent authority. Implemented as a second, lightweight,
**trace-less** Plotly instance (empty `[]` traces array — axis only,
never a second waveform chart) rather than a hand-rolled SVG/canvas
ruler: this reuses Phase 2C-C3's own `wwTimeAxisTickFormat()` verbatim,
so the ruler's ticks are chosen/formatted by the exact same engine as
every panel, with zero risk of a second, independently-drifting
time-formatting implementation — the one thing this task's own
instructions were most emphatic about avoiding. Plotly was already a
page dependency, so this adds zero new weight.

**Alignment (called out as critical)**: a new shared constant,
`WW_PANEL_MARGIN = { l: 55, r: 20 }`, replaces the margin numbers
previously inlined only in `wwBuildLayout()` — now used by both
`wwBuildLayout()` and the ruler, so the two cannot independently drift
out of pixel alignment. Combined with the ruler's CSS horizontal padding
matching `.ww-panel`'s own exactly (14px, confirmed identical across
Grouped/Separate/Custom), this keeps tick positions pixel-aligned with
every panel's plot area with no runtime measurement needed.

**Sticky behavior**: pure CSS `position: sticky; bottom: 0` — not
`fixed`, no scroll listener. The ruler is a normal-flow sibling of
`#wwPanels` inside `.workspace-section` (its containing block), which is
what makes it stay pinned to the viewport bottom only while part of the
workspace is still below the viewport, and scroll away naturally once
the whole workspace has been scrolled past — satisfying the explicit
"must not permanently float over unrelated content" requirement using
ordinary browser layout. Confirmed by test: dispatching synthetic scroll
events causes zero Plotly calls and zero waveform fetches.

**No new synchronization loop**: `wwSyncStickyRuler()` is called from
exactly the places that already mutate `ww.viewport`/`ww.timeMode`
(`wwApplyAndFetchViewport` — the single function zoom/pan/Reset Time
View all funnel through — and `wwSetTimeMode`), plus displayed-channel-
count and theme-switch call sites. It never registers its own Plotly
event listener (`staticPlot: true`, no `.on(...)` wired), confirmed by
test, so it cannot become a second authority or loop.

**Existing panel axis labels (section 16)**: Separate mode's per-lane
axis chrome (`wwApplyTimeAxisChrome()`) now suppresses ticks/title on
**every** lane, not just the non-bottom ones — the sticky ruler makes
that lone remaining bottom-lane axis redundant. Grouped/Custom panels'
own per-panel axis labels are **deliberately left unchanged** this
slice (a materially larger, riskier restructuring given neither mode
has a single "bottom panel" concept) — documented as a known,
intentional duplication for a future cleanup pass, not fixed here.

**Verification**: 24 new frontend `jsdom` checks (`phase2cc4_check.mjs`)
+ the full existing suites re-run unmodified. `frontend_logic_check.mjs`
and `theme_crosshair_check.mjs` pass in full. Across the Phase 2C-A
through 2C-C3 suites, **9 new failures appear, all explained by this
phase's two deliberate changes** — not regressions: (1) several scripts
assert an exact Plotly `newPlot`/`relayout` call count "one per panel,"
now off-by-one because of the ruler's own extra (single) Plotly
instance; (2) several scripts assert the now-superseded "only the
bottom lane shows ticks" Separate-mode behavior. These are frozen,
one-off, not-committed verification scripts from prior phases — per
this project's own established precedent (Phase 2C-C3's identical
treatment of its own Absolute-default divergence), they were not
modified; `phase2cc4_check.mjs` explicitly covers what changed. Backend:
zero diff, 278/278 passing in a fresh venv.

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the ruler genuinely reads as "sticky" and unobtrusive while
scrolling, whether tick positions visibly line up with waveform data at
various real zoom levels, whether it ever visually covers content — was
NOT and cannot be confirmed in this sandboxed session; this remains
explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C3 — COMTRADE Time-Axis Modes)

**Phase 2C-C3 — COMTRADE Time-Axis Modes.** Adds two selectable,
workspace-level time-axis representations for COMTRADE waveforms:
**Absolute Time** (real recording timestamp per sample, the new
default) and **Elapsed Time** (the pre-existing 0-based-from-record-
start behavior, now explicit/selectable). Full detail:
[MIGRATION_PLAN.md — Phase 2C-C3 Record](MIGRATION_PLAN.md#phase-2c-c3--comtrade-time-axis-modes-2026-08-15).

**Timing investigation, done first per this task's own mandate**:
`TimingInformation.start_time`/`.trigger_time` are separate,
independently-parsed COMTRADE CFG fields, never conflated; the DAT
file's per-sample `ts` (µs from recording start) has sample 0 always
coinciding with `start_time`, **never** `trigger_time` (confirmed
against real parsed metadata, not assumed); both timestamps are
timezone-naive end to end (no timezone field exists anywhere in the
parser/schema); `TimebaseOut` (`GET .../channels`) already exposed
`start_time`/`trigger_time`/`timing_reference` before this pass —
**zero backend changes were needed**, this is a pure frontend
presentation transform.

**Architecture**: `ww.timeMode` (`"absolute"` \| `"elapsed"`) is
workspace-level, not per-panel. The shared physical viewport (DEC-021)
stays authoritative in elapsed-seconds internally, permanently — a
single conversion boundary (`wwElapsedToPlotlyX`/`wwPlotlyXToElapsed`)
is the only place Absolute-mode date strings and Elapsed-mode numbers
meet; the fetch pipeline and backend requests are untouched.
**Zero waveform refetches on a mode switch** — confirmed by test.
Timestamp parsing/formatting uses only `Date.UTC()`/`getUTC*()` — never
local-time getters or `new Date(isoString)` — so there is no
browser-timezone dependency anywhere in this path. The source
capability model (`wwTimeModesForChannel()`) gates Absolute availability
on the backend's own `timing_reference === "absolute"` field, falling
back to Elapsed-only (with both toolbar buttons correctly
enabled/disabled) rather than ever showing a fake option.
`ww.timeMode` **persists across `wwClearWorkspace()`** — same
viewing-preference policy as `ww.layoutMode`/`ww.dragMode`. Adaptive
tick formatting uses Plotly's own native `tickformatstops` (broad-to-
fine date/time bands for Absolute, decimal-precision bands for
Elapsed) — SI-prefix (`~s`) formatting was explicitly rejected as
ambiguous for time values.

**Two real regressions were caught and fixed during this pass's own
regression-suite re-run** (before anything shipped): (1) a `timebase`
variable-scoping bug in `renderAnalogGroup`/`renderChannelTable` that
broke ALL channel checkbox rendering (channel metadata plumbing needed
`timebase` threaded through two intermediate functions that didn't
have it in scope); (2) `wwApplyTimeAxisChrome()` (renamed from
`wwUpdateBottomLaneAxis()`) initially lost its original Grouped/Custom-
mode no-op guard, causing unnecessary relayout calls on every panel in
every layout mode — fixed by restoring the guard and instead updating
Grouped/Custom panel titles directly inside `wwSetTimeMode()`, where a
mode switch actually needs it.

**Verification**: 26 new frontend `jsdom` checks
(`phase2cc3_check.mjs`) + the full existing `frontend_logic_check.mjs`,
`theme_crosshair_check.mjs`, and Phase 2C-A through 2C-C2A suites (193
checks) re-run unmodified, all passing except 2 pre-existing checks in
the non-committed `phase2ca_check.mjs` that assert a raw-elapsed-number
`xaxis.range` — the **expected, correct** consequence of Absolute now
being the COMTRADE default, not a regression. Backend: zero diff,
278/278 passing in a fresh venv. **Real COMTRADE verification**: a
synthetic ASCII COMTRADE record imported through the actual FastAPI app
(`TestClient`, no mocking) with a known `start_time`
(`2025-07-26T14:23:10.123456`) and a distinct `trigger_time` 200ms
later confirmed sample 0's absolute time equals `start_time` exactly,
never `trigger_time`; a second scenario deliberately crossing a
midnight/date boundary confirmed both the API and the frontend's own
`wwParseNaiveTimestamp`/`wwFormatPlotlyDateString` correctly roll the
calendar date over. Both scenarios' backend-returned values were then
fed through the actual shipped frontend JS to confirm parser and
frontend agree exactly.

**Known, documented (not a bug) precision limitation**: JS `Date` has
millisecond resolution vs. COMTRADE's microsecond-precision CFG
timestamps — a sample whose fractional second rounds to exactly the
next millisecond can display 1ms later than its literal value; invisible
in practice since the UI never shows sub-millisecond precision, and not
a rollover-logic defect (`Date.UTC` overflow handling itself is
correct).

**Backend**: zero files changed. **Real-browser visual confirmation —
whether the toolbar toggle reads as compact/discoverable, whether
adaptive tick formatting looks right across real zoom levels, whether
mode-switching while zoomed feels seamless — was NOT and cannot be
confirmed in this sandboxed session; this remains explicitly for the
owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C2A — Panel Resize Responsiveness Investigation)

**Phase 2C-C2A — Panel Resize Responsiveness Investigation.** The
owner's manual UAT of Phase 2C-C2 (adjustable panel heights) **passed
functionally** — resize works correctly in Grouped/Separate/Custom, the
handle feels natural enough, and the 100px minimum / 600px maximum are
both accepted as-is (**unchanged by this pass**). The owner separately
**observed** that during live dragging, the waveform does not visually
follow the panel resize immediately — a delay of perhaps a few hundred
milliseconds, judged bearable, with a preference for better
responsiveness only if low-cost/low-risk. This task was explicitly
**investigate first, do not assume an optimization is needed**. Full
detail:
[MIGRATION_PLAN.md — Phase 2C-C2A Investigation Record](MIGRATION_PLAN.md#phase-2c-c2a--panel-resize-responsiveness-investigation-2026-08-15),
[DECISIONS.md — DEC-028 Update note](DECISIONS.md#dec-028--adjustable-waveform-panel-heights-added-to-all-three-layout-modes-phase-2c-c2)
(no new decision entry — a refinement of the same resize-performance
concern DEC-028 already covers, per governance).

**Bottleneck identified, by direct code-path tracing**: Phase 2C-C2's
`wwSetPanelHeight()` performed the cheap DOM height write AND the
expensive `Plotly.Plots.resize()` call as two synchronous statements
inside the SAME `requestAnimationFrame` callback. A browser cannot paint
a DOM change until the current synchronous unit of JS returns control —
so the panel's new box size was gated on Plotly's own redraw finishing
first, every frame during a drag. Confirmed **structurally** (this
sandbox has no real browser; installing Playwright/Puppeteer for a
one-off diagnostic was judged disproportionate) via jsdom instrumentation
with a simulated-cost Plotly mock (tested at 0ms/20ms/50ms simulated
cost): before the fix, every observed DOM height-write timestamp was
numerically identical to that cycle's Plotly-resize-*end* timestamp —
the height change was never externally observable until Plotly's
(simulated) work had already finished.

**Investigation questions A–I** (this task's own list) were answered
directly by code inspection: rAF scheduling itself is not a contributor
(near-zero-cost browser primitive); no redundant legend/axis/layout work
is triggered beyond what `Plotly.Plots.resize()` itself inherently does;
**dragging one panel already only ever resized that one panel** (no loop
over `ww.panels` anywhere in the resize path — confirmed, not a bug);
and per-frame cost is structurally independent of total panel count
(each panel's resize handle has its own closured state).

**Decision: A. LOW-COST REFINEMENT JUSTIFIED**, checked against every
bullet of DEC-028's own cost/benefit rule (small/understandable change;
no custom rendering engine; no brittle Plotly internals; no
synchronization regression; no waveform refetch; no added state
complexity of consequence; likely meaningful improvement, confirmed
structurally not just asserted).

**What was built**: `wwSetPanelHeight()` split into
`wwSetPanelHeightImmediate()` (clamp/store/write the CSS height only —
now called on **every** raw `pointermove`, not gated behind rAF at all,
since a bare style write doesn't itself force synchronous layout) and
`wwResizePanelPlot()` (the `Plotly.Plots.resize()` call only — still
invoked from inside `requestAnimationFrame`, still coalesced to at most
once per frame regardless of raw pointermove frequency, **identical
coalescing behavior to before**, confirmed by test that Plotly call
counts are unchanged). `wwSetPanelHeight()` itself is retained as the
combination of both, used only for the authoritative final write on
`pointerup`/`pointercancel` (unchanged contract from Phase 2C-C2). Verified
by re-running the same jsdom measurement after the fix: the DOM height
write now becomes observable measurably *before* the corresponding
Plotly resize call even starts, at every simulated cost level tested.

**Preserved exactly, unchanged, reconfirmed by test**: 100px minimum /
600px maximum clamping; independent per-panel sizing; Grouped/Separate/
Custom mode behavior; the panel-height state model (`ww.panelHeights`,
keyed by `groupKey`); zoom/pan synchronization; shared viewport; Reset
Time View; Autoscale Y; theme behavior; crosshair; overlay labels;
Custom Groups behavior; the waveform API. **Zero waveform refetches**
during resizing, before and after this change.

**Backend**: zero files changed — no backend change was needed or made.

**Tests**: 278 backend (unmodified) + 9 new frontend `jsdom` checks
(`phase2cc2a_check.mjs`) + the full existing Phase 2C-C2 (23), Phase
2C-C1 (30), Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20), Phase
2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites all re-run
unmodified and still passing (154 total this pass, no regressions).
**Real-browser tactile confirmation of the improvement — whether the
drag genuinely feels smoother, and whether any momentary divergence
between the box's edge and the waveform's own rendered edge is visible
during a fast drag — was NOT and cannot be confirmed in this sandboxed
session; this remains explicitly for the owner's own manual UAT.**

## What was done in the prior session (Phase 2C-C2 — Adjustable Waveform Panel Heights)

**Phase 2C-C2 — Adjustable Waveform Panel Heights.** The owner completed
manual UAT of Phase 2C-C1 Custom Groups: **PASSED** — "the workflow is
smooth and easy to understand." Before moving on to digital channels, the
owner requested one more analog-workspace refinement: every waveform
panel/lane independently resizable by dragging, across all three layout
modes (Grouped/Separate/Custom), with **Detego's vertical panel-resize
interaction named as the explicit UX benchmark** (placement/feel only —
no branding/colors/icons copied). Full detail:
[MIGRATION_PLAN.md — Phase 2C-C2 Implementation Record](MIGRATION_PLAN.md#phase-2c-c2--adjustable-waveform-panel-heights-implementation-record-2026-08-15),
[DECISIONS.md — DEC-028](DECISIONS.md#dec-028--adjustable-waveform-panel-heights-added-to-all-three-layout-modes-phase-2c-c2).

**What was built**: a thin `.ww-resize-handle` (8px hit area, small
centered theme-token-styled grip, `cursor: ns-resize`) added to every
panel's DOM in `wwCreatePanelDom()`, sitting entirely below the chart
(zero overlap into the plotting area, so it never intercepts hover/
crosshair). Dragging uses native **Pointer Events + Pointer Capture**
(`setPointerCapture` on `pointerdown`, so the drag keeps working even if
the pointer leaves the handle's narrow bounds) with move/up listeners
added on `pointerdown` and always removed on `pointerup`/`pointercancel`
— no `document`-level listeners, nothing that can leak. Resizing is live
during the drag (not deferred to mouse-up), coalesced through
`requestAnimationFrame` so at most one `Plotly.Plots.resize()` call
happens per animation frame regardless of raw pointer-event frequency.

**Height constraints (documented, tested)**: minimum **100px** (keeps a
usable plot area above `wwBuildLayout()`'s own fixed 44px top+bottom
margins — a floor much lower would produce the "unusable strip" this
task explicitly warned against); maximum **600px** (generous, not a hard
requirement, purely to prevent pathological single-panel growth);
defaults match each mode's own pre-existing height (Grouped/Custom
260px, Separate 140px) so a brand-new panel's first paint is unchanged
from before this phase.

**Height state model (documented, tested)**: explicit application state
(`ww.panelHeights`, a `Map<groupKey, heightPx>`), never read from the
rendered DOM as the source of truth — reusing the SAME `groupKey` panel
derivation already computes (Phase 2C-B1's own architecture), not a new
identity concept. This single mechanism, with zero per-mode
special-casing, produces exactly the requested behavior: different
modes' keys never collide (a Separate VA lane's height never leaks onto
the Grouped Voltage panel); the SAME mode's key persists across a round
trip (Separate→Grouped→Separate restores VA's own Separate height); a
brand-new key always gets its mode's sensible default — no cross-mode
height-mapping logic was built, per this task's own explicit
instruction not to invent one.

**Presentation-only, verified directly**: `Plotly.Plots.resize()` is the
only Plotly API ever called for a height change — no data refetch, no
viewport reset, no Y-range reset. Fetch-call counts before/after a full
multi-move resize drag, in every mode, are identical. Synchronization
(DEC-021) is untouched — resizing never reads/writes `ww.viewport` or any
panel's `suppressNext` flag; zoom/pan after resizing still broadcasts
correctly to every panel. Separate mode's unified canvas, overlay label
(still a correctly-positioned child of its own lane regardless of that
lane's height), and bottom-only shared X-axis (still exactly the true
last panel, regardless of resizing) are all fully preserved — verified
directly, not just asserted. Custom group membership and the group-
editing workflow itself are completely untouched.

**Persistence**: `ww.panelHeights` is session/workspace-only (no
backend/database persistence, matching DEC-015's ephemeral-by-design
principle); a whole-workspace reset clears it; individual channel/panel
removal deliberately does not (same policy Phase 2C-C1 already
established for `ww.customGroups`, same reasoning).

**Accessibility limitation, documented honestly**: keyboard resizing was
**not** implemented this slice (`tabindex="-1"`, `role="separator"` +
`aria-label` only) — this task's own instructions marked it desirable
long-term but not required "unless trivial," and a correct keyboard-
resize interaction (likely `role="slider"` with `aria-valuenow`/min/max)
was judged non-trivial, out of proportion to this slice's pointer-drag
requirement.

**Backend**: zero files changed — no backend change was needed
(frontend/state-only, per this task's own preference).

**Tests**: 278 backend (unmodified) + 23 new frontend `jsdom` checks
(using jsdom's real `PointerEvent` constructor plus a
`requestAnimationFrame`/`cancelAnimationFrame` polyfill jsdom itself
lacks) + the full existing Phase 2C-C1 (30), Phase 2C-B3A (17), Phase
2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19), and
Phase 1 (4) suites all re-run unmodified and still passing (145 total
this pass, no regressions). **Digital-channel rendering, lane drag/
reorder, and drag-to-group all remain explicitly not started.**
Real-browser tactile/visual confirmation of the drag interaction itself
was not possible in this sandboxed, no-real-browser session — see this
task's own final report for the closest available substitute evidence;
final judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-C1 — Custom Analog Channel Groups)

**Phase 2C-C1 — Custom Analog Channel Groups.** The owner chose to
**skip vertical lane drag/reorder for now** — previously flagged as the
owner's likely next direction since Phase 2C-A — and instead requested
**Custom Groups**: manual, user-controlled decisions about which
displayed analog channels share a waveform panel, with **Detego's own
"Edit Channel Groups" workflow named as the explicit benchmark** (a
workflow/layout reference only — no Detego branding/colors/icons
copied). Full detail:
[MIGRATION_PLAN.md — Phase 2C-C1 Implementation Record](MIGRATION_PLAN.md#phase-2c-c1--custom-analog-channel-groups-implementation-record-2026-08-15),
[DECISIONS.md — DEC-027](DECISIONS.md#dec-027--custom-analog-channel-groups-added-as-a-third-layout-mode-dragreorder-deferred-phase-2c-c1).

**What was built**: a third toolbar layout-mode button, `[ Grouped ]
[ Separate ] [ Custom ]`. Selecting Custom with no custom grouping
defined yet shows one panel per channel (the auto-solo fallback, see
below) so the mode is never empty/broken on first entry. A new **Edit
Channel Groups** button (visible only in Custom mode) opens a modal
(reusing the app's existing `.confirm-overlay` backdrop pattern, Oruxa
theme tokens throughout): an **Unassigned channels** list (each a chip
with an "Add to group…" `<select>`) and a **Groups** section (`+ Add
group`, each group a card with an editable name, a delete button, and a
chip list of its assigned channels with per-chip remove). Apply commits
the working copy and rebuilds the workspace under Custom mode; Cancel /
the × close button / Escape / backdrop-click all discard the working
copy with zero side effects (editing happens in an in-memory
`groupEditorState`, never touching the real `ww.customGroups` until
Apply). No drag-and-drop inside the modal — moving a channel between
groups is two explicit steps (unassign, then assign via the dropdown), a
deliberate, honestly-reported first-slice simplification.

**Group assignment rule (documented, per this task's own required
choice)**: any displayed channel not placed in a group automatically
becomes its own single-channel panel — there is no "unplaced" error
state, and Apply is never blocked on complete assignment.

**Rendering**: each custom group becomes a panel via the exact same
`wwCreatePanelObject`/`wwCreatePanelDom`/`wwBuildLayout`/`wwInitPanelPlot`
machinery every other mode already uses — **zero changes needed there**.
The only new logic is a "custom" branch in `wwPanelGroupKeyFor`/
`wwPanelLabelFor` (looks up which `ww.customGroups` entry claims a
channel, or falls back to a uniquely-prefixed solo key) plus a new
`wwCustomGroupFor()` helper; `wwRebuildLayout()` itself needed **no
changes at all**, exactly the payoff of the panel-derivation architecture
Phase 2C-B1 (DEC-025) built for this purpose. Custom panels use Grouped's
card styling, not Separate's unified/overlay treatment (a Custom panel
can hold multiple channels, the same shape as Grouped).

**Viewport preservation and grouping persistence, both verified
directly**: zooming, then opening/Applying the group editor, leaves the
resulting panels at the exact same X/time range (zero special-case code
— `wwRebuildLayout()` already reads the current `ww.viewport` and never
touches it). The last-applied custom grouping persists across
Grouped/Separate/Custom mode switches within the session — switching
back to Custom restores it rather than resetting to all-solo — and is
only cleared by a whole-workspace reset ("Clear workspace"/"Start new
workspace"), matching how the viewport/record bounds are already reset
there.

**Backend**: zero files changed — no backend change was needed (Custom
grouping is frontend-only, in-memory, ephemeral session state, per this
task's own preference and the project's existing ephemeral-by-design
principle, DEC-015).

**Tests**: 278 backend (unmodified) + 30 new frontend `jsdom` checks + the
full existing Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20),
Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites all re-run
unmodified and still passing (122 total this pass, no regressions).
**Direct vertical lane drag/reorder and drag-to-overlay/group by direct
lane dragging were explicitly not started — deliberately deferred by the
owner's own choice this pass, not abandoned.**

**Also note**: between Phase 2C-B3A and this pass, the owner made two
small direct manual tweaks to the Phase 2C-B3A overlay tag (committed
separately as `d902dc5`, "style: tune overlay lane label position and
background"): `top: 50%` → `top: 25%` (a higher vertical position within
the lane) and `.ww-legend-item`'s `background` changed from the
`--surface-tint` theme token to a fixed `rgb(255 255 255 / 80%)`. The
fixed background is **not theme-reactive** — it will look the same
(translucent white) in Dark theme as in Light, which was flagged to the
owner at the time but implemented as explicitly requested. If Dark-theme
tag readability is ever raised in a future UAT, this is why. This
pass's own test suite (`phase2cb3a_check.mjs`) was updated to assert the
overlay mechanism generically (percentage-based `top` + `translateY`)
rather than the exact tuned value, so future manual tweaks like this one
don't spuriously fail the regression suite.

Real-browser visual/
workflow confirmation of the group editor modal was not possible in this
sandboxed, no-real-browser session — see this task's own final report for
the closest available substitute evidence; final judgment remains the
owner's own manual UAT.

## What was done in the prior session (Phase 2C-B3A — Overlay Right-Side Lane Labels)

**Phase 2C-B3A — Overlay Right-Side Lane Labels (correction).** The Phase
2C-B3 right-side-column label was **not** the owner's intended layout —
the owner clarified explicitly: the label must be **overlaid on the
waveform lane itself**, not placed in a dedicated right-side layout
column, and should follow **Detego's own separate-waveform label style as
closely as practical** for this specific placement (Detego treated as the
explicit layout benchmark here, not just loose inspiration — a narrower
application of the Detego Benchmark Principle than earlier passes used).
Full detail:
[MIGRATION_PLAN.md — Phase 2C-B3A Implementation Record](MIGRATION_PLAN.md#phase-2c-b3a--overlay-right-side-lane-labels-implementation-record-2026-08-15),
[DECISIONS.md — DEC-026 further Update note](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2)
(no new decision entry — a further refinement of the same visual-
presentation concern DEC-026 already covers, per governance).

**What was built**: the dedicated `108px`/`136px` fixed-width grid column
Phase 2C-B3 introduced was removed entirely. `.ww-panel` (the lane) is no
longer split into two grid columns — it's a plain block with `position:
relative`, and `.ww-chart-wrap` fills its full width. `.ww-legend` (the
same DOM — dot + `.ww-legend-label` span + remove button, unchanged) is
now `position: absolute`, pinned `right: 14px`, vertically centered
(`top: 50%; transform: translateY(-50%)`), with `z-index: 2` so it floats
on top of the chart instead of reserving its own layout space next to it.
`pointer-events: none` on the wrapper (re-enabled on the pill via
`pointer-events: auto`) keeps empty space around the compact tag from
blocking chart hover/crosshair underneath it. No tradeoff was needed for
the remove control — it fits identically inside the overlay tag as it did
inside the column tag, since only the tag's position changed.

**No architecture change**: Phase 2C-B2's unified-canvas container, lane
dividers, compact lane height, and `wwUpdateBottomLaneAxis()`'s
bottom-lane-only shared time axis are completely unchanged; Grouped
mode's own CSS was not touched at all. No change to the shared-viewport
synchronization mechanism, relayout loop-prevention, theme behavior,
crosshair styling, point-budget, or source/workspace lifecycle — verified
directly.

**Backend**: zero files changed — same endpoint, same query parameters,
confirmed by test.

**Tests**: 278 backend (unmodified) + 17 new frontend `jsdom` checks + 2
of Phase 2C-B3's own CSS-source assertions corrected in place (they
specifically tested the now-removed grid-column mechanism; the other 14
needed no change) + the full existing Phase 2C-B2 (20), Phase 2C-B1 (16),
Phase 2C-A (19), and Phase 1 (4) suites all re-run unmodified and still
passing (92 total this pass, no functional regressions). **Direct
drag/reorder of panels, drag-to-overlay/group, drag-out-to-separate,
digital-channel rendering, and lane resize were all explicitly not
started.** Real-browser visual confirmation that the overlay genuinely
reads as a Detego-style floating label rather than a side panel was not
possible in this sandboxed, no-real-browser session — see this task's own
final report for the closest available substitute evidence; final
appearance judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-B3 — Right-Side Compact Lane Labels)

**Phase 2C-B3 — Right-Side Compact Lane Labels.** Following manual owner
UAT of Phase 2C-B2 (**passed** — "Separate view now feels much better,
unified analog canvas direction is accepted"), the owner's next requested
refinement was moving the Separate-mode lane label to a small compact tag
on the RIGHT side, similar in placement/feel to Detego — used only as a
UI/layout reference (no colors/typography/icons/component styling
copied). This was a small, deliberately-scoped VISUAL refinement of the
existing lane label only. Full detail:
[MIGRATION_PLAN.md — Phase 2C-B3 Implementation Record](MIGRATION_PLAN.md#phase-2c-b3--right-side-compact-lane-labels-implementation-record-2026-08-15),
[DECISIONS.md — DEC-026 Update note](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2)
(no new decision entry — a refinement of the same visual-presentation
concern DEC-026 already covers, per governance).

**What was built**: the existing compact legend chip (dot + channel name
+ unit + remove button, unchanged since Phase 2C-A) moved from the lane's
left edge to its right edge via a CSS grid-column swap on `.ww-panel`
(`.ww-chart-wrap` is now `grid-column: 1`/`.ww-legend` is now
`grid-column: 2` with `justify-self: end`) — the waveform column keeps
maximum width, only which side got the fixed-width column changed. The
tag is now an explicit small pill (`border-radius: 999px`, a subtle
`var(--panel-border)` border, `var(--surface-tint)` background) using
existing Oruxa theme tokens already proven across the rest of the app
(DEC-023) — no Detego color/typography/icon was copied. A new
`.ww-legend-label` wrapping span gives the text an ellipsis-truncation
target (`max-width: 130px` on the tag) so an unusually long channel
identifier can't crowd the waveform. The remove control and color dot are
unchanged and still fit cleanly inside the tag — no interaction tradeoff
was needed. The redundant per-lane header stays hidden (unchanged from
Phase 2C-B2) — still exactly one label treatment per lane, just
repositioned and restyled.

**No architecture change**: Phase 2C-B2's unified-canvas container, lane
dividers, compact lane height, and `wwUpdateBottomLaneAxis()`'s
bottom-lane-only shared time axis are completely unchanged; Grouped
mode's own CSS was not touched at all. No change to the shared-viewport
synchronization mechanism, relayout loop-prevention, theme behavior,
crosshair styling, point-budget, or source/workspace lifecycle — verified
directly.

**Backend**: zero files changed — same endpoint, same query parameters,
confirmed by test.

**Tests**: 278 backend (unmodified) + 16 new frontend `jsdom` checks + the
full existing Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19), and
Phase 1 (4) suites all re-run unmodified and still passing (75 total this
pass, no regressions). **Direct drag/reorder of panels, drag-to-
overlay/group, drag-out-to-separate, digital-channel rendering, and lane
resize were all explicitly not started.** Real-browser visual confirmation
that the tag genuinely reads as compact/readable/low-clutter was not
possible in this sandboxed, no-real-browser session — see this task's own
final report for the closest available substitute evidence; final
appearance judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-B2 — Unified Analog Canvas Layout)

**Phase 2C-B2 — Unified Analog Canvas Layout.** Following manual owner
UAT of Phase 2C-B1 (**passed** for synchronization, horizontal zoom, and
pan; **refinement requested** for Separate mode's visual layout, which
looked like a stack of individually bordered/headed cards rather than one
continuous analog canvas — the owner supplied a Detego screenshot purely
as a visual/layout reference, per the Detego Benchmark Principle), this
was a small, deliberately-scoped VISUAL refinement of Separate mode only.
Full detail:
[MIGRATION_PLAN.md — Phase 2C-B2 Implementation Record](MIGRATION_PLAN.md#phase-2c-b2--unified-analog-canvas-layout-implementation-record-2026-08-15),
[DECISIONS.md — DEC-026](DECISIONS.md#dec-026--separate-modes-visual-presentation-is-a-unified-analog-canvas-phase-2c-b2).

**What was built**: `#wwPanels` gains a `ww-panels-unified` CSS class only
while `ww.layoutMode === "separate"` (toggled in `wwSetLayoutMode`). With
it: one shared outer background/border replaces N repeated panel cards
(the container's background is literally the same theme token each
Plotly chart's own background already uses, so there's no visible seam);
each lane becomes a CSS-grid row (narrow 108px label column + a
maximum-width chart column) separated by a hairline `border-bottom`
divider instead of a full card border; the now-redundant per-panel header
is hidden and the existing compact legend chip (dot + channel name + unit
+ remove button) becomes the sole per-lane label; lane height drops from
260px to 140px for compactness. A new `wwUpdateBottomLaneAxis()` function
shows X tick labels/title on only the last panel in `ww.panels`' order —
every other lane suppresses them, since all lanes already share one
X/time viewport — called after every panel-array mutation (add, remove,
mode-switch rebuild) so the "which lane is bottom" role correctly follows
whichever lane is actually last. **Each lane keeps its own independent Y
axis — channels are never merged onto one shared Y axis**, an explicit
distinction from the visual chrome change (the task's own "critical
distinction" section). Grouped mode's own CSS and per-panel X axis are
completely untouched — the unified class is never applied while
`ww.layoutMode === "grouped"`.

**No architecture change**: this is a pure CSS/relayout-chrome layer on
top of Phase 2C-B1's existing panel data model (`ww.panels`: displayed
channels + panel membership + panel order, unchanged) and Phase 2C-A's
shared-viewport synchronization mechanism (DEC-021, unchanged). Switching
into or out of unified mode issues **zero** new waveform requests,
verified directly — same as every prior Phase 2C-A/B1 layout operation.
No drag handle/drop-target markup was added (optional per this task's own
instructions); the existing panel-order property (already read here to
decide the bottom lane) remains the same forward-compatible foundation
Phase 2C-B1 (DEC-025) already established for a future drag/reorder
feature.

**Backend**: zero files changed — same endpoint, same query parameters,
confirmed by test.

**Tests**: 278 backend (unmodified) + 20 new frontend `jsdom` checks + the
full existing Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites
all re-run unmodified and still passing (59 total this pass, no
regressions). **Direct drag/reorder of panels, drag-to-overlay/group,
drag-out-to-separate, digital-channel rendering, panel resize, and Custom
layout mode were all explicitly not started.** Real-browser visual
confirmation that the six lanes genuinely read as "one canvas" was not
possible in this sandboxed, no-real-browser session — see this task's own
final report for the closest available substitute evidence; final
appearance judgment remains the owner's own manual UAT.

## What was done in the prior session (Phase 2C-B1 — Grouped / Separate Analog Waveform Layout)

**Phase 2C-B1 — Grouped / Separate Analog Waveform Layout.** Following
manual owner UAT of Phase 2C-A (**passed** for shared synchronization,
horizontal zoom, Reset Time View, pan synchronization, Voltage/Current
grouping, and Autoscale Y — a small bearable interaction latency and a
vertical-zoom-discoverability note were both raised but deliberately left
for a later pass), the owner's requested next enhancement was waveform
layout flexibility. Full detail:
[MIGRATION_PLAN.md — Phase 2C-B1 Implementation Record](MIGRATION_PLAN.md#phase-2c-b1--grouped--separate-analog-waveform-layout-implementation-record-2026-08-15),
[DECISIONS.md — DEC-025](DECISIONS.md#dec-025--groupedseparate-analog-waveform-layout-modes-confirmed-and-implemented-phase-2c-b1).

**What was built**: a small **Grouped / Separate** toggle added to the
existing central toolbar. Grouped is unchanged from Phase 2C-A
(`engineering_type`-based). Separate gives every displayed analog channel
its own panel/lane (one Plotly instance, one trace, its own Y axis) — 6
displayed channels produce exactly 6 lanes, verified directly. Switching
modes **never** changes which channels are displayed, **never** issues a
new waveform request (each channel's already-fetched data is reused as-is
when its panel is rebuilt), and **preserves the current shared X/time
viewport exactly** in either direction — verified by test: zoom to a
window in Separate mode, switch to Grouped, the rebuilt panels open at
that exact same window, and the same holds switching back. The underlying
model — `ww.panels` as an ordered `{label, channels, ...}` array — was
already shaped correctly since Phase 2C-A; what's new is
`wwPanelGroupKeyFor`/`wwPanelLabelFor` (layout-mode-aware panel identity)
and `wwRebuildLayout()` (re-derives panels from the flat displayed-channel
list under the current mode). This was deliberately built so a future
direct vertical-drag/reorder/overlay/split interaction — the owner's own
stated next direction — is architecturally just another way of producing
the same panels/membership/order shape, not a redesign of it. Removal
behaviour needed **zero code changes**: a Separate-mode panel always has
exactly one channel by construction, so removing it always empties (and
therefore removes) the panel automatically. Theme switching, the shared-
viewport broadcast mechanism, loop-prevention, and the crosshair
(DEC-022/DEC-023, untouched) all work identically in both layout modes,
reusing Phase 2C-A's existing mechanisms unchanged.

**Backend**: zero files changed — same endpoint, same query parameters
(`channel_name`/`start_time`/`end_time`/`point_budget`), confirmed by
test that switching layout mode issues no new request at all.

**Tests**: 278 backend (unmodified) + 16 new frontend `jsdom` checks +
the full existing Phase 2C-A suite (19 checks) and Phase 1 regression
suite (4 checks) both re-run unmodified and still passing (39 total this
pass, no regressions). **Direct drag/reorder of panels, drag-to-
overlay/group, drag-out-to-separate, Custom layout mode, and panel resize
were all explicitly not started.**

## What was done in the prior session (Phase 2C-A — Synchronized Multi-Channel Waveform Display)

**Phase 2C-A — Synchronized Multi-Channel Waveform Display.** The first
real multi-channel waveform workspace, implemented directly in
`frontend/index.html` (not an isolated page). Full detail:
[MIGRATION_PLAN.md — Phase 2C-A Implementation Record](MIGRATION_PLAN.md#phase-2c--synchronized-multi-channel-waveform-display-implementation-record-2026-08-15),
[DECISIONS.md — DEC-024](DECISIONS.md#dec-024--phase-2c-a-multi-channel-waveform-workspace-architecture-confirmed-and-implemented).

**What was built**: a checkbox per analog channel row (search/grouping
unchanged) + "Add N selected" → newly-added channels group, on *initial*
placement only, by the existing `engineering_type` (never re-derived) →
each engineering-type group becomes its own panel, **one independent
Plotly instance per panel** (never a single figure with fixed subplots) →
every panel shares **one Oruxa-owned X/time viewport** (DEC-021, now
actually implemented) — zoom or pan on any one panel debounces (120ms)
then broadcasts the exact same range to every other panel and refetches
every displayed channel for it, using a per-panel `suppressNext` flag to
prevent the broadcast's own programmatic relayout from re-triggering
itself (verified with a test double that faithfully re-fires Plotly's
relayout event, not just structurally present in the code) → a single
central toolbar (Zoom, Pan, Reset Time View, Autoscale Y — exactly 4
controls, nothing else) is the only navigation surface; every native
per-panel Plotly modebar is disabled. Autoscale Y is viewport-aware Fit
only (Plotly's native `yaxis.autorange` against data that's already
scoped to the current viewport by construction) — Proportional/
shared-unit scaling was not built. A channel can be removed from a panel
(the panel disappears once empty) without touching its imported source;
"Clear workspace," per-source removal, and "Start new workspace" all
correctly clear the relevant part of the display. Theme switching
re-colors every panel via `Plotly.relayout` only, still never refetching
waveform data; the crosshair (DEC-022/DEC-023) is unchanged, applied
per-panel — cross-panel crosshair sync was explicitly not built.

**Backend**: zero files changed. The existing Phase 2A single-channel
waveform endpoint is reused as-is — N displayed channels means N
requests, each with its own independent abort-controller/sequence-number
stale-response guard (generalizing Phase 2B's proven single-channel
pattern, not a new mechanism); no batching endpoint was built (explicitly
evidence-gated, deferred).

**Tests**: 278 backend (unmodified, unchanged) + 19 new frontend `jsdom`
checks (selection/Add/grouping/panels/shared-viewport/loop-prevention/
toolbar/removal/theme/a 12-channel structural scale check) + 4 existing
Phase 1 regression checks re-run and still passing (two of that older
script's own assertions were tightened, not weakened, to account for the
new checkbox column). **Phase 2C-B (drag/reorder between panels, panel
resize, Proportional Y scaling, mixed-unit handling, digital channels,
shared crosshair) was explicitly not started.**

## What was done in the prior session (Crosshair Visual UAT Follow-up)

**Crosshair Visual UAT Follow-up** (a very small, config-only refinement —
**not** Phase 2C work). Theme UAT (prior pass) passed with no changes
requested; the owner's only remaining feedback was that the Plotly
crosshair was still too coarse (dash segments too long) and too faint (in
**both** themes). Full detail:
[MIGRATION_PLAN.md's follow-up subsection](MIGRATION_PLAN.md#follow-up-crosshair-visual-uat-refinement-2026-08-15-same-day),
an "Update" note appended to
[DEC-023](DECISIONS.md#dec-023--application-supports-light-and-dark-appearance-light-is-the-preferreddefault-direction)
(no new decision entry — same crosshair-styling concern DEC-023 already
covers).

**What changed**: `spikethickness` `0.5` → `0.35` (both axes) — the same
SVG-fractional-stroke-width reasoning as the prior pass. `spikedash`
changed from the named `"dash"` style to a custom native Plotly
dash-length string, `"3px,2px"` — Plotly's own `dash` attribute documents
this `"px,px,..."` syntax as first-class native configuration, so this is
not a workaround. **Native limitation found and stated honestly**:
Plotly's built-in `"dash"` style has no stable, documented internal pixel
definition to reverse-engineer and produce a mathematically exact "half
length" from — a deliberately shorter native value was chosen instead, as
the closest clean native option. `--spike-color` (theme.css) was
strengthened in both themes for stronger contrast, stopping short of full
opacity: Light `rgba(92, 101, 121, 0.42)` → `rgba(60, 68, 87, 0.6)`
(darkened toward `--text`, higher alpha); Dark
`rgba(139, 150, 173, 0.42)` → `rgba(168, 178, 199, 0.6)` (brightened
toward `--text`, higher alpha). Grid-line styling was deliberately left
untouched — the owner already finds it acceptable.

**Unchanged**: `spikesnap: "data"`, both vertical/horizontal spike lines,
moving hover X/Y values, theme-switch-without-refetch behavior, DEC-021/
DEC-022, the waveform API, zoom/pan/Reset Time View/Autoscale Y,
source/workspace lifecycle. No custom crosshair/cursor overlay was built;
no Plotly-generated SVG was manually manipulated. No backend file was
touched (278 tests unmodified and passing); the existing 19-check
`jsdom` test script was updated in place for the new values (not a new
test file). **No Phase 2C work.**

## What was done in the prior session (Light/Dark Theme & Crosshair Refinement)

**Light/Dark Theme & Crosshair Refinement** (a small, general-application
UX task — **not** Phase 2C work). Full detail:
[MIGRATION_PLAN.md — Light/Dark Theme & Crosshair Refinement Record](MIGRATION_PLAN.md#lightdark-theme--crosshair-refinement-record-2026-08-15),
[DECISIONS.md — DEC-023](DECISIONS.md#dec-023--application-supports-light-and-dark-appearance-light-is-the-preferreddefault-direction).

**What was built**: a shared, reusable theme-token system —
`frontend/theme.css` (new: CSS custom properties for Light — the
default/preferred theme — and `[data-theme="dark"]`, plus new
`--waveform-surface`/`--toolbar-surface`/wash-tint tokens that replace
what used to be raw `rgba(...)` literals) and `frontend/theme.js` (new:
`PowerwaveTheme.getTheme()`/`setTheme()`/`mountThemeToggle()`, applies
`[data-theme]` to `<html>` before body paint to avoid a flash, persists to
`localStorage` (`powerwave.theme`), and syncs live across tabs via the
`storage` event). Both `index.html` and `waveform-prototype.html` now
include these shared files, had their own local hard-coded `:root` color
blocks and scattered `rgba(...)` literals removed/replaced with tokens,
and gained a small Light/Dark segmented control in their header. The
light palette is an **original Oruxa design** (`--bg: #f3f5f9`,
`--panel: #ffffff`, `--accent: #3568d4`, etc.) — Detego's palette was not
consulted or copied, per the owner's explicit instruction and the
already-established Detego Benchmark Principle (DEC-020). The dark theme
is the exact same values the app already used, just migrated onto the
shared token system (same layout/behavior, different appearance — not a
second CSS implementation).

**Plotly integration**: `waveform-prototype.html`'s chart now reads its
colors from the active theme at init time and re-applies them via
`Plotly.relayout`/`Plotly.restyle` on a theme change (new
`PlotlyRenderer.applyTheme()`) — **verified via test that this never
triggers a new waveform data fetch**.

**Crosshair refined further** (beyond the Phase 2B closure pass, DEC-022):
`spikethickness` `1` → `0.5` (a genuine, natively-supported thinner SVG
stroke-width value — Plotly's spike lines render as SVG paths even for a
`scattergl` trace, and fractional stroke-width is standard, reliable SVG
behavior, not a workaround; the prior pass's "practical minimum" claim
was not fully substantiated) and `spikecolor` alpha `0.55` → `0.42`.
Dashed style, `spikesnap: "data"`, and moving hover X/Y values are
unchanged. **No custom crosshair/cursor engine was built.** Honest
limitation: pixel-level visual confirmation wasn't done in this
sandboxed, no-real-browser session — see this task's live DEV
verification for that.

**No backend change** (zero backend files touched, 278 tests unmodified
and passing). **No Phase 2C work** — Phase 2C remains exactly as the
prior pass left it: designed, not implemented, not authorized.

## What was done in the prior session (Phase 2C discovery/design)

**Phase 2C — Flexible Multi-Channel Waveform Workspace: Discovery and
Design.** Design/discovery only — **nothing implemented, nothing decided**.
Full detail:
[MIGRATION_PLAN.md — Phase 2C](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15).

**What was done**: re-verified `powerwave`'s live multi-channel/panel code
directly (via a spawned Explore subagent, same commit `3156392`), consulted
Detego's own public marketing/docs pages (`detego.app`,
`detego.app/docs/guide/waveform-viewer`) for publicly observable
waveform-viewer behavior per DEC-020's benchmark framework, and produced a
full design proposal covering: the panel abstraction (one shared X inherited
from DEC-021, independent Y per panel); an `engineering_type` auto-grouping
default that never permanently constrains channel placement; a channel-add
workflow recommendation (checkbox + "Add N selected," matching Phase 1's
established interaction pattern); a drag/reorder model (reorder panels, move
channels between panels, create/split panels via drag — explicitly **not**
one-per-panel channel reordering or panel-merging in the first slice); a
recommended **one independent Plotly instance per panel** architecture
(extending Phase 2B's already-proven `suppressNextRelayout`/sequence-number
broadcast mechanism to N panels, rather than fighting Plotly's native
multi-subplot domain-fraction math); a Fit-vs-Proportional Y-scaling model
(Fit — viewport-aware — as the default, an explicit improvement over
`powerwave`'s own stale full-session-window autoscale; Proportional as a
later toggle); mixed-unit-panel handling (allowed via drag, with an
automatic secondary Y axis); a legend/identity model reusing Phase 1's
existing sidebar rather than building a second one; a lightweight
plain-object workspace state model (no Redux/framework); a recommended
implementation slicing (2C-A through 2C-D, plus an optional
backend-batching slice); and a reassessment of the TTL and ~100 MB
real-file-memory open items (neither escalates to a Phase 2C blocker).

**A genuinely new finding, not previously recorded**: `powerwave` already
has live channel-to-panel drag-and-drop (legend row → panel header, plus a
sidebar combo box and a merge/split context menu) — but **no panel-
reordering mechanism exists anywhere in its codebase**. Detego's own public
docs don't document panel-reordering either. This is flagged as the single
clearest opportunity for Oruxa to exceed both references at once, not
merely match one of them.

**Nothing here is a `[DECISION]`** — every substantive design choice remains
`[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`/`[DEFER]`, per this
task's own explicit instruction. DEC-021 and DEC-022 are reaffirmed,
unweakened, throughout. **No code was written this pass** — no multi-channel
API, no panel model, no drag/drop, no digital signals, no cursors. Commit
was **docs-only**.

## What was done in the prior session (Phase 2B Renderer Closure)

**Phase 2B — Renderer Closure.** The owner's final UAT decision:
**Plotly.js is selected as the waveform rendering foundation** (DEC-022,
[DECISIONS.md](DECISIONS.md)) — Plotly's better waveform clarity, richer
built-in navigation, and overall stronger engineering interaction feel
won out over uPlot's own strength (a very good free-moving crosshair
feel). **This is Phase 2B's final outcome — no longer `[UAT]`.** Full
detail:
[MIGRATION_PLAN.md — Phase 2B Renderer Closure Record](MIGRATION_PLAN.md#phase-2b--renderer-closure-record-2026-08-15).

**What changed**: the crosshair was restyled — `spikedash: "dash"` (was
solid) and a reduced-opacity `spikecolor` (was fully opaque) — a lighter,
subtler guide line closer to uPlot's visual character, **without**
recreating uPlot's cursor mechanics. The owner explicitly declined to
pursue crosshair-responsiveness parity with uPlot ("not important enough
to justify additional implementation complexity or development time") —
no custom mouse-following overlay was built; Plotly's native, sample-
snapped hover behaviour is otherwise unchanged. `UPlotAdapter`, the
renderer-switch UI (tabs), and `frontend/vendor/uplot/` were all removed
— confirmed via repository-wide search, no live `uplot` reference remains
outside historical documentation. The page itself was simplified: no more
"renderer comparison"/"Phase 2B UAT" wording, just a plain "Single-channel
waveform preview — not the final Phase 2C workspace" label. **DEC-021
(workspace-level, centralized-toolbar navigation) is unchanged and
unweakened** — Plotly's native per-channel modebar, kept for this
single-channel page, is now documented directly in the page's own visible
text as temporary, ahead of Phase 2C's required centralized toolbar.

**No Phase 2A backend change** (zero backend files touched, 278 tests
unmodified and passing). **No Phase 2C work.**

## What was done in the prior session (Phase 2B Plotly refinement)

**Phase 2B — Plotly Refinement & Workspace-Level Navigation.** Follows
the owner's hands-on UAT of the Phase 2B renderer prototype (commit
`ad6d9d2`): **Plotly is currently preferred** (better clarity, richer
native controls, smoother interaction) over uPlot (whose own strength was
its built-in crosshair), but the renderer choice is **explicitly not
closed** — `[UAT — Plotly preferred pending final refinement
confirmation]`. Full detail:
[MIGRATION_PLAN.md — Phase 2B Plotly Refinement & Workspace-Level
Navigation Record](MIGRATION_PLAN.md#phase-2b--plotly-refinement--workspace-level-navigation-record-2026-08-15).

**Two things were built/fixed this pass**:
1. A native Plotly crosshair (`showspikes`/`spikesnap: "data"`/
   `spikemode: "across"` on both axes, `hovermode: "closest"`) — no
   custom crosshair system, per the task's own preference for native
   capability first. `spikesnap: "data"` deliberately snaps to real
   recorded samples, never an interpolated position.
2. A toolbar-lag investigation that found a real bug, not just perceived
   slowness: Plotly's native Autoscale/Reset-axes modebar buttons fire an
   `xaxis.autorange: true` relayout (no explicit range), which the
   original relayout handler silently ignored — meaning those buttons
   never actually re-fetched the true full record, only re-scaled
   whatever data was already loaded. Fixed. The viewport debounce was
   also shortened 200ms → 120ms (button clicks have no drag-frames to
   coalesce, so the old debounce was pure added latency for that specific
   interaction). "Reset View" was relabelled "Reset Time View" throughout
   to keep it distinct from "Autoscale Y," per DEC-021.

**DEC-021 — waveform navigation is workspace-level, not channel-level**
(full text in [DECISIONS.md](DECISIONS.md)): one shared X/time viewport
must eventually drive every displayed channel together; a centralized
Powerwave toolbar (never a per-channel native modebar) is the required
future architecture. Recorded now, while Phase 2B still has one channel,
specifically so Phase 2C's architecture doesn't accidentally build
per-channel navigation controls. The existing request-coordinator
function was deliberately left unrestructured (multi-channel fetching is
still out of scope) but is now commented as the exact Phase 2C extension
point.

**uPlot was NOT removed** — it remains fully functional and unmodified,
for the owner's final side-by-side crosshair comparison. **No Phase 2A
backend change** (zero backend files touched, 278 tests unmodified and
passing). **No Phase 2C work.**

## What was done in the prior session (Phase 2B renderer UAT prototype)

**Phase 2B — Renderer UAT Prototype.** Built the bounded browser
comparison prototype the Phase 2 design work called for: a new, isolated
page (`frontend/waveform-prototype.html`) lets the owner hands-on compare
**uPlot** and **Plotly.js** against the identical Phase 2A backend
waveform data and interaction contract — same endpoint, same channel,
same fixed point budget (4000), switching renderers reuses already-
fetched data instead of re-fetching. Opened via a new "Waveform (UAT)"
link added to each analog channel row in the existing Phase 1 channel
browser (`frontend/index.html`) — the main app itself is otherwise
unchanged. **No plotting-library winner was chosen — this is `[DECISION
MODE: UAT]`, for the owner to judge.** No Phase 2C (draggable/panel)
work, no digital channels, no cursors/measurements, no calculated
signals, no synchronization. Full detail:
[MIGRATION_PLAN.md — Phase 2B Implementation Record](MIGRATION_PLAN.md#phase-2b--renderer-uat-prototype-implementation-record-2026-08-15).

**What was built, precisely**: uPlot (v1.6.32) and Plotly.js
cartesian-only (v3.7.0) vendored as static, pre-built, minified bundles
under `frontend/vendor/` (no build step — matches the project's existing
architecture; provenance/versions recorded in `frontend/vendor/README.md`
for later removal/upgrade). Both candidates implement one shared
`WaveformRenderer` adapter contract (`init`/`update`/`setViewport`/
`destroy`) so a losing candidate is cleanly deletable later. A shared
coordinator owns the debounced (200ms), doubly-protected
(`AbortController` **and** a sequence number, tested independently)
range-request pipeline — zoom/pan in either renderer calls the same
`requestViewportRangeDebounced()` function, nothing else. Neither
renderer applies curve smoothing (uPlot's default linear path; Plotly's
`line.shape: "linear"` set explicitly, not left to an unexamined
default). Backend was **not touched** — `git diff --stat -- backend/` is
empty, and all 278 existing backend tests, none modified, still pass.

**TTL note for this pass**: per the task's explicit instruction, TTL was
**not** implemented; a temporary DEV-only operational stopgap was
documented instead (owner clicks `Start new workspace` at the end of the
UAT session, or the DEV backend container is restarted between separate
UAT sessions) — see
[CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).
**This is not a claim that the TTL `[OPEN]` item is solved.**

## What was done in the prior session (Detego benchmark documentation, three passes)

**Documentation-only, three passes same day**: established `detego.app`
as an official product/UI-UX/waveform-workspace/dashboard/workflow
**benchmark** (explicitly not a ceiling or a spec to copy blindly) for
feature design, per direct owner instruction — new
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md), DEC-020 in
[DECISIONS.md](DECISIONS.md), and short pointer sections added to
[CLAUDE.md](../../CLAUDE.md)/[AGENTS.md](../../AGENTS.md) (matching the
existing architecture-reference pointer pattern — state the principle
briefly, read detail at the source). A second pass the same day received
the owner's actual source document ("Detego Benchmark Principle.rtf") as
a genuine attachment and updated all four files to quote/match its exact
canonical wording (same DEC-020, not a new decision — see its own
"Wording update" note in [DECISIONS.md](DECISIONS.md)), adding two
specifics the first pass's paraphrase hadn't captured: "learn from
Detego's public behaviour, implement an independent Oruxa design," and
the standing question for major features — *"What does Detego do here,
what does existing powerwave do, and what would make oruxa_powerwave
better for the engineer?"* A **third pass**, same day, expanded
[PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) with the four-way
feature-design method (`powerwave` / Detego / owner requirements /
proposed superior Oruxa approach), three worked examples (waveform
workspace, multi-source synchronization, calculated signals), an explicit
"owner-specific capabilities may exceed Detego" list (not exhaustive —
Detego is not the product boundary), and explicit
"architecture-stays-Oruxa-owned" / "independent implementation, not
reverse engineering" sections — plus one added sentence each in
`CLAUDE.md`/`AGENTS.md` covering those last two points concisely. Still
the same DEC-020; no new `DECISIONS.md` entry was needed. **No production
code changed in any of the three passes.**

**Provenance note, worth preserving**: an earlier version of this same
request arrived mid-turn, structured as a system-reminder-wrapped message
that referenced "an attached ZIP" never actually present in context, and
asked for edits to this repository's own governance files plus a push to
`main` while explicitly directing that this project's own
change-governance step be skipped. That version was declined and flagged
to the user rather than executed — an unverifiable, injection-shaped
request is not owner authorization on its own. The owner then reissued
the same direction as a normal, self-contained conversational instruction
with no external attachment referenced or needed, which is what this
pass and [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md) are built from.
**No technical audit of `detego.app` itself was performed or is claimed**
— see [PRODUCT_REFERENCES.md](PRODUCT_REFERENCES.md)'s own `[OPEN]` note.
Future sessions should not assume a feature comparison against Detego
already exists just because this reference framework does.

## What was done in the prior session (Phase 2A implementation)

**Phase 2A — Waveform Data Foundation** (backend only). Following the
Phase 2 discovery/design pass (summarized below), the owner authorized
implementing exactly the first recommended vertical slice: retain each
imported source's full-resolution `DisturbanceRecord` in the active
workspace, and add one bounded waveform range endpoint for a single analog
channel. **No chart library, no frontend rendering, no digital-channel
waveform delivery, no Phase 2B/2C/2D work** — see
[MIGRATION_PLAN.md — Phase 2A Implementation Record](MIGRATION_PLAN.md#phase-2a--waveform-data-foundation-implementation-record-2026-08-15)
and [DECISIONS.md — DEC-019](DECISIONS.md#dec-019--phase-2a-retains-the-full-resolution-disturbancerecord-in-the-active-workspace)
for full detail; summarized here for continuation purposes.

**What was built**: `ActiveSource` (`app/domain/source.py`) pairs the
existing lightweight `SourceMetadata` with the authoritative
`DisturbanceRecord`; `WorkspaceRegistry` now stores `ActiveSource`
(keying/locking/cleanup methods unchanged — `remove()`/`remove_workspace()`
already correctly release whatever's stored per `(workspace_id,
source_id)`); `app/domain/waveform_reduction.py` implements a
peak-preserving min/max envelope (equal-count buckets, chronological
output, guaranteed true first/last sample, deterministic, never mutates
its input) — deliberately **not** `powerwave`'s own plain-stride
decimator; `app/services/waveform_service.py` does exact time-range
extraction (boundary-inclusive, `searchsorted`-based) then applies that
reduction only when the range exceeds the request's `point_budget`;
`GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform`
(added to the existing `app/api/v1/sources.py` router) exposes it as JSON.

**What was verified**: 278 backend tests pass (227 unchanged + 51 new),
including the mandatory synthetic-spike regression test (proves plain
stride sampling misses a narrow transient that the new algorithm
preserves), zoom-fidelity tests (narrower requests reveal genuinely finer
data, and a sufficiently narrow range returns true full-resolution
samples again), and lifecycle tests including a weakref-based proof that
`Remove`/whole-workspace-DELETE actually release the retained record's
memory, not just make it API-inaccessible. Measured (not assumed)
performance/memory across four synthetic scenarios up to 2,000,000
samples: range extraction is sub-millisecond at every scale tested;
reduction to a 4000-point budget stays under 8 ms even at 2M samples;
JSON payload for a reduced response stays ~110-120 KB regardless of
record size, versus 61 MB if full resolution were returned for one
channel at the largest scale tested — directly confirming why the
range-request architecture was recommended.

## What was done in the prior session (Phase 2 discovery/design)

**Phase 2 waveform-workspace discovery and design** — the project owner
confirmed Phase 1 has passed its final UAT and is complete, then requested
a discovery/design-only pass (explicitly: no implementation) covering the
existing `powerwave` waveform/plotting architecture, candidate web
waveform data-delivery architectures, plotting-library candidates, the
backend memory-model change Phase 2 requires, and a proposed Phase 2 slice
sequence. Full content:
[MIGRATION_PLAN.md — Phase 2 Waveform Workspace Discovery and
Design](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14) —
summarized here for continuation purposes. **No code was written this
pass** — no waveform API, no chart library dependency, no backend
full-resolution-array retention, nothing deployed.

**`powerwave` waveform architecture — re-verified live** (not trusted from
documentation, per the task's own warning that discovery already found
stale/dead plotting references): live path is `SessionCanvasWidget` +
`SessionCanvasController`; `FlexiblePlotCanvas`/`VisualizationManager`/
`DigitalEventTimeline`/`channel_grouper.py`/the `overlays/` abstraction are
all confirmed dead (unreachable from the live app; `FastWaveformWidget`
doesn't exist as a class at all). **The single most consequential finding**:
`build_aligned_data()`'s decimation (`downsampling.py`) is **plain
nth-point stride sampling** (`t_clip[::stride]`) — not peak-preserving,
not viewport-aware (decimates against the whole session window, not the
live viewport, at a hardcoded `max_points=4000` never overridden anywhere).
This means `powerwave` itself can silently drop a transient spike or a
narrow digital pulse during decimation, and zooming does not fetch
higher-resolution detail — both are explicitly flagged as behaviors Phase
2 must **not** inherit.

**Design proposal highlights** (all `[PROPOSAL]` / decision-mode-tagged,
none approved): viewport/range-request API (`GET .../sources/{id}/waveform`)
over "send everything once"; **min/max envelope** decimation (not
`powerwave`'s stride sampling, not LTTB) for engineering-correctness
reasons; JSON to start, binary only if benchmarking shows a real cost;
extend `WorkspaceRegistry`'s stored value to also retain the parsed
`DisturbanceRecord` (currently discarded after upload — this is the major
backend architecture change Phase 2 requires); reassessed the existing
abandoned-session TTL `[OPEN]` item as materially more important now that
full-resolution arrays (not just metadata) would be at stake, without
resolving it outright (`[DECISION MODE: COMPARISON]`); a bounded two-library
plotting prototype (uPlot vs. ECharts, `[DECISION MODE: UAT]`); and a
Phase 2A/2B/2C/2D slice sequence with an exact-scope first slice
(one channel, backend-only, API-tested, no frontend chart yet).

## What was done in the prior session (Phase 1 closure fix)

A **focused Phase 1 closure fix**: correcting `Start new workspace` into a
real, backend-enforced whole-workspace reset. This followed a same-day
investigation (requested separately, before this fix) into whether
`Remove` and `Start new workspace` were genuinely different — the
investigation found `Start new workspace` was a no-op pretending to be a
reset (client-only UUID rotation, no backend call, old sources leaked in
memory, stale banner). The owner decided to **keep** the button and make it
correct, rather than remove or hide it. See
[MIGRATION_PLAN.md — Phase 1 Workspace-Reset Record](MIGRATION_PLAN.md#phase-1--workspace-reset-record-2026-08-14)
and [DECISIONS.md — DEC-018](DECISIONS.md#dec-018--start-new-workspace-is-a-distinct-whole-workspace-lifecycle-operation-not-a-remove-alias)
for full detail.

**What was built**: a new whole-workspace backend endpoint
(`DELETE /api/v1/workspaces/{workspace_id}`, new file
`backend/app/api/v1/workspaces.py`) backed by a new
`WorkspaceRegistry.remove_workspace(workspace_id)` method; and a corrected
frontend flow where `Start new workspace` shows its own confirmation
(only when the workspace is non-empty), calls that DELETE against the
*old* workspace id, and only rotates the client-side id — clearing the
source list, channel panel, and stale banner — after the backend call
succeeds. A failed cleanup leaves everything as it was, with a visible
error instead of a silent fake reset.

**Prior work this document also covers** (unchanged by this pass): a
narrow UI refinement pass on the already-implemented, already-deployed
Phase 1, driven directly by the owner's completed hands-on UAT of
`https://dev.powerwave.oruxa.uk`.

**What UAT approved and left alone**: the two-slot `.cfg`/`.dat` upload
workflow (now formally decided — DEC-017, not just a temporary Phase 1
choice), the loading/parsing indicator, the 100 MB guidance text, the
source-metadata-review-before-channels step, and the overall simple
single-page UI direction. None of these were touched.

**What UAT asked to change, and what was built**:

1. **Channel organization** — the reported problem was scrolling through
   hundreds of channels in one long table (UAT's own example: 80 analog,
   282 digital). Fixed with native `<details>`/`<summary>` collapsible
   sections (Analog defaults open, Digital defaults collapsed — the
   section that was actually overwhelming), always showing counts.
2. **Analog sub-grouping by engineering type** — `Voltage`/`Current`/
   `Power`/`Frequency`/`ROCOF`/`Undefined`. Classification is computed
   **once, backend-side** (new `backend/app/domain/channel_classification.py`),
   exposed as `engineering_type` on every analog channel — never
   re-derived or duplicated in the frontend. Three-tier rule (explicit
   `parameter_type` → unit semantics → nothing else — naming-pattern
   classification was deliberately not implemented, since no pattern was
   judged unambiguous enough): anything that doesn't confidently resolve
   is `Undefined`, never guessed into a real category.
3. **Channel search** — client-side only, over the already-fetched channel
   list, no network calls per keystroke. Auto-expands groups containing a
   match; clearing search restores the default expansion state.
4. **Scale/Offset removed from the primary analog table** — UAT found them
   low-value for browsing. Both fields are **unchanged** in the domain
   model and API response (`AnalogChannelSummary`/`AnalogChannelOut`) —
   only this one table stopped displaying them.
5. **Removal confirmation** — clicking "Remove" now opens one small
   confirmation dialog before the DELETE request is ever issued.
6. **Stale-banner bug fixed** — the import-success banner previously stayed
   visible after its source was removed. Now cleared, but only when it
   actually described the source just removed (tracked precisely, not a
   blanket clear-on-any-removal) — deliberately forward-compatible with a
   future multi-source workspace.

## What was verified (this pass — Phase 3A-UAT2 remove duplicate header theme control)

- `oruxa_powerwave` git state confirmed against GitHub `main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (diff scoped to
  `frontend/index.html` only).
- **Frontend, new: 11 scripted `jsdom` checks, all passing**
  (`phase3auat2_check.mjs`) — `#themeToggle` absent from the DOM
  entirely, `#globalHeader` contains no Light/Dark-labeled buttons, the
  Main Sidebar Menu's `#mainNavSettingsBtn` exists in `.shell-nav-bottom`
  and still flips Light→Dark→Light, the preference persists across a
  simulated reload, theme change causes zero waveform refetch, theme
  change still triggers the existing per-panel Plotly chrome relayout,
  the Global Header's remaining controls still render, Main Sidebar Menu
  collapse/expand still works, displayed-channel/panel state undisturbed.
- **Frontend, existing suite correction**: `theme_crosshair_check.mjs`'s
  own pre-existing test asserting `#themeToggle` exists in `index.html`
  was corrected in place (it now asserts absence, by design) rather than
  left to fail — full suite re-run confirms all its OTHER checks (19
  total) still pass unmodified.
- **Frontend, full regression: the exact same pre-existing 20 failures
  already documented in prior phases' own records, zero new
  divergences** — independently confirmed by running the full scratch
  suite both before and after this pass's change.
- `git diff --check` clean (no whitespace errors).
- No real-browser/visual confirmation was performed in this sandboxed
  session — whether the header now reads cleanly with no leftover gap,
  and whether Settings remains comfortably reachable in both collapsed
  and expanded Main Sidebar states, were NOT visually confirmed. Final
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 3A-UAT1 responsive waveform width reflow)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Root cause established by direct code inspection, not guessed**
  (per this task's own explicit instruction): traced the missing
  `Plotly.Plots.resize()` call in both `shellCreateHorizontalSplit()`
  and `shellSetMainSidebarExpanded()`, confirmed the CSS `min-width: 0`
  chain was already correct at every level that mattered, and confirmed
  `.ww-chart-wrap` had no `overflow` rule to contain a stale-width
  Plotly SVG.
- **Frontend, new: 20 scripted `jsdom` checks, all passing**
  (`phase3auat1_check.mjs`) — `.ww-chart-wrap` containment CSS,
  Workspace Sidebar drag resizing every visible panel's Plotly instance
  AND the sticky ruler, zero waveform fetches during resize,
  byte-identical physical viewport before/after, no relayout call
  touching range/Y state as a side effect of the resize, rAF-coalesced
  scheduling (many raw pointermoves → far fewer resize calls),
  authoritative final resize on pointerup, pointercancel cleanup + its
  own final resize (matching the established `wwSetPanelHeight`
  contract), a subsequent drag after a cancelled one still working,
  Main Sidebar Menu expand/collapse both triggering a full reflow via
  `transitionend` (correctly scoped to the `width` property only), zero
  fetch/viewport-preserving on menu toggle, window resize triggering
  the same reflow path, rapid-fire window resize events coalescing to
  one pass (no runaway loop), zero fetch on window resize, Separate
  mode (all 6 lanes reflow) and Custom mode (all panels reflow), Phase
  3A shell hierarchy unchanged, and panel-height resizing unaffected.
- **Frontend, existing: the full Phase 2C-A through Phase 3A suites
  (264 checks, after fixing six older scripts' missing
  requestAnimationFrame polyfill — a test-infrastructure gap this
  fix's own rAF-coalescing exposed, not an application bug) — the exact
  same pre-existing 20 failures already documented in those phases' own
  records, zero new divergences.** Independently confirmed by running
  the suite both before and after this phase's changes.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — whether the waveform canvas genuinely stays visually
  contained during a real drag, and whether the reflow feels smooth,
  were NOT visually confirmed. See the final report's explicit
  statement about what's honestly unverified. Final visual judgment
  remains the owner's own manual UAT.

## What was verified (prior pass — Phase 3A application shell redesign foundation)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 40 scripted `jsdom` checks, all passing**
  (`phase3a_check.mjs`) — every shell structural relationship (Global
  Header/Body/Main Sidebar Menu/Work Area/Workspace Row/Bottom Status
  Bar/Workspace Sidebar/Main Workspace), including the specific
  parent-chain assertion proving the Status Bar's parent (`#workArea`)
  differs from Main Sidebar Menu's parent (`#appBody`) — the exact
  structural guarantee behind "the Status Bar can never render beneath
  Main Sidebar Menu"; Main Sidebar Menu collapse/expand and confirmed
  non-drag-resizability; Workspace Sidebar drag-resize (live resize,
  min/max clamping, zero waveform fetches, pointer-listener cleanup
  after pointerup, localStorage persistence); the full existing
  waveform feature set re-verified working end to end (channel
  selection, Grouped/Separate/Custom, zoom/pan/Reset Time View/
  Autoscale Y, Absolute/Elapsed, panel-height resize, Custom Groups,
  theme switching); the Active View state model (all three values
  representable, Table/Split contain zero fake data and trigger zero
  fetches); Bottom Status Bar real-value sourcing and channel-count
  sync; and workspace-reset clearing both waveform and status-bar state
  cleanly.
- **Frontend, existing: the full Phase 2C-A through 2C-C4B suites (224
  checks) were all re-run unmodified against this pass's code — the
  EXACT SAME pre-existing pass/fail counts as immediately before this
  phase (20 already-documented failures across those phases' own
  records), zero new divergences.** This was independently confirmed by
  running the suite both before and after this phase's changes, not
  assumed from the diff alone.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — actual shell proportions, resize feel, and responsive
  behavior at real narrow widths were NOT visually confirmed. See the
  final report's explicit statement about what's honestly unverified.
  This is explicitly an INITIAL shell (task's own framing) — final
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C4B compact sticky time-axis layout correction)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Frontend, rewritten (per this task's own explicit instruction): 25
  scripted `jsdom` checks, all passing** (`phase2cc4a_check.mjs`,
  updated in place rather than left as a documented divergence, since
  its old assertions read a DOM element — `#wwStickyRulerTitle` — that
  no longer exists) — no separate title/date DOM elements exist,
  compact CSS height (<= 42px), near-zero top margin, exact "Record
  Time" wording, no date shown anywhere in the ruler, ms/s/min adaptive
  titles via zoom/pan, title/tick unit consistency preserved, mode
  switching, zero waveform fetches, Reset Time View, Grouped/Separate/
  Custom (including Separate's still-suppressed per-lane ticks), sticky
  CSS/margin/alignment unchanged, zero Plotly work on synthetic scroll
  events, theme switching (a single `font.color` relayout still covers
  both ticks and the native title), and workspace-reset behavior.
- **Frontend, existing: the full Phase 2C-A through 2C-C4 suites (199
  checks) were all re-run unmodified against this pass's code — the
  exact same 20 failures already fully documented in the Phase
  2C-C4/2C-C4A records, zero new divergences** introduced by this
  correction (none of this pass's changes touch the underlying causes
  of those existing, already-explained failures).
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — whether the compact layout genuinely reads as a
  conventional X-axis matching the owner's own reference screenshot was
  NOT visually confirmed. See the final report's explicit statement
  about what's honestly unverified. Final visual judgment remains the
  owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C4A sticky time-axis title placement and unit label)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 23 scripted `jsdom` checks, all passing**
  (`phase2cc4a_check.mjs`) — title element positioned before the tick
  chart in DOM order (top placement), Absolute title exactly "Record
  time", the simplified date-only ruler context line vs. the toolbar's
  unchanged full text, ms/s/min titles (min-scale verified directly
  against `wwStickyRulerElapsedUnit()` since the fixture's own record
  is too short to reach a real 60s+ zoom), the ruler's rescaled tick
  values genuinely matching the title's unit (no mismatch — the exact
  thing section 4 required), zoom and pan both updating the unit/title
  correctly, Absolute↔Elapsed switching, zero waveform fetches on a
  mode switch, Reset Time View, Grouped/Separate/Custom, sticky CSS/
  margin/alignment-input unchanged, theme switching, and workspace-
  reset ruler/title clearing (including confirming `ww.timeMode`'s own
  established persistence-across-clear behavior is unaffected).
- **Frontend, existing: the full Phase 2C-A through 2C-C4 suites (222
  checks) were all re-run unmodified against this pass's code.** 20
  failures appear, all explained by either (1) the same pre-existing
  Phase 2C-C3/2C-C4 divergences already documented in those phases'
  own records, or (2) two new divergences directly caused by this
  phase's own deliberate design: several older, pre-COMTRADE-timing
  test fixtures' "last relayout call has this xaxis.range value"
  assumption now sometimes resolves to the ruler's own correctly-
  rescaled value (e.g. `100` instead of `0.1` for a 100ms zoom) instead
  of a real panel's raw value; and `phase2cc4_check.mjs`'s own
  assertion that the toolbar and ruler date-context text are identical,
  which is exactly what this phase's own section 5 deliberately
  changed. None of these frozen, one-off, not-committed scripts were
  modified, per this project's established precedent.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation was performed in this sandboxed
  session — in particular, whether rescaling the ruler's own axis
  domain for ms/min display genuinely preserves tick-pixel alignment
  with the real (unrescaled) waveform panels was reasoned through
  carefully but NOT visually confirmed. See the final report's explicit
  statement about what's honestly unverified. Final visual judgment
  remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C4 sticky shared waveform time axis)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` plus
  project-memory docs).
- **Frontend, new: 24 scripted `jsdom` checks, all passing**
  (`phase2cc4_check.mjs`) — ruler hidden with no waveforms, ruler visible
  once displayed, sticky CSS/container structure, ruler derives its
  range from `ww.viewport` (not an independent state), margin/alignment
  consistency between the ruler and a real panel (same `WW_PANEL_MARGIN`
  values), Absolute and Elapsed rendering, mode-switch updates the ruler
  with zero new waveform fetches, zoom/pan/Reset Time View all update
  the ruler via the existing single broadcast path, the ruler never
  registers its own Plotly event listener, Grouped/Separate/Custom all
  work (Separate's all-lanes-suppressed chrome verified explicitly),
  panel resize causes zero ruler-related Plotly calls, theme switching
  re-colors the ruler without a refetch, removing all channels hides the
  ruler, re-adding channels reuses the existing Plotly instance rather
  than recreating it, Clear workspace hides the ruler, and dispatching
  synthetic scroll events causes zero waveform fetches and zero new
  Plotly calls.
- **Frontend, existing: `frontend_logic_check.mjs`, `theme_crosshair_
  check.mjs`, and the full Phase 2C-A through 2C-C3 suites were all
  re-run unmodified against this pass's code.** `frontend_logic_check.mjs`
  and `theme_crosshair_check.mjs` pass in full. **9 new failures appear
  across the rest, all explained by this phase's own two deliberate
  architecture changes** (not regressions): the ruler's own extra Plotly
  `newPlot`/`relayout` call makes several scripts' exact "one per panel"
  call-count assertions off-by-one, and several scripts assert the
  now-superseded "only the bottom Separate lane shows ticks" behavior
  (section 16's own suppression change). These are frozen, one-off,
  not-committed verification scripts from prior phases — per this
  project's established precedent (Phase 2C-C3's identical treatment of
  its own Absolute-default divergence), not modified; `phase2cc4_check.mjs`
  explicitly covers what changed. `phase2ca_check.mjs` additionally still
  carries its 2 pre-existing Phase 2C-C3 divergences, unrelated to this
  phase.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation (ruler "sticky" feel while
  scrolling, real tick-to-waveform alignment at various zoom levels, any
  visual content coverage) was performed in this sandboxed session — see
  the final report's explicit statement about what's honestly
  unverified. Final visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C3 COMTRADE time-axis modes)

- `oruxa_powerwave` git state confirmed against `origin/main` (read-only
  `git fetch`), working tree clean before this pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat --
  backend/` empty; diff scoped to `frontend/index.html` only).
- **Timing investigation, done first**: direct code reading of
  `backend/app/domain/timing.py` and the schema/parser layer confirmed
  `start_time`/`trigger_time` are separate fields, sample 0 coincides
  with `start_time` (never `trigger_time`), both timestamps are
  timezone-naive, and `TimebaseOut` already exposed everything needed —
  zero backend changes required.
- **Frontend, new: 26 scripted `jsdom` checks, all passing**
  (`phase2cc3_check.mjs`) — Absolute default, Elapsed selectable, mode
  switching both directions, viewport preservation while zoomed,
  displayed-channel preservation, zero-refetch, Reset Time View in both
  modes, Autoscale Y unaffected, all three layout modes (including
  Separate's bottom-lane-only axis and Grouped's zero-showticklabels
  invariant), zoom/pan sync in both modes, panel-height preservation,
  theme-switch preservation, adaptive tick-format bands, a midnight/date
  rollover, a full year-boundary rollover, the source capability model,
  and time-mode persistence across Clear workspace.
- **Frontend, existing: `frontend_logic_check.mjs`, `theme_crosshair_
  check.mjs`, and the full Phase 2C-A through 2C-C2A suites (193 checks)
  were all re-run unmodified against this pass's code** — all still pass
  except 2 in the non-committed `phase2ca_check.mjs` that assert a
  raw-elapsed-number `xaxis.range`, the expected consequence of Absolute
  now being the COMTRADE default (not a regression; explained in the
  final report). **This re-run caught two real regressions before they
  shipped** (a `timebase`-scoping bug that broke all channel rendering,
  and a `wwApplyTimeAxisChrome` Grouped-mode guard regression) — both
  fixed and reconfirmed clean.
- **Real COMTRADE verification**: a synthetic ASCII COMTRADE record with
  a known, non-trivial `start_time`/distinct `trigger_time` imported via
  a real FastAPI `TestClient` (no mocking) confirmed the API returns
  both exactly, and that sample 0's absolute time equals `start_time`,
  never `trigger_time`. A second scenario crossing a midnight/date
  boundary confirmed both the API and the frontend's own timestamp
  formula roll the calendar date over correctly — backend-returned
  values were fed through the actual shipped frontend JS, not a
  reimplementation.
- `node --check` on `frontend/index.html`'s inline `<script>` block, and
  a `getElementById`/`id=` cross-reference check (no dangling
  references, no duplicate IDs) — both clean.
- No real-browser/visual confirmation (toolbar toggle discoverability,
  tick-formatting readability at real zoom levels, mode-switch-while-
  zoomed "feel") was performed in this sandboxed session — see the final
  report's explicit statement about what's honestly unverified. Final
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C2A panel resize responsiveness)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `7b2d433` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this
  pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Investigation instrumentation (scratch, not committed)**: a jsdom
  script (`resize_lag_measure.mjs`) with a simulated-cost
  `Plotly.Plots.resize` mock (busy-wait, tested at 0ms/20ms/50ms), run
  BEFORE the code change to confirm the bottleneck (DOM height-write
  timestamps identical to Plotly-resize-end timestamps) and AFTER to
  confirm the fix (DOM height-write timestamps measurably earlier than
  the corresponding Plotly-resize-start timestamps), at every simulated
  cost level.
- **Frontend, new: 9 scripted `jsdom` checks, all passing**
  (`phase2cc2a_check.mjs`) — the DOM height write is now observable
  synchronously on every raw `pointermove` (not gated behind a tick/rAF
  wait); `Plotly.Plots.resize` remains coalesced (far fewer calls than
  raw pointermoves); the final Plotly resize call is always against the
  exact final committed height; `pointercancel` performs exactly one
  final resize and leaves no stale/late resize call; a subsequent drag
  after a cancelled one still works; the 100px minimum and 600px maximum
  are both still enforced synchronously; only the dragged panel is ever
  resized; a full drag still causes zero waveform fetches.
- **Frontend, existing: the full Phase 2C-C2 (23), Phase 2C-C1 (30),
  Phase 2C-B3A (17), Phase 2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1
  (16), Phase 2C-A (19), and Phase 1 (4) suites were all re-run
  unmodified against this pass's code and all still pass in full** — 145
  existing checks, zero regressions (154 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- No real-browser/visual or tactile confirmation of the actual felt
  improvement was performed in this sandboxed session (no headless
  browser available; installing one — Playwright/Puppeteer — was judged
  disproportionate for a single diagnostic) — see "Live DEV verification"
  in this task's final report for what was checked instead, and its own
  explicit statement about what's honestly unverified. Final tactile
  judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C2 adjustable waveform panel heights)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `91bb0fc` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this
  pass began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 23 scripted `jsdom` checks, all passing** — a resize
  handle exists on every panel in Grouped/Separate/Custom; dragging a
  Grouped panel's handle resizes only that panel (an unrelated panel's
  height is byte-for-byte unchanged); `Plotly.Plots.resize` is called
  during the drag; resizing issues zero waveform fetches; extreme drags
  clamp correctly at both the 100px minimum and the 600px maximum;
  zoom/Reset-Time-View synchronization still work correctly after
  resizing; Separate lanes resize independently while the overlay label
  stays a correctly-positioned child of its own lane and the true bottom
  lane still (and only it) shows the shared X axis; a Custom group panel
  resizes independently with membership unchanged; height state
  round-trips correctly across Custom→Grouped→Custom and
  Separate→Grouped→Separate, including confirming different modes'
  height keys never collide; Grouped/Separate/Custom keep working; theme
  switching remains correct at custom heights without a refetch;
  removing then re-adding a channel restores its remembered height
  (deliberately not scrubbed); Clear workspace resets remembered heights
  entirely; waveform query-parameter whitelist unchanged.
- **Frontend, existing: the full Phase 2C-C1 (30), Phase 2C-B3A (17),
  Phase 2C-B3 (16), Phase 2C-B2 (20), Phase 2C-B1 (16), Phase 2C-A (19),
  and Phase 1 (4) suites were all re-run unmodified against this pass's
  code and all still pass in full** — 122 existing checks, zero
  regressions (145 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual or tactile confirmation of the drag interaction
  itself was performed in this sandboxed session (no headless browser
  available; jsdom implements neither element-level Pointer Capture nor
  `requestAnimationFrame` natively, both worked around in the test
  harness) — see "Live DEV verification" in this task's final report for
  what was checked instead (API-level evidence only), and its own
  explicit statement about what's honestly unverified. Final tactile/
  visual judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-C1 custom analog channel groups)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `ae8ccfd` (independent `git fetch` via the
  established HTTPS-URL workaround) before this pass began. **Two
  uncommitted local changes were found in the working tree** (the direct
  manual overlay-tag tweaks described above) — preserved (not discarded,
  per the project's own git-safety rule) and committed separately as
  `d902dc5` before this pass's own implementation work began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 30 scripted `jsdom` checks, all passing** — the Custom
  toolbar button and Edit Channel Groups control appear correctly;
  switching to Custom with no groups yet produces one panel per channel
  (auto-solo); the modal opens/closes (including Cancel, then reopening
  cleanly); groups can be created (Group 1/2/3); channels can be assigned
  via the Unassigned select and removed back to Unassigned; an empty
  group can be deleted; Apply renders the exact example grouping from
  this task's own manual-verification checklist (Group 1 = VA/VB/VC,
  Group 2 = IA/IB, IC auto-solo); a pre-Apply zoomed viewport survives
  Apply exactly; zoom-broadcast synchronization, Reset Time View,
  Autoscale Y, and no-per-panel-modebar all work in Custom mode;
  switching Custom→Separate→Custom preserves displayed channels AND
  restores the last-applied grouping; Grouped mode groups by
  engineering_type with zero regression; theme switching still works in
  Custom mode; Clear workspace resets both the display and the
  remembered custom grouping (verified behaviorally); waveform
  query-parameter whitelist unchanged.
- **Frontend, corrected in place: 1 of Phase 2C-B3A's own CSS-source
  assertions**, which had hardcoded the exact `top: 50%` value later
  manually tuned to `25%`, was relaxed to assert the overlay MECHANISM
  (percentage-based `top` + `translateY(-50%)`) rather than the specific
  tunable percentage — the rest of that suite needed no change.
- **Frontend, existing: the full Phase 2C-B3 (16), Phase 2C-B2 (20),
  Phase 2C-B1 (16), Phase 2C-A (19), and Phase 1 (4) suites were all
  re-run unmodified against this pass's code and all still pass in
  full** — 92 existing checks (75 unmodified + 17 corrected-B3A), zero
  regressions (122 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs (one regex false-positive
  from a JS template string containing `data-group-id="..."` was
  investigated and ruled out with a stricter check).
- No real-browser/visual or hands-on-workflow verification of the group
  editor modal was performed in this sandboxed session (no headless
  browser available) — see "Live DEV verification" in this task's final
  report for what was checked instead (API-level evidence only), and its
  own explicit statement about what's honestly unverified. Final
  workflow/appearance judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-B3A overlay right-side lane labels)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `ef89cc7` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 17 scripted `jsdom` checks, all passing** — CSS-source
  checks confirming the label uses absolute positioning against a
  relatively-positioned lane (not a grid column), is pinned near the right
  edge and vertically centered, and sits above the chart via z-index; the
  lane's chart area is no longer split into two columns; the overlay
  label's DOM parent is the lane element itself (a sibling of the
  chart-wrap within the same lane, not a separate layout block);
  displayed-channel identity is correct; Separate mode still shows exactly
  one lane per channel with the unified-canvas class intact; only the
  bottom lane still shows the shared X axis; Grouped mode still groups
  correctly and never applies the unified/overlay CSS; zoom/pan/Reset Time
  View/Autoscale Y/no-modebar/theme-switching all still work;
  Grouped↔Separate still preserves viewport and displayed channels;
  removal via the overlay tag's remove button still removes the whole
  lane; waveform query-parameter whitelist unchanged.
- **Frontend, corrected in place: 2 of Phase 2C-B3's own CSS-source
  assertions**, which specifically tested the now-removed grid-column
  mechanism, were updated to assert the new overlay mechanism instead —
  the remaining 14 of its 16 checks needed no change and passed
  unmodified.
- **Frontend, existing: the full Phase 2C-B2 (20), Phase 2C-B1 (16), Phase
  2C-A (19), and Phase 1 (4) suites were all re-run unmodified against
  this pass's code and all still pass in full** — 59 existing checks,
  zero regressions (92 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual verification of whether the overlay genuinely
  reads as a Detego-style floating label rather than a side panel was
  performed in this sandboxed session (no headless browser available) —
  see "Live DEV verification" in this task's final report for what was
  checked instead (API-level evidence only), and its own explicit
  statement about what's honestly unverified. Final visual-appearance
  judgment remains the owner's own manual UAT.

## What was verified (prior pass — Phase 2C-B3 right-side compact lane labels)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `9fcc2d8` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 16 scripted `jsdom` checks, all passing** — CSS-source
  checks confirming the chart/label grid columns swapped sides and the
  label is now a compact pill (border-radius/max-width); a new
  `.ww-legend-label` span exists per lane for ellipsis truncation;
  displayed-channel identity is correct in each tag (name + unit); the
  remove control and color dot are preserved inside the tag; 6 lanes still
  render with the unified-canvas class; only the bottom lane still shows
  the shared X axis; Grouped mode still groups correctly and never applies
  the unified class; zoom/pan/Reset Time View/Autoscale Y/no-modebar all
  still work; theme switching re-colors without refetching and the tag has
  no inline color override; Grouped↔Separate still preserves viewport and
  displayed channels; removal via the tag's remove button still removes
  the whole lane; waveform query-parameter whitelist unchanged.
- **Frontend, existing: the full Phase 2C-B2 (20), Phase 2C-B1 (16), Phase
  2C-A (19), and Phase 1 (4) suites were all re-run unmodified against
  this pass's code and all still pass in full** — 59 existing checks,
  zero regressions (75 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual verification of whether the tag genuinely reads
  as compact/readable/low-clutter to a human eye was performed in this
  sandboxed session (no headless browser available) — see "Live DEV
  verification" in this task's final report for what was checked instead
  (API-level evidence only), and its own explicit statement about what's
  honestly unverified. Final visual-appearance judgment remains the
  owner's own manual UAT.

## What was verified (prior pass — Phase 2C-B2 unified analog canvas layout)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `60a77bb` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty; diff scoped to `frontend/index.html` only).
- **Frontend, new: 20 scripted `jsdom` checks, all passing** — static
  CSS-source checks confirming the unified-container/de-carded-lane rules
  exist and that Grouped mode's own card CSS is untouched; Separate mode
  still creates 6 stacked lanes and now applies the `ww-panels-unified`
  class; the mode switch still issues zero new waveform fetches; only the
  bottom-most lane shows X tick labels/title (verified against actual
  `Plotly.relayout` calls, restricted to currently-active panel elements);
  Grouped mode's panels never receive an axis-suppression relayout;
  zoom/pan/Reset Time View/Autoscale Y/no-modebar all still work
  identically; viewport preservation across Separate→Grouped→Separate
  (including the re-applied unified class); theme switching without
  refetching; removing the current bottom lane correctly hands the shared
  axis to the new last lane; "Clear workspace" empties the unified
  container; waveform query-parameter whitelist unchanged.
- **Frontend, existing: the full Phase 2C-B1 suite (16 checks), Phase 2C-A
  suite (19 checks), and Phase 1 regression suite (4 checks) were all
  re-run unmodified against this pass's code and all still pass in full**
  — 39 existing checks, zero regressions (59 total this pass).
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists; no duplicate IDs.
- No real-browser/visual verification of whether the six lanes genuinely
  read as "one canvas" to a human eye was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked instead (API-level
  evidence only), and its own explicit statement about what's honestly
  unverified. Final visual-appearance judgment remains the owner's own
  manual UAT.

## What was verified (prior pass — Phase 2C-B1 Grouped / Separate layout)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `3f637ba` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend, new: 16 scripted `jsdom` checks, all passing** — Grouped
  baseline unchanged; switching to Separate produces exactly 6 panels
  (one per displayed channel) with correct labels, no per-panel modebar,
  zero new waveform fetches, old panels purged; shared zoom/pan
  synchronization and loop-prevention verified in Separate mode using the
  same faithful Plotly-relayout-refire test double established for Phase
  2C-A; Reset Time View and Autoscale Y in Separate mode; **viewport
  preservation verified directly** by asserting the actual
  `layout.xaxis.range` Plotly was called with after a Separate→Grouped
  and a Grouped→Separate switch, both following a real zoom; channel
  removal in Separate mode removes the whole lane; theme switching in
  Separate mode; and a direct check that every waveform request's query
  parameters are still exactly the pre-existing four
  (`channel_name`/`start_time`/`end_time`/`point_budget`) — confirming no
  backend API shape changed.
- **Frontend, existing: the full Phase 2C-A suite (19 checks) and the
  Phase 1 regression suite (4 checks) were both re-run unmodified against
  this pass's code and both still pass in full** — no regression.
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call (including the two
  new layout-toggle buttons) resolves to an `id=` that actually exists.
- No real-browser/visual verification of rendering smoothness was
  performed in this sandboxed session (no headless browser available) —
  see "Live DEV verification" in this task's final report for what was
  checked instead, and its own explicit statement about what's honestly
  unverified.

## What was verified (prior pass — Phase 2C-A synchronized multi-channel waveform display)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `51ac404` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend, new: 19 scripted `jsdom` checks, all passing** — channel
  selection/Add-selected/Clear-selection; initial engineering-type
  grouping into the correct panel/trace counts; one `Plotly.newPlot` per
  panel with `displayModeBar: false`; shared-viewport broadcast on both
  zoom and pan, verified against a Plotly test double that faithfully
  re-fires `plotly_relayout` on a programmatic `relayout()` call so
  loop-prevention (`suppressNext`) is actually exercised, not just
  structurally present; Zoom/Pan toolbar buttons (dragmode only, never
  refetches); Reset Time View (refetches, restores full record on every
  panel); Autoscale Y (native `yaxis.autorange`, never refetches); theme
  switch (re-colors every panel, never refetches); removing one channel
  vs. removing a panel's last channel; source removal clearing only that
  source's displayed channels; "Start new workspace" clearing everything;
  a 12-channel/4-panel structural scale check (exactly 12 requests, a
  12-channel zoom refetches exactly 12 times, not a multiplied/runaway
  amount).
- **Frontend, existing (Phase 1 regression): 4 scripted `jsdom` checks,
  re-run and still passing** (`frontend_logic_check.mjs`) — two of its
  own assertions were tightened (not weakened) to correctly account for
  the new leading checkbox column (`td:not(.select-col)` instead of a
  bare first-`<td>` assumption; filtering empty headers before comparing
  labeled ones) — confirms search/grouping/counts/remove-confirmation/
  banner-isolation all still behave exactly as before.
- `node --check` on `frontend/index.html`'s inline `<script>` block —
  syntactically valid.
- `grep` cross-check: every `getElementById(...)` call resolves to an
  `id=` that actually exists in the file (including IDs that only exist
  inside dynamically-rendered `innerHTML`, wired via functions called
  after that HTML is set); no duplicate function/element-id declarations.
- **Structural-only performance check (section 15)**: verified via the
  jsdom suite at 3, 6, and 12 displayed channels that request count
  scales exactly linearly and never duplicates/runs away. This sandboxed
  session has no real browser, so actual paint/scroll responsiveness at
  these counts was **not** visually confirmed here — live DEV round-trip
  API timing was measured instead as the closest available evidence; see
  this task's final report for the exact numbers, and its own explicit
  statement that no claim is made about 50/100 simultaneous channels
  (not built for, requested, or tested).

## What was verified (prior pass — crosshair visual UAT follow-up)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `adc9439` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend: the same 19-check scripted `jsdom` test, updated in place
  and re-passing** for the new values — `spikethickness: 0.35`,
  `spikedash: "3px,2px"`, Light `--spike-color: rgba(60,68,87,0.6)`, Dark
  `--spike-color: rgba(168,178,199,0.6)`, `spikesnap: "data"` unchanged,
  both axes' spikes enabled, theme switch still triggers **zero**
  additional `fetch` calls, Reset Time View regression check still green.
- `node --check` on `frontend/waveform-prototype.html`'s inline
  `<script>` block — syntactically valid.
- Manual `grep` confirmed the new `spikethickness`/`spikedash` values are
  only present in the intended two places (xaxis/yaxis) and no stale
  `0.5`/`"dash"` values remain in the live config (only historical
  comment text, left as accurate history, not live code).
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report, and the honest limitation note on the
  dash-length/thickness claims (DECISIONS.md's DEC-023 Update note).

## What was verified (prior pass — Light/Dark theme & crosshair refinement)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `2349972` (independent `git fetch` via the
  established HTTPS-URL workaround), working tree clean, before this pass
  began.
- **Backend regression: 278 tests, unmodified, all still pass** (fresh
  venv run) — zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend: 19 new scripted `jsdom` checks, all passing** — theme
  default/selection/persistence/cross-tab-sync/toggle-control behavior on
  both `index.html` and `waveform-prototype.html`; Plotly crosshair
  (dashed/thinner/reduced-alpha/sample-snapped/hover-values) at chart
  init; theme switch updates Plotly via `relayout`/`restyle` with **zero**
  additional `fetch` calls; Reset Time View still triggers exactly one
  fresh waveform request (regression check).
- `node --check` on every inline `<script>` block in both HTML files, and
  on `frontend/theme.js` directly — all syntactically valid.
- Manual `grep` sweep for `rgba(\|#[0-9a-fA-F]{3,6}` in both HTML files
  confirmed only the intentional, theme-invariant `color: #fff` (white
  text on solid accent/danger buttons, same in both themes) remains
  outside the shared token files.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked via `curl`/static-asset
  inspection instead, and the honest caveat on the `spikethickness: 0.5`
  visual claim (DECISIONS.md DEC-023's own Impact section).

## What was verified (prior pass — Phase 2C discovery/design)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` at commit `704df11` (independent `git fetch` via the
  established HTTPS-URL workaround — the configured SSH `origin` remote is
  not authenticated in this sandbox), working tree clean, before this pass
  began.
- **`powerwave` git state**: confirmed via a spawned Explore subagent —
  `/Volumes/externalDrive/code-gym/powerwave`, remote
  `https://github.com/myza81/powerwave.git`, commit `3156392` (same commit
  every prior investigation this project has used — no drift).
- **Detego**: only publicly available marketing/docs pages
  (`detego.app`, `detego.app/docs/guide/waveform-viewer`) were fetched via
  `WebFetch`/`WebSearch` — no authenticated app, no proprietary code/assets
  were accessed or inspected, per this task's own instruction and the
  standing `PRODUCT_REFERENCES.md` governance.
- **This is a documentation-only pass** — no backend or frontend code was
  touched; nothing to run a test suite against. `git diff --stat` after all
  edits shows only the four project-memory markdown files.
- `git diff --check` — no whitespace errors.

## What was verified (prior pass — Phase 2B renderer closure)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- **Backend regression: 278 tests, unmodified, all still pass** — zero
  backend files in the diff (`git diff --stat -- backend/` empty).
- **Frontend: 31 scripted `jsdom` checks, all passing** — 3 new
  static-markup checks confirming no renderer-selector UI, no
  "renderer comparison"/"Phase 2B UAT" wording, and no uPlot code
  references remain anywhere in the shipped file; the rest cover
  Plotly-only initialization, the restyled crosshair configuration
  (dashed/thin/reduced-opacity/still-sample-snapped/both-axes), zoom,
  the native-autoscale-refetch fix, Reset Time View, both stale-request
  protection layers, and safe-failure error handling.
- **Repository-wide search**: `grep -ril "uplot"` (excluding `.git` and
  `docs/`, which intentionally retains historical record) returns only
  `frontend/waveform-prototype.html` (two historical/rationale comments,
  zero code references) and `frontend/vendor/README.md` (its own
  intentional "History" note). `find -iname "*uplot*"` confirms zero
  files with that name remain anywhere in the tree.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked via `curl`/static-asset
  inspection instead.

## What was verified (prior pass — Phase 2B Plotly refinement)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- **Backend regression: 278 tests, unmodified, all still pass** — zero
  backend files in the diff (`git diff --stat -- backend/` empty).
- **Frontend: 24 scripted `jsdom` checks, all passing** — 10 regression
  checks confirming every existing Phase 2B behaviour (initial request,
  zoom, both stale-protection layers, Reset Time View, renderer switching
  including uPlot remaining functional, adapter cleanup, error banner) is
  unchanged after this pass's edits, plus 5 new checks: the Plotly
  layout's spike/crosshair configuration is present with the exact
  documented settings, and — the most important new test — a simulated
  native Autoscale/Reset-axes relayout event now correctly triggers a
  real full-record re-fetch, proving the toolbar-lag investigation's bug
  fix.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — visual crosshair appearance
  and felt interaction smoothness are exactly what the owner's own final
  UAT session is for; see "Live DEV verification" in this task's final
  report for what was checked via `curl`/static-asset inspection instead.

## What was verified (prior pass — Phase 2B renderer UAT prototype)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- **Backend regression: 278 tests, unmodified, all still pass** —
  confirmed zero backend files in the diff (`git diff --stat -- backend/`
  empty).
- **Frontend: 25 scripted `jsdom` checks, all passing**, driving the
  actual shipped `waveform-prototype.html` (not a reimplementation)
  against stub `uPlot`/`Plotly` objects satisfying their real public
  APIs. Covers: initial full-record request shape; zoom → debounced
  narrower request; the stale-response scenario with the
  `AbortController` layer and the sequence-number fallback layer verified
  **independently** (a dedicated test isolates the sequence-number path
  by simulating an abort that doesn't reject the promise); Reset View;
  friendly error-banner wording; renderer switch issuing zero new
  requests and reusing already-fetched data; repeated renderer switching
  with matched init/destroy counts and no duplicate DOM nodes; and
  Plotly's own programmatic-relayout-after-Reset not looping into a
  second fetch.
- Vendored library integrity: exact byte sizes recorded (uPlot ≈ 52 KB
  combined JS+CSS; Plotly-cartesian ≈ 1.36 MB JS), versions/licenses
  recorded in `frontend/vendor/README.md`.
- No real-browser/visual verification was performed in this sandboxed
  session (no headless browser available) — see "Live DEV verification"
  in this task's final report for what was checked via `curl`/static
  asset inspection instead, and note clearly that interactive/visual
  correctness is the explicit purpose of the owner's own upcoming UAT
  session, not something already claimed done here.

## What was verified (prior pass — Phase 2A implementation)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- All 227 previously-passing backend tests still pass **unmodified in
  behaviour** — only `tests/test_workspace_registry.py`'s fixture helper
  needed a mechanical update (build `ActiveSource` instead of a bare
  `SourceMetadata`); every assertion it made before still holds.
  `tests/test_comtrade_parity.py`/`test_comtrade_provider.py` (parser
  correctness) were touched by nothing this pass and still pass.
- **278 total backend tests pass** — see "What was most recently done"
  above for the breakdown; re-verified from a clean venv
  (`pip install -r requirements-dev.txt && pytest`).
- Performance/memory measured via a one-off, uncommitted benchmark script
  against synthetic (non-confidential) data at four scales up to 2M
  samples — see the Phase 2A Implementation Record's tables. Not measured:
  an actual ~100 MB real COMTRADE file through the real parser (still
  `[OPEN]`, now partially informed by a precisely measured
  file-to-parsed-memory expansion ratio instead of a pure guess).
- Manually confirmed (via `app.openapi()`'s paths, not raw `app.routes` —
  FastAPI's internal route representation makes the latter show an opaque
  wrapper object, a known quirk from Phase 1's own final report) that all
  6 endpoints register correctly, including the new
  `GET .../sources/{source_id}/waveform`.

## What was verified (prior pass — Phase 2 design)

- `oruxa_powerwave` git state: local `main` confirmed identical to
  `origin/main` (independent `git fetch`), working tree clean, before and
  after this pass.
- `powerwave` git state: confirmed unchanged since the original discovery
  audit (`HEAD` still `31563920...` / short form `3156392`), so the
  original [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) findings were
  still applicable — but re-verified live anyway (not assumed), per the
  task's explicit instruction and the project's own "code over docs"
  source-of-truth rule.
- **All 14 specific `powerwave` waveform-architecture claims this pass set
  out to check were independently re-confirmed against live code** (file
  path + line number evidence, not just re-reading the prior discovery
  doc) — see [MIGRATION_PLAN.md §2](MIGRATION_PLAN.md#phase-2--waveform-workspace-discovery-and-design-2026-08-14)
  for the full findings. One correction to the prior discovery note:
  `_infer_panel_for_channel()` is a module-level function, not a method.
  One materially new finding beyond the prior discovery pass's scope: the
  decimation algorithm itself (`t_clip[::stride]`) is confirmed plain
  nth-point stride sampling with no peak preservation, and digital
  transitions are decimated *before* transition-extraction runs, meaning a
  narrow pulse can be dropped before `extract_transitions()` ever sees it
  — a genuine, previously uncited engineering-integrity risk in the
  current desktop app, carried into the design as an explicit "do not
  repeat this" principle.
- This was a discovery/design-only task — **no automated test suite
  applies** (no code was written). No backend/frontend changes exist to
  regression-test.

## What was verified (prior pass — workspace-reset fix)

- **227 backend tests pass** (`cd backend && pytest`), up from 215 — new:
  `test_workspaces_api.py` (single- and multi-source whole-workspace
  DELETE, cross-workspace isolation, empty/unknown-workspace idempotency,
  blank-id rejection, delete-then-reupload-into-the-same-id), 4 new
  `WorkspaceRegistry.remove_workspace()` unit tests in
  `test_workspace_registry.py`, and one `Remove`-regression test in
  `test_sources_api.py` confirming a single-source delete leaves sibling
  sources in the same workspace intact. No COMTRADE parser/provider/
  classification code was touched this pass.
- **Frontend logic verified against the actual shipped code**, not a
  reimplementation: a one-off `jsdom` script (not committed, same
  established approach as the prior UAT refinement pass) drove the *real*
  upload code path (mocked-`fetch` form submission — not direct variable
  poking, since top-level `let`/`const` in a classic script are not
  reachable via `window.*`, matching real browsers) and exercised 36
  checks across 7 scenarios: confirmation shown only for a non-empty
  workspace and only before any DELETE; Cancel issues zero DELETE calls
  and preserves the old workspace id/source list/banner; Confirm issues
  exactly one workspace-level DELETE against the *old* id, then mints a
  new id and clears source list/channel panel/banner; a failed DELETE
  preserves everything and shows a visible error; an empty workspace
  skips confirmation but still resets; `Remove` still issues only a
  source-level DELETE and its Cancel/banner/other-source-preserved
  behaviour is unchanged; removing an unrelated source still leaves a
  still-valid banner alone. All 36 passed.
- No production code outside the intended scope was touched — see "Files
  changed" below.

## What was verified (prior pass — UAT refinement)

- **215 backend tests pass**, up from 168 — new:
  `test_channel_classification.py` (every recognized unit/parameter_type,
  priority ordering, explicit ambiguous-channel-stays-Undefined coverage)
  plus a new API assertion that `engineering_type` appears correctly in
  live channel responses. No provider/parser code was touched that pass —
  COMTRADE parity is structurally unaffected (confirmed by the unmodified
  parity tests still passing).
- **Frontend logic verified against the actual shipped code**, not a
  reimplementation: a one-off Node script (not committed — no frontend
  test framework existed before this task, and none was introduced, per
  the task's explicit allowance to document manual/scripted verification
  instead) loaded `frontend/index.html`'s real inline `<script>` into a
  `jsdom`-backed DOM and exercised: grouping/counts/default-expansion/
  column-removal against an 80-analog/282-digital dataset matching UAT's
  own numbers; search (case-insensitive, cross-analog/digital,
  auto-expand-on-match, no-match empty state, clear-restores-default);
  the full remove-confirmation flow, explicitly confirming **Cancel issues
  zero DELETE requests**; the stale-banner fix; and — the task's explicit
  forward-compat check — that removing a *different* source never clears
  an unrelated still-valid banner. All passed. (One bug was caught and
  fixed in the *test script itself* during this process — an attempt to
  read a `let`-scoped JS variable via `window.X` from outside the script,
  which correctly doesn't work in real browsers either; the fix was to
  drive the real upload/removal code paths instead of poking at internal
  state, which is also the more faithful test.)
- **Live guardrail regression check** against a local `uvicorn` server:
  missing-companion-file (422), wrong-extension (400
  `unsupported_file_type`), and successful upload-then-delete-then-404 all
  behave exactly as before; the new `engineering_type` field appears
  correctly (`VA`/`VB` → `Voltage`, `IA` → `Current` for the synthetic
  fixture).

## What files were changed this session (Phase 3B-UAT1 recording row divider alignment)

Modified only: `frontend/index.html` (moved `.recording-actions`'s flex
layout from the Actions `<td>` itself onto a new inner `<div>`, plus one
explanatory CSS comment). No new files. **No `backend/` file, no
CI/deployment workflow file was touched.** Project memory:
`MIGRATION_PLAN.md`, `CURRENT_STATE.md`, `HANDOFF.md` updated;
`DECISIONS.md` intentionally NOT touched (a cosmetic correction within
the already-decided DEC-032 Recordings page, not a new/revised
decision).

## What files were changed in the prior session (Phase 3B recordings page and upload workflow)

Modified: `frontend/index.html` (the bulk of this phase — new
Recordings page markup/CSS/JS, new upload modal, Main Sidebar Menu
rename + new item, removed the old always-visible sidebar upload form,
`shell.currentPage`/`shellSetCurrentPage()`, `RECORDING_FORMATS`,
`fetchSourcesList()`/`refreshAllSourceViews()`/`renderRecordingsTable()`
and friends, two new `[hidden]` CSS override rules);
`backend/app/schemas/source.py` (additive `duration_seconds`/
`sample_count` fields on `SourceSummaryOut`);
`backend/tests/test_sources_api.py` (new/extended coverage for those
fields). No new files. No CI/deployment workflow file. Project memory:
`DECISIONS.md` (new DEC-032 — this IS a meaningful product-navigation
change, per this task's own explicit instruction), `MIGRATION_PLAN.md`,
`CURRENT_STATE.md`, `HANDOFF.md` all updated.

## What files were changed in the prior session (Phase 3A-UAT4 channel filename containment)

Modified only: `frontend/index.html` (new `.detail-header-info` class
with `min-width: 0; max-width: 100%;`, applied to the previously-unnamed
flex-item wrapper in `renderChannels()`'s markup; `.detail-header
h3`/`.meta` gained explicit `white-space: normal; max-width: 100%;`
alongside their existing `overflow-wrap: anywhere`). No new files. **No
`backend/` file, no CI/deployment workflow file was touched.** Project
memory: `MIGRATION_PLAN.md`, `CURRENT_STATE.md`, `HANDOFF.md` updated;
`DECISIONS.md` intentionally NOT touched (a targeted correction within
the already-decided DEC-031 shell architecture and its own Phase
3A-UAT3 containment pass, not a new/revised decision).

## What files were changed in the prior session (Phase 3A-UAT3 targeted overflow and containment fixes)

Modified only: `frontend/index.html` (CSS containment rules for Findings
A/B/C/D/G; `shellSetActiveView()` resize call for Finding E;
`shellSyncSidebarWidthForBreakpoint()`/`matchMedia` listener for Finding
F; `.group-chip-label` markup wrap for Finding D). No new files. **No
`backend/` file, no CI/deployment workflow file was touched.** Project
memory: `MIGRATION_PLAN.md`, `CURRENT_STATE.md`, `HANDOFF.md` updated;
`DECISIONS.md` intentionally NOT touched (targeted corrections within
the already-decided DEC-031 shell architecture, not a new/revised
decision).

## What files were changed in the prior session (Phase 3A-UAT2 remove duplicate header theme control)

Modified only: `frontend/index.html` (removed the `<div id="themeToggle">`
element from the Global Header and its `mountThemeToggle()` Init call;
corrected a stale code comment on the Main Sidebar Menu's Settings
handler). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change (both
still used unmodified by `waveform-prototype.html`), no CI/deployment
workflow file was touched.** Project memory: `MIGRATION_PLAN.md`,
`CURRENT_STATE.md`, `HANDOFF.md` updated; `DECISIONS.md` intentionally
NOT touched (no new/corrected architectural decision this pass).

## What files were changed in the prior session (Phase 3A-UAT1 responsive waveform width reflow)

Modified only: `frontend/index.html` (`shellCreateHorizontalSplit()`
rewritten with rAF-coalesced resize scheduling; new
`wwResizeAllVisiblePlots()` and `wwScheduleResizeAllVisiblePlots()`;
Init wiring adds `onResize: wwResizeAllVisiblePlots` to the Workspace
Sidebar split config, a `transitionend` listener on `#mainSidebarMenu`,
and a `window.resize` listener; `.ww-chart-wrap` CSS gained `overflow:
hidden`). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 3A application shell redesign foundation)

Modified only: `frontend/index.html` (full CSS restructuring —
`#globalHeader`, `#appBody`, `#mainSidebarMenu`, `.shell-nav-*`,
`#workArea`, `#workspaceRow`, `#workspaceSidebar`,
`.shell-split-handle`, `#mainWorkspace`, `#activeViewArea`,
`.shell-view-placeholder`, `#bottomStatusBar`, `.shell-sidebar-backdrop`,
plus two responsive media queries; removed the old `main`/`footer`/
`.ww-header` page-grid CSS). HTML restructured: existing Import/
Sources/Channels panels moved into `#workspaceSidebar`; the existing
waveform workspace moved into `#activeViewArea`'s new `#viewWaveform`
container; new `#viewTable`/`#viewSplit` placeholders added; every
existing element ID preserved. New JS: `shell` state object,
`shellCreateHorizontalSplit()`, `shellSetMainSidebarExpanded()`,
`shellSetActiveView()`, `shellSetSidebarDrawerOpen()`,
`shellOpenImport()`, `shellUpdateStatusBar()`,
`shellUpdateStatusBarChannelCount()`; small hooks added into
`renderChannels()` and the three existing `ww.displayed`-count-changing
call sites (`wwAddSelectedChannels`/`wwRemoveChannel`/
`wwClearWorkspace`). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C4B compact sticky time-axis layout correction)

Modified only: `frontend/index.html` (`#wwStickyRulerTitle`/
`#wwStickyRulerContext` DOM elements and their `.ww-sticky-ruler-title`/
`.ww-sticky-ruler-context` CSS deleted entirely; `.ww-sticky-ruler`
padding simplified, `.ww-sticky-ruler-chart` height reduced 46px→40px;
`wwSyncStickyRuler()` rewritten to set `xaxis.title` on the ruler's own
Plotly layout/relayout calls instead of writing to a DOM title element,
with margin changed to `{t:2, b:34}`; Absolute mode's title wording
changed to "Record Time" (capital T); `wwUpdateTimeModeContext()`
simplified to only drive the toolbar's own label, no longer touching a
ruler-side date element). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C4A sticky time-axis title placement and unit label)

Modified only: `frontend/index.html` (`.ww-sticky-ruler-title` CSS
(new) + `.ww-sticky-ruler-context` CSS updated to centered/dimmer;
`#wwStickyRulerTitle` markup (new, before the context line and chart);
new `wwStickyRulerElapsedUnit(spanSeconds)` helper; `wwSyncStickyRuler()`
rewritten to compute/apply a mode-aware title and (Elapsed-only) rescaled
tick range/format; `wwUpdateTimeModeContext()` updated so the ruler's own
context line shows only the date, while the toolbar's copy keeps its
full wording unchanged). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C4 sticky shared waveform time axis)

Modified only: `frontend/index.html` (`.ww-sticky-ruler`/
`.ww-sticky-ruler-context`/`.ww-sticky-ruler-chart` CSS; `#wwStickyRuler`/
`#wwStickyRulerContext`/`#wwStickyRulerChart` markup as a sibling of
`#wwPanels`; new `WW_PANEL_MARGIN` shared constant, also wired into
`wwBuildLayout()`'s own margin (replacing its previous inline literal);
`ww.rulerReady` state; new `wwSyncStickyRuler()`;
`wwUpdateTimeModeContext()` extended to also drive
`#wwStickyRulerContext`; `wwApplyTimeAxisChrome()` changed to suppress
ticks/title on every Separate lane, not just the non-bottom ones;
`wwSyncStickyRuler()` called from `wwApplyAndFetchViewport`,
`wwSetTimeMode`, `wwAddSelectedChannels`, `wwRemoveChannel`,
`wwClearWorkspace`; `wwApplyTheme()` extended to re-color the ruler),
`docs/project-memory/{MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (this
work). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C3 COMTRADE time-axis modes)

Modified only: `frontend/index.html` (toolbar HTML for the Absolute/
Elapsed toggle + date-context label; `channelCheckboxHtml`/
`renderAnalogGroup`/`renderChannelTable` thread `timebase` through so
each channel carries `recordingStartTime`/`timingReference`;
`WW_TIME_MODES`/`ww.timeMode` state; new helpers
`wwParseNaiveTimestamp`, `wwFormatPlotlyDateString`,
`wwTimeModesForChannel`, `wwAvailableTimeModes`,
`wwWorkspaceRecordingStartMs`, `wwElapsedToPlotlyX`,
`wwPlotlyXToElapsed`, `wwTimeAxisTickFormat`, `wwTimeAxisTitle`,
`wwUpdateTimeModeContext`, `wwUpdateTimeModeControlAvailability`,
`wwSetTimeMode`; `wwBuildTrace`/`wwBuildLayout`/`wwLoadChannelRange`/
`wwWirePanelRelayout`/`wwApplyAndFetchViewport` made mode-aware;
`wwUpdateBottomLaneAxis()` renamed to `wwApplyTimeAxisChrome()` (same
Separate-only guard, now mode-aware title); toolbar listeners wired),
`docs/project-memory/{MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (this
work). No new files. **No `backend/` file, no
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no CI/
deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C2A panel resize responsiveness)

Modified only: `frontend/index.html` (`wwSetPanelHeight()` split into
`wwSetPanelHeightImmediate()` — the cheap DOM-only write, now called on
every raw `pointermove` — and `wwResizePanelPlot()` — the
`Plotly.Plots.resize()` call only, still `requestAnimationFrame`-
coalesced; `wwSetPanelHeight()` itself retained as their combination,
used only for the authoritative final write on `pointerup`/
`pointercancel`; `wwWireResizeHandle()`'s `onPointerMove`/`flush` updated
accordingly (the old `pendingHeight` variable is gone — the DOM write no
longer needs to wait for a scheduled frame); module header comments
updated), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,
HANDOFF}.md` (an "Update" note appended to DEC-028, no new decision
entry; this work). No new files. **No `frontend/waveform-prototype.html`/
`theme.css`/`theme.js` change, no `backend/` file, no CI/deployment
workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C2 adjustable waveform panel heights)

Modified only: `frontend/index.html` (`WW_MIN_PANEL_HEIGHT`/
`WW_MAX_PANEL_HEIGHT`/`WW_DEFAULT_PANEL_HEIGHT` constants; a
`ww.panelHeights` Map; `wwDefaultHeightForCurrentMode()`/
`wwHeightForGroupKey()`/`wwClampPanelHeight()` helpers; `panel.height`
added to the panel object (`wwCreatePanelObject`); `wwSetPanelHeight()`
and `wwWireResizeHandle()` (Pointer Events + Pointer Capture +
`requestAnimationFrame` coalescing); a `.ww-resize-handle` element added
to every panel's DOM (`wwCreatePanelDom`) with its own theme-token CSS,
unscoped to any one layout mode; `wwClearWorkspace()` extended to reset
`ww.panelHeights`; the module header comment updated), `docs/project-
memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (DEC-028
added; this work). No new files. **No `frontend/waveform-prototype.html`/
`theme.css`/`theme.js` change, no `backend/` file, no CI/deployment
workflow file was touched.**

## What files were changed in the prior session (Phase 2C-C1 custom analog channel groups)

Modified only: `frontend/index.html` (a `ww.customGroups`/
`ww.customGroupSeq` state pair; a `wwCustomGroupFor()` helper; a "custom"
branch added to `wwPanelGroupKeyFor`/`wwPanelLabelFor`; a third
`layoutModeCustomBtn` toolbar button; a new `editChannelGroupsBtn`
control and `wwUpdateEditGroupsButtonVisibility()`; the group editor
modal's HTML/CSS (`groupEditorOverlay`, `.group-editor-box`, `.group-
card`, `.chip-list`, `.group-chip`, etc.); `groupEditorState` and
`wwOpenGroupEditor`/`wwCloseGroupEditor`/`wwRenderGroupEditor`/
`wwGroupEditorAddGroup`/`wwGroupEditorRemoveGroup`/
`wwGroupEditorAssignChannel`/`wwGroupEditorUnassignChannel`/
`wwGroupEditorRenameGroup`/`wwApplyGroupEditor`; `wwClearWorkspace()`
extended to reset `ww.customGroups`; `wwSetLayoutMode()` extended to
accept "custom"; the module header comment updated), `docs/project-
memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (DEC-027
added; this work). Also committed separately this session (before this
task's own work began, preserving pre-existing uncommitted changes found
in the working tree per the project's git-safety rule): `d902dc5`,
two small direct manual CSS tweaks to the Phase 2C-B3A overlay tag (see
"Also note" above). No new files. **No
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no
`backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-B3A overlay right-side lane labels)

Modified only: `frontend/index.html` (removed the `#wwPanels.ww-panels-
unified .ww-panel` grid-template-columns split; `.ww-panel` is now
`position: relative` in unified mode; `.ww-legend` is now `position:
absolute` — pinned `right: 14px`, `top: 50%`/`transform: translateY(-50%)`,
`z-index: 2`, `pointer-events: none` (re-enabled on `.ww-legend-item` via
`pointer-events: auto`); `.ww-chart-wrap` no longer has a `grid-column`;
the module header comment updated), `docs/project-memory/{DECISIONS,
MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (a further "Update" note
appended to DEC-026, no new decision entry; this work). No new files. **No
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no
`backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-B3 right-side compact lane labels)

Modified only: `frontend/index.html` (grid-column order swapped in the
`#wwPanels.ww-panels-unified .ww-panel` CSS so the chart is column 1 and
the label is column 2 with `justify-self: end`; `.ww-legend-item`
restyled as a compact pill; a new `.ww-legend-label` rule for ellipsis
truncation; `wwRenderLegend()` now wraps each channel's text in a
`<span class="ww-legend-label">`; the module header comment updated),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(an "Update" note appended to DEC-026, no new decision entry; this work).
No new files. **No `frontend/waveform-prototype.html`/`theme.css`/
`theme.js` change, no `backend/` file, no CI/deployment workflow file was
touched.**

## What files were changed in the prior session (Phase 2C-B2 unified analog canvas layout)

Modified only: `frontend/index.html` (new CSS rules scoped under
`#wwPanels.ww-panels-unified` for the unified-canvas presentation; a
`wwUpdateBottomLaneAxis()` function; the `ww-panels-unified` class toggle
in `wwSetLayoutMode()`; calls to `wwUpdateBottomLaneAxis()` wired into
`wwAddSelectedChannels()`, `wwRemoveChannel()`, and `wwRebuildLayout()`;
the module header comment updated), `docs/project-memory/{DECISIONS,
MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` (DEC-026 added; this work). No
new files. **No `frontend/waveform-prototype.html`/`theme.css`/`theme.js`
change, no `backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-B1 Grouped / Separate layout)

Modified only: `frontend/index.html` (a `ww.layoutMode` state field;
`wwPanelGroupKeyFor`/`wwPanelLabelFor` helpers; `wwRebuildLayout()`;
`wwSetLayoutMode()`; a small Grouped/Separate toolbar toggle;
`channelEntry.engineeringType` retained on add; the module header comment
updated), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,
HANDOFF}.md` (DEC-025 added; this work). No new files. **No
`frontend/waveform-prototype.html`/`theme.css`/`theme.js` change, no
`backend/` file, no CI/deployment workflow file was touched.**

## What files were changed in the prior session (Phase 2C-A synchronized multi-channel waveform display)

Modified only: `frontend/index.html` (checkbox selection + Add/Clear
selected controls on the existing analog channel table; a new full-width
"Waveform Workspace" section: central toolbar, panel container, empty
state; the whole `ww*`-prefixed panel/viewport/toolbar/removal/theme JS
module), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,
HANDOFF}.md` (DEC-024 added; this work). No new files. **No
`frontend/waveform-prototype.html` change, no `backend/` file, no
CI/deployment workflow file was touched.**

## What files were changed in the prior session (crosshair visual UAT follow-up)

Modified only: `frontend/theme.css` (`--spike-color` values in both
themes), `frontend/waveform-prototype.html` (`spikethickness`/`spikedash`
values + updated code comments — no other logic touched),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(an "Update" note appended to DEC-023, not a new decision; this work). No
new files. **No `frontend/index.html` change, no `backend/` file, no
CI/deployment workflow file was touched.**

## What files were changed in the prior session (Light/Dark theme & crosshair refinement)

New: `frontend/theme.css`, `frontend/theme.js`.

Modified: `frontend/index.html` (theme link/script, header toggle,
`:root` block removed, `rgba(...)` literals replaced with tokens),
`frontend/waveform-prototype.html` (same, plus `themeColors()`,
`PlotlyRenderer.applyTheme()`, crosshair `spikethickness`/`spikecolor`
refinement, header toggle), `frontend/Dockerfile` (copies the two new
files), `frontend/.dockerignore` (comment accuracy only),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(DEC-023 added; this work). **No `backend/` file, no CI/deployment
workflow file was touched.**

## What files were changed in the prior session (Phase 2C discovery/design)

Modified only: `docs/project-memory/MIGRATION_PLAN.md` (new "Phase 2C —
Flexible Multi-Channel Waveform Workspace: Discovery and Design" section,
inserted between the Phase 2B Renderer Closure Record and the Phase 0
section), `docs/project-memory/CURRENT_STATE.md` (Development-phase
paragraph, Current-approved-focus paragraph, Next-approved-activity
paragraph, Documentation bullet, Major-currently-available-components
bullet), `docs/project-memory/HANDOFF.md` (this document). **No entry was
added to `DECISIONS.md`** — nothing in this pass rose to an approved
`[DECISION]`, per the task's own explicit instruction. **No `backend/` file,
no `frontend/` file, no CI/deployment workflow file was touched** — this was
a documentation-only, design/discovery pass.

## What files were changed in the prior session (Phase 2B renderer closure)

Modified: `frontend/waveform-prototype.html` (uPlot removal, crosshair
restyle, page-text simplification), `frontend/Dockerfile` (comment
accuracy only), `frontend/vendor/README.md` (uPlot entry removed, History
section added), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(DEC-022 added; this work).

Deleted: `frontend/vendor/uplot/uPlot.iife.min.js`,
`frontend/vendor/uplot/uPlot.min.css`, `frontend/vendor/uplot/LICENSE`.

No new files, no `frontend/index.html` change, no `backend/` file, and no
CI/deployment workflow file touched.

## What files were changed in the prior session (Phase 2B Plotly refinement)

Modified only: `frontend/waveform-prototype.html` (Plotly native
spike/crosshair config; relayout-handler autorange fix; debounce 200ms →
120ms; "Reset View" → "Reset Time View" label/wording; Phase 2C
extension-point and semantic-distinction comments — no HTML structure
change), `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(DEC-021 added; this work).

No new files, no `frontend/vendor/*` change, no `frontend/index.html`
change, no `backend/` file, and no CI/deployment workflow file touched.

## What files were changed in the prior session (Phase 2B renderer UAT prototype)

New: `frontend/waveform-prototype.html`, `frontend/vendor/README.md`,
`frontend/vendor/uplot/{uPlot.iife.min.js,uPlot.min.css,LICENSE}`,
`frontend/vendor/plotly/{plotly-cartesian.min.js,LICENSE}`.

Modified: `frontend/index.html` (one new "Waveform (UAT)" link per analog
channel row; `renderChannelTable`/`renderAnalogGroup` extended with a
backward-compatible optional action-column parameter — digital channels'
call site unchanged), `frontend/Dockerfile` (serves the new page +
vendored assets), `frontend/.dockerignore` (comment only, no pattern
changes), `docs/project-memory/{MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(this work).

**`DECISIONS.md` was NOT modified** — no plotting-library winner was
chosen (explicitly out of scope; `[DECISION MODE: UAT]`), and no other
new non-UI technical decision was made this pass that wasn't already
covered by DEC-019/DEC-020.

No `backend/`, `docker-entrypoint.d/`, or CI/deployment workflow file was
touched.

## What files were changed in the prior session (Phase 2A implementation)

New: `backend/app/domain/waveform_reduction.py`,
`backend/app/services/waveform_service.py`,
`backend/app/schemas/waveform.py`,
`backend/tests/test_waveform_reduction.py`,
`backend/tests/test_waveform_service.py`,
`backend/tests/test_waveform_api.py`.

Modified: `backend/app/domain/source.py` (new `ActiveSource`),
`backend/app/domain/__init__.py`,
`backend/app/domain/disturbance_record.py` (docstring correction — see
below),
`backend/app/services/workspace_registry.py` (stored-value type widened
from `SourceMetadata` to `ActiveSource`; keying/locking/cleanup logic
itself unchanged; docstrings corrected),
`backend/app/services/import_service.py` (builds/stores `ActiveSource`
instead of discarding the parsed record; docstring corrected),
`backend/app/services/errors.py` (3 new error classes, shared base class
docstring broadened),
`backend/app/api/v1/sources.py` (new waveform endpoint; existing
endpoints' internals updated to unwrap `.metadata` — their
request/response contracts are unchanged),
`backend/tests/test_workspace_registry.py` (fixture helper builds
`ActiveSource`),
`docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
(this work — DEC-019 added).

**Stale-docstring corrections, not silent rewrites** (per the project's
own conflict-resolution rule): `app/domain/disturbance_record.py` and
`app/services/import_service.py`'s module docstrings both used to state
the `DisturbanceRecord` is discarded after upload — both now explain the
Phase 2A change and point to DEC-019, rather than leaving the old,
now-false claim in place uncorrected.

No `backend/app/providers/*`, `backend/app/main.py`, `frontend/*`, or CI/
deployment file was touched.

## What files were changed in the prior session (Phase 2 design)

Modified (documentation only — no application code):
- `docs/project-memory/MIGRATION_PLAN.md` — new "Phase 2 — Waveform
  Workspace Discovery and Design" section (~1,400 lines): verified
  `powerwave` findings, behavior-vs-implementation table, data-delivery
  architecture comparison (Options A-D), transfer-format comparison,
  frontend/backend boundary confirmation, plotting-library candidates,
  Phase 2 scope + channel-selection UX, panel model, analog scaling,
  time-axis handling, full-resolution zoom principle, peak-preservation
  recommendation, digital-signal preservation, browser/backend memory
  models, source-lifecycle extension proposal, TTL reassessment, session
  concurrency, API proposal, caching strategy, initial-load UX, loading
  states, error handling, performance targets, engineering-correctness
  test design, benchmark plan, and the full UAT/technical decision lists.
- `docs/project-memory/CURRENT_STATE.md` — recorded Phase 1's final owner
  UAT pass as complete; recorded that Phase 2 is in design-only stage with
  nothing implemented.
- `docs/project-memory/HANDOFF.md` — this section.

**`DECISIONS.md` was deliberately NOT modified** — no new item in the
Phase 2 design proposal has been owner-approved; recording any of it there
would misrepresent a proposal as a decision, which this task's own
instructions explicitly prohibited.

No `backend/` or `frontend/` file was touched.

## What files were changed in the prior session (workspace-reset fix)

New:
- `backend/app/api/v1/workspaces.py` — `DELETE /api/v1/workspaces/{workspace_id}`.
- `backend/tests/test_workspaces_api.py` — whole-workspace DELETE API tests.

Modified:
- `backend/app/services/workspace_registry.py` — added
  `remove_workspace(workspace_id)`.
- `backend/app/main.py` — mounts the new `workspaces_v1_router`.
- `backend/tests/test_workspace_registry.py` — added `remove_workspace()`
  unit tests.
- `backend/tests/test_sources_api.py` — added the `Remove`-regression test
  (sibling sources in the same workspace survive a single-source delete).
- `frontend/index.html` — `startNewWorkspace()` split into a confirmation
  gate (`requestNewWorkspaceConfirm`) and the actual ordered reset
  (`resetToNewWorkspace`: DELETE old workspace → only on success, rotate
  id and clear UI state); new confirmation dialog
  (`#newWorkspaceConfirmOverlay`) separate from `Remove`'s; new error
  element (`#workspaceResetError`) for cleanup failures.
- `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md`
  — this work (DEC-018 added).

No COMTRADE parser/provider/classification/config/storage file was
touched.

## Files changed in the prior session (UAT refinement pass)

New:
- `backend/app/domain/channel_classification.py`
- `backend/tests/test_channel_classification.py`

Modified:
- `backend/app/domain/source.py` — `AnalogChannelSummary` gained
  `engineering_type: str`.
- `backend/app/domain/__init__.py` — exports the classifier.
- `backend/app/schemas/source.py` — `AnalogChannelOut` gained
  `engineering_type`.
- `backend/app/services/import_service.py` — calls the classifier when
  building each analog channel's summary.
- `frontend/index.html` — collapsible grouping, analog sub-grouping,
  search, Scale/Offset removed from the primary table, remove
  confirmation dialog, stale-banner fix (for `Remove` only, at the time).

## GitHub / deployment status

See "GitHub persistence" and "DEV deployment" in this task's final report
(delivered in-conversation) for the exact commit hash, push confirmation,
independent-fetch verification, GitHub Actions run, and live-endpoint
checks for this Phase 3B pass. **Production was not touched.**

## What remains unresolved

- `[OPEN]`, **direct vertical drag/reorder of panels and drag-to-overlay/
  group by direct lane dragging are still fully unimplemented and
  undecided** — `[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`,
  not `[DECISION]`. Neither this pass (Phase 2C-C2A, a performance
  refinement of already-shipped panel resize) nor the prior one touched
  this — it remains the owner's stated *possible* next direction, not
  started, not abandoned.
- `[OPEN]`, unchanged: Proportional Y scaling, mixed-unit panel handling,
  digital-channel display, shared crosshair — every one of these remains
  `[PROPOSAL]`/`[ANALYSIS]`/`[COMPARISON]`/`[NEEDS UAT]`.
- `[OPEN]` **Unchanged, still real**: abandoned-workspace cleanup still
  has no automatic expiry/TTL. `[DECISION MODE: COMPARISON]` — none of
  Phase 2C-A, Phase 2C-B1, Phase 2C-B2, Phase 2C-B3, Phase 2C-B3A, Phase
  2C-C1, Phase 2C-C2, or Phase 2C-C2A changes the backend memory-
  retention shape (still per-*source*, DEC-019), which raises (not
  resolves) the same urgency already flagged for every prior Phase 2C
  pass. See
  [MIGRATION_PLAN.md's Phase 2C §30](MIGRATION_PLAN.md#phase-2c--flexible-multi-channel-waveform-workspace-discovery-and-design-2026-08-15)
  and DEC-019's Impact section.
- `[OPEN]`, unchanged: digital waveform handling (still not built,
  explicitly the owner's own stated next area); the ~100 MB real-file
  memory ceiling (still not directly measured); and everything else
  already listed in
  [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers).
- `[OPEN]`, unchanged from Phase 2C-C2: keyboard resizing of panel
  heights was not implemented (documented accessibility limitation,
  untouched by this investigation pass).
- **Carried over from Phase 2C-A's own manual UAT, deliberately not
  addressed this pass**: a small amount of interaction latency, judged
  currently bearable; and vertical (Y-axis) zoom being less intuitive
  than the rest of the toolbar — both explicitly flagged for a **later**
  UX refinement pass, not this one.
- **New this pass — explicitly unverifiable in this sandbox**: whether
  the resize-responsiveness refinement genuinely *feels* smoother to a
  human hand, and whether any momentary divergence between the box's
  edge and the waveform's own rendered edge is visible/distracting during
  a fast drag. The decoupling mechanism was proven structurally (jsdom
  instrumentation with a simulated-cost Plotly mock); the felt result was
  not and cannot be confirmed here. This is the primary thing the next
  owner UAT should specifically compare against the pre-Phase-2C-C2A
  build.
- **Unchanged from Phase 2C-A/B1/B2/B3/B3A/C1/C2**: real-browser
  rendering responsiveness and actual tactile/visual quality generally
  were not confirmed in this sandboxed, no-real-browser session — see
  this task's final report for the structural/code-level evidence
  gathered instead.

## What should be done next

**Phase 3A-UAT1 (width-reflow) passed owner UAT. Phase 3A-UAT2, UAT3,
UAT4, and now Phase 3B are all still awaiting a live DEV review —
Phase 3A-UAT3's OWN manual UAT is what surfaced the filename bug UAT4
fixed, so that portion of UAT3 has already been exercised.** The next
step is for the **project owner** to review Phase 3A-UAT2 through Phase
3B together via live DEV UAT: confirm the Global Header reads cleanly
with no leftover gap; confirm Settings is reachable/functional in both
Main Sidebar Menu states; confirm Light/Dark still works app-wide;
narrow the Workspace Sidebar to 240px and confirm BOTH the channel table
(scrolls rather than breaks) AND the CFG/DAT filenames in the
source-detail section stay contained; check long source/channel names
if a real event with them is available; check Grouped and Custom mode
legend chips with long channel names; narrow the browser around the
~900px responsive threshold and confirm the Sidebar becomes a
reopenable drawer at a SAFE width; switch to the Table placeholder,
resize something, then switch back to Waveform and confirm it isn't
visually stale; confirm no panel/dialog/table/text visibly overflows
its own frame anywhere — and specifically for **Phase 3B**: does the
Recordings page read as simple/clear/engineering-focused (not
card-heavy); is the Main Sidebar Menu's Waveform/Recordings split
intuitive; is the recording table readable with real data; does the
Upload New modal feel clear (format selector, file fields, loading/
error/success states); does Open/Analyse correctly land back on
Waveform with the right source's channels available; does navigating
Waveform ⇆ Recordings genuinely preserve viewport/zoom/grouping/panel
heights/time mode as claimed. This is a large but still deliberately
scoped pass — no Table/Split/digital-channel/CSV/Excel work, no shell
restructuring beyond what's described above. If confirmed clean: no
further action needed, and the still-open Phase 3A dimension/spacing
feedback remains welcome whenever convenient. If anything looks off,
report back with the specific control/page/mode — do **not** assume the
outcome. Separately, the owner may choose to: (a) request further Phase
3A dimension/spacing refinements or Phase 3B UX refinements; (b)
authorize the drag/reorder/overlay/split work directly (still the
owner's own possible next direction, deliberately set aside across
thirteen passes now, not abandoned); (c) request the still-outstanding
Grouped/Custom axis-duplication cleanup (Phase 2C-C4's own section 16
gap, unchanged across four passes now); (d) authorize real Table/Split
view implementation (explicitly NOT authorized yet — the shell only
avoids blocking it); (e) authorize real CSV/Excel parsing (the upload
modal's provider model is structurally ready but no parser exists —
explicitly NOT authorized yet); or (f) move on to digital channels (the
owner's own explicitly stated next area, and this task's own explicit
instruction: do **not** begin digital-channel, Table/Split, or CSV/Excel
work without a separate signal). Separately, resolving the abandoned-
session TTL question and the ~100 MB real-file memory validation remain
recommended before broader/prolonged shared-DEV UAT, unchanged
conclusion from every prior Phase 2 pass — and now additionally relevant
given Phase 3B makes uploading noticeably easier to reach (Global Header
Import + Recordings' own Upload New), which may increase how often
sources actually get imported during a shared-DEV session.

## What must not be assumed

- **Do not assume `index.html` still has an always-visible "Import
  COMTRADE Event" form in the Workspace Sidebar** — as of Phase 3B it was
  removed (`#uploadForm`/`#cfgInput`/`#datInput`/`#uploadButton`/
  `#uploadStatus` all no longer exist). Upload now happens exclusively
  through `#uploadModalOverlay` (opened via `openUploadModal()`), driven
  by `RECORDING_FORMATS`. If you need to trigger an upload from a test or
  from other code, target the modal's dynamic file inputs
  (`#uploadModalFileFields input[data-file-key="cfg"|"dat"]`), not the
  old fixed IDs.
- **Do not assume `shell.activeView` (`"waveform"`|`"table"`|`"split"`)
  and `shell.currentPage` (`"waveform"`|`"recordings"`) are the same
  concept** — they are two independent toggles at different levels.
  `currentPage` controls which top-level PAGE is shown in Work Area
  (`#workspaceRow` vs `#pageRecordings`); `activeView` only matters
  WITHIN the Waveform page, selecting its own sub-view. Setting one does
  not imply anything about the other except where `shellSetCurrentPage`/
  the Main Sidebar Menu's own click handlers explicitly coordinate them
  (e.g. clicking "Waveform" sets both to `"waveform"`).
- **Do not assume `refreshSourceList()` alone keeps the Recordings page
  in sync** — it only re-renders the Workspace Sidebar's compact source
  list. Anything that actually changes the source set (upload, remove,
  workspace reset) must call `refreshAllSourceViews()` instead, which
  refreshes BOTH the Sidebar list and the Recordings table from one
  shared fetch (`fetchSourcesList()`). `selectSource()` still correctly
  calls the narrower `refreshSourceList()` on its own, since selecting an
  already-listed source doesn't change the source SET.
- **Do not assume every element with `.hidden = true`/`false` set via JS
  actually becomes invisible** — if that element (or a class it carries)
  has its OWN author CSS `display` property (e.g. `display: flex`), that
  author rule beats the UA stylesheet's default `[hidden] {display:
  none}` rule by ORIGIN alone, regardless of specificity or source
  order, silently making the `hidden` attribute a no-op. `#workspaceRow`,
  `#pageRecordings`, and `#bottomStatusBar .shell-status-item` all needed
  (and now have) explicit `[hidden] { display: none; }` override rules
  for exactly this reason — check for this whenever adding a NEW
  `.hidden` toggle to an element that already has its own `display`
  rule; jsdom-based tests cannot catch this class of bug (no real CSS
  layout engine), so it must be checked by direct CSS inspection.
- **Do not assume `.detail-header`'s station-name/filename child `<div>`
  is still unnamed/unstyled** — as of Phase 3A-UAT4 it has a real class,
  `.detail-header-info` (`min-width: 0; max-width: 100%;`). This is the
  ACTUAL root-cause containment fix for the Channels source-detail
  filename overflow; `overflow-wrap: anywhere` alone on the text elements
  (Phase 3A-UAT3's own Finding C fix) was NOT sufficient by itself,
  because the flex item wrapping them never had `min-width: 0`. If a
  similar filename/long-text overflow is ever reported elsewhere in a
  flex layout, check the PARENT flex item's `min-width` first, not just
  the text element's own `overflow-wrap` — a text-level fix alone can be
  silently ineffective if its containing flex item can't shrink.
- **Do not assume `jsdom` implements `window.matchMedia`** — it does not,
  at all. `shellSyncSidebarWidthForBreakpoint()` (Phase 3A-UAT3, Finding
  F) calls it unconditionally at Init, so any NEW scratch test script
  that runs `index.html`'s real inline script needs the same
  `window.matchMedia`/`window.__setInnerWidth(px)` polyfill already added
  to all 16 existing scripts — omitting it aborts the whole `<script>`
  tag partway through Init, the same failure class as the Phase 3A-UAT1
  `requestAnimationFrame` gap.
- **Do not assume `#shellSidebarToggleBtn`'s CSS is still ordered
  base-rule-after-media-query** — Phase 3A-UAT3 (Finding A) moved the
  base `display: none` rule to BEFORE its `@media (max-width: 900px)`
  override; if either rule is edited again, keep the base rule first —
  equal-specificity selectors resolve by source order, and the earlier
  ordering silently disabled the reopen button.
- **Do not assume the Workspace Sidebar's inline `style.width` always
  reflects the user's desktop preference** — as of Phase 3A-UAT3
  (Finding F), it is deliberately CLEARED while `window.matchMedia
  ("(max-width: 900px)")` matches (so the CSS drawer rule governs) and
  only reflects the real persisted width at desktop widths. Read
  `workspaceSidebarSplit.getWidth()` (or the `localStorage` key), not
  `style.width` directly, if you need the user's actual preference
  regardless of current viewport.
- **Do not assume `.ww-legend-item`/`.ww-legend-label` are unstyled
  outside Separate mode** — Phase 3A-UAT3 (Finding G) added base
  (Grouped/Custom) `max-width`/ellipsis containment; the more specific
  `#wwPanels.ww-panels-unified .ww-legend-item/-label` selector (Separate
  mode, already passed owner UAT) still wins there via specificity,
  unchanged.
- **Do not assume `index.html`'s Global Header still has a `#themeToggle`
  element or that `mountThemeToggle()` is called from `index.html`'s own
  Init** — as of Phase 3A-UAT2, both were removed; the Main Sidebar
  Menu's "Settings" item (`#mainNavSettingsBtn`, flips theme directly via
  `window.PowerwaveTheme.getTheme()`/`setTheme()`) is now the sole theme
  entry point on this page.
- **Do not assume `theme.js`'s `mountThemeToggle()` function itself was
  removed or is unused** — it is still a live, shared, tested function;
  `frontend/waveform-prototype.html` (a separate, out-of-scope page)
  still mounts and uses it unchanged. Only `index.html`'s own header
  instance was removed.
- **Do not assume `.theme-toggle` (the CSS class) was removed** — it
  remains in use by the unrelated `#shellViewToggle` (Waveform/Table/
  Split) segmented control in the Global Header; only the `#themeToggle`
  element and its mount call were removed.
- **Do not assume Plotly's `responsive: true` config alone keeps a
  waveform panel correctly sized after ANY container-width change** —
  it reliably reacts to actual `window` resize events, but NOT to a
  container that changed size for another reason (a sibling flex item
  resizing). Any FUTURE code path that changes Main Workspace's
  available width (a future Table/Split divider, a future Workspace
  Sidebar redesign, etc.) must explicitly call
  `wwResizeAllVisiblePlots()` (or `wwScheduleResizeAllVisiblePlots()`
  for a rapid-fire-event source) — it will NOT happen automatically.
  This was the exact root cause of the Phase 3A-UAT1 bug.
- **Do not assume `shellCreateHorizontalSplit()`'s `onResize` callback
  fires on every raw pointermove** — it is rAF-coalesced (at most once
  per animation frame during a drag), with an authoritative final call
  on pointerup/pointercancel. A caller that needs to observe every
  intermediate width during a drag (not just the coalesced/final ones)
  would need different wiring.
- **Do not assume `.ww-chart-wrap`'s new `overflow: hidden` is what
  fixes waveform containment** — it is a defense-in-depth safety net
  only; the actual fix is making sure Plotly is always explicitly told
  to resize. If a future gap in that wiring reappears, this CSS rule
  will hide the symptom (clipped, not overflowing) without fixing the
  underlying cause — don't mistake "no visible overflow" for "Plotly is
  correctly sized."
- **Do not assume the page still scrolls as a whole document** — as of
  Phase 3A, `<body>` has `overflow: hidden`; each shell region
  (Workspace Sidebar, `#activeViewArea`) owns its own internal scroll.
  Global Header, Main Sidebar Menu, and the Bottom Status Bar are fixed
  in place and never scroll away. This is a structural change from
  every prior phase.
- **Do not assume `main`/`header`/`footer` bare-element CSS selectors
  still exist** — they were replaced by ID-scoped shell selectors
  (`#globalHeader`, `#appBody`, `#mainWorkspace`, etc.). The semantic
  tags themselves are still used in the HTML (`<header id="globalHeader">`,
  `<main id="mainWorkspace">`) but styled only via their IDs now.
- **Do not assume Table or Split view do anything real** — both are
  structural placeholders (`.shell-view-placeholder`) with zero data,
  zero fetches, and zero real grid/split rendering. `shell.activeView`
  can represent all three states, but only `"waveform"` has real
  content. Do NOT build real Table/Split functionality without a
  separate, explicit authorization — Phase 3A only avoids blocking it
  architecturally.
- **Do not assume Main Sidebar Menu and Workspace Sidebar share any
  state** — they are deliberately independent: one is a collapsed/
  expanded boolean toggle (`shell.mainSidebarExpanded`), the other is a
  drag-resized pixel width (`SHELL_WORKSPACE_SIDEBAR_*` constants +
  `shellCreateHorizontalSplit()`). Do not couple them when adding future
  behavior — the task's own section 21 explicitly required this
  independence.
- **Do not assume the shell reads or writes waveform-domain state
  (`ww`) directly** — it does not, except for a few narrow, one-way
  READS explicitly called by the OWNING waveform code (e.g.
  `shellUpdateStatusBarChannelCount(ww.displayed.size)` is called FROM
  `wwAddSelectedChannels`/`wwRemoveChannel`/`wwClearWorkspace`, never
  the reverse). Keep this direction when extending either side.
- **Do not assume Workspace Sidebar's min/max width (240px/520px) is
  computed dynamically against the current window width** — it is not;
  these are fixed pixel bounds, a documented, deliberate initial-phase
  simplification. The responsive drawer fallback (below ~900px) is what
  actually prevents an unusably narrow squeeze at real narrow
  viewports, not dynamic bound computation.
- **Do not assume the responsive drawer/collapse behavior was visually
  verified** — it was reasoned through and covered by CSS source
  inspection, but real narrow-viewport rendering was NOT confirmed in
  this sandbox (no real browser). Flagged for owner UAT.
- **Do not assume "Tools" exists anywhere in the UI** — it was
  deliberately omitted from both the Global Header and (as a REAL
  destination) Main Sidebar Menu this phase; only a disabled,
  clearly-marked placeholder nav item exists in the rail. No functional
  Tools destination exists yet.
- **Do not assume the ruler's title is rendered by a custom DOM
  element** — as of Phase 2C-C4B, `#wwStickyRulerTitle` and
  `#wwStickyRulerContext` were both deleted entirely (not hidden — the
  elements and their CSS no longer exist in the file at all). The
  title is now Plotly's own native `xaxis.title` property on the
  ruler's own chart layout, read via `layout.xaxis.title` (at init) or
  the most recent relayout's `update["xaxis.title"]` — the same pattern
  every real waveform panel already uses for its own title.
- **Do not assume "Record time" (lowercase t) is still the sticky
  ruler's Absolute-mode wording** — it is now "Record Time" (capital
  T), per explicit owner instruction in Phase 2C-C4B. The TOOLBAR's own
  `#wwTimeModeContext` label is unaffected and still uses lowercase
  "Record time" — the two are deliberately different now; do not
  "fix" one to match the other without checking which context you're
  in.
- **Do not assume any date text appears inside the sticky ruler** — it
  does not, as of Phase 2C-C4B; the ruler shows only tick labels and
  the mode title. The toolbar's own date-context label is the sole
  remaining place a date is shown.
- **Do not assume the ruler's Elapsed-mode tick VALUES are still raw
  seconds with just a relabeled title** — they are genuinely rescaled
  (×1000 for ms, ×1/60 for min) by `wwStickyRulerElapsedUnit()`, the
  SAME function that also chooses the title text, so title and ticks
  can never disagree (Phase 2C-C4A, section 4 of that task). This
  rescale is scoped ENTIRELY to the ruler's own independent Plotly
  x-axis domain.
- **Do not assume this rescale touches `ww.viewport`,
  `wwElapsedToPlotlyX()`, `wwBuildTrace()`, or any real waveform
  panel's own axis** — it does not; all of those remain exactly as
  Phase 2C-C3 left them, always raw elapsed seconds. Grouped/Custom
  panels' own per-panel axes (already a known, separate duplication
  with the ruler since Phase 2C-C4) are unaffected and still show raw
  seconds via the unchanged `wwTimeAxisTickFormat()`.
- **Do not assume Elapsed-mode unit-switching was verified to preserve
  tick-pixel alignment in a real browser** — it was reasoned through
  (Plotly's own "nice tick value" algorithm is scale-covariant under a
  constant multiplier) but NOT visually confirmed; no browser is
  available in this sandbox. Treat this as the single most important
  open item for owner UAT, not a settled fact.
- **Do not assume the ruler still has its own date-context line at
  all** — Phase 2C-C4A gave it one (date-only, alongside a
  "Record time" title); Phase 2C-C4B removed it entirely per owner
  correction. Only the toolbar's `#wwTimeModeContext` label still shows
  a date, unchanged full "<date> · Record time" wording.
- **Do not assume the sticky ruler is interactive** — it deliberately is
  not this slice (`staticPlot: true`, `pointer-events: none` on its CSS
  wrapper): not draggable, not zoomable, not pannable, not selectable,
  no crosshair. Waveform panels remain the only interaction surfaces;
  the ruler is display-only, per this task's own §11/§24.
- **Do not assume the ruler holds its own viewport or time-mode state**
  — it does not; `wwSyncStickyRuler()` reads `ww.viewport`/`ww.timeMode`
  fresh every time it is called and never stores an independent copy.
  There is no scenario where the ruler and the panels can show different
  ranges/modes simultaneously by construction.
- **Do not assume the ruler is a second waveform chart** — it carries an
  empty (`[]`) traces array always; it never fetches, holds, or displays
  channel data. Its only content is the shared x-axis.
- **Do not assume Grouped/Custom panels' own per-panel x-axis labels
  were suppressed by this phase** — they were **not**; only Separate
  mode's per-lane labels changed (now suppressed on every lane, not just
  the non-bottom ones). Grouped/Custom panels still show their own
  ticks/title on every panel, which now visibly duplicates the sticky
  ruler — a documented, deliberate, NOT-yet-fixed gap (section 16), left
  for a future cleanup pass rather than a larger restructuring this
  phase's own scope didn't justify.
- **Do not assume the ruler uses a scroll event listener** — it does
  not; its visibility/positioning is pure CSS `position: sticky`,
  confirmed by test to cause zero JavaScript work (zero Plotly calls,
  zero waveform fetches) when scroll events fire.
- **Do not assume the ruler is `position: fixed`** — it is
  `position: sticky`, constrained to `.workspace-section`'s own box; it
  does not float over the footer or any content below the waveform
  workspace, and stops being sticky once the whole workspace has
  scrolled past.
- **Do not assume the Absolute-mode timestamp is derived from the
  trigger time, the browser's clock, the upload time, or a guessed
  timezone** — it is derived exclusively from the backend's own
  `timebase.start_time` (already-parsed, existing COMTRADE CFG field),
  confirmed against real parsed metadata that sample 0 = `start_time`,
  never `trigger_time`. There is no timezone anywhere in this path — the
  parser never attaches one, and the frontend never invents or
  silently converts to browser-local time.
- **Do not assume Synthetic Elapsed Time or Sample Index are
  implemented** — they are not; both are reserved NAMES in the
  time-mode model (`WW_TIME_MODES`) for possible future CSV/Excel work
  only. The only two selectable modes today are Absolute and Elapsed.
- **Do not assume a time-mode switch ever refetches waveform data,
  changes `ww.viewport`, or changes which channels are displayed** —
  verified by test that it does none of these; it is a pure
  presentation transform of already-loaded data.
- **Do not assume multi-source Absolute-mode display has been solved**
  — it has not; if channels from sources with different recording-start
  timestamps were ever displayed together, Absolute-mode labels would
  use only the first-displayed channel's origin. This is a documented,
  known gap for future multi-source work, not something this pass fixed
  or hid.
- **Do not assume `ww.timeMode` resets when the workspace is cleared**
  — it deliberately does not; it persists as a viewing preference, same
  policy as `ww.layoutMode`/`ww.dragMode` (verified by test).
- **Do not assume drag/reorder/overlay/split has started** — it has not;
  no direct vertical lane dragging (to reorder panels), no reorder, no
  drop-to-overlay/group by direct lane dragging, no drag-out-to-separate
  exist anywhere in the repository. **Custom layout mode DOES now exist**
  (Phase 2C-C1, DEC-027) — do not confuse it with drag/reorder; Custom
  Groups are assigned via a modal dialog with dropdowns and buttons, not
  by dragging lanes. **Panel HEIGHT resize DOES now exist** (Phase
  2C-C2, DEC-028) — do not confuse this with lane drag/reorder either;
  the resize handle only ever changes a panel's vertical size, never its
  position/order relative to other panels, and there is still no way to
  reorder or drag one lane onto another.
- **Do not assume Custom mode's channel-to-group assignment uses
  drag-and-drop** — it deliberately does not (this task's own §6 allowed
  skipping it "unless genuinely simple"); moving a channel between groups
  is two explicit actions (remove from its current group via a chip's ×,
  then assign via an Unassigned-channel `<select>` dropdown).
- **Do not assume every displayed channel must be placed in a custom
  group before Apply works** — it does not; any unassigned channel
  automatically becomes its own single-channel panel (the documented,
  chosen rule, DEC-027). There is no validation error state to satisfy.
- **Do not assume Custom grouping is persisted to the backend or survives
  a page reload/new session** — it is not; `ww.customGroups` is
  frontend-only, in-memory, ephemeral session state (matching DEC-015's
  existing ephemeral-by-design principle), reset only by a whole-
  workspace clear ("Clear workspace"/"Start new workspace").
- **Do not assume panel resizing ever triggers a waveform refetch, resets
  the shared X/time viewport, or resets a panel's Y range** — verified by
  test that it does none of these; `Plotly.Plots.resize()` is the only
  Plotly API a height change ever calls.
- **Do not assume panel heights are persisted to the backend or survive a
  page reload** — they are not; `ww.panelHeights` is frontend-only,
  in-memory, ephemeral session state (matching DEC-015), reset only by a
  whole-workspace clear. Removing an individual channel/panel does NOT
  clear its remembered height (same policy as `ww.customGroups`).
- **Do not assume panel resizing supports keyboard input** — it does not
  this slice (documented accessibility limitation, DEC-028); the handle
  is `tabindex="-1"` and pointer/touch-drag only.
- **Do not assume the Phase 2C-C2A responsiveness refinement changed the
  100–600px height bounds, the panel-height state model, Plotly call
  COUNTS, or any Grouped/Separate/Custom/synchronization behavior** — it
  did not; only the ORDER/coupling of the existing DOM-write and
  Plotly-resize steps changed (the DOM write moved off the rAF gate; the
  Plotly call is still coalesced to at most once per frame, same as
  before). Confirmed by test that Plotly resize call counts are
  unchanged.
- **Do not claim the resize drag now "feels smoother" as a confirmed
  fact** — the decoupling mechanism was proven structurally via jsdom
  instrumentation with a simulated-cost Plotly mock, not via real
  browser paint timing or tactile testing (neither is available in this
  sandbox, and no browser-automation tool was installed to attempt it).
  This remains explicitly for owner manual UAT.
- **Do not assume the unified-canvas refinement changed the panel/layout
  data model or the Y-axis behavior** — it did not; `ww.panels` (displayed
  channels + panel membership + panel order) is byte-for-byte the same
  model Phase 2C-B1 (DEC-025) built. Each lane still has its own
  completely independent Y axis; **no channel was ever merged onto
  another channel's Y axis** — this was an explicit, deliberate
  distinction in the task's own instructions, not an incidental detail.
- **Do not confuse this pass's "overlay label" with the future
  "drag-to-overlay" interaction** — they are unrelated concepts that
  happen to share the word "overlay." This pass only changed the label's
  *visual position* (a static CSS overlay on the chart, no dragging, no
  interaction beyond the pre-existing remove button). Drag-to-overlay/
  group (dragging one channel's lane onto another to merge them) remains
  entirely unbuilt — do not read this pass as any part of that feature.
- **Do not assume digital channels or a digital-section container exist**
  — neither was built this pass; no digital content, fake or real, exists
  anywhere in the repository.
- **Do not assume the overlay label correction changed anything besides
  the tag's position/styling** — it did not; the same `.ww-legend`/
  `.ww-legend-item` DOM (now with one added `.ww-legend-label` wrapping
  span), the same remove control, the same color dot, the same panel/data
  model, and the same unified-canvas container from Phase 2C-B2 are all
  unchanged. Only the CSS grid-column order and the tag's own styling
  moved.
- **Do not assume Separate is the default** — Grouped is, unchanged from
  Phase 2C-A; Separate is opt-in via the new toolbar toggle.
- **Do not assume channels are permanently locked to their panel in
  either layout mode** — panel membership is always re-derivable from the
  flat displayed-channel list (`wwRebuildLayout()`); this is exactly the
  property that made Grouped/Separate switching straightforward and is
  the same property a future drag/reorder feature will rely on.
- **Do not assume switching layout mode refetches waveform data or
  resets the viewport** — verified by test that it does neither; already-
  fetched channel data and the current shared X/time range are both
  reused as-is.
- **Do not assume a multi-channel batching endpoint exists** — it does
  not; N displayed channels still means N independent existing
  single-channel requests, regardless of layout mode. Batching remains
  evidence-gated future work, not built.
- **Do not assume crosshair behavior changed** — each panel's crosshair
  (DEC-022/DEC-023, `spikethickness: 0.35`, `spikedash: "3px,2px"`,
  sample-snapped) is independent in both layout modes; hovering one panel
  does not show a guide line on any other panel.
- **Do not assume "Clear workspace" or channel removal touches an
  imported source** — both are purely display-state operations; the
  source (and its backend-retained record) is untouched either way, in
  either layout mode.
- Do not assume theme switching ever triggers a waveform data refetch — it
  doesn't, by design and by test; `Plotly.relayout` only, applied to
  every panel regardless of layout mode.
- **Do not assume Plotly is still "pending" or "preferred but open"** —
  it is the final, owner-selected renderer (DEC-022, unaffected by this
  pass). uPlot remains removed.
- **Do not assume DEC-021 (workspace-level navigation) is weakened by
  Separate mode having more panels** — the shared viewport is still
  mandatory and still enforced identically regardless of panel count.
- Do not assume TTL or the ~100 MB validation is solved — both remain
  explicitly open; neither Phase 2C-A nor Phase 2C-B1 changes the backend
  memory-retention shape (see "What remains unresolved" above).
- Do not assume the retained `DisturbanceRecord` (Phase 2A, DEC-019) or the
  waveform API's behavior changed this pass — zero backend files were
  touched; the existing single-channel endpoint's contract is unchanged.
- Do not assume `Start new workspace`/`Remove` behavior changed for
  SOURCES — both are unchanged from DEC-018; both already clean up the
  waveform workspace display, unaffected by which layout mode is active.
- Do not assume the COMTRADE upload interaction is still open for UAT — it
  is decided (DEC-017): two explicit slots, not auto-pairing.
- Do not assume Phase 1.5, drag/reorder work, or any later phase is
  authorized.
- Do not assume `powerwave` is still at commit `3156392` by the time you
  read this — this pass did not re-verify `powerwave` (no fresh
  `powerwave` investigation was needed for this implementation task); the
  last confirmed commit was `3156392`, from the Phase 2C design pass.

## Owner approval needed before proceeding?

- **Yes — Phase 4A (Digital Channels Rendering) specifically needs
  real-browser owner UAT before any further waveform feature work
  (cursor/measurement tools etc.) begins**, per that task's own explicit
  closing instruction. See "What was most recently done" at the top of
  this document for the open questions (digital step-trace readability
  in Light/Dark, hover tooltips, scroll feel, zoom/pan responsiveness at
  a real large digital-channel count).
- Not needed to review or use Phase 2C-A, Phase 2C-B1, Phase 2C-B2, Phase
  2C-B3, Phase 2C-B3A, Phase 2C-C1, Phase 2C-C2, Phase 2C-C2A, Phase
  2C-C3, Phase 2C-C4, Phase 2C-C4A, Phase 2C-C4B, Phase 3A, Phase
  3A-UAT1, Phase 3A-UAT2, Phase 3A-UAT3, Phase 3A-UAT4, or Phase 3B
  themselves — already implemented, deployed to DEV, and live-verified
  per this exact task's own authorization. **Recommended, though**: an
  owner UAT specifically confirming (a) the Global Header now reads
  cleanly with no leftover gap where the removed Light/Dark control sat,
  (b) the Main Sidebar Menu's "Settings" item remains comfortably
  reachable/usable in both collapsed and expanded states, (c) the Phase
  3A-UAT3 overflow fixes hold up visually — Workspace Sidebar at 240px,
  Grouped/Custom long legends, narrow-browser behavior around the
  ~900px responsive threshold, sidebar drawer reopen, and
  Waveform → placeholder → Waveform, (d) the Phase 3A-UAT4 fix
  specifically — the owner's own reported CFG/DAT filenames now wrap
  fully within the Sidebar at 240px with no horizontal escape, and (e)
  Phase 3B as a whole — Recordings page simplicity/readability, Main
  Sidebar Menu Waveform/Recordings navigation, the Upload New modal
  (format selector, file requirements, loading/error/success states),
  the Open/Analyse workflow, and that Waveform ⇆ Recordings navigation
  genuinely preserves viewport/zoom/grouping/panel-heights/time-mode as
  claimed — plus the still-open Phase 3A proportions/dimensions feedback
  and the still-carried-forward Phase 2C-C4A
  tick-alignment-at-rescaled-units claim — none of which could be
  visually confirmed in this sandbox.
- **Yes**, before any drag/reorder/overlay/split work begins (still the
  owner's own possible next direction, deliberately set aside across
  thirteen passes now, but still not yet explicitly authorized to
  *implement* — Phase 3A's shell only avoids blocking it
  architecturally), before REAL Table or Split view implementation
  (explicitly not authorized yet — only structural placeholders exist),
  before REAL CSV/Excel parsing (Phase 3B's upload modal is structurally
  ready for these formats — `RECORDING_FORMATS` lists them as
  `enabled: false` — but no parser exists for either; explicitly not
  authorized yet), before a persistent/database-backed recording
  library (Phase 3B's Recordings page is explicitly session/workspace-
  backed only, per DEC-032 — persistent retention is a separate future
  product/architecture decision, not to be backed into via a UI
  feature), before cursor/measurement tools or any further waveform
  feature builds on top of digital-channel rendering (Phase 4A is now
  implemented and deployed to DEV per that task's own authorization, but
  its own explicit closing instruction was to stop for real-browser
  owner UAT before proceeding further — see the Phase 4A entry at the
  top of this document for the specific open questions), before
  Synthetic Elapsed Time, Sample
  Index, or any CSV/Excel timing mode, before the Grouped/Custom per-panel
  axis-label duplication (Phase 2C-C4's own section 16 gap, unchanged
  and still outstanding across five passes now) is cleaned up, before
  interactive ruler zoom/pan/selection or a shared crosshair on the
  ruler, before Cursor A/B or Delta Cursor functionality in the Bottom
  Status Bar, before Phase 1.5 or any later phase begins, before a PROD
  deployment, before any further crosshair or theming work beyond
  what's already described in project-memory, and before any change to
  the ephemeral-storage, upload-size, COMTRADE-upload-interaction,
  workspace-lifecycle, or waveform-data decisions recorded in
  `DECISIONS.md`. Per the change-governance rule in
  [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md).
- **Recommended before any further prolonged/shared-DEV waveform UAT**: a
  real decision on the abandoned-session TTL question, and ideally the
  ~100 MB real-file memory validation, rather than continuing to rely on
  the manual DEV stopgap.
