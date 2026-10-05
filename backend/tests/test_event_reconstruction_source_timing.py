"""Per-source Event Reconstruction timing metadata (DEC-127 Slice 3B, on
the record model of DEC-128).

    reconstruction_x_s = source_elapsed_s + total_reconstruction_offset_s
    total_reconstruction_offset_s = within_record_offset_s + reconstruction_record_offset_s

Every record today has exactly one source, so `within_record_offset_s` is
0. Absolute time enters exactly once (the record's recorded-start
difference to the reference, inside `reconstruction_record_offset_s`), and
Waveform Synchronise Sources corrections never contribute."""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.event_reconstruction import total_reconstruction_offset_s
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.main import create_app
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.event_reconstruction_service import (
    get_reconstruction,
    set_member_correction,
    set_reconstruction_definition,
    set_reconstruction_reference,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import set_source_alignment_offset
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-er-timing"
T0 = datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc)
THRESHOLD_S = 3600.0


def _source(source_id: str, *, start: datetime | None = T0, duration_s: float = 1.0, rate_hz: float = 20.0) -> ActiveSource:
    n = int(round(duration_s * rate_hz)) + 1
    time = np.linspace(0.0, duration_s, n)
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": time, "VA": np.zeros(n)}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=start, trigger_time=start),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=T0,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=start, trigger_time=start,
        sample_count=n, duration_seconds=duration_s,
        elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(rate_hz,), samples_per_rate=(n,),
        analog_channels=[AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


class _Ctx:
    def __init__(self, *sources: ActiveSource):
        self.sources = WorkspaceRegistry()
        self.sync = SynchronizationRegistry()
        self.er = EventReconstructionRegistry()
        for source in sources:
            self.sources.add(source)

    def kw(self):
        return {"workspace_id": WS, "registry": self.er, "source_registry": self.sources, "large_gap_threshold_s": THRESHOLD_S}

    def define(self, record_ids, reference):
        return set_reconstruction_definition(record_ids=list(record_ids), reference_record_id=reference, **self.kw())

    def view(self):
        return get_reconstruction(**self.kw())

    def timings(self, view=None):
        view = view or self.view()
        return {t.source_id: t for m in view.members for t in (m.source_timings or [])}


REF_ORIGIN = T0 + timedelta(seconds=5)
ALL = ["R", "R2", "A", "A2"]


@pytest.fixture
def ctx() -> _Ctx:
    # R and R2 overlap (one Waveform Time Group), as do A and A2; for Event
    # Reconstruction all four are independent records.
    return _Ctx(
        _source("R", start=REF_ORIGIN),
        _source("R2", start=REF_ORIGIN + timedelta(seconds=0.4)),
        _source("A", start=T0),
        _source("A2", start=T0 + timedelta(seconds=0.3), duration_s=1.2),
    )


def test_domain_total_is_the_sum_of_the_two_components():
    assert total_reconstruction_offset_s(within_record_offset_s=0.4, reconstruction_record_offset_s=-5.0) == pytest.approx(-4.6, abs=1e-15)
    assert total_reconstruction_offset_s(within_record_offset_s=0.0, reconstruction_record_offset_s=0.0) == 0.0


class TestComponents:
    def test_each_record_reports_exactly_its_own_source(self, ctx):
        view = ctx.define(ALL, "R")
        assert [[t.source_id for t in m.source_timings] for m in view.members] == [["R"], ["R2"], ["A"], ["A2"]]

    def test_component_semantics_and_mapped_extents(self, ctx):
        t = ctx.timings(ctx.define(ALL, "R"))
        expected = {
            # source: (reconstruction_record_offset_s, duration)
            "R": (0.0, 1.0),
            "R2": (0.4, 1.0),
            "A": (-5.0, 1.0),
            "A2": (-4.7, 1.2),
        }
        for sid, (record_offset, duration) in expected.items():
            assert t[sid].within_record_offset_s == 0.0
            assert t[sid].reconstruction_record_offset_s == pytest.approx(record_offset, abs=1e-12)
            assert t[sid].total_reconstruction_offset_s == t[sid].within_record_offset_s + t[sid].reconstruction_record_offset_s
            assert t[sid].reconstruction_start_s == pytest.approx(record_offset, abs=1e-12)
            assert t[sid].reconstruction_end_s == pytest.approx(record_offset + duration, abs=1e-12)

    def test_record_offset_equals_the_member_reconstruction_offset(self, ctx):
        view = ctx.define(ALL, "R")
        for member in view.members:
            [timing] = member.source_timings
            assert timing.reconstruction_record_offset_s == member.reconstruction_offset_s
            assert (timing.reconstruction_start_s, timing.reconstruction_end_s) == (member.start_s, member.end_s)

    def test_zero_corrections_reproduce_recorded_absolute_time_exactly_once(self, ctx):
        t = ctx.timings(ctx.define(ALL, "R"))
        for active in ctx.sources.list_for_workspace(WS):
            # x(elapsed 0) is the source's recorded start, relative to the reference origin.
            expected = (active.metadata.start_time - REF_ORIGIN).total_seconds()
            assert t[active.metadata.source_id].total_reconstruction_offset_s == pytest.approx(expected, abs=1e-9)


class TestEachLayerContributesOnce:
    def test_waveform_synchronise_sources_never_contributes(self, ctx):
        before = ctx.timings(ctx.define(ALL, "R"))
        set_source_alignment_offset(workspace_id=WS, source_id="A2", alignment_offset_s=0.002, registry=ctx.sync, source_registry=ctx.sources)
        assert ctx.timings() == before

    def test_event_reconstruction_correction_moves_only_its_record(self, ctx):
        before = ctx.timings(ctx.define(ALL, "R"))
        set_member_correction(record_id="A2", correction_s=0.0125, **ctx.kw())
        after = ctx.timings()
        assert after["A2"].within_record_offset_s == 0.0
        assert after["A2"].total_reconstruction_offset_s - before["A2"].total_reconstruction_offset_s == pytest.approx(0.0125, abs=1e-12)
        for sid in ("R", "R2", "A"):
            assert after[sid].total_reconstruction_offset_s == before[sid].total_reconstruction_offset_s

    def test_reference_switch_rebases_but_keeps_pairwise_spacing(self, ctx):
        ctx.define(ALL, "R")
        set_member_correction(record_id="R", correction_s=0.0007, **ctx.kw())
        from_r = ctx.timings()
        from_a = ctx.timings(set_reconstruction_reference(record_id="A", **ctx.kw()))
        shift = from_a["R"].total_reconstruction_offset_s - from_r["R"].total_reconstruction_offset_s
        assert shift == pytest.approx(5.0007, abs=1e-9)
        for sid in ("R2", "A", "A2"):
            assert from_a[sid].total_reconstruction_offset_s - from_r[sid].total_reconstruction_offset_s == pytest.approx(shift, abs=1e-9)
        assert from_a["A"].total_reconstruction_offset_s == pytest.approx(0.0, abs=1e-12)


class TestPrecision:
    """5 kHz spacing, sub-millisecond correction, multi-hour placement."""

    @pytest.fixture
    def far(self):
        ctx = _Ctx(_source("REF", start=T0), _source("FAST", start=T0 + timedelta(hours=2), duration_s=0.2, rate_hz=5000.0))
        ctx.define(["REF", "FAST"], "REF")
        set_member_correction(record_id="FAST", correction_s=0.000123, **ctx.kw())
        return ctx

    def test_multi_hour_offset_keeps_sub_millisecond_correction(self, far):
        fast = far.timings()["FAST"]
        assert fast.total_reconstruction_offset_s == pytest.approx(7200.000123, abs=1e-9)
        assert fast.reconstruction_end_s - fast.reconstruction_start_s == pytest.approx(0.2, abs=1e-9)

    def test_mapped_5khz_samples_keep_their_spacing_in_float64(self, far):
        total = far.timings()["FAST"].total_reconstruction_offset_s
        elapsed = np.arange(1001) * 0.0002
        mapped = elapsed + total
        assert np.allclose(np.diff(mapped), 0.0002, rtol=0, atol=1e-9)
        assert np.allclose(mapped - total, elapsed, rtol=0, atol=1e-9)

    def test_float32_risk_fixture_for_slice_3c_uat(self, far):
        """Documents the WebGL precision concern (DEC-127 / design doc):
        reduced-precision (float32) storage of multi-hour reconstruction X
        values cannot resolve 5 kHz spacing, while a numerically local
        origin can. Slice 3C must check this in UAT; the mapping itself is
        exact in float64."""
        total = far.timings()["FAST"].total_reconstruction_offset_s
        elapsed = np.arange(1001) * 0.0002
        far_float32 = (elapsed + total).astype(np.float32).astype(np.float64)
        spacing_error = np.max(np.abs(np.diff(far_float32) - 0.0002))
        assert spacing_error > 0.0001  # at least half a sample period lost
        local = (elapsed + total) - (elapsed[0] + total)  # local plotting origin
        local_float32 = local.astype(np.float32).astype(np.float64)
        assert np.max(np.abs(np.diff(local_float32) - 0.0002)) < 1e-7


class TestStaleState:
    def test_removed_record_exposes_no_mapping(self, ctx):
        ctx.define(ALL, "R")
        ctx.sources.remove(WS, "A")
        view = ctx.view()
        stale = next(m for m in view.members if m.status == "stale")
        assert stale.record_id == "A" and stale.source_timings is None
        assert all(m.source_timings is not None for m in view.members if m.status == "current")

    def test_overlapping_upload_does_not_withhold_mappings(self, ctx):
        ctx.define(ALL, "R")
        ctx.sources.add(_source("R3", start=REF_ORIGIN + timedelta(seconds=0.9)))  # joins R's Waveform Time Group
        view = ctx.view()
        assert view.placements_available is True
        assert all(m.source_timings is not None for m in view.members)

    def test_removed_reference_withholds_every_mapping(self, ctx):
        ctx.define(ALL, "R")
        ctx.sources.remove(WS, "R")
        view = ctx.view()
        assert view.placements_available is False
        assert all(m.source_timings is None for m in view.members)


# ---- API -------------------------------------------------------------------------

FIXTURE_START = datetime(2026, 3, 6, 10, 0, 0)
_STAMP = re.compile(rb"^\d{2}/\d{2}/\d{4},\d{2}:\d{2}:\d{2}\.\d{6}(\r?)$", re.MULTILINE)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload(client, ws, fixtures, offset_s):
    stamps = iter([FIXTURE_START + timedelta(seconds=offset_s), FIXTURE_START + timedelta(seconds=offset_s + 0.005)])
    cfg = _STAMP.sub(lambda m: next(stamps).strftime("%d/%m/%Y,%H:%M:%S.%f").encode() + m.group(1), (fixtures / "synth_ascii.cfg").read_bytes(), count=2)
    files = {
        "cfg_file": ("s.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("s.dat", io.BytesIO((fixtures / "synth_ascii.dat").read_bytes()), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{ws}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def test_api_exposes_additive_source_timings_and_calculated_parent(client, comtrade_fixtures_dir):
    ws = "ws-er-timing-api"
    a = _upload(client, ws, comtrade_fixtures_dir, 0.0)
    b = _upload(client, ws, comtrade_fixtures_dir, 10.0)
    twin = _upload(client, ws, comtrade_fixtures_dir, 10.0)  # identical timestamps to b
    calc = client.post(f"/api/v1/workspaces/{ws}/calculated-channels", json={
        "name": "-VA", "operation": "reverse_polarity", "inputs": [{"kind": "source", "source_id": a, "channel_name": "VA"}], "parameters": {},
    })
    assert calc.status_code == 201, calc.text
    body = client.put(
        f"/api/v1/workspaces/{ws}/event-reconstruction/definition",
        json={"record_ids": [a, b, twin], "reference_record_id": a},
    ).json()
    members = {m["record_id"]: m for m in body["members"]}
    for key in ("record_id", "source_ids", "reconstruction_offset_s", "start_s", "end_s", "correction_s", "status"):
        assert key in members[a]
    timing_b = members[b]["source_timings"][0]
    assert set(timing_b) == {
        "source_id", "within_record_offset_s", "reconstruction_record_offset_s",
        "total_reconstruction_offset_s", "reconstruction_start_s", "reconstruction_end_s",
    }
    assert timing_b["within_record_offset_s"] == 0.0
    assert timing_b["total_reconstruction_offset_s"] == pytest.approx(10.0, abs=1e-9)
    assert timing_b["total_reconstruction_offset_s"] == timing_b["within_record_offset_s"] + timing_b["reconstruction_record_offset_s"]
    # The identical-timestamp twin is its own member with its own single timing.
    assert [t["source_id"] for t in members[twin]["source_timings"]] == [twin]
    assert members[twin]["source_timings"][0]["total_reconstruction_offset_s"] == timing_b["total_reconstruction_offset_s"]
    # A calculated channel has no timing of its own: its parent's entry applies.
    parent = calc.json()["reference_source_id"]
    assert parent == a
    assert [t["source_id"] for t in members[a]["source_timings"]] == [a]

    # A removed record exposes no mapping.
    assert client.delete(f"/api/v1/workspaces/{ws}/sources/{twin}").status_code == 204
    body = client.get(f"/api/v1/workspaces/{ws}/event-reconstruction/definition").json()
    stale = next(m for m in body["members"] if m["status"] == "stale")
    assert stale["record_id"] == twin and stale["source_timings"] is None
