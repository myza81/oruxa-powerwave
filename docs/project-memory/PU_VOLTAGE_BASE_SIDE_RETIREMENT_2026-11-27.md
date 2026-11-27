# Voltage Base Reference Side retirement (DEC-219) — implementation record and legacy replacement-contract proposal

**Date:** 2026-11-27 · **Worktree / branch:** `.local-data/pu-mig-s5`, `feature/pu-mig-s5-verification-presentation`, on the DEV baseline `9ec49d9`.
**Local only: not pushed, merged or deployed. Stopped for owner review before any DEV redeployment.**
Authority: owner direction "Voltage Base Reference Side Retirement" (2026-11-27), recorded as **DEC-219** in [DECISIONS.md](DECISIONS.md#dec-219--the-nominal-system-voltage-is-always-the-primary-voltage-pu-base-the-separate-voltage-base-reference-side-input-is-retired).

## 1. Governance statement (DEC-218)

Consulted before editing: AGENTS.md, DEC-218; DEC-216 and Amendments 6–7 with the Correction (the deferred PU retirement); D-2 / OD-3 (agreed), D-4 (P5), D-5, D-6, D-7, D-8
(25 Nov); the S0 final reconciliation and governance correction; the accepted S1–S6 reports; the previous read-only retirement report; the Recording Details implementation and its
tests. Nothing was reopened: no mathematics, no CT/VT authority, no historical-Unverified, no D-4/D-5/D-6/D-7/D-8 policy. Only the Voltage selector is retired; the Calculated Current
manual base-side control, DEC-212, calculated-Current PU, RMS/power mathematics and the samples are untouched.

## 2. What changed

| Path | Change |
|---|---|
| `frontend/index.html` | The **Base reference side** selector (`wwRdVltRefSide`), its option list, its draft state and its help text are removed from Recording Details → Voltage group → Advanced. |
| | `wwRdVoltageNominalSave()`: a save that **establishes a nominal base** (a new, changed or `legacy_manual`-reviewed value) sends `nominal_voltage_ll_kv` and `base_reference_side: "primary"`; any other save sends **neither** (the unchanged nominal is not re-sent, so it cannot clear a stored secondary base, and the side is omitted, so the backend preserves it). |
| | The three other Voltage writers (clear nominal, set VT, clear VT) no longer echo `(vc && vc.base_reference_side) \|\| "unknown"` — that echo wrote **Unknown** whenever a group had no stored configuration. |
| | `wwRdLegacySecondaryBaseNoteHtml()`: a legitimate legacy Secondary base (stored Secondary + a valid stored secondary value, the D-5 criterion) is shown **read-only** in read and edit mode, with the consequence of changing the nominal stated; it is shown with or without a nominal (A15). |
| `backend/` | **No production change.** The API contract already preserves an omitted `base_reference_side` (`measurement_groups.py:431`, `voltage_group_config_service.py:105`); the frontend now relies on it. |
| Tests | `backend/tests/test_pu_voltage_base_side_retirement.py` (13), `backend/tests/test_frontend_pu_voltage_base_side_retirement.py` (6), `browser-tests/pu-voltage-base-side-retirement.spec.js` (5); four selector assertions updated in `rd1-slice-d2.spec.js`, `rd1-slice-d2-final.spec.js`, `rd1-slice-d2-uat.spec.js` (policy-bearing; the owner authorised the retirement). |
| Evidence | `docs/project-memory/evidence/dec-219-2026-11-27/` — before (`9ec49d9`) and after, Light and Dark. |

## 3. Writer inventory (frontend and auto-base) and the verified outcome

| Writer | Before | After |
|---|---|---|
| Recording Details **Apply** (`wwRdVoltageApply`) | sent the draft side (Unknown / Primary / Secondary) and always re-sent the nominal | nominal and `"primary"` only when a nominal base is established; otherwise neither |
| **Clear manual nominal** (`wwRdVoltageRevert`) | echoed the stored side, or **Unknown** with no stored config | omitted |
| **Set VT** (`wwRdVtApply`) / **Clear VT** (`wwRdVtRemove`) | same echo | omitted |
| Auto-base **Primary path** (`auto_base_service`) | writes nominal + `"primary"` | unchanged and **consistent** with DEC-219 (tested) |
| Auto-base **insufficient-evidence path** | wrote the measurement side as the label (`primary` / `secondary`) without a nominal | the Primary label is unchanged; a Secondary **sample** side no longer writes a Secondary **base** label (§9) |
| Auto-base **Secondary path** | wrote a legacy `secondary` declaration **and** a stored secondary base (the VT winding value) | **changed by Amendment 1 (W-1, §9):** no legacy base is created for Secondary samples; existing ones are preserved |
| API consumers | `base_reference_side` accepted and stored | unchanged (D-8) |

## 4. Verification against the 13 required demonstrations

| # | Required | Evidence |
|---|---|---|
| 1 | the selector is absent | static `test_the_selector_and_its_draft_state_are_gone`; browser test 1 (`toHaveCount(0)`); the three updated rd1 specs |
| 2 | a new nominal establishes a Primary base | backend `test_a_new_nominal_voltage_establishes_a_primary_base`; browser test 2 (the PUT carries `"primary"`; the stored value is `primary`, no secondary base) |
| 3 | Primary samples: correct denominator | `test_primary_samples_use_the_primary_denominator` — 158.77 / 275 = 0.57735, `verified_direct` |
| 4 | Secondary samples: derived denominator | `test_secondary_samples_use_the_derived_denominator` — 0.577345 / 0.110 = 5.2486 (`auto_nominal` r = 2500, `verified_converted`) |
| 5 | L-L / L-G | `test_line_to_ground_conversion_stays_correct` — D = 275/√3 kV: Primary 1.0, Secondary 9.0909 (= 5.2486 × √3) |
| 6 | a measurement-side change leaves the nominal base | `test_changing_the_measurement_side_never_changes_the_nominal_base` |
| 7 | a VT change refreshes PU | `test_changing_the_vt_refreshes_the_denominator_and_leaves_the_base_alone` — manual VT 275 kV : 1 kV: 0.577345 |
| 8 | existing Secondary bases unchanged | `test_an_existing_secondary_base_is_unchanged_by_unrelated_saves` (bit for bit); browser test 3 |
| 9 | historical Unknown preserved | `test_a_historical_unknown_declaration_is_preserved_by_unrelated_saves`; browser test 4; the existing S2/S4 historical-gate suites |
| 10 | unrelated saves do not overwrite legacy declarations | the same tests; static `test_the_voltage_writers_never_echo_or_default_the_side` |
| 11 | missing VT authority still refuses | `test_a_required_conversion_without_vt_authority_is_still_refused` (`vt_authority_unavailable`, ENG shown) |
| 12 | the Calculated Current side control remains | browser test 5 (`#wwCalculatedPuSide` visible in Manual); static `test_the_calculated_current_manual_base_side_control_remains` |
| 13 | auto-base writers consistent | the Primary path and, since Amendment 1, the Secondary path (§9) |

Expected values are first-principles and reuse the S1 oracle fixture values (no application arithmetic in the tests, none in the frontend).

## 5. Findings that need an owner decision

**W-1 — RESOLVED by the owner's clarification (Amendment 1, §9). The original finding:** the auto-base Secondary path was not consistent with DEC-219. For a recording whose P/S marker says Secondary, `auto_base_service` stores `base_reference_side = "secondary"` plus a stored secondary base
(the CFG VT winding value, e.g. 1.0 kV) and, when its evidence allows, a nominal. D-5 then activates the legacy path, so a **new** Secondary recording is not given "nominal = Primary base, denominator from the VT
authority". It cannot be corrected without changing numbers (D-4 / D-5): on the fixture the legacy denominator is 1.0 kV (0.5773 pu, physically right because the CFG VT is 275 : 1), whereas nominal ÷ `auto_nominal`
(110 V) gives 5.2486 unless the recording's VT metadata is first accepted as a VT authority. Options for the owner: **(A)** leave it as is (legacy declarations keep being written for new Secondary recordings; DEC-219 applies to
what the engineer configures); **(B)** the writer declares Primary and stores no secondary base, together with a decision on consuming the CFG VT ratio as `recording_metadata` authority (DEC-215) so the numbers stay physically
correct; **(C)** keep the value only as the D-4 diagnostic. I changed nothing; the test pins today's behaviour.

**W-2 — the legacy management contract (below) is not implemented.** Until it is approved, a legacy group is identified and protected from unrelated saves, and an engineer's **explicit** new or changed nominal replaces the
stored Secondary base (the existing stale-secondary rule of `voltage_group_config_service`, previously reachable through the same Apply) and declares Primary; the edit form states this before saving.

## 6. Proposed legacy replacement contract and UI (for approval — not implemented)

**Definition.** A *legacy Secondary base* is a group whose stored `base_reference_side` is `secondary` **and** whose stored `secondary_voltage_ll_v` is valid (D-5). A *historical Unknown* has a stored `unknown`. Neither is rewritten except by an explicit
per-group action; there is no bulk migration, no automatic replacement and no inference. API fields and storage are unchanged.

**Contract.**
1. **Retain** is the default and needs no action: the base is used exactly as stored (D-4 P5: a stored-versus-derived difference stays a diagnostic).
2. **Correct the stored value** (optional, only if approved): edits `secondary_voltage_ll_v` alone (positive, finite); the declaration, nominal and numbers' basis stay; a visible "Stored value changed" provenance note.
3. **Switch to the normal Primary nominal base** — an explicit, confirmed, per-group transition: the engineer enters (or confirms) the nominal kV; on confirmation the page sends `nominal_voltage_ll_kv` and `base_reference_side: "primary"`, the stored secondary base is
   removed, and the denominator becomes nominal ÷ the VT authority (manual > recording_metadata > auto_nominal). The confirmation names the consequence — *"PU values for this group will be recomputed on the nominal Primary base; current effective base 110 V, new effective base derived from 132 kV and the VT; the stored Secondary base (110 V) is removed"* — and records the previous value in the group's provenance text.
4. A historical **Unknown** group needs no action; saving a nominal establishes Primary (this decision); a group the engineer never edits keeps working exactly as before.

**UI representation (inside Recording Details → Voltage Base Configuration, no new panel):**

```
Voltage Base Configuration                                     [Edit]
 Nominal voltage (L-L)   132 kV            Voltage reference  Line-to-ground
 Legacy Secondary base   110 V (L-L), Secondary — kept as stored        <- implemented (read-only)
 Used as stored; it is unchanged unless the nominal voltage is changed.
 [ Manage legacy base ▾ ]                                               <- proposed, legacy groups only
     Keep as stored (no change)
     Correct stored value…            (only if approved)
     Switch to the nominal Primary base…   -> confirm dialog stating the consequence above
```

Decisions requested: approve the contract (retain / correct / explicit transition), whether "Correct stored value" is wanted, and W-1 (A, B or C).

## 7. Limitations

* Only the Recording Details Voltage selector is retired (DEC-219 scope); the Calculated Current side control stays. API fields are unchanged; the auto-base writer is aligned by Amendment 1 (§9).
* The legacy management action (§6) awaits the owner; W-1 is resolved (§9).
* No full regression was run for this initial UI change (as instructed); targeted results are in §8.

## 8. Targeted regression results

Targeted only (the full S1–S6 regression was not repeated, as instructed); every figure below is measured.

| Suite | Result |
|---|---|
| Backend — PU, per-unit, Measurement Group, auto-base, Recording Details, side/ratio authority and every `test_frontend_*` static file (5,258 tests, 646 s) | **0 failed, 0 errors, 5 skipped** (the 5 pre-existing PU skips). Includes the 13 new API tests and the 6 new static guards; every S1–S6 suite, the 108-case historical-gate oracle and the S4 oracle integration pass unmodified |
| Static frontend subset of that run (`test_frontend_*`) | 2,254 tests (2,248 before + 6 new), 0 failed |
| Browser — 30 spec files: the four Recording Details D2 specs and the other `rd1-*` specs, `d5a_ui_002_group_details`, the new Voltage spec, the S5 spec, calculated-Current manual PU, the per-unit reference-safety / eligibility / atomic-update / display-synchronisation / numeric-integrity specs, voltage-only PU display, line-to-line, auto-PU import, current common base (1 worker, `BEN5K_EXPERIMENTAL_ENABLED=1`, 13.5 min) | **324 passed, 0 failed** |
| New Voltage spec after strengthening (3 consecutive runs) | 15 / 15 |
| Mutation — 5 static + 4 browser | **all killed** (FM1 never declares Primary; FM2 declares Primary on every save; FM3 the Unknown echo returns; FM4 the unchanged nominal is always re-sent; FM5 the legacy note removed). FM4 first **survived** the browser spec (its legacy group had no nominal), so that test now uses the realistic legacy group (nominal + stored secondary base) and FM4 is killed by two tests |

Not run (not authorised for this change): the full backend suite, the full browser suite, the BEN owner-reference suites. The browser runs regenerate seven tracked evidence screenshots (`rd1-d2-refine/*`, `recording-details-toolbar/*`) as a known side effect; they were restored and are not part of any commit.


## 9. W-1 resolution — the automatic base service follows DEC-219 (Amendment 1, 2026-11-27)

Owner clarification: DEC-215 is retained (auto VT primary = nominal system voltage, auto VT secondary = 110 V L-L, Manual VT override through the existing configuration); no new VT or CFG
authority. The change is confined to `backend/app/services/auto_base_service.py`:

| Case | Before | After |
|---|---|---|
| New recording with **Secondary samples** | a legacy `secondary` declaration + a stored `secondary_voltage_ll_v` (the CFG winding value, e.g. 1000 V) per group; PU available at once | **no** Secondary declaration, **no** stored secondary value; the group is `needs_review` (the CFG winding rating of a Secondary recording is only a low-confidence candidate, C2) until the engineer enters the nominal; then Primary base + the shared VT authority |
| Evidence supports a nominal for Secondary samples | (path unreachable in practice) | nominal written as the **Primary** base, no secondary base |
| Primary recording | nominal + `primary` | unchanged (tested) |
| Insufficient evidence, Secondary samples | wrote the label `secondary` | writes no base side |
| **Existing** group with a stored Secondary declaration (auto, re-run or membership change) | re-evaluated and rewritten | **skipped** (`skipped_legacy_secondary`): nothing migrated, refreshed or demoted |
| Manual / legacy-manual authority | never overwritten (C4) | unchanged |

**Checks the owner asked for.** No authoritative metadata is discarded: the CFG VT ratio stays on the immutable recording channels (`primary_ratio` / `secondary_ratio`); the stored secondary value was never read by any
consumer except the PU base resolver and the D-4 diagnostic (verified by search), so no other consumer loses data; no `recording_metadata` VT authority existed to be preserved (nothing in the code stores one, so no
precedence is altered); no protected historical configuration is changed (guarded and tested).

**Fixture verification — numerical vs physical correctness** (nominal 275 kV, line-to-line base, Secondary peak 0.577345 kV, `synth_measurement_groups`):

| VT configuration | Ratio r | Denominator D = nominal / r | PU peak | Numerically correct for the configured ratio | Physically correct |
|---|---|---|---|---|---|
| Auto VT 275 kV : 110 V (DEC-215 default) | 2500 | 0.110 kV | **5.2486** | yes | **only if the equipment really is 2500 : 1** — the fixture's real VT is 275 : 1, so this reads 9.0909 × high |
| Manual VT 275 kV : 1000 V (the fixture's real VT) | 275 | 1.000 kV | **0.577345** | yes | **yes** — equals the Primary recording of the same condition, 158.77 / 275 = 0.57735 (1e-5; the CFG rounds a to six digits) |

The 110 V auto default is a configured default, not a measurement; the engineer overrides it through the existing Manual VT when the real ratio differs. Tests: `test_pu_dec219_auto_base_w1.py` (11).

**Consequence to know.** For a **new** Secondary recording the group no longer arrives with an automatically available PU (it did, via the legacy base, before): the engineer enters the nominal voltage in Recording Details
(the existing "Nominal voltage is required for voltage per-unit calculation" prompt), after which PU follows the Auto or Manual VT. Existing legacy groups are unaffected.

**Existing tests superseded (policy-bearing, updated with this record):** three Slice 5D-3 tests that asserted the automatic legacy Secondary base (`TestAT2SecondaryComtrade`, `TestAT9MixedPrimarySecondaryGroups`,
`TestAT15NumericalPuEquivalence`) now assert the DEC-219 contract with first-principles values for both VTs; the interim "pinned deviation" test of §4 is replaced by `test_pu_dec219_auto_base_w1.py`.


## 10. W-1 targeted regression results (measured; the full PU migration regression was not repeated)

| Suite | Result |
|---|---|
| New W-1 tests (`test_pu_dec219_auto_base_w1.py`) | 11 / 11: no legacy base for Secondary samples; Primary recordings unchanged; the CFG ratio is not made an authority; Auto VT 5.2486 and Manual VT 0.577345 (numerical, configured ratio); Primary ≡ Secondary-with-Manual-VT (1e-5) and the Auto/Manual ratio 2500 / 275; legacy bases survive a service re-run and a membership change; an engineer-set Secondary base is never overwritten; a missing VT authority still refuses |
| Backend — PU, per-unit, Measurement Group, auto-base, side / VT authority, Recording Details and every `test_frontend_*` file (5,482 tests, 544 s) | **0 failed, 0 errors, 5 skipped** (the pre-existing PU skips); includes the three updated Slice 5D-3 tests, the retirement tests and the S1–S6 suites unmodified |
| Browser — 18 spec files (auto-PU import, the Recording Details D2/D4/C-slice specs, the DEC-219 Voltage spec, the S5 spec, per-unit reference-safety / eligibility, voltage-only PU, group details, line-to-line, calculated-Current manual PU; 1 worker) | **209 passed, 0 failed** (8.1 min) |
| Mutation — 3 writer mutants | **all killed** (legacy Secondary base re-created → 5 tests fail; the legacy-skip guard removed → 2 fail; the insufficient path declaring Secondary again → 3 fail) |

Not run (not authorised for this change): the full backend and full browser suites. The browser runs regenerate seven tracked evidence screenshots as a known side effect; they were restored and are not part of the commit.
