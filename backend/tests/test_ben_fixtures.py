"""The committed synthetic BEN fixtures (used by browser-tests/ben-import.spec.js)
stay byte-identical to tests/ben/make_fixtures.py and parse as intended."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.providers.ben import BenRecordClass, parse_ben

sys.path.insert(0, str(Path(__file__).resolve().parent / "ben"))
from make_fixtures import FIXTURE_DIR, FIXTURES  # noqa: E402


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_committed_fixture_matches_its_generator(name):
    assert (FIXTURE_DIR / name).read_bytes() == FIXTURES[name](), (
        f"{name} drifted; regenerate with: python tests/ben/make_fixtures.py"
    )


def test_fixtures_decode_as_fast_and_slow_records():
    fast = parse_ben((FIXTURE_DIR / "synthetic_fast.ben").read_bytes())
    slow = parse_ben((FIXTURE_DIR / "synthetic_slow.ben").read_bytes())
    assert fast.header.record_class is BenRecordClass.FAST
    assert (fast.header.sampling_rate_hz, fast.sample_count, len(fast.value_channels)) == (1000.0, 500, 6)
    assert slow.header.record_class is BenRecordClass.SLOW
    assert (slow.header.sampling_rate_hz, slow.sample_count, len(slow.value_channels)) == (20.0, 600, 3)
    assert not slow.valid_mask(slow.value_channel("FREQ LINE2 VY")).any()
