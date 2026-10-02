"""BEN import through the real upload endpoint (DEC-120). Synthetic files only.

POST /api/v1/workspaces/{ws}/sources with ``ben_file`` -> provider
registry -> BenProvider -> native parser -> DisturbanceRecord -> the
same SourceMetadata/ActiveSource and post-upload preparation COMTRADE
uses. The real owner records are exercised by test_ben_reference_files.py.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.metadata import DEFAULT_NOMINAL_FREQUENCY_HZ
from app.main import create_app
from app.providers.base import ProviderNotFoundError
from app.providers.ben import BenProvider
from app.providers.comtrade import ComtradeProvider
from app.services.import_service import build_provider_manager

sys.path.insert(0, str(Path(__file__).resolve().parent / "ben"))
from synthetic_ben import SynthBen, SynthDigital, SynthValue, active_low, to_word  # noqa: E402

URL = "/api/v1/workspaces/ws-ben/sources"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _fast_bytes() -> bytes:
    n = 60
    words = np.zeros((n, 6), dtype=np.uint16)
    i = np.arange(n)
    words[:, 1] = to_word(np.round(400 * np.sin(2 * np.pi * i / 20)))
    words[:, 2] = to_word(np.round(300 * np.sin(2 * np.pi * i / 20 - 2.1)))
    words[:, 4] = to_word(np.round(90 * np.sin(2 * np.pi * i / 20)))
    words[:, 0] = active_low((i >= 30).astype(np.uint16)) << 2
    spec = SynthBen(
        record_class="fast",
        rate_field=1_000_000,  # 1000 samples/s
        pre_trigger=25,
        words_per_sample=6,
        values=[
            SynthValue(10000, " LINE1 VR", word=1, scale=0.5, bay="FEEDER LINE1"),
            SynthValue(10001, "LINE1 VY", word=2, phase_code=2, scale=0.5, bay="FEEDER LINE1"),
            SynthValue(10002, "LINE1 IR", word=4, unit_code=5, quantity_code=4, scale=0.01, primary=2.0, secondary=1.0, bay="FEEDER LINE1"),
        ],
        digitals=[
            SynthDigital("physical", 11000, "LINE1 CB OPEN", word=0, bit=2, bay="FEEDER LINE1"),
            SynthDigital("physical", 11001, "SPARE", word=3, bit=0),
            SynthDigital("physical", 11002, "SPARE", word=3, bit=1),
        ],
        samples=words,
    )
    return spec.build()[0]


def _slow_bytes() -> bytes:
    n = 40
    words = np.zeros((n, 4), dtype=np.uint16)
    i = np.arange(n)
    words[:, 0] = to_word(i * 4)  # MW
    words[:, 1] = to_word(np.where(i < 10, -32768, i - 20))  # Hz, first 10 unavailable
    words[:, 2] = to_word(np.full(n, -32768))  # Hz, never available
    words[:, 3] = active_low((i >= 15).astype(np.uint16)) << 5
    spec = SynthBen(
        record_class="slow",
        rate_field=20_000,
        pre_trigger=8,
        words_per_sample=4,
        values=[
            SynthValue(12000, "POWER LINE1", word=0, unit_code=38, multiplier=6, phase_code=0, quantity_code=14, scale=2.0),
            SynthValue(12001, "FREQ LINE1 VR", word=1, unit_code=33, multiplier=0, phase_code=1, quantity_code=14, scale=0.0005, offset=50.0),
            SynthValue(12002, "FREQ LINE2 VY", word=2, unit_code=33, multiplier=0, phase_code=2, quantity_code=14, scale=0.0005, offset=50.0),
        ],
        digitals=[SynthDigital("derived", 20060, "FREQ LINE1 VR", word=3, bit=5, source_channel_id=12001)],
        samples=words,
    )
    return spec.build()[0]


def _upload(client, data: bytes, name="record.ben", **form):
    return client.post(URL, files={"ben_file": (name, io.BytesIO(data), "application/octet-stream")}, data=form)


def _active(client, source_id):
    return client.app.state.workspace_registry.get("ws-ben", source_id)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# ─────────────────────────────────────────────────────────────────────────────
# Provider registration
# ─────────────────────────────────────────────────────────────────────────────


def test_upload_registry_routes_ben_and_comtrade_to_their_own_providers():
    manager = build_provider_manager()
    assert isinstance(manager.find_provider(Path("event.ben")), BenProvider)
    assert isinstance(manager.find_provider(Path("EVENT.BEN")), BenProvider)
    assert isinstance(manager.find_provider(Path("event.cfg")), ComtradeProvider)
    assert isinstance(manager.find_provider(Path("event.comtrade")), ComtradeProvider)
    with pytest.raises(ProviderNotFoundError):
        manager.find_provider(Path("event.dat"))


# ─────────────────────────────────────────────────────────────────────────────
# Successful imports
# ─────────────────────────────────────────────────────────────────────────────


def test_fast_ben_imports_through_the_source_upload_endpoint(client):
    data = _fast_bytes()
    resp = _upload(client, data, name="LINE1 fast.ben")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider_type"] == "BEN"
    assert body["station_name"] == "SYNTH STATION"
    assert body["status"] == "ready"
    assert body["analog_channel_count"] == 3
    assert body["digital_channel_count"] == 3
    assert body["sample_count"] == 60
    assert body["file_size_bytes"] == len(data)
    assert body["nominal_frequency"] == DEFAULT_NOMINAL_FREQUENCY_HZ

    # Canonical time is timezone-aware UTC; pre-trigger = 25 / 1000 s.
    start, trigger = _utc(body["start_time"]), _utc(body["trigger_time"])
    assert body["trigger_time"].endswith("Z")
    assert trigger == datetime.fromisoformat("2024-03-05T06:07:08.123456+00:00")
    assert (trigger - start).total_seconds() == pytest.approx(0.025)

    channels = client.get(f"{URL}/{body['source_id']}/channels").json()
    assert channels["timebase"]["sampling_rates"] == [1000.0]
    analog = {c["name"]: c for c in channels["analog_channels"]}
    assert list(analog) == ["LINE1 VR", "LINE1 VY", "LINE1 IR"]  # trimmed for display
    assert (analog["LINE1 VR"]["engineering_type"], analog["LINE1 VR"]["unit"], analog["LINE1 VR"]["phase"]) == ("Voltage", "kV", "A")
    assert (analog["LINE1 IR"]["engineering_type"], analog["LINE1 IR"]["unit"]) == ("Current", "kA")
    assert analog["LINE1 IR"]["primary_ratio"] == 2.0
    digital = {c["name"]: c for c in channels["digital_channels"]}
    assert list(digital) == ["LINE1 CB OPEN", "SPARE", "SPARE_1"]
    assert digital["LINE1 CB OPEN"]["classification"] == "triggered"

    wave = client.get(f"{URL}/{body['source_id']}/waveform", params={"channel_name": "LINE1 VR"}).json()
    assert wave["original_sample_count"] == 60
    np.testing.assert_allclose(wave["time"][:3], [0.0, 0.001, 0.002])


def test_ben_source_identity_is_kept_alongside_the_normalized_record(client):
    body = _upload(client, _fast_bytes()).json()
    provenance = _active(client, body["source_id"]).metadata.preparation_provenance
    assert provenance["source_format"] == "BEN"
    assert provenance["record_class"] == "Fast SubBen"
    assert provenance["time_basis"] == "UTC"
    assert provenance["nominal_frequency_assumed"] is True
    identities = {c["name"]: c for c in provenance["channels"]}
    assert identities["LINE1 VR"] == {
        "name": "LINE1 VR", "kind": "analog", "ben_channel_id": 10000,
        "source_name": " LINE1 VR", "bay": "FEEDER LINE1",
    }
    assert identities["SPARE_1"]["source_name"] == "SPARE"
    assert identities["SPARE_1"]["ben_channel_id"] == 11002
    assert identities["LINE1 CB OPEN"]["digital_source"] == "physical"


def test_slow_ben_imports_calculated_channels_with_nan_for_unavailable(client):
    resp = _upload(client, _slow_bytes(), name="slow.ben")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["analog_channel_count"], body["digital_channel_count"], body["sample_count"]) == (3, 1, 40)
    trigger, start = _utc(body["trigger_time"]), _utc(body["start_time"])
    assert (trigger - start).total_seconds() == pytest.approx(8 / 20)
    assert body["duration_seconds"] == pytest.approx(39 / 20)

    channels = client.get(f"{URL}/{body['source_id']}/channels").json()
    types = {c["name"]: (c["engineering_type"], c["unit"]) for c in channels["analog_channels"]}
    assert types == {
        "POWER LINE1": ("Power", "MW"),
        "FREQ LINE1 VR": ("Frequency", "Hz"),
        "FREQ LINE2 VY": ("Frequency", "Hz"),
    }
    # The derived binary shares a value channel's name -> suffixed for display.
    assert [c["name"] for c in channels["digital_channels"]] == ["FREQ LINE1 VR_1"]

    wave = client.get(f"{URL}/{body['source_id']}/waveform", params={"channel_name": "FREQ LINE1 VR"}).json()
    assert wave["values"][:10] == [None] * 10  # NaN, never 99999 or -32768
    assert wave["values"][10] == pytest.approx(50.0 - 10 * 0.0005)
    np.testing.assert_allclose(wave["time"][:3], [0.0, 0.05, 0.1])
    never = client.get(f"{URL}/{body['source_id']}/waveform", params={"channel_name": "FREQ LINE2 VY"})
    assert never.status_code == 200
    assert never.json()["values"] == [None] * 40

    record = _active(client, body["source_id"]).record
    assert record.waveform_data["FREQ LINE1 VR"].isna().sum() == 10
    assert not (record.waveform_data[["POWER LINE1", "FREQ LINE1 VR"]] == 99999).any().any()


def test_explicit_nominal_frequency_overrides_the_default(client):
    body = _upload(client, _fast_bytes(), nominal_frequency_hz="60").json()
    assert body["nominal_frequency"] == 60.0
    provenance = _active(client, body["source_id"]).metadata.preparation_provenance
    assert (provenance["nominal_frequency_hz"], provenance["nominal_frequency_assumed"]) == (60.0, False)


def test_comtrade_import_is_unchanged_and_carries_no_ben_provenance(client, comtrade_fixtures_dir):
    files = {
        "cfg_file": ("e.cfg", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes()), "x"),
        "dat_file": ("e.dat", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()), "x"),
    }
    resp = client.post(URL, files=files)
    assert resp.status_code == 201
    assert resp.json()["provider_type"] == "COMTRADE"
    assert _active(client, resp.json()["source_id"]).metadata.preparation_provenance is None


def test_ben_and_comtrade_sources_share_one_workspace(client, comtrade_fixtures_dir):
    _upload(client, _fast_bytes())
    files = {
        "cfg_file": ("e.cfg", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes()), "x"),
        "dat_file": ("e.dat", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()), "x"),
    }
    client.post(URL, files=files)
    listed = client.get(URL).json()
    assert sorted(s["provider_type"] for s in listed) == ["BEN", "COMTRADE"]


# ─────────────────────────────────────────────────────────────────────────────
# Errors: domain errors, never a 500, never internal offsets
# ─────────────────────────────────────────────────────────────────────────────


def _patched(data: bytes, offset: int, value: bytes) -> bytes:
    buf = bytearray(data)
    buf[offset : offset + len(value)] = value
    return bytes(buf)


@pytest.mark.parametrize(
    ("data_factory", "code", "phrase"),
    [
        # Older BEN layout discriminator (as in the BPHE/GPTH files).
        (lambda: _patched(_fast_bytes(), 0x04, b"\x28\xff"), "unsupported_ben_variant", "not currently supported"),
        (lambda: _fast_bytes()[:-5], "parse_error", "truncated"),
        (lambda: _fast_bytes()[:150], "parse_error", "truncated"),
        (lambda: _patched(_fast_bytes(), 0x7A, b"\x00\x00\x00\x00"), "parse_error", "corrupt"),
        (lambda: b"1,station,1999\n2,1A,1D\n" * 20, "parse_error", "not a recognized BEN record"),
        (lambda: bytes(range(256)) * 50, "parse_error", "not a recognized BEN record"),
    ],
)
def test_bad_ben_files_are_rejected_with_a_domain_error(client, data_factory, code, phrase):
    resp = _upload(client, data_factory())
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == code
    assert phrase in detail["message"]
    assert "offset" not in detail["message"] and "0x" not in detail["message"]
    assert client.get(URL).json() == []  # nothing half-imported


def test_empty_ben_file_is_invalid(client):
    resp = _upload(client, b"")
    assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "invalid_file")


def test_ben_field_requires_a_ben_extension(client):
    resp = _upload(client, _fast_bytes(), name="record.cfg")
    assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "unsupported_file_type")


def test_ben_with_a_comtrade_pair_is_ambiguous(client, comtrade_fixtures_dir):
    files = {
        "ben_file": ("r.ben", io.BytesIO(_fast_bytes()), "x"),
        "cfg_file": ("e.cfg", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes()), "x"),
    }
    resp = client.post(URL, files=files)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "ambiguous_source_upload")


def test_no_file_parts_is_still_the_field_required_validation_error(client):
    resp = client.post(URL, files={}, data={"unrelated": "1"})
    assert resp.status_code == 422
    assert {tuple(e["loc"]) for e in resp.json()["detail"]} == {("body", "cfg_file"), ("body", "dat_file")}


@pytest.mark.parametrize("value", ["0", "-50", "5000"])
def test_out_of_range_nominal_frequency_is_rejected(client, value):
    resp = _upload(client, _fast_bytes(), nominal_frequency_hz=value)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "invalid_nominal_frequency")


def test_nominal_frequency_is_rejected_for_comtrade(client, comtrade_fixtures_dir):
    files = {
        "cfg_file": ("e.cfg", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes()), "x"),
        "dat_file": ("e.dat", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()), "x"),
    }
    resp = client.post(URL, files=files, data={"nominal_frequency_hz": "60"})
    assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "invalid_nominal_frequency")


def test_oversized_ben_is_rejected_without_parsing(settings):
    from dataclasses import replace

    small = replace(settings, max_event_upload_size_mb=1)
    data = _fast_bytes()
    big = data + bytes(1024 * 1024)  # over the limit; never reaches the parser
    with TestClient(create_app(small)) as client:
        resp = _upload(client, big)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (413, "upload_too_large")


def _reactive_slow_bytes(station_suffix: int = 0) -> bytes:
    n = 30
    words = np.zeros((n, 4), dtype=np.uint16)
    i = np.arange(n)
    words[:, 0] = to_word(i * 4 - 50)  # MW
    words[:, 1] = to_word(i * 7 - 90)  # Mvar
    words[:, 2] = to_word(-(i * 5) + 12 + station_suffix)  # Mvar
    words[:, 3] = active_low((i >= 15).astype(np.uint16)) << 5
    spec = SynthBen(
        record_class="slow",
        rate_field=50_000,
        pre_trigger=8,
        words_per_sample=4,
        values=[
            SynthValue(12000, "POWER GSU 12UBF", word=0, unit_code=38, multiplier=6, phase_code=0, quantity_code=14, scale=2.0),
            SynthValue(12001, "R.POWER  GSU 12UBF", word=1, unit_code=63, multiplier=6, phase_code=0, quantity_code=14, scale=0.18183),
            SynthValue(12002, "R.POWER GSU 11UBF", word=2, unit_code=63, multiplier=6, phase_code=0, quantity_code=14, scale=0.0625, offset=-1.5),
        ],
        digitals=[SynthDigital("derived", 20060, "POWER GSU 12UBF", word=3, bit=5, source_channel_id=12000)],
        samples=words,
    )
    return spec.build()[0], spec


def test_ben_reactive_power_channels_share_one_reactive_power_display_axis(client):
    """Code 63 is classified by its validated unit code -- not by its name --
    so every code-63 channel resolves to Reactive Power (Mvar) and they
    share one display axis; values are exactly scale * raw + offset."""
    data, spec = _reactive_slow_bytes()
    body = _upload(client, data, name="PCGP like.ben").json()
    channels = {c["name"]: c for c in client.get(f"{URL}/{body['source_id']}/channels").json()["analog_channels"]}
    for name in ("R.POWER  GSU 12UBF", "R.POWER GSU 11UBF"):
        c = channels[name]
        assert (c["engineering_type"], c["unit"]) == ("Power", "Mvar")
        assert (c["display_axis_key"], c["display_axis_quantity"], c["display_axis_unit"]) == ("Reactive Power|Mvar", "Reactive Power", "Mvar")
    assert channels["POWER GSU 12UBF"]["display_axis_key"] == "Active Power|MW"
    for name, word in (("R.POWER  GSU 12UBF", 1), ("R.POWER GSU 11UBF", 2)):
        value = next(v for v in spec.values if v.name == name)
        wave = client.get(f"{URL}/{body['source_id']}/waveform", params={"channel_name": name}).json()
        raw = spec.samples[:, word].astype(np.uint16).view(np.int16)
        np.testing.assert_allclose(wave["values"], raw * np.float32(value.scale) + np.float32(value.offset), rtol=1e-6)
    # A second record's code-63 channel shares the same axis key.
    other = _upload(client, _reactive_slow_bytes(3)[0], name="JMHE like.ben").json()
    other_channels = client.get(f"{URL}/{other['source_id']}/channels").json()["analog_channels"]
    assert {c["display_axis_key"] for c in other_channels if c["name"].startswith("R.POWER")} == {"Reactive Power|Mvar"}
