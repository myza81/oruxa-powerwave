"""Writes the committed synthetic BEN fixtures used by the browser tests.

    cd backend && python tests/ben/make_fixtures.py

The fixtures are fully synthetic (no owner data): a Fast record with a
50 Hz three-phase bay and two binaries, and a Slow record with
frequency/power channels including unavailable samples.
test_ben_fixtures.py fails if a committed file drifts from this script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from synthetic_ben import SynthBen, SynthDigital, SynthValue, active_low, to_word

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "ben"


def fast_spec() -> SynthBen:
    """1000 samples/s, 0.5 s, 100 ms pre-trigger, a fault on phase R."""
    n, rate = 500, 1000.0
    t = np.arange(n) / rate
    fault = t >= 0.2
    words = np.zeros((n, 9), dtype=np.uint16)
    for k, shift in enumerate((0.0, -2 * np.pi / 3, 2 * np.pi / 3)):
        sag = np.where(fault & (k == 0), 0.4, 1.0)
        words[:, 1 + k] = to_word(np.round(14000 * sag * np.sin(2 * np.pi * 50 * t + shift)))
        rise = np.where(fault & (k == 0), 6.0, 1.0)
        words[:, 5 + k] = to_word(np.round(3000 * rise * np.sin(2 * np.pi * 50 * t + shift - 0.5)))
    trip = (t >= 0.26).astype(np.uint16)
    words[:, 0] = (active_low(trip) << 0) | (active_low(np.zeros(n)) << 1)
    words[:, 4] = active_low(fault.astype(np.uint16)) << 3
    phases = {"R": 1, "Y": 2, "B": 3}
    values = [
        SynthValue(10000 + i, f"LINE1 V{p}", word=1 + i, phase_code=code, scale=0.0275, primary=500.0, secondary=110.0, bay="FEEDER LINE1")
        for i, (p, code) in enumerate(phases.items())
    ] + [
        SynthValue(10004 + i, f"LINE1 I{p}", word=5 + i, unit_code=5, quantity_code=4, phase_code=code, scale=0.00075, primary=2.0, secondary=1.0, bay="FEEDER LINE1")
        for i, (p, code) in enumerate(phases.items())
    ]
    return SynthBen(
        record_class="fast",
        rate_field=1_000_000,
        pre_trigger=100,
        words_per_sample=9,
        values=values,
        digitals=[
            SynthDigital("derived", 20000, "UNDER LINE1 VR", word=4, bit=3, source_channel_id=10000, bay="FEEDER LINE1"),
            SynthDigital("physical", 11000, "LINE1 TRIP", word=0, bit=0, bay="FEEDER LINE1"),
            SynthDigital("physical", 11001, "SPARE", word=0, bit=1),
        ],
        samples=words,
        station="SYNTH BEN FAST",
    )


def slow_spec() -> SynthBen:
    """20 samples/s, 30 s, 10 s pre-trigger; one frequency never available."""
    n = 600
    i = np.arange(n)
    words = np.zeros((n, 4), dtype=np.uint16)
    words[:, 0] = to_word(np.round(200 + 30 * np.sin(i / 40)))  # MW raw
    words[:, 1] = to_word(np.where(i < 50, -32768, np.round(-80 * np.exp(-(i - 200) ** 2 / 4000.0))))
    words[:, 2] = to_word(np.full(n, -32768))
    words[:, 3] = active_low((i >= 210).astype(np.uint16)) << 2
    return SynthBen(
        record_class="slow",
        rate_field=20_000,
        pre_trigger=200,
        words_per_sample=4,
        values=[
            SynthValue(12000, "POWER LINE1", word=0, unit_code=38, multiplier=6, phase_code=0, quantity_code=14, scale=0.75),
            SynthValue(12001, "FREQ LINE1 VR", word=1, unit_code=33, multiplier=0, phase_code=1, quantity_code=14, scale=0.0005, offset=50.0),
            SynthValue(12002, "FREQ LINE2 VY", word=2, unit_code=33, multiplier=0, phase_code=2, quantity_code=14, scale=0.0005, offset=50.0),
        ],
        digitals=[SynthDigital("derived", 20060, "UNDER FREQ LINE1", word=3, bit=2, source_channel_id=12001)],
        samples=words,
        station="SYNTH BEN SLOW",
    )


FIXTURES = {"synthetic_fast.ben": fast_spec, "synthetic_slow.ben": slow_spec}


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in FIXTURES.items():
        (FIXTURE_DIR / name).write_bytes(spec().build()[0])
        print(f"wrote {FIXTURE_DIR / name}")


if __name__ == "__main__":
    main()
