# NF-3E — Stale calculated channels as inputs to engineering calculations: focused call-path review

**Date:** 2026-11-27 · **Scope:** the owner's request for a focused, **read-only** review. No consumer refusal was implemented; no code changed for this review.
**Principle under review (proposed):** *a stale calculated channel remains available for historical inspection but is not silently reused as a valid input for a new engineering calculation or assessment.* One staleness authority exists (`services/calculated_channel_staleness.py`); this review does not create another.

## 1. What can be stale

Staleness originates only at a **recording-following RMS channel** and propagates through `dependency_ids`. By the waveform-form propagation rule (`derive_waveform_form`) every stale channel has form **`rms`** (the RMS channel, add/subtract/multiply/reverse of RMS inputs) or **`unknown`** (absolute value; mixed-form add/subtract). A stale channel is never `instantaneous`.

## 2. Historical inspection versus new calculation

| Use | Examples | Must stay available? |
|---|---|---|
| **Historical inspection** | waveform, cursor and peak values, annotation anchor, per-unit display, list/inventory, delete | **Yes** (they go through `get_calculated_result` / `extract_calculated_waveform_range`; probed: HTTP 200 for a stale channel) |
| **New calculation** | creating a calculated channel; readiness reuse of an RMS channel | guarded (Phase B) |
| **New engineering assessment** | compliance measurement/assessment; oscillation; phasor family; overcurrent | see section 3 |

Consequence: the guard must sit at **consumer entry points**, never inside the shared array fetchers (`get_calculated_result`, `_resolve_input`), which also serve inspection.

## 3. Which consumers actually accept a stale calculated channel (evidence)

Method: code read of every service that resolves a calculated reference (`calc_registry` / `get_calculated_result` / `_resolve_input`), plus an in-process probe (scratchpad `probe_consumers.py`, no repository change) with a recording-following RMS channel `rms_follow` and `abs_of_rms`, made stale by a Manual 60 Hz change.

| Consumer | Accepts a calculated ref? | Stale `rms`-form input | Stale `unknown`-form input (abs of RMS) | Uses the staleness guard today? |
|---|---|---|---|---|
| **Compliance** (`compliance_series._raw` → `load_series`, `unit_problem`, `timebase_key`; used by readiness, trace and measurement) | yes | **accepted silently** (probe: 5,000 samples returned, no problem) | **accepted silently** (probe) | **no** |
| **Oscillation** (`derive_analysis_representation`, called by the representation and spectrum services; the other six endpoints build on them and were not probed individually) | yes | refused by form: `unavailable / already_magnitude` (probe) | refused by form: same (probe) | no (not needed today) |
| **Phasor analysis** (`_fetch_role_candidate`) and the services built on its roles: impedance, distance, sequence components, phasor diagram | yes (`get_calculated_result`) | refused by form: declared `rms`/`magnitude` is `FORM_NOT_ELIGIBLE` (code, `_waveform_form_eligible`) | falls to the signal detector; RMS-shaped data is classified magnitude/uncertain and refused (code; **not probed live**) | no |
| **Overcurrent** (`_fetch_current_candidate`) | yes | refused by form (code, `_waveform_form_eligible_for_rms`) | detector: eligible only if it says *instantaneous* (code; not probed live) | no |
| Event detection, line-to-line readiness/creation of sources | source inputs only (line-to-line creation also takes calculated operands) | n/a | n/a | line-to-line **creation: yes** (Phase B) |
| Protection context report, `resolve_analysis_inputs` | metadata only (type/unit/phase); no values | n/a | n/a | n/a (configuration) |
| Creation of calculated channels (generic) | yes | refused (409) | refused (409) | **yes** |
| Compliance readiness reuse (`find_equivalent_rms`) | yes | never reused | never reused | **yes** |

**Finding 1 (the real gap): compliance.** It is the only consumer that takes a stale RMS channel and uses its values with nothing in the way. It is also the main consumer of prepared RMS channels, so a Manual frequency change followed by an unrefreshed assessment would silently assess the old window.
**Finding 2 (defence in depth, not a present gap):** phasor, overcurrent and oscillation refuse a stale channel only **because of its waveform form**, not because it is stale. The reason code they give (`waveform_form_not_eligible` / `already_magnitude`) is true but does not mention staleness, and the `unknown`-form path depends on the detector's judgement (probed for oscillation; read from code for phasor/overcurrent).
**Finding 3:** the refusal vocabulary differs by consumer. Compliance raises typed errors that the router maps to HTTP (`InvalidCalibrationAuthorityError` → 422); oscillation raises typed errors mapped to HTTP (`representation_unavailable` → 409); phasor and overcurrent return a 200 result with `reason_code`.

## 4. Where the shared guard can be reused (no second authority)

`assert_inputs_not_stale(refs, workspace_id, calc_registry, frequency_access)` takes channel references and the central accessor. Every entry point below already holds both:

| Entry point | Has `frequency_access`? | Change |
|---|---|---|
| `compliance_series.load_series` (the one reader behind compliance trace/measurement/assessment) | not in `Registries` today; the callers (`compliance.py`, readiness, trace) hold it | add one **additive field** `frequency_access` to `Registries`; call the guard in `load_series` |
| `oscillation_representation_service.derive_analysis_representation` (the shared derivation used by the representation and spectrum services) | **yes** (parameter) | one call before resolving the input |
| `phasor_analysis_service._fetch_role_candidate`, `overcurrent_analysis_service._fetch_current_candidate` | **yes** (they read the frequency from it) | one call each, **optional**: only for a staleness-specific reason instead of the form reason |

## 5. Minimum changes for consistent refusal semantics (proposal; nothing implemented)

1. **Compliance (required for the principle):** the guard in `load_series` + the `Registries` field; `stale_calculated_input` mapped to **409** in the compliance router (same code and message as creation). Readiness (`unit_problem`, `timebase_key`) should report a stale measurement channel as a blocked/needs-action state with the same sentence rather than raise, so the card explains it; that is a wording/state change in one function and is for owner decision.
2. **Oscillation (optional, defence in depth):** the same call in `derive_analysis_representation`; map the code to 409 in `api/v1/oscillation.py` (it already uses 409 for `representation_unavailable`).
3. **Phasor family and overcurrent (optional):** no change now (refused by form); add the same call only if the owner wants the refusal reason to say *stale* and to remove dependence on the detector for `unknown`-form descendants. Their result-level `reason_code` convention would then need one new value, `stale_calculated_input`, in the existing enumerations — a public-vocabulary change, so it needs approval.
4. **Do not** guard `get_calculated_result`, `_resolve_input`, waveform, cursor, peak, per-unit or list paths (historical inspection).
5. Frontend: the compliance panel already shows typed backend messages; no new UI. The Waveform sidebar marker stays out of scope.

Tests for step 1 would reuse the existing staleness fixtures (stale RMS → compliance load refused; current → accepted; explicit → accepted; inherited → refused), plus a static guard that every production reader of calculated arrays for a **new assessment** passes the authority.

## 6. Not done / limits of this review

No consumer refusal was implemented. Phasor, overcurrent, impedance, distance and sequence were reviewed from code, not probed live (they need an engineering context with calculated members). The review did not audit analysis engines beyond calculated-reference acceptance.

## 7. Governance compliance (DEC-218)

One authority reused, none added; no decision reopened; no kernel or numerical change; no PU artefact touched.
