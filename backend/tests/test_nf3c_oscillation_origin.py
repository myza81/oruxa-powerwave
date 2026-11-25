"""NF-3C -- oscillation representation: the frequency, its NF-1 origin and the revision come from the central accessor (O-6, option A).

`nominal_frequency_origin` is one of five machine-readable values: `recording_metadata`, `import_supplied` (a BEN upload's value),
`assumed_default`, `manual` (only while the server-side release gate is open) and `unusable`. `nominal_frequency_revision` is additive.
The reported frequency, the status and the reason codes are unchanged for every recording class; the historical-versus-new outputs are
compared in the baseline modules through `nf3c_approved_changes.py`. Not changed here (deferred, and not claimed as verified): the
first-member cross-recording rule (NF-3G) and the staleness of stored calculated channels (NF-3E).
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.calculated_channel import OP_ACTIVE_POWER, ChannelRef
from app.main import create_app
from app.services import oscillation_representation_service as rep
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests import nf3b_baseline_scenarios as scn
from tests import nf3c_baseline_scenarios as scn3c
from tests.nf3c_access_support import access_for

WS = scn.WS
COMTRADE = {"source_format": "COMTRADE"}
ASSUMED = {"source_format": "COMTRADE", "nominal_frequency_assumed": True}
BEN = {"source_format": "BEN", "nominal_frequency_assumed": False}
BEN_FIXTURE = Path(__file__).parent / "fixtures" / "ben" / "synthetic_fast.ben"


def setup(nominal, provenance=COMTRADE, *, enabled=False, manual=None, f_sig=50.0):
    sources, calcs = WorkspaceRegistry(), CalculatedChannelRegistry()
    sources.add(scn.build_source("src", nominal, provenance, f_sig))
    store = NominalFrequencyRegistry()
    if manual is not None:
        store.set(WS, "src", manual, datetime(2026, 11, 26, tzinfo=timezone.utc))
    return sources, calcs, access_for(sources, manual_override_enabled=enabled, registry=store), store


def derive(sources, calcs, access, channel="IA"):
    return rep.derive_analysis_representation(
        workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src", channel_name=channel), representation="rms_magnitude",
        source_registry=sources, calc_registry=calcs, frequency_access=access)


class TestOriginAndRevision:
    @pytest.mark.parametrize("nominal,prov,origin", [
        (50.0, COMTRADE, "recording_metadata"), (60.0, COMTRADE, "recording_metadata"), (50.0, ASSUMED, "assumed_default"),
        (60.0, BEN, "import_supplied"), (50.0, BEN, "import_supplied"),
    ])
    def test_the_origin_is_the_authoritys_and_the_revision_is_zero_without_an_engineer_value(self, nominal, prov, origin):
        r = derive(*setup(nominal, prov, f_sig=nominal)[:3])
        assert (r.status, r.nominal_frequency_origin, r.nominal_frequency_revision) == ("ready", origin, 0)
        assert r.nominal_frequency_hz == (50.0 if prov is ASSUMED else nominal)

    @pytest.mark.parametrize("bad", [0.0, -50.0, float("nan"), float("inf"), 0.5, 1001.0])
    def test_an_unusable_declaration_is_unavailable_with_origin_unusable_and_never_reaches_the_numerics(self, bad, monkeypatch):
        def must_not_run(*a, **k):
            raise AssertionError("an unusable nominal frequency reached a numerical routine")
        monkeypatch.setattr(rep, "derive_rms_magnitude", must_not_run)
        monkeypatch.setattr(rep, "check_rms_eligibility", must_not_run)
        monkeypatch.setattr(rep, "representation_unavailable_reason", must_not_run)
        r = derive(*setup(bad)[:3])
        assert (r.status, r.reason_code, r.nominal_frequency_origin, r.derived) == ("unavailable", "invalid_nominal_frequency", "unusable", None)
        assert (math.isnan(r.nominal_frequency_hz) if math.isnan(bad) else r.nominal_frequency_hz == bad)        # the declared value, as before

    def test_manual_is_the_effective_frequency_with_origin_manual_and_a_revision(self):
        r = derive(*setup(50.0, enabled=True, manual=60.0, f_sig=60.0)[:3])
        assert (r.status, r.nominal_frequency_hz, r.nominal_frequency_origin, r.nominal_frequency_revision) == ("ready", 60.0, "manual", 1)
        assert r.derived.nominal_frequency_hz == 60.0 and r.derived.window_s == pytest.approx(1.0 / 60.0)

    def test_manual_makes_an_unusable_recording_ready(self):
        r = derive(*setup(0.0, enabled=True, manual=50.0)[:3])
        assert (r.status, r.nominal_frequency_hz, r.nominal_frequency_origin) == ("ready", 50.0, "manual")

    def test_a_stored_value_is_ignored_while_the_gate_is_closed(self):
        r = derive(*setup(50.0, enabled=False, manual=60.0)[:3])
        assert (r.nominal_frequency_hz, r.nominal_frequency_origin, r.nominal_frequency_revision) == (50.0, "recording_metadata", 1)
        # the revision is the registry's (it did change), but the value and origin are Auto: nothing from the engineer reached the result

    def test_the_revision_moves_when_the_setting_changes_and_returns_to_auto_with_reset(self):
        sources, calcs, access, _ = setup(50.0, enabled=True)
        assert derive(sources, calcs, access).nominal_frequency_revision == 0
        access.set_manual(WS, "src", 60.0)
        assert derive(sources, calcs, access).nominal_frequency_revision == 1
        access.set_manual(WS, "src", 40.0)
        assert derive(sources, calcs, access).nominal_frequency_revision == 2
        access.reset_to_auto(WS, "src")
        r = derive(sources, calcs, access)
        assert (r.nominal_frequency_hz, r.nominal_frequency_origin, r.nominal_frequency_revision) == (50.0, "recording_metadata", 3)

    def test_a_calculated_channel_uses_the_frequency_of_the_recording_that_grounds_it(self):
        sources, calcs, access, _ = setup(50.0, enabled=True)
        access.set_manual(WS, "src", 60.0)
        channel = create_calculated_channel(
            workspace_id=WS, name="P", operation=OP_ACTIVE_POWER, parameters={}, source_registry=sources, calc_registry=calcs,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="VA"), ChannelRef(kind="source", source_id="src", channel_name="IA")])
        r = rep.derive_analysis_representation(
            workspace_id=WS, input_ref=ChannelRef(kind="calculated", calculated_channel_id=channel.id), representation="rms_magnitude",
            source_registry=sources, calc_registry=calcs, frequency_access=access)
        assert r.nominal_frequency_origin == "manual" and r.nominal_frequency_hz == 60.0     # (the channel is a power: unavailable by type, origin still reported)

    def test_describe_exposes_origin_and_revision(self):
        out = rep.describe(derive(*setup(50.0, enabled=True, manual=60.0)[:3]))
        assert (out["nominal_frequency_origin"], out["nominal_frequency_revision"], out["nominal_frequency_hz"]) == ("manual", 1, 60.0)

    def test_the_constants_are_the_nf1_vocabulary(self):
        assert {rep.NOMINAL_FREQUENCY_RECORDING_METADATA, rep.NOMINAL_FREQUENCY_IMPORT_SUPPLIED, rep.NOMINAL_FREQUENCY_ASSUMED_DEFAULT,
                rep.NOMINAL_FREQUENCY_MANUAL, rep.NOMINAL_FREQUENCY_UNUSABLE} == {
            "recording_metadata", "import_supplied", "assumed_default", "manual", "unusable"}


# ------------------------------------------------------------------------------------------------------------- over HTTP
def _settings(tmp_path, enabled):
    return Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=("http://localhost:8101",),
                    database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local", nominal_frequency_manual_override_enabled=enabled)


@pytest.fixture
def opened(tmp_path):
    with TestClient(create_app(_settings(tmp_path, True)), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def closed(tmp_path):
    with TestClient(create_app(_settings(tmp_path, False)), raise_server_exceptions=False) as c:
        yield c


def representation(client, ws, sid, channel="ALPHA1_IA"):
    r = client.post(f"/api/v1/workspaces/{ws}/oscillation-analysis/representation",
                    json={"input": {"kind": "source", "source_id": sid, "channel_name": channel}, "representation": "rms_magnitude"})
    assert r.status_code == 200, r.text
    return r.json()


def nf(ws, sid):
    return f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency"


class TestOverHttp:
    def test_manual_changes_the_reported_frequency_origin_and_revision_and_auto_restores_them(self, opened):
        ws = "ws-osc-1"
        sid = scn3c._upload(opened, ws, "a", 5000.0, 60.0, "60")
        before = representation(opened, ws, sid)
        assert (before["nominal_frequency_hz"], before["nominal_frequency_origin"], before["nominal_frequency_revision"]) == (60.0, "recording_metadata", 0)
        opened.put(nf(ws, sid), json={"mode": "manual", "value_hz": 50})
        after = representation(opened, ws, sid)
        assert (after["nominal_frequency_hz"], after["nominal_frequency_origin"], after["nominal_frequency_revision"]) == (50.0, "manual", 1)
        opened.put(nf(ws, sid), json={"mode": "auto"})
        back = representation(opened, ws, sid)
        assert (back["nominal_frequency_hz"], back["nominal_frequency_origin"], back["nominal_frequency_revision"]) == (60.0, "recording_metadata", 2)

    def test_manual_corrects_an_unusable_recording_over_http(self, opened):
        ws = "ws-osc-2"
        sid = scn3c._upload(opened, ws, "z", 5000.0, 50.0, "0")
        assert representation(opened, ws, sid)["status"] == "unavailable"
        opened.put(nf(ws, sid), json={"mode": "manual", "value_hz": 50})
        r = representation(opened, ws, sid)
        assert (r["status"], r["nominal_frequency_origin"]) == ("ready", "manual")

    def test_the_closed_gate_keeps_every_response_on_auto(self, closed):
        ws = "ws-osc-3"
        sid = scn3c._upload(closed, ws, "a", 5000.0, 50.0, "50")
        assert closed.put(nf(ws, sid), json={"mode": "manual", "value_hz": 60}).status_code == 409
        closed.app.state.nominal_frequency_registry.set(ws, sid, 60.0, datetime(2026, 11, 26, tzinfo=timezone.utc))       # stored behind the API
        r = representation(closed, ws, sid)
        assert (r["nominal_frequency_hz"], r["nominal_frequency_origin"]) == (50.0, "recording_metadata")

    @pytest.mark.parametrize("value,expected", [("60", "import_supplied"), ("50", "import_supplied"), (None, "assumed_default")])
    def test_a_real_ben_upload_reports_its_authoritative_origin(self, opened, value, expected):
        ws = f"ws-osc-ben-{value}"
        r = opened.post(f"/api/v1/workspaces/{ws}/sources", files={"ben_file": ("r.ben", io.BytesIO(BEN_FIXTURE.read_bytes()), "application/octet-stream")},
                        data={} if value is None else {"nominal_frequency_hz": value})
        assert r.status_code == 201
        sid = r.json()["source_id"]
        name = opened.get(f"/api/v1/workspaces/{ws}/sources/{sid}/channels").json()["analog_channels"][0]["name"]
        body = representation(opened, ws, sid, name)
        assert body["nominal_frequency_origin"] == expected and body["nominal_frequency_revision"] == 0

    def test_the_spectrum_carries_origin_and_revision_and_warns_only_for_an_assumed_default(self, opened):
        def spectrum(ws, sid):
            r = opened.post(f"/api/v1/workspaces/{ws}/oscillation-analysis/spectrum", json={
                "input": {"kind": "source", "source_id": sid, "channel_name": "ALPHA1_VA"}, "representation": "rms_magnitude",
                "window_start_s": 0.1, "window_end_s": 0.9, "frequency_min_hz": 1.0, "frequency_max_hz": 20.0})
            assert r.status_code == 200, r.text
            return r.json()
        sid = scn3c._upload(opened, "ws-osc-4", "a", 5000.0, 50.0, "abc")                       # assumed 50 Hz
        body = spectrum("ws-osc-4", sid)
        block = body["representation"]
        assert (block["nominal_frequency_hz"], block["nominal_frequency_origin"], block["nominal_frequency_revision"]) == (50.0, "assumed_default", 0)
        assert "nominal_frequency_assumed" in {w["code"] for w in body["warnings"]}
        opened.put(nf("ws-osc-4", sid), json={"mode": "manual", "value_hz": 50})
        body = spectrum("ws-osc-4", sid)
        block = body["representation"]
        assert (block["nominal_frequency_origin"], block["nominal_frequency_revision"]) == ("manual", 1)
        assert "nominal_frequency_assumed" not in {w["code"] for w in body["warnings"]}          # an engineer's value is not an assumption

    def test_source_deletion_and_workspace_reset_return_the_oscillation_responses_to_auto(self, opened):
        ws = "ws-osc-5"
        sid = scn3c._upload(opened, ws, "a", 5000.0, 50.0, "50")
        opened.put(nf(ws, sid), json={"mode": "manual", "value_hz": 60})
        assert representation(opened, ws, sid)["nominal_frequency_origin"] == "manual"
        assert opened.delete(f"/api/v1/workspaces/{ws}/sources/{sid}").status_code in (200, 204)
        sid2 = scn3c._upload(opened, ws, "a", 5000.0, 50.0, "50")
        assert representation(opened, ws, sid2)["nominal_frequency_origin"] == "recording_metadata"
        opened.put(nf(ws, sid2), json={"mode": "manual", "value_hz": 60})
        assert opened.delete(f"/api/v1/workspaces/{ws}").status_code in (200, 204)
        assert opened.app.state.nominal_frequency_registry.count() == 0
