"""NF-3E Phase B -- derived calculated-channel frequency staleness, the explicit-versus-recording-following intent, Option B (a stale input
is refused for a NEW calculation) and the eligibility 400 (O-10).

Policy (owner, 2026-11-27): stored values are preserved and never recomputed; a RECORDING-FOLLOWING RMS channel is stale while its stored
frequency differs from its grounding recording's effective frequency (and clears when they agree again); an EXPLICITLY selected frequency is
never stale on that account; intent is declared by the caller (`parameters.nominal_frequency_basis`), never inferred from numerical equality;
dependants inherit staleness transitively and inherited staleness clears only when every stale ancestor is current; power channels are not
assessed directly (NF-3F) but inherit; creating a new calculation on a stale input (direct or transitive) is refused with a typed error.
The state is derived on every request: nothing is stored, so nothing can go out of date.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.calculated_channel import CalculatedChannel, ChannelRef, OP_ACTIVE_POWER
from app.main import create_app
from tests import nf3d_baseline_scenarios as scn
from tests import nf3e_baseline_scenarios as nf3e

_ids = itertools.count(1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf3e_b")),
                        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100, git_sha="local",
                        version="local", nominal_frequency_manual_override_enabled=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def ws(client):
    return f"ws-nf3e-b-{next(_ids)}"


def rec(client, ws, name="r50", fs=5000.0, f=50.0, lf="50"):
    return scn.upload(client, ws, name, fs, f, lf)


def following(client, ws, name, sid, hz, channel="VA", **extra):
    return nf3e.create(client, ws, name, "rms", [nf3e.src(sid, channel)], {"nominal_frequency_hz": hz, "nominal_frequency_basis": "recording"}, **extra)


def explicit(client, ws, name, sid, hz, channel="VA"):
    return nf3e.create(client, ws, name, "rms", [nf3e.src(sid, channel)], {"nominal_frequency_hz": hz, "nominal_frequency_basis": "explicit"})


def listing(client, ws):
    r = client.get(f"/api/v1/workspaces/{ws}/calculated-channels")
    assert r.status_code == 200
    return {c["name"]: c for c in r.json()}


def staleness(client, ws, name):
    return listing(client, ws)[name]["frequency_staleness"]


def values(client, ws, cid):
    body = client.get(f"/api/v1/workspaces/{ws}/calculated-channels/{cid}/waveform", params={"point_budget": 100000}).json()
    return body["time"], body["values"]


class TestIntentAndProvenance:
    def test_a_recording_following_channel_records_its_basis_and_the_origin_and_revision_it_was_computed_with(self, client, ws):
        sid = rec(client, ws)
        made = following(client, ws, "f50", sid, 50)
        assert made["status"] == 201
        p = made["body"]["parameters"]
        assert p["nominal_frequency_hz"] == 50.0 and p["nominal_frequency_basis"] == "recording"
        assert p["nominal_frequency_origin"] == "recording_metadata" and p["nominal_frequency_revision"] == 0

    def test_an_explicit_channel_records_its_basis(self, client, ws):
        sid = rec(client, ws)
        p = explicit(client, ws, "e50", sid, 50)["body"]["parameters"]
        assert p["nominal_frequency_basis"] == "explicit" and p["nominal_frequency_hz"] == 50.0

    def test_an_omitted_basis_is_explicit_the_intent_is_never_inferred_from_equality_with_the_recording(self, client, ws):
        sid = rec(client, ws)
        made = nf3e.create(client, ws, "legacy_call", "rms", [nf3e.src(sid, "VA")], {"nominal_frequency_hz": 50})
        assert made["status"] == 201 and made["body"]["parameters"]["nominal_frequency_basis"] == "explicit"

    def test_the_origin_and_revision_follow_a_manual_value_at_creation(self, client, ws):
        sid = rec(client, ws)
        assert nf3e.put_manual(client, ws, sid, 60.0)["status"] == 200
        p = following(client, ws, "f60", sid, 60)["body"]["parameters"]
        assert (p["nominal_frequency_origin"], p["nominal_frequency_revision"]) == ("manual", 1)

    def test_a_recording_following_channel_whose_value_is_not_the_recordings_current_frequency_is_refused(self, client, ws):
        sid = rec(client, ws)
        made = following(client, ws, "f60_on_50", sid, 60)
        assert made["status"] == 400 and made["body"]["detail"]["code"] == "invalid_nominal_frequency"
        assert "50" in made["body"]["detail"]["message"] and "60" in made["body"]["detail"]["message"]
        assert listing(client, ws) == {}

    @pytest.mark.parametrize("basis", ["automatic", "", 5, True])
    def test_an_unknown_basis_is_refused(self, client, ws, basis):
        sid = rec(client, ws)
        made = nf3e.create(client, ws, "bad_basis", "rms", [nf3e.src(sid, "VA")], {"nominal_frequency_hz": 50, "nominal_frequency_basis": basis})
        assert made["status"] == 400 and made["body"]["detail"]["code"] == "invalid_nominal_frequency"


class TestRecordingFollowingStaleness:
    def test_a_manual_change_makes_a_following_channel_stale_with_the_reason_and_both_frequencies(self, client, ws):
        sid = rec(client, ws)
        following(client, ws, "f50", sid, 50)
        assert staleness(client, ws, "f50")["state"] == "current"
        nf3e.put_manual(client, ws, sid, 60.0)
        s = staleness(client, ws, "f50")
        assert s["state"] == "stale" and s["assessment"] == "frequency_aware"
        (cause,) = s["causes"]
        assert (cause["own"], cause["reason"], cause["stored_hz"], cause["effective_hz"]) == (True, "recording_frequency_changed", 50.0, 60.0)
        assert (cause["stored_origin"], cause["stored_revision"], cause["effective_origin"], cause["effective_revision"]) == (
            "recording_metadata", 0, "manual", 1)
        assert cause["channel_name"] == "f50"

    def test_returning_to_auto_or_setting_manual_to_the_stored_value_clears_the_staleness(self, client, ws):
        sid = rec(client, ws)
        following(client, ws, "f50", sid, 50)
        nf3e.put_manual(client, ws, sid, 60.0)
        assert staleness(client, ws, "f50")["state"] == "stale"
        nf3e.put_auto(client, ws, sid)
        assert staleness(client, ws, "f50")["state"] == "current"
        nf3e.put_manual(client, ws, sid, 60.0)
        nf3e.put_manual(client, ws, sid, 50.0)                       # a Manual value equal to the stored one is current again
        assert staleness(client, ws, "f50")["state"] == "current"

    def test_stale_values_are_preserved_and_never_recomputed(self, client, ws):
        sid = rec(client, ws)
        cid = following(client, ws, "f50", sid, 50)["id"]
        before = values(client, ws, cid)
        params = listing(client, ws)["f50"]["parameters"]
        nf3e.put_manual(client, ws, sid, 60.0)
        assert values(client, ws, cid) == before
        assert listing(client, ws)["f50"]["parameters"] == params
        nf3e.put_auto(client, ws, sid)
        assert values(client, ws, cid) == before

    def test_an_explicit_frequency_is_not_stale_because_it_differs_from_the_recording(self, client, ws):
        sid = rec(client, ws)
        explicit(client, ws, "e50", sid, 50)
        explicit(client, ws, "e60", sid, 60)                          # differs from the recording from the start
        nf3e.put_manual(client, ws, sid, 60.0)
        for name in ("e50", "e60"):
            assert staleness(client, ws, name)["state"] == "current", name

    def test_equal_numbers_with_different_intent_behave_differently(self, client, ws):
        sid = rec(client, ws)
        following(client, ws, "follow_50", sid, 50)
        explicit(client, ws, "explicit_50", sid, 50)
        nf3e.put_manual(client, ws, sid, 60.0)
        assert staleness(client, ws, "follow_50")["state"] == "stale"
        assert staleness(client, ws, "explicit_50")["state"] == "current"

    def test_a_recording_whose_frequency_became_unusable_makes_a_following_channel_stale_with_that_reason(self, client, ws):
        sid = rec(client, ws, name="declared_zero", lf="0")
        nf3e.put_manual(client, ws, sid, 60.0)
        following(client, ws, "f60", sid, 60)
        nf3e.put_auto(client, ws, sid)                                 # back to the unusable declared value: nothing to match
        s = staleness(client, ws, "f60")
        assert s["state"] == "stale" and s["causes"][0]["reason"] == "recording_frequency_unusable"
        assert s["causes"][0]["effective_hz"] is None

    def test_another_recordings_change_does_not_affect_the_channel(self, client, ws):
        a, b = rec(client, ws, "a"), rec(client, ws, "b")
        following(client, ws, "fa", a, 50)
        nf3e.put_manual(client, ws, b, 60.0)
        assert staleness(client, ws, "fa")["state"] == "current"


class TestInheritance:
    def _chain(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        add = nf3e.create(client, ws, "add", "addition", [nf3e.calc(rms), nf3e.calc(rms)])["id"]
        nf3e.create(client, ws, "abs", "absolute_value", [nf3e.calc(add)])
        return sid, rms

    def test_dependants_inherit_staleness_transitively_and_name_the_root_cause(self, client, ws):
        sid, _ = self._chain(client, ws)
        nf3e.put_manual(client, ws, sid, 60.0)
        for name in ("rms", "add", "abs"):
            s = staleness(client, ws, name)
            assert s["state"] == "stale", name
            assert [c["channel_name"] for c in s["causes"]] == ["rms"], name
        assert [staleness(client, ws, n)["causes"][0]["own"] for n in ("rms", "add", "abs")] == [True, False, False]
        assert staleness(client, ws, "add")["assessment"] == "inherited_only"

    def test_inherited_staleness_clears_with_the_root_cause(self, client, ws):
        sid, _ = self._chain(client, ws)
        nf3e.put_manual(client, ws, sid, 60.0)
        nf3e.put_auto(client, ws, sid)
        assert {n: staleness(client, ws, n)["state"] for n in ("rms", "add", "abs")} == {"rms": "current", "add": "current", "abs": "current"}

    def test_inherited_staleness_is_not_cleared_while_another_ancestor_is_still_stale(self, client, ws):
        a, b = rec(client, ws, "a"), rec(client, ws, "b")
        ra = following(client, ws, "rms_a", a, 50)["id"]
        rb = following(client, ws, "rms_b", b, 50)["id"]
        nf3e.create(client, ws, "sum", "addition", [nf3e.calc(ra), nf3e.calc(rb)])
        nf3e.put_manual(client, ws, a, 60.0)
        nf3e.put_manual(client, ws, b, 60.0)
        assert sorted(c["channel_name"] for c in staleness(client, ws, "sum")["causes"]) == ["rms_a", "rms_b"]
        nf3e.put_auto(client, ws, a)
        s = staleness(client, ws, "sum")
        assert s["state"] == "stale" and [c["channel_name"] for c in s["causes"]] == ["rms_b"]
        nf3e.put_auto(client, ws, b)
        assert staleness(client, ws, "sum")["state"] == "current"

    def test_each_ancestor_is_compared_with_its_own_recording_in_a_two_recording_channel(self, client, ws):
        a, b = rec(client, ws, "a"), rec(client, ws, "b")
        ra = following(client, ws, "rms_a", a, 50)["id"]
        rb = following(client, ws, "rms_b", b, 50)["id"]
        nf3e.create(client, ws, "sum", "addition", [nf3e.calc(ra), nf3e.calc(rb)])
        nf3e.put_manual(client, ws, b, 60.0)                            # only the NON-reference recording changes
        assert staleness(client, ws, "rms_a")["state"] == "current"
        s = staleness(client, ws, "sum")
        assert s["state"] == "stale" and [c["channel_name"] for c in s["causes"]] == ["rms_b"]

    def test_frequency_independent_channels_on_source_inputs_are_current_and_say_they_are_not_assessed(self, client, ws):
        sid = rec(client, ws)
        nf3e.create(client, ws, "sum_raw", "addition", [nf3e.src(sid, "VA"), nf3e.src(sid, "VB")])
        nf3e.put_manual(client, ws, sid, 60.0)
        s = staleness(client, ws, "sum_raw")
        assert (s["state"], s["assessment"], s["causes"]) == ("current", "inherited_only", [])

    def test_a_power_channel_is_not_assessed_directly_and_keeps_its_stored_parameters_on_a_60hz_recording(self, client, ws):
        sid = rec(client, ws, "r60", f=60.0, lf="60")
        made = nf3e.create(client, ws, "p", "active_power", [nf3e.src(sid, "VA"), nf3e.src(sid, "IA")])
        assert made["status"] == 201
        s = staleness(client, ws, "p")
        assert (s["state"], s["assessment"]) == ("current", "inherited_only")
        assert made["body"]["parameters"]["nominal_frequency_hz"] == 50.0
        nf3e.put_manual(client, ws, sid, 50.0)
        assert staleness(client, ws, "p")["state"] == "current"

    def test_a_power_channel_inherits_upstream_staleness(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        registry = client.app.state.calculated_channel_registry
        source = registry.get(ws, rms)
        registry.add(CalculatedChannel(
            id="calc-power-inherit", workspace_id=ws, name="p_over_rms", unit="W", operation=OP_ACTIVE_POWER,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=rms)] * 2,
            parameters={"nominal_frequency_hz": 50.0, "window_mode": "trailing", "sign_convention": "passive"},
            dependency_ids=[rms], reference_source_id=source.reference_source_id, time=source.time, values=np.array(source.values),
            created_at=source.created_at))
        assert staleness(client, ws, "p_over_rms")["state"] == "current"
        nf3e.put_manual(client, ws, sid, 60.0)
        s = staleness(client, ws, "p_over_rms")
        assert s["state"] == "stale" and s["assessment"] == "inherited_only" and [c["channel_name"] for c in s["causes"]] == ["rms"]


class TestStaleInputRefusal:
    """Option B: a NEW calculation on a stale input is refused with a typed, actionable error; nothing is written."""

    def test_a_direct_stale_input_is_refused_with_the_reason_and_a_remedy(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        made = nf3e.create(client, ws, "sum", "addition", [nf3e.calc(rms), nf3e.calc(rms)])
        assert made["status"] == 409 and made["body"]["detail"]["code"] == "stale_calculated_input"
        message = made["body"]["detail"]["message"]
        assert "rms" in message and "50" in message and "60" in message and "new" in message.lower()
        assert sorted(listing(client, ws)) == ["rms"]

    def test_a_transitive_stale_input_is_refused_and_names_the_root_cause(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        add = nf3e.create(client, ws, "add", "addition", [nf3e.calc(rms), nf3e.calc(rms)])["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        made = nf3e.create(client, ws, "abs", "absolute_value", [nf3e.calc(add)])
        assert made["status"] == 409 and made["body"]["detail"]["code"] == "stale_calculated_input"
        assert "'rms'" in made["body"]["detail"]["message"]

    def test_rms_of_a_stale_calculated_channel_is_refused(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        made = nf3e.create(client, ws, "rms_of_rms", "rms", [nf3e.calc(rms)], {"nominal_frequency_hz": 60}, override=True)
        assert made["status"] == 409 and made["body"]["detail"]["code"] == "stale_calculated_input"

    def test_source_inputs_are_never_refused_and_a_new_rms_at_the_current_frequency_is_allowed(self, client, ws):
        sid = rec(client, ws)
        following(client, ws, "rms50", sid, 50)
        nf3e.put_manual(client, ws, sid, 60.0)
        assert following(client, ws, "rms60", sid, 60)["status"] == 201
        assert nf3e.create(client, ws, "raw_sum", "addition", [nf3e.src(sid, "VA"), nf3e.src(sid, "VB")])["status"] == 201

    def test_the_refusal_lifts_when_the_staleness_clears(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        assert nf3e.create(client, ws, "s1", "addition", [nf3e.calc(rms), nf3e.calc(rms)])["status"] == 409
        nf3e.put_auto(client, ws, sid)
        assert nf3e.create(client, ws, "s1", "addition", [nf3e.calc(rms), nf3e.calc(rms)])["status"] == 201

    def test_an_explicit_channel_is_never_refused_as_an_input(self, client, ws):
        sid = rec(client, ws)
        rms = explicit(client, ws, "rms", sid, 50)["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        assert nf3e.create(client, ws, "s1", "addition", [nf3e.calc(rms), nf3e.calc(rms)])["status"] == 201

    def test_stale_channels_remain_viewable_and_deletable(self, client, ws):
        sid = rec(client, ws)
        rms = following(client, ws, "rms", sid, 50)["id"]
        nf3e.put_manual(client, ws, sid, 60.0)
        assert client.get(f"/api/v1/workspaces/{ws}/calculated-channels/{rms}/waveform").status_code == 200
        assert client.delete(f"/api/v1/workspaces/{ws}/calculated-channels/{rms}").status_code == 204

    def test_the_readiness_identity_never_reuses_a_stale_channel(self, client, ws):
        from app.services.compliance_readiness_service import find_equivalent_rms
        sid = rec(client, ws)
        following(client, ws, "rms50", sid, 50)
        reg, access = client.app.state.calculated_channel_registry, client.app.state.nominal_frequency_access
        ref = nf3e.ref(sid, "VA")
        assert find_equivalent_rms(reg, ws, ref, 50.0, frequency_access=access).name == "rms50"
        nf3e.put_manual(client, ws, sid, 60.0)
        assert find_equivalent_rms(reg, ws, ref, 50.0, frequency_access=access) is None


class TestEligibilityInvalidFrequencyIs400:
    """O-10: an invalid user-supplied frequency is a client error (400), not an HTTP 500; a genuine internal failure stays a 500."""

    def _post(self, client, ws, sid, hz):
        return client.post(f"/api/v1/workspaces/{ws}/calculated-channels/rms-eligibility",
                           json={"input": nf3e.src(sid, "VA"), "nominal_frequency_hz": hz})

    @pytest.mark.parametrize("hz", [0, -50, 0.5, 1001])
    def test_an_invalid_frequency_is_a_typed_400(self, client, ws, hz):
        sid = rec(client, ws)
        r = self._post(client, ws, sid, hz)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_nominal_frequency"

    @pytest.mark.parametrize("hz", [50, 60])
    def test_a_valid_frequency_is_unchanged(self, client, ws, hz):
        sid = rec(client, ws)
        r = self._post(client, ws, sid, hz)
        assert r.status_code == 200 and r.json()["status"] == "suitable"

    def test_an_unexpected_internal_failure_is_not_turned_into_a_client_error(self, client, ws, monkeypatch):
        sid = rec(client, ws)
        import app.api.v1.calculated_channels as api

        def boom(**_):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(api, "check_rms_eligibility", boom)
        assert self._post(client, ws, sid, 50).status_code == 500


class TestEveryProductionCreationPathUsesTheAuthority:
    """The refusal and the provenance stamp need the accessor; a production caller that forgot it would silently skip them."""

    def test_every_production_call_of_create_calculated_channel_passes_the_frequency_authority(self):
        import ast
        from pathlib import Path
        app_dir = Path(__file__).resolve().parents[1] / "app"
        calls = []
        for path in app_dir.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "create_calculated_channel":
                    calls.append((path.name, {k.arg for k in node.keywords}))
        assert {name for name, _ in calls} == {"calculated_channels.py", "compliance_readiness_service.py"}
        assert all("frequency_access" in keywords for _, keywords in calls), calls

    def test_line_to_line_creation_checks_its_operands(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "app" / "services" / "line_to_line_voltage_service.py").read_text(encoding="utf-8")
        assert "assert_inputs_not_stale(" in text
