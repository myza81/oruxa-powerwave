# RD-1 Slice D2 — Voltage Editing Preparation Plan

**Date:** 2026-11-18  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Status:** Awaiting owner approval before implementation  
**Prerequisite:** D1 backend implementation committed (d67163d)

---

## 1. D1 CT/VT Configuration Lifecycle Verification

**Verified — all lifecycle paths are correct.**

| Event | Registry effect | Evidence |
|-------|----------------|----------|
| Recording selected / group navigated to | No change — config persists across navigation | `wwRdState` reads from `ww.measurementGroups` cache |
| Recording (source) removed | `delete_group()` / `remove_measurement_groups_for_source()` clean `VoltageGroupConfigRegistry` and `CurrentGroupConfigRegistry` | `measurement_group_service.py` lifecycle methods |
| "Start New Workspace" (workspace reset) | `remove_workspace()` on both registries | `app/main.py` lifespan wiring |
| Server restart | All in-memory state lost (session-scoped, by design) | Registry docstrings |
| PUT voltage-config with VT fields | `update_vt=True` path in `update_fields()` stores `vt_primary_v`/`vt_secondary_v`/`vt_authority`/`vt_provenance_note` | `voltage_group_config_registry.py:103–148` |
| PUT current-config with CT fields | `update_ct_config()` via `update_fields()` on `CurrentGroupConfigRegistry` | `current_group_config_service.py` |
| Wire schema | `vt_*` / `ct_*` fields present in `VoltageGroupConfigOut` / `CurrentGroupConfigOut` | `schemas/measurement_group.py:51–105` |

**Conclusion:** D1 CT/VT config attaches to the same lifecycle as the measurement group itself. No orphaned config risk.

---

## 2. Existing Voltage PUT Contract

**Endpoint:** `PUT /api/v1/workspaces/{wid}/sources/{sid}/measurement-groups/{gid}/voltage-config`

**Current `VoltageGroupConfigUpdateRequest` fields:**

```python
nominal_voltage_ll_kv: float | None = None      # None → preserve (NOT clear)
reference_mode: VoltageReferenceMode = "auto"   # defaults to "auto"
reference_override: VoltageReferenceValue | None = None
base_reference_side: ReferenceSide = "unknown"
secondary_voltage_ll_v: float | None = None     # Note: not sent by existing UI
vt_primary_v: float | None = None               # D1
vt_secondary_v: float | None = None             # D1
vt_provenance_note: str | None = None           # D1
clear_vt: bool = False                          # D1
```

**Service behaviour (`update_voltage_configuration()`):**

- `nominal_voltage_ll_kv=None` → **preserve existing kV** (docstring: "None nominal means preserve the base")
- `nominal_voltage_ll_kv=<value>` → sets kV, sets `base_authority="manual"`, clears `secondary_voltage_ll_v`
- `reference_mode` always has a value (defaults `"auto"`); `"auto"` → `reference_override` is cleared
- After any kV change: API layer calls `reconfigure_auto_base_after_membership_change()` for RD-0B conflict detection
- `base_authority` is **never caller-settable** — derived from edit intent internally

**Gap for D2:** No `clear_nominal_voltage` field exists. Setting `nominal_voltage_ll_kv=None` is a no-op for the nominal kV, not a revert-to-auto operation.

**Existing UI sends:** `{ nominal_voltage_ll_kv, reference_mode, reference_override }` only. It does not echo `base_reference_side`, `secondary_voltage_ll_v`, or VT fields — meaning every save through the existing UI resets `base_reference_side` to `"unknown"` (schema default). This is an existing limitation of the old drawer UI.

---

## 3. Revert-to-Auto Contract (`clear_nominal_voltage`)

### 3.1 Schema change

Add to `VoltageGroupConfigUpdateRequest`:

```python
clear_nominal_voltage: bool = False
```

**Validation rules:**
- `clear_nominal_voltage=True` AND `nominal_voltage_ll_kv` is not `None` → HTTP 422
  (`"clear_nominal_voltage and nominal_voltage_ll_kv cannot both be set"`)
- `clear_nominal_voltage=True` AND `clear_vt=True` is allowed (independent fields)

### 3.2 Service change

In `update_voltage_configuration()`, add a `clear_nominal_voltage: bool = False` parameter:

**When `clear_nominal_voltage=True`:**
1. Reset registry to: `nominal_voltage_ll_kv=None`, `base_authority="needs_review"`,
   `manual_conflict_detected=False`, `manual_conflict_detail=None`,
   `secondary_voltage_ll_v=None` (stale secondary always cleared with primary)
2. Re-run auto-base evidence analysis for the group by calling a new public function
   `reconfigure_auto_base_for_voltage_group()` (see §3.3).
3. The result of that re-run sets the final `base_authority` and `nominal_voltage_ll_kv`.
4. Return the final `VoltageBaseConfiguration` (then mapped through the full response builder).

**When `clear_nominal_voltage=False`** (the default): existing logic unchanged.

### 3.3 Auto-base re-run after clear

A new public function in `auto_base_service.py`:

```python
def reconfigure_auto_base_for_voltage_group_after_clear(
    *, workspace_id, source_id, measurement_group_id,
    source_registry, group_registry, voltage_config_registry,
) -> VoltageGroupAutoResult | None
```

**Contract:**
- Explicitly authorised to re-run even when `base_authority` was previously `"manual"` or `"legacy_manual"` —
  because the engineer explicitly requested a clear (this is the one exception to constraint C4).
- Calls `_configure_voltage_group()` directly after the registry has already been reset to `needs_review`.
- At that point `_configure_voltage_group()` will NOT skip on the `is_engineer_approved()` guard
  (authority is now `needs_review`), so normal evidence resolution runs.
- Result:
  - Sufficient evidence → `auto_resolved` with detected kV
  - BEN channels / insufficient evidence → remains `needs_review`, `nominal_voltage_ll_kv=None`
- Never raises (C6).

### 3.4 API layer

In `put_voltage_config()`:

```python
if body.clear_nominal_voltage:
    # Step 1: clear and re-run auto-base
    reconfigure_auto_base_for_voltage_group_after_clear(
        workspace_id=workspace_id, source_id=source_id,
        measurement_group_id=measurement_group_id,
        source_registry=..., group_registry=...,
        voltage_config_registry=...,
    )
    # Step 2: also clear any existing VT if clear_vt was set
    if body.clear_vt:
        update_voltage_configuration(..., clear_vt=True, ...)
    # Build and return response
    return _build_group_response(...)
else:
    # Existing path
    update_voltage_configuration(
        ..., clear_nominal_voltage=False, ...
    )
    reconfigure_auto_base_after_membership_change(...)  # RD-0B
    return _build_group_response(...)
```

> **Note:** `reconfigure_auto_base_after_membership_change()` is NOT called on the
> clear path, because `reconfigure_auto_base_for_voltage_group_after_clear()` already
> performs a full evidence re-run. Calling both would be redundant and could
> unexpectedly re-flag a conflict that the clear was intended to resolve.

---

## 4. Frontend Dependency Invalidation Map

After a successful voltage config PUT from the RD-1 panel:

| Surface | Current state | After config change | Update mechanism |
|---------|--------------|---------------------|------------------|
| `ww.measurementGroups` Map | Stale `VoltageGroupConfigOut` | Updated | Replace specific group entry from PUT response body |
| RD-1 Column 2 group list | Shows old base authority badge | Needs refresh | Re-render `wwRdRenderGroupList()` |
| RD-1 Column 3 group details | Shows old config values | Needs refresh | Re-render `wwRdRenderDetails()` |
| Measurement Groups modal | May be open concurrently | Stale | Full re-fetch on next modal open (lazy — acceptable) |
| PU waveform display | Stale PU basis | Re-derive | `wwRefreshDisplayedChannelsForPerUnitChange(sourceId)` |

**Cache update strategy (D2):**

The PUT endpoint already returns the full `MeasurementGroupOut`. Rather than a full
group list re-fetch (as the existing drawer does), the RD-1 panel should:

```js
// 1. Patch the specific group in the cache
const groups = ww.measurementGroups.get(sourceId) || [];
const idx = groups.findIndex(g => g.id === groupId);
if (idx >= 0) groups[idx] = updatedGroup; // updatedGroup = PUT response body
ww.measurementGroups.set(sourceId, groups);

// 2. Re-render RD-1 (both column 2 and column 3 read from ww.measurementGroups)
wwRdRender();

// 3. If in PU mode, refresh waveform display
await wwRefreshDisplayedChannelsForPerUnitChange(sourceId);
```

This avoids an extra round-trip and keeps the RD-1 panel feel instant.

---

## 5. Reference Mode / Side Preservation

**Current risk:** `reference_mode` defaults to `"auto"` in the schema, so a D2 edit
that sends only `nominal_voltage_ll_kv` will also silently reset `reference_mode` to
`"auto"` and clear any existing `reference_override`.

**D2 frontend must:** echo back the current `reference_mode`, `reference_override`,
and `base_reference_side` values in the PUT body when editing only the nominal kV.
These are available from the group's current `voltage_config` in the cache.

Concretely, the D2 "Edit kV" PUT body will be:
```json
{
  "nominal_voltage_ll_kv": <new value or existing>,
  "reference_mode": "<current group.voltage_config.reference_mode>",
  "reference_override": "<current group.voltage_config.reference_override or null>",
  "base_reference_side": "<current group.voltage_config.base_reference_side>"
}
```

For "Revert to Auto":
```json
{
  "clear_nominal_voltage": true,
  "reference_mode": "auto"
}
```

(The backend's `clear_nominal_voltage` path will reset the reference to `"auto"` automatically,
but sending `reference_mode: "auto"` explicitly in the body ensures no ambiguity.)

---

## 6. Proposed D2 UI Editing Workflow

### 6.1 "Base Configuration" section in Group Details (Voltage Groups only)

**Display state (read-only, default):**
- Current nominal kV value (or "Not configured")
- Base authority badge
- `[Edit]` button (always visible for voltage groups)
- `[Revert to Auto]` button (visible only when `base_authority === "manual"`)

**Edit state (after `[Edit]` clicked):**
- Input field pre-populated with current kV (or empty)
- `[Apply]` button (disabled until input is valid: non-empty, positive number)
- `[Cancel]` button
- Validation error shown inline (e.g. "Must be a positive number")

**Apply flow:**
1. Client-side validation (required, positive finite float)
2. PUT with `{ nominal_voltage_ll_kv: <value>, reference_mode: <current>, reference_override: <current>, base_reference_side: <current> }`
3. On success: patch `ww.measurementGroups` from response, re-render, trigger PU refresh if needed
4. On 422: show server error message inline
5. Return to read-only state

**Revert to Auto flow:**
1. Confirm not needed (non-destructive: auto-base will re-run)
2. PUT with `{ clear_nominal_voltage: true, reference_mode: "auto" }`
3. Same success path as Apply
4. `[Revert to Auto]` button disappears (authority is no longer `"manual"`)

### 6.2 Section isolation

- Editing kV **does not** affect the VT section (which will be D4)
- The PUT body for kV editing never includes `vt_*` fields → VT config is preserved

---

## 7. Files Expected to Change

**Backend:**
- `backend/app/schemas/measurement_group.py` — add `clear_nominal_voltage: bool = False` to `VoltageGroupConfigUpdateRequest`
- `backend/app/services/voltage_group_config_service.py` — add `clear_nominal_voltage` parameter and routing logic
- `backend/app/services/auto_base_service.py` — add `reconfigure_auto_base_for_voltage_group_after_clear()`
- `backend/app/api/v1/measurement_groups.py` — pass `clear_nominal_voltage` through; dispatch to clear path

**Tests:**
- `backend/tests/test_d2_clear_nominal_voltage.py` — new (see §8)

**Frontend:**
- `frontend/index.html` — `wwRdBuildDetailsHtml()` Base Configuration section: add Edit/Apply/Cancel/Revert-to-Auto controls

**Browser tests:**
- `browser-tests/rd1-slice-d2.spec.js` — new

---

## 8. Regression Tests and Acceptance Criteria

### Backend unit tests (`test_d2_clear_nominal_voltage.py`)

| ID | Scenario | Expected result |
|----|----------|-----------------|
| D2-BE-01 | `clear_nominal_voltage=True` + kV set → 422 | HTTP 422 `conflicting_clear_and_set` |
| D2-BE-02 | Clear on group with `base_authority="manual"` and sufficient COMTRADE evidence | `auto_resolved`, detected kV in response |
| D2-BE-03 | Clear on group with `base_authority="manual"` and insufficient evidence (BEN) | `needs_review`, `nominal_voltage_ll_kv=null` |
| D2-BE-04 | Clear on group with `base_authority="auto_resolved"` | Re-runs evidence; same or updated `auto_resolved` kV |
| D2-BE-05 | Clear clears `secondary_voltage_ll_v` | `secondary_voltage_ll_v=null` in response |
| D2-BE-06 | Clear clears `manual_conflict_detected` flag | `manual_conflict_detected=false` in response |
| D2-BE-07 | Set new kV preserves existing `reference_mode="manual"` when echoed | Reference fields unchanged |
| D2-BE-08 | `clear_nominal_voltage=True` + `clear_vt=True` is allowed | Both cleared, no 422 |
| D2-BE-09 | Clear on `needs_review` group re-runs evidence | Same as D2-BE-03 |
| D2-BE-10 | Response is full `MeasurementGroupOut`, not just config | Contains `id`, `kind`, `pu_status`, etc. |

### Browser tests (`rd1-slice-d2.spec.js`)

| ID | Scenario | Assertion |
|----|----------|-----------|
| D2-BT-01 | Voltage group details shows `[Edit]` button | Button visible |
| D2-BT-02 | Click `[Edit]` → input appears pre-populated | Input has current kV value |
| D2-BT-03 | Clear input → `[Apply]` disabled | Button has `disabled` attribute |
| D2-BT-04 | Enter invalid value (negative) → inline error | Error message visible |
| D2-BT-05 | Enter valid kV, Apply → success, details panel updated | Shows new kV, authority "Manual" |
| D2-BT-06 | `[Revert to Auto]` only visible for `base_authority="manual"` | Hidden for `auto_resolved`/`needs_review` |
| D2-BT-07 | Revert to Auto → `base_authority` changes in panel | No longer shows "Manual" badge |
| D2-BT-08 | Cancel edit → panel returns to read-only, no change | Original value shown |
| D2-BT-09 | Backend 422 during Apply → inline error shown | Error message visible, stays in edit mode |
| D2-BT-10 | Group list (Column 2) badge updates after Apply | Badge reflects new authority |

---

## 9. Open Questions for Owner

| # | Question | Impact |
|---|----------|--------|
| OQ-D2-1 | When `clear_nominal_voltage=True`, should the reference_mode also revert to `"auto"` **unconditionally**, or should it preserve the current `reference_mode`? **Recommended:** revert to `"auto"` — a nominal kV clear is a full "return to auto" intent, and a stale manual reference without a nominal kV is meaningless. | Backend service logic |
| OQ-D2-2 | Should the `[Edit]` button appear for voltage groups in `needs_review` state (no auto-detected kV), or only for groups with an existing manual or auto kV? **Recommended:** always show `[Edit]` for any voltage group — it's the path to resolve `needs_review`. | Frontend only |
| OQ-D2-3 | The `secondary_voltage_ll_v` field is set by the auto-base service for secondary-side recordings. It is NOT exposed in the D2 edit UI. Should it be preserved when the engineer manually edits the primary nominal kV? Currently the service clears it (stale-secondary rule). **Recommended:** clear it (existing service behavior is correct). | No code change needed if confirmed |
| OQ-D2-4 | The `base_reference_side` field defaults to `"unknown"` in the schema. The D2 "Edit kV" PUT will echo back the current `base_reference_side`. Is this the correct behavior, or should D2 also expose a `base_reference_side` selector? **Recommended:** echo back without a selector in D2 — this keeps D2 focused; a side-selector can be added in a later slice if needed. | Frontend scope |

---

## 10. Summary

**D2 scope is well-bounded:**

- **Backend:** 4 files, ~60 lines of new logic, 10 new unit tests
- **Frontend:** `wwRdBuildDetailsHtml()` Base Configuration section, Edit/Apply/Cancel/Revert controls, cache-patch pattern
- **Browser tests:** 1 new spec file, 10 tests

**No changes to:**
- PU mathematics or waveform ingestion
- CT/VT configuration (D4)
- Equipment rating editing (D3)
- Reference mode selector (deferred)

**Risks:**
- Low — `clear_nominal_voltage` is a new field with a boolean guard; existing `nominal_voltage_ll_kv=None` semantics are unchanged
- The auto-base re-run on clear requires explicitly bypassing C4 — this is correct and intentional (engineer explicitly requested it), but the new function must document the C4 exception clearly to prevent future misuse

**Recommendation:** Proceed to D2 implementation once owner approves the OQ answers above, particularly OQ-D2-1 (reference mode behavior on clear).
