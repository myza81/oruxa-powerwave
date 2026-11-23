# D5A-2B2C-1B — Recorded Impedance Locus and Distance Protection consume the unified measurement side

**Branch:** `feature/d5a-2b2c-1b-impedance-distance-unified-side`, from the DEV-UAT-approved `f24f1d72f49cf694ac5f843d03fd102e7754320a` (`uat/dev-d5a-20261121`). **Not pushed, merged or deployed.**
Authority: [DEC-216](DECISIONS.md#dec-216--recording-details-is-the-single-authority-for-recorded-measurement-side-d5a-2b2-unified-model) Amendment 6.
Scope: recorded Impedance Locus and Distance Protection (selected-time and locus). The impedance and loop-impedance mathematics, the low-current guardrails, the Mho / Quadrilateral geometry, zone classification
and delays, the Manual input source, Overcurrent mathematics, PU, calculated-channel behaviour, CT/VT configuration models, Engineering Context membership, the Source Default / calibration safeguards and
D5A-2B2D are **not** touched.

## 1. Data flow before and after

| Step | Before (`f24f1d7`) | After |
|---|---|---|
| Who decided the recorded side | The engineer, through a single `Recording basis` select (pre-selected from consistent declarations; "unverified" when undeclared); one basis for Voltage **and** Current. Or, for a direct API client, `voltage_side` / `current_side` request parameters ("strict" mode). | **Recording Details**, per quantity: `resolve_effective_measurement_side()` of every consumed channel — group override > recording correction > channel declaration > inferred (not strict-usable) > unresolved — with the shared consumer policy (calculated / unresolved / inferred / group-conflict → blocked). Voltage and Current are independent. |
| Who decided the VT/CT | The page read `protection-instrument-context` and sent `vt_*` / `ct_*` request parameters when a conversion was needed. | The **backend**: the VT/CT of the Measurement Group that owns the consumed channel(s), read inside the calculation, and only where a conversion is needed. |
| Request (recorded) | `recording_basis` (required) + `impedance_basis` + `vt_*`/`ct_*`; optionally `voltage_side` / `current_side`. | `phase`/`loop`, `analysis_time` (or the locus range), `impedance_basis` (the requested OUTPUT side), zone parameters. Nothing else is needed. |
| Legacy bypass | Omitting `voltage_side`/`current_side` selected the legacy path, where the request basis and ratios decided and the recorded inconsistency was only a warning. | **Closed.** There is one path. |
| What the page shows | `Recording basis` select, read-only CT/VT, the "choose the basis explicitly" confirmation. | Read-only block: **Voltage side** and **Current side** (provenance + link), **VT** and **CT** (ratio + owning group, or "not needed"), the backend's blocker text, the override disclosure. |
| Freshness | Report re-read on context (re)load / phase|loop change. | Same triggers **plus an output-side change** (it decides whether a ratio is needed). The result, the plotted point, the locus and a zone classification are withheld while the read is in flight or blocked. |
| Cost | Locus: the strict path already evaluated the plan once. | Request-scoped, **one** authority evaluation per request (a locus shares one snapshot across all points); nothing per Playback tick or per point; the prepared-phasor optimisation (DEC-114) is untouched. |
| Stateless? | n/a | Yes — nothing is cached, so a Level 1 / Level 2 change reaches the very next request. |

## 2. Shared backend authority

* `app/services/recorded_side_authority.py` — the one per-channel policy (`evaluate_channel_side`): used by Overcurrent (`overcurrent_recorded_input.py`, mapping problems onto its **unchanged** reason codes) and by
  Impedance/Distance (`independent_side_service.py`). No parallel authority exists; the resolver is `measurement_side_service.resolve_effective_measurement_side`.
* `independent_side_service.evaluate_recorded_input(...)` evaluates, for the consumed roles of one phase/loop: each channel's side and provenance → the quantity's effective side (the legs of a loop must agree) →
  the legacy assertions → the VT/CT of the **owning groups** (only for a quantity whose side differs from the output side) → a `SidePlan` (or a `SideBlock` with a reason). The same evaluation feeds both the calculation and
  the read-only `protection-recorded-input` report, so the page and the backend cannot disagree.
* `impedance_analysis_service` / `distance_protection_analysis_service` take the plan as a **required** argument (there is no code path that skips the authority). Each quantity is converted directly to the output
  side (`convert_to_side`: Secondary → Primary multiplies, Primary → Secondary divides, same side is an identity), after D5A-UNIT-001 normalisation to volts / amperes; `Z = V/I` (or `(V1−V2)/(I1−I2)` with full complex
  subtraction) is formed once; the low-current floor is `MIN_CURRENT_A × (|I_out| / |I_recorded|)` so it keeps judging the recorded current. The numerical engines are untouched.
* Manual mode (`/impedance-manual`, `/distance-protection-manual`) is a separate code path and is unchanged.

## 3. API contract, legacy clients and reason codes

**Request parameters.** `impedance_basis` — required, the OUTPUT side. `recording_basis`, `voltage_side`, `current_side`, `vt_primary`/`vt_secondary`, `ct_primary`/`ct_secondary` — optional **assertions**: validated
against Recording Details; a match changes nothing and causes no extra conversion; a contradiction blocks; none can select a side, supply a missing ratio, or be required. An assertion about a quantity that needs no
conversion (e.g. a VT pair when the voltage is already on the output side) is ignored. Response-schema compatibility: all existing fields are kept (the echoed `recording_basis` is the single effective side, or `null` when
Voltage and Current are on different sides; the echoed VT/CT are the authoritative pair **applied**, `null` when none was); `side_conversion` gains `voltage_side_authority`, `current_side_authority`, `voltage_group_names`,
`current_group_names` (additive).

| Situation | Result |
|---|---|
| recorded sides usable, ratios present where needed | `computed` |
| quantity already on the output side, no VT/CT anywhere | `computed` (identity, no ratio read) |
| calculated channel consumed | `needs_configuration` / `calculated_channel_side_unavailable` |
| channel side unresolved | `voltage_side_authority_unavailable` / `current_side_authority_unavailable` |
| channel side only inferred from siblings | `voltage_side_inferred` / `current_side_inferred` |
| consumed Measurement Group declares mixed sides (uncorrected) | `voltage_group_side_conflict` / `current_group_side_conflict` |
| the two legs of a loop disagree (no group) | `voltage_mixed_side_within_quantity` / `current_mixed_side_within_quantity` |
| VT / CT needed but missing, no group, invalid, untrusted, conflicting between groups | `vt_authority_unavailable` / `ct_authority_unavailable` (message names the group / channel and the remedy) |
| asserted `voltage_side` / `current_side` / `recording_basis` ≠ the effective side | `voltage_side_contradicts_recording` / `current_side_contradicts_recording` |
| asserted request VT / CT ratio ≠ the authoritative ratio (conversion needed) | `request_vt_conflicts_with_authority` / `request_ct_conflicts_with_authority` |
| half a request pair, zero or negative | `request_vt_invalid` / `request_ct_invalid` |
| `impedance_basis` / `recording_basis` / `voltage_side` / `current_side` not primary|secondary | `invalid_impedance_basis` / `invalid_recording_basis` / `invalid_voltage_side` / `invalid_current_side` |
| unit not volts / amperes | `unsupported_voltage_unit` / `unsupported_current_unit` (D5A-UNIT-001) |
| role unresolved / ambiguous / not eligible | the analysis' own status and reason, **before** any side is consumed (unchanged precedence) |
| current below the floor | `current_too_small` / `loop_current_too_small` (unchanged) |
| unknown Engineering Context | 404 |

A blocked result carries no impedance (never a fabricated zero or infinity), **no zone classification** (every zone reports the established not-operated placeholder; the page shows none), and keeps the resolved
channel identities and units, so Related Waveforms keep working. A blocked locus reports the reason on every point and in `side_conversion`.

Retired reason codes: `voltage_side_required`, `current_side_required` (and the legacy `invalid_ratio` message for a missing request ratio, now `vt_authority_unavailable` / `ct_authority_unavailable`).
`recording_basis` is no longer required (the 422 on its omission is gone); `impedance_basis` is still required.

New read-only endpoint: `GET /engineering-contexts/{id}/protection-recorded-input?analysis=impedance|distance_protection&phase|loop=&impedance_basis=` (per quantity: channels, effective side + authority, the
original declarations, group ids/names, whether a ratio is required, the VT/CT with its authority, a configure target, the blocker; plus the conversion that will apply and the overall status).

## 4. Recorded-mode UI

* The `Recording basis (as recorded)` field is removed from both panels. **Impedance basis (output)** stays editable and drives the next computation.
* `#wwImpedanceCtVtAuthority` / `#wwDistanceCtVtAuthority` show (existing `ww-ctvt-*` typography, no new heading/input/card/padding): `Voltage side` — `Secondary (declared by the recording)` / `Primary (set by engineer for <group>)` /
  `… set by engineer for the recording` / `conflicting declarations` / `only inferred, not usable` / `not defined` / `not available for a calculated channel`; `VT` — `132 kV / 110 V (Manual, <group>)` / `… (Auto-derived, <group>)` /
  `not needed (voltage is already Primary)` / `not configured`; the same two rows for Current / CT; the backend's blocker message; the override disclosure; **Configure in Recording Details** (opens the owning group; absent for a
  calculated channel, which has none).
* Manual Input / Calculator mode keeps every Voltage basis, Current basis, CT/VT and output-impedance control.
* Screenshots: `docs/project-memory/evidence/d5a-2b2c-1b/`.

## 5. Mathematics and numerical oracles (hand-derived, never read back from the code)

Reference: VT 110 000 V : 110 V (ratio 1000), CT 1000 A : 5 A (ratio 200); V Primary 66 000 V / Secondary 66 V; I Primary 400 A / Secondary 2 A; `Z_pri = 66 000 / 400 = 165 Ω`, `Z_sec = 66 / 2 = 33 Ω`;
current lags voltage by 30°, so `Z = |Z|∠+30°` (`R = |Z|cos 30°`, `X = |Z|sin 30°`). For the balanced three-phase set `Vab = Va − Vb = √3·V∠30°`, `Iab = Ia − Ib = √3·I∠0°`, so `Zab = (V/I)∠30°` (same for BC and CA).

Full 2 × 2 × 2 matrix (Voltage input × Current input × Impedance output), identical for impedance selected-time, impedance locus, distance AB / BC / CA and distance locus, and for each authority source (the recording's own
declaration, an engineer's Measurement-Group setting that contradicts the declaration, and — for uniform sides — an engineer's recording correction):

| V input | I input | Output Primary | Output Secondary | Conversions applied |
|---|---|---|---|---|
| Primary (66 000 V) | Primary (400 A) | **165 Ω ∠30°** | **33 Ω ∠30°** | Primary: none; Secondary: V ÷ 1000, I ÷ 200 |
| Primary | Secondary (2 A) | 165 Ω | 33 Ω | Primary: I × 200; Secondary: V ÷ 1000 |
| Secondary (66 V) | Primary | 165 Ω | 33 Ω | Primary: V × 1000; Secondary: I ÷ 200 |
| Secondary | Secondary | 165 Ω | 33 Ω | Primary: V × 1000, I × 200; Secondary: none |

Each result is asserted to `R`, `X`, `|Z|` and the angle, and the applied ratios are asserted to be applied **only** where a side differs (`test_matrix_with_*`, `test_the_eight_combination_numbers_are_the_hand_derived_ones…`).
A reversed ratio, a double conversion or a missing conversion would give 165 × 1000, 33 / 200, 0.033 or 165 / 40 000 and fails. Further oracles in the same files: all four V/I side combinations in one bay; Voltage group and Current
group set independently (`66 000 V` re-read as Secondary → `66 000 × 1000 / 400 = 165 000 Ω`; `400 A` as Secondary → `66 000 / (400 × 200) = 0.825 Ω`); group override beats a recording correction per quantity; an engineer's correction
contradicting the COMTRADE flags (declarations stay unchanged); V/A, kV/A, V/kA, kV/kA normalisation; the low-current floor judging the recorded current (0.5 mA Secondary blocked whatever the output side, 2 mA computed); Mho zone boundaries
at `0.99 × / 1.01 ×` the converted `|Z|` for both output sides; a blocked calculation never classifies a zone (reach 10⁹ Ω still reports no operation); Manual mode unchanged (66 kV / 2 A with 132000:110 and 1200:1 → 165 Ω; a
loop golden 100 Ω).

## 6. Tests

| Layer | File | What it proves |
|---|---|---|
| Backend (new) | `test_d5a_2b2c_1b_impedance_distance_oracles.py` | the matrix × four endpoints × three authority sources; independence of Voltage and Current; precedence; evidence preserved; ratio only where needed; nominal-derived VT; unit normalisation; the low-current floor; zone boundaries; Manual unchanged |
| Backend (new) | `test_d5a_2b2c_1b_authority_enforcement.py` | assertions both directions; ratio assertions (equal, wrong, reversed, half, unnecessary, missing authority, untrusted); every blocker; mixed / undeclared / group conflicts; calculated channels; two recordings and an unrelated group never borrow a CT; workspace isolation; one evaluation per request including a locus; the report and the calculation never disagree; the specific blocker messages |
| Node + static (new) | `test_frontend_d5a_2b2c_1b_protection_side.py` | the real `D5A-2B2C-1B-BLOCK` run in Node (plan, rendering, reads, stale answers, reset, navigation) plus reports from the real endpoint |
| Browser (new) | `d5a_2b2c_1b_protection_side.spec.js` | 8 cases × 2 panels end-to-end on a real backend |
| Mutation | scratch harness (not committed) | see §7 |

**Existing tests changed (no assertion weakened; each now states the new contract with an equal or stronger check):** fixtures that uploaded hand-built recordings (all channels flagged `P`) now state the side the test
meant — "secondary" — as an engineer would (a Level 1 correction through `tests/recorded_side_support.declare_sides`), and the requests drop `recording_basis` / ratios; `test_d5a2b1_*` (11 tests: the "required" side codes become
the inferred-side codes, mixed sides are asserted both without and with a Measurement Group, the legacy-path characterisation tests become "the old defect can no longer produce a wrong number" and "`recording_basis` is optional,
`impedance_basis` is required"); `test_d5a_blocked_channel_refs.py` (a missing/invalid request ratio is now `vt_authority_unavailable` and still identifies the channels); `test_d5a2a_*` (request ratios never replace the authority);
`test_d5a_ui_002_*` (Impedance now follows the side by design and leaves the unchanged-results snapshot, as Overcurrent did in 1A); `test_d5a_unit001_*` (OpenAPI wording of the new contract); `test_locus_shared_phasor_preparation.py`
(hands the services a validated `SidePlan`); `test_frontend_impedance_analysis.py`, `test_frontend_distance_protection_analysis.py` (marker/accessor updates), `test_frontend_d5a_2b2c_1a_overcurrent_side.py` (decoupled from the shared block).
**Retired:** `test_frontend_d5a_ctvt_authority.py` and `d5a_ctvt_authority.spec.js` (the user-chosen-basis design DEC-216 retires); what they protected and still applies is carried by the two new files (Manual untouched,
nothing shown while loading, stale reads discarded, reset empties everything, Related Waveforms for a blocked result, correction only through Recording Details, no frontend derivation, an auto-derived VT shown like any other,
and the specific blocker messages — now produced by the backend and asserted there).

## 7. Verification

Commits above `f24f1d7`: `3e9cc5f` (shared channel policy), `b7b689d` (backend), `4187680` (legacy-suite adaptation), `843f346` (frontend), and the documentation / evidence commit that holds this file.

| Layer | Result |
|---|---|
| Backend, full suite (`pytest tests`, includes every frontend static/Node test) | **14,059 collected: 13,654 passed, 405 skipped, 0 failed** (31 min). The approved baseline (1A final) was 13,528 passed / 405 skipped; the difference is the new and rewritten tests. |
| New backend suites | oracles **34**, enforcement **52**, all passing |
| New Node + static frontend suite | **57** passing (the real `D5A-2B2C-1B-BLOCK` run in Node; includes reports from the real endpoint) |
| Mutation checks (`scripts/diagnostics/d5a_2b2c_1b_mutation_checks.py`) | **17 / 17 mutants killed**: reversed conversion ratio; double conversion of the impedance voltage, the impedance current and a distance voltage leg; a distance current leg not converted; low-current floor not scaled; conversions using the declared instead of the effective side (bypass of the shared authority); assertions not validated; a request ratio replacing the authoritative one; a request ratio compensating for a missing one; a ratio required where none is needed; wrong-group VT/CT borrowing (two variants); mixed group declarations ignored; an inferred side accepted; calculated channels not guarded; the ratio-required flag inverted. Each production file was restored (`git status` clean afterwards). |
| Browser, affected set (11 spec files: the new `d5a_2b2c_1b_protection_side` (16 cases), `impedance_analysis`, `distance_protection_analysis`, `distance_dynamic_zones`, `distance_manual_input_layout`, `distance_resistive_reach_ux`, `distance_reverse_zone`, `analysis_related_waveforms`, `overcurrent_analysis`, `d5a_2b2c_1a_overcurrent_side`, `d5a_ui_002_group_details`) | **221 passed, 0 failed** (14.9 min, isolated :8102 / :8200) |
| Browser, `post_upload_readiness` (shared Primary-declared fixture; known baseline failures) | this tree **14 passed / 12 failed**; approved baseline `f24f1d7` **14 passed / 12 failed**; the two failing sets are **identical** (the Overcurrent / Impedance / Distance auto-resolve tests that expect a number on a fixture that declares Primary and has no VT/CT — they already fail on the baseline). |
| Locus / performance | `test_locus_shared_phasor_preparation.py` 10 / 10: the locus numerically equals independent single-point calls, and static preparation still runs once per role for the whole locus (6 role resolutions for a 50-point locus, not 300). The new suite additionally proves **one** authority evaluation per request, locus included. |

**Not re-run:** the Playback, Playback-ownership and Phasor shared-clock browser specs (they fail identically on the baseline and do not touch this change); the full browser suite.

**Performance / regression observations.** The authority is evaluated once per request (channel sides, group status and the two transformer lookups; no I/O beyond the in-memory registries). A selected-time request costs the same as before plus
the read; a locus shares one evaluation. The page issues one report read per context / phase|loop / output-side change — never per Playback tick or per locus point. The existing 1 ms-class numeric loop (`prepare_phasor_diagram` once per locus) is unchanged.

**Process notes.** (1) The legacy suites that failed on the first pass (54 tests in ten files) all asserted the retired contract or relied on a fixture that declares every channel `P`; each was restated, none deleted or weakened (§6). (2) Auto-discovery
creates Measurement Groups on upload, so fixtures configure the existing groups instead of creating new ones. (3) A request ratio that merely restates the authoritative ratio (e.g. 220 000:220 for 110 000:110) is accepted; the authoritative pair is what is echoed.


## 8. Decisions and limitations for the owner

1. **Legacy parameters** are kept as optional assertions (validated, never applied). They can be removed in D5A-2B2D.
2. **Calculated channels are blocked** (`calculated_channel_side_unavailable`) — the same owner-accepted safe blocking and temporary regression as Overcurrent. Previously a calculated V or I worked under the single basis.
   A lineage-aware enhancement is a future slice; until then the page says so plainly and offers nothing to configure.
3. **A recording with no P/S evidence** (BEN, CSV, …) needs an engineer's Level 1 or group setting before a recorded number is shown; the old "choose an unverified basis in the analyzer" path is gone.
4. **A Measurement Group with mixed declarations blocks every channel it owns** — even a loop whose own legs agree — until the engineer chooses a side for the group (consistent with Group Details).
5. **A multi-group quantity with different ratios** keeps the existing behaviour (`conflict` → blocked); no common ratio is invented.
6. **The two voltage legs of a distance loop must agree on a side** (and so the two current legs); Voltage and Current need not agree with each other.
7. **Zone classification while blocked** is the established "not operated" placeholder of the response schema (it has only two states); the page shows no classification at all.

## 9. DEV UAT checklist (after the owner authorises a push and deploy)

Use a recording whose Voltage and Current channels are in Measurement Groups with a VT/CT configured, and open Analysis → Impedance Locus, then Distance Protection (Recording input source).

1. **No Recording-basis input.** The panel shows `Impedance basis (output)` only; below it a read-only block "Recorded input — from Recording Details" with Voltage side, VT, Current side, CT. Output Secondary on a Primary recording shows the VT and CT (with their group names) that convert; switch the output to Primary and both show "not needed (… already Primary)" and the result still computes. The impedance basis selector stays editable.
2. **Independent sides.** In Recording Details set only the Voltage group to Secondary (Level 2): return to the analyzer — Voltage side reads "Secondary (set by engineer for <group>)", the VT row reads "not needed", Current stays Primary with its CT, a note says the recording declared Primary, and the number follows. Repeat with the Current group.
3. **Recording correction.** Set the recording side (Level 1) — both sides follow, the declaration is unchanged in Recording Details.
4. **Blockers.** Remove the CT (output Secondary, Primary current): the status row and the block name the group ("CT is not configured for '<group>'"), no number, no zone state, **Configure in Recording Details** opens that group, Related Waveforms still plot the channels. Likewise a missing VT, a group with mixed declarations ("conflicting declarations"), and a recording with no P/S evidence ("only inferred, not usable" / "not defined") until you set a side.
5. **Same-side needs nothing.** With both quantities on the output side, delete the VT/CT: the result still computes.
6. **Auto-derived VT.** A group with only a nominal voltage shows "132 kV / 110 V (Auto-derived, <group>)" and calculates.
7. **Numbers.** With VT 110 000:110, CT 1000:5, V 66 000 V / 66 V and I 400 A / 2 A, every Voltage × Current × output combination gives 165 Ω (Primary) / 33 Ω (Secondary) at ∠30°, in Impedance and in Distance (AB, BC, CA) and along the locus; Distance zones follow the converted impedance.
8. **Locus and playback.** Scrub and play: no extra requests per tick (network tab: only the two analysis requests, none to `protection-recorded-input`); changing the output side, phase/loop or any Recording Details setting updates the next result and the locus.
9. **Manual input source.** Unchanged — Voltage/Current basis, CT/VT and output-impedance controls all present; the recorded block is hidden.
10. **Direct API (optional).** `GET .../impedance?phase=A&analysis_time=…&impedance_basis=primary` with no other parameter computes from Recording Details; adding `voltage_side=secondary` against a Primary recording blocks with `voltage_side_contradicts_recording`; `vt_primary=1&vt_secondary=1` blocks with `request_vt_conflicts_with_authority` when a VT conversion is needed.
11. **Overcurrent** (D5A-2B2C-1A) behaves as before.

