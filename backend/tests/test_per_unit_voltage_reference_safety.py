"""VLT-REF-001: Voltage PU reference-side safety.

Mirrors the LIM-001 test pattern from test_per_unit_reference_safety.py:
same COMTRADE fixture, but modifying Voltage channel PS markers (rows 1-9
of synth_measurement_groups.cfg) to exercise primary/secondary mismatch
detection, compatibility classification, and the full consumer surface.

PU-MIG S2 (owner-approved, S0 intentional changes IC-1..IC-4): when Recording Details establishes the SAMPLE side strictly
(a P/S declaration, or an engineer's correction), a known Primary/Secondary mismatch is no longer a flat block -- the base is
placed on the samples' side with the group's own authoritative VT. It stays blocked only when no authoritative ratio exists. These
tests keep every original assertion: the "incompatible" cases now give the group the evidence that makes its ratio non-authoritative
(`SECONDARY_V`: the VT secondary the CFG itself declares, 1.0 kV, which contradicts the 110 V `auto_nominal` default -- decision
D-7), and the new rows state the converted outcomes. A sample side that is NOT strict (`C`, empty) keeps the historical Unverified
behaviour bit for bit.
"""
from __future__ import annotations

import io

import pytest

from tests.test_current_effective_base_inheritance import (
    client, checked, ROOT, WS, configuration_snapshot,
)

# Voltage channels in synth_measurement_groups.cfg (rows 3-11, 0-indexed 2-10)
# Phase channels: rows 2,3,4 (N275_VR/VY/VB) and rows 5,6,7 (S132_VR/VY/VB)
# Line-to-line channels: rows 8,9,10 (E275_VRY/VYB/VBR)
VNAMES = ["N275_VR", "N275_VY"]


def recording(client, fixtures, marker="P"):
    """Upload synth_measurement_groups.cfg with all Voltage rows rewritten
    to the requested PS marker.

    IEEE C37.111 / IEC 60255-24: PS is the engineering-value scale identifier,
    not the physical acquisition side.
      PS="P": a×raw+b produces Primary-referred values (e.g. kV primary).
      PS="S": a×raw+b produces Secondary-referred values (e.g. kV or V secondary).

    When marker="S", the scaling factor `a` is also rescaled by secondary/primary so
    that the resulting COMTRADE file is internally consistent: the scaled values are
    genuinely Secondary-referred. For N275_VR (a=158.77 kV, primary=275.0, secondary=1.0):
      a_secondary = 158.77 × (1.0/275.0) = 0.577345 kV  (secondary L-G at nominal)
    The VT secondary circuit L-L voltage = secondary=1.0 kV = 1000 V.
    For other markers (P, C, empty), only the pors field is changed and `a` is preserved.
    """
    lines = (fixtures / "synth_measurement_groups.cfg").read_text().splitlines()
    for index in range(2, 11):   # rows 1-9 are Voltage channels (kV)
        fields = lines[index].split(",")
        if fields[4].strip().lower() == "kv":
            if marker == "S":
                # Rescale a and b by secondary/primary: produces genuinely Secondary-referred values.
                # Both scaling coefficients must be rescaled (spec §1). All fixture channels have
                # b=0.0, so the b rescaling is a no-op here but required for general correctness.
                a_primary = float(fields[5])
                b_primary = float(fields[6])
                primary = float(fields[10])
                secondary = float(fields[11])
                fields[5] = f"{a_primary * secondary / primary:.6g}"
                fields[6] = f"{b_primary * secondary / primary:.6g}"
            fields[-1] = marker
            lines[index] = ",".join(fields)
    sid = checked(client.post(ROOT + "/sources", files={
        "cfg_file": ("vlt_ref.cfg", io.BytesIO("\n".join(lines).encode()), "application/octet-stream"),
        "dat_file": ("vlt_ref.dat", io.BytesIO((fixtures / "synth_measurement_groups.dat").read_bytes()), "application/octet-stream"),
    }), 201)["source_id"]
    # Remove all auto-detected groups (want clean slate for each test)
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    for group in checked(client.get(url)):
        assert client.delete(url + "/" + group["id"]).status_code == 204
    return sid


#: The VT secondary circuit L-L voltage the fixture's CFG declares (secondary=1.0 kV), as a stored secondary base.
SECONDARY_V = 1000.0


def setup_voltage_base(client, sid, base_side="primary", scope="group", secondary_v=None):
    """Configure a Voltage Measurement Group with a base_reference_side."""
    if scope == "group":
        url = f"{ROOT}/sources/{sid}/measurement-groups"
        group = checked(client.post(url, json={
            "kind": "voltage", "display_name": "VLT ref test", "status": "confirmed",
            "channel_refs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in VNAMES],
        }), 201)
        path = url + "/" + group["id"] + "/voltage-config"
        body: dict = {
            "nominal_voltage_ll_kv": 275,
            "reference_mode": "manual",
            "reference_override": "line_to_line",
            "base_reference_side": base_side,
        }
        if base_side == "secondary" or secondary_v is not None:
            # Fixture: secondary=1.0 kV (LL) in the CFG primary/secondary ratio fields.
            # VT secondary circuit L-L voltage = 1.0 kV = 1000 V.
            body["secondary_voltage_ll_v"] = 1000.0 if secondary_v is None else secondary_v
        checked(client.put(path, json=body))
        return path, group["id"]
    else:
        path = f"{ROOT}/per-unit/sources/{sid}"
        checked(client.put(path, json={
            "voltage_base_value": 275,
            "voltage_reference_mode": "manual",
            "voltage_reference_override": "line_to_line",
            "voltage_base_reference_side": base_side,
        }))
        return path, None


def wave_status(client, sid, channel_name):
    return checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={
        "channel_name": channel_name, "unit_mode": "per_unit",
    }))


def provenance(client, sid, channel_name):
    return checked(client.get(f"{ROOT}/sources/{sid}/per-unit-resolution", params={
        "channel_name": channel_name,
    }))


def cursor_status(client, sid, channel_name):
    return checked(client.post(f"{ROOT}/sources/{sid}/cursor-values", json={
        "analog_channel_names": [channel_name],
        "cursor_a_time": 0,
        "cursor_b_time": 0.0001,
        "unit_mode": "per_unit",
    }))["channels"][0]


def peak_status(client, sid, channel_name):
    return checked(client.post(f"{ROOT}/sources/{sid}/peak-values", json={
        "start_time": 0, "end_time": 0.001, "unit_mode": "per_unit",
        "requests": [{"channel_name": channel_name, "mode": "max"}],
    }))["results"][0]


def all_consumer_statuses(client, sid, channel_name):
    return [
        wave_status(client, sid, channel_name),
        cursor_status(client, sid, channel_name),
        peak_status(client, sid, channel_name),
        checked(client.post(f"{ROOT}/sources/{sid}/annotation-anchor", json={
            "channel_name": channel_name, "approximate_elapsed_seconds": 0, "unit_mode": "per_unit",
        })),
    ]


# ---------------------------------------------------------------------------
# Core classifier (apply_voltage_reference) — pure unit tests
# ---------------------------------------------------------------------------

class TestApplyVoltageReference:
    """Direct unit tests for the apply_voltage_reference classifier."""

    def _classify(self, measurement_side, base_side):
        from app.domain.per_unit import STATUS_CONFIGURED, PerUnitResolution
        from app.domain.per_unit_reference import apply_voltage_reference
        resolution = PerUnitResolution(
            status=STATUS_CONFIGURED, profile_id="g1",
            base_amount=275_000.0, base_unit="V", reason=None,
        )
        return apply_voltage_reference(resolution, measurement_side, base_side)

    def test_primary_primary_compatible(self):
        r = self._classify("primary", "primary")
        assert r.reference_compatibility == "compatible"
        assert r.status == "configured"

    def test_secondary_secondary_compatible(self):
        r = self._classify("secondary", "secondary")
        assert r.reference_compatibility == "compatible"
        assert r.status == "configured"

    def test_secondary_primary_incompatible(self):
        r = self._classify("secondary", "primary")
        assert r.reference_compatibility == "incompatible"
        assert r.status == "base_required"
        assert "voltage_reference_side_incompatible" in r.reason

    def test_primary_secondary_incompatible(self):
        r = self._classify("primary", "secondary")
        assert r.reference_compatibility == "incompatible"
        assert r.status == "base_required"

    def test_unknown_base_unverified(self):
        r = self._classify("primary", "unknown")
        assert r.reference_compatibility == "unverified"
        assert r.status == "configured"

    def test_unknown_measurement_unverified(self):
        r = self._classify("unknown", "primary")
        assert r.reference_compatibility == "unverified"
        assert r.status == "configured"

    def test_both_unknown_unverified(self):
        r = self._classify("unknown", "unknown")
        assert r.reference_compatibility == "unverified"
        assert r.status == "configured"

    def test_sides_set_on_resolution(self):
        r = self._classify("secondary", "secondary")
        assert r.measurement_side == "secondary"
        assert r.base_reference_side == "secondary"

    def test_existing_base_required_not_demoted_to_configured(self):
        from app.domain.per_unit import STATUS_BASE_REQUIRED, PerUnitResolution
        from app.domain.per_unit_reference import apply_voltage_reference
        resolution = PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id="g1",
            base_amount=None, base_unit=None, reason="base_not_configured",
        )
        r = apply_voltage_reference(resolution, "primary", "primary")
        # compatible classification, but status was already base_required for
        # a different reason — we do NOT upgrade it back to configured
        assert r.reference_compatibility == "compatible"
        assert r.status == STATUS_BASE_REQUIRED
        assert r.reason == "base_not_configured"


# ---------------------------------------------------------------------------
# Integration: Measurement Group path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marker,base_side,secondary_v,expected_compat,eligible", [
    ("P", "primary", None, "compatible", True),
    ("S", "secondary", None, "compatible", True),
    ("P", "secondary", None, "incompatible", False),
    ("S", "primary", SECONDARY_V, "incompatible", False),     # no authoritative ratio: the original block, unchanged
    ("C", "primary", None, "unverified", True),
    ("", "primary", None, "unverified", True),
    ("C", "unknown", None, "unverified", True),               # historical Unverified, bit for bit
    ("", "unknown", None, "unverified", True),
    # PU-MIG S2 intentional changes (S0 IC-1/IC-2/IC-3): a STRICT sample side is the proof, the stored side no longer is.
    ("S", "primary", None, "compatible", True),               # IC-1: converted with the group's auto-derived VT
    ("P", "unknown", None, "compatible", True),               # IC-3: same number, label only
    ("S", "unknown", None, "compatible", True),               # IC-2: converted (was an unverified 0.0004-pu class)
])
def test_voltage_group_reference_safety(client, comtrade_fixtures_dir, marker, base_side, secondary_v, expected_compat, eligible):
    """Group path: the PS-marker x base_side matrix (strict sides convert or block; non-strict stay historical)."""
    sid = recording(client, comtrade_fixtures_dir, marker)
    setup_voltage_base(client, sid, base_side, scope="group", secondary_v=secondary_v)
    prov = provenance(client, sid, VNAMES[0])
    assert prov["reference_compatibility"] == expected_compat
    expected_status = "configured" if eligible else "base_required"
    assert prov["status"] == expected_status
    # Every consumer surface must carry the same status
    for body in all_consumer_statuses(client, sid, VNAMES[0]):
        assert body["per_unit_status"] == expected_status
        assert body["per_unit_reference_compatibility"] == expected_compat


@pytest.mark.parametrize("marker,base_side,expected_compat,eligible", [
    ("P", "primary", "compatible", True),
    ("S", "primary", "incompatible", False),      # a Source Default has no VT authority: a Secondary sample stays blocked
    ("C", "primary", "unverified", True),
    ("C", "unknown", "unverified", True),
    ("P", "unknown", "compatible", True),         # PU-MIG S2 IC-3: a strict Primary sample, same number, label only
])
def test_voltage_source_default_reference_safety(client, comtrade_fixtures_dir, marker, base_side, expected_compat, eligible):
    """Source Default path exercises voltage_base_reference_side on the profile."""
    sid = recording(client, comtrade_fixtures_dir, marker)
    setup_voltage_base(client, sid, base_side, scope="default")
    prov = provenance(client, sid, VNAMES[0])
    assert prov["reference_compatibility"] == expected_compat
    expected_status = "configured" if eligible else "base_required"
    assert prov["status"] == expected_status


def test_voltage_group_base_reference_side_persists_through_api(client, comtrade_fixtures_dir):
    """base_reference_side round-trips through the voltage-config PUT and GET."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    _path, group_id = setup_voltage_base(client, sid, "secondary", scope="group")
    group_out = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups/{group_id}"))
    assert group_out["voltage_config"]["base_reference_side"] == "secondary"


def test_voltage_source_default_base_reference_side_persists_through_api(client, comtrade_fixtures_dir):
    """voltage_base_reference_side round-trips through the per-unit PUT and GET."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    setup_voltage_base(client, sid, "secondary", scope="default")
    out = checked(client.get(f"{ROOT}/per-unit/sources/{sid}"))
    assert out["voltage_base_reference_side"] == "secondary"


def test_voltage_incompatible_does_not_mutate_stored_state(client, comtrade_fixtures_dir):
    """Incompatible reference must not alter the stored configuration."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    before = configuration_snapshot(client)
    prov = provenance(client, sid, VNAMES[0])
    assert prov["status"] == "base_required"
    after = configuration_snapshot(client)
    assert before == after


def test_voltage_reference_side_change_takes_effect_immediately(client, comtrade_fixtures_dir):
    """Changing base_reference_side from incompatible to compatible resolves inline.
    recording(marker="S") produces genuinely Secondary-referred values (a rescaled by
    secondary/primary). After correcting base to "secondary" with the matching
    secondary_voltage_ll_v, the classifier yields "compatible" and PU is enabled."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    path, _gid = setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    prov = provenance(client, sid, VNAMES[0])
    assert prov["status"] == "base_required"
    # Fix: set base to secondary with the VT secondary circuit L-L voltage from the fixture
    # (secondary=1.0 kV in the CFG → secondary_voltage_ll_v=1000 V).
    checked(client.put(path, json={
        "nominal_voltage_ll_kv": 275,
        "reference_mode": "manual",
        "reference_override": "line_to_line",
        "base_reference_side": "secondary",
        "secondary_voltage_ll_v": 1000.0,
    }))
    prov2 = provenance(client, sid, VNAMES[0])
    assert prov2["status"] == "configured"
    assert prov2["reference_compatibility"] == "compatible"


def test_voltage_incompatible_uses_raw_value_not_pu(client, comtrade_fixtures_dir):
    """Waveform endpoint must return raw engineering values when incompatible."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    wave = wave_status(client, sid, VNAMES[0])
    assert wave["per_unit_status"] == "base_required"
    # Raw unit, not "pu"
    assert wave["unit"] != "pu"


def test_voltage_unverified_allows_pu_conversion(client, comtrade_fixtures_dir):
    """Unknown sides produce unverified compatibility but still convert to PU. (An undeclared recording side: a strict
    `P` against an Unknown base is now `compatible`, PU-MIG S2 IC-3.)"""
    sid = recording(client, comtrade_fixtures_dir, "C")
    setup_voltage_base(client, sid, "unknown", scope="group")
    prov = provenance(client, sid, VNAMES[0])
    assert prov["status"] == "configured"
    assert prov["reference_compatibility"] == "unverified"
    wave = wave_status(client, sid, VNAMES[0])
    assert wave["per_unit_status"] == "configured"
    assert wave["unit"] == "pu"


def test_voltage_reference_safety_coverage_unverified_count(client, comtrade_fixtures_dir):
    """Coverage endpoint reports unverified_reference_count for unverified Voltage."""
    sid = recording(client, comtrade_fixtures_dir, "C")
    setup_voltage_base(client, sid, "primary", scope="group")
    cov = checked(client.get(f"{ROOT}/per-unit/sources/{sid}/coverage"))
    assert cov["unverified_reference_count"] > 0


def test_voltage_incompatible_coverage_needs_configuration(client, comtrade_fixtures_dir):
    """An incompatible Voltage channel contributes to needs_configuration_count."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    cov = checked(client.get(f"{ROOT}/per-unit/sources/{sid}/coverage"))
    assert cov["needs_configuration_count"] > 0


def test_voltage_invalid_base_reference_side_rejected(client, comtrade_fixtures_dir):
    """API must reject unknown base_reference_side values with 400."""
    sid = recording(client, comtrade_fixtures_dir, "P")
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    group = checked(client.post(url, json={
        "kind": "voltage", "display_name": "Invalid side test", "status": "confirmed",
        "channel_refs": [{"kind": "source", "source_id": sid, "channel_name": VNAMES[0]}],
    }), 201)
    path = url + "/" + group["id"] + "/voltage-config"
    r = client.put(path, json={
        "nominal_voltage_ll_kv": 275,
        "reference_mode": "auto",
        "base_reference_side": "tertiary",
    })
    assert r.status_code == 422


def test_voltage_lgl_and_ll_channels_both_classified(client, comtrade_fixtures_dir):
    """Both L-G (N275_VR) and L-L (E275_VRY) channels go through the reference gate."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    # Create a group containing both L-G and L-L voltage channels
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    group = checked(client.post(url, json={
        "kind": "voltage", "display_name": "LG+LL test", "status": "confirmed",
        "channel_refs": [
            {"kind": "source", "source_id": sid, "channel_name": "N275_VR"},
            {"kind": "source", "source_id": sid, "channel_name": "E275_VRY"},
        ],
    }), 201)
    path = url + "/" + group["id"] + "/voltage-config"
    checked(client.put(path, json={
        "nominal_voltage_ll_kv": 275,
        "reference_mode": "manual",
        "reference_override": "line_to_line",
        "base_reference_side": "primary",
        "secondary_voltage_ll_v": SECONDARY_V,
    }))
    for ch in ("N275_VR", "E275_VRY"):
        prov = provenance(client, sid, ch)
        assert prov["reference_compatibility"] == "incompatible"
        assert prov["status"] == "base_required"


def test_voltage_current_lim001_unaffected(client, comtrade_fixtures_dir):
    """LIM-001 regression: Current channels still correctly classified."""
    from tests.test_per_unit_reference_safety import recording as cur_recording, setup_base, assert_consumers, NAMES
    sid = cur_recording(client, comtrade_fixtures_dir, "S")
    setup_base(client, sid, "group_manual", "secondary")
    assert_consumers(client, sid, name=NAMES[0], compatible="compatible")


def test_voltage_group_path_takes_precedence_over_source_default(client, comtrade_fixtures_dir):
    """When both a Measurement Group and Source Default are configured,
    the Group path's base_reference_side wins.
    recording(marker="S") produces genuinely Secondary-referred values; the Group
    declares secondary with the correct VT circuit voltage → "compatible"."""
    sid = recording(client, comtrade_fixtures_dir, "S")
    # Source Default says primary (incompatible with Secondary-referred recording)
    setup_voltage_base(client, sid, "primary", scope="default")
    # Group says secondary with matching secondary_voltage_ll_v (compatible)
    setup_voltage_base(client, sid, "secondary", scope="group")
    prov = provenance(client, sid, VNAMES[0])
    # Group wins: secondary vs secondary = compatible
    assert prov["reference_compatibility"] == "compatible"
    assert prov["status"] == "configured"
