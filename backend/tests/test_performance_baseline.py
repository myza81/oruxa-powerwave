"""Correctness tests for the performance-baseline test infrastructure
(Pre-Advanced Foundation Slice F2).

These run as part of normal `pytest tests/` regression -- they are
DELIBERATELY tiny (tens of KB, sub-second) and verify only that the
synthetic fixture generators and the real import/parse/waveform
pipeline they exercise are correct, never a performance measurement.

The actual 10-100 MB performance BENCHMARK lives in
`tests/perf/baseline_runner.py`, is NOT a pytest test (never
auto-collected here), and is run explicitly:

    cd backend
    python tests/perf/baseline_runner.py run --scenario medium_comtrade
    python tests/perf/baseline_runner.py run --scenario large_comtrade
    python tests/perf/baseline_runner.py run --scenario csv_medium

See docs/development/PERFORMANCE_BASELINE.md for the full reproduction
command, methodology, and the current recorded baseline numbers.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

sys.path.insert(0, str(Path(__file__).resolve().parent / "perf"))
from mem_probe import memory_metric_label, peak_bytes  # noqa: E402
from synthetic_comtrade import generate_comtrade_fixture  # noqa: E402
from synthetic_csv import generate_csv_fixture  # noqa: E402


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


class TestMemProbe:
    """Sanity-only -- the exact numeric value is platform-dependent and
    is never asserted against a threshold here (see
    docs/development/PERFORMANCE_BASELINE.md for why)."""

    def test_peak_bytes_returns_a_positive_integer(self):
        value = peak_bytes()
        assert isinstance(value, int)
        assert value > 0

    def test_memory_metric_label_is_a_nonempty_string(self):
        assert isinstance(memory_metric_label(), str)
        assert memory_metric_label()


class TestSyntheticComtradeFixtureGenerator:
    def test_generated_fixture_is_deterministic(self, tmp_path):
        info_a = generate_comtrade_fixture(
            tmp_path / "a", n_analog=6, n_digital=17, sample_rate_hz=1000.0,
            target_size_bytes=50_000,
        )
        info_b = generate_comtrade_fixture(
            tmp_path / "b", n_analog=6, n_digital=17, sample_rate_hz=1000.0,
            target_size_bytes=50_000,
        )
        assert info_a.dat_path.read_bytes() == info_b.dat_path.read_bytes()
        assert info_a.cfg_path.read_text() == info_b.cfg_path.read_text()
        assert info_a.n_samples == info_b.n_samples

    def test_row_count_derived_from_target_size(self, tmp_path):
        info = generate_comtrade_fixture(
            tmp_path, n_analog=4, n_digital=8, sample_rate_hz=1000.0,
            target_size_bytes=18_000,
        )
        # row_size = 8 + 2*4 + 2*ceil(8/16) = 8 + 8 + 2 = 18
        assert info.row_size_bytes == 18
        assert info.n_samples == 1000
        assert info.dat_size_bytes == 18_000

    def test_real_provider_parses_the_generated_fixture(self, tmp_path):
        """Round-trips the generated CFG/DAT through the REAL
        `ComtradeProvider` (not the HTTP layer) -- the most direct proof
        the generator's binary row layout matches the parser's own."""
        from app.providers.comtrade import ComtradeProvider

        info = generate_comtrade_fixture(
            tmp_path, n_analog=10, n_digital=20, sample_rate_hz=2000.0,
            target_size_bytes=100_000,
        )
        record = ComtradeProvider().load(info.cfg_path)
        assert len(record.analog_channels) == 10
        assert len(record.digital_channels) == 20
        assert record.sample_count() == info.n_samples
        assert record.waveform_data[info.analog_channel_names[0]].notna().all()


class TestSyntheticCsvFixtureGenerator:
    def test_generated_fixture_is_deterministic(self, tmp_path):
        info_a = generate_csv_fixture(
            tmp_path / "a", n_channels=5, sample_rate_hz=100.0, target_size_bytes=20_000,
        )
        info_b = generate_csv_fixture(
            tmp_path / "b", n_channels=5, sample_rate_hz=100.0, target_size_bytes=20_000,
        )
        assert info_a.csv_path.read_bytes() == info_b.csv_path.read_bytes()

    def test_row_count_targets_the_requested_size(self, tmp_path):
        info = generate_csv_fixture(
            tmp_path, n_channels=3, sample_rate_hz=100.0, target_size_bytes=5_000,
        )
        assert info.n_rows > 0
        assert info.size_bytes <= 5_000


class TestBaselinePipelineCorrectnessComtrade:
    """One small, fast, real end-to-end pass through the exact same
    upload -> import -> waveform pipeline `baseline_runner.py`'s
    `measure-comtrade` command uses at 10-100 MB scale -- here at a few
    tens of KB, so it runs in normal regression."""

    def test_import_and_waveform_round_trip(self, client, tmp_path):
        info = generate_comtrade_fixture(
            tmp_path, n_analog=8, n_digital=16, sample_rate_hz=1000.0,
            target_size_bytes=200_000,
        )
        resp = client.post(
            "/api/v1/workspaces/ws-perfbase-comtrade/sources",
            files={
                "cfg_file": ("event.cfg", io.BytesIO(info.cfg_path.read_bytes()), "application/octet-stream"),
                "dat_file": ("event.dat", io.BytesIO(info.dat_path.read_bytes()), "application/octet-stream"),
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["analog_channel_count"] == 8
        assert body["digital_channel_count"] == 16
        assert body["sample_count"] == info.n_samples

        waveform_resp = client.get(
            f"/api/v1/workspaces/ws-perfbase-comtrade/sources/{body['source_id']}/waveform",
            params={"channel_name": info.analog_channel_names[0]},
        )
        assert waveform_resp.status_code == 200
        waveform_body = waveform_resp.json()
        assert waveform_body["returned_point_count"] > 0
        assert len(waveform_body["time"]) == waveform_body["returned_point_count"]
        assert len(waveform_body["values"]) == waveform_body["returned_point_count"]
        assert len(waveform_resp.content) > 0


class TestBaselinePipelineCorrectnessCsv:
    def test_upload_configure_convert_and_waveform_round_trip(self, client, tmp_path):
        info = generate_csv_fixture(
            tmp_path, n_channels=4, sample_rate_hz=50.0, target_size_bytes=10_000,
        )
        upload_resp = client.post(
            "/api/v1/workspaces/ws-perfbase-csv/preparation-sources",
            files={"csv_file": ("event.csv", io.BytesIO(info.csv_path.read_bytes()), "text/csv")},
        )
        assert upload_resp.status_code == 201, upload_resp.text
        prep_source_id = upload_resp.json()["source_id"]

        role_resp = client.put(
            f"/api/v1/workspaces/ws-perfbase-csv/preparation-sources/{prep_source_id}/working/columns/0/role",
            json={"role": "time_axis"},
        )
        assert role_resp.status_code == 200
        for col in range(1, info.n_channels + 1):
            role_resp = client.put(
                f"/api/v1/workspaces/ws-perfbase-csv/preparation-sources/{prep_source_id}/working/columns/{col}/role",
                json={"role": "waveform"},
            )
            assert role_resp.status_code == 200

        time_axis_resp = client.put(
            f"/api/v1/workspaces/ws-perfbase-csv/preparation-sources/{prep_source_id}/working/time-axis",
            json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
        )
        assert time_axis_resp.status_code == 200

        convert_resp = client.post(
            f"/api/v1/workspaces/ws-perfbase-csv/preparation-sources/{prep_source_id}/convert"
        )
        assert convert_resp.status_code in (200, 201), convert_resp.text
        source_id = convert_resp.json()["source_id"]

        channels_resp = client.get(f"/api/v1/workspaces/ws-perfbase-csv/sources/{source_id}/channels")
        assert channels_resp.status_code == 200
        analog_channels = channels_resp.json()["analog_channels"]
        assert len(analog_channels) == info.n_channels

        waveform_resp = client.get(
            f"/api/v1/workspaces/ws-perfbase-csv/sources/{source_id}/waveform",
            params={"channel_name": analog_channels[0]["name"]},
        )
        assert waveform_resp.status_code == 200
        waveform_body = waveform_resp.json()
        assert waveform_body["returned_point_count"] > 0
        assert len(waveform_resp.content) > 0
