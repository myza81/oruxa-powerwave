# PU-MIG S2 — raw Voltage: Recording Details' side and VT decide the per-unit denominator

**Date:** 2026-11-25 · **Branch / worktree:** `feature/pu-mig-s1-pure-denominator-resolver`, `.local-data/pu-mig-s1`, on top of the
accepted S1 (`e41aecd`, `b055ba4`, `993cf89`) and P0 (`07cbaaa`, `d122037`, `1fb0128`, `a328ff2`, `abe2a7e`, `557d4f1`).
Baseline for the numbers below: the P0 browser baseline (1,783 passed / 20 failed / 8 skipped, `07cbaaa`) and `e9c621c` code.
**Local only: not pushed, merged or deployed. Stopped for owner review (S3 is not started).**
Authority: owner message "PU Migration — Final P0 Acceptance and S2 Authorisation" (2026-11-25).

## 1. Scope actually implemented

Governance scope (S0 final reconciliation §9.1/§9.2, row S2): *raw Voltage — one shared function for the four source seams,
resolver side + ratio, refresh wiring, provenance, `measurement_side` semantics; fixes C-3.* Implemented:

| Seam | Where | Change |
|---|---|---|
| Source waveform range, cursor values, peak values, annotation anchors | `waveform_service._resolve_effective_per_unit` (the one dispatch the four call) | the raw gate is `per_unit_side_authority.apply_raw_source_reference` |
| Provenance (`GET /sources/{id}/per-unit-resolution`) | `per_unit_provenance_service` | same function; additive verification/conversion fields |
| Coverage (`GET /per-unit/sources/{id}/coverage`) | `per_unit_coverage_service` | same function; **now passes the Voltage group configuration like the other seams (S0 finding C-3)** |
| Compliance series / readiness (source Voltage) | `compliance_series.Registries.side_authority` | follows the seam |
| Refresh wiring | `frontend/index.html` `wwRdSideEnqueue` | a saved side re-reads the displayed PU channels once after the last queued write |
| `measurement_side` semantics | provenance | the EFFECTIVE side when Recording Details established one; the recording's declaration otherwise (unchanged) |

Deliberately **not** in S2 (their own slices or decisions): calculated Voltage/Current (S3/S4), raw Current and every Current base
(S4, DEC-212: raw Current stays engineering), UI wording and Base Reference Side controls (S5/S6; the "no CT/VT scaling" wording is
untouched), `*_base_reference_side` API fields (D-8), Source Default stored-`secondary` handling (below), the group-level view
(`measurement_group_view_service` computes a group's base, which does not depend on a sample side, so it needed no change and already
agrees with the seams). No decision conflicts with the original specification; the one point needing the owner is §4.

## 2. Resolver integration points

`side_denominator.resolve_side_denominator()` has **one** call site: `per_unit_reference.apply_strict_voltage_reference`. A guard
test (`test_pu_side_denominator.py::test_the_resolver_is_connected_only_at_the_s2_integration_points`, AST-based) fails on any other
caller (no duplicated denominator arithmetic) and on any importer outside the five listed integration modules.

Separation of concerns:

* **Base selection** stays with the unchanged base resolvers (`resolve_voltage_base_for_group`, `resolve_per_unit`): they now merely hand
  on the established base (`PerUnitResolution.base_descriptor`: kind, SI value, declared side) and the representation.
* **Measurement side** and **ratio authority** are read from Recording Details by `per_unit_side_authority` (the same
  `evaluate_channel_side` / `resolve_transformer_context` Overcurrent, Impedance and Distance use); that adapter does no arithmetic.
* **Denominator arithmetic**: the S1 resolver only. **Eligibility and representability**: the existing `resolve_conversion_eligibility`,
  unchanged and still applied afterwards. **Samples** are never modified.

## 3. Approved policies implemented (owner decisions 2026-11-25)

| Decision | Implementation |
|---|---|
| **D-1 R+** | a strict-usable sample side is verified (`verified_direct` / `verified_converted`); a side that is not strict keeps the historical gate and its numbers bit for bit and is labelled `unverified_historical`; a known Primary/Secondary mismatch is never bypassed (the historical gate still blocks it; `blocked`) |
| **D-4 P5** | nothing is selected or replaced; a stored secondary base that disagrees with the one derived from nominal ÷ VT is reported as `base_diagnostics` (`stored_secondary_differs_from_derived`); P4 not implemented |
| **D-5** | the legacy secondary path is activated only by a stored `base_reference_side == "secondary"` **and** a valid stored `secondary_voltage_ll_v` (unchanged selection; the mere presence of a value does nothing — mutation-checked) |
| **D-6** | a Secondary base on Primary samples converts (`base × VT ratio`) only with an authoritative ratio, else it is blocked; no new automatic base selection |
| **D-7** | the existing shared VT authority (DEC-215, `auto_nominal` included) is consumed exactly as approved, with its provenance (`ratio_authority`); PU adds no rule of its own (reassessed and corrected in §4) |
| **D-8** | no `*_base_reference_side` field is touched or deprecated |
| **N-2** | existing vocabulary: a required-but-unavailable VT is the existing PU reason `voltage_reference_side_incompatible` (and compatibility `incompatible`), a non-representable denominator is `effective_base_not_representable`; the resolver's own code and detail (`vt_authority_unavailable` + `no_group` / `not_configured` / `untrusted_authority` …) travel additively as `side_refusal_reason` / `side_refusal_detail`. No new production code was needed. The mapping is tested over every oracle refusal |

Source Default (ungrouped) channels: the nominal base is Primary by meaning, a Secondary sample has no VT authority (`no_group`) and is
blocked, a Primary sample is unchanged. A Source Default that stores `voltage_base_reference_side == "secondary"` has no secondary value
(D-5), so nothing is handed to the resolver and the historical gate decides exactly as before.

## 4. D-7 reassessment and correction (closeout, 2026-11-26)

Applied under [DEC-218](DECISIONS.md#dec-218--approved-decisions-are-binding-agents-consult-them-before-acting-and-preserve-them-agent-governance)
and the owner's closeout direction. **No policy changed**: the approved `auto_nominal` VT (DEC-215: primary = accepted nominal, secondary =
110 V default, provenance `auto_nominal`), the existing manual VT correction and the shared VT authority (manual > recording_metadata >
auto_nominal > not_configured) are not reopened. The selected PU base and the VT equipment ratio are independent engineering quantities.

**Documents and records consulted:** DEC-215 and `D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md`; DEC-216 Amendments 6–7; DEC-211 and DEC-212;
`PER_UNIT_MEASUREMENT_MODEL.md` §11 (a VT ratio is measurement scaling, not itself a Vbase); the S0 reconciliation (§4.3 denominator, §4.5
selection, §8 rows) and the owner decisions D-1, D-4 (P5), D-5, D-6, D-7, D-8, N-2 of 2026-11-25; the S1 specification; and the code and tests
named below.

**Finding 1 — the guard was unsupported.** The S2 provision "refuse the `auto_nominal` ratio for PU when the group stores a different
`secondary_voltage_ll_v`" was a PU-specific VT authority. DEC-215 makes the derived VT "immediately valid for every consuming module";
`secondary_voltage_ll_v` is a PU base, not a VT (the authority only checks a *stored VT* first); and D-4 (P5) requires a stored-versus-derived
disagreement to be **reported, not acted on**. A per-consumer rule over a shared authority is what DEC-218 forbids. **Corrected:** the guard and its
helper are removed; `per_unit_side_authority` passes the shared authority's answer through unchanged.

**Finding 2 — the "1200×" is the approved arithmetic, not a discrepancy.** In `waveform-axis-units` the same raw numbers read as Primary and as
Secondary volts differ by the VT ratio of a 132 kV nominal with the 110 V default: 132 000 / 110 = 1200. Nothing was scaled twice.

**Worked example on the actual legacy fixture** (`synth_measurement_groups`, channel `N275_VR`, L-L reference as the VLT-REF-001 tests set it,
nominal 275 kV, the CFG's own VT secondary 1.0 kV stored as the group's secondary base = 1000 V). Independent expected values are in
`test_pu_mig_s2_d7_closeout.py`; the engine matches them to 1e-12:

| Case | Sample peak (instantaneous) | VT authority | Base D | sample / D (peak-referred) |
|---|---|---|---|---|
| A: stored side Primary, no VT stored | Secondary, 0.577345 kV | `auto_nominal` 275 kV : 110 V, r = 2500 | 275 kV / 2500 = 0.110 kV | **5.2486** |
| B: A + the engineer's manual VT 275 kV : 1 kV (existing correction) | Secondary, 0.577345 kV | `manual`, r = 275 | 275 kV / 275 = 1.000 kV | **0.577345** (= 158.77 kV / 275 kV on the Primary recording) |
| C: stored side **Secondary** 1000 V (D-5: declared + valid value) | Secondary, 0.577345 kV | not read (same side) | the **stored** 1.000 kV | **0.577345** |
| D: stored side Secondary 1000 V, Primary samples | Primary, 158.77 kV | `auto_nominal`, r = 2500 | 1.000 kV × 2500 = 2500 kV | **0.063508** |
| E: D + manual VT, r = 275 | Primary, 158.77 kV | `manual` | 1.000 kV × 275 = 275 kV | **0.577345** |

Every figure is an **instantaneous sample peak divided by a base**, not a per-unit of rated RMS voltage: the fixture's samples peak at 158.77 kV (= 275 kV / sqrt(3)), and a waveform at exactly rated RMS would peak at sqrt(2) times the RMS-referred base. The table checks the division and the side conversion. (See section 9.4.)

A and B differ by exactly 2500 / 275 = 1000 V / 110 V = 9.0909: the ratio of the two VT assumptions, which is what the D-4 report
(`base_diagnostics`: stored 1000 V, derived 110 V, relative difference 8.09, derivation `auto_nominal`) tells the engineer. The stored 1 kV base is
used as stored (C, D, E) and never replaced (D-4); the diagnostic is the whole of the PU-specific response; the engineer's remedy is the existing
manual VT (B, E). Without a nominal the authority derives nothing, and a Secondary base on Primary samples stays blocked (D-6).

**Finding 3 — Source Default historical gate.** It preserves the approved side-safety restrictions: a stored `secondary` base against
Secondary samples is the same-side number (no ratio read), against Primary samples it is blocked (an ungrouped channel has no ratio authority,
S0 §8), and an undeclared side keeps the historical Unverified number (D-1). One gap was found and **corrected**: the gate compared the stored
base side with the recording's *raw declaration*, so an engineer's correction (DEC-216) could be ignored and a declared-Secondary recording
corrected to Primary still read "compatible". The gate now compares the **effective** side when Recording Details has established one; it
never alters a denominator, so no number changes. D-5 is applied unchanged: the legacy path needs an explicit Secondary declaration and a valid
stored value, and a stored value alone activates nothing.

## 5. Verification

### 5.1 Tests added (173 backend/static, 3 browser)

* `test_pu_mig_s2_oracle_integration.py` (148): the production gate driven by the frozen S1 oracle rows (125 Voltage rows: grid, the
  132/138 kV case, numeric extremes) — the number that reaches `base_amount`, the ratio read only for a conversion, every refusal
  mapped to the existing vocabulary with the resolver's code/detail carried; historical Unverified qualification (bit-identical number,
  `unverified_historical`), no bypass of a known Primary/Secondary mismatch, no ratio read for a historical result.
* `test_pu_mig_s2_raw_voltage_side.py` (23, real API): same-side Primary bit-identical to the historical arithmetic; same-side
  Secondary (legacy) with no ratio; Primary base on Secondary samples with a manual VT and with `auto_nominal`; physical equivalence
  (primary and secondary samples of one condition give the same pu to 1e-12); stored-Unknown base side with strict Secondary (IC-2);
  an engineer's recording correction changing PU (IC-7); Secondary base on Primary samples with and without a ratio (D-6); the D-5
  rule (a stored value alone does nothing; a Secondary declaration without a value stays blocked); D-4 P5 (stored base never
  replaced, discrepancy reported); Source Default primary / secondary; downstream non-representable PU, conversion overflow and a
  subnormal denominator; coverage agreeing with provenance (C-3).
* static harness (2): a saved side refreshes the displayed PU channels once after the last write, a failed write does not.
* browser (3): the converted case, the Recording Details refresh, and the updated axis-units expectation.
* Anti-vacuity: 9 mutants of the S2 wiring (ratio ignored; ratio read for same side; legacy path activated by a stored value;
  historical labelled verified; `auto_nominal` guard removed; coverage dropping the group config; a refusal given a number;
  effective side not reported; stored secondary replaced by a derived one) — all caught; the frontend refresh removed — caught. Closeout mutants (historical gate ignoring the effective side; a PU-specific `auto_nominal`
  refusal reintroduced; the stored secondary base altered on the legacy path) — all caught.

### 5.2 Numerical parity and equivalence

Same-side Primary (and Secondary) denominators are bit-identical to the existing arithmetic (`value / sqrt(3)` or the value, asserted with
exact equality of the whole array), the existing PU backend suites pass unchanged except where an S0 intentional change applies, and
one physical condition expressed on either side gives the same pu (1e-12). The S1 oracle (858 rows, 80-digit decimals) is the
reference for every denominator the gate produces.

### 5.3 Existing contracts updated — only for the S0 intentional changes (IC-1…IC-3, IC-7)

| Test | Change | Why |
|---|---|---|
| `test_per_unit_voltage_reference_safety` (group + Source Default matrix) | 4 new rows state the converted outcomes (strict `S`/primary, strict `P`/unknown, strict `S`/unknown, strict `P`/secondary base); the blocking cases keep every original assertion and obtain "no authoritative ratio" the approved way — Primary samples against a stored Secondary base with **no nominal**, so the shared VT authority has nothing to derive; `C` and empty (non-strict) rows unchanged | IC-1/IC-2/IC-3/IC-4, D-6 |
| `test_per_unit_reference_safety[default_derived-S-primary]` | the nine Source Default Voltage channels are no longer counted "unverified": their strict Primary side is the proof (same numbers, label only); the count of enabled channels is unchanged | IC-3 |
| `test_pu_side_denominator` disconnection guard | becomes an AST-based allowlist of the five S2 integration modules and the single caller | S1 said "deliberately changed by S2" |
| `per-unit-voltage-reference-safety.spec.js` (browser) | same treatment as the backend matrix, plus two new tests | IC-1 |
| `waveform-axis-units.spec.js` | after a recording-side change the pane is compared with the API's engine result and the independent ×1200, instead of the old values | IC-7; the "no double conversion" purpose is kept and strengthened |

No assertion about a historical (non-strict) result, a refusal, a numeric value or a safeguard was weakened or removed.

### 5.4 Regression results

* **Complete backend suite** (one run, final production tree): 14,875 tests — 14,465 passed, 410 skipped (pre-existing: owner-reference data,
  `ben_reference`, `slow`), **0 failed**. (The first run, before the intentional-change updates, had 15 failures: the 10 voltage
  reference-safety and 1 current reference-safety contracts of §5.3, 3 static-harness tests that did not know the refresh, and the S1
  guard; all dispositioned above.)
* **Targeted browser** (PU atomicity, numeric integrity, display synchronisation, Recording Details base configuration, side/ratio
  safety, compliance, Overcurrent/Impedance/Distance side specs, BEN5K PU gates, waveform PU): 439 passed, 2 failed (the two
  IC-1 cases of `per-unit-voltage-reference-safety`, fixed as §5.3), 4 skipped (owner-data).
* **Complete browser acceptance** (one worker, `BEN5K_EXPERIMENTAL_ENABLED=1`, production commit `eb8d4e3`, tests `0ca10bc`): **1,809 tests —
  1,794 passed, 7 failed, 8 skipped** (1.1 h). Against the P0 flagged baseline (1,811 / 1,783 / 20 / 8) by identity: 1,782 unchanged
  passes, 10 baseline failures now pass (the P0 closeout fixes), 4 retired by the owner, 2 added; the same 6 CSV/Excel
  preparation-row failures remain (deferred, not S2); **1 regression**, `waveform-axis-units.spec.js:29`, an intentional change
  (§5.3) updated afterwards in `c2b57bb` and verified by running that spec (8/8). The 8 skips are the owner-reference-data specs
  (environment variables unset), identical to the baseline. The post-run test edit is verified by that targeted run, not by a
  second complete run.
* The 6 CSV failures are unchanged and unrelated. The projected figure after `c2b57bb` is 1,795 passed / 6 failed / 8
  skipped — **derived, not measured**.

## 6. Protected files and boundaries

`git diff 557d4f1..HEAD`: no change to `side_denominator.py` (the S1 resolver), `per_unit_numerics.py`, any calculated-channel
service, any Current base module, RMS code, waveform samples (read-only throughout) or any API write contract; no `*_base_reference_side`
field changed or deprecated; nothing pushed, merged or deployed. Concurrent branches: NF-3x touch `api/v1/sources.py` and
`frontend/index.html` (this slice adds 16 and 9 lines there, no existing line changed); `rms-r0` and the WUI branches touch none of
the changed files.

## 7. Remaining limitations

* The badge/popover text "no CT/VT scaling is applied" (frontend lines 33257/33259) is now inaccurate for a converted result; it belongs to
  S5 (UI wording) and was deliberately not touched.
* Calculated Voltage (S3) and every Current path (S4) still use the historical gate; `measurement_side` there remains the raw declaration.
* A Source Default that stores `voltage_base_reference_side == "secondary"` keeps the historical gate (no resolver base; D-5), now comparing the
  effective side (§4, Finding 3).
* The verification state is on the provenance endpoint only; the five waveform response schemas still carry `per_unit_reference_compatibility`
  (whose `compatible` now includes "normalised by an authoritative ratio", as the S0 matrix stated).
* The auto_nominal conversion uses the documented 110 V secondary default exactly as DEC-215 approves; where the real VT differs the engineer
  enters it (existing manual VT) and the D-4 report says so (§4).

## 8. S2 acceptance verdict

Implemented as specified and verified: backend 0 failures; browser 0 unexplained failures (the only regression is an intentional change,
updated and re-verified; the 6 CSV failures are deferred and independent). **S2 is acceptable for owner review.** The D-7 point is
resolved by correction (§4); no decision is outstanding from S2. S3 is not started.

## 9. Owner verification of the concurrent correction (2026-11-26)

Scope: commits `8ef6d5c` (guard removal and the historical-gate change) and `1dea5e4` (closeout tests and record), on the committed state
`58ef97b`; reviewed and re-run on a separate verification branch (`verify/pu-mig-s2-correction`) so that the active PU session's uncommitted work
in this worktree was not touched. **No production file was changed by this verification.**

**Authorship.** Both commits were created by the PU session `3d20c740-5d83-440b-a7f3-ce61d7bbe558` (its transcript holds the commit tool call at
00:37:49 UTC, 08:37:49 +08:00, in `.local-data/pu-mig-s1`); the git identity and the `Co-Authored-By` trailer are shared by every session and prove nothing.
The verifying session (`ec1c6f12-…`) never ran a write command in that worktree.

**Guard removal** (`per_unit_side_authority.py`): accepted. The shared ratio is returned unchanged; the D-4 P5 diagnostic is retained.

### 9.1 Behavioural delta of the `per_unit_reference.py` change (exhaustive, 108 input rows, old `8ef6d5c^` against new)

The change touches only the Voltage historical gate, which is reached when the resolver is NOT used: a Source Default that stores `secondary` (no
base descriptor, D-5) and a resolution that is not configured. The Current branch (DEC-210), `side_denominator.py`, `per_unit_numerics.py` and every
CT/VT and calibration module (DEC-213) are byte-identical.

* **Unchanged (bit for bit):** every row whose sample side is not strict (unknown, inferred, unresolved, group conflict, or no authority supplied): 0 of those rows
  changed. An inferred or unusable side is never promoted. `base_amount` is identical in all 108 rows: **no denominator changed**.
* **Changed (strict effective side from Recording Details, resolver not used), configured Source Default stored `secondary`:**

| Raw declaration | Effective side | Before | After | Class |
|---|---|---|---|---|
| Primary | Primary | blocked | blocked | unchanged |
| Primary | **Secondary** | blocked | configured, compatible, **`verified_direct`** | newly allowed (engineer's correction) |
| Secondary | Secondary | configured, `unverified_historical` | configured, **`verified_direct`** | relabelled |
| Secondary | **Primary** | configured (compatible) | **blocked** | newly blocked (known mismatch, DEC-211/216) |
| Unknown | **Primary** | configured, unverified | **blocked** | newly blocked |
| Unknown | **Secondary** | configured, unverified | configured, compatible, **`verified_direct`** | newly allowed and relabelled |

  For an unconfigured resolution (status already `base_required`) only `reference_compatibility` and the reported `measurement_side` change; no number.
  With base side `unknown` only the reported `measurement_side` changes.

### 9.2 Finding: the relabel to `verified_direct` is not justified on this path

Numbers on the real API, Source Default, line-to-ground, 132 kV / 110 V VT (ratio 1200); `pu` is a sample peak divided by the base:

| Case | Before | After |
|---|---|---|
| Base value 0.110 kV declared Secondary, Secondary samples at 110 V / sqrt(3) | 1.0, `unverified_historical` | 1.0, `verified_direct` |
| **Base value 132 kV declared Secondary (by mistake), Secondary samples of the same condition (63.5085 V)** | **0.000833333**, `unverified_historical` | **0.000833333, `verified_direct`** |
| The same, no raw declaration, the engineer sets Secondary | 0.000833333, `unverified_historical` | **0.000833333, `verified_direct`** |

The second row is the 1200x error (63.5085 / 76,210.2 = 8.333e-4 against 1.0): a Source Default has no secondary value (D-5), the base resolver treats its
nominal as Primary by meaning (`per_unit.py`), and the gate cannot tell a Secondary-valued base from a mistyped Primary one. The side of the SAMPLES is
strictly established; the side of the DENOMINATOR is only the engineer's label. Before the change such a result was honestly `unverified_historical`; after it,
the same wrong number carries `verified_direct`, `denominator_side = secondary`, `conversion = direct`. This does not meet the owner's condition that a
strict side be "correctly paired with the actual denominator". The blocking half of the change (newly blocked rows) is the safe direction and is not affected.

**Proposed minimal narrowing (not applied; the file is being edited by the PU session):** in the historical branch keep comparing the effective side for
blocking and compatibility, but never emit `verified_direct`, `denominator_side` or `conversion`: a compatible result stays `unverified_historical`, a
mismatch is `blocked`. Numbers are unaffected. Expected test change: the three `verified_direct` rows of
`test_source_default_stored_secondary_keeps_its_side_safety` and `..._honours_the_engineers_side_correction` become `unverified_historical`; nothing else
depends on the label. Verification of the pairing would need an established secondary base value for the Source Default (a separate decision).

### 9.3 Required cases (committed `58ef97b`, real API, 132 kV / VT 1200; expected values from first principles)

| Case | Samples | Result | Denominator | Expected | State |
|---|---|---|---|---|---|
| A: stored 1 kV, Primary base, no VT stored | Secondary 63.5085 V peak | **1.0** | `auto_nominal` r = 1200, base 63.5085 V | 1.0 | `verified_converted`, diagnostic `stored_secondary_differs_from_derived` retained |
| A0: no stored secondary | Secondary 63.5085 V | **1.0** | same | 1.0 | `verified_converted` |
| B: stored side Secondary + 1 kV (D-5) | Secondary 63.5085 V | **0.11** | the stored 1 kV / sqrt(3) = 577.35 V, no ratio read | 0.11 | `verified_direct` |
| C: same base on Primary samples | Primary 76,210.2 V | **0.11** | 577.35 V x 1200 = 692.82 kV | 0.11 | `verified_converted` |
| No nominal (no authority derivable) | Primary | raw 76,210.2 (blocked) | none | blocked | `blocked`, `vt_authority_unavailable` |
| Invalid VT (0 V primary) | any | rejected at the API (`invalid_instrument_transformer_value`); cannot be stored | | | |

### 9.4 RMS versus peak

The S2 test and record wording is corrected: per unit is applied to **instantaneous samples**, `pu = sample / D` with the RMS-referred base D. The synthetic
sinusoids have a **peak** equal to D (1.0 pu peak, 0.7071 pu RMS); a waveform at exactly rated RMS peaks at sqrt(2) = 1.4142 pu. "1.0 pu" in these tests, and
the earlier statement "1.0 pu is the rated condition", mean "the same peak-referred value on either side of the VT".

### 9.5 Results (verification branch, tests unchanged apart from comments)

| Run | Result |
|---|---|
| Focused backend: 52 PU, per-unit, reference-safety (Voltage and Current), CT/VT, auto-nominal, side-denominator, D5A protection-context, measurement-group, calibration (DEC-213) and PU-MIG files | **2,492 passed, 5 skipped, 0 failed** (7 min 19 s) |
| Full backend suite | **14,473 passed, 410 skipped, 0 failed** (27 min 37 s); the S2 record's 14,465 plus the 8 closeout tests |
| PU browser specs (voltage and Current reference safety, axis units, atomic updates, display synchronisation, numeric integrity, eligibility, VT effective, overcurrent and protection side, BEN5K PU gates, Recording Details toolbar, auto-PU import) | **164 passed, 0 failed** (9.5 min) |
| Dry run of the proposed narrowing (scratch export, not applied) | only the two predicted closeout label assertions fail; the other 5 failures of that run are an artefact of the partial export (no `frontend/`) |

Governance statement: documents consulted — AGENTS.md (DEC-218 governance), DEC-210, DEC-211, DEC-213, DEC-215, DEC-216, the P0 decision register (D-1, D-4..D-8), the S2 record and the code. No approved policy changed. Unresolved: the `verified_direct` relabel on the Source Default path (9.2).
