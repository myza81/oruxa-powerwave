"""PU-MIG S0 final reconciliation - independent oracle for the proposed S1 side-denominator contract.

Standard library only. It imports NOTHING from the application, so it cannot share a defect with the code under
test. Arithmetic is exact to 60 significant digits (`decimal`); every input is an exact decimal string.

    python -I pu_mig_s0_final_oracle.py            # prints the summary, asserts every invariant, rewrites the JSON
    python -I pu_mig_s0_final_oracle.py --check    # additionally fails if pu_mig_s0_final_expected.json differs

What it models (all [PROPOSAL] until the owner approves S1; see PU_MIG_S0_FINAL_RECONCILIATION_2026-11-24.md):

    resolve(request) -> (status, reason, denominator, conversion)

    denominator  = base_value * rho                      sample side == base side           ("direct"; ratio never read)
                 = base_value * rho / ratio              base primary,   sample secondary   ("base_divided_by_ratio")
                 = base_value * rho * ratio              base secondary, sample primary     ("base_multiplied_by_ratio")
    pu           = sample / denominator                  samples are NEVER scaled
    rho          = 1 (line-to-line / current), 1/sqrt(3) (line-to-ground voltage)
    ratio        = primary / secondary of the consumed channel's OWN Measurement Group (VT for voltage, CT for current)

Precedence of the refusals (first match wins; pinned by the expected JSON):
    1. invalid request                       2. sample side not strict-usable      3. base side unknown
    4. conversion needed and ratio not authoritative                               5. denominator not representable

Part B checks the claim the owner asked to be verified exactly: the 4.35 % Voltage discrepancy.
"""

from __future__ import annotations

import itertools
import json
import sys
from decimal import Decimal as D, getcontext
from pathlib import Path

getcontext().prec = 60
S3 = D(3).sqrt()
HERE = Path(__file__).resolve().parent
JSON_PATH = HERE / "pu_mig_s0_final_expected.json"

# ---------------------------------------------------------------------------------------------------------------- model
SAMPLE_PROBLEMS = {
    "calculated": "calculated_channel_side_unavailable",
    "unresolved": "measurement_side_unresolved",
    "inferred": "measurement_side_inferred",
    "group_conflict": "measurement_group_side_conflict",
}
RATIO_REASON = {"voltage": "vt_authority_unavailable", "current": "ct_authority_unavailable"}
RATIO_STATES = ("configured", "not_configured", "invalid", "untrusted_authority", "conflict", "no_group")


def resolve(req: dict) -> dict:
    """Specification model of `resolve_side_denominator`. Pure; no I/O."""
    q, base, sample, ratio = req["quantity"], req["base"], req["sample"], req["ratio"]
    out = {"status": "unavailable", "reason": None, "denominator": None, "conversion": None, "ratio_applied": None}
    # 1. invalid request: equipment/nominal-derived bases are Primary by definition (DEC-209); a value must be positive.
    if base["kind"] in ("nominal_ll_primary", "equipment_derived_primary") and base["declared_side"] != "primary":
        out["reason"] = "invalid_base_declaration"
        return out
    if D(base["value"]) <= 0:
        out["reason"] = "invalid_base_value"
        return out
    # 2. the sample side must be strict-usable (Recording Details; never inferred, never from a ratio or a magnitude)
    if sample["problem"] is not None:
        out["reason"] = SAMPLE_PROBLEMS[sample["problem"]]
        return out
    # 3. an Unknown base side is never assumed Primary
    if base["declared_side"] not in ("primary", "secondary"):
        out["reason"] = "base_side_unknown"
        return out
    rho = D(1) / S3 if (q == "voltage" and req.get("representation") == "line_to_ground") else D(1)
    scaled = D(base["value"]) * rho
    # direct: the ratio is not read, so a missing/invalid ratio never matters
    if base["declared_side"] == sample["side"]:
        out.update(status="resolved", denominator=scaled, conversion="direct")
        return out
    # 4. a conversion is needed: only an authoritative ratio may be used
    if ratio["status"] != "configured":
        out["reason"] = RATIO_REASON[q]
        out["ratio_status"] = ratio["status"]
        return out
    r = D(ratio["value"])
    if base["declared_side"] == "primary":      # primary base, secondary samples
        out.update(status="resolved", denominator=scaled / r, conversion="base_divided_by_ratio", ratio_applied=r)
    else:                                       # secondary base, primary samples
        out.update(status="resolved", denominator=scaled * r, conversion="base_multiplied_by_ratio", ratio_applied=r)
    return out


def pu(sample_value: D, den: D) -> D:
    return sample_value / den


# ----------------------------------------------------------------------------------------- Part A: exhaustive table
VT_RATIO = D(275000) / D(110)          # 2500
CT_RATIO = D(2000) / D(1)              # 2000:1
IBASE_EQUIP = D(1_000_000_000) / (S3 * D(275000))   # S = 1000 MVA, V_LL = 275 kV  -> 2099.4555...

VOLTAGE_BASES = {
    "nominal_ll_primary": {"kind": "nominal_ll_primary", "value": "275000", "declared_side": "primary"},
    "legacy_secondary_voltage_ll": {"kind": "legacy_secondary_voltage_ll", "value": "110", "declared_side": "secondary"},
}
CURRENT_BASES = {
    "equipment_derived_primary": {"kind": "equipment_derived_primary", "value": format(IBASE_EQUIP, ".30f"), "declared_side": "primary"},
    "manual_direct_primary": {"kind": "manual_direct", "value": "2100", "declared_side": "primary"},
    "manual_direct_secondary": {"kind": "manual_direct", "value": "1", "declared_side": "secondary"},
    "manual_direct_unknown": {"kind": "manual_direct", "value": "1", "declared_side": "unknown"},
    "result_manual_secondary": {"kind": "result_manual", "value": "1", "declared_side": "secondary"},
}
SAMPLE_STATES = ("primary", "secondary", "calculated", "unresolved", "inferred", "group_conflict")


def sample_input(state: str) -> dict:
    return {"side": state if state in ("primary", "secondary") else None,
            "problem": None if state in ("primary", "secondary") else state}


def ratio_input(state: str, value) -> dict:
    return {"status": state, "value": format(value, ".30f") if state == "configured" else None}


def table() -> list[dict]:
    rows: list[dict] = []
    for (bname, base), rep, sstate, rstate in itertools.product(VOLTAGE_BASES.items(), ("line_to_line", "line_to_ground"),
                                                                SAMPLE_STATES, RATIO_STATES):
        req = {"quantity": "voltage", "base": base, "representation": rep, "sample": sample_input(sstate),
               "ratio": ratio_input(rstate, VT_RATIO)}
        rows.append(_row(f"TV/{bname}/{rep}/{sstate}/{rstate}", req))
    for (bname, base), sstate, rstate in itertools.product(CURRENT_BASES.items(), SAMPLE_STATES, RATIO_STATES):
        req = {"quantity": "current", "base": base, "sample": sample_input(sstate), "ratio": ratio_input(rstate, CT_RATIO)}
        rows.append(_row(f"TC/{bname}/{sstate}/{rstate}", req))
    return rows


def _row(cid: str, req: dict) -> dict:
    out = resolve(req)
    return {"id": cid, "request": req, "status": out["status"], "reason": out["reason"],
            "conversion": out["conversion"],
            "denominator": None if out["denominator"] is None else format(out["denominator"], ".12f"),
            "ratio_applied": None if out["ratio_applied"] is None else format(out["ratio_applied"], ".12f")}


# ------------------------------------------------------------------------------------------- Part A2: worked examples
def worked() -> list[dict]:
    ex: list[dict] = []

    def add(cid, title, req, sample, note=""):
        out = resolve(req)
        den = out["denominator"]
        ex.append({"id": cid, "title": title, "status": out["status"], "reason": out["reason"], "conversion": out["conversion"],
                   "denominator": None if den is None else format(den, ".12f"),
                   "pu": None if den is None else format(pu(sample, den), ".12f"), "note": note})

    vt = ratio_input("configured", VT_RATIO)
    ct = ratio_input("configured", CT_RATIO)
    nom = VOLTAGE_BASES["nominal_ll_primary"]
    leg = VOLTAGE_BASES["legacy_secondary_voltage_ll"]
    for k in ("1", "0.87"):
        K = D(k)
        add(f"W-V-LL-P-{k}", f"Primary L-L at {k} pu", {"quantity": "voltage", "base": nom, "representation": "line_to_line",
            "sample": sample_input("primary"), "ratio": vt}, K * D(275000))
        add(f"W-V-LL-S-{k}", f"Secondary L-L at {k} pu (base 275 kV / VT 2500)", {"quantity": "voltage", "base": nom,
            "representation": "line_to_line", "sample": sample_input("secondary"), "ratio": vt}, K * D(275000) / VT_RATIO)
        add(f"W-V-LN-P-{k}", f"Primary L-N at {k} pu", {"quantity": "voltage", "base": nom, "representation": "line_to_ground",
            "sample": sample_input("primary"), "ratio": vt}, K * D(275000) / S3)
        add(f"W-V-LN-S-{k}", f"Secondary L-N at {k} pu", {"quantity": "voltage", "base": nom, "representation": "line_to_ground",
            "sample": sample_input("secondary"), "ratio": vt}, K * D(275000) / S3 / VT_RATIO)
    add("W-V-LEG-S", "Legacy secondary base (110 V), secondary L-L at nominal, no ratio needed",
        {"quantity": "voltage", "base": leg, "representation": "line_to_line", "sample": sample_input("secondary"),
         "ratio": ratio_input("not_configured", VT_RATIO)}, D(110), "ratio is not read")
    add("W-V-LEG-P", "Legacy secondary base on PRIMARY samples (VM1) with VT 2500",
        {"quantity": "voltage", "base": leg, "representation": "line_to_line", "sample": sample_input("primary"), "ratio": vt}, D(275000))
    add("W-V-LEG-P-NR", "Legacy secondary base on primary samples, ratio missing -> block",
        {"quantity": "voltage", "base": leg, "representation": "line_to_line", "sample": sample_input("primary"),
         "ratio": ratio_input("not_configured", VT_RATIO)}, D(275000))
    eq, md, ms = CURRENT_BASES["equipment_derived_primary"], CURRENT_BASES["manual_direct_primary"], CURRENT_BASES["manual_direct_secondary"]
    add("W-I-EQ-P", "Equipment Ibase, primary samples at Ibase", {"quantity": "current", "base": eq, "sample": sample_input("primary"),
        "ratio": ct}, IBASE_EQUIP)
    add("W-I-EQ-S", "Equipment Ibase, secondary samples at Ibase/2000", {"quantity": "current", "base": eq,
        "sample": sample_input("secondary"), "ratio": ct}, IBASE_EQUIP / CT_RATIO)
    add("W-I-EQ-S1", "Equipment Ibase, secondary 1.0 A (rated secondary current) -> below base", {"quantity": "current", "base": eq,
        "sample": sample_input("secondary"), "ratio": ct}, D(1))
    add("W-I-MP-S", "Manual 2100 A PRIMARY base, secondary samples 0.525 A, CT 4000:1", {"quantity": "current", "base": md,
        "sample": sample_input("secondary"), "ratio": ratio_input("configured", D(4000))}, D("0.525"))
    add("W-I-MS-S", "Manual 1 A SECONDARY base, secondary samples 0.5 A (no ratio)", {"quantity": "current", "base": ms,
        "sample": sample_input("secondary"), "ratio": ratio_input("no_group", CT_RATIO)}, D("0.5"))
    add("W-I-MS-P", "Manual 1 A SECONDARY base, primary samples 1000 A, CT 2000", {"quantity": "current", "base": ms,
        "sample": sample_input("primary"), "ratio": ct}, D(1000))
    add("W-I-MU", "Manual UNKNOWN base side -> never assumed Primary", {"quantity": "current",
        "base": CURRENT_BASES["manual_direct_unknown"], "sample": sample_input("primary"), "ratio": ct}, D(1000))
    return ex


# ----------------------------------------------------------------------------------------- Part B: the 4.35 % figure
def vt_discrepancy() -> list[dict]:
    """PU read with the legacy denominator `secondary_voltage_ll_v` (= the VT secondary WINDING RATING, written by auto-base
    from the channel's `secondary_ratio`) versus the derived denominator nominal / ratio, for a system at nominal.

        sample_secondary = nominal * Vs / Vp            (nominal L-L, VT Vp : Vs)
        pu_legacy        = sample / Vs         = nominal / Vp
        pu_derived       = sample / (nominal / (Vp/Vs)) = 1
        error            = nominal / Vp - 1
    """
    rows = []
    for nominal_kv, vp_kv, vs_v in ((132, 138, 110), (132, 132, 110), (275, 275, 110), (220, 230, 110), (110, 115, 110),
                                    (66, 69, 110), (400, 420, 110), (33, 34.5, 110), (132, 138, 63.5)):
        nominal, vp, vs = D(str(nominal_kv)) * 1000, D(str(vp_kv)) * 1000, D(str(vs_v))
        ratio = vp / vs
        sample = nominal / ratio
        den_leg = vs
        den_new = nominal / ratio
        pu_leg, pu_new = sample / den_leg, sample / den_new
        rows.append({"nominal_ll_kv": str(nominal_kv), "vt_primary_kv": str(vp_kv), "vt_secondary_v": str(vs_v),
                     "ratio": format(ratio, ".9f"), "sample_secondary_v": format(sample, ".9f"),
                     "legacy_denominator_v": format(den_leg, ".9f"), "derived_denominator_v": format(den_new, ".9f"),
                     "pu_legacy": format(pu_leg, ".9f"), "pu_derived": format(pu_new, ".9f"),
                     "error_pct": format((pu_leg / pu_new - 1) * 100, ".6f")})
        assert pu_new == 1 or abs(pu_new - 1) < D("1e-50")
        assert abs(pu_leg - nominal / vp) < D("1e-50")      # pu_legacy = nominal / Vp exactly
    # the owner's figure, exactly: nominal 132 kV, VT 138 kV / 110 V
    err = D(132) / D(138) - 1
    assert abs(err + D(1) / D(23)) < D("1e-55"), err         # = -1/23
    assert D(138) / D(132) == D(23) / D(22)
    return rows


# --------------------------------------------------------------------------------------------------- invariants
def check_invariants(tbl: list[dict]) -> None:
    # (a) PU of one physical condition is identical on both sides, for every ratio, level and representation.
    for rho_name in ("line_to_line", "line_to_ground"):
        for r in (D("1.0000001"), D("2"), D("63.7"), D(2500), D("1e6"), D("1e-3")):
            for k in (D(0), D("0.5"), D("0.87"), D(1), D("1.1")):
                base = VOLTAGE_BASES["nominal_ll_primary"]
                rat = ratio_input("configured", r)
                rho = D(1) / S3 if rho_name == "line_to_ground" else D(1)
                p = resolve({"quantity": "voltage", "base": base, "representation": rho_name, "sample": sample_input("primary"), "ratio": rat})
                s = resolve({"quantity": "voltage", "base": base, "representation": rho_name, "sample": sample_input("secondary"), "ratio": rat})
                sample_p = k * D(275000) * rho
                assert abs(sample_p / p["denominator"] - (sample_p / r) / s["denominator"]) < D("1e-50")
    # (b) ratio is not read on a same-side computation (a poisoned ratio changes nothing)
    for st in RATIO_STATES:
        a = resolve({"quantity": "current", "base": CURRENT_BASES["manual_direct_secondary"], "sample": sample_input("secondary"),
                     "ratio": ratio_input(st, CT_RATIO)})
        assert a["status"] == "resolved" and a["conversion"] == "direct" and a["denominator"] == D(1)
    # (c) round trip: a primary base B on secondary samples == a secondary base B/r declared on secondary samples
    for r in (D(2), D(2500), D("63.7")):
        a = resolve({"quantity": "current", "base": {"kind": "manual_direct", "value": "1000", "declared_side": "primary"},
                     "sample": sample_input("secondary"), "ratio": ratio_input("configured", r)})
        b = resolve({"quantity": "current", "base": {"kind": "manual_direct", "value": format(D(1000) / r, ".40f"), "declared_side": "secondary"},
                     "sample": sample_input("secondary"), "ratio": ratio_input("not_configured", r)})
        assert abs(a["denominator"] - b["denominator"]) < D("1e-35")
        c = resolve({"quantity": "current", "base": {"kind": "manual_direct", "value": format(D(1000) / r, ".40f"), "declared_side": "secondary"},
                     "sample": sample_input("primary"), "ratio": ratio_input("configured", r)})
        assert abs(c["denominator"] - D(1000)) < D("1e-35")
    # (d) every row of the exhaustive table is either resolved or carries exactly one reason; refusals never carry a number
    for row in tbl:
        assert (row["status"] == "resolved") == (row["reason"] is None), row["id"]
        assert (row["status"] == "resolved") == (row["denominator"] is not None), row["id"]
    # (e) refusal precedence: a non-strict sample side beats an unknown base side beats a missing ratio
    r1 = resolve({"quantity": "current", "base": CURRENT_BASES["manual_direct_unknown"], "sample": sample_input("inferred"),
                  "ratio": ratio_input("no_group", CT_RATIO)})
    assert r1["reason"] == "measurement_side_inferred"
    r2 = resolve({"quantity": "current", "base": CURRENT_BASES["manual_direct_unknown"], "sample": sample_input("primary"),
                  "ratio": ratio_input("no_group", CT_RATIO)})
    assert r2["reason"] == "base_side_unknown"
    r3 = resolve({"quantity": "current", "base": CURRENT_BASES["manual_direct_primary"], "sample": sample_input("secondary"),
                  "ratio": ratio_input("no_group", CT_RATIO)})
    assert r3["reason"] == "ct_authority_unavailable"
    # (f) DEC-215: the nominal-derived VT is nominal_primary : 110 V, so nominal / ratio is exactly 110 V and
    #     coincides with a 110 V secondary rating - the two paths only diverge when the VT primary differs from nominal.
    for nominal in (D(132000), D(275000), D(66000), D("33000")):
        ratio = nominal / D(110)
        assert nominal / ratio == D(110)
    # (g) a base declared on the sample's own side is never converted, whatever the quantity or representation
    for q, bases in (("voltage", VOLTAGE_BASES), ("current", CURRENT_BASES)):
        for b in bases.values():
            if b["declared_side"] in ("primary", "secondary"):
                out = resolve({"quantity": q, "base": b, "representation": "line_to_line", "sample": sample_input(b["declared_side"]),
                               "ratio": ratio_input("conflict", CT_RATIO)})
                assert out["conversion"] == "direct" and out["denominator"] == D(b["value"])


def main() -> int:
    tbl = table()
    check_invariants(tbl)
    data = {"model": __doc__.splitlines()[0], "table_rows": len(tbl), "table": tbl, "worked_examples": worked(),
            "vt_discrepancy": vt_discrepancy()}
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    resolved = sum(1 for r in tbl if r["status"] == "resolved")
    print(f"exhaustive table rows: {len(tbl)}  resolved: {resolved}  refused: {len(tbl) - resolved}")
    print("refusal reasons:", ", ".join(sorted({r['reason'] for r in tbl if r['reason']})))
    print("\nworked examples")
    for w in data["worked_examples"]:
        print(f"  {w['id']:<14s}{w['status']:<12s}{(w['reason'] or w['conversion']):<36s}den={w['denominator']}  pu={w['pu']}")
    print("\n4.35 % VT discrepancy (legacy secondary rating vs nominal / ratio, system at nominal)")
    for v in data["vt_discrepancy"]:
        print(f"  nominal {v['nominal_ll_kv']:>5s} kV  VT {v['vt_primary_kv']:>5s} kV/{v['vt_secondary_v']:>5s} V  "
              f"sample={v['sample_secondary_v']:>14s} V  pu_legacy={v['pu_legacy']}  error={v['error_pct']} %")
    if "--check" in sys.argv:
        if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != text:
            print("CHECK FAILED: expected JSON differs", file=sys.stderr)
            return 1
        print("\nCHECK OK: expected JSON is up to date")
        return 0
    JSON_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"\nwrote {JSON_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
