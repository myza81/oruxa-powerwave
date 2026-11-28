# Recording Metadata Auto-Detection Capability Audit

**Date:** 2026-11-17  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Status:** Investigation complete — no production code changed  
**Prerequisites:** Read `RECORDING_METADATA_AUTHORITY_AUDIT.md` first; this document is a companion.

---

## A. Executive Summary

### What already exists

A full, non-trivial auto-detection pipeline runs synchronously at every recording upload
(`workspace_preparation_service.prepare_workspace_source()`). It performs three independent
discovery passes in sequence:

1. **Measurement Group detection** (`measurement_group_detection.py`) — clusters voltage and current
   channels by name pattern into `STATUS_SUGGESTED` / `STATUS_NEEDS_REVIEW` groups.

2. **Engineering Context detection** (`engineering_context_service.py`) — creates suggested
   engineering contexts for phase role resolution.

3. **Auto-base configuration** (`auto_base_service.py`) — resolves nominal L-L voltage, measurement
   side, and L-L/L-G reference for each newly-created voltage group, writing
   `VoltageBaseConfiguration` with `base_authority="auto_resolved"` or `"needs_review"`.

The auto-base resolver draws on a rich evidence pipeline:

- **Voltage reference geometry** (`voltage_reference.py:detect_voltage_reference()`) — name-based
  L-L vs L-G determination. 31 tests. No waveform access.
- **Multi-hypothesis L-G resolver** (`voltage_hypothesis.py:evaluate_voltage_hypotheses()`) —
  evaluates Convention A vs B for L-G channels using standard-nominal tables, name kV tokens,
  group name kV tokens, and VT winding ratio plausibility. 53 tests.
- **Evidence resolver** (`auto_base_evidence.py:resolve_voltage_group_evidence()`) — produces
  `NominalVoltageCandidate` objects with provenance and sufficiency flags. 72 tests.
- **Waveform corroboration** (`waveform_evidence.py`) — extracts stable prefault RMS to annotate
  hypothesis resolution. Advisory only (never changes authority). 69 tests.
  **Currently NOT wired into the upload path** — `waveform_provider` is not supplied at upload.

### What can be reused

- Voltage reference detection (L-L/L-G) is immediately reusable by Recording Details.
- Auto-base evidence output (`VoltageGroupEvidence.primary_nominal_candidates`,
  `secondary_measured`, `hypothesis_resolution`) is already computed and stored via registry.
  Recording Details could surface it read-only without any new computation.
- `base_authority` state machine already distinguishes auto-resolved, needs-review, manual, and
  legacy configurations — a provenance model for Recording Details is already in place.
- `preparation_provenance.nominal_frequency_assumed` flag is already tracked at import time.
  Recording Details needs only to surface it.

### What is missing

- **Nominal frequency is not user-editable.** No PATCH endpoint on `SourceMetadata.nominal_frequency`.
  BEN recordings silently assume 50 Hz with no visible warning in Recording Details.
- **CT primary/secondary ratings are stored per-channel but never offered as suggestions** in
  analysis forms (Overcurrent, Distance, Impedance). The `primary_ratio`/`secondary_ratio` fields
  exist on `AnalogChannelSummary` and are populated for COMTRADE 1999 and BEN32 SubBen.
- **Auto-base does not re-run when `POST /suggest` is called manually.** Auto-base only runs at
  upload. If a user triggers re-suggestion after the initial upload, newly-created groups are not
  auto-configured.
- **Recording Details does not display detected voltage levels or base authority.** The
  `VoltageBaseConfiguration` populated by auto-detection is accessible via the Measurement Groups
  API but never summarised on Recording Details.
- **Waveform corroboration is not used at upload.** The wiring exists but `waveform_provider` is
  not passed to `configure_auto_bases_for_source` at upload time.
- **Secondary VT voltage (110 V suggestion) has no Recording Details UI entry point.** The
  `secondary_voltage_ll_v` field in `VoltageBaseConfiguration` can be auto-populated from
  `secondary_ratio` for COMTRADE 1999 secondary-side files, but cannot be overridden from
  Recording Details.

---

## B. Existing Capability Inventory

| Capability | Existing implementation | Inputs | Output | Reliability / limitations | Reusable? |
|---|---|---|---|---|---|
| Voltage reference detection (L-L vs L-G) | `voltage_reference.py:detect_voltage_reference()` | Voltage channel names (strings) | `LINE_TO_LINE` / `LINE_TO_GROUND` / `None` with reason | HIGH for explicit names (VR/VA/VRY/VAB); `None` when ambiguous or absent; never guesses | Yes — pure function, no deps |
| Measurement Group clustering | `measurement_group_detection.py:detect_measurement_groups()` | `(name, type, unit)` tuples | `DetectedGroup` list (`SUGGESTED`/`NEEDS_REVIEW`) | Deterministic name-grammar only; ambiguous names → `NEEDS_REVIEW`; no waveform | Yes — pure function |
| Auto upload trigger | `workspace_preparation_service.prepare_workspace_source()` | workspace_id, source_id, registries | `WorkspaceSourcePreparationResult` (count + errors) | Runs at every upload; non-blocking (try/except); idempotent | Reuse as-is; extend for new steps |
| Nominal voltage evidence resolution | `auto_base_evidence.py:resolve_voltage_group_evidence()` | `ChannelAutoMetadata` list (name, type, unit, PS flag, ratios) | `VoltageGroupEvidence` with candidates, side, reference, sufficiency | COMTRADE 1999+PS: HIGH; no PS flag: LOW; BEN5K: no ratio evidence; needs channel name or primary_ratio | Yes — pure function |
| L-G convention disambiguation | `voltage_hypothesis.py:evaluate_voltage_hypotheses()` | `ChannelAutoMetadata` list, optional group name, optional waveform | `VoltageHypothesisResolution` (A/B/ambiguous/none) | Relies on standard-nominal table; can be ambiguous (e.g. 132 kV L-G matches 132 kV direct and 228.6 kV ×√3) | Yes — pure function; already wired into evidence resolver |
| Waveform RMS corroboration | `waveform_evidence.py:extract_waveform_evidence()` + `corroborate_hypothesis()` | Channel waveform arrays (kV), nominal freq | `WaveformEvidence` + `WaveformCorroboration` per hypothesis | Advisory only; `magnitude_disagreement` does not reject hypothesis; not usable on disturbed recordings; capped at 2 s | Yes — currently unwired at upload; suitable for lazy/on-demand trigger |
| Auto-base orchestration | `auto_base_service.py:configure_auto_bases_for_source()` | workspace/source/registries, optional waveform_provider | `AutoBaseResult` (configured count, needs_review, skipped) | Idempotent; never overwrites manual/legacy; current groups skipped (CT Ibase excluded); `needs_review` written when insufficient | Reuse as-is; extend with waveform_provider for corroboration |
| Channel CT/VT ratio storage | `AnalogChannelSummary.primary_ratio` / `.secondary_ratio` | From COMTRADE CFG fields 10/11; from BEN32 SubBen normalize | Per-channel float or None | COMTRADE 1999 only; COMTRADE 1991 always None; BEN5K always None; descriptive, NOT applied to samples | Reusable as suggestion source for analysis forms |
| Measurement side detection | `reference_side.py:comtrade_measurement_side()` | COMTRADE CFG ps_flag ("P"/"S"/blank) | "primary" / "secondary" / "unknown" | Only available for COMTRADE 1999; always "unknown" for BEN, COMTRADE 1991 | Yes — already on AnalogChannelSummary |
| BEN nominal frequency flag | `BenProvider._nominal_frequency_assumed` → `preparation_provenance.nominal_frequency_assumed` | None (input at upload) | bool in provenance dict | Correctly flags assumed-50-Hz BEN recordings | Reusable: expose in Recording Details as "Assumed" badge |
| RMS eligibility detection | `rms_detector.py:classify_waveform_form()` | Waveform samples, nominal_freq | `LIKELY_INSTANTANEOUS` / `LIKELY_MAGNITUDE_OR_RMS` / `UNCERTAIN` | Fallback when `waveform_form == "unknown"` (all COMTRADE/BEN channels); NOT part of auto-detection pipeline | No — per-operation eligibility check, not upload-time |

---

## C. Detection Provenance and Precedence

### Recommended provenance hierarchy

Every piece of metadata should carry an explicit provenance label visible to the engineer:

| Label | Meaning | Example |
|---|---|---|
| **Imported** | Value came directly from the file format, unmodified | COMTRADE `station_name`, `nominal_frequency`, `primary_ratio`, `ps_flag` |
| **Detected** | Computed from imported values without user input; may be wrong | Voltage reference geometry from channel names; nominal kV from primary_ratio |
| **Defaulted** | No imported or detected value; a standard default was applied | `nominal_frequency = 50 Hz` for BEN recordings |
| **Suggested** | Detected or defaulted, awaiting engineer review | Auto-base result with `base_authority="auto_resolved"` on `STATUS_SUGGESTED` group |
| **Verified** | Engineer has explicitly confirmed or entered the value | Manual VoltageBaseConfiguration or confirmed Measurement Group |
| **Unresolved** | Detection failed or was ambiguous; engineer input required | `base_authority="needs_review"`, or missing CT primary rating |

### Current implementation vs. recommended

| Metadata | Currently labelled? | Needs improvement? |
|---|---|---|
| Nominal frequency (BEN assumed) | `nominal_frequency_assumed` bool in `preparation_provenance` | Yes — not surfaced on Recording Details; used in analysis forms only |
| Voltage reference (L-L/L-G) | `detection_reason` on `VoltageGroupConfigOut` | Partial — in Measurement Groups modal, not Recording Details |
| Nominal kV (auto-resolved) | `base_authority` field on `VoltageBaseConfiguration` | Partial — accessible in Measurement Groups API, not surfaced in Recording Details |
| CT/VT primary_ratio | Stored on `AnalogChannelSummary` | No label indicating source or whether it was applied |
| Measurement side (PS flag) | `measurement_side` on `AnalogChannelSummary` | No Recording Details display; not visible outside channel list |

### Critical rule — do not conflate provenance levels

Imported metadata is not automatically trustworthy. `primary_ratio` from COMTRADE CFG is a
descriptor written by the relay/recorder, which may encode winding voltage directly (Convention A)
or phase-winding voltage (Convention B), or may be the COMTRADE default of `1.0` (meaning "not
declared"). The evidence pipeline already handles this, but any UI surfacing of CT/VT values
must carry the provenance label to prevent an engineer from treating a "Detected" value as
verified engineering data.

---

## D. CT/VT Feasibility Assessment

### VT default suggestions

The following standard secondary voltages can be suggested as defaults for a secondary-side VT:

| Suggested secondary | Appropriate when |
|---|---|
| 110 V L-L | Standard IEC/EN protection VT secondary; L-L reference |
| ~63.5 V L-N | Standard IEC/EN protection VT secondary; L-N reference (110/√3) |
| 115 V L-L | IEEE/ANSI standard protection VT secondary |

These are **suggestions only**, not automatically applied. An explicit imported `secondary_ratio`
(from COMTRADE CFG or BEN32) takes precedence as a **more specific candidate** than the standard
default, but still requires engineer confirmation as a nameplate rating.

**Can Recording Details propose primary-side VT suggestions (e.g. `132 kV / 110 V`)?**

| Required capability | Status |
|---|---|
| Obtain nominal primary voltage | YES for COMTRADE 1999 primary-side (PS=P) with `primary_ratio` and L-L geometry. MEDIUM confidence. LOW confidence without PS flag. NO for BEN5K. |
| Distinguish L-L and L-N reference | YES via `detect_voltage_reference()`. Well-tested. |
| Distinguish primary vs secondary side | YES for COMTRADE 1999 with PS flag. UNKNOWN for all others. |
| Detect multiple voltage levels | YES — separate groups per (context_hint, kind) pair. |
| Detect conflict with standard defaults | YES — evidence pipeline computes consistency and sets `has_contradictions` flag. |
| Explicit imported secondary rating | YES — `secondary_ratio` on `AnalogChannelSummary` → `secondary_voltage_ll_v` via auto-base. |

**Engineering safety rules for VT suggestions:**

1. Never present a VT suggestion as a nameplate rating — label it "Suggested from detected nominal."
2. An auto-resolved `nominal_voltage_ll_kv` in `VoltageBaseConfiguration` is an auto-detected
   primary estimate, NOT a confirmed nameplate VT primary rating.
3. `secondary_voltage_ll_v` from `secondary_ratio` is the VT output terminal voltage as declared
   in the file. It is NOT a nameplate secondary rating unless the engineer confirms it.
4. A `needs_review` auto-base result must display a warning, not a suggestion.
5. Never suggest a VT configuration when `measurement_side = "unknown"` for the group without
   clearly flagging that the primary/secondary distinction is unverified.

### CT rating feasibility

**CT primary rating cannot be inferred or detected.** This is an explicitly established engineering
constraint (DEC-050 §11, `auto_base_evidence.py` C5). Reasons:

- CT primary winding rating is excluded from automatic Ibase derivation by design.
- CT primary rating cannot be reliably inferred from measured current magnitude (a 1200 A CT on a
  lightly-loaded 100 A feeder looks identical to a 100 A CT at rated load).
- Imported `primary_ratio` on current channels (from COMTRADE CFG) is retained on
  `AnalogChannelSummary` as a **candidate only** — it may be used as a pre-fill suggestion in
  analysis forms, clearly labelled "Declared in file — verify nameplate."
- BEN5K: CT rating is `None` for all channels.
- BEN32 SubBen: CT `primary_rating` is imported from BEN header; mapped to `primary_ratio` on
  `AnalogChannelSummary`.

**Recommended CT handling:**

- In Overcurrent, Distance, Impedance analysis forms: pre-populate from channel
  `primary_ratio` / `secondary_ratio` where available, labelled "Declared in file (unverified)."
- Do not auto-apply. Require explicit engineer confirmation.
- Do not display CT ratio in Recording Details as a recording-level property — it belongs to the
  analysis or Current Measurement Group configuration, not the recording identity.

---

## E. Proposed Integration Architecture

### Upload pipeline (already exists, partially)

```
Upload
  ↓
WorkspaceRegistry.register() → SourceMetadata, AnalogChannelSummary (with primary_ratio, secondary_ratio, measurement_side)
  ↓
prepare_workspace_source() [non-blocking, all wrapped in try/except]
  ├── generate_suggested_groups_for_source()   → STATUS_SUGGESTED / STATUS_NEEDS_REVIEW groups
  ├── generate_suggested_contexts_for_source() → suggested engineering contexts
  └── configure_auto_bases_for_source()        → VoltageBaseConfiguration (auto_resolved / needs_review)
         ├── detect_voltage_reference()   [name-based L-L/L-G]
         ├── evaluate_voltage_hypotheses() [L-G Convention A/B]
         └── resolve_voltage_group_evidence() [nominal kV candidates, side, consistency]
```

### Recording Details as consumer (proposed)

Recording Details should **read** already-computed detection results rather than triggering new
computation. The data already exists in in-memory registries:

```
Recording Details page loads
  ↓
GET /api/v1/workspaces/{wid}/sources/{sid}
  → SourceSummaryOut: nominal_frequency, preparation_provenance (includes nominal_frequency_assumed)
                      analog_channels (each with: primary_ratio, secondary_ratio, measurement_side, unit)

GET /api/v1/workspaces/{wid}/sources/{sid}/measurement-groups
  → List[MeasurementGroupOut]: each with VoltageGroupConfigOut
    (nominal_voltage_ll_kv, base_authority, secondary_voltage_ll_v, base_reference_side,
     effective_reference, detection_reason, evidence_names)
```

**No new backend computation is required for the read-only display improvement.**

### New recording-level metadata (proposed — owner decisions needed)

If `nominal_frequency` editability is approved (Decision J-1):
- Add `PATCH /api/v1/workspaces/{wid}/sources/{sid}/nominal-frequency` → update
  `SourceMetadata.nominal_frequency` in-session, flagging as "user override."
- Propagate to all analysis defaults via the already-established `SourceMetadata` path (consumers
  read `nominal_frequency` from `SourceMetadata` at analysis time, not from a snapshot).

If CT/VT suggestion pre-fill is approved (Decision J-2):
- No backend change needed — `primary_ratio`/`secondary_ratio` are already in the API response.
- Frontend analysis forms read these from `SourceChannelsOut.analog_channels` and pre-populate,
  labelled "Declared in file — verify before use."

### Standalone manual calculators boundary

[DECISION — established] Standalone calculators (single-phase Power Calculator, manual Phasor
input forms) must never inherit recording metadata automatically. They remain independent of this
integration architecture.

---

## F. Engineering Safety and Failure Scenarios

### F-1 Ambiguous measurement side

**Scenario:** COMTRADE file has no PS flag (COMTRADE 1991, or 1999 with blank ps field).

**Current behavior:** `measurement_side = "unknown"` for all channels → `sufficient_for_auto_side =
False` → `base_authority = "needs_review"` → group does NOT resolve to PU-eligible status without
engineer intervention.

**Risk:** Engineer may not notice the `needs_review` state and assume PU is configured.

**Mitigation:** Recording Details should display `needs_review` groups with a visible warning
("Measurement side unverified — engineer confirmation required").

### F-2 Mixed voltage levels in one recording

**Scenario:** Recording contains both 132 kV and 33 kV channels (transformer differential).

**Current behavior:** Two separate voltage groups are detected (`(context_hint, kind)` clusters).
Auto-base runs for each group independently. Each group's kV level is determined from its own
channels' `primary_ratio` and name tokens.

**Risk:** A channel whose name does not carry a kV token or primary_ratio may be clustered into
the wrong group → wrong nominal voltage.

**Mitigation:** `STATUS_NEEDS_REVIEW` is set for clusters with conflicting evidence. Recording
Details should summarize group membership and kV levels, allowing the engineer to spot conflicts.

### F-3 Incorrect imported primary_ratio

**Scenario:** COMTRADE file has `primary_ratio = 1.0` (the COMTRADE field default for "not
declared," not an actual 1 kV VT).

**Current behavior:** `_MIN_NOMINAL_LL_KV = 2.0` gate in `auto_base_evidence.py` excludes the
1.73 kV derived value (1.0 kV × √3 for an L-G channel). `REASON_NOMINAL_BELOW_MINIMUM` is
returned → `sufficient_for_auto_nominal = False` → `needs_review`.

**Risk:** LOW — the minimum-voltage gate handles the most common form of this error. Edge case:
a 1.0 kV system (not a standard relay recording) could be incorrectly excluded.

### F-4 L-L / L-N mismatch

**Scenario:** Engineer selects "Line-to-Line" reference for a group that actually has
phase-to-neutral channels.

**Current behavior:** `detect_voltage_reference()` returns `LINE_TO_GROUND` for channels named
"VR"/"VA". If the engineer overrides to `LINE_TO_LINE` via `reference_override`, the PU
denominator is set to `nominal_voltage_ll_kv` instead of `nominal_voltage_ll_kv / √3` → values
are √3 × too large.

**Risk:** Medium — results in systematic PU error but no silent failure.

**Mitigation:** Recording Details and Measurement Group UI should both show the detected reference
alongside the user override, with a visual indicator when the override contradicts detection.

### F-5 Disturbed waveform magnitudes

**Scenario:** Recording captures a voltage sag or fault. Waveform RMS does not reflect nominal voltage.

**Current behavior:** Waveform corroboration returns `magnitude_disagreement` verdict but does
NOT downgrade authority (explicitly by design — `auto_base_service.py` C8). `base_authority` is
unchanged.

**Risk:** LOW for automatic authority; the design handles this correctly. The concern arises only
if future UI presents the corroboration verdict incorrectly as an error.

**Mitigation:** When waveform corroboration is wired into upload, the `magnitude_disagreement`
verdict must be presented as "Waveform magnitude does not match expected nominal — this may be
normal for a fault recording" rather than "Incorrect nominal."

### F-6 Derived/calculated channels and double scaling

**Scenario:** An RMS calculated channel or power channel inherits group metadata from its source.

**Current behavior:** Calculated channels inherit PU group from source channel via Slice 7 (DEC-050).
This is PU base inheritance only — no CT/VT scaling is applied to calculated channels.

**Risk:** LOW — the inheritance is PU base only. No physical scaling is involved. Double-scaling
only arises if CT/VT ratios are explicitly applied to source channels (not currently implemented).

### F-7 Double-scaling via CT/VT auto-apply

**Scenario:** An engineer applies CT/VT ratio to a COMTRADE file whose `a`/`b` coefficients
already incorporate the CT/VT transformation (primary-side-equivalent samples).

**Current behavior:** CT/VT ratios from channel metadata are NEVER automatically applied to
waveform samples. All physical scaling is performed once at import via `a`/`b` COMTRADE coefficients
or BEN gain factors. No subsequent application of `primary_ratio`/`secondary_ratio` occurs.

**Risk:** ZERO from automatic application (correctly guarded). HIGH if future feature auto-applies
CT/VT to already-scaled samples.

**Mitigation:** Any future feature that uses `primary_ratio`/`secondary_ratio` for physical
conversion must (a) check `measurement_side` to confirm the file is secondary-side, (b) require
engineer confirmation, and (c) document clearly that the conversion is irreversible.

### F-8 `needs_review` authority is not PU-eligible

**Scenario:** Auto-base resolves insufficient evidence (conflicting ratios, unknown side, ambiguous
L-G convention).

**Current behavior:** `base_authority = "needs_review"` → `is_base_eligible_for_pu()` returns False
→ PU resolution returns `STATUS_BASE_REQUIRED`. **This is already wired in**
(`voltage_group_config.py:265`).

**Risk:** Engineer navigates to PU display, sees "PU not configured," and manually enters a base
without understanding why auto-detection failed.

**Mitigation:** Recording Details and Measurement Groups should surface `needs_review` reason
(from `insufficient_reasons` in `VoltageGroupEvidence`) with an actionable message.

---

## G. Performance Assessment

### Upload-time detection (synchronous, non-blocking)

| Step | Computation | Estimated cost | Risk |
|---|---|---|---|
| `detect_measurement_groups()` | O(n) channel names, regex matching | Negligible | None |
| `generate_suggested_contexts_for_source()` | O(n) channel names | Negligible | None |
| `resolve_voltage_group_evidence()` per group | Channel metadata only, no waveform | Negligible | None |
| `evaluate_voltage_hypotheses()` per L-G group | Standard-nominal table lookup | Negligible | None |
| `configure_auto_bases_for_source()` total | Sum of above, per group | Negligible | None |
| `extract_waveform_evidence()` (NOT called at upload) | Sliding RMS over up to 2 s of samples; O(N) | Medium (scales with sample count) | Should remain on-demand |

**All detection except waveform corroboration is effectively free.** Waveform corroboration is
the only potentially expensive step and is correctly not wired into the upload path.

### On-demand / lazy detection

Waveform corroboration (`extract_waveform_evidence`) is suitable for lazy triggering: when
Recording Details is opened for the first time after upload, the backend could run corroboration
for `needs_review` groups and annotate the result. This provides the most useful information
(does the waveform magnitude agree with the detected nominal?) at the right time — when the
engineer is actively reviewing the recording — without blocking the upload.

**Recommendation:** Keep the upload pipeline free of waveform scanning. If waveform corroboration
is ever wired in:
- Call it lazily on first Recording Details view (not at upload).
- Cache the result in the session (the evidence doesn't change).
- Never block waveform display on corroboration completion.
- Always respect `suitable_for_corroboration = False` for disturbed recordings.

### Cache invalidation

If `nominal_frequency` becomes user-editable (Decision J-1):

- `nominal_frequency` is used by: RMS channel computation, phasor analysis, compliance
  measurement, overcurrent analysis.
- An in-session override changes the effective value read from `SourceMetadata.nominal_frequency`.
- Existing calculated channels that capture `nominal_frequency_hz` in their `parameters` dict
  would become stale if the value changes after their creation.
- **Risk:** Stale RMS channels. The compliance readiness service already checks whether a
  calculated channel's `parameters.nominal_frequency_hz` matches the current source frequency
  (`compliance_readiness_service.py:220`). The same gate could detect and invalidate stale
  calculated channels.

---

## H. Gap Analysis

| Capability | Classification | Notes |
|---|---|---|
| Voltage reference detection (L-L/L-G) from channel names | **Already implemented and reusable** | `voltage_reference.py`; well-tested (31 tests) |
| Nominal kV auto-detection from COMTRADE primary_ratio | **Already implemented and reusable** | `auto_base_evidence.py`; runs at upload; 72 tests |
| L-G convention disambiguation (Hypothesis A/B) | **Already implemented and reusable** | `voltage_hypothesis.py`; wired into evidence resolver; 53 tests |
| Measurement Group auto-suggestion at upload | **Already implemented and reusable** | `workspace_preparation_service.py` → `generate_suggested_groups_for_source()` |
| VoltageBaseConfiguration auto-population | **Already implemented and reusable** | Auto-base at upload; `base_authority` gate wired |
| `base_authority` PU gate | **Already implemented and reusable** | `voltage_group_config.py:265`; note: docstring in `base_authority.py` calls this "Slice 5C not wired yet" but code shows it IS wired |
| Waveform RMS corroboration | **Implemented but requires adaptation** | Module exists and tested (69 tests); NOT wired at upload; suitable for lazy/on-demand trigger |
| Nominal frequency provenance flag | **Implemented but requires adaptation** | `preparation_provenance.nominal_frequency_assumed` exists; not surfaced in Recording Details |
| Nominal frequency user override | **Missing and requires new functionality** | No PATCH endpoint; `SourceMetadata.nominal_frequency` is immutable |
| CT/VT pre-fill suggestions in analysis forms | **Missing and requires new functionality** | Data exists (`primary_ratio`/`secondary_ratio` on channel summary); just not wired into forms |
| `needs_review` reason surfaced to engineer | **Missing and requires new functionality** | `insufficient_reasons` in `VoltageGroupEvidence` exists in domain; not exposed in API response |
| VT secondary standard suggestion (110 V) | **Missing and requires new functionality** | No "suggest 110 V" logic in Recording Details; could be a simple UI addition using known VT convention |
| Auto-base re-run after `POST /suggest` | **Missing and requires new functionality** | `POST /suggest` calls `generate_suggested_groups_for_source()` but not `configure_auto_bases_for_source()` |
| Station/recorder name user override | **Missing and requires new functionality** | `station_name`/`recorder_name` immutable; needs display-name override field on `SourceMetadata` or separate workspace-scoped table |
| CT primary rating auto-detection | **Not suitable — unsafe by design** | DEC-050 §11; CT primary is not inferrable from current magnitude; must remain manual |
| Nominal kV from waveform magnitude | **Not suitable — deferred by design** | Owner instruction: "Do not infer voltage reference solely from instantaneous magnitude yet"; corroboration is the only waveform use |
| Auto-apply CT/VT to waveform samples | **Unsafe — requires owner decision** | Double-scaling risk; `measurement_side` must be verified; engineer must confirm |
| Persistence beyond session | **Unsafe — pending architecture decision (J-4)** | DEC-015 forbids server persistence; metadata currently lost on session end |

---

## I. Recommended Incremental Implementation Plan

**These are proposals. Each requires owner approval before implementation.**

### Slice RD-1 — Expose existing detection data in Recording Details (read-only, no new computation)

**Scope:** Frontend only. No new backend logic.

1. Surface `nominal_frequency` with an "assumed 50 Hz" badge when
   `preparation_provenance.nominal_frequency_assumed == true`. (The API already returns
   `preparation_provenance`; the frontend just needs to read the flag.)
2. Display per-channel `primary_ratio`, `secondary_ratio`, and `measurement_side` in the channel
   list within Recording Details (data already in `SourceChannelsOut.analog_channels`).
3. Add a Measurement Group summary to Recording Details: list each confirmed/suggested group,
   its kind, nominal kV (if auto-resolved), `base_authority` badge, and effective reference.
   Data source: existing `GET .../measurement-groups` endpoint.
4. Display `needs_review` groups with a warning message in the summary.

**Dependencies:** None. All data already in API responses.  
**Risk:** Very low — read-only display changes.  
**Testable independently:** Yes — visual inspection of Recording Details panel.

### Slice RD-2 — Surface detection provenance (backend adaptation)

**Scope:** Backend schema + frontend.

5. Extend `VoltageGroupConfigOut` to include `base_authority` state label and
   `insufficient_reasons` (already in `VoltageGroupEvidence` domain object; not yet in schema).
6. Extend `SourceSummaryOut` to include `nominal_frequency_assumed` flag (already in
   `preparation_provenance`; expose as a first-class field for clarity).

**Dependencies:** RD-1.  
**Risk:** Low — additive schema changes.

### Slice RD-3 — Nominal frequency override (requires owner decision J-1)

**Scope:** Backend + frontend.

7. Add `PATCH /api/v1/workspaces/{wid}/sources/{sid}/nominal-frequency` to update
   `SourceMetadata.nominal_frequency` in-session, with provenance flag ("user_override").
8. Add a Recording Details UI control for this field, showing current value and provenance.
9. Identify and invalidate stale calculated channels that captured the old frequency in their
   `parameters` (compliance readiness service already does this check).

**Dependencies:** Decision J-1.  
**Risk:** Medium — propagation to calculated channels needs careful testing.

### Slice RD-4 — CT/VT suggestion pre-fill in analysis forms (requires owner decision J-2)

**Scope:** Frontend only.

10. In Overcurrent, Distance Protection, and Impedance analysis forms: pre-populate CT/VT
    input fields from `primary_ratio`/`secondary_ratio` of the selected channel(s), labelled
    "Declared in file — verify nameplate rating before use."
11. Add VT secondary default suggestion (110 V or 63.5 V based on detected reference) as a
    separate, clearly-labelled suggestion alongside the imported value.

**Dependencies:** Decision J-2.  
**Risk:** Low — pre-fill only; engineer must still confirm before analysis runs.

### Slice RD-5 — Re-trigger auto-base after manual Suggest Groups

**Scope:** Backend.

12. When `POST /suggest` creates new measurement groups, also call
    `configure_auto_bases_for_source()` for the newly created groups.
    Guard: skip if no new groups were created.

**Dependencies:** None (code change only).  
**Risk:** Low — idempotent, non-blocking, same logic as upload path.

### Slice RD-6 — Station name override (requires owner decision J-3)

**Scope:** Backend + frontend.

13. Add a session-scoped display-name override field to `SourceMetadata` or a workspace-scoped
    metadata table.
14. Surface as an editable field in Recording Details. Use override in source list display.

**Dependencies:** Decision J-3.  
**Risk:** Low — cosmetic session-scoped override; does not modify imported values.

---

## J. Owner Decisions Required

The following decisions are genuinely unresolved. The architectural decisions stated in the
investigation brief (§2) are not reopened here.

### J-1: Should `nominal_frequency` be user-editable from Recording Details?

**Engineering need:** BEN recordings silently assume 50 Hz with no correction path. All analyses
using `nominal_frequency` (phasor, RMS, compliance, overcurrent) consume this value. An engineer
working with a 60 Hz BEN recording has no way to correct it without re-importing.

**Proposal:** Allow an in-session override via PATCH endpoint. Original imported value is
preserved in `preparation_provenance`. Effective value propagates to all analyses. Stale
calculated channels are invalidated.

**Decision mode:** ANALYSIS — straightforward addition; risk is well-characterized.

### J-2: Should imported `primary_ratio`/`secondary_ratio` be offered as suggestions in analysis forms?

**Engineering need:** CT/VT ratios are re-entered for every analysis (Overcurrent, Distance,
Impedance). The file often carries these values. Pre-filling would reduce engineer effort.

**Engineering risk:** Imported ratios may not equal nameplate ratings. The file may have
calibration-adjusted ratios. A `measurement_side = "unknown"` channel makes the value ambiguous.
Label must clearly state provenance.

**Proposal:** Pre-fill as suggestions, clearly labelled "Declared in file — unverified."
Engineer must confirm. Never auto-apply.

**Decision mode:** ANALYSIS — conservative path (suggestion only) is unambiguous.

### J-3: Should station/recorder name be user-editable?

**Engineering need:** Files from some recorders use technical IDs ("IED_01") that are unhelpful
as display names. Engineers may want to label a recording "Feeder 3 — North Substation."

**Proposal:** Add a session-scoped display-name field. Used in UI display only; does not modify
`SourceMetadata.station_name` or `recorder_name`.

**Decision mode:** ANALYSIS — straightforward addition; no engineering risk.

### J-4: Should any metadata survive session end?

**Context:** Current architecture (DEC-015) forbids server-side persistence. All metadata —
including auto-detected voltage levels, confirmed groups, and nominal frequency overrides — is
lost on session end. Recording Details cannot surface "last session's configuration."

**Engineering impact:** Every session that re-uploads the same recording requires re-confirming
the same measurement groups and nominal voltages. For engineers working repeatedly with known
substations, this is significant friction.

**Decision mode:** COMPARISON — multiple options exist (export/import configuration file, local
browser storage, server-side per-recording profile) with different engineering trade-offs. The
owner's current DEC-015 philosophy must be revisited before any option is selected.

### J-5: Should waveform corroboration be triggered lazily when Recording Details is opened?

**Engineering value:** For `needs_review` auto-base groups, waveform corroboration could answer
"does the waveform magnitude agree with the detected nominal?" helping the engineer decide
whether to accept or override the auto-detected value.

**Performance implication:** Requires reading waveform samples for up to 2 s of data. Should be
lazy (not at upload) and cached in-session.

**Decision mode:** ANALYSIS — conservative path (lazy, non-blocking, cached) is clear; whether
to build it at all is the owner's call.

---

## K. Evidence Appendix

### K.1 Auto-detection implementation files

| File | Role |
|---|---|
| `backend/app/domain/voltage_reference.py` | `detect_voltage_reference()` — name-based L-L/L-G detection |
| `backend/app/domain/measurement_group_detection.py` | `detect_measurement_groups()` — channel clustering by name grammar |
| `backend/app/domain/auto_base_evidence.py` | `resolve_voltage_group_evidence()`, `resolve_current_group_evidence()` — full evidence pipeline |
| `backend/app/domain/voltage_hypothesis.py` | `evaluate_voltage_hypotheses()` — multi-hypothesis L-G Convention A/B resolver |
| `backend/app/domain/waveform_evidence.py` | `extract_waveform_evidence()`, `corroborate_hypothesis()` — waveform corroboration |
| `backend/app/domain/base_authority.py` | `BaseAuthorityState` vocabulary, `is_base_eligible_for_pu()` gate |
| `backend/app/services/auto_base_service.py` | `configure_auto_bases_for_source()` — orchestrates evidence → VoltageBaseConfiguration |
| `backend/app/services/workspace_preparation_service.py` | `prepare_workspace_source()` — upload trigger; calls all three discovery steps |
| `backend/app/services/measurement_group_service.py` | `generate_suggested_groups_for_source()` — Slice 2 detection + persistence |

### K.2 Upload trigger wiring

| File | Line | Note |
|---|---|---|
| `backend/app/api/v1/sources.py` | 247–252 | Calls `prepare_workspace_source()` after every successful upload |
| `backend/app/services/workspace_preparation_service.py` | 120–162 | Calls group detection, context detection, auto-base in sequence |
| `backend/app/services/auto_base_service.py` | 154 | `configure_auto_bases_for_source()` called WITHOUT `waveform_provider` at upload |

### K.3 Stale docstrings (do not rely on)

| File | Stale claim | Actual behavior |
|---|---|---|
| `backend/app/services/measurement_group_service.py:305` | "No automatic trigger exists for this function" | Trigger exists via `workspace_preparation_service.py` since shared post-upload preparation was added |
| `backend/app/api/v1/measurement_groups.py:19` | "Slice 2's grouping detector is invoked ONLY by POST .../suggest, never automatically" | Incorrect — also invoked at upload via `workspace_preparation_service` |
| `backend/app/domain/base_authority.py:25` | "The active resolvers do not check this field yet (Slice 5B establishes the vocabulary; Slice 5C wires it)" | Incorrect — `voltage_group_config.py:265` and `current_group_config.py:258` already gate on this field |
| `backend/app/domain/voltage_hypothesis.py:22` | "It is NOT yet wired into the import lifecycle or auto_base_service" | Incorrect — `auto_base_evidence.py:472` imports and calls `evaluate_voltage_hypotheses` |

### K.4 CT/VT import by format

| Format | primary_ratio | secondary_ratio | measurement_side | Notes |
|---|---|---|---|---|
| COMTRADE 1999 | CFG field 10 (may be `None` or `1.0`) | CFG field 11 (may be `None`) | CFG field 12 ps_flag ("P"/"S") → "primary"/"secondary"/"unknown" | `comtrade.py:207–216` |
| COMTRADE 1991 | None (fields 10–12 absent) | None | "unknown" | `comtrade.py:207` — only 10 fields in 1991 |
| BEN32 SubBen | `BenAnalogChannel.primary_rating` → `primary_ratio` | `secondary_rating_in_channel_unit` → `secondary_ratio` | "unknown" (BEN has no PS flag) | `ben/normalize.py:117-118`, `ben/model.py:177` |
| BEN5K Legacy | None | None | "unknown" | `legacy_ben5k/normalize.py:221-222` |
| CSV / Excel | None | None | "unknown" | Preparation-wizard channels; no CT/VT fields |

### K.5 Test coverage

| Test file | Tests | Coverage area |
|---|---|---|
| `backend/tests/test_voltage_reference.py` | 31 | Name-based L-L/L-G detection, word-boundary rules, winding qualifier stripping |
| `backend/tests/test_auto_base_evidence.py` | 72 | Evidence resolution (primary candidates, side detection, contradiction cases) |
| `backend/tests/test_voltage_hypothesis.py` | 53 | Hypothesis A/B evaluation, standard nominal matching, scoring |
| `backend/tests/test_waveform_evidence.py` | 69 | Stable window detection, onset detection, corroboration thresholds |
| `backend/tests/test_auto_base_6b_integration.py` | 20 | End-to-end waveform corroboration integration |
| `backend/tests/test_measurement_group_detection.py` | 24 | Channel clustering logic |
| `backend/tests/test_measurement_group_service.py` | (various) | `generate_suggested_groups_for_source()` lifecycle |

### K.6 Frontend — nominal frequency provenance (existing, in analysis forms only)

| Line | Context |
|---|---|
| `frontend/index.html:60595` | Phasor analysis form shows "(assumed default)" or "(from the recording)" |
| `frontend/index.html:61146` | Overcurrent analysis form — same pattern |
| `frontend/index.html:61356` | Compliance analysis — same pattern |
| `frontend/index.html:22247` | Recording Details `renderRecordingDetails()` — shows `nominal_frequency + " Hz"` but NO assumed/override badge |

### K.7 Key design constraint reminders

- `primary_ratio`/`secondary_ratio` on `AnalogChannelSummary` are DESCRIPTIVE ONLY — never applied
  to waveform samples (confirmed by code audit: no caller reads these for scaling).
- `nominal_voltage_ll_kv` in `VoltageBaseConfiguration` is the auto-detected or manually-set
  nominal primary L-L voltage. It is NOT a VT nameplate primary rating.
- `secondary_voltage_ll_v` in `VoltageBaseConfiguration` is the VT output terminal voltage
  (from `secondary_ratio`). It is NOT a standard secondary rating until the engineer confirms it.
- `auto_resolved` authority bypasses the `STATUS_CONFIRMED` gate for `STATUS_SUGGESTED` groups
  — a suggested group with auto-resolved evidence IS PU-eligible without explicit confirmation
  (`voltage_group_config.py:275–280`). `STATUS_NEEDS_REVIEW` groups are NOT eligible even with
  auto-resolved evidence (identity conflict takes precedence).

---

*Report generated 2026-11-17. All findings are from code read-only inspection. No production code was modified.*
