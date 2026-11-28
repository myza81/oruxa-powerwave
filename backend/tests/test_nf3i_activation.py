"""NF-3I -- activation of the Nominal Frequency feature for DEV: the owner's UAT scenarios, end to end over HTTP.

The application is built exactly as the DEV deployment builds it: through `load_settings` from the environment the DEV overlay sets
(`ENVIRONMENT=development`, a deployed `APP_VERSION`, the signing key, `NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED=1`). Before NF-3I that configuration
was refused at start; here it must start and the whole feature must work. Scenarios (owner, 2026-11-28): declared 50 Hz, declared 60 Hz, assumed
50 Hz and unusable recordings; Auto and Manual; a Manual override; return to Auto; calculated-channel staleness; power across compatible and
incompatible recordings; existing per-unit functionality; preservation of the recording's samples. The same app with the variable unset must keep the
safe default (a Manual value is refused, nothing else changes).
"""

from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from tests import nf3d_baseline_scenarios as scn
from tests import nf3e_baseline_scenarios as nf3e

ENV_VAR = "NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED"
DEV_ENV = {"ENVIRONMENT": "development", "APP_VERSION": "a" * 40, "RELAY_REVIEW_SIGNING_KEY": "k" * 32}
_ids = itertools.count(1)


def _app(tmp_path_factory, **extra):
    env = {"STORAGE_PATH": str(tmp_path_factory.mktemp("nf3i")), **DEV_ENV, **extra}
    return create_app(load_settings(env))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(_app(tmp_path_factory, **{ENV_VAR: "1"}), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def closed_client(tmp_path_factory):
    with TestClient(_app(tmp_path_factory), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def ws():
    return f"ws-nf3i-{next(_ids)}"


def rec(client, ws, key, *, f, lf, fs=5000.0):
    sid = scn.upload(client, ws, key, fs, f, lf)
    assert sid is not None
    return sid


def view(client, ws, sid):
    r = client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency")
    assert r.status_code == 200
    return r.json()


def power(client, ws, name, v_sid, i_sid):
    return nf3e.create(client, ws, name, "active_power", [nf3e.src(v_sid, "VA"), nf3e.src(i_sid, "IA")])


class TestTheDevConfigurationStartsAndOpensTheFeature:
    def test_the_dev_deployment_environment_starts_with_the_gate_open(self, client):
        assert client.app.state.nominal_frequency_access.manual_override_enabled is True
        assert client.get("/health").status_code == 200

    def test_the_same_deployment_without_the_variable_keeps_the_safe_default(self, closed_client, ws):
        sid = rec(closed_client, ws, "r60", f=60.0, lf="60")
        assert closed_client.app.state.nominal_frequency_access.manual_override_enabled is False
        refused = closed_client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": 50.0})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "manual_nominal_frequency_disabled"
        assert view(closed_client, ws, sid)["effective_hz"] == 60.0                        # Auto still works

    def test_production_with_the_variable_is_refused_at_start(self, tmp_path_factory):
        from app.config import ConfigurationError
        with pytest.raises(ConfigurationError, match="development only"):
            load_settings({"STORAGE_PATH": str(tmp_path_factory.mktemp("prod")), "ENVIRONMENT": "production", "CORS_ORIGINS": "https://x",
                           "RELAY_REVIEW_SIGNING_KEY": "k" * 32, ENV_VAR: "1"})


class TestRecordingStates:
    @pytest.mark.parametrize("lf,effective,origin,flag", [
        ("50", 50.0, "recording_metadata", None),
        ("60", 60.0, "recording_metadata", None),
        ("abc", 50.0, "assumed_default", "assumed"),                 # nothing declared: the 50 Hz fallback, flagged assumed
    ])
    def test_declared_and_assumed_recordings_report_their_effective_frequency(self, client, ws, lf, effective, origin, flag):
        body = view(client, ws, rec(client, ws, "r", f=60.0 if lf == "60" else 50.0, lf=lf))
        assert (body["mode"], body["effective_hz"], body["origin"]) == ("auto", effective, origin)
        assert body["usable"] is True
        assert (body["auto_origin"] == "assumed_default") is (flag == "assumed")

    def test_an_unusable_declaration_has_no_effective_frequency_and_keeps_the_imported_text(self, client, ws):
        body = view(client, ws, rec(client, ws, "r0", f=50.0, lf="0"))
        assert (body["usable"], body["effective_hz"], body["auto_origin"]) == (False, None, "unusable")
        assert body["imported_text"] == "0.0"


class TestAutoManualAndReturnToAuto:
    def test_manual_override_then_return_to_auto_restores_the_declared_value(self, client, ws):
        sid = rec(client, ws, "r50", f=50.0, lf="50")
        manual = client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": 60.0}).json()
        assert (manual["mode"], manual["effective_hz"], manual["origin"], manual["auto_hz"]) == ("manual", 60.0, "manual", 50.0)
        auto = client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "auto"}).json()
        assert (auto["mode"], auto["effective_hz"], auto["origin"]) == ("auto", 50.0, "recording_metadata")

    @pytest.mark.parametrize("value", [0.5, 1001.0, -50.0, 0.0])
    def test_an_out_of_range_manual_value_is_refused_and_nothing_is_stored(self, client, ws, value):
        sid = rec(client, ws, "r50", f=50.0, lf="50")
        r = client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": value})
        assert r.status_code in (400, 422)
        assert view(client, ws, sid)["mode"] == "auto"

    def test_a_manual_value_repairs_an_unusable_recording_and_a_consumer_reads_it(self, client, ws):
        sid = rec(client, ws, "r0", f=50.0, lf="0")
        refused = power(client, ws, "P", sid, sid)
        assert refused["status"] == 400 and refused["body"]["detail"]["code"] == "invalid_nominal_frequency"
        assert nf3e.put_manual(client, ws, sid, 50.0)["status"] == 200
        made = power(client, ws, "P", sid, sid)
        assert made["status"] == 201
        assert client.app.state.calculated_channel_registry.get(ws, made["id"]).parameters["nominal_frequency_hz"] == 50.0
        # the same value reaches event detection (another migrated consumer)
        detect = client.post(f"/api/v1/workspaces/{ws}/synchronization/detect-event", json={"source_id": sid, "channel_name": "ALPHA1_VA"})
        assert detect.status_code == 200 and detect.json()["nominal_frequency_hz"] == 50.0

    def test_a_manual_value_is_what_a_consumer_uses_and_returning_to_auto_changes_it_back(self, client, ws):
        sid = rec(client, ws, "r50", f=50.0, lf="50")
        nf3e.put_manual(client, ws, sid, 60.0)
        detect = lambda: client.post(f"/api/v1/workspaces/{ws}/synchronization/detect-event",             # noqa: E731
                                     json={"source_id": sid, "channel_name": "ALPHA1_VA"}).json()["nominal_frequency_hz"]
        assert detect() == 60.0
        nf3e.put_auto(client, ws, sid)
        assert detect() == 50.0


class TestStalenessOfExistingCalculatedChannels:
    def test_a_recording_following_channel_goes_stale_and_current_again_with_the_frequency(self, client, ws):
        sid = rec(client, ws, "r50", f=50.0, lf="50")
        made = nf3e.create(client, ws, "rms50", "rms", [nf3e.src(sid, "VA")], {"nominal_frequency_hz": 50, "nominal_frequency_basis": "recording"})
        assert made["status"] == 201
        state = lambda: {c["name"]: c["frequency_staleness"]["state"] for c in nf3e.inventory_raw(client, ws)}["rms50"]       # noqa: E731
        assert state() == "current"
        nf3e.put_manual(client, ws, sid, 60.0)
        assert state() == "stale"
        refused = nf3e.create(client, ws, "sum", "addition", [nf3e.calc(made["id"]), nf3e.calc(made["id"])])
        assert refused["status"] == 409 and refused["body"]["detail"]["code"] == "stale_calculated_input"
        nf3e.put_auto(client, ws, sid)
        assert state() == "current"

    def test_a_power_channel_follows_the_recording_too(self, client, ws):
        sid = rec(client, ws, "r60", f=60.0, lf="60")
        made = power(client, ws, "P", sid, sid)
        assert made["status"] == 201 and made["body"]["frequency_staleness"]["state"] == "current"
        nf3e.put_manual(client, ws, sid, 50.0)
        stale = {c["name"]: c["frequency_staleness"] for c in nf3e.inventory_raw(client, ws)}["P"]
        assert stale["state"] == "stale" and stale["assessment"] == "frequency_aware"
        assert stale["causes"][0]["stored_hz"] == 60.0 and stale["causes"][0]["effective_hz"] == 50.0


class TestPowerAcrossRecordings:
    def test_incompatible_frequencies_are_refused_compatible_ones_are_accepted_and_a_manual_value_can_reconcile(self, client, ws):
        v50 = rec(client, ws, "v50", f=50.0, lf="50")
        i60 = rec(client, ws, "i60", f=50.0, lf="60")
        refused = power(client, ws, "P", v50, i60)
        assert refused["status"] == 400 and refused["body"]["detail"]["code"] == "nominal_frequency_mixed"
        assert "50 Hz" in refused["body"]["detail"]["message"] and "60 Hz" in refused["body"]["detail"]["message"]
        assert nf3e.inventory_raw(client, ws) == []                                         # nothing was written
        nf3e.put_manual(client, ws, v50, 60.0)                                              # the engineer reconciles the recordings
        accepted = power(client, ws, "P", v50, i60)
        assert accepted["status"] == 201
        assert client.app.state.calculated_channel_registry.get(ws, accepted["id"]).parameters["nominal_frequency_hz"] == 60.0

    def test_two_recordings_that_agree_are_accepted_without_any_override(self, client, ws):
        a = rec(client, ws, "a60", f=60.0, lf="60")
        b = rec(client, ws, "b60", f=60.0, lf="60")
        assert power(client, ws, "P", a, b)["status"] == 201


class TestExistingFunctionalityIsPreserved:
    def test_the_recordings_samples_and_imported_metadata_never_change(self, client, ws):
        sid = rec(client, ws, "r50", f=50.0, lf="50")
        waveform = lambda: client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/waveform").json()               # noqa: E731
        summary = lambda: client.get(f"/api/v1/workspaces/{ws}/sources/{sid}").json()                         # noqa: E731
        before_w, before_s = waveform(), summary()
        nf3e.put_manual(client, ws, sid, 60.0)
        assert waveform() == before_w and summary() == before_s
        nf3e.put_auto(client, ws, sid)
        assert waveform() == before_w and summary() == before_s
        assert summary()["nominal_frequency"] == 50.0                                        # the imported value, original metadata

    def test_per_unit_configuration_and_the_waveform_are_unaffected_by_a_frequency_change(self, client, ws):
        sid = rec(client, ws, "r50", f=50.0, lf="50")
        put = client.put(f"/api/v1/workspaces/{ws}/per-unit/sources/{sid}", json={"voltage_base_value": 275.0})
        assert put.status_code == 200
        listing = lambda: client.get(f"/api/v1/workspaces/{ws}/per-unit/sources").json()                      # noqa: E731
        waveform = lambda: client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/waveform").json()               # noqa: E731
        before_l, before_w = listing(), waveform()
        nf3e.put_manual(client, ws, sid, 60.0)
        assert listing() == before_l and waveform() == before_w
        nf3e.put_auto(client, ws, sid)
        assert listing() == before_l and waveform() == before_w
