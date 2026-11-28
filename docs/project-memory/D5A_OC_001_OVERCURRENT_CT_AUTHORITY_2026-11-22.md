# D5A-OC-001 — Recorded Overcurrent takes its CT from Recording Details

> **Partly superseded by D5A-2B2C-1A (2026-11-23, DEC-216 Amendment 5):** the CT is still the consumed channel's own Measurement Group's, but the Recording-basis control, the basis/CT sent in the request and the
> page-side side rules described below are gone — Recording Details decides the side and the backend enforces it ([D5A_2B2C_1A_OVERCURRENT_UNIFIED_SIDE_2026-11-23.md](D5A_2B2C_1A_OVERCURRENT_UNIFIED_SIDE_2026-11-23.md)).
> This document records the behaviour of the DEV-UAT build `a2b55eb`..`ad1b6ed`.

**Status:** implemented and fully regression-verified on `feature/d5a-oc-001-overcurrent-ct-authority`, branched from the accepted D5A UAT
commit `082b2a6` (`uat/dev-d5a-20261121`). Owner decisions OC-1..OC-3 approved (§4). **Not pushed, merged or deployed.** Awaiting owner authorisation for DEV deployment and UAT.
**Scope:** recorded Overcurrent only. Impedance, Distance, PU and physical calibration are untouched. D5A-2B2
(engineer-confirmed measurement-side storage) is **not** started.

## 1. Confirmed data flow before this slice, and the defects

| Question | Finding (verified in code) |
|---|---|
| Recorded vs Manual CT inputs | One shared pair, `wwOvercurrentState.settings.ctPrimary/ctSecondary`, edited through `#wwOvercurrentCtPrimaryInput` / `…SecondaryInput`. Recorded mode showed them when the Recording basis was Primary; Manual mode showed them for Direct-Current-Primary and always for Equipment Loading. |
| How `recording_basis` was chosen | A plain select, default `secondary`. Never pre-selected from the recording; nothing compared it with the channel's declared side. |
| Primary → relay-secondary | `convert_to_relay_secondary()` (`domain/overcurrent.py`): current normalised to amperes, then `× ct_secondary / ct_primary` for `primary`; unchanged for `secondary`. The compute endpoint is driven purely by its request parameters. |
| Channel and group resolution | `resolve_analysis_inputs()` with `OVERCURRENT_CURRENT_PHASE_A/B/C` → one `Ia/Ib/Ic` channel. The group is the Measurement Group owning that exact `ChannelRef` (`group_registry.group_for_channel`). |
| `protection-instrument-context?analysis=overcurrent` | Already correct: current-only (`voltage: null`), CT from the owning group, per-channel declared side, consumable only for `manual` / `recording_metadata`. It was simply **not consumed** by the Overcurrent page. |

Defects found (all in the recorded path):

1. **Duplicate CT entry.** A CT already configured in Recording Details had to be typed again in the analyzer, and could silently disagree with it.
2. **Wrong CT could be applied.** The typed CT belonged to no group, so one recording's CT was applied to another's channels, and a Manual-mode CT leaked into recordings (shared state).
3. **No side check.** A Primary basis on a recording declaring a secondary channel applied the CT ratio a second time (×CT_s/CT_p ≈ 0.005), and a Secondary basis on a primary recording skipped it. Neither was detected.
4. **Blocked result lost the channel.** A primary request without a valid CT returned `invalid_ct_values` with no `channel_ref`, so Related Waveforms said "No related waveform signals available". The frontend also required `status == computed` before declaring the waveform.
5. **Workspace reset left the CT, the typed values and the basis choice behind.**

## 2. What changed

**Backend** (`overcurrent_analysis_service.py`; commit `e7c895d`). A result blocked by an invalid/missing CT (primary basis) or an unsupported unit keeps `channel_ref` and `measured_rms_current_unit` when the phase's current channel resolved. Status, `reason_code`, message and the absent numerics are byte-identical; the CT check still precedes resolution, so precedence is unchanged (an unknown context still reports `invalid_ct_values`, never a 404). No schema change: the fields already existed.

**Frontend** (`frontend/index.html`; one commit). Overcurrent becomes a third consumer of the existing shared `wwCtVt*` block — no new configuration mechanism:

- **Read-only CT block** `#wwOvercurrentCtVtAuthority` in the settings grid: `CT 1200 A / 1 A (Manual, <group name>)` plus **Configure in Recording Details** (`wwNavigateToRdForGroup(sourceId, groupId)` of the owning group). No editor.
- **Recording mode has no CT inputs.** The inputs are Manual-only (`wwOvercurrentCtFieldsNeeded()` is false for Recording). Manual mode, its inputs and its three request paths are unchanged.
- **Request:** `recording_basis`, plus `ct_primary`/`ct_secondary` **only** for a primary recording **and** a `ratio_consumable` CT of the phase's own channel group. Never a partial pair, never a stale one, never a VT or `impedance_basis`.
- **Side handling:** declared side pre-selects the basis (Primary or Secondary) until the engineer chooses. Undeclared → the existing explicit select, marked **"unverified"** once chosen; the CT ratio is never used to infer a side. A basis that contradicts a declared side is **rejected** (below).
- **Refresh:** the report is re-read on context (re)load (also the path taken when returning from Recording Details), phase change, basis change and switching back to Recording; stale or superseded reads are discarded by the existing generation guard.
- **Reset:** `wwOvercurrentResetState()` clears the report (and any read in flight), the basis choice, and the Manual-mode CT values and inputs. `wwOvercurrentShowEmptyState()` clears the block when no context is selected.
- **Blocked ⇒ withheld, not shown stale:** a configuration blocker withholds the result and its chart point even if the backend could compute one; Related Waveforms still show the channel.
- Shared helpers were generalised, not duplicated: single-quantity side logic, a per-panel `title` / `basisSelectId`, and a `strictSides` flag that is `true` only for Overcurrent.

## 3. Mathematical behaviour — before / after

The calculation is **unchanged**: `relay_secondary = I_recorded_A` (secondary) or `I_recorded_A × CT_s / CT_p` (primary); IEC IDMT `t = TMS·k / (Mᵅ − 1)`, `M = I_relay / pickup`; the RMS window, units, pickup and above-pickup duration are untouched. What changes is **which CT is fed in, and when**:

| Case | Before | After |
|---|---|---|
| Primary recording, CT in Recording Details | CT typed by hand (any value) | CT of the owning group, once: 400 A × 5/1000 = **2.0 A** |
| Secondary recording | Secondary basis only if the user chose it; Primary applied the CT again → **0.01 A** (wrong) | Basis pre-selected from the declaration; no CT sent; 2 A → **2.0 A**. Choosing Primary is rejected |
| Primary recording, basis left at the default Secondary | 400 A treated as relay-secondary (wrong) | Pre-selected Primary; a Secondary choice is rejected |
| Primary basis, no usable CT | `invalid_ct_values`, waveform lost | Same status/message, **channel kept**; page names the group and links to it |
| Secondary basis, no CT | computed | computed (a CT is not needed; shown as such) |

Hand-derived oracle used by the tests: CT 1000:5; 400 A primary and 2 A secondary both give **2.0 A** relay-secondary, `M = 2`, `t = 0.1·0.14/(2^0.02 − 1)`; applying the ratio to the secondary value would give 0.01 A.

## 4. Decisions made here that the owner should confirm

| # | Decision | Why |
|---|---|---|
| OC-1 | **A basis that contradicts a *declared* side is rejected for Overcurrent** (no number is shown until it matches), whereas Impedance/Distance only warn. | The brief says "reject genuine side conflicts". Either direction produces a wrong relay-secondary current (a double conversion, or a missing one). Impedance/Distance keep their accepted warning-only behaviour. If the owner prefers warn-only, set `strictSides: false` for Overcurrent. |
| OC-2 | While the report is loading, a basis the engineer has not chosen shows no result ("Checking the CT configuration…") rather than a number on an unconfirmed basis. | Avoids a brief wrong value for a recording that declares primary. Costs a short status flash on context/phase change. |
| OC-3 | A workspace reset also clears the Manual-mode CT values and the Recording basis. | "No CT survives a workspace reset." Other relay settings (curve, TMS, pickup) are unchanged. |
| OC-4 | Impedance/Distance behaviour is not touched. | Scope. |

**Owner decisions (recorded 2026-11-22): OC-1, OC-2 and OC-3 are APPROVED as implemented.**

- **OC-1** — a requested Recording basis that contradicts a *reliably declared* measurement side is rejected.
- **OC-2** — "Checking…" is shown where needed to avoid presenting a potentially incorrect number.
- **OC-3** — a workspace reset clears the Manual CT and the recorded basis selection.
- The existing Impedance/Distance side-conflict behaviour (warn-only) is **not altered** in this slice.

**Recorded inconsistency, for the future measurement-side integration phase (not fixed here):** a declared-side contradiction is
a hard blocker for Overcurrent (`strictSides: true`) but only a warning for Impedance and Distance
(`strictSides: false`, the shared D5A behaviour accepted at `082b2a6`). The measurement-side integration phase (with D5A-2B2,
engineer-confirmed side storage) must decide one consistent policy across the three analyzers, with owner approval, and change the
accepted Impedance/Distance behaviour only then.

## 5. Limitations (deliberate or inherent)

- **Declared sides only.** If the recording's own side declaration is wrong, the engineer cannot override it until D5A-2B2 (engineer-confirmed side) — they can still choose a basis only where the recording is silent.
- **Calculated current channels** have no Measurement Group, so a primary conversion reports "not in a Current Measurement Group" and cannot be fixed from Recording Details.
- **One channel, so no CT "conflict".** Overcurrent resolves a single current channel; the `conflict` ratio status cannot occur.
- **Recorded CT is no longer the Manual CT.** A CT typed in Manual mode is never used for a recording (this was the shared-state defect above).
- Strict `current_side` on the compute endpoint is not adopted (needs separate owner authorisation, as for D5A).

## 6. Tests

| Layer | File | What it proves |
|---|---|---|
| Backend | `backend/tests/test_d5a_oc_001_overcurrent_ct_authority.py` | Owning-group CT per phase; an unrelated group's CT never borrowed; `manual`/`recording_metadata` consumable, untrusted/invalid not; declared vs unknown side independent of the ratio; hand-derived primary/secondary known answers and no double conversion; missing CT blocks only a needed conversion; blocked results keep the channel (mutation-checked: 6 tests fail without the service change); Recording Details changes and workspace isolation; the report never alters a calculation. |
| Static + Node (real helper block) | `backend/tests/test_frontend_d5a_oc_001_ct_authority.py` | What a request may carry, every blocker message and its group, side preselection / rejection / "unverified", loading and error handling, signature changes, stale-read discard, reset, rendering, Configure navigation, and that Impedance/Distance plans are unchanged. |
| Browser | `browser-tests/d5a_oc_ct_authority.spec.js` | 11 end-to-end cases on a real backend, including return from Recording Details, side rejection, reset and the stale-read race. |
| Updated deliberately | `test_frontend_overcurrent_analysis.py`, `overcurrent_analysis.spec.js` | Pinned the old rule that Recording mode shows CT inputs when the basis is Primary. |

### Final regression results (final tree `5c2af2a` plus this documentation commit; baseline `082b2a6`)

| Layer | Result |
|---|---|
| Backend, full suite (`pytest`, whole `backend/`) | **13,386 passed, 405 skipped, 0 failed**, exit 0. The earlier single failure (the old "computed-only" Related Waveforms rule) is the corrected legacy test. |
| Browser, affected specs on isolated ports (`overcurrent_analysis`, `d5a_oc_ct_authority`, `analysis_related_waveforms`, `d5a_ctvt_authority`, all five `distance_*`, `impedance_analysis`) | **194 passed, 0 failed** (11.9 min), including the two corrected layout tests. |

- **Baseline comparison.** Only two pre-existing backend test files and three pre-existing browser specs were modified; every
  other pre-existing test is untouched and passes. The baseline tree `082b2a6` was not re-run in this verification.
- **Legitimate coverage preserved.** Each changed legacy assertion was replaced by an equivalent or stronger one: the Recording-mode
  CT inputs became a read-only-block check plus an explicit "CT inputs are hidden in Recording" assertion; the CT Primary/Secondary
  overlap and within-card checks moved to Manual input source, where those inputs still exist; fixtures that now need a CT
  configure it through the same API Recording Details saves through. No assertion was deleted without a replacement.
- **Scope not run.** The rest of the browser suite (other pages) was not run; backend tests cover the unchanged areas.

## 7. Proposed DEV UAT checklist

1. Recording whose current channel is in a Current group with a manual CT (e.g. 1200/1): Overcurrent shows `CT 1200 A / 1 A (Manual, <group>)`, no CT input, Recording basis pre-selected to the declared side, result shown.
2. Clear that group's CT: primary recording → message names the group, **Configure in Recording Details** opens it, waveform still plotted, no number. Set the CT, return: the value appears immediately, no reload.
3. Same recording, change the Recording basis against the declared side: result withheld with the contradiction message; restore it: result returns.
4. Recording that does not declare its side: choose Primary → "unverified" note; the CT is used.
5. Switch phase A→B→C, and between two Bays (contexts): the block follows each phase's own channel/group.
6. Switch to Manual: CT inputs reappear and behave as before; back to Recording: the typed Manual CT is not used.
7. Clear workspace / start a new one: no CT, block or basis carries over.
8. Impedance Locus, Distance, PU and Waveform pages behave as in the last accepted UAT.
