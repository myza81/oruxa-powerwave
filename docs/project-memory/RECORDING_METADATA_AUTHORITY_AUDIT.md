# Recording Metadata Authority & Consumer Audit

**Date:** 2026-11-17  
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`  
**Status:** Investigation complete — no production code changed  

---

## A. Executive Summary

### Architecture overview

`oruxa_powerwave` is a FastAPI (Python) backend + single-page frontend (`frontend/index.html`).  
All state is **in-process, ephemeral**. There is no database. Every workspace, source, measurement group, and per-unit configuration lives in process memory and is lost on server restart.

**Import pipeline** (COMTRADE and BEN only; CSV/Excel via Data Preparation Workspace):

```
Upload (bytes) → TemporaryDirectory → Provider (COMTRADE/BEN/CSV) → DisturbanceRecord
    → SourceMetadata (lightweight) + ActiveSource (full record, retained in memory)
    → WorkspaceRegistry [(workspace_id, source_id) → ActiveSource]
```

**Four distinct metadata scopes** (all in-memory, no persistence):
1. **Recording/Source** — `SourceMetadata` / `ActiveSource` in `WorkspaceRegistry`  
2. **Measurement Group** — `MeasurementGroup` + `VoltageBaseConfiguration` / `CurrentBaseConfiguration` in `MeasurementGroupRegistry` / `VoltageGroupConfigRegistry` / `CurrentGroupConfigRegistry`  
3. **Engineering Context** — `EngineeringContext` in `EngineeringContextRegistry` (workspace-scoped, may span sources)  
4. **Analysis result** — derived fresh per request, never persisted

### Main findings

1. **Recording Details UI is read-only today.** It shows recorder name, channel counts, nominal frequency, timing reference, trigger time, file names, and a time-reference-interpretation selector. No engineering metadata (nominal voltage, CT/VT ratios, phase convention) is displayed or editable there.

2. **CT/VT ratios are analysis-specific, never recording-level.** Every analysis function (Overcurrent, Impedance, Distance Protection) accepts `ct_primary`, `ct_secondary`, `vt_primary`, `vt_secondary` as per-request API parameters. They are never stored against a recording or channel; the user re-enters them for every analysis session.

3. **Nominal voltage is configured at Measurement Group level** (DEC-050, Slices 3–5), not at recording level. The legacy DEC-049 source-wide path also exists. Neither path is exposed from Recording Details.

4. **Nominal frequency** is the only engineering metadata the recording currently owns that all analyses consume — it is imported from the file and used directly by phasor/RMS/overcurrent/compliance analyses.

5. **Measurement groups are not auto-created on import.** Auto-detection (`POST .../suggest`) must be explicitly triggered; groups are confirmed manually. Until confirmed, channels use the legacy DEC-049 source-wide PU path.

6. **Physical calibration status** (Stage 3B) is the only new channel-level engineering metadata recently added. It is immutable after import and gates PU conversion and compliance.

7. **All storage is in-memory.** Nothing survives a session reset or server restart. No metadata persists beyond the browser session.

### Critical risks

- **R-1: Double CT/VT entry risk.** The same CT/VT values may be needed by multiple analyses (Overcurrent, Impedance, Distance) in the same session. No shared storage exists; re-entry is required each time. This creates inconsistency risk and engineer friction.
- **R-2: Nominal voltage is not surfaced on Recording Details.** An engineer cannot see what PU bases are configured without navigating to the Measurement Groups configuration panel.
- **R-3: Nominal frequency is assumed for BEN.** The DEFAULT_NOMINAL_FREQUENCY_HZ (50 Hz) is used when not explicitly supplied at upload. No user-editable field currently exists to correct a wrongly-assumed frequency.
- **R-4: No persistence.** All metadata (groups, PU config, engineering contexts, alignment offsets, CT/VT analysis history) is lost on session end. Recording Details cannot surface a "last-used" CT/VT suggestion because nothing is stored.
- **R-5: Station/recorder name not user-editable.** `station_name` and `recorder_name` come from the file. No override mechanism exists. If the file has a blank or meaningless name, Recording Details cannot correct it.
- **R-6: Phase display convention is not surfaced on Recording Details.** It is derived from Engineering Context / Measurement Group channel membership and cannot be inspected or overridden from a recording-level view.

---

## B. Existing Metadata Inventory

### Recording / Source level (`SourceMetadata`)

| Field | Engineering meaning | Source | Editable | Survives session reset? | Code reference |
|---|---|---|---|---|---|
| `source_id` | Opaque session identity | Generated at upload (`uuid4()`) | No | No (in-memory) | `import_service.py` |
| `workspace_id` | Owning workspace | Caller-supplied | No | No | `source.py:85` |
| `provider_type` | File format: `"comtrade"`, `"ben"`, `"csv_converted"` | Provider | No | No | `source.py:88` |
| `original_filenames` | Original uploaded file names | Upload form | No | No | `source.py:95` |
| `created_at` | Session import timestamp | `utc_now()` | No | No | `source.py:96` |
| `station_name` | Station/substation name from CFG/BEN header | Imported | No | No | `source.py:98` |
| `recorder_name` | Recorder/IED device ID from CFG/BEN header | Imported | No | No | `source.py:99` |
| `nominal_frequency` | Nominal power system frequency (Hz) | Imported (COMTRADE CFG) or assumed (BEN: 50 Hz default) | No (no API endpoint) | No | `metadata.py:16`, `ben/provider.py:46` |
| `timing_reference` | "absolute" / "relative_elapsed" / "time_of_day" | Imported | No | No | `source.py:103` |
| `start_time` | Recording start timestamp (may be naive) | Imported | No | No | `source.py:104` |
| `trigger_time` | Trigger timestamp (may be naive) | Imported | No | No | `source.py:105` |
| `sample_count` | Total samples | Computed at import | No | No | `source.py:107` |
| `duration_seconds` | Recording duration | Computed at import | No | No | `source.py:108` |
| `elapsed_start_seconds` | First sample time (elapsed axis) | Computed | No | No | `source.py:109` |
| `elapsed_end_seconds` | Last sample time (elapsed axis) | Computed | No | No | `source.py:110` |
| `sampling_rates` | Sampling rate(s) in Hz | Imported | No | No | `source.py:111` |
| `samples_per_rate` | Sample counts per rate section | Imported | No | No | `source.py:112` |
| `file_size_bytes` | Combined file size at upload | Captured at upload | No | No | `source.py:124` |
| `preparation_provenance` | JSON bag: format, record class, BEN channel identities, diagnostics, assumed-frequency flag | Provider-generated | No | No | `source.py:142` |
| `time_of_day_reference_seconds` | Seconds-since-midnight for time-of-day sources | Computed at import (CSV/Excel only) | No | No | `source.py:153` |
| `time_basis` | Clock authority: `verified_utc`, `verified_local`, `source_timezone`, `unknown` | Imported (BEN=UTC, BEN5K=unknown, COMTRADE=inferred) | Indirectly (time reference interpretation) | No | `source_timezone.py:37` |
| `time_reference_interpretation` | User-assigned UTC offset (session-only, `TimeReferenceInterpretation`) | User, via PATCH `.../time-reference` | Yes (session-only) | No | `workspace_registry.py:76` |
| `time_reference_revision` | Version counter for interpretation changes | Computed | No | No | `workspace_registry.py` |

**Validation rules:** No business-logic validation on import. `validate()` on `DisturbanceRecord` checks structural integrity (non-empty, non-NaN time axis, non-decreasing time, consistent sample counts).

**Consumers of recording-level metadata:** Waveform display (`waveform_service.py`), phasor analysis (uses `nominal_frequency`, `start_time`), all analyses using timing, Recording Details panel (UI), Recording Events list, synchronization.

### Analog channel level (`AnalogChannelSummary` / `AnalogChannel`)

| Field | Engineering meaning | Source | Editable | Code reference |
|---|---|---|---|---|
| `name` | Channel name string (e.g. "VR", "NORTH BUS VR") | Imported from CFG/BEN | No | `source.py:36` |
| `index` | 1-based position in file | Imported | No | |
| `unit` | Declared engineering unit (e.g. "V", "kV", "A") | Imported from CFG | No | |
| `engineering_type` | Broad classification: Voltage / Current / Power / Frequency / ROCOF / Undefined | Computed from `unit` or `parameter_type` | No (computed) | `channel_classification.py:129` |
| `engineering_quantity` | Rich classification: "Voltage", "Voltage Angle", "Current", "Active Power", etc. | Computed (CSV/Excel) or Undefined (COMTRADE/BEN) | No (CSV/Excel import-time) | `channel_classification.py:239` |
| `phase` | Phase label from CFG (e.g. "A", "R", "N") | Imported from CFG `ph` field | No | `comtrade.py:88` |
| `scale` | Multiplier (`a` coefficient) | Imported from CFG | No | `comtrade.py:88` |
| `offset` | Additive offset (`b` coefficient) | Imported from CFG | No | |
| `primary_ratio` | CT/VT primary ratio from CFG | Imported from CFG (may be None) | No | `comtrade.py:88` |
| `secondary_ratio` | CT/VT secondary ratio from CFG | Imported from CFG (may be None) | No | |
| `measurement_side` | "primary" / "secondary" / "unknown" (from CFG `ps_flag`) | Imported from COMTRADE `ps_flag` field | No | `reference_side.py` |
| `waveform_form` | "instantaneous" / "rms" / "magnitude" / "unknown" | Always `"unknown"` for COMTRADE/BEN; set by CSV/Excel | No | `channel_classification.py:74` |
| `calibration_status` | "verified" / "unverified" / "invalid" / None | Computed at import from `AnalogChannel.calibration_authority` (BEN5K: Unverified; SubBen/COMTRADE: None=not assessed) | No | `source.py:67`, `physical_calibration.py` |
| `calibration_reason` | Reason code for calibration status | Computed at import | No | `source.py:68` |
| `parameter_type` | Raw import-wizard type (CSV/Excel only: "voltage", "current", etc.) | CSV/Excel import | No | `channel_classification.py:91` |

**Note:** `primary_ratio` and `secondary_ratio` are **descriptive metadata only** in this codebase. They are stored on the channel but are NOT automatically applied to convert sample values. Physical scaling is done by the `scale`/`offset` COMTRADE CFG coefficients. See Section E.

### Digital channel level (`DigitalChannelSummary`)

| Field | Source | Editable |
|---|---|---|
| `name` | Imported | No |
| `index` | Imported | No |
| `normal_state` | Imported | No |
| `classification` | Computed at import (triggered/never_triggered/spare) | No |

### Measurement Group level (`MeasurementGroup`)

| Field | Engineering meaning | Source | Editable | Code reference |
|---|---|---|---|---|
| `id` | Stable opaque identity (`"mg-" + uuid4().hex`) | Generated | No | `measurement_group.py:136` |
| `workspace_id` | Owning workspace | Caller | No | |
| `source_id` | Owning source | Caller | No | |
| `kind` | "voltage" / "current" | User/detection | Yes (create/update) | `measurement_group.py:142` |
| `display_name` | Human-readable label | User/detection heuristic | Yes | |
| `channel_refs` | List of `ChannelRef(source_id, channel_name)` | User | Yes | |
| `status` | "suggested" / "confirmed" / "needs_review" / "manual" | Auto or user | Yes | |
| `created_at` | Creation timestamp | Auto | No | |

### Voltage group configuration (`VoltageBaseConfiguration`)

| Field | Engineering meaning | Source | Editable | Code reference |
|---|---|---|---|---|
| `nominal_voltage_ll_kv` | Nominal line-to-line voltage (kV) | User | Yes | `voltage_group_config.py` |
| `reference_mode` | "auto" / "manual" | User | Yes | |
| `reference_override` | "line_to_ground" / "line_to_line" (when manual) | User | Yes | |
| `base_reference_side` | "primary" / "secondary" / "unknown" | User | Yes | |
| `secondary_voltage_ll_v` | Secondary-side voltage (V) | User | Yes | |

Effective reference is derived from channel names (auto) or override (manual), never from `primary_ratio`/`secondary_ratio`.

### Current group configuration (`CurrentBaseConfiguration`)

| Field | Engineering meaning | Source | Editable | Code reference |
|---|---|---|---|---|
| `method` | "equipment_rating" / "manual" / "none" | User | Yes | `current_group_config.py` |
| `equipment_rating_mva` | Equipment MVA rating | User | Yes | |
| `linked_voltage_group_id` | Voltage group to derive Vbase from | User | Yes | |
| `manual_voltage_base_kv` | Manual Vbase if not linked | User | Yes | |
| `manual_ibase_ka` | Direct user-supplied Ibase | User | Yes | |
| `base_reference_side` | "primary" / "secondary" / "unknown" | User | Yes | |

### Legacy source-wide PU (`PerUnitBaseProfile`, DEC-049)

Stored in `PerUnitRegistry`, keyed by `source_id`. Fields: `voltage_base_value`, `voltage_reference_mode`, `voltage_reference_override`, `current_base_mode`, `apparent_power_base_value`, `direct_current_base_value`, `voltage_base_reference_side`, `current_base_reference_side`. All editable by user, all in-memory only.

### Synchronization / time offset (`SynchronizationRegistry`)

| Field | Meaning | Scope | Editable |
|---|---|---|---|
| `alignment_offset_s` | Per-source elapsed-time shift (Slice 1) | `(workspace_id, source_id)` | Yes |
| `t0_workspace_time` | Workspace-wide event origin (Slice 2) | `workspace_id` | Yes |

---

## C. Metadata Consumer Matrix

### C.1 Waveform visualization / channel display

| Aspect | Detail |
|---|---|
| Required engineering inputs | Channel names, engineering_type, unit, scale, offset, waveform samples, synchronization offsets |
| Inputs currently requested from user | Channel selection (which channels to show), unit mode (engineering/per-unit), waveform range |
| Inputs from recording metadata | All channel descriptors, sampling rates, timing, synchronization state |
| CT/VT needed? | No — waveform display never re-scales by CT/VT ratios |
| Nominal voltage needed? | Optional (for PU display) |
| Reuse classification | **READY** for all basic display parameters; **CONDITIONAL** for PU display (requires Measurement Group or legacy source-wide config) |
| Current fallback | Shows engineering-unit values when no PU config exists |

### C.2 RMS (Calculated Channels)

| Aspect | Detail |
|---|---|
| Required engineering inputs | Source channel samples, nominal frequency (for window size), waveform_form eligibility |
| User inputs | Channel selection, operation selection |
| From recording metadata | `nominal_frequency` (from `SourceMetadata`), waveform samples |
| CT/VT needed? | No |
| Reuse classification | **READY** — `nominal_frequency` already consumed from `SourceMetadata` |

### C.3 Phasor Calculator

| Aspect | Detail |
|---|---|
| Required engineering inputs | Voltage/Current channels (Va/Vb/Vc/Ia/Ib/Ic), `nominal_frequency`, start epoch for angle reference, `analysis_time` |
| User inputs | `analysis_time`, optional `reference_frequency_hz_override`, Engineering Context selection |
| From recording metadata | `nominal_frequency` (from each channel's owning source), `start_time` (absolute epoch) |
| CT/VT needed? | No — results in raw engineering units |
| Reuse classification | **READY** for `nominal_frequency`; **READY** for Engineering Context if confirmed |
| Calibration gate | BEN5K channels blocked for authoritative phasor (`physical_calibration_unverified`) |

### C.4 Power Calculator (single-phase)

| Aspect | Detail |
|---|---|
| Required engineering inputs | V magnitude, V angle, I magnitude, I angle (all as RMS phasor inputs in SI base units) |
| User inputs | The four phasor values (typed manually or from Phasor Calculator output) |
| From recording metadata | None — stateless calculator, no workspace scope |
| Reuse classification | **NOT SUITABLE** for direct recording metadata injection — this is a manual workspace tool |

### C.5 Three-phase Power (Calculated Channel operation)

| Aspect | Detail |
|---|---|
| Required engineering inputs | 3× V phasors + 3× I phasors from same measurement point |
| User inputs | Channel role assignments |
| From recording metadata | Channel engineering_type, phase identity (via Engineering Context role resolution) |
| CT/VT needed? | No — operates on whatever engineering unit the channels carry |
| Reuse classification | **READY** for phase/type; **CONDITIONAL** on Engineering Context confirmation |
| Calibration gate | Provenance status propagated (`all_verified`, `exploratory_unverified`, etc.) |

### C.6 Overcurrent Protection Analysis

| Aspect | Detail |
|---|---|
| Required engineering inputs | Current channel (phase A/B/C), `analysis_time`, IEC IDMT curve, TMS, pickup current, CT primary/secondary (for secondary→primary conversion), `recording_basis`, `nominal_frequency`, optional `system_voltage_kv` for equipment-loading mode |
| User inputs | CT primary/secondary, characteristic, TMS, pickup, recording basis, system voltage (all per-request, not stored) |
| From recording metadata | `nominal_frequency` (from source, via Engineering Context role resolution); current channel selected via Engineering Context |
| CT/VT metadata on channel? | `primary_ratio`/`secondary_ratio` exist on `AnalogChannelSummary` from COMTRADE CFG, but are NOT automatically consumed — user must re-enter |
| Reuse classification | **CONDITIONAL** for `nominal_frequency` (already consumed); **CONDITIONAL** for CT ratios if `primary_ratio`/`secondary_ratio` from COMTRADE CFG are surfaced as suggestions |
| Missing metadata | No stored CT/VT; `primary_ratio`/`secondary_ratio` from COMTRADE not currently offered as defaults |

### C.7 Distance Protection Analysis

| Aspect | Detail |
|---|---|
| Required engineering inputs | 2× V + 2× I channels (phase-pair loop), `vt_primary`, `vt_secondary`, `ct_primary`, `ct_secondary`, impedance basis, `nominal_frequency`, zone settings |
| User inputs | CT/VT ratios, zone settings, fault loop selection — all per-request |
| From recording metadata | `nominal_frequency` (from source); channels via Engineering Context |
| CT/VT metadata on channel? | Same as Overcurrent — not automatically consumed |
| Reuse classification | **CONDITIONAL** for CT/VT if imported ratios surfaced as suggestions |

### C.8 Impedance Locus

| Aspect | Detail |
|---|---|
| Required engineering inputs | Per-phase V and I phasors, VT/CT ratios, `nominal_frequency` |
| User inputs | VT/CT ratios, impedance basis |
| From recording metadata | `nominal_frequency`, channels via Engineering Context |
| Reuse classification | **CONDITIONAL** for CT/VT |

### C.9 Sequence Components Analysis

| Aspect | Detail |
|---|---|
| Required engineering inputs | 3× V or 3× I channels, `nominal_frequency` |
| User inputs | None specific to recording metadata |
| From recording metadata | `nominal_frequency`, channels via Engineering Context |
| Reuse classification | **READY** |

### C.10 Compliance & Capability (voltage measurement normalization)

| Aspect | Detail |
|---|---|
| Required engineering inputs | Voltage channels, PU base (from Measurement Group or legacy source-wide), `nominal_frequency`, reference profiles |
| User inputs | Reference profile selection, PU base configuration (via Measurement Groups or legacy) |
| From recording metadata | `nominal_frequency`, PU base from Measurement Group configuration |
| Calibration gate | BEN5K channels blocked (`calibration_unavailable` state) |
| Reuse classification | **READY** for `nominal_frequency`; **CONDITIONAL** for PU base (requires Measurement Group confirmation) |

### C.11 Event Reconstruction

| Aspect | Detail |
|---|---|
| Required engineering inputs | Per-unit resolution (from waveform endpoint), channel display axes |
| User inputs | None additional — PU configuration comes from Waveform (DEC-138) |
| From recording metadata | Channels, PU resolution (read-only consumer) |
| Reuse classification | **READY** — Event Reconstruction is a PU consumer only, never a configurator |

### C.12 Multi-recording synchronization

| Aspect | Detail |
|---|---|
| Required engineering inputs | `timing_reference`, `start_time` / `trigger_time`, `time_basis`, elapsed axes |
| User inputs | Manual alignment offset per source; workspace-wide t0 |
| From recording metadata | All timing fields |
| Reuse classification | **READY** for read; **NOT SUITABLE** for automatic — no auto-sync implemented by design (DEC-036) |

### C.13 Oscillation Analysis

| Aspect | Detail |
|---|---|
| Required engineering inputs | Channel samples, `nominal_frequency` |
| User inputs | Channel selection, analysis window |
| From recording metadata | `nominal_frequency`, channel descriptors |
| Reuse classification | **READY** |

---

## D. Measurement-Group Findings

### How groups are currently created

1. **Manual creation** — engineer calls `POST .../measurement-groups` with `kind`, `display_name`, and channel membership. Produces `STATUS_MANUAL`.
2. **Auto-detection** — engineer calls `POST .../measurement-groups/suggest`; `detect_measurement_groups()` clusters channels by name pattern into `STATUS_SUGGESTED` or `STATUS_NEEDS_REVIEW` candidates. These are created as groups but require explicit confirmation to become `STATUS_CONFIRMED`.
3. **Never automatic on upload** — no group auto-creation happens at import time (confirmed by code at `measurement_groups.py:22`).

**Code reference:** `measurement_group_detection.py:95`, `measurement_group_service.py:generate_suggested_groups_for_source()`

### Group semantics

- Groups are **source-scoped** (a group belongs to exactly one source/workspace).
- A group has exactly one `kind`: `"voltage"` or `"current"`.
- A group member must be a **source channel** (not a calculated channel) of the matching engineering type.
- A channel may belong to **at most one** measurement group (enforced by `channel_already_grouped` error).
- Calculated channels **inherit** their source group via Slice 7 (DEC-050): a calculated channel inherits the group of its source input, with exceptions for multi-input Voltage arithmetic (DEC-052/DEC-116).
- Multiple groups of different kinds can coexist for the same source.
- Multiple voltage groups at different voltage levels can coexist in one source (the whole point of DEC-050).

### Can group membership be corrected?

Yes. `PATCH .../measurement-groups/{id}` and `PUT .../measurement-groups/{id}/members` allow membership changes. A channel can be removed from a group and added to another.

### Group identity stability

The group `id` (`"mg-" + uuid4().hex`) is stable for the life of the in-memory session. It does NOT survive session reset or source re-import. No persistence layer exists.

### Risks using groups as CT/VT ownership boundary

**[OPEN]** CT/VT ratios do NOT currently belong to measurement groups. The group owns Voltage Base (kV) and Current Base (kA/MVA method). CT/VT ratios as physical transformer descriptors are a separate engineering concept that is currently analysis-specific only. If CT/VT ratios were attached to a measurement group, it would need to be clearly separated from the PU base configuration that the group already owns.

---

## E. CT/VT and Scaling Findings

### How physical scaling currently works

**COMTRADE samples → engineering quantities:**

1. COMTRADE CFG declares `a` (scale multiplier) and `b` (additive offset) per channel.
2. Physical value = `sample_integer * a + b` — this is applied by `ComtradeProvider` at import, producing `waveform_data` already in engineering units (V/kV, A/kA, etc.).
3. These are stored in `AnalogChannel.scale` and `AnalogChannel.offset` and reflected in `AnalogChannelSummary`.

**BEN samples → engineering quantities:**

1. BEN decoding applies its own gain factors (`(signed_word >> 4) * gain * sqrt(2)`) in `app/providers/ben/normalize.py` / `legacy_ben5k/normalize.py`.
2. The result is a `DisturbanceRecord` already in engineering units.
3. BEN5K decoding is currently under investigation for root-cause scaling errors (see CURRENT_STATE.md "BEN-wide physical scaling root cause"). No production correction is applied.

**COMTRADE `primary_ratio` and `secondary_ratio` fields:**

- These are stored on `AnalogChannel` and `AnalogChannelSummary` as metadata.
- They are sourced from CFG line fields 8/9 (the `primary`/`secondary` values).
- They are **NOT automatically applied** to convert between primary and secondary.
- The `measurement_side` ("primary"/"secondary"/"unknown") is derived from the COMTRADE `ps_flag` field.
- Code reference: `comtrade.py:88` (`_AnalogDef`), `reference_side.py:comtrade_measurement_side()`

**Explicit primary/secondary conversion:**

- Used in Overcurrent, Impedance, Distance Protection: the `convert_to_relay_secondary()` / `convert_impedance_basis()` / `convert_array_to_relay_secondary()` functions in `overcurrent.py` / `impedance.py` perform explicit CT/VT ratio-based conversion.
- These functions take user-supplied CT/VT values per request.
- They do NOT read `primary_ratio`/`secondary_ratio` from channel metadata.

### Double-scaling risk

**Current risk is LOW for COMTRADE**: The file-level CFG `a`/`b` scaling is applied once at import. No subsequent re-scaling occurs in the application. Analysis functions operate on the already-scaled engineering-unit values.

**Risk assessment for CT/VT metadata:** If CT/VT ratios from channel metadata were to be automatically applied as a default for analysis functions, there would be a **double-scaling risk** for COMTRADE files that are already stored as primary-side values (i.e., the CFG `a`/`b` scaling already incorporates CT/VT transformation). The `measurement_side` field on the channel descriptor should be verified before any automatic CT/VT application.

**BEN5K risk:** Currently under investigation. The root cause of BEN5K scaling errors has been partially characterized (see CURRENT_STATE.md) but no correction is in production.

---

## F. Per-Unit Compatibility Assessment

### Current implementation vs. approved direction

**Two concurrent PU paths exist (DEC-051 coexistence):**

| Path | Status | Code |
|---|---|---|
| DEC-049 source-wide | Deployed, operational | `per_unit.py`, `PerUnitRegistry`, `per_unit_service.py` |
| DEC-050 group-aware | Deployed, operational (Slices 1–7) | `voltage_group_config.py`, `current_group_config.py`, `group_aware_per_unit.py` |

**Precedence rule (DEC-051):** If a channel belongs to a confirmed/suggested/manual measurement group, the group-aware path is used. If not grouped, the DEC-049 source-wide path is used. A grouped channel never falls back to source-wide.

### Consistency with PER_UNIT_MEASUREMENT_MODEL.md

| Requirement (from PER_UNIT_MEASUREMENT_MODEL.md) | Implementation status |
|---|---|
| Multiple voltage levels per source | IMPLEMENTED (Slices 1–5) |
| Voltage PU denominator matches L-G or L-L reference | IMPLEMENTED (Slice 3, `voltage_group_config.py`) |
| L-L denominator from `nominal_voltage_ll_kv` directly | IMPLEMENTED |
| L-G denominator = `nominal_voltage_ll_kv / sqrt(3)` | IMPLEMENTED |
| Generic multi-input V addition/subtraction → `base_required` | IMPLEMENTED (DEC-052/DEC-116) |
| L-L declared voltage channel (VAB etc.) uses L-L base | IMPLEMENTED (`line_to_line_voltage.py`, DEC-115) |
| Current normally displayed in A/kA, not PU | IMPLEMENTED (DEC-212 §2: cursor readouts stay kA) |
| Current PU not mandatory | IMPLEMENTED (method=`none` is valid, `base_required` state) |
| Calculated channel inherits source group | IMPLEMENTED (Slice 7) |
| Voltage multi-input calc channel never auto-inherits | IMPLEMENTED (DEC-052) |
| Event Reconstruction is PU consumer only | IMPLEMENTED (DEC-138) |
| BEN5K channels blocked from authoritative PU | IMPLEMENTED (Stage 3B, `calibration_unavailable` status) |

**No contradictions found** between current implementation and PER_UNIT_MEASUREMENT_MODEL.md, as of this audit. The DEC-049 legacy path is explicitly intended to coexist during transition.

---

## G. Proposed Metadata Ownership Model

Based on the audit, the following boundary model is consistent with current code and approved decisions:

### Recording level (owns these, never duplicated elsewhere)
- `station_name`, `recorder_name` (from file; currently immutable)
- `nominal_frequency` (from file; currently immutable; assumed for BEN)
- `timing_reference`, `start_time`, `trigger_time`, `time_basis`
- `time_reference_interpretation` (session-only user override)
- `original_filenames`, `file_size_bytes`, `provider_type`, `preparation_provenance`
- `sample_count`, `duration_seconds`, `sampling_rates`

### Measurement Group level (owns these, channel-specific configs live here)
- `nominal_voltage_ll_kv` (Voltage group: the engineer's reference base)
- `reference_mode` / `effective_reference` (line-to-ground vs. line-to-line)
- `base_reference_side` (primary/secondary for PU purposes)
- `secondary_voltage_ll_v` (secondary-side voltage, optional)
- Current base method and parameters (`method`, `equipment_rating_mva`, `linked_voltage_group_id`, `manual_ibase_ka`)

### Channel level (owns these, immutable after import)
- `name`, `unit`, `index`, `scale`, `offset`
- `engineering_type`, `engineering_quantity`
- `phase`, `measurement_side`
- `primary_ratio`, `secondary_ratio` (descriptive, not auto-applied)
- `calibration_status`, `calibration_reason`
- `waveform_form`

### Engineering Context level (owns cross-source channel role assignments)
- Phase identity assignments (`PHASE_A`/`PHASE_B`/`PHASE_C` etc.)
- Phase display convention (A/B/C vs. R/Y/B)
- Cross-source membership
- Status lifecycle (suggested/confirmed/manual)

### Workspace level (owns session state)
- Alignment offsets per source (`SynchronizationRegistry`)
- Workspace-wide event origin `t0` (`SynchronizationRegistry`)
- Calculated channel definitions (`CalculatedChannelRegistry`)

### Analysis result level (owns these, never promoted to recording-level)
- CT/VT ratios used in an analysis computation
- IEC IDMT characteristic parameters, TMS, pickup
- Impedance zone settings
- System voltage for equipment loading
- Reference frequency override

**[PROPOSAL]** CT/VT descriptive metadata could be attached at the channel level (as `primary_ratio`/`secondary_ratio` already are), or at the measurement-group level as a separate "physical transformer descriptor" object (distinct from PU base configuration). This needs an owner decision before implementation.

---

## H. UX Opportunities

### Controls currently duplicated across pages

1. **Nominal frequency** — currently fixed from the file. If editable, it appears as an implicit default in every analysis (phasor, overcurrent, compliance). Centralizing a "nominal frequency override" at Recording Details would propagate to all analyses. **[OPEN — engineering ownership at recording level, but no current override UI]**

2. **CT/VT ratios** — re-entered for every analysis session in Overcurrent, Impedance, Distance. The `primary_ratio` / `secondary_ratio` from COMTRADE CFG are stored on channel metadata but never offered as defaults. **[PROPOSAL: surface as read-only suggestions in analysis forms]**

3. **Measurement Group configuration** — currently only accessible from a dedicated panel inside Waveform Analysis. No link or summary from Recording Details.

### Controls suitable for Recording Details

| Control | Justification |
|---|---|
| Station name (editable override) | Recording-level identity, not tied to any analysis |
| Nominal frequency (editable, with "assumed" flag) | Recording-level property, consumed by all analyses; especially important for BEN |
| Time reference interpretation (UTC offset) | Already on Recording Details (implemented) |
| `primary_ratio` / `secondary_ratio` read-only display | Descriptive CT/VT from COMTRADE — informational, helps engineer validate analysis setup |
| `measurement_side` per channel (read-only) | Informs the engineer whether file is already primary-side or secondary-side |
| Calibration status badges | Already in Waveform channel list; could be summarized at recording level |
| Measurement Group summary (read-only link) | Show configured voltage levels at recording level |

### Controls that must stay in Waveform Analysis

| Control | Reason |
|---|---|
| Measurement Group nominal voltage / reference configuration | Requires visual context of which channels belong to the group |
| PU base mode (derived/direct/none) | Requires measurement group membership context |
| Engineering Context phase assignments | Requires visual inspection of waveform |
| Synchronization alignment offsets | Requires visual waveform alignment |
| Event origin (t0) | Workspace-wide, requires waveform inspection |
| Calculated channel definitions | Waveform-workspace artifacts |

### Metadata visible but read-only on Recording Details

- `station_name`, `recorder_name` (from file; override per suggestion above)
- `nominal_frequency` (read-only unless override implemented)
- All timing fields (start_time, trigger_time, timing_reference, time_basis)
- Channel count, sampling rates, duration
- File names and size
- Provider type (COMTRADE/BEN/CSV)
- Preparation provenance (BEN: assumed frequency flag, layout family, record class)
- Per-channel `primary_ratio`/`secondary_ratio` (informational)
- Calibration status summary

### Missing-data behavior

- If `nominal_frequency` is assumed (BEN), Recording Details should show a warning indicator.
- If `measurement_side` is "unknown" on all channels, CT/VT-based analysis should alert the engineer.
- If no measurement groups are confirmed, PU display should show "PU not configured" — this is already implemented (`base_required` state).

### Repeated user input to eliminate

| Input re-entered today | Suggested resolution |
|---|---|
| `nominal_frequency` override for BEN | Make editable at Recording Details; propagate to all analysis defaults |
| CT/VT ratios in Overcurrent / Impedance / Distance | Pre-populate from channel `primary_ratio`/`secondary_ratio` as suggestions (not auto-applied); store last-used per session |
| System voltage (kV) for equipment loading mode | Could be pre-populated from confirmed Measurement Group nominal voltage (CONDITIONAL) |

---

## I. Gaps and Unresolved Questions

### I-1: No persistence layer

**[OPEN]** All metadata is in-memory and ephemeral. Recording Details cannot surface "last session's configuration" because nothing is persisted. Any "centralize metadata" design must decide whether metadata should survive session end.

**Decision mode: ANALYSIS** — the current architecture explicitly chose no server-side persistence (DEC-015, DEC-012). Extending this requires an explicit owner decision.

### I-2: CT/VT ownership

**[OPEN]** CT/VT ratios as a **recording-level authoritative configuration** (distinct from COMTRADE CFG descriptive fields and analysis-specific inputs) have no home. The question of whether CT/VT should be stored at the measurement group, recording, or channel level is unresolved.

**Decision mode: ANALYSIS** — sufficient evidence exists to present options.

### I-3: Nominal frequency editability for BEN

**[OPEN]** BEN imports assume DEFAULT_NOMINAL_FREQUENCY_HZ (50 Hz). No API endpoint allows the engineer to correct this assumption after import. The `nominal_frequency` field on `SourceMetadata` is immutable.

**Decision mode: ANALYSIS** — a straightforward addition (PATCH endpoint + UI control).

### I-4: Station/recorder name editability

**[OPEN]** `station_name` and `recorder_name` come from the file and cannot be overridden. If the recorder has a blank or technical ID, the engineer cannot give the recording a meaningful name.

**Decision mode: ANALYSIS** — straightforward; needs owner scope decision on whether to add a user-editable "display name" override.

### I-5: Double-scaling risk if CT/VT metadata auto-applies

**[OPEN]** COMTRADE files whose CFG `a`/`b` coefficients already incorporate CT/VT transformation would be double-scaled if `primary_ratio`/`secondary_ratio` were automatically applied. The `measurement_side` field would need to be verified first. A "suggest but don't auto-apply" approach is safer.

**Decision mode: ANALYSIS** — conservative approach (pre-populate as suggestion, let engineer confirm) is unambiguous and avoids the risk.

### I-6: Engineering Context vs. Measurement Group boundary

**[OPEN]** Engineering Contexts (bay/equipment identity) and Measurement Groups (phase-set/PU base) address different concerns but are closely related. No UI currently links or summarizes both from Recording Details. The relationship between confirming a Measurement Group and confirming an Engineering Context is not documented at the UI level.

**Decision mode: DEFER** — not needed until Recording Details redesign scope is confirmed.

### I-7: BEN5K scaling root cause

**[OPEN]** BEN5K numerical conversion accuracy is under active investigation (see CURRENT_STATE.md). Until resolved, BEN5K channels carry `calibration_status = "unverified"` and are excluded from authoritative PU output.

### I-8: `waveform_form` always "unknown" for COMTRADE/BEN

**[FACT]** No COMTRADE or BEN channel ever gets a non-"unknown" waveform_form. This means RMS eligibility cannot be inferred from metadata alone. Analyses that need an instantaneous waveform (RMS, phasor) rely on the `rms_detector.py` heuristic or accept the form at face value. This is documented and intentional (see channel_classification.py §5B).

---

## J. Recommended Implementation Sequence

**These are proposals only. Each requires owner approval before implementation.**

### Phase 1 — Make Recording Details informative (read-only improvements)

1. Display `nominal_frequency` with an "assumed" warning badge for BEN recordings.
2. Display `measurement_side` per channel in the channel list (already in API response, not shown in UI).
3. Show `primary_ratio` / `secondary_ratio` per channel (already in API, not surfaced in Recording Details today).
4. Add a summary of configured Measurement Groups and their nominal voltages to Recording Details.
5. Show calibration status summary at recording level (count of verified/unverified/not-assessed channels).

### Phase 2 — Nominal frequency editability

6. Add PATCH endpoint to update `nominal_frequency` on `SourceMetadata` (session-only).
7. Add a recording-level UI control for this, with provenance label ("from file" vs. "user override").
8. Propagate updated value to all analyses — verify that all consumers read from live `SourceMetadata`, not a captured snapshot.

### Phase 3 — CT/VT suggestion (not auto-apply)

9. Surface `primary_ratio` / `secondary_ratio` from channel metadata as pre-fill suggestions in Overcurrent, Impedance, and Distance Protection analysis forms.
10. Add a clear "Suggested from file — verify before use" label.
11. Do NOT auto-apply; engineer must confirm.

### Phase 4 — Station/recorder name override

12. Add user-editable "display name" override at recording level (session-only), shown in Recording Details and throughout the UI where the source is listed.

### Phase 5 — Persistence decision (requires architectural owner decision)

13. Evaluate whether measurement group configuration, CT/VT suggestions, and nominal frequency overrides should survive session end (requires a storage decision — currently out of scope per DEC-015 philosophy).

---

## K. Evidence Appendix

### K.1 Core domain model files

| File | Purpose |
|---|---|
| `backend/app/domain/source.py` | `SourceMetadata`, `AnalogChannelSummary`, `DigitalChannelSummary`, `ActiveSource` |
| `backend/app/domain/channels.py` | `AnalogChannel`, `DigitalChannel` (full detail including `calibration_authority`) |
| `backend/app/domain/disturbance_record.py` | `DisturbanceRecord` — unified internal waveform contract |
| `backend/app/domain/metadata.py` | `RecordingMetadata`, `DEFAULT_NOMINAL_FREQUENCY_HZ` |
| `backend/app/domain/timing.py` | `SamplingInformation`, `TimingInformation` |
| `backend/app/domain/channel_classification.py` | Engineering type/quantity taxonomy and classifiers |
| `backend/app/domain/measurement_group.py` | `MeasurementGroup`, group kind/status constants |
| `backend/app/domain/voltage_group_config.py` | `VoltageBaseConfiguration`, group-aware voltage PU resolver |
| `backend/app/domain/current_group_config.py` | `CurrentBaseConfiguration`, group-aware current PU resolver |
| `backend/app/domain/per_unit.py` | Legacy DEC-049 source-wide PU model |
| `backend/app/domain/physical_calibration.py` | `PhysicalCalibrationAuthority`, calibration status/purpose contract |
| `backend/app/domain/synchronization.py` | Timing coordinate transforms (`alignment_offset_s`, `t0_workspace_time`) |
| `backend/app/domain/source_timezone.py` | `TimeBasis`, `DEFAULT_SOURCE_TIMEZONE` ("Asia/Kuala_Lumpur") |

### K.2 Provider files (import pipelines)

| File | Purpose |
|---|---|
| `backend/app/providers/comtrade.py` | COMTRADE CFG+DAT parser; extracts `station_name`, `rec_dev_id`, analog/digital channels, timing, `a`/`b` scaling, `primary`/`secondary`/`ps_flag` |
| `backend/app/providers/ben/provider.py` | `BenProvider` — BEN32 SubBen and BEN5K Legacy adapter |
| `backend/app/providers/ben/normalize.py` | BEN → `DisturbanceRecord` conversion |
| `backend/app/providers/ben/legacy_ben5k/normalize.py` | BEN5K Legacy normalization; sets `calibration_authority` Unverified |
| `backend/app/services/import_service.py` | Upload orchestration; builds `SourceMetadata`, retains `ActiveSource` |

### K.3 Schema / API files

| File | Purpose |
|---|---|
| `backend/app/schemas/source.py` | `SourceSummaryOut`, `AnalogChannelOut`, `SourceChannelsOut` — wire shape of recording/channel metadata |
| `backend/app/schemas/measurement_group.py` | `MeasurementGroupOut`, `VoltageGroupConfigOut`, `CurrentGroupConfigOut` |
| `backend/app/schemas/per_unit.py` | Legacy DEC-049 per-unit config wire shapes |
| `backend/app/api/v1/sources.py` | Source/channel/waveform API endpoints |
| `backend/app/api/v1/measurement_groups.py` | Measurement Group CRUD and suggest endpoints |
| `backend/app/api/v1/per_unit.py` | Legacy DEC-049 per-unit config endpoints |

### K.4 Analysis service files

| File | Purpose |
|---|---|
| `backend/app/services/waveform_service.py` | Waveform range extraction, PU resolution (group-aware + legacy), cursor values |
| `backend/app/services/phasor_analysis_service.py` | Phasor computation; uses `nominal_frequency`, `start_time` from `SourceMetadata` |
| `backend/app/services/overcurrent_analysis_service.py` | Overcurrent; accepts `ct_primary`/`ct_secondary` per request |
| `backend/app/services/distance_protection_analysis_service.py` | Distance Protection; accepts `vt_primary`/`vt_secondary`/`ct_primary`/`ct_secondary` per request |
| `backend/app/services/impedance_analysis_service.py` | Impedance locus; accepts CT/VT per request |
| `backend/app/services/compliance_measurement_service.py` | Compliance voltage normalization |
| `backend/app/services/group_aware_per_unit.py` | DEC-050 Slice 5 group-aware PU bridge |

### K.5 Frontend

| File | Relevant section |
|---|---|
| `frontend/index.html:22218` | `renderRecordingDetails()` — current Recording Details panel: recorder, channels, freq, timing, trigger, files |
| `frontend/index.html:22294` | `wwTimeReferenceControl()` — time reference interpretation control (only interactive element in Recording Details) |

### K.6 Project-memory documentation

| Document | Relevance |
|---|---|
| `docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md` | Authoritative for all PU design decisions (DEC-049/DEC-050) |
| `docs/project-memory/DECISIONS.md` | DEC-012 (workspace scoping), DEC-015 (no file persistence), DEC-019 (DisturbanceRecord retention), DEC-049/DEC-050 (PU), DEC-051 (coexistence), DEC-052/DEC-115/DEC-116 (representation rules), DEC-121/DEC-122 (timezone), DEC-213 (calibration authority) |
| `docs/project-memory/BEN_WIDE_SCALING_ROOT_CAUSE_2026-11-16.md` | BEN5K physical scaling investigation |

---

*Report generated 2026-11-17. All findings are from code read-only. No production code was modified.*
