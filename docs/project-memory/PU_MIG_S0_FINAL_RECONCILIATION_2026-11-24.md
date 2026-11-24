# PU-MIG S0 — Final Engineering Contract Reconciliation

**Date:** 2026-11-24
**Type:** documentation, one read-only probe and one independent oracle. **No production code, test, API, UI or configuration was changed. Nothing is pushed, merged or deployed.**
**Stop point:** owner engineering review. S1 is **not** started and is **not** authorised by this document.

**Baseline.** `uat/dev-d5a-20261121` @ `e9c621c4c15e0693d008670e9be8ae38b29c6d97` (D5A-2B2C-1B + WUI-001–004), confirmed unchanged on `origin` at the start of the work.
`backend/app` at `e9c621c` is byte-identical to `2144893`, the tree the earlier audit examined (`git diff 2144893 e9c621c -- backend/app` is empty); only frontend and documentation differ, so every backend finding of the earlier audit still holds.

**Branch / worktree.** `audit/pu-mig-s0-final-contract`, worktree `.local-data/pu-mig-s0-contract`, created from `e9c621c`. Other worktrees (Codex's `d5a-2b2a`, the DEV baseline, the superseded `pu-mig-s0-reconciliation` and `pu-mig-001-audit`) were not touched.

**Labels.** **[APPROVED]** owner-decided, with source · **[FACT]** verified in code at `e9c621c` or by executing the probe/oracle · **[PROPOSAL]** my recommendation · **[OWNER]** needs an explicit owner decision · **[ASSUMPTION]** stated so it can be challenged.

---

## 1. What was preserved, and what was added

| Commit on the audit branch | Content | Integrity |
|---|---|---|
| `e5c6fce` | `PU_MIG_001_ASSESSMENT_2026-11-24.md` and `evidence/pu-mig-001-2026-11-24/pu_mig_oracle_v1_original.py` | The assessment is the original delivered text recovered from the session transcript (no banner, no later edit). The v1 oracle is the original script, sha256 `480d12a0…f6fa`. |
| `55f3218` | S0 decision matrix, v2 oracle (`pu_mig_oracle.py`) + `pu_mig_oracle_expected.json`, DEC-216 Amendment 7 | Byte-identical to `88c9244` (sha256 prefixes compared). |
| this commit | this report, the final oracle, the existing-behaviour probe and its recorded output | New. |

Two differences exist between the **original** assessment and the copy previously committed on `audit/pu-mig-001-s0-decision-matrix` (`88c9244`): a two-line "Update 2026-11-24 (owner review)" banner and one corrected line-number reference (`:36533-36524` → `:36533-36568`, `:36494-36518`). Neither is applied to the preserved original; the matrix header already records that it supersedes the assessment where they differ.

---

## 2. Status ledger

### 2.1 Approved (preserved unchanged)

| # | Requirement | Source |
|---|---|---|
| A1 | Recording Details is the single source of the recorded side, via `resolve_effective_measurement_side()`; precedence group override > recording correction > channel declaration > recording default (inferred, **not** strict-usable) > unresolved. | DEC-216 + Amendments 1, 3, 4 |
| A2 | Voltage and Current may sit on different sides; only disagreement *within one quantity* is a conflict. | B2A-1 |
| A3 | Nothing is inferred from a CT/VT ratio or a magnitude; a side without evidence needs an engineer's Level 1/Group value. | B2A-4, Amendment 5/6 |
| A4 | The ratio is that of the **consumed channel's own Measurement Group**; matching sides do not prove shared ratio authority; the ratio is applied once and **only when a conversion is needed**. | DEC-216 item 8, Amendment 3 safeguard |
| A5 | PU future behaviour: primary measurement + primary base → direct; secondary measurement + primary base → secondary denominator from the authoritative CT/VT; conversion needed without CT/VT → block; a legitimately configured secondary base is **never reinterpreted as primary**; primary and secondary readings of one condition give equivalent PU. | DEC-216 PU paragraph |
| A6 | Nominal L-L voltage, the L-L/L-N distinction, derived `Ibase`, DEC-211, DEC-213, calculated-channel policy, DEC-215 preserved; a manual Current base's reference side is reviewed before any assumption; raw waveforms never modified; no double conversion. | DEC-216 |
| A7 | **OD-1:** PU may select/derive a compatible denominator from the effective side and the authoritative ratio (narrow supersession of DEC-210/211 "no ratio scaling" and "known mismatch blocks"); a transformer rating is never a base; DEC-215 provenance preserved. | Owner, 2026-11-24; DEC-216 **Amendment 7** |
| A8 | Equipment-derived bases are Primary; manual/direct bases carry their own declared side; an omitted side is preserved only within the same method; explicit Unknown resets; Stage 5B result bases are independent; Unknown fails closed for cross-authority Automatic and result Manual. | DEC-209, DEC-210 |
| A9 | Historical Unknown stays computable and labelled **Unverified** (not removed without owner authorisation); a known P/S mismatch blocks. | DEC-210, DEC-211 (until narrowed by A7) |
| A10 | Physical calibration authority gates PU first (`calibration_unavailable`). | DEC-213 |
| A11 | Nominal-derived VT (`auto_nominal`, secondary 110 V) is a valid consumable ratio; provenance never relabelled. | DEC-215 |
| A12 | Calculated Voltage: no generic multi-input base (DEC-052), declared L-L representation authoritative (DEC-115), undetermined representation → no base (DEC-116). | DEC-052/115/116 |
| A13 | Calculated Current: PC-001 common base (rtol 1e-12), Stage 5A cross-authority Primary/Primary only, Stage 5B result Manual with its own side. `legacy_manual` profile pointer retained (PU-CORE-001 H2). | DEC-209; PU-CORE-001 |
| A14 | Raw Current stays ENG in the UI; automatic PU is Voltage-only in the UI. | DEC-212 |
| A15 | Owner instruction for OD-3/OD-4: manual/direct and result-owned Current bases keep **independent** side semantics; selective (not blanket) calculated lineage; preserve the legitimate Secondary Voltage denominator path using `secondary_voltage_ll_v`, **including cases with no primary nominal**. | Owner guidance, 2026-11-24 |

### 2.2 Not decided (this report makes recommendations only)
OD-2 (per class), OD-3 (replacement contract), OD-4 (lineage table), R-4 … R-10 and the new items N-1 … N-3 in §10. Amendment 7 states this explicitly.

---

## 3. Reconciliation of the S0 matrix with the published code

The matrix (`PU_MIG_001_S0_DECISION_MATRIX_2026-11-24.md`) was re-checked against `e9c621c`. Its rules A1–A14, the §2.2 supersession, the §3 outcome table and the numerical cases V1–F5 hold. Corrections and additions, all **[FACT]**:

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| C-1 | **The 4.35 % is not hypothetical: the published code returns 0.956522 for a system at nominal** whenever the stored `secondary_voltage_ll_v` is the VT secondary *rating* and the VT primary differs from the system nominal. | `existing_behaviour_probe_output.txt`: secondary sample 105.217391 V, declared secondary, base secondary (110 V) → `compatible`, `configured`, **0.956522** | §6; decision R-4 |
| C-2 | `secondary_voltage_ll_v` is written automatically from the channel's **VT secondary winding rating** (`auto_base_service.py:248-258` ← `MeasuredSecondaryVoltage.value_kv` ← `ch.secondary_ratio`, `auto_base_evidence.py:545-590`); the module's own contract (C2) says ratings are *transformation information*, not bases. | code | The legacy denominator is a rating-as-base by construction; correct only when nominal = VT primary rating |
| C-3 | **The PU surfaces do not agree today for Voltage group channels.** The display seam (`waveform_service.py:226`) and the source provenance group path (`per_unit_provenance_service.py:364`) pass the Voltage group config; the **coverage** group path (`per_unit_coverage_service.py:119`) and the **calculated provenance** group path (`per_unit_provenance_service.py:458`) do not, so their base side is "unknown". Same input: display `base_required / incompatible / voltage_reference_side_incompatible`, coverage `configured / unverified`. | probe `gate_agreement`; code lines | DEC-210 requires all surfaces to agree. S2 must replace the four call sites with one function **in the same slice** |
| C-4 | Concrete hazards of retaining "Unverified" (matrix V6 gave one): primary sample, declared Unknown, **secondary** base (110 V) → **1200.000 pu**; secondary sample, declared Unknown, primary base → **0.000797**. | probe table, rows 5 and 9–12 | Input to OD-2 (§5) |
| C-5 | The PU engine reads the **raw declared flag** `channel.measurement_side`, never `resolve_effective_measurement_side()`. Calculated Voltage passes no side at all (`calculated_channel_service.py:1784`); calculated Current uses the leaves' raw flags (`calculated_current_per_unit.py:~150`). An engineer's Level 1/2 correction therefore has **no effect on PU** today. | code; `grep` finds no use of the resolver in the PU services | motivating gap (IC-7) confirmed |
| C-6 | `resolve_transformer_context()` returns a `side`/`side_status` derived from the **raw declared** flags (`_resolve_side`). S1/S2 must take **only** the ratio fields from it and the side from `evaluate_channel_side()`. | `protection_instrument_context.py:112-130, 175-250` | Prevents a second, divergent side source |
| C-7 | A Voltage **nominal base is Primary by meaning** (auto-base contract C1: `nominal_voltage_ll_kv` is the nominal *primary-system* L-L voltage), independent of the stored `base_reference_side`, which defaults to `"unknown"` for every older configuration. The legacy secondary branch is selected **only** by stored `base_reference_side == "secondary"` and requires a valid `secondary_voltage_ll_v` (`voltage_group_config.py:324-348`). | code | S1 must take the base's *meaning* (kind), not the stored field, as the base side for the nominal path |
| C-8 | Calculated **Current** common-base compares the contributors' **base amounts** (`calculated_current_per_unit.py:~170-180`). With side-derived denominators it must compare the **denominators in the sample side** and, for Secondary samples, still require a single CT authority — otherwise bases that agree can hide different CT ratios. | code | S4 constraint (§8, K-3) |
| C-9 | Line-to-Line Voltage is its own operation `line_to_line_voltage` (not Subtraction). It is outside `MULTI_OPERATIONS`, so the DEC-052 refusal in `calculated_group_aware_per_unit.py` does not apply to it; its declared representation selects the L-L denominator. ROCOF and the power operations are never PU-inherited. | `domain/line_to_line_voltage.py:51`, `per_unit.py:498`, `calculated_group_aware_per_unit.py:~216` | §7 table uses the real operation names |
| C-10 | **The browser regression contracts the matrix names as S2 guard rails are already failing on the deployed DEV baseline.** On exact `3ed200c` and on the release candidate alike (same 131 tests): `per-unit-reference-safety` 2, `pulu-auto-reference` 3, `per-unit-display-synchronization` 6, `per-unit-numeric-integrity` 4, `per-unit-eligibility` 1, `per-unit-atomic-updates` 1, `voltage-only-pu-display` 4, `current-common-base` 3 (`D5A_2B2C_1B_WUI_INTEGRATION_REPORT_2026-11-24.md` §3). Cause not established; not declared obsolete. | integration report | New prerequisite **P0** (§9): the PU browser suites must be triaged before they can gate S2–S4 |
| C-11 | Frontend: the Base Reference Side controls (10 occurrences), the "no CT/VT scaling" wording (`index.html:33257`) and the refresh path (`wwRefreshDisplayedChannelsForPerUnitChange`, `:36239`; `wwRdSideEnqueue`, `:36888`) still exist after WUI-001–004. | grep | S5 scope unchanged |

No matrix statement was found to be numerically wrong. C-3, C-8 and C-10 are gaps in it.

---

## 4. The mathematical contract (denominator selection and derivation)

### 4.1 Vocabulary — the five things that must never be conflated

| Concept | Meaning | Where it comes from | Never |
|---|---|---|---|
| **Recorded measurement side** `s` ∈ {primary, secondary} | what the *samples* are | `evaluate_channel_side()` over `resolve_effective_measurement_side()`; **strict-usable only** | inferred from a ratio, a magnitude, a name or a sibling channel |
| **Configured engineering base** `B` + **base meaning** `b` | the physical quantity that equals 1.0 pu, and the side it is expressed on | the existing base resolvers (nominal L-L kV, derived Ibase, manual/direct, result manual, legacy `secondary_voltage_ll_v`) | a CT/VT *rating*, a transformer MVA, a ratio |
| **Transformation ratio** `r` = primary ÷ secondary | moves a denominator between sides | VT/CT of the **consumed channel's own Measurement Group**, authority `manual` / `recording_metadata` / `auto_nominal` | borrowed from another group/recording; used when no conversion is needed; used to *decide* a side |
| **Voltage representation** `ρ` | L-L → 1; L-N → 1/√3 | existing `voltage_reference` / declared representation | folded into the ratio; applied to samples |
| **Explicit Secondary manual base** | a manual/direct (or result-owned) base the engineer declared as Secondary | `CurrentBaseConfiguration.base_reference_side`, `PerUnitBaseProfile.*_base_reference_side`, calculated `base_reference_side` | reinterpreted as Primary; "Unknown" treated as Primary |

### 4.2 Base meaning by kind

| Kind | Base side `b` | Value |
|---|---|---|
| `nominal_ll_primary` (voltage nominal path) | **Primary**, by meaning (C-7) | nominal L-L volts |
| `equipment_derived_primary` (`Ibase = S/(√3·V_LL)`) | **Primary** (DEC-209) | amperes |
| `manual_direct` / `result_manual` | the **declared** side (`primary` / `secondary` / `unknown`) | amperes |
| `legacy_secondary_voltage_ll` | **Secondary** (declared by `base_reference_side == "secondary"`) | secondary L-L volts |

### 4.3 The denominator

The denominator is expressed in the unit of the **sample's own side**, so `pu = sample ÷ D` and the sample is never scaled.

```
ρ = 1/√3 for L-N voltage, else 1
b = s                      D = B·ρ                     direct; the ratio is NOT read
b = primary,   s = secondary   D = B·ρ / r             base_divided_by_ratio
b = secondary, s = primary     D = B·ρ · r             base_multiplied_by_ratio
```

Refusals, in this precedence (first match wins, so the answer is deterministic):

1. invalid request (equipment/nominal base not Primary; non-positive or non-finite value);
2. sample side not strict-usable (`calculated`, `unresolved`, `inferred`, `group_conflict`);
3. base side `unknown` — **never assumed Primary**;
4. conversion needed and the ratio is not authoritative (`no_group`, `not_configured`, `invalid`, `untrusted_authority`, `conflict`);
5. denominator not representable (existing numerical safeguards).

### 4.4 Properties (the acceptance conditions, independently verified in §11)

| P | Property |
|---|---|
| P1 | **Equivalence.** For one physical condition, `pu(primary samples) = pu(secondary samples)` for every ratio, level and representation (verified to 1e-50 over 5 levels × 6 ratios × 2 representations). |
| P2 | **Identity.** Same-side computations return exactly the existing denominator (`B·ρ`); Primary/Primary results are bit-identical to today (golden file). |
| P3 | **Ratio-not-read.** A same-side computation ignores the ratio entirely (a missing, invalid, untrusted or conflicting ratio changes nothing). |
| P4 | **Round trip.** A Primary base `B` on secondary samples equals a Secondary base `B/r` on secondary samples; a Secondary base `B/r` on primary samples equals `B`. |
| P5 | **Commutation.** `ρ` and `r` are scalars; the order of applying them does not matter. |
| P6 | **No assumption.** An unknown/inferred/unresolved side or an Unknown base side never produces a number from the strict resolver. |
| P7 | **Refusals carry no number**; resolved results carry exactly one conversion kind. |
| P8 | **Transformer rating is never a base**; the ratio only moves a denominator. |

### 4.5 Selection when more than one base exists (Voltage)

`select` is **S2**, not S1 (it needs R-4/R-5). Rule proposed for S2: the stored `base_reference_side` keeps selecting the path exactly as today — `secondary` ⇒ legacy `secondary_voltage_ll_v` base (kind `legacy_secondary_voltage_ll`); otherwise the nominal base (kind `nominal_ll_primary`). The new strict resolver then derives the denominator for the **consumed sample's** side. No existing numerical outcome of a path whose sample side equals its base side changes.

---

## 5. Historical Unknown / Unverified — policy alternatives per class (OD-2)

**Evidence of what retention means** (probe, 132 kV system, VT 138 kV/110 V, base 110 V secondary): a Primary sample with declared Unknown against the Secondary base shows **1200 pu**; a Secondary sample with declared Unknown against the Primary base shows **0.000797 pu**; both labelled *Unverified*. Retention keeps such numbers; blocking removes them together with the legitimately correct ones.

Options: **R** retain unchanged · **B** block (`base_required`, ENG fallback) · **N** narrow block: retain everything except the one combination with a deterministic ≥ 100× risk — a Secondary-declared base against a non-strict sample side.

| Class | What "Unverified" is today | Retain (R) | Block (B) | Narrow (N) | Recommendation [PROPOSAL] |
|---|---|---|---|---|---|
| **Raw Voltage** | `configured` numerics, `unverified`, because sample side or stored base side is unknown (CSV/Excel/BEN32/partial COMTRADE; every pre-existing group with default base side). | Unchanged numbers. Strict sample side now **upgrades** them to compatible/converted (an intentional change, §10 IC list). | PU of every recording without Recording Details evidence disappears until a side is set; rewrites the contracts listed in matrix §4.1 (`test_per_unit_voltage_reference_safety`, `test_pu_ssot_001_calc_voltage_ref_side`, `per-unit-reference-safety`, `pulu-auto-reference`). | Removes the 1200-pu class only; Primary-base/Unknown-sample numbers stay. | **R through S4**; **N** offered as a low-risk option the owner may add at S2; **B only after the §5.1 census.** |
| **Raw Current** | Same mechanism; reachable only through the backend API (UI shows ENG, DEC-212). | Unchanged; independent of the recording. | The largest regression: every manual Ibase typed without a side. | Not applicable (no ≥100× combination is unique to it). | **R through S4**; revisit with the census. |
| **Calculated Voltage** | **Every** result is Unverified today (no side is passed, C-5). | Unchanged until lineage. After S3, strict uniform leaves become compatible/converted. | Removes all calculated Voltage PU on every recording — rejected by the owner (OD-4) in blanket form. | After S3, only for non-strict leaves. | **R**; non-strict leaves keep today's Unverified; strict leaves upgrade (S3). |
| **Calculated Current** | Single-authority Automatic with Unknown retains numbers; cross-authority Automatic, result Manual and `strict` already fail closed; `legacy_manual` keeps the old denominator. | Unchanged. | Contradicts the PU-CORE-001 H2 owner decision (retain, defer to Phase C). | — | **R**; `legacy_manual` untouched. |

### 5.1 Read-only census [PROPOSAL, S1]
A shadow harness evaluates every V/I channel of the owner's reference recordings under *old gate* vs *strict resolver* and tabulates strict-direct / strict-converted / historical-Unverified / blocked, **per class**. It changes no behaviour and turns OD-2 into counts. I could not count the owner's recordings (assumption: they are not available to this audit).

---

## 6. The 4.35 % VT discrepancy — exact evidence

**Inputs (verified against the production code):** nominal L-L **132 000 V**; VT **138 000 V / 110 V** (ratio 1254.5454…); stored `secondary_voltage_ll_v` **110 V** (the VT secondary rating); L-L representation; system exactly at nominal.

| Quantity | Value | How obtained |
|---|---|---|
| Secondary sample at nominal | 132 000 × 110 / 138 000 = **105.217391304 V** | physics (independent) |
| Legacy denominator | **110 V** | `resolve_voltage_base_for_group` (`voltage_group_config.py:344-350`) — probe shows `denominator_V = 110.0` |
| Derived denominator `nominal ÷ ratio` | **105.217391304 V** | oracle |
| Correct PU | **1.000000** | sample ÷ derived |
| **Production PU today** | **0.956522** (`compatible`, `configured`) | probe: executed, not modelled |
| Error | `0.956521739 / 1 − 1` = **−4.347826 %** = **−1/23** exactly (oracle asserts it to 1e-55) | derived |

**Closed form.** `pu_legacy = nominal / V_VTprimary`, so `error = nominal / V_VTprimary − 1`. The 4.35 % is the figure for `V_VTprimary / nominal = 23/22 = 138/132 = 1.04545` (equally 230/220, 115/110, 69/66, 34.5/33). It is **zero when the VT primary equals the nominal**, and 4.76 % for 400/420 kV. Example table (oracle):

| nominal | VT primary / secondary | secondary sample | production PU | error |
|---|---|---|---|---|
| 132 kV | 138 kV / 110 V | 105.217391 V | 0.956522 | −4.3478 % |
| 132 kV | 132 kV / 110 V | 110.000000 V | 1.000000 | 0 |
| 275 kV | 275 kV / 110 V | 110.000000 V | 1.000000 | 0 |
| 220 kV | 230 kV / 110 V | 105.217391 V | 0.956522 | −4.3478 % |
| 400 kV | 420 kV / 110 V | 104.761905 V | 0.952381 | −4.7619 % |
| 132 kV | 138 kV / 63.5 V | 60.739130 V | 0.956522 | −4.3478 % |

**Why it exists.** The legacy value is a **winding rating** written automatically (C-2); rating-as-denominator is correct only when the system nominal equals the VT primary rating. DEC-215 makes this coincide *by construction* for the nominal-derived VT (primary = nominal, secondary 110 V ⇒ `nominal ÷ ratio` ≡ 110 V; asserted for 4 voltage levels), so the discrepancy appears only with a `manual`/`recording_metadata` VT whose primary differs from the nominal.

**Consequence for R-4.** Preserving the legacy output (P1) preserves a known −4.35 % error in exactly the cases where it appears. Recommended end state P4 (§10) distinguishes by authority; S2 default is P1 plus a diagnostic, i.e. **zero numeric change**.

---

## 7. Operation-aware lineage for calculated channels (OD-4)

Rules that run **first and unchanged**: DEC-213 calibration leaves → calculated Current path (`resolve_calculated_current_per_unit`) → DEC-116 representation gate → group-aware inheritance / DEC-049 profile. Lineage only supplies the **sample side and the ratio** for the denominator of a base that has already been resolved. The **leaf set** is the transitive set of source channels, as `calculated_current_per_unit.visit()` already collects; each leaf contributes `(strict side, owning group, ratio authority)` from `evaluate_channel_side()`.

| Operation (real name) | Today (base) | Lineage rule | If the rule holds | Otherwise | Slice |
|---|---|---|---|---|---|
| `reverse_polarity`, `absolute_value`, `multiply_constant`, `rms` on one source leaf (Voltage or Current) | inherits the leaf's group/source verbatim | inherit the leaf's strict side and its group ratio; `multiply_constant` keeps the side (the constant is the engineer's scale) | compatible / converted | non-strict leaf → historical Unverified (§5) | S3 (V), S4 (I) |
| unary **chain** (nested unary) | transitive verbatim | same single leaf through the chain | as above | as above | S3 / S4 |
| `line_to_line_voltage` (declared `line_to_line`, DEC-115) | unanimous owning group; declared representation selects ρ = 1 | **both** phase leaves share the **same strict side and the same owning group** (already required by `derive_per_unit_profile_id`) | denominator `nominal ÷ r` if secondary; direct if primary | different sides → block; non-strict → historical | S3 |
| `addition`/`subtraction`, **Voltage** | DEC-052/116: no representation → **no base** | not reached | unchanged | unchanged | none |
| `addition`/`subtraction`, **Current** | PC-001 live leaves, common base | same strict side on every leaf **and a single CT authority**; compare **denominators in the sample side**, not bases (C-8) | `Ibase ÷ CT` if secondary | mixed sides, or Secondary across authorities → block (DEC-209/210 deferral) | S4 |
| cross-group (same recording) | group inheritance → `None`, falls back to the Source Default | the Source Default has no ratio authority for a *Secondary* sample → **block** for secondary; primary unchanged | primary unchanged | secondary → `vt/ct_authority_unavailable` (`no_group`/`conflict`) | S3 / S4 |
| cross-recording | no common profile → `base_required` | not reached | unchanged | unchanged | none |
| nested multi-input | transitive | apply the leaf-set rule to the **transitive** leaves; any non-uniform leaf blocks | reduces to the row above | block | S3 / S4 |
| Stage 5B result Manual / explicit Unassigned | independent | unchanged; the manual base keeps its **declared** side and is compared with the leaves' strict side (F1–F5) | per §4.3 | declared Unknown → block | S4 |
| `rocof`, `active/reactive/apparent_power` (+ three-phase) | not PU-inherited | unchanged | — | — | none |

**Shared function [PROPOSAL].** S3 introduces one pure `resolve_calculated_side(leaf set)`; the protection consumers (Overcurrent, Impedance, Distance) currently block calculated channels as `calculated_channel_side_unavailable` (Amendments 5/6). They **must not** gain a second, different lineage rule; adopting the shared function there is a separate owner-approved slice, not part of PU-MIG.

**Preserved safeguards.** DEC-052/115/116 are evaluated before any side logic; Current PC-001 / 5A / 5B and the `legacy_manual` branch are unchanged except that the common-base comparison moves to denominators (C-8), which is a no-op whenever sides are equal.

**Secondary Voltage denominator path (OD-4).** `secondary_voltage_ll_v` remains valid for source **and** calculated Voltage (via the inherited group's config) wherever existing eligibility allows, **including no primary nominal** (cases VL1/VL2). The new derivation is added **beside** it; S3 does not alter it.

---

## 8. Manual Current bases, authoritative CT, and result lineage (OD-3)

| Declared side of the manual/direct (or result-owned) base | Primary samples | Secondary samples | Unknown / non-strict samples |
|---|---|---|---|
| **Primary** | direct | `B ÷ CT` | strict resolver refuses; historical Unverified (§5) |
| **Secondary** | `B × CT` (ratio authoritative, else block) | direct, no CT | same |
| **Unknown** | **never assumed Primary** — refuse | refuse | historical Unverified |

For a **calculated Current result**: a Stage 5B result Manual base keeps its **own declared side**, compared with the leaves' strict (uniform) side. An Automatic result uses its leaves' bases (8 above). Stored metadata (`base_reference_side` fields, the auto-base writer, the API and UI controls) is **read, never rewritten, and unchanged through S4**.

Constraints carried into S4: **K-1** equal sides required across leaves; **K-2** Secondary across distinct CT authorities stays unavailable (DEC-209/210 "shared physical reference", deferred); **K-3** common-base comparison on denominators (C-8).

---

## 9. Consumers, dependencies and the safe migration sequence

### 9.1 Production consumers that S1–S6 must update (all **[FACT]**, `e9c621c`)

| Consumer | Location | Today | Change | Slice |
|---|---|---|---|---|
| Source PU seam | `waveform_service._resolve_effective_per_unit` (`:143`, gate at `:226`); callers `:413, :646, :784, :945` (range, cursor-values, peak, annotation anchors) | raw `channel.measurement_side` | resolver side + group ratio | S2 |
| Compliance series | `compliance_series.py:155` (source), `:112` (calculated) | via the two seams | follows the seams; **values change** for the same cases | S2/S3 |
| Calculated PU seam | `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel` (`:1670`, gate `:1784`); callers `:1857, :1954, :2041, :2131` | passes **no** side | lineage side + ratio | S3 |
| Calculated Current | `calculated_current_per_unit.py` (`:90, :141, :144, :170`) | raw leaf flags, base-amount compare | strict leaf sides; denominators | S4 |
| Provenance | `per_unit_provenance_service.py` (source `:364, :375`; calculated `:458, :472`) | gate arguments differ per path (C-3) | one shared call | S2/S3 |
| Coverage | `per_unit_coverage_service.py:119, :130` | no Voltage group config (C-3) | one shared call; **counts change** | S2 |
| Group view | `measurement_group_view_service.py` | group-level base resolution | agree with the seams | S2 |
| API | `GET /sources/{id}/per-unit-resolution`, `GET /calculated-channels/{id}/per-unit-resolution` (`PerUnitResolutionOut`); 5 waveform/measurement response schemas carrying `per_unit_reference_compatibility` | `measurement_side` echoes the raw flag | additive fields; `measurement_side` semantics change (needs owner awareness) | S2 |
| Config writers | `PUT .../voltage-config`, `.../current-config`, `PUT /per-unit/sources/{id}`, `PUT /calculated-channels/{id}/per-unit-config`, `auto_base_service.py:248-298` | store `base_reference_side`, `secondary_voltage_ll_v` | **none through S4** | — |
| Frontend | refresh `wwRefreshDisplayedChannelsForPerUnitChange` (`index.html:36239`), `wwRdSideEnqueue` (`:36888`); badge wording (`:33257`); Base Reference Side controls (10 refs); WUI pane-local ENG/PU controls (must be confirmed to use the same refresh) | side writes do not refresh PU (PU ignores sides) | refresh after side writes; wording; provenance rows | S2 / S5 |

### 9.2 Sequence

| Slice | Scope | Needs first | Gate |
|---|---|---|---|
| **P0** | triage of the 131 shared browser failures, **at least the PU/source/current ones** (C-10), so S2–S4 have working guard rails | — (not authorised by this report) | owner decision to schedule |
| **S1** | pure `side_denominator` + oracle in `backend/tests` + read-only census; **no wiring** | owner approval of §10 D-1…D-6 | oracle passes; Primary/Primary golden file |
| **S2** | raw Voltage: one shared function for the four source seams, resolver side + ratio, refresh wiring, provenance, `measurement_side` semantics; fixes C-3 | S1, R-4/R-5/R-6/R-7, P0 | UAT-1 |
| **S3** | shared `resolve_calculated_side`; calculated Voltage per §7 | S2, OD-4 approval | UAT-2 |
| **S4** | Current: group Ibase `÷ CT`, calculated Current (K-1…K-3), Stage 5B | S3, OD-3 | UAT-3 |
| **S5** | UI wording/provenance only; **no control retirement** | S4, OD-3 replacement contract | UAT-4 |
| **S6** | retirement of the Base Reference Side input and legacy paths | separate approval | owner review |

Stop conditions for every slice: a Primary/Primary number changes; a refusal acquires a number; a DEC-213/052/116 gate is reordered; any consumer disagrees with the display seam.

---

## 10. Remaining owner decisions

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| **D-1 (OD-2)** | Historical Unverified, per class (§5) | R / B / N per class | **R** for all four classes through S4; optionally **N** for raw Voltage at S2; B only after the census |
| **D-2 (OD-3)** | Manual-base side metadata | keep / re-label / replace | **Keep through S4** (§8); decide replacement after UAT-3 |
| **D-3 (OD-4)** | Lineage table (§7) and the shared function | approve / amend | **Approve §7**; protection adoption separate |
| **D-4 (R-4)** | Precedence when `secondary_voltage_ll_v` and nominal ÷ ratio disagree (the 4.35 %) | **P1** legacy wins + diagnostic · **P2** derived wins · **P3** block · **P4** by authority (manual legacy wins; auto-written rating yields to nominal ÷ ratio) | **P1 at S2** (zero numeric change, diagnostic when `\|legacy ÷ derived − 1\| > 1e-6`); decide **P4** after the census |
| **D-5 (R-5)** | What activates the legacy secondary path | (i) stored `base_reference_side == "secondary"` · (ii) effective side secondary + valid value | **(i) through S4** |
| **D-6 (R-6)** | Primary sample vs Secondary-only base | convert with an authoritative VT / keep blocked | **Convert only with a valid, trusted ratio**, else block |
| **D-7 (R-7)** | `auto_nominal` ratio for secondary PU | accept + show / require manual or recording metadata | **Accept + show** (DEC-215; note the ratio makes the derived denominator ≡ 110 V) |
| **D-8 (R-8)** | API deprecation of `*_base_reference_side` | none through S4 / deprecate | **None through S4** |
| **D-9 (R-9/R-10)** | refresh scope; oracle into `backend/tests` | per source; yes | per source; **yes**, still importing no application code |
| **N-1** | Unify the four seams in S2, accepting that coverage counts change (C-3) | yes / defer | **Yes**; it is a DEC-210 obligation |
| **N-2** | Reuse existing reason names (`vt_authority_unavailable`, `ct_authority_unavailable`, the `RATIO_*` states, `recorded_side_authority.PROBLEM_*`) and add only `base_side_unknown`, `invalid_base_*`, `denominator_not_representable` | approve names | **Approve** (all names are proposals) |
| **N-3** | Schedule **P0** before S2 | yes / no | **Yes** |

Intentional output changes (carried from the matrix, unchanged): IC-1 … IC-8 (strict secondary Voltage becomes compatible/converted; an engineer's correction changes PU; calculated Voltage with strict leaves upgrades; wording). Everything else is bit-identical by design.

---

## 11. S1 specification — the pure-domain resolver

**Module** `backend/app/domain/side_denominator.py` (framework-free; imports only `math` and the existing numeric helpers). **No registry, no I/O, no sample values, no wiring, no change to any existing function.**

```python
@dataclass(frozen=True, slots=True)
class SideBase:      kind: str   # nominal_ll_primary | equipment_derived_primary | manual_direct | result_manual | legacy_secondary_voltage_ll
                     value: float          # SI: volts (L-L) or amperes; finite, > 0
                     declared_side: str    # primary | secondary | unknown   (nominal/equipment kinds must be primary)

@dataclass(frozen=True, slots=True)
class SampleSide:    side: str | None      # primary | secondary | None
                     problem: str | None   # None | calculated | unresolved | inferred | group_conflict   (recorded_side_authority.PROBLEM_*)
                     authority: str | None # provenance echo (engineer_group_override, recording_channel_declared, ...)

@dataclass(frozen=True, slots=True)
class SideRatio:     status: str           # configured | no_channels | no_group | not_configured | untrusted_authority | invalid | conflict
                     value: float | None   # primary / secondary, finite, > 0 when configured
                     authority: str | None # manual | recording_metadata | auto_nominal | mixed
                     group_ids: tuple[str, ...] = ()

def resolve_side_denominator(quantity: str, base: SideBase, sample: SampleSide, ratio: SideRatio | None,
                             *, representation: str | None = None) -> SideDenominator
```

**Result** `SideDenominator`: `status` (`resolved`/`unavailable`), `reason`, `denominator` (SI, **in the sample side's unit**), `denominator_side`, `conversion` (`direct` / `base_divided_by_ratio` / `base_multiplied_by_ratio`), `ratio_applied`, `ratio_authority`, `ratio_group_ids`, `sample_side`, `sample_authority`, `base_kind`, `base_side`, `representation_factor`.

**Unavailable reasons** (precedence of §4.3): `invalid_base_declaration`, `invalid_base_value`, `calculated_channel_side_unavailable`, `measurement_side_unresolved`, `measurement_side_inferred`, `measurement_group_side_conflict`, `base_side_unknown`, `vt_authority_unavailable` / `ct_authority_unavailable` (with the `ratio.status` as detail), `denominator_not_representable`. **[PROPOSAL: names]**

**Numerical rules.** Result finite, `> 0`, and not below the smallest normal float (otherwise `denominator_not_representable`); the same-side path returns `base.value × ρ` **unmodified** (P2); ratios are validated finite and `> 0`; no sample is ever passed in or returned.

**Worked examples** (independent oracle, 60-digit; full table in the JSON):

| Case | Inputs | D | pu |
|---|---|---|---|
| Primary L-L, nominal 275 kV | `s=primary`, `b=primary`, `r=2500` | 275 000 V (direct) | 1.000000 |
| Secondary L-L at 1.0 and 0.87 | same, `s=secondary` | **110.000000000 V** (`÷r`) | 1.000000 / 0.870000 |
| Secondary L-N at nominal | `ρ=1/√3` | **63.508529611 V** | 1.000000 |
| Legacy secondary base 110 V, secondary L-L | `r` not configured | 110 V (direct, ratio **not read**) | 1.000000 |
| Legacy secondary base, **primary** samples, VT 2500 | `b=secondary`, `s=primary` | 275 000 V (`×r`) | 1.000000 |
| same, ratio missing | — | refused `vt_authority_unavailable` | — |
| Equipment Ibase 2099.455524 A (1000 MVA, 275 kV), secondary samples, CT 2000 | `÷r` | **1.049727762 A** | 1.000000; secondary 1.0 A → **0.952628** |
| Manual **2100 A Primary**, secondary samples 0.525 A, CT 4000 | `÷r` | 0.525 A | 1.000000 |
| Manual **1 A Secondary**, secondary 0.5 A, no group | direct | 1 A | 0.500000 |
| Manual 1 A Secondary, primary 1000 A, CT 2000 | `×r` | 2000 A | 0.500000 |
| Manual **Unknown** | — | refused `base_side_unknown` | — |

**Independent acceptance tests** (to graduate into `backend/tests/test_pu_side_denominator.py`, importing the oracle's JSON, never application code):

| T | Test |
|---|---|
| T1 | Every row of the 324-row exhaustive table in `pu_mig_s0_final_expected.json` (status, reason, conversion, denominator to rel 1e-12). |
| T2 | P1 equivalence sweep (levels 0, 0.5, 0.87, 1, 1.1 × ratios 1e-3…1e6 × L-L/L-N). |
| T3 | P2/P3: same-side result equals `base × ρ` bit-for-bit under every ratio status. |
| T4 | P4 round trip and P5 commutation. |
| T5 | Refusal precedence (sample problem > unknown base > ratio). |
| T6 | Domain guards: NaN, ±inf, 0, negative, bool, string for value and ratio; equipment/nominal base declared Secondary. |
| T7 | Representability: subnormal and overflow denominators refused, not returned. |
| T8 | Golden file: Primary/Primary outputs equal the existing `resolve_voltage_base_for_group` / `apply_per_unit_to_value` results for a fixture grid (bit-identical). |
| T9 | Legacy numerics: sample-side = base-side secondary reproduces today's `denominator_volts` exactly (VL1/VL2). |
| T10 | Import guard: the module imports no service, registry, API or I/O module. |
| T11 | Census harness (read-only) runs over fixture recordings and reports §5.1 counts without changing any output. |

The 4.35 % table (§6) is **not** an S1 test of the resolver — it is the test of the S2 precedence decision (D-4) and the diagnostic threshold.

---

## 12. Verification of this report

| Check | Result |
|---|---|
| Baseline | `origin/uat/dev-d5a-20261121` = `e9c621c`; `backend/app` identical to `2144893` |
| Existing-behaviour probe (executed against production domain functions, read-only) | `existing_behaviour_probe_output.txt/.json`: 12 Voltage rows, 27 Current rows, gate agreement; 0.956522, 1200.0, 0.000797 as quoted |
| Final oracle (`python -I pu_mig_s0_final_oracle.py`) | 324-row table (56 resolved, 268 refused, 7 distinct reasons); invariants (a)–(g) hold; `--check` OK; the 4.35 % equals −1/23 (asserted to 1e-55) |
| Oracle ↔ production agreement | production legacy value 0.956522 equals the oracle's independent `nominal / V_VTprimary` (0.956521739) |
| Oracle ↔ earlier oracle | 63.508529611 V, 1.049727762 A and 0.952628 agree with the v2 oracle's V2 and I2/I3 |
| Tests | **No test suite or browser run was executed for this slice**; no production file differs from `e9c621c` (the worktree's only changes are under `docs/`) |
| Not verified | the owner's recordings were not available, so §5.1 counts are unknown; behaviour of the WUI pane-local PU controls against the refresh path (S5) was not exercised |

Evidence folder: `docs/project-memory/evidence/pu-mig-s0-final-2026-11-24/` (`pu_mig_s0_final_oracle.py`, `pu_mig_s0_final_expected.json`, `existing_behaviour_probe.py`, `existing_behaviour_probe_output.txt/.json`).

**Stop for owner engineering review.** S1 does not start until D-1 … D-6 and N-1 … N-3 are answered.
