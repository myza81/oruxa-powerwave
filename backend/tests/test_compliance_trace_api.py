"""DEC-169 -- resolved measurement traces for the Comparison Chart, end to end
through the real FastAPI app. Same fixture and helpers as
`test_compliance_readiness_api.py` (`line_to_line_multibay`: KPDN1
instantaneous, KPDN2 two phases, MCRS already-RMS).

The central rule under test: **Ready means the trace can actually be
produced.** Every READY reference yields its traces; anything else yields
none -- never a guessed, unconverted or half-built trace.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.test_compliance_readiness_api import (  # noqa: F401  (fixture re-export)
    WS,
    _add_reference,
    _calc_channels,
    _groups,
    _prepare,
    _readiness,
    _set_base,
    client,
)

BASE_KV = 132.0


def _traces(client, bay: str) -> dict:
    group = _groups(client)[bay]
    response = client.get(
        f"/api/v1/workspaces/{WS}/compliance/voltage/measurement-traces", params={"measurement_group_id": group["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _arr(values) -> np.ndarray:
    """JSON null (the RMS warm-up samples) -> NaN."""
    return np.asarray([np.nan if v is None else v for v in values], dtype=float)


def _by_members(payload: dict) -> dict:
    return {tuple(t["members"]): t for t in payload["traces"]}


class TestEachPhase:
    def test_each_phase_gives_one_trace_per_required_voltage_in_the_reference_unit(self, client):
        _add_reference(client, unit="kV")
        _prepare(client, "KPDN1")
        payload = _traces(client, "KPDN1")
        assert payload["readiness_status"] == "ready"
        assert sorted(tuple(t["members"]) for t in payload["traces"]) == [("AB",), ("BC",), ("CA",)]
        assert {t["unit"] for t in payload["traces"]} == {"kV"}
        assert all(t["kind"] == "member" and len(t["x"]) == len(t["y"]) > 10 for t in payload["traces"])
        assert payload["phase_display"]["convention"] == "RYB"  # the frontend spells VRY/VYB/VBR from this

    def test_pu_reference_plots_per_unit_using_the_shared_group_base(self, client):
        _add_reference(client, name="pu", unit="pu")
        _add_reference(client, name="kV", unit="kV")
        _prepare(client, "KPDN1")
        _set_base(client, "KPDN1", BASE_KV)
        payload = _traces(client, "KPDN1")
        layers = {r["profile_name"]: r["layer_id"] for r in _readiness(client, "KPDN1")["references"]}
        pu = {tuple(t["members"]): t for t in payload["traces"] if t["unit"] == "pu"}
        kv = {tuple(t["members"]): t for t in payload["traces"] if t["unit"] == "kV"}
        assert set(pu) == set(kv) == {("AB",), ("BC",), ("CA",)}
        for member in pu:
            assert pu[member]["layer_ids"] == [layers["pu"]] and kv[member]["layer_ids"] == [layers["kV"]]
            # Same samples, converted by the shared per-unit path: pu = kV / base.
            np.testing.assert_allclose(pu[member]["x"], kv[member]["x"])
            np.testing.assert_allclose(_arr(pu[member]["y"]) * BASE_KV, _arr(kv[member]["y"]), rtol=1e-9)


class TestSingleMinimumMaximum:
    def test_single_plots_only_the_named_voltage(self, client):
        _add_reference(client, treatment="single", member="BC", unit="kV")
        _prepare(client, "KPDN1")
        payload = _traces(client, "KPDN1")
        assert [t["members"] for t in payload["traces"]] == [["BC"]]

    @pytest.mark.parametrize("treatment,kind,reducer", [("minimum", "minimum", np.minimum), ("maximum", "maximum", np.maximum)])
    def test_min_and_max_are_one_sample_by_sample_trace_across_the_members(self, client, treatment, kind, reducer):
        _add_reference(client, name="each", treatment="each_phase", unit="kV")
        _add_reference(client, name="agg", treatment=treatment, unit="kV")
        _prepare(client, "KPDN1")
        readiness = _readiness(client, "KPDN1")
        agg_layer = next(r["layer_id"] for r in readiness["references"] if r["profile_name"] == "agg")
        payload = _traces(client, "KPDN1")
        aggregate = [t for t in payload["traces"] if t["kind"] == kind]
        assert len(aggregate) == 1 and aggregate[0]["members"] == ["AB", "BC", "CA"]
        assert aggregate[0]["layer_ids"] == [agg_layer]
        members = [t for t in payload["traces"] if t["kind"] == "member"]
        expected = reducer.reduce([_arr(t["y"]) for t in members])
        np.testing.assert_allclose(_arr(aggregate[0]["y"]), expected)


class TestSourceRmsAndReuse:
    def test_an_already_rms_source_is_plotted_directly_without_a_calculated_channel(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        payload = _traces(client, "MCRS")
        assert sorted(tuple(t["members"]) for t in payload["traces"]) == [("A",), ("B",), ("C",)]
        assert _calc_channels(client) == []

    def test_existing_calculated_rms_channels_are_reused_not_duplicated(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        _prepare(client, "KPDN1")
        count = len(_calc_channels(client))
        assert len(_traces(client, "KPDN1")["traces"]) == 3
        assert len(_calc_channels(client)) == count  # reading traces creates nothing


class TestMultipleReferences:
    def test_two_references_needing_the_identical_product_share_one_set_of_traces(self, client):
        _add_reference(client, name="A", unit="kV")
        _add_reference(client, name="B", unit="kV")
        _prepare(client, "KPDN1")
        payload = _traces(client, "KPDN1")
        assert len(payload["traces"]) == 3
        assert all(len(t["layer_ids"]) == 2 for t in payload["traces"])

    def test_genuinely_different_products_are_both_plotted(self, client):
        _add_reference(client, name="each", unit="kV")
        _add_reference(client, name="single", treatment="single", member="AB", unit="kV")
        _prepare(client, "KPDN1")
        payload = _traces(client, "KPDN1")
        # AB is one shared member trace (same channel, same unit): the Single reference reuses it.
        assert len(payload["traces"]) == 3
        ab = next(t for t in payload["traces"] if t["members"] == ["AB"])
        assert len(ab["layer_ids"]) == 2


class TestNothingIsGuessed:
    def test_no_reference_means_no_traces(self, client):
        payload = _traces(client, "KPDN1")
        assert payload["traces"] == [] and payload["readiness_status"] == "no_reference"

    def test_pu_without_a_base_plots_nothing(self, client):
        _add_reference(client, unit="pu")
        _prepare(client, "KPDN1")
        assert _readiness(client, "KPDN1")["status"] == "action_required"
        assert _traces(client, "KPDN1")["traces"] == []

    def test_a_base_that_is_not_applied_yet_plots_nothing(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="pu")
        _prepare(client, "KPDN1")
        group = _groups(client)["KPDN1"]
        client.put(
            f"/api/v1/workspaces/{WS}/sources/{group['source_id']}/measurement-groups/{group['id']}/voltage-config",
            json={"nominal_voltage_ll_kv": 132.0, "reference_mode": "auto"},
        )  # saved, group still only suggested
        assert _traces(client, "KPDN1")["traces"] == []

    def test_unsafe_line_line_plots_nothing(self, client):
        _add_reference(client, unit="kV")
        payload = _traces(client, "MCRS")
        assert payload["readiness_status"] == "incompatible" and payload["traces"] == []

    def test_nothing_prepared_yet_plots_nothing(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        assert _traces(client, "KPDN1")["traces"] == []  # RMS still needs preparing


class TestTimeAxisIsTheMeasurementsOwn:
    """DEC-170: traces carry the measurement's own recording time. The
    Compliance Event Alignment (assessment-local, NOT Waveform t0) is returned
    beside them -- see test_compliance_alignment_api.py for its lifecycle and
    its independence from Waveform t0."""

    def test_x_is_the_recording_time_and_the_alignment_is_reported_separately(self, client):
        _add_reference(client, representation="phase_ground_rms", unit="kV")
        _prepare(client, "KPDN1")
        payload = _traces(client, "KPDN1")
        assert payload["alignment"]["aligned"] is False and payload["alignment"]["measurement_event_origin_s"] is None
        source = client.app.state.workspace_registry.get(WS, _groups(client)["KPDN1"]["source_id"])
        times = source.record.waveform_data["time"].to_numpy()
        assert payload["traces"][0]["x"][0] == float(times[0])
        assert payload["traces"][0]["x"][-1] == float(times[-1])
