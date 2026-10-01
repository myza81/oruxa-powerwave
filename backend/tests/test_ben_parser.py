"""Native BEN parser: synthetic-file tests (always run, no owner data).

Files come from tests/ben/synthetic_ben.py, which restates the layout in
docs/project-memory/BEN_FORMAT.md independently of the parser. The real
owner records are exercised by test_ben_reference_files.py.
"""

from __future__ import annotations

import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from app.providers.base import ProviderLoadError
from app.providers.ben import (
    BenChannelKind,
    BenDigitalSource,
    BenNotRecognizedError,
    BenProvider,
    BenRecordClass,
    BenStructureError,
    BenTruncatedError,
    BenUnsupportedVariantError,
    parse_ben,
    to_disturbance_record,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "ben"))
from synthetic_ben import SynthBen, SynthDigital, SynthValue, active_low, to_word  # noqa: E402

N = 40


def _fast(**kwargs) -> SynthBen:
    """1200 samples/s, 7 words (14-byte stride), values at words 2/4/6,
    binaries in words 0 and 3 -- unlike any reference file on purpose."""
    n = kwargs.pop("n", N)
    words = np.zeros((n, 7), dtype=np.uint16)
    i = np.arange(n)
    words[:, 2] = to_word(i * 25 - 300)
    words[:, 4] = to_word((i % 7) * 100 - 350)
    words[:, 6] = to_word(-(i % 3))
    cb_open = (i >= 15).astype(np.uint16)
    over = ((i >= 10) & (i < 20)).astype(np.uint16)
    words[:, 0] = (active_low(cb_open) << 3) | (active_low(np.zeros(n)) << 15)
    words[:, 3] = active_low(np.zeros(n)) | (active_low(over) << 7)
    spec = SynthBen(
        record_class="fast",
        rate_field=1_200_000,
        pre_trigger=10,
        words_per_sample=7,
        values=[
            SynthValue(10000, "BAY1 VR", word=2, scale=0.25, primary=400.0, secondary=110.0, bay="FEEDER BAY1"),
            SynthValue(10001, "BAY1 IR", word=4, unit_code=5, quantity_code=4, scale=0.01, primary=2.0, secondary=1.0, bay="FEEDER BAY1"),
            SynthValue(10002, "BAY1 IN", word=6, unit_code=5, quantity_code=4, phase_code=4, scale=0.01, primary=2.0, secondary=1.0, bay="FEEDER BAY1"),
        ],
        digitals=[
            SynthDigital("derived", 20000, "OVER BAY1 VR", word=3, bit=7, source_channel_id=10000, bay="FEEDER BAY1"),
            SynthDigital("physical", 11000, "BAY1 CB OPEN", word=0, bit=3, event_name="Level BAY1 CB OPEN", bay="FEEDER BAY1"),
            SynthDigital("physical", 11001, "SPARE", word=0, bit=15, event_name="Level SPARE"),
            SynthDigital("physical", 11002, "SPARE", word=3, bit=0, event_name="Level SPARE"),
        ],
        samples=words,
    )
    for key, value in kwargs.items():
        setattr(spec, key, value)
    return spec


def _slow() -> SynthBen:
    """20 samples/s calculated channels (Hz, MW) with unavailable samples."""
    n = 30
    words = np.zeros((n, 5), dtype=np.uint16)
    i = np.arange(n)
    freq = np.where(i < 5, -32768, (i - 15) * 20)
    words[:, 0] = to_word(i * 3 - 40)  # MW
    words[:, 4] = to_word(freq)  # Hz
    words[:, 2] = active_low((i >= 12).astype(np.uint16)) << 4
    return SynthBen(
        record_class="slow",
        rate_field=20_000,
        pre_trigger=8,
        words_per_sample=5,
        values=[
            SynthValue(12000, "POWER LINE1", word=0, unit_code=38, multiplier=6, phase_code=0, quantity_code=14, scale=2.25, bay="FEEDER LINE1"),
            SynthValue(12001, "FREQ LINE1 VY", word=4, unit_code=33, multiplier=0, phase_code=2, quantity_code=14, scale=0.0005, offset=50.0, bay="FEEDER LINE1"),
        ],
        digitals=[SynthDigital("derived", 20060, "FREQ LINE1 VY", word=2, bit=4, source_channel_id=12001)],
        samples=words,
    )


def _parse(spec: SynthBen):
    data, offsets = spec.build()
    return parse_ben(data), data, offsets


# ─────────────────────────────────────────────────────────────────────────────
# Header, layout and channel decoding
# ─────────────────────────────────────────────────────────────────────────────


def test_header_facts_come_from_the_file():
    record, data, offsets = _parse(_fast())
    h = record.header
    assert h.record_class is BenRecordClass.FAST
    assert h.record_class_code == 1006
    assert h.rate_field == 1_200_000
    assert h.sampling_rate_hz == 1200.0
    assert h.sample_count == N
    assert h.pre_trigger_samples == 10
    assert h.words_per_sample == 7
    assert h.sample_stride_bytes == 14
    assert h.sample_data_offset == offsets["data"]
    assert h.sample_data_offset + N * 14 == len(data)
    assert (h.station_name, h.recorder_unit_id, h.record_number) == ("SYNTH STATION", 4321, 777)
    assert h.record_label == "New Record"
    assert h.trigger_time.fraction_digits == (12, 34, 56)
    assert h.trigger_time_utc == datetime(2024, 3, 5, 6, 7, 8, 123456, tzinfo=timezone.utc)
    assert h.trigger_time_utc.utcoffset().total_seconds() == 0  # timezone-aware UTC
    assert h.pre_trigger_seconds == pytest.approx(10 / 1200)
    assert h.start_time_utc == datetime(2024, 3, 5, 6, 7, 8, 123456 - 8333, tzinfo=timezone.utc)


def test_value_channels_decode_raw_scaling_units_and_ratings():
    spec = _fast()
    record, _, _ = _parse(spec)
    assert [c.name for c in record.value_channels] == ["BAY1 VR", "BAY1 IR", "BAY1 IN"]
    vr, ir, in_ = record.value_channels
    assert [c.slot.word_index for c in record.value_channels] == [2, 4, 6]
    assert vr.kind is BenChannelKind.ANALOG
    assert (vr.unit, vr.measurement, vr.phase) == ("kV", "voltage", "A")
    assert (ir.unit, ir.measurement, ir.phase) == ("kA", "current", "A")
    assert in_.phase == "N"
    assert (vr.primary_rating, vr.secondary_rating) == (400.0, 110.0)
    assert vr.secondary_rating_in_channel_unit == pytest.approx(0.110)
    assert vr.bay_name == "FEEDER BAY1"
    assert vr.invalid_raw_value is None
    for channel, word in zip(record.value_channels, (2, 4, 6)):
        expected_raw = spec.samples[:, word].astype(np.uint16).view(np.int16)
        np.testing.assert_array_equal(record.raw_values(channel), expected_raw)
        np.testing.assert_allclose(
            record.engineering_values(channel), expected_raw * channel.scale + channel.offset
        )


def test_digital_channels_follow_descriptor_links_and_are_active_low():
    record, _, _ = _parse(_fast())
    names = [c.name for c in record.digital_channels]
    assert names == ["OVER BAY1 VR", "BAY1 CB OPEN", "SPARE", "SPARE"]
    over, cb, spare_a, spare_b = record.digital_channels
    assert over.source is BenDigitalSource.DERIVED
    assert (over.bit_channel_id, over.source_channel_id) == (20000, 10000)
    assert cb.source is BenDigitalSource.PHYSICAL
    assert cb.event_name == "Level BAY1 CB OPEN"
    assert (cb.slot.word_index, cb.slot.bit) == (0, 3)
    assert (spare_b.slot.word_index, spare_b.slot.bit) == (3, 0)
    assert cb.bay_name == "FEEDER BAY1" and spare_a.bay_name is None

    i = np.arange(N)
    np.testing.assert_array_equal(record.digital_states(cb), (i >= 15).astype(np.int8))
    np.testing.assert_array_equal(record.digital_states(over), ((i >= 10) & (i < 20)).astype(np.int8))
    np.testing.assert_array_equal(record.stored_bits(cb), 1 - (i >= 15))
    np.testing.assert_array_equal(record.digital_states(spare_a), np.zeros(N, dtype=np.int8))


def test_slow_record_carries_calculated_quantities_and_unavailable_samples():
    spec = _slow()
    record, _, _ = _parse(spec)
    h = record.header
    assert h.record_class is BenRecordClass.SLOW
    assert (h.sampling_rate_hz, h.sample_count, h.sample_stride_bytes) == (20.0, 30, 10)
    power, freq = record.value_channels
    assert power.kind is freq.kind is BenChannelKind.CALCULATED
    assert (power.unit, power.measurement, power.phase) == ("MW", "active_power", None)
    assert (freq.unit, freq.measurement, freq.phase) == ("Hz", "frequency", "B")
    assert power.primary_rating is None and power.hardware_address is None
    assert freq.invalid_raw_value == -32768

    valid = record.valid_mask(freq)
    assert valid.tolist() == [False] * 5 + [True] * 25
    values = record.engineering_values(freq)
    assert np.isnan(values[:5]).all()
    raw = spec.samples[5:, 4].astype(np.uint16).view(np.int16)
    np.testing.assert_allclose(values[5:], raw.astype(np.float64) * freq.scale + 50.0)
    assert freq.scale == pytest.approx(0.0005)
    np.testing.assert_array_equal(record.raw_values(freq)[:5], [-32768] * 5)  # raw kept
    assert record.valid_mask(power).all()

    (trip,) = record.digital_channels
    np.testing.assert_array_equal(record.digital_states(trip), (np.arange(30) >= 12).astype(np.int8))
    assert _codes(record) >= {"unavailable_samples", "duplicate_channel_names"}


def test_raw_minimum_on_a_sampled_analog_input_is_kept_as_a_measurement():
    spec = _fast()
    spec.samples[3, 6] = to_word([-32768])[0]
    record, _, _ = _parse(spec)
    channel = record.value_channel("BAY1 IN")
    assert channel.invalid_raw_value is None
    assert record.valid_mask(channel).all()
    assert record.engineering_values(channel)[3] == pytest.approx(-32768 * channel.scale)
    assert "unverified_raw_extreme" in _codes(record)


def test_sample_words_are_a_read_only_view_over_the_file_bytes():
    record, data, _ = _parse(_fast())
    assert not record.sample_words.flags.writeable
    assert np.shares_memory(record.sample_words, np.frombuffer(data, dtype=np.uint8))
    assert record.sample_words.shape == (N, 7)


# ─────────────────────────────────────────────────────────────────────────────
# Guardrails: nothing from a particular reference file is assumed
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("record_class", "rate_field", "words", "value_words", "n", "pre"),
    [
        # 20 samples/s Fast record, 2-word stride, value in the very first word.
        ("fast", 20_000, 2, [0], 9, 0),
        # 10 kHz Fast record, 30 channels starting at word 9 (byte 18), 45-word stride.
        ("fast", 10_000_000, 45, list(range(9, 39)), 25, 24),
        # 5 kHz Slow record (class is independent of rate), 3-word stride.
        ("slow", 5_000_000, 3, [1, 2], 12, 3),
        # Non-integral samples/s (rate field not a multiple of 1000).
        ("fast", 1_234_567, 4, [3], 6, 1),
    ],
)
def test_layout_is_derived_from_the_file_not_assumed(record_class, rate_field, words, value_words, n, pre):
    samples = np.zeros((n, words), dtype=np.uint16)
    values = []
    for k, word in enumerate(value_words):
        samples[:, word] = to_word(np.arange(n) * (k + 1) - k)
        unit = (29, 3) if record_class == "fast" else (33, 0)
        values.append(SynthValue(10000 + k if record_class == "fast" else 12000 + k, f"CH{k}", word=word, unit_code=unit[0], multiplier=unit[1]))
    spec = SynthBen(record_class=record_class, rate_field=rate_field, pre_trigger=pre, words_per_sample=words, values=values, samples=samples)
    record, data, offsets = _parse(spec)

    h = record.header
    assert h.record_class is (BenRecordClass.FAST if record_class == "fast" else BenRecordClass.SLOW)
    assert h.sampling_rate_hz == pytest.approx(rate_field / 1000)
    assert (h.sample_count, h.pre_trigger_samples, h.words_per_sample) == (n, pre, words)
    assert h.sample_stride_bytes == 2 * words
    assert h.sample_data_offset == offsets["data"] == len(data) - n * 2 * words
    assert len(record.value_channels) == len(value_words)
    for k, channel in enumerate(record.value_channels):
        assert channel.slot.word_index == value_words[k]
        np.testing.assert_array_equal(record.raw_values(channel), np.arange(n) * (k + 1) - k)
    np.testing.assert_allclose(np.diff(record.time_axis()), 1000 / rate_field)


# ─────────────────────────────────────────────────────────────────────────────
# Normalization into DisturbanceRecord
# ─────────────────────────────────────────────────────────────────────────────


def test_fast_record_normalizes_into_a_valid_disturbance_record():
    record, _, _ = _parse(_fast())
    dr = to_disturbance_record(record, source_file="synthetic.ben", nominal_frequency_hz=60.0)
    assert dr.validate() == []
    assert list(dr.waveform_data.columns) == [
        "time", "BAY1 VR", "BAY1 IR", "BAY1 IN", "OVER BAY1 VR", "BAY1 CB OPEN", "SPARE", "SPARE_1",
    ]
    assert [c.name for c in dr.digital_channels] == ["OVER BAY1 VR", "BAY1 CB OPEN", "SPARE", "SPARE_1"]
    vr = dr.analog_channels[0]
    assert (vr.unit, vr.phase, vr.parameter_type, vr.index) == ("kV", "A", "voltage", 1)
    assert (vr.primary_ratio, vr.secondary_ratio) == (400.0, pytest.approx(0.11))
    assert dr.analog_channels[1].parameter_type == "current"
    np.testing.assert_allclose(dr.waveform_data["BAY1 VR"], record.engineering_values(record.value_channels[0]))
    assert dr.waveform_data["BAY1 CB OPEN"].dtype == np.int8
    assert dr.waveform_data["BAY1 CB OPEN"].tolist() == [0] * 15 + [1] * 25
    np.testing.assert_allclose(dr.waveform_data["time"].to_numpy(), np.arange(N) / 1200.0)

    assert dr.metadata.provider_type == "BEN"
    assert dr.metadata.station_name == "SYNTH STATION"
    assert dr.metadata.recorder_name == "4321"
    assert dr.metadata.nominal_frequency == 60.0
    assert dr.metadata.timezone == dr.timing_info.timezone == "UTC"
    assert dr.timing_info.trigger_time == record.header.trigger_time_utc
    assert dr.timing_info.trigger_time.tzinfo is not None and dr.timing_info.start_time.tzinfo is not None
    assert dr.timing_info.start_time == record.header.start_time_utc
    assert dr.sampling_info.sampling_rates == [1200.0]
    assert dr.sampling_info.samples_per_rate == [N]


def test_slow_record_normalizes_calculated_channels_with_nan_for_unavailable():
    record, _, _ = _parse(_slow())
    dr = to_disturbance_record(record, source_file="slow.ben", nominal_frequency_hz=50.0)
    assert dr.validate() == []
    power, freq = dr.analog_channels
    assert (power.unit, power.parameter_type) == ("MW", "active power")
    assert (freq.unit, freq.parameter_type) == ("Hz", "frequency")
    assert power.primary_ratio is None and power.secondary_ratio is None
    assert dr.waveform_data["FREQ LINE1 VY"].isna().sum() == 5
    # The derived binary shares its name with a value channel -> suffixed column.
    assert [c.name for c in dr.digital_channels] == ["FREQ LINE1 VY_1"]


def test_names_are_exact_in_the_record_and_trimmed_when_normalized():
    spec = _fast()
    spec.values[0].name = " BAY1 VR "
    spec.digitals[1].name = "BAY1 CB OPEN "
    record, _, _ = _parse(spec)
    assert record.value_channels[0].name == " BAY1 VR "
    assert record.digital_channels[1].name == "BAY1 CB OPEN "
    dr = to_disturbance_record(record, source_file="x.ben", nominal_frequency_hz=50.0)
    assert dr.analog_channels[0].name == "BAY1 VR"
    assert dr.digital_channels[1].name == "BAY1 CB OPEN"
    assert dr.validate() == []


@pytest.mark.parametrize("bad", [0.0, -50.0, float("nan"), float("inf")])
def test_normalization_requires_an_explicit_nominal_frequency(bad):
    record, _, _ = _parse(_fast())
    with pytest.raises(ValueError):
        to_disturbance_record(record, source_file="x.ben", nominal_frequency_hz=bad)


def test_provider_loads_ben_files_only(tmp_path):
    data, _ = _fast().build()
    path = tmp_path / "record.BEN"
    path.write_bytes(data)
    provider = BenProvider(nominal_frequency_hz=50.0)
    assert provider.can_load(path)
    assert not provider.can_load(tmp_path / "record.cfg")
    dr = provider.load(path)
    assert dr.metadata.source_file == str(path)
    assert dr.validate() == []


def test_provider_failure_is_a_provider_load_error(tmp_path):
    path = tmp_path / "broken.ben"
    path.write_bytes(b"not a ben file" * 40)
    with pytest.raises(ProviderLoadError):
        BenProvider(nominal_frequency_hz=50.0).load(path)


# ─────────────────────────────────────────────────────────────────────────────
# Defensive parsing
# ─────────────────────────────────────────────────────────────────────────────


def _patched(spec: SynthBen, edits) -> bytes:
    data, offsets = spec.build()
    buf = bytearray(data)
    edits(buf, offsets)
    return bytes(buf)


def _layout_entry(offsets, i: int) -> int:
    return offsets["layout_entries"] + 6 * i


def test_non_ben_bytes_are_not_recognized():
    with pytest.raises(BenNotRecognizedError):
        parse_ben(bytes(range(256)) * 4)
    with pytest.raises(BenNotRecognizedError):
        parse_ben(b"")


def test_header_shorter_than_its_fixed_size_is_truncated():
    data, _ = _fast().build()
    with pytest.raises(BenTruncatedError):
        parse_ben(data[:100])


@pytest.mark.parametrize(
    ("offset", "value"),
    [
        (0x04, b"\x28\xff"),  # older BEN layout discriminator
        (0x0E, b"\x05\x00"),  # older generation marker
        (0x06, b"\x04\x00"),
    ],
)
def test_unvalidated_layout_signature_is_rejected(offset, value):
    def edit(buf, _):
        buf[offset : offset + len(value)] = value

    with pytest.raises(BenUnsupportedVariantError):
        parse_ben(_patched(_fast(), edit))


def test_truncated_sample_data_is_rejected_not_shortened():
    data, _ = _fast().build()
    with pytest.raises(BenTruncatedError):
        parse_ben(data[:-1])
    with pytest.raises(BenTruncatedError):
        parse_ben(data[:-14])


def test_bytes_beyond_the_declared_samples_are_rejected():
    data, _ = _fast().build()
    with pytest.raises(BenStructureError):
        parse_ben(data + b"\x00\x00")


def test_file_cut_inside_the_configuration_is_truncated():
    data, offsets = _fast().build()
    with pytest.raises(BenTruncatedError):
        parse_ben(data[: offsets["section_0518"] + 10])


def test_record_section_count_must_match_its_length():
    def edit(buf, offsets):
        struct.pack_into("<H", buf, offsets["section_0514"] + 8, 4)

    with pytest.raises(BenStructureError):
        parse_ben(_patched(_fast(), edit))


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"class_flag": 1}, BenStructureError),  # header says Slow, section says Fast
        ({"class_code": 1010}, BenUnsupportedVariantError),
        ({"class_rate": 999}, BenStructureError),
        ({"summary_sample_count": N + 1}, BenStructureError),
        ({"summary_words": 8}, BenStructureError),
        ({"summary_record_number": 1}, BenStructureError),
        ({"last_index": N}, BenStructureError),
        ({"value_bit": 1}, BenStructureError),  # value channel mapped to a bit
    ],
)
def test_internal_declarations_must_agree(override, error):
    with pytest.raises(error):
        parse_ben(_fast(override=override).build()[0])


def test_sample_count_that_disagrees_with_payload_is_rejected():
    # Header and summary agree on one more sample than the payload holds.
    spec = _fast(override={"sample_count": N + 1, "summary_sample_count": N + 1, "last_index": N})
    with pytest.raises(BenTruncatedError):
        parse_ben(spec.build()[0])


@pytest.mark.parametrize(
    "header_edit",
    [
        lambda buf: struct.pack_into("<I", buf, 0x54, 0),  # zero rate
        lambda buf: struct.pack_into("<I", buf, 0x58, N + 1),  # pre-trigger > samples
        lambda buf: buf.__setitem__(0x65, 13),  # month 13
    ],
)
def test_impossible_header_values_are_rejected(header_edit):
    with pytest.raises(BenStructureError):
        parse_ben(_patched(_fast(), lambda buf, _: header_edit(buf)))


def test_layout_map_word_outside_the_sample_is_rejected():
    def edit(buf, offsets):
        struct.pack_into("<H", buf, _layout_entry(offsets, 0) + 2, 7)

    with pytest.raises(BenStructureError, match="word 7"):
        parse_ben(_patched(_fast(), edit))


def test_layout_map_bit_outside_the_word_is_rejected():
    def edit(buf, offsets):
        buf[_layout_entry(offsets, 4) + 4] = 16

    with pytest.raises(BenStructureError):
        parse_ben(_patched(_fast(), edit))


def test_value_channel_missing_from_the_layout_map_is_rejected():
    def edit(buf, offsets):
        struct.pack_into("<H", buf, _layout_entry(offsets, 1), 9999)

    with pytest.raises(BenStructureError, match="10001"):
        parse_ben(_patched(_fast(), edit))


def test_two_value_channels_in_one_word_are_rejected():
    def edit(buf, offsets):
        struct.pack_into("<H", buf, _layout_entry(offsets, 1) + 2, 2)

    with pytest.raises(BenStructureError, match="share sample word"):
        parse_ben(_patched(_fast(), edit))


def test_name_offset_outside_the_string_table_is_rejected():
    def edit(buf, offsets):
        struct.pack_into("<H", buf, offsets["section_0514"] + 12 + 8, 60000)

    with pytest.raises(BenStructureError, match="name offset"):
        parse_ben(_patched(_fast(), edit))


def test_missing_sample_data_tag_is_rejected():
    def edit(buf, offsets):
        struct.pack_into("<H", buf, offsets["data"] - 2, 0x1234)

    with pytest.raises(BenStructureError, match="sample-data tag"):
        parse_ben(_patched(_fast(), edit))


def test_every_ben_error_is_a_provider_load_error():
    for error in (BenNotRecognizedError, BenUnsupportedVariantError, BenTruncatedError, BenStructureError):
        assert issubclass(error, ProviderLoadError)


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostics: partial understanding is reported, never hidden
# ─────────────────────────────────────────────────────────────────────────────


def _codes(record) -> set[str]:
    return {d.code for d in record.diagnostics}


def test_undecodable_sub_second_digits_keep_the_whole_second_only():
    record, _, _ = _parse(_fast(trigger=(2024, 3, 5, 6, 7, 8, 12, 150, 3)))
    assert record.header.trigger_time.microsecond is None
    assert record.header.trigger_time_utc == datetime(2024, 3, 5, 6, 7, 8, tzinfo=timezone.utc)
    assert "trigger_fraction_undecodable" in _codes(record)


def test_unrecognized_section_is_skipped_and_reported():
    record, _, _ = _parse(_fast(extra_sections=[(0x0999, struct.pack("<HH", 0, 0xFFFF))]))
    assert "unrecognized_section" in _codes(record)
    assert len(record.value_channels) == 3


def test_unresolvable_exported_binary_is_omitted_and_reported():
    def edit(buf, offsets):
        # First exported binary now names a trigger no definition declares.
        struct.pack_into("<H", buf, offsets["section_0579"] + 12 + 74, 0x7777)

    record = parse_ben(_patched(_fast(), edit))
    assert [c.name for c in record.digital_channels] == ["BAY1 CB OPEN", "SPARE", "SPARE"]
    assert {"unresolved_digital_channels", "unreferenced_layout_entries"} <= _codes(record)


def test_unvalidated_unit_code_leaves_the_unit_unknown():
    spec = _fast()
    spec.values[0].unit_code = 30
    record, _, _ = _parse(spec)
    channel = record.value_channels[0]
    assert (channel.unit, channel.measurement, channel.unit_code) == (None, None, 30)
    assert "unknown_unit_code" in _codes(record)
    dr = to_disturbance_record(record, source_file="x.ben", nominal_frequency_hz=50.0)
    assert dr.analog_channels[0].unit == "" and dr.analog_channels[0].parameter_type is None


def test_clean_record_reports_only_duplicate_names():
    record, _, _ = _parse(_fast())
    assert _codes(record) == {"duplicate_channel_names"}
