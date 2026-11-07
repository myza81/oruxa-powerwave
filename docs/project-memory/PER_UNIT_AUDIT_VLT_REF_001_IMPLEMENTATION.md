# VLT-REF-001 — Voltage PU reference-side safety

Recorded: 2026-11-07. Branch: `feature/vlt-ref-001-voltage-reference-safety`.
Policy: DEC-211.

## Defect confirmed

The VLT-REF-001 investigation (task 2) live-reproduced the defect before
implementation. A COMTRADE recording with Secondary-referred Voltage channels
(PS flag "S") was normalized against a Primary voltage base (Measurement Group
path and Source Default path), producing:

- **Measurement Group path** — `configured`, `0.000833 pu` (expected ≈ 1.0 pu). DEFECT.
- **Source Default path** — `configured`, `0.000833 pu` (expected ≈ 1.0 pu). DEFECT.
- **`reference_compatibility`** — `null` on all Voltage channels. No gate ran.

Root cause: `apply_source_reference()` in `per_unit_reference.py` returned
`resolution` unchanged for `engineering_type != "Current"`. No Voltage analogue
of `apply_current_reference()` existed.

## Engineering policy (DEC-211)

The LIM-001/DEC-210 reference-side architecture is extended to Voltage.

| Reference pair | Conversion policy | reference_compatibility |
|---|---|---|
| Primary/Primary | Eligible subject to existing gates | compatible |
| Secondary/Secondary | Eligible subject to existing gates | compatible |
| Primary/Secondary or Secondary/Primary | PU unavailable; return raw ENG | incompatible |
| Unknown measurement or base | Previously allowed conversion retained | unverified |
| Both unknown | Previously allowed conversion retained | unverified |

No VT ratio scaling, side inference, sample reinterpretation, or new storage
model. Configuration defaults to `"unknown"` for backward compatibility.
Existing configurations become `unverified`, not `incompatible`.

## Implementation

### New classifier

`app.domain.per_unit_reference.apply_voltage_reference()` — structurally
mirrors `apply_current_reference()`. Classifies the measurement/base pair,
attaches `reference_compatibility`, `measurement_side`, `base_reference_side`
to the resolution, and blocks the resolution (`status=base_required`) on a
known mismatch. Existing unrelated unavailability reasons retain precedence.

### Gate extended

`apply_source_reference()` in `per_unit_reference.py` — previously returned
unchanged for Voltage. Now routes to `apply_voltage_reference()` for
`engineering_type == "Voltage"`, using `voltage_group_config.base_reference_side`
(group path) or `profile.voltage_base_reference_side` (Source Default path),
falling back to `"unknown"` when neither is available.

### New configuration fields

| File | Field | Scope |
|---|---|---|
| `domain/voltage_group_config.py` `VoltageBaseConfiguration` | `base_reference_side: ReferenceSide = "unknown"` | Voltage Measurement Group |
| `domain/per_unit.py` `PerUnitBaseProfile` | `voltage_base_reference_side: ReferenceSide = "unknown"` | Source Default profile |

### Services updated

- `services/voltage_group_config_registry.py` — `update_fields()` accepts and
  persists `base_reference_side`.
- `services/voltage_group_config_service.py` — `update_voltage_configuration()`
  validates and passes `base_reference_side` to registry.
- `services/per_unit_service.py` — `SourcePerUnitConfigView` gains
  `voltage_base_reference_side`; `_view_for_source()` and
  `upsert_source_per_unit_config()` updated.
- `services/measurement_group_view_service.py` — `VoltageGroupConfigView` gains
  `base_reference_side`; `_build_voltage_view()` populates it from the config.

### Wire paths

- `services/waveform_service.py` `_resolve_effective_per_unit()` — looks up
  the `VoltageBaseConfiguration` from `voltage_config_registry` for the Group
  path (`profile_id != source_id`), passes as `voltage_group_config`. Source
  Default path uses `profile=per_unit_profile`.
- `services/per_unit_provenance_service.py` `_build_source_channel_provenance()`
  — same group-config lookup added for the provenance endpoint group path.

### APIs extended (additive only)

- `schemas/measurement_group.py` — `VoltageGroupConfigOut` and
  `VoltageGroupConfigUpdateRequest` gain `base_reference_side: ReferenceSide = "unknown"`.
- `schemas/per_unit.py` — `SourcePerUnitConfigOut` and
  `SourcePerUnitConfigUpdateRequest` gain `voltage_base_reference_side: ReferenceSide = "unknown"`.
- `api/v1/measurement_groups.py` — `_view_to_out()` populates
  `base_reference_side`; `put_voltage_config()` passes it to service.
- `api/v1/per_unit.py` — `put_source()` passes `voltage_base_reference_side`
  to `upsert_source_per_unit_config()`.

## Verification

### New tests: `backend/tests/test_per_unit_voltage_reference_safety.py`

33 tests, all passing:

**Unit tests (pure classifier):**
- Primary/Primary → compatible, configured
- Secondary/Secondary → compatible, configured
- Secondary/Primary → incompatible, base_required, reason `voltage_reference_side_incompatible`
- Primary/Secondary → incompatible, base_required
- Unknown base → unverified, configured
- Unknown measurement → unverified, configured
- Both unknown → unverified, configured
- Sides written to resolution fields
- Existing `base_required` not upgraded to `configured` by classifier

**Integration tests (Measurement Group path):**
- All 8 marker × base_side combinations (P/S/C/empty × primary/secondary/unknown)
- Group base_reference_side round-trips through API
- Incompatible does not mutate stored state
- Reference side change takes effect immediately
- Incompatible waveform returns raw unit, not "pu"
- Unverified allows PU conversion
- Coverage unverified_reference_count reported for unverified Voltage
- Coverage needs_configuration_count for incompatible Voltage
- Invalid base_reference_side rejected with 422
- L-G and L-L Voltage channels both classified
- Group path takes precedence over Source Default

**Integration tests (Source Default path):**
- P/primary → compatible
- S/primary → incompatible
- C/primary → unverified
- P/unknown → unverified
- Source Default base_reference_side round-trips through API

**Regression:**
- LIM-001 Current reference safety unaffected

### Full existing backend suite
Existing backend tests (pre-new-tests) pass without regression. No FAILED lines
observed in the full suite run on this branch (dots only through completion).

## Deferred

- **Frontend selectors** for `base_reference_side` (Voltage group) and
  `voltage_base_reference_side` (Source Default) — Phase 2. Existing
  configurations default to `"unknown"` (unverified, not blocked) until
  the owner sets an explicit side.
- **Calculated Voltage** — already restricted by DEC-052; unchanged.
- **Power/phasor mathematics** — unchanged.

Owner review required before acceptance, push, merge or deployment.
