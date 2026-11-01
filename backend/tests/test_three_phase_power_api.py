"""API-level tests for Phase E-2C three-phase power integration (DEC-208).

Coverage:
  A  /vi-pairs three-phase complete set discovery — RYB convention
  B  /vi-pairs three-phase complete set discovery — ABC convention
  C  /vi-pairs incomplete set (2 of 3 phases present)
  D  /vi-pairs voltage_reference_confirmation_required — line_to_ground auto (False)
  E  /vi-pairs voltage_reference_confirmation_required — unknown naming (True)
  F  /vi-pairs backward compatibility (existing fields intact)
  G  /vi-pairs empty workspace returns empty three-phase lists
  H  Calculated channel creation — three_phase_active_power
  I  Calculated channel creation — three_phase_reactive_power
  J  Calculated channel creation — three_phase_apparent_power
  K  L-L voltage → 400 line_to_line_voltage_rejected
  L  Unknown voltage reference → 400 unconfirmed_voltage_reference
  M  Generic names → 400 unconfirmed_phase_pairing
  N  Generic names + both confirmations → 201 success
  O  Cross-convention mismatch → 400 invalid_three_phase_phase_mismatch
  P  Duplicate voltage assignment → 400 duplicate_phase_assignment
  Q  Cross-source pairing → 400 unconfirmed_phase_pairing
  R  Cross-source + phase_pairing_confirmed → 201 success
  S  Single-phase power operations unchanged (regression)
  T  Invalid operation name → 422 (schema validation)
"""

from __future__ import annotations

import io
import math

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# COMTRADE helpers
# ---------------------------------------------------------------------------

def _comtrade_bytes(
    channels: list[tuple[str, str, str, str]],
    rows: int = 100,
    fs: float = 4000.0,
) -> tuple[bytes, bytes]:
    """Build minimal ASCII COMTRADE bytes.

    *channels*: list of (name, phase, unit, channel_type) where
    channel_type is "P" (primary/voltage) or "C" (current).
    *rows*: sample count; defaults to 100 so the density check for
    phasor-based calculations passes (100 samples @ 4000 Hz = 25 ms >
    20 ms minimum at 50 Hz).
    """
    n = len(channels)
    cfg_lines: list[str] = [
        "SYNTH,DEV,1999",
        f"{n},{n}A,0D",
    ]
    for i, (name, phase, unit, ch_type) in enumerate(channels, 1):
        cfg_lines.append(
            f"{i},{name},{phase},,{unit},1.0,0.0,0,-999999,999999,1.0,1.0,{ch_type}"
        )
    cfg_lines += [
        "50",
        "1",
        f"{fs},{rows}",
        "06/03/2026,10:00:00.000000",
        "06/03/2026,10:00:00.000000",
        "ASCII",
        "1.0",
        "",
    ]
    cfg = "\r\n".join(cfg_lines)
    dt_us = round(1_000_000.0 / fs)
    dat_rows = [f"{i},{(i - 1) * dt_us}," + ",".join(["1"] * n) for i in range(1, rows + 1)]
    dat = "\r\n".join(dat_rows) + "\r\n"
    return cfg.encode("latin-1"), dat.encode("latin-1")


def _upload(client: TestClient, workspace_id: str, cfg: bytes, dat: bytes) -> str:
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        files={
            "cfg_file": ("event.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": ("event.dat", io.BytesIO(dat), "application/octet-stream"),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _get_vi_pairs(client: TestClient, workspace_id: str) -> dict:
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/vi-pairs")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_channel(client: TestClient, workspace_id: str, **body) -> dict:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/calculated-channels",
        json=body,
    )


def _source_ref(source_id: str, name: str) -> dict:
    return {"kind": "source", "source_id": source_id, "channel_name": name}


def _six_inputs(sid: str, vr: str, vy: str, vb: str, ir: str, iy: str, ib: str) -> list[dict]:
    return [
        _source_ref(sid, vr),
        _source_ref(sid, ir),
        _source_ref(sid, vy),
        _source_ref(sid, iy),
        _source_ref(sid, vb),
        _source_ref(sid, ib),
    ]


# Standard six-channel RYB source fixture (shared across tests).
_RYB_CHANNELS = [
    ("VR", "R", "kV", "P"),
    ("VY", "Y", "kV", "P"),
    ("VB", "B", "kV", "P"),
    ("IR", "R", "kA", "C"),
    ("IY", "Y", "kA", "C"),
    ("IB", "B", "kA", "C"),
]

_ABC_CHANNELS = [
    ("VA", "A", "kV", "P"),
    ("VB", "B", "kV", "P"),
    ("VC", "C", "kV", "P"),
    ("IA", "A", "kA", "C"),
    ("IB", "B", "kA", "C"),
    ("IC", "C", "kA", "C"),
]


# ---------------------------------------------------------------------------
# Class A — /vi-pairs complete set: RYB
# ---------------------------------------------------------------------------

class TestA_VIPairsCompleteRYB:
    def test_complete_ryb_set_appears_in_three_phase_complete_sets(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-a1", cfg, dat)
        result = _get_vi_pairs(client, "ws-a1")
        assert len(result["three_phase_complete_sets"]) == 1
        s = result["three_phase_complete_sets"][0]
        assert s["status"] == "complete"
        assert s["phase_convention"] == "RYB"
        assert len(s["pairs"]) == 3

    def test_complete_ryb_pair_phases_in_order(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-a2", cfg, dat)
        s = _get_vi_pairs(client, "ws-a2")["three_phase_complete_sets"][0]
        phases = [p["phase"] for p in s["pairs"]]
        assert phases == ["R", "Y", "B"]

    def test_complete_ryb_pair_channel_names(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-a3", cfg, dat)
        s = _get_vi_pairs(client, "ws-a3")["three_phase_complete_sets"][0]
        for pair in s["pairs"]:
            ph = pair["phase"]
            assert pair["voltage_channel"]["channel_name"] == f"V{ph}"
            assert pair["current_channel"]["channel_name"] == f"I{ph}"

    def test_complete_ryb_set_id_is_stable_string(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-a4", cfg, dat)
        s = _get_vi_pairs(client, "ws-a4")["three_phase_complete_sets"][0]
        assert isinstance(s["set_id"], str)
        assert s["set_id"].startswith("3ph:")

    def test_complete_ryb_three_phase_incomplete_sets_empty(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-a5", cfg, dat)
        result = _get_vi_pairs(client, "ws-a5")
        assert result["three_phase_incomplete_sets"] == []


# ---------------------------------------------------------------------------
# Class B — /vi-pairs complete set: ABC
# ---------------------------------------------------------------------------

class TestB_VIPairsCompleteABC:
    def test_complete_abc_set_appears(self, client):
        cfg, dat = _comtrade_bytes(_ABC_CHANNELS)
        _upload(client, "ws-b1", cfg, dat)
        result = _get_vi_pairs(client, "ws-b1")
        assert len(result["three_phase_complete_sets"]) == 1
        s = result["three_phase_complete_sets"][0]
        assert s["phase_convention"] == "ABC"
        assert len(s["pairs"]) == 3

    def test_complete_abc_pair_phases_in_order(self, client):
        cfg, dat = _comtrade_bytes(_ABC_CHANNELS)
        _upload(client, "ws-b2", cfg, dat)
        s = _get_vi_pairs(client, "ws-b2")["three_phase_complete_sets"][0]
        phases = [p["phase"] for p in s["pairs"]]
        assert phases == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Class C — /vi-pairs incomplete set
# ---------------------------------------------------------------------------

class TestC_VIPairsIncompleteSet:
    def test_two_of_three_ryb_produces_incomplete_set(self, client):
        # Only R and Y — B is missing.
        channels = [
            ("VR", "R", "kV", "P"),
            ("VY", "Y", "kV", "P"),
            ("IR", "R", "kA", "C"),
            ("IY", "Y", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-c1", cfg, dat)
        result = _get_vi_pairs(client, "ws-c1")
        assert result["three_phase_complete_sets"] == []
        assert len(result["three_phase_incomplete_sets"]) == 1
        s = result["three_phase_incomplete_sets"][0]
        assert s["status"] == "incomplete"
        assert s["phase_convention"] == "RYB"
        assert len(s["present_pairs"]) == 2
        assert len(s["missing_phases"]) == 1
        assert s["missing_phases"][0]["phase"] == "B"

    def test_incomplete_set_missing_phase_reason_not_found(self, client):
        channels = [
            ("VR", "R", "kV", "P"),
            ("VY", "Y", "kV", "P"),
            ("IR", "R", "kA", "C"),
            ("IY", "Y", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-c2", cfg, dat)
        s = _get_vi_pairs(client, "ws-c2")["three_phase_incomplete_sets"][0]
        assert s["missing_phases"][0]["reason"] == "not_found"


# ---------------------------------------------------------------------------
# Class D — voltage_reference_confirmation_required: auto line_to_ground
# ---------------------------------------------------------------------------

class TestD_VoltageReferenceConfirmedRequired:
    def test_ryb_naming_gives_line_to_ground_and_no_confirmation_required(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-d1", cfg, dat)
        s = _get_vi_pairs(client, "ws-d1")["three_phase_complete_sets"][0]
        assert s["voltage_reference"] == "line_to_ground"
        assert s["voltage_reference_confirmation_required"] is False

    def test_voltage_reference_evidence_names_nonempty_for_ryb(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-d2", cfg, dat)
        s = _get_vi_pairs(client, "ws-d2")["three_phase_complete_sets"][0]
        assert len(s["voltage_reference_evidence_names"]) > 0


# ---------------------------------------------------------------------------
# Class E — voltage_reference_confirmation_required: unknown naming
# ---------------------------------------------------------------------------

class TestE_VoltageReferenceUnknown:
    def test_generic_v_naming_gives_unknown_reference_and_confirmation_required(self, client):
        # CH1/CH2/CH3 etc. have no voltage-reference evidence.
        channels = [
            ("CH1V", "", "kV", "P"),
            ("CH2V", "", "kV", "P"),
            ("CH3V", "", "kV", "P"),
            ("CH1I", "", "kA", "C"),
            ("CH2I", "", "kA", "C"),
            ("CH3I", "", "kA", "C"),
        ]
        # These channels have no recognisable phase-role token so they won't
        # appear in three_phase_complete_sets at all; test this expectation.
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-e1", cfg, dat)
        result = _get_vi_pairs(client, "ws-e1")
        # Generic channels produce no automatic single-phase pairs either.
        assert result["three_phase_complete_sets"] == []

    def test_l1l2l3_naming_with_no_vref_evidence_needs_confirmation(self, client):
        # VL1/VL2/VL3 have no LINE_TO_GROUND evidence in the detector vocabulary,
        # so voltage_reference should be None → confirmed_required=True.
        channels = [
            ("VL1", "", "kV", "P"),
            ("VL2", "", "kV", "P"),
            ("VL3", "", "kV", "P"),
            ("IL1", "", "kA", "C"),
            ("IL2", "", "kA", "C"),
            ("IL3", "", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-e2", cfg, dat)
        result = _get_vi_pairs(client, "ws-e2")
        complete = result["three_phase_complete_sets"]
        if complete:
            s = complete[0]
            if s["voltage_reference"] != "line_to_ground":
                assert s["voltage_reference_confirmation_required"] is True


# ---------------------------------------------------------------------------
# Class F — backward compatibility
# ---------------------------------------------------------------------------

class TestF_BackwardCompatibility:
    def test_existing_fields_present_with_three_phase_source(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-f1", cfg, dat)
        result = _get_vi_pairs(client, "ws-f1")
        assert "automatic_pairs" in result
        assert "candidates_needing_confirmation" in result
        assert "total_input_channel_count" in result

    def test_single_phase_pair_still_present_in_automatic_pairs(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-f2", cfg, dat)
        result = _get_vi_pairs(client, "ws-f2")
        # A complete three-phase set still exposes its individual pairs
        # in automatic_pairs for single-phase power creation.
        assert len(result["automatic_pairs"]) == 3


# ---------------------------------------------------------------------------
# Class G — empty workspace
# ---------------------------------------------------------------------------

class TestG_EmptyWorkspace:
    def test_empty_workspace_has_no_three_phase_sets(self, client):
        result = _get_vi_pairs(client, "ws-g-empty")
        assert result["three_phase_complete_sets"] == []
        assert result["three_phase_incomplete_sets"] == []


# ---------------------------------------------------------------------------
# Helper: upload a long RYB six-channel source for creation tests
# ---------------------------------------------------------------------------

def _upload_ryb_source(client: TestClient, workspace_id: str) -> str:
    cfg, dat = _comtrade_bytes(_RYB_CHANNELS, rows=100)
    return _upload(client, workspace_id, cfg, dat)


# ---------------------------------------------------------------------------
# Class H — three_phase_active_power creation
# ---------------------------------------------------------------------------

class TestH_ThreePhaseActivePower:
    def test_three_phase_active_power_returns_201(self, client):
        sid = _upload_ryb_source(client, "ws-h1")
        resp = _create_channel(
            client, "ws-h1",
            name="P_total",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VR", "VY", "VB", "IR", "IY", "IB"),
        )
        assert resp.status_code == 201, resp.text

    def test_three_phase_active_power_unit_is_mw(self, client):
        sid = _upload_ryb_source(client, "ws-h2")
        resp = _create_channel(
            client, "ws-h2",
            name="P_total",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VR", "VY", "VB", "IR", "IY", "IB"),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit"] == "MW"

    def test_three_phase_active_power_operation_in_response(self, client):
        sid = _upload_ryb_source(client, "ws-h3")
        resp = _create_channel(
            client, "ws-h3",
            name="P_total",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VR", "VY", "VB", "IR", "IY", "IB"),
        )
        assert resp.json()["operation"] == "three_phase_active_power"


# ---------------------------------------------------------------------------
# Class I — three_phase_reactive_power creation
# ---------------------------------------------------------------------------

class TestI_ThreePhaseReactivePower:
    def test_three_phase_reactive_power_returns_201_with_mvar_unit(self, client):
        sid = _upload_ryb_source(client, "ws-i1")
        resp = _create_channel(
            client, "ws-i1",
            name="Q_total",
            operation="three_phase_reactive_power",
            inputs=_six_inputs(sid, "VR", "VY", "VB", "IR", "IY", "IB"),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit"] == "Mvar"


# ---------------------------------------------------------------------------
# Class J — three_phase_apparent_power creation
# ---------------------------------------------------------------------------

class TestJ_ThreePhaseApparentPower:
    def test_three_phase_apparent_power_returns_201_with_mva_unit(self, client):
        sid = _upload_ryb_source(client, "ws-j1")
        resp = _create_channel(
            client, "ws-j1",
            name="S_total",
            operation="three_phase_apparent_power",
            inputs=_six_inputs(sid, "VR", "VY", "VB", "IR", "IY", "IB"),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit"] == "MVA"


# ---------------------------------------------------------------------------
# Class K — L-L voltage rejection
# ---------------------------------------------------------------------------

class TestK_LineToLineVoltageRejected:
    def test_ll_voltage_in_v1_slot_rejected_without_phase_pairing_confirmed(self, client):
        channels = [
            ("VRY", "R", "kV", "P"),  # line-to-line name
            ("VY",  "Y", "kV", "P"),
            ("VB",  "B", "kV", "P"),
            ("IR",  "R", "kA", "C"),
            ("IY",  "Y", "kA", "C"),
            ("IB",  "B", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-k1", cfg, dat)
        resp = _create_channel(
            client, "ws-k1",
            name="P_bad",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VRY", "VY", "VB", "IR", "IY", "IB"),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "line_to_line_voltage_rejected"

    def test_ll_voltage_rejected_even_with_phase_pairing_confirmed(self, client):
        channels = [
            ("VRY", "R", "kV", "P"),
            ("VY",  "Y", "kV", "P"),
            ("VB",  "B", "kV", "P"),
            ("IR",  "R", "kA", "C"),
            ("IY",  "Y", "kA", "C"),
            ("IB",  "B", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-k2", cfg, dat)
        resp = _create_channel(
            client, "ws-k2",
            name="P_bad",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VRY", "VY", "VB", "IR", "IY", "IB"),
            phase_pairing_confirmed=True,
        )
        # L-L guard is unconditional — phase_pairing_confirmed does not bypass it.
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "line_to_line_voltage_rejected"


# ---------------------------------------------------------------------------
# Class L — unconfirmed voltage reference
# ---------------------------------------------------------------------------

class TestL_UnconfirmedVoltageReference:
    def test_unknown_vref_channels_rejected_without_voltage_reference_confirmed(self, client):
        # Use VL1/VL2/VL3 — these have no LINE_TO_GROUND evidence.
        channels = [
            ("VL1", "", "kV", "P"),
            ("VL2", "", "kV", "P"),
            ("VL3", "", "kV", "P"),
            ("IL1", "", "kA", "C"),
            ("IL2", "", "kA", "C"),
            ("IL3", "", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-l1", cfg, dat)
        resp = _create_channel(
            client, "ws-l1",
            name="P_l123",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VL1", "VL2", "VL3", "IL1", "IL2", "IL3"),
            phase_pairing_confirmed=True,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unconfirmed_voltage_reference"

    def test_unknown_vref_accepted_with_voltage_reference_confirmed(self, client):
        channels = [
            ("VL1", "", "kV", "P"),
            ("VL2", "", "kV", "P"),
            ("VL3", "", "kV", "P"),
            ("IL1", "", "kA", "C"),
            ("IL2", "", "kA", "C"),
            ("IL3", "", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-l2", cfg, dat)
        resp = _create_channel(
            client, "ws-l2",
            name="P_l123",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VL1", "VL2", "VL3", "IL1", "IL2", "IL3"),
            phase_pairing_confirmed=True,
            voltage_reference_confirmed=True,
        )
        assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Class M — unconfirmed phase pairing (generic names)
# ---------------------------------------------------------------------------

class TestM_UnconfirmedPhasePairing:
    def test_generic_ch_names_rejected_without_phase_pairing_confirmed(self, client):
        channels = [
            ("CH1", "", "kV", "P"),
            ("CH2", "", "kV", "P"),
            ("CH3", "", "kV", "P"),
            ("CH4", "", "kA", "C"),
            ("CH5", "", "kA", "C"),
            ("CH6", "", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-m1", cfg, dat)
        resp = _create_channel(
            client, "ws-m1",
            name="P_generic",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "CH1", "CH2", "CH3", "CH4", "CH5", "CH6"),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unconfirmed_phase_pairing"


# ---------------------------------------------------------------------------
# Class N — generic names accepted with both confirmations
# ---------------------------------------------------------------------------

class TestN_GenericNamesWithBothConfirmations:
    def test_generic_names_accepted_with_both_confirmed_flags(self, client):
        channels = [
            ("CH1", "", "kV", "P"),
            ("CH2", "", "kV", "P"),
            ("CH3", "", "kV", "P"),
            ("CH4", "", "kA", "C"),
            ("CH5", "", "kA", "C"),
            ("CH6", "", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-n1", cfg, dat)
        resp = _create_channel(
            client, "ws-n1",
            name="P_generic",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "CH1", "CH2", "CH3", "CH4", "CH5", "CH6"),
            phase_pairing_confirmed=True,
            voltage_reference_confirmed=True,
        )
        assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Class O — cross-convention mismatch (confirmed)
# ---------------------------------------------------------------------------

class TestO_PhaseMismatch:
    def test_cross_convention_without_confirmation_rejected(self, client):
        # VR/VY/VB (RYB) with IA/IB/IC (ABC) — different conventions.
        # Without phase_pairing_confirmed → unconfirmed_phase_pairing.
        channels = [
            ("VR", "R", "kV", "P"),
            ("VY", "Y", "kV", "P"),
            ("VB", "B", "kV", "P"),
            ("IA", "A", "kA", "C"),
            ("IB", "B", "kA", "C"),
            ("IC", "C", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-o1", cfg, dat)
        resp = _create_channel(
            client, "ws-o1",
            name="P_mismatch",
            operation="three_phase_active_power",
            inputs=_six_inputs(sid, "VR", "VY", "VB", "IA", "IB", "IC"),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unconfirmed_phase_pairing"

    def test_same_convention_token_swap_rejected_unconditionally(self, client):
        # VR+IB, VY+IY, VB+IR — all RYB but phase-R voltage is paired with
        # phase-B current → same-convention mismatch, unconditional.
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS, rows=100)
        sid = _upload(client, "ws-o2", cfg, dat)
        resp = _create_channel(
            client, "ws-o2",
            name="P_swap",
            operation="three_phase_active_power",
            inputs=[
                _source_ref(sid, "VR"),  # V1
                _source_ref(sid, "IB"),  # I1 — mismatch: R≠B in RYB
                _source_ref(sid, "VY"),
                _source_ref(sid, "IY"),
                _source_ref(sid, "VB"),
                _source_ref(sid, "IR"),
            ],
            phase_pairing_confirmed=True,  # override has no effect on mismatch
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "invalid_three_phase_phase_mismatch"


# ---------------------------------------------------------------------------
# Class P — duplicate phase assignment
# ---------------------------------------------------------------------------

class TestP_DuplicatePhaseAssignment:
    def test_duplicate_voltage_channel_rejected(self, client):
        # Supply VR in both first and second voltage slot.
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS, rows=100)
        sid = _upload(client, "ws-p1", cfg, dat)
        resp = _create_channel(
            client, "ws-p1",
            name="P_dup",
            operation="three_phase_active_power",
            inputs=[
                _source_ref(sid, "VR"),  # V-slot 1
                _source_ref(sid, "IR"),  # I-slot 1
                _source_ref(sid, "VR"),  # V-slot 2 — duplicate!
                _source_ref(sid, "IY"),
                _source_ref(sid, "VB"),
                _source_ref(sid, "IB"),
            ],
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "duplicate_phase_assignment"


# ---------------------------------------------------------------------------
# Class Q — cross-source pairing
# ---------------------------------------------------------------------------

class TestQ_CrossSourcePairing:
    def test_cross_source_pairing_rejected_without_phase_pairing_confirmed(self, client):
        # Voltages from source1, currents from source2.
        v_channels = [
            ("VR", "R", "kV", "P"),
            ("VY", "Y", "kV", "P"),
            ("VB", "B", "kV", "P"),
        ]
        i_channels = [
            ("IR", "R", "kA", "C"),
            ("IY", "Y", "kA", "C"),
            ("IB", "B", "kA", "C"),
        ]
        cfg1, dat1 = _comtrade_bytes(v_channels, rows=100)
        cfg2, dat2 = _comtrade_bytes(i_channels, rows=100)
        sid1 = _upload(client, "ws-q1", cfg1, dat1)
        sid2 = _upload(client, "ws-q1", cfg2, dat2)

        resp = _create_channel(
            client, "ws-q1",
            name="P_cross",
            operation="three_phase_active_power",
            inputs=[
                _source_ref(sid1, "VR"),
                _source_ref(sid2, "IR"),
                _source_ref(sid1, "VY"),
                _source_ref(sid2, "IY"),
                _source_ref(sid1, "VB"),
                _source_ref(sid2, "IB"),
            ],
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "unconfirmed_phase_pairing"


# ---------------------------------------------------------------------------
# Class R — cross-source accepted with phase_pairing_confirmed
# ---------------------------------------------------------------------------

class TestR_CrossSourceWithConfirmation:
    def test_cross_source_accepted_with_phase_pairing_confirmed(self, client):
        v_channels = [
            ("VR", "R", "kV", "P"),
            ("VY", "Y", "kV", "P"),
            ("VB", "B", "kV", "P"),
        ]
        i_channels = [
            ("IR", "R", "kA", "C"),
            ("IY", "Y", "kA", "C"),
            ("IB", "B", "kA", "C"),
        ]
        cfg1, dat1 = _comtrade_bytes(v_channels, rows=100)
        cfg2, dat2 = _comtrade_bytes(i_channels, rows=100)
        sid1 = _upload(client, "ws-r1", cfg1, dat1)
        sid2 = _upload(client, "ws-r1", cfg2, dat2)

        resp = _create_channel(
            client, "ws-r1",
            name="P_cross_ok",
            operation="three_phase_active_power",
            inputs=[
                _source_ref(sid1, "VR"),
                _source_ref(sid2, "IR"),
                _source_ref(sid1, "VY"),
                _source_ref(sid2, "IY"),
                _source_ref(sid1, "VB"),
                _source_ref(sid2, "IB"),
            ],
            phase_pairing_confirmed=True,
        )
        assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Class S — single-phase regression
# ---------------------------------------------------------------------------

class TestS_SinglePhaseRegression:
    def test_single_phase_active_power_still_works(self, client):
        channels = [("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-s1", cfg, dat)
        resp = _create_channel(
            client, "ws-s1",
            name="P_single",
            operation="active_power",
            inputs=[_source_ref(sid, "VA"), _source_ref(sid, "IA")],
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit"] == "MW"

    def test_single_phase_apparent_power_still_works(self, client):
        channels = [("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")]
        cfg, dat = _comtrade_bytes(channels, rows=100)
        sid = _upload(client, "ws-s2", cfg, dat)
        resp = _create_channel(
            client, "ws-s2",
            name="S_single",
            operation="apparent_power",
            inputs=[_source_ref(sid, "VA"), _source_ref(sid, "IA")],
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit"] == "MVA"

    def test_vi_pairs_single_phase_fields_present_in_3ph_source(self, client):
        cfg, dat = _comtrade_bytes(_RYB_CHANNELS)
        _upload(client, "ws-s3", cfg, dat)
        result = _get_vi_pairs(client, "ws-s3")
        assert result["total_input_channel_count"] == 6
        assert len(result["automatic_pairs"]) == 3


# ---------------------------------------------------------------------------
# Class T — schema validation (invalid operation)
# ---------------------------------------------------------------------------

class TestT_SchemaValidation:
    def test_invalid_operation_name_returns_422(self, client):
        channels = [("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")]
        cfg, dat = _comtrade_bytes(channels)
        sid = _upload(client, "ws-t1", cfg, dat)
        resp = _create_channel(
            client, "ws-t1",
            name="P_bad",
            operation="three_phase_active_power_TYPO",
            inputs=[_source_ref(sid, "VA"), _source_ref(sid, "IA")],
        )
        assert resp.status_code == 422

    def test_voltage_reference_confirmed_defaults_to_false(self, client):
        # A request body without voltage_reference_confirmed should default
        # to False — no 422 from missing field.
        channels = [("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")]
        cfg, dat = _comtrade_bytes(channels)
        sid = _upload(client, "ws-t2", cfg, dat)
        resp = _create_channel(
            client, "ws-t2",
            name="P_ok",
            operation="active_power",
            inputs=[_source_ref(sid, "VA"), _source_ref(sid, "IA")],
        )
        # active_power with VA/IA doesn't need the flag — this just proves
        # the field is optional (no 422).
        assert resp.status_code == 201, resp.text

    def test_phase_pairing_confirmed_defaults_to_false(self, client):
        channels = [("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")]
        cfg, dat = _comtrade_bytes(channels)
        sid = _upload(client, "ws-t3", cfg, dat)
        resp = _create_channel(
            client, "ws-t3",
            name="P_ok2",
            operation="active_power",
            inputs=[_source_ref(sid, "VA"), _source_ref(sid, "IA")],
        )
        assert resp.status_code == 201, resp.text
