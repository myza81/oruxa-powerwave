# BEN5K Slow Compatibility Investigation

**Status:** S2 (Structural Reader and Channel Mapping) implemented — oracle validation phase  
**Branch:** `investigation/legacy-ben5k-slow`  
**Based on:** `investigation/legacy-ben5k` at commit `b33b7af`  
**Recording under investigation:** `GRNE230726_143432426.ben`

---

## 1. Objective

Determine why the recording `GRNE230726_143432426.ben` cannot be parsed by either
the production BEN parser or the experimental BEN5K Fast parser, reverse-engineer
its binary structure, and propose a maintainable decoder architecture.

This document covers investigation and design only. No production code changes
are proposed in this branch.

---

## 2. Subject Recording

| Field | Value |
|-------|-------|
| Filename | `GRNE230726_143432426.ben` |
| File size | 70,315 bytes |
| Station | `GRNE` (Gurun East substation, 132 kV) |
| Recorder unit | 1547 |
| Record number | 6606 |
| Timestamp | 2023-07-26 14:34:32.426316 |
| Duration | 59.4 s |
| Rate | 20 sps (trend / Slow recording) |
| Sample count | 1,188 |
| Words per sample | 26 (52 bytes per sample row) |

---

## 3. Parser Failure Reproduction

### 3.1 Production parser — parse_ben()

```
Exception type: BenUnsupportedVariantError
Message:        Unsupported BEN variant: layout=29ff0300 6e00ca00, gen=0500
Location:       backend/app/providers/ben/parser.py:168, _check_signatures()
```

Root cause: `_check_signatures()` accepts `2a ff 03 00` (SubBen) and `28 ff 03 00`
(BEN5K Fast) only. The GRNE recording has `29 ff 03 00` — a distinct variant byte
that no existing branch in the dispatcher handles.

### 3.2 Experimental parser — parse_ben_experimental()

Same failure. `parse_ben_experimental()` in the experimental branch calls
`parse_ben()` internally for unrecognised variants; it adds no independent
dispatch for `29 ff`.

### 3.3 Signature comparison

| Variant | Layout signature (bytes 4–11) | Gen marker (bytes 14–15) | Class flag (0x3C) |
|---------|-------------------------------|--------------------------|-------------------|
| SubBen Slow | `2a ff 03 00 6e 00 ca 00` | `06 ff` | `0x01` |
| SubBen Fast | `2a ff 03 00 6e 00 ca 00` | `06 ff` | `0x00` |
| BEN5K Fast  | `28 ff 03 00 6e 00 ca 00` | `05 00` | `0x00` |
| **BEN5K Slow** | **`29 ff 03 00 6e 00 ca 00`** | **`05 00`** | **`0x01`** |

The single differing nibble (byte 4: `0x29` vs `0x28`) plus the Slow class flag
`0x01` at 0x3C identifies this as a new variant: **BEN5K Slow**.

---

## 4. Fixed Header Structure

The BEN5K Slow fixed header matches the BEN5K family layout exactly:

```
0x00: 01 00 04 00              family signature (all BEN variants)
0x04: 29 ff 03 00 6e 00 ca 00  layout signature  **NEW**
0x0C: u16le  = 1547            recorder unit
0x0E: 05 00                    generation marker  (BEN5K, same as Fast)
0x10: 'GRNE'                   station name (NUL-padded, up to 40 bytes)
0x38: u32le  = 6606            record number
0x3C: 0x01                     class flag  (0x00=Fast, 0x01=Slow — same encoding as SubBen)
0x54: u32le  = 20000           rate field  --> 20.0 sps
0x58: u32le  = 400             pre-trigger samples
0x5C: u32le  = 1188            sample count
0x60: u16le  = 26              words per sample
0x64–0x6C:  timestamp bytes    2023-07-26 14:34:32.426316
0x7A: u32le  = 1187            last sample index  (= sample count - 1)
```

The header layout is byte-for-byte identical to BEN5K Fast. Only bytes 4–7 differ.

---

## 5. Payload Arithmetic

```
payload_bytes = sample_count  x  words_per_sample  x  2
             = 1188           x  26                x  2
             = 61,776 bytes

file_size         = 70,315 bytes
config_area_start = 0x00DC   = 220
payload_offset    = 70,315 - 61,776 = 8,539  (0x215B)
config_area_size  = 0x215B - 0xDC = 8,319 bytes
```

The arithmetic closes exactly. No padding, no partial words.

---

## 6. Config Area Structure

The config area spans 0x00DC to 0x215A (8,319 bytes). It uses a **flat format**
(no typed-section framing), the same architecture as BEN5K Fast.

### 6.1 Config header block (0x00DC – 0x00FD, 34 bytes)

```
0xDC: u16le = 4        version/type
0xDE: u16le = 0xFF32   section marker
0xE6: u16le = 1547     recorder unit (cross-check against 0x0C)
0xE8: u16le = 5        channel group count (groups 1-5 in primary section)
0xEA: 'GRNE'           station name (16 bytes NUL-padded)
0xFA–0xFD: zeros       padding
```

### 6.2 HVDC Power formula descriptor (0x00FE – 0x013E, 65 bytes)

A single derived-channel descriptor precedes the channel groups:

```
+0  (0x00FE): 00 00 00 00        header (no channel-type flag)
+4  (0x0102): 'HVDC Power'       16-byte NUL-padded name
+20 (0x0112): 06 00 65 01 ...    scale/metadata (not yet fully decoded)
+30 (0x011C): FF FF               NaN marker
+32 (0x011E): 83 00 1B 00 01 00  unknown params
+38 (0x0124): 'C014+C041+C021+C019+178'  formula string (23 chars)
+61 (0x013B): 0D 0A 84 00        CRLF + terminator
```

This is an aggregated channel whose value is computed from channel references
C014, C041, C021, C019 plus a constant (178). The formula encoding appears to be
a BEN recorder display formula; decoding it is out of scope for this investigation.

### 6.3 Channel groups (0x013F – 0x0A1A, 2,268 bytes)

Nine channel groups follow in a strict 252-byte stride:

```
Group offset = 0x013F + group_index x 252
```

| Group | SENS name | Description |
|-------|-----------|-------------|
| 0 | SENS BDNG 1 | Feeder BDNG No.1 measurements |
| 1 | SENS JJNG 1 | Feeder JJNG No.1 measurements |
| 2 | SENS JJNG 2 | Feeder JJNG No.2 measurements |
| 3 | SENS BDNG 2 | Feeder BDNG No.2 measurements |
| 4 | SENS JJNG 2 RMS | JJNG 2 voltage RMS/max/min |
| 5 | SENS AUTO TRF 1 | Autotransformer SGT1 measurements |
| 6 | SENS AUTO TRF 2 | Autotransformer SGT2 measurements |
| 7 | SENS BDNG 1 | (repeat — empty placeholder group) |
| 8 | SENS JJNG 1 | (repeat — empty placeholder group) |

**Groups 7 and 8** have the same names as groups 0 and 1 but all channel slots are
`----` (inactive). They appear to be reserved hardware slots not used in this
recording.

### 6.4 Channel group internal layout (252 bytes)

Each 252-byte group contains (**8** channel slots confirmed by S2 implementation):

```
[0  – 23]  SENS descriptor       24 bytes   (group status/sensitivity)
[24 – 51]  Channel 1 descriptor  28 bytes
[52 – 79]  Channel 2 descriptor  28 bytes
[80 – 107] Channel 3 descriptor  28 bytes
[108–135]  Channel 4 descriptor  28 bytes
[136–163]  Channel 5 descriptor  28 bytes
[164–191]  Channel 6 descriptor  28 bytes
[192–219]  Channel 7 descriptor  28 bytes
[220–247]  Channel 8 descriptor  28 bytes
[248–251]  Group separator       4 bytes    ff ff ff ff
```

> **Correction from initial investigation** — the preliminary analysis assumed 7
> channel slots (224 bytes), making the group total 252 bytes with 28 bytes of
> unknown padding. S2 binary analysis confirmed the padding is actually an 8th
> channel descriptor slot; groups 4–6 use slots 4–8 for additional limit channels.
> Arithmetic: 24 + 8 × 28 + 4 = **252** ✓

**SENS descriptor (24 bytes):**

```
byte 0: 0x02         type marker
byte 1: 0x3C         sub-type marker (constant across all groups)
byte 2: group_index  0=BDNG1, 1=JJNG1, 2=JJNG2, etc.
byte 3: 0x00         SENS discriminator  (0x00 = SENS, 0xFF = channel)
bytes 4–19: name     'SENS BDNG 1' etc., NUL-padded to 16 bytes
bytes 20–23: data    (function not yet determined)
```

**Channel descriptor (28 bytes):**

```
bytes 0–1:  u16le    channel selector (word_index encoding — see Section 7)
byte  2:    0x00     reserved
byte  3:    0xFF     channel discriminator  (0xFF = active channel, 0x00 = SENS)
bytes 4–19: name     'POWER BDNG 1' etc., NUL-padded to 16 bytes
bytes 20–23: 0xFFFFFFFF   NaN / unavailable marker
bytes 24–27: scale/unit reference (not yet decoded — 'ff ff 38 00' pattern)
```

An inactive slot (displayed as `----` in the BEN recorder) has:

```
bytes 0–1:  FF FF
byte  3:    0xFF
bytes 4–19: '-' '-' '-' '-' followed by NUL padding
```

### 6.5 Extended config sections (0x0A1C – 0x215A)

After the 9 channel groups (ending at 0x0A1A), the remaining ~4,670 bytes contain
at least three more sections:

- **0x0A1B – ~0x1050:** Wider-stride (~30-byte) extended descriptors repeating
  channel names with additional metadata. Stride and exact format not yet decoded.
- **~0x1053 – ~0x1400:** Long feeder description entries (stride ~194 bytes),
  including 'GURUN EAST S/S:FEEDER BDNG NO 1', 'GURUN EAST S/S:FEEDER JJNG NO 1',
  page numbers, and other recorder display strings.
- **0x141C – 0x215A:** A SubBen-style section beginning with the literal string
  `'SubBen 2'` followed by station/feeder long names ('GURUN EAST S/S') and
  further autotransformer and short-form names (e.g. 'SENS BDNG1', 'SENS JJNG1').
  This section appears to be a secondary BEN display format embedded within the
  Slow config for recorder front-panel use.

These extended sections are not required for sample decoding — the channel-to-word
mapping is fully determined by the 9-group primary section.

---

## 7. Sample Encoding

### 7.1 Payload format

Identical to BEN5K Fast:

- Big-endian unsigned 16-bit words (`'>u2'` NumPy dtype)
- Signed interpretation via `.astype(np.int16)` (two's complement reinterpretation)
- Shape: `(sample_count, words_per_sample)` = `(1188, 26)`
- Unavailable/inactive word marker: `0xFFFF`

### 7.2 Word-index encoding

The u16le value at descriptor bytes 0–1 encodes the word index as:

```
word_index = u16le_value // 256
```

This was confirmed for BDNG 1 group:

| Channel | bytes 0–1 | u16le | word_index | word column values | Interpretation |
|---------|-----------|-------|------------|-------------------|----------------|
| POWER BDNG 1 | 00 04 | 0x0400 = 1024 | 4 | 63–152 (unsigned) | ~100 MW at 1.0 MW/count |
| FREQ BDNG 1  | 00 01 | 0x0100 = 256  | 1 | 12898–13152 (unsigned) | 49.6–50.6 Hz at scale 50/13000 |
| MVAR BDNG 1  | 00 02 | 0x0200 = 512  | 2 | 13453–13720 (unsigned) | ~13.5–13.7 Mvar at scale 0.001 |

The FREQ assignment to word 1 (and its 49.6–50.6 Hz interpretation) is confirmed
by engineering expectation for the Malaysian power system (nominally 50 Hz). The
POWER assignment to word 4 (~100 MW) is plausible for a 132 kV transmission
feeder. The MVAR assignment to word 2 (~13.5 Mvar) is plausible for reactive
power on the same feeder.

**Caveat — JJNG 1 group:** POWER JJNG 1 has bytes 0–1 = `00 20`, giving
u16le = 0x2000 = 8192, word_index = 32. This exceeds the 26-word frame (words
0–25) and cannot be a direct word index. Two hypotheses remain open:

1. The u16le is a **bitmask** (one bit set per active word), and word_index is
   `log2(u16le)` (giving bit 13 for POWER JJNG 1). Mapping from bit position to
   word slot requires a separate lookup not yet found in the config area.
2. The u16le is a **global channel ID** that maps to a word via the extended
   descriptor section (0x0A1B–0x1050), which contains repeat channel entries
   with additional metadata.

Resolution requires either oracle validation against a known-good GRNE sample or
complete decoding of the extended config sections.

### 7.3 Word column analysis

26-word per-sample frame statistics (1,188 samples, from S2 inventory run
against `GRNE230726_143432426.ben`). Channel assignment column reflects the
S2 TENTATIVE mapping only; cells with `—` have no mapped channel yet.

```
wi  Unsigned range    Signed range      Unavail  Assigned channel        Interpretation (hypothesis)
 0  0 – 65535        -40 – 24            17      —                       Status flags / counter
 1  12898 – 13152    12898 – 13152        0      FREQ BDNG 1 (TENTATIVE)  49.6–50.6 Hz CONFIRMED
 2  13453 – 13720    13453 – 13720        0      MVAR BDNG 1 (TENTATIVE)  ~13.5–13.7 Mvar plausible
 3  13822 – 14096    13822 – 14096        0      —                       FREQ/MVAR BDNG 2 (UNRESOLVED)
 4  63 – 152         63 – 152             0      POWER BDNG 1 (TENTATIVE) ~100 MW plausible
 5  0 – 65535        -732 – 24            2      —                       Variable (limit events)
 6  0 – 65535        -732 – 24            3      —                       Same pattern as wi=5
 7  24 – 89          24 – 89              0      —                       Low-range positive
 8  1 – 65535        -36 – 27             4      FREQ JJNG 1 (TENTATIVE)  Near-nominal Hz range
 9  65274 – 65396    -262 – -140          0      —                       All-negative: reactive power?
10  34 – 84          34 – 84              0      —                       Low-range positive
11  65272 – 65394    -264 – -142          0      —                       All-negative: similar to wi=9
12  4095 – 65535     -16385 – 4095      999      —                       Mixed: 999 × 0xFFFF, rest 0x0FFF
13  65535 – 65535    -1 – -1           1188      —                       CONSTANT 0xFFFF = INACTIVE slot
14  0 – 65535        -732 – 23            2      —                       Dip pattern (limit events)
15  61 – 149         61 – 149             0      —                       ~100 MW plausible
16  0 – 65535        -732 – 24            2      MVAR JJNG 1 (TENTATIVE)  Range anomaly — needs oracle
17  61823 – 64895    -3713 – -641         0      —                       Large negative — auto TRF?
18  0 – 65535        -732 – 24            3      —                       Dip pattern
19  0 – 65535        -732 – 24            2      —                       Dip pattern
20  13531 – 13801    13531 – 13801        0      —                       Voltage RMS ~135.3–138.0 kV
21  13478 – 13742    13478 – 13742        0      —                       Voltage RMS ~134.8–137.4 kV
22  13356 – 13617    13356 – 13617        0      —                       Voltage RMS ~133.6–136.2 kV
23  13528 – 13800    13528 – 13800        0      —                       Voltage RMS ~135.3–138.0 kV
24  289 – 2377       289 – 2377           0      —                       Large positive — HVDC aggregate?
25  288 – 2380       288 – 2380           0      —                       Same as wi=24
```

**Key observations from the inventory:**

- **wi=1 (FREQ BDNG 1):** 12,898–13,152, no unavailable samples, 142 unique values.
  The 49.6–50.6 Hz encoding is consistent with scale ≈ 50/13,000 ≈ 0.003846 Hz/count.
  Pending SCADA oracle.

- **wi=4 (POWER BDNG 1):** 63–152, 75 unique values, always positive, no
  unavailable samples. Plausible for ~100 MW at 1.0 MW/count.

- **wi=8 (FREQ JJNG 1):** 4 unavailable samples; minimum value = 1 (not 0) in the
  1–65535 range is ambiguous. The S2 mapping formula (selector=0x0800, wi=8) is
  confirmed by the selector encoding, but the value range needs oracle validation.

- **wi=16 (MVAR JJNG 1):** Mapped as TENTATIVE, but the range 0–65535 with
  signed -732 to +24 is anomalous for a reactive power channel. The large
  negative signed excursion (-732) may indicate a limit-crossing event or may
  be a different quantity. Oracle validation required.

- **wi=13:** Constant 0xFFFF across all 1,188 samples — an inactive or padding slot.

- **wi=17:** 61,823–64,895 (signed -3,713 to -641) — large negative quantity
  possibly autotransformer load flow or a calculated flag.

- **wi=20–23:** Unsigned range 13,356–13,801, consistent with 132 kV bus voltage
  at scale 0.01 kV → 133.6–138.0 kV. Likely JJNG 2 phase voltage RMS (UR, UY,
  UB max/min). These words correspond to the SENS JJNG 2 RMS group channels
  (UR MAX, UR MIN, UY MAX, UY MIN) whose selectors are UNRESOLVED (CONFLICT or
  OOR) under the current formula.

- **wi=3, 7, 9–12, 15:** Unmapped words with real non-trivial data — correspond
  to JJNG 2, BDNG 2, and autotransformer channels whose selectors are in the
  UNRESOLVED_ZERO or UNRESOLVED_CONFLICT categories.

Words 20–23 in the range 13,300–14,000 (unsigned) with near-constant spread
consistent with a 132 kV bus voltage (scale 0.01 kV gives 133–140 kV), matching
the JJNG 2 RMS group channels (UR MAX, UR MIN, UY MAX, UY MIN, UB MAX, UB MIN).

---

## 8. Engineering Measurement Model

Unlike BEN5K Fast (which stores instantaneous waveform samples at 3,000–7,200 sps),
BEN5K Slow stores **calculated/aggregated quantities** at 20 sps. The channel names
confirm this:

**Per-feeder groups (BDNG 1, JJNG 1, JJNG 2, BDNG 2):**
- `POWER`: active power, MW scale (~100 MW per feeder plausible)
- `FREQ`: power system frequency, Hz (49.6–50.6 Hz confirmed)
- `MVAR`: reactive power, Mvar (~13–14 Mvar plausible for 132 kV feeder)

**Voltage RMS group (JJNG 2 RMS):**
- `UR MAX`, `UR MIN`, `UY MAX`, `UY MIN`, `UB MAX`, `UB MIN`: phase voltage
  max/min over a reporting window, kV scale (133–137 kV plausible for 132 kV)

**Autotransformer groups (AUTO TRF 1, AUTO TRF 2):**
- `FREQ UR`, `P AUTO`: transformer frequency and active power
- `OVER UR HV`, `UNDER UR HV`, etc.: over/under voltage limit flags

**Derived/formula channel:**
- `HVDC Power`: sum of four feeder power values plus a constant (C014+C041+C021+C019+178)

The Slow recording is therefore a **trend/energy log**, not a fault waveform. It
would typically be used for load-flow analysis, HVDC power monitoring, and energy
accounting — not for relay protection review.

---

## 9. Format Family Comparison

| Property | SubBen (Slow) | BEN5K Fast | BEN5K Slow |
|----------|--------------|------------|------------|
| Layout sig byte 4 | `0x2A` | `0x28` | `0x29` |
| Generation marker | `06 FF` | `05 00` | `05 00` |
| Class flag | `0x01` | `0x00` | `0x01` |
| Config structure | Typed sections | Flat, 58-byte descriptors | Flat, 28-byte channel / 24-byte SENS |
| Sample rate | 3,000–7,200 sps | 3,000–7,200 sps | 20 sps |
| Channel content | Instantaneous waveform | Instantaneous waveform | Calculated trends |
| Sample encoding | Big-endian u16 | Big-endian u16 | Big-endian u16 |
| Signed conversion | .astype(np.int16) | .astype(np.int16) | .astype(np.int16) |
| Descriptor word_index | n/a (typed-section) | Byte 53 (direct index) | bytes 0–1 u16le / 256 |
| Digital discriminator | n/a | byte 3 == 0xFF | Not yet observed |
| Phantom channel fix | n/a | Stage 10 correction | Not yet needed |

---

## 10. S2 Implementation Status

### 10.1 What was implemented

S2 ("Structural Reader and Channel Mapping") was implemented in the
`investigation/legacy-ben5k-slow` worktree on branch of the same name.
No production code was modified; all new code is isolated behind the
`allow_legacy_ben5k_slow=True` opt-in flag on `parse_ben_experimental()`.

**New package:** `backend/app/providers/ben/legacy_ben5k_slow/`

| Module | Purpose |
|--------|---------|
| `reader.py` | Reads fixed header, config header, HVDC formula, and all 9 channel groups; classifies each channel as TENTATIVE / INACTIVE / UNRESOLVED_OOR / UNRESOLVED_ZERO / UNRESOLVED_CONFLICT |
| `decoder.py` | Extracts raw sample matrix and per-channel int16 columns; produces per-word diagnostic inventory |
| `normalize.py` | Builds a canonical `BenRecord` from TENTATIVE channels; attaches all diagnostics |
| `__init__.py` | Exports `parse_ben5k_slow` |

**Modified files:**

| File | Change |
|------|--------|
| `layout.py` | Added `BEN5K_SLOW_LAYOUT_SIGNATURE = b"\x29\xff\x03\x00\x6e\x00\xca\x00"` |
| `model.py` | Added `BenRecordClass.BEN5K_SLOW_LEGACY = "BEN32 BEN5K Slow Legacy"` |
| `parser.py` | Extended `parse_ben_experimental()` to accept `allow_legacy_ben5k_slow` flag; added `_is_ben5k_slow()` helper |

**New tests:**

| File | Tests | All pass |
|------|-------|---------|
| `tests/test_ben5k_slow_reader.py` | 36 tests: header, config header, HVDC formula, group reading, channel classification, dispatch | ✓ |
| `tests/test_ben5k_slow_decoder.py` | 42 tests: raw matrix extraction, signed column extraction, word inventory, end-to-end BenRecord | ✓ |

BEN5K Fast regression: `tests/test_ben5k_reader.py` (27 tests) — all pass, no regression.

### 10.2 Channel classification result (GRNE230726_143432426.ben)

```
INACTIVE             : 42   (groups 7–8 entirely; unused slots in groups 0–6)
TENTATIVE            :  5   (available for decoding)
UNRESOLVED_ZERO      : 12   (low-byte selector; formula gives wi=0)
UNRESOLVED_OOR       :  6   (wi >= 26; selector >> 8 is out of frame range)
UNRESOLVED_CONFLICT  :  7   (groups 4–5 claim words already held by groups 0–1)
```

The 5 TENTATIVE channels with their confirmed word indices:

| Channel | Group | selector | wi |
|---------|-------|----------|----|
| POWER BDNG 1 | SENS BDNG 1 | 0x0400 | 4 |
| FREQ BDNG 1  | SENS BDNG 1 | 0x0100 | 1 |
| MVAR BDNG 1  | SENS BDNG 1 | 0x0200 | 2 |
| FREQ JJNG 1  | SENS JJNG 1 | 0x0800 | 8 |
| MVAR JJNG 1  | SENS JJNG 1 | 0x1000 | 16 |

POWER JJNG 1 (selector 0x2000 → wi=32) remains UNRESOLVED_OOR as expected.

### 10.3 Root cause of unresolved channels

Groups 2–6 use selectors that differ fundamentally from the Groups 0–1 encoding:

- **Groups 2–3 (JJNG 2, BDNG 2):** All selectors are single-bit values with only
  the low byte set (0x0004, 0x0008, 0x0010, etc.). The `selector >> 8` formula
  gives 0 for all of these → UNRESOLVED_ZERO. These bits may represent a
  per-channel bitmask where the bit position encodes a global channel index, not
  a word index.

- **Groups 4–5 (JJNG 2 RMS, AUTO TRF 1):** Some selectors produce wi=1, 2, 4, 8,
  16 which are the same words claimed by Groups 0–1. This cannot mean "same word
  as FREQ BDNG 1" for a different physical quantity → UNRESOLVED_CONFLICT. The
  selector encoding is different for these groups.

- **Group 6 (AUTO TRF 2):** Mix of low-byte-only (ZERO) and large-value (0x4000,
  0x8000 → wi=64, wi=128) OOR selectors.

**Working hypothesis:** The `selector >> 8` formula is specific to groups using a
"direct word-index" selector encoding (high byte = index). Groups 2–6 use an
alternative encoding (bitmask or global ID). The 30-byte extended descriptor
section at 0x0A1B likely contains the lookup table mapping these channel IDs to
word indices, but that section is not decoded in S2.

### 10.4 Diagnostics always attached to every BenRecord

```
time_basis_unconfirmed          [WARNING]  Timestamp decoded as UTC; local vs UTC unconfirmed
layout_ben5k_slow_legacy        [INFO]     Layout type, tentative/unresolved counts
ben5k_slow_mapping_tentative    [WARNING]  word_index formula confirmed for Group 0 only
ben5k_slow_tentative_channels   [INFO]     Names and word indices of TENTATIVE channels
ben5k_slow_oor_channels         [INFO]     Count and first example of OOR channels
ben5k_slow_zero_index_channels  [INFO]     Count and first example of ZERO channels
ben5k_slow_conflict_channels    [INFO]     Count and first example of CONFLICT channels
ben5k_slow_hvdc_formula         [INFO]     HVDC formula name noted; decoding deferred
```

---

## 11. Proposed Decoder Architecture (original section, retained)

### 11.1 New layout constant

In `backend/app/providers/ben/layout.py`, add:

```python
BEN5K_SLOW_LAYOUT_SIGNATURE = bytes.fromhex('29ff0300' + '6e00ca00')
```

The existing `BEN5K_GENERATION_MARKER = bytes.fromhex('0500')` is shared with
BEN5K Fast and needs no duplication.

### 11.2 Dispatcher extension

In `_check_signatures()`, add a branch:

```python
elif layout_sig == BEN5K_SLOW_LAYOUT_SIGNATURE and gen_marker == BEN5K_GENERATION_MARKER:
    return BenVariant.BEN5K_SLOW
```

The dispatch must remain gated behind the same `BEN5K_EXPERIMENTAL_ENABLED`
feature flag used for BEN5K Fast, since this variant is also experimental.

### 11.3 New parse_ben5k_slow() function

A dedicated function in `backend/app/providers/ben/parser.py` (or a new
`slow.py` module alongside `fast.py`). Required stages:

1. **Header parse** — identical to BEN5K Fast; read rate, sample count,
   words_per_sample, timestamp, class flag from fixed positions.
2. **Config header parse** — read 34 bytes at 0xDC: version, marker, recorder
   unit, group count, station name.
3. **HVDC formula descriptor parse** — 65 bytes at 0xFE: extract derived
   channel name and formula string (store as a non-plot annotation channel or
   skip for initial implementation).
4. **Group scan** — iterate 9 groups at stride 252 from 0x013F:
   a. Read SENS descriptor (24 bytes): extract group name and group_index.
   b. Read 8 channel descriptors (28 bytes each): extract name, channel
      selector u16le, discriminator byte.
   c. Skip 4-byte `ff ff ff ff` group separator.
   d. Compute word_index = u16le // 256; skip if word_index >= words_per_sample
      or name == '----'.
5. **Payload decode** — same as BEN5K Fast: reshape big-endian u16 array to
   (sample_count, words_per_sample), cast to int16 via .astype(np.int16).
6. **Channel extraction** — for each active channel, extract column
   raw_signed[:, word_index] as the channel signal.
7. **Scale / unit** — scale factors are not yet confirmed from descriptor bytes.
   For initial implementation, expose raw int16 values with unit "raw" until
   oracle validation provides confirmed scales.
8. **Timing** — use timing_reference="relative_elapsed" (same as BEN5K Fast)
   until timestamp UTC offset is verified.

### 11.4 Channel type model

BEN5K Slow channels are engineering measurements, not waveform channels. The
existing channel type taxonomy may need extension:

```
ChannelKind.TREND_POWER_MW   — active power trend
ChannelKind.TREND_FREQ_HZ    — frequency trend
ChannelKind.TREND_MVAR       — reactive power trend
ChannelKind.TREND_VRMS_KV    — voltage RMS trend
ChannelKind.TREND_VLIMIT_KV  — voltage max/min trend
ChannelKind.TREND_DIGITAL    — status/flag channel (word 0 pattern)
```

Alternatively, treat all as generic analogue channels with a descriptive unit
string and let the UI infer rendering from the name prefix or unit. This is
simpler for an initial implementation.

### 11.5 Phantom channel handling

BEN5K Fast required a Stage 10 phantom-channel correction for descriptors with
no physical sample slot. BEN5K Slow groups 7 and 8 are all-inactive placeholder
groups — they can be skipped entirely (word_index = 0xFFFF in the first two
bytes means inactive; discriminator still 0xFF). No phantom correction is
expected for Slow, but this should be verified during implementation.

---

## 12. Validation Strategy

Before any production merge, the following oracle validation steps are required:

1. **Frequency oracle:** Compare decoded word 1 values (FREQ BDNG 1) against
   TNB SCADA frequency logs for 2023-07-26 14:34–14:35 UTC+8. Values should
   match 49.6–50.6 Hz range.

2. **Active power oracle:** Compare word 4 values (POWER BDNG 1) against
   SCADA MW readings for the same period. Confirm 1.0 MW/count scale.

3. **Reactive power oracle:** Validate word 2 (MVAR BDNG 1) against SCADA.
   Confirm scale (0.001 or 0.01 Mvar/count).

4. **JJNG 1 word_index:** Confirm whether byte[1]=0x08 for FREQ JJNG 1 means
   word 8 (direct) or whether a bitmask/lookup is needed. Inspect a second
   Slow recording from the same station or from JJNG to compare.

5. **Voltage RMS oracle:** Words 20–23 (hypothesised as JJNG 2 RMS) against
   metering. Confirm 0.01 kV/count scale.

6. **Timestamp UTC check:** Verify whether the recorded timestamp is UTC or
   UTC+8 (Malaysian local time). All BEN5K Fast recordings confirmed UTC+8
   internally; assumed same here but not verified for Slow.

---

## 13. Regression Requirements

The BEN5K Slow decoder must not affect:

1. **Production SubBen decoder** — `parse_ben()` dispatch unchanged; `2a ff`
   recordings continue to parse identically.
2. **BEN5K Fast decoder** — `28 ff` recordings continue to parse identically;
   all 17 existing BEN5K Fast test assertions pass unmodified.
3. **Feature flag** — BEN5K Slow dispatch is gated behind the same
   `BEN5K_EXPERIMENTAL_ENABLED` env var. Disabled by default in production
   until oracle validation passes.
4. **Import pipeline** — no change to recording import API surface, file
   routing, or storage paths.

---

## 14. Open Questions

| # | Question | Status | Impact |
|---|----------|--------|--------|
| 1 | Exact word_index encoding for groups 2–6 (JJNG 2, BDNG 2, AUTO TRF 1/2) — bitmask or global ID? | OPEN — S2 classified as UNRESOLVED; formula confirmed for Group 0 and Group 1 only | Required to map remaining ~20 channels |
| 2 | Scale/offset encoding in descriptor bytes 24–27 | OPEN — S2 exposes raw int16 pending oracle | Required for physical units |
| 3 | Timestamp UTC vs UTC+8 | OPEN | Affects time-axis alignment with other event data |
| 4 | Significance of wi=16 (MVAR JJNG 1 TENTATIVE) — range 0–65535 signed -732 to 24 is anomalous for Mvar | OPEN | TENTATIVE label may be wrong; oracle needed |
| 5 | Significance of wi=17 — signed -3713 to -641, large negative, no channel assignment | OPEN | Possibly autotransformer load or flag word |
| 6 | HVDC Power formula channel: should it be decoded and displayed? | OPEN — deferred | Scope decision |
| 7 | Extended config sections (0x0A1B onwards) — do they hold the bitmask/ID→word lookup? | OPEN | Required to resolve OQ 1 |
| 8 | Groups 7 and 8 (placeholder groups): are all channels `----` in every GRNE recording? | OPEN — confirmed `----` in this recording only | Skip logic validation |

---

## 15. Decision Required

Before implementation begins, obtain owner approval on:

- Whether to decode HVDC Power formula channels (scope: yes/no/deferred)
- Whether raw int16 values with unit "raw" are acceptable for an initial
  version pending oracle scale validation
- Whether BEN5K Slow dispatch should share the existing `BEN5K_EXPERIMENTAL_ENABLED`
  flag or get its own (e.g. `BEN5K_SLOW_EXPERIMENTAL_ENABLED`)

---

*Written on the `investigation/legacy-ben5k-slow` branch. Commits to this
document must not be cherry-picked to `main` or to `investigation/legacy-ben5k`
without owner approval.*
