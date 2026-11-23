# D5A-2B2C-1A — Recorded Overcurrent consumes the unified measurement side

**Branch:** `feature/d5a-2b2c-1a-overcurrent-unified-side`, from the DEV-UAT-approved `ad1b6ed` (`uat/dev-d5a-20261121`). **Not pushed, merged or deployed.**
Authority: [DEC-216](DECISIONS.md#dec-216--recording-details-is-the-single-authority-for-recorded-measurement-side-d5a-2b2-unified-model) Amendments 4 and 5.
Scope: recorded Overcurrent only. PU, Impedance Locus, Distance Protection, calculated channels, D5A-2B2C-1B, D5A-2B2D and the PU migration are **not** touched. The numeric engine
(`convert_to_relay_secondary`, RMS window, IDMT, pickup, above-pickup duration) is unchanged.

## 1. Data flow before and after

| Step | Before (`ad1b6ed`) | After |
|---|---|---|
| Who decided Primary/Secondary | The engineer, with a `Recording current basis` select in the page (pre-selected from the channel's declared side; "unverified" when undeclared). | **Recording Details**: `resolve_effective_measurement_side()` of the consumed Current channel — Level 2 Current-group setting > Level 1 recording correction > the channel's own declaration > inferred default (not strict-usable) > unresolved. |
| Who decided the CT | The page read `protection-instrument-context?analysis=overcurrent` and sent `ct_primary`/`ct_secondary` as request parameters. | The **backend**: the CT of the Measurement Group that owns the consumed channel, read inside the calculation. |
| Request | `recording_basis` (required) + `ct_*` for a Primary recording. | `phase`, `analysis_time`, `characteristic_id`, `tms`, `pickup_current_secondary` only. |
| Side check | Page only (a contradiction withheld the number client-side); a direct API client could request the wrong basis and get a wrong number. | **Backend**, for every client (below). |
| What the page shows | Select + read-only CT. | Read-only block: **Side** (with provenance and a link), **CT** (with its group), blockers/notes. |
| Freshness | Report re-read on context (re)load / phase / basis change. | Same triggers (no basis), plus the result is withheld while the read is in flight; the analysis is requested again only when the answer changes what the backend computes from. |
| Stateless? | n/a | Yes — the resolver caches nothing, so a Level 1 or group change reaches the very next request; an unrelated Voltage group changes nothing. |

## 2. Backend enforcement and legacy API compatibility

New module `app/services/overcurrent_recorded_input.py` (`evaluate_recorded_current_authority`), used by **both** `compute_overcurrent_analysis` and the new read-only report, so the page and the
calculation cannot disagree. `compute_overcurrent_analysis(..., authority=...)` takes the registries as a **required** argument: no code path can skip the authority.

| Request | Recording Details says | Result |
|---|---|---|
| no `recording_basis`, no CT | Primary + CT of the channel's group | `computed`, converted **once**: `I × CTs/CTp` |
| none | Secondary | `computed`, **never** converted (CT not needed, none applied) |
| none | side unresolved | `needs_configuration` / `measurement_side_unresolved` (no number; a magnitude or CT ratio never decides it) |
| none | side only inferred from sibling channels | `measurement_side_inferred` |
| none | the channel's Current group declares mixed sides | `measurement_side_conflict` (until the engineer chooses the group's side) |
| none | Primary, no usable CT in the channel's **own** group (or no group) | `invalid_ct_values`, message names the group |
| none | calculated current channel | `calculated_channel_side_unavailable` (deferred, see §8) |
| `recording_basis` = the side | any usable | accepted, same as no basis |
| `recording_basis` ≠ the side | any usable | **blocked**: `recording_basis_contradicts_measurement_side` |
| `recording_basis` not primary/secondary | — | `invalid_recording_basis` (before any resolution, as before) |
| `ct_*` with the same ratio as the group's (e.g. 200:1 vs 1000:5) | Primary | accepted; the **group's** CT is what is applied |
| `ct_*` with a different ratio | Primary | **blocked**: `request_ct_differs_from_authority` |
| partial / zero / negative `ct_*` | Primary | `invalid_ct_values` |
| any `ct_*` | Secondary | ignored (never applied) |
| `ct_*` given but the group has no CT | Primary | `invalid_ct_values` — a request CT cannot stand in for Recording Details |
| unknown Engineering Context | — | **404** for every request (a Primary request without a CT used to answer `200 invalid_ct_values` because the CT check ran before resolution) |

An engineer's explicit Level 1 / Level 2 correction of an incorrect COMTRADE declaration is authoritative and consumable: the result carries `measurement_side_authority`
(`engineer_recording_correction` / `engineer_group_override`), the report carries `declared_side` and the `…OVERRIDES_DECLARATION` warning, and nothing is silently dropped.
Every configuration block keeps `channel_ref` and the unit, so Related Waveforms stay available (D5A-OC-001 behaviour preserved).

Order inside the calculation: settings → resolver → channel read → reference frequency → waveform-form eligibility → **side/CT authority** → RMS. The authority check follows the
eligibility check so `analysis-input-readiness` still predicts the calculation's rejection reason for identity/representation problems.

API additions (additive): `GET .../engineering-contexts/{id}/overcurrent-recorded-input?phase=A|B|C` (channel, group, side with provenance, CT, `conversion`, blocker);
`measurement_side`, `measurement_side_authority`, `measurement_group_id`, `ct_authority` on the result. `recording_basis` in the result is the effective side used;
`ct_primary`/`ct_secondary` are the CT **applied** (null when none was).

## 3. Frontend (`frontend/index.html`, `D5A-2B2C-1A-BLOCK`)

* The `Recording current basis` field and select are gone. `#wwOvercurrentCtVtAuthority` shows, read-only and in the existing compact typography: **Side** (`Primary (declared by the recording)` /
  `set by engineer for <group>` / `set by engineer for the recording` / `inferred from the recording` / `not defined`), **CT** (`1200 A / 1 A (Manual, <group>)`, `not applied to a Secondary current`, `not needed for a Secondary current`,
  `not configured`), the backend's blocker text, the non-blocking override disclosure, and **Configure in Recording Details** (opens the owning group; the recording's groups are read first so the group stays selected).
* The request carries no basis and no CT. A result is withheld (never shown stale) while the read is in flight, when it failed, and whenever the backend reports a blocker; Related Waveforms stay available.
* A workspace reset clears the report, any read in flight and the Manual CT. Reads are keyed by workspace/context/phase and discarded when superseded or when the workspace changed.
* **Manual input source** and its CT/basis inputs are unchanged. The shared CT/VT block now serves Impedance and Distance only (the `strictSides` branches that only Overcurrent used were removed; their behaviour is unchanged).

## 4. Mathematics and numerical oracles (hand-derived, never read back from the code)

`Irelay = Irec × CTs/CTp` (Primary) or `Irec` (Secondary); IEC standard inverse, TMS 0.1, pickup 1.0 A: `t = 0.1 × 0.14 / (M^0.02 − 1)`.

| Case | Recorded | CT (group) | Relay-secondary | Test |
|---|---|---|---|---|
| Primary with CT | 400 A | 1000:5 | **2.0 A**, M = 2, t = 0.1·0.14/(2^0.02−1) | `test_primary_recorded_current_is_converted_once…` |
| Secondary with CT configured | 2 A | 1000:5 (not applied) | **2.0 A** (a double conversion would give 0.01 A) | `…secondary_recorded_current_with_a_ct_is_not_converted_again` |
| Secondary, no CT | 2 A | none | **2.0 A** | `…secondary_recorded_current_without_a_ct_is_computed` |
| Primary, no CT | 400 A | none | blocked, no number | `…primary_recorded_current_without_a_ct_blocks…` |
| Phase B on its own group | 400 A | 2000:1 | **0.2 A** (A and C: 2.0 A on 1000:5) | `…each_phase_uses_the_ct_and_the_override_of_its_own_current_group` |
| Second recording | 2 A, engineer → Primary | 600:1 | **2.0 × 1/600** (not 1000:5 of the first recording) | `…different_recordings_have_separate_authority…` |

Cross-check against the original accepted calculation: for the same input the recorded result equals the unchanged `/overcurrent-manual` pipeline to 1e-12 (relay current, multiple of pickup, operating time) and the hand-derived values
(`test_the_recorded_result_equals_the_accepted_manual_calculation_for_the_same_input`, three cases). The existing numeric suites (`test_overcurrent_domain.py`, the service/API golden cases, the kA normalisation cases) pass unchanged in value.

## 5. Files changed

Backend: `app/domain/overcurrent.py` (reason codes, result fields), `app/services/overcurrent_recorded_input.py` (**new**; owner-review: calculated-channel wording and the other-group CT hint), `app/services/overcurrent_analysis_service.py`, `app/schemas/overcurrent_analysis.py`, `app/api/v1/engineering_contexts.py`.
Frontend: `frontend/index.html`.
Tests: see §6. Docs: this file, DEC-216 Amendment 5, `HANDOFF.md`, `OVERCURRENT_ANALYSIS.md` (supersession notes + new section), `D5A_OC_001_…` banner.

## 6. Tests

| Layer | File | Purpose |
|---|---|---|
| Backend (new) | `test_d5a_2b2c_1a_overcurrent_unified_side.py` | the 15 requested areas on the real app and real COMTRADE uploads (see below) + report endpoint + calculated channel + manual unchanged + cross-check |
| Node + static (new) | `test_frontend_d5a_2b2c_1a_overcurrent_side.py` | the real `D5A-2B2C-1A-BLOCK` run in Node against a fake network |
| Browser (new) | `d5a_2b2c_1a_overcurrent_side.spec.js` | 13 end-to-end cases on a real backend, every side/CT change through the Recording Details API |
| Guard | mutation checks | each of six enforcement mutants (inferred accepted, unresolved not blocked, request basis overrides, group conflict ignored, differing request CT accepted, CT applied to a Secondary side) fails the suite; a no-op control mutant survives, as expected |

The 15 requested areas map to: 1–4 the four oracles; 5 Level 1 Primary + Level 2 Secondary; 6 Level 1 changes without a group override; 7 independent Voltage/Current groups; 8 declaration vs engineer correction; 9 inferred-only and unresolved;
10 legacy basis/CT contradicting; 11 phases and owning groups; 12 separate recordings; 13 workspace reset and stale reads (backend reset + Node/browser stale-read discard); 14 Manual unchanged; 15 blocked results keep the channel.

**Existing tests changed (no assertion weakened; each now states the new contract with an equal or stronger check):**

* `test_overcurrent_analysis_service.py`, `test_overcurrent_analysis_api.py`: recordings now declare the side their values are on (`S`, or `P` + a group CT for the Primary cases) and the service takes the authority; every original numeric assertion is kept.
* `test_d5a_oc_001_overcurrent_ct_authority.py` (5 tests): a Primary request without a CT keeps the reason and channel identity with the group-specific message; an unresolved role reports the resolver's answer; an unknown context is a 404 for every request; a request CT that disagrees with Recording Details now **blocks** instead of being applied.
* `test_dec108_disturbance_record_integration.py`: the fixture declares no side, so the test sets it in Recording Details (as an engineer would).
* `test_frontend_overcurrent_analysis.py` (5 tests): the selector/label/gate assertions now assert it is absent and the read-only host is present and gated.
* `browser-tests/overcurrent_analysis.spec.js`, `analysis_related_waveforms.spec.js`: the specs that chose the basis in the page now set the side through the same API Recording Details saves through (`support/current_side_helpers.js`).
* **Retired:** `test_frontend_d5a_oc_001_ct_authority.py` and `d5a_oc_ct_authority.spec.js`, which tested the user-chosen-basis design DEC-216 retires; every behaviour they protected that still applies is covered by the two new files.

## 7. Verification (first pass, `a6adcbd`; superseded by §10 for the final tree)

Final tree `49f7825` (five commits above `ad1b6ed`).

| Layer | Result |
|---|---|
| Backend, full suite (`pytest`, whole `backend/`) | **13,933 collected: 13,528 passed, 405 skipped, 0 failed** (18.3 min). An earlier full run had one failure — the D5A-UI-002 "results unchanged by side configuration" guard still listed the Overcurrent endpoint, which now follows the side by design; the guard was updated (Impedance, Distance, PU, the protection-context report, channels and groups remain asserted unchanged) and the file re-run. |
| Frontend static + Node (`tests/test_frontend*.py`, real helper blocks run in Node) | **2,214 passed, 0 failed** (includes the 41 new Node/static tests; the 32 retired D5A-OC-001 frontend tests are replaced by them). |
| New backend suite | 34 tests, all passing; mutation checks: six enforcement mutants killed, the no-op control mutant survived as expected. |
| Browser, new spec `d5a_2b2c_1a_overcurrent_side.spec.js` | **13 / 13 passed.** |
| Browser, affected set (16 spec files: Overcurrent, Related Waveforms, Impedance, Distance ×5, Sequence, Phasor, Playback, Playback ownership, post-upload readiness, `d5a_ctvt_authority`, `d5a_ui_002_group_details`, the new spec) | **310 passed, 41 failed** (20.5 min). All 41 are in four spec files — `playback` (27), `playback_waveform_ownership` (8), `phasor_analysis` (1), `post_upload_readiness` (5) — which also fail on the **untouched approved baseline `ad1b6ed`** (41 failures across the same four files there). `overcurrent_analysis`, `analysis_related_waveforms`, `d5a_ctvt_authority`, `d5a_ui_002_group_details`, every `distance_*`, `impedance_analysis` and `sequence_components_analysis` spec pass. |

**Baseline comparison.** The four spec files above were run on the baseline frontend and compared test by test. The only titles that differed between runs were in `post_upload_readiness` and are flaky in
that file on both trees (three of them passed 6/6 and 5/5 on this tree; the baseline itself failed 1 of 6 on one of them); none involves the Overcurrent side/CT change. The Playback failures occur in Waveform-page setup
(`#channelGroups` hidden) before any analysis code runs. The post-upload Overcurrent tests expect a number on a Primary-declared fixture with no CT, which D5A-OC-001 already withheld on the baseline.
No unrelated application code was edited and no failing pre-existing test was weakened.

**Process note.** A first version of the browser helper intercepted the upload request to set the side; it left the upload dialog hanging (82 timeouts, a 118-minute run). It was replaced by an explicit
Recording Details API call after each upload (`setRecordedSide`), and the set was re-run from scratch.

## 8. Decisions and limitations for the owner

1. **Legacy parameters.** `recording_basis`, `ct_primary`, `ct_secondary` are kept as optional assertions (validated, never applied; contradictions block). They can be removed in D5A-2B2D.
2. **Calculated current channels are blocked — a temporary functional regression.** (`calculated_channel_side_unavailable`; owner-accepted safe blocking, the legacy basis override is deliberately not restored.) Previously a calculated current worked on a Secondary basis. It needs a future **lineage-aware enhancement** (a calculated channel's side derived from its inputs' sides and ownership), which is not implemented here. Until then the page says so plainly (see §10 A); Related Waveforms still show the channel and no calculated channel is modified.
3. **A recording with no P/S evidence** (BEN, CSV, …) now needs an engineer's Level 1 or group setting before a recorded Overcurrent number is shown; the old "choose an unverified basis in the analyzer" path is gone by design (B2A-4).
4. **A Current group with mixed declarations blocks every phase it owns** — even a phase whose own channel declares a clear side — until the engineer chooses the group's side (consistent with Group Details showing no side for such a group).
5. **Impedance/Distance are unchanged**: their side-contradiction behaviour remains warn-only (the recorded inconsistency noted in D5A-OC-001 is still open for the later integration slices).
6. **Tab-corner commits.** Included after owner review (§10 D): the two approved CSS commits were cherry-picked from `feature/d5a-ui-003-restore-typography-spacing` (`2f1d9f5` → `3d5e16a`, `c7bae26` → `270c090`).
7. **Pre-existing browser failures** (Playback, Playback ownership, Phasor shared-clock, and the post-upload readiness Overcurrent/Impedance/Distance specs on the shared fixture) fail identically on the untouched `ad1b6ed` frontend and are not touched.

## 9. DEV UAT instructions (after the owner authorises a push and deploy)

Use a recording whose current channels are in a Current Measurement Group (e.g. KPDN1 CURRENT) and open Analysis → Overcurrent.

1. **Declared Primary + CT.** The block shows `Side: Primary (declared by the recording)` and `CT: 1200 A / 1 A (Manual, KPDN1 CURRENT)`; there is no basis select; a number is shown; 400 A recorded gives 0.333 A relay-secondary.
2. **Level 2.** In Recording Details → Group Details → KPDN1 CURRENT set **Secondary**; return: `Secondary (set by engineer for KPDN1 CURRENT)`, `CT … not applied to a Secondary current`, the number is the recorded value unconverted, and a note says the recording declares Primary.
3. **Independence.** Change KPDN1 **VOLTAGE** only: Overcurrent is unchanged.
4. **Level 1.** Clear the group setting, set the recording to Secondary (Recording Info): Overcurrent follows (`set by engineer for the recording`); set it back.
5. **Missing CT.** Clear the group's CT with the side Primary: no number, a message naming the group, **Configure in Recording Details** opens that group, waveform still plotted; set the CT, return: the number appears with no reload. With the side Secondary a missing CT is fine.
6. **Undeclared recording** (BEN/CSV or any without P/S): `Side: not defined`, no number, link to Recording Details; set Level 1, return: the number appears.
7. **Phase and recording switches.** A→B→C follow each phase's own group/CT; two recordings keep separate sides and CTs; clearing the workspace leaves no side/CT behind.
8. **Manual mode.** CT and basis inputs behave as before; the typed Manual CT is never used for a recording.
9. **Direct API check.** `GET …/overcurrent?…&recording_basis=secondary` on a Primary recording returns `needs_configuration` / `recording_basis_contradicts_measurement_side` with no numbers.
10. Impedance Locus, Distance, PU, Waveform and Recording Details behave as in the last accepted UAT.

## 10. Owner review and final hardening (2026-11-23)

The owner provisionally accepted `a6adcbd`. The unified architecture is approved; these checks and refinements were requested before DEV deployment.

**A. Calculated current channels** — safe blocking retained; no legacy override restored; no side propagation implemented.
1. *Explicit blocker:* `calculated_channel_side_unavailable`, message "Measurement-side support for calculated channels is not available yet: the side of the calculated current channel '<id>' is derived from its inputs, and Recording Details does not resolve it, so there is nothing to set there…".
2. *No misleading suggestion:* the page shows the Side as `not available for a calculated channel` (not "not defined"), offers **no** Configure link, shows no CT row, and neither message mentions a Measurement Group. The link target is withheld on the reason as well as on a missing source id.
3. *Related Waveforms* remain functional: the blocked result and the report keep the calculated channel's identity and unit; the browser test plots it.
4. *Nothing is deleted or modified:* tests snapshot the calculated-channel list byte for byte, the side-registry and group counts, across repeated evaluations (including legacy requests).
5. *The legacy basis/CT cannot get around it* (three request shapes). *Documented limitation:* a temporary functional regression requiring a future lineage-aware enhancement (§8 item 2).

**B. Secondary without CT** — verified at both layers. With an authoritative Secondary side the calculation runs for every CT state (no group, group without CT, untrusted authority, invalid pair) with `ct_*` null; the report is `ready` / `conversion: none`; the page shows `not needed for a Secondary current` with no blocker, no message list and no critical styling (Node + browser assertions). Primary without a usable CT **of its own group** still blocks in all four states, with or without a request CT. A recording-wide Secondary/Primary toggle removes and restores the requirement.

**C. Mixed P/S declarations** — verified: a Current group declaring IA Primary / IB Secondary / IC Primary blocks every phase (`measurement_side_conflict`, naming the group, with a link) until an engineer resolves it at group level (`engineer_group_override`) or recording level (`engineer_recording_correction`); then every phase is consumable (Primary with the group's CT, or Secondary without one). The original declarations are **never rewritten** (read back from the source channels API after each step), the group view lists the overridden declaration (IB: Secondary → Primary), the report carries `GROUP_OVERRIDE_OVERRIDES_DECLARATION` / `ENGINEER_CORRECTION_OVERRIDES_DECLARATION` for exactly the disagreeing channel, the page discloses it ("The recording declares secondary; the side set in Recording Details is used instead."), and removing the correction restores the conflict.

**D. Tab corners** — `2f1d9f5` and `c7bae26` were inspected (one CSS line each: `border-radius: 0` on `.ww-rd-tab` and on `.ww-rd-tab:focus-visible`, nothing else) and cherry-picked cleanly. The keyboard focus outline (`2px solid var(--accent)`, offset −2px) is unchanged; the tab dimensions, fonts, padding and colours are untouched.

**E. Coverage of the retired tests.** Every retired test was mapped to a replacement; the audit found and closed two gaps:

| Retired (D5A-OC-001) | Replacement |
|---|---|
| read-only host, no CT editor; manual untouched; lifecycle; Related Waveforms/never plotted; Impedance/Distance not strict and unchanged params | `test_frontend_d5a_2b2c_1a_overcurrent_side.py` (same intent, now asserting no basis input either) |
| request carries only the authoritative CT / no VT or impedance basis; secondary sends no CT | `test_the_recorded_request_carries_no_basis_and_no_ct` (stronger: neither is sent) |
| CT never derived from equipment or nominal data | `test_the_page_never_derives_a_side_or_a_ct_itself` — the equipment/nominal token guard was **restored** in the owner-review pass |
| unusable CT blocks only when needed; names the group and links to it | backend `test_a_secondary_current_is_calculated_whatever…` / `…primary_current_without_a_usable_ct…`; Node blocker/link tests |
| CT of an unrelated group is named but never used | backend `test_a_missing_ct_names_another_group…` (**gap closed**: the hint moved to the backend message, plus "never borrowed" and "never another recording" tests) |
| unresolved channel is named; ratio never decides the side; undeclared side never inferred | backend `…no_side_evidence_never_guesses…`, `test_a_channel_that_never_resolved…` |
| basis contradicts the declared side, both directions; agreeing basis raises nothing | backend `test_a_legacy_basis_that_contradicts_the_declared_side_is_rejected_in_both_directions` (**gap closed**: the reverse direction and the "wrong number never produced" check were added) |
| basis pre-selected from the declared side; explicit/unverified choice | replaced by showing the effective side with provenance (`test_the_provenance_of_the_side_is_stated`); the choice itself no longer exists |
| nothing shown while the read is in flight; stale/foreign reads discarded; reset; read key/URL; signature | the same Node tests, ported to the new module |
| unreadable report blocks only a needed conversion | **intentional change:** an unreadable report now blocks every recorded result, because the side itself is unknown without it (`CONTEXT_UNAVAILABLE`) |
| 11 browser cases | `d5a_2b2c_1a_overcurrent_side.spec.js` (15 cases: the 11 rewritten for the new contract — the contradiction case became the direct-API case and the undeclared case the unresolved case — plus a recording-wide correction, a side changed in Recording Details and picked up on return, the calculated-channel case and the mixed-group case) |

Numerical coverage is unchanged: the original numeric suites (`test_overcurrent_domain.py`, the service/API/kA golden cases, the OC-001 backend oracles) still pass with their expected values, and the new oracles of §4 are added.

**Final verification (final code tree, after the tab commits and the hardening commits).**

| Layer | Result |
|---|---|
| Backend, full suite | **13,964 collected: 13,559 passed, 405 skipped, 0 failed** (26 min) |
| Frontend static + Node (`tests/test_frontend*.py`) | **2,218 passed, 0 failed** |
| New backend hardening suite | 27 tests, all passing; four mutants (calculated guard off, CT required for Secondary, hint reading other recordings, group conflict ignored) all killed |
| Browser, affected set (19 spec files: the 16 of §7 plus `rd1-slice-c1-tabs`, `ui_rec_001_recording_info`, `rd1-responsive` for the tab change) | **347 passed, 40 failed** (27.6 min). All 40 are in the four spec files that already fail on the untouched baseline `ad1b6ed` (`playback` 27, `playback_waveform_ownership` 8, `phasor_analysis` 1, `post_upload_readiness` 4). **No test fails here that passes on `ad1b6ed`.** |
| Browser, new/changed specs | `d5a_2b2c_1a_overcurrent_side` 15/15, `overcurrent_analysis`, `analysis_related_waveforms`, `d5a_ui_002_group_details`, the three tab-related Recording Details specs, `d5a_ctvt_authority`, all `distance_*`, `impedance_analysis`, `sequence_components_analysis`: all green |

**Regression against `ad1b6ed`.** The four failing files were run on the baseline frontend earlier and compared test by test: the baseline fails 41 there, this tree 40, none new (post-upload readiness is
flaky on both trees; its Overcurrent/Impedance/Distance cases that expect a number on the Primary-declared fixture with no CT were already withheld by D5A-OC-001). No unrelated application code was edited and no failing pre-existing test was weakened.

Not changed in this pass, as instructed: Impedance and Distance, the PU migration, calculated-channel lineage, anything outside Overcurrent and the two approved tab-corner CSS lines. Nothing is pushed, merged or deployed.
