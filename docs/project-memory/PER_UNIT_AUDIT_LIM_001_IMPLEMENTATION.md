# LIM-001 — centralized Current PU reference safety

Finalized: 2026-11-07. Test execution records: 2026-11-06.
Baseline: `384a55fafbbecf7e304aa9ea8cfc663554177fd1`
(FA-001), branch `feature/calculator-vi-phasors`. Owner task:
"LIM-001: Centralized PU Reference-Side Safety". Policy: DEC-210.

Implementation and local verification are complete. All LIM-001 acceptance
checks pass. The focused local implementation commit is the commit containing
this report; its parent is the FA-001 baseline above. Overall PU audit acceptance
remains with the owner. No push, merge or deployment was performed.

## Engineering policy

Measurement side, configured base side, provenance and actual denominator stay
independent. Known Primary/Secondary mismatch blocks Current normalization on
raw, Group/Source Default, legacy and calculated/nested paths. Original ENG
values remain unchanged. No ratio scaling, side inference or new storage model.

| Reference pair / authority | Conversion policy | Reference metadata |
|---|---|---|
| Primary/Primary | Eligible subject to existing gates | compatible |
| Secondary/Secondary, one established authority | Existing eligible behavior retained | compatible |
| Primary/Secondary or Secondary/Primary | PU unavailable; preserve ENG | incompatible |
| Historical raw/single-authority Unknown | Previously allowed PU remains available | unverified |
| Cross-authority Automatic with Unknown | Existing fail-closed behavior | unverified, unavailable |
| Distinct Secondary authorities | Shared secondary reference remains deferred | unverified, unavailable |
| Result Manual with Unknown samples or declared base side | Reject before publication | unverified, unavailable |
| Mixed known P/S samples, including with other Unknown metadata | PU unavailable; known conflict cannot disappear into aggregation | incompatible |

Units, review state, dependencies and numerical representability remain separate
mandatory gates. Matching sides do not certify recorder calibration or instrument
wiring. Historical Unverified PU remains a disclosed engineering limitation that
the owner explicitly accepted; it is not reference-validated conversion.

Result-specific Manual selects its own independently declared denominator/side
before reference proof. Thus Primary samples can use a valid Primary result base
despite unavailable, unequal or Secondary **input normalization bases**. Original
inputs stay untouched. Manual does not repair Unknown samples or mixed physical
references. Automatic descendants still resolve source leaves, not a parent's
Manual or Unassigned selection. Voltage and Power mathematics are unchanged.

## Centralized implementation

`domain/per_unit_reference.py` contains the shared pure classifier. It examines
sets of known measurement/base sides before Unknown aggregation, distinguishes
compatible/incompatible/unverified, and applies existing unavailable reason
codes. Historical Unknown is permitted only outside strict Manual/cross-authority
mode. It uses metadata only; no waveform scan, array normalization or registry
mutation. Existing unrelated unavailability reasons retain precedence.

Transient `PerUnitResolution` carries reference compatibility and independent
sides. The raw shared dispatcher, provenance and coverage use the same source
gate after selecting group/default authority. Group membership remains final;
an incompatible or unresolved group never borrows Source Default.

The calculated Current resolver uses the same classifier over live contributing
leaves. It retains the global base comparison and final-result numerical checks.
Legacy internal manual profile pointers retain their denominator behavior, but
must pass input and selected-base reference checks. They cannot bypass known
mismatch through an ancestor or ambient default. The shared Compliance adapter
now supplies complete registry context to the calculated dispatcher; no public
Current Compliance feature is added and the Voltage-only product scope remains.

No configuration-write path is redesigned. Existing copy/candidate/locked
publication and rejection atomicity remain authoritative. Separately accepted
cross-registry edits still are not one global snapshot. Reference proof is
derived live, without a permanent eligibility cache.

## Additive API and shared UI

Existing `configured`, `base_required` and `not_applicable` meanings are retained.
Configured means usable conversion, not proof of physical reference compatibility.
Existing Current side reasons explain mismatch/Unknown/unestablished Secondary.

- Raw/calculated waveform, A/B cursor, anchor and peak responses add nullable
  `per_unit_reference_compatibility` (compatible/incompatible/unverified).
- Provenance adds nullable `reference_compatibility`; existing measurement/base
  side, origin, group/default identity and denominator fields stay independent.
- Coverage adds `unverified_reference_count`, a **subset** of usable Group/Source
  Default counts, not a fourth category to add to the existing totals.
- Engineering-mode and non-Current reference metadata are null where no proof
  is requested/applicable. No new request parameter or status enum is required.

Shared compact status rendering places Unverified reference or PU unavailable
beside applicable channel rows/legends, with accessible explanation and tooltips.
Hover, both cursor rows, callouts, peaks, provenance and coverage use the same
backend outcome. Warning text is not duplicated in every cursor numeric cell.
Existing base-side selectors explain independent sample/base meaning; derived
Primary semantics remain unchanged. No sample-side selector or CT workflow.

Event Reconstruction uses its own mode/resolution, not Waveform's warning state.
Unavailable channels stay selected and are not drawn as PU there; Waveform
retains ENG. Annotation times/indices and trace identity stay unchanged. Existing
generation/abort fences protect new metadata as well as arrays; reference/base
edits cannot restore obsolete PU through an old asynchronous response.

Visual inspection found the initial new warning style too faint. Its scoped
style uses existing theme text and warning-wash tokens with normal lettering;
no unrelated layout/theme or Peak/modal behavior is changed.

## Regression evidence

All outputs are isolated in:

```text
C:/Users/fairizat/AppData/Local/Temp/oruxa-lim001-f7c1a499069b416097aabd49a5d828e5/
```

Prerequisites: Windows, repository virtualenv Python 3.12.10 / pytest 9.1.1,
Node 24.15.0, installed Playwright 1.62.1 Chromium. Backend uses
`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, a new `--basetemp` and JUnit
path. Browser uses real local backend/frontend servers, `CI=1`,
`BEN5K_EXPERIMENTAL_ENABLED=1`, the repository virtualenv via `PW_PYTHON`,
four workers and explicit `--retries=0`. Storage, artifacts, logs, JSON and JUnit
paths are new for every run. The manifest explicitly selects 91 tracked specs
plus the new reference-safety file; neither protected screenshot spec is included.

Initial defect-first run (`before.xml/.log`): **6 failures**, each asserting the
actual known-mismatch status returned configured/pu instead of base_required/A.
Two impossible equipment-Secondary-base combinations were skipped in that first
parameter construction; the final test list explicitly enumerates valid input
combinations and has no such skips. Original logs remain intact.

Initial focused implementation run: **239 passes / 1 failure / 2 skips** in
193.20 seconds. The failed new coverage assertion incorrectly included nine
unrelated Voltage channels that the derived Source Default legitimately enables.
It was corrected to assert preserved Voltage coverage and unavailable Current,
without changing production behavior. The impossible parameter combinations
were removed, not converted into passing cases.

Expanded focused run (`focused-v2.xml/.log`): **118/118 passed**, 57.09 seconds,
zero skips/failures/errors, three existing warnings. It covers both new modules,
real CSV and native BEN import, source/group methods, both cursor values, max/min
peaks, anchors, raw/calculated/nested values, provenance/coverage, Manual base
replacement, rejected-save snapshots, legacy pointers and Compliance reuse.

New browser file: **7/7 passed**, zero retries/failures/skips/flaky cases,
84.005 seconds wrapper time. Real group edits/rejection, Source Default mismatch,
compatible Secondary, Unknown annotations/cursors/legends, mode round trips,
independent ER and a held obsolete response are exercised. Screenshots and exact
response assertions are retained; physical samples/trace identity are compared.

The first full backend run (`backend-full.xml/.log`) completed with **11,373
passes / 1 failure / 320 skips / 21 warnings**, 3261.58 seconds. The failure
was a static assertion expecting the old two-argument Event Reconstruction name
cell call. The shared name cell now accepts an explicit third argument so ER
uses its own reference status. Both exact source assertions were updated; their
remaining markup and identity assertions were preserved.

The first complete four-worker browser run (`browser-full.json/.xml/.log`)
completed with **1291 passes / 11 failures**, zero retries, 2755.142 seconds.
All eleven failures were inspected individually:

- Five Text Note cases exposed an implementation regression: the new ER
  annotation adapter requested channel metadata for channel-free Text Notes.
  The adapter now requests reference status only for annotations with a channel.
- One exact coverage response assertion needed the additive zero-valued
  `unverified_reference_count` field; it remains an exact object comparison.
- One common-base test read retired arrays while the old status/unit remained
  visible during an accepted base refresh. Its readiness poll now captures the
  complete expected sample count together with status/unit. Every sample's
  numerical comparison and the array length assertion remain intact.
- Two existing 30-second workflow timeouts, one estimate-confirm overlay wait
  and one calculated-catalogue console 404 did not recur in the complete affected
  file rerun. They were not suppressed or corrected through product changes.
  The first backend and browser runs overlapped; resource contention is possible
  but was not established as the cause.

After these scoped corrections, all **65 tests in nine complete affected browser
files passed**, four workers, zero retries/failures/skips/flaky cases, 183.906
seconds. The log and JSON retain the full original failures and rerun evidence.
New screenshots confirm readable associated warnings. The final complete backend
and browser runs are executed sequentially against identical source.

Final full backend (`backend-final.xml/.log`): **11,374 passed / 320 skipped /
zero failures or errors / 21 existing warnings**, exit 0. Pytest time 2012.44
seconds (33m32s); wrapper including startup/teardown 2023.388 seconds. The 59 new
policy/safety cases all pass. Existing Stage 5A inheritance 132, graph 22, Stage
5B Manual 62, atomic update/publication 45 and numerical-integrity 164 cases are
included, along with the entire Voltage, Power, Calculator and Compliance suites.

Skips: 153 absent owner relay PDFs, 49 unconfigured BEN reference corpus,
17 Windows POSIX-shell checks and 101 relay-sheet applicability cases. Existing
warnings: Starlette/httpx and HTTP-422 deprecations, two relay regular-expression
FutureWarnings, two class-scoped fixture deprecations and deliberately malformed/
duplicate COMTRADE import fixtures. No new reference-safety warning is introduced.

Final complete browser (`browser-final-v2.json/.xml/.log`): **1302/1302 actual
passed results across 92 files**, four workers, zero failures/skips/flaky cases/
global errors/retries, exit 0. Playwright duration 2449.365 seconds (40m49s);
wrapper duration 2452.858 seconds. This covers the complete tracked inventory
plus the seven new LIM-001 cases, including Stage 5A/5B, FA-001, Voltage PU,
Power Calculator, three-phase Power, Compliance, annotation/modal and notation
regressions. All eleven initial browser failures are resolved in the complete
final run; no unrelated production correction was made.

`final-verification-summary.json` confirms these counts and zero source drift
across **871 application/test files** between the complete runs. The index was
empty before scoped review and no tracked changes lay outside the 26-file scope.

The initial queued launcher
stopped at inventory preflight because its PowerShell JSON-array parsing nested
the selection. Reading the same manifest as one JSON document confirmed exactly
92 unchanged intended files; that temporary launcher was corrected before any
tests started. No production/test file or acceptance retry setting was changed.
The subsequent attempt exposed Windows PowerShell 5.1 stream handling:
`ErrorActionPreference=Stop` buffers native output and treats ordinary server
stderr as a terminating error. A harmless isolated stderr probe confirmed it.
That attempt was interrupted; partial `browser-final-artifacts` are preserved
and it supplies no acceptance result. The corrected acceptance launcher uses
normal native stream handling after strict preflight and new
`browser-final-v2.*` outputs. No test timeout, assertion, worker count or
Playwright retry setting was changed to address these temporary launcher faults.

## Numerical reproductions

The real imported 2000:1 CT fixture uses `a=0.5`, `b=0`, raw integer 1 and S
marker, preserving 0.5 A Secondary. With a 2 kA Primary base:

- Before: 0.00025 pu, configured (incorrect reference).
- After: base_required/incompatible, **0.5 A ENG retained**, no scaled substitute.
- A two-input sum remains physically 1 A, and its nested magnitude remains 1 A.
- Known S/S under the established authority still gives 0.00025 pu on a 2 kA
  Secondary base. A separately valid 1 A Secondary base gives 0.5 pu for a
  single 0.5 A result, without interpreting the CT ratio.
- Historical Unknown retains the same direct division and explicit Unverified
  metadata. Real CSV A and BEN kA tests independently check SI normalization.
- Valid Primary result Manual 1 A normalizes a physical 1 A sum to 1 pu despite
  incompatible Secondary input normalization bases; input configurations remain
  byte/field equivalent around that save.

FA-001 remains a separate local commit; its new regressions are included in the
complete browser selection. No PU arithmetic is changed by LIM-001.

## Scope and remaining limits

The scoped change comprises the following 26 files. Each path below is relative
to the repository root:

| Files | Purpose |
|---|---|
| `backend/app/domain/per_unit.py`, new `backend/app/domain/per_unit_reference.py` | Add transient proof metadata and the shared pure classifier/source adapter |
| `backend/app/services/waveform_service.py` | Apply proof to raw waveform, cursor, anchor and peak resolution |
| `backend/app/services/calculated_current_per_unit.py` | Apply proof to historical/single-authority, cross-authority, Manual and legacy descendant resolution |
| `backend/app/services/calculated_channel_service.py` | Propagate proof to all calculated value consumers and context-free fallback |
| `backend/app/services/per_unit_provenance_service.py` | Use the same gate and expose independent compatibility/reason metadata |
| `backend/app/services/per_unit_coverage_service.py` | Align readiness and count usable Unverified references as a subset |
| `backend/app/services/compliance_series.py` | Supply full registry context to the existing calculated adapter |
| `backend/app/schemas/annotation_anchor.py`, `calculated_channel.py`, `cursor_values.py`, `peak_value.py`, `per_unit.py`, `waveform.py` | Add backward-compatible response metadata and mapping |
| `backend/tests/test_per_unit_reference_policy.py` (new), `backend/tests/test_per_unit_reference_safety.py` (new) | 59 policy/API/provider/numerical/state regressions |
| `backend/tests/test_frontend_event_reconstruction.py` | Preserve exact static guards with ER's explicit independent status argument |
| `browser-tests/per-unit-reference-safety.spec.js` (new) | Seven real UI/value/identity/annotation/refresh cases |
| `browser-tests/current-common-base.spec.js` | Await complete refreshed arrays while preserving exact numerical assertions |
| `browser-tests/per-unit-eligibility.spec.js` | Extend exact coverage expectation for the additive field |
| `frontend/index.html` | Shared accessible reference warnings, metadata propagation and editor explanations |
| `docs/project-memory/DECISIONS.md`, `PER_UNIT_MEASUREMENT_MODEL.md` | Record approved DEC-210 and its bounded model clarification |
| `docs/project-memory/CURRENT_STATE.md`, `HANDOFF.md`, this new report | Record implementation, evidence, remaining boundaries and local commit status |

The existing historical final audit and assessment remain outside the focused
commit. The final audit receives append-only follow-up evidence; its entire
47,966-byte task-start prefix remains preserved. All 2250 protected evidence
files passed SHA-256, size and nanosecond-mtime comparison, with no added files,
on 2026-11-07 01:27:23 UTC (`protected-closure.json`), after resuming closure.
Earlier checks remain saved separately. The historical audit
SHA-256 remains `e98310e2d3618d22b2468df3c878904e6e2009bf94ba4f338c1603c740ec256b`.
The assessment is byte-identical to its task-start copy. No protected path is
part of the commit allowlist. The final audit follow-up is appended separately;
it is not folded into the focused commit.

Deferred: CT/VT conversion, shared secondary-reference identity, recorded-side
declaration for CSV/BEN, separate CSV discovery-ID defect and durable workspace
persistence. Input metadata is trusted as declared; matching sides are not an
independent equipment calibration certificate. No final overall audit closure,
push, main merge or deployment is authorized by this implementation.

## Performance observations

The added decision examines small sets of reference metadata after existing base
selection. It does not iterate waveform samples, normalize arrays, make requests
or mutate registries. Calculated dependency traversal and existing full-result
numerical checks remain in their established resolver; this change adds no
permanent cache or workspace-wide refresh. UI propagation uses existing accepted
response/generation refreshes and shared row/legend/annotation rendering.

`reference-performance.py/.json` records five rounds of 10,000 decisions per
case on this Windows host. Median times were 7.645 microseconds compatible,
12.163 known mismatch, 7.460 historical Unknown and 13.055 strict Unknown.
This bounded pure-helper measurement ran alongside backend tests. It is neither
an end-to-end latency comparison nor a release performance threshold; it supports
the source review finding that reference proof adds metadata work only.

The existing full-suite 500,000-sample extraction checks also passed: Current
PU/ENG time ratio 1.18x; Voltage 1.02x. These measurements describe this host/run,
not a guarantee for other datasets or platforms.

## Final Git state and acceptance boundary

Branch: `feature/calculator-vi-phasors`. FA-001 remains intact as parent
`384a55fafbbecf7e304aa9ea8cfc663554177fd1`. The focused LIM-001 commit is the
commit that adds this report; obtain its exact identity with
`git log -1 --format=%H -- docs/project-memory/PER_UNIT_AUDIT_LIM_001_IMPLEMENTATION.md`.
It contains only the 26 scoped paths above. Both local fixes remain unpublished:
two ahead / zero behind fetched `origin/feature/calculator-vi-phasors` at
`265f1906d4a6c30568309dd45ffa5e41cbb236ce`. `origin/main` remains
`d8ade8f04dde5df2654082a784adbebb064a7336`.

Tracked working tree and index are clean on completion. Seven existing untracked
entries remain: `.audit/`, `.slice1-evidence/`, `test-results/`, the two protected
screenshot specs, the historical final audit and the assessment. None is staged
or committed. The assessment is unchanged; only authorized append-only follow-up
is added to the historical final audit. The protected evidence itself is untouched.

DEV frontend/backend were last observed at `265f1906` on 2026-11-05
12:26:55 UTC; this task makes no new deployed-version claim. No push, merge,
CI dispatch, deployment or final overall audit closure. No additional work is
started. Owner review/acceptance and separate release authorization remain next.
