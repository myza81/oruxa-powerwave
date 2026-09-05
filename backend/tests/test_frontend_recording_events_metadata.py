"""Structural checks for the Recording Events metadata display
consistency fix:

1. Sampling-rate display robustness -- `SAMPLING_RATE_INTEGER_TOLERANCE_HZ`
   was too tight (`1e-9`), so a genuinely-integer engineering rate like
   50 Hz arriving as `50.00000008` (accumulated floating-point noise from
   averaging measured sample intervals, not a real fractional rate) printed
   in full instead of collapsing to "50 Hz".
2. Start Time for `Time of Day` sources -- `formatRecordingStartTime()`
   read only `source.start_time`, which is deliberately `None` for a
   `time_of_day` source (no fabricated date), so a source with a known
   clock-time origin (`time_of_day_reference_seconds`) showed "-" even
   though that origin is known.

These are static source-text checks, the same convention every other
test_frontend_*.py file in this suite uses -- no JS execution engine is
part of this repository's test harness.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class TestSamplingRateToleranceRobustness:
    def test_tolerance_loosened_past_observed_float_noise(self):
        source = _source()
        # The UAT-reported noise (50.00000008 / 49.99999998) is ~1e-8 away
        # from the nearest integer -- the tolerance must exceed that, and
        # stay far below any genuinely fractional rate this app displays
        # (0.10, 0.25 Hz), so both directions of the required behavior
        # hold simultaneously.
        assert "const SAMPLING_RATE_INTEGER_TOLERANCE_HZ = 1e-6;" in source
        assert "const SAMPLING_RATE_INTEGER_TOLERANCE_HZ = 1e-9;" not in source

    def test_only_one_sampling_rate_tolerance_constant_exists(self):
        source = _source()
        assert source.count("SAMPLING_RATE_INTEGER_TOLERANCE_HZ") >= 1
        assert source.count("const SAMPLING_RATE_INTEGER_TOLERANCE_HZ") == 1

    def test_formatter_still_rounds_off_near_integers(self):
        # The near-integer branch itself is unchanged -- only the
        # tolerance moved.
        source = _source()
        body = _function_body(
            source, "function formatSamplingRate(rate)", "function formatSamplingRates(rates)",
        )
        assert "Math.round(rate)" in body
        assert "SAMPLING_RATE_INTEGER_TOLERANCE_HZ" in body
        assert "toPrecision(12)" in body


class TestFractionalSamplingRatePresentation:
    """Presentation fix, second pass: a genuine fractional rate must show
    at least 2 decimal places (50.10 Hz, not 50.1 Hz -- `.toString()`
    drops a trailing zero) WITHOUT hiding more meaningful precision a
    rate actually carries (a rate genuinely precise to 6 decimals must
    still show all 6, never truncated to 2). Exact numeric behavior for
    the required values (50.00000008/49.99999998/50.10/50.25) is verified
    live in the browser UAT (this suite has no JS execution engine, see
    module docstring) -- these are structural checks that the padding
    mechanism itself is present and does not clamp/truncate precision."""

    def test_uses_toFixed_with_a_floor_of_two_not_a_fixed_two(self):
        source = _source()
        body = _function_body(
            source, "function formatSamplingRate(rate)", "function formatSamplingRates(rates)",
        )
        assert "Math.max(2, decimalPart.length)" in body
        assert "cleaned.toFixed(digits)" in body
        # Never a hardcoded toFixed(2) -- that would truncate a rate with
        # more than 2 meaningful decimal places.
        assert "toFixed(2)" not in body

    def test_only_one_fractional_sampling_rate_formatter_exists(self):
        # Guards against a second, Recording-Events-only formatter being
        # introduced instead of adjusting the one shared implementation.
        source = _source()
        assert source.count("function formatSamplingRate(rate)") == 1


class TestStartTimeIsTimeDomainAware:
    def test_formatter_takes_the_whole_source_not_just_start_time(self):
        source = _source()
        assert "function formatRecordingStartTime(source)" in source
        assert "function formatRecordingStartTime(startTime)" not in source

    def test_time_of_day_branch_uses_reference_seconds_not_start_time(self):
        source = _source()
        body = _function_body(
            source,
            "function formatRecordingStartTime(source)",
            "function formatSamplingRate(rate)",
        )
        assert 'source.timing_reference === "time_of_day"' in body
        assert "source.time_of_day_reference_seconds" in body
        # Reuses the existing shared clock-string builder rather than a
        # second, divergent HH:MM:SS implementation.
        assert "wwFormatClockTimeFromTotalSeconds(source.time_of_day_reference_seconds" in body
        # The date flag must stay off -- Time of Day never shows a date.
        assert "wwFormatClockTimeFromTotalSeconds(source.time_of_day_reference_seconds, 3, false)" in body

    def test_non_time_of_day_branch_still_reads_start_time_unchanged(self):
        source = _source()
        body = _function_body(
            source,
            "function formatRecordingStartTime(source)",
            "function formatSamplingRate(rate)",
        )
        assert 'source.start_time ? source.start_time.replace("T", " ") : "—"' in body

    def test_call_site_passes_the_whole_source_not_just_start_time(self):
        source = _source()
        assert "formatRecordingStartTime(source)" in source
        assert "formatRecordingStartTime(source.start_time)" not in source

    def test_no_synthetic_date_is_ever_introduced(self):
        source = _source()
        body = _function_body(
            source,
            "function formatRecordingStartTime(source)",
            "function formatSamplingRate(rate)",
        )
        assert "1970-01-01" not in body
        assert "new Date()" not in body
