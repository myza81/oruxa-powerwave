# PU-MIG-001 S0 — Decision Matrix

> **Governance correction (2026-11-24, owner review).** Two statements in section 2.2 (the `base x ratio` case for a secondary base on primary samples, and "the side of any contributing leaf not strict" as a blocking condition) were **not decisions**; they are struck through below. Secondary-base-to-Primary conversion is pending decision D-6; historical Unverified behaviour is unchanged and its policy is pending decision D-1. See [PU_MIG_S0_GOVERNANCE_CORRECTION_2026-11-24.md](PU_MIG_S0_GOVERNANCE_CORRECTION_2026-11-24.md) (ledger GC-1, GC-2). The rest of this document is preserved as delivered.

**Date:** 2026-11-24
**Branch:** `audit/pu-mig-001-s0-decision-matrix`, created from `2144893` (`feature/d5a-2b2c-1b-impedance-distance-unified-side`, the relevant D5A implementation) in its own worktree. Local only: **not pushed, merged or deployed.** The older voltage-reference branch and Codex's worktree were not modified.
**Type:** documentation and an independent oracle only. **No production code, test or API was changed.**
**Basis:** [PU_MIG_001_ASSESSMENT_2026-11-24.md](PU_MIG_001_ASSESSMENT_2026-11-24.md) (read-only assessment) and the owner's "Verified Decision Guidance" of 2026-11-24. This document governs where the two differ.
**Status:** OD-1 is confirmed in principle and recorded (§8, appended to DEC-216 as Amendment 7). OD-2, OD-3, OD-4 and the follow-on questions in §3 **remain open and need owner approval before S1**. S1-S6 are not authorised.

Labels: **[APPROVED]** already decided; **[SUPERSEDED]** narrowly replaced by OD-1; **[OPEN]** owner decision needed; **[PROPOSAL]** my recommendation; **[FACT]** verified in code at `2144893` or by executing the oracle.

---

## 1. Owner guidance, as recorded

| OD | Owner position | Effect on this document |
|---|---|---|
| OD-1 | **Confirmed in principle.** DEC-216 authorises selecting/deriving a compatible denominator from the effective measurement side and the authoritative CT/VT ratio. Record a narrow amendment to DEC-210/211. Samples, base meanings, calibration gates, L-L/L-N and numerical safeguards preserved. A transformer rating is never the equipment PU base. DEC-215 `auto_nominal` and its provenance preserved. | §2.2, §8 |
| OD-2 | **Policy open.** Historical Unknown-reference behaviour (DEC-210/211) is owner-approved. The *new strict resolver* never converts on an unknown or inferred-only side, but historical Unverified numerics are not removed without explicit authorisation. Show retain-vs-block impact **separately** for raw Voltage, raw Current, calculated Voltage, calculated Current. | §4 |
| OD-3 | Equipment-derived bases stay Primary. Manual/direct Current bases and result-owned Manual bases keep **independent** side semantics; never reinterpret Secondary as Primary; never assume Unknown is Primary; preserve metadata and workflows until a replacement contract is approved. | §5 |
| OD-4 | **Selective** calculated lineage: not a blanket block, not blanket inheritance; assess unary, line-to-line, multi-input, cross-group, cross-recording and nested individually. Preserve DEC-052/209/210/211/213 and all base-authority/calibration rules. **Preserve the legitimate Secondary Voltage denominator path using `secondary_voltage_ll_v`, including cases with no primary nominal where existing eligibility rules allow.** | §6 |

Two consequences I applied throughout: (1) I withdraw my earlier recommendation to *retire* the Current side declaration and to *treat inferred sides as unresolved-by-default*; both are now stated as options only. (2) The legacy `secondary_voltage_ll_v` path is **not** being replaced in S2; the new derived denominator is added beside it (§3 R-4).

---

## 2. Decision matrix

### 2.1 Already-approved rules (all preserved)

| # | Rule | Source | How the migration preserves it |
|---|---|---|---|
| A1 | Recording Details is the single source of the recorded side; one resolver (`resolve_effective_measurement_side`); precedence group override > recording correction > channel declaration > recording default (inferred, not `strict_usable`) > unresolved | DEC-216 + Amendments 1-4 | PU calls the resolver; no PU-private side logic |
| A2 | Voltage and Current may be on different sides; only disagreement *within* a quantity is a conflict | B2A-1 | Each quantity normalised independently (cases IM1/IM2) |
| A3 | A sibling-derived default is *inferred*; not strict-usable | B2A-2 | Strict resolver never converts on it (OD-2 text) |
| A4 | CT/VT ratio of the **consumed channel's own** Measurement Group; matching sides do not prove shared ratio authority; applied once, only when needed | DEC-216 item 8; Amendments 3-4 | Denominator uses that group's ratio; `conflict`/`no_group` block (B4, B5) |
| A5 | PU future behaviour: primary+primary direct; secondary + primary base -> secondary denominator from authoritative CT/VT; conversion needed but CT/VT unavailable -> block; a legitimately configured secondary base is never reinterpreted as primary; primary and secondary of one condition give equivalent PU | DEC-216 (PU paragraph) | The whole of S1-S4; property tested in oracle (`H`-loop, V1=V2, V3=V4) |
| A6 | Nominal L-L voltage, L-L/L-N distinction, derived `Ibase = S/(sqrt3 V_LL)`; raw samples never modified; no double conversion | DEC-216; DEC-050; MODEL §8/§10 | Base resolvers untouched; sqrt3 stays a *representation* factor |
| A7 | Current PU: calculated/result-specific only in the UI; CT primary is never an equipment Ibase; raw Current stays ENG in the UI | DEC-212 | Unchanged |
| A8 | Equipment-derived bases are Primary; manual/direct bases carry their own declared side; omitted side preserved only within the same method; explicit Unknown resets | DEC-209 | Unchanged (OD-3) |
| A9 | Known P/S mismatch blocks; historical Unknown stays computable and labelled **Unverified**; mixed known sides are not hidden by Unknown aggregation; cross-authority Automatic needs known compatible sides; distinct Secondary authorities need a shared reference (deferred) | DEC-209, DEC-210, DEC-211 | Preserved except the narrow supersession in §2.2 |
| A10 | Physical calibration authority gates PU first (`calibration_unavailable`); BEN5K defence-in-depth | DEC-213 | Gate order unchanged; regression test required (§7) |
| A11 | Nominal-derived VT (`auto_nominal`, 110 V default) is valid for every consumer; precedence manual > recording_metadata > auto_nominal > not_configured; provenance never relabelled | DEC-215 | Ratio read through the existing `resolve_transformer_context`; provenance shown |
| A12 | Calculated Voltage: DEC-052 (generic multi-input has no authoritative representation), DEC-115 (declared L-L), DEC-116 (undetermined -> no base) | DEC-052/115/116 | Checked **before** any side logic (§6) |
| A13 | Calculated Current: PC-001 common base (rtol 1e-12), Stage 5A cross-authority P/P, Stage 5B result Manual with its own independent side | DEC-209 | Unchanged except where §6 states |
| A14 | Backend is the sole conversion authority; no frontend normalisation; stale-response fences | DEC-210 | Refresh wiring only (S2) |

### 2.2 Narrowly superseded rules (OD-1)

Only these sentences are replaced, and only for the stated case. Everything else in DEC-210/211 stays.

| Superseded text | Source | Replaced by | Limits (what does **not** change) |
|---|---|---|---|
| "No CT/VT ratio scaling, side inference, sample reinterpretation, new conversion workflow or persistence." (the **ratio-scaling** part) | DEC-210 bullet 1 | When the consumed channel's effective side is **strict-usable** and differs from the side of the accepted base, the PU **denominator** may be derived as `base / ratio` (~~or `base x ratio` for a secondary base on primary samples~~ *[GC-1: not approved; pending D-6]*) using the authoritative ratio of the channel's own group. | Samples are never scaled; side is never inferred (from names, magnitude or ratio); no new persistence; a rating is never a base. |
| "Known P/S or S/P mismatch blocks PU in raw, group/default, legacy, calculated and nested paths." | DEC-210 bullet 2 | Mismatch **blocks only when the conversion is not authoritative** (ratio missing, invalid, untrusted, conflicting, no group~~; or the side of any contributing leaf not strict~~ *[GC-2: a non-strict side is historical Unverified today and is not changed; D-1 open]*). With an authoritative ratio it normalises. | Mixed known sides across the leaves of one calculated sum still block (CC2/CV3). Unknown and inferred sides never establish a conversion. |
| "No VT ratio scaling, side inference or sample reinterpretation." and "Known Primary/Secondary mismatch blocks Voltage PU (`voltage_reference_side_incompatible`)" | DEC-211 bullets 1-2 | Same as above for Voltage. | `unverified` for unknown sides is **not** touched here (§4). |

Not superseded (explicitly): "Unknown sides produce `unverified` without blocking conversion" (DEC-211) and the historical Unknown behaviour (DEC-210) - those wait on OD-2.

### 2.3 Remaining owner decisions

| ID | Question | Options | Recommendation [PROPOSAL] | Mode |
|---|---|---|---|---|
| **OD-2** | Retain or block **historical Unverified** numerics, per class (§4) | R retain unchanged / B block / M retain for single-authority automatic only | **R for S2-S4** (zero change), with a read-only census (§4.5) before any later B | COMPARISON, then UAT |
| **OD-3** | Replacement contract for manual-base side metadata | keep as-is / re-label only / replace | **Keep as-is through S4**; decide replacement after UAT-3; no S5 UI retirement for Current until approved | COMPARISON |
| **OD-4** | Calculated lineage per operation (§6) | table in §6 | **Approve §6 table**, S3 limited to rows marked "S3" | COMPARISON |
| R-4 | Precedence when both `secondary_voltage_ll_v` and nominal+ratio exist and disagree (D-PREC; the 4.35 % case, §7 VT1/VL3) | P1 legacy value wins, diagnostic shown / P2 nominal+ratio wins / P3 block on disagreement | **P1** (historical output preserved, which is what OD-4 asks), plus a non-blocking diagnostic when `|legacy/derived - 1| > 1e-6` and provenance "uses VT secondary winding rating" | ANALYSIS |
| R-5 | What activates the legacy `secondary_voltage_ll_v` path once `base_reference_side` is no longer *the* PU input | (i) unchanged: stored `base_reference_side == "secondary"`; (ii) effective side secondary + `secondary_voltage_ll_v` valid | **(i) through S4** (preserve metadata/workflow, OD-3); (ii) to be decided at S6 | ANALYSIS |
| R-6 | Strict **primary** sample against a **secondary-only** base (today: blocked as incompatible) | convert by authoritative VT ratio (VM1) / keep blocked | Convert only with a valid, trusted ratio; else block (A5 text) | ANALYSIS |
| R-7 | DEC-215 `auto_nominal` ratio for secondary PU: accept as-is and show provenance, or require recording_metadata/manual for PU | accept+show / require | **Accept+show** (DEC-215 already decided; only visibility is new) | UAT |
| R-8 | API deprecation of `*_base_reference_side` | none through S4 / deprecate | **None through S4** (OD-3); revisit S6 | ANALYSIS |
| R-9 | Refresh scope for Level 2 writes | per source / per group | Per source (existing function) | ANALYSIS |
| R-10 | Does the oracle graduate into `backend/tests` at S1 | yes / evidence only | Yes, still importing no application code | ANALYSIS |

---

## 3. Strict-resolver outcome table (base meaning x sample side)

The **strict** resolver is the new code. It never assumes a side. Unknown/inferred handling of the *historical* path is §4.

| Base meaning | Sample side strict-usable = primary | = secondary | Not strict (unknown / inferred / conflict) |
|---|---|---|---|
| Voltage nominal L-L (always **Primary**) | direct | `nominal / VT ratio` (ratio authoritative, else block) | strict resolver: no conversion; historical path per §4 |
| Derived / equipment-rating Ibase (always **Primary**) | direct | `Ibase / CT ratio` | same |
| Manual/direct Current base, declared **Primary** | direct | `base / CT ratio` | same |
| Manual/direct Current base, declared **Secondary** | `base x CT ratio` (ratio authoritative, else block) | direct, no ratio | same |
| Manual/direct Current base, declared **Unknown** | **never assumed Primary**: no conversion | no conversion | historical Unverified per §4 |
| Result-owned Manual base (Stage 5B), declared side as above | as the row above for its declared side | | strict already today (no Unknown) |
| Legacy Voltage `secondary_voltage_ll_v` (declared secondary) | `value x VT ratio` only with authoritative ratio (R-6), else block | direct (**existing numerics, preserved**) | historical per §4 |

---

## 4. OD-2 - retain versus block historical Unverified, per class

[FACT] "Unverified" today means: `configured` numerics, `reference_compatibility = unverified`, because the measurement side or the stored base side is `unknown` (`per_unit_reference.py`). Option **R** keeps those numbers byte-identical; option **B** turns them into `base_required` with ENG fallback.

Which recordings are affected [FACT/limit]: any channel whose effective side is **not** strict-usable in Recording Details - CSV/Excel (no P/S provider contract), BEN32/SubBen, COMTRADE without P/S flags or with partial/mixed declarations; and, **independently of the recording**, any group/profile whose *stored base side* is `unknown` (the default for every configuration saved before the field existed, and every manual Current base entered without a side). BEN5K legacy is already blocked by DEC-213 and is outside this question. I cannot count the owner's recordings; §4.5 proposes a read-only census.

### 4.1 Raw Voltage
| | Retain (R) | Block (B) |
|---|---|---|
| Strict side present (COMTRADE P/S, or engineer set Level 1/2) | New behaviour (§3); not part of this choice | same |
| Side not strict, base primary | Unchanged: `sample / primary base`, "Unverified reference". **Hazard V6**: a secondary sample reads 0.0004 pu | PU unavailable, reason `measurement_side_not_strict`; engineer must set Recording Details |
| Stored base side `unknown`, strict sample side | **Intentional change**: becomes compatible (the stored base side is no longer the proof) | same |
| Regression contracts touched | none beyond §2.2 | `test_per_unit_voltage_reference_safety.py` (4 assertions), `test_pu_ssot_001_calc_voltage_ref_side.py` (5), browser `per-unit-voltage-reference-safety`, `per-unit-reference-safety` (9), `pulu-auto-reference` (7) must be rewritten |
| User-visible | label stays; wording must stop saying "no CT/VT scaling" | whole CSV/Excel/BEN32 PU disappears until a side is set |

### 4.2 Raw Current
[FACT] The UI always shows raw source Current in ENG (DEC-212, frontend); raw-Current PU is reachable only through the backend API and any backend consumer that asks (Compliance series resolves PU for source channels through the same seam; whether a requirement requests Current PU was not verified).

| | Retain | Block |
|---|---|---|
| Group manual/direct Ibase typed **without a side** (the common legacy state) | unchanged Unverified numerics, independent of the sample side | all such raw-Current PU unavailable - the largest Current regression, because it does not depend on the recording at all |
| Equipment-derived Ibase (Primary) with non-strict sample side | unchanged | unavailable |
| UI impact | none (ENG) | none (ENG) |
| Tests | `test_per_unit_reference_safety.py`, `test_per_unit_reference_policy.py` unchanged | rewritten |

### 4.3 Calculated Voltage
[FACT] Today **every** calculated Voltage PU result is Unverified, because the calculated seam passes no measurement side (`calculated_channel_service.py:1784`). Executed: side `unknown` + primary base -> configured/unverified/0.0004 for a secondary-derived L-L (oracle CV2).

| | Retain | Block |
|---|---|---|
| Before lineage (S3 not done) | unchanged for all | **every calculated Voltage PU removed** on every recording - rejected by the owner (OD-4) in blanket form |
| After lineage (§6) with strict leaves | becomes compatible/converted (**intentional change**, CV2 -> CV1: 0.0004 -> 1.0) | same |
| After lineage with non-strict leaves | unchanged Unverified | unavailable |
| Tests | `test_pu_ssot_001_calc_voltage_ref_side.py` expectations about Unverified stay valid for non-strict leaves | rewritten |

### 4.4 Calculated Current
[FACT] Single-authority **Automatic** with an Unknown side retains numerics (unverified, non-strict); cross-authority Automatic, result Manual (5B) and `strict` paths already fail closed on Unknown; the `legacy_manual` profile-pointer branch retains the old denominator.

| | Retain | Block |
|---|---|---|
| Single-authority Automatic, Unknown side | unchanged | unavailable |
| Cross-authority Automatic / result Manual | already strict - no change | no change |
| `legacy_manual` branch (PU-CORE-001 H2, owner: retain, defer to Phase C) | unchanged | would contradict the H2 owner decision |
| Tests | PC-001/5A/5B suites unchanged | the single-authority Unknown fixtures rewritten |

### 4.5 Proposed read-only census (before any B decision) [PROPOSAL]
At S1/S2, a shadow harness evaluates every V/I channel of the owner's reference recordings (COMTRADE, CSV, BEN32) under *old gate* vs *strict resolver* and tabulates: strict-converted / strict-direct / historical-Unverified / blocked, per class. No behaviour changes. This turns §4 into counts the owner can decide on.

**Recommendation:** R for all four classes through S4. B is a separate, later, owner-authorised change.

---

## 5. OD-3 - manual-base metadata (preserved)

[FACT] Stored today and **kept unchanged through S4** (no schema, API or UI change): `CurrentBaseConfiguration.base_reference_side`, `PerUnitBaseProfile.current_base_reference_side` / `voltage_base_reference_side`, `VoltageBaseConfiguration.base_reference_side` + `secondary_voltage_ll_v`, `CalculatedCurrentConfiguration.base_reference_side`, with `candidate_base_side()` and `configured_base_side()` rules (equipment/derived -> Primary; manual/direct -> declared; omitted preserved only within the same method; explicit Unknown resets).

New behaviour only *reads* these: the strict resolver uses the declared side as the base's meaning (§3). It never writes them, never reinterprets Secondary as Primary and never treats Unknown as Primary. The UI controls stay until the owner approves a replacement contract (R-8); the auto-base writer (`auto_base_service.py:248-298`) is unchanged.

---

## 6. OD-4 - calculated-channel lineage, assessed per case [PROPOSAL, needs approval]

Existing rules run **first and unchanged**: DEC-213 calibration leaves -> calculated Current path -> DEC-116 undetermined-representation gate -> group-aware inheritance / DEC-049 profile. The lineage step is added only *after* a base has already been resolved, and only supplies the sample side/ratio for the denominator.

Definition: the **leaf set** is the transitive set of source channels feeding the result (as `calculated_current_per_unit.visit` already collects). A leaf supplies `(strict side, owning group, ratio authority)` through `evaluate_channel_side`.

| Case | Today (base) | Lineage rule | Result when rule holds | Otherwise | Slice |
|---|---|---|---|---|---|
| **Unary, single source leaf** (Reverse polarity, Absolute, RMS, Multiply by constant) | inherits the leaf's group/source verbatim | inherit the leaf's strict side and group ratio. Multiply-by-constant keeps the side (the constant is the engineer's scale; the result is whatever the engineer defined) | compatible / converted | non-strict leaf -> historical path (§4.3) | S3 |
| **Unary chain** (nested unary) | transitive verbatim | same leaf, through the chain | as above | as above | S3 |
| **Line-to-Line Voltage** (declared `line_to_line`, DEC-115) | unanimous group; declared representation drives the denominator | both phase leaves must have the **same strict side and the same owning group/ratio**; denominator = group L-L base `/ ratio` if secondary | CV1 = 1.0 | different sides -> block `calculated_leaf_sides_differ` (CV3); different ratios -> block (CV4); non-strict -> historical | S3 |
| **Generic Addition/Subtraction, Voltage** | DEC-052/116: no authoritative representation -> **no base at all** | not reached - stays `voltage_representation_undetermined` | unchanged | unchanged | none |
| **Addition/Subtraction, Current** | PC-001: live leaves, common base | same strict side on every leaf; same owning CT group (single authority) -> denominator `Ibase / CT` if secondary (CC1). Cross-authority Secondary stays deferred (DEC-209/210) | CC1 | mixed sides -> block (CC2) | S4 |
| **Cross-group (same recording)** | group-aware inheritance returns `None` unless unanimous; falls back to the Source Default of the single source | the Source Default has no ratio authority for a *secondary* sample (`ratio_status = no_group` for ungrouped / conflicting for split groups) -> **block** for secondary; primary unchanged | primary: unchanged | secondary: block `voltage_ratio_conflict` / `no_group` | S3 |
| **Cross-recording** | no common profile -> no base (`base_required`) | not reached - unchanged | unchanged | unchanged | none |
| **Nested multi-input** (a sum of a sum, L-L of unary results) | transitive | apply the leaf-set rule to the **transitive** leaves; any non-uniform leaf blocks | follows the row it reduces to | block | S3/S4 |
| **Stage 5B result Manual / explicit Unassigned** | independent | unchanged; the manual base keeps its declared side (§3) and is compared with the leaves' strict side | F1-F3 | declared Unknown -> F4 | S4 |
| **ROCOF / Power / Frequency** | not applicable | unchanged | | | none |

Secondary Voltage denominator path with `secondary_voltage_ll_v` (OD-4 explicit): remains valid for source **and** calculated Voltage (via the inherited group's config) where existing eligibility rules permit - including no primary nominal (VL1/VL2). It is the numerically existing path and is **not** altered by S3; see R-4/R-5 for precedence and activation.

---

## 7. Mathematical cases and independent expected values

Source of truth: `docs/project-memory/evidence/pu-mig-001-2026-11-24/pu_mig_oracle.py` (standard library, 60-digit `decimal`, imports nothing from the application) and its machine-readable `pu_mig_oracle_expected.json` (`--check` fails on drift). Every expected value below is printed there with 15 decimals. All pass the invariants: `pu_primary == pu_secondary` to 1e-50 for k in {0, 0.5, 0.87, 1, 1.1}; the 4.35 % error equals exactly `1/23`.

| ID | Case | Exact inputs | Expected |
|---|---|---|---|
| V1/V2 | Primary / Secondary L-N at nominal | V_LL 275 000 V; VT 275 000 V / 110 V (ratio 2500); samples `275000/sqrt3` V and `275000/sqrt3/2500` V | **1.000000** both; secondary denominator 63.508529611 V |
| V3/V4 | same at 0.87 | k = 0.87 | 0.870000 both |
| V5 | Secondary L-L | 110 V vs `275000/2500` | 1.000000 |
| V6 | **Hazard today** | secondary L-N, side unknown, primary denominator | **0.000400** (executed against the current gate: configured/unverified) |
| **VT1** | **Secondary L-L, nominal / ratio** | nominal L-L **132 000 V**; VT **138 000 V / 110 V** (ratio 138000/110 = 1254.5454...); system at nominal -> sample = 132000 x 110 / 138000 = **105.217391304 V**; denominator = 132000 / 1254.5454... = **105.217391304 V** | **1.000000** |
| **VT1x** | **Same sample / `vt_secondary_V` = 110 V** | denominator 110 V | **0.956521739** -> error **-0.043478261 = -(1 - 132/138) = -1/23 = -4.3478 % ("4.35 %")** |
| VL1/VL2 | Legacy secondary base, **no nominal** (preserved) | `secondary_voltage_ll_v` = 110 V; samples 110/sqrt3 V (L-N), 110 V (L-L) | 1.000000 each; L-N denominator 63.508529611 V |
| VL3 / VL3b | Both legacy secondary base and nominal/ratio, disagree | inputs of VT1 plus `secondary_voltage_ll_v` = 110 V | P1 legacy wins **0.956522**; P2 nominal/ratio wins **1.000000** |
| VM1 | Primary sample, secondary-only base, VT ratio valid | `secondary_voltage_ll_v` 110 V, ratio 2500, sample 275 000 V | 1.000000 (denominator 275 000 V) |
| CV1/CV2 | Calculated L-L = \|Va - Vb\| from secondary L-N legs | a = 275000/sqrt3/2500; \|Va - Vb\| = a sqrt3 = 110 V | CV1 1.000000; CV2 (side unknown) **0.000400** |
| CV3/CV4 | Legs of different side / different VT ratio | - | **block** |
| I1-I4 | Current, S = 1000 MVA, V_LL = 275 kV, CT 2000:1 -> Ibase 2099.455524 A | primary at Ibase; secondary at Ibase/2000 = 1.049728 A; secondary 1.0 A | 1.000000; 1.000000; **0.952628**; hazard I4 **0.000476** |
| IM1/IM2 | Mixed V/I sides | primary V + secondary I; secondary V + primary I (2099.6 A) | I: 0.952628; I: 1.000069 (the voltage side never changes Ibase) |
| F1 | Manual 2100 A **Primary**, secondary samples, CT 4000 | sample 0.525 A | 1.000000 |
| F2 | Manual 1.0 A **Secondary**, secondary samples | 0.5 A | 0.500000 (no ratio) |
| F3 | Manual 1.0 A **Secondary**, primary samples, CT 2000 | 1000 A | 0.500000 |
| F4 | Manual, declared **Unknown** | - | **block** (never assumed Primary) |
| F5 | Manual Secondary, primary samples, CT missing | - | **block** |
| CC1/CC2 | Calculated Current sum, same group CT 2000 / mixed sides | 0.5 A + 0.25 A | 0.714471 / **block** |
| B1-B8 | Strict-resolver blocks | ratio missing / invalid (0, negative, NaN, inf) / untrusted / conflicting / no group; side not strict; group mixed; CT missing | no numeric pu; `base_required` + reason (names are **proposals**) |

**The 4.35 % figure, exactly.** It is not a rounding artefact: a secondary L-L reading of a 132 kV system measured through a 138 kV / 110 V VT is `132000 x 110/138000 = 105.2174 V`. Using the VT's secondary *rating* (110 V) as the denominator yields `105.2174/110 = 0.9565`, i.e. an error of exactly `1 - 132/138 = 6/138 = 1/23`. Using the **nominal divided by the ratio** gives 1.0000. The discrepancy therefore equals `1 - V_nominal / V_VT,primary` and vanishes only when the VT primary equals the system nominal (as DEC-215's nominal-derived VT guarantees by construction). This is why R-4 exists: the legacy `secondary_voltage_ll_v` *is* a winding rating (`auto_base_evidence.py`: `secondary_ratio`), historically approved and preserved, but a derived denominator must never use a rating as a base.

---

## 8. Migration impacts and affected APIs

### 8.1 Code (all additive until S6)
| Area | Impact |
|---|---|
| `waveform_service._resolve_effective_per_unit` | step (4) gets the resolver's side and the group ratio; needs `measurement_side_registry` + transformer context threaded through 4 call sites and the 3 other source seams (Compliance series, provenance, coverage) |
| `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel` | lineage step (§6); stops passing no side (retires hazard CV2 for strict leaves) |
| `per_unit_provenance_service`, `per_unit_coverage_service`, `measurement_group_view_service` | must agree with the seams (DEC-210) - migrated in the same slice |
| `per_unit_reference.py` | strict resolver added beside the historical `apply_*_reference`; the historical functions remain for the Unverified path |
| `voltage_group_config.resolve_voltage_base_for_group`, `current_group_config`, `per_unit.resolve_per_unit`, base resolvers | **untouched** |
| Frontend | refresh after side writes (`wwRdSideEnqueue` -> `wwRefreshDisplayedChannelsForPerUnitChange`); badge/popover wording ("no CT/VT scaling" becomes false); provenance rows |

### 8.2 APIs
| Endpoint / schema | Change |
|---|---|
| `GET /sources/{id}/per-unit-resolution`, `GET /calculated-channels/{id}/per-unit-resolution` (`PerUnitResolutionOut`) | **Additive**: `effective_side`, `side_authority`, `ratio_applied`, `ratio_authority`, `denominator_side`. **Semantic change:** `measurement_side` currently echoes the raw declared flag; it would report the effective side (the raw declaration remains in the measurement-side API). Needs owner awareness |
| Waveform range / cursor-values / peak / annotation-anchor / calculated-channel range responses | `per_unit_reference_compatibility` keeps its three values; `compatible` may now mean "normalised by an authoritative ratio" |
| `GET /per-unit/sources/{id}/coverage` | channel counts per status will change (IC-1..IC-5) |
| Compliance endpoints | PU series values change for the same cases |
| `PUT .../voltage-config`, `.../current-config`, `PUT /per-unit/sources/{id}`, `PUT /calculated-channels/{id}/per-unit-config` | **No change through S4** (`base_reference_side`, `voltage_/current_base_reference_side` accepted and persisted exactly as today) |
| New read-only report (optional, S2) | PU analogue of `overcurrent-recorded-input`: what the PU will consume and why it is blocked |

### 8.3 Regression contracts to keep green
Backend: `test_per_unit_reference_safety`, `test_per_unit_reference_policy`, `test_per_unit_voltage_reference_safety`, `test_pu_ssot_001_calc_voltage_ref_side`, `test_reference_side_configuration`, `test_slice5d1_ps_integration`, `test_slice5d2_auto_base_service`, `test_slice5d3_auto_pu_display`, `test_calculated_current_manual_config`, `test_current_effective_base_*`, DEC-213 suites, PC-001/5A/5B. Browser: `per-unit-reference-safety`, `per-unit-voltage-reference-safety`, `pulu-auto-reference`, `current-common-base`, `calculated-current-manual-pu`, `event-reconstruction-per-unit`, `per-unit-display-synchronization`. A test may change **only** where a row of §2.2 or an owner-approved §4/§6 decision says so.

---

## 9. Cases where historical outputs will intentionally change

| ID | Case | Today | After | Cause |
|---|---|---|---|---|
| IC-1 | Raw Voltage, strict secondary side, stored base side Primary | blocked (`incompatible`) | converted pu (V2/V5) | §2.2 |
| IC-2 | Raw Voltage, strict secondary side, stored base side Unknown | **0.0004 Unverified** (V6) | 1.0 compatible | the stored base side is no longer the proof; real side supplied by Recording Details |
| IC-3 | Raw Voltage, strict primary side, stored base side Unknown | Unverified, same number | compatible, **same number** (bit-identical) | label only |
| IC-4 | Raw Voltage, strict primary side, stored base side Secondary + `secondary_voltage_ll_v` | blocked | converted via VT ratio if authoritative (VM1) else blocked (R-6) | §2.2 |
| IC-5 | Calculated Voltage with strict, uniform leaves | Unverified (CV2 0.0004 for secondary) | compatible (CV1 1.0) | §6 |
| IC-6 | Calculated Current, same-group Secondary, Primary-declared base | blocked or Unverified | converted (CC1) | §2.2 |
| IC-7 | An engineer correction at Level 1/2 | no effect on PU | changes PU | the motivating gap |
| IC-8 | UI wording and provenance rows | "no CT/VT scaling" | "normalised using VT/CT (auto-derived/manual/recording)" | accuracy |

**Unchanged by design:** Primary/Primary numbers (golden-file bit-identical); every historical Unverified number (pending OD-2); the legacy `secondary_voltage_ll_v` numerics (VL1/VL2/VL3 under P1); L-L/L-N denominators; DEC-213 blocks; DEC-212 raw-Current ENG; all stored configuration and write APIs.

---

## 10. Proposed slice impact of the guidance (replaces §9 of the assessment where different) [PROPOSAL]

| Slice | Scope | Gate |
|---|---|---|
| S0 | this document + Amendment 7 (OD-1) | **owner approves OD-2/3/4 and R-4..R-10** |
| S1 | pure `side_denominator` domain function + the oracle in `backend/tests`; census harness (§4.5, read-only); **no wiring** | independent oracles pass; golden P/P file |
| S2 | raw Voltage: strict resolver beside the historical gate, refresh wiring, provenance, all four seams together | UAT-1 |
| S3 | calculated Voltage per §6 | UAT-2 |
| S4 | Current (group Ibase `/CT`, calculated, 5B) with declared sides preserved | UAT-3 |
| S5 | UI wording/provenance only; **no control retirement** until OD-3 replacement contract is approved | UAT-4 |
| S6 | legacy retirement, only after separate approval | owner review |

Owner stop: nothing beyond S0 starts without approval of the §2.3 items.

---

## 11. Draft decision text (also appended to DECISIONS.md)

See DEC-216 **Amendment 7** (2026-11-24) in `DECISIONS.md`. It records OD-1 only; OD-2/3/4 and R-4..R-10 are explicitly *not* decided there.

## 12. Verification of this document
* Oracle run (`python -I pu_mig_oracle.py` and `--check`): all invariants hold; 38 cases emitted to the JSON.
* F-1/V6 was additionally executed against the existing `apply_voltage_reference` + `apply_per_unit_to_value` on a read-only export of `2144893` (configured/unverified/0.0004; known secondary -> `base_required`).
* No test suite or browser run was executed for this slice; no production file differs from `2144893`.
