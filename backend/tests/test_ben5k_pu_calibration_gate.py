"""Stage 3B-2A tests: Physical Calibration Authority Per Unit Safety Gate.

Verifies that channels with an explicitly Unverified or Invalid
PhysicalCalibrationAuthority cannot produce authoritative Per Unit results,
while engineering waveform inspection is fully preserved.

Requirement categories covered:
  A  BEN5K voltage/current with explicit unverified authority → calibration_unavailable
  B  BEN5K current channel (explicit unverified) → calibration_unavailable
  C  Defensive provenance check (None authority, BEN+UNKNOWN) → blocked
  D  COMTRADE not-assessed (None authority) → NOT blocked (backward compat)
  E  Verified authority → NOT blocked
  F  Invalid authority → blocked
  G  Status constant is distinct from base_required and not_applicable
  H  apply_per_unit_to_array/value with calibration_unavailable → engineering values
  I  Angle channels → NOT_APPLICABLE (angle check runs BEFORE calibration check)
  J  extract_waveform_range integration: BEN5K PU mode → calibration_unavailable, ENG values

Governance: Stage 3B-2A — PU eligibility gate ONLY.
  No calibration correction factors are applied.
  No calculated-channel, phasor, power or Compliance enforcement.
  PULU-07/08/09 regressions (COMTRADE sources) are unaffected.
  Stage 3B-2B/3B-3 is NOT activated by any code here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.channel_classification import ENGINEERING_QUANTITY_VOLTAGE_ANGLE, UNDEFINED
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import FORMAT_VARIANT_BEN5K_LEGACY, RecordingMetadata
from app.domain.per_unit import (
    STATUS_BASE_REQUIRED,
    STATUS_CALIBRATION_UNAVAILABLE,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    apply_per_unit_to_array,
    apply_per_unit_to_value,
)
from app.domain.physical_calibration import (
    CALIBRATION_INVALID,
    CALIBRATION_UNVERIFIED,
    CALIBRATION_VERIFIED,
    REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    PhysicalCalibrationAuthority,
)
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.source_timezone import TimeBasis
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.waveform_service import (
    PEAK_MODE_MAX,
    UNIT_MODE_PER_UNIT,
    _calibration_blocked_reason,
    _resolve_effective_per_unit,
    extract_cursor_values,
    extract_waveform_range,
    resolve_annotation_anchor,
    resolve_peak_value,
)

# ---------------------------------------------------------------------------
# Well-known test authorities
# ---------------------------------------------------------------------------

_UNVERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_UNVERIFIED,
    reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)
_VERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_VERIFIED,
    reason="lab_verified_crosscheck",
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)
_INVALID_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_INVALID,
    reason="transform_id_mismatch_invalidated",
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_N = 20
_RATE = 1000.0
_NOW = datetime.now(timezone.utc)


def _make_active_source(
    *,
    channel_name: str = "VA",
    engineering_type: str = "Voltage",
    unit: str = "kV",
    provider_type: str = "BEN",
    time_basis: TimeBasis | None = TimeBasis.UNKNOWN,
    format_variant: str | None = None,
    calibration_authority: PhysicalCalibrationAuthority | None = _UNVERIFIED_AUTH,
) -> ActiveSource:
    """Minimal ActiveSource with one analog channel for calibration-gate testing.

    ``format_variant`` is None by default so the defensive provenance check
    only fires when the test explicitly passes FORMAT_VARIANT_BEN5K_LEGACY —
    matching the corrected waveform_service implementation (DEC-213 Item 1).
    """
    time = np.arange(_N, dtype=np.float64) / _RATE
    values = np.ones(_N, dtype=np.float64) * 1.0

    analog_channel = AnalogChannel(
        name=channel_name,
        unit=unit,
        index=1,
        phase="A",
        calibration_authority=calibration_authority,
    )
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="TEST_STATION",
            recorder_name="TEST_REC",
            source_file="test.ben",
            provider_type=provider_type,
            nominal_frequency=50.0,
            format_variant=format_variant,
        ),
        waveform_data=pd.DataFrame({"time": time, channel_name: values}),
        analog_channels=[analog_channel],
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[_RATE], samples_per_rate=[_N]),
        timing_info=TimingInformation(
            start_time=_NOW,
            trigger_time=_NOW,
            time_basis=time_basis,
        ),
    )
    metadata = SourceMetadata(
        source_id="src-test",
        workspace_id="ws-test",
        provider_type=provider_type,
        original_filenames=("test.ben",),
        created_at=_NOW,
        station_name="TEST_STATION",
        recorder_name="TEST_REC",
        nominal_frequency=50.0,
        timing_reference="relative_elapsed",
        start_time=_NOW,
        trigger_time=_NOW,
        sample_count=_N,
        duration_seconds=float(time[-1] - time[0]),
        elapsed_start_seconds=float(time[0]),
        elapsed_end_seconds=float(time[-1]),
        sampling_rates=(_RATE,),
        samples_per_rate=(_N,),
        analog_channels=[
            AnalogChannelSummary(
                name=channel_name,
                index=1,
                unit=unit,
                engineering_type=engineering_type,
            )
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


# ---------------------------------------------------------------------------
# A/B: BEN5K channels with explicit unverified authority → calibration_unavailable
# ---------------------------------------------------------------------------

class TestExplicitUnverifiedAuthority:
    """Req A/B: explicitly Unverified BEN5K channels (voltage and current) are
    blocked by _resolve_effective_per_unit."""

    def test_voltage_channel_returns_calibration_unavailable(self):
        active = _make_active_source(channel_name="VA", engineering_type="Voltage")
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_current_channel_returns_calibration_unavailable(self):
        active = _make_active_source(
            channel_name="IA", engineering_type="Current", unit="A",
        )
        result = _resolve_effective_per_unit(
            active, "IA", "Current", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_blocked_reason_carries_ben5k_reason_code(self):
        active = _make_active_source(channel_name="VA", engineering_type="Voltage")
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.reason == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_profile_id_is_none_when_blocked(self):
        active = _make_active_source(channel_name="VA", engineering_type="Voltage")
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.profile_id is None
        assert result.base_amount is None
        assert result.base_unit is None


# ---------------------------------------------------------------------------
# C: Defensive provenance check — absent authority on BEN5K record
# ---------------------------------------------------------------------------

class TestDefensiveProvenanceCheck:
    """Req C: a BEN5K channel whose calibration_authority is None (lost/absent
    metadata) must be blocked via record format_variant, not silently bypassed.

    The defensive check uses FORMAT_VARIANT_BEN5K_LEGACY (the explicit format
    identity) — NOT time_basis. Calibration authority and timestamp authority
    are independent (DEC-213 Item 1).
    """

    def test_none_authority_ben5k_format_variant_is_blocked(self):
        active = _make_active_source(
            channel_name="VA",
            provider_type="BEN",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=None,
        )
        result = _calibration_blocked_reason("VA", active)
        assert result == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_none_authority_ben5k_format_variant_resolve_returns_unavailable(self):
        active = _make_active_source(
            channel_name="VA",
            provider_type="BEN",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=None,
        )
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_none_authority_ben_no_format_variant_not_blocked(self):
        """A BEN32/SubBen record without BEN5K format_variant (e.g. VERIFIED_UTC
        SubBen) must NOT be blocked by the defensive provenance check."""
        active = _make_active_source(
            channel_name="VA",
            provider_type="BEN",
            time_basis=TimeBasis.VERIFIED_UTC,
            format_variant=None,
            calibration_authority=None,
        )
        result = _calibration_blocked_reason("VA", active)
        assert result is None

    def test_none_authority_ben5k_time_basis_alone_does_not_block(self):
        """UNKNOWN time_basis alone must NOT trigger the block — format_variant
        is the explicit identity, not time_basis (DEC-213 Item 1)."""
        active = _make_active_source(
            channel_name="VA",
            provider_type="BEN",
            time_basis=TimeBasis.UNKNOWN,
            format_variant=None,
            calibration_authority=None,
        )
        result = _calibration_blocked_reason("VA", active)
        assert result is None


# ---------------------------------------------------------------------------
# D: COMTRADE not-assessed → NOT blocked (backward compat)
# ---------------------------------------------------------------------------

class TestComtradeNotAssessedPreservation:
    """Req D: COMTRADE and other non-BEN5K sources with None authority are NOT
    blocked.  This is the existing compatibility behavior (not-assessed = compat
    mode); Stage 3B-2A must not break any COMTRADE PU workflow."""

    def test_comtrade_none_authority_not_blocked(self):
        active = _make_active_source(
            channel_name="VA",
            provider_type="COMTRADE",
            time_basis=None,
            calibration_authority=None,
        )
        result = _calibration_blocked_reason("VA", active)
        assert result is None

    def test_comtrade_none_authority_resolve_not_unavailable(self):
        active = _make_active_source(
            channel_name="VA",
            provider_type="COMTRADE",
            time_basis=None,
            calibration_authority=None,
        )
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        # Without a PU profile the status is base_required, not calibration_unavailable
        assert result.status != STATUS_CALIBRATION_UNAVAILABLE
        assert result.status == STATUS_BASE_REQUIRED

    def test_csv_none_authority_not_blocked(self):
        """CSV/Excel sources also carry None authority and must not be affected."""
        active = _make_active_source(
            channel_name="VA",
            provider_type="CSV",
            time_basis=None,
            calibration_authority=None,
        )
        result = _calibration_blocked_reason("VA", active)
        assert result is None


# ---------------------------------------------------------------------------
# E: Verified authority → NOT blocked
# ---------------------------------------------------------------------------

class TestVerifiedAuthorityNotBlocked:
    """Req E: a channel with an explicitly Verified authority is NOT blocked."""

    def test_verified_authority_not_blocked(self):
        active = _make_active_source(calibration_authority=_VERIFIED_AUTH)
        result = _calibration_blocked_reason("VA", active)
        assert result is None

    def test_verified_authority_resolve_not_calibration_unavailable(self):
        active = _make_active_source(calibration_authority=_VERIFIED_AUTH)
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.status != STATUS_CALIBRATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# F: Invalid authority → blocked
# ---------------------------------------------------------------------------

class TestInvalidAuthorityBlocked:
    """Req F: a channel with an explicitly Invalid authority is blocked."""

    def test_invalid_authority_blocked(self):
        active = _make_active_source(calibration_authority=_INVALID_AUTH)
        result = _calibration_blocked_reason("VA", active)
        assert result is not None

    def test_invalid_authority_returns_calibration_unavailable(self):
        active = _make_active_source(calibration_authority=_INVALID_AUTH)
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.status == STATUS_CALIBRATION_UNAVAILABLE

    def test_invalid_authority_reason_is_authority_reason(self):
        active = _make_active_source(calibration_authority=_INVALID_AUTH)
        result = _resolve_effective_per_unit(
            active, "VA", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.reason == _INVALID_AUTH.reason


# ---------------------------------------------------------------------------
# G: Status constant distinctness
# ---------------------------------------------------------------------------

class TestStatusConstantDistinctness:
    """Req G: STATUS_CALIBRATION_UNAVAILABLE is a distinct machine-readable
    value that cannot be confused with existing PU statuses."""

    def test_distinct_from_base_required(self):
        assert STATUS_CALIBRATION_UNAVAILABLE != STATUS_BASE_REQUIRED

    def test_distinct_from_not_applicable(self):
        assert STATUS_CALIBRATION_UNAVAILABLE != STATUS_NOT_APPLICABLE

    def test_distinct_from_configured(self):
        assert STATUS_CALIBRATION_UNAVAILABLE != STATUS_CONFIGURED

    def test_exact_string_value(self):
        assert STATUS_CALIBRATION_UNAVAILABLE == "calibration_unavailable"


# ---------------------------------------------------------------------------
# H: apply_per_unit_to_array/value with calibration_unavailable → ENG values
# ---------------------------------------------------------------------------

class TestApplyPuReturnsFallback:
    """Req H: apply_per_unit_to_array and apply_per_unit_to_value both return
    engineering values unchanged when status is calibration_unavailable, so the
    waveform display path works without any additional special-casing."""

    def test_array_returns_engineering_values_unchanged(self):
        from app.domain.per_unit import PerUnitResolution
        resolution = PerUnitResolution(
            status=STATUS_CALIBRATION_UNAVAILABLE,
            profile_id=None, base_amount=None, base_unit=None,
            reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        values = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        out_values, out_unit, out_status = apply_per_unit_to_array(
            values, "kV", "Voltage", resolution
        )
        np.testing.assert_array_equal(out_values, values)
        assert out_unit == "kV"
        assert out_status == STATUS_CALIBRATION_UNAVAILABLE

    def test_scalar_returns_engineering_value_unchanged(self):
        from app.domain.per_unit import PerUnitResolution
        resolution = PerUnitResolution(
            status=STATUS_CALIBRATION_UNAVAILABLE,
            profile_id=None, base_amount=None, base_unit=None,
            reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        )
        out_value, out_unit, out_status = apply_per_unit_to_value(
            1.5, "kV", "Voltage", resolution
        )
        assert out_value == pytest.approx(1.5)
        assert out_unit == "kV"
        assert out_status == STATUS_CALIBRATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# I: Angle channels → NOT_APPLICABLE (angle check runs BEFORE calibration gate)
# ---------------------------------------------------------------------------

class TestAngleChannelsBypassCalibrationGate:
    """Req I: voltage/current angle channels resolve to NOT_APPLICABLE regardless
    of calibration authority — the DEC-078 angle check runs FIRST in
    _resolve_effective_per_unit, before the calibration gate."""

    def test_voltage_angle_returns_not_applicable_even_with_unverified_authority(self):
        active = _make_active_source(
            channel_name="VA_ang",
            engineering_type="Voltage",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        # Patch the AnalogChannelSummary engineering_quantity to look like an angle.
        # We rebuild with the right engineering_quantity.
        active.metadata.analog_channels[0].engineering_quantity = ENGINEERING_QUANTITY_VOLTAGE_ANGLE

        result = _resolve_effective_per_unit(
            active, "VA_ang", "Voltage", None, None,
            workspace_id=None, group_registry=None,
            voltage_config_registry=None, current_config_registry=None,
        )
        assert result.status == STATUS_NOT_APPLICABLE


# ---------------------------------------------------------------------------
# J: extract_waveform_range integration — BEN5K PU mode
# ---------------------------------------------------------------------------

class TestExtractWaveformRangeIntegration:
    """Req J: extract_waveform_range in PU mode on a BEN5K source returns
    engineering values with per_unit_status == 'calibration_unavailable',
    so the waveform panel displays as 'PU unavailable' (engineering values shown)."""

    def test_ben5k_pu_mode_returns_calibration_unavailable_status(self):
        active = _make_active_source(channel_name="VA", engineering_type="Voltage")
        result = extract_waveform_range(
            active,
            channel_name="VA",
            start_time=None,
            end_time=None,
            point_budget=10_000,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.per_unit_status == STATUS_CALIBRATION_UNAVAILABLE

    def test_ben5k_pu_mode_returns_engineering_values_unchanged(self):
        active = _make_active_source(channel_name="VA", engineering_type="Voltage")
        # Engineering values are all 1.0 (from fixture)
        result = extract_waveform_range(
            active,
            channel_name="VA",
            start_time=None,
            end_time=None,
            point_budget=10_000,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        np.testing.assert_array_equal(result.values, np.ones(_N))

    def test_ben5k_pu_mode_returns_engineering_unit(self):
        active = _make_active_source(channel_name="VA", engineering_type="Voltage", unit="kV")
        result = extract_waveform_range(
            active,
            channel_name="VA",
            start_time=None,
            end_time=None,
            point_budget=10_000,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.unit == "kV"

    def test_comtrade_pu_mode_not_affected_by_gate(self):
        """COMTRADE sources must not be affected — PULU regression coverage."""
        active = _make_active_source(
            channel_name="VA",
            engineering_type="Voltage",
            provider_type="COMTRADE",
            time_basis=None,
            calibration_authority=None,
        )
        result = extract_waveform_range(
            active,
            channel_name="VA",
            start_time=None,
            end_time=None,
            point_budget=10_000,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        # Without a PU profile the status is base_required (normal COMTRADE behavior)
        assert result.per_unit_status == STATUS_BASE_REQUIRED

    def test_engineering_mode_unaffected_by_calibration_gate(self):
        """In engineering mode the gate does not run; no per_unit_status is set."""
        active = _make_active_source(channel_name="VA")
        result = extract_waveform_range(
            active,
            channel_name="VA",
            start_time=None,
            end_time=None,
            point_budget=10_000,
        )
        assert result.per_unit_status is None


# ---------------------------------------------------------------------------
# _calibration_blocked_reason unit tests
# ---------------------------------------------------------------------------

class TestCalibrationBlockedReasonHelper:
    """Direct unit tests for the _calibration_blocked_reason helper."""

    def test_unverified_returns_reason(self):
        active = _make_active_source(calibration_authority=_UNVERIFIED_AUTH)
        assert _calibration_blocked_reason("VA", active) == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_invalid_returns_reason(self):
        active = _make_active_source(calibration_authority=_INVALID_AUTH)
        result = _calibration_blocked_reason("VA", active)
        assert result == _INVALID_AUTH.reason

    def test_verified_returns_none(self):
        active = _make_active_source(calibration_authority=_VERIFIED_AUTH)
        assert _calibration_blocked_reason("VA", active) is None

    def test_comtrade_none_returns_none(self):
        active = _make_active_source(
            provider_type="COMTRADE", time_basis=None, calibration_authority=None
        )
        assert _calibration_blocked_reason("VA", active) is None

    def test_ben5k_format_variant_none_auth_returns_ben5k_code(self):
        active = _make_active_source(
            provider_type="BEN",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=None,
        )
        assert _calibration_blocked_reason("VA", active) == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED

    def test_ben_no_format_variant_none_auth_returns_none(self):
        """SubBen/VERIFIED_UTC without BEN5K format_variant: not blocked."""
        active = _make_active_source(
            provider_type="BEN",
            time_basis=TimeBasis.VERIFIED_UTC,
            format_variant=None,
            calibration_authority=None,
        )
        assert _calibration_blocked_reason("VA", active) is None

    def test_channel_not_in_record_non_ben5k_returns_none(self):
        """Non-BEN5K: missing channel → not blocked (backward compat)."""
        active = _make_active_source(channel_name="VA", format_variant=None)
        assert _calibration_blocked_reason("VB_nonexistent", active) is None

    def test_channel_not_in_record_ben5k_returns_blocked(self):
        """BEN5K: missing channel must NOT silently authorize PU (DEC-213 Item 1)."""
        active = _make_active_source(
            channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        # VB_nonexistent is not in the record — BEN5K must block it
        assert _calibration_blocked_reason("VB_nonexistent", active) == REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED


# ---------------------------------------------------------------------------
# K: cursor API end-to-end — BEN5K PU mode returns calibration_unavailable
#    with engineering values and engineering unit (DEC-213 Item 2)
# ---------------------------------------------------------------------------

class TestCursorValuesIntegration:
    """Req K: extract_cursor_values in PU mode on a BEN5K source returns
    calibration_unavailable with engineering values (not PU-converted values)
    and the engineering unit (not 'pu')."""

    def _active(self) -> ActiveSource:
        return _make_active_source(channel_name="VA", engineering_type="Voltage", unit="kV")

    def test_per_unit_status_is_calibration_unavailable(self):
        result = extract_cursor_values(
            self._active(),
            analog_channel_names=["VA"],
            digital_channel_names=[],
            cursor_a_time=0.0,
            cursor_b_time=0.01,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert len(result.channels) == 1
        assert result.channels[0].per_unit_status == STATUS_CALIBRATION_UNAVAILABLE

    def test_a_value_is_engineering_value(self):
        result = extract_cursor_values(
            self._active(),
            analog_channel_names=["VA"],
            digital_channel_names=[],
            cursor_a_time=0.0,
            cursor_b_time=None,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        # Fixture values are all 1.0 kV
        assert result.channels[0].a_value == pytest.approx(1.0)

    def test_b_value_is_engineering_value(self):
        result = extract_cursor_values(
            self._active(),
            analog_channel_names=["VA"],
            digital_channel_names=[],
            cursor_a_time=None,
            cursor_b_time=0.01,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.channels[0].b_value == pytest.approx(1.0)

    def test_unit_is_engineering_unit_not_pu(self):
        result = extract_cursor_values(
            self._active(),
            analog_channel_names=["VA"],
            digital_channel_names=[],
            cursor_a_time=0.0,
            cursor_b_time=0.01,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.channels[0].unit == "kV"
        assert result.channels[0].unit != "pu"


# ---------------------------------------------------------------------------
# L: peak API end-to-end — BEN5K PU mode returns calibration_unavailable
#    with engineering value and engineering unit (DEC-213 Item 2)
# ---------------------------------------------------------------------------

class TestPeakValueIntegration:
    """Req L: resolve_peak_value in PU mode on a BEN5K source returns
    calibration_unavailable with the engineering peak value and engineering unit."""

    def _active(self) -> ActiveSource:
        return _make_active_source(channel_name="VA", engineering_type="Voltage", unit="kV")

    def test_per_unit_status_is_calibration_unavailable(self):
        result = resolve_peak_value(
            self._active(),
            channel_name="VA",
            mode=PEAK_MODE_MAX,
            start_time=0.0,
            end_time=float(_N - 1) / _RATE,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.per_unit_status == STATUS_CALIBRATION_UNAVAILABLE

    def test_value_is_engineering_value(self):
        result = resolve_peak_value(
            self._active(),
            channel_name="VA",
            mode=PEAK_MODE_MAX,
            start_time=0.0,
            end_time=float(_N - 1) / _RATE,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        # Fixture values are all 1.0 kV; max is 1.0
        assert result.available is True
        assert result.value == pytest.approx(1.0)

    def test_unit_is_engineering_unit_not_pu(self):
        result = resolve_peak_value(
            self._active(),
            channel_name="VA",
            mode=PEAK_MODE_MAX,
            start_time=0.0,
            end_time=float(_N - 1) / _RATE,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.unit == "kV"
        assert result.unit != "pu"


# ---------------------------------------------------------------------------
# M: annotation anchor end-to-end — BEN5K PU mode returns calibration_unavailable
#    with engineering value and engineering unit (DEC-213 Item 2)
# ---------------------------------------------------------------------------

class TestAnnotationAnchorIntegration:
    """Req M: resolve_annotation_anchor in PU mode on a BEN5K source returns
    calibration_unavailable with the engineering anchor value and engineering unit."""

    def _active(self) -> ActiveSource:
        return _make_active_source(channel_name="VA", engineering_type="Voltage", unit="kV")

    def test_per_unit_status_is_calibration_unavailable(self):
        result = resolve_annotation_anchor(
            self._active(),
            channel_name="VA",
            approximate_elapsed_seconds=0.01,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.per_unit_status == STATUS_CALIBRATION_UNAVAILABLE

    def test_value_is_engineering_value(self):
        result = resolve_annotation_anchor(
            self._active(),
            channel_name="VA",
            approximate_elapsed_seconds=0.01,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        # Fixture values are all 1.0 kV
        assert result.value == pytest.approx(1.0)

    def test_unit_is_engineering_unit_not_pu(self):
        result = resolve_annotation_anchor(
            self._active(),
            channel_name="VA",
            approximate_elapsed_seconds=0.01,
            unit_mode=UNIT_MODE_PER_UNIT,
        )
        assert result.unit == "kV"
        assert result.unit != "pu"
