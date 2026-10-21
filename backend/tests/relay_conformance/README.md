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

## Shadow canonical boundaries (DEC-199 Phase 2A)

For a catalog with a `boundaries` section the expectation also records `shadow_geometry`. Per zone it holds:
- `production_geometry` -- the V1 classification, which shadow evidence never changes;
- `shadow_geometry` -- `exact` or `not_assembled` with a reason;
- the edges with provenance;
- the top;
- `represented` / `not_represented`.

It also records `shadow_golden`: independent engineering values from `shadow_golden.py` -- `R(X) = r_at_axis +
X / tan(angle)` at 0 / 0.25 / 0.5 / 1.0 x the X reach, plus inside / outside probes -- never computed by V2.

The suite checks that:
- each golden equals the documented equation;
- the V2 edges pass through every golden edge point;
- the V2 region classifies every probe as stated;
- V1 still holds no value for an inclined edge.

## Shadow directional half-planes (DEC-199 Phase 2B)

When a catalog declares `directional` boundaries, each zone record also holds `directional`, keyed by retained side
(`counter_clockwise` / `clockwise`). Each entry carries:
- the canonical `angle_deg` and its `frame`;
- `fidelity` (e.g. `static_equivalent`);
- the source row with its raw value;
- the source's `convention`;
- the `transform` (e.g. "canonical angle = -ArgDir = -15 deg (ArgDir 15 as printed, deg)");
- references and the equation.

A zone is assembled only when every declared directional boundary is derived; otherwise it is `not_assembled` with the
reason.

The golden adds the following, computed from the angular condition on atan2(X, R) and never from V2:
- `directional` -- the canonical angles;
- `directional_points` -- points on each ray at 0.25 / 0.5 / 1.0 x the reach;
- `directional_probes` -- each ray +/- 2 deg at 0.1 / 0.25 x the reach, plus first-quadrant, +X, negative-R, -X and
  third-quadrant points.

A reverse zone's points are reflected once.

The suite checks that:
- the V2 line passes through every ray point;
- every probe is classified as the golden says;
- the assembled zone is placed in the absolute frame exactly once.

The REL511 owner sheet states no ArgDir / ArgNegRes, so its zones are not assembled. The synthetic variant
`rel511` / `directional` states them; see `expectations/rel511--directional.json`.

## Shadow lower reactance limits and closed zones (DEC-199 Phase 2C)

When a catalog declares a `reactance_lower` boundary, each zone record holds `lower`:
- `x_minus`, the frame, the unit and the fidelity;
- the source row with its raw value, the transform, references and the equation;
- `null` if it is not derived.

A zone is assembled only when it is derived. Every assembled zone also states `relay_behaviour_fidelity`: the weakest of
its boundaries' fidelities. This is separate from `shadow_geometry: exact`, which only says the documented relations
are represented exactly.

The golden adds:
- `lower_points` -- on X = -x_minus;
- `lower_probes` -- just above / below, checked against the V2 lower half-plane alone.

For a zone with a lower limit it also adds:
- `closed`;
- `active` -- each documented line sampled for a stretch of the outline;
- `boundary_probes` -- labelled `inside_<b>` / `beyond_<b>` probes.

The suite checks that:
- the V2 zone classifies every probe as the golden says;
- a closed zone outlines without plotting bounds;
- the labels cover every active boundary.

Samples:
- `rel511--closed-region` -- forward Z1 bounded by the lower limit, reverse Z2 by the left line;
- `rel511--wide-sector` -- the refused 220 deg sector.

## Shadow tilted upper reactance limits (DEC-199 Phase 2D)

When a catalog declares a `reactance_upper` boundary, each zone record holds `tilt`:
- `x_at_reference`, `tilt_deg`, the frame, the unit and the fidelity;
- the source row with its raw value, the transform, references and the equation;
- `null` if it is not derived.

The tilted limit is added *alongside* the zone's plain horizontal top, never in its place, so `represented` gains
`"tilt"` without changing `"top"` or `not_represented`. A zone with no verified left resistive boundary (e.g. 7SL87)
is never fully assembled, but its tilt boundary is still derived and recorded on its own.

The golden adds:
- `tilt_points` -- on the tilted line at R = 0 (the pivot), 0.25 and 0.5 x the X reach;
- `tilt_probes` -- just inside (below) / outside (above) each point, checked against the tilted half-plane alone.

The existing resistive `probes` and their `inside()` membership also apply the tilt constraint for R >= 0, so a
probe near the top that was inside before a non-zero tilt can correctly become outside -- the golden recomputes
this every time, it is never hand-patched.

Samples:
- `7sa613--zone-reduction-10` -- a non-zero Zone 1 tilt, now assembled;
- `7sl87--tilt-5` / `--tilt-blank` / `--tilt-malformed` -- the tilt boundary alone, derived / blank / unreadable.

## 7SA613's closed shadow region (DEC-199 Phase 2F)

7SA613's lower reactance boundary (`7sa613.boundary.lower`) reuses the Phase 2C `reactance_lower` kind with no new
code anywhere in `app/domain/distance_boundaries.py`, the catalog model/validator/interpreter, this harness or
`shadow_golden.py`: zone discovery, assembly and the independent goldens already handled an arbitrary relay's lower
boundary generically. Only the catalog JSON changed.

Z1, Z2, Z3 and Z1B now report `represented` including `"lower"` and `not_represented: []`: their shadow phase-phase
region is closed. Z5 is excluded by the boundary's own zone scope (its reach is independently forward/reverse, not
symmetric about one setting), unaffected by this change.

`shadow_geometry: exact` still states only that the assembled relations are exact; it is not a claim that directional
clipping or load-trapezoid encroachment -- both still unrepresented -- are resolved.

Sample `7sa613--lower-reverse` (Op. mode Z1B = Reverse) proves the lower boundary reflects together with the rest of
a reverse zone's boundaries.

## Fixed OEM constants and boundaries recorded on their own (DEC-199 Phase 2G)

A boundary's angle (or any field already shaped `{source: ...}`) may instead be a fixed OEM constant --
`{"constant": <number>, "unit": ..., "name": ..., "sign"?: 1|-1}` -- when the OEM reference states it directly
rather than as a document setting. It carries no `range` (a constant has no setting range to be outside of) and may
not coexist with `source` on the same field. A constant's own `BoundarySource` has no page/line: there is no
document location for it.

**This is never a substitute for a missing configured value, in either direction.** A boundary with one field
sourced from the document and another fixed by a constant still needs the document-sourced field to actually be
present and readable; a blank or unreadable configured value derives no boundary regardless of what else is fixed.

When a boundary is derived for a zone whose region cannot (yet) be fully assembled -- no paired edge, no verified
left/directional boundary -- it is still recorded, with full provenance, and `shadow_edge_golden` (`shadow_golden.py`)
gives it an independent engineering golden of its own: points on the documented line, with inside/outside probes,
checked against that edge's half-plane alone. A zone whose region *is* assembled keeps using the existing
`shadow_golden` instead; the two are never both populated for the same zone.

Sample: GRZ100's forward zones (Z1, Z1X, Z2, ZF, Z3) derive their right blinder (`BFRS`, fixed 75 deg) this way, with
no zone reaching a complete assembled region.

## GRZ100 left blinder and assembled forward zones (DEC-199 Phase 2I)

**GRZ100's five forward zones (Z1, Z1X, Z2, ZF, Z3) now assemble a complete open-bottomed region** when the sheet
is quadrilateral and BFLS-angle is present and within its documented range (90-135 deg):
- `shadow_geometry = "exact"`, `relay_behaviour_fidelity = "static_equivalent"` (BFL is a voltage-polarised
  boundary; its DC steady-state geometry is the static equivalent -- a new fidelity level for resistive boundaries).
- `represented = ["top", "right", "left"]`, `not_represented = ["lower"]` (no directional or lower-reactance
  boundary modelled; ZBS, reverse zones, ZND and Z4 remain out of scope).

**A resistive boundary's `r_at_axis` can now be a fixed OEM constant.** Same mechanism as Phase 2G's constant
`angle_deg`: `{"constant": 0, "unit": "ohm", "name": "..."}`. BFL's intercept is BFLS = 0 Ω (Toshiba 6F2S0834-0,
settings p. 34). A missing BFLS-angle is never satisfied by the fixed zero intercept.

**`shadow_golden` for asymmetric zones.** `zone_golden()` now handles different right and left edge angles --
the symmetric case (REL511 / 7SA613 / 7SL87) keeps `"cot"` unchanged; asymmetric zones (GRZ100, BFR 75 deg vs
BFL typically 120 deg) output `"cot_right"` and `"cot_left"` instead of `"cot"`.

**GRZ100 expectations** with `ZS-C = quad` and a readable BFLS-angle: `shadow_geometry` changes from
`not_assembled` to `exact`; `shadow_golden` is populated; `shadow_edge_golden` becomes null. `grz100--mho`: no
boundaries, no change. All 28 synthetic expectations regenerated.
