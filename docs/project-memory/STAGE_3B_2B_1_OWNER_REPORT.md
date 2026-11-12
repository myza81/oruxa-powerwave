# Stage 3B-2B-1 — Engineering Review Report
# Calculated Channel PU Calibration Authority Gate (DEC-213)
# 2026-11-12

---

## 1. Implementation summary

Injected a PhysicalCalibrationAuthority gate into the single PU dispatch
function for all calculated channels:
`_resolve_effective_per_unit_for_calculated_channel()` in
`backend/app/services/calculated_channel_service.py`.

The gate traverses the full dependency tree of a calculated channel,
collects the original leaf-channel authorities from every source channel,
and blocks authoritative PU output when any leaf fails the calibration
eligibility check (`evaluate_calibration_eligibility`, PURPOSE_ENGINEERING_CALCULATION).

**Two new code artefacts:**
- `_LeafAuthorityResult` dataclass — result carrier for the traversal
- `_collect_leaf_authorities()` — DFS traversal with cycle detection,
  deduplication, and OD-1/OD-3 fail-closed conditions

**One regression fix in existing tests:**
- `backend/tests/test_per_unit_eligibility_integration.py` line 165–169:
  Added `source_registry=r.source` to a direct call to
  `_resolve_effective_per_unit_for_calculated_channel()`. This call
  omitted `source_registry` before Stage 3B-2B-1; OD-1 now blocks
  VOLTAGE/CURRENT types when it is absent. The fix is correct — the test
  simulates a production call and production callers already pass
  `source_registry`.

---

## 2. Gate placement and owner decisions

### Gate placement (OD-4)

The gate fires ONLY when `channel.engineering_type in (VOLTAGE, CURRENT)`:
- POWER, ROCOF, FREQUENCY, UNDEFINED → gate does NOT fire
- Those types reach `STATUS_NOT_APPLICABLE` via the existing
  `resolve_per_unit()` path unchanged

The gate fires BEFORE the CURRENT inherited-PU path (lines 1626+), so
even a CURRENT channel that would inherit PU from a Measurement Group
must first pass the calibration check on its leaf sources.

### OD-1: fail-closed for absent registries

If `source_registry is None` or `workspace_id is None` and the
channel has source-backed refs: returns
`STATUS_CALIBRATION_UNAVAILABLE, reason="source_registry_unavailable"`.

This fires for the ENG-mode no-registry call pattern. Production callers
(waveform endpoint, compliance series, provenance service) all pass
`source_registry`; the gate is harmless for them.

### OD-2: ENG mode

Gate fires ONLY on PU dispatch (`_resolve_effective_per_unit_for_calculated_channel`).
ENG-mode callers never reach this function; they call the ENG waveform
path directly. No ENG-mode behavior change.

### OD-3: machine-readable reasons

No fabricated `PhysicalCalibrationAuthority` objects are created for
missing provenance. Machine-readable `blocked_reason` strings:
- `"source_registry_unavailable"` — registry or workspace_id absent
- `"source_unavailable"` — source not found in registry
- `"channel_not_found_ben5k"` — BEN5K source, channel not in analog_channels
- `"ben5k_authority_absent"` — BEN5K source, authority=None on channel
- `"circular_dependency"` — defensive cycle detection triggered
- `"calculated_channel_not_found"` — calc-kind ref not in calc_registry

These propagate as `PerUnitResolution.reason` to callers.

### OD-4: not_applicable precedence

POWER, ROCOF, FREQUENCY, UNDEFINED: gate does not fire → `STATUS_NOT_APPLICABLE`
returned by existing `resolve_per_unit()`. No change to existing behavior.

---

## 3. Test coverage

### New file: `backend/tests/test_ben5k_calculated_channel_pu_gate.py`

30 tests covering:

**_collect_leaf_authorities unit tests (12 tests):**
- OD-1: source_registry=None → source_registry_unavailable
- OD-1: workspace_id=None → source_registry_unavailable
- OD-3a: source not found → source_unavailable
- OD-3b: BEN5K channel missing → channel_not_found_ben5k
- OD-3c: BEN5K authority absent → ben5k_authority_absent
- Non-BEN5K missing channel → None (not-assessed, backward compat)
- Non-BEN5K missing authority → None (not-assessed, backward compat)
- Single unverified BEN5K leaf → one unverified authority
- Deduplication: same (source_id, channel_name) counted once
- Cycle detection → circular_dependency
- Calc-kind ref without calc_registry → source_registry_unavailable
- Calc-kind ref not in registry → calculated_channel_not_found
- Two-level chain: calc → calc → BEN5K → unverified propagates

**_resolve_effective_per_unit_for_calculated_channel scenario tests (18 tests):**
- Scenario A: BEN5K voltage → reverse polarity → calibration_unavailable
- Scenario B: Two BEN5K sources → subtraction → calibration_unavailable
- Scenario C: BEN5K (unverified) + COMTRADE (not-assessed) → calibration_unavailable
- Scenario D: BEN5K → calc1 → calc2 → calibration_unavailable (chain)
- Scenario E: COMTRADE not-assessed → gate PASSES (backward compat)
- Scenario F: All-verified → gate PASSES
- Scenario G: Verified BEN5K + not-assessed COMTRADE → gate PASSES
  (eligible=True: not-assessed backward compat preserved by domain evaluator)
- Scenario H: BEN5K invalid authority → calibration_unavailable
- Scenario I: Three-level chain BEN5K → calibration_unavailable
- Scenario J: POWER quantity → not_applicable (OD-4: gate does not fire)
- Scenario K: FREQUENCY quantity → not_applicable (OD-4)
- Scenario L: UNDEFINED quantity → not_applicable (OD-4)
- OD-2/OD-1: VOLTAGE with no registries → calibration_unavailable (not a crash)
- OD-2/OD-1: CURRENT with no registries → calibration_unavailable (not a crash)
- OD-4: POWER with no registries → not_applicable (gate does not fire)
- OD-3: reason string is machine-readable non-empty string
- OD-3: blocked reason propagates as PerUnitResolution.reason

---

## 4. Regression results

All results are PASS with zero failures or skips.

| Suite | Tests |
|-------|-------|
| test_ben5k_calculated_channel_pu_gate.py (new) | 30 |
| test_ben5k_pu_calibration_gate.py (Stage 3B-2A) | 46 |
| test_calculated_channel_service.py | 94 |
| test_calculated_group_aware_per_unit.py | 42 |
| test_per_unit_eligibility_integration.py (regression fix) | 69 |
| test_per_unit_provenance_api.py + provenance_service.py + domain.py | 86 |
| test_per_unit_numeric_integrity.py | 164 |
| test_per_unit_reference_policy.py + reference_safety.py + voltage_reference_safety.py | 92 |
| **Full backend/tests/ suite** | **ALL PASS (exit 0)** |

---

## 5. Known behavioral change

**Before Stage 3B-2B-1:** any calculated VOLTAGE/CURRENT channel whose
source chain contained a BEN5K source with Unverified or Invalid
authority would silently resolve PU as if the source were not-assessed
(COMTRADE backward compat). No calibration check existed on the
calculated-channel path.

**After Stage 3B-2B-1:** those channels return
`STATUS_CALIBRATION_UNAVAILABLE` from all four PU-aware entry points
(waveform, cursor, peak, annotation). Engineering-unit values are
unchanged. No PU conversion is applied.

**COMTRADE-only chains are unaffected.** Not-assessed (None) authority
leaves continue to pass the gate (`eligible=True` via
`_result_for_not_assessed`). Existing COMTRADE calculated channels
behave identically to before.

---

## 6. What is NOT activated

- No BEN5K numerical calibration factors (√2/16, any gain correction)
- No new PU base assignment
- No phasor, power, or compliance enforcement
- No Stage 3B-2C, 3B-3 or Slice 6D code

---

## 7. Scenario G: design clarification

The assessment document listed Scenario G as "Mix verified + not-assessed →
not_fully_verified → calibration_unavailable". This was incorrect.

The domain evaluator (`_result_for_not_assessed`) returns `eligible=True`
even when mixed with Verified leaves. The intent is backward compatibility:
not-assessed leaves (COMTRADE, legacy non-BEN5K sources) are always
treated as eligible for the basic PU gate, regardless of what other leaves
are present. Only explicitly Unverified or Invalid authorities block.

Scenario G test was corrected to assert `result.status != STATUS_CALIBRATION_UNAVAILABLE`.
The assessment document should be updated to reflect this.

---

## 8. Files changed

**New:**
- `backend/tests/test_ben5k_calculated_channel_pu_gate.py` — 30 test cases
- `docs/project-memory/STAGE_3B_2B_CALCULATED_CHANNEL_CALIBRATION_ASSESSMENT.md` — assessment
- `docs/project-memory/STAGE_3B_2B_1_OWNER_REPORT.md` — this report

**Modified (implementation):**
- `backend/app/services/calculated_channel_service.py`
  - Added `_LeafAuthorityResult` dataclass (~20 lines)
  - Added `_collect_leaf_authorities()` function (~135 lines)
  - Added gate injection at top of `_resolve_effective_per_unit_for_calculated_channel()` (~35 lines)
  - Added 3 import lines

**Modified (regression fix):**
- `backend/tests/test_per_unit_eligibility_integration.py`
  - 1-line fix: added `source_registry=r.source` to direct call at line 167

---

## 9. Ready for owner review

No commit has been made. The branch is `feature/vlt-ref-001-voltage-reference-safety`.

Recommended review points:
1. Gate placement: confirm gate fires BEFORE the CURRENT inherited path at line 1626
2. OD-1 fail-closed behavior: confirm `source_registry=None` for VOLTAGE/CURRENT is the correct posture
3. Scenario G clarification: confirm not-assessed + verified = eligible is the intended policy
4. Regression fix: confirm adding `source_registry=r.source` to `test_per_unit_eligibility_integration.py` is acceptable

---

## 10. Invalid authority — exploratory-calculation enforcement gap

### What is exposed

The domain evaluator (`physical_calibration.py: _result_for_invalid`) already blocks
`PURPOSE_EXPLORATORY_ANALYSIS` for Invalid authority sources. The Stage 3B-2B-1 gate
uses `PURPOSE_ENGINEERING_CALCULATION`, so an Invalid-authority BEN5K source correctly
returns `calibration_unavailable` on the PU path.

However, `_resolve_input()` (`calculated_channel_service.py` line 343) is called at
calculated-channel **creation time** and resolves raw sample data from the source registry.
It never reads `calibration_authority` — an Invalid-authority BEN5K channel can be used
as input to a new calculated channel without any gate at the creation layer.

The result:
- **PU path (Stage 3B-2B-1):** Invalid → `calibration_unavailable`. Blocked correctly.
- **Calculated-channel creation:** Invalid authority is not checked. The channel is created,
  evaluated, and stored normally. Engineering-unit values are computed and displayed.

This is **not a PU correctness gap** — PU output is blocked by the gate. It is a
**workflow enforcement gap**: a calculated channel using an Invalid-authority source
is accepted and stored, even though the authority classification signals that the source
data itself cannot be trusted for any calculation purpose.

### Why it is not fixed in Stage 3B-2B-1

Stage 3B-2B-1 scope (OD-4): gate fires only on PU dispatch for VOLTAGE/CURRENT.
Blocking at creation time would affect the ENG-mode display path and require a separate
owner decision on whether Invalid authority should block creation entirely, or only block
PU output (the current posture).

### Minimum future integration point

`_resolve_input()` at `calculated_channel_service.py` line ~343 is the single
input-resolution call site. Adding an authority check here would catch all creation-time
Invalid authority conditions before the numeric evaluation runs.

### Why backend enforcement is required

Frontend-only warning is insufficient: the API endpoint
`POST /api/v1/workspaces/{id}/calculated-channels` accepts any valid input reference
regardless of calibration status. A backend gate at `_resolve_input()` or at the
`create_calculated_channel()` layer is the only reliable enforcement point.

### Domain readiness

`_result_for_invalid` already returns `eligible=False` for `PURPOSE_EXPLORATORY_ANALYSIS`.
The domain model is ready. The gap is in the service layer, not the domain.

### Decision needed

Owner must decide: should Invalid authority at a source channel **block calculated-channel
creation** (strict) or only **block PU output** (current posture, Stage 3B-2B-1)? Both
are implementable with the existing domain model. No action is taken here pending that decision.

---

## 11. Performance characteristics

### Call site

`_collect_leaf_authorities()` is called once per PU dispatch inside
`_resolve_effective_per_unit_for_calculated_channel()` at lines 1600–1605
(`calculated_channel_service.py`). This function is reached only when PU mode
is active (the ENG-mode waveform path never calls it).

### Per-request, not per-sample

The traversal operates on the dependency tree of `ChannelRef` objects (a small,
in-memory list per channel), not on sample arrays. It resolves calibration authority
metadata only. The numeric arrays (`channel.values`, `channel.time`) are never touched
by the traversal. Cost is O(D × N) where D is tree depth and N is unique source leaves —
typically 1–3 for real-world calculated channels.

### Deduplication

`_seen_leaves: set` (lines 374, 391–393) deduplicates by stable `(source_id, channel_name)`
tuples. A source channel used in multiple branches of the tree is resolved once. Prevents
redundant registry lookups when branches converge on the same leaf.

### Cycle guard

`_path_visited: frozenset` (lines 371–372, 377, 437) carries the set of calculated-channel
IDs on the current DFS path. Each recursive call receives `current_path` (line 459).
Accumulation is O(depth) per branch; the set is immutable and shared across branches
without mutation. Real cycles are already prevented at channel-creation time by
`would_create_cycle()`, so this guard is a defensive safeguard only.

### No persistent state

`_collect_leaf_authorities()` creates no caches and modifies no module-level state.
Each PU dispatch gets a fresh traversal. This is correct because source-channel
calibration authority can change between re-imports without invalidating the
`CalculatedChannel` object itself.

### ENG-mode callers

Callers that never reach `_resolve_effective_per_unit_for_calculated_channel()` —
specifically, the ENG waveform endpoint and any path that calls `extract_calculated_waveform_range()`
in ENG mode — pay zero cost from Stage 3B-2B-1.
