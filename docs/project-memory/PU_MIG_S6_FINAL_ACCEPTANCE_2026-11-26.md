# PU-MIG S6 — final compatibility review and engineering acceptance

**Date:** 2026-11-26 · **Authoritative worktree / branch:** `.local-data/pu-mig-s5`, `feature/pu-mig-s5-verification-presentation` (S1–S6 on the accepted
baseline `cf9e836`; S5 `7b2e8e0`/`7447d48`/`28fc3ca` preserved) · **Implementation commit under test: `7026f14`** (the acceptance suites ran against it; only
documentation was added afterwards).
**Local only: not pushed, merged or deployed. Stopped for owner review and UAT.**
Authority: owner message "PU-MIG S5 Acceptance and S6 Final Authorisation" (2026-11-26).

## 1. Governance statement (DEC-218)

Consulted before editing: AGENTS.md, CLAUDE.md, DEC-218; `PER_UNIT_MEASUREMENT_MODEL`; DEC-210/211 (Current base and reference compatibility), DEC-212, DEC-213,
DEC-215/216, DEC-070 Amendment 1, DEC-117/118; the S0 final reconciliation (§4.3, §9 S6 row, D-1…D-8, OD-3); the accepted S1–S5 reports and the S2–S4
reconciliation. Settled and **not reopened**: D-1 R+, D-2, D-4 (diagnostic only), D-5, D-6, D-7 (`auto_nominal`), D-8 (no deprecation through S4), N-2, DEC-212's raw-Current
restriction, K-1…K-3. No new PU eligibility, no retired UI restored, no API field removed, no migration of any denominator.

## 2. S6 changes (two commits)

| Commit | Change |
|---|---|
| `ee4dfae` | **Source Default Voltage reports the reference side it is declared on** (§3). `per_unit_provenance_service._source_default_base_side()`; 7 backend tests, the counterexample browser assertion, evidence PNG 09 refreshed. |
| `7026f14` | **Found by the acceptance run:** the S5 HTML comment inside the Per-unit overlay cut the slice read by the static test `test_popover_reuses_the_calculated_channels_info_strip_pattern` (overlay id → next `<!--`). The only failure of the first full backend run; the note moved into the S5 CSS comment. Markup and behaviour unchanged. |

The first acceptance sequence was stopped and restarted from the beginning on the corrected commit, so every reported total is for `7026f14`.

## 3. Outstanding S5 limitations — disposition

**Source Default Voltage base-side reporting → case B (established authority, not exposed).** The compatibility gate reads the stored `voltage_base_reference_side`
(`per_unit_reference.apply_source_reference`, `profile.voltage_base_reference_side`) and compares it with the measurement side, while the response hard-coded
`unknown` for every non-Current Source Default. The provenance now carries the gate's own `base_reference_side`. Preserved exactly: a Source Default that stores nothing
still reports **Unknown** (case A, tested); no number, verification state, status or eligibility changed (the S2/S4 outcome tables pass unmodified); the stored label never
becomes a Secondary denominator (D-5); no inference was added and Source Default selection is untouched. A 5-of-7 mutant check confirms the tests detect the old behaviour.
The 132 kV counterexample now shows *Base reference side: Secondary* beside *Unverified*.

**Calculated Voltage details dialog → deferred** (DEC-070 A1 and the badge-only presentation are preserved; `calculated-channel-presentation.spec.js:150` still asserts it).
**Future enhancement (not implemented):** an expanded calculated-channel information dialog that shows a calculated Voltage's verification state, side lineage and ratio provenance.

**Historical calculated-Current presentation test → accepted, with the distinction recorded.** The browser test replays the real automatic resolution with the backend's
historical-gate fields because the legacy pointer has no API route; it proves the *presentation* only. The *engineering resolution* is proven by real backend regression:
`test_pu_mig_s4_current_side.py::test_a_legacy_manual_pointer_keeps_its_historical_denominator_and_is_never_verified` and
`::test_recording_details_side_adds_a_block_to_the_legacy_manual_pointer_but_never_removes_one`, plus the S4 oracle integration.

## 4. Final compatibility review — S1…S5 as one implementation

| Requirement | Evidence (real backend regression unless stated) |
|---|---|
| Shared side-denominator authority | `test_pu_side_denominator.py` (30) and the independent oracle (`pu_side_denominator_oracle.py --check`: **CHECK OK**, re-run in this slice; 858-case grid, 132/138 : 110 matrix, 122 invalid, 21 extremes, 900 physical-equivalence rows; 200 resolved / 813 refused; AST-pinned stdlib-only imports); production call sites pinned by `test_pu_mig_s2_oracle_integration.py` / `test_pu_mig_s4_oracle_integration.py` |
| Raw Voltage | `test_pu_mig_s2_raw_voltage_side.py` (22), `test_pu_mig_s2_historical_gate.py` (108-case oracle), `test_pu_mig_s2_d7_closeout.py` (cases A, A0, B, C) |
| Calculated Voltage | `test_pu_mig_s3_calculated_voltage_side.py` (21), `…_side_lineage.py` (7), `…_compliance_series.py` (5) |
| Applicable Current PU | `test_pu_mig_s4_current_side.py` (42), `test_pu_mig_s4_oracle_integration.py`, `test_calculated_current_manual_config.py` |
| ENG-first calculation | the S3/S4 suites assert that a refused or unverified result keeps the ENG values and that PU is the scalar division of the ENG result; samples are never modified |
| Measurement Group inheritance and base-selection precedence | `test_per_unit_reference_safety.py`, `test_per_unit_voltage_reference_safety.py`, `test_pu_ssot_001_calc_voltage_ref_side.py`; S4 precedence tests (Stage 5B Manual > automatic common base > legacy pointer; group > Source Default) |
| Historical Unverified | `test_pu_mig_s2_historical_gate.py` (never verified, never newly allowed), S4 historical Current tests, S5 browser Unverified states |
| CT/VT authority consistency | one shared authority (`per_unit_side_authority`); `auto_nominal` D-7 closeout cases; S4 "two CT authorities" refusal |
| Known mismatch and missing-ratio refusals | `test_pu_mig_s2_d7_closeout.py` (no nominal → `vt_authority_unavailable`), S4 `ct_authority_unavailable`; S5 blocked-state browser test (actionable text, never the code) |
| Numerical representability | oracle extremes + S4 `effective_base_not_representable`; `per_unit_numerics` |
| Stage 5B atomicity | `test_per_unit_atomic_publication.py`, `test_per_unit_atomic_updates.py`, the S4 rejected-update test, browser `per-unit-atomic-updates.spec.js` |
| Coverage and provenance consistency | `test_per_unit_coverage_*.py`, `test_pu_mig_s5_verification_state_field.py` (the new state equals the resolution's on waveform, calculated, cursor, peak, anchor), S3 compliance series |
| Accurate verification-state presentation | `pu-side-provenance-presentation.spec.js` (13), 8/8 mutants killed |
| DEC-212 raw Current restriction | `per-unit-eligibility.spec.js`, S4 eligibility tests, S5 "raw Current stays engineering" |

No inconsistency between slices was found. The one defect the final run surfaced (§2, `7026f14`) was a static-test interaction of an S5 comment, not an engineering behaviour.

## 5. D-8 — `*_base_reference_side` API compatibility → **retained, no deprecation**

Review: the fields are read or written in 22 backend modules (≈ 150 references; `voltage_group_config`, `current_group_config`, `calculated_current_config`, the Source
Default profile `voltage_/current_base_reference_side`, `per_unit_reference`, `group_aware_per_unit`, provenance, measurement-group views/schemas, auto-base evidence) and 16
places in `frontend/index.html` (the Base Reference Side controls and their hints). They are **still required**: by the Measurement Group editors and Source Default writes
(current consumers), by stored historical configurations (D-2), by the D-5 legacy Secondary path (it needs a stored `secondary` declaration and a valid
`secondary_voltage_ll_v`), by historical Unverified treatment (an undeclared side must stay `unknown`, never assumed Primary), and by the reference-compatibility gate for
every non-strict case. S0 §9 lists their retirement as "separate approval". **Nothing was removed or deprecated.**
**Future proposal (needs a new owner decision, not blocking):** deprecate the inputs once (i) the OD-3 replacement contract exists, (ii) the D-5 legacy Secondary path is
retired with a data migration of stored configurations, and (iii) no current consumer reads the fields; the response fields would then be marked deprecated for one release before removal.

## 6. Engineering formula traceability (DEC-218)

```
rho = 1/sqrt(3) for a line-to-ground Voltage, otherwise 1          pu = sample / D          (samples are never scaled)
base side == sample side            D = B * rho                    (ratio not read)
base Primary,   samples Secondary   D = B * rho / r
base Secondary, samples Primary     D = B * rho * r                r = primary / secondary of the channel's own Measurement Group (VT for Voltage, CT for Current)
```

* **Established references:** S0 final reconciliation §4.3 (with governance correction GC-1 for the Secondary-on-Primary formula), the S1 report §2 (mathematical contract), the auto-base
  contract C1 (a nominal base is the primary-system L-L voltage), DEC-215 (`auto_nominal` = nominal kV × 1000 : 110 V), DEC-210/212/213, `PER_UNIT_MEASUREMENT_MODEL`.
* **Independent derivation:** per-unit is value ÷ base; the three-phase L-L/L-G relation is √3; an ideal transformer ratio r = V<sub>p</sub>/V<sub>s</sub> refers a quantity across sides
  (V<sub>p</sub> = r·V<sub>s</sub>), so a Primary base seen from the Secondary is B/r and a Secondary base from the Primary is B·r. The oracle encodes exactly these identities with 80-digit decimal
  arithmetic, imports no application code (AST-pinned), and asserts **physical equivalence**: the same physical condition recorded on a Primary and on a Secondary channel gives the same per-unit
  value to 1e-40. Worked fixture: 132 kV / 110 V VT (r = 1200): D<sub>L-G, primary</sub> = 76,210.2 V, secondary equivalent 63.5085 V, rated Secondary samples 1.0 pu on the converted base and 1/1200 on
  the (mis)labelled nominal — the counterexample.
* **Assumptions preserved:** the VT/CT ratio is the equipment's rated ratio; instantaneous samples are divided by an RMS-referred base (a rated-RMS waveform peaks at √2 pu — recorded in S2 §9.6);
  a stored secondary base is reported against the derived one and never replaced (D-4); a conversion needs an authoritative ratio (D-6).
* No application-wide formula audit was started.

## 7. Final regression — measured, against `7026f14`

All runs are against commit `7026f14` (one backend/browser worker as noted; default ports; `BEN5K_EXPERIMENTAL_ENABLED=1` for the browser). **Measured** results are kept apart from targeted runs; nothing below is projected.

| Suite | Measured result |
|---|---|
| **Complete backend suite** | **15,624 tests: 15,214 passed, 410 skipped, 0 failed, 0 errors** (29.4 min). The S5 total (15,207) plus the 7 new S6 tests. |
| Static frontend tests (`test_frontend_*`, part of the backend run) | 2,248 tests, 0 failed, 0 skipped. (The first full run caught the one comment-placement defect fixed by `7026f14`; this is the rerun.) |
| PU-related backend modules (`pu_mig*`, `pu_side*`, `per_unit*`, part of the backend run) | 2,226 tests, 5 skipped (pre-existing), 0 failed |
| **Owner-reference BEN backend tests** (`--ben-reference-dir`, 7 files: BEN5K fast/slow/mapping, BEN import, BEN parser, reference files, ASCII missing data) | **284 passed, 0 skipped, 0 failed** — they are among the 410 default-run skips because the recordings are not in the default environment |
| **Complete browser suite** (1 worker, ports 8000/8101) | **1,822 tests: 1,808 passed, 6 failed, 8 skipped** (2.2 h). The 6 failures are the documented deferred CSV/Excel backlog (§8); the 8 skips need the owner recordings |
| **Owner-reference BEN5K browser specs** (`BPHE_BEN_PATH`, `GPTH_SLOW_BEN_PATH`, `GPTH_BEN_PATH`, `PERMAS_BEN_PATH`; the recordings were located by their pinned SHA-256) | **13 of 13 passed** — the 8 previously skipped tests plus the 5 siblings in those four spec files |
| *Combined browser accounting (two measured runs, not one run)* | 1,816 passed, 6 deferred failures, 0 skipped |

Targeted evidence from this slice (not substitutes for the above): the S5 browser spec 13/13 (three consecutive runs 39/39 earlier; 13/13 after the S6 assertion), the 7 S6 backend tests, the 8 S5 mutants and the
Source Default mutant (5 of 7 fail under the old behaviour), the oracle `--check` (OK).

The browser suite regenerates seven tracked evidence screenshots (`rd1-d2-refine/*`, `recording-details-toolbar/*`) as a known side effect; they were restored to their committed state and are not part of any commit.

## 8. Known failures, skips and backlog

* **Six browser failures — all the documented deferred CSV/Excel preparation-row backlog, identical to the P0 record (row 6), none per-unit related:**
  `data-issues-estimate-fill.spec.js:32`, `:208`; `data-issues-panel.spec.js:27`, `:193`; `data-preparation-sticky-header.spec.js:50`; `sampling-rate-format.spec.js:24`
  (cause: CSV/Excel preparation rows are not listed in Recording Details — `BACKLOG_CSV_EXCEL_PREPARATION_ROWS_IN_RECORDING_DETAILS_2026-11-25.md`).
* **Eight browser skips** (BPHE layout, GPTH slow, Permas/GPTH physical mapping, GPTH slow/Fast, Permas Fast, BPHE Fast waveform values): gated on the owner-recording environment variables; all 8 pass when the recordings are supplied (§7).
* **410 backend skips:** unchanged from the S2–S4 baseline (405 reference/environment-dependent + 5 pre-existing); the 284 owner-reference BEN tests pass with the recordings.
* **No new skip, `xfail`, `fixme` or expected-failure annotation was added** since the accepted baseline `cf9e836` (checked on the diff of `backend/tests` and `browser-tests`).
* No unexplained engineering regression.

## 9. Protected-file integrity

Across S6 only `backend/app/services/per_unit_provenance_service.py`, the new backend test, the S5 browser spec, evidence PNGs 09 and the one comment in `frontend/index.html` changed. Unchanged since
the accepted baseline: `per_unit_reference.py`, `side_denominator.py`, `per_unit_side_authority.py`, `per_unit_numerics.py`, the group-config resolvers, `calculated_current_per_unit.py`,
`group_aware_per_unit.py`, the calibration gate, RMS and power mathematics, authoritative samples. The independent oracle and its expected JSON are byte-identical to S1/S4 (`--check` OK). Both archived
worktrees (`pu-mig-s1` with the superseded S5 files, `pu-mig-s2-verify`) and the paused NF/RMS/WUI worktrees were not touched.

## 10. Integration with main and DEV (nothing merged)

| Ref (after `git fetch origin`) | Tip | Relationship to `7026f14`-lineage |
|---|---|---|
| `origin/uat/dev-d5a-20261121` (DEV UAT branch) | `e9c621c` (2026-11-24) | **0 behind, 38 ahead — a fast-forward**; it contains D5A-2B2C-1B on the consolidated WUI-001–004 baseline `3ed200c` |
| `origin/main` | `b743a67` (2026-11-17) | 0 behind, ≈ 190 ahead (main lacks the whole D5A / WUI / NF / PU stack) |

Overlap with paused work (files changed on both sides, **not integrated**): NF-3E → `api/v1/{calculated_channels,compliance,sources}.py`, `services/calculated_channel_service.py`,
`services/compliance_readiness_service.py`; RMS R0 → `services/calculated_channel_service.py`; WUI-004 → `api/v1/sources.py` and `test_frontend_d5a_2b2b_measurement_side.py`; the consolidated WUI baseline → none.
**Recommended DEV approach:** deploy this branch alone, as a fast-forward of the DEV UAT branch (e.g. a `uat/dev-pu-mig-<date>` branch at the S6 documentation commit) through the existing
`Deploy Powerwave` workflow (`target=dev`), verify DEV `/health`, `/config.js` and the OpenAPI `per_unit_verification_state` field, run the owner UAT below, and only then decide `main`. The NF, RMS and WUI
branches should be rebased onto the accepted PU result later (the NF-3E / RMS overlap is in `calculated_channel_service.py`, a mechanical merge), not before UAT.

## 11. Owner UAT checklist (practical workflows; the twelve S5 screenshots are in `evidence/pu-mig-s5-2026-11-26/`, Light and Dark)

1. **Same-side Voltage.** Primary-scaled recording, Voltage group (132 kV, L-G), Primary base: toggle PU — values = sample ÷ base, no badge, *Per-unit details* → **Verified**, "no VT conversion needed".
2. **Converted Voltage.** The same condition on a Secondary-scaled recording with a 132 kV : 110 V VT: *Verified, base converted* with the ratio and its origin; the per-unit values equal those of step 1.
3. **Missing ratio.** Secondary recording, Primary base, no VT and no nominal: *PU unavailable* badge, ENG values shown, dialog tells you to enter the VT in Recording Details; entering it clears the badge without reload.
4. **Undeclared side.** Recording with no side: *Unverified reference* badge; declare the side in Recording Details and watch the badge and numbers update everywhere (waveform, cursor, peak, annotation).
5. **Source Default.** Source Default 132 kV labelled Secondary on rated Secondary samples: reads ≈ 0.0008 pu, **Unverified**, *Base reference side: Secondary* — never "Verified".
6. **Calculated Voltage.** A reversed/derived Voltage inherits its leaves' state (badge when Unverified/unavailable; no details dialog by design).
7. **Calculated Current.** Manual base + CT 240 : 1 on a Secondary recording: *Verified, base converted*; raw Current channels stay in amperes (DEC-212).
8. **Mixed sides.** A calculation combining a Primary and a Secondary channel is refused with the plain explanation.
9. **Stored vs derived.** A stored 115 V secondary base against a 110 V derived value shows *Stored base check*; the stored base is used and unchanged.
10. **Dialog usability.** Resize the window short and narrow: the sentence is never cut, Save/Close stay visible. Check Light and Dark.
11. **Existing analyses.** Event Reconstruction PU, compliance series, overcurrent and the BEN5K owner recordings behave as before.
12. **ENG ⇄ PU toggle** on every pane type: no stale values, no request storm.

## 12. Verdict and compliance

**Final PU migration engineering-readiness verdict: READY FOR DEV DEPLOYMENT AND OWNER UAT.** S1–S6 operate as one coherent implementation: one shared, independently-verified denominator authority; raw Voltage,
calculated Voltage and Current on it; a historical result is never certified; refusals are explicit and actionable; the user-facing verification state equals the engine's; all approved policies, the
DEC-212 restriction, the D-8 contract and the numerical behaviour are preserved. Conditions of the verdict: the 6 deferred CSV/Excel failures remain documented backlog; the calculated-Voltage information dialog
is a recorded future enhancement; D-8 deprecation is a future owner proposal. Acceptance still requires the owner's visual review and UAT.

**Local commits of the slice:** S5 `7b2e8e0`, `7447d48`, `28fc3ca` (preserved); S6 `ee4dfae`, `7026f14`, and the S6 record commit that adds this document (documentation only; the suites ran on `7026f14`).

**DEC-218 compliance statement:** the applicable decisions and documents were consulted before any change (§1) and none was reopened or amended; the two S6 code changes are a reporting correction of an established value (no new inference,
no numerical, eligibility or state change) and a comment relocation; the formula traceability and independent oracle evidence required by DEC-218 are recorded (§6) and re-verified (`--check` OK); no API field was removed; every
regression was measured and any defect found by the final run was fixed at its cause and the suites restarted on the corrected commit.
