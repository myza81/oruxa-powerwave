"""Stage 3 tests: BEN5K sample decoder.

Validates:
  - Big-endian u16 → signed int16 conversion (critical: must use .astype not .view)
  - Scale/offset application per-channel
  - Active-low digital bit extraction
  - OOB word_index raises BenStructureError

All tests use synthetic data, not the real GPTH recording.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app.providers.ben.legacy_ben5k.decoder import decode_samples, extract_raw_matrix
from app.providers.ben.legacy_ben5k.reader import (
    Ben5kAnalogChannel,
    Ben5kDigitalChannel,
    Ben5kHeader,
)
from app.providers.ben.errors import BenStructureError, BenTruncatedError


def _header(
    sample_count: int = 10,
    words_per_sample: int = 5,
    rate_hz: int = 5000,
    pre_trigger: int = 0,
) -> Ben5kHeader:
    return Ben5kHeader(
        station_name="TEST",
        rate_hz=rate_hz,
        pre_trigger=pre_trigger,
        sample_count=sample_count,
        words_per_sample=words_per_sample,
        trigger_bytes=bytes(9),
    )


def _analog_ch(name: str, word_index: int, scale: float = 1.0, offset: float = 0.0) -> Ben5kAnalogChannel:
    return Ben5kAnalogChannel(
        name=name,
        word_index=word_index,
        physical_word_index=word_index,  # decoder uses physical_word_index
        scale=scale,
        offset=offset,
        low_range=-100.0,
        high_range=100.0,
        type_byte=0x00,
        phase_seq=1,
        class_code=0x0528,
        descriptor_offset=0,
    )


def _digital_ch(name: str, word_group: int, bit_index: int) -> Ben5kDigitalChannel:
    return Ben5kDigitalChannel(
        name=name,
        word_group=word_group,
        bit_index=bit_index,
        polarity_flag=1,
        descriptor_offset=0,
    )


def _build_data(
    sample_count: int,
    words_per_sample: int,
    raw_matrix: np.ndarray,
) -> bytes:
    """Build a fake BEN5K file with the given sample matrix at the end."""
    # Header placeholder (0xDC bytes of zeros with minimal valid fields)
    header = bytearray(0xDC)
    header[0:4] = b"\x01\x00\x04\x00"
    header[4:12] = b"\x28\xff\x03\x00\x6e\x00\xca\x00"
    header[14:16] = b"\x05\x00"
    struct.pack_into("<I", header, 0x54, 5_000_000)
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<I", header, 0x60, words_per_sample)
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    # Config padding (enough for feeder names and one descriptor)
    config = bytes(0xBB6 - 0xDC + 58)  # reach past descriptor area

    payload = raw_matrix.astype(">u2").tobytes()
    return bytes(header) + config + payload


class TestBen5kDecodeAnalog:
    def test_identity_scale(self) -> None:
        """scale=1, offset=0: engineering value equals raw int16."""
        raw = np.array([[1000, 0, 0]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=0, scale=1.0, offset=0.0)]
        eng, _ = decode_samples(data, h, channels, [])
        assert eng.shape == (1, 1)
        assert abs(eng[0, 0] - 1000.0) < 1e-3

    def test_scale_applied(self) -> None:
        raw = np.array([[2000, 0, 0]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=0, scale=0.5, offset=0.0)]
        eng, _ = decode_samples(data, h, channels, [])
        assert abs(eng[0, 0] - 1000.0) < 1e-3

    def test_offset_applied(self) -> None:
        raw = np.array([[0, 0, 0]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=0, scale=1.0, offset=5.0)]
        eng, _ = decode_samples(data, h, channels, [])
        assert abs(eng[0, 0] - 5.0) < 1e-3

    def test_negative_raw_value_correct_sign(self) -> None:
        """Big-endian 0x8000 = unsigned 32768 → signed int16 = -32768."""
        # Must use .astype not .view to get correct signed value
        raw = np.array([[0x8000, 0, 0]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=0, scale=1.0, offset=0.0)]
        eng, _ = decode_samples(data, h, channels, [])
        assert abs(eng[0, 0] - (-32768.0)) < 1e-3

    def test_max_positive_raw(self) -> None:
        """0x7FFF = 32767 → signed +32767."""
        raw = np.array([[0x7FFF, 0, 0]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=0, scale=1.0, offset=0.0)]
        eng, _ = decode_samples(data, h, channels, [])
        assert abs(eng[0, 0] - 32767.0) < 1e-3

    def test_byte_order_not_view(self) -> None:
        """
        Critical regression: 0xD0E0 stored big-endian as bytes D0 E0.
        As big-endian u16 this is 0xD0E0 = 53472 unsigned.
        As signed int16 this is 53472 - 65536 = -12064.
        If .view() were used on LE hardware it would read as 0xE0D0 = -8000 (WRONG).
        """
        raw = np.array([[0xD0E0, 0, 0]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=0, scale=1.0, offset=0.0)]
        eng, _ = decode_samples(data, h, channels, [])
        expected = int.from_bytes(b"\xD0\xE0", "big", signed=True)  # = -12064
        assert abs(eng[0, 0] - float(expected)) < 1e-3, (
            f"Expected {float(expected)}, got {eng[0, 0]}: "
            "possible .view() byte-order error"
        )

    def test_multiple_channels_separate_words(self) -> None:
        raw = np.array([[100, 200, 300]], dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [
            _analog_ch("CH0", word_index=0, scale=1.0),
            _analog_ch("CH1", word_index=1, scale=2.0),
            _analog_ch("CH2", word_index=2, scale=3.0),
        ]
        eng, _ = decode_samples(data, h, channels, [])
        assert abs(eng[0, 0] - 100.0) < 1e-3
        assert abs(eng[0, 1] - 400.0) < 1e-3  # 200 × 2
        assert abs(eng[0, 2] - 900.0) < 1e-3  # 300 × 3

    def test_multiple_samples(self) -> None:
        raw = np.array([[10], [20], [30]], dtype=">u2")
        data = _build_data(3, 1, raw)
        h = _header(sample_count=3, words_per_sample=1)
        channels = [_analog_ch("CH", word_index=0, scale=2.0)]
        eng, _ = decode_samples(data, h, channels, [])
        np.testing.assert_allclose(eng[:, 0], [20.0, 40.0, 60.0], atol=1e-3)

    def test_empty_channel_list_returns_empty_array(self) -> None:
        raw = np.zeros((5, 3), dtype=">u2")
        data = _build_data(5, 3, raw)
        h = _header(sample_count=5, words_per_sample=3)
        eng, _ = decode_samples(data, h, [], [])
        assert eng.shape == (5, 0)

    def test_oob_word_index_raises(self) -> None:
        raw = np.zeros((1, 3), dtype=">u2")
        data = _build_data(1, 3, raw)
        h = _header(sample_count=1, words_per_sample=3)
        channels = [_analog_ch("VR", word_index=99)]  # 99 >= 3 words
        with pytest.raises(BenStructureError):
            decode_samples(data, h, channels, [])


class TestBen5kDecodeDigital:
    def _fixture_with_digital_word(
        self, word_group: int, word_value: int, bit_index: int
    ) -> tuple[bytes, Ben5kHeader, list[Ben5kDigitalChannel]]:
        # sample_word_index = 37 + word_group; total words must cover that slot
        sw = 37 + word_group
        wps = sw + 1  # just enough words
        raw = np.full((5, wps), 0xFFFF, dtype=">u2")  # all bits high = quiescent
        raw[2, sw] = word_value  # set sample 2 to the test value
        data = _build_data(5, wps, raw)
        h = _header(sample_count=5, words_per_sample=wps)
        ch = _digital_ch("CB OPEN", word_group=word_group, bit_index=bit_index)
        return data, h, [ch]

    def test_all_inactive_when_quiescent(self) -> None:
        """0xFFFF with active-low = all bits 1 = all channels inactive."""
        data, h, chans = self._fixture_with_digital_word(1, 0xFFFF, bit_index=7)
        _, digital = decode_samples(data, h, [], chans)
        assert not digital.any()

    def test_active_low_bit7_goes_zero(self) -> None:
        """Bit 7 = 0 in an otherwise all-1 word → channel active."""
        word_val = 0xFFFF & ~(1 << 7)  # 0xFF7F
        data, h, chans = self._fixture_with_digital_word(1, word_val, bit_index=7)
        _, digital = decode_samples(data, h, [], chans)
        # sample 2 should be active, others inactive
        assert digital[2, 0] is np.bool_(True)
        assert not digital[0, 0]
        assert not digital[1, 0]

    def test_bit_index_0(self) -> None:
        """LSB (bit 0) transitions to 0 = channel active."""
        word_val = 0xFFFF & ~1  # bit 0 = 0
        data, h, chans = self._fixture_with_digital_word(1, word_val, bit_index=0)
        _, digital = decode_samples(data, h, [], chans)
        assert digital[2, 0] is np.bool_(True)

    def test_bit_index_15(self) -> None:
        """MSB (bit 15) transitions to 0 = channel active."""
        word_val = 0x7FFF  # bit 15 = 0, all others 1
        data, h, chans = self._fixture_with_digital_word(1, word_val, bit_index=15)
        _, digital = decode_samples(data, h, [], chans)
        assert digital[2, 0] is np.bool_(True)

    def test_empty_digital_returns_empty(self) -> None:
        raw = np.zeros((5, 3), dtype=">u2")
        data = _build_data(5, 3, raw)
        h = _header(sample_count=5, words_per_sample=3)
        _, digital = decode_samples(data, h, [], [])
        assert digital.shape == (5, 0)


class TestBen5kExtractRawMatrix:
    def test_shape_matches_dimensions(self) -> None:
        raw = np.arange(30, dtype=">u2").reshape(5, 6)
        data = _build_data(5, 6, raw)
        h = _header(sample_count=5, words_per_sample=6)
        mat = extract_raw_matrix(data, h)
        assert mat.shape == (5, 6)

    def test_values_preserved(self) -> None:
        raw = np.array([[0xABCD, 0x1234], [0x5678, 0x9ABC]], dtype=">u2")
        data = _build_data(2, 2, raw)
        h = _header(sample_count=2, words_per_sample=2)
        mat = extract_raw_matrix(data, h)
        assert mat[0, 0] == 0xABCD
        assert mat[1, 1] == 0x9ABC
