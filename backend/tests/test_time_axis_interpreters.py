"""Unit tests for the deterministic absolute-time (Slice 8A) and
elapsed-time/sample-index (Slice 8B) parsing/detection functions
(CSV/Excel ingestion, DEC-072). Pure functions only -- no session, no
registry, no HTTP; service-layer wiring is covered by
tests/test_time_axis_service.py's own new test classes.
"""

from __future__ import annotations

from app.domain.time_axis import (
    AMBIGUITY_AMBIGUOUS,
    AMBIGUITY_INVALID,
    AMBIGUITY_UNAMBIGUOUS,
    CONFIDENCE_HIGH,
    CONFIDENCE_UNKNOWN,
    DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
    DIAGNOSTIC_ELAPSED_TIME_GOES_BACKWARD,
    DIAGNOSTIC_MISSING_DATETIME_VALUE,
    DIAGNOSTIC_MISSING_ELAPSED_UNIT,
    DIAGNOSTIC_MISSING_ELAPSED_VALUE,
    DIAGNOSTIC_MISSING_SAMPLE_INDEX,
    DIAGNOSTIC_MIXED_DATETIME_FORMAT,
    DIAGNOSTIC_NON_NUMERIC_ELAPSED_VALUE,
    DIAGNOSTIC_NON_NUMERIC_SAMPLE_INDEX,
    DIAGNOSTIC_NON_UNIFORM_ELAPSED_INTERVAL,
    DIAGNOSTIC_REPEATED_ELAPSED_TIME,
    DIAGNOSTIC_REPEATED_SAMPLE_INDEX,
    DIAGNOSTIC_SAMPLE_INDEX_GAP,
    DIAGNOSTIC_SAMPLE_INDEX_GOES_BACKWARD,
    DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE,
    DIAGNOSTIC_UNPARSEABLE_DATETIME,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    PROVENANCE_USER_SPECIFIED,
)
from app.services.time_axis_interpreters import (
    build_absolute_datetime_preview,
    build_elapsed_preview,
    build_sample_index_preview,
    build_split_date_time_preview,
    detect_absolute_datetime,
    detect_elapsed_numeric,
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
        result = detect_absolute_datetime(
            _rows(["31/08/2026 13:09:44.305", "30/08/2026 13:09:45.505"]), requested_options={},
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
        result = detect_absolute_datetime(
            _rows(["08/31/2026 1:09:44 PM", "08/30/2026 2:15:00 AM"]), requested_options={},
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
        # for a bare time-of-day column in this slice.
        result = detect_absolute_datetime(_rows(["23:59:59.900", "00:00:00.100"]), requested_options={})

        assert result.family == FAMILY_PARTIAL


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
        dates = _rows(["31/08/2026", "30/08/2026"])
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
