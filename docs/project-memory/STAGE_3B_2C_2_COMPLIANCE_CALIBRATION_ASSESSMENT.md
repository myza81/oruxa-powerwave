# Stage 3B-2C-2 — Compliance Calibration Gate
## Implementation Assessment (DEC-213)
## 2026-11-13

---

## 1. Scope

This document is a bounded implementation assessment for the Compliance
calibration gate (Stage 3B-2C, Slice 2C-2). It covers the ENG-mode data
path in `compliance_series._raw()`, the readiness evaluation path in
`compliance_readiness_service.evaluate_readiness()`, source/calc-kind
dependency resolution, Stage 3A eligibility, existing leaf-authority
resolver reuse, response schema design, frontend treatment, stale result
prevention, and backward compatibility.

**This is an assessment document only. No production code changes are
included. Do not implement until separately authorized.**

---

## 2. The two distinct compliance bypass paths

The original Stage 3B-2C architecture assessment (Section 1) confirmed two
separate unprotected code paths in Compliance:

| # | Path | What bypasses the gate | How output is used |
|---|------|------------------------|--------------------|
| C-1 | `compliance_series._raw()` / `load_series()` / `compliance_trace_service.build_measurement_traces()` | ENG-mode array read; no `calibration_authority` check for source-kind or calc-kind refs | Trace plotted against reference envelope |
| C-2 | `compliance_readiness_service.evaluate_readiness()` via `_plottable_problem()` → `unit_problem()` / `timebase_key()` → `_raw()` | Readiness verdict depends on `_raw()` returning non-None; no authority check | `ready` / `action_required` / `incompatible` verdict returned to frontend |

These are not duplicates. C-1 fires when a READY reference's traces are
fetched. C-2 fires earlier, during the readiness check that decides
whether the reference can be satisfied at all.

Both must be protected. The gate design for each is different.

---

## 3. Gate injection point — `_raw()`

`compliance_series._raw()` (line 78) is the single function called by
`load_series()`, `unit_problem()`, and `timebase_key()`. It has two
branches:

### 3.1 Source-kind branch (lines 100–122)

```python
active = reg.source.get(workspace_id, ref.source_id)
if active is None:
    return None
data = active.record.waveform_data           # <-- bypass: no authority check here
if ref.channel_name not in data.columns:
    return None
```

Gate must fire after `active is not None` and before the array read.

**Proposed injection:**

```python
active = reg.source.get(workspace_id, ref.source_id)
if active is None:
    return None
# --- STAGE 3B-2C-2 calibration gate ---
_meta = next(
    (ch for ch in active.record.analog_channels
     if ch.name == ref.channel_name),
    None
)
_is_ben5k = active.record.metadata.format_variant == FORMAT_VARIANT_BEN5K_LEGACY
if _meta is None and _is_ben5k:
    raise InvalidCalibrationAuthorityError(
        f"Channel '{ref.channel_name}' not found in BEN5K record.",
        reason="channel_not_found_ben5k",
    )
if _meta is not None:
    _auth = _meta.calibration_authority
    if _auth is None and _is_ben5k:
        raise InvalidCalibrationAuthorityError(
            f"Channel '{ref.channel_name}' has no calibration authority in BEN5K record.",
            reason="ben5k_authority_absent",
        )
    if _auth is not None:
        _elig = evaluate_calibration_eligibility(
            [_auth], PURPOSE_COMPLIANCE_ASSESSMENT
        )
        if not _elig.eligible:
            raise InvalidCalibrationAuthorityError(
                f"Channel '{ref.channel_name}' calibration is {_elig.reason}.",
                reason=_elig.reason,
            )
# --- end gate ---
data = active.record.waveform_data
```

### 3.2 Calculated-kind branch (lines 82–98)

```python
channel = get_calculated_result(workspace_id, ref.calculated_channel_id,
                                 source_registry=reg.source, calc_registry=reg.calc)
if channel is None:
    return None
# ... reads channel.time, channel.values directly — no authority check
```

Gate must fire after `channel is not None` and before the array read.

**Proposed injection:**

```python
channel = get_calculated_result(...)
if channel is None:
    return None
# --- STAGE 3B-2C-2 calibration gate ---
_leaf = _collect_leaf_authorities(
    channel,
    workspace_id=workspace_id,
    source_registry=reg.source,
    calc_registry=reg.calc,
)
if _leaf.blocked_reason is not None:
    raise InvalidCalibrationAuthorityError(
        f"Calculated channel '{channel.name}' depends on a blocked source.",
        reason=_leaf.blocked_reason,
    )
_elig2 = evaluate_calibration_eligibility(
    [a for a in _leaf.authorities if a is not None],
    PURPOSE_COMPLIANCE_ASSESSMENT,
)
if not _elig2.eligible:
    raise InvalidCalibrationAuthorityError(
        f"Calculated channel '{channel.name}' calibration is {_elig2.reason}.",
        reason=_elig2.reason,
    )
# --- end gate ---
```

### 3.3 Why raise, not return None

`_raw()` returning `None` means "channel not found". Callers (e.g.
`load_series()`) treat `None` as a soft failure and produce a reason string
(not an exception), which is included in `result.skipped` with a 200 OK
response.

A calibration block must NOT be a soft-404. It must distinguish
"calibration prevented this assessment" from "the channel was deleted" so
the frontend can show the right message and the engineer knows what action
to take.

Raising `InvalidCalibrationAuthorityError` (already defined in
`services/errors.py`) achieves this cleanly:
- Callers that catch it can propagate a structured block signal.
- Callers that don't catch it bubble it to the API layer.

---

## 4. Gate propagation through `evaluate_readiness()`

`evaluate_readiness()` calls `_plottable_problem()` → `unit_problem()` /
`timebase_key()` → `_raw()`. These are structured to return strings (not
raise), so if `_raw()` raises, it escapes through these wrapper functions
up into `evaluate_readiness()`.

There are two design options:

### Option A — Catch at `_plan_direct_channel()` level (preferred)

Add a `try/except InvalidCalibrationAuthorityError` in
`_plan_direct_channel()` around the `unit_problem()` / `timebase_key()`
calls. Translate the exception into a new member state
`STATE_CALIBRATION_UNAVAILABLE`. Propagate this state up through
`_plan_reference_layer()` → `evaluate_readiness()` to set reference status
`"calibration_unavailable"` and overall status `"calibration_unavailable"`.

This is the minimum surface change: one catch site in the readiness service,
no changes to the domain functions.

### Option B — Change return type of `unit_problem()` / `timebase_key()`

Extend `unit_problem()` and `timebase_key()` to catch
`InvalidCalibrationAuthorityError` and return a distinguishable error token.
More invasive; not preferred for this stage.

**Recommendation: Option A.** One catch per channel evaluation path in
`_plan_direct_channel()`, same pattern as Stage 3B-2C-1's
`_CalibrationBlockedResult` sentinel.

---

## 5. Stage 3A calibration eligibility

`PURPOSE_COMPLIANCE_ASSESSMENT` already exists in
`backend/app/domain/physical_calibration.py` (line 85):

```python
PURPOSE_COMPLIANCE_ASSESSMENT = CalibrationPurpose(
    name="compliance_assessment",
    requires_verified=True,         # Unverified blocks compliance
    requires_not_invalid=True,      # Invalid blocks compliance
)
```

This is exactly the purpose to use in the gate. `evaluate_calibration_eligibility([auth], PURPOSE_COMPLIANCE_ASSESSMENT)` will:

- **Verified** → eligible (gate passes)
- **Unverified** → not eligible (gate blocks; `reason = "calibration_unverified"`)
- **Invalid** → not eligible (gate blocks; `reason = "calibration_invalid"`)
- **None (Not Assessed)** → eligible via `_result_for_not_assessed()` (backward compat; passes)

No change to the domain is needed.

---

## 6. Dependency-leaf authority resolver reuse

`_collect_leaf_authorities()` from `calculated_channel_service.py` is
already used by Stage 3B-2B-1 and 3B-2B-2. It performs a DFS from the
calculated channel to its source-kind leaf channels, collecting
`calibration_authority` from each BEN5K leaf and detecting cycles.

**Reuse strategy for Stage 3B-2C-2:**

| Call site | Input | Usage |
|-----------|-------|-------|
| `_raw()` calc-kind branch | `channel` (a `CalculatedChannelResult`) | Full DFS to leaves; then `evaluate_calibration_eligibility(leaves, PURPOSE_COMPLIANCE_ASSESSMENT)` |
| `_plan_direct_channel()` source-kind ref | Direct `active.record.analog_channels[i].calibration_authority` | Direct read; no DFS needed (single source channel) |
| `_plan_direct_channel()` calc-kind ref | The calc channel | Calls `_collect_leaf_authorities()` once; delegates to `_raw()` gate internally |

The compliance service does not need its own DFS. `_collect_leaf_authorities()` is imported from `calculated_channel_service` and called without modification. Exact same call signature as Stage 3B-2B-2.

**Import note**: `_collect_leaf_authorities` is a module-private function
(`_` prefix). The same import pattern used in Stage 3B-2B-2 (direct import
within the same package) applies here. If the function is ever promoted to
a public helper (e.g., moved to a shared `calibration_utils` module), that
refactor is out of scope for 3B-2C-2.

---

## 7. The critical distinction: "unavailable" vs "assessed and failed"

The owner requirement: **"distinguish 'Compliance could not be assessed
because calibration is unavailable' from 'Compliance was assessed and
failed.'"**

The existing three readiness states are:

| State | Meaning |
|-------|---------|
| `ready` | All required channels can be satisfied. |
| `action_required` | Recording can satisfy; a preparation step is missing. |
| `incompatible` | Recording CANNOT satisfy this reference (structural impossibility — missing phase, angle-less RMS, ambiguous metadata). |

**`incompatible` does NOT mean "calibration unavailable."**

Using `incompatible` for calibration blocks (as OD-10(a) originally
phrased) would conflate two distinct conditions:

- Structural incompatibility: the recording's signal content cannot
  satisfy the reference regardless of calibration status. The engineer
  cannot fix this by improving calibration — the measurement is wrong.
- Calibration unavailability: the signal content MIGHT satisfy the
  reference, but calibration evidence is insufficient for a compliance
  verdict. The engineer CAN fix this by obtaining verified calibration.

These require different engineer actions. Using the same status prevents
correct diagnosis.

### 7.1 New status: `calibration_unavailable`

Stage 3B-2C-2 must introduce a **new status value**:

| Status | Meaning | Engineer action |
|--------|---------|-----------------|
| `calibration_unavailable` | Channel calibration status prevents compliance assessment. The recording may contain the required signal, but no verified calibration evidence exists. | Obtain verified calibration for the BEN5K recording, then re-assess. |

This applies to:
- `ComplianceReferenceReadinessOut.status` (per-reference)
- `ComplianceReadinessOut.status` (overall result)
- `ComplianceMeasurementReadinessOut.status` (measurement-level, if present)

### 7.2 New member state: `calibration_unavailable`

`ComplianceMemberReadinessOut.state` also needs a new value:

| State | Meaning |
|-------|---------|
| `calibration_unavailable` | This member channel's calibration prevents compliance assessment. |

This is analogous to `blocked` (which means "cannot be prepared here") but
for a different reason: calibration, not preparation.

### 7.3 New reason code field on member readiness

Currently `ComplianceMemberReadinessOut` has no `reason_code` field. Add:

```python
reason_code: str | None = None
```

to carry the machine-readable reason (e.g. `"calibration_unverified"`,
`"calibration_invalid"`, `"channel_not_found_ben5k"`). Same pattern as
`PhasorDiagramRoleResult.reason_code` added in Stage 3B-2C-1.

---

## 8. Response schema changes

All compliance status fields in `backend/app/schemas/compliance.py` are
`str`, not `Literal`. **There is no Pydantic serialization gap risk** —
no HTTP 500 will occur when a new status string is returned. This was
confirmed by reading the schema file in full.

Fields requiring documentation (not code change — but add to schema
docstrings for clarity):

| Schema | Field | Current known values | New value |
|--------|-------|----------------------|-----------|
| `ComplianceReadinessOut` | `status: str` | `ready`, `action_required`, `incompatible`, `no_reference` | `calibration_unavailable` |
| `ComplianceReferenceReadinessOut` | `status: str` | same | `calibration_unavailable` |
| `ComplianceMemberReadinessOut` | `state: str` | `source_rms`, `reused`, `needs_rms`, `needs_line_to_line`, `derived_at_assessment`, `blocked`, `incompatible` | `calibration_unavailable` |
| `ComplianceMemberReadinessOut` | `reason_code` | (field absent) | **NEW FIELD** `str \| None = None` |

No existing field values change. The API is additive.

**`compliance.py` API router**: `_STATUS_BY_ERROR_CODE` does not contain
`"invalid_calibration_authority"`. When `_raw()` raises
`InvalidCalibrationAuthorityError` and it propagates to the trace endpoint,
the existing `except ImportServiceError as exc: raise _http_error(exc)`
pattern will return HTTP 500 (the base `ImportServiceError` handler maps to
500 by default). This must be fixed:

```python
"invalid_calibration_authority": status.HTTP_422_UNPROCESSABLE_ENTITY,
```

Add this to `_STATUS_BY_ERROR_CODE` in `backend/app/api/v1/compliance.py`.

Alternatively, if `evaluate_readiness()` catches the exception and returns
`calibration_unavailable` status (Option A from Section 4), the trace
endpoint never receives this exception for READY references (traces are
only fetched for READY references), so the HTTP 500 risk only exists if a
race condition exposes a channel between readiness and trace fetch, or if
the trace endpoint is called without first checking readiness.

**Recommendation:** Add the mapping defensively regardless, so the API
never returns HTTP 500 for a calibration block.

---

## 9. Frontend treatment

### 9.1 Current state

The frontend compliance panel renders two maps:

**`WW_COMPLIANCE_READINESS_LABEL`** (line 54407 in `index.html`):
```js
{
    ready: "✓ Ready for assessment",
    action_required: "⚠ Action required",
    incompatible: "✕ Measurement cannot satisfy this reference",
    no_reference: "Add a Reference Layer to define what must be assessed.",
}
```

**`WW_COMPLIANCE_MEMBER_STATE_LABEL`** (line 54414):
```js
{
    source_rms: "source RMS channel used directly",
    reused: "existing RMS calculated channel reused",
    needs_rms: "fundamental RMS needs preparation",
    needs_line_to_line: "line-to-line voltage + RMS need preparation",
    derived_at_assessment: "derived from instantaneous phases at assessment",
    blocked: "cannot be prepared here",
    incompatible: "cannot be satisfied",
}
```

**CSS status classes** (lines 7211–7213):
```css
.ww-compliance-readiness-status--ready { color: #2f7a46; }
.ww-compliance-readiness-status--action_required { color: #a86a00; }
.ww-compliance-readiness-status--incompatible { color: #a33; }
```

**`wwComplianceRepresentationRow()`** (line 54501) checks for
`needs_rms`, `needs_line_to_line`, and `blocked` by name. A
`calibration_unavailable` member state falls through to the final
"✓ Fundamental RMS available" message — **this would be misleading**.

### 9.2 Required frontend changes (not in scope for 3B-2C-2 implementation — record here for the frontend implementation story)

1. **Add `calibration_unavailable` to `WW_COMPLIANCE_READINESS_LABEL`:**
   ```js
   calibration_unavailable: "⚠ Calibration required for compliance assessment",
   ```

2. **Add `calibration_unavailable` to `WW_COMPLIANCE_MEMBER_STATE_LABEL`:**
   ```js
   calibration_unavailable: "calibration status prevents compliance assessment",
   ```

3. **Add CSS rule for the new status:**
   ```css
   .ww-compliance-readiness-status--calibration_unavailable { color: #a86a00; }
   ```
   (Same warning orange as `action_required` — it is a resolvable condition,
   not a permanent incompatibility.)

4. **Guard `wwComplianceRepresentationRow()`** to handle `calibration_unavailable`
   as a blocking state (like `blocked`), not silently fall through.

5. **Status label fallback** (line 54584):
   `WW_COMPLIANCE_READINESS_LABEL[result.status] || result.status`
   currently falls back to the raw string if the key is missing. Without
   change (1) above, a `calibration_unavailable` status displays as the
   raw string `"calibration_unavailable"` — not ideal but non-crashing.

**Minimum safe behavior without frontend changes:** A new backend that
returns `calibration_unavailable` on the existing frontend will render:
- Status text: raw string `"calibration_unavailable"` (no label, no icon)
- Status CSS: `ww-compliance-readiness-status--calibration_unavailable`
  (no color — inherits default text color)
- Member: raw string for state label
- Representation row: misleading "Fundamental RMS available" message if
  the member state is `calibration_unavailable`

Frontend changes are **required before shipping** Stage 3B-2C-2 to avoid
misleading UX. They can be delivered in the same commit as the backend
gate.

### 9.3 No structural JS safety risk

Unlike the `PhasorDiagramRoleStatus` Literal gap in Stage 3B-2C-1 (which
caused HTTP 500), compliance schemas use plain `str` throughout — there is
no serialization failure. The frontend renders degraded UX but does not
crash or receive 500s.

---

## 10. Stale result prevention

### 10.1 Readiness stale cache

`evaluate_readiness()` has no internal cache — it is computed fresh on
every call. The API route calls it synchronously. No stale result risk
from the backend side.

The frontend fetches readiness via `GET .../compliance/voltage/readiness`
and stores the result in `wwComplianceState.readiness`. The frontend
re-fetches readiness:
- On measurement group selection
- After `prepare_measurement()` completes

If a BEN5K source is added to a workspace whose compliance readiness was
already computed, the frontend must re-fetch readiness. Existing
re-fetch logic (on group change) covers this. No additional invalidation
is needed from the backend.

### 10.2 Trace stale cache

`build_measurement_traces()` is called only for READY references. If the
calibration gate causes `calibration_unavailable` on the readiness check,
traces will not be fetched. No stale trace risk.

**Potential race condition:** If the frontend has cached `ready` status
and then the backend's `_raw()` gate raises `InvalidCalibrationAuthorityError`
during a trace fetch, the API would return HTTP 422. The frontend's current
trace error handling converts HTTP errors to a user-visible message via
`wwRefFetchJson` (throws, caught by `wwComplianceRefreshTraces`). The
engineer will see an error notification but the existing trace result
(already cached from a prior fetch) is not automatically cleared. This is
acceptable — the engineer can re-fetch by re-selecting the measurement group.

No additional stale-state machinery is needed for the initial gate
implementation.

---

## 11. Backward compatibility for Not Assessed sources (COMTRADE/CSV)

The gate uses `evaluate_calibration_eligibility([auth], PURPOSE_COMPLIANCE_ASSESSMENT)`.

For a Not Assessed source (COMTRADE, CSV, non-BEN5K BEN), `calibration_authority is None`.
`_result_for_not_assessed()` in `physical_calibration.py` returns `eligible=True` for all purposes.

**All existing COMTRADE and CSV compliance analyses are unaffected.** The
gate fires only when `calibration_authority is not None` and the authority's
status is `Unverified` or `Invalid`. Not Assessed sources pass the gate
unconditionally.

For BEN5K sources:
- `calibration_authority is None` on a BEN5K channel → `ben5k_authority_absent`
  → gate blocks (consistent with Stage 3B-2A/3B-2B/3B-2C-1 policy of treating
  missing authority on a BEN5K channel as a fail-closed condition)
- `calibration_authority.status == CALIBRATION_VERIFIED` → gate passes
- `calibration_authority.status == CALIBRATION_UNVERIFIED` → gate blocks
  (OD-10a approved)
- `calibration_authority.status == CALIBRATION_INVALID` → gate blocks
  (OD-11 approved)

---

## 12. OD-10 / OD-11 alignment

The existing OD-10(a) recommendation in the Stage 3B-2C assessment stated:
"Block: report compliance readiness as `incompatible` for that member."

**This assessment clarifies that OD-10(a) must NOT use `incompatible`.**
Reusing `incompatible` for calibration blocks conflates two distinct
conditions with different engineer actions (see Section 7). The correct
implementation of OD-10(a) is to introduce `calibration_unavailable` as a
new, distinct status.

This does not change the owner's intent — OD-10(a) says "block" and
"calibration unavailability" is an `incompatible`-class outcome in the
sense that "you cannot proceed to a compliance verdict." The distinction
matters for the UI message and engineer action, not the high-level
"you cannot assess compliance" outcome.

Similarly, OD-11's "block entirely" should produce `calibration_unavailable`
(not `incompatible`) with `reason_code = "calibration_invalid"` on the
member that is Invalid.

---

## 13. API contract summary

### GET `.../compliance/voltage/readiness` and POST `.../compliance/voltage/prepare`

| Scenario | Current behavior | With Stage 3B-2C-2 gate |
|----------|-----------------|--------------------------|
| COMTRADE/CSV source | `ready` / `action_required` / `incompatible` as before | Unchanged |
| BEN5K Verified | (would compute normally) | `ready` / `action_required` / `incompatible` as normal |
| BEN5K Unverified (OD-10a) | Bypasses gate; computes normally | `calibration_unavailable` per affected member/reference |
| BEN5K Invalid (OD-11) | Bypasses gate; computes normally | `calibration_unavailable` per affected member/reference |
| BEN5K, channel missing | Silently returns `None` from `_raw()`; treated as missing | `calibration_unavailable` with `reason_code="channel_not_found_ben5k"` |
| Calc channel over BEN5K Unverified | Computes; Stage 3B-2B-2 allows Unverified at EXPLORATORY level | `calibration_unavailable` (compliance uses `PURPOSE_COMPLIANCE_ASSESSMENT` which blocks Unverified) |

### GET `.../compliance/voltage/measurement-traces/{id}`

| Scenario | Behavior |
|----------|----------|
| Reference is READY | Traces fetched normally (Verified or Not Assessed source) |
| Reference is `calibration_unavailable` | Traces not fetched (reference is not READY; `build_measurement_traces` skips non-READY references) |
| Race: readiness cached as READY but `_raw()` raises during trace fetch | HTTP 422 (`invalid_calibration_authority`) from the trace endpoint |

---

## 14. Files requiring change

The following file list is bounded — do not expand scope without owner approval.

**Backend (production — 3 files):**

1. `backend/app/services/compliance_series.py`
   - Add imports: `FORMAT_VARIANT_BEN5K_LEGACY`, `evaluate_calibration_eligibility`,
     `PURPOSE_COMPLIANCE_ASSESSMENT`, `InvalidCalibrationAuthorityError`,
     `_collect_leaf_authorities`
   - In `_raw()` source-kind branch: add calibration gate (after `active is not None`)
   - In `_raw()` calc-kind branch: add calibration gate (after `channel is not None`)

2. `backend/app/services/compliance_readiness_service.py`
   - Add `STATE_CALIBRATION_UNAVAILABLE = "calibration_unavailable"` constant
   - In `_plan_direct_channel()`: add `try/except InvalidCalibrationAuthorityError`
     around `unit_problem()` / `timebase_key()` calls → return member with
     `state=STATE_CALIBRATION_UNAVAILABLE, reason_code=exc.reason`
   - In `_plan_reference_layer()`: propagate `calibration_unavailable` member state
     to reference status
   - In `evaluate_readiness()` / `ReadinessResult` construction: propagate
     `calibration_unavailable` reference to overall status

3. `backend/app/api/v1/compliance.py`
   - Add `"invalid_calibration_authority": status.HTTP_422_UNPROCESSABLE_ENTITY`
     to `_STATUS_BY_ERROR_CODE`

**Backend (schemas — 1 file):**

4. `backend/app/schemas/compliance.py`
   - Add `reason_code: str | None = None` to `ComplianceMemberReadinessOut`
   - (Optional) Add docstring comments listing new known status/state values

**Backend (tests — 1 new file):**

5. `backend/tests/test_compliance_calibration_gate.py` (new)
   - Unit tests for `_raw()` gate: source-kind (Unverified, Invalid, BEN5K missing,
     Verified passes, Not Assessed passes)
   - Unit tests for `evaluate_readiness()` calibration propagation:
     BEN5K Unverified member → `calibration_unavailable` reference status → overall
     `calibration_unavailable`
   - Serialization test: `GET .../readiness` returns
     `{"status": "calibration_unavailable", ...}` without HTTP 500
   - Backward compat tests: COMTRADE members unaffected; mixed BEN5K+COMTRADE
     group → only BEN5K member shows `calibration_unavailable`

**Frontend (1 file):**

6. `frontend/index.html`
   - Add `calibration_unavailable` to `WW_COMPLIANCE_READINESS_LABEL`
   - Add `calibration_unavailable` to `WW_COMPLIANCE_MEMBER_STATE_LABEL`
   - Add CSS rule `ww-compliance-readiness-status--calibration_unavailable`
   - Guard `wwComplianceRepresentationRow()` for `calibration_unavailable` state

**Browser tests (1 new file):**

7. `browser-tests/compliance-calibration-gate.spec.js` (new)
   - Mandatory scenario: COMTRADE source → compliance readiness is NOT
     `calibration_unavailable` (backward compat regression)
   - Mandatory scenario: synthetic BEN5K fixture → compliance readiness is
     `calibration_unavailable` with correct reason_code (gate fires)
   - Optional: real GPTH/Permas recordings (gated on env vars)

---

## 15. Implementation risk and size estimate

| Risk | Assessment |
|------|-----------|
| Pydantic HTTP 500 on new status | **None.** All compliance status fields are `str`, not `Literal`. Confirmed by reading `schemas/compliance.py` in full. |
| `_collect_leaf_authorities` import | **Low.** Same import used in Stage 3B-2B-2. No change to the function. |
| `_raw()` raises breaking existing callers | **Medium.** `load_series()` and `unit_problem()` currently expect `_raw()` to return `None` or a tuple, never raise. Each call site in the compliance services must be audited. The two key call sites are `_plan_direct_channel()` and `load_series()` / `build_measurement_traces()`. |
| Frontend renders misleading "✓ Fundamental RMS available" | **Certain without fix.** `wwComplianceRepresentationRow()` does not handle `calibration_unavailable` member state. Frontend fix MUST ship with backend gate. |
| `prepare_measurement()` HTTP 422 from Stage 3B-2B-2 Invalid gate | **Already present.** `create_calculated_channel()` raises for Invalid inputs. The `_STATUS_BY_ERROR_CODE` mapping in `compliance.py` missing `invalid_calibration_authority` causes HTTP 500 for this path today. The `_STATUS_BY_ERROR_CODE` fix is a **pre-existing defect** to fix immediately in Stage 3B-2C-2, not a new regression. |

**Size estimate:** 5–7 backend files (services, schema, API, 1 test), 1 frontend
file, 1 browser test file. Comparable in scope to Stage 3B-2C-1 (which was
4 production files + 3 test files). The compliance service change is slightly
more complex due to the `_plan_direct_channel()` / `_plan_reference_layer()`
propagation chain.

---

## 16. Owner decisions required before implementation

**No new unresolved decisions.** OD-10(a) and OD-11 were approved.
This assessment refines the implementation of OD-10(a) to use
`calibration_unavailable` rather than `incompatible` — this refines the
approved decision without reversing it, and aligns with the owner
requirement to distinguish calibration unavailability from compliance failure.

If the owner disagrees with the `calibration_unavailable` / `incompatible`
distinction described in Section 7, that must be resolved before implementation.

**One clarification item (no blocking):**

- **`prepare_measurement()` HTTP 422 on Invalid** (pre-existing defect):
  `create_calculated_channel()` can already raise `InvalidCalibrationAuthorityError`
  when a compliance preparation creates a calculated channel from an Invalid
  source. The `compliance.py` router has no handler for this code and returns
  HTTP 500 today. Stage 3B-2C-2 should fix this as part of the
  `_STATUS_BY_ERROR_CODE` update. Owner is informed — no decision required.

---

## 17. Governance compliance

- Stage 3B-2C-1, Stage 3B-2B-2, Stage 3B-2A, BEN, PULU commits: untouched.
- Stage 3B-2C-3, Stage 3B-3, Slice 6D: not started.
- BEN decoding and PU mathematics: not modified.
- Not committed. Not pushed. Not merged. Not deployed.

---

## 18. Implementation record — 2026-11-13

**Status: LOCAL IMPLEMENTATION COMPLETE — awaiting owner engineering review before commit.**

Governance: authorized under DEC-213 owner decisions OD-10(a) and OD-11.
Do NOT commit, push, merge or deploy without owner approval.

### 18.1 Files changed (working tree)

| File | Change |
|------|--------|
| `backend/app/services/compliance_series.py` | C-1 bypass closed: `_raw()` gates source-kind and calc-kind refs via `_check_compliance_calibration()` |
| `backend/app/services/compliance_readiness_service.py` | C-2 bypass closed: `_plan_direct_channel()` checks calibration before structural planning; `_evaluate_reference()` and `evaluate_readiness()` precedence corrected (calibration_unavailable beats incompatible per OD-10a); `MemberReadiness.reason_code` added |
| `backend/app/api/v1/compliance.py` | `_STATUS_BY_ERROR_CODE["invalid_calibration_authority"] = HTTP_422`; `reason_code` passed to output |
| `backend/app/schemas/compliance.py` | `reason_code: str \| None = None` on `ComplianceMemberReadinessOut` |
| `frontend/index.html` | CSS token `--compliance-calibration-unavailable`; label map entries for `calibration_unavailable` state; `wwComplianceRepresentationRow()` guard |

### 18.2 New test files

| File | Purpose |
|------|---------|
| `backend/tests/test_compliance_calibration_gate.py` | 39 tests: C-1/C-2 bypass closures, precedence, distinct reason codes, serialization round-trip, HTTP 422, OD-10 no-false-verdict |
| `backend/tests/fixtures/ben/synthetic_ben5k_compliance.ben` | 3-phase BEN5K fixture (VR/VY/VB, all CALIBRATION_UNVERIFIED); 3776 bytes |
| `browser-tests/compliance-calibration-gate.spec.js` | 4 browser tests: Scenarios A (COMTRADE compat), B (BEN5K → calibration_unavailable, 0 skips), C (UI smoke ×2) |

### 18.3 Test results

**Backend unit/integration tests (2026-11-13):**

| Suite | Result |
|-------|--------|
| `test_compliance_calibration_gate.py` | **39 passed, 0 failed, 0 skipped** |
| `test_compliance_readiness_api.py` + `test_compliance_measurement_api.py` | **46 passed, 0 failed, 0 skipped** |
| `test_phasor_calibration_gate.py` + `test_ben5k_pu_calibration_gate.py` + `test_ben5k_calculated_channel_pu_gate.py` + `test_invalid_calibration_calculated_channel_gate.py` | **120 passed, 0 failed, 0 skipped** |
| Full backend suite (excl. `test_ben_reference.py`) | **328 collected, exit 0 (0 failures)** |

**Browser tests (2026-11-13, `BEN5K_EXPERIMENTAL_ENABLED=1`):**

| Spec | Result |
|------|--------|
| `compliance-calibration-gate.spec.js` | **4 passed, 0 failed, 0 skipped** |
| `ben5k-phasor-calibration-gate.spec.js` | **6 passed, 0 failed, 0 skipped** |

### 18.4 Owner corrections applied

All 5 owner corrections from the DEC-213 review are addressed:

1. **Correction 1 (precedence)**: `calibration_unavailable` now beats `incompatible` in both `_evaluate_reference()` and `evaluate_readiness()`.
2. **Correction 2 (Scenario B no soft-skip)**: `synthetic_ben5k_compliance.ben` is 3-phase (VR/VY/VB) so auto-discovery always creates a voltage group; browser Scenario B asserts `>0` groups (hard failure, no skip).
3. **Correction 3 (distinct reason codes)**: Unverified → `physical_calibration_unverified`; Invalid → `physical_calibration_invalid`; missing BEN5K provenance → `ben5k_authority_absent` / `channel_not_found_ben5k`. No HTTP 500 for any calibration exception (all map to 422).
4. **Correction 4 (serialization tests)**: `TestFullReadinessRoundTrip`, `TestCalibrationExecutionPathHttp422`, `TestOD10NoFalseVerdict`, `TestDistinctReasonCodes`, `TestMixedMemberStatePrecedence` added.
5. **Correction 5 (regression suites)**: All specified suites run; results in §18.3.
