# NF-3E — Phase A: frozen baseline and assessment (stale calculated channels, O-4)

**Date:** 2026-11-27 · **Decision base:** [DEC-217](DECISIONS.md), [DEC-218](DECISIONS.md), [NF-3A](NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md) (section 7, 9.4, O-4/O-8/O-10), [NF-3B](NF_3B_FROZEN_BASELINES_ACCESSOR_GATE_2026-11-25.md), [NF-3D](NF_3D_PHASOR_OVERCURRENT_MIGRATION_2026-11-25.md) (section 10).
**Branch:** `feature/nf-3e-calculated-channel-staleness`, worktree `.local-data/nf-3e`, from NF-3D `65390d3`.
**Status:** Phase A complete (tests and records only). **No production file is changed. Nothing is pushed, merged or deployed.** Stops here for the owner's choices in section 6.

## 1. Authorised scope (as resumed)

The owner approved the NF-3E direction: a stored calculated channel is **flagged stale** when the frequency it was computed with no longer matches its recording's effective frequency;
its values are **preserved and never recomputed automatically**; and it must not be **silently reused as a current input**. The owner also set the limit: if the work exceeds the documented
O-4 option (**stale marker + one advisory only**), stop for review. A refusal or blocking of stale inputs exceeds that option, so the agreed order is **Phase A (inventory + frozen baseline)
→ this assessment → stop for the owner's choice**. Nothing in this record redesigns that scope.

## 2. What Phase A did

* `backend/tests/nf3e_baseline_scenarios.py`, `tests/fixtures/nf3e_baselines/nf3e_phase_a_baseline.json` (generated once from the unmodified `65390d3`, two identical runs required) and `test_nf3e_phase_a_baseline.py`: 8 scenario groups (RMS across a Manual change and back to Auto, a DAG, two recordings, reference-recording removal, power channels, frequency-independent operations, an unusable recording, creation-time validation).
* `test_nf3e_independent_oracles.py`: closed-form and direct-summation expected values for what a stale RMS channel is worth.
* Result: **32 passed** (focused); the NF-3B call-path guard and NF-3D baseline (**39 passed**) are unaffected.

## 3. Verified facts (frozen)

1. **The system says nothing about staleness today.** A Manual change (and the return to Auto) moves the central accessor and the NF-1 revision, but the channel inventory, the waveform response and the stored parameters stay byte-identical. No field in `CalculatedChannelOut` mentions frequency, origin, revision or staleness.
2. A stored RMS channel records **only the frequency value** (`parameters.nominal_frequency_hz`), with no origin and no revision. Whether the value followed the recording or was an explicit choice is **not recorded**.
3. Derived channels (add, abs, …) store no frequency; the walk goes through `dependency_ids`. ROCOF, add/sub/abs/multiply/reverse store none and cannot be stale on their own account.
4. **Power channels store a fixed `50.0`** on any recording (NF-3F). Under the naive predicate "stored ≠ effective" a 60 Hz recording's power channel would be stale **at birth**.
5. A channel over two recordings takes its frequency from its **reference recording only** (the first input's): after a change on the other recording the accessor still says 50 Hz while the recordings are `mixed` (50/60). Removing the **non-reference** recording leaves the mixed channel in the inventory with an unavailable waveform (HTTP 400 `incompatible_time_base`, an existing runtime signal); removing the **reference** recording removes the channel.
6. The readiness identity (`find_equivalent_rms`) proposes a **new** RMS step after a change; the old channel is untouched and still matches its own frequency.
7. An RMS channel can be created on an unusable recording with an explicit frequency; the accessor then refuses (`usable: false`), and a later Manual value makes it answer.
8. **Why it matters (independent oracle):** a stored RMS built with the wrong window frequency (60 Hz window on a 50 Hz signal) deviates from the true 100 V by **−8.7 % … +8.0 %** (bound `sqrt(1 ± |sin wT|/wT)`, reached to within 0.5 %). A stored channel must not read as if it reflected the new setting.
9. **F-1 (not NF-3E scope, not changed):** for a window that is not a whole number of samples (60 Hz at 5 kHz: 83.33) the RMS kernel uses the rounded sample count (83), not the elapsed-time window its docstring describes; about 0.3 %, identical for every stored channel.

## 4. Proposed model (a `[PROPOSAL]`, nothing implemented)

**Derived staleness, read-only, computed per request** (no stored flag to go out of date; the registry is in-memory, so there is no persisted channel to migrate):

| State | Meaning |
|---|---|
| `current` | every frequency-using ancestor's stored frequency equals the effective frequency of **its own** grounding recording |
| `stale` | at least one such ancestor differs (a channel built on a stale channel is stale through `dependency_ids`; a two-recording channel compares each ancestor with its own recording) |
| `indeterminate` | the stored value cannot be classified: the recording's frequency is currently unusable, or the channel kind has no meaningful predicate yet (power, see D2) |
| `unavailable` | an input recording is gone: the existing `incompatible_time_base` signal, unchanged |

*Additive only:* the list/response gains one read-only object (state, stored Hz, effective Hz, the stale ancestors); a new RMS channel additionally records the **origin and revision** it was created with (O-6, the calculated-channel half that NF-3C deferred to this slice). Values, creation rules, immutability, the readiness identity and every kernel stay as they are. Remedy for a stale channel: create a new one (existing behaviour); no recompute, no overwrite.

*Frontend:* a stale marker on the channel and **one advisory line**; the NF-2 control is not redesigned. NF-3A section 7.3 proposed one in-page event from the NF-2 apply/auto success path so panels refresh; that is an addition to accepted NF-2 code and is listed as D5 rather than assumed.

## 5. The part beyond O-4 — "not silently reused as a current input"

| Option | Behaviour | Effect |
|---|---|---|
| **A — propagate and warn** (recommended) | Staleness propagates to dependants (derived state above) and every surface that shows a channel carries the marker/advisory; nothing is refused | Stays inside the approved O-4 option; no new refusal; the engineer sees the state wherever the channel is used |
| **B — typed refusal** | Creating a calculated channel, or running an analysis, on a stale input is refused with a typed reason | Changes existing endpoints' behaviour and workflows (a new refusal path, a new public reason code); needs its own approval and tests |
| **C — acknowledgement** | A stale input is accepted only with an explicit acknowledgement (like the existing `override`) | Smaller change than B but still a new request contract |

Recommendation: **A** for NF-3E; B/C only if the owner wants enforcement after seeing A. A "recreate at the new frequency" button is a separate UX convenience (O-4's second branch), not proposed.

## 6. Owner decisions needed (nothing proceeds without them)

* **D1 — reuse blocking:** A (recommended), B or C (section 5).
* **D2 — power channels:** exclude them from the predicate (state `indeterminate` / "not frequency-aware yet") until NF-3F fixes the stored 50.0, or treat the fixed 50 as stale at birth on a 60 Hz recording. Recommended: exclude, with a visible reason, so NF-3E does not flag channels the engineer cannot fix.
* **D3 — explicit versus following channels:** channels created before stamping cannot say whether they followed the recording. The registry is in-memory (no legacy), so only new channels are stamped; an explicit user-chosen frequency that differs from the recording would be reported stale. Confirm this is acceptable (recommended), or add an explicit "chosen frequency" flag to the stamp.
* **D4 — O-8 (RMS builder shows no preselected frequency for an unusable recording) and O-10 (eligibility endpoint HTTP 500 → 400):** NF-3A lists both inside NF-3E, but their approval is recorded only as "proposed". Confirm whether they are in this slice.
* **D5 — NF-2 apply/auto event emission** (one added in-page event, no visual change): confirm as a functional necessity.
* **D6 — advisory wording and placement** (one line, marker on the channel row/legend), for UAT.

## 7. Verification plan (after the owner's choices)

Same discipline as NF-3C/NF-3D: tests that fail first, the frozen baseline edited only for approved entries in the same commit, the **full** backend suite on the final commit (about 50 min; the focused run does not replace it), a mutation pass over the staleness predicate (including the three-level DAG, the two-recording case, and the mixed-recording removal), browser tests for the marker/advisory and the builder, no gate activated, no DEV/PROD deployment, no PU or `main` integration.

## 8. Isolation and governance compliance (DEC-218)

* Worktree `.local-data/nf-3e` only; `.local-data/pu-mig-s5`, PR #14, `4885ca2` and the running G4 were not read for edit, modified, stopped or duplicated. The NF focused tests start no server and no browser (in-process `TestClient`, temporary directories), so no port is used.
* Applied decisions: DEC-217 (one authority; never the first recording's frequency), DEC-218, NF-3A O-4, NF-3C O-6, NF-3B baselines policy (never regenerate to pass). No decision was reopened. The proposals in sections 4–6 are `[PROPOSAL]`s awaiting the owner.
* No engineering formula was added or changed.
