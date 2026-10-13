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
`unit`, `printed_unit`, `validate`, `allowed_text`.

**Value sources.** Only the configured setting (`setting_value`), a structured `engineering_instruction` or a
`profile_inference` can supply a canonical value. A printed **range**, a **default** or a free-text **note** is refused
by the validator -- they can never be mistaken for the setting. Precedence when several mappings could supply one value:
`configured_setting > engineering_instruction > documented_derivation > assumption` (then manual resolution in review).

**Transformation primitives** (named, no code): `direct`, `enum`, `boolean`, `scale`, `multiply`, `divide`, `ratio`,
`unit_conversion`, `percentage`, `bitmask`, `regex`, `constant`, `decision_table`, `impedance_rx`, `impedance_polar`.
Units convert only where `units.CONVERSIONS` lists the pair (kV -> V ...), automatically from a selector's declared
`unit` to the canonical unit.

**Capability gaps.** `gap` declares that the document states something the canonical model cannot represent: the value
stays *Unsupported*, the evidence is cited and preserved, nothing is approximated.

Coverage is reported per import (`catalog_coverage`): raw settings split into catalog
mapped / unsupported / unresolved, read by the extension, not interpreted and outside Distance Protection (they add up
to the extracted settings), plus canonical values by outcome. Review rows are not raw settings.

Not covered here: 7SA511 (paused pending verified source data), any administrator UI, database storage, CSV/Excel/XML.
