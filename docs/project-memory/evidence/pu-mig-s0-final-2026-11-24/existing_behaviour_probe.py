"""PU-MIG S0 final reconciliation - executed probe of the EXISTING gates (read-only).

Calls the production domain functions at the checked-out tree (e9c621c; backend/app is byte-identical to 2144893) with hand-built inputs and prints what they
return today. It changes nothing: no registry, no file, no network. Run it with the backend interpreter from the
repository root of this branch:

    PYTHONDONTWRITEBYTECODE=1 backend/.venv/Scripts/python.exe -B <this file> [--json]

It is evidence about *existing* behaviour only. Expected values for the PROPOSED behaviour come from the separate,
application-independent `pu_mig_s0_final_oracle.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.dont_write_bytecode = True

from app.domain.base_authority import BASE_AUTHORITY_MANUAL  # noqa: E402
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL, MeasurementGroup  # noqa: E402
from app.domain.per_unit import (  # noqa: E402
    STATUS_CONFIGURED, PerUnitResolution, apply_per_unit_to_value, resolve_conversion_eligibility,
)
from app.domain.per_unit_reference import apply_current_reference, apply_source_reference, apply_voltage_reference  # noqa: E402
from app.domain.voltage_group_config import VoltageBaseConfiguration, resolve_voltage_base_for_group  # noqa: E402

# 132 kV system, VT 138 kV / 110 V (ratio 138000/110), L-L representation, secondary rating 110 V stored as evidence.
NOMINAL_KV = 132.0
VT_RATIO = 138000.0 / 110.0
SAMPLE_PRIMARY_V = 132000.0
SAMPLE_SECONDARY_V = 132000.0 / VT_RATIO          # 105.2173913...
SECONDARY_RATING_V = 110.0

GROUP = MeasurementGroup(id="g1", workspace_id="w", source_id="s", kind=KIND_VOLTAGE, display_name="probe", status=STATUS_MANUAL)


def voltage_row(sample_is: str, declared: str, base_side: str) -> dict:
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="w", nominal_voltage_ll_kv=NOMINAL_KV,
        reference_mode="manual", reference_override="line_to_line", base_reference_side=base_side,
        base_authority=BASE_AUTHORITY_MANUAL, secondary_voltage_ll_v=SECONDARY_RATING_V,
    )
    base = resolve_voltage_base_for_group(GROUP, cfg)
    if base.status != "configured":
        return dict(sample=sample_is, declared=declared, base_side=base_side, status="base_required", reason=base.reason)
    res = PerUnitResolution(STATUS_CONFIGURED, "g1", base.denominator_volts, "V", None)
    res = apply_source_reference(res, "Voltage", declared, voltage_group_config=cfg)
    res = resolve_conversion_eligibility(res, "V", "Voltage")
    value = SAMPLE_PRIMARY_V if sample_is == "primary" else SAMPLE_SECONDARY_V
    out, unit, status = apply_per_unit_to_value(value, "V", "Voltage", res)
    return dict(sample=sample_is, declared=declared, base_side=base_side, denominator_V=round(base.denominator_volts, 9),
                compat=res.reference_compatibility, status=res.status, reason=res.reason,
                pu=None if unit != "pu" else out)


def current_row(declared: str, base_side: str, *, strict: bool, cross: bool) -> dict:
    res = PerUnitResolution(STATUS_CONFIGURED, "g", 1000.0, "A", None)
    res = apply_current_reference(res, [declared], [base_side], strict=strict, cross_authority=cross)
    return dict(declared=declared, base_side=base_side, strict=strict, cross_authority=cross,
                compat=res.reference_compatibility, status=res.status, reason=res.reason)


def gate_agreement() -> dict:
    """Display seam passes the Voltage group config; coverage/calculated provenance group paths do not."""
    cfg = VoltageBaseConfiguration(measurement_group_id="g1", workspace_id="w", nominal_voltage_ll_kv=NOMINAL_KV,
                                   base_reference_side="primary", base_authority=BASE_AUTHORITY_MANUAL)
    base = PerUnitResolution(STATUS_CONFIGURED, "g1", NOMINAL_KV * 1000.0, "V", None)
    display = apply_source_reference(base, "Voltage", "secondary", voltage_group_config=cfg)
    coverage = apply_source_reference(base, "Voltage", "secondary", group_config=None)
    return dict(display=dict(status=display.status, compat=display.reference_compatibility, reason=display.reason),
                coverage_or_calculated_provenance=dict(status=coverage.status, compat=coverage.reference_compatibility,
                                                       reason=coverage.reason))


def main() -> int:
    rows = [voltage_row(s, d, b) for s in ("primary", "secondary") for d in (s, "unknown") for b in ("primary", "secondary", "unknown")]
    cur = [current_row(d, b, strict=st, cross=cr) for d in ("primary", "secondary", "unknown")
           for b in ("primary", "secondary", "unknown") for st, cr in ((False, False), (True, False), (True, True))]
    data = dict(voltage=rows, current=cur, gate_agreement=gate_agreement())
    if "--json" in sys.argv:
        print(json.dumps(data, indent=2))
        return 0
    print("VOLTAGE  (132 kV L-L, VT 138 kV/110 V, secondary_voltage_ll_v=110 V; truth=what the samples physically are)")
    print(f"{'truth':<10}{'declared':<10}{'base side':<11}{'denominator V':>15}  {'compat':<12}{'status':<14}{'pu':>12}  reason")
    for r in rows:
        print(f"{r['sample']:<10}{r['declared']:<10}{r['base_side']:<11}{str(r.get('denominator_V', '-')):>15}  "
              f"{str(r.get('compat', '-')):<12}{r['status']:<14}{('-' if r.get('pu') is None else format(r['pu'], '.6f')):>12}  {r.get('reason') or ''}")
    print("\nCURRENT  apply_current_reference (plain = raw/single-authority automatic; strict = Manual; strict+cross = cross-authority)")
    for r in cur:
        mode = "strict+cross" if r["cross_authority"] else "strict" if r["strict"] else "plain"
        print(f"declared={r['declared']:<10}base={r['base_side']:<10}{mode:<13}{str(r['compat']):<12}{r['status']:<14}{r['reason'] or ''}")
    print("\nGATE AGREEMENT (Voltage, declared secondary vs stored base side primary):")
    print(json.dumps(data["gate_agreement"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
