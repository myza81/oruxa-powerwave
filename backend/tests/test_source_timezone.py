"""DEC-121: source timezone interpretation of absolute recording timestamps.

Stored value (as the importer produced it) vs source timezone
interpretation (naive -> DEFAULT_SOURCE_TIMEZONE, declared offset wins)
vs display (not decided here).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.source_timezone import DEFAULT_SOURCE_TIMEZONE, canonical_utc, interpret_naive
from app.domain.time_grouping import (
    TIME_REFERENCE_RECORDED_ABSOLUTE,
    derive_time_groups,
    normalize_absolute_datetime,
    timestamp_placement_offset_s,
)
from app.providers.comtrade import ComtradeProvider, _parse_time_code

# The validated LGNG pair: BEN stores UTC; BEN32's COMTRADE export
# stamps the exporting PC's Malaysian local clock (naive).
BEN_START = datetime(2026, 1, 16, 5, 54, 22, 729783, tzinfo=timezone.utc)
COMTRADE_START = datetime(2026, 1, 16, 13, 54, 22, 729783)


def test_default_source_timezone_is_malaysia():
    assert DEFAULT_SOURCE_TIMEZONE == "Asia/Kuala_Lumpur"


def test_naive_value_is_interpreted_in_the_source_timezone_digits_unchanged():
    local = interpret_naive(COMTRADE_START)
    assert local.replace(tzinfo=None) == COMTRADE_START
    assert local.utcoffset() == timedelta(hours=8)
    assert canonical_utc(COMTRADE_START) == BEN_START


def test_declared_offset_is_never_overridden():
    declared = datetime(2026, 1, 16, 0, 54, 22, tzinfo=timezone(timedelta(hours=-5)))
    assert interpret_naive(declared) is declared
    assert canonical_utc(declared) == datetime(2026, 1, 16, 5, 54, 22, tzinfo=timezone.utc)
    assert canonical_utc(BEN_START) == BEN_START


def test_ben_and_its_comtrade_export_are_the_same_instant():
    assert normalize_absolute_datetime(BEN_START) == normalize_absolute_datetime(COMTRADE_START)
    assert timestamp_placement_offset_s(source_start_time=COMTRADE_START, origin_start_time=BEN_START) == 0.0


def test_ben_and_its_comtrade_export_share_one_time_group():
    groups = derive_time_groups([
        ("ben", "absolute", BEN_START, 0.0, 8.5488),
        ("comtrade", "absolute", COMTRADE_START, 0.0, 8.5488),
    ])
    assert len(groups) == 1
    assert groups[0].time_reference_type == TIME_REFERENCE_RECORDED_ABSOLUTE
    assert set(groups[0].source_ids) == {"ben", "comtrade"}


def test_all_naive_sources_compare_exactly_as_before():
    a = datetime(2026, 1, 16, 13, 54, 22)
    b = a + timedelta(seconds=1.25)
    assert timestamp_placement_offset_s(source_start_time=b, origin_start_time=a) == pytest.approx(1.25)
    assert len(derive_time_groups([("a", "absolute", a, 0.0, 2.0), ("b", "absolute", b, 0.0, 2.0)])) == 1


def test_a_naive_utc_reading_would_have_kept_the_pair_apart():
    """Guards the policy: the old UTC label left BEN 8 h from its export."""
    utc_labelled = COMTRADE_START.replace(tzinfo=timezone.utc)
    assert (utc_labelled - BEN_START) == timedelta(hours=8)


# ── COMTRADE-2013 declared time_code ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "offset"),
    [("8", timedelta(hours=8)), ("+8", timedelta(hours=8)), ("-5", timedelta(hours=-5)),
     ("+5h30", timedelta(hours=5, minutes=30)), ("-3h30", timedelta(hours=-3, minutes=-30)), ("0", timedelta(0))],
)
def test_time_code_parses_declared_offsets(text, offset):
    assert _parse_time_code(text) == offset


@pytest.mark.parametrize("text", ["", "x", "F", "8:00", "+25", "abc", "8h"])
def test_unusable_time_code_declares_nothing(text):
    assert _parse_time_code(text) is None


def _write_comtrade(tmp_path, *, rev: str, tail: list[str], fixture_dir) -> object:
    cfg = (fixture_dir / "synth_ascii.cfg").read_text().splitlines()
    cfg[0] = f"SYNTH_STATION,SYNTH_DEV,{rev}"
    (tmp_path / "e.cfg").write_text("\n".join(cfg + tail) + "\n")
    (tmp_path / "e.dat").write_bytes((fixture_dir / "synth_ascii.dat").read_bytes())
    return ComtradeProvider().load(tmp_path / "e.cfg")


def test_comtrade_2013_time_code_makes_timestamps_aware(tmp_path, comtrade_fixtures_dir):
    record = _write_comtrade(tmp_path, rev="2013", tail=["8,8", "F,3"], fixture_dir=comtrade_fixtures_dir)
    start = record.timing_info.start_time
    assert start == datetime(2026, 3, 6, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    assert record.timing_info.timezone == record.metadata.timezone == "UTC+08:00"
    assert canonical_utc(start) == datetime(2026, 3, 6, 2, 0, tzinfo=timezone.utc)


def test_comtrade_2013_negative_half_hour_time_code(tmp_path, comtrade_fixtures_dir):
    record = _write_comtrade(tmp_path, rev="2013", tail=["-3h30,-3h30", "F,0"], fixture_dir=comtrade_fixtures_dir)
    assert record.timing_info.start_time.utcoffset() == timedelta(hours=-3, minutes=-30)


@pytest.mark.parametrize(("rev", "tail"), [("1999", []), ("1999", ["8,8"]), ("2013", []), ("2013", ["x,x"])])
def test_comtrade_without_a_declared_time_code_stays_naive(tmp_path, comtrade_fixtures_dir, rev, tail):
    record = _write_comtrade(tmp_path, rev=rev, tail=tail, fixture_dir=comtrade_fixtures_dir)
    assert record.timing_info.start_time.tzinfo is None
    assert record.timing_info.timezone is None
