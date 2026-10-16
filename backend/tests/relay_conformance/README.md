# Relay conformance harness (DEC-199, Relay Scalability Phase 0)

One generic suite tests every relay. A relay is added with **data**: a catalog with its references, a synthetic sheet
spec and an expectation. No dedicated Python test file and no browser spec are written for it.

| Part | Where | What it is |
|---|---|---|
| Catalog + references | `backend/app/data/parameter_catalog/<family>/<relay>.json` (+ `catalog.lock.json`) | The relay knowledge (DEC-194 / DEC-198) |
| Sheet spec | `sheets/<id>.json` | A synthetic setting sheet: layout, lines, notes, named variants. The single source for backend **and** browser tests |
| Expectation | `expectations/<name>.json` | What the import must produce for a sheet (or an owner's real sheet) |
| Known findings | `known_findings.json` | Deviations the suite reports but a phase did not fix (each needs a later, approved slice) |

Generic tests: `backend/tests/test_relay_conformance.py` (backend) and `browser-tests/relay_import_conformance.spec.js`
(the real review UI, from the same expectations). Primitive tests for reusable capabilities stay in
`backend/tests/test_relay_catalog_capabilities.py`.

## Sheet spec (`"schema": "oruxa.relay-sheet/1"`)

```json
{
  "schema": "oruxa.relay-sheet/1", "id": "acme100", "relay": "ACME 100", "description": "...",
  "layout": {"columns": [40, 230, 340, 450], "rows_per_page": 40, "line_height": 16, "top": 780},
  "value_index": 1,
  "lines": [["LZOP: ...", "Scheme: ACME100_V1"], ["TAP NAME", "TAP SETTING", "TAP RANGE"], ["Z1 X", "3.2", "0.05-250 ohms"]],
  "notes": [["Zone 1", "Forward direction timer set to 0.15s"]],
  "variants": {"no_notes": {"notes": []}}
}
```

A line is keyed by its first cell (a name, a code, or "code name"); `null` leaves a column empty. The PDF is built only by
`sheet_spec.sheet_pdf` (one escaping and layout implementation; deterministic bytes). Overrides, usable by every test,
the snapshot tool and the browser (`relaySheet(id, overrides)`): `variant`, `drop`, `set` (value cell; `""` = a blank
cell), `set_range`, `insert_after`, `append`, `notes`. An unknown key is an error.

    python -m tests.relay_conformance.sheet_cli acme100 '{"set": {"Z1 X": ""}}' > sheet.pdf     # from backend/

## Expectation (`"schema": "oruxa.relay-expectation/1"`)

`sample` names the sheet (`{"kind": "synthetic", "sheet": ..., "overrides": ..., "manual": [{"item_id", "value"}]}`) or an
owner sheet (`{"kind": "real", "file": "acme100.pdf"}`, run only when `RELAY_SAMPLE_PDF_DIR` is set; owner PDFs are never
committed and only the values the file names are compared -- `"values_mode": "subset"`). The rest is engineering
semantics, compared exactly:
- `identity`;
- `counts`;
- `readiness` (initial / after confirming assumptions and accepting suggestions);
- `zones` (status, direction, characteristic, geometry classification);
- `engine` (adapter reason codes by zone);
- `blocking`;
- `values` (text and category of every canonical value);
- `provenance` (raw text, source rows, cited references);
- `preserved` zone rows;
- `offers`;
- `approximations`;
- `apply` (status, characteristic, basis and the applied zones -- the V1 engine geometry);
- `not_interpreted_distance`, `coverage`, `catalog_sources_absent`.

`mutations` declares the sheet-specific mutation data (`disable_zone` with its cells, or the reason none exists; known
findings as data).

`golden` (DEC-199 Phase 1) is the **V1** geometry of every zone V1 draws, built by `golden.py` from the expectation's own
`apply.zones` with V1 only (never V2):
- the key outline (V1's corner / circle formula);
- a 17 x 17 membership grid over the zone's extent (`"1"` inside, `"0"` outside, `"."` too close to a boundary to compare);
- inside / outside probes per boundary and the 180 deg reflection of each inside probe;
- the characteristic, geometry mode, direction and numeric basis;
- `not_drawn` zones.

The suite checks that V1 still produces the golden exactly and that the V2 shadow kernel
(`app/domain/distance_geometry.py`, via `distance_geometry_compat.py`) reproduces it. The snapshot tool writes the golden
from the observed Apply. **V1 remains production-authoritative; V2 is shadow-only.** Coordinates: R horizontal, X
vertical, ohms, angles in degrees CCW from +R; one tolerance, 1e-6 ohm (see `distance_geometry.py`).

## Adding a relay

1. Write the catalog and its references; `catalog_cli validate-catalog`; record its lock entry.
2. Write `sheets/<id>.json` in the shape the extractor produces for the real sheet (invented numbers).
3. Record the expectation from the current behaviour, **then review every line of it** -- an expectation states what the
   import must do; it is not a log:

       python -m tests.relay_conformance.snapshot <id> --sheet <id> --write
       python -m tests.relay_conformance.snapshot <id>--<scenario> --sheet <id> --overrides '{"set": {...}}' --write
       python -m tests.relay_conformance.snapshot <id>.real --real <file>.pdf --write   # RELAY_SAMPLE_PDF_DIR set

4. Add `mutations.disable_zone` (the cells that take a zone out of service, or the reason none exists).
5. Run `pytest tests/test_relay_conformance.py` and the browser `relay_import_conformance.spec.js`.

The suite then checks, for every relay and without relay code:
- **catalog integrity:** valid, locked, references cited and scoped, derivations refused without a verified reference;
- **expectations:** the expectation itself, determinism, readiness and Apply agreeing, OEM-neutral Apply, catalog
  provenance on every value, every raw setting accounted for;
- **review authority:** relay settings that do not exist never shown as Missing; forged suggestions / manual values /
  tokens refused;
- **mutations:** blank and malformed cells never becoming values, note edits changing no configured value, a disabled
  zone dropping its blockers, harmless and geometry-affecting preserved values behaving as the catalog declares.
