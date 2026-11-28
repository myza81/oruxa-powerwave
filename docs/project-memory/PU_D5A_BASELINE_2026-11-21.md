# PU-CORE-001 — D5A Integration Baseline

**Date:** 2026-11-21  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety` @ `c593a0b`  
**Verification worktree:** `.local-data/pu-core-001` → `chore/pu-core-001-verification`  
**Status:** Pending final full-suite regression — see PU_CORE_001_REPORT_2026-11-21.md for the release-gate verdict.

---

## 1. Exact Commit Baseline

| Item | Value |
|------|-------|
| Feature branch | `feature/vlt-ref-001-voltage-reference-safety` |
| HEAD commit | `c593a0b` — fix(pu-ssot-001): pass voltage_group_config to apply_source_reference for group-aware calculated Voltage channels |
| Verification branch | `chore/pu-core-001-verification` |
| Math test commit | `6e8f5b2` — 33 independent math tests |
| Report commit | `46591ea` — PU-CORE-001 report (Phase 1–8) |

---

## 2. Approved PU Formulas and Numerical Invariants

All formulas use `SQRT_3 = 1.7320508075688772` (hardcoded constant in `app/domain/per_unit_numerics.py`).

### Voltage PU base (DEC-049 and DEC-050 share the same formula)

```
LG reference:  base_V = nominal_voltage_ll_kv × 1000 / SQRT_3
LL reference:  base_V = nominal_voltage_ll_kv × 1000
```

**Invariant:** `nominal_voltage_ll_kv` is ALWAYS the nominal line-to-line voltage, regardless of channel reference. The LG denominator applies `SQRT_3` to the base, never to the measured value.

### Current PU base — Direct mode

```
base_A = direct_current_base_value_kA × 1000
```

**Invariant:** Direct base is independent of voltage reference. No `SQRT_3` factor.

### Current PU base — Derived (Equipment Rating) mode

```
Ibase_A = apparent_power_base_MVA × 10⁶ / (SQRT_3 × nominal_voltage_ll_kv × 1000)
```

**Invariant:** `nominal_voltage_ll_kv` is the nominal LL voltage — NOT adjusted for LG reference. Using LG reference does not change Ibase.

### Secondary voltage path (Slice 5D-1)

```
LG reference:  base_V = secondary_voltage_ll_v / SQRT_3
LL reference:  base_V = secondary_voltage_ll_v
```

Gate: requires `secondary_voltage_ll_v` to be set; without it, `base_required` with `reason="secondary_equivalent_not_configured"`.

### PU conversion

```
PU = (measured_value × unit_scale) / base_value
```

Implemented in `app/domain/per_unit_numerics.py::convert_scalar()`.

---

## 3. Measurement Group Authority and Eligibility Rules

### Authority hierarchy (DEC-051)

1. **Measurement Group (DEC-050):** Takes precedence for any channel assigned to a MG. Grouped channels NEVER fall back to Source Default.
2. **Source Default (DEC-049):** Fallback for ungrouped channels only. Write endpoint `PUT /per-unit/sources/{source_id}` has no frontend client after PU-UI-001 Step B.

### Group status gate

| Group status | base_authority | PU active? |
|--------------|---------------|-----------|
| `confirmed` | any eligible | YES |
| `suggested` | `manual` or `auto_resolved` | YES (skip_status_gate) |
| `suggested` | `needs_review` / `unavailable` | NO |
| `needs_review` | any | NO |

### Base authority gate (Slice 5C-1)

Eligible authorities for PU: `legacy_manual`, `manual`, `auto_resolved`.  
Blocking: `needs_review`, `unavailable`.

### RD-0B conflict detection

When the engineer enters a nominal kV, `reconfigure_auto_base_after_membership_change()` compares the entered value against COMTRADE `primary` field evidence for all group members. If they conflict, `manual_conflict_detected=True` is set, blocking PU until resolved. This safeguard must not be weakened or auto-overridden.

### Eligibility status vocabulary

| Status | Meaning |
|--------|---------|
| `not_applicable` | Non-V/C type or angle quantity — never participates in PU |
| `configured` | All gates pass; PU active |
| `base_required` | A gate fired; PU unavailable; `reason` field names the specific gate |
| `calibration_unavailable` | DEC-213 calibration gate blocked PU |

### Authority gate priority order

1. Calibration gate (DEC-213) — `calibration_unavailable`
2. Base authority gate (Slice 5C-1) — `base_invalidated`
3. Manual conflict gate (RD-0B) — `manual_conflict_detected`
4. Secondary safety gate (Slice 5D-1) — `secondary_equivalent_not_configured`
5. Group status gate — `group_not_confirmed` (unless skip_status_gate)
6. Nominal gate — `voltage_base_not_configured` / `voltage_reference_undetermined`

---

## 4. Reference-Side Handling and Provenance

### Reference classification

| Measured side | Base side | Compatibility |
|---------------|-----------|---------------|
| `primary` | `primary` | `compatible` |
| `secondary` | `secondary` | `unverified` or `compatible` |
| `primary` | `secondary` | `incompatible` → `base_required` |
| `secondary` | `primary` | `incompatible` → `base_required` |
| `unknown` | any | `unverified` → `configured` |
| any | `unknown` | `unverified` → `configured` |

### Provenance fields

| Field | DEC-049 value | DEC-050 value |
|-------|--------------|--------------|
| `profile_id` | `source_id` | `measurement_group_id` |
| `reason` | gate identifier string | gate identifier string |
| `reference_compatibility` | `compatible`/`incompatible`/`unverified` | same |
| `measurement_side` | from COMTRADE CFG `P`/`S` field | same |
| `base_reference_side` | `profile.voltage_base_reference_side` | `VoltageBaseConfiguration.base_reference_side` |

**F3 fix (c593a0b):** For group-aware calculated Voltage channels, `apply_source_reference()` now reads `base_reference_side` from `voltage_group_config` (DEC-050) rather than from the SD profile (DEC-049). This was the only correctness defect found in PU-SSOT-001.

---

## 5. Calculated-Channel Base Behavior (DEC-052)

| Operation | PU base authority |
|-----------|------------------|
| Unary ops (reverse_polarity, rms, abs, multiply_constant) | Inherits input channel's MG/SD base |
| `OP_LINE_TO_LINE_VOLTAGE` | Inherits input group's base; forces `explicit_voltage_reference="line_to_line"` |
| Cross-group add/subtract where inputs share MG and source | Inherits if unanimous (same profile_id) |
| Cross-group add/subtract spanning different MGs | `resolve_calculated_group_aware_per_unit()` returns `None`; falls back to SD |
| Calculated Current with `mode="manual"` | Uses manually configured base from `PUT /{id}/per-unit-config` (live frontend feature) |

Calculated channels always have `measurement_side="unknown"` → `reference_compatibility ≤ "unverified"`.

Do not reinterpret DEC-052 cross-group rules without owner approval.

---

## 6. Known Physical-Calibration Limitations

- DEC-213: Channels with `calibration_unavailable` status (unverified or invalid calibration authority) have PU blocked regardless of base configuration.
- For COMTRADE sources without an explicit `calibration_authority` field: vacuous truth → eligible (calibration gate passes).
- CT/VT mathematics and physical waveform scaling are **outside the scope of PU-CORE-001** and must not be altered during D5A PU integration.
- `app/domain/per_unit.py` does not perform CT/VT conversion — it operates on already-scaled engineering values.

---

## 7. Interfaces That D5A May Consume

| Endpoint / function | Description |
|---------------------|-------------|
| `GET /api/v1/workspaces/{ws}/sources/{src}/waveform?unit_mode=per_unit` | Returns PU-converted waveform samples |
| `GET /api/v1/workspaces/{ws}/sources/{src}/per-unit-resolution?channel_name={name}` | Returns `PerUnitResolutionOut` with status, base_amount, base_unit, provenance |
| `GET /api/v1/workspaces/{ws}/measurement-groups/{id}` | Returns group status, channel membership |
| `GET /api/v1/workspaces/{ws}/sources/{src}/measurement-groups/{id}/voltage-config` | Returns `VoltageBaseConfiguration` |
| `GET /api/v1/workspaces/{ws}/sources/{src}/measurement-groups/{id}/current-config` | Returns `CurrentBaseConfiguration` |
| `GET /api/v1/workspaces/{ws}/calculated-channels/{id}/per-unit-config` | Returns `CalculatedCurrentConfiguration` |
| `app.domain.per_unit.resolve_per_unit()` | Core DEC-049 resolver (internal) |
| `app.domain.voltage_group_config.resolve_voltage_base_for_group()` | Core DEC-050 resolver (internal) |
| `app.services.waveform_service._resolve_effective_per_unit()` | Dispatches DEC-049/DEC-050 (internal) |

---

## 8. PU Functionality That D5A Must Not Alter

The following behaviors are locked by approved decisions and must be preserved:

1. **DEC-051 coexistence precedence:** Grouped channels always use DEC-050; ungrouped channels fall back to DEC-049. Never merge these paths.
2. **Slice 4 invariant:** `nominal_voltage_ll_kv` stores the nominal LL voltage unconditionally. The LG denominator is applied to the base value, not the stored kV.
3. **Derived current base formula:** `Ibase = Sbase_MVA × 10⁶ / (SQRT_3 × Vbase_LL_kV × 1000)`. `Vbase_LL_kV` is NOT adjusted for reference mode.
4. **RD-0B conflict gate:** A manually entered kV that contradicts COMTRADE evidence must remain blocked until resolved. Do not add auto-resolution or override.
5. **Authority gate (Slice 5C-1):** `needs_review` and `unavailable` authorities block PU. Do not widen eligibility without approval.
6. **F3 fix:** For group-aware calculated Voltage, `base_reference_side` comes from `VoltageBaseConfiguration`, not the SD profile.
7. **Calibration gate (DEC-213):** Channels with unverified/invalid calibration authority have PU blocked. Do not bypass.
8. **Source Default frontend:** No UI for SD configuration is to be added or restored (`PUT /per-unit/sources/{source_id}` has no frontend client by design after PU-UI-001 Step B).
