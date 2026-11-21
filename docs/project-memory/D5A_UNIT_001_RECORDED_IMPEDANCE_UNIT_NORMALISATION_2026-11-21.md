# D5A-UNIT-001 — Recorded Impedance and Distance do not normalise channel units

**Status:** CLASSIFIED, **NOT corrected.** Legacy numerics are preserved pending owner authorisation. Found during D5A-2B1 verification.

## 1. Classification

**Numerical-scaling defect, surfacing as a unit-label inconsistency.** The recorded legacy path computes `Z = V / I` from the *raw* channel magnitudes and reports the result in fields named `*_ohm`. The value is in ohms only when voltage and current share the same SI scale. The labels (`magnitude_ohm`, `resistance_ohm`, `reactance_ohm`, `reach_ohm` comparisons) claim ohms; there is no impedance-unit field. So the 1000× difference is a **scaling** error (the number is not in ohms), and the **label** is what makes it misleading — both, with scaling as the root cause.

It is **not an approved numerical contract**: it contradicts the documented ohm contract and golden example (`IMPEDANCE_LOCUS_ANALYSIS.md`: 100 kV / 1 kA → 100 Ω, "never a second unit dictionary"), manual mode (normalises through the shared `engineering_units` layer), and Overcurrent (normalises to amperes). The Recording-mode golden test uses V/A channels, so it never exercised a mixed-scale pair.

## 2. Evidence (observed with the real app, true values 66 kV / 400 A ⇒ 165 Ω)

| Voltage / Current unit | Legacy recorded Impedance | Legacy recorded Distance | Strict (D5A-2B1) | Manual (impedance and distance) |
|---|---|---|---|---|
| V / A | 165 | 165 | 165 | 165 |
| V / kA | **165 000** | **165 000** | 165 | 165 |
| kV / A | **0.165** | **0.165** | 165 | 165 |
| kV / kA | 165 | 165 | 165 | 165 |

Legacy is correct only for same-scale pairs (V/A, kV/kA, whose raw ratio happens to be correct). Pinned by `test_d5a2b1_independent_side_conversion.py` (`test_unit_matrix_*`, `test_legacy_*kilovolt*`).

## 3. Where it occurs

- `impedance_analysis_service._impedance_analysis_from_diagram` → `compute_impedance_point(voltage_role.magnitude_rms, …, current_role.magnitude_rms, …)`.
- `distance_protection_analysis_service._distance_analysis_from_diagram` → `compute_loop_impedance(v1.magnitude_rms, …)`.
- Both are shared by the single-time and the **locus** endpoints, so **Impedance Locus and Distance Protection are both affected**, identically.
- Roles carry the channel's raw unit (`candidate.unit`), echoed as `voltage_unit`/`current_unit`; nothing converts it.
- By code reading (not probed): the 1 mA low-current floor is compared with the raw current, so for a kA channel it behaves as 1 A.

## 4. Consumers of the affected value

- **Distance zone decisions are backend-evaluated from the affected point** (`evaluate_zones(point_out, …)`). Observed: for a kV/A recording a 10 Ω mho reach (true loop impedance 165 Ω) reports **`operated` on legacy** and `not_operated` on strict — a wrong element state (`test_legacy_distance_zone_decision_is_wrong_for_mixed_scale_units`).
- **Frontend** (read-only inspection, not modified): |Z|, R, X and the R-X plot take `magnitude_ohm`/R/X directly (`wwImpedanceFormatOhm(result.magnitude_ohm)`, `wwDistanceFormatOhm`); no unit compensation was found, so displayed impedance and its comparison with zone reaches inherit the error.
- Relay-import / parameter-catalog modules deal with *settings*, not recorded impedance; no other consumer of recorded `Z` was found.
- Phasor and Sequence Components do not produce ohms and carry per-role unit labels; Overcurrent normalises to amperes — not affected.

## 5. Likelihood

Primary-side recordings commonly pair kV voltages with A currents; the repository's own measurement-group fixture does (kV voltage channels, A current channels). That is exactly the 0.001× case. Only V/kA (1000×) and other prefix mixes were not exercised beyond the four combinations above.

## 6. Preserved, not changed

All legacy calculations, response shapes and defaults are untouched. Strict mode (opt-in) is correct for all four combinations. No caller was switched to strict mode.

## 7. Recommended controlled correction (needs owner approval)

1. **Classify and accept the defect** (this document) before D5A-2B1 acceptance.
2. **Correct the legacy recorded path in a separate, small commit:** normalise each role magnitude to V and A with `convert_value_to_canonical` before dividing, and apply the low-current floor in amperes. Unknown/unsupported units → `needs_configuration` (`unsupported_voltage_unit` / `unsupported_current_unit`), consistent with manual mode (decision: today they compute silently).
3. **Make the change identifiable:** bump `ALGORITHM_VERSION` for Impedance and Distance recorded results.
4. **Expected numerical impact:** V/A and kV/kA recordings unchanged (equal within floating-point rounding); kV/A recordings ×1000; V/kA ×1/1000; Distance zone states may change for those recordings (to the physically correct state); locus trails rescale. No stored data is affected (results are never persisted).
5. **Verification before merge:** flip the characterisation tests to the corrected values in the same commit, add a before/after survey over all repository COMTRADE fixtures listing exactly which would change, run the full protection and regression suites.
6. **Coordination:** tell Codex (no frontend change expected, but plot auto-range should be checked).
7. **Interim, non-numerical option:** an additive diagnostic in the D5A-2A context API (`UNIT_SCALE_MISMATCH`) warning when the consumed voltage and current unit scales differ, so the exposure is visible before the correction is approved.

Rejected alternatives: an opt-in `normalize_units` flag (leaves the wrong default in place); migrating callers to strict mode as the only fix (needs D5A-2B2 and Recording Details sides/groups, and leaves other legacy callers wrong).

## 8. Owner decisions required

- Accept the classification (defect, not contract).
- Authorise the legacy correction, and choose unknown-unit behaviour (recommended: block).
- Authorise the interim diagnostic.
- Sequence: before D5A-2B2, or alongside D5A-2B1 acceptance.
- Confirm no caller is moved to strict mode until D5A-2B2.
