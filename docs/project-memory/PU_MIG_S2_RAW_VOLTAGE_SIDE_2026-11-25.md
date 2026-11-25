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
| **D-7** | the existing `auto_nominal` VT is consumed with its provenance (`ratio_authority: auto_nominal`) — **with the one exception in §4** |
| **D-8** | no `*_base_reference_side` field is touched or deprecated |
| **N-2** | existing vocabulary: a required-but-unavailable VT is the existing PU reason `voltage_reference_side_incompatible` (and compatibility `incompatible`), a non-representable denominator is `effective_base_not_representable`; the resolver's own code and detail (`vt_authority_unavailable` + `no_group` / `not_configured` / `untrusted_authority` …) travel additively as `side_refusal_reason` / `side_refusal_detail`. No new production code was needed. The mapping is tested over every oracle refusal |

Source Default (ungrouped) channels: the nominal base is Primary by meaning, a Secondary sample has no VT authority (`no_group`) and is
blocked, a Primary sample is unchanged. A Source Default that stores `voltage_base_reference_side == "secondary"` has no secondary value
(D-5), so nothing is handed to the resolver and the historical gate decides exactly as before.

## 4. The one point raised under D-7

> **Governance note (2026-11-26, [DEC-217](DECISIONS.md#dec-217--approved-decisions-are-binding-agents-consult-them-before-acting-and-preserve-them-agent-governance)).**
> The approved `auto_nominal` VT authority is not reopened by this point: the VT equipment ratio and the selected PU base are
> independent engineering quantities, and a legacy secondary base differing from the 110 V default does not by itself reopen DEC-215 or
> D-7. The question below is to be assessed against the existing approved VT-authority and base-selection policies, not treated as a
> request to amend any of them; the guard described is an implementation provision pending that assessment. No policy was changed.

The `auto_nominal` contract (DEC-215, `auto_nominal_vt.py`) derives *primary = nominal kV × 1000, secondary = 110 V* — a documented
default. For Impedance and Distance this is exactly what the owner approved. For per unit the same ratio makes a Primary nominal base on
Secondary samples read `1 pu = 110 V · ρ` **whatever the nominal**. That is supported by the contract when nothing contradicts it; it is
**not** supported when the group itself stores a different secondary base (`secondary_voltage_ll_v`, for example the 1.0 kV the CFG
declares in the P0 fixtures): the default is then contradicted by the group's own evidence and the converted PU would be wrong by the
ratio of the two. The affected path is therefore **not enabled** for that combination: the `auto_nominal` ratio is refused
(`untrusted_authority`) and the channel is blocked (`voltage_reference_side_incompatible`), with the diagnostic of §3 explaining why.
A manual or recording-metadata VT is unaffected. No new inference was added. **Decision requested:** keep that fail-closed rule, or accept
the `auto_nominal` default even against a contradicting stored secondary.

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
  effective side not reported; stored secondary replaced by a derived one) — all caught; the frontend refresh removed — caught.

### 5.2 Numerical parity and equivalence

Same-side Primary (and Secondary) denominators are bit-identical to the existing arithmetic (`value / sqrt(3)` or the value, asserted with
exact equality of the whole array), the existing PU backend suites pass unchanged except where an S0 intentional change applies, and
one physical condition expressed on either side gives the same pu (1e-12). The S1 oracle (858 rows, 80-digit decimals) is the
reference for every denominator the gate produces.

### 5.3 Existing contracts updated — only for the S0 intentional changes (IC-1…IC-3, IC-7)

| Test | Change | Why |
|---|---|---|
| `test_per_unit_voltage_reference_safety` (group + Source Default matrix) | 3 new rows state the converted outcomes (strict `S`/primary, strict `P`/unknown, strict `S`/unknown); the "incompatible" rows keep every original assertion and now store the VT secondary the CFG declares (1.0 kV), which contradicts the 110 V default so no authoritative ratio exists; `C` and empty (non-strict) rows unchanged | IC-1/IC-2/IC-3, D-7 |
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

* **D-7 fail-closed rule** (§4) awaits the owner's decision.
* The badge/popover text "no CT/VT scaling is applied" (frontend lines 33257/33259) is now inaccurate for a converted result; it belongs to
  S5 (UI wording) and was deliberately not touched.
* Calculated Voltage (S3) and every Current path (S4) still use the historical gate; `measurement_side` there remains the raw declaration.
* A Source Default that stores `voltage_base_reference_side == "secondary"` keeps the historical gate (it has no secondary value, D-5).
* The verification state is on the provenance endpoint only; the five waveform response schemas still carry `per_unit_reference_compatibility`
  (whose `compatible` now includes "normalised by an authoritative ratio", as the S0 matrix stated).
* The auto_nominal conversion assumes the documented 110 V secondary default wherever the group stores nothing that contradicts it.

## 8. S2 acceptance verdict

Implemented as specified and verified: backend 0 failures; browser 0 unexplained failures (the only regression is an intentional change,
updated and re-verified; the 6 CSV failures are deferred and independent). **S2 is acceptable for owner review.** One decision is requested
(§4, D-7). S3 is not started.

