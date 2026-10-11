# Relay Settings Import — Architecture (Slice 1: foundation)

Status: **Slices 1-8 + 8A (review status taxonomy, below)** (domain contracts, manual entry + engine adapter,
ephemeral upload, generic PDF extraction, relay identification, MiCOM P441
interpretation profile, read-only Extraction Review, review confirmation / resolution) implemented
and **integrated into `main`** (2026-10-11) on top of the completed Oscillation Analysis Phase 1
baseline. Slice 6 is **Implemented / Awaiting
Validation**; Slices 7 and 8 are **Implemented / Awaiting owner UAT**. Every other relay
is identification-only; auto-population / Apply (Slice 9) are later slices and **not started**. Approval record:
[DECISIONS.md — DEC-184](DECISIONS.md#dec-184--relay-settings-import-oem-neutral-raw--profile--canonical-architecture).

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
RelayIdentifier             (Slice 5: which relay is it likely to be?)
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
| `profile.py` | `RelayProfile` protocol, `GenericFallbackProfile`, `RelayProfileRegistry` (also holds identification descriptors; `identify()`) |
| `identification.py` | Slice 5 relay-neutral identifier, result/evidence types, scoring rules, manufacturer aliases |

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
- **Engine capability** (updated with the Reverse Zone enhancement): exactly four
  zone slots in order, each with an explicit direction (forward or reverse);
  one characteristic (mho or quadrilateral) for all zones; phase-phase loops
  only; forward and reverse directional geometry only (non-directional,
  unknown or unresolved directions are still refused); one delay and one shared
  angle per zone; zone ohms compared in the selected impedance basis. A reverse
  zone is the characteristic rotated 180° about the origin; it is unrelated to a
  quadrilateral's reverse *resistive* reach. The canonical model itself still
  allows any number of zones - four is only what the engine evaluates.
- **Supported canonical fields:** zone status (enabled / disabled / inactive),
  forward or reverse direction, phase-phase operation, polar reach (→ mho `reach_ohm` or
  quadrilateral `reactive_reach_ohm`, angle → shared characteristic angle),
  phase-phase (else common) and reverse resistive reach, common (else phase)
  timer, setting basis equal to the engine basis. Disabled/inactive zones
  beyond the fourth are dropped only if disabled.
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

## Slice 3 — ephemeral Import Relay Settings upload

First visible workflow: an **Import Relay Settings** control on the
Distance Protection panel (always shown, both input-source modes). It
uploads one file, the backend validates it and returns basic metadata, and
the raw file is discarded. **Nothing is extracted, identified or
auto-populated**; manual entry is untouched and fully available.

```text
Import Relay Settings -> pick file -> POST /api/v1/relay-import/upload
   -> bounded in-memory read -> minimal inspection -> metadata response
   -> raw bytes dropped, upload handle closed (finally) -> in-tab UI state only
```

- **Endpoint:** `POST /api/v1/relay-import/upload` (multipart field `file`),
  no workspace id (nothing is workspace state). Response:
  `{filename, source_format, size_bytes, status: "accepted"}` -- no
  manufacturer/model/engineering values. Errors use the project's
  `{detail: {code, message}}` shape: `unsupported_file_type` (400),
  `empty_file` (400), `invalid_file` (400, malformed PDF),
  `upload_too_large` (413), `internal_error` (500, generic text).
- **Format:** PDF only. `SUPPORTED_EXTENSIONS` / `_INSPECTORS` in
  `services/relay_import_upload_service.py` are the extension points for
  Excel/CSV/XML/OEM exports. Extension decides the format; the client
  Content-Type is not trusted.
- **Inspection (stdlib only, no new dependency):** `%PDF-` header within the
  first 1024 bytes and `%%EOF` within the last 2048 bytes. No OCR, parsing,
  page count (a page count without a PDF library would be a heuristic that can
  be wrong, so none is reported), external service or LLM.
- **Size limit:** `MAX_RELAY_IMPORT_UPLOAD_SIZE_MB`, default **20 MB**
  (`Settings.max_relay_import_upload_size_mb`). Setting sheets are small
  documents, so the 100 MB recording limit is deliberately not reused; 20 MB
  leaves room for scanned multi-page sheets. Enforced twice: a
  Content-Length fast-path in the existing upload middleware (extended to this
  path with its own limit) and the authoritative bytes-read check
  (`read_bounded`).
- **Raw-file lifecycle:** read into a bounded in-memory `bytes`, inspected,
  dropped on return; the `UploadFile` is closed in a `finally` for success and
  failure. The framework's multipart spool (an OS-managed temp file only past
  ~1 MiB) is closed by Starlette at request end. No code in the upload path
  writes any file, directory, database row, `StorageBackend` object, registry
  entry or cache; the filename is never logged (rejections log the error code
  only). Guarded by tests (temp dir empty after success/failure/oversize;
  storage root and cwd unchanged; no persistence imports in the upload modules).
- **Browser state:** `wwRelayImportState` (idle / uploading / accepted /
  error, filename, format, size, error text) in page memory only -- no
  localStorage, sessionStorage, IndexedDB or cookies. Hard refresh, reopening
  or leaving the page starts clean. **Remove** aborts any in-flight request
  and resets all of it; a late response after Remove/replace is discarded.
  A failed upload never touches the manual form.
- **Privacy wording (accurate to the above):** "Files are processed
  temporarily and are not permanently stored. Import details are kept in this
  browser tab only and are cleared when you refresh or close it."

## Slice 4 — generic PDF text extraction into `RawRelayDocument`

`PDF upload -> generic extractor -> RawRelayDocument (request-scoped) -> counts`.
The relay-neutral extractor (`backend/app/services/relay_pdf_extractor.py`)
fills the Slice 1 `RawRelayDocument` as far as the PDF's text layer safely
supports. **Extracted is not interpreted:** no manufacturer/model is
identified, no parameter is given an engineering meaning, nothing is mapped
into the canonical model and the Distance Protection form is never
auto-populated. Engineering interpretation is still not implemented.

- **Layers kept apart:** `relay_import_upload_service` = file lifecycle and
  validation (and reducing the document to a summary); `relay_pdf_extractor` =
  generic extraction; `RawRelayDocument` = neutral result. Relay
  identification, relay profiles and the canonical model remain later slices.
- **Library: pypdf 6.20.0** (pure Python, BSD, maintained, one pinned
  dependency, no rendering/OCR stack). Layout extraction mode
  (`extract_text(extraction_mode="layout")`) preserves horizontal gaps, which
  is what lets a settings table row be split into cells without guessing.
  *Limitations:* reading order is geometric, so multi-column pages or
  rotated text may interleave; no table-structure recovery beyond column
  gaps; no OCR; pure Python so large documents are slower than MuPDF-class
  libraries (the 31-page sample takes < 1 s). AES-encrypted files need the
  optional `cryptography` package, deliberately **not** added -- they are
  reported as `encrypted`.
- **Statuses** (`PdfExtractionStatus`):
  - `text_extracted` -- text found; `RawRelayDocument` built.
  - `no_extractable_text` -- valid PDF, empty text layer (scanned/image-only).
    No OCR. The extractor also notes pages that contain image XObjects but no
    text (a heuristic, advisory only). Not treated as corrupt.
  - `encrypted` -- `is_encrypted` and an empty password does not open it (or
    the decryption backend is unavailable). A PDF with only an owner password
    and an empty user password is read, with a warning.
  - `unreadable` -- parser failure -> API `400 invalid_file` ("The file is not
    a readable PDF."), same shape as the Slice 3 malformed-file error.
- **How `RawSetting` is populated** (one per non-heading, non-furniture text
  line): `setting_id` `p<page>-e<n>` (deterministic, unique); `name`;
  `parameter_id` (only a leading code-like token: starts with a digit, 3-8
  alphanumeric chars, not a decimal number, followed by text); `raw_value`
  (original text, never altered); `normalized_value` (float, only for a plain
  decimal number without code-like leading zeros, so `0000` stays raw-only);
  `unit` (only a unit symbol from a closed lexical table written directly
  after a number, never converted); `setting_range` (a trailing `a-b` /
  enumeration cell, text kept verbatim); `location` (page + line);
  `source_text` (the original line, trimmed); `notes` (the cells of a
  multi-column row); `extraction` (`generic_pdf_text`, version, and the
  syntactic rule that fired: `row:key_value`, `row:key_value_range`,
  `row:table`, `row:separator`, `row:label`).
- **Rules (all syntactic):** split a line into cells on 2+ spaces/tabs.
  `name  value [range]` -> key/value; `name  v1  v2 ...` -> table row (first
  cell value in `raw_value`, every cell in `notes`, columns are not guessed);
  `name = value` / `name: value` (name starts with a letter) -> separator row;
  otherwise a label-only entry. **Headings** are conservative: a lone line
  that is numbered (`21 Distance protection zones`, dotted numbers nest by
  depth) or a short ALL-CAPS line that is followed by another line. A heading
  sets `section_path` for the entries after it; hierarchy is never invented
  (a `2.1` heading with no `2` is just `("2.1 ...",)`). No heading -> flat.
  Lines repeated at a page's edges on at least half the pages (headers/footers,
  only page counters such as `2/5` are masked) are treated as page furniture:
  kept as `identification_hints`, not entries.
- **Provenance:** every entry keeps page, line, original text, the code/label
  and value text found, and the rule used.
- **Determinism:** same bytes -> equal result (tested on synthetic and real
  documents).
- **Safety:** all parser/decryption exceptions are caught (class name logged
  only, never content or paths); `MAX_PAGES` 400, `MAX_ENTRIES` 50 000 and a
  2 000-char line cap, each reported as a warning; per-page extraction
  failures are isolated; control characters are stripped; pypdf's own
  decompression limits apply. Extraction runs in the thread pool so the event
  loop is not blocked. Bytes are never written anywhere and Slice 3's
  ephemeral guarantees (no storage/DB/browser storage, handle closed in
  `finally`) are unchanged and still tested.
- **API:** `POST /api/v1/relay-import/upload` now also returns
  `extraction_status` (`text_extracted | no_extractable_text | encrypted`),
  `page_count`, `pages_with_text`, `raw_entry_count`, `section_count` and
  `extraction_warnings` (counts and fixed messages only -- no document content,
  so the payload stays small). The full `RawRelayDocument` is built and
  dropped inside the request.
- **UI:** the file card shows `PDF` / `17.2 KB · 4 pages · 126 raw entries`
  with `Text extracted. Relay settings have not been interpreted yet.`, or the
  scanned / encrypted messages. Nothing touches the Distance Protection form.
- **Known limitations:** no OCR; no multi-column reordering; repeated
  identical rows at page edges can be mistaken for page furniture (they are
  retained in `identification_hints`); a code-like leading token heuristic can
  split a row such as `2024 Foo`; ALL-CAPS label-only rows can be taken as
  headings when followed by another line; unit table is lexical, so
  unlisted units stay in `raw_value`.
- **Regression:** the owner's relay sample sheets (kept outside the repo; set
  `RELAY_SAMPLE_PDF_DIR` to run `test_real_sample_regression`) all extract
  as text with page provenance, stable ids and deterministic output; the
  extractor contains no OEM-specific rule (guarded by a test).


## Slice 5 — relay identification framework

`RawRelayDocument -> RelayIdentifier -> RelayIdentification`. Slice 5 answers
*"which relay family/model does this document most likely belong to?"* and
nothing more. **Identified is not interpreted and not validated:** no setting
is read as an engineering value, the canonical model is not populated, the
Distance Protection form is never auto-filled, and no catalogue entry is
`Validated` (that word is reserved for profiles that later pass owner UAT with
real setting files). The catalogue means only *recognisable*.

### Architecture

```text
PDF extractor            generic syntax                  (unchanged)
RawRelayDocument         neutral extracted data          (unchanged)
RelayIdentifier          likely relay / profile          NEW  domain/relay_import/identification.py
RelayProfile             engineering interpretation      later slice
CanonicalDistance...     OEM-neutral engineering model   unchanged
Engine adapter           plotting capability             unchanged
```

| Module | Holds |
|---|---|
| `domain/relay_import/identification.py` | relay-neutral engine: `RelayIdentifier`, `RelayIdentification`, `IdentificationCandidate`, `IdentificationEvidence`, `RelayIdentificationDescriptor`, `ParameterSignature`, `ManufacturerAliases`, `ScoringRules`. Contains **no relay names** (a test and the Slice 1 guard enforce it). |
| `domain/relay_import/profile.py` | `RelayProfileRegistry` now also holds identification descriptors and exposes `identify(document)`. `interpret()` is unchanged. |
| `relay_profiles/identification_catalogue.py` | all relay-specific identification **data**: descriptors and the manufacturer-alias table. Outside the domain package; no engineering mapping, no engine or storage imports. |
| `services/relay_import_upload_service.py` | calls `default_registry().identify(document)` request-scoped and reduces it to a verdict summary. |

The identifier operates on `RawRelayDocument` only -- never on PDF bytes, a
file name or parser internals -- so Excel/CSV/XML/OEM-export readers reuse the
same layer (tested with a CSV-format document). Allowed inputs:
`identification_hints`, each raw entry's name / parameter id / value / range /
notes / source text, and section headings.

**Registry integration.** A descriptor can be registered standalone
(`register_identification_descriptor`) or exposed by a future `RelayProfile`
through an optional `identification` attribute; `identification_descriptors()`
returns both. `identify()` never calls `profile.match()` or
`profile.interpret()` (tested with a profile that raises if called). Duplicate
ids are rejected.

### Descriptors (data-driven, no `if "MODEL" in text`)

`RelayIdentificationDescriptor(profile_id, relay_family, manufacturer, model,
model_patterns, family_markers, parameter_signatures)`:

- `model_patterns` -- regex fragments for the model identifier; matched only as
  a **whole alphanumeric run** (`(?<![A-Za-z0-9])...(?![A-Za-z0-9])`,
  case-insensitive), so a model token never matches inside a longer
  identifier. `_` `-` `?` `.` are separators, which is what lets a scheme
  string such as `NAME_V3.2_1A` match.
- `family_markers` -- brand/family text that is not the model itself.
- `parameter_signatures` -- a distinctive parameter-naming family, searched in
  entry `name` / `parameter_id` / `text`, counted only when at least
  `min_matches` entries show it.
- `manufacturer` -- the **normalised** identity, or `None` where the project
  has not established it. It is never taken from, or guessed out of, the
  document text.

Generic protection vocabulary (Distance Protection, Zone 1, R1, X1, K0, CT,
VT, reach, ...) appears in no descriptor and scores nothing.

### Scoring (deterministic, inspectable, not a probability)

Each descriptor is scored independently by summing evidence points; every kind
is capped so repetition cannot masquerade as proof. Constants are in
`ScoringRules` / `DEFAULT_RULES`.

| Evidence kind | Points | Cap | Meaning |
|---|---|---|---|
| `scheme_model` | 100 | once | model token inside a scheme/template field |
| `labelled_model` | 90 | once | model token inside a model/type/order-code field (`Type`, `Product Code`, `Relay Type`, ...) |
| `model_mention` | 10 | 30 | model token anywhere else (at most 3 places count) |
| `family_marker` | 25 | 25 | family/brand marker |
| `parameter_signature` | 20 | 40 | distinctive parameter-naming family |
| `manufacturer_name` | 10 | 10 | manufacturer or alias named in the text |

Fields are found structurally (an entry named `Type` with value `7SL87`) or
inline (`... Scheme: NAME_V3.2_1A` on a line with other text; the value ends at
a 2+ space gap). A label never creates evidence by itself -- only a catalogued
model token inside its value does.

- **Identified** -- best score `>= 60` (`identify_threshold`) **and** a lead of
  at least `30` (`ambiguity_margin`) over every other candidate; when the best
  candidate has no explicit scheme/model field behind it, the required lead is
  `60` (`indirect_ambiguity_margin`).
- **Ambiguous** -- best `>= 60` but a rival inside the margin. Nothing is
  selected (`profile_id`, `model` are `None`); manufacturer/family are reported
  only if every tied candidate agrees. All tied candidates and their evidence
  are preserved.
- **Unknown** -- best `< 60`, or no evidence. A valid outcome, never an error.
  Weak candidates (score > 0) are kept in `candidates` and a warning names them.
- **Confidence** (categorical): `high` = identified with an explicit
  scheme/model field; `medium` = identified from combined indirect evidence
  only; `low` = ambiguous, or unknown with weak candidates; `none` = no
  evidence. No percentages are shown because none is estimated.

The indirect-margin rule exists because of a real finding: with its scheme line
removed, the RED670 sample quotes `REL670` in six option cells and shares the
Relion 670 parameter naming, so REL670 would outscore RED670 70-40 and be named
with confidence. A 30-point lead is not enough from indirect evidence alone, so
that case is `ambiguous` (guarded by the sample test
`test_removing_the_scheme_line_never_misidentifies`).

### Result

`RelayIdentification`: `status`, `confidence`, `profile_id`, `manufacturer`
(normalised), `manufacturer_source_name` (spelling found in the document, if
any), `relay_family`, `model`, `version` + `version_source`, `scheme_name`,
`score`, `evidence` (of the selected candidate: kind, points, matched text,
explanation, setting id, page), `candidates` (all with score > 0, ranked by
`(-score, profile_id)`), `alternatives`, `warnings`.

- **Version** is reported only when explicit: a `V<n>` / `Ver<n>` marker inside
  the scheme name, or a labelled firmware / software-version field (a labelled
  field wins). `7SL87_8.81` therefore reports no version.
- **Scheme name** is document metadata and is reported for every status.

### Manufacturer aliases / normalisation

`ManufacturerAliases` maps a canonical name to the names it has been published
under; the canonical name is exposed, the source spelling is kept beside it,
and the document text is never rewritten. Current table
(`MANUFACTURER_ALIASES`): Schneider Electric (Schneider, Areva T&D, Areva,
Alstom Grid, Alstom), Hitachi Energy (Hitachi ABB Power Grids, ABB Power Grids,
ABB, Asea Brown Boveri), Siemens, Toshiba, NR Electric (NARI). Alias matching
uses the same whole-run rule, so a station code such as `ABBA` is not the
manufacturer `ABB` (tested against the real P441 sheet). A named manufacturer is
weak evidence (10); the reported manufacturer always comes from the matched
descriptor.

### Identification catalogue (identification only)

| Profile id | Normalised manufacturer | Family | Model |
|---|---|---|---|
| `schneider-micom-p441` | Schneider Electric | MiCOM P44x | P441 |
| `siemens-7sa511` | Siemens | SIPROTEC 7SA5 | 7SA511 |
| `siemens-7sa613` | Siemens | SIPROTEC 4 7SA6 | 7SA613 |
| `siemens-siprotec5-7sl87` | Siemens | SIPROTEC 5 | 7SL87 |
| `toshiba-grl200` | Toshiba | GR200 | GRL200 |
| `toshiba-grz100` | Toshiba | GRZ100 | GRZ100 |
| `nr-rcs941` | NR Electric | RCS-9xx | RCS-941 |
| `hitachi-red670` | Hitachi Energy (formerly ABB) | Relion 670 | RED670 |
| `hitachi-rel670` | Hitachi Energy (formerly ABB) | Relion 670 | REL670 |
| `hitachi-rel511` | Hitachi Energy (formerly ABB) | REx5xx | REL511 |
| `lfzp111` | *(not asserted)* | LFZP | LFZP111 |
| `relz100` | *(not asserted)* | RELZ 100 | RELZ100 |

The manufacturer of the two older lines is left unset on purpose: it is not
recorded in the project and identification must not guess. Family names are
informal display labels, not an OEM-published taxonomy -- confirm them before
they are relied on. A relay not in the catalogue (including a sibling model of
a catalogued family) is `unknown`.

### Unknown relays and the raw document

Unknown never fails an upload and never discards data: the `RawRelayDocument`
is untouched (immutable), `registry.interpret()` still returns the generic
fallback with every raw setting retained as unmapped, and the user continues
with manual entry.

### API and UI

`POST /api/v1/relay-import/upload` additionally returns `identification_status`
(`identified | ambiguous | unknown`, `null` when no text could be read),
`manufacturer`, `relay_family`, `model`, `profile_id`, `confidence`
(`high | medium | low | none`) and `identification_warnings` (fixed phrases and
profile ids only). Evidence, scores, candidates and document text are **not**
returned. The upload card shows, between file name and status,
`Siemens · 7SA613` with `Relay identified. Settings have not been interpreted yet.`;
unknown shows `Relay model not recognised. You can continue with manual entry.`;
ambiguous shows `Relay identification needs confirmation.` (and the
manufacturer only if all tied candidates agree). No candidate-selection UI, no
auto-population.

### Limits and assumptions

- The owner's sample sheets all carry a `Scheme:` field in the project's
  setting-sheet header; that field is the strongest evidence, and the label
  vocabulary is configurable (`ScoringRules.scheme_labels` / `model_labels`).
  Without it most sheets fall to `unknown` / `ambiguous` -- the intended
  conservative behaviour.
- Family-marker and parameter-signature patterns were derived from the sample
  sheets and public naming conventions; they add only moderate evidence and are
  exercised by tests that remove the scheme line and thin/reorder entries.
- Sheets of a catalogued family with a different template may need extra
  signatures; add them to the catalogue, not to the identifier.
- Scanned or encrypted documents have no text to identify (status `null`).

## Slice 6 — MiCOM P441 engineering interpretation (`micom-p441-v1`)

Status: **Implemented / Awaiting Validation.** It becomes `Validated` only after
owner UAT against the real P441 setting file; until then no UI, API field or
document calls it validated. **Interpreted is not applied:** nothing is written
to the Distance Protection form, there is no Apply button, no Extraction Review
UI, no persistence, no plotting from imported settings and no AI/LLM step.

```text
RawRelayDocument -> RelayIdentifier -> (identified P441 only) MicomP441Profile
     -> CanonicalDistanceProtectionModel -> existing adapt_to_engine() (read-only check)
     -> interpretation SUMMARY in the upload response
```

| Module | Holds |
|---|---|
| `relay_profiles/micom_p441.py` | **all P441 knowledge**: parameter codes and expected names, unit/basis rules, shared Zone 3/4 settings, scheme-note wording; `MicomP441Profile` (`profile_id` `schneider-micom-p441`, `version` `micom-p441-v1`) |
| `relay_profiles/identification_catalogue.py` | registers the profile beside the identification descriptors (the only registered profile) |
| `domain/relay_import/profile.py` | `RelayProfileRegistry.profile_for(identification)`: a profile is returned only for an `identified` verdict whose `profile_id` matches exactly; ambiguous / unknown / any other family returns `None` |
| `services/relay_interpretation_summary.py` | runs the profile, counts, runs the engine adapter as a read-only check, reduces to counts + fixed phrases; a profile exception becomes `failed`, never a 500 |

Generic domain changes (relay-neutral): `UnresolvedSetting.out_of_scope`,
`RelayMetadata.scheme_name`, `CanonicalDistanceProtectionModel.referenced_setting_ids()`.
The generic extractor, the identifier, the canonical model, the adapter and the
distance engine contain no P441 name (a test scans the whole `app/` tree: only
`micom_p441.py` and the catalogue may mention it).

### How a setting is read

A setting is trusted only when its parameter **code and name** both match this
version's table (a known code under another name is unresolved). Then:

* **duplicates** — identical duplicates map with a note; conflicting duplicates
  are unresolved and cite every entry (nothing chosen);
* **numbers** — plain decimals only (`1,43`, `1e3`, `NaN`, `1.43 ohm` are
  unresolved, raw text kept) and inside the printed range;
* **units** — taken from the printed range/unit cell, never assumed, never
  scaled: `A`, `V` (so `kV` is unresolved, no x1000), `s` (so `ms` is
  unresolved), `deg`, dimensionless factors; impedances are secondary ohms only
  for the printed `/I1` marker **with a 1 A CT secondary** (or an explicit
  ohm unit);
* **missing** — unresolved with a note; never defaulted.

Statuses: **mapped** = stated by the sheet; **inferred** = rests on P441 family
knowledge the sheet does not repeat (each carries a note saying why, and is
counted as "to confirm"); **unresolved** = kept raw, no engineering value.

### Exact semantics (v1)

| Canonical | Source | Status |
|---|---|---|
| model, scheme name | `Scheme:` field (`SE_P441?A1???038?JE`) | mapped; source wording kept in `raw_value` |
| manufacturer, family | normalised from the catalogue (the sheet does not name them) | mapped, with a note |
| firmware version | only a free-text `Minor Ver.` marker exists | **unresolved**, marker kept raw |
| active setting group | `0903 Active Settings` | mapped |
| CT primary/secondary, VT primary/secondary | `0A07`, `0A08`, `0A01`, `0A02` | mapped |
| setting basis | `092E Setting Values` (Secondary / Primary) | mapped; the `Measure't Setup` display selections are **not** the settings basis |
| voltage / current base | not a P441 setting | unresolved (nothing invented) |
| line length + unit | `3002` with `0D07 Distance Unit` (km / mile, not converted) | mapped (unit unresolved without `0D07`) |
| line angle | `3005` | mapped |
| line impedance magnitude | `3004`, kept as an extra, **not** combined with the angle | mapped; positive-sequence impedance left unresolved (the sheet names no sequence) |
| zone reach | `Z1/Z2/Z3/Z4/Zp` as polar magnitude at the **line angle** | inferred (angle per zone is not restated) |
| resistive reach | `R<n>Ph` -> phase-phase, `R<n>G` -> phase-earth, always separate | mapped; `common` and **reverse** stay unresolved |
| zone delay | `tZ1/tZ2/tZ3/tZ4/tZp` -> common timer | mapped |
| characteristic | quadrilateral (P441 family; sheet does not name it) | inferred |
| PP / PE loop enable | `3103 Fault Type = Both Enabled` | inferred |
| residual compensation | `kZn Res Comp` + `kZn Angle` as a K0-style magnitude/angle pair, **never converted** | inferred |
| Zones 1-3 status | `090D Dist. Protection = Enabled` + the zone's own settings | inferred |
| Zones 2-3 direction | scheme notes "Zone 2/3 Forward direction..." | mapped |
| Zone 1 direction, Zone 4 direction (reverse) | P441 family design (Zone 4 also agrees with the `DIST REV OP` output label) | inferred |
| Zone P direction | `301D ZoneP - Direct` | mapped |
| Zone 1 extension reach | `300B Z1X`, kept as a Zone 1 parameter (not a zone) | mapped |
| Zone 3/4 shared settings | `kZ3/4`, `R3G-R4G`, `R3Ph-R4Ph` cited by **both** zones | as above |

Zones found on the sample: **Z1, Z2, Z3, Z4, ZP** (5). The canonical model is
not limited to four.

### Zone 4 / defeated logic

Zone 4 carries real numbers (`Z4 0.36`, `tZ4 3`, shared resistive reaches) but
the sheet's scheme notes say **"Zone 4 Defeated"** (and "To defeat Zone 4 ...",
and a `3007 Zone Status 11010 -> 01010` revision). The profile reports
`status = disabled` (inferred, citing the statements and `3007`) and **keeps
every number**. No statement -> status **unresolved** (never "enabled by
default"); contradictory statements -> unresolved with a note; negated or
look-alike wording ("Not Defeated", "Zone 40 Defeated") does not defeat the
zone; `Dist. Protection = Disabled` disables every zone.

### Deliberately not decoded

* **`3007 Zone Status`** is a bit string (`01010`). Its bit-to-zone layout is not
  stated by the sheet and is **not decoded** in v1, so it never decides a zone's
  state; the raw string is preserved. Consequently **Zone P's in-service state
  is unresolved**.
* **Tilt angles** (`3026`-`3028`) apply per fault-loop type / zone group and are
  kept raw in the zones' `unresolved_settings`; no single `tilt_deg` is claimed.
* **Left-hand (reverse) resistive reach** — the sheet states none, so none is
  invented (see the adapter result below).
* Scheme logic, power swing, SOTF, unblocking, etc. are retained raw as
  distance-related "not interpreted" settings; non-distance settings (recorders,
  comms, labels, opto/relay mapping) are retained raw and flagged `out_of_scope`.
  Every raw setting is either cited by a value or carried as an
  `UnresolvedSetting` (tested on the sample: none is discarded).

### Engine-adapter result (read-only check, nothing changed)

On the owner sample `adapt_to_engine()` reports **unsupported**, for two reasons
the sheet cannot answer: (1) **Zone P** has no established in-service state, so
it is treated as a possible fifth zone; (2) the quadrilateral needs a
**reverse resistive reach** and the sheet states none. The engine and adapter
were deliberately not changed. Phase-earth operation and residual compensation
are warned as preserved-but-unused. When a reverse reach and Zone P's state are
supplied, the model reaches the engine with the **phase-phase** resistive reach
(2.11 Ω for Zone 1, not the phase-earth 7.02 Ω), reach 1.43 Ω at 80° and delay 0 s
(tested).

### API and UI

`POST /api/v1/relay-import/upload` adds `interpretation_status`
(`interpreted | incomplete | not_supported | failed`, `null` when no text),
`profile_version`, `mapped_setting_count`, `inferred_setting_count`,
`unresolved_setting_count`, `not_interpreted_setting_count`, `zone_count`,
`interpretation_warnings`. Counts are canonical values (not raw lines); an
untouched placeholder for something the relay does not have is not counted as
unresolved. Warnings are fixed phrases (profile notes and `Engine: ...` adapter
reasons) with **no document values** (tested). The upload card shows, for an
interpreted P441, `Schneider Electric · P441`, "Relay identified and settings
interpreted. Review is required before applying. Nothing has been applied to the
form." and e.g. `5 zones found · 33 settings mapped · 36 to confirm · 6 unresolved`.
Every other identified family keeps "Relay identified. Settings have not been
interpreted yet." and `interpretation_status = not_supported`.

### Limits and open points

See the Slice 6 report in [HANDOFF.md](HANDOFF.md): the `3007` bit layout, the
P441 left-hand resistive reach rule, whether `R<n>Ph` is a loop or per-phase
value, and the K0-style reading of `kZn` all need confirmation against the P44x
technical manual or the owner before Slice 7 (Extraction Review / Apply).

## Slice 7 — Extraction Review (read-only)

Status: **Implemented / Awaiting owner UAT.** Pipeline:
`Upload -> Extract -> Identify -> Interpret -> Review`. The slice stops at
**Review**: there is no Apply, Accept, Populate, Generate Characteristic or
auto-fill, no owner editing and no per-mapping accept/reject. The manual
Distance Protection form is neither read nor written by the review.

```text
CanonicalDistanceProtectionModel + RawRelayDocument + EngineAdaptation
        -> build_extraction_review()   services/relay_extraction_review.py
        -> ExtractionReview (dataclasses) -> ExtractionReviewOut (Pydantic)
        -> upload response `review` field -> tab memory -> Review panel
```

| Piece | Where |
|---|---|
| review builder (relay-neutral; walks the canonical model; a test forbids relay names) | `services/relay_extraction_review.py` |
| wiring: built once beside the summary, only for an `interpreted` relay; a builder failure leaves `review = null` (logged by class only) and never fails the upload | `services/relay_interpretation_summary.py` (`RelayInterpretationSummary.review`, `engine_adaptation()`) |
| stable API schema (`ExtractionReviewOut` and friends; internal dataclasses are not exposed) | `schemas/relay_import.py` |
| UI | `frontend/index.html` -- `#wwRelayReviewBtn`, `#wwRelayReviewPanel`, `wwRelayReviewRender()` |

**Delivery, and why it is not a second endpoint.** The platform deliberately
keeps nothing between requests (Slice 3). A "fetch review by id" endpoint would
need server-side state, which is forbidden. The review therefore rides in the
`POST /api/v1/relay-import/upload` response as a nested `review` object
(`null` unless the relay was interpreted) and lives only in
`wwRelayImportState.review`. The existing summary fields are unchanged and are
still counts and fixed phrases; **engineering values appear only inside
`review`**. A hard refresh, Remove or a new upload drops it. The payload for the
P441 sample is about 40 KB.

**Review DTO.** `relay identity + profile id/version + zone_count + counts +
interpretation quality + engine compatibility + notes + groups[] +
not_interpreted[] + out_of_scope[]`. Groups, in order: Relay / source
information, CT / VT, Protected line, **one group per zone** (generated from
`model.zones`; titles come from the zone, the count is whatever the profile
produced), Residual compensation (per zone, shown for the compensation kind the
model carries). Each item: `key`, short `label`, `full_label` (e.g. "Zone 1
Earth Resistive Reach", used in the provenance heading), formatted `value_text`
with unit (`null` when unresolved), `status` (mapped / inferred / unresolved),
the profile's `notes`, `raw_value`, profile id/version and `sources[]`.
A source is `code`, `name`, `raw_value`, `page`, `line`, `source_text`, resolved
from the raw document by `setting_id`; no file path or file name is ever in it.

**Presentation rules (no new engineering meaning).**

* A reach is shown as two rows, the magnitude and its angle, sharing one
  provenance (rectangular R/X likewise). Counts are of canonical settings, so
  the review says they are not display rows.
* Required items are always listed even when unresolved (zone status,
  direction, characteristic, reach, phase-phase / earth / **reverse** resistive
  reach for a quadrilateral, a delay, firmware version, voltage and current
  base, positive-sequence impedance). A placeholder for something the relay
  simply does not have (earth reach, zero-sequence reach, an unused timer, tilt,
  common resistive reach) is hidden unless the profile touched it. An unresolved
  item the profile left no reason for reads "No value is stated in the document."
* Zone-level raw settings the profile declined (the P441 tilt angles) appear in
  that zone as unresolved items with the profile's reason.
* Inferred items show the profile's reason as "Assumption"; unresolved items as
  "Why unresolved". Inferred values are never styled as deterministic.
* Zone 4 reads "Zone 4 — Disabled / Defeated" and keeps its reach, resistive
  reach and delay; Zone P reads "Zone P — Status unresolved" with its numbers.

**Engine compatibility is separate from interpretation quality.** The review
carries `interpretation` (`reviewable` / `incomplete`) and `engine`
(`ready` / `not_ready`, the existing adapter's reasons with identical messages
merged across zones, and its preserved-but-unused warnings). For the P441 sample
the panel states "Interpretation: Complete enough for review" and "Current
engine compatibility: Not ready to apply", with "Interpretation succeeded, but
the current Distance Protection engine cannot fully apply this scheme yet."
and the adapter's reasons (Zone P cannot be represented; the reverse resistive
reach is unresolved). These are review notes, never upload errors. The adapter
and engine were not changed; the basis logic was only extracted into
`engine_adaptation()` so the summary and the review share one run.

**Other extracted settings.** A collapsed section, secondary to the canonical
review: distance-related settings the profile retained but did not interpret,
and settings outside Distance Protection. Each row shows code / name, raw value
and page / line; lists show 25 rows and grow by "Show more", so the initial view
never dumps the ~300 retained lines.

**UI.** A "Review Extracted Settings" button on the relay-import card, visible
only for `interpretation_status = interpreted` with a review payload (never for
an identified-but-unsupported relay such as 7SA511). It opens a contained panel
(max 70vh, internal scroll, sticky header) inside the relay-import card:
summary, compatibility, collapsible `<details>` groups, and rows
`label | value | status chip | Source`. "Source" is an accessible disclosure
(`aria-expanded` / `aria-controls`) that expands the provenance in place: code ·
name, page · line, raw value, source text, profile version and the note. Status
styling is restrained: Mapped a quiet dot, To confirm amber, Unresolved red text
on a dashed chip; shared theme tokens only, so light and dark both work; no
animation. All document text is inserted with `textContent` (no `innerHTML`).
Electrical V/I notation is not displayed here, so the formatter is not needed.

**Ephemeral lifecycle (unchanged policy).** No database table, no saved import,
no server session, no browser storage, no filesystem write. The review object is
built inside the request and dropped; the browser holds it only in the page's
memory. A static test and a browser test guard this.

**Out of scope (unchanged for Slice 9+).** Apply Settings, form population,
(editing and confirming individual values is Slice 8, below) P44x-manual-based fixes for Zone P /
reverse reach, further profiles, persistence/history, OCR, AI/LLM.

## Slice 8 — Review Confirmation / Resolution (still no Apply)

Status: **Implemented / Awaiting owner UAT.** Pipeline:
`Upload -> Extract -> Identify -> Interpret -> Review -> Confirm / Resolve`. The
slice stops **before Apply**: there is no Apply / Populate / Generate control, the
Distance Protection form is neither read nor written, and no plotted
characteristic changes. It ends when the review can say **Ready to apply**.

```text
original interpretation (immutable)  +  ReviewDecisions (session overlay)
      -> apply_review()                domain/relay_import/review_state.py
      -> effective reviewed model
      -> engine adapter, re-run        (read-only; paths added to its reasons)
      -> build_extraction_review()     counts, blocking, readiness
```

### Semantics

* **Confirm** means "I accept this interpreted value for this import session". It
  does **not** validate the profile, trust a mapping rule, affect future imports
  or apply anything. The effective value keeps its value, profile provenance and
  its `inferred` status; a `ReviewRecord(status=confirmed, original_status=inferred)`
  is added beside them. `interpretation status` and `review status` are separate
  (`ReviewItem.status` vs `ReviewItem.review_status`). `Sourced.needs_confirmation`
  is false once confirmed.
* **Mapped** values are read-only and never ask for confirmation.
* **Unresolved** values have three states: untouched, *resolved manually* or
  *left unresolved*. Nothing is ever turned into zero or a default; a blank is not
  a value, an explicit `0` is.
* **Manual resolution** only where the canonical target and type are clear
  (`review_state.resolution_spec`, a path-pattern table): zone `status`
  (enabled/disabled), zone `direction`, `resistive_reach.{common,phase_phase,
  phase_earth,reverse}` (Ω, 0..1e5) and the zone timers (s, 0..1e4). Compound
  reaches, base values, firmware, raw OEM settings stay unresolved. The effective
  value keeps the original unresolved provenance (sources, raw text, notes) and a
  `ReviewRecord(status=resolved_manually, original_status=unresolved,
  user_value_text="2.5 Ω")`, with `MappingStatus.RESOLVED_MANUALLY` and
  `ProvenanceOrigin.SESSION_REVIEW`. The UI shows `Source value: unavailable /
  unresolved` apart from `User resolution: 2.5 Ω`. No timestamp is recorded: the
  state is session-only and the domain is deterministic.
* **No silent substitution.** Every resolved value comes from a profile mapping,
  an explicit confirmation or an explicit manual entry -- never a form, zone or
  engine default (tested).

### Blocking issues and readiness

`UnsupportedReason` gained `paths` (canonical value paths whose resolution would
address it). An **unresolved item is blocking** iff its path is in some current
adapter reason's `paths`; otherwise it is *unresolved, non-blocking*. A
**blocking issue** is an adapter reason (identical messages merged across zones);
it can outlive every value that caused it (Zone P resolved to *enabled* still
cannot be represented: "a limit of the current engine"). Readiness
(`review_state.compute_readiness`):

| Result | Rule |
|---|---|
| `Not ready` | the adapter rejects the effective model, or a blocking item is open |
| `Ready after confirmation` | adapter accepts, but inferred values remain unconfirmed |
| `Ready to apply` | adapter accepts and every inferred value is confirmed |

"Required canonical fields" means those the adapter needs, so an unresolved one
always makes the adapter refuse. Other unresolved values (firmware version,
voltage/current base, ...) do not block.

### Counting convention

Counts are per **canonical value the review lists** (a reach and its angle are one
value; `ReviewItem.primary` marks the first row), plus zone settings the profile
declined (always unresolved, never resolvable). `mapped` (untouched), `to confirm`
(inferred, pending), `confirmed`, `resolved manually`, `unresolved` (blocking or
not, incl. left unresolved), `blocking` (a subset of unresolved). This differs from
the Slice 6 upload-response counts (`count_model`), which are profile-level and do
not list required placeholders; blocking items must be a subset of the unresolved,
so the review and the card line use the review counts. The Slice 6 response fields
are unchanged.

### Stateless validation API

`POST /api/v1/relay-import/review/validate` (versioned, no session, no store).
Input: `validation_context` + `confirmed` ids + `manual` `{item_id, value}` +
`left_unresolved` ids. Output `ReviewStateOut`: per canonical value `{item_id,
status, review_status, value_text, blocking, left_unresolved, user_value_text}`,
counts, `blocking_issues`, `engine`, `readiness`. Errors: `400 invalid_review`
(fixed domain phrases only). The **validation context** is the original canonical
model as JSON (`domain/relay_import/canonical_codec.py`, ~64 KB for the P441
sample, document-level unmapped settings omitted), returned inside the upload
`review` and held in tab memory. The decoder builds only registered canonical
dataclasses/enums through their own constructors, so every domain invariant is
re-checked. It is **not authenticated** (the user's own session data): Slice 9
must re-derive or re-verify before acting on it. Item ids are canonical paths
(`zones[Z1].resistive_reach.reverse`) -- relay-neutral, no P441 logic.

### UI

Same panel, no modal. `To confirm` rows get **Confirm**; confirmed rows show
**Confirmed** and **Undo confirmation**; unresolved rows with a known type get
**Resolve** (inline number input or choice, **Set value** / **Leave unresolved** /
**Cancel**); resolved rows get **Edit** / **Clear**. Bulk: **Confirm all inferred
values (N)** (exact count; only `To confirm` rows; unresolved and mapped
untouched) and **Undo all confirmations**. A readiness box and a *Blocking issues*
list (what each needs, or that no value can clear it) sit above the groups. The
panel updates in place (scroll, open groups and open sources are kept); a refused
decision is rolled back with the backend's message. The card summary line shows
the live counts.

### Ephemeral lifecycle

Decisions (`wwRelayImportState.decisions`, `reviewLive`) live in page memory only:
cleared by Remove, a new upload and a refresh; never in localStorage,
sessionStorage, IndexedDB, cookies, the server, database or filesystem.

### Out of scope (unchanged)

Apply Settings, form population, plotting from imports, persistent decisions,
learning from confirmations, profile mutation, further profiles, decoding P441
`3007`, deriving a reverse reach, OCR, AI/LLM.

### P441 sample before / after

Before: 4 blocking items (Z1-Z3 reverse resistive reach, Zone P status), not
ready. Confirming everything alone stays *Not ready*. Reverse reach for Z1-Z3 +
Zone P *disabled* -> *Ready after confirmation*; plus confirming all -> *Ready to
apply*. Zone P *enabled* -> still *Not ready* (fifth zone); Zone P is never
removed from the model.

## Slice 8A — review uncertainty taxonomy

Status: **Implemented / Awaiting owner UAT** (with Slice 8). Presentation and
classification only: no engineering value, mapping rule, engine or readiness rule
changed. This section supersedes the visible "To confirm" / "Unresolved" wording
used in the Slice 6-8 text above (those names survive only as internal fields).

The user may not be a protection engineer, so the review explains *why* a value is
uncertain instead of asking everything to be confirmed. Six compact categories
(`ReviewItem.category`):

| Category | Meaning | User action |
|---|---|---|
| **Mapped** | read, and the mapping is deterministic | none (read-only) |
| **Assumption** | the source value **was read**, but Oruxa made an engineering assumption to interpret it (direction from family convention, characteristic from the setting family, reach angle = line angle) | expert may Confirm / Undo; bulk "Confirm all assumptions (N)" |
| **Missing** | a value the workflow needs is not in the source | manual value only where the canonical type/unit is known |
| **Conflict** | source values/statements disagree, or contradict the printed range/unit; none is chosen | none (the competing choices are not offered) |
| **Unsupported** | Oruxa understands it, but the current engine/model cannot represent or use it (Zone P as a fifth zone, a lenticular characteristic, a per-loop tilt) | none -- a limit of the software, never confirmed away |
| **Unreadable** | the text could not be read reliably (empty cell, not a plain number) | clearer source, or manual value where offered |

Not every uncertainty is a question for the user; only an Assumption is confirmable.

**Three facts stay separate** and the category is derived from them, never stored:
(1) *interpretation status* -- `MappingStatus` mapped / inferred / unresolved,
unchanged (`inferred` is presented as Assumption); (2) *source / extraction cause*
of an unresolved value -- new `Provenance.cause` (`UnresolvedCause`: missing /
conflict / unreadable / unsupported; unset means Missing), set by the profile where
it knows why (P441: absent code → missing; duplicates, wrong name, outside range,
wrong unit → conflict; empty or non-numeric cell → unreadable; unrecognised choice
→ unsupported); (3) *engine capability* -- `review_state.engine_limits()` reads the
adapter's reasons: a **resolved** value named by a capability reason is Unsupported,
by a conflict reason is Conflict (`ReviewItem.engine_reason` carries the message).
Zone settings the profile keeps raw (P441 tilts) are Unsupported. A confirmation or
manual resolution never rewrites the category (a confirmed assumption is still an
Assumption; the Source shows "Classified as" and "Originally an assumption because"),
except that an engine limit always shows as Unsupported/Conflict.

**Enforcement.** The UI offers Confirm only for Assumption rows and the bulk action
selects only those; the validate endpoint also refuses (`400 invalid_review`) a
confirmation of a value that is currently Unsupported or Conflict.

**Counts.** Review fields `assumption_count`, `missing_count`, `conflict_count`,
`unsupported_count`, `unreadable_count` (legacy `to_confirm_count` /
`unresolved_count` remain, readiness still uses them). Card line:
`5 zones found · 32 settings mapped · 36 assumptions · 10 missing · 4 unsupported · 4 blocking settings`
(zero parts dropped; Conflict/Unreadable only appear when present). **Blocking
settings** (`blocking_count`: values the engine needs and that are still open) and
**blocking reasons** (`blocking_issues`: the adapter's messages) are different
numbers and are worded apart.

**P441 sample (fixture):** 32 mapped; 36 Assumption (zone status 1-4, direction of
Z1/Z4, characteristic, reach angle, PP/PE fault type, residual compensation);
10 Missing (reverse resistive reach ×5, Zone P state, firmware version, voltage and
current base, positive-sequence impedance); 4 Unsupported (tilt settings kept raw);
no Conflict/Unreadable. Zone P's state is *Missing* while unknown (disabling it is a
valid answer) and becomes *Unsupported* if the user says it is enabled. Readiness is
identical to Slice 8 (4 blocking settings, 2 reasons). Open judgement: tilt settings
are classed Unsupported because neither the canonical model nor the engine has a
per-loop tilt; the owner may prefer another label.

## Intentionally unresolved in Slice 1

- ~~Mapping onto the existing `ZoneSettings`~~ — done in Slice 2 (above).
- Geometry for lenticular, polygon and unknown characteristics, and
  per-loop (phase-earth) evaluation — need engine work and owner decisions.
- Setting-basis (primary/secondary) handling when the source does not say.
- Whether active setting groups need a multi-group model (currently one
  active group name).
- ~~Extraction technology, upload API shape~~ -- decided in Slices 3-4 (above).
- ~~Relay identification heuristics~~ -- Slice 5 (above). Still open: OCR for scanned
  sheets; a confirmation UI for ambiguous documents.
- ~~First engineering profile~~ -- Slice 6 (P441, above), awaiting owner UAT before it
  may be called `Validated`. ~~Extraction Review~~ -- Slice 7 (above), read-only,
  awaiting owner UAT. Still open: profiles for every other family; the Apply
  workflow (Slice 9, after Slice 8 UAT).
