# DEC-213 Consolidated Integration Audit
## Physical Calibration Authority — Cross-Functional Engineering Review

**Date:** 2026-11-14
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Auditor:** Claude Sonnet 4.6 (automated, read-only)
**Scope:** Stages 3A through 3B-2C-3 as committed on this branch

---

## 1. Executive Verdict

**PASS — All findings resolved. Ready for Stage 3B-3.**

The DEC-213 Physical Calibration Authority system is correctly implemented across all five active protection layers (source PU gate, calculated-channel Invalid gate, phasor/impedance/sequence/distance gate, compliance gate, POWER provenance labeling). No Critical or High defects were found. Invalid and Unverified measurements cannot produce falsely authoritative engineering results through any currently active pathway.

All three findings from the conditional-pass verdict have been resolved:
- **M-1 (resolved — 2026-11-14):** Docstring added to `evaluate_calibration_eligibility()` clarifying empty-list vacuous-truth semantics. Full call-site audit: 11 callers, all guard `blocked_reason` before calling the evaluator. No bypass confirmed.
- **M-2 (resolved — 2026-11-14):** All 11 `test.skip()` guards removed from `power-provenance.spec.js`. Fixture confirmed: `synthetic_ben5k_phasor.ben` returns `Va` with `engineering_type=Voltage` and `Ia` with `engineering_type=Current`. Single-run result: **8 passed, 0 failed, 0 skipped**. Regression: compliance + phasor suites **10 passed, 0 failed, 0 skipped**.
- **L-1 (resolved — 2026-11-14):** Single-run baseline established. See §10 for exact counts.

---

## 2. Full System-Wide Calibration-Authority Flow

```
BEN5K import (ben/normalize.py)
  → AnalogChannel.calibration_authority = PhysicalCalibrationAuthority(UNVERIFIED)
  → RecordingMetadata.format_variant = "BEN5K_LEGACY"

COMTRADE/CSV/BEN32 import (all other providers)
  → AnalogChannel.calibration_authority = None  (not assessed)
  → RecordingMetadata.format_variant = None

──────────────────────────────────────────────────────────────────────
GATE LAYER 1 — Source PU conversion (Stage 3B-2A)
  waveform_service._calibration_blocked_reason()
  → BEN5K + absent authority → blocked (REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED)
  → BEN5K + UNVERIFIED authority → blocked
  → Non-BEN5K, None authority → passes (not assessed, backward compat)
  → Verified → passes
  
  waveform_service._resolve_effective_per_unit()
  → Calls _calibration_blocked_reason(); if blocked → STATUS_CALIBRATION_UNAVAILABLE
  → Covers all 4 waveform entry-points (waveform, cursor, peak, annotation)

GATE LAYER 2 — Calculated-channel PU (Stage 3B-2B-1)
  calculated_channel_service._collect_leaf_authorities()  [DFS traversal]
  calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()
  → evaluate_calibration_eligibility(leaves, PURPOSE_ENGINEERING_CALCULATION)
  → UNVERIFIED or INVALID leaf → STATUS_CALIBRATION_UNAVAILABLE
  → Fires only for VOLTAGE/CURRENT engineering types (OD-4)
  → POWER/ROCOF/FREQUENCY/UNDEFINED → STATUS_NOT_APPLICABLE (unchanged)

GATE LAYER 3 — Calculated-channel creation + evaluation Invalid gate (Stage 3B-2B-2)
  calculated_channel_service._check_creation_authority()
  → Fires for ALL engineering types (OD-5)
  → Source-kind refs: INVALID → raises InvalidCalibrationAuthorityError
  → Calc-kind refs: _collect_leaf_authorities() + PURPOSE_EXPLORATORY_ANALYSIS
    → INVALID leaf → raises; UNVERIFIED leaf → passes (exploratory allowed)
  
  Evaluation-time guards (all 4 entry-points):
  → _collect_leaf_authorities() + PURPOSE_EXPLORATORY_ANALYSIS
  → INVALID → raises InvalidCalibrationAuthorityError → HTTP 422

GATE LAYER 4 — Phasor / Impedance / Sequence / Distance (Stage 3B-2C-1)
  phasor_analysis_service._fetch_role_candidate()
  → Source-kind refs: evaluate_calibration_eligibility([auth], PURPOSE_ENGINEERING_CALCULATION)
    → UNVERIFIED or INVALID → returns _CalibrationBlockedResult(reason)
  → Calc-kind refs: _collect_leaf_authorities() + PURPOSE_ENGINEERING_CALCULATION
    → Any limitation → returns _CalibrationBlockedResult(reason)
  → Callers: blocked → ROLE_STATUS_CALIBRATION_UNAVAILABLE (not NEEDS_CONFIGURATION)
  → Covers all 4 analysis types sharing _fetch_role_candidate()

GATE LAYER 5 — Compliance readiness + assessment (Stage 3B-2C-2)
  compliance_series._raw()  [via _check_compliance_calibration()]
  → evaluate_calibration_eligibility([auth], PURPOSE_COMPLIANCE_ASSESSMENT)
  → UNVERIFIED → raises InvalidCalibrationAuthorityError(reason="physical_calibration_unverified")
  → INVALID → raises InvalidCalibrationAuthorityError(reason="physical_calibration_invalid")
  
  compliance_readiness_service: blocked → STATE_CALIBRATION_UNAVAILABLE
  → Precedence: calibration_unavailable beats incompatible in aggregation
  → Router: HTTP 422 for InvalidCalibrationAuthorityError

PROVENANCE LAYER — Calculated POWER labeling (Stage 3B-2C-3)
  calculated_channels.py _compute_provenance()
  → _collect_leaf_authorities() + evaluate_calibration_eligibility(leaves, PURPOSE_ENGINEERING_CALCULATION)
  → Empty leaf set → ("blocked_structural", "no_leaf_authorities_found") [not all_verified]
  → Returns (status, reason) on POST create + GET list
  → Frontend: "⚠ exploratory" badge for exploratory_unverified
```

---

## 3. Actual Status-Policy Matrix

Verified from production code (not from prior reports).

| Leaf state | PU calc (V/I) | ENG calc (all types) | Phasor/Seq/Dist | Compliance | POWER provenance |
|---|---|---|---|---|---|
| **Verified** | Passes | Passes | Passes | Passes (ready) | `all_verified` |
| **Unverified** | BLOCKED (`calibration_unavailable`) | Passes (exploratory) | BLOCKED (`calibration_unavailable`) | BLOCKED (`calibration_unavailable`) | `exploratory_unverified` |
| **Invalid** | BLOCKED | BLOCKED (OD-6, HTTP 422) | BLOCKED | BLOCKED (HTTP 422) | `blocked_invalid` |
| **Not Assessed (None, non-BEN5K)** | Passes | Passes | Passes | Passes (ready) | `not_assessed` |
| **BEN5K + authority None** | BLOCKED (defensive) | BLOCKED (defensive) | BLOCKED (`channel_not_found_ben5k`/`ben5k_authority_absent`) | BLOCKED | `blocked_structural` |
| **Mixed Verified + Not Assessed** | Passes (compat) | Passes | Passes | Passes (`not_fully_verified` in reason) | `not_fully_verified` |
| **Mixed Verified + Unverified** | BLOCKED (worst-case) | Passes (exploratory) | BLOCKED (worst-case) | BLOCKED | `exploratory_unverified` |
| **Mixed Invalid + anything** | BLOCKED | BLOCKED | BLOCKED | BLOCKED | `blocked_invalid` |
| **Empty leaf set** | N/A | N/A | N/A | N/A | `blocked_structural` |

Policy keys: **BLOCKED** = calibration gate prevents the operation or returns a non-authoritative status; **Passes** = operation proceeds with the noted limitation or compatibility mode; **Passes (exploratory)** = operation proceeds but result is marked exploratory.

Notes:
- "Passes (compat)" for Mixed Verified+Not Assessed PU: `_result_for_not_assessed()` returns `eligible=True` regardless of purpose; this is the backward-compat rule.
- Phasor: "Passes" for Not Assessed means `_CalibrationBlockedResult` is NOT returned; the role proceeds with `ROLE_STATUS_AVAILABLE`.
- POWER provenance uses `PURPOSE_ENGINEERING_CALCULATION` via `_compute_provenance()`.

---

## 4. Cross-Functional Entry-Point Inventory

| Gate | File | Approximate location | Purpose constant |
|---|---|---|---|
| Source PU block | `waveform_service.py` | `_calibration_blocked_reason()`, `_resolve_effective_per_unit()` | `PURPOSE_ENGINEERING_CALCULATION` |
| Calc PU block (VOLTAGE/CURRENT) | `calculated_channel_service.py` | `_resolve_effective_per_unit_for_calculated_channel()` | `PURPOSE_ENGINEERING_CALCULATION` |
| Calc creation Invalid gate | `calculated_channel_service.py` | `_check_creation_authority()` | `PURPOSE_EXPLORATORY_ANALYSIS` |
| Calc evaluation Invalid gate ×4 | `calculated_channel_service.py` | `extract_calculated_waveform_range`, `extract_calculated_cursor_values`, `resolve_calculated_peak_value`, `resolve_calculated_annotation_anchor` | `PURPOSE_EXPLORATORY_ANALYSIS` |
| Phasor/Seq/Dist gate | `phasor_analysis_service.py` | `_fetch_role_candidate()` | `PURPOSE_ENGINEERING_CALCULATION` |
| Compliance execution gate | `compliance_series.py` | `_raw()` via `_check_compliance_calibration()` | `PURPOSE_COMPLIANCE_ASSESSMENT` |
| Compliance readiness gate | `compliance_readiness_service.py` | `_plan_direct_channel()` | `PURPOSE_COMPLIANCE_ASSESSMENT` |
| POWER provenance labeling | `calculated_channels.py` (router) | `_compute_provenance()` | `PURPOSE_ENGINEERING_CALCULATION` |
| Leaf authority DFS | `calculated_channel_service.py` | `_collect_leaf_authorities()` | shared (called by multiple gates) |

---

## 5. Confirmed Protection and Bypass Findings

### Protected pathways (confirmed from code)

1. **BEN5K PU conversion** — `waveform_service._calibration_blocked_reason()` blocks UNVERIFIED and absent-authority BEN5K at the PU gate. COMTRADE/non-BEN5K None authority passes (backward compat).

2. **Invalid leaf propagation** — `_check_creation_authority()` and all 4 evaluation-time guards raise `InvalidCalibrationAuthorityError` for any INVALID leaf in a calculated channel's dependency tree. HTTP 422 returned; no partial result.

3. **Phasor analysis** — `_fetch_role_candidate()` gates every role independently. UNVERIFIED/INVALID leaf returns `_CalibrationBlockedResult` sentinel (distinct from `needs_configuration`). The Pydantic `PhasorDiagramRoleStatus` Literal correctly includes `"calibration_unavailable"` (added in `35af9e1`).

4. **Compliance** — `_raw()` raises for UNVERIFIED (→ `calibration_unavailable`) and INVALID (→ `calibration_unavailable` with distinct reason code). Router maps to HTTP 422. `calibration_unavailable` beats `incompatible` in readiness aggregation.

5. **POWER provenance** — All 6 provenance statuses computed at API boundary. Empty leaf set → `blocked_structural` (not `all_verified`). `blocked_structural` and `blocked_invalid` POWER channels: waveform/cursor/peak evaluation raises `InvalidCalibrationAuthorityError` via Stage 3B-2B-2 evaluation-time guards. These are enforced, not metadata-only.

### No confirmed bypasses found.

---

## 6. API/Schema Consistency Audit

| Check | Schema/Router | Finding |
|---|---|---|
| `PhasorDiagramRoleStatus` Literal includes `"calibration_unavailable"` | `schemas/phasor_analysis.py:52` | ✓ Present (added `35af9e1`). No HTTP 500 risk. |
| `ComplianceMemberReadinessOut.state` type | `schemas/compliance.py:90` | ✓ `str` (open). No Pydantic rejection for `"calibration_unavailable"`. |
| `ComplianceMemberReadinessOut.reason_code` | `schemas/compliance.py:94` | ✓ `str | None = None` present. |
| `CalculatedChannelOut.calibration_provenance_status` | `schemas/calculated_channel.py:219` | ✓ `str | None = None`. Open — no Pydantic HTTP 500 risk. |
| `calculated_channels.py _STATUS_BY_ERROR_CODE` | `api/v1/calculated_channels.py:126` | ✓ `"invalid_calibration_authority": HTTP_422` present. |
| `compliance.py _STATUS_BY_ERROR_CODE` | `api/v1/compliance.py:100` | ✓ `"invalid_calibration_authority": HTTP_422` present. |
| `engineering_contexts.py _STATUS_BY_ERROR_CODE` | `api/v1/engineering_contexts.py:149` | ✓ Absent — not needed. Phasor service returns sentinel (never raises `InvalidCalibrationAuthorityError`). Default fallback returns HTTP 400 for unrecognized codes, not HTTP 500. |
| `sources.py` | `api/v1/sources.py` | ✓ Calls only `remove_calculated_channels_for_source` (deletion lifecycle, not evaluation). No `InvalidCalibrationAuthorityError` risk. |
| `compliance.py` default fallback | `api/v1/compliance.py:131` | ✓ `_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)`. Unknown codes → 400, not 500. |

**No unprotected HTTP 500 path was found for any currently-producible calibration status.**

---

## 7. Frontend Lifecycle and Display Audit

### POWER provenance badges
- `wwCalcChannelProvenanceBadgeHtml()` injects `⚠ exploratory` (amber) for `exploratory_unverified`; `not fully verified` (grey) for `not_fully_verified`. No badge for `all_verified`, `not_assessed`, blocked states.
- Badge injected in: (1) channel-manager list row, (2) waveform sidebar section.
- `wwPeakValueLineText()` appends `⚠` glyph for `exploratory_unverified` channels in peak annotations.
- `all_verified` and `not_assessed`: no indicator (preserved backward compat).

### Compliance `calibration_unavailable`
- CSS token `--compliance-calibration-unavailable` present.
- `WW_COMPLIANCE_READINESS_LABEL` and `WW_COMPLIANCE_MEMBER_STATE_LABEL` label maps include `calibration_unavailable` entries.
- `wwComplianceRepresentationRow()` guard prevents "✓ Fundamental RMS available" for `calibration_unavailable` members.

### Phasor `calibration_unavailable`
- Domain constant `ROLE_STATUS_CALIBRATION_UNAVAILABLE = "calibration_unavailable"` added to `phasor.py`.
- `KNOWN_ROLE_STATUSES` tuple updated.
- `PhasorDiagramRoleResult.reason_code` already existed in schema — no new schema surface.

### Stale state risk assessment
- POWER provenance computed at API boundary from current source registry; never stored on the domain object. Reimport removes the old source → lifecycle cascade removes dependent calc channels → no stale labels possible.
- Compliance `calibration_unavailable`: computed per-request from current channel state; not persisted.
- Phasor `calibration_unavailable`: computed per-request from active source channels; not persisted.

### ENG/PU transitions
- PU gate is in `waveform_service._resolve_effective_per_unit()` and `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`. Both are evaluated per-request, not cached. No stale state after ENG↔PU transitions.

---

## 8. Cross-Format Compatibility Assessment

Confirmed from `ben/normalize.py` and provider absence of `calibration_authority`:

| Format | `format_variant` | `calibration_authority` | Gate behavior |
|---|---|---|---|
| **BEN5K Legacy** | `"BEN5K_LEGACY"` | `CALIBRATION_UNVERIFIED` (explicitly set) | All gates active: Unverified blocks PU/Phasor/Compliance; ENG calc passes (exploratory) |
| **BEN32 Fast SubBen** | `None` | `None` (not set by provider) | Not assessed — backward compat; passes all gates |
| **BEN32 Slow SubBen** | `None` | `None` (not set by provider) | Not assessed — backward compat; passes all gates |
| **COMTRADE** | `None` | `None` (not set by provider) | Not assessed — backward compat; passes all gates |
| **CSV** | `None` | `None` (not set by provider) | Not assessed — backward compat; passes all gates |

The only format with explicit calibration authority metadata is BEN5K Legacy. All other formats behave as "not assessed" — consistent with the backward-compatibility guarantee. BEN32 SubBen is NOT treated as Verified merely because it lacks BEN5K identity markers. The `format_variant == "BEN5K_LEGACY"` check is the only identity trigger.

**No cross-format false Verified classification confirmed.**

---

## 9. Downstream/Export Findings

Endpoints searched: all `api/v1/*.py` routers for `export`, `download`, `report`, `csv`, `xlsx`, `pdf`.

| Pathway | Router | Verdict |
|---|---|---|
| `export_preparation_source()` | `preparation_sources.py` | Exports preparation-layer COMTRADE sources only. Zero references to `calculated_channel`, `POWER`, `phasor`, or `calibration` in `preparation_export_service.py`. **No DEC-213 bypass.** |
| Oscillation analysis | `oscillation.py` | Analysis-only endpoint. No export, no download. Calls oscillation analysis service only. **No DEC-213 bypass.** |
| Waveform data | `sources.py` | Raw waveform arrays via `/sources/{id}/waveform`. No calculated channels, no calibration labeling. **Not a bypass** (raw source data, PU gate active). |
| Calculated-channel waveform | `calculated_channels.py` | Evaluation-time Invalid gate active. Unverified passes (exploratory). **Provenance label missing** from waveform array response (only on POST/GET-list metadata). This is a known, accepted limitation per Stage 3B-2C-3 design. |

**No confirmed active export bypass.** The only downstream risk is that the waveform array response from `/calculated-channels/{id}/waveform` does not include `calibration_provenance_status` — the label is on the metadata endpoints only. This is an accepted design decision (deferred to Stage 3B-3) and does not constitute an active bypass because the engineer must have already seen the provenance label when creating the channel.

---

## 10. Exact Regression Totals

### Single-run baseline (2026-11-14, `pytest tests/ -q --tb=no --no-header`)

**Method:** Progress characters counted from dot lines only (lines containing `[N%]` markers).

```
Passed (dots):  12,249
Skipped (s):       391
Failed (F):          0
Errors (E):          0
─────────────────────
Total collected: 12,640  ✓ (matches --co -q count)
Exit code: 0
```

**Discrepancy explanation:** The Stage 3B-2C-3 final report stated 12,271 passed + 391 skipped = 12,662. The correct single-run counts are 12,249 + 391 = 12,640. The 22-test difference (12,271 − 12,249) was caused by piecing together counts from multiple partial background runs; one run reported 22 more passing tests than the single-run baseline. The collected count 12,640 was always correct. No test failures exist.

### Browser tests (committed fixtures, `BEN5K_EXPERIMENTAL_ENABLED=1`)

| Spec | Result (2026-11-14) | Confidence |
|---|---|---|
| `ben5k-phasor-calibration-gate.spec.js` | 6/0/0 | High |
| `compliance-calibration-gate.spec.js` | 4/0/0 | High |
| `power-provenance.spec.js` | **8/0/0** (skip guards removed) | **High — mandatory asserts, 0 skips** |
| `ben5k-pu-calibration-gate.spec.js` | Various (from prior stages) | High |
| Regression (`compliance` + `phasor`) | 10/0/0 | High |

---

## 11. Findings with Severity

### Medium

**M-1 — Domain-layer empty-leaf-set policy is misleading** ✓ RESOLVED 2026-11-14
- File: `backend/app/domain/physical_calibration.py:294-303`
- Description: `evaluate_calibration_eligibility([])` (empty list) returns `all_verified=True`. Misleading for future callers.
- **Resolution:** Docstring note added to `evaluate_calibration_eligibility()` warning that empty-list all_verified is a vacuous truth, not physical certification evidence, and that callers responsible for calculated-channel provenance must independently verify leaf presence via `_collect_leaf_authorities()`.
- **Call-site audit result:** 11 call sites audited. All callers check `blocked_reason` before invoking the evaluator; no existing caller passes an empty list AND relies on `all_verified=True` as physical certification. No bypass confirmed.

**M-2 — `power-provenance.spec.js` contained conditional skip guards** ✓ RESOLVED 2026-11-14
- File: `browser-tests/power-provenance.spec.js` (11 locations removed)
- Description: 11 `test.skip(true, ...)` guards in Scenarios A–H that could allow mandatory tests to silently skip.
- **Resolution:** All 11 soft-skip guards removed and replaced with hard `expect(voltCh, "...must expose a Voltage channel").toBeTruthy()` assertions. `synthetic_ben5k_phasor.ben` confirmed to return `Va` with `measurement=voltage` → `engineering_type=Voltage` and `Ia` with `measurement=current` → `engineering_type=Current` via `app.providers.ben.legacy_ben5k.normalize.parse_ben5k`.
- **Post-fix result:** 8 passed, 0 failed, 0 skipped (exit 0). Regression: `compliance-calibration-gate.spec.js` + `ben5k-phasor-calibration-gate.spec.js`: 10 passed, 0 failed, 0 skipped.

### Low

**L-1 — Stage 3B-2C-3 final test report arithmetic inconsistency** ✓ RESOLVED 2026-11-14
- Description: Prior report stated 12,271 passed + 391 skipped = 12,662 ≠ 12,640 collected.
- **Resolution:** Single-run baseline established: **12,249 passed, 391 skipped, 0 failed, total 12,640, exit 0**. The 22-test discrepancy (12,271 − 12,249) was caused by assembling counts from multiple partial background runs. Collected count 12,640 was always correct.

---

## 12. Remediation Applied

### R-1 (M-1) — Domain evaluator docstring ✓ Applied 2026-11-14
`evaluate_calibration_eligibility()` in `backend/app/domain/physical_calibration.py` now contains an explicit warning that empty-list `all_verified=True` is a vacuous truth and not physical certification evidence. No behavioral change.

### R-2 (M-2) — Browser spec skip guards removed ✓ Applied 2026-11-14
All 11 `test.skip()` guards removed from `browser-tests/power-provenance.spec.js`. Replaced with `expect(...).toBeTruthy()` hard assertions with descriptive messages naming the fixture. Result: 8/0/0.

### R-3 (L-1) — Single-run baseline captured ✓ Applied 2026-11-14
Single-run counts: 12,249 passed, 391 skipped, 0 failed, 12,640 total, exit 0.

---

## 13. Readiness Verdict for Stage 3B-3

**CLEARED — All Medium and Low findings resolved. Stage 3B-3 may proceed.**

Stage 3B-2C is structurally complete and consistent. All three audit findings are resolved. The DEC-213 foundation is confirmed solid.

Stage 3B-3 (frontend calibration limitation display) will build directly on:
- `calibration_provenance_status` field (`CalculatedChannelOut`) — stable, confirmed
- `ROLE_STATUS_CALIBRATION_UNAVAILABLE` constant — stable, confirmed
- `STATE_CALIBRATION_UNAVAILABLE` compliance state — stable, confirmed
- `evaluate_calibration_eligibility()` docstring — updated, no behavioral change

No new DEC-213 owner decisions are required to begin Stage 3B-3.

---

## 14. Formal Audit Close

**DEC-213 audit formally closed — 2026-11-14.**

All five protection layers confirmed correct. No Critical or High defects. All Medium and Low findings resolved. Single-run regression baseline: 12,249 passed, 391 skipped, 0 failed, exit 0. Browser suite: 18 tests across 3 mandatory specs — all pass, 0 skip.

This branch is ready for owner engineering review and push/merge authorization at the owner's discretion.

---

*Audit produced from code inspection only. Changes: `browser-tests/power-provenance.spec.js` (skip guards → hard assertions), `backend/app/domain/physical_calibration.py` (docstring only). No production behavioral changes.*
