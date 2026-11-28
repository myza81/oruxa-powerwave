# Post-DEC-213 Browser Regression Triage

**Date:** 2026-11-14
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Head commit at investigation time:** `9688493` (Stage 3B-3 HANDOFF update)
**Authored by:** Browser-triage investigation — DEC-213 consolidated audit follow-up
**Status:** COMPLETE — no production or test code modified; no commits made

---

## 1. Mandate

Three browser tests were failing at the conclusion of Stage 3B-3. The mandate was to
classify each failure as:

- **(A)** Genuine pre-existing defect — broken before any DEC-213 stage
- **(B)** Stage 3B-3 regression — introduced by the most recent commit (`81e7fb0`)
- **(C)** Earlier DEC-213 regression — introduced by Stage 3B-2C-1 through 3B-3
- **(D)** Flaky / timing — non-deterministic, passes on re-run
- **(E)** Outdated assertion — assertion was correct when written but rendered stale by a
  later approved feature without the test being updated

No production or test code was modified during this investigation.

---

## 2. Failures investigated

| # | Spec file | Line | Test name |
|---|-----------|------|-----------|
| F-1 | `browser-tests/compliance_measurement.spec.js` | 208 | switching Bay updates the base from that group's own shared configuration |
| F-2 | `browser-tests/compliance_workspace.spec.js` | 279 | a pu Reference: no base -> Action Required and NO pu trace … |
| F-3 | `browser-tests/per-unit-display-synchronization.spec.js` | 317 | a Voltage base edit refreshes linked Current while other groups keep their bases |

---

## 3. F-1 — compliance_measurement.spec.js:208

### Exact failure

```
Error: expect(locator).toContainText(expected)
Expected:  "275 kV L-G"
Received:  "Base✓ 275.00 kV L-G"
```

Reproduced consistently across 2/2 runs.

### Root-cause analysis

`wwComplianceUnitRowHtml()` at `frontend/index.html:54589` produces the unit row for
a configured PU base:

```javascript
const text = base ? ("✓ " + Number(base.nominal_voltage_ll_kv).toFixed(2) + " kV " + refLabel)
                  : "✓ Per-unit base configured";
return '<div class="ww-compliance-readiness-row" data-row="unit" data-state="ready">'
     + '<span class="ww-compliance-readiness-label">Base</span>'
     + '<span class="ww-compliance-readiness-value">' + escapeHtml(text) + '</span></div>';
```

The combined DOM text content of the two spans is `"Base✓ 275.00 kV L-G"`.
The test asserts `.toContainText("275 kV L-G")` — the substring `"275 kV L-G"` does NOT
appear anywhere in `"Base✓ 275.00 kV L-G"` because `toFixed(2)` inserts `".00"` between
`"275"` and `" kV"`.

### When this code was introduced

`git log -S "toFixed(2)" -- frontend/index.html` returns `d9b3caf` as the introducing
commit. That commit is `feat(pu): Slice 6C — Voltage-only ENG/PU display, Current always
A/kA (DEC-212)`.

The compliance_measurement spec was last modified at `3c6495b`
(`fix: harden recording lifecycle and browser regression readiness`) and
`8739ddb` (`fix: harden Slice D timing and browser regressions`).

`git merge-base --is-ancestor d9b3caf 3c6495b` → exit 1 (d9b3caf is NOT an ancestor of
3c6495b). The two commits are on diverged parallel histories that merged before DEC-213.
Both commits are present on the current branch. `d9b3caf` (Slice 6C) is at linear log
position ~38 (more recent), and `3c6495b` is at position ~92 (older). Slice 6C changed
the compliance unit row format AFTER the spec assertion was written but the test was not
updated.

### DEC-213 involvement

No DEC-213 stage (`34c396f` through `81e7fb0`) modified `wwComplianceUnitRowHtml`. The
function is unchanged from `d9b3caf`. Confirmed via `git show c7b8388 d30a4be 81e7fb0`
grep for this function — no hits.

### Classification

**(A) Pre-existing defect** — broken since `d9b3caf` (Slice 6C / DEC-212), which
predates all DEC-213 stages by approximately 50 commits. No DEC-213 involvement.

---

## 4. F-2 — compliance_workspace.spec.js:279

### Exact failure

```
Error: expect(locator).toHaveClass(expected)
Locator: locator('.ww-compliance-readiness-row[data-row="unit"]')
Expected pattern: /ww-compliance-critical/
Received string:  "ww-compliance-readiness-row"
```

The element consistently resolved to `data-state="ready"` across 23 resolution attempts
in a 10-second poll. Line 278 (reference action_required) **passed** on the same run.

### Root-cause analysis

The test scenario: upload `line_to_line_multibay` (COMTRADE), add a PU reference, open
compliance for the KPDN1 measurement group, click Prepare, assert that the unit row is in
"action_required" (critical) state because no base has been configured.

The backend returns `unit_state = "ready"` for the KPDN1 group, meaning a voltage base
IS configured. The test assumed no base would be configured at upload time.

The measurement group KPDN1 receives an automatic voltage base as a consequence of
`7d4c263` (`feat(pu): automatic primary-secondary per-unit configuration and display`).
That feature evaluates uploaded recordings and automatically configures per-unit voltage
groups where a nominal voltage can be inferred. The `line_to_line_multibay` fixture's
KPDN1 bay has instantaneous kV channels; Slice 6C (`d9b3caf`) or the automatic PU
feature picks up the nominal voltage and configures a base.

Line 278 of the test passes (`data-status="action_required"` on the reference) because
the reference is action_required for a **different** reason from what the test intended —
the KPDN1 channels are instantaneous (not yet prepared as RMS) so the compliance system
still reports action_required, but via the measurement-preparation path rather than the
"no base" path. The base IS configured, so the unit row is "ready".

The fixture is COMTRADE. COMTRADE sources carry `not_assessed` calibration authority and
pass all DEC-213 calibration gates without change.

### DEC-213 involvement

None. `STATE_CALIBRATION_UNAVAILABLE` and the compliance calibration gate (Stage
3B-2C-2) only affect BEN5K sources with explicit calibration authority. The
`line_to_line_multibay` COMTRADE fixture is entirely unaffected by any DEC-213 stage.
The unit row's "ready" state comes from the automatic base configured by `7d4c263`, which
is an entirely separate feature (DEC-212 PU slices, pre-DEC-213).

### Classification

**(A) Pre-existing defect** — broken since `7d4c263` (automatic primary-secondary PU
configuration), which predates all DEC-213 stages. No DEC-213 involvement.

---

## 5. F-3 — per-unit-display-synchronization.spec.js:317

### Exact failure

```
Error: expect(received).toBeCloseTo(expected, precision)
Expected: 2.0005186827420536
Received: 4.2
Expected precision: 1 (tolerance < 0.05)
Received difference: 2.1994813172579466
Timeout 10000ms exceeded while waiting on the predicate
```

### Root-cause analysis

The test sequence (lines 305–326):
1. Upload a synthetic COMTRADE fixture with IA at 4.2 kA amplitude.
2. Create an equipment-rating current group for "IA" linked to the voltage group at
   275 kV nominal.
3. Display IA, LOW VA, MANUAL IA channels; set cursor positions via `cursors()`.
4. Call `switchMode(page, "per_unit")`.
5. `expectCursors(..., 4.2 / (1000 / (√3 × 275)), { name: "IA" })` ← **fails here**
   (expects PU-converted value ≈ 2.0005, received 4.2 — the raw ENG value).

`switchMode()` is defined at line 105–110:

```javascript
async function switchMode(page, mode) {
  await page.locator(...).click();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expect(locator).toHaveAttribute("aria-pressed", "true");
}
```

`switchMode` clicks the PU button and waits for `window.unitJobs` (tracked calls to
`wwApplyUnitMode`) to resolve. It does NOT call `wwFetchCursorValuesForSource`.

`cursors()` (line 67–77) explicitly calls `wwFetchCursorValuesForSource` to populate the
cursor DOM with values. These are API calls that return values in the current unit mode.
After `switchMode`, `wwApplyUnitMode` refreshes the waveform display (channel list values,
peak annotations) but does NOT re-fetch cursor values unless the mode switch internally
triggers `wwFetchCursorValuesForSource`.

The cursor DOM retains the value fetched during `cursors()` (ENG mode: 4.2 kA). The test
expects the cursor DOM to show the PU-converted value (≈ 2.0005 pu) without an explicit
re-fetch. `expect.poll()` waited 10 s — the value never changed. This is not a timing
race; `wwApplyUnitMode` genuinely does not re-fetch cursor values.

The first explicit refresh call in the test (`wwRefreshDisplayedChannelsForPerUnitChange`)
appears only at line 321 (after the base edit), which correctly updates cursors.

### DEC-213 involvement

No DEC-213 stage modified `wwApplyUnitMode`, `wwFetchCursorValuesForSource`,
`wwCurValueText`, or any cursor-fetching path for source channels. Stage 3B-3-C added
`" ⚠"` to `wwCurValueText` for `exploratory_unverified` **calculated** channels only;
source channels are unaffected. COMTRADE sources pass all DEC-213 gates without change.

The spec file was last modified in `0eea55c`
(`fix(pu): synchronize waveform display state for Slice 2`) and `57ec3d1`
(`docs(pu): record VLT-REF-001 final local verification; add Voltage browser spec`), both
predating all DEC-213 stages.

### Classification

**(A) Pre-existing defect** — `switchMode` does not trigger a cursor re-fetch; the test
expectation at line 317 is incompatible with how `wwApplyUnitMode` works. No DEC-213
involvement. The defect predates all DEC-213 stages.

---

## 6. Summary table

| ID | Spec | Line | Classification | Introduced by | DEC-213 stage? |
|----|------|------|----------------|---------------|----------------|
| F-1 | compliance_measurement.spec.js | 208 | **A — Pre-existing defect** | `d9b3caf` Slice 6C (DEC-212) | None |
| F-2 | compliance_workspace.spec.js | 279 | **A — Pre-existing defect** | `7d4c263` auto PU (DEC-212 PU slices) | None |
| F-3 | per-unit-display-synchronization.spec.js | 317 | **A — Pre-existing defect** | `0eea55c` Slice 2 cursor sync | None |

All three failures are pre-existing defects that predate the entire DEC-213 work stream
(`34c396f` Stage 3A through `81e7fb0` Stage 3B-3). None were introduced or modified by
any DEC-213 stage.

---

## 7. Push-blocking verdict

**None of the three failures are push-blocking for the DEC-213 feature branch.**

Rationale:
- All three are pre-existing. They were present before DEC-213 work began and remain
  unchanged by it.
- No DEC-213 stage degraded an assertion that was previously passing.
- The failures do not indicate any regression in the capabilities delivered by DEC-213
  (phasor gate, compliance calibration gate, calculated-channel provenance, UI badges).
- The browser test suite, excluding these three pre-existing failures, passes without
  failures across all DEC-213 scenarios.

These failures should be tracked separately as technical debt for the PU/compliance
display layer (DEC-212 / VLT-REF-001) and fixed in a dedicated pass.

---

## 8. Stage 3B-3 closure verdict

**Stage 3B-3 (`81e7fb0`) is not blocked by any of these failures.**

None of the three failures involve code changed in Stage 3B-3. The Stage 3B-3 deliverables:

- `WW_PHASOR_REASON_TEXT` +4 DEC-213 reason codes
- `wwPhasorRoleStatusLabel` +`calibration_unavailable`
- `.ww-source-calib-badge` CSS tokens
- `wwSourceCalibrationBadgeHtml(channel)` helper
- `wwCurValueText()` +`" ⚠"` for `exploratory_unverified` calculated channels

…are covered by the new spec `browser-tests/stage3b3-source-badge.spec.js` and the
`+1` phasor label test in `browser-tests/ben5k-phasor-calibration-gate.spec.js`, both of
which pass. No existing passing test was broken by Stage 3B-3.

**Stage 3B-3 is closed pending owner engineering review. The three browser failures are
not blockers.**

---

## 9. Recommended remediation (not in scope here — record only)

| ID | Fix approach |
|----|--------------|
| F-1 | Update `compliance_measurement.spec.js:208` assertion to match current format: `toContainText("✓ 275.00 kV L-G")` or use a partial regex |
| F-2 | Update test to use a fixture that starts with no PU base configured, or delete and re-create the KPDN1 group at the start of the test; test should verify `unit_state === "action_required"` before base configuration |
| F-3 | Insert `await page.evaluate(source => wwRefreshDisplayedChannelsForPerUnitChange(source), source)` between `switchMode` (line 316) and the first `expectCursors` (line 317), matching the pattern used at line 321 |

These are test-only fixes. No production code changes are required for any of the three.
