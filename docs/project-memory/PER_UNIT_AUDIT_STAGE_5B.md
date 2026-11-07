# Per-Unit audit Stage 5B - calculated Current manual override

Work: 2026-11-03/04. Owner-approved implementation task, following Stage 5A
`e2427b652bafcb9e366cc84d79258e28c15dcc8b`, on
`feature/calculator-vi-phasors`. Fetched upstream: five ahead / zero behind.
**Stage 5B acceptance is met locally. Full backend: 11,315 passed / 320 skipped,
zero failures/errors. Final browser: 431/431 in 37 selected files, zero retries.
The owner-approved test-only maintenance is complete. No push, merge, deployment
or automatic final audit is included.**

## Result ownership and configuration lifecycle

A calculated Current result now owns an optional immutable configuration in its
existing workspace/calculated-id assignment record. It contains mode, positive
finite Current base in canonical SI amperes, independently declared base side,
and the accepted update timestamp. It contains no waveform arrays and no Source
Default pointer. Existing calculated identity and cleanup mechanisms are reused.

| Mode | Effective behavior |
|---|---|
| Automatic | Stage 5A live source-leaf resolution; no stored inherited denominator |
| Manual | This result's explicit base takes precedence, subject to live physical/unit/numerical validation |
| Unassigned | PU unavailable until an explicit subsequent selection; ENG remains available |

Absence of a result configuration preserves existing behavior. Manual and
Unassigned cannot be overwritten by the legacy auto recompute, including a
recompute that read Automatic before the engineer's save. Return to Automatic
is an explicit action; it clears the result-owned manual fields. Failed manual
validation preserves the entire previous assignment and timestamp.

The assignment registry publishes one complete replacement under its existing
lock. Configuration candidates are independent immutable objects. Publication
does not update any other registry/index/assignment. A removed lifetime record
cannot be recreated by a save finishing after calculated/workspace cleanup.
Calculated deletion, source cascade removal and workspace deletion release the
same record; no second configuration index needs synchronization.

The existing workspace is in memory (DEC-015). Modes survive browser reload and
reopening the same live workspace. They do not introduce server-restart
durability, a database, workspace serialization or a new persistence system.

## Physical references and numerical validation

Physical calculated arithmetic remains authoritative and unchanged. For the
reference example, 4199 A + 4199 A remains 8398 A in every configuration mode.
PU normalizes that physical result once. Original input values, Measurement
Groups, group statuses/membership/reverse indices, Source Defaults and linked
Voltage/Current configurations are not edited by this feature.

Manual normalization does not require the input normalization bases to agree or
even exist. It does require known compatible physical samples, supported Current
units/operations, available dependencies, required group confirmation, and a
representable result. A manual number never declares the samples' reference side.

| Contributing samples / manual base | Manual result eligibility |
|---|---|
| Primary / Primary | Candidate eligible regardless of differing/missing input base amounts |
| Secondary / Secondary in one established group/default authority | Candidate eligible with independently known sides |
| Secondary / Secondary across distinct authorities | Unavailable; shared secondary reference is not established |
| Primary / Secondary or Secondary / Primary | Incompatible; no scaling |
| Unknown/conflicting physical side, or Unknown base side | Unavailable |

All existing unit, quantity, operation, confirmation, dependency and result-range
checks still apply. Initial manual requests failing those checks reject before
publication. If a saved manual selection later becomes inapplicable, retain it
and report `base_required` with a reason. Never silently use an automatic base.
CSV/BEN Unknown samples are not repaired by choosing Primary in the base editor.

The new request accepts canonical A or kA and uses the existing pre-coercion
boolean guard and shared positive/finite/SI/numerical helpers. Zero, negative,
non-finite, unsupported-unit, boolean, overflowed SI bases and currently
unrepresentable normalization reject without changing the accepted configuration.
Finite usable subnormals remain valid, including true-zero results on the
smallest positive ampere base. No arbitrary magnitude cutoff is added.

Manual base provenance normally displays kA. When kA would underflow or lose
subnormal precision, only the new manual-result path reports the exact base in
A. The additive provenance unit vocabulary therefore includes A. The editor and
details preserve small positive values rather than formatting them as 0.00.
Historical group/Source Default output units and all conversion mathematics are
unchanged. Canonical `configured_current_base_amps` remains available even when
the saved manual selection is currently unavailable.

## Nested results and centralized consumers

An automatic descendant continues to resolve from its contributing source
leaves under Stage 5A. A parent's Manual or Unassigned choice does not supply or
disable that descendant's base. A descendant may independently select its own
manual result base. Neither choice changes physical arithmetic or normalizes
already normalized input arrays. This implements the Stage 5B task's explicit
descendant requirement, rather than the earlier assessment's tentative proposal
to inherit a parent's manual base.

The existing calculated Current resolver supplies Waveform arrays, A/B scalar
cursors, anchors, peaks and calculated provenance. Existing engineering timing
validation remains a separate shared gate. Each conversion request obtains one
effective Current resolution; no permanent automatic-base cache is introduced.
Event Reconstruction consumes these same endpoints and resolved readiness.
Definition lists and Calculated Channels Preview continue showing engineering
quantities; a manual PU setting does not rewrite their physical units or values.
Voltage-only Compliance gains no Current functionality.

Visual review found a calculated Waveform row still marked `(A)` beside PU
cursor numbers. Two added assertions reproduced that mismatch. Calculated rows
now use the accepted backend display unit through the existing shared name-cell
renderer. Event Reconstruction uses its own resolution/unit mode; it never
reads Waveform's mode. Source metadata, definition units, names, selectors and
toggle data-unit attributes are unchanged. Rejected saves and obsolete responses
cannot restore old displayed units. Raw source-row behavior is unchanged.

## API and UI

Additive workspace routes:

```text
GET /api/v1/workspaces/{workspace}/calculated-channels/{id}/per-unit-config
PUT /api/v1/workspaces/{workspace}/calculated-channels/{id}/per-unit-config
```

Examples:

```json
{"mode":"manual","current_base_value":4,"current_base_unit":"kA","base_reference_side":"primary"}
{"mode":"unassigned"}
{"mode":"automatic"}
```

Requests are complete configurations. Unsupported modes/types/units reject;
nonmanual modes cannot carry a manual base or declared side. Target workspace,
identity, supported Current classification and physical timing/dependencies are
validated. Responses expose calculated identity, mode, canonical ampere base,
base side and update timestamp. Existing calculated channels require no migration.

Provenance retains the existing status and source_kind vocabularies. Additive
fields expose configuration_mode and configured_current_base_amps. New origins
`manual_calculated_current` and `explicit_unassigned` distinguish result-owned
choices from `automatic_common_base`, Group and Source Default. A result-owned
base is never attributed to an input group or Source Default. Conversion and
provenance share resolution, including unavailable reasons. Strict external
response validators must accept the new fields/origins and manual A-unit case.

Current results expose the existing Per-Unit modal from Waveform's context menu
and a compact PU configuration action in the Calculated Channels manager.
Automatic / Manual override / Unassigned, base amount/unit and independent side
use existing field styles. Return to Automatic is separate from Unassigned.
Sources remain read-only in this modal; Voltage/Power override behavior is not
introduced. Opening/fetching still performs GET only; explicit Save performs PUT.

Successful writes reuse Slice 2's display-basis generations, request cancellation
and cursor/annotation invalidation, addressed to the exact calculated id. Every
relevant Waveform array, legend, unit, cursor, callout and peak refreshes without
moving cursors or annotation anchors. Obsolete responses cannot restore old
values/labels. Unrelated raw channels and calculated results are not refetched.
ER rereads live provenance on entry and retains selection with safe unavailable/
ENG behavior. Workspace/epoch/target and modal sequence guards prevent obsolete
editor responses from populating a different result/workspace.

## Changed files

| File | Purpose |
|---|---|
| `backend/app/api/v1/calculated_channels.py` | Add result configuration GET/PUT; existing conversion endpoints unchanged. |
| `backend/app/domain/calculated_current_config.py` | Immutable result-owned mode/base/side/timestamp value object. |
| `backend/app/schemas/per_unit.py` | Validated request/read shapes and additive mode/origin/SI provenance. |
| `backend/app/services/calculated_current_config_service.py` | Validate full physical/numerical candidate before atomic publication. |
| `backend/app/services/calculated_current_per_unit.py` | Shared Automatic/Manual/Unassigned selection and live reference proof. |
| `backend/app/services/per_unit_provenance_service.py` | Truthful result ownership, saved base and subnormal A display. |
| `backend/app/services/per_unit_registry.py` | Extend existing assignment lifetime; protect explicit choices/deletion races. |
| `backend/tests/test_calculated_current_manual_config.py` | Numerical lifecycle, atomic rejection, units/sides, dependencies, cleanup and publication races. |
| `backend/tests/test_frontend_per_unit_traceability.py` | Preserve and strengthen GET-only coverage through the changed open-function boundary. |
| `browser-tests/calculated-current-manual-pu.spec.js` | Real editor, reload, numeric readouts, nested/ER and four-request race workflows. |
| `browser-tests/channel-presentation-propagation.spec.js` | Separately approved test maintenance: exact input aliases in expression rows, identity, compact type/policy and MW units. |
| `browser-tests/text-spacing.spec.js` | Separately approved test maintenance: current compact RMS summary, preserving input/frequency/window, preview and rendered-spacing assertions. |
| `frontend/index.html` | Existing modal/manager controls and exact-result refresh through shared helpers; no CSS/math changes. |
| `docs/project-memory/CURRENT_STATE.md` | Current Stage 5B operational status. |
| `docs/project-memory/DECISIONS.md` | Record explicit owner Stage 5B approval and boundaries. |
| `docs/project-memory/HANDOFF.md` | Results, evidence and owner-review stop boundary. |
| `docs/project-memory/MIGRATION_PLAN.md` | Stage 5B completion and remaining deferred scope. |
| `docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md` | Result override lifecycle, physical reference and descendant contract. |
| `docs/project-memory/PER_UNIT_AUDIT_STAGE_5B.md` | This implementation/verification report. |

## Verification evidence and status

- Test-first: 21 failures / zero passes/errors/skips against Stage 5A, exit 1;
  the new configuration route/workflow was absent. Three existing warnings.
- Initial corrected backend selection: 226 passed, zero failures/errors/skips,
  three existing warnings, exit 0.
- Broader focused backend: 535 passed, zero failures/errors/skips, three existing
  warnings, exit 0. Includes prior PU atomicity/eligibility/numerics and Stage 5A.
- Boundary-first: three new SI/subnormal provenance cases failed before their
  correction. The later focused 110-case run had one outdated static boundary
  assertion; its GET-only guard now includes both fetch and open functions.
  Rerun: 110 passed, zero failures/errors/skips, three existing warnings, exit 0.
- Initial new browser runs: seven failures on an incorrect trace-name/legend
  assumption, then seven on expecting Separate-view legends in Grouped view.
  Corrected test selectors/layout preserve exact identity, names, units and
  every numerical assertion. No product change accommodated those assertions.
- New browser file: ten passed, zero failures/skips/flaky cases/global errors,
  retries=0, exit 0, including base edits, Unassigned and Automatic races.
- Visual label reproduction: two failures, exit 1, before the shared display-row
  correction. Complete new file then passed all ten cases. One further boundary
  test reproduced precision loss reopening `1.2347e-320 A` as subnormal kA;
  the editor now retains SI A, matching provenance. Final ten-case file passes,
  including exact unchanged-field resave for both `5e-324` and `1.2347e-320 A`.
- Interim full backend: 11,315 passed, 320 skipped, zero failures/errors,
  21 existing warnings, exit 0. This preceded the final frontend label/precision
  changes, so it does not replace final verification below.
- Interim broad browser: 401 passed / one failed / zero skipped or flaky cases,
  exit 1. The unchanged Compliance `alignment is not stored in the browser`
  case timed out before its alignment assertion, awaiting initial readiness.
  It recorded 1,810,280 ms elapsed against a 30,000 ms test limit during the
  interrupted overnight run; that timing suggests an execution interruption,
  without proving its cause. Failure evidence is retained. No Compliance code
  or assertion is changed. The same unchanged case passes in 3.6 seconds with
  zero retries in the final selection, which includes its complete file.
- Final full backend: **11,315 passed / 320 skipped / zero failures/errors**,
  21 existing warnings, exit 0, 11635 collected cases. All 62 new Stage 5B cases
  execute and pass. Duration 1643.205 seconds.
- Expanded browser before approved maintenance: **429 passed / two failed / zero skipped/flaky cases or
  global errors**, 431 cases in 37 explicit files, retries=0, exit 1. Duration
  1575.534 seconds. These failures are the two additional existing expectations
  described below; the unchanged earlier Compliance timeout passes in this run.
  The original 33-file PU/Power selection is **402/402 passed** within this run;
  the four supplemental presentation files contribute 27 passes and two failures.
- Final closure browser after approved maintenance: **431/431 passed**, zero
  failures/skips/flaky cases/global errors, retries=0, exit 0, in all 37 selected
  files. Duration 1215.658 seconds. This is the final browser acceptance run.

### Additional existing test expectations - owner-approved maintenance

`channel-presentation-propagation.spec.js:107` expects aliases in the compact
summary. `text-spacing.spec.js:213` expects the RMS input repeated in that
summary. Committed `ff813af` explicitly removed redundant input names there,
leaving operation/policy in the summary and full inputs in the expression and
preview. HEAD `e2427b6` and Stage 5B have the same summary-rendering line. These
are additional test files beyond the prior four-assertion maintenance pass
(`cc72cc7` changed only `calculated-channel-power.spec.js` and
`line-to-line-voltage.spec.js`), not new production regressions.

Prepared proposal: move alias checks to exact expression rows addressed by
calculated identity; require the symbolic absolute-value expressions, operation/
policy text and MW units. Update only the RMS summary expectation, preserving
the full input/frequency/window expression, preview, rich notation and rendered
spacing checks. Benefit: meaningful coverage consistent with the committed UI.
Risk: masking a presentation regression; exact identity/expression/unit checks
mitigate this. Impact: two test files only, no production change. AGENTS.md change
governance required approval before extending Stage 5B with this maintenance.
The owner explicitly approved applying the prepared patch and rerunning all 37
selected files. Both repository files now match the approved patch exactly.
The original proposed diff remains in browser evidence:
`prepared-summary-maintenance-v2/proposed.patch`.

Temporary-copy validation first passed eight cases and failed one because the
proposal used `Abs (input)` instead of the existing symbolic `|input|` expression.
The revised proposal retains the precise symbolic expression. Its complete
two-file dry run passes **nine of nine**, zero failures/skips/flaky cases/global
errors, retries=0, exit 0, 35.615 seconds. It is recorded separately as
`prepared-summary-validation-v2.json`; it does not replace repository-wide
acceptance; owner approval and the applied-file runs below are separate evidence.

After owner approval, both complete repository files pass **9/9**, zero failures,
skips, flaky cases or global errors, retries=0, exit 0. The full 37-file closure
rerun passes **431/431**, zero failures/skips/flaky cases/global errors,
retries=0, exit 0. The 861-file hash comparison proves that only these two
browser files changed after the passing full backend; no production/backend
test code changed. The affected backend notation guard, which scans browser
files, also reruns successfully: **11/11**, zero failures/errors/skips/warnings,
exit 0. Full backend results are retained at unchanged production code; this
test-only maintenance does not rerun that entire suite. Closure evidence is isolated in
`C:/Users/fairizat/AppData/Local/Temp/oruxa-stage5b-closure-c0ce8e9f34174a6bb119eebd16816b67`.

The final browser selection contains 431 cases in 37 explicitly named files:
the 33-file PU/Power/Waveform/ER/Compliance/lifecycle selection, plus
`channel-presentation-propagation.spec.js`, `electrical-notation.spec.js`,
`text-spacing.spec.js` and `phase-display-convention.spec.js`. There are 90
tracked browser files including the new file once committed; 53 other files
are not executed. Selection targets the changed PU consumers and prior PU/Power
regressions; omitted files include import/relay workflows, other analysers,
standalone calculators and additional ER layout/navigation cases. Running all
90 is beyond this bounded local acceptance run. This is broad relevant coverage,
not the full repository browser suite. Both protected screenshot scripts are
explicitly excluded.
The complete selected list is retained as `final-selected-browser-files.json`
in the browser evidence directory. All browser acceptance runs use zero retries.

Reproducible browser selection (pass these explicit filenames to Playwright):

```text
per-unit-display-synchronization.spec.js
smoke.spec.js
waveform-top-toolbar-migration.spec.js
waveform-toolbar-t0-sync-refinement.spec.js
waveform-y-zoom.spec.js
waveform-auto-fit-range.spec.js
per-unit-atomic-updates.spec.js
event-reconstruction-per-unit.spec.js
event-reconstruction-cursors.spec.js
event-reconstruction-annotations.spec.js
event-reconstruction-grouped.spec.js
event-reconstruction-combined.spec.js
calculated-channel-preview.spec.js
calculated-channel-presentation.spec.js
calculated-channel-null-handling.spec.js
calculated-channel-rocof.spec.js
calculated-channel-power.spec.js
calculated-channel-power-label.spec.js
three-phase-power.spec.js
calculator-power-current.spec.js
line-to-line-voltage.spec.js
compliance_measurement.spec.js
compliance_readiness.spec.js
source-removal-context-lifecycle.spec.js
lifecycle-hardening.spec.js
analysis_related_waveforms.spec.js
playback_waveform_ownership.spec.js
per-unit-eligibility.spec.js
compliance_workspace.spec.js
compliance.spec.js
per-unit-numeric-integrity.spec.js
current-common-base.spec.js
calculated-current-manual-pu.spec.js
channel-presentation-propagation.spec.js
electrical-notation.spec.js
text-spacing.spec.js
phase-display-convention.spec.js
```

Backend command: `backend/.venv/Scripts/python.exe -X utf8 -m pytest
-p no:cacheprovider backend/tests --basetemp=<fresh TEMP> --junitxml=<TEMP.xml> -q`,
with `PYTHONDONTWRITEBYTECODE=1`. Browser command: `node
node_modules/@playwright/test/cli.js test <explicit files> --workers=1
--retries=0 --reporter=list,json --output=<fresh TEMP>`, from `browser-tests`,
using fresh hidden local backend/frontend servers and the copied frontend's
runtime API address. No production configuration is edited for testing.

The 62 new backend cases cover all requested A-L scenarios, including full
before/after authoritative snapshots for rejected operations, all four PU value
endpoints, provenance, group/default/linked-base integrity, independent child
policy, later inapplicability, stale auto publication, injected publication failure
and deletion-before-publication. The ten browser cases cover real saves/rejections,
reload, values/units/identity, cursor/annotation anchors, ER and delayed obsolete
waveform/cursor/callout/peak responses. Prior Slice 1-4 and 5A regressions are
included in the full backend and relevant browser selections.

Existing backend warning categories are Starlette/httpx and HTTP 422 deprecations,
relay-review regex FutureWarnings, fixture-scope deprecations and expected
COMTRADE duplicate/malformed-fixture warnings. Browser logs contain the
environment's NO_COLOR/FORCE_COLOR warning.
Existing skips concern absent owner relay PDFs (153), unconfigured BEN reference
data (49), POSIX shell requirements (17) and inapplicable relay/catalog cases
(101). These are not silently counted as passes; no new Stage 5B case is skipped.

## Independent electrical and performance evidence

An independently checked 100,000-sample calculated result remains 8398 A.
Decimal division agrees with waveform/cursor/anchor/peak endpoints in all 20
comparisons over bases 4 kA, 2 kA, 4000 A, 1e300 A and 1e-300 A. Ten complete
full-resolution API ranges check all 100,000 PU samples. The established large
viewport reducer returns 5001 points; reduction is not mistaken for full storage.
Thus 4 kA gives 2.0995 pu and 2 kA gives 4.199 pu without changing engineering
samples. Save observations are 21.1-26.9 ms for this local dataset while other
tests run, not a deployment benchmark or scalability guarantee.

Input hashes and the engineering result hash/array identity remain unchanged.
Engineering result SHA-256:
`11108765f6198f4e97b8e3b2e6c72c5f1068be0ab2f0026936abcba0bead306b`.
Ten reviewed engineering/import/timing modules are byte-equivalent to HEAD after
line-ending normalization, including physical calculated operations, Power,
phasors, sliding phasors, COMTRADE sample scaling, stable division and group
base formulas. No normalized array is retained as a manual configuration.
All 25 existing calculated API functions have unchanged ASTs; only the two
configuration handlers are added. The single frontend style block is unchanged.
The source/test hash manifests cover 861 files. Details are in
`electrical-performance-proof.json`, `engineering-invariance-proof.json` and
`final-code-test-manifest.json` in backend evidence; closure's
`code-test-manifest.json` additionally records the two approved browser edits.

Probe authoring initially assumed a 1 kHz fixture (actual 5 kHz), then assumed
the large viewport bypassed existing reduction. Those probes were corrected to
the documented fixture/range contract; no production change accommodated them.

New backend evidence is isolated in
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-stage5b-20261103-jlhzg8h7`.
Browser evidence/server storage is isolated in
`C:/Users/fairizat/AppData/Local/Temp/oruxa-stage5b-browser-5db4d2f589b04367b92d4c84f8f7654d`.
The initial server launch encountered a Windows account/TEMP ACL mismatch;
fresh server-account-owned TEMP directories resolved it. Only verified owned
test servers are managed; all Stage 5B test servers are now stopped. Existing
audit/evidence paths are not test outputs.

## Limitations and delivery boundary

No CT/VT scaling, new sample-side declaration, shared secondary-reference
identity framework, Voltage override, power math change or CSV discovery-id
correction is included. Unknown physical side remains a real limitation, not a
base value to guess. The original audit and historical assessments remain intact.

Visual inspection also observes an existing Peak annotation box above the
reused PU modal, partly obscuring provenance text. Editor controls are usable;
workflow and numerical assertions pass. No stacking/CSS change is included.
Evidence: final new-browser `manual-current-editor.png`. Proposed separate
owner-reviewed follow-up: examine shared modal/annotation stacking. Benefit:
unobscured dialogs; risk/impact: shared overlay interactions across the UI.
Its cause and a correction are not claimed to be verified in this stage.

One result assignment replacement is atomic; independently accepted changes
retain the existing last-writer/per-registry concurrency model. There is no global
transaction snapshot across all source/group/dependency edits. Eligibility is
reevaluated live; invalidation does not silently replace a saved manual choice.

The 19-file Stage 5B/approved-maintenance diff passes whitespace checks. All
2,250 protected evidence files retain their file list, hashes, sizes and
modification times. Only the two
approved browser files differ from the 861-file full-backend manifest; closure
records their exact new hashes. Prior Slice 1, maintenance, Power and
Stage 5A ancestors remain intact. Branch remains `feature/calculator-vi-phasors`,
baseline HEAD `e2427b652bafcb9e366cc84d79258e28c15dcc8b` was five ahead / zero
behind origin after fetch. The containing local revision is the Stage 5B
delivery; use Git history and the accompanying delivery message for its hash
and final working-tree status. The two additional test-only files are explicitly
distinguished from the result-configuration feature above. Stage 5B acceptance
is met locally, subject to the documented coverage boundary and existing limits.
Do not push, merge, deploy or begin a final audit. Stop for owner review.
