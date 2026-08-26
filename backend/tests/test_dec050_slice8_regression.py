"""DEC-050 Slice 8 final hardening regression coverage. Targets three
genuine gaps identified during the Slice 8 audit that weren't already
covered by the Slice 1-7 test suites (see that audit for what already
existed and was left alone -- this file deliberately does not duplicate
coverage that test_group_aware_per_unit_endpoints.py,
test_calculated_group_aware_per_unit_endpoints.py, or
test_measurement_group_api.py already provide):

1. One realistic single-source, multi-group scenario exercising every
   kind of channel `synth_measurement_groups.cfg` provides at once
   (two Voltage groups, two Current groups, a manual-Ibase line, a
   method=none line, and a deliberately ungrouped channel) in a single
   test, proving zero cross-group/cross-channel leakage end-to-end --
   not just pairwise, as the existing suites test.
2. Multi-source isolation using the SAME nominal voltage across two
   sources (the existing `TestCrossSourceIsolation` in
   test_group_aware_per_unit_endpoints.py deliberately used DIFFERENT
   bases, which can't rule out "got lucky because the numbers differ" --
   this proves resolution is genuinely id-keyed, not value-keyed), plus
   that deleting one source's group never affects the other's.
3. A true three-request original-data-integrity check (engineering ->
   per_unit -> engineering, request 1 and 3 byte-identical) for all
   four combinations of {source, calculated} x {Voltage, Current} --
   the existing suites each check ONE engineering-mode request in
   isolation, not that a PRIOR per_unit request left no residue.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_MANUAL
from app.main import create_app
from app.services.current_group_config_service import set_current_base_equipment_rating, set_current_base_manual, set_current_base_none
from app.services.measurement_group_service import create_group
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_measurement_groups"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _make_group(client, workspace_id, source_id, kind, channel_names, display_name):
    return create_group(
        workspace_id=workspace_id, source_id=source_id, kind=kind, display_name=display_name,
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=STATUS_MANUAL,
        registry=client.app.state.measurement_group_registry,
        source_registry=client.app.state.workspace_registry,
    )


def _voltage_group(client, workspace_id, source_id, channel_names, nominal_kv, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_VOLTAGE, channel_names, display_name)
    set_voltage_base(
        workspace_id=workspace_id, measurement_group_id=group.id, nominal_voltage_ll_kv=nominal_kv,
        group_registry=client.app.state.measurement_group_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _current_group_equipment_rating(client, workspace_id, source_id, channel_names, mva, linked_voltage_group_id, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name)
    set_current_base_equipment_rating(
        workspace_id=workspace_id, measurement_group_id=group.id, equipment_rating_mva=mva,
        linked_voltage_group_id=linked_voltage_group_id,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _current_group_manual(client, workspace_id, source_id, channel_names, manual_ibase_ka, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name)
    set_current_base_manual(
        workspace_id=workspace_id, measurement_group_id=group.id, manual_ibase_ka=manual_ibase_ka,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
    )
    return group


def _current_group_none(client, workspace_id, source_id, channel_names, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name)
    set_current_base_none(
        workspace_id=workspace_id, measurement_group_id=group.id,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
    )
    return group


def _waveform(client, workspace_id, source_id, channel_name, unit_mode="engineering"):
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform",
        params={"channel_name": channel_name, "unit_mode": unit_mode},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRealisticMultiVoltageMultiCurrentSourceNoLeakage:
    """Section 7: one source, every DEC-050 configuration shape at once
    -- two independent Voltage groups (275/132 kV), an equipment-rating
    Current group linked to each, a manual-Ibase line, a method=none
    line, and a deliberately ungrouped channel. Every channel must
    resolve using ONLY its own configuration."""

    def test_full_source_resolves_with_zero_cross_group_leakage(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        v275 = _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        v132 = _voltage_group(client, "ws-1", source_id, ["S132_VR", "S132_VY", "S132_VB"], 132.0, "132 BUS")
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 1000.0, v275.id, "IBT HV"
        )
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_LV_IR", "IBT_LV_IY", "IBT_LV_IB"], 1000.0, v132.id, "IBT LV"
        )
        _current_group_manual(client, "ws-1", source_id, ["LINEA_IR"], 1.5, "LINE A")
        _current_group_none(client, "ws-1", source_id, ["LINEB_IR"], "LINE B")
        # SPARE_IR and FREQ deliberately left ungrouped/unconfigured.

        n275 = _waveform(client, "ws-1", source_id, "N275_VR", "per_unit")
        s132 = _waveform(client, "ws-1", source_id, "S132_VR", "per_unit")
        hv = _waveform(client, "ws-1", source_id, "IBT_HV_IR", "per_unit")
        lv = _waveform(client, "ws-1", source_id, "IBT_LV_IR", "per_unit")
        line_a = _waveform(client, "ws-1", source_id, "LINEA_IR", "per_unit")
        line_b = _waveform(client, "ws-1", source_id, "LINEB_IR", "per_unit")
        spare = _waveform(client, "ws-1", source_id, "SPARE_IR", "per_unit")
        freq = _waveform(client, "ws-1", source_id, "FREQ", "per_unit")

        # Each Voltage group resolves to its OWN ~1.0 pu -- healthy
        # phase-ground readings on their own nominal base.
        assert n275["per_unit_status"] == "configured"
        assert n275["values"][0] == pytest.approx(1.0, abs=0.01)
        assert s132["per_unit_status"] == "configured"
        assert s132["values"][0] == pytest.approx(1.0, abs=0.01)

        # 1000 MVA @ 275 kV LG -> Ibase ~2.0995 kA; @ 132 kV LG -> ~4.3739 kA.
        # HV/LV both carry the SAME raw 4199 A but resolve to DIFFERENT
        # pu values because each uses its OWN linked group's Ibase.
        assert hv["per_unit_status"] == "configured"
        assert hv["values"][0] == pytest.approx(4.199 / 2.0995, abs=0.001)
        assert lv["per_unit_status"] == "configured"
        assert lv["values"][0] == pytest.approx(4.199 / 4.3739, abs=0.001)
        assert hv["values"][0] != pytest.approx(lv["values"][0])

        # Manual Ibase line uses its own 1.5 kA, unrelated to any Voltage group.
        assert line_a["per_unit_status"] == "configured"
        assert line_a["values"][0] == pytest.approx(3.0 / 1.5, abs=0.001)

        # method=none is base_required -- never silently uses another
        # group's or a DEC-049 base.
        assert line_b["per_unit_status"] == "base_required"
        assert line_b["unit"] != "pu"

        # Ungrouped, no DEC-049 profile configured on this source either.
        assert spare["per_unit_status"] == "base_required"
        # Frequency is not_applicable regardless of grouping.
        assert freq["per_unit_status"] == "not_applicable"


class TestMultiSourceIsolationSameNominalVoltage:
    """Section 8: two sources with IDENTICAL channel names, IDENTICAL
    group display names, and the SAME nominal voltage -- resolution
    must still be fully independent (proving id-keying, not a
    coincidence of differing numbers), and deleting one source's group
    must never affect the other's."""

    def test_identical_configuration_on_two_sources_resolves_independently(
        self, client, comtrade_fixtures_dir
    ):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        group_a = _voltage_group(client, "ws-1", source_a, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        group_b = _voltage_group(client, "ws-1", source_b, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        assert group_a.id != group_b.id

        result_a = _waveform(client, "ws-1", source_a, "N275_VR", "per_unit")
        result_b = _waveform(client, "ws-1", source_b, "N275_VR", "per_unit")
        assert result_a["per_unit_status"] == "configured"
        assert result_b["per_unit_status"] == "configured"
        assert result_a["values"][0] == pytest.approx(result_b["values"][0], abs=1e-9)

        # Delete source A entirely; source B's group/config/resolution
        # must be completely unaffected.
        delete_resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_a}")
        assert delete_resp.status_code == 204, delete_resp.text

        result_b_after = _waveform(client, "ws-1", source_b, "N275_VR", "per_unit")
        assert result_b_after["per_unit_status"] == "configured"
        assert result_b_after["values"][0] == pytest.approx(result_b["values"][0], abs=1e-9)

        groups_b_after = client.get(f"/api/v1/workspaces/ws-1/sources/{source_b}/measurement-groups").json()
        assert any(g["id"] == group_b.id for g in groups_b_after)

        # Source A's own group is gone (source itself no longer exists).
        get_a_groups = client.get(f"/api/v1/workspaces/ws-1/sources/{source_a}/measurement-groups")
        assert get_a_groups.status_code == 404


class TestOriginalDataIntegrityAcrossRequestSequence:
    """Section 18: engineering -> per_unit -> engineering must return
    IDENTICAL values on requests 1 and 3, for every one of {source,
    calculated} x {Voltage, Current} -- proving per_unit conversion
    never mutates the retained authoritative array."""

    def _source_case(self, client, comtrade_fixtures_dir, channel_name, group_kind, group_setup):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group_setup(client, source_id)
        before = _waveform(client, "ws-1", source_id, channel_name, "engineering")
        _waveform(client, "ws-1", source_id, channel_name, "per_unit")
        after = _waveform(client, "ws-1", source_id, channel_name, "engineering")
        assert before["values"] == after["values"]
        assert before["unit"] == after["unit"]

    def test_source_voltage_no_mutation(self, client, comtrade_fixtures_dir):
        self._source_case(
            client, comtrade_fixtures_dir, "N275_VR", "voltage",
            lambda c, sid: _voltage_group(c, "ws-1", sid, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS"),
        )

    def test_source_current_no_mutation(self, client, comtrade_fixtures_dir):
        self._source_case(
            client, comtrade_fixtures_dir, "LINEA_IR", "current",
            lambda c, sid: _current_group_manual(c, "ws-1", sid, ["LINEA_IR"], 1.5, "LINE A"),
        )

    def test_calculated_voltage_no_mutation(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        create_resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels",
            json={
                "name": "NEG_VR", "operation": "reverse_polarity",
                "inputs": [{"kind": "source", "source_id": source_id, "channel_name": "N275_VR"}],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        calc_id = create_resp.json()["id"]

        def _calc_waveform(unit_mode):
            resp = client.get(
                f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}/waveform",
                params={"unit_mode": unit_mode},
            )
            assert resp.status_code == 200, resp.text
            return resp.json()

        before = _calc_waveform("engineering")
        _calc_waveform("per_unit")
        after = _calc_waveform("engineering")
        assert before["values"] == after["values"]
        assert before["unit"] == after["unit"]

    def test_calculated_current_no_mutation(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _current_group_manual(client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 4.199, "IBT HV")
        create_resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels",
            json={
                "name": "SUM_HV", "operation": "addition",
                "inputs": [
                    {"kind": "source", "source_id": source_id, "channel_name": "IBT_HV_IR"},
                    {"kind": "source", "source_id": source_id, "channel_name": "IBT_HV_IY"},
                ],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        calc_id = create_resp.json()["id"]

        def _calc_waveform(unit_mode):
            resp = client.get(
                f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}/waveform",
                params={"unit_mode": unit_mode},
            )
            assert resp.status_code == 200, resp.text
            return resp.json()

        before = _calc_waveform("engineering")
        _calc_waveform("per_unit")
        after = _calc_waveform("engineering")
        assert before["values"] == after["values"]
        assert before["unit"] == after["unit"]
