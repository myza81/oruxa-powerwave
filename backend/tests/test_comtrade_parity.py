"""Migration parity: golden values captured from powerwave's canonical
ComtradeProvider (app/providers/comtrade/comtrade_provider.py at commit
3156392), run against the same synthetic fixtures committed here.

This is not a live cross-repo test (oruxa_powerwave's test suite does not
import or depend on a sibling powerwave checkout at run time -- see
docs/project-memory/MIGRATION_PLAN.md's Testing strategy section for why).
Instead, the comparison was run once, manually, during this migration slice
against BOTH these synthetic fixtures and one real (uncommitted, not
redistributed here -- see the note below) powerwave sample file, and the
resulting values are hard-coded below as the regression baseline.

Real-sample cross-check (not committed, run locally, recorded for
traceability): powerwave/samples/comtrade/PTAI_MVLY_relay.CFG produced an
identical station_name, channel counts/names/units, sample_count,
start/trigger time, sampling_rates, and SHA-256 array hashes (16 hex chars)
for `time`, `VA`, `VB`, `VC`, and the first three digital channels, in both
the canonical powerwave provider and this ported one. That file was not
copied into this repository: powerwave/samples/README.md notes sample
files "may be large or confidential" (real substation event data), so it
was used for local verification only -- see this phase's final report /
docs/project-memory/HANDOFF.md.
"""

from __future__ import annotations

import hashlib

import pytest

from app.providers.comtrade import ComtradeProvider

_EXPECTED = {
    "synth_ascii": {
        "station_name": "SYNTH_STATION",
        "nominal_frequency": 50.0,
        "analog": [("VA", "V", 0.1, 0.0), ("VB", "V", 0.1, 0.0), ("IA", "A", 0.01, 0.0)],
        "digital": [("BRK_A", 0), ("BRK_B", 0)],
        "sample_count": 40,
        "duration": 0.00975,
        "start_time": "2026-03-06T10:00:00",
        "trigger_time": "2026-03-06T10:00:00.005000",
        "sampling_rates": [4000.0],
        "samples_per_rate": [40],
        "time_hash": None,  # filled in below -- ASCII and BINARY share the same values
        "VA": [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0] * 4,
        "IA": [round(0.01 * 50 * i, 10) for i in range(40)],
        "BRK_A": [0] * 20 + [1] * 20,
        "BRK_B": [0] * 10 + [1] * 30,
    },
}
_EXPECTED["synth_binary"] = _EXPECTED["synth_ascii"]


def _hash(array) -> str:
    return hashlib.sha256(array.tobytes()).hexdigest()[:16]


def test_parity_channel_and_metadata_values(comtrade_fixtures_dir):
    for stem, expected in _EXPECTED.items():
        record = ComtradeProvider().load(comtrade_fixtures_dir / f"{stem}.cfg")

        assert record.metadata.station_name == expected["station_name"], stem
        assert record.metadata.nominal_frequency == expected["nominal_frequency"], stem
        assert [
            (c.name, c.unit, c.scale, c.offset) for c in record.analog_channels
        ] == expected["analog"], stem
        assert [
            (c.name, c.normal_state) for c in record.digital_channels
        ] == expected["digital"], stem
        assert record.sample_count() == expected["sample_count"], stem
        assert record.duration_seconds() == expected["duration"], stem
        assert record.elapsed_start_seconds() == pytest.approx(0.0), stem
        assert record.elapsed_end_seconds() == pytest.approx(expected["duration"]), stem
        assert record.timing_info.start_time.isoformat() == expected["start_time"], stem
        assert record.timing_info.trigger_time.isoformat() == expected["trigger_time"], stem
        assert record.sampling_info.sampling_rates == expected["sampling_rates"], stem
        assert record.sampling_info.samples_per_rate == expected["samples_per_rate"], stem
        assert record.waveform_data["VA"].tolist() == expected["VA"], stem
        assert record.waveform_data["IA"].tolist() == expected["IA"], stem
        assert record.waveform_data["BRK_A"].tolist() == expected["BRK_A"], stem
        assert record.waveform_data["BRK_B"].tolist() == expected["BRK_B"], stem


def test_ascii_and_binary_encodings_agree_on_array_hashes(comtrade_fixtures_dir):
    """The two DAT encodings of the same synthetic event must parse to
    byte-identical arrays -- this is the parity check within
    oruxa_powerwave itself, independent of the powerwave cross-check above.
    """
    ascii_record = ComtradeProvider().load(comtrade_fixtures_dir / "synth_ascii.cfg")
    binary_record = ComtradeProvider().load(comtrade_fixtures_dir / "synth_binary.cfg")

    for column in ("time", "VA", "VB", "IA", "BRK_A", "BRK_B"):
        ascii_hash = _hash(ascii_record.waveform_data[column].to_numpy())
        binary_hash = _hash(binary_record.waveform_data[column].to_numpy())
        assert ascii_hash == binary_hash, column
