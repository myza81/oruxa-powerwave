"""Native BEN parser against real owner records (optional, local only).

The BEN records and their BEN32-generated COMTRADE exports are owner
engineering data and are not committed. tests/fixtures/ben/
reference_manifest.json records each file's name, size and SHA-256 and
the structure it must decode to. These tests run only when a reference
directory is supplied:

    pytest -m ben_reference --ben-reference-dir "D:/.../Tripping Event"

(or POWERWAVE_BEN_REFERENCE_DIR). Files are found recursively by name and
used only when their SHA-256 matches; a missing file skips its test.

COMTRADE is only the validation oracle here: the BEN side is decoded by
the native parser alone. BEN<->COMTRADE channels are paired by name
(BEN32 reorders channels on export), repeated names by occurrence order.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.providers.ben import BenRecord, BenUnsupportedVariantError, parse_ben_file, to_disturbance_record
from app.providers.comtrade import _parse_cfg

pytestmark = pytest.mark.ben_reference

MANIFEST = json.loads((Path(__file__).parent / "fixtures" / "ben" / "reference_manifest.json").read_text())
RECORDS = {entry["id"]: entry for entry in MANIFEST["records"]}
DECODABLE = [i for i, e in RECORDS.items() if e["role"] != "unsupported_variant"]
MATCHED = [i for i, e in RECORDS.items() if e["role"].startswith("matched")]
UNSUPPORTED = [i for i, e in RECORDS.items() if e["role"] == "unsupported_variant"]

#: BEN32 renders BEN's UTC trigger instant in the exporting PC's local
#: time; every validated pair was exported at UTC+08:00.
EXPORT_UTC_OFFSET = timedelta(hours=8)
#: Value BEN32 writes to COMTRADE for an unavailable calculated sample.
COMTRADE_UNAVAILABLE = 99999
#: BEN stores scale/ratings as float32; BEN32 prints them to 10 decimals.
FLOAT32_REL = float(np.finfo(np.float32).eps)


@pytest.fixture(scope="session")
def reference_root(request) -> Path:
    configured = request.config.getoption("--ben-reference-dir") or os.environ.get("POWERWAVE_BEN_REFERENCE_DIR")
    if not configured:
        pytest.skip("no BEN reference directory configured (--ben-reference-dir / POWERWAVE_BEN_REFERENCE_DIR)")
    root = Path(configured)
    if not root.is_dir():
        pytest.fail(f"BEN reference directory does not exist: {root}")
    return root


def _locate(root: Path, spec: dict) -> Path:
    path = _find(root, spec["name"], spec["size"], spec["sha256"])
    if path is None:
        pytest.skip(f"reference file {spec['name']!r} (sha256 {spec['sha256'][:12]}...) not found under {root}")
    return path


@cache
def _find(root: Path, name: str, size: int, sha256: str) -> Path | None:
    for candidate in sorted(root.rglob(name)):
        if candidate.is_file() and candidate.stat().st_size == size:
            if hashlib.sha256(candidate.read_bytes()).hexdigest() == sha256:
                return candidate
    return None


@cache
def _parsed(path: Path) -> BenRecord:
    return parse_ben_file(path)


def _record(root: Path, record_id: str) -> tuple[BenRecord, dict]:
    entry = RECORDS[record_id]
    return _parsed(_locate(root, entry["ben"])), entry


@cache
def _comtrade(cfg_path: Path):
    cfg = _parse_cfg(cfg_path)
    dat = (
        pd.read_csv(cfg.dat_file, header=None, comment="\x1a", low_memory=False)
        .dropna(how="all")
        .to_numpy(dtype=np.int64)
    )
    return cfg, dat


def _matched(root: Path, record_id: str):
    record, entry = _record(root, record_id)
    _locate(root, entry["comtrade_dat"])
    cfg, dat = _comtrade(_locate(root, entry["comtrade_cfg"]))
    return record, entry, cfg, dat


# ─────────────────────────────────────────────────────────────────────────────
# Structure, decoded from BEN alone
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("record_id", DECODABLE)
def test_reference_record_structure(reference_root, record_id):
    record, entry = _record(reference_root, record_id)
    expected = entry["expected"]
    h = record.header
    assert h.record_class.value == expected["record_class"]
    assert h.station_name == expected["station_name"]
    assert h.recorder_unit_id == expected["recorder_unit_id"]
    assert h.sampling_rate_hz == expected["sampling_rate_hz"]
    assert h.sample_count == expected["sample_count"]
    assert h.pre_trigger_samples == expected["pre_trigger_samples"]
    assert h.sample_stride_bytes == expected["stride_bytes"]
    assert h.sample_data_offset == expected["data_offset"]
    assert h.sample_data_offset + h.sample_count * h.sample_stride_bytes == entry["ben"]["size"]
    assert len(record.value_channels) == expected["value_channels"]
    assert len(record.digital_channels) == expected["digital_channels"]
    assert h.trigger_time_utc == datetime.fromisoformat(expected["trigger_time_utc"])
    codes = {d.code for d in record.diagnostics}
    assert not codes & {
        "unresolved_digital_channels",
        "unreferenced_layout_entries",
        "unknown_unit_code",
        "unrecognized_section",
        "trigger_fraction_undecodable",
        "unverified_raw_extreme",
    }
    assert all(c.bay_name for c in record.value_channels)
    assert all(c.bay_name for c in record.digital_channels)

    dr = to_disturbance_record(record, source_file=entry["ben"]["name"], nominal_frequency_hz=50.0)
    assert dr.validate() == []


@pytest.mark.parametrize("record_id", UNSUPPORTED)
def test_unvalidated_ben_layout_is_rejected(reference_root, record_id):
    path = _locate(reference_root, RECORDS[record_id]["ben"])
    with pytest.raises(BenUnsupportedVariantError):
        parse_ben_file(path)


def test_agjh_layout_differs_from_lgng(reference_root):
    """The layouts that disprove 'universal' stride/offset/channel counts."""
    lgng, _ = _record(reference_root, "lgng_fast")
    agjh, _ = _record(reference_root, "agjh_fast")
    first_value_word = lambda r: min(c.slot.word_index for c in r.value_channels)  # noqa: E731
    assert (lgng.header.sample_stride_bytes, agjh.header.sample_stride_bytes) == (158, 128)
    assert (first_value_word(lgng), first_value_word(agjh)) == (8, 7)
    assert (len(lgng.value_channels), len(agjh.value_channels)) == (56, 49)


# ─────────────────────────────────────────────────────────────────────────────
# BEN <-> BEN32 COMTRADE export
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("record_id", MATCHED)
def test_every_value_sample_matches_the_comtrade_export(reference_root, record_id):
    record, entry, cfg, dat = _matched(reference_root, record_id)
    assert dat.shape[0] == record.sample_count
    column = {d.ch_id: 2 + i for i, d in enumerate(cfg.analog_defs)}
    assert len(column) == len(cfg.analog_defs) == len(record.value_channels)

    unavailable = set()
    for channel in record.value_channels:
        reference = dat[:, column[channel.name.strip()]]
        raw = record.raw_values(channel).astype(np.int64)
        valid = record.valid_mask(channel)
        np.testing.assert_array_equal(raw[valid], reference[valid], err_msg=channel.name)
        assert (reference[~valid] == COMTRADE_UNAVAILABLE).all(), channel.name
        if not valid.any():
            unavailable.add(channel.name)
    assert unavailable == set(entry["expected"].get("unavailable_channels", []))
    for name in entry["expected"].get("varying_channels", []):
        assert len(np.unique(record.raw_values(record.value_channel(name)))) > 1


@pytest.mark.parametrize("record_id", MATCHED)
def test_value_channel_metadata_matches_the_comtrade_export(reference_root, record_id):
    record, _, cfg, _ = _matched(reference_root, record_id)
    defs = {d.ch_id: d for d in cfg.analog_defs}
    for channel in record.value_channels:
        d = defs[channel.name.strip()]
        assert channel.unit == d.uu
        assert (channel.phase or None) == d.ph
        assert channel.scale == pytest.approx(d.a, rel=FLOAT32_REL)
        assert channel.offset == pytest.approx(d.b, abs=1e-9)
        if channel.primary_rating is not None:
            assert channel.primary_rating == pytest.approx(d.primary, rel=FLOAT32_REL)
            assert channel.secondary_rating_in_channel_unit == pytest.approx(d.secondary, rel=FLOAT32_REL)


@pytest.mark.parametrize("record_id", MATCHED)
def test_every_digital_sample_matches_the_comtrade_export(reference_root, record_id):
    record, entry, cfg, dat = _matched(reference_root, record_id)
    first_digital = 2 + len(cfg.analog_defs)
    columns = defaultdict(list)
    for i, d in enumerate(cfg.digital_defs):
        columns[d.ch_id].append(first_digital + i)
    assert len(record.digital_channels) == len(cfg.digital_defs)

    taken: dict[str, int] = defaultdict(int)
    changing = 0
    for channel in record.digital_channels:
        name = channel.name.strip()  # the CFG oracle strips fields; BEN keeps them exact
        column = columns[name][taken[name]]
        taken[name] += 1
        reference = dat[:, column]
        np.testing.assert_array_equal(record.digital_states(channel), reference, err_msg=channel.name)
        changing += int(reference.min() != reference.max())
    # Channels that change state confirm their mapping uniquely; constant
    # ones are only consistent with it.
    assert changing == entry["expected"]["changing_digitals"]


@pytest.mark.parametrize("record_id", MATCHED)
def test_trigger_and_start_times_match_the_comtrade_export(reference_root, record_id):
    record, _, cfg, _ = _matched(reference_root, record_id)
    assert record.header.trigger_time.microsecond is not None
    assert record.header.trigger_time_utc + EXPORT_UTC_OFFSET == cfg.trigger_time
    assert record.header.start_time_utc + EXPORT_UTC_OFFSET == cfg.start_time
    assert cfg.sampling_rates == [record.header.sampling_rate_hz]
    assert cfg.total_samples == record.sample_count


def test_normalized_lgng_engineering_values_match_the_comtrade_scaling(reference_root):
    record, _, cfg, dat = _matched(reference_root, "lgng_fast")
    dr = to_disturbance_record(record, source_file="lgng.ben", nominal_frequency_hz=50.0)
    for i, d in enumerate(cfg.analog_defs):
        expected = dat[:, 2 + i] * d.a + d.b
        np.testing.assert_allclose(dr.waveform_data[d.ch_id].to_numpy(), expected, rtol=FLOAT32_REL, atol=1e-9)
