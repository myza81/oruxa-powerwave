# NF-3E — Final engineering policy and consumer guards (closeout)

**Date:** 2026-11-27 · **Decision base:** [DEC-217](DECISIONS.md), [DEC-218](DECISIONS.md), [NF-3E record](NF_3E_STALE_CALCULATED_CHANNELS_2026-11-27.md), [consumer review](NF_3E_STALE_INPUT_CONSUMER_REVIEW_2026-11-27.md) and the owner's closeout instruction (2026-11-27).
**Branch:** `feature/nf-3e-calculated-channel-staleness`, worktree `.local-data/nf-3e`. **Not pushed, merged or deployed. NF is not integrated against the pending PU release.**

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

RESULTS_PLACEHOLDER

## 4. Known limitations

1. Phasor/overcurrent reasons are result-level codes with a message (their convention), not HTTP errors; compliance and oscillation use the typed 409 (theirs). One public reason value, `stale_calculated_input`, is used everywhere.
2. The compliance readiness member is blocked from a defensive path: readiness itself never *reuses* a stale RMS (it proposes a new step), so the blocked state is reached only when another planner hands it a stale channel (tested by patching the planner).
3. The marker is on the Calculated Channels list only (by instruction); there is no sidebar or legend marker.
4. Power channels keep the fixed 50 Hz and are not assessed (NF-3F); F-1 is unchanged; the mixed-recording first-member rule is unchanged (NF-3G).
5. A direct API caller that omits `nominal_frequency_basis` creates an explicit channel (never flagged) by design.
6. The first-time browser failure patterns (flakes) and the pre-existing failure sets are listed with the regression results.

## 5. Integration readiness

Not integrated, pushed or deployed. The branch is based on the NF-3D tip `65390d3` (which carries the earlier D5A/RD-1/WUI lineage), not on `main` or the pending PU release `f51a631` (PR #14). Before integration the owner decides the order: the PU release first, then a fresh NF integration baseline with a compatibility check (known conflict areas from the PU readiness record: `DECISIONS.md`, `HANDOFF.md`, `compliance.py`, `compliance_readiness_service.py`, `browser-tests/playwright.config.js`). The gate stays closed (`WW_NF_CONSUMERS_MIGRATED` false; server Manual gate closed by default); nothing here activates it.

## 6. Governance compliance (DEC-218)

Applied as written: DEC-217, DEC-218, NF-3A O-4/O-6/O-8/O-10, the owner's Option B, intent and consumer-guard decisions. No decision was reopened; no mathematical kernel was changed; no second authority was added; the PU worktree, PR #14 and the PU branch were not touched. NF-3F, NF-3G, NF-3H, RMS and WUI work did not start.
