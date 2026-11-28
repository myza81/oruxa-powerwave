"""D5A-2B2C-1B: recorded Impedance Locus and Distance Protection consume the unified measurement side of Recording Details.

Independent, hand-derived oracles (never copied from the code under test). The established D5A reference example:

    VT 110000 V : 110 V  (ratio 1000)          CT 1000 A : 5 A  (ratio 200)
    V primary = 66 000 V,  V secondary = 66 V      I primary = 400 A,  I secondary = 2 A
    Z primary = 66 000 / 400 = 165 ohm            Z secondary = 66 / 2 = 33 ohm
    Current lags voltage by 30 deg, so Z = |Z| at +30 deg:  R = |Z| cos 30,  X = |Z| sin 30.
    Balanced loops: Vab = Va - Vb = sqrt(3) V at +30 deg,  Iab = Ia - Ib = sqrt(3) I at 0 deg  ->  Zab = (V/I) at +30 deg.

Whatever the recorded sides of Voltage and Current, the physical impedance is the same, so a correct implementation gives 165 ohm
for a Primary output and 33 ohm for a Secondary output in ALL eight (V side x I side x output side) combinations -- a wrong ratio,
a reversed ratio or a double conversion each produces a different number (e.g. 165 x 1000, 33 / 200, 0.033, 165 / 40000).

The recorded request carries NO side and NO ratio: the sides come from Recording Details, either from the recording's own P/S
declarations or from engineer Measurement-Group / recording settings that CONTRADICT the declarations.
"""

from __future__ import annotations

import itertools
import math

import pytest

from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from tests.test_d5a2a_protection_instrument_context_api import _contexts, _ct, _group, _vt
from tests.test_d5a2b1_independent_side_conversion import (  # noqa: F401  (client is the shared fixture)
    ANGLE, CT_P, CT_S, I_PRI, I_SEC, V_PRI, V_SEC, VT_P, VT_S, Z_PRI, Z_SEC, _ALL, _bay, _dist, _dist_locus, _imp, _imp_locus,
    _upload, client,
)
from tests.test_d5a_ui_002_group_measurement_side import _put, _set_rec
from tests.test_distance_protection_analysis_api import _mho_zone_params

SIDES = ("primary", "secondary")
OPPOSITE = {"primary": "secondary", "secondary": "primary"}
LOOPS = ("AB", "BC", "CA")


def _expected(out: str) -> tuple[float, float, float]:
    magnitude = Z_PRI if out == "primary" else Z_SEC
    return magnitude, magnitude * math.cos(math.radians(ANGLE)), magnitude * math.sin(math.radians(ANGLE))


def _ws(tag: str) -> str:
    return f"1b-{tag}"


def _opposite_flags(vs: str, cs: str) -> dict[str, str]:
    """P/S flags that say the OPPOSITE of the true sides on every channel (so only an engineer setting can be right)."""
    return {n: ("S" if (vs if n[0] == "V" else cs) == "primary" else "P") for n in _ALL}


def _recording(client, ws, vs, cs, *, authority, **bay):
    """One bay whose recorded magnitudes follow (vs, cs). `declared`: the P/S flags tell the truth. `group_override`: the flags
    say the opposite and the engineer sets each Measurement Group. `recording_correction`: (uniform sides only) the flags say the
    opposite and the engineer corrects the whole recording."""
    if authority == "declared":
        return _bay(client, ws, v_side=vs, i_side=cs, **bay)
    src, ctx = _bay(client, ws, v_side=vs, i_side=cs, ps=_opposite_flags(vs, cs), **bay)
    if authority == "group_override":
        _put(client, ws, src, f"vg-{src}", vs)
        _put(client, ws, src, f"ig-{src}", cs)
    else:
        assert vs == cs
        _set_rec(client, ws, src, vs, "the recorder's P/S flags are wrong")
    return src, ctx


def _assert_point(body, out, *, label=""):
    mag, r, x = _expected(out)
    assert body["status"] == "computed", (label, body)
    assert body["magnitude_ohm"] == pytest.approx(mag, rel=1e-3), label
    assert body["resistance_ohm"] == pytest.approx(r, rel=1e-3), label
    assert body["reactance_ohm"] == pytest.approx(x, rel=1e-3), label
    assert body["angle_deg"] == pytest.approx(ANGLE, abs=0.05), label


def _assert_conversion(info, vs, cs, out, *, v_authority, i_authority):
    assert info["mode"] == "independent_sides"
    assert (info["voltage_side"], info["current_side"], info["output_side"]) == (vs, cs, out)
    assert info["vt_ratio_applied"] == (pytest.approx(1000.0) if vs != out else None)      # a ratio only where a side differs
    assert info["ct_ratio_applied"] == (pytest.approx(200.0) if cs != out else None)
    assert (info["voltage_side_authority"], info["current_side_authority"]) == (v_authority, i_authority)
    assert info["block_code"] is None


def _all_endpoints(client, ws, ctx, vs, cs, out, **authority):
    """The selected-time and locus endpoints of both analyzers, with NO side and NO ratio in the request."""
    imp = _imp(client, ws, ctx, impedance_basis=out)
    assert imp.status_code == 200, imp.text
    _assert_point(imp.json(), out, label="impedance")
    _assert_conversion(imp.json()["side_conversion"], vs, cs, out, **authority)
    assert imp.json()["recording_basis"] == (vs if vs == cs else None)
    locus = _imp_locus(client, ws, ctx, impedance_basis=out).json()
    assert len(locus["points"]) == 3
    for point in locus["points"]:
        _assert_point(point, out, label="impedance locus")
    _assert_conversion(locus["side_conversion"], vs, cs, out, **authority)
    for loop in LOOPS:
        dist = _dist(client, ws, ctx, loop=loop, impedance_basis=out)
        assert dist.status_code == 200, dist.text
        _assert_point(dist.json(), out, label=f"distance {loop}")
        _assert_conversion(dist.json()["side_conversion"], vs, cs, out, **authority)
    dist_locus = _dist_locus(client, ws, ctx, loop="AB", impedance_basis=out).json()
    for point in dist_locus["points"]:
        _assert_point(point, out, label="distance locus")
    _assert_conversion(dist_locus["side_conversion"], vs, cs, out, **authority)


# =========================================================================== the 2 x 2 x 2 matrix through all four endpoints


@pytest.mark.parametrize("vs,cs", list(itertools.product(SIDES, repeat=2)))
def test_matrix_with_the_sides_the_recording_declares(client, vs, cs):
    ws = _ws(f"decl-{vs[:1]}{cs[:1]}")
    _src, ctx = _recording(client, ws, vs, cs, authority="declared")
    for out in SIDES:
        _all_endpoints(client, ws, ctx, vs, cs, out, v_authority="recording_channel_declared", i_authority="recording_channel_declared")


@pytest.mark.parametrize("vs,cs", list(itertools.product(SIDES, repeat=2)))
def test_matrix_with_engineer_group_settings_that_contradict_the_declarations(client, vs, cs):
    ws = _ws(f"grp-{vs[:1]}{cs[:1]}")
    src, ctx = _recording(client, ws, vs, cs, authority="group_override")
    for out in SIDES:
        _all_endpoints(client, ws, ctx, vs, cs, out, v_authority="engineer_group_override", i_authority="engineer_group_override")


@pytest.mark.parametrize("side", SIDES)
def test_matrix_with_an_engineer_recording_correction_that_contradicts_the_declarations(client, side):
    ws = _ws(f"rec-{side[:1]}")
    _src, ctx = _recording(client, ws, side, side, authority="recording_correction")
    for out in SIDES:
        _all_endpoints(client, ws, ctx, side, side, out,
                       v_authority="engineer_recording_correction", i_authority="engineer_recording_correction")


def test_the_eight_combination_numbers_are_the_hand_derived_ones_not_a_ratio_artifact(client):
    """Every mis-applied ratio would show up here as a different number; these are the literal worked-example values."""
    ws = _ws("literal")
    expected_by_output = {"primary": 165.0, "secondary": 33.0}
    for vs, cs in itertools.product(SIDES, repeat=2):
        src, ctx = _recording(client, f"{ws}-{vs[:1]}{cs[:1]}", vs, cs, authority="declared")
        for out, z in expected_by_output.items():
            body = _imp(client, f"{ws}-{vs[:1]}{cs[:1]}", ctx, impedance_basis=out).json()
            assert body["magnitude_ohm"] == pytest.approx(z, rel=1e-3), (vs, cs, out)
            assert body["magnitude_ohm"] not in (pytest.approx(z * 1000), pytest.approx(z / 1000), pytest.approx(z * 200),
                                                 pytest.approx(z / 200), pytest.approx(z / 40000), pytest.approx(z * 40000))
            # and the recorded magnitudes themselves are what the oracle says they are
            assert body["voltage_magnitude_rms"] == pytest.approx(V_PRI if vs == "primary" else V_SEC, rel=1e-3)
            assert body["current_magnitude_rms"] == pytest.approx(I_PRI if cs == "primary" else I_SEC, rel=1e-3)


# =========================================================================== independent Voltage / Current authority


def test_group_override_beats_the_recording_correction_per_quantity(client):
    """Voltage group says Primary, the recording correction says Secondary: Voltage follows its group, Current the recording."""
    ws = _ws("precedence")
    src, ctx = _bay(client, ws, v_side="primary", i_side="secondary")         # values: 66 000 V and 2 A, flags both truthful
    _set_rec(client, ws, src, "secondary")                                    # Level 1 would make the voltage Secondary too ...
    _put(client, ws, src, f"vg-{src}", "primary")                             # ... but the Voltage group is Primary
    for out in SIDES:
        body = _imp(client, ws, ctx, impedance_basis=out).json()
        _assert_point(body, out)
        _assert_conversion(body["side_conversion"], "primary", "secondary", out,
                           v_authority="engineer_group_override", i_authority="engineer_recording_correction")


def test_voltage_and_current_groups_are_configured_independently_and_a_change_reaches_the_next_computation(client):
    ws = _ws("independent")
    src, ctx = _bay(client, ws, v_side="primary", i_side="primary")
    assert _imp(client, ws, ctx, impedance_basis="primary").json()["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3)
    # The recorded numbers do not change; the engineer re-labels ONE group, and only that quantity's conversion changes.
    _put(client, ws, src, f"vg-{src}", "secondary")        # 66 000 now means "66 000 V secondary": Z = 66 000 * 1000 / 400
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(66000.0 * 1000.0 / 400.0, rel=1e-3)
    assert body["side_conversion"]["voltage_side"] == "secondary" and body["side_conversion"]["current_side"] == "primary"
    _put(client, ws, src, f"vg-{src}", "primary")          # back
    _put(client, ws, src, f"ig-{src}", "secondary")        # 400 now means "400 A secondary": Z = 66 000 / (400 * 200)
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert body["magnitude_ohm"] == pytest.approx(66000.0 / (400.0 * 200.0), rel=1e-3)
    assert body["side_conversion"]["voltage_side"] == "primary" and body["side_conversion"]["current_side"] == "secondary"


def test_changing_the_output_side_changes_only_the_conversion(client):
    ws = _ws("output")
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")
    primary = _imp(client, ws, ctx, impedance_basis="primary").json()
    secondary = _imp(client, ws, ctx, impedance_basis="secondary").json()
    assert primary["magnitude_ohm"] == pytest.approx(165.0, rel=1e-3) and secondary["magnitude_ohm"] == pytest.approx(33.0, rel=1e-3)
    assert primary["magnitude_ohm"] / secondary["magnitude_ohm"] == pytest.approx(1000.0 / 200.0, rel=1e-3)   # VT ratio / CT ratio


def test_the_declarations_are_never_rewritten_by_an_engineer_setting(client):
    ws = _ws("evidence")
    src, ctx = _recording(client, ws, "secondary", "primary", authority="group_override")
    declared = {c["name"]: c["measurement_side"] for c in
                client.get(f"/api/v1/workspaces/{ws}/sources/{src}/channels").json()["analog_channels"] if c["name"].startswith("ZBAY_")}
    assert declared == {"ZBAY_VA": "primary", "ZBAY_VB": "primary", "ZBAY_VC": "primary",        # the flags said the opposite
                        "ZBAY_IA": "secondary", "ZBAY_IB": "secondary", "ZBAY_IC": "secondary"}
    _all_endpoints(client, ws, ctx, "secondary", "primary", "primary",
                   v_authority="engineer_group_override", i_authority="engineer_group_override")


# =========================================================================== transformer ratios only where they are needed


def test_no_ratio_is_needed_when_both_quantities_are_already_on_the_output_side(client):
    for out in SIDES:
        ws = _ws(f"noratio-{out[:1]}")
        _src, ctx = _bay(client, ws, v_side=out, i_side=out, groups=False)           # no Measurement Group, no VT, no CT at all
        for body in (_imp(client, ws, ctx, impedance_basis=out).json(), _dist(client, ws, ctx, impedance_basis=out).json()):
            _assert_point(body, out)
            assert (body["side_conversion"]["vt_ratio_applied"], body["side_conversion"]["ct_ratio_applied"]) == (None, None)
            assert (body["vt_primary"], body["vt_secondary"], body["ct_primary"], body["ct_secondary"]) == (None,) * 4


@pytest.mark.parametrize("vs,cs,out,needs_vt,needs_ct", [
    ("primary", "secondary", "primary", False, True),       # only the CT converts
    ("secondary", "primary", "primary", True, False),       # only the VT converts
    ("primary", "secondary", "secondary", True, False),
    ("secondary", "primary", "secondary", False, True),
])
def test_only_the_quantity_that_must_convert_needs_its_transformer(client, vs, cs, out, needs_vt, needs_ct):
    ws = _ws(f"one-{vs[:1]}{cs[:1]}{out[:1]}")
    src, ctx = _bay(client, ws, v_side=vs, i_side=cs)
    if needs_vt:
        client.app.state.current_group_config_registry.delete(ws, f"ig-{src}")       # the unneeded CT is absent ...
    if needs_ct:
        client.app.state.voltage_group_config_registry.delete(ws, f"vg-{src}")        # ... or the unneeded VT is
    body = _imp(client, ws, ctx, impedance_basis=out).json()
    _assert_point(body, out)
    assert (body["side_conversion"]["vt_ratio_applied"] is not None, body["side_conversion"]["ct_ratio_applied"] is not None) == (needs_vt, needs_ct)
    # the authoritative pair applied is echoed, and only for the quantity that converted
    assert (body["vt_primary"], body["vt_secondary"]) == ((VT_P, VT_S) if needs_vt else (None, None))
    assert (body["ct_primary"], body["ct_secondary"]) == ((CT_P, CT_S) if needs_ct else (None, None))


def test_a_nominal_derived_vt_is_consumable_and_keeps_its_provenance(client):
    ws = _ws("nominal")
    src, ctx = _bay(client, ws, v_side="secondary", i_side="primary", vt=(None, None))   # no stored VT
    client.app.state.voltage_group_config_registry.update_fields(ws, f"vg-{src}", vt_primary_v=None, vt_secondary_v=None,
                                                                 vt_authority="not_configured", update_vt=True)
    client.app.state.voltage_group_config_registry.update_fields(ws, f"vg-{src}", nominal_voltage_ll_kv=110.0, update_nominal=True)
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    _assert_point(body, "primary")                      # 66 V x (110 000 / 110) / 400 A
    assert body["side_conversion"]["vt_ratio_applied"] == pytest.approx(1000.0)
    report = client.get(f"{_contexts(ws)}/{ctx}/protection-recorded-input",
                        params={"analysis": "impedance", "phase": "A", "impedance_basis": "primary"}).json()
    assert report["voltage"]["transformer"]["authority"] == "auto_nominal" and report["voltage"]["transformer"]["consumable"] is True


# =========================================================================== unit normalisation (D5A-UNIT-001 preserved)


@pytest.mark.parametrize("v_unit,i_unit,v_value,i_value", [
    ("V", "A", 66000.0, 400.0), ("kV", "A", 66.0, 400.0), ("V", "kA", 66000.0, 0.4), ("kV", "kA", 66.0, 0.4),
])
def test_voltage_and_current_units_are_normalised_before_the_impedance_is_formed(client, v_unit, i_unit, v_value, i_value):
    ws = _ws(f"unit-{v_unit}{i_unit}")
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary", v_rms=v_value, i_rms=i_value, v_unit=v_unit, i_unit=i_unit)
    for out in SIDES:
        _assert_point(_imp(client, ws, ctx, impedance_basis=out).json(), out)
        _assert_point(_dist(client, ws, ctx, impedance_basis=out).json(), out)
    body = _imp(client, ws, ctx, impedance_basis="primary").json()
    assert (body["voltage_unit"], body["current_unit"]) == (v_unit, i_unit)


def test_an_unrecognised_unit_is_refused_not_divided_raw_and_labelled_ohms(client):
    ws = _ws("badunit")
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary", v_unit="furlongs")
    for body in (_imp(client, ws, ctx, impedance_basis="primary").json(), _dist(client, ws, ctx, impedance_basis="primary").json()):
        # The phasor layer already withholds a channel whose unit it cannot read ("missing"); the conversion-layer refusal
        # (`unsupported_*_unit`) is covered by the D5A-UNIT-001 wiring test. Either way no number is produced.
        assert body["status"] in ("missing", "needs_configuration"), body
        assert body["magnitude_ohm"] is None and body["resistance_ohm"] is None and body["reactance_ohm"] is None


# =========================================================================== low-current guardrails keep judging the RECORDED current


@pytest.mark.parametrize("current_side,i_rms,out,expected_status", [
    ("secondary", 0.0005, "secondary", "needs_configuration"),   # 0.5 mA: below the 1 mA floor
    ("secondary", 0.0005, "primary", "needs_configuration"),     # x200 = 0.1 A would pass an UNSCALED floor; the recorded 0.5 mA must not
    ("secondary", 0.002, "primary", "computed"),
    ("secondary", 0.002, "secondary", "computed"),
])
def test_the_low_current_floor_judges_the_recorded_current_whatever_the_output_side(client, current_side, i_rms, out, expected_status):
    ws = _ws(f"floor-{i_rms}-{out[:1]}")
    _src, ctx = _bay(client, ws, v_side="secondary", i_side=current_side, i_rms=i_rms)
    imp = _imp(client, ws, ctx, impedance_basis=out).json()
    dist = _dist(client, ws, ctx, impedance_basis=out).json()
    assert imp["status"] == dist["status"] == expected_status
    if expected_status == "needs_configuration":
        assert imp["reason_code"] == "current_too_small" and dist["reason_code"] == "loop_current_too_small"
        assert imp["magnitude_ohm"] is None and dist["magnitude_ohm"] is None          # never a fabricated zero or infinite impedance


# =========================================================================== distance zones keep their geometry on the converted impedance


@pytest.mark.parametrize("out,z", [("primary", 165.0), ("secondary", 33.0)])
def test_zone_classification_at_the_defined_boundary_follows_the_converted_impedance(client, out, z):
    """A mho zone whose characteristic angle equals the line angle (30 deg) operates iff |Z| <= reach."""
    ws = _ws(f"zone-{out[:1]}")
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="primary")                # mixed recorded sides
    for reach, state in ((z * 1.01, "operated"), (z * 0.99, "not_operated"), (z * 1.5, "operated"), (z * 0.5, "not_operated")):
        body = _dist(client, ws, ctx, impedance_basis=out, **_mho_zone_params(1, reach_ohm=reach, characteristic_angle_deg=ANGLE)).json()
        assert body["status"] == "computed" and body["zone1"]["state"] == state, (reach, state, body["zone1"])
        assert body["zone1"]["enabled"] is True


def test_a_blocked_calculation_never_fabricates_a_zone_classification(client):
    ws = _ws("zone-blocked")
    _src, ctx = _bay(client, ws, v_side="primary", i_side="primary", ps={n: "" for n in _ALL})     # sides not defined
    body = _dist(client, ws, ctx, impedance_basis="primary", **_mho_zone_params(1, reach_ohm=1.0e9, characteristic_angle_deg=ANGLE)).json()
    assert body["status"] == "needs_configuration" and body["magnitude_ohm"] is None
    # No impedance, so no zone was evaluated: none is reported. A reach of 1e9 ohm would classify ANY valid impedance as operated.
    # (Owner review of 1B: `not_operated` is the result of a valid impedance, never a placeholder -- see
    # test_d5a_2b2c_1b_zone_not_evaluated.py.)
    assert body["zones"] == [] and [body[k] for k in ("zone1", "zone2", "zone3", "zone4")] == [None] * 4


# =========================================================================== Manual mode is unchanged


def test_manual_mode_keeps_its_own_basis_and_ratio_inputs_and_ignores_recording_details(client):
    ws = _ws("manual")
    src, _ctx = _bay(client, ws, v_side="primary", i_side="primary")
    _put(client, ws, src, f"vg-{src}", "secondary")                                    # Recording Details configuration changes ...
    query = dict(phase_label="A", voltage_basis="primary", current_basis="secondary", impedance_basis="primary",
                 vt_primary=110000, vt_secondary=110, ct_primary=1000, ct_secondary=5,
                 voltage_enabled=True, voltage_magnitude=66, voltage_unit="kV", voltage_angle_deg=0,
                 current_enabled=True, current_magnitude=2, current_unit="A", current_angle_deg=-30)
    first = client.get(f"/api/v1/workspaces/{ws}/impedance-manual", params=query).json()
    assert first["status"] == "computed" and first["magnitude_ohm"] == pytest.approx(165.0, rel=1e-6)   # 66 kV / (2 A x 200)
    _put(client, ws, src, f"ig-{src}", "secondary")
    assert client.get(f"/api/v1/workspaces/{ws}/impedance-manual", params=query).json() == first      # ... and changes nothing here
    loop = client.get(f"/api/v1/workspaces/{ws}/distance-protection-manual", params={
        "loop_label": "AB", "voltage_basis": "secondary", "current_basis": "secondary", "impedance_basis": "secondary",
        "characteristic": "mho", **{f"zone{n}_enabled": False for n in (1, 2, 3)},
        "v1_enabled": True, "v1_magnitude": 100, "v1_unit": "V", "v1_angle_deg": 0,
        "v2_enabled": True, "v2_magnitude": 100, "v2_unit": "V", "v2_angle_deg": -120,
        "i1_enabled": True, "i1_magnitude": 1, "i1_unit": "A", "i1_angle_deg": -30,
        "i2_enabled": True, "i2_magnitude": 1, "i2_unit": "A", "i2_angle_deg": -150})
    assert loop.status_code == 200, loop.text
    assert loop.json()["status"] == "computed" and loop.json()["magnitude_ohm"] == pytest.approx(100.0, rel=1e-6)
