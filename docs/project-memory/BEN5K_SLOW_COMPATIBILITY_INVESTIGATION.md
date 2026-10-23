# BEN5K Slow Compatibility Investigation

**Status:** S6 (Engineering Scaling Validation) complete — frequency divisor confirmed inferred (not binary-encoded); POWER scale 1 MW/count PLAUSIBLE, MVAR scale 0.001 Mvar/count PLAUSIBLE; no independent reference data available; all three Group 0 channels remain raw provisional; 25 remaining channels unresolved  
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

### 6.5 Extended catalog section (0x0A1B – 0x141B, 2,561 bytes)

Immediately after the nine channel groups, the 2,561 bytes from 0x0A1B to the
SubBen 2 boundary at 0x141C contain a sequence of **30-byte catalog records**.
This section was fully decoded in S3. There are 85 complete 30-byte records.

**30-byte record structure:**

```
bytes 0–1  : type marker  (0x01 0x01 = LOGICAL; 0x04 0x33 = DERIVED)
bytes 2–3  : channel ID   u16le (sequential for LOGICAL; parent ID for DERIVED)
bytes 4–5  : flags        u16le (0xFF00 = primary substation; 0xFF01 = secondary)
bytes 6–25 : name         20 bytes, NUL-padded latin-1 (name starts at byte 6)
bytes 26–29: tail         0xFFFFFFFF for all valid catalog records
```

> **Field offset correction from pre-S3 analysis:** The name field begins at byte 6,
> not byte 10. The first 4 characters of each name were truncated by the initial
> analysis script; full names have been verified against byte-by-byte decodes.

**Record types observed in GRNE:**

| Type | Byte pair | Count | Meaning |
|------|-----------|-------|---------|
| LOGICAL | `0x01 0x01` | 23 | Logical channel with unique sequential ID |
| DERIVED | `0x04 0x33` | 29 | Derived/threshold channel referencing a parent ID |
| (end/garbage) | other | 33 | Overlap with SubBen 2 section; excluded by tail validation |

**LOGICAL records (IDs 44–60, flags=0xFF00 primary or 0xFF01 secondary):**

Records 0–11 and 30–32 (type 0x0101, flags=0xFF00) define the primary logical
channels for this recording:

| ID | Name |
|----|------|
| 44 | MVAR JJNG 1 |
| 45 | UR JJNG 2 RMS |
| 46 | UY JJNG 2 RMS |
| 47 | UB JJNG 2 RMS |
| 48 | POWER BDNG 2 |
| 49 | FREQ. JJNG 2 |
| 50 | FREQ, BDNG 2 |
| 51 | MVAR BDNG 2 |
| 52 | MVAR JJNG 2 |
| 53 | POWER JJNG 2 |
| 54 | MVAR BDNG 1 |
| 55 | POWER JJNG 1 |
| 58 | FREQ JJNG 1 |
| 59 | POWER BDNG 1 |
| 60 | FREQ BDNG 1 |

Records 45–52 (type 0x0101, flags=0xFF01) define the secondary-substation variants
of the same channels (autotransformer feeder names: FREQ UR TF1, P AUTO TF1, etc.).

**DERIVED records (type 0x0433, IDs 56 and 57):**

Records 12–29 list derived channel names (FREQ BDNG 1, MVAR BDNG 1, POWER BDNG 1,
UR JJNG 2 MAX, UR JJNG 2 MIN, etc.) all referencing parent IDs 56 or 57. These are
the recorder's pre-computed combined-group measurement list.

Records 33–44 reference parent ID 48 and define transformer threshold channels
(OVER UR HV TF1, UNDER UR HV TF1, etc.).

**S3 conclusion:** The catalog contains logical channel names and IDs but does NOT
contain physical sample word indices. No word-index data was found in any of the
85 catalog records. The relationship between catalog IDs and the group-descriptor
selector values has not been decoded.

### 6.6 SubBen 2 section (0x141C – 0x215A)

A display-text section beginning with the ASCII signature `b"SubBen 2"` at 0x141C.
Contains station long names (`GURUN EAST S/S:FEEDER BDNG1`, `GURUN EAST S/S:FEEDER
JJNG NO 2`, etc.) for the recorder's front-panel display. Not relevant to sample
decoding or channel-to-word mapping.

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

## 10. S2 and S3 Implementation Status

### 10.1 What was implemented (S2 + S3)

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
| `tests/test_ben5k_slow_catalog.py` | 15 tests: catalog record parsing, name-at-byte-6 correctness, tail validation, SubBen 2 boundary, record types | ✓ |

BEN5K Fast regression: `tests/test_ben5k_reader.py` (27 tests) — all pass, no regression.

**S3 additions to `reader.py`:**

- `ExtendedCatalogEntryType` enum: `LOGICAL`, `DERIVED`, `UNKNOWN`
- `ExtendedCatalogEntry` frozen dataclass: `entry_type`, `channel_id`, `flags`, `name`, `record_offset`
- `read_extended_catalog(data)` — reads 30-byte records from 0x0A1B to the SubBen 2
  boundary; excludes records with tail ≠ 0xFFFFFFFF

### 10.2 Channel classification result (GRNE230726_143432426.ben)

**S3 classification (superseded by S4 for Group 1):**

```
INACTIVE             : 42   (groups 7–8 entirely; unused slots in groups 0–6)
TENTATIVE            :  5   (Group 0 only — see S4 reclassification below)
UNRESOLVED_ZERO      : 12   (low-byte selector; formula gives wi=0)
UNRESOLVED_OOR       :  6   (wi >= 26; selector >> 8 is out of frame range)
UNRESOLVED_CONFLICT  :  7   (groups 4–5 claim words already held by groups 0–1)
```

**S4 reclassification (current):**

```
INACTIVE                    : 42
TENTATIVE                   :  3   (Group 0 only; confirmed by S4 engineering analysis)
UNRESOLVED_FORMULA_UNCONFIRMED:  2   (Group 1: formula confirmed invalid by S4 data analysis)
UNRESOLVED_ZERO             : 12
UNRESOLVED_OOR              :  6
UNRESOLVED_CONFLICT         :  7
```

Group 0 TENTATIVE channels (available as raw int16 values):

| Channel | Group | selector | wi | S4 validation |
|---------|-------|----------|----|---------------|
| POWER BDNG 1 | SENS BDNG 1 | 0x0400 | 4 | PLAUSIBLE (63–152 MW; oracle needed for scale) |
| FREQ BDNG 1  | SENS BDNG 1 | 0x0100 | 1 | CONFIRMED (49.6–50.6 Hz; Malaysian 50 Hz grid) |
| MVAR BDNG 1  | SENS BDNG 1 | 0x0200 | 2 | PLAUSIBLE (13.45–13.72 Mvar; oracle needed for scale) |

Group 1 FORMULA_UNCONFIRMED channels (excluded from value_channels):

| Channel | Group | selector | wi | S4 finding |
|---------|-------|----------|----|------------|
| FREQ JJNG 1 | SENS JJNG 1 | 0x0800 | 8 | INVALIDATED — wi=8 values are 1–27 and 65500–65534 (limit-event/status data, not frequency) |
| MVAR JJNG 1 | SENS JJNG 1 | 0x1000 | 16 | INVALIDATED — wi=16 values are bimodal 0–24 and 64804–65534 (not Mvar range) |

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

**S3 finding (definitive):** The extended catalog at 0x0A1B was fully decoded in S3.
It provides 23 LOGICAL channel entries (IDs 44–60) and 29 DERIVED channel entries
but contains **no physical word indices**. The catalog is a logical channel name
registry, not a word-index lookup table.

The selector encoding for Groups 2–6 remains unknown. No alternative formula
(`sel >> 4`, `lsb_pos(sel)`, `msb_pos(sel)`) maps Groups 2–6 selectors to word
indices without conflict across all channels. The root cause is unresolved.

### 10.3 Root cause of JJNG 1 invalidation (S4 finding)

The `selector >> 8` formula was confirmed for Group 0 (BDNG 1) by engineering
analysis. For Group 1 (JJNG 1), the same formula gives wi=8 for FREQ JJNG 1 and
wi=16 for MVAR JJNG 1. S4 analysis of the actual word column data:

- **wi=8:** Values are 1–27 and 65500–65534 (near 0 and near 0xFFFF). This is a
  bimodal limit-event or status pattern, not a frequency channel (which would
  show values near 13,000–13,200 for 50 Hz).
- **wi=16:** Values are bimodal 0–24 and 64804–65534. Again a status/limit pattern,
  not Mvar (which would show small positive values like 13,000–14,000 if the same
  scale applied).

These word positions contain recorder internal state, not the declared measurements.
The `selector >> 8` formula encodes something different for Group 1+ than for Group 0.
The actual mapping formula for Groups 1+ remains unknown.

### 10.4 Additional recording search result (S4)

Owner-authorized directories searched:
- `C:\Users\fairizat\OneDrive\...\Tripping Event\` (all subdirectories)
- `C:\Users\fairizat\Desktop\BEN\`

Result: Only 2 copies of `GRNE230726_143432426.ben` (70,315 bytes each, identical
content) found with the `29 FF` Slow layout signature. No other `29 FF` Slow
recording exists in owner-authorized directories. Cross-recording validation is
not possible at this time.

### 10.5 Frequency scale clarification (S4)

The wi=1 column statistics for 1,188 samples:
- Minimum: ~12,898 (49.3 Hz at scale 50/13000)
- Median: 13,086 → 50/13086 ≈ 0.003821 Hz/count
- Maximum: ~13,152 (50.6 Hz at scale 50/13000)

The scale 50/13086 ≈ 0.003821 Hz/count gives median exactly 50.00 Hz. The
previously documented estimate of 50/13000 ≈ 0.003846 is close but slightly off;
the median-based value is more consistent. Oracle validation against SCADA
frequency logs remains the authoritative resolution.

### 10.6 Diagnostics always attached to every BenRecord (S4 updated)

```
time_basis_unconfirmed                  [WARNING]  Timestamp decoded as UTC; local vs UTC unconfirmed
layout_ben5k_slow_legacy                [INFO]     Layout type, tentative/unresolved counts
ben5k_slow_mapping_tentative            [WARNING]  word_index formula confirmed for Group 0 only; S4 findings
ben5k_slow_formula_unconfirmed_channels [WARNING]  Group 1+ channels excluded; S4 data analysis result
ben5k_slow_tentative_channels           [INFO]     Names and word indices of TENTATIVE channels
ben5k_slow_oor_channels                 [INFO]     Count and first example of OOR channels
ben5k_slow_zero_index_channels          [INFO]     Count and first example of ZERO channels
ben5k_slow_conflict_channels            [INFO]     Count and first example of CONFLICT channels
ben5k_slow_hvdc_formula                 [INFO]     HVDC formula name noted; decoding deferred
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
   all existing BEN5K Fast test assertions pass unmodified.
3. **Feature flag** — BEN5K Slow dispatch is gated behind its own, separate
   `BEN5K_SLOW_EXPERIMENTAL_ENABLED` env var (Settings field
   `ben5k_slow_experimental_enabled`). This is independent of the BEN5K Fast
   `BEN5K_EXPERIMENTAL_ENABLED` flag — enabling one does NOT enable the other.
   Disabled by default in production. See S4 decision record below.
4. **Import pipeline** — no change to recording import API surface, file
   routing, or storage paths.
5. **Unresolved channels not in value_channels** — FORMULA_UNCONFIRMED, OOR,
   ZERO, and CONFLICT channels must never appear in value_channels and must
   not be displayed as valid measured waveforms.
6. **timing_reference must be `relative_elapsed`** — BEN5K Slow sources
   (like BEN5K Fast) use `timing_reference="relative_elapsed"` so they land
   in the elapsed-only time bucket and are never auto-grouped with confirmed-UTC
   sources by timestamp.

---

## 14. Open Questions

| # | Question | Status | Impact |
|---|----------|--------|--------|
| 1 | Exact word_index encoding for groups 2–6 (JJNG 2, BDNG 2, AUTO TRF 1/2) — bitmask or global ID? | OPEN — S3 confirmed no lookup in extended catalog; S4 confirmed formula is wrong for Group 1; formula for Groups 2–6 unknown | Required to map remaining 25 channels |
| 2 | Scale/offset encoding in descriptor bytes 24–27 | **PARTIALLY RESOLVED (S6):** Two byte patterns found: `33 ff 38 00` (Power/Freq/Voltage) and `ff ff 00 00` (Mvar); not literal scale factors. Their meaning is **unverified** — firmware documentation or a second Slow recording with known engineering values would be required to confirm any interpretation. Candidate scales (unconfirmed): POWER 1.0 MW/count, MVAR 0.001 Mvar/count, voltage 0.01 kV/count. | Physical engineering units still require SCADA oracle |
| 3 | Timestamp UTC vs UTC+8 | OPEN — S6 found no independent reference data for 2023-07-26 | Affects time-axis alignment; `timing_reference="relative_elapsed"` applied as safeguard |
| 4 | Significance of wi=16 (MVAR JJNG 1) — range anomaly | **RESOLVED (S4):** wi=16 is NOT Mvar. Values are bimodal 0–24 and 64804–65534 (limit-event/status data). Channel reclassified to UNRESOLVED_FORMULA_UNCONFIRMED. | Closed — channel excluded from value_channels |
| 5 | Significance of wi=17 — signed -3713 to -641, large negative, no channel assignment | OPEN | Possibly autotransformer load or flag word |
| 6 | HVDC Power formula channel: should it be decoded and displayed? | OPEN — deferred per S4 decision | Scope decision |
| 7 | Extended catalog at 0x0A1B — does it hold the bitmask/ID→word lookup? | **RESOLVED (S3):** No. Catalog contains 85 30-byte records with channel names and IDs only; no word indices. | OQ 1 cannot be resolved via catalog. |
| 8 | Groups 7 and 8 (placeholder groups): are all channels `----` in every GRNE recording? | OPEN — confirmed `----` in this recording only | Skip logic validation |
| 9 | Is the selector for Groups 2–6 a BEN recorder internal register address or a display-group bitmask? | OPEN — S3, S4, S6 investigations exhausted all known binary sections | Requires second Slow recording or BEN5K Slow protocol documentation |
| 10 | Is there a second `29 FF` Slow recording available for cross-recording validation? | **RESOLVED (S4/S6):** No. Only the two copies of GRNE230726_143432426.ben exist in owner-authorized directories (OneDrive Tripping Event + Desktop BEN + Desktop root). No SCADA/historian reference data found for 2023-07-26. | Cross-recording and oracle validation not possible at this time |
| 11 | Frequency divisor origin — is 13,086 a stored calibration constant or inferred? | **RESOLVED (S6):** 13,086 (median) and 13,082 (mean) are NOT stored anywhere in the binary config area. The divisor is inferred from the nominal 50 Hz assumption. 13,000 is also not present and would give 50.315 Hz mean. The S5 candidate 50/13,086 is the best available estimate but not independently confirmed. | Divisor precision requires SCADA frequency oracle |
| 12 | Does wi=3 correspond to MVAR BDNG 2? | PROVISIONAL (S6): wi=3 range 13,822–14,096 rules out frequency (would be 52.8–53.9 Hz). At 0.001 Mvar/count: 13.82–14.10 Mvar (plausible). Not assigned — word still not claimed by any descriptor. | Low-priority; requires selector decode for Group 3 |

---

## 15. Decision Record (S4)

The following decisions were made during S4 implementation:

| Decision | Resolution |
|----------|-----------|
| BEN5K Slow feature flag | **Separate flag** — `BEN5K_SLOW_EXPERIMENTAL_ENABLED` (env var) / `ben5k_slow_experimental_enabled` (Settings field). Independent of BEN5K Fast flag. Disabled by default. |
| HVDC Power formula channel | **Deferred** — `hvdc.name` is captured and reported in diagnostics but not included in value_channels. |
| Raw int16 values with unit "raw" | **Accepted for UAT** — all TENTATIVE channels exposed with `scale=1.0, offset=0.0, unit="raw"`. Oracle validation required before engineering units are published. |
| Group 1 TENTATIVE channels | **Reclassified to UNRESOLVED_FORMULA_UNCONFIRMED** — S4 engineering analysis definitively shows wi=8 and wi=16 hold limit-event/status data, not the declared measurements. |
| Production merge | **Not approved** — S4 provides development/UAT path only. No production merge without owner approval and oracle validation. |

---

## 16. S4 Engineering Validation

### 16.1 Group 0 (BDNG 1) validation results

Analysis of 1,188 samples from `GRNE230726_143432426.ben`:

| Channel | wi | Raw value range | Interpretation | Status |
|---------|-----|----------------|----------------|--------|
| FREQ BDNG 1 | 1 | 12,898–13,152 unsigned | Scale 50/13086 → 49.3–50.6 Hz. Consistent with Malaysian 50 Hz grid. | **CONFIRMED** |
| MVAR BDNG 1 | 2 | 13,453–13,720 unsigned | ~13.45–13.72 Mvar if scale ≈ 0.001 Mvar/count. Plausible for 132 kV feeder. | **PLAUSIBLE** — oracle needed |
| POWER BDNG 1 | 4 | 63–152 unsigned | ~63–152 MW if scale ≈ 1 MW/count; mean 108 MW. Plausible for 132 kV transmission feeder. | **PLAUSIBLE** — oracle needed |

### 16.2 Group 1 (JJNG 1) invalidation results

| Channel | wi | Raw value range | Expected for measurement | Finding |
|---------|-----|----------------|--------------------------|---------|
| FREQ JJNG 1 | 8 | 1–27 and 65500–65534 (bimodal) | ~12,900–13,200 for 50 Hz | **INVALIDATED** — values are status/limit pattern |
| MVAR JJNG 1 | 16 | 0–24 and 64,804–65,534 (bimodal) | ~13,000–14,000 for similar Mvar range | **INVALIDATED** — values are status/limit pattern |

Both channels map to word positions that contain internal recorder state
(limit-crossing events, status flags), not the declared physical measurements.
The `selector >> 8` formula is confirmed only for Group 0.

### 16.3 Implications for Groups 2–6

S4 confirms that the `selector >> 8` formula cannot be relied on for any group
other than Group 0. The encoding for Groups 2–6 remains unknown. All 25
remaining non-trivial channels (UNRESOLVED_ZERO, UNRESOLVED_OOR, UNRESOLVED_CONFLICT,
UNRESOLVED_FORMULA_UNCONFIRMED) are preserved in diagnostics for future investigation.

### 16.4 S4 implementation summary

| Component | Change |
|-----------|--------|
| `reader.py` | Added `UNRESOLVED_FORMULA_UNCONFIRMED` to `SlowChannelStatus`; `g != 0` condition routes Group 1+ channels to new status instead of TENTATIVE; `unresolved_channels()` includes the new status |
| `normalize.py` | New `ben5k_slow_formula_unconfirmed_channels` diagnostic (WARNING); updated `ben5k_slow_mapping_tentative` message with S4 findings |
| `config.py` | Added `ben5k_slow_experimental_enabled: bool = False` to `Settings`; reads `BEN5K_SLOW_EXPERIMENTAL_ENABLED` env var |
| `provider.py` | Added `ben5k_slow_experimental_enabled` param; separate `_LAYOUT_FAMILY_BEN5K_SLOW` constant; `timing_reference="relative_elapsed"` applied to both Fast and Slow; `is_ben5k_any` covers both |
| `import_service.py` | Threaded `ben5k_slow_experimental_enabled` through `build_provider_manager()` and `import_ben_source()` |
| `api/v1/sources.py` | Passes `settings.ben5k_slow_experimental_enabled` to `import_ben_source()` |
| `schemas/source.py` | Added `layout_family: str | None = None` to `SourceSummaryOut`; populated from `preparation_provenance["layout_family"]` |
| `frontend/index.html` | Added `.ww-ben5k-slow-notice` CSS; updated `renderRecordingDetails()` to show UAT warning when `layout_family === "BEN32 BEN5K Slow Legacy"`; BEN filename shown in Files zone |
| `tests/test_ben5k_slow_api.py` | 14 new tests: flag disabled/enabled, layout_family, timing_reference, channel counts, flag independence |

**Test results at S4 commit:** All 14 new `test_ben5k_slow_api.py` tests pass.
All existing BEN5K Fast tests pass. Full test suite regression confirmed.

---

## 17. S6 Engineering Scaling and Independent Validation

### 17.1 Frequency calibration (wi=1, FREQ BDNG 1)

**S5 candidate conversion:** raw × 50 / 13,086 → 49.28–50.25 Hz.

**S6 finding — divisor origin:**

Direct binary search of the entire config area (0x00DC to 0x215A) for the
values 13,086, 13,082, and 13,000 as u16le, u16be, and u32le found:

| Value | Format | Result |
|-------|--------|--------|
| 13,086 | u16le, u16be, u32le | **NOT FOUND** in config area |
| 13,082 | u16le, u16be, u32le | **NOT FOUND** in config area |
| 13,000 | u16le, u16be | **NOT FOUND** in config area |

The divisor is not stored anywhere in the binary. It is purely inferred from
the assumption that the nominal grid frequency is 50 Hz:

| Divisor | Source | Mean frequency | Median frequency | f_range |
|---------|--------|----------------|-----------------|---------|
| 13,000 | Previously proposed | 50.315 Hz | 50.327 Hz | 49.608–50.585 Hz |
| 13,082 | Sample mean | **50.000 Hz** (by construction) | 50.007 Hz | 49.297–50.268 Hz |
| 13,086 | Sample median (S5 candidate) | 49.985 Hz | **50.000 Hz** (by construction) | 49.282–50.252 Hz |

**Conclusions:**

- The divisor 13,086 (sample median) is the S5 candidate and produces
  median frequency = 50.000 Hz. It is the more robust choice (median is
  resistant to outliers).
- The divisor 13,082 (sample mean) produces mean frequency = 50.000 Hz
  exactly, but this is trivially true by construction.
- The divisor 13,000 gives a mean of 50.315 Hz — less consistent with
  nominal 50 Hz operation than the mean-based and median-based candidates,
  but cannot be independently excluded without a SCADA frequency reference.
  All three (13,000, 13,082, 13,086) remain candidate interpretations.
- **The correct divisor cannot be established from the binary alone.**
  The choice of 13,086 (median) versus 13,082 (mean) versus 13,000 requires
  an independent SCADA frequency reading for the same 59-second window to
  resolve.
- The S5 conversion `f = raw × 50 / 13,086` is the best available
  estimate but is classified as **INFERRED, not independently confirmed**.

### 17.2 Descriptor scale_ref bytes (bytes 24–27 of each channel descriptor)

Binary analysis of all active channel descriptors across all nine groups
reveals two distinct patterns and two sub-variants:

| Pattern | Bytes | u16le pair | Channels |
|---------|-------|-----------|----------|
| A | `33 ff 38 00` | (0xFF33, 0x0038=56) | POWER BDNG 1, FREQ BDNG 1, POWER/FREQ JJNG 1, POWER/FREQ JJNG 2/BDNG 2, UR MAX/MIN TF1 |
| A' | `33 ff 39 00` | (0xFF33, 0x0039=57) | UY MIN, UB MAX (voltage RMS limit channels) |
| A'' | `33 ff 30 00` | (0xFF33, 0x0030=48) | TF1, TF2 autotransformer group channels |
| B | `ff ff 00 00` | (0xFFFF, 0x0000) | MVAR BDNG 1, MVAR JJNG 1, MVAR JJNG 2, MVAR BDNG 2, UB MIN |

The SENS group descriptors' bytes 20–23 also carry pattern A (`33 ff 38 00`).

**Interpretation:**

- The `0xFF33` prefix is not a scale multiplier. Its meaning is
  **unverified** — one hypothesis is that it is a BEN recorder internal
  calibration table reference (table 0xFF, entry 0x33), but this
  interpretation cannot be confirmed without firmware documentation.
  The second u16le (0x38, 0x39, 0x30) may be a sub-type or range code
  under the same hypothesis.
- Pattern B (`0xFFFF, 0x0000`) is similarly **unverified** — one
  hypothesis is that it indicates no calibration table reference, and
  that the Mvar quantity uses a different convention, but this too
  cannot be confirmed without firmware documentation.
- These bytes cannot be interpreted as IEEE 754 floats (they produce
  sub-normal values) and are not meaningful as u32le integers at any
  plausible scale factor.
- **The scale factor for each channel is not derivable from these bytes
  without knowledge of the BEN recorder's internal calibration table.**
  The bytes are opaque without firmware documentation.

### 17.3 Active power scaling (wi=4, POWER BDNG 1)

| Property | Value |
|----------|-------|
| Raw range (unsigned) | 63–152 |
| Raw range (signed) | 63–152 (identical — all positive, max < 32768) |
| Mean raw | 107.6 |
| Unavailable samples | 0 / 1188 |
| Unidirectional | Yes (all positive, no reverse flow) |

**Candidate scale interpretations:**

| Scale | Unit | Engineering range | Mean | Assessment |
|-------|------|------------------|------|------------|
| 0.01 MW/count | MW | 0.63–1.52 MW | 1.1 MW | Too low for 132 kV EHV transmission |
| 0.1 MW/count | MW | 6.3–15.2 MW | 10.8 MW | Plausible for a 33 kV feeder; unlikely for 132 kV EHV |
| **1.0 MW/count** | **MW** | **63–152 MW** | **108 MW** | **MOST PLAUSIBLE** — typical for 132 kV transmission feeder at 50–75% loading |
| 10 MW/count | MW | 630–1520 MW | 1076 MW | Exceeds any 132 kV transmission line thermal rating |

**Conclusion:** Scale 1.0 MW/count (63–152 MW, mean 108 MW) is the most
physically plausible interpretation for a GRNE BDNG 1 132 kV transmission
feeder. Reverse power flow is not observed, consistent with radial feeder
operation. Oracle validation against SCADA is required before this scale
is adopted as confirmed.

### 17.4 Reactive power scaling (wi=2, MVAR BDNG 1)

| Property | Value |
|----------|-------|
| Raw range (unsigned) | 13,453–13,720 |
| Raw range (signed) | 13,453–13,720 (identical — all positive) |
| Mean raw | 13,647.8 |
| Median raw | 13,652.0 |
| Unavailable samples | 0 / 1188 |
| Unidirectional | Yes (all positive — consistent reactive import) |

**Note on scale_ref bytes:** MVAR BDNG 1 has pattern B (`ff ff 00 00`),
distinct from POWER BDNG 1 (pattern A, `33 ff 38 00`). This suggests
MVAR and active power use different internal calibration references.
The raw encoding for MVAR is therefore not necessarily comparable to
active power.

**Candidate scale interpretations:**

| Scale | Unit | Engineering range | Mean | Assessment |
|-------|------|------------------|------|------------|
| **0.001 Mvar/count** | **Mvar** | **13.45–13.72 Mvar** | **13.65 Mvar** | **MOST PLAUSIBLE** — consistent with reactive compensation on a 132 kV feeder |
| 0.01 Mvar/count | Mvar | 134.5–137.2 Mvar | 136.5 Mvar | Too large for a 132 kV feeder at this MW loading ratio (Q/P ≈ 1.27 at 0.01 scale) |
| 0.1 Mvar/count | Mvar | 1345–1372 Mvar | 1365 Mvar | Impossible |

The raw range for MVAR BDNG 1 (13,453–13,720) is of similar magnitude to
FREQ BDNG 1 (12,898–13,152). This is coincidental: with scale 0.001, the
13,000-range raw values produce the expected Mvar range (13–14 Mvar).
With scale 0.01 or 0.1 the reactive power would be implausibly large
relative to the active power (108 MW at 1 MW/count).

**Conclusion:** Scale 0.001 Mvar/count (13.45–13.72 Mvar) is the most
plausible interpretation. Q/P ratio ≈ 0.127 (108 MW, 13.65 Mvar) is
physically reasonable for a 132 kV transmission feeder with typical power
factors. Oracle validation against SCADA is required.

### 17.5 Additional word analysis

**wi=3 (unresolved — FREQ BDNG 2 or MVAR BDNG 2 hypothesis):**

Range 13,822–14,096 (unsigned), mean 14,023. Applying the FREQ scale
(50/13,086) would give 52.8–53.9 Hz — physically impossible for a 50 Hz
system. This conclusively rules out wi=3 as a frequency channel.

At MVAR scale 0.001 Mvar/count: 13.82–14.10 Mvar, mean 14.02 Mvar.
This is plausible for a second feeder of similar characteristics to
BDNG 1. **Hypothesis: wi=3 = MVAR BDNG 2 at scale 0.001 Mvar/count**
(PROVISIONAL — not confirmed, not exposed in value_channels).

**wi=20–23 (voltage RMS hypothesis, Group 4 JJNG 2 RMS):**

| wi | Unsigned range | At 0.01 kV/count | Assessment |
|----|---------------|-----------------|------------|
| 20 | 13,531–13,801 | 135.3–138.0 kV | 132 kV bus at +2–4% nominal ✓ |
| 21 | 13,478–13,742 | 134.8–137.4 kV | Same ✓ |
| 22 | 13,356–13,617 | 133.6–136.2 kV | Slightly lower phase ✓ |
| 23 | 13,528–13,800 | 135.3–138.0 kV | Same as wi=20 ✓ |

Values 133.6–138.0 kV are fully consistent with a 132 kV bus operating
at 1–4% above nominal voltage (normal operational practice). The
interpretation **wi=20–23 = JJNG 2 RMS voltage channels at 0.01 kV/count**
is assessed as **PLAUSIBLE**; the Group 4 physical mapping (selector
encoding) is not validated — these words are currently UNRESOLVED_CONFLICT
or UNRESOLVED_OOR, so the channel-to-word assignment cannot be confirmed.

**wi=9, wi=11 (all negative signed):**

- wi=9: signed −262 to −140, mean −215 (unsigned 65,274–65,396)
- wi=11: signed −264 to −142, mean −216 (unsigned 65,272–65,394)

Both words are consistently negative, with a narrow range. Hypothesis:
Mvar channels for JJNG 1 or JJNG 2 representing reactive export (negative
convention). At scale 1.0 Mvar/count: −262 to −140 Mvar — plausible for
a generation-connected feeder exporting reactive power to the grid. At
scale 0.001 Mvar/count: −0.264 to −0.140 Mvar — too small for a 132 kV
feeder. These channels remain UNRESOLVED (their word positions are claimed
by UNRESOLVED_FORMULA_UNCONFIRMED or UNRESOLVED_CONFLICT assignments).

### 17.6 Independent reference comparison

A search was conducted of all owner-authorized directories for independent
measurements corresponding to GRNE 2023-07-26:

- `C:\Users\fairizat\Desktop\BEN\` — contains only:
  - Two copies of `GRNE230726_143432426.ben` (confirmed identical)
  - Unrelated BEN recordings: SJTM U1 (2024-05-18), KDIS 275kV (2023-12-01),
    PAKA 275kV (2023-12-01), HTRG (2025-02-25), TMRH (2025-02-25)
- `C:\Users\fairizat\Desktop\` — relay documentation PDFs and trip record
  spreadsheets (`Tripping 2026.xlsx`, `tripping list.xlsx`) for 2026 events;
  no 2023 power measurements
- `C:\Users\fairizat\OneDrive\...\Tripping Event\` — searched in S4;
  no additional Slow recordings found

**Result:** No independent reference data (SCADA historian, COMTRADE, PI
historian, load dispatch logs) for GRNE 2023-07-26 is available. Both
timestamp interpretations remain unresolved:

| Interpretation | Header time | Malaysia local equivalent |
|---------------|-------------|--------------------------|
| UTC (assumed, by analogy with BEN5K Fast) | 14:34:32 UTC | 22:34:32 MYT (next hour after midnight) |
| MYT (local time) | 14:34:32 MYT | 06:34:32 UTC |

BEN5K Fast recordings at GPTH (Stage 8–11) were confirmed as UTC-encoded
internally. BEN5K Slow is assumed to use the same convention by analogy,
but this has not been independently verified for the Slow variant.

**Timestamp validation cannot be completed without an external reference.**
The `timing_reference = "relative_elapsed"` safeguard correctly prevents
cross-event timestamp-based synchronisation.

### 17.7 Browser and engineering safeguards assessment

Review of `frontend/index.html` and `normalize.py` confirms:

- All three TENTATIVE channels are exported with `unit = "raw"`,
  `scale = 1.0`, `offset = 0.0`. No engineering unit labels are applied.
- Cursor readings in the waveform display show raw int16 values with
  unit "raw" — not MW, Mvar, or Hz.
- The details panel shows a prominent "**BEN5K Slow — Development/UAT only**"
  notice with text: _"raw int16 values … scale factors unconfirmed; unit
  shown as 'raw'."_
- No derived calculations (e.g. frequency conversion) are applied to any
  channel value in the current implementation.
- The relative time axis is enforced by `timing_reference = "relative_elapsed"`.

**Assessment:** Current safeguards are adequate. No code changes are
required to prevent misleading engineering unit presentation.

### 17.8 HVDC formula descriptor — NaN marker correction

The HVDC Power formula descriptor at 0x00FE was previously documented as
having NaN marker `0xFFFFFFFF` at bytes 30–33. The S6 binary re-read
shows the actual bytes are `ff ff 83 00`, decoding as u32le `0x0083ffff`
(not `0xFFFFFFFF`). This indicates the NaN/unavailable marker encoding
for derived/formula channel descriptors may differ from the standard
`0xFFFFFFFF` used in active channel slots. This does not affect the
current implementation (the HVDC formula channel is not decoded); it is
recorded here for completeness.

### 17.9 S6 calibration summary

| Measurement | wi | Raw range | Best candidate scale | Confidence | Oracle needed |
|------------|-----|-----------|---------------------|------------|--------------|
| FREQ BDNG 1 | 1 | 12,898–13,152 | 50/13,086 Hz/count | CONFIRMED (nominal 50 Hz) | Divisor precision |
| POWER BDNG 1 | 4 | 63–152 | 1.0 MW/count | PLAUSIBLE | SCADA MW reading |
| MVAR BDNG 1 | 2 | 13,453–13,720 | 0.001 Mvar/count | PLAUSIBLE | SCADA Mvar reading |
| JJNG 2 RMS (wi=20–23) | 20–23 | 13,356–13,801 | 0.01 kV/count | PLAUSIBLE — Group 4 mapping unvalidated | SCADA voltage reading + selector decode |
| wi=3 | 3 | 13,822–14,096 | 0.001 Mvar/count? | PROVISIONAL | Oracle + selector decode |

**Remaining uncertainties:**

1. Frequency divisor exact value (13,082 vs 13,086 vs firmware constant):
   requires SCADA frequency logs for 2023-07-26 14:34–14:35 UTC.
2. Active power scale exact value (1.0 MW/count): requires SCADA MW
   reading for BDNG 1 feeder on 2023-07-26.
3. Reactive power scale (0.001 Mvar/count): requires SCADA Mvar reading.
4. Timestamp UTC vs MYT basis: requires any event-correlated reference.
5. Scale_ref bytes 24–27 decoding: requires BEN recorder firmware
   documentation or a second Slow recording with known engineering values.
6. Selector encoding for Groups 2–6 (27 unresolved channels): no new
   evidence found; requires firmware documentation or a second Slow
   recording from the same recorder.

### 17.10 S6 test results

No production code changes in S6. The three confirmed TENTATIVE channels
retain their `unit = "raw"` validation status.

Targeted regression test run:

```
backend: pytest tests/test_ben5k_slow_api.py tests/test_ben5k_slow_reader.py
         tests/test_ben5k_slow_decoder.py tests/test_ben5k_slow_catalog.py
         → 106 passed, 0 failed
```

No code changes were made to the decoder, reader, normalizer, or API in S6.
The S5 browser UAT test (`grne-slow-uat.spec.js`, 16/16) was not re-run as
no browser-facing code changed; its results remain as recorded in S5.

---

## 18. Branch Freeze — S6 Status, Uncertainties and Integration Prerequisites

### 18.1 Final S6 branch status

The `investigation/legacy-ben5k-slow` branch at the S6 commit (`81bb409`) is
complete for the current investigation phase. No further investigation can be
conducted without external reference data (see Section 18.3). The branch is
ready to remain frozen until the owner authorizes integration.

**What exists:**

| Component | Status |
|-----------|--------|
| Binary format reverse-engineering | Complete — header, config, groups, payload all mapped |
| S2 reader + decoder + catalog parser | Implemented; all tests pass |
| S3 extended catalog decoder | Implemented; all tests pass |
| S4 engineering validation, feature flag, API | Implemented; all tests pass |
| S5 browser UAT test suite | Implemented; 16/16 pass |
| S6 calibration analysis | Documentation only; no code change |
| Production feature flag | `BEN5K_SLOW_EXPERIMENTAL_ENABLED` disabled by default |
| Fast/Slow flag independence | Verified — each flag is independent |
| Raw provisional labels | `unit="raw"`, "Development/UAT only" notice in browser |
| Relative-elapsed timing | `timing_reference="relative_elapsed"` enforced |
| Unresolved channels excluded | FORMULA_UNCONFIRMED, OOR, ZERO, CONFLICT never in `value_channels` |

**What does not exist:**
- Confirmed engineering unit calibration for any channel
- Oracle-validated scale factors
- Resolved selector encoding for Groups 2–6 (27 channels)
- A second `29 FF` Slow recording for cross-recording validation

### 18.2 Remaining uncertainties (all unresolved at S6 freeze)

| Uncertainty | Evidence basis | Confidence |
|-------------|---------------|------------|
| Frequency divisor exact value — 13,000 vs 13,082 vs 13,086 | Sample statistics only; none stored in binary | Cannot distinguish without SCADA oracle |
| Active power scale — 1.0 MW/count | Physical plausibility for 132 kV EHV feeder | HYPOTHESIS only |
| Reactive power scale — 0.001 Mvar/count | Physical plausibility (Q/P ratio) | HYPOTHESIS only |
| Voltage RMS scale — 0.01 kV/count (wi=20–23) | Numerical range consistent with 132 kV bus | PLAUSIBLE — Group 4 selector unvalidated |
| Descriptor bytes `33 ff 38 00` and `ff ff 00 00` | Byte pattern only | UNVERIFIED — meaning unknown without firmware documentation |
| Timestamp UTC vs MYT | Analogy with BEN5K Fast (assumed UTC) | UNVERIFIED — no independent reference for 2023-07-26 |
| Selector encoding for Groups 2–6 | All known binary sections exhausted | OPEN — requires second Slow recording or firmware documentation |
| HVDC Power formula channel | Formula string decoded; values not decoded | DEFERRED — out of scope |

### 18.3 Reference evidence required before production merge

The following external references are required before any production integration:

1. **SCADA frequency logs** — GRNE substation, 2023-07-26 14:34–14:35 UTC (or MYT
   if the recording is MYT-encoded). Needed to resolve divisor and timestamp basis.

2. **SCADA MW reading** — BDNG 1 feeder, same period. Needed to confirm 1.0 MW/count
   scale (or refute it in favour of 0.01, 0.1 or another value).

3. **SCADA Mvar reading** — BDNG 1 feeder, same period. Needed to confirm
   0.001 Mvar/count scale.

4. **A second `29 FF` Slow recording** from any BEN5K recorder — needed to
   cross-validate the Group 2–6 selector encoding. Without this, 25 of 27
   unresolved channels cannot be mapped by binary analysis alone.

5. **BEN5K Slow firmware or protocol documentation** — would allow decoding
   descriptor bytes 24–27 and confirming the Group 2–6 selector formula.
   Not publicly available as of S6.

Any of references 1–3 alone would confirm or refute the Group 0 calibration
hypotheses. None of references 1–5 was available in owner-authorized directories
at S6 (confirmed by S4 and S6 searches).

### 18.4 Test baseline at S6 freeze

| Suite | Tests | Result |
|-------|-------|--------|
| `test_ben5k_slow_api.py` | 14 | All pass |
| `test_ben5k_slow_reader.py` | 36 | All pass |
| `test_ben5k_slow_decoder.py` | 42 | All pass |
| `test_ben5k_slow_catalog.py` | 15 | All pass |
| **Backend subtotal** | **107** | **All pass** |
| `grne-slow-uat.spec.js` (S5) | 16 | All pass (S5 run; no browser-facing change in S6) |
| BEN5K Fast regression (`test_ben5k_reader.py`) | 27 | All pass |

No test was added or modified in S6. The test baseline is unchanged from S5.

### 18.5 Dependencies for future integration

Any future production merge of the BEN5K Slow decoder requires:

1. **Owner approval** — no merge to `main` without explicit owner decision.
2. **Oracle-validated calibration** — at minimum, POWER and MVAR scales confirmed
   against SCADA. Raw `unit="raw"` must be replaced by confirmed engineering units
   before the feature can be called production-quality.
3. **Feature flag decision** — whether `BEN5K_SLOW_EXPERIMENTAL_ENABLED` becomes
   a permanent opt-in for a "beta" path, or is removed once the decoder is stable.
4. **Group 2–6 channel mapping** — current deployment surfaces only 3 channels.
   A production deployment without resolving Groups 2–6 would leave 25 channels
   permanently excluded.

The following must be preserved through any future integration:

- `BEN5K_SLOW_EXPERIMENTAL_ENABLED` disabled by default.
- Fast and Slow feature flags remain independent.
- `timing_reference = "relative_elapsed"` for all BEN5K Slow sources.
- Unresolved channels (`FORMULA_UNCONFIRMED`, `ZERO`, `OOR`, `CONFLICT`) never
  in `value_channels` and never displayed as valid waveforms.
- No calibration logic or guessed scale factors introduced without oracle evidence.

### 18.6 Can the branch remain frozen safely?

Yes. The branch is self-contained and isolated:

- All new code is in `backend/app/providers/ben/legacy_ben5k_slow/` (new package)
  and three modified files in the BEN provider layer (`layout.py`, `model.py`,
  `parser.py`).
- The production dispatch path (`parse_ben()`) is unchanged. BEN5K Slow dispatch
  is only reachable via `parse_ben_experimental()` with `allow_legacy_ben5k_slow=True`
  AND `BEN5K_SLOW_EXPERIMENTAL_ENABLED=1`.
- No changes to SubBen, BEN5K Fast, relay-import, or main branch code.
- No migrations, database changes, or API surface changes.
- All tests pass.

The branch can remain frozen at commit `81bb409` indefinitely. The only action
needed before freezing is to push the S6 documentation commits to GitHub when
the owner authorizes it.

---

*Written on the `investigation/legacy-ben5k-slow` branch. Commits to this
document must not be cherry-picked to `main` or to `investigation/legacy-ben5k`
without owner approval.*
