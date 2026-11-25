# NF-3B — Frozen baselines, central accessor, server-side release gate, call-path guard

**Date:** 2026-11-25 · **Decision base:** [DEC-217](DECISIONS.md), NF-3A assessment ([NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md](NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md))
**Branch:** `feature/nf-3b-frozen-baselines-accessor-gate`, worktree `.local-data/nf-3b` · **Base:** `c70182c` (NF-3A) on `2adf9db` (NF-2 closure) on the accepted NF-1/R0/R1A ancestry.
**Status:** implemented and verified locally. **No engineering consumer, algorithm, PU/CT-VT behaviour or sample is changed.** Not pushed, merged or deployed. NF-3C is not started; owner review is required first.

## 1. What NF-3B is

A non-output-changing foundation for migrating the nominal-frequency consumers (NF-3C onward):

1. **Frozen numerical baselines** that reproduce today's frequency-dependent behaviour, defects included, so every later slice can show "Auto is identical" and exactly what it changed.
2. **A central accessor** (`NominalFrequencyAccess`) that engineering consumers will be required to use. Unused by any consumer in NF-3B.
3. **A server-side release gate** (O-1) for the Manual override, closed by default and refused in any deployed build.
4. **A consumer call-path guard** that freezes an exact inventory of every frequency read, key, literal, default and frontend token.

## 2. Owner decision register (O-1 to O-12)

Status words: **Approved** = confirmed by the owner's NF-3B instruction; **Approved in principle** = accepted as a direction, the action itself still needs its own slice and evidence; **Proposed** = the recommendation below is mine and is **not** an owner decision; **Pending** = needs an owner answer before the slice that depends on it.

| ID | Decision | Status | Effect on NF-3B | Depends on it |
|---|---|---|---|---|
| **O-1** | Server-side enforcement of the release gate | **Approved** (instruction of 2026-11-25) | **Implemented** (section 5) | NF-3B |
| **O-2** | Correct the frequency-dependent power channels (P −11.8 % / Q −13.2 % on a 60 Hz recording) and require V and I to agree | **Approved in principle.** The numerical correction is **not** implemented and **not** approved as a specific change | None. The defect is frozen as a defect (section 4); the strict-xfail oracle names NF-3F | NF-3F: golden vectors and the V/I-agree refusal still need approval at that slice |
| **O-3** | Auto Base frequency-dependent changes belong to PU-MIG | **Approved** | None. C-17 stays frozen and untouched; PU-MIG S1–S6 not started | NF-3I wording ("setting does not apply to Auto Base evidence") |
| **O-4** | Existing channels after a change: stale marker plus one advisory only | **Proposed** (not approved) | None | NF-3E |
| **O-5** | Unusable recording in the phasor family and overcurrent: reuse `invalid_reference_frequency` | **Proposed** | None | NF-3D |
| **O-6** | Additive provenance fields (origin, revision) in analysis results and new calculated-channel parameters | **Proposed** | None. The accessor carries origin and revision so O-6 costs no redesign | NF-3C/D/E |
| **O-7** | Event detection when unusable: keep `nominal_frequency_hz: float` (non-null) | **Proposed** | None | NF-3C |
| **O-8** | RMS builder for an unusable recording: no preselected frequency | **Proposed** | None | NF-3E |
| **O-9** | Oscillation cross-signal: agreement-or-`nominal_frequency_mixed` | **Proposed** | None. The accessor's multi-recording contract is *compatible* with it but does not decide it | NF-3G |
| **O-10** | Fix the eligibility-endpoint HTTP 500 inside NF-3E | **Proposed** | None. Frozen as a defect (R0 baseline plus section 4) | NF-3E |
| **O-11** | The Technical facts card shows the effective value | **Proposed** | None | NF-3C |
| **O-12** | Gate-opening evidence: triage of the 14 unresolved WUI failures, mandatory interactive UAT | **Pending.** The 14 stay recorded as unresolved | None | NF-3I |

**Further decisions that would affect NF-3B.** None needed an owner answer, so work did not stop. Six implementation choices were made inside the approved O-1 frame; each is small, reversible and changes no engineering output. They are listed so the owner can veto any of them at review:

| # | Choice | Why | Reversible by |
|---|---|---|---|
| N-1 | `PUT mode=manual` while closed → **409** with code `manual_nominal_frequency_disabled` | 409 is the status O-1's own text recommended; the code name is new | renaming one constant |
| N-2 | `PUT mode=auto` is **allowed** while closed; `GET` always allowed | Returning to Auto only removes a value; "preserve GET access" | one condition |
| N-3 | A **deployed build refuses to start** with the variable set (`ConfigurationError`) | "Prevent accidental enablement in normal DEV/PROD configuration". Consequence: an isolated environment must be a non-deployed process (no `APP_VERSION`, not `production`). NF-3I removes the refusal in the same reviewed commit that introduces the deliberate deployment path | one condition in `load_settings` |
| N-4 | One **additive** read-only field `manual_override_enabled` on the NF-1 `GET`/`PUT` response | So a client can see the policy instead of discovering it from a 409; optional for every existing client | removing one field |
| N-5 | Multi-recording agreement tolerance = the one the phasor family already uses (`math.isclose`, rel 1e-9, abs 1e-9); the common value is the smallest of the agreeing values | Reuses existing behaviour; keeps the answer independent of recording order | the two constants |
| N-6 | The Playwright **test** backend opens the gate (`browser-tests/playwright.config.js`) | NF-2's browser tests drive real `PUT`s. The file is a test harness, not a deployment path, and a static test proves no deployment file mentions the variable | removing one env entry |

## 3. Scope protection (verified)

* No engineering consumer imports the accessor (guard test, section 7). No consumer file changed: `git diff c70182c..HEAD --stat -- backend/app` lists only the files in section 8.
* `WW_NF_CONSUMERS_MIGRATED` is still `false`; `frontend/` is byte-identical to `c70182c` (section 8); the UI gate flag `nominalFrequencyOverride` is still absent from every configuration path.
* No RMS, phasor, power, protection or oscillation algorithm, sample, calibration, PU or CT/VT code changed.
* Nothing pushed, merged or deployed. No other worktree touched.

## 4. Frozen numerical baselines

**Files.** `backend/tests/nf3b_baseline_scenarios.py` (scenario runner), `backend/tests/fixtures/nf3b_baselines/generate_nf3b_baselines.py` (generator) and `nf3b_frozen_baselines.json` (the frozen outcomes), `backend/tests/test_nf3b_frozen_baselines.py` (comparison and named legacy defects), `backend/tests/test_nf3b_independent_oracles.py` (desired behaviour). Committed first, as `077814e`, **before any production change**; generated from the pristine NF-3A tree (`baseline_git_sha: c70182c…`). The generator refuses to write the committed file if `backend/app` differs from HEAD or if two consecutive runs differ.

**Two kinds of test, kept apart.**

| Kind | File | What it asserts | Status today |
|---|---|---|---|
| **Legacy characterisation** | `test_nf3b_frozen_baselines.py` | The consumers still do exactly what they did at `c70182c`, defects included. A value here is **not** approved as correct | passes |
| **Engineering oracle, part 1** | `test_nf3b_independent_oracles.py` | The kernels are exact (round-off) when handed the matching frequency at integer samples per cycle, and inside the proposed tolerance at 4096 Hz (non-integer) | passes |
| **Engineering oracle, part 2** | `test_nf3b_independent_oracles.py` | What each consumer **must** do once migrated | **7 strict `xfail`**, each naming the slice that fixes it |

A strict xfail that starts passing is a *failure* of the suite, so the slice that fixes a defect must remove the marker deliberately. Nothing can rot into a silently accepted defect.

**What is frozen** (four groups; 50 Hz, 60 Hz and non-integer 4096 Hz samples per cycle throughout):

| Group | Cases | Content |
|---|---|---|
| Engine kernels | 8 grid cases (rate × signal × nominal) | trailing RMS, sliding phasor, single-point phasor, overcurrent RMS, waveform-form detector, event-onset detector; plus power single-phase P/Q/S and three-phase with the window left at its default, 50 and 60 |
| Invalid inputs | 7 values: 0, −50, NaN, +∞, −∞, 0.5, 1001 | each kernel's outcome, recorded as a result or the exception **class** |
| In-process consumers | 11 recordings (50, 60, assumed, assumed-on-a-60 Hz-signal, declared-50-on-60, 0, −50, NaN, +∞, 1001, 0.5) | compliance readiness value, compliance-measurement input type, oscillation representation (value, origin, verdict), event-detection view, power channels (stored parameter, unit, value statistics) |
| HTTP consumers | 11 real uploads (5 kHz and 4096 Hz, `lf` 50/60/unparseable/0/−50/NaN/1001) | upload, the NF-1 `GET`, source summary, detect-event, phasor, overcurrent, power channels |
| Oscillation selection | 3 component frequencies × 8 member combinations | the verdict as a function of the members' nominal frequencies and **order** |

The RMS creation and eligibility behaviour (including the eligibility HTTP 500) is already frozen by the R0 baseline and the COMTRADE importer by R1A; they are referenced, not duplicated, and a test proves the R0 file still records the 500.

**Defects now reproduced by tests** (frozen as defects; none fixed):

| Defect | Measured today | Slice |
|---|---|---|
| D-A power ignores the recording's frequency | on a 60 Hz recording the stored parameter is `50.0` and the active-power mean is **−11.76 %** (HTTP, 5 kHz) | NF-3F |
| D-B eligibility endpoint | HTTP **500** for 0; 200 for −50 (R0 file) | NF-3E |
| D-C phasor, declared 0 Hz | HTTP **500** (**now measured end to end**; NF-3A had only inferred it) | NF-3D |
| D-C overcurrent, declared 0 Hz or NaN | HTTP **500** (measured) | NF-3D |
| D-C compliance measurement, declared 0 / NaN | `ZeroDivisionError` / `ValueError` | NF-3C |
| D-D oscillation selection | with a 55 Hz component, recordings (50, 60) and (60, 50) give **different** verdicts: the first member decides (now measured, not only inspected) | NF-3G |

**New observations recorded by the baseline** (not defects of NF-3, but relevant to later slices):

* A **60 Hz signal in a recording whose frequency was assumed (50 Hz)** is refused by the phasor and overcurrent gates as `waveform_form_not_eligible`. Today there is no way to correct that; a Manual 60 Hz is what NF-3D must make possible.
* A **4096 Hz ASCII COMTRADE** is refused as `irregular_sampling_not_supported` before any frequency is used, because ASCII timestamps are written to 0.1 µs (244.140625 µs becomes 244.1). This is the limit NF-3A section 16 anticipated, now frozen. The non-integer-samples-per-cycle case is therefore exercised at kernel level and by the 5 kHz recordings (83.33 samples per 60 Hz cycle), not through a 4096 Hz upload.
* The phasor magnitude at 60 Hz on 5 kHz (non-integer) is 100.79 for a true 100: the inherent ripple, inside the proposed tolerance.

## 5. Server-side release gate (O-1)

**Setting.** `Settings.nominal_frequency_manual_override_enabled`, default `False`, read **only** in `app/config.py` from `NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED` (`1`/`true`/`yes`, case-insensitive; anything else is closed). A deployed build (production, or any build with `APP_VERSION` set by the deploy workflows) **refuses to start** with it set (N-3).

**Enforcement lives in the NF-1 service layer**, not in the router, so there is no path around it: `effective_nominal_frequency`, `set_manual_nominal_frequency` and `reset_nominal_frequency_to_auto` take a **required** keyword `manual_override_enabled` with no default.

| | Gate closed (default) | Gate open (local/isolated process) |
|---|---|---|
| `PUT mode=manual` | **409** `manual_nominal_frequency_disabled`, nothing stored, value not examined (a closed gate reveals nothing about validation). Order: recording exists (404) → gate (409) → value valid (400) | NF-1 behaviour; validation unchanged (0, negative, NaN, ±∞, outside 1–1000, bool, string, missing → the same 400/422 as before) |
| `PUT mode=auto` | allowed (only removes a value) | allowed |
| `GET` | allowed; reports the **Auto** resolution; `manual_override_enabled: false` | full resolution; `manual_override_enabled: true` |
| a value already in the registry | **ignored** by the accessor and by `GET` (dormant, not deleted) | honoured |
| engineering consumers | none uses the accessor in NF-3B; a stored value cannot reach any calculation either way | same |

**UI.** The UI flag `nominalFrequencyOverride` is unchanged and remains *visibility only*. With the UI on and the server gate closed, the editor shows the server's sentence — *"A manual nominal frequency cannot be saved: the feature has not been released in this environment."* — and nothing is saved (browser test added). The isolated NF-2 preview instructions (gallery and slice document) now require both switches.

**Accidental enablement is prevented by four independent things:** the default is closed; a deployed build refuses to start with it open; a static test proves no compose, env, Dockerfile, workflow, script, entrypoint or `config.js` file mentions the variable; and the frontend cannot set it (no mention in `index.html`).

## 6. Central accessor contract

`backend/app/services/nominal_frequency_access.py`, class `NominalFrequencyAccess`, created once in `create_app` from the registries and `Settings` and stored as `app.state.nominal_frequency_access`.

| Call | Returns / raises |
|---|---|
| `for_source(ws, source_id)` | `SourceFrequency` — `hz` (None when unusable), `usable`, `status`, `origin`, `mode`, `revision`, `assumed`, `manual`, `imported_hz` (exactly as imported), `manual_override_enabled`. Raises `SourceNotFoundError` for an unknown recording, a removed one, or another workspace |
| `for_channel_ref(ws, ref, calc_registry=)` | the frequency of the recording that grounds the channel: the source itself, or a calculated channel's `reference_source_id` (inherited, never a stored copy). Raises `CalculatedChannelNotFoundError` |
| `for_sources(ws, ids)` | `MultiSourceFrequency` — `status` ∈ `empty` / `unavailable` / `agreed` / `mixed`; `common_hz` only when `agreed`; `distinct_hz`; `unusable_source_ids`; `any_assumed`, `any_manual`, `revisions`. **Never a representative chosen from the members; independent of order** (all permutations tested) |
| `effective(ws, id)` | the full NF-1 resolution with the gate applied (what the endpoint reports) |
| `set_manual(...)` / `reset_to_auto(...)` | policy-enforced writers |

Rules it enforces: resolves only through the NF-1 authority; the 50 Hz default exists in exactly one place (the resolver, for a **missing or importer-assumed** value) and an unusable declared value is **never** replaced by it; imported metadata, provenance and samples are never modified (fingerprint test across set/change/reset/refused calls); recordings and workspaces are isolated; lifecycle (source removal, re-add, workspace reset) starts from Auto again.

## 7. Consumer call-path guard

`backend/tests/test_nf3b_frequency_call_path_guard.py` (22 tests). It extends the NF-1 tripwire (which counted only `x.metadata.nominal_frequency`, 11 reads) to **every** frequency path found in NF-3A, as an exact inventory classified `K` (unrelated), `D` (different justified authority) or `M` (still to migrate, with the NF-3A consumer id and slice):

| Table | What it freezes | Entries |
|---|---|---|
| G1 attribute reads | any `<x>.nominal_frequency` load (imported value and carried copies) | 10 files, 20 reads (the NF-1 counter saw 11) |
| G2 keys | `"nominal_frequency"`, `"nominal_frequency_hz"`, `"reference_frequency_hz"` (calculated-channel inheritance, parameters) | 10 (file, key) pairs |
| G3 literals | numeric 50, 60 and 0.02 anywhere in `backend/app` | 17 files, each classified; 8 `M` / `D`, 9 `K` |
| G4 defaults | default values of frequency-named parameters | 4 (the two power kernels, `compute_sliding_phasor`, `extract_waveform_evidence`) |
| G5 isolation | who imports the NF-1 service layer, the accessor, the resolver, the registry | only the accessor imports the service layer; only `main.py` and the NF-1 router import the accessor; only the service layer *reads* the registry |
| G6 frontend | exact counts of five frequency tokens in `frontend/index.html` | 9 / 10 / 31 / 2 / 2 |

Synthetic offenders (a direct read, a carried-copy read, a `parameters["nominal_frequency_hz"]` read, a literal 50 and 60, a defaulted frequency argument, a service-layer or registry bypass, an accessor import by a consumer) are each detected, and docstring mentions are not counted. **How a slice uses it:** a migrating slice *removes* its `M` entries in the same commit; no entry is ever added to make a test pass.

## 8. Files changed since NF-3A

`git diff --stat c70182c..HEAD` (production code):

| File | Change |
|---|---|
| `backend/app/services/nominal_frequency_access.py` | **new**: the accessor (221 lines) |
| `backend/app/services/nominal_frequency_service.py` | +29/−9: the gate as a required keyword on the three NF-1 functions |
| `backend/app/api/v1/nominal_frequency.py` | 409 mapping; goes through the accessor instead of the service |
| `backend/app/schemas/nominal_frequency.py` | one additive field `manual_override_enabled` (default `false`) |
| `backend/app/config.py` | the setting, its one environment variable, the deployed-build refusal |
| `backend/app/services/errors.py` | `ManualNominalFrequencyDisabledError` |
| `backend/app/main.py` | builds the accessor from `Settings` |

Tests and evidence: six new test modules and the frozen baseline (about 5,900 lines); `test_nf1_nominal_frequency_authority.py` (9 lines: the client fixture opens the gate explicitly, one direct service call passes the new keyword, the importer tripwire names the accessor); `browser-tests/playwright.config.js` (the test backend opens the gate), `nf2_recording_details_nominal_frequency.spec.js` (+1 test); the NF-2 preview instructions (gallery and slice document); `docs/project-memory/evidence/nf-3b-2026-11-25/`.

**Protected-file integrity.** `git diff c70182c HEAD` is **empty** for: all of `frontend/`, all of `backend/app/domain/` and `backend/app/providers/`, and every consumer service (`phasor_analysis`, `overcurrent_analysis`, `calculated_channel`, `compliance_readiness`, `compliance_measurement`, `synchronization`, `oscillation_*`, `auto_base`) and `api/v1/calculated_channels.py`. No compose, workflow, script, Dockerfile or entrypoint changed.

## 9. Before/after numerical equivalence

The scenario set of section 4 (2,971 recorded values: kernel statistics, exception classes, HTTP statuses, stored parameters) was run twice: once against a **pristine export of `c70182c`** from a scratch directory (not any worktree), once against this branch's tip. The two outputs are **byte-identical** (same SHA-256 `b5609564dc9f2a697d7887234ddf9a2a2daffb6c62001d174427b07f64bce0b7`). Evidence: `evidence/nf-3b-2026-11-25/equivalence.txt`, `outcomes_pristine_c70182c_and_nf3b_tip_identical.json`, `equivalence_run.py`. In addition `test_nf3b_frozen_baselines.py` re-checks this on every test run, and with the gate **open** and a Manual value stored, the HTTP consumers still match the frozen baseline (`TestAManualValueDoesNotYetInfluenceAnyConsumer`). No engineering numerical output changed.

## 10. Regression results

| Check | Result |
|---|---|
| NF-3B and NF-1/NF-2/R1A tests together (accessor 75, gate 66, guard 22, frozen baseline 34, oracles 12 passed + 7 strict xfail, NF-1 authority, NF-2 static gate, R0 baseline, importer provenance) | **all pass** (run before the final commit; part of the full run below) |
| **Mutation checks** (`evidence/…/mutation_checks.py`, on a scratch copy; 23 mutations: ignore Manual, honour it while closed, no gate, wrong order, default substituted for unusable, first-member pick, wrong grounding recording, lost isolation, gate default open, deployed build accepts it, wrong status mapping, a consumer reading/importing/hard-coding/defaulting a frequency, a silently migrated consumer, a changed kernel default) | **23 of 23 killed.** Two survived the first run (a hard-coded power gate moved from 50 to 60 Hz, and "first" versus "smallest" agreed value); the tests were strengthened and both are now killed |
| Browser: `nf2_recording_details_nominal_frequency` + `ui_rec_001_recording_info` (gate open on the test backend) | **53 passed, 1 skipped** (the screenshot-only test), including the new closed-server-gate test |
| Browser: 6 Waveform/PU/consumer groups (489 tests in 26 files: `voltage-only-pu-display`, all `waveform-*`, `calculated-channel-power`, `phasor_analysis`, `overcurrent_analysis`, `oscillation_setup`) | **462 passed, 4 skipped, 23 failed.** All **14** known baseline-equivalent WUI failures are among the 23 (VD-09/10/15/16; `waveform-empty-state` ×3; `waveform-measurement-values` ×5; `waveform-top-toolbar-migration` Per-Unit ×2). The other **9** (`waveform-toolbar-t0-sync-refinement` ×7, `waveform-auto-fit-range` ×1, `phasor_analysis` playback ×1) were re-run against a pristine export of `c70182c` and **fail identically there**: pre-existing, not caused by NF-3B. All 23 are recorded as **unresolved**, not as obsolete |
| Full backend regression on the final code | FULLRUN_PLACEHOLDER |

Frontend and Waveform code are byte-identical to `c70182c`, so no Waveform browser result can differ for a frontend reason; the runs above are the regression evidence that the backend change does not disturb them.

## 11. Limits

* The release gate is **in-process state** like the NF-1 registry: a restart clears Manual values (a natural reset to Auto). A multi-process deployment would need shared state, which is outside NF-1/NF-3.
* The accessor is **not exercised by any real consumer** in NF-3B. Its multi-recording tolerance and "smallest value" rule are reused/neutral choices (N-5); whether oscillation cross-signal adopts them is **O-9**.
* The 4096 Hz non-integer case is covered at kernel level and with 5 kHz uploads; a real 4096 Hz COMTRADE is refused earlier for an unrelated, pre-existing reason (section 4).
* The baseline records exception **classes**, not messages (messages are not part of the contract). Floats are frozen to 12 significant digits and compared at rel 1e-9, so a different libm cannot cause a false failure, but a real change of more than that does.
* Browser evidence is limited to the NF-2 specification, the new closed-gate UI test and a Waveform subset; the 14 baseline-equivalent WUI failures are **unresolved** and untouched.

## 12. Recommendation for NF-3C

**Proceed to NF-3C after owner review, with these conditions.**

NF-3C is the first behaviour-changing slice, so it should be the smallest: the consumers that already validate and already refuse in a typed way (NF-3A section 9.2): event detection and synchronization (C-03), compliance readiness (C-04), compliance measurement (C-05), oscillation representation and its labels (C-06/07), and, per O-11, the Technical facts card.

What NF-3B has put in place for it:

* `for_source` / `for_channel_ref` return everything those consumers need (value, origin, assumed flag, revision), so each is a one-line replacement of a direct read.
* The guard names every entry NF-3C removes (`M`, C-03 to C-07) and fails if one is left behind or a new one appears.
* The frozen baseline proves "Auto is identical" for each; the strict xfail `test_compliance_measurement_does_not_raise_for_zero_hertz` flips to a pass and its marker is removed in the same commit.
* The gate guarantees that, until the owner opens it, the accessor returns Auto for every consumer, so **NF-3C changes no output at all in a normal environment**. Manual only becomes effective in an isolated process that opens the server gate.

Decisions NF-3C needs before it starts (from section 2): **O-6** (provenance fields), **O-7** (event-detection response when unusable), **O-11** (facts card), and the label wording for the new `manual` origin. O-4, O-5, O-8, O-9, O-10, O-12 are not needed until later slices. **O-2** is not needed until NF-3F.

Not recommended before NF-3C: opening any gate, setting `WW_NF_CONSUMERS_MIGRATED`, or touching PU-MIG. The 14 (now 23, with 9 pre-existing others) unresolved browser failures are a gate-opening matter (**O-12**), not an NF-3C blocker.
