"""PU-MIG S2 closeout (DEC-218 application): the shared VT authority is consumed as approved, a stored secondary base is never replaced.

Worked example on the ACTUAL legacy fixture (`synth_measurement_groups`, the recording the VLT-REF-001 contracts use): channel N275_VR,
Line-to-line reference, nominal 275 kV, the CFG's own VT secondary 1.0 kV stored as the group's secondary base (1000 V). The expected
values are written from the physics, never from application code:

    pu = sample / D          D = base expressed in the unit of the SAMPLES' side
    VT ratio r = primary / secondary
    approved VT authority (DEC-215): manual > recording_metadata > auto_nominal;  auto_nominal = nominal kV x 1000 : 110 V  -> r = 2500
    an engineer's manual VT of 275 kV : 1 kV (the fixture's real VT)                                                  -> r = 275

Instantaneous versus RMS: every `pu` below is an instantaneous SAMPLE PEAK divided by a base, not a per-unit of rated RMS voltage. The
fixture's samples peak at 158.77 kV (= 275 kV / sqrt(3)) on the Primary recording and at 0.577345 kV on the Secondary one, and the base here is the
L-L nominal; the figures (5.2486, 0.577345, 0.063508) check the DIVISION and the side conversion, not how far a rated voltage sits from 1.0 pu.

The selected PU base (a stored 1 kV secondary, or the nominal) and the VT equipment ratio are independent quantities: neither changes
the other, and a disagreement between them is REPORTED (decision D-4, option P5), never "corrected" and never a reason to refuse the
approved VT authority.
"""

from __future__ import annotations

import pytest

from tests.test_per_unit_voltage_reference_safety import (  # noqa: F401  (client is the shared fixture)
    NO_NOMINAL, SECONDARY_V, VNAMES, checked, client, provenance, recording, setup_voltage_base, wave_status, ROOT,
)
from tests.test_pu_mig_s2_raw_voltage_side import build, peak as pu_peak, provenance as source_provenance, wave

NOMINAL_KV = 275.0
AUTO_RATIO = NOMINAL_KV * 1000.0 / 110.0        # 2500: the approved auto_nominal VT (110 V secondary default)
REAL_RATIO = NOMINAL_KV * 1000.0 / SECONDARY_V  # 275: the VT the fixture's CFG actually declares


def engineering_peak(client, sid):
    body = checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={"channel_name": VNAMES[0]}))
    return max(abs(v) for v in body["values"]), body["unit"]


def config(path, **extra):
    body = {"nominal_voltage_ll_kv": 275, "reference_mode": "manual", "reference_override": "line_to_line",
            "base_reference_side": "primary", "secondary_voltage_ll_v": SECONDARY_V}
    body.update(extra)
    return body


def test_the_fixtures_samples_are_what_the_worked_example_assumes(client, comtrade_fixtures_dir):
    secondary = recording(client, comtrade_fixtures_dir, "S")
    primary = recording(client, comtrade_fixtures_dir, "P")
    assert engineering_peak(client, secondary) == (pytest.approx(0.577345, rel=1e-9), "kV")     # 158.77 kV x 1.0/275
    assert engineering_peak(client, primary) == (pytest.approx(158.77, rel=1e-9), "kV")


def test_worked_example_primary_base_on_secondary_samples(client, comtrade_fixtures_dir):
    """A/B: the stored 1000 V secondary base does not change the VT authority; the engineer's manual VT corrects the number."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    path, _ = setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    sample, _unit = engineering_peak(client, sid)

    # A -- no VT stored: the shared authority derives auto_nominal (275 kV : 110 V, r = 2500). D = 275 kV / 2500 = 0.110 kV.
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert (prov["verification_state"], prov["ratio_authority"], prov["ratio_applied"]) == ("verified_converted", "auto_nominal", AUTO_RATIO)
    assert prov["effective_base_amount"] == pytest.approx(NOMINAL_KV / AUTO_RATIO, rel=1e-12)       # 0.110 kV
    assert pu_peak(body) == pytest.approx(sample / (NOMINAL_KV / AUTO_RATIO), rel=1e-12)            # 0.577345 / 0.110 = 5.2486
    # D-4 (P5): the stored 1000 V secondary base is untouched and the disagreement with the derived 110 V is reported.
    (diagnostic,) = prov["base_diagnostics"]
    assert (diagnostic["stored_secondary_ll_v"], diagnostic["derived_secondary_ll_v"], diagnostic["derivation"]) == (SECONDARY_V, pytest.approx(110.0), "auto_nominal")
    stored = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))[0]["voltage_config"]
    assert stored["secondary_voltage_ll_v"] == SECONDARY_V

    # B -- the existing manual VT correction (the real 275 kV : 1 kV, r = 275): D = 275 kV / 275 = 1.0 kV, and the report disappears.
    checked(client.put(path, json=config(path, vt_primary_v=275000.0, vt_secondary_v=SECONDARY_V)))
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert (prov["ratio_authority"], prov["ratio_applied"]) == ("manual", pytest.approx(REAL_RATIO))
    assert prov["effective_base_amount"] == pytest.approx(1.0, rel=1e-12)
    assert pu_peak(body) == pytest.approx(sample / 1.0, rel=1e-12)                                   # 0.577345
    assert prov["base_diagnostics"] == []
    # Physical equivalence with the PRIMARY recording of the same condition: 158.77 kV / 275 kV = 0.5773454... pu. (The fixture builder
    # rounds the secondary scale factor 158.77 x 1/275 to six significant figures, so the two agree to 1e-5, not to the last digit.)
    primary = recording(client, comtrade_fixtures_dir, "P")
    setup_voltage_base(client, primary, "primary", scope="group", secondary_v=SECONDARY_V)
    assert pu_peak(wave_status(client, primary, VNAMES[0])) == pytest.approx(158.77 / 275.0, rel=1e-12)
    assert pu_peak(wave_status(client, primary, VNAMES[0])) == pytest.approx(pu_peak(body), rel=1e-5)

    # The numerical gap between A and B is exactly the ratio of the two VT assumptions, 2500 / 275 = 1000 V / 110 V = 9.0909...
    assert AUTO_RATIO / REAL_RATIO == pytest.approx(1000.0 / 110.0, rel=1e-12)


def test_worked_example_stored_secondary_base_is_used_as_stored_and_the_vt_is_not_refused(client, comtrade_fixtures_dir):
    """C/D/E: D-5 activates the legacy path (Secondary declared + valid stored value); the stored 1 kV is never replaced."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    path, _ = setup_voltage_base(client, sid, "secondary", scope="group", secondary_v=SECONDARY_V)
    sample, _ = engineering_peak(client, sid)
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    # C -- Secondary samples on the Secondary base: direct, D = the STORED 1.0 kV (not the derived 0.110 kV), no ratio read.
    assert (prov["verification_state"], prov["side_conversion"], prov["ratio_applied"]) == ("verified_direct", "direct", None)
    assert prov["effective_base_amount"] == pytest.approx(1.0, rel=1e-12)
    assert pu_peak(body) == pytest.approx(sample / 1.0, rel=1e-12)
    assert len(prov["base_diagnostics"]) == 1                                                       # reported, not applied

    primary = recording(client, comtrade_fixtures_dir, "P")
    path2, _ = setup_voltage_base(client, primary, "secondary", scope="group", secondary_v=SECONDARY_V)
    sample_p, _ = engineering_peak(client, primary)
    # D -- Primary samples on the Secondary base: D = 1.0 kV x r. The auto_nominal VT is consumed as approved (r = 2500).
    prov, body = provenance(client, primary, VNAMES[0]), wave_status(client, primary, VNAMES[0])
    assert (prov["verification_state"], prov["side_conversion"], prov["ratio_authority"]) == ("verified_converted", "base_multiplied_by_ratio", "auto_nominal")
    assert prov["effective_base_amount"] == pytest.approx(1.0 * AUTO_RATIO, rel=1e-12)             # 2500 kV
    assert pu_peak(body) == pytest.approx(sample_p / (1.0 * AUTO_RATIO), rel=1e-12)                # 158.77 / 2500 = 0.063508
    # E -- the engineer's manual VT (r = 275): D = 275 kV, the physically consistent 0.5773.
    checked(client.put(path2, json=config(path2, base_reference_side="secondary", vt_primary_v=275000.0, vt_secondary_v=SECONDARY_V)))
    prov, body = provenance(client, primary, VNAMES[0]), wave_status(client, primary, VNAMES[0])
    assert prov["ratio_authority"] == "manual" and prov["effective_base_amount"] == pytest.approx(1.0 * REAL_RATIO, rel=1e-12)
    assert pu_peak(body) == pytest.approx(sample_p / REAL_RATIO, rel=1e-12)                        # 158.77 / 275 = 0.57735
    assert checked(client.get(f"{ROOT}/sources/{primary}/measurement-groups"))[0]["voltage_config"]["secondary_voltage_ll_v"] == SECONDARY_V


def test_without_a_nominal_there_is_no_vt_authority_and_the_conversion_stays_blocked(client, comtrade_fixtures_dir):
    """The approved authority derives nothing without a nominal, so a Secondary base on Primary samples is blocked (D-6)."""
    sid = recording(client, comtrade_fixtures_dir, "P")
    setup_voltage_base(client, sid, "secondary", scope="group", secondary_v=SECONDARY_V, nominal=NO_NOMINAL)
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert body["per_unit_status"] == "base_required" and prov["side_refusal_reason"] == "vt_authority_unavailable"
    assert prov["side_refusal_detail"] == "not_configured" and prov["reason"]


# ------------------------------------------------------------------------- Source Default (historical gate) side safety
# A Source Default's `voltage_base_value` is the nominal system L-L voltage. A stored `secondary` reference-side LABEL does not turn it
# into a Secondary denominator (D-5: that needs an explicit declaration AND a valid stored `secondary_voltage_ll_v`, which a Source
# Default does not have), so the historical gate can never verify a result: Recording Details' side may only ADD a block.
def source_default(client, *, flag, stored_side, value_kv):
    sid, _ = build(client, flag=flag, amplitude=value_kv * 1000.0 / 3 ** 0.5, group=False)
    checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
        "voltage_base_value": value_kv, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground",
        "voltage_base_reference_side": stored_side,
    }))
    return sid


@pytest.mark.parametrize("flag,expected_status,state,compat", [
    ("S", "configured", "unverified_historical", "compatible"),   # label-matched: the historical number, NEVER verified (denominator side unestablished)
    ("P", "base_required", "blocked", "incompatible"),            # a known mismatch with no ratio authority (ungrouped): blocked
    ("", "configured", "unverified_historical", "unverified"),    # no side established: the historical Unverified number (D-1)
])
def test_source_default_stored_secondary_keeps_its_side_safety(client, flag, expected_status, state, compat):
    sid = source_default(client, flag=flag, stored_side="secondary", value_kv=0.110)
    body, p = wave(client, sid), source_provenance(client, sid)
    assert (body["per_unit_status"], p["verification_state"], p["reference_compatibility"]) == (expected_status, state, compat)
    assert p.get("denominator_side") is None and p.get("side_conversion") is None            # no unsupported provenance
    if expected_status == "configured":
        assert pu_peak(body) == pytest.approx(1.0, rel=1e-12)                                # the historical arithmetic, unchanged


def test_source_default_stored_secondary_side_correction_only_adds_protection(client):
    """DEC-216: Recording Details' effective side may block a known mismatch; it never unblocks or verifies a Source Default result."""
    # no raw declaration, the engineer sets Secondary: the historical Unverified number, still never verified
    undeclared = source_default(client, flag="", stored_side="secondary", value_kv=0.110)
    checked(client.put(f"{ROOT}/sources/{undeclared}/measurement-side", json={"side": "secondary"}))
    p = source_provenance(client, undeclared)
    assert (p["verification_state"], p["reference_compatibility"]) == ("unverified_historical", "unverified")
    assert pu_peak(wave(client, undeclared)) == pytest.approx(1.0, rel=1e-12)
    # declared Secondary, the engineer sets Primary: a known mismatch with the Secondary label, blocked (it used to read compatible)
    declared = source_default(client, flag="S", stored_side="secondary", value_kv=0.110)
    checked(client.put(f"{ROOT}/sources/{declared}/measurement-side", json={"side": "primary"}))
    p = source_provenance(client, declared)
    assert (p["verification_state"], p["reference_compatibility"], p["status"]) == ("blocked", "incompatible", "base_required")
    assert wave(client, declared)["per_unit_status"] == "base_required"
    # declared Primary (blocked against the Secondary label), the engineer sets Secondary: it must NOT be newly allowed
    primary = source_default(client, flag="P", stored_side="secondary", value_kv=0.110)
    checked(client.put(f"{ROOT}/sources/{primary}/measurement-side", json={"side": "secondary"}))
    p = source_provenance(client, primary)
    assert (p["verification_state"], p["reference_compatibility"], p["status"]) == ("blocked", "incompatible", "base_required")
    assert wave(client, primary)["per_unit_status"] == "base_required"


def test_a_mislabelled_source_default_is_never_verified(client):
    """The 1200x case: a 132 kV (Primary-valued) base labelled Secondary, rated Secondary samples of a 132 kV / 110 V VT.

    The number is the historical arithmetic (63.5085 V / 76.2102 kV = 8.333e-4, 1200x below the physical 1.0 pu peak-referred) and must never
    carry a verified state, a denominator side or a conversion, whatever Recording Details says."""
    d_primary_lg = 132000.0 / 3 ** 0.5
    secondary_peak = d_primary_lg / (132000.0 / 110.0)
    for correction in (None, "secondary"):
        sid, _ = build(client, flag="S" if correction is None else "", amplitude=secondary_peak, group=False)
        checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
            "voltage_base_value": 132.0, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground",
            "voltage_base_reference_side": "secondary"}))
        if correction:
            checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": correction}))
        body, p = wave(client, sid), source_provenance(client, sid)
        assert pu_peak(body) == pytest.approx(secondary_peak / d_primary_lg, rel=1e-12)       # 8.333e-4
        assert p["verification_state"] == "unverified_historical"
        assert p.get("denominator_side") is None and p.get("side_conversion") is None and p.get("ratio_applied") is None


# ------------------------------------------------------------------------- the four required cases on the 132 kV / 110 V (ratio 1200) fixture
def test_cases_a_a0_b_c_denominators(client):
    """Expected values from first principles; `pu` is an instantaneous sample peak divided by the base (see the module docstring).

    One condition, two sides: a primary peak of D = 132 kV / sqrt(3) = 76,210.2 V is a secondary peak of D / 1200 = 63.5085 V. The stored
    1 kV secondary base is a PU base chosen by the engineer, never a VT: it neither vetoes the approved `auto_nominal` ratio (A) nor is replaced
    by it (B, C); a disagreement between the two is only reported (D-4, P5).
    """
    import math
    d_pri = 132000.0 / math.sqrt(3)
    ratio = 132000.0 / 110.0
    sec_peak, d_sec_stored = d_pri / ratio, 1000.0 / math.sqrt(3)
    cases = {                                    # name -> (build arguments, expected pu, expected state, ratio applied, expected base in volts)
        "A":  (dict(flag="S", amplitude=sec_peak, stored_side="primary", secondary_v=1000.0), 1.0, "verified_converted", ratio, sec_peak),
        "A0": (dict(flag="S", amplitude=sec_peak, stored_side="primary", secondary_v=None), 1.0, "verified_converted", ratio, sec_peak),
        "B":  (dict(flag="S", amplitude=sec_peak, stored_side="secondary", secondary_v=1000.0), sec_peak / d_sec_stored, "verified_direct", None, d_sec_stored),
        "C":  (dict(flag="P", amplitude=d_pri, stored_side="secondary", secondary_v=1000.0), d_pri / (d_sec_stored * ratio), "verified_converted", ratio,
               d_sec_stored * ratio),
    }
    for name, (args, pu, state, applied, base_volts) in cases.items():
        sid, _ = build(client, **args)
        body, prov = wave(client, sid), source_provenance(client, sid)
        assert pu_peak(body) == pytest.approx(pu, rel=1e-12), name
        assert prov["verification_state"] == state and prov["ratio_applied"] == applied, name
        assert prov["effective_base_amount"] * 1000.0 == pytest.approx(base_volts, rel=1e-12), name          # kV -> V
        assert ("stored_secondary_differs_from_derived" in [d["code"] for d in prov["base_diagnostics"]]) == (name != "A0"), name
        if applied is not None:
            assert prov["ratio_authority"] == "auto_nominal", name
    assert (cases["A"][1], cases["B"][1]) == (1.0, pytest.approx(0.11))
    # a VT is required but not derivable (no nominal): the Primary samples stay blocked, the raw value is returned
    sid, _ = build(client, flag="P", amplitude=d_pri, stored_side="secondary", secondary_v=1000.0, nominal=None)
    prov = source_provenance(client, sid)
    assert (wave(client, sid)["per_unit_status"], prov["verification_state"], prov["side_refusal_reason"]) == ("base_required", "blocked", "vt_authority_unavailable")
