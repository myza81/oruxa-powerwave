"""Unit tests for app.services.time_axis_normalization -- specifically
the FAMILY_PARTIAL (Time of Day) midnight-rollover unwrap added
alongside the new Time of Day interpreter. Pure functions only.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.domain.time_axis import FAMILY_ABSOLUTE, FAMILY_PARTIAL
from app.services.time_axis_normalization import (
    format_time_of_day,
    relative_seconds,
    relative_seconds_with_anchor,
    seconds_from_midnight,
)


def _t(text: str) -> dt.time:
    return dt.datetime.strptime(text, "%H:%M:%S.%f").time()


class TestSecondsFromMidnight:
    def test_basic_conversion(self):
        assert seconds_from_midnight(_t("18:04:00.020000")) == pytest.approx(65040.02)


class TestPartialFamilyNoRollover:
    """Regression: ordinary, non-rollover FAMILY_PARTIAL sequences must
    compute exactly as they always have (no behavior change for the
    common case)."""

    def test_monotonic_sequence_unchanged(self):
        natives = [_t("18:04:00.000000"), _t("18:04:00.020000"), _t("18:04:00.040000")]
        result = relative_seconds(natives, family=FAMILY_PARTIAL)
        assert result == pytest.approx([0.0, 0.02, 0.04])


class TestPartialFamilyMidnightRollover:
    """Task's own Case 8: 23:59:59.980, 00:00:00.000, 00:00:00.020 must
    produce a continuous, monotonic-increasing elapsed sequence -- never
    a fabricated date, never a negative jump at the rollover point."""

    def test_rollover_produces_continuous_monotonic_sequence(self):
        natives = [_t("23:59:59.980000"), _t("00:00:00.000000"), _t("00:00:00.020000")]
        result = relative_seconds(natives, family=FAMILY_PARTIAL)
        assert result == pytest.approx([0.0, 0.02, 0.04])
        assert all(result[i] <= result[i + 1] for i in range(len(result) - 1))

    def test_rollover_with_external_anchor(self):
        anchor = _t("23:59:59.980000")
        natives = [_t("00:00:00.000000"), _t("00:00:00.020000")]
        result = relative_seconds_with_anchor(natives, anchor, family=FAMILY_PARTIAL)
        assert result == pytest.approx([0.02, 0.04])

    def test_an_ordinary_backward_jump_far_from_midnight_is_not_unwrapped(self):
        # Conservative guardrail: a backward jump that does NOT land
        # within the day-boundary window on both sides must stay exactly
        # as it always was (a plain, non-unwrapped, negative delta) --
        # never treated as a rollover on a broad heuristic.
        natives = [_t("12:00:00.000000"), _t("11:59:00.000000")]
        result = relative_seconds(natives, family=FAMILY_PARTIAL)
        assert result == pytest.approx([0.0, -60.0])

    def test_absolute_family_is_completely_unaffected(self):
        base = dt.datetime(2026, 6, 3, 23, 59, 59)
        natives = [base, base + dt.timedelta(seconds=2)]
        result = relative_seconds(natives, family=FAMILY_ABSOLUTE)
        assert result == pytest.approx([0.0, 2.0])


class TestFormatTimeOfDay:
    """Time of Day (additive) presentation formatter -- the ONE shared
    implementation `table_service.py`/`time_axis_service.py`'s own
    Configured Time column both reuse."""

    def test_basic_formatting(self):
        assert format_time_of_day(65040.0) == "18:04:00.000"
        assert format_time_of_day(65040.02) == "18:04:00.020"
        assert format_time_of_day(65040.04) == "18:04:00.040"

    def test_wraps_past_86400_for_display_only(self):
        # 86400.02 is 20ms past midnight -- must wrap to 00:00:00.020,
        # never a fabricated day-2 indicator.
        assert format_time_of_day(86400.02) == "00:00:00.020"

    def test_exactly_midnight(self):
        assert format_time_of_day(86400.0) == "00:00:00.000"

    def test_distinguishable_nearby_millisecond_values(self):
        # Precision guardrail: distinct samples 20ms apart must remain
        # visually distinguishable, never rounded into the same string.
        assert format_time_of_day(65040.0) != format_time_of_day(65040.02)
        assert format_time_of_day(65040.02) != format_time_of_day(65040.04)
