"""API-level tests for GET /api/v1/workspaces/{workspace_id}/vi-pairs
(Phase C, DEC-205).

Tests the full HTTP path: workspace registry → find_vi_pairs() domain
resolver → serialisation → JSON response.

Coverage (12 scenario categories from the Phase C specification):
  1  Empty workspace → empty arrays, total_input_channel_count=0
  2  Single-source automatic pairing → correct pair fields
  3  Multiple bays (context-scoped pairs from the same source)
  4  Multiple phases (3 auto pairs from one source)
  5  Ambiguous candidates (duplicate V name across two sources → multiple_voltage)
  6  Duplicate channel names across sources → pair_ids are unambiguous
  7  Cross-source pairing (V from source1, I from source2 → cross_source)
  8  Conflicting metadata channel does not appear in automatic_pairs
  9  Unknown (Undefined) channels are excluded from pairing but counted
 10  Source removal → removed source's channels no longer appear
 11  Invalid workspace_id → 400
 12  API response schema (required fields, status literals, reason codes)
 13  Performance: 200 channels — completes without error
 14  Performance: 2 000 channels — completes without error

All tests use an in-process TestClient + the real app (no mocks).
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "comtrade"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Inline COMTRADE fixture generator
# ---------------------------------------------------------------------------

def _comtrade_bytes(
    channels: list[tuple[str, str, str, str]],
    rows: int = 4,
) -> tuple[bytes, bytes]:
    """Build minimal ASCII COMTRADE bytes suitable for upload.

    *channels* is a list of ``(name, phase, unit, channel_type)`` tuples
    where ``channel_type`` is ``"P"`` (primary/voltage-class) or ``"C"``
    (current-class).  ``phase`` may be ``""`` for channels with no COMTRADE
    phase label.  The sample rate is chosen large enough to be above the
    ``MIN_SAMPLES_PER_CYCLE = 4`` guard (4000 Hz at 50 Hz = 80 samples/cycle).

    *rows* controls how many sample rows the .dat contains (minimum 1).
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
        f"4000.0,{rows}",
        "06/03/2026,10:00:00.000000",
        "06/03/2026,10:00:00.000000",
        "ASCII",
        "1.0",
        "",
    ]
    cfg = "\r\n".join(cfg_lines)
    dat_rows: list[str] = []
    for i in range(1, rows + 1):
        vals = ",".join(["1"] * n)
        dat_rows.append(f"{i},{(i - 1) * 250},{vals}")
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


def _upload_fixture(client: TestClient, workspace_id: str, stem: str) -> str:
    cfg = (FIXTURES_DIR / f"{stem}.cfg").read_bytes()
    dat = (FIXTURES_DIR / f"{stem}.dat").read_bytes()
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        files={
            "cfg_file": ("event.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": ("event.dat", io.BytesIO(dat), "application/octet-stream"),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _get_vi_pairs(client: TestClient, workspace_id: str, expect_status: int = 200):
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/vi-pairs")
    assert resp.status_code == expect_status, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Scenario 1: empty workspace
# ---------------------------------------------------------------------------

class TestEmptyWorkspace:
    def test_empty_workspace_returns_empty_arrays(self, client):
        result = _get_vi_pairs(client, "ws-empty")
        assert result["automatic_pairs"] == []
        assert result["candidates_needing_confirmation"] == []
        assert result["total_input_channel_count"] == 0

    def test_unknown_workspace_same_as_empty(self, client):
        result = _get_vi_pairs(client, "ws-never-existed")
        assert result["total_input_channel_count"] == 0


# ---------------------------------------------------------------------------
# Scenario 2: single-source automatic pairing
# ---------------------------------------------------------------------------

class TestSingleSourceAutomatic:
    def test_va_ia_single_source_yields_one_auto_pair(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-a", cfg, dat)

        result = _get_vi_pairs(client, "ws-a")
        assert len(result["automatic_pairs"]) == 1
        assert result["candidates_needing_confirmation"] == []

        pair = result["automatic_pairs"][0]
        assert pair["status"] == "automatic"
        assert pair["voltage_channel"]["channel_name"] == "VA"
        assert pair["current_channel"]["channel_name"] == "IA"
        assert pair["voltage_channel"]["unit"] == "kV"
        assert pair["current_channel"]["unit"] == "kA"
        assert pair["matching_evidence"]["phase_token"] == "A"

    def test_auto_pair_total_channel_count_includes_both(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-b", cfg, dat)

        result = _get_vi_pairs(client, "ws-b")
        assert result["total_input_channel_count"] == 2

    def test_auto_pair_pair_id_starts_with_auto_prefix(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-c", cfg, dat)

        result = _get_vi_pairs(client, "ws-c")
        pair = result["automatic_pairs"][0]
        assert pair["pair_id"].startswith("auto:")

    def test_auto_pair_source_id_matches_uploaded_source(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        source_id = _upload(client, "ws-d", cfg, dat)

        result = _get_vi_pairs(client, "ws-d")
        pair = result["automatic_pairs"][0]
        assert pair["source_id"] == source_id
        assert pair["voltage_channel"]["source_id"] == source_id
        assert pair["current_channel"]["source_id"] == source_id

    def test_auto_pair_display_label_contains_channel_names(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-e", cfg, dat)

        result = _get_vi_pairs(client, "ws-e")
        label = result["automatic_pairs"][0]["display_label"]
        assert "VA" in label
        assert "IA" in label

    def test_voltage_only_source_yields_no_pairs(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("VB", "B", "kV", "P")])
        _upload(client, "ws-vonly", cfg, dat)

        result = _get_vi_pairs(client, "ws-vonly")
        assert result["automatic_pairs"] == []
        assert result["candidates_needing_confirmation"] == []

    def test_current_only_source_yields_no_pairs(self, client):
        cfg, dat = _comtrade_bytes([("IA", "A", "kA", "C"), ("IB", "B", "kA", "C")])
        _upload(client, "ws-ionly", cfg, dat)

        result = _get_vi_pairs(client, "ws-ionly")
        assert result["automatic_pairs"] == []
        assert result["candidates_needing_confirmation"] == []


# ---------------------------------------------------------------------------
# Scenario 3: multiple bays (context-scoped pairs)
# ---------------------------------------------------------------------------

class TestMultipleBays:
    def test_two_bays_yield_two_separate_auto_pairs(self, client):
        # "N275_VA" / "N275_IA" → context "N275", phase "A"
        # "S132_VA" / "S132_IA" → context "S132", phase "A"
        channels = [
            ("N275_VA", "A", "kV", "P"),
            ("N275_IA", "A", "kA", "C"),
            ("S132_VA", "A", "kV", "P"),
            ("S132_IA", "A", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-bays", cfg, dat)

        result = _get_vi_pairs(client, "ws-bays")
        assert len(result["automatic_pairs"]) == 2

        contexts = {p["matching_evidence"]["context_hint"] for p in result["automatic_pairs"]}
        assert "N275" in contexts
        assert "S132" in contexts

    def test_mismatched_context_voltages_do_not_pair(self, client):
        # N275 voltage + S132 current — different contexts, no pair
        channels = [
            ("N275_VA", "A", "kV", "P"),
            ("S132_IA", "A", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-mismatch-ctx", cfg, dat)

        result = _get_vi_pairs(client, "ws-mismatch-ctx")
        assert result["automatic_pairs"] == []
        assert result["candidates_needing_confirmation"] == []


# ---------------------------------------------------------------------------
# Scenario 4: multiple phases
# ---------------------------------------------------------------------------

class TestMultiplePhases:
    def test_three_phase_source_yields_three_auto_pairs(self, client):
        channels = [
            ("VA", "A", "kV", "P"), ("IA", "A", "kA", "C"),
            ("VB", "B", "kV", "P"), ("IB", "B", "kA", "C"),
            ("VC", "C", "kV", "P"), ("IC", "C", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-3ph", cfg, dat)

        result = _get_vi_pairs(client, "ws-3ph")
        assert len(result["automatic_pairs"]) == 3
        assert result["candidates_needing_confirmation"] == []

        phase_tokens = {p["matching_evidence"]["phase_token"] for p in result["automatic_pairs"]}
        assert phase_tokens == {"A", "B", "C"}

    def test_ryb_three_phase_source_yields_three_auto_pairs(self, client):
        channels = [
            ("VR", "A", "kV", "P"), ("IR", "A", "kA", "C"),
            ("VY", "B", "kV", "P"), ("IY", "B", "kA", "C"),
            ("VB", "C", "kV", "P"), ("IB", "C", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-ryb", cfg, dat)

        result = _get_vi_pairs(client, "ws-ryb")
        assert len(result["automatic_pairs"]) == 3

    def test_line_to_line_voltage_excluded_from_pairing(self, client):
        # "VAB" is line-to-line; its phase_token_kind is "pair" → excluded.
        channels = [
            ("VA", "A", "kV", "P"),
            ("VAB", "AB", "kV", "P"),  # line-to-line, must be excluded
            ("IA", "A", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-l2l", cfg, dat)

        result = _get_vi_pairs(client, "ws-l2l")
        # VA+IA auto pair; VAB excluded
        assert len(result["automatic_pairs"]) == 1
        voltage_names = [p["voltage_channel"]["channel_name"] for p in result["automatic_pairs"]]
        assert "VAB" not in voltage_names
        assert "VA" in voltage_names


# ---------------------------------------------------------------------------
# Scenario 5: ambiguous candidates
# ---------------------------------------------------------------------------

class TestAmbiguousCandidates:
    def test_two_sources_same_voltage_name_yields_multiple_voltage_candidate(self, client):
        # Two sources supply the same context-scoped "CTX_VA" → multiple_voltage
        # candidate (context present, so OD-4 does not suppress it).
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_VA", "A", "kV", "P"), ("CTX_IA", "A", "kA", "C")])
        _upload(client, "ws-multi-v", cfg1, dat1)
        _upload(client, "ws-multi-v", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-multi-v")
        assert result["automatic_pairs"] == []
        assert len(result["candidates_needing_confirmation"]) == 1
        cand = result["candidates_needing_confirmation"][0]
        assert cand["reason"] == "multiple_voltage"
        assert len(cand["voltage_refs"]) == 2

    def test_null_context_multiple_voltage_is_suppressed(self, client):
        # OD-4 (DEC-206): plain "VA" (null context) multiple-voltage → suppressed.
        cfg1, dat1 = _comtrade_bytes([("VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-multi-v-noCtx", cfg1, dat1)
        _upload(client, "ws-multi-v-noCtx", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-multi-v-noCtx")
        assert result["automatic_pairs"] == []
        assert result["candidates_needing_confirmation"] == []

    def test_candidate_pair_id_starts_with_cand_prefix(self, client):
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_VA", "A", "kV", "P"), ("CTX_IA", "A", "kA", "C")])
        _upload(client, "ws-cand-id", cfg1, dat1)
        _upload(client, "ws-cand-id", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-cand-id")
        cand = result["candidates_needing_confirmation"][0]
        assert cand["pair_id"].startswith("cand:")

    def test_candidate_status_is_needs_confirmation(self, client):
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_VA", "A", "kV", "P"), ("CTX_IA", "A", "kA", "C")])
        _upload(client, "ws-cand-status", cfg1, dat1)
        _upload(client, "ws-cand-status", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-cand-status")
        cand = result["candidates_needing_confirmation"][0]
        assert cand["status"] == "needs_confirmation"

    def test_candidate_voltage_refs_carry_all_candidates(self, client):
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_VA", "A", "kV", "P"), ("CTX_IA", "A", "kA", "C")])
        _upload(client, "ws-cand-refs", cfg1, dat1)
        _upload(client, "ws-cand-refs", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-cand-refs")
        cand = result["candidates_needing_confirmation"][0]
        assert len(cand["voltage_refs"]) == 2
        v_names = {r["channel_name"] for r in cand["voltage_refs"]}
        assert v_names == {"CTX_VA"}
        v_sources = {r["source_id"] for r in cand["voltage_refs"]}
        assert len(v_sources) == 2  # from two different sources


# ---------------------------------------------------------------------------
# Scenario 6: duplicate channel names across sources — pair_ids unambiguous
# ---------------------------------------------------------------------------

class TestDuplicateNamesAcrossSources:
    def test_pair_ids_are_distinct_when_sources_share_channel_names(self, client):
        # Two sources that each have VA+IA would yield a multiple_voltage candidate,
        # not two auto pairs, because the resolver sees 2 V and 2 I at the same
        # (context, phase) key and cannot determine pairing without confirmation.
        # To demonstrate pair_id uniqueness, use different phases per source so
        # each source contributes an unambiguous auto pair.
        cfg1, dat1 = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        cfg2, dat2 = _comtrade_bytes([("VB", "B", "kV", "P"), ("IB", "B", "kA", "C")])
        sid1 = _upload(client, "ws-dup", cfg1, dat1)
        sid2 = _upload(client, "ws-dup", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-dup")
        # Each source forms its own independent auto pair (different phases)
        assert len(result["automatic_pairs"]) == 2

        pair_ids = {p["pair_id"] for p in result["automatic_pairs"]}
        assert len(pair_ids) == 2, "pair_ids must be unique across separate sources"

        source_ids = {p["source_id"] for p in result["automatic_pairs"]}
        assert source_ids == {sid1, sid2}

    def test_channel_refs_carry_source_id_in_duplicate_name_scenario(self, client):
        # Two sources, different phases, each producing an auto pair.
        # Each pair's voltage and current refs must belong to the same source.
        cfg1, dat1 = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        cfg2, dat2 = _comtrade_bytes([("VB", "B", "kV", "P"), ("IB", "B", "kA", "C")])
        sid1 = _upload(client, "ws-dup2", cfg1, dat1)
        sid2 = _upload(client, "ws-dup2", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-dup2")
        assert len(result["automatic_pairs"]) == 2
        for pair in result["automatic_pairs"]:
            assert pair["voltage_channel"]["source_id"] in {sid1, sid2}
            assert pair["current_channel"]["source_id"] in {sid1, sid2}
            # Voltage and current of an auto pair must come from the same source
            assert pair["voltage_channel"]["source_id"] == pair["current_channel"]["source_id"]


# ---------------------------------------------------------------------------
# Scenario 7: cross-source pairing
# ---------------------------------------------------------------------------

class TestCrossSourcePairing:
    def test_cross_source_without_context_is_not_a_candidate(self, client):
        # OD-4: plain "VA"/"IA" have no equipment-context prefix →
        # cross-source candidate is suppressed; channels are accessible only
        # through the Phase A manual-selection fallback.
        cfg1, dat1 = _comtrade_bytes([("VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("IA", "A", "kA", "C")])
        _upload(client, "ws-cross-noCtx", cfg1, dat1)
        _upload(client, "ws-cross-noCtx", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-cross-noCtx")
        assert result["automatic_pairs"] == []
        assert result["candidates_needing_confirmation"] == []

    def test_cross_source_with_context_yields_candidate(self, client):
        # Context-scoped cross-source: "CTX_VA" (source1) + "CTX_IA" (source2)
        # share context_hint "CTX" → REASON_CROSS_SOURCE candidate is kept.
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_IA", "A", "kA", "C")])
        sid1 = _upload(client, "ws-cross-ctx", cfg1, dat1)
        sid2 = _upload(client, "ws-cross-ctx", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-cross-ctx")
        assert result["automatic_pairs"] == []
        assert len(result["candidates_needing_confirmation"]) == 1

        cand = result["candidates_needing_confirmation"][0]
        assert cand["reason"] == "cross_source"
        assert cand["matching_evidence"]["context_hint"] == "CTX"
        assert len(cand["voltage_refs"]) == 1
        assert len(cand["current_refs"]) == 1
        assert cand["voltage_refs"][0]["source_id"] == sid1
        assert cand["current_refs"][0]["source_id"] == sid2

    def test_cross_source_candidate_carries_correct_channel_names(self, client):
        # Context-scoped RYB cross-source.
        cfg1, dat1 = _comtrade_bytes([("CTX_VR", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_IR", "A", "kA", "C")])
        _upload(client, "ws-cross-names", cfg1, dat1)
        _upload(client, "ws-cross-names", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-cross-names")
        assert len(result["candidates_needing_confirmation"]) == 1
        cand = result["candidates_needing_confirmation"][0]
        assert cand["voltage_refs"][0]["channel_name"] == "CTX_VR"
        assert cand["current_refs"][0]["channel_name"] == "CTX_IR"


# ---------------------------------------------------------------------------
# Scenario 8: conflicting metadata channel not in auto_pairs
# ---------------------------------------------------------------------------

class TestConflictingMetadata:
    def test_channel_with_conflicting_name_does_not_appear_in_auto_pairs(self, client):
        # A channel named "IVA" has both a current (I) and voltage (V) role
        # token in the same name -- this may trigger has_conflict in the
        # identity resolver.  Whether it does or not, the channel must not
        # contribute to an automatic pair.
        channels = [
            ("VA", "A", "kV", "P"),   # clean voltage
            ("IA", "A", "kA", "C"),   # clean current
            ("IVA", "A", "kA", "C"),  # potentially conflicted
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-conflict", cfg, dat)

        result = _get_vi_pairs(client, "ws-conflict")
        # "VA" + "IA" → clean auto pair; "IVA" must not appear in auto voltage
        for pair in result["automatic_pairs"]:
            assert pair["voltage_channel"]["channel_name"] != "IVA"
            assert pair["current_channel"]["channel_name"] != "IVA"


# ---------------------------------------------------------------------------
# Scenario 9: Undefined channels excluded from pairing, counted in total
# ---------------------------------------------------------------------------

class TestUndefinedChannels:
    def test_undefined_pu_channel_not_in_pairs(self, client):
        channels = [
            ("VA", "A", "kV", "P"),
            ("IA", "A", "kA", "C"),
            ("SIG", "", "pu", "P"),   # "pu" → Undefined engineering_type
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-undef", cfg, dat)

        result = _get_vi_pairs(client, "ws-undef")
        assert len(result["automatic_pairs"]) == 1
        assert result["candidates_needing_confirmation"] == []
        # All 3 channels counted even though SIG is ignored by the resolver
        assert result["total_input_channel_count"] == 3

    def test_frequency_channel_not_in_pairs(self, client):
        channels = [
            ("VA", "A", "kV", "P"),
            ("IA", "A", "kA", "C"),
            ("FREQ", "", "Hz", "P"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-freq", cfg, dat)

        result = _get_vi_pairs(client, "ws-freq")
        assert len(result["automatic_pairs"]) == 1
        assert result["total_input_channel_count"] == 3


# ---------------------------------------------------------------------------
# Scenario 10: source removal
# ---------------------------------------------------------------------------

class TestSourceRemoval:
    def test_removing_source_removes_its_channels_from_pairs(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        sid = _upload(client, "ws-remove", cfg, dat)

        # Before removal: 1 auto pair
        result = _get_vi_pairs(client, "ws-remove")
        assert len(result["automatic_pairs"]) == 1

        # Remove the source
        resp = client.delete(f"/api/v1/workspaces/ws-remove/sources/{sid}")
        assert resp.status_code == 204

        # After removal: empty
        result = _get_vi_pairs(client, "ws-remove")
        assert result["automatic_pairs"] == []
        assert result["total_input_channel_count"] == 0

    def test_removing_one_source_leaves_other_intact(self, client):
        cfg1, dat1 = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        cfg2, dat2 = _comtrade_bytes([("VB", "B", "kV", "P"), ("IB", "B", "kA", "C")])
        sid1 = _upload(client, "ws-remove2", cfg1, dat1)
        _upload(client, "ws-remove2", cfg2, dat2)

        # Before: 2 auto pairs
        result = _get_vi_pairs(client, "ws-remove2")
        assert len(result["automatic_pairs"]) == 2

        # Remove source 1
        client.delete(f"/api/v1/workspaces/ws-remove2/sources/{sid1}")

        # After: 1 auto pair remains
        result = _get_vi_pairs(client, "ws-remove2")
        assert len(result["automatic_pairs"]) == 1
        assert result["automatic_pairs"][0]["voltage_channel"]["channel_name"] == "VB"


# ---------------------------------------------------------------------------
# Scenario 11: invalid workspace_id
# ---------------------------------------------------------------------------

class TestInvalidWorkspaceId:
    def test_blank_workspace_id_returns_400(self, client):
        _get_vi_pairs(client, "   ", expect_status=400)

    def test_blank_workspace_error_code(self, client):
        resp = client.get("/api/v1/workspaces/   /vi-pairs")
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["code"] == "invalid_workspace"


# ---------------------------------------------------------------------------
# Scenario 12: API response schema validation
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_auto_pair_has_all_required_fields(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-schema", cfg, dat)

        result = _get_vi_pairs(client, "ws-schema")
        pair = result["automatic_pairs"][0]
        assert "pair_id" in pair
        assert "status" in pair
        assert "display_label" in pair
        assert "source_id" in pair
        assert "voltage_channel" in pair
        assert "current_channel" in pair
        assert "matching_evidence" in pair

    def test_auto_pair_channel_has_all_required_fields(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-schema2", cfg, dat)

        result = _get_vi_pairs(client, "ws-schema2")
        ch = result["automatic_pairs"][0]["voltage_channel"]
        assert "source_id" in ch
        assert "channel_name" in ch
        assert "engineering_type" in ch
        assert "unit" in ch

    def test_matching_evidence_has_required_fields(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-schema3", cfg, dat)

        result = _get_vi_pairs(client, "ws-schema3")
        ev = result["automatic_pairs"][0]["matching_evidence"]
        assert "context_hint" in ev
        assert "phase_token" in ev
        assert "phase_token_kind" in ev

    def test_candidate_has_all_required_fields(self, client):
        # Use context-scoped channels so OD-4 preserves the candidate.
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_VA", "A", "kV", "P"), ("CTX_IA", "A", "kA", "C")])
        _upload(client, "ws-schema4", cfg1, dat1)
        _upload(client, "ws-schema4", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-schema4")
        assert len(result["candidates_needing_confirmation"]) == 1
        cand = result["candidates_needing_confirmation"][0]
        assert "pair_id" in cand
        assert "status" in cand
        assert "display_label" in cand
        assert "reason" in cand
        assert "voltage_refs" in cand
        assert "current_refs" in cand
        assert "matching_evidence" in cand

    def test_reason_codes_are_known_values(self, client):
        # Context-scoped multiple_voltage: guaranteed candidate for reason-code check.
        cfg1, dat1 = _comtrade_bytes([("CTX_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("CTX_VA", "A", "kV", "P"), ("CTX_IA", "A", "kA", "C")])
        _upload(client, "ws-reason", cfg1, dat1)
        _upload(client, "ws-reason", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-reason")
        assert len(result["candidates_needing_confirmation"]) >= 1
        known_reasons = {"conflict", "multiple_voltage", "multiple_current", "cross_source"}
        for cand in result["candidates_needing_confirmation"]:
            assert cand["reason"] in known_reasons

    def test_workspace_isolation_between_separate_workspaces(self, client):
        cfg, dat = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        _upload(client, "ws-iso-1", cfg, dat)

        # ws-iso-2 has no sources
        result1 = _get_vi_pairs(client, "ws-iso-1")
        result2 = _get_vi_pairs(client, "ws-iso-2")

        assert len(result1["automatic_pairs"]) == 1
        assert result2["automatic_pairs"] == []


# ---------------------------------------------------------------------------
# Scenario 13: performance — 200 channels
# ---------------------------------------------------------------------------

class TestPerformance200:
    def test_200_channels_completes_without_error(self, client):
        # 100 bays, each with VA (Voltage) + IA (Current) → 100 auto pairs.
        # Bay context "B{n:03d}" ensures unique (context, phase) keys across all
        # bays so the resolver can auto-pair without ambiguity.
        channels = []
        for n in range(100):
            ctx = f"B{n:03d}"
            channels.append((f"{ctx}_VA", "A", "kV", "P"))
            channels.append((f"{ctx}_IA", "A", "kA", "C"))
        cfg, dat = _comtrade_bytes(channels, rows=4)
        _upload(client, "ws-perf200", cfg, dat)

        t0 = time.perf_counter()
        result = _get_vi_pairs(client, "ws-perf200")
        elapsed = time.perf_counter() - t0

        assert result["total_input_channel_count"] == 200
        assert len(result["automatic_pairs"]) == 100
        assert result["candidates_needing_confirmation"] == []
        print(f"\n[perf] 200-channel vi-pairs GET: {elapsed * 1000:.1f} ms")


# ---------------------------------------------------------------------------
# Scenario 14: performance — 2 000 channels
# ---------------------------------------------------------------------------

class TestPerformance2000:
    def test_2000_channels_completes_without_error(self, client):
        # 1000 bays, each with VA + IA → 1000 auto pairs (2000 channels total).
        channels = []
        for n in range(1000):
            ctx = f"B{n:04d}"
            channels.append((f"{ctx}_VA", "A", "kV", "P"))
            channels.append((f"{ctx}_IA", "A", "kA", "C"))
        cfg, dat = _comtrade_bytes(channels, rows=4)
        _upload(client, "ws-perf2000", cfg, dat)

        t0 = time.perf_counter()
        result = _get_vi_pairs(client, "ws-perf2000")
        elapsed = time.perf_counter() - t0

        assert result["total_input_channel_count"] == 2000
        assert len(result["automatic_pairs"]) == 1000
        assert result["candidates_needing_confirmation"] == []
        print(f"\n[perf] 2000-channel vi-pairs GET: {elapsed * 1000:.1f} ms")


# ---------------------------------------------------------------------------
# Focused tests — Item 3 (Phase C Final API Verification)
# ---------------------------------------------------------------------------

class TestChannelIdentityStability:
    def test_duplicate_names_within_source_uniquified_by_importer(self, client):
        # The COMTRADE importer renames duplicate channel names: the second "VA"
        # becomes "VA_1".  After upload, each channel has a unique name within
        # the source, so (source_id, channel_name) is always unambiguous.
        # The uniquified "VA_1" has no recognised phase token (the "_1" suffix is
        # treated as a numeric modifier, not a phase) → only the first "VA" + "IA"
        # form an auto pair.
        channels = [
            ("VA", "A", "kV", "P"),   # first VA
            ("VA", "A", "kV", "P"),   # second VA → stored as "VA_1" after import
            ("IA", "A", "kA", "C"),
        ]
        cfg, dat = _comtrade_bytes(channels)
        _upload(client, "ws-dup-names", cfg, dat)

        result = _get_vi_pairs(client, "ws-dup-names")
        # "VA" + "IA" → auto pair; "VA_1" (the uniquified duplicate) has no phase
        # token and is ignored by the resolver.
        assert len(result["automatic_pairs"]) == 1
        assert result["automatic_pairs"][0]["voltage_channel"]["channel_name"] == "VA"
        # All three stored channel slots are counted.
        assert result["total_input_channel_count"] == 3

    def test_pair_ids_unique_across_context_scoped_pairs(self, client):
        # Two bays on two sources: each bay forms a cross-source candidate.
        # The pair_ids must differ even though both have the same phase_token "A".
        cfg1, dat1 = _comtrade_bytes([("BAY1_VA", "A", "kV", "P"), ("BAY2_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("BAY1_IA", "A", "kA", "C"), ("BAY2_IA", "A", "kA", "C")])
        _upload(client, "ws-pid-ctx", cfg1, dat1)
        _upload(client, "ws-pid-ctx", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-pid-ctx")
        # BAY1 and BAY2 each have a cross-source candidate with context.
        assert len(result["candidates_needing_confirmation"]) == 2
        pair_ids = {c["pair_id"] for c in result["candidates_needing_confirmation"]}
        assert len(pair_ids) == 2, "pair_ids must be unique for different context/channel combinations"

    def test_auto_pair_ids_unique_across_separate_sources(self, client):
        # Two sources with different phases → two auto pairs; pair_ids must differ.
        cfg1, dat1 = _comtrade_bytes([("VA", "A", "kV", "P"), ("IA", "A", "kA", "C")])
        cfg2, dat2 = _comtrade_bytes([("VB", "B", "kV", "P"), ("IB", "B", "kA", "C")])
        _upload(client, "ws-auto-pid", cfg1, dat1)
        _upload(client, "ws-auto-pid", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-auto-pid")
        assert len(result["automatic_pairs"]) == 2
        pair_ids = {p["pair_id"] for p in result["automatic_pairs"]}
        assert len(pair_ids) == 2

    def test_cross_source_candidate_context_hint_matches_channel_prefix(self, client):
        # Verify the matching_evidence.context_hint field reflects the actual
        # equipment-context prefix extracted from the channel names.
        cfg1, dat1 = _comtrade_bytes([("N275_VA", "A", "kV", "P")])
        cfg2, dat2 = _comtrade_bytes([("N275_IA", "A", "kA", "C")])
        _upload(client, "ws-ctx-evidence", cfg1, dat1)
        _upload(client, "ws-ctx-evidence", cfg2, dat2)

        result = _get_vi_pairs(client, "ws-ctx-evidence")
        assert len(result["candidates_needing_confirmation"]) == 1
        cand = result["candidates_needing_confirmation"][0]
        assert cand["matching_evidence"]["context_hint"] == "N275"
        assert cand["reason"] == "cross_source"
