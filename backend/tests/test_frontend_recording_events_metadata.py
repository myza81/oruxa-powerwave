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
        # tolerance moved (in the earlier fix) and the fractional branch
        # below it (second pass, owner UAT 2026-09-10).
        source = _source()
        body = _function_body(
            source, "function formatSamplingRate(rate)", "function formatSamplingRates(rates)",
        )
        assert "Math.round(rate)" in body
        assert "SAMPLING_RATE_INTEGER_TOLERANCE_HZ" in body


class TestFractionalSamplingRatePresentation:
    """Presentation fix, second pass (owner UAT 2026-09-10): a CSV/Excel
    source with a genuine 60s sample interval reported
    "0.0166666666667 Hz" -- audited first and confirmed NOT a derivation
    bug (see test_preparation_conversion_service.py's own
    TestSamplingMetadata -- 1/60 Hz is the mathematically correct rate
    for that recording). The first pass's own "at least 2 decimal
    places, preserve however much noise-stripped precision remains" rule
    only fixed the ORIGINAL reported noise (50.00000008 Hz); it did
    nothing for a genuinely small fractional rate, since 1/60's own
    decimal expansion never terminates. Replaced with a fixed
    SIGNIFICANT-DIGIT count (scales with magnitude, unlike a fixed
    decimal-place count) -- this SUPERSEDES the first pass's own "must
    show all 6 decimals if a rate is genuinely precise to 6 decimals"
    requirement in favor of a bounded, human-readable precision; a
    formerly-required trailing zero (50.10) is also no longer added
    (50.1 -- `Number(...)` naturally strips it). Exact numeric behavior
    for the full required matrix (5000/5000.00000001/50.00000008/50.1/1/
    0.5/0.0166666666667) is locked with real JS execution in
    browser-tests/sampling-rate-format.spec.js (this suite has no JS
    execution engine, see module docstring) -- these remain structural
    checks that only ONE shared implementation exists and uses the new
    mechanism, not exact-value assertions."""

    def test_uses_a_fixed_significant_digit_count_not_decimal_places(self):
        source = _source()
        body = _function_body(
            source, "function formatSamplingRate(rate)", "function formatSamplingRates(rates)",
        )
        assert "const rounded = Number(rate.toPrecision(SAMPLING_RATE_SIGNIFICANT_DIGITS));" in body
        assert "return rounded + \" Hz\";" in body
        # The old magnitude-blind decimal-place mechanism must be gone,
        # not left dangling alongside the new one.
        assert "decimalPart" not in body
        assert "toFixed" not in body

    def test_significant_digit_constant_is_defined_exactly_once(self):
        source = _source()
        assert "const SAMPLING_RATE_SIGNIFICANT_DIGITS = 4;" in source
        assert source.count("SAMPLING_RATE_SIGNIFICANT_DIGITS") >= 2  # declaration + use
        assert source.count("const SAMPLING_RATE_SIGNIFICANT_DIGITS") == 1

    def test_only_one_fractional_sampling_rate_formatter_exists(self):
        # Guards against a second, Recording-Events-only formatter being
        # introduced instead of adjusting the one shared implementation.
        source = _source()
        assert source.count("function formatSamplingRate(rate)") == 1


class TestRecordingEventsTableUsesTheCleanedFormatter:
    """Regression proving the Recording Events LIST ITSELF routes through
    formatSamplingRates()/formatSamplingRate() -- not only that the
    helper functions exist correctly in isolation (task's own explicit
    "do not test only the helper" instruction). A raw numeric
    interpolation of `source.sampling_rates` directly into the row's own
    markup, bypassing the formatter entirely, would have reproduced the
    reported bug regardless of how correct the formatter itself is."""

    def test_sampling_rates_cell_calls_the_shared_formatter(self):
        source = _source()
        fn_idx = source.index("function renderRecordingsTable(sources)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert '<td class="recording-sampling-rates-cell">' in fn_body
        assert "formatSamplingRates(source.sampling_rates)" in fn_body
        # No raw numeric interpolation of the rates array bypassing the
        # formatter (e.g. `.join(", ")` directly on the raw array/a
        # template literal reading `source.sampling_rates` without going
        # through formatSamplingRates() first).
        assert "source.sampling_rates.join" not in fn_body
        assert 'source.sampling_rates.map((r) => r + " Hz")' not in fn_body


class TestStartTimeIsTimeDomainAware:
    """`formatRecordingStartTime()` is now a thin wrapper over the SHARED
    `wwFormatRecordingTimeIdentity()` policy (time-identity consistency
    fix) -- these tests check the shared function's own body, which is
    where the real branch logic now lives, plus that the Recordings
    table's own call site still passes the whole `source` unchanged."""

    def test_formatter_takes_the_whole_source_not_just_start_time(self):
        source = _source()
        assert "function formatRecordingStartTime(source)" in source
        assert "function formatRecordingStartTime(startTime)" not in source

    def test_start_time_formatter_delegates_to_the_shared_helper(self):
        source = _source()
        body = _function_body(
            source,
            "function formatRecordingStartTime(source)",
            "function formatSamplingRate(rate)",
        )
        assert "return wwFormatRecordingTimeIdentity(source);" in body

    def test_time_of_day_branch_uses_reference_seconds_not_start_time(self):
        source = _source()
        body = _function_body(
            source,
            "function wwFormatRecordingTimeIdentity(source, opts)",
            "function formatRecordingStartTime(source)",
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
            "function wwFormatRecordingTimeIdentity(source, opts)",
            "function formatRecordingStartTime(source)",
        )
        assert "source.start_time.replace(\"T\", \" \")" in body

    def test_non_absolute_non_time_of_day_falls_back_to_a_named_label_not_a_dash(self):
        # Time-identity consistency fix: the old unconditional "—"
        # fallback is gone -- a genuinely non-positional Time Axis
        # (Elapsed/Sample Index/Reconstructed-without-origin/Manual)
        # names itself instead, reusing the SAME label map the Data
        # Preparation Time Format dropdown already uses.
        source = _source()
        body = _function_body(
            source,
            "function wwFormatRecordingTimeIdentity(source, opts)",
            "function formatRecordingStartTime(source)",
        )
        assert "WW_DATA_PREP_INTERPRETER_LABELS[source.preparation_interpreter_id] || \"—\"" in body

    def test_call_site_passes_the_whole_source_not_just_start_time(self):
        source = _source()
        assert "formatRecordingStartTime(source)" in source
        assert "formatRecordingStartTime(source.start_time)" not in source

    def test_no_synthetic_date_is_ever_introduced(self):
        source = _source()
        body = _function_body(
            source,
            "function wwFormatRecordingTimeIdentity(source, opts)",
            "function formatSamplingRate(rate)",
        )
        assert "1970-01-01" not in body
        assert "new Date()" not in body
