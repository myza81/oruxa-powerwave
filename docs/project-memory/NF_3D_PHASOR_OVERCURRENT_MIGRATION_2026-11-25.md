# NF-3D — Phasor family and overcurrent migration

**Date:** 2026-11-25 · **Decision base:** [DEC-217](DECISIONS.md), [NF-3A](NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md), [NF-3B](NF_3B_FROZEN_BASELINES_ACCESSOR_GATE_2026-11-25.md), [NF-3C](NF_3C_CONSUMER_MIGRATION_2026-11-25.md) and the owner's NF-3C review (D-2, O-5, O-6)
**Branch:** `feature/nf-3d-phasor-overcurrent`, worktree `.local-data/nf-3d`, from NF-3C `446b566` (R0/R1A, NF-1, NF-2, NF-3B and NF-3C ancestry preserved).
**Status:** implemented and verified locally. **Not pushed, merged or deployed. No DEV or PROD gate is activated; `WW_NF_CONSUMERS_MIGRATED` is still false. NF-3E is not started.** Owner review required.

## 1. Owner decisions applied

| Decision | Applied as |
|---|---|
| **D-2** | The dormant Technical facts card is **unchanged**; no NF-2 Recording Info change. Recorded here: the O-11 renderer is **implemented but not reachable through the current UI** (its only caller left with the Recording Events page). It is **not** a delivered live feature. Unused-code cleanup is a separate, explicitly reviewed task |
| **O-5** | `invalid_reference_frequency` is reused only where its established meaning matches: an **unusable nominal-frequency authority** (0, negative, NaN, infinite, outside 1–1000 Hz) and an **invalid explicit override** (its existing sentence, unchanged). A **valid** frequency the sampling cannot support is a *different* condition and keeps its own existing reason, `insufficient_sampling_density`. No new common reason was created |
| **O-6** | Phasor, phasor-diagram, overcurrent, impedance, sequence-components and distance results carry `nominal_frequency_origin`, `nominal_frequency_revision` and a per-recording `nominal_frequency_sources` list, in the unchanged five-value origin vocabulary. They describe the frequency **the calculation used**, per recording; an explicit `reference_frequency_hz` has none; `manual` is never described as measured or verified |
| Baseline / constraints | New isolated worktree on `446b566`; no push, merge or deployment; Manual not enabled in DEV/PROD |

## 2. Commits (all local; none pushed)

| SHA | Content |
|---|---|
| `ac198ff` | **Phase A.** Scenario runner, frozen pre-migration baseline (generated from the unmodified NF-3C tip, two identical runs), the historical-facts tests and independent oracles with 5 strict xfails. Tests and fixtures only |
| `3179cd4` | **Phases B–C.** The migration, the approved-changes manifest and its classification test, the behaviour tests, and the deliberate guard-inventory and older-test updates |
| (this report) | docs and evidence |

`git diff 446b566 ac198ff` touches tests and fixtures only: no production file changed before the baseline was committed.

## 3. Affected-consumer and changed-file manifest

**Frequency-reading points found and migrated** (NF-3A C-01, C-02, plus the paths that reach them):

| Where the declared value used to be read directly | Now |
|---|---|
| `phasor_analysis_service`: compute, diagram preparation, diagram readiness (three duplicated blocks, five attribute reads) | `decide_reference_frequency()` over `NominalFrequencyAccess` |
| `overcurrent_analysis_service`: compute, readiness, recorded input (three blocks, four reads) | same |
| reached through the phasor diagram: impedance, impedance locus, sequence components, distance, distance locus, line-to-line readiness and creation, compliance readiness (NF-3C code) | the accessor is passed down; their results carry the provenance |

**Production files (22):** new `domain/frequency_provenance.py`, `schemas/frequency_provenance.py`, `services/analysis_reference_frequency.py`; changed `domain/{phasor,overcurrent,impedance,distance_protection,sequence_components}.py` (one additive field each), the six result schemas (inherit the provenance mixin), `services/{phasor,overcurrent}_analysis_service.py` (the migration), `services/{impedance,distance_protection,sequence_components}_analysis_service.py`, `line_to_line_voltage_service.py`, `compliance_readiness_service.py`, `api/v1/engineering_contexts.py` (ten endpoints) and `api/v1/calculated_channels.py` (two). **No frontend, kernel, estimator, calibration, PU, CT/VT or sample code changed**; `domain/phasor.py` and `domain/overcurrent.py` gained only the provenance field.

**Test and fixture files:** Phase A (`nf3d_baseline_scenarios.py`, the baseline generator and JSON, `test_nf3d_pre_migration_baseline.py`, `test_nf3d_independent_oracles.py`); NF-3D approved-changes manifest (`nf3d_approved_changes.json`, its generator, `nf3d_diff_tools.py`, `test_nf3d_approved_changes.py`, an extension of `nf3c_approved_changes.py`); `test_nf3d_behaviour.py`; deliberate updates to the call-path guard inventories and the NF-1 tripwire (two rows removed, importers added); adapted older tests (section 6).

## 4. Frozen baselines (Phase A, before any production change)

`backend/tests/fixtures/nf3d_baselines/nf3d_pre_migration_baseline.json` (generated from `446b566`; two identical runs; defects included): 14 recordings (valid 50/60 Hz at 5000 and 4000 Hz — integer 100 and 80, non-integer 83.33 and 66.67 samples per cycle —, 60 Hz at 4096 Hz, assumed, a declared 50 on a 60 Hz signal, and the six unusable declarations), 8 explicit-override cases, 4 two-recording cases, ten endpoints each; 13,309 lines.

**Legacy defects recorded as defects, not approved behaviour:**

| Unusable declaration | Legacy phasor / diagram / overcurrent / impedance / sequence / distance |
|---|---|
| `0` and `inf` | **HTTP 500** on every endpoint |
| `nan` | overcurrent **HTTP 500**; the others a 200 `reference_frequency_conflict` (the wrong cause) |
| `-50`, `0.5`, `1001` | 200 `waveform_form_not_eligible` (the wrong cause) **and the phasor diagram and sequence components were computed** from a meaningless window (a −50 Hz or 0.5 Hz cycle) |

The last row is the most important finding of Phase A: for three unusable values the legacy code did not merely give a wrong refusal; it **returned numbers**. They are now refused (section 5).

## 5. Before/after behaviour matrix (Auto mode; gate closed unless stated)

| Case | Before (`446b566`) | After |
|---|---|---|
| Valid declared 50 or 60 Hz (5000 / 4000 Hz; integer and non-integer samples per cycle) | computed | **identical numbers**; additive provenance (`recording_metadata`, revision 0, the source) |
| Assumed 50 Hz (`lf` unparseable) | computed | identical numbers; origin `assumed_default` |
| Declared 50 on a 60 Hz signal | as before | unchanged, origin `recording_metadata` (the declaration is used as declared; no claim it is the waveform frequency) |
| Declared `0` / `inf` | HTTP 500 | HTTP 200 `invalid_reference_frequency`, message names the declared value ("0", "infinite"); no kernel, no detector |
| Declared `nan` | 500 or `reference_frequency_conflict` | 200 `invalid_reference_frequency` ("not a number") |
| Declared `-50` / `0.5` / `1001` | `waveform_form_not_eligible`; diagram and sequence **computed** | 200 `invalid_reference_frequency`; **nothing computed** |
| Explicit valid `reference_frequency_hz` | wins | wins; **no provenance** (the caller's own value); wins even over an unusable declaration |
| Explicit `0` / negative / `1001` | `invalid_reference_frequency`, existing sentence | unchanged |
| Valid frequency the sampling cannot hold (1000 Hz on a 5 kHz recording: 5 samples per cycle; phasor minimum 8) | `waveform_form_not_eligible` (the detector answered "uncertain") | `insufficient_sampling_density` with "fewer than 8 samples per cycle at 1000 Hz" |
| Two recordings: both usable and equal | computed | computed; origin if shared, revision `null` (revisions are per recording), both sources listed |
| Two recordings: usable but different | `reference_frequency_conflict` | unchanged |
| Two recordings: one unusable | overcurrent 500, diagram `reference_frequency_conflict` | both `invalid_reference_frequency` |
| Manual value stored, server gate **open** | declared value read (Manual ignored) | Manual **is** the frequency; origin `manual`, revision from the registry; an unusable recording becomes computable |
| Manual value stored, gate **closed** | cannot be stored | cannot be stored; a value stored earlier while open is **ignored** (proved by swapping the accessor to closed) |

The approved-changes manifest records every difference to the two baselines that cover these endpoints: **946** entries against the NF-3D baseline (576 additive provenance fields, 347 unusable-recording refusals, 23 sampling-reason changes) and **79** against the NF-3B `http` group (57 and 22). `test_nf3d_approved_changes.py` restricts the manifest to those three kinds, so a numerical or other change cannot hide in it: provenance entries are only new keys with the recording's own origin (or null); refusal entries only touch unusable recordings, never introduce a `computed` status or a number, turn every legacy 500 into a typed 200, and use only `invalid_reference_frequency`; sampling entries touch only the one scenario and only the existing reason.

## 6. Verification

### 6.1 Numerical oracles (independent of the code under test)

`test_nf3d_independent_oracles.py`, 22 tests that passed **before** the migration and still pass: closed forms for the pure windows (|V| = 100 V at 0°/−120°/+120°; pre-fault I = 1 A at −30°; settled fault I = 10 A at −75°) and a direct summation written from the definition (half-open trailing window, `X = √2/N Σ x e^{−jωt}`, `RMS = √mean x²`) for the fault-onset window, which holds a decaying DC offset and has no closed form. Integer samples per cycle agree to round-off (1e-6); non-integer to the NF-3A tolerances (1.05 % magnitude, 0.6°) for the pure windows and to round-off against the direct sum. At 50 and 60 Hz, 5000 and 4000 samples/s. The five Part-2 strict xfails (invalid −50, the sampling reason, the two provenance results, Manual) and the two NF-3B zero-Hz xfails are now ordinary passing tests.

**Frozen-baseline comparison:** history + NF-3C changes + the NF-3D manifest = current output, for 14 + 8 + 4 scenarios and the NF-3B `http` group, **0 unexplained differences**; every valid recording differs from the baseline only by the additive provenance fields (so every number, angle, RMS and window is byte-equal within the 1e-9 tolerance of the existing comparison).

### 6.2 New tests and mutation checks

`test_nf3d_behaviour.py` (233 tests, 168 of them the property grid below): usable/assumed/downstream provenance; every unusable value on every surface (no 500, nothing computed, reason, no echoed value, **no 50 Hz substitution**, message wording with the gate open and closed); **spies proving no detector or estimator is called with an unusable frequency**, and that a valid one receives exactly the declared frequency; explicit override; Manual (50 and 60, override of a valid declaration, revision advance, clearing, closed gate, stored-while-open ignored when closed, wording); two-recording provenance, source and workspace isolation, source deletion; the sampling reason; and a **property grid (7 sampling rates × 12 frequencies × 2 estimators) proving the pre-check refuses only what the estimator itself can never compute at any window alignment, and allows only what it can**.

**Mutation checks, 17 of 17 killed** (`evidence/nf-3d-2026-11-25/mutation_results.json`, run on a copy of the working tree): an unusable authority substituting 50 Hz; the refusal skipped; an invalid override accepted; the wrong reason; provenance dropped, hard-coded or wrong (mixed origins collapsed, revision of the first recording, an override carrying a provenance, the wire mixin or the router dropping it); the sampling rule stricter (floor), never refusing, skipped in the phasor service or reporting a form refusal (phasor and overcurrent); and the server gate ignored. **One mutation survived the first run** (overcurrent reporting its sampling limit as a form refusal): no test exercised the overcurrent minimum of 4 samples per cycle. Two tests were added (a 2 kHz recording at 1000 Hz; and 5 samples per cycle, which the phasor refuses but overcurrent accepts) and the mutation was killed.

### 6.3 Result-provenance validation

Origin, revision and sources are asserted per recording and per surface (phasor, diagram, overcurrent, impedance, sequence), against the recording's own authority; a Manual value on one source never reaches another source or workspace; deleting a source removes its Manual value; an explicit override never carries a recording provenance; and the vocabulary is the five NF-1 values (a test over the whole manifest checks it). A refusal carries no provenance, because no frequency was used.

### 6.4 Full backend regression

**15,109 passed, 405 skipped, 4 xfailed (strict), 0 failed** (52 min 8 s) on `3179cd4`. The NF-3C figure was 14,810 passed, 405 skipped, 6 xfailed: +299 passed (the Phase A tests, the NF-3D behaviour and manifest tests, and the former xfails), the skip count identical, and two fewer xfails because the two NF-3B zero-Hz xfails that named NF-3D now pass. The four remaining strict xfails name NF-3E, NF-3F (two) and NF-3G.

The first full run (before the tail fixes) showed **26 failures**, all consequences of the approved migration and none numerical: 18 in `test_phasor_calibration_gate.py`, 2 each in `test_calculated_timing_authority.py` and `test_time_reference_interpretation.py` (older tests that call the private candidate readers directly and now need the accessor), and 4 in `test_nf3b_server_side_release_gate.py`, which asserted that the phasor family was *not* yet influenced by a stored Manual value. Correct for NF-3B, not now; it now asserts that the phasor result reports the Manual frequency and origin and that a refusal for another reason never blames the frequency. No assertion was weakened, skipped or relabelled. Targeted runs would not have found these (the lesson of NF-3C stands: always run the whole suite).

### 6.5 Browser regression

Focused set, 561 tests across: phasor analysis, overcurrent, impedance, distance (four specs), sequence components, line-to-line voltage, NF-2 Recording Details nominal frequency, NF-3C origin labels, oscillation setup, the compliance specs, phasor bare context, D5A overcurrent side, and the two BEN5K calibration-gate specs. Frontend unchanged since NF-3C, so the comparison is a behaviour check of the migrated backend.

First run (isolated ports 8102/8200): **511 passed, 3 skipped, 47 failed.** Classified:

| Group | Count | Verdict |
|---|---|---|
| NF-2 spec (`nf2_recording_details_nominal_frequency`) | 35 | **Harness artefact, not a failure of the code.** The spec reads the repository's `frontend/config.js` (pinned to :8000) to build its gated config, so on my relocated :8200 backend every page said "Backend unreachable". Re-run on the default ports: the spec **passes in full** |
| `compliance_measurement` ×2, `compliance_readiness` ×1, `compliance-calibration-gate` ×1 | 4 | Known since NF-3C; **fail identically on the unmodified NF-3C tip `446b566`** (re-run there in this session) |
| `ben5k-phasor-calibration-gate` Scenarios A/B, C/D, E | 3 | **New to the recorded sets but not caused by NF-3D**: they fail identically on `446b566` (re-run there in this session). Not triaged |
| `phasor_analysis` "Waveform and Phasor share one Playback clock across page navigation" | 1 | Known (fails on `c70182c`, recorded in NF-3C) |
| **Net unexplained by an earlier baseline** | **0** | |

Re-run on the default ports of the specs that failed in the isolated run (NF-2, BEN5K phasor gate, the three compliance specs): **78 passed, 1 skipped, 7 failed**, the 7 being exactly the 4 compliance and 3 BEN5K failures above, identical on `446b566` (**38 passed, 7 failed** on the same specs there; it has no NF-3D tests). The 35 remaining failures of the first run are therefore all explained; the other NF-3C sets (the 14 Waveform/PU baseline-equivalent failures and the t0-sync and auto-fit failures of the 9 that fail on `c70182c`; the ninth is the phasor playback test above) are in specs this focused run did not include and remain unresolved and untouched. The 27 failures recorded in NF-3C are therefore **27 + 3 = 30 known unresolved**.

## 7. Findings that need the owner's attention

* **F-1 — the legacy code returned numbers for unusable frequencies** (section 4): the phasor diagram and sequence components were *computed* for declared −50, 0.5 and 1001 Hz. They are now refused. Any saved screenshot or note that relied on such a result was not engineering-valid.
* **F-2 — `insufficient_sampling_density` is reached by a valid frequency that the sampling cannot hold:** an explicit `reference_frequency_hz`, a Manual value (gate open), or a recording that declares a high frequency on a low sampling rate (for example 500 Hz declared on a 2 kHz recording). The pre-check uses the estimators' own minimum samples per cycle (8 phasor, 4 overcurrent) and `ceil(samples per cycle)`, so it refuses only what the estimator could **never** compute and never changes a result in the band just under the minimum, where the window's alignment decides. **No threshold was invented.**
* **F-3 — the form detector's own limits are unchanged.** It answers "uncertain" for nominal frequencies below about 3 Hz (documented earlier) and for signals it cannot classify; that is still reported as `waveform_form_not_eligible`. NF-3D did not touch the detector, and does not claim a frequency is supported merely because NF-1 accepts 1–1000 Hz.
* **F-4 — refusal bodies carry no provenance** (null origin, empty source list): no frequency was used. An engineer looking at "why was my Manual value not used" gets the refusal message, not an origin. If the owner wants the refusal to name the origin (`unusable`) of the offending recording, that is an additive change.
* **F-5 — compliance wording (carried from NF-3C F-2):** line-to-line readiness now reaches the same refusal, but the compliance step text for an unusable frequency is still generic for ordinary COMTRADE channels.

## 8. Remaining engineering limitations (not newly verified, not changed)

* **Locus responses** (impedance locus, distance locus) carry no provenance fields: they do not report one frequency but a series, and were not in the approved scope. The refusal itself is typed and tested.
* **NF-3E (O-4):** stored calculated channels are not recomputed or marked stale; nothing here changes that. **NF-3F:** the power channels' fixed 50 Hz window and stored parameter. **NF-3G (O-9):** the first-member rule for cross-recording oscillation. All untouched, as instructed. The O-7 event-detection NaN → `null` schema mismatch stays a tracked issue.
* An analysis with a recording whose sampling is irregular is still refused by the estimators for that reason (`irregular_sampling_not_supported`), unchanged; the sampling pre-check uses the median step and leaves fewer-than-two-sample inputs to the estimators.
* The browser failures recorded in earlier slices remain unresolved and untouched (section 6.5).
* Manual remains enabled only in an isolated process that opens the server gate.

## 9. Release boundary

Server gate default closed and unchanged; no deployment file mentions the Manual variable; `WW_NF_CONSUMERS_MIGRATED` false; NF-2 UI gate untouched; no frontend file changed. Nothing is pushed, merged or deployed.

## 10. Recommendation for NF-3E

NF-3E (**O-4**: stale calculated channels after a nominal-frequency change) is the next dependency before any gate is opened for engineers: Manual can now change phasor and overcurrent results *and* the RMS channels compliance preparation creates, but a stored calculated channel keeps the frequency it was built with and nothing tells the user. Before it starts, the owner needs to decide O-4 (flag stale, recompute on demand, or block). Independently, **NF-3G** (O-9) should be scheduled before opening Manual to a multi-recording oscillation workflow, and the NF-3C browser failure sets (27 in three groups) should be triaged in their own task. NF-3E should begin with the same Phase-A freeze.

## 11. Evidence

`docs/project-memory/evidence/nf-3d-2026-11-25/`: `mutation_results.json` (17 of 17) and `mutation_checks.py`, `numerical_and_regression_counts.json`. Baselines and manifest: `backend/tests/fixtures/nf3d_baselines/` (`nf3d_pre_migration_baseline.json` generated from the unmodified `446b566`, `nf3d_approved_changes.json` and its generator).
