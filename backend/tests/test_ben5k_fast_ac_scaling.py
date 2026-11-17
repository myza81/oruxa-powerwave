"""P1 numerical vectors and exclusions, independent of private-file availability."""
from dataclasses import replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.domain.physical_calibration import CALIBRATION_UNVERIFIED
from app.providers.ben.model import BenChannelKind, BenRecord
from app.providers.ben.legacy_ben5k.engineering import (
    FAST_AC_TRANSFORM_ID,
    fast_ac_engineering_values,
    has_supported_fast_ac_configuration,
    is_supported_fast_ac_descriptor,
)
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.legacy_ben5k.reader import read_channel_descriptors, read_header
from app.providers.ben.normalize import to_disturbance_record
from test_ben5k_normalize import _make_ben5k_fixture

EVIDENCE = json.loads((Path(__file__).parent / "fixtures/ben/ben5k_fast_ac_scaling.json").read_text())


@pytest.mark.parametrize("vector", EVIDENCE["october_vectors"], ids=lambda r: f"{r['record']}-{r['channel']}-{r['sample_index']}")
def test_reviewed_october_scalar_vectors(vector):
    raw = np.array([int(vector["signed_s16"])], dtype=np.int16)
    corrected = fast_ac_engineering_values(raw, float(vector["scale"]), float(vector["offset"]))
    # Frozen pre-implementation investigation values; not a call to a shared
    # expectation helper that could change with the production conversion.
    assert corrected[0] == float(vector["h2"])
    assert raw[0] == int(vector["signed_s16"])


@pytest.mark.parametrize("vector", EVIDENCE["bphe"]["sample_rows"], ids=lambda r: f"{r['name']}-{r['occurrence']}-{r['sample']}")
def test_bphe_export_scalar_vectors(vector):
    corrected = fast_ac_engineering_values(np.array([vector["signed_s16"]], dtype=np.int16), vector["gain"])
    assert corrected[0] == pytest.approx(vector["expected"], rel=3e-8, abs=1e-9)


def test_signed_boundaries_zero_and_low_nibbles_are_measurement_invariant():
    raw = np.array([-32768, -32753, -17, -16, -2, -1, 0, 14, 15, 16, 30, 31, 32752, 32767], dtype=np.int16)
    counts = np.array([-2048, -2048, -2, -1, -1, -1, 0, 0, 0, 1, 1, 1, 2047, 2047])
    result = fast_ac_engineering_values(raw, 1 / math.sqrt(2))
    np.testing.assert_allclose(result, counts, rtol=1e-15, atol=0)
    assert not np.array_equal(result, raw / 16.0)


@pytest.mark.parametrize("raw", [np.array([65535], dtype=np.uint16), np.array([1.0]), np.array([32768]), np.array([-32769])])
def test_numeric_function_refuses_unsigned_float_or_out_of_range_words(raw):
    with pytest.raises(ValueError):
        fast_ac_engineering_values(raw, .125)


@pytest.mark.parametrize("gain,offset", [(.125, 1.0), (.125, -1.0), (.125, float('nan')), (float('inf'), 0), (float('nan'), 0)])
def test_numeric_function_does_not_guess_nonzero_offset_or_nonfinite_gain(gain, offset):
    with pytest.raises(ValueError):
        fast_ac_engineering_values(np.array([-1], dtype=np.int16), gain, offset)


def _record():
    words = np.zeros((20, 40), dtype=">u2")
    words[:, 0] = np.resize(np.array([-18945, 591, 15, 14, 32767, -32753], dtype=np.int16), 20).astype(np.uint16)
    words[:, 38] = np.resize(np.array([0xffff, 0xfffe], dtype=np.uint16), 20)
    data = _make_ben5k_fixture(payload_words=words)
    record = parse_ben5k(data)
    return data, record


def test_unidentified_configuration_keeps_previous_projection_and_authority():
    data, record = _record()
    channel = record.value_channels[0]
    assert not has_supported_fast_ac_configuration(data, read_header(data))
    assert not record.fast_ac_channel_ids
    np.testing.assert_array_equal(record.engineering_values(channel), BenRecord.engineering_values(record, channel))
    normalized = to_disturbance_record(record, source_file="unknown.ben", nominal_frequency_hz=50)
    authority = normalized.analog_channels[0].calibration_authority
    assert authority.status == CALIBRATION_UNVERIFIED
    assert authority.transform_id == "ben5k_v1_raw_s16_linear_scale_offset"


def test_explicit_ac_projection_preserves_words_coefficients_metadata_and_unverified():
    data, base = _record()
    channel = base.value_channels[0]
    # Explicit unit construction exercises the projection in CI; actual source
    # applicability is separately tested with the original configuration hashes.
    record = replace(base, fast_ac_channel_ids=frozenset({channel.channel_id}))
    before = record.sample_words.copy()
    raw = record.raw_values(channel).copy()
    values = record.engineering_values(channel)
    normalized = to_disturbance_record(record, source_file="explicit-ac.ben", nominal_frequency_hz=50)
    np.testing.assert_array_equal(normalized.waveform_data[channel.name], values)
    np.testing.assert_array_equal(record.raw_values(channel), raw)
    np.testing.assert_array_equal(record.sample_words, before)
    assert not record.sample_words.flags.writeable
    assert record.sample_words.base is not None
    assert (record.header, record.value_channels, record.diagnostics) == (base.header, base.value_channels, base.diagnostics)
    assert (normalized.analog_channels[0].scale, normalized.analog_channels[0].offset) == (channel.scale, channel.offset)
    authority = normalized.analog_channels[0].calibration_authority
    assert authority.status == CALIBRATION_UNVERIFIED
    assert authority.transform_id == FAST_AC_TRANSFORM_ID
    assert authority.reason == "ben5k_absolute_calibration_unverified"
    assert np.shares_memory(record.sample_words, np.frombuffer(data, dtype=np.uint8))


@pytest.mark.parametrize("changes", [
    {"offset": 7.25}, {"phase_code": 0}, {"measurement": "dc_voltage"},
    {"kind": BenChannelKind.CALCULATED}, {"quantity_code": 99},
    {"unit": "V"}, {"unit_multiplier_exponent": 0}, {"invalid_raw_value": -32768},
])
def test_projection_never_applies_ac_to_unidentified_or_unsupported_channel(changes):
    _, base = _record()
    channel = replace(base.value_channels[0], **changes)
    record = replace(base, fast_ac_channel_ids=frozenset({channel.channel_id}), value_channels=(channel,))
    assert not record.uses_fast_ac_contract(channel)
    np.testing.assert_array_equal(record.engineering_values(channel), BenRecord.engineering_values(record, channel))


def test_descriptor_guard_requires_matching_unit_phase_and_zero_offset():
    data, _ = _record()
    header = read_header(data)
    channel = read_channel_descriptors(data, header)[0][0]
    # Historical synthetic builder writes KA even for its Voltage descriptor.
    assert not is_supported_fast_ac_descriptor(data, channel)
    matched = bytearray(data)
    matched[channel.descriptor_offset + 20:channel.descriptor_offset + 22] = b"KV"
    assert is_supported_fast_ac_descriptor(bytes(matched), channel)
    assert not is_supported_fast_ac_descriptor(bytes(matched), replace(channel, phase_seq=0))
    assert not is_supported_fast_ac_descriptor(bytes(matched), replace(channel, offset=1.0))
    assert not is_supported_fast_ac_descriptor(bytes(matched), replace(channel, type_byte=99))


@pytest.mark.parametrize("position,value", [(4, 0x2a), (4, 0x29), (6, 2), (14, 6), (60, 1)])
def test_non_fast_or_other_layout_cannot_select_ac_contract(position, value):
    data, _ = _record()
    changed = bytearray(data)
    changed[position] = value
    assert not has_supported_fast_ac_configuration(bytes(changed), read_header(data))
