# PU-MIG S4 — Current: Recording Details' side and the CT decide the per-unit denominator

**Date:** 2026-11-26 · **Branch / worktree:** `feature/pu-mig-s1-pure-denominator-resolver`, `.local-data/pu-mig-s1`, on top of the
accepted S3 (`03e1b77`, `01b0364`) and its closeout (`1f82126`).
**Local only: not pushed, merged or deployed. Stopped for owner review (S5/S6 are not started).**
Authority: owner message "PU Migration — S3 Acceptance and S4 Authorisation" (2026-11-26).

## 1. Governing decisions and the approved S4 scope

Consulted: AGENTS.md and CLAUDE.md, DEC-218; DEC-209/210 (Current common base, explicit measurement and base sides, K-1…K-3),
DEC-212 (Voltage-only automatic PU; **raw Current stays in engineering units in the UI; existing Current PU services stay**), DEC-213,
DEC-215/216 (the shared VT/CT authority; Recording Details is the single side authority); `PER_UNIT_MEASUREMENT_MODEL`; the S0 final
reconciliation §4.3 (denominator), §7 (calculated lineage), §8 (manual Current bases, authoritative CT), §9 (S4 row); the accepted S1–S3
reports; `current_group_config`, `calculated_current_per_unit` and their tests.

Approved S4 scope (S0 §9.2): *Current — group Ibase `÷ CT` (`× CT` for a Secondary base on Primary samples), calculated Current
(K-1…K-3), Stage 5B result-owned bases.* Settled and **not reopened**: D-1 R+ (undeclared / non-strict keep today's numbers, labelled
Unverified — "R through S4" for Current), D-2 (stored base-side metadata kept through S4), D-5, D-6 (a conversion needs an authoritative
ratio, else the established refusal), D-8 (no API deprecation), N-2 (existing reason vocabulary), the DEC-212 eligibility (no new Current PU
eligibility: only resolutions that were already `configured` are re-expressed on the sample's side).

## 2. What changed

| Path | Change |
|---|---|
| Raw Current — the four source seams, provenance, coverage, compliance | `apply_source_reference` (`Current` branch) now uses the S2 gate: a strict sample side and an established base whose side is declared go through `side_denominator.resolve_side_denominator()` (Current quantity); the ratio is the CT (`ct_authority`) of the channel's own Current Measurement Group, read only for a conversion. Everything else keeps the historical gate, qualified (`unverified_historical` / `blocked`). |
| Base descriptors | `resolve_per_unit_for_group` (Current group) and `resolve_per_unit` (Source Default Current) hand on **what the base is** (`equipment_derived_primary` is Primary by meaning; `manual_direct` keeps its own declared side, possibly `unknown`, never assumed Primary). Base selection (`resolve_current_base_for_group`, `resolve_current_base_amps`) is untouched. |
| Calculated Current (unary, chains, addition/subtraction, Stage 5B Manual) | `resolve_calculated_current_per_unit(side_authority=…)`: leaves' strict sides (`evaluate_channel_side`) and the group CT. If every leaf is strict on one side, every base has a declared side, and (Secondary) there is a single CT authority (K-2), `place_current_base` places each contributor's base on that side and the **denominators** — not the bases (C-8/K-3) — are compared. Otherwise the historical code decides unchanged, comparing the *effective* strict side (DEC-216), and the result is qualified. |
| Stage 5B result-owned Manual base | descriptor `result_manual` with its own declared side, compared with the leaves' strict side; the candidate **proof** in `calculated_current_config_service` uses the same engine, so a rejected update stays atomic and an accepted one is exactly what the display will show. |
| Consumers | `calculated_channel_service` dispatch, `per_unit_provenance_service`, `calculated_current_config_service` and `PUT …/per-unit-config` pass the authority; the compliance series and coverage follow the seams. Without `side_authority` every path is exactly the historical gate. |

Production files: `domain/per_unit_reference.py`, `domain/per_unit.py`, `services/group_aware_per_unit.py`,
`services/per_unit_side_authority.py`, `services/calculated_current_per_unit.py`, `services/calculated_channel_service.py`,
`services/per_unit_provenance_service.py`, `services/calculated_current_config_service.py`, `api/v1/calculated_channels.py`.
`resolve_side_denominator()` keeps **one** production call site (`per_unit_reference`; the calculated K-3 comparison calls
`place_current_base`); no CT authority and no denominator arithmetic were added.

Refusal vocabulary (N-2, existing): a required CT that is not authoritative → `current_reference_side_incompatible` with the resolver's
`ct_authority_unavailable` and its detail (`not_configured`, `no_group`, …) in `side_refusal_*`; a non-representable denominator →
`effective_base_not_representable`; K-1 (different strict sides) and K-2 (Secondary across CT authorities) → the unchanged
`current_reference_side_incompatible` / `current_secondary_reference_unestablished`.

## 3. Policies preserved

ENG arithmetic before PU; DEC-212 (no change of which Current is PU-eligible; measured-unit and numerical-representability checks run after
the gate exactly as before); Current base-selection precedence (Stage 5B Manual > Automatic common base > legacy profile pointer, group
> Source Default); `legacy_manual` denominators (untouched); DEC-052/115/116 and the DEC-213 calibration gate (still first); historical
Unverified for undeclared bases and non-strict samples (never assumed Primary); known incompatibilities stay refusals; stored
`*_base_reference_side` fields read, never rewritten; no retired UI restored; RMS and power untouched; source samples never modified.

## 4. Verification

### 4.1 Tests added

* `tests/test_pu_mig_s4_oracle_integration.py` (the S1 independent oracle through the production Current gate): every Current row with a
  declared base side (equipment-derived Primary and manual-direct, both sides, grid + 132/138 kV case + extremes) matches the oracle's
  denominator (Decimal tolerance), reads the CT only for a conversion, and maps each refusal to the **existing** Current vocabulary with the
  resolver's code/detail carried additively; the undeclared-base rows keep today's number, labelled `unverified_historical` and read no CT; the
  non-strict and known-mismatch historical rows; the effective (Recording Details) side is the one compared; no authority = the historical gate.
* `tests/test_pu_mig_s4_current_side.py` (API-level, 46): raw Current Primary/Secondary samples, same-side and cross-side (`B`, `B / r`,
  `B × r`), manual and equipment-derived Ibase, manual (CT 1200 A : 5 A) and missing CT, undeclared base side, undeclared sample side and the
  engineer's Recording Details correction, Source Default (direct, no CT authority), measured-unit scaling (kA), overflow / non-representable,
  samples unchanged, coverage agreement, all four source seams plus provenance; calculated Current: unary ops, chain, addition (ENG first),
  Primary/Secondary physical equivalence, missing CT, non-strict leaf, K-1 (mixed strict sides), K-2 (Secondary across CT authorities, also with an
  engineer-established side), K-3 (equal / different bases across groups), conversion across two CT authorities, Source Default leaves;
  Stage 5B result Manual base (Primary on Secondary leaves converted, Secondary direct, **rejected updates atomic** for a missing CT, an
  undeclared side and a Source Default mismatch); the compliance series for a calculated Current member.
* `tests/test_pu_side_denominator.py`: the single-caller guard's importer allow-list gains `calculated_current_per_unit.py` (vocabulary only;
  the K-3 comparison calls `per_unit_reference.place_current_base`, so the resolver still has exactly one production call site).

### 4.2 Numerical parity and physical equivalence

Expected values are written from physics (`pu = sample / D`, `r = CT primary / CT secondary = 240`), never from application code. Primary
results are bit-identical to engineering ÷ Ibase (raw and calculated); a Primary and a Secondary recording of one physical condition give the
same per-unit values (1e-12) for raw and calculated channels; a Secondary-sample calculated sum is the ENG sum ÷ `B / r`; the equipment-derived
Ibase (100 MVA at 132 kV = 437.4 A) and manual Ibase behave identically; every conversion reproduces the S1 oracle's denominators.

### 4.3 Current base and eligibility

The 2 596 pre-existing Current / PU / calculated / overcurrent / compliance tests (all files matching `current|per_unit|pu_`) passed unchanged
except the guard allow-list; Stage 5B, PC-001, `legacy_manual`, calculated group-aware and DEC-052/116 contracts are unchanged. No new Current
PU eligibility: the gate only re-expresses a resolution that was already `configured` (and `configured` resolutions with an undeclared base or a
non-strict sample keep today's numbers).

### 4.4 Refusal and provenance

A required CT that is not authoritative: no number, ENG values kept, status `base_required`, `current_reference_side_incompatible`, provenance
`blocked` with `ct_authority_unavailable` and its detail (`not_configured`, `no_group`); a non-representable denominator:
`effective_base_not_representable` / `denominator_not_representable`. Provenance (`verification_state`, `side_conversion`, `ratio_*`,
`denominator_side`) is the S2/S3 shape, now filled for raw, calculated and result-Manual Current; coverage and the compliance series agree with
the display seams.

### 4.5 Mutation testing

24 mutants (`mutate_s4.py`, out of tree; the gate, the descriptors, the adapter, the K-1/K-2/K-3 guards, the refusal mapping, the Stage 5B
declared side, and every place the authority is threaded: dispatch, provenance, candidate proof): 5 survived the first run, and
four of them exposed missing tests (the effective-side report of the historical Current gate, a Source Default Secondary base, a calculated
undeclared base side) — added, then all caught. Two mutants survive **individually** (`calc_source_default_gets_a_group_ct`,
`calc_ratio_group_mismatch_ignored`): the `single_group is None` guard and the `context.group_ids != (single_group,)` guard enforce the same
rule, so either alone is an equivalent mutant (the same disposition as S3); removing **both** is caught by
`test_a_conversion_across_two_ct_authorities_is_refused_even_when_both_cts_agree`. 22 of 24 caught, 2 accepted as above.

### 4.6 Regression results (measured)

* Complete backend suite: **14 786 passed, 410 skipped, 0 failed** (52 min, measured on the final tree `7584363`).
* Targeted browser regressions (workers = 1, isolated ports; 24 specs: calculated channels, Current manual PU, current-common-base,
  source-default Current preview, overcurrent, group details, line-to-line, per-unit reference/voltage-reference safety, eligibility, numeric
  integrity, display synchronisation, atomic updates, power provenance, voltage-only PU display, BEN5K calculated PU gate, power calculator,
  event-reconstruction PU): **322 passed, 0 failed** (25.7 min). The full browser suite was not run (reserved for the integration gate); the
  6 CSV/Excel failures remain deferred and independent.

See §9 of `PU_MIG_S3_CALCULATED_VOLTAGE_SIDE_2026-11-26.md` (`compliance_series` coverage, mutant disposition, `manual_conflict_detected`).

## 6. Protected files and boundaries

`git diff 1f82126..HEAD`: no change to `side_denominator.py` (the S1 resolver), `per_unit_numerics.py`, `current_group_config.py` (base
selection), `reference_side.py`, any RMS or power code, waveform samples, the frontend, the CSV workflow or any API write contract or field; no
`*_base_reference_side` field changed or deprecated (D-8); nothing pushed, merged or deployed. Concurrent branches: `nf-3d`/`nf-3e`/`rms-r0`
touch none of the S4 production files except `calculated_channel_service.py` (S4: one line in the dispatch) and `api/v1/calculated_channels.py`
(S4: three lines), in different hunks from theirs; `wui-*` touch none. No other worktree was modified.

## 7. Remaining limitations and acceptance

* Calculated Current across **distinct CT authorities** (K-2) and every conversion that has no single owning Measurement Group stays
  unavailable (DEC-209/210 "shared physical reference", deferred); a Source Default base has no CT authority (no ratio is guessed).
* An undeclared (`unknown`) manual base side keeps today's number labelled Unverified (D-1 R); it is never assumed Primary and is the
  census / replacement-contract question (D-2) for after UAT-3, not decided here.
* `legacy_manual` calculated bases keep their historical denominator (labelled where the authority exists), as the S0 contract states.
* The `side_refusal_detail` of a K-2 / K-1 refusal is empty (those refusals are decided by the unchanged historical gate, whose reasons are the
  established ones).
* Raw Current remains engineering in the UI (DEC-212); the converted numbers are reachable through the API, calculated channels, the
  compliance series and the Stage 5B Manual base. The "no CT/VT scaling" badge text is still inaccurate for converted results (S5, untouched).
* The S3 `manual_conflict_detected` observation is unchanged and has no S4 dependency.

### S4 acceptance recommendation

Implemented strictly within the S0 §9 S4 scope and verified: complete backend 0 failures, targeted browser 0 failures, the S1 oracle
reproduced through the production Current gate, mutation testing closed (two equivalent redundant-guard singles accepted, the combined
mutation caught). **S4 is acceptable for owner review.** No owner decision is outstanding. S5/S6 are not started.
