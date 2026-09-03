"""Pure domain tests for app.domain.time_grouping -- timestamp-based
initial alignment and Time Group derivation. Synthetic tuples only (see
that module's own docstring for why `derive_time_groups()` takes plain
tuples rather than `SourceMetadata`); test_time_grouping_service.py
covers the ActiveSource/registry-aware layer built on top of this one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.time_grouping import (
    NON_OVERLAPPING_NOTE,
    TIME_REFERENCE_ELAPSED_ONLY,
    TIME_REFERENCE_RECORDED_ABSOLUTE,
    derive_time_groups,
    time_reference_type_for_source,
    timestamp_placement_offset_s,
)

T0 = datetime(2026, 3, 6, 13, 9, 44, 0)


def _abs_source(source_id: str, *, start: datetime, elapsed_start: float = 0.0, elapsed_end: float = 2.0):
    return (source_id, "absolute", start, elapsed_start, elapsed_end)


def _elapsed_source(source_id: str, *, elapsed_start: float = 0.0, elapsed_end: float = 2.0):
    return (source_id, "relative_elapsed", None, elapsed_start, elapsed_end)


class TestTimeReferenceType:
    def test_absolute_literal_is_recorded_absolute(self):
        assert time_reference_type_for_source("absolute") == TIME_REFERENCE_RECORDED_ABSOLUTE

    def test_anything_else_is_elapsed_only(self):
        assert time_reference_type_for_source("relative_elapsed") == TIME_REFERENCE_ELAPSED_ONLY
        assert time_reference_type_for_source("") == TIME_REFERENCE_ELAPSED_ONLY
        assert time_reference_type_for_source("something_else") == TIME_REFERENCE_ELAPSED_ONLY


class TestAbsoluteTimestampPlacement:
    """Task section 38's own worked example: A start=13:09:44.000,
    B start=13:09:44.401 -> A placement=0, B placement=+0.401s."""

    def test_placement_matches_worked_example(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0),
            _abs_source("B", start=T0 + timedelta(milliseconds=401)),
        ])
        assert len(groups) == 1
        group = groups[0]
        assert group.origin_source_id == "A"
        assert group.source_ids == ["A", "B"]

        placement_a = timestamp_placement_offset_s(source_start_time=T0, origin_start_time=T0)
        placement_b = timestamp_placement_offset_s(source_start_time=T0 + timedelta(milliseconds=401), origin_start_time=T0)
        assert placement_a == pytest.approx(0.0)
        assert placement_b == pytest.approx(0.401, abs=1e-9)

    def test_sub_millisecond_precision_is_preserved(self):
        precise = T0 + timedelta(microseconds=401123)
        placement = timestamp_placement_offset_s(source_start_time=precise, origin_start_time=T0)
        assert placement == pytest.approx(0.401123, abs=1e-9)


class TestOverlappingIntervals:
    def test_overlapping_absolute_sources_share_one_group(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0, elapsed_start=0.0, elapsed_end=1.0),
            _abs_source("B", start=T0 + timedelta(milliseconds=800), elapsed_start=0.0, elapsed_end=0.8),
        ])
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"A", "B"}
        assert groups[0].note is None


class TestLargeNonOverlappingGap:
    """Task section 11/38: A=13:09:44, B=13:29:00.401 -> separate
    groups, flagged, never one giant panel."""

    def test_large_gap_creates_separate_groups_with_a_note(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0, elapsed_start=0.0, elapsed_end=1.0),
            _abs_source("B", start=T0 + timedelta(minutes=19, milliseconds=401), elapsed_start=0.0, elapsed_end=1.0),
        ])
        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert group_ids == {"A", "B"}
        for g in groups:
            assert g.note == NON_OVERLAPPING_NOTE

    def test_single_absolute_upload_with_nothing_to_overlap_gets_no_note(self):
        """A workspace with only ONE absolute source has nothing to
        compare against -- this is an ordinary case, not a flagged one."""
        groups = derive_time_groups([_abs_source("A", start=T0)])
        assert len(groups) == 1
        assert groups[0].note is None


class TestLongRecordOverlap:
    """Task section 12/38: large start-time difference, but the
    intervals genuinely overlap (e.g. two 10-minute records 5 minutes
    apart) -> same group, never split merely because start times differ
    a lot."""

    def test_large_start_offset_with_real_overlap_still_groups(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0, elapsed_start=0.0, elapsed_end=600.0),  # 10 min
            _abs_source("B", start=T0 + timedelta(minutes=5), elapsed_start=0.0, elapsed_end=600.0),
        ])
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"A", "B"}

    def test_transitive_chain_groups_even_when_ends_do_not_directly_overlap(self):
        """A overlaps B, B overlaps C, A does NOT overlap C directly --
        still one group (task section 12's own transitive-chain case)."""
        groups = derive_time_groups([
            _abs_source("A", start=T0, elapsed_start=0.0, elapsed_end=10.0),
            _abs_source("B", start=T0 + timedelta(seconds=8), elapsed_start=0.0, elapsed_end=10.0),
            _abs_source("C", start=T0 + timedelta(seconds=16), elapsed_start=0.0, elapsed_end=10.0),
        ])
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"A", "B", "C"}


class TestElapsedOnlySource:
    def test_elapsed_only_source_never_joins_an_absolute_group(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0),
            _elapsed_source("C"),
        ])
        assert len(groups) == 2
        by_id = {g.group_id: g for g in groups}
        assert by_id["A"].source_ids == ["A"]
        assert by_id["A"].time_reference_type == TIME_REFERENCE_RECORDED_ABSOLUTE
        assert by_id["C"].source_ids == ["C"]
        assert by_id["C"].time_reference_type == TIME_REFERENCE_ELAPSED_ONLY


class TestTwoElapsedOnlySources:
    """Task section 15/38: do not group two elapsed-only sources
    together merely because both start at 0 -- remain separate by
    default."""

    def test_two_elapsed_only_sources_remain_separate(self):
        groups = derive_time_groups([
            _elapsed_source("C"),
            _elapsed_source("D"),
        ])
        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert group_ids == {"C", "D"}
        for g in groups:
            assert len(g.source_ids) == 1
            assert g.time_reference_type == TIME_REFERENCE_ELAPSED_ONLY


class TestMixedFourSourceCase:
    """Task section 32/38's own worked example: A+B absolute
    (overlapping), C elapsed, D elapsed -> Group1=A+B, Group2=C,
    Group3=D. Never A+B / C+D."""

    def test_mixed_case_matches_expected_default(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0, elapsed_start=0.0, elapsed_end=1.0),
            _abs_source("B", start=T0 + timedelta(milliseconds=500), elapsed_start=0.0, elapsed_end=1.0),
            _elapsed_source("C"),
            _elapsed_source("D"),
        ])
        assert len(groups) == 3
        by_id = {g.group_id: g for g in groups}
        assert set(by_id["A"].source_ids) == {"A", "B"}
        assert by_id["C"].source_ids == ["C"]
        assert by_id["D"].source_ids == ["D"]


class TestDateRollover:
    """Task section 18/38: A=23:59:59.800, B=00:00:00.200 next day ->
    a 400ms relationship, not compared as bare time-of-day."""

    def test_rollover_across_midnight_is_handled_correctly(self):
        a_start = datetime(2026, 3, 6, 23, 59, 59, 800_000)
        b_start = datetime(2026, 3, 7, 0, 0, 0, 200_000)
        groups = derive_time_groups([
            _abs_source("A", start=a_start, elapsed_start=0.0, elapsed_end=1.0),
            _abs_source("B", start=b_start, elapsed_start=0.0, elapsed_end=1.0),
        ])
        assert len(groups) == 1  # 400ms apart, both 1s long -> overlaps
        placement = timestamp_placement_offset_s(source_start_time=b_start, origin_start_time=a_start)
        assert placement == pytest.approx(0.4, abs=1e-9)


class TestTimeGroupCanvasDatetimeInvariants:
    """Slice TG-B+C sections 1-2/21-23: locks in that Time Groups are
    derived from complete, normalized absolute datetime intervals --
    never time-of-day alone -- ahead of the frontend Time Group Canvas
    work that reads these same groups. These are regression tests for
    already-correct `derive_time_groups()` behaviour verified ad hoc
    during that slice's own audit; no domain code changed."""

    def test_case_a_different_date_same_time_of_day_stays_two_groups(self):
        """Two non-overlapping recordings that happen to start at the
        exact same time-of-day on different calendar dates must NOT be
        merged merely because their clock time matches."""
        a_start = datetime(2026, 1, 27, 13, 9, 40)
        b_start = datetime(2026, 2, 3, 13, 9, 40)
        groups = derive_time_groups([
            _abs_source("A", start=a_start, elapsed_start=0.0, elapsed_end=1.0),
            _abs_source("B", start=b_start, elapsed_start=0.0, elapsed_end=1.0),
        ])
        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert group_ids == {"A", "B"}

    def test_case_b_bridging_long_record_merges_two_dates_into_one_group(self):
        """Task section 21 Case B's own literal worked example: A and B
        are on different dates and do not directly overlap, but bridge
        source C spans from A's date all the way to B's date -- the
        transitive overlap (A<->C, C<->B) must merge all three into ONE
        Time Group, never leave A and B split."""
        a_start = datetime(2026, 1, 27, 13, 0, 0)
        b_start = datetime(2026, 2, 3, 13, 0, 0)
        c_start = datetime(2026, 1, 27, 13, 0, 0)
        c_end_elapsed = (datetime(2026, 2, 3, 13, 0, 30) - c_start).total_seconds()
        groups = derive_time_groups([
            _abs_source("A", start=a_start, elapsed_start=0.0, elapsed_end=60.0),
            _abs_source("B", start=b_start, elapsed_start=0.0, elapsed_end=60.0),
            _abs_source("C", start=c_start, elapsed_start=0.0, elapsed_end=c_end_elapsed),
        ])
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"A", "B", "C"}

    def test_case_c_same_hour_different_date_does_not_imply_similarity(self):
        """Task section 23 Case C: two sources sharing the same clock
        hour but on different, non-overlapping dates prove that
        time-of-day *similarity* is never a grouping signal -- only the
        actual absolute datetime interval overlap is."""
        a_start = datetime(2026, 4, 1, 9, 30, 0)
        b_start = datetime(2026, 4, 15, 9, 30, 0)
        groups = derive_time_groups([
            _abs_source("A", start=a_start, elapsed_start=0.0, elapsed_end=2.0),
            _abs_source("B", start=b_start, elapsed_start=0.0, elapsed_end=2.0),
        ])
        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert group_ids == {"A", "B"}

    def test_midnight_rollover_non_overlapping_stays_two_groups(self):
        """Complement to TestDateRollover's overlapping case: when the
        two intervals straddle midnight but do NOT actually overlap
        (a real gap remains once compared as full datetimes), they must
        stay separate groups -- confirming the invariant isn't "any
        midnight-adjacent pair merges," only genuine interval overlap."""
        a_start = datetime(2026, 3, 6, 23, 59, 0)
        b_start = datetime(2026, 3, 7, 0, 5, 0)
        groups = derive_time_groups([
            _abs_source("A", start=a_start, elapsed_start=0.0, elapsed_end=1.0),
            _abs_source("B", start=b_start, elapsed_start=0.0, elapsed_end=1.0),
        ])
        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert group_ids == {"A", "B"}


class TestSamplingRateIsNeverAGroupingInput:
    """Task section 16/38: derive_time_groups() takes no sampling-rate
    parameter at all -- different rates cannot possibly block grouping
    because nothing here ever reads one."""

    def test_derive_time_groups_signature_has_no_rate_concept(self):
        import inspect

        from app.domain import time_grouping

        sig = inspect.signature(time_grouping.derive_time_groups)
        assert "rate" not in str(sig).lower()


class TestDeterminism:
    def test_group_and_source_order_is_deterministic(self):
        groups1 = derive_time_groups([
            _abs_source("B", start=T0 + timedelta(milliseconds=401)),
            _abs_source("A", start=T0),
        ])
        groups2 = derive_time_groups([
            _abs_source("A", start=T0),
            _abs_source("B", start=T0 + timedelta(milliseconds=401)),
        ])
        assert groups1 == groups2
        assert groups1[0].origin_source_id == "A"
        assert groups1[0].source_ids == ["A", "B"]

    def test_tie_broken_by_source_id_when_start_times_are_identical(self):
        groups = derive_time_groups([
            _abs_source("Z", start=T0),
            _abs_source("A", start=T0),
        ])
        assert len(groups) == 1
        assert groups[0].origin_source_id == "A"


class TestMissingStartTimeDefensiveFallback:
    def test_absolute_type_with_missing_start_time_becomes_its_own_group(self):
        groups = derive_time_groups([
            _abs_source("A", start=T0),
            ("B", "absolute", None, 0.0, 1.0),
        ])
        assert len(groups) == 2
        by_id = {g.group_id: g for g in groups}
        assert by_id["B"].source_ids == ["B"]


class TestMixedTimezoneAwarenessIntegration:
    """CSV/Excel ingestion Slice 11 (DEC-072): a converted CSV/Excel
    absolute source may carry a genuinely timezone-AWARE `start_time`
    (Slice 10 preserves a real declared offset) while a COMTRADE source
    is always naive -- mixing the two previously raised `TypeError`
    (Python refuses to compare/subtract aware vs naive datetimes). This
    is the regression test for that fix (`normalize_absolute_datetime()`
    in this module)."""

    def test_naive_and_aware_absolute_sources_do_not_crash(self):
        naive = T0
        aware = T0.replace(tzinfo=timezone(timedelta(hours=8)))
        groups = derive_time_groups([
            _abs_source("comtrade", start=naive),
            _abs_source("csv", start=aware),
        ])
        assert {g.group_id for g in groups} == {"comtrade", "csv"}

    def test_two_aware_sources_representing_the_same_instant_still_overlap(self):
        # 10:00 UTC and 18:00+08:00 are the SAME true instant.
        utc_source = datetime(2026, 3, 6, 10, 0, 0, tzinfo=timezone.utc)
        plus8_source = datetime(2026, 3, 6, 18, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        groups = derive_time_groups([
            _abs_source("a", start=utc_source),
            _abs_source("b", start=plus8_source),
        ])
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"a", "b"}

    def test_naive_treated_as_utc_never_changes_pure_naive_behavior(self):
        # Every existing (pre-Slice-10) COMTRADE-only workspace is
        # entirely naive datetimes -- confirms the fix is a no-op there.
        groups_before_reasoning = derive_time_groups([
            _abs_source("a", start=T0),
            _abs_source("b", start=T0 + timedelta(seconds=1)),
        ])
        assert len(groups_before_reasoning) == 1
        assert set(groups_before_reasoning[0].source_ids) == {"a", "b"}

    def test_timestamp_placement_offset_handles_mixed_awareness(self):
        naive_origin = T0
        aware_source = T0.replace(tzinfo=timezone.utc) + timedelta(seconds=5)
        offset = timestamp_placement_offset_s(source_start_time=aware_source, origin_start_time=naive_origin)
        assert offset == pytest.approx(5.0)
