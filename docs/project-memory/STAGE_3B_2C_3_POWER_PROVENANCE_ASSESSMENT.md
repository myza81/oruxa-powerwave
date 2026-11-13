# Stage 3B-2C-3 — Calculated POWER Physical Calibration Provenance
## Focused Implementation Assessment

**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Date:** 2026-11-13
**Status:** Implementation complete. Committed — see CURRENT_STATE.md for commit hash.

---

## 1. Actual POWER Calculation and API Paths

### 1.1 POWER operations (6 total)

| Operation constant | API wire value | Output |
|---|---|---|
| `OP_ACTIVE_POWER` | `active_power` | Active power (W/kW/MW) |
| `OP_REACTIVE_POWER` | `reactive_power` | Reactive power (VAR/kVAR/MVAR) |
| `OP_APPARENT_POWER` | `apparent_power` | Apparent power (VA/kVA/MVA) |
| `OP_THREE_PHASE_ACTIVE_POWER` | `three_phase_active_power` | Three-phase P |
| `OP_THREE_PHASE_REACTIVE_POWER` | `three_phase_reactive_power` | Three-phase Q |
| `OP_THREE_PHASE_APPARENT_POWER` | `three_phase_apparent_power` | Three-phase |S| |

All produce `engineering_type = POWER`. Fixed output units from `POWER_OUTPUT_UNITS`. Single-phase requires 2 inputs (`[voltage, current]`); three-phase requires 6 inputs (`[V1, I1, V2, I2, V3, I3]`).

### 1.2 Code path — creation

```
POST /api/v1/workspaces/{ws}/calculated-channels
  → calculated_channels.py router
  → create_calculated_channel()   [calculated_channel_service.py:907]
      → _check_creation_authority()  [line 479] — Stage 3B-2B-2: fires for ALL types
      → _resolve_input() × N         — reads V and I arrays
      → evaluate_power_channel() / evaluate_three_phase_power_channel()
      → CalculatedChannel stored in calc_registry
```

### 1.3 Code path — evaluation (4 endpoints)

```
GET   /waveform-range   → extract_calculated_waveform_range()   [line 1793]
GET   /cursor-values    → extract_calculated_cursor_values()    [line 1880]
GET   /peaks            → resolve_calculated_peak_value()       [line 1978]
GET   /annotation-anchor → resolve_calculated_annotation_anchor() [line 2065]
```

Each evaluation entry-point begins with an `InvalidCalibrationAuthorityError` guard (`PURPOSE_EXPLORATORY_ANALYSIS`) at lines 1816, 1909, 2000, 2089 respectively.

### 1.4 Code path — API response

```
GET /calculated-channels
GET /calculated-channels/{id}
  → _channel_out(channel, sources, registry)   [calculated_channels.py:199]
  → CalculatedChannelOut.from_domain(channel, timing)
  → returns CalculatedChannelOut
```

`_channel_out()` currently passes only `channel` (domain object) and `timing`. It does NOT run `_collect_leaf_authorities()`. **No provenance metadata is computed or returned today.**

---

## 2. Confirmed Provenance Gaps

### Gap A — `CalculatedChannelOut` carries no calibration provenance

**Confirmed.** The `CalculatedChannelOut` schema (`backend/app/schemas/calculated_channel.py:159`) has no `calibration_provenance_status` or equivalent field. A consumer receiving a POWER channel in the channel list (GET `/calculated-channels`) cannot determine whether its leaf inputs are Verified, Unverified, or Not Assessed.

The `CalculatedChannel` domain object (`backend/app/domain/calculated_channel.py:269`) has no provenance field either — this is correct design since provenance depends on current source-registry state, which can change after reimport.

### Gap B — Consumer cannot distinguish Verified vs Unverified POWER

**Confirmed.** `CalculatedChannelOut` today exposes `engineering_type = "Power"`, `operation`, `inputs` (source refs), and `parameters`. None of these communicate whether the contributing voltage/current leaves carry Verified, Unverified, or Not Assessed calibration authorities.

A downstream consumer relying on the API cannot prevent misinterpretation of an Unverified POWER output as authoritative.

### Gap C — Frontend POWER panels have no calibration warning

**Confirmed.** The frontend POWER display path (`wwPowerCompactLabel()`, `wwCalculatedChannelNameHtml()`, `WW_POWER_DISPLAY_GLYPHS` — `index.html:33469–33533`) renders P/Q/|S| glyphs and compact labels without any calibration limitation indicator. There is no "exploratory" badge, no calibration icon, no suppression of numerical cursor/peak values for Unverified POWER.

The compliance section now has `calibration_unavailable` handling (Stage 3B-2C-2), but the waveform panel for calculated POWER channels has no equivalent.

### Gap D — Nested POWER provenance at API level

**Partially confirmed.** At evaluation time, `_collect_leaf_authorities()` performs a full DFS traversal through any calc-kind inputs including POWER channels, reaching original source leaves correctly. This is sound: a downstream calc channel that uses a POWER output as input will correctly traverse through it to find source leaves.

However, at the static API level (GET `/calculated-channels`), provenance is not computed at all. If a user creates Calc B = f(POWER_A) and reads Calc B's `CalculatedChannelOut`, there is no provenance field indicating that POWER_A's leaves were Unverified.

**Root cause:** `_channel_out()` in `calculated_channels.py:199` does not have access to `source_registry` for leaf traversal. The router has `source_registry` available; it is simply not passed through.

---

## 3. Recommended Minimal Metadata Contract

### 3.1 Recommendation

Add **two additive nullable fields** to `CalculatedChannelOut`:

```python
# Stage 3B-2C-3 (DEC-213, OD-12): calibration provenance of leaf source inputs.
# Computed at API boundary from current source registry state; None when
# source_registry unavailable (backward compat for tests).
calibration_provenance_status: str | None = None
calibration_provenance_reason: str | None = None
```

These are **additive** — no existing fields are changed, no existing consumers break. `None` is the backward-compatible default when provenance is unavailable.

### 3.2 Status vocabulary (6 values)

| Status value | Meaning | OD-12 case |
|---|---|---|
| `"all_verified"` | All leaf inputs carry explicit Verified authority | A |
| `"exploratory_unverified"` | One or more Unverified leaves; no Invalid | B — exploratory only, NOT authoritative |
| `"not_assessed"` | All leaves Not Assessed (None authority); no Verified/Unverified | E — compat; never claims Verified |
| `"not_fully_verified"` | Mixed Verified + Not Assessed; no Unverified | D — cannot claim full Verified |
| `"blocked_invalid"` | One or more Invalid leaves | C — should not appear (blocked at creation + eval by Stage 3B-2B-2) |
| `"blocked_structural"` | `_collect_leaf_authorities()` returned `blocked_reason != None` | E — missing source, BEN5K absent, etc. |

### 3.3 Computation

At router GET/list time:

```python
def _channel_out(channel, sources, registry):
    provenance_status = None
    provenance_reason = None
    if sources is not None and registry is not None:
        leaf = _collect_leaf_authorities(
            channel,
            workspace_id=...,
            source_registry=sources,
            calc_registry=registry,
        )
        if leaf.blocked_reason is not None:
            provenance_status = "blocked_structural"
            provenance_reason = leaf.blocked_reason
        else:
            elig = evaluate_calibration_eligibility(
                [a for a in leaf.authorities if a is not None],
                PURPOSE_ENGINEERING_CALCULATION,
            )
            if elig.has_invalid_leaves:
                provenance_status = "blocked_invalid"
            elif elig.has_unverified_leaves:
                provenance_status = "exploratory_unverified"
            elif elig.all_verified:
                provenance_status = "all_verified"
            elif elig.has_not_assessed_leaves and elig.reason == REASON_NOT_FULLY_VERIFIED:
                provenance_status = "not_fully_verified"
            else:
                provenance_status = "not_assessed"
            provenance_reason = elig.reason
    return CalculatedChannelOut.from_domain(channel, timing, provenance_status, provenance_reason)
```

`PURPOSE_ENGINEERING_CALCULATION` is used for provenance reporting because it marks Unverified leaves as not eligible for authoritative use — the status accurately reflects whether the POWER output can be treated as authoritative.

### 3.4 Why not store provenance on `CalculatedChannel`

Source calibration status can change after reimport (same source_id, different calibration). The POWER channel itself is not deleted on reimport (only on source removal). Provenance computed at creation time and stored on the domain object would become stale after reimport. Computing at API boundary using current source state is the correct approach.

### 3.5 Why not a separate endpoint

A separate `GET .../calculated-channels/{id}/calibration-provenance` endpoint would require an extra round-trip per channel in the channel list. Embedding in the channel list response is consistent with how `per_unit_status`, `timing_status`, and `display_axis_key` are already computed at list time.

---

## 4. Complete Calibration-Status Precedence Rules

These rules are already encoded in `evaluate_calibration_eligibility()` (`physical_calibration.py:223`). They apply without modification for POWER provenance.

**Precedence order (highest to lowest severity):**

1. **Any `CALIBRATION_INVALID` leaf** → `blocked_invalid` (all purposes blocked except raw inspection)
2. **Any `CALIBRATION_UNVERIFIED` leaf, no Invalid** → `exploratory_unverified` (`raw_inspection` and `exploratory_analysis` eligible; `engineering_calculation` and `compliance_assessment` blocked)
3. **Mixed Verified + Not Assessed, no Unverified** → `not_fully_verified` (all purposes eligible; cannot claim `all_verified`)
4. **All Not Assessed (None authority), no Verified** → `not_assessed` (all purposes eligible; compat mode)
5. **All Verified** → `all_verified` (all purposes eligible; `all_verified = True`)

The existing `REASON_*` constants (`REASON_UNVERIFIED`, `REASON_NOT_FULLY_VERIFIED`, etc.) serve as the `calibration_provenance_reason` values without requiring new constants.

**OD-12 specific rule:** Unverified POWER inputs (case B) may produce exploratory waveforms. The `calibration_provenance_status = "exploratory_unverified"` communicates this limitation to consumers without blocking evaluation (the evaluation gate uses `PURPOSE_EXPLORATORY_ANALYSIS` which allows Unverified — this is correct and must be preserved).

---

## 5. Backend Integration Points

| File | Line | Action |
|---|---|---|
| `backend/app/schemas/calculated_channel.py` | 159 (`CalculatedChannelOut`) | Add `calibration_provenance_status: str | None = None` and `calibration_provenance_reason: str | None = None` |
| `backend/app/schemas/calculated_channel.py` | 266 (`from_domain`) | Accept and store provenance fields |
| `backend/app/api/v1/calculated_channels.py` | 199 (`_channel_out`) | Add `source_registry`, `workspace_id` params; call `_collect_leaf_authorities()` + `evaluate_calibration_eligibility()` |
| `backend/app/api/v1/calculated_channels.py` | `GET ""` and `GET "/{id}"` endpoints | Pass `source_registry` and `workspace_id` to `_channel_out()` |
| `backend/app/services/calculated_channel_service.py` | No change needed | `_collect_leaf_authorities()` already works correctly |
| `backend/app/domain/physical_calibration.py` | No change needed | `evaluate_calibration_eligibility()` already returns all required fields |

**No changes to `CalculatedChannel` domain object.** No changes to evaluation entry-points. No changes to creation gate.

**Import additions in `calculated_channels.py`:**
```python
from app.services.calculated_channel_service import _collect_leaf_authorities
from app.domain.physical_calibration import (
    evaluate_calibration_eligibility, PURPOSE_ENGINEERING_CALCULATION,
    REASON_NOT_FULLY_VERIFIED,
)
```

---

## 6. Frontend Safety Implications

### 6.1 Minimum required indicator (OD-12 scope)

When `calibration_provenance_status === "exploratory_unverified"`, show a small inline badge on the POWER channel's row in the channel list panel. The badge text should communicate the exploratory limitation without overwhelming the display.

**Recommended implementation:** a subtle `⚠ exploratory` or `⚠ unverified inputs` label beside the channel name in the sidebar channel list, implemented as:

```javascript
function wwCalcChannelProvenanceBadgeHtml(calc) {
    if (calc.calibration_provenance_status === "exploratory_unverified") {
        return '<span class="ww-calc-provenance-badge ww-calc-provenance-badge--exploratory" ' +
               'title="One or more input sources are Unverified. This channel is exploratory only.">⚠ exploratory</span>';
    }
    return "";
}
```

**CSS token:**
```css
.ww-calc-provenance-badge--exploratory {
    color: #a86a00;
    font-size: 0.8em;
    margin-left: 0.4em;
}
```

### 6.2 Surfaces that need updating

| Surface | Required change |
|---|---|
| Channel list entry | Provenance badge beside channel name (minimum required) |
| POWER panel title | No change required at Stage 3B-2C-3 (Stage 3B-3 handles calibration-warning UX) |
| Cursor readouts | No change — values remain numerically correct; badge in channel list communicates limitation |
| Peak values | No change — same rationale |
| Calculated-channel details | Optionally show provenance status; not minimum required for OD-12 |
| Download/export | No change at Stage 3B-2C-3 (downstream export risk, see §7) |

### 6.3 Stale metadata risk

After source reimport (same source_id, new calibration), the POWER channel continues to exist. `calibration_provenance_status` is computed from current source state at each GET request, so it always reflects the current calibration authority. No stale state risk.

After source removal, the cascade in `remove_calculated_channels_for_source()` deletes all POWER channels grounded on that source. No stale state risk.

After workspace/ENG mode changes: provenance is re-fetched on each channel list load. No stale state risk.

---

## 7. Downstream Consumption and Export Risks

### 7.1 Download/export (CSV)

The existing `POST /data-prep/export` endpoint exports waveform arrays. It does not include calibration provenance today. An Unverified POWER CSV export would carry no disclaimer.

**Risk:** An engineer downloads a POWER CSV from an Unverified BEN5K source and treats it as authoritative. This is a Stage 3B-3 concern — the broader calibration-warning UX will add provenance to exports. Stage 3B-2C-3 should NOT include export changes (out of scope for the minimum provenance indicator).

### 7.2 Nested calculated channels

A downstream calc channel (e.g., addition of two POWER channels) has `engineering_type = POWER`. Its `_collect_leaf_authorities()` DFS will traverse through both POWER channels to their V/I source leaves. The resulting `calibration_provenance_status` on the downstream channel will correctly reflect the combined leaf authority set (worst case wins: Unverified leaf anywhere → `exploratory_unverified`).

### 7.3 Manual Calculator

The existing manual source-independent Calculator creates channels with `inputs` pointing to no source channels (or uses a fixed numeric input). `_collect_leaf_authorities()` on such a channel returns `authorities=[]` (no leaves). `evaluate_calibration_eligibility([])` returns `all_verified=True` (empty leaf list = no known calibration limitation, by existing policy in `physical_calibration.py:294`). This is the correct behavior: manual values have no source provenance to evaluate.

**Do not change this behavior.** A manually-entered POWER value is source-independent by design.

---

## 8. Backward-Compatibility Considerations

1. **New fields are nullable** — existing consumers that do not read `calibration_provenance_status` are unaffected. The fields default to `None` when provenance is unavailable (source_registry not passed).

2. **No existing gate changes** — creation and evaluation gates are unchanged. Unverified POWER continues to work exactly as today.

3. **No PU math changes** — `_resolve_effective_per_unit_for_calculated_channel()` already skips POWER (line 1702). This is preserved.

4. **COMTRADE/CSV backward compat** — Not Assessed leaves (None authority) produce `calibration_provenance_status = "not_assessed"`. All existing COMTRADE-based POWER channels continue to work and are marked `not_assessed` (which is a true statement: they have never been assessed).

5. **API serialization** — Two new `str | None` fields added to a Pydantic model. This is a standard additive extension. Existing test fixtures do not need updating unless they assert an exact field set.

---

## 9. Suggested Implementation Slices

### Slice A — Schema extension (backend, no behavior change)
- Add `calibration_provenance_status: str | None = None` and `calibration_provenance_reason: str | None = None` to `CalculatedChannelOut` in `schemas/calculated_channel.py`
- Update `from_domain()` to accept and store them
- All callers pass `None` by default (backward compat)
- Tests: schema serializes `None` and all 5 non-null status values without error

### Slice B — Provenance computation in router (backend behavior)
- Update `_channel_out()` in `calculated_channels.py` to accept `source_registry` and `workspace_id`
- Add `_collect_leaf_authorities()` + `evaluate_calibration_eligibility()` call
- Update GET `""` and GET `"/{id}"` to pass source_registry and workspace_id
- Tests: API responses for Verified, Unverified, mixed, Not Assessed, nested POWER

### Slice C — Frontend provenance badge (frontend)
- Add `ww-calc-provenance-badge--exploratory` CSS token
- Inject `wwCalcChannelProvenanceBadgeHtml(calc)` into the channel list entry HTML for POWER channels
- Tests: browser — Unverified BEN5K POWER channel shows `⚠ exploratory` badge

### Slice D — Full regression
- 15 backend tests (scenarios A–O from §10)
- 3 browser tests (synthetic BEN5K + COMTRADE + stale-state)

Slices A and B are independent and can be developed together. Slice C depends on Slice B being available in the API. Slice D covers all.

---

## 10. Regression Plan (Owner Scenarios A–O)

| Scenario | Test description | Coverage |
|---|---|---|
| A | BEN5K Unverified V + Unverified I → POWER: `calibration_provenance_status = "exploratory_unverified"`; waveform evaluates; numerical values unchanged | Backend + browser |
| B | Unverified source → calc Voltage → calc Current → POWER: same `exploratory_unverified`; correct leaf traversal | Backend unit |
| C | Depth-3 nested chain: source → calc1 (Voltage) → calc2 (Voltage) → POWER: provenance correctly propagated | Backend unit |
| D | Verified V + Unverified I → POWER: `exploratory_unverified` (Unverified leaf present) | Backend unit |
| E | Verified V + Not Assessed I → POWER: `not_fully_verified` (mixed Verified + Not Assessed) | Backend unit |
| F | Invalid leaf → POWER creation blocked (HTTP 422); no `calibration_provenance_status` returned | Backend unit |
| G | Missing source after POWER creation: `blocked_structural` in provenance; waveform still evaluates from cached arrays | Backend unit |
| H | Source reimport → POWER channel persists → provenance recomputed from new calibration state | Backend + browser |
| I | Three-phase POWER from V_A(Unverified) + V_B(Verified) + V_C(Verified) + I_A/B/C(Verified) → `exploratory_unverified` | Backend unit |
| J | Verified V + Verified I → POWER: `all_verified`; waveform evaluates; numerical values unchanged | Backend unit |
| K | Correct MW/MVar/MVA unit labels preserved; cursor/peak values correct regardless of provenance | Backend unit |
| L | No stale provenance badge after source reimport (provenance re-fetched on channel list load) | Browser |
| M | COMTRADE V + COMTRADE I → POWER: `not_assessed`; backward compat preserved | Backend + browser |
| N | Manual Calculator source-independent POWER (no source leaves): `all_verified` (empty leaf list = no known limitation) | Backend unit |
| O | API response serialization: all 5 provenance status values serialize without ValidationError | Backend schema test |

**Browser tests must be executable using synthetic fixtures** (extend `synthetic_ben5k_compliance.ben` or the phasor fixture for Voltage + Current BEN5K channels). No private owner `.ben` files.

**Performance note:** Per-channel provenance computation (`_collect_leaf_authorities()` DFS + `evaluate_calibration_eligibility()`) is pure in-memory with no I/O. It runs once per channel per GET request. Typical workspaces have fewer than 50 calculated channels. No performance concern.

---

## 11. Unresolved Owner Decisions

None outstanding. All implementation decisions follow directly from OD-12 and the existing DEC-213 domain model.

The following are confirmed by this assessment (not requiring a new decision):

| Item | Confirmation |
|---|---|
| Unverified POWER may evaluate (exploratory allowed) | OD-12 already approved; evaluation gate uses PURPOSE_EXPLORATORY_ANALYSIS — no change needed |
| Provenance computed at API boundary, not stored on domain object | Assessment confirms: source calibration can change post-import; dynamic computation is the correct design |
| `all_verified` = TRUE only when ALL leaves carry explicit Verified authority | Existing `evaluate_calibration_eligibility()` semantics, unchanged |
| Manual Calculator channels: `all_verified` (no source leaves → no limitation) | Existing empty-leaf policy, unchanged |
| Export provenance warning deferred to Stage 3B-3 | Noted as out-of-scope risk in §7.1 |

---

## Conclusion

**Stage 3B-2C-3 can be implemented using the existing DEC-213 domain model and `_collect_leaf_authorities()` without architectural redesign.**

The existing gate infrastructure (Stage 3B-2B-2) already correctly blocks Invalid inputs at creation and evaluation time for all engineering types including POWER. The existing `_collect_leaf_authorities()` already correctly traverses through POWER channels to source leaves. The existing `evaluate_calibration_eligibility()` already returns all the data needed to determine provenance status.

The implementation is additive: two new nullable fields on `CalculatedChannelOut`, computed at the API boundary using existing service functions, plus a minimal frontend badge for the exploratory state. No changes to evaluation gates, PU mathematics, BEN decoding, compliance calculation formulas, or existing approved commits.

**Scope estimate:** Comparable to Stage 3B-2C-1 in backend complexity; smaller on the frontend side (1 badge vs. 4 frontend changes in Stage 3B-2C-2). 4 implementation slices. Approximately 15 new backend tests + 3 browser tests.

---

*Implementation complete. 25 backend tests + 8 browser tests pass. Committed to `feature/vlt-ref-001-voltage-reference-safety`. See CURRENT_STATE.md for commit hash and final test counts.*
