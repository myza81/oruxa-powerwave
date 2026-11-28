"""NF-3B (owner decision O-1) -- the SERVER-SIDE release gate for a Manual nominal-frequency override.

Frontend visibility is not enforcement. The gate is a backend setting, closed by default. NF-3I (owner, 2026-11-28) released it for DEV ONLY: the
variable is accepted when ENVIRONMENT=development and refused for every other environment, and only the DEV overlay (`compose.dev.yaml`) sets it:

* closed: `PUT mode=manual` is refused with 409 `manual_nominal_frequency_disabled` and stores nothing; `PUT mode=auto` and every
  `GET` still work; a stored value cannot reach an engineering consumer; Auto behaviour is exactly what it was;
* open (through `NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED`, in a local process, an isolated test process or the DEV deployment): the NF-1
  behaviour, with its validation unchanged.

The UI flag (`nominalFrequencyOverride`) is separate; `test_frontend_nf2_release_gate.py` keeps it off by default and the DEV overlay turns it on.
"""

from __future__ import annotations

import io
import json
import warnings
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigurationError, Settings, load_settings
from app.main import create_app
from tests import comtrade_frequency_scenarios as scn
from tests import nf3b_baseline_scenarios as base

ROOT = Path(__file__).resolve().parents[2]
ENV_VAR = "NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED"
FROZEN = json.loads((Path(__file__).parent / "fixtures" / "nf3b_baselines" / "nf3b_frozen_baselines.json").read_text(encoding="utf-8"))["outcomes"]


def _env(**extra):
    return {"STORAGE_PATH": "/tmp/x", **extra}


# ---------------------------------------------------------------------------------------------------- configuration
class TestConfiguration:
    def test_the_dataclass_default_is_closed(self):
        assert Settings.__dataclass_fields__["nominal_frequency_manual_override_enabled"].default is False

    def test_an_unset_or_empty_variable_leaves_the_gate_closed(self):
        assert load_settings(_env()).nominal_frequency_manual_override_enabled is False
        assert load_settings(_env(**{ENV_VAR: ""})).nominal_frequency_manual_override_enabled is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " Yes "])
    def test_only_an_explicit_affirmative_opens_it_in_development(self, value):
        assert load_settings(_env(**{ENV_VAR: value})).nominal_frequency_manual_override_enabled is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "enabled", "2", "on", "y", "t", "open"])
    def test_anything_else_leaves_it_closed(self, value):
        assert load_settings(_env(**{ENV_VAR: value})).nominal_frequency_manual_override_enabled is False

    @pytest.mark.parametrize("env", [
        {"ENVIRONMENT": "production", "CORS_ORIGINS": "https://x", "RELAY_REVIEW_SIGNING_KEY": "k" * 32},
        {"ENVIRONMENT": "production", "CORS_ORIGINS": "https://x", "RELAY_REVIEW_SIGNING_KEY": "k" * 32, "APP_VERSION": "a" * 40},
        {"ENVIRONMENT": " Production ", "CORS_ORIGINS": "https://x", "RELAY_REVIEW_SIGNING_KEY": "k" * 32},
        {"ENVIRONMENT": "staging"},
        {"ENVIRONMENT": "test"},
    ])
    def test_every_environment_other_than_development_refuses_to_start_with_the_gate_open(self, env):
        with pytest.raises(ConfigurationError, match="released for ENVIRONMENT=development only"):
            load_settings(_env(**env, **{ENV_VAR: "1"}))

    @pytest.mark.parametrize("env", [
        {},                                                                                       # ENVIRONMENT defaults to development
        {"ENVIRONMENT": "development"},
        {"ENVIRONMENT": " Development "},
        {"ENVIRONMENT": "development", "APP_VERSION": "a" * 40, "RELAY_REVIEW_SIGNING_KEY": "k" * 32},   # the DEV deployment (NF-3I)
    ])
    def test_a_development_environment_including_the_dev_deployment_opens_it(self, env):
        settings = load_settings(_env(**env, **{ENV_VAR: "1"}))
        assert settings.nominal_frequency_manual_override_enabled is True
        assert settings.is_production is False

    def test_the_dev_deployment_build_is_a_deployed_build_and_is_still_allowed(self):
        settings = load_settings(_env(ENVIRONMENT="development", APP_VERSION="a" * 40, RELAY_REVIEW_SIGNING_KEY="k" * 32, **{ENV_VAR: "1"}))
        assert settings.is_deployed is True and settings.nominal_frequency_manual_override_enabled is True

    @pytest.mark.parametrize("env", [
        {"ENVIRONMENT": "production", "CORS_ORIGINS": "https://x", "RELAY_REVIEW_SIGNING_KEY": "k" * 32},
        {"ENVIRONMENT": "development", "APP_VERSION": "a" * 40, "RELAY_REVIEW_SIGNING_KEY": "k" * 32},
    ])
    def test_without_the_variable_every_environment_starts_with_the_gate_closed(self, env):
        assert load_settings(_env(**env)).nominal_frequency_manual_override_enabled is False
        assert load_settings(_env(**env, **{ENV_VAR: "0"})).nominal_frequency_manual_override_enabled is False


class TestOnlyTheDevDeploymentSetsTheVariable:
    """NF-3I: the gate is released for DEV only, and deliberately. Exactly two files may mention the variable: the DEV overlay (which sets it for the
    backend, the enforcement, and the frontend, which shows the control) and the frontend entrypoint that turns it into the page flag. Nothing
    else that builds, configures or deploys the application may: not the base compose file, not the PROD overlay, not an env example, a
    Dockerfile, a workflow or a script."""

    ALLOWED = ["compose.dev.yaml", "frontend/docker-entrypoint.d/10-powerwave-config.sh"]

    def _deployment_files(self):
        files = [*ROOT.glob("compose*.yaml"), *ROOT.glob("compose*.yml"), *ROOT.glob(".env*"), *ROOT.glob("Dockerfile*"),
                 *(ROOT / ".github" / "workflows").glob("*"), *(ROOT / "scripts").rglob("*"),
                 *(ROOT / "frontend" / "docker-entrypoint.d").glob("*"), *(ROOT / "backend").glob("Dockerfile*"),
                 ROOT / "frontend" / "config.js"]
        return [f for f in files if f.is_file()]

    def test_there_are_deployment_files_to_check(self):
        names = {f.name for f in self._deployment_files()}
        assert {"compose.yaml", "compose.dev.yaml", "compose.prod.yaml", ".env.example", "config.js"} <= names
        assert any(f.parent.name == "workflows" for f in self._deployment_files())

    def test_only_the_dev_overlay_and_the_entrypoint_mention_the_gate_variable(self):
        offenders = sorted(f.relative_to(ROOT).as_posix() for f in self._deployment_files()
                           if ENV_VAR in f.read_text(encoding="utf-8", errors="ignore"))
        assert offenders == self.ALLOWED

    def test_the_dev_overlay_sets_it_for_the_backend_and_the_frontend_and_nothing_else_is_opened(self):
        import yaml
        services = yaml.safe_load((ROOT / "compose.dev.yaml").read_text(encoding="utf-8"))["services"]
        assert services["backend"]["environment"][ENV_VAR] == "1"
        assert services["frontend"]["environment"][ENV_VAR] == "1"

    @pytest.mark.parametrize("name", ["compose.yaml", "compose.prod.yaml", ".env.example"])
    def test_the_base_and_the_prod_files_do_not_carry_it(self, name):
        assert ENV_VAR not in (ROOT / name).read_text(encoding="utf-8")

    def test_the_checked_in_frontend_config_does_not_carry_the_ui_flag(self):
        assert "nominalFrequencyOverride" not in (ROOT / "frontend" / "config.js").read_text(encoding="utf-8")

    def test_the_backend_reads_the_variable_in_exactly_one_place(self):
        readers = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "backend" / "app").rglob("*.py")
                         if ENV_VAR in p.read_text(encoding="utf-8"))
        assert readers == ["backend/app/config.py"]

    def test_the_frontend_page_cannot_open_the_server_gate(self):
        index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        assert ENV_VAR not in index and "manual_override_enabled" not in index


# -------------------------------------------------------------------------------------------------------- the API
def _settings(tmp_path, **kw) -> Settings:
    return Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=("http://localhost:8101",),
        database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local", **kw)


@pytest.fixture
def closed(tmp_path):
    with TestClient(create_app(_settings(tmp_path)), raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def opened_lenient(tmp_path):
    """Like `opened`, but a server error is a 500 response, not a raised exception (the frozen baseline contains known 500s)."""
    with TestClient(create_app(_settings(tmp_path, nominal_frequency_manual_override_enabled=True)), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def opened(tmp_path):
    with TestClient(create_app(_settings(tmp_path, nominal_frequency_manual_override_enabled=True)), raise_server_exceptions=True) as c:
        yield c


_N = iter(range(10_000))


def _upload(client, variant="declared_50"):
    ws = f"ws-gate-{next(_N)}"
    text = scn.build_variants()[variant]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        response = client.post(f"/api/v1/workspaces/{ws}/sources", files={
            "cfg_file": ("e.cfg", text.encode("latin-1"), "application/octet-stream"),
            "dat_file": ("e.dat", scn._DAT.encode(), "application/octet-stream")})
    assert response.status_code in (200, 201), response.text
    return ws, response.json()["source_id"]


def _url(ws, sid):
    return f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency"


class TestClosedGate:
    def test_manual_put_is_refused_with_409_and_stores_nothing(self, closed):
        ws, sid = _upload(closed)
        r = closed.put(_url(ws, sid), json={"mode": "manual", "value_hz": 60})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "manual_nominal_frequency_disabled"
        assert "not been released" in r.json()["detail"]["message"]
        assert closed.app.state.nominal_frequency_registry.snapshot(ws, sid) == (None, 0)
        got = closed.get(_url(ws, sid)).json()
        assert (got["mode"], got["effective_hz"], got["manual_hz"], got["revision"], got["manual_override_enabled"]) == ("auto", 50.0, None, 0, False)

    @pytest.mark.parametrize("body", [
        {"mode": "manual", "value_hz": 0}, {"mode": "manual", "value_hz": -50}, {"mode": "manual", "value_hz": 1001},
        {"mode": "manual", "value_hz": 60.5}, {"mode": "manual"}, {"mode": "manual", "value_hz": None},
    ])
    def test_a_closed_gate_refuses_before_examining_the_value(self, closed, body):
        ws, sid = _upload(closed)
        assert closed.put(_url(ws, sid), json=body).status_code == 409
        assert closed.app.state.nominal_frequency_registry.count() == 0

    @pytest.mark.parametrize("raw", ['{"mode":"manual","value_hz":"60"}', '{"mode":"manual","value_hz":true}', '{"mode":"bogus"}',
                                     '{"mode":"manual","value_hz":60,"extra":1}'])
    def test_malformed_requests_are_still_422_never_500_and_never_stored(self, closed, raw):
        ws, sid = _upload(closed)
        r = closed.put(_url(ws, sid), content=raw, headers={"content-type": "application/json"})
        assert r.status_code == 422
        assert closed.app.state.nominal_frequency_registry.count() == 0

    def test_an_unknown_recording_is_404_before_the_gate(self, closed):
        ws, _ = _upload(closed)
        assert closed.put(_url(ws, "nope"), json={"mode": "manual", "value_hz": 60}).status_code == 404

    def test_returning_to_auto_still_works_and_is_idempotent(self, closed):
        ws, sid = _upload(closed, "declared_60")
        for _ in range(2):
            r = closed.put(_url(ws, sid), json={"mode": "auto"})
            assert r.status_code == 200 and r.json()["effective_hz"] == 60.0 and r.json()["manual_override_enabled"] is False

    def test_a_value_supplied_with_mode_auto_is_still_the_existing_400(self, closed):
        ws, sid = _upload(closed)
        assert closed.put(_url(ws, sid), json={"mode": "auto", "value_hz": 60}).status_code == 400

    @pytest.mark.parametrize("variant,hz,origin,usable", [
        ("declared_50", 50.0, "recording_metadata", True), ("declared_60", 60.0, "recording_metadata", True),
        ("unparseable_text", 50.0, "assumed_default", True), ("declared_zero", None, "unusable", False),
        ("declared_negative_50", None, "unusable", False), ("declared_nan", None, "unusable", False),
    ])
    def test_get_reports_the_auto_resolution_for_every_recording_class(self, closed, variant, hz, origin, usable):
        ws, sid = _upload(closed, variant)
        got = closed.get(_url(ws, sid)).json()
        assert (got["effective_hz"], got["origin"], got["usable"], got["mode"], got["manual_override_enabled"]) == (hz, origin, usable, "auto", False)

    def test_a_value_stored_behind_the_apis_back_is_invisible_to_get(self, closed):
        from datetime import datetime, timezone
        ws, sid = _upload(closed, "declared_50")
        closed.app.state.nominal_frequency_registry.set(ws, sid, 33.0, datetime(2026, 11, 25, tzinfo=timezone.utc))
        got = closed.get(_url(ws, sid)).json()
        assert (got["mode"], got["effective_hz"], got["manual_hz"], got["origin"]) == ("auto", 50.0, None, "recording_metadata")
        assert closed.app.state.nominal_frequency_access.for_source(ws, sid).hz == 50.0


    @pytest.mark.parametrize("raw", ['{"mode":"manual","value_hz":NaN}', '{"mode":"manual","value_hz":Infinity}', '{"mode":"manual","value_hz":-Infinity}'])
    def test_nan_and_infinity_are_refused_by_the_gate_first_and_never_stored(self, closed, raw):
        # They parse as JSON floats, so they reach the service; a closed gate refuses before the value is examined.
        ws, sid = _upload(closed)
        r = closed.put(_url(ws, sid), content=raw, headers={"content-type": "application/json"})
        assert r.status_code == 409
        assert closed.app.state.nominal_frequency_registry.count() == 0


class TestOpenGate:
    def test_the_nf1_cycle_works_and_reports_the_gate(self, opened):
        ws, sid = _upload(opened)
        r = opened.put(_url(ws, sid), json={"mode": "manual", "value_hz": 60})
        assert r.status_code == 200
        body = r.json()
        assert (body["mode"], body["effective_hz"], body["origin"], body["manual_hz"], body["revision"], body["manual_override_enabled"]) == (
            "manual", 60.0, "manual", 60.0, 1, True)
        assert opened.get(_url(ws, sid)).json()["effective_hz"] == 60.0
        assert opened.put(_url(ws, sid), json={"mode": "auto"}).json()["effective_hz"] == 50.0

    @pytest.mark.parametrize("value", [0, -50, 0.5, 1001, 1e308])
    def test_validation_is_unchanged(self, opened, value):
        ws, sid = _upload(opened)
        r = opened.put(_url(ws, sid), json={"mode": "manual", "value_hz": value})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_nominal_frequency"
        assert opened.app.state.nominal_frequency_registry.count() == 0

    def test_a_missing_value_is_the_existing_400(self, opened):
        ws, sid = _upload(opened)
        r = opened.put(_url(ws, sid), json={"mode": "manual"})
        assert r.status_code == 400 and "required" in r.json()["detail"]["message"]

    @pytest.mark.parametrize("raw", ['{"mode":"manual","value_hz":NaN}', '{"mode":"manual","value_hz":Infinity}', '{"mode":"manual","value_hz":-Infinity}'])
    def test_nan_and_infinity_are_refused_by_the_existing_validation_and_never_stored(self, opened, raw):
        ws, sid = _upload(opened)
        r = opened.put(_url(ws, sid), content=raw, headers={"content-type": "application/json"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_nominal_frequency"
        assert opened.app.state.nominal_frequency_registry.count() == 0

    def test_a_manual_value_corrects_an_unusable_recording(self, opened):
        ws, sid = _upload(opened, "declared_zero")
        assert opened.get(_url(ws, sid)).json()["usable"] is False
        assert opened.put(_url(ws, sid), json={"mode": "manual", "value_hz": 60}).json()["effective_hz"] == 60.0

    def test_source_removal_and_workspace_reset_clear_the_value_through_the_open_gate(self, opened):
        ws, a = _upload(opened)
        opened.put(_url(ws, a), json={"mode": "manual", "value_hz": 40})
        assert opened.app.state.nominal_frequency_registry.count() == 1
        assert opened.delete(f"/api/v1/workspaces/{ws}/sources/{a}").status_code in (200, 204)
        assert opened.app.state.nominal_frequency_registry.count() == 0
        ws2, b = _upload(opened)
        opened.put(_url(ws2, b), json={"mode": "manual", "value_hz": 40})
        assert opened.delete(f"/api/v1/workspaces/{ws2}").status_code in (200, 204)
        assert opened.app.state.nominal_frequency_registry.count() == 0

    def test_an_app_started_with_the_gate_open_then_a_second_one_closed_do_not_share_state(self, tmp_path):
        with TestClient(create_app(_settings(tmp_path / "a", nominal_frequency_manual_override_enabled=True))) as a, \
                TestClient(create_app(_settings(tmp_path / "b"))) as b:
            assert a.app.state.nominal_frequency_access.manual_override_enabled is True
            assert b.app.state.nominal_frequency_access.manual_override_enabled is False


# --------------------------------------------------------------------- engineering behaviour is unchanged in NF-3B
class TestAManualValueInfluencesOnlyTheMigratedConsumers:
    """NF-3B migrated no consumer, and this class said so: with the gate open and a Manual value stored, every consumer reproduced the
    frozen baseline. NF-3C migrated event detection (and compliance and oscillation, tested in test_nf3c_*): their Manual behaviour is
    asserted there and for event detection below. NF-3D migrated the phasor family and overcurrent: a stored Manual value IS their
    frequency, and the result says so (tests/test_nf3d_behaviour.py proves it in depth). NF-3F (O-2) migrated the power channels, so a
    stored Manual value IS the frequency a new power channel is calculated at, and the channel records it; this class was edited in that
    commit, as it announced. With the gate closed nothing can be stored at all."""

    @pytest.mark.parametrize("recording,manual", [("r50", 60.0), ("r60", 50.0), ("assumed_on_60hz_signal", 60.0), ("declared_zero", 60.0)])
    def test_a_stored_manual_value_reaches_event_detection_the_phasor_family_and_the_power_channels(self, opened_lenient, recording, manual):
        opened = opened_lenient
        fs, f_sig, lf = base.HTTP_RECORDINGS[recording]
        ws = base.WS
        cfg, dat = base.build_comtrade(fs, f_sig, lf)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            up = opened.post(f"/api/v1/workspaces/{ws}/sources", files={
                "cfg_file": ("a.cfg", io.BytesIO(cfg), "application/octet-stream"), "dat_file": ("a.dat", io.BytesIO(dat), "application/octet-stream")})
        sid = up.json()["source_id"]
        assert opened.put(_url(ws, sid), json={"mode": "manual", "value_hz": manual}).status_code == 200
        frozen = FROZEN["http"][recording]
        # the same consumers the baseline captured, with a Manual value now stored for the recording
        det = opened.post(f"/api/v1/workspaces/{ws}/synchronization/detect-event", json={"source_id": sid, "channel_name": "ALPHA1_VA"})
        assert det.status_code == frozen["detect_event"]["status"]
        # NF-3C: event detection is migrated, so the Manual value IS the frequency it reports (it used to echo the declared one)
        assert det.json()["nominal_frequency_hz"] == manual
        for context in opened.get(f"/api/v1/workspaces/{ws}/engineering-contexts").json():
            opened.delete(f"/api/v1/workspaces/{ws}/engineering-contexts/{context['id']}")
        ref = lambda n: {"kind": "source", "source_id": sid, "channel_name": n}      # noqa: E731
        ctx = opened.post(f"/api/v1/workspaces/{ws}/engineering-contexts", json={"display_name": "Alpha 1", "status": "manual", "members": [
            {"channel_ref": ref(n), "phase": p, "phase_source": "engineer_confirmed"}
            for n, p in (("ALPHA1_VA", "A"), ("ALPHA1_VB", "B"), ("ALPHA1_VC", "C"), ("ALPHA1_IA", "A"))]})
        cid = ctx.json()["id"]
        ph = opened.get(f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}/phasor",
                        params={"analysis_kind": "phasor", "mode": "voltage_three_phase", "analysis_time": 0.5})
        # NF-3D: the phasor family is migrated, so the Manual value IS its reference frequency (it used to read the declared one) and the
        # result says where it came from. A refusal for another reason (the form detector on a 50 Hz signal at 60 Hz) never blames the frequency.
        assert ph.status_code == 200
        body = ph.json()
        assert body["reason_code"] != "invalid_reference_frequency"
        if body["status"] == "computed":
            assert body["reference_frequency_hz"] == manual
            assert (body["nominal_frequency_origin"], body["nominal_frequency_revision"]) == ("manual", 1)
        # NF-3F (O-2): the power channels are migrated, so the Manual value IS the frequency a new power channel is calculated at, and the
        # channel records the origin and revision it used (recording-following, so a later change makes it stale)
        power = opened.post(f"/api/v1/workspaces/{ws}/calculated-channels", json={
            "operation": "active_power", "name": "P-manual", "parameters": {},
            "inputs": [ref("ALPHA1_VA"), ref("ALPHA1_IA")]})
        assert power.status_code == 201
        stored = opened.app.state.calculated_channel_registry.get(ws, power.json()["id"]).parameters
        assert stored["nominal_frequency_hz"] == manual
        assert (stored["nominal_frequency_basis"], stored["nominal_frequency_origin"], stored["nominal_frequency_revision"]) == (
            "recording", "manual", 1)
