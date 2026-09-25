"""DEC-116: per-unit base selection follows ONE representation rule on
both the Measurement Group (DEC-050) and Source Default (DEC-049) paths.

- Generic multi-input Voltage arithmetic (Addition/Subtraction) has no
  authoritative L-G/L-L output representation -> `base_required`, with
  reason `voltage_representation_undetermined`, on BOTH paths. Unary
  descendants of it (RMS(VR - VY), -(VR - VY)) inherit that uncertainty.
- Semantic Line-to-Line outputs (DEC-115) declare `line_to_line` -> the
  L-L base (275 kV), as do their unary descendants (RMS(VAB)).
- Phase-to-ground source channels and unary operations on them keep the
  L-G base (275/sqrt(3) kV).
- Engineering-unit values are never changed by any of this.

Nominal system: 275 kV L-L. Fixture: line_to_line_multibay (KPDN1
VR/VY/VB phase-to-ground, kV).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import CalculatedChannel, ChannelRef, evaluate_rms
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL
from app.domain.per_unit import STATUS_BASE_REQUIRED
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_group_aware_per_unit import (
    REASON_VOLTAGE_REPRESENTATION_UNDETERMINED,
    undetermined_representation_resolution,
    voltage_representation_undetermined,
)
from app.services.measurement_group_service import create_group
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772
LL_BASE_KV = 275.0
LG_BASE_KV = 275.0 / SQRT_3  # 158.77 kV
WS = "ws-116"
UNDETERMINED_TEXT = "Automatic per-unit base cannot be inferred for a generic multi-input voltage calculation."


# ---------------------------------------------------------------- pure rule


def _calc(cid, operation, inputs, *, engineering_type="Voltage", voltage_representation=None, phase_member=None):
    return CalculatedChannel(
        id=cid, workspace_id=WS, name=cid, unit="kV", operation=operation, inputs=inputs, parameters={},
        dependency_ids=[r.calculated_channel_id for r in inputs if r.kind == "calculated"],
        reference_source_id="src", time=np.zeros(1), values=np.zeros(1), created_at=datetime.now(timezone.utc),
        engineering_type=engineering_type, voltage_representation=voltage_representation, phase_member=phase_member,
    )


SRC_A = ChannelRef(kind="source", source_id="src", channel_name="VR")
SRC_B = ChannelRef(kind="source", source_id="src", channel_name="VY")


class TestRepresentationRule:
    @pytest.fixture
    def registry(self):
        reg = CalculatedChannelRegistry()
        reg.add(_calc("calc-sub", "subtraction", [SRC_A, SRC_B]))
        reg.add(_calc("calc-vab", "line_to_line_voltage", [SRC_A, SRC_B], voltage_representation="line_to_line", phase_member="AB"))
        return reg

    @pytest.mark.parametrize("operation", ["addition", "subtraction"])
    def test_generic_multi_input_voltage_is_undetermined(self, registry, operation):
        assert voltage_representation_undetermined(WS, _calc("x", operation, [SRC_A, SRC_B]), calc_registry=registry)

    @pytest.mark.parametrize("operation", ["rms", "reverse_polarity", "absolute_value", "multiply_constant"])
    def test_unary_descendant_of_generic_is_undetermined(self, registry, operation):
        ref = ChannelRef(kind="calculated", calculated_channel_id="calc-sub")
        assert voltage_representation_undetermined(WS, _calc("x", operation, [ref]), calc_registry=registry)

    @pytest.mark.parametrize("operation", ["rms", "reverse_polarity", "absolute_value", "multiply_constant"])
    def test_unary_on_source_channel_is_not_undetermined(self, registry, operation):
        assert not voltage_representation_undetermined(WS, _calc("x", operation, [SRC_A]), calc_registry=registry)

    def test_declared_representation_is_authoritative(self, registry):
        vab = registry.get(WS, "calc-vab")
        assert not voltage_representation_undetermined(WS, vab, calc_registry=registry)
        rms = _calc("x", "rms", [ChannelRef(kind="calculated", calculated_channel_id="calc-vab")],
                    voltage_representation="line_to_line", phase_member="AB")
        assert not voltage_representation_undetermined(WS, rms, calc_registry=registry)

    def test_current_multi_input_is_unaffected(self, registry):
        assert not voltage_representation_undetermined(
            WS, _calc("x", "addition", [SRC_A, SRC_B], engineering_type="Current"), calc_registry=registry
        )

    def test_resolution_reuses_base_required_vocabulary(self):
        resolution = undetermined_representation_resolution()
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == REASON_VOLTAGE_REPRESENTATION_UNDETERMINED
        assert resolution.base_amount is None


# ---------------------------------------------------------------- end to end


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, comtrade_fixtures_dir):
    stem = "line_to_line_multibay"
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO((comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO((comtrade_fixtures_dir / f"{stem}.dat").read_bytes()), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{WS}/sources", files=files)
    assert resp.status_code == 201, resp.text
    source_id = resp.json()["source_id"]
    groups_url = f"/api/v1/workspaces/{WS}/sources/{source_id}/measurement-groups"
    for group in client.get(groups_url).json():
        client.delete(f"{groups_url}/{group['id']}")
    return source_id


def _configure(client, source_id, path):
    if path == "measurement_group":
        group = create_group(
            workspace_id=WS, source_id=source_id, kind=KIND_VOLTAGE, display_name="KPDN1 275 kV",
            channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in ("KPDN1_VR", "KPDN1_VY", "KPDN1_VB")],
            status=STATUS_MANUAL,
            registry=client.app.state.measurement_group_registry, source_registry=client.app.state.workspace_registry,
        )
        set_voltage_base(
            workspace_id=WS, measurement_group_id=group.id, nominal_voltage_ll_kv=LL_BASE_KV,
            group_registry=client.app.state.measurement_group_registry,
            voltage_config_registry=client.app.state.voltage_group_config_registry,
        )
    else:
        resp = client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": LL_BASE_KV})
        assert resp.status_code == 200, resp.text


def _src(source_id, name):
    return {"kind": "source", "source_id": source_id, "channel_name": name}


def _calc_ref(channel):
    return {"kind": "calculated", "calculated_channel_id": channel["id"]}


def _create(client, name, operation, inputs, **extra):
    resp = client.post(f"/api/v1/workspaces/{WS}/calculated-channels",
                       json={"name": name, "operation": operation, "inputs": inputs, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_ll(client, output, **extra):
    context_id = next(c["id"] for c in client.get(f"/api/v1/workspaces/{WS}/engineering-contexts").json()
                      if c["display_name"] == "KPDN1")
    resp = client.post(f"/api/v1/workspaces/{WS}/calculated-channels/line-to-line-voltage",
                       json={"engineering_context_id": context_id, "output": output, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["channels"]


def _calc_pu(client, calc_id):
    resp = client.get(f"/api/v1/workspaces/{WS}/calculated-channels/{calc_id}/per-unit-resolution")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _source_pu(client, source_id, name):
    resp = client.get(f"/api/v1/workspaces/{WS}/sources/{source_id}/per-unit-resolution", params={"channel_name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _waveform(client, calc_id, unit_mode):
    resp = client.get(f"/api/v1/workspaces/{WS}/calculated-channels/{calc_id}/waveform",
                      params={"unit_mode": unit_mode, "point_budget": 5000})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _source_values(client, source_id, name):
    return client.app.state.workspace_registry.get(WS, source_id).record.waveform_data[name].to_numpy()


def _stored_values(client, calc_id):
    return client.app.state.calculated_channel_registry.get(WS, calc_id).values


@pytest.fixture(params=["measurement_group", "source_default"])
def setup(request, client, comtrade_fixtures_dir):
    source_id = _upload(client, comtrade_fixtures_dir)
    _configure(client, source_id, request.param)
    return {"source_id": source_id, "path": request.param}


class TestRegressionMatrix:
    """The owner's 275 kV / 158.77 kV matrix, identical on both paths."""

    @pytest.mark.parametrize("operation", ["subtraction", "addition"])
    def test_generic_multi_input_voltage_is_base_required(self, client, setup, operation):
        sid = setup["source_id"]
        generic = _create(client, f"VR {operation} VY", operation, [_src(sid, "KPDN1_VR"), _src(sid, "KPDN1_VY")])
        pu = _calc_pu(client, generic["id"])
        assert pu["status"] == "base_required"
        assert pu["effective_base_amount"] is None
        assert pu["reason"] == UNDETERMINED_TEXT
        assert _waveform(client, generic["id"], "per_unit")["per_unit_status"] == "base_required"

    def test_semantic_ll_outputs_use_ll_base(self, client, setup):
        for channel in _create_ll(client, "all_three"):
            pu = _calc_pu(client, channel["id"])
            assert pu["status"] == "configured", channel["name"]
            assert pu["effective_base_amount"] == pytest.approx(LL_BASE_KV)
            assert pu["nominal_reference"] == "line_to_line"

    def test_rms_of_vab_keeps_ll_base(self, client, setup):
        vab = _create_ll(client, "AB")[0]
        rms = _create(client, "RMS(KPDN1 VAB)", "rms", [_calc_ref(vab)], parameters={"nominal_frequency_hz": 50})
        pu = _calc_pu(client, rms["id"])
        assert pu["status"] == "configured"
        assert pu["effective_base_amount"] == pytest.approx(LL_BASE_KV)

    def test_phase_ground_source_uses_lg_base(self, client, setup):
        pu = _source_pu(client, setup["source_id"], "KPDN1_VR")
        assert pu["status"] == "configured"
        assert pu["effective_base_amount"] == pytest.approx(LG_BASE_KV)

    def test_renamed_ll_output_is_still_ll(self, client, setup):
        """Representation comes from metadata, never the name."""
        renamed = _create_ll(client, "AB", names={"AB": "Feeder quantity 1"})[0]
        assert renamed["voltage_representation"] == "line_to_line"
        assert _calc_pu(client, renamed["id"])["effective_base_amount"] == pytest.approx(LL_BASE_KV)


class TestDescendantsAndSingleInputPropagation:
    @pytest.mark.parametrize("operation,extra", [
        ("rms", {"parameters": {"nominal_frequency_hz": 50}, "override": True}),
        ("reverse_polarity", {}),
        ("absolute_value", {}),
        ("multiply_constant", {"parameters": {"constant": 2.0}}),
    ])
    def test_unary_of_generic_subtraction_is_base_required(self, client, setup, operation, extra):
        sid = setup["source_id"]
        generic = _create(client, "VR - VY", "subtraction", [_src(sid, "KPDN1_VR"), _src(sid, "KPDN1_VY")])
        child = _create(client, f"{operation}(VR - VY)", operation, [_calc_ref(generic)], **extra)
        pu = _calc_pu(client, child["id"])
        assert pu["status"] == "base_required"
        assert pu["reason"] == UNDETERMINED_TEXT

    @pytest.mark.parametrize("operation,extra", [
        ("rms", {"parameters": {"nominal_frequency_hz": 50}}),
        ("reverse_polarity", {}),
        ("absolute_value", {}),
        ("multiply_constant", {"parameters": {"constant": 2.0}}),
    ])
    def test_unary_on_phase_ground_source_keeps_lg_base(self, client, setup, operation, extra):
        child = _create(client, f"{operation}(VR)", operation, [_src(setup["source_id"], "KPDN1_VR")], **extra)
        pu = _calc_pu(client, child["id"])
        assert pu["status"] == "configured"
        assert pu["effective_base_amount"] == pytest.approx(LG_BASE_KV)

    @pytest.mark.parametrize("operation,extra", [
        ("reverse_polarity", {}),
        ("absolute_value", {}),
        ("multiply_constant", {"parameters": {"constant": 2.0}}),
    ])
    def test_unary_on_semantic_vab_keeps_ll_base(self, client, setup, operation, extra):
        vab = _create_ll(client, "AB")[0]
        child = _create(client, f"{operation}(VAB)", operation, [_calc_ref(vab)], **extra)
        assert _calc_pu(client, child["id"])["effective_base_amount"] == pytest.approx(LL_BASE_KV)

    def test_current_multi_input_is_unaffected(self, client, setup):
        """DEC-116 is Voltage-only: Current has no L-G/L-L concept."""
        sid = setup["source_id"]
        total = _create(client, "IR + IY", "addition", [_src(sid, "KPDN1_IR"), _src(sid, "KPDN1_IY")])
        assert _calc_pu(client, total["id"])["reason"] != UNDETERMINED_TEXT


class TestArithmeticUnchanged:
    def test_engineering_values_are_exact(self, client, setup):
        sid = setup["source_id"]
        va, vb = _source_values(client, sid, "KPDN1_VR"), _source_values(client, sid, "KPDN1_VY")
        sub = _create(client, "VR - VY", "subtraction", [_src(sid, "KPDN1_VR"), _src(sid, "KPDN1_VY")])
        add = _create(client, "VR + VY", "addition", [_src(sid, "KPDN1_VR"), _src(sid, "KPDN1_VY")])
        vab = _create_ll(client, "AB")[0]
        rms = _create(client, "RMS(KPDN1 VAB)", "rms", [_calc_ref(vab)], parameters={"nominal_frequency_hz": 50})

        np.testing.assert_array_equal(_stored_values(client, sub["id"]), va - vb)
        np.testing.assert_array_equal(_stored_values(client, add["id"]), va + vb)
        np.testing.assert_array_equal(_stored_values(client, vab["id"]), va - vb)
        time = client.app.state.calculated_channel_registry.get(WS, rms["id"]).time
        np.testing.assert_array_equal(_stored_values(client, rms["id"]), evaluate_rms(time, va - vb, 50.0))

        # Engineering-mode serving is untouched; base_required per-unit mode
        # serves the same engineering values, never a divided result.
        eng = _waveform(client, sub["id"], "engineering")
        pu = _waveform(client, sub["id"], "per_unit")
        np.testing.assert_array_equal(np.array(eng["values"], float), va - vb)
        assert pu["per_unit_status"] == "base_required"
        np.testing.assert_array_equal(np.array(pu["values"], float), va - vb)


class TestOwnerUatRegression:
    def test_source_default_generic_then_semantic(self, client, comtrade_fixtures_dir):
        """The exact owner flow: 275 kV Source Default, VR/VY phase-ground.
        Before DEC-116 VR - VY was divided by 158.77 kV; now base_required.
        Semantic VAB then uses 275 kV."""
        source_id = _upload(client, comtrade_fixtures_dir)
        _configure(client, source_id, "source_default")
        generic = _create(client, "VR - VY", "subtraction", [_src(source_id, "KPDN1_VR"), _src(source_id, "KPDN1_VY")])
        assert _calc_pu(client, generic["id"])["status"] == "base_required"
        assert _waveform(client, generic["id"], "per_unit")["per_unit_status"] == "base_required"

        vab = _create_ll(client, "AB")[0]
        pu = _waveform(client, vab["id"], "per_unit")
        assert pu["per_unit_status"] == "configured"
        np.testing.assert_allclose(np.array(pu["values"], float), _stored_values(client, vab["id"]) / LL_BASE_KV, rtol=1e-12)
