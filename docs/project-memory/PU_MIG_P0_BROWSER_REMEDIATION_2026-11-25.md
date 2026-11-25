# PU-MIG P0 — browser-test remediation (2026-11-25)

Branch `feature/pu-mig-s1-pure-denominator-resolver` (worktree `.local-data/pu-mig-s1`), on top of the accepted S1
commits `e41aecd`, `b055ba4`, `993cf89` (all preserved). Authority: owner message "PU Migration — P0 Remediation
Authorisation" (2026-11-25), which authorises browser-test code, test helpers, test-environment configuration and
documentation only. **No production file is changed. S2 is not started. Nothing is pushed, merged or deployed.**

Companion records: `PU_MIG_S0_OWNER_REVIEW_RESPONSE_2026-11-24.md` §6 (the P0 plan),
`BACKLOG_CSV_EXCEL_PREPARATION_ROWS_IN_RECORDING_DETAILS_2026-11-25.md` (deferred item).

## 1. BEN5K test-environment configuration

`browser-tests/playwright.config.js`: the Playwright `webServer` backend now starts with
`BEN5K_EXPERIMENTAL_ENABLED=1` (`env: { STORAGE_PATH, BEN5K_EXPERIMENTAL_ENABLED: "1" }`). It is a test-process
setting only; no production or DEV runtime setting, Dockerfile, workflow or `backend/app` file changed. Without the
flag the backend refuses BEN uploads ("This BEN file uses a BEN layout that is not currently supported",
`import_service.py:256`), so 18 tests failed for environment reasons and 16 BEN5K tests skipped. A server that is
already running is reused by Playwright (`reuseExistingServer`); such a server must itself be started with the flag.
No skip condition was added anywhere.

## 2. Files changed (commits `07cbaaa`, `d122037`, and this document)

Only `browser-tests/**` and `docs/project-memory/**`. New helper `support/recording_details_pu_helpers.js`
(`openRdGroupDetails`, `openRdVoltageEditor`, `openRdCurrentEditor`; recordings and groups are located by
`data-source-id` / `data-group-id`, never by position). `support/event_reconstruction_helpers.js::uploadRecord` now
opens Recording Details first (upload exists only there). Every other change is inside a spec file.

## 3. PU atomicity and numerical-integrity coverage (real backend)

`per-unit-atomic-updates.spec.js` (1 test) and `per-unit-numeric-integrity.spec.js` (4 original + 2 added) drive the
Recording Details voltage editor (`#wwRdVoltageEditBtn` / `#wwRdVltKv` / `#wwRdVoltageApplyBtn`) against the real
backend. Every original engineering assertion is character-identical: initial PU peak √2; accepted base; the
real backend rejection (400 for an incomplete manual reference and for an overflowing SI base, 422 for the two
non-numeric bodies); unchanged group configuration, PU waveform, provenance and displayed array after rejection;
recovery through a later valid save (peak √2·275/132); the tiny-base `base_required` fallback in Waveform and ER and
its recovery. Only the checks "drawer is open / closed" became "editor form present / absent plus
`.ww-rd-edit-error` visible". The request is altered on the wire (`page.route` + `route.continue`) exactly as
before; no response or state is mocked.

Frontend validation and backend rejection are separate responsibilities: two added tests fill `0` and `-5`,
assert the editor error text contains "positive number", assert that **no** `PUT …/voltage-config` request was sent
and that the API group, the PU waveform and the displayed PU state are unchanged.

Anti-vacuity (mutation): removing the PU refresh from `wwRdVoltageApply` in a scratch copy of the frontend makes
7 of these ports fail (atomic-updates, 3 numeric-integrity rejection tests, display-synchronization "real Voltage
Group save", PULU-07, PULU-08).

## 4. Tier-1 / Tier-1b disposition

Legend: PORT = same intention and assertions through the current UI; RE-HOME = the editor no longer exists, the
same real endpoint it called is used and every numerical / provenance / atomicity assertion is kept; PENDING = left
unchanged and failing, because the original assertion concerns a deliberately retired surface with no equivalent
(owner decision requested, §7).

| Spec | Disposition |
|---|---|
| per-unit-atomic-updates, per-unit-numeric-integrity | PORT (+2 added), §3 |
| per-unit-display-synchronization | 153 PORT (Recording Details editor); 177 RE-HOME (Source Default endpoint + the refresh the editor ran); 139/240/281: the held request `GET /per-unit/sources` no longer exists (be1e7e0), so the same race is held on the PU responses that remain (PU cursor values / PU waveform); 362 upload helper |
| pulu-auto-reference | PULU-07/08 PORT (Recording Details editor); PULU-09/08/07: no pane exists before a channel is shown, so the mode itself (`ww.unitMode`, `wwApplyUnitMode`) is asserted/selected |
| voltage-only-pu-display | VD-10, VD-15, VD-16 PORT (VD-15's conditional `if` removed: the group and its 275 kV are now required); VD-09 PENDING |
| per-unit-eligibility | PORT (coverage table → channel Per-unit dialog "Needs configuration"; the API coverage assertion is unchanged) |
| per-unit-reference-safety | 231 PORT (editor offers only equipment-rating controls); 265 PENDING |
| source-default-current-preview | RE-HOME: derived kA agrees with five independent values incl. extremes; unusable bases rejected with the backend's own message; configuration preserved; nominal L-L base unchanged across references |
| current-common-base | RE-HOME: same `PUT …/current-config` and `PUT /per-unit/sources/{id}` bodies the retired editors sent + `wwRefreshDisplayedChannelsForPerUnitChange`; all numeric/provenance/atomic assertions kept |
| compliance_measurement (2), compliance_readiness (1) | PORT: the Measurement Groups overlay/drawer were replaced by a redirect to Recording Details (4161a63); "never a navigation" is therefore reversed by that approved change |
| waveform-measurement-values, phasor_analysis, BEN/ASCII specs | navigation (§5); ben5k-*-pu-gate: mode selected before any pane exists |

Not ported, because no surface exists (PU-UI-001, commits 1c60a1e, 4161a63, be1e7e0): the live "calculated current
base" preview field and its comparison with the backend, the drawer/editor visible-error elements, the Cancel/Close
controls, the explanatory DEC-212 note text, `wwPerUnitEditorResolvedCurrentBaseText()` (removed with the editor).
Each is listed for owner confirmation in §7.

## 5. Navigation

Selecting a recording in Recording Details only selects it. `#mainNavWaveformBtn` is clicked after the selection in the
18 experimentally validated specs plus `phasor_analysis`, `waveform-measurement-values`, `ben5k-gpth-uat`,
`ben5k-permas-jaya-uat`, `comtrade-ascii-missing-data` and `ben5k-timezone` (same root cause confirmed by the run).
Different causes, handled separately: upload helper (upload exists only on Recording Details); `waveform-auto-fit-range`
needs the real "open for analysis" action, Recording Details' **View Waveform** (`openRecordingForAnalysis`), which is
also what establishes a source's own initial bounds; tests that set the mode before any pane exists.

## 6. Obsolete UI assertions

* `playback.spec.js` Autoscale Y: `#wwAutoscaleYBtn` was removed from the page toolbar by WUI-001 (3ed200c);
  the equivalent is the pane header's `[data-pane-y="auto"]`, now asserted visible in the Time Group canvas.
* `waveform-auto-fit-range.spec.js`: **not** superseded. DEC-037's 2026-09-10 Update (owner UAT + hardening, commit
  `4ee0bee`) explicitly preserves the zero-channel source case that this step asserts. The failure was the open
  action (see §5); the assertion is unchanged.
* `smoke.spec.js` Smoke D: `.ww-tg-toolbar-row` still exists but its controls moved to `#wwToolbar` (DEC-158), so the row
  is collapsed (not "visible"). The step now asserts the canvas header is visible, the row is attached, `#wwToolbar`
  is visible and `#wwZoomXInBtn` is enabled for the Time Group.
* VD-09, VD-10, VD-15, VD-16: see §4 and §7.

## 7. Items needing an owner decision

1. **VD-09** ("MG modal shows the DEC-212 note in Current Groups") and **per-unit-reference-safety:265** ("MG drawer
   shows Legacy Current Reference") assert surfaces removed by 4161a63 with no Recording Details equivalent; the
   engineering behaviour they accompany (Current always engineering, VD-04/05/07/13/17) is covered by passing tests.
   Recommendation: retire both. They are left unchanged and failing until approved.
2. Recording Details has **no editor for a Current group's manual Ibase or Base reference side**, and the Source Default
   editor is gone, although the backend endpoints and PU resolution for them remain (DEC-212 §5, be1e7e0). Those
   settings can no longer be viewed or changed in the UI. Relevant to S2 planning (D-series current-base decisions).
3. Confirm the dropped UI-only assertions listed at the end of §4.

## 8. Impedance Locus and Distance Protection — the six `post_upload_readiness` tests

Fixtures `phasor_smoke_three_phase`, `mixed_capability_multibay`, `representation_eligibility_multibay`,
`disturbance_record_multibay`: every Voltage and Current channel declares **Primary** (`P`) in the CFG; none carries a
VT/CT, nominal voltage or any ratio. The analyzers default the requested output side (`impedance_basis`) to
**Secondary**. Measured through `GET …/protection-recorded-input` on the real backend (scratch probe, repository untouched):

| Quantity | Authoritative sample side | Requested side | Conversion | Authority available | Result |
|---|---|---|---|---|---|
| Voltage | Primary (`recording_channel_declared`) | Secondary | required (`ratio_required: true`) | no VT (no nominal voltage, no VT) | `vt_authority_unavailable` — "VT is not configured for '<bay> VOLTAGE'" |
| Current | Primary (`recording_channel_declared`) | Secondary | required | no CT | not reached (voltage is evaluated first) |
| both | Primary | **Primary** | none (`ratio_required: false`) | n/a | ready, "The recorded input is ready." |

Classification: **C — correct refusal under the existing approved measurement-side policy**, and the change that
caused the tests to fail is **D — intentional and approved**: DEC-216 Amendment 6 (D5A-2B2C-1B): "A ratio only where
a conversion needs it. A quantity already on the output side needs no VT/CT, even when none exists… Missing / invalid
… → blocked with `vt_authority_unavailable` / `ct_authority_unavailable`" and "the old 'choose an unverified basis in
the analyzer' path is gone". The engineering principle the owner asked to assess (no ratio solely for conversion when
the sides match) is already implemented and verified (rows 3). It is not B (no unnecessary prerequisite) and not E.
The fixtures are outdated for the approved workflow (class A), not the product.

Correction (tests only): the six tests request the recorded Primary side (`#wwImpedanceOutputBasisSelect` /
`#wwDistanceOutputBasisSelect` = primary) and then assert exactly what they asserted before. No safeguard is weakened
or bypassed: the refusal itself stays covered by `d5a_2b2c_1b_protection_side.spec.js` (passing), which also proves a
nominal-only VT and a manual VT/CT are consumed correctly. The two companion tests of the same families that already
failed on `3ed200c` (357, 688) now also pass.

Four Overcurrent tests in the same file (204, 343, 511, 661) fail identically on `3ed200c` and here and are **not**
caused by this work. Probe result (same method): Overcurrent works in secondary current (`pickup_current_secondary`);
the Primary-declared current needs a CT (`ct.status: not_configured`, `invalid_ct_values`, "CT is not configured for
the Current Measurement Group …") — class C under D5A-2B2C-1A. They are left as documented backlog (a CT of 1:1 or a
real CT through the API would restore them); they do not involve per-unit.

## 9. Application defects found (production unchanged)

1. **Compliance → Configure Base loses the pre-selected group.** `wwComplianceOpenConfigureBase()` →
   `wwNavigateToRdForGroup(sourceId, groupId)` sets `wwRdState.selectedGroupId`, but `wwRdOnPageEntered()` calls
   `wwRdSelectSource(sourceId)` when `ww.measurementGroups` has no entry for that source, and `wwRdSelectSource`
   resets `selectedGroupId = null`. Observed on a fresh workspace (Compliance visited before Waveform). Proposed minimal
   correction (not applied): let `wwRdSelectSource` keep a group id supplied by the navigation. The original assertion is
   kept, unchanged, in its own test (`compliance_readiness.spec.js`, "Configure Base opens Recording Details with the
   selected group pre-selected") and currently fails; the companion test selects the group explicitly and passes.
   Pre-existing in `3ed200c`.
2. CSV/Excel preparation rows are not listed in Recording Details — deferred, see the backlog record.
3. RD has no Current manual-Ibase / base-reference-side / Source Default surface — see §7.2.

## 10. Results

### 10.1 Complete flagged suite (one run, `BEN5K_EXPERIMENTAL_ENABLED=1`, one worker, commit `07cbaaa`)

| | Baseline P0 (993cf89, flag off) | Remediated (flag on) |
|---|---|---|
| Tests | 1,808 | 1,811 |
| Passed | 1,624 | **1,783** |
| Failed | 168 | **20** |
| Skipped | 16 | **8** |
| Duration | 3.9 h | 1.5 h |

Individual identities (file + title; line numbers shift in edited specs) compared with the baseline run:
**0 regressions (no test that passed before fails now)**; 1,624 passed-before tests still pass; 133 of the 168
baseline failures now pass; 8 of the 16 baseline skips now run and pass (the flag); 19 baseline failures remain.
Retired/renamed (16 baseline ids, all ported, §4) and added (19 ids): the two added browser-validation tests
(`0`, `-5`), the split Configure Base test (one pinned-defect test + the passing save test) and the renamed ports of
the retired Source Default / drawer tests. Net +3 tests.

After that run, the test-only edits of commit `d122037` were verified by targeted runs, not by a second full
run (as instructed): `calculated-channel-preview.spec.js` (5 tests, 5 pass) and the three owner-data specs
(`ben5k-bphe-layout`, `ben5k-gpth-slow`, `ben5k-physical-mapping`). The 8 remaining skips are those four owner-data
specs' tests: they skip, unchanged and by their own pre-existing condition, unless `GPTH_BEN_PATH`, `PERMAS_BEN_PATH`,
`BPHE_BEN_PATH`, `GPTH_SLOW_BEN_PATH` point at the owner recordings. With the recordings on this machine
(`D:\OneDrive - Tenaga Nasional Berhad\WorkFiles\Tripping Event`) all 8 run and **pass** (targeted run). On
that basis the corrected-tree expectation is 15 failures, but the measured full-run figure is the 20 above.

### 10.2 Every remaining failure (20 measured; the first 5 were fixed afterwards)

| # | Tests | Class | Relevant to S2? |
|---|---|---|---|
| 5 | `calculated-channel-preview` ×5 | obsolete global ENG selector before any pane exists — **fixed after the run**, 5/5 pass | no |
| 6 | CSV/Excel preparation rows missing from Recording Details: `data-issues-estimate-fill` ×2, `data-issues-panel` ×2, `data-preparation-sticky-header` ×1, `sampling-rate-format` ×1 | deferred backlog item (pre-existing, identical on 3ed200c) | no |
| 4 | `post_upload_readiness` Overcurrent ×4 (204/343/511/661 before edits) | pre-existing, identical on 3ed200c; correct CT refusal (§8) | no — not per-unit |
| 2 | `waveform-top-toolbar-migration` "Per-Unit Settings icon" ×2 | assert the retired Settings Hub button/asset (`#wwOpenPerUnitSettingsBtn`, `pu_settings.svg`, 1c60a1e); retirement decision requested | no |
| 1 | `voltage-only-pu-display` VD-09 | PENDING owner retirement (§7.1) | no (behaviour covered) |
| 1 | `per-unit-reference-safety` "Legacy Current Reference" | PENDING owner retirement (§7.1) | see §7.2 |
| 1 | `compliance_readiness` "Configure Base … pre-selected" | genuine application defect, original assertion pinned (§9.1) | no |

No remaining failure involves the PU base/atomicity/numerical path, the real-backend rejection path, the voltage or
current base editors, ENG/PU switching, cursors, annotations or Event Reconstruction PU. There is no new relevant
failure that is unexplained.

### 10.3 S2 gate checklist

* Real-backend PU atomicity coverage restored — yes (§3, mutation-proven).
* PU numerical-integrity coverage restored — yes (§3).
* Relevant Recording Details regression coverage restored — yes (§4); Compliance → Recording Details hand-off covered.
* Measurement-side and base-configuration safeguards covered — the side/VT/CT refusal and conversion specs
  (`d5a_2b2c_1b_protection_side`, `d5a_2b2c_1a_overcurrent_side`, `d5a_ui_002_group_details`) pass unchanged; base
  rejection/atomicity/numeric specs pass.
* Tier-1 / Tier-1b failures resolved or explicitly dispositioned — resolved except the two PENDING retirements.
* Impedance/Distance differences technically explained — yes (§8).
* No unexplained relevant failure — yes.

Open S2-relevant caveat (not a test failure): §7.2 — no UI edits a Current group's manual Ibase / base reference side
or a Source Default, while the backend still honours them. Coverage of that behaviour is now API-driven.


## 11. Protected production-file integrity

`git diff --name-only 993cf89 HEAD`: only `browser-tests/**` and `docs/project-memory/**` files. No file under
`backend/`, `frontend/`, `.github/` or any Dockerfile/compose file is modified; the S1 domain module
`backend/app/domain/side_denominator.py` and its tests are untouched; `resolve_side_denominator()` is still wired to
nothing. S1 commits `e41aecd`, `b055ba4`, `993cf89` are preserved (this work sits on top). Test-generated tracked
evidence images (`docs/project-memory/evidence/rd1-d2-refine/*`, `…/recording-details-toolbar/*`) were rewritten by
the full run and restored with `git checkout --`.

## 12. P0 closeout (owner decisions of 2026-11-25)

Owner decisions applied: (1) VD-09 and the Legacy Current Reference test retired; (2) the two Per-Unit Settings icon tests
retired; (3) minimal production fix for Compliance → Configure Base; (4) API-level coverage retained for Current-group
manual Ibase / base reference side / Source Default, UI not restored (not an independent S2 blocker); (5) the dropped
UI-only assertions of §4 accepted; (6) the four Overcurrent tests corrected with a valid manual CT; (7) CSV/Excel row failures
stay deferred; (8) BEN5K timezone remediation and the relay-import instability classification accepted.

| Item | Change | Commit |
|---|---|---|
| Production fix | `wwRdOnPageEntered()` keeps the group pre-selected by `wwNavigateToRdForGroup` once the source's groups have loaded (and only if it belongs to that source). `wwRdSelectSource()` and every click path are unchanged. 13 lines in `frontend/index.html`. Other worktrees (wui-001..004, d5a-1b-on-wui, rms-r0, nf-2, nf-3d) were inspected read-only: none touches these lines, so a merge conflict is unlikely and would be local. | `a328ff2` (alone) |
| Retirements | VD-09, "Legacy Current Reference", and the two "Per-Unit Settings icon" tests removed; each site keeps a `RETIRED (owner decision …)` note with the reason. Engineering behaviour stays covered: VD-03…08/13/17, `per-unit-reference-safety`, `current-common-base` (API-level). | `abe2a7e` |
| Overcurrent | The four `post_upload_readiness` Overcurrent tests call `configureCurrentGroupCts()`: `PUT …/measurement-groups/{id}/current-config {update_ct_only, ct_primary_a: 1200, ct_secondary_a: 1}` — the endpoint Recording Details' CT editor saves to — for the uploaded recording's Current groups. Production Overcurrent is untouched; the missing-CT refusal remains covered by `d5a_2b2c_1a_overcurrent_side.spec.js` (not modified, passing). Impedance/Distance tests are unchanged (no CT configured), so "no ratio needed on the same side" stays proven. | `abe2a7e` |

Targeted run (one worker, flag on; **not** the full suite): `compliance_readiness`, `compliance_measurement`,
`post_upload_readiness`, `d5a_2b2c_1a_overcurrent_side`, `d5a_2b2c_1b_protection_side`, `d5a_ui_002_group_details`,
`per-unit-reference-safety`, `voltage-only-pu-display`, `waveform-top-toolbar-migration`, `pulu-auto-reference`,
`per-unit-atomic-updates`, `per-unit-numeric-integrity`: **187 passed, 0 failed** (14.6 min), including the pinned
"Configure Base … pre-selected" test, which failed before the fix and now passes unchanged, all four Overcurrent tests,
and the missing-CT refusal tests. Static frontend tests touching Recording Details (58) pass.

Derived state of the suite (not a measured full run): of the 20 failures measured at `07cbaaa`, 5 were fixed in `d122037`,
1 by `a328ff2`, 4 by the CT correction and 4 were retired, leaving the **6 CSV/Excel preparation-row failures** (deferred
backlog). Expected totals 1,807 tests = 1,793 passed + 6 failed + 8 skipped (owner-data skips, which pass when the
reference-data variables are set).

### 12.1 Decision register for the remaining PU-MIG decisions

Source: `PU_MIG_S0_OWNER_REVIEW_RESPONSE_2026-11-24.md` §1.2, `PU_MIG_S0_GOVERNANCE_CORRECTION_2026-11-24.md` (status
column), `PU_MIG_S0_FINAL_RECONCILIATION_2026-11-24.md` (slice table: "S2 … needs S1, R-4/R-5/R-6/R-7, P0"). All are
PENDING/OPEN; none is decided by this work. "Needed before S2" is read from those documents.

| ID | Question | Status | Options (recommendation in the documents) | Needed before S2? |
|---|---|---|---|---|
| **D-1** (OD-2) | Historical Unknown/Unverified PU, per class | OPEN — must not be silently changed nor shown as verified | R / **R+** (recommended: keep numbers, add an explicit verification state) / N / B | **Yes for raw Voltage** (S2's class): choose R or R+ (and whether N at S2). Other classes can follow at S3/S4. |
| **D-4** (R-4) | Precedence between `secondary_voltage_ll_v` and nominal ÷ ratio | OPEN — "legacy always wins" not approvable | P1–P5; **P5 now, P4 later** (needs a `secondary_base_origin` field) | **Yes** (named S2 dependency). P5 keeps S2 numerics unchanged. |
| **D-5** (R-5) | What activates the legacy secondary path | PENDING | (i) stored `base_reference_side == "secondary"` + valid value (recommended through S4) / (ii) effective Recording Details side | **Yes** (named S2 dependency). |
| **D-6** (R-6) | Primary samples against a Secondary-only base | PENDING (was wrongly shown approved in Amendment 7; corrected GC-1) | convert only with a valid trusted ratio, else block (recommended) / keep blocked | **Yes** (named S2 dependency). |
| **D-7** (R-7) | `auto_nominal` ratio for secondary PU | PENDING | accept + show provenance (recommended; DEC-215) / require manual or recording metadata | **Yes** (named S2 dependency). |
| **D-8** (R-8) | API deprecation of `*_base_reference_side` | PENDING | none through S4 (recommended) / deprecate; revisit at S6 | **No** — follows D-2; revisit at S6. |
| **N-2** | Reason-code vocabulary | PENDING — every S1 reason code is a proposal | A: reuse existing names + add `base_side_unknown`, `invalid_base_*`, `denominator_not_representable` (recommended) / B: separate PU namespace | **Yes, before any production consumer calls the resolver** (S2 is the first); production refusal codes must not be finalised without it. |

Not in the list but relevant to S2: D-9 (refresh scope per source; oracle placement) was approved on 2026-11-24. §7.2 of
this document (no UI for Current-group manual Ibase / base reference side / Source Default) was accepted as not an
independent S2 blocker; API-level coverage is retained.

### 12.2 P0 readiness verdict

All P0 acceptance gates of §10.3 are met and every item the owner dispositioned is closed. **P0 is complete.** The only
remaining browser failures are the 6 deferred CSV/Excel preparation-row tests, which have no per-unit dependency.
**S2 is not started.** What stands between P0 and S2 is the decision register above: D-1 (raw Voltage), D-4, D-5, D-6, D-7
and N-2 need an owner decision first; D-8 does not.

