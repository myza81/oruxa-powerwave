# Stage 3B-2B-2 — Engineering Review Report
# Invalid Calibration Authority Gate for Calculated Channels (DEC-213)
# 2026-11-12

---

## 1. Modified-file inventory

**New:**
- `backend/tests/test_invalid_calibration_calculated_channel_gate.py` — 23 test cases

**Modified (implementation):**
- `backend/app/services/errors.py`
  - Added `InvalidCalibrationAuthorityError` (new service error class, ~25 lines)
- `backend/app/services/calculated_channel_service.py`
  - Added `CALIBRATION_INVALID` and `PURPOSE_EXPLORATORY_ANALYSIS` to imports
  - Added `InvalidCalibrationAuthorityError` to imports from `errors`
  - Added `_check_creation_authority()` function (~80 lines)
  - Injected `_check_creation_authority()` call in `create_calculated_channel()` (8 lines)
  - Added evaluation-time guard (~25 lines each) to all 4 entry-points:
    `extract_calculated_waveform_range`, `extract_calculated_cursor_values`,
    `resolve_calculated_peak_value`, `resolve_calculated_annotation_anchor`
- `backend/app/api/v1/calculated_channels.py`
  - Added `InvalidCalibrationAuthorityError` to imports
  - Added `"invalid_calibration_authority": status.HTTP_422_UNPROCESSABLE_ENTITY` to `_STATUS_BY_ERROR_CODE`
  - Wrapped all 4 evaluation service calls in `try/except ImportServiceError`

---

## 2. Creation-time enforcement behavior

`_check_creation_authority()` is called in `create_calculated_channel()` after the
name-duplicate check and before the first `_resolve_input()` call.

**OD-5 (strict):** fires for ALL engineering types — VOLTAGE, CURRENT, POWER,
FREQUENCY, ROCOF, UNDEFINED. No OD-4 exception.

For each input ref:

**`ref.kind == "source"`:**
- Source not found in registry → skip (let `_resolve_input()` raise `SourceNotFoundError`).
- BEN5K source, channel absent from `analog_channels` → `InvalidCalibrationAuthorityError(reason="channel_not_found_ben5k")`.
- Non-BEN5K, channel absent → skip (not-assessed backward compat).
- BEN5K, authority is None → `InvalidCalibrationAuthorityError(reason="ben5k_authority_absent")`.
- Non-BEN5K, authority is None → skip (not-assessed backward compat).
- Authority found with `status == CALIBRATION_INVALID` → `InvalidCalibrationAuthorityError(reason=authority.reason)`.

**`ref.kind == "calculated"`:**
- Calc channel not found → skip (let `_resolve_input()` raise `CalculatedChannelNotFoundError`).
- Found → call `_collect_leaf_authorities()` on the referenced calc channel.
- If `blocked_reason` → `InvalidCalibrationAuthorityError(reason=blocked_reason)`.
- Run `evaluate_calibration_eligibility([leaves], PURPOSE_EXPLORATORY_ANALYSIS)`.
- If `not eligible` → `InvalidCalibrationAuthorityError(reason=eligibility.reason)`.

**Passes:** Unverified, Not Assessed (backward compat), Verified.

---

## 3. Evaluation-time enforcement behavior

Each of the 4 evaluation entry-points now has an evaluation-time guard that fires
unconditionally (both ENG and PU mode) when `source_registry`, `workspace_id`,
and `calc_registry` are all non-None:

```python
if source_registry is not None and workspace_id is not None and calc_registry is not None:
    _leaf = _collect_leaf_authorities(channel, ...)
    if _leaf.blocked_reason is not None:
        raise InvalidCalibrationAuthorityError(...)
    _elig = evaluate_calibration_eligibility([...], PURPOSE_EXPLORATORY_ANALYSIS)
    if not _elig.eligible:
        raise InvalidCalibrationAuthorityError(...)
```

The None-guard preserves backward compat for existing service-layer tests that
call these functions without registries. Production router callers always supply
all three, so the guard fires in all production evaluation paths.

The Stage 3B-2B-1 PU gate inside `_resolve_effective_per_unit_for_calculated_channel()`
is preserved unchanged — it handles Unverified on the PU path (OD-4 scope, 
PURPOSE_ENGINEERING_CALCULATION). Stage 3B-2B-2's evaluation-time gate uses
PURPOSE_EXPLORATORY_ANALYSIS and is orthogonal.

---

## 4. HTTP error codes and response schemas

**Creation-time:** HTTP 422 Unprocessable Entity (OD-7, explicitly approved).

**Evaluation-time:** HTTP 422 Unprocessable Entity.

Rationale for 422 on evaluation: there are no existing HTTP 409 responses in
this router's `_STATUS_BY_ERROR_CODE` table. All existing validation errors use
400/404/500. HTTP 422 was explicitly approved for creation (OD-7); using the
same code for evaluation is consistent and avoids introducing a new HTTP status
tier (409) that has no existing usage precedent in this codebase.

**Response schema** (unchanged `ErrorOut`):
```json
{
  "code": "invalid_calibration_authority",
  "message": "Channel 'VA' has an explicitly Invalid physical calibration authority..."
}
```

The `InvalidCalibrationAuthorityError` also carries `reason` (machine-readable
reason string from `evaluate_calibration_eligibility()` or traversal) and
optional `input_ref` (channel name or calc channel id), available to callers
but not in the HTTP response body.

---

## 5. Dependency-resolution reuse

`_collect_leaf_authorities()` from Stage 3B-2B-1 is reused without modification
for BOTH creation-time and evaluation-time gates. No second DFS implementation
was introduced.

- **Creation-time gate** (`_check_creation_authority()`): calls `_collect_leaf_authorities()`
  only for `calc`-kind input refs. Source-kind refs are handled inline (direct
  authority read), which is simpler and doesn't require a full leaf traversal
  for a single source channel.

- **Evaluation-time gate** (all 4 entry-points): calls `_collect_leaf_authorities()`
  on the full channel, same as Stage 3B-2B-1's PU gate. The two gates (creation,
  evaluation) use `PURPOSE_EXPLORATORY_ANALYSIS`; Stage 3B-2B-1 uses
  `PURPOSE_ENGINEERING_CALCULATION`. All three reuse the same traversal.

---

## 6. Numerical regression findings

**BEN5K Unverified (not Invalid):** ENG values are unchanged. Stage 3B-2B-2 uses
`PURPOSE_EXPLORATORY_ANALYSIS` which allows Unverified. The Unverified source
passes both creation and evaluation gates, and ENG mode never applies PU
conversion — numerical output is identical to pre-Stage 3B-2B-2.

**COMTRADE Not Assessed:** ENG values are unchanged. Not Assessed (None authority)
passes all gates via `_result_for_not_assessed()`.

**Verified sources:** ENG values are unchanged. All gates pass.

---

## 7. Frontend compatibility findings

The new `"invalid_calibration_authority"` error code and HTTP 422 require frontend
handling at two points:

1. **Calculated-channel creation (POST):** The existing error display for creation
   failures (e.g., `incompatible_time_base`, `invalid_operation_arity`) handles
   any `{code, message}` from an API error body. HTTP 422 is a new status code
   in this router; the frontend should handle it like 400 (display error message
   to user). If the frontend currently only handles 400 as a "creation failed"
   path, it may need a check for 422.

2. **Evaluation endpoints (waveform/cursor/peak/annotation):** These endpoints
   previously never raised structured service errors. The frontend currently
   treats any 2xx from these as success. HTTP 422 from an evaluation endpoint
   is new; the frontend needs to handle it and show an appropriate error rather
   than treating the response as a valid waveform result.

   Both are frontend-only scope changes — no service behavior change is needed.
   The API shape (`{code, message}`) matches existing error responses.

---

## 8. Test results (exact counts)

| Suite | Tests | Result |
|-------|-------|--------|
| `test_invalid_calibration_calculated_channel_gate.py` (new) | 23 | PASS |
| `test_ben5k_calculated_channel_pu_gate.py` (Stage 3B-2B-1) | 30 | PASS |
| `test_ben5k_pu_calibration_gate.py` (Stage 3B-2A) | 46 | PASS |
| `test_calculated_channel_service.py` | 94 | PASS |
| `test_calculated_group_aware_per_unit.py` | 42 | PASS |
| `test_per_unit_eligibility_integration.py` + `test_per_unit_numeric_integrity.py` + `test_per_unit_provenance_api.py` | 248 | PASS |
| `test_per_unit_reference_policy.py` + `test_per_unit_reference_safety.py` + `test_per_unit_voltage_reference_safety.py` | 92 | PASS |
| `test_per_unit_api.py` + `test_per_unit_registry.py` + `test_per_unit_domain.py` + other PU suites | 200 | PASS |
| **Full backend/tests/ suite** | **ALL PASS (exit 0)** | **PASS** |
| Browser (Stage 3B-2A + 3B-2B-1 regressions) | 7 | PASS |

---

## 9. Remaining limitations

### Stage 3B-2C, 3B-3, Slice 6D — not activated

No calibration correction factors (√2/16 or any numerical gain), new PU bases,
phasor/power compliance enforcement, or scope-3B-3/Slice 6D code was added.
Stage 3B-2B-2 is a gate-only change.

### "Mark-as-Invalid" API — not yet implemented

The evaluation-time guard is already in place for a future "mark-as-Invalid"
API that would update an existing source's calibration authority after the fact.
Currently, an Invalid authority is only applied at import time (or created
synthetically in tests). Once a "mark-as-Invalid" API exists, any stale
calculated channel whose source is then marked Invalid will correctly raise
`InvalidCalibrationAuthorityError` on next evaluation.

### Cascading lifecycle (reimport)

The existing `remove_calculated_channels_for_source()` cascade correctly handles
reimport: removing the old source removes all calc channels that referenced it,
and a fresh import creates a new `source_id`. No stale Invalid authority state
persists after reimport.

### COMTRADE/CSV backward compat

Not Assessed (None authority) on non-BEN5K sources passes both gates unchanged.
Existing COMTRADE and CSV calculated channels are unaffected.

---

## 10. Ready for owner review

No commit has been made. The branch is `feature/vlt-ref-001-voltage-reference-safety`.

Recommended review points:
1. **OD-5 strictness**: confirm all engineering types (POWER, FREQUENCY, ROCOF,
   UNDEFINED) are gated at creation time by reviewing `_check_creation_authority()`.
2. **Evaluation-time None-guard**: confirm the `source_registry is not None`
   condition is the correct backward-compat posture (existing tests that call
   evaluation functions without registries are unaffected).
3. **HTTP 422 for evaluation**: confirm this is acceptable or whether a different
   code is preferred for the evaluation-time path.
4. **Frontend impact**: confirm whether the frontend needs changes to handle HTTP
   422 from evaluation endpoints before this can be shipped.
5. **Test D (POWER creation)**: the POWER creation test uses a Voltage + Current
   pair where the Voltage input has Invalid authority. This exercises OD-5's
   "all engineering types" rule. The POWER channel itself has Invalid authority
   in its upstream source — the resulting calc channel (POWER output) would have
   been blocked at creation. Confirm this is the intended behavior.
