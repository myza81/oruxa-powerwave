"""DEC-167 -- Reference-driven Measurement readiness and shared
preparation, end to end through the real FastAPI app.

> Reference defines. Measurement satisfies.
> Compliance never owns a private RMS channel or private per-unit
> configuration.

Fixture `line_to_line_multibay` (50 Hz, kV, uploaded through the real
endpoint so DEC-104 builds the Measurement Groups and Engineering
Contexts -- nothing is seeded by hand):

- KPDN1 VOLTAGE: VR/VY/VB instantaneous            -> every case that needs preparation
- KPDN2 VOLTAGE: VR/VY only                         -> a missing phase
- MCRS  VOLTAGE: VR/VY/VB already-RMS envelopes     -> RMS reused directly / no safe line-line

The spec's own validation cases A-H are named in the test names.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

WS = "ws-readiness-1"
FIXTURE = "line_to_line_multibay"


@pytest.fixture
def client(settings, comtrade_fixtures_dir):
    app = create_app(settings)
    with TestClient(app) as test_client:
        cfg = (comtrade_fixtures_dir / f"{FIXTURE}.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / f"{FIXTURE}.dat").read_bytes()
        files = {
            "cfg_file": (f"{FIXTURE}.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": (f"{FIXTURE}.dat", io.BytesIO(dat), "application/octet-stream"),
        }
        response = test_client.post(f"/api/v1/workspaces/{WS}/sources", files=files)
        assert response.status_code == 201, response.text
        yield test_client


def _groups(client) -> dict:
    rows = client.get(f"/api/v1/workspaces/{WS}/compliance/voltage/measurement-groups").json()
    return {row["display_name"].split()[0]: row for row in rows}


def _add_reference(client, *, name="Ref", representation="line_line_rms", treatment="each_phase", member=None,
                   unit="pu", visible=True) -> dict:
    body = {
        "name": name, "category": "grid_requirement",
        "assessment_definition": {"representation": representation, "phase_treatment": treatment, "member": member},
        "unit": unit, "display_start_time": 0, "display_end_time": 3, "evaluation_start_time": 0,
        "evaluation_end_time": 3, "tolerance": 0,
        "lower_boundary": {"segments": [
            {"start_time": 0, "end_time": 3, "start_value": 0.9, "end_value": 0.9, "segment_type": "constant"}]},
        "upper_boundary": None, "metadata": {},
    }
    profile = client.post(f"/api/v1/workspaces/{WS}/reference-profiles", json=body)
    assert profile.status_code == 201, profile.text
    layer = client.post(f"/api/v1/workspaces/{WS}/reference-layers", json={"profile_id": profile.json()["id"], "visible": visible})
    assert layer.status_code == 201, layer.text
    return layer.json()


def _readiness(client, bay: str) -> dict:
    group = _groups(client)[bay]
    response = client.get(
        f"/api/v1/workspaces/{WS}/compliance/voltage/readiness", params={"measurement_group_id": group["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _prepare(client, bay: str) -> dict:
    group = _groups(client)[bay]
    response = client.post(
        f"/api/v1/workspaces/{WS}/compliance/voltage/prepare", json={"measurement_group_id": group["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _calc_channels(client) -> list[dict]:
    return client.get(f"/api/v1/workspaces/{WS}/calculated-channels").json()


def _set_base(client, bay: str, kv: float = 132.0) -> None:
    group = _groups(client)[bay]
    response = client.put(
        f"/api/v1/workspaces/{WS}/sources/{group['source_id']}/measurement-groups/{group['id']}/voltage-config",
        json={"nominal_voltage_ll_kv": kv, "reference_mode": "auto"},
    )
    assert response.status_code == 200, response.text
    # Saving a base in the group editor also promotes a suggested group to
    # confirmed (the UI's own behaviour) -- until then the shared per-unit
    # configuration is deliberately not applied.
    confirm = client.patch(
        f"/api/v1/workspaces/{WS}/sources/{group['source_id']}/measurement-groups/{group['id']}",
        json={"status": "confirmed"},
    )
    assert confirm.status_code == 200, confirm.text


def _states(readiness: dict, ref_index: int = 0) -> dict:
    return {m["member"]: m["state"] for m in readiness["references"][ref_index]["members"]}


class TestRequirementComesFromTheReference:
    def test_no_active_reference_means_nothing_is_required_or_ready(self, client):
        readiness = _readiness(client, "KPDN1")
        assert readiness["status"] == "no_reference"
        assert readiness["references"] == [] and readiness["steps"] == [] and readiness["needs_base"] is False

    def test_line_line_each_phase_pu_requires_all_three_pairs_rms_and_a_base(self, client):
        _add_reference(client)
        requirement = _readiness(client, "KPDN1")["references"][0]["requirement"]
        assert requirement == {
            "representation": "line_line_rms", "phase_treatment": "each_phase", "member": None, "unit": "pu",
            "required_members": ["AB", "BC", "CA"], "requires_rms": True, "requires_per_unit": True,
            "unresolved_reason": None,
        }

    def test_single_requires_only_the_named_voltage_case_g(self, client):
        _add_reference(client, treatment="single", member="AB")
        readiness = _readiness(client, "KPDN1")
        assert readiness["references"][0]["requirement"]["required_members"] == ["AB"]
        assert [s["description"] for s in readiness["steps"]] == ["Line-line voltage VRY"]

    @pytest.mark.parametrize("treatment", ["each_phase", "minimum", "maximum"])
    def test_each_minimum_maximum_all_require_the_whole_set_case_h(self, client, treatment):
        _add_reference(client, treatment=treatment)
        assert _readiness(client, "KPDN1")["references"][0]["requirement"]["required_members"] == ["AB", "BC", "CA"]

    def test_kv_reference_has_no_per_unit_requirement_case_d(self, client):
        _add_reference(client, unit="kV")
        readiness = _readiness(client, "KPDN1")
        reference = readiness["references"][0]
        assert reference["requirement"]["requires_per_unit"] is False
        assert reference["unit_state"] == "not_required" and reference["unit_message"] is None
        assert readiness["needs_base"] is False
        # RMS is still required, because the representation says RMS.
        assert reference["requirement"]["requires_rms"] is True

    def test_a_reference_that_states_too_little_is_incompatible_and_says_where_to_fix_it(self, client):
        body = {
            "name": "Legacy", "category": "custom_reference", "assessment_definition": {}, "unit": "pu",
            "display_start_time": 0, "display_end_time": 3, "evaluation_start_time": 0, "evaluation_end_time": 3,
            "tolerance": 0, "upper_boundary": None, "metadata": {},
            "lower_boundary": {"segments": [{"start_time": 0, "end_time": 3, "start_value": 1, "end_value": 1, "segment_type": "constant"}]},
        }
        profile = client.post(f"/api/v1/workspaces/{WS}/reference-profiles", json=body).json()
        client.post(f"/api/v1/workspaces/{WS}/reference-layers", json={"profile_id": profile["id"], "visible": True})
        readiness = _readiness(client, "KPDN1")
        assert readiness["status"] == "incompatible"
        assert "Edit the Reference Profile" in readiness["references"][0]["message"]

    def test_a_hidden_layer_imposes_no_requirement(self, client):
        _add_reference(client, visible=False)
        assert _readiness(client, "KPDN1")["status"] == "no_reference"


class TestCaseAPuRequiredNothingPrepared:
    def test_action_required_with_both_actions_never_a_false_ready(self, client):
        _add_reference(client)
        readiness = _readiness(client, "KPDN1")
        assert readiness["status"] == "action_required"
        assert readiness["needs_base"] is True
        assert _states(readiness) == {"AB": "needs_line_to_line", "BC": "needs_line_to_line", "CA": "needs_line_to_line"}
        assert [s["kind"] for s in readiness["steps"]] == ["line_to_line"] * 3
        assert all(s["executable"] for s in readiness["steps"])
        assert readiness["references"][0]["unit_state"] == "action_required"
        assert "voltage base" in readiness["references"][0]["unit_message"]

    def test_readiness_itself_never_creates_anything(self, client):
        _add_reference(client)
        _readiness(client, "KPDN1")
        _readiness(client, "KPDN1")
        assert _calc_channels(client) == []


class TestSharedRmsPreparation:
    def test_prepare_creates_ordinary_shared_calculated_channels(self, client):
        _add_reference(client)
        outcome = _prepare(client, "KPDN1")
        assert [c["operation"] for c in outcome["created"]] == ["line_to_line_voltage"] * 3 + ["rms"] * 3
        # They are normal Calculated Channels -- visible to every consumer of the shared registry.
        listed = {c["id"]: c for c in _calc_channels(client)}
        assert {c["id"] for c in outcome["created"]} <= set(listed)
        assert [c["operation"] for c in _calc_channels(client)].count("rms") == 3
        assert all(c["name"].startswith("RMS (") for c in outcome["created"] if c["operation"] == "rms")
        # Only the pu base remains.
        assert outcome["readiness"]["status"] == "action_required"
        assert outcome["readiness"]["steps"] == []
        assert outcome["readiness"]["needs_base"] is True
        assert set(_states(outcome["readiness"]).values()) == {"reused"}

    def test_prepare_is_idempotent_no_duplicate_rms_channels(self, client):
        _add_reference(client)
        _prepare(client, "KPDN1")
        count = len(_calc_channels(client))
        second = _prepare(client, "KPDN1")
        assert second["created"] == []
        assert len(_calc_channels(client)) == count

    def test_two_references_needing_the_same_rms_share_one_set(self, client):
        _add_reference(client, name="A", unit="pu")
        _add_reference(client, name="B", unit="kV", treatment="minimum")
        readiness = _readiness(client, "KPDN1")
        assert len(readiness["steps"]) == 3  # deduplicated across References
        _prepare(client, "KPDN1")
        assert [c["operation"] for c in _calc_channels(client)].count("rms") == 3

    def test_phase_ground_requirement_needs_only_rms_no_line_line(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        readiness = _readiness(client, "KPDN1")
        assert _states(readiness) == {"A": "needs_rms", "B": "needs_rms", "C": "needs_rms"}
        outcome = _prepare(client, "KPDN1")
        assert [c["operation"] for c in outcome["created"]] == ["rms"] * 3
        assert outcome["readiness"]["status"] == "ready"

    def test_single_voltage_prepares_only_what_it_needs_case_g(self, client):
        _add_reference(client, treatment="single", member="AB", unit="kV")
        outcome = _prepare(client, "KPDN1")
        assert [c["operation"] for c in outcome["created"]] == ["line_to_line_voltage", "rms"]
        assert outcome["readiness"]["status"] == "ready"


class TestCaseBExistingCalculatedChannelsAreReused:
    def test_rms_and_line_line_created_elsewhere_are_discovered_and_reused(self, client):
        # The engineer created them in Calculated Channels first.
        contexts = {c["display_name"]: c for c in client.get(f"/api/v1/workspaces/{WS}/engineering-contexts").json()}
        made = client.post(
            f"/api/v1/workspaces/{WS}/calculated-channels/line-to-line-voltage",
            json={"engineering_context_id": contexts["KPDN1"]["id"], "output": "all_three"},
        )
        assert made.status_code == 201, made.text
        for channel in made.json()["channels"]:
            rms = client.post(f"/api/v1/workspaces/{WS}/calculated-channels", json={
                "name": f"my own name for {channel['name']}", "operation": "rms",
                "inputs": [{"kind": "calculated", "calculated_channel_id": channel["id"]}],
                "parameters": {"nominal_frequency_hz": 50.0},
            })
            assert rms.status_code == 201, rms.text
        before = {c["id"] for c in _calc_channels(client)}

        _add_reference(client, unit="kV")
        readiness = _readiness(client, "KPDN1")
        assert readiness["status"] == "ready"  # reuse is by identity: the custom NAMES do not matter
        assert set(_states(readiness).values()) == {"reused"}
        assert readiness["steps"] == []
        assert _prepare(client, "KPDN1")["created"] == []
        assert {c["id"] for c in _calc_channels(client)} == before

    def test_an_rms_channel_with_a_different_frequency_is_not_equivalent(self, client):
        contexts = {c["display_name"]: c for c in client.get(f"/api/v1/workspaces/{WS}/engineering-contexts").json()}
        client.post(
            f"/api/v1/workspaces/{WS}/calculated-channels/line-to-line-voltage",
            json={"engineering_context_id": contexts["KPDN1"]["id"], "output": "AB"},
        )
        ab = [c for c in _calc_channels(client) if c["operation"] == "line_to_line_voltage"][0]
        client.post(f"/api/v1/workspaces/{WS}/calculated-channels", json={
            "name": "RMS (60 Hz)", "operation": "rms",
            "inputs": [{"kind": "calculated", "calculated_channel_id": ab["id"]}],
            "parameters": {"nominal_frequency_hz": 60.0},
        })
        _add_reference(client, treatment="single", member="AB", unit="kV")
        readiness = _readiness(client, "KPDN1")
        assert _states(readiness) == {"AB": "needs_rms"}


class TestCaseEAlreadyRmsSourceIsUsedDirectly:
    def test_no_new_calculated_channel_is_created(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        readiness = _readiness(client, "MCRS")
        assert set(_states(readiness).values()) == {"source_rms"}
        assert readiness["status"] == "ready" and readiness["steps"] == []
        assert _prepare(client, "MCRS")["created"] == []
        assert _calc_channels(client) == []


class TestCaseFUnsafeLineLineIsBlocked:
    def test_angle_less_phase_rms_never_yields_line_line(self, client):
        _add_reference(client, unit="kV")
        readiness = _readiness(client, "MCRS")
        assert readiness["status"] == "incompatible"
        message = readiness["references"][0]["message"]
        assert "unsafe" in message and "phase angle" in message
        assert readiness["steps"] == []
        assert _prepare(client, "MCRS")["created"] == []

    def test_positive_sequence_has_no_time_series_product_yet_so_it_is_never_ready(self, client):
        """DEC-169: Ready must mean a trace can actually be produced. No shared
        positive-sequence time series exists, so even instantaneous phases are
        reported honestly as unable to satisfy the Reference."""
        _add_reference(client, representation="positive_sequence_rms", treatment="single", unit="kV")
        assert _readiness(client, "MCRS")["status"] == "incompatible"
        instantaneous = _readiness(client, "KPDN1")
        assert instantaneous["status"] == "incompatible"
        assert "positive-sequence" in instantaneous["references"][0]["message"]
        assert instantaneous["steps"] == []

    def test_a_missing_phase_is_incompatible_not_action_required(self, client):
        _add_reference(client, unit="kV")
        readiness = _readiness(client, "KPDN2")
        assert readiness["status"] == "incompatible"
        assert "missing" in readiness["references"][0]["message"].lower()


class TestCaseCBaseIsTheSharedGroupConfiguration:
    def test_base_configured_through_the_existing_group_endpoint_is_reused(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="pu")
        _prepare(client, "KPDN1")
        assert _readiness(client, "KPDN1")["status"] == "action_required"
        _set_base(client, "KPDN1", 132.0)  # the SAME endpoint Per-Unit Settings / Waveform use
        readiness = _readiness(client, "KPDN1")
        assert readiness["base"]["nominal_voltage_ll_kv"] == 132.0
        assert readiness["needs_base"] is False
        assert readiness["references"][0]["unit_state"] == "ready"
        assert readiness["status"] == "ready"

    def test_the_base_is_the_group_configuration_not_a_compliance_copy(self, client):
        group = _groups(client)["KPDN1"]
        registry = client.app.state.voltage_group_config_registry
        _add_reference(client, unit="pu")
        assert registry.get(WS, group["id"]) is None
        _prepare(client, "KPDN1")  # preparing never writes a base
        assert registry.get(WS, group["id"]) is None
        _set_base(client, "KPDN1", 275.0)
        stored = registry.get(WS, group["id"])
        assert stored is not None and stored.nominal_voltage_ll_kv == 275.0
        assert _readiness(client, "KPDN1")["base"]["nominal_voltage_ll_kv"] == 275.0

    def test_base_is_per_group(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="pu")
        _set_base(client, "KPDN1", 132.0)
        assert _readiness(client, "KPDN1")["needs_base"] is False
        assert _readiness(client, "MCRS")["needs_base"] is True


class TestSeveralReferences:
    def test_one_incompatible_reference_is_never_hidden_by_a_satisfiable_one(self, client):
        _add_reference(client, name="Phase-ground", representation="phase_ground_rms", unit="kV")
        _add_reference(client, name="Line-line", unit="kV")
        readiness = _readiness(client, "MCRS")
        statuses = {r["profile_name"]: r["status"] for r in readiness["references"]}
        assert statuses == {"Phase-ground": "ready", "Line-line": "incompatible"}
        assert readiness["status"] == "incompatible"


class TestErrors:
    def test_unknown_group_is_404(self, client):
        response = client.get(
            f"/api/v1/workspaces/{WS}/compliance/voltage/readiness", params={"measurement_group_id": "mg-nope"},
        )
        assert response.status_code == 404

    def test_groups_expose_their_source_for_the_existing_group_editor(self, client):
        for group in _groups(client).values():
            assert group["source_id"]


class TestReadyMeansTheTraceCanBeProduced:
    """DEC-169: metadata readiness is not Ready; the measurement product must be resolvable."""

    def test_pu_with_a_base_set_but_group_not_confirmed_is_action_required_not_ready(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="pu")
        _prepare(client, "KPDN1")
        group = _groups(client)["KPDN1"]
        client.put(
            f"/api/v1/workspaces/{WS}/sources/{group['source_id']}/measurement-groups/{group['id']}/voltage-config",
            json={"nominal_voltage_ll_kv": 132.0, "reference_mode": "auto"},
        )  # base saved but the suggested group is NOT confirmed
        readiness = _readiness(client, "KPDN1")
        assert readiness["status"] == "action_required"
        assert readiness["references"][0]["unit_state"] == "action_required"
        assert "confirm" in readiness["references"][0]["message"].lower()
        assert readiness["needs_base"] is True
        _set_base(client, "KPDN1", 132.0)  # confirm, as the editor's Save does
        assert _readiness(client, "KPDN1")["status"] == "ready"

    def test_kv_reference_is_ready_without_any_base(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        _prepare(client, "KPDN1")
        assert _readiness(client, "KPDN1")["status"] == "ready"
