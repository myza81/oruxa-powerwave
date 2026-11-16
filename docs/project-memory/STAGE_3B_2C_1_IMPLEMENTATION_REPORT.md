# Stage 3B-2C-1 Implementation Report

**Date:** 2026-11-13
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Status:** Implementation and regression testing complete. NOT committed. Awaiting owner
commit approval.

---

## 1. Implementation summary

Stage 3B-2C-1 injects a single calibration eligibility gate into
`_fetch_role_candidate()` in `phasor_analysis_service.py`. This covers all four
phasor-based analysis types (Phasor Diagram, Impedance, Distance Protection, Sequence
Components) through one change point.

**Owner correction 1 — `_CalibrationBlockedResult` sentinel (OD-8/OD-9/OD-13):**
Before this correction, all calibration blocks returned `None`, identical to "role not
configured." Callers could not distinguish calibration unavailability from a missing role.
A typed sentinel `_CalibrationBlockedResult(reason: str)` is now returned for all
calibration-blocked code paths. Callers set `ROLE_STATUS_CALIBRATION_UNAVAILABLE`
(not `ROLE_STATUS_NEEDS_CONFIGURATION`) and propagate the machine-readable `reason`.

**Owner correction 2 — Epoch consistency regression (DEC-213 OD-8 regression fix):**
The prior implementation conditionally skipped the phasor-epoch assertion whenever
the BEN5K source was blocked. The test now actively asserts that BEN5K Unverified
returns `_CalibrationBlockedResult` (not a silently skipped `None`), AND adds a
separate test `test_phasor_epoch_consumer_not_assessed_source` that uploads a committed
COMTRADE fixture (not-assessed, passes gate) and executes the epoch consistency assertion
unconditionally.

---

## 2. Owner decisions honored

| OD   | Decision                                                              | Implementation                                                                                                       |
|------|-----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| OD-8 | Block authoritative phasor when source is Unverified                  | `evaluate_calibration_eligibility(PURPOSE_ENGINEERING_CALCULATION)` returns blocked → `_CalibrationBlockedResult`   |
| OD-9 | Block when source is Invalid                                          | Same path — `CALIBRATION_INVALID` fails `PURPOSE_ENGINEERING_CALCULATION` and `PURPOSE_EXPLORATORY_ANALYSIS` both   |
| OD-13 | Per-role blocking — eligible roles independently preserved            | Each role fetched independently; blocked role → sentinel; other roles unaffected                                     |
| OD-14 | Distance Protection needs engineering-calculation eligibility         | Inherited via `compute_phasor_diagram()` / `prepare_phasor_diagram()` — single gate covers all 4 analysis types      |

Additional owner decisions confirmed:
- BEN5K Verified sources pass the gate (existing analysis preserved).
- COMTRADE not-assessed (None authority) passes the gate (backward compat).
- BEN5K + channel missing from `record.analog_channels` → `channel_not_found_ben5k` (fail-closed).
- BEN5K + `calibration_authority is None` → `ben5k_authority_absent` (fail-closed, matches Stage 3B-2A).
- Genuinely unconfigured roles (source not in registry) continue to return `None` → `ROLE_STATUS_NEEDS_CONFIGURATION` — distinct from `calibration_unavailable`.

---

## 3. Files changed (not yet committed)

**Production code (3 files):**

- `backend/app/domain/phasor.py`
  - Added `ROLE_STATUS_CALIBRATION_UNAVAILABLE = "calibration_unavailable"` constant
  - Updated `KNOWN_ROLE_STATUSES` tuple to include the new status
  - `PhasorDiagramRoleResult.reason_code` already existed — no schema change required

- `backend/app/services/phasor_analysis_service.py`
  - Added `_CalibrationBlockedResult(reason: str)` frozen dataclass sentinel
  - Changed `_fetch_role_candidate()` return type to `_RoleCandidate | _CalibrationBlockedResult | None`
  - 5 calibration-block `return None` sites → `return _CalibrationBlockedResult(reason=...)`
  - `compute_phasor_analysis()`: sentinel → `reason_code="calibration_unavailable"` (distinct from `channel_unavailable`)
  - `prepare_phasor_diagram()`: sentinel → `role_statuses[role_key] = ROLE_STATUS_CALIBRATION_UNAVAILABLE`
  - `check_phasor_diagram_readiness()`: sentinel → `RoleReadiness(status=STATUS_NEEDS_CONFIGURATION, reason_code="calibration_unavailable")`

**Test code (3 files):**

- `backend/tests/test_phasor_calibration_gate.py` (modified — was 17 tests, now 19 tests with class Q)
  - All `assert result is None` for blocked cases changed to `assert isinstance(result, _CalibrationBlockedResult)`
  - `result.reason` asserted non-empty for all blocked cases
  - L/M: reason codes asserted exactly (`channel_not_found_ben5k`, `ben5k_authority_absent`)
  - New class Q (2 tests): genuinely unconfigured role → `None`, not `_CalibrationBlockedResult`
  - Module docstring and class docstrings updated to reflect sentinel semantics

- `backend/tests/test_time_reference_interpretation.py` (modified — was 27 tests, now 28 tests)
  - `test_every_epoch_consumer_uses_effective_time`: BEN5K assertion changed from conditional skip to
    `assert isinstance(_phasor_cand, _CalibrationBlockedResult)` with reason check
  - New test `test_phasor_epoch_consumer_not_assessed_source`: uploads COMTRADE `synth_ascii` fixture
    and executes `assert phasor_cand.start_epoch == epoch` unconditionally (original coverage restored)
  - Added `_FIXTURES_DIR`, `_upload_comtrade()` helper, `io` import

- `browser-tests/ben5k-phasor-calibration-gate.spec.js` (NEW — covers scenarios A/B/C–E/G–K)
  - Scenario K (COMTRADE not-assessed): always runs; asserts all roles `available` with no
    `calibration_unavailable` reason
  - Scenarios A/B/E/F–I (BEN5K blocked): skipped when neither `GPTH_BEN_PATH` nor `PERMAS_BEN_PATH`
    is set (matches existing `ben5k-physical-mapping.spec.js` gate convention)
  - Scenarios G/H/I (Impedance/Distance/Sequence COMTRADE passes): always runs as over-block regression
  - Scenarios C/D (Calc chain over BEN5K): gated on BEN5K env var; also handles HTTP 422 from
    Stage 3B-2B-2 as an acceptable "gate working" signal
  - UI smoke test: verifies phasor panel does not throw JS errors after upload

---

## 4. Test results

**New + modified backend tests:**

| File                                     | Tests | Result |
|------------------------------------------|-------|--------|
| test_phasor_calibration_gate.py          | 19    | 19 pass |
| test_time_reference_interpretation.py    | 28    | 28 pass |

**Targeted regression suites (all pass):**

| Suite / area                                              | Tests | Result |
|-----------------------------------------------------------|-------|--------|
| test_invalid_calibration_calculated_channel_gate.py       | 23    | 23 pass |
| test_phasor_analysis_api.py + test_phasor_domain.py       | 68    | 68 pass |
| test_phasor_diagram_api.py + test_phasor_diagram_service.py + test_phasor_analysis_service.py | 56 | 56 pass |
| PU + BEN key suites (5 files, see §5)                     | 228   | 228 pass |
| **Total targeted regression**                             | **422** | **422 pass** |

Full backend suite: **exit code 0** (confirmed — same 12 500+ test suite that passed at prior
stages; output summary line was buffered, exit code is authoritative). No failures.

**Browser tests:**
- `ben5k-phasor-calibration-gate.spec.js` (new): passes when COMTRADE fixture present (Scenario K, G/H/I
  COMTRADE branch, smoke test). BEN5K-gated scenarios (A/B/C–F) require owner .ben file.
- Existing phasor browser tests not modified.

---

## 5. Architecture note — sentinel size assessment

The `_CalibrationBlockedResult` dataclass is 2 lines of code plus a docstring. It satisfies
the owner requirement without a schema refactor:
- `PhasorDiagramRoleResult.reason_code: str | None = None` already existed — no Pydantic changes.
- `PhasorAnalysisResult.reason_code` and `role_reasons` already existed — no changes.
- `RoleReadiness.reason_code` already existed — no changes.
- HTTP response shapes are unchanged.
- The sentinel is an internal service implementation detail — it never leaves `phasor_analysis_service.py`.

The scope is exactly as estimated: smaller than a full schema refactor, larger than a one-line change.

---

## 6. Items NOT implemented (scope guardrails confirmed)

The following are explicitly not included in this stage:

- Stage 3B-2C-2 (compliance gateway)
- Stage 3B-2C-3 (POWER label for calibration-blocked analysis)
- Stage 3B-3 (BEN numerical calibration correction)
- Slice 6D
- BEN decoding, PU mathematics, or any numerical operations
- Phasor frontend rendering for `calibration_unavailable` state (not in OD-8 to OD-14 scope)
- Any change to COMTRADE, CSV, or Sub-BEN code paths
- Any modification to existing DEC-213 BEN, PULU, or Stage 3B-2B commits

---

## 7. Owner decisions required

None outstanding. All implementation decisions follow directly from OD-8/OD-9/OD-13/OD-14
and the two owner corrections. The sentinel mechanism was the minimum viable approach (no
alternatives require owner selection).

**Outstanding question on browser tests (for owner information, no decision required):**
The BEN5K-gated browser test scenarios A/B/C–F will produce 0 assertions when no owner .ben
file is set. The underlying behavior is fully covered by the backend unit tests (test_phasor_
calibration_gate.py classes A–Q). The browser tests serve as an end-to-end API layer check.
If the owner wants a synthetic BEN5K fixture committed for browser-level coverage without the
real .ben file, that can be added as a follow-up (committed synthetic .ben in `backend/tests/
fixtures/ben/`) — but this is not needed for commit approval.

---

## Governance compliance

- Not committed. Not pushed. Not merged. Not deployed.
- Stage 3B-2C-2, 3B-2C-3, Stage 3B-3, BEN numerical corrections, Slice 6D: not started.
- All prior DEC-213 BEN, PULU, and Stage 3B-2B commits preserved exactly.
- BEN decoding and PU mathematics not modified.
