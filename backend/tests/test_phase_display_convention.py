"""DEC-118: context-specific phase display convention.

Canonical A/B/C (AB/BC/CA) stay the only internal identities. A Measurement
Group / Engineering Context additionally reports how its OWN measurement
spells those phases, so Powerwave-generated notation follows the input
(R/Y/B bay -> VR, VRY) instead of silently switching to A/B/C.

Fixture `phase_convention_mixed` (one source, one workspace):

- KPDN1_VR/VY/VB + IR/IY/IB -> R/Y/B bay
- MCRS_VA/VB/VC + IA/IB/IC  -> A/B/C bay
- AMBG_VB alone             -> undecidable ("B" alone is A/B/C phase B or
                               R/Y/B phase C): canonical fallback, no guess
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.line_to_line_voltage import default_output_name
from app.domain.phase_identity import (
    CANONICAL_PHASE_DISPLAY,
    PHASE_DISPLAY_CANONICAL_FALLBACK,
    PHASE_DISPLAY_ESTABLISHED,
    phase_symbol_text,
    resolve_phase_display_convention,
)
from app.main import create_app

FIXTURE = "phase_convention_mixed"
RYB_SYMBOLS = {"A": "R", "B": "Y", "C": "B", "AB": "RY", "BC": "YB", "CA": "BR"}
ABC_SYMBOLS = {"A": "A", "B": "B", "C": "C", "AB": "AB", "BC": "BC", "CA": "CA"}


# ---------------------------------------------------------------------------
# Pure domain resolver
# ---------------------------------------------------------------------------


class TestResolver:
    def test_ryb_bay_is_established(self):
        display = resolve_phase_display_convention([("A", "R"), ("B", "Y"), ("C", "B")])
        assert (display.convention, display.status) == ("RYB", PHASE_DISPLAY_ESTABLISHED)
        assert display.symbols == RYB_SYMBOLS

    def test_abc_bay_is_established(self):
        display = resolve_phase_display_convention([("A", "A"), ("B", "B"), ("C", "C")])
        assert (display.convention, display.status) == ("ABC", PHASE_DISPLAY_ESTABLISHED)
        assert display.symbols == ABC_SYMBOLS

    def test_currents_and_pairs_count_as_evidence_of_the_same_bay(self):
        display = resolve_phase_display_convention([("A", "R"), ("AB", "RY"), ("C", "B"), ("N", "N")])
        assert display.convention == "RYB"

    def test_convention_fixes_the_full_map_even_for_an_unrecorded_phase(self):
        # R and Y are R/Y/B-only letters, so phase C is "B" even though the
        # bay records no phase-C channel.
        display = resolve_phase_display_convention([("A", "R"), ("B", "Y")])
        assert display.convention == "RYB"
        assert display.symbol("C") == "B"

    def test_lone_b_is_never_enough_evidence(self):
        for members in ([("B", "B")], [("C", "B")]):
            display = resolve_phase_display_convention(members)
            assert display.status == PHASE_DISPLAY_CANONICAL_FALLBACK
            assert display.convention is None
            assert display.symbols == ABC_SYMBOLS

    def test_conflicting_conventions_fall_back(self):
        # e.g. an engineer-built context spanning an R/Y/B and an A/B/C file.
        display = resolve_phase_display_convention([("A", "R"), ("B", "Y"), ("A", "A"), ("C", "C")])
        assert display.status == PHASE_DISPLAY_CANONICAL_FALLBACK

    def test_label_inconsistent_with_the_inferred_convention_falls_back(self):
        # "B" labelled canonical B next to R/Y evidence: not R/Y/B-consistent.
        display = resolve_phase_display_convention([("A", "R"), ("B", "B")])
        assert display.status == PHASE_DISPLAY_CANONICAL_FALLBACK

    def test_member_without_a_source_label_falls_back(self):
        display = resolve_phase_display_convention([("A", "R"), ("B", None)])
        assert display.status == PHASE_DISPLAY_CANONICAL_FALLBACK
        assert "label" in display.reason

    def test_no_resolved_phase_falls_back(self):
        assert resolve_phase_display_convention([]).status == PHASE_DISPLAY_CANONICAL_FALLBACK
        assert resolve_phase_display_convention([("unknown", "B")]).status == PHASE_DISPLAY_CANONICAL_FALLBACK

    def test_l123_is_recognised_but_has_no_display_notation_yet(self):
        display = resolve_phase_display_convention([("A", "L1"), ("B", "L2"), ("C", "L3")])
        assert display.status == PHASE_DISPLAY_CANONICAL_FALLBACK
        assert "L123" in display.reason

    def test_plain_symbols_follow_dec117_fallback_never_underscore(self):
        ryb = resolve_phase_display_convention([("A", "R"), ("B", "Y"), ("C", "B")])
        assert phase_symbol_text("V", "A", ryb) == "VR"
        assert phase_symbol_text("V", "AB", ryb) == "VRY"
        assert phase_symbol_text("V", "CA", ryb) == "VBR"
        assert phase_symbol_text("V", "A") == "VA"
        assert phase_symbol_text("V", "AB", CANONICAL_PHASE_DISPLAY) == "VAB"
        assert all("_" not in phase_symbol_text("V", m, ryb) for m in RYB_SYMBOLS)

    def test_default_name_follows_display_but_is_canonical_without_one(self):
        ryb = resolve_phase_display_convention([("A", "R"), ("B", "Y"), ("C", "B")])
        assert default_output_name("KPDN1", "AB", ryb) == "KPDN1 VRY"
        assert default_output_name("KPDN1", "BC", ryb) == "KPDN1 VYB"
        assert default_output_name("KPDN1", "CA", ryb) == "KPDN1 VBR"
        assert default_output_name("MCRS", "AB") == "MCRS VAB"


# ---------------------------------------------------------------------------
# One workspace, three bays, three outcomes
# ---------------------------------------------------------------------------


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, fixtures_dir, stem):
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO((fixtures_dir / f"{stem}.cfg").read_bytes()), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO((fixtures_dir / f"{stem}.dat").read_bytes()), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


@pytest.fixture
def ws(client, comtrade_fixtures_dir):
    source_id = _upload(client, "ws-pd", comtrade_fixtures_dir, FIXTURE)
    contexts = {c["display_name"]: c for c in client.get("/api/v1/workspaces/ws-pd/engineering-contexts").json()}
    return {"id": "ws-pd", "source_id": source_id, "contexts": contexts}


def _readiness(client, ws_id):
    resp = client.get(f"/api/v1/workspaces/{ws_id}/calculated-channels/line-to-line-voltage/readiness")
    assert resp.status_code == 200, resp.text
    return {r["display_name"]: r for r in resp.json()}


def _create_ll(client, ws_id, context_id, output, **extra):
    return client.post(
        f"/api/v1/workspaces/{ws_id}/calculated-channels/line-to-line-voltage",
        json={"engineering_context_id": context_id, "output": output, **extra},
    )


class TestEngineeringContextReportsItsConvention:
    def test_each_bay_reports_its_own_convention_in_one_workspace(self, ws):
        kpdn, mcrs = ws["contexts"]["KPDN1"], ws["contexts"]["MCRS"]
        assert kpdn["phase_display"] == {
            "convention": "RYB", "status": "established", "symbols": RYB_SYMBOLS, "reason": None,
        }
        assert mcrs["phase_display"] == {
            "convention": "ABC", "status": "established", "symbols": ABC_SYMBOLS, "reason": None,
        }

    def test_lone_vb_bay_is_not_guessed(self, ws):
        ambg = ws["contexts"]["AMBG"]
        assert ambg["status"] == "needs_review"
        assert [m["phase"] for m in ambg["members"]] == ["unknown"]
        assert ambg["phase_display"]["status"] == "canonical_fallback"
        assert ambg["phase_display"]["convention"] is None
        assert ambg["phase_display"]["symbols"] == ABC_SYMBOLS

    def test_canonical_member_phases_are_unchanged(self, ws):
        kpdn = {m["channel_ref"]["channel_name"]: (m["phase"], m["original_phase_label"]) for m in ws["contexts"]["KPDN1"]["members"]}
        assert kpdn["KPDN1_VR"] == ("A", "R")
        assert kpdn["KPDN1_VY"] == ("B", "Y")
        assert kpdn["KPDN1_VB"] == ("C", "B")
        mcrs = {m["channel_ref"]["channel_name"]: m["phase"] for m in ws["contexts"]["MCRS"]["members"]}
        assert mcrs["MCRS_VB"] == "B"  # the same raw "B" is canonical B here, canonical C in KPDN1

    def test_convention_is_derived_on_read_so_an_engineer_correction_applies(self, client, ws):
        kpdn = ws["contexts"]["KPDN1"]
        vb_ref = next(m["channel_ref"] for m in kpdn["members"] if m["channel_ref"]["channel_name"] == "KPDN1_VB")
        # An engineer re-labels KPDN1_VB as canonical B with label "B" -- no
        # longer R/Y/B-consistent next to VY, so the bay stops claiming R/Y/B.
        resp = client.patch(
            f"/api/v1/workspaces/{ws['id']}/engineering-contexts/{kpdn['id']}/member-phase",
            json={"channel_ref": vb_ref, "phase": "B", "original_phase_label": "B"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["phase_display"]["status"] == "canonical_fallback"

    def test_context_spanning_two_conventions_falls_back(self, client, ws):
        members = [
            m for name in ("KPDN1", "MCRS") for m in ws["contexts"][name]["members"]
            if m["channel_ref"]["channel_name"] in ("KPDN1_VR", "KPDN1_VY", "MCRS_VC")
        ]
        # A channel belongs to at most one context: release the detected bays.
        for name in ("KPDN1", "MCRS"):
            deleted = client.delete(f"/api/v1/workspaces/{ws['id']}/engineering-contexts/{ws['contexts'][name]['id']}")
            assert deleted.status_code == 204, deleted.text
        resp = client.post(
            f"/api/v1/workspaces/{ws['id']}/engineering-contexts",
            json={"display_name": "MIXED", "members": members},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["phase_display"]["status"] == "canonical_fallback"


class TestLineToLineFollowsTheBayConvention:
    def test_readiness_carries_the_convention(self, client, ws):
        readiness = _readiness(client, ws["id"])
        assert readiness["KPDN1"]["phase_display"]["symbols"] == RYB_SYMBOLS
        assert readiness["MCRS"]["phase_display"]["symbols"] == ABC_SYMBOLS
        assert readiness["AMBG"]["phase_display"]["status"] == "canonical_fallback"
        # Role and output keys stay canonical.
        assert set(readiness["KPDN1"]["roles"]) == {"Va", "Vb", "Vc"}
        assert set(readiness["KPDN1"]["outputs"]) == {"AB", "BC", "CA", "all_three"}

    def test_ambiguous_bay_messages_use_canonical_fallback(self, client, ws):
        roles = _readiness(client, ws["id"])["AMBG"]["roles"]
        assert roles["Va"]["message"].startswith("VA:")

    def test_default_names_follow_each_bay_while_arithmetic_stays_canonical(self, client, ws):
        kpdn = _create_ll(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "all_three")
        mcrs = _create_ll(client, ws["id"], ws["contexts"]["MCRS"]["id"], "all_three")
        assert kpdn.status_code == 201, kpdn.text
        assert mcrs.status_code == 201, mcrs.text
        kpdn_channels, mcrs_channels = kpdn.json()["channels"], mcrs.json()["channels"]

        assert [c["name"] for c in kpdn_channels] == ["KPDN1 VRY", "KPDN1 VYB", "KPDN1 VBR"]
        assert [c["name"] for c in mcrs_channels] == ["MCRS VAB", "MCRS VBC", "MCRS VCA"]
        for channels in (kpdn_channels, mcrs_channels):
            assert [c["phase_member"] for c in channels] == ["AB", "BC", "CA"]
            assert all(c["voltage_representation"] == "line_to_line" for c in channels)
            assert [c["parameters"]["pair"] for c in channels] == ["AB", "BC", "CA"]
        assert kpdn_channels[0]["parameters"]["phase_display"]["convention"] == "RYB"
        assert mcrs_channels[0]["parameters"]["phase_display"]["convention"] == "ABC"

        registry = client.app.state.workspace_registry.get(ws["id"], ws["source_id"]).record.waveform_data
        calc = client.app.state.calculated_channel_registry
        vr, vy, vb = (registry[n].to_numpy() for n in ("KPDN1_VR", "KPDN1_VY", "KPDN1_VB"))
        np.testing.assert_array_equal(calc.get(ws["id"], kpdn_channels[0]["id"]).values, vr - vy)  # AB = A - B
        np.testing.assert_array_equal(calc.get(ws["id"], kpdn_channels[1]["id"]).values, vy - vb)  # BC = B - C
        np.testing.assert_array_equal(calc.get(ws["id"], kpdn_channels[2]["id"]).values, vb - vr)  # CA = C - A

    def test_custom_names_are_kept_verbatim(self, client, ws):
        resp = _create_ll(client, ws["id"], ws["contexts"]["KPDN1"]["id"], "AB", names={"AB": "Backup VAB Check"})
        assert resp.status_code == 201, resp.text
        assert resp.json()["channels"][0]["name"] == "Backup VAB Check"
        assert resp.json()["channels"][0]["phase_member"] == "AB"

    def test_existing_channels_are_not_renamed(self, client, ws):
        created = _create_ll(client, ws["id"], ws["contexts"]["MCRS"]["id"], "AB").json()["channels"][0]
        _readiness(client, ws["id"])
        listed = client.get(f"/api/v1/workspaces/{ws['id']}/calculated-channels").json()
        assert [c["name"] for c in listed] == [created["name"]] == ["MCRS VAB"]


class TestComplianceFollowsTheGroupConvention:
    def _groups(self, client, ws_id):
        return {g["display_name"]: g for g in client.get(f"/api/v1/workspaces/{ws_id}/compliance/voltage/measurement-groups").json()}

    def _measure(self, client, ws_id, group_id, quantity_id):
        resp = client.get(
            f"/api/v1/workspaces/{ws_id}/compliance/voltage/measurement",
            params={"measurement_group_id": group_id, "quantity_id": quantity_id},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _group_for(self, groups, prefix):
        return next(g for name, g in groups.items() if name.startswith(prefix))

    def test_resolved_measurement_carries_its_group_convention(self, client, ws):
        groups = self._groups(client, ws["id"])
        kpdn = self._measure(client, ws["id"], self._group_for(groups, "KPDN1")["id"], "phase_a_lg_rms")
        mcrs = self._measure(client, ws["id"], self._group_for(groups, "MCRS")["id"], "phase_a_lg_rms")
        assert kpdn["phase_display"]["symbols"] == RYB_SYMBOLS
        assert mcrs["phase_display"]["symbols"] == ABC_SYMBOLS
        # Canonical API values are unchanged: role A, display_name "Va".
        assert [(r["role"], r["display_name"], r["channel_name"]) for r in kpdn["resolved_roles"]] == [("A", "Va", "KPDN1_VR")]
        assert [(r["role"], r["display_name"], r["channel_name"]) for r in mcrs["resolved_roles"]] == [("A", "Va", "MCRS_VA")]

    def test_ambiguous_group_is_not_guessed(self, client, ws):
        groups = self._groups(client, ws["id"])
        ambg = self._measure(client, ws["id"], self._group_for(groups, "AMBG")["id"], "phase_b_lg_rms")
        assert ambg["phase_display"]["status"] == "canonical_fallback"
        assert ambg["status"] == "missing_inputs"
        assert ambg["missing"] == ["Vb"]  # canonical API value
        assert "Missing: VB." in ambg["message"]
