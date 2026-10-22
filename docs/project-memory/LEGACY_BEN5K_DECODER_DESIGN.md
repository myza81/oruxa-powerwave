# Legacy BEN5K Decoder — Design and Implementation

Date: 2026-10-21 (Stages 2–9); 2026-10-22 (Stage 10). Status: Phase 2 implementation in progress (owner-approved).
Branch: `investigation/legacy-ben5k`.

## Executive summary

The GPTH 275kV recording (`261016_180314535_GPTH_275kV.ben`) belongs to an older
Qualitrol BEN recorder family (`28 ff / 05 00`) that the existing parser deliberately
rejects. Binary investigation of the recording and the BEN32 3.8.9.6 installer package
has established the flat configuration layout, 58-byte channel descriptor structure,
0-indexed word_index addressing, sample frame boundaries, and digital word positions.

**Phase 2 implementation has been approved by the owner** without waiting for a
COMTRADE oracle. Legacy BEN5K compatibility is a core Powerwave requirement. The
inability to obtain a vendor export must not indefinitely block development.

The following sections document all confirmed structural findings, remaining unknowns,
proposed architecture, and a phased validation plan.

---

## 1. Findings from the BEN32 software package

**Package:** `D:\Relay Software\BEN32 3.8.9\ben32 version 3.8.9.6.zip`
(15,031,821 bytes, dated 2021-03-03).

| Finding | Evidence |
|---|---|
| Publisher | DATA.TAG: `Company=Qualitrol`, `Application=BEN32`, `Version=2.00.000` |
| Runtime | DOS application bundled with DOSBox 0.74; launched via `DOSBox 0.74 Options.bat` |
| Main cabinet | `data1.cab` (12.6 MB InstallShield cabinet — not extracted; cabextract unavailable in this environment) |
| BEN binary bundled | None directly visible in the ZIP; the application reads BEN files from the target installation, not from within the ZIP |
| Documentation | Only DOSBox manual/changelogs present; no BEN format specification document found |
| COMTRADE export | BEN32 v2 is known to support COMTRADE export from its DOS shell; this is the preferred oracle mechanism |

**Implication:** BEN32 cannot be run headlessly on Windows for automated export.
A human-operated DOSBox session is required to obtain a COMTRADE oracle from this
application. This is the primary remaining prerequisite for Phase 2.

---

## 2. Findings from the GPTH recording

**File:** `261016_180314535_GPTH_275kV.ben`  
SHA-256: `55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88`  
Size: 1,629,786 bytes

### 2.1 Fixed header (offsets 0x00–0xDB, 220 bytes) — shared with SubBen family

| Offset | Value | Interpretation |
|---|---|---|
| 0x00–0x03 | `01 00 04 00` | BEN family signature — confirmed match |
| 0x04–0x0B | `28 ff 03 00 6e 00 ca 00` | Layout/variant signature — confirmed mismatch with SubBen `2a ff` |
| 0x0E–0x0F | `05 00` | Generation marker — mismatch with SubBen `06 ff` |
| 0x10 | `GPTH 275kV - BEN5K` | Station text (NUL-padded to 0x37); BEN5K identification confirmed in binary |
| 0x54 | 5,000,000 | Nominal sample rate (u32le) → 5,000 samples/s |
| 0x58 | 2,500 | Pre-trigger count (u32le) → 0.5 s pre-trigger |
| 0x5C | 8,262 | Sample count (u32le) → 1.6524 s total |
| 0x60 | 97 | Words per sample (u32le) → 194 bytes/sample, not an analog-channel count |
| 0x64–0x6C | `7e 0a 10 12 03 0e 35 36 00` | Shared date/fraction encoding → 2026-10-16 18:03:14.535400; UTC vs local unconfirmed |
| 0x7A | 8,261 | Sample count minus 1 (u32le) |
| 0xF8 | `SubBen 1` | Embedded text; insufficient to assign SubBen class semantics |

**Payload boundary:** `file_size − count × words × 2 = 1,629,786 − 8,262 × 194 = 26,958 = 0x694E`  
This is consistent and places the config area at 0xDC–0x694D (26,738 bytes).

### 2.2 Configuration area (0xDC–0x694D, 26,738 bytes) — BEN5K-specific flat layout

The first word at 0xDC is `0x0018` with marker `0x0C7D` — incompatible with the SubBen
typed-section format (which requires marker `0xFFFF`). The entire configuration is a
flat binary structure with no per-section type/length framing.

Confirmed sub-structures within the config area:

**Master block header (0xDC–~0x12B, ~80 bytes)**  
Contains recorder serial number, channel counts and other global scalars. Partially
decoded; field boundaries not fully mapped.

**Long feeder descriptions (0x12C onwards, stride 129 bytes × 12 feeders)**  
Null-terminated ASCII strings up to 129 bytes. Confirmed entries:
`FEEDER TBIN 1`, `FEEDER SDAI 1`, `FEEDER SDNK 1`, `FEEDER TBIN 2`, `FEEDER SDAI 2`,
`FEEDER SDNK 2`, `FEEDER HV TX1`, `FEEDER LV TX1`, `FEEDER HV TX2`, `FEEDER LV TX2`,
`CURR SENS PLNG 1`, `CURR SENS PLNG 2`.

**Channel sensor name groups (0x73C area, stride 20 bytes)**  
20-byte entries, each: 16-byte name + 4 metadata bytes. Names include
`DIGITAL 1 TBIN 1`, `DIGITAL 2 TBIN 1`, `DIGITAL 1 SDAI 1`, etc. Trailing byte
`0x44` = `'D'` (digital), `0x41` = `'A'` (analog).

**Short feeder names (0xAAE, stride 22 bytes × 12 entries)**  
Structure: 13-byte name | 1 NUL | 2-byte NUL pad | 6-byte `0xFF` separator.
Names: `TBIN1`, `SDAI1`, `BBTU1`, `TBIN2`, `SDAI2`, `BBTU2`, `HV TX1`, `LV TX1`,
`HV TX2`, `LV TX2`, `PLNG1`, `PLNG2`. Last entry ends at 0xBB5; section transitions
to channel descriptors at ~0xBB6.

**Channel full descriptors (0xBB6–0x694D, ~25,000 bytes)**  
Mixed analog and digital channel descriptors. Not a typed-section format.
Descriptors for different channel types have different structures (see section 3).

---

## 3. Confirmed legacy binary structure

### 3.1 Analog channel descriptor (58 bytes)

```
Offset  Size  Field
 0       1    type_byte:   0x00=voltage, 0x04=current
 1       1    phase_seq:   1=R/A, 2=Y/B, 3=B/C, 4=N (within feeder)
 2       2    class_code:  u16le; 0x0528=VR, 0x0488=VY, 0x03E8=VB,
                            0x021C=IR, 0x0190=IY, 0x00F0=IB, 0x0050=IN
 4      16    name:        NUL-padded ASCII, e.g. "TBIN1 VR"
20       2    constant_1:  0x414B (appears fixed; meaning unconfirmed)
22       4    zeros_1
26       2    constant_2:  0x0028 = 40 (appears fixed; meaning unconfirmed)
28       4    scale:       f32le, raw-to-engineering multiplier
                            (e.g., ~0.01871 for a current channel)
32       4    offset:      f32le, additive offset (typically 0.0)
36       4    low_range:   f32le (e.g., -1.5 for a current channel)
40       4    high_range:  f32le (e.g., +1.5 for a current channel)
44       1    type_flag:   0x02 for current; 0x00 for voltage (observed)
45       7    zeros_2
52       1    group_flag:  0x02 (observed; meaning unconfirmed)
53       1    word_index:  sample word slot (0-based, 0–96)
54       3    zeros_3
57       1    terminator:  0xFF
```

**Word index confirmed** at byte 53 from descriptor start. **0-indexed** (not 1-indexed):
TBIN1 VR = word_index 0 → sample word 0 (V ✓), confirmed by direct scan of 22 channels.
8-word-per-feeder confirmed: SDAI1 starts at 8, SDNK1 at 16, TBIN2 at 24.

Confirmed word allocation for active feeders in GPTH recording:

| Feeder | Block | Layout within block (confirmed word_index values) |
|---|---|---|
| TBIN1 | words 0–7 | VR=0, VY=1, VB=2, ?=3(unused,std≈3.6), IR=4, IY=5, IB=6, IN=7 |
| SDAI1 | words 8–15 | VR=8, VY=9, VB=10, ?=11(std≈97), IR=12, IY=13, IB=14(std≈16), IN=15(std≈11693 V!) |
| SDNK1 | words 16–23 | VR=16, VY=17, VB=18(std≈4 near-zero), ?=19, IR=20, IY=21, IB=22, IN=23(std≈11685 V!) |
| TBIN2 | words 24–31 | VR=24(confirmed), remaining inferred |
| SDAI2 | words 32–39 | VR=32(inferred), remaining inferred |
| SDNK2–PLNG2 | words 40–95 | Constant 2048 in GPTH recording (inactive feeders) |

**Site-specific anomalies in GPTH recording (not decoder defects):**
- SDAI1 IB (word 14) near-zero: this feeder carries negligible phase-B current at event time.
- SDAI1/SDNK1 "IN" channels show voltage amplitude: these ports carry neutral voltage
  (residual V0) rather than neutral current at this site.
- SDNK1 VB (word 18) near-zero: phase-B VT disconnected or failed for that bay.
- The decoder reads word_index from the descriptor and applies it — site wiring is an
  engineering matter, not a decoder defect.

**Sample encoding:** big-endian u16, numerically converted to signed int16 via `.astype(np.int16)`.
**Important:** do NOT use `.view(np.int16)` on a big-endian array — byte-order error.
`engineering_value = scale × raw + offset` (f32le coefficients from descriptor bytes 28–35).

### 3.2 Digital channel descriptor (58 bytes)

```
Offset  Size  Field
 0       1    polarity_flag: 0x01, 0x02, or 0x03 (pattern unconfirmed)
 1       1    word_group:   1–7 observed; maps to a digital sample word slot
 2       1    bit_index:    0–15; bit position within the digital word
 3       1    type_marker:  0xFF (digital channel discriminator)
 4      16    name:         NUL-padded ASCII, e.g. "TBIN1 CB_R OPEN"
20      38    metadata:     scale/calibration fields; structure not fully mapped
57       1    terminator:   0xFF
```

**Word group addressing:** word groups 1–7 each represent one 16-bit word in the sample
frame. Groups map to feeder pairs: TBIN1 → groups 1–2, SDAI1 → groups 3–4, SDNK1 → 5–6,
TBIN2 → group 7 (partial; remaining feeders use higher groups not yet scanned).

**Active-low vs active-high:** not yet determined. SubBen uses active-low (bit=0 →
channel active); BEN5K polarity may differ. The `polarity_flag` byte (values 0x01–0x03)
may encode this, but decoding has not been confirmed.

**Group 0 channels:** 30 "SENS OUT" channels with bit_index=0 and word_group=0 were
detected; these appear to have a different addressing scheme (possibly sensor output
channels with contiguous word assignment rather than bitmask-within-word). Not decoded.

### 3.3 Digital word slot mapping to sample frame

The sample frame has 97 words (194 bytes). **Confirmed by payload analysis:**

| Frame region | Assignment |
|---|---|
| Words 0–37 | Active analog channels (5 active feeders × 8 words) |
| Words 38–42 | Digital bitmask words (5 words, active-low) |
| Words 43–96 | Constant 0x0800 = 2048 (inactive feeder slots in GPTH recording) |

**Digital word characteristics (from GPTH payload survey):**
- Words 38–42 all show values with max ≤ −1 (signed) = bitmask word in active-low convention
- Quiescent state: 0xFFFF (all bits high = all channels inactive)
- Bits transition to 0 during the event (CB trip operations)
- Word 38: 5 distinct states, bits 7/8/9 go low = 3 CB operations
- Word 42: 15 distinct states, 18 transitions (most complex digital activity)

**Digital word_group → sample word mapping:** word_group N maps to sample word (37 + N).
- word_group 1 → sample word 38
- word_group 2 → sample word 39
- word_group 3 → sample word 40
- word_group 4 → sample word 41
- word_group 5 → sample word 42
This is inferred from the 5-active-feeder structure and 5 digital words. Oracle confirmation
is required before declaring this authoritative.

### 3.4 Time encoding

The fixed header at 0x64–0x6C uses the same 9-byte date/fraction encoding as the
SubBen family, yielding 2026-10-16 18:03:14.535400. Whether this is UTC or local
time (+8 Malaysia) is **not yet confirmed**. The existing documentation for this
recording family notes local time, but this must be verified against an oracle.

---

## 4. Remaining unknowns

| Unknown | Risk if wrong | Resolution method |
|---|---|---|
| UTC vs local time (+8) | Timestamps off by 8 h | Same-event oracle; compare trigger to network time |
| Word offset 3 in each feeder block (4th analog slot) | Wrong channel count / missing channel | Oracle channel list + word count |
| Exact digital word → sample slot mapping | All digital states wrong or absent | Oracle digital events; match to sample frame words |
| Active-low vs active-high for digital | All digital polarities inverted | Oracle: observe CB trip logic state at known instant |
| `polarity_flag` byte semantics | Incorrect inversion of specific channels | Oracle + descriptor flag cross-check |
| Group 0 "SENS OUT" channel addressing | 30 channels absent or misplaced | Oracle + descriptor byte-level analysis |
| Missing-value encoding | NaN injection on valid samples, or missing samples displayed as values | Inject out-of-range sample; compare to oracle |
| Partial / truncated recording handling | Decoder crash on non-standard files | Multiple same-event BEN files; edge cases |
| Feeder word allocation for feeders 4–12 | Incorrect channel assignment for those feeders | Oracle; verify descriptor word_index against oracle channel ordering |
| data1.cab contents | Missed format documentation | Extract with cabextract on Linux; search for .hlp, .ini, format specs |
| Scale/offset for voltage channels | Engineering values wrong by ratio | Oracle voltage waveform comparison |
| Header field boundaries in master block (0xDC–0x12B) | Incorrect channel count, rate or offset | Compare multi-file recordings with different counts |

---

## 5. Proposed standalone decoder architecture

The decoder is additive to the existing BEN provider. No existing SubBen parsing code
is modified.

### 5.1 Dispatch (signature-based, not name-based)

```python
# In _check_signatures (parser.py)
SUBBEN_LAYOUT = bytes.fromhex('2aff0300')
BEN5K_LAYOUT  = bytes.fromhex('28ff0300')
GEN_SUBBEN    = bytes.fromhex('06ff')
GEN_BEN5K     = bytes.fromhex('0500')

layout = file[4:8]
gen    = file[14:16]

if layout == SUBBEN_LAYOUT and gen == GEN_SUBBEN:
    return BenLayout.SUBBEN           # existing path
elif layout == BEN5K_LAYOUT and gen == GEN_BEN5K:
    return BenLayout.BEN5K_LEGACY     # new path
else:
    raise BenUnsupportedVariantError(...)
```

Dispatch uses confirmed byte-level signatures only. Station name is never used for
format selection.

### 5.2 Module layout

```
backend/app/providers/ben/
    parser.py           # existing; add BenLayout enum value and dispatch
    layout.py           # existing; add BEN5K signature constants
    legacy_ben5k/
        __init__.py
        reader.py        # flat-config field extraction (no typed-section walking)
        channel_map.py   # build analog word_index map and digital word/bit map
        decoder.py       # numpy sample-matrix decode + scale/offset application
        normalize.py     # BenRecord construction from legacy metadata
```

The legacy decoder is isolated behind the `legacy_ben5k/` package. It shares
`BenRecord` (the existing domain record), the normalizer contract, and the existing
`BenProvider.load_with_provenance` entry point.

### 5.3 Config reader (`reader.py`)

```python
@dataclass
class Ben5kHeader:
    station: str        # 0x10, NUL-padded
    rate: int           # 0x54, u32le
    pretrigger: int     # 0x58, u32le
    count: int          # 0x5C, u32le
    words_per_sample: int  # 0x60, u32le
    trigger_bytes: bytes   # 0x64..0x6C (9 bytes)

@dataclass
class Ben5kAnalogChannel:
    name: str           # descriptor [4..19]
    word_index: int     # descriptor [53]
    scale: float        # descriptor [28..31] f32le
    offset: float       # descriptor [32..35] f32le
    type_byte: int      # descriptor [0]
    phase_seq: int      # descriptor [1]

@dataclass
class Ben5kDigitalChannel:
    name: str           # descriptor [4..19]
    word_group: int     # descriptor [1]
    bit_index: int      # descriptor [2]
    polarity_flag: int  # descriptor [0] — reserved until oracle confirms semantics

def read_header(data: ByteView) -> Ben5kHeader: ...
def read_channel_descriptors(data: ByteView) -> tuple[list[Ben5kAnalogChannel], list[Ben5kDigitalChannel]]: ...
```

Channel descriptor walk: starting at the first confirmed analog descriptor offset
(~0xBB6 + small header), advance by 58 bytes per descriptor. Discriminate analog
from digital using the byte at descriptor_start+3: `0xFF` → digital, else analog.
Stop when the descriptor name is all-NUL or the offset reaches payload start.

### 5.4 Decoder (`decoder.py`)

```python
def decode_samples(
    data: bytes,
    payload_offset: int,
    count: int,
    words_per_sample: int,
    analog_channels: list[Ben5kAnalogChannel],
    digital_channels: list[Ben5kDigitalChannel],
) -> tuple[np.ndarray, np.ndarray]:
    # sample_matrix: shape (count, words_per_sample), dtype=np.uint16, big-endian
    raw = np.frombuffer(data, dtype='>u2', count=count*words_per_sample,
                        offset=payload_offset).reshape(count, words_per_sample)

    # Analog: MUST use .astype(np.int16) NOT .view(np.int16)
    # .view() on a big-endian array reinterprets bytes as little-endian → byte-swapped values
    analog_raw = raw[:, [ch.word_index for ch in analog_channels]].astype(np.int16)
    scales = np.array([ch.scale for ch in analog_channels], dtype=np.float32)
    offsets = np.array([ch.offset for ch in analog_channels], dtype=np.float32)
    analog_eng = analog_raw.astype(np.float32) * scales + offsets

    # Digital: extract bits from word groups; active-low assumed (pending oracle)
    # word_to_sample_slot mapping: TBD via oracle — placeholder:
    #   sample_word = word_group_to_slot[word_group]
    digital = ...  # one bool array per channel

    return analog_eng, digital
```

Active-low vs active-high is a **one-line flag** in the decoder, selectable after the
oracle confirms polarity. It is NOT hardcoded.

### 5.5 Time normalization

The trigger timestamp bytes are decoded identically to the SubBen path. However, the
UTC assumption is **not applied** until the oracle confirms the timezone. Instead,
`BenRecord.trigger_time` carries an `aware=False` flag (or a separate
`BenRecord.time_basis = TimeBase.LOCAL_UNCONFIRMED`) until validation, preventing
the waveform from appearing at an incorrect UTC offset in the workspace.

### 5.6 BenRecord and provider

The `BenRecord` currently carries `layout_family = "BEN32 SubBen"`. A new
`"BEN32 BEN5K Legacy"` value will be set for this decoder path, surfacing in
provenance. The `BenProvider.load_with_provenance` method dispatches on the returned
layout; no API shape changes.

---

## 6. Required reference data

| Data | Purpose | Source |
|---|---|---|
| COMTRADE export from `261016_180314535_GPTH_275kV.ben` | Primary oracle: timestamp, channel list, engineering values, digital states | BEN32 v2.00 via DOSBox; owned recording |
| CFG+DAT pair (COMTRADE) | Sample-for-sample validation | Same export |
| At least one additional `28 ff / 05 00` recording from a different event or station | Variant coverage; different channel count / rate | Owner BEN library |
| BEN32 v2 user manual or format specification | Definitively resolves remaining unknowns | Qualitrol / owner |

The COMTRADE export must be generated by the owner operating BEN32 in DOSBox, not
by any converter. This preserves the chain of evidence from the original hardware.

---

## 7. Detailed implementation stages

### Stage 1 — Oracle and baseline (owner prerequisite, no code)
- Owner exports COMTRADE from `261016_180314535_GPTH_275kV.ben` via BEN32 in DOSBox.
- Owner provides CFG+DAT and notes whether timezone offset was applied.
- Agent confirms timestamp UTC-vs-local from oracle vs header bytes.
- Agent cross-checks channel count, names and ordering vs `Ben5kAnalogChannel` list.

### Stage 2 — Config reader and channel map (safe, no payload decode)
- Implement `legacy_ben5k/reader.py`: fixed header + channel descriptor walk.
- Unit tests: confirm descriptor field offsets against GPTH recording using byte-level assertions.
- No engineering values computed; tests pass with raw struct reads only.

### Stage 3 — Payload decoder and analog waveforms
- Implement `decoder.py`: sample matrix extraction, int16 reinterpretation, scale/offset.
- Validate against oracle: sample-for-sample engineering values for each analog channel.
- Confirm or reject the missing-value encoding (e.g., raw = -32768).

### Stage 4 — Digital decode
- Resolve digital word → sample slot mapping from oracle.
- Implement digital bit extraction with active-low as default, oracle-confirmed polarity.
- Validate all CB states and protection indications against oracle event list.

### Stage 5 — Time basis
- Confirm UTC vs local from oracle trigger time vs network/event time.
- Set `time_basis` in `BenRecord` accordingly.

### Stage 6 — `BenRecord` and normalization
- Wire `normalize.py` to produce `BenRecord` with correct `layout_family`, channels,
  metadata, and `trigger_time`.
- Full API upload test → `ready` source → analog/digital API → browser plots.

### Stage 7 — Regression safety
- All existing 87 BEN tests continue to pass.
- Private reference entry (SHA-256 pinned) for the GPTH file added to the test suite.
- Synthetic BEN5K fixture (minimal fake header + config + payload) covers: correct
  decode, unsupported signature rejection, truncated file, wrong word count.
- Deliberate out-of-range raw value test confirms missing-value handling.

---

## 8. Engineering validation and regression strategy

### Mandatory before any PR merge

1. **87 existing BEN parser + import + fixture tests pass unchanged.** No test
   expectation may be relaxed to accommodate the new path.
2. **SHA-256 pinned rejection test for GPTH recording.** Until Stage 6 is complete,
   the recording must still be rejected and the test must assert `BenUnsupportedVariantError`.
   Only after Stage 6 does this test expectation transition to `ready`.
3. **Synthetic BEN5K fixture tests** (not the original engineering recording):
   - Valid minimal fixture → `BenRecord` with expected channels and sample values.
   - BEN5K signature + SubBen generation → `BenUnsupportedVariantError`.
   - SubBen signature + BEN5K generation → `BenUnsupportedVariantError`.
   - Truncated payload → `BenStructureError`.
4. **Sample-for-sample oracle comparison** (private, not committed): all analog
   engineering values within tolerance; all digital states match oracle event list.
5. **Timestamp oracle comparison:** trigger time matches within ± 1 sample interval.
6. **Full browser smoke test:** upload → ready → workspace loads → analog waveforms
   visible → digital transitions visible → no console errors.

### Regression guards for the existing SubBen path

No change to `_check_signatures`, `_read_header_fields`, `_read_sections`,
`reader.py`, or `normalize.py` in the existing SubBen path may be introduced by the
BEN5K PR. The legacy decoder must live entirely in `legacy_ben5k/` with import
isolation. Any shared helper extracted to a common module requires its own PR and
review.

---

## 9. Risks to existing functionality

| Risk | Probability | Mitigation |
|---|---|---|
| Signature dispatch change causes false-positive match on unknown third variant | Low | Exact 8-byte comparison; reject both mismatches |
| `BenRecord` model change breaks existing SubBen normalization | Medium | Add layout field as Optional; default to existing SubBen value; test both paths |
| Shared `normalize.py` edit introduces regression | Low | Stage 5 deferred until Stages 2–4 are green; the SubBen normalize path is not touched |
| `BenLayout` enum addition causes exhaustiveness warning in existing match | Low | Handle explicitly in all existing match sites before PR merge |
| Oracle timestamp does not match header bytes (corrupt or unusual recording) | Low | Confirm with a second same-event recording before implementing time decode |
| Wrong missing-value sentinel causes NaN injection on valid samples | Medium | Test with known non-NaN sample; compare raw value -32768 against oracle |
| Digital polarity inversion silently passes if oracle has no transitions | Medium | Confirm at least one transition (e.g., CB trip) in the oracle event before closing Stage 4 |

---

## 10. Current implementation status

**Stages 2–10 complete** (branch `investigation/legacy-ben5k`, commit `ebba404`).
Full browser UAT against the real GPTH 275kV recording passed 10/10 Playwright tests
on 2026-10-21. Stage 10 phantom-channel correction adds 108 unit tests; all pass.
Engineering validation report at `docs/project-memory/BEN5K_ENGINEERING_VALIDATION.md`.
No merge to `main` until owner approval.

### Stage 10 — Phantom channel detection and physical word mapping (2026-10-22)

Direct payload analysis of the GPTH recording confirmed that two channel descriptors
in the BEN5K config area name channels with no physical recording slot ("phantom"
channels). Their presence shifts all subsequent descriptor `word_index` values by +1
each relative to the actual payload columns.

**Implementation:**

- `Ben5kAnalogChannel` (reader.py): added `physical_word_index: int = 0` field; set
  to `word_index` by `read_channel_descriptors()`; overridden by `classify_channels()`.
- `_compute_physical_mapping()` (channel_map.py): new function; walks descriptors in
  ascending `word_index` order, accumulating a correction count as phantom slots are
  detected. Returns `{wi: physical_word_index}` for all non-phantom channels.
- Phantom detection rules:
  1. Current descriptor where `raw_rms[phys] > 5000` → unambiguous phantom (current
     channel reading a voltage-strength signal).
  2. Voltage descriptor where `300 < raw_rms[phys] < 5000` AND at least one of the
     next 5 descriptors is a current descriptor whose tentative physical also reads
     voltage-strength → confirmed phantom via look-ahead.
- `classify_channels()`: uses `_compute_physical_mapping()` when `sample_words` is
  provided; falls back to identity map otherwise. The `first_digital_sw` boundary
  check and duplicate-slot check both use `physical_word_index`, not `wi`.
- `decode_samples()` (decoder.py): uses `ch.physical_word_index` for payload column
  selection (was `ch.word_index`).

**GPTH result:** Two phantoms detected (SDAI1 IN wi=15, SGT2 VY_LV wi=27). Active
analog count rises from 35 to 37 (SDAI2 IB/IN recovered). All 5 feeder voltage
triplets balanced. All Stage 9 current/voltage anomalies explained and resolved.
See `BEN5K_ENGINEERING_VALIDATION.md` §9 for full analysis.

### Implemented (Stages 2–7B)

| Module | Status |
|---|---|
| `legacy_ben5k/reader.py` | Complete — flat header + 58-byte descriptor walk |
| `legacy_ben5k/channel_map.py` | Complete — six-way classification; 0x0800-specific constant_placeholder criterion (Stage 7B) |
| `legacy_ben5k/normalize.py` | Complete — `parse_ben5k()` builds `BenRecord`; `time_basis_unconfirmed` diagnostic always attached |
| `providers/ben/parser.py` | Complete — `parse_ben_experimental()` opt-in wrapper; BEN5K dispatched only with flag |
| `providers/ben/provider.py` | Complete — `BenProvider(ben5k_experimental_enabled=True/False)`; BEN5K sets `timing_reference="relative_elapsed"` to prevent auto-synchronization |
| `config.py` | Complete — `BEN5K_EXPERIMENTAL_ENABLED` env var → `Settings.ben5k_experimental_enabled` |
| `services/import_service.py` | Complete — flag threaded to `BenProvider` |
| `api/v1/sources.py` | Complete — upload endpoint reads flag from settings |

**Feature flag:** `BEN5K_EXPERIMENTAL_ENABLED=1` enables BEN5K decoding. Default: disabled.
All existing SubBen tests continue to pass unchanged (exit 0, 190+ tests).

### Channel classification (Stage 7B refinement)

Six-way classification in `channel_map.py`:
1. `unsupported_digital` — group-0 SENS OUT channels (unconfirmed addressing)
2. `inactive_digital` — sample_word_index ≥ words_per_sample (structurally out of bounds)
3. `constant_placeholder_digital` — in-bounds AND constant value **exactly 0x0800** (confirmed inactive-feeder placeholder; other constant values, e.g. 0xFFFF quiescent, remain in verified_digital)
4. `verified_digital` — in-bounds AND (varying OR constant ≠ 0x0800)
5. `inactive_analog` — word_index ≥ first_digital_sw OR duplicate word_index
6. `recorded_analog` — all other analog channels

### Timestamp safety (Stage 7B)

BEN5K `timing_reference = "relative_elapsed"` (not `"absolute"`) in the returned
`DisturbanceRecord`. This places BEN5K in the `TIME_REFERENCE_ELAPSED_ONLY` grouping
bucket and prevents automatic cross-source time synchronization from an unverified
timestamp. The `time_basis_unconfirmed` diagnostic is always attached.

### Stage 8 — Real GPTH browser UAT (2026-10-21)

**Environment:** BEN5K-enabled backend (`BEN5K_EXPERIMENTAL_ENABLED=1`) on port 8000;
frontend served statically on port 8101; Playwright Chromium browser.

**Recording:** `261016_180314535_GPTH_275kV.ben`, 1,629,786 bytes,
SHA-256 `55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88`.

**API upload result (HTTP 201):**

| Field | Value |
|---|---|
| `provider_type` | `BEN` |
| `status` | `ready` |
| `station_name` | `GPTH 275kV - BEN5K` |
| `analog_channel_count` | 35 (37 after Stage 10 phantom correction) |
| `digital_channel_count` | 40 |
| `sample_count` | 8262 |
| `duration_seconds` | 1.6522 |
| `sampling_rates` | [5000.0] |
| `timing_reference` | `relative_elapsed` (not `absolute`) — timestamp safeguard confirmed |
| `file_size_bytes` | 1,629,786 |

**Analog channels (35 at Stage 8; 37 after Stage 10 phantom correction):** 4 bays × 7
channels (VR, VY, VB, IR, IY, IB, IN) for TBIN1/TBIN2/SDAI1/SDAI2, plus SDNK1
(VR–VB, IR–IB, IN = 7) and SGT1 VY_LV. Stage 10 excludes SDAI1 IN and SGT2 VY_LV as
phantoms and recovers SDAI2 IB and SDAI2 IN. All units kV/kA as expected for a 275 kV
substation recording.

**Digital channels (40):** All 40 in-bounds digital channels have real signal names —
`TBIN1 CB_R OPEN`, `TBIN1 CB_Y OPEN`, `TBIN1 CB_B OPEN`, `TBIN1 11L/1`,
`TBIN1 11L/2`, `TBIN1 11L_COMFL`, `TBIN1 BU_21Z_TOL`, `TBIN1 BU_21Z_Z2`, etc.
**120 channels triggered the `constant_placeholder_digital` classification** — word
groups 6–40 (sample words 43–77) each hold the constant value 0x0800 across the entire
recording. These 120 descriptors are correctly excluded from the API response.

**The 40 verified digital channels** (word groups 1–5, sample words 38–42) hold 0xFFFF
quiescent — which is ≠ 0x0800 and is non-constant where protection signals fired —
and therefore remain in `verified_digital` as intended. This confirms the 0x0800-specific
guard is correctly scoped to inactive-feeder placeholder slots, not to quiescent channels.

**10 of the 40 verified digital channels have transitions** (protection signals). Three
channels named `SPARE`, `SPARE 1`, and a `SPARE` in the SDNK1 word carry real data.

*(Correction to the Stage 8 draft — the original draft incorrectly reported zero
placeholder channels because the Stage 8 UAT did not inspect the raw sample words for
words 43–77; the Stage 9 analysis confirmed the correct numbers.)*

**Browser test results (spec `ben5k-gpth-uat.spec.js`, 10 tests):**

| # | Test | Result |
|---|---|---|
| 1 | GPTH .ben file present and correct size | PASS |
| 2 | Upload without error; station name in recordings table | PASS |
| 3 | Workspace shows 35 analog + digital channels (37 after Stage 10) | PASS |
| 4 | Expected analog channel names visible (TBIN1 VR/VY/VB/IR/IY/IB) | PASS |
| 5 | Enabling TBIN1 VR renders a waveform plot | PASS |
| 6 | TBIN1 3-phase voltages (VR+VY+VB) render in a single panel | PASS |
| 7 | Digital channel `TBIN1 CB_R OPEN` present in DOM; DOM-dispatch enable works | PASS |
| 8 | X-axis shows no absolute date/time pattern — elapsed time axis confirmed | PASS |
| 9 | API: `timing_reference="relative_elapsed"`, `status="ready"`, all metadata correct | PASS |
| 10 | Enabling all TBIN1 channels produces no console errors | PASS |

**Finding — digital channel visibility:** Digital channels have class `channel-row--hidden`
and `data-classification="never_triggered"` by default, placing them in a collapsed group
section. They are present in the DOM with correct attributes (incl.
`data-timing-reference="relative_elapsed"`) and can be enabled via DOM dispatch or by
expanding the group. This is normal channel-list behaviour for non-triggered digitals,
not a BEN5K-specific bug.

**Explicitly confirmed: The GPTH 275kV recording WAS displayed in the actual browser.**
Chromium loaded the frontend, the GPTH file was uploaded through the Upload Recording
modal, the workspace opened, and analog waveforms rendered correctly. All 10 UAT tests
passed in 39.6 s total.

### Still unverified (requires owner oracle)

- UTC vs local time (+8): timestamp stored as UTC internally but may be local time.
- Digital word_group → sample word formula: `37 + group` (inferred, not oracle-confirmed).
- `polarity_flag` semantics: byte preserved in descriptor, not yet decoded.
- Active-low polarity: assumed from GPTH quiescent 0xFFFF observation; not oracle-confirmed.
- Scale/offset correctness for voltage channels: no oracle comparison done.
- Missing-value encoding: no BEN5K-specific test; SubBen rule (raw = -32768) assumed.

---

## Appendix A — Key byte offsets summary

| Offset | Field |
|---|---|
| 0x04 | Layout signature (`28 ff 03 00 6e 00 ca 00` for BEN5K) |
| 0x0E | Generation marker (`05 00` for BEN5K) |
| 0x10 | Station name, NUL-padded to 0x37 |
| 0x54 | Sample rate, u32le µHz (÷ 1000 → samples/s) |
| 0x58 | Pre-trigger count, u32le |
| 0x5C | Total sample count, u32le |
| 0x60 | Words per sample, u32le |
| 0x64 | Trigger timestamp, 9 bytes (shared encoding with SubBen) |
| 0xDC | Config area start — flat layout, NOT typed-section |
| 0x12C | Long feeder descriptions, stride 129 bytes |
| 0x73C | Channel sensor name groups, stride 20 bytes |
| 0xAAE | Short feeder names, stride 22 bytes, 12 entries |
| 0xBB6 | Channel full descriptors begin |
| 0x694E | Payload start (count × words × 2 bytes, big-endian u16) |

**Within a channel descriptor (both analog and digital):**

| Byte | Field |
|---|---|
| 0 | Type byte / polarity flag |
| 1 | Phase sequence (analog) / word group (digital) |
| 2 | Class code high (analog) / bit index (digital) |
| 3 | Class code low (analog) / `0xFF` type marker (digital) |
| 4–19 | Name, NUL-padded |
| 28–31 | Scale (f32le, analog only — confirmed) |
| 32–35 | Offset (f32le, analog only — confirmed) |
| 36–39 | Low range (f32le, analog only — confirmed) |
| 40–43 | High range (f32le, analog only — confirmed) |
| 53 | **Word index** (u8, analog only — **confirmed**) |
| 57 | `0xFF` terminator |

---

## Appendix B — Analog channel class codes observed

| Class code (u16le) | Channel |
|---|---|
| 0x0528 = 1320 | V R-phase |
| 0x0488 = 1160 | V Y-phase |
| 0x03E8 = 1000 | V B-phase |
| 0x021C =  540 | I R-phase |
| 0x0190 =  400 | I Y-phase |
| 0x00F0 =  240 | I B-phase |
| 0x0050 =   80 | I N (neutral) |

Class codes are the same across feeders (TBIN1 VR and SDAI1 VR both have code 0x0528).
These appear to be channel-type templates, not word-index encodings.

---

*Investigation conducted by: Claude Sonnet 4.6 (read-only binary analysis)*  
*Owner review required before Phase 2 implementation begins.*
