# NF-3E — Stale calculated channels (Phase B): implementation record

**Date:** 2026-11-27 · **Decision base:** [DEC-217](DECISIONS.md), [DEC-218](DECISIONS.md), [NF-3A](NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md) (O-4, O-6, O-8, O-10), [NF-3E Phase A](NF_3E_PHASE_A_ASSESSMENT_2026-11-27.md) and the owner's Phase B authorisation (2026-11-27).
**Branch:** `feature/nf-3e-calculated-channel-staleness`, worktree `.local-data/nf-3e`, from `65390d3` (Phase A `d57a279`, `e0d11c4`).
**Status:** implemented and verified with **focused** tests only (the PU G4 browser run is still active; the full backend and browser gate is deferred to owner review).
**Not pushed, merged or deployed. No gate is activated. No PU worktree, branch, PR #14 or running process was touched.**

## 1. Owner decisions applied

| Decision | Applied as |
|---|---|
| **Option B** (stale inputs) | Existing stale channels stay viewable, inspectable and deletable; dependants inherit staleness (direct and transitive); creating a NEW calculation on a stale input is refused with the typed `stale_calculated_input` (HTTP 409) whose message names the stale channel, why, and what to do. Verified for the generic creation path, RMS-of-RMS, the line-to-line creation path and the readiness identity (a stale channel is never reused as a current RMS). |
| **Preserve values** | Nothing is recomputed, overwritten or removed by a frequency change (tested: waveform and stored parameters identical after Manual and after Auto). Staleness is **derived on every request** from the central accessor; no flag is stored. |
| **Intent** | A calculation is **recording-following** or **explicitly selected**. Intent is declared by the caller (`parameters.nominal_frequency_basis`), never inferred from numerical equality (tested: an explicit 50 Hz and a following 50 Hz channel on a 50 Hz recording behave differently after a Manual 60). |
| **Following staleness** | Stale while the stored frequency differs from the grounding recording's effective frequency, or while that recording has no usable frequency; current again as soon as they agree (Auto, or Manual set back to the stored value). Inherited staleness clears only when every stale ancestor is current (tested with two ancestors). |
| **Explicit frequency** | Never stale on its own account; **still inherits upstream staleness** (tested: an explicit RMS over a recording-following RMS goes stale through it and clears with it). |
| **Power** | Not assessed directly (NF-3F); stored parameters and mathematics unchanged; a power channel inherits upstream staleness (tested). |
| **O-8** (corrected after review) | The RMS builder **preselects** the recording's applicable (effective: Auto or Manual) frequency as the first option of the existing dropdown, **"Recording (X Hz)"**, and never imposes it: 50 Hz and 60 Hz remain selectable. Accepting the preselection declares `nominal_frequency_basis: recording`; choosing 50 or 60 Hz is a deliberate **explicit** selection even when equal to the recording's (the option chosen is the intent, never the number); returning to the Recording option restores following. An unusable recording preselects nothing and requires an explicit choice; an explicit choice is preserved when the recording's frequency loads or changes later. The first version locked the field; that was wrong and is replaced. One dropdown, existing layout and styling. |
| **O-10** | The eligibility pre-check validates the frequency with the same authority as creation: `invalid_nominal_frequency`, HTTP 400, instead of an HTTP 500 for 0. A genuine internal failure still returns 500 (tested). |
| **NF-2** | One `nominal-frequency-changed` in-page notification after a successful Manual or Auto change (`workspaceId, sourceId, revision, effectiveHz, origin`). Its subscriber re-reads calculated-channel **metadata** and the builder's applicable frequency; it fetches no waveform and creates nothing. The backend stays the authority for staleness. |
| **UI** | One small "stale" marker and one advisory line on the calculated-channel list row, naming the reason and the root cause for a dependant; the existing `--warn` token and row layout; no dialog or panel. Wording and placement are subject to UAT. |

## 2. The provenance change, reconciled with O-6 (for owner confirmation)

O-6 (approved in NF-3C) put the recording's **origin and revision** in new calculated-channel parameters. They say *which recording frequency was used*; they cannot say *whether the engineer chose it or the calculation follows the recording*, and equal numbers must not be read as intent. The **minimum necessary change** is therefore one additive parameter on an RMS channel, `nominal_frequency_basis` (`recording` | `explicit`):

* **Request:** optional; **omitted means `explicit`** (the caller supplied the number; no inference). An unknown value is `invalid_nominal_frequency` (400). `recording` is refused (400) when the stated value is not the recording's current effective frequency (a concurrent change), so a channel is never stale at birth.
* **Stored (API-created RMS channels):** `nominal_frequency_basis`, `nominal_frequency_origin`, `nominal_frequency_revision` (O-6), in addition to the existing three parameters. The origin and revision are informational; staleness compares frequencies.
* **Who declares `recording`:** the builder (locked frequency) and the compliance preparation (the step's frequency is the recording's effective value just resolved). Direct API callers that send only the number create explicit channels.
* No existing field is removed or changed; no stored value changes. Approved changes to frozen baselines are data in `tests/nf3e_approved_changes.py`.

## 3. Implementation

| File | Change |
|---|---|
| `services/calculated_channel_staleness.py` (new) | `frequency_staleness()` (derived state, causes, memoised DAG walk), `assert_inputs_not_stale()`, the wording of the refusal |
| `services/errors.py` | `StaleCalculatedInputError` (`stale_calculated_input`) |
| `services/calculated_channel_service.py` | `frequency_access` kwarg; stale-input refusal; basis validation and verification; origin/revision stamp; eligibility validates the frequency (O-10) |
| `services/line_to_line_voltage_service.py` | refuses a stale calculated operand |
| `services/compliance_readiness_service.py` | `find_equivalent_rms` never reuses a stale channel; preparation declares `recording` and passes the authority |
| `api/v1/calculated_channels.py`, `schemas/calculated_channel.py` | 409 mapping; the derived `frequency_staleness` object (`state`, `assessment`, `causes[]`) on create and list responses |
| `frontend/index.html` | notification, metadata refresh, builder authority/preselection/intent, marker and advisory |

## 4. Verification (focused; full gates deferred)

| Check | Result |
|---|---|
| **New backend tests** (`test_nf3e_staleness.py`, written failing-first: 31 failed / 7 passed before the implementation) | **42 passed**: intent and provenance, recording-following staleness, return to the original frequency (Auto and Manual-equal), unusable recording, preserved values, explicit frequency, equal numbers with different intent, direct and transitive inheritance, inheritance kept while another ancestor is stale, two recordings, frequency-independent and power channels (incl. inherited), Option B refusal (direct, transitive, RMS-of-RMS, source inputs, any list position, lifts when cleared, viewable and deletable), the readiness identity, O-10 (400 for 0, -50, 0.5, 1001; valid unchanged; an internal failure stays 500), static guards that every production creation path passes the authority |
| **Static frontend** (`test_frontend_nf3e_staleness.py`) | 9 passed. The whole `test_frontend_*` subset ran at **2,321 passed, 1 failed**: the NF-2 isolation guard caught the builder reading an NF-2 helper (`wwRdNfUrl`); fixed by building the URL locally (the guard was not weakened); the affected files were re-run: 73 passed |
| **Focused backend regression** (calculated-channel API/service/domain/power/ROCOF, compliance readiness, line-to-line, RMS R0 baseline + shared authority + golden vectors, NF-3B/C/D baselines, guards and oracles, NF-3E Phase A/oracles/staleness, timing/calibration/per-unit calculated tests) | **1,502 passed, 3 xfailed (strict, NF-3F/G/H), 0 failed** |
| **Approved changes to frozen baselines** | data only (`tests/nf3e_approved_changes.py`): R0 eligibility 0/-50/0.5/1001 and one service scenario (O-10); additive provenance and `frequency_staleness` on R0 and Phase A channel bodies. The strict O-10 xfail was flipped; pinned inventories (call-path guard, frontend token counts) and two static tests were updated deliberately. Historical files are unedited |
| **Mutation checks** (`evidence/nf-3e-2026-11-27/mutation_checks.py`, 19 mutations of the predicate, refusal, intent/stamp, O-10, readiness and API wiring) | **19 of 19 killed**: 17 on the first pass; M4 (omitted basis inferred as following) and M11 (a source input first hides a later stale input) survived and exposed two test gaps, closed by two tests and killed on the re-run |
| **New browser spec** `nf3e-calculated-channel-staleness.spec.js` (isolated ports 8200/8102) | **5 passed**: marker and advisory after a Manual change, values unchanged, explicit channel unflagged, Auto clears, the single notification's detail, inherited marker naming the root, 409 refusal message, builder preselects and locks the Manual frequency and declares `recording`, unusable recording requires a choice and declares `explicit` |
| **Related existing browser specs** (calculated-channel preview/presentation/ROCOF/power/null-handling, compliance readiness; isolated ports) | 57 passed, **6 failed: `calculated-channel-preview` x5 and `compliance_readiness:212`, all failing identically on the unmodified NF-3D tip `65390d3`** (a missing `#wwUnitEngineeringBtn` / `#measurementGroupsOverlay`: the known Waveform/PU-group set, unresolved and unrelated). No regression |
| **Not run** | the full backend suite (~50 min) and the full browser suite (both deferred: G4 holds the machine); the NF-2 browser spec (it serves the repository's `config.js`, pinned to :8000, which is G4's backend; the notification it needs is covered by the new spec) |

## 5. Remaining limitations and unresolved findings (recorded, not implemented)

1. **Scope of Option B:** it refuses new *calculated channels* on stale inputs. Analyses that accept a calculated channel (phasor, overcurrent, compliance, oscillation) are not refused and do not show the marker; the stored channel keeps the frequency of its reference recording (the existing first-recording rule, NF-3G).
2. The marker appears on the Calculated Channels manager list; the Waveform sidebar legend and the trace names do not show it.
3. **Power channels** keep the fixed 50 Hz and are not assessed (NF-3F). **F-1** (rounded sample-count RMS window, ~0.3 %) is unchanged by instruction.
4. **Mixed-recording** channels: only the existing reference-recording rule applies; each ancestor RMS is compared with its own recording, but no new selection policy was introduced.
5. **O-10 widening to confirm:** the same validation also turns the eligibility pre-check's former `200 uncertain/likely already RMS` for **-50, 0.5 and 1001 Hz** into 400 (it already was 400 at creation). If only the former HTTP 500 (0 Hz) should change, the range check can be narrowed.
6. API callers that omit `nominal_frequency_basis` create explicit channels and are never flagged (by design; see section 2).
7. The browser specification `nf3e-calculated-channel-staleness.spec.js` was run on isolated ports (5 passed); wording and placement of the marker and advisory still need owner UAT.
8. A Manual value is still gated (server and UI); no gate was activated.

## 6. Governance compliance (DEC-218)

Applied as written: DEC-217 (one authority; never the first recording's frequency), DEC-218, NF-3A O-4/O-6/O-8/O-10, the NF-3B/C/D baseline policy (history never edited; approved changes are data in `nf3e_approved_changes.py`, strict xfail flipped for O-10), and the owner's Option B and intent policy. No decision was reopened; no engineering formula was added or changed (the RMS kernel and F-1 are untouched); the PU workstream was not touched.
