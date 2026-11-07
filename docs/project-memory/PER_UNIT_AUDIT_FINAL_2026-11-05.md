# Final consolidated Per-Unit audit — 5 November 2026

Audit target: `265f1906d4a6c30568309dd45ffa5e41cbb236ce`, branch
`feature/calculator-vi-phasors`. Original audit baseline:
`944e98f3a8c99692414cde3e1cf9a604d020f5f2`. Deployment comparison baseline:
`d8ade8f04dde5df2654082a784adbebb064a7336` (`origin/main`).

**Verdict: CONDITIONAL PASS — Ready subject to stated conditions.**
This is an audit recommendation for owner review, not merge authorization.
No production functionality has been changed.

## 1. Executive summary

Independent reproductions of PU-001 through PU-008 pass on the approved
release. The fresh full backend suite passes. All 1288 distinct tracked browser
cases pass across the standard and prerequisite-enabled environments; the
initial run's 22 BEN5K prerequisite failures are retained in section 8.
Independent numerical, API,
reference-side, live-dependency and browser race/cursor checks support the
centralized conversion and result-specific manual-override contracts.

One additional issue is confirmed: **FA-001, Low severity**, the Source Default
editor's derived-current preview can display `Infinity kA` for extreme finite
inputs whose saved base and actual PU calculations are finite and correct.
This is a remaining presentation defect, not a recurrence of the original
backend denominator failure. It is reproduced and left unchanged for owner
review. The previously deferred CSV post-conversion discovery-ID defect also
remains reproducible.

This audit does not authorize a merge. Owner DEV UAT is provisionally accepted;
final owner acceptance and review of the stated limitations remain necessary.
No push, merge, deployment, production fix or engineering-policy change is part
of this audit.

## 2. Scope and reviewed commits

Preparation included repository governance, the architecture reference,
CURRENT_STATE, DECISIONS, HANDOFF, MIGRATION_PLAN, the authoritative
PER_UNIT_MEASUREMENT_MODEL, the original audit, all four remediation reports,
the Stage 5A/5B reports, DEV readiness and the owner UAT checklist. Relevant
decisions include DEC-050/051, DEC-052/115/116, the shared notation conventions,
Power Calculator decisions and DEC-209's explicit reference-side contract.

`git fetch origin` succeeded before the audit. The working branch and its
upstream both pointed at the approved target, zero ahead/behind. Tracked files
were clean at entry. Existing protected untracked evidence was preserved.

The seven commits above the deployment baseline, oldest first, are:

| Commit | Reviewed contents |
|---|---|
| `cc72cc72ceea6c5ed9152480a74bc691459159ea` | Approved test maintenance for Power labels and RMS presentation |
| `0eea55c3dd28dcff4096b1b615f97cb6dc8a8ae7` | Slice 2: waveform mode and cursor/base synchronization |
| `b5d824e7dfb0db5f33ae4ba55f8084479652cd6d` | Slice 3: measured-unit eligibility and Compliance reference resolution |
| `2114a714f43a00fe40b1d293bd1852e1a3e92ad7` | Slice 4: numerical integrity and pre-coercion boolean rejection |
| `e2427b652bafcb9e366cc84d79258e28c15dcc8b` | Stage 5A: automatic Current common bases and explicit side metadata |
| `bddebd507d40ab5d4d92a95f1e1917c130ac8e6d` | Stage 5B: calculated-result Manual/Unassigned/Automatic configuration |
| `265f1906d4a6c30568309dd45ffa5e41cbb236ce` | Approved Peak annotation/modal stacking correction and readiness/UAT deliverables |

Slice 1 commit `498e8cd59e61886ad9d6dbef513a53f91f4413ed` and maintenance
`0f751b2abc582ef7ed85319164c33a245cc5c84c` are already in the comparison
baseline. The 14-operation picker maintenance
`caae9d101e0519f5ab4aed003821554154432f47` is also in that baseline.
The release delta is 64 files; it includes approved browser presentation
maintenance and documentation as well as PU implementation. It does not add
new Power algorithms. The baseline already contains the approved Power
Calculator and three-phase calculated Power functionality.

### Evidence location and independence

Fresh scripts, JSON/JUnit results, logs and screenshots are isolated under:

```text
C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-final-audit-20261105-ee2a39ad987b43f2b8ff4d73d09c63e3/
```

This is local audit evidence, not a committed, portable artifact archive.
The original `.audit/per-unit-2026-10-31/AUDIT_REPORT.md` is historical evidence
and has not been rewritten. Existing `.audit/`, `.slice1-evidence/`,
`test-results/` and both untracked screenshot scripts are excluded from writes
and browser selection.

New numerical oracles use Decimal arithmetic and explicit expected values,
not the implementation under test. API probes build fresh requests and compare
full state. Existing test factories are reused only to construct source
fixtures. Fresh browser probes exercise real UI saves and real backend values.
Existing regressions are additional evidence, not the sole basis for closure.

## 3. Original defect closure matrix

| Finding | Original failure independently exercised | Observed result at target | Closure |
|---|---|---|---|
| PU-001 | Valid 275 kV configuration; PUT 132 kV/manual without required reference; invalid-reference and multiple-field variants | Rejects; entire authoritative snapshot and fresh ENG/PU values remain equal. Accepted 132 kV update changes Voltage and linked Current consistently. | **PASS** |
| PU-002 | `needs_review` group; combined name/status confirmation plus missing, wrong-kind or duplicate membership | Rejects; name/status/metadata/members/reverse indices/bases and ENG/PU results unchanged. Cannot activate PU using old members. | **PASS** |
| PU-003 | Real CSV preparation/conversion with missing measured unit and a numeric configured base | Coverage, provenance and waveform agree on `base_required`; original `[1.32, 1.33, 1.31]` values and empty unit remain intact. | **PASS** |
| PU-004 | Raw-source RMS Voltage through Source Default automatic reference | Compliance series/readiness and Waveform use the same resolved reference; independent nominal signal produces 1 pu. | **PASS** |
| PU-005 | Hold a real metadata response during PU selection, select Engineering, then release response | Newer Engineering intent wins. Further ENG/PU round trips preserve full expected arrays and units. | **PASS** |
| PU-006 | Extreme positive bases, SI/derived overflow, finite-to-zero underflow, full-channel representability, scalar/vector parity | Invalid candidates reject atomically; a valid but unusable recording/base pair reports unavailable and retains ENG. True zero remains valid. See separate FA-001 preview issue. | **PASS** for original backend defect |
| PU-007 | Both JSON booleans on all seven numeric configuration fields | HTTP 422 before coercion; complete state and effective values unchanged. Numeric compatibility remains covered by regression suite. | **PASS** |
| PU-008 | Stationary A/B cursors through ENG → PU → accepted Voltage base edit → ENG | Values, units, arrays and cursor text refresh without cursor movement; physical values and cursor times are preserved. | **PASS** |

The independent rejected-request snapshot includes workspace groups, all
Voltage/Current/Source Default configurations, reverse indices, calculated
assignments, source/group views and fresh raw/calculated ENG/PU waveforms.
Object equality is checked before recording a digest; an HTTP error alone is
not used as atomicity evidence. Fault-injection regressions additionally cover
publication failures and index integrity. Missing/wrong-source/wrong-quantity,
duplicate/already-assigned members, invalid metadata, omitted fields, initial
configuration and accepted metadata/member/combined updates remain covered by
the full dedicated regression modules.

For PU-008's independent sine case, 275 kV nominal gives instantaneous peak
`sqrt(2)` pu; 132 kV gives `sqrt(2) * 275/132 = 2.9462782549` pu. The stationary
5 ms and 15 ms cursors follow those signed peaks, then restore the same physical
engineering values. This checks numerical contents, not only labels.

## 4. Mathematical verification

The central contract remains `Vpu = Vactual/Vbase` and
`Ipu = Iactual/Ibase`. Applicable three-phase equipment uses
`Ibase = Sbase/(sqrt(3) * VLL,base)`. Nominal Voltage entry is system L-L;
L-G measurement normalization uses the corresponding phase base. Instantaneous
samples are not silently converted to RMS.

| Independent reference | Expected value |
|---|---:|
| 132 kV nominal, L-G base | 76,210.2355330306 V |
| 275 kV nominal, L-G base | 158,771.3240271471 V |
| 1000 MVA / 132 kV three-phase Current base | 4,373.865675678983 A |
| 1000 MVA / 275 kV three-phase Current base | 2,099.455524325912 A |
| Nominal sinusoid normalized to RMS base | RMS 1 pu; instantaneous peak 1.4142135623730951 pu |
| 4199 A + 4199 A, 2 kA common base | 8398 A physical; 4.199 pu |
| Same physical sum, result-specific 4 kA manual base | 8398 A physical; 2.0995 pu |

`independent-numerics.json` records 12 nominal/reference cases at 33, 66, 132,
275, 500 and 765 kV, six additional extreme derived-base cases, both signs,
V/kV/A/kA normalization, 16 unit-eligibility cases and input immutability.
Decimal precision is 160, deterministic random seed 20261105.

Of 4096 random normal/subnormal/exponent cases, 3062 are representable and
1034 correctly unavailable. There are zero classification or scalar/vector
parity discrepancies, with at most one ULP error against the independent
reference. No arbitrary practical-magnitude threshold is inferred from this.
Finite usable subnormals and genuine zero are distinguished from overflow or
false zero produced by normalizing a finite nonzero sample.

The real RMS operation was also exercised on a generated 275 kV, 50 Hz
COMTRADE waveform. All 181 finite RMS samples agree between Compliance and
Waveform; maximum deviation from nominal 1 pu is `1.46358928991841e-5`, consistent
with the sampled waveform. A generic Voltage subtraction renamed `VAB`, and
its RMS descendant, remain unavailable under DEC-052/116. Names cannot confer
an approved Voltage representation.

Code reviewed includes `domain/per_unit_numerics.py`, `domain/per_unit.py`,
Voltage/Current base domains, `services/group_aware_per_unit.py` and
`services/calculated_group_aware_per_unit.py`. Shared helpers use stable scaled
arithmetic where intermediate multiplication would overflow. Array safety is
checked against the complete channel, not just the viewport or cursor sample.
Missing original samples retain their gap semantics; physical arrays are not
modified by display conversion.

## 5. Configuration precedence findings

| Authority / proposed change | Verified behavior |
|---|---|
| Source channel belongs to a Measurement Group | That group remains authoritative, including missing/unconfirmed/unusable configuration; no ambient-default repair |
| Genuinely ungrouped source channel | Its own Source Default may supply its effective base |
| Legacy source-wide configuration | Established fallback remains supported in its intended path; does not override group ownership or a saved result mode |
| Linked Current equipment base | Resolves the accepted linked Voltage configuration live; rejected Voltage changes do not alter it |
| Calculated Current Automatic | Resolve contributing source leaves, not an unrelated result/ambient default |
| Calculated Current Manual | Result-specific base takes precedence subject to independent physical/unit/side/numerical validity |
| Calculated Current Unassigned | Explicitly unavailable; no automatic fallback |
| Return to Automatic | Explicitly clears result-owned manual fields and resumes live leaf resolution |

The independent split-group example rejects the old PC-001 behavior: 2 kA and
4 kA input groups cannot normalize an 8398 A result using an ambient 1 kA Source
Default. Equal 2 kA inputs resolve to 4.199 pu. Setting the result itself to a
valid 4 kA manual base produces 2.0995 pu without changing either input group.

Slice 1 uses independent validated candidates and replacement publication.
`measurement_group_registry` validates the complete merged group, stages group
and reverse-index mappings, and publishes under its existing lock.
`voltage_group_config_registry` publishes one validated configuration
replacement. Side/default/Current candidates and Stage 5B assignment records
are likewise validated before replacement. No validation path mutates a
shared candidate. Publication fault tests verify preservation rather than
assuming validation-before-write alone is sufficient.

The existing concurrency model is per-registry. Multiple separately accepted
edits across registries are not a global transaction or snapshot. Locks,
immutable candidates and lifetime checks protect the scoped updates; no new
database transaction or global synchronization system has been introduced.

## 6. Cross-group and manual override findings

### Automatic common-base resolution

The live dependency walker deduplicates source references and shared ancestors,
detects cycles/missing dependencies and checks units, quantity, supported
operations, confirmation and actual output range. Arithmetic always runs in
ENG; only the final result is normalized. A parent's Manual or Unassigned mode
does not supply or disable an Automatic descendant's base.

Agreement is `(max - min) / max <= 1e-12`, with zero absolute tolerance and the
minimum compatible SI base chosen deterministically. Independent cases at
relative perturbations `0.8e-12` and `1.2e-12` straddle the boundary correctly.
Existing graph regressions cover nested extrema, order, shared ancestors and
subnormal limits. Later base changes are observed without persisting an
inherited denominator.

### Physical-reference compatibility

Recorded measurement side and configured base side are separate metadata.
Recognized COMTRADE P/S markers supply the former; manual/direct bases do not
inherit it. Equipment-derived bases retain Primary semantics. No CT/VT ratio
scaling, sample reinterpretation or magnitude/name-based side inference occurs.

| Samples / base / authority | Automatic | Explicit Manual |
|---|---|---|
| Primary / Primary, distinct authorities | Eligible if effective bases agree | Eligible with a valid result base; input amounts need not agree |
| Secondary / Secondary, distinct authorities | Unavailable: shared secondary reference deferred | Unavailable for the same physical reason |
| Primary / Secondary or Secondary / Primary | Unavailable across authorities | Reject incompatible result-base declaration |
| Unknown samples, distinct authorities | Unavailable | Cannot be repaired by declaring a Primary base |
| Primary samples / unknown input bases, distinct authorities | Unavailable | Valid independently declared Primary result base is allowed |
| Historical single authority | Existing Automatic path is preserved; its legacy lack of side gating is not a physical-compatibility proof | New Manual requires known compatible samples and declared base side |

Eight independent side/authority cases pass, including preserved historical
same-authority behavior, shared Secondary manual eligibility and strict
cross-authority rejection. The physical 8398 A sum and input registries remain
unchanged in every case. These outcomes do not certify general secondary
equipment-base compatibility.

An additional independent reproduction of original LIM-001 confirms the exact
boundary: a Secondary-marked 2000:1 CT recording with physical samples of
0.5 A and a same-group 2 kA Primary base still yields 0.00025 pu in raw and
same-authority Automatic paths. There is no ratio scaling or historical side
rejection added to those paths. New result-specific Manual rejects a Primary
base for these Secondary samples; an explicit 1 A Secondary result base gives
0.5 pu, leaving input groups and samples unchanged. See section 11.

### Manual lifecycle, integrity and persistence

Automatic → Manual → Unassigned → Return to Automatic, manual editing,
rejected saves, live review-gate invalidation, nested results and deletion are
covered by fresh probes and the full regression modules. Waveform, cursor,
anchor and peak APIs return the same normalization and explicit manual
provenance. A later invalidated Manual selection remains saved but unavailable;
it does not fall back silently. An older Automatic recompute cannot overwrite
Manual/Unassigned or recreate a deleted assignment lifetime.

Configuration belongs to `(workspace, calculated result)`, not input groups or
defaults. It survives browser refresh/reopening the same still-live workspace.
New Workspace creates different identity and empty configuration. Reopening
source files in a new workspace does not restore old settings. Backend restart
loses in-memory workspace state. This matches DEC-015 and the owner-approved
ephemeral architecture; it is not permanent server-side persistence.

## 7. Consumer integration matrix

| Consumer | Authority and conversion path reviewed | Evidence / conclusion |
|---|---|---|
| Raw Waveform API / plots | Shared group/default resolution, measured-unit and whole-channel safety checks | Independent Voltage/Current arrays, missing units and extreme values agree with eligibility |
| Waveform lists, calculated rows and plot legends | Backend effective unit/status plus shared presentation helpers | Browser regression run; independent mode/base transitions inspect arrays, unit and raw trace identity |
| A/B cursor values | Shared scalar dispatch and frontend request-generation fences | Independent stationary-cursor round trip and saved-base edit; no extra cursor movement required |
| Anchors, annotations and peaks | Shared raw/calculated conversion, retained sample/time identity | Independent Manual endpoint parity; backend endpoint and browser annotation/modal regressions |
| Calculated Current provenance | Same live Current resolver as value consumers | Automatic common-base / manual / unassigned origins and actual effective bases agree |
| Event Reconstruction | Same value endpoints; separate page mode/cache, source-scoped refresh | Backend integration and complete browser selection; no independent PU arithmetic introduced |
| Compliance | Shared Voltage reference/unit/conversion path and zero-valued readiness probe | Raw Source Default oracle plus actual RMS waveform parity; current scope is Voltage-only |
| Calculated operations and definition/preview lists | Physical engineering arithmetic and units | Independent 8398 A result; definitions/previews stay ENG; no double normalization |
| Power Calculator / phasors / calculated Power | Physical engineering inputs, not PU plot arrays | Unchanged numerical ASTs and full backend/browser Power regressions |
| Source Default derived-base editor preview | Separate cosmetic JavaScript formula | **FA-001: finite valid extremes can display `Infinity kA`** |

`consumer-call-inventory.json` records 44 central resolver/dispatcher call
sites. All four calculated value consumers in `calculated_channel_service.py`
(waveform, cursor, peak and anchor) pass the live source/default/group/config/
assignment registries needed by Stage 5A/5B. No active Current value consumer
was found bypassing result-specific resolution.

Compliance's calculated adapter does not carry the new Current-only context;
the product explicitly gates Compliance to Voltage. This is not an active
Current Compliance defect. Any future Current Compliance extension must wire
that context and add tests rather than assuming the Voltage adapter suffices.

Frontend review covered immediate mode publication, mode/display generations,
cursor/anchor request fences, metadata invalidation and exact-result/source
refresh. Relevant paths include `wwApplyUnitMode`,
`wwRefreshWaveformDisplayBasis` and cursor transport. Browser probes delay real
responses and compare full-precision arrays, not only visual text. No new
unconditional workspace-wide polling or network refresh system was introduced.

## 8. Regression results

### Environment and commands

Windows, Python 3.12.10, pytest 9.1.1, NumPy 2.4.6, FastAPI 0.141.1,
Pydantic 2.14.1, Node 24.15.0, Playwright 1.62.1 and Chromium 151.0.7922.34.
The host reports 14 logical CPUs and 16,565,342,208 bytes RAM.
Existing pinned environment
was reused; no dependency installation/upgrade was performed. Local application
servers use the production app factory and temporary storage. Browser
acceptance runs use one worker and **zero retries**.

Full backend, from `backend/`, with `PYTHONDONTWRITEBYTECODE=1`:

```text
.venv/Scripts/python.exe -X utf8 -m pytest -p no:cacheprovider
  --basetemp <evidence>/pytest-full
  --junitxml <evidence>/backend-full.xml --tb=short
```

**11,315 passed, 320 skipped, zero failures/errors, 21 warnings**.
Pytest reports 919.50 seconds; JUnit 919.223 seconds; wrapper wall time
924.680 seconds. The 320 skips are 153 absent owner PDF cases, 49 unconfigured
BEN-reference cases, 17 POSIX-shell cases on Windows and 101 relay applicability
cases. They are not passes. Warning categories are existing Starlette/httpx,
HTTP 422 constant, pytest classmethod-fixture and relay-regex deprecations,
plus expected malformed/duplicate COMTRADE fixture warnings.

The following **525 dedicated remediation cases** all pass inside that full
suite; these counts must not be added to the full-suite total:

| Module | Passed |
|---|---:|
| `test_per_unit_atomic_updates` | 36 |
| `test_per_unit_atomic_publication` | 9 |
| `test_per_unit_eligibility_integration` | 69 |
| `test_per_unit_numeric_integrity` | 164 |
| `test_current_effective_base_inheritance` | 132 |
| `test_current_effective_base_graphs` | 22 |
| `test_reference_side_configuration` | 31 |
| `test_calculated_current_manual_config` | 62 |

### Complete browser coverage

**All 1288 distinct cases in all 90 tracked browser files pass with the
appropriate documented prerequisites, zero browser retries and zero skips.**
This is complete coverage across two environments, not one clean initial run.
`browser-selected-files.json` enumerates every tracked `.spec.js` file.
The two pre-existing untracked screenshot scripts are deliberately excluded.
The temporary config retains repository assertions and uses explicit
`testMatch`, `webServer: []`, isolated JSON/JUnit/artifact outputs and zero
retries. The manually owned backend/frontend serve unchanged local code on
8000/8101; no DEV endpoints are used for this full suite.

| Execution | Passed | Failed | Skipped / flaky / global errors | Duration / wrapper | Exit |
|---|---:|---:|---|---|---:|
| All 90 files, standard backend, BEN5K flag off | 1266 | 22 (13 timeouts, 9 failed assertions/API calls) | 0 / 0 / 0 | 3403.508 s / 3405.571 s | 1 |
| All five BEN5K-dependent files, flag enabled | 38 | 0 | 0 / 0 / 0 | 75.662 s / 76.876 s | 0 |

The first pass omitted `BEN5K_EXPERIMENTAL_ENABLED=1`. Its 22 failures all occur
at BEN5K upload, before the intended timing/waveform assertions. Captured UI
state shows the unsupported-layout message; direct API failures report
`unsupported_ben_variant`. Failure distribution is 9 GPTH, 6 Permas Jaya,
3 timezone, 3 time-reference interpretation and 1 timing-authority invalidation.
This was a test-environment prerequisite error, corrected without changing
application code or test expectations.

An isolated backend with the required flag, fresh storage and frontend runtime
configuration on 8200/8102 runs these five **complete** files:

- `ben5k-gpth-uat.spec.js`
- `ben5k-permas-jaya-uat.spec.js`
- `ben5k-timezone.spec.js`
- `time-reference-interpretation.spec.js`
- `timing-authority-invalidation.spec.js`

All 38 pass. The earlier three-file prerequisite check also passed 23 cases in
47.008 seconds (wrapper 48.357); it is overlapping supplemental evidence, not
additional unique coverage. The temporary frontend's `index.html` SHA-256
matches the source; only its runtime API URL differs. No repository
configuration was changed.

`browser-summary.json` and `browser-case-inventory.json` verify the exact
1288-case/90-file inventory using suite ancestry, source location, title and
project. Every case in both acceptance executions has one attempt with retry
number zero. The corrected five-file inventory exactly matches those files in
the original run; the other 1250 cases pass in the original environment. No
case is discarded. `browser-first-pass-failures.json`, original logs and
screenshots preserve all 22 failures.

Runner output contains the same `NO_COLOR`/`FORCE_COLOR` warning from 23 worker
processes in the first run and one in the final prerequisite run. There is one
slow-file advisory for `oscillation_setup.spec.js` (6.1 minutes). Neither is a
test failure. Both reports contain zero global execution errors.

Selected disjoint file groups within the 1288-case total include:

| Browser files | Passed |
|---|---:|
| Calculated Current Manual PU | 12 |
| Current common base | 3 |
| Event Reconstruction PU | 8 |
| PU atomic updates | 1 |
| PU display synchronization | 26 |
| PU eligibility | 3 |
| PU numerical integrity | 4 |
| Calculated Power, its labels, Power/Current Calculator, V-I Phasors Calculator, Calculator entry and three-phase Power | 112 |
| Four Compliance files (`compliance`, measurement, readiness, workspace) | 82 |

The seven PU-specific rows total 57; these and the other subsets must not be
added to the full browser total. Reference Profiles, recording import,
Measurement Groups, Source Defaults, timing, lifecycle, shared notation and
existing waveform behavior are also included in the complete file inventory.

### Independent checks and diagnostic attempts

| Evidence | Fresh result |
|---|---|
| `independent-api-v2.json` | Six grouped API/state scenarios pass |
| `independent-numerics.json` | Independent nominal/edge/unit oracles and 4096 random cases pass |
| `independent-side-rms.json` | Eight side/authority scenarios, actual RMS and Voltage restriction checks pass |
| `independent-browser-v2.json` | Two browser race/cursor cases pass, zero retries, 12.4 seconds |
| `preview-observation-v4.json`, `preview-finding-v4.json` | One diagnostic passes by **reproducing FA-001**, including visible field/screenshot and correct saved values |
| `performance-and-invariance.json` | Numerical AST invariance, immutable arrays, live graph change and bounded benchmarks verified |
| `historical-secondary-applicability.json` | Original LIM-001 boundary reproduced; incompatible new Manual rejects, compatible explicit Secondary Manual works without input mutation |
| `dev-version-recheck.json`, `dev-version-final.json` | Strict TLS, backend health and frontend runtime SHA match approved commit |

Earlier temporary diagnostic attempts are retained. An API probe initially
expected deletion of a parent with dependents to succeed; the corrected probe
checks the documented rejection, retained Manual state, then deletes child and
parent. An initial browser probe had a route-release/unroute race in its own
harness. Preview diagnostic attempts also had an unrelated setup precondition
and an incorrect response-field lookup before using the documented nested
`resolved_current_base.value` response. These are not classified as product
failures or erased from the evidence. No repository tests were weakened.

## 9. Performance assessment

Measurements use warmed, alternating paired calls, median of 15 on fixed
datasets. The backend suite had completed; another browser process was active.
These are local observations, not a concurrency SLA or a baseline release
speedup claim. Actual configured conversion and physical-array hashes were
checked, avoiding a misleading benchmark of unavailable-conversion fallback.

| 500,000 samples / 20 groups / 4002 returned points | ENG median | PU median | PU/ENG |
|---|---:|---:|---:|
| Voltage | 42.646 ms | 47.339 ms | 1.110 |
| Current | 38.142 ms | 44.816 ms | 1.175 |

| Vector length | Conversion median | Bounds median | Output bytes | Traced peak allocation |
|---|---:|---:|---:|---:|
| 4,000 | 0.053 ms | 0.038 ms | 32,000 | 64,720 |
| 500,000 | 9.056 ms | 4.842 ms | 4,000,000 | 8,000,720 |
| 2,000,000 | 34.377 ms | 18.525 ms | 16,000,000 | 32,000,720 |

Outputs do not share writable input memory; inputs remain unchanged.
Tracemalloc measurements do not certify total process RSS or long-lived
browser heap. Bounds checking is intentionally O(n) over the full channel even
when a reduced viewport is returned; scalar calls can incur that eligibility
cost too. Conversion/output allocation is linear. No significant regression
requiring speculative optimization was demonstrated by these measurements.

The dependency traversal visits each unique calculated ancestor/source leaf;
graph work is O(V+E), plus source metadata lookup and whole-result bounds work.
A unary chain at depths 1/10/50/100/300 took approximately
0.065/0.100/0.213/0.437/0.704 ms, with 0/9/49/99/299 calculated-dependency
registry gets (not a count of all other registry lookups). A live base
edit from 2 to 4 kA was observed at depth 300. Very deep graphs beyond 300,
many concurrent workspaces and retained-browser-memory soak tests are not
certified by this audit.

Source-isolation and stale-response regressions check refresh targeting.
Code review found no new persistent automatic-base cache, cross-source fetch
fan-out or unconditional polling. Network request counts are covered by
existing focused browser assertions; this audit does not claim a separate
production network-load benchmark.

Atomic group publication copies the complete registry's group and reverse-
index maps. That configuration-write cost is O(total registered groups and
references), including other workspaces, rather than O(changed membership)
alone. A separate owned-registry benchmark across ten workspaces, five warmups
then 30 measured updates, gave the following results. Identity and indices
remained consistent. This is metadata-only registry latency, not full API
latency, and is recorded in `registry-publication-benchmark.json`.

| Total groups / reverse entries | Median update | Traced peak allocation |
|---|---:|---:|
| 20 / 60 | 0.0256 ms | 5,716 bytes |
| 1,000 / 3,000 | 0.0943 ms | 184,892 bytes |
| 10,000 / 30,000 | 2.74735 ms | 1,606,188 bytes |

No material configuration bottleneck was demonstrated at these sizes. The
global-map copy remains a scaling limitation to reassess if registry size or
write contention becomes substantial; this audit does not replace the atomic
mechanism with an unapproved optimization.

## 10. Backward-compatibility assessment

| Contract | Assessment |
|---|---|
| DEC-050/051 Measurement Groups | Identity, source ownership, quantity, member restrictions, reverse indices and review gate preserved; atomicity restored |
| DEC-052/115/116 Voltage representations | Generic arithmetic does not become an approved L-L result through naming; representation inheritance remains restricted |
| Source Default and legacy paths | Existing fallback scope preserved; no borrowing across authoritative grouped inputs |
| Manual principle | Result-specific configuration takes precedence without altering inputs; no bypass of physical safety |
| Physical waveform storage | Unchanged; conversion returns separate output arrays |
| Voltage/Current mathematics | Same nominal L-L, L-G/L-L, instantaneous/RMS and applicable three-phase formulas |
| COMTRADE scaling | P/S metadata propagated independently; existing `a*x+b` sample scaling unchanged |
| Power Calculator / phasors / calculated Power | Numerical implementation unchanged from comparison baseline; covered by full regressions |
| API compatibility | Existing status/source-kind vocabulary retained; documented additive side/origin/config fields and manual provenance A unit require strict clients to accept additions |
| Workspace lifetime | Existing ephemeral model retained and accepted by owner |

AST comparisons against `d8ade8f` show no changes to calculated arithmetic,
Power calculation, sliding phasors, phasors, L-L Voltage calculation or
COMTRADE `_apply_analog_scaling`. These structural comparisons support, but do
not replace, numerical and integration tests.

## 11. Remaining risks and deferred issues

### FA-001 — finite valid derived Current base previews as Infinity

**Severity: Low. Status: newly confirmed, unresolved; owner review required.**
Affected code: `frontend/index.html`,
`wwPerUnitEditorResolvedCurrentBaseText`, approximately lines 34988–35014 at the
audited commit. Its cosmetic formula multiplies MVA by `1_000_000` before
division, unlike the stable backend derivation.

Reproduction on a source with a resolved Voltage reference:

1. Open Source Default — Per-Unit; select Calculate from apparent power.
2. Enter nominal L-L Voltage Base `1e300` kV and Apparent Power Base `1e308` MVA.
3. The visible Calculated Current Base field reads **`Infinity kA`**.
4. Save succeeds. The API reports a finite
   `57,735,026,918.96258 A` (`57,735,026.91896258 kA`) base.
5. Fresh waveform PU values equal physical amperes divided by that finite base.

For the value comparison, use genuinely ungrouped Current channels so Source
Default is authoritative. The independent probe removes the fixture's groups
in its own temporary workspace; it does not change unrelated workspace data.

Evidence: `preview-finding-v4.json`, `preview-observation-v4.spec.cjs`, its JSON
result and `finite-base-infinite-preview-visible.png`. Independent expected
base: `57,735,026,918.962585 A`.

Impact: incorrect preview for extreme accepted finite inputs; the save,
authoritative base and actual numerical results are correct. Ordinary equipment
ratings do not approach the reproduced range. No claim of complete consumer
display consistency can include this case while it remains unresolved.

**Proposed focused remediation:** make the preview use overflow-safe scaled
derivation or an authoritative preview value and finite-value formatting; add
an extreme finite browser regression. Do not impose an arbitrary physical cap
or modify PU mathematics. This audit has not implemented that proposal.
Benefit: the preview would agree with the accepted finite base. Expected
impact is limited to editor presentation. The main implementation risk is
changing nominal L-L/SI semantics while replacing the formula, so focused
nominal, extreme and reference-mode checks should accompany any approved fix.
Recommendation: owner may explicitly accept this as a documented nonblocking
limitation or approve the focused fix and revalidation before final acceptance.

### Deferred-item reassessment

| Item | Classification | Evidence, boundary and proposed next step |
|---|---|---|
| CSV/BEN measurement side Unknown | Acceptable documented limitation | Providers do not carry the independently established side needed by new cross-authority decisions. Independent Unknown-side cases fail closed. Add a provider/sample-side contract only by approved future design; never infer it from manual Ibase. |
| Secondary/Secondary across authorities | Acceptable documented limitation | Independent automatic/manual cases reject; same numerical base does not establish one shared secondary reference. Future shared-reference identity design needs owner approval; no automatic ratio scaling. |
| Ephemeral workspace persistence | Acceptable documented limitation | Same live workspace retains modes; new workspace/reimport/server restart does not restore them. Matches approved architecture and explicit owner acceptance. |
| CSV post-conversion discovery identity | Separate future improvement; existing Medium workflow defect | Independently reproduced: canonical conversion assigns a new source UUID, but post-conversion discovery is called with the preparation UUID; automatic groups remain absent. `api/v1/preparation_sources.py:1189` passes the old ID. Correct canonical-source identity and group-discovery regression require separately approved work. Not fixed or newly introduced by this release. |
| O(n) full-vector bounds | Acceptable documented limitation; potential future optimization | Measured linear costs above. Full-channel numerical integrity is intentional. Optimize only with equivalent invalidation/whole-channel safety and evidence of a material bottleneck. |
| Live linked-base resolution | Acceptable documented limitation / intended behavior | Accepted Voltage/base/group edits change effective linked values live. Rejected edits do not. Separate accepted registry edits are not a global snapshot; no denormalized permanent base cache. |

**Original LIM-001, retained reference applicability limitation:** a recorded
secondary ampere is not an equipment-primary ampere. The legacy raw/single-
authority paths can still return `configured` for incompatible sides; Stage
5A deliberately does not redesign those paths. This is an engineering
applicability risk with potentially large numerical consequences when used
incorrectly, not a failure of division or permission to add CT scaling. It is
classified as an acceptable documented limitation only within the previously
approved scope and subject to explicit owner acceptance of that boundary.

Potential engineering impact is **High if reference sides are misapplied**;
this is an existing applicability limitation rather than a new release defect.
Affected paths include `providers/comtrade.py::_apply_analog_scaling`, raw
group-aware resolution and the historical single-authority branch in
`services/calculated_current_per_unit.py` (side guard around lines 146–152).

The fresh `historical-secondary-applicability.json` probe uploads COMTRADE with
gain 0.5, CT 2000:1 and marker S, sets a 2 kA Primary group base and observes
0.00025 pu. A compatible 1 A Secondary manual result gives 0.5 pu. This
independently reproduces the original audit's factor-of-2000 applicability
example, while verifying the new Manual workflow does not bypass reference
validation. A broader historical raw/single-authority side guard or scaling
workflow would require separate owner design approval, explicit provenance and
backward-compatibility tests. No such change is made here.

The independent CSV reproduction records distinct preparation/canonical IDs
and zero discovered groups in `independent-api-v2.json`; backend logs contain
the failed discovery lookup. It must not be reported as repaired merely because
unit-eligibility PU-003 is repaired. Manual grouping remains the established
explicit configuration route. No automatic grouping correction is authorized
here.

Reproduction: prepare a CSV Voltage column and valid time axis, convert the
preparation session, inspect the returned canonical source identity, then list
its Measurement Groups. In this run preparation
`bcdbf3db-e2d1-4d5a-95c2-a89d9efa5d61` creates canonical source
`2daa739e-3079-45fe-959b-335eeb79ad20`, but discovery is called against the
former and the canonical source has zero groups. The focused future correction
would pass the returned canonical identity to the existing shared discovery
helper and verify group/context ownership and post-conversion readiness.

Other limits: Windows skips do not certify POSIX entrypoints; optional BEN/PDF
reference corpora were not configured for backend tests. Historical shared-
authority Unknown-side compatibility is preserved rather than retrospectively
certified. Extreme-depth/load/heap soak behavior is outside the measurements.
There is no new general single-phase equipment-rating model.

## 12. Final recommendation

**CONDITIONAL PASS — Ready subject to stated conditions.**

All eight original defects pass independent revalidation. Stage 5A/5B math,
authority, side validation, manual lifecycle and consumer propagation pass the
fresh checks. The full backend passes and the complete tracked browser
inventory passes with correct prerequisites. No newly demonstrated
release-blocking defect remains within the approved remediation scope.
FA-001 and the retained applicability/deferred boundaries prevent an
unqualified acceptance recommendation.

Conditions proposed for owner review:

1. Review FA-001 and either explicitly accept its bounded preview limitation or
   authorize a focused correction with revalidation before final acceptance.
2. Retain the documented reference-side, Secondary, persistence, CSV-discovery
   and performance boundaries; do not describe them as fixed or fully certified.
3. Review final regression inventory and remaining environment-specific skips.
4. Give explicit final acceptance/merge authorization. This report and
   provisional DEV UAT do not themselves authorize a merge or deployment.

DEV was rechecked at **2026-11-05 12:26:55 UTC** (and earlier at 11:56:48 UTC)
using strict TLS and Node
`--use-system-ca`, with no disabled verification or `ignoreHTTPSErrors`.
Backend `/health.git_sha` and frontend `/config.js` `buildVersion` both match
`265f1906d4a6c30568309dd45ffa5e41cbb236ce`. Hostname validation succeeds and a
wrong hostname is rejected. Windows-trusted corporate inspection CA is used;
no trust store, certificate/key export or application configuration is changed.

Final Git state: branch `feature/calculator-vi-phasors`, HEAD and upstream
`265f1906d4a6c30568309dd45ffa5e41cbb236ce`, zero ahead/behind after fetch.
`origin/main` remains `d8ade8f04dde5df2654082a784adbebb064a7336`.
Tracked and staged diffs are empty. The only new repository file is this
uncommitted report. Existing untracked paths remain:

```text
.audit/
.slice1-evidence/
browser-tests/compact-label-screenshots.spec.js
browser-tests/e3b-screenshots.spec.js
test-results/
```

At **2026-11-05 12:26:57 UTC**, all 2250 protected files match the original
manifest in SHA-256, size and modification timestamp, with zero additions,
removals or changed files (`protected-files-final.json`). The original audit
report SHA-256 remains
`e98310e2d3618d22b2468df3c878904e6e2009bf94ba4f338c1603c740ec256b`.
Fresh test evidence remains in the isolated temporary directory. No production
code or repository tests were edited; no commit, push, merge, production fix or
deployment was performed. Stop for owner review before remediation or merge.


---

## 13. Owner-authorized follow-up — 6 November 2026

This is an append-only follow-up, not a rewrite of the audit or its conditional
verdict at `265f1906d4a6c30568309dd45ffa5e41cbb236ce`. Sections 1–12 above remain
historical evidence. Their original 42113 bytes have SHA-256
`143117e511c6237d8e6dd7c21b6a1b47d50493b84626b3f567b2485b51d42f42` and are
preserved byte for byte as the prefix of this file. The owner separately
approved FA-001 remediation and LIM-001 assessment, with no LIM runtime change.

### FA-001 — fixed and verified locally

Focused local commit: **`384a55fafbbecf7e304aa9ea8cfc663554177fd1`**,
`fix(ui): stabilize Source Default current-base preview`, parent `265f1906`.
Exactly five files: frontend preview helper/formatting; new seven-case browser
regression; two existing static formula guards; and
[FA-001 implementation record](PER_UNIT_AUDIT_FA_001_2026-11-05.md).

The example now displays **57735026.9190 kA**, consistent with the unchanged
backend's finite accepted base. Tiny positive previews no longer display false
zero. Invalid/unrepresentable inputs display unavailable. Nominal L-L semantics,
ordinary 132/275 kV values, reference modes, submitted inputs, saved configuration,
PU mathematics, physical samples, linked groups and Power remain unchanged.

Fresh follow-up evidence (implementation/tests 5 November; local closure 6 November):

- New browser baseline: **3 failures / 4 passes**; corrected: **7/7**, no retries.
  Original failures target finite-extreme Infinity, false-zero and invalid previews.
- Numerical: **4352** boundary/random cases; zero backend representability
  classification differences and zero ULP differences for admissible values.
  Independent 180-digit Decimal maximum difference: 2 ULP. Ten invalid helper
  inputs return unavailable.
- Relevant browser: **158/158** in 14 complete explicit files; zero failures,
  skips, flaky cases, global errors or retries. Includes PU atomicity, display
  synchronization, manual/nested Current, ER, Power and shared labeling/notation.
- Relevant backend: initial 105-module run **3742 passed / 2 failed / 17 skipped**,
  three existing warnings. The two failures were source-text guards requiring
  the old overflowing expression. Both complete corrected guard modules then
  passed **22/22**. Combined unique inventory: **3744 passes / 17 POSIX-only
  Windows skips / no unresolved failure**. No production code changed between
  those runs. This is not a fresh full-backend rerun or an initially clean run.
- Separate overlapping visual case passes and captures the real finite field
  and accepted backend save. Full prior audit results remain baseline evidence.

### LIM-001 — assessed; implementation awaits owner policy review

The [dedicated assessment](PER_UNIT_AUDIT_LIM_001_ASSESSMENT_2026-11-06.md)
provides the current behavior, physical risk, code-path/consumer map, complete
reference matrix, compatibility impacts, proposed API/UI scope, tests and options.
**56/56 isolated characterization probes confirm current behavior**, including
unsafe outputs; they are not passing LIM-001 remediation acceptance tests.

Raw Current, same-authority Automatic/nested results, and legacy internal
assignment fallback can still configure known incompatible references.
Waveform/cursors/anchors/peaks/provenance and raw coverage share that historical
omission. New cross-authority Automatic and result-owned Manual retain their
strict compatibility rules. A latent context-free internal Compliance helper
also needs deliberate treatment before future Current reuse; existing public
Compliance is Voltage-only and no unrelated correction is made.

The owner approved the principle prohibiting known Primary/Secondary mixing
without validated conversion. The assessment proposes centralized reference
eligibility after selecting the final normalization base, preserving independent
Manual override. It distinguishes known compatible, known incompatible and
Unknown/unverified. Existing group/direct/result base-side controls cannot
establish missing recorded sample side.

**Owner decision remains necessary:** option A blocks known conflicts everywhere
while explicitly identifying historical Unknown raw/single-authority PU as
Unverified (bounded recommendation, requiring residual-risk acceptance); option B
makes Unknown Current PU unavailable universally, affecting CSV/BEN/unmarked
recordings and historical manual/direct bases. Restoring those Unknown workflows
under B would need a separately approved measurement-side design. Neither option
infers side, rescales CT/VT samples or adds permanent storage.

### Git, evidence preservation and stop boundary

Branch: `feature/calculator-vi-phasors`; HEAD `384a55f`, one ahead / zero behind
fetched upstream `265f1906`. Main remains `d8ade8f`. The FA-001 fix is local only.
This original report plus addendum, LIM-001 assessment, CURRENT_STATE and HANDOFF
remain uncommitted for owner review; none is silently included in the focused fix.

At **2026-11-06 00:55:22 UTC**, all **2250 protected files** matched their original
SHA-256, size and modification timestamp, with zero additions/removals/changes.
The original `.audit/per-unit-2026-10-31/AUDIT_REPORT.md` hash remains
`e98310e2d3618d22b2468df3c878904e6e2009bf94ba4f338c1603c740ec256b`.
No existing evidence or untracked screenshot test was staged or modified.
New outputs are isolated in:

```text
C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-followup-20261105-0c938079ecc74c33a4025c18138a7666/
```

No push, merge or deployment. No LIM-001 runtime restriction, new scaling,
persistence or other feature was implemented. FA-001 is locally closed;
LIM-001 and final PU acceptance remain pending explicit owner review.


## LIM-001 implementation follow-up - 2026-11-07

This is subsequent evidence, not a rewrite of the original audit's conclusions
at baseline 265f1906. The owner approved DEC-210 option A and a focused local
implementation. Known Primary/Secondary mismatch now blocks Current PU across
raw, group/default, legacy and calculated/nested consumers. Historical raw and
single-authority Unknown conversion keeps its numbers with explicit Unverified
reference disclosure. Stage 5A cross-authority and Stage 5B Manual restrictions
remain strict; valid independent result Manual still supersedes input bases.
No CT/VT scaling, side inference, physical sample change or PU/Power formula
change is introduced.

For the original 2000:1 CT reproduction, 0.5 A Secondary plus 2 kA Primary no
longer returns 0.00025 pu as valid conversion: it returns base_required with
incompatible reference metadata and retains 0.5 A ENG. No 0.5 pu substitute is
fabricated. Historical Unknown retains its approved direct division as
Unverified. Real CSV/BEN imports, all value consumers and rejected-save complete
state snapshots are covered.

Focused local commit: b6202fcea18682dccd1b8ec41e080f9e9be953a7
(fix(pu): centralize Current reference-side safety), parent FA-001
384a55fafbbecf7e304aa9ea8cfc663554177fd1.
Branch feature/calculator-vi-phasors is two ahead / zero behind fetched upstream
265f1906d4a6c30568309dd45ffa5e41cbb236ce. The commit contains only 26 scoped
files. Neither this pre-existing untracked audit nor the historical assessment
was staged or committed.

Final full backend: 11,374 passed / 320 existing skips / zero failures or errors /
21 existing warnings, exit 0, 2012.44 seconds. Final complete browser: 1302/1302
actual passes, 92 explicit files, four workers, zero failures/skips/flaky cases/
global errors/retries, exit 0, 2449.365 seconds. All 59 new backend and seven new
browser cases pass. The complete inventory also covers Stage 5A/5B, FA-001,
Voltage PU, linked bases, Power Calculator, three-phase Power and Compliance.
All 871 tested application/test source hashes remain unchanged.

The six intended pre-fix failures and initial full-suite failures remain in
evidence. A new Text Note adapter regression and narrowly scoped static/
response/readiness assertions were corrected. The 65-case complete affected-file
rerun and complete final runs pass. Temporary Windows PowerShell launcher faults
and their interrupted output are retained separately, not counted as acceptance.
No timeout/retry setting or meaningful numerical/identity assertion was weakened.

All 2250 protected files passed SHA-256, size and nanosecond-mtime comparison,
with no added files, at 2026-11-07 01:27:23 UTC. The original audit report remains
e98310e2d3618d22b2468df3c878904e6e2009bf94ba4f338c1603c740ec256b (SHA-256).
The assessment is byte-identical; this report's entire 47,966-byte task-start
prefix is preserved before this addendum.

Complete policy, changed-file list, numerical reproductions, exact test evidence,
performance observations, skips, limits and Git boundary:
[PER_UNIT_AUDIT_LIM_001_IMPLEMENTATION.md](PER_UNIT_AUDIT_LIM_001_IMPLEMENTATION.md).
New outputs only:
C:/Users/fairizat/AppData/Local/Temp/oruxa-lim001-f7c1a499069b416097aabd49a5d828e5

LIM-001's local acceptance checks pass. Overall PU audit acceptance still
requires owner review; no automatic full closure is claimed. Historical Unknown,
shared Secondary identity, CSV/BEN side declaration, the separate CSV discovery-ID
defect, CT/VT conversion and durable workspace life remain bounded/deferred.
No push, merge, CI dispatch or deployment was performed. DEV was last observed
at 265f1906; no new deployed-version claim is made. Stop for owner review.


## Final release preparation authorization - 2026-11-07

The owner accepted the LIM-001 policy and authorized reviewed documentation,
normal feature-branch push, required CI, exact-commit manual DEV deployment
and actual deployed smoke. This supersedes earlier deployment pause notes only
for that explicit scope; main merge, PROD and automatic final owner acceptance
remain unauthorized.

FA-001 (384a55f) and LIM-001 (b6202fc) pass local acceptance. All 871 tested
application/test hashes remain unchanged. Historical conclusions and earlier
failure records above are preserved, not rewritten. The dated LIM assessment
is archived unchanged and superseded by DEC-210. Both previously untracked
memory reports are now included in the reviewed documentation release commit;
the protected audit/evidence directories and screenshot specs are excluded.

Strict system-CA TLS/hostname preflight at 2026-11-07 01:59:42 UTC confirms
DEV frontend/backend still match 265f1906, environment development, healthy API.
New CI, deployment and post-deployment smoke are pending at this preparation
checkpoint. Do not infer them from local acceptance. The final release SHA is
the documentation commit containing the new release record; its parent is b6202fc.

Exact release delta, unchanged-code evidence, deployment gates, rollback plan,
synthetic deployed smoke and remaining limitations:
[PU_FINAL_RELEASE_DEV_VERIFICATION_2026-11-07.md](PU_FINAL_RELEASE_DEV_VERIFICATION_2026-11-07.md).
Actual execution results will follow in a separate documentation-only record.
