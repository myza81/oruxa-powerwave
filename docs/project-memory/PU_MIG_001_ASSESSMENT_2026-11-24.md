# PU-MIG-001 — Per-Unit Measurement-Side Migration Assessment

**Date:** 2026-11-24
**Type:** READ-ONLY assessment. No production code, test, API or configuration was modified.
**Governance:** Not pushed, not merged, not deployed. The shared UAT branch, Codex's worktrees and the DEV
deployment were not touched. The PU migration has **not** been started. Stopped after the assessment.
**Audience:** the owner, for review and for the decisions in §10.

Labels follow the project convention: **[FACT]** verified from code, a document or an executed check;
**[PROPOSAL]** my recommendation, not a decision; **[OPEN]** needs an owner decision.

---

## 0. Baseline examined (read this first)

| Item | State |
|---|---|
| Local checkout | `feature/vlt-ref-001-voltage-reference-safety` @ `77fc74a`. **It predates D5A: it does not contain DEC-216 or the D5A-2B2A/2B2B/2B2C code.** |
| Code and docs examined | `feature/d5a-2b2c-1b-impedance-distance-unified-side` @ `2144893` (a strict superset of the local checkout: 81 commits ahead, 0 behind). Exported read-only with `git archive` to a scratch folder; Codex's worktree at `.local-data/d5a-2b2a` was not opened. |
| `git fetch origin` | Done (read-only). The local branch is 79 commits **ahead** of its `origin` counterpart, i.e. unpushed. Nothing was reset, stashed or cleaned. |
| Uncommitted files | 13 untracked files (BEN scaling docs/scripts, PU-SSOT-001 audit, `test-run-*.txt`). Preserved. This report and its evidence folder are two more untracked items. |
| Tests | **I ran no test suite.** Quoted suite totals come from the slice reports. I executed only two small read-only Python scripts (see §11). |

Line numbers below refer to the `2144893` tree, not to the local working tree.

---

## 1. Executive summary

1. **PU does not consume Recording Details today. [FACT]** The PU gate reads the raw COMTRADE flag
   `channel.measurement_side` (`waveform_service.py:226-228`) and the group's/profile's *separately stored*
   `base_reference_side`. An engineer's Level 1 (recording) or Level 2 (Measurement Group) correction has **no
   effect** on PU at all. Only Overcurrent, Impedance and Distance consume the unified resolver.
2. **Today PU can only block or assume; it never converts. [FACT]** A known Primary/Secondary mismatch blocks
   (DEC-210/211). An *unknown* side computes against the configured base and is labelled "Unverified
   reference". Executed against the current gate: a secondary L-N sample of 63.51 V, side unknown, primary
   base 158.77 kV → **`configured`, 0.0004 pu** (§5, §8 F-1).
3. **The legacy "Base Reference Side" can be retired, but not by deleting it first. [PROPOSAL]** It has three
   different jobs (§3): a *gate* (safe to replace), a *denominator selector* for Voltage (replace with a derived
   denominator) and a *meaning declaration for a hand-typed Current base* (must be reviewed, DEC-216 says so).
   It is **not** safely removable as one change.
4. **The mathematics is straightforward once one distinction is kept (§4):** physical bases (nominal L-L kV,
   equipment-derived Ibase) are *primary-system quantities*. The recorded side only decides which *denominator*
   the samples are divided by: `denominator_secondary = base_primary ÷ CT/VT ratio`. Samples are never scaled.
   Primary and secondary recordings of the same condition then give the **identical** pu (proved, §5-H).
5. **Four things need an owner decision before any code (§10):** (OD-1) DEC-216 narrowly supersedes the "no CT/VT
   scaling / known mismatch blocks" clauses of DEC-210/211; (OD-2) what PU does for an unresolved or merely
   inferred side; (OD-3) what happens to a hand-typed Current base's declared side; (OD-4) calculated channels
   — blanket block (like Overcurrent) would be a much larger regression for PU than for the protection pages.
6. **Recommended sequence (§9):** S0 decisions/doc amendments → S1 pure-domain denominator resolver with
   independent oracles (no wiring) → S2 raw Voltage path + refresh wiring → S3 calculated Voltage → S4 Current
   (group, calculated, manual) → S5 retire the UI controls → S6 legacy retirement. Owner UAT after S2, S3, S4, S5.

---

## 2. Verified data flow today

```text
COMTRADE/CSV/BEN import
  └─ AnalogChannel.measurement_side  (P/S flag → primary|secondary|unknown; CSV/BEN: unknown)   domain/channels.py:36
     AnalogChannel.calibration_authority (DEC-213; BEN5K etc.)                                   domain/channels.py:39
        │ physical a*x+b calibration happens at decode; samples = engineering values in the recorded unit
        ▼
Measurement Groups (suggested/confirmed/manual) + per-group config
  ├─ VoltageBaseConfiguration: nominal_voltage_ll_kv, reference_mode/override (L-L vs L-N),
  │     base_reference_side, secondary_voltage_ll_v, base_authority, VT (vt_primary_v/vt_secondary_v, vt_authority)
  └─ CurrentBaseConfiguration: method (equipment_rating | manual | none), equipment_rating_mva, manual_ibase_ka,
        base_reference_side, CT (ct_primary_a/ct_secondary_a), base_authority
  (+ Source Default PerUnitBaseProfile, DEC-049: voltage_base_value, current_base_mode, *_base_reference_side)
        │
        ▼  ONE dispatch seam for raw channels:  waveform_service._resolve_effective_per_unit()   :143
           (1) angle quantities → not_applicable                                                  :178
           (2) DEC-213 calibration gate → calibration_unavailable                                 :183
           (3) group-aware base (group_aware_per_unit) else Source Default (resolve_per_unit)     :200-212
           (4) apply_source_reference(resolution, type, channel.measurement_side, …)  ← THE SIDE GATE   :226
           (5) resolve_conversion_eligibility(unit + whole-channel representability)              :232
        ▼
     apply_per_unit_to_array/value:  pu = (value × unit_scale) / base_amount     (domain/per_unit.py)
```

* **Calculated channels** use a second seam, `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`
  (`:1670-1790`): calibration leaves → calculated **Current** via `calculated_current_per_unit.py` (PC-001/Stage 5A/5B)
  → DEC-116 representation gate → group-aware inheritance (`calculated_group_aware_per_unit.py`) else DEC-049 profile
  → `apply_source_reference` (`:1784`) **without a measurement side** (default `unknown`).
* **Consumers share those two seams** (waveform range/cursor/peak/annotation, Compliance series, Event Reconstruction,
  Phasor/V-I pages). Two *other* places duplicate the gate and must agree with them (DEC-210): `per_unit_provenance_service.py`
  (`:364, :375, :458, :472`) and `per_unit_coverage_service.py` (`:119, :130`).
* **No backend cache.** PU is re-resolved on every request; calculated-Current bases are "never persisted"
  (`calculated_current_per_unit.py` docstring). Registries are workspace-lifetime (in memory); no stored data needs
  migrating, only logic.
* **Frontend authority split.** DEC-212 is implemented in the frontend: raw source **Current** is always shown in ENG
  (`index.html:19523, 34585, 38876…`); PU is automatic for raw **Voltage** and available for **calculated** channels. The
  backend can still resolve raw-Current PU if asked, and Compliance/Event Reconstruction may ask.
* **The unified authority already exists and is stateless:** `resolve_effective_measurement_side()`
  (`measurement_side_service.py`) → precedence *group override > recording correction > channel declaration > recording
  default (inferred, not `strict_usable`) > unresolved*; `recorded_side_authority.evaluate_channel_side()` applies the single
  consumer policy (calculated → blocked; unresolved/inferred/group-conflict → blocked); `resolve_transformer_context()` and
  `independent_side_service` give the CT/VT of the *consumed channel's own group* (`manual > recording_metadata > auto_nominal`,
  DEC-215), with `ratio_status` ∈ {configured, no_group, not_configured, untrusted_authority, invalid, conflict}.

---

## 3. Inventory of the legacy PU Base Reference Side, and can it be removed?

"Legacy side" = `base_reference_side` (Voltage group, Current group), `voltage_base_reference_side` /
`current_base_reference_side` (Source Default), `CalculatedCurrentConfiguration.base_reference_side` (Stage 5B), and the
transient `PerUnitResolution.measurement_side/base_reference_side/reference_compatibility`.

| # | Where (backend, `2144893`) | Role | Safe to remove? |
|---|---|---|---|
| 1 | `per_unit_reference.py` `apply_current_reference` / `apply_voltage_reference` / `apply_source_reference` | **Gate**: classifies compatible/incompatible/unverified, blocks known mismatch | **Replace** with the side-aware denominator resolver (S1/S2). Keep the three-state vocabulary for the API/UI. |
| 2 | `voltage_group_config.py:330-349` | **Denominator selector.** `base_reference_side == "secondary"` switches the Voltage denominator to `secondary_voltage_ll_v` (÷√3 for L-N). Numerically load-bearing. | **Not yet.** Replace by `base_primary ÷ VT ratio` selected from the *effective* side. See OD-4 for the case with no nominal. |
| 3 | `auto_base_service.py:248-298` | **Writer.** Import-time evidence (COMTRADE P/S + winding ratios) writes `base_reference_side` and `secondary_voltage_ll_v` | Stop writing after S2 is accepted; remove in S6. The recording-side evidence it uses is already what the unified resolver reads. |
| 4 | `voltage_group_config_service.py`, `voltage_group_config_registry.py`, `current_group_config_service.py` (`:131-240`), `per_unit_service.py` (`:162-207`), `calculated_current_config_service.py` | Validated persistence/write paths; `candidate_base_side()` rules (equipment/derived ⇒ primary; manual/direct ⇒ declared) | Voltage and equipment/derived: removable. **Manual Current: review first (OD-3).** |
| 5 | `schemas/measurement_group.py`, `schemas/per_unit.py`, `api/v1/measurement_groups.py` (`:177,:196,:431,:525-542`), `api/v1/per_unit.py:137-138` | Public API fields (request + response) | Additive deprecation first (accepted-but-inert), delete in S6. |
| 6 | `calculated_current_per_unit.py` (`:88-170`), `calculated_group_aware_per_unit.py` | Calculated Current: per-leaf `configured_base_side()`, Stage 5A cross-authority, Stage 5B manual side | **Review with S4.** Hand-typed result base side is the same question as #4. |
| 7 | `per_unit_provenance_service.py`, `per_unit_coverage_service.py`, `measurement_group_view_service.py` | Read models showing measurement/base side and compatibility | Migrate **together** with #1 (must agree, DEC-210). |
| 8 | Frontend `index.html` (`:37152` Voltage "Base reference side" selector in Recording Details → Advanced; `:35871` `wwPerUnitBaseSideFieldHtml` in the calculated-Current editor; `:33622` provenance rows; `:33407` badge text "no CT/VT scaling is applied") | UI declaration + display + wording | S5. The badge/hint wording becomes false after S2 ("no CT/VT scaling") and must change with it. |
| 9 | Tests: 18 backend files reference the legacy fields (largest: `test_slice5d1_ps_integration` 63 hits, `test_per_unit_voltage_reference_safety` 33, `test_pu_ssot_001_calc_voltage_ref_side` 31, `test_reference_side_configuration` 18, `test_per_unit_reference_safety` 13); ≥20 browser specs (`per-unit-reference-safety`, `per-unit-voltage-reference-safety`, `current-common-base`, `calculated-current-manual-pu`, `event-reconstruction-per-unit`, `pulu-auto-reference`, the `rd1-*` family, …) | Existing regression contracts | They are the safety net: update only where a *policy* changes (OD-1), never delete to make a run green. |

**Answer.** The legacy side is removable **only in stages**: its gate and its Voltage denominator-selector roles are replaceable
by the unified side plus the authoritative ratio; its role as the *meaning of a hand-typed Current base* is a different concept
(what the number represents) that DEC-216 explicitly asks to review before any assumption. Removing it in one step would either
reinterpret a legitimately secondary base as primary (forbidden by DEC-216) or silently change numbers for saved manual bases.

---

## 4. Physical engineering bases versus the side of recorded samples

Two independent facts, never to be conflated:

| | What it says | Where it lives | Side-dependent? |
|---|---|---|---|
| **Physical base** | The system quantity the pu is relative to: nominal L-L kV; `Ibase = S / (√3·V_LL)`; a manual Ibase | Group config / Source Default | **No.** Equipment-derived and nominal bases are *primary-system* quantities (`configured_base_side()` already hard-codes this). L-N base = nominal L-L ÷ √3, unchanged. |
| **Sample side** | Whether the recorded numbers are primary-referred or secondary-referred | Recording Details (unified resolver) | n/a |
| **Denominator** | The number the samples are divided by | derived | `base_primary` if samples primary; `base_primary ÷ ratio` if secondary |

```text
Vbase_primary(L-L)  = nominal_voltage_ll_kv × 1000                          (L-N: ÷ √3)
Ibase_primary       = Sbase / (√3 × Vbase_primary_LL)                        (manual Ibase: as entered)
denominator(side)   = base_primary                    when side == primary
                    = base_primary ÷ ratio            when side == secondary     ratio = primary/secondary of the
                                                                                   consumed channel's OWN group (VT or CT)
pu = (sample × unit_scale) / denominator            samples never modified; nothing converted twice
```

**Where automatic denominator conversion is valid** (all must hold):
1. the consumed channel's effective side is `strict_usable` (own declaration or an engineer's Level 1/Level 2 setting; not inferred);
2. the base is an accepted primary physical base (existing gates: `base_authority` eligible, no `manual_conflict_detected`, group status/skip rules, DEC-213 calibration eligible);
3. for secondary samples, the ratio comes from the group that owns that channel, with `ratio_status == configured` (manual, recording_metadata, or DEC-215 `auto_nominal`);
4. unit normalisation and whole-channel representability pass (existing `resolve_conversion_eligibility`).

**Where it must block** (never guess, never fall back to the primary denominator):

| Situation | Result |
|---|---|
| Secondary samples, ratio missing / invalid / untrusted / conflicting / channel in no group | `base_required`, reason `…_ratio_unavailable` (specific message, link to the owning group) |
| Side conflict inside one group or across the leaves of a calculated channel | blocked (same policy as `evaluate_channel_side`) |
| A configured **secondary** base would need to be read as primary (or vice versa) and no valid ratio exists | blocked; a secondary base is never reinterpreted as primary |
| Group spans bays/recordings with different ratios (`ratio_status == conflict`) | blocked |
| Calculated channel whose leaves differ in side or owning ratio | blocked |
| Voltage Primary + Current Secondary (or the reverse) | **not** a conflict (B2A-1): each quantity is normalised independently |

**Where it must not apply a ratio:** primary samples (denominator is the base), secondary samples against a *secondary-declared
base* (direct, no ratio, F2 below), L-L versus L-N (the √3 is a *representation* factor, never a side factor), and anything already
converted once (no double conversion).

**Open sub-case (OD-2):** an unresolved or merely *inferred* side (CSV/BEN with no P/S evidence).

---

## 5. Mathematical examples (independent oracle)

Computed by `evidence/pu-mig-001-2026-11-24/pu_mig_oracle.py` — standard-library arithmetic, **no import from the application**.
System: 275 kV L-L, VT 275 kV/110 V (ratio 2500), S = 1000 MVA ⇒ Ibase = 2099.4555 A, CT 2000:1.

| ID | Case | Samples | Denominator | pu | Today |
|---|---|---|---|---|---|
| A1 | **Primary** L-N voltage | 158 771 V | 158 771 V | **1.000000** | ✓ same |
| A2 | **Secondary** L-N voltage | 63.5085 V | 158 771 / 2500 = 63.5085 V | **1.000000** | blocked if base side = Primary; correct only if legacy `secondary` + `secondary_voltage_ll_v` set |
| A3 | Secondary L-N, side *unknown*, primary base | 63.5085 V | 158 771 V | **0.000400** | `configured`, "Unverified reference" — **executed, §8 F-1** |
| A4 | Secondary L-L | 110 V | 275 000/2500 = 110 V | 1.000000 | as A2 |
| B1 | VT primary ≠ system nominal (132 kV system, VT 138 kV/110 V), secondary L-L at nominal | 105.2174 V | 132 000/1254.545 = 105.2174 V | **1.000000** | — |
| B1′ | same, *wrongly* using `vt_secondary` (110 V) as denominator | 105.2174 V | 110 V | 0.956522 (−4.35 %) | the failure the rule `base ÷ ratio` avoids |
| C1 | Primary current at Ibase | 2099.46 A | 2099.46 A | 1.000000 | ✓ (raw Current is ENG in the UI, DEC-212) |
| C2 | **Secondary** current at Ibase (CT 2000:1) | 1.049728 A | 2099.4555/2000 = 1.049728 A | **1.000000** | blocked/unverified |
| C3 | Secondary 1.0 A | 1.0 A | 1.049728 A | **0.952628** (= 1.0×2000/2099.4555) | vs primary base: 0.000476 (wrong) |
| D | **Mixed**: primary V + secondary I | V: 158.771 kV; I: 1.0 A | V: primary base; I: Ibase/CT | Vpu ≈ 1.0; Ipu = 0.952628 | Ibase is built from the *nominal (primary)* V, never from the voltage recording's side |
| E | **Mixed**: secondary V + primary I | V: 63.508 V; I: 2099.6 A | V: 63.5085 V; I: 2099.4555 A | ≈ 1.0; ≈ 1.0 | — |
| F1 | **Manual Ibase** 2.1 kA declared *Primary*, secondary current, CT 4000:1 | 0.525 A | 2100/4000 = 0.525 A | 1.000000 | — |
| F2 | Manual Ibase 1.0 A declared *Secondary*, secondary recording | 0.5 A | 1.0 A (direct, **no ratio**) | 0.5 | — |
| F3 | Manual Ibase 1.0 A declared *Secondary*, **primary** recording, CT 2000:1 | 1000 A | 1.0 × 2000 = 2000 A | 0.5 | — |
| F4 | Manual Ibase, side *unknown* | — | no sound denominator | block (or legacy "Unverified") | **OD-3** |
| G1 | **Calculated** `\|Va − Vb\|` from secondary L-N legs | 109.999 V | 275 000/2500 = 110 V | 0.999992 | with side `unknown`: 0.000400 |
| H | **Equivalence**: primary vs secondary of the same condition at k ∈ {0, 0.5, 0.87, 1.0, 1.1} | — | — | identical to ≤ 1e-15 | the DEC-216 acceptance property |

Cases with **missing / invalid / untrusted CT-VT** are the §4 block table; each is a one-line unit test (ratio `None`, `0`, `NaN`,
negative, `untrusted_authority`, `conflict`, channel in no group) expecting `base_required` + reason and **no** numeric pu.
**Manual Voltage base:** the stored value is nominal L-L kV (primary physical). A secondary recording is normalised by `value ÷ ratio`
(same as A2/A4); there is no "manual secondary Voltage base" in the primary model, only the legacy `secondary_voltage_ll_v` (OD-4).
**Calculated channels, inherited vs overridden bases:** unary ops (RMS, ±, |x|, ×k) and Line-to-Line Voltage inherit the single
side/group of their leaves (G1); Addition/Subtraction require identical side **and** owning ratio on every leaf; a Stage 5B result
Manual base is an *override of the base value only* (F1–F3 apply to its leaves' side), never of the samples or the leaves' groups.

---

## 6. Preserving DEC-210 / 211 / 213 / 215 and the calibration safeguards

| Decision | What must survive | How the proposal keeps it |
|---|---|---|
| **DEC-213** calibration authority | `calibration_unavailable` precedes any base/side logic | Untouched: step (2) of the seam stays before the new side step. Add a regression test that an Unverified/Invalid leaf still wins over a perfectly valid side+ratio. |
| **DEC-215** nominal-derived VT | `auto_nominal` valid, provenance never relabelled | Used as a ratio source through the existing `resolve_transformer_context`; PU reports `auto_nominal` provenance. See OD-5 (a *tautology* risk). |
| **DEC-211 / DEC-210** | A silently wrong pu must be impossible; Unknown stays *Unverified*, not blocked; known conflicts not hidden by aggregation; cross-authority Secondary deferred | The proposal removes the silently-wrong outcomes by *deriving* the correct denominator, and keeps blocking wherever conversion isn't provably valid. **But two clauses change** — see OD-1. |
| DEC-050 / MODEL §11 | "CT/VT scaling ≠ PU normalisation; do not merge it into PU" | Reconciled: **samples are never scaled**; only the *denominator* is derived (`base ÷ ratio`), which is algebraically `(sample·ratio)/base` without ever producing a scaled sample. MODEL §11/§27 need a short amendment (S0). |
| DEC-212 | Raw Current stays ENG; Current PU via Calculated Channels | Unchanged. S4 is needed only for calculated Current and the backend's own raw-Current path. |
| DEC-209 Stage 5A/5B, PC-001 | Common-base rtol 1e-12; distinct Secondary authorities need a shared reference; result Manual independent | Keep. Mixed P/S leaves in one sum stay blocked (adding secondary amps to primary amps is arithmetically meaningless). Same-group Secondary/Secondary becomes valid with a CT denominator. |
| VLT-REF-001, DEC-116/115 | L-L vs L-N representation, no √3 on samples | The √3 stays a *base representation* factor; the side factor is a separate multiplier of the denominator. |

---

## 7. Invalidation and refresh when Recording Details changes

* **Backend [FACT]:** correct by construction. PU is resolved per request from live registries; no PU result, base or side is
  cached or persisted; the unified resolver is stateless. A Level 1/Level 2/ratio change reaches the *next* request with no
  cascade needed, and physical samples are never touched.
* **Frontend [FACT]:** a **gap**. Voltage/Current config and VT/CT writes call
  `wwRefreshDisplayedChannelsForPerUnitChange(sourceId)` (e.g. `index.html:37294…37617`), which retires presentation arrays,
  bumps generation fences and refetches waveform, cursor and annotation/peak values. The **measurement-side writes do not**:
  `wwRdSideEnqueue` → `wwRdSideLoad` re-reads only the side overview (`:36533-36568`, `:36494-36518`). Harmless today (PU ignores the side),
  **stale-PU after the migration** unless wired.
* **Proposal:** after a settled side write call the same refresh for the affected source (Level 1 ⇒ the whole source; Level 2 ⇒
  that source, only displayed channels of that group matter but the existing per-source refresh is correct and cheap). No new
  polling, no frontend normalisation (DEC-210: backend is the sole conversion authority). Verify Event Reconstruction
  (`wwEr…`) and Compliance/phasor surfaces re-fetch on the same trigger (`event-reconstruction-per-unit.spec.js`,
  `per-unit-display-synchronization.spec.js` are the existing guards to extend).
* **Required property tests:** (a) flip Level 1 Secondary→Primary with identical samples: displayed pu changes to the expected value
  and the array hash of the *physical* samples is unchanged; (b) a stale response issued before the flip never repaints;
  (c) a Level 2 override survives a Level 1 change and keeps its own pu; (d) editing CT/VT ratio updates secondary pu only.

---

## 8. Findings outside the agreed scope (reported, not acted on)

**F-1 — Calculated Voltage PU assumes the primary denominator for samples of unknown side.** *Issue:* the calculated seam calls
`apply_source_reference` without a measurement side. *Evidence:* `calculated_channel_service.py:1784`; executing the current
`apply_voltage_reference("unknown", "primary")` on a 63.5085 V sample against a 158 771 V base returns `status=configured`,
`reference_compatibility=unverified`, **0.0004 pu**; the same sample with a known `secondary` side is `base_required`. *Proposed
solution:* resolved by S3 (lineage-lite side). *Benefits:* removes a silent ×2500 error on L-L calculated voltages from secondary
recordings. *Risks:* behaviour change for calculated channels that "worked" with the unverified label. *Expected impact:* limited to
secondary/mixed recordings. **No change made; owner approval needed.**

**F-2 — Engineer side corrections do not affect PU** (§1.1) — the motivating gap, not a defect to patch separately.

**F-3 — Side writes do not trigger the PU refresh** (§7).

**F-4 — The gate is implemented in four places** (waveform seam, calculated seam, provenance, coverage); a partial migration would
make badges, popovers and values disagree. S2 must move all four atomically.

**F-5 — Policy text conflict:** DEC-210/211 ("no CT/VT scaling", "known mismatch blocks") and MODEL §11/§27 versus DEC-216's PU
clause. Per project rules I do not choose silently: **OD-1**.

**F-6 — `secondary_voltage_ll_v` duplicates VT-secondary information** and is written from import evidence (`auto_base_service.py:248`)
independently of `vt_secondary_v`; the two can disagree (§5 B1 shows a 4.35 % consequence if the wrong one is used). **OD-4**.

---

## 9. Proposed smallest safe slices (each independently reviewable; none authorised yet)

Principle: the base resolvers (`resolve_voltage_base_for_group`, `resolve_current_base_for_group`, derived Ibase) stay **untouched**.
The new logic is one pure function applied *after* base selection, exactly where `apply_source_reference` sits, so DEC-213/215,
group status gates and numerics for Primary/Primary stay bit-identical.

| Slice | Scope | Independent oracle / regression guard | Owner checkpoint |
|---|---|---|---|
| **S0** Decisions + docs (no code) | Record OD-1…OD-8; amend MODEL §11/§27 and a DEC-216 amendment; no behaviour change | n/a | **Approve OD-1…OD-4** |
| **S1** Pure denominator resolver | New `domain/side_denominator.py` (inputs: base, base side, sample side, ratio status/value → denominator \| block-reason \| unverified). **No wiring** | Table tests = §5 A–H (oracle script is the source of truth, reimplemented without app imports); property: pu_primary ≡ pu_secondary (1e-12); ratio invalid matrix; subnormal/overflow path (`_scaled_ratio`); no double application; **golden file of today's Primary/Primary outputs must stay bit-identical** | none (internal) |
| **S2** Raw Voltage path | Thread `SideAuthority`/transformer registries into `_resolve_effective_per_unit`; use the resolver's side instead of `channel.measurement_side`; Voltage groups **and** Source Default (ungrouped channels follow Level 1); additive provenance fields (`effective_side`, `side_authority`, `ratio_applied`, `denominator_side`); migrate provenance + coverage + Compliance call sites **in the same slice**; wire the refresh hook (§7); legacy fields still stored but **ignored** for gating; shadow comparison test asserts old vs new agree on every existing fixture except the intended differences (A2/A3) | §5 A/B/G oracles through the **public API**; DEC-213 precedence test; Compliance and waveform produce the same pu for one channel; refresh/stale-fence browser tests | **UAT-1 (DEV):** owner's primary and secondary recordings of one event → same pu; flip Level 1/Level 2 and see PU follow; a CSV/BEN recording (no P/S) behaves per OD-2; VT missing → clear block message |
| **S3** Calculated Voltage | Lineage-lite side/ratio for calculated Voltage (unary + Line-to-Line inherit; Add/Sub need identical side and owning ratio); retire F-1 | G1 oracle; mixed-side leaves blocked; DEC-115/116 representation tests unchanged | **UAT-2:** an L-L calculated channel on a secondary recording |
| **S4** Current | Group Ibase denominators (`Ibase ÷ CT`), calculated Current (PC-001 same-group Secondary), Stage 5B result Manual per OD-3, F1–F4 | C/D/E/F oracles; PC-001/5A/5B regression suites unchanged; Stage 5B manual-base tests | **UAT-3:** calculated Current on secondary + manual base |
| **S5** UI retirement | Remove the Voltage "Base reference side" control and (per OD-3) the calculated-Current side field; replace the badge/hint copy; show effective side, ratio provenance and denominator read-only in the PU info popover; electrical-notation rules (DEC-117/118) and `expectTrueSubscripts` for any new symbols | Update only the policy-bearing browser specs listed in §3 #9; text-spacing guard | **UAT-4:** Recording Details → PU end-to-end walkthrough |
| **S6** Legacy retirement | Remove `base_reference_side`/`secondary_voltage_ll_v` writers, schema fields (after a deprecation window), `apply_*_reference` side parameters, dead tests; couples with PU-CORE-001 Phase C (Source Default, H2) | Full backend + browser suites; API schema diff reviewed | Owner review before merge |

Verification baseline to beat at each slice: the last recorded full backend run on this line is 13,448 passed / 405 skipped /
0 failed (D5A-2B2A report); later slices recorded higher totals in their own reports. A slice is not done until the **same suite
set passes with zero new failures and every changed expectation is traceable to an approved OD**.

---

## 10. Unresolved engineering decisions (owner)

| ID | Decision needed | Options | Recommendation | Mode |
|---|---|---|---|---|
| **OD-1** | **Supersession scope.** The task says preserve DEC-210/211; DEC-216's PU clause conflicts with their "no CT/VT scaling" and "known mismatch blocks" sentences. | (a) DEC-216 supersedes only those sub-clauses, and only where a valid authoritative ratio exists; block everywhere else. (b) Keep DEC-210/211 as written and defer conversion. | **(a).** The *safety intent* (no silently wrong pu) is preserved and strengthened; samples are never scaled. Needs explicit confirmation because it changes two approved decisions. | ANALYSIS |
| **OD-2** | **Unresolved or inferred side** for PU (CSV/BEN, partial evidence). | (a) Keep the DEC-210/211 behaviour: compute against the primary base, label "Unverified reference", with a pointer to Recording Details. (b) Block (DEC-216 item 7, as Overcurrent/Impedance do). | **(a) for S2**, because (b) removes PU from every CSV/BEN recording the day it ships; revisit (b) after UAT-1. Inferred ⇒ treated as unresolved (never used to convert). Hazard A3 stays visible but labelled. | COMPARISON → UAT |
| **OD-3** | **Hand-typed Current base side** (group manual Ibase, Stage 5B result base). | (A) Keep a Primary/Secondary declaration *as the meaning of the typed number* (retire it only for Voltage and equipment-derived); legacy `unknown` stays Unverified/strict as today. (B) Retire; treat every manual Ibase as primary — **reinterprets legitimately secondary bases (forbidden by DEC-216)**. (C) Retire; ask engineers to re-enter. | **(A)**, relabelled "this base is a Primary/Secondary current" (task language, not "reference side"). | COMPARISON |
| **OD-4** | **Calculated channels in the PU slices** and **Voltage with no nominal but a secondary base** (`secondary_voltage_ll_v`). | Calculated: (A) lineage-lite as §9 S3; (B) block all calculated V/I like the protection pages. Secondary base: (A) keep as a *direct* secondary base usable only when the effective side is secondary, never converted; (B) require a nominal. | **Calculated (A):** (B) would break L-L and RMS PU for every secondary recording, a far bigger regression than for Overcurrent. **Secondary base (A)**, with a diagnostic when it disagrees with `nominal ÷ ratio` by more than 1e-6 relative. | COMPARISON |
| OD-5 | A nominal-derived VT (DEC-215, 110 V default) makes secondary pu *tautological*: `denominator = nominal ÷ (nominal×1000/110) = 110 V`. If the true secondary rating is 100 V the pu is off by 10 %. | Accept per DEC-215 and show provenance ("VT auto-derived, 110 V") in the PU popover; or require `recording_metadata`/`manual` VT for PU conversions | Accept + show provenance; stored `recording_metadata`/`manual` VT already outranks it. | UAT |
| OD-6 | Deprecation of the API fields. | Accepted-but-inert then removed (S6) / rejected immediately | Accepted-but-inert, documented. | ANALYSIS |
| OD-7 | Refresh trigger scope for Level 2 writes. | per source (existing function) / per group | Per source; simplest correct. | ANALYSIS |
| OD-8 | Whether the independent oracle script graduates into the repository tests (`backend/tests`) at S1. | yes / keep as evidence only | Yes; it must not import application code. | ANALYSIS |

---

## 11. Method and limits

* Read: AGENTS.md, CLAUDE.md, project-memory README, DEC-050/209/210/211/212/213/214/215/216 (+ Amendments 1–6), MODEL §8/§11/§27 and
  headings, HANDOFF head, D5A-2B2A/2B2B notes, PU-SSOT-001 audit, PU-CORE-001 report; and the PU/measurement-side modules listed in §2/§3
  at `2144893`.
* Executed (read-only, against the exported copy; nothing in the repository was changed):
  `evidence/pu-mig-001-2026-11-24/pu_mig_oracle.py` (§5) and a four-line call of the existing `apply_voltage_reference` +
  `apply_per_unit_to_value` (F-1). Reproduce F-1 with: sample 63.50852961 V, base 158 771 V, sides (`unknown`,`primary`) ⇒ configured/unverified/0.0004.
* Not done: no test suite run, no browser run, no DEV inspection, no inspection of Codex's worktree, no `powerwave` desktop comparison
  (not required for this assessment). Frontend line numbers come from the `2144893` tree.
* Not verified: behaviour of the Event Reconstruction and phasor pages when a side write occurs (inferred from the shared seams; §7 names
  the specs to extend).
