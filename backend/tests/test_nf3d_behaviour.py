"""NF-3D behaviour: the phasor family and overcurrent take their reference frequency from the central authority and refuse what it cannot supply.

What this proves (owner decisions D-2, O-5, O-6 and the NF-3D phases B-D):

* a USABLE declared or assumed frequency is computed exactly as before, and the result says where the frequency came from (origin + revision);
* an UNUSABLE declaration (0, negative, NaN, infinite, outside 1-1000 Hz) is a typed refusal (`invalid_reference_frequency`, HTTP 200), never
  an HTTP 500, never a substituted 50 Hz, and it never reaches the form detector or an estimator;
* a VALID frequency the sampling cannot support is a DIFFERENT refusal (`insufficient_sampling_density`), decided by the estimators' own
  minimum samples per cycle and never stricter than they are;
* an explicit `reference_frequency_hz` still wins and carries no provenance (it is the caller's own value);
* Manual (server gate open) is honoured and labelled `manual`; with the gate closed a stored Manual value is ignored;
* provenance describes the frequency actually used, per recording, and never leaks between sources or workspaces.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.overcurrent import OVERCURRENT_MIN_SAMPLES_PER_CYCLE, estimate_trailing_rms_at_time
from app.domain.phasor import PHASOR_MIN_SAMPLES_PER_CYCLE, REASON_INSUFFICIENT_SAMPLING_DENSITY, estimate_phasor
from app.main import create_app
from app.services import overcurrent_analysis_service as oc_service
from app.services import phasor_analysis_service as phasor_service
from app.services.analysis_reference_frequency import sampling_supports
from tests import nf3d_baseline_scenarios as scn

UNUSABLE = ("declared_zero", "declared_nan", "declared_inf", "declared_negative_50", "declared_0_5", "declared_1001")
ORIGINS = {"r50": "recording_metadata", "r60": "recording_metadata", "r50_fs4000": "recording_metadata", "r60_fs4000": "recording_metadata",
           "declared_50_on_60hz_signal": "recording_metadata", "assumed_50": "assumed_default", "assumed_on_60hz_signal": "assumed_default"}
INVALID_OVERRIDE_MESSAGE = "The supplied reference_frequency_hz is outside the plausible range."


def settings(tmp_path, enabled=False):
    return Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=("http://localhost:8101",),
                    database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
                    nominal_frequency_manual_override_enabled=enabled)


@pytest.fixture(scope="module")
def closed(tmp_path_factory):
    with TestClient(create_app(settings(tmp_path_factory.mktemp("nf3d-closed"))), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def opened(tmp_path_factory):
    with TestClient(create_app(settings(tmp_path_factory.mktemp("nf3d-open"), enabled=True)), raise_server_exceptions=False) as c:
        yield c


def bay(client, key, ws):
    fs, f, lf = scn.RECORDINGS[key]
    sid = scn.upload(client, ws, key, fs, f, lf)
    return sid, scn.context(client, ws, sid)


def get(client, ws, cid, path, **params):
    return client.get(f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}/{path}", params=params)


def phasor(client, ws, cid, **extra):
    return get(client, ws, cid, "phasor", analysis_kind="phasor", mode="voltage_three_phase", analysis_time=scn.PRE_FAULT_S, **extra)


def overcurrent(client, ws, cid, **extra):
    return get(client, ws, cid, "overcurrent", analysis_time=scn.FAULT_S, **scn.OVERCURRENT, **extra)


@pytest.fixture(scope="module")
def unusable_surfaces(closed):
    out = {}
    for key in UNUSABLE:
        sid, cid = bay(closed, key, f"ws-u-{key}")
        out[key] = (cid, scn.surfaces(closed, f"ws-u-{key}", cid), scn.readiness(closed, f"ws-u-{key}", cid))
    return out


# ------------------------------------------------------------------------------------------------ usable frequencies keep working
class TestAUsableFrequencyIsComputedAndLabelled:
    @pytest.mark.parametrize("key,hz", [("r50", 50.0), ("r60", 60.0), ("r50_fs4000", 50.0), ("r60_fs4000", 60.0)])
    def test_phasor_and_overcurrent_report_the_declared_frequency_and_its_origin(self, closed, key, hz):
        ws = f"ws-use-{key}"
        sid, cid = bay(closed, key, ws)
        p, o = phasor(closed, ws, cid).json(), overcurrent(closed, ws, cid).json()
        for body in (p, o):
            assert body["status"] == "computed" and body["reference_frequency_hz"] == hz
            assert (body["nominal_frequency_origin"], body["nominal_frequency_revision"]) == ("recording_metadata", 0)
            assert body["nominal_frequency_sources"] == [{"source_id": sid, "origin": "recording_metadata", "revision": 0}]

    def test_an_assumed_frequency_is_labelled_assumed_not_declared(self, closed):
        sid, cid = bay(closed, "assumed_50", "ws-assumed")
        b = phasor(closed, "ws-assumed", cid).json()
        assert b["status"] == "computed" and b["reference_frequency_hz"] == 50.0
        assert b["nominal_frequency_origin"] == "assumed_default"

    @pytest.mark.parametrize("path,params", [
        ("phasor-diagram", {"analysis_time": scn.FAULT_S}),
        ("impedance", {"phase": "A", "analysis_time": scn.FAULT_S, "impedance_basis": "secondary"}),
        ("sequence-components", {"analysis_time": scn.FAULT_S}),
    ])
    def test_the_downstream_analyses_carry_the_same_provenance(self, closed, path, params):
        sid, cid = bay(closed, "r60", f"ws-down-{path}")
        b = get(closed, f"ws-down-{path}", cid, path, **params).json()
        assert b["status"] == "computed" and b["reference_frequency_hz"] == 60.0
        assert b["nominal_frequency_origin"] == "recording_metadata"


# ------------------------------------------------------------------------------------------------ unusable declarations are refused
class TestAnUnusableDeclarationIsATypedRefusal:
    SURFACES = ("phasor_voltage_three_phase", "phasor_current_phase_a_fault", "phasor_diagram_fault", "overcurrent_pre_fault", "overcurrent_fault",
                "overcurrent_settled", "impedance_a", "impedance_locus_a", "sequence_components", "distance_ab")

    @pytest.mark.parametrize("key", UNUSABLE)
    def test_no_surface_is_an_internal_server_error(self, unusable_surfaces, key):
        _cid, surfaces, readiness = unusable_surfaces[key]
        for name, snap in {**surfaces, **readiness}.items():
            assert snap["status"] < 500, (key, name, snap)
            if name != "input_readiness_phasor":                 # that request shape is a 400 on every recording (a legacy query defect, not frequency)
                assert snap["status"] == 200, (key, name, snap)

    @pytest.mark.parametrize("key", UNUSABLE)
    def test_every_surface_refuses_and_computes_nothing(self, unusable_surfaces, key):
        _cid, surfaces, _readiness = unusable_surfaces[key]
        for name in self.SURFACES:
            body = surfaces[name]["body"]
            if name == "impedance_locus_a":
                assert all(point["status"] != "computed" for point in body["points"]), (key, name)
                continue
            assert body["status"] != "computed", (key, name)
            assert body.get("reference_frequency_hz") is None, (key, name)
            assert body["nominal_frequency_origin"] is None and body["nominal_frequency_sources"] == [], (key, name)

    @pytest.mark.parametrize("key", UNUSABLE)
    def test_the_reason_is_the_established_invalid_reference_frequency(self, unusable_surfaces, key):
        _cid, surfaces, _readiness = unusable_surfaces[key]
        for name in ("phasor_voltage_three_phase", "phasor_current_phase_a_fault", "phasor_diagram_fault", "overcurrent_fault"):
            assert surfaces[name]["body"]["reason_code"] == "invalid_reference_frequency", (key, name)

    def test_the_message_names_the_declared_value_and_offers_only_a_remedy_that_exists(self, unusable_surfaces):
        body = unusable_surfaces["declared_negative_50"][1]["phasor_voltage_three_phase"]["body"]
        assert "-50" in body["message"] and "reference_frequency_hz" in body["message"]
        assert "Recording Details" not in body["message"]               # the Manual gate is closed: that remedy does not exist

    def test_with_the_gate_open_the_message_may_offer_recording_details(self, opened):
        sid, cid = bay(opened, "declared_negative_50", "ws-open-msg")
        assert "Recording Details" in phasor(opened, "ws-open-msg", cid).json()["message"]

    def test_fifty_hertz_is_never_substituted_for_an_explicit_invalid_declaration(self, unusable_surfaces):
        for key in UNUSABLE:
            for name in self.SURFACES:
                assert unusable_surfaces[key][1][name]["body"].get("reference_frequency_hz") != 50.0, (key, name)

    def test_a_declared_value_outside_one_to_a_thousand_hertz_is_refused_even_though_it_is_finite_and_positive(self, unusable_surfaces):
        for key in ("declared_0_5", "declared_1001"):
            assert unusable_surfaces[key][1]["phasor_voltage_three_phase"]["body"]["reason_code"] == "invalid_reference_frequency"


class TestAnUnusableFrequencyNeverReachesAKernelOrTheDetector:
    @pytest.mark.parametrize("key", UNUSABLE)
    def test_no_detector_or_estimator_is_called(self, closed, monkeypatch, key):
        seen = []

        def spy(name, fn):
            def wrapper(*args, **kwargs):
                seen.append((name, args[-1] if name != "estimate_phasor" else args[3]))
                return fn(*args, **kwargs)
            return wrapper
        monkeypatch.setattr(phasor_service, "classify_waveform_form", spy("classify_waveform_form", phasor_service.classify_waveform_form))
        monkeypatch.setattr(phasor_service, "estimate_phasor", spy("estimate_phasor", phasor_service.estimate_phasor))
        monkeypatch.setattr(oc_service, "classify_waveform_form", spy("classify_waveform_form", oc_service.classify_waveform_form))
        monkeypatch.setattr(oc_service, "estimate_trailing_rms_at_time", spy("estimate_trailing_rms_at_time", oc_service.estimate_trailing_rms_at_time))
        ws = f"ws-spy-{key}"
        sid, cid = bay(closed, key, ws)
        assert phasor(closed, ws, cid).status_code == 200 and overcurrent(closed, ws, cid).status_code == 200
        get(closed, ws, cid, "phasor-diagram", analysis_time=scn.FAULT_S)
        assert seen == []

    def test_a_valid_frequency_reaches_them_with_exactly_that_frequency(self, closed, monkeypatch):
        seen = []
        real = phasor_service.estimate_phasor
        monkeypatch.setattr(phasor_service, "estimate_phasor", lambda *a, **k: (seen.append(a[3]), real(*a, **k))[1])
        sid, cid = bay(closed, "r60", "ws-spy-valid")
        assert phasor(closed, "ws-spy-valid", cid).json()["status"] == "computed"
        assert seen and set(seen) == {60.0}


# ------------------------------------------------------------------------------------------------ explicit overrides
class TestAnExplicitOverrideStillWinsAndHasNoProvenance:
    def test_a_valid_override_wins_over_an_unusable_declaration(self, closed):
        sid, cid = bay(closed, "declared_zero", "ws-ov-win")
        b = phasor(closed, "ws-ov-win", cid, reference_frequency_hz=50.0).json()
        assert b["status"] == "computed" and b["reference_frequency_hz"] == 50.0
        assert b["nominal_frequency_origin"] is None and b["nominal_frequency_revision"] is None and b["nominal_frequency_sources"] == []

    @pytest.mark.parametrize("hz", [0.0, -50.0, 1001.0])
    def test_an_invalid_override_keeps_the_existing_message(self, closed, hz):
        sid, cid = bay(closed, "r50", f"ws-ov-bad-{hz}")
        b = phasor(closed, f"ws-ov-bad-{hz}", cid, reference_frequency_hz=hz).json()
        assert b["reason_code"] == "invalid_reference_frequency" and b["message"] == INVALID_OVERRIDE_MESSAGE

    def test_an_override_is_used_even_when_it_differs_from_the_declaration(self, closed):
        sid, cid = bay(closed, "r50", "ws-ov-60")
        b = phasor(closed, "ws-ov-60", cid, reference_frequency_hz=60.0).json()
        assert b["reference_frequency_hz"] == 60.0 and b["nominal_frequency_origin"] is None


# ------------------------------------------------------------------------------------------------ Manual and the server gate
class TestManualFollowsTheServerGate:
    def _set_manual(self, client, ws, sid, hz):
        return client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": hz})

    @pytest.mark.parametrize("hz", [50, 60])
    def test_a_manual_value_makes_an_unusable_recording_computable_and_is_labelled_manual(self, opened, hz):
        ws = f"ws-man-{hz}"
        sid, cid = bay(opened, "declared_zero", ws)
        assert phasor(opened, ws, cid).json()["reason_code"] == "invalid_reference_frequency"
        assert self._set_manual(opened, ws, sid, hz).status_code == 200
        for b in (phasor(opened, ws, cid).json(), overcurrent(opened, ws, cid).json()):
            assert b["status"] == "computed" and b["reference_frequency_hz"] == float(hz)
            assert (b["nominal_frequency_origin"], b["nominal_frequency_revision"]) == ("manual", 1)
            assert b["nominal_frequency_sources"] == [{"source_id": sid, "origin": "manual", "revision": 1}]

    def test_a_manual_override_of_a_valid_declaration_is_what_the_calculation_uses(self, opened):
        sid, cid = bay(opened, "r50", "ws-man-over-valid")
        assert self._set_manual(opened, "ws-man-over-valid", sid, 60).status_code == 200
        b = phasor(opened, "ws-man-over-valid", cid).json()
        assert b["reference_frequency_hz"] == 60.0 and b["nominal_frequency_origin"] == "manual"

    def test_the_revision_advances_with_every_change_and_the_result_reports_the_current_one(self, opened):
        sid, cid = bay(opened, "r50", "ws-man-rev")
        for expected, hz in ((1, 60), (2, 50)):
            assert self._set_manual(opened, "ws-man-rev", sid, hz).status_code == 200
            assert phasor(opened, "ws-man-rev", cid).json()["nominal_frequency_revision"] == expected

    def test_clearing_the_manual_value_returns_to_the_recording_authority(self, opened):
        sid, cid = bay(opened, "declared_zero", "ws-man-clear")
        self._set_manual(opened, "ws-man-clear", sid, 50)
        assert opened.put(f"/api/v1/workspaces/ws-man-clear/sources/{sid}/nominal-frequency", json={"mode": "auto"}).status_code == 200
        assert phasor(opened, "ws-man-clear", cid).json()["reason_code"] == "invalid_reference_frequency"

    def test_with_the_gate_closed_the_endpoint_refuses_to_store_a_manual_value(self, closed):
        sid, cid = bay(closed, "declared_zero", "ws-gate-closed")
        r = self._set_manual(closed, "ws-gate-closed", sid, 50)
        assert r.status_code >= 400
        assert phasor(closed, "ws-gate-closed", cid).json()["reason_code"] == "invalid_reference_frequency"

    def test_a_manual_value_stored_while_open_is_ignored_when_the_gate_is_closed(self, tmp_path):
        from app.services.nominal_frequency_access import NominalFrequencyAccess
        app = create_app(settings(tmp_path / "a", enabled=True))
        with TestClient(app, raise_server_exceptions=False) as client:
            sid, cid = bay(client, "declared_zero", "ws-stale")
            assert self._set_manual(client, "ws-stale", sid, 50).status_code == 200
            assert phasor(client, "ws-stale", cid).json()["nominal_frequency_origin"] == "manual"
            access = app.state.nominal_frequency_access
            app.state.nominal_frequency_access = NominalFrequencyAccess(access._sources, access._registry, manual_override_enabled=False)
            b = phasor(client, "ws-stale", cid).json()
            assert b["reason_code"] == "invalid_reference_frequency" and b["nominal_frequency_origin"] is None

    def test_manual_is_never_described_as_a_measured_frequency(self, opened):
        sid, cid = bay(opened, "declared_zero", "ws-man-wording")
        self._set_manual(opened, "ws-man-wording", sid, 50)
        text = str(phasor(opened, "ws-man-wording", cid).json()).lower()
        assert "verified" not in text and "measured frequency" not in text


# ------------------------------------------------------------------------------------------------ provenance across recordings and workspaces
class TestProvenanceIsPerRecordingAndIsolated:
    def _two(self, client, a, b, ws):
        sids = {}
        for role, key in (("V", a), ("I", b)):
            fs, f, lf = scn.RECORDINGS[key]
            sids[role] = scn.upload(client, ws, f"{key}-{role}", fs, f, lf)
        members = [{"channel_ref": {"kind": "source", "source_id": sids["V" if n.startswith("V") else "I"], "channel_name": f"ALPHA1_{n}"},
                    "phase": n[1], "phase_source": "engineer_confirmed"} for n in scn.CHANNELS]
        r = client.post(f"/api/v1/workspaces/{ws}/engineering-contexts", json={"display_name": "Bay 1", "status": "manual", "members": members})
        assert r.status_code == 201, r.text
        return sids, r.json()["id"]

    def test_two_agreeing_recordings_with_one_origin_report_that_origin_and_both_sources(self, closed):
        sids, cid = self._two(closed, "r50", "r50", "ws-two-agree")
        b = get(closed, "ws-two-agree", cid, "phasor-diagram", analysis_time=scn.FAULT_S).json()
        assert b["status"] == "computed" and b["nominal_frequency_origin"] == "recording_metadata"
        assert b["nominal_frequency_revision"] is None                                 # revisions are per recording
        assert {s["source_id"] for s in b["nominal_frequency_sources"]} == set(sids.values())

    def test_two_agreeing_recordings_with_different_origins_report_no_single_origin(self, closed):
        sids, cid = self._two(closed, "assumed_50", "r50", "ws-two-mixed")
        b = get(closed, "ws-two-mixed", cid, "phasor-diagram", analysis_time=scn.FAULT_S).json()
        assert b["status"] == "computed" and b["nominal_frequency_origin"] is None
        assert {s["origin"] for s in b["nominal_frequency_sources"]} == {"assumed_default", "recording_metadata"}

    def test_differing_recordings_remain_a_conflict_with_no_provenance(self, closed):
        sids, cid = self._two(closed, "r50", "r60", "ws-two-conflict")
        b = get(closed, "ws-two-conflict", cid, "phasor-diagram", analysis_time=scn.FAULT_S).json()
        assert b["reason_code"] == "reference_frequency_conflict" and b["nominal_frequency_sources"] == []

    def test_an_unusable_second_recording_is_a_typed_refusal_for_both_analyses(self, closed):
        sids, cid = self._two(closed, "r50", "declared_zero", "ws-two-bad")
        d = get(closed, "ws-two-bad", cid, "phasor-diagram", analysis_time=scn.FAULT_S)
        o = overcurrent(closed, "ws-two-bad", cid)
        assert d.status_code == o.status_code == 200
        assert d.json()["reason_code"] == o.json()["reason_code"] == "invalid_reference_frequency"

    def test_overcurrent_reports_only_the_recording_that_supplied_the_current(self, closed):
        sids, cid = self._two(closed, "r50", "r60", "ws-two-oc")
        b = overcurrent(closed, "ws-two-oc", cid).json()
        assert b["status"] == "computed" and b["reference_frequency_hz"] == 60.0
        assert [s["source_id"] for s in b["nominal_frequency_sources"]] == [sids["I"]]

    def test_a_manual_value_on_one_recording_never_reaches_another_source_or_workspace(self, opened):
        sid1, cid1 = bay(opened, "r50", "ws-iso-1")
        sid2, cid2 = bay(opened, "r50", "ws-iso-1b")
        sid3, cid3 = bay(opened, "r50", "ws-iso-2")
        assert opened.put(f"/api/v1/workspaces/ws-iso-1/sources/{sid1}/nominal-frequency", json={"mode": "manual", "value_hz": 60}).status_code == 200
        assert phasor(opened, "ws-iso-1", cid1).json()["nominal_frequency_origin"] == "manual"
        for ws, cid in (("ws-iso-1b", cid2), ("ws-iso-2", cid3)):
            b = phasor(opened, ws, cid).json()
            assert b["nominal_frequency_origin"] == "recording_metadata" and b["reference_frequency_hz"] == 50.0

    def test_deleting_a_source_removes_its_manual_value(self, opened):
        sid, cid = bay(opened, "declared_zero", "ws-del")
        opened.put(f"/api/v1/workspaces/ws-del/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": 50})
        assert opened.delete(f"/api/v1/workspaces/ws-del/sources/{sid}").status_code in (200, 204)
        sid2, cid2 = bay(opened, "declared_zero", "ws-del")
        assert phasor(opened, "ws-del", cid2).json()["reason_code"] == "invalid_reference_frequency"


# ------------------------------------------------------------------------------------------------ Phase C: sampling eligibility
class TestASupportedFrequencyIsNotAnInvalidOne:
    def test_a_valid_frequency_the_sampling_cannot_hold_is_a_sampling_reason_not_an_invalid_frequency(self, closed):
        sid, cid = bay(closed, "r50", "ws-samp")
        b = phasor(closed, "ws-samp", cid, reference_frequency_hz=1000.0).json()          # 5 samples per cycle at 5 kHz
        assert b["reason_code"] == "insufficient_sampling_density"
        assert "samples per cycle" in b["message"] and "1000" in b["message"]

    def test_the_two_refusals_have_different_reason_codes(self, closed):
        sid, cid = bay(closed, "declared_negative_50", "ws-two-reasons")
        sid2, cid2 = bay(closed, "r50", "ws-two-reasons-b")
        assert phasor(closed, "ws-two-reasons", cid).json()["reason_code"] == "invalid_reference_frequency"
        assert phasor(closed, "ws-two-reasons-b", cid2, reference_frequency_hz=1000.0).json()["reason_code"] == "insufficient_sampling_density"

    def test_overcurrent_names_its_own_sampling_limit(self, closed):
        """Overcurrent needs 4 samples per cycle (not 8): a 2 kHz recording at an explicit 1000 Hz holds 2."""
        ws = "ws-samp-oc"
        sid = scn.upload(closed, ws, "r50_fs2000", 2000.0, 50.0, "50")
        cid = scn.context(closed, ws, sid)
        b = overcurrent(closed, ws, cid, reference_frequency_hz=1000.0).json()
        assert b["reason_code"] == "insufficient_sampling_density" and "4 samples per cycle" in b["message"]

    def test_overcurrent_computes_where_its_own_minimum_is_met_although_the_phasor_minimum_is_not(self, closed):
        """5 kHz at 1000 Hz is 5 samples per cycle: below the phasor's 8, above overcurrent's 4."""
        sid, cid = bay(closed, "r50", "ws-samp-oc-ok")
        assert phasor(closed, "ws-samp-oc-ok", cid, reference_frequency_hz=1000.0).json()["reason_code"] == "insufficient_sampling_density"
        assert overcurrent(closed, "ws-samp-oc-ok", cid, reference_frequency_hz=1000.0).json()["reason_code"] != "insufficient_sampling_density"

    def test_the_detector_is_not_asked_about_a_frequency_the_sampling_cannot_hold(self, closed, monkeypatch):
        seen = []
        monkeypatch.setattr(phasor_service, "classify_waveform_form", lambda *a, **k: seen.append(a) or pytest.fail("detector reached"))
        sid, cid = bay(closed, "r50", "ws-samp-spy")
        assert phasor(closed, "ws-samp-spy", cid, reference_frequency_hz=1000.0).json()["reason_code"] == "insufficient_sampling_density"
        assert seen == []

    def test_a_supported_sampling_still_computes_at_a_high_valid_frequency(self, closed):
        sid, cid = bay(closed, "r50_fs4000", "ws-samp-ok")
        b = phasor(closed, "ws-samp-ok", cid, reference_frequency_hz=400.0).json()           # 10 samples per cycle at 4 kHz
        assert b["reason_code"] != "insufficient_sampling_density"


GRID_FS = (1000.0, 2000.0, 2500.0, 3000.0, 4000.0, 5000.0, 6000.0)
GRID_F = (47.0, 50.0, 60.0, 100.0, 250.0, 333.0, 400.0, 500.0, 620.0, 710.0, 800.0, 1000.0)


class TestThePreCheckIsNeverStricterThanTheEstimators:
    """`sampling_supports` must refuse ONLY what the estimator itself could never compute, at any alignment of the window."""

    @staticmethod
    def _density_refused_everywhere(estimate, fs, f, min_samples):
        time = np.arange(0.0, 1.0, 1.0 / fs)
        values = np.sin(2 * np.pi * f * time)
        window = 1.0 / f
        refusals, computed = 0, 0
        for analysis_time in np.linspace(window + 0.05, 0.9, 97):
            result = estimate(time, values, float(analysis_time), f)
            if result.available:
                computed += 1
            elif result.reason_code == REASON_INSUFFICIENT_SAMPLING_DENSITY:
                refusals += 1
        return refusals, computed

    @pytest.mark.parametrize("fs", GRID_FS)
    @pytest.mark.parametrize("f", GRID_F)
    def test_phasor_rule_equals_the_estimators_best_case(self, fs, f):
        time = np.arange(0.0, 1.0, 1.0 / fs)
        refusals, computed = self._density_refused_everywhere(estimate_phasor, fs, f, PHASOR_MIN_SAMPLES_PER_CYCLE)
        supported = sampling_supports(time, f, PHASOR_MIN_SAMPLES_PER_CYCLE)
        if not supported:
            assert computed == 0, f"the pre-check refuses fs={fs} f={f} but the estimator computes it at {computed} analysis times"
        else:
            assert computed > 0, f"the pre-check allows fs={fs} f={f} yet the estimator never computes it"

    @pytest.mark.parametrize("fs", GRID_FS)
    @pytest.mark.parametrize("f", GRID_F)
    def test_overcurrent_rule_equals_the_estimators_best_case(self, fs, f):
        time = np.arange(0.0, 1.0, 1.0 / fs)
        refusals, computed = self._density_refused_everywhere(estimate_trailing_rms_at_time, fs, f, OVERCURRENT_MIN_SAMPLES_PER_CYCLE)
        supported = sampling_supports(time, f, OVERCURRENT_MIN_SAMPLES_PER_CYCLE)
        if not supported:
            assert computed == 0
        else:
            assert computed > 0

    def test_the_boundary_is_decided_by_ceil_of_samples_per_cycle(self):
        time = np.arange(0.0, 1.0, 1.0 / 4000.0)
        assert sampling_supports(time, 500.0, 8)                    # exactly 8 per cycle
        assert not sampling_supports(time, 600.0, 8)                # 6.67 per cycle: at most 7 samples
        assert sampling_supports(time, 540.0, 8)                    # 7.41 per cycle: a window can hold 8
        assert not sampling_supports(time, 571.5, 8)                # 7.0 per cycle: never more than 7

    def test_fewer_than_two_samples_is_left_to_the_estimators(self):
        assert sampling_supports(np.array([0.0]), 50.0, 8)
