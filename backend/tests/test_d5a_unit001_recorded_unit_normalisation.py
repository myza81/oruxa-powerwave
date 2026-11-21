"""D5A-UNIT-001: recorded Impedance and Distance must report actual ohms whatever the channels' SI scale.

Equivalent physical inputs (66 kV, 400 A, current lagging 30 deg => 165 ohm at +30 deg) are recorded in all four
V/kV x A/kA unit combinations; every combination must give the same ohms, on every recorded endpoint, in legacy
and strict mode. Expected values are derived by hand from the physical quantities, never from the production code.
Before the correction the legacy path divided raw channel magnitudes: kV/A gave 0.165 and V/kA gave 165 000.
"""

from __future__ import annotations

import math

import pytest

from app.domain import side_conversion
from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    DIRECTION_FORWARD,
    MANUAL_ALGORITHM_VERSION as DISTANCE_MANUAL_VERSION,
    ZONE_GEOMETRY_ENGINE_VERSION,
    ZoneSettings,
    evaluate_manual_distance,
)
from app.domain.impedance import MANUAL_ALGORITHM_VERSION as IMPEDANCE_MANUAL_VERSION, evaluate_manual_impedance
from app.domain.phasor import ManualPhasorRoleInput
from app.domain.side_conversion import normalise_to_amperes, normalise_to_volts
from tests.test_d5a2a_protection_instrument_context_api import _contexts
from tests.test_d5a2b1_independent_side_conversion import (  # noqa: F401  (client is the shared fixture)
    ANGLE, CT_P, CT_S, I_PRI, I_SEC, V_PRI, V_SEC, VT_P, VT_S, Z_PRI, Z_SEC,
    _bay, _comtrade, _context, _dist, _dist_locus, _imp, _imp_locus, _strict, _upload, client,
)

SCALE = {"V": 1.0, "kV": 1e-3, "A": 1.0, "kA": 1e-3}          # value in that unit = SI value * scale
MATRIX = [("V", "A"), ("V", "kA"), ("kV", "A"), ("kV", "kA")]
RATIOS = dict(vt_primary=VT_P, vt_secondary=VT_S, ct_primary=CT_P, ct_secondary=CT_S)
R_FACTOR, X_FACTOR = math.cos(math.radians(ANGLE)), math.sin(math.radians(ANGLE))


def _record(client, ws, vu, iu, *, side="primary", **kw):
    """The same physical quantities, expressed in the requested channel units."""
    v_si, i_si = (V_PRI, I_PRI) if side == "primary" else (V_SEC, I_SEC)
    return _bay(client, ws, v_side=side, i_side=side, v_rms=v_si * SCALE[vu], i_rms=i_si * SCALE[iu],
                v_unit=vu, i_unit=iu, **kw)


def _legacy(basis="primary", out="primary", **extra):
    return dict(recording_basis=basis, impedance_basis=out, **extra)


# =========================================================================== the acceptance criterion


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_recorded_impedance_is_165_ohm_for_every_unit_combination(client, vu, iu):
    ws = f"u001-imp-{vu}-{iu}"
    _, ctx = _record(client, ws, vu, iu)
    body = _imp(client, ws, ctx, **_legacy()).json()
    assert body["status"] == "computed", body
    assert (body["voltage_unit"], body["current_unit"]) == (vu, iu)
    assert body["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)
    assert body["resistance_ohm"] == pytest.approx(Z_PRI * R_FACTOR, rel=1e-3)
    assert body["reactance_ohm"] == pytest.approx(Z_PRI * X_FACTOR, rel=1e-3)
    assert body["angle_deg"] == pytest.approx(ANGLE, abs=0.05)
    assert body["algorithm_version"] == "impedance_locus_v2"


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_recorded_impedance_locus_is_165_ohm_for_every_unit_combination(client, vu, iu):
    ws = f"u001-loc-{vu}-{iu}"
    _, ctx = _record(client, ws, vu, iu)
    points = _imp_locus(client, ws, ctx, **_legacy()).json()["points"]
    assert len(points) == 3 and all(p["status"] == "computed" for p in points)
    assert all(p["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3) for p in points)


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_recorded_distance_loops_are_165_ohm_for_every_unit_combination(client, vu, iu):
    """Phase-to-phase loops: Vab/Iab for a balanced set equals the phase impedance."""
    ws = f"u001-dist-{vu}-{iu}"
    _, ctx = _record(client, ws, vu, iu)
    for loop in ("AB", "BC", "CA"):
        body = _dist(client, ws, ctx, loop=loop, **_legacy()).json()
        assert body["status"] == "computed", body
        assert body["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3), (vu, iu, loop)
        assert body["angle_deg"] == pytest.approx(ANGLE, abs=0.05)
        assert body["algorithm_version"] == "distance_protection_v2"
    locus = _dist_locus(client, ws, ctx, **_legacy()).json()["points"]
    assert all(p["status"] == "computed" and p["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3) for p in locus)


def test_all_unit_combinations_agree_with_each_other_to_numerical_precision(client):
    results = {}
    for vu, iu in MATRIX:
        ws = f"u001-agree-{vu}-{iu}"
        _, ctx = _record(client, ws, vu, iu)
        results[(vu, iu)] = _imp(client, ws, ctx, **_legacy()).json()["magnitude_ohm"]
    base = results[("V", "A")]
    # Agreement is limited by the fixture's six-decimal ASCII sample quantisation (~4e-8), not by the code.
    assert all(v == pytest.approx(base, rel=1e-6) for v in results.values()), results


def test_the_original_thousand_fold_defect_cannot_recur(client):
    """Regression for D5A-UNIT-001: kV/A used to report 0.165 and V/kA 165 000 for a true 165 ohm."""
    ws_a, ws_b = "u001-defect-kva", "u001-defect-vka"
    _, ctx_a = _record(client, ws_a, "kV", "A")
    _, ctx_b = _record(client, ws_b, "V", "kA")
    kv_a = _imp(client, ws_a, ctx_a, **_legacy()).json()["magnitude_ohm"]
    v_ka = _imp(client, ws_b, ctx_b, **_legacy()).json()["magnitude_ohm"]
    assert kv_a == pytest.approx(165.0, rel=1e-3) and kv_a != pytest.approx(0.165, rel=1e-3)
    assert v_ka == pytest.approx(165.0, rel=1e-3) and v_ka != pytest.approx(165000.0, rel=1e-3)
    for ws, ctx in ((ws_a, ctx_a), (ws_b, ctx_b)):
        dist = _dist(client, ws, ctx, **_legacy()).json()["magnitude_ohm"]
        assert dist == pytest.approx(165.0, rel=1e-3)


# =========================================================================== CT/VT conversion and strict parity


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_legacy_ct_vt_conversion_applies_exactly_once_after_normalisation(client, vu, iu):
    ws = f"u001-ctvt-{vu}-{iu}"
    _, pri_ctx = _record(client, ws, vu, iu, side="primary")
    assert _imp(client, ws, pri_ctx, **_legacy("primary", "secondary", **RATIOS)).json()["magnitude_ohm"] \
        == pytest.approx(Z_SEC, rel=1e-3)                                  # 165 * (200 / 1000)
    assert _imp(client, ws, pri_ctx, **_legacy("primary", "primary", **RATIOS)).json()["magnitude_ohm"] \
        == pytest.approx(Z_PRI, rel=1e-3)                                  # same basis: no ratio applied
    ws2 = f"u001-ctvt2-{vu}-{iu}"
    _, sec_ctx = _record(client, ws2, vu, iu, side="secondary")
    assert _imp(client, ws2, sec_ctx, **_legacy("secondary", "primary", **RATIOS)).json()["magnitude_ohm"] \
        == pytest.approx(Z_PRI, rel=1e-3)                                  # 33 * (1000 / 200)
    dist = _dist(client, ws2, sec_ctx, **_legacy("secondary", "primary", **RATIOS)).json()
    assert dist["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_legacy_and_strict_agree_for_equivalent_inputs(client, vu, iu):
    ws = f"u001-parity-{vu}-{iu}"
    _, ctx = _record(client, ws, vu, iu)
    for out in ("primary", "secondary"):
        legacy = _imp(client, ws, ctx, **_legacy("primary", out, **RATIOS)).json()["magnitude_ohm"]
        strict = _imp(client, ws, ctx, **_strict("primary", "primary", out)).json()["magnitude_ohm"]
        assert legacy == pytest.approx(strict, rel=1e-9) == pytest.approx(Z_PRI if out == "primary" else Z_SEC, rel=1e-3)
        dl = _dist(client, ws, ctx, **_legacy("primary", out, **RATIOS)).json()["magnitude_ohm"]
        ds = _dist(client, ws, ctx, **_strict("primary", "primary", out)).json()["magnitude_ohm"]
        assert dl == pytest.approx(ds, rel=1e-9)


# =========================================================================== low-current / zero-current floor (1 mA)


@pytest.mark.parametrize("unit,gain,rms,v_rms,imp_ok,dist_ok", [
    ("kA", 1e-6, 1.5e-6, 0.15, True, True),     # 1.5 mA expressed in kA: above the 1 mA floor (was refused when judged raw)
    ("kA", 1e-6, 5e-7, 0.05, False, False),     # 0.5 mA expressed in kA: below it (loop current 0.87 mA is also below)
    ("A", 1e-3, 0.0011, 0.11, True, True),      # 1.1 mA
    ("A", 1e-3, 0.0009, 0.09, False, True),     # 0.9 mA: |Ia| below the floor, but the Distance LOOP current sqrt3 x 0.9 = 1.56 mA is not
    ("A", 1e-3, 0.0005, 0.05, False, False),    # 0.5 mA: loop current 0.87 mA is below it
])
def test_the_current_floor_is_judged_in_amperes(client, unit, gain, rms, v_rms, imp_ok, dist_ok):
    """The 1 mA floor is an ampere threshold: Impedance judges |I|, Distance judges the loop current |I1 - I2|."""
    ws = f"u001-floor-{unit}-{rms}"
    _, ctx = _bay(client, ws, v_side="secondary", i_side="secondary", v_rms=v_rms, i_rms=rms, i_unit=unit, i_gain=gain,
                  groups=False)
    imp = _imp(client, ws, ctx, **_legacy("secondary", "secondary")).json()
    dist = _dist(client, ws, ctx, **_legacy("secondary", "secondary")).json()
    if imp_ok:
        assert imp["status"] == "computed" and imp["magnitude_ohm"] == pytest.approx(100.0, rel=2e-3)
    else:
        assert (imp["status"], imp["reason_code"], imp["magnitude_ohm"]) == ("needs_configuration", "current_too_small", None)
    if dist_ok:
        assert dist["status"] == "computed" and dist["magnitude_ohm"] == pytest.approx(100.0, rel=2e-3)
    else:
        assert (dist["status"], dist["reason_code"], dist["magnitude_ohm"]) == (
            "needs_configuration", "loop_current_too_small", None)


def test_zero_current_never_yields_an_impedance(client):
    """An all-zero current waveform is rejected by the existing waveform-eligibility check before any division."""
    ws = "u001-zero-current"
    _, ctx = _bay(client, ws, v_side="secondary", i_side="secondary", v_rms=10.0, i_rms=0.0, groups=False)
    for body in (_imp(client, ws, ctx, **_legacy("secondary", "secondary")).json(),
                 _dist(client, ws, ctx, **_legacy("secondary", "secondary")).json()):
        assert body["status"] != "computed" and body["magnitude_ohm"] is None


# =========================================================================== Distance zone classification


def _zone_state(client, ws, ctx, **zone):
    body = _dist(client, ws, ctx, **_legacy(), **zone).json()
    assert body["status"] == "computed", body
    return body["zone1"]["state"]


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_mho_classification_is_independent_of_channel_units(client, vu, iu):
    """True loop impedance 165 ohm at 30 deg: inside, outside and near the boundary of a mho reach along 30 deg."""
    ws = f"u001-mho-{vu}-{iu}"
    _, ctx = _record(client, ws, vu, iu)
    for reach, expected in [(200.0, "operated"), (150.0, "not_operated"), (165.5, "operated"), (164.5, "not_operated"),
                            (10.0, "not_operated"), (1000.0, "operated")]:
        assert _zone_state(client, ws, ctx, zone1_enabled=True, zone1_reach_ohm=reach,
                           zone1_characteristic_angle_deg=ANGLE) == expected, (vu, iu, reach)


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_quadrilateral_classification_is_independent_of_channel_units(client, vu, iu):
    """Z = 165 at 30 deg has R = 142.9 ohm and X = 82.5 ohm; a quadrilateral with 90 deg reactance line is R-X axis aligned."""
    ws = f"u001-quad-{vu}-{iu}"
    _, ctx = _record(client, ws, vu, iu)
    base = dict(characteristic="quadrilateral", zone1_enabled=True, zone1_characteristic_angle_deg=90.0,
                zone1_resistive_reach_forward_ohm=160.0, zone1_resistive_reach_reverse_ohm=10.0)
    assert _zone_state(client, ws, ctx, zone1_reactive_reach_ohm=100.0, **base) == "operated"        # X 82.5 < 100, R 142.9 < 160
    assert _zone_state(client, ws, ctx, zone1_reactive_reach_ohm=50.0, **base) == "not_operated"     # X 82.5 > 50
    assert _zone_state(client, ws, ctx, zone1_reactive_reach_ohm=100.0,
                       **{**base, "zone1_resistive_reach_forward_ohm": 120.0}) == "not_operated"     # R 142.9 > 120


def test_zone_classifications_the_defect_used_to_get_wrong_are_now_physically_correct(client):
    """Historical outputs that change: kV/A (0.165 ohm) used to fall INSIDE a 10 ohm reach; V/kA (165 000 ohm) used to
    fall OUTSIDE a 1000 ohm reach. The physical 165 ohm is outside the first and inside the second."""
    _, ctx_a = _record(client, "u001-zone-kva", "kV", "A")
    _, ctx_b = _record(client, "u001-zone-vka", "V", "kA")
    assert _zone_state(client, "u001-zone-kva", ctx_a, zone1_enabled=True, zone1_reach_ohm=10.0,
                       zone1_characteristic_angle_deg=ANGLE) == "not_operated"
    assert _zone_state(client, "u001-zone-vka", ctx_b, zone1_enabled=True, zone1_reach_ohm=1000.0,
                       zone1_characteristic_angle_deg=ANGLE) == "operated"


# =========================================================================== unknown / unsupported units


@pytest.mark.parametrize("fn,magnitude,unit,expected", [
    (normalise_to_volts, 66.0, "kV", 66000.0), (normalise_to_volts, 66000.0, "V", 66000.0),
    (normalise_to_amperes, 0.4, "kA", 400.0), (normalise_to_amperes, 400.0, "A", 400.0),
])
def test_the_helpers_use_the_shared_unit_layer(fn, magnitude, unit, expected):
    assert fn(magnitude, unit) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("fn,unit", [
    (normalise_to_volts, "furlongs"), (normalise_to_volts, ""), (normalise_to_volts, None), (normalise_to_volts, "A"),
    (normalise_to_amperes, "furlongs"), (normalise_to_amperes, ""), (normalise_to_amperes, None), (normalise_to_amperes, "V"),
])
def test_an_unsupported_unit_is_never_assumed_to_be_volts_or_amperes(fn, unit):
    assert fn(5.0, unit) is None


def test_a_non_finite_magnitude_is_left_to_the_calculation_guardrails_not_called_a_unit_error():
    assert math.isnan(normalise_to_volts(float("nan"), "kV"))


@pytest.mark.parametrize("bad_unit,code", [("kV", "unsupported_voltage_unit"), ("A", "unsupported_current_unit")])
def test_an_unsupported_unit_is_refused_with_a_reason_and_never_divided_raw(client, monkeypatch, bad_unit, code):
    """Wiring check: when the shared unit layer cannot normalise a consumed unit, every recorded endpoint refuses."""
    real = side_conversion.scale_to_canonical
    monkeypatch.setattr(side_conversion, "scale_to_canonical", lambda q, u: None if u == bad_unit else real(q, u))
    ws = f"u001-badunit-{bad_unit}"
    _, ctx = _record(client, ws, "kV", "A")
    for body in (_imp(client, ws, ctx, **_legacy()).json(), _dist(client, ws, ctx, **_legacy()).json(),
                 _imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json()):
        assert (body["status"], body["reason_code"]) == ("needs_configuration", code), body
        assert body["magnitude_ohm"] is None and body["resistance_ohm"] is None and body["reactance_ohm"] is None
    for points in (_imp_locus(client, ws, ctx, **_legacy()).json()["points"],
                   _dist_locus(client, ws, ctx, **_legacy()).json()["points"]):
        assert {p["reason_code"] for p in points} == {code} and all(p["magnitude_ohm"] is None for p in points)


# =========================================================================== manual mode and isolation (non-regression)


@pytest.mark.parametrize("vu,iu", MATRIX)
def test_manual_mode_is_unchanged_and_unit_independent(vu, iu):
    v = ManualPhasorRoleInput(enabled=True, magnitude=V_PRI * SCALE[vu], unit=vu, angle_deg=ANGLE)
    i = ManualPhasorRoleInput(enabled=True, magnitude=I_PRI * SCALE[iu], unit=iu, angle_deg=0.0)
    imp = evaluate_manual_impedance(v, i, phase_label="A", voltage_basis="primary", current_basis="primary",
                                    impedance_basis="primary", **RATIOS)
    assert imp.magnitude_ohm == pytest.approx(Z_PRI, rel=1e-9)
    zero_v = ManualPhasorRoleInput(enabled=True, magnitude=0.0, unit=vu, angle_deg=0.0)
    zero_i = ManualPhasorRoleInput(enabled=True, magnitude=0.0, unit=iu, angle_deg=0.0)
    off = ZoneSettings(enabled=False, direction=DIRECTION_FORWARD)
    dist = evaluate_manual_distance(v, zero_v, i, zero_i, loop_label="AB", voltage_basis="primary", current_basis="primary",
                                    impedance_basis="primary", characteristic=CHARACTERISTIC_MHO, zone1=off, zone2=off,
                                    zone3=off, **RATIOS)
    assert dist.magnitude_ohm == pytest.approx(Z_PRI, rel=1e-9)


def test_two_recordings_with_different_units_in_one_workspace_stay_independent(client):
    ws = "u001-iso"
    _, ctx1 = _record(client, ws, "kV", "A")
    cfg, dat = _comtrade(v_rms=V_PRI, i_rms=I_PRI * 1e-3, ps={n: "P" for n in ("VA", "VB", "VC", "IA", "IB", "IC")},
                         v_unit="V", i_unit="kA")
    second = _upload(client, ws, cfg, dat, stem="second")
    for auto in client.get(_contexts(ws)).json():
        if auto["id"] != ctx1:
            client.delete(f"{_contexts(ws)}/{auto['id']}")
    st = client.app.state
    for g in st.measurement_group_registry.list_for_source(ws, second):
        st.measurement_group_registry.remove(ws, g.id)
        st.voltage_group_config_registry.delete(ws, g.id)
        st.current_group_config_registry.delete(ws, g.id)
    ctx2 = _context(client, ws, second)
    one = _imp(client, ws, ctx1, **_legacy()).json()
    two = _imp(client, ws, ctx2, **_legacy()).json()
    assert (one["voltage_unit"], one["current_unit"], two["voltage_unit"], two["current_unit"]) == ("kV", "A", "V", "kA")
    assert one["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3) and two["magnitude_ohm"] == pytest.approx(Z_PRI, rel=1e-3)


# =========================================================================== versioning / provenance


def test_algorithm_versions_identify_the_corrected_recorded_calculation(client):
    ws = "u001-version"
    _, ctx = _record(client, ws, "V", "A")
    assert _imp(client, ws, ctx, **_legacy()).json()["algorithm_version"] == "impedance_locus_v2"
    assert _dist(client, ws, ctx, **_legacy()).json()["algorithm_version"] == "distance_protection_v2"
    assert _imp(client, ws, ctx, **_strict("primary", "primary", "primary")).json()["algorithm_version"] == "impedance_locus_v2"


def test_manual_and_zone_geometry_identities_are_unchanged():
    assert IMPEDANCE_MANUAL_VERSION == "impedance_manual_v1"
    assert DISTANCE_MANUAL_VERSION == "distance_protection_manual_v1"
    assert ZONE_GEOMETRY_ENGINE_VERSION == "distance_protection_v1"


# =========================================================================== OpenAPI contract wording


@pytest.mark.parametrize("path", ["impedance", "impedance-locus", "distance-protection", "distance-protection-locus"])
def test_openapi_distinguishes_legacy_and_strict_parameters(client, path):
    spec = client.app.openapi()
    op = spec["paths"][f"/api/v1/workspaces/{{workspace_id}}/engineering-contexts/{{engineering_context_id}}/{path}"]["get"]
    params = {p["name"]: p for p in op["parameters"]}
    assert params["impedance_basis"]["required"] is True
    assert "BOTH modes" in params["impedance_basis"]["description"] and "OUTPUT" in params["impedance_basis"]["description"]
    assert params["recording_basis"]["required"] is False
    assert "LEGACY" in params["recording_basis"]["description"] and "422" in params["recording_basis"]["description"]
    assert "ignored" in params["recording_basis"]["description"]
    for name in ("voltage_side", "current_side"):
        assert params[name]["required"] is False and "STRICT" in params[name]["description"]
    assert "BOTH" in params["voltage_side"]["description"] and "Never inferred" in params["voltage_side"]["description"]
