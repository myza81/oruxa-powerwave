"""Unit tests for the ported ComtradeProvider (backend/app/providers/comtrade.py).

Fixtures are synthetic (see tests/fixtures/comtrade/, generated for this
migration -- not derived from any real utility event). See
tests/test_comtrade_parity.py for the golden-value regression test that
was cross-checked against powerwave's own canonical provider.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.providers.base import ProviderLoadError
from app.providers.comtrade import ComtradeProvider


def test_can_load_accepts_cfg_and_comtrade_suffixes():
    provider = ComtradeProvider()

    assert provider.can_load(Path("event.cfg"))
    assert provider.can_load(Path("event.CFG"))
    assert provider.can_load(Path("event.comtrade"))
    assert not provider.can_load(Path("event.csv"))
    assert not provider.can_load(Path("event.dat"))


@pytest.mark.parametrize("stem", ["synth_ascii", "synth_binary"])
def test_load_parses_channels_and_metadata(comtrade_fixtures_dir, stem):
    record = ComtradeProvider().load(comtrade_fixtures_dir / f"{stem}.cfg")

    assert record.metadata.provider_type == "COMTRADE"
    assert record.metadata.station_name == "SYNTH_STATION"
    assert [c.name for c in record.analog_channels] == ["VA", "VB", "IA"]
    assert [c.unit for c in record.analog_channels] == ["V", "V", "A"]
    assert [c.name for c in record.digital_channels] == ["BRK_A", "BRK_B"]
    assert record.sample_count() == 40
    assert record.validate() == []


@pytest.mark.parametrize("stem", ["synth_ascii", "synth_binary"])
def test_ascii_and_binary_produce_identical_values(comtrade_fixtures_dir, stem):
    record = ComtradeProvider().load(comtrade_fixtures_dir / f"{stem}.cfg")

    # VA = 0.1 * (1000 * (i % 10)), scale applied
    assert record.waveform_data["VA"].iloc[0] == pytest.approx(0.0)
    assert record.waveform_data["VA"].iloc[1] == pytest.approx(100.0)
    assert record.waveform_data["VA"].iloc[9] == pytest.approx(900.0)
    # BRK_A goes high at sample index 20 (0-based)
    assert record.waveform_data["BRK_A"].iloc[19] == 0
    assert record.waveform_data["BRK_A"].iloc[20] == 1
    # BRK_B goes high at sample index 10
    assert record.waveform_data["BRK_B"].iloc[9] == 0
    assert record.waveform_data["BRK_B"].iloc[10] == 1


def test_load_missing_dat_file_raises(tmp_path, comtrade_fixtures_dir):
    cfg_text = (comtrade_fixtures_dir / "synth_ascii.cfg").read_text(encoding="latin-1")
    orphan_cfg = tmp_path / "orphan.cfg"
    orphan_cfg.write_text(cfg_text, encoding="latin-1")

    with pytest.raises(ProviderLoadError, match="DAT file not found"):
        ComtradeProvider().load(orphan_cfg)


def test_load_binary32_is_rejected(tmp_path, comtrade_fixtures_dir):
    cfg_text = (comtrade_fixtures_dir / "synth_ascii.cfg").read_text(encoding="latin-1")
    cfg_text = cfg_text.replace("ASCII", "BINARY32")
    cfg_path = tmp_path / "synth32.cfg"
    dat_path = tmp_path / "synth32.dat"
    cfg_path.write_text(cfg_text, encoding="latin-1")
    dat_path.write_bytes(b"\x00" * 16)  # content irrelevant -- rejected before parsing

    with pytest.raises(ProviderLoadError, match="BINARY32"):
        ComtradeProvider().load(cfg_path)


def test_load_truncated_cfg_raises(tmp_path):
    cfg_path = tmp_path / "truncated.cfg"
    dat_path = tmp_path / "truncated.dat"
    cfg_path.write_text("STATION,DEV,1999\n5,3A,2D\n", encoding="latin-1")
    dat_path.write_bytes(b"")

    with pytest.raises(ProviderLoadError, match="truncated"):
        ComtradeProvider().load(cfg_path)
