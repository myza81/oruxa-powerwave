"""D5A-1: pins of the CT/VT semantics the protection engines ALREADY implement.

These tests characterise existing behaviour with hand-derived expected values; they
establish what a future recorded-path integration may rely on. No engine is changed.

Convention (codebase-wide): ratio = primary / secondary; I_sec = I_pri / ct_ratio;
V_sec = V_pri / vt_ratio; Z_pri = Z_sec * vt_ratio / ct_ratio.

Worked example used throughout: VT 110 000 V : 110 V (ratio 1000), CT 1000 A : 5 A (ratio 200).
  V_pri = 66 000 V  ->  V_sec = 66 V.   I_sec = 2 A  ->  I_pri = 400 A.
  Z_sec = 66 / 2 = 33 ohm.   Z_pri = 66 000 / 400 = 165 ohm  (= 33 * 1000 / 200).
"""

from __future__ import annotations

import math

import pytest

from app.domain.distance_protection import CHARACTERISTIC_MHO, DIRECTION_FORWARD, ZoneSettings, evaluate_manual_distance
from app.domain.impedance import (
    IMPEDANCE_BASIS_PRIMARY,
    IMPEDANCE_BASIS_SECONDARY,
    ImpedancePoint,
    convert_impedance_basis,
    evaluate_manual_impedance,
)
from app.domain.phasor import ManualPhasorRoleInput
from app.services.overcurrent_analysis_service import compute_overcurrent_manual_analysis

VT = dict(vt_primary=110000.0, vt_secondary=110.0)
CT = dict(ct_primary=1000.0, ct_secondary=5.0)
ANGLE = 60.0
Z_SEC, Z_PRI = 33.0, 165.0
R_FACTOR, X_FACTOR = math.cos(math.radians(ANGLE)), math.sin(math.radians(ANGLE))


def _v(magnitude: float, angle: float = ANGLE) -> ManualPhasorRoleInput:
    return ManualPhasorRoleInput(enabled=True, magnitude=magnitude, unit="V", angle_deg=angle)


def _i(magnitude: float, unit: str = "A") -> ManualPhasorRoleInput:
    return ManualPhasorRoleInput(enabled=True, magnitude=magnitude, unit=unit, angle_deg=0.0)


def _z(vb: str, ib: str, out: str, v: float, i: float, **ratios):
    return evaluate_manual_impedance(
        _v(v), _i(i), phase_label="A", voltage_basis=vb, current_basis=ib, impedance_basis=out,
        **{**VT, **CT, **ratios},
    )


# --- Overcurrent: primary converted exactly once, secondary never re-scaled -------------------


def _oc(basis: str, value: float, unit: str = "A", **ratios):
    return compute_overcurrent_manual_analysis(
        characteristic_id="iec_standard_inverse", tms=1.0, pickup_current_secondary=2.5,
        input_current=value, input_current_unit=unit, input_basis=basis,
        **{"ct_primary": 1200.0, "ct_secondary": 5.0, **ratios},
    )


def test_overcurrent_primary_current_is_scaled_once_by_the_ct_ratio():
    result = _oc("primary", 1200.0)                     # 1200 A / (1200/5) = 5 A
    assert result.relay_secondary_current == pytest.approx(5.0)
    assert result.multiple_of_pickup == pytest.approx(5.0 / 2.5)


def test_overcurrent_secondary_current_is_not_scaled_again_even_with_ratios_present():
    result = _oc("secondary", 5.0)                      # a second application would give 5 * 5/1200
    assert result.relay_secondary_current == pytest.approx(5.0)
    assert result.relay_secondary_current != pytest.approx(5.0 * 5.0 / 1200.0)


def test_overcurrent_kiloampere_primary_normalises_units_before_the_ratio():
    assert _oc("primary", 1.2, unit="kA").relay_secondary_current == pytest.approx(5.0)


def test_overcurrent_primary_without_a_ct_ratio_is_refused_not_guessed():
    result = _oc("primary", 1200.0, ct_primary=None, ct_secondary=None)
    assert result.status == "needs_configuration" and result.relay_secondary_current is None


def test_overcurrent_unknown_basis_is_refused_and_converts_nothing():
    result = _oc("unknown", 1200.0)
    assert result.status == "needs_configuration" and result.reason_code == "invalid_recording_basis"
    assert result.relay_secondary_current is None


# --- Impedance: V and I sides independent; one output conversion ---------------------------------


def test_impedance_voltage_primary_current_secondary_to_secondary_output():
    r = _z("primary", "secondary", "secondary", 66000.0, 2.0)
    assert r.voltage_magnitude_secondary == pytest.approx(66.0)
    assert r.current_magnitude_secondary == pytest.approx(2.0)
    assert r.magnitude_ohm == pytest.approx(Z_SEC)


def test_impedance_voltage_primary_current_secondary_to_primary_output():
    r = _z("primary", "secondary", "primary", 66000.0, 2.0)
    assert r.magnitude_ohm == pytest.approx(Z_PRI)                       # = 66000 / (2 * 200)
    assert r.resistance_ohm == pytest.approx(Z_PRI * R_FACTOR)
    assert r.reactance_ohm == pytest.approx(Z_PRI * X_FACTOR)
    assert r.angle_deg == pytest.approx(ANGLE)                           # scaling never rotates Z


def test_impedance_current_primary_voltage_secondary_is_the_mirror_case():
    r = _z("secondary", "primary", "primary", 66.0, 400.0)
    assert r.magnitude_ohm == pytest.approx(Z_PRI)


@pytest.mark.parametrize("vb,ib,v,i", [
    ("primary", "primary", 66000.0, 400.0),
    ("primary", "secondary", 66000.0, 2.0),
    ("secondary", "primary", 66.0, 400.0),
    ("secondary", "secondary", 66.0, 2.0),
])
def test_impedance_is_independent_of_which_side_each_quantity_was_entered_on(vb, ib, v, i):
    """Same physical V and I expressed on any side combination give the same Z on each output basis."""
    assert _z(vb, ib, "primary", v, i).magnitude_ohm == pytest.approx(Z_PRI)
    assert _z(vb, ib, "secondary", v, i).magnitude_ohm == pytest.approx(Z_SEC)


def test_secondary_inputs_to_secondary_output_need_no_ratio_and_apply_none():
    r = _z("secondary", "secondary", "secondary", 66.0, 2.0,
           vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None)
    assert r.status == "computed" and r.magnitude_ohm == pytest.approx(Z_SEC)


def test_impedance_primary_output_without_ratios_is_refused_not_guessed():
    r = _z("secondary", "secondary", "primary", 66.0, 2.0,
           vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None)
    assert r.status == "needs_configuration" and r.reason_code == "invalid_ratio"


@pytest.mark.parametrize("vb,ib", [("unknown", "secondary"), ("primary", "unknown"), ("", "primary")])
def test_impedance_unknown_basis_is_refused_and_converts_nothing(vb, ib):
    r = _z(vb, ib, "secondary", 66000.0, 2.0)
    assert r.status == "needs_configuration" and r.reason_code == "invalid_basis"
    assert r.magnitude_ohm is None


# --- Shared output conversion: no-op when bases match; single factor otherwise --------------------


@pytest.mark.parametrize("basis", [IMPEDANCE_BASIS_PRIMARY, IMPEDANCE_BASIS_SECONDARY])
def test_same_basis_conversion_is_an_identity_and_reads_no_ratio(basis):
    point = ImpedancePoint(resistance_ohm=16.5, reactance_ohm=28.6, magnitude_ohm=33.0, angle_deg=60.0)
    out = convert_impedance_basis(point, from_basis=basis, to_basis=basis,
                                  vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None)
    assert out == point


def test_secondary_to_primary_applies_exactly_vt_ratio_over_ct_ratio_and_round_trips():
    point = ImpedancePoint(resistance_ohm=16.5, reactance_ohm=28.0, magnitude_ohm=33.0, angle_deg=60.0)
    ratios = dict(vt_primary=110000.0, vt_secondary=110.0, ct_primary=1000.0, ct_secondary=5.0)
    primary = convert_impedance_basis(point, from_basis="secondary", to_basis="primary", **ratios)
    assert primary.magnitude_ohm == pytest.approx(33.0 * 1000.0 / 200.0)           # 165 ohm
    back = convert_impedance_basis(primary, from_basis="primary", to_basis="secondary", **ratios)
    assert back.magnitude_ohm == pytest.approx(33.0, rel=1e-12)


# --- Distance: same V/I-independent normalisation, same dimensions --------------------------------


_ZONE = ZoneSettings(enabled=False, direction=DIRECTION_FORWARD)


def _dist(vb: str, ib: str, out: str, v: float, i: float):
    zero_v = ManualPhasorRoleInput(enabled=True, magnitude=0.0, unit="V", angle_deg=0.0)
    zero_i = ManualPhasorRoleInput(enabled=True, magnitude=0.0, unit="A", angle_deg=0.0)
    return evaluate_manual_distance(
        _v(v), zero_v, _i(i), zero_i, loop_label="AB", voltage_basis=vb, current_basis=ib,
        impedance_basis=out, characteristic=CHARACTERISTIC_MHO, **VT, **CT,
        zone1=_ZONE, zone2=_ZONE, zone3=_ZONE,
    )


def test_distance_mixed_sides_match_impedance_dimensions():
    """With the second leg at zero, Vloop = V1 and Iloop = I1, so Z must equal the impedance result."""
    r = _dist("primary", "secondary", "primary", 66000.0, 2.0)
    assert r.status == "computed"
    assert r.magnitude_ohm == pytest.approx(Z_PRI)
    assert _dist("primary", "secondary", "secondary", 66000.0, 2.0).magnitude_ohm == pytest.approx(Z_SEC)


def test_distance_unknown_basis_is_refused_and_converts_nothing():
    r = _dist("unknown", "secondary", "secondary", 66000.0, 2.0)
    assert r.status == "needs_configuration" and r.reason_code == "invalid_basis"
    assert r.magnitude_ohm is None
