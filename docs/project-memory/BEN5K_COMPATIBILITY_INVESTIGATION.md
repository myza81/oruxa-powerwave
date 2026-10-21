# BEN5K compatibility investigation — GPTH recording

Date: 2026-10-20. Status: investigation complete; recommendations await owner review.
No production code, parser rules, tests or original recordings were changed.

## Finding

**[FACT] The supplied recording belongs to the already documented unsupported
`28 ff … / 05 00` BEN layout family. The native parser deliberately rejects it
before extracting channel metadata or decoding samples.** This is a compatibility
gap, not evidence of a defect in the supported SubBen decoder or frontend.

The configuration also differs structurally from the supported format. Accepting
the older signature alone would immediately fail section parsing and would not
provide a safe solution.

This investigation establishes the rejection cause. It does not establish that
every part of the recording is valid, or complete the reverse engineering needed
to decode this older family.

## Repository and evidence baseline

- Repository: `https://github.com/myza81/oruxa-powerwave.git`.
- Local branch: `feature/remaining-relay-imports`, HEAD
  `120b77970f8e96aaca0b934ce6053e7606bf3be9`.
- `git fetch origin` succeeded. Fetched `origin/main`:
  `324af93346ed3474683fd7b82f66be6805189ffd`.
- Local HEAD has 27 commits not in `origin/main`; `origin/main` has four not in
  local HEAD. No matching remote feature branch was present. No checkout,
  reset, stash, merge or rebase was performed.
- Six pre-existing uncommitted relay files were preserved: the GRZ100 catalog,
  distance boundaries, catalog model/validation/interpreter, and shadow golden.
- The entire BEN provider package, import service, source API module and
  `BEN_FORMAT.md` are identical between HEAD and fetched `origin/main`.
- Read repository governance, project-memory startup/current-state/handoff and
  discovery documentation, DEC-119/120 and the BEN-related follow-ups, the
  architecture reference, and `BEN_FORMAT.md`. Fetched `origin/main` also
  explicitly documents older BPHE/GPTH layout rejection.

Input, read without alteration:

```text
D:\OneDrive - Tenaga Nasional Berhad\WorkFiles\Tripping Event\2026\20261016 132kV_KTBR\BEN\261016_180314535_GPTH_275kV.ben
Size:   1,629,786 bytes
SHA256: 55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88
```

The same digest was obtained after reproduction. No CFG or PRN oracle for GPTH
was found in the supplied event directory tree.

## Exact failure and reproduction

Calling `app.providers.ben.parse_ben(bytes)` on the original bytes gives:

```text
parser.py:82   parse_ben -> _check_signatures(file)
parser.py:168  _check_signatures -> raise BenUnsupportedVariantError

BenUnsupportedVariantError: BEN layout signature 28 ff 03 00 6e 00 ca 00 / 05 00 is not the validated BEN32 SubBen layout (2a ff 03 00 6e 00 ca 00 / 06 ff) (at byte offset 0x4)
```

The rejection precedes `_read_header_fields`, `_read_sections`, channel
construction, `np.frombuffer`, normalization and workspace preparation.

The full upload was reproduced with `TestClient(create_app(settings))`, including
application startup, against a temporary archive of fetched `origin/main`:

```text
POST /api/v1/workspaces/ws-ben-investigation/sources
multipart field: ben_file
HTTP 400
{"detail":{"code":"unsupported_ben_variant","message":"This BEN file uses a BEN layout that is not currently supported."}}
```

The same bytes uploaded as `neutral-name.ben` produced the identical response.
Listing sources afterwards returned HTTP 200 and `[]`. Supported committed
`synthetic_fast.ben` and `synthetic_slow.ben` controls then returned HTTP 201,
provider `BEN`, status `ready`, and 500 / 600 samples respectively.

For direct reproduction from the backend directory, with this file accessible:

```python
from pathlib import Path
from app.providers.ben import parse_ben_file

parse_ben_file(Path(
    r"D:\OneDrive - Tenaga Nasional Berhad\WorkFiles\Tripping Event\2026\20261016 132kV_KTBR\BEN\261016_180314535_GPTH_275kV.ben"
))
```

## Full import path and supported assumptions

| Stage | Existing behavior / assumption | Outcome for this recording |
|---|---|---|
| Frontend | `frontend/index.html`: `submitBenUpload` submits `ben_file` through `submitSourceUpload`; ordinary source upload endpoint | Correct upload form exists; frontend decoding is not involved |
| API | `backend/app/api/v1/sources.py:170`: validates upload form, invokes `import_ben_source`, maps domain errors | HTTP 400 as designed |
| Import | `backend/app/services/import_service.py:180`: suffix and size checks, bounded read, ephemeral sanitized `event.ben`, provider registry | BEN provider selected; filename does not select a binary layout |
| Provider | `backend/app/providers/ben/provider.py`: `load_with_provenance` calls `parse_ben_file`, then normalizer | Stops inside parser |
| Signature/header | `parser.py:154`, `layout.py`: family `01 00 04 00`; supported layout `2a ff 03 00 6e 00 ca 00`, generation `06 ff`; 0xDC-byte fixed header | Family matches; layout and generation do not |
| Configuration | `reader.py`, `parser.py:250`: little-endian typed sections, marker `0xFFFF`, explicit lengths; record sections have count and exact fixed-size entries | Older configuration does not use this framing at 0xDC |
| Class | `parser.py:281`: only 1006 / `Fast SubBen` and 1007 / `Slow SubBen`, header flag and repeated facts cross-checked | Not reached; the text `SubBen 1` occurs in this file instead |
| Channel metadata | Analog 0x0514 / 52-byte entries; physical digital 0x0515 / 18; calculated 0x0516 / 164; derived triggers 0x0578 / 210; exported binary 0x0579 / 86; names in separate string sections | No validated mapping of the older descriptors to these structures |
| Identity and scaling | Channel IDs link names, bays, descriptors and sample slots; f32 scale/offset and ratings; metadata unit/phase codes, not filename/name guesses | Older links, scales, units and ratings remain unvalidated |
| Container/map | `parser.py:345`: 0x03E8 container; 0x4E21 summary repeats header facts; 0x4E25 entries give channel ID, word index, bit and kind; 0x07D0 data tag | This supported structure cannot be established in the older configuration |
| Payload boundary | `parser.py:392`: `data_offset + count * (2 * words_per_sample) == file_size`; reject truncation and trailing bytes | Cannot derive a validated data offset using the current layout walker |
| Waveforms | Big-endian unsigned 16-bit sample matrix; analog values reinterpret words as signed int16; `scale * raw + offset`; binary bits LSB-indexed, active-low | Not reached; applying these rules to BEN5K without an oracle is unverified |
| Missing data | Slow calculated raw -32768 becomes NaN; sampled analog -32768 stays a value with a diagnostic; raw -1 is not globally treated as missing | No BEN5K missing-value rule proven |
| Conversion | `normalize.py:60`: `BenRecord` -> engineering-value DataFrame and existing `DisturbanceRecord`; trim/deduplicate names, preserve source identity in provenance | No normalized record produced |
| Time/frequency | Supported family uses aware UTC, start = trigger - pre/rate; nominal frequency supplied by integration, default 50 Hz with provenance | Older-family time basis must be verified before normalization |
| Workspace/display | Metadata + `ActiveSource`, shared `prepare_workspace_source`; ordinary analog range and digital transition APIs; frontend plots existing normalized contract | No source registered, so chart handling is never reached |
| Error display | `_classify_ben_error` at import-service line 235 maps to `unsupported_ben_variant`; frontend displays the safe API message | Matches observed API behavior; frontend reviewed statically, no live browser run |

Support is a validated binary layout family, not a promise to accept every file
produced by a product named BEN32. Existing evidence comes from BEN32 3.8.9.6
SubBen recordings; other layouts/classes remain rejected.

## Actual file structure versus assumptions

The first 16 bytes are:

```text
01 00 04 00 28 ff 03 00 6e 00 ca 00 2e 07 05 00
```

| Offset | Observed bytes/value | Interpretation and confidence |
|---|---|---|
| 0x00 | `01 00 04 00` | Confirmed BEN family signature |
| 0x04 | `28 ff 03 00 6e 00 ca 00` | Confirmed mismatch with supported `2a ff …`; matches documented unsupported family |
| 0x0C | `2e 07` -> 1838 | Raw little-endian value; recorder-ID interpretation consistent with shared header |
| 0x0E | `05 00` | Confirmed generation-marker mismatch with `06 ff` |
| 0x10 | `GPTH 275kV - BEN5K` | Confirmed embedded station text; BEN5K identification is not based on filename alone |
| 0x38 | 2025 | Raw u32 at existing record-number offset |
| 0x3C | 0 | Raw class flag; consistent with Fast under existing header interpretation, not proof of supported class 1006 |
| 0x54 | 5,000,000 | Existing rate rule would give 5,000 samples/s |
| 0x58 | 2,500 | Existing rule would give 0.5 s pre-trigger |
| 0x5C | 8,262 | Existing sample-count interpretation |
| 0x60 | 97 | Existing rule would give 97 words / 194 bytes per sample; this is **not an analog-channel count** |
| 0x64 | `7e 0a 10 12 03 0e 35 36 00` | Shared date/fraction encoding would give 2026-10-16 18:03:14.535400; timezone is not established by these bytes |
| 0x7A | 8,261 | Consistent with count minus one |
| 0xDC | `18 00 7d 0c 07 17 03 2e …` | Does not start a supported typed section |
| 0xF8 | `SubBen 1` | Confirmed configuration text; insufficient to assign class semantics |

Read-only calls to the existing private header reader returned the above
internally consistent header facts. They are candidate older-family semantics,
not evidence that the current parser successfully supports this recording.

Calling only `_read_sections(ByteView.whole(original_bytes), [])`, independently
of the signature check, produced this second diagnostic:

```text
parser.py:258 -> reader.py:78
BenStructureError: section type 0x0018 has marker 0x0c7d, expected 0xffff (at byte offset 0xdc)
```

No bytes or parser functions were patched for that diagnostic. It demonstrates
that changing only signature acceptance cannot solve compatibility. It does
**not** prove that the old-format file is corrupt: the reader is applying the
wrong format's grammar.

Additional configuration observations:

- Feeder description strings occur at 0x12C, 0x1AD and 0x22E, separated by
  129 bytes. Digital labels at 0x73C, 0x750 and 0x764 are separated by 20 bytes.
- Analog/channel and binary labels occur throughout the configuration, e.g.
  `TBIN1 VR` at 0xBBE and binary labels at 0xC76, 0xCB0 and 0xCEA (58-byte
  spacing). These are byte/string observations, not a validated descriptor schema.
- No supported analog-section frame `14 05 ff ff`, class-section frame
  `a4 06 ff ff`, summary/map frames `21 4e ff ff` / `25 4e ff ff`, or sample
  tag bytes `d0 07` occur before the candidate payload offset below.

Under the shared-header count/stride interpretation:

```text
8,262 * 194 = 1,602,828 payload bytes
1,629,786 - 1,602,828 = 26,958 = 0x694E candidate payload offset
N / fs = 1.6524 s; last sample elapsed time = (N - 1) / fs = 1.6522 s
```

**[HYPOTHESIS]** This could describe the recording's sample region and duration.
The offset is calculated backwards from EOF, not independently obtained from an
understood configuration boundary. Thus the arithmetic does not prove framing,
absence of corruption/trailers, sample encoding, or channel mapping. No usable
engineering waveform or digital polarity was established for BEN5K.

Existing documentation reports local time for the older family. For this exact
recording, that requires validation against a same-event vendor export or other
authoritative timing evidence. Applying the supported family's UTC label would
be an unverified assumption.

## Classification and legacy comparison

- **Confirmed:** unsupported older binary layout, with an incompatible
  configuration grammar as well as different signature/generation markers.
- **Known family, not newly discovered family:** `BEN_FORMAT.md` already lists
  older BPHE / `GPTH 275.ben` examples and their explicit rejection. Matching
  discriminators do not prove every older recording has one identical schema.
- **No supported-parser defect demonstrated:** fail-closed behavior matches
  DEC-119/120 and existing accepted UAT scope.
- **Not a demonstrated frontend integration failure:** the backend reproduces
  rejection independently and no normalized data reaches the frontend.
- **Not proven malformed metadata or unsupported sample representation:** the
  layout gate prevents those stages being evaluated; later defects remain possible.
- No local `D:\Programming\powerwave` clone exists. Read-only access to its
  separate canonical GitHub remote returned `Repository not found`; a connector
  fetch of its provider source also returned 404. Current legacy support could
  not be verified, and the recording was not run through that application.
  Historical discovery/handoff describe COMTRADE/CSV/Excel providers and no native
  BEN parser, but that is historical evidence, not a verified current claim.

## Recommended engineering solution — proposal only

1. Obtain a vendor-generated same-event export for this recording and at least
   one more `28 ff … / 05 00` record. Prefer COMTRADE plus channel/configuration
   and digital-event output. Vendor documentation or an accessible proven legacy
   decoder can strengthen the evidence. Validate timestamps separately.
2. Document the older header, metadata grammar, channel references, sample
   framing, scaling, polarity, missing values and time basis. Derive offsets and
   counts from configuration, then independently reconcile them with EOF.
3. After owner approval, add an explicitly selected older-layout decoder behind
   the native BEN provider. Dispatch using validated byte-level structural
   signatures, not station names or filenames. Keep supported SubBen decoding
   and its validation rules intact; reject unidentified or ambiguous variants.
4. Normalize to the existing record contract only after proving the native
   interpretation. Review whether `BenRecord` needs layout/time provenance before
   reuse: its current header/time model assumes the supported UTC layout, and
   `BenProvider` currently reports a fixed `BEN32 SubBen` layout family.
5. Continue the existing import/API/frontend lifecycle. A production BEN-to-
   COMTRADE conversion fallback would conflict with DEC-119; exports should
   remain validation oracles.

Benefit: native access to older recordings with traceable engineering values.
Principal risks: wrong scale/sign, shifted channel slots, inverted binary states,
incorrect missing markers, and an eight-hour timestamp error. These risks justify
an independently validated decoder instead of relaxing the current gate.

Expected impact: additive format support, parser/provenance documentation and
tests; API shape and ordinary waveform UI can stay shared if the normalized
contract represents all proven semantics. Any necessary model/time-policy change
requires review first. Existing support remains unchanged during investigation.

## Regression tests and validation

Required before enabling the older layout:

1. SHA-256-pinned private reference entry for this file; reproducible current
   rejection baseline, then approved decoding expectations once support exists.
   Never commit the original engineering recording.
2. Independent synthetic old-layout fixtures covering variable channel counts,
   rates, pre-trigger, stride and data offsets; prove selection is independent of
   filenames/stations and distinguish unknown/mixed signatures.
3. Exact metadata, raw samples and engineering values against the same-event
   vendor oracle for **every** value channel. Prove signedness, byte order,
   calibration, units, ratios, extreme values and missing-data rules.
4. Every binary state/transition and polarity, including changing physical and
   derived indications; validate descriptor-driven mapping, duplicate names,
   sparse channels and record boundaries without relying only on constant bits.
5. Count/rate/duration checks, repeated-field consistency, truncation, trailing
   bytes, invalid references, overlaps and out-of-bounds offsets.
6. Trigger fractional seconds, time basis, UTC normalization and alignment with
   the independently validated same-event export; no copied SubBen timezone rule.
7. Upload -> ready source -> channel summaries -> analog/digital APIs -> browser
   plots; safe errors and no half-created source on rejection.
8. All existing synthetic BEN tests and every available real-reference pair,
   including sample-for-sample Fast/Slow parity, reactive power, unavailable
   Slow samples, names, provenance, timestamps and unsupported-layout rejection.
   Previously unsupported fixtures should change expectation only when their
   own variants are validated. Keep COMTRADE upload and browser regressions.

Validation performed in this investigation:

- Direct parser traceback against the original bytes.
- Independent header and section probes without byte/function mutation.
- Full API reproduction and Fast/Slow positive controls on fetched `origin/main`.
- All **87** tests passed in `test_ben_parser.py`, `test_ben_import_api.py` and
  `test_ben_fixtures.py` on the canonical temporary snapshot. Tests used the
  existing local Python environment and a fresh pytest base directory; no
  dependencies were installed. Real-reference and browser suites were not run.
- The initial working-copy API startup was blocked by the pre-existing dirty
  GRZ100 1.3.0 catalog not matching `catalog.lock.json`. The initial test attempt
  also encountered permission errors in the existing shared pytest temp
  directory. Neither issue was repaired or treated as the BEN root cause;
  isolated canonical execution removed both confounders.

No fix is implemented or approved by this report.
