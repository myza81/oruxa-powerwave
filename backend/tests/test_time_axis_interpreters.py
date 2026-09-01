"""Unit tests for the deterministic absolute-time parsing/detection
functions (CSV/Excel ingestion Slice 8A, DEC-072). Pure functions only
-- no session, no registry, no HTTP; service-layer wiring is covered by
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
    DIAGNOSTIC_MISSING_DATETIME_VALUE,
    DIAGNOSTIC_MIXED_DATETIME_FORMAT,
    DIAGNOSTIC_TIME_ONLY_NOT_ABSOLUTE,
    DIAGNOSTIC_UNPARSEABLE_DATETIME,
    FAMILY_ABSOLUTE,
    FAMILY_PARTIAL,
    PROVENANCE_NATIVE,
    PROVENANCE_USER_SPECIFIED,
)
from app.services.time_axis_interpreters import (
    build_absolute_datetime_preview,
    build_split_date_time_preview,
    detect_absolute_datetime,
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
