# NF-3C — Validating-consumer migration (event detection, compliance, oscillation labels, facts card)

**Date:** 2026-11-25 · **Decision base:** [DEC-217](DECISIONS.md), [NF-3A](NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md), [NF-3B](NF_3B_FROZEN_BASELINES_ACCESSOR_GATE_2026-11-25.md), [the NF-3C decision handover](NF_3C_DECISION_HANDOVER_2026-11-25.md)
**Branch:** `feature/nf-3c-consumer-migration`, worktree `.local-data/nf-3c`, from the NF-3B decision handover `6794150` (R0/R1A, NF-1, NF-2 and NF-3B ancestry preserved).
**Status:** implemented and verified locally. **Not pushed, merged or deployed. No DEV or PROD gate is activated. NF-3D is not started.** Owner review required.

## 1. Owner decisions applied

| Decision | Applied as |
|---|---|
| **O-6, option A** | `nominal_frequency_origin` carries the NF-1 provenance of the effective value (`recording_metadata`, `import_supplied`, `assumed_default`, `manual`, `unusable`); `nominal_frequency_revision` added to the oscillation representation and spectrum responses. `manual` kept as the machine-readable value. Backend and frontend mapping shipped in **one commit** (`5a699ad`) |
| **O-6, BEN label (1)** | BEN upload-supplied value → `import_supplied` → "Supplied at import" (it used to read "from the recording") |
| **O-7, option A, interim** | Event detection keeps its response contract: effective value echoed when usable, the declared value otherwise. The NaN/∞ → `null` mismatch is **not** changed and is recorded below as an open defect |
| **O-11, option A** | The facts-card display contract is implemented (section 7, finding F-1: **the card is dormant**) |
| **D-1** | No DEV activation, no deployment configuration changed (compose, workflows, scripts and entrypoint are byte-identical); isolated local UAT only |
| **Wording** | From recording · Supplied at import · Assumed default · Manual override — Set in Recording Details · Unusable declaration. An unknown origin is "Origin not recognised": the page never gives a provenance it has not earned. Nothing says measured or verified |

## 2. Commits (all local; none pushed)

| SHA | Content |
|---|---|
| `19d9755` | **Phase A.** Pre-migration baselines G-1 (BEN), G-2 (compliance-measurement HTTP), G-3 (browser: three oscillation labels and the facts card). No production change |
| `0cd98f8` | Phase A addendum: compliance readiness and prepare HTTP behaviour. No production change |
| `3cb19ec` | **B1.** Event detection, compliance measurement, compliance readiness on the accessor |
| `5a699ad` | **B2.** Oscillation representation origin and revision; the three frontend label sites; the facts-card contract (atomic) |
| `c229d8d` | Test-only: three older baselines that the full run caught (see section 6) |
| (this report) | docs and evidence |

Phase A was committed and verified **before** any consumer behaviour changed (`git diff 6794150 19d9755`/`0cd98f8` touches tests and fixtures only).

## 3. Changed-file manifest

**Production code (16 files, +244/−83), `git diff --stat 6794150 HEAD -- backend/app frontend`:**

| File | Change |
|---|---|
| `services/synchronization_service.py`, `api/v1/synchronization.py` | event detection: accessor, refusal before the detector, declared value echoed when unusable |
| `services/compliance_measurement_service.py`, `services/compliance_readiness_service.py`, `api/v1/compliance.py` | classifier asks the accessor; unusable → "do not guess"; readiness names the declared value as unusable; Manual remedy offered only while the gate is open |
| `services/oscillation_representation_service.py`, `services/oscillation_spectrum_service.py`, `schemas/oscillation.py` | origin and revision from the accessor; unusable checked first |
| `services/oscillation_{spectrogram,damping,cross_signal,interpretation,mode_shape,coherence}_service.py`, `api/v1/oscillation.py` | the accessor threaded down (13 signatures, 22 call sites, 8 endpoints) |
| `frontend/index.html` | `wwNominalFrequencyOriginLabel` (three sites), `wwNominalFrequencyFactDisplay` and the dormant card renderer |

**Verified untouched** (`git diff 6794150 HEAD` is empty): `backend/app/domain/` (every algorithm, the power kernels, the detector), `backend/app/providers/`, `phasor_analysis_service`, `overcurrent_analysis_service`, `calculated_channel_service` (RMS and the fixed-50 Hz power code), `auto_base_service`, `api/v1/calculated_channels.py`, the accessor and the NF-1 service layer, and every compose, workflow, script and entrypoint file. No sample, calibration, PU or CT/VT code changed.

**Tests (28 files, +6,227 lines):** new `nf3c_baseline_scenarios.py`, `nf3c_approved_changes.py`, `nf3c_access_support.py`, three fixtures, `test_nf3c_pre_migration_baseline.py`, `test_nf3c_validating_consumers.py`, `test_nf3c_oscillation_origin.py`, `browser-tests/nf3c_origin_labels.spec.js`; existing tests updated only to pass the accessor, to name the approved wording, or to follow the approved changes (section 6).

## 4. Before/after behaviour matrix (Auto mode; gate closed unless stated)

"Before" is measured at the NF-3B tip (the committed baselines). "After" is measured on this branch. **Same** is proved by the baselines.

| Case | Event detection | Compliance measurement | Compliance readiness / prepare | Oscillation representation / spectrum | Facts card (dormant) |
|---|---|---|---|---|---|
| **Valid declared** (50, 60; 5 kHz and 4096 Hz-type) | **Same** | **Same** (`available`) | **Same** (RMS steps store the effective frequency) | **Same** value, status and reason; origin `recording_metadata`, label "From recording" (was "from the recording"); revision 0 added | plain "50 Hz", as today |
| **Assumed** (unparseable `lf`: 50 Hz) | **Same** | **Same** | **Same** | **Same**; origin `assumed_default`, "Assumed default" | "50 Hz (Assumed default)" when the authority's answer is supplied |
| **BEN, frequency supplied at import** | **Same** | **Same** | **Same** | origin `recording_metadata` → **`import_supplied`**, "Supplied at import" | "(Supplied at import)" |
| **Unusable: 0, NaN, ±∞** | **Same** (HTTP 200, `found:false`, same sentence, declared value echoed) | **HTTP 500 → 200 "unresolved"** (`ambiguous_measurement_metadata`, "Powerwave does not guess…") | **HTTP 500 → 200 "incompatible"**, no channel created (readiness, prepare) | status and reason **same** (`unavailable`, `invalid_nominal_frequency`); origin `recording_metadata` → **`unusable`**; wire value as before | "Unusable declaration"; declared value shown separately; never "null Hz"/"NaN Hz" |
| **Unusable: −50, 0.5** | **Same** | **Same** (already unresolved) | **Same** (already incompatible) | origin → `unusable`; rest same | as above |
| **Out of range: 1001** | **Same** | **`available` → unresolved** (it was classified as RMS) | **`source_rms` → `incompatible`** | origin → `unusable`; rest same | as above |
| **Declared 50 on a 60 Hz signal; assumed 50 on a 60 Hz signal** | **Same** | **Same** (unresolved) | **Same** | **Same** | n/a |
| **Mixed recordings** | n/a (one recording per call) | n/a | n/a | **cross-signal: first member decides, unchanged (NF-3G)** | n/a |
| **Manual set, server gate open (isolated process)** | the detector receives the Manual value; the response echoes it; an unusable recording becomes detectable | classification uses the Manual value; an unusable recording becomes `available` | the RMS step carries the Manual value; prepare creates channels storing it; a calculated channel follows its grounding recording | all responses report it: origin `manual`, "Manual override — Set in Recording Details", revision n; the spectrum no longer warns "assumed" | "60 Hz (Manual override — Set in Recording Details)" with "Imported: 50 Hz" separate |
| **Manual stored while the gate is closed** | **Same as Auto** (the stored value is ignored) | **Same** | **Same** | **Same** (revision shows the registry's count) | **Same** |
| **Reset to Auto, source deleted, workspace reset** | back to Auto | back to Auto | back to Auto (a new recording starts clean) | back to Auto | back to Auto |

**Intentional correctness fixes:** the three HTTP 500 paths (measurement, readiness, prepare) for an unusable declaration; an out-of-range declaration is no longer classified; the unusable origin is stated; the facts-card text. **Intentional contract changes:** the oscillation origin value set grows from two to five values; `nominal_frequency_revision` is additive. **Regression risks tested:** a Manual value mislabelled by the frontend (mutation N18/N19, browser tests), an unusable value reaching a numerical routine (spy tests, mutations N1, N8, N12), the Manual value ignored (N2, N7, N13).

## 5. Verification

### 5.1 Numerical (the frozen baselines, with approved changes separated)

The historical records are **never edited**. Every intentional change is one explicit entry in `tests/nf3c_approved_changes.py` (path, frozen value, new value, matrix row). The comparison tests require *history + approved entries = current*.

| Baseline | Recorded values | Differences from history | Covered by an approved entry | **Unexplained** |
|---|---|---|---|---|
| NF-3B frozen (kernels, in-process, HTTP, oscillation selection, power gates) | 2,349 | 13 (10 entries) | 13 | **0** |
| NF-3C pre-migration (compliance measurement, readiness, oscillation wire shape, BEN) | 3,164 | 106 (32 entries) | 106 | **0** |
| R1A COMTRADE | compared by its own test (it also permits R1A's own provenance additions) | 14 approved entries (origin of an unusable declaration only) | all | the R1A baseline and provenance tests pass |

(The "2,971 values" quoted for NF-3B counted every key/value pair; counted as leaf values the same file holds 2,349.) **Unchanged:** every engine-kernel statistic (RMS, sliding and single-point phasor, overcurrent RMS, detector, event onset, three-phase power), the power channels (values and stored 50.0 parameter), the power prerequisite gates, the oscillation member-order behaviour, and every phasor and overcurrent response including their HTTP 500s. **Approved changes only:** the measurement/readiness answers for unusable and out-of-range declarations, the oscillation origin labels and the additive revision. Evidence: `evidence/nf-3c-2026-11-25/numerical_verification_counts.json`.

### 5.2 New tests and mutation checks

* **Tests added:** 28 (baseline facts) + 54 (validating consumers) + 26 (oscillation origin) backend tests, and 25 browser tests; the strict xfail for compliance measurement **flipped and its marker was removed** in the same commit (6 strict expected-failures remain, each naming its slice: NF-3D ×2, NF-3E, NF-3F ×2, NF-3G).
* **Mutation checks (scratch copy of the committed tree): 19 of 19 killed.** Covered: usability ignored, imported value used instead of the effective one (measurement, event detection, oscillation), unusable value reaching the detector or the RMS numerics, readiness wording and the Manual remedy offered while the gate is closed, calculated-channel inheritance, origin hard-coded, revision dropped, an approved change removed from the overlay, a migrated consumer reading the imported value again, an unmigrated consumer silently changing (power window), the frontend giving an unknown origin a provenance, and the facts card printing "null Hz" again. Evidence: `evidence/nf-3c-2026-11-25/mutation_results.json`.
* **States exercised everywhere:** valid 50/60, assumed, 0, negative, NaN, ±∞, 0.5, 1001, BEN supplied/explicit/absent, Manual with the gate open, a stored value with the gate closed, set/change/reset revision, source deletion, workspace reset, a calculated channel inheriting from its recording.

### 5.3 Browser

654 tests in 34 files, run sequentially against the real backend (test backend with the server gate open): the NF-3C label spec (25), NF-2 Recording Details (53), Recording Info, all compliance specs, `oscillation_setup` (with its two label assertions updated to the approved wording), Waveform, PU-display, calculated-channel power, phasor and overcurrent.

**622 passed, 5 skipped, 27 failed.** The 27 are **exactly the failures already recorded as unresolved, with none new from NF-3C**:

| Group | Count | Status |
|---|---|---|
| `voltage-only-pu-display` VD-09/10/15/16, `waveform-empty-state` ×3, `waveform-measurement-values` ×5, `waveform-top-toolbar-migration` Per-Unit ×2 | 14 | the known baseline-equivalent WUI failures |
| `waveform-toolbar-t0-sync-refinement` ×7, `waveform-auto-fit-range` ×1, `phasor_analysis` playback ×1 | 9 | fail identically on pristine `c70182c` (NF-3B) |
| `compliance_measurement` ×2 (Bay/Measurement Group discovery, Manage Measurement Groups), `compliance_readiness` ×1 (Configure Base), `compliance-calibration-gate` ×1 (BEN5K Unverified) | 4 | **found now, because earlier slices did not run the compliance specs**; re-run against a scratch export of the NF-3B tip `6794150`: the **same four fail** (4 failed / 34 passed), so they pre-exist NF-3C |

All 27 stay recorded as **unresolved, not obsolete**. The Waveform and compliance code paths NF-3C touches are exercised by the 622 passes, including every compliance measurement and readiness state test and the oscillation setup flow. The facts-card and label cases are in `nf3c_origin_labels.spec.js` (section 7, F-1: the card is dormant).

### 5.4 Full backend regression

**14,810 passed, 405 skipped, 6 xfailed (strict), 0 failed** (40 min 22 s) on `c229d8d`, which carries the final production and test code (only this report and the HANDOFF line were edited afterwards). The NF-3B figure was 14,701 passed.

## 6. What the full run caught that targeted runs had not

A targeted regression (compliance, synchronization, oscillation, NF-1/2/3B) was clean, yet the **first full run showed 5 failures and 273 errors**. All were consequences of the approved changes, none a numerical regression, and each was fixed in `c229d8d` without weakening an assertion:

1. **273 fixture errors:** the R1A COMTRADE scenario runner imported the private `_nominal_frequency` function this slice replaced. It now asks the accessor; the R1A baseline goes through the same approved-changes overlay (only the **origin** of an unusable declaration changes, the recorded frequencies are identical).
2. **R1A provenance tests** expected `recording_metadata` for an unusable declared value; they now expect `unusable` for those and `recording_metadata` for usable ones (never `assumed_default`).
3. **The assumed-flag reader tripwire** still listed the oscillation representation; it no longer reads the flag (the authority does).
4. **An NF-3B gate test** asserted that no consumer reads a Manual value. NF-3B was right then; it is not now. It now proves the other half: event detection reports the Manual value, while the **unmigrated** phasor family and the power channels' fixed 50 Hz window are untouched by it.

## 7. Findings that need the owner's attention

* **F-1 — the Technical facts card is dormant (new, material to O-11).** Its only caller, `renderRecordingsTable()`, was removed with the Recording Events page (RD-1 UX-3); `#recordingsTableBody` is absent from the live DOM (an existing test asserts so). O-11 was approved for a surface that **no screen renders**. I implemented the display contract in the renderer and a pure formatter, and tested it by calling the renderer directly, but **no user can see it**. The live nominal-frequency display today is the **Recording Details > Recording Info** row, which is accepted NF-2 design: with the UI gate off it is the original read-only row (it already avoids "null Hz": a NaN shows "—"; 0 and −50 still show "0 Hz"/"−50 Hz"; an assumed 50 is indistinguishable from a declared 50). I did **not** change that row, because NF-2's acceptance says gate-off equals the original and a static test pins the exact line. **Decision D-2 for the owner:** (a) leave it (the contract waits in a dormant function); (b) adopt the same formatter in the live gate-off row (a visible change to NF-2's accepted default presentation, with its static test updated); or (c) remove the dormant card.
* **F-2 — correction to my NF-3B handover matrix.** I had described an unusable declaration in compliance readiness as a *blocked step with "frequency unknown"*. Measured: the shared input classifier raised first, so readiness, prepare and measurement answered **HTTP 500**. After NF-3C they answer 200 "incompatible"/"unresolved" with the generic "Could not confidently determine whether … is Instantaneous or RMS". The more specific wording ("the nominal frequency declared by this recording (0) is not usable") now exists, but is reached only when the channel's own form metadata is trusted-instantaneous (a blocked RMS step); for ordinary COMTRADE recordings the compliance screens therefore do **not** name the frequency as the cause. A follow-up could carry the cause through the classifier; it was not done because it widens the contract.
* **F-3 — a declared 1001 Hz** was classified as RMS and the measurement was "available"; it is now unresolved. Almost certainly a mis-declaration, but it is a visible change.
* **F-4 — refusal precedence in event detection:** an unusable frequency is now reported before an empty analysis window ("No samples available"); previously the order was reversed. Both are refusals; pinned by a test.

## 8. Known limitations and unresolved defects (not newly verified)

* **NF-3G (O-9):** cross-recording oscillation still takes the first member's frequency (order-dependent, frozen and unchanged). A Manual value on one of several recordings is therefore **not** order-independent for cross-signal analysis, and nothing here claims it is.
* **NF-3E (O-4):** stored calculated channels are not recomputed or flagged stale. RMS channels created by compliance preparation under a Manual value keep that frequency; if Manual later changes, readiness proposes a new step and the older channel is simply no longer reused. No stale cue exists yet.
* **O-7 defect (documented, not fixed):** a declared NaN or infinity is serialised as JSON `null` in the event-detection response although its schema field is a required non-null `float`; separate resolution is required before the final NF release.
* The oscillation responses carry only the effective value and its origin, **not the imported value**, so the "imported shown separately" part of the wording exists in the facts-card contract and in Recording Details (NF-2), not in the oscillation panels.
* Unmigrated and untouched by design: the power-channel fixed 50 Hz window and its stored parameter, the phasor family, overcurrent, the RMS kernels and builder default, the eligibility endpoint 500 (NF-3D to NF-3F), Auto Base (PU-MIG), CT/VT and calibration.
* The browser failures recorded in earlier slices (14 baseline-equivalent Waveform/PU failures, 9 that also fail on `c70182c`) and the 4 compliance-spec failures first found here (they fail identically on the NF-3B tip) remain **unresolved**; section 5.3 compares them as a set. None was triaged or touched.

## 9. Release boundary

Server-side gate default closed and unchanged; `NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED` appears in no deployment file (static test); `WW_NF_CONSUMERS_MIGRATED` is still `false`; the NF-2 UI gate is untouched. Manual works only in an isolated process that opens the server gate, as in the browser test backend.

## 10. Recommended next slice

**NF-3D — phasor family and overcurrent** (NF-3A section 9.3), because it removes the largest remaining defect family: the declared value reaches `1/f` unvalidated, which is what measurement and readiness did until this slice. Measured in NF-3B: the phasor endpoint answers HTTP 500 for a declared 0 Hz, and overcurrent for 0 Hz and NaN; the impedance, distance, sequence and line-to-line endpoints reach the same code and were **not** driven. Before it starts:

1. **O-5** (reuse `invalid_reference_frequency` for an unusable recording; recommended) needs an answer.
2. **O-6 for the phasor results** (origin and revision on analysis results): approved for oscillation only; confirm it extends.
3. **D-2** (facts card) can be settled independently.
4. Consider whether **NF-3G** should precede opening any gate, because Manual is not order-independent for cross-recording oscillation until then.
5. NF-3D's first commit should be the baseline hardening it already has (the phasor/overcurrent 500s are frozen in NF-3B), plus an HTTP baseline for the impedance, distance, sequence and line-to-line endpoints, which NF-3B did not drive.

## 11. Evidence

`docs/project-memory/evidence/nf-3c-2026-11-25/`: `mutation_results.json` (19 of 19), `numerical_verification_counts.json`, the two mutation-check scripts. Baselines: `backend/tests/fixtures/nf3c_baselines/nf3c_pre_migration_baseline.json` (generated from the unmodified NF-3B code), `nf3c_approved_changes.py`.
