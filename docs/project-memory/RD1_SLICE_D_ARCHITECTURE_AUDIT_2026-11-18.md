# RD-1 Slice D — Architecture and Implementation Audit

**Date:** 2026-11-18  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Head commit:** `23f1117`  
**Status:** Read-only audit. No production files modified.

---

## 1. Existing Voltage Editing Contract

### What exists today

**Endpoint:** `PUT /api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups/{id}/voltage-config`  
**Request schema:** `VoltageGroupConfigUpdateRequest`

Editable fields:
- `nominal_voltage_ll_kv: float | None` — set manual kV (None = preserve existing; no "clear to null" operation exists)
- `reference_mode: "auto" | "manual"` — switching to "auto" clears the override (`return_voltage_reference_to_auto()`)
- `reference_override: "line_to_ground" | "line_to_line" | None` — required when `reference_mode="manual"`
- `base_reference_side: ReferenceSide` — primary/secondary/unknown declaration
- `secondary_voltage_ll_v: float | None` — secondary equivalent voltage

**Post-edit behaviour:**  
1. `update_voltage_configuration()` validates, sets `base_authority = "manual"`, clears conflict flag  
2. If `nominal_voltage_ll_kv` is supplied, `reconfigure_auto_base_after_membership_change()` immediately re-evaluates evidence and re-flags conflict if the new kV is incompatible (RD-0B safety)  
3. Returns updated `MeasurementGroupOut` with new `pu_status`/`pu_reason`/`base_authority`

**What is missing:**
- **No "clear nominal kV to null" operation.** The docstring explicitly says there is no "clear" operation. Setting a manual kV can only be superseded by another manual kV. `return_voltage_reference_to_auto()` only clears the reference override — it does NOT reset `nominal_voltage_ll_kv` or `base_authority` back to `needs_review`/`unavailable`.
- **No "revert base to automatic" endpoint.** No path exists to clear a manual kV and trigger re-auto-detection. This is the gap identified in Slice C-2.

---

## 2. Existing Current / Equipment Rating Editing Contract

### What exists today

**Endpoint:** `PUT /api/v1/.../measurement-groups/{id}/current-config`  
**Request schema:** `CurrentGroupConfigUpdateRequest`  

The endpoint dispatches to one of three method setters:

| `method` | Service function | Key inputs |
|---|---|---|
| `"equipment_rating"` | `set_current_base_equipment_rating()` | `equipment_rating_mva`, `linked_voltage_group_id` (required), optional `manual_voltage_base_kv` |
| `"manual"` | `set_current_base_manual()` | `manual_ibase_ka` |
| `"none"` | `set_current_base_none()` | (clears all current config) |

**Current base calculation:** `resolved_ibase_ka = equipment_rating_mva / (√3 × applicable_voltage_ll_kv)` — computed server-side, never by the frontend.

**What is fully supported today:**
- Setting equipment rating MVA + linked voltage group
- Switching method (equipment_rating → manual → none)
- Clearing current configuration entirely (`method="none"`)
- Linking to a specific voltage group for the kV derivation

**What is missing:**
- No "inherit kV from group" without explicit `linked_voltage_group_id` — the engineer must name the group
- No automatic CT ratio field on the current group config

---

## 3. CT/VT Ownership (Current State)

### Where CT/VT ratios live today

**NOT in Measurement Group schemas.** Neither `VoltageGroupConfigOut` nor `CurrentGroupConfigOut` carry any CT/VT ratio fields.

**Where they DO live — per-analysis-module, per-request:**

| Module | Schema | Fields | Editable by user? |
|---|---|---|---|
| Impedance Analysis | `ImpedanceAnalysisRequest` (inferred) | `vt_primary`, `vt_secondary`, `ct_primary`, `ct_secondary` | Yes — numeric input fields in the UI |
| Distance Protection | `DistanceProtectionAnalysisRequest` | `vt_primary`, `vt_secondary`, `ct_primary`, `ct_secondary` | Yes — numeric input fields in the UI |
| Overcurrent Analysis | `OvercurrentAnalysisRequest` | `ct_primary`, `ct_secondary` | Yes — conditionally shown fields |

**Frontend state:** Each analysis module maintains its own local state object with `ctPrimary`, `ctSecondary`, `vtPrimary`, `vtSecondary`. These are independent per-module values populated from the analysis settings panel, not from Measurement Groups.

**How CT/VT ratios are used:** Applied to convert between primary and secondary representations of waveform magnitudes for impedance locus and distance protection calculations. They are applied to derived quantities (phasors), **not** directly to raw sample arrays.

**Key architectural implication:** CT/VT ratios exist today only as transient per-analysis-module state. There is no authoritative single-source-of-truth record for CT/VT configuration. This is the gap that must be closed in Slice D Stage 1.

---

## 4. Dependency Map

### Voltage base consumers

| Consumer | File | How it uses voltage base |
|---|---|---|
| PU display (waveform) | `group_aware_per_unit.py` | `ibase_ka` from resolution; voltage base used to normalise voltage channels |
| Compliance measurement | `compliance_measurement_service.py` | `nominal_voltage_ll_kv` + `effective_reference` for PQ compliance voltage comparisons |
| Per-unit provenance | `per_unit_provenance_service.py` | `nominal_voltage_ll_kv` for display/traceability text |
| Auto-base detection | `auto_base_service.py` | Writes `nominal_voltage_ll_kv`; compares detected kV against existing manual kV |
| Current base derivation | `current_group_config_service.py` | Reads linked voltage group's `nominal_voltage_ll_kv` for Ibase = MVA/(√3·kV) |

### Current base consumers

| Consumer | File | How it uses current base |
|---|---|---|
| PU display (waveform) | `group_aware_per_unit.py` | `ibase_ka × 1000.0` as the per-unit base amount for current normalisation |
| Per-unit provenance | `per_unit_provenance_service.py` | `equipment_rating_mva`, `applicable_voltage_ll_kv` for display text |
| Overcurrent analysis | `overcurrent_analysis_service.py` | `equipment_rating_mva` for equipment loading calculation (independent path) |

### PU eligibility consumers

- `voltage_group_config.py:resolve_voltage_base_for_group()` — authority gate + conflict gate
- `current_group_config.py` — `is_base_eligible_for_pu()` checks `base_authority`
- `measurement_group_view_service.py` — computes `pu_status`/`pu_reason` for the wire response
- Frontend `wwMgPuBadge()` — renders badge in Measurement Group list (Waveform workspace)
- Frontend `wwRdPuEligibilityHtml()` — renders eligibility section in Recording Details

---

## 5. Invalidation Mechanisms

### Backend
No explicit cache invalidation mechanism. All resolution is live (re-derived from registry state on every request). The `MeasurementGroupView` is computed fresh on each `build_group_view()` call. No stale cached views.

### Frontend
**`wwErState.perUnit.generation`**: integer counter incremented when PU settings may have changed. Currently incremented in one place only — `wwErOnPageEntered()` — meaning PU cache is invalidated on every navigation to the Event Reconstruction page, **not** on individual voltage/current config edits.

**Gap:** After a Slice D voltage-config or current-config PUT, the frontend must:
1. Re-fetch the measurement groups for the affected source (`ww.measurementGroups` cache)
2. Call `wwRdRenderDetails()` and `wwRdRenderGroups()` to update the Recording Details panel
3. Increment `wwErState.perUnit.generation` to invalidate the Event Reconstruction PU cache
4. Invalidate any per-unit waveform traces that belong to the affected group

Currently none of steps 1–4 happen automatically after a config edit. Slice D must wire them in.

---

## 6. Session Persistence

All registries are **in-memory, session-scoped** Python objects attached to `app.state`:
- `app.state.workspace_registry`
- `app.state.measurement_group_registry`
- `app.state.voltage_group_config_registry`
- `app.state.current_group_config_registry`

They are instantiated at application startup (`backend/app/main.py:73–97`) and live for the process lifetime. **Manual edits (voltage kV, current method, group membership) do not persist to disk and are lost on server restart.**

The existing UI preserves the workspace across browser refresh via `localStorage workspace_id`, but the workspace state only survives while the backend process is running.

**Implication for Slice D:** Apply/Cancel is entirely a UI-side concern. The backend has no transaction or draft concept — every PUT immediately commits to the in-memory registry. Cancel must be implemented as a frontend-only rollback using the cached pre-edit group state.

---

## 7. Revert-to-Automatic Gap

**Confirmed absent.** `return_voltage_reference_to_auto()` exists and is tested, but it only clears the **reference override** (line_to_line/line_to_ground). It does not clear `nominal_voltage_ll_kv`.

There is no path to:
- Clear `nominal_voltage_ll_kv` to `None`
- Reset `base_authority` from `"manual"` back to `"needs_review"` or `"unavailable"`
- Re-trigger auto-detection after a manual kV has been set

**Minimum safe contract for Slice D Stage 2:**

Option A — extend `VoltageGroupConfigUpdateRequest` with a `clear_nominal_voltage: bool = False` flag:
- When `True`, sets `nominal_voltage_ll_kv = None`, resets `base_authority` to its pre-manual state, then runs auto-detection
- Risk: requires careful handling of the authority state machine (manual → what state?)

Option B — a dedicated `DELETE /voltage-config/nominal-voltage` endpoint:
- Cleaner semantics; unambiguous intent
- Server clears `nominal_voltage_ll_kv`, runs `reconfigure_auto_base_after_membership_change()`, which either resolves a new auto base or sets `needs_review`/`unavailable`
- Recommended: matches the ownership model and avoids misuse of the existing PUT

**Owner decision required** before Stage 2 implementation.

---

## 8. Staged Implementation Plan for Slice D

### Stage 1 — Backend: CT/VT ownership in Measurement Groups

**Objective:** Establish CT/VT ratios as authoritative group-level configuration.

Required backend changes:
- Add `ct_primary: float | None`, `ct_secondary: float | None` to `CurrentGroupConfigOut` and its domain/registry types
- Add `vt_primary: float | None`, `vt_secondary: float | None` to `VoltageGroupConfigOut` and its domain/registry types
- Extend `CurrentGroupConfigUpdateRequest` with optional CT ratio fields
- Extend `VoltageGroupConfigUpdateRequest` with optional VT ratio fields
- Extend the respective service setters to persist these values

**Regression risk:** Additive schema change. Existing consumers that do not read CT/VT from measurement groups are unaffected. Existing analysis-module CT/VT inputs remain unchanged until Stage 5.

**Acceptance criteria:**
- CT ratio set on a Current group appears in `CurrentGroupConfigOut`
- VT ratio set on a Voltage group appears in `VoltageGroupConfigOut`
- Existing analysis modules continue to use their own independent CT/VT inputs (no forced migration yet)

---

### Stage 2 — Backend: Revert-to-automatic contract + Frontend: Voltage base editing

**Objective:** Engineer can edit nominal kV and revert to automatic in Recording Details.

Required backend changes:
- Implement revert-to-automatic (Option B recommended: `DELETE /voltage-config/nominal-voltage` or `clear_nominal_voltage` flag per owner decision)
- Confirm `update_voltage_configuration()` already handles the full manual kV → conflict detection cycle (confirmed: RD-0B, already implemented)

Required frontend changes (Recording Details, Slice D):
- Add editable nominal kV field (number input) to Voltage Group Details panel
- Add reference mode selector (auto / manual + override)
- Apply / Cancel buttons — Cancel performs UI-only rollback from cached pre-edit state
- On successful Apply: re-fetch groups, call `wwRdRenderDetails()`, `wwRdRenderGroups()`, increment `wwErState.perUnit.generation`
- Revert button (uses new backend contract)

**Regression risk:** Medium. PU cache invalidation must not leave stale traces. Apply/Cancel must not leave the UI in a partially-edited state on network error.

**Acceptance criteria:**
- Setting 275 kV on a `needs_review` BEN group makes it PU-eligible
- Setting a conflicting kV triggers the RD-0B conflict banner
- Reverting to automatic returns the group to `needs_review` for BEN
- PU waveform display refreshes after Apply
- Cancel returns all fields to their pre-edit values

---

### Stage 3 — Frontend: Equipment rating (MVA) editing

**Objective:** Engineer can set/change MVA rating and linked voltage group.

Required backend changes: None (endpoint already exists: `PUT .../current-config` with `method="equipment_rating"`)

Required frontend changes:
- Add MVA input field + linked voltage group selector to Current Group Details
- Apply / Cancel with same invalidation pattern as Stage 2

**Regression risk:** Low. Endpoint and service are fully implemented and tested.

---

### Stage 4 — Frontend: CT/VT editing (depends on Stage 1)

**Objective:** Engineer can set CT ratio (Current Group) and VT ratio (Voltage Group) in Recording Details.

Required frontend changes:
- Add CT primary/secondary inputs to Current Group Details
- Add VT primary/secondary inputs to Voltage Group Details
- Apply / Cancel with group re-fetch

**Prerequisite:** Stage 1 must be complete (backend fields exist).

**Regression risk:** Low until Stage 5 (analysis modules still use their own inputs).

---

### Stage 5 — Analysis module migration to group-level CT/VT

**Objective:** Eliminate per-analysis-module CT/VT inputs; use group-level values as the single source of truth.

Affected modules:
- Impedance Analysis: `wwImpedanceManualVtPrimaryInput`, `wwImpedanceManualCtPrimaryInput` etc.
- Distance Protection: `wwDistanceManualVtPrimaryInput`, `wwDistanceManualCtPrimaryInput` etc.
- Overcurrent Analysis: `wwOvercurrentCtPrimaryInput`, `wwOvercurrentCtSecondaryInput`

Migration strategy:
1. When a Measurement Group is selected for a module, pre-populate the module's CT/VT inputs from the group's authoritative values
2. Only after a UAT acceptance period: remove the per-module manual CT/VT inputs entirely

**Regression risk:** High. This is the highest-risk stage and must follow comprehensive regression testing. The existing per-module inputs are used in all existing analysis workflows. No waveform samples are modified. Apply/Cancel must be implemented in Stage 2 first.

**Owner decision required** on the migration strategy (pre-populate vs. hard-enforce) before Stage 5 begins.

---

## 9. API Gaps Requiring Owner Decisions

| Gap | Options | Recommendation |
|---|---|---|
| Revert nominal kV to auto | A: `clear_nominal_voltage` flag on existing PUT; B: dedicated DELETE endpoint | Option B (cleaner semantics) |
| CT/VT ownership in measurement groups | Add fields to existing config schemas | Additive — safe, proceed in Stage 1 |
| Analysis module migration strategy | Pre-populate (soft) vs. hard-enforce (remove manual inputs) | Pre-populate first, hard-enforce after UAT |
| Apply/Cancel transaction semantics | UI-only rollback vs. server-side draft/commit | UI-only (server has no transaction support; this is correct for session-scoped state) |

---

## 10. Invariants Slice D Must Preserve

1. Physical waveform samples must not be rescaled by CT/VT ratios stored in Measurement Groups
2. `nominal_voltage_ll_kv` is a line-to-line primary voltage; engineers enter the familiar system voltage directly
3. `resolved_ibase_ka` is always server-computed (MVA/(√3·kV)); the frontend must never recompute it
4. `base_authority = "manual"` is set only by an explicit engineer PUT, never by auto-detection
5. `auto_resolved` is set only by `reconfigure_auto_base_after_membership_change()`, never by the editing path
6. The RD-0B conflict guard (`manual_conflict_detected`) must be re-evaluated after every kV edit
7. PU calculations for the Event Reconstruction workspace must be re-fetched after any effective base change
8. CT/VT ratios in Distance Protection and Impedance Analysis are applied to phasor magnitudes for unit conversion, not to raw sample arrays; this must remain unchanged through any migration
9. Per-analysis-module CT/VT inputs must remain functional until Stage 5 migration is explicitly approved and tested
10. Session-scoped storage is intentional; Slice D must not introduce silent persistence to disk without an explicit architecture decision

---

*This document is untracked and not committed. For owner review before Slice D implementation.*
