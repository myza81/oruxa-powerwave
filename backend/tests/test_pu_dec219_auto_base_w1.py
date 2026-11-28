"""DEC-219 / W-1 -- the automatic base service establishes the nominal voltage as the Primary PU base; it never creates a legacy Secondary base
merely because the recording contains Secondary samples.

Owner clarification: the DEC-215 VT policy is unchanged -- auto VT primary follows the nominal system voltage, auto VT secondary defaults to 110 V
line-to-line, the engineer overrides the VT through the existing Manual VT configuration, and no new VT / CFG authority is introduced.

The reported fixture (synth_measurement_groups, channel N275_VR, nominal 275 kV, line-to-line base) is verified with BOTH VTs. Two different questions
are kept apart:

  NUMERICAL correctness  -- the PU equals sample / D for the CONFIGURED ratio r:       D = nominal / r
        Auto VT    275 kV : 110 V   (r = 2500)  ->  Secondary peak 0.577345 kV / 0.110 kV = 5.2486
        Manual VT  275 kV : 1000 V  (r = 275)   ->  Secondary peak 0.577345 kV / 1.000 kV = 0.577345
  PHYSICAL correctness   -- holds only when the configured ratio IS the equipment's actual ratio. The fixture's CFG declares the real VT as
        275 kV : 1 kV (r = 275): under it the Secondary recording and the Primary recording of the same condition agree
        (158.77 kV / 275 kV = 0.57735). The 110 V auto default is a configured default, not a measurement of the equipment: with it the same
        recording reads 2500 / 275 = 9.0909 x higher. That is the engineer's cue to enter the Manual VT; it is not a defect of the denominator.
"""

from __future__ import annotations

import io

import pytest

from tests.test_per_unit_voltage_reference_safety import (  # noqa: F401  (client is the shared fixture)
    SECONDARY_V, VNAMES, checked, client, provenance, recording, wave_status, ROOT,
)
from tests.test_pu_mig_s2_raw_voltage_side import peak as pu_peak
from tests.test_pu_voltage_base_side_retirement import new_group, stored, ui_apply_new_nominal, upload_and_read_auto_voltage_configs

NOMINAL_KV = 275.0
AUTO_RATIO = NOMINAL_KV * 1000.0 / 110.0         # DEC-215 auto_nominal
ACTUAL_RATIO = NOMINAL_KV * 1000.0 / SECONDARY_V  # the fixture's real VT, 275 kV : 1 kV
PRIMARY_PEAK_KV = 158.77
SECONDARY_PEAK_KV = 0.577345


# ----------------------------------------------------------------------------------- a new Secondary recording: no legacy base
def test_a_new_secondary_recording_gets_no_legacy_secondary_base(client, comtrade_fixtures_dir):
    configs = upload_and_read_auto_voltage_configs(client, comtrade_fixtures_dir, "S")
    assert configs
    for c in configs:
        assert c["base_reference_side"] != "secondary"          # no Secondary declaration because the samples are Secondary
        assert c["secondary_voltage_ll_v"] is None              # the CFG winding value is not stored as a denominator
        assert c["base_authority"] == "needs_review"            # the CFG primary winding rating of a Secondary recording is only a low-confidence candidate


def test_a_new_primary_recording_is_configured_exactly_as_before(client, comtrade_fixtures_dir):
    configs = upload_and_read_auto_voltage_configs(client, comtrade_fixtures_dir, "P")
    resolved = [c for c in configs if c["base_authority"] == "auto_resolved"]
    assert resolved and all(c["nominal_voltage_ll_kv"] == NOMINAL_KV and c["base_reference_side"] == "primary"
                            and c["secondary_voltage_ll_v"] is None for c in resolved)


def test_the_cfg_vt_ratio_stays_in_the_recording_metadata_and_is_not_made_an_authority(client, comtrade_fixtures_dir):
    """Nothing authoritative is discarded: the CFG ratio remains on the immutable recording channels; the group neither stores it as a
    base nor invents a recording_metadata VT authority (no new CFG authority semantics)."""
    configs = upload_and_read_auto_voltage_configs(client, comtrade_fixtures_dir, "S")
    assert all(c["vt_authority"] == "not_configured" and c["vt_primary_v"] is None and c["vt_secondary_v"] is None for c in configs)


# ----------------------------------------------------------------------------------- numerical vs physical correctness
def secondary_group_with_nominal(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    path = new_group(client, sid)
    ui_apply_new_nominal(client, path)
    return sid, path


def test_auto_vt_is_numerically_correct_for_the_configured_ratio(client, comtrade_fixtures_dir):
    sid, _ = secondary_group_with_nominal(client, comtrade_fixtures_dir)
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert (prov["verification_state"], prov["ratio_authority"]) == ("verified_converted", "auto_nominal")
    assert (prov["ratio_applied"], prov["effective_base_amount"]) == (pytest.approx(AUTO_RATIO), pytest.approx(NOMINAL_KV / AUTO_RATIO, rel=1e-12))
    assert pu_peak(body) == pytest.approx(SECONDARY_PEAK_KV / (NOMINAL_KV / AUTO_RATIO), rel=1e-9)       # 5.2486


def test_manual_vt_is_numerically_and_physically_correct_for_the_actual_ratio(client, comtrade_fixtures_dir):
    sid, path = secondary_group_with_nominal(client, comtrade_fixtures_dir)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "vt_primary_v": NOMINAL_KV * 1000.0, "vt_secondary_v": SECONDARY_V}))   # the existing Manual VT configuration
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert (prov["ratio_authority"], prov["ratio_applied"]) == ("manual", pytest.approx(ACTUAL_RATIO))
    assert pu_peak(body) == pytest.approx(SECONDARY_PEAK_KV / (NOMINAL_KV / ACTUAL_RATIO), rel=1e-9)     # 0.577345


def test_primary_and_secondary_recordings_agree_physically_only_under_the_actual_ratio(client, comtrade_fixtures_dir):
    primary = recording(client, comtrade_fixtures_dir, "P")
    ui_apply_new_nominal(client, new_group(client, primary))
    primary_pu = pu_peak(wave_status(client, primary, VNAMES[0]))
    assert primary_pu == pytest.approx(PRIMARY_PEAK_KV / NOMINAL_KV, rel=1e-12)                         # 0.57735

    sid, path = secondary_group_with_nominal(client, comtrade_fixtures_dir)
    auto_pu = pu_peak(wave_status(client, sid, VNAMES[0]))
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "vt_primary_v": NOMINAL_KV * 1000.0, "vt_secondary_v": SECONDARY_V}))
    manual_pu = pu_peak(wave_status(client, sid, VNAMES[0]))
    assert manual_pu == pytest.approx(primary_pu, rel=1e-5)                       # physical equivalence under the ACTUAL ratio (the CFG rounds a to 6 digits)
    assert auto_pu / manual_pu == pytest.approx(AUTO_RATIO / ACTUAL_RATIO, rel=1e-12)   # 2500 / 275: the configured default, not the equipment
    assert auto_pu / primary_pu == pytest.approx(9.0909090909, rel=1e-4)


# ----------------------------------------------------------------------------------- historical configurations are preserved
def make_auto_resolved_legacy_secondary(client, sid, group_id):
    """What an earlier release wrote for a Secondary recording: an auto_resolved legacy Secondary base."""
    registry = client.app.state.voltage_group_config_registry
    workspace = ROOT.split("/workspaces/")[1]
    from app.domain.base_authority import BASE_AUTHORITY_AUTO
    registry.update_fields(workspace, group_id, base_authority=BASE_AUTHORITY_AUTO, base_reference_side="secondary",
                           secondary_voltage_ll_v=SECONDARY_V, update_secondary=True)


def legacy_group(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    new_group(client, sid)
    group = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))[0]
    make_auto_resolved_legacy_secondary(client, sid, group["id"])
    return sid, group


def test_a_rerun_of_the_auto_base_service_never_migrates_a_legacy_secondary_base(client, comtrade_fixtures_dir):
    from app.services.auto_base_service import configure_auto_bases_for_source
    sid, group = legacy_group(client, comtrade_fixtures_dir)
    before = stored(client, sid)
    assert (before["base_reference_side"], before["secondary_voltage_ll_v"], before["base_authority"]) == ("secondary", SECONDARY_V, "auto_resolved")
    state = client.app.state
    result = configure_auto_bases_for_source(
        workspace_id=ROOT.split("/workspaces/")[1], source_id=sid, source_registry=state.workspace_registry,
        group_registry=state.measurement_group_registry, voltage_config_registry=state.voltage_group_config_registry)
    assert [d.action for d in result.voltage_group_details] == ["skipped_legacy_secondary"]
    after = stored(client, sid)
    for key in ("base_reference_side", "secondary_voltage_ll_v", "nominal_voltage_ll_kv", "base_authority"):
        assert after[key] == before[key], key


def test_a_membership_change_never_migrates_a_legacy_secondary_base(client, comtrade_fixtures_dir):
    sid, group = legacy_group(client, comtrade_fixtures_dir)
    before = stored(client, sid)
    checked(client.patch(f"{ROOT}/sources/{sid}/measurement-groups/{group['id']}",
                         json={"channel_refs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in VNAMES]}))
    after = stored(client, sid)
    for key in ("base_reference_side", "secondary_voltage_ll_v", "nominal_voltage_ll_kv", "base_authority"):
        assert after[key] == before[key], key


def test_a_legacy_secondary_base_keeps_its_numerical_result(client, comtrade_fixtures_dir):
    """D-4 / D-5 / A15: the legitimate legacy denominator is unchanged: the stored 1.0 kV L-L secondary base, line-to-ground,
    D = 1.0 / sqrt(3) kV = 0.57735 kV, so the rated Secondary peak 0.577345 kV reads 1.0 pu."""
    import math
    sid, _ = legacy_group(client, comtrade_fixtures_dir)
    prov, body = provenance(client, sid, VNAMES[0]), wave_status(client, sid, VNAMES[0])
    assert prov["verification_state"] == "verified_direct" and prov["effective_base_amount"] == pytest.approx(1.0 / math.sqrt(3.0))
    assert pu_peak(body) == pytest.approx(1.0, rel=1e-5)


def test_an_engineer_set_secondary_base_is_still_never_overwritten(client, comtrade_fixtures_dir):
    from app.services.auto_base_service import configure_auto_bases_for_source
    sid = recording(client, comtrade_fixtures_dir, "S")
    path = new_group(client, sid)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "base_reference_side": "secondary", "secondary_voltage_ll_v": SECONDARY_V}))     # manual authority (C4)
    before = stored(client, sid)
    state = client.app.state
    configure_auto_bases_for_source(
        workspace_id=ROOT.split("/workspaces/")[1], source_id=sid, source_registry=state.workspace_registry,
        group_registry=state.measurement_group_registry, voltage_config_registry=state.voltage_group_config_registry)
    assert stored(client, sid) == before


# ----------------------------------------------------------------------------------- existing numerical safeguards
def test_missing_vt_authority_still_refuses_a_required_conversion(client, comtrade_fixtures_dir):
    """No nominal means no derivable VT (DEC-215 needs the nominal): a Secondary-declared base on Primary samples stays blocked (D-6)."""
    sid = recording(client, comtrade_fixtures_dir, "P")
    path = new_group(client, sid)
    checked(client.put(path, json={"reference_mode": "manual", "reference_override": "line_to_line",
                                    "base_reference_side": "secondary", "secondary_voltage_ll_v": SECONDARY_V}))
    prov = provenance(client, sid, VNAMES[0])
    assert (prov["verification_state"], prov["side_refusal_reason"]) == ("blocked", "vt_authority_unavailable")
