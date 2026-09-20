# Compliance & Capability

**Status: Slice 1 (workspace shell only) implemented 2026-09-19; Slice 2
(Measurement Selection + Normalization Foundation) implemented
2026-09-20.** Reference profiles, event alignment/t0, comparison curves,
and compliance evaluation/breach/margin logic still do not exist — see
"Slice 2" below for exactly what Measurement now does, and "No
calculation/profile/persistence logic exists yet" for what still
doesn't.

## Compliance is a top-level function, independent of Analysis

`Compliance` is its own first-class application page (`shell.currentPage
=== "compliance"`, `#pageCompliance`), reached from its own main-sidebar
entry — **not** another Analysis-menu analyzer. It does not register as
an Engineering Context consumer, does not mount the shared Playback
control surface, has no Analysis Input Source (Recording/Manual), and
carries no analyzer-specific state of any kind (no Phasor/Overcurrent/
Impedance/Sequence/Distance coupling). Opening Compliance does not
initialize, reset, or alter Playback, Analysis Input Source, Engineering
Context analyzer state, Sequence state, or Distance state — verified
directly (`browser-tests/compliance.spec.js`, "opening Compliance does
not touch Playback, Analysis Input Source, or any analyzer state").

Why independent rather than a sixth analyzer: compliance/capability
assessment is a genuinely different engineering question from the
existing Analysis-menu family (Phasor/Overcurrent/Impedance/Sequence/
Distance all answer "what did this event's signals actually do,"
Compliance answers "does a measured quantity satisfy an external
requirement/capability curve") and does not naturally share the
Analysis shell's own Engineering Context/Playback/Related-Waveforms
infrastructure (Compliance's own Event Alignment step, for one, is
expected to need a DIFFERENT, standalone time-reference model, not the
shared workspace clock every Analysis analyzer already consumes). Kept
as its own top-level page rather than forcing an awkward fit into the
existing shared shell.

Final main-menu order (implemented):

```text
Recordings
Waveform
Table
Calculated Channels
Analysis
Compliance
```

## Slice 1 supports only the Voltage workspace shell

```text
Compliance
└── Voltage
```

One Compliance function exists today (`wwComplianceActiveType ===
"voltage"`, `#wwComplianceTypeVoltageBtn`), reusing the exact
`.ww-analysis-type-nav`/`.ww-analysis-type-item` sub-nav component the
Analysis page already established (same visual language — task's own
explicit "do not introduce a separate visual design language"
instruction) so a future second function (e.g. Current) slots in the
same way a sixth analyzer would. The page heading currently reads
**"Voltage Compliance & Capability"** — intentionally provisional
wording, explicitly subject to change through owner UAT.

## Current workflow hypothesis

```text
Measurement
→ Reference Layers
→ Event Alignment
→ Comparison Chart
→ Results
```

Rendered top-to-bottom so the intended engineering workflow reads
directly off the screen without needing an explanation: Measurement/
Reference Layers/Event Alignment are three short, compact configuration
cards side by side (`.ww-compliance-config-row`), followed by the
Comparison Chart (`.ww-compliance-chart-panel`, deliberately the
single largest section on the page — sized via `aspect-ratio: 16/7`
with `min-height: 320px`/`max-height: 520px`, never a tiny fixed
height), followed by Results.

Every section shows a neutral empty state only — no fabricated
engineering values, no fake LVRT/HVRT curves, no fabricated
Compliant/Boundary Breached/Within Capability verdict:

| Section | Empty state |
|---|---|
| Measurement | "No assessment quantity selected" |
| Reference Layers | "No reference layers added" |
| Event Alignment | "No event reference set" |
| Comparison Chart | "No voltage assessment configured" |
| Results | "Results will appear after a measurement, reference layer and event alignment are configured." |

A few controls exist as visibly **disabled** placeholders purely for
layout UAT (task's own explicit allowance) — a "+ Add Reference" button
and Shift-left/t0/Shift-right alignment buttons — none of them wired to
any real behavior. **The "Assessment quantity" select is no longer one
of these placeholders as of Slice 2** — see below.

## Slice 2 — Measurement Selection + Normalization Foundation (2026-09-20)

Implements **only** the Measurement section and the underlying
normalization foundation. Reference Layers, Event Alignment, Comparison
Chart, and Results remain exactly the Slice 1 placeholders described
above.

**The user chooses the assessment quantity first** (owner decision) —
there is no reference-profile-driven quantity selection, and nothing in
this slice can silently change the engineer's own selection. The fixed
v1 Voltage catalogue (`app.domain.compliance_measurement.VOLTAGE_
QUANTITIES`, the ONE source of truth — never duplicated as static
frontend HTML) is:

```text
Phase A Voltage            phase_a_lg_rms
Phase B Voltage            phase_b_lg_rms
Phase C Voltage            phase_c_lg_rms
Line-Line AB Voltage       phase_ab_ll_rms
Line-Line BC Voltage       phase_bc_ll_rms
Line-Line CA Voltage       phase_ca_ll_rms
Minimum Three-Phase Voltage  min_phase_lg_rms
Maximum Three-Phase Voltage  max_phase_lg_rms
Positive Sequence Voltage  positive_sequence_rms
```

**Channel/phase resolution reuses the Engineering Context Detection
ALGORITHM directly (`app.domain.engineering_context_detection.detect_
engineering_contexts()`), never the Engineering Context FEATURE.**
Compliance still does not register as an Engineering Context consumer
(DEC-100, unchanged) — no Bay selector, no `wwAnalysisRegisterContextConsumer()`,
no Playback, no Analysis Input Source. `app.services.compliance_
measurement_service.resolve_voltage_role_catalogue()` calls the pure
detection function directly (call-by-value, no `EngineeringContext`
object ever created/read/persisted), per loaded source, and flattens
every detected member's phase into one workspace-wide `phase -> channel`
map. See [DECISIONS.md — DEC-101](DECISIONS.md#dec-101--compliance-slice-2-resolves-voltage-phase-roles-by-independently-re-running-the-engineering-context-detection-algorithm-never-by-becoming-an-engineering-context-consumer)
for the full architectural record of this distinction.

**Instantaneous vs RMS is read from authoritative metadata, never
guessed from a channel name** (task section 4). Reuses the EXACT
metadata-first/detector-fallback hierarchy `app.services.calculated_
channel_service.check_rms_eligibility()`/`phasor_analysis_service.
_waveform_form_eligible()` already established: a channel's own trusted
`AnalogChannelSummary.waveform_form` wins outright when set; otherwise
`app.domain.rms_detector.classify_waveform_form()` runs against the
channel's own full sample array. An `UNCERTAIN` detector verdict, or
resolved roles that disagree with each other (one Instantaneous, one
RMS), is `STATUS_AMBIGUOUS_METADATA` — never a guess.

**Normalization order** (task section 12, all pure/no I/O in
`app.domain.compliance_measurement.compute_voltage_quantity_value()`):
raw recording → engineering units → RMS/fundamental representation →
required phase/line-line/sequence quantity → per-unit conversion (later,
via the SAME unchanged `app.domain.per_unit`/`app.domain.voltage_group_
config`, never a second Compliance-specific base model).

- **Instantaneous input** → `app.domain.phasor.estimate_phasor()` (the
  SAME Phasor Slice 1 estimator, never a second DFT/RMS engine) →
  fundamental RMS magnitude + angle.
- **Already-RMS input** → used directly; "Derived As" reads "Direct RMS
  (Source-defined / unspecified)" — never claimed to be a fundamental-
  frequency estimate, since the recording's own RMS method is unknown.
- **Line-line, no direct Vab/Vbc/Vca channel available** → derived ONLY
  from two genuine complex phase phasors, `Vab = Va - Vb` — **never
  `VLL = sqrt(3) * VLN`** (task section 8's own explicit disturbance-
  time prohibition; that shortcut assumes a balanced system, which a
  fault may violate). Requires BOTH phases to have angle information
  (i.e. both instantaneous) — an already-RMS, angle-less input is
  `STATUS_UNSUPPORTED_REPRESENTATION`, not a guess.
- **Line-line, a direct Vab/Vbc/Vca channel exists** → used verbatim,
  never re-derived from the individual phases even when they also
  resolve (task section 11 — preserve actual measurement identity).
- **Positive Sequence** → requires genuine complex phasors for A/B/C
  (same angle requirement as line-line derivation), then
  `app.domain.sequence_components.compute_symmetrical_components()` —
  the SAME Sequence Components domain function, never a second
  Fortescue transform.
- **Minimum/Maximum Three-Phase Voltage** → `min()`/`max()` of the three
  resolved phase RMS magnitudes (no domain function needed for this
  trivial comparison).

**Single-phase recordings are valid where the quantity permits it, with
no balanced-system assumption** (task section 9) — `Va` alone resolves
Phase A Voltage but leaves Positive Sequence/every three-phase quantity
`STATUS_MISSING_INPUTS`, with the exact missing channels named (e.g.
"Missing: Vb, Vc.").

**The live "switch assessment quantity" endpoint never actually computes
a value.** `app.services.compliance_measurement_service.evaluate_
voltage_measurement()` (backing `GET .../compliance/voltage/measurement`)
determines status/resolved-input-channels/Instantaneous-vs-RMS/"Derived
As"/Base entirely from channel-level METADATA — it never calls
`estimate_phasor()` or `compute_voltage_quantity_value()`. Reason:
Compliance has no selected-time/Playback concept yet (Event
Alignment/t0 is explicitly Slice 2 out-of-scope), so there is no
meaningful instant to evaluate a real number AT; the Measurement UI
itself never displays a computed value this slice either (matching the
task's own UI mock, which shows Status/Input/Input Type/Derived As/
Base/Unit but no numeric reading). `compute_voltage_quantity_value()`
and `estimate_phasor()`/`compute_symmetrical_components()` ARE fully
implemented and golden-tested directly
(`backend/tests/test_compliance_measurement_domain.py`) against
synthetic waveforms, proving the computation path correct and ready for
a later slice's actual selected-time wiring.

**Base/Assessment Unit reuse the existing group-aware Per-Unit model
verbatim (task section 7 — no second Compliance-specific base model).**
If every resolved role's channel belongs to the SAME Voltage Measurement
Group with a configured base, `app.services.measurement_group_view_
service.build_group_view()` supplies the nominal LL kV + effective
L-G/L-L reference, and Assessment Unit is `pu`. No group (or an
unconfigured one) is a normal, non-error state — Assessment Unit falls
back to the channel's own Engineering Units, never "Invalid Base".
Resolved roles spanning two DIFFERENT Measurement Groups (genuinely
incompatible bases) IS `STATUS_INVALID_BASE`.

**Guardrail vocabulary** (task section 16, `app.domain.compliance_
measurement`): `available`, `missing_inputs`, `ambiguous_measurement_
metadata`, `unsupported_representation`, `invalid_base` — each carries a
specific engineering-language message (e.g. "Positive Sequence Voltage
requires simultaneous complex phase phasors... already-RMS
magnitude-only, with no angle"), never a generic "Error".

**Backend**: two new, workspace-scoped (never Engineering-Context-
scoped), read-only endpoints in a dedicated router, `app/api/v1/
compliance.py` — `GET .../compliance/voltage/quantities` (the fixed
catalogue) and `GET .../compliance/voltage/measurement?quantity_id=...`
(eligibility + metadata). New domain module `app/domain/compliance_
measurement.py` (catalogue + pure value computation), new service
`app/services/compliance_measurement_service.py` (role resolution,
Instantaneous/RMS classification, Base lookup), new schemas `app/
schemas/compliance.py`. Zero changes to `app.domain.phasor`,
`app.domain.sequence_components`, `app.domain.per_unit`, `app.domain.
voltage_group_config`, `app.domain.engineering_context_detection`, or
any existing endpoint.

**Frontend**: the Measurement card's select is a real, backend-populated
dropdown (`wwComplianceLoadQuantities()`); selecting a quantity fetches
and renders a compact Status/Input/Input Type/Derived As/Base/Assessment
Unit summary (`wwComplianceFetchMeasurement()`/`wwComplianceRenderMeasurement()`,
`.ww-compliance-measurement-summary`/`.ww-compliance-measurement-row`,
reusing `.ww-phasor-status-row` verbatim for the Status line — no new
status-color system). Re-evaluates the selected quantity on every
Compliance page visit (the same "re-runs on every mere page revisit"
convention Phasor's own context loader already established), so a
source uploaded/removed elsewhere never leaves a stale result on
return.

New tests: `backend/tests/test_compliance_measurement_domain.py`
(golden vectors — balanced/unbalanced three-phase, RMS direct, 275 kV
base reuse, unsupported-representation guardrails, min/max), `backend/
tests/test_compliance_measurement_service.py` (role resolution/
eligibility/guardrail matrix against fake workspace fixtures), `backend/
tests/test_compliance_measurement_api.py` (HTTP wiring), `backend/
tests/test_frontend_compliance.py`'s new `TestComplianceMeasurementSlice2Structure`/
`TestComplianceOutOfScopeSlice2` classes, and `browser-tests/
compliance_measurement.spec.js` (14 real-browser scenarios: dropdown
catalogue, quantity switching, single-phase/three-phase cases,
Instantaneous/RMS summaries, Base metadata display, 1366/1024/800px
responsive, Analysis/Playback isolation) — two new committed ASCII
COMTRADE fixtures, `compliance_smoke_three_phase(.cfg/.dat)` (bare-role
VA/VB/VC, balanced 100 V RMS/50 Hz) and `compliance_smoke_rms_phase_a(.cfg/.dat)`
(a single VA channel with a smooth, always-positive envelope, verified
directly to trigger the real algorithmic RMS-detector fallback before
being committed, since COMTRADE never sets `waveform_form` metadata).

## UI/UX is intentionally subject to owner UAT and may change

Workflow order, section placement, chart prominence, terminology,
density, and spacing are all explicitly UAT-subject per the task that
built this slice — not treated as settled product decisions. No
DECISIONS.md architectural entry was needed for the layout/terminology
choices themselves (see below for the one architectural point that WAS
recorded).

## No calculation/profile/persistence logic exists yet

**As of Slice 2, instantaneous-to-RMS conversion, L-G/L-L normalization,
per-unit conversion (reused, not reimplemented), and positive-sequence
calculation ARE implemented** — see "Slice 2" above. Everything else
below remains explicitly out of scope, not implemented anywhere in this
codebase:

```text
Malaysian Grid Code profile
OEM profiles
profile JSON / profile import/export
t0 alignment logic
reference curves
multiple layer rendering
compliance evaluation / breach calculation / margin calculation / tolerance
database/storage
localStorage
```

Reference Layers/Event Alignment/Comparison Chart/Results are still
Slice 1's own static, no-op markup — `wwRenderCompliancePage()` now
does real work for Measurement only (`wwComplianceLoadQuantities()`/
re-evaluating the selected quantity), never for any other section.
`backend/tests/test_frontend_compliance.py`'s `TestComplianceOutOfScopeSlice1`
(profile/evaluation identifiers, no literal `/api/v1/compliance`
top-level prefix, no `localStorage`) and the new `TestComplianceOutOfScopeSlice2`
(Reference Layers/Event Alignment buttons still disabled, no alignment/
evaluation function names) both guard this boundary directly.

## Files

- `frontend/index.html` — `#mainNavComplianceBtn` (main sidebar),
  `#pageCompliance` (page markup, including the Slice 2 Measurement
  select/summary), `shellSetCurrentPage()` (page lifecycle),
  `wwRenderCompliancePage()`/`wwComplianceSyncTypeNav()`/
  `wwComplianceLoadQuantities()`/`wwComplianceFetchMeasurement()`/
  `wwComplianceRenderMeasurement()` (JS), `.ww-compliance-*` CSS.
- `backend/app/domain/compliance_measurement.py` — quantity catalogue +
  pure `compute_voltage_quantity_value()`.
- `backend/app/services/compliance_measurement_service.py` — role
  resolution (reuses `engineering_context_detection` directly, see
  DEC-101), Instantaneous/RMS classification, Base lookup.
- `backend/app/schemas/compliance.py`, `backend/app/api/v1/compliance.py`
  — the two new workspace-scoped endpoints.
- `backend/tests/test_frontend_compliance.py` — structural regression
  (nav registration/order, panel existence, Voltage sub-nav, the five
  section identifiers in order, empty-state wording, Slice 1 + Slice 2
  out-of-scope guards, Slice 2 Measurement markup/JS structure).
- `backend/tests/test_compliance_measurement_domain.py`/
  `test_compliance_measurement_service.py`/`test_compliance_measurement_api.py`
  — golden vectors, eligibility/guardrail matrix, HTTP wiring.
- `browser-tests/compliance.spec.js` — Slice 1 real-browser coverage
  (menu order, page open/close, sub-nav, all five sections, chart
  dominance, navigation lifecycle/isolation from Analysis, responsive/
  no-overflow checks).
- `browser-tests/compliance_measurement.spec.js` — Slice 2 real-browser
  coverage (Assessment Quantity dropdown/switching, single-phase/
  three-phase cases, Instantaneous/RMS summaries, Base metadata,
  responsive, Analysis/Playback isolation), using two new committed
  ASCII COMTRADE fixtures under `backend/tests/fixtures/comtrade/`.

## Related documents

- [DECISIONS.md](DECISIONS.md) — DEC-100 (top-level/independent-from-
  Analysis architectural decision) and
  [DEC-101](DECISIONS.md#dec-101--compliance-slice-2-resolves-voltage-phase-roles-by-independently-re-running-the-engineering-context-detection-algorithm-never-by-becoming-an-engineering-context-consumer)
  (Slice 2's own Engineering-Context-detection-algorithm-reuse-without-
  consumer-registration boundary).
- [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) — the
  group-aware Per-Unit model Slice 2's own Base display reuses verbatim.
- [CURRENT_STATE.md](CURRENT_STATE.md), [HANDOFF.md](HANDOFF.md).
