# PU-MIG S0 — Response to the Final Owner Decision Review

**Date:** 2026-11-24
**Branch:** `audit/pu-mig-s0-final-contract` (worktree `.local-data/pu-mig-s0-contract`), based on `e9c621c`. Local only: **not pushed, merged or deployed.**
**Scope:** documentation, executed read-only probes and a triage plan. **No production code, test, API, UI or configuration was changed. S1 is not authorised and not started.**
**Companion to:** [PU_MIG_S0_FINAL_RECONCILIATION_2026-11-24.md](PU_MIG_S0_FINAL_RECONCILIATION_2026-11-24.md). Where this document differs from it, this document governs.

Labels: **[APPROVED]** owner-decided · **[FACT]** verified in code at `e9c621c` or by an executed probe · **[PROPOSAL]** my recommendation · **[OWNER]** needs an explicit owner decision · **[CORRECTION]** an error or overstatement in my earlier S0 material.

---

## 0. Owner dispositions recorded, and corrections to my earlier S0 report

### 0.1 Dispositions (owner message of 2026-11-24)

| Item | Owner disposition | Recorded effect |
|---|---|---|
| S0 audit | Provisionally accepted as investigation work | S1 is **not** authorised |
| **D-2** | **Agreed.** Preserve existing manual Current base reference-side semantics through S4 | no schema/API/UI/writer change to manual-base side metadata through S4 |
| **D-3** | **Agreed in principle:** shared, operation-aware calculated-channel lineage architecture. Final operation-specific rules remain subject to review | S3 may not start on the §7 table as written; the table is a draft |
| **N-1** | **Agreed in principle:** PU waveform, calculated-channel, provenance and coverage consumers use one authority and denominator policy | S2 designs one shared function |
| **N-3** | **Agreed:** focused P0 browser-guardrail triage before S2 | plan in §6 |
| **D-1** | **Open.** Historical Unknown/Unverified behaviour must not be silently changed, **and** must not be represented as verified engineering PU | §1 restates D-1 with that two-sided constraint |
| **D-4** | **Open.** No general rule that the legacy secondary denominator always wins; distinguish independently configured Secondary bases from values populated from VT winding ratings | §1–§3 |
| D-5 … D-9, N-2 | Pending review | §1 |

### 0.2 Corrections to my earlier S0 material [CORRECTION]

| # | What I wrote | What the evidence shows | Where fixed |
|---|---|---|---|
| X-1 | S0 report C-1 and §6: "production returns 0.956522 for a system at nominal **whenever** `secondary_voltage_ll_v` is the VT secondary rating and the VT primary differs from the nominal". | The arithmetic is exact, but the **mechanism was overstated**. The automatic writer produces a secondary-only base with **no nominal and no VT** (probe §1/§6 M1), so no "ratio-derived denominator" exists for it. The 0.956522 reading (versus 1.0) exists only when an **engineer-visible state** holds *nominal 132 kV + a manual VT 138:110 + a secondary base of 110 V* (probe M3/M6/M7). Without a nominal and VT the 110 V base simply means "1.0 pu = VT rated secondary", for which 0.9565 is correct by definition. | §2, §3 |
| X-2 | S0 report §6: the `recording_metadata` VT authority is among the ratio sources. | **No production code writes `vt_authority = "recording_metadata"`** (only `update_voltage_configuration` writes `manual` / `not_configured`; the value is read, never stored). The ratio sources actually reachable are `manual` and the derived `auto_nominal` (DEC-215). | §2.3 |
| X-3 | Commit `e5c6fce` and S0 report §1: the preserved assessment is "byte-identical to what the 2026-11-24 assessment delivered … no later edit". | **Inaccurate.** `e5c6fce` held the initial `Write` payload; one `Edit` six seconds later, **before delivery**, corrected a line-number reference. Delivered text = Write + that Edit. Fixed in commit `4b53d09`; provenance in §5. | §5 |
| X-4 | S0 report §2.1 (row A7) and §3 treated Amendment 7's formulas as approved. | Amendment 7 records two behaviours that are **not** approved (§4). | §4 |

---

## 1. Request 1 — the complete text of §10, with options and consequences

### 1.1 §10 exactly as delivered in the S0 report

> ## 10. Remaining owner decisions
>
> | ID | Decision | Options | Recommendation |
> |---|---|---|---|
> | **D-1 (OD-2)** | Historical Unverified, per class (§5) | R / B / N per class | **R** for all four classes through S4; optionally **N** for raw Voltage at S2; B only after the census |
> | **D-2 (OD-3)** | Manual-base side metadata | keep / re-label / replace | **Keep through S4** (§8); decide replacement after UAT-3 |
> | **D-3 (OD-4)** | Lineage table (§7) and the shared function | approve / amend | **Approve §7**; protection adoption separate |
> | **D-4 (R-4)** | Precedence when `secondary_voltage_ll_v` and nominal ÷ ratio disagree (the 4.35 %) | **P1** legacy wins + diagnostic · **P2** derived wins · **P3** block · **P4** by authority (manual legacy wins; auto-written rating yields to nominal ÷ ratio) | **P1 at S2** (zero numeric change, diagnostic when `\|legacy ÷ derived − 1\| > 1e-6`); decide **P4** after the census |
> | **D-5 (R-5)** | What activates the legacy secondary path | (i) stored `base_reference_side == "secondary"` · (ii) effective side secondary + valid value | **(i) through S4** |
> | **D-6 (R-6)** | Primary sample vs Secondary-only base | convert with an authoritative VT / keep blocked | **Convert only with a valid, trusted ratio**, else block |
> | **D-7 (R-7)** | `auto_nominal` ratio for secondary PU | accept + show / require manual or recording metadata | **Accept + show** (DEC-215; note the ratio makes the derived denominator ≡ 110 V) |
> | **D-8 (R-8)** | API deprecation of `*_base_reference_side` | none through S4 / deprecate | **None through S4** |
> | **D-9 (R-9/R-10)** | refresh scope; oracle into `backend/tests` | per source; yes | per source; **yes**, still importing no application code |
> | **N-1** | Unify the four seams in S2, accepting that coverage counts change (C-3) | yes / defer | **Yes**; it is a DEC-210 obligation |
> | **N-2** | Reuse existing reason names (`vt_authority_unavailable`, `ct_authority_unavailable`, the `RATIO_*` states, `recorded_side_authority.PROBLEM_*`) and add only `base_side_unknown`, `invalid_base_*`, `denominator_not_representable` | approve names | **Approve** (all names are proposals) |
> | **N-3** | Schedule **P0** before S2 | yes / no | **Yes** |
>
> Intentional output changes (carried from the matrix, unchanged): IC-1 … IC-8 (strict secondary Voltage becomes compatible/converted; an engineer's correction changes PU; calculated Voltage with strict leaves upgrades; wording). Everything else is bit-identical by design.
>
> ---

### 1.2 The decision register, expanded (options, consequences, updated recommendation)

The earlier §10 listed one recommendation per item. The register below gives every option and its consequence, reflects the owner dispositions of §0.1, and corrects §10 where the evidence in §2–§3 changes it.

#### D-1 (OD-2) — Historical Unknown / Unverified references, per class — **OPEN**

Owner constraint: the numbers must **not be silently changed**, and must **not be represented as verified engineering PU**.

| Option | Meaning | Consequence |
|---|---|---|
| **R** | Retain the numbers and today's wording | Satisfies "not silently changed". **Fails "not represented as verified" in places** (below). |
| **R+** | Retain the numbers; make "not verified" an explicit, uniform **verification state** on every surface and consumer | Satisfies both halves. Additive API/provenance field; no number changes. |
| **N** | R+, plus block only the ≥100× combination (a Secondary-declared base against a non-strict sample side) | Removes the 1200-pu class; changes outputs for those cases only. |
| **B** | Block (`base_required`, ENG fallback) | Strongest; removes all historical PU for recordings without Recording Details evidence; rewrites contracts. |

**Where retention currently looks "verified" [FACT]:**
(i) `services/compliance_series.py`, `compliance_readiness_service.py` and the other `compliance*` services contain **no reference to `reference_compatibility`** (searched), so an Unverified PU value reaches Compliance without any marker.
(ii) The coverage service reports a Voltage mismatch as `configured / unverified` while the display blocks it (S0 report C-3), i.e. the *state* is wrong, not just unlabelled.
(iii) A strict Primary sample with a stored Unknown base side today gets the same number labelled *Unverified*; after S2 it would be *compatible*, which is correct, but only if the verification state is a first-class field rather than inferred from labels.

**Per class** (unchanged facts from the S0 report §5; the recommendation changes):

| Class | R | R+ | N | B |
|---|---|---|---|---|
| Raw Voltage | unchanged | **recommended** | optional add-on at S2 | after the census only |
| Raw Current (API-only; UI shows ENG, DEC-212) | unchanged | **recommended** | n/a | after the census only |
| Calculated Voltage (every result Unverified today; no side passed) | unchanged | **recommended**; strict, uniform leaves upgrade at S3 | after S3, non-strict leaves | rejected in blanket form (OD-4) |
| Calculated Current (single-authority Automatic retains; strict paths already fail closed; `legacy_manual` retained, PU-CORE-001 H2) | unchanged | **recommended** | n/a | contradicts H2 |

**Updated recommendation [PROPOSAL]: R+ for all four classes through S4**, with the verification state defined once (suggested values: `verified_direct`, `verified_converted`, `unverified_historical`, `blocked`) and read by display, provenance, coverage and Compliance. The read-only census (S0 report §5.1) precedes any N or B.

#### D-2 (OD-3) — Manual-base side metadata — **AGREED**
Preserve existing semantics through S4 (§0.1). Consequences carried forward: `base_reference_side` fields, `auto_base_service` writers, API and UI controls unchanged; the strict resolver only **reads** the declared side. No replacement contract is designed before UAT-3.

#### D-3 (OD-4) — Calculated-channel lineage — **AGREED IN PRINCIPLE**
Agreed: one shared, operation-aware lineage function (`resolve_calculated_side`), PU-first; protection consumers (Overcurrent/Impedance/Distance) adopt it only by a separate approval. **Not agreed:** the operation rows of S0 report §7. Consequence: S3 cannot start until each row is reviewed; S0 §7 is a draft agenda, not a rule set.

#### D-4 (R-4) — Precedence between `secondary_voltage_ll_v` and nominal ÷ ratio — **OPEN**

Owner constraint: do **not** approve "legacy secondary always wins"; distinguish an **independently configured Secondary engineering base** from a value **populated from a VT winding rating**.

| Option | Rule | Consequence |
|---|---|---|
| P1 | The stored secondary value always wins (+ diagnostic) | **Not approvable as a general rule** (owner). It preserves a rating-as-base silently. |
| P2 | Nominal ÷ ratio always wins | Overrides an engineer's deliberate Secondary base (probe M4-type values, or "1 pu = rated secondary" by intent). Rejected for the same reason as P1. |
| P3 | Block when both exist and disagree | Safe but removes PU for M3/M6/M7 until the engineer resolves it; no origin needed. |
| **P4** | **Decide by recorded origin of the secondary value** (below) | Matches the owner's distinction. **Needs provenance that does not exist today** (§2.2). |
| **P5** | P3-style *diagnostic only* (numbers unchanged) until the origin field exists and a census is done, then P4 | Zero numeric change at S2; honest labelling immediately. |

**P4 in full [PROPOSAL, needs owner approval]:**
- **Origin `engineer`** (API-entered, or entered together with a nominal): an independently configured Secondary base. **Authoritative; never overridden** by nominal ÷ ratio; if nominal and an authoritative ratio imply a different denominator, a non-blocking diagnostic shows both numbers.
- **Origin `vt_winding_rating_auto`** (written by `auto_base_service`): a *rating-based* base. Used as the denominator **when it is the only base** (no nominal — the actual auto-writer output, M1), labelled "VT secondary rating, auto-populated". When a nominal **and** an authoritative ratio exist, it **yields** to nominal ÷ ratio, flagged as an intentional output change for those groups.
- **Origin `origin_not_recorded`** (every value stored today, and any value whose origin cannot be proven): treated as engineer-configured — **preserved**, labelled "origin not recorded". Absent provenance never promotes or demotes a value.
- **Prerequisites (all production changes, none in S1):** an additive `secondary_base_origin` field set at write time; the auto-writer must **not overwrite** an `engineer` value (verified hazard, §2.2 3b); API/UI wording.

**Recommendation [PROPOSAL]: P5 now, P4 once the origin field is approved and a census exists.** S2 numerics are then unchanged for every existing configuration.

#### D-5 (R-5) — What activates the legacy secondary path — **PENDING**

| Option | Consequence |
|---|---|
| (i) stored `base_reference_side == "secondary"` **and** a valid `secondary_voltage_ll_v` (today) | Zero change; independent of the recording side. |
| (ii) effective (Recording Details) side secondary + valid value | Ties the base to the recording; can switch the path when an engineer corrects the recording side. Mixed with D-4/D-6 it multiplies cases. |

**Recommendation: (i) through S4** (preserves metadata and workflows, D-2); decide (ii) only at S6.

#### D-6 (R-6) — Primary samples against a Secondary-only base — **PENDING** (and currently mislabelled as approved, §4)

| Option | Consequence |
|---|---|
| Convert (`D = B × r`) with an authoritative ratio, else block | Gives 1.0 pu for primary samples; **needs a ratio**, and the auto-writer's base has **no nominal and no VT** (M1), so the conversion is impossible there and would block. |
| Keep blocked | Matches today (known mismatch blocks). Loses the equivalence P1 for these groups. |

**Recommendation: convert only with a valid, trusted ratio, else block** — but this is **not** part of Amendment 7 until you approve it.

#### D-7 (R-7) — `auto_nominal` ratio for secondary PU — **PENDING**

| Option | Consequence |
|---|---|
| Accept + show provenance (DEC-215) | `nominal ÷ ratio ≡ 110 V` for **any** nominal (asserted in the oracle), so the derived denominator equals a 110 V base. **If the real VT secondary is not 110 V or the real ratio differs, the assumption is wrong and the PU reads off** (M2: real VT 138:110 gives 0.9565 against the assumed 132:110). DEC-215 already accepted this; the consequence is that provenance **must** be visible. |
| Require `manual` (or recording metadata, once something writes it — X-2) | PU unavailable until an engineer enters a VT; stricter than DEC-215 (a decided rule). |

**Recommendation: accept + show.**

#### D-8 (R-8) — API deprecation of `*_base_reference_side` — **PENDING**
None through S4 (consequence of D-2); revisit at S6.

#### D-9 (R-9, R-10) — refresh scope; oracle placement — **PENDING**
Refresh **per source** (the existing `wwRefreshDisplayedChannelsForPerUnitChange(sourceId)` takes a source id; a per-group scope would be a new frontend contract). The oracle graduates into `backend/tests` at S1, still importing no application code.

#### N-1 — One authority and denominator policy for every PU consumer — **AGREED IN PRINCIPLE**
Consequences: coverage counts change (the C-3 disagreement disappears); compliance values change for the same cases; the work is wide (§9 of the S0 report lists 10 consumers) and must be in **one** slice with golden-file protection for Primary/Primary. R+ (D-1) means the shared function also returns the verification state.

#### N-2 — Reason-code vocabulary — **PENDING**
Option A: reuse `vt_authority_unavailable`, `ct_authority_unavailable`, the `RATIO_*` states and `recorded_side_authority.PROBLEM_*`, add only `base_side_unknown`, `invalid_base_*`, `denominator_not_representable`. Option B: a separate PU namespace. A keeps one vocabulary across Overcurrent/Impedance/Distance/PU (fewer client branches); B isolates PU from protection wording. **Recommendation: A.** All names remain proposals.

#### N-3 — P0 browser-guardrail triage before S2 — **AGREED** (§6).

---

## 2. Request 2 — where `secondary_voltage_ll_v` is populated, and what provenance says

### 2.1 The writers [FACT]

| Writer | Location | What it stores | Authority written |
|---|---|---|---|
| **Automatic** | `app/services/auto_base_service.py:248-259` (`_configure_voltage_group`) | `secondary_voltage_ll_v = evidence.secondary_measured.value_kv × 1000`, `base_reference_side = "secondary"`, optional `nominal` only when `sufficient_for_auto_nominal` | `base_authority = auto_resolved` |
| Source of that value | `app/domain/auto_base_evidence.py:545-590` (Step 4) | `kv = _to_kv(ch.secondary_ratio, ch.unit)` for channels flagged secondary; `secondary_ratio` is documented at `:164` as the **"VT/CT secondary winding rating, channel unit"** (COMTRADE CFG secondary field; BEN `secondary_rating`) | — |
| Engineer (API only) | `app/api/v1/measurement_groups.py:425-426` → `update_voltage_configuration` | whatever the client sends | **unchanged unless a nominal is supplied** (then `manual`) |
| Clearing | `auto_base_service.py:277-279` (primary path), `voltage_group_config_service.py:~157` (nominal edited without a secondary) | `None` | as above |

**No UI control reads or writes the field** (`frontend/index.html` contains no `secondary_voltage` reference). In the product as deployed, an engineer-entered Secondary base can only arrive through a direct API call.

The module's own contract states the value is a rating, not a base: `auto_base_evidence.py` C2 — *"CT/VT winding ratings (primary_ratio, secondary_ratio) are transformation information. They produce candidates, not authoritative nominal values."* The auto-writer nevertheless stores the rating **as the denominator** (`voltage_group_config.py:344-350`).

### 2.2 What provenance distinguishes — executed [FACT]

`secondary_base_provenance_probe.py` runs the **production** writer, configuration service, resolver and view builders on in-memory registries (output: `secondary_base_provenance_probe_output.txt`).

| # | Executed step | Result |
|---|---|---|
| 1 | Auto-writer on a secondary-flagged L-L recording, channel rating 138 kV : 110 V | `nominal_ll_kv=None`, `base_reference_side=secondary`, `base_authority=auto_resolved`, `secondary_voltage_ll_v=110.0`, **VT not stored** (`vt_authority=not_configured`) |
| 2 | Same, channels carry only the secondary rating | identical |
| 3a | Engineer edits **only** `secondary_voltage_ll_v` (105.217391304) on that group | value changes; **`base_authority` stays `auto_resolved`** |
| 3b | The automatic writer runs again | **the engineer's 105.217391304 is overwritten with 110.0** |
| 3c | Engineer types nominal 132 kV only | nominal 132, authority `manual`, **secondary cleared**, resolver `base_required / secondary_equivalent_not_configured` (safe) |
| 3d | Engineer types nominal 132 kV **and** secondary 110 V | both stored, authority `manual` |
| 4 | Read models | the group view exposes `base_authority` (**one value for the whole group**) and `secondary_voltage_ll_v`; `PerUnitChannelProvenance` exposes **neither** `secondary_voltage_ll_v`, nor `base_authority`, nor any origin of the secondary denominator |

**Answer.** Provenance does **not** distinguish a VT-rating-populated value from an engineer-entered Secondary base:

1. there is **no per-field origin** for `secondary_voltage_ll_v`;
2. the only marker, `base_authority`, is **group-wide** and is not updated when only the secondary value is edited (3a), so an engineer-typed value on an auto group is still labelled `auto_resolved`;
3. because the label stays `auto`, the automatic writer treats the engineer's value as its own and **overwrites it** (3b) — a verified hazard (API-only exposure);
4. `PerUnitChannelProvenance` and the per-unit API never state which denominator path was used or where the secondary value came from.

### 2.3 Related facts [FACT]
- The VT ratio is stored only by `update_voltage_configuration` (`manual`) or derived by `derive_auto_nominal_vt` (`auto_nominal`: primary = nominal, secondary = **110 V**). `grep` finds **no writer of `vt_authority="recording_metadata"`**.
- The ratio sources that can reach `resolve_transformer_context` today are therefore `manual` and `auto_nominal`.

---

## 3. Request 3 — comparison matrix, 132 kV system, VT 138 kV : 110 V

Secondary samples at nominal: `132 000 × 110 / 138 000 = 105.217391304 V`. All "existing" values are **executed** against the production resolver (probe §6); "ratio-derived" is `nominal ÷ (VT primary ÷ VT secondary)` from the stored (manual) or auto-nominal VT.

| # | Stored state | Existing denominator | Existing PU | Ratio-derived denominator | Ratio-derived PU | Notes |
|---|---|---|---|---|---|---|
| **M1** | **What the auto-writer actually stores:** no nominal, no VT, `secondary=110 V`, `auto_resolved` | 110 V | **0.956522** | **not computable** (no nominal; `auto_nominal` needs a nominal) | — | Base meaning is "1.0 pu = VT rated secondary"; nothing in the product knows the system is 132 kV, so 0.9565 is **not detectable as an error** |
| **M2** | nominal 132 + `secondary=110`, no VT stored | 110 V | 0.956522 | 110 V (`auto_nominal` VT 132:110) | 0.956522 | Derived = existing **by construction**; the physical VT (138:110) is unknown to the product (D-7) |
| **M3** | nominal 132 + `secondary=110` + **manual VT 138:110**, authority `manual` | 110 V | **0.956522** | **105.217391 V** | **1.000000** | The disagreement (−1/23 = **−4.3478 %**). Reachable only by an engineer entering all three (API for `secondary`) |
| **M4** | as M3 but the engineer's **secondary base 105.217391304 V** | 105.217391 V | 1.000000 | 105.217391 V | 1.000000 | **Independently configured Secondary base; agrees** |
| **M5** | nominal 132 + manual VT 138:110, secondary **cleared** (engineer typed nominal) | blocked: `secondary_equivalent_not_configured` | — | 105.217391 V | 1.000000 | Safe today; the derivation would make it computable (needs D-4/D-5) |
| **M6** | as M3, authority **`legacy_manual`** (origin unknown) | 110 V | 0.956522 | 105.217391 V | 1.000000 | Origin cannot be proven |
| **M7** | as M3, authority **`auto_resolved`** (engineer edited only the secondary value via API) | 110 V | 0.956522 | 105.217391 V | 1.000000 | **Mislabelled**: an engineer value labelled auto; overwritable (3b) |

**Behaviour by distinction [PROPOSAL, pending D-4]:**

| Situation | Behaviour under P5 (S2) | Behaviour under P4 (end state) |
|---|---|---|
| **Secondary base explicitly configured** (M4; and an engineer's 110 V with a manual VT, if the origin is recorded as `engineer`) | Existing denominator and PU **unchanged**; diagnostic if nominal ÷ ratio differs | Authoritative; never overridden; diagnostic shows both numbers (M3 with origin `engineer`: stays 0.956522, **flagged**, because 110 V is then the engineer's chosen base) |
| **Value populated from a VT rating** (M1: sole base; M3-like with origin `vt_winding_rating_auto`) | Unchanged numerically; label "VT secondary rating, auto-populated" | Sole base: used, labelled. With nominal **and** authoritative ratio: yields to nominal ÷ ratio (**intentional change**, 0.956522 → 1.000000) |
| **Provenance unavailable** (M6, and every value stored today) | Unchanged; label "origin not recorded"; **never** demoted by absence of provenance | Same: preserved as engineer-configured; the owner may later choose to re-prove origins |

The decisive point for the owner: **M3, M6 and M7 hold the identical stored numbers**; only an origin record can tell an engineer's deliberate 110 V base from an auto-populated rating. Without that record any rule that changes the number would be a guess, and any rule that keeps it would be P1.

---

## 4. Request 4 — review of DEC-216 Amendment 7

Amendment 7 (on this audit branch only; unpublished) records OD-1. Reviewed sentence by sentence against DEC-216, the owner's OD-1 wording and the open items.

| # | Text in Amendment 7 | Verdict |
|---|---|---|
| A7-1 | Header and status: "OD-1 confirmed in principle … authorises no implementation; S1-S6 need separate approval" | **Accurate.** |
| A7-2 | "PU may select or derive a compatible denominator … (Primary sample + Primary base: direct; Secondary sample + Primary base: base divided by the ratio; …)" | **Accurate**: these are DEC-216's own PU cases. |
| A7-3 | "**Secondary base on Primary samples: base multiplied by the ratio**" | **Incorrectly labelled as decided.** DEC-216 says only that a secondary base is never reinterpreted as primary and that a needed conversion without a ratio blocks; it does **not** approve converting a Secondary base onto Primary samples. That is D-6 / R-6, **pending**. Today this combination is blocked when the sample side is known. |
| A7-4 | "a base declared on the sample's own side: direct" | **Accurate** (existing behaviour; Current Secondary/Secondary across distinct authorities stays deferred, DEC-209). |
| A7-5 | "Narrowly supersedes only DEC-210's 'no CT/VT ratio scaling' and 'known mismatch blocks PU', and DEC-211's equivalent … only where the effective side is strict-usable and the ratio is authoritative" | **Consistent with OD-1** ("narrow amendment to DEC-210/211"), **except** that it implicitly includes A7-3. |
| A7-6 | "Where the conversion is not authoritative (ratio missing, invalid, untrusted, conflicting, channel in no group, **or any contributing side not strict**) **PU still blocks**" | **Misstates behaviour and pre-decides D-1.** A non-strict (Unknown/inferred) side does **not** block today: DEC-210/211 retain it as *Unverified*, and D-1 is open with the owner's "not silently changed" constraint. The clause as written is option **B**. Only a **known** P/S mismatch without an authoritative ratio blocks. |
| A7-7 | "An unknown or inferred-only side never establishes a conversion" | **Accurate** (A3, DEC-216 Amendments 1, 3). |
| A7-8 | "Preserved: samples, base meanings, DEC-213 gates, L-L/L-N, DEC-052/115/116, DEC-209/212, numerical safeguards, DEC-215, a transformer rating is never a base" | **Accurate** (all decided). |
| A7-9 | "Not decided here (open): OD-2, OD-3, OD-4, precedence, API deprecation" | **Incomplete.** Omits D-6 (Secondary base on Primary samples), D-5, D-7, N-1/N-2, and now the D-4 distinction. OD-3 has since been **agreed** (D-2) and OD-4 agreed in principle (D-3). |

The same two overstatements recur in the matrix `PU_MIG_001_S0_DECISION_MATRIX_2026-11-24.md` (§2.2 first row "[SUPERSEDED] … or `base × ratio` for a secondary base on primary samples", and §3's last-but-one row) and in the S0 report (§4.3, A7 row). They are corrected by this document; the files themselves are left as delivered.

**Proposed replacement text for the second and fourth bullets (for owner approval; not applied — the existing text is untouched):**

> - PU may **select or derive a compatible denominator** from the consumed channel's effective Recording Details measurement side and the authoritative CT/VT ratio of that channel's own Measurement Group: Primary sample + Primary base — direct; Secondary sample + Primary base — the base divided by the ratio; a base declared on the sample's own side — direct. *Converting a Secondary-declared base onto Primary samples is **not** approved here (pending).*
> - **Narrowly supersedes only** DEC-210's "no CT/VT ratio scaling" and DEC-210/211's "known Primary/Secondary mismatch blocks PU", and only where the sample side is strict-usable and the ratio is authoritative. Where it is not, **the DEC-210/211 gate applies unchanged**: a known mismatch still blocks; an Unknown or inferred side still yields no conversion and its historical **Unverified** treatment is **not changed or removed by this amendment** (owner decision D-1 open).
> - **Not decided here (open):** historical Unverified policy per class (D-1); precedence and the distinction between an engineer-configured Secondary base and a value populated from a VT winding rating (D-4); activation of the legacy secondary path (D-5); a Secondary base on Primary samples (D-6); `auto_nominal` for secondary PU (D-7); API deprecation (D-8); the final operation-specific lineage rules (D-3). **Decided:** manual-base side semantics are preserved through S4 (D-2).

---

## 5. Request 5 — provenance of the preserved originals (recorded accurately)

| Artefact | Is it verified byte-for-byte against its original file? | How it was established |
|---|---|---|
| **Assessment** `PU_MIG_001_ASSESSMENT_2026-11-24.md` | **No — the original file no longer exists on disk** (it was created in the main checkout, then moved into the audit worktree and subsequently carried with a banner). The preserved text is a **replay of the session transcript**, cross-checked against a surviving git blob. Line endings: the editor tool on this machine normally writes CRLF (not checked for this file) while the git blob is LF-normalised, so the equality is **content-equal modulo line endings**, not a byte comparison with the disk file. | (1) Transcript line 393 (2026-11-23T22:25:31Z): the `Write` payload (sha256 `ab5076a9…`, 33 017 chars). (2) Transcript line 407 (22:25:37Z, **six seconds later, before delivery**): one `Edit` of one line (`:36533-36524` → `:36533-36568`, `:36494-36518`). (3) **Delivered text = (1) + (2)** (sha256 `c5e7088f…`, 33 033 chars). (4) The git blob `88c9244` minus its later two-line owner-review banner is **identical** to (3) (programmatic equality). So the delivered text is confirmed by two independent sources (transcript replay and a git object), neither of which is the original disk file. |
| `e5c6fce` (my earlier commit) | **Held (1) only** — the pre-Edit payload — and its message wrongly called it "byte-identical to what was delivered" [X-3]. | corrected by `4b53d09` (applies the one line); the message of `4b53d09` states the provenance |
| **v1 oracle** `pu_mig_oracle_v1_original.py` | **Yes, against a surviving original file.** | The transcript's creating command (line 337, 22:21:05Z) heredoc payload equals the scratchpad file `oracle/pu_mig_oracle.py` (3 608 bytes, mtime = creation time), which equals the committed copy; sha256 `480d12a0…f6fa` |
| S0 matrix, v2 oracle, expected JSON | Compared **byte-for-byte as git blobs** against `88c9244` (identical sha256 prefixes). They are not compared with a pre-commit disk file; `88c9244` is itself the first and only committed form. | `git show 88c9244:<path>` |
| Amendment 7 text | The diff `2144893..88c9244` applied unchanged; **not** edited here | — |

The only difference between what the owner received and what is now preserved is **zero lines** (after `4b53d09`); the only difference between the preserved assessment and the `88c9244` copy is the later banner.

---

## 6. Request 6 — focused P0 browser-test triage plan

**Facts [FACT].** 131 tests in 41 spec files fail **identically** on exact `3ed200c` and on `e9c621c` (integration report §3; sorted failing-test lists equal). They were run sequentially, `workers=1`, `retries=0`. None is caused by D5A-2B2C-1B. **No test is declared obsolete.**

### 6.1 What the failures wait for (all 131 parsed from the baseline logs; classification is by **first failing step**, not by test intent)

| Cat | First failing step | Tests | Evidence so far |
|---|---|---|---|
| **T1** | a control retired **before** `f24f1d7`: `#wwOpenPerUnitSettingsBtn` (22), `wwOpenPerUnitSettingsM…` (1, truncated in the log), `#measurementGroupsOverlay` (3), plus 1 related | **27** | `git log -S`: `wwOpenPerUnitSettingsBtn` removed by `1c60a1e` "retire Per-Unit Settings Hub from Waveform Analysis" (PU-UI-001 Slice B); `measurementGroupsOverlay` by `4161a63` "remove MG overlay/drawer … (Step C)". Absent at `f24f1d7`, `3ed200c`, `e9c621c`. |
| **T2** | the global `#wwUnitEngineeringBtn` / `#wwUnitPerUnitBtn` | **9** | static buttons present at `f24f1d7` (3/4 occurrences), reduced to JS references at `3ed200c`; the pane-local control `wwPaneUnitModeHtml` (`index.html:34653`) exists. A passing spec (`waveform-axis-units`) exercises ENG/PU switching, so the **function exists**. |
| **T3a** | upload flow: `#uploadModalOverlay` not hidden within 30 s (17), `#wwRdUploadBtn` not clickable (6), recording list (2) | **25** | snapshot of `waveform-empty-state:44`: `#wwRdUploadBtn` **resolves but is "not visible"** — the test is on the Waveform page, the Recording Details control is on another page. BEN5K uploads (`ben5k-*`, `power-provenance`): cause **not examined** (large/external fixtures; a 30 s modal wait). |
| **T3b** | `#workspaceRow` hidden | **11** | snapshot of `event-reconstruction-plot:520`: element resolves, `hidden`; active page is **Recording Details** |
| **T3c** | `#channelGroups tr.channel-row--toggle` / `details.source-recording` rows | **53** | snapshot of `playback:144`: the rows exist (`details.source-recording … open`) but are **hidden**; the active page is **Recording Details** (after upload) |
| T4 | other (3 timeouts, `ReferenceError: wwMgBaseSummary…`, a missing-function call, one assertion) | 6 | not yet examined |

**Working hypothesis H-1 (supported by three page snapshots, one per cluster; 128 tests classified by locator only):** after upload the product lands on **Recording Details**, whereas the legacy helpers assume the Waveform workspace (or the reverse for T3a). This is a *navigation-flow* difference, not a missing feature. It is a **hypothesis**, to be proven per test (§6.3), not a classification.

### 6.2 Priority — functional PU controls and numerical integrity first

| Tier | Specs (failing tests) | Count | Why first | Gate for |
|---|---|---|---|---|
| **1 — PU controls and PU numerics** | `per-unit-display-synchronization` 6, `per-unit-numeric-integrity` 4, `per-unit-reference-safety` 2, `per-unit-eligibility` 1, `per-unit-atomic-updates` 1, `pulu-auto-reference` 3, `voltage-only-pu-display` 4, `current-common-base` 3, `source-default-current-preview` 7, `ben5k-calculated-channel-pu-gate` 1 | **32** (T1 22, T2 4, T4 5, T3a 1) | the PU guard rails S2–S4 name as acceptance contracts | **S2** |
| **1b — numerical measurement and calibration gates** | `waveform-measurement-values` 5, `phasor_analysis` 1, `compliance_measurement` 2, `compliance_readiness` 1, `compliance-calibration-gate` 1, `ben5k-phasor-calibration-gate` 3 | **13** | numerical correctness of values the PU work feeds | S2/S3 |
| **2 — provenance and calibration badges** | `stage3b3-source-badge` 3, `power-provenance` 7 | **10** | provenance wording S2/S5 change | S2 |
| **3 — UI, time, playback, Event Reconstruction, layout** | `playback` 27, `playback_waveform_ownership` 8, `waveform-toolbar-t0-sync-refinement` 7, `calculated-channel-preview` 5, Event Reconstruction (12, 10 files), `waveform-empty-state` 3, `time-reference-interpretation` 3, `data-issues-panel` 2, `waveform-top-toolbar-migration` 2, `smoke` 2, `electrical-notation` 1, `phase-display-convention` 2, `waveform-auto-fit-range` 1, `timing-authority-invalidation` 1 | **76** | release hygiene; not PU numerics | after Tier 1 |

**Coverage gap to settle first [FACT-derived]:** 22 of the 32 Tier-1 failures target the **retired** Per-Unit Settings Hub / MG overlay. Their numerical intent is covered by 13 701 passing backend tests, but the **browser-level** PU guard rails for the *current* configuration surface (Recording Details → Group Details) must be identified or created; that decision is the owner's, not an automatic retirement.

### 6.3 Method (per failing test; nothing is weakened)

1. **Reproduce** on `3ed200c` and `e9c621c` — **done** for all 131 (identical).
2. **Diagnose without editing:** re-run the single test with trace and read the `error-context` page snapshot to see the real page state (done for three representatives; to be done for every Tier-1 test first).
3. **State the test's intent in one sentence** from its title and assertions (what physical/numerical fact it guards).
4. **Choose exactly one disposition**, each needing owner approval before any test file is edited:
   - **PORT** — change navigation/selectors only; the assertions stay character-identical (review shows the diff touches no `expect`).
   - **RE-HOME** — the same assertion is already exercised by a passing test; prove it by mapping and by a **mutation check** (see 6).
   - **RETIRE** — only for a control removed by an **approved** retirement commit **and** with replacement coverage proven; never by default.
   - **FIX PRODUCT** — a genuine defect on the baseline; reported separately, never fixed under P0.
5. **Never auto-classify:** T1/T2/T3 above are *first-failing-step* groups, not dispositions.
6. **Anti-vacuity:** every ported/re-homed numerical test must be shown to **fail** when the behaviour it protects is deliberately broken (a temporary mutation in a scratch copy of the backend or the formula), then pass when restored; the run must be on **both** `3ed200c` and `e9c621c`.
7. **Equivalence of runs:** same ports, `workers=1`, `retries=0`; no `skip`, `fixme`, `retries`, longer timeouts or loosened `expect` anywhere.
8. **Report** per test: id, intent, first failing step, snapshot evidence, disposition proposed, replacement/mutation evidence.

### 6.4 Order and exit criteria
- **P0-1:** Tier-1 diagnosis for all 32 + the coverage-gap settlement above (owner decision on the retired Settings Hub's browser coverage).
- **P0-2:** the H-1 experiment on **one** Tier-3 test in a **scratch copy outside the repository** (insert the Recording-Details → Waveform navigation, keep every assertion) to prove or refute the 64-test navigation hypothesis cheaply.
- **P0-3:** Tiers 1b and 2; then Tier 3.
- **Exit for S2:** Tier 1, 1b and 2 each either passing with all original assertions, or listed with an owner-approved disposition and equal-or-better replacement coverage. Tier 3 does not gate S2.
- **Stop conditions:** any case where the only way to pass is to weaken an assertion; any failure whose cause is a product defect (report, do not patch); any result that differs between `3ed200c` and `e9c621c`.

### 6.5 Not done / limits
Only three representative tests were examined with page snapshots; no test file, config or product file was edited; the BEN5K and OneDrive-dependent specs may need external fixtures (cause not examined).

---

## 7. Verification and limits of this response

| Item | State |
|---|---|
| Probe `secondary_base_provenance_probe.py` | executed against production services/resolver/view builders on in-memory registries; no file, network or shared state touched; output recorded |
| Existing probe and final oracle | re-run, unchanged results (`--check` OK) |
| Browser diagnostics | three single-test baseline runs for page snapshots; the baseline worktree stayed clean |
| Preserved originals | provenance re-established by transcript replay and git-blob equality (§5); the earlier "byte-identical" claim withdrawn |
| Amendment 7, matrix, S0 report | **not edited**; corrections and proposed wording are in this document |
| Production code, tests, APIs, UI | **unchanged**; no push, merge or deployment |
| Not verified | the owner's recordings (census counts unknown); whether any BEN5K upload failure is environmental; behaviour of the WUI pane-local PU controls against the refresh path |

**Stop for owner review.** S1 does not start.
