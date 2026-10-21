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


def _analog(name: str, word_index: int) -> Ben5kAnalogChannel:
    return Ben5kAnalogChannel(
        name=name,
        word_index=word_index,
        scale=1.0,
        offset=0.0,
        low_range=-100.0,
        high_range=100.0,
        type_byte=0x00,
        phase_seq=1,
        class_code=0x0528,
        descriptor_offset=0,
    )


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


def test_constant_column_becomes_placeholder():
    # sw=38: all 0x0800 → constant → constant_placeholder_digital (not verified)
    digital = [_digital("CB_OPEN", 1)]  # group 1 → sw=38
    sw = _make_sample_words(10, 97, **{"38": 0x0800})
    cm = classify_channels([], digital, words_per_sample=97, sample_words=sw)
    assert len(cm.constant_placeholder_digital) == 1
    assert cm.constant_placeholder_digital[0].name == "CB_OPEN"
    assert cm.verified_digital == ()
    assert cm.digital_bitmask_word_count == 0


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
