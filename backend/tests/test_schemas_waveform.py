"""Unit tests for app.schemas.waveform's JSON-boundary sanitization
(DEC-084, Slice 3 tightening).

Direct, schema-level tests against a hand-built `WaveformRangeResult` --
these prove the finite-time invariant independent of whether the full
CSV/Excel -> conversion pipeline can ever actually produce a non-finite
`time` value (it structurally cannot, since
`app.domain.disturbance_record.DisturbanceRecord.validate()` already
enforces finiteness upstream -- this file is the defensive/invariant
layer of coverage, complementing the end-to-end HTTP-level coverage in
tests/test_waveform_api.py::TestExplicitNullSourceChannelSerialization).
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from app.schemas.waveform import (
    WaveformRangeOut,
    _require_finite_time_array,
    _sanitize_float_array,
)
from app.services.waveform_service import WaveformRangeResult


def _result(*, time: np.ndarray, values: np.ndarray) -> WaveformRangeResult:
    return WaveformRangeResult(
        source_id="src-1",
        channel_name="VA",
        unit="V",
        start_time=float(time[0]),
        end_time=float(time[-1]),
        original_sample_count=int(time.shape[0]),
        representation="full_resolution",
        time=time,
        values=values,
    )


class TestFiniteTimeSerializesNormally:
    def test_finite_time_produces_ordinary_json_numbers(self):
        result = _result(
            time=np.array([0.0, 1.0, 2.0]),
            values=np.array([10.0, 11.0, 12.0]),
        )

        out = WaveformRangeOut.from_result(result)

        assert out.time == [0.0, 1.0, 2.0]
        assert all(isinstance(t, float) for t in out.time)


class TestWaveformNullValueSanitization:
    def test_explicit_null_value_serializes_as_none(self):
        result = _result(
            time=np.array([0.0, 1.0, 2.0]),
            values=np.array([10.0, np.nan, 12.0]),
        )

        out = WaveformRangeOut.from_result(result)

        assert out.values == [10.0, None, 12.0]

    def test_sanitize_float_array_never_substitutes_zero(self):
        assert _sanitize_float_array(np.array([np.nan])) == [None]


class TestTimeSchemaRemainsNonNullable:
    def test_time_field_rejects_none_directly(self):
        # Constructing the pydantic model directly with a None in `time`
        # must be rejected outright -- `time: list[float]` is NOT
        # `list[float | None]`, unlike `values`.
        with pytest.raises(ValidationError):
            WaveformRangeOut(
                source_id="src-1", channel_name="VA", unit="V",
                start_time=0.0, end_time=2.0, original_sample_count=3,
                returned_point_count=3, representation="full_resolution",
                time=[0.0, None, 2.0], values=[10.0, 11.0, 12.0],
            )

    def test_values_field_still_accepts_none(self):
        # The contrast case -- `values` staying nullable is the approved,
        # unchanged Slice 3 behavior; only `time` was tightened.
        out = WaveformRangeOut(
            source_id="src-1", channel_name="VA", unit="V",
            start_time=0.0, end_time=2.0, original_sample_count=3,
            returned_point_count=3, representation="full_resolution",
            time=[0.0, 1.0, 2.0], values=[10.0, None, 12.0],
        )
        assert out.values == [10.0, None, 12.0]


class TestNonFiniteTimeIsNeverSilentlySanitized:
    def test_require_finite_time_array_raises_on_nan(self):
        with pytest.raises(ValueError):
            _require_finite_time_array(np.array([0.0, np.nan, 2.0]))

    def test_require_finite_time_array_raises_on_inf(self):
        with pytest.raises(ValueError):
            _require_finite_time_array(np.array([0.0, np.inf, 2.0]))

    def test_from_result_raises_rather_than_producing_a_null_time(self):
        # The core regression this tightening exists for: a non-finite
        # time reaching this boundary must fail LOUDLY, never quietly
        # degrade into a `null` time coordinate the way a Waveform/data
        # gap legitimately does.
        result = _result(
            time=np.array([0.0, np.nan, 2.0]),
            values=np.array([10.0, 11.0, 12.0]),
        )

        with pytest.raises(ValueError):
            WaveformRangeOut.from_result(result)

    def test_require_finite_time_array_accepts_all_finite(self):
        # Sanity check: the guard itself does not reject legitimate data.
        assert _require_finite_time_array(np.array([0.0, 1.0, 2.0])) == [0.0, 1.0, 2.0]


class TestArrayLengthAlignmentPreservedForLegitimateGaps:
    def test_time_and_values_length_match_with_a_waveform_gap(self):
        # A legitimate, DEC-084-approved Waveform/data gap must never
        # affect `time`'s own length or finiteness -- only `values` at
        # the corresponding position becomes `null`.
        result = _result(
            time=np.array([0.0, 1.0, 2.0]),
            values=np.array([10.0, np.nan, 12.0]),
        )

        out = WaveformRangeOut.from_result(result)

        assert len(out.time) == len(out.values) == 3
        assert out.time == [0.0, 1.0, 2.0]
        assert out.values == [10.0, None, 12.0]
