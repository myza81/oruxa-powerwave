"""NF-3C -- the validating consumers ask the central accessor and never hand an unusable frequency to a numerical routine.

Scope: event detection / synchronization (C-03), compliance measurement (C-05) and compliance readiness (C-04). Oscillation is in
`test_nf3c_oscillation_origin.py`. Algorithms and waveform data are untouched; only WHERE the frequency comes from and what happens when
it is unusable changed. The historical-versus-new outputs are compared in the two baseline modules through `nf3c_approved_changes.py`.

States exercised everywhere: valid declared, assumed, unusable (0, negative, NaN, infinity, out of range), Manual with the server gate
open, a Manual value present while the gate is closed, and removal/reset.
"""

from __future__ import annotations

import dataclasses
import math
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.calculated_channel import OP_ACTIVE_POWER, ChannelRef
from app.domain.channel_classification import WAVEFORM_FORM_INSTANTANEOUS
from app.domain.event_detection import detect_event_onset
from app.main import create_app
from app.services import compliance_measurement_service as measurement
from app.services import synchronization_service as sync
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.compliance_readiness_service import (
    STATE_BLOCKED, STATE_NEEDS_RMS, _Context, _nominal_frequency_for, _rms_step_or_state,
)
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests import nf3b_baseline_scenarios as scn
from tests import nf3c_baseline_scenarios as scn3c
from tests.nf3c_access_support import access_for

WS = scn.WS
COMTRADE = {"source_format": "COMTRADE"}
ASSUMED = {"source_format": "COMTRADE", "nominal_frequency_assumed": True}
UNUSABLE = [0.0, -50.0, float("nan"), float("inf"), float("-inf"), 0.5, 1001.0]


def step_source(nominal, provenance=COMTRADE, *, trusted_form: bool = False):
    """A recording whose current doubles at t = 1 s (so a working detector finds an onset), declared `nominal`."""
    source = scn.build_source("src", nominal, provenance, 50.0, fs=4800.0, seconds=2.0)
    t = source.record.waveform_data["time"].to_numpy()
    source.record.waveform_data["IA"] = np.where(t < 1.0, 1e3, 2e3) * np.cos(2 * np.pi * 50.0 * t)
    if trusted_form:
        channels = [dataclasses.replace(c, waveform_form=WAVEFORM_FORM_INSTANTANEOUS) for c in source.metadata.analog_channels]
        source = dataclasses.replace(source, metadata=dataclasses.replace(source.metadata, analog_channels=channels))
    return source


def registries(source, *, enabled: bool = False, manual: float | None = None):
    sources = WorkspaceRegistry()
    sources.add(source)
    store = NominalFrequencyRegistry()
    access = access_for(sources, manual_override_enabled=enabled, registry=store)
    if manual is not None:
        from datetime import datetime, timezone
        store.set(WS, "src", manual, datetime(2026, 11, 26, tzinfo=timezone.utc))
    return sources, access


def detect(sources, access, **kwargs):
    return sync.detect_event_candidate(
        workspace_id=WS, source_id="src", channel_name="IA", sensitivity="normal", search_start_time=kwargs.get("start"),
        search_end_time=kwargs.get("end"), source_registry=sources, synchronization_registry=SynchronizationRegistry(), frequency_access=access)


# ------------------------------------------------------------------------------------------------- event detection (C-03)
class TestEventDetection:
    @pytest.mark.parametrize("nominal,prov", [(50.0, COMTRADE), (60.0, COMTRADE), (50.0, ASSUMED)])
    def test_usable_recordings_are_detected_and_echo_the_effective_value(self, nominal, prov):
        sources, access = registries(step_source(nominal, prov))
        view = detect(sources, access)
        assert view.found is True and view.nominal_frequency_hz == nominal

    @pytest.mark.parametrize("bad", UNUSABLE)
    def test_an_unusable_declaration_is_refused_before_the_detector_with_the_existing_sentence(self, bad, monkeypatch):
        def must_not_run(*a, **k):
            raise AssertionError("an unusable nominal frequency reached the detector")
        monkeypatch.setattr(sync, "detect_event_onset", must_not_run)
        sources, access = registries(step_source(bad))
        view = detect(sources, access)
        assert view.found is False and view.reason == sync.NO_USABLE_NOMINAL_FREQUENCY_REASON
        assert view.detector_method == "rms_sustained_change"
        # O-7 option A: the declared value is echoed as before (NaN stays NaN here; the wire turns it into null: a documented defect)
        assert (math.isnan(view.nominal_frequency_hz) if math.isnan(bad) else view.nominal_frequency_hz == bad)

    def test_the_service_sentence_is_the_detectors_own_sentence(self):
        t = np.arange(100) / 1000.0
        assert detect_event_onset(t, np.sin(t), nominal_frequency_hz=0.0).reason == sync.NO_USABLE_NOMINAL_FREQUENCY_REASON

    def test_an_unusable_frequency_is_reported_before_an_empty_window_is(self):
        # Intentional ordering change (NF-3C matrix OC-6 note): previously an empty slice said "No samples available to analyse." first.
        sources, access = registries(step_source(0.0))
        assert detect(sources, access, start=100.0, end=200.0).reason == sync.NO_USABLE_NOMINAL_FREQUENCY_REASON

    def test_manual_makes_an_unusable_recording_detectable_and_is_the_value_the_detector_receives(self, monkeypatch):
        seen = []
        real = sync.detect_event_onset
        monkeypatch.setattr(sync, "detect_event_onset", lambda *a, **k: (seen.append(k["nominal_frequency_hz"]), real(*a, **k))[1])
        sources, access = registries(step_source(0.0), enabled=True, manual=50.0)
        view = detect(sources, access)
        assert view.found is True and view.nominal_frequency_hz == 50.0 and seen == [50.0]

    def test_manual_overrides_a_valid_declaration(self, monkeypatch):
        seen = []
        real = sync.detect_event_onset
        monkeypatch.setattr(sync, "detect_event_onset", lambda *a, **k: (seen.append(k["nominal_frequency_hz"]), real(*a, **k))[1])
        sources, access = registries(step_source(50.0), enabled=True, manual=60.0)
        view = detect(sources, access)
        assert seen == [60.0] and view.nominal_frequency_hz == 60.0

    def test_a_stored_value_is_ignored_while_the_server_gate_is_closed(self, monkeypatch):
        seen = []
        real = sync.detect_event_onset
        monkeypatch.setattr(sync, "detect_event_onset", lambda *a, **k: (seen.append(k["nominal_frequency_hz"]), real(*a, **k))[1])
        sources, access = registries(step_source(50.0), enabled=False, manual=60.0)
        view = detect(sources, access)
        assert seen == [50.0] and view.nominal_frequency_hz == 50.0

    def test_a_missing_recording_is_still_not_found(self):
        from app.services.errors import SourceNotFoundError
        sources, access = registries(step_source(50.0))
        with pytest.raises(SourceNotFoundError):
            sync.detect_event_candidate(
                workspace_id=WS, source_id="ghost", channel_name="IA", sensitivity="normal", search_start_time=None, search_end_time=None,
                source_registry=sources, synchronization_registry=SynchronizationRegistry(), frequency_access=access)


# ------------------------------------------------------------------------------------------ compliance measurement (C-05)
def classify(sources, access):
    return measurement._classify_input_type(
        ChannelRef(kind="source", source_id="src", channel_name="IA"), workspace_id=WS, source_registry=sources, frequency_access=access)


class TestComplianceMeasurementClassifier:
    @pytest.mark.parametrize("nominal,prov", [(50.0, COMTRADE), (60.0, COMTRADE), (50.0, ASSUMED)])
    def test_usable_recordings_are_classified_by_the_detector(self, nominal, prov):
        sources, access = registries(step_source(nominal, prov))
        assert classify(sources, access) == "instantaneous"

    @pytest.mark.parametrize("bad", UNUSABLE)
    def test_an_unusable_declaration_never_reaches_the_detector_and_the_answer_is_do_not_guess(self, bad, monkeypatch):
        def must_not_run(*a, **k):
            raise AssertionError("an unusable nominal frequency reached the form detector")
        monkeypatch.setattr(measurement, "classify_waveform_form", must_not_run)
        sources, access = registries(step_source(bad))
        assert classify(sources, access) is None

    @pytest.mark.parametrize("bad", UNUSABLE)
    def test_trusted_form_metadata_needs_no_frequency(self, bad):
        sources, access = registries(step_source(bad, trusted_form=True))
        assert classify(sources, access) == "instantaneous"

    def test_manual_corrects_an_unusable_recording_and_is_the_frequency_the_detector_receives(self, monkeypatch):
        seen = []
        real = measurement.classify_waveform_form
        monkeypatch.setattr(measurement, "classify_waveform_form", lambda t, v, f: (seen.append(f), real(t, v, f))[1])
        sources, access = registries(step_source(0.0), enabled=True, manual=50.0)
        assert classify(sources, access) == "instantaneous" and seen == [50.0]

    def test_a_stored_value_does_not_rescue_an_unusable_recording_while_the_gate_is_closed(self):
        sources, access = registries(step_source(0.0), enabled=False, manual=50.0)
        assert classify(sources, access) is None


# --------------------------------------------------------------------------------------------- compliance readiness (C-04)
def context(sources, access, calcs=None):
    return _Context(workspace_id=WS, group=MagicMock(), catalogue={}, display=MagicMock(), source_registry=sources,
                    calc_registry=calcs or CalculatedChannelRegistry(), context_registry=MagicMock(), frequency_access=access)


def rms_state(sources, access, calcs=None):
    return _rms_step_or_state(context(sources, access, calcs), "A", ChannelRef(kind="source", source_id="src", channel_name="IA"), label="Ia")


class TestComplianceReadiness:
    @pytest.mark.parametrize("nominal,prov", [(50.0, COMTRADE), (60.0, COMTRADE), (50.0, ASSUMED)])
    def test_a_usable_recording_proposes_an_rms_step_with_the_effective_frequency(self, nominal, prov):
        result = rms_state(*registries(step_source(nominal, prov, trusted_form=True)))
        assert result.state == STATE_NEEDS_RMS and result.step.executable and result.step.nominal_frequency_hz == nominal

    @pytest.mark.parametrize("bad,text", [(0.0, "0"), (-50.0, "-50"), (float("nan"), "nan"), (float("inf"), "inf"), (1001.0, "1001"), (0.5, "0.5")])
    def test_an_unusable_declaration_blocks_the_step_and_says_it_is_unusable_not_unknown(self, bad, text):
        result = rms_state(*registries(step_source(bad, trusted_form=True)))
        assert result.state == STATE_BLOCKED and result.step.executable is False and result.step.nominal_frequency_hz is None
        assert f"declared by this recording ({text}) is not usable" in result.message
        assert "unknown" not in result.message
        assert "Recording Details" not in result.message          # gate closed: Manual is not offered as a remedy

    def test_with_the_gate_open_the_message_offers_the_manual_remedy_without_claiming_anything_about_the_value(self):
        result = rms_state(*registries(step_source(0.0, trusted_form=True), enabled=True))
        assert "Set a nominal frequency in Recording Details" in result.message
        for word in ("measured", "verified", "confirmed"):
            assert word not in result.message

    def test_manual_unblocks_the_step_and_the_step_carries_the_manual_value(self):
        result = rms_state(*registries(step_source(0.0, trusted_form=True), enabled=True, manual=60.0))
        assert result.state == STATE_NEEDS_RMS and result.step.nominal_frequency_hz == 60.0

    def test_a_stored_value_is_ignored_while_the_gate_is_closed(self):
        result = rms_state(*registries(step_source(50.0, trusted_form=True), enabled=False, manual=60.0))
        assert result.step.nominal_frequency_hz == 50.0

    def test_a_calculated_channel_inherits_the_frequency_of_its_grounding_recording(self):
        sources, access = registries(step_source(50.0), enabled=True, manual=60.0)
        calcs = CalculatedChannelRegistry()
        channel = create_calculated_channel(
            workspace_id=WS, name="P", operation=OP_ACTIVE_POWER, parameters={}, source_registry=sources, calc_registry=calcs,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="VA"), ChannelRef(kind="source", source_id="src", channel_name="IA")])
        outcome = _nominal_frequency_for(ChannelRef(kind="calculated", calculated_channel_id=channel.id), workspace_id=WS,
                                         frequency_access=access, calc_registry=calcs)
        assert outcome.hz == 60.0 and outcome.manual

    def test_a_vanished_recording_or_channel_is_none_not_an_exception(self):
        sources, access = registries(step_source(50.0))
        calcs = CalculatedChannelRegistry()
        assert _nominal_frequency_for(ChannelRef(kind="calculated", calculated_channel_id="ghost"), workspace_id=WS,
                                      frequency_access=access, calc_registry=calcs) is None
        assert _nominal_frequency_for(ChannelRef(kind="source", source_id="ghost", channel_name="IA"), workspace_id=WS,
                                      frequency_access=access, calc_registry=calcs) is None


# ------------------------------------------------------------------------------------------ end to end over HTTP, both gate states
def _settings(tmp_path, enabled: bool) -> Settings:
    return Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=("http://localhost:8101",),
                    database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
                    nominal_frequency_manual_override_enabled=enabled)


@pytest.fixture
def opened(tmp_path):
    with TestClient(create_app(_settings(tmp_path, True)), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def closed(tmp_path):
    with TestClient(create_app(_settings(tmp_path, False)), raise_server_exceptions=False) as c:
        yield c


def nf_url(ws, sid):
    return f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency"


def measurement_status(client, ws):
    gid = client.get(f"/api/v1/workspaces/{ws}/compliance/voltage/measurement-groups").json()[-1]["id"]
    r = client.get(f"/api/v1/workspaces/{ws}/compliance/voltage/measurement", params={"measurement_group_id": gid, "quantity_id": "phase_a_lg_rms"})
    return r.status_code, (r.json()["status"] if r.status_code == 200 else None)


class TestEndToEnd:
    def test_manual_corrects_an_unusable_recording_through_measurement_and_readiness_and_auto_reverts_it(self, opened):
        ws = "ws-e2e-1"
        sid = scn3c._upload(opened, ws, "z", 5000.0, 50.0, "0")
        assert measurement_status(opened, ws) == (200, "ambiguous_measurement_metadata")           # unusable: unresolved, not a 500
        scn3c._add_reference(opened, ws)
        gid = opened.get(f"/api/v1/workspaces/{ws}/compliance/voltage/measurement-groups").json()[-1]["id"]
        states = lambda: {m["state"] for ref in opened.get(f"/api/v1/workspaces/{ws}/compliance/voltage/readiness",   # noqa: E731
                                                          params={"measurement_group_id": gid}).json()["references"] for m in ref["members"]}
        assert states() == {"incompatible"}

        assert opened.put(nf_url(ws, sid), json={"mode": "manual", "value_hz": 50}).status_code == 200
        assert measurement_status(opened, ws) == (200, "available")
        assert states() == {"needs_rms"}
        prepared = opened.post(f"/api/v1/workspaces/{ws}/compliance/voltage/prepare", json={"measurement_group_id": gid})
        assert prepared.status_code == 200 and len(prepared.json()["created"]) == 3
        stored = {c["parameters"]["nominal_frequency_hz"] for c in opened.get(f"/api/v1/workspaces/{ws}/calculated-channels").json()}
        assert stored == {50.0}                                                                       # the effective (Manual) value is what is stored

        assert opened.put(nf_url(ws, sid), json={"mode": "auto"}).status_code == 200
        assert measurement_status(opened, ws) == (200, "ambiguous_measurement_metadata")

    def test_the_closed_gate_refuses_manual_and_the_consumers_stay_on_auto(self, closed):
        ws = "ws-e2e-2"
        sid = scn3c._upload(closed, ws, "z", 5000.0, 50.0, "0")
        assert closed.put(nf_url(ws, sid), json={"mode": "manual", "value_hz": 50}).status_code == 409
        assert measurement_status(closed, ws) == (200, "ambiguous_measurement_metadata")

    def test_a_value_stored_behind_the_api_is_still_ignored_by_every_migrated_consumer_while_closed(self, closed):
        from datetime import datetime, timezone
        ws = "ws-e2e-3"
        sid = scn3c._upload(closed, ws, "z", 5000.0, 50.0, "0")
        closed.app.state.nominal_frequency_registry.set(ws, sid, 50.0, datetime(2026, 11, 26, tzinfo=timezone.utc))
        assert measurement_status(closed, ws) == (200, "ambiguous_measurement_metadata")
        det = closed.post(f"/api/v1/workspaces/{ws}/synchronization/detect-event", json={"source_id": sid, "channel_name": "ALPHA1_VA"})
        assert det.status_code == 200 and det.json()["reason"] == sync.NO_USABLE_NOMINAL_FREQUENCY_REASON

    def test_event_detection_uses_the_manual_value_over_http(self, opened):
        ws = "ws-e2e-4"
        sid = scn3c._upload(opened, ws, "z", 5000.0, 50.0, "0")
        url = f"/api/v1/workspaces/{ws}/synchronization/detect-event"
        body = {"source_id": sid, "channel_name": "ALPHA1_VA"}
        assert opened.post(url, json=body).json()["reason"] == sync.NO_USABLE_NOMINAL_FREQUENCY_REASON
        opened.put(nf_url(ws, sid), json={"mode": "manual", "value_hz": 50})
        r = opened.post(url, json=body).json()
        assert r["reason"] != sync.NO_USABLE_NOMINAL_FREQUENCY_REASON and r["nominal_frequency_hz"] == 50.0

    def test_source_deletion_and_workspace_reset_remove_the_manual_value_and_the_consumers_return_to_auto(self, opened):
        ws = "ws-e2e-5"
        sid = scn3c._upload(opened, ws, "z", 5000.0, 50.0, "0")
        opened.put(nf_url(ws, sid), json={"mode": "manual", "value_hz": 50})
        assert measurement_status(opened, ws) == (200, "available")
        assert opened.delete(f"/api/v1/workspaces/{ws}/sources/{sid}").status_code in (200, 204)
        assert opened.app.state.nominal_frequency_registry.count() == 0
        assert opened.post(f"/api/v1/workspaces/{ws}/synchronization/detect-event", json={"source_id": sid, "channel_name": "ALPHA1_VA"}).status_code == 404
        sid2 = scn3c._upload(opened, ws, "z", 5000.0, 50.0, "0")                           # the same kind of recording again: Auto, no memory
        assert measurement_status(opened, ws) == (200, "ambiguous_measurement_metadata")
        opened.put(nf_url(ws, sid2), json={"mode": "manual", "value_hz": 50})
        assert opened.delete(f"/api/v1/workspaces/{ws}").status_code in (200, 204)
        assert opened.app.state.nominal_frequency_registry.count() == 0
