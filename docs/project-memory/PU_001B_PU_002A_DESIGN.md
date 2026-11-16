# PU-001B + PU-002A Engineering Design Document

**Status:** Design review — owner approval required before implementation.
**Date:** 2026-11-09
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Governed by:** [DEC-212](DECISIONS.md#dec-212)

---

## 1. Owner decision recorded

[DEC-212](DECISIONS.md#dec-212) records the following approved policy:

- Automatic PU is applicable to **Voltage only**.
- The standard ENG/PU display selector controls Voltage channel display.
- Raw Current waveforms always retain physical engineering units (A / kA).
- Current normalization is performed explicitly through Calculated Channels.
- CT primary winding ratings are never automatically used as equipment nominal-current references.
- Existing Current PU domain services remain available pending dependency review.
- Changes must not silently break existing calculated results, saved configurations, or engineering functions.

---

## 2. PU-001B — Multi-hypothesis Voltage reference resolver

### 2.1 Problem statement

The existing `auto_base_evidence.resolve_voltage_group_evidence()` resolver (Step 3b) uses a
one-pass standard-nominal-match heuristic (the "Convention A/B" check) to determine whether a
COMTRADE L-G channel's `primary_ratio` encodes the nominal system L-L voltage directly
(Convention A) or a phase-winding voltage needing × √3 (Convention B).

The heuristic works by:
1. Checking if `primary_ratio` is near a standard nominal → Convention A.
2. Else if `primary_ratio × √3` is near a standard nominal → Convention B.
3. Else → ambiguous.

**PU-001 root cause:** When `primary_ratio = 275.0 kV` (Convention A), the check correctly
selects A. But the check is not symmetric: when `primary_ratio = 76.2 kV` (Convention B for a
132 kV system), it correctly selects B. However, `primary_ratio = 133.0 kV` triggers both A
(133 ≈ 132 kV IEC) and B (133 × √3 = 230.4 ≈ 230 kV ANSI) — the existing code silently picks
A because the `near_direct` branch fires first. This is an undetected ambiguity.

### 2.2 Explicitly separated quantities

The PU-001B design separates the following quantities:

| Quantity | Source | Used for |
|---|---|---|
| `primary_ratio` | COMTRADE CFG field | Input only — raw VT winding data |
| Nominal system L-L voltage | Hypothesis A: `primary_ratio`; Hypothesis B: `primary_ratio × √3` | PU denominator derivation |
| VT primary winding rating | Hypothesis B phase-winding = `primary_ratio` | Secondary plausibility check |
| VT secondary winding rating | `secondary_ratio` field | Winding ratio plausibility |
| Recorded waveform geometry | Channel name detection (C3) | Denominator selection |
| Measurement side | COMTRADE PS flag | Independence check only |
| PU denominator | L-L: nominal_ll; L-G: nominal_ll / √3 | Per-unit conversion |
| Evidence provenance | Per-dimension weights | Transparency |

### 2.3 Multi-hypothesis design

**Prototype module:** `backend/app/domain/voltage_hypothesis.py`

For each Line-to-Ground channel group, the resolver evaluates:

#### Hypothesis A — `Vnom_LL = primary_ratio`
Assumes the CFG engineer entered the nominal system L-L voltage directly in `primary_ratio`.
Dominant encoding in IEC/EN protection relay COMTRADE files.

#### Hypothesis B — `Vnom_LL = primary_ratio × √3`
Assumes the CFG engineer entered the actual VT phase-winding primary voltage in `primary_ratio`.
Nominal L-L system voltage = `primary_ratio × √3`.

#### Evidence dimensions (four, evaluated independently)

| Dimension | Weight when supporting | Notes |
|---|---|---|
| `standard_nominal_match` | 2.0 (< 1% off), 1.0 (< 2% off) | Standard IEC + ANSI + regional table |
| `name_token_corroboration` | 3.0 | kV token in channel name matching candidate |
| `group_name_token` | 2.0 | kV token in group/source name matching candidate |
| `vt_winding_ratio_plausibility` | 1.0 | secondary_ratio / primary_phase gives typical VT ratio |

Opposing evidence (negative weights) is accumulated separately and used for opposition-breaking.

#### Verdict logic

```
if only A is supported:  → select A
if only B is supported:  → select B
if both supported AND B opposed (but not A):  → select A (opposition-breaking)
if both supported AND A opposed (but not B):  → select B (opposition-breaking)
if both supported AND neither clearly opposed:  → "ambiguous" (needs review)
if neither supported:  → "none" (needs review)
```

This is strictly more conservative than the existing heuristic: when both candidates plausibly
match, the system declines to auto-configure rather than guessing.

### 2.4 Key engineering findings from the prototype

#### Finding 1 — 275.0 kV L-G (PULU scenario)
- Hypothesis A: 275.0 kV ✓ (exact match to IEC standard 275 kV)
- Hypothesis B: 476.31 kV ✗ (not near any standard; closest is 500 kV at 4.7% → rejected)
- **Result:** Hypothesis A selected with high confidence. Nominal = 275.00 kV. ✓

#### Finding 2 — 76.2 kV VT (phase-winding, Convention B)
- Hypothesis A: 76.2 kV ✗ (not near any standard; closest is 66 kV at 15.5% → rejected)
- Hypothesis B: 131.98 kV ✓ (within 0.013% of IEC standard 132 kV)
- **Result:** Hypothesis B selected with high confidence. Nominal = 131.98 kV. ✓

#### Finding 3 — 132.0 kV L-G (genuinely ambiguous without context)
- Hypothesis A: 132.0 kV ✓ (exact match to IEC standard 132 kV)
- Hypothesis B: 228.6 kV ✓ (within 0.6% of ANSI standard 230 kV)
- **Result without context:** `ambiguous` — the multi-hypothesis resolver correctly declines.
- **With group_name="132KV":** Hypothesis B opposed (228.6 ≠ 132 → weight −1.5), Hypothesis A
  supported + opposed = False → **Hypothesis A selected**. Nominal = 132.00 kV. ✓
- **Improvement over heuristic:** The existing `auto_base_evidence.py` heuristic silently picks
  Convention A for 132.0 kV because `near_direct` is checked first. This is correct in
  practice but masks the genuine ambiguity. The multi-hypothesis approach is safer: it requires
  corroborating evidence and returns `ambiguous` without it.

#### Finding 4 — 133.0 kV (genuinely ambiguous, resolvable by name token)
- Both A (133 ≈ 132 kV) and B (230.4 ≈ 230 kV) initially plausible.
- With group_name="133KV": A is corroborated (+2), B is opposed (−1.5) → **A selected**.
- This is the opposition-breaking pathway working correctly.

#### Finding 5 — Correct PU calculation for PULU
- Nominal = 275.00 kV L-L (Hypothesis A)
- L-G denominator = 275.00 / √3 = 158.771 kV
- Measured prefault L-G voltage ≈ 162.42 kV → PU ≈ 1.023 pu ✓
- If Hypothesis B were incorrectly selected: denominator = 275.0 kV, PU = 162.42/275.0 = 0.59 pu ✗

### 2.5 Assessment of the Convention A/B heuristic (provisional)

The existing Convention A/B heuristic (`_is_near_standard_nominal_kv` in `auto_base_evidence.py`)
is **sound for the common cases** and fixes the PU-001 bug correctly:
- 275.0 kV: heuristic → A ✓, multi-hypothesis → A ✓
- 76.2 kV: heuristic → B ✓, multi-hypothesis → B ✓
- 50.0 kV: heuristic → neither ✓, multi-hypothesis → neither ✓

However, it has a **known weakness**: for `primary_ratio` values that happen to fall near both a
standard nominal AND a standard nominal / √3 (e.g., 133.0 kV), the heuristic silently picks
Convention A because `near_direct` is checked first. The multi-hypothesis resolver returns
`ambiguous` in this case, which is the correct engineering response.

**Recommendation:** The PU-001B multi-hypothesis resolver is the preferred long-term design.
The Convention A/B heuristic is acceptable as a provisional measure for the common 275/132 kV
cases but should be replaced before the feature is considered complete.

**Transition path:** The multi-hypothesis resolver is ready as a prototype. Wiring it into the
import lifecycle requires owner approval and replaces the Convention A/B heuristic in
`auto_base_evidence.py` Step 3b.

### 2.6 Waveform corroboration design (design only, not implemented)

The measured waveform can corroborate a candidate but must not independently establish nominal
voltage (a recording of a sustained 0.9 pu undervoltage must not be misclassified as nominal).

**Proposed interface:**

```python
@dataclass
class WaveformWindow:
    """A candidate 'trustworthy' interval extracted from the recording."""
    start_s: float
    end_s: float
    fundamental_rms_per_phase: tuple[float, float, float]  # kV
    three_phase_balance_ok: bool   # unbalance < 5%
    frequency_stable: bool         # within ± 1 Hz of nominal
    no_clipping: bool
    no_severe_harmonics: bool
    is_prefault: bool              # precedes onset marker

@dataclass
class WaveformCorroboration:
    """Result of comparing a nominal candidate against waveform evidence."""
    candidate_ll_kv: float
    expected_lg_rms_kv: float      # candidate_ll / √3
    measured_mean_lg_rms_kv: float # from trustworthy window
    ratio: float                   # measured / expected (target ≈ 1.0 pu)
    deviation_pct: float
    verdict: Literal["corroborated", "inconsistent", "indeterminate"]
    # corroborated: ratio within ± 10 %
    # inconsistent: ratio < 0.5 or > 1.3
    # indeterminate: no trustworthy window available
    trust_level: Literal["high", "low"]
```

**Corroboration rules:**
- A `corroborated` verdict (ratio 0.90–1.10) increases confidence in the selected hypothesis.
- An `inconsistent` verdict does NOT by itself reject a hypothesis — the recording may be a
  sustained fault, motor start, or other non-nominal condition.
- `indeterminate` (no trustworthy prefault window) → no change in confidence.
- Measured magnitude must NEVER independently establish the nominal voltage: corroboration
  only confirms or questions a hypothesis formed from metadata.

**Integration constraint:** Waveform scanning must not be introduced into the synchronous import
lifecycle (upload → parse → group → auto-configure). It may be offered as a post-import
advisory service.

---

## 3. PU-002A — Current PU dependency inventory

### 3.1 Raw waveform rendering

**File:** `frontend/index.html` → `wwErState.unitMode` / `wwApplyUnitMode()`

The global `unitMode` ("engineering" | "per_unit") is currently applied uniformly to ALL
channels (Voltage and Current). The ENG/PU toggle switches between rendering all channels in
their native units and rendering channels using their configured PU denominator.

For Current channels, `wwErChannelUnitDisplay()` calls the backend per-unit resolution endpoint.
If the Current channel has a configured `pu_status=configured`, PU values are requested; if
`not_applicable` or `base_required`, engineering values are used.

**Classification:** Adapt to Voltage-only display (§4 of this document).

### 3.2 Measurement Group current group configuration

**File:** `backend/app/domain/current_group_config.py`

`resolve_current_base_for_group()` checks:
- Authority gate (`base_authority`)
- Group lifecycle status gate
- Equipment rating path: linked Voltage group nominal L-L kV → Ibase = rating_mva / (√3 × Vnom_ll)
- Manual Ibase path: explicitly set value
- None path: no Ibase configured

**Critical dependency (DEC-212 §regression risk):** The equipment-rating path uses
`linked_voltage_config.nominal_voltage_ll_kv`. If the auto-resolver writes an incorrect Voltage
nominal (e.g., from ambiguous Convention A/B), the derived Ibase is proportionally wrong.
Example: 100 MVA equipment, 275 kV nominal → correct Ibase = 209.95 A.
If nominal were incorrectly written as 476.31 kV: derived Ibase = 121.21 A (−42%). This would
silently corrupt all Current PU values in the affected engineering contexts.

**Classification:**
- Keep domain service unchanged.
- Guard: auto-resolver must not write `nominal_voltage_ll_kv` with `base_authority=auto_resolved`
  to any Voltage group that has a Current group linked to it via `method=METHOD_EQUIPMENT_RATING`,
  unless the nominal evidence meets the multi-hypothesis resolver's `suitable_for_auto=True`
  threshold (is_resolved AND confidence=high/medium AND not ambiguous).

### 3.3 Source Default PU path

**File:** `backend/app/domain/per_unit.py` → `resolve_per_unit()` (legacy DEC-049 path)

When a channel belongs to no Measurement Group, the Source Default PU profile is used. This
path applies to both Voltage and Current channels.

**Classification:** Preserve unchanged. Source Default remains usable for manually set Current
Ibase values.

### 3.4 Calculated Channels — Current PU

**Files:** `backend/app/domain/calculated_current_config.py`,
`backend/app/domain/calculated_channel.py`

Calculated Current PU produces a channel whose values = `raw_current / ibase`. It uses the
Current group's configured `ibase` value (from group configuration) or a manually specified
reference.

**Classification:** Preserve unchanged. This is the PREFERRED path for Current normalization
per DEC-212.

### 3.5 Calculated Channels — same-group Voltage inheritance

**File:** `backend/app/domain/calculated_channel.py`

Voltage Calculated Channels inherit the PU denominator from the same Voltage group (DEC-052
multi-input restriction). Unary operations on a Voltage channel inherit the group base.

**Classification:** Preserve unchanged.

### 3.6 Power Calculator

**File:** `backend/app/services/impedance_analysis_service.py` and related

Uses Voltage and Current PU bases for per-unit power, impedance, and sequence calculations.
When Voltage group has `base_authority=auto_resolved`, the nominal kV from that group is used
in power calculations.

**Classification:** Preserve unchanged. Already protected by the authority gate.

### 3.7 V-I Phasors

**File:** `backend/app/services/phasor_analysis_service.py`

Accepts both Voltage and Current in engineering or PU units depending on the configured bases.

**Classification:** Preserve unchanged.

### 3.8 Compliance analysis

**Files:** `backend/app/services/compliance_series.py`,
`backend/app/services/compliance_measurement_service.py`,
`backend/app/services/compliance_readiness_service.py`

Compliance uses Voltage PU (for voltage profile assessments) and Current PU (for overcurrent
assessment when a Current Ibase is configured). Both depend on the authority gate.

**Classification:** Preserve unchanged.

### 3.9 Event Reconstruction

**Files:** `frontend/index.html` → `wwErState`, `wwErChannelUnitDisplay()`, `wwErState.unitMode`

Event Reconstruction currently applies a single global `unitMode` to all channels. The ENG/PU
buttons above the Event Reconstruction plot switch ALL channels simultaneously.

**Classification:** This is the primary surface requiring a Voltage-only display change (§4).

### 3.10 Cursor and annotation readouts

**File:** `frontend/index.html` → waveform cursor callbacks

Cursor values are computed in the same units as the displayed trace. If a channel is shown in PU,
the cursor reads in PU.

**Classification:** Preserve unchanged. When Current channels stop being rendered in PU (§4),
their cursor values remain in A/kA, which is correct.

### 3.11 ENG/PU display-mode global state

**File:** `frontend/index.html` → `wwApplyUnitMode()`, `wwErState.unitMode`

The global `unitMode` is a single string ("engineering" | "per_unit") applied to all channels.
The PU toggle fires `wwApplyUnitMode("per_unit")` which causes all channels to request PU
values from the backend. For Current channels without a configured Ibase, the backend returns
`pu_status=base_required` and the trace falls back to engineering units automatically — but the
intent is ambiguous and the UI shows no distinction.

**Classification:** Adapt (§4).

### 3.12 Browser tests asserting Current PU behaviour

Browser tests in `browser-tests/` include assertions against Current PU configuration and
display. These must be inventoried before any change to the ENG/PU toggle behavior.

Relevant specs (from existing test files):
- `auto-pu-import.spec.js` — asserts `configuredVoltageGroups > 0` triggers PU mode
- `per-unit-voltage-reference-safety.spec.js` — asserts Voltage reference safety

**Classification:** These tests do not assert that Current channels are shown in PU; they
assert that the toggle switches to PU mode when Voltage groups are configured. The proposed
Voltage-only change preserves this behavior (the toggle fires, Voltage changes, Current stays).

---

## 4. Proposed Voltage-only display implementation plan

### 4.1 Goal

The ENG/PU selector continues to control the display mode label and applies to Voltage channels.
Raw Current channels remain in A/kA regardless of the mode selection.

### 4.2 Minimum safe frontend change

The smallest maintainable change is to filter Current channels out of the PU rendering path
at the display layer, NOT to change the global `unitMode` state.

**Current code path in `wwErChannelUnitDisplay()`:**
```javascript
function wwErChannelUnitDisplay(kind, sourceId, channelName, unitMode) {
    if (unitMode !== "per_unit") return { state: "engineering", ... };
    const resolution = ...;  // fetch from backend
    if (resolution.status === "configured") return { state: "per_unit", ... };
    if (resolution.status === "not_applicable") return { state: "engineering", ... };
    return { state: "unavailable", ... };
}
```

**Proposed change:** Add a `kind` check at the top:
```javascript
function wwErChannelUnitDisplay(kind, sourceId, channelName, unitMode) {
    // Current channels always render in engineering units (DEC-212)
    if (kind === "current") return { state: "engineering", unitMode: "engineering",
                                     key: "engineering", resolution: null };
    if (unitMode !== "per_unit") return { state: "engineering", ... };
    // ... existing voltage path unchanged ...
}
```

**Label update:** The existing "Units: ENG | PU" toggle text is changed to
"Voltage Display: ENG | PU" or similar to communicate that it controls Voltage only.

**Scope:** This is a single-function change plus a label update. The global `unitMode` state
is preserved as-is. No backend changes required. No existing PU calculation paths are touched.

### 4.3 Cursor/annotation consistency

When Current channels always render in engineering units:
- Current cursor values remain in A/kA ✓
- Voltage cursor values switch between kV (ENG) and pu (PU) ✓
- Event Reconstruction axis grouping: Current channels always use a kA/A axis; Voltage
  channels use either kV or pu axis depending on mode ✓

### 4.4 Manual Voltage display selection persistence

`wwApplyUnitMode("per_unit")` already stores the selection. This behavior is preserved.

### 4.5 Calculated Current PU traces

A Calculated Channel created from a Current channel with an explicit normalization remains
available as a Calculated Channel trace. Its `kind` = "calculated_voltage" or similar
(it is NOT a raw Current channel), so the kind filter does not suppress it.

**To be verified:** The `kind` of a Calculated Current PU channel in the Event Reconstruction
context — ensure it is not classified as "current" and suppressed unintentionally.

---

## 5. Proposed explicit Current normalization Calculated Channel design

### 5.1 Reference types

An explicit Current normalization Calculated Channel would support the following reference types:

| Reference type | Input | Denominator | Notes |
|---|---|---|---|
| Nominal equipment current (direct) | Engineer-specified RMS A | As entered | Standard Ibase |
| Equipment MVA + Voltage base | Rating MVA, group Voltage nominal kV | MVA / (√3 × Vnom_kV) × 1000 A | Requires confirmed Voltage base |
| Explicit reference channel | Another Current channel | RMS of reference window | Useful for ratio studies |
| Protection pickup multiple | Pickup current setting (A) | Pickup value | Shows per-unit of pickup, not of nominal |

**Important:** CT primary winding rating is NOT a valid reference type (C5 / DEC-050 §11 / DEC-212).

### 5.2 Peak vs RMS semantics

A rated sinusoidal Current waveform at the reference current has instantaneous peaks of
`±1.414 pu` (= ±√2). The corresponding RMS waveform (if the user requests an RMS Calculated
Channel) is `1.0 pu`. Both are correct; the engineer should choose the appropriate form.

This distinction must be clearly communicated in the UI to avoid misinterpretation.

### 5.3 Primary/Secondary numerical reference

The engineer must specify whether the reference value is a **primary-side** or
**secondary-side** quantity. The recorded waveform's measurement side (PS flag) determines the
applicable denominator:
- Primary recording + primary reference → PU directly
- Primary recording + secondary reference → rescale by CT ratio
- Secondary recording + secondary reference → PU directly

This mirrors the Voltage reference-side safety mechanism (DEC-210, DEC-211).

### 5.4 Existing manual Current PU capability

The existing `set_current_base_manual()` path and `base_authority=manual` authority allow
engineers to set a manual Ibase through the Measurement Groups UI. This capability must be
preserved until its integration with the Calculated Channel normalization workflow is designed
and owner-approved. Removing it prematurely would break existing manual configurations.

---

## 6. Critical regression risk — Voltage nominal contaminating Current calculations

### 6.1 Risk description

`resolve_current_base_for_group()` with `method=METHOD_EQUIPMENT_RATING` uses
`linked_voltage_config.nominal_voltage_ll_kv` to derive equipment base current:

```python
ibase_a = (equipment_rating_mva * 1e6) / (SQRT_3 * nominal_voltage_ll_kv * 1e3)
```

If `nominal_voltage_ll_kv` is incorrect (e.g., from an ambiguous Convention A/B resolution),
the derived Ibase is proportionally wrong. The error is proportional to the voltage error:
- Incorrect 476.31 kV instead of 275.00 kV: Ibase ratio = 275/476.31 = 0.577 → 42% low.
- All subsequent Current PU values, phasor magnitudes, and compliance measurements using this
  Ibase would be proportionally in error.

### 6.2 Mitigation

1. The `auto_resolved` Voltage nominal must ONLY be written if `suitable_for_auto=True`
   (resolved, medium or high confidence, not ambiguous).
2. Before writing `base_authority=auto_resolved` to a Voltage group, the auto-base service
   must check whether any Current group is linked to it via `METHOD_EQUIPMENT_RATING`. If
   such a link exists, the auto-resolved confidence must be `high` (not just `medium`) before
   the nominal is written automatically.
3. Manual Voltage configurations (`base_authority=manual`) already require engineer confirmation
   and are not affected.
4. The PU-001 fix (Convention A/B in `auto_base_evidence.py`) correctly resolves 275.0 kV
   (high confidence, no ambiguity). The PULU case is safe.

### 6.3 Existing test coverage

`backend/tests/test_slice5d2_auto_base_service.py` includes `test_manual_authority_preserved`
and `test_legacy_authority_preserved` which verify that existing manual configurations are not
overwritten. These tests must remain green.

---

## 7. Recommended implementation slices and acceptance criteria

### Slice 6A — Replace Convention A/B with multi-hypothesis resolver (backend)
**Scope:** Replace `_is_near_standard_nominal_kv` logic in `auto_base_evidence.py` Step 3b
and Step 4 with calls to `evaluate_voltage_hypotheses()` from `voltage_hypothesis.py`.
**Acceptance criteria:**
- 68/68 existing `test_auto_base_evidence.py` tests pass.
- 49/49 `test_voltage_hypothesis.py` tests pass.
- Full backend suite exit 0.
- Owner reviews PULU recording result with group_name corroboration.
**Risk:** Low. The common cases (275 kV, 76.2 kV) are identical. The 132 kV case becomes
more conservative (ambiguous without name token) — the owner must decide whether this is
acceptable or whether group_name population is required.

### Slice 6B — Voltage-only display selector (frontend)
**Scope:** Add `kind === "current"` early-return in `wwErChannelUnitDisplay()`. Update toggle
label text. Verify Calculated Current PU traces are not suppressed.
**Acceptance criteria:**
- ENG/PU toggle applies only to Voltage traces.
- Current traces remain A/kA in both modes.
- Existing Calculated Channel Current PU traces (if any) remain visible.
- No regression in browser tests.
**Risk:** Low. Single-function change.

### Slice 6C — Current PU dependency audit and documentation
**Scope:** Verify all 12 dependency areas in §3 against the Voltage-only change.
Write targeted tests for any boundary cases.
**Acceptance criteria:**
- Each dependency classified as preserve/adapt/retire.
- No unintended behavioral change confirmed by tests.

### Slice 6D — Multi-hypothesis regression guard (auto-base service)
**Scope:** Add a guard in `auto_base_service._configure_voltage_group()` that checks for linked
Current groups before writing `auto_resolved` Voltage nominals. Require `confidence=high` when
a Current equipment-rating link exists.
**Acceptance criteria:**
- New test: Voltage group with linked Current group equipment rating → auto_resolved only when
  confidence=high.
- New test: ambiguous Voltage nominal → `needs_review` even when no other reason to block.

---

## 8. Test counts (this session)

| Test file | Tests | Status |
|---|---|---|
| `test_auto_base_evidence.py` | 68 | 68/68 pass |
| `test_voltage_hypothesis.py` (new, PU-001B prototype) | 49 | 49/49 pass |
| `test_slice5d2_auto_base_service.py` | 10 | 10/10 pass |
| `test_slice5d3_auto_pu_display.py` | 23 | 23/23 pass |
| `test_per_unit_voltage_reference_safety.py` | 33 | 33/33 pass |
| Targeted suite (5 files) | 135 | 135/135 pass |
| Full backend suite | ~11,780+ | exit 0 |

---

## 9. Files changed this session

| File | Type | Description |
|---|---|---|
| `backend/app/domain/auto_base_evidence.py` | Modified | PU-001: Convention A/B disambiguation |
| `backend/tests/test_auto_base_evidence.py` | Modified | +9 PU-001 regression tests |
| `frontend/index.html` | Modified | PU-001: "Nominal Voltage:" + `.toFixed(2)` |
| `docs/project-memory/HANDOFF.md` | Modified | PU-001 fix recorded |
| `docs/project-memory/DECISIONS.md` | Modified | +DEC-212 |
| `backend/app/domain/voltage_hypothesis.py` | New | PU-001B prototype |
| `backend/tests/test_voltage_hypothesis.py` | New | 49 decision-matrix tests |
| `docs/project-memory/PU_001B_PU_002A_DESIGN.md` | New | This document |

---

## 10. Stop condition

This document represents the engineering design, prototype verification, and dependency
assessment as requested in the PU-001B + PU-002A task statement. Implementation has NOT been
promoted to the live resolvers.

The owner should review:
1. DEC-212 (§1) — confirm the policy is correctly stated.
2. The 132 kV ambiguity finding (§2.4 Finding 3) — confirm acceptable to require group_name
   for 132 kV L-G disambiguation, or request a different resolution policy.
3. The Voltage-only display plan (§4) — confirm the `kind` filter approach is acceptable.
4. The Current normalization design (§5) — confirm the reference types and Primary/Secondary
   semantics match the intended product.
5. The recommended implementation slices (§7) — authorize Slice 6A, 6B, 6C, 6D in order.

No push, merge, or deployment until the owner approves.
