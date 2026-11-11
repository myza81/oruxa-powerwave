# BEN5K exact-event COMTRADE parity specification

Date: 2026-11-10. Status: specification for the next calibration evidence stage;
not authorization to implement a calibration factor. The owner authorized only
the separate physical-channel-mapping correction. Absolute calibration remains
open under BEN5K_ENGINEERING_VALIDATION.md §6.1.

## 1. Scope and evidence identity

Use BEN32 exports of these exact originals, never another event at the station:

| Original | Size | SHA-256 | Recorder | Rate / samples / pre-trigger |
|---|---:|---|---:|---|
| 261016_175827403_Permas_Jaya.ben | 941793 | bc9f78ac3008b79308a7230f0f0a61f1e308b4bc10e16a346748e529c007ee87 | 488 | 5000 Hz / 7719 / 2500 |
| 261016_180314535_GPTH_275kV.ben | 1629786 | 55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88 | 1838 | 5000 Hz / 8262 / 2500 |

Keep owner originals/exports local and immutable; commit only manifests and
non-sensitive expectations, following the existing `ben_reference` convention.
Record SHA-256 and size of CFG, DAT and all D00..D99 segments, export software
version, operator/date, recorder firmware/configuration identity and export
options. If any event-identity gate fails, report **wrong/incomplete oracle**;
do not fit a calibration coefficient or align different events into parity.

Request full-record, all-original-channel, native-rate export without custom
gain edits, added calculations, cropping, resampling or unrecorded CT/VT
transformations. Record whether the export/view uses instantaneous/peak or
RMS-equivalent presentation, and independently capture true RMS over a stated
whole-cycle interval. Prefer binary plus ASCII exports where available; each
must describe the same samples. Archive BEN32 channel-attribute views as well.

The July GPTH CFG/DAT corroborates an encoding hypothesis; it cannot satisfy
this specification for the October events. A waveform near nominal or 1 pu is
never an event-identity or absolute-calibration oracle.

## 2. Independent reference harness

1. Independently read header dimensions and payload boundaries from original
   bytes. Permas payload starts at 15513, GPTH at 26958. Verify these against
   file size and declared frame dimensions.
2. Read each accepted physical column with scalar big-endian binary operations.
   Pin the mappings in `backend/tests/fixtures/ben/ben5k_physical_mapping.json`;
   do not ask the classifier under test to produce expected indices. Verify
   column hashes and descriptor addresses. The mapping goldens certify the
   accepted column contract, not OEM calibration or every future BEN variant.
3. Independently parse CFG and DAT framing, signedness, sample numbers, time
   multiplier, ASCII/binary format and split-file ordering. Do not compare two
   arrays produced by the same production BEN decoder.
4. Match original descriptors, recorded channels and export channels by proven
   identity (source name, phase, occurrence, recorder configuration). BEN32 may
   reorder, repeat or export inactive configured descriptors. Keep a reviewed
   inclusion/exclusion ledger; never silently equate the 27/35 recorded analog
   channels with every configured/exported channel.
5. Compare the complete provider/import/DataFrame/API path to the independent
   reference. A passing standalone decoder is insufficient.

## 3. Required parity matrix

| ID | Check | Required result and failure interpretation |
|---|---|---|
| EP-01 | Event identity, dimensions and timing | Exact source hashes; declared rate/count/pre-trigger; sample/time sequence and full coverage agree. Preserve the unverified BEN5K clock basis: no automatic UTC/+8-hour repair to manufacture agreement. |
| EP-02 | Physical channel mapping | Compare every included sample at its pinned physical slot, including all 14 Permas and 21 GPTH shifted channels, unshifted channels, duplicates/phantoms and GPTH SDAI2 IB/IN adjacent to digital words. Wrong-phase or digital-word reads fail before calibration analysis. |
| EP-03 | Raw packed-word interpretation | Record original two bytes, unsigned value, signed-16 two's-complement value, candidate measurement bits and low bits. Test positive, zero, negative and endpoints independently; a native-endian view of big-endian bytes must fail. Current mapping-only behavior remains full signed packed words until further authorization. |
| EP-04 | Bit extraction and internal flags | Establish, rather than assume, which bits are amplitude versus flags. Compare export raw words with original words and explicitly test whether low-nibble clearing, signed right shift or another mapping is required. Capture all observed low-nibble patterns. Supplemental synthetic vectors exercise all 16 patterns with identical high bits and verify digital words are not altered. Hardware-computed 16-bit channels require a separate supported contract. |
| EP-05 | Negative samples and boundaries | Validate sign extension before/after extraction, including 0xB3CF, 0xFAAF and 0xBBBF where present, plus synthetic 0x0000/0x000F/0x7FFF/0x8000/0xFFFF. Do not assume -1 or -32768 means unavailable without a BEN5K-specific oracle. |
| EP-06 | Descriptor coefficients | Read exact float32 gain at +28 and offset at +32 independently. Compare every channel with CFG a/b and document the transformation from packed measurement to exported engineering samples. Analyze the proposed √2/16 relationship as a hypothesis, not a required passing result. No multiplication/division may be added to production from this specification alone. |
| EP-07 | Offsets and operation order | These originals have zero observed offsets, so they cannot prove whether an offset is applied before/after bit extraction or an AC calibration factor. Request an OEM definition or exact nonzero-offset recording/injection. Test its additive intercept separately; do not declare the general offset contract verified from zero-offset cases. |
| EP-08 | Units | Compare descriptor ASCII units at +20 onward, BEN32 attributes, CFG units and normalized channel units, including prefixes. Verify V/kV and A/kA factors independently. Unit agreement does not establish Primary/Secondary side. A blanket label change cannot repair unproven calibration. |
| EP-09 | RMS/peak/instantaneous equivalence | Compare every instantaneous sample, min/max and sample indices, peak-to-peak, mean/DC component and independently computed cycle RMS. Separately compare BEN32 instantaneous/peak, RMS-equivalent cursor and true-RMS modes. For distorted, depressed, DC-offset or transient signals, never assume instantaneous/√2 equals true RMS. |
| EP-10 | Primary/Secondary reference | Record CFG P/S/absent marker and primary/secondary fields exactly, plus BEN32 sensor/CT/VT evidence. Distinguish a 1/1 default from a meaningful ratio. Missing BEN side remains Unknown until independent authority is established; another event's P marker cannot be copied. Compare metadata separately from values; no automatic CT/VT scaling or new side inference is authorized. |
| EP-11 | Independent nominal and display range | Compare high/low display parameters, actual winding/terminal configuration and approved system nominal separately. Neither high_range nor RMS is sufficient to assign nominal_voltage_ll_kv. Resolve the Permas 132/275 question through source-specific configuration/wiring evidence. |
| EP-12 | Shared consumers and immutability | DataFrame, source table, waveform (full resolution and envelope), cursor, callout/peak, calculated RMS/polarity/nested results and relevant Power consumers agree with the independent reference. ENG/PU switching and rejected saves do not mutate physical arrays. Original input and export hashes remain unchanged. |

## 4. Numerical acceptance

- **Raw and mapping comparisons:** exact integer equality for every included
  sample, plus full-column SHA-256 where the representation is identical. No
  approximate matching, channel phase swap, silent clipping or omitted outlier.
- **Coefficient comparisons:** preserve exact BEN float32 values and CFG
  decimal precision. Report absolute/relative coefficient differences and any
  proposed transformation. Agreement with a candidate factor is evidence, not
  automatic approval of that factor.
- **Engineering arrays:** derive the error bound from coefficient/export
  rounding and arithmetic precision. For a printed coefficient with quantum
  q_a and offset quantum q_b, the rounding component per sample is at most
  `abs(export_raw) * q_a/2 + q_b/2`, plus a separately justified arithmetic
  bound. Include source quantization only when the exporter demonstrably
  requantizes; never use a blanket one-count allowance to hide a bit error.
- **RMS/peaks:** use the same declared sample intervals. First compare oracle
  samples, then propagate their known error bounds to derived quantities.
  Report worst-case discrepancy and its channel/sample. Do not enlarge
  tolerances until a preferred factor passes.
- **Metadata:** exact semantics, with case/prefix normalization only under the
  existing shared unit contract. Side/nominal differences are reported even if
  numeric samples match. Correct calibration and PU readiness remain separate.

Keep separate verdicts for raw extraction, mapping, calibration, representation,
units, side and nominal metadata. A missing export is **not executed / blocked
on evidence**, never parity passed. If an exact oracle disproves the current
formula or a previous hypothesis, report it for owner engineering review before
changing production. Do not change expected results merely to accommodate the
decoder.

Independent nominal-context evidence is now available in the owner event
folder's `SOE PMJY.pdf`: its device identities place the recorded PLTG1, PLTG2,
PGPS1 and KTBR2 bays at 275 kV and separately identify the 132 kV bays. See the
[bounded assessment](BEN5K_PHYSICAL_MAPPING_CORRECTION.md#permas-nominal-voltage-discrepancy--bounded-assessment)
for its hash and limitations. Use this as network/bay corroboration, not a
substitute for BEN channel wiring, calibration or Primary/Secondary evidence.

## 5. Required evidence and closure

Produce the channel inclusion ledger, sample/bit comparison CSV, coefficients
and offsets table, units/reference table, RMS/peak interval table, discrepancy
inventory, file/code hashes and reproducible test command/results. Include
negative and observed flag patterns from both exact events, and distinguish
supplemental synthetic coverage from actual observed OEM behavior.

Rerun the four existing Fast/Slow SubBen COMTRADE pairs without any altered
formula or tolerance. Run native BEN dispatch, shared normalized-record,
waveform/cursor/annotation/calculated-channel/PU/Power integrations, relevant
browsers and full backend regressions after a separately authorized calibration
implementation. This stage neither changes calibration nor begins Slice 6D.
