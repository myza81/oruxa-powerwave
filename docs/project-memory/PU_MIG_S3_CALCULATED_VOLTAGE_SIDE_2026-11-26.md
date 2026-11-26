# PU-MIG S3 — calculated Voltage: the side of a result is the side of its leaves

**Date:** 2026-11-26 · **Branch / worktree:** `feature/pu-mig-s1-pure-denominator-resolver`, `.local-data/pu-mig-s1`, on top of the
accepted S2 (`8ef6d5c`, `1dea5e4`, `8ebe1fd`) and the DEC renumbering commit `58ef97b`.
**Local only: not pushed, merged or deployed. Stopped for owner review (S4/S5/S6 are not started).**
Authority: owner message "PU Migration — S2 Final Acceptance and S3 Authorisation" (2026-11-26).

## 1. Scope actually implemented

S0 final reconciliation §7 (calculated lineage table) and §9 row S3: *calculated Voltage per-unit through the shared side-denominator
authority.* The Voltage operation rows of §7 were taken as the established S3 scope:

| Calculated Voltage result | Side taken from | Outcome |
|---|---|---|
| unary (reverse polarity, absolute value, multiply constant, RMS) and chains of them | the transitive source leaf | the leaf's side, exactly as a raw channel (S2) |
| line-to-line (multi-input, declared L-L representation, DEC-115/116) | its leaves, which must all agree | the common side |
| leaves with any non-strict side (undeclared, inferred, group conflict, calculated) | — | historical number kept, labelled `unverified_historical` (D-1 R+) |
| strict leaves on different sides | — | refused, `voltage_mixed_side` (existing vocabulary, N-2), no number, no ratio read |
| generic addition / subtraction | — | unchanged: no base (DEC-052) |
| base inherited from a Measurement Group | that group's VT (shared authority, DEC-215) | convert, or block without an authoritative ratio (D-6) |
| base is a Source Default (no group, or leaves in several groups) | — | no ratio authority: a required conversion is blocked, `vt_authority_unavailable` / `no_group` (S0 §7) |

Not in S3: Current (S4, DEC-212: raw Current stays engineering), power, RMS arithmetic, UI wording and the "no CT/VT scaling" badge (S5),
Base Reference Side controls (S6), any API deprecation.

## 2. Integration points

`side_denominator.resolve_side_denominator()` still has **one** call site (`per_unit_reference.apply_strict_voltage_reference`); no
denominator arithmetic and no separate CT/VT authority were added. Separation of concerns:

| Concern | Owner |
|---|---|
| ENG arithmetic (before PU) | unchanged calculated-channel evaluation |
| base selection, Measurement Group inheritance, effective-base compatibility | unchanged (`resolve_calculated_group_aware_per_unit`, `resolve_per_unit`) |
| measurement-side authority | Recording Details via `recorded_side_authority.evaluate_channel_side` (per leaf) |
| lineage rule (which side the result has) | new pure `domain/calculated_side_lineage.py` — no registry, no base, no ratio, no arithmetic |
| ratio authority | `resolve_transformer_context` for the group whose base was inherited (`per_unit_side_authority.calculated_voltage_side_inputs`) |
| denominator conversion | the S1 resolver, reached only through the S2 gate |
| eligibility / representability | existing `resolve_conversion_eligibility`, applied **after** the gate (so the converted denominator is the one checked) |

Production files (6 modified, 1 new): `domain/calculated_side_lineage.py` (new); `domain/per_unit_reference.py` (`RawVoltageSideInputs.refusal`
and the lineage-refusal block); `services/per_unit_side_authority.py` (`collect_source_leaf_refs`, `calculated_voltage_side_inputs`,
`apply_calculated_source_reference`); `services/calculated_channel_service.py` (`side_authority` threaded through the one dispatch and the
four public functions); `api/v1/calculated_channels.py` (`get_recorded_authority` and the five routes); `services/per_unit_provenance_service.py`
(gate then eligibility, effective side reported); `services/compliance_series.py` (passes the authority). Without `side_authority` every
path is exactly the historical gate.

## 3. Policies preserved

Arithmetic in ENG before PU; effective-base compatibility (numerical equality of bases never establishes compatibility); Measurement
Group inheritance and Source Default fallback; DEC-052 multi-input restriction; DEC-212 Current restrictions (untouched); power and RMS
semantics (untouched); DEC-116 undetermined-representation check; DEC-213 calibration gate (still first); historical Unverified;
rejection and numerical safety (`denominator_not_representable`, `per_unit_result_not_representable`). Source samples are never modified.
Verification state and provenance fields are the S2 ones (`verified_direct`, `verified_converted`, `unverified_historical`, `blocked`;
`side_refusal_reason/detail`); `measurement_side` reports the effective lineage side when Recording Details established it.

## 4. Verification

### 4.1 Tests added (44 backend)

* `tests/test_pu_mig_s3_calculated_side_lineage.py` (15): the pure rule — agreeing leaves, mixed sides in any order, non-strict leaf beside
  strict ones, deterministic problem, no leaves, authority labelling.
* `tests/test_pu_mig_s3_calculated_voltage_side.py` (29), through the real API and every calculated seam (range, cursor, peaks, anchor,
  provenance): Primary / Secondary samples; same-side and cross-side; manual and `auto_nominal` VT; unary ops and a three-deep chain; RMS;
  line-to-line on Primary, Secondary and recording-declared sides (KPDN1 multibay fixture); historical Unverified and the engineer's
  Recording Details correction; DEC-052 add/subtract; Source Default Primary / Secondary; leaves in two groups; mixed sides (gate level);
  missing ratio; overflow, unrepresentable, subnormal; leaf samples unchanged.

### 4.2 Numerical parity and physical equivalence

Expected values are written from physics (`pu = sample / D`, `D = B·ρ`, `/ratio` or `·ratio` across sides, L-L ρ = 1), never from
application code. Primary-side results are bit-identical to engineering ÷ denominator; Primary and Secondary recordings of one physical
condition give the same per-unit values (1e-12); L-L outputs equal the independent phase differences ÷ 275 kV, and on Secondary samples
÷ 0.110 kV (275 kV × 110 V / 275 000 V). An intentional-change update of an existing test was needed in one place only (§5).

### 4.3 Mutation testing

17 mutants (`mutate_s3.py`, five route mutants in `mutate_s3_routes.py`; out of tree): 14 + 5 caught. Three single-guard mutants of the
ratio group check (`group_id is None` guard alone, mismatch guard alone, `group_id=profile_id`) survive **individually** because the two
guards defend each other (equivalent); removing both is caught by `test_leaves_in_two_groups_fall_back_to_the_source_default…`.

### 4.4 Regression results

* Complete backend suite: 14 516 passed, 410 skipped, 1 failed (the S2 single-caller guard needed the new module on its importer
  allow-list — it only imports the `SampleSide` vocabulary and never calls the resolver); fixed, `test_pu_side_denominator.py` 585 passed.
* Targeted browser regressions (calculated channels, per-unit display/eligibility/reference safety, L-L, power provenance): see §8 (164 passed, 0 failed).
* The 6 CSV/Excel failures remain deferred and independent. No full browser suite (reserved for the integration gate).

## 5. Existing contracts updated

Only `tests/test_pu_side_denominator.py::S2_IMPORTERS` (above). No calculated or power assertion was weakened; the 148 existing
calculated-PU tests and the L-L, DEC-052 and calculated group-aware suites pass unchanged.

## 6. Protected files and boundaries

No change to `side_denominator.py`, `per_unit_numerics.py`, RMS or power code, any Current base module, waveform samples, the frontend,
the CSV workflow, or any API write contract. Concurrent branches: `nf-3d`/`nf-3e` change `calculated_channel_service.py` and
`api/v1/calculated_channels.py` in different hunks (imports, `check_rms_eligibility`, `create_calculated_channel`, L-L routes); the only
adjacency is where both add a dependency helper near `get_current_group_config_registry` — a trivial textual conflict to resolve at
integration. `rms-r0` touches `calculated_channel_service.py` imports and `check_rms_eligibility` only. WUI branches touch none of the
changed files. No other worktree was modified.

## 7. Remaining limitations

* The mixed-side refusal is verified at the gate (no public operation combines two recordings of different sides with a base: DEC-052
  blocks generic add/subtract first, and L-L is built from one engineering context).
* `compliance_series` is wired to pass the authority but has no S3-specific test beyond the existing compliance suite passing.
* The "no CT/VT scaling" badge text is inaccurate for converted results (S5). Calculated Current (S4) still uses its own path.
* A PUT of a Voltage group configuration through the public API with default reference fields can mark an L-L context
  `manual_conflict_detected` (existing behaviour, observed while building fixtures; not changed here).

## 8. Browser results and acceptance

Targeted browser regressions (workers=1, isolated ports): 17 specs — calculated-channel (null handling, power, power label, presentation,
preview, ROCOF), calculated-current manual PU, line-to-line voltage, per-unit reference safety / voltage reference safety / eligibility /
numeric integrity / display synchronisation / atomic updates, power provenance, voltage-only PU display, BEN5K calculated-channel PU gate:
**164 passed, 0 failed** (6.8 min). No full browser suite was run.

**S3 acceptance recommendation:** implemented as specified and verified; backend 0 unexplained failures (one intentional guard allow-list
update), browser 0 failures, mutation testing clean apart from equivalent redundant-guard mutants. Acceptable for owner review. No owner
decision is outstanding from S3. S4 is not started.

## 9. S3 closeout (owner message "PU Migration — S3 Acceptance and S4 Authorisation", 2026-11-26)

**S3 accepted**; commits `03e1b77` and `01b0364` preserved; the importer allow-list correction accepted.

* **`compliance_series` coverage.** `tests/test_pu_mig_s3_compliance_series.py` (5 tests) builds `Registries` exactly as `api/v1/compliance.py`
  does and calls `load_series(ref, "pu")` for calculated Voltage members: a Secondary-sample result is the converted 1.0 pu and equals the
  calculated waveform display (same numbers, provenance `verified_converted`); without the authority the same result is the historical
  unconverted number (~0.0008 pu, the documented hazard class), proving the authority is what the consumer reads; a Primary result is
  `verified_direct` and bit-identical to the display; a Source Default Secondary result is refused by the display, by provenance and by the
  series alike; a non-strict leaf keeps the historical numbers (`unverified_historical`). A mutant that stops `compliance_series` passing the
  authority is caught. No production change was needed.
* **Disposition of the surviving mutants (§4.3).** `source_default_gets_a_group_ratio`, `ratio_for_source_default_not_refused` and
  `ratio_group_mismatch_ignored` each survive alone because two independent safeguards enforce the same rule (the `group_id is None`
  guard and the `context.group_ids != (group_id,)` guard in `calculated_voltage_side_inputs`); each one alone is an equivalent mutant of
  the pair. `both_ratio_group_guards_removed` is **caught** by
  `test_leaves_in_two_groups_fall_back_to_the_source_default_and_never_borrow_either_groups_vt`. The overlapping guards are retained
  deliberately (defence in depth); the surviving single mutants are accepted.
* **`manual_conflict_detected` observation (recorded, not changed).** While building the KPDN1 multibay fixture, saving a VT pair through
  the public `PUT …/voltage-config` (with the default or an explicit `auto` reference mode, with or without a stored nominal) left the
  line-to-line calculated channels `base_required` with raw reason `manual_conflict_detected`, whereas saving the same VT through the
  service `update_voltage_configuration(vt_primary_v, vt_secondary_v)` (reference pair preserved) resolved normally. The cause was not
  investigated (out of S3 scope, no S4 dependency identified); no production code was changed for it. Reproduce: upload
  `line_to_line_multibay`, create the KPDN1 Voltage group, `PUT` a config with `vt_primary_v`/`vt_secondary_v`, create the L-L channels, read
  `per-unit-resolution`.
