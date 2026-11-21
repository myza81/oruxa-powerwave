# D5A-2B1 — Recorded Impedance and Distance: Independent Measurement-Side Conversion

> **Superseded in part (DEC-215, 2026-11-21):** a nominal-derived (`auto_nominal`) VT is now valid, consumable engineering configuration. Statements below that call it display-only / not consumable describe the earlier D5A rule. See [D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md](D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md).

**Branch:** `feature/d5a-1-ctvt-authority` · Backend only · Opt-in · Overcurrent, PU, CT/VT calibration, frontend and Source Default untouched.

## 1. API contract and mode selection

Applies to the four recorded endpoints:
`GET …/engineering-contexts/{id}/impedance`, `…/impedance-locus`, `…/distance-protection`, `…/distance-protection-locus`.

New optional query parameters: `voltage_side`, `current_side` ∈ {`primary`, `secondary`}. Existing `impedance_basis` is unchanged and is the **requested output side**.

| Supplied | Mode | Behaviour |
|---|---|---|
| neither `voltage_side` nor `current_side` | **Legacy** | Exactly the historical single-`recording_basis` behaviour. `recording_basis` stays required (same `422` shape when missing). `side_conversion` is `null`. |
| either one | **Strict independent-side** | Never reads `recording_basis`, never infers a missing side, validates against recording evidence, and on any failure returns `needs_configuration` with a reason — **never falls back to legacy**. |

`recording_basis` was made `str | None = None` in the signature only so strict mode need not send it; the legacy path re-raises the identical missing-field `422`. The OpenAPI "required" flag for it therefore changes; runtime behaviour does not. Requests that send both are strict (and `recording_basis` is echoed, ignored).

Responses gain an additive `side_conversion` object (null on legacy):
`{ mode, voltage_side, current_side, output_side, vt_ratio_applied, ct_ratio_applied, voltage_group_ids, current_group_ids, block_code, block_quantity, block_detail }`. Locus responses carry it once at top level; every locus point of a blocked request is `needs_configuration` with the same `reason_code`.

## 2. Authority validation (strict mode)

Order of checks; the first failure is returned as `reason_code` (also `side_conversion.block_code`, with `block_quantity` and `block_detail`):

1. `invalid_impedance_basis` → 2. `voltage_side_required` / `current_side_required` (both are consumed, so both must be declared; never taken from `recording_basis`) → 3. `invalid_voltage_side` / `invalid_current_side`.
4. Channels are resolved through the same role mappings as the compute path (D5A-2A). If any role is unresolved, the compute path reports its own natural status (no side block).
5. Per consumed quantity, over **only the channels the calculation uses**: `voltage_mixed_side_within_quantity` / `current_mixed_side_within_quantity` (declared sides differ) → `voltage_side_authority_unavailable` / `current_side_authority_unavailable` (any consumed channel's side is undeclared — a caller-supplied value cannot stand in) → `voltage_side_contradicts_recording` / `current_side_contradicts_recording` (asserted ≠ declared).
6. Ratios, **only for a quantity whose side differs from the output side**: `vt_authority_unavailable` / `ct_authority_unavailable` (no consumable Measurement Group ratio: `no_group`, `not_configured`, `untrusted_authority`, `invalid`, `conflict`; `auto_nominal` and nominal-only are never ratios) and `request_vt_conflicts_with_authority` / `request_ct_conflicts_with_authority` (a complete, valid request ratio that disagrees with the group beyond 1e-6). Request ratios are never applied.
7. At compute time: `side_plan_channel_mismatch` (the validated channels differ from those consumed), `unsupported_voltage_unit` / `unsupported_current_unit`, then the existing `current_too_small` / `loop_current_too_small`.

Unrelated unused channels never block (tested: Vc/Ic unknown or mixed does not affect loop AB or phase A, but does affect loop BC).

## 3. Numerical implementation

Each consumed quantity is converted **directly to the output side**, then Z is formed once:
`secondary→primary: ×ratio`, `primary→secondary: ÷ratio`, same side: identity (ratio never read). Magnitudes are first normalised to V and A with the shared `convert_value_to_canonical`. Distance converts all four legs, then forms `V1−V2`, `I1−I2` (`compute_loop_impedance`) and evaluates zones in the output basis. Angles are untouched. The low-current floor keeps judging the **recorded** current (`min_current = 1 mA × current_scale`), matching legacy. L-L/L-N interpretation is unchanged (Impedance uses phase quantities; Distance phase-to-phase loops). Distance v1 has no ground/k0 compensation, so "compensated quantities" do not apply.

## 4. Independent test-oracle results

`tests/test_d5a2b1_independent_side_conversion.py` — **70 tests** (84 when this slice was delivered; the 14 legacy-unit tests moved to `test_d5a_unit001_recorded_unit_normalisation.py` when D5A-UNIT-001 was corrected), expected values hand-derived (VT 110000:110, CT 1000:5, 66 kV / 400 A, Z = 165 Ω primary / 33 Ω secondary at +30°):

- All 8 voltage-side × current-side × output-side combinations through `/impedance`, `/impedance-locus`, `/distance-protection` (loops AB, BC, CA) and `/distance-protection-locus`, including exactly which ratios are applied.
- Conversion in both directions, same-side identity, no fabricated value for an unusable ratio, kV normalisation, no double scaling, floor semantics.
- Missing / invalid / untrusted / nominal-only ratios; unknown side; contradictory side; required / invalid sides; request-ratio conflict; mixed sides within a quantity; unrelated channels; blocked locus; unresolved channels; multi-recording isolation.
- **Mutation checks:** swapping the conversion direction fails 26 tests; making the floor judge the scaled current fails 2.

## 5. Legacy backward-compatibility evidence

- All pre-existing protection, engineering-context and phasor tests pass unchanged (see commit report for counts).
- Legacy calls return hand-derived values and equal the strict result for same-side inputs (rel 1e-9/1e-12); `side_conversion` is `null`; missing `recording_basis` still yields the identical `422` shape (compared against a missing `impedance_basis`).
- **Defect D5A-UNIT-001 — since CORRECTED (commit `303d307`):** the legacy path did not normalise units, so mixed-scale pairs were wrong by 10^±3 (kV/A → 0.165 Ω, V/kA → 165 000 Ω for a true 165 Ω). The legacy recorded paths now normalise to volts and amperes; see `D5A_UNIT_001_RECORDED_IMPEDANCE_UNIT_NORMALISATION_2026-11-21.md`. The legacy mixed-side error (33 000 / 6 600 Ω vs 165 / 33 Ω) remains pinned: it is a different limitation that only strict mode resolves.

## 6. Changes per protection module

| Module | Change |
|---|---|
| Impedance Locus (`/impedance`, `/impedance-locus`) | optional `side_plan`; strict branch after role-availability checks; block results; locus block short-circuit |
| Distance Protection (`/distance-protection`, `…-locus`) | same, four legs, zones in output basis |
| Overcurrent | **unchanged** |
| PU / CT-VT calibration / Source Default / H2 | **unchanged** |

New: `domain/side_conversion.py`, `services/independent_side_service.py`, `schemas/side_conversion.py`. Refactor: `resolve_analysis_roles` extracted from the D5A-2A report service (behaviour identical).

## 6a. Decisions taken that the owner may want to revisit

- Strict mode requires **both** sides (both quantities are consumed).
- Strict ratios come only from Recording Details; a conflicting complete request ratio **blocks** rather than being silently ignored or preferred.
- Strict and (since D5A-UNIT-001) legacy modes both normalise units.
- An unresolved channel in strict mode reports the compute path's natural status, with `side_conversion` null.

## 7. Remaining measurement-side authority / data-model questions

See `D5A2B2_MEASUREMENT_SIDE_DATA_MODEL_PROPOSAL_2026-11-21.md`. Until D5A-2B2, an undeclared recorded side cannot be used in strict mode.
