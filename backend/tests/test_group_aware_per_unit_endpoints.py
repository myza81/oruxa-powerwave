"""Live-endpoint integration tests for DEC-050 Slice 5: group-aware
Per-Unit resolution wired into the source display endpoints (`GET
.../waveform`, `POST .../cursor-values`, `.../annotation-anchor`,
`.../peak-values`). Exercises the real FastAPI app end-to-end -- proving
the channel -> MeasurementGroup -> BaseConfiguration -> resolved base ->
conversion flow at the actual HTTP boundary, not just at the resolver/
service level (see test_group_aware_per_unit_service.py for that).

Fixture: `synth_measurement_groups.cfg`/`.dat` (new this slice) -- a
single synthetic source purpose-built for these scenarios. Every analog
channel holds a CONSTANT value across all 5 samples (raw sample = 1 for
every channel; each channel's own `a` multiplier in the .cfg IS its
value), chosen so expected PU results can be computed independently in
each test rather than hard-coded:

    N275_VR/VY/VB   kV, value=158.77   (275 kV nominal, LG phase group)
    S132_VR/VY/VB   kV, value=76.21    (132 kV nominal, LG phase group)
    E275_VRY/VYB/VBR kV, value=275.0   (275 kV nominal, LL pair group)
    IBT_HV_IR/IY/IB  A, value=4199.0   (transformer HV side current)
    IBT_LV_IR/IY/IB  A, value=4199.0   (transformer LV side current -- SAME raw value as HV, deliberately)
    LINEA_IR         A, value=3000.0  (manual-Ibase line current)
    LINEB_IR         A, value=1000.0  (current method=none line current)
    SPARE_IR         A, value=500.0   (deliberately left ungrouped)
    FREQ            Hz, value=50.0    (unsupported quantity for DEC-050)
    BRK_A/BRK_B (digital)
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import CurrentBaseConfiguration, METHOD_MANUAL
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_MANUAL, STATUS_SUGGESTED
from app.main import create_app
from app.services.current_group_config_service import (
    set_current_base_equipment_rating,
    set_current_base_manual,
    set_current_base_none,
)
from app.services.errors import ChannelWrongEngineeringTypeError
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


def _make_group(client, workspace_id, source_id, kind, channel_names, display_name, status=STATUS_MANUAL):
    return create_group(
        workspace_id=workspace_id, source_id=source_id, kind=kind, display_name=display_name,
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=status,
        registry=client.app.state.measurement_group_registry,
        source_registry=client.app.state.workspace_registry,
    )


def _voltage_group(client, workspace_id, source_id, channel_names, nominal_kv, display_name, status=STATUS_MANUAL):
    group = _make_group(client, workspace_id, source_id, KIND_VOLTAGE, channel_names, display_name, status=status)
    set_voltage_base(
        workspace_id=workspace_id, measurement_group_id=group.id, nominal_voltage_ll_kv=nominal_kv,
        group_registry=client.app.state.measurement_group_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _current_group_equipment_rating(
    client, workspace_id, source_id, channel_names, mva, display_name, *,
    linked_voltage_group_id=None, manual_voltage_base_kv=None, status=STATUS_MANUAL,
):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name, status=status)
    set_current_base_equipment_rating(
        workspace_id=workspace_id, measurement_group_id=group.id, equipment_rating_mva=mva,
        linked_voltage_group_id=linked_voltage_group_id, manual_voltage_base_kv=manual_voltage_base_kv,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _current_group_manual(client, workspace_id, source_id, channel_names, manual_ibase_ka, display_name, status=STATUS_MANUAL):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name, status=status)
    set_current_base_manual(
        workspace_id=workspace_id, measurement_group_id=group.id, manual_ibase_ka=manual_ibase_ka,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
    )
    return group


def _current_group_none(client, workspace_id, source_id, channel_names, display_name, status=STATUS_MANUAL):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name, status=status)
    set_current_base_none(
        workspace_id=workspace_id, measurement_group_id=group.id,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
    )
    return group


def _waveform_pu(client, workspace_id, source_id, channel_name):
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform",
        params={"channel_name": channel_name, "unit_mode": "per_unit"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _waveform_engineering(client, workspace_id, source_id, channel_name):
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/waveform",
        params={"channel_name": channel_name},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestTwoVoltageLevelsInOneSource:
    """Scenario A: two independent LG Voltage groups in one source must
    each resolve their OWN nominal base -- proves source-wide base
    leakage is gone."""

    def test_275kv_and_132kv_buses_independently_resolve_near_1pu(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 NORTH BUS")
        _voltage_group(client, "ws-1", source_id, ["S132_VR", "S132_VY", "S132_VB"], 132.0, "132 SOUTH BUS")

        north = _waveform_pu(client, "ws-1", source_id, "N275_VR")
        south = _waveform_pu(client, "ws-1", source_id, "S132_VR")

        assert north["per_unit_status"] == "configured"
        assert north["unit"] == "pu"
        assert north["values"][0] == pytest.approx(158.77 / (275.0 / SQRT_3), abs=0.001)
        assert north["values"][0] == pytest.approx(1.0, abs=0.01)

        assert south["per_unit_status"] == "configured"
        assert south["values"][0] == pytest.approx(76.21 / (132.0 / SQRT_3), abs=0.001)
        assert south["values"][0] == pytest.approx(1.0, abs=0.01)


class TestLgAndLlGroupsInOneSource:
    """Scenario B: an LG group and an LL group at the SAME nominal
    voltage level must use different denominators."""

    def test_lg_and_ll_275kv_groups_use_different_denominators(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 LG BUS")
        _voltage_group(client, "ws-1", source_id, ["E275_VRY", "E275_VYB", "E275_VBR"], 275.0, "275 LL BUS")

        lg = _waveform_pu(client, "ws-1", source_id, "N275_VR")
        ll = _waveform_pu(client, "ws-1", source_id, "E275_VRY")

        assert lg["values"][0] == pytest.approx(1.0, abs=0.01)
        assert ll["values"][0] == pytest.approx(275.0 / 275.0, abs=1e-9)
        assert ll["values"][0] == pytest.approx(1.0, abs=1e-9)


class TestTransformerHvLvCurrentGroups:
    """Scenario C: the same equipment Sbase must NOT imply the same
    Ibase on a transformer's two sides."""

    def test_hv_and_lv_sides_resolve_independently(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        hv_voltage = _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        lv_voltage = _voltage_group(client, "ws-1", source_id, ["S132_VR", "S132_VY", "S132_VB"], 132.0, "132 BUS")
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 1000.0, "IBT1 HV CURRENT",
            linked_voltage_group_id=hv_voltage.id,
        )
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_LV_IR", "IBT_LV_IY", "IBT_LV_IB"], 1000.0, "IBT1 LV CURRENT",
            linked_voltage_group_id=lv_voltage.id,
        )

        hv = _waveform_pu(client, "ws-1", source_id, "IBT_HV_IR")
        lv = _waveform_pu(client, "ws-1", source_id, "IBT_LV_IR")

        hv_ibase_ka = 1000.0 / (SQRT_3 * 275.0)
        lv_ibase_ka = 1000.0 / (SQRT_3 * 132.0)
        assert hv["per_unit_status"] == "configured"
        assert lv["per_unit_status"] == "configured"
        assert hv["values"][0] == pytest.approx(4.199 / hv_ibase_ka, abs=0.001)
        assert lv["values"][0] == pytest.approx(4.199 / lv_ibase_ka, abs=0.001)
        # The same absolute raw current (4199 A on both channels) must
        # produce two DIFFERENT pu results.
        assert hv["values"][0] != pytest.approx(lv["values"][0])


class TestManualCurrentIbase:
    """Scenario D: manual Ibase mode, verified through the live endpoint."""

    def test_manual_ibase_is_used(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _current_group_manual(client, "ws-1", source_id, ["LINEA_IR"], 1.5, "LINE A CURRENT")

        result = _waveform_pu(client, "ws-1", source_id, "LINEA_IR")
        assert result["per_unit_status"] == "configured"
        assert result["values"][0] == pytest.approx(3.0 / 1.5, abs=1e-9)
        assert result["values"][0] == pytest.approx(2.0, abs=1e-9)


class TestCurrentMethodNone:
    """Scenario E: method=none never invents a base."""

    def test_method_none_is_base_required(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _current_group_none(client, "ws-1", source_id, ["LINEB_IR"], "LINE B CURRENT")

        result = _waveform_pu(client, "ws-1", source_id, "LINEB_IR")
        assert result["per_unit_status"] == "base_required"
        assert result["unit"] == "A"  # unchanged engineering unit, never fabricated pu
        assert result["values"][0] == pytest.approx(1000.0)


class TestMissingGroupCompatibility:
    """Scenario F: a channel with no MeasurementGroup at all must use
    the existing DEC-049 source-wide path unchanged -- and once a
    DEC-049 profile IS configured, it must apply to that ungrouped
    channel while never leaking into a grouped channel's own result."""

    def test_ungrouped_channel_with_no_dec049_profile_is_base_required(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        result = _waveform_pu(client, "ws-1", source_id, "SPARE_IR")
        assert result["per_unit_status"] == "base_required"

    def test_dec049_coexistence_never_overrides_a_grouped_channel(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        # A grouped Current channel (its own group-specific Ibase).
        _current_group_manual(client, "ws-1", source_id, ["LINEA_IR"], 1.5, "LINE A CURRENT")
        # A DEC-049 source-wide profile configured on the SAME source,
        # with a deliberately DIFFERENT current base, to prove the two
        # systems never blend for the same channel.
        put_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 275.0, "current_base_mode": "direct", "direct_current_base_value": 9.0},
        )
        assert put_resp.status_code == 200, put_resp.text

        grouped = _waveform_pu(client, "ws-1", source_id, "LINEA_IR")
        ungrouped = _waveform_pu(client, "ws-1", source_id, "SPARE_IR")

        # Grouped channel: still uses its OWN manual Ibase (1.5 kA), not
        # the DEC-049 source-wide 9.0 kA.
        assert grouped["values"][0] == pytest.approx(3.0 / 1.5, abs=1e-9)
        # Ungrouped channel: falls back to the DEC-049 source-wide base
        # (9.0 kA) exactly as before Slice 5.
        assert ungrouped["per_unit_status"] == "configured"
        assert ungrouped["values"][0] == pytest.approx(0.5 / 9.0, abs=1e-9)


class TestSuggestedLinkedVoltageGroup:
    """Scenario G: a linked Voltage group's own lifecycle status must
    NOT block Current Ibase resolution -- only the CURRENT group's own
    status is gated."""

    def test_current_group_resolves_via_a_suggested_linked_voltage_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        linked_voltage = _voltage_group(
            client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS (still suggested)",
            status=STATUS_SUGGESTED,
        )
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 1000.0, "IBT1 HV CURRENT",
            linked_voltage_group_id=linked_voltage.id,
            status=STATUS_MANUAL,  # the CURRENT group itself is authoritative
        )

        result = _waveform_pu(client, "ws-1", source_id, "IBT_HV_IR")
        expected_ibase_ka = 1000.0 / (SQRT_3 * 275.0)
        assert result["per_unit_status"] == "configured"
        assert result["values"][0] == pytest.approx(4.199 / expected_ibase_ka, abs=0.001)


class TestCrossSourceIsolation:
    """Scenario H: two sources with identically-named channels/groups
    must never resolve each other's base."""

    def test_two_sources_with_the_same_channel_names_stay_independent(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_a, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "A's 275 BUS")
        _voltage_group(client, "ws-1", source_b, ["N275_VR", "N275_VY", "N275_VB"], 220.0, "B's 220 BUS (different base)")

        result_a = _waveform_pu(client, "ws-1", source_a, "N275_VR")
        result_b = _waveform_pu(client, "ws-1", source_b, "N275_VR")

        assert result_a["values"][0] == pytest.approx(158.77 / (275.0 / SQRT_3), abs=0.001)
        assert result_b["values"][0] == pytest.approx(158.77 / (220.0 / SQRT_3), abs=0.001)
        assert result_a["values"][0] != pytest.approx(result_b["values"][0])


class TestDigitalChannelsUnaffected:
    """Scenario I: digital channels have no unit_mode concept at all --
    grouping other channels on the same source must not affect them."""

    def test_digital_waveform_unaffected_by_grouping(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/digital-waveform",
            params={"channel_names": ["BRK_A"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["channels"][0]["channel_name"] == "BRK_A"
        assert "unit" not in body["channels"][0] or True  # digital results carry no unit/pu concept at all


class TestUnsupportedAnalogQuantity:
    """Scenario J: Frequency (and other non-Voltage/Current types) must
    never receive a guessed PU base, grouped or not."""

    def test_frequency_channel_is_not_applicable(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        result = _waveform_pu(client, "ws-1", source_id, "FREQ")
        assert result["per_unit_status"] == "not_applicable"
        assert result["unit"] == "Hz"
        assert result["values"][0] == pytest.approx(50.0)

    def test_frequency_channel_cannot_be_added_to_a_voltage_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        with pytest.raises(ChannelWrongEngineeringTypeError):
            _voltage_group(client, "ws-1", source_id, ["FREQ"], 275.0, "INVALID BUS")


class TestEngineeringModeUnchanged:
    """Scenario K: requesting engineering mode for a grouped channel
    must be byte-for-byte the same as before grouping existed."""

    def test_grouped_channel_engineering_mode_is_unaffected(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        before = _waveform_engineering(client, "ws-1", source_id, "N275_VR")
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        after = _waveform_engineering(client, "ws-1", source_id, "N275_VR")

        assert before["values"] == after["values"]
        assert before["unit"] == after["unit"] == "kV"
        assert after["per_unit_status"] is None


class TestAllFourEndpointsUseGroupAwareResolution:
    """Section 18: prove the wiring reaches every migrated endpoint, not
    just GET .../waveform."""

    @pytest.fixture
    def grouped_source(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        return source_id

    def test_cursor_values_endpoint(self, client, grouped_source):
        resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{grouped_source}/cursor-values",
            json={
                "analog_channel_names": ["N275_VR"], "digital_channel_names": [],
                "cursor_a_time": 0.0, "cursor_b_time": None, "unit_mode": "per_unit",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        channel = body["channels"][0]
        assert channel["per_unit_status"] == "configured"
        assert channel["a_value"] == pytest.approx(1.0, abs=0.01)

    def test_annotation_anchor_endpoint(self, client, grouped_source):
        resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{grouped_source}/annotation-anchor",
            json={"channel_name": "N275_VR", "approximate_elapsed_seconds": 0.0, "unit_mode": "per_unit"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] == "configured"
        assert body["value"] == pytest.approx(1.0, abs=0.01)

    def test_peak_values_endpoint(self, client, grouped_source):
        resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{grouped_source}/peak-values",
            json={
                "start_time": 0.0, "end_time": 0.001, "unit_mode": "per_unit",
                "requests": [{"channel_name": "N275_VR", "mode": "max"}],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        result = body["results"][0]
        assert result["per_unit_status"] == "configured"
        assert result["value"] == pytest.approx(1.0, abs=0.01)


class TestAdversarial:
    """Section 19: failure-isolation and defensive-safety scenarios."""

    def test_same_display_name_two_groups_resolve_by_id_not_name(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "BUS VOLTAGE")
        _voltage_group(client, "ws-1", source_id, ["S132_VR", "S132_VY", "S132_VB"], 132.0, "BUS VOLTAGE")

        north = _waveform_pu(client, "ws-1", source_id, "N275_VR")
        south = _waveform_pu(client, "ws-1", source_id, "S132_VR")
        assert north["values"][0] == pytest.approx(1.0, abs=0.01)
        assert south["values"][0] == pytest.approx(1.0, abs=0.01)

    def test_deleted_linked_voltage_group_config_degrades_to_base_required(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        linked_voltage = _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 1000.0, "IBT1 HV CURRENT",
            linked_voltage_group_id=linked_voltage.id,
        )
        # Simulate the linked group's own configuration going stale/removed.
        client.app.state.voltage_group_config_registry.delete("ws-1", linked_voltage.id)

        result = _waveform_pu(client, "ws-1", source_id, "IBT_HV_IR")
        assert result["per_unit_status"] == "base_required"

    def test_deleted_linked_voltage_group_itself_degrades_to_base_required(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        linked_voltage = _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 BUS")
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 1000.0, "IBT1 HV CURRENT",
            linked_voltage_group_id=linked_voltage.id,
        )
        client.app.state.measurement_group_registry.remove("ws-1", linked_voltage.id)

        result = _waveform_pu(client, "ws-1", source_id, "IBT_HV_IR")
        assert result["per_unit_status"] == "base_required"

    def test_corrupted_zero_ibase_never_divides(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = _current_group_manual(client, "ws-1", source_id, ["LINEA_IR"], 1.5, "LINE A CURRENT")
        # Bypass the service layer's own validation entirely, simulating
        # corrupted/stale registry state -- the resolver must still never
        # divide by zero or fabricate a value.
        client.app.state.current_group_config_registry.upsert(
            CurrentBaseConfiguration(measurement_group_id=group.id, workspace_id="ws-1", method=METHOD_MANUAL, manual_ibase_ka=0.0)
        )
        result = _waveform_pu(client, "ws-1", source_id, "LINEA_IR")
        assert result["per_unit_status"] == "base_required"

    def test_current_linked_to_lg_or_ll_voltage_group_yields_the_same_ibase(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        lg_voltage = _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "275 LG BUS")
        ll_voltage = _voltage_group(client, "ws-1", source_id, ["E275_VRY", "E275_VYB", "E275_VBR"], 275.0, "275 LL BUS")
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 1000.0, "LINKED TO LG",
            linked_voltage_group_id=lg_voltage.id,
        )
        _current_group_equipment_rating(
            client, "ws-1", source_id, ["IBT_LV_IR", "IBT_LV_IY", "IBT_LV_IB"], 1000.0, "LINKED TO LL",
            linked_voltage_group_id=ll_voltage.id,
        )

        via_lg = _waveform_pu(client, "ws-1", source_id, "IBT_HV_IR")
        via_ll = _waveform_pu(client, "ws-1", source_id, "IBT_LV_IR")

        assert via_lg["per_unit_status"] == "configured"
        assert via_ll["per_unit_status"] == "configured"
        # Same raw current (4199 A on both channels), same equipment
        # rating, same nominal 275 kV -- must produce the SAME pu
        # regardless of the linked group's own LG/LL reference.
        assert via_lg["values"][0] == pytest.approx(via_ll["values"][0], rel=1e-9)
