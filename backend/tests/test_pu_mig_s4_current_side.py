"""PU-MIG S4 -- Current per-unit through the real API: Recording Details' side and the CT decide the per-unit denominator.

Every case builds a synthetic ASCII COMTRADE (three 50 Hz Current channels IA/IB/IC whose peak is `amplitude`, the recording's own P/S
flag as given), one confirmed Current Measurement Group and the configuration under test, then reads the SAME channel through the source
seams (range, cursor values, peak values, annotation anchor), the provenance and coverage endpoints, and calculated channels over it.
Expected numbers are written from the physics, never from application code: `pu = sample / D` with `D` the Ibase expressed in the unit of
the SAMPLES' side -- `B` on the same side, `B / r` for a Primary base on Secondary samples, `B * r` for a Secondary base on Primary
samples, `r = CT primary / CT secondary` (here 1200 A : 5 A = 240).

Approved policies exercised: D-1 R+ (undeclared / non-strict keep the historical numbers, labelled), D-2 (stored base side metadata kept),
D-5/D-6 (a conversion needs an authoritative ratio, else the established refusal), DEC-209/210 (K-1 equal sides, K-2 Secondary across
distinct CT authorities stays unavailable, K-3 denominators compared), DEC-212 (no change of Current PU eligibility), N-2 (existing reason
vocabulary), S0 section 7/8 (Source Default has no ratio authority; Stage 5B result bases keep their declared side).
"""

from __future__ import annotations

import io
import math

import pytest

from tests.test_current_effective_base_inheritance import ROOT, checked, client  # noqa: F401  (client is the shared fixture)

SAMPLES = 100
NAMES = ["IA", "IB", "IC"]
IBASE_A = 1200.0                       # the group's Ibase, amperes
CT_PRIMARY, CT_SECONDARY = 1200.0, 5.0
RATIO = CT_PRIMARY / CT_SECONDARY      # 240
CALC = f"{ROOT}/calculated-channels"


def comtrade(flags, amplitude, unit="A", names=NAMES):
    cfg = [
        "S4_STATION,S4_DEVICE,1999", f"{len(names)},{len(names)}A,0D",
        *[f"{i + 1},{n},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,{flags[i] if isinstance(flags, (list, tuple)) else flags}"
          for i, n in enumerate(names)],
        "50", "1", f"1000.0,{SAMPLES}", "01/01/2026,00:00:00.000000", "01/01/2026,00:00:00.000000", "ASCII", "1.0",
    ]
    rows = []
    for n in range(SAMPLES):
        v = amplitude * math.sin(2.0 * math.pi * 50.0 * n / 1000.0)
        rows.append(f"{n + 1}," + f"{n * 1000.0}," + ",".join(repr(v) for _ in names))
    return ("\r\n".join(cfg) + "\r\n").encode(), ("\r\n".join(rows) + "\r\n").encode()


def upload(client, flags, amplitude, unit="A"):
    cfg, dat = comtrade(flags, amplitude, unit)
    return checked(client.post(ROOT + "/sources", files={
        "cfg_file": ("s4.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("s4.dat", io.BytesIO(dat), "application/octet-stream"),
    }), 201)["source_id"]


def clear_groups(client, sid):
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    for existing in checked(client.get(url)):
        assert client.delete(url + "/" + existing["id"]).status_code == 204
    return url


def current_group(client, sid, members, *, name="HV", ibase_ka=IBASE_A / 1000.0, side="primary", ct=(CT_PRIMARY, CT_SECONDARY),
                  method="manual", status="confirmed", mva=None, kv=None):
    """One Current group over `members`, its base and (optionally) its CT, all through the public API."""
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    gid = checked(client.post(url, json={
        "kind": "current", "display_name": name, "status": status,
        "channel_refs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in members]}), 201)["id"]
    body = {"method": method, "base_reference_side": side}
    if method == "manual":
        body["manual_ibase_ka"] = ibase_ka
    elif method == "equipment_rating":
        body["equipment_rating_mva"], body["manual_voltage_base_kv"], body["base_reference_side"] = mva, kv, "primary"
    if ct is not None:
        body["ct_primary_a"], body["ct_secondary_a"] = ct
    checked(client.put(f"{url}/{gid}/current-config", json=body))
    return gid


def build(client, *, flags="P", amplitude=IBASE_A, side="primary", ct=(CT_PRIMARY, CT_SECONDARY), method="manual", group=True,
          unit="A", **kw):
    sid = upload(client, flags, amplitude, unit)
    clear_groups(client, sid)
    gid = current_group(client, sid, NAMES, side=side, ct=ct, method=method, **kw) if group else None
    return sid, gid


def wave(client, sid, name="IA", mode="per_unit"):
    return checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={"channel_name": name, "unit_mode": mode}))


def provenance(client, sid, name="IA"):
    return checked(client.get(f"{ROOT}/sources/{sid}/per-unit-resolution", params={"channel_name": name}))


def peak(values):
    return max(abs(v) for v in values if v is not None)


def seams(client, sid, name="IA"):
    path = f"{ROOT}/sources/{sid}"
    body = wave(client, sid, name)
    cursor = checked(client.post(path + "/cursor-values", json={
        "analog_channel_names": [name], "cursor_a_time": 0.005, "cursor_b_time": 0.015, "unit_mode": "per_unit"}))["channels"][0]
    anchor = checked(client.post(path + "/annotation-anchor", json={
        "channel_name": name, "approximate_elapsed_seconds": 0.005, "unit_mode": "per_unit"}))
    peaks = checked(client.post(path + "/peak-values", json={
        "start_time": 0, "end_time": 0.099, "unit_mode": "per_unit",
        "requests": [{"channel_name": name, "mode": "max"}, {"channel_name": name, "mode": "min"}]}))["results"]
    return body, cursor, anchor, peaks, provenance(client, sid, name)


def calc(client, sid, operation, members=("IA",), parameters=None, name=None):
    body = {"name": name or f"{operation} {'+'.join(members)}", "operation": operation,
            "inputs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in members]}
    if parameters is not None:
        body["parameters"] = parameters
    return checked(client.post(CALC, json=body), 201)["id"]


def cwave(client, cid, mode="per_unit"):
    return checked(client.get(f"{CALC}/{cid}/waveform", params={"unit_mode": mode}))


def cprov(client, cid):
    return checked(client.get(f"{CALC}/{cid}/per-unit-resolution"))


# ------------------------------------------------------------------------------------------------ raw Current: same side
@pytest.mark.parametrize("method,kwargs,base_a", [
    ("manual", {}, IBASE_A),
    ("equipment_rating", {"mva": 100.0, "kv": 132.0}, 100.0 / (math.sqrt(3.0) * 132.0) * 1000.0),
])
def test_same_side_primary_is_bit_identical_to_the_historical_arithmetic(client, method, kwargs, base_a):
    sid, _ = build(client, flags="P", amplitude=base_a, method=method, **kwargs)
    body, p = wave(client, sid), provenance(client, sid)
    raw = wave(client, sid, mode="engineering")["values"]
    assert body["per_unit_status"] == "configured" and body["unit"] == "pu"
    assert body["values"] == [v / base_a for v in raw]
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["ratio_applied"]) == ("verified_direct", "direct", None)
    assert p["measurement_side"] == "primary" and p["base_reference_side"] == "primary" and p["denominator_side"] == "primary"
    assert p["effective_base_amount"] == pytest.approx(base_a / 1000.0, rel=1e-12)


def test_same_side_secondary_manual_base_needs_no_ct(client):
    sid, _ = build(client, flags="S", amplitude=5.0, side="secondary", ibase_ka=0.005, ct=None)
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["ratio_applied"]) == ("verified_direct", "direct", None)
    assert p["measurement_side"] == "secondary" and p["base_reference_side"] == "secondary"


# ------------------------------------------------------------------------- Primary base, Secondary samples (B / r)
@pytest.mark.parametrize("method,kwargs,base_a", [
    ("manual", {}, IBASE_A),
    ("equipment_rating", {"mva": 100.0, "kv": 132.0}, 100.0 / (math.sqrt(3.0) * 132.0) * 1000.0),
])
def test_primary_base_on_secondary_samples_is_converted_by_the_groups_ct(client, method, kwargs, base_a):
    d = base_a / RATIO                                                  # 1 pu in secondary amperes
    sid, _ = build(client, flags="S", amplitude=d, method=method, **kwargs)
    body, cursor, anchor, peaks, p = seams(client, sid)
    raw = wave(client, sid, mode="engineering")["values"]
    assert body["per_unit_status"] == "configured" and body["per_unit_reference_compatibility"] == "compatible"
    assert body["values"] == pytest.approx([v / d for v in raw], rel=1e-12, abs=1e-15)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == ("verified_converted", "base_divided_by_ratio", "secondary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["ratio_authority"] == "manual"
    assert p["effective_base_amount"] == pytest.approx(d / 1000.0, rel=1e-12)
    assert p["measurement_side"] == "secondary" and p["base_reference_side"] == "primary"
    assert cursor["per_unit_reference_compatibility"] == "compatible" and anchor["per_unit_reference_compatibility"] == "compatible"
    assert max(r["value"] for r in peaks if r["mode"] == "max") == pytest.approx(1.0, rel=1e-12)
    assert all(r["per_unit_reference_compatibility"] == "compatible" for r in peaks)


def test_primary_and_secondary_recordings_of_one_physical_condition_give_the_same_pu(client):
    primary, _ = build(client, flags="P", amplitude=0.8 * IBASE_A)
    secondary, _ = build(client, flags="S", amplitude=0.8 * IBASE_A / RATIO)
    a, b = wave(client, primary)["values"], wave(client, secondary)["values"]
    assert peak(a) == pytest.approx(0.8, rel=1e-12)
    assert a == pytest.approx(b, rel=1e-12, abs=1e-12)


# ------------------------------------------------------------------------- Secondary base, Primary samples (B * r)
def test_secondary_base_on_primary_samples_converts_with_an_authoritative_ct(client):
    sid, _ = build(client, flags="P", amplitude=5.0 * RATIO, side="secondary", ibase_ka=0.005)
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == (
        "verified_converted", "base_multiplied_by_ratio", "primary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["effective_base_amount"] == pytest.approx(5.0 * RATIO / 1000.0, rel=1e-12)


# --------------------------------------------------------------------------------------- missing CT: the established refusal
@pytest.mark.parametrize("flags,side,ibase_ka,amplitude", [("S", "primary", 1.2, 5.0), ("P", "secondary", 0.005, 1200.0)])
def test_a_conversion_without_an_authoritative_ct_is_the_established_refusal_with_no_number(client, flags, side, ibase_ka, amplitude):
    sid, _ = build(client, flags=flags, amplitude=amplitude, side=side, ibase_ka=ibase_ka, ct=None)
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "A"
    assert body["values"] == wave(client, sid, mode="engineering")["values"]
    assert body["per_unit_reference_compatibility"] == "incompatible"
    assert p["status"] == "base_required" and p["verification_state"] == "blocked"
    assert p["side_refusal_reason"] == "ct_authority_unavailable" and p["side_refusal_detail"] == "not_configured"
    assert p["reason"]


# ------------------------------------------------------------------------------------------ D-1: historical, Unverified
def test_a_manual_base_with_no_declared_side_keeps_the_historical_number_and_is_never_assumed_primary(client):
    sid, _ = build(client, flags="P", amplitude=IBASE_A, side="unknown")
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "configured"
    assert body["values"] == [v / IBASE_A for v in wave(client, sid, mode="engineering")["values"]]      # the historical number
    assert p["verification_state"] == "unverified_historical" and p["ratio_applied"] is None
    assert body["per_unit_reference_compatibility"] == "unverified"


def test_a_sample_with_no_declared_side_keeps_the_historical_number_labelled_unverified(client):
    sid, _ = build(client, flags="", amplitude=IBASE_A)
    body, p = wave(client, sid), provenance(client, sid)
    assert body["values"] == [v / IBASE_A for v in wave(client, sid, mode="engineering")["values"]]
    assert p["verification_state"] == "unverified_historical" and p["measurement_side"] == "unknown"


def test_an_engineers_recording_side_correction_promotes_it_with_the_same_or_converted_number(client):
    sid, _ = build(client, flags="", amplitude=IBASE_A / RATIO)
    assert provenance(client, sid)["verification_state"] == "unverified_historical"
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    p, body = provenance(client, sid), wave(client, sid)
    assert (p["verification_state"], p["measurement_side"], p["side_authority"]) == (
        "verified_converted", "secondary", "engineer_recording_correction")
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)


def test_a_known_primary_secondary_mismatch_is_never_bypassed_by_an_unverified_label(client):
    """A stored Secondary base against a declared-Primary sample with a CT converts; without one it stays refused (never Unverified)."""
    sid, _ = build(client, flags="P", amplitude=1.0, side="secondary", ibase_ka=0.005, ct=None)
    assert provenance(client, sid)["verification_state"] == "blocked"
    assert wave(client, sid)["per_unit_status"] == "base_required"


# --------------------------------------------------------------------------------- Source Default (no group, no CT authority)
def source_default(client, sid, side, ka=IBASE_A / 1000.0):
    checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
        "current_base_mode": "direct", "direct_current_base_value": ka, "current_base_reference_side": side}))


def test_source_default_primary_base_on_primary_samples_is_verified_direct(client):
    sid, _ = build(client, flags="P", amplitude=IBASE_A, group=False)
    source_default(client, sid, "primary")
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["source_kind"]) == ("verified_direct", "source_default")


def test_source_default_has_no_ct_authority_so_a_secondary_sample_is_refused(client):
    sid, _ = build(client, flags="S", amplitude=IBASE_A / RATIO, group=False)
    source_default(client, sid, "primary")
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and body["values"] == wave(client, sid, mode="engineering")["values"]
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "ct_authority_unavailable" and p["side_refusal_detail"] == "no_group"


# ------------------------------------------------------------- eligibility, representability and safety (DEC-212 unchanged)
def test_the_measured_unit_still_scales_into_the_denominators_unit(client):
    """Samples in kA: the existing eligibility scales the base's unit; the converted denominator is in amperes like any other."""
    sid, _ = build(client, flags="S", amplitude=IBASE_A / RATIO / 1000.0, unit="kA")
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "configured" and peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert p["verification_state"] == "verified_converted"


def test_a_conversion_that_overflows_is_refused_with_the_existing_reason_and_no_number(client):
    sid, _ = build(client, flags="S", amplitude=1.0, ibase_ka=1.0e300, ct=(1.0e-100, 1.0e100))
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and body["values"] == wave(client, sid, mode="engineering")["values"]
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "denominator_not_representable"


def test_a_non_representable_pu_result_stays_blocked_after_the_resolver(client):
    sid, _ = build(client, flags="P", amplitude=1.0e300, ibase_ka=1.0e-23)
    body = wave(client, sid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "A"


def test_the_leafs_authoritative_samples_are_never_changed_by_side_resolution(client):
    sid, _ = build(client, flags="S", amplitude=IBASE_A / RATIO)
    before = wave(client, sid, mode="engineering")["values"]
    wave(client, sid)
    provenance(client, sid)
    assert wave(client, sid, mode="engineering")["values"] == before


# ----------------------------------------------------------------------------------------------- coverage agrees with display
def test_coverage_counts_agree_with_the_display(client):
    converted, _ = build(client, flags="S", amplitude=IBASE_A / RATIO)
    historical, _ = build(client, flags="", amplitude=IBASE_A)
    c1 = checked(client.get(f"{ROOT}/per-unit/sources/{converted}/coverage"))
    c2 = checked(client.get(f"{ROOT}/per-unit/sources/{historical}/coverage"))
    assert (c1["applicable_channel_count"], c1["needs_configuration_count"], c1["unverified_reference_count"]) == (3, 0, 0)
    assert (c2["applicable_channel_count"], c2["unverified_reference_count"]) == (3, 3)


# ===================================================================================================== calculated Current
UNARY = [
    ("reverse_polarity", None, lambda x: -x),
    ("absolute_value", None, abs),
    ("multiply_constant", {"constant": 0.5}, lambda x: 0.5 * x),
]


@pytest.mark.parametrize("operation,parameters,physics", UNARY)
def test_unary_calculated_current_on_secondary_samples_is_converted_eng_first(client, operation, parameters, physics):
    d = IBASE_A / RATIO
    sid, _ = build(client, flags="S", amplitude=d)
    cid = calc(client, sid, operation, parameters=parameters)
    raw = wave(client, sid, mode="engineering")["values"]
    eng = cwave(client, cid, "engineering")["values"]
    assert eng == pytest.approx([physics(v) for v in raw], rel=1e-12, abs=1e-9)           # arithmetic in ENG before normalisation
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "configured" and body["values"] == pytest.approx([v / d for v in eng], rel=1e-12, abs=1e-15)
    assert peak(body["values"]) == pytest.approx(abs(physics(1.0)), rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == ("verified_converted", "base_divided_by_ratio", "secondary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["measurement_side"] == "secondary"


def test_a_unary_chain_takes_the_side_of_the_transitive_leaf(client):
    d = IBASE_A / RATIO
    sid, _ = build(client, flags="S", amplitude=d)
    first = calc(client, sid, "reverse_polarity")
    second = checked(client.post(CALC, json={"name": "half", "operation": "multiply_constant", "parameters": {"constant": 0.5},
        "inputs": [{"kind": "calculated", "calculated_channel_id": first}]}), 201)["id"]
    body, p = cwave(client, second), cprov(client, second)
    assert peak(body["values"]) == pytest.approx(0.5, rel=1e-12) and p["verification_state"] == "verified_converted"


def test_addition_of_two_same_group_secondary_phases_sums_in_eng_then_converts(client):
    d = IBASE_A / RATIO
    sid, _ = build(client, flags="S", amplitude=d)
    cid = calc(client, sid, "addition", ("IA", "IB"))
    raw = wave(client, sid, mode="engineering")["values"]
    eng = cwave(client, cid, "engineering")["values"]
    assert eng == pytest.approx([2.0 * v for v in raw], rel=1e-12, abs=1e-9)
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["values"] == pytest.approx([v / d for v in eng], rel=1e-12, abs=1e-15) and peak(body["values"]) == pytest.approx(2.0, rel=1e-12)
    assert (p["verification_state"], p["ratio_authority"]) == ("verified_converted", "manual")


def test_addition_on_primary_samples_is_verified_direct_and_bit_identical(client):
    sid, _ = build(client, flags="P", amplitude=IBASE_A)
    cid = calc(client, sid, "addition", ("IA", "IB"))
    eng = cwave(client, cid, "engineering")["values"]
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["values"] == [v / IBASE_A for v in eng] and p["verification_state"] == "verified_direct"


def test_primary_and_secondary_recordings_give_the_same_calculated_pu(client):
    primary, _ = build(client, flags="P", amplitude=0.8 * IBASE_A)
    secondary, _ = build(client, flags="S", amplitude=0.8 * IBASE_A / RATIO)
    a = cwave(client, calc(client, primary, "reverse_polarity", name="p"))["values"]
    b = cwave(client, calc(client, secondary, "reverse_polarity", name="s"))["values"]
    assert a == pytest.approx(b, rel=1e-12, abs=1e-12) and peak(a) == pytest.approx(0.8, rel=1e-12)


def test_a_calculated_conversion_without_a_ct_is_the_established_refusal(client):
    sid, _ = build(client, flags="S", amplitude=1.0, ct=None)
    cid = calc(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["values"] == cwave(client, cid, "engineering")["values"]
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "ct_authority_unavailable"
    assert p["reason"] and "incompatible" in p["reason"].lower()


def test_a_non_strict_leaf_keeps_the_historical_number_labelled_unverified(client):
    sid, _ = build(client, flags="", amplitude=IBASE_A)
    cid = calc(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["values"] == [v / IBASE_A for v in cwave(client, cid, "engineering")["values"]]
    assert p["verification_state"] == "unverified_historical" and p["ratio_applied"] is None


# ------------------------------------------------------------------------- K-1 / K-2 / K-3 across groups
def two_groups(client, flags, *, sides=("primary", "primary"), cts=((CT_PRIMARY, CT_SECONDARY),) * 2, bases=(1.2, 1.2), amplitude=IBASE_A):
    sid = upload(client, flags, amplitude)
    clear_groups(client, sid)
    current_group(client, sid, ["IA"], name="G1", side=sides[0], ct=cts[0], ibase_ka=bases[0])
    current_group(client, sid, ["IB"], name="G2", side=sides[1], ct=cts[1], ibase_ka=bases[1])
    return sid


def test_k1_strict_leaves_on_different_sides_are_refused_never_converted(client):
    sid = two_groups(client, ["P", "S", "P"])
    cid = calc(client, sid, "addition", ("IA", "IB"))
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["values"] == cwave(client, cid, "engineering")["values"]
    assert p["status"] == "base_required" and "incompatible" in p["reason"].lower()
    assert p["verification_state"] == "blocked"


def test_k2_secondary_across_distinct_ct_authorities_stays_unavailable_even_with_equal_ratios(client):
    sid = two_groups(client, "S", sides=("secondary", "secondary"), bases=(0.005, 0.005), amplitude=5.0)
    cid = calc(client, sid, "addition", ("IA", "IB"))
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and p["verification_state"] == "blocked"
    assert "secondary" in p["reason"].lower()


def test_k3_primary_across_two_groups_with_equal_bases_is_direct(client):
    sid = two_groups(client, "P")
    cid = calc(client, sid, "addition", ("IA", "IB"))
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "configured" and peak(body["values"]) == pytest.approx(2.0, rel=1e-12)
    assert p["verification_state"] == "verified_direct"


def test_k3_primary_across_two_groups_with_different_bases_is_still_unavailable(client):
    sid = two_groups(client, "P", bases=(1.2, 2.4))
    cid = calc(client, sid, "addition", ("IA", "IB"))
    body = cwave(client, cid)
    assert body["per_unit_status"] == "base_required" and body["values"] == cwave(client, cid, "engineering")["values"]


# ------------------------------------------------------------------------------------------------ Source Default leaves
def test_calculated_current_over_a_source_default_follows_the_same_gate(client):
    primary, _ = build(client, flags="P", amplitude=IBASE_A, group=False)
    source_default(client, primary, "primary")
    p = cprov(client, calc(client, primary, "reverse_polarity", name="p"))
    assert (p["verification_state"], p["source_kind"]) == ("verified_direct", "source_default")
    secondary, _ = build(client, flags="S", amplitude=1.0, group=False)
    source_default(client, secondary, "primary")
    cid = calc(client, secondary, "reverse_polarity", name="s")
    assert cwave(client, cid)["per_unit_status"] == "base_required"
    assert cprov(client, cid)["side_refusal_detail"] == "no_group"


# ----------------------------------------------------------------------------------- Stage 5B: a result-owned Manual base
def result_config(client, cid, **body):
    return client.put(f"{CALC}/{cid}/per-unit-config", json=body)


def test_stage_5b_manual_primary_base_on_secondary_leaves_is_converted_with_the_leaves_ct(client):
    d = 600.0 / RATIO
    sid, _ = build(client, flags="S", amplitude=d)
    cid = calc(client, sid, "reverse_polarity")
    saved = result_config(client, cid, mode="manual", current_base_value=600.0, current_base_unit="A", base_reference_side="primary")
    assert saved.status_code == 200, saved.text
    body, p = cwave(client, cid), cprov(client, cid)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["configuration_mode"]) == ("verified_converted", "base_divided_by_ratio", "manual")
    assert p["configured_current_base_amps"] == 600.0 and p["base_reference_side"] == "primary"


def test_stage_5b_manual_secondary_base_on_secondary_leaves_is_direct(client):
    sid, _ = build(client, flags="S", amplitude=2.5)
    cid = calc(client, sid, "reverse_polarity")
    assert result_config(client, cid, mode="manual", current_base_value=2.5, current_base_unit="A", base_reference_side="secondary").status_code == 200
    body, p = cwave(client, cid), cprov(client, cid)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12) and p["verification_state"] == "verified_direct"


def test_stage_5b_a_rejected_update_is_atomic_when_the_conversion_has_no_ct(client):
    sid, _ = build(client, flags="S", amplitude=1.0, ct=None)
    cid = calc(client, sid, "reverse_polarity")
    before = checked(client.get(f"{CALC}/{cid}/per-unit-config"))
    rejected = result_config(client, cid, mode="manual", current_base_value=600.0, current_base_unit="A", base_reference_side="primary")
    assert rejected.status_code in (400, 422), rejected.text
    assert checked(client.get(f"{CALC}/{cid}/per-unit-config")) == before          # nothing was published


def test_stage_5b_an_undeclared_manual_side_is_still_rejected_and_nothing_is_stored(client):
    sid, _ = build(client, flags="P", amplitude=IBASE_A)
    cid = calc(client, sid, "reverse_polarity")
    before = checked(client.get(f"{CALC}/{cid}/per-unit-config"))
    rejected = result_config(client, cid, mode="manual", current_base_value=600.0, current_base_unit="A", base_reference_side="unknown")
    assert rejected.status_code in (400, 422), rejected.text
    assert checked(client.get(f"{CALC}/{cid}/per-unit-config")) == before


def test_stage_5b_a_known_mismatch_across_a_source_default_is_rejected(client):
    sid, _ = build(client, flags="S", amplitude=1.0, group=False)
    cid = calc(client, sid, "reverse_polarity")
    rejected = result_config(client, cid, mode="manual", current_base_value=600.0, current_base_unit="A", base_reference_side="primary")
    assert rejected.status_code in (400, 422), rejected.text


# ------------------------------------------------------------------------------------------ compliance consumer (calculated)
def test_the_compliance_series_follows_the_calculated_current_side_authority(client):
    from app.domain.calculated_channel import ChannelRef
    from app.services.compliance_series import Registries, load_series
    from app.services.recorded_side_authority import RecordedAuthority

    d = IBASE_A / RATIO
    sid, _ = build(client, flags="S", amplitude=d)
    cid = calc(client, sid, "reverse_polarity")
    s = client.app.state
    reg = Registries(source=s.workspace_registry, calc=s.calculated_channel_registry, per_unit=s.per_unit_registry,
                     group=s.measurement_group_registry, voltage_config=s.voltage_group_config_registry,
                     current_config=s.current_group_config_registry, side_authority=RecordedAuthority.from_app_state(s))
    loaded, problem = load_series(ChannelRef(kind="calculated", calculated_channel_id=cid), "pu",
                                  workspace_id=ROOT.split("/workspaces/")[1], reg=reg)
    assert problem is None
    assert list(loaded.values) == pytest.approx(cwave(client, cid)["values"], rel=1e-12, abs=1e-15)


# ------------------------------------------------------------------------- Recording Details corrections reach calculated Current
def test_an_engineers_side_correction_reaches_a_calculated_current_result(client):
    sid, _ = build(client, flags="", amplitude=IBASE_A / RATIO)
    cid = calc(client, sid, "reverse_polarity")
    assert cprov(client, cid)["verification_state"] == "unverified_historical"
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    p = cprov(client, cid)
    assert (p["verification_state"], p["measurement_side"]) == ("verified_converted", "secondary")
    assert peak(cwave(client, cid)["values"]) == pytest.approx(1.0, rel=1e-12)


def test_an_engineer_established_side_never_turns_a_blocked_k2_result_into_a_number(client):
    """Recording Details' side may only ADD a block to the historical gate (S2 correction): undeclared leaves across two CT authorities are
    refused for an unknown side; establishing the Secondary side in Recording Details leaves the result refused (K-2), never allowed."""
    sid = two_groups(client, "", sides=("secondary", "secondary"), bases=(0.005, 0.005), amplitude=5.0)
    cid = calc(client, sid, "addition", ("IA", "IB"))
    assert cwave(client, cid)["per_unit_status"] == "base_required" and "unknown" in cprov(client, cid)["reason"].lower()
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["values"] == cwave(client, cid, "engineering")["values"]
    assert p["verification_state"] == "blocked"


# ------------------------------------------------------------------------------- additional safeguards (mutation closeout)
def test_source_default_secondary_base_on_secondary_samples_is_verified_direct_without_a_ct(client):
    sid, _ = build(client, flags="S", amplitude=5.0, group=False)
    source_default(client, sid, "secondary", ka=0.005)
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body["values"]) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["base_reference_side"], p["ratio_applied"]) == ("verified_direct", "secondary", None)


def test_a_calculated_result_over_an_undeclared_base_side_keeps_the_historical_number_never_assumed_primary(client):
    sid, _ = build(client, flags="P", amplitude=IBASE_A, side="unknown")
    cid = calc(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "configured"
    assert body["values"] == [v / IBASE_A for v in cwave(client, cid, "engineering")["values"]]
    assert p["verification_state"] == "unverified_historical" and p["ratio_applied"] is None


def test_a_conversion_across_two_ct_authorities_is_refused_even_when_both_cts_agree(client):
    """Secondary bases on Primary samples need B x CT; with the leaves in two groups there is no single CT authority (K-2 family)."""
    sid = two_groups(client, "P", sides=("secondary", "secondary"), bases=(0.005, 0.005), amplitude=1200.0)
    cid = calc(client, sid, "addition", ("IA", "IB"))
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and body["values"] == cwave(client, cid, "engineering")["values"]
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "ct_authority_unavailable"


# ---------------------------------------------------------------- the S2 numerical-integrity correction applied to calculated Current
def test_a_legacy_manual_pointer_keeps_its_historical_denominator_and_is_never_verified(client):
    """The legacy explicit profile-pointer path is the historical gate: same number as before, never `verified_*`, no denominator side,
    conversion or ratio claimed -- even when the recording's side and the base label are both strictly Primary."""
    sid, _ = build(client, flags="P", amplitude=IBASE_A)
    cid = calc(client, sid, "reverse_polarity")
    assert cprov(client, cid)["verification_state"] == "verified_direct"                  # the resolver placed the automatic base
    client.app.state.per_unit_registry.set_manual_assignment_for_calculated_channel(ROOT.split("/workspaces/")[1], cid, sid)
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["values"] == [v / IBASE_A for v in cwave(client, cid, "engineering")["values"]]      # the historical number, bit for bit
    assert p["verification_state"] == "unverified_historical"
    assert p["denominator_side"] is None and p["side_conversion"] is None and p["ratio_applied"] is None


def test_recording_details_side_adds_a_block_to_the_legacy_manual_pointer_but_never_removes_one(client):
    """The effective side may only ADD a block: the pointer's raw-Primary / Primary-label result becomes refused once Recording Details
    establishes Secondary, whereas the opposite correction cannot unblock a result the raw declaration refused."""
    ws = ROOT.split("/workspaces/")[1]
    sid, _ = build(client, flags="P", amplitude=IBASE_A)
    cid = calc(client, sid, "reverse_polarity")
    client.app.state.per_unit_registry.set_manual_assignment_for_calculated_channel(ws, cid, sid)
    assert cwave(client, cid)["per_unit_status"] == "configured"
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and p["verification_state"] == "blocked"
    sid2, _ = build(client, flags="S", amplitude=5.0, ct=None)
    cid2 = calc(client, sid2, "reverse_polarity", name="second")
    client.app.state.per_unit_registry.set_manual_assignment_for_calculated_channel(ws, cid2, sid2)
    assert cwave(client, cid2)["per_unit_status"] == "base_required"                       # raw Secondary vs Primary label
    checked(client.put(f"{ROOT}/sources/{sid2}/measurement-side", json={"side": "primary"}))
    assert cwave(client, cid2)["per_unit_status"] == "base_required"                       # the correction cannot unblock it
