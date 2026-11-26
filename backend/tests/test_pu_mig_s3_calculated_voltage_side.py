"""PU-MIG S3 -- calculated Voltage per-unit through the real API: the side of a calculated result is the side of its leaves.

Every case builds the S2 synthetic ASCII COMTRADE (three 50 Hz Voltage channels, peak = `amplitude` volts, the recording's own P/S
flag as given) with one confirmed Voltage Measurement Group, then creates a calculated channel over it and reads the SAME result
through every calculated seam (range, cursor values, peak values, annotation anchor) and the provenance endpoint.

Expected numbers are written from the physics, never from application code: arithmetic is done in engineering units, then
`pu = result / D`, with `D` the inherited base expressed in the unit of the samples' side (S1/S2: D = B*rho, divided by the VT ratio
for a Primary base on Secondary samples, multiplied for a Secondary base on Primary samples).

Approved policies exercised: D-1 R+ (non-strict leaves keep the historical number, labelled Unverified), D-5/D-6 (a conversion needs
an authoritative ratio, else the result is blocked), D-7/DEC-215 (the shared VT authority), DEC-052 (calculated Voltage add/subtract
produce no base), N-2 (existing reason vocabulary), S0 section 7 (the ratio belongs to the group whose base was inherited; a Source
Default base has no ratio authority).
"""

from __future__ import annotations

import math

import pytest

from tests.test_current_effective_base_inheritance import ROOT, checked, client  # noqa: F401  (client is the shared fixture)
from tests.test_pu_mig_s2_raw_voltage_side import (
    D_PRIMARY_LG,
    D_SECONDARY_LG,
    NOMINAL_KV,
    RATIO,
    SQRT3,
    build,
)

CALC = f"{ROOT}/calculated-channels"


def make(client, sid, operation, channel="VA", parameters=None, name=None):
    body = {"name": name or f"{operation} {channel}", "operation": operation,
            "inputs": [{"kind": "source", "source_id": sid, "channel_name": channel}]}
    if parameters is not None:
        body["parameters"] = parameters
    return checked(client.post(CALC, json=body), 201)["id"]


def make_over(client, operation, calc_id, parameters=None):
    body = {"name": f"{operation} of calc", "operation": operation,
            "inputs": [{"kind": "calculated", "calculated_channel_id": calc_id}]}
    if parameters is not None:
        body["parameters"] = parameters
    return checked(client.post(CALC, json=body), 201)["id"]


def cwave(client, cid, mode="per_unit"):
    return checked(client.get(f"{CALC}/{cid}/waveform", params={"unit_mode": mode}))


def cprov(client, cid):
    return checked(client.get(f"{CALC}/{cid}/per-unit-resolution"))


def cpeak(body):
    return max(abs(v) for v in body["values"])


def engineering(client, cid):
    return cwave(client, cid, "engineering")["values"]


def source_values(client, sid, name="VA"):
    return checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={"channel_name": name, "unit_mode": "engineering"}))["values"]


def cseams(client, cid):
    """The calculated seams plus provenance: every one must agree on the number and the verification."""
    body = cwave(client, cid)
    cursor = checked(client.post(CALC + "/cursor-values", json={
        "calculated_channel_ids": [cid], "cursor_a_time": 0.005, "cursor_b_time": 0.015, "unit_mode": "per_unit"}))
    peaks = checked(client.post(CALC + "/peak-values", json={
        "start_time": 0, "end_time": 0.099, "unit_mode": "per_unit",
        "requests": [{"calculated_channel_id": cid, "mode": "max"}, {"calculated_channel_id": cid, "mode": "min"}]}))
    anchor = checked(client.post(f"{CALC}/{cid}/annotation-anchor", json={
        "approximate_elapsed_seconds": 0.005, "unit_mode": "per_unit"}))
    return body, cursor, peaks, anchor, cprov(client, cid)


UNARY = [
    ("reverse_polarity", None, lambda x: -x),
    ("absolute_value", None, abs),
    ("multiply_constant", {"constant": 0.5}, lambda x: 0.5 * x),
]


# ------------------------------------------------------------------------------------ same side, Primary (verified_direct)
@pytest.mark.parametrize("operation,parameters,physics", UNARY)
def test_unary_result_on_primary_samples_is_the_engineering_arithmetic_over_the_primary_base(client, operation, parameters, physics):
    sid, _ = build(client, flag="P", stored_side="primary")
    cid = make(client, sid, operation, parameters=parameters)
    raw = source_values(client, sid)
    eng = engineering(client, cid)
    assert eng == pytest.approx([physics(v) for v in raw], rel=1e-12, abs=1e-9)      # arithmetic in ENG, before normalisation
    denominator = NOMINAL_KV * 1000.0 / SQRT3                                        # exactly (kV x 1000) / sqrt(3), L-G
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "configured" and body["unit"] == "pu"
    assert body["values"] == [v / denominator for v in eng]
    assert (p["verification_state"], p["side_conversion"], p["ratio_applied"]) == ("verified_direct", "direct", None)
    assert p["measurement_side"] == "primary" and p["base_reference_side"] == "primary" and p["denominator_side"] == "primary"
    assert p["effective_base_amount"] == pytest.approx(denominator / 1000.0, rel=1e-15)


def test_rms_of_a_grouped_voltage_inherits_the_side_too(client):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    cid = make(client, sid, "rms", parameters={"nominal_frequency_hz": 50.0})
    eng, body, p = engineering(client, cid), cwave(client, cid), cprov(client, cid)
    assert [v for v in body["values"] if v is not None] == pytest.approx([v / D_SECONDARY_LG for v in eng if v is not None], rel=1e-12)
    assert p["verification_state"] == "verified_converted" and p["denominator_side"] == "secondary"
    assert eng[-1] == pytest.approx(D_SECONDARY_LG / math.sqrt(2.0), rel=5e-2)        # physics: the RMS of a sine of that peak


# ---------------------------------------------------------------------- Primary base on Secondary samples (verified_converted)
@pytest.mark.parametrize("vt,authority", [((132000.0, 110.0), "manual"), (None, "auto_nominal")])
@pytest.mark.parametrize("operation,parameters,physics", UNARY)
def test_primary_base_on_secondary_samples_is_converted_by_the_groups_vt(client, operation, parameters, physics, vt, authority):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=vt)
    cid = make(client, sid, operation, parameters=parameters)
    raw = source_values(client, sid)
    eng = engineering(client, cid)
    assert eng == pytest.approx([physics(v) for v in raw], rel=1e-12, abs=1e-9)
    body, cursor, peaks, anchor, p = cseams(client, cid)
    assert body["per_unit_status"] == "configured" and body["per_unit_reference_compatibility"] == "compatible"
    assert body["values"] == pytest.approx([v / D_SECONDARY_LG for v in eng], rel=1e-12, abs=1e-15)
    assert cpeak(body) == pytest.approx(abs(physics(1.0)), rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == (
        "verified_converted", "base_divided_by_ratio", "secondary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["ratio_authority"] == authority
    assert p["effective_base_amount"] == pytest.approx(D_SECONDARY_LG / 1000.0, rel=1e-12)
    assert p["measurement_side"] == "secondary" and p["base_reference_side"] == "primary"
    # every calculated seam answers with the same compatible, converted result
    assert cursor["channels"][0]["per_unit_reference_compatibility"] == "compatible"
    assert anchor["per_unit_reference_compatibility"] == "compatible"
    assert max(r["value"] for r in peaks["results"] if r["mode"] == "max") == pytest.approx(
        max(v / D_SECONDARY_LG for v in eng), rel=1e-12)
    assert all(r["per_unit_reference_compatibility"] == "compatible" for r in peaks["results"])


def test_primary_and_secondary_recordings_of_one_physical_condition_give_the_same_calculated_pu(client):
    primary, _ = build(client, flag="P", amplitude=0.8 * D_PRIMARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    secondary, _ = build(client, flag="S", amplitude=0.8 * D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    a = cwave(client, make(client, primary, "reverse_polarity", name="primary recording"))["values"]
    b = cwave(client, make(client, secondary, "reverse_polarity", name="secondary recording"))["values"]
    assert cpeak({"values": a}) == pytest.approx(0.8, rel=1e-12)
    assert a == pytest.approx(b, rel=1e-12, abs=1e-12)


def test_a_chain_of_calculated_channels_takes_the_side_of_the_transitive_leaf(client):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    first = make(client, sid, "reverse_polarity")
    second = make_over(client, "multiply_constant", first, {"constant": 0.5})
    third = make_over(client, "absolute_value", second)
    body, p = cwave(client, third), cprov(client, third)
    assert cpeak(body) == pytest.approx(0.5, rel=1e-12)
    assert body["values"] == pytest.approx([abs(-0.5 * v) / D_SECONDARY_LG for v in source_values(client, sid)], rel=1e-12, abs=1e-15)
    assert (p["verification_state"], p["denominator_side"], p["ratio_authority"]) == ("verified_converted", "secondary", "manual")


# ---------------------------------------------------------------------- Secondary base on Primary samples (D-5, D-6)
def test_secondary_base_on_primary_samples_converts_with_an_authoritative_vt(client):
    sid, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, stored_side="secondary", secondary_v=110.0, vt=(132000.0, 110.0))
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert cpeak(body) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == (
        "verified_converted", "base_multiplied_by_ratio", "primary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["ratio_authority"] == "manual"


def test_secondary_base_on_primary_samples_is_blocked_without_an_authoritative_ratio(client):
    """D-6: a required conversion without a ratio authority is no number; the engineering values are untouched."""
    sid, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, stored_side="secondary", secondary_v=110.0, nominal=None)
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "V"
    assert body["values"] == engineering(client, cid)
    assert body["per_unit_reference_compatibility"] == "incompatible"
    assert p["verification_state"] == "blocked" and p["status"] == "base_required"
    assert p["side_refusal_reason"] == "vt_authority_unavailable" and p["side_refusal_detail"] == "not_configured"


# ---------------------------------------------------------------------------------------- historical, Unverified (D-1 R+)
def test_a_leaf_without_a_declared_side_keeps_the_historical_number_labelled_unverified(client):
    sid, _ = build(client, flag="", amplitude=D_PRIMARY_LG, stored_side="primary")
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "configured" and body["unit"] == "pu"
    assert body["values"] == [v / (NOMINAL_KV * 1000.0 / SQRT3) for v in engineering(client, cid)]   # the historical arithmetic
    assert p["verification_state"] == "unverified_historical" and p["ratio_applied"] is None
    # an engineer's Recording Details correction promotes it to a verified result with the SAME number
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "primary"}))
    assert cprov(client, cid)["verification_state"] == "verified_direct"
    assert cwave(client, cid)["values"] == body["values"]


def test_a_secondary_correction_changes_the_calculated_pu_through_recording_details(client):
    sid, _ = build(client, flag="", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    cid = make(client, sid, "reverse_polarity")
    assert cprov(client, cid)["verification_state"] == "unverified_historical"
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    p = cprov(client, cid)
    assert (p["verification_state"], p["measurement_side"], p["side_authority"]) == (
        "verified_converted", "secondary", "engineer_recording_correction")
    assert cpeak(cwave(client, cid)) == pytest.approx(1.0, rel=1e-12)


# ------------------------------------------------------------------------------------------- DEC-052: no multi-input base
@pytest.mark.parametrize("operation", ["addition", "subtraction"])
def test_voltage_add_and_subtract_still_produce_no_base_whatever_the_side(client, operation):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    body = {"name": f"{operation} VA VB", "operation": operation, "inputs": [
        {"kind": "source", "source_id": sid, "channel_name": "VA"}, {"kind": "source", "source_id": sid, "channel_name": "VB"}]}
    cid = checked(client.post(CALC, json=body), 201)["id"]
    out, p = cwave(client, cid), cprov(client, cid)
    assert out["per_unit_status"] == "base_required" and out["unit"] == "V"
    assert out["values"] == engineering(client, cid)
    assert p["status"] == "base_required" and p["verification_state"] != "verified_converted"


# ------------------------------------------------------------------------------- Source Default (no group, no ratio authority)
def source_default(client, sid, side, kv=NOMINAL_KV):
    checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
        "voltage_base_value": kv, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground",
        "voltage_base_reference_side": side}))


def test_source_default_primary_base_on_primary_samples_is_verified_direct(client):
    sid, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, group=False)
    source_default(client, sid, "primary")
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "configured" and cpeak(body) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["source_kind"]) == ("verified_direct", "source_default")


def test_source_default_primary_base_on_secondary_samples_is_blocked_for_want_of_a_ratio_authority(client):
    """S0 section 7: a Source Default base has no Measurement Group, hence no VT authority -- never a guessed ratio."""
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, group=False)
    source_default(client, sid, "primary")
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "V"
    assert body["values"] == engineering(client, cid)
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "vt_authority_unavailable"
    assert p["side_refusal_detail"] == "no_group"


# ------------------------------------------------------------------ line-to-line outputs (multi-input, DEC-115/116, KPDN1 context)
WSID = ROOT.split("/workspaces/")[1]


def ll_source(client, comtrade_fixtures_dir, side, vt=None):
    """The multibay recording with its KPDN1 Measurement Group (275 kV L-L), the recording's side set in Recording Details."""
    import io
    from app.domain.calculated_channel import ChannelRef
    from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL
    from app.services.measurement_group_service import create_group
    from app.services.voltage_group_config_service import set_voltage_base

    stem = "line_to_line_multibay"
    sid = checked(client.post(ROOT + "/sources", files={
        "cfg_file": (f"{stem}.cfg", io.BytesIO((comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO((comtrade_fixtures_dir / f"{stem}.dat").read_bytes()), "application/octet-stream"),
    }), 201)["source_id"]
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    for existing in client.get(url).json():
        client.delete(url + "/" + existing["id"])
    group = create_group(
        workspace_id=WSID, source_id=sid, kind=KIND_VOLTAGE, display_name="KPDN1 275 kV",
        channel_refs=[ChannelRef(kind="source", source_id=sid, channel_name=n) for n in ("KPDN1_VR", "KPDN1_VY", "KPDN1_VB")],
        status=STATUS_MANUAL, registry=client.app.state.measurement_group_registry, source_registry=client.app.state.workspace_registry)
    set_voltage_base(
        workspace_id=WSID, measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
        group_registry=client.app.state.measurement_group_registry, voltage_config_registry=client.app.state.voltage_group_config_registry)
    if vt is not None:
        from app.services.voltage_group_config_service import update_voltage_configuration
        update_voltage_configuration(
            workspace_id=WSID, measurement_group_id=group.id, vt_primary_v=vt[0], vt_secondary_v=vt[1],
            group_registry=client.app.state.measurement_group_registry,
            voltage_config_registry=client.app.state.voltage_group_config_registry)
    if side is not None:
        checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": side}))
    return sid


def ll_channels(client, output="all_three"):
    ctx = next(c["id"] for c in client.get(f"{ROOT}/engineering-contexts").json() if c["display_name"] == "KPDN1")
    return checked(client.post(f"{CALC}/line-to-line-voltage", json={"engineering_context_id": ctx, "output": output}), 201)["channels"]


def test_line_to_line_outputs_on_primary_samples_use_the_ll_denominator_and_match_the_phase_differences(client, comtrade_fixtures_dir):
    sid = ll_source(client, comtrade_fixtures_dir, "primary")
    channels = ll_channels(client)
    assert len(channels) == 3
    vr, vy, vb = (source_values(client, sid, f"KPDN1_V{c}") for c in "RYB")
    differences = [[a - b for a, b in zip(x, y)] for x, y in ((vr, vy), (vy, vb), (vb, vr))]        # independent: V_AB = V_A - V_B
    for ch in channels:
        body, p = cwave(client, ch["id"]), cprov(client, ch["id"])
        assert any(body["values"] == pytest.approx([d / 275.0 for d in diff], rel=1e-6, abs=1e-9) for diff in differences), ch["name"]
        assert (p["verification_state"], p["side_conversion"], p["nominal_reference"]) == ("verified_direct", "direct", "line_to_line")
        assert p["effective_base_amount"] == pytest.approx(275.0) and p["denominator_side"] == "primary"   # L-L base, never 275/sqrt(3)


def test_line_to_line_outputs_on_secondary_samples_convert_the_primary_base_with_the_groups_vt(client, comtrade_fixtures_dir):
    sid = ll_source(client, comtrade_fixtures_dir, "secondary", vt=(275000.0, 110.0))
    for ch in ll_channels(client):
        body, p = cwave(client, ch["id"]), cprov(client, ch["id"])
        eng = engineering(client, ch["id"])
        # the recording's own unit is kV; the L-L secondary denominator is 275 kV x (110 V / 275000 V) = 0.110 kV
        assert body["values"] == pytest.approx([v / 0.110 for v in eng], rel=1e-9)
        assert (p["verification_state"], p["side_conversion"], p["ratio_authority"]) == ("verified_converted", "base_divided_by_ratio", "manual")
        assert p["ratio_applied"] == pytest.approx(2500.0, rel=1e-12) and p["denominator_side"] == "secondary"
        assert p["effective_base_amount"] == pytest.approx(0.110, rel=1e-9) and p["nominal_reference"] == "line_to_line"


def test_line_to_line_outputs_take_the_recordings_own_declared_side_without_an_engineer_correction(client, comtrade_fixtures_dir):
    """The multibay recording's channels declare Primary themselves: no Recording Details correction is needed to verify."""
    ll_source(client, comtrade_fixtures_dir, None)
    for ch in ll_channels(client):
        body, p = cwave(client, ch["id"]), cprov(client, ch["id"])
        assert (p["status"], p["verification_state"], p["side_authority"]) == ("configured", "verified_direct", "recording_channel_declared")
        assert body["values"] == pytest.approx([v / 275.0 for v in engineering(client, ch["id"])], rel=1e-12)


# ----------------------------------------------------------------------------------------------- representability and safety
def test_a_calculated_conversion_that_overflows_is_refused_with_the_existing_reason_and_no_number(client):
    sid, _ = build(client, flag="S", amplitude=1.0, stored_side="primary", nominal=1.0e300, vt=(1.0e-100, 1.0e100))
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["values"] == engineering(client, cid)
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "denominator_not_representable"


def test_a_calculated_result_whose_pu_is_not_representable_stays_blocked_and_its_engineering_values_survive(client):
    sid, _ = build(client, flag="P", amplitude=1.0e300, stored_side="primary", nominal=1.0e-20)
    cid = make(client, sid, "multiply_constant", parameters={"constant": 10.0})
    body = cwave(client, cid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "V"
    assert body["values"] == engineering(client, cid)
    assert cprov(client, cid)["reason"]


def test_a_subnormal_calculated_denominator_is_valid(client):
    sid, _ = build(client, flag="P", amplitude=1.0e-320, stored_side="primary", nominal=1.0e-320)
    cid = make(client, sid, "absolute_value")
    p = cprov(client, cid)
    assert p["status"] == "configured" and p["verification_state"] == "verified_direct"


def test_the_engineering_samples_of_the_leaf_are_never_changed_by_the_side_resolution(client):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    before = source_values(client, sid)
    cid = make(client, sid, "reverse_polarity")
    cwave(client, cid)
    cprov(client, cid)
    assert source_values(client, sid) == before
    assert engineering(client, cid) == pytest.approx([-v for v in before], rel=0, abs=0)


# ------------------------------------------------------------- strict leaves on different sides: refused (the lineage rule)
def test_strict_leaves_on_different_sides_are_refused_by_the_shared_calculated_gate(client):
    """Two recordings of opposite sides combined into one line-to-line result. No public operation can combine them with a base (DEC-052
    blocks generic add/subtract first), so the gate is exercised on the multi-input line-to-line shape directly: the result is refused,
    never converted with either leaf's side, and no ratio is read."""
    import dataclasses

    from app.services import calculated_channel_service as svc
    from app.services.recorded_side_authority import RecordedAuthority

    primary, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, stored_side="primary", group=False)
    secondary, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", group=False)
    source_default(client, primary, "primary")
    source_default(client, secondary, "primary")
    body = {"name": "mixed", "operation": "subtraction", "inputs": [
        {"kind": "source", "source_id": primary, "channel_name": "VA"}, {"kind": "source", "source_id": secondary, "channel_name": "VB"}]}
    created = client.post(CALC, json=body)
    assert created.status_code == 201, created.text
    s = client.app.state
    registry = s.calculated_channel_registry
    channel = dataclasses.replace(registry.get(WSID, created.json()["id"]), voltage_representation="line_to_line")
    profile = s.per_unit_registry.get(WSID, primary)

    def resolve(authority):
        return svc._resolve_effective_per_unit_for_calculated_channel(
            channel, profile, None, workspace_id=WSID, calc_registry=registry, group_registry=s.measurement_group_registry,
            voltage_config_registry=s.voltage_group_config_registry, current_config_registry=s.current_group_config_registry,
            source_registry=s.workspace_registry, per_unit_registry=s.per_unit_registry, side_authority=authority)

    refused = resolve(RecordedAuthority.from_app_state(s))
    assert refused.status == "base_required" and refused.base_amount is None
    assert refused.side_provenance.verification_state == "blocked"
    assert refused.side_provenance.refusal_reason == "voltage_mixed_side"
    # without the authority the historical gate is exactly what it was: no refusal, no side provenance
    assert resolve(None).side_provenance is None


def test_leaves_in_two_groups_fall_back_to_the_source_default_and_never_borrow_either_groups_vt(client):
    """A multi-input line-to-line result over leaves of two different Measurement Groups has no single inherited group, so its base is
    the Source Default one, and a Source Default base has no ratio authority (S0 section 7) -- although BOTH groups carry a manual VT."""
    import dataclasses

    from app.services import calculated_channel_service as svc
    from app.services.recorded_side_authority import RecordedAuthority

    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, group=False)
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    for members in (["VA"], ["VB", "VC"]):
        gid = checked(client.post(url, json={"kind": "voltage", "display_name": "+".join(members), "status": "confirmed", "channel_refs": [
            {"kind": "source", "source_id": sid, "channel_name": n} for n in members]}), 201)["id"]
        checked(client.put(f"{url}/{gid}/voltage-config", json={
            "reference_mode": "manual", "reference_override": "line_to_ground", "base_reference_side": "primary",
            "nominal_voltage_ll_kv": NOMINAL_KV, "vt_primary_v": 132000.0, "vt_secondary_v": 110.0}))
    source_default(client, sid, "primary")
    created = checked(client.post(CALC, json={"name": "cross group", "operation": "subtraction", "inputs": [
        {"kind": "source", "source_id": sid, "channel_name": "VA"}, {"kind": "source", "source_id": sid, "channel_name": "VB"}]}), 201)
    s = client.app.state
    channel = dataclasses.replace(s.calculated_channel_registry.get(WSID, created["id"]), voltage_representation="line_to_line")
    resolved = svc._resolve_effective_per_unit_for_calculated_channel(
        channel, s.per_unit_registry.get(WSID, sid), None, workspace_id=WSID, calc_registry=s.calculated_channel_registry,
        group_registry=s.measurement_group_registry, voltage_config_registry=s.voltage_group_config_registry,
        current_config_registry=s.current_group_config_registry, source_registry=s.workspace_registry,
        per_unit_registry=s.per_unit_registry, side_authority=RecordedAuthority.from_app_state(s))
    assert resolved.status == "base_required" and resolved.base_amount is None
    side = resolved.side_provenance
    assert (side.verification_state, side.refusal_reason, side.refusal_detail) == ("blocked", "vt_authority_unavailable", "no_group")
