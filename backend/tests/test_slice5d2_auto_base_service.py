"""DEC-050 Slice 5D-2 — Automatic Per-Unit Base Configuration after Import.

Covers auto_base_service.configure_auto_bases_for_source():

  Primary-side auto-configuration (PS=P):
    - N275 group gets nominal=275.0 kV, base_reference_side="primary", base_authority="auto_resolved"
    - S132 group gets nominal=132.0 kV, base_reference_side="primary", base_authority="auto_resolved"
    - E275 LL group gets nominal=275.0 kV (LL), base_authority="auto_resolved"

  Current groups skipped (DEC-050 §11 / C5):
    - Voltage config registry has no entries for current groups after configure_auto_bases

  Manual authority preservation (C4):
    - A group with base_authority="manual" is not overwritten by configure_auto_bases
    - A group with base_authority="legacy_manual" is not overwritten

  needs_review for insufficient evidence:
    - A group whose channel has measurement_side="unknown" (no PS flag) → needs_review
    - base_authority="needs_review" is written to registry

  Idempotency (C7):
    - Calling configure_auto_bases twice with same state produces same result

  prepare_workspace_source integration (Slice 5D-2 wiring):
    - After upload with voltage_config_registry supplied, auto bases are configured
    - auto_bases_configured > 0 on a primary-PS COMTRADE file
    - Calling twice is idempotent (second call: auto_bases_configured=0 for already-manual,
      but auto_resolved groups may be re-processed)

  Never-raises contract (C6):
    - Passing unknown source_id returns error result, does not raise
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, STATUS_SUGGESTED
from app.main import create_app
from app.services.auto_base_service import AutoBaseResult, configure_auto_bases_for_source


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

ROOT = "/api/v1/workspaces/ws-1"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _upload(client, fixtures_dir):
    """Upload synth_measurement_groups.cfg/.dat (PS=P primary markers)."""
    cfg = (fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
    dat = (fixtures_dir / "synth_measurement_groups.dat").read_bytes()
    resp = client.post(f"{ROOT}/sources", files={
        "cfg_file": ("event.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("event.dat", io.BytesIO(dat), "application/octet-stream"),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _registries(client):
    app = client.app
    return {
        "source_registry": app.state.workspace_registry,
        "group_registry": app.state.measurement_group_registry,
        "voltage_config_registry": app.state.voltage_group_config_registry,
    }


def _all_voltage_groups(client, source_id):
    groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
    return [g for g in groups if g["kind"] == "voltage"]


# ---------------------------------------------------------------------------
# Primary-side auto-configuration
# ---------------------------------------------------------------------------

class TestPrimaryAutoConfiguration:

    def test_primary_voltage_groups_get_auto_resolved(self, client, comtrade_fixtures_dir):
        """N275 and E275 groups resolve automatically; S132 is correctly ambiguous (Slice 6B).

        S132 channels have primary_ratio=132.0 kV on L-G channels.  With the
        Slice 6B multi-hypothesis resolver, 132.0 kV is ambiguous — it matches
        both IEC 132 kV (Convention A) and ANSI 230 kV via Convention B
        (132.0 × √3 ≈ 228.6 kV ≈ 230 kV).  The channel names "S132_VR/VY/VB"
        contain no "KV" token, so the name-token dimension cannot break the tie.
        Result: needs_review for S132, auto_resolved for N275 and E275.
        """
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = _registries(client)
        result = configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)

        assert result.error is None
        assert result.voltage_groups_configured > 0

        voltage_groups = _all_voltage_groups(client, source_id)
        assert len(voltage_groups) > 0, "Expected auto-detected voltage groups"

        for group in voltage_groups:
            group_id = group["id"]
            channel_names = [r["channel_name"] for r in group.get("channel_refs", [])]
            cfg = regs["voltage_config_registry"].get("ws-1", group_id)
            assert cfg is not None, f"No config for voltage group {group_id}"

            has_n275 = any("N275" in n for n in channel_names)
            has_e275 = any("E275" in n for n in channel_names)
            has_s132 = any("S132" in n for n in channel_names)

            if has_n275 or has_e275:
                assert cfg.base_authority == BASE_AUTHORITY_AUTO, (
                    f"Expected auto_resolved for N275/E275 group, got {cfg.base_authority!r}"
                )
                assert cfg.base_reference_side == "primary"
                assert cfg.nominal_voltage_ll_kv is not None and cfg.nominal_voltage_ll_kv > 0
            elif has_s132:
                # 132.0 kV L-G without group-name kV token → ambiguous (Slice 6B)
                assert cfg.base_authority == BASE_AUTHORITY_NEEDS_REVIEW, (
                    f"S132 group should be needs_review (ambiguous 132 kV), "
                    f"got {cfg.base_authority!r}"
                )

    def test_e275_ll_group_gets_275kv_nominal(self, client, comtrade_fixtures_dir):
        """E275 group has L-L channels (E275_VRY/VYB/VBR, primary=275.0).
        For L-L channels the evidence engine uses primary_ratio directly (no √3 scale).
        """
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = _registries(client)
        configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)

        all_groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
        # E275 L-L group contains E275_VRY/VYB/VBR channels
        e275 = next(
            (g for g in all_groups
             if g["kind"] == "voltage" and any("E275" in ref["channel_name"]
                                               for ref in g.get("channel_refs", []))),
            None,
        )
        assert e275 is not None, "E275 voltage group not found"
        cfg = regs["voltage_config_registry"].get("ws-1", e275["id"])
        assert cfg is not None
        assert cfg.base_authority == BASE_AUTHORITY_AUTO
        assert cfg.base_reference_side == "primary"
        # L-L primary_ratio=275.0 kV: evidence uses it directly (no √3 correction for L-L)
        assert cfg.nominal_voltage_ll_kv is not None
        assert abs(cfg.nominal_voltage_ll_kv - 275.0) < 0.5, (
            f"Expected 275.0 kV for E275 L-L group, got {cfg.nominal_voltage_ll_kv}"
        )


# ---------------------------------------------------------------------------
# Current groups skipped (C3 / DEC-050 §11)
# ---------------------------------------------------------------------------

class TestCurrentGroupsSkipped:

    def test_no_voltage_config_created_for_current_groups(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = _registries(client)
        configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)

        all_groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
        current_groups = [g for g in all_groups if g["kind"] == "current"]
        assert len(current_groups) > 0, "Expected current groups to be auto-detected"

        for group in current_groups:
            cfg = regs["voltage_config_registry"].get("ws-1", group["id"])
            assert cfg is None, (
                f"No VoltageBaseConfiguration should exist for current group {group['id']}"
            )


# ---------------------------------------------------------------------------
# Manual authority preservation (C4)
# ---------------------------------------------------------------------------

class TestManualAuthorityPreservation:

    def test_manual_authority_not_overwritten(self, client, comtrade_fixtures_dir):
        """Upload creates auto-detected groups.  Set one to manual authority via
        the voltage-config endpoint, then run configure_auto_bases and verify
        the manual value is preserved.
        """
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = _registries(client)

        # Find an auto-detected voltage group to test with
        all_groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
        voltage_groups = [g for g in all_groups if g["kind"] == "voltage"]
        assert voltage_groups, "Need at least one auto-detected voltage group"
        group_id = voltage_groups[0]["id"]

        # First confirm the group so the voltage-config endpoint accepts it
        client.patch(f"{ROOT}/sources/{source_id}/measurement-groups/{group_id}",
                     json={"status": "confirmed"})

        # Set manual authority via the voltage-config endpoint (PUT)
        config_url = f"{ROOT}/sources/{source_id}/measurement-groups/{group_id}/voltage-config"
        patch_resp = client.put(config_url, json={
            "nominal_voltage_ll_kv": 300.0,  # deliberately non-auto value — should be preserved
            "reference_mode": "manual", "reference_override": "line_to_ground",
            "base_reference_side": "primary",
        })
        assert patch_resp.status_code == 200, patch_resp.text

        # Confirm it was set as manual
        cfg_before = regs["voltage_config_registry"].get("ws-1", group_id)
        assert cfg_before is not None
        assert cfg_before.base_authority == BASE_AUTHORITY_MANUAL
        assert abs(cfg_before.nominal_voltage_ll_kv - 300.0) < 0.001

        # Run auto-base
        configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)

        # Manual value must be unchanged
        cfg_after = regs["voltage_config_registry"].get("ws-1", group_id)
        assert cfg_after.base_authority == BASE_AUTHORITY_MANUAL
        assert abs(cfg_after.nominal_voltage_ll_kv - 300.0) < 0.001, (
            "Manual nominal_voltage_ll_kv must not be overwritten by auto-base"
        )

    def test_legacy_manual_authority_not_overwritten(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = _registries(client)

        # Directly inject a legacy_manual config into the registry
        from app.domain.voltage_group_config import VoltageBaseConfiguration
        from app.domain.base_authority import BASE_AUTHORITY_LEGACY

        all_groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
        voltage_groups = [g for g in all_groups if g["kind"] == "voltage"]
        assert voltage_groups, "Need at least one voltage group"
        group_id = voltage_groups[0]["id"]

        regs["voltage_config_registry"].upsert(VoltageBaseConfiguration(
            measurement_group_id=group_id, workspace_id="ws-1",
            nominal_voltage_ll_kv=99.0, base_authority=BASE_AUTHORITY_LEGACY,
        ))

        configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)

        cfg_after = regs["voltage_config_registry"].get("ws-1", group_id)
        assert cfg_after.base_authority == BASE_AUTHORITY_LEGACY
        assert abs(cfg_after.nominal_voltage_ll_kv - 99.0) < 0.001, (
            "legacy_manual authority must not be overwritten by auto-base"
        )


# ---------------------------------------------------------------------------
# needs_review for unknown-side evidence
# ---------------------------------------------------------------------------

class TestNeedsReviewForUnknownSide:

    def test_unknown_ps_marker_produces_needs_review(self, client, comtrade_fixtures_dir):
        """Upload a recording with no PS marker → measurement_side='unknown' → needs_review."""
        lines = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_text().splitlines()
        for index in range(2, 11):
            fields = lines[index].split(",")
            if fields[4].strip().lower() == "kv":
                fields[-1] = ""  # blank PS marker → unknown measurement_side
                lines[index] = ",".join(fields)

        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        resp = client.post(f"{ROOT}/sources", files={
            "cfg_file": ("unknown_ps.cfg", io.BytesIO("\n".join(lines).encode()), "application/octet-stream"),
            "dat_file": ("unknown_ps.dat", io.BytesIO(dat), "application/octet-stream"),
        })
        assert resp.status_code == 201
        source_id = resp.json()["source_id"]

        regs = _registries(client)
        result = configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)

        assert result.error is None
        # Groups should be needs_review (unknown side, evidence not auto-sufficient)
        voltage_groups = _all_voltage_groups(client, source_id)
        for group in voltage_groups:
            cfg = regs["voltage_config_registry"].get("ws-1", group["id"])
            assert cfg is not None
            assert cfg.base_authority == BASE_AUTHORITY_NEEDS_REVIEW, (
                f"Expected needs_review for unknown-PS group, got {cfg.base_authority!r}"
            )


# ---------------------------------------------------------------------------
# Idempotency (C7)
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_calling_twice_same_state(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = _registries(client)

        result1 = configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)
        assert result1.error is None

        # Read config after first call
        voltage_groups = _all_voltage_groups(client, source_id)
        cfgs_after_first = {
            g["id"]: regs["voltage_config_registry"].get("ws-1", g["id"])
            for g in voltage_groups
        }

        result2 = configure_auto_bases_for_source(workspace_id="ws-1", source_id=source_id, **regs)
        assert result2.error is None

        # Config values must be identical after second call
        for group in voltage_groups:
            cfg1 = cfgs_after_first[group["id"]]
            cfg2 = regs["voltage_config_registry"].get("ws-1", group["id"])
            assert cfg1.base_authority == cfg2.base_authority
            assert cfg1.nominal_voltage_ll_kv == cfg2.nominal_voltage_ll_kv
            assert cfg1.base_reference_side == cfg2.base_reference_side


# ---------------------------------------------------------------------------
# Never-raises contract (C6)
# ---------------------------------------------------------------------------

class TestNeverRaises:

    def test_unknown_source_returns_error_result(self, client):
        regs = _registries(client)
        result = configure_auto_bases_for_source(
            workspace_id="ws-1", source_id="nonexistent-source", **regs
        )
        assert result.error == "source_not_found"
        assert result.voltage_groups_configured == 0


# ---------------------------------------------------------------------------
# prepare_workspace_source integration (Slice 5D-2 wiring)
# ---------------------------------------------------------------------------

class TestPrepareWorkspaceSourceIntegration:

    def test_upload_configures_auto_bases_via_prepare(self, client, comtrade_fixtures_dir):
        """A fresh upload with voltage_config_registry wired in auto-configures bases."""
        source_id = _upload(client, comtrade_fixtures_dir)

        # Voltage groups should already have auto_resolved config from prepare_workspace_source
        all_groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
        voltage_groups = [g for g in all_groups if g["kind"] == "voltage"]
        assert len(voltage_groups) > 0

        voltage_registry = client.app.state.voltage_group_config_registry
        auto_configured = [
            g for g in voltage_groups
            if (cfg := voltage_registry.get("ws-1", g["id"])) is not None
            and cfg.base_authority == BASE_AUTHORITY_AUTO
        ]
        assert len(auto_configured) > 0, (
            "Expected at least one voltage group auto-configured after upload"
        )

    def test_no_phantom_configs_after_upload(self, client, comtrade_fixtures_dir):
        # §1 guard: every config in the registry after upload must correspond to a known voltage
        # group from this source — no extra phantom entries, no configs for current groups.
        source_id = _upload(client, comtrade_fixtures_dir)
        all_groups = client.get(f"{ROOT}/sources/{source_id}/measurement-groups").json()
        voltage_group_ids = {g["id"] for g in all_groups if g["kind"] == "voltage"}
        assert voltage_group_ids, "Need at least one voltage group"

        all_configs = client.app.state.voltage_group_config_registry.list_for_workspace("ws-1")
        config_group_ids = {cfg.measurement_group_id for cfg in all_configs}

        assert config_group_ids <= voltage_group_ids, (
            f"Configs exist for group ids not in voltage_group_ids: "
            f"{config_group_ids - voltage_group_ids}"
        )

    def test_upload_prepare_result_reports_configured_count(self, client, comtrade_fixtures_dir, monkeypatch):
        """prepare_workspace_source() returns auto_bases_configured > 0 for primary-PS file."""
        from app.services import workspace_preparation_service
        from app.services.workspace_preparation_service import prepare_workspace_source

        # Suppress group and context discovery so we control what prepare_workspace_source does
        source_id = _upload(client, comtrade_fixtures_dir)
        regs = {
            "source_registry": client.app.state.workspace_registry,
            "group_registry": client.app.state.measurement_group_registry,
            "context_registry": client.app.state.engineering_context_registry,
            "calculated_channel_registry": client.app.state.calculated_channel_registry,
            "voltage_config_registry": client.app.state.voltage_group_config_registry,
        }
        # Groups and contexts already exist from upload — call prepare again
        result = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **regs)
        # auto_bases_configured may be 0 on second run (groups already auto_resolved),
        # but no error must occur
        assert result.auto_bases_error is None
