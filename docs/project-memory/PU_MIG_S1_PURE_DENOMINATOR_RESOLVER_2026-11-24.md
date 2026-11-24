# PU-MIG S1 — pure side-denominator resolver

**Date:** 2026-11-24
**Branch / worktree:** `feature/pu-mig-s1-pure-denominator-resolver`, `.local-data/pu-mig-s1`, created from `audit/pu-mig-s0-final-contract` (`d387033`), which differs from the DEV baseline `e9c621c4c15e0693d008670e9be8ae38b29c6d97` only under `docs/` (`backend/` and `frontend/` are byte-identical to `e9c621c`). Local only: **not pushed, merged or deployed.**
**Status:** implemented and verified locally. **Stopped for owner review before S2.** Authority: the owner's "PU-MIG S0 Closure and S1 — Pure Denominator Resolver" direction (2026-11-24). Governance corrections made first: [PU_MIG_S0_GOVERNANCE_CORRECTION_2026-11-24.md](PU_MIG_S0_GOVERNANCE_CORRECTION_2026-11-24.md).

Labels: **[FACT]** verified by reading code or running it · **[PENDING]** an owner decision that is open; nothing here treats it as approved.

---

## 1. What S1 delivers

One new production module, [backend/app/domain/side_denominator.py](../../backend/app/domain/side_denominator.py), exposing `resolve_side_denominator(quantity, base, sample, ratio, *, representation)`. It is pure (no I/O, no registry, no samples in or out, never raises), **connected to no consumer**, and makes no change to any current PU output. It accepts one already-established base and its declared side, the measurement-side result (including whether it is strict-usable), the quantity, the Voltage L-L/L-N representation and the already-established CT/VT information, and returns the denominator **in the unit of the samples' side**, or exactly one refusal reason, with the conversion provenance.

It deliberately does **not** choose between a stored `secondary_voltage_ll_v` and a nominal-derived value (**D-4, pending**), decide what activates the legacy secondary path (**D-5, pending**), approve converting a Secondary base onto Primary samples (**D-6, pending**), or retain/label/remove historical Unverified results (**D-1, pending**).

## 2. The mathematical contract

```
rho = 1/sqrt(3) for a line-to-ground Voltage, otherwise 1          pu = sample / D     (samples are never scaled)

base side == sample side           D = B * rho                    conversion "direct"                    the ratio is NOT read
base Primary,   samples Secondary  D = B * rho / r                conversion "base_divided_by_ratio"
base Secondary, samples Primary    D = B * rho * r                conversion "base_multiplied_by_ratio"  arithmetic only (D-6 pending)
r = primary / secondary of the consumed channel's own Measurement Group (VT for Voltage, CT for Current)
```

**Inputs** (frozen dataclasses): `SideBase(kind, value, declared_side)`; `SampleSide(side, problem, authority)`; `SideRatio(status, value, authority, group_ids)`. A base **kind** fixes the side where the meaning decides it: `nominal_ll_primary` and `equipment_derived_primary` are Primary by meaning; `legacy_secondary_voltage_ll` is Secondary; `manual_direct` and `result_manual` carry their own declared side. Voltage kinds are `nominal_ll_primary`, `legacy_secondary_voltage_ll`; Current kinds are `equipment_derived_primary`, `manual_direct`, `result_manual`.

**Refusal precedence** (first match wins; a refusal carries no number):

| # | Condition | Reason |
|---|---|---|
| 1 | invalid request (checked in this order) | `invalid_quantity` · `invalid_representation` · `invalid_base_declaration` · `invalid_base_value` · `invalid_sample_side` |
| 2 | sample side not strict-usable | `calculated_channel_side_unavailable` · `measurement_side_unresolved` · `measurement_side_inferred` · `measurement_group_side_conflict` |
| 3 | base side `unknown` (never assumed Primary) | `base_side_unknown` |
| — | sides match → **resolved, direct** (ratio never read) | — |
| 4 | a conversion is needed and the ratio is not authoritative | `vt_authority_unavailable` (Voltage) / `ct_authority_unavailable` (Current), with `detail` = the ratio status (`no_channels`, `no_group`, `not_configured`, `untrusted_authority`, `invalid`, `conflict`), `not_provided` (ratio absent), `invalid` (malformed status or value), or `untrusted_authority` (configured with an authority that is not `manual`, `recording_metadata`, `auto_nominal` or `mixed`) |
| 5 | denominator not representable | `denominator_not_representable` |

**Validation rules.** Voltage requires `representation` ∈ {`line_to_line`, `line_to_ground`} (never defaulted, so DEC-116's "undetermined → no base" is not bypassed); Current requires `representation` to be None. A base kind must belong to the quantity; equipment/nominal bases declared Secondary or Unknown, and the legacy secondary base declared Primary or Unknown, are contradictory and refused. Values must be finite, strictly positive, real numbers (`bool`, strings, `None`, NaN, ±inf, zero, negatives and ints too large for a double are refused). A sample is consistent only if it is `primary`/`secondary` with no problem, or has no side and one known problem. The status of a ratio is authoritative: a value that accompanies a non-configured status is never used.

**Numerics** reuse `app.domain.per_unit_numerics` (`positive_finite`, `SQRT_3`). The same-side path is exactly the existing arithmetic (`value / SQRT_3` for line-to-ground, otherwise the value unchanged), so same-side denominators are **bit-identical** to the production base resolvers. A conversion keeps the same operation order and uses one exponent-separated evaluation (a single final rounding) only when an intermediate or the result would not be a normal float. A result must be finite and nonzero; a **subnormal result is valid** (the repository's existing convention), overflow and underflow to zero are refused.

**Provenance on the result:** `conversion`, `ratio_applied`, `ratio_authority`, `ratio_group_ids` (only when a ratio was applied), `sample_side`, `sample_authority`, `base_kind`, `base_side`, `denominator_side`, `quantity`, `representation`, `representation_factor`.

### 2.1 Changes from the S0 specification (recorded, not hidden)

| S0 §11 said | S1 does | Why |
|---|---|---|
| a denominator below the smallest normal float is refused (T7) | **subnormal results are valid**; overflow and underflow-to-zero are refused | the owner's instruction is to preserve the existing numerical safeguards; `per_unit_numerics` states "Subnormal results are valid; overflow and nonzero-to-zero underflow are unavailable" |
| reasons: `invalid_base_declaration`, `invalid_base_value` | adds `invalid_quantity`, `invalid_representation`, `invalid_sample_side`, and a `detail` field | the owner asks to reject invalid and contradictory input explicitly; all names remain **proposals pending N-2** |
| ratio authority listed but not required | a `configured` ratio must carry one of the four consumable authorities | "reject non-authoritative required conversion information" |
| line-to-ground factor written as `B·ρ` | evaluated as `B / SQRT_3` | bit-identity with `per_unit.resolve_per_unit` and `voltage_group_config` (verified by tests) |
| `representation` optional | required for Voltage, forbidden for Current | an undetermined representation must not silently become line-to-line |

## 3. Independent expected-value matrix

The oracle ([pu_side_denominator_oracle.py](../../backend/tests/fixtures/pu_side_denominator/pu_side_denominator_oracle.py)) is standard library only, imports no application code, uses 80-digit decimal arithmetic on the **exact value of each double** the code receives, and states the contract in two different ways: a reference model with the refusal precedence, and a **physical model** (a true primary quantity X and a recorder ratio r give the two readings X and X/r; the per-unit value of that one condition must be identical on either side and for either base side, derived from physical truth, not from the denominator formulas). It regenerates byte-identically (`--check`).

| Matrix | Rows | Coverage |
|---|---|---|
| S0 final-contract table (unchanged artefact, git blob `d387033`, LF sha256 `7eb5070144cd8d24…`) | 324 | Voltage L-L/L-N × 2 bases × 6 sample states × 7 ratio states; Current × 5 bases × 6 × 7 |
| Exhaustive grid | 858 | Voltage L-L and L-N, 2 bases (Primary nominal, Secondary legacy); Current, 7 bases (equipment Primary, manual Primary/Secondary/Unknown, result Primary/Secondary/Unknown); 6 sample states (Primary, Secondary, calculated, unresolved, inferred, group conflict); ratio: 3 configured values (including identity ratio 1.0), 3 non-`manual` consumable authorities, 6 non-configured statuses, absent |
| 132 kV / 138 kV : 110 V | 12 | below |
| Invalid / contradictory input | 122 | every numeric token (NaN, ±inf, 0, negative, −0.0, `True`, `False`, string, `None`, int > 1e308) on the base and the ratio; invalid side, kind, quantity, representation, sample object, ratio authority and status; absent ratio; ten contradictory declarations |
| Extreme doubles | 21 | max and min doubles, min normal, subnormal inputs and results, overflow and underflow in both directions, line-to-ground at the edges, huge and tiny ratios |
| Physical equivalence | 900 | 3 bases × 5 ratios × (L-L, L-N) × 5 levels (0, 0.5, 0.87, 1, 1.1 pu) × 2 base sides × 2 sample sides, for Voltage and for Current (ratios from 1e-3 to 1e6) |

**The 132 kV / 138 kV : 110 V case** (system at nominal; VT 138 kV : 110 V, ratio 1254.5454…; secondary reading 132 000 × 110 / 138 000 = 105.217391304 V). The resolver is given one base at a time:

| Base given | Samples | D (V) | Conversion | pu |
|---|---|---|---|---|
| Primary nominal 132 kV | Primary 132 000 V | 132 000.000000000 | direct | **1.000000** |
| Primary nominal 132 kV | Secondary 105.217391304 V | **105.217391304** | base ÷ r | **1.000000** |
| Secondary base 110 V (a VT winding *rating*) | Secondary | 110.000000000 | direct | **0.956522** |
| Secondary base 110 V | Primary 132 000 V | 138 000.000000000 | base × r (arithmetic only) | 0.956522 |
| Independent Secondary base 105.217391304 V | Secondary | 105.217391304 | direct | 1.000000 |
| Independent Secondary base 105.217391304 V | Primary | 132 000.000000000 | base × r (arithmetic only) | 1.000000 |

The difference between 0.956522 and 1.000000 is **−1/23 = −4.347826 %**, asserted exactly by the oracle. It is a property of the *base* the caller supplies, not of the resolver: the resolver returns each base's own denominator and never overrides a stored value with a derived one (D-4). Line-to-ground variants give the same per-unit values.

## 4. Verification

| Check | Result |
|---|---|
| Focused tests, `backend/tests/test_pu_side_denominator.py` | **585 passed, 5 skipped.** The 5 skips are the by-design inapplicable combinations (Current × line-to-ground) of one parametrised same-side test |
| Oracle regeneration (`python -I pu_side_denominator_oracle.py --check`) | OK, byte-identical; every oracle invariant holds, including physical equivalence to 1e-40 and the exact −1/23 |
| Oracle independence | an AST test pins that the oracle imports only `itertools`, `json`, `sys`, `decimal`, `pathlib`, `copy` and `__future__` |
| Same-side bit-identity with production | the resolver equals `per_unit.resolve_per_unit` (source-wide Voltage L-L and L-N for 13 kV values from 1e-9 to 1e6, and direct Current) and `voltage_group_config.resolve_voltage_base_for_group` (nominal path, and the legacy `secondary_voltage_ll_v` path **including a group with no primary nominal**) with `==`, not "close" |
| Wide-range property | 6 000 log-uniform cases over almost the whole double range against exact decimal arithmetic: resolved exactly when representable, refused when not, subnormal results valid; each regime exercised more than 50 times |
| Never-raises fuzz | 27 junk values in every argument and every field of every input object: always a `SideDenominator`, never an exception, never a non-finite number |
| **Mutation check** (28 injected regressions in an out-of-tree copy) | **28 / 28 caught** |
| Existing PU / side / reference / group / calibration / D5A suites (84 test files, run on this branch) | **2 952 passed, 146 skipped, 0 failed** |
| Full backend suite, pristine baseline (`git archive d387033`, run in the scratchpad) | **13 701 passed, 405 skipped, 0 failed** |
| Full backend suite, this branch | **14 286 passed, 410 skipped, 0 failed** (+585 passed = exactly the new tests; +5 skipped = the 5 above) |
| Existing tests | none modified: `git diff --name-status e9c621c -- backend/tests` shows only additions (the new test module and the fixtures) |

**Mutants caught (28):** multiply/divide swapped; ratio read before the direct branch; direct branch removed; unknown base checked before the sample side; unknown base assumed Primary; line-to-ground ignored; line-to-ground as a multiplication by `1/sqrt(3)` (one-bit difference); `sqrt(3)` applied twice; non-positive ratio accepted; `bool` base value accepted; overflow/underflow refusal removed; subnormal results refused; exponent-separated fallback removed; inferred side accepted; VT and CT reasons swapped; ratio detail dropped; Voltage representation defaulted; equipment base allowed Secondary; ratio authority not checked; conversion labels swapped; group conflict reported as calculated; unrecognised ratio status accepted; sample provenance dropped; ratio provenance dropped; denominator side wrong; invalid sample object accepted; representation accepted for Current; same-side overflow unchecked.

**Source-diff evidence that nothing is wired** (against the DEV baseline `e9c621c`):

- `git diff --name-status e9c621c -- backend/app frontend browser-tests backend/pytest.ini` lists exactly one path: `A backend/app/domain/side_denominator.py`. `git diff --name-only e9c621c HEAD` outside `docs/` lists only that module, the new test and the fixtures.
- `per_unit.py`, `per_unit_numerics.py`, `per_unit_reference.py`, `voltage_group_config.py`, `current_group_config.py`, `side_conversion.py`, `reference_side.py`, `auto_base_evidence.py` and everything under `services/`, `api/`, `schemas/`, `frontend/` and `browser-tests/`: **zero diff**.
- `grep -rn side_denominator backend/app frontend` matches only the module itself. Two tests keep it that way: an import tripwire over every `backend/app` module, and a scan of the API, schema and frontend files. S2 must change that tripwire deliberately.


## 5. What is not done, and what stays pending

- **No consumer is wired.** The module is imported by nothing under `backend/app` (tripwire test); the frontend, API, schemas, auto-base writer, Base Reference Side controls, WUI-001–004 and the protection analyzers are untouched.
- **Pending owner decisions, unchanged:** D-1 (historical Unverified, per class), D-4 (precedence between `secondary_voltage_ll_v` and nominal ÷ ratio), D-5, D-6 (Secondary base on Primary samples), D-7, D-8, D-9 (the oracle fixtures and tests are test-only evidence under `backend/tests/fixtures/pu_side_denominator/`, subject to the owner's confirmation), N-2 (every reason code above is a proposal).
- **Commit message correction:** the message of `b055ba4` quotes the S0 table hash as `d81c1c11…`; that is the hash of the CRLF working-copy bytes. The git blob (LF) hash, identical in `d387033` and in this branch, is `7eb5070144cd8d24…`, and is the value the test pins.
- **P0 is still a hard gate before S2**, including replacement coverage for the retired Settings Hub controls through the current Recording Details workflow (see the governance correction, section 4). No browser test, spec or fixture was touched.
- **S2 is not started** and needs its own owner approval; it must also settle how a stored base is selected (D-4/D-5) before any consumer calls this function.
