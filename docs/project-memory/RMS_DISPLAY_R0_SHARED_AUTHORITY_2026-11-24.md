# RMS display mode — R0: shared RMS prerequisites and input-form classification

**Date:** 2026-11-24
**Branch / worktree:** `feature/rms-display-r0-shared-authority`, `.local-data/rms-r0`
**Status:** implemented and verified locally. **Not pushed, merged or deployed.** Stopped for owner review; R1 has not been started.
**Authority:** the owner's Stage 2 review outcome and R0 authorisation (2026-11-24). Design: `WAVEFORM_RMS_DISPLAY_MODE_STAGE2_TECHNICAL_DESIGN.md` (kept outside the repository by the design stage; section 6.3 is the R0 specification).

Labels follow the project convention: **[FACT]** verified, **[PROPOSAL]** not yet decided, **[OPEN]** needs an owner decision.

---

## 1. What R0 does

[FACT] R0 extracts, into one pure domain module, the two pieces of *composition* that surround the RMS engine and that every RMS consumer must apply identically. It exposes **no** new behaviour: no endpoint, no display path, no cache, no frontend change.

| Shared function (`backend/app/domain/rms_prerequisites.py`) | Meaning |
|---|---|
| `check_rms_window_prerequisites(time, f) -> RmsPrerequisiteFailure \| None` | the existing `rms_recording_long_enough`, then `rms_sampling_dense_enough`; first failure reported; the second predicate is not evaluated when the first fails |
| `classify_input_form(declared_waveform_form, time, values, f) -> InputFormClassification` | declared `rms` / `magnitude` / `instantaneous` wins and the detector is **not** run; otherwise the unchanged `classify_waveform_form` decides |

`InputFormClassification` = `outcome` (`instantaneous` / `rms_or_magnitude` / `uncertain`), `basis` (`declared_waveform_form` / `detector`), the declared string verbatim, and the raw detector result (or `None`).

**Provenance limitation (documented in the module).** [FACT] `basis` distinguishes *declared* from *detector-decided* only. A declared `waveform_form` can originate from recording metadata or from a calculated channel's own derivation (`derive_waveform_form`), and the string alone cannot tell which; the interface therefore does not claim it. Display-specific eligibility (R1) must carry that distinction separately if it needs it. A detector result is never promoted to a declared form.

**Separation of concerns.** [FACT] The module contains no mathematics (a test asserts no `sqrt` / `cumsum` / `evaluate_rms` / `mean` / `median` / `diff` / `allclose` calls), no override, no exception, no user-facing wording, no service/API imports, and does not validate the nominal frequency (`nominal_frequency_valid` stays a separate, unchanged predicate with the caller's own ordering). Sharing the classification therefore gives no other feature an override capability.

`calculated_channel_service.py` (19 insertions, 14 deletions): `check_rms_eligibility` delegates the classification and keeps its own statuses, reason strings and `override_required`; the two hard gates in `create_calculated_channel` call the shared function and map its result to the same exceptions and messages in the same order; three now-unused imports were removed.

## 2. Unchanged (protected)

[FACT] Byte-identical to the baseline commit: `calculated_channel.py` (`evaluate_rms`, `nominal_frequency_valid`, the window predicates, constants), `rms_detector.py`, `channel_classification.py`, `physical_calibration.py`, `per_unit.py`, `per_unit_reference.py`, `waveform_service.py`, `group_aware_per_unit.py`, `errors.py`, `api/v1/calculated_channels.py`, `api/v1/sources.py`, `schemas/calculated_channel.py`, `calculated_channel_registry.py`, `domain/source.py`, and the whole frontend. The power-channel branches that call the two window predicates directly (with `50.0` and their own messages) were deliberately left as they are.

## 3. Verification

| Check | Result |
|---|---|
| Baseline commit | `2a7ddc1`, tests and fixtures only, made **before** any production change; baseline SHA `3ed200c02a845fe1cc09707feb268128d46b112c` |
| Mathematical golden vectors (38 cases) | all pass at three separately asserted levels: dtype/shape; exact numerical equality with matching NaN positions; **binary** equality of raw bytes and SHA-256 (frozen on Python 3.12.10 / NumPy 2.4.6 / Windows; no environmental difference observed) |
| Service + API behavioural baseline (148 outcomes) | all reproduced exactly: eligibility status/reason/override, exception class/code/message, validation precedence, created-channel metadata, sample and timestamp hashes, HTTP status and bodies |
| Differential corpus (1 800 outcomes, seeded, pre-R0 tree vs refactored tree) | identical |
| Baseline sensitivity (10 injected regressions in an out-of-tree copy: gate order, reason wording, override ignored, uncertain made suitable, engine window rounding, engine boundary, engine NaN rule, frequency precedence, detector threshold, calibration gate) | all 10 caught |
| New shared-authority tests | 37 pass |
| Existing Calculated Channels and related suites (18 files) | 819 passed, unchanged |
| Full backend suite, pre-R0 tree | 13 584 passed, 405 skipped, 0 failed |
| Full backend suite, after R0 | **13 870 passed, 405 skipped, 0 failed** (+249 baseline +37 new; identical skips) |
| Existing tests | none modified (`git diff --name-status` over `backend/tests` shows only additions) |

Reproduction: `python tests/fixtures/rms_golden/generate_rms_golden.py` and `.../generate_rms_service_baseline.py` document how the baselines were produced; both refuse to run unless `backend/app` matches `HEAD`. They must **not** be re-run to make a failing test pass.

## 4. Observations (pre-existing, not changed)

- [FACT] `POST .../calculated-channels/rms-eligibility` does not validate `nominal_frequency_hz` (only creation does). A value of `0` returns HTTP 500 (`ZeroDivisionError` in the detector); other out-of-range values can raise `ValueError` / `IndexError` in the eligibility service. These outcomes are frozen in the baseline. [OPEN] Fixing them is a behaviour change for separate approval (change governance); R1 must not inherit them.
- [FACT] `providers/comtrade.py` replaces an unparseable `lf` line by 50 Hz with only a Python warning, so declared and assumed frequency are indistinguishable for COMTRADE. Owner decision D6 (a separate small slice) covers it; R0 did not touch it.

## 5. Mandatory follow-up gates recorded from the owner's review (not implemented in R0)

- **R1 — frequency resolution:** distinguish missing, assumed and explicitly invalid declared frequency; never silently convert an explicitly invalid frequency to 50 Hz; preserve a valid assumed frequency; reconcile with the Calculated Channels validation; D6 provenance separately.
- **R1/R3 — eligibility limits:** the batch eligibility endpoint must not become an unbounded CPU or shared-thread-pool workload.
- **R3 — resource governor:** review admission before expensive eligibility and allocation; bound in-flight requests, waiters, transient and retained memory; prevent late computations from repopulating caches after source/workspace deletion; account for active references to evicted arrays; admission estimates must not materially underestimate the real engine path; no unreviewed placeholder VPS limits reach production.
- **R2 — API compatibility:** omit the new response field where required to keep native responses unchanged (resolving the "byte-identical vs nullable field" contradiction); display RMS uses `propagate` null behaviour, with the equivalence guarantee stated for identical samples, frequency and null policy.
- **R4 — pane state:** separate temporary hiding from permanent removal and investigate preserving representation state across hiding; return a pane to native and disable RMS when its last eligible channel is removed; temporary recreation must not trigger the deliberate regroup-conflict rule; do not extend the control to mixed-quantity custom panes beyond the approved Voltage/Current scope.

## 6. Proposed documentation updates (not applied; existing project-memory documents were not modified)

- `CURRENT_STATE.md`: a short R0 paragraph (shared prerequisites extracted; baselines frozen; nothing exposed).
- `HANDOFF.md`: this slice's outcome, the stop point and the §5 gates.
- `DECISIONS.md`: **no number is reserved here.** The highest number found on any local branch on 2026-11-24 is DEC-216 (with Amendment 7 on the PU-MIG audit branch). A decision for the RMS display feature should be numbered at owner approval, after re-checking parallel branches.
- `MIGRATION_PLAN.md`: add the R0 → R1 → R3 → R2 → R4 → R5 sequence once the owner approves it as a plan item.

## 7. Next step

Owner review of this slice. R1 starts only on explicit approval.
