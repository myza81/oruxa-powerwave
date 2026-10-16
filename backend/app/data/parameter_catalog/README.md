# Parameter catalogs

External, validated JSON that says what a relay's setting names **mean**. Governing decision:
`docs/project-memory/DECISIONS.md` DEC-194 (Parameter Catalog Architecture); design:
`docs/project-memory/RELAY_IMPORT_ARCHITECTURE.md`.

```text
PDF -> generic extraction -> relay identification -> OEM catalog (JSON) -> generic matcher / transformer
    -> canonical model -> review / readiness -> Apply -> generic protection engine
```

The Distance Protection engine never reads these files. It consumes only the canonical model the
catalog populates. Raw OEM names and codes live on in each value's provenance (the review's *Source*).

```text
canonical/distance_protection.json   the application's own vocabulary (ids, labels, units, groups, order, engine paths)
<manufacturer>/<family>.json         one OEM catalog = one catalog version
catalog.lock.json                    semantic digests of locked (validated / tested / active) versions
```

## Precedence (DEC-195)

For every canonical value and zone: (1) the **active** catalog mapping is authoritative -- also when it does not
resolve (Missing / Conflict / Unreadable / Unsupported stay so; nothing falls back to Python); (2) an extension profile
(a hand-written profile with the same `profile_id`) supplies only targets the catalog does not map; (3) otherwise the
raw setting is retained as *Not interpreted* and never reaches the engine. The catalog's `authority` decides the review
category (an `assumption` mapping is shown as an Assumption).

## Adding a relay (no Python)

```text
python -m app.tools.catalog_cli validate-catalog <file> [--root DIR]     schema, canonical targets, transforms, units,
                                                                         enums, duplicates, applicability, lock
python -m app.tools.catalog_cli dry-run <file> <sheet.pdf> [--json]      recognised / mapped / transformed /
                                                                         unsupported / conflicting / unmapped; changes nothing
python -m app.tools.catalog_cli list                                     installed and rejected catalogs
```

1. Write `<manufacturer>/<family>.json` with `"lifecycle": "draft"`. Map only what the source states.
2. **Validate** with `validate-catalog` (the service validates the same way at start-up and refuses to start on an
   invalid shipped catalog -- it is never partly used). Move to `"validated"`.
3. **Dry-run** it against a real sheet with `dry-run`; read the unmapped and conflicting lists.
4. **Test**: add a test that reads a real or synthetic sheet through the catalog (see
   `backend/tests/test_parameter_catalog_new_relay_by_json.py`; for a relay that already has a hand-written
   profile, prove equivalence as `test_parameter_catalog_*_equivalence.py` do). Move to `"tested"`.
5. **Activate**: set `"lifecycle": "active"` and restart. Only an active catalog interprets real imports. A catalog
   whose `profile_id` a hand-written profile owns becomes catalog-first for that relay (the profile is an extension).
   Only one version of a `catalog_id` may be active, and two active catalogs may not claim the same relay and firmware.
6. Record the version in `catalog.lock.json` (`write_lock`). A locked version is never edited: a change of meaning is
   a new `version` (imports record the catalog id and version, so v1 and v2 imports are distinguishable).

## Catalog format (`oruxa.parameter-catalog/1`)

| Key | Meaning |
|---|---|
| `catalog_id`, `version` (`MAJOR.MINOR.PATCH`), `lifecycle` | identity; `draft` -> `validated` -> `tested` -> `active` |
| `applicability` | `manufacturer`, `family`, `model`, `versions` (firmware patterns, `*` = any) |
| `profile_id` | the routing id (defaults to `catalog_id`) |
| `identification` | model patterns, family markers, parameter signatures, the scheme pattern that confirms the relay |
| `zones` | `discover` (a name pattern with group `n`) or `static` (listed ids) |
| `distance_scope` | code prefixes / section markers / names that mark a leftover setting as distance-related |
| `mappings` | one entry per canonical parameter and zone target |

A mapping: `canonical` (registry id), `zone` (`"*"`, an id or a list; zone-scope parameters only), a `source` selector
(or named `sources`), an optional `transform` (a primitive or a chain), `requires` (gates), `value_source`,
`authority`, `confidence`, `note`. A selector matches by `name` (templates `{n}` `{nn}` `{zone}`), `code` (+ `name`),
`name_pattern`, `pattern_in_text`, `indexed_family` or `zone_family`, and says how to read the value: `type`,
`unit`, `printed_unit`, `validate`, `allowed_text`, `infinity`. DEC-198 Amendment 6: `"infinity": true` (number sources
only) reads the relay's own setting "Infinity" / "∞" as a configured value (`inf`) -- e.g. a stage timer that never trips
on time -- instead of an unreadable one; a range column showing only "Infinity" is then not taken as a printed unit.
Without the option, "Infinity" stays Unreadable.

**Value sources.** Only the configured setting (`setting_value`), a structured `engineering_instruction` or a
`profile_inference` can supply a canonical value. A printed **range**, a **default** or a free-text **note** is refused
by the validator -- they can never be mistaken for the setting. Precedence when several mappings could supply one value:
`configured_setting > engineering_instruction > documented_derivation > assumption` (then manual resolution in review).

**Transformation primitives** (named, no code): `direct`, `enum`, `boolean`, `scale`, `multiply`, `divide`, `ratio`,
`unit_conversion`, `percentage`, `bitmask`, `regex`, `constant`, `decision_table`, `impedance_rx`, `impedance_polar`.
Units convert only where `units.CONVERSIONS` lists the pair (kV -> V ...), automatically from a selector's declared
`unit` to the canonical unit.

**Capability gaps.** `gap` declares that the document states something the canonical model cannot represent: the value
stays *Unsupported*, the evidence is cited and preserved, nothing is approximated. DEC-198: `gap.kind` says why --
`"unsupported"` (default: the meaning is understood, the engine cannot represent it; shown "Not yet supported") or
`"unverified"` (what the value means, or how it converts, is not established for this relay; shown "Not yet supported"
with a different explanation). Both keep the raw value and block where the engine needs the value.

**Authoritative references** (DEC-198). A top-level `references` list of `{id, title, verification, document?, section?,
page?, scope?}` (`verification`: `verified` | `unverified`). A reference *identifies* its source (OEM manual number,
section, page, an owner decision) and never copies its text: unknown keys are refused and every field is length-capped.
A mapping cites them with `"references": [ids]`; they appear in the value's provenance and the review's *Source*.
A mapping may declare `"verification": "verified"` -- a **verified documented derivation** -- only when its authority is
`documented_derivation`, its confidence `mapped`, and it cites at least one `verified` reference; otherwise the catalog is
refused (`unverified_reference`). A `documented_derivation` value that is `mapped` is shown as **Documented relay
behaviour**, not as Mapped.

**Gated constants.** A `constant` mapping honours its `requires` gates like any other mapping (e.g. a documented zone
behaviour applies only while the zone's own switch is On); the gate's setting is cited as evidence.

**Material preserved settings** (DEC-198). A `zone_preserved` entry may list `unverified_when: [raw values]`: a preserved
setting with such a value may change the zone's operation while its meaning is not verified. It is shown Unverified
("Not yet supported"), keeps its exact value (never interpreted) and blocks an **enabled** zone.
DEC-198 Amendment 6: instead, `material_unless: [raw values]` declares a *geometry-affecting* preserved setting that is
harmless only with those values (e.g. a load-cutout resistance of "infinity"): a **blank** configured cell blocks an
enabled zone as a missing source value ("Source value missing" -- its effect is unknown), any other stated value blocks it
as a boundary the engine cannot represent ("Not yet supported"). The two options are exclusive.
DEC-198 Amendment 7: `"always_material": true` declares a geometry-affecting preserved setting with **no** harmless value
(e.g. the GRZ100 reverse-zone backup-trip switch, which only chooses between two forward-offset reaches): a stated value
blocks an enabled (or geometry-reviewed) zone as a boundary the engine cannot represent, a blank cell as a missing source
value. The three options are exclusive.

**Zone status not verified** (DEC-198 Amendment 7). A status `gap` of kind `unverified` (e.g. a relay whose trip logic is
a site-specific programmable scheme the source does not define) never invents Enabled / Disabled and is never offered for
entry; the engine adapter still reviews the zone's configured geometry as for a zone in service and fails with
`ZONE_STATUS_UNVERIFIED`. A status `gap` of kind `unsupported` that cites a verified reference states a documented zone
function the engine does not model (e.g. a command-protection-only element): `ZONE_STATUS_UNSUPPORTED`, preserved, not
drawn.

**Not exposed** (DEC-198). `"not_exposed": {"note": ...}` on a mapping (no source, transform, gate, evidence, authority or
gap) states that the relay has **no configurable setting** for this canonical parameter -- inherent / fixed behaviour.
It is *not* a missing source value (shown "Not a relay setting", never counted as Missing) and it **never supplies a
value**: only a separate documented-derivation mapping of the same target can, and wins when it resolves. A relay cannot
both state and not expose a setting (a configured-setting mapping of the same target is a conflict).

**Zone document notes** (`source_notes`, DEC-197). A list of rules `{pattern, zone_id, zone_ids, subjects}`: `pattern` is
searched in a raw row's text (name and value) and has a named group `zone`; `zone_id` (default `Z{zone}`) turns the token into a
zone id, `zone_ids` overrides listed tokens (`{"3R": "ZR"}`); `subjects` (`timer` / `status`, a pattern and a value template
`{1} s`) label what the note states. A matching row becomes a `SourceNote` of that zone -- shown as "Document note / proposed
requirement", **never a value, a status or a default**. A note naming a zone the document does not have stays a raw row.

**Preserved zone settings** (`zone_preserved`, DEC-197). A list of `{zone, names | name_pattern, reason}`: the matching raw settings
(templated per zone; `{zone}` / `{n}` / `{nn}` / `{key}`, regex-escaped in a pattern) are kept **with their zone** as Unsupported,
never-resolvable review rows carrying `reason` -- for geometry or logic the canonical model cannot represent (blinders, boundary
angles, reach multipliers). A setting a mapping reads is never taken. Coverage counts them as recognised-unsupported.

**Listed zone keys.** A listed zone may declare `"key"` (default: its id), used as `{key}` in templates when the sheet's own zone
token differs from the zone id (`Z_PP1`, `En_ZPP_Rev`, `KZ1X`).

**Blank setting cells.** A row whose setting cell the extractor established as blank (`row:blank_value_range`) reads as *Missing*
("the configured setting cell is blank (the range column shows 'Infinity', which is not a setting)") -- never the range, never a
default. A merely empty value without that evidence stays *Unreadable*.

**Other keys.** `distance_scope.name_patterns` (regex over names, for codes written inside names); `applicability.manufacturer: null`
(the manufacturer is explicitly not asserted; shown as Missing); a selector's `note` is appended when that source cannot be read.
The canonical registry (1.1.0) adds `ct_vt.ct_ratio` / `ct_vt.vt_ratio` for relays that state ratios (never split into primary /
secondary). The lock digest counts `source_notes` / `zone_preserved` only when a catalog uses them.

Coverage is reported per import (`catalog_coverage`): raw settings split into catalog
mapped / unsupported / unresolved, read by the extension, not interpreted and outside Distance Protection (they add up
to the extracted settings), plus canonical values by outcome. Review rows are not raw settings.

## Shipped catalogs

| Catalog | Relay | Mode |
|---|---|---|
| `schneider/p44x.json` | MiCOM P441 | catalog-first (+ hand-written extension) |
| `hitachi_energy/red670.json` | RED670 | catalog-first (+ hand-written extension) |
| `hitachi_energy/rel670.json` | REL670 | catalog-only |
| `hitachi_energy/rel511.json` | REL511 | catalog-only, 1.2.0: documented characteristic / loops (ABB 1MDB06309-YN), documented Secondary basis and RFZn / RFNZn meanings (ABB 1MRK 506 101 / 109 / 167-UEN, REL 511 2.3 / 2.5 -- verified for the family, version-dependent for the 1.x-style sheet); RFZn inclined boundary and left / directional boundary unsupported; ZnBlock unverified |
| `siemens/siprotec5_7sl87.json` | 7SL87 | catalog-only, 1.1.0: documented quadrilateral characteristic (selector not exposed), per-phase R (ph-ph) / R (ph-g) and the operate-delay loop assignment (Siemens C53000-G5040-C011-9, V07.50 -- version-dependent for the 7SL87_8.81 sheet); +R inclined at the distance characteristic angle and the left / directional boundary unsupported (+R = R (ph-ph) only at 90 deg); phase-phase load cutout in use unverified; blank delays Missing |
| `siemens/siprotec4_7sa613.json` | 7SA613 | catalog-only, 1.1.0: documented polygonal characteristic and PP / PE loops (selectors not exposed), documented Secondary basis, per-phase R(Zn) ph-ph and the delay loop assignment (Siemens 7SA6 manuals C53000-G1176-C156-2 / -7, version-dependent for the V4.2-style sheet); explicit Infinity delays configured (engine-unsupported on a zone in service); inclined +R / -R and non-directional Z5 unsupported; blank delays and a blank R load (ph-ph) Missing |
| `toshiba/grz100.json` | GRZ100 | catalog-only, 1.1.0: documented Secondary basis, fixed zone directions, inherent PP / PE (selectors not exposed), ZnS as the Quad X reach and Z1X instantaneous (Toshiba 6F2S0834-0 / 6641-1, version-dependent, not the exact 201A manual); ZS-C / ZG-C exact selectors; zone trip state Unverified (site-specific PLC) with geometry still reviewed; Z4 preserved, not drawn; BFRS +R, BFLS / ZBS-angle −R, the ZR1 / ZR2 forward offset (`always_material`) and the ZND impedance element unsupported; no source gap |
| `toshiba/grl200.json` | GRL200 | catalog-only (verified subset) |
| `nr_electric/rcs941.json` | RCS-941 | catalog-only (verified subset) |
| `relz/relz100.json` | RELZ100 | catalog-only (verified subset) |
| `lfzp/lfzp111.json` | LFZP111 | catalog-only (limited review, deferred) |

Support status per relay and the owner-UAT matrix: `docs/project-memory/RELAY_IMPORT_ARCHITECTURE.md`, "Remaining relay families".

Not covered here: 7SA511 (paused pending verified source data), any administrator UI, database storage, CSV/Excel/XML.

## Conformance data for a new relay (DEC-199)

A catalog ships with its synthetic sheet (`backend/tests/relay_conformance/sheets/<id>.json`) and expectation
(`backend/tests/relay_conformance/expectations/<id>.json`); the generic conformance suite tests it with no relay-specific
test code. See `backend/tests/relay_conformance/README.md`.
