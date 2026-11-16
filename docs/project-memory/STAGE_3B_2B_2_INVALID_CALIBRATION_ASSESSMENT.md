# Stage 3B-2B-2 — Architecture Assessment
# Invalid Physical-Calibration Exploratory-Calculation Safeguards (DEC-213)
# 2026-11-12

---

## 1. Purpose and scope

This document is an **architecture assessment only**. No production code is
modified here. No commits, pushes, or deployments are authorised.

Stage 3B-2B-2 adds safeguards that prevent an **Invalid**-authority source
channel from being used in a calculated channel — either at creation time, or
at evaluation time if a dependency has become Invalid after the channel was
created. The owner-stated policy distinguishes Unverified from Invalid:

> Unverified inputs may be used for explicitly exploratory ENG calculations.
> Invalid inputs must be rejected for ordinary exploratory calculations.
> Enforce this at creation and at evaluation when an existing dependency has
> become Invalid. Preserve Not Assessed backward compatibility.

Stage 3B-2B-1 (committed as `9dbc4d4`) already blocks Invalid authority on the
**PU** path for all calculated VOLTAGE/CURRENT channels. The remaining gap is
the **ENG** path at both the creation layer and the waveform/cursor/peak/
annotation evaluation layers.

---

## 2. Owner policy mapping to domain constants

The owner policy maps directly to constants already in
`backend/app/domain/physical_calibration.py`:

| Owner statement | Domain constant | `_result_for_*()` behaviour |
|---|---|---|
| Unverified may be used for exploratory ENG calculations | `PURPOSE_EXPLORATORY_ANALYSIS` | `_result_for_unverified` → `eligible=True` |
| Invalid must be rejected for ordinary exploratory calculations | `PURPOSE_EXPLORATORY_ANALYSIS` | `_result_for_invalid` → `eligible=False` |
| Preserve Not Assessed backward compatibility | (any purpose) | `_result_for_not_assessed` → `eligible=True` unconditionally |

The domain model is **complete and correct**. No changes to
`physical_calibration.py` are needed.

For reference, `_result_for_invalid` (line 306–324):
```python
eligible = purpose == PURPOSE_RAW_INSPECTION  # False for all other purposes
```

`_result_for_unverified` (line 327–346):
```python
eligible = purpose in (PURPOSE_RAW_INSPECTION, PURPOSE_EXPLORATORY_ANALYSIS)  # True for exploratory
```

---

## 3. The two enforcement points

The owner policy mandates enforcement at two distinct points:

### 3A. Creation time — `create_calculated_channel()`

`_resolve_input()` (line 511, `calculated_channel_service.py`) is called once
per input reference at lines 907–910 of `create_calculated_channel()`. It reads
`AnalogChannelSummary.engineering_type`, `.waveform_form`, and the raw sample
arrays. **It never reads `calibration_authority`.**

This is the bypass point. An Invalid-authority BEN5K channel can currently be
used as a creation-time input without any gate. The result is a stored
`CalculatedChannel` whose ENG-mode values derive from data the owner has
classified as Invalid.

### 3B. Evaluation time — ENG-mode callers

The four PU-aware evaluation entry-points (`extract_calculated_waveform_range`,
`extract_calculated_cursor_values`, `resolve_calculated_peak_value`,
`resolve_calculated_annotation_anchor`) all call
`_resolve_effective_per_unit_for_calculated_channel()` **only when
`unit_mode == UNIT_MODE_PER_UNIT`**.

In `UNIT_MODE_ENGINEERING`, they go directly to the stored arrays. The Stage
3B-2B-1 gate does not fire. An existing calculated channel whose leaf source
has become Invalid will continue to display ENG-mode values without any warning
or block.

---

## 4. Source lifecycle — when does "dependency has become Invalid" apply?

Understanding this is essential for scoping the evaluation-time gate.

### Reimport path (remove + add)

`remove_calculated_channels_for_source()` (line 1531) filters all channels by
`c.reference_source_id == source_id` and deletes the entire subtree in one
pass. When a BEN5K file is reimported, the old source is **removed** first,
which atomically deletes all calculated channels anchored to it. The reimport
adds a fresh source with a new `source_id`. Any new calculated channels must be
created fresh — the creation-time gate catches them.

Under the reimport path, there is no reachable scenario where an existing
calculated channel holds a stale Invalid dependency. **The creation-time gate
alone is sufficient for all current reimport behaviour.**

### Future "mark as Invalid" path

The owner phrase *"at evaluation when an existing dependency has become
Invalid"* anticipates a future API that allows the authority status of an
existing source channel to be changed from Unverified → Invalid **without**
removing and reimporting the source. This path does not exist today. When it
is implemented, source_id stays constant, `reference_source_id` on existing
calculated channels still points to the now-Invalid source, and the creation-
time gate does not help — only the evaluation-time gate catches it.

**The evaluation-time ENG-mode gate is therefore future-proofing for a planned
but not-yet-implemented "mark as Invalid" workflow.** Both gates should be
designed together so they present consistent behaviour when both are active.

---

## 5. Existing infrastructure that can be reused

### `_collect_leaf_authorities()` (line 338)

The DFS traversal from Stage 3B-2B-1 already:
- Traverses the full dependency tree of a `CalculatedChannel`
- Collects `PhysicalCalibrationAuthority | None` for each unique source leaf
- Returns `blocked_reason` for OD-1/OD-3 failure conditions
- Handles cycle detection and deduplication

This function can be reused directly for the **evaluation-time** ENG-mode gate —
it takes a `CalculatedChannel` and all registries that the evaluation entry-
points already accept.

For the **creation-time** gate, the channel does not exist yet, so
`_collect_leaf_authorities()` cannot be called on it directly. A separate
pre-flight function must traverse the `inputs: list[ChannelRef]` list and check
each ref's authority before `_resolve_input()` is called.

### `evaluate_calibration_eligibility()` (line 223)

Already accepts `Sequence[PhysicalCalibrationAuthority | None]` and a
`purpose`. Passing `PURPOSE_EXPLORATORY_ANALYSIS` correctly applies the
Unverified=allowed, Invalid=blocked policy.

---

## 6. Creation-time gate — proposed design

### Location in `create_calculated_channel()`

The existing validation sequence (lines 907–1333) is:

```
1.  _resolve_input() calls for all inputs (lines 907–910)
2.  Engineering-type guards (lines 935+)
3.  Unit guards (lines 948+)
4.  Sampling density guards (lines 964+)
5.  Phase matching and three-phase guards (lines 994+)
6.  Null policy guard (lines 1312–1327)
7.  Cycle check (line 1332)
8.  Array computation (lines 1349+)
```

The calibration authority check must come **before step 1**, so that
`_resolve_input()` is never called for an Invalid-authority input. No waveform
arrays are read; no numerical evaluation is performed.

### Proposed new function `_check_creation_authority()`

```python
def _check_creation_authority(
    inputs: list[ChannelRef],
    *,
    workspace_id: str,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> None:
    """
    Raise InvalidCalibrationAuthorityError if any leaf of any input ref
    carries CALIBRATION_INVALID authority (PURPOSE_EXPLORATORY_ANALYSIS
    semantics: Unverified passes, Invalid blocks, Not-Assessed passes).
    """
```

**For each `ref` in `inputs`:**

- `ref.kind == "source"` → look up source in `source_registry`.
  - If `source.record.metadata.format_variant == FORMAT_VARIANT_BEN5K_LEGACY`:
    - Find the channel in `source.record.analog_channels` by `ref.channel_name`.
    - If the channel has `calibration_authority` with
      `status == CALIBRATION_INVALID`:
      - Raise `InvalidCalibrationAuthorityError` with machine-readable reason.
  - Non-BEN5K sources: `calibration_authority` is `None` → not-assessed →
    passes (backward compat preserved).

- `ref.kind == "calculated"` → look up the existing `CalculatedChannel` in
  `calc_registry`.
  - Call `_collect_leaf_authorities()` on that channel (it already exists).
  - Run `evaluate_calibration_eligibility(leaves, PURPOSE_EXPLORATORY_ANALYSIS)`.
  - If `not eligibility.eligible`:
    - Raise `InvalidCalibrationAuthorityError` with machine-readable reason
      derived from `eligibility.reason`.

**Why this design and not a check inside `_resolve_input()`:**

`_resolve_input()` is a pure data-resolution function that deliberately does
not read calibration metadata. Preserving that separation keeps the ENG display
path clean (a future `OP_DISPLAY` or inspection function can call
`_resolve_input()` without inheriting calibration semantics). The pre-flight
function at the `create_calculated_channel()` layer is the correct gate for
creation-purpose semantics.

**Bypass protection for calc-kind chains:**

If `_check_creation_authority()` only checked direct `source`-kind refs, an
engineer could bypass the gate by using an intermediate calculated channel as
a "buffer" (create Calc1 from Invalid source → then create Calc2 from Calc1).
Checking calc-kind refs via `_collect_leaf_authorities()` closes this bypass:
the DFS traversal always walks to the original source leaves.

### New error type needed

No `InvalidCalibrationAuthorityError` exists in `app/services/errors.py`
(confirmed by grep). This is a new error that:
- Signals that a source or its transitive dependency carries
  `CALIBRATION_INVALID` authority
- Is distinct from existing errors (`SourceNotFoundError`, `CyclicDependencyError`, etc.)
- Returns HTTP 422 from the API router (consistent with other creation-time
  validation errors)
- Carries a machine-readable `reason` field (e.g.
  `"invalid_calibration_authority"`) for the frontend to display a specific
  message

---

## 7. Evaluation-time gate (ENG mode) — proposed design

### Entry-points affected

All four PU-aware entry-points call
`_resolve_effective_per_unit_for_calculated_channel()` only in PU mode.
In ENG mode they currently skip all authority checks:

| Entry-point | ENG-mode bypass | Lines |
|---|---|---|
| `extract_calculated_waveform_range()` | `if unit_mode == UNIT_MODE_PER_UNIT:` | 1717 |
| `extract_calculated_cursor_values()` | `if unit_mode == UNIT_MODE_PER_UNIT:` | 1789 |
| `resolve_calculated_peak_value()` | `if available and unit_mode == UNIT_MODE_PER_UNIT:` | 1855 |
| `resolve_calculated_annotation_anchor()` | `if unit_mode == UNIT_MODE_PER_UNIT:` | (analogous) |

### Proposed gate placement

Add an **authority preflight** at the top of each entry-point (or extracted
into a shared helper), unconditional on `unit_mode`, that:
1. Calls `_collect_leaf_authorities()` to gather all leaf authorities
2. If `blocked_reason is not None` → surface a machine-readable status
3. Runs `evaluate_calibration_eligibility(leaves, PURPOSE_EXPLORATORY_ANALYSIS)`
4. If `not eligibility.eligible` (i.e., Invalid leaf found) → surface a
   machine-readable `calibration_invalid` status

**Surfacing Invalid in ENG mode — decision needed (see Section 10):**

The result types carry `per_unit_status: str | None` which is `None` in ENG
mode. The assessment identifies two options:

**Option A — Reuse `per_unit_status`:**
Set `per_unit_status = "calibration_invalid"` even in ENG mode when an Invalid
leaf is detected. The frontend already reads `per_unit_status` for the
`calibration_unavailable` case; it would need a new branch for
`calibration_invalid` in ENG mode. Values are still returned as-is (not zeroed
or omitted) — the status is informational only.

**Option B — Block values, surface a new `calibration_status` field:**
Add a new `calibration_status: str | None` to result types. When Invalid,
return `None` values and set `calibration_status = "calibration_invalid"`. This
prevents ENG-mode display of Invalid-sourced data entirely, matching the
creation-time rejection semantics.

Option B is more consistent with the owner policy ("must be rejected") but is a
larger change to the response schema. The owner must decide before
implementation.

**OD-2 compatibility:**

Stage 3B-2B-1 OD-2 stated: "Preserve exploratory ENG calculations." This
applied to Unverified sources — Unverified is still allowed for `PURPOSE_
EXPLORATORY_ANALYSIS`. The evaluation-time gate here applies `PURPOSE_EXPLORATORY_
ANALYSIS`, which passes Unverified and blocks only Invalid. OD-2 is preserved
for Unverified; the new behaviour applies to Invalid only.

---

## 8. Interaction with Stage 3B-2B-1 PU gate

Stage 3B-2B-1 (committed) blocks VOLTAGE/CURRENT calculated channels from
returning authoritative PU output when any leaf is Unverified or Invalid.
Stage 3B-2B-2 adds:

| Path | Unverified | Invalid |
|---|---|---|
| PU output (Stage 3B-2B-1, committed) | `calibration_unavailable` | `calibration_unavailable` |
| ENG creation gate (Stage 3B-2B-2) | Allowed | Blocked (`InvalidCalibrationAuthorityError`) |
| ENG evaluation gate (Stage 3B-2B-2) | Allowed | `calibration_invalid` status or blocked values |

The PU path and the ENG path use different purposes
(`PURPOSE_ENGINEERING_CALCULATION` vs `PURPOSE_EXPLORATORY_ANALYSIS`) but the
same domain evaluator (`evaluate_calibration_eligibility`). No domain-layer
changes are needed.

---

## 9. What is NOT covered in Stage 3B-2B-2

The following are explicitly out of scope and should be deferred:

- **BEN5K numerical calibration corrections** — no scaling factor changes, no
  `√2/16` or gain correction, no changes to raw sample interpretation.
- **PU base assignments or nominal voltage interpretation** — out of scope.
- **Phasor, power or compliance enforcement** — out of scope.
- **Stage 3B-2C, 3B-3, Slice 6D** — out of scope.
- **Existing `PerUnitResolution.reason` or domain constants** — no changes.
- **Non-BEN5K sources (COMTRADE, CSV, SubBen)** — `calibration_authority` is
  `None` → not-assessed → passes both gates unchanged (backward compat).
- **POWER / ROCOF / FREQUENCY / UNDEFINED calculated channels** — OD-4 from
  Stage 3B-2B-1 established that those types are not subject to the PU gate.
  The creation-time and ENG-mode gates follow the same OD-4 scope: they fire
  only for VOLTAGE and CURRENT engineering types (consistent with where Invalid
  data would affect magnitude-critical calculations).

---

## 10. Owner decisions required before implementation

The following decisions cannot be resolved from the existing domain contract or
existing owner decisions. They must be obtained before Stage 3B-2B-2
implementation is started.

### OD-5 (New): Invalid in creation — scope of engineering_type gate

Should the creation-time Invalid check fire for **all** engineering types
(VOLTAGE, CURRENT, UNDEFINED, POWER, ROCOF, FREQUENCY), or only for
VOLTAGE and CURRENT (consistent with the OD-4 scope from Stage 3B-2B-1)?

- **Strict option** (all types): An Invalid-authority BEN5K channel cannot be
  used as an input to any calculated channel regardless of operation. Prevents
  any derivation from Invalid data.
- **Consistent option** (VOLTAGE/CURRENT only): Matches OD-4's scope. POWER,
  ROCOF and FREQUENCY operations never produce authoritative PU output anyway,
  so Invalid authority does not affect PU correctness for those types.

### OD-6 (New): Invalid in ENG-mode evaluation — block or annotate?

Should an existing calculated channel whose leaf has become Invalid:
- **Block** display (return `None` values, surface `calibration_invalid` —
  Option B above), or
- **Annotate** (return values as-is, surface `calibration_invalid` as a warning
  status on the result — Option A above)?

Blocking is consistent with the creation-time rejection ("must be rejected").
Annotating may be preferable when the engineer needs to investigate the data
before deciding whether to invalidate it.

### OD-7 (New): New error type name and HTTP semantics

Should the creation-time Invalid rejection use:
- A new `InvalidCalibrationAuthorityError` (422, recommended), or
- An existing error type with an extended reason code?

The new error type is cleaner for the frontend to identify and display a
specific message. The recommendation is a new type consistent with the existing
`app/services/errors.py` pattern.

---

## 11. Proposed test scenarios for future implementation

These scenarios are defined here as a stable specification for the
implementation stage. No test code exists yet.

### Creation-time unit tests

| Scenario | Input | Expected result |
|---|---|---|
| CA-1 | BEN5K source, `CALIBRATION_INVALID` authority, VOLTAGE | Raises `InvalidCalibrationAuthorityError` |
| CA-2 | BEN5K source, `CALIBRATION_UNVERIFIED` authority, VOLTAGE | Passes (Unverified allowed) |
| CA-3 | BEN5K source, `CALIBRATION_INVALID` authority, CURRENT | Raises `InvalidCalibrationAuthorityError` |
| CA-4 | COMTRADE source, `calibration_authority=None`, VOLTAGE | Passes (not-assessed backward compat) |
| CA-5 | Calc-kind ref → BEN5K leaf with `CALIBRATION_INVALID` | Raises `InvalidCalibrationAuthorityError` (bypass protection) |
| CA-6 | Calc-kind ref → Verified BEN5K leaf | Passes |
| CA-7 | Mixed: COMTRADE (not-assessed) + BEN5K (Invalid) | Raises `InvalidCalibrationAuthorityError` |
| CA-8 | Mixed: COMTRADE (not-assessed) + BEN5K (Unverified) | Passes |
| CA-9 | BEN5K source, `CALIBRATION_INVALID`, source not found in registry | Machine-readable error (OD-3 consistent) |
| CA-10 | Depth-3 chain: CalcC→CalcB→CalcA→BEN5K (Invalid) | Raises `InvalidCalibrationAuthorityError` |

### Evaluation-time ENG-mode unit tests (Option B — block)

| Scenario | Input | Expected result |
|---|---|---|
| EV-1 | BEN5K VOLTAGE, `CALIBRATION_INVALID`, ENG mode | `calibration_invalid` status, None values |
| EV-2 | BEN5K VOLTAGE, `CALIBRATION_UNVERIFIED`, ENG mode | No block (Unverified allowed for exploratory) |
| EV-3 | BEN5K VOLTAGE, `CALIBRATION_INVALID`, PU mode | `calibration_unavailable` (Stage 3B-2B-1, unchanged) |
| EV-4 | COMTRADE VOLTAGE, `calibration_authority=None`, ENG mode | No block (backward compat) |
| EV-5 | Calc chain → BEN5K leaf with `CALIBRATION_INVALID`, ENG mode | `calibration_invalid` status |

### Browser integration tests (future)

| Test | Scenario |
|---|---|
| BT-1 | Attempt to create Reverse-Polarity of BEN5K Invalid channel → creation rejected, no channel appears |
| BT-2 | BEN5K Unverified channel → creation succeeds, channel appears in ENG mode |
| BT-3 | Existing calculated channel; source re-marked Invalid (future) → ENG-mode waveform suppressed |

---

## 12. Summary of files that will be modified

No files are modified in this assessment stage. The following files would be
modified in the implementation stage:

| File | Change |
|---|---|
| `backend/app/services/calculated_channel_service.py` | New `_check_creation_authority()` preflight; ENG-mode gate in evaluation entry-points |
| `backend/app/services/errors.py` | New `InvalidCalibrationAuthorityError` |
| `backend/app/routers/calculated_channel_router.py` | Map `InvalidCalibrationAuthorityError` → HTTP 422 |
| `backend/tests/test_ben5k_calculated_channel_pu_gate.py` | Extend with CA-* and EV-* scenarios |

No changes to: `physical_calibration.py`, `per_unit.py`, `metadata.py`,
`normalize.py`, BEN scaling factors, PU mathematics, or any test file from
Stages 3B-2A or 3B-2B-1.

---

*Assessment complete. Owner decisions OD-5, OD-6, OD-7 are required before
implementation begins.*
