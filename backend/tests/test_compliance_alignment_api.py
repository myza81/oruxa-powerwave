"""DEC-170 -- Compliance-local Event Alignment.

> Compliance Event Alignment is an assessment-local horizontal offset between
> the selected measurement and the Reference Layers. It is NOT Waveform t0.

Domain rules (sign convention, nearest-sample snapping) and the API lifecycle,
including the core product requirement: **no state is shared with Waveform t0**.
Fixture `line_to_line_multibay`: 1 kHz, 2 s -> samples every 1 ms.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.compliance_alignment import (
    FINE_SHIFT_STEP_S,
    alignment_offset_s,
    comparison_time,
    require_finite_origin,
    snap_to_sample,
)
from tests.test_compliance_readiness_api import (  # noqa: F401  (fixture re-export)
    WS,
    _add_reference,
    _groups,
    _prepare,
    client,
)

URL = f"/api/v1/workspaces/{WS}/compliance/voltage/event-alignment"


class TestDomainRules:
    def test_sign_convention_event_moves_to_reference_zero(self):
        assert comparison_time(0.550, 0.550) == 0.0                 # the marked event lands on Reference t = 0
        assert comparison_time(0.700, 0.550) == pytest.approx(0.150)
        assert alignment_offset_s(0.550) == -0.550                   # added to a measurement time

    def test_snap_picks_the_nearest_actual_sample(self):
        times = np.array([0.0, 0.001, 0.002, 0.003])
        assert snap_to_sample(times, 0.0014) == 0.001
        assert snap_to_sample(times, 0.0016) == 0.002
        assert snap_to_sample(times, -5.0) == 0.0                    # clamps to the first sample
        assert snap_to_sample(times, 9.0) == 0.003                   # and the last

    def test_an_exact_tie_goes_to_the_earlier_sample(self):
        times = np.array([0.0, 0.002])
        assert snap_to_sample(times, 0.001) == 0.0

    def test_origin_must_be_finite_and_zero_is_a_valid_origin(self):
        assert require_finite_origin(0) == 0.0
        for bad in (float("nan"), float("inf"), True, "1"):
            with pytest.raises(ValueError):
                require_finite_origin(bad)

    def test_fine_shift_step_is_one_millisecond(self):
        assert FINE_SHIFT_STEP_S == 0.001


def _get(client, bay):
    group = _groups(client)[bay]
    response = client.get(URL, params={"measurement_group_id": group["id"]})
    assert response.status_code == 200, response.text
    return response.json()


def _put(client, bay, origin, snap=True):
    group = _groups(client)[bay]
    response = client.put(URL, json={"measurement_group_id": group["id"], "measurement_event_origin_s": origin, "snap_to_sample": snap})
    assert response.status_code == 200, response.text
    return response.json()


def _delete(client, bay):
    group = _groups(client)[bay]
    response = client.delete(URL, params={"measurement_group_id": group["id"]})
    assert response.status_code == 200, response.text
    return response.json()


def _traces(client, bay):
    group = _groups(client)[bay]
    return client.get(
        f"/api/v1/workspaces/{WS}/compliance/voltage/measurement-traces", params={"measurement_group_id": group["id"]},
    ).json()


def _t0(client):
    group = _groups(client)["KPDN1"]
    return client.get(f"/api/v1/workspaces/{WS}/synchronization/t0", params={"source_id": group["source_id"]}).json()


class TestAlignmentLifecycle:
    def test_starts_not_aligned(self, client):
        view = _get(client, "KPDN1")
        assert view["aligned"] is False
        assert view["measurement_event_origin_s"] is None and view["alignment_offset_s"] is None
        assert view["fine_shift_step_s"] == 0.001 and view["reference_position_s"] == 0.0

    def test_set_snaps_to_an_actual_sample_and_reports_the_offset(self, client):
        view = _put(client, "KPDN1", 0.5504)
        assert view["aligned"] is True
        assert view["measurement_event_origin_s"] == pytest.approx(0.550, abs=1e-9)
        assert view["alignment_offset_s"] == pytest.approx(-0.550, abs=1e-9)
        assert _get(client, "KPDN1") == view

    def test_an_explicit_origin_of_zero_is_aligned_not_the_same_as_not_aligned(self, client):
        view = _put(client, "KPDN1", 0.0)
        assert view["aligned"] is True and view["measurement_event_origin_s"] == 0.0
        assert _delete(client, "KPDN1")["aligned"] is False

    def test_fine_shift_keeps_the_exact_value_and_is_not_snapped(self, client):
        _put(client, "KPDN1", 0.550)
        view = _put(client, "KPDN1", 0.5505, snap=False)
        assert view["measurement_event_origin_s"] == 0.5505

    def test_clear_returns_to_not_aligned(self, client):
        _put(client, "KPDN1", 0.55)
        assert _delete(client, "KPDN1")["aligned"] is False
        assert _get(client, "KPDN1")["aligned"] is False

    def test_changing_the_measurement_group_does_not_reuse_the_old_alignment(self, client):
        _put(client, "KPDN1", 0.55)
        assert _get(client, "KPDN2")["aligned"] is False          # another recording context: never assumed
        _put(client, "KPDN2", 0.30)
        assert _get(client, "KPDN1")["aligned"] is False          # replaced: one alignment per workspace
        assert _get(client, "KPDN2")["measurement_event_origin_s"] == pytest.approx(0.30, abs=1e-9)

    def test_clearing_another_groups_alignment_leaves_this_one_alone(self, client):
        _put(client, "KPDN1", 0.55)
        _delete(client, "KPDN2")
        assert _get(client, "KPDN1")["aligned"] is True

    def test_changing_the_reference_layers_keeps_the_alignment(self, client):
        _put(client, "KPDN1", 0.55)
        layer = _add_reference(client, representation="phase_ground_rms", unit="kV")
        assert _get(client, "KPDN1")["aligned"] is True
        other = _add_reference(client, name="Other", unit="kV")
        client.delete(f"/api/v1/workspaces/{WS}/reference-layers/{layer['id']}")
        assert _get(client, "KPDN1")["measurement_event_origin_s"] == pytest.approx(0.55, abs=1e-9)
        assert other["id"]

    def test_start_new_workspace_clears_it(self, client):
        _put(client, "KPDN1", 0.55)
        assert client.app.state.compliance_alignment_registry.get(WS) is not None
        assert client.delete(f"/api/v1/workspaces/{WS}").status_code == 204
        assert client.app.state.compliance_alignment_registry.get(WS) is None

    def test_removing_the_source_leaves_no_stale_alignment(self, client):
        group = _groups(client)["KPDN1"]
        _put(client, "KPDN1", 0.55)
        assert client.delete(f"/api/v1/workspaces/{WS}/sources/{group['source_id']}").status_code == 204
        stored = client.app.state.compliance_alignment_registry
        response = client.get(URL, params={"measurement_group_id": group["id"]})
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            assert response.json()["aligned"] is False
        assert stored.get(WS) is None or response.status_code == 404

    def test_unknown_group_is_404(self, client):
        assert client.get(URL, params={"measurement_group_id": "mg-nope"}).status_code == 404


class TestAlignmentOnlyOffsetsTheMeasurement:
    def test_traces_carry_the_recording_time_unchanged_and_the_alignment_beside_them(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        _prepare(client, "KPDN1")
        before = _traces(client, "KPDN1")
        assert before["alignment"]["aligned"] is False
        _put(client, "KPDN1", 0.55)
        after = _traces(client, "KPDN1")
        assert after["alignment"]["aligned"] is True
        assert after["alignment"]["alignment_offset_s"] == pytest.approx(-0.55, abs=1e-9)
        for a, b in zip(before["traces"], after["traces"]):
            assert a["x"] == b["x"] and a["y"] == b["y"]   # values AND recording time untouched; the offset is applied when comparing

    def test_the_stored_origin_is_a_real_sample_time_of_the_recording(self, client):
        group = _groups(client)["KPDN1"]
        _put(client, "KPDN1", 0.5504)
        times = client.app.state.workspace_registry.get(WS, group["source_id"]).record.waveform_data["time"].to_numpy()
        origin = client.app.state.compliance_alignment_registry.get(WS).measurement_event_origin_s
        assert origin in set(float(t) for t in times)


class TestIndependenceFromWaveformT0:
    def test_setting_waveform_t0_does_not_create_or_change_compliance_alignment(self, client):
        group = _groups(client)["KPDN1"]
        response = client.put(f"/api/v1/workspaces/{WS}/synchronization/t0", json={"source_id": group["source_id"], "t0_workspace_time": 0.5})
        assert response.status_code == 200
        assert _get(client, "KPDN1")["aligned"] is False
        _put(client, "KPDN1", 0.9)
        client.put(f"/api/v1/workspaces/{WS}/synchronization/t0", json={"source_id": group["source_id"], "t0_workspace_time": 0.2})
        assert _get(client, "KPDN1")["measurement_event_origin_s"] == pytest.approx(0.9, abs=1e-9)
        client.delete(f"/api/v1/workspaces/{WS}/synchronization/t0", params={"source_id": group["source_id"]})
        assert _get(client, "KPDN1")["measurement_event_origin_s"] == pytest.approx(0.9, abs=1e-9)

    def test_setting_changing_and_clearing_compliance_alignment_never_touches_waveform_state(self, client):
        group = _groups(client)["KPDN1"]
        client.put(f"/api/v1/workspaces/{WS}/synchronization/t0", json={"source_id": group["source_id"], "t0_workspace_time": 0.5})
        sync_before = (_t0(client), client.get(f"/api/v1/workspaces/{WS}/synchronization/sources").json())
        _put(client, "KPDN1", 0.55)
        _put(client, "KPDN1", 0.5505, snap=False)
        assert (_t0(client), client.get(f"/api/v1/workspaces/{WS}/synchronization/sources").json()) == sync_before
        _delete(client, "KPDN1")
        assert (_t0(client), client.get(f"/api/v1/workspaces/{WS}/synchronization/sources").json()) == sync_before
        assert _t0(client)["t0_workspace_time"] == 0.5

    def test_measured_traces_do_not_move_with_waveform_t0(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        _prepare(client, "KPDN1")
        raw = _traces(client, "KPDN1")
        group = _groups(client)["KPDN1"]
        client.put(f"/api/v1/workspaces/{WS}/synchronization/t0", json={"source_id": group["source_id"], "t0_workspace_time": 0.5})
        shifted_by_waveform = _traces(client, "KPDN1")
        assert shifted_by_waveform["alignment"]["aligned"] is False
        for a, b in zip(raw["traces"], shifted_by_waveform["traces"]):
            assert a["x"] == b["x"]

    def test_compliance_code_does_not_import_waveform_synchronization(self):
        import inspect
        import app.services.compliance_alignment_service as alignment_service
        import app.services.compliance_trace_service as trace_service
        for module in (alignment_service, trace_service):
            source = inspect.getsource(module)
            assert "synchronization_service" not in source and "synchronization_registry" not in source, module.__name__
