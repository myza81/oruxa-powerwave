"""Revision-scoped COMTRADE ASCII nulls, including BEN32 Slow exports.

IEEE PSRC H5-c report (2008), pp4-5, quotes COMTRADE-1999's reserved
ASCII analog code 99999: https://www.pes-psrc.org/kb/report/068.pdf.
This is a raw-field rule, never a threshold or an engineering-value rule.
The owner originals are optional and located by their existing manifest hashes.
"""
from __future__ import annotations

from functools import cache
import hashlib
import json
from pathlib import Path
import struct

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.main import create_app
from app.providers.ben import parse_ben_file, to_disturbance_record
from app.providers.comtrade import ComtradeProvider, _parse_cfg


def _ascii(tmp_path, *, revision="1999", raw=(0, 99999, 1000, 99999, -1000), gain=0.0005, offset=50):
    # A second valid channel and digital state in each row must survive a gap.
    cfg = tmp_path / "event.cfg"
    cfg.write_text("\n".join([
        f"SYNTHETIC,DEVICE,{revision}", "3,2A,1D",
        f"1,FREQ,A,,Hz,{gain},{offset},0,-99999,99998,1,1,P",
        "2,VA,A,,V,1,0,0,-99999,99998,1,1,P", "1,CB,,,0",
        "50", "1", f"1000,{len(raw)}", "11/11/2026,08:00:00.000000",
        "11/11/2026,08:00:00.000000", "ASCII", "1", "",
    ]), encoding="ascii")
    cfg.with_suffix(".dat").write_text("\n".join(
        f"{i+1},{i*1000},{value},{10+i},{i%2}" for i, value in enumerate(raw)
    ) + "\n", encoding="ascii")
    return cfg


@pytest.mark.parametrize("revision", ["1999", "2001", "2005"])
def test_reserved_raw_code_becomes_null_before_gain_and_offset(tmp_path, revision):
    path = _ascii(tmp_path, revision=revision)
    original = path.with_suffix(".dat").read_bytes()
    record = ComtradeProvider().load(path)
    np.testing.assert_array_equal(record.waveform_data["FREQ"], [50, np.nan, 50.5, np.nan, 49.5])
    np.testing.assert_array_equal(record.waveform_data["VA"], [10, 11, 12, 13, 14])
    np.testing.assert_array_equal(record.waveform_data["CB"], [0, 1, 0, 1, 0])
    assert record.sample_count() == 5
    assert record.analog_channels[0].measurement_side == "primary"
    assert path.with_suffix(".dat").read_bytes() == original


@pytest.mark.parametrize("gain,offset", [(0, 50), (-2, 7)])
def test_null_survives_zero_or_negative_gain(tmp_path, gain, offset):
    record = ComtradeProvider().load(_ascii(tmp_path, gain=gain, offset=offset))
    values = record.waveform_data["FREQ"].to_numpy()
    assert np.isnan(values[[1, 3]]).all()
    np.testing.assert_array_equal(values[[0, 2, 4]], np.array([0, 1000, -1000])*gain + offset)


def test_valid_raw_limits_and_engineering_value_99999_are_preserved(tmp_path):
    path = _ascii(tmp_path, raw=(-99999, 99998, 100), gain=1000, offset=-1)
    record = ComtradeProvider().load(path)
    np.testing.assert_array_equal(record.waveform_data["FREQ"], [-99999001, 99997999, 99999])


@pytest.mark.parametrize("raw", [(99999,99999,1), (1,99999,99999), (99999,)*5])
def test_leading_trailing_and_whole_channel_unavailable_intervals(tmp_path, raw):
    record = ComtradeProvider().load(_ascii(tmp_path, raw=raw))
    expected = np.array(raw, dtype=float)*.0005 + 50
    expected[np.array(raw) == 99999] = np.nan
    np.testing.assert_array_equal(record.waveform_data["FREQ"], expected)
    np.testing.assert_array_equal(record.waveform_data["VA"], np.arange(len(raw))+10)
    assert record.sample_count() == len(raw)


@pytest.mark.parametrize("revision", ["1991", "2013", "", "unrecognized"])
def test_other_or_assumed_revisions_do_not_acquire_a_numeric_null_rule(tmp_path, revision):
    # Preserve the existing parser's fallback, without treating a guessed
    # revision as authoritative evidence about what 99999 means.
    path = _ascii(tmp_path, revision=revision, raw=(99999, 12))
    if revision == "unrecognized":
        with pytest.warns(UserWarning, match="Unrecognized rev_yr"):
            record = ComtradeProvider().load(path)
    else:
        record = ComtradeProvider().load(path)
    np.testing.assert_array_equal(record.waveform_data["FREQ"], [99.9995, 50.006])


def test_binary_values_are_not_reinterpreted_by_the_ascii_rule(tmp_path):
    path = _ascii(tmp_path, raw=(100, -1, -32768), gain=1000, offset=-1)
    path.write_text(path.read_text().replace("ASCII", "BINARY"), encoding="ascii")
    path.with_suffix(".dat").write_bytes(b"".join(
        struct.pack("<IIhhH", i+1, i*1000, value, 10+i, i%2)
        for i, value in enumerate([100, -1, -32768])
    ))
    record = ComtradeProvider().load(path)
    np.testing.assert_array_equal(record.waveform_data["FREQ"], [99999, -1001, -32768001])


def test_sample_numbers_and_timestamps_equal_to_99999_are_not_nulls(tmp_path):
    path = _ascii(tmp_path, raw=(0, 1))
    path.with_suffix(".dat").write_text("99999,99999,0,10,0\n100000,100999,1,11,1\n", encoding="ascii")
    record = ComtradeProvider().load(path)
    np.testing.assert_array_equal(record.waveform_data["FREQ"], [50, 50.0005])
    assert record.waveform_data["time"].iloc[0] == pytest.approx(0.099999)


def test_gaps_reach_waveforms_cursors_peaks_and_nested_calculations(tmp_path, settings):
    path = _ascii(tmp_path, raw=(0, 99999, 99999, 1000, -1000, 99999, 2000))
    expected = [50, None, None, 50.5, 49.5, None, 51]
    with TestClient(create_app(settings)) as client:
        base = "/api/v1/workspaces/ws-ascii-null"
        upload = client.post(base+"/sources", files={
            "cfg_file": ("event.cfg", path.read_bytes(), "x"),
            "dat_file": ("event.dat", path.with_suffix(".dat").read_bytes(), "x"),
        })
        assert upload.status_code == 201, upload.text
        sid = upload.json()["source_id"]
        url = f"{base}/sources/{sid}"
        wave = client.get(url+"/waveform", params={"channel_name":"FREQ"})
        assert wave.status_code == 200, wave.text
        assert wave.json()["values"] == expected
        assert wave.json()["unit"] == "Hz"
        cursor = client.post(url+"/cursor-values", json={"analog_channel_names":["FREQ"],"cursor_a_time":.001,"cursor_b_time":.003})
        assert cursor.status_code == 200, cursor.text
        assert cursor.json()["channels"][0]["a_value"] is None
        assert cursor.json()["channels"][0]["b_value"] == 50.5
        peak = client.post(url+"/peak-values", json={"requests":[{"channel_name":"FREQ","mode":"max"}],"start_time":0,"end_time":.006})
        assert peak.status_code == 200, peak.text
        assert peak.json()["results"][0]["value"] == 51
        first_input = {"kind":"source","source_id":sid,"channel_name":"FREQ"}
        for name, inp, sign in [("Reverse frequency", first_input, -1), ("Restore frequency", None, 1)]:
            if inp is None: inp = {"kind":"calculated","calculated_channel_id":cid}
            create = client.post(base+"/calculated-channels", json={"name":name,"operation":"reverse_polarity","inputs":[inp],"null_policy":"propagate_null"})
            assert create.status_code == 201, create.text
            cid = create.json()["id"]
            calc = client.get(f"{base}/calculated-channels/{cid}/waveform")
            assert calc.status_code == 200, calc.text
            assert calc.json()["values"] == [None if v is None else sign*v for v in expected]
        assert client.get(url+"/waveform",params={"channel_name":"FREQ"}).json()["values"] == expected


MANIFEST = json.loads((Path(__file__).parent/"fixtures/ben/reference_manifest.json").read_text())
SPECS = {e["id"]:e for e in MANIFEST["records"]}


@cache
def _original(root, spec_json):
    spec = json.loads(spec_json)
    for p in sorted(root.rglob(spec["name"])):
        if p.stat().st_size == spec["size"] and hashlib.sha256(p.read_bytes()).hexdigest() == spec["sha256"]:
            return p
    pytest.skip(f"owner reference not available: {spec['name']}")


@pytest.fixture
def reference_paths(request):
    configured = request.config.getoption("--ben-reference-dir")
    if not configured: pytest.skip("requires --ben-reference-dir owner corpus")
    def paths(key):
        e = SPECS[key]
        return tuple(_original(Path(configured), json.dumps(e[k],sort_keys=True)) for k in ["ben","comtrade_cfg","comtrade_dat"])
    return paths


@pytest.mark.ben_reference
@pytest.mark.parametrize("record_id,name", [
    ("pmjy_slow","FREQ SGT1 VB_HV"), ("pmjy_slow","FREQ SGT1 VY_LV"),
    ("pmjy_slow","FREQ SGT2 VR_HV"), ("pmjy_slow","FREQ SGT2 VB_LV"),
    ("btgh_slow","FREQ TMGR VB"),
])
def test_real_ben32_slow_unavailable_channel_does_not_become_99_9995_hz(reference_paths, record_id, name):
    ben, cfg, _ = reference_paths(record_id)
    native = parse_ben_file(ben)
    channel = native.value_channel(name)
    assert np.all(native.raw_values(channel) == -32768)
    assert _parse_cfg(cfg).rev_yr == "1999"  # Existing 2005 alias.
    imported = ComtradeProvider().load(cfg)
    values = imported.waveform_data[name].to_numpy()
    assert len(values) == native.sample_count == 1401
    assert np.isnan(values).all(), f"unavailable data became {np.unique(values)} Hz"


@pytest.mark.ben_reference
@pytest.mark.parametrize("record_id", ["pmjy_slow", "btgh_slow"])
def test_real_slow_export_valid_values_and_gap_positions_match_native(reference_paths, record_id):
    ben, cfg, _ = reference_paths(record_id)
    native = to_disturbance_record(parse_ben_file(ben),source_file=str(ben),nominal_frequency_hz=50)
    imported = ComtradeProvider().load(cfg)
    assert native.sample_count() == imported.sample_count()
    for channel in native.analog_channels:
        a = native.waveform_data[channel.name].to_numpy()
        b = imported.waveform_data[channel.name].to_numpy()
        np.testing.assert_array_equal(np.isnan(a),np.isnan(b),err_msg=channel.name)
        np.testing.assert_allclose(a,b,rtol=np.finfo(np.float32).eps,atol=1e-9,err_msg=channel.name)
        assert next(c.unit for c in imported.analog_channels if c.name==channel.name) == channel.unit
    for channel in native.digital_channels:
        np.testing.assert_array_equal(native.waveform_data[channel.name],imported.waveform_data[channel.name])
