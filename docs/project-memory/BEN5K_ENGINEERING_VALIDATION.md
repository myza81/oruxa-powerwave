# BEN5K Engineering Validation Report

**Recording:** `261016_180314535_GPTH_275kV.ben`  
**SHA-256:** `55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88`  
**Date of analysis:** 2026-10-21 (Stages 1–9); 2026-10-22 (Stage 10)  
**Branch:** `investigation/legacy-ben5k` (commit `ebba404` → Stage 10B)  
**Status:** Not merged to main — owner review required before production use.

> **Stage 10B — phantom-channel correction applied and validated (2026-10-22):** Two
> phantom descriptors (SDAI1 IN wi=15 and SGT2 VY_LV wi=27) had no physical recording
> slots, causing all subsequent descriptor word_index values to be offset by −1 and −2
> relative to the actual payload columns. Three bugs in the Stage 10 decoder were
> identified and fixed: (Bug 1) a comment misidentified the header field as u32le instead
> of u16le; (Bug 2) RMS was computed on unsigned uint16 values, making all channels appear
> voltage-strength and defeating phantom detection; (Bug 3) the look-ahead window counted
> raw descriptor positions instead of distinct word_index values, causing duplicate inactive-
> feeder descriptors to exhaust the window before the critical descriptor was reached. After
> all three fixes: all five feeder 3-phase voltage sets are well-balanced, all current
> anomalies are resolved, SDAI2 IB/IN are recovered as active channels, and 73 BEN5K
> unit tests pass. The active analogue channel count remains **35** (two phantoms excluded,
> two previously excluded channels recovered — net zero change in count). See §9 for the
> complete Stage 10 analysis.

---

## 1. Complete Decoded Channel Inventory

### 1.1 Recording metadata

| Field | Value | Classification |
|---|---|---|
| Station | `GPTH 275kV - BEN5K` | Confirmed |
| Rate | 5000 Hz | Confirmed |
| Total samples | 8262 | Confirmed |
| Pre-trigger samples | 2500 | Confirmed |
| Post-trigger samples | 5762 | Confirmed |
| Duration | 1.6522 s | Confirmed |
| Pre-trigger window | 0.50 s | Confirmed |
| Post-trigger window | 1.152 s | Confirmed |
| Words per sample | 97 | Confirmed |
| Analog descriptor count | 80 (35 active + 45 inactive) | Updated: Stage 10B |
| Digital descriptor count | 160 (40 verified + 120 constant-placeholder) | Confirmed |
| API-exposed channels | 35 analog + 40 digital | Updated: Stage 10B |

### 1.2 Active analogue channels (35)

*Stage 10B: `phys` column confirmed by direct GPTH analysis. SDAI1 IN (wi=15) and
SGT2 VY_LV (wi=27) are phantom channels (listed in §1.3). SDAI2 IB (wi=38→phys=36)
and SDAI2 IN (wi=39→phys=37) are now active after phantom correction. Total remains
35 (two phantoms excluded, two recovered — net zero change from Stage 8 count).*

| Name | wi | phys | Type | Scale | High-range | Notes |
|---|---|---|---|---|---|---|
| TBIN1 VR | 0 | 0 | V | 0.134343 | 158.77 | TBIN1 3-phase voltage, R-phase |
| TBIN1 VY | 1 | 1 | V | 0.134343 | 158.77 | TBIN1 3-phase voltage, Y-phase |
| TBIN1 VB | 2 | 2 | V | 0.134343 | 158.77 | TBIN1 3-phase voltage, B-phase |
| TBIN1 IR | 4 | 4 | I | 0.018709 | 1.50 | TBIN1 feeder current, R-phase |
| TBIN1 IY | 5 | 5 | I | 0.018709 | 1.50 | TBIN1 feeder current, Y-phase |
| TBIN1 IB | 6 | 6 | I | 0.018709 | 1.50 | TBIN1 feeder current, B-phase |
| TBIN1 IN | 7 | 7 | I | 0.018709 | 1.50 | TBIN1 neutral current |
| SDAI1 VR | 8 | 8 | V | 0.134343 | 158.77 | SDAI1 3-phase voltage, R-phase |
| SDAI1 VY | 9 | 9 | V | 0.134343 | 158.77 | SDAI1 3-phase voltage, Y-phase |
| SDAI1 VB | 10 | 10 | V | 0.134343 | 158.77 | SDAI1 3-phase voltage, B-phase |
| SGT1 VY_LV | 11 | 11 | V | 0.064485 | 76.21 | SGT1 transformer LV Y-phase voltage |
| SDAI1 IR | 12 | 12 | I | 0.018709 | 1.50 | SDAI1 feeder current, R-phase |
| SDAI1 IY | 13 | 13 | I | 0.018709 | 1.50 | SDAI1 feeder current, Y-phase |
| SDAI1 IB | 14 | 14 | I | 0.018709 | 1.50 | SDAI1 feeder current, B-phase |
| SDNK1 VR | 16 | **15** | V | 0.134343 | 158.77 | SDNK1 3-phase voltage, R-phase |
| SDNK1 VY | 17 | **16** | V | 0.134343 | 158.77 | SDNK1 3-phase voltage, Y-phase |
| SDNK1 VB | 18 | **17** | V | 0.134343 | 158.77 | SDNK1 3-phase voltage, B-phase |
| SDNK1 IR | 20 | **19** | I | 0.018709 | 1.50 | SDNK1 feeder current, R-phase |
| SDNK1 IY | 21 | **20** | I | 0.018709 | 1.50 | SDNK1 feeder current, Y-phase |
| SDNK1 IB | 22 | **21** | I | 0.018709 | 1.50 | SDNK1 feeder current, B-phase |
| SDNK1 IN | 23 | **22** | I | 0.018709 | 1.50 | SDNK1 neutral current |
| TBIN2 VR | 24 | **23** | V | 0.134343 | 158.77 | TBIN2 3-phase voltage, R-phase |
| TBIN2 VY | 25 | **24** | V | 0.134343 | 158.77 | TBIN2 3-phase voltage, Y-phase |
| TBIN2 VB | 26 | **25** | V | 0.134343 | 158.77 | TBIN2 3-phase voltage, B-phase |
| TBIN2 IR | 28 | **26** | I | 0.018709 | 1.50 | TBIN2 feeder current, R-phase |
| TBIN2 IY | 29 | **27** | I | 0.018709 | 1.50 | TBIN2 feeder current, Y-phase |
| TBIN2 IB | 30 | **28** | I | 0.018709 | 1.50 | TBIN2 feeder current, B-phase |
| TBIN2 IN | 31 | **29** | I | 0.018709 | 1.50 | TBIN2 neutral current |
| SDAI2 VR | 32 | **30** | V | 0.134343 | 158.77 | SDAI2 3-phase voltage, R-phase |
| SDAI2 VY | 33 | **31** | V | 0.134343 | 158.77 | SDAI2 3-phase voltage, Y-phase |
| SDAI2 VB | 34 | **32** | V | 0.134343 | 158.77 | SDAI2 3-phase voltage, B-phase |
| SDAI2 IR | 36 | **34** | I | 0.018709 | 1.50 | SDAI2 feeder current, R-phase |
| SDAI2 IY | 37 | **35** | I | 0.018709 | 1.50 | SDAI2 feeder current, Y-phase |
| SDAI2 IB | 38 | **36** | I | 0.018709 | 1.50 | SDAI2 feeder current, B-phase (**recovered Stage 10B**) |
| SDAI2 IN | 39 | **37** | I | 0.018709 | 1.50 | SDAI2 neutral current (**recovered Stage 10B**) |

Notes: `wi` = logical slot from descriptor byte 53. `phys` = phantom-corrected physical
payload column. Bold values indicate a Stage 10 correction. `High-range` 158.77 = 275/√3
(primary kV at 275 kV); 76.21 = 132/√3 kV; 1.50 = rated primary kA.

### 1.3 Inactive analogue channels (45) — reason for exclusion

*Stage 10B: SDAI2 IB and SDAI2 IN promoted to active (see §1.2). SDAI1 IN and
SGT2 VY_LV confirmed as phantom channels. SGT2 IB_LV/IN_LV reclassified from
"digital region" to "duplicate wi" (their physical words 36/37 are in the analog
region but already claimed by SDAI2 IB/IN).*

| Name | wi | Scale | Reason |
|---|---|---|---|
| SDAI1 IN | 15 | 0.018709 | **PHANTOM** — current descriptor, phys=15 carries SDNK1 VR voltage-strength signal; no physical IN slot in SDAI1 block |
| SGT2 VY_LV | 27 | 0.064485 | **PHANTOM** — voltage descriptor, phys=26 carries TBIN2 IR current; no SGT2 LV slot in TBIN2 block; detected via look-ahead |
| SDNK2 VR | 0 | 0.134343 | Duplicate wi=0 (TBIN1 VR has priority) |
| SDNK2 VY | 1 | 0.134343 | Duplicate wi=1 |
| SDNK2 VB | 2 | 0.134343 | Duplicate wi=2 |
| SDNK2 IR | 4 | 0.018709 | Duplicate wi=4 |
| SDNK2 IY | 5 | 0.018709 | Duplicate wi=5 |
| SDNK2 IB | 6 | 0.018709 | Duplicate wi=6 |
| SDNK2 IN | 7 | 0.018709 | Duplicate wi=7 |
| SGT1 VR_HV | 8 | 0.134343 | Duplicate wi=8 (SDAI1 VR) |
| SGT1 VY_HV | 9 | 0.134343 | Duplicate wi=9 |
| SGT1 VB_HV | 10 | 0.134343 | Duplicate wi=10 |
| SGT1 IR_HV | 12 | 0.007484 | Duplicate wi=12 (SDAI1 IR) |
| SGT1 IY_HV | 13 | 0.007484 | Duplicate wi=13 |
| SGT1 IB_HV | 14 | 0.007484 | Duplicate wi=14 |
| SGT1 IN_HV | 15 | 0.007484 | Duplicate wi=15 (SDAI1 IN) |
| SGT1 IR_LV | 20 | 0.014967 | Duplicate wi=20 (SDNK1 IR) |
| SGT1 IY_LV | 21 | 0.014967 | Duplicate wi=21 |
| SGT1 IB_LV | 22 | 0.014967 | Duplicate wi=22 |
| SGT1 IN_LV | 23 | 0.014967 | Duplicate wi=23 (SDNK1 IN) |
| SGT2 VR_HV | 24 | 0.134343 | Duplicate wi=24 (TBIN2 VR) |
| SGT2 VY_HV | 25 | 0.134343 | Duplicate wi=25 |
| SGT2 VB_HV | 26 | 0.134343 | Duplicate wi=26 (TBIN2 VB) |
| SGT2 IR_HV | 28 | 0.007484 | Duplicate wi=28 (TBIN2 IR) |
| SGT2 IY_HV | 29 | 0.007484 | Duplicate wi=29 |
| SGT2 IB_HV | 30 | 0.007484 | Duplicate wi=30 (TBIN2 IB) |
| SGT2 IN_HV | 31 | 0.007484 | Duplicate wi=31 (TBIN2 IN) |
| SGT2 IR_LV | 36 | 0.014967 | Duplicate wi=36 (SDAI2 IR) |
| SGT2 IY_LV | 37 | 0.014967 | Duplicate wi=37 |
| SGT2 IB_LV | 38 | 0.014967 | Duplicate wi=38 (SDAI2 IB has priority; phys=36) |
| SGT2 IN_LV | 39 | 0.014967 | Duplicate wi=39 (SDAI2 IN has priority; phys=37) |
| PLNG1 VR | 0 | 0.134343 | Duplicate wi=0 |
| PLNG1 VY | 1 | 0.134343 | Duplicate wi=1 |
| PLNG1 VB | 2 | 0.134343 | Duplicate wi=2 |
| PLNG1 IR | 4 | 0.036639 | Duplicate wi=4 |
| PLNG1 IY | 5 | 0.036639 | Duplicate wi=5 |
| PLNG1 IB | 6 | 0.036639 | Duplicate wi=6 |
| PLNG1 IN | 7 | 0.036639 | Duplicate wi=7 |
| PLNG2 VR | 8 | 0.134343 | Duplicate wi=8 |
| PLNG2 VY | 9 | 0.134343 | Duplicate wi=9 |
| PLNG2 VB | 10 | 0.134343 | Duplicate wi=10 |
| PLNG2 IR | 12 | 0.036639 | Duplicate wi=12 |
| PLNG2 IY | 13 | 0.036639 | Duplicate wi=13 |
| PLNG2 IB | 14 | 0.036639 | Duplicate wi=14 |
| PLNG2 IN | 15 | 0.036639 | Duplicate wi=15 |

**Inactive channel interpretation:**

- SDNK2, PLNG1, PLNG2: feeder descriptors present in the BEN configuration but sharing
  word slots with commissioned feeders (TBIN1, SDAI1). The BEN recorder was configured for a
  full substation template; these feeders were not commissioned (no unique word slots assigned).
  This is normal BEN5K behaviour — the configuration template covers all planned bays.

- SGT1/SGT2 HV/LV currents: The transformer high-voltage and low-voltage current
  descriptors share word slots with feeder current channels. The SGT1 LV currents share
  slots 20–23 with SDNK1 IR–IN; the SGT1 HV currents share slots 12–15 with SDAI1 IR–IN.
  This sharing is a RECORDING LIMITATION — only the first descriptor per slot is recorded.
  The transformer currents are therefore NOT available from this recording despite being
  configured. The inactive-analog classification correctly identifies this.

- SDAI2 IB/IN at wi=38–39: The descriptor word_index values (38, 39) coincide with the
  digital bitmask region (formula `sw = 37 + group`), but after phantom correction
  (correction=2) their physical payload columns are 36 and 37 — both within the analog
  region. SDAI2 IB and SDAI2 IN are therefore correctly classified as active channels
  (see §1.2). The corresponding SGT2 IB_LV and SGT2 IN_LV descriptors share the same
  wi=38/39 slots and are classified as duplicate_slot (inactive), because physical words
  36 and 37 are already claimed by SDAI2 IB/IN.

### 1.4 Digital channels

**40 verified digital channels** (word groups 1–5, sample words 38–42, 8 channels per word):

| SW | Bit | Name | Transitions |
|---|---|---|---|
| 38 | 0 | TBIN1 CB_R OPEN | None |
| 38 | 1 | TBIN1 CB_Y OPEN | None |
| 38 | 2 | TBIN1 CB_B OPEN | None |
| 38 | 3 | TBIN1 11L/1 | None |
| 38 | 4 | SPARE | None |
| 38 | 5 | TBIN1 11L/2 | None |
| 38 | 6 | TBIN1 11L_COMFL | None |
| 38 | 7 | TBIN1 BU_21Z_TOL | **2 transitions** (+252.4ms, +816.8ms) |
| 39 | 0 | TBIN1 BU_21Z_Z2 | None |
| 39 | 1 | TBIN1 BU_21Z_Z3 | None |
| 39 | 2 | TBIN1 BU_21Z_Z3R | None |
| 39 | 3 | TBIN1 BU21Z_SOTF | None |
| 39 | 4 | TBIN1 79AR_L/O | None |
| 39 | 5 | TBIN1 79AR_ATMPT | None |
| 39 | 6 | TBIN1 85INTRSEND | None |
| 39 | 7 | TBIN1 85INTR_REC | **2 transitions** (+252.6ms, +816.8ms) |
| 40 | 0 | SDAI1 CB_R OPEN | None |
| 40 | 1 | SDAI1 CB_Y OPEN | None |
| 40 | 2 | SDAI1 CB_B OPEN | None |
| 40 | 3 | SDAI1 87L/1 | None |
| 40 | 4 | SPARE 1 | None |
| 40 | 5 | SDAI1 87L/2 | None |
| 40 | 6 | SDAI1 87L_COMFL | None |
| 40 | 7 | SDAI1 BU_21Z_TOL | **2 transitions** (+252.6ms, +816.8ms) |
| 41 | 0 | SDAI1 BU_21Z_Z2 | None |
| 41 | 1 | SDAI1 BU_21Z_Z3 | None |
| 41 | 2 | SDAI1 BU_21Z_Z1 | None |
| 41 | 3 | SDAI1 BU21Z_SOTF | None |
| 41 | 4 | SDAI1 79AR_L/O | None |
| 41 | 5 | SDAI1 79AR_ATMPT | None |
| 41 | 6 | SDAI1 85INTRSEND | **2 transitions** (+9.6ms, +33.4ms) |
| 41 | 7 | SDAI1 85INTR_REC | **2 transitions** (+252.6ms, +816.8ms) |
| 42 | 0 | SDNK1 CB_R OPEN | None |
| 42 | 1 | SDNK1 CB_Y OPEN | None |
| 42 | 2 | SDNK1 CB_B OPEN | None |
| 42 | 3 | SDNK1 87L/1 | **2 transitions** (+453.8ms, +997.4ms) |
| 42 | 4 | SPARE (SDNK1 bay) | **4 transitions** (+9.6ms, +35.2ms, +100.6ms, +1043.6ms) |
| 42 | 5 | SDNK1 87L/2 | **2 transitions** (+466.0ms, +851.2ms) |
| 42 | 6 | SDNK1 87L_COMFL | **2 transitions** (−1.8ms, +855.0ms) |
| 42 | 7 | SDNK1 BU_21Z_TOL | **2 transitions** (+252.6ms, +817.0ms) |

Quiescent state (no-change channels): initial and final word = 0xFFFF.
Active-low convention assumed: stored bit 1 = inactive, stored bit 0 = active.

**120 constant-placeholder digital channels** (word groups 6–40, sample words 43–77):
All sample words 43–77 hold the constant value 0x0800 across the entire recording.
These 120 channel descriptors are correctly excluded by the `constant_placeholder_digital`
classification criterion (`constant value == 0x0800`). They are not exposed via the API.

---

## 2. Analogue RMS and Phasor Analysis

### 2.1 Calibration coefficient metadata

The high_range values in the channel descriptors identify the system:

| Type | Scale (f32) | High-range (f32) | Interpretation |
|---|---|---|---|
| Voltage (275 kV feeders) | 0.134343 | 158.77 | 158.77 = 275/√3 kV phase-to-earth |
| Current (feeders) | 0.018709 | 1.50 | 1.50 rated range (kA or A — see §6.1) |
| Voltage (132 kV SGT LV) | 0.064485 | 76.21 | 76.21 = 132/√3 kV phase-to-earth |
| Current (SGT HV, inactive) | 0.007484 | n/a | Different CT ratio — not decoded |
| Current (SGT LV, inactive) | 0.014967 | n/a | Different CT ratio — not decoded |
| Current (PLNG feeders, inactive) | 0.036639 | n/a | Different CT ratio — not decoded |

The high-range values confirm this is a 275 kV / 132 kV installation (GPTH 275 kV
substation with SGT step-down transformers to a 132 kV section). The different scale
factors for SGT and PLNG feeders indicate different VT/CT ratios for those equipment types.

### 2.2 Three-phase voltage balance (pre-trigger, one cycle)

Pre-trigger window: samples 2400–2500 (the last 100 samples before the trigger, 1 cycle at
50 Hz). All values in engineering units as produced by the decoder.

*Stage 10 update: values computed using phantom-corrected physical word indices.*

| Bay | VR | VY | VB | Balance |
|---|---|---|---|---|
| TBIN1 | 1782.4 | 1767.4 | 1805.0 | **Well balanced** (< 2% deviation) |
| SDAI1 | 1790.9 | 1769.2 | 1809.7 | **Well balanced** (< 1.2% deviation) |
| SDNK1 | 1532.6† | 1596.8 | ~1596.7† | **Well balanced** (Stage 10 corrected) |
| TBIN2 | 1534.3† | 1594.2 | ~1594.3† | **Well balanced** (Stage 10 corrected) |
| SDAI2 | 1600.6† | ~1532.4† | ~1600.7† | **Well balanced** (Stage 10 corrected) |

†Full-record RMS × scale (pre-trigger one-cycle values require re-running the analysis
script against the real recording). All five feeders now show well-balanced 3-phase
voltages consistent with normal 275 kV operation. The previous near-zero and reduced
values (SDNK1 VB, TBIN2 VB, SDAI2 VY/VB) were artefacts of the phantom descriptor
offset — those channels were reading physical control-word and current-signal slots
rather than their correct voltage payload columns. See §9.

### 2.3 Three-phase current balance (pre-trigger, one cycle)

*Stage 10 update: values computed using phantom-corrected physical word indices.
Previous anomalous current values (TBIN2 IB=248, SDNK1 IN=248, etc.) are resolved.*

| Bay | IR | IY | IB | IN |
|---|---|---|---|---|
| TBIN1 | 7.68 | 8.42 | 7.83 | ~0.86 |
| SDAI1 | 1.97 | 1.99 | 1.10 | (phantom—excluded) |
| SDNK1 | ~5.14† | ~4.63† | ~1.35† | ~1.35† |
| TBIN2 | ~12.01† | ~10.73† | ~10.74† | ~1.63† |
| SDAI2 | ~14.52† | ~16.31† | ~13.02† | ~7.07† |

†Full-record RMS × scale estimates from Stage 10 physical word analysis. Pre-trigger
one-cycle values require re-running the analysis script. All previous anomalous large-
amplitude current readings (TBIN2 IB=248, SDNK1 IN=248, TBIN2 IN=213) are now
confirmed as phantom-offset artefacts: those channels were reading the wrong physical
payload column (a voltage slot decoded with current scale). See §9.

### 2.4 Pre-trigger versus post-trigger RMS (first cycle after trigger)

Significant changes (> ±20%) observed at the trigger:

| Channel | Pre RMS | Post RMS | Delta | Interpretation |
|---|---|---|---|---|
| TBIN1 VY | 1767 | 1375 | −22% | Voltage depression, Y-phase |
| TBIN1 VR | 1782 | 1626 | −9% | Voltage depression, R-phase |
| SDAI1 VY | 1769 | 1376 | −22% | Same voltage depression |
| SDNK1 VR | 1767 | 1374 | −22% | Same voltage depression |
| TBIN2 VY | 1804 | 1736 | −4% | Minor voltage depression |
| SDNK1 IR | 1.66 | 5.94 | +259% | Large current increase |
| SDNK1 IB | 0.95 | 2.42 | +153% | Large current increase |
| TBIN2 IY | 1.18 | 3.02 | +156% | Large current increase |
| SDAI2 IY | 3.83 | 17.3 | +352% | Very large current increase |
| TBIN1 IR | 7.68 | 9.95 | +30% | Moderate current increase |
| SDAI1 IB | 1.10 | 1.49 | +35% | Moderate current increase |

The voltage depressions (VY and VR phases, Y-phase most affected) combined with
simultaneous current increases on multiple feeders is consistent with a system fault
in the Y-phase propagating through the 275 kV network.

### 2.5 SGT transformer LV voltage

| Channel | Full-record RMS | Pre-trigger | Post-trigger | Notes |
|---|---|---|---|---|
| SGT1 VY_LV | 6.31 | 4.98 | 5.62 | Very low — SGT1 LV may be de-energized |

*Note: SGT2 VY_LV (wi=27) is confirmed as a PHANTOM channel (Stage 10B). Its descriptor
had no physical recording slot; it was misidentifying physical word 26 (TBIN2 IR) as a
transformer LV voltage. The previous SGT2 VY_LV statistics (RMS 38.1) were artefacts of
the wrong physical column. SGT2 VY_LV is now excluded from all statistics.*

SGT2 VY_LV high-range is 76.21 kV (= 132/√3), consistent with a 132 kV LV winding.
SGT1 VY_LV at 4.98–6.31 is substantially below rated level.

---

## 3. Raw-Versus-Engineering-Value Verification

Spot-checks at sample index 2500 (trigger point) confirm the decoder formula
`eng = int16(raw_uint16) × scale + offset`:

| Channel | Raw (hex) | s16 | Scale | Calculated | Decoded | Match |
|---|---|---|---|---|---|---|
| TBIN1 VR | 0xBBBF | −17473 | 0.134343 | −2347.374 | −2347.374 | YES* |
| TBIN1 VY | 0x13BF | 5055 | 0.134343 | 679.104 | 679.104 | YES |
| TBIN1 VB | 0x30AF | 12463 | 0.134343 | 1674.316 | 1674.316 | YES |
| TBIN1 IR | 0x028F | 655 | 0.018709 | 12.255 | 12.255 | YES |
| TBIN1 IY | 0xFE3F | −449 | 0.018709 | −8.401 | −8.401 | YES |
| TBIN1 IB | 0xFF4F | −177 | 0.018709 | −3.312 | −3.312 | YES |

*TBIN1 VR shows float32 rounding in the final digit; the values agree to 4 significant figures.

The endian interpretation, channel word-index addressing, and scale/offset application
are confirmed correct. The decoder's `astype(np.int16)` conversion (not `view()`) is
verified to produce the correct signed interpretation of big-endian uint16 data.

---

## 4. Digital Transition Table

Transitions where a channel changed state during the recording. All times relative to the
trigger. Active-low convention: stored bit 1 = inactive (normal state), stored bit 0 = active
(function operated). A pair of transitions (inh → act → inh) indicates a temporary operation.

| Channel | SW | Bit | Transition 1 | Transition 2 | Transition 3 | Transition 4 |
|---|---|---|---|---|---|---|
| SDNK1 87L_COMFL | 42 | 6 | **−1.8 ms** | +855.0 ms | — | — |
| SDAI1 85INTRSEND | 41 | 6 | +9.6 ms | +33.4 ms | — | — |
| SPARE (sw42,bit4) | 42 | 4 | +9.6 ms | +35.2 ms | +100.6 ms | +1043.6 ms |
| TBIN1 BU_21Z_TOL | 38 | 7 | +252.4 ms | +816.8 ms | — | — |
| TBIN1 85INTR_REC | 39 | 7 | +252.6 ms | +816.8 ms | — | — |
| SDAI1 BU_21Z_TOL | 40 | 7 | +252.6 ms | +816.8 ms | — | — |
| SDAI1 85INTR_REC | 41 | 7 | +252.6 ms | +816.8 ms | — | — |
| SDNK1 BU_21Z_TOL | 42 | 7 | +252.6 ms | +817.0 ms | — | — |
| SDNK1 87L/1 | 42 | 3 | +453.8 ms | +997.4 ms | — | — |
| SDNK1 87L/2 | 42 | 5 | +466.0 ms | +851.2 ms | — | — |

30 channels had no transitions (quiescent 0xFFFF throughout, including all CB OPEN contacts,
TBIN1/SDAI1 line differential 87L, all SOTF, autoreclose 79AR and intertrip send/receive
except those listed above).

**Sequence interpretation (plausible — active-low assumed, polarity unconfirmed by oracle):**

The transition sequence is consistent with a teleprotection-initiated multi-feeder event:

1. **T − 1.8 ms**: `SDNK1 87L_COMFL` (SDNK1 line-differential communication/pilot fault)
   activates. This is the event that triggered the BEN recorder. A communication fault or
   loss-of-guard detection in the SDNK1 distance protection.

2. **T + 9.6 ms / T + 33.4 ms**: `SDAI1 85INTRSEND` operates for 23.8 ms. SDAI1
   teleprotection send channel operated briefly, indicating the SDAI1 protection issued a
   permissive or direct intertrip command.

3. **T + 9.6 ms**: The `SPARE` channel (sw=42, bit=4) in the SDNK1 word also activates.
   Its four transitions at +9.6, +35.2, +100.6 and +1043.6 ms suggest chattering or a
   protection function with multiple picks and drops. The name "SPARE" prevents confident
   assignment; this could be a protection output or a supervisory contact.

4. **T + 252 ms (simultaneous)**: `TBIN1 BU_21Z_TOL`, `TBIN1 85INTR_REC`, `SDAI1 BU_21Z_TOL`,
   `SDAI1 85INTR_REC`, `SDNK1 BU_21Z_TOL` all activate within one sample (0.2 ms) of each
   other. This is consistent with a BUSBAR or inter-bus protection zone timed-out signal
   (BU_21Z_TOL = busbar distance Zone 1 time-out tolerance?) operating simultaneously on
   three feeders, concurrent with teleprotection receive signals.

5. **T + 453 ms / +466 ms**: `SDNK1 87L/1` and `SDNK1 87L/2` activate. Line differential
   operating signals on SDNK1, 453–466 ms after the trigger.

6. **T + 816–817 ms**: All BU_21Z_TOL, 85INTR_REC signals reset simultaneously, consistent
   with protection relay reset or clearing of the fault condition.

**Important caveats:**
- Active-low polarity is assumed, not oracle-confirmed. If the convention is inverted, all
  interpretations above are reversed.
- `BU_21Z_TOL`, `87L_COMFL`, `85INTRSEND`, `85INTR_REC` are abbreviated names; exact
  function assignments depend on the relay configuration documents, not available to this analysis.
- The simultaneous operation on TBIN1, SDAI1 and SDNK1 channels suggests a substation-wide
  event rather than a single-feeder fault.
- No CB OPEN contacts operated during the recording window, which is unusual for a fault that
  triggered protection functions. Either the CBs are at a remote substation (and only the
  protection signals are wired to GPTH BEN), or the breaker operations occurred outside the
  recording window.

---

## 5. Timing Assessment

### 5.1 Trigger timestamp bytes

Raw trigger bytes: `7e 0a 10 12 03 0e 35 36 00`

Interpreted using the SubBen encoding (confirmed shared with BEN5K):

| Byte | Value (hex) | Decoded |
|---|---|---|
| 0 | 0x7E = 126 | Year last two digits: 2026 |
| 1 | 0x0A = 10 | Month: October |
| 2 | 0x10 = 16 | Day: 16 |
| 3 | 0x12 = 18 | Hour: 18 |
| 4 | 0x03 = 3 | Minute: 03 |
| 5 | 0x0E = 14 | Second: 14 |
| 6 | 0x35 = 53 | Centiseconds: 53 (530 ms) |
| 7 | 0x36 = 54 | ??? |
| 8 | 0x00 = 0 | ??? |

Decoded trigger timestamp: **2026-10-16 18:03:14** (UTC or local time +8 — unconfirmed).
API-reported `trigger_time`: `2026-10-16T18:03:14.535400Z` (the `.535` vs byte 6 `0x35=530ms`
differs by 5ms; byte 7 `0x36` may encode a 6ms sub-centisecond component → 530+5=535ms).

The event date (16 October 2026) is consistent with the filename `261016_180314535` which
encodes date `261016` and time `180314535` (18:03:14.535).

### 5.2 UTC versus local time

The time `18:03:14` could be:
- UTC: 18:03:14 UTC (2:03 am Malaysian local, 16 October 2026)
- Local (+8): 18:03:14 MYT = 10:03:14 UTC (16 October 2026)

Malaysian substations typically operate on Malaysian time (UTC+8). TNB SCADA systems
generally timestamp events in local time. A BEN recorder at a TNB substation likely
stores local time.

If 18:03:14 is local MYT: the event occurred at 10:03:14 UTC on 16 October 2026.
If 18:03:14 is UTC: the event occurred at 02:03:14 local time (the middle of the night
on 17 October 2026 local) — less consistent with typical disturbance investigation records
which are named by local date.

The filename prefix `261016` matches day **16 October** in local Malaysian date format
(`YYMMDD`). This is consistent with the event occurring in the morning on 16 October 2026
local time (18:03 local MYT), not at 02:03 local on the following day.

**Plausible interpretation**: the timestamp is local Malaysian time (MYT = UTC+8).
The UTC equivalent would be 10:03:14 UTC, 16 October 2026.

This interpretation is **plausible but unconfirmed** — oracle comparison is required.

### 5.3 Relative timing safeguard

`timing_reference = "relative_elapsed"` is set on all BEN5K sources. Time-grouping
places BEN5K in `TIME_REFERENCE_ELAPSED_ONLY`, preventing automatic cross-source UTC
synchronization. This is the correct behaviour until the UTC/local question is resolved.
The digital transition times (+252ms, +816ms, etc.) are relative to the trigger and do
not depend on the absolute timestamp.

---

## 6. Unresolved Engineering Uncertainties

### 6.1 Absolute calibration — scale unit unknown

**Status: Plausible but unverified.**

The scale factors (0.134343, 0.018709) convert ADC int16 counts to engineering values.
The `high_range` metadata contains values that map directly to system nominal quantities:
- 158.77 = 275/√3 kV (nominal phase-to-earth voltage at 275 kV)
- 76.21 = 132/√3 kV (132 kV LV winding)
- 1.50 = rated range (kA or A — ambiguous from metadata alone)

However, the observed pre-trigger RMS for fully-commissioned feeders (TBIN1 VR ≈ 1782)
is approximately 11× larger than the high_range nominal (158.77). This relationship
is consistent for ALL voltage channels and current channels, suggesting the scale
factor encodes an intermediate quantity (secondary VT/CT output, not primary kV/kA)
rather than primary engineering units.

**Two self-consistent hypotheses:**
1. Scale produces secondary voltage (V)/current (A); high_range is primary kV/kA —
   the VT/CT ratio is embedded in the relationship between observed values and high_range.
2. Scale produces primary engineering values in kV/kA — the ADC operates at ~3.6% of
   its range under nominal conditions (high dynamic range design).

Without a COMTRADE oracle export from BEN32, the absolute engineering values cannot be
independently verified. The RELATIVE values (pre/post ratios, 3-phase balance, digital
timing) are meaningful regardless of the unit question.

### 6.2 Four anomalous channels

**Status: RESOLVED by Stage 10 (2026-10-22) — phantom descriptor offset explained all anomalies.**

The four channels listed below were reading the WRONG physical payload columns because
two phantom descriptors (SDAI1 IN wi=15 and SGT2 VY_LV wi=27) had no physical slots and
shifted all subsequent descriptor word_index values by −1 or −2.

| Channel | wi | Old phys | Wrong signal at old phys | Correct phys | Correct signal |
|---|---|---|---|---|---|
| SDAI1 IN | 15 | 15 | SDNK1 VR voltage (RMS 11693 raw) | — | **PHANTOM — excluded** |
| SDNK1 IN | 23 | 23 | TBIN2 VR voltage (RMS 11685 raw) | **22** | Real neutral IN (~1.35 kA) |
| TBIN2 IB | 30 | 30 | SDAI2 VR voltage (RMS 11672 raw) | **28** | Real phase IB (~10.7 kA) |
| TBIN2 IN | 31 | 31 | SDAI2 VY voltage (RMS 11407 raw) | **29** | Real neutral IN (~1.6 kA) |

The near-identical anomalous amplitudes (248 RMS engineering units across channels at
wi=15, 23, 30) were all reading the same calibration group (275 kV phase voltage decoded
with current scale 0.018709): a voltage raw count of ~11685 × 0.018709 ≈ 218.7.

After the Stage 10 phantom correction, all four channels read physically correct signals
and the values are engineering-plausible. Oracle comparison is still required to confirm
absolute calibration, but the channel-to-slot mapping issue is resolved.

Additionally, the following near-zero/reduced voltage anomalies (Stage 6.3) were caused
by the same phantom offset — see §6.3 below.

### 6.3 Near-zero and reduced voltage channels

**Status: RESOLVED by Stage 10 (2026-10-22) — all four anomalies were phantom-offset artefacts.**

| Channel | wi | Old phys | Wrong signal at old phys | Correct phys | Correct signal |
|---|---|---|---|---|---|
| SDNK1 VB | 18 | 18 | SDNK1 control word (RMS 32 raw) | **17** | Real VB voltage (~1597 engineering) |
| TBIN2 VB | 26 | 26 | TBIN2 IR current (RMS 642 raw) | **25** | Real VB voltage (~1594 engineering) |
| SDAI2 VY | 33 | 33 | SDAI2 control word (RMS 154 raw) | **31** | Real VY voltage (~1532 engineering) |
| SDAI2 VB | 34 | 34 | SDAI2 IR current (RMS 776 raw) | **32** | Real VB voltage (~1601 engineering) |

These channels were reading physical payload positions corresponding to control words and
current slots instead of their correct voltage positions. After phantom correction:

- SDNK1 VB (wi=18 → phys=17): reads real SDNK1 VB voltage, well-balanced with VR and VY.
- TBIN2 VB (wi=26 → phys=25): reads real TBIN2 VB voltage, well-balanced with VR and VY.
- SDAI2 VY (wi=33 → phys=31): reads real SDAI2 VY voltage, well-balanced with VR and VB.
- SDAI2 VB (wi=34 → phys=32): reads real SDAI2 VB voltage, well-balanced with VR and VY.

All five feeders in the GPTH 275 kV recording now show well-balanced 3-phase voltages
consistent with normal commissioning. The hypothesis of "uncommissioned VT connections"
is withdrawn.

### 6.4 Digital polarity convention — active-low assumed

**Status: Plausible — assumed from quiescent state, unconfirmed by oracle.**

Active-low convention is assumed: stored bit 1 = inactive (normal), stored bit 0 = active
(protection operated). This assumption is consistent with the quiescent state of 0xFFFF
(all bits 1 = all protection functions normally de-energized). However, the specific
mapping of each bit to a relay function and the polarity (normally closed vs normally
open contact) has not been verified from the relay configuration or COMTRADE export.

The transition analysis in §4 applies this assumed polarity.

### 6.5 Digital word_group formula — confirmed by payload analysis

**Status: Confirmed by payload analysis, not oracle-confirmed.**

The formula `sample_word = 37 + word_group` was confirmed by direct payload analysis
of the GPTH recording (groups 1–5 → words 38–42 show digital bit patterns; words 38–42
quiescent at 0xFFFF with narrow range of ~900). The 10 channels with transitions in §4
are concentrated in specific bit positions within words 38–42, consistent with the
formula.

---

## 7. Browser UAT Findings (Stage 8 Summary)

From the Stage 8 Playwright UAT (commit `7fd2324`), 10/10 tests passed:

| Finding | Status |
|---|---|
| Upload via modal → recordings table | PASS |
| Workspace: 35 analog + 40 digital channels shown | PASS |
| Channel names correct (TBIN1 VR/VY/VB/IR/IY/IB) | PASS |
| Analog waveform renders on channel enable | PASS |
| 3-phase voltage waveform renders (VR+VY+VB) | PASS |
| Digital channel present in DOM with `data-timing-reference=relative_elapsed` | PASS |
| X-axis shows elapsed time (no absolute UTC date) | PASS |
| API: `timing_reference="relative_elapsed"` (timestamp safeguard) | PASS |
| No console errors on TBIN1 full channel enable | PASS |

**Observation (not a test failure):** Digital channels with `data-classification="never_triggered"`
are placed in a collapsed group in the channel list (CSS class `channel-row--hidden`).
They can be enabled via DOM dispatch (programmatic click) but require the user to expand
the group in normal browser use. This is existing channel-list behaviour for non-triggered
digital channels, not a BEN5K-specific regression.

**Performance:** Upload and workspace open for an 8262-sample, 75-channel recording completed
in approximately 2–3 seconds at a local server. No performance issues observed during UAT.

---

## 8. Recommendations for Production Readiness

### 8.1 Prerequisites for production support

The following items must be resolved before BEN5K is enabled by default (flag removed):

| Item | Priority | Blocking? |
|---|---|---|
| COMTRADE oracle export from BEN32 | Critical | YES — without oracle, absolute calibration and digital polarity are unconfirmed |
| UTC vs local time confirmation | High | YES — without this, `timing_reference` cannot be changed to `absolute` |
| Resolution of 4 anomalous current channels | High | **RESOLVED** by Stage 10 — phantom correction explains all anomalies; oracle still needed for absolute values |
| Resolution of near-zero voltage channels | Medium | **RESOLVED** by Stage 10 — phantom correction explains all anomalies |
| Digital active-low oracle confirmation | Medium | No — assumed convention is internally consistent; affects interpretation, not decode |

### 8.2 Items confirmed safe for production use

| Item | Evidence |
|---|---|
| BEN5K file detection (signature `28 ff 03 00 …`) | Confirmed; no false-positive on SubBen |
| Channel descriptor walk | 35 active + 45 inactive correctly classified |
| ADC uint16 → int16 → engineering value | Verified spot-check for 6 channels |
| 3-phase voltage balance (TBIN1, SDAI1) | Confirmed well-balanced pre-trigger |
| 3-phase current qualitative behaviour | Confirmed reasonable (TBIN1, SDAI1) |
| Digital transition extraction | 10 channels with transitions correctly found |
| Constant-placeholder classification (0x0800) | 120 channels correctly excluded |
| Timestamp safeguard (relative_elapsed) | Verified via API and browser x-axis |
| No SubBen regression | 73 BEN5K unit tests pass (Stage 10B); full SubBen suite unaffected |
| Browser display, zoom, cursors | 10/10 Playwright tests pass |
| Phantom-channel detection and physical word mapping | 73 BEN5K unit tests pass; all 5 feeder voltage sets balanced (max_dev <1.3%); SDAI2 IB/IN recovered; three decoder bugs found and fixed |

### 8.3 Flag status

`BEN5K_EXPERIMENTAL_ENABLED` should remain **disabled by default** until at minimum:
1. The absolute calibration is oracle-confirmed.
2. The UTC/local time question is resolved.
3. The four anomalous current channels are investigated and explained.

The experimental-data diagnostic (`time_basis_unconfirmed`) is always attached to BEN5K
sources and is visible via the backend API. Users who opt in with the flag see warnings
in the source provenance. This is appropriate for the current experimental status.

---

## 9. Stage 10 — Phantom Channel Detection and Physical Word Mapping

**Analysis date:** 2026-10-22 (Stage 10) / 2026-10-22 (Stage 10B — three decoder bugs fixed)  
**Commits:** `ebba404` (Stage 10), `a61bb65` + Stage 10B fixes  
**Status:** Implemented and tested; 73 BEN5K unit tests pass.

### 9.1 Investigation summary

Stage 10 investigated systematic channel anomalies first documented in Stage 9: four
current channels with voltagestrength amplitudes, four voltage channels near zero or
reading control-word signals, and the unexplained exclusion of SDAI2 IB and IN.

Direct payload analysis of the GPTH recording confirmed that the BEN5K descriptor
`word_index` values are NOT always equal to the physical payload column. Two descriptors
in the config area correspond to channels that were configured in the BEN template but
have no physical recording slot ("phantom channels"). Their presence shifts all subsequent
descriptor word_index values by +1 each.

### 9.2 Confirmed phantom channels

| Descriptor | wi | Physical (wrong) | Signal at wrong phys | Detection method |
|---|---|---|---|---|
| SDAI1 IN (current) | 15 | 15 | SDNK1 VR voltage (raw RMS 11693 ≫ 5000) | Unambiguous: current reads voltage |
| SGT2 VY_LV (voltage) | 27 | 26 (after −1) | TBIN2 IR current (raw RMS 642) | Look-ahead: TBIN2 IN (wi=31) reads voltage at phys=30 under same correction |

SDAI1's physical block omits the IN slot (7 real channels: VR, VY, VB, SGT1_LV, IR, IY, IB).
TBIN2's physical block omits the SGT2_LV slot (7 real channels: VR, VY, VB, IR, IY, IB, IN).

### 9.3 Correction rule

```
physical = wi − correction(wi)

correction(wi) = 0     if wi ≤ 14   (TBIN1 + SDAI1 without IN)
                 1     if 15 ≤ wi ≤ 26  (after SDAI1 IN phantom)
                 2     if wi ≥ 27   (after SDAI1 IN + SGT2 VY_LV phantoms)
```

### 9.4 Physical block structure confirmed

| Block | Physical words | Content |
|---|---|---|
| TBIN1 | 0–7 (8 words) | VR, VY, VB, ctrl, IR, IY, IB, IN |
| SDAI1 | 8–14 (7 words) | VR, VY, VB, SGT1_LV, IR, IY, IB (no IN, no ctrl) |
| SDNK1 | 15–22 (8 words) | VR, VY, VB, ctrl, IR, IY, IB, IN |
| TBIN2 | 23–29 (7 words) | VR, VY, VB, IR, IY, IB, IN (no SGT2_LV, no ctrl) |
| SDAI2 | 30–37 (8 words) | VR, VY, VB, ctrl, IR, IY, IB, IN |
| Digital | 38–42 (5 words) | Bitmask words (groups 1–5) |

Control words are at physical 3 (TBIN1), 18 (SDNK1), 33 (SDAI2) — all reading 3–4
distinct values consistent with a low-amplitude multi-state control or status signal.

### 9.5 All Stage 9 anomalies resolved

| Stage 9 anomaly | Explanation (Stage 10) |
|---|---|
| SDAI1 IN (wi=15) RMS=248 | Was reading SDNK1 VR (phys=15, voltage) with current scale → 11693×0.018709≈219. PHANTOM — excluded. |
| SDNK1 VB (wi=18) near-zero | Was reading control word (phys=18, RMS=32). Correct phys=17 = real SDNK1 VB voltage. |
| SDNK1 IN (wi=23) RMS=248 | Was reading TBIN2 VR (phys=23, voltage) with current scale. Correct phys=22 = real SDNK1 IN (~1.35 kA). |
| TBIN2 VB (wi=26) depressed | Was reading TBIN2 IR current (phys=26, RMS=642). Correct phys=25 = real TBIN2 VB voltage. |
| SGT2 VY_LV (wi=27) | Was reading TBIN2 IR at phys=26. PHANTOM — excluded. |
| TBIN2 IB (wi=30) RMS=248 | Was reading SDAI2 VR (phys=30, voltage) with current scale. Correct phys=28 = real TBIN2 IB (~10.7 kA). |
| TBIN2 IN (wi=31) RMS=213 | Was reading SDAI2 VY (phys=31, voltage) with current scale. Correct phys=29 = real TBIN2 IN (~1.6 kA). |
| SDAI2 VY (wi=33) near-zero | Was reading control word (phys=33, RMS=154). Correct phys=31 = real SDAI2 VY voltage. |
| SDAI2 VB (wi=34) reduced | Was reading SDAI2 IR current (phys=34, RMS=776). Correct phys=32 = real SDAI2 VB voltage. |
| SDAI2 IB/IN (wi=38/39) inactive | Logical wi=38/39 appeared in digital region. Corrected phys=36/37 are in analog region — now active. |

### 9.6 Implementation details

- `Ben5kAnalogChannel` (reader.py): added `physical_word_index` field, initialized to
  `word_index` by `read_channel_descriptors()`; overridden by `classify_channels()`.
- `classify_channels()` (channel_map.py): new `_compute_physical_mapping()` function;
  phantom detection via sequential walk with accumulated correction; uses `physical_word_index`
  (not `wi`) for digital boundary and duplicate-slot checks.
- `decode_samples()` (decoder.py): uses `ch.physical_word_index` for payload column
  selection.
- Stage 10B — three additional bugs fixed and tested (see §9.7). 73 BEN5K unit tests
  pass (reader: 27, decoder: 17, channel_map: 29).

### 9.7 Stage 10B — Three decoder bugs identified and fixed

**Bug 1 — Comment misidentified header field type (reader.py)**

The constant `_WORDS_PER_SAMPLE_OFFSET` had a comment saying `# u32le` but the
implementation correctly uses `struct.unpack_from("<H", ...)` (u16le, 2 bytes). In the
GPTH recording, bytes 0x60–0x63 are `61 00 02 18`; u16le=97 (correct); u32le=402784353
(wrong). Fixed: comment changed to `# u16le`; two new tests confirm non-zero trailing
bytes at 0x62–0x63 are silently ignored.

**Bug 2 — RMS computed on unsigned uint16 instead of signed int16 (channel_map.py)**

`_compute_physical_mapping` computed RMS with `sample_words.astype(np.float64)`. For
sinusoidal signals, the negative half-cycle becomes large unsigned values (~46000),
making all channels appear voltage-strength (RMS >> 5000 threshold). Phantom detection
therefore flagged every current channel as phantom. Fix: added `.astype(np.int16)` before
`.astype(np.float64)`. With signed values: voltage RMS ≈ 11000–12000; current RMS ≈
300–600 — well separated by the 5000 threshold.

**Bug 3 — Look-ahead window depleted by duplicate descriptors (channel_map.py)**

The look-ahead for SGT2 VY_LV phantom detection used
`sorted_chans[i+1 : i+6]` (next 5 raw descriptor positions). The GPTH recording has
multiple inactive-feeder descriptors at wi=28 (TBIN2 IR + SGT2 IR_HV) and wi=29 (TBIN2
IY + SGT2 IY_HV). Those duplicates consumed 4 of the 5 look-ahead slots before wi=31
(TBIN2 IN) was reached, so the look-ahead saw no current-reads-voltage confirmation and
SGT2 VY_LV was not detected as phantom. Fix: look-ahead collects the next 5 *distinct*
word_index values (de-duplicated by wi). One new test
`test_gpth_phantom_layout_with_duplicate_descriptors` verifies the fix.

---

## Appendix A — Full-Record Analogue Statistics

*Stage 10B confirmed (2026-10-22): all 35 channels decoded with phantom-corrected physical
word indices. Values in engineering units (after scale/offset). Analysis script:
`gpth_stage10_analysis.py` against SHA-256 55bf6866… GPTH recording.*

| Name | wi | phys | Min | Max | Full-RMS | Pre-RMS | Post-RMS |
|---|---|---|---|---|---|---|---|
| TBIN1 VR | 0 | 0 | −2710.637 | 2721.116 | 1566.865 | 1782.369 | 1625.804 |
| TBIN1 VY | 1 | 1 | −2695.591 | 2701.771 | 1533.353 | 1767.375 | 1374.729 |
| TBIN1 VB | 2 | 2 | −2708.488 | 2710.369 | 1595.388 | 1804.994 | 1737.091 |
| TBIN1 IR | 4 | 4 | −18.578 | 19.738 | 9.960 | 7.680 | 9.953 |
| TBIN1 IY | 5 | 5 | −20.075 | 20.636 | 10.307 | 8.421 | 10.127 |
| TBIN1 IB | 6 | 6 | −19.177 | 19.439 | 9.320 | 7.826 | 5.620 |
| TBIN1 IN | 7 | 7 | −1.515 | 2.675 | 0.961 | 0.860 | 0.895 |
| SDAI1 VR | 8 | 8 | −2721.385 | 2736.163 | 1574.388 | 1790.937 | 1633.703 |
| SDAI1 VY | 9 | 9 | −2697.740 | 2703.920 | 1534.919 | 1769.184 | 1376.038 |
| SDAI1 VB | 10 | 10 | −2712.787 | 2716.817 | 1599.418 | 1809.720 | 1741.458 |
| SGT1 VY_LV | 11 | 11 | −15.541 | 13.348 | 6.306 | 4.976 | 5.622 |
| SDAI1 IR | 12 | 12 | −2.713 | 5.370 | 2.236 | 1.973 | 1.867 |
| SDAI1 IY | 13 | 13 | −2.413 | 5.370 | 2.207 | 1.987 | 1.796 |
| SDAI1 IB | 14 | 14 | −2.413 | −0.019 | 1.161 | 1.101 | 1.489 |
| SDNK1 VR | 16 | **15** | −2717.086 | 2729.714 | 1570.959 | 1786.718 | 1629.937 |
| SDNK1 VY | 17 | **16** | −2693.442 | 2701.771 | 1532.603 | 1766.676 | 1374.013 |
| SDNK1 VB | 18 | **17** | −2708.488 | 2714.668 | 1596.778 | 1806.525 | 1738.487 |
| SDNK1 IR | 20 | **19** | −11.394 | 12.554 | 5.157 | 1.311 | 2.447 |
| SDNK1 IY | 21 | **20** | −11.095 | 12.554 | 5.319 | 1.658 | 5.944 |
| SDNK1 IB | 22 | **21** | −11.693 | 12.255 | 4.626 | 1.400 | 1.220 |
| SDNK1 IN | 23 | **22** | −3.611 | 4.172 | 1.353 | 0.955 | 2.417 |
| TBIN2 VR | 24 | **23** | −2717.086 | 2727.565 | 1569.836 | 1785.938 | 1628.980 |
| TBIN2 VY | 25 | **24** | −2697.740 | 2701.771 | 1534.302 | 1768.276 | 1375.196 |
| TBIN2 VB | 26 | **25** | −2706.338 | 2708.219 | 1594.205 | 1803.679 | 1736.002 |
| TBIN2 IR | 28 | **26** | −23.069 | 24.528 | 12.028 | 8.999 | 11.829 |
| TBIN2 IY | 29 | **27** | −21.272 | 22.133 | 11.043 | 8.767 | 11.460 |
| TBIN2 IB | 30 | **28** | −21.871 | 23.031 | 10.742 | 8.631 | 6.886 |
| TBIN2 IN | 31 | **29** | −4.808 | 4.771 | 1.631 | 1.182 | 3.021 |
| SDAI2 VR | 32 | **30** | −2693.442 | 2742.611 | 1568.056 | 1783.918 | 1627.659 |
| SDAI2 VY | 33 | **31** | −2678.395 | 2716.817 | 1532.430 | 1766.379 | 1373.102 |
| SDAI2 VB | 34 | **32** | −2699.890 | 2738.312 | 1600.578 | 1811.121 | 1743.193 |
| SDAI2 IR | 36 | **34** | −39.851 | 46.661 | 14.524 | 4.667 | 4.798 |
| SDAI2 IY | 37 | **35** | −39.851 | 47.260 | 16.332 | 7.591 | 19.493 |
| SDAI2 IB | 38 | **36** | −36.857 | 43.368 | 13.024 | 4.967 | 6.609 |
| SDAI2 IN | 39 | **37** | −16.202 | 29.897 | 7.084 | 3.827 | 17.297 |

Bold `phys` = phantom-corrected (wi ≥ 16 shifted by −1; wi ≥ 28 shifted by −2).
Pre-RMS = last 100 samples before trigger (samples 2400–2500, 1 cycle at 50 Hz).
Post-RMS = first 100 samples after trigger (samples 2500–2600).
All values confirmed by Stage 10B analysis script (2026-10-22) against SHA-256 55bf6866…
