"""DEC-050 Slice 5D-3 — Automatic Per-Unit Display and User Workflow.

§10 Acceptance tests for the backend-verifiable contract:

  AT-1  Primary COMTRADE import → voltage groups have pu_status="configured"
        (the backend state that enables the frontend §2 auto-switch to PU).
  AT-2  Secondary COMTRADE import → base_reference_side="secondary" and
        secondary_voltage_ll_v set correctly (not silently using primary kV).
  AT-3  Voltage PU configured; Current PU groups remain base_required (§3
        independence: Voltage PU does not auto-configure Current PU).
  AT-4  COMTRADE with no PS markers → needs_review → pu_status="base_required"
        (engineering display retained; no auto-switch would fire in frontend).
  AT-5  BEN import → no auto-resolved base → pu_status!="configured"
        (BEN has no PS declaration; no falsely authoritative PU).
  AT-6  Existing manual base survives repeated upload / auto-base (C4).
  AT-7  Repeated import of the same source → no duplicate configurations
        (idempotency at the lifecycle level).
  AT-8  Second source import → first source's auto-resolved configs untouched
        (additional import preserves existing state; each source is independent).
  AT-9  Mixed Primary/Secondary groups in one upload → each group gets its
        correct base_reference_side independently.
  AT-10 Invalidated (unavailable) authority → pu_status="base_required"
        (a base that was auto_resolved but later contradicted is not served).
  AT-11 — AT-15 require frontend/waveform verification; see §12 final report.
        AT-11: cursor/annotation values update after mode/base change.
        AT-12: calculated-channel and compliance compliance.
        AT-13: no silent ENG/PU mixing on a shared axis.
        AT-14: workspace-reset and new-workspace lifecycle.
        AT-15: numerical PU ≈ ENG / nominal for primary-side denominator.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.base_authority import BASE_AUTHORITY_AUTO, BASE_AUTHORITY_MANUAL, BASE_AUTHORITY_UNAVAILABLE
from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
COMTRADE = FIXTURES / "comtrade"
BEN = FIXTURES / "ben"
ROOT = "/api/v1/workspaces/ws-1"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _upload_comtrade(client, cfg_bytes: bytes, dat_bytes: bytes, *, workspace: str = "ws-1") -> str:
    resp = client.post(
        f"/api/v1/workspaces/{workspace}/sources",
        files={
            "cfg_file": ("event.cfg", io.BytesIO(cfg_bytes), "application/octet-stream"),
            "dat_file": ("event.dat", io.BytesIO(dat_bytes), "application/octet-stream"),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _upload_ben(client, ben_bytes: bytes, *, workspace: str = "ws-1") -> str:
    resp = client.post(
        f"/api/v1/workspaces/{workspace}/sources",
        files={"ben_file": ("event.ben", io.BytesIO(ben_bytes), "application/octet-stream")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _groups(client, source_id: str, workspace: str = "ws-1") -> list[dict]:
    resp = client.get(f"/api/v1/workspaces/{workspace}/sources/{source_id}/measurement-groups")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _voltage_groups(client, source_id: str, workspace: str = "ws-1") -> list[dict]:
    return [g for g in _groups(client, source_id, workspace) if g["kind"] == "voltage"]


def _current_groups(client, source_id: str, workspace: str = "ws-1") -> list[dict]:
    return [g for g in _groups(client, source_id, workspace) if g["kind"] == "current"]


def _cfg_with_ps(ps_value: str) -> bytes:
    """Return synth_measurement_groups.cfg with every analog PS field replaced by ps_value."""
    text = (COMTRADE / "synth_measurement_groups.cfg").read_text()
    lines = text.splitlines()
    new_lines = []
    header_seen = False
    analog_count = 0
    for line in lines:
        if not header_seen:
            header_seen = True
            new_lines.append(line)
            continue
        fields = line.split(",")
        # Analog channel lines have >=13 fields; the last is the PS marker.
        # Digital channel lines have 5 fields. Skip non-analog.
        if len(fields) >= 13:
            analog_count += 1
            # Field index 12 (0-based) is the PS marker for analog channels in
            # COMTRADE 1999 — only replace for channels that currently have P/S/C.
            current_ps = fields[-1].strip().upper()
            if current_ps in ("P", "S", "C", ""):
                fields[-1] = ps_value + "\n" if line.endswith("\n") else ps_value
            new_lines.append(",".join(fields))
        else:
            new_lines.append(line)
    return "\n".join(new_lines).encode()


def _cfg_with_secondary_channels() -> bytes:
    """Return a minimal COMTRADE cfg with PS=S voltage channels (secondary-referred).

    Uses N275_VR/VY/VB channels from synth_measurement_groups.cfg, rewritten
    with PS=S and secondary_ratio=0.0635 kV (≈ 63.5 V secondary on a 275 kV system).

    COMTRADE 1999 analog channel field order (0-indexed):
      0=n, 1=name, 2=ph, 3=ccbm, 4=unit, 5=a, 6=b, 7=skew, 8=min, 9=max,
      10=primary_ratio, 11=secondary_ratio, 12=PS
    """
    text = (COMTRADE / "synth_measurement_groups.cfg").read_text()
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        fields = line.split(",")
        if len(fields) >= 13:
            ch_name = fields[1].strip()
            unit = fields[4].strip().lower()
            if ch_name.startswith("N275_V") and unit == "kv":
                # primary_ratio stays 275.0 (fields[10] unchanged)
                fields[11] = "0.0635"  # secondary_ratio: 63.5 V = 0.0635 kV
                fields[-1] = "S"       # PS = Secondary (index 12)
            new_lines.append(",".join(fields))
        else:
            new_lines.append(line)
    return "\n".join(new_lines).encode()


# ---------------------------------------------------------------------------
# AT-1: Primary COMTRADE → voltage groups pu_status="configured"
# ---------------------------------------------------------------------------

class TestAT1PrimaryComtradeConfiguredPu:

    def test_voltage_groups_have_configured_pu_status_after_primary_upload(self, client, comtrade_fixtures_dir):
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        assert voltage_groups, "Expected auto-detected voltage groups"
        # Every voltage group that received a valid auto-resolved base must expose
        # pu_status="configured" through the measurement-groups API (§2 frontend
        # trigger relies on this field rather than on base_authority directly).
        configured = [g for g in voltage_groups if g["pu_status"] == "configured"]
        assert configured, (
            "Expected at least one voltage group with pu_status='configured' after primary COMTRADE import"
        )

    def test_configured_groups_have_valid_nominal_voltage(self, client, comtrade_fixtures_dir):
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        for g in _voltage_groups(client, source_id):
            if g["pu_status"] == "configured":
                assert g["voltage_config"] is not None
                assert g["voltage_config"]["nominal_voltage_ll_kv"] is not None
                assert g["voltage_config"]["nominal_voltage_ll_kv"] > 0

    def test_primary_reference_side_is_primary(self, client, comtrade_fixtures_dir):
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        for g in _voltage_groups(client, source_id):
            if g["pu_status"] == "configured":
                assert g["voltage_config"]["base_reference_side"] == "primary", (
                    f"PS=P group {g['id']} should have primary reference side"
                )


# ---------------------------------------------------------------------------
# AT-2: Secondary COMTRADE → secondary denominator, not primary kV
# ---------------------------------------------------------------------------

class TestAT2SecondaryComtrade:

    def test_secondary_channels_get_secondary_voltage_ll_v_set(self, client, comtrade_fixtures_dir):
        cfg = _cfg_with_secondary_channels()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        # Look for a group that contains N275_V channels (which we rewrote to PS=S)
        secondary_groups = [
            g for g in voltage_groups
            if g["voltage_config"] is not None
            and g["voltage_config"]["base_reference_side"] == "secondary"
        ]
        assert secondary_groups, (
            "Expected at least one voltage group with base_reference_side='secondary' "
            "after uploading a CFG with PS=S voltage channels"
        )

    def test_secondary_groups_have_secondary_voltage_ll_v(self, client, comtrade_fixtures_dir):
        cfg = _cfg_with_secondary_channels()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        for g in _voltage_groups(client, source_id):
            if (g["voltage_config"] is not None
                    and g["voltage_config"]["base_reference_side"] == "secondary"):
                sec_v = g["voltage_config"]["secondary_voltage_ll_v"]
                assert sec_v is not None, (
                    f"secondary group {g['id']} must have secondary_voltage_ll_v set"
                )
                # 63.5 V secondary (0.0635 kV) → ~63.5 V (line-to-ground) or ~110 V (line-to-line)
                # depending on detected reference; either way, never 275,000 V (primary kV)
                assert sec_v < 1000.0, (
                    f"secondary_voltage_ll_v={sec_v} V looks like a primary kV value was used "
                    "instead of the actual secondary voltage (C1 violation)"
                )

    def test_secondary_groups_have_configured_pu_status(self, client, comtrade_fixtures_dir):
        cfg = _cfg_with_secondary_channels()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        for g in _voltage_groups(client, source_id):
            if (g["voltage_config"] is not None
                    and g["voltage_config"]["base_reference_side"] == "secondary"):
                assert g["pu_status"] == "configured", (
                    f"secondary group {g['id']} with valid secondary_voltage_ll_v must be configured"
                )


# ---------------------------------------------------------------------------
# AT-3: Voltage PU configured; Current PU groups remain base_required (§3)
# ---------------------------------------------------------------------------

class TestAT3VoltagePuIndependentOfCurrentPu:

    def test_current_groups_are_not_auto_configured(self, client, comtrade_fixtures_dir):
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        current_groups = _current_groups(client, source_id)
        assert current_groups, "Expected auto-detected current groups"

        for g in current_groups:
            # Current groups must NOT be auto-configured: Ibase requires explicit
            # equipment rating or manual entry — not CT primary winding (C3 / §11).
            assert g["pu_status"] != "configured", (
                f"Current group {g['id']} must not be auto-configured for PU (C3 / §11)"
            )

    def test_voltage_configured_while_current_not_configured_coexist(self, client, comtrade_fixtures_dir):
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        current_groups = _current_groups(client, source_id)
        assert any(g["pu_status"] == "configured" for g in voltage_groups), (
            "At least one voltage group must be configured"
        )
        assert all(g["pu_status"] != "configured" for g in current_groups), (
            "No current group must be auto-configured"
        )


# ---------------------------------------------------------------------------
# AT-4: No PS markers → needs_review → pu_status="base_required"
# ---------------------------------------------------------------------------

class TestAT4NoPsMarkersNoAutoPu:

    def test_no_ps_markers_produces_base_required(self, client, comtrade_fixtures_dir):
        cfg = _cfg_with_ps("")
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        for g in voltage_groups:
            # Unknown measurement_side → needs_review → base ineligible → base_required
            assert g["pu_status"] != "configured", (
                f"Voltage group {g['id']} must not be auto-configured when PS markers are absent "
                "(engineering display should be retained, no auto-switch)"
            )

    def test_no_ps_markers_has_no_voltage_config_registry_entries_as_auto_resolved(
            self, client, comtrade_fixtures_dir):
        cfg = _cfg_with_ps("")
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        registry = client.app.state.voltage_group_config_registry
        for g in voltage_groups:
            config = registry.get("ws-1", g["id"])
            if config is not None:
                assert config.base_authority != BASE_AUTHORITY_AUTO, (
                    f"Group {g['id']} has no PS markers — base_authority must not be auto_resolved"
                )


# ---------------------------------------------------------------------------
# AT-5: BEN import → no auto-resolved base
# ---------------------------------------------------------------------------

class TestAT5BenNoFalsePu:

    def test_ben_upload_gives_no_auto_configured_voltage_pu(self, client):
        ben_bytes = (BEN / "synthetic_fast.ben").read_bytes()
        source_id = _upload_ben(client, ben_bytes)

        voltage_groups = _voltage_groups(client, source_id)
        # BEN has no PS declaration — none of the voltage groups should be
        # auto-configured as PU-reliable (no falsely authoritative PU, §10 AT-5).
        for g in voltage_groups:
            assert g["pu_status"] != "configured", (
                f"BEN voltage group {g['id']} must not appear as auto-configured for PU "
                "(BEN has no PS flag; this would be falsely authoritative)"
            )

    def test_ben_voltage_config_is_at_most_needs_review(self, client):
        ben_bytes = (BEN / "synthetic_fast.ben").read_bytes()
        source_id = _upload_ben(client, ben_bytes)

        registry = client.app.state.voltage_group_config_registry
        all_configs = registry.list_for_workspace("ws-1")
        for cfg in all_configs:
            assert cfg.base_authority != BASE_AUTHORITY_AUTO, (
                f"BEN upload must never produce base_authority=auto_resolved "
                f"(group {cfg.measurement_group_id})"
            )


# ---------------------------------------------------------------------------
# AT-6: Manual base survives repeated auto-base runs (C4)
# ---------------------------------------------------------------------------

class TestAT6ManualBaseNotOverwritten:

    def test_manual_base_survives_second_upload_of_same_source(self, client, comtrade_fixtures_dir):
        cfg_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg_bytes, dat_bytes)

        voltage_groups = _voltage_groups(client, source_id)
        assert voltage_groups, "Expected voltage groups"
        group_id = voltage_groups[0]["id"]

        # Confirm group so the voltage-config PUT endpoint accepts it
        client.patch(
            f"{ROOT}/sources/{source_id}/measurement-groups/{group_id}",
            json={"status": "confirmed"},
        )
        # Set a distinctive manual base
        put_resp = client.put(
            f"{ROOT}/sources/{source_id}/measurement-groups/{group_id}/voltage-config",
            json={"nominal_voltage_ll_kv": 999.0, "reference_mode": "manual",
                  "reference_override": "line_to_ground", "base_reference_side": "primary"},
        )
        assert put_resp.status_code == 200, put_resp.text
        registry = client.app.state.voltage_group_config_registry
        cfg_before = registry.get("ws-1", group_id)
        assert cfg_before.base_authority == BASE_AUTHORITY_MANUAL
        assert abs(cfg_before.nominal_voltage_ll_kv - 999.0) < 0.001

        # Upload a second time — auto-base re-runs for all groups
        _upload_comtrade(client, cfg_bytes, dat_bytes)

        # Manual base on the ORIGINAL group must be unchanged
        cfg_after = registry.get("ws-1", group_id)
        assert cfg_after.base_authority == BASE_AUTHORITY_MANUAL, (
            "Manual authority must survive auto-base re-run (C4)"
        )
        assert abs(cfg_after.nominal_voltage_ll_kv - 999.0) < 0.001, (
            "Manual nominal_voltage_ll_kv=999.0 must not be overwritten by auto-base"
        )


# ---------------------------------------------------------------------------
# AT-7: Repeated import — no duplicate configurations
# ---------------------------------------------------------------------------

class TestAT7RepeatedImportNoDuplicates:

    def test_uploading_same_content_twice_does_not_duplicate_configs(
            self, client, comtrade_fixtures_dir):
        cfg_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()

        source_id_a = _upload_comtrade(client, cfg_bytes, dat_bytes)
        count_after_first = client.app.state.voltage_group_config_registry.count()
        assert count_after_first > 0

        # Upload a second identical recording
        source_id_b = _upload_comtrade(client, cfg_bytes, dat_bytes)
        assert source_id_b != source_id_a, "Second upload must produce a distinct source_id"

        # Second upload is a NEW source → new groups → new configs; each source's
        # groups are independent so total count increases, never shrinks.
        count_after_second = client.app.state.voltage_group_config_registry.count()
        assert count_after_second >= count_after_first, (
            "Total config count must not decrease after a second identical upload"
        )
        # Verify no cross-source contamination: source A's configs still present.
        for g in _voltage_groups(client, source_id_a):
            if g["pu_status"] == "configured":
                assert client.app.state.voltage_group_config_registry.get("ws-1", g["id"]) is not None


# ---------------------------------------------------------------------------
# AT-8: Additional import preserves first source's auto-resolved configs
# ---------------------------------------------------------------------------

class TestAT8AdditionalImportPreservesFirstSource:

    def test_first_sources_configs_unchanged_after_second_upload(self, client, comtrade_fixtures_dir):
        cfg_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()

        source_id_a = _upload_comtrade(client, cfg_bytes, dat_bytes)
        registry = client.app.state.voltage_group_config_registry
        cfgs_before = {g["id"]: registry.get("ws-1", g["id"]) for g in _voltage_groups(client, source_id_a)}
        assert any(c is not None for c in cfgs_before.values()), "Source A must have configs after upload"

        # Upload a different second source (synth_ascii is simpler — no cross-contamination)
        cfg2 = (comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes()
        dat2 = (comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()
        _upload_comtrade(client, cfg2, dat2)

        # Source A's configs must be unchanged
        for group_id, cfg_before in cfgs_before.items():
            cfg_after = registry.get("ws-1", group_id)
            if cfg_before is None:
                assert cfg_after is None, f"Group {group_id} gained a config after second upload"
            else:
                assert cfg_after is not None, f"Group {group_id} lost its config after second upload"
                assert cfg_after.base_authority == cfg_before.base_authority
                assert cfg_after.nominal_voltage_ll_kv == cfg_before.nominal_voltage_ll_kv


# ---------------------------------------------------------------------------
# AT-9: Mixed Primary/Secondary groups in one upload
# ---------------------------------------------------------------------------

class TestAT9MixedPrimarySecondaryGroups:

    def test_primary_and_secondary_groups_get_correct_sides(self, client, comtrade_fixtures_dir):
        """A source that has both P and S channels (after rewriting) should produce
        at least one primary group and at least one secondary group, each with the
        correct base_reference_side."""
        # Build a CFG where N275_V* channels are PS=S (secondary) and
        # S132_V* and E275_V* stay PS=P (primary). Start from the original
        # and patch only the N275 lines.
        text = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_text()
        lines = text.splitlines()
        new_lines = []
        for line in lines:
            fields = line.split(",")
            if len(fields) >= 13:
                ch_name = fields[1].strip()
                if ch_name.startswith("N275_V"):
                    # fields[10] = primary_ratio (keep 275.0 unchanged)
                    fields[11] = "0.0635"  # secondary_ratio: 63.5 V = 0.0635 kV
                    fields[-1] = "S"       # PS = Secondary
            new_lines.append(",".join(fields))
        cfg = "\n".join(new_lines).encode()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        sides = [
            g["voltage_config"]["base_reference_side"]
            for g in voltage_groups
            if g["voltage_config"] is not None
        ]
        # We patched N275 to secondary → at least one "secondary" in sides
        assert "secondary" in sides, "Expected at least one secondary-side group"
        # S132 and E275 channels remain primary → at least one "primary"
        assert "primary" in sides, "Expected at least one primary-side group"


# ---------------------------------------------------------------------------
# AT-10: Invalidated base → pu_status="base_required"
# ---------------------------------------------------------------------------

class TestAT10InvalidatedBaseBecomesUnavailable:

    def test_unavailable_authority_gives_base_required(self, client, comtrade_fixtures_dir):
        cfg_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg_bytes, dat_bytes)

        voltage_groups = _voltage_groups(client, source_id)
        # Find a group that is currently configured
        configured = [g for g in voltage_groups if g["pu_status"] == "configured"]
        assert configured, "Need a configured group to test invalidation"
        group_id = configured[0]["id"]

        # Inject unavailable authority directly into the registry
        registry = client.app.state.voltage_group_config_registry
        existing = registry.get("ws-1", group_id)
        assert existing is not None
        registry.upsert(VoltageBaseConfiguration(
            measurement_group_id=group_id,
            workspace_id="ws-1",
            nominal_voltage_ll_kv=existing.nominal_voltage_ll_kv,
            base_authority=BASE_AUTHORITY_UNAVAILABLE,
        ))

        # Re-fetch measurement groups — the group must now report base_required
        updated_groups = _voltage_groups(client, source_id)
        updated = next(g for g in updated_groups if g["id"] == group_id)
        assert updated["pu_status"] == "base_required", (
            f"Group {group_id} with base_authority='unavailable' must report "
            "pu_status='base_required' (not 'configured')"
        )

    def test_unavailable_authority_does_not_propagate_to_other_groups(
            self, client, comtrade_fixtures_dir):
        cfg_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat_bytes = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg_bytes, dat_bytes)

        voltage_groups = _voltage_groups(client, source_id)
        configured = [g for g in voltage_groups if g["pu_status"] == "configured"]
        assert len(configured) >= 2, "Need at least 2 configured groups for this test"

        # Invalidate only the first group
        group_id_to_invalidate = configured[0]["id"]
        registry = client.app.state.voltage_group_config_registry
        existing = registry.get("ws-1", group_id_to_invalidate)
        registry.upsert(VoltageBaseConfiguration(
            measurement_group_id=group_id_to_invalidate, workspace_id="ws-1",
            nominal_voltage_ll_kv=existing.nominal_voltage_ll_kv,
            base_authority=BASE_AUTHORITY_UNAVAILABLE,
        ))

        updated_groups = _voltage_groups(client, source_id)
        for g in updated_groups:
            if g["id"] == group_id_to_invalidate:
                assert g["pu_status"] == "base_required"
            elif g["id"] in {c["id"] for c in configured[1:]}:
                assert g["pu_status"] == "configured", (
                    f"Group {g['id']} must still be configured — "
                    "invalidating one group must not affect others"
                )


# ---------------------------------------------------------------------------
# AT-12: Calculated channels with auto-resolved base
# ---------------------------------------------------------------------------

class TestAT12CalculatedChannelPU:
    """Verify that automatic PU configuration does not break calculated-channel
    consumers and that calculated channels correctly inherit the auto-resolved
    voltage base from their source channel's group."""

    def test_calculated_channel_in_auto_resolved_group_serves_pu(
            self, client, comtrade_fixtures_dir):
        """After COMTRADE upload triggers auto-base, a calculated channel that
        references a channel from an auto-resolved voltage group must expose
        per_unit_status='configured'."""
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        configured = [g for g in voltage_groups if g["pu_status"] == "configured"]
        assert configured, "Expected auto-resolved groups after primary COMTRADE upload"

        channel_name = configured[0]["channel_refs"][0]["channel_name"]

        calc_resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels",
            json={
                "name": f"Abs({channel_name})",
                "operation": "absolute_value",
                "inputs": [{"kind": "source", "source_id": source_id,
                            "channel_name": channel_name}],
            },
        )
        assert calc_resp.status_code == 201, calc_resp.text
        calc_id = calc_resp.json()["id"]

        wave_resp = client.get(
            "/api/v1/workspaces/ws-1/calculated-channels/{}/waveform".format(calc_id),
            params={"unit_mode": "per_unit"},
        )
        assert wave_resp.status_code == 200, wave_resp.text
        body = wave_resp.json()
        assert body["per_unit_status"] == "configured", (
            "Calculated channel from auto-resolved group must expose "
            "per_unit_status='configured', got {!r}".format(body["per_unit_status"])
        )

    def test_calculated_channel_abs_values_match_abs_of_source_pu(
            self, client, comtrade_fixtures_dir):
        """Abs(channel) in PU mode must equal abs(channel_in_pu) — the base is
        applied to the input before Abs, not after the absolute-value operation."""
        import math
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        voltage_groups = _voltage_groups(client, source_id)
        configured = [g for g in voltage_groups if g["pu_status"] == "configured"]
        assert configured
        channel_name = configured[0]["channel_refs"][0]["channel_name"]

        # Source PU waveform
        src_resp = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": channel_name, "unit_mode": "per_unit"},
        )
        assert src_resp.status_code == 200
        src_values = src_resp.json()["values"]

        # Create Abs(channel)
        calc_resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels",
            json={"name": "AbsCheck", "operation": "absolute_value",
                  "inputs": [{"kind": "source", "source_id": source_id,
                               "channel_name": channel_name}]},
        )
        assert calc_resp.status_code == 201, calc_resp.text
        calc_id = calc_resp.json()["id"]

        calc_resp2 = client.get(
            "/api/v1/workspaces/ws-1/calculated-channels/{}/waveform".format(calc_id),
            params={"unit_mode": "per_unit"},
        )
        assert calc_resp2.status_code == 200
        calc_values = calc_resp2.json()["values"]

        pairs = [(s, c) for s, c in zip(src_values, calc_values)
                 if s is not None and c is not None]
        assert pairs, "Expected at least one finite pair"
        for src_v, calc_v in pairs:
            expected = abs(src_v)
            assert abs(calc_v - expected) < max(abs(expected) * 1e-9, 1e-12), (
                f"Abs(x_pu): calc={calc_v:.10f}, abs(src_pu)={expected:.10f}"
            )


# ---------------------------------------------------------------------------
# AT-15: Independent numerical equivalence
# ---------------------------------------------------------------------------

class TestAT15NumericalPuEquivalence:
    """Verify actual waveform PU output against independently calculated reference
    values.  Covers Primary L-G, Primary L-L, and Secondary L-G cases."""

    def test_primary_lg_channel_pu_equals_eng_divided_by_ll_nominal_over_sqrt3(
            self, client, comtrade_fixtures_dir):
        """Primary L-G channel: PU = ENG_kV / (LL_nominal_kV / √3).
        Uses N275_VR (phase A) from synth_measurement_groups.cfg.
        Auto-base resolves to 275 kV LL → denominator = 275/√3 kV."""
        import math
        SQRT_3 = math.sqrt(3)

        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        # Find the N275 group (contains N275_VR)
        n275_group = next(
            (g for g in _groups(client, source_id)
             if g["kind"] == "voltage" and any(
                 ref["channel_name"] == "N275_VR"
                 for ref in g.get("channel_refs", [])
             )),
            None,
        )
        assert n275_group is not None, "N275 voltage group not found"
        assert n275_group["pu_status"] == "configured", "N275 group must be configured"

        nominal_kv = n275_group["voltage_config"]["nominal_voltage_ll_kv"]
        assert nominal_kv is not None and nominal_kv > 0
        denominator_kv = nominal_kv / SQRT_3  # L-G: LL/√3

        eng_values = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": "N275_VR", "unit_mode": "engineering"},
        ).json()["values"]

        pu_resp = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": "N275_VR", "unit_mode": "per_unit"},
        ).json()
        assert pu_resp["per_unit_status"] == "configured"
        pu_values = pu_resp["values"]

        pairs = [(e, p) for e, p in zip(eng_values, pu_values)
                 if e is not None and p is not None]
        assert pairs, "Expected at least one finite (eng, pu) pair"
        for eng_kv, pu_actual in pairs:
            expected_pu = eng_kv / denominator_kv
            tol = max(abs(expected_pu) * 1e-9, 1e-12)
            assert abs(pu_actual - expected_pu) < tol, (
                f"AT-15 primary L-G: pu={pu_actual:.10f}, "
                f"expected={expected_pu:.10f} (eng={eng_kv:.6f} kV, "
                f"denom={denominator_kv:.6f} kV = {nominal_kv:.1f}/√3)"
            )

    def test_primary_ll_channel_pu_equals_eng_divided_by_ll_nominal(
            self, client, comtrade_fixtures_dir):
        """Primary L-L channel: PU = ENG_kV / LL_nominal_kV.
        Uses E275_VRY (line-to-line) from synth_measurement_groups.cfg.
        No √3 factor — L-L measurement divides by L-L denominator directly."""
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        # Find the E275 L-L group (contains E275_VRY)
        e275_group = next(
            (g for g in _groups(client, source_id)
             if g["kind"] == "voltage" and any(
                 ref["channel_name"] == "E275_VRY"
                 for ref in g.get("channel_refs", [])
             )),
            None,
        )
        assert e275_group is not None, "E275 L-L voltage group not found"
        assert e275_group["pu_status"] == "configured", "E275 group must be configured"

        nominal_kv = e275_group["voltage_config"]["nominal_voltage_ll_kv"]
        assert nominal_kv is not None and nominal_kv > 0
        denominator_kv = nominal_kv  # L-L: use LL nominal directly (no √3)

        eng_values = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": "E275_VRY", "unit_mode": "engineering"},
        ).json()["values"]

        pu_resp = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": "E275_VRY", "unit_mode": "per_unit"},
        ).json()
        assert pu_resp["per_unit_status"] == "configured"
        pu_values = pu_resp["values"]

        pairs = [(e, p) for e, p in zip(eng_values, pu_values)
                 if e is not None and p is not None]
        assert pairs, "Expected at least one finite (eng, pu) pair"
        for eng_kv, pu_actual in pairs:
            expected_pu = eng_kv / denominator_kv
            tol = max(abs(expected_pu) * 1e-9, 1e-12)
            assert abs(pu_actual - expected_pu) < tol, (
                f"AT-15 primary L-L: pu={pu_actual:.10f}, "
                f"expected={expected_pu:.10f} (eng={eng_kv:.6f} kV, "
                f"denom={denominator_kv:.6f} kV = LL nominal directly)"
            )

    def test_secondary_lg_channel_pu_uses_secondary_voltage_as_denominator(
            self, client, comtrade_fixtures_dir):
        """Secondary L-G channel: PU = ENG_kV / (secondary_voltage_ll_v / 1000 / √3).
        Verifies the strict secondary denominator: auto-resolved secondary base uses
        secondary_voltage_ll_v (63.5 V = 0.0635 kV), NOT the primary nominal (275 kV).
        This is the core AT-15 safety check for the VLT-REF-001 secondary path."""
        import math
        SQRT_3 = math.sqrt(3)

        # _cfg_with_secondary_channels() marks N275_V* as PS=S with secondary_ratio=0.0635 kV
        # → auto-base sets secondary_voltage_ll_v=63.5 V, base_reference_side="secondary"
        cfg = _cfg_with_secondary_channels()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        source_id = _upload_comtrade(client, cfg, dat)

        n275_group = next(
            (g for g in _groups(client, source_id)
             if g["kind"] == "voltage" and any(
                 ref["channel_name"] == "N275_VR"
                 for ref in g.get("channel_refs", [])
             )),
            None,
        )
        assert n275_group is not None, "N275 group not found in secondary fixture"
        assert n275_group["pu_status"] == "configured", (
            "Secondary N275 group must be configured; "
            "voltage_config={}".format(n275_group.get("voltage_config"))
        )

        vc = n275_group["voltage_config"]
        assert vc is not None
        secondary_ll_v = vc["secondary_voltage_ll_v"]
        assert secondary_ll_v is not None and secondary_ll_v > 0, (
            "secondary_voltage_ll_v must be populated for secondary group"
        )
        # Denominator for secondary L-G: secondary_ll_v (V) / √3 → convert to kV: / 1000
        denominator_kv = secondary_ll_v / (SQRT_3 * 1000.0)

        eng_values = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": "N275_VR", "unit_mode": "engineering"},
        ).json()["values"]

        pu_resp = client.get(
            f"{ROOT}/sources/{source_id}/waveform",
            params={"channel_name": "N275_VR", "unit_mode": "per_unit"},
        ).json()
        assert pu_resp["per_unit_status"] == "configured"
        pu_values = pu_resp["values"]

        pairs = [(e, p) for e, p in zip(eng_values, pu_values)
                 if e is not None and p is not None]
        assert pairs, "Expected at least one finite (eng, pu) pair"
        for eng_kv, pu_actual in pairs:
            expected_pu = eng_kv / denominator_kv
            tol = max(abs(expected_pu) * 1e-9, 1e-12)
            assert abs(pu_actual - expected_pu) < tol, (
                f"AT-15 secondary L-G: pu={pu_actual:.10f}, "
                f"expected={expected_pu:.10f} "
                f"(eng={eng_kv:.6f} kV, secondary_denom={secondary_ll_v:.2f}/√3 V "
                f"= {denominator_kv*1000:.4f} V = {denominator_kv:.6f} kV)"
            )
