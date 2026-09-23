# Compliance & Capability

**Status: Slice 1 (workspace shell only) implemented 2026-09-19; Slice 2
(Measurement Selection + Normalization Foundation) implemented
2026-09-20; a same-day owner-UAT correction (Bay/Measurement Group
scoping) implemented 2026-09-20; a further owner-UAT correction (group
discovery/bootstrap) implemented 2026-09-23.** Reference profiles,
event alignment/t0, comparison curves, and compliance evaluation/
breach/margin logic still do not exist — see "Slice 2" below for
exactly what Measurement now does, "Bay/Measurement Group scoping
(2026-09-20 UAT correction)" for the corrected selection workflow,
"Bay/Measurement Group discovery/bootstrap (2026-09-23 UAT correction)"
for why groups now appear WITHOUT visiting another page first, and "No
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

**Superseded in part, same day, by owner UAT — see "Bay/Measurement
Group scoping (2026-09-20 UAT correction)" below.** Everything in this
section about the NORMALIZATION MATH (Instantaneous/RMS handling,
Phasor/Sequence Components reuse, line-line derivation, per-unit reuse)
is still exactly accurate and unchanged. What changed is the SCOPE role
resolution runs against: this section's own original text below still
describes resolution as "workspace-wide" (`resolve_voltage_role_
catalogue()`, since removed) — that is now stale; role resolution is
scoped to one explicitly selected Measurement Group
(`resolve_voltage_role_catalogue_for_group()`), never the whole
workspace. Kept here verbatim (rather than silently rewritten) as the
accurate historical record of what Slice 2 shipped before the
correction — do not treat the "workspace-wide" framing below as current
behavior.

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
*(Original Slice 2 text described "resolved roles spanning two
DIFFERENT Measurement Groups" as a `STATUS_INVALID_BASE` trigger — the
2026-09-20 Bay/Measurement Group UAT correction below makes this
structurally unreachable, since every resolved role is now, by
construction, a member of the one selected group.)*

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

New tests (original Slice 2 shape, since revised by the correction
below — file names are current, contents were substantially reworked):
`backend/tests/test_compliance_measurement_domain.py` (golden vectors —
balanced/unbalanced three-phase, RMS direct, 275 kV base reuse,
unsupported-representation guardrails, min/max — UNCHANGED by the
correction), `backend/tests/test_compliance_measurement_service.py`,
`backend/tests/test_compliance_measurement_api.py`, `backend/tests/
test_frontend_compliance.py`, and `browser-tests/compliance_
measurement.spec.js`.

## Bay/Measurement Group scoping (2026-09-20 UAT correction)

**Owner UAT identified a real workflow gap the same day Slice 2
shipped**: a bare Assessment Quantity selector is ambiguous the moment
a workspace contains more than one bay/Measurement Group, since several
valid `Va`/`Vb`/`Vab` etc. may exist across different bays — this is
not a naming conflict to resolve, it is a missing selection step. See
[DECISIONS.md — DEC-102](DECISIONS.md#dec-102--compliance-measurement-scopes-role-resolution-to-an-explicitly-selected-measurement-group-bay-reusing-the-existing-measurement-group-model-verbatim--never-a-second-bay-concept-never-engineering-context)
for the full architectural record.

**Corrected workflow:**

```text
1. Select Bay / Measurement Group
2. Select Assessment Quantity
3. Resolve only the channels within that selected bay/group
4. Normalize and assess (unchanged Slice 2 math, see above)
```

**Reuses the EXISTING `app.domain.measurement_group` model verbatim —
never a second, Compliance-specific bay concept** (task's own explicit
instruction). A new, lean, read-only, Compliance-only endpoint,
`GET .../compliance/voltage/measurement-groups`, lists every Voltage-
kind group in the workspace whose own grouping is not itself contested
(`status != needs_review`; `suggested`/`confirmed`/`manual` are all
included, mirroring the existing Measurement Groups configuration UI's
own "never hide suggested, just flag it" convention) — built by reusing
the already-existing `MeasurementGroupRegistry.list_for_workspace()`
(previously present at the service layer, not previously exposed
workspace-wide over REST). `GET .../compliance/voltage/measurement` now
REQUIRES an explicit `measurement_group_id` query parameter.

**Cross-bay role duplication is expected and is resolved by group
selection, not treated as a naming conflict.** Selecting Bay A and
resolving `Va` never looks at Bay B's own `Va` at all — `app.services.
compliance_measurement_service.resolve_voltage_role_catalogue_for_group()`
groups the SELECTED group's own `channel_refs` by `source_id` (a group
may legitimately span more than one loaded source — task section 11,
"do not assume one group == one file") and runs `app.domain.
engineering_context_detection.detect_engineering_contexts()` only
against those member channels, per represented source. The old
"Multiple channels match Va across the loaded recordings" wording no
longer exists. A duplicate `Va` genuinely WITHIN one selected group's
own membership (e.g. two differently-named member channels that both
parse to phase A) remains `STATUS_AMBIGUOUS_METADATA` — reworded
"...within the selected Measurement Group" to make the scope explicit.

**Auto-selection is exact, never a heuristic**: exactly one valid
Voltage group in the workspace auto-selects it; two or more require an
explicit choice; zero shows "No Measurement Group is available for this
workspace." — the group picker's own `stillExists`/auto-select logic
mirrors `wwPhasorRenderContextOptions()`'s established pattern
(preserve a still-valid selection across a reload; never silently
re-pick a different one).

**Switching a quantity that becomes invalid in the new group never
silently substitutes another quantity** — the select's own value is
preserved, and the summary simply reports `missing_inputs`/whatever
status genuinely applies in the new group (task section 8's own
explicit "keep selection → show Missing Inputs" requirement), verified
directly by a dedicated Playwright scenario.

**Base/Assessment Unit simplification**: because every resolved role is
now, by construction, a member of the ONE selected group,
`_base_for_group()` is a single `build_group_view()` lookup on that
group — the former "do resolved roles span two different groups"
conflict check (and its own `STATUS_INVALID_BASE` trigger) is
structurally unreachable through this path and was removed. The
`invalid_base` status constant itself remains defined for vocabulary
stability (task's own guardrail list); nothing currently triggers it.

**UI**: a new `#wwComplianceGroupField`/`#wwComplianceGroupSelect`
("Bay / Measurement Group" — the task's own specified wording, not yet
simplified to "Bay" since the existing model does not guarantee every
Measurement Group is a physical bay) sits ABOVE Assessment Quantity in
the same compact Measurement card, sharing the identical ID-scoped
containment fix (`#wwComplianceGroupField { min-width: 0; margin: 0 }`,
`#wwComplianceGroupSelect { width: 100%; max-width: 100%; min-width: 0;
box-sizing: border-box }`) the owner's own earlier CSS refinement
(commit `3447f24`) established for the Assessment Quantity select —
both selects stay contained at 1366/1024/800px, verified directly.
`wwComplianceRenderMeasurementCardState()` is the one function deciding
which of the four required empty states (no groups / select a group /
no quantity selected / real summary) is showing at any moment.

**Tests reworked**: `test_compliance_measurement_service.py` (17
tests: group-scoped resolution, cross-bay duplication is NOT ambiguous,
same-group duplication IS still ambiguous, group-controls-base,
group-controls-role-resolution, a group may span multiple sources),
`test_compliance_measurement_api.py` (11 tests: new group-list endpoint,
`measurement_group_id` required/404/wrong-kind), `test_frontend_
compliance.py`'s new `TestComplianceMeasurementGroupSelectorStructure`
class (6 tests), and a substantially reworked `browser-tests/
compliance_measurement.spec.js` (18 scenarios: one-group auto-select,
two-groups-duplicate-Va before/after selection, group-specific missing
phase with kept quantity selection, full group-switch summary update,
responsive containment of BOTH selects). `test_compliance_measurement_
domain.py`'s 13 golden tests are completely unchanged (normalization
math was explicitly out of scope for this correction). Full backend
suite (5480 tests) and full Playwright suite (151 scenarios) pass.

## Bay/Measurement Group discovery/bootstrap (2026-09-23 UAT correction)

**Owner UAT found a further, real workflow gap the same feature area
had inherited rather than introduced**: a workspace containing obvious
multi-bay Voltage channel sets (e.g. `KPDN1`, `KPDN2`, `SLKS`, `MCRS`,
`SGT1`, each with a full A/B/C or R/Y/B triplet visible in the
recording/channel list) still showed "No Measurement Group is available
for this workspace." on Compliance. See
[DECISIONS.md — DEC-103](DECISIONS.md#dec-103--compliances-baymeasurement-group-picker-automatically-bootstraps-the-existing-measurement-group-detection-for-every-loaded-source-mirroring-the-analysis-workspaces-own-proven-engineering-context-bootstrap)
for the full architectural record.

**Exact root cause (confirmed by direct reproduction, not assumed):
`app.services.measurement_group_service.generate_suggested_groups_
for_source()` — the ONE function that ever creates a `MeasurementGroup`
from automatic detection — has never had ANY automatic trigger anywhere
in this codebase.** Its own docstring already said so: *"No automatic
trigger exists for this function... wiring it into an existing
endpoint's behaviour is deferred to whichever later slice first needs
the result to be observable."* Before this correction, a `MeasurementGroup`
was only ever created by (a) an engineer manually creating one, or (b)
an engineer opening "Manage Measurement Groups" (via Per-Unit Settings)
and explicitly clicking "Suggest" for one source at a time. A workspace
where the engineer had done neither had a genuinely empty
`MeasurementGroupRegistry`, no matter how obviously multi-bay the
recording's own channel list was. Compliance's own group-list endpoint
and Voltage-kind filtering were already correct — there was simply
nothing in the registry yet to list. This is classified as root cause
**A (groups were never materialized/registered)** combined with **E
(Compliance had no bootstrap of its own to compensate)** from this
task's own classification scheme.

**Fix: Compliance is the "later slice" the existing function's own
docstring anticipated.** `wwComplianceLoadGroups()` now calls the
EXISTING, unchanged `POST .../sources/{source_id}/measurement-groups/
suggest` endpoint for every currently loaded source not yet attempted
this session, BEFORE listing groups — mirroring the Analysis
workspace's own already-proven `wwAnalysisDiscoverUncoveredSources()`
bootstrap for Engineering Context, applied to Measurement Group
instead. Safe because `generate_suggested_groups_for_source()` is
already idempotent/additive-only (skips a cluster entirely if even one
of its channels already belongs to any existing group). **No new
detection algorithm was written** — `app.domain.measurement_group_
detection.detect_measurement_groups()` is completely unchanged; this
was purely a missing CALLER, not a missing engine.

**A second, related gap fixed the same day: `GET .../compliance/
voltage/measurement-groups` used to exclude `needs_review` groups
entirely**, which meant a workspace with genuinely discovered-but-
uncertain groups looked byte-for-byte identical to a truly empty one.
The endpoint now returns EVERY Voltage-kind group of any status; the
frontend buckets the response into `wwComplianceUsableGroups()`
(`status !== "needs_review"`, selectable) and `wwComplianceReviewRequiredGroups()`
(`status === "needs_review"`, surfaced via a distinct message) --
`app.domain.measurement_group`'s own canonical "a channel in a
`needs_review` group behaves like unconfigured until reviewed"
guardrail is preserved exactly (a `needs_review` group is STILL never
selectable in the dropdown and never silently trusted for role
resolution). The Measurement card now distinguishes three states:

| State | Message | Action |
|---|---|---|
| No groups discovered at all | "No Voltage Measurement Group is available for this workspace." | "Manage Measurement Groups" |
| Groups discovered, all need review | "Voltage Measurement Groups were found, but they require review before use." | "Review Measurement Groups" |
| At least one usable group | (normal Bay selector flow) | — |

**A "Manage/Review Measurement Groups" action was added directly to the
Measurement card's own empty states, reusing the EXISTING Measurement
Groups management modal verbatim (`wwOpenMeasurementGroupsModal()`) —
no new editor was built inside Compliance** (task's own explicit "Do
not duplicate management controls inside Compliance" instruction).
Because that modal is an overlay, not a page navigation, Compliance's
own state is never disturbed underneath it; `wwCloseMeasurementGroupsModal()`
gained one additional line refreshing Compliance's own group list only
when Compliance happens to be the current page, so a group confirmed/
edited via the modal is immediately reflected the moment it closes,
with no manual reload needed.

**Backend changes are minimal**: `app.services.compliance_measurement_
service.list_compliance_voltage_groups()` no longer filters by status
(now returns every Voltage-kind group); `app.api.v1.compliance.py`
docstrings updated to match. `ComplianceMeasurementGroupOut` already
carried a `status` field, so the response SHAPE is unchanged — only
which rows are included changed. Zero changes to `app.domain.
measurement_group_detection`, `app.services.measurement_group_service`,
`app.services.measurement_group_registry`, or any existing Measurement
Groups endpoint/UI.

**New tests**: `test_compliance_measurement_api.py` gained a
`TestMeasurementGroupBootstrapDiscovery` class (4 tests: group list
reflects authoritative registry state after bootstrap, review-required
groups are distinguishable from no groups, bootstrap is idempotent,
multi-source groups remain independently valid) plus one test proving
`needs_review` groups are now included in the raw list response;
`test_frontend_compliance.py` gained a `TestComplianceMeasurementGroupBootstrapAndReviewState`
class (6 tests: bootstrap reuses the existing suggest endpoint with no
client-side name parsing/fabrication of any kind, `wwComplianceLoadGroups()`
bootstraps before listing, usable/review-required are distinct
collections, the card state distinguishes the two empty states, the
Manage button reuses the existing modal, closing the modal refreshes
Compliance only when active). `browser-tests/compliance_measurement.spec.js`
gained a `test.describe` block (6 real-browser scenarios: direct-to-
Compliance multi-bay discovery with no prior visit to Manage
Measurement Groups, re-visiting never duplicates groups, the
review-required empty state and its action, the Manage action's
open/return-intact behavior, and reviewing-then-confirming a group
moving it from review-required to usable on return) using two new
committed ASCII COMTRADE fixtures (`compliance_smoke_multibay`: four
clean bays verified directly against `detect_measurement_groups()` to
produce four independent `suggested` groups with zero manual
intervention; `compliance_smoke_review_required`: one bay with
deliberately mixed single+pair phase representation, verified directly
to produce `needs_review`). Full backend suite (5491 tests) and full
Playwright suite (156 scenarios) pass.

## Shared post-upload workspace preparation supersedes Compliance's own bootstrap trigger point (2026-09-23, DEC-104)

**The bootstrap described in the section above was, and remains, a
correct fix for Compliance's own independence — but the owner's next
round of UAT generalized the requirement application-wide**: *"Once an
event file is uploaded successfully, every function that can operate on
that file should be ready to use independently. No function should
require the user to first open Waveform, Analysis, Manage Measurement
Groups, or any other page merely to trigger hidden preparation/bootstrap
work."* See
[DECISIONS.md — DEC-104](DECISIONS.md#dec-104--successful-source-upload-triggers-shared-workspacesource-preparation-measurement-group--engineering-context-discovery-no-top-level-function-may-depend-on-another-page-having-been-opened-first)
for the full architectural record.

**Measurement Group discovery is now triggered from the backend, at
upload time, for every source** — `app.services.workspace_preparation_
service.prepare_workspace_source()` runs the EXACT SAME `generate_
suggested_groups_for_source()` this page's own bootstrap calls, but
immediately after `WorkspaceRegistry.add()` succeeds in `app.api.v1.
sources.upload_comtrade_source()` / `app.api.v1.preparation_sources.
post_convert_preparation_source()`, rather than waiting for Compliance
(or any page) to open. By the time an engineer opens Compliance after a
fresh upload, the Bay/Measurement Group selector is normally ALREADY
populated — no page-owned discovery step runs at all on the common path.

**`wwComplianceBootstrapGroupsIfNeeded()` is KEPT, not removed, but is
now fallback-only.** It still runs on every `wwComplianceLoadGroups()`
call, but normally finds nothing left to do (every loaded source already
covered, or `/suggest` returning nothing new) and completes as a cheap
no-op. It remains as defense-in-depth for a group deleted after upload,
or a workspace whose sources were registered before DEC-104 existed.
Compliance's own readiness — the bay selector being populated the moment
the page opens, with zero prior page visits of any kind, not even to
"Manage Measurement Groups" — is now guaranteed by the backend, not by
this frontend function; the direct-upload-to-Compliance acceptance
scenario (`browser-tests/post_upload_readiness.spec.js`) verifies this
without seeding any group state and without relying on this bootstrap
having anything to discover.

**Nothing else in this document changes.** DEC-100/DEC-101/DEC-102's own
guardrails (Compliance is not an Engineering Context consumer, role
resolution is scoped to an explicitly selected Measurement Group, a
`needs_review` group is never silently trusted) are all fully preserved
— this is purely a change in WHEN discovery runs, not what it discovers
or how Compliance uses the result.

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
  `#pageCompliance` (page markup, including the Bay/Measurement Group
  select above the Assessment Quantity select, the summary, and
  `#wwComplianceManageGroupsBtn`), `shellSetCurrentPage()` (page
  lifecycle), `wwRenderCompliancePage()`/`wwComplianceSyncTypeNav()`/
  `wwComplianceLoadQuantities()`/`wwComplianceLoadGroups()`/
  `wwComplianceBootstrapGroupsIfNeeded()`/`wwComplianceSuggestGroupsForSource()`/
  `wwComplianceUsableGroups()`/`wwComplianceReviewRequiredGroups()`/
  `wwComplianceRenderGroupOptions()`/`wwComplianceOnGroupChange()`/
  `wwComplianceOnQuantityChange()`/`wwComplianceRenderMeasurementCardState()`/
  `wwComplianceOpenManageGroups()`/`wwComplianceFetchMeasurement()`/
  `wwComplianceRenderMeasurement()` (JS, plus one added line in the
  pre-existing `wwCloseMeasurementGroupsModal()`), `.ww-compliance-*`
  CSS (including `#wwComplianceGroupField`/`#wwComplianceGroupSelect`'s
  own ID-scoped containment fix).
- `backend/app/domain/compliance_measurement.py` — quantity catalogue +
  pure `compute_voltage_quantity_value()` (unchanged by either
  correction).
- `backend/app/services/compliance_measurement_service.py` — group-
  scoped role resolution (`resolve_voltage_role_catalogue_for_group()`,
  reuses `engineering_context_detection` directly, see DEC-101/DEC-102),
  the Bay/Measurement Group candidate list (`list_compliance_voltage_
  groups()`, now unfiltered by status per DEC-103), Instantaneous/RMS
  classification, group-scoped Base lookup (`_base_for_group()`).
- `backend/app/schemas/compliance.py`, `backend/app/api/v1/compliance.py`
  — the three workspace-scoped endpoints (quantities, measurement-groups,
  measurement); response shapes unchanged by DEC-103, only which rows
  the group-list endpoint includes.
- `backend/app/services/errors.py` — `UnknownComplianceQuantityError`,
  `ComplianceMeasurementGroupNotVoltageKindError` (reuses the existing
  `MeasurementGroupNotFoundError` for an unknown group id).
- `backend/tests/test_frontend_compliance.py` — structural regression
  (nav registration/order, panel existence, Voltage sub-nav, the five
  section identifiers in order, empty-state wording, Slice 1/Slice 2/
  correction out-of-scope guards, `TestComplianceMeasurementGroupSelectorStructure`,
  `TestComplianceMeasurementGroupBootstrapAndReviewState`).
- `backend/tests/test_compliance_measurement_domain.py` (unchanged by
  either correction) / `test_compliance_measurement_service.py` /
  `test_compliance_measurement_api.py` (the latter gained a
  `TestMeasurementGroupBootstrapDiscovery` class) — golden vectors,
  eligibility/guardrail matrix, HTTP wiring.
- `backend/tests/fixtures/comtrade/compliance_smoke_multibay(.cfg/.dat)`,
  `compliance_smoke_review_required(.cfg/.dat)` — new fixtures for the
  2026-09-23 correction (see above for what each represents).
- `browser-tests/compliance.spec.js` — Slice 1 real-browser coverage
  (menu order, page open/close, sub-nav, all five sections, chart
  dominance, navigation lifecycle/isolation from Analysis, responsive/
  no-overflow checks; its own former "Measurement select stays
  contained" scenario moved to `compliance_measurement.spec.js`, since
  the select is conditionally hidden on this file's own always-empty
  workspace).
- `browser-tests/compliance_measurement.spec.js` — Bay/Measurement
  Group + Assessment Quantity real-browser coverage (one-group auto-
  select, two-groups-duplicate-Va, group-specific missing phase, group
  switching, Instantaneous/RMS summaries, Base metadata, both selects'
  responsive containment, Analysis/Playback isolation, PLUS the
  2026-09-23 bootstrap/discovery/review-required/Manage-action scenarios),
  using four committed ASCII COMTRADE fixtures under `backend/tests/
  fixtures/comtrade/`.

## Related documents

- [DECISIONS.md](DECISIONS.md) — DEC-100 (top-level/independent-from-
  Analysis architectural decision),
  [DEC-101](DECISIONS.md#dec-101--compliance-slice-2-resolves-voltage-phase-roles-by-independently-re-running-the-engineering-context-detection-algorithm-never-by-becoming-an-engineering-context-consumer)
  (Engineering-Context-detection-algorithm-reuse-without-consumer-
  registration boundary),
  [DEC-102](DECISIONS.md#dec-102--compliance-measurement-scopes-role-resolution-to-an-explicitly-selected-measurement-group-bay-reusing-the-existing-measurement-group-model-verbatim--never-a-second-bay-concept-never-engineering-context)
  (the 2026-09-20 Bay/Measurement Group scoping correction), and
  [DEC-103](DECISIONS.md#dec-103--compliances-baymeasurement-group-picker-automatically-bootstraps-the-existing-measurement-group-detection-for-every-loaded-source-mirroring-the-analysis-workspaces-own-proven-engineering-context-bootstrap)
  (the 2026-09-23 group discovery/bootstrap correction), and
  [DEC-104](DECISIONS.md#dec-104--successful-source-upload-triggers-shared-workspacesource-preparation-measurement-group--engineering-context-discovery-no-top-level-function-may-depend-on-another-page-having-been-opened-first)
  (the same-day generalization moving discovery to a shared backend
  post-upload choke point, with DEC-103's own bootstrap kept as
  fallback-only).
- [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) — the
  group-aware Per-Unit/Measurement Group model this feature's Bay
  picker and Base display both reuse verbatim.
- [CURRENT_STATE.md](CURRENT_STATE.md), [HANDOFF.md](HANDOFF.md).
