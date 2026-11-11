"""Stage 3B-1 tests: BEN5K calibration authority propagation end-to-end.

Tests validate that every BEN5K analog channel receives
PhysicalCalibrationAuthority(status="unverified") at the normalize step, and
that this metadata flows correctly through every layer of the pipeline:

  normalize.py → DisturbanceRecord.analog_channels
              → AnalogChannelSummary (import_service)
              → AnalogChannelOut (API schema)

Governance: Stage 3B-1 — metadata propagation ONLY.
  - No correction factors are applied.
  - Waveform array values must be numerically identical to pre-3B-1 behavior.
  - Stage 3B-2 (calculation gates) is NOT activated by any code here.
"""

from __future__ import annotations

import struct
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from app.domain.channel_classification import UNDEFINED
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.physical_calibration import (
    CALIBRATION_UNVERIFIED,
    PURPOSE_ENGINEERING_CALCULATION,
    PURPOSE_EXPLORATORY_ANALYSIS,
    REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    evaluate_calibration_eligibility,
    is_blocked_by_calibration,
    is_eligible,
)
from app.domain.source import AnalogChannelSummary
from app.domain.source_timezone import TimeBasis
from app.domain.timing import SamplingInformation, TimingInformation
from app.providers.ben.legacy_ben5k.normalize import parse_ben5k
from app.providers.ben.normalize import _BEN5K_CHANNEL_AUTHORITY, to_disturbance_record
from app.schemas.source import AnalogChannelOut

# ── Minimal BEN5K synthetic fixture builder ───────────────────────────────────
# Duplicated/adapted from test_ben5k_normalize.py (same heritage as
# test_ben5k_reader.py's own fixture builder), extended to produce a
# two-analog-channel record so multi-channel propagation can be verified.

_BEN5K_FAMILY_SIG = b"\x01\x00\x04\x00"
_BEN5K_LAYOUT_SIG = b"\x28\xff\x03\x00\x6e\x00\xca\x00"
_BEN5K_GEN_MARKER = b"\x05\x00"
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


def _build_digital_descriptor(name: str, word_group: int, bit_index: int = 0) -> bytes:
    buf = bytearray(58)
    buf[0] = 0x01
    buf[1] = word_group
    buf[2] = bit_index
    buf[3] = 0xFF
    n = name.encode("latin-1")[:16]
    buf[4 : 4 + len(n)] = n
    buf[57] = 0xFF
    return bytes(buf)


def _build_short_feeder_names() -> bytes:
    result = bytearray()
    for _ in range(_SHORT_FEEDER_NAME_COUNT):
        entry = bytearray(22)
        entry[16:22] = b"\xff" * 6
        result.extend(entry)
    return bytes(result)


def _make_ben5k_two_channel(
    *,
    sample_count: int = 20,
    words_per_sample: int = 40,
    rate_hz: int = 5000,
    raw_a: int = 1000,
    raw_b: int = 2000,
    scale_a: float = 0.01,
    scale_b: float = 0.1,
) -> bytes:
    """BEN5K fixture with two analog channels (word 0 = VR, word 1 = IR)."""
    header = bytearray(0xDC)
    header[0:4] = _BEN5K_FAMILY_SIG
    header[4:12] = _BEN5K_LAYOUT_SIG
    header[14:16] = _BEN5K_GEN_MARKER
    struct.pack_into("<H", header, 0x0C, 1196)
    s = b"TEST STATION"
    header[0x10 : 0x10 + len(s)] = s
    struct.pack_into("<I", header, 0x54, rate_hz * 1000)
    struct.pack_into("<I", header, 0x58, 10)
    struct.pack_into("<I", header, 0x5C, sample_count)
    struct.pack_into("<H", header, 0x60, words_per_sample)
    header[0x64:0x6D] = bytes([126, 10, 16, 18, 3, 14, 53, 54, 0])
    struct.pack_into("<I", header, 0x7A, sample_count - 1)

    config_prefix = bytes(0xAAE - 0xDC)
    feeder_names = _build_short_feeder_names()
    gap = bytes(4)
    desc_a = _build_analog_descriptor("VR", word_index=0, scale=scale_a)
    desc_b = _build_analog_descriptor("IR", word_index=1, scale=scale_b)
    digital_desc = _build_digital_descriptor("CB_R OPEN", word_group=1, bit_index=0)
    config = config_prefix + feeder_names + gap + desc_a + desc_b + digital_desc

    payload_words = np.zeros((sample_count, words_per_sample), dtype=">u2")
    payload_words[:, 0] = raw_a
    payload_words[:, 1] = raw_b
    for i in range(sample_count):
        payload_words[i, 38] = np.uint16(0x0000 if i % 2 == 0 else 0x0002)

    return bytes(header) + config + payload_words.tobytes()


def _parse_and_normalize(
    data: bytes, nominal_frequency_hz: float = 50.0
) -> DisturbanceRecord:
    ben = parse_ben5k(data)
    return to_disturbance_record(ben, source_file="test.ben", nominal_frequency_hz=nominal_frequency_hz)


# ── A: BEN5K analog channels carry Unverified authority ───────────────────────


class TestNormalizeAuthorityAttached:
    def test_all_analog_channels_have_authority(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority is not None

    def test_authority_status_is_unverified(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority.status == CALIBRATION_UNVERIFIED

    def test_authority_reason_is_ben5k_code(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority.reason == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_authority_transform_id_describes_current_formula(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority.transform_id == "ben5k_v1_raw_s16_linear_scale_offset"

    def test_all_channels_share_same_authority_object(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        authorities = [ch.calibration_authority for ch in rec.analog_channels]
        assert len(authorities) >= 2
        assert all(a is authorities[0] for a in authorities), (
            "All BEN5K channels should reference the same module-level authority constant"
        )

    def test_module_constant_is_the_assigned_authority(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority is _BEN5K_CHANNEL_AUTHORITY

    def test_voltage_channel_has_authority(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        vr = next(ch for ch in rec.analog_channels if ch.name == "VR")
        assert vr.calibration_authority is not None
        assert vr.calibration_authority.status == CALIBRATION_UNVERIFIED

    def test_current_channel_has_authority(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        ir = next(ch for ch in rec.analog_channels if ch.name == "IR")
        assert ir.calibration_authority is not None
        assert ir.calibration_authority.status == CALIBRATION_UNVERIFIED


# ── B: Non-BEN5K (COMTRADE-style) AnalogChannels have authority=None ─────────


class TestNotBen5kNoAuthority:
    def test_analog_channel_default_authority_is_none(self):
        ch = AnalogChannel(name="VA", unit="V", index=1)
        assert ch.calibration_authority is None

    def test_analog_channel_explicit_none_authority(self):
        ch = AnalogChannel(name="IA", unit="A", index=2, calibration_authority=None)
        assert ch.calibration_authority is None

    def test_multiple_comtrade_like_channels_all_none(self):
        channels = [
            AnalogChannel(name=f"C{i}", unit="V", index=i + 1)
            for i in range(5)
        ]
        for ch in channels:
            assert ch.calibration_authority is None


# ── C: AnalogChannelSummary propagation ────────────────────────────────────────


class TestAnalogChannelSummaryPropagation:
    def test_summary_calibration_status_from_ben5k_channel(self):
        ch = AnalogChannel(
            name="VR",
            unit="V",
            index=1,
            calibration_authority=_BEN5K_CHANNEL_AUTHORITY,
        )
        summary = AnalogChannelSummary(
            name=ch.name,
            index=ch.index,
            unit=ch.unit,
            engineering_type="voltage",
            calibration_status=ch.calibration_authority.status if ch.calibration_authority else None,
            calibration_reason=ch.calibration_authority.reason if ch.calibration_authority else None,
        )
        assert summary.calibration_status == CALIBRATION_UNVERIFIED
        assert summary.calibration_reason == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_summary_calibration_none_for_comtrade_channel(self):
        ch = AnalogChannel(name="VA", unit="V", index=1, calibration_authority=None)
        summary = AnalogChannelSummary(
            name=ch.name,
            index=ch.index,
            unit=ch.unit,
            engineering_type="voltage",
            calibration_status=ch.calibration_authority.status if ch.calibration_authority else None,
            calibration_reason=ch.calibration_authority.reason if ch.calibration_authority else None,
        )
        assert summary.calibration_status is None
        assert summary.calibration_reason is None

    def test_summary_default_calibration_fields_are_none(self):
        summary = AnalogChannelSummary(
            name="VA", index=1, unit="V", engineering_type="voltage"
        )
        assert summary.calibration_status is None
        assert summary.calibration_reason is None

    def test_summary_fields_match_authority_values(self):
        ch = AnalogChannel(
            name="IR",
            unit="A",
            index=2,
            calibration_authority=_BEN5K_CHANNEL_AUTHORITY,
        )
        s = AnalogChannelSummary(
            name=ch.name,
            index=ch.index,
            unit=ch.unit,
            engineering_type="current",
            calibration_status=ch.calibration_authority.status if ch.calibration_authority else None,
            calibration_reason=ch.calibration_authority.reason if ch.calibration_authority else None,
        )
        assert s.calibration_status == ch.calibration_authority.status
        assert s.calibration_reason == ch.calibration_authority.reason


# ── D: AnalogChannelOut schema reflects calibration fields ─────────────────────


class TestAnalogChannelOutSchema:
    def _make_summary(
        self,
        calibration_status: str | None = None,
        calibration_reason: str | None = None,
    ) -> AnalogChannelSummary:
        return AnalogChannelSummary(
            name="VR",
            index=1,
            unit="V",
            engineering_type="voltage",
            calibration_status=calibration_status,
            calibration_reason=calibration_reason,
        )

    def test_out_has_calibration_status_unverified(self):
        summary = self._make_summary(
            calibration_status=CALIBRATION_UNVERIFIED,
            calibration_reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        out = AnalogChannelOut.model_validate(summary, from_attributes=True)
        assert out.calibration_status == CALIBRATION_UNVERIFIED

    def test_out_has_calibration_reason_ben5k(self):
        summary = self._make_summary(
            calibration_status=CALIBRATION_UNVERIFIED,
            calibration_reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        out = AnalogChannelOut.model_validate(summary, from_attributes=True)
        assert out.calibration_reason == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_out_calibration_null_for_comtrade(self):
        summary = self._make_summary()
        out = AnalogChannelOut.model_validate(summary, from_attributes=True)
        assert out.calibration_status is None
        assert out.calibration_reason is None

    def test_out_serialises_to_json_with_calibration_fields(self):
        summary = self._make_summary(
            calibration_status=CALIBRATION_UNVERIFIED,
            calibration_reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        out = AnalogChannelOut.model_validate(summary, from_attributes=True)
        payload = out.model_dump()
        assert payload["calibration_status"] == CALIBRATION_UNVERIFIED
        assert payload["calibration_reason"] == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_out_serialises_null_calibration_fields(self):
        summary = self._make_summary()
        payload = AnalogChannelOut.model_validate(summary, from_attributes=True).model_dump()
        assert payload["calibration_status"] is None
        assert payload["calibration_reason"] is None

    def test_existing_fields_unaffected_by_stage3b1(self):
        summary = self._make_summary(
            calibration_status=CALIBRATION_UNVERIFIED,
            calibration_reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        out = AnalogChannelOut.model_validate(summary, from_attributes=True)
        assert out.name == "VR"
        assert out.index == 1
        assert out.unit == "V"
        assert out.engineering_type == "voltage"
        assert out.engineering_quantity == UNDEFINED


# ── E: Waveform arrays are numerically unchanged ──────────────────────────────


class TestWaveformNumericalIntegrity:
    def test_engineering_values_match_raw_times_scale(self):
        scale_a, scale_b = 0.01, 0.1
        raw_a, raw_b = 1000, 2000
        rec = _parse_and_normalize(
            _make_ben5k_two_channel(raw_a=raw_a, raw_b=raw_b, scale_a=scale_a, scale_b=scale_b)
        )
        vr_col = rec.waveform_data["VR"].values
        ir_col = rec.waveform_data["IR"].values
        assert np.allclose(vr_col, raw_a * scale_a), f"VR engineering values changed: {vr_col[:3]}"
        assert np.allclose(ir_col, raw_b * scale_b), f"IR engineering values changed: {ir_col[:3]}"

    def test_waveform_shape_unchanged(self):
        sample_count = 30
        rec = _parse_and_normalize(_make_ben5k_two_channel(sample_count=sample_count))
        assert len(rec.waveform_data) == sample_count

    def test_adding_authority_does_not_alter_channel_scale(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel(scale_a=0.05))
        vr = next(ch for ch in rec.analog_channels if ch.name == "VR")
        assert vr.scale == pytest.approx(0.05)

    def test_adding_authority_does_not_alter_channel_offset(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        vr = next(ch for ch in rec.analog_channels if ch.name == "VR")
        assert vr.offset == pytest.approx(0.0)

    def test_no_nan_in_constant_raw_waveform(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for col in ["VR", "IR"]:
            assert not rec.waveform_data[col].isna().any(), f"{col} contains unexpected NaN"


# ── F: Authority object is immutable ─────────────────────────────────────────


class TestAuthorityImmutability:
    def test_status_field_is_frozen(self):
        auth = _BEN5K_CHANNEL_AUTHORITY
        with pytest.raises(FrozenInstanceError):
            auth.status = "verified"  # type: ignore[misc]

    def test_reason_field_is_frozen(self):
        auth = _BEN5K_CHANNEL_AUTHORITY
        with pytest.raises(FrozenInstanceError):
            auth.reason = "tampered"  # type: ignore[misc]

    def test_transform_id_field_is_frozen(self):
        auth = _BEN5K_CHANNEL_AUTHORITY
        with pytest.raises(FrozenInstanceError):
            auth.transform_id = "tampered"  # type: ignore[misc]

    def test_ben5k_channel_authority_constant_is_frozen(self):
        auth = _BEN5K_CHANNEL_AUTHORITY
        assert auth.status == CALIBRATION_UNVERIFIED
        with pytest.raises(FrozenInstanceError):
            auth.status = "verified"  # type: ignore[misc]
        # Confirm the constant was not mutated
        assert auth.status == CALIBRATION_UNVERIFIED


# ── G: Stage 3A evaluator correctly classifies BEN5K channels ────────────────


class TestStage3AEvaluatorWithBen5kChannels:
    def _authority(self):
        return _BEN5K_CHANNEL_AUTHORITY

    def test_blocked_for_engineering_calculation(self):
        result = evaluate_calibration_eligibility(
            [self._authority()], PURPOSE_ENGINEERING_CALCULATION
        )
        assert not result.eligible
        assert result.has_unverified_leaves

    def test_allowed_for_exploratory_analysis(self):
        result = evaluate_calibration_eligibility(
            [self._authority()], PURPOSE_EXPLORATORY_ANALYSIS
        )
        assert result.eligible

    def test_is_blocked_by_calibration_predicate(self):
        eligibility = evaluate_calibration_eligibility(
            [self._authority()], PURPOSE_ENGINEERING_CALCULATION
        )
        assert is_blocked_by_calibration(eligibility)

    def test_is_eligible_predicate_false_for_engineering_calc(self):
        eligibility = evaluate_calibration_eligibility(
            [self._authority()], PURPOSE_ENGINEERING_CALCULATION
        )
        assert not is_eligible(eligibility)

    def test_multi_channel_all_unverified_blocked(self):
        authorities = [self._authority()] * 3
        result = evaluate_calibration_eligibility(authorities, PURPOSE_ENGINEERING_CALCULATION)
        assert not result.eligible
        assert result.has_unverified_leaves

    def test_limiting_transform_id_included(self):
        result = evaluate_calibration_eligibility(
            [self._authority()], PURPOSE_ENGINEERING_CALCULATION
        )
        assert "ben5k_v1_raw_s16_linear_scale_offset" in result.limiting_transform_ids


# ── Refinement 2: full PhysicalCalibrationAuthority object preserved on AnalogChannel ──
# AnalogChannelSummary/AnalogChannelOut expose only a limited string projection
# (status, reason).  transform_id and evidence_refs remain solely on the full
# PhysicalCalibrationAuthority held by DisturbanceRecord.analog_channels[i].
# Stage 3B-2 evaluators must source the authority from that full object —
# never from the summary strings.


class TestFullAuthorityPreservedOnAnalogChannel:
    def test_transform_id_accessible_from_disturbance_record(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority is not None
            assert ch.calibration_authority.transform_id == "ben5k_v1_raw_s16_linear_scale_offset"

    def test_evidence_refs_accessible_from_disturbance_record(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        for ch in rec.analog_channels:
            assert ch.calibration_authority is not None
            assert isinstance(ch.calibration_authority.evidence_refs, tuple)

    def test_summary_does_not_expose_transform_id(self):
        summary = AnalogChannelSummary(
            name="VR", index=1, unit="V", engineering_type="voltage",
            calibration_status=CALIBRATION_UNVERIFIED,
            calibration_reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        assert not hasattr(summary, "calibration_transform_id"), (
            "AnalogChannelSummary must not expose transform_id — it is a limited projection"
        )

    def test_schema_out_does_not_expose_transform_id(self):
        summary = AnalogChannelSummary(
            name="VR", index=1, unit="V", engineering_type="voltage",
            calibration_status=CALIBRATION_UNVERIFIED,
            calibration_reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        out = AnalogChannelOut.model_validate(summary, from_attributes=True)
        payload = out.model_dump()
        assert "calibration_transform_id" not in payload, (
            "AnalogChannelOut must not expose transform_id — it is a limited API projection"
        )

    def test_full_authority_object_is_the_stage3b2_evaluation_source(self):
        rec = _parse_and_normalize(_make_ben5k_two_channel())
        ch = rec.analog_channels[0]
        # Confirm the full object — not just strings — is available for Stage 3B-2 evaluation
        auth = ch.calibration_authority
        assert auth is not None
        assert auth.status == CALIBRATION_UNVERIFIED
        assert auth.reason == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED
        assert auth.transform_id == "ben5k_v1_raw_s16_linear_scale_offset"
        assert isinstance(auth.evidence_refs, tuple)


# ── H: COMTRADE None authority is preserved through the full pipeline ─────────


class TestComtradeNotAssessedPreservation:
    def test_comtrade_channel_has_no_authority(self):
        ch = AnalogChannel(name="VA", unit="kV", index=1)
        assert ch.calibration_authority is None

    def test_summary_propagates_none_as_null(self):
        ch = AnalogChannel(name="VA", unit="kV", index=1, calibration_authority=None)
        s = AnalogChannelSummary(
            name=ch.name,
            index=ch.index,
            unit=ch.unit,
            engineering_type="voltage",
            calibration_status=ch.calibration_authority.status if ch.calibration_authority else None,
            calibration_reason=ch.calibration_authority.reason if ch.calibration_authority else None,
        )
        assert s.calibration_status is None
        assert s.calibration_reason is None

    def test_schema_out_null_for_not_assessed(self):
        s = AnalogChannelSummary(
            name="VA", index=1, unit="kV", engineering_type="voltage"
        )
        out = AnalogChannelOut.model_validate(s, from_attributes=True)
        assert out.calibration_status is None
        assert out.calibration_reason is None

    def test_null_authority_evaluates_as_not_assessed(self):
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)
        assert result.has_not_assessed_leaves

    def test_mixed_ben5k_and_comtrade_channels_blocked(self):
        result = evaluate_calibration_eligibility(
            [_BEN5K_CHANNEL_AUTHORITY, None], PURPOSE_ENGINEERING_CALCULATION
        )
        assert not result.eligible
        assert result.has_unverified_leaves
        assert result.has_not_assessed_leaves
