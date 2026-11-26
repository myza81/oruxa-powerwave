# PU-MIG S5 — presenting the side-aware per-unit engine's verification state

**Date:** 2026-11-26 · **Branch / worktree:** `feature/pu-mig-s5-verification-presentation`, `.local-data/pu-mig-s5`, created from the owner-approved
integration baseline **`cf9e836`** (`integration/pu-mig-s2-correction-into-s4`: S2 correction + S3 + S4 + the reconciliation record).
**Local only: not pushed, merged to any shared branch or deployed. Stopped for owner review (S6 is not started).**
Authority: owner message "PU-MIG — S2–S4 Reconciliation Accepted; Resume S5" (2026-11-26). Specification: S0 final reconciliation §9 — *S5: UI
wording/provenance only; no control retirement.*

## 1. Governing decisions

Consulted: AGENTS.md, CLAUDE.md, DEC-218; `PER_UNIT_MEASUREMENT_MODEL`; DEC-210/211 (Current base and reference compatibility), DEC-212 (raw Current stays
ENG on the waveform), DEC-213 (calibration), DEC-215/216 (shared VT/CT authority, Recording Details as the side authority), DEC-117/118 (electrical notation:
no symbol is formatted in this slice; the texts say "VT"/"CT"), DEC-070 Amendment 1 (Per-Unit Details is raw-channel and calculated-Current only), DEC-023
(Light/Dark); the S0 final reconciliation (§4.3, §9 S5 row, OD-3); the accepted S1–S4 reports and the S2–S4 reconciliation record.

Not reopened: D-1 R+, D-4 (diagnostic only), D-5, D-6, D-7 (`auto_nominal`), the DEC-212 raw-Current restriction, K-1…K-3, D-8, N-2. Nothing in the
engine, the denominators, the base-selection precedence, the CT/VT authority, the calibration gate, RMS or power was changed.

## 2. Preservation and transfer of the pre-existing S5 work

The S5 work started in `.local-data/pu-mig-s1` (uncommitted `frontend/index.html`, untracked `browser-tests/pu-side-provenance-presentation.spec.js`). Before
transfer the original files were compared with the recorded copies outside the repository (the PU session's `s5_backup/`): the `index.html` working-tree diff
(+108/−8) is byte-identical to `s5_backup/s5_frontend.patch`, and both files are byte-identical to the saved copies (SHA-256 prefixes `eb9c4922…` and
`a633b29a…`). The diff was applied to the new worktree with `git apply` and the spec copied; both are byte-identical to the originals at the moment of transfer.

The original worktree was **not** modified by this work (no reset, stash, checkout or overwrite). Observation: between the backup and the end of this slice that
worktree was fast-forwarded to `cf9e836` (its own reflog, 20:35) and its spec was edited once (the `innerText` assertion of the converted-Voltage test — the same
root cause as §5, test 1); its `index.html` is unchanged. Nothing it holds is lost: the new spec reads the same rows through the DOM and is stricter. **Two copies
of S5 now exist; the owner should retire the original or tell its session which one continues** (§9).

## 3. What changed

| Area | Path | Change |
|---|---|---|
| Backend (additive, read-only) | `domain/per_unit.py` | `PerUnitResolution.verification_state` — an accessor returning the existing `side_provenance.verification_state` (or `None`). No logic. |
| Backend (additive) | `schemas/{waveform,calculated_channel,peak_value,cursor_values,annotation_anchor}.py`, `services/{waveform_service,calculated_channel_service}.py` | `per_unit_verification_state` beside `per_unit_reference_compatibility` on every response the channel badge is built from (waveform, calculated waveform, peak, cursor, anchor). 54 lines, **0 deletions**; copied from the resolution that produced the numbers, so it cannot disagree with `GET …/per-unit-resolution`. |
| Frontend | `frontend/index.html` | (a) the "no CT/VT scaling" wording replaced (owner §4 of the S5 message), (b) Reference check row, ratio/authority and refusal wording from the backend's state, (c) stored-versus-derived diagnostic row, (d) readable small bases, (e) the badge follows the backend's verification state, (f) the Current compatibility row never reads "Verified compatible" for a historical result, (g) sentence rows take the full width, (h) the dialog uses the established pinned header/footer pattern. |
| Tests | `backend/tests/test_pu_mig_s5_verification_state_field.py` (14), `browser-tests/pu-side-provenance-presentation.spec.js` (13) | below |
| Evidence | `docs/project-memory/evidence/pu-mig-s5-2026-11-26/` | 12 states × Light and Dark |

No new panel, control or configuration mechanism. Recording Details, the channel row badge, the legend/hover/annotation badges and the existing Per-unit
details dialog are the only surfaces; no retired Current UI was restored.

## 4. State → wording mapping (everything shown is the backend's own field; nothing is derived in JavaScript)

| Backend state | Channel badge | Per-unit details — Reference check |
|---|---|---|
| `verified_direct` | none (nothing to warn about) | **Verified.** The recording and the base are on the same side (primary); no VT/CT conversion was needed. Waveform samples are unchanged. |
| `verified_converted` | none | **Verified, base converted.** The per-unit base was referred to the secondary side with the VT/CT ratio 1200 : 1 (entered manually / from the recording / derived from the nominal voltage); waveform samples are unchanged. |
| `unverified_historical` | **Unverified reference** (title: not checked against a CT/VT ratio; samples unchanged) — including a historical result whose side *labels* match | **Unverified.** The base was not placed on the measurement side with a verified denominator, so the historical per-unit value is kept without a VT/CT check. Waveform samples are unchanged. |
| `blocked` | **PU unavailable** (no authoritative CT/VT ratio) | **Unavailable.** + the actionable explanation per refusal (no ratio set — enter it in Recording Details; not tied to a Measurement Group; invalid or untrusted ratio; conflicting groups; not representable; mixed sides). The internal code is never shown. |

Stored-versus-derived (D-4): a **Stored base check** row — "The stored secondary base (115.00 V) differs by 4.55 % from the 110.00 V derived … The stored base is used and
was not changed." Voltage representation is the existing *Channel interpretation* (L-G/L-L); measurement side, base reference side and effective base are rows of the
same dialog. The wording separates the two facts the owner asked to be kept apart: **waveform samples are never transformed; only the PU denominator may be
referred to the measurement side.**

## 5. The two failing S5 browser tests, and what the work uncovered

| # | Test | Cause (classification) | Resolution |
|---|---|---|---|
| 1 | converted Voltage | **Incorrect assertion.** It read `innerText`, which returns the CSS-upper-cased label ("VT RATIO"). Not a defect, not timing. | Rows are read from the DOM by label (`infoValue()`), values by `toHaveText`. |
| 2 | calculated Voltage | **Incorrect expectation of an established contract.** It right-clicks a calculated Voltage row for "Per-Unit Details…", which the shared menu hides for every calculated channel except Current (DEC-070 A1; `calculated-channel-presentation.spec.js:150` asserts it). S5 is wording only and adds no surface. | The test now checks the inherited converted result through the engine's own calculated resolution, that the dialog is still not offered, and that an Unverified calculated Voltage is labelled on the channel. |

No delay, retry or weakened assertion was used. The converted/derived states pass repeatably (3 × 13 = 39 consecutive passes).

Running the scenarios the owner listed uncovered four further defects, all corrected at the cause:

1. **The Source Default counterexample had no channel badge** (132 kV base labelled Secondary, rated Secondary samples, 0.0008333 pu): the badge was keyed to
   `reference_compatibility`, which is `compatible` both for a resolver-verified result and for a historical result whose labels merely match — the very confusion the
   S2 correction removed from the engine. The backend's `verification_state` now reaches the badge (additive field, §3); the frontend shows it and never derives it.
2. **The Current dialog read "Reference compatibility: Verified compatible"** beside an Unverified check for a legacy pointer → "Side labels match; not verified".
3. **The verification sentence was cut to one grid cell** ("Unverified. The base was no…") → the sentence rows (Reference check, Stored base check, Reason) take the full
   row and wrap; asserted (not clipped and ≥ 95 % of the row width).
4. **The extra line pushed Save below the 85vh dialog cap at 1280×720** (`calculated-current-manual-pu` "Peak cannot cover Per-unit dialog controls" went red:
   scroll height 666 against 610). The redundant CT/VT-ratio row was removed (the sentence already states ratio and authority), a refusal is said once (the duplicate
   *Reason* row is dropped), and the dialog now uses the established `ww-pu-dialog` pinned header/footer pattern.

## 6. Verification

Scenarios (browser, real backend; `pu-side-provenance-presentation.spec.js`, 13 tests; screenshots in Light and Dark):

| Owner scenario | Test | Result |
|---|---|---|
| 132 kV Source Default counterexample, ≈ 0.0008333 pu, `unverified_historical` | Source Default counterexample | peak 1/1200 (7 digits), Unverified badge and sentence, never "Verified" |
| Legacy calculated Current pointer, `unverified_historical` | legacy pointer | Unverified sentence and "Side labels match; not verified" (see §8, limitation 3) |
| Same-side `verified_direct` | same-side Voltage; Manual Current on the recording's side | Verified, no ratio, no badge |
| Authoritative VT/CT conversion `verified_converted` | converted Voltage; VT from the nominal voltage; calculated Current + CT | 0.06351 kV L-G, ratio and authority named |
| Blocked reference-side mismatch | blocked conversion | "Unavailable …", PU unavailable badge, no internal code, ENG values |
| Valid engineer-configured Manual bases | Manual Current (same side), calculated Current (CT 240 : 1) | Verified / Verified, base converted |
| Existing waveform and calculated-channel display modes | calculated Voltage (converted, Unverified), raw Current stays ENG (DEC-212), error/recovery, no request until opened | pass |
| Stored-versus-derived diagnostic | stored 115 V vs derived 110 V | reported, not applied |

Mutation (frontend: scratch copies; backend: in place, restored and hash-checked) — **all 8 killed**: badge ignores the backend state (M1), compatibility row says
verified (M2), sentence rows not full-width (M3 — first survived, which exposed a missing width assertion that was then added), Unverified sentence dropped (M4), state
not carried to the badge (M5), dialog not pinned (M6, caught by `calculated-current-manual-pu`), converted treated as direct (M7), backend accessor returns `None` (M8).

## 7. Regression (measured)

* Backend, new tests: 14 passed (waveform, calculated waveform, cursor, peak, engineering mode, schema parity on all five modules).
* **Full backend suite: 15,617 tests, 15,207 passed, 410 skipped, 0 failed** (JUnit; the S2–S4 reconciliation's 15,193 plus the 14 new). Backend files did not change after that run; later edits were frontend only.
* **Affected PU browser regression (26 specs: the 25 of the S2–S4 reconciliation + the S5 spec): 355 passed, 0 failed** (342 + 13 new), including every calculated-Current, per-unit,
  waveform-axis-units, calculated-channel presentation and Source Default Current spec. No full browser suite (reserved for S6).
* Repeatability of the S5 spec: 3 consecutive runs, 39/39.

## 8. Performance, boundaries and limitations

* **No new requests.** Nothing is fetched merely to show a badge; the dialog still issues one `per-unit-resolution` request per open (asserted). The new field is one short nullable
  string on responses that already exist; the rows are built only when the dialog opens; no recomputation of any denominator in JavaScript.
* **Protected files:** none of `per_unit_reference.py`, `side_denominator.py`, `per_unit_side_authority.py`, the group-config resolvers, `calculated_current_per_unit.py`, `group_aware_per_unit.py`, calibration, RMS or power was touched.
* Limitations:
  1. **Source Default Voltage reports "Base reference side: Unknown"** in the dialog even where a `secondary` label is stored: the backend provenance has never carried a base
     side for that path (it is shown as reported; the check line says the base was not placed on the measurement side). Reporting the stored label would be a backend response
     change; recommended for a later slice only if the owner wants it.
  2. **A calculated Voltage has no details dialog** (DEC-070 A1): its Unverified/unavailable state is the badge; a *verified* calculated Voltage has no surface other than the API.
     Offering the dialog for it would reverse an asserted contract — an owner decision, not made here.
  3. The legacy calculated-Current pointer has no API route (it is set in-process only), so its browser test fulfils the real automatic resolution with the backend's
     historical-gate fields; the backend behaviour itself is covered by the S4/reconciliation tests.
  4. Electrical-symbol notation (DEC-117) is not exercised: the texts contain no phase or sequence symbol.

## 9. Acceptance recommendation

Accept S5 for local engineering closure after the owner's visual review (UAT-4): the presentation follows the backend's states one-to-one, a historical result can no longer be mistaken
for a verified one on the channel or in the dialog, the two failing tests are explained and corrected at the cause, and every regression is green. Open owner items: (1) retire or
re-point the duplicate S5 files in `.local-data/pu-mig-s1` (§2); (2) limitations 1 and 2.

**DEC-218 compliance statement:** the applicable decisions were consulted before editing (§1); no approved policy was reopened or changed; the one backend change is an additive,
read-only field required by the S5 requirement "do not infer verified status from labels", recorded here rather than decided silently.
