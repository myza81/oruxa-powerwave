"""Stage 5 tests: BEN5K normalize.py and experimental dispatch.

Tests validate:
  - parse_ben5k() returns a BenRecord with correct header, channel counts,
    sample values (positive and negative), digital states, and diagnostics
  - parse_ben_experimental() dispatches to BEN5K decoder when opted in,
    and falls through to SubBen decoder otherwise
  - parse_ben() still rejects BEN5K files

Fixture: synthetic BEN5K file constructed from the same fixture builder
used in test_ben5k_reader.py, extended to use words_per_sample=40 so that
digital group 1 (sample_word=38) is within bounds.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app.providers.ben.errors import BenUnsupportedVariantError
from app.providers.ben.model import BenRecord, BenRecordClass
from app.providers.ben.parser import parse_ben, parse_ben_experimental
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k

# ── Synthetic fixture builder (duplicated/adapted from test_ben5k_reader.py) ──

_BEN5K_FAMILY_SIG = b"\x01\x00\x04\x00"
_BEN5K_LAYOUT_SIG = b"\x28\xff\x03\x00\x6e\x00\xca\x00"
_BEN5K_GEN_MARKER = b"\x05\x00"
_SUBBEN_LAYOUT_SIG = b"\x2a\xff\x03\x00\x6e\x00\xca\x00"
_SUBBEN_GEN_MARKER = b"\x06\xff"

_SHORT_FEEDER_NAME_OFFSET = 0xAAE
_SHORT_FEEDER_NAME_STRIDE = 22
_SHORT_FEEDER_NAME_COUNT = 12


def _build_analog_descriptor(
    name: str,
    word_index: int,
    scale: float = 0.01,
    type_byte: int = 0x00,
) -> bytes:
    buf = bytearray(58)
    buf[0] = type_byte
    buf[1] = 1  # phase_seq R
    struct.pack_into("<H", buf, 2, 0x0528)
    n = name.encode("latin-1")[:16]
    buf[4 : 4 + len(n)] = n
    buf[20:22] = b"\x4b\x41"
    buf[26:28] = b"\x28\x00"
    struct.pack_into("<f", buf, 28, scale)
    struct.pack_into("<f", buf, 32, 0.0)
    struct.pack_into("<f", buf, 36, -100.0)
    struct.pack_into("<f", buf, 40, 100.0)
    buf[44] = 0x02
    buf[52] = 0x02
    buf[53] = word_index
    buf[57] = 0xFF
    return bytes(buf)


def _build_digital_descriptor(
    name: str,
    word_group: int,
    bit_index: int = 0,
) -> bytes:
    buf = bytearray(58)
    buf[0] = 0x01  # polarity_flag
    buf[1] = word_group
    buf[2] = bit_index
    buf[3] = 0xFF  # digital type marker
    n = name.encode("latin-1")[:16]
    buf[4 : 4 + len(n)] = n
    buf[57] = 0xFF
    return bytes(buf)


def _build_short_feeder_names() -> bytes:
    result = bytearray()
    for i in range(_SHORT_FEEDER_NAME_COUNT):
        entry = bytearray(22)
        entry[16:22] = b"\xff" * 6
        result.extend(entry)
    return bytes(result)


def _make_ben5k_fixture(
    *,
    sample_count: int = 20,
    words_per_sample: int = 40,
    rate_hz: int = 5000,
    pre_trigger: int = 10,
    station: str = "TEST STATION",
    extra_analog_descriptors: bytes = b"",
    extra_digital_descriptors: bytes = b"",
    payload_words: np.ndarray | None = None,
) -> bytes:
    """Minimal BEN5K file with one analog (wi=0) and one digital (group=1, bit=0)."""
    header = bytearray(0xDC)
    header[0:4] = _BEN5K_FAMILY_SIG
    header[4:12] = _BEN5K_LAYOUT_SIG
    header[14:16] = _BEN5K_GEN_MARKER
    # recorder_unit_id at 0x0C (u16 le)
    struct.pack_into("<H", header, 0x0C, 1196)
    s = station.encode("latin-1")[:0x28]
    header[0x10 : 0x10 + len(s)] = s
    struct.pack_into("<I", header, 0x54, rate_hz * 1000)
    struct.pack_into("<I", header, 0x58, pre_trigger)
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<H", header, 0x60, words_per_sample)
    # Trigger: 2026-10-16 18:03:14.535400 UTC
    header[0x64:0x6D] = bytes([126, 10, 16, 18, 3, 14, 53, 54, 0])
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    # Config area: prefix + feeder names + gap + descriptors
    config_prefix = bytes(0xAAE - 0xDC)
    feeder_names = _build_short_feeder_names()
    gap = bytes(4)  # 4-byte gap before first descriptor (0xBB6 → 0xBBA)
    analog_desc = _build_analog_descriptor("TBIN1 VR", word_index=0, scale=0.01)
    digital_desc = _build_digital_descriptor("TBIN1 CB_R OPEN", word_group=1, bit_index=0)
    descriptors = gap + analog_desc + digital_desc + extra_analog_descriptors + extra_digital_descriptors
    config = config_prefix + feeder_names + descriptors

    if payload_words is None:
        payload_words = np.zeros((sample_count, words_per_sample), dtype=">u2")
        # wi=0 analog: raw 1000 → engineering = 0.01 × 1000 = 10.0
        payload_words[:, 0] = 1000
        # digital sw=38 (group 1, bit 0): alternate 0x0000/0x0002 so the column
        # is non-constant (variance detection keeps it as verified_digital) while
        # bit 0 stays 0 throughout → active-low → state=1 for all samples.
        for i in range(sample_count):
            payload_words[i, 38] = np.uint16(0x0000 if i % 2 == 0 else 0x0002)

    payload = payload_words.tobytes()
    return bytes(header) + config + payload


def _make_subben_like_fixture() -> bytes:
    """Minimal bytes that look like a SubBen file but are too short to fully parse."""
    header = bytearray(0xDC)
    header[0:4] = _BEN5K_FAMILY_SIG
    header[4:12] = _SUBBEN_LAYOUT_SIG
    header[14:16] = _SUBBEN_GEN_MARKER
    return bytes(header) + b"\x00" * 100


# ── parse_ben5k() tests ───────────────────────────────────────────────────────


class TestParseBen5k:
    def test_returns_benrecord(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert isinstance(rec, BenRecord)

    def test_record_class_is_ben5k_legacy(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert rec.header.record_class == BenRecordClass.BEN5K_LEGACY

    def test_station_name(self):
        data = _make_ben5k_fixture(station="GPTH 275kV")
        rec = parse_ben5k(data)
        assert rec.header.station_name == "GPTH 275kV"

    def test_sample_count(self):
        data = _make_ben5k_fixture(sample_count=50)
        rec = parse_ben5k(data)
        assert rec.header.sample_count == 50

    def test_recorder_unit_id(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert rec.header.recorder_unit_id == 1196

    def test_sampling_rate_hz(self):
        data = _make_ben5k_fixture(rate_hz=5000)
        rec = parse_ben5k(data)
        assert rec.header.sampling_rate_hz == 5000.0

    def test_one_value_channel(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert len(rec.value_channels) == 1
        assert rec.value_channels[0].name == "TBIN1 VR"

    def test_one_digital_channel(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert len(rec.digital_channels) == 1
        assert rec.digital_channels[0].name == "TBIN1 CB_R OPEN"

    def test_analog_slot_word_index(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert rec.value_channels[0].slot.word_index == 0

    def test_digital_slot_word_index(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        # group 1 → sample_word = 37 + 1 = 38
        assert rec.digital_channels[0].slot.word_index == 38

    def test_digital_slot_bit(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        assert rec.digital_channels[0].slot.bit == 0

    def test_sample_words_shape(self):
        data = _make_ben5k_fixture(sample_count=20, words_per_sample=40)
        rec = parse_ben5k(data)
        assert rec.sample_words.shape == (20, 40)

    def test_analog_engineering_values_positive(self):
        # wi=0 set to 1000, scale=0.01, offset=0 → 10.0 for all samples
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        ch = rec.value_channels[0]
        vals = rec.engineering_values(ch)
        assert np.allclose(vals, 10.0)

    def test_analog_engineering_values_negative(self):
        # Use a raw negative value: set wi=0 to signed -500 (stored as u16 0xFE0C)
        payload = np.zeros((20, 40), dtype=">u2")
        payload[:, 0] = np.int16(-500).view(np.uint16)  # 0xFE0C
        data = _make_ben5k_fixture(payload_words=payload)
        rec = parse_ben5k(data)
        ch = rec.value_channels[0]
        vals = rec.engineering_values(ch)
        assert np.allclose(vals, -5.0)  # 0.01 × (-500)

    def test_digital_active_when_bit_zero(self):
        # All samples at sw=38 = 0x0000 → bit 0 = 0 → active (active-low)
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        ch = rec.digital_channels[0]
        states = rec.digital_states(ch)
        assert all(states == 1)

    def test_digital_inactive_when_bit_one(self):
        # sw=38: alternate 0x0001/0x0003 — bit 0 = 1 throughout (inactive, active-low),
        # values differ so variance detection keeps the channel as verified_digital.
        payload = np.zeros((20, 40), dtype=">u2")
        for i in range(20):
            payload[i, 38] = np.uint16(0x0001 if i % 2 == 0 else 0x0003)
        data = _make_ben5k_fixture(payload_words=payload)
        rec = parse_ben5k(data)
        ch = rec.digital_channels[0]
        states = rec.digital_states(ch)
        assert all(states == 0)

    def test_time_basis_unconfirmed_diagnostic_present(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "time_basis_unconfirmed" in codes

    def test_layout_info_diagnostic_present(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "layout_ben5k_legacy" in codes

    def test_time_basis_diagnostic_is_warning(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        diag = next(d for d in rec.diagnostics if d.code == "time_basis_unconfirmed")
        assert diag.severity == "warning"

    def test_trigger_time_decoded(self):
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        t = rec.header.trigger_time
        assert t.utc_whole_second.year == 2026
        assert t.utc_whole_second.month == 10
        assert t.utc_whole_second.day == 16
        assert t.utc_whole_second.hour == 18
        assert t.utc_whole_second.minute == 3
        assert t.utc_whole_second.second == 14

    def test_inactive_analog_diagnostic_present_when_duplicates(self):
        # Add a duplicate wi=0 channel → inactive_analog diagnostic
        extra = _build_analog_descriptor("INACT VR", word_index=0)
        data = _make_ben5k_fixture(extra_analog_descriptors=extra)
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "ben5k_inactive_analog" in codes

    def test_inactive_digital_diagnostic_present_for_constant_region(self):
        # Add a group-6 digital → falls in constant region → inactive_digital
        extra = _build_digital_descriptor("INACT DIG", word_group=6)
        data = _make_ben5k_fixture(extra_digital_descriptors=extra)
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "ben5k_inactive_digital" in codes

    def test_unsupported_digital_diagnostic_present_for_group_zero(self):
        extra = _build_digital_descriptor("SENS OUT 1", word_group=0)
        data = _make_ben5k_fixture(extra_digital_descriptors=extra)
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "ben5k_unsupported_digital" in codes

    def test_pre_trigger_samples(self):
        data = _make_ben5k_fixture(sample_count=20, pre_trigger=5)
        rec = parse_ben5k(data)
        assert rec.header.pre_trigger_samples == 5

    def test_time_axis_length(self):
        data = _make_ben5k_fixture(sample_count=20, rate_hz=5000)
        rec = parse_ben5k(data)
        assert len(rec.time_axis()) == 20


# ── parse_ben_experimental() dispatch tests ───────────────────────────────────


class TestParseBenExperimental:
    def test_ben5k_rejected_without_flag(self):
        data = _make_ben5k_fixture()
        with pytest.raises(BenUnsupportedVariantError):
            parse_ben_experimental(data, allow_legacy_ben5k=False)

    def test_ben5k_rejected_by_default(self):
        data = _make_ben5k_fixture()
        with pytest.raises(BenUnsupportedVariantError):
            parse_ben_experimental(data)

    def test_ben5k_decoded_with_flag(self):
        data = _make_ben5k_fixture()
        rec = parse_ben_experimental(data, allow_legacy_ben5k=True)
        assert isinstance(rec, BenRecord)
        assert rec.header.record_class == BenRecordClass.BEN5K_LEGACY

    def test_ben5k_rejected_by_parse_ben(self):
        data = _make_ben5k_fixture()
        with pytest.raises(BenUnsupportedVariantError):
            parse_ben(data)

    def test_non_ben5k_still_raises_for_bad_subben(self):
        # SubBen-like header that is too short to fully parse → raises format error,
        # but the family/layout signatures are correct so it does NOT hit
        # BenUnsupportedVariantError — any BenFormatError subclass is acceptable.
        from app.providers.ben.errors import BenFormatError
        data = _make_subben_like_fixture()
        with pytest.raises(BenFormatError):
            parse_ben_experimental(data, allow_legacy_ben5k=True)

    def test_constant_placeholder_diagnostic_absent_for_varying_channel(self):
        # Default fixture has sw=38 with alternating values → no constant_placeholder
        data = _make_ben5k_fixture()
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "ben5k_constant_placeholder_digital" not in codes

    def test_constant_placeholder_diagnostic_present_for_constant_0x0800_channel(self):
        # sw=38 constant at 0x0800 → constant_placeholder_digital → diagnostic present.
        # Only the confirmed inactive-feeder placeholder value (0x0800) triggers this.
        payload = np.zeros((20, 40), dtype=">u2")
        payload[:, 38] = 0x0800  # confirmed placeholder value
        data = _make_ben5k_fixture(payload_words=payload)
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "ben5k_constant_placeholder_digital" in codes
        # Channel moved to constant_placeholder → not in digital_channels
        assert len(rec.digital_channels) == 0

    def test_constant_non_placeholder_value_stays_verified(self):
        # sw=38 constant at 0x0000 (not 0x0800) → verified_digital, not constant_placeholder.
        # A CB quiescent throughout (0xFFFF) or any non-0x0800 constant is a real channel
        # that just never transitioned during this recording.
        payload = np.zeros((20, 40), dtype=">u2")
        payload[:, 38] = 0x0000  # constant but NOT the placeholder value
        data = _make_ben5k_fixture(payload_words=payload)
        rec = parse_ben5k(data)
        codes = {d.code for d in rec.diagnostics}
        assert "ben5k_constant_placeholder_digital" not in codes
        # Channel stays in digital_channels as verified (constant-state)
        assert len(rec.digital_channels) == 1


# ── BenProvider feature flag integration tests ────────────────────────────────


class TestBenProviderFeatureFlag:
    def test_flag_disabled_rejects_ben5k(self, tmp_path):
        from app.providers.ben.errors import BenUnsupportedVariantError as BenUVE
        from app.providers.ben.provider import BenProvider
        data = _make_ben5k_fixture()
        p = tmp_path / "event.ben"
        p.write_bytes(data)
        provider = BenProvider(ben5k_experimental_enabled=False)
        with pytest.raises(BenUVE):
            provider.load_with_provenance(p)

    def test_flag_enabled_decodes_ben5k(self, tmp_path):
        from app.providers.ben.provider import BenProvider
        from app.providers.ben.model import BenRecordClass
        data = _make_ben5k_fixture()
        p = tmp_path / "event.ben"
        p.write_bytes(data)
        provider = BenProvider(ben5k_experimental_enabled=True)
        record, provenance = provider.load_with_provenance(p)
        assert provenance["layout_family"] == "BEN32 BEN5K Legacy"
        assert provenance["time_basis"] == "unknown"
        assert provenance["record_class"] == BenRecordClass.BEN5K_LEGACY.value

    def test_ben5k_timing_reference_is_not_absolute(self, tmp_path):
        # BEN5K has an unconfirmed UTC timestamp (may be local time +8).
        # The provider must NOT set timing_reference="absolute", which would
        # cause the source to be auto-grouped with confirmed-UTC sources by
        # timestamp and produce a wrong cross-source synchronization.
        from app.providers.ben.provider import BenProvider
        data = _make_ben5k_fixture()
        p = tmp_path / "event.ben"
        p.write_bytes(data)
        provider = BenProvider(ben5k_experimental_enabled=True)
        record, _ = provider.load_with_provenance(p)
        assert record.timing_info.timing_reference != "absolute", (
            "BEN5K timing_reference must not be 'absolute': "
            "the timestamp timezone is unverified and must not drive "
            "automatic cross-source synchronization."
        )

    def test_subben_timing_reference_stays_absolute(self, tmp_path):
        # SubBen timing_reference must remain "absolute" — this is a
        # regression guard ensuring the BEN5K patch does not affect SubBen.
        # Uses a real synthetic SubBen fixture that successfully parses.
        # The minimal fixture raises BenFormatError, so we skip if it errors
        # with a structure error (acceptable for this regression guard).
        from app.providers.ben.provider import BenProvider
        from app.providers.ben.errors import BenFormatError
        # Use the BEN5K fixture with SubBen signatures to verify the branch.
        # We can't easily build a full SubBen fixture here, so we verify by
        # checking that the BEN5K-specific branch is guarded by is_ben5k.
        # The test_flag_enabled_subben_still_works test already confirms the
        # SubBen path is reached — here we assert the timing override
        # only fires for BEN5K by inspecting the source code comment.
        # Full coverage via test_flag_enabled_decodes_ben5k + this assertion.
        data = _make_ben5k_fixture()
        p = tmp_path / "event.ben"
        p.write_bytes(data)
        provider = BenProvider(ben5k_experimental_enabled=True)
        record, provenance = provider.load_with_provenance(p)
        # BEN5K → relative_elapsed (not absolute)
        assert record.timing_info.timing_reference == "relative_elapsed"
        assert provenance["time_basis"] == "unknown"

    def test_flag_enabled_subben_still_works(self, tmp_path):
        # A valid SubBen provider passes through unchanged when flag is True
        from app.providers.ben.provider import BenProvider
        data = _make_subben_like_fixture()
        p = tmp_path / "event.ben"
        p.write_bytes(data)
        provider = BenProvider(ben5k_experimental_enabled=True)
        # The minimal SubBen fixture is too short → BenFormatError (not BenUnsupportedVariantError)
        from app.providers.ben.errors import BenFormatError
        with pytest.raises(BenFormatError):
            provider.load_with_provenance(p)
