# Sequence Components Analysis

Status: **v1 implemented and CLOSED as a stable feature** (2026-09-18).
Activates the pre-existing `Sequence Components` navigation placeholder
as the **FOURTH** Analysis-menu analyzer (order preserved: Phasor,
Overcurrent, Impedance Locus, Sequence Components). See
[DECISIONS.md — DEC-097](DECISIONS.md#dec-097--sequence-components-v1-the-fourth-analysis-menu-analyzer-positivenegativezero-sequence-voltage-and-current-calculationvisualization)
for the approval record.

**2026-09-18 UAT fix — vector shaft/color rendering** (renderer/style
only, no math changed): see "Vector rendering invariant and the shaft/
color rendering bug fix" below for the full root-cause record.

**2026-09-18 closure/hardening pass** — a complete audit of every
Sequence-specific implementation path (domain math, service layer, API/
schema, frontend state machine, Recording/Manual input, Playback,
Related Waveforms, vector renderer, scale logic, visibility, ratios,
angle convention, responsive layout, theme tokens, tests, docs) found
the architecture already sound; closure work was almost entirely test-
hardening plus two documentation clarifications for behavior that was
already correct but not yet explicitly confirmed in writing (see
"Closure-pass audit summary" below for the full list, including the
items explicitly checked and found to already be correct).

## Closure-pass audit summary (2026-09-18)

Every item in the closure task's own checklist (math, color system,
vector renderer, scale behavior, scale legend, Manual mode, Recording
mode, partial-family behavior, ratios, angle convention, naming/
ordering, visibility controls, Related Waveforms, Playback, empty/
invalid states, responsive UI, accessibility) was audited against the
current code, not assumed correct because existing tests passed. Result:

- **No production defects found** beyond the vector-shaft/color bug
  already fixed the same day (see above) — every other audited path
  (domain transform, service-layer family evaluation, API schema,
  frontend fetch/stale-response guards, Playback integration, Related
  Waveforms, Manual/Recording isolation) was verified correct by direct
  code reading AND real-browser testing, not assumption.
- **Two behaviors were confirmed-and-documented, not changed** (task's
  own "if changed, explain the difference; if not, confirm and
  document" framing): (1) hiding a role never rescales the remaining
  visible vectors — see "Sequence visibility" below; (2) a ratio's own
  magnitude is never capped, only guarded against `Infinity`/`NaN` —
  see "Sequence ratios" below.
- **Naming/ordering was already consistent** — `V1`/`V2`/`V0` (positive
  → negative → zero) is used uniformly across the Values list, the
  combined diagram's own draw order, and the ratio labels (`V2/V1` then
  `V0/V1`); no `0,1,2` vs `1,2,0` inconsistency was found anywhere.
- **Backend golden coverage was strengthened**: the existing unbalanced/
  mixed-input golden test asserted magnitude only — now asserts real,
  imaginary, magnitude, AND angle (catching a rotation-direction/sign
  bug a magnitude-only check could miss), plus a new equivalent Current-
  domain unbalanced golden case.
- **Real-browser coverage was substantially extended**
  (`browser-tests/sequence_components_analysis.spec.js` grew from 20 to
  33 scenarios): individual dominant-color golden cases for all six
  roles (V1/V2/V0/I1/I2/I0, closing the I2/I0 gap), a mixed-all-six-
  visible simultaneous-color case, dark-theme color resolution, the
  visibility/scale-isolation rule, angle-wrap-around display, the ratio-
  unavailable guardrail at the UI layer, context-switch staleness, and
  scale-legend/vector non-overlap at 1366px/1024px.
- **No Sequence-specific `[OPEN]`/pending/TODO/FIXME items existed** in
  the codebase or `docs/project-memory/` before this pass (confirmed by
  direct search) — there was nothing pending to close going in.

## Vector rendering invariant and the shaft/color rendering bug fix

**Invariant (owner instruction, now guarded by regression tests):**

> Every available, visible sequence component is rendered as a
> complete vector from origin to arrowhead, using its sequence-identity
> color.

That means, for every rendered role (`V1`/`V2`/`V0`/`I1`/`I2`/`I0`), all
three of: a shaft (`<line>`) with a real, non-zero, correctly-colored
stroke; an arrowhead (`<polygon>`) filled in the same color; and a
label (`<text>`). A vector whose magnitude is genuinely tiny may have a
naturally short shaft — that is correct, physical behavior, never a
bug. A vector with a materially non-zero magnitude must never render as
an isolated arrowhead with no visible connecting shaft.

**Owner UAT report**: sequence values appeared to calculate correctly
(arrowheads positioned far from the origin for a dominant component,
near the origin for small ones), but the connecting shaft line was
effectively invisible, and the intended Positive/Negative/Zero
sequence-identity colors did not appear to be applied.

**Investigation**: `wwSequenceRenderDiagramSvg()` is structurally
identical to the proven `wwPhasorRenderDiagramSvg()` — same grid/ring/
legend geometry, same scale-freeze policy, and it calls the exact same
`wwPhasorVectorSvg()` shaft/arrowhead/label drawing function Phasor's
own diagram uses (see "Visualization" below). Direct comparison and
exhaustive real-browser testing (Manual and Recording, Secondary and
Primary basis, balanced and unbalanced angles, light and dark theme, the
visibility-toggle round trip) all rendered correctly against a healthy,
up-to-date `theme.css` — the defect could not be reproduced that way.

**Root cause, confirmed by direct reproduction (not assumed):**
`wwSequenceRoleColor()` (the function that maps `V1`/`V2`/`V0`/`I1`/`I2`/
`I0` to `--ww-seq-positive`/`-negative`/`-zero`) returned a bare
`var(--ww-seq-positive)` with **no fallback value** — unlike this
codebase's own already-established defensive-CSS convention for exactly
this risk (see `.ww-annotation`'s own CSS comment: a `var(x, fallback)`
second argument "falls back... if this file is ever loaded without
theme.css, e.g. a stale cached copy predating this token"). The
`--ww-seq-*` tokens are comparatively NEW (added in this same feature's
own slice, 2026-09-18) — a genuine staleness window exists for a
recently-added token in a way it essentially does not for Phasor's own
long-stable `--ww-phase-a/b/c` tokens (which alias `--accent`/`--warn`/
`--ok`, present since early in the project). With `--ww-seq-positive`
unresolved:
- The shaft `<line>`'s own `stroke="var(--ww-seq-positive)"` is its
  **only** color source (no competing CSS class for the solid/Voltage
  case) — an unresolved token is invalid at computed-value time, so the
  browser falls back to `stroke`'s own SVG initial value, `none`: an
  **entirely invisible shaft**, even though the line's own `x1/y1/x2/y2`
  geometry is completely correct (proving the Fortescue math/positioning
  was never the problem).
- The arrowhead `<polygon>`'s own `fill="var(--ww-seq-positive)"`
  degrades the same way, but `fill`'s own SVG initial value is `black`,
  not `none` — so the arrowhead stays **visible**, just in the wrong,
  browser-default color.
- The `<text>` label survives untouched only because it also carries
  `.ww-phasor-vector-label { fill: var(--text) }` in the stylesheet,
  which always outranks the inline presentation attribute regardless of
  whether the sequence token resolves — so the label stays visible too.

This precisely reproduces every symptom reported. Confirmed directly by
temporarily unsetting the three custom properties in a real browser
(`:root { --ww-seq-positive: initial; ... }`) and observing computed
`stroke: none` on the shaft and `fill: rgb(0, 0, 0)` on the arrowhead —
a screenshot of that state is pixel-for-pixel the shape the owner
described (a lone black arrowhead far from the origin, no visible
connecting line).

**Fix** (`wwSequenceRoleColor()`, `frontend/index.html`): each of the
three lookups now carries the same `var(x, fallback)` defensive pattern
already established elsewhere in this file —
`var(--ww-seq-positive, var(--text-dim))`, etc. — falling back to the
SAME `--text-dim` token this function already used for an unrecognized
role key. Even in the degraded case, the shaft now stays visibly
present (a neutral gray, not gone), and the arrowhead is never
browser-default black. The primary color path (a healthy, up-to-date
`theme.css`) is completely unchanged — `--ww-seq-positive/-negative/
-zero` still render exactly as before. `wwPhasorRoleColor()` (Phasor's
own, separate function) was deliberately left untouched — out of this
fix's explicit narrow scope, and its own tokens carry negligible
staleness risk in comparison.

No math, Recording calculation, Manual calculation, ratio, basis-
conversion, or Playback behavior was touched — confirmed by this fix
touching exactly one function (`wwSequenceRoleColor()`), a pure color-
string builder with no numeric/geometric logic of its own.

**Regression coverage** (`browser-tests/sequence_components_analysis.spec.js`):
a new "vector shaft/color rendering" suite asserts actual rendered SVG
geometry and computed color (never markup presence alone) for a
dominant V1, a pure V2, a pure V0, a dominant I1, and all six roles
together, in both Manual and Recording mode, at 1366px/1024px; plus one
dedicated test that reproduces the exact degraded-token scenario above
and asserts the shaft still paints — verified to actually fail before
the fix (`lineStroke === "none"`) and pass after it, per this project's
own disable-fix-then-verify discipline.

## Product definition

Powerwave calculates the classical Fortescue symmetrical-component
transform from a three-phase set of phasors — independently for Voltage
(Va/Vb/Vc → V0/V1/V2) and Current (Ia/Ib/Ic → I0/I1/I2):

```text
a = exp(j*2*pi/3)                        (the 120 deg rotation operator)

X0 = (Xa + Xb + Xc) / 3                  (zero sequence)
X1 = (Xa + a*Xb + a^2*Xc) / 3             (positive sequence)
X2 = (Xa + a^2*Xb + a*Xc) / 3             (negative sequence)
```

This is calculation + visualization only. **Explicitly not protection
interpretation** — see "Scope of v1" below.

## Scope of v1

**In scope:** positive-, negative-, and zero-sequence Voltage and
Current calculation from a resolved (Recording) or manually-entered
(Manual) three-phase phasor set; a combined polar phasor diagram
(V1/V2/V0 and I1/I2/I0, six vectors, two independent graphical scales);
a compact Values panel; descriptive negative-/zero-sequence ratios
(`|V2|/|V1|`, `|V0|/|V1|`, `|I2|/|I1|`, `|I0|/|I1|`, all as percentages);
per-role visibility toggles; the shared Analysis Input Source (Recording/
Manual), Playback, and Related Waveforms primitives.

**Explicitly out of scope this slice** (task's own instruction, restated
here as the single most important interpretive boundary): protection
interpretation of any kind. No unbalance limits, no negative-sequence
relay operation claims, no ground-fault analysis, no fault
classification, no sequence-network diagrams, no sequence impedance, no
trip-decision claims exist anywhere in this feature. A future analyzer
(unbalance assessment, negative-sequence protection, ground-fault
analysis, system disturbance studies) may consume V0/V1/V2/I0/I1/I2 as
its own input, built on top of this module — never coupled into it here.

## Recording mode reuses the existing Phasor estimator — no second estimator

`app.services.sequence_components_analysis_service.compute_sequence_
analysis()` calls the existing, unchanged `phasor_analysis_service.
compute_phasor_diagram()` — the same bay-centric aggregator Phasor's own
page, and Impedance Locus's own Recording mode, already use — and reads
out the Va/Vb/Vc and Ia/Ib/Ic roles it already resolved and estimated.
Zero duplicated FFT/DFT/RMS code, and automatic inheritance of that
function's own reference-frequency/timebase/waveform-form guardrails.
`app.domain.analysis_requirements` gained `SEQUENCE_VOLTAGE_PHASE_A/B/C`/
`SEQUENCE_CURRENT_PHASE_A/B/C` under their own
`analysis_kind="sequence_components"` (declared for registry
completeness/future reuse, mirroring Impedance's own precedent exactly —
the service itself resolves via `compute_phasor_diagram()`, never a
second `resolve_analysis_inputs()` call).

## Complete-phase-set requirement — the one hard difference from Phasor's own diagram

Unlike Phasor's own six-independent-role diagram (where one role's own
status never affects another), a sequence-component transform is
mathematically meaningless without all three phases of ONE family
present. `app.services.sequence_components_analysis_service._evaluate_
family()` requires Va+Vb+Vc (or Ia+Ib+Ic) all `available` before calling
`app.domain.sequence_components.compute_symmetrical_components()`; an
incomplete family reports the worst of the three roles' own statuses
(`missing`/`needs_configuration`/`ambiguous`/`not_eligible`, using the
identical precedence order `app.services.impedance_analysis_service.
_worse_role_status()` already established, generalized here from two
roles to three) — never a fabricated missing phase. **Voltage and
Current families are evaluated completely independently** — one
family's own incompleteness never blocks or degrades the other (task's
own worked example: Va/Vb/Vc complete, Ia/Ib incomplete → Voltage
sequences calculated, Current sequences report Missing).

Channel identity (`phase_a_channel_ref`/`phase_b_channel_ref`/
`phase_c_channel_ref`) is carried through on each family's own result
regardless of that family's `status`, whenever a role's own identity is
known — mirroring `ImpedanceAnalysisResult`'s own "identity known,
independent of overall status" precedent — so the shared Related
Waveforms panel can always show the underlying source phase quantities
even when the sequence transform itself could not be computed.

## Complex-number representation

`app.domain.sequence_components` is the first module in this codebase to
need genuine complex-number arithmetic (a linear combination of three
rotated phasors) — rather than hand-rolling real/imaginary-part
bookkeeping the way `app.domain.phasor._phasor_from_window()` does (a
style chosen there to keep a hot per-sample estimation loop simple),
this module uses the stdlib `complex`/`cmath` directly: there is exactly
one of these transforms per analysis (never a per-sample loop), so there
is no performance reason to avoid it, and the native complex type keeps
the implementation directly checkable against the textbook definition.
`_ALPHA = cmath.exp(1j * 2.0 * math.pi / 3.0)` is the rotation operator;
`compute_symmetrical_components()` builds each phasor via `cmath.rect(
magnitude, radians(angle))`, applies the three linear combinations, and
converts back to magnitude/angle via `cmath.polar()`.

## Angle convention — reused verbatim, never a new one

`Xa`/`Xb`/`Xc` are built from each phasor's own **ABSOLUTE** angle
(`angle_deg_absolute`) — the identical convention Impedance Locus's own
`theta_Z = theta_V - theta_I` and Phasor's own combined-diagram vector
geometry already use — never independently zero-referenced, which would
destroy the true inter-phase angular relationship this transform depends
on entirely. Output angles are normalized to `(-180, 180]` via the same
shape `app.domain.phasor._normalize_angle_deg()` already uses
(re-declared locally, matching this codebase's own established
"each analyzer module owns its own tiny helper/tolerance constant"
convention).

## Golden mathematical result — the chosen phase-sequence convention, proved

With `a = exp(j*120 deg)`:

```text
Balanced positive sequence:
  Va=100∠0°, Vb=100∠-120°, Vc=100∠120°
  → V1 ≈ 100∠0°, V2 ≈ 0, V0 ≈ 0

Pure zero sequence:
  Va=Vb=Vc=100∠0°
  → V0 = 100∠0°, V1 ≈ 0, V2 ≈ 0

Pure negative sequence (B/C swapped relative to positive sequence):
  Va=100∠0°, Vb=100∠120°, Vc=100∠-120°
  → V2 = 100∠0°, V1 ≈ 0, V0 ≈ 0
```

These three vectors are the core regression (task's own explicit
mandate) — see `backend/tests/test_sequence_components_domain.py::
TestGoldenBalancedPositiveSequence/TestGoldenPureZeroSequence/
TestGoldenPureNegativeSequence`, each proved against an independently
hand-summed reference (never a value re-derived from the implementation
itself), plus a Fortescue inverse-transform conservation identity
(`Xa = X0 + X1 + X2` exactly) checked on a genuinely unbalanced/mixed
input as an implementation-independent sanity property.

## Sequence ratios — descriptive only, numerical-validity guardrail

`negative_sequence_ratio_percent = |X2|/|X1| * 100`,
`zero_sequence_ratio_percent = |X0|/|X1| * 100` — purely descriptive
(task's own explicit "never compare against protection thresholds in
v1" instruction). `app.domain.sequence_components.
MIN_POSITIVE_SEQUENCE_MAGNITUDE = 1e-9` guards the division only: when
`|X1|` is effectively zero, the ratio is reported unavailable (`None` →
frontend "Unavailable"), never `Infinity`/`NaN`. This is a numerical-
validity floor only, deliberately tiny (unlike e.g. `app.domain.
impedance.MIN_CURRENT_A`, which excludes a whole physically-meaningless
measurement range for a different purpose) — it only needs to exclude
genuine floating-point-zero. A real waveform-**estimated** phasor from a
Recording never lands at exact mathematical zero (estimator noise sits
well above this floor for any realistic signal), so the guardrail's own
"unavailable" branch is only practically reachable via Manual mode's
exact math or a degenerate Recording; see `backend/tests/
test_sequence_components_analysis_api.py::
TestManualSequenceViaHttp::test_near_zero_positive_sequence_ratio_is_
unavailable_via_manual` for the end-to-end proof and its own comment on
why the equivalent Recording-mode assertion is written differently.

**Deliberately no upper cap on a ratio's own magnitude (closure-pass
audit, 2026-09-18):** a positive sequence just above the `1e-9` floor
paired with a genuinely large negative/zero sequence can still produce
an arithmetically enormous percentage (e.g. millions of percent) —
this is intentional, not a bug: `sequence_ratio_percent()` guards
against division producing `Infinity`/`NaN` only, never against a
technically-valid-but-extreme *value*, since capping or reformatting an
extreme-but-real ratio would itself be an implicit threshold/compliance
judgment (task's own explicit "ratios are descriptive only, do not add
protection thresholds or compliance judgments" instruction). In
practice this is essentially unreachable from a real Recording (a
waveform-estimated phasor's own noise floor sits far above `1e-9` for
any realistic signal — see above); it is only reachable via a
deliberately degenerate Manual input, in which case an engineer sees an
honest (if visually large) descriptive number rather than a silently
clamped one.

## Visualization — combined polar diagram, two independent family scales

`wwSequenceRenderDiagramSvg()` mirrors `wwPhasorRenderDiagramSvg()`'s
own geometry/legend/vector-drawing shape almost exactly (reuses
`wwPhasorVectorSvg()` verbatim), but draws six SEQUENCE roles
(`V1`/`V2`/`V0`/`I1`/`I2`/`I0`) instead of six PHASE roles. Sequence
components within one family share ONE graphical scale (task's own
section 10: "Voltage scale derived from `max(|V0|,|V1|,|V2|)`");
Voltage and Current use INDEPENDENT scales, both normalized to the same
outer plot radius, exactly like Phasor's own diagram — never letting one
family affect the other. Voltage vectors solid, Current vectors dashed
(quantity-type distinction, reused from Phasor).

**Color identity is sequence-based, never phase-based** (task's own
section 13: "do not reuse phase A/B/C colors in a way that implies phase
identity") — three new dedicated design tokens in `frontend/theme.css`,
`--ww-seq-positive`/`--ww-seq-negative`/`--ww-seq-zero` (violet/teal/
magenta family, light+dark variants), distinct from `--ww-phase-a/b/c`
(which alias `--accent`/`--warn`/`--ok`) and from `--error` (already
"problem" app-wide) and from `--annotation-peak-accent` (a different
muted teal-green already used for +Peak/-Peak waveform markers).
`wwSequenceRoleColor(roleKey)` maps a role's trailing digit
(`1`→positive, `2`→negative, `0`→zero) to its own token.

## Scale stability during Playback — implemented correctly from day one

Follows the "recently corrected Phasor invariant" the task itself names
(section 11): Manual mode always recomputes its own family scale fresh
from its own currently-enabled values on every render — it never reads
or writes the frozen-scale fields at all. Recording mode preserves the
SAME Playback-stability freeze policy Phasor's own diagram uses
(`wwSequenceState.frozenVoltageScale`/`frozenCurrentScale`, established
from the first valid result of a "playback run," held fixed unless a
later magnitude would overflow the plot radius, released on a genuine
Restart-to-`bounds.start` or a real context switch). The freeze fields
are gated on `wwSequenceState.inputSource` from the very first line of
code — this analyzer never had the Manual/Recording scale-leak bug
Phasor's own diagram once had and later fixed (see PHASOR_ANALYSIS.md's
own "Diagram scaling stability during Playback" section for that
incident record); there was nothing to fix here, only a precedent to
follow. `backend/tests/test_frontend_sequence_components_analysis.py::
TestSequenceScaleNeverLeaksBetweenRecordingAndManual` guards this
statically.

## Manual Input / Calculator mode

Reuses the shared Analysis Input Source shell (`WW_ANALYSIS_INPUT_
SOURCE_RECORDING`/`WW_ANALYSIS_INPUT_SOURCE_MANUAL`) and the three-
region markup separation (always-visible Input Source toggle /
Recording-only section / always-visible Body) verbatim, implemented
correctly from day one — mirrors Impedance Locus's own precedent, never
the flawed intermediate coupling Overcurrent briefly shipped and later
corrected (see [ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md)).

**Manual entry stays phase-domain, never a direct V0/V1/V2 field**
(task's own explicit "reuse the Manual Phasor input architecture instead
of inventing a separate sequence-entry model" instruction) — the
IDENTICAL six-role (Va/Vb/Vc/Ia/Ib/Ic), two-independent-basis
(`voltageBasis`+VT/PT ratio, `currentBasis`+CT ratio) Manual Phasor form
Phasor's own Manual mode already established, reusing `WW_PHASOR_
DIAGRAM_ROLE_ORDER` and the identical field-id-construction convention
(`wwSequenceManual` + roleKey + `Enabled`/`Magnitude`/`Unit`/`Angle`).
Backend: `evaluate_manual_phasor_role()`/`convert_manual_magnitude_to_
secondary()` (both `app.domain.phasor`) are reused **verbatim**, per
role — the SAME Manual Phasor normalization, never a duplicated
conversion formula. A sequence-component transform mathematically
requires the full phase-domain set, so even though the task's own
governing invariant permits a partial entry, `_evaluate_family()`'s
complete-set guardrail applies identically to Manual as to Recording.

Since `evaluate_manual_phasor_role()` returns a `PhasorDiagramRoleResult`
— the identical shape `compute_phasor_diagram()`'s own `roles` dict
already uses — Manual mode's six per-role evaluations feed into the
exact SAME `_evaluate_family()` helper Recording mode uses. This is the
one authoritative symmetrical-component implementation for both input
sources (task's own section 21 requirement) — there is no second,
Manual-only transform anywhere.

## Sequence visibility

Per-role (`V1`/`V2`/`V0`/`I1`/`I2`/`I0`) visibility is a pure frontend
display preference (`wwSequenceState.visibleRoles`), reusing the EXACT
row-as-toggle-button convention Phasor's own Values list already
established (itself reused from `#channelGroups`' own channel-visibility
rows) — clicking a role's own row hides/shows it with a cheap local
re-render only, never a new backend request, and never changes a
calculated value (task's own explicit "visibility must not change
calculated results" instruction). Default: every role that computes
`available` starts visible on its first appearance; a toggle-off
persists across re-renders (auto-seed only sets `true` the FIRST time a
role is seen, mirroring Phasor's own precedent exactly).

**Visibility/scale interaction — the documented rule (closure-pass
audit, 2026-09-18):** hiding a role does NOT recompute or shrink the
family's own graphical scale. `wwSequenceFamilyMaxMagnitude()` derives
the scale from every `available` role in the family regardless of its
own `visibleRoles` entry — identical to `wwPhasorFamilyMaxMagnitude()`'s
own precedent (Phasor's diagram has the exact same property). Hiding
the dominant V1 therefore never changes V2/V0's own rendered position —
only V1's own shaft/arrowhead/label disappear; the plot's own scale
stays exactly as it was. This is intentional, not an oversight: visibly
hiding a role is a display preference for THAT role only, never a
request to re-derive the whole family's scale from whatever remains
visible (which would make every other vector's own apparent size shift
merely because an unrelated role was toggled — a more confusing
behavior than the current one). Guarded by
`browser-tests/sequence_components_analysis.spec.js`'s own "visibility/
scale isolation rule" suite.

## Related Waveforms shows source phase quantities, never sequence values

Task's own section 15: Recording mode pushes the SOURCE Va/Vb/Vc/Ia/Ib/
Ic quantities the sequence transform was derived from — never V0/V1/V2/
I0/I1/I2 themselves, which have no waveform/time series of their own.
`wwSequenceComputeActiveRelatedWaveformRoles()` reads channel identity
straight from each family's own `phase_a/b/c_channel_ref` (never
re-derived from a channel name), pushing a role only when its own
`channelRef` is known — regardless of whether the sequence transform
itself succeeded, so the underlying waveforms stay visible even when a
family reports `needs_configuration`/`missing`. Manual mode declares
zero active roles (a manually-entered value structurally never has a
waveform) — double-enforced by the Recording-only anchor's own parent
container being hidden in Manual mode, mirroring every other analyzer's
identical defense-in-depth.

## Playback

Recording mode mounts the SAME reusable Playback control surface
(`wwCreatePlaybackControlsHtml()`/`wwWirePlaybackControls()`/
`wwSyncPlaybackControls()`/`wwUpdatePlaybackControlsTick()`) every other
analyzer mounts — Sequence Components is the FOURTH consumer of the ONE
shared `wwPlayback` controller (DEC-085). `wwSequenceOnPlaybackTick()`
mirrors `wwPhasorOnPlaybackTick()`'s/`wwImpedanceOnPlaybackTick()`'s own
exact shape: gates on `wwSequenceState.activeTimeGroupId`/`isOurGroup`,
syncs the mounted transport UI regardless of input source, but only
drives the `/sequence-components` fetch pipeline while Recording is
active — Manual mode's own vectors stay completely stable while Playback
moves elsewhere (mirrors every prior analyzer's identical Manual/
Playback isolation). Throttled (~10 Hz,
`WW_SEQUENCE_PLAYBACK_THROTTLE_MS = 100`) while playing, exact
(non-throttled) convergence on Pause/Restart/seek-commit/a context's own
initial claim — the identical "one request in flight + latest desired
time, never a growing queue" pattern every prior analyzer already
established. No analyzer-specific timer exists anywhere in this feature.

## API

```text
GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/sequence-components
    ?analysis_time=1.5
    &reference_frequency_hz=50.0        (optional override)

GET /api/v1/workspaces/{workspace_id}/sequence-components-manual
    ?voltage_basis=secondary&current_basis=secondary
    &vt_primary=...&vt_secondary=...    (only when voltage_basis=primary)
    &ct_primary=...&ct_secondary=...    (only when current_basis=primary)
    &va_enabled=true&va_magnitude=100&va_unit=V&va_angle_deg=0
    &vb_enabled=true&vb_magnitude=100&vb_unit=V&vb_angle_deg=-120
    &vc_enabled=true&vc_magnitude=100&vc_unit=V&vc_angle_deg=120
    &ia_enabled=...&ib_enabled=...&ic_enabled=...   (identical shape, Current)
```

Both defined in `app/api/v1/engineering_contexts.py` (same router file/
nesting convention every prior analyzer's own endpoints already
established) — the context-nested endpoint mirrors `.../impedance`/
`.../phasor-diagram`; the workspace-scoped manual endpoint mirrors
`.../impedance-manual`/`.../phasor-manual` exactly, including the
per-role `{prefix}_enabled`/`_magnitude`/`_unit`/`_angle_deg` query-
parameter shape.

## Response shape

```text
SequenceAnalysisResultOut / SequenceManualResultOut
├── status                    "computed" | "needs_configuration"  (whole-result; a
│                              genuine cross-role BLOCKING condition only —
│                              reference-frequency conflict, timebase
│                              incompatibility, surfaced verbatim from
│                              compute_phasor_diagram() for Recording)
├── (Recording only) engineering_context_id, analysis_time,
│   reference_frequency_hz, window_seconds
├── algorithm_version          "sequence_components_v1" | "sequence_components_manual_v1"
├── voltage_sequences: SequenceFamilyResultOut
│     ├── status               computed | needs_configuration | missing | ambiguous | not_eligible
│     ├── zero_sequence_magnitude / zero_sequence_angle_deg
│     ├── positive_sequence_magnitude / positive_sequence_angle_deg
│     ├── negative_sequence_magnitude / negative_sequence_angle_deg
│     ├── negative_sequence_ratio_percent / zero_sequence_ratio_percent   (nullable)
│     ├── unit
│     ├── phase_a_channel_ref / phase_b_channel_ref / phase_c_channel_ref  (Recording only, nullable)
│     └── reason_code, message
├── current_sequences: SequenceFamilyResultOut     (identical shape)
├── warnings[]
├── reason_code, message
```

`SequenceManualResultOut` omits `engineering_context_id`/`analysis_time`/
`reference_frequency_hz`/`window_seconds` (mirrors `ManualImpedanceResultOut`'s
own field-omission rationale — none of those concepts exist for a
standalone manually-entered phasor set).

## Frontend — Input Source shell reuse

`wwSequenceState` mirrors `wwPhasorState`'s own shape closely
(`contexts`/`selectedContextId`/`lastLoadedContextId`/`analysisTime`/
`anchorDisplaySourceId`/`activeTimeGroupId`/`latestResult`/
`visibleRoles`/`frozenVoltageScale`/`frozenCurrentScale`/
`requestGeneration`/`inputSource`/`recordingAvailable`/
`inputSourceAutoSelected`/`manualRequestGeneration`/`manual`). Every
generic (Phasor-state-free) helper is reused verbatim rather than
duplicated: `wwPhasorFetchJson()`, `wwPhasorAnchorDisplaySourceIdForContext()`,
`wwPhasorComputeInitialClaimTime()`, `wwPhasorVectorSvg()`,
`wwPhasorReasonText()`, `wwPhasorRoleStatusLabel()`,
`wwPhasorFormatAngle()`, `wwPhasorRoleColor()` (for the source Va/Vb/Vc/
Ia/Ib/Ic Related-Waveforms roles specifically — sequence-role coloring
uses the new, separate `wwSequenceRoleColor()`). Registers as an
Engineering Context consumer (`wwAnalysisRegisterContextConsumer({
onContexts: wwSequenceOnAnalysisContexts, ... })`) and a Playback tick
subscriber (`wwPlaybackOnTick(wwSequenceOnPlaybackTick)`) in the Init
wiring section, alongside every other analyzer — never its own
`wwSequenceLoadContexts()`/`wwSequenceDiscoverUncoveredSources()`
bootstrap (the exact architectural rule
`test_frontend_phasor_analysis.py::TestSharedAnalysisContextConsumers`
exists to catch).

## Remaining limitations — legitimate future enhancements only, zero open bugs/debt

As of the 2026-09-18 closure pass, every item below is a **future
product-scope enhancement**, never an unresolved bug or debt item — see
"Closure-pass audit summary" above for the audit that confirmed this.
None of these are silently-deferred defects; each is a permanent scope
boundary or a genuinely separate future feature that would need its own
owner approval to start.

- No unbalance-limit/negative-sequence-protection/ground-fault/fault-
  classification interpretation (see "Scope of v1" above — this is a
  **permanent** boundary for this feature, not a temporary gap).
- No sequence-network diagrams, no sequence impedance (Z1/Z2/Z0) —
  future enhancement, would consume V0/V1/V2/I0/I1/I2 as its own input,
  never coupled into this module.
- No automatic cross-source Engineering Context merging, no manual
  Engineering Context creation/editing UI (unchanged, project-wide
  deferrals every prior analyzer also inherits — not Sequence-specific).
- No Per-Unit display mode (engineering units only, matching Phasor
  Slice 1's own original scope) — future enhancement.
- No time-series/locus visualization for sequence values (unlike
  Impedance Locus's own R-X trajectory) — the v1 scope is a
  selected-time snapshot, following Phasor's own original shape rather
  than Impedance's newer locus-sampling one; a future slice could add
  this without changing the domain/service layer — future enhancement,
  not a defect in the current snapshot-only behavior.
- Ratio magnitude is deliberately never capped (see "Sequence ratios"
  above) — a documented design choice, not a limitation to fix.

## Related documents

- [ANALYSIS_INPUT_SOURCE.md](ANALYSIS_INPUT_SOURCE.md) — the shared
  Recording/Manual shell this reuses.
- [ANALYSIS_WORKSPACE.md](ANALYSIS_WORKSPACE.md) — the shared
  Engineering Context lifecycle / Playback / Related Waveforms
  primitives.
- [PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md) — the authoritative Phasor
  architecture (angle convention, diagram aggregation, Manual Phasor
  normalization) this feature builds directly on top of.
- [IMPEDANCE_LOCUS_ANALYSIS.md](IMPEDANCE_LOCUS_ANALYSIS.md) — the
  freshest prior analyzer, the direct structural template this feature
  mirrors (own domain/service/schema modules, endpoint nesting
  convention, Input Source shell implemented correctly from day one).
- [DECISIONS.md — DEC-097](DECISIONS.md#dec-097--sequence-components-v1-the-fourth-analysis-menu-analyzer-positivenegativezero-sequence-voltage-and-current-calculationvisualization)
  — the approval record.
