"""Stage 4 tests: BEN5K channel classification (channel_map.py).

Tests confirm the six-way classification of raw descriptor lists into:
  recorded_analog, inactive_analog, verified_digital, inactive_digital,
  unsupported_digital, constant_placeholder_digital.

No real recording is read here.  All tests use synthetic channel objects.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.providers.ben.legacy_ben5k.reader import Ben5kAnalogChannel, Ben5kDigitalChannel
from app.providers.ben.legacy_ben5k.channel_map import Ben5kChannelMap, classify_channels


# ── Helpers ───────────────────────────────────────────────────────────────────


def _analog(name: str, word_index: int, type_byte: int = 0x00) -> Ben5kAnalogChannel:
    return Ben5kAnalogChannel(
        name=name,
        word_index=word_index,
        physical_word_index=word_index,
        scale=1.0,
        offset=0.0,
        low_range=-100.0,
        high_range=100.0,
        type_byte=type_byte,
        phase_seq=1,
        class_code=0x0528,
        descriptor_offset=0,
    )


def _current(name: str, word_index: int) -> Ben5kAnalogChannel:
    return _analog(name, word_index, type_byte=0x04)


def _digital(name: str, word_group: int, bit_index: int = 0) -> Ben5kDigitalChannel:
    return Ben5kDigitalChannel(
        name=name,
        word_group=word_group,
        bit_index=bit_index,
        polarity_flag=0x01,
        descriptor_offset=0,
    )


# ── Basic classification ───────────────────────────────────────────────────────


def test_empty_inputs():
    cm = classify_channels([], [], words_per_sample=97)
    assert cm.recorded_analog == ()
    assert cm.inactive_analog == ()
    assert cm.verified_digital == ()
    assert cm.inactive_digital == ()
    assert cm.unsupported_digital == ()
    assert cm.constant_placeholder_digital == ()
    assert cm.digital_bitmask_word_count == 0


def test_single_recorded_analog():
    cm = classify_channels([_analog("VR", 0)], [], words_per_sample=97)
    assert len(cm.recorded_analog) == 1
    assert cm.recorded_analog[0].name == "VR"
    assert cm.inactive_analog == ()


def test_single_verified_digital():
    cm = classify_channels([], [_digital("CB_OPEN", 1)], words_per_sample=97)
    assert len(cm.verified_digital) == 1
    assert cm.verified_digital[0].name == "CB_OPEN"
    assert cm.inactive_digital == ()
    assert cm.first_digital_sample_word == 38  # 37 + 1


# ── Duplicate word_index → inactive_analog ────────────────────────────────────


def test_duplicate_word_index_second_is_inactive():
    analog = [_analog("TBIN1 VR", 0), _analog("SDNK2 VR", 0)]  # same wi=0
    cm = classify_channels(analog, [], words_per_sample=97)
    assert len(cm.recorded_analog) == 1
    assert cm.recorded_analog[0].name == "TBIN1 VR"
    assert len(cm.inactive_analog) == 1
    assert cm.inactive_analog[0].name == "SDNK2 VR"


def test_triple_duplicate_word_index():
    analog = [_analog("A", 5), _analog("B", 5), _analog("C", 5)]
    cm = classify_channels(analog, [], words_per_sample=97)
    assert len(cm.recorded_analog) == 1
    assert cm.recorded_analog[0].name == "A"
    assert len(cm.inactive_analog) == 2
    assert {ch.name for ch in cm.inactive_analog} == {"B", "C"}


# ── Analog word_index in digital region → inactive_analog ─────────────────────


def test_analog_wi_in_digital_region_is_inactive():
    # wi=38 is the first digital bitmask word (SDAI2 IB equivalent)
    analog = [_analog("SDAI2 IB", 38)]
    digital = [_digital("CB_OPEN", 1)]  # group 1 → sw=38
    cm = classify_channels(analog, digital, words_per_sample=97)
    assert len(cm.inactive_analog) == 1
    assert cm.inactive_analog[0].name == "SDAI2 IB"
    assert len(cm.recorded_analog) == 0


def test_analog_wi_well_below_digital_region_is_recorded():
    analog = [_analog("VR", 0), _analog("VY", 1)]
    digital = [_digital("CB_OPEN", 1)]  # first_digital_sw=38
    cm = classify_channels(analog, digital, words_per_sample=97)
    assert len(cm.recorded_analog) == 2
    assert len(cm.inactive_analog) == 0


# ── Digital group 0 → unsupported ─────────────────────────────────────────────


def test_group_zero_is_unsupported():
    cm = classify_channels([], [_digital("SENS OUT 1", 0)], words_per_sample=97)
    assert len(cm.unsupported_digital) == 1
    assert cm.unsupported_digital[0].name == "SENS OUT 1"
    assert cm.verified_digital == ()
    assert cm.inactive_digital == ()


def test_group_zero_mixed_with_group_one():
    digital = [_digital("SENS OUT 1", 0), _digital("CB_OPEN", 1)]
    cm = classify_channels([], digital, words_per_sample=97)
    assert len(cm.unsupported_digital) == 1
    assert len(cm.verified_digital) == 1


# ── Inactive digital (constant-0x0800 region) ────────────────────────────────


def test_inactive_digital_group_6_onwards():
    # Groups 1-5 → sw 38-42 are within bounds (wps=43); group 6 → sw=43 >= wps.
    digital = [_digital(f"DIG_G{g}", g) for g in range(1, 7)]
    cm = classify_channels([], digital, words_per_sample=43)
    # Groups 1-5: sw=38..42, all < 43 → 5 verified
    assert len(cm.verified_digital) == 5
    # Group 6: sw=43 >= 43 → inactive
    assert len(cm.inactive_digital) == 1
    assert cm.digital_bitmask_word_count == 5


def test_inactive_digital_many_groups():
    # Groups 1-5 within bounds; groups 6-40 exceed words_per_sample=43.
    digital = [_digital(f"DIG_G{g}", g) for g in range(1, 41)]
    cm = classify_channels([], digital, words_per_sample=43)
    assert len(cm.verified_digital) == 5
    assert len(cm.inactive_digital) == 35


# ── first_digital_sample_word field ──────────────────────────────────────────


def test_first_digital_sample_word_correct():
    digital = [_digital("CB1", 1), _digital("CB2", 2)]
    cm = classify_channels([], digital, words_per_sample=97)
    assert cm.first_digital_sample_word == 38  # 37 + 1


def test_no_verified_digital_first_sw_equals_wps():
    # Only group-0 channels (unsupported) → no bitmask region
    cm = classify_channels([], [_digital("SENS OUT", 0)], words_per_sample=97)
    assert cm.first_digital_sample_word == 97  # equals words_per_sample


# ── GPTH-like scenario (38 analog, 5 verified, inactive on both sides) ────────


def test_gpth_like_scenario():
    # 5 feeders × 8 analog slots = 40 configured analog channels.
    # Active feeder (wi 0-37): first 38 are unique recorded.
    # Inactive feeders sharing wi 0-7: next 2 × 8 = 16 are inactive.
    # SDAI2 IB/IN at wi=38/39: 2 more inactive (wi in digital region).
    # words_per_sample=43: groups 1-5 → sw=38..42 in bounds; group 6+ out of bounds.
    analog = (
        [_analog(f"ACT_{i}", i) for i in range(38)]          # unique, recorded
        + [_analog(f"INACT1_{i}", i) for i in range(8)]      # duplicate wi 0-7
        + [_analog(f"INACT2_{i}", i) for i in range(8)]      # duplicate wi 0-7
        + [_analog("SDAI2 IB", 38), _analog("SDAI2 IN", 39)] # wi in digital region
    )
    digital = [_digital(f"DIG_G{g}", g) for g in range(1, 41)]
    cm = classify_channels(analog, digital, words_per_sample=43)

    assert len(cm.recorded_analog) == 38
    assert len(cm.inactive_analog) == 18  # 16 duplicates + 2 digital-region
    assert len(cm.verified_digital) == 5  # groups 1-5: sw=38..42 < 43
    assert len(cm.inactive_digital) == 35  # groups 6-40: sw >= 43
    assert cm.first_digital_sample_word == 38
    assert cm.digital_bitmask_word_count == 5


# ── Variance-based constant_placeholder_digital detection ─────────────────────


def _make_sample_words(n_samples: int, wps: int, **col_values: int) -> np.ndarray:
    """Build a sample_words array; col_values sets specific columns to a constant."""
    sw = np.zeros((n_samples, wps), dtype=">u2")
    for col, val in col_values.items():
        sw[:, int(col)] = val
    return sw


def test_constant_0x0800_becomes_placeholder():
    # sw=38: all 0x0800 → confirmed placeholder value → constant_placeholder_digital
    digital = [_digital("CB_OPEN", 1)]  # group 1 → sw=38
    sw = _make_sample_words(10, 97, **{"38": 0x0800})
    cm = classify_channels([], digital, words_per_sample=97, sample_words=sw)
    assert len(cm.constant_placeholder_digital) == 1
    assert cm.constant_placeholder_digital[0].name == "CB_OPEN"
    assert cm.verified_digital == ()
    assert cm.digital_bitmask_word_count == 0


def test_constant_non_0x0800_stays_verified():
    # sw=38: constant 0x0000 (not the placeholder value) → verified_digital, not placeholder.
    # e.g. a CB quiescent at 0xFFFF, or any non-0x0800 value, means real channel.
    digital = [_digital("CB_OPEN", 1)]  # group 1 → sw=38
    sw = _make_sample_words(10, 97, **{"38": 0x0000})  # constant but not 0x0800
    cm = classify_channels([], digital, words_per_sample=97, sample_words=sw)
    assert len(cm.verified_digital) == 1
    assert cm.verified_digital[0].name == "CB_OPEN"
    assert cm.constant_placeholder_digital == ()
    assert cm.digital_bitmask_word_count == 1


def test_constant_0xffff_stays_verified():
    # sw=38: constant 0xFFFF = all bits high = all channels inactive in active-low.
    # This is a legitimate quiescent recording, not an inactive-feeder slot.
    digital = [_digital("CB_NORMAL", 1)]
    sw = _make_sample_words(10, 97, **{"38": 0xFFFF})
    cm = classify_channels([], digital, words_per_sample=97, sample_words=sw)
    assert len(cm.verified_digital) == 1
    assert cm.constant_placeholder_digital == ()


def test_varying_column_stays_verified():
    # sw=38: alternating 0x0000/0x0001 → varying → verified_digital
    digital = [_digital("CB_OPEN", 1)]  # group 1 → sw=38
    sw = np.zeros((10, 97), dtype=">u2")
    for i in range(10):
        sw[i, 38] = i % 2
    cm = classify_channels([], digital, words_per_sample=97, sample_words=sw)
    assert len(cm.verified_digital) == 1
    assert cm.constant_placeholder_digital == ()
    assert cm.digital_bitmask_word_count == 1


def test_mixed_constant_and_varying():
    # group 1 (sw=38): varying; group 2 (sw=39): constant 0x0800
    digital = [_digital("CB1", 1), _digital("CB2", 2)]
    sw = np.zeros((10, 97), dtype=">u2")
    for i in range(10):
        sw[i, 38] = i % 2  # varying
    sw[:, 39] = 0x0800     # constant
    cm = classify_channels([], digital, words_per_sample=97, sample_words=sw)
    assert len(cm.verified_digital) == 1
    assert cm.verified_digital[0].name == "CB1"
    assert len(cm.constant_placeholder_digital) == 1
    assert cm.constant_placeholder_digital[0].name == "CB2"
    assert cm.digital_bitmask_word_count == 1


def test_constant_placeholder_does_not_affect_first_digital_sw():
    # first_digital_sw comes from ALL in-bounds channels.
    # group 1 (sw=38): constant; group 2 (sw=39): varying.
    # first_digital_sw must still be 38 (not 39), so analog at wi=38 is excluded.
    digital = [_digital("CB1", 1), _digital("CB2", 2)]
    analog = [_analog("VR", 38)]  # should be inactive (wi=38 = first digital sw)
    sw = np.zeros((10, 97), dtype=">u2")
    sw[:, 38] = 0x0800     # constant
    for i in range(10):
        sw[i, 39] = i % 2  # varying
    cm = classify_channels(analog, digital, words_per_sample=97, sample_words=sw)
    assert cm.first_digital_sample_word == 38
    assert len(cm.inactive_analog) == 1
    assert cm.inactive_analog[0].name == "VR"


def test_no_sample_words_all_in_bounds_are_verified():
    # Without sample_words, all in-bounds channels go to verified_digital.
    digital = [_digital(f"DIG_{g}", g) for g in range(1, 6)]  # groups 1-5, sw 38-42
    cm = classify_channels([], digital, words_per_sample=97)
    assert len(cm.verified_digital) == 5
    assert cm.constant_placeholder_digital == ()


def test_gpth_like_with_variance_detection():
    # Real GPTH scenario (wps=97, groups 1-40, sw 38-77):
    # groups 1-5 (sw 38-42): varying → verified_digital
    # groups 6-40 (sw 43-77): constant 0x0800 → constant_placeholder_digital
    digital = [_digital(f"DIG_G{g}", g) for g in range(1, 41)]
    analog = [_analog(f"ACT_{i}", i) for i in range(38)]
    sw = np.zeros((20, 97), dtype=">u2")
    # sw 38-42: varying
    for i in range(20):
        for col in range(38, 43):
            sw[i, col] = i % 2
    # sw 43-77: constant 0x0800
    for col in range(43, 78):
        sw[:, col] = 0x0800
    cm = classify_channels(analog, digital, words_per_sample=97, sample_words=sw)
    assert len(cm.verified_digital) == 5  # groups 1-5 (one channel descriptor each)
    assert len(cm.constant_placeholder_digital) == 35
    assert len(cm.recorded_analog) == 38
    assert cm.first_digital_sample_word == 38
    assert cm.digital_bitmask_word_count == 5


# ── Stage 10: phantom channel detection and physical_word_index correction ────
#
# The BEN5K flat config area may contain "phantom" descriptors — channels that
# are configured but have no physical recording slot in the payload.  Their
# presence shifts all subsequent descriptor word_indices relative to the
# actual payload columns.
#
# Confirmed phantoms in the GPTH 275 kV recording:
#   - SDAI1 IN  (wi=15): current reading voltage-strength signal at phys 15
#   - SGT2 VY_LV (wi=27 → phys 26 under -1 correction): voltage reading
#     current-like amplitude, confirmed by look-ahead future mismatch
#
# After phantom correction: wi≤14 → phys=wi; 15≤wi≤26 → phys=wi-1; wi≥27 → phys=wi-2


def _make_sw(n_samples: int, wps: int, **col_rms_vals: float) -> np.ndarray:
    """Build sample_words where each named column has approximately the given RMS.

    Uses a constant value equal to floor(rms_val) for each column so that
    raw_rms ≈ rms_val (for constant signals, rms = the constant value).
    """
    sw = np.zeros((n_samples, wps), dtype=">u2")
    for col_str, rms_val in col_rms_vals.items():
        sw[:, int(col_str)] = int(rms_val)
    return sw


def test_phantom_current_reads_voltage_is_excluded():
    """A current descriptor at wi=X where physical X carries a voltage-strength
    signal (rms > 5000) is a phantom and excluded from recorded_analog.

    The phantom's physical slot is consumed by the next VOLTAGE descriptor.
    A subsequent CURRENT descriptor is then correctly mapped one position earlier.

    Layout:
      wi=0,1: voltages (phys=0,1, rms=11000)
      wi=2:   PHANTOM_I current (phys=2, rms=11000) → correction=1
      wi=3:   VZ voltage (phys=2 after -1, rms=11000) → consumes phantom slot
      wi=4:   REAL_I current (phys=3 after -1, rms=500) → recorded at phys=3
    """
    analog = [
        _analog("VR", 0), _analog("VY", 1),
        _current("PHANTOM_I", 2),
        _analog("VZ", 3),
        _current("REAL_I", 4),
    ]
    sw = _make_sw(10, 10, **{"0": 11000, "1": 11000, "2": 11000, "3": 500})
    cm = classify_channels(analog, [], words_per_sample=10, sample_words=sw)
    names_recorded = {ch.name for ch in cm.recorded_analog}
    names_inactive = {ch.name for ch in cm.inactive_analog}
    assert "PHANTOM_I" not in names_recorded
    assert "PHANTOM_I" in names_inactive
    assert "REAL_I" in names_recorded
    # REAL_I must land at physical word 3 (one phantom before it; VZ consumed phys=2)
    real_i = next(ch for ch in cm.recorded_analog if ch.name == "REAL_I")
    assert real_i.physical_word_index == 3


def test_phantom_voltage_reads_current_with_lookahead():
    """A voltage descriptor in the current-like amplitude range is a phantom when
    a subsequent current descriptor would also read a voltage-strength signal."""
    # wi=2: voltage, phys=2 → rms=600 (current-like, ambiguous)
    # wi=3: current, phys=3 → rms=11000 (voltage-strength) → future mismatch!
    # → wi=2 (voltage) is a phantom; wi=3 (current) should map to phys=2
    analog = [_analog("VR", 0), _analog("VY", 1), _analog("PHANTOM_V", 2), _current("REAL_I", 3)]
    sw = _make_sw(10, 10, **{"0": 11000, "1": 11000, "2": 600, "3": 11000})
    cm = classify_channels(analog, [], words_per_sample=10, sample_words=sw)
    names_recorded = {ch.name for ch in cm.recorded_analog}
    names_inactive = {ch.name for ch in cm.inactive_analog}
    assert "PHANTOM_V" not in names_recorded
    assert "PHANTOM_V" in names_inactive
    assert "REAL_I" in names_recorded
    real_i = next(ch for ch in cm.recorded_analog if ch.name == "REAL_I")
    assert real_i.physical_word_index == 2


def test_phantom_lookahead_requires_future_mismatch():
    """A voltage in the current-like amplitude range is NOT a phantom when no
    subsequent current descriptor has a voltage-strength signal."""
    # wi=2: voltage, phys=2 → rms=600 (ambiguous)
    # wi=3: current, phys=3 → rms=400 (plausible current, NOT a mismatch)
    # → wi=2 stays recorded at physical 2
    analog = [_analog("VR", 0), _analog("VY", 1), _analog("SMALL_V", 2), _current("REAL_I", 3)]
    sw = _make_sw(10, 10, **{"0": 11000, "1": 11000, "2": 600, "3": 400})
    cm = classify_channels(analog, [], words_per_sample=10, sample_words=sw)
    names_recorded = {ch.name for ch in cm.recorded_analog}
    assert "SMALL_V" in names_recorded
    small_v = next(ch for ch in cm.recorded_analog if ch.name == "SMALL_V")
    assert small_v.physical_word_index == 2


def test_small_transformer_lv_voltage_not_phantom():
    """A voltage descriptor with rms below _PHANTOM_VOLTAGE_LOWER_BOUND (300) is
    never treated as a phantom, even if subsequent currents have no mismatch."""
    # wi=2: voltage, phys=2 → rms=98 (small transformer LV, like SGT1_VY_LV)
    analog = [_analog("VR", 0), _analog("SGT_LV", 2), _current("IR", 3)]
    sw = _make_sw(10, 10, **{"0": 11000, "2": 98, "3": 400})
    cm = classify_channels(analog, [], words_per_sample=10, sample_words=sw)
    assert "SGT_LV" in {ch.name for ch in cm.recorded_analog}
    sgt = next(ch for ch in cm.recorded_analog if ch.name == "SGT_LV")
    assert sgt.physical_word_index == 2


def test_two_phantoms_double_correction():
    """Two phantom channels produce a cumulative correction of -2.

    Mirrors the GPTH structure: one current phantom then one voltage phantom
    detected via look-ahead.  A voltage descriptor between them "consumes"
    the shifted position so there is no cascade.

    Layout (matching the GPTH detection pattern):
      wi=0..2: voltages (phys=0..2, rms=11000)
      wi=3:    CURRENT PHANTOM1 (phys=3, rms=11000) → correction=1
      wi=4..5: voltages (phys=3..4 after -1, rms=11000) → absorb shift, recorded
      wi=6:    VOLTAGE PHANTOM2 (phys=5 after -1, rms=600); look-ahead wi=7
               current maps to phys=6 (after -1, rms=11000) → future_mismatch → correction=2
      wi=7:    current (phys=5 after -2, rms=600) → recorded at phys=5
    """
    analog = [
        _analog("V0", 0), _analog("V1", 1), _analog("V2", 2),
        _current("PHANT1", 3),                        # current phantom
        _analog("V3", 4), _analog("V4", 5),           # voltages consume phantom shift
        _analog("PHANT2", 6),                          # voltage phantom via look-ahead
        _current("I_REAL", 7),                         # real current, corrected to phys=5
    ]
    sw = _make_sw(10, 10, **{
        "0": 11000, "1": 11000, "2": 11000,
        "3": 11000,   # phys=3: voltage-strength → phantom for wi=3 current
        "4": 11000,   # phys=4: voltage for wi=4 after -1
        "5": 600,     # phys=5: current-like → ambiguous for wi=6 voltage (PHANT2)
        "6": 11000,   # phys=6: voltage-strength → future-mismatch trigger for wi=7 current
    })
    cm = classify_channels(analog, [], words_per_sample=10, sample_words=sw)
    inactive_names = {ch.name for ch in cm.inactive_analog}
    recorded_names = {ch.name for ch in cm.recorded_analog}
    assert "PHANT1" in inactive_names
    assert "PHANT2" in inactive_names
    assert "I_REAL" in recorded_names
    i_real = next(ch for ch in cm.recorded_analog if ch.name == "I_REAL")
    assert i_real.physical_word_index == 5  # wi=7 − 2 = phys=5


def test_gpth_phantom_layout():
    """Synthetic layout matching the GPTH 275 kV recording structure.

    Two phantoms:
      - wi=15 (current) reads voltage-strength at phys=15 → correction=1
      - wi=27 (voltage) reads current-like at phys=26 (after -1); look-ahead
        wi=31 (current) reads voltage at phys=30 (after -1) → correction=2

    After correction:
      - wi=38 (current) → phys=36: in analog region (< first_digital_sw=38)
      - wi=39 (current) → phys=37: in analog region (< first_digital_sw=38)
    """
    # Build descriptors matching the GPTH structure:
    #   wi=0-14:  TBIN1 + SDAI1 (14 channels)
    #   wi=15:    SDAI1 IN (current, phantom)
    #   wi=16-26: SDNK1 + TBIN2 VR,VY,VB (11 channels, voltages)
    #   wi=27:    SGT2 VY_LV (voltage, phantom)
    #   wi=28-37: TBIN2 IR,IY,IB,IN + SDAI2 VR,VY,VB,[ctrl],IR,IY
    #   wi=38-39: SDAI2 IB, IN (current)
    # Digital: group 1 → sw=38

    analog = (
        [_analog(f"TBIN1_SDAI1_{i}", i) for i in range(15)]    # wi=0..14
        + [_current("SDAI1_IN", 15)]                             # wi=15: phantom current
        + [_analog(f"SDNK1_TBIN2_V_{i}", i) for i in range(16, 27)]  # wi=16..26
        + [_analog("SGT2_VY_LV", 27)]                            # wi=27: phantom voltage
        + [_current(f"TBIN2_IR_{i}", i) for i in range(28, 32)] # wi=28..31 (currents)
        + [_analog(f"SDAI2_V_{i}", i) for i in range(32, 38)]   # wi=32..37
        + [_current("SDAI2_IB", 38)]                             # wi=38: should become active
        + [_current("SDAI2_IN", 39)]                             # wi=39: should become active
    )
    digital = [_digital("CB_OPEN", 1)]  # group 1 → sw=38

    # Build sample_words:
    # Physical col  Signal
    #  0..14        voltages (~11000 rms)
    # 15..17        voltages (SDNK1 VR,VY,VB after correction)
    # 18            CONTROL (small, ~30 rms)
    # 19..22        currents (SDNK1 IR,IY,IB,IN ~300 rms)
    # 23..25        voltages (TBIN2 VR,VY,VB ~11000)
    # 26..29        currents (TBIN2 IR,IY,IB,IN ~500)
    # 30..32        voltages (SDAI2 VR,VY,VB ~11000)
    # 33            CONTROL (~30 rms)
    # 34..37        currents (SDAI2 IR,IY,IB,IN ~600)
    # 38..42        digital bitmask (varying)
    wps = 97
    n_samples = 20
    sw = np.zeros((n_samples, wps), dtype=">u2")

    # Voltage positions: 0-14, 15-17, 23-25, 30-32
    for col in list(range(15)) + [15, 16, 17, 23, 24, 25, 30, 31, 32]:
        sw[:, col] = 11000

    # Current positions: 19-22, 26-29, 34-37
    for col in list(range(19, 23)) + list(range(26, 30)) + list(range(34, 38)):
        sw[:, col] = 500

    # Control positions: 18, 33
    sw[:, 18] = 30
    sw[:, 33] = 30

    # Digital: varying
    for i in range(n_samples):
        sw[i, 38] = i % 2

    cm = classify_channels(analog, digital, words_per_sample=wps, sample_words=sw)

    recorded_names = {ch.name for ch in cm.recorded_analog}
    inactive_names = {ch.name for ch in cm.inactive_analog}

    # Phantoms must be excluded
    assert "SDAI1_IN" in inactive_names
    assert "SGT2_VY_LV" in inactive_names

    # SDAI2 IB and IN must now be recorded (physical words 36, 37)
    assert "SDAI2_IB" in recorded_names
    assert "SDAI2_IN" in recorded_names

    sdai2_ib = next(ch for ch in cm.recorded_analog if ch.name == "SDAI2_IB")
    sdai2_in = next(ch for ch in cm.recorded_analog if ch.name == "SDAI2_IN")
    assert sdai2_ib.physical_word_index == 36
    assert sdai2_in.physical_word_index == 37

    # SDNK1_TBIN2_V_16 (wi=16) must be at physical 15 (after -1 correction)
    v16 = next(ch for ch in cm.recorded_analog if ch.name == "SDNK1_TBIN2_V_16")
    assert v16.physical_word_index == 15

    # TBIN2_IR_28 (wi=28) must be at physical 26 (after -2 correction)
    tbin2_ir = next(ch for ch in cm.recorded_analog if ch.name == "TBIN2_IR_28")
    assert tbin2_ir.physical_word_index == 26

    # SDAI2_V_32 (wi=32) must be at physical 30 (after -2 correction)
    sdai2_vr = next(ch for ch in cm.recorded_analog if ch.name == "SDAI2_V_32")
    assert sdai2_vr.physical_word_index == 30
