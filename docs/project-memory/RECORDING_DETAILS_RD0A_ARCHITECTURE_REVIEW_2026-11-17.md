# RD-0A: Recording Details Metadata Enhancement — Architecture Review

**Date:** 2026-11-17  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Status:** Investigation complete — no production code changed, no git operation performed  
**Prerequisites:** Read `RECORDING_METADATA_AUTHORITY_AUDIT.md` and `RECORDING_METADATA_AUTODETECTION_AUDIT.md` first.

---

## A. Executive Summary

The existing codebase is better-prepared for Recording Details metadata enhancement than the earlier
audit suggested. The automatic detection pipeline (measurement group clustering, engineering context
detection, auto-base configuration) is fully wired and runs synchronously at every upload. The
authority gate (`is_base_eligible_for_pu`) is live, not deferred. The primary/secondary secondary-
denominator path is wired. The three in-memory registries are wired into API routers.

**Four docstrings are stale** — they describe features as not-yet-wired when they already are (see
Section J). These will cause developer confusion and must be corrected in the next approved slice.

**One significant UX provenance risk** exists: a Measurement Group with `status = "suggested"` and
`base_authority = "auto_resolved"` resolves as PU-eligible (`pu_status = "configured"`) but is
simultaneously listed by the UI as "needs review." An engineer can be in PU mode on an unconfirmed
group without realizing the group membership itself was never verified (see Section E).

**Browser refresh behavior** is better than expected: the workspace_id persists in localStorage;
the backend retains all in-memory data for the duration of the server process. A refresh does NOT
require re-upload — provided the server is still running (see Section F).

**Recording-level VT defaults do not exist** in the current codebase — this is a proposed concept
only. `SourceMetadata` has no VT-related fields.

**Recommended immediate scope:**

- **RD-1** (read-only display, zero new backend logic): Surface detection results already computed.
- **RD-2** (first editable fields): nominal_frequency override, station/recorder display-name override.

---

## B. Approved Owner Decisions

(Summary of architecture decisions supplied with this task. These are established requirements, not
proposals.)

### B.1 Metadata ownership
- **Recording level:** identity, nominal frequency, original imported metadata, recording-level VT defaults *(proposed — not yet implemented)*.
- **Voltage Measurement Group:** nominal system voltage, L-L/L-N voltage reference, group-specific VT overrides.
- **Current Measurement Group:** CT primary/secondary ratings.
- **Channel level:** overrides only. Original imported metadata immutable.
- **Engineering Context:** measurement roles and relationships — not CT/VT owner.
- **Analysis level:** explicit analysis-specific overrides. Must not silently modify recording metadata.
- **Standalone calculators:** fully independent of recording metadata.

### B.2 CT/VT conventions
- VT preferred format: `132 kV / 110 V`. CT preferred format: `1200 A / 1 A`.
- Suggested secondary defaults: 110 V (L-L reference), ~63.5 V (L-N reference).
- CT ratings must NOT be inferred from measured current magnitude.
- Imported CT/VT from CFG may be presented as candidates; engineer must confirm.
- Waveform samples remain unchanged. Engineering conversions only within explicit calculation context.

### B.3 Nominal frequency
- Import where available; identify assumptions where not.
- Allow recording-level user override. Preserve original imported values.
- Propagate effective frequency to applicable consumers. Invalidate dependent derived results on change.
- Do not change waveform samples.

### B.4 Recording identity
- Preserve original filename, station name, recorder/IED identity.
- Allow user-defined recording display names and display overrides for station/recorder names.
- Keep internal recording identifiers immutable. Display-name changes must not affect calculations.
- Allow overrides to be reset to imported values.

### B.5 Persistence
- Engineering metadata remains session-scoped (DEC-015).
- No permanent waveform storage, database-backed recording metadata, or cross-session restoration.

---

## C. Verified Current Implementation

### C.1 What exists today (code-verified)

**`SourceMetadata` fields** (`backend/app/domain/source.py:84-158`):
- `station_name`, `recorder_name`, `nominal_frequency`, `timing_reference`, `start_time`,
  `trigger_time`, `sample_count`, `duration_seconds`, `sampling_rates`, `samples_per_rate`,
  `file_size_bytes`, `preparation_provenance`, `time_basis`, `time_reference_interpretation`.
- NO VT-related fields. NO CT-related fields. NO display-name override fields. NO user_nominal_frequency.

**WorkspaceRegistry** (`backend/app/services/workspace_registry.py:54-182`):
- Pure in-memory dict keyed by `(workspace_id, source_id)`. No TTL, no DB, no disk.
- Time-reference overlay keyed by `(workspace_id, source_id, page_session_id)` — session-local only.

**Three satellite in-memory registries** are wired into API routers (`backend/app/api/v1/measurement_groups.py`, `per_unit.py`, `compliance.py`, `sources.py`):
- `MeasurementGroupRegistry`
- `VoltageGroupConfigRegistry`
- `CurrentGroupConfigRegistry`

**Upload trigger** (`backend/app/services/workspace_preparation_service.py`):
- Runs three detection passes synchronously for every upload.
- Results in: `STATUS_SUGGESTED`/`STATUS_NEEDS_REVIEW` groups + auto-base `VoltageBaseConfiguration` with `base_authority`.

**Authority gate** (`backend/app/domain/voltage_group_config.py:263-283`):
- `is_base_eligible_for_pu()` IS called (contradicts docstring — see Section J.1).
- `auto_resolved + STATUS_SUGGESTED` bypasses the group-status gate (confirmed intentional, tested).
- `needs_review` and `unavailable` block PU regardless of group status.

**Secondary-denominator path** (`backend/app/domain/voltage_group_config.py:285-313`):
- `base_reference_side = "secondary"` with valid `secondary_voltage_ll_v` IS active.
- Contradicts docstring — see Section J.3.

**Current resolver** (`backend/app/domain/current_group_config.py:267-271`):
- Mirrors voltage resolver exactly. Same `auto_resolved + STATUS_SUGGESTED` bypass.

**Nominal frequency consumers** (all read `active.metadata.nominal_frequency` at request time):
- `overcurrent_analysis_service.py:128`
- `compliance_measurement_service.py:298`
- `compliance_readiness_service.py:252`
- `phasor_analysis_service.py:215, 245`
- `oscillation_representation_service.py:95`
- RMS calculated channels store `nominal_frequency_hz` as a creation-time parameter (from API body, not from metadata).

**`nominal_frequency` is NOT user-editable.** No PATCH endpoint exists. No display-name override exists for `station_name`/`recorder_name`. Both are planned but not implemented.

### C.2 What does NOT exist today
- Recording-level VT default fields (not in `SourceMetadata`).
- User-editable `nominal_frequency` (no PATCH endpoint).
- Display-name override for `station_name`/`recorder_name`.
- Waveform corroboration wired at upload (exists as module but `waveform_provider` not passed).
- CT/VT suggestions in analysis forms.
- Provenance labels visible in Recording Details.

---

## D. Metadata Ownership and Effective-Value Resolution

### D.1 Proposed 7-layer resolution model

| Layer | Scope | Source | Verification | Conflict detection | Reset path | Dependency invalidation |
|---|---|---|---|---|---|---|
| **1. Imported** | Channel / Recording | File format | None — raw import | Contradictions flagged by auto-base evidence | Cannot reset (immutable) | N/A |
| **2. Auto-detected** | Group | Upload pipeline | None — computed | `has_contradictions` flag + `needs_review` state | Re-run `/suggest` | Transitions to `unavailable` on contradictory new evidence |
| **3. Defaulted** | Recording | Standard assumption | None — flag only | `nominal_frequency_assumed` bool in `preparation_provenance` | Override at Layer 4 | Downstream consumers update on change |
| **4. Recording-override** | Recording | Engineer input | Explicit entry | Conflict with imported shown as badge | Reset to imported value | All consumers propagate new value at next request |
| **5. Group-override** | Measurement Group | Engineer input | Explicit entry | Conflict with auto-resolved shown as badge | Reset to auto-detected | PU denominator recalculated |
| **6. Channel-override** | Channel | Engineer input | Explicit entry | Conflict with group shown as badge | Reset to group value | Per-channel PU denominator recalculated |
| **7. Analysis-override** | Analysis result | Per-analysis | Per-analysis | Conflict with group shown as badge | Per-analysis | Does not propagate back to recording |

### D.2 Value precedence ≠ engineering authority

A higher-priority override does not establish physical validity. Specifically:

- Layer 4 (recording-override nominal frequency) overrides Layer 3 (assumed 50 Hz) — but it is still
  an engineer assertion, not an instrument measurement.
- Layer 5 (group-override nominal voltage) overrides Layer 2 (auto-detected) — but it is still the
  engineer's stated system voltage, not a nameplate VT primary voltage.
- Imported CT/VT ratios (`primary_ratio`/`secondary_ratio` on `AnalogChannelSummary`) are Layer 1
  (imported) but should be labelled "Declared in file — verify nameplate" before use as a CT/VT
  primary rating. They are candidates, not nameplate ratings.

Each layer must carry an explicit **provenance label**: Imported / Detected / Defaulted / Suggested /
Verified / Unresolved. Recording Details must not display a bare value without its provenance.

### D.3 Conflict detection rules

| Metadata field | Conflict scenario | Current behavior | Required behavior |
|---|---|---|---|
| `nominal_voltage_ll_kv` | Auto-detected kV conflicts with engineer-entered kV | None — engineer entry silently wins | Show warning badge "Overrides auto-detected {X} kV" |
| `nominal_frequency` | Assumed 50 Hz conflicts with engineer-entered | No PATCH endpoint exists | Show "Assumed — no source declaration" badge; allow override |
| `base_authority` | Previously `auto_resolved`; evidence later contradicted | `unavailable` transition exists but not triggered by any existing workflow | Need: trigger invalidation when group membership changes |
| `secondary_voltage_ll_v` | Explicit imported secondary conflicts with 110 V default | Imported value used if present | Show "Imported {X} V — verify nameplate" |

---

## E. Automatic PU Authority Safety Assessment

### E.1 Answers to the 10 investigation questions

**Q1 — Which functions implement the authority gate?**

[FACT] `is_base_eligible_for_pu()` in `backend/app/domain/base_authority.py:71` is the predicate.
It is called at `voltage_group_config.py:265` and (by symmetry) `current_group_config.py` for the
current resolver. Both resolvers check it before all other steps.

**Q2 — What exact conditions permit automatic PU eligibility?**

[FACT] From `voltage_group_config.py:263-283`:

```
If config is not None AND NOT is_base_eligible_for_pu(config.base_authority):
    → STATUS_BASE_REQUIRED ("base_invalidated")

If is_auto_resolved(config.base_authority) AND group.status == STATUS_SUGGESTED:
    → skip_status_gate = True  → may proceed without confirmed/manual status
```

A `STATUS_SUGGESTED` group with `base_authority = "auto_resolved"` resolves as PU-eligible
provided `nominal_voltage_ll_kv` and voltage reference are also valid. No engineer confirmation
of the group is required.

**Q3 — Which conditions require explicit engineer confirmation?**

[FACT] Engineer confirmation (confirmed/manual group status) is required when:
- `base_authority` is `legacy_manual` or `manual` — these only bypass the gate for confirmed/manual groups.
- `base_authority` is `needs_review` or `unavailable` — these block PU entirely.
- `base_authority` is `None` / no config exists — falls through to `voltage_base_not_configured`.

For `auto_resolved`: **the group status gate is bypassed** — no confirmation required.

**Q4 — How is automatic resolution distinguished from verification?**

[FACT] Via `is_auto_resolved(config.base_authority)` returning `True`. The `is_engineer_approved()`
predicate (`base_authority.py:88`) returns `False` for `auto_resolved`. The distinction exists in
code but is **not surfaced in the current UI** — both auto-resolved-suggested and confirmed-manual
groups appear identically as "ready" in the PU display.

**Q5 — What happens when detection evidence conflicts?**

[FACT] `base_authority` is set to `"needs_review"` by `auto_base_service.py` when evidence is
insufficient or contradictory. `is_base_eligible_for_pu("needs_review")` returns `False` → PU is
blocked. This path is well-tested (53 tests in `test_slice5c1_authority_gate.py`).

**Q6 — What happens after Measurement Group membership changes?**

[OPEN — RISK] No code path currently transitions `base_authority` to `"unavailable"` when group
channel membership changes. The `should_invalidate_on_contradiction()` predicate exists
(`base_authority.py:125`) but is not called by any service when a group is modified. If an engineer
changes group membership after auto-resolution, the existing `auto_resolved` base is silently retained
even though the evidence that produced it may no longer apply.

**Q7 — What happens when nominal voltage is overridden?**

[FACT] Engineer-entered `nominal_voltage_ll_kv` via `set_voltage_base()` sets `base_authority =
"manual"` (`voltage_group_config_service.py:38, BASE_AUTHORITY_MANUAL`). Manual authority is always
PU-eligible for confirmed/manual groups. The previously auto-resolved value is replaced. No
invalidation of downstream results (no existing result-caching).

**Q8 — Can an incorrect automatically resolved voltage propagate into downstream calculations?**

[FACT — POTENTIAL RISK] Yes. If auto-resolution reaches `auto_resolved` with an incorrect nominal kV
(e.g. a 1991 COMTRADE file with no PS flag and ambiguous channel names resolving to the wrong
hypothesis), that incorrect base immediately drives PU display for all channels in the suggested
group. No waveform corroboration occurs at upload (the waveform_provider is not passed). The only
barrier is the `needs_review` path, which requires the evidence pipeline to identify the conflict.

Vectors for incorrect propagation:
- COMTRADE 1991: no PS flag → `measurement_side = "unknown"` → auto-base returns `needs_review` → blocked. LOW RISK.
- COMTRADE 1999 primary-side, ambiguous kV token: hypothesis resolver runs, may produce `ambiguous` → `needs_review` → blocked. LOW RISK.
- COMTRADE 1999 primary-side, unambiguous kV token but physically wrong recorder metadata: auto-resolves with incorrect kV → PU active. **MEDIUM RISK** — depends entirely on the recorder having written correct CFG metadata.

This is the fundamental limitation of metadata-based (vs. waveform-based) resolution. It is an
accepted limitation under the existing approved architecture.

**Q9 — What existing tests protect this behavior?**

[FACT] 203 tests across three test files:
- `test_slice5c1_authority_gate.py`: 53 tests — authority gate + bypass + service transitions
- `test_base_authority_domain.py`: 93 tests — domain predicates
- `test_slice5d1_ps_integration.py`: 57 tests — PS flag / secondary denominator integration

**Q10 — Are the current UI labels potentially misleading?**

[FACT — NEEDS CLEARER UI] Yes. A group with `status = "suggested"` and `base_authority =
"auto_resolved"` simultaneously appears:
- As "ready" in the PU groups summary (`pu_status === "configured"` — `index.html:35922`)
- As counted in "need review" in the same summary (`status === "suggested"` — `index.html:35923`)

An engineer sees "1 ready · 1 need review" for a group that is both. The comment in `index.html:16943`
documents this correctly ("no Measurement Group confirmation is required") but the visible UI text
does not explain why a "suggested" group can be PU-ready without being confirmed.

### E.2 Classification summary

| Finding | Classification |
|---|---|
| Authority gate is wired and working | VERIFIED SAFE |
| `needs_review`/`unavailable` block PU | VERIFIED SAFE |
| `auto_resolved + STATUS_SUGGESTED` bypass is intentional | VERIFIED SAFE |
| 203 tests covering gate behavior | VERIFIED SAFE |
| No invalidation when group membership changes after auto-resolution | POTENTIAL RISK — requires owner review |
| Incorrect recorder metadata propagates as `auto_resolved` | POTENTIAL RISK — accepted limitation |
| "suggested" group shown as both "ready" and "need review" simultaneously | NEEDS CLEARER UI |
| `base_authority` not visible in Recording Details | NEEDS CLEARER UI |

---

## F. Workspace Refresh and Lifecycle Findings

### F.1 Backend lifecycle

[FACT] All backend state is in-process, in-memory. No database, no disk storage, no TTL.

- `WorkspaceRegistry` (sources + time-reference overlays): `backend/app/services/workspace_registry.py`
- `MeasurementGroupRegistry`, `VoltageGroupConfigRegistry`, `CurrentGroupConfigRegistry`: sibling registries
- All entries survive until: (a) explicit DELETE call, (b) server process restart, (c) "Start New Workspace" action.

### F.2 Frontend lifecycle

[FACT] `workspace_id` is stored in `localStorage` at key `"powerwave.workspaceId"` (`index.html:16508`).

- `currentWorkspaceId()` reads from localStorage, creating a new UUID if none exists (`index.html:16510-16516`).
- `powerwavePageSessionId` is generated fresh with `crypto.randomUUID()` per page load (`index.html:16462`).
  It is intentionally NOT stored in localStorage — time-reference overlays are page-local.
- Every API request to `/api/v1/workspaces/` carries `X-Powerwave-Session: {pageSessionId}` (`index.html:16479`).

### F.3 After a browser refresh

| Component | After refresh | Evidence |
|---|---|---|
| `workspace_id` | **Survives** — read from localStorage | `index.html:16511` |
| Backend sources / measurement groups / PU config | **Survives** — if server process still running | `workspace_registry.py` in-memory |
| Page session ID (`powerwavePageSessionId`) | **Lost** — fresh UUID on reload | `index.html:16462` |
| Time-reference interpretation overlay | **Lost** — keyed by old page session | `workspace_registry.py:89` |
| Frontend displayed channels / waveform view | **Lost** — re-initialized from scratch | Frontend state only |
| RMS/calculated channel definitions | **Survives** — stored in `CalculatedChannelRegistry` | (not page-scoped) |

**Practical result:** After a browser refresh, the user recovers their recordings and measurement groups
without re-upload. The waveform view and time-reference overlay must be reconfigured. This is better
than the earlier audit implied ("user must upload again") — that was not accurate for a simple browser
refresh (only for a server restart or explicit "Start New Workspace").

### F.4 Server restart behavior

After a server restart: ALL state is lost. The `workspace_id` from localStorage no longer matches
any backend entries. The user must re-upload. No configuration is recoverable.

---

## G. CT/VT Configuration and Conversion Boundaries

### G.1 Current state — CT/VT storage

| Field | Location | Source | Used for |
|---|---|---|---|
| `primary_ratio` | `AnalogChannelSummary` on each channel | COMTRADE CFG fields 10/11; BEN32 SubBen normalize | Stored only — descriptive |
| `secondary_ratio` | `AnalogChannelSummary` on each channel | COMTRADE CFG fields 10/11 | Stored only — descriptive |
| `measurement_side` | `AnalogChannelSummary.measurement_side` | COMTRADE 1999 PS flag | Used by auto-base evidence pipeline |
| `secondary_voltage_ll_v` | `VoltageBaseConfiguration` | Auto-computed from secondary_ratio, or engineer-entered | Used by secondary-denominator path |
| CT primary/secondary ratings | `CurrentBaseConfiguration.primary_ka` / `secondary_a` | Engineer entry only (analysis forms) | Used for current PU (kA base) |

**Double-scaling risk: NONE currently.** `primary_ratio`/`secondary_ratio` are stored as metadata and
never applied to waveform samples. All existing physical scaling is applied during import (file
coefficients only). Introducing automatic CT/VT conversion WOULD create double-scaling if the file is
already primary-side scaled — this risk is explicitly managed by the approved safety rules.

### G.2 Conversion boundaries

| Operation | Permitted | Requires |
|---|---|---|
| Displaying `primary_ratio` as VT/CT candidate suggestion | YES | Provenance label "Declared in file" |
| Auto-applying `primary_ratio` to waveform samples | NO | Never — per approved architecture |
| Using `secondary_voltage_ll_v` as PU denominator | YES | `base_reference_side = "secondary"` + valid value + engineer confirmation |
| Using `nominal_voltage_ll_kv` as PU denominator (primary path) | YES | `auto_resolved` or `manual` authority + group resolved |
| CT primary kA used for current PU base | YES | Engineer entry in group config; never inferred from waveform |

### G.3 Scaling safety guarantees (verified)

1. `DisturbanceRecord.waveform_data` contains post-import engineering-unit samples. Samples never
   modified after import (`backend/app/domain/disturbance_record.py` — no setter on waveform_data).
2. All PU conversion occurs in `resolve_voltage_base_for_group()` and `resolve_current_base_for_group()`
   as a denominator computation — never as a sample mutation.
3. CT/VT analysis forms (`ct_primary`, `ct_secondary`, `vt_primary`, `vt_secondary`) accept values
   as per-request API parameters; they are applied within the analysis computation only, not stored
   against the recording.

---

## H. Metadata Dependency and Invalidation Requirements

### H.1 nominal_frequency dependency graph

Consumers reading `active.metadata.nominal_frequency` at request time:

| Consumer | File | Impact if frequency changes |
|---|---|---|
| Overcurrent analysis | `overcurrent_analysis_service.py:128` | Next analysis request uses new value |
| Compliance measurement | `compliance_measurement_service.py:298` | Next analysis request uses new value |
| Compliance readiness | `compliance_readiness_service.py:252` | Next readiness check uses new value |
| Phasor analysis | `phasor_analysis_service.py:215, 245` | Next phasor request uses new value |
| Oscillation representation | `oscillation_representation_service.py:95` | Next oscillation request uses new value |

**RMS calculated channels** do NOT read from `SourceMetadata.nominal_frequency` at request time.
They store `nominal_frequency_hz` as a creation-time parameter in the calculated channel definition.
If the recording's nominal frequency is later changed, **existing RMS channels will not update** —
they retain the frequency used at creation. This is the most significant invalidation risk.

### H.2 nominal_voltage_ll_kv (group level) dependency graph

| Consumer | Impact |
|---|---|
| Waveform PU display | Auto-refreshes on next render (reads live from registry) |
| Phasor magnitude | Reads group config at phasor request time |
| Compliance PU thresholds | Reads group config at compliance request time |
| Power calculated channels (PU path) | Reads at calculation time |

No result caching exists — all analyses re-read metadata at each request. Invalidation is automatic
for analysis-on-demand. No stale cached results.

### H.3 Required invalidation behavior for new nominal_frequency override

If `nominal_frequency` becomes user-editable (RD-2):
1. PATCH endpoint updates `SourceMetadata.nominal_frequency` in-session.
2. All analyses (overcurrent, compliance, phasor, oscillation) will automatically use the new value
   on their next request — no explicit invalidation needed for these.
3. **Existing RMS calculated channels** will NOT auto-update. UI must warn: "Existing RMS channels
   were created with nominal frequency {old} Hz. Reconfigure or delete them to use the new frequency."

---

## I. Future Waveform Corroboration Safeguards

Waveform-based voltage corroboration is deferred. When eventually implemented, these requirements apply:

**Non-interference requirements:**

1. Read-only access to `DisturbanceRecord.waveform_data` — no modification of imported sample buffers.
2. No automatic CT/VT rescaling of samples.
3. No changes to synchronization offsets or event t0.
4. Use source-local time coordinate, not workspace-synchronized time.
5. Correct measurement-side interpretation before comparing RMS to nominal kV.
6. No circular validation: do not corroborate a hypothesis using a PU base derived FROM the
   nominal kV candidate being tested.
7. Select steady-state pre-fault window; avoid disturbed samples. The existing
   `waveform_evidence.py:extract_waveform_evidence()` already applies this logic.
8. Advisory result only — `magnitude_disagreement` must not reject hypotheses; only advisory annotations.
9. No automatic overwrite of `nominal_voltage_ll_kv` or VT settings.
10. No interference with RMS, phasor, power, PU, or protection calculations.
11. Avoid blocking upload, waveform rendering, or interactive navigation — lazy/on-demand trigger only.
12. Invalidate corroboration results when `nominal_voltage_ll_kv`, `base_reference_side`, or group
    membership changes.

**Required regression tests before shipping:**

- Verify that enabling waveform corroboration does not alter waveform render outputs.
- Verify that enabling waveform corroboration does not alter phasor magnitude/angle outputs.
- Verify that enabling waveform corroboration does not alter RMS channel values.
- Verify that enabling waveform corroboration does not alter PU denominator for any existing test recording.

---

## J. Stale Docstring Findings

Do not edit these during RD-0A. Correct in next approved slice.

| # | File | Line | Misleading statement | Verified behavior | Recommended correction |
|---|---|---|---|---|---|
| **J.1** | `backend/app/domain/base_authority.py` | 80–83 | "This predicate describes the INTENDED gate once Slice 5C wires it into resolve_voltage_base_for_group() and resolve_current_base_for_group(). The live resolvers do not call it yet (Slice 5B establishes the vocabulary only; Slice 5C activates the gate)." | `is_base_eligible_for_pu()` IS called at `voltage_group_config.py:265` and `current_group_config.py`. Gate is fully wired (Slice 5C is complete). | Replace with: "This predicate is called by `resolve_voltage_base_for_group()` and `resolve_current_base_for_group()` before group-status checks." |
| **J.2** | `backend/app/domain/base_authority.py` | 24–25 | "The active resolvers do not check this field yet (Slice 5B establishes the vocabulary; Slice 5C wires it)." | Same as J.1 — gate is wired. | Same correction as J.1; remove the "not yet" qualifier from §4. |
| **J.3** | `backend/app/domain/voltage_group_config.py` | 159–160 | "The live resolver still uses nominal_voltage_ll_kv (primary path) until Slice 5D connects this." | The secondary denominator path at lines 285–313 IS active. When `base_reference_side = "secondary"` and `secondary_voltage_ll_v` is valid, it is used as the denominator. | Replace with: "Used by `resolve_voltage_base_for_group()` secondary path (lines 285–313) when base_reference_side = 'secondary'." |
| **J.4** | `backend/app/domain/voltage_primary_secondary.py` | 28–30 | "This module is NOT wired into the live resolver — it establishes the model and validates the computations. Connecting it to the existing resolve_voltage_base_for_group() is a controlled step for Slice 5D." | `secondary_voltage_ll_v_valid` from this module IS imported and used at `voltage_group_config.py:71, 294`. Slice 5D is complete. | Remove item 5 from the design principles list, or replace with: "Connected to live resolver via `secondary_voltage_ll_v_valid` (Slice 5D — complete)." |
| **J.5** | `backend/app/main.py` | 84–96 | Three registry comments say "not yet wired into any API router" for `MeasurementGroupRegistry`, `VoltageGroupConfigRegistry`, `CurrentGroupConfigRegistry`. | All three are wired into `measurement_groups.py`, `per_unit.py`, `compliance.py`, `sources.py`, `workspaces.py`. | Replace "not yet wired into any API router" with "wired into measurement_groups, per_unit, compliance, sources and workspaces API routers." |

---

## K. Recommended RD-1 and RD-2 Implementation Boundaries

### K.1 RD-1 — Read-only display (zero new backend logic)

All data already exists in existing API responses. No new endpoints, no new backend logic.

**What RD-1 adds to Recording Details:**

- Display `nominal_frequency` with a provenance badge:
  - "Imported {X} Hz" (COMTRADE with explicit rate section) — `preparation_provenance.nominal_frequency_assumed == false`
  - "Assumed {X} Hz — not declared in file" — `preparation_provenance.nominal_frequency_assumed == true`
- Display `station_name` and `recorder_name` with "(imported)" label.
- Summary of detected Measurement Groups: group name, kind, channel count, `base_authority`, `pu_status`.
  Indicate clearly when `pu_status = "configured"` on a `status = "suggested"` group.
- Display `base_authority` per voltage group: "Auto-detected", "Engineer-verified", "Needs review".
- Display voltage reference detection result per group (`detection_reason`).
- Display per-channel `measurement_side` ("Primary", "Secondary", "Unknown") and `primary_ratio`/
  `secondary_ratio` where available, with label "Declared in file — verify nameplate".
- Warn on `needs_review` groups: "Measurement configuration ambiguous — engineer review required."

**Tests:** RD-1 requires only frontend tests (panel rendering, provenance badge rendering).
No new backend tests needed.

### K.2 RD-2 — First editable fields (requires backend changes)

**What RD-2 adds:**

- `PATCH /api/v1/workspaces/{wid}/sources/{sid}/nominal-frequency` — allow engineer override.
  Stores `user_nominal_frequency` as an overlay (preserves original imported value as `imported_nominal_frequency`).
  Returns updated effective frequency.
  Warn in UI: "Existing RMS channels use {old} Hz. They will not update automatically."
- Display-name override for `station_name`/`recorder_name`.
  New optional string fields on `SourceMetadata` or a separate overlay dict.
  Allow reset to imported value.
- Display validation: reject frequency outside 45–65 Hz (or configurable range).

**Tests:** RD-2 requires backend unit tests for PATCH endpoint, overlay preservation, reset behavior,
and validation.

### K.3 Recommended slice ordering

| Slice | Scope | Backend changes | Tests |
|---|---|---|---|
| RD-1 | Read-only display improvements | None | Frontend tests |
| RD-1a | Fix stale docstrings (J.1–J.5) | Docstrings only | None |
| RD-2a | nominal_frequency override endpoint | PATCH endpoint, overlay model | Backend unit + browser test |
| RD-2b | station/recorder display-name override | Overlay fields + reset endpoint | Backend unit + browser test |
| RD-3 | CT/VT suggestion pre-fill in analysis forms | None (data already in API) | Frontend tests |
| RD-4 | Group-membership change invalidation | `unavailable` transition on group edit | Backend unit tests |

---

## L. Remaining Owner Decisions

Decisions not covered by the architecture decisions supplied with this task.

| # | Decision | Blocks | Decision mode |
|---|---|---|---|
| **L-1** | Should nominal_frequency override be allowed from Recording Details? (RD-2a scope) | RD-2a | ANALYSIS — conservative; straightforward |
| **L-2** | Should station_name/recorder_name display-name overrides be allowed? (RD-2b scope) | RD-2b | ANALYSIS — no engineering impact |
| **L-3** | Should imported CT/VT ratios be pre-populated in analysis forms? (RD-3 scope) | RD-3 | ANALYSIS — conservative; data already available |
| **L-4** | Should group-membership changes invalidate `auto_resolved` base authority? (Section E Q6 risk) | RD-4 | ANALYSIS — `should_invalidate_on_contradiction()` already exists; wiring is straightforward |
| **L-5** | What is the nominal_frequency validation range for user override? (45–65 Hz, or other?) | RD-2a | ANALYSIS — engineering convention |
| **L-6** | Should waveform corroboration be introduced, and at what trigger point (lazy/upload)? | Deferred | DEFER — not needed until RD-1/RD-2 are complete |

---

## M. Risks, Assumptions and Evidence Gaps

| Risk | Severity | Evidence | Mitigation |
|---|---|---|---|
| Incorrect auto-resolved kV due to wrong recorder metadata | MEDIUM | Code-verified path exists | Waveform corroboration (deferred); engineer review prompt for suggested groups |
| Group membership change silently retains stale `auto_resolved` base | MEDIUM | No invalidation path found in service code | RD-4 slice to add invalidation trigger |
| RMS calculated channels retain stale nominal_frequency after override | MEDIUM | Code-verified: creation-time parameter | UI warning on RD-2a nominal-frequency change |
| Stale docstrings mislead future developers | LOW | Verified in Sections C and J | RD-1a slice (documentation only) |
| "suggested + auto_resolved" shown as both "ready" and "need review" simultaneously | LOW | UI code verified `index.html:35922-35923` | Provenance label improvement in RD-1 |
| Server restart loses all workspace state | LOW (expected) | DEC-015 — intentional | User documentation; not a defect |
| `voltage_primary_secondary.py` docstring still says "not wired" | LOW | See J.4 | RD-1a slice |

**Evidence gaps:**

- **M-1:** Whether `base_authority` invalidation on group-membership change was intentionally deferred
  (not documented in DECISIONS.md) or simply not yet implemented. Recommend treating as a gap to close
  in RD-4 pending owner confirmation.
- **M-2:** Whether the `main.py` comments for the three registries were left stale intentionally or
  accidentally. No decision record found — assumed accidental omission.

---

*No production code was modified. No git operation (commit/push/merge/rebase/deploy) was performed.*
