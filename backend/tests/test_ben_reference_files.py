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
from datetime import datetime, timedelta, timezone
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
#: time (a naive CFG timestamp); every validated pair was exported at
#: UTC+08:00. BEN itself stays UTC -- this only reproduces the export.
EXPORT_TIMEZONE = timezone(timedelta(hours=8))
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
    assert h.trigger_time_utc == datetime.fromisoformat(expected["trigger_time_utc"]).replace(tzinfo=timezone.utc)
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
    assert record.header.trigger_time_utc.astimezone(EXPORT_TIMEZONE).replace(tzinfo=None) == cfg.trigger_time
    assert record.header.start_time_utc.astimezone(EXPORT_TIMEZONE).replace(tzinfo=None) == cfg.start_time
    assert cfg.sampling_rates == [record.header.sampling_rate_hz]
    assert cfg.total_samples == record.sample_count


def test_normalized_lgng_engineering_values_match_the_comtrade_scaling(reference_root):
    record, _, cfg, dat = _matched(reference_root, "lgng_fast")
    dr = to_disturbance_record(record, source_file="lgng.ben", nominal_frequency_hz=50.0)
    for i, d in enumerate(cfg.analog_defs):
        expected = dat[:, 2 + i] * d.a + d.b
        np.testing.assert_allclose(dr.waveform_data[d.ch_id].to_numpy(), expected, rtol=FLOAT32_REL, atol=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Through the real upload endpoint (DEC-120)
# ─────────────────────────────────────────────────────────────────────────────

WS_URL = "/api/v1/workspaces/ws-ref/sources"


@pytest.fixture
def client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload_ben(client, path: Path):
    return client.post(WS_URL, files={"ben_file": (path.name, path.read_bytes(), "application/octet-stream")})


@pytest.mark.parametrize("record_id", DECODABLE)
def test_reference_ben_imports_through_the_upload_endpoint(reference_root, client, record_id):
    entry = RECORDS[record_id]
    expected = entry["expected"]
    resp = _upload_ben(client, _locate(reference_root, entry["ben"]))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider_type"] == "BEN"
    assert body["station_name"] == expected["station_name"]
    assert body["sample_count"] == expected["sample_count"]
    assert body["analog_channel_count"] == expected["value_channels"]
    assert body["digital_channel_count"] == expected["digital_channels"]
    assert body["nominal_frequency"] == 50.0
    trigger = datetime.fromisoformat(body["trigger_time"].replace("Z", "+00:00"))
    start = datetime.fromisoformat(body["start_time"].replace("Z", "+00:00"))
    assert trigger == datetime.fromisoformat(expected["trigger_time_utc"]).replace(tzinfo=timezone.utc)
    pre_trigger_s = expected["pre_trigger_samples"] / expected["sampling_rate_hz"]
    assert (trigger - start).total_seconds() == pytest.approx(pre_trigger_s)

    timebase = client.get(f"{WS_URL}/{body['source_id']}/channels").json()["timebase"]
    assert timebase["sampling_rates"] == [expected["sampling_rate_hz"]]
    assert timebase["duration_seconds"] == pytest.approx((expected["sample_count"] - 1) / expected["sampling_rate_hz"])


def test_lgng_fast_reaches_the_workspace_with_exact_values(reference_root, client):
    record, entry, cfg, dat = _matched(reference_root, "lgng_fast")
    body = _upload_ben(client, _locate(reference_root, entry["ben"])).json()
    assert body["sample_count"] == 42745
    assert (trigger := body["trigger_time"]) == "2026-01-16T05:54:23.229783Z", trigger
    active = client.app.state.workspace_registry.get("ws-ref", body["source_id"])
    data = active.record.waveform_data
    assert data["time"].iloc[2500] == pytest.approx(0.5)  # the trigger sample
    for i, d in enumerate(cfg.analog_defs):
        np.testing.assert_allclose(data[d.ch_id].to_numpy(), dat[:, 2 + i] * d.a + d.b, rtol=FLOAT32_REL, atol=1e-9)
    provenance = active.metadata.preparation_provenance
    assert provenance["record_class"] == "Fast SubBen"
    assert provenance["nominal_frequency_assumed"] is True
    assert all(c["bay"] for c in provenance["channels"])


def test_pmjy_slow_reaches_the_workspace_as_calculated_channels(reference_root, client):
    entry = RECORDS["pmjy_slow"]
    body = _upload_ben(client, _locate(reference_root, entry["ben"])).json()
    assert body["trigger_time"] == "2022-07-27T04:41:49.926317Z"
    channels = client.get(f"{WS_URL}/{body['source_id']}/channels").json()
    types = {c["engineering_type"] for c in channels["analog_channels"]}
    assert types == {"Frequency", "Power"}
    for name in entry["expected"]["unavailable_channels"]:
        wave = client.get(f"{WS_URL}/{body['source_id']}/waveform", params={"channel_name": name}).json()
        assert wave["values"] == [None] * 1401
    wave = client.get(f"{WS_URL}/{body['source_id']}/waveform", params={"channel_name": "FREQ UR BBTU"}).json()
    assert None not in wave["values"]
    assert wave["time"][400] == pytest.approx(20.0)  # trigger at 400 / 20 s
    # No V/I bay can be formed from frequency/power channels.
    contexts = client.get("/api/v1/workspaces/ws-ref/engineering-contexts").json()
    assert all(body["source_id"] not in str(c) for c in contexts)


@pytest.mark.parametrize("record_id", UNSUPPORTED)
def test_unsupported_reference_layout_is_a_domain_error_through_upload(reference_root, client, record_id):
    resp = _upload_ben(client, _locate(reference_root, RECORDS[record_id]["ben"]))
    assert resp.status_code == 400
    assert resp.json()["detail"] == {
        "code": "unsupported_ben_variant",
        "message": "This BEN file uses a BEN layout that is not currently supported.",
    }


@pytest.mark.parametrize("record_id", MATCHED)
def test_ben_and_its_comtrade_export_are_the_same_recording(reference_root, client, record_id):
    """Downstream needs no BEN branch: the same event imported as BEN
    and as BEN32 COMTRADE gives the same canonical instant (one Time
    Group, zero placement -- DEC-121), the same channel identities and
    classifications, the same digital states and the same values."""
    entry = RECORDS[record_id]
    ws = f"ws-pair-{record_id}"
    url = f"/api/v1/workspaces/{ws}/sources"
    ben_bytes = _locate(reference_root, entry["ben"]).read_bytes()
    ben = client.post(url, files={"ben_file": ("r.ben", ben_bytes, "x")}).json()
    cfg_path, dat_path = _locate(reference_root, entry["comtrade_cfg"]), _locate(reference_root, entry["comtrade_dat"])
    files = {"cfg_file": ("e.cfg", cfg_path.read_bytes(), "x"), "dat_file": ("e.dat", dat_path.read_bytes(), "x")}
    comtrade = client.post(url, files=files).json()

    # Same instant: BEN stores UTC, the export naive local (+08:00); the
    # canonical companions (DEC-122) are identical.
    assert ben["trigger_time"].endswith("Z") and not comtrade["trigger_time"].endswith("Z")
    assert ben["start_time_utc"] == comtrade["start_time_utc"]
    assert ben["trigger_time_utc"] == comtrade["trigger_time_utc"]
    groups = client.get(f"/api/v1/workspaces/{ws}/synchronization/time-groups").json()
    assert len(groups) == 1 and set(groups[0]["source_ids"]) == {ben["source_id"], comtrade["source_id"]}
    placements = client.get(f"/api/v1/workspaces/{ws}/synchronization/sources").json()
    assert [p["timestamp_placement_offset_s"] for p in placements] == [0.0, 0.0]

    ben_ch = client.get(f"{url}/{ben['source_id']}/channels").json()
    com_ch = client.get(f"{url}/{comtrade['source_id']}/channels").json()

    def analog(channels):
        return {c["name"]: (c["engineering_type"], c["unit"], c["phase"]) for c in channels["analog_channels"]}

    def digital(channels):
        return [(c["name"], c["classification"]) for c in channels["digital_channels"]]

    assert analog(ben_ch) == analog(com_ch)
    assert sorted(digital(ben_ch)) == sorted(digital(com_ch))  # incl. duplicate-named digitals

    registry = client.app.state.workspace_registry
    ben_data = registry.get(ws, ben["source_id"]).record.waveform_data
    com_data = registry.get(ws, comtrade["source_id"]).record.waveform_data
    for name, _ in digital(com_ch):
        np.testing.assert_array_equal(ben_data[name].to_numpy(), com_data[name].to_numpy(), err_msg=name)
    for name in analog(com_ch):
        ben_values, com_values = ben_data[name].to_numpy(), com_data[name].to_numpy()
        available = ~np.isnan(ben_values)  # BEN NaN <-> BEN32's raw 99999 export
        np.testing.assert_allclose(ben_values[available], com_values[available], rtol=FLOAT32_REL, atol=1e-9, err_msg=name)
    assert ben["sample_count"] == comtrade["sample_count"]
