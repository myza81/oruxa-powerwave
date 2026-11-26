"""PU-MIG S2 -- raw Voltage per-unit through the real API: Recording Details' side and VT decide the denominator.

Every case builds one synthetic ASCII COMTRADE (three 50 Hz Voltage channels whose peak is `amplitude` volts, the recording's own
P/S flag as given), one confirmed Voltage Measurement Group and the configuration under test, then reads the SAME channel through
every source seam (range, cursor values, peak values, annotation anchor), the provenance endpoint and the coverage endpoint. The
expected numbers are written out from the physics (never from application code): `pu = sample / D`, with `D` the base expressed in
the unit of the SAMPLES' side.

Instantaneous versus RMS (read before the numbers): per unit here is applied to INSTANTANEOUS samples, `pu = sample / D`, where `D` is
the RMS-referred base (nominal L-L, or nominal L-L / sqrt(3) for a line-to-ground reference). The synthetic sinusoids below have a PEAK equal
to `D`, so their peak reads 1.0 pu and their RMS 0.7071 pu; a waveform at exactly the rated RMS voltage would PEAK at sqrt(2) = 1.4142 pu.
"The same 1.0 pu" in these tests therefore means "the same peak-referred value on either side of the VT", not "rated voltage".

Approved policies exercised (owner decisions of 2026-11-25): D-1 R+ (historical numbers kept, explicitly qualified), D-4 P5 (a
stored secondary base is never replaced; a discrepancy is reported), D-5 (the legacy secondary path needs an explicit Secondary
declaration AND a valid stored value), D-6 (a Secondary base on Primary samples converts only with an authoritative ratio),
D-7 (the existing `auto_nominal` VT is consumed, with its provenance), N-2 (existing reason vocabulary).
"""

from __future__ import annotations

import io
import math

import pytest

from tests.test_current_effective_base_inheritance import ROOT, checked, client  # noqa: F401  (client is the shared fixture)

SQRT3 = math.sqrt(3.0)
NOMINAL_KV = 132.0
RATIO = 132000.0 / 110.0                      # a 132 kV / 110 V VT
D_PRIMARY_LG = NOMINAL_KV * 1000.0 / SQRT3    # the line-to-ground base in primary volts (RMS-referred); a sinusoid whose PEAK is this reads 1.0 pu
D_SECONDARY_LG = 110.0 / SQRT3                # the same base in secondary volts (110 V L-L VT); a sinusoid whose PEAK is this reads 1.0 pu
SAMPLES = 100
NAMES = ["VA", "VB", "VC"]


def comtrade(flag: str, amplitude: float) -> tuple[bytes, bytes]:
    cfg = [
        "S2_STATION,S2_DEVICE,1999", "3,3A,0D",
        *[f"{i + 1},{n},,,V,1.0,0.0,0,-99999999,99999999,1.0,1.0,{flag[i] if isinstance(flag, (list, tuple)) else flag}"
          for i, n in enumerate(NAMES)],
        "50", "1", f"1000.0,{SAMPLES}", "01/01/2026,00:00:00.000000", "01/01/2026,00:00:00.000000", "ASCII", "1.0",
    ]
    rows = []
    for n in range(SAMPLES):
        v = amplitude * math.sin(2.0 * math.pi * 50.0 * n / 1000.0)
        rows.append(f"{n + 1},{n * 1000.0},{v!r},{v!r},{v!r}")
    return ("\r\n".join(cfg) + "\r\n").encode(), ("\r\n".join(rows) + "\r\n").encode()


def build(client, *, flag="P", amplitude=D_PRIMARY_LG, stored_side="unknown", nominal=NOMINAL_KV, vt=None,
          secondary_v=None, group=True, status="confirmed"):
    cfg, dat = comtrade(flag, amplitude)
    sid = checked(client.post(ROOT + "/sources", files={
        "cfg_file": ("s2.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("s2.dat", io.BytesIO(dat), "application/octet-stream"),
    }), 201)["source_id"]
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    for existing in checked(client.get(url)):
        assert client.delete(url + "/" + existing["id"]).status_code == 204
    gid = None
    if group:
        gid = checked(client.post(url, json={
            "kind": "voltage", "display_name": "HV", "status": status,
            "channel_refs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in NAMES],
        }), 201)["id"]
        body = {"reference_mode": "manual", "reference_override": "line_to_ground", "base_reference_side": stored_side}
        if nominal is not None:
            body["nominal_voltage_ll_kv"] = nominal
        if secondary_v is not None:
            body["secondary_voltage_ll_v"] = secondary_v
        if vt is not None:
            body["vt_primary_v"], body["vt_secondary_v"] = vt
        checked(client.put(f"{url}/{gid}/voltage-config", json=body))
    return sid, gid


def wave(client, sid, name="VA", mode="per_unit"):
    return checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={"channel_name": name, "unit_mode": mode}))


def provenance(client, sid, name="VA"):
    return checked(client.get(f"{ROOT}/sources/{sid}/per-unit-resolution", params={"channel_name": name}))


def peak(body):
    return max(abs(v) for v in body["values"])


def seams(client, sid, name="VA"):
    """The four source seams plus provenance: every one must agree on the number and the verification."""
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


# --------------------------------------------------------------------------------------------- same side, Primary
def test_same_side_primary_is_bit_identical_to_the_historical_arithmetic(client):
    sid, _ = build(client, flag="P", stored_side="primary")
    body, p = wave(client, sid), provenance(client, sid)
    denominator = (NOMINAL_KV * 1000.0) / SQRT3      # exactly the production base: (kV x 1000) / sqrt(3)
    raw = wave(client, sid, mode="engineering")["values"]
    assert body["per_unit_status"] == "configured" and body["unit"] == "pu"
    assert body["values"] == [v / denominator for v in raw]
    assert peak(body) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["ratio_applied"]) == ("verified_direct", "direct", None)
    assert p["measurement_side"] == "primary" and p["base_reference_side"] == "primary"
    assert p["effective_base_amount"] == pytest.approx(denominator / 1000.0, rel=1e-15)


def test_a_stored_unknown_base_side_no_longer_downgrades_a_strict_primary_sample(client):
    """IC-3: the same number as before; only the label changes (compatible, no longer 'unverified')."""
    sid, _ = build(client, flag="P", stored_side="unknown")
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body) == pytest.approx(1.0, rel=1e-12)
    assert body["per_unit_reference_compatibility"] == "compatible" and p["verification_state"] == "verified_direct"


# ----------------------------------------------------------------------------------------- same side, Secondary (legacy)
def test_same_side_secondary_legacy_path_keeps_its_numerics_and_needs_no_ratio(client):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="secondary", secondary_v=110.0)
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["ratio_applied"]) == ("verified_direct", "direct", None)
    assert p["measurement_side"] == "secondary" and p["base_reference_side"] == "secondary"


# --------------------------------------------------------------------- Primary base, Secondary samples (converted)
@pytest.mark.parametrize("vt,authority", [((132000.0, 110.0), "manual"), (None, "auto_nominal")])
def test_primary_base_on_secondary_samples_is_converted_by_the_groups_vt(client, vt, authority):
    """Physical equivalence: the SAME peak-referred 1.0 pu (peak = D, RMS 0.7071 pu) whether the samples are primary or secondary volts (D-7 for auto_nominal)."""
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=vt)
    body, cursor, anchor, peaks, p = seams(client, sid)
    assert body["per_unit_status"] == "configured" and body["per_unit_reference_compatibility"] == "compatible"
    assert peak(body) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == ("verified_converted", "base_divided_by_ratio", "secondary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["ratio_authority"] == authority
    assert p["effective_base_amount"] == pytest.approx(D_SECONDARY_LG / 1000.0, rel=1e-12)
    assert p["measurement_side"] == "secondary"
    # Every seam answers with the same number and the same verification.
    assert abs(cursor["a_value"]) <= 1.0 + 1e-12 and cursor["per_unit_reference_compatibility"] == "compatible"
    assert anchor["per_unit_reference_compatibility"] == "compatible"
    assert max(r["value"] for r in peaks if r["mode"] == "max") == pytest.approx(1.0, rel=1e-12)
    assert min(r["value"] for r in peaks if r["mode"] == "min") == pytest.approx(-1.0, rel=1e-3)


def test_primary_and_secondary_samples_of_one_physical_condition_give_the_same_pu(client):
    primary, _ = build(client, flag="P", amplitude=0.8 * D_PRIMARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    secondary, _ = build(client, flag="S", amplitude=0.8 * D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    a, b = wave(client, primary)["values"], wave(client, secondary)["values"]
    assert peak(wave(client, primary)) == pytest.approx(0.8, rel=1e-12)
    assert a == pytest.approx(b, rel=1e-12, abs=1e-12)


def test_a_stored_unknown_base_side_with_a_strict_secondary_sample_converts(client):
    """IC-2: a number is produced ONLY because Recording Details declared the side and a VT exists."""
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="unknown")
    assert peak(wave(client, sid)) == pytest.approx(1.0, rel=1e-12)
    assert provenance(client, sid)["verification_state"] == "verified_converted"


def test_an_engineers_recording_side_correction_changes_the_pu(client):
    """IC-7: the recording declares nothing; the engineer sets Secondary in Recording Details (Level 1)."""
    sid, _ = build(client, flag="", amplitude=D_SECONDARY_LG, stored_side="primary")
    before = provenance(client, sid)
    assert before["verification_state"] == "unverified_historical"          # a number, explicitly not verified
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    after, body = provenance(client, sid), wave(client, sid)
    assert after["verification_state"] == "verified_converted" and after["measurement_side"] == "secondary"
    assert peak(body) == pytest.approx(1.0, rel=1e-12)
    assert after["side_authority"] == "engineer_recording_correction"


# ------------------------------------------------------------------------- Secondary base, Primary samples (D-5, D-6)
def test_secondary_base_on_primary_samples_converts_with_an_authoritative_vt(client):
    sid, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, stored_side="secondary", secondary_v=110.0, vt=(132000.0, 110.0))
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body) == pytest.approx(1.0, rel=1e-12)
    assert (p["verification_state"], p["side_conversion"], p["denominator_side"]) == ("verified_converted", "base_multiplied_by_ratio", "primary")
    assert p["ratio_applied"] == pytest.approx(RATIO, rel=1e-12) and p["ratio_authority"] == "manual"


def test_secondary_base_on_primary_samples_is_blocked_without_an_authoritative_ratio(client):
    """D-6: required conversion + no ratio authority = no number; the engineering values are untouched."""
    sid, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, stored_side="secondary", secondary_v=110.0, nominal=None)
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "V"
    assert body["values"] == wave(client, sid, mode="engineering")["values"]
    assert body["per_unit_reference_compatibility"] == "incompatible"
    assert p["reason"] and p["status"] == "base_required" and p["verification_state"] == "blocked"
    assert p["side_refusal_reason"] == "vt_authority_unavailable" and p["side_refusal_detail"] == "not_configured"


def test_a_stored_secondary_value_alone_does_not_activate_the_legacy_path(client):
    """D-5: the declaration `secondary` AND a valid value are both required. With the declaration Primary the nominal base
    decides -- a stored 115 V is ignored for the denominator -- exactly as before."""
    sid, _ = build(client, flag="P", amplitude=D_PRIMARY_LG, stored_side="primary", secondary_v=115.0, vt=(132000.0, 110.0))
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body) == pytest.approx(1.0, rel=1e-12) and p["side_conversion"] == "direct"


def test_a_stored_secondary_declaration_without_a_valid_value_stays_blocked(client):
    """The existing safeguard (no silent fall-back to the primary nominal) is preserved untouched."""
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="secondary", secondary_v=None)
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and p["reason"]
    assert body["values"] == wave(client, sid, mode="engineering")["values"]


# --------------------------------------------------------------------------------------------------------------- D-4 (P5)
def test_a_stored_secondary_base_is_never_replaced_by_a_derived_one_but_the_discrepancy_is_reported(client):
    sid, _ = build(client, flag="S", amplitude=115.0 / SQRT3, stored_side="secondary", secondary_v=115.0, vt=(132000.0, 110.0))
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body) == pytest.approx(1.0, rel=1e-12)             # D = the STORED 115 V / sqrt(3), not the derived 110 V
    (diagnostic,) = p["base_diagnostics"]
    assert diagnostic["code"] == "stored_secondary_differs_from_derived"
    assert diagnostic["stored_secondary_ll_v"] == 115.0 and diagnostic["derived_secondary_ll_v"] == pytest.approx(110.0)
    assert diagnostic["relative_difference"] == pytest.approx(5.0 / 110.0, rel=1e-9) and diagnostic["derivation"] == "stored_vt"


def test_an_agreeing_stored_secondary_base_reports_no_discrepancy(client):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="secondary", secondary_v=110.0, vt=(132000.0, 110.0))
    assert provenance(client, sid)["base_diagnostics"] == []


# -------------------------------------------------------------------------------- historical Unverified (D-1, option R+)
def test_an_undeclared_side_keeps_the_historical_number_and_is_labelled(client):
    sid, _ = build(client, flag="", amplitude=D_PRIMARY_LG, stored_side="primary")
    body, p = wave(client, sid), provenance(client, sid)
    raw = wave(client, sid, mode="engineering")["values"]
    assert body["values"] == [v / ((NOMINAL_KV * 1000.0) / SQRT3) for v in raw]       # bit-identical to the historical result
    assert body["per_unit_reference_compatibility"] == "unverified" and p["verification_state"] == "unverified_historical"
    assert p["side_conversion"] is None and p["ratio_applied"] is None


def test_the_historical_exception_does_not_bypass_a_known_mismatch(client):
    """Primary samples declared on the recording, a stored Secondary base with no secondary value: still blocked."""
    sid, _ = build(client, flag="P", stored_side="secondary", secondary_v=None)
    assert wave(client, sid)["per_unit_status"] == "base_required"


# ------------------------------------------------------------------------------------------------ Source Default (ungrouped)
def source_default(client, *, flag):
    sid, _ = build(client, flag=flag, amplitude=D_PRIMARY_LG if flag != "S" else D_SECONDARY_LG, group=False)
    checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
        "voltage_base_value": NOMINAL_KV, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground",
    }))
    return sid


def test_source_default_primary_samples_are_unchanged_and_verified(client):
    sid = source_default(client, flag="P")
    body, p = wave(client, sid), provenance(client, sid)
    assert peak(body) == pytest.approx(1.0, rel=1e-12) and p["source_kind"] == "source_default"
    assert p["verification_state"] == "verified_direct"


def test_source_default_has_no_vt_authority_so_a_secondary_sample_is_blocked(client):
    sid = source_default(client, flag="S")
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and body["values"] == wave(client, sid, mode="engineering")["values"]
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "vt_authority_unavailable"
    assert p["side_refusal_detail"] == "no_group"
    assert p["reason"] is not None


# ----------------------------------------------------------------------------------------------- representability
def test_downstream_non_representable_pu_results_stay_blocked(client):
    """The existing channel-value safeguard (`per_unit_result_not_representable`) is evaluated after the resolver."""
    sid, _ = build(client, flag="P", amplitude=1.0e300, stored_side="primary", nominal=1.0e-20)
    body = wave(client, sid)
    assert body["per_unit_status"] == "base_required" and body["unit"] == "V"
    assert provenance(client, sid)["reason"]


def test_a_conversion_that_overflows_is_refused_with_the_existing_reason_and_no_number(client):
    sid, _ = build(client, flag="S", amplitude=1.0, stored_side="primary", nominal=1.0e300, vt=(1.0e-100, 1.0e100))
    body, p = wave(client, sid), provenance(client, sid)
    assert body["per_unit_status"] == "base_required" and body["values"] == wave(client, sid, mode="engineering")["values"]
    assert p["verification_state"] == "blocked" and p["side_refusal_reason"] == "denominator_not_representable"


def test_a_subnormal_denominator_is_valid(client):
    sid, _ = build(client, flag="P", amplitude=1.0e-320, stored_side="primary", nominal=1.0e-320)
    p = provenance(client, sid)
    assert p["status"] == "configured" and p["verification_state"] == "verified_direct"


# ----------------------------------------------------------------------------------------------- coverage agrees (C-3)
def test_coverage_counts_agree_with_the_display(client):
    converted, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    assert checked(client.get(f"{ROOT}/per-unit/sources/{converted}/coverage")) == {
        "source_id": converted, "applicable_channel_count": 3, "measurement_group_count": 3,
        "source_default_count": 0, "needs_configuration_count": 0, "unverified_reference_count": 0}
    historical, _ = build(client, flag="", amplitude=D_PRIMARY_LG, stored_side="primary")
    coverage = checked(client.get(f"{ROOT}/per-unit/sources/{historical}/coverage"))
    assert (coverage["measurement_group_count"], coverage["unverified_reference_count"]) == (3, 3)
    blocked = source_default(client, flag="S")
    coverage = checked(client.get(f"{ROOT}/per-unit/sources/{blocked}/coverage"))
    assert (coverage["needs_configuration_count"], coverage["source_default_count"]) == (3, 0)


def test_coverage_and_provenance_agree_when_a_groups_declared_sides_conflict(client):
    """S0 finding C-3: the coverage seam reads the Voltage group's stored side exactly like the display and provenance seams.
    Mixed P/S declarations make the group's side a conflict (not strict), so the historical gate decides per channel: the two
    Primary channels meet a stored Secondary base (blocked), the Secondary channel meets it (a number, explicitly not verified)."""
    sid, _ = build(client, flag=["P", "S", "P"], amplitude=D_SECONDARY_LG, stored_side="secondary", secondary_v=110.0)
    states = {name: provenance(client, sid, name) for name in NAMES}
    assert [states[n]["status"] for n in NAMES] == ["base_required", "configured", "base_required"]
    assert [states[n]["verification_state"] for n in NAMES] == ["blocked", "unverified_historical", "blocked"]
    coverage = checked(client.get(f"{ROOT}/per-unit/sources/{sid}/coverage"))
    assert (coverage["measurement_group_count"], coverage["needs_configuration_count"], coverage["unverified_reference_count"]) == (1, 2, 0)
    # The Secondary channel's historical label is unchanged ("compatible": its declaration matches the stored base side); what
    # S2 adds is the explicit state, because its group's side is not strict.
    assert states["VB"]["reference_compatibility"] == "compatible"

