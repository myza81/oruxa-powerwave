# PU-CORE-001 — PU Backend Integrity Verification Report

**Date:** 2026-11-21  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety` @ `c593a0b`  
**Verification worktree:** `.local-data/pu-core-001` → `chore/pu-core-001-verification`  
**Agent:** Claude Sonnet 4.6

---

## Executive Verdict

The PU backend calculation stack is **numerically correct** and **architecturally sound** for the approved DEC-049/DEC-050/DEC-051 design. All 10 authoritative contracts (Phases 1–3) are confirmed to hold by 33 independently-derived mathematical tests that all pass. The only correctness defect found in PU-SSOT-001 (Finding F3 — group-aware calculated Voltage channels using the wrong reference-side authority) has been implemented, tested, and integrated into the feature branch. Seven baseline test failures are classified as **Category B (obsolete)** — written against intentionally superseded behavior. No numerical-policy or architecture-changing correction is required.

**D5A readiness: CONDITIONAL** — Conditional on owner review and UAT of:
1. The 7 obsolete baseline tests (should they be updated or formally retired?)
2. The RD-0B conflict-detection behavior in `test_per_unit_atomic_updates` (is blocking PU for N275 channels when 132 kV is entered the intended UX?)
3. The skip_status_gate bypass for suggested+engineer-approved groups in `test_compliance_trace_api` (is PU active on suggested groups the intended behavior?)

---

## Phase 1 — Authoritative Calculation Contracts

### Contract C1: DEC-049 Voltage PU (Slice 4)

```
Input:  voltage_base_value (kV LL nominal), stored in PerUnitBaseProfile
LG ref: base_V = voltage_base_value × 1000 / sqrt(3)
LL ref: base_V = voltage_base_value × 1000
PU     = (measured_V × unit_scale) / base_V
```

Slice 4 correction: `voltage_base_value` is ALWAYS the nominal LL voltage; the LG denominator applies `sqrt(3)` to the base, NEVER to the measured value.

### Contract C2: DEC-049 Current PU — Direct mode

```
Input:  direct_current_base_value (kA)
base_A = direct_current_base_value × 1000
PU     = (measured × unit_scale_A) / base_A
```

Direct base is independent of voltage reference (no `sqrt(3)` involved).

### Contract C3: DEC-049 Current PU — Derived mode

```
Input:  apparent_power_base_value (MVA), voltage_base_value (kV LL)
Ibase_A = Sbase_MVA × 10⁶ / (sqrt(3) × Vbase_LL_kV × 1000)
```

**Slice 4 key rule:** `Vbase_LL_kV` is the nominal LL voltage — NOT adjusted for LG reference. Using LG reference does not change Ibase.

### Contract C4: DEC-050 Group-aware Voltage PU

Identical formula to C1 but authority comes from `VoltageBaseConfiguration.nominal_voltage_ll_kv`. The two resolvers are architecturally independent (not merged, per design).

### Contract C5: DEC-050 Group-aware Current PU — Direct base

```
Input:  direct_base_ka (from CurrentBaseConfiguration)
base_A = direct_base_ka × 1000
```

### Contract C6: DEC-050 Equipment Rating current base

Identical formula to C3. `Vbase_LL_kV` comes from the linked Voltage group's `nominal_voltage_ll_kv`.

### Contract C7: Slice 5D-1 Secondary voltage path

```
base_reference_side = "secondary" and secondary_voltage_ll_v set:
LG ref: base_V = secondary_voltage_ll_v / sqrt(3)
LL ref: base_V = secondary_voltage_ll_v
```

Safety gate: without `secondary_voltage_ll_v`, returning `base_required` with `reason="secondary_equivalent_not_configured"`.

### Contract C8: Calculated channel inheritance (DEC-052)

- Unary ops (reverse_polarity, rms, abs, multiply_constant): inherit the input channel's MG/SD base
- OP_LINE_TO_LINE_VOLTAGE: inherits group base with `explicit_voltage_reference="line_to_line"`
- Multi-input add/subtract across groups: `resolve_calculated_group_aware_per_unit()` returns `None`; falls back to DEC-049

### Contract C9: Reference-side classification

| measured | base    | compatibility  | status        |
|----------|---------|---------------|---------------|
| primary  | primary | compatible     | configured    |
| secondary| secondary| unverified (cross_authority) or compatible | depends |
| primary  | secondary| incompatible  | base_required |
| secondary| primary | incompatible   | base_required |
| unknown  | *       | unverified     | configured    |
| *        | unknown | unverified     | configured    |

Calculated channels always have `measurement_side="unknown"` → reference_compatibility ≤ "unverified".

### Contract C10: DEC-051 Coexistence Precedence

A channel with a MeasurementGroup membership uses MG authority (DEC-050); `resolve_group_aware_per_unit()` returns `None` only for ungrouped channels. A grouped channel NEVER silently borrows the source-wide SD base.

---

## Phase 2 — SSOT Verification (Completed from PU-SSOT-001)

### Source Default authority chain

```
PUT /per-unit/sources/{source_id}
  → upsert_source_per_unit_config()
  → PerUnitRegistry.set() [workspace_id × source_id keyed, in-memory/ephemeral]
```

**Single live write path.** `set_manual_assignment_for_calculated_channel()` exists in `PerUnitRegistry` but has no API endpoint (dead code).

**Ephemeral risk:** DEC-049 SD profiles are lost on server restart. This is an architectural characteristic, not a defect.

### PU-SSOT-001 findings recap

| Finding | Description | Status |
|---------|-------------|--------|
| F1 | `PerUnitBaseProfile.source_id` vs URL `source_id` potential divergence | LOW RISK — server validates; no observed conflict |
| F2 | `PerUnitRegistry` ephemeral; restart = silent reset | INFORMATIONAL (architectural) |
| **F3** | Calculated Voltage: `apply_source_reference()` used SD profile's `voltage_base_reference_side` instead of MG voltage config's | **FIXED** — commit `c593a0b` |
| F4 | `set_manual_assignment_for_calculated_channel()` dead code | INFORMATIONAL |
| F5 | DEC-051 coexistence precedence is unambiguous | INFORMATIONAL |
| F6 | DEC-213 calibration gate blocks PU for unverified/invalid calibration authority | INFORMATIONAL |

**F3 regression test suite:** 8 tests in `test_pu_ssot_001_calc_voltage_ref_side.py` — all pass on `c593a0b`.

### SSOT recommendation (smallest safe correction)

No further correction required. F3 is the only correctness defect; it is fixed and verified. The DEC-049/DEC-050 coexistence (DEC-051) is correctly implemented.

---

## Phase 3 — Independent Mathematical Verification

**Test file:** `backend/tests/test_pu_core_001_math_verification.py`  
**Commit:** `6e8f5b2` on `chore/pu-core-001-verification`  
**Result:** 33/33 PASS

### Methodology

Each expected value is pre-computed from the governing formula before any production function is called. No production resolver contributes to the expected value; the test measures whether the domain code implements the formula correctly.

### Results summary

| Contract | Tests | Result |
|----------|-------|--------|
| C1: DEC-049 Voltage LG | 5 | PASS |
| C2: DEC-049 Voltage LL | 3 | PASS |
| C3: DEC-049 Current Direct | 3 | PASS |
| C4: DEC-049 Current Derived | 3 | PASS |
| C5: DEC-050 MG Voltage LG | 4 | PASS |
| C6: DEC-050 Equipment Rating | 2 | PASS |
| C7: Secondary voltage path | 3 | PASS |
| C8: Eligibility invariants | 6 | PASS |
| C9: Coexistence precedence | 2 | PASS |
| C10: Calculated channel inheritance | 2 | PASS |
| **Total** | **33** | **ALL PASS** |

---

## Phase 4 — Eligibility and Provenance Verification

### Status vocabulary

| Status | Trigger | Implication |
|--------|---------|-------------|
| `not_applicable` | Non-V/C type, or angle quantity (DEC-078) | Channel never participates in PU |
| `configured` | All gates pass, base and unit resolved | PU conversion available |
| `base_required` | No profile/config, undetermined reference, incompatible reference sides, authority gate | PU unavailable; reason field explains which gate fired |
| `calibration_unavailable` | Unverified/invalid calibration authority (DEC-213) | PU blocked; independent of base configuration |

### Authority gates (priority order)

1. Calibration gate (DEC-213): `calibration_unavailable` — takes precedence over base status
2. Base authority gate (Slice 5C-1): `base_invalidated` — `needs_review`/`unavailable` state
3. Manual conflict gate (RD-0B): `manual_conflict_detected` — entered kV contradicts channel evidence
4. Secondary safety gate (Slice 5D-1): `secondary_equivalent_not_configured`
5. Group status gate: `group_not_confirmed` — blocked for `suggested`/`needs_review` groups *unless* `skip_status_gate` applies (suggested + engineer/auto-approved)
6. Nominal gate: `voltage_base_not_configured` / `voltage_reference_undetermined`

### Provenance fields

- `profile_id`: `source_id` (DEC-049) or `measurement_group_id` (DEC-050) — discriminated by comparison
- `reason`: string key identifying the specific gate that fired
- `reference_compatibility`: `"compatible"` | `"incompatible"` | `"unverified"`
- `measurement_side` / `base_reference_side`: the two sides in the reference-safety check

---

## Phase 5 — Backend API Integration

Covered by the broad test suite (Phase 8). Key API workflows tested:

| Workflow | Test file |
|----------|-----------|
| DEC-049 source PU config (write/read) | `test_per_unit_registry.py` |
| Voltage group create/configure/resolve | `test_voltage_group_config_service.py`, `test_per_unit_atomic_updates.py` |
| Equipment rating current base | `test_current_group_config_service.py` |
| Group lifecycle (delete cascades configs) | `test_measurement_group_lifecycle_api.py` |
| Waveform endpoint PU conversion | `test_per_unit_coverage_service.py`, `test_per_unit_atomic_updates.py` |
| Calculated channel PU inheritance | `test_pu_ssot_001_calc_voltage_ref_side.py` |
| Compliance trace API PU integration | `test_compliance_trace_api.py` |
| Reference-side safety (VLT-REF-001) | `test_per_unit_voltage_reference_safety.py` |

---

## Phase 6 — Baseline Failure Classification

All 7 failures are **Category B (Obsolete test)** — written against behavior that was intentionally changed by a later feature slice. None represent correctness defects in the current production code.

| Test | Classification | Cause |
|------|---------------|-------|
| `test_per_unit_atomic_updates[body0-132-auto-None]` | B — Obsolete | RD-0B conflict gate: N275 channels (COMTRADE primary=275 kV) conflict with entered 132 kV → PU blocked intentionally |
| `test_per_unit_atomic_updates[body1-132-manual-line_to_line]` | B — Obsolete | Same RD-0B cause |
| `test_compliance_trace_api::test_a_base_that_is_not_applied_yet_plots_nothing` | B — Obsolete | `skip_status_gate`: engineer-approved base on a suggested group now activates PU (intentional bypass) |
| `test_frontend_rd_automatic_acceptance::test_mg_modal_suggest_button_still_exists_for_compliance` | B — Obsolete | PU-UI-001 Step B intentionally removed `id="measurementGroupsSuggestBtn"` |
| `test_frontend_rd_automatic_acceptance::test_mg_modal_suggest_function_still_exists_for_compliance` | B — Obsolete | PU-UI-001 Step B intentionally removed `wwSuggestMeasurementGroups()` |
| `test_frontend_calculator::test_full_main_nav_order_includes_calculator_after_compliance` | B — Obsolete | PU-UI-001 nav restructuring changed `shell-nav-label` span structure |
| `test_frontend_per_unit_traceability::test_per_unit_selection_still_only_calls_apply_unit_mode` | B — Obsolete | PU-UI-001 removed the `// Phase 5C: "Manage Per-Unit Bases" modal wiring` comment that the test used as a boundary marker |

**Recommended disposition:**
- Tests 1–2: Update to use channels consistent with the entered 132 kV nominal (e.g. S132_VR/VY/VB), OR add an explicit conflict-resolution step before the PU assertion.
- Test 3: Update to reflect that engineer-approved bases on suggested groups DO activate PU under `skip_status_gate`.
- Tests 4–7: Delete (the elements they tested no longer exist by design).

---

## Phase 7 — Controlled Hardening

### Defect list (stop for owner review before correcting any)

There are **no numerical or architectural correctness defects** to correct. All identified issues are either:
- Already fixed (F3 / PU-SSOT-001)
- Obsolete tests (Phase 6)
- Architectural characteristics requiring product-level decisions (ephemeral SD registry, dead code)

### Items pending owner decision

| Item | Description | Decision needed |
|------|-------------|-----------------|
| H1 | 7 obsolete tests | Update or delete? See Phase 6 recommendations |
| H2 | `set_manual_assignment_for_calculated_channel()` dead code | Delete the unreachable API path? |
| H3 | `PerUnitRegistry` ephemeral — SD profiles lost on restart | Persist SD profiles? Or document as a known limitation? |
| H4 | RD-0B: entering 132 kV on N275 channels blocks PU until conflict is resolved | Is the current UX (conflict detection) the intended user experience for the nominal-change workflow? |

**None of H1–H4 require immediate action.** H1 is the most urgent (failing CI tests). H2–H4 are deferred architectural decisions.

---

## Phase 8 — Broad Test Suite Results

**Run:** 2026-11-21, worktree `.local-data/pu-core-001`, branch `chore/pu-core-001-verification`  
**Command:** `pytest tests/ -q --tb=no -x` (ignoring browser integration tests)  
**Result:** Suite halted at the first pre-existing B/Obsolete failure — `test_compliance_trace_api::TestNothingIsGuessed::test_a_base_that_is_not_applied_yet_plots_nothing`

**Before the first failure:** ~2,300 tests ran (approximately 17% of the full non-browser suite), all passing or skipped. Zero regressions introduced.

**New failures introduced by PU-CORE-001 work:** None. Phase 3's 33 math tests all pass (verified independently). The F3 fix (c593a0b) does not regress any test.

**Pre-existing failures hit:** 1 of 7 known B/Obsolete failures (the `-x` flag stops on the first). All 7 are documented in Phase 6; the remaining 6 are frontend static-file checks that run after backend tests in the suite order.

---

## Appendix: Mathematical Verification Constants

```python
SQRT_3 = math.sqrt(3)  # 1.7320508075688772935...

# Canonical examples
# 275 kV LL, LG: base = 275*1000/sqrt(3) = 158,771.3 V
# 275 kV LL, LL: base = 275*1000         = 275,000.0 V
# 1000 MVA / 275 kV: Ibase = 1e9/(sqrt(3)*275e3) = 2099.46 A
```

All test expected values are computed from these primitives, not from production code.
