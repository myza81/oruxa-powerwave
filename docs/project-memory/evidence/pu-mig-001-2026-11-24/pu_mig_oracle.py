"""PU-MIG-001 S0 — independent numerical oracle.

Standard library only; imports NOTHING from the application, so it cannot share a defect with the code under
test. Arithmetic is exact to 60 significant digits (`decimal`), inputs are exact decimal/rational strings.

    python -I pu_mig_oracle.py            # prints the table, asserts every invariant, rewrites the JSON
    python -I pu_mig_oracle.py --check    # additionally fails if pu_mig_oracle_expected.json differs

Case ids are the ones cited by PU_MIG_001_S0_DECISION_MATRIX_2026-11-24.md. `expected_pu` is the independent
expected value; a case with `expected_block` expects NO numeric pu (the production code must report
`base_required` and the named reason; reason names are PROPOSALS pending owner approval).

Model (all [PROPOSAL] until the S0 decisions are approved):
    base_primary                    nominal L-L (L-N: / sqrt3), derived Ibase = S / (sqrt3 * V_LL), or manual Ibase
    denominator(sample side)        = base_primary                 sample side primary
                                    = base_primary / ratio         sample side secondary, ratio = primary / secondary
                                                                   of the consumed channel's OWN group (VT or CT)
    pu                              = sample / denominator         samples are never scaled
A transformer RATING is never a base; the ratio only moves a denominator between sides.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal as D, getcontext
from pathlib import Path

getcontext().prec = 60
S3 = D(3).sqrt()
HERE = Path(__file__).resolve().parent
JSON_PATH = HERE / "pu_mig_oracle_expected.json"

CASES: list[dict] = []


def case(cid, title, inputs, expected_pu=None, *, block=None, note=None, **extra):
    CASES.append({
        "id": cid, "title": title, "inputs": inputs,
        "expected_pu": None if expected_pu is None else format(expected_pu, ".15f"),
        "expected_block": block, "note": note, **extra,
    })


# ------------------------------------------------------------------ Voltage: 275 kV system, VT 275 kV / 110 V
VLL = D(275000)
VT_P, VT_S = D(275000), D(110)
R_VT = VT_P / VT_S                                   # exactly 2500
BASE_LN = VLL / S3
IN_V = {"nominal_ll_V": "275000", "vt_primary_V": "275000", "vt_secondary_V": "110", "ratio": "2500"}

case("V1", "Primary L-N at nominal", {**IN_V, "side": "primary", "sample_V": "275000/sqrt3"}, (VLL / S3) / BASE_LN)
case("V2", "Secondary L-N at nominal", {**IN_V, "side": "secondary", "sample_V": "275000/sqrt3/2500"},
     (VLL / S3 / R_VT) / (BASE_LN / R_VT), denominator_V=format(BASE_LN / R_VT, ".12f"))
case("V3", "Primary L-N at 0.87 pu", {**IN_V, "side": "primary", "sample_V": "0.87*275000/sqrt3"},
     (D("0.87") * VLL / S3) / BASE_LN)
case("V4", "Secondary L-N at 0.87 pu", {**IN_V, "side": "secondary", "sample_V": "0.87*275000/sqrt3/2500"},
     (D("0.87") * VLL / S3 / R_VT) / (BASE_LN / R_VT))
case("V5", "Secondary L-L at nominal", {**IN_V, "side": "secondary", "sample_V": "110"}, D(110) / (VLL / R_VT),
     denominator_V="110")
case("V6", "HAZARD (today, side unknown): secondary L-N sample / primary denominator",
     {**IN_V, "side": "unknown", "sample_V": "275000/sqrt3/2500"}, (VLL / S3 / R_VT) / BASE_LN,
     note="Executed against the current gate: status=configured, reference_compatibility=unverified, 0.0004 pu.")

# ------------------------------------------------------------------ Voltage: VT primary differs from system nominal (the 4.35 % case)
NOM_B = D(132000)
VT_BP, VT_BS = D(138000), D(110)
R_B = VT_BP / VT_BS                                  # 1254.545454...
SAMPLE_B = NOM_B / R_B                               # secondary L-L at system nominal = 105.217391304...
IN_B = {"nominal_ll_V": "132000", "vt_primary_V": "138000", "vt_secondary_V": "110", "ratio": "138000/110",
        "side": "secondary", "sample_V": "132000*110/138000 (system at nominal, L-L)"}
case("VT1", "Secondary L-L; denominator = nominal / ratio (correct)", IN_B, SAMPLE_B / (NOM_B / R_B),
     denominator_V=format(NOM_B / R_B, ".12f"))
case("VT1x", "Same sample divided by vt_secondary_V (a transformer RATING used as the base) — WRONG", IN_B,
     SAMPLE_B / VT_BS, note="Shows the discrepancy only. error = 1 - 132/138 = 1/23 = 4.3478...%",
     error_vs_unity=format(SAMPLE_B / VT_BS - 1, ".15f"))

# ------------------------------------------------------------------ Voltage: legacy secondary_voltage_ll_v path (preserved, OD-4)
IN_L = {"nominal_ll_V": None, "secondary_voltage_ll_v": "110", "side": "secondary"}
case("VL1", "Legacy secondary base, no nominal, L-N", {**IN_L, "sample_V": "110/sqrt3"}, (D(110) / S3) / (D(110) / S3),
     denominator_V=format(D(110) / S3, ".12f"), note="Numerics identical to today's `base_reference_side=secondary` path.")
case("VL2", "Legacy secondary base, no nominal, L-L", {**IN_L, "sample_V": "110"}, D(110) / D(110))
case("VL3", "Legacy secondary_voltage_ll_v wins over nominal/ratio (DECISION D-PREC option P1: preserve history)",
     {**IN_B, "secondary_voltage_ll_v": "110"}, SAMPLE_B / D(110), denominator_V="110",
     note="Historical output preserved; the 4.35 % disagreement must at least be reported as a diagnostic.")
case("VL3b", "Same inputs, nominal/ratio wins (D-PREC option P2)", {**IN_B, "secondary_voltage_ll_v": "110"},
     SAMPLE_B / (NOM_B / R_B), denominator_V=format(NOM_B / R_B, ".12f"))
case("VM1", "Primary sample against a secondary-only base converted by the VT ratio (conversion needed, ratio valid)",
     {"secondary_voltage_ll_v": "110", "vt_primary_V": "275000", "vt_secondary_V": "110", "side": "primary", "sample_V": "275000"},
     D(275000) / (D(110) * R_VT), denominator_V=format(D(110) * R_VT, ".6f"))

# ------------------------------------------------------------------ Calculated voltage
A = BASE_LN / R_VT                                   # secondary L-N phase magnitude at nominal
LL_FROM_LN = A * S3                                  # |Va - Vb| with Vb = Va at -120 deg is exactly a*sqrt3
case("CV1", "Calculated L-L = |Va - Vb|, both legs Secondary, same group/ratio",
     {**IN_V, "legs": "Va,Vb secondary", "sample_V": "a*sqrt3, a=275000/sqrt3/2500"}, LL_FROM_LN / (VLL / R_VT),
     denominator_V="110")
case("CV2", "HAZARD (today): the same calculated channel with side unknown", {**IN_V, "side": "unknown"},
     LL_FROM_LN / VLL)
case("CV3", "Calculated Voltage, one leg Primary and one Secondary", {"legs": "Va primary, Vb secondary"},
     block="calculated_leaf_sides_differ")
case("CV4", "Calculated Voltage across two groups with different VT ratios", {"legs": "Va in G1 (2500), Vb in G2 (1250)"},
     block="calculated_leaf_ratio_authority_differs")

# ------------------------------------------------------------------ Current: 1000 MVA, 275 kV, CT 2000:1
SB = D(1000000000)
IBASE = SB / (S3 * VLL)
CT = D(2000)
IN_I = {"sbase_VA": "1000000000", "nominal_ll_V": "275000", "ct_ratio": "2000"}
case("I1", "Primary current at Ibase", {**IN_I, "side": "primary", "sample_A": "Ibase"}, IBASE / IBASE,
     ibase_A=format(IBASE, ".9f"))
case("I2", "Secondary current at Ibase/CT", {**IN_I, "side": "secondary", "sample_A": "Ibase/2000"},
     (IBASE / CT) / (IBASE / CT), denominator_A=format(IBASE / CT, ".9f"))
case("I3", "Secondary 1.0 A", {**IN_I, "side": "secondary", "sample_A": "1.0"}, D(1) / (IBASE / CT))
case("I4", "HAZARD: secondary 1.0 A / primary Ibase", {**IN_I, "side": "unknown", "sample_A": "1.0"}, D(1) / IBASE)
case("IM1", "Mixed: primary V + secondary I -> current denominator uses CT only; voltage side never touches Ibase",
     {**IN_I, "V": "primary", "I": "secondary", "sample_A": "1.0"}, D(1) / (IBASE / CT))
case("IM2", "Mixed: secondary V + primary I", {**IN_I, "V": "secondary", "I": "primary", "sample_A": "2099.6"},
     D("2099.6") / IBASE)

# ------------------------------------------------------------------ Manual bases
case("F1", "Manual Ibase 2100 A declared Primary; secondary recording; CT 4000", {"manual_A": "2100", "base_side": "primary",
     "side": "secondary", "ct_ratio": "4000", "sample_A": "0.525"}, D("0.525") / (D(2100) / D(4000)))
case("F2", "Manual Ibase 1.0 A declared Secondary; secondary recording (direct, no ratio)",
     {"manual_A": "1.0", "base_side": "secondary", "side": "secondary", "sample_A": "0.5"}, D("0.5") / D(1))
case("F3", "Manual Ibase 1.0 A declared Secondary; primary recording; CT 2000",
     {"manual_A": "1.0", "base_side": "secondary", "side": "primary", "ct_ratio": "2000", "sample_A": "1000"},
     D(1000) / (D(1) * CT), denominator_A="2000")
case("F4", "Manual Ibase, declared side UNKNOWN: never assumed Primary", {"manual_A": "1000", "base_side": "unknown",
     "side": "primary"}, block="manual_base_side_unknown",
     note="Strict resolver: no conversion. Historical Unverified numerics are the separate OD-2 question.")
case("F5", "Manual Ibase declared Secondary; primary recording; CT missing", {"manual_A": "1.0", "base_side": "secondary",
     "side": "primary", "ct": None}, block="current_ratio_unavailable")

# ------------------------------------------------------------------ Calculated current
case("CC1", "Calculated Current = I1 + I2, both Secondary, same group (CT 2000)",
     {**IN_I, "legs": "0.5 A + 0.25 A, secondary, same group"}, D("0.75") / (IBASE / CT))
case("CC2", "Calculated Current, leaves Primary 1000 A + Secondary 0.5 A", {"legs": "mixed"},
     block="calculated_leaf_sides_differ", note="Adding secondary amperes to primary amperes is arithmetically meaningless.")

# ------------------------------------------------------------------ Strict-resolver blocks (no numeric pu may be produced)
for cid, title, why in [
    ("B1", "Secondary sample, VT ratio missing", "voltage_ratio_unavailable"),
    ("B2", "Secondary sample, ratio 0 / negative / NaN / inf", "voltage_ratio_invalid"),
    ("B3", "Secondary sample, ratio authority untrusted", "voltage_ratio_untrusted"),
    ("B4", "Secondary sample, groups with conflicting ratios", "voltage_ratio_conflict"),
    ("B5", "Secondary sample, channel in no Measurement Group", "voltage_ratio_no_group"),
    ("B6", "Side unresolved or inferred-only (strict resolver)", "measurement_side_not_strict"),
    ("B7", "Group declares mixed sides, no engineer choice", "measurement_group_side_conflict"),
    ("B8", "Secondary Current sample, CT missing", "current_ratio_unavailable"),
]:
    case(cid, title, {}, block=why)

# ------------------------------------------------------------------ Invariants
for k in (D(0), D("0.5"), D("0.87"), D(1), D("1.1")):
    p = (VLL / S3) * k
    s = p / R_VT
    assert abs(p / BASE_LN - s / (BASE_LN / R_VT)) < D("1e-50"), k
assert abs(D(1) / D(23) - (1 - NOM_B / VT_BP)) < D("1e-50")                # 4.3478...% error is exactly 1/23
assert abs((SAMPLE_B / VT_BS - 1) + D(1) / D(23)) < D("1e-50")
assert abs(LL_FROM_LN - D(110)) < D("1e-50")
for c in CASES:
    assert (c["expected_pu"] is None) == (c["expected_block"] is not None), c["id"]


def main() -> int:
    for c in CASES:
        out = c["expected_pu"] if c["expected_pu"] is not None else f"BLOCK: {c['expected_block']}"
        print(f"{c['id']:<5s} {out:<34s} {c['title']}")
    text = json.dumps(CASES, indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv and (not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != text):
        print("expected-values JSON differs", file=sys.stderr)
        return 1
    JSON_PATH.write_text(text, encoding="utf-8")
    print("\nall invariants hold (primary == secondary pu; 4.3478% == 1/23)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
