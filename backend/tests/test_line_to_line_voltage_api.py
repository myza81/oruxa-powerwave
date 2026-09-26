"""End-to-end tests for the Line-to-Line Voltage calculated-channel
operation (DEC-115), through the real FastAPI app.

Fixture: line_to_line_multibay(.cfg/.dat) -- 50 Hz, 1 kHz, 2 s, kV/kA:

- KPDN1_VR/VY/VB (+ IR/IY/IB): instantaneous phase-to-ground voltages
  with an unbalanced disturbance from 0.5 s (R sags to 30 %, Y shifts
  +15 deg) -> ready for All Three.
- KPDN2_VR/VY only -> VRY (canonical AB) available, VYB/VBR/All Three
  unavailable.
- MCRS_VR/VY/VB: RMS-magnitude envelopes -> unsupported representation.

Every bay here uses R/Y/B names, so DEC-118 makes every user-facing symbol
(default names, messages) follow R/Y/B while `phase_member`, role keys and
output keys stay canonical A/B/C. The mixed R/Y/B + A/B/C workspace is
covered by test_phase_display_convention.py.

Uploaded via the real endpoint so DEC-104's own upload-time preparation
creates the KPDN1/KPDN2/MCRS Engineering Contexts -- nothing seeded by
hand unless a test says so.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SQRT_3 = 1.7320508075688772
LL_FIXTURE = "line_to_line_multibay"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem=LL_FIXTURE, dat_stem=None):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{dat_stem or stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _contexts(client, ws):
    return {c["display_name"]: c for c in client.get(f"/api/v1/workspaces/{ws}/engineering-contexts").json()}


def _readiness(client, ws):
    resp = client.get(f"/api/v1/workspaces/{ws}/calculated-channels/line-to-line-voltage/readiness")
    assert resp.status_code == 200, resp.text
    return {r["display_name"]: r for r in resp.json()}


def _create(client, ws, context_id, output, **extra):
    return client.post(
        f"/api/v1/workspaces/{ws}/calculated-channels/line-to-line-voltage",
        json={"engineering_context_id": context_id, "output": output, **extra},
    )


def _list(client, ws):
    return client.get(f"/api/v1/workspaces/{ws}/calculated-channels").json()


def _source_values(client, ws, source_id, channel_name):
    active = client.app.state.workspace_registry.get(ws, source_id)
    return active.record.waveform_data[channel_name].to_numpy()


def _calc_values(client, ws, calc_id):
    return client.app.state.calculated_channel_registry.get(ws, calc_id).values


@pytest.fixture
def ws(client, comtrade_fixtures_dir):
    source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
    return {"id": "ws-1", "source_id": source_id, "contexts": _contexts(client, "ws-1")}


class TestReadiness:
    def test_every_bay_is_listed_with_explicit_status(self, client, ws):
        readiness = _readiness(client, ws["id"])
        assert set(readiness) == {"KPDN1", "KPDN2", "MCRS"}  # never hides a bay
        assert readiness["KPDN1"]["status"] == "ready"
        assert readiness["KPDN1"]["summary"] == "Ready for All Three"
        assert readiness["KPDN2"]["status"] == "incomplete"
        assert readiness["MCRS"]["status"] == "unsupported_representation"

    def test_single_pair_readiness_depends_on_selected_output(self, client, ws):
        outputs = _readiness(client, ws["id"])["KPDN2"]["outputs"]
        assert outputs["AB"]["available"] is True
        assert outputs["BC"]["available"] is False
        assert outputs["CA"]["available"] is False
        assert outputs["all_three"]["available"] is False
        # DEC-118: canonical C of an R/Y/B bay is spelled "B".
        assert "VB missing" in outputs["BC"]["reason"]
        summary = _readiness(client, ws["id"])["KPDN2"]["summary"]
        assert "VRY" in summary and "VB missing" in summary

    def test_rms_magnitude_only_is_rejected_with_actionable_reason(self, client, ws):
        mcrs = _readiness(client, ws["id"])["MCRS"]
        assert mcrs["roles"]["Va"]["status"] == "unsupported_representation"
        assert "RMS magnitudes alone are insufficient" in mcrs["outputs"]["AB"]["reason"]
        assert "instantaneous phase voltages" in mcrs["outputs"]["AB"]["reason"]
        assert mcrs["source_path"] is None

    def test_roles_report_resolved_channels(self, client, ws):
        roles = _readiness(client, ws["id"])["KPDN1"]["roles"]
        assert {k: r["channel_label"] for k, r in roles.items()} == {
            "Va": "KPDN1_VR", "Vb": "KPDN1_VY", "Vc": "KPDN1_VB",
        }
        assert all(r["unit"] == "kV" for r in roles.values())

    def test_readiness_is_read_only(self, client, ws):
        _readiness(client, ws["id"])
        assert _list(client, ws["id"]) == []


class TestAllThreeCreation:
    def test_creates_exactly_three_with_exact_pointwise_values(self, client, ws):
        resp = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        channels = body["channels"]
        # DEC-118: R/Y/B bay -> R/Y/B default names; phase_member stays canonical.
        assert [c["name"] for c in channels] == ["KPDN1 VRY", "KPDN1 VYB", "KPDN1 VBR"]
        assert [c["phase_member"] for c in channels] == ["AB", "BC", "CA"]
        assert len(_list(client, ws["id"])) == 3
        assert body["creation_batch_id"] and all(c["creation_batch_id"] == body["creation_batch_id"] for c in channels)

        va, vb, vc = (_source_values(client, ws["id"], ws["source_id"], n) for n in ("KPDN1_VR", "KPDN1_VY", "KPDN1_VB"))
        by_name = {c["name"]: c["id"] for c in channels}
        np.testing.assert_array_equal(_calc_values(client, ws["id"], by_name["KPDN1 VRY"]), va - vb)
        np.testing.assert_array_equal(_calc_values(client, ws["id"], by_name["KPDN1 VYB"]), vb - vc)
        np.testing.assert_array_equal(_calc_values(client, ws["id"], by_name["KPDN1 VBR"]), vc - va)

    def test_output_engineering_metadata(self, client, ws):
        channels = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three").json()["channels"]
        for channel, pair in zip(channels, ("AB", "BC", "CA")):
            assert channel["operation"] == "line_to_line_voltage"
            assert channel["engineering_type"] == "Voltage"
            assert channel["voltage_representation"] == "line_to_line"
            assert channel["phase_member"] == pair
            assert channel["waveform_form"] == "instantaneous"
            assert channel["unit"] == "kV"
            assert channel["parameters"]["pair"] == pair
            assert channel["parameters"]["source_path"] == "instantaneous"
            assert channel["parameters"]["engineering_context_id"] == ws["contexts"]["KPDN1"]["id"]
            assert channel["parameters"]["phase_display"]["convention"] == "RYB"
            assert channel["reference_source_id"] == ws["source_id"]
            assert len(channel["inputs"]) == 2

    def test_semantics_do_not_depend_on_the_name(self, client, ws):
        channels = _create(
            client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three",
            names={"AB": "first", "BC": "second", "CA": "third"},
        ).json()["channels"]
        assert [(c["name"], c["phase_member"]) for c in channels] == [("first", "AB"), ("second", "BC"), ("third", "CA")]

    def test_input_order_encodes_polarity(self, client, ws):
        channels = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three").json()["channels"]
        vca = channels[2]
        assert [i["channel_name"] for i in vca["inputs"]] == ["KPDN1_VB", "KPDN1_VR"]  # VC - VA


class TestAtomicity:
    def test_all_three_with_missing_phase_creates_nothing(self, client, ws):
        resp = _create(client, ws["id"], ws["contexts"]["KPDN2"]["id"], "all_three")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "line_to_line_inputs_unavailable"
        assert "nothing was created" in resp.json()["detail"]["message"]
        assert _list(client, ws["id"]) == []

    def test_all_three_with_one_name_collision_creates_nothing(self, client, ws):
        ok = _create(client, ws["id"], ws["contexts"]["KPDN2"]["id"], "AB", names={"AB": "KPDN1 VBR"})
        assert ok.status_code == 201
        resp = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "duplicate_calculated_channel_name"
        assert [c["name"] for c in _list(client, ws["id"])] == ["KPDN1 VBR"]

    def test_duplicate_names_within_one_request_create_nothing(self, client, ws):
        resp = _create(
            client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three", names={"AB": "same", "BC": "same"},
        )
        assert resp.status_code == 400
        assert _list(client, ws["id"]) == []

    def test_unsupported_representation_creates_nothing(self, client, ws):
        resp = _create(client, ws["id"], ws["contexts"]["MCRS"]["id"], "AB")
        assert resp.status_code == 400
        assert "RMS magnitudes alone are insufficient" in resp.json()["detail"]["message"]
        assert _list(client, ws["id"]) == []


class TestSinglePair:
    def test_available_pair_on_incomplete_bay(self, client, ws):
        resp = _create(client, ws["id"], ws["contexts"]["KPDN2"]["id"], "AB")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["creation_batch_id"] is None
        (channel,) = body["channels"]
        assert channel["name"] == "KPDN2 VRY"
        assert channel["phase_member"] == "AB"
        va, vb = (_source_values(client, ws["id"], ws["source_id"], n) for n in ("KPDN2_VR", "KPDN2_VY"))
        np.testing.assert_array_equal(_calc_values(client, ws["id"], channel["id"]), va - vb)

    @pytest.mark.parametrize("output", ["BC", "CA"])
    def test_unavailable_pair_is_rejected(self, client, ws, output):
        resp = _create(client, ws["id"], ws["contexts"]["KPDN2"]["id"], output)
        assert resp.status_code == 400
        assert "VB missing" in resp.json()["detail"]["message"]
        assert _list(client, ws["id"]) == []

    def test_each_pair_individually(self, client, ws):
        for output in ("AB", "BC", "CA"):
            assert _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], output).status_code == 201
        assert sorted(c["phase_member"] for c in _list(client, ws["id"])) == ["AB", "BC", "CA"]


class TestRequestValidation:
    def test_generic_endpoint_cannot_create_line_to_line(self, client, ws):
        resp = client.post(
            f"/api/v1/workspaces/{ws['id']}/calculated-channels",
            json={
                "name": "fake", "operation": "line_to_line_voltage",
                "inputs": [
                    {"kind": "source", "source_id": ws["source_id"], "channel_name": "KPDN1_VR"},
                    {"kind": "source", "source_id": ws["source_id"], "channel_name": "KPDN1_VY"},
                ],
            },
        )
        assert resp.status_code == 422

    def test_unknown_output_rejected(self, client, ws):
        assert _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "AC").status_code == 422

    def test_unknown_context_404(self, client, ws):
        resp = _create(client, ws["id"], "ec-nope", "AB")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "engineering_context_not_found"


class TestRoleGuardrails:
    def _set_phase(self, client, ws, context_name, channel_name, phase):
        context_id = ws["contexts"][context_name]["id"]
        resp = client.patch(
            f"/api/v1/workspaces/{ws['id']}/engineering-contexts/{context_id}/member-phase",
            json={
                "channel_ref": {"kind": "source", "source_id": ws["source_id"], "channel_name": channel_name},
                "phase": phase,
            },
        )
        assert resp.status_code == 200, resp.text

    def test_ambiguous_phase_is_reported_not_guessed(self, client, ws):
        self._set_phase(client, ws, "KPDN1", "KPDN1_VY", "A")  # two phase-A voltages now
        kpdn1 = _readiness(client, ws["id"])["KPDN1"]
        assert kpdn1["status"] == "ambiguous"
        assert kpdn1["roles"]["Va"]["status"] == "ambiguous"
        assert kpdn1["outputs"]["AB"]["available"] is False
        assert kpdn1["outputs"]["CA"]["available"] is False
        assert _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "AB").status_code == 400
        assert _list(client, ws["id"]) == []

    def test_non_voltage_member_never_satisfies_a_voltage_role(self, client, ws):
        """KPDN1's VR is taken out of phase A; a phase-A CURRENT (IR) is
        still present -- Va must be reported missing, never resolved to it."""
        self._set_phase(client, ws, "KPDN1", "KPDN1_VR", "N")
        kpdn1 = _readiness(client, ws["id"])["KPDN1"]
        assert kpdn1["roles"]["Va"]["status"] == "missing"
        assert kpdn1["outputs"]["BC"]["available"] is True
        assert kpdn1["outputs"]["AB"]["available"] is False

    def test_unknown_phase_identity(self, client, ws):
        self._set_phase(client, ws, "KPDN1", "KPDN1_VB", "unknown")
        kpdn1 = _readiness(client, ws["id"])["KPDN1"]
        assert kpdn1["roles"]["Vc"]["status"] == "phase_identity_missing"
        assert kpdn1["outputs"]["AB"]["available"] is True
        assert kpdn1["outputs"]["all_three"]["available"] is False

    def test_already_line_to_line_input_is_rejected(self, client, ws):
        """A calculated VAB assigned phase A must never be re-used as a
        phase-to-neutral input."""
        vab = _create(client, ws["id"], ws["contexts"]["KPDN2"]["id"], "AB").json()["channels"][0]
        context = client.post(
            f"/api/v1/workspaces/{ws['id']}/engineering-contexts",
            json={"display_name": "LLBAY", "members": [
                {"channel_ref": {"kind": "calculated", "calculated_channel_id": vab["id"]}, "phase": "A"},
            ]},
        ).json()
        readiness = _readiness(client, ws["id"])["LLBAY"]
        assert readiness["roles"]["Va"]["status"] == "unsupported_representation"
        assert "already a line-to-line quantity" in readiness["roles"]["Va"]["message"]
        assert _create(client, ws["id"], context["id"], "AB").status_code == 400


class TestCrossSourceGuardrails:
    """Manual multi-source bays: units and timebases are proven, never assumed."""

    def _manual_bay(self, client, ws_id, name, members):
        for context in client.get(f"/api/v1/workspaces/{ws_id}/engineering-contexts").json():
            claimed = {(m["channel_ref"].get("source_id"), m["channel_ref"].get("channel_name")) for m in context["members"]}
            if claimed & {(s, c) for s, c, _ in members}:
                client.delete(f"/api/v1/workspaces/{ws_id}/engineering-contexts/{context['id']}")
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/engineering-contexts",
            json={"display_name": name, "members": [
                {"channel_ref": {"kind": "source", "source_id": s, "channel_name": c}, "phase": p}
                for s, c, p in members
            ]},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_incompatible_units(self, client, ws, comtrade_fixtures_dir):
        other = _upload(client, ws["id"], comtrade_fixtures_dir, "mixed_capability_multibay")  # V, same instants
        context_id = self._manual_bay(client, ws["id"], "UNITBAY", [
            (ws["source_id"], "KPDN1_VR", "A"), (other, "KPDN1_VY", "B"),
        ])
        ab = _readiness(client, ws["id"])["UNITBAY"]["outputs"]["AB"]
        assert ab["available"] is False
        assert "different units" in ab["reason"]
        assert _create(client, ws["id"], context_id, "AB").status_code == 400

    def test_misaligned_timebase(self, client, ws, comtrade_fixtures_dir):
        a = _upload(client, ws["id"], comtrade_fixtures_dir, "mixed_capability_multibay")  # 10:00:00, V
        b = _upload(
            client, ws["id"], comtrade_fixtures_dir, "phasor_smoke_charlie_earlier_overlap", "phasor_smoke_three_phase",
        )  # 09:59:59, V
        context_id = self._manual_bay(client, ws["id"], "TIMEBAY", [(a, "KPDN2_VR", "A"), (b, "CHARLIE1_VB", "B")])
        ab = _readiness(client, ws["id"])["TIMEBAY"]["outputs"]["AB"]
        assert ab["available"] is False
        assert "not aligned" in ab["reason"]
        assert _create(client, ws["id"], context_id, "AB").status_code == 400


class TestNullPolicy:
    def test_null_policy_is_recorded_and_validated(self, client, ws):
        resp = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "AB", null_policy="treat_null_as_zero")
        assert resp.status_code == 201
        assert resp.json()["channels"][0]["null_policy"] == "treat_null_as_zero"
        bad = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "BC", estimation_method="linear")
        assert bad.status_code == 400
        assert bad.json()["detail"]["code"] == "estimation_fields_not_applicable"


class TestDependencyBehaviour:
    def test_individual_delete_keeps_siblings(self, client, ws):
        channels = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three").json()["channels"]
        resp = client.delete(f"/api/v1/workspaces/{ws['id']}/calculated-channels/{channels[0]['id']}")
        assert resp.status_code == 204
        assert sorted(c["name"] for c in _list(client, ws["id"])) == ["KPDN1 VBR", "KPDN1 VYB"]

    def test_calculated_from_line_to_line_and_dependency_block(self, client, ws):
        vab = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "AB").json()["channels"][0]
        rms = client.post(
            f"/api/v1/workspaces/{ws['id']}/calculated-channels",
            json={"name": "RMS VAB", "operation": "rms", "parameters": {"nominal_frequency_hz": 50},
                  "inputs": [{"kind": "calculated", "calculated_channel_id": vab["id"]}]},
        )
        assert rms.status_code == 201, rms.text
        assert rms.json()["engineering_type"] == "Voltage"
        blocked = client.delete(f"/api/v1/workspaces/{ws['id']}/calculated-channels/{vab['id']}")
        assert blocked.status_code == 400
        assert blocked.json()["detail"]["code"] == "calculated_channel_has_dependents"

    def test_source_removal_cascades(self, client, ws):
        _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three")
        assert client.delete(f"/api/v1/workspaces/{ws['id']}/sources/{ws['source_id']}").status_code == 204
        assert _list(client, ws["id"]) == []


class TestWaveformServing:
    def test_line_to_line_channel_serves_like_any_calculated_channel(self, client, ws):
        vab = _create(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "AB").json()["channels"][0]
        resp = client.get(f"/api/v1/workspaces/{ws['id']}/calculated-channels/{vab['id']}/waveform")
        assert resp.status_code == 200, resp.text
        assert resp.json()["unit"] == "kV"
        assert resp.json()["original_sample_count"] == 2000
