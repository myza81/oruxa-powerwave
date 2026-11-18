# RD-1 Slice C — Engineering State & Group Details UX Audit

**Date:** 2026-11-18  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Baseline:** `6cdb2af` (Slice C-1 tabs)  
**Scope:** Read-only audit. No production files modified.

---

## 1. Root Cause: "Base invalidated" for KTBR / PMJY1 VOLTAGE

### What the state actually is

`"Base invalidated"` is **not** a stale-state defect. It is the UI string that the
frontend renders whenever `pu_reason === "base_invalidated"`. That `reason` string
is returned by `resolve_voltage_base_for_group()` in
`backend/app/domain/voltage_group_config.py` (line 276–277) when:

```python
if config is not None and not is_base_eligible_for_pu(config.base_authority):
    return VoltageBaseResolution(
        status=STATUS_BASE_REQUIRED, reason="base_invalidated"
    )
```

`is_base_eligible_for_pu()` returns `False` for **two distinct** `base_authority`
values: `"needs_review"` and `"unavailable"`. Both reach the same code path and
emit the same `"base_invalidated"` reason. The UI cannot distinguish them.

### Which state does PMJY1 VOLTAGE hold?

`base_authority = "needs_review"`. The sequence:

1. BEN recording is imported. `PMJY1 VOLTAGE` is a suggested or confirmed voltage
   group.
2. `run_auto_base_for_source()` is called. For each voltage group,
   `_configure_voltage_group()` builds `ChannelAutoMetadata` for each channel.
3. BEN channels: `measurement_side = "unknown"` — BEN has no COMTRADE PS flag.
4. `resolve_voltage_group_evidence()` runs. `measurement_side = "unknown"`,
   `side_declared = False`. Both primary path (`measurement_side == "primary"`)
   and secondary path (`measurement_side == "secondary"`) gate checks fail.
5. Falls to the **insufficient evidence** branch. The service writes:
   `base_authority = BASE_AUTHORITY_NEEDS_REVIEW`.
   `nominal_voltage_ll_kv` is NOT written here — it retains whatever value it
   previously had (typically `None` on first import).
6. At display time, `resolve_voltage_base_for_group()` checks
   `is_base_eligible_for_pu("needs_review")` → `False` → returns
   `reason="base_invalidated"`.

### Why can't the engine resolve the nominal voltage?

The auto-base service has three paths for writing `base_authority = "auto_resolved"`:

- **Primary path** (line 267): `measurement_side == "primary" and sufficient_for_auto_nominal`.
- **Secondary path** (line 244): `measurement_side == "secondary" and sufficient_for_auto_side`.
- Neither fires for BEN because `measurement_side = "unknown"`.

Even when channel-name kV tokens (e.g., `"275KV"`) or VT winding ratios could
produce a nominal candidate with medium confidence, the engine will not write
`auto_resolved` for a BEN group. The service correctly refuses to infer
measurement side from winding data alone (C2/C4 constraints from
`auto_base_evidence.py`).

This is correct behavior, not a defect. BEN recordings with unknown measurement
side require the engineer to manually enter the nominal voltage for PU eligibility.

### Why "Base invalidated" is misleading

The term implies that a previously working value was broken by a subsequent event.
For BEN recordings, the base was **never** auto-resolved — evidence was simply
insufficient on first analysis. The backend uses `"needs_review"` correctly to
mean "evidence analysed but insufficient." The frontend label "Base invalidated"
does not reflect that meaning.

The same `reason="base_invalidated"` is emitted for the genuinely invalidated
case (`base_authority = "unavailable"` — a formerly `auto_resolved` base that was
subsequently contradicted). The frontend cannot distinguish these two situations
because `base_authority` is not in the wire schema.

**This is a frontend label defect, not an engineering logic defect.**

---

## 2. "Not configured" Authority Label

The UI authority label is derived by the frontend (line 36844–36853) because
`base_authority` is not in the wire schema (`VoltageGroupConfigOut` does not
expose it):

```js
if (!vc || vc.nominal_voltage_ll_kv == null) {
    authorityLabel = "Not configured";
}
```

For PMJY1 VOLTAGE: `nominal_voltage_ll_kv = null` (the `needs_review` path in the
service never writes nominal kV) → `authorityLabel = "Not configured"`.

This is technically correct — there is no configured kV — but conveys the wrong
situation. It implies the engineer has not yet interacted with this group, when in
fact the auto-detection engine has run, examined the evidence, and determined it
was insufficient for automatic resolution. A better label is
**"Evidence insufficient — configure manually"** (or similar).

---

## 3. Current Base Configuration Fields

Source: `backend/app/domain/current_group_config.py`,
`backend/app/schemas/measurement_group.py` (`CurrentGroupConfigOut`).

| Field | Engineering meaning | Source | Recommended visibility |
|---|---|---|---|
| `method` | Derivation approach: `equipment_rating` = Ibase from Sbase / (√3 × VLL); `manual` = direct kA entry; `none` = PU not available | Engineer-set | **Main view** — essential context |
| `resolved_ibase_ka` | Calculated effective Ibase (kA). The actual engineering result. NULL when unresolved | Derived read-only | **Main view** — primary result |
| `applicable_voltage_ll_kv` | The VLL used in the Ibase calculation (from linked V group or manual_voltage_base_kv). NULL when unresolved | Derived read-only | **Main view** when resolved; evidence otherwise |
| `manual_ibase_ka` | Direct Ibase entry (method = manual only) | Engineer-set | **Main view** when method = manual |
| `equipment_rating_mva` | Equipment rated MVA for the Ibase denominator calculation | Engineer-set | **Evidence** — input to calculation |
| `linked_voltage_group_id` | Internal ID of linked V group whose nominal_voltage_ll_kv provides VLL | Engineer-set | **Evidence** — internal ID, not useful raw; could display linked group name |
| `manual_voltage_base_kv` | Standalone manual VLL when no linked V group | Engineer-set | **Evidence** — only when no linked V group |
| `base_reference_side` | Primary or secondary measurement side | Config or auto-detected | **Evidence** |

**PU eligibility for current groups:** follows the same `pu_status` / `pu_reason`
pattern. No auto-Ibase detection exists (CT primary excluded per DEC-050 §11,
`auto_base_evidence.py` C5). Current groups always require manual configuration.

---

## 4. Proposed Group Details Information Hierarchy

### Voltage group

**Main view (always visible):**

```
Nominal voltage:    275 kV (L-L)        ← nominal_voltage_ll_kv, or "—" with note
Reference:          Line-to-ground (auto-detected)
Configuration:      [authority label — see mapping below]
PU availability:    [pill — see mapping below]
```

**Conflict banner** (only when `manual_conflict_detected === true`):
```
⚠ Voltage Base Conflict Detected
  [manual_conflict_detail or fallback text]
```

**Expandable Engineering Evidence:**
- Detection reason
- Evidence channels
- Reference mode / override
- Reference side
- Secondary L-L voltage (if applicable)

---

**Improved authority label mapping** (can be implemented without wire schema change):

| Condition | Proposed label |
|---|---|
| `vc` absent or `nominal_voltage_ll_kv == null` and `pu_reason != "base_invalidated"` | Not configured |
| `pu_reason === "base_invalidated"` and `nominal_voltage_ll_kv == null` | Evidence insufficient — configure manually |
| `pu_reason === "base_invalidated"` and `nominal_voltage_ll_kv != null` | Auto-resolved base invalidated |
| `manual_conflict_detected === true` | Manual (conflict — see warning) |
| `reference_mode === "manual"` | Manual |
| `nominal_voltage_ll_kv != null` and `reference_mode === "auto"` | Auto-resolved |

With `base_authority` on the wire, this collapses to a direct enum→string map.

---

**Improved PU eligibility pill mapping:**

| Backend value | Current UI | Proposed label |
|---|---|---|
| `configured` | "Eligible" (green) | "Eligible" (green) — no change |
| `base_required` / `reason="manual_conflict_detected"` or `manual_conflict_detected` flag | "Blocked — conflict" (amber) | "Blocked — base conflict" (amber) |
| `base_required` / `reason="base_invalidated"` and no nominal kV | "Base invalidated" (grey) | "Auto-resolution incomplete" (grey) |
| `base_required` / `reason="base_invalidated"` and nominal kV present | "Base invalidated" (grey) | "Base invalidated — reconfigure" (grey) |
| `base_required` / `reason="voltage_base_not_configured"` | "No base configured" (grey) | "Nominal voltage not configured" (grey) |
| `base_required` / `reason="group_not_confirmed"` | "Group not confirmed" (grey) | "Group pending confirmation" (grey) |
| `base_required` / `reason="voltage_reference_undetermined"` | "Reference undetermined" (grey) | "Voltage reference undetermined" (grey) |
| `base_required` / `reason="secondary_equivalent_not_configured"` | "Secondary equivalent required" (grey) | "Secondary equivalent not configured" (grey) |
| Catch-all | "Not eligible" (grey) | "PU not available" (grey) |

**To fully separate "insufficient evidence" from "genuinely invalidated"** without
exposing the full `base_authority` field, the minimum backend change is to split
the single `"base_invalidated"` reason:

```python
# In resolve_voltage_base_for_group(), line 276:
reason = (
    "evidence_insufficient"       # needs_review: auto-resolution ran, couldn't resolve
    if config.base_authority == "needs_review"
    else "base_unavailable"       # unavailable: was auto_resolved, then contradicted
)
```

This is a one-line change to `voltage_group_config.py`. It enables the frontend to
display "Auto-resolution incomplete" vs "Base was invalidated — reconfigure" without
the full `base_authority` field.

---

### Current group

**Main view (always visible):**
```
Effective I base:   [resolved_ibase_ka kA]  or  "—"
Configuration:      [method label: Equipment rating / Manual / None]
PU availability:    [pill]
```

**Expandable Engineering Evidence:**
- Equipment rating MVA (when method = equipment_rating)
- Applicable V base (resolved or manual)
- Linked voltage group (name, not raw ID — Slice D should fetch the name)
- Manual V base (when no linked group)
- Reference side

---

## 5. API Gaps

### Gap 1 — `base_authority` not on wire schema (pre-existing, documented)

`VoltageBaseConfiguration.base_authority` (domain type `BaseAuthorityState`) is not
serialized to `VoltageGroupConfigOut`. The wire schema has no `base_authority` field.

**Impact:**
- Frontend cannot show "Auto-resolved" vs "Manual" vs "Needs review" vs "Legacy
  manual" labels without inference from other fields
- `"base_invalidated"` reason conflates two distinct states
- Slice D "Revert to auto" button cannot be conditionally shown based on actual
  authority

**Minimum fix:** Add `base_authority: str` to `VoltageGroupConfigOut`, populated
from `config.base_authority if config is not None else "unavailable"`. Additive,
backward-compatible. No existing consumers break.

**Alternative minimum fix (smaller scope):** Split the `"base_invalidated"` reason
string in `resolve_voltage_base_for_group()` as described above. Addresses the
most user-visible label defect without a schema change.

### Gap 2 — No "revert base to automatic" API endpoint

`return_voltage_reference_to_auto()` exists as a service function (clears reference
override only). There is no way for the engineer to clear a manual nominal kV and
trigger re-detection through the current API. The PUT endpoint requires a valid
`nominal_voltage_ll_kv` to change the base; passing `null` preserves the existing
value.

**Impact for Slice D:** "Revert to auto" (remove manual kV, re-run auto-detection)
is not currently expressible through the API. Slice D will need either:
- A new endpoint (`DELETE .../voltage-config/base` or `POST .../voltage-config/revert`)
- Or a new field on the existing PUT (`"clear_nominal": true`) that explicitly
  sets `nominal_voltage_ll_kv = None` and triggers `run_auto_base_for_source()` for
  the group

### Gap 3 — `base_authority` absent from `CurrentGroupConfigOut` too

By the same reasoning, the current-base equivalent is also not exposed. Lower
priority since current-base auto-detection does not exist (all current groups
require manual configuration).

---

## 6. Slice C Correction Recommendations

These corrections can be made to `frontend/index.html` only, without backend
changes, using the information available from the existing wire schema:

**C1. Fix "Base invalidated" label** — the most important correction:

Distinguish the BEN "insufficient evidence" case from a genuine invalidation using
the available `nominal_voltage_ll_kv` field as a proxy (imperfect but better than
the current label). The `pu_reason` check can further refine the display:

```js
if (reason === "base_invalidated") {
    if (vc && vc.nominal_voltage_ll_kv != null) {
        return '<span ...>Base invalidated — reconfigure</span>';
    }
    return '<span ...>Auto-resolution incomplete — configure manually</span>';
}
```

This covers the BEN case (null nominal = auto ran and got needs_review) and the
genuinely invalidated case (non-null nominal = was once auto_resolved, now
unavailable).

**C2. Fix "Not configured" authority label** when `pu_reason === "base_invalidated"`:

```js
if (pu_reason === "base_invalidated") {
    authorityLabel = vc && vc.nominal_voltage_ll_kv != null
        ? "Auto-resolved (invalidated)"
        : "Evidence insufficient — configure manually";
}
```

**C3. Replace "Configured" fallback** (the else branch) with "Auto-resolved" when
`nominal_voltage_ll_kv != null`, `reference_mode === "auto"`, and no conflict:

```js
authorityLabel = "Auto-resolved";
```

**C4. Consider suppressing the CT/VT section** (or labeling it "Not available from
recording metadata") rather than "Not configured" — "Not configured" implies the
engineer should configure it, but CT/VT configuration is out of Slice scope.

---

## 7. Slice D Readiness Assessment

| Operation | Backend status | Action needed |
|---|---|---|
| Set manual voltage base (kV) | **Ready** — `PUT .../voltage-config` with `nominal_voltage_ll_kv` | None |
| Set voltage reference (auto/manual) | **Ready** — same PUT, `reference_mode + reference_override` | None |
| Revert reference to auto | **Ready** — `PUT` with `reference_mode="auto"` clears override | None |
| Revert **base** to automatic | **Not supported** — no API path to clear manual kV and re-trigger detection | New endpoint or PUT extension needed |
| Set manual current base (kA) | **Ready** — `PUT .../current-config` with `method="manual"` | None |
| Apply/Cancel semantics | **No backend transaction** — edits apply immediately | Slice D must implement Cancel as UI-only rollback using cached state |
| PU eligibility refresh after edit | **Ready** — PUT response returns updated `MeasurementGroupOut` with new `pu_status`/`pu_reason` | Slice D frontend must: re-render Group Details panel; re-render group list row; increment `wwErState.perUnit.generation` to invalidate PU display |
| Conflict detection | **Ready** — RD-0B: conflict flag is re-evaluated by `reconfigure_auto_base_after_membership_change()` on each PUT with new kV | None — PUT response already includes `manual_conflict_detected` |
| `base_authority` on wire | **Not supported** — not in `VoltageGroupConfigOut` | Additive: add `base_authority: str` to schema; enables "Revert to auto" conditional display and precise authority labels |

**Recommended pre-Slice D backend additions (small, low-risk):**

1. Add `base_authority: str` to `VoltageGroupConfigOut`. One-line schema change.
   Unlocks precise labels, conditional "Revert to auto" button, and separates
   `needs_review` from `unavailable` in the UI.
   
2. Split `reason="base_invalidated"` into `"evidence_insufficient"` and
   `"base_unavailable"` in `resolve_voltage_base_for_group()`. One-line logic change.
   Enables actionable UI copy without full schema change.

3. Define the "revert base to auto" API contract (endpoint or PUT extension) before
   Slice D begins, to avoid mid-slice scope creep.

---

## 8. Slice C-2 Completion Summary (2026-11-18)

**All items above are now resolved.** The following changes were implemented and merged
into commit `06db556` on branch `feature/vlt-ref-001-voltage-reference-safety`:

### Completed

| Item | Resolution |
|---|---|
| Gap 1 — `base_authority` not on wire schema | Added `base_authority: str` to `VoltageGroupConfigOut` and `CurrentGroupConfigOut` (default `"legacy_manual"`); wired through view service and API layer. Commit `933beaa`. |
| "Base invalidated" conflates two states | Frontend now branches on `base_authority` within the `base_invalidated` reason: `needs_review` → "Nominal voltage not resolved — manual configuration required" (or "Review required before PU is available" when kV is set); `unavailable` → "Base invalidated — reconfigure". |
| Authority inference from `reference_mode` | Replaced with direct `vc.base_authority` lookup. No inference needed. |
| CT/VT "Not configured" misleading label | Changed to "Not available from recording metadata". |
| Voltage main view — secondary fields in main view | `base_reference_side` and `secondary_voltage_ll_v` moved to Engineering Evidence. Main view: 4 rows only. |
| Current main view — method/MVA/linked group in main view | Moved to Engineering Evidence. Main view: 3 rows — Current base, Configuration, PU availability. |
| `ww-rd-pu-needs-review` CSS class | Added for the amber review-required PU pill state. |
| Backend test coverage | 14 tests in `test_slice_c2_base_authority.py` — all pass. Commit `933beaa`. |
| Browser test coverage | 10 tests in `browser-tests/rd1-slice-c2.spec.js` — all pass. 52/52 RD-1 tests pass. Commit `06db556`. |

### Remaining for Slice D

| Item | Status |
|---|---|
| Gap 2 — "Revert base to auto" API endpoint | Still not supported. Define contract before Slice D begins. |
| Linked voltage group display name | Still raw ID. Slice D should resolve name via group list. |
| Apply/Cancel editing workflow | Not implemented. Slice D scope. |
| PU display refresh on group edit | Not implemented. Slice D scope (increment `wwErState.perUnit.generation`). |
