# FA-001 — Source Default Current-base preview follow-up

Implementation and tests: 2026-11-05. Local closure review: 2026-11-06.
Owner-approved Part A of the final PU audit follow-up.
Baseline: `265f1906d4a6c30568309dd45ffa5e41cbb236ce`,
`feature/calculator-vi-phasors`. Local implementation; no push, merge or deploy.

**FA-001 is corrected and verified locally.** LIM-001 runtime behavior is not
changed by this fix; final PU acceptance remains subject to separate owner review.

## Correction and scope

The Source Default editor multiplied `1e308 MVA` by one million before dividing
by a finite Voltage base. That intermediate overflow displayed `Infinity kA`
although the backend's accepted base was finite.

`wwPerUnitDerivedCurrentBaseKa()` is the cosmetic counterpart of the established
backend `derived_current_ka()`. It evaluates `Sbase_MVA / (sqrt(3) * VLL_kV)`
directly in kA: the SI powers cancel. Ordinary operation order is preserved.
At floating-point range boundaries it separates mantissas and exponents, avoids
intermediate overflow and avoids rounding a subnormal twice. IEEE-754 exponent
bounds are machine representability limits, not new engineering magnitude caps.

Voltage-base SI representability and final Current-base SI representability
must match backend acceptance. Invalid/unrepresentable candidates display the
existing unavailable marker. Ordinary previews retain four decimal places; a
positive value that would round to `0.0000` uses its nonzero numeric string.
The existing Source Default preview calls this helper; no other editor or
authoritative calculation is changed.

Both automatic and manual L-G/L-L reference modes continue to use the entered
nominal system L-L voltage for equipment-current derivation. The reference
availability gate is retained. Save payloads, inputs, saved configurations,
Measurement Groups, physical arrays, conversion consumers, Power algorithms
and reference-side eligibility policies are unchanged.

## Before/after evidence

| Input | Before | After / accepted backend |
|---|---|---|
| 1000 MVA, 132 kV | `4.3739 kA` | Same; backend 4373.865675678983 A |
| 1000 MVA, 275 kV | `2.0995 kA` | Same; backend 2099.455524325912 A |
| 1e308 MVA, 1e300 kV | `Infinity kA` | `57735026.9190 kA`; backend approximately 57735026918.96258 A |
| 1e-320 MVA, 1 kV | `0.0000 kA` | Nonzero `5.776e-321 kA`, consistent with accepted backend subnormal |
| Unrepresentable derived SI base | `Infinity kA` | Unavailable marker; backend rejects save without changing accepted state |

The new seven-case browser file first ran against unchanged production code:
**3 failed / 4 passed**, 25.6 seconds, zero retries. Failures independently
exercise the finite extreme, false-zero formatting and invalid preview.
After correction: **7 passed / zero failures/skips/retries**, 23.7 seconds.

The first temporary attempt omitted the synthetic fixture's required start
clock and failed at import. It was interrupted, preserved and corrected before
the above baseline run. Those setup failures are not FA-001 evidence.

Real UI tests save and reopen each valid configuration, compare preview to
accepted backend values, verify original input values, and compare complete
Measurement Group views and physical Current waveforms. Invalid saves preserve
the entire accepted Source Default response. Reference-mode tests check both
manual interpretations, no mutation before Save and Return to Auto.

## Numerical verification

The actual helper is extracted from the changed HTML and evaluated with Node;
expected values come from the unchanged backend and an independent 180-digit
Decimal `sqrt(3)` calculation. This avoids testing a rewritten copy of the JS
implementation. Seed: 2026110501.

- 4352 boundary/random cases: 3204 admissible and 1148 unavailable.
- Zero representability-classification differences.
- Zero ULP difference from backend for every admissible case.
- Maximum two ULP difference from independent Decimal mathematics, including
  subnormal boundaries and the existing backend's floating-point rounding.
- Ten invalid helper inputs return unavailable.

## Regression results

The 105 selected backend modules cover 3761 distinct cases. Initial execution:
**3742 passed / 2 failed / 17 POSIX-only skips**, three existing warnings,
472.80 seconds. Both failures were static assertions requiring the old
`sbaseVa / (sqrt(3) * vbaseVolts)` source text. They were updated to verify the
new helper call, the exact equivalent MVA/kV formula and absence of an L-G
reference adjustment. Both complete affected modules then passed **22/22**,
1.37 seconds, no warnings. No production code changed after the initial broad
run. The final combined inventory is **3744 distinct passes / 17 skips / no
unresolved failures**, not a claim that the initial run was clean.

All **158 browser cases in 14 explicitly selected complete files pass**,
494.547 seconds, zero failures/skips/flaky cases/global errors/retries. This
includes the seven new cases as well as PU synchronization, atomicity,
eligibility, numerical handling, Current common bases/manual lifecycle, ER,
shared labeling/notation and single-/three-phase Power. The protected untracked
screenshot scripts are excluded. One Node color-environment warning occurs in
this run; it is not a product error.

A separate visual probe also passes (one overlapping case, 6.888 seconds),
capturing the visible `57735026.9190 kA` field and checking the real accepted
backend save. It is supplemental evidence, not an additional unique regression.
Exact selection manifests, original failures and corrected module results are
retained. Backend selection includes every frontend static-guard module.

The full consolidated backend/browser results at baseline remain historical
evidence in the final audit; they are not described as fresh results for this
changed HTML.

## Files in the focused change

| File | Purpose |
|---|---|
| `frontend/index.html` | Safe Source Default derived-current preview and nonzero tiny formatting |
| `browser-tests/source-default-current-preview.spec.js` | Ordinary/extreme/subnormal, invalid-save, reference-mode and accepted-value regressions |
| `backend/tests/test_frontend_per_unit_source_default_voltage_reference.py` | Preserve the nominal L-L/no-double-adjustment guard through the new helper |
| `backend/tests/test_frontend_per_unit_source_default_voltage_traceability.py` | Preserve the equivalent current-preview formula guard after SI cancellation |
| `docs/project-memory/PER_UNIT_AUDIT_FA_001_2026-11-05.md` | Scoped implementation and validation record |

The previously uncommitted final audit is preserved and is not automatically
included in this commit. LIM-001 is a separate assessment, with runtime changes
explicitly awaiting owner review. Use this file's containing Git commit for the
focused local revision identity.

## Evidence

New outputs only:

```text
C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-followup-20261105-0c938079ecc74c33a4025c18138a7666/
```

Key artifacts: `fa001-before-v2.json`, `fa001-after.json`,
`preview-numerical-summary.json`, `preview-numerical-cases.json`,
`preview-numerical-values.json`, `backend-relevant.xml`,
`backend-updated-guards.xml`, `browser-relevant.json`, `fa001-visual.json`,
`finite-current-preview.png` and exact selection manifests. Existing audit/evidence
directories remain outside all test outputs.
