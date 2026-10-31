# Per-Unit audit remediation — Slice 1

Date: 2026-10-31. Scope: PU-001 and PU-002 only. Owner-authorized defect
remediation restoring the existing configuration contract; no new engineering
decision. The original `.audit/per-unit-2026-10-31/AUDIT_REPORT.md` remains
unchanged historical evidence (audit baseline `944e98f`).

## Implementation

[FACT] Implementation started at GitHub-verified `58f4964`, on
`feature/calculator-vi-phasors`, tracking and equal to `origin/main` after fetch.
The later Power Calculated Channel commit had not corrected either defect.
The existing frontend edit, concurrent `calculated-channel-power.spec.js`,
DEC-203 addition and separate V-I Pairing HANDOFF section are excluded from this
remediation. Only the Slice 1 HANDOFF hunk belongs to the remediation commit.

- **PU-001:** the Voltage PUT calls `update_voltage_configuration()` once.
  The service validates the nominal base and requested reference together.
  The registry constructs an independent configuration, prepares its return
  copy, and publishes one dictionary entry under its existing lock. A failed
  candidate never creates or modifies an authoritative configuration.
- **PU-002:** the group PATCH calls `update_group()` once. The service checks
  status and all supplied members before the registry applies either. Under
  its existing lock the registry merges into the latest group, rechecks
  duplicate/claimed members, and stages independent group/index dictionaries.
  Only fully prepared dictionaries become authoritative. Allocation, copying
  or hashing failures during staging leave both old dictionaries intact.
- Existing individual service setters use the same field-update paths.
  Merging omitted fields inside the lock prevents overlapping partial edits
  from restoring stale values. The registry still owns defensive copies.

Omitted/null nominal voltage preserves the existing base. The Voltage API's
default reference mode remains `auto`, which clears the override. Manual mode
requires an explicit valid reference even if an earlier manual override exists.
Omitted/null PATCH fields preserve their current values; supplied membership
replaces the whole list. Group identity, source, quantity and creation time
are retained. Current base records stay associated with the same group id.
Linked equipment-current denominators continue to read the accepted nominal
L-L base live, independently of Voltage reference mode.

No conversion/domain mathematics, precedence, calculated inheritance, physical
samples, Power Calculator, Sliding Phasor, frontend or infrastructure code was
changed. DEC-050/051/052/115/116, Source Default and legacy source-wide
configuration retain their existing rules. The audit's cross-group Current
policy conflict PC-001 and PU-003 through PU-008 remain outside this slice.

## Regression evidence

`test_per_unit_atomic_updates.py` adds 36 API cases. Before correction, **15
failed and 21 passed**, with no errors/skips: two missing-reference saves
(initial/existing), twelve combined metadata/member rejections (both group
kinds), and one publication-copy failure that corrupted the reverse index.
The first attempted run had a missing test-evidence parent directory and
produced setup errors; the counted reproduction is the subsequent complete run.

Rejected-request snapshots compare every workspace group and base record,
the complete reverse membership index, source-default profiles, group API
views, and fresh PU plus engineering waveform responses for every analog
channel. This proves the review gate, linked Current results, configuration
absence and physical data all survive rejection.

Coverage includes missing/invalid manual references, invalid nominal voltage,
multiple invalid fields, initial/existing configurations, automatic/manual
saves, omitted/null fields, wrong-source/quantity/kind, nonexistent, duplicate
and already-assigned members, invalid metadata, and successful metadata-only,
membership-only and combined edits. Accepted Voltage and linked Current values
are compared independently against `math.sqrt(3)` and SI base calculations.

`test_per_unit_atomic_publication.py` adds nine cases: invalid service
candidates (including values rejected by the API schema), new/existing Voltage
copy failures, index-allocation failure, and controlled overlapping partial
group/Voltage edits. The browser regression drives the real group editor,
passes an incomplete request to the real backend, checks the visible rejection
and unchanged saved/PU state, then successfully saves 132 kV and checks the
analytically expected plotted result. No API responses are mocked.

## Validation and delivery

[FACT] First targeted backend run: **177 passed, zero failures/errors/skips**.
Publication/overlap run: **9 passed, zero failures/errors/skips**.
Broader compatibility: **1,014 passed, zero failures/errors/skips**, including
all 45 new backend cases, group/current/voltage configurations, group-aware PU,
calculated inheritance, DEC-116, measured units, L-L, Power and Sliding Phasor.
Full backend: **10,576 passed, 320 skipped, zero failures/errors**, 20 warnings,
exit **0**, 1,204.8 seconds. All 45 Slice 1 cases are included. The skipped
cases are 153 unavailable owner PDFs, 49 unavailable BEN references, 17 requiring
POSIX `sh`, and 101 relay-case applicability/metadata conditions. Exact reasons
are retained in the JUnit XML; no skipped case is counted as passed.

Selected browser run: **27 passed, 1 failed, zero skipped** (two workers, zero
retries). The new editor case passes. The existing
`line-to-line-voltage.spec.js:382` operation-picker test expects eight cards;
`58f4964` adds the three approved DEC-202 Power cards. A separate diagnostic
serving committed HEAD HTML reproduces the same eight-versus-eleven assertion.
Two earlier full-fixture baseline diagnostic attempts timed out during upload;
they do not establish additional product defects. The final card-only baseline
diagnostic requires no upload and directly reproduces the stale assertion.
The owner subsequently approved a test-only correction, conditional on checking
the approved DEC-202 implementation. DEC-202-A/H, the committed frontend operation
order/labels and API schema confirm all eleven operations, specifically Active
Power, Reactive Power and Apparent Power as the three additions. Only the title
and expected labels were updated; all existing assertions remain. The corrected
test passes **1/1**. The final selected-browser rerun passed **28/28**, zero
failures/errors/skips, two workers, zero retries, in 104.6 seconds. This approved
test maintenance is distinct from PU-001/002 and is committed separately.
The complete repository browser suite has not been run.

Evidence is retained locally under `.slice1-evidence/` (JUnit XML and server
logs), with runner logs `.slice1-*.log`. These generated files and the original
untracked `.audit/` are excluded from the implementation commit.

Dedicated local commits contain the approved browser expectation maintenance
and PU Slice 1 separately. No unrelated concurrent files/hunks are staged.
No push or deployment; GitHub remains unchanged until owner-approved delivery.

## Files in this remediation

| File | Purpose |
|---|---|
| `backend/app/api/v1/measurement_groups.py` | One validated service call for each affected request |
| `backend/app/services/measurement_group_service.py` | Combined metadata/member validation; retained individual entry points |
| `backend/app/services/measurement_group_registry.py` | Merge under lock and stage group/index replacement |
| `backend/app/services/voltage_group_config_service.py` | Validate the complete Voltage edit before publication |
| `backend/app/services/voltage_group_config_registry.py` | One independent configuration replacement under lock |
| `backend/tests/test_per_unit_atomic_updates.py` | 36 whole-state API regressions, accepted saves and linked-current mathematics |
| `backend/tests/test_per_unit_atomic_publication.py` | Nine service, injected-failure and overlapping-write regressions |
| `browser-tests/per-unit-atomic-updates.spec.js` | Real editor rejection followed by accepted save |
| `docs/project-memory/CURRENT_STATE.md` | Current implementation/validation status |
| `docs/project-memory/HANDOFF.md` (Slice 1 hunk only) | Continuation status and stop boundary |
| `docs/project-memory/PER_UNIT_AUDIT_SLICE_1.md` | Mechanism, evidence, compatibility, delivery and limits |

Separate owner-approved test maintenance:
`browser-tests/line-to-line-voltage.spec.js` changes only the outdated test
title and expected operation labels; all remaining assertions are preserved.

## Limits

Atomicity covers each affected update within its owning in-memory registry.
The group update's two internal dictionary references publish while all readers
and writers are excluded by the same existing lock. There is no database,
generic transaction framework, new lock hierarchy or cross-registry rollback.
Same-field concurrent edits retain the established last-writer behavior.
Group edits temporarily copy the group/index maps; the waveform read path is
unchanged. Large-registry update peak memory has not been benchmarked here.

Independent HTTP requests (including the UI's configuration save followed by
confirmation), source deletion, metadata reclassification and workspace teardown
are not one transaction. Exhaustive lifecycle races, process termination and
multi-process persistence are not certified here. These are existing broader
lifecycle limits; this slice introduces no new cross-registry writes or caches.
No DEV/PROD deployment or push is authorized. Stop after Slice 1 for owner review.
