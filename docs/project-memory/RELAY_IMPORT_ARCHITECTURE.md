# Relay Settings Import — Architecture (Slice 1: foundation)

Status: **Slices 1-8 + 8A (review status taxonomy, below)** (domain contracts, manual entry + engine adapter,
ephemeral upload, generic PDF extraction, relay identification, MiCOM P441
interpretation profile, read-only Extraction Review, review confirmation / resolution) implemented
and **integrated into `main`** (2026-10-11) on top of the completed Oscillation Analysis Phase 1
baseline. Slice 6 is **Implemented / Awaiting
Validation**; Slices 7 and 8 are **Implemented / Awaiting owner UAT**. Every other relay
is identification-only; **Slice 9 (Apply Settings, DEC-188), Slice 10 (Dynamic Distance Zones, DEC-189) and Slice 11 (Siemens 7SA511 profile, DEC-196/191) are implemented; the 7SA511 profile is PAUSED pending verified source data (DEC-192). Slice 12 (Hitachi Energy RED670 profile, DEC-192) is implemented and awaiting owner UAT**. Approval record:
**2026-10-13: the RED670 semantics are corrected (DEC-193) and a data-driven Parameter Catalog Foundation is added (DEC-194; last section).**
**2026-10-14: every remaining sample relay family is interpreted by a catalog-only JSON parameter catalog (DEC-197, branch `feature/remaining-relay-imports`; section "Remaining relay families", with the consolidated owner-UAT matrix).**
**2026-10-15: Relay Import Assistance for Non-Expert Users -- generic foundation (DEC-198; last section): catalog references and verified documented derivations, "Documented relay behaviour", Unverified vs Unsupported, Not exposed, the approximation data model, `ready_approximate`, Apply `approximations[]`. Then REL511 knowledge integration (DEC-198 Amendment 1, catalog 1.1.0): REL511 artificial characteristic/loop blockers resolved through documented relay behaviour; REL511 still blocked by genuine unresolved engineering semantics. Then REL511 semantic integration (DEC-198 Amendment 2, catalog 1.2.0): basis (Secondary) and RFZn / RFNZn meanings verified from the ABB REL 511 2.3 / 2.5 manuals; the only semantic unknown left is ZnBlock; the RFZn inclined boundary and the left / directional boundary are known engine limitations; still NOT_READY.**
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
- **Engine capability** (updated with the Reverse Zone enhancement and again by Slice 10, DEC-189): any number of
  zones, each with a stable key and an explicit direction (forward or reverse);
  one characteristic (mho or quadrilateral) for all zones; phase-phase loops
  only; forward and reverse directional geometry only (non-directional,
  unknown or unresolved directions are still refused); one delay and one shared
  angle per zone; zone ohms compared in the selected impedance basis. A reverse
  zone is the characteristic rotated 180° about the origin; it is unrelated to a
  quadrilateral's reverse *resistive* reach. The canonical model allows any number of zones and, since
  Slice 10, so does the engine: zone count is not a capability limit.
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
  Since Slice 9, Remove also releases the Distance Protection settings the
  import applied (see "Slice 9", *Remove after Apply*).
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
must re-derive or re-verify before acting on it. *(Superseded by DEC-198 Amendment 5 -- see "Signed validation
token" below: the snapshot now travels only inside a signed, opaque `validation_token` bound to an `import_id`;
the request takes those two fields and refuses a raw `validation_context`.)* Item ids are canonical paths
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
**DEC-198 (2026-10-15)** in turn renames the visible "Missing" chip "Source value missing" and "Unsupported" "Not yet
supported", and adds Documented relay behaviour / Approximate plot / Not a relay setting (and the internal category
`unverified`) -- see the last section; the internal category names below are unchanged.

The user may not be a protection engineer, so the review explains *why* a value is
uncertain instead of asking everything to be confirmed. Six compact categories
(`ReviewItem.category`):

| Category | Meaning | User action |
|---|---|---|
| **Mapped** | read, and the mapping is deterministic | none (read-only) |
| **Assumption** | the source value **was read**, but an engineering assumption was made to interpret it (direction from family convention, characteristic from the setting family, reach angle = line angle) | expert may Confirm / Undo; bulk "Confirm all assumptions (N)" |
| **Missing** | a value the workflow needs is not in the source | manual value only where the canonical type/unit is known |
| **Conflict** | source values/statements disagree, or contradict the printed range/unit; none is chosen | none (the competing choices are not offered) |
| **Unsupported** | the software understands it, but the current engine/model cannot represent or use it (Zone P as a fifth zone, a lenticular characteristic, a per-loop tilt) | none -- a limit of the software, never confirmed away |
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

## Review UX fix -- Left Resistive Reach (−R) and the explicit 0.00 Ω suggestion (DEC-185)

Status: **Implemented / Awaiting owner UAT** (2026-10-12). Review-stage only; Slice 9 has
not started and nothing is applied.

* **Labels.** `resistive_reach.reverse` is shown as **Left Resistive Reach (−R)** (review
  row, adapter message "The Left Resistive Reach (−R) is unresolved.", profile note). Canonical
  and API names are unchanged.
* **Suggestion** (`review_state.SuggestionSpec`, table `_SUGGESTIONS`, one entry:
  `zones[*].resistive_reach.reverse` → 0 Ω, text "0.00 Ω"). `ReviewItem.suggestion` is set only
  while the item is unresolved with category **Missing**; it is never part of the effective
  model until the user accepts it.
* **Decision.** `ReviewDecisions.suggested` (API `suggested[]`) → `apply_review` writes the
  value with `MappingStatus.RESOLVED_MANUALLY`, origin `SESSION_REVIEW` and
  `ReviewRecord(SUGGESTION_ACCEPTED, original_status=unresolved, user_value_text="0.00 Ω")`;
  source references, raw text, notes and `cause` (Missing) are kept. Refused (400
  `invalid_review`) for any other path, a resolved value, a non-Missing cause, or an item that
  also has a manual/confirm/leave decision.
* **Output.** `ReviewItem(State)Out.resolution_origin` = `manual` | `suggestion` | null;
  `review_status` stays `resolved_manually` (counts unchanged), `category` stays `missing`.
* **UI.** Missing row: "This value was not found in the relay setting file. Suggested for
  visualization: 0.00 Ω. …" with **Use 0.00 Ω** and **Enter manually** (the existing Resolve
  editor; its aria-label stays "Resolve …"). Accepted: chip **Resolved · Suggested**, Source
  shows "Suggested value: 0.00 Ω — accepted by you …" and "Not the relay's setting,
  and not mapped from a profile"; **Edit** / **Clear** restore manual entry / Missing.
* **Tests.** `backend/tests/test_relay_review_suggestion.py`;
  `browser-tests/distance_resistive_reach_ux.spec.js` (plus renamed assertions in the review specs).

## Slice 9 -- Apply Settings (DEC-188)

Status: **Implemented / Awaiting owner UAT.** Pipeline end: `... -> Review -> Confirm / Resolve -> Apply -> Distance Protection form`.

```text
original interpretation + decisions            (sent by the browser, stateless)
      -> reviewed_state()                       decode, apply_review, engine_adaptation (re-run), review/readiness
      -> readiness must be exactly "ready"      else 409 apply_not_ready
      -> build_apply_plan()                     domain/relay_import/apply_settings.py
      -> ApplySettingsOut                       schemas/relay_import.py   (409/422/400 on refusal; never partial)
      -> wwDistanceApplyImportedSettings()      frontend: validate whole payload, then write form state + inputs
      -> existing change handlers               field visibility, analysis request, wwDistanceRenderPlot()
```

* **Endpoint:** `POST /api/v1/relay-import/review/apply`, same body as `review/validate`. Code: `services/relay_apply_settings.py`
  (readiness gate), `domain/relay_import/apply_settings.py` (plan + form-slot limits). No relay-family knowledge, no math.
* **Payload boundary (superseded by Slice 10 -- see below; the payload is now the complete zone list under stable ids, no `slot`):** `characteristic`, `impedance_basis`, four slots with `enabled`, `direction`, `delay_s`,
  `characteristic_angle_deg`, `reach_ohm` (Mho) or `reactive_reach_ohm` + `resistive_reach_forward_ohm` (+R) +
  `resistive_reach_reverse_ohm` (-R). Finite, non-negative; `0.0` valid. No document, raw-setting or provenance data.
* **Form slots (removed by Slice 10):** Zone 1-3 (forward) and the Reverse Zone (reverse). `form_slot_reasons()` was merged into
  `relay_interpretation_summary.engine_adaptation()` so review readiness and Apply cannot disagree: an *enabled* zone whose
  canonical id does not belong to its slot (a fifth zone such as Zone P, or Zone P sitting in an empty fourth slot) or whose direction
  contradicts the slot is `ZONE_SLOT_UNSUPPORTED` (category Unsupported, blocks). A disabled zone is preserved canonically and not applied.
* **Equivalence:** the payload is the engine adapter's own `ZoneSettings`, reshaped; the form then feeds the unchanged
  manual endpoints. Imported and hand-typed identical values give identical engine input and R-X geometry (tested).
* **Re-Apply / failure / lifecycle:** overwrite, not merge; the R-X view resets to automatic; a failed or malformed Apply changes
  nothing and the review is re-validated. State lives in the tab only; one-way (later form edits never flow back).
* **Remove after Apply (owner UAT fix, 2026-10-14):** an applied relay import owns the Distance Protection state it populated;
  removing that import clears its applied analysis state so stale zone cards and R-X traces cannot remain. A hand edit after Apply
  makes the configuration the user's, and Remove then keeps it. A successfully accepted new relay import likewise releases any
  unedited state still owned by the previous import; failed uploads change nothing and edited configurations are preserved.
  Rules and code: DISTANCE_PROTECTION_ANALYSIS.md, "Ownership of applied state".
* **Out of scope:** extra-zone cards, other relay profiles, persistence, export, write-back.

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

### Defeated-zone delay rule (DEC-187, 2026-10-12)

A generic relay-import step (`defeated_zone.infer_defeated_zones`) reads a distance zone with an unresolved status and an
operating delay of exactly 10.0 s as **Disabled · Assumption** (origin `DEFAULT_ASSUMPTION`, never Mapped; timer and source
provenance preserved). It runs after profile interpretation, is vendor-neutral and distance-zone-only, and is absent from the OEM
profiles and the engine. This supersedes the earlier statements in this document that the P441 sample's Zone P is unresolved/blocking
(the profile still reports it unresolved; the generic step then disables it). Explicit status wins; other delays stay unresolved; an
assumed status can be overridden in review; an enabled Zone P (fifth zone) was reported as unsupported by the four-zone engine until Slice 10 (DEC-189), after which it is validated like any other zone.

## Slice 10 -- Dynamic Distance Zones (DEC-189)

Status: **Implemented / Awaiting owner UAT.** Removes the four-slot ceiling of Slice 9: the reviewed model's complete zone collection
is applied, displayed and plotted.

```text
canonical model (any number of zones)
      -> adapt_to_engine()        one engine ZoneSettings per canonical zone (zones + zone_ids, same length/order)
      -> readiness                the adapter alone decides; there is no separate form-slot check any more
      -> build_apply_plan()       ApplyPlan.zones: every zone, in order, {id, display_name, enabled, direction, geometry}
      -> ApplySettingsOut         schemas/relay_import.py   (no `slot`; at least one zone, no upper bound)
      -> wwDistanceApplyImportedSettings()   validate whole payload; rebuild the zone collection; render cards/plot/legend
      -> GET .../distance-protection[-locus] and .../distance-protection-manual   with ?zones=<JSON list>
```

* **Removed:** `ENGINE_ZONE_COUNT`, `UnsupportedCode.TOO_MANY_ZONES`, `UnsupportedCode.ZONE_SLOT_UNSUPPORTED`, `APPLY_SLOTS`,
  `form_slot_reasons()`. `EngineAdaptation.zones` is a tuple of any length (no padding with `DEFAULT_ZONE4`).
* **Identity:** the canonical zone id (`Z1`, `ZP`, `ZX7`, ...) is the zone's identity and travels as `id`; `display_name` is the source's own
  label. Position carries no meaning (shuffling the model changes only the display order).
* **Payload:** a zone that is disabled is present with `enabled: false`, no geometry and a delay only if the source states one; its
  `direction` is `null` when the source does not state it. An enabled zone always states a forward/reverse direction. The payload still
  carries no document, raw-setting or provenance data.
* **Browser mapping:** `Z1`..`Z4` fill the four standard cards (so the existing Zone 1-3 and Reverse Zone behaviour is preserved); any other
  *enabled* id gets an extra card keyed `z_<slug>`; a disabled non-standard zone has no card. Apply rebuilds the collection from the
  standard defaults plus the payload, so a re-Apply removes zones that are gone and updates the same id in place.
* **Direction and characteristic:** each zone's own direction decides its geometry (forward, or reverse = rotated 180 degrees); the
  characteristic is still one per analysis and only Mho / Quadrilateral are drawable. A model with any other characteristic is not
  applicable -- readiness blocks Apply and the adapter reports `CHARACTERISTIC_UNSUPPORTED` for that zone.
* **The P441 sample** is unchanged: Zone 4 and Zone P stay Disabled (DEC-187). Overriding Zone P to Enabled blocks only for the missing
  phase-phase and Left Resistive Reach values, and applies as a fifth card once they are resolved.
* **Out of scope (unchanged):** a second relay family, a manual "add zone" editor, per-zone characteristics, non-directional zones,
  persistence, write-back.

## Slice 11 -- Siemens SIPROTEC 7SA511 profile (DEC-196, corrected by DEC-191)

Status: **PAUSED / incomplete pending verified source data (DEC-192, 2026-10-13); code unchanged.** Previously: Implemented / Awaiting owner UAT. The second real profile; the test of the architecture. `siemens-7sa511-v2` (DEC-191 corrected the v1 reading of the real sheet and added a generic capability).

```text
7SA511 PDF -> generic extractor (column-aware) -> identifier (siemens-7sa511) -> Siemens7SA511Profile
   -> canonical model (6 zones, explicit R/X) -> defeated-zone rule (unchanged) -> adapter / review / readiness / Apply
   -> dynamic Distance Protection cards -> R-X plot
```

* **Source fidelity (DEC-191).** The sheet's operating-timer setting cells are **blank**; `Infinity` is in the range column - not the timer and not a zone state, so every delay is Missing. `1201 DIST.PROT. = ON` is the function, not a zone: all zone statuses are Missing (directions stay mapped). The page-5 requirements (0.15 / 0.45 / 3 / 3 s, Zone 1B "inactive") are **source notes** (`DistanceZone.source_notes`), shown as "Document note / proposed requirement - not a current setting, not applied", never a value or a status. The generic extractor keeps the table's value and range columns apart (a lone cell in the range column with an empty value column is the range).
* **Canonical model - two quadrilateral representations.** `CharacteristicSpec.geometry_mode`: `POLAR_REACH` (a reach at an angle in `DistanceZone.reach` - P441, manual form) or `EXPLICIT_RX` (`DistanceZone.x_reach_ohm` X limit + `resistive_reach.phase_phase` Right (+R) + `resistive_reach.reverse` Left (-R), no angle). The 7SA511 states R and X and no angle, so its zones are `EXPLICIT_RX`; no Reach Angle exists anywhere in its model. The model, engine, adapter, Apply, review and UI treat the mode generically - there is no Siemens branch in any of them.
* **Engine / adapter / Apply.** `ZoneSettings.geometry_mode`; an explicit zone is evaluated by `explicit_rx_quadrilateral_zone_operated()` which reuses `quadrilateral_zone_operated()` in the orthogonal frame (one set of maths). Polar and explicit zones coexist; direction (Forward / Reverse = whole characteristic rotated 180 degrees) is independent. `ApplyZone(Out).geometry_mode` and `ZoneSettingsIn.geometry_mode` carry the mode review -> Apply -> analysis state -> R-X plot; an explicit zone is never converted to a polar form and carries `characteristic_angle_deg = null`.
* **Real sample result:** identified (Siemens / SIPROTEC 7SA5 / 7SA511, high); 6 zones; 34 Mapped, 28 Assumption, 29 Missing, 7 blocking before review. Z1 (X 2.74, +R 1.84, R1E 9.14, Forward), Z2 (4.47, 2.12, 9.96, Forward), Z3 (0.69, 0.46, 2.29, Reverse), Z4 (fault-detection stage, no geometry), Z1B (= Z2 reach "for SOTF"), Z1L (non-directional, engine refuses if enabled). After the user states the zone statuses and delays, takes or types the Left (-R) reach and confirms the assumptions, readiness is **Ready to apply** and the unchanged Apply plots the three zones as angle-less boxes (secondary basis).
* **Zone model:** `Z1`, `Z2`, `Z3` (REVERSE - identity and direction are independent), `Z4` (fault-detection stage: direction + delay only), `Z1B`, `Z1L` (non-directional). Any number of zones; none squeezed into slots.
* **Reading rules:** address *and* name must match the table; the printed range supplies the unit (kV -> V is the only conversion); a blank setting cell is Missing; an `Infinity` in the value column is a readable non-number, never a delay; notes about a zone become source notes with their source line; a finite delay is not a zone state.
* **Known generic gaps (reported, not fixed):** phase-earth loops preserved but not plotted; assumption-note wording for non-DEC-186/187 assumptions. (The rectangular R/X gap of DEC-196 is closed by DEC-191; the DEC-187 "infinite delay" proposal is withdrawn.)
* **Not started:** 7SA613, 7SL87, any Siemens family abstraction.

## Slice 12 -- Hitachi Energy RED670 profile (DEC-192)

Status: **Implemented / Awaiting owner UAT.** The third real profile (`hitachi-red670-v1`); the 7SA511 is paused pending verified source data and nothing of it was reused or changed.

```text
RED670 PDF -> generic extractor -> identifier (hitachi-red670) -> HitachiRed670Profile
   -> canonical model (4 zones, explicit R/X) -> defeated-zone rule (unchanged) -> adapter / review / readiness / Apply
   -> dynamic Distance Protection cards -> R-X plot
```

* **Generic code changed: none** (registration line only). The review, readiness, Apply, engine and UI treat the RED670 exactly like the P441 and 7SA511; browser spec `relay_import_red670.spec.js` asserts there is no RED670-specific control or script.
* **Source shape.** Relion 670 sheet: `name | value | range` rows; function-instance headings (`IMP_PROT/DistanceZones/ZMQPDIS:n`); instance-prefixed parameters (`ZM0n-:X1`); channel-numbered CT/VT rows read only from the channels named as phase currents/voltages; page-end scheme requirements kept as zone source notes.
* **Activation is explicit per zone** (`Operation` + `OperationDir`) and Mapped -- the user is not asked for zone state. Zone 4 on the real sheet is switched off by its own parameters (the page-16 "Zone 4 Inactive" line is a note that agrees).
* **Geometry is the native explicit R/X** (`X1`, `RFPP / 2` as +R, no angle); `RFPP` is a phase-phase *loop* value so the canonical +R is half of it (raw value and transformation kept in provenance, DEC-193); phase-phase `RFPP`/`tPP`/`OperationPP` and phase-earth `RFPE` (as printed, never halved)/`tPE`/`OperationPE` stay distinct. Timers are `tPP`/`tPE`, read only while the zone's `Timer` switch is ON; an OFF switch leaves the delay Missing.
* **Left Resistive Reach (-R) is Unsupported (DEC-193)**: the relay forms that boundary with a directional element (`ZDRDIR`), not a resistive reach -- a capability gap of the canonical model. `ArgDir` / `ArgNegRes` are preserved with their raw values; the existing explicit 0.00 Ω suggestion (DEC-185) is offered as a clearly worded *visualization approximation*, never as the relay's geometry. This is the only blocker on the real sheet.
* **Mapped from documented family semantics (DEC-193):** the `ZMQPDIS` quadrilateral characteristic and the primary impedance basis (`IBase`/`UBase`). **Assumptions:** the RFPP / 2 loop convention (to be confirmed against the Relion 670 manual), VT/UBase units (kV, V), line sequence-impedance naming.
* **Real sample:** 4 zones; 44 mapped / 18 assumptions / 4 missing; Not ready until the Left (-R) suggestion is taken and assumptions are confirmed, then Ready to apply and plotted (Zones 1-3 enabled, Zone 4 off).
* **Open generic gaps (reported):** directional-element boundaries (a first-class representation is still missing); phase-earth plotting (unchanged); "Disabled / Defeated" wording for a plainly switched-off zone.
* **Not started:** any further relay profile. See DEC-192 for the full mapped / assumption / missing list.

## Parameter Catalog Foundation (DEC-194; RED670 corrected by DEC-193)

Status: **Foundation implemented (DEC-194); made the primary mapping path by DEC-195 (below).** P441 and RED670 are interpreted catalog-first; Awaiting owner UAT.

```text
PDF -> generic extractor -> identifier -> OEM Parameter Catalog (JSON) -> generic matcher / transformer
    -> canonical model -> defeated-zone rule (unchanged) -> adapter / review / readiness / Apply -> generic engine
```

Code: [backend/app/domain/parameter_catalog/](../../backend/app/domain/parameter_catalog/) (pure domain, no FastAPI / storage imports). Data: [backend/app/data/parameter_catalog/](../../backend/app/data/parameter_catalog/) (with its own README: the format, the lifecycle, how to add a relay).

| Module | Holds |
|---|---|
| `registry.py` | the canonical registry loader / validator (`CanonicalRegistry`, `CanonicalParameter`): id, label (+ geometry variants), type, unit, group, order, scope, **engine path** (checked against the model's dataclasses), applicability |
| `catalog_model.py` | the typed OEM catalog (`Catalog`, `Mapping`, `Selector`, `Step`, `Gate`, `Gap`, ...) and the vocabularies (lifecycle, value sources, authority precedence) |
| `catalog_validation.py` | strict schema + semantic validation (`parse_catalog`); raises `CatalogValidationError` listing every issue |
| `transforms.py` | the named transformation primitives and their parameter / type rules (no code from JSON) |
| `units.py` | unit vocabulary, printed-unit aliases, the listed conversions |
| `interpreter.py` | the generic matcher / transformer (`CatalogInterpreter`): locate, read, validate, transform, write at the engine path, record provenance, preserve the unmapped |
| `loader.py` | `load_store` (validate every file, reject the invalid loudly), selection by manufacturer / family / model / firmware / lifecycle, the lock (`check_lock`) |
| `profile.py` | `CatalogProfile`: a `RelayProfile` backed by one *active* catalog, so a catalog-only relay needs no Python |

* **Roles.** Profiles / extractors parse source structure. The catalog defines OEM parameter meaning. The canonical registry defines application terminology. The review (and so the frontend) is labelled from the registry -- "Reactive Reach (X)", "Right Resistive Reach (+R)", "Phase Time Delay" -- with the OEM's names and codes only under **Source**. The engine consumes the canonical model only. Raw OEM terminology stays in provenance.
* **Provenance** (`Provenance`): raw value, source page / line, `catalog_id`, `catalog_version`, `canonical_id`, `transformation`, `authority`. The review item DTO and the Source disclosure carry them.
* **Lifecycle:** `draft -> validated -> tested -> active`; only `active` interprets real imports; locked versions are digest-checked (`catalog.lock.json`).
* **Equivalence (this slice):** P441 subset (CT/VT, basis, delays, resistive reaches, Zone P direction) and RED670 subset (activation, direction, PP/PE, X1, RFPP, RFPE, gated tPP/tPE, characteristic, basis, ZDRDIR gap, bases, CT/VT, zero-sequence, line impedances) are read by the generic matcher and compared field by field with the hand-written profiles on clean and degraded sheets (`test_parameter_catalog_*_equivalence.py`).
* **Catalog-only relay:** `test_parameter_catalog_new_relay_by_json.py` drives an "Acme X1" PDF through the real upload API using only a JSON catalog.
* **Not started:** switching P441 / RED670 production to their catalogs; 7SA511 migration (paused); another relay family; an administrator editor, database storage, online distribution; CSV / Excel / XML import.

## Catalog-first mapping (DEC-195)

Status: **Implemented / Awaiting owner UAT.** The parameter catalog is now the *primary* mapping path for every field a catalog maps; the hand-written profile survives only as an **extension** for what the catalog schema cannot yet express.

```text
PDF -> generic extractor -> identifier -> active Parameter Catalog (JSON) -> generic matcher / transformer
    -> canonical model  <- (extension profile: only targets the catalog does not map)
    -> defeated-zone rule -> review table -> Apply -> generic engine
```

Ownership: the PDF extractor owns source extraction; the **parameter catalog owns OEM -> canonical meaning**; the canonical registry owns common terminology and metadata; the review owns uncertainty and human resolution; the protection engine owns calculations only.

| Module | Holds |
|---|---|
| `catalog_first.py` | `overlay`: the catalog value wins per (canonical target, zone), also when unresolved; the extension fills only unmapped targets; nothing is dropped (settings the extension read for a catalog-owned value are kept "Not interpreted") |
| `profile.py` | `CatalogProfile(catalog, store, extension=None)`; `interpret_with_coverage` |
| `coverage.py` | `CatalogCoverage`: raw settings in exactly one bucket + canonical values by outcome |
| `dry_run.py` | `dry_run(catalog, registry, document)` -> recognised / mapped / transformed / unsupported / conflicting / unmapped; pure |
| `loader.py` | + `validate_catalog_file`, `verify_shipped_catalogs` (start-up gate), two-active-catalogs applicability check |
| `app/tools/catalog_cli.py` | `validate-catalog`, `dry-run`, `list` |

* **Precedence:** (1) validated active catalog mapping, authoritative even when Missing / Conflict / Unreadable / Unsupported; (2) extension profile, only for targets the catalog does not map; (3) unresolved / unmapped, retained "Not interpreted", never in the engine. No silent fallback to guessed profile logic.
* **Review taxonomy is unchanged:** Mapped / Assumption / Missing / Conflict / Unsupported / Unreadable. Using a catalog is not automatically Mapped; the mapping's `authority` decides (RED670 VT primary is an Assumption).
* **RFPP:** raw OEM value (ohm/loop) -> `divide by 2` (catalog primitive) -> canonical ohm/phase; raw value, transformation and catalog id / version are in the Source. RFPE is used as printed. The owner approved `RFPP / 2` (2026-10-13).
* **Versions:** every catalog-owned value records the catalog id and version; its `profile_version` is `<catalog_id>-v<version>`. The upload response carries `catalog_id`, `catalog_version`, `catalog_coverage` (counts only).
* **Start-up gate:** the shipped catalog set must validate (no rejected file, lock consistent) or the service refuses to start. A catalog change needs a restart; there is no hot reload.
* **Adding a relay with JSON only:** write `<manufacturer>/<family>.json` (`draft`) -> `catalog_cli validate-catalog <file>` -> `catalog_cli dry-run <file> <sheet.pdf>` -> add a test -> set `"lifecycle": "active"` -> `write_lock`. No Python, no relay name in code (guard tests). Proven by the synthetic relay in `test_parameter_catalog_new_relay_by_json.py`.
* **Remaining in Python (extensions):** P441: line-angle reach, residual compensation, Zone 4 / Zone P status from scheme notes, tilts, fault-type reading, line data; RED670: source notes, Active Group, fault-locator fallbacks; 7SA511 entirely (paused, no catalog). The Python that computes the *migrated* fields still runs but its result for catalog-owned targets is discarded (follow-up: delete it after UAT).
* **Unchanged:** the ZDRDIR left boundary is Unsupported (not faked); no administrator GUI; no new relay.

## Remaining relay families (DEC-197)

Status: **Implemented on `feature/remaining-relay-imports` (not merged); awaiting one consolidated owner UAT.** Every remaining
owner sample relay is interpreted by an **active, locked JSON parameter catalog with no hand-written profile** (catalog-only).
P441 and RED670 are unchanged (their catalogs and lock digests are untouched); 7SA511 stays paused (DEC-192).

```text
PDF -> generic extractor -> identifier (unchanged descriptors) -> active OEM catalog (JSON) -> generic matcher / transformer
    -> canonical model -> defeated-zone rule (unchanged) -> generic review / readiness -> Apply -> generic engine
```

### Support status

| Relay | Catalog | Status |
|---|---|---|
| Hitachi Energy REL670 | `hitachi_energy/rel670.json` | **READY FOR OWNER UAT** (catalog-only proof) |
| Hitachi Energy REL511 | `hitachi_energy/rel511.json` (1.2.0, DEC-198 Am. 1-2) | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| Siemens SIPROTEC 5 7SL87 | `siemens/siprotec5_7sl87.json` (1.1.0, DEC-198 Am. 3) | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| Siemens SIPROTEC 4 7SA613 | `siemens/siprotec4_7sa613.json` (1.1.0, DEC-198 Am. 6) | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| Toshiba GRZ100 | `toshiba/grz100.json` (1.1.0, DEC-198 Am. 7) | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| Toshiba GRL200 | `toshiba/grl200.json` | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| NR Electric RCS-941 | `nr_electric/rcs941.json` | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| RELZ100 | `relz/relz100.json` | PARTIALLY SUPPORTED — UAT WITH LIMITATIONS |
| LFZP111 | `lfzp/lfzp111.json` | DEFERRED — SOURCE SEMANTICS NOT VERIFIED (limited review) |
| Siemens 7SA511 | hand-written, paused | DEFERRED — SOURCE SEMANTICS NOT VERIFIED (unchanged) |
| Schneider MiCOM P441 | `schneider/p44x.json` + extension | unchanged (catalog-first, awaiting UAT since DEC-195) |
| Hitachi Energy RED670 | `hitachi_energy/red670.json` + extension | unchanged (catalog-first, awaiting UAT since DEC-195) |

"Partially supported" means the review is useful (identification, CT/VT, line data, zones and every value the sheet states with
its provenance) but the relay cannot reach Apply, because a semantic the engine needs (characteristic, impedance basis, zone state,
timers, phase-phase loop operation) is not stated or not verified -- and is therefore not invented.

### Generic catalog capabilities added (relay-neutral, additive)

| Capability | Where | Used by |
|---|---|---|
| `source_notes`: document notes about a zone ("Zone 1 Forward direction timer set to 0.15s") become that zone's `SourceNote`s -- provenance only, never a value, a status or a default. Rows consumed; coverage counts them *not interpreted*. **UI rule (owner UAT, 2026-10-14):** document notes are preserved for auditability but are collapsed and visually secondary, because they are not authoritative configured settings -- one neutral disclosure per zone under its settings ("Document note" / "N document notes"), collapsed by default; expanded it shows the document's exact words, `Source: Page N · line M` and "Not used as the configured setting." This replaces the earlier always-open "Document note / proposed requirement - not a current setting, not applied" card (DEC-191); presentation only -- extraction, payload, readiness and Apply are unchanged. | catalog key; `interpreter._collect_zone_notes`; `wwRrSourceNotes` | REL670, REL511, 7SL87, 7SA613, GRZ100, RCS-941 |
| `zone_preserved`: declared raw zone settings (blinders, boundary angles, reach multipliers, scheme switches) are kept **with their zone** as visible, never-resolvable Unsupported rows with the catalog's reason. Coverage: recognised-unsupported. A setting a mapping reads is never taken. | catalog key; `interpreter._preserve_zone_settings` | REL511, 7SL87, 7SA613, GRZ100, GRL200, RCS-941, LFZP111, RELZ100 |
| Listed zones may declare a `key` used as `{key}` in templates (`Z_PP1`, `En_ZPP_Rev`, `KZ1X`). | `zones.static[].key` | RCS-941, LFZP111 |
| A setting cell the extractor **established** as blank (`row:blank_value_range`) is **Missing** with the note "the configured setting cell is blank (the range column shows 'Infinity', which is not a setting)" -- never Unreadable and never the range value (generalises DEC-191). An empty cell without that evidence stays Unreadable. | `interpreter.locate` | 7SL87, 7SA613 |
| `distance_scope.name_patterns` (regex over names, for codes written inside names). | catalog key | 7SL87, GRZ100, GRL200, RCS-941, LFZP111, RELZ100 |
| `"manufacturer": null` -- the manufacturer is explicitly not asserted (shown Missing, never a placeholder). | `applicability` | LFZP111, RELZ100 |
| Canonical **CT Ratio / VT Ratio** (`transformers.ct_ratio`, `.vt_ratio`; registry 1.1.0); review rows appear only when a relay states them, so other relays keep exactly their rows. A ratio is never split into primary / secondary. | model, registry, review | GRZ100, LFZP111 |
| A selector's `note` is appended when that source cannot be read (documented, previously unused). | `interpreter.evaluate` | 7SA613 (`Infinity` setting) |

The lock digest counts the new sections only when a catalog uses them, so the locked P441 / RED670 digests are unchanged.
A catalog that declares notes / preserved settings owns them also in catalog-first mode (`catalog_first.overlay`; no effect on
P441 / RED670, which declare neither).

**Investigated, not implemented (documented future capability):** a generic *angle-defined / inclined boundary* geometry would
cover the ZDRDIR directional boundary (RED670 / REL670), the SIPROTEC polygon whose resistance lines are inclined at the distance /
characteristic angle (7SL87, 7SA613), GRZ100 blinders (BFRS, BFLS-angle) and GRL200 mho-with-blinders. It changes the engine and
the R-X renderer, so per the batch rules it is not done here; every such setting is preserved and shown as a capability gap.

### Per-relay mapping summary

* **REL670** -- identical ZMQPDIS semantics to RED670 (DEC-193 / DEC-195): Operation + OperationDir -> status (decision table),
  OperationDir -> direction, OperationPP / PE, X1 -> X (explicit R/X), `RFPP / 2` -> +R (raw value + transformation kept),
  RFPE as printed, R1 / R0 / X0 preserved, `Timer tPP / tPE` gates tPP / tPE, ZMQPDIS -> quadrilateral (documented derivation),
  IBase / UBase -> bases and primary basis (documented derivation), ZDRDIR left boundary = capability gap (0.00 Ω only as a
  user-accepted visualization approximation). **Review wording (owner UAT, 2026-10-14):** the line under an Unsupported
  Left Resistive Reach (−R) is the concise "Relay directional boundary is not yet representable. 0.00 Ω is an optional
  visualization approximation only and is not a mapped relay setting." (`SuggestionSpec.unsupported_rationale`, shown
  alone); semantics unchanged -- still Unsupported, the offer optional, accepting it a visualization resolution
  (Resolved · Suggested, never Mapped), readiness / Apply unchanged. **CT / VT variant handled declaratively**: the indexed channel family matches
  `^(?:CH\d+_)?IL[123]$` / `UL[123]` with no `ChannelType` filter (the REL670 sheet has none); the IN channel is never read.
* **REL511** -- Operation_Zn -> status, DirZn -> direction (`None` is not a printed option: Unsupported), `Timer tn` gates `tn`,
  X1Zn -> X, R1Zn / R0Zn / X0Zn preserved, RFNZn as printed (assumption), CT / VT (Ir / Ur as secondaries: assumptions; VT kV:
  assumption), line data. **Not interpreted:** characteristic, basis, RF loop/per-phase convention (RFZn preserved as an
  Unsupported +R with its raw value), ZnBlock (preserved), directional boundary. *(Superseded by DEC-198 Amendments 1-2 -- see
  the last section: characteristic, loops, basis and the RFZn / RFNZn meanings are now documented relay behaviour.)*
* **7SL87** -- Edit mode -> basis (Primary), Mode -> status, Directional mode -> direction, Function mode -> PP / PE loops,
  X reach / R (ph-ph) / R (ph-g), Zone-inclination angle -> tilt (an explicit 0° is a valid configured value -- no inclination --
  and does not block readiness by itself; any other tilt stays Unsupported; DEC-197 Amendment 1), zone-specific Kr / Kx
  (gated by `Zone-spec. residu. comp.` = YES and format Kr, Kx), CT / VT (VT units assumed kV / V), line length / angle.
  Operate delays: **blank setting cells -> Missing** (never `Infinity`, never the notes' 0.15 / 0.45 / 3 s); the 1-phase / multi-phase
  -> earth / phase delay loop assignment is an assumption. **Not interpreted:** characteristic; the polygon's inclined resistance
  boundary (Dist. characteristic angle preserved in every zone); K0 rows (other compensation format). *(Superseded by DEC-198
  Amendment 3 -- see "7SL87 -- documented relay behaviour": the characteristic is documented, the delay assignment is
  documented, the inclined +R and the left boundary are Unsupported, the phase-phase load cutout in use blocks.)*
* **7SA613** -- Op. mode Zn (+ 1201 FCT Distance) -> status and direction (Z4 Inactive -> Disabled, Z5 Non-directional),
  R(Zn) ph-ph / X(Zn) / RE(Zn) ph-E, Z5 `X+` -> X (`X-` preserved), RE/RL - XE/XL compensation (Z1 own, Z2..Z1B shared;
  format-gated), CT / VT with units from the printed range (kV, AMP), line angle / length / unit. Timers: blank -> Missing,
  `Infinity` setting -> Unreadable "not a finite delay". **Not interpreted:** basis, characteristic, Distance Angle (inclined
  boundary, preserved), Zone Reduction (preserved). *(Superseded by DEC-198 Amendment 6 -- see "7SA613 -- documented relay
  behaviour": characteristic, loops, Secondary basis and the delay assignment are documented, `Infinity` is a configured
  value, the inclined +R / -R and the load cutout block, Zone Reduction is the Z1 tilt.)*
* **GRZ100** -- CT / VT **ratios**, line data, ZS-C / ZG-C -> characteristic (Quad + Quad -> quadrilateral; differing -> "unknown",
  which the engine reports Unsupported -- never forced into one), TZnS / TZnG -> phase / earth delays. **Not interpreted:**
  zone status and direction (no per-zone switch), each zone's reach setting (reactance limit or impedance reach not established),
  BFRS / BFLS-angle / BRRS / BNDS, reactance-line and bottom angles (all preserved with their zones), Krs / Kxs (percent factors in
  Toshiba's own definition -- not the canonical Kr / Kx; preserved), basis. *(Superseded by DEC-198 Amendment 7 -- see "GRZ100 --
  documented relay behaviour": basis, directions, loops, ZnS as the X reach are documented; zone trip state Unverified (site
  PLC) with geometry reviewed; BFRS / BFLS / ZBS-angle, the reverse offset and ZND block as engine limitations; Z4 added.)*
* **GRL200** (setting group 1) -- ZnS-EN / ZnG-EN -> PP / PE loops, agreed ZnS-Dir / ZnG-Dir -> direction, ZnS-Mho.Reach at
  ZnS-Mho.Angle -> polar reach, ZnG-R.Reach -> earth resistive reach, TZnS / TZnG -> delays, ZS-Chara MHO + ZG-Chara QUAD ->
  "unknown" (Unsupported: one canonical characteristic cannot represent both), fault-locator line data. **Not interpreted:**
  zone status (no zone switch), CT / VT (not on the sheet; the notes' CT ratio is not a setting), basis, blinders / mho geometry /
  earth X reach / Krs-Kxs (preserved with the zone).
* **RCS-941** -- U1n / U2n / I1n / I2n (units printed; U as printed phase-to-neutral), Z_PPn at phi1_Reach -> polar reach,
  En_ZPPn / En_ZPGn -> loops, timers (t_Z1, t_PPn / t_PGn, t_Rev), Rn_Quad -> earth resistive reach only while En_ZPGn_Quad = 1,
  K0 -> K0 magnitude (assumption), reverse zone direction from its identity (assumption), line data. **Not interpreted:** zone
  status, forward zones' direction, characteristic, basis, Z_PGn (preserved).
* **RELZ100** -- reference CT / VT (VT kV assumed), line data **exactly as printed** (R1 4.381 > X1 0.74 is not corrected),
  Xn -> X, RNn as printed (assumption), Tn gated by TimerTn, Dir -> direction where stated (Zones 4-5). **Not interpreted:** status,
  Zones 1-3 direction, characteristic, basis, Rn convention (preserved as Unsupported +R), KNn and the T3R reverse timer (preserved).
* **LFZP111** -- CT / VT ratios (N:1), line length / unit, tripping switches -> zone state (**assumption**). **Not interpreted:**
  any reach (multipliers KZn preserved; their combination is not verified), lenticular / quadrilateral geometry, timers (none on the
  sheet), direction, characteristic, basis. Manufacturer not asserted.

### Real-sample results (owner sheets, `RELAY_SAMPLE_PDF_DIR`, never committed)

| Relay | Zones | Review counts (mapped / assumption / missing / unsupported / unreadable / blocking) | Raw settings: extracted = catalog mapped + unsupported + unresolved + not interpreted + outside DP | Readiness after accepting every offered approximation and confirming every assumption |
|---|---|---|---|---|
| REL670 | 4 (Z1-Z3 fwd, Z4 rev, all enabled) | 62 / 9 / 2 / 4 / 0 / 4 | 993 = 88 + 0 + 0 + 117 + 788 | **Ready to apply**; Apply returns 4 zones |
| REL511 | 5 | 35 / 10 / 17 / 11 / 0 / 9 | 238 = 53 + 11 + 2 + 46 + 126 | Not ready (basis, characteristic, PP loops) -- *DEC-197 snapshot; now 12 blocking settings, see the last section* |
| 7SL87 | 6 | 63 / 2 / 14 / 36 / 0 / 6 | 794 = 60 + 31 + 21 + 84 + 598 | Not ready (characteristic, delays); tilt 0° Mapped, not a blocker -- *DEC-197 snapshot; now 12 blocking settings, characteristic documented (DEC-198 Am. 3)* |
| 7SA613 | 6 | 51 / 0 / 26 / 9 / 3 / 16 | 343 = 38 + 3 + 9 + 38 + 255 | Not ready (basis, characteristic, delays, loops, non-dir Z5) |
| GRZ100 | 8 | 30 / 2 / 75 / 58 / 0 / 17 | 858 = 24 + 32 + 0 + 58 + 744 | Not ready (basis, zone status) |
| GRL200 | 6 | 47 / 2 / 22 / 246 / 0 / 7 | 2498 = 63 + 240 + 0 + 121 + 2074 | Not ready (basis, characteristic, zone status) |
| RCS-941 | 4 | 30 / 7 / 26 / 3 / 0 / 12 | 164 = 36 + 3 + 0 + 35 + 90 | Not ready (basis, characteristic, zone status) |
| RELZ100 | 5 | 18 / 9 / 30 / 12 / 0 / 14 | 154 = 31 + 12 + 2 + 36 + 73 | Not ready (basis, characteristic, zone status) |
| LFZP111 | 5 | 6 / 5 / 36 / 8 / 0 / 13 | 102 = 10 + 8 + 0 + 30 + 54 | Not ready (by design: deferred) |

Every extracted raw setting is in exactly one bucket (no extension reads anything for these relays: `extension_interpreted = 0`);
0 conflicts on every real sheet. Unchanged regression references: P441 32 / 36 / 7 / 4 / 0 / 3 and RED670 61 / 9 / 1 / 4 / 0 / 3,
both Ready after the same decisions.

### Consolidated owner-UAT matrix

Upload each owner sheet in Distance Protection -> Import Relay Settings, open *Review Extracted Settings*, compare with the PDF.
"As printed" = the TAP SETTING column. Owner checks are what this batch could not verify from the repository.

| Relay | Sample file | Support status | Identification | CT/VT | Basis | Zones | Status | Direction | Characteristic | Reach | PP resistive reach | PE resistive reach | Timers | Compensation | Review readiness | Apply | R-X plot | Known limitations | Owner checks required |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| REL670 | rel670.pdf | READY FOR OWNER UAT | Hitachi Energy · REL670, V1.2, high | CT 900/1 A (IL1-IL3); VT 132 kV / 110 V (unit assumption) | Primary (IBase/UBase, documented) | Z1-Z4 | Z1-Z4 Enabled (Operation/OperationDir) | Z1-Z3 Fwd, Z4 Rev | Quadrilateral (ZMQPDIS) | X 0.65 / 1.3 / 4.65 / 0.16 Ω | RFPP/2: 0.49 / 0.97 / 3.49 / 0.125 Ω (raw 0.98 / 1.94 / 6.98 / 0.25) | RFPE 3.27 / 6.48 / 17.26 / 0.8 Ω | tPP = tPE 0.15 / 0.45 / 3 / 3 s | none stated (R0/X0 kept) | Not ready -> Ready after 4 × 0.00 Ω approximation + 9 confirmations | Yes | 4 explicit R/X boxes, Z4 dashed reverse | Left boundary is the ZDRDIR directional element (0 Ω is an approximation); PE not plotted | Z4 reverse in service correct?; RFPP/2 for REL670 like RED670; VT/UBase units; the 0 Ω approximation acceptable for viewing |
| REL511 | rel511.pdf | PARTIAL | Hitachi Energy · REL511, V1.2, high | CT 1200 A, Ir 1 A (assumption); VT 132 kV (assumption) / Ur 110 V (assumption) | Missing | Z1-Z5 | Z1-Z4 Enabled, Z5 Disabled (Operation_Zn) | Z1-Z3 Fwd, Z4 Rev; Z5 'None' not interpreted | Missing | X1Zn 3.08 / 4.7 / 10.28 / 0.77 Ω | Unsupported: RFZn preserved (4.62 / 6.77 / 11.87 / 1.15) | RFNZn as printed 15.39 / 17.5 / 23.26 / 3.85 (assumption) | t1-t4 0 / 0.3 / 3 / 3 s (Timer on); Z5 Missing | none (R0/X0 kept) | Not ready (basis, characteristic, PP loops) | No | No | RF loop / per-phase, characteristic, basis, ZnBlock unknown | Is REL511 primary or secondary ohms? Characteristic? RF per loop or per phase? ZnBlock meaning? |
| 7SL87 | 7sl87.pdf | PARTIAL | Siemens · 7SL87, high | CT 1500/1 A; VT 275 kV / 110 V (unit assumption) | Primary (Edit mode) | Z1-Z6 | Z1-Z3 Enabled, Z4-Z6 Disabled (Mode) | Z1-Z3 Fwd, Z4 Rev | Quadrilateral, documented (Siemens C53000-G5040-C011-9; DEC-198 Am. 3) | X 4.7 / 8.5 / 30.5 Ω | Not yet supported: R (ph-ph) 3.1 / 3.6 / 6.6 Ω inclined at 82.7° (per-phase, not halved) | R (ph-g) 11.2 / 14.4 / 34 Ω | **all Missing** (blank cells; Infinity is the range); loop assignment documented | Kr 1.72 / Kx 0.58 (Z1-Z3) | Not ready (delays, inclined +R, left boundary, ph-ph load cutout) | No | No | Inclined R boundary (82.7°) and left / directional boundary not representable (candidate A7 documented only); load cutout effect not verified; explicit tilt = 0° Mapped | Notes' 0.15 / 0.45 / 3 s are not settings -- confirm the real delays; Z4 off matches "Zone 4 Inactive" note |
| 7SA613 | 7sa613.pdf | PARTIAL | Siemens · 7SA613, high | CT 1200/1 A; VT 275 kV / 110 V (units printed) | Secondary, documented (DEC-198 Am. 6) | Z1, Z2, Z3, Z4, Z5, Z1B | Z1-Z3, Z5, Z1B Enabled; Z4 Disabled (Op. mode Inactive) | Z1-Z3, Z1B Fwd; Z5 Non-directional (engine-unsupported) | Polygon (quadrilateral), documented | X 2.4 / 3.6 / 8.8 / 250 / 10.6 (X+) / 3.2 Ω; Z5 X- 6.9 preserved | Not yet supported: R ph-ph 1.5 / 1.7 / 2.4 / 250 / 2.9 / 1.6 Ω inclined at 82° (per phase, not halved); left edge unsupported, no 0 Ω offer | 7.8 / 8.6 / 13.6 / 250 / 16.3 / 8.4 Ω | T1-T3 Missing (blank); T4, T5, T1B ∞ (no timed trip) -- configured, engine-unsupported on Z5 / Z1B | RE/RL 1.51, XE/XL 0.48 | Not ready (delays, R load, inclined +R / −R, ∞ delays, non-directional Z5) | No | No | Inclined polygon, ∞-delay zones, non-directional Z5 and the load trapezoid not representable (A613 / B613 documented only); Zone Reduction 0° exact | Real delays (blank on sheet); R load (ph-ph) / (ph-E) values (blank on sheet) |
| GRZ100 | grz100.pdf | PARTIAL | Toshiba · GRZ100, Ver 2.1, high | CT ratio 1200, VT ratio 1200 | Secondary, documented (DEC-198 Am. 7) | Z1, Z1X, Z2, ZF, Z3, ZR1, ZR2, ZND, Z4 | Not verified (site PLC `TNBGRZ100-01`; default logic in provenance); Z4 not a tripping zone | Fwd Z1 / Z1X / Z2 / ZF / Z3; Rev ZR1 / ZR2 / Z4; ZND Non-directional (engine-unsupported) -- documented | Quadrilateral (ZS-C = ZG-C = Quad, configured); ZND impedance element (unsupported) | X 5.72 / 12 / 8.2 / 8.2 / 14.8 / 1.4 / 1.4 Ω (ZnS, documented) | Not yet supported: BFRS 20 Ω at a fixed 75° (`Rright(X) = BFRS + X·cot 75°`) | Not yet supported: BFLS-angle 120° / ZBS-angle 15°, no 0 Ω offer | TZ1S 0, TZ2S 0.3, TZFS 0.35, TZ3S 3, TZR1S 0.5, TZR2S 3, TZNDS 0.7 s (+G); Z1X 0 s documented; Z4 none (not exposed) | Krs 560 / Kxs 313 % preserved (earth elements) | Not ready (PLC trip state, inclined +R / −R, ZR1 / ZR2 offset, ZND, Z4) | No | No | 75° blinders, polarised left boundary, offset reverse zones, ND impedance element not representable (AGRZ-A / AGRZ-B documented only); Z1S-angle1 0° exact | TNB PLC definition (or owner decision on default logic); exact 201A manual |
| GRL200 | grl200.pdf | PARTIAL | Toshiba · GRL200, high | Missing (only in the notes) | Missing | Z1-Z5, Z1X | Missing; PP/PE enables Z1-Z3 on, Z4, Z5, Z1X off | Z1-Z3 Fwd, Z4 Rev (agreed) | Unknown -> Unsupported (MHO phase / QUAD earth) | mho 3.59 / 7.18 / 10.53 Ω ∠85° | not interpreted (blinder 4.2 / 5 / 5.32 preserved) | ZnG-R.Reach 15.42 / 18.34 / 21.06 Ω | TZnS = TZnG 0.15 / 0.45 / 3 s | Krs/Kxs preserved | Not ready (basis, characteristic, status) | No | No | Mho-with-blinders + quad earth needs a per-loop / blinder geometry model | Basis; CT/VT; is the review useful as it stands? |
| RCS-941 | rcs.pdf | PARTIAL | NR Electric · RCS-941, high | CT 1200/1 A; VT 76.2 kV / 63.5 V (as printed, phase-neutral) | Missing | Z1, Z2, Z3, Reverse Zone | Missing; PP/PE enables on | Z1-Z3 Missing; Reverse Zone Reverse (assumption) | Missing | Z_PP 0.53 / 1.23 / 3.57 / 0.15 Ω ∠80° | not stated | Rn_Quad 2.44 / 4.92 / 14.28 Ω (quad enabled) | t_Z1 0.15; Z2 0.45 / 0.45; Z3 3 / 3; Rev 3 s | K0 0.83 (assumption) | Not ready (basis, characteristic, status) | No | No | PG mho reach (Z_PGn) and blinder not interpreted | Characteristic (mho?); basis; K0 definition |
| RELZ100 | relz100.pdf | PARTIAL | RELZ 100 (manufacturer not asserted), 3.0, high | CT 1200/1 A; VT 132 kV / 0.11 kV = 110 V (units assumed) | Missing | Z1-Z5 | Missing | Z4, Z5 Non-directional; Z1-Z3 Missing | Missing | X 3.91 / 4.59 / 8.98 / 11.81 / 150 Ω | Unsupported: Rn preserved (5.69 / 5.81 / 6.58 / 8.21 / 150) | RNn as printed 16.69 / 16.99 / 18.89 / 23.5 / 150 (assumption) | T1-T4 0 / 0.3 / 3 / 0 s; T5 Missing (TimerT5 OFF) | KNn preserved | Not ready (basis, characteristic, status) | No | No | Line R1 4.381 > X1 0.74 kept as printed | Is the line data correct on the sheet? Zones 1-3 direction; basis |
| LFZP111 | lfzp.pdf | DEFERRED | LFZP111 (manufacturer not asserted), high | CT ratio 600, VT ratio 1200 | Missing | Z1, Z1X, Z1Y, Z2, Z3 | from tripping switch (assumption): Z1, Z2, Z3 on; Z1X, Z1Y blocked | Missing | Missing | not derived (KZn preserved) | not derived | not derived | none on the sheet | not interpreted | Not ready (deferred) | No | No | Multiplier-based reaches, lenticular Z3 | How KZn / KZPh / KR combine into a reach (manual) |
| 7SA511 | 7sa511.pdf | DEFERRED (unchanged) | Siemens · 7SA511, high | as before | Assumption (secondary) | 6 | Missing | Z1, Z2 Fwd, Z3 Rev | Assumption | X/R as before | as before | as before | Missing (blank) | RE/RL - XE/XL | Not ready | after user decisions only | -- | Paused (DEC-192) | none in this batch |
| P441 | p441.pdf | unchanged (regression) | Schneider Electric · P441 | unchanged | unchanged | 5 | unchanged | unchanged | Assumption | unchanged | unchanged | unchanged | unchanged | K0 | Ready after decisions | Yes | unchanged | -- | regression only |
| RED670 | red670.pdf | unchanged (regression) | Hitachi Energy · RED670 | unchanged | Primary | 4 | unchanged | unchanged | Quadrilateral | unchanged | RFPP/2 | RFPE | unchanged | -- | Ready after decisions | Yes | unchanged | -- | regression only |

### Regression

**Regression (2026-10-14):** backend full suite 9,192 tests, 0 failures, 49 skipped (unrelated gates; the relay real-sample tests ran with `RELAY_SAMPLE_PDF_DIR`); focused relay / Distance Protection browser specs 176 passed (171 + the new 5); full browser suite 1,032 specs: 1,029 passed, 3 failed -- `calculated-channel-presentation.spec.js:213` (passed on isolated rerun), `calculated-channel-presentation.spec.js:256` and `impedance_analysis.spec.js:289` (Play/Pause timing; both also fail on untouched `main` b2d796a -- pre-existing, not relay-related).

### Open (owner input needed)

1. Whether the RFPP / 2 convention approved for RED670 applies to REL670 unchanged (same ZMQPDIS parameters; implemented so).
2. The impedance basis of REL511, 7SA613, GRZ100, GRL200, RCS-941 and RELZ100 sheets (not stated; never inferred from magnitudes).
   **REL511 resolved (DEC-198 Amendment 2):** Secondary, documented relay behaviour (ABB 1MRK 506 109-UEN Eq. 39).
   **7SA613 resolved (DEC-198 Amendment 6):** Secondary, documented (Siemens C53000-G1176-C156-2 secondary ranges).
   **GRZ100 resolved (DEC-198 Amendment 7):** Secondary, documented (Toshiba 6F2S0834-0 1 A ranges, secondary-side line data). The others stay open.
3. The characteristic of REL511, 7SL87, 7SA613, RCS-941, RELZ100 (not named on the sheets; the parameter sets suggest
   quadrilateral / mho, but nothing is assumed). **REL511 resolved (DEC-198 Amendment 1):** quadrilateral, documented.
   **7SL87 resolved (DEC-198 Amendment 3):** quadrilateral, documented (Siemens C53000-G5040-C011-9).
   **7SA613 resolved (DEC-198 Amendment 6):** polygon (quadrilateral), documented (Siemens C53000-G1176-C156-2 / -7).
4. The per-loop / per-phase meaning of REL511 RFZn / RELZ100 Rn (preserved, not used). **REL511 resolved (DEC-198 Amendment 2):**
   RFZn phase-phase and RFNZn phase-earth, both ohm/loop; RELZ100 Rn stays open.
5. ~~Whether a zero tilt (7SL87 Zone-inclination angle 0) should be acceptable to the engine.~~ **Resolved (owner, 2026-10-14,
   DEC-197 Amendment 1):** explicit tilt = 0° is a valid configured value and does not block readiness by itself. Generic rule in
   the engine adapter: a stated, finite 0 on explicit R/X geometry is accepted (the X limit is drawn horizontally); any non-zero /
   NaN / infinite tilt and a zero tilt on a polar reach (reference angle not established) stay Unsupported; a blank tilt stays
   Missing, a non-numeric one Unreadable. 7SL87 stays Not ready (characteristic not named; Z1-Z3 delays Missing -- blank cells).
6. A first-class angle-defined / inclined boundary geometry (ZDRDIR, SIPROTEC polygon, Toshiba blinders) -- a future engine slice.
7. GRZ100 operational zone state (DEC-198 Amendment 7): the site-specific PLC program (`TNBGRZ100-01`) is not on the sheet, so
   no zone's in-service state is asserted. Needs TNB's PLC definition, or an owner decision to accept Toshiba's default
   scheme logic for this template `[OPEN]`.

## Relay Import Assistance for Non-Expert Users -- foundation (DEC-198)

Status: **Foundation implemented on `feature/remaining-relay-imports` (not merged); awaiting owner review.** Generic model
only: no shipped catalog, relay mapping, geometry, readiness rule or confirmation gate changed. Governing decision:
[DECISIONS.md -- DEC-198](DECISIONS.md#dec-198----relay-import-assistance-for-non-expert-users).

**Principle.** Relay-family interpretation belongs in the catalog knowledge layer, with cited and verified provenance; the
user is not asked to decide OEM semantics. Documented relay behaviour is derived automatically; known engine limits may be
drawn approximately only under an explicit, versioned, relay-neutral rule whose effect is established (conservative or
bounded); anything unverified that can change the result stays blocking.

```text
Can the semantics be established?  no -> block (Unverified)
        | yes
Can the engine represent it exactly?  yes -> exact (Mapped / Documented relay behaviour)
        | no
Approved conservative / bounded rule?  yes -> automatic approximation (Approximate plot, ready_approximate)
        | no
block (Not yet supported)
```

### Taxonomy (internal -> what the user sees)

| Internal | Presentation category | Chip | Blocks? |
|---|---|---|---|
| `MAPPED`, authority `configured_setting` / `engineering_instruction` | `mapped` | Mapped | no |
| `MAPPED`, authority `documented_derivation` | `documented` | Documented relay behaviour | no |
| `MAPPED`, origin `engine_approximation` + `ApproximationRecord` | `approximate` | Approximate plot | no (readiness `ready_approximate`) |
| `INFERRED` (any authority, incl. an inferred documented derivation such as RFPP / 2) | `assumption` | Assumption | until confirmed (unchanged) |
| `UNRESOLVED` + `MISSING` | `missing` | Source value missing | if the engine needs it |
| `UNRESOLVED` + `UNSUPPORTED` (understood, not representable) | `unsupported` | Not yet supported | if the engine needs it |
| `UNRESOLVED` + `UNVERIFIED` (meaning / conversion not established) -- new | `unverified` | Not yet supported (other explanation) | if the engine needs it |
| `UNRESOLVED` + `NOT_EXPOSED` (the relay has no such setting) -- new | `not_exposed` | Not a relay setting | if the engine needs it |
| `UNRESOLVED` + `CONFLICT` / `UNREADABLE` | `conflict` / `unreadable` | Conflict / Unreadable | as before |

This supersedes the visible Slice 8A words "Missing" and "Unsupported" (the internal category names are unchanged). Review
counts: `mapped_count` now excludes documented values; new `documented_count`, `approximate_count`, `unverified_count`,
`not_exposed_count` (review DTO, state DTO, card line, summary chips). Internal words (gap, adapter, `geometry_mode`,
`UNVERIFIED`) appear only in the Source disclosure, never in the normal UI (browser-tested).

### Catalog additions (`oruxa.parameter-catalog/1`, additive; README of `backend/app/data/parameter_catalog/`)

* `references: [{id, title, verification, document?, section?, page?, scope?}]` -- identification only, length-capped,
  unknown keys refused. A mapping cites `references: [ids]` (carried as `Provenance.references` / `DocumentReference`,
  shown under Source as "Reference: <title> (<document> · <section> · p. N) -- verified / not yet verified").
* `"verification": "verified"` on a mapping = a verified documented derivation: requires `documented_derivation` +
  `mapped` + at least one verified reference, else the catalog is refused (`unverified_reference`).
* `"not_exposed": {"note"}` -- reads / transforms / asserts nothing; a documented-derivation mapping of the same target is
  tried first and wins when it resolves; a configured-setting mapping of the same target is a conflict.
* `gap.kind`: `unsupported` (default, unchanged behaviour) | `unverified`.
* Lock: `references` counts in the semantic digest only when used -- every shipped digest is unchanged (tested). No
  shipped catalog uses any of the new keys yet.
* Coverage / dry-run: new `canonical_values_unverified` / `canonical_values_not_exposed`; unverified sources are
  recognised-unsupported raw settings.

### Approximations (data model only)

`domain/relay_import/approximation.py` (relay-neutral; guard test): `ApproximationClass` conservative / bounded / unbounded
(only the first two may be applied automatically), `ErrorEnvelope`, `ApproximationRule` (`rule_id`, `rule_version`, affected
field, classification, description, envelope -- a bounded rule needs one), `ApproximationRecord` (on the approximated value's
`Provenance`, origin `engine_approximation`; an unbounded record cannot be constructed). **`APPROVED_RULES = ()`** -- no rule
is approved and no OEM catalog can opt into one yet; the future opt-in is a catalog declaration naming a relay-neutral rule id,
allowed only once the catalog has established the relay semantics. The review context sent by the browser can never carry an
approximation (not decodable): approximations will be derived server-side after decoding, before the user's decisions.

### Readiness and Apply

| Readiness | Meaning | Apply |
|---|---|---|
| `not_ready` | the adapter refuses, or a blocking value is open | no |
| `ready_after_confirmation` | accepted, assumptions still unconfirmed (gating unchanged) | no |
| `ready` | accepted, exact under the current verified model | yes |
| `ready_approximate` -- new | accepted, at least one automatic approximation | yes |

No current relay reaches `ready_approximate`. `ApplySettingsOut.approximations[]` (rule id / version, field, classification,
description, envelope, zone id) is empty for every relay; the browser validates it atomically with the rest of the payload
(an unbounded entry or a bounded one without an envelope refuses the Apply), stores it as
`wwDistanceState.appliedApproximations`, shows "Approximate plot" in the R-X legend while non-empty, and releases it together
with the configuration (Remove / newly accepted import: cleared while unedited; a hand-edited configuration keeps it). The
`d032dcd` / `9ceb7a6` ownership rules are unchanged (browser-tested).

### Manual resolution -- intended rule (nothing removed)

*User correction is primarily for source-data problems, not OEM-semantic interpretation.* Appropriate (stays primary):
genuinely missing / blank source values (e.g. 7SL87 / 7SA613 / 7SA511 delays), unreadable cells, extraction / row
association errors. Expert semantic decisions to move into catalog knowledge (later; manual stays as an advanced fallback,
UAT slice): confirming family-convention assumptions (P441 characteristic / loops / Z1-Z4 direction / reach angle; 7SA511
basis / characteristic / R-RE loops; RFPP / 2 for RED670 / REL670), zone status / direction for relays with no per-zone switch
or a fixed direction (GRZ100, GRL200, RCS-941, RELZ100), and the per-zone 0.00 Ω acceptance for the ZDRDIR directional
boundary (a candidate approximation rule). The 0.00 Ω suggestion for a *missing* left reach (P441) stays a user value.

### REL511 -- knowledge integration (DEC-198 Amendments 1-2, catalog 1.2.0)

**References (owner-approved, verified).** Applicability by matching function and parameter structure, **not** a confirmed
firmware match (`REL511_V1.2_TNB` is not asserted to be firmware V1.2).

| Catalog reference id | Document | Used for |
|---|---|---|
| `abb-1mdb06309-yn-fig1`, `-p2` | ABB *Line distance protection terminal REL 511*, **1MDB06309-YN** (April 1999), Fig. 1 pp. 2-3, p. 2 | Characteristic; PP / PE loops (Amendment 1) |
| `abb-1mrk506101-uen-zm` | *Technical reference manual REL 511-C2\*2.3*, **1MRK 506 101-UEN** (May 2001), ZM 1.10-1.14, Tables 66-76 | Units (X / R ohm/ph, RF ohm/loop), Ir = 1 A ranges, ArgDir / ArgNegRes ranges |
| `abb-1mrk506109-uen-conv` | *Application manual REL 511\*2.3*, **1MRK 506 109-UEN** (July 2001), p. 74, Eq. 39 | Conversion to secondary impedances -- the basis |
| `abb-1mrk506109-uen-pp` | same, Fig. 29-30, Eq. 31-37, Eq. 72 (pp. 56-57, 65-67, 88) | Phase-phase boundary; `RFZ1 ≤ 3·X1Z1` names RFZn as the PP reach |
| `abb-1mrk506109-uen-pe` | same, Eq. 24-30, Eq. 69-70 (pp. 63-65, 87-88) | Phase-earth loop boundary; `R = ⅓(2·R1Zn + R0Zn) + RFNZn` |
| `abb-1mrk506167-uen-zm` | *Installation and commissioning manual REL 511\*2.5*, **1MRK 506 167-UEN** (Dec 2006), Tables 25-26 | Test points in ohm/loop (PP: R = RFPP at X = 0) |

The 2.3 / 2.5 manuals are **verified for the REL 511 family (2.3 generation)** and **likely but version-dependent** for the TNB
1.x-style sheet (one X1Zn / R1Zn / X0Zn / R0Zn / RFZn / RFNZn set per zone -- the 2.3 "simplified setting parameters" structure,
whose names the Application manual itself uses in Eq. 69 / 72). The scope note travels with every citation.

| Item | Now (1.2.0) | Classification |
|---|---|---|
| Characteristic | Quadrilateral, `documented_derivation` (Fig. 1), enabled zones; selector `not_exposed` | Documented relay behaviour |
| PP / PE loops | Enabled, `documented_derivation` (p. 2), enabled zones; selectors `not_exposed` | Documented relay behaviour |
| Impedance basis | **Secondary**, `documented_derivation` (verified; evidence `Ir`); never from the CT / VT ratios | Documented relay behaviour |
| RFZn -> +R | `gap` (**unsupported**); raw value, references and the exact relation in the provenance; no +R plotted | **Engine geometry limitation** -- blocking |
| RFNZn | Earth Resistive Reach as printed (ohm/loop, loop domain), `documented_derivation` (verified); not plotted | Documented relay behaviour -- not blocking |
| ZnBlock = On, enabled zone | preserved, `unverified_when: ["on"]` (unchanged) | **Semantic unknown** -- blocking (owner decision; no meaning assigned) |
| Left / directional boundary | `gap` (unsupported), documented relation + references in the note; no 0.00 Ω offer | **Engine geometry limitation** -- blocking |
| Firmware version | not asserted (scheme `V<n>` marker is not firmware) | Source-data gap -- not blocking |

**Documented geometry (recorded in the catalog's interpretation notes and the +R / −R provenance; the engine is unchanged).**
Phase-phase, per-phase R-X plane, forward zone n:

```text
top:   X <= X1Zn                          (horizontal -- the engine's top line is exact)
right: R <= R1Zn * X / X1Zn + RFZn / 2    (inclined at atan(X1Zn / R1Zn), crosses the R axis at +RFZn / 2)
left:  R >= R1Zn * X / X1Zn - RFZn / 2    (parallel to the right line, crosses at -RFZn / 2)
directional: -ArgDir (4th quadrant, 5-45 deg) .. ArgNegRes (2nd quadrant, 90-175 deg from the R axis),
             common to all zones, not on the sheet; reverse zone = forward rotated 180 deg
```

Phase-earth, loop domain (not drawn): reactive reach `(2·X1Zn + X0Zn) / 3`; resistive reach at the zone end
`(2·R1Zn + R0Zn) / 3 + RFNZn`; lines inclined at `atan((2·X1Zn + X0Zn) / (2·R1Zn + R0Zn))`.

**Approximation candidates -- documented, NOT approved, NOT in `APPROVED_RULES`, no records emitted.**

| Candidate | Rule | Class | Condition | Envelope / domain |
|---|---|---|---|---|
| A | +R = RFZn / 2 (vertical) | conservative | R1Zn ≥ 0 | shortfall ≤ R1Zn at X = X1Zn, 0 at X = 0 (real Z1: 2.31 Ω plotted vs 2.87 Ω documented at X1Z1) |
| B | −R = 0, X ≥ 0 | conservative | RFZn ≥ 2·R1Zn (with the documented ArgDir ≥ 5°, ArgNegRes ≥ 90° ranges) | first quadrant / current engine idealisation (the directional element is voltage-polarised); omits the 2nd-quadrant wedge and the 4th-quadrant sliver |

Each needs an owner-approved, relay-neutral rule; REL511 would also need ZnBlock resolved before `ready_approximate`.

**Result (owner REL511 sheet).** Blocking settings **13 -> 12**: semantic unknowns 9 -> **4** (ZnBlock = On × 4 -- the only
one left), engine geometry limitations 4 -> **8** (RFZn inclined boundary × 4, left / directional boundary × 4), source-data
gaps 0 blocking. Documented relay behaviour 12 -> **18** (+ basis, + RFNZn × 5); 5 assumptions (gating unchanged);
`approximations[]` empty; **PARTIALLY SUPPORTED / NOT_READY**. Generic: an Unsupported +R whose gap cites a verified reference
reads "A source fault-resistance setting is available and its resistive boundary is documented, but the current engine cannot
represent that boundary exactly." (without a verified reference -- e.g. RELZ100 -- the previous wording stays). Amendment 1's
history (9 -> 13; 7SL87 / 7SA613 side effects): DECISIONS.md, DEC-198 Amendments 1-2.

### 7SL87 -- documented relay behaviour (DEC-198 Amendment 3, catalog 1.1.0)

**7SL87 characteristic blocker resolved as documented relay behaviour.** **7SL87 remains partial because the source omits
Z1-Z3 timers and the current engine cannot yet reproduce all quadrilateral geometry.** Investigation first (owner-accepted),
then this slice; no approximation rule, no engine change.

**Reference (verified; version-dependent).** Siemens *SIPROTEC 5 Distance and Line Differential Protection, Breaker Management
for 1-Pole and 3-Pole Tripping 7SA87, 7SD87, 7SL87, 7VK87 -- Manual*, **C53000-G5040-C011-9** (V07.50, Edition 11.2017),
chapter 6.6 (distance protection with classic method). The owner sheet is scheme `7SL87_8.81`: applicability rests on the
matching function and parameter structure (`21 Distance prot.`, zones stated with X reach / R (ph-g) / R (ph-ph) /
Zone-inclination angle), is version-dependent, and is **not** a firmware match. The scope note travels with every citation.
The classic-method polygon description (6.6.9.1, pp. 523-525) was not available and was not researched further (owner
instruction).

| Catalog reference id | Section (pages) | Used for |
|---|---|---|
| `siemens-c53000-g5040-c011-9-zones` | 6.6.2.2 Structure of the Function -- zone assignment to quadrilateral / adaptive quadrilateral / MHO / circular operate curves (472-476) | Characteristic: no selector; the zone function-block type fixes the curve |
| `siemens-c53000-g5040-c011-9-quad` | 6.6.15.4-6.6.15.6 Application example, quadrilateral zones (569-580): Dist. characteristic angle (Fig. 6-141), R (ph-ph), R (ph-g), operate delays, Zone-inclination angle | Characteristic; R convention; delay loop assignment; inclined resistance line |
| `siemens-c53000-g5040-c011-9-direction` | 6.6.4 Direction Determination, Fig. 6-102 (500-504) | Left / directional boundary (fixed device characteristic, not a setting) |
| `siemens-c53000-g5040-c011-9-load` | 6.6.5.1-6.6.5.2 Impedance pickup, load cutout, Fig. 6-106 (504-508) | Load cutout (geometry-affecting) |

| Item | Now (1.1.0) | Classification |
|---|---|---|
| Characteristic | Quadrilateral, `documented_derivation` (verified), enabled zones (Mode = on), evidence the quadrilateral parameter set; selector `not_exposed` | Documented relay behaviour -- **no longer a blocker** |
| PP / PE loops | Mapped from `Function mode` (configured); option texts `ph-gnd and ph-ph`, `ph-gnd only`, `ph-ph only` (and the shortened forms) | Mapped (unchanged result on the owner sheet) |
| R (ph-ph) | per-phase (conductor / positive-sequence) value, used directly, **never halved** (the loop arc resistance is halved when setting it, 6.6.15.6) | Documented convention (in the +R provenance) |
| +R at φ = 82.7° | `gap` (unsupported), evidence R (ph-ph) + `21.901.2311.107 Dist. characteristic angle` (raw `3.1 \| 82.7`); `Rright(X) = R + X·cot φ` in the provenance; no vertical +R | **Engine geometry limitation** -- blocking |
| +R at φ = 90° | `7sl87.r_right.vertical`: R (ph-ph) direct, `documented_derivation` (verified), gated on the angle = 90 (the gap ranks first and wins at any other angle) | Documented relay behaviour (exact) |
| R (ph-g) | as printed, per-phase (loop resistance / (1 + Kr)), cited; not drawn | Mapped -- not blocking |
| Operate delays | `Operate delay (multi-ph.)` -> phase delay, `Operate delay (1-phase)` -> earth delay: `documented_derivation` (verified); a **blank cell stays Missing** (never Infinity, a range, a default, a note or a proposed timer) | Assignment documented; **source-data gap** -- Z1-Z3 phase delays block |
| Left / directional boundary | `gap` (unsupported), cites 6.6.4; was Missing with a user 0.00 Ω offer; **no offer** (no directional angles stated -- the DEC-198 Amendment 1 rule) | **Engine geometry limitation / evidence gap** -- blocking |
| Phase-phase load cutout | `Use ph-ph load cutout` preserved with every zone, `unverified_when: ["yes"]`; R / angle preserved; shape vs polygon not verified, so "no intersection" is **not** asserted | Geometry item requiring verification -- blocks an enabled zone while in use |
| Phase-ground load cutout | preserved, not material (acts on the phase-earth loops, not drawn) | Not blocking |
| Zone-inclination angle 0° | Mapped (DEC-197 Amendment 1) | Exact |
| Kr / Kx / K0, parallel-line compensation (NO), PSB / SOTF / blocking switches | unchanged (earth-loop compensation / no effect at the configured state / scheme logic) | Not geometry blockers |

**Approximation candidate -- documented only, NOT approved, NOT in `APPROVED_RULES`, no record emitted.**

| Candidate | Rule | Class | Envelope | Owner sheet (shortfall at the X reach) |
|---|---|---|---|---|
| A7 | +R = R (ph-ph) (vertical) | conservative (first quadrant, φ ≤ 90°) | shortfall ≤ X·cot φ at X = X reach, 0 at X = 0 | Z1 ≈ 0.60 Ω, Z2 ≈ 1.09 Ω, Z3 ≈ 3.91 Ω (cot 82.7° = 0.1281) |

A left-boundary candidate (−R = 0) is not documented: it needs the Siemens polygon / directional evidence (6.6.9.1, Fig. 6-102
angles) first.

**Result (owner 7SL87 sheet).** Blocking settings **9 -> 12**, all genuine: source-data gaps 3 (Z1-Z3 phase delays),
engine geometry limitations 6 (inclined +R × 3, left / directional boundary × 3), geometry verification 3 (phase-phase load
cutout in use × 3); characteristic 3 -> **0**. Documented relay behaviour 0 -> 3 (characteristic Z1-Z3); not exposed 3
(characteristic Z4-Z6, switched off); 0.00 Ω offers 3 -> 0; 2 assumptions (VT units, unchanged); `approximations[]` empty.
With the Z1-Z3 timers typed in, 9 still block. **PARTIALLY SUPPORTED / NOT_READY.**

**Open (found in this slice) -- closed by DEC-198 Amendment 4.** `review/validate` accepted a manual value for an
Unsupported +R although the review offers no manual entry for it (also REL511 RFZn); a crafted request can no longer do so
(see "Manual resolution authority" below).

### Manual resolution authority (DEC-198 Amendment 4)

**Manual resolution authority is generated by the backend review. Clients may submit only resolutions explicitly offered by
that review; clients cannot convert Unsupported or Unverified engineering semantics into accepted values.**

```text
review generation      build_extraction_review -> item.resolution = manual_entry_spec(path, sourced)   (domain rule)
validate / Apply       reviewed_state(token, import_id, decisions, signer)
                         original = signer.verify(token, import_id, current relay knowledge)   (Amendment 5)
                         offered  = manual_entry_paths(original)      (the server review of the original, no decisions)
                         apply_review(original, decisions, offered_manual=offered)
                           manual path not offered -> 400 invalid_review
                           "This setting cannot be resolved manually in the current review."
                         -> engine adapter re-run -> readiness -> (Apply) plan
```

| Value | Typed entry offered / accepted? |
|---|---|
| Unresolved, cause missing (blank / absent cell, a gated timer switched off) | yes, where a canonical type spec exists |
| Unresolved, cause unreadable | yes, where a canonical type spec exists |
| Zone status Oruxa only assumed (absent optional zone, defeated delay) | yes (override) |
| Already resolved in the session (typed or an accepted suggestion) | yes, judged by its original cause (re-edit) |
| Unsupported (documented but unrepresentable geometry, engine limit), Unverified, Not exposed, Conflict | **no** |
| Mapped / documented / inferred (assumption) value | **no** (assumptions are confirmed, not overwritten) |
| A canonical path the review does not show (e.g. `resistive_reach.common`) | **no** |

Suggestions are server-derived and unchanged: the client names an item, the server re-derives whether a suggestion is offered
(missing value, or unsupported with stated directional angles; never for a disabled zone) and its value. One unauthorised entry
refuses the whole request. Decisions are judged against the interpretation they are sent with, so a replay against another
import is refused unless that review offers the same entry; superseded / removed imports are handled by the browser (the
server keeps no import state).

~~`[OPEN]` -- the validation context itself is not authenticated~~ -- **closed by DEC-198 Amendment 5** (below).

### Signed validation token (DEC-198 Amendment 5)

**Signed validation tokens provide integrity, expiry and import binding while preserving stateless backend operation. They do
not provide immediate revocation of an already issued token after browser-side Remove or supersession; that would require
server-side state.**

```text
upload     model + relay knowledge --> token = "v1." + b64url(zlib(canonical JSON payload)) + "." + b64url(HMAC-SHA256(key, "v1." + body))
           payload: schema "oruxa.relay-review-token/1", import_id (uuid4, backend-generated), issued_at, expires_at,
                    knowledge {profile_id, profile_version, catalog {id, version, semantic digest}}, model (canonical snapshot)
           response review: validation_token + import_id (no validation_context)
validate   verify: format -> HMAC (constant time, canonical base64, before decompressing) -> schema -> issued_at / expiry
Apply        -> import_id matches the request -> knowledge == the service's current knowledge for that profile
             -> decode snapshot (strict) -> manual-resolution authority (Amendment 4) -> decisions -> readiness / plan
           any failure -> 400 invalid_review_token "This relay review is no longer valid. Please upload the setting file again."
```

| Item | Rule |
|---|---|
| Key | `RELAY_REVIEW_SIGNING_KEY` (≥ 32 characters), from the environment / host `.env`; required when `ENVIRONMENT=production` or `APP_VERSION` is set (every deployed build, VPS DEV included) -- the backend refuses to start without it; one value per environment, shared by every instance of it; never committed, never logged or returned. Local development / tests without a key: a random per-process key (tokens do not survive a restart). |
| Lifetime | `RELAY_REVIEW_TOKEN_TTL_HOURS`, default 24; an expired token -> re-upload. 300 s clock skew tolerated for `issued_at`. |
| Rotation | Changing the key invalidates every open review (users re-upload); there is no key ring. |
| Import binding | The request's `import_id` must equal the token's: token A cannot be used with import B (and the reverse). |
| Relay knowledge | A token made with another profile version, catalog version or catalog semantic digest (or a profile that no longer exists) is refused: a changed catalog never silently re-reads an earlier review. |
| No unsigned fallback | `ReviewValidationIn` forbids unknown fields: a body with `validation_context` is a 422, with or without a token. |
| Browser | Holds `validation_token` / `import_id` from the upload and returns them unchanged; no crypto, no parsing (`wwRrPayload`). Remove / new-import ownership unchanged (`d032dcd`, `9ceb7a6`). |
| Not provided | Revocation: after a browser Remove or a newer upload, the earlier token stays valid until it expires (tested as such). The token is signed, not encrypted: its payload is readable, and holds only the interpretation the review already shows. |

### 7SA613 -- documented relay behaviour (DEC-198 Amendment 6, catalog 1.1.0)

**7SA613 artificial semantic blockers resolved.** **7SA613 remains partial due to genuine source gaps and engine
limitations.** Investigation first (owner-accepted), then this slice; no approximation rule.

**References (verified; version-dependent).** Siemens *SIPROTEC Distance Protection 7SA6* manuals **C53000-G1176-C156-2**
(V4.2) and **C53000-G1176-C156-7** (V4.70, 02.2011). The owner sheet's parameter set matches V4.2 (Z1-Z5 + Z1B, R / X ranges
0.05-250 Ω, x' 0.005-6.5 Ω/km, Zone Reduction 0-45°; V4.70 widened the ranges and added Z6); V4.70 is used where it agrees.
No firmware version is asserted.

| Catalog reference id | Section (pages) | Used for |
|---|---|---|
| `siemens-c53000-g1176-c156-2-polygon` | V4.2, 6.2.4 polygonal tripping characteristic (6-55 to 6-63) | polygon, symmetric parallelogram, direction, setting notes |
| `siemens-c53000-g1176-c156-2-settings` | V4.2, 6.2.4.3 settings (6-64 to 6-66): "secondary values of impedance ... refer to IN = 1 A"; timers 0-30 s or ∞ | basis; delays |
| `siemens-c53000-g1176-c156-7-polygon` | V4.70, 2.2.2 (89-102): operating polygons (Fig. 2-22), direction (Fig. 2-24), R per phase, Zone Reduction, Z5, "Setting T5 to infinite prevents that this stage causes a trip" | characteristic; loops; R convention; ∞ |
| `siemens-c53000-g1176-c156-7-ordering` | V4.70, 2.1 address 115 (Region DE only, p. 35), 2.2.2.2 primary / secondary entry (p. 96), A.1 ordering (603-605) | characteristic option; basis |

| Item | Now (1.1.0) | Classification |
|---|---|---|
| Characteristic | Quadrilateral (polygon), `documented_derivation`, zones in service (FCT Distance ON, Op. mode not Inactive); selector `not_exposed`; a `DIS Charact. = Circle` row (Region-DE address 115) would be preserved as Unverified and block | Documented -- **no longer a blocker** |
| PP / PE loops | Enabled, `documented_derivation` (six loops per zone; no per-zone switch), zones in service; selectors `not_exposed`; `1221A 2Ph-E faults` preserved (loop selection, not boundary) | Documented -- **no longer a blocker** |
| Basis | **Secondary**, `documented_derivation` (owner-approved): V4.2 secondary ranges printed on the sheet, 1 A device, secondary-form V / I settings; never from CT / VT ratios | Documented -- **no longer a blocker** |
| R(Zn) ph-ph | per phase (half the loop arc resistance), used directly, never halved | Documented convention (in the +R / −R provenance) |
| +R at φ = 82° | `gap` (unsupported), evidence R(Zn) ph-ph + Distance Angle (raw `1.5 \| 82`); `Rright(X) = R + X·cot φ`; direct mapping only at φ = 90° | Engine geometry limitation -- blocking |
| Left (−R) | `gap` (unsupported), same evidence; `Rleft(X) = −R + X·cot φ` (symmetric parallelogram) + fixed directional characteristic; **no 0.00 Ω offer** (was Missing + offer) | Engine geometry limitation -- blocking |
| Zone Reduction (Z1) | mapped to `tilt` (0° = exact; non-zero = Unsupported, DEC-197 Am. 1) | Exact |
| T1-T3 delays | blank cells -> Missing (never Infinity, a range, a default or the notes); T-1phase -> PE, T-multi-phase -> PP documented | **Source-data gap** -- blocking |
| T4 / T5 / T1B = Infinity | configured value `inf`, shown "∞ (no timed trip)" (generic `infinity` selector option) -- never Unreadable; Z4 (Inactive) non-blocking, no delay carried; Z5 / Z1B in service -> `DELAY_INFINITE` | Documented value; **engine limitation** (no zone that only picks up) -- blocking |
| Z5 Non-Directional | direction preserved (never forced forward / reverse); X(Z5)− preserved; entire parallelogram ±X, no directional clipping | **Engine limitation** -- blocking |
| R load (ph-ph) blank | preserved with every zone, `material_unless: ["infinity"]`: blank -> "Source value missing", blocks a zone in service; a stated finite value would block as an engine limitation; `Infinity` -> no effect | **Source-data gap** -- blocking |
| R load / phi load (ph-E), phi load (ph-ph) | preserved, not material (phase-earth loops not drawn; phi only matters with a finite R) | Not blocking |

**Approximation candidates -- documented only, NOT approved, NOT in `APPROVED_RULES`, no record emitted.**

| Candidate | Rule | Class | Condition / envelope | Owner sheet |
|---|---|---|---|---|
| A613 | +R = R (vertical) | conservative (first quadrant, φ ≤ 90°) | shortfall ≤ X·cot φ at X = X(Zn), 0 at X = 0 | Z1 0.34, Z2 0.51, Z3 1.24, Z1B 0.45, Z5 1.49 Ω (cot 82° = 0.1405) |
| B613 | −R = 0 with X ≥ 0 | conservative where R ≥ X·cot φ (and the directional characteristic keeps its safety margin outside the first quadrant) | omits the 2nd-quadrant part of the polygon | holds for Z1, Z2, Z3, Z1B, Z5 (left edge at the top −1.15 to −1.41 Ω) |

**Result (owner 7SA613 sheet).** Blocking settings **21 -> 18**: removed basis 1, characteristic 5, PP loops 5 (artificial);
remaining Z1-Z3 delays 3 (source), +R 5 and −R 5 (engine geometry), R load (ph-ph) 5 (source; zones in service Z1, Z2, Z3,
Z5, Z1B); plus the engine refusals on resolved values -- infinite delay (Z5, Z1B) and non-directional Z5. Documented relay
behaviour 0 -> 17; not exposed 3 (Z4); Unreadable 3 -> 0; 0.00 Ω offers 5 -> 0; `approximations[]` empty.
**PARTIALLY SUPPORTED / NOT_READY.**

### GRZ100 -- documented relay behaviour (DEC-198 Amendment 7, catalog 1.1.0)

**GRZ100 has no genuine source-data gaps. GRZ100 remains partial because of custom PLC status uncertainty and engine geometry
limitations.** Investigation first (owner-accepted), then this slice; no approximation rule.

**References (verified; version-dependent).** Toshiba GRZ100 instruction manual **6F2S0834-0** (Ver. 0.3, documented model set
GRZ100-211B to -323B) and brochure **6641-1** (lists Model 201). The owner sheet is a GRZ100-201A (`GRZ100_201A_Ver2.1`); the
manual is used where its setting set matches the sheet (same names, the 1 A ranges printed beside every ohmic setting) -- not
claimed as the exact 201A manual.

| Catalog reference id | Section (pages) | Used for |
|---|---|---|
| `toshiba-6f2s0834-0-distance` | 2.4.1 time-stepped distance protection (24-39): zone functions, Mho / Quad, Fig. 2.4.1.2, scheme logic Fig. 2.4.1.5, Fig. 2.4.1.14 | directions, loops, default trip logic, Z4, compensation |
| `toshiba-6f2s0834-0-settings` | 2.4.1 settings (31-34): ranges per CT rating (1 A in parentheses), fixed BFRS / BRRS 75°, Z4BS 7.5 Ω | basis, X reach, blinder angles |
| `toshiba-6f2s0834-0-zone1x` | 2.4.2 zone 1 extension (40-42): instantaneous trip, Z1X_F.ENABLE | Z1X delay and state |
| `toshiba-6f2s0834-0-elements` | 2.6.1 distance measuring elements (113-121): reactance, blinder, directional, offset directional, reverse offset Fig. 2.6.1.3, ZND | geometry |
| `toshiba-6f2s0834-0-fault-locator` | 2.8.5 fault locator (150): line data on the secondary side of CT and VT | basis |
| `toshiba-6641-1-brochure` | brochure (3-4, 21): zones, Fig. 3, reverse offset directional, Z4, Model 201 | directions, Z4 |

| Item | Now (1.1.0) | Classification |
|---|---|---|
| ZS-C / ZG-C | exact configured selectors (Quad + Quad -> quadrilateral; mismatch -> unknown) | Mapped |
| Basis | **Secondary**, `documented_derivation` (owner-approved): 1 A ranges printed on the sheet, secondary-side line data, Vn 110 V; never ratios | Documented -- **no longer a blocker** |
| Direction | forward Z1 / Z1X / Z2 / ZF / Z3, reverse ZR1 / ZR2 / Z4, non-directional ZND (zone function); selector `not_exposed` | Documented -- **no longer a blocker** (ZND engine-unsupported) |
| PP / PE | enabled for every zone (separate S / G elements); selectors `not_exposed` | Documented |
| ZnS / ZnG | ZnS -> X reach (Quad, secondary Ω/phase, direct); ZnG -> earth X reach preserved | Documented / preserved |
| Zone trip state | default scheme logic in provenance (Z1 / Z2 / Z3 trip; ZF / ZR1 / ZR2 / ZND via [ZnBT]; Z1X via Z1EXT or Z1X_F.ENABLE); site PLC `TNBGRZ100-01` can override and is not on the sheet -> **Unverified**, never Enabled / Disabled, never entered; geometry still reviewed (generic `ZONE_STATUS_UNVERIFIED`) | **Site-specific logic not verified** -- blocking |
| Z4 | reverse, command protection only, no timer (`not_exposed`), status Unsupported (generic `ZONE_STATUS_UNSUPPORTED`); Z4S cited, Z4G preserved | Preserved, not drawn -- blocking |
| +R (BFRS) | `gap`: `Rright(X) = BFRS + X·cot 75°` (BFR fixed 75°); reverse zones BRR / BRL | Engine geometry limitation -- blocking |
| −R (BFLS-angle, ZBS-angle) | `gap`: BFL Vp·I·cos(φ + θ − 90°) > 0, directional I·Vp·cos(θ − φ) >= 0; combined orientation not fully verified; **no 0.00 Ω offer** | Engine geometry limitation -- blocking |
| Reverse offset | ZR1BT / ZR2BT `always_material`: forward offset 7.5 Ω (1 A), limited to Z1S when On (Fig. 2.6.1.3) | Engine geometry limitation -- blocking |
| ZND | impedance element (circle) + BNDS 75° blinders, non-directional | Engine limitation -- blocking |
| Z1S-angle1 | Z1 / Z1X tilt: 0° horizontal = exact; non-zero broken line = Unsupported | Exact on the owner sheet |
| Earth blinders BFRG / BRRG / BNDG | Earth Resistive Reach `gap` (inclined, not drawn) -- was a false "Missing" | Not blocking |
| Krs / Kxs / Krm / Kxm / KrsR / KxsR | preserved with Z1 / Z1X / Z2 (ZR1); not the canonical Kr / Kx | Not blocking |
| Timers | TZnS / TZnG exact; Z1X 0 s documented; no note-derived value | Mapped / Documented |

**Approximation candidates -- documented only, NOT approved, NOT in `APPROVED_RULES`, no record emitted.**

| Candidate | Rule | Class | Condition / envelope | Owner sheet |
|---|---|---|---|---|
| AGRZ-A | +R = BFRS (vertical) | conservative | shortfall X·cot 75° at the X reach, 0 at X = 0 | Z1 1.53, Z2 2.20, Z3 3.97 Ω (cot 75° = 0.2679) |
| AGRZ-B | −R = 0 with X >= 0 | conservative candidate | pending confirmation of the combined BFLS / directional orientation | BFLS 120°, ZBS 15° |

**Result (owner GRZ100 sheet).** Blocking settings **17 -> 26**: removed basis 1, status "Missing" 8, direction 8 (artificial);
now trip state Unverified 8, Z4 1, +R 7, −R 7, reverse offset 2, ZND characteristic 1 (all genuine), plus the engine refusal of
the non-directional ZND. Missing 75 -> 8 (zone level 0; the 8 left are document-level fields the sheet does not carry);
documented relay behaviour 0 -> 36; `approximations[]` empty. **PARTIALLY SUPPORTED / NOT_READY.**

### Recommended next slices (not started)

1. ~~REL511 references + verified derivations~~ -- done (Amendment 1). Still open: Relion 670 references; RELZ100 Rn as `unverified`.
   ~~REL511 basis / RFZn / RFNZn semantics~~ -- done (Amendment 2). Still open for REL511: **ZnBlock** (needs OEM evidence:
   the REL 511\*1.2 User's Guide 1MRK 506 002-UEN or TNB's template definition), then candidates A / B for owner approval.
   ~~7SL87 characteristic / delay assignment / R convention~~ -- done (Amendment 3). Still open for 7SL87: the real Z1-Z3
   delays (source data), the Siemens polygon / directional evidence (6.6.9.1, Fig. 6-102) for the left boundary, the load-cutout
   shape (Fig. 6-106), then candidate A7 for owner approval. ~~Generic: refuse a manual value where the review offers none~~ -- done
   (Amendment 4). ~~Still open (generic): authenticate the validation context~~ -- done (Amendment 5).
   ~~7SA613 characteristic / loops / basis / delay assignment / Infinity~~ -- done (Amendment 6). Still open for 7SA613: the
   real Z1-Z3 delays and R load (ph-ph) (source data), then owner decisions on A613 / B613; generic engine support for a
   zone that only picks up (infinite delay) and for non-directional zones.
   ~~GRZ100 basis / direction / loops / X reach / Z1X delay~~ -- done (Amendment 7). Still open for GRZ100: the site PLC
   program (operational state), the exact 201A manual, owner decisions on AGRZ-A / AGRZ-B (AGRZ-B also needs the combined
   BFLS / directional orientation confirmed); generic engine support for inclined / polarised boundaries, offset reverse zones
   and non-directional impedance elements.
2. Narrow assumption gating to values the engine / analysis consumes (deferred by the owner: P441 / RED670 regression risk).
3. The first approximation rule (ZDRDIR directional boundary) with its established classification and envelope, opted into by
   RED670 / REL670; resolve the open 670 resistive-line inclination question first.
4. Non-expert UI pass (Advanced section for manual overrides) -- `[DECISION MODE: UAT]`.
5. Polygon / half-plane engine geometry (turns most approximations into exact plots).

## Relay scalability programme -- Phase 0: generic conformance harness (DEC-199)

Status: **Phase 0 implemented on `feature/remaining-relay-imports` (not merged).** Governing decision:
[DECISIONS.md -- DEC-199](DECISIONS.md). Tests only: no production code, catalog, readiness, Apply, geometry or frontend
behaviour changed.

**Target.** A relay whose engineering concepts are already supported generically needs only **catalog + references +
fixture / expectation data**. Production code changes only for a new reusable protection concept, transformation or
source / extraction structure. Later phases (each separately approved):
1. geometry kernel in shadow mode;
2. canonical boundary vocabulary;
3. operational layer separate from geometry;
4. disks and exclusion;
5. catalog operators and CLI;
6. retire extension profiles.

| Piece | Location | Role |
|---|---|---|
| Sheet specs | `backend/tests/relay_conformance/sheets/*.json` | Single source of every synthetic relay sheet (backend + browser); PDF built only by `sheet_spec.sheet_pdf` |
| Sheet CLI | `python -m tests.relay_conformance.sheet_cli <id> [overrides]` | How the browser tests obtain a sheet (`relaySheet()` in `browser-tests/support/relay_import_helpers.js`) |
| Harness | `backend/tests/relay_conformance/harness.py` | Observes a sample through the real API + the engine adapter's reason codes; compares with an expectation |
| Expectations | `backend/tests/relay_conformance/expectations/*.json` | 46 engineering-semantic records (14 base, 20 scenario variants, 12 owner sheets gated on `RELAY_SAMPLE_PDF_DIR`) |
| Snapshot tool | `python -m tests.relay_conformance.snapshot` | Records / prints an observation (review every line before writing) |
| Generic suites | `backend/tests/test_relay_conformance.py`, `browser-tests/relay_import_conformance.spec.js` | Catalog integrity, expectations, invariants, authority, mutations; the real review UI against the same data |
| Known findings | `backend/tests/relay_conformance/known_findings.json` + `mutations` in expectations | Current deviations reported, not fixed |

**Adding a relay** (no dedicated Python test file, no browser spec): catalog + references (validated, locked) ->
`sheets/<id>.json` -> `expectations/<id>.json` (snapshot, then review) -> `mutations.disable_zone` -> run the generic
suites. Details: `backend/tests/relay_conformance/README.md`.

**Phase 1 preparation.** Each expectation's `apply.zones` is the V1 engine geometry, and `zones[*].geometry` classifies
it. `golden` (`points`, `outlines`) is reserved: Phase 1 records the V1 outline / point-membership goldens there and
proves the V2 kernel reproduces them before any boundary changes.

**Findings (current behaviour, frozen as data, not fixed):**
- **F-1:** a blank configured numeric cell on the P441 / 7SA511 sheets (hand-written profiles) and one 7SA613 row is
  Unreadable rather than Missing. It is never a value.
- **F-2:** disabling the only zone in service leaves that zone's characteristic blocking.
- **F-3:** the 7SL87 catalog has an uncited reference.

### Phase 1: generic geometry kernel in shadow mode (DEC-199 Amendment 1)

**V1 remains production-authoritative; V2 is shadow-only.** The Distance engine (`app/domain/distance_protection.py`),
readiness, Apply and the frontend plot are unchanged; no production code path imports the kernel.

| Piece | Location | Role |
|---|---|---|
| Kernel | `app/domain/distance_geometry.py` | `HalfPlane`, `Disk`, `Intersection`, point reflection; membership; bounded outline; frames; `BoundaryMeta` |
| Compatibility compiler | `app/domain/distance_geometry_compat.py` | V1 engine input -> V2 characteristic (temporary; tests only) |
| V1 goldens | `golden` in each `backend/tests/relay_conformance/expectations/*.json`; built by `tests/relay_conformance/golden.py` | V1 outline, membership grid and probes per drawn zone |
| Shadow comparison | `tests/test_relay_conformance.py` (golden tests), `tests/test_distance_geometry_*.py` | V1 == golden; V2 == golden; shape matrix; checkpoints |

* **Coordinates.** One canonical plane: horizontal **R**, vertical **X**, ohms, in the caller's impedance basis (never
  converted). Angles in **degrees, counter-clockwise from +R** (+X = 90 deg); radians only inside the arithmetic.
  **Absolute frame** = the R-X plane of the measured loop impedance (looking forward into the line); **zone-local frame**
  = the frame a characteristic is stated in before its direction is applied (forward: the absolute frame; reverse: the
  absolute frame rotated 180 deg, i.e. a point reflection -- exactly V1's reverse zone). Every V2 `Characteristic`
  names its frame; only an absolute characteristic is evaluated or outlined.
* **Tolerance.** One policy: `TOLERANCE_OHM` = 1e-6 ohm (= V1's `ZONE_BOUNDARY_TOLERANCE_OHM`) for boundary-inclusive
  membership (half-plane signed distance <= tol; disk distance <= radius + tol) and for outline vertex merging /
  comparison (golden vertices are stored to 6 decimals, compared within 5e-7 + tol). Engine-equivalence test points
  stay `guard_distance(extent)` = max(1e-3 x zone extent, 1000 x tol) from every boundary, so floating-point noise
  never decides a comparison. No per-relay epsilon.

**Coverage.** 22 drawn zones in 7 applied samples, 6,610 membership points compared, 0 mismatches. Mho is covered by the
kernel / compiler shape matrix, since no imported relay currently applies a mho. A new relay whose zones V1 draws gets the
comparison automatically from its expectation.

### Phase 2A: canonical inclined resistive boundaries (DEC-199 Amendment 2)

**Phase 2A proves an OEM-derived geometry that V1 cannot represent against independent engineering equations, while production remains on V1.** V1 stays production-authoritative.

| Piece | Location | Role |
|---|---|---|
| Canonical boundary | `app/domain/distance_boundaries.py` | `ResistiveBoundary` (r_at_axis, angle, side, frame, unit, provenance, fidelity) -> kernel half-plane; `assemble_zone` |
| Catalog section | optional `boundaries` (`catalog_model.BoundarySpec`, validated; in the digest only when used) | Derives boundaries from settings; shadow only |
| Shadow evaluation | `CatalogInterpreter.shadow_boundaries()` | Reads without consuming; never part of the model, review or readiness |
| Conformance | `shadow_geometry` + `shadow_golden` in the expectations; `tests/relay_conformance/shadow_golden.py` | V1 classification beside the V2 shadow; independent engineering goldens |

`resistive(r_at_axis, angle_deg, side)` with an explicit `frame` (`absolute` | `zone`): the line crossing the R axis at
`r_at_axis` at `angle_deg` CCW from +R (0 < angle < 180), `R(X) = r_at_axis + X * cot(angle)`; side `right` = `R <= R(X)`,
`left` = `R >= R(X)`. As a kernel half-plane: right `(sin a, -cos a) . (R, X) <= r_at_axis * sin a`, left
`(-sin a, cos a) . (R, X) <= -r_at_axis * sin a`; 90 deg degenerates to a vertical limit; a `zone`-frame edge is
point-reflected for a reverse zone.

**7SA613 (catalog 1.2.0).** Right / left edges `+/-R(Zn) ph-ph + X * cot(Distance Angle)`, zone frame, documented
(C53000-G1176-C156-2 / -7), for zones in service with a Forward / Reverse Op. mode. Production: +R / -R stay Not yet
supported; 7SA613 stays PARTIALLY SUPPORTED / NOT_READY; A613 / B613 documented only. Shadow: `exact` edges with the top;
the lower / directional limit is not represented yet.

### Phase 2B: canonical directional half-planes (DEC-199 Amendment 3)

**V2 represents a documented directional characteristic as two half-planes through the origin, in shadow mode only;
production remains on V1.** REL511 is the first verified OEM case.

| Piece | Location | Role |
|---|---|---|
| Directional boundary | `app/domain/distance_boundaries.py` | `DirectionalBoundary` (angle, retained side, frame, provenance incl. source convention, fidelity) -> kernel half-plane |
| Sector rule | `assemble_zone(..., directional=...)` | At most one ray per retained side; a sweep of 180 deg or more is refused (it is a union) |
| Catalog section | `boundaries` `kind: directional` (`retained_side`, `convention`, `angle_deg {source, sign, range}`); resistive `r_at_axis.scale`, `angle_deg.atan2` | Shadow only; a source value outside its documented range is not derived |
| Goldens | `shadow_golden.py` `directional`, `directional_points`, `directional_probes` | Membership from the angular condition on atan2(X, R), never the half-plane normals |

**Directional half-plane.** `directional(angle_deg, retained_side, frame)` is the line through the origin along the ray
at `angle_deg` (CCW from +R, (-180, 180]).
- `counter_clockwise` keeps `-sin a * R + cos a * X >= 0`.
- `clockwise` keeps the other side.

Two rays bound the sector swept counter-clockwise from the counter-clockwise-retained ray to the clockwise-retained ray,
but only when that sweep is below 180 deg. `fidelity` (exact | documented | static_equivalent) describes how a boundary
relates to relay behaviour; the geometry is always the exact documented relation.

**REL511 (catalog 1.3.0)** -- *Partial / Not Ready, unchanged*.
- **Directional lines:**
  - ArgDir is a magnitude in the fourth quadrant -> canonical `-ArgDir`, `counter_clockwise`;
  - ArgNegRes is in degrees from +R, in the second quadrant -> canonical `+ArgNegRes`, `clockwise`.

  Both are zone-frame; a reverse zone is the forward characteristic rotated 180 deg. Fidelity is `static_equivalent`:
  the element is polarised by the positive-sequence voltage with memory.
- **Resistive lines:** inclined `R1Zn * X / X1Zn +/- RFZn / 2`.
- **Top:** X1Zn.
- **Not represented:** the lower X limit (added in Phase 2C), the phase-earth geometry and ZnBlock.
- **Sheets:** ArgDir / ArgNegRes appear on neither REL511 sheet, so the owner sheet's zones are not assembled. The
  mapping is proven on the synthetic `directional` variant.

**Relion 670 (RED670 / REL670): ZDRDIR mapping deferred pending verified v1.2 technical-manual evidence.** No directional
mapping exists for them. *Similar parameter names or behaviour across OEM / product generations are not sufficient
evidence for canonical geometry mapping.*

### Phase 2C: canonical lower reactance boundary (DEC-199 Amendment 4)

**Lower reactance boundaries are now a first-class canonical V2 primitive and REL511's documented phase-phase lower
limit is represented exactly in shadow geometry.** Production remains on V1.

| Piece | Location | Role |
|---|---|---|
| Lower limit | `app/domain/distance_boundaries.py` `ReactanceLowerBoundary` | `X >= -x_minus` (x_minus >= 0, mandatory frame) -> one half-plane `(0, -1) . p <= x_minus`; a zone limit is reflected once for a reverse zone |
| Assembly | `assemble_zone(..., lower=...)` | Top + lower + both edges = a bounded region (`not_represented: []`) |
| Catalog section | `boundaries` `kind: reactance_lower`, `x_minus {source}` | Shadow only |
| Goldens | `shadow_golden.py` `lower_points`, `lower_probes`, `closed`, `active`, `boundary_probes` | From the plain inequalities; boundary-by-boundary inside / beyond probes of a closed zone |

**REL511 (catalog 1.4.0).** `X >= -X1Zn` (App. 1MRK 506 109-UEN **Eq. 33**, p. 66; Eq. 34 is the top `X <= X1Zn`), zone
frame, documented. With the resistive lines, the top and -- where the sheet states them -- the directional lines, the
static phase-phase region is closed.
- Every assembled zone records `shadow_geometry: exact` beside `relay_behaviour_fidelity`, the weakest of its
  boundaries: `static_equivalent` once the directional lines are in.
- The owner sheet (no ArgDir / ArgNegRes) stays unassembled.

**Union support remains intentionally deferred** until a real documented relay configuration requires it. A directional
sweep of 180 deg or more stays a refused assembly with its provenance kept (`rel511--wide-sector`).

### Phase 2D: canonical tilted upper reactance boundary (DEC-199 Amendment 5)

**Inclined upper-reactance boundaries are now a first-class V2 primitive where OEM tilt convention is independently
verified.** 7SA613 and 7SL87 are the first verified cases; production remains on V1.

| Piece | Location | Role |
|---|---|---|
| Tilted upper limit | `app/domain/distance_boundaries.py` `TiltedReactanceBoundary` | `X <= x_at_reference - R*tan(tilt_deg)` for all R; added alongside the plain horizontal top, never in its place |
| Assembly | `assemble_zone(..., upper=...)` | Intersecting both half-planes reproduces "inclined ... in the 1st quadrant" without quadrant-conditional logic |
| Catalog section | `boundaries` `kind: reactance_upper` (`x_at_reference {source}`, `tilt_deg {source, range}`) | Shadow only |
| Goldens | `shadow_golden.py` `tilt`, `tilt_points`, `tilt_probes` | From the plain line equation; the existing resistive probes also pick up the tilt automatically |

**The line.** Through `(0, x_at_reference)` on the X axis, retaining `X <= x_at_reference - R*tan(tilt_deg)`
(`-90 < tilt_deg < 90`). At `tilt_deg = 0` this is bit-exact `HalfPlane(0, 1, x_at_reference)` -- the same half-plane
`assemble_zone` already builds for the plain top, not a separate case. The boundary is **added alongside** the
horizontal top: for R >= 0 the tilted line is the tighter constraint (reproducing the manuals' "1st quadrant" scope);
for R < 0 the horizontal one stays tighter -- no quadrant conditional in the kernel.

**7SA613 (catalog 1.3.0), Zone 1 only.** `x_at_reference = X(Z1)`, `tilt_deg = Zone Reduction` (range 0-45 deg;
Siemens C53000-G1176-C156-7, 2.2.2.2: *"Parameter 1307 Zone Reduction allows an inclination of the upper limit of
zone Z1 in the 1st quadrant"*). Z1B and the higher zones have no such tilt (manual, both generations). A non-zero
tilt stays `TILT_UNSUPPORTED` in production; shadow geometry is now `exact` for it.

**7SL87 (catalog 1.2.0), every zone.** `x_at_reference = X reach`, `tilt_deg = Zone-inclination angle` (per zone,
range 0-45 deg; Siemens C53000-G5040-C011-9, 6.6.15.6: *"the limit of the X setting for Zone 1 is inclined downwards
by the zone inclination"*). 7SL87 has no verified left resistive boundary (DEC-198), so no full shadow zone can be
assembled for it yet; the tilt boundary alone is still derived and verified against independent goldens.

Neither relay's convention was inferred from the other -- each is cited to its own accepted manual text.

### Phase 2F: 7SA613's lower reactance boundary, catalog-only reuse (DEC-199 Amendment 6)

**7SA613 gains a fully closed shadow phase-phase region (Z1, Z2, Z3, Z1B) by reusing the Phase 2C
`ReactanceLowerBoundary` primitive through a catalog addition alone -- zero new production code.** V1 stays
authoritative; this is the first direct proof of DEC-199's "catalog + references + data, not new code" goal.

| Piece | Location | Role |
|---|---|---|
| Lower limit | `app/domain/distance_boundaries.py` `ReactanceLowerBoundary` (Phase 2C, unchanged) | `X >= -X(Zn)`, reused as-is |
| Catalog section | `7sa613.boundary.lower`, `kind: reactance_lower`, `zone: ["Z1","Z2","Z3","Z4","Z1B"]` | The only change; `x_minus = X({zone})`, the same setting already read for the top |
| Harness / goldens | `tests/relay_conformance/harness.py`, `shadow_golden.py` (Phase 2C/2D, unchanged) | Already generic across boundary kinds; no edit needed |

**Evidence.** Siemens C53000-G1176-C156-2 (V4.2, p. 6-55) and C53000-G1176-C156-7 (V4.70, p. 89), both already cited
by `7sa613.boundary.right` / `.left`: *"The parallelogram is symmetrical with respect to the origin of the
R-X-coordinate system."* Z1, Z2, Z3, Z4, Z1B each have one `X(Zn)` setting, so the symmetric bottom reuses it
directly. **Z5 is excluded**: it states an independent forward `X(Z5)+` and reverse `X(Z5)-` reach (different default
values), so its reach is not symmetric about a single setting and needs separate treatment, out of scope here.

**Result.** Z1, Z2, Z3, Z1B now assemble with `not_represented: []` -- a closed, bounded parallelogram in shadow
mode (proven also for a reverse zone: `7sa613--lower-reverse`, Z1B reversed). This is **not** a claim that 7SA613's
full characteristic is complete: directional clipping and load-trapezoid encroachment remain outside what any
`exact` zone represents, exactly as before. 7SA613 stays PARTIALLY SUPPORTED / NOT_READY; production unchanged.

### Phase 2G: generic constant-value boundaries, GRZ100's right blinder (DEC-199 Amendment 7)

**A boundary field can now be a fixed OEM constant instead of a document setting, distinct from both a configured
value and a default.** GRZ100's right blinder (BFR, fixed 75 deg) is the first verified case; production remains on
V1.

| Piece | Location | Role |
|---|---|---|
| Constant value | `app/domain/parameter_catalog/catalog_model.py` `ConstantValue(value, unit, name)` | A finite, named, unit-explicit fixed value -- never read from the document |
| Catalog field | `{"constant": <number>, "unit": ..., "name": ..., "sign"?: 1\|-1}` in place of `{"source": ...}` | No `range` (a constant has no setting range to fall outside of); refuses coexisting with `source` |
| Interpreter | `CatalogInterpreter._shadow_boundary()` | Builds the constant's own `BoundarySource` directly (no document location); never calls the document reader for it |
| Goldens | `shadow_golden.py` `shadow_edge_golden()` | Independent checks for a resistive edge recorded on a zone that is **not** (yet) fully assembled |

**The safeguard this exists for.** A missing *configured* value is never satisfied by a *constant*, and a *constant*
never substitutes for a missing *configured* value -- they are independent fields (GRZ100: the constant supplies
only the 75 deg angle; the configured `BFRS` reach must still be read from the sheet, or nothing is derived).

**GRZ100 (catalog 1.2.0).** `grz100.boundary.right`: `r_at_axis = BFRS` (configured), `angle_deg = 75 deg` (constant,
Toshiba 6F2S0834-0, 2.6.1, Fig. 2.6.1.9: *"The BFR has an angle of 75 deg to the R-axis"*), zones Z1/Z1X/Z2/ZF/Z3
only (the forward zones sharing one `BFRS`; the reverse blinder BRR/BRRS and ZND's BNDS are separately scoped and
not represented), gated on `ZS-C = quad`.

The right blinder is now derived and fully provenanced, **even though no GRZ100 zone assembles a complete region**
-- there is still no verified left/directional boundary, so `assemble_zone` is never reached. GRZ100 stays PARTIALLY
SUPPORTED / NOT_READY; left/directional orientation, the reverse-zone forward offset, the ZND circle and the
site-PLC trip status remain exactly as unresolved as before.

### Phase 2I: GRZ100 left blinder, forward zones assemble (DEC-199 Amendment 8)

**GRZ100's forward zones (Z1, Z1X, Z2, ZF, Z3) now assemble a complete open-bottomed region** -- right edge (BFR,
fixed 75 deg, `documented`) plus left edge (BFL, static-equivalent, `static_equivalent`). Production remains on V1.

| Piece | Location | Role |
|---|---|---|
| `static_equivalent` fidelity for resistive | `app/domain/distance_boundaries.py` `ResistiveBoundary.__post_init__` | Voltage-polarised (cross-polarised) boundaries whose static DC equivalent is modelled; previously restricted to directional |
| `r_at_axis` constant | `app/domain/parameter_catalog/catalog_model.py` `BoundarySpec.r_at_axis: Selector \| ConstantValue \| None` | BFLS = 0 Ω is a fixed OEM constant -- same `ConstantValue` introduced in Phase 2G, now extended to `r_at_axis` |
| Constant `r_at_axis` validator | `app/domain/parameter_catalog/catalog_validation.py` `_boundaries()` | New constant branch parallel to the existing constant-`angle_deg` branch; refuses both `source` and `constant` on the same field |
| Constant `r_at_axis` interpreter | `app/domain/parameter_catalog/interpreter.py` `CatalogInterpreter._shadow_boundary()` | `is_constant_r` flag, `_Read` pseudo-read (no document read), explicit `BoundarySource` with no page/line, adjusted transform text |
| Asymmetric-angle zone golden | `tests/relay_conformance/shadow_golden.py` `zone_golden()` | Symmetric zones keep `"cot"`; asymmetric zones (different right/left angles) output `"cot_right"` / `"cot_left"` |

**GRZ100 (catalog 1.3.0).** `grz100.boundary.left`: `r_at_axis = 0` (constant, BFLS fixed at 0 Ω), `angle_deg = BFLS-angle`
(configured, 90-135 deg range, printed as `"degree"` -- `printed_unit` required), gated on `ZS-C = quad`, fidelity
`static_equivalent`. A blank or out-of-range BFLS-angle derives no left boundary; the fixed zero intercept is never
used to stand in for a missing angle.

**Forward zones assemble open-bottomed.** `represented = ["top", "right", "left"]`,
`not_represented = ["lower"]`, `relay_behaviour_fidelity = "static_equivalent"` (max of right=documented,
left=static_equivalent). ZBS directional, reverse-zone offsets, ZND and load encroachment remain unresolved and
not represented.
