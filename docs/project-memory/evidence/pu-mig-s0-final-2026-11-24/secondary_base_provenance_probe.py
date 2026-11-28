"""PU-MIG S0 owner review (item 2/3) - where `secondary_voltage_ll_v` comes from, and what provenance says about it.

Read-only probe. It runs the PRODUCTION writer (`auto_base_service.configure_auto_bases_for_source`), the PRODUCTION
configuration service (`update_voltage_configuration`), the PRODUCTION resolver (`resolve_voltage_base_for_group`) and the
PRODUCTION view/provenance builders against in-memory registries. It touches no file, network or shared state.

    PYTHONDONTWRITEBYTECODE=1 backend/.venv/Scripts/python.exe -B <this file>

Scenario inputs: a 132 kV system (the owner's example), VT 138 kV : 110 V.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.dont_write_bytecode = True

from app.domain.base_authority import BASE_AUTHORITY_MANUAL  # noqa: E402
from app.domain.calculated_channel import ChannelRef  # noqa: E402
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup  # noqa: E402
from app.domain.per_unit import STATUS_CONFIGURED, PerUnitResolution, apply_per_unit_to_value, resolve_conversion_eligibility  # noqa: E402
from app.domain.per_unit_reference import apply_source_reference  # noqa: E402
from app.domain.voltage_group_config import VoltageBaseConfiguration, resolve_voltage_base_for_group  # noqa: E402
from app.services.auto_base_service import configure_auto_bases_for_source  # noqa: E402
from app.services.measurement_group_registry import MeasurementGroupRegistry  # noqa: E402
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry  # noqa: E402
from app.services.voltage_group_config_service import update_voltage_configuration  # noqa: E402

WS, SRC, GID = "w", "s", "g1"
NOMINAL_V = 132000.0
VT_P, VT_S = 138000.0, 110.0
SAMPLE_S = NOMINAL_V * VT_S / VT_P            # 105.217391304... V, system exactly at nominal


def channels(names, *, side="secondary", unit="V", pri=VT_P, sec=VT_S):
    return [SimpleNamespace(name=n, engineering_type="Voltage", unit=unit, measurement_side=side,
                            primary_ratio=pri, secondary_ratio=sec) for n in names]


def build(names, **kw):
    group_reg, cfg_reg = MeasurementGroupRegistry(), VoltageGroupConfigRegistry()
    group = MeasurementGroup(id=GID, workspace_id=WS, source_id=SRC, kind=KIND_VOLTAGE, display_name="V-bus",
                             channel_refs=[ChannelRef(kind="source", source_id=SRC, channel_name=n) for n in names],
                             status=STATUS_CONFIRMED)
    group_reg.add(group)
    active = SimpleNamespace(metadata=SimpleNamespace(analog_channels=channels(names, **kw)))
    src_reg = SimpleNamespace(get=lambda ws, sid: active if sid == SRC else None)
    return group, group_reg, cfg_reg, src_reg


def run_writer(names, **kw):
    group, group_reg, cfg_reg, src_reg = build(names, **kw)
    result = configure_auto_bases_for_source(workspace_id=WS, source_id=SRC, source_registry=src_reg,
                                             group_registry=group_reg, voltage_config_registry=cfg_reg)
    return group, group_reg, cfg_reg, result


def show(label, cfg):
    if cfg is None:
        print(f"  {label}: <no configuration>")
        return
    print(f"  {label}: nominal_ll_kv={cfg.nominal_voltage_ll_kv} base_reference_side={cfg.base_reference_side} "
          f"base_authority={cfg.base_authority} secondary_voltage_ll_v={cfg.secondary_voltage_ll_v} "
          f"vt={cfg.vt_primary_v}/{cfg.vt_secondary_v} vt_authority={cfg.vt_authority}")


def pu_for(group, cfg, sample_v, *, sample_side="secondary", declared="secondary"):
    base = resolve_voltage_base_for_group(group, cfg)
    if base.status != STATUS_CONFIGURED:
        return dict(denominator_V=None, status=base.status, reason=base.reason, pu=None)
    res = PerUnitResolution(STATUS_CONFIGURED, GID, base.denominator_volts, "V", None)
    res = apply_source_reference(res, "Voltage", declared, voltage_group_config=cfg)
    res = resolve_conversion_eligibility(res, "V", "Voltage")
    out, unit, status = apply_per_unit_to_value(sample_v, "V", "Voltage", res)
    return dict(denominator_V=round(base.denominator_volts, 9), status=res.status, reason=res.reason,
                compat=res.reference_compatibility, pu=out if unit == "pu" else None)


def main() -> int:
    names = ["VAB", "VBC", "VCA"]
    print("=== 1. The automatic writer (production service) on a secondary-flagged L-L recording, channel rating 138 kV : 110 V")
    group, group_reg, cfg_reg, result = run_writer(names)
    print("  service result:", result.voltage_group_details)
    cfg = cfg_reg.get(WS, GID)
    show("stored", cfg)

    print("\n=== 2. Same recording, the channels carry only the secondary rating (no primary winding)")
    g2, gr2, cr2, r2 = run_writer(names, pri=None)
    print("  service result:", r2.voltage_group_details)
    show("stored", cr2.get(WS, GID))

    print("\n=== 3. What the engineer's own edit does to authority (production `update_voltage_configuration`)")
    # 3a: engineer edits ONLY the secondary value on the auto-written group
    update_voltage_configuration(workspace_id=WS, measurement_group_id=GID, group_registry=group_reg,
                                 voltage_config_registry=cfg_reg, secondary_voltage_ll_v=105.217391304)
    show("3a engineer typed ONLY secondary_voltage_ll_v", cfg_reg.get(WS, GID))
    # 3b: the auto service runs again (e.g. a membership change re-evaluates an auto_resolved base)
    configure_auto_bases_for_source(workspace_id=WS, source_id=SRC, source_registry=SimpleNamespace(
        get=lambda ws, sid: SimpleNamespace(metadata=SimpleNamespace(analog_channels=channels(names)))),
        group_registry=group_reg, voltage_config_registry=cfg_reg)
    show("3b after the automatic writer runs again", cfg_reg.get(WS, GID))
    # 3c: engineer sets the nominal kV without supplying a secondary value
    group, group_reg, cfg_reg, _ = run_writer(names)
    update_voltage_configuration(workspace_id=WS, measurement_group_id=GID, group_registry=group_reg,
                                 voltage_config_registry=cfg_reg, nominal_voltage_ll_kv=132.0)
    show("3c engineer typed nominal 132 kV only", cfg_reg.get(WS, GID))
    print("      resolver:", pu_for(group, cfg_reg.get(WS, GID), SAMPLE_S))
    # 3d: engineer supplies nominal and a secondary value together
    group, group_reg, cfg_reg, _ = run_writer(names)
    update_voltage_configuration(workspace_id=WS, measurement_group_id=GID, group_registry=group_reg,
                                 voltage_config_registry=cfg_reg, nominal_voltage_ll_kv=132.0,
                                 secondary_voltage_ll_v=110.0, base_reference_side="secondary")
    show("3d engineer typed nominal 132 kV + secondary 110 V", cfg_reg.get(WS, GID))

    print("\n=== 4. What the read models expose about the secondary value")
    from app.services.measurement_group_view_service import build_group_view  # noqa: E402
    group, group_reg, cfg_reg, _ = run_writer(names)
    view = build_group_view(group, group_registry=group_reg, voltage_config_registry=cfg_reg,
                            current_config_registry=SimpleNamespace(get=lambda *a, **k: None))
    vc = view.voltage_config
    print("  group view voltage_config fields:", sorted(f for f in vars(vc) if not f.startswith("_")) if hasattr(vc, "__dict__")
          else [s for s in type(vc).__slots__])
    print(f"  -> base_authority={vc.base_authority!r} secondary_voltage_ll_v={vc.secondary_voltage_ll_v!r}; "
          "no field records WHO or WHAT produced secondary_voltage_ll_v")
    from app.services.per_unit_provenance_service import PerUnitChannelProvenance  # noqa: E402
    print("  PerUnitChannelProvenance fields:", [f for f in PerUnitChannelProvenance.__dataclass_fields__])

    print("\n=== 5. 132 kV system, VT 138 kV : 110 V, system exactly at nominal, SECONDARY samples (105.217391304 V)")
    rows = []

    def row(label, nominal_kv, secondary_v, authority, side="secondary"):
        grp = MeasurementGroup(id=GID, workspace_id=WS, source_id=SRC, kind=KIND_VOLTAGE, display_name="V-bus", status=STATUS_CONFIRMED)
        c = VoltageBaseConfiguration(measurement_group_id=GID, workspace_id=WS, nominal_voltage_ll_kv=nominal_kv,
                                     reference_mode="manual", reference_override="line_to_line", base_reference_side=side,
                                     base_authority=authority, secondary_voltage_ll_v=secondary_v)
        r = pu_for(grp, c, SAMPLE_S)
        rows.append((label, authority, secondary_v, r))
        print(f"  {label:<58s} authority={authority:<14s} sec_base={str(secondary_v):<13s} -> {r}")

    row("auto-written rating (110 V), nominal 132 kV", 132.0, 110.0, "auto_resolved")
    row("same value, engineer-entered via API (authority unchanged)", 132.0, 110.0, "auto_resolved")
    row("same value, authority manual (engineer typed nominal+secondary)", 132.0, 110.0, BASE_AUTHORITY_MANUAL)
    row("engineer-entered 105.217391304 V, manual", 132.0, 105.217391304, BASE_AUTHORITY_MANUAL)
    row("legacy_manual 110 V (pre-existing configuration)", 132.0, 110.0, "legacy_manual")
    row("no nominal at all (secondary-only base 110 V)", None, 110.0, "auto_resolved")

    print()
    print("=== 6. Owner matrix: 132 kV system, VT 138 kV : 110 V (when configured), SECONDARY samples at nominal = 105.217391304 V")
    from app.domain.auto_nominal_vt import derive_auto_nominal_vt  # noqa: E402

    def matrix(label, *, nominal_kv, secondary_v, authority, vt=None, side="secondary"):
        grp = MeasurementGroup(id=GID, workspace_id=WS, source_id=SRC, kind=KIND_VOLTAGE, display_name="V-bus", status=STATUS_CONFIRMED)
        c = VoltageBaseConfiguration(measurement_group_id=GID, workspace_id=WS, nominal_voltage_ll_kv=nominal_kv,
                                     reference_mode="manual", reference_override="line_to_line", base_reference_side=side,
                                     base_authority=authority, secondary_voltage_ll_v=secondary_v,
                                     vt_primary_v=vt[0] if vt else None, vt_secondary_v=vt[1] if vt else None,
                                     vt_authority="manual" if vt else "not_configured")
        existing = pu_for(grp, c, SAMPLE_S)
        if vt:
            ratio, ratio_src = vt[0] / vt[1], "manual VT"
        else:
            auto = derive_auto_nominal_vt(c)
            ratio, ratio_src = (auto.primary_v / auto.secondary_v, "auto_nominal VT") if auto.derived else (None, "none")
        if nominal_kv is not None and ratio:
            derived = nominal_kv * 1000.0 / ratio
            derived_pu = SAMPLE_S / derived
        else:
            derived, derived_pu = None, None
        print(f"  {label}")
        print(f"      stored: nominal={nominal_kv} kV, secondary_base={secondary_v} V, authority={authority}, VT={vt}")
        print(f"      existing: denominator={existing['denominator_V']} V  status={existing['status']}  reason={existing['reason']}  pu={existing['pu']}")
        print(f"      ratio-derived ({ratio_src}): denominator={None if derived is None else round(derived, 9)} V  pu={None if derived_pu is None else round(derived_pu, 9)}")

    matrix("M1 what the AUTO writer actually stores (no nominal, no VT)", nominal_kv=None, secondary_v=110.0, authority="auto_resolved")
    matrix("M2 nominal 132 + secondary 110, no VT stored (auto_nominal VT = 132 kV : 110 V)", nominal_kv=132.0, secondary_v=110.0, authority="manual")
    matrix("M3 nominal 132 + secondary 110 + manual VT 138:110", nominal_kv=132.0, secondary_v=110.0, authority="manual", vt=(138000.0, 110.0))
    matrix("M4 nominal 132 + engineer secondary base 105.217391304 + manual VT 138:110", nominal_kv=132.0, secondary_v=105.217391304, authority="manual", vt=(138000.0, 110.0))
    matrix("M5 nominal 132 + manual VT 138:110, secondary base cleared (engineer typed nominal)", nominal_kv=132.0, secondary_v=None, authority="manual", vt=(138000.0, 110.0))
    matrix("M6 as M3 but authority legacy_manual (origin of the 110 unknown)", nominal_kv=132.0, secondary_v=110.0, authority="legacy_manual", vt=(138000.0, 110.0))
    matrix("M7 as M3 but authority auto_resolved (engineer edited only the secondary value via API)", nominal_kv=132.0, secondary_v=110.0, authority="auto_resolved", vt=(138000.0, 110.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
