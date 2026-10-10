# Relay Settings Import — Architecture (Slice 1: foundation)

Status: **Slices 1-4** (domain contracts, manual entry + engine adapter,
ephemeral upload, generic PDF extraction) implemented on
`feature/distance-relay-import`. Relay identification, relay profiles,
interpretation and auto-population are later slices. Approval record:
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

## Intentionally unresolved in Slice 1

- ~~Mapping onto the existing `ZoneSettings`~~ — done in Slice 2 (above).
- Geometry for lenticular, polygon and unknown characteristics, and
  per-loop (phase-earth) evaluation — need engine work and owner decisions.
- Setting-basis (primary/secondary) handling when the source does not say.
- Whether active setting groups need a multi-group model (currently one
  active group name).
- ~~Extraction technology, upload API shape~~ -- decided in Slices 3-4 (above).
- Relay identification heuristics (Slice 5+), OCR for scanned sheets.
