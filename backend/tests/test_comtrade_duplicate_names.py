"""DEC-121: a COMTRADE channel descriptor binds to its own data column.

Regression for the BEN32 Slow export pattern: an analog and a digital
both named ``POWER BBTU``. Before the fix the digital's column was
renamed ``POWER BBTU_1`` but its descriptor kept ``POWER BBTU``, so the
digital was classified from the analog MW series ("triggered").
"""

from __future__ import annotations

import io
import warnings

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.comtrade import ComtradeProvider

CFG = """PMJY,1214,2005
5,2A,3D
1,FREQ UR BBTU,A,,Hz,0.0005,50.0,0,-32767,+32767,1,1,P
2,POWER BBTU,,,MW,2.2431788445,0.0,0,-32767,+32767,1,1,P
1,FREQ UR BBTU,,,0
2,POWER BBTU,,,0
3,SPARE,,,0
50
1
20.000,6
27/07/2022,12:41:29.926317
27/07/2022,12:41:49.926317
ASCII
1
"""
# MW raw 31 -> 69.5 MW (never 0/1); digitals 0, toggling 0/1, 0.
DAT = "".join(
    f"{i + 1},{i * 50000},{-75 + i},{31 + i},0,{i % 2},0\n" for i in range(6)
)


@pytest.fixture
def cfg_path(tmp_path):
    (tmp_path / "e.cfg").write_text(CFG)
    (tmp_path / "e.dat").write_text(DAT)
    return tmp_path / "e.cfg"


def _load(cfg_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return ComtradeProvider().load_with_provenance(cfg_path)


def test_every_descriptor_names_its_own_column(cfg_path):
    record, _ = _load(cfg_path)
    assert [c.name for c in record.analog_channels] == ["FREQ UR BBTU", "POWER BBTU"]
    assert [c.name for c in record.digital_channels] == ["FREQ UR BBTU_1", "POWER BBTU_1", "SPARE"]
    assert record.validate() == []
    names = [c.name for c in record.analog_channels + record.digital_channels]
    assert len(set(names)) == len(names)
    assert list(record.waveform_data.columns) == ["time", *names]


def test_duplicate_named_digital_reads_digital_samples_not_the_analog(cfg_path):
    record, _ = _load(cfg_path)
    data = record.waveform_data
    np.testing.assert_allclose(data["POWER BBTU"], (np.arange(6) + 31) * 2.2431788445)
    assert data["POWER BBTU_1"].tolist() == [0, 1, 0, 1, 0, 1]
    assert data["FREQ UR BBTU_1"].tolist() == [0] * 6


def test_original_names_are_kept_as_provenance(cfg_path):
    _, provenance = _load(cfg_path)
    assert provenance == {
        "source_format": "COMTRADE",
        "channel_renames": [
            {"name": "FREQ UR BBTU_1", "source_name": "FREQ UR BBTU", "kind": "digital", "index": 1},
            {"name": "POWER BBTU_1", "source_name": "POWER BBTU", "kind": "digital", "index": 2},
        ],
    }


def test_no_duplicates_means_no_renames_and_no_provenance(comtrade_fixtures_dir):
    record, provenance = ComtradeProvider().load_with_provenance(comtrade_fixtures_dir / "synth_ascii.cfg")
    assert provenance is None
    assert [c.name for c in record.digital_channels] == ["BRK_A", "BRK_B"]


def test_import_classifies_the_duplicate_named_digital_from_its_own_states(settings):
    files = {"cfg_file": ("e.cfg", io.BytesIO(CFG.encode()), "x"), "dat_file": ("e.dat", io.BytesIO(DAT.encode()), "x")}
    with TestClient(create_app(settings)) as client:
        body = client.post("/api/v1/workspaces/ws-dup/sources", files=files).json()
        channels = client.get(f"/api/v1/workspaces/ws-dup/sources/{body['source_id']}/channels").json()
        digital = {c["name"]: c["classification"] for c in channels["digital_channels"]}
        assert digital["FREQ UR BBTU_1"] == "never_triggered"
        assert digital["POWER BBTU_1"] == "triggered"  # its own 0/1 toggling, not MW
        wave = client.get(
            f"/api/v1/workspaces/ws-dup/sources/{body['source_id']}/digital-waveform",
            params={"channel_names": "FREQ UR BBTU_1"},
        ).json()
        assert wave["channels"][0]["transitions"] == []
