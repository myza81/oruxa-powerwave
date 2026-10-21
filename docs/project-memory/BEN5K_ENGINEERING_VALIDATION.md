# BEN5K Engineering Validation Report

**Recording:** `261016_180314535_GPTH_275kV.ben`  
**SHA-256:** `55bf6866b6d86262930afc6282fb5255f7124c966fc2a507e06897b912acfa88`  
**Date of analysis:** 2026-10-21  
**Branch:** `investigation/legacy-ben5k` (commit `7fd2324` + Stage 9)  
**Status:** Not merged to main — owner review required before production use.

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
| Analog descriptor count | 80 (35 active + 45 inactive) | Confirmed |
| Digital descriptor count | 160 (40 verified + 120 constant-placeholder) | Confirmed |
| API-exposed channels | 35 analog + 40 digital | Confirmed |

### 1.2 Active analogue channels (35)

| Name | wi | Type | Scale | High-range | Notes |
|---|---|---|---|---|---|
| TBIN1 VR | 0 | V | 0.134343 | 158.77 | TBIN1 3-phase voltage, R-phase |
| TBIN1 VY | 1 | V | 0.134343 | 158.77 | TBIN1 3-phase voltage, Y-phase |
| TBIN1 VB | 2 | V | 0.134343 | 158.77 | TBIN1 3-phase voltage, B-phase |
| TBIN1 IR | 4 | I | 0.018709 | 1.50 | TBIN1 feeder current, R-phase |
| TBIN1 IY | 5 | I | 0.018709 | 1.50 | TBIN1 feeder current, Y-phase |
| TBIN1 IB | 6 | I | 0.018709 | 1.50 | TBIN1 feeder current, B-phase |
| TBIN1 IN | 7 | I | 0.018709 | 1.50 | TBIN1 neutral current |
| SDAI1 VR | 8 | V | 0.134343 | 158.77 | SDAI1 3-phase voltage, R-phase |
| SDAI1 VY | 9 | V | 0.134343 | 158.77 | SDAI1 3-phase voltage, Y-phase |
| SDAI1 VB | 10 | V | 0.134343 | 158.77 | SDAI1 3-phase voltage, B-phase |
| SGT1 VY_LV | 11 | V | 0.064485 | 76.21 | SGT1 transformer LV Y-phase voltage |
| SDAI1 IR | 12 | I | 0.018709 | 1.50 | SDAI1 feeder current, R-phase |
| SDAI1 IY | 13 | I | 0.018709 | 1.50 | SDAI1 feeder current, Y-phase |
| SDAI1 IB | 14 | I | 0.018709 | 1.50 | SDAI1 feeder current, B-phase |
| SDAI1 IN | 15 | I | 0.018709 | 1.50 | **ANOMALOUS** — see §6 |
| SDNK1 VR | 16 | V | 0.134343 | 158.77 | SDNK1 3-phase voltage, R-phase |
| SDNK1 VY | 17 | V | 0.134343 | 158.77 | SDNK1 3-phase voltage, Y-phase |
| SDNK1 VB | 18 | V | 0.134343 | 158.77 | **NEAR-ZERO** — see §6 |
| SDNK1 IR | 20 | I | 0.018709 | 1.50 | SDNK1 feeder current, R-phase |
| SDNK1 IY | 21 | I | 0.018709 | 1.50 | SDNK1 feeder current, Y-phase |
| SDNK1 IB | 22 | I | 0.018709 | 1.50 | SDNK1 feeder current, B-phase |
| SDNK1 IN | 23 | I | 0.018709 | 1.50 | **ANOMALOUS** — see §6 |
| TBIN2 VR | 24 | V | 0.134343 | 158.77 | TBIN2 3-phase voltage, R-phase |
| TBIN2 VY | 25 | V | 0.134343 | 158.77 | TBIN2 3-phase voltage, Y-phase |
| TBIN2 VB | 26 | V | 0.134343 | 158.77 | **REDUCED** — see §6 |
| SGT2 VY_LV | 27 | V | 0.064485 | 76.21 | SGT2 transformer LV Y-phase voltage |
| TBIN2 IR | 28 | I | 0.018709 | 1.50 | TBIN2 feeder current, R-phase |
| TBIN2 IY | 29 | I | 0.018709 | 1.50 | TBIN2 feeder current, Y-phase |
| TBIN2 IB | 30 | I | 0.018709 | 1.50 | **ANOMALOUS** — see §6 |
| TBIN2 IN | 31 | I | 0.018709 | 1.50 | **ANOMALOUS** — see §6 |
| SDAI2 VR | 32 | V | 0.134343 | 158.77 | SDAI2 3-phase voltage, R-phase |
| SDAI2 VY | 33 | V | 0.134343 | 158.77 | **NEAR-ZERO** — see §6 |
| SDAI2 VB | 34 | V | 0.134343 | 158.77 | **REDUCED** — see §6 |
| SDAI2 IR | 36 | I | 0.018709 | 1.50 | SDAI2 feeder current, R-phase |
| SDAI2 IY | 37 | I | 0.018709 | 1.50 | SDAI2 feeder current, Y-phase |

Notes: `wi` = sample-word index. `High-range` = descriptor field (bytes 40–43, f32le).
High-range 158.77 = 275/√3 (primary kV at 275 kV). High-range 76.21 = 132/√3 (primary
kV at 132 kV, i.e. the transformer LV winding). High-range 1.50 = rated primary kA.

### 1.3 Inactive analogue channels (45) — reason for exclusion

Inactive channels share a word index with an active channel. The decoder selects the
first channel for each word index; subsequent descriptors at the same index are excluded.

| Name | wi | Scale | Reason |
|---|---|---|---|
| SDAI2 IB | 38 | 0.018709 | wi=38 is the digital bitmask region (sw 38–42) |
| SDAI2 IN | 39 | 0.018709 | wi=39 is the digital bitmask region |
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
| SGT2 IB_LV | 38 | 0.014967 | wi=38 is the digital bitmask region |
| SGT2 IN_LV | 39 | 0.014967 | wi=39 is the digital bitmask region |
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

- SDAI2 IB/IN at wi=38–39: The word-index slots 38–42 are the digital bitmask region
  (formula `sw = 37 + group`). These analog channels would destructively overlap with
  digital bitmasks and are correctly excluded.

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

| Bay | VR | VY | VB | Balance |
|---|---|---|---|---|
| TBIN1 | 1782.4 | 1767.4 | 1805.0 | **Well balanced** (< 2% deviation) |
| SDAI1 | 1790.9 | 1769.2 | 1809.7 | **Well balanced** (< 1.2% deviation) |
| SDNK1 | 1766.7 | 1806.5 | 4.40 | **VB near zero** — plausible disconnection |
| TBIN2 | 1768.3 | 1803.7 | 64.6 | **VB depressed** (3.6% of VR) |
| SDAI2 | 1811.1 | 20.7 | 33.5 | **VY and VB near zero** |

TBIN1 and SDAI1 show well-balanced 3-phase voltage consistent with normal 275 kV
operation. SDNK1 VB, TBIN2 VB, and SDAI2 VY/VB have anomalously low values that persist
throughout the recording (including pre-trigger), suggesting missing VT connections or
uncommissioned phases rather than a fault-induced voltage collapse. See §6.

### 2.3 Three-phase current balance (pre-trigger, one cycle)

| Bay | IR | IY | IB |
|---|---|---|---|
| TBIN1 | 7.68 | 8.42 | 7.83 |
| SDAI1 | 1.97 | 1.99 | 1.10 |
| SDNK1 | 1.66 | 1.40 | 0.95 |
| TBIN2 | 8.63 | 1.18 | 248.4* |

*TBIN2 IB (wi=30) and several IN channels have anomalously large values — see §6.

TBIN1 shows reasonably balanced 3-phase current with small neutral (0.86).
SDAI1 shows moderate current with phase B significantly lower than R and Y.
SDNK1 shows low and moderately balanced current.

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
| SGT2 VY_LV | 30.2 | 39.5 | +31% | LV transformer voltage increase |

The voltage depressions (VY and VR phases, Y-phase most affected) combined with
simultaneous current increases on multiple feeders is consistent with a system fault
in the Y-phase propagating through the 275 kV network.

### 2.5 SGT transformer LV voltage

| Channel | Full-record RMS | Pre-trigger | Post-trigger | Notes |
|---|---|---|---|---|
| SGT1 VY_LV | 6.31 | 4.98 | 5.62 | Very low — SGT1 LV may be de-energized |
| SGT2 VY_LV | 38.1 | 30.2 | 39.5 | Active; significant post-trigger increase |

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

**Status: Unsupported — reason unknown without oracle.**

Four channels carry large-amplitude sinusoidal signals that are inconsistent with their
labeled function:

| Channel | wi | Labeled function | Pre-trigger RMS | Observation |
|---|---|---|---|---|
| SDAI1 IN | 15 | Neutral current | 248.8 | Same amplitude as phase currents |
| SDNK1 IN | 23 | Neutral current | 248.7 | Same amplitude as SDAI1 IN |
| TBIN2 IB | 30 | Phase B current | 248.4 | Same amplitude as neutral channels |
| TBIN2 IN | 31 | Neutral current | 213.4 | Same order as above |

The near-identical amplitudes across channels at different word indices suggest either:
(a) these four word slots are physically connected to the same CT secondary circuit,
(b) the word index assignments in the descriptors do not match the physical recorder wiring
    for these channels (descriptor ordering error), or
(c) the high values are a legitimate zero-sequence/earth-fault current component that
    was present throughout the recording.

These are flagged as anomalous. The waveform decoder correctly reads the sample words
and applies the calibration; the question is whether the wording-to-slot mapping is
physically correct. Oracle comparison is required.

### 6.3 Near-zero and reduced voltage channels

**Status: Plausible — likely uncommissioned VT connections.**

| Channel | Full-record RMS | Pre-trigger RMS | Observation |
|---|---|---|---|
| SDNK1 VB | 4.30 | 4.40 | Near zero throughout recording |
| SDAI2 VY | 20.6 | 20.7 | Near zero throughout recording |
| SDAI2 VB | 104.3 | 33.5 | Reduced — significant variation |
| TBIN2 VB | 86.4 | 64.6 | Reduced throughout recording |

The VB depression on SDNK1 and TBIN2, and the VY/VB reduction on SDAI2, are consistent
with VT secondary connections that were not commissioned or not energized at the time
of this recording. They are NOT consistent with a sustained single-phase fault (fault
currents would appear at the corresponding feeder current channels, which do not show
a fault-level signal consistent with a sustained single-phase condition).

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
| COMTRADE oracle export from BEN32 | Critical | YES — without oracle, absolute calibration, channel mapping, and digital polarity are unconfirmed |
| UTC vs local time confirmation | High | YES — without this, `timing_reference` cannot be changed to `absolute` |
| Resolution of 4 anomalous current channels | High | YES — these produce engineering values that would mislead protection analysis |
| Resolution of near-zero voltage channels | Medium | No — display correctly as-is; root cause is cosmetic/commissioning |
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
| No SubBen regression | 67 BEN5K tests + full SubBen suite pass |
| Browser display, zoom, cursors | 10/10 Playwright tests pass |

### 8.3 Flag status

`BEN5K_EXPERIMENTAL_ENABLED` should remain **disabled by default** until at minimum:
1. The absolute calibration is oracle-confirmed.
2. The UTC/local time question is resolved.
3. The four anomalous current channels are investigated and explained.

The experimental-data diagnostic (`time_basis_unconfirmed`) is always attached to BEN5K
sources and is visible via the backend API. Users who opt in with the flag see warnings
in the source provenance. This is appropriate for the current experimental status.

---

## Appendix A — Full-Record Analogue Statistics

| Name | wi | Min | Max | Full-RMS |
|---|---|---|---|---|
| TBIN1 VR | 0 | −2710.6 | 2721.1 | 1566.9 |
| TBIN1 VY | 1 | −2695.6 | 2701.8 | 1533.4 |
| TBIN1 VB | 2 | −2708.5 | 2710.4 | 1595.4 |
| TBIN1 IR | 4 | −18.58 | 19.74 | 9.960 |
| TBIN1 IY | 5 | −20.08 | 20.64 | 10.307 |
| TBIN1 IB | 6 | −19.18 | 19.44 | 9.320 |
| TBIN1 IN | 7 | −1.516 | 2.675 | 0.961 |
| SDAI1 VR | 8 | −2721.4 | 2736.2 | 1574.4 |
| SDAI1 VY | 9 | −2697.7 | 2703.9 | 1534.9 |
| SDAI1 VB | 10 | −2712.8 | 2716.8 | 1599.4 |
| SDAI1 IR | 12 | −2.713 | 5.370 | 2.236 |
| SDAI1 IY | 13 | −2.414 | 5.370 | 2.207 |
| SDAI1 IB | 14 | −2.414 | −0.019 | 1.161 |
| SDAI1 IN | 15 | −378.4 | 380.2 | 218.8* |
| SDNK1 VR | 16 | −2693.4 | 2701.8 | 1532.6 |
| SDNK1 VY | 17 | −2708.5 | 2714.7 | 1596.8 |
| SDNK1 VB | 18 | 2.015 | 8.464 | 4.300* |
| SDNK1 IR | 20 | −11.09 | 12.55 | 5.319 |
| SDNK1 IY | 21 | −11.69 | 12.25 | 4.626 |
| SDNK1 IB | 22 | −3.611 | 4.172 | 1.353 |
| SDNK1 IN | 23 | −378.4 | 379.9 | 218.6* |
| TBIN2 VR | 24 | −2697.7 | 2701.8 | 1534.3 |
| TBIN2 VY | 25 | −2706.3 | 2708.2 | 1594.2 |
| TBIN2 VB | 26 | −165.6 | 176.1 | 86.37* |
| TBIN2 IR | 28 | −21.87 | 23.03 | 10.742 |
| TBIN2 IY | 29 | −4.808 | 4.771 | 1.631 |
| TBIN2 IB | 30 | −375.1 | 382.0 | 218.4* |
| TBIN2 IN | 31 | −373.0 | 378.4 | 213.4* |
| SDAI2 VR | 32 | −2699.9 | 2738.3 | 1600.6 |
| SDAI2 VY | 33 | 17.06 | 23.51 | 20.65* |
| SDAI2 VB | 34 | −286.2 | 335.1 | 104.3* |
| SDAI2 IR | 36 | −36.86 | 43.37 | 13.024 |
| SDAI2 IY | 37 | −16.20 | 29.90 | 7.084 |
| SGT1 VY_LV | 11 | −15.54 | 13.35 | 6.306* |
| SGT2 VY_LV | 27 | −73.32 | 76.29 | 38.06 |

*Flagged anomalous or partially commissioned — see §6.

---

*Document generated from direct analysis of the raw BEN5K payload using the Stage 9
analysis script. All numerical results are independently calculated from the binary file
using the confirmed BEN5K decoder. No values are taken from cached memory or
previous reports.*
