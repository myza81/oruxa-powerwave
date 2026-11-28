# NF-3E — Final engineering policy and consumer guards (closeout)

**Date:** 2026-11-27 · **Decision base:** [DEC-217](DECISIONS.md), [DEC-218](DECISIONS.md), [NF-3E record](NF_3E_STALE_CALCULATED_CHANNELS_2026-11-27.md), [consumer review](NF_3E_STALE_INPUT_CONSUMER_REVIEW_2026-11-27.md) and the owner's closeout instruction (2026-11-27).
**Branch:** `feature/nf-3e-calculated-channel-staleness`, worktree `.local-data/nf-3e`. **Not pushed, merged or deployed. NF is not integrated against the pending PU release.**

**Status (owner, 2026-11-28): engineering ACCEPTED and FROZEN.** The accepted functional implementation is frozen at **`00387aa`**; later commits on this branch are documentation only (`f7623f9` final verification, then the acceptance record). Acceptance is **subject to integration verification and owner UAT** (both pending). No further functional change is authorised on this branch; NF-3F, NF-3G and NF-3H have **not** started; the NF gates stay **closed** (`WW_NF_CONSUMERS_MIGRATED = false`, the server Manual gate closed by default and set in no deployment file). **Integration order (owner):** (1) complete the PU release (PR #14); (2) establish the accepted `main` baseline; (3) prepare a *separate* NF integration candidate containing NF-1 through NF-3E; (4) reconcile the actual conflicts; (5) verify combined PU, WUI and NF behaviour; (6) obtain owner acceptance before NF-3F. Not pushed, merged or deployed; this branch and its worktree are preserved.

## 1. Governing policy (owner decision, 2026-11-27)

> A stale calculated channel remains available for **historical inspection** but shall not be accepted as a valid input for a **new engineering calculation or assessment**.

* Existing numerical values are preserved; calculated channels are **never recomputed automatically**.
* There is **one** staleness authority, `services/calculated_channel_staleness.py` (derived on every request from the central nominal-frequency accessor; nothing stored). No consumer has its own staleness rule (a test pins the set of importers and forbids frequency/basis logic in the consumers).
* **Stale** means: a recording-following RMS channel whose stored frequency differs from its recording's effective frequency (or the recording has none), or any channel that depends on one, directly or transitively. An **explicit** frequency is never stale on its own account but inherits upstream staleness. **Power** channels are not assessed directly (NF-3F) but inherit. Returning to the original frequency clears the frequency-related staleness; inherited staleness clears only when every stale ancestor is current.
* **Historical inspection** (waveform, cursor and peak values, annotation anchor, per-unit display, list/inventory, delete) goes through `get_calculated_result` / `extract_calculated_waveform_range` / `_resolve_input`, which are **never guarded** (a static test pins this).

## 2. Consumer guards (what changed)

The guard is applied only at the entry of a *new* calculation or assessment, with the refusal convention of that consumer. All reuse `assert_inputs_not_stale` / `stale_input_problem` / `stale_input_block` of the one authority.

| Consumer | Where | Refusal |
|---|---|---|
| Calculated-channel creation, line-to-line creation | (Phase B) `create_calculated_channel`, `create_line_to_line_voltage_channels` | typed `stale_calculated_input`, HTTP 409 |
| **Compliance execution** | `compliance_series.load_series` (the one reader behind trace, measurement and assessment); `Registries` gained the additive `frequency_access` | typed `stale_calculated_input`, HTTP 409 (compliance router maps it) |
| **Compliance readiness** | `compliance_readiness_service._block_stale_members` after member planning | the member is **BLOCKED**, the reference **needs action**, with the sentence naming the channel, why, and what to do; covers a member's channel and the input of its RMS step; the readiness response shape is unchanged |
| **Oscillation** | `oscillation_spectrum_service._analysis_series` (entry of every analysis, **native and RMS-magnitude**) and `derive_analysis_representation` (representation endpoint) | typed `stale_calculated_input`, HTTP 409 (oscillation router maps it) |
| **Phasor family** (phasor, diagram, input-readiness; impedance/distance/sequence ride on the same role candidates) | `phasor_analysis_service._fetch_role_candidate` returns a `StaleInputBlocked` sentinel handled at the 3 call sites | result `status: needs_configuration`, `reason_code: stale_calculated_input` and the message (the module's convention) |
| **Overcurrent** (analysis, input-readiness, recorded-input report) | `overcurrent_analysis_service._fetch_current_candidate`, 3 call sites | same result-level reason code and message |
| Frontend | existing phasor reason table (`WW_PHASOR_REASON_TEXT`) gets the actionable sentence; compliance and oscillation show the backend `message` through their existing error/blocked-state presentation | no new UI; the Calculated Channels marker and advisory are unchanged; no sidebar or legend marker |

**Correction to the earlier review.** The consumer review reported oscillation as "refused by form" for both representations, from a probe of `rms_magnitude` only. Reading `_analysis_series` shows the **native** representation explicitly accepts an RMS/magnitude voltage or current channel, so oscillation **did** accept a stale RMS channel natively. It is now refused (tested for both representations). Overcurrent already refuses *any* calculated current in recorded mode for another reason (`calculated_channel_side_unavailable`, D5A); the stale guard precedes the form check and does not change that.

## 3. Verification

All results are for the code commit **`00387aa`** (the final gate candidate; later commits are documentation only).

| Check | Result |
|---|---|
| **Failing-first guard tests** (`test_nf3e_consumer_guards.py`) | 15 failed / 4 passed before the implementation; **20 passed** after (compliance execution direct and transitive, readiness blocked member and the endpoint integration, oscillation native and RMS-magnitude and the representation endpoint, phasor, diagram, input-readiness, overcurrent, input-readiness and recorded-input report, valid inputs accepted, frequency restoration lifting the refusal, values unchanged, historical inspection available, one-authority and unguarded-fetcher static guards) |
| **Static frontend sentence** | passed (`test_frontend_nf3e_staleness.py`) |
| **Broad focused regression** (every consumer touched: calculated channels, compliance, oscillation, phasor, overcurrent, impedance/distance/sequence, NF-3B/C/D baselines and guards, RMS baselines, per-unit registries, frontend NF/RMS) | 4,360 passed, 3 xfailed, 1 failed: the pinned accessor-importer inventory, updated deliberately (`compliance_series` now takes the accessor for its type), then passing |
| **Mutation checks of the guards** (24: compliance execution/readiness/router wiring, oscillation entry/representation/router, phasor/overcurrent fetchers and six handlers, public reason value, message, frontend sentence, shared-fetcher guard) | **24 of 24 killed** (23 on the first pass; G3 "readiness never blocks a stale member" survived because only the conversion was unit-tested; the readiness-endpoint integration test was added and G3 was killed on the re-run). Earlier suite: 19 of 19 killed. Scripts and results: `evidence/nf-3e-2026-11-27/` |
| **Full backend** (`pytest`, 28 min) | **15,217 passed, 405 skipped, 3 xfailed (strict: NF-3F/G/H), 0 failed.** NF-3D tip for reference: 15,109 / 405 / 4 xfailed (+108 tests; the O-10 xfail flipped; skips unchanged) |
| **Full static frontend** | included in the full backend run (the whole `test_frontend_*` subset and `test_user_facing_copy`): 0 failed |
| **BEN owner-reference tests** (`--ben-reference-dir`, 8 files) | **284 passed** |
| **Full browser** (1 worker, default ports, 3.5 h, includes the NF-2 spec and the new NF-3E spec) | **1,697 passed, 167 failed, 17 skipped, 0 flaky, 0 retries** (retries are disabled in the configuration). **This is not an unconditional pass.** It is accepted only as evidence that no new regression relative to NF-3D was identified (reconciliation below) |

**Count reconciliation (167 versus 163).** The authoritative figure is **167 failed tests** (the Playwright test-level count: 1,697 + 167 + 17 = 1,881). The figure **163** is the number of *distinct* test titles among them: two titles are parameterised and repeat three times each (`ben5k-timezone.spec.js` "upload, recording details, sidebar and waveform retain clock authority" for UTC / America/New_York / Asia/Kuala_Lumpur, and `time-reference-interpretation.spec.js` "interpret once: automatic Waveform alignment..."), so 167 - 4 = 163. The baseline comparison was keyed by file and title, so it reports 163; the baseline's own test-level counts agree with the candidate's where they were taken (22 files: 106 failed on both; 27 files: 61 on the candidate).

**Browser reconciliation against the unmodified NF-3D tip `65390d3`.** The failures are not caused by NF-3E: they are the NF lineage's pre-existing and environment sets.

* The same tests were run on a `git archive` copy of `65390d3` in the same configuration (49 spec files that contain a failure, 476 tests; the first attempt was invalid because of a carriage return in my file list and a session restart, and was redone). **Every test that fails on the candidate also fails on the baseline: 0 failures only on the candidate.** One test fails on the baseline but passes on the candidate (`event-reconstruction-plot`: overlap, containment, separation) and is a flake on the baseline side. Part 1 (27 files, 213 tests): 212 agree; part 2 (22 files): 104 candidate failures = 104 baseline failures, identical sets.
* **Causes** (all pre-existing): (a) the NF Playwright configuration opens the server's Manual nominal-frequency gate but not `BEN5K_EXPERIMENTAL_ENABLED` (the PU lineage's configuration has the reverse), so the five `ben5k-*` specs fail for lack of the flag; with a backend started with **both** flags the BEN-area specs give 19 passed / 18 failed / 2 skipped on the candidate and **the identical 19 / 18 / 2 on the baseline** (the remaining failures wait for `#wwUnitPerUnitBtn`, a toolbar control the NF lineage predates); (b) the playback, post-upload-readiness, per-unit, event-reconstruction, waveform toolbar, power-provenance and similar groups, the CSV/Excel preparation rows (`data-issues-*`, `data-preparation-sticky-header`, `sampling-rate-format`), `calculated-channel-preview` ×5, `compliance_readiness:212` and `compliance_measurement` ×2 fail identically on the baseline; they belong to the documented unresolved sets of the NF-3B to NF-3D slices and are fixed on the PU/WUI lineage, which the NF branch does not yet contain.
* **Not weakened:** no test, configuration or expected value was changed to obtain these results; the dual-flag backend was started outside the configuration, and nothing was committed for it.
* NF-2 browser spec on the default ports: **40 passed, 1 skipped** (a screenshot test, by design) in the second full run; the first run had one failure (`a declared and an assumed recording carry the preview line`) that passes alone, on the baseline and on re-run: recorded as a first-run flake, not reproduced. The new NF-3E spec: 7 of 7 passed on isolated ports.
* **Housekeeping:** the browser run rewrote seven tracked evidence screenshots in this worktree; they were restored with `git checkout` and are not part of any commit.


## 4. Known limitations

1. Phasor/overcurrent reasons are result-level codes with a message (their convention), not HTTP errors; compliance and oscillation use the typed 409 (theirs). One public reason value, `stale_calculated_input`, is used everywhere.
2. The compliance readiness member is blocked from a defensive path: readiness itself never *reuses* a stale RMS (it proposes a new step), so the blocked state is reached only when another planner hands it a stale channel (tested by patching the planner).
3. The marker is on the Calculated Channels list only (by instruction); there is no sidebar or legend marker.
4. Power channels keep the fixed 50 Hz and are not assessed (NF-3F); F-1 is unchanged; the mixed-recording first-member rule is unchanged (NF-3G).
5. A direct API caller that omits `nominal_frequency_basis` creates an explicit channel (never flagged) by design.
6. The browser suite on this branch fails 167 tests (163 distinct titles) that fail identically on the unmodified NF-3D tip (section 3); they clear only when the NF lineage is rebased onto the PU/WUI lineage, which is the integration step the owner has deferred.

## 5. Integration readiness

**Integration verification and owner UAT are pending; the branch is frozen at `00387aa` and not to be rebased, rewritten or integrated under this record.** Not integrated, pushed or deployed. The branch is based on the NF-3D tip `65390d3` (which carries the earlier D5A/RD-1/WUI lineage), not on `main` or the pending PU release `f51a631` (PR #14). Before integration the owner decides the order: the PU release first, then a fresh NF integration baseline with a compatibility check (known conflict areas from the PU readiness record: `DECISIONS.md`, `HANDOFF.md`, `compliance.py`, `compliance_readiness_service.py`, `browser-tests/playwright.config.js`). The gate stays closed (`WW_NF_CONSUMERS_MIGRATED` false; server Manual gate closed by default); nothing here activates it.

## 6. Governance compliance (DEC-218)

Applied as written: DEC-217, DEC-218, NF-3A O-4/O-6/O-8/O-10, the owner's Option B, intent and consumer-guard decisions. No decision was reopened; no mathematical kernel was changed; no second authority was added; the PU worktree, PR #14 and the PU branch were not touched. NF-3F, NF-3G, NF-3H, RMS and WUI work did not start.
