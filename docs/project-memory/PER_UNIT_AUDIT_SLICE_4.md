# Per-Unit audit remediation - Slice 4

Date: 2026-11-03. Scope: PU-006 / PU-007. Based on local `b5d824e`,
branch `feature/calculator-vi-phasors`, three commits ahead and zero behind
the fetched upstream. Owner authorized Slice 4 in the attached task.
No concurrent agent, worktree, reset or unrelated cleanup. Original audit
baseline `944e98f` and protected evidence remain historical records.

## Implementation and numerical contract

**PU-006 fixed.** Positive finite input alone did not prove that SI scaling,
derived current or normalized measurements were representable. Shared pure
domain helpers now validate SI denominators and perform safe scalar/vector
division. Ordinary arithmetic retains the established operation order.
Exponent-separated fallback is used when intermediate overflow or underflow
would otherwise lose a representable answer. A finite subnormal is valid;
no arbitrary voltage, current or equipment-rating limits are introduced.

Canonical kV and kA must produce finite, positive volts/amps. MVA is validated
as finite and positive; its complete MVA/kV current derivation must produce
finite, positive kA and A. A representable derived current is accepted even
when an unnecessary intermediate MVA-to-VA multiplication would overflow.
Current derivation always uses nominal L-L voltage, never a phase voltage.
Voltage group resolution carries an internal SI denominator, scaling before
phase division to preserve subnormal precision; public fields are unchanged.

Current Group and Source Default derived candidates are checked before registry
publication. Existing defensive copies, locks and Slice 1 atomic replacements
remain in place. Numerical/type rejection cannot mutate configuration, group
metadata/membership, reverse indices, inherited assignments or linked values.
No generic transaction, database, synchronization or cache framework is added.

Configuration validity and measurement availability remain distinct. A usable
tiny base can be saved even when a particular recording cannot be normalized.
Finite nonzero input that would yield infinity, NaN or a false zero makes that
channel `base_required`, with engineering values retained by display fallbacks.
Conversion helpers return None for unavailable conversion. A true zero stays
a valid PU zero. Original missing/non-finite sample gaps retain their existing
semantics; they are distinguished from faults created from finite samples.

The shared eligibility check validates full-channel finite magnitude bounds
using NumPy reductions, without a second normalized waveform. Raw/calculated
dispatchers, coverage and provenance use those bounds, so viewports and A/B
cursor batches agree. An unavailable channel cannot claim readiness merely
because its current viewport contains only zero. Existing measured-unit,
representation, group review and precedence guards run first. Provenance
retains a valid resolved base while explaining numerical unavailability in its
existing reason field. Configuration views still describe base availability;
conversion status determines whether measurements can be shown in PU.

Compliance uses the same dispatchers. Its readiness probe is zero rather than
a fabricated measurement of one: one could overflow on a valid subnormal base
even though every actual sample is representable. Readiness and real traces
therefore agree for both valid subnormals and unavailable results.

**PU-007 fixed.** One Pydantic BeforeValidator-backed numeric alias rejects
bool before ordinary float coercion on all seven numeric configuration fields:
Voltage Group nominal kV; Current Group MVA, manual voltage kV and manual kA;
Source Default voltage kV, MVA and direct kA. Integer, float and numeric-string
compatibility is preserved. Voltage omitted/null nominal preserves its value;
Source Default PUT remains full replacement; allowed incomplete/null bases and
Current method requirements retain their existing semantics.

No response field, field type or status vocabulary is added. The existing
configured/base_required/not_applicable statuses remain; new internal numerical
reason strings use the existing reason field. No new engineering decision.

## Independent engineering evidence

| Nominal L-L | Phase voltage base (V), expected = actual | 1000 MVA current base (A), expected = actual | Matching measurements |
|---|---:|---:|---|
| 132 kV | 76210.2355330306 | 4373.865675678983 | 1.0 pu voltage and current |
| 275 kV | 158771.3240271471 | 2099.455524325912 | 1.0 pu voltage and current |

Expected values use independent Decimal calculations, not application
conversion helpers; relative tolerance 1e-12. The existing real RMS regression
uses an instantaneous sine with phase RMS 132/sqrt(3) kV and verifies 1 pu after
warm-up. New browser sine peaks remain sqrt(2) pu at 275 kV and
sqrt(2)*275/132 pu after a valid 132 kV save. Engineering arrays remain unchanged.

A measured 1e308 kV divided by a 1e308 V base legitimately returns 1000 pu,
despite overflow in the naive intermediate numerator. Subnormal
1e-320 V / 1e-320 V remains 1 pu. True zero remains zero. Nonzero quotient
underflow and unrepresentable overflow return unavailable, never configured
false zeros or newly created JSON nulls. 1e308 MVA / 1e300 kV resolves
57735026.91896258 kA (57735026918.96258 A) without overflowing an unused VA step.

An additional deterministic 4,096-case scalar/vector experiment (seed 6007)
matches a 120-digit Decimal reference over normal/subnormal exponent ranges:
zero availability or parity mismatches, maximum relative error for normal
results 2.2144391543939672e-16. Absolute tolerance is the smallest float64
subnormal when applicable. This experiment supplements the committed tests.

## Regression evidence

The counted unmodified baseline has **27 failures / 11 passes / no errors or
skips**, exit 1, in 38 cases. Failures demonstrate boolean coercion, SI overflow,
invalid derived current, invalid effective denominators, false zero/non-finite
results and misleading readiness. Baseline XML/log/exit files remain preserved.

The final dedicated file has **164 cases**. It covers both booleans on all seven
fields with existing and absent configurations, integer/float/numeric strings,
null/omission contracts, nonpositive/non-finite domain inputs, SI and derived
boundaries, stable finite division, scalar/vector parity, gaps, whole-channel
readiness across viewports/cursors, raw and calculated channels, both base
scopes, linked/manual equipment bases, coverage/provenance and Compliance.

Rejected API operations compare complete before/after snapshots: every group,
Voltage/Current/Source Default configuration, reverse membership index, group
view and fresh engineering plus PU waveform response for every analog channel.
This includes linked Current results and absence versus empty configuration.

| Verification | Passed | Failed | Errors | Skipped | Exit |
|---|---:|---:|---:|---:|---:|
| Original-defect baseline | 11 | 27 | 0 | 0 | 1 |
| First corrected dedicated selection | 38 | 0 | 0 | 0 | 0 |
| Existing PU/group compatibility selection | 465 | 0 | 0 | 0 | 0 |
| Expanded dedicated + Slice 3 integration | 233 | 0 | 0 | 0 | 0 |
| Final new browser file | 4 | 0 | 0 | 0 | 0 |
| Final relevant browser selection, 31 explicit files | 389 | 0 | 0 | 0 | 0 |
| Full backend, 11388 collected | 11068 | 0 | 0 | 320 | 0 |

Counts overlap; do not add them as unique cases. Targeted backend runs reported
three pre-existing warnings. Full backend: 21 warnings,
1,040.125 (JUnit) seconds. Skip breakdown: 153 unavailable owner-PDF references, 49 unavailable BEN references, 17 POSIX-only cases and 101 relay applicability/metadata conditions.
All 164 new cases, 69 Slice 3 cases and 45 Slice 1 atomicity cases pass.
All 26 Slice 2 browser cases remain green. Browser selection:
778.447 (runner) seconds, two configured workers, zero retries.

During authoring, three existing integration cases exposed integer waveform
columns in the new reduction (initial=inf on an integer array); float64 bounds
handling corrected that scoped defect. The expanded rerun passes 233/233.
Early new-browser attempts passed the three rejection tests but failed the
recovery setup: direct API writes did not invalidate ER's page cache, and one
attempt left the configuration overlay open. The final test uses the actual
editor, closes the overlay and re-enters ER. An isolated port-in-use startup
attempt executed no tests. All attempts are retained; no product workaround
or weakened numerical assertion is included.

Windows Playwright teardown required stopping only each completed run's two
verified leaf server descendants after test workers exited. No test was
interrupted. Both untracked screenshot scripts were explicitly excluded.
No full-repository browser run, remote deployment, owner-document-dependent
skips or sustained load benchmark is claimed.

## Compatibility and performance

DEC-050/051 ownership, review and base precedence; DEC-052/115/116 inheritance
and voltage representation restrictions; Source Default fallback/legacy config;
L-G/L-L interpretation; RMS versus instantaneous quantities; physical samples;
Sliding Phasor, Power Calculator and three-phase Power algorithms remain intact.
The calculated-channel service change is confined to PU output eligibility.
No production frontend, power formula, CT/VT scaling, cross-group Current policy,
infrastructure or deployment file changes.

Measured local 500,000-sample medians: bounds check 3.574 ms; guarded conversion
6.676 ms; bounds plus conversion 9.645 ms (five repeats, twenty calls/repeat,
while regression processes were active). Bounds are vectorized O(n), read-only,
and not cached. These are local measurements, not a load or deployment SLA.

## Limitations and deferred work

Linked Current bases remain live dependencies rather than persisted derived
numbers. A separately accepted, numerically valid Voltage edit can make the
dependent current formula unrepresentable; its resolver then reports
base_required/effective_base_not_representable, never configured infinity.
Restoring voltage restores conversion without rewriting Current configuration.
Current-base writes with an unusable derived denominator are rejected before
publication. No cross-registry snapshot transaction or new link policy is added.

The separately recorded CSV post-conversion discovery id mismatch remains
unchanged; see the Slice 3 report for evidence and proposed owner-scoped work.
PC-001, CT/VT scaling and other deferred policies remain outside this slice.
No new unresolved product defect was found by the completed regression runs.
Stop for owner review; do not begin Slice 5.

## Files changed

| File | Purpose |
|---|---|
| backend/app/domain/per_unit_numerics.py | Shared finite/SI checks, stable derivation/division and vector bounds |
| backend/app/domain/per_unit.py | Source/shared denominator and scalar/array numerical safety |
| backend/app/domain/voltage_group_config.py | Validate SI voltage and preserve subnormal phase denominator precision |
| backend/app/domain/current_group_config.py | Validate SI current and stable equipment derivation |
| backend/app/schemas/measurement_group.py | Reject booleans before numeric coercion in group requests |
| backend/app/schemas/per_unit.py | Apply the same alias to Source Default requests |
| backend/app/services/current_group_config_service.py | Validate complete derived candidates before publication |
| backend/app/services/per_unit_service.py | Validate Source Default derived candidates before publication |
| backend/app/services/group_aware_per_unit.py | Use the stable internal SI voltage denominator |
| backend/app/services/waveform_service.py | Apply whole-channel numerical eligibility |
| backend/app/services/calculated_channel_service.py | Apply the same check to calculated output only |
| backend/app/services/per_unit_coverage_service.py | Match numerical conversion readiness |
| backend/app/services/per_unit_provenance_service.py | Match readiness and explain numerical unavailability |
| backend/app/services/compliance_series.py | Probe actual eligibility without inventing an overflowing sample |
| backend/app/api/v1/sources.py | Pass immutable channel values to provenance bounds checks |
| backend/tests/test_per_unit_numeric_integrity.py | 164 numerical/type/atomicity/integration regressions |
| browser-tests/per-unit-numeric-integrity.spec.js | Four real editor/Waveform/ER regressions |
| docs/project-memory/PER_UNIT_AUDIT_SLICE_4.md | Implementation, numerical proof, verification and limitations |
| docs/project-memory/CURRENT_STATE.md | Current Slice 4 verified state |
| docs/project-memory/HANDOFF.md | Scoped continuation and stop for owner review |
| docs/project-memory/MIGRATION_PLAN.md | Audit-remediation sequencing/status |

## Evidence and delivery

Fresh isolated TEMP evidence directory:
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-slice4-20261103-rhegcftn`.
It contains baseline/targeted/expanded/full-backend and browser logs,
JUnit XML and actual exit-code files; selected browser files, frozen code
hashes, numerical proof, boundary experiment, performance and linked-dependency
proof. Final SHA-256/size/mtime plus file-list comparison confirms all 2,250
protected files unchanged, with no added/removed protected evidence.

Only the 21 scoped files above belong in the local Slice 4 commit.
Preserve .audit/, .slice1-evidence/, test-results/ and both untracked screenshot
specs. Earlier Slice 1-3 commits remain intact. No push, merge or deployment.
