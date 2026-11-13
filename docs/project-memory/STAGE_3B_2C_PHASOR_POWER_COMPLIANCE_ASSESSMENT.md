# Stage 3B-2C — Phasor, Power and Compliance Calibration Safeguards
## Architecture Assessment (DEC-213)
## 2026-11-12

---

## 1. Calculation-path inventory

This matrix covers every source-backed engineering calculation pathway
inspected. "Authority read?" means the function reads `calibration_authority`
or calls `evaluate_calibration_eligibility`. "Bypass?" means Unverified or
Invalid source data can reach the calculation without any gate.

| # | File / function | Input source type | Authority read? | Eligibility evaluated? | Bypass (Unverified)? | Bypass (Invalid)? | Output type in UI |
|---|-----------------|-------------------|-----------------|------------------------|----------------------|-------------------|-------------------|
| P-1 | `phasor_analysis_service._fetch_role_candidate()` (called by `compute_phasor_analysis`, `compute_phasor_diagram`, `prepare_phasor_diagram`, `check_phasor_diagram_readiness`) | recorded source or calculated channel | No | No | **YES** | **YES** | Authoritative (magnitude kV/kA, angle °) |
| P-2 | `impedance_analysis_service` (delegates to `compute_phasor_diagram` / `prepare_phasor_diagram`) | same as P-1 | No | No | **YES** | **YES** | Authoritative (Ω, R-X locus) |
| P-3 | `distance_protection_analysis_service` (delegates to `prepare_phasor_diagram`) | same as P-1 | No | No | **YES** | **YES** | Authoritative (Ω, relay-zone verdict) |
| P-4 | `sequence_components_analysis_service` (delegates to `compute_phasor_diagram`) | same as P-1 | No | No | **YES** | **YES** | Authoritative (V₁/V₂/V₀ kV, I₁/I₂/I₀ kA, ratio %) |
| C-1 | `compliance_series._raw()` / `load_series()` — ENG-mode path (`kV`/`V` unit) | recorded source or calculated channel | No | No (PU path goes through waveform_service gate) | **YES** | **YES** | Compliance trace plotted against reference |
| C-2 | `compliance_readiness_service.evaluate_readiness()` | recorded source or calculated channel | No | No | **YES** | **YES** | `ready` / `action_required` / `incompatible` verdict |
| W-1 | `waveform_service._resolve_effective_per_unit()` (PU path only) | recorded source | **YES** (Stage 3B-2A gate) | **YES** | Blocked (calibration_unavailable) | Blocked | PU: blocked → calibration_unavailable |
| W-2 | `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()` (PU, VOLTAGE/CURRENT only) | calculated channel | **YES** (Stage 3B-2B-1 gate) | **YES** | Blocked | Blocked | PU: blocked → calibration_unavailable |
| W-3 | `calculated_channel_service.create_calculated_channel()` (all types) | calculated channel | **YES** (Stage 3B-2B-2 gate, Invalid only) | **YES** | Allowed (Unverified permitted for exploratory) | Blocked → HTTP 422 | Creation rejected for Invalid |
| W-4 | `calculated_channel_service.extract_calculated_waveform_range` / cursor / peak / annotation (ENG+PU) | calculated channel | **YES** (Stage 3B-2B-2 gate, Invalid only) | **YES** | Allowed (Unverified permitted for exploratory) | Blocked → HTTP 422 | ENG values: Invalid blocked; Unverified allowed |
| K-1 | `calculator.py:compute_single_phase_power()` | **manual entry only** (no source linkage) | n/a | n/a | n/a — genuinely independent | n/a — genuinely independent | Exploratory calculator result (W/VAr/VA) |
| K-2 | `phasor_analysis_service.compute_phasor_manual_diagram()` | **manual entry only** (no source linkage) | n/a | n/a | n/a — genuinely independent | n/a — genuinely independent | Manual phasor result |

**Key finding:** All phasor-based analyses (P-1 through P-4) share the single
function `_fetch_role_candidate()` as their waveform-fetch entry point.
Injecting one calibration gate there protects all four analyses. No second
DFS implementation is required.

**Compliance (C-1, C-2):** The ENG-mode trace path in `compliance_series._raw()`
has no calibration gate. The PU path is indirectly protected (calls
`_resolve_effective_per_unit` which has the Stage 3B-2A/3B-2B-1/2B-2 gates).
An ENG-mode compliance trace from an Unverified or Invalid BEN5K source is
not blocked.

---

## 2. Source-backed vs manual calculator boundary

### Type A — inputs linked to recorded source channels

All phasor analyses in Recording mode: `compute_phasor_analysis`,
`compute_phasor_diagram` (and dependent Impedance, Distance, Sequence
services). Channels are fetched from `WorkspaceRegistry` / `CalculatedChannelRegistry`.
Source provenance is fully maintained in the `_RoleCandidate` struct
(which carries `reference_source_id` for time-axis alignment but does
NOT carry `calibration_authority`).

Compliance traces: source channels read via `compliance_series._raw()` from
`WorkspaceRegistry`. Provenance is not propagated beyond the array fetch.

BEN5K restrictions: **fully applicable**. These inputs flow from real
recorded waveforms and must respect calibration authority.

`_collect_leaf_authorities()` reuse: **yes**, for calc-kind role refs.
For source-kind role refs, the authority is read directly from
`active.record.analog_channels[i].calibration_authority`, same as Stage 3B-2A.

### Type B — manually entered numerical phasors / values

`compute_phasor_manual_diagram()` and `compute_single_phase_power()`:
no `WorkspaceRegistry`, no `source_registry`. Inputs are raw floats
supplied by the user. No recording provenance exists.

BEN5K restrictions: **not applicable**. These are genuinely independent
mathematical operations. Applying source-calibration restrictions to
user-typed numbers would be incorrect.

### Type C — calculated POWER channels derived from waveform sources

`OP_ACTIVE_POWER`, `OP_REACTIVE_POWER`, `OP_APPARENT_POWER`, and their
three-phase equivalents: inputs resolved via `_resolve_input()`, which
reads source/calc-channel arrays. Creation is now protected (Invalid
blocked by Stage 3B-2B-2). Evaluation ENG mode is protected for Invalid.
Unverified inputs are allowed for exploratory analysis.

Provenance: `_collect_leaf_authorities()` already traverses the full
input tree. For POWER channels, the leaf authorities from V and I inputs
are available at creation and evaluation time.

**Gap**: Unverified BEN5K → POWER calculated channel is currently allowed
(Unverified is permitted for exploratory analysis per OD-6). The resulting
MW/MVar/MVA time-series value is computed and displayed in engineering units
without any provenance label. Owner decision needed (OD-12).

### Type D — mixed pathways

`compliance_readiness_service.evaluate_readiness()` creates calculated
channels (RMS channels, L-L voltage channels) on behalf of compliance by
calling `create_calculated_channel()`. Those creation calls now have the
Stage 3B-2B-2 Invalid gate. If an Invalid-authority source underlies an
RMS channel needed for compliance, the creation of that RMS channel will
raise `InvalidCalibrationAuthorityError`. The compliance readiness service
will propagate this as an error from the creation call.

However: `compliance_readiness_service` does not independently check
calibration authority before deciding `ready` / `action_required` /
`incompatible`. An Unverified source channel used directly (STATE_SOURCE_RMS,
already-RMS channel) will be reported as `ready` for compliance without
any calibration qualifier.

---

## 3. Reuse assessment for `_collect_leaf_authorities()`

| Bypass | Gate location | `_collect_leaf_authorities()` reusable? | Extension needed |
|--------|--------------|----------------------------------------|-----------------|
| P-1 to P-4: source-kind role ref | `_fetch_role_candidate()`, lines ~163–176 | Partial — for `source-kind`, authority is read directly (single channel, no DFS needed); for `calc-kind`, the existing DFS is reused | None — same pattern as Stage 3B-2A for source, same as Stage 3B-2B-1 for calc |
| P-1 to P-4: calc-kind role ref | `_fetch_role_candidate()`, lines ~177–189 | **Yes, directly** — `_collect_leaf_authorities()` imported from `calculated_channel_service` and called on the resolved `CalculatedChannel` | None |
| C-1: compliance ENG trace | `compliance_series._raw()`, source-kind branch (~line 100–122) | Partial — for source-kind, direct authority read; for calc-kind, `_collect_leaf_authorities()` reusable | None |
| C-2: compliance readiness | `compliance_readiness_service.evaluate_readiness()` | Same as C-1 | None |

**Conclusion:** No new DFS implementation is needed for Stage 3B-2C.
`_collect_leaf_authorities()` is reused for calc-kind refs. Source-kind refs
use the same direct `calibration_authority` read pattern as Stage 3B-2A.

---

## 4. Policy recommendation (exploratory vs authoritative)

### P-1 to P-4: Phasor, Impedance, Sequence Components, Distance Protection

These services produce phasor magnitudes, angles, impedances, zone verdicts.
In the current UI they are presented without any "exploratory" qualifier —
they appear as engineering measurements.

**Recommended policy:**

- **Invalid authority → block entirely.** `_result_for_invalid` already
  blocks `PURPOSE_EXPLORATORY_ANALYSIS`. An Invalid-authority source must
  not contribute to any derived phasor-based quantity. Return `needs_configuration`
  with a machine-readable `reason_code = "calibration_invalid"` on the
  affected role(s).
- **Unverified authority:** owner decision required (OD-8). Two options:
  - **(a) Block at PURPOSE_ENGINEERING_CALCULATION** — treat phasor analysis
    as an authoritative engineering operation; return `needs_configuration`
    with `reason_code = "calibration_unverified"` for affected roles.
  - **(b) Permit at PURPOSE_EXPLORATORY_ANALYSIS** — allow phasor result
    to be computed but mark the affected role result with an
    `authority_status = "unverified"` field on the per-role output. This
    would require an API extension to `PhasorRoleResult` / `PhasorDiagramRoleResult`.

The engineering argument for (a): phasor magnitude and angle are the
direct basis for relay zone coordination and fault current magnitude
determination. Presenting Unverified values as plain engineering results
risks them being used in protection engineering decisions without the
limitation being visible. Option (a) is the more conservative and
recommended default.

The engineering argument for (b): BEN5K recordings of real disturbance
events have diagnostic value even when calibration is unverified. If phasor
analysis is completely blocked, engineers lose the ability to do exploratory
fault current investigation. Option (b) preserves this with a provenance
label.

**Distance Protection fault-loop impedance** (OD-14): this produces relay
zone verdicts directly. This should be treated as `PURPOSE_ENGINEERING_CALCULATION`
regardless of what is decided for Phasor display — a "Zone 2" verdict from
Unverified data must be explicitly blocked or labeled.

**Per-role vs whole-result gating** (OD-13): when only some roles have
Unverified/Invalid authority, the existing `compute_phasor_diagram()` model
is per-role (a missing role does not block other roles). The recommended
approach mirrors this: flag the affected role(s) rather than blocking the
entire diagram, except for whole-result-blocking conditions (conflicting
time-bases, etc.). OD-13 asks the owner to confirm this per-role posture.

### C-1 / C-2: Compliance traces and readiness

Compliance produces a comparison between a measured voltage trace and a
reference curve (DEC-169). A "ready" verdict with an Unverified source means
the reference comparison is performed on data whose absolute scaling is
unconfirmed.

**Recommended policy:**

- **Invalid authority → block.** `load_series()` for an Invalid-authority
  channel should raise `InvalidCalibrationAuthorityError` (same as Stage
  3B-2B-2 evaluation gate). The compliance readiness result for that
  member should report `incompatible` with a calibration reason.
- **Unverified authority:** owner decision required (OD-10). Two options:
  - **(a) Block: treat as `incompatible`** — a compliance verdict on
    Unverified data has no engineering validity.
  - **(b) Permit exploratory trace** — allow trace but add `authority_status`
    to the Series response so the frontend can annotate "Unverified source".

### Calculated-channel POWER with Unverified inputs

Currently: Unverified → POWER calculated channel is allowed (Stage 3B-2B-2
only blocks Invalid). The POWER values are computed and displayed.

The question (OD-12) is whether the UI must label these values as derived
from an Unverified source. The minimum acceptable approach is to add
`authority_status` or a provenance flag to the calculated-channel evaluation
response when the leaf authority traversal returns `has_unverified_leaves=True`.
This requires no numerical change.

---

## 5. API and frontend implications

### Phasor gate (P-1 to P-4)

**If Option (a) — block Unverified:**
No new API field needed. The existing `PhasorRoleResult.status = "needs_configuration"`
/ `reason_code = "calibration_unverified"` or `"calibration_invalid"` conveys
the limitation. The frontend already handles `needs_configuration` roles
(shows "not_eligible" or "missing" state). This requires no new API schema.

**If Option (b) — permit exploratory with provenance label:**
A new `authority_status: str | None` field is needed on `PhasorRoleResult` and
`PhasorDiagramRoleResult` schemas. The frontend needs to render a provenance
indicator on roles with `authority_status = "unverified"`. This is a minimal
API extension. Full UX improvements (badges, tooltips) are deferred to Stage 3B-3.

**For Invalid authority (both options):** the role returns
`status = "needs_configuration"`, `reason_code = "calibration_invalid"`.
No new schema field needed. Frontend already handles this.

### Compliance gate (C-1 / C-2)

**If block Invalid in ENG-mode trace:** raise `InvalidCalibrationAuthorityError`
from `load_series()`; map to HTTP 422 in the compliance API router. Frontend
compliance trace fetch needs to handle 422 (currently only handles 2xx
"series loaded" and 404 "source gone"). Minimal frontend fix: treat 422 as
"trace unavailable" and display a reason.

**If permit exploratory with label:** add `authority_status` to `Series`
dataclass and to the compliance trace API response. Frontend renders provenance
label on affected traces. Full UX deferred to Stage 3B-3.

### Calculated-channel POWER with Unverified (OD-12 resolution)

Add `has_unverified_leaves: bool` and `has_not_assessed_leaves: bool` to the
waveform evaluation response for calculated channels (or to the channel
state object the frontend polls). These are already available from
`CalibrationEligibility` returned by `evaluate_calibration_eligibility()`.
No new traversal needed — the evaluation-time guard already runs the
traversal; expose the flags. Frontend can annotate the POWER trace.

---

## 6. Performance assessment

### Phasor gate in `_fetch_role_candidate()`

`_fetch_role_candidate()` is called once per role per request (6 roles for
a full diagram). For source-kind refs: one `active.record.analog_channels`
linear scan (small list). For calc-kind refs: one `_collect_leaf_authorities()`
DFS call. The DFS is O(D × N) where D = tree depth and N = unique leaves —
typically 1–3 for real-world phasor inputs.

The gate fires once per role per request, not per sample. No per-sample
calibration check is introduced.

`_collect_leaf_authorities()` creates no caches and modifies no module-level
state. Each request gets a fresh traversal. This is correct because
calibration authority may change between re-imports.

**Conclusion:** No performance concern. The DFS cost is negligible relative
to the waveform fetch and DFT estimation in `estimate_phasor()`.

### `prepare_phasor_diagram()` optimization

`prepare_phasor_diagram()` (DEC-114) already separates the analysis-time-
independent preparation (role resolution, candidate fetch, waveform-form
eligibility) from per-time estimation. The calibration gate belongs in the
preparation phase — it fires ONCE per `prepare_phasor_diagram()` call, not
per `evaluate_prepared_phasor_diagram()` call. For Impedance Locus / Distance
Protection endpoints that call `prepare_phasor_diagram()` once and then
`evaluate_prepared_phasor_diagram()` N times, the gate cost is O(1) per
multi-time request, not O(N). This is the correct placement.

### Compliance gate

`compliance_series.load_series()` is called once per trace per compliance
readiness check. Adding a calibration check at the top of `_raw()` is
O(1) per channel (direct authority read for source-kind; `_collect_leaf_authorities()`
DFS for calc-kind). No performance concern.

---

## 7. Owner decisions needed (OD-8 onward)

**OD-8 — Phasor analysis: Unverified source policy**

For a phasor role backed by an Unverified (BEN5K) source or calculated
channel:

- **(a) Block:** return `needs_configuration` with `reason_code = "calibration_unverified"`.
  Phasor magnitude/angle not computed for affected roles.
- **(b) Permit exploratory:** compute phasor normally but add `authority_status = "unverified"`
  to the role result. Frontend labels the role.

Applies to all phasor-dependent analyses (Phasor, Impedance, Sequence
Components, Distance Protection).

Recommended: **(a)**, on the basis that phasor results are used for
engineering decisions (fault current, relay zone). This is consistent with
Stage 3A's `PURPOSE_ENGINEERING_CALCULATION` policy for Unverified.

---

**OD-9 — Phasor analysis: Invalid source policy**

For a phasor role backed by an Invalid authority source:

- Block the affected role: return `needs_configuration` with
  `reason_code = "calibration_invalid"`. Consistent with Stage 3B-2B-2.

This is the RECOMMENDED default. No owner approval needed if accepted as
the default — it is consistent with existing Invalid policy. If the owner
wants a different behavior (e.g., "allow raw waveform inspection but block
phasor"), confirm here.

---

**OD-10 — Compliance assessment: Unverified source policy**

For a compliance measurement member backed by an Unverified source:

- **(a) Block:** report compliance readiness as `incompatible` for that
  member (a physical compliance verdict on unverified data has no
  engineering validity).
- **(b) Permit exploratory trace:** compute and display the trace, add
  `authority_status = "unverified"` to the Series response.

Recommended: **(a)** for authoritative compliance verdicts; compliance
assessment is a `PURPOSE_COMPLIANCE_ASSESSMENT` operation, which
`_result_for_unverified` already blocks. If `(b)` is chosen for Compliance
displays, the distinction between "informational trace" and "compliance
verdict" must be clear in the UI.

---

**OD-11 — Compliance assessment: Invalid source policy**

For a compliance measurement member backed by an Invalid authority source:

- Block entirely: `load_series()` raises `InvalidCalibrationAuthorityError`
  → HTTP 422; compliance readiness returns `incompatible` with calibration reason.

This is consistent with Stage 3B-2B-2 and the domain policy. Confirm as default.

---

**OD-12 — Calculated-channel POWER with Unverified inputs: labeling required?**

Currently, Unverified BEN5K → POWER calculated channel is allowed
(exploratory). The MW/MVar/MVA time-series is computed and displayed in
engineering units.

- **(a) No change:** Unverified POWER output is acceptable as an exploratory
  engineering estimate. No labeling needed.
- **(b) Minimum labeling:** add `has_unverified_leaves` and
  `has_not_assessed_leaves` flags to the channel evaluation response. Frontend
  may render a "Unverified source" indicator. No numerical change.
- **(c) Block:** treat POWER calculations from Unverified inputs as
  `calibration_unavailable` (extend Stage 3B-2B-1 OD-4 to include POWER).

Recommended: **(b)** as a minimum. Option (c) would be a scope expansion
beyond Stage 3B-2C and requires a separate Stage 3B-2B-1 amendment.

---

**OD-13 — Per-role vs whole-result blocking for phasor diagram**

When ONE role in a 6-role phasor diagram has an Unverified/Invalid authority
and OD-8 selects block:

- **(a) Per-role block only:** affected role returns
  `needs_configuration`/calibration reason; other roles compute normally.
  (Mirrors the existing "one missing role does not block others" design.)
- **(b) Whole-diagram block:** all roles return `needs_configuration` if
  any role has a calibration limitation.

Recommended: **(a)** — consistent with existing per-role design. A partially-
computed diagram with clearly labeled "unavailable due to calibration" roles
is more useful than an entirely blocked diagram when only one phase has an
Unverified BEN5K source.

---

**OD-14 — Distance Protection fault-loop impedance: purpose classification**

Distance Protection produces relay zone verdicts (Z ∈ Zone 1/2/3).

- **(a) PURPOSE_ENGINEERING_CALCULATION** — Unverified inputs block this
  analysis. Zone verdicts from unverified data are suppressed entirely.
- **(b) PURPOSE_EXPLORATORY_ANALYSIS** — Unverified inputs allowed; zone
  verdict is computed but labeled "based on Unverified source."

Recommended: **(a)**. A zone verdict is not an informational display — it
is an engineering determination used in protection coordination. Presenting
a zone verdict from an unverified impedance is a safety concern.

---

## 8. Suggested implementation slices

### Slice 3B-2C-1: Phasor service calibration gate

**Single injection point:** `_fetch_role_candidate()` in
`backend/app/services/phasor_analysis_service.py`, lines ~150–189.

After fetching the candidate (and before returning `_RoleCandidate`), add:

```python
# Source-kind ref: read calibration_authority from analog_channels
if channel_ref.kind == "source":
    full_ch = next((ch for ch in active.record.analog_channels
                    if ch.name == channel_ref.channel_name), None)
    if full_ch is not None and full_ch.calibration_authority is not None:
        eligibility = evaluate_calibration_eligibility(
            [full_ch.calibration_authority], PURPOSE_EXPLORATORY_ANALYSIS
        )
        if not eligibility.eligible:
            return None  # or a _RoleCandidate with authority_status set
# Calc-kind ref: use _collect_leaf_authorities()
else:
    leaf_result = _collect_leaf_authorities(
        calculated, workspace_id=workspace_id,
        source_registry=source_registry,
        calc_registry=calculated_channel_registry,
    )
    if leaf_result.blocked_reason is not None or not evaluate_calibration_eligibility(
        [a for a in leaf_result.authorities if a is not None],
        PURPOSE_EXPLORATORY_ANALYSIS
    ).eligible:
        return None  # or return with authority_status
```

The exact return value (None → `needs_configuration` in callers, or a
flagged candidate for option (b)) depends on OD-8 decision.

**Protects:** Phasor (P-1), Impedance (P-2), Distance Protection (P-3),
Sequence Components (P-4) — all in one change.

**Tests required:** 8–10 unit tests (source/calc kind × verified/unverified/invalid
× single-phase/multi-phase diagram); 2–3 browser tests.

**Files changed (implementation):**
- `backend/app/services/phasor_analysis_service.py` (~40 lines)
- Possibly `backend/app/domain/phasor.py` (new `authority_status` field on
  `PhasorDiagramRoleResult` if OD-8 selects option b)
- `backend/app/schemas/phasor_analysis.py` (schema update if option b)
- `backend/app/api/v1/engineering_contexts.py` (error mapping if option b)
- New test file: `backend/tests/test_phasor_calibration_gate.py`

**Gate fires in `prepare_phasor_diagram()` phase (DEC-114):** because
`_fetch_role_candidate()` is called in the preparation phase, the gate fires
ONCE per multi-time request. No per-sample cost.

---

### Slice 3B-2C-2: Compliance ENG-mode gate

**Injection point:** `compliance_series._raw()`, source-kind branch (~line 100),
before the array read.

```python
if ref.kind == "source":
    full_ch = next((ch for ch in active.record.analog_channels
                    if ch.name == ref.channel_name), None)
    if full_ch is not None and full_ch.calibration_authority is not None:
        eligibility = evaluate_calibration_eligibility(
            [full_ch.calibration_authority], PURPOSE_COMPLIANCE_ASSESSMENT
        )
        if not eligibility.eligible:
            raise InvalidCalibrationAuthorityError(
                reason=eligibility.reason,
                input_ref=ref.channel_name,
            )
```

For calc-kind refs in compliance, `_collect_leaf_authorities()` applies.

**Files changed (implementation):**
- `backend/app/services/compliance_series.py` (~25 lines)
- `backend/app/api/v1/compliance.py` (HTTP 422 mapping for
  `InvalidCalibrationAuthorityError`)
- New test file: `backend/tests/test_compliance_calibration_gate.py`

**Protects:** Compliance traces (C-1) and compliance readiness (C-2, indirectly,
since readiness calls `load_series()` / `unit_problem()`).

---

### Slice 3B-2C-3: Provenance labeling (OD-12, OD-8b/OD-10b)

If the owner selects option (b) for any of OD-8, OD-10, OD-12:

- Add `authority_status: str | None` and `has_unverified_leaves: bool` to
  the relevant response schemas.
- Frontend renders per-role / per-trace provenance indicators.
- Full UX improvements (badges, warning banners, explanatory tooltips)
  deferred to Stage 3B-3.

This slice is optional pending OD decisions. It does not block Slice 3B-2C-1
or 3B-2C-2.

---

## 9. Regression and UAT test plan

### Backend unit tests (new: `test_phasor_calibration_gate.py`)

| Scenario | Expected result |
|----------|----------------|
| 1. Unverified BEN5K Va → phasor analysis | `needs_configuration` / `calibration_unverified` on Va role (if OD-8a) |
| 2. Invalid BEN5K Va → phasor analysis | `needs_configuration` / `calibration_invalid` on Va role |
| 3. Unverified BEN5K Va in 3-phase diagram | Va blocked; Vb/Vc computed if from verified source (OD-13a) |
| 4. COMTRADE Va (not-assessed) → phasor | computed normally (backward compat) |
| 5. All-verified sources → phasor | computed normally |
| 6. Unverified BEN5K → Reverse Polarity calc channel → phasor | Va blocked (DFS traversal) |
| 7. Invalid → phasor | blocked (Invalid dominates) |
| 8. Unverified BEN5K Va → impedance locus | Va role blocked; Z not computed |
| 9. COMTRADE Va → impedance locus | computed normally |
| 10. Unverified BEN5K → Distance Protection | zone verdict blocked (OD-14) |
| 11. Unverified BEN5K → Sequence Components | V₁/V₂/V₀ blocked if any Va/Vb/Vc unverified |
| 12. Manual phasor diagram | always computed (no source linkage) |

### Backend unit tests (new: `test_compliance_calibration_gate.py`)

| Scenario | Expected result |
|----------|----------------|
| 13. Unverified BEN5K → compliance trace (ENG) | `incompatible` / blocked (OD-10a) or exploratory label (OD-10b) |
| 14. Invalid BEN5K → compliance trace | `incompatible` / HTTP 422 |
| 15. COMTRADE (not-assessed) → compliance trace | loaded normally |
| 16. Verified BEN5K → compliance trace | loaded normally |
| 17. Unverified → RMS calc channel → compliance trace | blocked (DFS traversal) |

### Regression — existing test suites (must remain unchanged)

| Suite | Expected |
|-------|----------|
| `test_ben5k_pu_calibration_gate.py` (46) | PASS |
| `test_ben5k_calculated_channel_pu_gate.py` (30) | PASS |
| `test_invalid_calibration_calculated_channel_gate.py` (23) | PASS |
| `test_phasor_domain.py` | PASS (gate is in service layer, not domain) |
| `test_phasor_analysis_service.py` | PASS (COMTRADE/manual paths unaffected) |
| `test_compliance_*.py` | PASS (COMTRADE paths unaffected) |
| `test_calculated_channel_service.py` | PASS |
| Full backend suite | exit 0 |

### Browser regression scenarios

| Scenario | Test mechanism |
|----------|----------------|
| BEN5K Va → Phasor diagram | `ben5k-phasor-calibration-gate.spec.js`: Va role shows `needs_configuration` |
| COMTRADE Va → Phasor diagram | Same spec: Va role shows `available`, numeric result present |
| BEN5K Va → Impedance Locus | `ben5k-impedance-calibration-gate.spec.js`: Z value blocked/labelled |
| BEN5K compliance trace | `ben5k-compliance-calibration-gate.spec.js`: trace blocked / status `incompatible` |
| COMTRADE compliance trace | Same spec: trace loads normally |
| Existing Stage 3B-2A/3B-2B-1/3B-2B-2 browser tests | PASS (regressions) |

### UAT scenarios (owner sign-off)

| Scenario | Validation |
|----------|-----------|
| Load BEN5K recording; view Phasor diagram | Va/Ia roles show appropriate calibration status |
| Load BEN5K recording; view Impedance Locus | Locus blocked or labelled depending on OD-8 decision |
| Load COMTRADE recording; all analyses | No change in behavior |
| Load mixed BEN5K + COMTRADE workspace; Sequence Components | BEN5K role blocked; COMTRADE roles computed |
| Load BEN5K; compliance readiness | Either blocked (`incompatible`) or exploratory label per OD-10 |
| Calculator manual phasor diagram | Fully functional regardless of any recording |

### Numerical invariants

- ENG waveform values for BEN5K channels: **unchanged** (gate is in analysis
  layer; raw waveform display is `PURPOSE_RAW_INSPECTION`, always eligible).
- COMTRADE/CSV calculated channels: **unchanged** (not-assessed passes all gates).
- Verified BEN5K channels: **unchanged** (gate passes on all purposes).
- Phasor magnitude/angle for COMTRADE inputs: **unchanged**.

---

## 10. Verdict

### Is the existing DEC-213 domain model sufficient?

**Yes.** `evaluate_calibration_eligibility()` already supports all required
purposes for Stage 3B-2C:

- `PURPOSE_EXPLORATORY_ANALYSIS`: for phasor display (if OD-8b) and compliance
  traces (if OD-10b).
- `PURPOSE_ENGINEERING_CALCULATION`: for phasor gate under OD-8a.
- `PURPOSE_COMPLIANCE_ASSESSMENT`: for compliance readiness gate under OD-10a.

No new purpose constants, no new authority statuses, no new domain functions
are required.

### Is `_collect_leaf_authorities()` sufficient?

**Yes.** The DFS traversal is reusable for calc-kind role refs in both the
phasor service gate and the compliance series gate. No second DFS
implementation is needed.

### What IS needed

1. A calibration check in `_fetch_role_candidate()` (phasor service) using the
   same pattern as Stage 3B-2A for source refs and Stage 3B-2B-1 for calc refs.

2. A calibration check in `compliance_series._raw()` (compliance service)
   using the same pattern.

3. Owner decisions OD-8 through OD-14 to confirm the purpose and per-role vs
   whole-result policy before implementation.

### Key architectural differences from Stage 3B-2B-1 and 3B-2B-2

Stage 3B-2B-1/2B-2 operated on **calculated-channel evaluation** (a channel
exists in the registry; its dependency tree is traversed). Stage 3B-2C
operates on **ad-hoc, role-resolved analysis requests** (there is no stored
channel; roles are resolved fresh per request from the workspace state).

This means:
- No creation-time gate is needed in the phasor service (phasor analysis is
  not stored).
- The gate fires at the top of `_fetch_role_candidate()` and returns a role
  status of `needs_configuration`, not a service exception.
- The phasor API response already has a per-role `status` / `reason_code`
  vocabulary to carry the calibration limitation without a new error class.

For compliance traces, the gate fires in `_raw()` / `load_series()` and
raises `InvalidCalibrationAuthorityError` (same as Stage 3B-2B-2 evaluation
gate), since compliance traces are array-valued outputs, not role-status
objects.

---

## 11. Files to be modified in Stage 3B-2C (implementation, pending owner approval)

**New files:**
- `backend/tests/test_phasor_calibration_gate.py`
- `backend/tests/test_compliance_calibration_gate.py`
- `browser-tests/ben5k-phasor-calibration-gate.spec.js`
- `browser-tests/ben5k-compliance-calibration-gate.spec.js`

**Modified files (Slice 3B-2C-1):**
- `backend/app/services/phasor_analysis_service.py` — gate in `_fetch_role_candidate()`
- Possibly: `backend/app/domain/phasor.py` (if OD-8b: add `authority_status` field)
- Possibly: `backend/app/schemas/phasor_analysis.py` (if OD-8b: schema update)
- Possibly: `backend/app/api/v1/engineering_contexts.py` (if new error type/status needed)

**Modified files (Slice 3B-2C-2):**
- `backend/app/services/compliance_series.py` — gate in `_raw()`
- `backend/app/api/v1/compliance.py` — HTTP 422 mapping

**No changes required to:**
- `backend/app/domain/physical_calibration.py` (domain model is complete)
- `backend/app/services/impedance_analysis_service.py` (inherits from phasor gate)
- `backend/app/services/distance_protection_analysis_service.py` (inherits from phasor gate)
- `backend/app/services/sequence_components_analysis_service.py` (inherits from phasor gate)
- `backend/app/services/calculated_channel_service.py` (Stage 3B-2B-1/2B-2 unchanged)
- `backend/app/api/v1/calculator.py` (manual path, no gate needed)
- BEN decoding, PU mathematics, numerical operations

---

*Assessment only. No production code or test files modified in this document.*
*Awaiting owner decisions OD-8 through OD-14 before implementation.*
