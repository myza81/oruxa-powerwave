# RD-1 Slice D1 — CT/VT Contract Proposal

**Date:** 2026-11-18  
**Branch:** feature/vlt-ref-001-voltage-reference-safety  
**Baseline commit:** 23f1117 (Slice C-1 tabs)  
**Status:** Proposal — stop for owner review before implementation.

---

## 1. PMJY1 CURRENT Association Gap — Root Cause

**Root cause: backend domain gap, not a frontend display defect.**

The auto-base service (`auto_base_service.py:126`) contains the explicit comment:

> `continue  # C3: current groups have no auto Ibase`

No automatic process ever sets `linked_voltage_group_id` on a Current group. The link is set only when an engineer explicitly calls `PUT /measurement-groups/{id}/current-config` with `method="equipment_rating"` and `linked_voltage_group_id=<id>`.

For KTBR PMJY1 CURRENT:
- `method="none"` (no configuration applied)
- `linked_voltage_group_id=null`
- The frontend at `index.html:36934` correctly renders "—" when `linked_voltage_group_id` is null

**The frontend is correct.** The group genuinely has no linked voltage group because no engineer has configured it.

**What is needed to fix it:**  
An engineer must configure PMJY1 CURRENT via `PUT /measurement-groups/{id}/current-config` with `method="equipment_rating"` and `linked_voltage_group_id=<id of PMJY1 VOLTAGE>`. This requires the Slice D editing controls — the link cannot be established from the read-only Slice C panel.

**Name-matching confirmed absent:**  
Grep of both backend services and frontend confirms no name-pattern matching logic for voltage-current associations. All associations are set via opaque `id` only.

---

## 2. CT/VT Field Conventions in Existing Analysis Modules

Three analysis modules carry CT/VT fields today:

| Module | Schema file | CT fields | VT fields | Unit |
|--------|-------------|-----------|-----------|------|
| Distance Protection | `schemas/distance_protection_analysis.py:83–86` | `ct_primary`, `ct_secondary` | `vt_primary`, `vt_secondary` | **float, Amperes / Volts** |
| Impedance Analysis | `schemas/impedance_analysis.py:31–34` | `ct_primary`, `ct_secondary` | `vt_primary`, `vt_secondary` | float, Amperes / Volts |
| Overcurrent | `schemas/overcurrent_analysis.py:29–30` | `ct_primary`, `ct_secondary` | — (no VT) | float, Amperes |

**Established convention:**
- `ct_primary`: CT primary winding rated current in **Amperes** (e.g., 200.0 for a 200/5 CT)
- `ct_secondary`: CT secondary winding rated current in **Amperes** (e.g., 5.0 for a 200/5 CT)
- `vt_primary`: VT primary winding rated voltage in **Volts** (e.g., 132000.0 for 132 kV / 110 V VT)
- `vt_secondary`: VT secondary winding rated voltage in **Volts** (e.g., 110.0)
- Ratio is derived as needed: `ratio = secondary / primary` for conversion
- Each module defines its own `loop_ratio_valid()` / `manual_ratio_valid()` independently (per-module convention, `auto_base_evidence.py` C2 note)

**Channel-level storage:**  
`AnalogChannel.primary_ratio` and `secondary_ratio` carry the same winding values extracted from COMTRADE CFG headers (`ChannelAutoMetadata` in `auto_base_evidence.py:163–164`). These are **instrument-transformer winding quantities, not authoritative nominal-system values** (C2 comment at line 156). They are used only as evidence candidates for voltage-base detection, never as authoritative CT/VT configuration.

**No existing ratio-only storage.** The convention is always separate primary/secondary values.

---

## 3. Ingestion Metadata

### COMTRADE
COMTRADE 1999 CFG format carries `primary`/`secondary` fields per analog channel. These are read and stored in `AnalogChannel.primary_ratio` and `secondary_ratio` (in the channel's engineering unit — Volts for voltage channels, Amperes for current channels). The COMTRADE `P`/`S` flag sets `measurement_side`.

**These values are available in the channel descriptor at ingestion time.**

### BEN
BEN format carries `primary_rating` and `secondary_rating_in_channel_unit` per channel (see `ChannelAutoMetadata` docstring). `measurement_side = "unknown"` for all BEN channels (no PS flag equivalent).

**BEN CT/VT winding values exist in channel descriptors but measurement_side is always unknown.**

### Stored vs discarded
Channel descriptors (`AnalogChannel`) persist in `DisturbanceRecord.metadata.analog_channels` for the workspace lifetime. The winding values in `primary_ratio`/`secondary_ratio` are therefore available for auto-population at group creation time.

### Implication for D1
When a Measurement Group is created or its channel membership changes, the backend could auto-populate VT/CT fields from channel-level `primary_ratio`/`secondary_ratio` values with `vt_authority="recording_metadata"` / `ct_authority="recording_metadata"`. This would populate the read-only "Not available from recording metadata" display with actual values where COMTRADE provides them.

**This is optional for D1 — the minimum viable path is manual entry only.**

---

## 4. Proposed CT/VT Schema Fields

Based on the established primary/secondary Amperes/Volts convention:

### For `VoltageBaseConfiguration` (Voltage Group, owns VT):

```python
# VT instrument-transformer winding quantities (optional, all None = not configured).
# vt_primary_v: Primary winding rated voltage, Volts (same unit as channel's secondary_ratio).
# vt_secondary_v: Secondary winding rated voltage, Volts (typically 110 V or 100 V).
# vt_authority: Configuration provenance.
# vt_provenance_note: Optional free text, e.g., "from COMTRADE CFG header".
vt_primary_v: float | None = None
vt_secondary_v: float | None = None
vt_authority: str = "not_configured"  # "not_configured" | "recording_metadata" | "manual"
vt_provenance_note: str | None = None
```

**Unit: Volts for both primary and secondary.** Consistent with existing analysis modules (`vt_primary`, `vt_secondary` in Amperes/Volts). Note: `auto_base_evidence.py` uses `primary_ratio` in the channel's native unit (kV for voltage channels), so a kV→V conversion is needed during auto-population.

**Ratio derivation:** `vt_ratio = vt_secondary_v / vt_primary_v` — derived on demand, never stored separately, to avoid inconsistency.

### For `CurrentBaseConfiguration` (Current Group, owns CT):

```python
# CT instrument-transformer winding quantities (optional, all None = not configured).
# ct_primary_a: Primary winding rated current, Amperes (e.g., 200.0 for a 200/5 CT).
# ct_secondary_a: Secondary winding rated current, Amperes (typically 1.0 or 5.0).
# ct_authority: Configuration provenance.
# ct_provenance_note: Optional free text.
ct_primary_a: float | None = None
ct_secondary_a: float | None = None
ct_authority: str = "not_configured"  # "not_configured" | "recording_metadata" | "manual"
ct_provenance_note: str | None = None
```

**Field naming alignment:** Existing analysis modules use `ct_primary`/`ct_secondary` without unit suffix. For the domain model, adding `_a` suffix is unambiguous and aligns with `nominal_voltage_ll_kv`'s own unit-in-name convention. The API wire shape can omit the suffix for brevity.

**Validation:**
- `vt_primary_v > 0`, `vt_secondary_v > 0`, both finite
- `ct_primary_a > 0`, `ct_secondary_a > 0`, both finite
- Partial specification (only primary set) is valid — secondary may be unknown
- Setting either to `None` with `ct_authority="manual"` is a validation error; `manual` requires both values

---

## 5. API Contract Additions

### 5.1 GET response additions

Add to `VoltageGroupConfigOut`:

```python
vt_primary_v: float | None = None
vt_secondary_v: float | None = None
vt_authority: str = "not_configured"
vt_provenance_note: str | None = None
```

Add to `CurrentGroupConfigOut`:

```python
ct_primary_a: float | None = None
ct_secondary_a: float | None = None
ct_authority: str = "not_configured"
ct_provenance_note: str | None = None
```

**Backward compatibility:** All new fields default to `None` / `"not_configured"`. Existing clients receive the new fields but can ignore them.

### 5.2 PUT additions — Voltage Group (`PUT /voltage-config`)

Extend `VoltageGroupConfigUpdateRequest` with optional VT fields:

```python
vt_primary_v: float | None = None          # None = do not change
vt_secondary_v: float | None = None        # None = do not change
clear_vt: bool = False                     # True = clear VT config and return to not_configured
vt_provenance_note: str | None = None
```

Validation:
- `clear_vt=True` with `vt_primary_v` or `vt_secondary_v` set → reject (ambiguous)
- `vt_primary_v` or `vt_secondary_v` set without the other → accepted (partial specification)
- `vt_primary_v > 0` and finite if set

### 5.3 PUT additions — Current Group (`PUT /current-config`)

Extend `CurrentGroupConfigUpdateRequest` with optional CT fields:

```python
ct_primary_a: float | None = None          # None = do not change
ct_secondary_a: float | None = None        # None = do not change
clear_ct: bool = False                     # True = clear CT config
ct_provenance_note: str | None = None
```

Same validation pattern as VT.

### 5.4 Revert nominal kV to auto (approved Decision 1)

Extend `VoltageGroupConfigUpdateRequest` with:

```python
clear_nominal_voltage: bool = False
```

Service contract:
- `clear_nominal_voltage=True` with `nominal_voltage_ll_kv` also set → reject (ambiguous)
- `clear_nominal_voltage=True` → set `nominal_voltage_ll_kv=None` in the registry, set `base_authority="unavailable"`, then re-run `reconfigure_auto_base_after_membership_change()` → may resolve to `auto_resolved` or remain `needs_review`
- Result legitimately lands in `needs_review` when source evidence is insufficient (BEN recordings)

**Service change needed:** `update_voltage_configuration()` currently treats `nominal_voltage_ll_kv=None` as "do not change." A new code path in the service layer must distinguish "not supplied" from "explicitly cleared." Use a sentinel default (e.g., `_KV_NOT_GIVEN = object()`) mirroring the existing `_SECONDARY_NOT_GIVEN` pattern at line 134.

---

## 6. Measurement-Side Compatibility Design

### Current state
`AnalogChannel.measurement_side` is set from the COMTRADE PS flag (`"primary"` / `"secondary"`) or defaults to `"unknown"` (BEN and COMTRADE 1991). It is a read-only channel descriptor property — never modified after ingestion.

CT/VT ratios in analysis modules are used to convert between primary and secondary representations of phasor magnitudes: `secondary = primary × (secondary_a / primary_a)`.

### Invariant for group-level CT/VT
When CT/VT winding values are set on a Measurement Group:
1. The group's CT/VT configuration describes the instrument transformer nominal ratings
2. The channel `measurement_side` describes which side the recorded samples represent
3. The analysis conversion applies: `primary_quantity = secondary_recorded × (ct_primary_a / ct_secondary_a)`

**Double-scaling risk:** If `AnalogChannel.scale` and `offset` from COMTRADE CFG already converted the sample to primary-side engineering units (a valid COMTRADE encoding), then applying a CT ratio again would double-scale.

**Risk mitigation:** The existing `PhysicalCalibrationAuthority` framework (`physical_calibration.py`) is designed to track this. For Slice D, the CT/VT ratio must NOT be automatically applied to recorded samples. It is provided as metadata for analysis modules that require it. The `measurement_side` field on the channel tells the analysis module which side the sample is already on.

**Compatibility check recommendation:** Add a warning (not a hard rejection) when:
- CT ratio is configured on a Current group
- AND the group's channels have `measurement_side="primary"` (samples are already primary side)
- This suggests the CT ratio is redundant or would double-scale if applied

This warning belongs in the view service, surfaced as a provenance note, not as a blocking error.

---

## 7. Dependency Invalidation Contract

### CT/VT change triggers
After a successful PUT that changes VT or CT fields:

| Downstream consumer | Invalidation needed |
|---|---|
| Measurement Group GET response | Re-fetched automatically (PUT returns updated group) |
| Recording Details Group Details panel | Re-render with new CT/VT values (Slice D Apply path) |
| Impedance Analysis | Clear cached results for affected source; invalidate `wwImpedanceState.locusSignature` |
| Distance Protection | Clear cached results; invalidate `wwDistanceState` signature |
| Overcurrent Analysis | Clear cached results; invalidate `wwOvercurrentState.curveCache` |
| PU display | PU eligibility is NOT affected by CT/VT — no PU generation increment needed |

**CT/VT changes do not affect PU eligibility.** PU bases (kV, kA) are independent of instrument transformer metadata.

**Minimum frontend invalidation contract after CT/VT PUT:**
1. Re-fetch the measurement group list for the affected source (to refresh the Group Details panel)
2. Invalidate analysis results for the affected source (clear analyzer state signatures)
3. Do NOT increment `wwErState.perUnit.generation` (PU is unaffected)

### Comparison: voltage base change vs CT/VT change
| Event | PU affected | Analysis affected |
|---|---|---|
| nominal_voltage_ll_kv changed | Yes — increment PU generation | Yes |
| CT/VT winding values changed | No | Yes |

---

## 8. Regression Test Requirements

### Backend (D1 — not yet implemented)

For Voltage Group VT:
1. Setting `vt_primary_v`/`vt_secondary_v` → stored and returned in GET response
2. `clear_vt=True` → clears both values, sets `vt_authority="not_configured"`
3. `vt_authority="manual"` after manual set; `"recording_metadata"` after auto-population
4. Validation: negative `vt_primary_v` rejected
5. Validation: `clear_vt=True` with `vt_primary_v` set → 400 error
6. Partial specification (only `vt_primary_v` set) accepted without error

For Current Group CT (symmetric):
7–12. Mirror VT tests for `ct_primary_a`/`ct_secondary_a`/`clear_ct`

For revert-to-auto (`clear_nominal_voltage`):
13. `clear_nominal_voltage=True` → `nominal_voltage_ll_kv=None`, authority re-evaluated
14. Result is `needs_review` for a BEN group with insufficient evidence
15. `clear_nominal_voltage=True` with `nominal_voltage_ll_kv` set → 400 error

For double-scaling compatibility check:
16. Group with channels all `measurement_side="primary"` + CT set → warning note in view

### Browser tests (D4 — after D1 backend)
17. CT editing controls visible in Current Group Details
18. VT editing controls visible in Voltage Group Details
19. Apply saves values; Cancel reverts to pre-edit state
20. Validation: negative ratio shows inline error; Apply is disabled
21. After Apply, Group Details panel reflects new CT/VT values
22. After Apply, impedance analysis result cache is cleared

---

## 9. Open Questions for Owner

Before D1 implementation begins, these decisions are needed:

**Q1 — Auto-population from channel descriptors:**  
Should D1 auto-populate VT/CT fields from `AnalogChannel.primary_ratio`/`secondary_ratio` on group creation/membership change, with `vt_authority="recording_metadata"`? This would populate the currently blank CT/VT display for COMTRADE recordings. Risk: incorrect if the CFG values are nominal winding voltages rather than actual recording-side values.

**Q2 — Partial VT/CT specification:**  
Is partial specification (only `vt_primary_v` set, `vt_secondary_v` unknown) acceptable? Or must both winding values always be set together? The analysis modules require both for conversion, but partial is useful for display-only purposes.

**Q3 — VT unit for primary — kV vs Volts:**  
Analysis modules use `vt_primary` in Volts (e.g., 132000.0). The `auto_base_evidence.py` pipeline uses kV (consistent with `nominal_voltage_ll_kv`). The Slice D editing UI should present values in kV for the primary (more natural for a protection engineer). The API can accept kV and convert, or accept Volts and format for display. Which convention should the API use?

**Q4 — Compatibility warning vs hard rejection for double-scaling risk:**  
Should the measurement-side compatibility check produce a warning note (soft) or block the CT/VT configuration (hard)? Hard rejection would prevent misconfiguration but may obstruct valid use cases where the engineer knows the channel unit convention.

**Q5 — Provenance note — free text or structured:**  
Is `vt_provenance_note` / `ct_provenance_note` a free-text string sufficient, or should provenance be a structured enum (`"comtrade_cfg"` / `"manual"` / `"ben_header"` / `"unknown"`) for future filtering?

---

## 10. What D1 Must NOT Do

- Do NOT apply CT/VT ratios to imported waveform samples or rescale `DisturbanceRecord.waveform_data`
- Do NOT infer CT/VT ratios from nominal voltage, equipment MVA, or channel magnitude
- Do NOT modify the existing `auto_base_service.py` voltage-evidence pipeline
- Do NOT introduce CT/VT ratio into PU base calculations — `nominal_voltage_ll_kv` and `resolved_ibase_ka` remain the sole PU bases
- Do NOT make CT/VT configuration a prerequisite for PU eligibility
- Do NOT retire analysis-module CT/VT inputs (that is D5B, after D5A compatibility verification)
- Do NOT introduce database persistence — all state remains session-scoped
- Do NOT modify the `PhysicalCalibrationAuthority` framework
- Do NOT infer a voltage-current group association from matching names

---

---

## 11. Owner Decisions Incorporated (2026-11-18)

All five open questions from Section 9 are now resolved by owner decision:

| Q | Decision |
|---|---|
| Q1 (Auto-population) | Auto-populate ONLY from reliable, explicitly interpretable metadata. D1 prioritizes schema and API; ingestion extraction is a separate verified enhancement. |
| Q2 (Partial pairs) | Both primary AND secondary required for an effective configuration. Partial pairs allowed in unsaved frontend drafts only; not persisted. Clear supported explicitly. |
| Q3 (Units) | `vt_primary_v`/`vt_secondary_v` Volts; `ct_primary_a`/`ct_secondary_a` Amperes. Positive + finite validation. |
| Q4 (Measurement-side) | Do NOT reject CT/VT metadata because channels are primary-side. Separate configuration validity from conversion eligibility. Never double-scale. |
| Q5 (Provenance) | Structured authority enum `"not_configured"` / `"recording_metadata"` / `"manual"`. Optional free-text note. Preserve original evidence on manual override. |

---

## 12. Ambiguity Resolution — Codebase Findings

### A. VT voltage-reference basis — RESOLVED

The domain type `InstrumentTransformers` (`backend/app/domain/relay_import/canonical_distance.py:205`) already uses **exactly** the field names `vt_primary_v`, `vt_secondary_v`, `ct_primary_a`, `ct_secondary_a` in the same units (Volts / Amperes). Relay conformance tests confirm: `vt_primary_v = "132000 V"` for a 132 kV system (L-L in Volts); `vt_secondary_v = "110 V"` (standard L-L secondary).

**Decision: `vt_primary_v` and `vt_secondary_v` are BOTH L-L in Volts. No separate `vt_reference_mode` field is needed.** The L-L convention is consistent with `nominal_voltage_ll_kv`'s own semantic. The analysis conversion formula `V_secondary = V_primary × (vt_secondary_v / vt_primary_v)` applies directly.

The naming convention is already established in the domain model and is not an invention for D1.

### B. CT/VT effective value vs imported evidence — RESOLVED

`VoltageBaseConfiguration` uses a single value + `base_authority` (no separate `evidence` / `resolved` split at the domain level). The same single-value + authority pattern is sufficient for CT/VT in D1:

- `vt_primary_v`/`vt_secondary_v` = effective (current) values
- `vt_authority` = provenance of those values
- `vt_provenance_note` = optional narrative (e.g., "from COMTRADE CFG header channel 3")

A separate `vt_imported_*` field is NOT needed for D1. If COMTRADE ingestion auto-populates values and the engineer subsequently overrides them, the original values can be recorded in `vt_provenance_note`. A richer evidence model can be introduced in a later slice if needed.

### C. Clear operation and existing PUT compatibility — RESOLVED

The existing service already uses the `_SECONDARY_NOT_GIVEN` sentinel pattern to distinguish "not supplied" from "explicitly cleared to None" (see `voltage_group_config_service.py:60`). Adding `clear_vt: bool = False` and `clear_ct: bool = False` flags follows this same pattern and is fully compatible with the existing PUT request bodies.

Important: `VoltageGroupConfigUpdateRequest`'s current docstring notes "there is no 'clear' operation" for `nominal_voltage_ll_kv`. D1 adds `clear_nominal_voltage: bool = False` to change this. The docstring must be updated when this is implemented.

Validation rule: `clear_vt=True` with `vt_primary_v` or `vt_secondary_v` set → 422 Validation Error (ambiguous: cannot simultaneously set and clear).

### D. Analysis dependency invalidation — RESOLVED (confirmed independent of PU)

`is_base_eligible_for_pu()` at `base_authority.py:71` checks only the base authority state — CT/VT configuration has absolutely no effect on PU eligibility. **Confirmed: CT/VT edits do NOT require incrementing `wwErState.perUnit.generation`.**

CT/VT changes must invalidate:
- Distance Protection analysis results for the affected source (the analysis currently reads CT/VT from its own request body; after D5A/D5B, it reads from the group)
- Impedance Analysis results for the affected source
- Overcurrent Analysis results for the affected source

The analysis modules currently receive CT/VT from their own per-request bodies (engineering contexts API). D1 exposes CT/VT on the measurement group wire schema. D5A pre-populates module fields from the group. D5B retires local inputs.

### E. Backward compatibility for existing analysis modules — RESOLVED

All three modules (Distance Protection, Impedance Analysis, Overcurrent Analysis) have independent CT/VT input fields in their existing API schemas. These will remain in place through D5A.

**D5A minimum contract:**
- Group CT/VT is available from the GET measurement-groups response
- When the user opens an analysis module, the module's CT/VT inputs are pre-populated from the linked group's CT/VT values (where a group is associated)
- Local override remains possible; overriding values are marked "overriding group configuration" in the UI
- The module's own CT/VT fields remain in the request body for backward compatibility

**D5B:** Local CT/VT inputs are retired from analysis module forms after equivalence verified and owner UAT accepted.

---

## 13. Final D1 Implementation Plan

**Scope:** Backend schema + API additions only. Frontend editing controls are Slice D4. Recording Details already displays "Not available from recording metadata" for CT/VT — this remains correct until D1 is implemented; after D1, actual values will display when configured.

### 13.1 New domain fields

**`VoltageBaseConfiguration` (backend/app/domain/voltage_group_config.py):**
Add after `manual_conflict_detail`:
```python
# D1: VT instrument-transformer winding quantities. Owned by Voltage groups only.
# vt_primary_v: Primary winding rated voltage, Volts L-L (e.g. 132000.0 for 132 kV system).
# vt_secondary_v: Secondary winding rated voltage, Volts L-L (e.g. 110.0 standard secondary).
# vt_authority: Provenance of the VT values.
# vt_provenance_note: Optional narrative (e.g. "from COMTRADE CFG header").
vt_primary_v: float | None = None
vt_secondary_v: float | None = None
vt_authority: str = "not_configured"  # "not_configured" | "recording_metadata" | "manual"
vt_provenance_note: str | None = None
```

**`CurrentBaseConfiguration` (backend/app/domain/current_group_config.py):**
Add after `base_authority`:
```python
# D1: CT instrument-transformer winding quantities. Owned by Current groups only.
ct_primary_a: float | None = None
ct_secondary_a: float | None = None
ct_authority: str = "not_configured"  # "not_configured" | "recording_metadata" | "manual"
ct_provenance_note: str | None = None
```

### 13.2 New view fields

**`VoltageGroupConfigView` / `CurrentGroupConfigView`** (measurement_group_view_service.py):
Wire the four new fields from each domain object through to the view. No calculation — pass through as-is.

### 13.3 New wire schema fields

**`VoltageGroupConfigOut`** (schemas/measurement_group.py):
```python
vt_primary_v: float | None = None
vt_secondary_v: float | None = None
vt_authority: str = "not_configured"
vt_provenance_note: str | None = None
```

**`CurrentGroupConfigOut`**:
```python
ct_primary_a: float | None = None
ct_secondary_a: float | None = None
ct_authority: str = "not_configured"
ct_provenance_note: str | None = None
```

All default to `None` / `"not_configured"` — backward-compatible; existing clients can ignore new fields.

### 13.4 PUT request body additions

**`VoltageGroupConfigUpdateRequest`** — add:
```python
vt_primary_v: float | None = None          # None = do not change
vt_secondary_v: float | None = None        # None = do not change
clear_vt: bool = False                     # True = clear VT config → "not_configured"
vt_provenance_note: str | None = None
clear_nominal_voltage: bool = False        # True = clear kV, re-trigger auto-detection
```
Validation:
- `clear_vt=True` with `vt_primary_v` or `vt_secondary_v` set → 422
- `clear_nominal_voltage=True` with `nominal_voltage_ll_kv` set → 422
- If `vt_authority` becomes `"manual"`, both `vt_primary_v > 0` and `vt_secondary_v > 0` required
- Partial (only primary): accepted with `vt_authority="manual"` but not persisted as effective pair until secondary is also set (see Section 13.5)

**`CurrentGroupConfigUpdateRequest`** — add:
```python
ct_primary_a: float | None = None
ct_secondary_a: float | None = None
clear_ct: bool = False
ct_provenance_note: str | None = None
```
Same validation pattern.

### 13.5 Service logic

**`update_voltage_configuration()` additions:**
- VT update path: validate, then `registry.update_fields(group_id, vt_primary_v=..., vt_secondary_v=..., vt_authority="manual", vt_provenance_note=...)`
- `clear_vt=True` path: `registry.update_fields(group_id, vt_primary_v=None, vt_secondary_v=None, vt_authority="not_configured", vt_provenance_note=None)`
- `clear_nominal_voltage=True` path: use `_KV_NOT_GIVEN`-style sentinel; set `nominal_voltage_ll_kv=None` + `base_authority="unavailable"`; then call `reconfigure_auto_base_after_membership_change()` — may resolve to `auto_resolved` or remain `needs_review`
- Partial pair rule: if only `vt_primary_v` is set (no `vt_secondary_v`), store primary but set `vt_authority="needs_secondary"` (or store partial with `"manual"` and let the frontend show an incomplete-pair warning). **Owner decision needed**: whether a partial pair is a 422 error or is stored as an incomplete state. For D1, treat as 422 (simpler, matches Q2 decision: effective configuration requires both).

**`update_current_configuration()` additions:** symmetric CT pattern.

### 13.6 Registry additions

**`VoltageGroupConfigRegistry.update_fields()`**: add `vt_primary_v`, `vt_secondary_v`, `vt_authority`, `vt_provenance_note` parameters.

**`CurrentGroupConfigRegistry.update_fields()`**: add `ct_primary_a`, `ct_secondary_a`, `ct_authority`, `ct_provenance_note` parameters.

### 13.7 Validation helpers

```python
def vt_ratio_valid(primary_v: float | None, secondary_v: float | None) -> bool:
    """Both values present, positive, finite."""
    return (primary_v is not None and secondary_v is not None
            and math.isfinite(primary_v) and math.isfinite(secondary_v)
            and primary_v > 0.0 and secondary_v > 0.0)
```
Mirrors `loop_ratio_valid()` at `distance_protection.py:179`.

### 13.8 Measurement-side compatibility warning

After storing CT/VT values, check if the group's channels all have `measurement_side="primary"`. If so, add a note to `vt_provenance_note` / `ct_provenance_note`: "Note: channels are already primary-side — verify that applying this VT/CT ratio does not double-scale values."

This is a soft warning appended by the service layer, not a blocking error (per Q4 decision).

### 13.9 Dependency invalidation contract

After a successful PUT that changes VT or CT fields:
1. The PUT response already returns the updated `MeasurementGroupOut` — the Recording Details panel re-renders automatically in Slice D Apply flow
2. Frontend must invalidate analysis result caches for the affected source: clear Distance Protection, Impedance Analysis, Overcurrent Analysis cached results
3. **Do NOT** increment `wwErState.perUnit.generation` — PU is not affected

---

## 14. Remaining Open Question (Post-Owner-Decisions)

**OQ-1 — Partial VT/CT pair persistence:**
The Q2 decision says "partial pairs allowed in unsaved frontend editing drafts only; not persisted." This means the backend should return 422 when only one of `vt_primary_v` / `vt_secondary_v` is set without the other (treating a partial pair as a validation error). Confirm this is the intended behavior before D1 implementation.

---

## 15. What D1 Must NOT Do (Confirmed Final)

- Do NOT apply CT/VT ratios to imported waveform samples or rescale `DisturbanceRecord.waveform_data`
- Do NOT infer CT/VT ratios from nominal voltage, equipment MVA, or channel magnitude
- Do NOT modify `auto_base_service.py` voltage-evidence pipeline
- Do NOT introduce CT/VT ratio into PU base calculations — `nominal_voltage_ll_kv` and `resolved_ibase_ka` remain the sole PU bases
- Do NOT make CT/VT configuration a prerequisite for PU eligibility
- Do NOT retire analysis-module CT/VT inputs (that is D5B, after D5A compatibility verification and owner UAT)
- Do NOT introduce database persistence — all state remains session-scoped
- Do NOT modify `PhysicalCalibrationAuthority` framework
- Do NOT infer a voltage-current group association from matching names

---

*Document updated 2026-11-18 with owner decisions and final implementation plan. Stop for owner approval before implementation begins.*
