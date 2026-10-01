# BEN Record Format and Native Parser — `oruxa_powerwave`

Authoritative record of what is known about the BEN disturbance-record
format, what the native parser supports, and the evidence behind it.
Decisions: [DEC-119](DECISIONS.md#dec-119--native-ben-record-parsing-ben--native-parser--normalized-model-comtrade-is-a-validation-oracle-only)
(parser), [DEC-120](DECISIONS.md#dec-120--ben-import-is-integrated-into-the-existing-source-upload-one-endpoint-central-provider-registry-utc-aware-canonical-time-default-nominal-frequency-ben-identity-kept-as-provenance)
(import integration).
Code: [backend/app/providers/ben/](../../backend/app/providers/ben/),
[backend/app/services/import_service.py](../../backend/app/services/import_service.py).

Status (2026-10-01): **importable through the normal upload** (Upload
Recording → format "BEN"), on branch `feat/native-ben-parser`, awaiting
owner UAT. See §7.

**Supported:** the validated BEN32 SubBen layout family (Fast and Slow
SubBen, header signature `2a ff … / 06 ff`).
**Not supported:** older BEN layouts such as the BPHE/GPTH files
(header byte 0x04 = `28`), and any unvalidated variant. These are
rejected with `unsupported_ben_variant`.

## 1. Scope and architecture

`[DECISION]` (owner task, DEC-119):

```text
BEN bytes -> native BEN parser -> BenRecord -> DisturbanceRecord
```

never `BEN -> temporary COMTRADE -> COMTRADE parser`. COMTRADE files
exported by BEN32 are used only as a **test oracle**.

`[FACT]` Module layout (`backend/app/providers/ben/`):

| Module | Role |
|---|---|
| `layout.py` | Every structural constant (offsets, section codes, record sizes, unit/phase codes), named and explained. No other module holds a magic number. |
| `reader.py` | Bounds-checked little-endian reads, section framing, record sections, string tables. An out-of-range read is a `BenTruncatedError`, never an `IndexError`. |
| `parser.py` | `parse_ben(bytes)` / `parse_ben_file(path)`: header → sections → record class → container → layout map → channels → payload boundary. |
| `model.py` | `BenRecord` (native, lossless) and its header/channel types. |
| `normalize.py` | `to_disturbance_record(record, source_file=, nominal_frequency_hz=)`. |
| `provider.py` | `BenProvider(BaseProvider)`, registered for upload by `import_service.build_provider_manager()` (DEC-120). |
| `errors.py` | `BenFormatError` ⊂ `ProviderLoadError`; `BenNotRecognizedError`, `BenUnsupportedVariantError`, `BenTruncatedError`, `BenStructureError`. |

No BEN32 executable is ever run; nothing depends on Windows or COMTRADE.

## 2. File layout (BEN32 3.8.9.6 "SubBen")

All configuration fields are **little-endian**; all sample words are
**big-endian**.

```text
0x000  fixed header (0xDC bytes)
0x0DC  typed sections:  u16 type | u16 0xFFFF | u32 length | payload
       ...
       container:       u16 0x03E8 | u32 length | sub-blocks (section framing)
       u16 0x07D0       sample-data tag
       samples          sample_count x (2 x words_per_sample) bytes, to EOF
```

### 2.1 Fixed header

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | 4 B | `01 00 04 00` BEN family signature |
| 0x04 | 8 B | `2a ff 03 00 6e 00 ca 00` SubBen layout signature (0x04 = `28` in the older layout) |
| 0x0C | u16 | recorder unit number (= COMTRADE `rec_dev_id`) |
| 0x0E | 2 B | `06 ff` (older layout: `05 00`) |
| 0x10 | 40 B | station text, NUL-terminated (= COMTRADE station name) |
| 0x38 | u32 | record number (repeated in the record summary) |
| 0x3C | u8 | 0 = Fast, 1 = Slow |
| 0x42 | 18 B | record label ("New Record") |
| 0x54 | u32 | rate field; samples/s = field / 1000 |
| 0x58 | u32 | pre-trigger samples |
| 0x5C | u32 | sample count |
| 0x60 | u16 | words per sample (stride = 2 × this) |
| 0x64 | 6 × u8 | trigger year−1900, month, day, hour, minute, second (UTC) |
| 0x6A | 3 × u8 | fractional second as base-100 digits: 1e-2, 1e-4, 1e-6 s |
| 0x7A | u32 | last sample index (= count − 1) |
| 0x80 | 92 B | trigger-cause area (kept raw) |

### 2.2 Sections

Record sections are `u16 count | u16 0xFFFF | count × record`, and their
length must equal `4 + count × size` exactly. String tables are
NUL-terminated names addressed by byte offset.

| Type | Record size | Content |
|---|---|---|
| 0x0001 | — | recorder info (kept raw) |
| 0x06A4 | 84 | record class: code 1006 "Fast SubBen" / 1007 "Slow SubBen", repeated rate and pre-trigger |
| 0x0514 | 52 | analog input descriptors (Fast) |
| 0x0515 | 18 | physical binary input descriptors |
| 0x0516 | 164 | calculated-quantity descriptors (Slow) |
| 0x0518 | strings | channel names |
| 0x0578 | 210 | derived-indication (trigger) definitions |
| 0x0579 | 86 | BEN32's exported binary channel list |
| 0x057A | strings | exported binary names |
| 0x06A5 | 44 | station |
| 0x06A6 | 28 | bays (feeders) |
| 0x06A7 | 36 | analog/calculated channel → bay |
| 0x06A9 | 52 | bay cards: up to 8 binary ids → bay |
| 0x06AA / 0x06AB | strings | bay names / card names |

Channels reference each other only through u16 **channel ids**, never
positions. Analog descriptor: id, first trigger id, event id, name
offset, quantity code (0 V, 4 I), phase code (1..4 = A/B/C/N), unit code,
unit power-of-ten multiplier, f32 scale, f32 offset, f32 primary rating
(channel unit), f32 secondary rating (base unit), hardware address.

### 2.3 Sample layout

The container holds a record-summary sub-block (0x4E21, repeating record
number, class, words per sample, rate, pre-trigger and count — all
cross-checked) and the **layout map** (0x4E25): `u16 channel id | u16 word
index | u8 bit | u8 kind` for every channel stored in a sample. Value
channels occupy a whole word (signed int16); binaries one bit of a word,
bit 0 = least-significant bit of the big-endian word.

An exported binary (0x0579) resolves to its bit by BEN's own links: a
nonzero trigger id (+74) → that derived indication's map slot; otherwise
the source id (+76) must be a physical input → its map slot.

## 3. Support status

### 3.1 Proven

Evidence: four matched BEN/BEN32-COMTRADE pairs (two Fast, two Slow) plus
two structural-only files — see §4.

| Finding | Evidence |
|---|---|
| Fast SubBen decoding | LGNG and BAHS: every analog and binary sample equals the COMTRADE export. |
| Slow SubBen decoding | PMJY and BTGH: every available calculated sample and every binary sample equals the export. |
| Samples/s = rate field / 1000 | 5 000 000 → 5000 and 20 000 → 20, in 6 files; equals the CFG rate in 4. |
| Sample count, pre-trigger | Header = CFG in 4 pairs; cross-checked with the summary and class sections. |
| Variable stride / layout | Strides of 158, 128, 72 and 30 bytes; first value word at 8, 7 or 4; `offset + count × stride == file size` exactly in all 6 files. |
| Big-endian int16 values | Exact match in 4 pairs. |
| Scaling, units, phase, ratings | Scale `a`, offset `b`, unit (kV, kA, Hz, MW), phase and primary/secondary match the CFG for every channel of the 4 pairs. CFG secondary = BEN secondary / 10^multiplier. |
| Active-low binaries | Stored 0 = active for all 463 exported binaries of the 4 pairs, including 43 that change state. |
| Binary mapping from descriptors | All 335 + 104 + 12 + 12 exported binaries resolve through the tables of §2.3 with no event-specific data. |
| Trigger time incl. microseconds | BEN UTC + 8 h equals the CFG trigger to the microsecond in all 4 pairs; start = trigger − pre/rate equals the CFG start. |
| Calculated "unavailable" marker | Raw −32768 on a calculated channel ↔ COMTRADE 99999: 5 channels in 2 files, every sample. |

### 3.2 Inferred (consistent, not uniquely proven)

- **UTC.** The stored trigger time is UTC; the +08:00 is the export PC's
  zone. No timezone field was found in BEN.
- **Unit codes.** They coincide with IEC 61850-7-3 SIUnit numbering (5 A,
  29 V, 33 Hz, 38 W). Only those four codes and the multipliers 0/3/6 are
  mapped. Any other code leaves the unit unknown, with a diagnostic.
- **Constant binaries.** The mapping is taken from descriptors. Channels
  that never change in a test file are consistent with the mapping but
  do not confirm it uniquely.
- **Bay (feeder) names.** Every channel resolves to a bay in all 6
  files, but no external oracle confirms the names.

### 3.3 Unknown / not supported

- **Nominal system frequency.** No decoded field declares it. A field
  once suspected (class record +64) is 5000 in five files but 5400 in
  BTGH, which is 50 Hz, so it is not the nominal frequency.
  Normalization therefore requires the caller to supply it.
- **Raw −32768 on sampled analog inputs.** Never observed. It is kept as
  a value, with an `unverified_raw_extreme` diagnostic.
- **Raw 0xFFFF.** In the evidence it only appears as an all-inactive
  **binary** status word, never as an analog marker. Raw −1 is a valid
  value.
- **Other layouts.** The older layout (header 0x04 = `28`, as in
  `BEN BPHE …ben`, `GPTH 275.ben`) has a different configuration area and
  stores local time. It is rejected with `BenUnsupportedVariantError`.
  Other BEN32 versions and record classes are also unvalidated and
  rejected.
- **Uninterpreted content.** The trigger-cause area, recorder info,
  trigger thresholds (0x0578 bodies), the 0x4E20 acquisition block,
  quantity codes and hardware addresses are kept raw or ignored.

### 3.4 Fail-safe rules

- Rejected:
  - an unknown signature, record class or container sub-block;
  - any disagreement between header, class section and summary;
  - a record-count/length mismatch;
  - a map entry outside the sample;
  - two value channels in one word;
  - a value channel with no map entry;
  - truncated data;
  - **trailing bytes**.
- Nothing is truncated, padded or defaulted.
- Reported as `BenRecord.diagnostics` rather than failing:
  - unrecognized but well-framed sections;
  - exported binaries that cannot be resolved (omitted);
  - unused map entries;
  - unknown unit codes;
  - undecodable sub-second digits (whole second kept);
  - duplicate names;
  - unavailable samples.

## 4. Reference evidence

The files are owner engineering records. They are not committed.
[`backend/tests/fixtures/ben/reference_manifest.json`](../../backend/tests/fixtures/ben/reference_manifest.json)
holds their names, sizes, SHA-256 and expected structure.

| Record | Class | sps | Samples | Pre | Value / binary ch. | Stride | Data offset | COMTRADE |
|---|---|---|---|---|---|---|---|---|
| `160126_BEN RECORD TRIPPING LGNG_JMHE1 FIRST TRIP.ben` | Fast | 5000 | 42 745 | 2500 | 56 / 335 | 158 | 74 203 | matched |
| `BAHS 275 Fast Ben time124148659.ben` | Fast | 5000 | 37 595 | 500 | 28 / 104 | 72 | 27 243 | matched |
| `AGJH 221022.ben` | Fast | 5000 | 30 915 | 2500 | 49 / 182 | 128 | 48 617 | none (structural) |
| `PMJY slow sampling time124149926.ben` | Slow | 20 | 1 401 | 400 | 12 / 12 | 30 | 8 210 | matched |
| `BTGH Slow Ben time124150134.ben` | Slow | 20 | 1 401 | 400 | 12 / 12 | 30 | 8 259 | matched |
| `PMJY Slow Sampling time124937632.ben` | Slow | 20 | 1 018 | 400 | 12 / 12 | 30 | 8 210 | none (structural) |
| `BEN BPHE 27 JULY 2022 12.41.46.ben`, `GPTH 275.ben` | older layout | — | — | — | — | — | — | rejected |

Notes:
- `AGJH 275kv slow ben time124150016.cfg/.dat` is a **different event**
  and is never used to validate `AGJH 221022.ben`.
- BAHS and BTGH were found next to the owner-named files. Their pairing
  with the CFG/DAT files is proven by exact sample agreement.
- BEN32 reorders channels on export (e.g. `XGT4_LV`) and repeats binary
  names (`SPARE`). Tests therefore pair channels by name, and repeated
  names by occurrence order.
- BEN stores some names with surrounding spaces, and BEN32's CFG keeps
  them. `BenRecord` keeps names exactly; normalization trims them, as the
  COMTRADE provider does.

## 5. Tests

- `backend/tests/test_ben_parser.py` — always runs.
  - Synthetic files come from `backend/tests/ben/synthetic_ben.py`, which
    restates this layout with its own literal offsets.
  - Covers decoding, diagnostics, normalization, the provider and
    malformed input.
  - Guardrails show that no 5000 sps / 158-byte / 56-channel /
    16-byte-offset / Fast-only assumption exists.
- `backend/tests/test_ben_reference_files.py` — marker `ben_reference`.
  Skipped unless one of these is set:

  ```bash
  cd backend
  pytest -m ben_reference --ben-reference-dir "D:/OneDrive - .../Tripping Event"
  # or: POWERWAVE_BEN_REFERENCE_DIR=... pytest -m ben_reference
  ```

  - Files are found recursively by name and used only when the SHA-256
    matches.
  - It checks every sample of every channel of the matched pairs.

## 6. Open items

Resolved by DEC-120 (2026-10-01):
- timezone: UTC canonical;
- nominal frequency: integration-layer default;
- names: trimmed for display, BEN identity kept.

See §7. Still open:

- `[OPEN]` **Local-time presentation of UTC sources.** See §7.4.
- `[OPEN]` **Bay/feeder and BEN channel ids in the UI.** See §7.5.
- `[OPEN]` **Older BEN layout.** Support for `28 ff` files (BPHE, GPTH)
  would need its own reverse-engineering and validation pair.

## 7. Import integration (DEC-120)

### 7.1 Path

```text
Upload Recording modal (format "BEN", accept .ben)
  -> POST /api/v1/workspaces/{ws}/sources   ben_file [+ nominal_frequency_hz]
  -> import_service.import_ben_source()     bounded read, ephemeral temp dir
  -> build_provider_manager().find_provider(event.ben)  -> BenProvider
  -> BenProvider.load_with_provenance()     parse_ben_file -> BenRecord
                                            -> to_disturbance_record()
  -> SourceMetadata + ActiveSource          same as COMTRADE
  -> prepare_workspace_source()             same post-upload preparation
```

- BEN is imported natively and never converted to COMTRADE.
- COMTRADE uses the same endpoint (`cfg_file` + `dat_file`) and the same
  registry.
- Downstream code has no BEN branch.

### 7.2 Time

Start and trigger are **timezone-aware UTC** datetimes; the API
serializes them as `2026-01-16T05:54:23.229783Z`.

- The time axis is `sample index / rate` from the first sample.
- The trigger sample is the pre-trigger count. LGNG: sample 2500 at
  0.5 s. PMJY: sample 400 at 20 s.
- BEN times are not shifted toward BEN32's local-time COMTRADE exports.

### 7.3 Nominal frequency

`app.domain.metadata.DEFAULT_NOMINAL_FREQUENCY_HZ` (50 Hz) is the single
conventional default, also used by CSV/Excel conversion.

- An upload may pass `nominal_frequency_hz`. It is validated like the
  RMS parameter (1–1000 Hz).
- Provenance records `nominal_frequency_assumed`.
- It is never read from or written to the BEN parser.

### 7.4 Values

- **Slow unavailable samples:** raw −32768 becomes `NaN`, which is
  `null` in waveform JSON. Never 99999.
- **Channel typing:** Hz/MW channels classify as Frequency/Power through
  the existing classifier. They form no V/I Engineering Context.
- **Parity:** the same event imported as BEN and as BEN32 COMTRADE gives
  identical analog summaries (type, unit, phase) for all four matched
  pairs.

`[OPEN]` **Presentation.** The frontend deliberately shows a timestamp's
own wall-clock digits and ignores any offset, so a BEN source displays
UTC (05:54:23 for LGNG).
- The only zone marker is the trailing `Z` in the Recordings Start Time;
  the waveform ruler has none.
- Showing local time (Asia/Kuala_Lumpur) needs a presentation-layer
  timezone policy, which would also change CSV sources with offsets.
- A BEN source and a COMTRADE source of the same event sit 8 h apart in
  Time Groups.

### 7.5 Identity

Display names are trimmed and de-duplicated (`SPARE`, `SPARE_1`).
`SourceMetadata.preparation_provenance` keeps, per normalized name:
- `ben_channel_id`;
- the byte-exact `source_name`;
- `bay`;
- for binaries, `digital_source`.

It also keeps the record class, `time_basis`, nominal frequency,
`nominal_frequency_assumed` and the parser diagnostics.

`[OPEN]` These live in the backend only; channel summaries and the UI do
not show bay or ids yet.

### 7.6 Errors

The API returns user-safe messages. The parser's detail (offsets) is
logged server-side only.

| Input | Code (HTTP 400) | Message |
|---|---|---|
| older/unvalidated layout | `unsupported_ben_variant` | This BEN file uses a BEN layout that is not currently supported. |
| not BEN (e.g. renamed text) | `parse_error` | This file is not a recognized BEN record. |
| truncated | `parse_error` | This BEN file is incomplete (truncated). |
| inconsistent | `parse_error` | This BEN file is corrupt: its internal structure is inconsistent. |
| empty | `invalid_file` | BEN file is empty. |
| `ben_file` without `.ben` | `unsupported_file_type` | — |
| `ben_file` with `cfg_file`/`dat_file` | `ambiguous_source_upload` | — |

### 7.7 Tests

- `backend/tests/test_ben_import_api.py`: synthetic files, real
  endpoint.
- `backend/tests/test_ben_fixtures.py`: committed fixtures stay equal to
  `tests/ben/make_fixtures.py`.
- `backend/tests/test_ben_reference_files.py`: real records through the
  endpoint (`ben_reference` marker), plus BEN/COMTRADE parity.
- `browser-tests/ben-import.spec.js`:
  - Fast and Slow upload → Recordings → Waveform trace;
  - the old-layout and renamed-file error messages.
