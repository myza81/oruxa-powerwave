# Stage 3B-2B: Calculated Channel Calibration Safeguards — Architecture Assessment

**Date:** 2026-11-12  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Scope:** Assessment only. No production code modified. No commits.  
**Governance:** DEC-213. Stage 3B-2A gate (`06f6d3e`) must be preserved unchanged.

---

## 1. Current Architecture Overview

### Key files

| File | Role |
|------|------|
| `backend/app/services/calculated_channel_service.py` | Orchestration: validation, evaluation, display/measurement pipelines |
| `backend/app/domain/calculated_channel.py` | Domain model: `CalculatedChannel`, `ChannelRef`, evaluators |
| `backend/app/services/calculated_channel_registry.py` | In-memory per-workspace channel store |
| `backend/app/services/calculated_group_aware_per_unit.py` | Group-aware PU resolution for calculated channels |
| `backend/app/api/v1/calculated_channels.py` | Router: HTTP endpoints |
| `backend/app/schemas/calculated_channel.py` | Pydantic wire shapes |

### How calculated channels are defined and stored

A `CalculatedChannel` (domain model, `calculated_channel.py` lines 268–354) is an **immutable-after-creation** record carrying:
- `id`, `workspace_id`, `name`, `unit`, `operation`, `inputs: list[ChannelRef]`
- `time: np.ndarray`, `values: np.ndarray` — full-resolution arrays evaluated **eagerly** at creation time
- `reference_source_id: str` — the upstream source's `source_id`, inherited transitively through calculated-on-calculated chains; used for removal cascades, **not** for calibration
- `dependency_ids: list[str]` — direct calculated-channel dependencies only (never transitive)
- `engineering_type`, `waveform_form`, `voltage_representation`, `phase_member`

**No `calibration_authority` field.** `CalculatedChannel` has no calibration metadata of any kind.

A `ChannelRef` (domain model, `calculated_channel.py` lines 244–265) is a typed reference with two variants:
- `kind="source"` — `source_id` + `channel_name`: references a live recording's `AnalogChannel`
- `kind="calculated"` — `calculated_channel_id`: references another `CalculatedChannel`

### How calculated channels reference source channels

`create_calculated_channel()` calls `_resolve_input()` (service, lines 343–407) for each `ChannelRef`. For a `source`-kind ref, `_resolve_input()`:
1. Calls `source_registry.get(workspace_id, ref.source_id)` → `ActiveSource`
2. Reads `AnalogChannelSummary.engineering_type` and `.waveform_form` from `active.metadata.analog_channels` (line 366–370)
3. Reads raw sample data from `active.record.waveform_data` (line 371–373)
4. Returns a `_ResolvedInput` with `time`, `values`, `unit`, `engineering_type`, `waveform_form`

**`_resolve_input()` never reads `AnalogChannel.calibration_authority`.**  
The authority lives in `active.record.analog_channels[i].calibration_authority` (the `DisturbanceRecord`, not the `SourceMetadata`). It is accessible from `ActiveSource` but `_resolve_input()` does not touch it.

### PU resolution path for calculated channels

The calculated-channel PU dispatch point is `_resolve_effective_per_unit_for_calculated_channel()` (service, lines 1399–1472). This mirrors `waveform_service._resolve_effective_per_unit()` for source channels, but **does not contain the Stage 3B-2A calibration gate**.

Call chain for PU output on a calculated channel:

```
extract_calculated_waveform_range()     line 1490   (waveform)
extract_calculated_cursor_values()      line 1554   (cursor)
resolve_calculated_peak_value()         line 1629   (peak)
resolve_calculated_annotation_anchor()  line 1693   (annotation)
  └─ _resolve_effective_per_unit_for_calculated_channel()   line 1399
       ├─ resolve_calculated_current_per_unit()   [Current path]
       ├─ undetermined_representation_resolution()  [L-L Voltage guard]
       ├─ resolve_calculated_group_aware_per_unit()  [group path]
       └─ resolve_per_unit()   [DEC-049 fallback]
```

There is **no calibration gate anywhere in this chain**.

---

## 2. Dependency-Flow Diagram

```
Physical layer (providers)
─────────────────────────
  BEN5K recording                    COMTRADE recording
  ┌──────────────────┐               ┌──────────────────┐
  │ AnalogChannel VA │               │ AnalogChannel IA │
  │  .calibration_   │               │  .calibration_   │
  │   authority=     │               │   authority=None │
  │   {unverified}   │               │   (not assessed) │
  └────────┬─────────┘               └───────┬──────────┘
           │  active.record.analog_channels  │
           │  [DisturbanceRecord level]       │
           │                                  │
Metadata layer (SourceMetadata / AnalogChannelSummary)
─────────────────────────────────────────────────────
  AnalogChannelSummary                AnalogChannelSummary
    .calibration_status="unverified"    .calibration_status=None
    .calibration_reason=…               .calibration_reason=None
    [strings only — authority object    [authority object NOT here]
     NOT here]
           │                                  │
           ▼                                  ▼
_resolve_input()   ← ← ← ← ← ← ← ← ← ← ← ─┘
  reads engineering_type, waveform_form
  reads waveform_data (sample values)
  does NOT read calibration_authority          ← AUTHORITY LOST HERE
           │
           ▼
_ResolvedInput(time, values, unit, engineering_type, waveform_form)
  no calibration field
           │
           ▼
create_calculated_channel() → CalculatedChannel
  .calibration_authority = [field does not exist]  ← AUTHORITY ABSENT
  .reference_source_id = BEN5K source_id
           │
           ▼
_resolve_effective_per_unit_for_calculated_channel()
  no calibration gate                          ← BYPASS POINT
           │
           ▼
 PU output: "configured" or "base_required"   ← WRONG — should be
                                                "calibration_unavailable"
```

**Gate locations (Stage 3B-2A, source channels only):**

```
waveform_service._resolve_effective_per_unit()   line 183
  ├─ _calibration_blocked_reason()               line 102
  │    reads active.record.analog_channels       ← gate exists here
  │    reads active.record.metadata.format_variant
  └─ returns STATUS_CALIBRATION_UNAVAILABLE if blocked
```

The gate exists only for source-channel PU resolution. Calculated channels bypass it entirely.

---

## 3. Potential Calibration-Authority Bypasses

### A. BEN5K Voltage → calculated Voltage → PU

**Bypass possible: YES**

`VA` (BEN5K, unverified) is used as input to `reverse_polarity(-VA)` or `addition(VA, VA2)`. The result goes through `_resolve_effective_per_unit_for_calculated_channel()` with no gate. If a base is configured, PU succeeds with `status="configured"`.

Evidence: `_resolve_effective_per_unit_for_calculated_channel()` lines 1399–1472 — no calibration check.

**Severity: HIGH** — PU values derived from unverified amplitudes presented as authoritative.

---

### B. BEN5K Current → calculated RMS Current → PU

**Bypass possible: YES**

`IA` (BEN5K, unverified) → `rms("IA")` via `create_calculated_channel()` with `operation=OP_RMS`. The resulting RMS channel goes through the calculated-channel PU path with no gate. PU proceeds if a base is configured.

**Severity: HIGH** — an RMS magnitude from unverified current in PU is physically meaningless but displayable.

---

### C. BEN5K Current → Calculated A → Calculated B → PU

**Bypass possible: YES**

Each intermediate step calls `_resolve_input()` which drops `calibration_authority`. The final `CalculatedChannel` has `reference_source_id` pointing to the BEN5K source, but the PU gate checks neither that field nor any input graph.

**Severity: HIGH** — arbitrarily deep chains fully bypass the gate.

---

### D. BEN5K + COMTRADE inputs → calculated result

**Bypass possible: YES**

If `IA_BEN5K` and `IB_COMTRADE` are combined via `addition(IA_BEN5K, IB_COMTRADE)`, the result carries no calibration restriction. `_resolve_effective_per_unit_for_calculated_channel()` runs for the output channel without any gate.

**Severity: HIGH** — BEN5K restriction must propagate to any calculation that includes a BEN5K leaf.

---

### E. Verified + Not Assessed inputs

**Bypass possible: NO (but needs explicit documentation)**

Currently no source channel carries `status="verified"` — only BEN5K channels carry `status="unverified"`. COMTRADE channels have `calibration_authority=None` (not assessed). The evaluator treats `None` authorities as `not_assessed`, which is `eligible=True` with reason `not_assessed`.

The existing `evaluate_calibration_eligibility()` correctly handles mixed Verified + Not Assessed: `all_verified=False`, `eligible=True`, `reason=not_fully_verified`. This is the correct policy (compatible mode, never claimed as fully verified). No code change needed for this scenario today, but the propagation logic must enforce it going forward.

---

### F. Invalid + Verified inputs

**Bypass possible: YES (hypothetically)**

No source currently has `status="invalid"`, but if one did and was used as a calculated-channel input, the gate would not fire because calculated channels have no gate. Invalid dominates all others in `evaluate_calibration_eligibility()`, so the propagation logic would correctly block the result — but only once the gate is in place.

---

### G. Missing original channel or stale source reference

**Bypass possible: NO (by existing code)**

`calculated_timing_service.get_calculated_result()` validates that all upstream sources are still present. `remove_calculated_channels_for_source()` cascades deletions (service, lines 1363–1389) using `reference_source_id`. A stale source reference causes the calculated result to be invalidated before PU is even resolved.

---

### H. User changes Measurement Group or manually assigns calculated-result PU base

**Bypass possible: YES**

Assigning a PU base to a calculated channel (via `per_unit_registry`) does not trigger a calibration check. The PU path would use that base and return `status="configured"`. The calibration gate must be checked **before** the base resolution path, same pattern as Stage 3B-2A's placement in `_resolve_effective_per_unit()` (line 183–189, before the group-aware and legacy DEC-049 paths).

---

### I. Source removal/reimport changes available dependency provenance

**Bypass possible: NO (by existing code)**

Removal cascades via `reference_source_id`. Reimport creates a new `source_id` and all previous calculated channels are invalidated. The new source's channels carry fresh `calibration_authority` objects.

---

### J. Two calculated channels with identical numeric values but different source calibration authority

**Bypass possible: YES**

If `CalcA` derives from BEN5K and `CalcB` from COMTRADE, they may have identical sample values but different calibration status. Currently both go through the same unchecked PU path. The gate must per-channel-leaf resolve the authority — the values themselves are irrelevant to the gate.

---

### K. Multi-source time alignment remains correct

**Not a bypass risk.** `timebases_aligned()` already enforces absolute-instant proof for multi-source inputs. This is independent of calibration. Stage 3B-2B does not need to touch time alignment.

---

### L. Existing COMTRADE/CSV calculated-channel workflows remain numerically unchanged

**Preserved by design.** COMTRADE/CSV channels have `calibration_authority=None` (not assessed). `evaluate_calibration_eligibility([None-or-absent])` returns `eligible=True` with `reason=not_assessed`. The gate must pass `None` authorities through as not-assessed, never blocking them. This is the backward-compatibility requirement.

---

## 4. Recommended Eligibility Propagation Design

### Principle

The gate belongs in `_resolve_effective_per_unit_for_calculated_channel()` as the **first check**, mirroring Stage 3B-2A's placement in `_resolve_effective_per_unit()`. It must run before the CURRENT path, before the voltage-representation guard, and before the group-aware / DEC-049 paths.

### Leaf-authority traversal

A new helper function in `calculated_channel_service.py`:

```python
def _collect_leaf_calibration_authorities(
    channel: CalculatedChannel,
    *,
    workspace_id: str,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
    _visited: set[str] | None = None,
) -> list["PhysicalCalibrationAuthority | None"]:
    """Return the flat list of PhysicalCalibrationAuthority objects
    (or None for not-assessed channels) from all original source-channel
    leaves in this channel's full dependency tree.

    Fail-closed for BEN5K sources: if a source ChannelRef resolves to a
    BEN5K source (format_variant == FORMAT_VARIANT_BEN5K_LEGACY) but the
    AnalogChannel or its authority is absent, treat the authority as an
    explicit PhysicalCalibrationAuthority(status=CALIBRATION_UNVERIFIED,
    reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED, ...) rather than
    None/not-assessed.

    Already-visited calculated channel ids are skipped (the creation-time
    would_create_cycle() guard makes real cycles impossible, but _visited
    guards against any future mutation path; also eliminates redundant
    traversal when multiple calc channels share an ancestor).
    """
```

**Traversal:**
- For each `ref` in `channel.inputs`:
  - If `ref.kind == "source"`: get `active = source_registry.get(workspace_id, ref.source_id)`, then `full_ch = next((ch for ch in active.record.analog_channels if ch.name == ref.channel_name), None)`. Check `active.record.metadata.format_variant`. Collect `full_ch.calibration_authority` (or the defensive BEN5K sentinel).
  - If `ref.kind == "calculated"`: recurse into the referenced `CalculatedChannel.inputs` via the same function.

**What to do when source or channel is not found:**
- Source not found: collect a synthetic `PhysicalCalibrationAuthority(status=CALIBRATION_UNVERIFIED, reason="source_unavailable", transform_id="unknown")`. This fails closed — a missing source is as unknown as an unverified one, and the cascade guard should have already removed the channel.
- Channel name not found in `analog_channels`: check `format_variant`; fail closed for BEN5K, `None` (not-assessed) for others.

**Why not cache on `CalculatedChannel`?**  
Calibration authority is on the `DisturbanceRecord`, which lives in the `WorkspaceRegistry`. The registry is in-memory and ephemeral; sources can be re-imported with new authority objects. Caching authority on the `CalculatedChannel` dataclass would require invalidation logic that does not exist and is not needed. Per-request traversal is O(depth × channels), which is small for typical calculated-channel trees.

### Gate injection point

```python
def _resolve_effective_per_unit_for_calculated_channel(
    channel: CalculatedChannel,
    per_unit_profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str] | None,
    *,
    workspace_id: str | None = None,
    calc_registry: CalculatedChannelRegistry | None = None,
    source_registry: WorkspaceRegistry | None = None,
    ...
):
    # Stage 3B-2B calibration authority gate — FIRST CHECK
    if workspace_id is not None and source_registry is not None and calc_registry is not None:
        authorities = _collect_leaf_calibration_authorities(
            channel, workspace_id=workspace_id,
            source_registry=source_registry, calc_registry=calc_registry,
        )
        eligibility = evaluate_calibration_eligibility(
            [a for a in authorities if a is not None],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        if not eligibility.eligible:
            return PerUnitResolution(
                status=STATUS_CALIBRATION_UNAVAILABLE,
                profile_id=None, base_amount=None, base_unit=None,
                reason=eligibility.reason,
            )
    # ... existing CURRENT path, voltage-representation guard, group-aware, DEC-049 ...
```

**When `source_registry` or `calc_registry` are `None`** (legacy callers that omit them): gate is skipped, preserving exact existing behaviour. This is the same opt-in pattern used for the group-aware paths.

**All-not-assessed inputs** (pure COMTRADE/CSV calculated channels): `evaluate_calibration_eligibility([], ...)` with an empty list (all authorities were `None`, filtered out) returns `eligible=True, reason=not_assessed`. Gate passes, existing behaviour preserved.

---

## 5. Exploratory vs Authoritative Operations

### Current state

The code does **not** distinguish exploratory from authoritative at the operation level. All operations go through the same PU path.

### Operation classification

| Operation | Classification | Rationale |
|-----------|---------------|-----------|
| `reverse_polarity` | Exploratory | Sign inversion, shape unchanged |
| `absolute_value` | Exploratory | Magnitude inspection |
| `multiply_constant` | Exploratory | Scaling for display, unit-equivalent |
| `addition`, `subtraction` | Exploratory or Authoritative | Depends on use: waveform arithmetic is exploratory; a computed quantity presented in PU may be authoritative |
| `rms` | Authoritative | A PU-normalised RMS value is used for compliance and engineering decisions |
| `rocof` | Exploratory | Hz/s rate; not a voltage/current quantity; PU is `not_applicable` by `engineering_type` |
| `active_power`, `reactive_power`, `apparent_power` | Authoritative | Presented as physically valid power results |
| `three_phase_*` variants | Authoritative | Same as single-phase power |

### Key finding

PU output on a calculated channel is by definition **authoritative** — the frontend displays it as a per-unit value normalized against a physical base. The only distinction that matters for Stage 3B-2B is:

- **ENG mode** (engineering-unit display): numerically unchanged, calibration limitation does NOT block it. The gate fires only in PU mode.
- **PU mode**: if any leaf has an unverified/invalid calibration authority, PU output is blocked and returns `calibration_unavailable`. Engineering values remain unchanged.

The existing code already implements this split correctly for source channels (Stage 3B-2A). Stage 3B-2B extends the same logic to calculated channels.

### Minimum contract change

No new API field or operation-level classification is required. The existing `per_unit_status` field on `CalculatedWaveformRangeResult`, `CalculatedCursorValues`, `CalculatedPeakResult`, and `CalculatedAnnotationAnchorResult` (all in `calculated_channel_service.py`) already carries the status string. The existing schema fields `CalculatedWaveformRangeOut.per_unit_status` etc. already serialise it. The value `"calibration_unavailable"` is a new possible value for those fields — no schema change needed.

---

## 6. Proposed API and Status Behaviour

### Where `calibration_unavailable` surfaces for calculated channels

It surfaces identically to source channels:
- `CalculatedWaveformRangeResult.per_unit_status = "calibration_unavailable"` (line 1486)
- `CalculatedCursorValues.per_unit_status = "calibration_unavailable"` (line 1550)
- `CalculatedPeakResult.per_unit_status = "calibration_unavailable"` (line 1625)
- `CalculatedAnnotationAnchorResult.per_unit_status = "calibration_unavailable"` (line 1689)

All four result dataclasses already have `per_unit_status: str | None = None`. No new fields.

### Schema changes required

**None for calculated-channel display endpoints.** The `per_unit_status` field already exists in the wire shapes (`CalculatedWaveformRangeOut`, `CalculatedCursorValuesItemOut`, etc.) and is already serialised as a nullable string. The new value `"calibration_unavailable"` is handled by the existing string pass-through.

### Frontend panel grouping

The frontend routes `perUnitStatus == "calibration_unavailable"` to the "unavailable" branch (this was established by Stage 3B-2A for source channels). Calculated channels go through the same frontend waveform/panel logic. No new frontend path is needed — the existing branch already handles it correctly, as verified by the Stage 3B-2A browser tests.

**One edge case to verify:** if a workspace has both a source channel (BEN5K, `calibration_unavailable`) and a calculated channel derived from it (also `calibration_unavailable`), both should appear on the same non-`:pu` panel. This is already the case because panel grouping is driven by `perUnitStatus`, not by channel type.

---

## 7. Performance Implications

### How often is dependency resolution called?

`_resolve_effective_per_unit_for_calculated_channel()` is called once per calculated channel per display request (waveform, cursor, peak, annotation). For a workspace with N calculated channels all displayed simultaneously, it is called N times per request.

### Traversal cost

The `_collect_leaf_calibration_authorities()` traversal walks the dependency tree once per call. For a chain of depth D with branching factor B, the traversal is O(B^D) in the worst case. In practice:
- Depth is typically 1–3 (source → calc → calc).
- Branching factor is 1 for unary operations (reverse polarity, RMS, absolute value) and 2–6 for multi-input operations (addition, subtraction, power).
- The `_visited` set prevents redundant traversal of shared ancestors.

A typical calculated-channel tree has 2–10 total nodes. Traversal cost is negligible compared to the array operations already performed during waveform display.

### Registry lookups

Each source-kind leaf requires one `source_registry.get()` call and one linear scan of `active.record.analog_channels`. Both are O(1) hash lookup + O(C) scan (C = analog channel count per recording, typically 10–60). No new I/O.

### Recommendation

Resolve the leaf authorities **once per request** at the top of `_resolve_effective_per_unit_for_calculated_channel()`. Do NOT cache on the `CalculatedChannel` object (the authority may change on reimport). No per-sample computation is needed — the gate fires at the PU dispatch layer, never inside the numeric evaluators.

---

## 8. Frontend Compatibility Implications

### Does the frontend already handle `calibration_unavailable` on calculated channels?

The frontend's `calibration_unavailable` handling was implemented for source channels in Stage 3B-2A. The calculated-channel display endpoints return the same `perUnitStatus` field via the same JSON structure. The frontend does not distinguish source from calculated channels in its PU status routing — it reads `perUnitStatus` on the channel object regardless of type.

**Conclusion:** The existing frontend branch for `calibration_unavailable` already handles calculated channels correctly, as long as the backend returns the status. No frontend code change is required.

### Edge cases

1. **Mixed workspace (BEN5K source + derived calc + unrelated COMTRADE calc):** The COMTRADE-derived calc returns its own `perUnitStatus` normally; the BEN5K-derived calc returns `calibration_unavailable`. Both are displayed correctly — panel grouping is per-channel.

2. **PULU regression:** The earlier PULU mixed-unit defect (DEC-050) was caused by incorrect panel regrouping on PU mode switch. The Stage 3B-2B gate fires at the PU resolution layer, before panel assignment. The existing PULU post-fetch regrouping is unaffected — a channel with `calibration_unavailable` simply never enters a `:pu` panel.

3. **Cursor units for calculated channels in ENG mode:** Unaffected. The gate fires only in `unit_mode == UNIT_MODE_PER_UNIT`. ENG mode cursor values are served from the raw `channel.values` array.

---

## 9. Proposed Implementation Slices (File Inventory)

### Slice 3B-2B-1 — Leaf authority traversal helper (new function)

**File:** `backend/app/services/calculated_channel_service.py`  
**Change:** Add `_collect_leaf_calibration_authorities()` helper function (~30 lines)  
**New imports needed:**
- `from app.domain.physical_calibration import (PhysicalCalibrationAuthority, CALIBRATION_UNVERIFIED, evaluate_calibration_eligibility, PURPOSE_ENGINEERING_CALCULATION)`
- `from app.domain.metadata import FORMAT_VARIANT_BEN5K_LEGACY`
- `from app.domain.physical_calibration import REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED`
- `from app.domain.per_unit import STATUS_CALIBRATION_UNAVAILABLE`

**Dependencies:** None (pure addition)

---

### Slice 3B-2B-2 — Gate injection in PU dispatch function

**File:** `backend/app/services/calculated_channel_service.py`  
**Change:** Inject gate at the top of `_resolve_effective_per_unit_for_calculated_channel()` (lines 1399–1472), approximately 10 new lines  
**Location:** After the function signature and docstring, before the CURRENT path check at line 1426  
**Dependencies:** Slice 3B-2B-1 must be in place first

---

### Slice 3B-2B-3 — Backend tests (new file)

**File:** `backend/tests/test_ben5k_calculated_channel_pu_gate.py` (new, ~50–70 tests)  
**Coverage:**
- Leaf traversal: source leaf → authority collected
- Leaf traversal: calc-on-source leaf → authority propagated
- Leaf traversal: calc-on-calc-on-source → authority propagated (depth 3)
- Leaf traversal: mixed BEN5K + COMTRADE → BEN5K authority propagates
- Leaf traversal: missing channel on BEN5K → defensive sentinel returned
- Gate: `calibration_unavailable` returned for all 4 entry points (waveform, cursor, peak, annotation)
- Gate: COMTRADE-only calc channel → not blocked (backward compat)
- Gate: Verified + Not Assessed → not blocked, `all_verified=False`
- Gate: `source_registry=None` → gate skipped (legacy caller compat)
- All bypass scenarios A–L (see Section 10)

**Dependencies:** Slices 3B-2B-1 and 3B-2B-2

---

### Slice 3B-2B-4 — Browser regression spec (new file)

**File:** `browser-tests/ben5k-calculated-channel-pu-gate.spec.js` (new, ~3 tests)  
**Coverage:**
- BEN5K source → calculated reverse polarity → PU mode → `calibration_unavailable`, unit unchanged
- BEN5K source → calculated RMS → PU mode → `calibration_unavailable`
- COMTRADE source → calculated channel → PU mode → normal PU behaviour preserved

**Dependencies:** Slices 3B-2B-1–3

---

### No changes to:
- `backend/app/domain/calculated_channel.py` (no new fields needed)
- `backend/app/schemas/calculated_channel.py` (no new schema fields needed)
- `backend/app/api/v1/calculated_channels.py` (router passes `source_registry` already)
- `backend/app/domain/physical_calibration.py` (Stage 3A evaluator is reused unchanged)
- Any provider, frontend, or deployment code

---

## 10. Detailed Regression Plan

### A. BEN5K Voltage → calculated Voltage → PU

**Setup:** Create COMTRADE-like fixture with BEN5K format_variant set. Create `reverse_polarity(-VA)`. Call `extract_calculated_waveform_range()` in PU mode.  
**Expected:** `per_unit_status == "calibration_unavailable"`, unit unchanged.  
**Closest existing test:** `test_ben5k_pu_calibration_gate.py::TestWaveformIntegration`

---

### B. BEN5K Current → calculated RMS Current → PU

**Setup:** BEN5K source with Current channel. Create `rms("IA", 50.0)`. Call waveform in PU mode.  
**Expected:** `per_unit_status == "calibration_unavailable"`.  
**Closest existing test:** `test_calculated_channel_service.py::TestRmsCalculation`

---

### C. BEN5K Current → Calculated A → Calculated B → PU (depth 3)

**Setup:** `CalcA = absolute_value("IA_BEN5K")`. `CalcB = reverse_polarity(CalcA)`. PU on CalcB.  
**Expected:** `per_unit_status == "calibration_unavailable"` (traversal reaches BEN5K leaf through 2 hops).  
**Closest existing test:** No existing depth-3 test; new test needed.

---

### D. BEN5K + COMTRADE inputs → calculated result

**Setup:** `addition("VA_BEN5K", "VA_COMTRADE")` with proven-aligned timebases. PU mode.  
**Expected:** `calibration_unavailable` — BEN5K leaf propagates to the result.  
**Closest existing test:** `test_calculated_channel_service.py::TestAddition`

---

### E. Verified + Not Assessed inputs

**Setup:** One source with `calibration_authority.status="verified"`, one with `calibration_authority=None`. Combined calc. PU mode.  
**Expected:** Gate passes (`eligible=True`), `all_verified=False`. Normal PU resolution proceeds.  
**Closest existing test:** `test_physical_calibration.py::TestEligibilityEvaluator`

---

### F. Invalid + Verified inputs (hypothetical)

**Setup:** Source with `calibration_authority.status="invalid"`. Calculated channel. PU mode.  
**Expected:** `calibration_unavailable` — invalid dominates.  
**Closest existing test:** `test_physical_calibration.py::TestInvalidDominance`

---

### G. Missing original channel or stale source reference

**Setup:** Create calc channel. Remove source from registry (bypass the cascade guard in a test). Call PU.  
**Expected:** Source not found → `blocked_reason="source_unavailable"` (OD-3: no fabricated authority) → `calibration_unavailable`.  
**Closest existing test:** `test_calculated_timing_authority.py` (source removal tests); `test_ben5k_calculated_channel_pu_gate.py::test_source_unavailable_blocks` (OD-3 unit test, Stage 3B-2B-1)

**Amendment (Stage 3B-2B-1 / OD-3):** The original assessment proposed a synthetic `PhysicalCalibrationAuthority(status=CALIBRATION_UNVERIFIED, reason="source_unavailable", ...)` as the fail-closed mechanism. Owner decision OD-3 explicitly prohibits fabricated authority objects. The implementation uses a machine-readable `blocked_reason` string on `_LeafAuthorityResult` instead — `_collect_leaf_authorities()` returns `blocked_reason="source_unavailable"` and the gate maps this directly to `STATUS_CALIBRATION_UNAVAILABLE` without constructing a synthetic authority. The observable result (`calibration_unavailable`) is identical.

---

### H. User changes Measurement Group or manually assigns calculated-result PU base

**Setup:** BEN5K calculated channel. Assign PU base manually. Call PU.  
**Expected:** Gate fires BEFORE base resolution → `calibration_unavailable` returned; the base assignment is ignored for PU output.  
**Closest existing test:** `test_calculated_group_aware_per_unit.py`

---

### I. Source removal/reimport changes available dependency provenance

**Setup:** Create BEN5K calc channel. Remove source. Assert cascade removed the calc channel.  
**Expected:** Existing cascade behaviour preserved; no regression.  
**Closest existing test:** `test_calculated_channel_service.py::TestRemoveCalculatedChannelsForSource`

---

### J. Two calculated channels with identical numeric values but different source calibration authority

**Setup:** `CalcBEN5K = reverse_polarity("VA_BEN5K")`, `CalcCOMTRADE = reverse_polarity("VA_COMTRADE")`. Same values. PU on both.  
**Expected:** `CalcBEN5K → calibration_unavailable`, `CalcCOMTRADE → configured/base_required`.  
**Closest existing test:** No existing test; new test needed.

---

### K. Multi-source time alignment remains correct

**Setup:** Existing multi-source alignment tests.  
**Expected:** Unaffected. No regression.  
**Closest existing test:** `test_calculated_channel_service.py::TestTimebases`

---

### L. Existing COMTRADE/CSV calculated-channel workflows remain numerically unchanged

**Setup:** All existing `test_calculated_channel_service.py` and `test_calculated_channel_api.py` tests.  
**Expected:** All pass unchanged — COMTRADE-only chains have `all authority = None`, gate passes.  
**Closest existing test:** Entire existing calculated-channel test suite (9 test files, ~hundreds of tests).

---

## 11. Open Decisions Requiring Owner Approval

### OD-1: Gate behaviour when `source_registry` is `None` (legacy callers)

**Question:** When `_resolve_effective_per_unit_for_calculated_channel()` is called without `source_registry` (legacy/test callers that omit the registry), should the gate be:
- **Option A:** Skipped entirely (preserve existing behaviour, `eligible=True` assumed) — current recommendation, matches the pattern for the existing group-aware paths
- **Option B:** Fail-closed (treat missing registry as inability to verify, return `calibration_unavailable`)

**Recommendation:** Option A. Legacy callers are internal test infrastructure. The registry is always supplied by the production API endpoint. Failing closed on missing registry would break all existing tests and is not proportionate.

---

### OD-2: Scope of the exploratory/authoritative distinction

**Question:** Should waveform display in ENG mode ever carry a calibration limitation indicator, or is ENG display always unrestricted?

**Current state:** ENG mode display is unrestricted for both source and calculated channels. Only PU mode is gated.

**Option A:** Keep ENG mode unrestricted (current approach). The limitation is a PU-specific concern (physical amplitude normalization).  
**Option B:** Show a limitation indicator in ENG mode (a UI warning, not a data block).

**Recommendation:** Option A for Stage 3B-2B. Stage 3B-3 (UI warnings) is the appropriate stage for any ENG-mode indicator. Do not expand scope here.

---

### OD-3: Synthetic "source unavailable" authority sentinel

**Question:** When a source-kind leaf's `ActiveSource` is not found (should not happen post-cascade, but defensive), should the authority be:
- **Option A:** A synthetic `PhysicalCalibrationAuthority(status="unverified", reason="source_unavailable", ...)` — fails closed
- **Option B:** `None` (not-assessed) — allows PU to proceed

**Recommendation:** Option A. A missing source that bypassed the cascade guard represents an unknown state. Failing closed is consistent with the BEN5K defensive rule.

---

### OD-4: Overlap with Stage 3B-2C (phasor analysis service)

**Question:** Power channels (`active_power`, `reactive_power`, `apparent_power`, three-phase variants) produce a `CalculatedChannel` with `engineering_type=POWER`. They are not Voltage or Current. Stage 3B-2C concerns the phasor analysis service. Do power calculations need their own gate here (3B-2B) or in 3B-2C?

**Current state:** Power PU is `not_applicable` by engineering type (POWER channels have no base configured). The calculated-channel PU gate (3B-2B) would fire the calibration check before `resolve_per_unit()` for POWER channels, but `resolve_per_unit(POWER, ...)` returns `STATUS_NOT_APPLICABLE` anyway (no base for POWER). The gate is harmless but technically unnecessary for POWER channels.

**Recommendation:** Include POWER channels in the traversal anyway (no extra cost, correct behaviour, closes the gap if PU semantics for POWER change in future). The gate fires, finds the authority, and either blocks with `calibration_unavailable` or passes. If the POWER channel's PU path already returns `NOT_APPLICABLE`, that return is unreachable after the gate fires for a BEN5K input.

Owner decision required on whether the authority-blocked path (`calibration_unavailable`) or the existing `not_applicable` path takes precedence for POWER channels.

---

## 12. Verdict

**Can Stage 3B-2B be implemented using the existing Stage 3A domain model without architectural changes?**

**YES.**

Three specific justifications:

1. **Domain model unchanged:** `PhysicalCalibrationAuthority`, `CalibrationEligibility`, and `evaluate_calibration_eligibility()` from Stage 3A are reused without modification. The traversal helper only needs to collect existing authority objects from `DisturbanceRecord.analog_channels` — no new domain concepts.

2. **Service integration at a single seam:** `_resolve_effective_per_unit_for_calculated_channel()` (line 1399 in `calculated_channel_service.py`) is the existing single dispatch point for all four PU entry-points. Adding the gate here, before the CURRENT path, requires approximately 10 lines of new code plus a 30-line traversal helper — no structural changes to the validation flow, no new registries, no new API surface.

3. **Backward compatibility preserved:** The gate is guarded by `if workspace_id is not None and source_registry is not None and calc_registry is not None`, matching the existing opt-in pattern for the group-aware path. All existing tests that do not supply a `source_registry` are unaffected. COMTRADE-only chains pass the gate (all-`None` authorities → `eligible=True`).

The only decisions requiring owner approval before implementation are the four open decisions above (OD-1 through OD-4). None of them require architectural changes — they are policy choices that affect a few lines of the traversal helper.
