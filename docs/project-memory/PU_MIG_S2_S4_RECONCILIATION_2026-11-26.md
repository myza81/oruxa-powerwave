# PU-MIG — reconciliation of the S2 numerical-integrity correction with S3/S4

**Date:** 2026-11-26 · **Worktree / branch:** `.local-data/pu-mig-s2-s4-integration`, `integration/pu-mig-s2-correction-into-s4`, created from the
committed PU tip `e6a2a97` (S3 `03e1b77`/`01b0364`/`1f82126`, S4 `f5dc91f`/`7584363`/`5681491`/`e6a2a97`). The active PU worktree
(`.local-data/pu-mig-s1`) was **not** modified; its uncommitted S5 files are preserved there (§7).
**Local only: not pushed, merged to any shared branch or deployed.** Authority: owner decision "Pause S5 and Reconcile S2–S4" (2026-11-26).

## 1. Why

The S2 correction stack on `verify/pu-mig-s2-correction` (`3530c06`, `bf385f2`, `262e769`; base `58ef97b`) was completed in another session and
never reached the S3/S4 implementation session. It fixes a numerical-integrity defect of the S2 historical gate (`8ef6d5c`): a result that the
resolver did **not** place could be labelled `verified_direct` merely because the recording's side and the base's side LABEL were both strict and
equal — e.g. a Source Default whose 132 kV nominal base is labelled Secondary, on rated Secondary samples (63.5 V), reads 8.33e-4 pu (1200× low)
and was labelled verified. The rule: *a strict or compatible reference-side label does not prove the numerical denominator is on that side;
`verified_direct` needs a demonstrably correct same-side denominator, `verified_converted` an authoritative ratio actually applied.*

My S4 `qualify_historical` (the shared qualifier for raw Voltage and raw/calculated Current) copied the pre-correction rule, so S3/S4 carried the
defect for Voltage **and** introduced the same condition for Current (`legacy_manual` and any base the resolver cannot place).

## 2. Integration and conflict resolution

`git merge --no-ff 262e769` into `e6a2a97` → merge commit **`15dc8c4`**. One textual conflict: `backend/app/domain/per_unit_reference.py`
(the Voltage historical block: the correction rewrote it inline; S4 had moved it into the shared `qualify_historical(..., strict=...)`).
Resolution (the contracts of the two quantities are distinct, the rule is shared):

* `qualify_historical(historical, side_inputs, *, base_side)` — no `strict` parameter; a result of the historical gate is **never** verified
  (`unverified_historical`, or `blocked` when the gate refused); no denominator side, conversion or ratio is claimed. Used by Voltage (the
  correction's text kept verbatim: raw declaration decides, effective side may only add a block) and by Current.
* Raw Current historical gate: the raw declaration decides; Recording Details' strict effective side may only **add** a block (never replaces
  the raw side, never unblocks). DEC-210 Current reference rules, DEC-213, DEC-215 and the accepted S2 VT guard removal are untouched.
* Calculated Current: the effective sides feed a `gate_reference` that adds a block to the raw-declaration result (never replaces it); the
  post-hoc qualification of a historical result never verifies. The strict resolver path (`_strict_common_base`) is unchanged: verified states
  still come only from the S1 resolver (declared base side + actually applied authoritative CT).
* S4 tests that encoded the old "effective replaces raw / strict+compatible = verified" behaviour were rewritten to the corrected contract
  (`test_the_historical_current_gate_…`, the K-2 engineer-side test); no numerical, eligibility or protection assertion was weakened.
* Legitimate configured Manual bases keep their verified states **through the resolver** (`manual_direct` with its declared side:
  same-side → `verified_direct`, other side + authoritative CT → `verified_converted`); asserted at the gate and through the API.

## 3. Numerical before / after matrix (actual denominators and PU peaks, both trees run on identical API scenarios)

"Before" = the S4 tip `e6a2a97`; "after" = `15dc8c4`. Peaks are `max |pu|` of the displayed channel (instantaneous samples).

| Case | Before | After |
|---|---|---|
| V1 Source Default 132 kV label Primary, Primary rated samples | 1.0 · verified_direct | 1.0 · verified_direct |
| **V2 Source Default 132 kV label *Secondary*, Secondary rated 63.5 V (the counterexample)** | **8.33e-4 · `verified_direct` (false)** | **8.33e-4 · `unverified_historical`** (number unchanged) |
| V3 Source Default label Secondary, Primary rated | blocked (76 210 V, ENG) | blocked |
| V4 Source Default label Primary, Secondary rated | blocked (no VT authority, `no_group`) | blocked |
| V5 Source Default label Primary, undeclared sample | 8.33e-4 · unverified | 8.33e-4 · unverified |
| V6 group Primary base + manual VT 1200:1, Secondary rated | 1.0 · verified_converted | 1.0 · verified_converted |
| V7 group stored Secondary 110 V (D-5), Secondary rated | 1.0 · verified_direct (resolver) | 1.0 · verified_direct |
| V8 group Primary base, undeclared sample | 8.33e-4 · unverified | 8.33e-4 · unverified |
| C1 Source Default direct 1200 A label Primary, Primary rated | 1.0 · verified_direct | 1.0 · verified_direct |
| C2 Source Default direct 5 A label Secondary, Secondary rated (manual base, declared side) | 1.0 · verified_direct | 1.0 · verified_direct |
| C3 group manual 1200 A Primary + CT 240:1, Secondary rated | 1.0 · verified_converted | 1.0 · verified_converted |
| C4 group manual base, side undeclared, Primary rated | 1.0 · unverified | 1.0 · unverified |
| C5 calculated Current, automatic, Primary rated | 1.0 · verified_direct | 1.0 · verified_direct |
| **C6 calculated Current, legacy manual pointer, Primary rated** | 1.0 · `verified_direct` (resolver not used) | 1.0 · `unverified_historical` |
| C7 calculated Current, automatic, Secondary rated + CT | 1.0 · verified_converted | 1.0 · verified_converted |

No PU **number** changes in any case: the correction removes false certification, it does not move a denominator. S2 Cases A / A0 / B / C
(132 kV / 110 V, `test_pu_mig_s2_historical_gate.py` and `test_pu_mig_s2_d7_closeout.py`, first-principles denominators) pass on the integrated
tree, as do the 108-case independent historical-gate oracle and the S1 oracle through both the Voltage and the Current production gates.

## 4. Verification

* Focused S2–S4 PU tests (S2 historical gate, D-7 closeout, raw Voltage, S1 oracle Voltage + Current gates, S3, S4, guard): all pass.
* **Complete backend suite (measured, `15dc8c4` + the final tests): 15 193 passed, 410 skipped, 0 failed** (20 min).
* Mutation (`mutate_int.py`, out of tree): 8 / 8 caught — the qualifier verifying a historical result (Voltage and Current), the Voltage / Current /
  calculated effective side replacing the raw side, and each effective-side block dropped.
* Browser: see §6.

## 5. Unresolved items

* None found for Current PU or historical safety. Residual by design: a **configured Manual base's declared side is the engineer's declaration**
  (D-2, kept through S4); the engine cannot detect a mislabelled manual base — it is placed on the declared side by the resolver, exactly as approved.
* `legacy_manual` calculated Current is now labelled `unverified_historical` (numbers unchanged).

## 6. Browser (affected PU specs)

Affected PU specs run on the integration tree (workers = 1, isolated ports; the S4 list plus `waveform-axis-units`, 25 specs: calculated channels, Current manual PU, current-common-base, Source Default Current preview, overcurrent, group details, line-to-line, per-unit reference/voltage-reference safety, eligibility, numeric integrity, display synchronisation, atomic updates, power provenance, voltage-only PU display, BEN5K calculated PU gate, power calculator, event-reconstruction PU): **342 passed, 0 failed** (13.0 min, measured). No full browser suite (reserved for the S6 acceptance).

## 7. S5 state (paused)

The S5 work is preserved **uncommitted** in `.local-data/pu-mig-s1`: `frontend/index.html` (provenance wording and rows) and the untracked
`browser-tests/pu-side-provenance-presentation.spec.js` (two of its nine tests were still being corrected when the pause arrived). A byte copy and
`git diff` patch were also saved outside the repository. S5 is presentation-only over the backend's `verification_state`; the corrected states
(fewer `verified_*`, never from a historical result) only make its wording more accurate. S5 can resume on top of `15dc8c4` by re-applying that
diff — after owner review.
