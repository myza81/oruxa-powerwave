"""Unit tests for the deterministic absolute-time (Slice 8A),
elapsed-time/sample-index (Slice 8B), and repeated-timestamp/
precision-loss reconstruction (Slice 8C) parsing/detection functions
(CSV/Excel ingestion, DEC-072). Pure functions only -- no session, no
registry, no HTTP; service-layer wiring is covered by
tests/test_time_axis_service.py's own new test classes.
"""

from __future__ import annotations

import pytest

from app.domain.preparation_issue import SEVERITY_WARNING
from app.domain.time_axis import (
    AMBIGUITY_AMBIGUOUS,
    AMBIGUITY_INVALID,
    AMBIGUITY_UNAMBIGUOUS,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
    DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED,
    DIAGNOSTIC_CADENCE_NOT_RELIABLE,
    DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD,
    DIAGNOSTIC_INCONSISTENT_BUCKET_COUNT,
    DIAGNOSTIC_LARGE_TIME_GAP,
    DIAGNOSTIC_MISSING_DATETIME_VALUE,
    DIAGNOSTIC_MISSING_ELAPSED_UNIT,
    DIAGNOSTIC_MISSING_ELAPSED_VALUE,
    DIAGNOSTIC_MISSING_SAMPLE_INDEX,
    DIAGNOSTIC_MIXED_DATETIME_FORMAT,
    DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE,
    DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX,
    DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL,
    DIAGNOSTIC_NON_UNIFORM_INTERVAL,
    DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED,
    DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE,
    DIAGNOSTIC_PRECISION_LOSS_SUSPECTED,
    DIAGNOSTIC_REPEATED_ELAPSED_TIME,
    DIAGNOSTIC_REPEATED_SAMPLE_INDEX,
    DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED,
    DIAGNOSTIC_SAMPLE_INDEX_GAP,
    DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD,
    DIAGNOSTIC_TIME_GOES_BACKWARD,
    DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE,
    DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED,
    DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT,
    DIAGNOSTIC_UNPARSEABLE_DATETIME,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    PROVENANCE_RECONSTRUCTED,
    PROVENANCE_USER_SPECIFIED,
)
from app.services.time_axis_interpreters import (
    build_absolute_datetime_preview,
    build_elapsed_preview,
    build_repeated_timestamp_preview,
    build_sample_index_preview,
    build_split_date_time_preview,
    detect_absolute_datetime,
    detect_elapsed_numeric,
    detect_repeated_timestamp_precision_loss,
    detect_sample_index,
    detect_split_date_time,
)


def _rows(values: list[str | None]) -> list[tuple[int, str | None]]:
    return list(enumerate(values, start=1))


class TestSingleColumnIsoDatetime:
    def test_iso_with_space_separator_and_fractional_seconds(self):
        result = detect_absolute_datetime(
            _rows(["2026-08-31 13:09:44.305", "2026-08-31 13:09:45.505"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_NATIVE
        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []
        assert result.resolved_options["date_order"] == "ymd"

    def test_iso_with_t_separator(self):
        result = detect_absolute_datetime(_rows(["2026-08-31T13:09:44.305"]), requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        assert result.diagnostics == []

    def test_iso_with_timezone_offset_is_preserved_through_parsing(self):
        from app.services.time_axis_interpreters import parse_absolute_datetime

        parsed = parse_absolute_datetime("2026-08-31T13:09:44.305+08:00", date_order="ymd")

        assert parsed is not None
        assert parsed.utcoffset() is not None
        assert parsed.isoformat() == "2026-08-31T13:09:44.305000+08:00"

    def test_iso_without_timezone_stays_naive_never_invented(self):
        from app.services.time_axis_interpreters import parse_absolute_datetime

        parsed = parse_absolute_datetime("2026-08-31T13:09:44.305", date_order="ymd")

        assert parsed is not None
        assert parsed.tzinfo is None

    def test_24_hour_time(self):
        result = detect_absolute_datetime(_rows(["2026-08-31 23:15:00"]), requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        assert result.diagnostics == []


class TestSingleColumnSlashDashOrders:
    def test_dmy_unambiguous_by_elimination_day_over_twelve(self):
        # Chronologically ascending (day 30 then day 31) -- day=31 alone
        # is what rules out `mdy` here; ordering is irrelevant to that,
        # and ascending avoids also exercising Slice 8D's own new
        # backward-time detection, which is covered by its own tests.
        result = detect_absolute_datetime(
            _rows(["30/08/2026 13:09:44.305", "31/08/2026 13:09:45.505"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_NATIVE
        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []
        assert result.resolved_options["date_order"] == "dmy"

    def test_dmy_with_dash_separator(self):
        result = detect_absolute_datetime(_rows(["31-08-2026 13:09:44.305"]), requested_options={})

        assert result.resolved_options["date_order"] == "dmy"
        assert result.diagnostics == []

    def test_mdy_am_pm_form(self):
        # Chronologically ascending -- see the dmy elimination test's own
        # comment above for why order matters now that Slice 8D checks it.
        result = detect_absolute_datetime(
            _rows(["08/30/2026 2:15:00 AM", "08/31/2026 1:09:44 PM"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []
        assert result.resolved_options["date_order"] == "mdy"

    def test_ambiguous_date_order_produces_diagnostic_and_low_confidence(self):
        result = detect_absolute_datetime(
            _rows(["01/02/2026 13:09:44", "03/04/2026 13:09:45"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER in codes
        ambiguous_diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_AMBIGUOUS_DATE_ORDER)
        assert ambiguous_diag.ambiguity == AMBIGUITY_AMBIGUOUS
        assert result.resolved_options["date_order"] == "auto"

    def test_ambiguous_date_order_resolved_by_explicit_user_choice(self):
        result = detect_absolute_datetime(
            _rows(["01/02/2026 13:09:44", "03/04/2026 13:09:45"]), requested_options={"date_order": "dmy"},
        )

        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.confidence == CONFIDENCE_HIGH
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in result.diagnostics)
        assert result.resolved_options["date_order"] == "dmy"

    def test_single_valid_order_wins_even_if_a_different_order_was_requested(self):
        # The data itself is unambiguous (day=31 rules out mdy) -- the
        # data wins regardless of what was requested.
        result = detect_absolute_datetime(
            _rows(["31/08/2026 13:09:44"]), requested_options={"date_order": "mdy"},
        )

        assert result.resolved_options["date_order"] == "dmy"
        assert result.provenance == PROVENANCE_NATIVE


class TestSingleColumnMinuteResolution24Hour:
    """Enhancement (minute/AM-PM-hour absolute time support): the
    reported gap -- 24-hour HH:MM with no seconds -- across every
    date order, plus the owner's own confirmed reproduction case."""

    def test_reported_bug_dmy_mdy_ambiguous_stays_review_required(self):
        # The exact reported example -- must stay ambiguous, never
        # silently resolved just because minute-resolution now parses.
        result = detect_absolute_datetime(
            _rows(["3/6/2026 17:25", "3/6/2026 17:26", "3/6/2026 17:27"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER in codes
        assert result.resolved_options["date_order"] == "auto"

    def test_reported_bug_resolved_by_explicit_date_order(self):
        result = detect_absolute_datetime(
            _rows(["3/6/2026 17:25", "3/6/2026 17:26"]), requested_options={"date_order": "dmy"},
        )

        assert result.confidence == CONFIDENCE_HIGH
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in result.diagnostics)
        assert result.resolved_options["date_order"] == "dmy"

    def test_dmy_unambiguous_by_elimination(self):
        result = detect_absolute_datetime(
            _rows(["31/08/2026 17:25", "31/08/2026 17:26"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []
        assert result.resolved_options["date_order"] == "dmy"

    def test_mdy_explicit(self):
        result = detect_absolute_datetime(
            _rows(["08/31/2026 17:25", "08/31/2026 17:26"]), requested_options={},
        )

        assert result.resolved_options["date_order"] == "mdy"
        assert result.diagnostics == []

    def test_ymd_iso_style(self):
        result = detect_absolute_datetime(
            _rows(["2026-08-31 17:25", "2026-08-31 17:26"]), requested_options={},
        )

        assert result.resolved_options["date_order"] == "ymd"
        assert result.resolved_options["detected_format"] == "ISO-8601"
        assert result.diagnostics == []

    def test_full_seconds_precision_unaffected(self):
        # Regression: the new %H:%M pattern must never shadow the
        # existing, more specific %H:%M:%S pattern.
        result = detect_absolute_datetime(
            _rows(["31/08/2026 17:25:30", "31/08/2026 17:26:31"]), requested_options={},
        )

        assert result.resolved_options["detected_format"] == "DD/MM/YYYY HH:mm:ss"
        assert result.diagnostics == []

    def test_fractional_seconds_unaffected(self):
        result = detect_absolute_datetime(_rows(["2026-08-31 17:25:30.123456"]), requested_options={})

        assert result.resolved_options["detected_format"] == "ISO-8601"
        assert result.diagnostics == []


class TestSingleColumnBareHourOnlyRemainsUnsupported:
    """Enhancement scope boundary (task section H): a bare 24-hour
    hour-only value must NOT be newly accepted by this enhancement."""

    def test_bare_hour_only_still_unparseable(self):
        result = detect_absolute_datetime(_rows(["3/6/2026 17", "3/6/2026 18"]), requested_options={})

        assert result.confidence == CONFIDENCE_UNKNOWN
        assert DIAGNOSTIC_UNPARSEABLE_DATETIME in [d.code for d in result.diagnostics]


class TestSingleColumnHourOnlyExplicitAmPm:
    """Enhancement (minute/AM-PM-hour absolute time support): explicit
    AM/PM hour-only forms ("1pm", "1 PM", "2am") -- approved because
    the AM/PM marker makes the time-of-day unambiguous, unlike a bare
    24-hour hour-only value."""

    def test_no_space_lowercase(self):
        result = detect_absolute_datetime(
            _rows(["2026-06-03 1pm", "2026-06-03 2pm", "2026-06-03 3pm"]), requested_options={},
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []

    def test_space_and_uppercase(self):
        result = detect_absolute_datetime(
            _rows(["2026-06-03 1 PM", "2026-06-03 2 PM"]), requested_options={},
        )

        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []

    def test_case_insensitive_mixed(self):
        result = detect_absolute_datetime(_rows(["2026-06-03 2Am"]), requested_options={})

        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []

    @pytest.mark.parametrize(
        "text,expected_hour,expected_minute",
        [
            ("2026-06-03 1pm", 13, 0),
            ("2026-06-03 2am", 2, 0),
            ("2026-06-03 12am", 0, 0),
            ("2026-06-03 12pm", 12, 0),
        ],
    )
    def test_exact_hour_resolved(self, text, expected_hour, expected_minute):
        from app.services.time_axis_interpreters import parse_absolute_datetime

        parsed = parse_absolute_datetime(text, date_order="ymd")

        assert parsed is not None
        assert parsed.hour == expected_hour
        assert parsed.minute == expected_minute
        assert parsed.second == 0

    def test_does_not_shadow_more_specific_time_with_minutes_or_seconds(self):
        # Regression: "%I%p"/"%I %p" must never match a longer, more
        # specific string like "1:00 pm" or "1:00:30 pm".
        result = detect_absolute_datetime(
            _rows(["2026-06-03 1:00 PM", "2026-06-03 2:00 PM"]), requested_options={},
        )

        assert result.resolved_options["detected_format"] == "YYYY-MM-DD hh:mm A"
        assert result.diagnostics == []


class TestSingleColumnInvalidAndMixed:
    def test_clearly_invalid_value_is_unparseable(self):
        result = detect_absolute_datetime(_rows(["not-a-date-at-all"]), requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_UNPARSEABLE_DATETIME in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_UNPARSEABLE_DATETIME)
        assert diag.ambiguity == AMBIGUITY_INVALID
        assert result.confidence == CONFIDENCE_UNKNOWN

    def test_mixed_format_reports_mixed_diagnostic_not_silently_normalized(self):
        result = detect_absolute_datetime(
            _rows(["2026-08-31 13:09:44", "31/08/2026 13:09:45", "2026-08-31 13:09:46"]),
            requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MIXED_DATETIME_FORMAT in codes


class TestSingleColumnTimeOnly:
    def test_pure_time_of_day_is_partial_not_absolute(self):
        result = detect_absolute_datetime(_rows(["13:09:44.305", "13:09:45.000"]), requested_options={})

        assert result.family == FAMILY_PARTIAL
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE)
        assert diag.ambiguity == AMBIGUITY_INVALID

    def test_midnight_rollover_is_not_inferred_for_time_only(self):
        # Section O's own explicit scope boundary: no rollover inference
        # for a bare time-of-day column in this slice -- Slice 8D adds a
        # DIAGNOSTIC for this pattern (see TestTimingIrregularities below)
        # but still never fabricates a date or promotes to absolute.
        result = detect_absolute_datetime(_rows(["23:59:59.900", "00:00:00.100"]), requested_options={})

        assert result.family == FAMILY_PARTIAL


# ---- CSV/Excel ingestion Slice 8D (DEC-072): shared timing-irregularity
# diagnostics for `absolute_datetime`/`split_date_time` -- backward time,
# midnight rollover (partial only), timestamp reset, large gaps, and
# non-uniform spacing. Detect-only: nothing here ever sorts, rewrites, or
# drops a row. Elapsed/sample-index/repeated-timestamp diagnostics are
# unchanged (already covered by their own existing test classes above/
# below) -- Slice 8D's job for those three is normalization/consolidation
# only, not new detection logic.


class TestTimingIrregularitiesBackward:
    def test_small_backward_step_is_generic_backward(self):
        # 13:14:01.500 -> .600 -> .400 -- a small backward jitter, NOT a
        # reset (its own magnitude is comparable to the +0.1s normal step).
        result = detect_absolute_datetime(
            _rows(["13:14:01.500", "13:14:01.600", "13:14:01.400"]), requested_options={},
        )

        assert result.family == FAMILY_PARTIAL
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_TIME_GOES_BACKWARD in codes
        assert DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED not in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_TIME_GOES_BACKWARD)
        assert diag.location.row_number == 3
        assert diag.ambiguity == AMBIGUITY_UNAMBIGUOUS
        assert diag.severity_hint == SEVERITY_WARNING

    def test_clear_reset_like_jump_is_reset_suspected_not_generic_backward(self):
        # 13:14:30 -> :31 -> 00:00:00 -> :01 -- a sharp drop to near the
        # start of the day, NOT near the end of the day (not a rollover).
        result = detect_absolute_datetime(
            _rows(["13:14:30", "13:14:31", "00:00:00", "00:00:01"]), requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED in codes
        assert DIAGNOSTIC_TIME_GOES_BACKWARD not in codes
        assert DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED not in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED)
        assert diag.location.row_number == 3

    def test_row_order_is_never_reordered_or_rewritten(self):
        original = ["13:14:01.500", "13:14:01.600", "13:14:01.400"]
        result = detect_absolute_datetime(_rows(original), requested_options={})
        # Nothing about detection ever touches the caller's own values --
        # this pure function has no output surface for that at all beyond
        # diagnostics; asserting the input list itself is untouched.
        assert original == ["13:14:01.500", "13:14:01.600", "13:14:01.400"]
        assert result.family == FAMILY_PARTIAL


class TestTimingIrregularitiesPartialMidnightRollover:
    def test_rollover_pattern_is_distinguished_from_generic_backward(self):
        result = detect_absolute_datetime(
            _rows(["23:59:59", "23:59:59", "00:00:00", "00:00:00"]), requested_options={},
        )

        assert result.family == FAMILY_PARTIAL
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED in codes
        assert DIAGNOSTIC_TIME_GOES_BACKWARD not in codes
        assert DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED not in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED)
        assert diag.location.row_number == 3
        assert "date" not in diag.suggested_action.lower() or "no date is invented" in diag.suggested_action.lower()

    def test_no_date_is_fabricated_family_stays_partial(self):
        result = detect_absolute_datetime(
            _rows(["23:59:59.900", "00:00:00.100"]), requested_options={},
        )

        assert result.family == FAMILY_PARTIAL
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_PARTIAL_MIDNIGHT_ROLLOVER_SUSPECTED in codes


class TestTimingIrregularitiesLargeGap:
    def test_uniform_cadence_then_large_jump_is_flagged(self):
        result = detect_absolute_datetime(
            _rows(["13:14:01", "13:14:02", "13:20:00"]), requested_options={},
        )

        assert result.family == FAMILY_PARTIAL
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_LARGE_TIME_GAP in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_LARGE_TIME_GAP)
        assert diag.location.row_number == 3

    def test_irregular_but_reasonable_timing_is_not_flagged_as_a_large_gap(self):
        # Deltas of 1.0s, 1.2s, 0.9s -- ordinary jitter, nowhere near the
        # 5x-of-the-smallest-delta threshold.
        result = detect_absolute_datetime(
            _rows(["13:14:01.0", "13:14:02.0", "13:14:03.2", "13:14:04.1"]), requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_LARGE_TIME_GAP not in codes

    def test_no_synthetic_repair_row_count_and_values_unchanged(self):
        samples = [(1, ("13:14:01",)), (2, ("13:14:02",)), (3, ("13:20:00",))]
        preview = build_absolute_datetime_preview(samples, resolved_options={"date_order": "auto"}, limit=10)

        # The gap is a DIAGNOSTIC only -- the preview never inserts,
        # deletes, or interpolates a row to "fill" it.
        assert len(preview) == 3
        assert [row[1] for row in preview] == [("13:14:01",), ("13:14:02",), ("13:20:00",)]


class TestTimingIrregularitiesNonUniformInterval:
    def test_non_uniform_spacing_flagged_without_large_gap(self):
        # 1.0s, then 1.3s, then 0.7s -- each individually within the
        # ordinary range but the overall spread is not tight (>20% of
        # the median), so this is the SOFTER non_uniform_interval finding.
        result = detect_absolute_datetime(
            _rows(["13:14:01.0", "13:14:02.0", "13:14:03.3", "13:14:04.0"]), requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_NON_UNIFORM_INTERVAL in codes
        assert DIAGNOSTIC_LARGE_TIME_GAP not in codes


class TestTimingIrregularitiesMissingTimestamp:
    def test_empty_cell_is_missing_timestamp_row_preserved(self):
        result = detect_absolute_datetime(
            _rows(["2026-08-31 13:09:44", "", "2026-08-31 13:09:46"]), requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_DATETIME_VALUE in codes
        # A missing row is never synthesized -- only 2 of the 3 rows
        # ever entered the sequence analysis, and nothing crashes.
        assert result.family == FAMILY_ABSOLUTE


class TestSingleColumnMissingValues:
    def test_missing_value_is_retained_as_a_diagnostic_not_dropped(self):
        result = detect_absolute_datetime(
            _rows(["2026-08-31 13:09:44", None, "2026-08-31 13:09:46"]), requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_DATETIME_VALUE in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_MISSING_DATETIME_VALUE)
        assert diag.details["missing_count"] == 1
        assert diag.details["sample_size"] == 3
        # The still-parseable rows are not penalized by the missing one.
        assert result.family == FAMILY_ABSOLUTE

    def test_all_values_missing_yields_unknown_confidence_no_crash(self):
        result = detect_absolute_datetime(_rows([None, "", None]), requested_options={})

        assert result.confidence == CONFIDENCE_UNKNOWN
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_DATETIME_VALUE in codes


class TestSplitDateTime:
    def test_valid_dmy_date_plus_time(self):
        # Chronologically ascending -- see TestSingleColumnSlashDashOrders'
        # own comment for why order matters now that Slice 8D checks it.
        dates = _rows(["30/08/2026", "31/08/2026"])
        times = _rows(["13:09:44.305", "13:09:45.505"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_NATIVE
        assert result.diagnostics == []
        assert result.resolved_options["date_order"] == "dmy"

    def test_valid_mdy_after_explicit_user_choice(self):
        # "01/02/2026" alone is ambiguous; the user's own explicit choice resolves it.
        dates = _rows(["01/02/2026", "03/04/2026"])
        times = _rows(["13:09:44", "13:09:45"])

        result = detect_split_date_time(dates, times, requested_options={"date_order": "mdy"})

        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.resolved_options["date_order"] == "mdy"

    def test_fractional_seconds_in_time_column(self):
        dates = _rows(["2026-08-31"])
        times = _rows(["13:09:44.305"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.diagnostics == []

    def test_missing_date_value_reported(self):
        dates = _rows([None, "31/08/2026"])
        times = _rows(["13:09:44", "13:09:45"])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_DATETIME_VALUE in codes

    def test_missing_time_value_reported(self):
        dates = _rows(["31/08/2026", "30/08/2026"])
        times = _rows(["13:09:44", None])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_DATETIME_VALUE in codes

    def test_invalid_time_combination_reports_diagnostic_not_a_crash(self):
        dates = _rows(["31/08/2026"])
        times = _rows(["not-a-time"])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_UNPARSEABLE_DATETIME in codes

    def test_multiple_time_axis_columns_are_the_date_and_time_columns(self):
        # column_indices order IS the (date, time) assignment for this
        # interpreter -- proven here at the pure-function level by
        # passing genuinely different values for each column.
        dates = _rows(["31/08/2026"])
        times = _rows(["08:00:00"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        assert result.diagnostics == []


class TestSplitDateTimeMinuteResolutionAndAmPmHour:
    """Enhancement (minute/AM-PM-hour absolute time support), task
    section E: split Date + Time must stay behaviorally aligned with
    the single-column interpreter -- both share the SAME _TIME_PATTERNS
    table, verified here directly (not just by code inspection)."""

    def test_dmy_unambiguous_minute_resolution_time_column(self):
        dates = _rows(["31/08/2026", "31/08/2026"])
        times = _rows(["17:25", "17:26"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        assert result.confidence == CONFIDENCE_HIGH
        assert result.diagnostics == []
        assert result.resolved_options["date_order"] == "dmy"

    def test_ambiguous_date_plus_minute_resolution_time_stays_review_required(self):
        # The reported bug's own split-column equivalent.
        dates = _rows(["3/6/2026", "3/6/2026"])
        times = _rows(["17:25", "17:26"])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER in codes
        assert result.resolved_options["date_order"] == "auto"

    def test_ambiguous_resolved_by_explicit_date_order(self):
        dates = _rows(["3/6/2026", "3/6/2026"])
        times = _rows(["17:25", "17:26"])

        result = detect_split_date_time(dates, times, requested_options={"date_order": "dmy"})

        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_options["date_order"] == "dmy"

    def test_explicit_am_pm_hour_only_time_column(self):
        dates = _rows(["2026-06-03", "2026-06-03"])
        times = _rows(["1pm", "2pm"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        assert result.diagnostics == []

    def test_bare_hour_only_time_column_still_unparseable(self):
        dates = _rows(["2026-06-03"])
        times = _rows(["17"])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_UNPARSEABLE_DATETIME in codes


class TestTwoDigitYear:
    """UAT fix: `3/6/26 + 18:04:00.000` (a real owner-reported source
    shape) previously fell all the way to `unparseable_datetime` --
    root cause was that `_DATE_PATTERNS_BY_ORDER` had NO 2-digit-year
    (`%y`) candidate patterns at all (only `%Y`, which `strptime`
    correctly refuses to match against a bare 2-digit token like "26").
    This was a missing-format-family gap, not an ambiguity-detection
    bug and not a split-date-time matching bug specifically -- both
    `dmy` and `mdy` genuinely had ZERO matching candidates before this
    fix, so the case never even reached the ambiguity-by-elimination
    logic. See `app.services.time_axis_interpreters`'s own module
    docstring for the exact 2-digit-year century rule this class
    verifies (00-69 -> 2000-2069, 70-99 -> 1970-1999)."""

    def test_owner_reported_shape_is_ambiguous_not_unparseable(self):
        dates = _rows(["3/6/26", "3/6/26", "3/6/26"])
        times = _rows(["18:04:00.000", "18:04:00.020", "18:04:00.040"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.family == FAMILY_ABSOLUTE
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER in codes
        assert DIAGNOSTIC_UNPARSEABLE_DATETIME not in codes
        ambiguous = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_AMBIGUOUS_DATE_ORDER)
        assert ambiguous.ambiguity == AMBIGUITY_AMBIGUOUS
        assert set(ambiguous.details["candidate_orders"]) == {"dmy", "mdy"}
        assert result.resolved_options["date_order"] == "auto"
        # UAT fix (task section G): specific, actionable wording --
        # never the generic "could not be parsed" message for a value
        # that IS viably interpretable, just not yet chosen between.
        assert "needs confirmation" in ambiguous.message
        assert '"3/6/26"' in ambiguous.message
        assert "Day/Month/Year" in ambiguous.message and "Month/Day/Year" in ambiguous.message

    def test_explicit_dmy_choice_resolves_to_june_third(self):
        from app.services.time_axis_interpreters import build_split_date_time_preview

        result = detect_split_date_time(
            _rows(["3/6/26"]), _rows(["18:04:00.000"]), requested_options={"date_order": "dmy"},
        )
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.resolved_options["date_order"] == "dmy"
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in result.diagnostics)

        preview = build_split_date_time_preview(
            [(1, ("3/6/26", "18:04:00.000"))], resolved_options=result.resolved_options, limit=10,
        )
        assert preview[0][2] == "2026-06-03T18:04:00"

    def test_explicit_mdy_choice_resolves_to_march_sixth(self):
        from app.services.time_axis_interpreters import build_split_date_time_preview

        result = detect_split_date_time(
            _rows(["3/6/26"]), _rows(["18:04:00.000"]), requested_options={"date_order": "mdy"},
        )
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.resolved_options["date_order"] == "mdy"

        preview = build_split_date_time_preview(
            [(1, ("3/6/26", "18:04:00.000"))], resolved_options=result.resolved_options, limit=10,
        )
        assert preview[0][2] == "2026-03-06T18:04:00"

    def test_day_over_twelve_is_unambiguous_dmy_only(self):
        result = detect_split_date_time(
            _rows(["13/6/26"]), _rows(["18:04:00.000"]), requested_options={},
        )

        assert result.provenance == PROVENANCE_NATIVE
        assert result.resolved_options["date_order"] == "dmy"
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in result.diagnostics)

    def test_dash_separated_two_digit_year_also_supported(self):
        result = detect_split_date_time(
            _rows(["13-6-26"]), _rows(["18:04:00.000"]), requested_options={},
        )

        assert result.resolved_options["date_order"] == "dmy"
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in result.diagnostics)

    def test_zero_padded_two_digit_year_supported(self):
        result = detect_split_date_time(
            _rows(["13/06/26"]), _rows(["18:04:00.000"]), requested_options={},
        )

        assert result.resolved_options["date_order"] == "dmy"

    def test_century_pivot_00_to_69_maps_to_2000s(self):
        from app.services.time_axis_interpreters import parse_absolute_datetime

        assert parse_absolute_datetime("1/1/00", date_order="dmy").year == 2000
        assert parse_absolute_datetime("1/1/69", date_order="dmy").year == 2069

    def test_century_pivot_70_to_99_maps_to_1900s(self):
        from app.services.time_axis_interpreters import parse_absolute_datetime

        assert parse_absolute_datetime("1/1/70", date_order="dmy").year == 1970
        assert parse_absolute_datetime("1/1/99", date_order="dmy").year == 1999

    def test_genuinely_malformed_value_remains_a_real_parsing_failure(self):
        result = detect_split_date_time(
            _rows(["not-a-date"]), _rows(["18:04:00.000"]), requested_options={},
        )

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_UNPARSEABLE_DATETIME in codes
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER not in codes
        # UAT fix (task section G/D.3): the genuine-failure wording
        # mentions "supported formats" (never "needs confirmation") and
        # carries concrete failing examples, not only a count.
        unparseable = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_UNPARSEABLE_DATETIME)
        assert "supported formats" in unparseable.message
        assert "needs confirmation" not in unparseable.message
        assert unparseable.details["examples"] == [{"row_number": 1, "value": "not-a-date"}]


class TestSplitDateTimeTimingIrregularities:
    """(Slice 8D) Timing-quality analysis runs over the COMBINED
    date+time value per row, never the date-only column's own value
    sequence (which is always midnight-anchored and not a meaningful
    timing signal by itself)."""

    def test_backward_combined_datetime_is_flagged(self):
        # Same calendar day both rows, but the TIME goes backward --
        # the date-only sequence alone (31/08 both times) would never
        # reveal this; only the combined value does.
        dates = _rows(["31/08/2026", "31/08/2026"])
        times = _rows(["13:09:46", "13:09:44"])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_TIME_GOES_BACKWARD in codes

    def test_date_only_backward_pattern_alone_is_not_double_reported(self):
        # 31/08 then 30/08 (day decreasing) but the TIME moves forward
        # enough to make the COMBINED datetime also move backward -- this
        # must produce exactly ONE time_goes_backward/reset finding from
        # the combined analysis, never a second one from the date-only
        # column's own (unrelated) sequence.
        dates = _rows(["31/08/2026", "30/08/2026"])
        times = _rows(["13:09:44.305", "13:09:45.505"])

        result = detect_split_date_time(dates, times, requested_options={})

        backward_like_codes = [
            d.code for d in result.diagnostics
            if d.code in (DIAGNOSTIC_TIME_GOES_BACKWARD, DIAGNOSTIC_TIMESTAMP_RESET_SUSPECTED)
        ]
        assert len(backward_like_codes) == 1

    def test_large_gap_in_combined_datetime_is_flagged(self):
        dates = _rows(["31/08/2026", "31/08/2026", "31/08/2026"])
        times = _rows(["13:14:01", "13:14:02", "13:20:00"])

        result = detect_split_date_time(dates, times, requested_options={})

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_LARGE_TIME_GAP in codes

    def test_well_behaved_split_date_time_has_no_timing_diagnostics(self):
        dates = _rows(["31/08/2026", "31/08/2026", "31/08/2026"])
        times = _rows(["13:14:01", "13:14:02", "13:14:03"])

        result = detect_split_date_time(dates, times, requested_options={})

        assert result.diagnostics == []


class TestPreviewBuilders:
    def test_absolute_datetime_preview_rows_are_bounded(self):
        samples = [(i, (f"2026-08-31 13:09:{i:02d}",)) for i in range(1, 31)]

        preview = build_absolute_datetime_preview(samples, resolved_options={"date_order": "ymd"}, limit=20)

        assert len(preview) == 20

    def test_absolute_datetime_preview_row_shape(self):
        samples = [(1, ("2026-08-31 13:09:44.305",)), (2, (None,)), (3, ("garbage",))]

        preview = build_absolute_datetime_preview(samples, resolved_options={"date_order": "ymd"}, limit=10)

        assert preview[0] == (1, ("2026-08-31 13:09:44.305",), "2026-08-31T13:09:44.305000")
        assert preview[1] == (2, (None,), None)
        assert preview[2][2] is None  # unparseable row keeps original, interpreted=None

    def test_split_date_time_preview_row_shape(self):
        samples = [(1, ("31/08/2026", "13:09:44.305")), (2, ("30/08/2026", None))]

        preview = build_split_date_time_preview(samples, resolved_options={"date_order": "dmy"}, limit=10)

        assert preview[0][2] == "2026-08-31T13:09:44.305000"
        assert preview[1][2] is None
        assert preview[1][1] == ("30/08/2026", None)  # original preserved even on failure


# ---- CSV/Excel ingestion Slice 8B (DEC-072): elapsed numeric time + sample index ----


def _rows(values):
    return list(enumerate(values, start=1))


class TestElapsedNumericMissingUnit:
    def test_no_unit_is_ambiguous_review_required(self):
        result = detect_elapsed_numeric(_rows(["0", "0.001", "0.002"]), requested_unit=None)

        assert result.family == FAMILY_ELAPSED
        assert result.confidence == CONFIDENCE_UNKNOWN
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_ELAPSED_UNIT in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_MISSING_ELAPSED_UNIT)
        assert diag.ambiguity == AMBIGUITY_AMBIGUOUS
        assert result.resolved_unit is None

    def test_no_unit_does_not_compute_other_diagnostics(self):
        # Nothing safe to say about backward/repeated/non-uniform before
        # the unit itself is known -- see detect_elapsed_numeric's own
        # docstring.
        result = detect_elapsed_numeric(_rows(["5", "1", "1", "9"]), requested_unit=None)

        codes = [d.code for d in result.diagnostics]
        assert codes == [DIAGNOSTIC_MISSING_ELAPSED_UNIT]


class TestElapsedNumericUnits:
    def test_seconds(self):
        result = detect_elapsed_numeric(_rows(["0", "1", "2", "3"]), requested_unit="seconds")

        assert result.family == FAMILY_ELAPSED
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.resolved_unit == "seconds"
        assert result.diagnostics == []

    def test_milliseconds(self):
        result = detect_elapsed_numeric(_rows(["0", "10", "20", "30"]), requested_unit="milliseconds")

        assert result.resolved_unit == "milliseconds"
        assert result.diagnostics == []

    def test_microseconds(self):
        result = detect_elapsed_numeric(_rows(["0", "1000", "2000"]), requested_unit="microseconds")

        assert result.resolved_unit == "microseconds"
        assert result.diagnostics == []

    def test_nanoseconds(self):
        result = detect_elapsed_numeric(_rows(["0", "1000000", "2000000"]), requested_unit="nanoseconds")

        assert result.resolved_unit == "nanoseconds"
        assert result.diagnostics == []

    def test_negative_values_are_accepted_as_numeric(self):
        result = detect_elapsed_numeric(_rows(["-2", "-1", "0", "1"]), requested_unit="seconds")

        assert result.diagnostics == []
        assert result.family == FAMILY_ELAPSED

    # Enhancement (fixed-duration elapsed units): minutes/hours/days/weeks.
    def test_minutes(self):
        result = detect_elapsed_numeric(_rows(["0", "1", "2", "3"]), requested_unit="minutes")

        assert result.resolved_unit == "minutes"
        assert result.diagnostics == []

    def test_hours(self):
        result = detect_elapsed_numeric(_rows(["0", "1", "2"]), requested_unit="hours")

        assert result.resolved_unit == "hours"
        assert result.diagnostics == []

    def test_days(self):
        result = detect_elapsed_numeric(_rows(["0", "1", "2"]), requested_unit="days")

        assert result.resolved_unit == "days"
        assert result.diagnostics == []

    def test_weeks(self):
        result = detect_elapsed_numeric(_rows(["0", "1", "2"]), requested_unit="weeks")

        assert result.resolved_unit == "weeks"
        assert result.diagnostics == []

    def test_fractional_minutes_hours_days_weeks_accepted(self):
        for unit in ("minutes", "hours", "days", "weeks"):
            result = detect_elapsed_numeric(_rows(["0", "0.5", "1.0"]), requested_unit=unit)
            assert result.diagnostics == []
            assert result.resolved_unit == unit


class TestElapsedNumericDataQuality:
    def test_missing_value_retained_as_diagnostic(self):
        result = detect_elapsed_numeric(_rows(["0", None, "2"]), requested_unit="seconds")

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_ELAPSED_VALUE in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_MISSING_ELAPSED_VALUE)
        assert diag.details == {"missing_count": 1, "sample_size": 3}

    def test_non_numeric_value(self):
        result = detect_elapsed_numeric(_rows(["0", "abc", "2"]), requested_unit="seconds")

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE in codes
        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE)
        assert diag.ambiguity == AMBIGUITY_INVALID

    def test_repeated_elapsed_value(self):
        result = detect_elapsed_numeric(_rows(["0", "1", "1", "2"]), requested_unit="seconds")

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_REPEATED_ELAPSED_TIME in codes

    def test_backward_elapsed_value(self):
        result = detect_elapsed_numeric(_rows(["0", "2", "1", "3"]), requested_unit="seconds")

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD in codes

    def test_non_uniform_interval(self):
        result = detect_elapsed_numeric(_rows(["0.000", "0.001", "0.0025", "0.004"]), requested_unit="seconds")

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL in codes

    def test_uniform_interval_has_no_non_uniform_diagnostic(self):
        result = detect_elapsed_numeric(_rows(["0.000", "0.001", "0.002", "0.003"]), requested_unit="seconds")

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL not in codes

    def test_diagnostics_never_reorder_or_drop(self):
        # This is a detection-only function -- it never returns rows,
        # only diagnostics -- proven here by confirming a backward +
        # repeated + missing combination all surface simultaneously
        # without raising or dropping information.
        result = detect_elapsed_numeric(_rows(["0", None, "2", "1", "1"]), requested_unit="seconds")

        codes = {d.code for d in result.diagnostics}
        assert DIAGNOSTIC_MISSING_ELAPSED_VALUE in codes
        assert DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD in codes
        assert DIAGNOSTIC_REPEATED_ELAPSED_TIME in codes


class TestElapsedPreview:
    def test_seconds_conversion(self):
        samples = [(1, ("0",)), (2, ("10",)), (3, ("20",))]

        preview = build_elapsed_preview(samples, resolved_unit="milliseconds", limit=10)

        assert preview[0] == (1, ("0",), "0.000000 s")
        assert preview[1] == (2, ("10",), "0.010000 s")
        assert preview[2] == (3, ("20",), "0.020000 s")

    def test_no_unit_never_fabricates_seconds(self):
        samples = [(1, ("0",)), (2, ("10",))]

        preview = build_elapsed_preview(samples, resolved_unit=None, limit=10)

        assert all(interpreted is None for _, _, interpreted in preview)

    def test_non_numeric_row_is_none_not_dropped(self):
        samples = [(1, ("0",)), (2, ("garbage",)), (3, ("20",))]

        preview = build_elapsed_preview(samples, resolved_unit="seconds", limit=10)

        assert len(preview) == 3
        assert preview[1] == (2, ("garbage",), None)

    # Enhancement (fixed-duration elapsed units), task section M: exact
    # deterministic seconds factors -- worked examples straight from the
    # task's own spec.
    def test_minutes_conversion(self):
        samples = [(1, ("0",)), (2, ("1",)), (3, ("2",)), (4, ("3",))]

        preview = build_elapsed_preview(samples, resolved_unit="minutes", limit=10)

        assert [p[2] for p in preview] == ["0.000000 s", "60.000000 s", "120.000000 s", "180.000000 s"]

    def test_hours_conversion_with_fraction(self):
        samples = [(1, ("5.0",)), (2, ("5.5",)), (3, ("6.0",))]

        preview = build_elapsed_preview(samples, resolved_unit="hours", limit=10)

        # Normalized to canonical seconds -- anchor semantics (relative
        # to the first active row) are applied elsewhere, not by this
        # preview builder itself, which reports each row's own absolute
        # seconds-from-zero conversion.
        assert [p[2] for p in preview] == ["18000.000000 s", "19800.000000 s", "21600.000000 s"]

    def test_days_conversion(self):
        samples = [(1, ("0",)), (2, ("2",))]

        preview = build_elapsed_preview(samples, resolved_unit="days", limit=10)

        assert preview[1] == (2, ("2",), "172800.000000 s")

    def test_weeks_conversion_with_fraction(self):
        samples = [(1, ("0",)), (2, ("0.5",))]

        preview = build_elapsed_preview(samples, resolved_unit="weeks", limit=10)

        assert preview[1] == (2, ("0.5",), "302400.000000 s")


class TestSampleIndexStartingValues:
    def test_starts_at_zero(self):
        result = detect_sample_index(_rows(["0", "1", "2", "3"]), requested_interval_seconds=None)

        assert result.family == FAMILY_SAMPLE_INDEX
        assert result.diagnostics == []

    def test_starts_at_one(self):
        result = detect_sample_index(_rows(["1", "2", "3", "4"]), requested_interval_seconds=None)

        assert result.diagnostics == []

    def test_starts_at_arbitrary_value(self):
        result = detect_sample_index(_rows(["1001", "1002", "1003"]), requested_interval_seconds=None)

        assert result.diagnostics == []


class TestSampleIndexTiming:
    def test_unknown_rate_is_index_only_not_an_error(self):
        result = detect_sample_index(_rows(["1", "2", "3"]), requested_interval_seconds=None)

        assert result.family == FAMILY_SAMPLE_INDEX
        assert result.provenance == PROVENANCE_INDEX_ONLY
        assert result.confidence == CONFIDENCE_UNKNOWN
        assert result.diagnostics == []  # not an error -- the approved fallback
        assert result.resolved_interval_seconds is None

    def test_known_sampling_interval(self):
        result = detect_sample_index(_rows(["1001", "1002", "1003"]), requested_interval_seconds=0.0002)

        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_interval_seconds == 0.0002

    def test_known_sampling_rate_converted_to_interval_by_caller(self):
        # 5000 Hz -> 1/5000 s per sample; the CALLER is responsible for
        # this conversion (never a second stored representation) -- this
        # test proves the interpreter accepts the resulting canonical
        # value transparently.
        rate_hz = 5000
        result = detect_sample_index(_rows(["1", "2", "3"]), requested_interval_seconds=1 / rate_hz)

        assert result.resolved_interval_seconds == 1 / rate_hz
        assert result.provenance == PROVENANCE_USER_SPECIFIED


class TestSampleIndexDataQuality:
    def test_repeated_index(self):
        result = detect_sample_index(_rows(["1", "2", "2", "3"]), requested_interval_seconds=None)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_REPEATED_SAMPLE_INDEX in codes

    def test_backward_index(self):
        result = detect_sample_index(_rows(["1", "3", "2", "4"]), requested_interval_seconds=None)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD in codes

    def test_gap(self):
        result = detect_sample_index(_rows(["1", "2", "3", "5", "6"]), requested_interval_seconds=None)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_SAMPLE_INDEX_GAP in codes

    def test_no_gap_for_consecutive_sequence(self):
        result = detect_sample_index(_rows(["1", "2", "3", "4"]), requested_interval_seconds=None)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_SAMPLE_INDEX_GAP not in codes

    def test_non_numeric_value(self):
        result = detect_sample_index(_rows(["1", "abc", "3"]), requested_interval_seconds=None)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX in codes

    def test_missing_value(self):
        result = detect_sample_index(_rows(["1", None, "3"]), requested_interval_seconds=None)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_SAMPLE_INDEX in codes

    def test_repeated_index_rows_never_collapsed(self):
        # This is a detection-only function -- proving it reports rather
        # than removes: the diagnostic exists, but nothing here ever
        # returns a shorter row list (this function returns no rows at
        # all, only diagnostics -- collapsing would have to happen
        # elsewhere, and nothing elsewhere in this module does it).
        result = detect_sample_index(_rows(["1", "2", "2", "2", "3"]), requested_interval_seconds=None)

        diag = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_REPEATED_SAMPLE_INDEX)
        assert diag.details["repeated_count"] == 2


class TestSampleIndexPreview:
    def test_no_rate_never_fabricates_seconds(self):
        samples = [(1, ("1001",)), (2, ("1002",)), (3, ("1003",))]

        preview = build_sample_index_preview(samples, resolved_interval_seconds=None, limit=10)

        assert all(interpreted is None for _, _, interpreted in preview)

    def test_known_rate_relative_to_first_valid_sample_value(self):
        samples = [(1, ("1001",)), (2, ("1002",)), (3, ("1003",))]

        preview = build_sample_index_preview(samples, resolved_interval_seconds=0.0002, limit=10)

        assert preview[0] == (1, ("1001",), "0.000000 s")
        assert preview[1] == (2, ("1002",), "0.000200 s")
        assert preview[2] == (3, ("1003",), "0.000400 s")

    def test_first_valid_value_skips_a_leading_missing_row(self):
        # First valid index is 1002 (row 1 is missing) -- relative
        # seconds are computed from THAT reference, never assumed 0.
        samples = [(1, (None,)), (2, ("1002",)), (3, ("1003",))]

        preview = build_sample_index_preview(samples, resolved_interval_seconds=0.0002, limit=10)

        assert preview[0] == (1, (None,), None)
        assert preview[1] == (2, ("1002",), "0.000000 s")
        assert preview[2] == (3, ("1003",), "0.000200 s")

    def test_non_numeric_row_is_none_not_dropped(self):
        samples = [(1, ("1001",)), (2, ("garbage",)), (3, ("1003",))]

        preview = build_sample_index_preview(samples, resolved_interval_seconds=0.0002, limit=10)

        assert len(preview) == 3
        assert preview[1] == (2, ("garbage",), None)


# ---- CSV/Excel ingestion Slice 8C (DEC-072): repeated timestamp / precision-loss reconstruction ----


def _repeat(value: str, count: int) -> list[str]:
    return [value] * count


def _detect(values, requested_interval_seconds=None, options=None):
    return detect_repeated_timestamp_precision_loss(
        _rows(values), requested_interval_seconds=requested_interval_seconds, requested_options=options or {},
    )


class TestRepeatedTimestampDetectionStableCadence:
    def test_stable_5_rows_per_second(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values)

        assert result.family == FAMILY_PARTIAL
        assert result.provenance == PROVENANCE_RECONSTRUCTED
        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_interval_seconds == pytest.approx(0.2)

    def test_stable_10_rows_per_second_with_few_buckets_is_medium(self):
        # Only 3 buckets total (1 interior) -- perfectly stable, but
        # limited evidence, per §F's own "small sample size" factor.
        values = _repeat("13:14:01", 10) + _repeat("13:14:02", 10) + _repeat("13:14:03", 10)

        result = _detect(values)

        assert result.confidence == CONFIDENCE_MEDIUM
        assert result.resolved_interval_seconds == pytest.approx(0.1)

    def test_stable_10_rows_per_second_with_enough_interior_buckets_is_high(self):
        values = (
            _repeat("13:14:01", 10) + _repeat("13:14:02", 10) + _repeat("13:14:03", 10)
            + _repeat("13:14:04", 10) + _repeat("13:14:05", 10)
        )

        result = _detect(values)

        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_interval_seconds == pytest.approx(0.1)


class TestRepeatedTimestampPartialBuckets:
    def test_partial_first_bucket_does_not_reduce_confidence(self):
        # First bucket truncated (2 rows instead of the "true" 5) --
        # interior buckets (all 5) are still perfectly stable -> HIGH.
        values = _repeat("13:14:00", 2) + _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5)

        result = _detect(values)

        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_interval_seconds == pytest.approx(0.2)

    def test_partial_last_bucket_does_not_reduce_confidence(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 3)

        result = _detect(values)

        assert result.confidence == CONFIDENCE_HIGH

    def test_partial_first_and_last_buckets_both_present(self):
        values = (
            _repeat("13:14:00", 2) + _repeat("13:14:01", 5) + _repeat("13:14:02", 5)
            + _repeat("13:14:03", 5) + _repeat("13:14:04", 3)
        )

        result = _detect(values)

        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_interval_seconds == pytest.approx(0.2)


class TestRepeatedTimestampInconsistentCadence:
    def test_inconsistent_bucket_counts_is_low_confidence(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 2) + _repeat("13:14:03", 8) + _repeat("13:14:04", 4)

        result = _detect(values)

        assert result.confidence == CONFIDENCE_LOW
        assert result.resolved_interval_seconds is None
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_CADENCE_NOT_RELIABLE in codes
        assert DIAGNOSTIC_INCONSISTENT_BUCKET_COUNT in codes

    def test_too_few_buckets_is_low_confidence(self):
        # A single bucket -- no transition to measure a span from at all.
        result = _detect(_repeat("13:14:01", 5))

        assert result.confidence == CONFIDENCE_LOW
        assert result.resolved_interval_seconds is None


class TestRepeatedTimestampFractionalPrecision:
    def test_repeated_fractional_timestamp_precision(self):
        # Two EQUAL-sized buckets -- limited evidence (no interior
        # bucket at all) but perfectly consistent across what exists ->
        # MEDIUM per §F's own "small sample size" factor.
        values = _repeat("13:14:01.20", 3) + _repeat("13:14:01.30", 3)

        result = _detect(values)

        assert result.family == FAMILY_PARTIAL
        assert result.confidence == CONFIDENCE_MEDIUM
        assert result.resolved_interval_seconds is not None

    def test_repeated_fractional_timestamp_with_differing_bucket_sizes_is_low(self):
        # Different bucket sizes with no interior evidence either way --
        # genuinely too little to trust.
        values = _repeat("13:14:01.20", 3) + _repeat("13:14:01.30", 1)

        result = _detect(values)

        assert result.family == FAMILY_PARTIAL
        assert result.confidence == CONFIDENCE_LOW
        assert result.resolved_interval_seconds is None


class TestRepeatedTimestampAbsoluteSource:
    def test_absolute_datetime_source(self):
        values = (
            _repeat("2026-09-02 13:14:01", 5) + _repeat("2026-09-02 13:14:02", 5)
            + _repeat("2026-09-02 13:14:03", 5) + _repeat("2026-09-02 13:14:04", 5)
        )

        result = _detect(values)

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_RECONSTRUCTED
        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_options["date_order"] == "ymd"

    def test_ambiguous_date_order_among_bucket_values(self):
        values = _repeat("01/02/2026 13:14:01", 5) + _repeat("03/04/2026 13:14:02", 5) + _repeat("05/06/2026 13:14:03", 5)

        result = _detect(values)

        assert result.family == FAMILY_ABSOLUTE
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER in codes
        assert result.resolved_interval_seconds is None

    def test_ambiguous_date_order_resolved_by_explicit_choice(self):
        values = _repeat("01/02/2026 13:14:01", 5) + _repeat("03/04/2026 13:14:02", 5) + _repeat("05/06/2026 13:14:03", 5)

        result = _detect(values, options={"date_order": "dmy"})

        assert result.family == FAMILY_ABSOLUTE
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER not in codes


class TestRepeatedTimestampPartialSource:
    def test_partial_family_preserved_never_promoted_to_absolute(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values)

        assert result.family == FAMILY_PARTIAL


class TestRepeatedTimestampReconstruction:
    def test_5_hz_gives_200ms_interval(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values)

        assert result.resolved_interval_seconds == pytest.approx(0.2)

    def test_10_hz_gives_100ms_interval(self):
        values = (
            _repeat("13:14:01", 10) + _repeat("13:14:02", 10) + _repeat("13:14:03", 10)
            + _repeat("13:14:04", 10) + _repeat("13:14:05", 10)
        )

        result = _detect(values)

        assert result.resolved_interval_seconds == pytest.approx(0.1)

    def test_default_anchor_is_zero_offset(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values)

        assert result.resolved_options["anchor_offset_seconds"] == 0.0

    def test_custom_anchor_offset(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values, options={"anchor_offset_seconds": 0.1})

        assert result.resolved_options["anchor_offset_seconds"] == 0.1

    def test_anchor_assumption_diagnostic_always_disclosed(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED in codes

    def test_user_manual_interval_overrides_inference(self):
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 2) + _repeat("13:14:03", 8) + _repeat("13:14:04", 4)

        result = _detect(values, requested_interval_seconds=0.25)

        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.confidence == CONFIDENCE_HIGH
        assert result.resolved_interval_seconds == 0.25

    def test_user_manual_sampling_rate_converted_by_caller(self):
        # 4 Hz -> 0.25 s/sample; caller is responsible for the Hz->seconds
        # conversion (never a second stored representation).
        values = _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5)

        result = _detect(values, requested_interval_seconds=1 / 4)

        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.resolved_interval_seconds == pytest.approx(0.25)


class TestRepeatedTimestampPreservation:
    def test_detection_never_returns_rows_only_diagnostics(self):
        # This module is detection-only -- it has no mechanism to drop,
        # reorder, or collapse a row; proven structurally by the return
        # type carrying no row list at all, only counts/diagnostics.
        result = _detect(_repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5) + _repeat("13:14:04", 5))

        assert not hasattr(result, "rows")

    def test_missing_value_reported_not_silently_skipped(self):
        values = ["13:14:01", None, "13:14:01", "13:14:02", "13:14:02"]

        result = _detect(values)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_MISSING_DATETIME_VALUE in codes


class TestRepeatedTimestampMissingExtraSample:
    def test_possible_missing_sample_diagnostic(self):
        values = (
            _repeat("13:14:01", 5) + _repeat("13:14:02", 4) + _repeat("13:14:03", 5)
            + _repeat("13:14:04", 5) + _repeat("13:14:05", 5)
        )

        result = _detect(values)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE in codes
        assert result.resolved_interval_seconds is not None

    def test_unexpected_extra_sample_diagnostic(self):
        values = (
            _repeat("13:14:01", 5) + _repeat("13:14:02", 6) + _repeat("13:14:03", 5)
            + _repeat("13:14:04", 5) + _repeat("13:14:05", 5)
        )

        result = _detect(values)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT in codes

    def test_no_missing_or_extra_diagnostic_when_perfectly_stable(self):
        values = (
            _repeat("13:14:01", 5) + _repeat("13:14:02", 5) + _repeat("13:14:03", 5)
            + _repeat("13:14:04", 5) + _repeat("13:14:05", 5)
        )

        result = _detect(values)

        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_POSSIBLE_MISSING_SAMPLE not in codes
        assert DIAGNOSTIC_UNEXPECTED_BUCKET_SAMPLE_COUNT not in codes


class TestRepeatedTimestampNoRepetition:
    def test_no_repeats_is_clean_pass_through(self):
        result = _detect(["13:14:01", "13:14:02", "13:14:03"])

        assert result.family == FAMILY_PARTIAL
        assert result.provenance == PROVENANCE_NATIVE
        assert result.diagnostics == []
        assert result.resolved_interval_seconds is None


class TestRepeatedTimestampPreviewBuilder:
    def test_bounded_preview_preserves_row_order_and_bucket_spacing(self):
        samples = [
            (i, (v,)) for i, v in enumerate(
                _repeat("13:14:01", 5) + _repeat("13:14:02", 5), start=1,
            )
        ]

        preview = build_repeated_timestamp_preview(
            samples, resolved_options={"anchor_offset_seconds": 0.0}, resolved_interval_seconds=0.2, limit=20,
        )

        assert [r[0] for r in preview] == list(range(1, 11))  # row order preserved
        assert preview[0] == (1, ("13:14:01",), "13:14:01.000000")
        assert preview[1][2] == "13:14:01.200000"
        assert preview[4][2] == "13:14:01.800000"
        assert preview[5][2] == "13:14:02.000000"

    def test_preview_never_mutates_original_tuple(self):
        samples = [(1, ("13:14:01",)), (2, ("13:14:01",))]

        preview = build_repeated_timestamp_preview(
            samples, resolved_options={}, resolved_interval_seconds=0.2, limit=10,
        )

        assert preview[0][1] == ("13:14:01",)
        assert preview[1][1] == ("13:14:01",)

    def test_custom_anchor_offset_shifts_preview(self):
        samples = [(i, (v,)) for i, v in enumerate(_repeat("13:14:01", 3), start=1)]

        preview = build_repeated_timestamp_preview(
            samples, resolved_options={"anchor_offset_seconds": 0.1}, resolved_interval_seconds=0.2, limit=10,
        )

        assert preview[0][2] == "13:14:01.100000"
        assert preview[1][2] == "13:14:01.300000"

    def test_no_interval_never_fabricates_preview_values(self):
        samples = [(i, (v,)) for i, v in enumerate(_repeat("13:14:01", 3), start=1)]

        preview = build_repeated_timestamp_preview(
            samples, resolved_options={}, resolved_interval_seconds=None, limit=10,
        )

        assert all(interpreted is None for _, _, interpreted in preview)

    def test_bounded_preview_respects_limit(self):
        samples = [(i, (v,)) for i, v in enumerate(_repeat("13:14:01", 30), start=1)]

        preview = build_repeated_timestamp_preview(
            samples, resolved_options={}, resolved_interval_seconds=0.03, limit=20,
        )

        assert len(preview) == 20

    def test_absolute_family_preview_isoformat(self):
        samples = [
            (i, (v,)) for i, v in enumerate(
                _repeat("2026-09-02 13:14:01", 2) + _repeat("2026-09-02 13:14:02", 2), start=1,
            )
        ]

        preview = build_repeated_timestamp_preview(
            samples, resolved_options={"anchor_offset_seconds": 0.0, "date_order": "ymd"},
            resolved_interval_seconds=0.5, limit=10,
        )

        assert preview[0][2] == "2026-09-02T13:14:01"
        assert preview[1][2] == "2026-09-02T13:14:01.500000"
