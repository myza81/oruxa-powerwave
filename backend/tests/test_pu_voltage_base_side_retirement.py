"""DEC-219 -- the nominal system voltage is always the PRIMARY Voltage PU base; the separate Voltage Base Reference Side input is retired.

The frontend no longer lets an engineer pick a side. What the UI now sends is exactly what these tests send (the payloads of
`wwRdVoltageApply`, `wwRdVoltageRevert` and the VT writers), so they prove the contract at the API:

  * a save that establishes a nominal base (new, changed or reviewed) declares `base_reference_side: "primary"` explicitly;
  * every other save OMITS the field, and the backend preserves the stored declaration: a legacy Secondary base, a historical Unknown;
  * the effective denominator is the existing side-denominator authority's, so Primary and Secondary samples, L-L/L-G and a changed VT
    behave exactly as before (expected values are first-principles, as in S2: D = nominal / r, r = VT primary / secondary).

Expected values on the synth_measurement_groups fixture (channel N275_VR, nominal 275 kV, line-to-line base D = 275 kV):
    Primary samples   peak 158.77 kV                                            -> 158.77 / 275      = 0.57735
    Secondary samples peak 0.577345 kV, auto_nominal r = 275 kV : 110 V = 2500  -> 0.577345 / 0.110  = 5.2486
    Secondary samples with the engineer's VT 275 kV : 1 kV (r = 275)            -> 0.577345 / 1.0    = 0.577345
    line-to-ground base D = 275 / sqrt(3) kV = 158.77 kV                        -> Primary 1.0, Secondary 9.0909 (= 5.2486 x sqrt(3))
"""

from __future__ import annotations

import io

import pytest

from tests.test_per_unit_voltage_reference_safety import (  # noqa: F401  (client is the shared fixture)
    SECONDARY_V, VNAMES, checked, client, provenance, recording, wave_status, ROOT,
)
from tests.test_pu_mig_s2_raw_voltage_side import peak as pu_peak

NOMINAL_KV = 275.0
AUTO_RATIO = NOMINAL_KV * 1000.0 / 110.0        # DEC-215 auto_nominal: nominal kV x 1000 : 110 V
REAL_RATIO = NOMINAL_KV * 1000.0 / SECONDARY_V  # the fixture's own VT, 275 kV : 1 kV
PRIMARY_PEAK_KV = 158.77
SECONDARY_PEAK_KV = 0.577345


def new_group(client, sid):
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    group = checked(client.post(url, json={
        "kind": "voltage", "display_name": "DEC-219", "status": "confirmed",
        "channel_refs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in VNAMES]}), 201)
    return f"{url}/{group['id']}/voltage-config"


def stored(client, sid):
    return checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))[0]["voltage_config"]


def ui_apply_new_nominal(client, path, *, override="line_to_line", nominal=NOMINAL_KV):
    """The payload `wwRdVoltageApply` builds for a new or changed nominal: the side is declared Primary explicitly."""
    return checked(client.put(path, json={
        "reference_mode": "manual", "reference_override": override, "nominal_voltage_ll_kv": nominal, "base_reference_side": "primary"}))


# ------------------------------------------------------------------------------------------ 2, 3, 4, 5: a new nominal is the Primary base
def test_a_new_nominal_voltage_establishes_a_primary_base(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "P")
    path = new_group(client, sid)
    ui_apply_new_nominal(client, path)
    vc = stored(client, sid)
    assert (vc["nominal_voltage_ll_kv"], vc["base_reference_side"]) == (NOMINAL_KV, "primary")
    assert vc["secondary_voltage_ll_v"] is None                                            # no secondary base appears


def test_primary_samples_use_the_primary_denominator(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "P")
    ui_apply_new_nominal(client, new_group(client, sid))
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert prov["verification_state"] == "verified_direct" and prov["ratio_applied"] is None
    assert pu_peak(body) == pytest.approx(PRIMARY_PEAK_KV / NOMINAL_KV, rel=1e-12)


def test_secondary_samples_use_the_derived_denominator(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    ui_apply_new_nominal(client, new_group(client, sid))
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert (prov["verification_state"], prov["ratio_authority"]) == ("verified_converted", "auto_nominal")
    assert prov["ratio_applied"] == pytest.approx(AUTO_RATIO)
    assert prov["effective_base_amount"] == pytest.approx(NOMINAL_KV / AUTO_RATIO, rel=1e-12)      # 0.110 kV
    assert pu_peak(body) == pytest.approx(SECONDARY_PEAK_KV / (NOMINAL_KV / AUTO_RATIO), rel=1e-9)   # 5.2486


@pytest.mark.parametrize("marker,expected", [("P", 1.0), ("S", 9.0909090909)])
def test_line_to_ground_conversion_stays_correct(client, comtrade_fixtures_dir, marker, expected):
    sid = recording(client, comtrade_fixtures_dir, marker)
    ui_apply_new_nominal(client, new_group(client, sid), override="line_to_ground")
    assert pu_peak(wave_status(client, sid, VNAMES[0])) == pytest.approx(expected, rel=1e-4)       # D = 275 / sqrt(3) kV


# ------------------------------------------------------------------------------------------ 6, 7: side and VT changes
def test_changing_the_measurement_side_never_changes_the_nominal_base(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "P")
    ui_apply_new_nominal(client, new_group(client, sid))
    before = stored(client, sid)
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-side", json={"side": "secondary"}))
    after = stored(client, sid)
    keys = ("nominal_voltage_ll_kv", "base_reference_side", "secondary_voltage_ll_v")
    assert [after[k] for k in keys] == [before[k] for k in keys] == [NOMINAL_KV, "primary", None]


def test_changing_the_vt_refreshes_the_denominator_and_leaves_the_base_alone(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    path = new_group(client, sid)
    ui_apply_new_nominal(client, path)
    assert pu_peak(wave_status(client, sid, VNAMES[0])) == pytest.approx(SECONDARY_PEAK_KV / 0.110, rel=1e-9)
    # the VT writer: the VT is written and the base side is OMITTED
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "vt_primary_v": NOMINAL_KV * 1000.0, "vt_secondary_v": SECONDARY_V}))
    prov = provenance(client, sid, VNAMES[0])
    assert prov["ratio_authority"] == "manual" and prov["ratio_applied"] == pytest.approx(REAL_RATIO)
    assert pu_peak(wave_status(client, sid, VNAMES[0])) == pytest.approx(SECONDARY_PEAK_KV / 1.0, rel=1e-9)
    vc = stored(client, sid)
    assert (vc["nominal_voltage_ll_kv"], vc["base_reference_side"]) == (NOMINAL_KV, "primary")


# ------------------------------------------------------------------------------------------ 8, 9, 10: legacy declarations survive unrelated saves
def legacy_secondary_group(client, sid):
    """A legitimate legacy Secondary base (D-5): a stored Secondary declaration AND a valid stored secondary value."""
    path = new_group(client, sid)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "base_reference_side": "secondary", "secondary_voltage_ll_v": SECONDARY_V}))
    return path


def test_an_existing_secondary_base_is_unchanged_by_unrelated_saves(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    path = legacy_secondary_group(client, sid)
    before_vc, before_prov, before_wave = stored(client, sid), provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert before_prov["verification_state"] == "verified_direct" and before_prov["effective_base_amount"] == pytest.approx(1.0)
    # an edited reference (the unchanged nominal is not re-sent) and the clear-VT writer: the side is omitted from both
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line"}))
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line", "clear_vt": True}))
    after_vc = stored(client, sid)
    for key in ("base_reference_side", "secondary_voltage_ll_v", "nominal_voltage_ll_kv", "base_authority"):
        assert after_vc[key] == before_vc[key], key
    assert after_vc["base_reference_side"] == "secondary" and after_vc["secondary_voltage_ll_v"] == SECONDARY_V
    assert provenance(client, sid, VNAMES[0])["effective_base_amount"] == before_prov["effective_base_amount"]
    assert wave_status(client, sid, VNAMES[0])["values"] == before_wave["values"]            # bit for bit


def test_a_historical_unknown_declaration_is_preserved_by_unrelated_saves(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "")                                       # no side declared: non-strict samples
    path = new_group(client, sid)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line", "nominal_voltage_ll_kv": NOMINAL_KV}))
    assert stored(client, sid)["base_reference_side"] == "unknown"                            # a historical configuration
    before_prov, before_wave = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert before_prov["verification_state"] == "unverified_historical"                       # DEC-210/211 compatibility, unchanged
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_ground"}))    # an unrelated reference edit
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line"}))
    assert stored(client, sid)["base_reference_side"] == "unknown"                            # NOT rewritten to anything
    after_prov, after_wave = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert after_prov["verification_state"] == "unverified_historical" and after_wave["values"] == before_wave["values"]


def test_confirming_a_nominal_on_a_historical_unknown_group_declares_primary(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    path = new_group(client, sid)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line", "nominal_voltage_ll_kv": 132.0}))
    assert stored(client, sid)["base_reference_side"] == "unknown"
    ui_apply_new_nominal(client, path)                                                        # the engineer enters the real nominal
    vc = stored(client, sid)
    assert (vc["nominal_voltage_ll_kv"], vc["base_reference_side"]) == (NOMINAL_KV, "primary")


# ------------------------------------------------------------------------------------------ 11: missing authority
def test_a_required_conversion_without_vt_authority_is_still_refused(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "P")
    path = new_group(client, sid)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "base_reference_side": "secondary", "secondary_voltage_ll_v": SECONDARY_V}))   # legacy Secondary, no nominal
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert (prov["verification_state"], prov["side_refusal_reason"], body["per_unit_status"]) == ("blocked", "vt_authority_unavailable", "base_required")


# ------------------------------------------------------------------------------------------ 13: the auto-base writers
def upload_and_read_auto_voltage_configs(client, fixtures, marker):
    """Upload WITHOUT clearing the groups, so that what the auto-base writer stored is what is read."""
    lines = (fixtures / "synth_measurement_groups.cfg").read_text().splitlines()
    for index in range(2, 11):
        fields = lines[index].split(",")
        if fields[4].strip().lower() == "kv":
            if marker == "S":
                a, b, p, s = float(fields[5]), float(fields[6]), float(fields[10]), float(fields[11])
                fields[5], fields[6] = f"{a * s / p:.6g}", f"{b * s / p:.6g}"
            fields[-1] = marker
            lines[index] = ",".join(fields)
    sid = checked(client.post(ROOT + "/sources", files={
        "cfg_file": ("auto.cfg", io.BytesIO("\n".join(lines).encode()), "application/octet-stream"),
        "dat_file": ("auto.dat", io.BytesIO((fixtures / "synth_measurement_groups.dat").read_bytes()), "application/octet-stream")}), 201)["source_id"]
    groups = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))
    return [g["voltage_config"] for g in groups if g["kind"] == "voltage" and g["voltage_config"]]


def test_the_auto_base_primary_path_declares_a_primary_nominal_base(client, comtrade_fixtures_dir):
    configs = upload_and_read_auto_voltage_configs(client, comtrade_fixtures_dir, "P")
    resolved = [c for c in configs if c["base_authority"] == "auto_resolved" and c["nominal_voltage_ll_kv"] is not None]
    assert resolved and all(c["base_reference_side"] == "primary" and c["secondary_voltage_ll_v"] is None for c in resolved)


# The auto-base Secondary path (finding W-1) is covered by test_pu_dec219_auto_base_w1.py: a Secondary recording no longer gets a legacy Secondary base.
