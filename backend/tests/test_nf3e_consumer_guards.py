"""NF-3E closeout -- the governing principle at the engineering consumers.

A stale calculated channel (computed with a nominal frequency its recording no longer has, directly or through an input) stays available for
HISTORICAL INSPECTION but is not a valid input for a NEW engineering calculation or assessment. The consumers reuse the ONE shared staleness
authority (`services/calculated_channel_staleness.py`):

* compliance execution (`compliance_series.load_series`): typed `stale_calculated_input` (HTTP 409); compliance readiness: a BLOCKED member
  naming the channel and reason;
* oscillation (`_analysis_series` / `derive_analysis_representation`, native and RMS-magnitude): the typed error, HTTP 409;
* phasor family and overcurrent: a result with `reason_code: stale_calculated_input` and the actionable message (their convention).

Valid inputs stay accepted, nothing is recomputed, and returning to the original frequency lifts the refusal.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.calculated_channel import ChannelRef
from app.main import create_app
from app.services.compliance_series import Registries, load_series
from app.services.compliance_readiness_service import MemberReadiness, STATE_BLOCKED, STATE_REUSED
from app.services.errors import StaleCalculatedInputError
from tests import nf3d_baseline_scenarios as scn
from tests import nf3e_baseline_scenarios as nf3e

_ids = itertools.count(1)
APP_DIR = Path(__file__).resolve().parents[1] / "app"
STALE = "stale_calculated_input"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3e_guards")),
                        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local",
                        version="local", nominal_frequency_manual_override_enabled=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def ws(client):
    return f"ws-nf3e-guards-{next(_ids)}"


def rec(client, ws, name="r50"):
    return scn.upload(client, ws, name, 5000.0, 50.0, "50")


def following(client, ws, name, sid, channel="VA", hz=50):
    made = nf3e.create(client, ws, name, "rms", [nf3e.src(sid, channel)], {"nominal_frequency_hz": hz, "nominal_frequency_basis": "recording"})
    assert made["status"] == 201, made
    return made["id"]


def explicit(client, ws, name, sid, channel="VA", hz=50):
    made = nf3e.create(client, ws, name, "rms", [nf3e.src(sid, channel)], {"nominal_frequency_hz": hz, "nominal_frequency_basis": "explicit"})
    assert made["status"] == 201, made
    return made["id"]


def cref(cid):
    return ChannelRef(kind="calculated", calculated_channel_id=cid)


def registries(client):
    s = client.app.state
    return Registries(source=s.workspace_registry, calc=s.calculated_channel_registry, per_unit=s.per_unit_registry, group=s.measurement_group_registry,
                      voltage_config=s.voltage_group_config_registry, current_config=s.current_group_config_registry,
                      frequency_access=s.nominal_frequency_access)


def wave(client, ws, cid):
    r = client.get(f"/api/v1/workspaces/{ws}/calculated-channels/{cid}/waveform", params={"point_budget": 100000})
    assert r.status_code == 200, r.text
    return r.json()["time"], r.json()["values"]


# ------------------------------------------------------------------------------------------------ compliance
class TestComplianceExecutionAndReadiness:
    def test_execution_refuses_a_directly_stale_channel_with_the_typed_error(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        nf3e.put_manual(client, ws, sid, 60.0)
        with pytest.raises(StaleCalculatedInputError) as caught:
            load_series(cref(rms), "V", workspace_id=ws, reg=registries(client))
        assert caught.value.code == STALE and "'rms'" in caught.value.message and "60 Hz" in caught.value.message

    def test_execution_refuses_a_transitively_stale_channel(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        absd = nf3e.create(client, ws, "abs_of_rms", "absolute_value", [nf3e.calc(rms)])["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        with pytest.raises(StaleCalculatedInputError):
            load_series(cref(absd), "V", workspace_id=ws, reg=registries(client))

    def test_valid_inputs_remain_accepted_and_values_are_unchanged(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        exp = explicit(client, ws, "rms_explicit", sid)
        before, _ = load_series(cref(rms), "V", workspace_id=ws, reg=registries(client))
        nf3e.put_manual(client, ws, sid, 60.0)
        series, problem = load_series(cref(exp), "V", workspace_id=ws, reg=registries(client))     # explicit: never stale
        assert problem is None and series is not None
        raw, problem = load_series(ChannelRef(kind="source", source_id=sid, channel_name="ALPHA1_VA"), "V", workspace_id=ws, reg=registries(client))
        assert problem is None and raw is not None                                                 # raw sources are never stale
        nf3e.put_auto(client, ws, sid)                                                             # frequency restored: staleness clears
        after, problem = load_series(cref(rms), "V", workspace_id=ws, reg=registries(client))
        assert problem is None and np.array_equal(before.values, after.values, equal_nan=True)     # nothing was recomputed

    def test_historical_inspection_stays_available_while_stale(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        before = wave(client, ws, rms)
        nf3e.put_manual(client, ws, sid, 60.0)
        assert wave(client, ws, rms) == before
        peaks = client.post(f"/api/v1/workspaces/{ws}/calculated-channels/peak-values", json={"channels": [{"calculated_channel_id": rms}], "start_time": 0.0, "end_time": 1.0})
        assert peaks.status_code != 409                                                           # inspection is never a stale refusal

    def test_readiness_blocks_a_stale_member_naming_the_channel_and_reason(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        nf3e.put_manual(client, ws, sid, 60.0)
        from app.services.compliance_readiness_service import _block_stale_members
        s = client.app.state
        ctx = SimpleNamespace(workspace_id=ws, calc_registry=s.calculated_channel_registry, frequency_access=s.nominal_frequency_access)
        reused = MemberReadiness(member="va", state=STATE_REUSED, channel_name="rms", calculated_channel_id=rms, channel_ref=cref(rms), message="reused")
        raw = MemberReadiness(member="vb", state=STATE_REUSED, channel_name="VB", channel_ref=ChannelRef(kind="source", source_id=sid, channel_name="ALPHA1_VB"), message="ok")
        blocked, untouched = _block_stale_members(ctx, (reused, raw))
        assert blocked.state == STATE_BLOCKED and "'rms'" in blocked.message and "50 Hz" in blocked.message and "60 Hz" in blocked.message
        assert blocked.channel_ref == cref(rms) and blocked.member == "va"
        assert untouched == raw
        from app.services.compliance_readiness_service import STATE_NEEDS_RMS, PreparationStep, STEP_RMS
        step = PreparationStep(kind=STEP_RMS, key=(STEP_RMS, cref(rms), 60.0), description="RMS of rms", executable=True, input_ref=cref(rms),
                               nominal_frequency_hz=60.0)
        needs = MemberReadiness(member="va", state=STATE_NEEDS_RMS, channel_name="rms", step=step, message="needs RMS")
        (blocked_step,) = _block_stale_members(ctx, (needs,))                                      # an RMS step on a stale input would be refused
        assert blocked_step.state == STATE_BLOCKED and "'rms'" in blocked_step.message
        nf3e.put_auto(client, ws, sid)
        assert _block_stale_members(ctx, (reused,)) == (reused,)                                   # restored: no longer blocked
        assert _block_stale_members(ctx, (needs,)) == (needs,)

    def test_the_compliance_router_maps_the_refusal_to_409(self):
        from app.api.v1.compliance import _STATUS_BY_ERROR_CODE
        assert _STATUS_BY_ERROR_CODE[STALE] == 409

    def test_every_production_series_reader_passes_the_frequency_authority(self):
        calls = []
        for path in APP_DIR.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Registries":
                    calls.append((path.name, {k.arg for k in node.keywords}))
        assert {name for name, _ in calls} == {"compliance.py", "compliance_readiness_service.py"}
        assert all("frequency_access" in keywords for _, keywords in calls), calls


class TestReadinessEndpointBlocksAStaleMember:
    """The integration of the blocked state into the readiness endpoint (the unit tests above cover the conversion itself). The planner is
    patched to hand the readiness a stale calculated channel as a member: the readiness itself never reuses a stale RMS, so this is the
    defensive path a stale channel could only reach through another planner."""

    def test_the_reference_needs_action_and_names_the_stale_channel_and_reason(self, settings, comtrade_fixtures_dir, monkeypatch):
        import dataclasses
        import io

        from app.services import compliance_readiness_service as svc
        from tests import test_compliance_readiness_api as cr

        gate_open = dataclasses.replace(settings, nominal_frequency_manual_override_enabled=True)
        with TestClient(create_app(gate_open), raise_server_exceptions=False) as c:
            cfg = (comtrade_fixtures_dir / f"{cr.FIXTURE}.cfg").read_bytes()
            dat = (comtrade_fixtures_dir / f"{cr.FIXTURE}.dat").read_bytes()
            r = c.post(f"/api/v1/workspaces/{cr.WS}/sources", files={
                "cfg_file": (f"{cr.FIXTURE}.cfg", io.BytesIO(cfg), "application/octet-stream"),
                "dat_file": (f"{cr.FIXTURE}.dat", io.BytesIO(dat), "application/octet-stream")})
            assert r.status_code == 201, r.text
            cr._add_reference(c)
            group = cr._groups(c)["KPDN1"]
            sid = group["source_id"]
            channel = c.app.state.workspace_registry.get(cr.WS, sid).metadata.analog_channels[0].name
            made = nf3e.create(c, cr.WS, "rms_stale", "rms", [{"kind": "source", "source_id": sid, "channel_name": channel}],
                               {"nominal_frequency_hz": 50, "nominal_frequency_basis": "recording"}, override=True)
            assert made["status"] == 201, made
            rms = made["id"]
            monkeypatch.setattr(svc, "_plan_member", lambda ctx, requirement, member: svc.MemberReadiness(
                member=member, state=svc.STATE_REUSED, channel_name="rms_stale", calculated_channel_id=rms, channel_ref=cref(rms), message="reused"))

            nf3e.put_manual(c, cr.WS, sid, 60.0)
            reference = cr._readiness(c, "KPDN1")["references"][0]
            assert reference["status"] == "action_required"
            assert {m["state"] for m in reference["members"]} == {svc.STATE_BLOCKED}
            assert "'rms_stale'" in reference["message"] and "50 Hz" in reference["message"] and "60 Hz" in reference["message"]

            nf3e.put_auto(c, cr.WS, sid)                                                           # frequency restored: nothing is blocked any more
            restored = cr._readiness(c, "KPDN1")["references"][0]
            assert svc.STATE_BLOCKED not in {m["state"] for m in restored["members"]}


# ------------------------------------------------------------------------------------------------ oscillation
class TestOscillation:
    def _spectrum(self, client, ws, cid, representation):
        return client.post(f"/api/v1/workspaces/{ws}/oscillation-analysis/spectrum", json={
            "input": {"kind": "calculated", "calculated_channel_id": cid}, "representation": representation,
            "window_start_s": 0.2, "window_end_s": 0.9, "frequency_min_hz": 0.5, "frequency_max_hz": 20.0})

    @pytest.mark.parametrize("representation", ["native", "rms_magnitude"])
    def test_a_stale_channel_is_refused_in_every_representation(self, client, ws, representation):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        nf3e.put_manual(client, ws, sid, 60.0)
        r = self._spectrum(client, ws, rms, representation)
        assert r.status_code == 409 and r.json()["detail"]["code"] == STALE
        assert "Create a new" in r.json()["detail"]["message"]

    def test_the_representation_endpoint_refuses_a_stale_channel_too(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        absd = nf3e.create(client, ws, "abs_of_rms", "absolute_value", [nf3e.calc(rms)])["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        for cid in (rms, absd):                                                                    # direct and transitive
            r = client.post(f"/api/v1/workspaces/{ws}/oscillation-analysis/representation", json={"input": {"kind": "calculated", "calculated_channel_id": cid}})
            assert r.status_code == 409 and r.json()["detail"]["code"] == STALE

    def test_valid_inputs_stay_accepted_and_a_restored_frequency_lifts_the_refusal(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid)
        exp = explicit(client, ws, "rms_explicit", sid)
        nf3e.put_manual(client, ws, sid, 60.0)
        assert self._spectrum(client, ws, exp, "native").status_code == 200                      # explicit: never stale
        raw = client.post(f"/api/v1/workspaces/{ws}/oscillation-analysis/spectrum", json={
            "input": {"kind": "source", "source_id": sid, "channel_name": "ALPHA1_VA"}, "representation": "rms_magnitude",
            "window_start_s": 0.2, "window_end_s": 0.9, "frequency_min_hz": 0.5, "frequency_max_hz": 20.0})
        assert raw.status_code != 409                                                              # raw sources are never stale
        nf3e.put_auto(client, ws, sid)
        assert self._spectrum(client, ws, rms, "native").status_code == 200

    def test_the_oscillation_router_maps_the_refusal_to_409(self):
        from app.api.v1.oscillation import _STATUS_BY_ERROR_CODE
        assert _STATUS_BY_ERROR_CODE[STALE] == 409


# ------------------------------------------------------------------------------------------------ phasor family and overcurrent
def context_with(client, ws, sid, ia_ref):
    """A bay whose phase-A current is the given (calculated) channel and whose other roles are the raw recording's channels."""
    for existing in client.get(f"/api/v1/workspaces/{ws}/engineering-contexts").json():               # a channel belongs to one context
        client.delete(f"/api/v1/workspaces/{ws}/engineering-contexts/{existing['id']}")
    refs = {"VA": nf3e.src(sid, "VA"), "VB": nf3e.src(sid, "VB"), "VC": nf3e.src(sid, "VC"), "IA": ia_ref, "IB": nf3e.src(sid, "IB"), "IC": nf3e.src(sid, "IC")}
    members = [{"channel_ref": ref, "phase": n[1], "phase_source": "engineer_confirmed"} for n, ref in refs.items()]
    r = client.post(f"/api/v1/workspaces/{ws}/engineering-contexts", json={"display_name": "Bay 1", "status": "manual", "members": members})
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestPhasorFamilyAndOvercurrent:
    def _surfaces(self, client, ws, cid):
        base = f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}"
        return {
            "phasor": client.get(f"{base}/phasor", params={"analysis_kind": "phasor", "mode": "current_phase_a", "analysis_time": scn.FAULT_S}),
            "overcurrent": client.get(f"{base}/overcurrent", params={"analysis_time": scn.FAULT_S, **scn.OVERCURRENT}),
            "phasor_readiness": client.get(f"{base}/input-readiness", params={"analysis_kind": "phasor", "mode": "current_phase_a"}),
            "overcurrent_readiness": client.get(f"{base}/input-readiness", params={"analysis_kind": "overcurrent", "mode": "current_phase_a"}),
            "recorded_input": client.get(f"{base}/overcurrent-recorded-input", params={"phase": "A"}),
            "diagram": client.get(f"{base}/phasor-diagram", params={"analysis_time": scn.FAULT_S}),
        }

    def test_a_stale_channel_is_refused_with_the_stale_reason_not_the_form_reason(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms_ia", sid, channel="IA")
        cid = context_with(client, ws, sid, nf3e.calc(rms))
        form = self._surfaces(client, ws, cid)
        assert form["phasor"].json()["reason_code"] == "waveform_form_not_eligible"               # current RMS: unchanged form refusal
        assert form["overcurrent"].json()["reason_code"] == "waveform_form_not_eligible"
        nf3e.put_manual(client, ws, sid, 60.0)
        out = self._surfaces(client, ws, cid)
        for name in ("phasor", "overcurrent"):
            body = out[name].json()
            assert out[name].status_code == 200 and body["status"] == "needs_configuration" and body["reason_code"] == STALE, (name, body)
            assert "Create a new" in body["message"] and "'rms_ia'" in body["message"]
        for name in ("phasor_readiness", "overcurrent_readiness", "recorded_input", "diagram"):
            assert out[name].status_code == 200 and STALE in str(out[name].json()), (name, out[name].status_code, out[name].json())

    def test_a_transitively_stale_channel_is_refused(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms_ia", sid, channel="IA")
        absd = nf3e.create(client, ws, "abs_ia", "absolute_value", [nf3e.calc(rms)])["id"]
        cid = context_with(client, ws, sid, nf3e.calc(absd))
        nf3e.put_manual(client, ws, sid, 60.0)
        out = self._surfaces(client, ws, cid)
        assert out["phasor"].json()["reason_code"] == STALE and out["overcurrent"].json()["reason_code"] == STALE

    def test_a_valid_calculated_input_stays_accepted_and_restoring_the_frequency_lifts_the_refusal(self, client, ws):
        sid = rec(client, ws)
        valid = nf3e.create(client, ws, "ia_x1", "multiply_constant", [nf3e.src(sid, "IA")], {"constant": 1.0})["id"]    # instantaneous, never stale
        cid = context_with(client, ws, sid, nf3e.calc(valid))
        nf3e.put_manual(client, ws, sid, 60.0)
        nf3e.put_auto(client, ws, sid)
        ok = self._surfaces(client, ws, cid)
        assert ok["phasor"].json()["status"] == "computed"
        # recorded overcurrent already refuses a calculated current for its own reason (D5A: no measurement side for a calculated channel);
        # the point here is that the stale guard does not fire for a valid (non-stale) input and the existing behaviour is unchanged
        assert ok["overcurrent"].json()["reason_code"] == "calculated_channel_side_unavailable"
        rms = following(client, ws, "rms_ia", sid, channel="IA")
        stale_cid = context_with(client, ws, sid, nf3e.calc(rms))
        nf3e.put_manual(client, ws, sid, 60.0)
        assert self._surfaces(client, ws, stale_cid)["phasor"].json()["reason_code"] == STALE
        nf3e.put_auto(client, ws, sid)
        assert self._surfaces(client, ws, stale_cid)["phasor"].json()["reason_code"] == "waveform_form_not_eligible"    # back to the form rule

    def test_the_recorded_current_input_is_refused_too(self):
        text = (APP_DIR / "services" / "overcurrent_analysis_service.py").read_text(encoding="utf-8")
        assert text.count("isinstance(candidate, StaleInputBlocked)") == 3                           # compute, readiness, recorded input
        phasor = (APP_DIR / "services" / "phasor_analysis_service.py").read_text(encoding="utf-8")
        assert phasor.count("isinstance(candidate, StaleInputBlocked)") == 3                         # compute, diagram, readiness


class TestOneAuthorityAndTheSharedFetchersAreNotGuarded:
    def test_no_consumer_has_its_own_staleness_rule(self):
        users = {p.relative_to(APP_DIR).as_posix() for p in APP_DIR.rglob("*.py")
                 if "calculated_channel_staleness" in p.read_text(encoding="utf-8") and p.name != "calculated_channel_staleness.py"}
        assert users == {"api/v1/calculated_channels.py", "services/calculated_channel_service.py", "services/compliance_readiness_service.py",
                         "services/compliance_series.py", "services/line_to_line_voltage_service.py", "services/oscillation_representation_service.py",
                         "services/oscillation_spectrum_service.py", "services/overcurrent_analysis_service.py", "services/phasor_analysis_service.py"}
        for forbidden in ("nominal_frequency_basis", "BASIS_RECORDING"):
            for rel in ("services/compliance_series.py", "services/oscillation_spectrum_service.py", "services/phasor_analysis_service.py",
                        "services/overcurrent_analysis_service.py", "services/oscillation_representation_service.py"):
                assert forbidden not in (APP_DIR / rel).read_text(encoding="utf-8"), (rel, forbidden)

    @pytest.mark.parametrize("rel", ["services/calculated_timing_service.py", "services/waveform_service.py"])
    def test_the_shared_array_fetchers_used_by_historical_inspection_are_not_guarded(self, rel):
        assert "calculated_channel_staleness" not in (APP_DIR / rel).read_text(encoding="utf-8")
        text = (APP_DIR / "services" / "calculated_channel_service.py").read_text(encoding="utf-8")
        start = text.index("def _resolve_input(")
        assert "assert_inputs_not_stale" not in text[start:text.index("\ndef ", start + 10)]
