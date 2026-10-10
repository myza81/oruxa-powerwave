# Relay Settings Import — Architecture (Slice 1: foundation)

Status: **Slice 1** (domain contracts) and **Slice 2** (manual entry + engine
adapter) implemented on `feature/distance-relay-import`. Extraction, relay
profiles, auto-population and any UI are later slices. Approval record:
[DECISIONS.md — DEC-RELAY-IMPORT-1](DECISIONS.md#dec-relay-import-1--relay-settings-import-oem-neutral-raw--profile--canonical-architecture).

## Purpose

Distance Protection ([DISTANCE_PROTECTION_ANALYSIS.md](DISTANCE_PROTECTION_ANALYSIS.md))
is entered manually today. Import Relay Settings will let a user supply a
relay setting file (PDF first; Excel/CSV/XML/OEM exports later), have the
backend read it, identify the relay, interpret its OEM-specific parameters
and populate the Distance Protection form. The feature is **Import Relay
Settings**, not "Import PDF".

## Pipeline

```text
RawRelayDocument            (what was found; no meaning decided)
      |
RelayProfile / Interpreter  (all relay-family knowledge lives here)
      |
CanonicalDistanceProtectionModel   (OEM-neutral engineering model + provenance)
      |
Distance characteristic engine     (unchanged; no relay-specific logic)
```

Code: [backend/app/domain/relay_import/](../../backend/app/domain/relay_import/)
(pure dataclasses, no Pydantic/FastAPI/storage imports).

| Module | Holds |
|---|---|
| `raw_document.py` | `RawRelayDocument`, `RawSetting` (section path, parameter id, name, raw + normalized value, unit, range, page/location, source text, notes, extraction provenance), `SourceFormat` |
| `provenance.py` | `Sourced[T]` (value + `Provenance`), `MappingStatus` (mapped / inferred / unresolved), `SourceRef` |
| `canonical_distance.py` | the canonical model |
| `profile.py` | `RelayProfile` protocol, `GenericFallbackProfile`, `RelayProfileRegistry` |

## Canonical model

`CanonicalDistanceProtectionModel` = `RelayMetadata` + `InstrumentTransformers`
+ `ProtectedLine` + an arbitrary tuple of `DistanceZone` + unmapped settings
+ notes. Highlights:

- **Zones are a collection**, keyed by `zone_id` (`Z1`, `Z1B`, `Z7`, ...);
  nothing assumes four zones or one reach/one resistance per zone.
- **Per zone:** status (enabled/disabled/inactive/unknown); direction
  (forward/reverse/non-directional/inactive/unknown); PP and PE enable
  flags; phase, earth and common timers; `CharacteristicSpec`; `reach`,
  `earth_reach`, `zero_sequence_reach` (each an `ImpedanceValue`);
  `ResistiveReach` (common / phase-phase / phase-earth / reverse / extras);
  `ResidualCompensation`; tilt; per-zone `UnresolvedSetting`s.
- **`ImpedanceValue`** is *either* rectangular (R, X) *or* polar
  (magnitude, angle) as the source gave it; the form is preserved and
  `to_rectangular()` is an explicit call, never implicit.
- **`CharacteristicSpec`** types: quadrilateral, mho, lenticular,
  polygon_custom (explicit vertices), unknown. Only quadrilateral and mho are
  drawable by today's engine; the others are *representable* so adding them
  later does not reshape the model. Extra geometry values go in
  `parameters`.
- **`ResidualCompensation`** has a `kind` — K0 magnitude+angle, Kr+Kx,
  RE/RL + XE/XL, or OEM-specific — and only that kind's components may be
  populated (enforced). There is deliberately **no conversion** between
  kinds: they are not interchangeable without the relay's reference
  impedance and convention.
- **Setting basis** (primary/secondary), CT/VT ratios and voltage/current
  bases are recorded as `Sourced` values, defaulting to unresolved.

## Provenance and status

Every engineering value is a `Sourced`: the value plus where it came from
(`SourceRef`s back to raw `setting_id`s, page/location), the profile id and
version, the raw text, and notes. Statuses: **mapped** (deterministic),
**inferred** (confirmation recommended), **unresolved**. Enforced invariants:
an unresolved item carries *no* engineering value (only its raw text), and a
mapped/inferred item must cite at least one source. The value is independent
of any user-facing wording. `model.items_needing_confirmation()` and
`model.unresolved_paths()` drive future review UI.

## Profile strategy

Relay-family knowledge (parameter codes, vocabulary, unit/basis conventions,
characteristic semantics) lives in `RelayProfile` implementations — data-driven
where possible, custom code only where necessary — **never** in the generic
domain or in `distance_protection.py`. Concrete profiles will live outside
the domain, grouped per repository convention at the time (e.g. by
manufacturer family); none are created in Slice 1 and no empty folders mirror
the future layout. A test guards that the generic engine and the relay_import
package contain no relay-model names.

`RelayProfileRegistry.interpret()` uses a profile only when exactly one
**positively confirms** the document. Zero confirmed matches, or more than
one (ambiguity), yields the generic fallback.

## Unknown-relay fallback

A future unknown relay is (1) structurally read by a generic extractor,
(2) retained as raw settings, (3) mapped only where safe, (4) left
unresolved where meaning is unknown, (5) completed manually. The
`GenericFallbackProfile` interprets nothing: every raw setting becomes an
`UnresolvedSetting` and the model has no zones. Extraction success never
implies electrical meaning.

## Standing rules

- **Manual entry remains supported** and is the ultimate fallback. Slice 2
  integrates manual entry with the canonical model; Slice 1 changes no UI or
  engine behaviour.
- **Ephemeral data.** Uploaded setting files and everything derived from
  them (raw documents, canonical models) are session-scoped, in-memory
  values. They are never written to the application database or the
  storage layer. The domain package has no persistence imports (tested).
- **No LLM / external-AI dependency** in the baseline. Interpretation is
  deterministic profile logic.
- **Progressive validation.** Relay support is validated family-by-family /
  model-by-model against real setting sheets; an unvalidated relay uses the
  fallback rather than a best guess.
- **Benchmark hierarchy** (existing `powerwave` > `detego.app` > owner
  requirements) applies to later UI; Slice 1 has none.

## Relay styles the model must carry (design samples)

MiCOM P441/P44x, Siemens 7SA511 / 7SA613 / SIPROTEC 5 7SL87, ABB/Hitachi
REL511 / REL670 / RED670, Toshiba GRZ100 / GRL200, LFZP, RCS-941, RELZ100.
Representation notes and the sample-by-sample mapping are exercised in
[backend/tests/test_relay_import_model.py](../../backend/tests/test_relay_import_model.py)
(P441-style polar reach + split PP/PE resistance + K0; 7SA613-style
explicit R/X + RE/RL; REL670-style R1/X1, R0/X0, RFPP/RFPE, independent
timers; reverse, non-directional, inactive and 8-zone cases; unknown
characteristic). These are modelling tests, not parser tests, and do not
depend on any sample PDF.

## Slice 2 — manual entry and the engine adapter

```text
Manual form (flat API params -> ZoneSettings)      [transitional boundary]
        -> manual_to_canonical()      relay_import/manual_entry.py
        -> CanonicalDistanceProtectionModel
        -> adapt_to_engine()          relay_import/engine_adapter.py
        -> existing ZoneSettings / distance engine (unchanged)
```

- **Transitional boundary.** The frontend and the three API endpoints
  (selected-time, locus, manual) still receive flat per-zone parameters; no
  request/response or UI change. Right after `_zone_settings()` builds the
  three `ZoneSettings`, `engine_zones_from_manual()` routes them through the
  canonical model and adapter. Only fields the selected characteristic reads
  are carried, so engine results are identical (tested over fixed cases and
  400 randomised forms, including blank and garbage values). A characteristic
  or basis string the model cannot represent passes the original settings
  through untouched, exactly as before, so the service keeps reporting
  "not operated" / "needs configuration".
- **Manual provenance.** `ProvenanceOrigin.MANUAL_ENTRY`, status mapped, no
  document references, no profile. A blank field is *unresolved*, never
  defaulted. Manual zones are forward, phase-phase only; mho `|Z|` and the
  quadrilateral reactive reach are each the polar reach `magnitude ∠ angle`.
- **Adapter** (`adapt_to_engine(model, engine_basis=..., allow_incomplete_zones=False)`)
  is a read-only view returning `EngineAdaptation(supported, characteristic,
  zones, zone_ids, reasons, warnings)`. It never mutates the model, never
  picks a value to make conversion succeed, and reports *all* problems.
  `allow_incomplete_zones=True` (manual form only) passes a blank reach as
  absent (`None`), which the engine already treats as Not Operated.
- **Engine capability** (unchanged): exactly three zones in order; one
  characteristic (mho or quadrilateral) for all zones; phase-phase loops
  only; forward geometry only; one delay and one shared angle per zone; zone
  ohms compared in the selected impedance basis.
- **Supported canonical fields:** zone status (enabled / disabled / inactive),
  forward direction, phase-phase operation, polar reach (→ mho `reach_ohm` or
  quadrilateral `reactive_reach_ohm`, angle → shared characteristic angle),
  phase-phase (else common) and reverse resistive reach, common (else phase)
  timer, setting basis equal to the engine basis. Disabled/inactive zones
  beyond the third are dropped only if disabled.
- **Preserved but reported, not used:** phase-earth operation, earth timer,
  residual compensation, zero-sequence reach, line data.
- **Refused as unsupported (explicit reason, never guessed):** lenticular,
  polygon/custom, unknown or unresolved characteristic; mixed characteristics;
  reverse, non-directional or unknown direction on an enabled zone;
  phase-phase operation not established; phase-earth-only resistive reach;
  R/X-form reach; unresolved reach, resistive reach or timer; conflicting
  common/phase values; a separate tilt; an enabled zone beyond the third;
  unknown or mismatching primary/secondary basis (no CT/VT conversion is
  performed or inferred).
- **Deferred:** phase-earth plotting, lenticular/polygon/OEM geometry,
  per-zone characteristic, reverse/non-directional zones, per-loop timers.
- **Unchanged policies:** nothing is persisted; no LLM; manual entry remains
  fully supported.
- **Judgement call to confirm:** the engine is phase-phase, so the *phase*
  timer is treated as the matching delay and an extra earth timer is
  reported, not treated as a conflict.

## Intentionally unresolved in Slice 1

- ~~Mapping onto the existing `ZoneSettings`~~ — done in Slice 2 (above).
- Geometry for lenticular, polygon and unknown characteristics, and
  per-loop (phase-earth) evaluation — need engine work and owner decisions.
- Setting-basis (primary/secondary) handling when the source does not say.
- Whether active setting groups need a multi-group model (currently one
  active group name).
- Extraction technology, relay identification heuristics, upload API shape.
