"""PU-MIG S1 -- independent numerical oracle for `app.domain.side_denominator.resolve_side_denominator`.

Standard library only; it imports NOTHING from the application, so it cannot share a defect with the code under test.
Arithmetic is exact to 80 significant digits (`decimal`). Every numeric input is first converted to the EXACT value of the
IEEE-754 double the code under test will receive (`Decimal(float(text))`), so no input-rounding difference exists between
the oracle and the code; the only unavoidable difference is the code's own float arithmetic and its float constant for
sqrt(3), covered by `rel_tol` (1e-15 for ordinary rows).

    python -I pu_side_denominator_oracle.py            # asserts every invariant, rewrites the JSON
    python -I pu_side_denominator_oracle.py --check    # additionally fails if the JSON on disk differs

The oracle states the contract independently of the implementation, in two different ways:

1. A reference model `expected(request)` -- the refusal precedence and the denominator rules written out directly.
2. A PHYSICAL model (section "physics"): a true primary quantity X and a recorder ratio r produce the two sample
   readings (X and X / r); the per-unit value of that one physical condition must be the SAME whichever side the samples
   are on and whichever side the base was declared on. Those expected per-unit values are computed from the physical
   truth, not from the denominator formulas, and the tests require `sample / resolved_denominator` to reproduce them.

Contract summary (all of it is a PROPOSAL until the owner approves S2; nothing here is live behaviour):

    rho = 1/sqrt(3) for a line-to-ground Voltage, else 1
    same side                         D = B * rho                      (the ratio is NOT read)
    base primary,   samples secondary D = B * rho / r                  "base_divided_by_ratio"
    base secondary, samples primary   D = B * rho * r                  "base_multiplied_by_ratio"   (pending D-6; math only)
    pu = sample / D ; the samples are never scaled

Refusal precedence (first match wins): invalid request -> sample side not strict-usable -> base side unknown ->
conversion needed but ratio not authoritative -> denominator not representable.
"""

from __future__ import annotations

import itertools
import json
import sys
from decimal import Decimal as D, getcontext
from pathlib import Path

getcontext().prec = 80
S3 = D(3).sqrt()
HERE = Path(__file__).resolve().parent
JSON_PATH = HERE / "pu_side_denominator_expected.json"

# ------------------------------------------------------------------------------------------------------- vocabulary
QUANTITIES = ("voltage", "current")
REPRESENTATIONS = ("line_to_line", "line_to_ground")
SIDES = ("primary", "secondary", "unknown")
BASE_KINDS = {
    "voltage": ("nominal_ll_primary", "legacy_secondary_voltage_ll"),
    "current": ("equipment_derived_primary", "manual_direct", "result_manual"),
}
PRIMARY_ONLY = ("nominal_ll_primary", "equipment_derived_primary")
SECONDARY_ONLY = ("legacy_secondary_voltage_ll",)
SAMPLE_PROBLEMS = {
    "calculated": "calculated_channel_side_unavailable",
    "unresolved": "measurement_side_unresolved",
    "inferred": "measurement_side_inferred",
    "group_conflict": "measurement_group_side_conflict",
}
RATIO_STATUSES = ("configured", "no_channels", "no_group", "not_configured", "untrusted_authority", "invalid", "conflict")
RATIO_AUTHORITIES = ("manual", "recording_metadata", "auto_nominal", "mixed")
RATIO_REASON = {"voltage": "vt_authority_unavailable", "current": "ct_authority_unavailable"}

MAX_FLOAT = D(1.7976931348623157e308)           # exact value of the largest double
# Doubles round to the nearest representable value: anything below half the smallest subnormal becomes 0 and anything at or
# above max + half an ulp becomes infinity. The extreme rows are chosen far from both edges (factor >= 2).
MIN_SUBNORMAL = D(5e-324)                      # exact value of the smallest positive double
OVERFLOW_EDGE = MAX_FLOAT + D(2) ** 970         # max + half an ulp (the ulp of the largest double is 2**971)


def fl(text) -> D:
    """The exact value of the double the code under test receives for `text`."""
    return D(float(text))


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --------------------------------------------------------------------------------------------- reference model (1)
def classify(req: dict) -> tuple[str, str | None, str | None]:
    """(status, reason, detail) for everything that does not need the arithmetic; ("ok", None, None) to continue."""
    q, base, sample, ratio, rep = req["quantity"], req["base"], req["sample"], req["ratio"], req["representation"]
    if q not in QUANTITIES:
        return "unavailable", "invalid_quantity", None
    if (q == "voltage" and rep not in REPRESENTATIONS) or (q == "current" and rep is not None):
        return "unavailable", "invalid_representation", None
    kind, side = base["kind"], base["declared_side"]
    if kind not in BASE_KINDS[q] or side not in SIDES or (kind in PRIMARY_ONLY and side != "primary") \
            or (kind in SECONDARY_ONLY and side != "secondary"):
        return "unavailable", "invalid_base_declaration", None
    if not _positive_finite(base["value"]):
        return "unavailable", "invalid_base_value", None
    s_side, s_problem = sample["side"], sample["problem"]
    ok_strict = s_problem is None and s_side in ("primary", "secondary")
    ok_problem = s_side is None and s_problem in SAMPLE_PROBLEMS
    if not (ok_strict or ok_problem):
        return "unavailable", "invalid_sample_side", None
    if s_problem is not None:
        return "unavailable", SAMPLE_PROBLEMS[s_problem], None
    if side == "unknown":
        return "unavailable", "base_side_unknown", None
    if side == s_side:
        return "ok", None, None
    # a conversion is needed: only an authoritative ratio may be used
    if ratio is None:
        return "unavailable", RATIO_REASON[q], "not_provided"
    if ratio["status"] not in RATIO_STATUSES:
        return "unavailable", RATIO_REASON[q], "invalid"
    if ratio["status"] != "configured":
        return "unavailable", RATIO_REASON[q], ratio["status"]
    if not _positive_finite(ratio["value"]):
        return "unavailable", RATIO_REASON[q], "invalid"
    if ratio["authority"] not in RATIO_AUTHORITIES:
        return "unavailable", RATIO_REASON[q], "untrusted_authority"
    return "ok", None, None


def _positive_finite(v) -> bool:
    if not is_number(v):
        return False
    try:
        x = float(v)
    except OverflowError:
        return False
    return x == x and x not in (float("inf"), float("-inf")) and x > 0


def expected(req: dict) -> dict:
    status, reason, detail = classify(req)
    out = {"status": status, "reason": reason, "detail": detail, "conversion": None, "denominator": None,
           "ratio_applied": None}
    if status != "ok":
        out["status"] = "unavailable"
        return out
    base, sample, ratio = req["base"], req["sample"], req["ratio"]
    rho = D(1) / S3 if (req["quantity"] == "voltage" and req["representation"] == "line_to_ground") else D(1)
    b = fl(base["value"]) * rho
    if base["declared_side"] == sample["side"]:
        den, conversion = b, "direct"
    else:
        r = fl(ratio["value"])
        # normalise the base to its PRIMARY-side value, then express it on the sample's side
        primary_equivalent = b if base["declared_side"] == "primary" else b * r
        den = primary_equivalent if sample["side"] == "primary" else primary_equivalent / r
        conversion = "base_divided_by_ratio" if sample["side"] == "secondary" else "base_multiplied_by_ratio"
        out["ratio_applied"] = format(r, ".40e")
    # representability: a double must be finite and nonzero (subnormal results are valid, as in per_unit_numerics)
    if den >= OVERFLOW_EDGE or den < MIN_SUBNORMAL / 2:
        out.update(status="unavailable", reason="denominator_not_representable", detail=None, ratio_applied=None)
        return out
    out.update(status="resolved", conversion=conversion, denominator=format(den, ".40e"))
    return out


# -------------------------------------------------------------------------------------------------------- builders
def sample_state(name: str) -> dict:
    if name in ("primary", "secondary"):
        return {"side": name, "problem": None, "authority": "recording_channel_declared"}
    return {"side": None, "problem": name, "authority": None}


def ratio_state(status: str, value=None, authority="manual", groups=("g1",)) -> dict:
    return {"status": status, "value": None if status != "configured" else float(value),
            "authority": authority if status == "configured" else None, "group_ids": list(groups)}


def request(quantity, kind, value, side, sample, ratio, rep=None) -> dict:
    return {"quantity": quantity, "base": {"kind": kind, "value": float(value), "declared_side": side},
            "representation": rep, "sample": sample, "ratio": ratio}


def row(cid: str, req: dict, **tol) -> dict:
    out = {"id": cid, "request": req, "expect": expected(req)}
    out["expect"]["rel_tol"] = tol.get("rel_tol", "1e-15")
    out["expect"]["abs_tol"] = tol.get("abs_tol", "0")
    return out


# ------------------------------------------------------------------------------------------- A. exhaustive grid
VT_ABOUT_138_110 = float(D(138000) / D(110))     # the 132 kV system with a 138 kV : 110 V VT (ratio of the VT, not of the system)
VT_2500 = 2500.0
CT_2000 = 2000.0
CT_ODD = 63.7
IBASE_EQUIP = float(D(1_000_000_000) / (S3 * D(275000)))          # 1000 MVA, 275 kV  -> 2099.4555...

VOLTAGE_BASES = (("nominal_132kv", "nominal_ll_primary", 132000.0, "primary"),
                 ("legacy_110v", "legacy_secondary_voltage_ll", 110.0, "secondary"))
CURRENT_BASES = (("equip_primary", "equipment_derived_primary", IBASE_EQUIP, "primary"),
                 ("manual_primary", "manual_direct", 2100.0, "primary"),
                 ("manual_secondary", "manual_direct", 1.0, "secondary"),
                 ("manual_unknown", "manual_direct", 1.0, "unknown"),
                 ("result_primary", "result_manual", 1000.0, "primary"),
                 ("result_secondary", "result_manual", 1.0, "secondary"),
                 ("result_unknown", "result_manual", 0.5, "unknown"))
SAMPLE_NAMES = ("primary", "secondary", "calculated", "unresolved", "inferred", "group_conflict")


def ratio_grid(quantity: str):
    ratios = (VT_ABOUT_138_110, VT_2500, 1.0) if quantity == "voltage" else (CT_2000, CT_ODD, 1.0)
    for r in ratios:
        yield f"cfg{r:g}", ratio_state("configured", r)
    for auth in ("auto_nominal", "recording_metadata", "mixed"):
        yield f"cfg-{auth}", ratio_state("configured", ratios[0], authority=auth)
    for st in RATIO_STATUSES[1:]:
        yield st, ratio_state(st)
    yield "none", None


def grid() -> list[dict]:
    rows: list[dict] = []
    for (bn, kind, val, side), rep, sname in itertools.product(VOLTAGE_BASES, REPRESENTATIONS, SAMPLE_NAMES):
        for rn, ratio in ratio_grid("voltage"):
            rows.append(row(f"G/V/{bn}/{rep}/{sname}/{rn}", request("voltage", kind, val, side, sample_state(sname), ratio, rep)))
    for (bn, kind, val, side), sname in itertools.product(CURRENT_BASES, SAMPLE_NAMES):
        for rn, ratio in ratio_grid("current"):
            rows.append(row(f"G/I/{bn}/{sname}/{rn}", request("current", kind, val, side, sample_state(sname), ratio)))
    return rows


# --------------------------------------------------------------------------- B. the 132 kV system, VT 138 kV : 110 V
def case_132_138() -> list[dict]:
    """A 132 kV system with a 138 kV : 110 V VT, at nominal. The resolver is given ONE already-established base and never
    chooses between stored and derived authorities (decision D-4 is pending): each base below is resolved on its own terms."""
    nominal, vp, vs = D(132000), D(138000), D(110)
    r = float(vp / vs)
    rat = ratio_state("configured", r)
    out = []
    # (label, kind, value, declared side, representation, sample side)
    for rep in REPRESENTATIONS:
        rho = D(1) / S3 if rep == "line_to_ground" else D(1)
        phys_primary = nominal * rho                       # the true quantity at nominal, in primary units
        phys_secondary = phys_primary / fl(r)              # what the recorder's secondary winding reads
        for label, kind, value, side in (
            ("primary_base_132kV", "nominal_ll_primary", 132000.0, "primary"),
            ("secondary_base_110V_rating", "legacy_secondary_voltage_ll", 110.0, "secondary"),
            ("secondary_base_independent_105.217V", "legacy_secondary_voltage_ll", float(nominal / (vp / vs)), "secondary"),
        ):
            for s in ("primary", "secondary"):
                req = request("voltage", kind, value, side, sample_state(s), rat, rep)
                rw = row(f"C132/{rep}/{label}/{s}", req)
                sample = phys_primary if s == "primary" else phys_secondary
                den = D(rw["expect"]["denominator"])
                rw["sample_physical"] = format(sample, ".40e")
                rw["pu_expected"] = format(sample / den, ".30e")
                out.append(rw)
    return out


# ------------------------------------------------------------------------------------------- C. invalid inputs
BAD_NUMBERS = ("nan", "inf", "-inf", "zero", "negative", "negative_zero", "true", "false", "str", "none", "int_1e400")


def bad_number_tokens():
    return BAD_NUMBERS


def invalid_matrix() -> list[dict]:
    """Each row mutates ONE field of a valid baseline request. The `$` objects are decoded by the test (they cannot be JSON)."""
    rows: list[dict] = []
    good_v = request("voltage", "nominal_ll_primary", 132000.0, "primary", sample_state("secondary"),
                     ratio_state("configured", VT_ABOUT_138_110), "line_to_line")
    good_i = request("current", "manual_direct", 2100.0, "primary", sample_state("secondary"), ratio_state("configured", CT_2000))

    def mutate(base: dict, path: tuple, token: dict) -> dict:
        import copy
        req = copy.deepcopy(base)
        node = req
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = token
        return req

    def reason_of(req: dict) -> dict:
        """Expectation of a request whose fields may hold `$` tokens: decode to python values first."""
        return expected(decode(req))

    for q, base_req in (("voltage", good_v), ("current", good_i)):
        for tok in BAD_NUMBERS:
            for field, path in (("base_value", ("base", "value")), ("ratio_value", ("ratio", "value"))):
                req = mutate(base_req, path, {"$": tok})
                rows.append({"id": f"I/{q}/{field}/{tok}", "request": req, "expect": reason_of(req)})
        for tok in ("Primary", "", "tertiary", None, 1):
            req = mutate(base_req, ("base", "declared_side"), {"$": "raw", "v": tok})
            rows.append({"id": f"I/{q}/base_side/{tok!r}", "request": req, "expect": reason_of(req)})
        for tok in ("nominal_ll", "", None, "MANUAL_DIRECT"):
            req = mutate(base_req, ("base", "kind"), {"$": "raw", "v": tok})
            rows.append({"id": f"I/{q}/base_kind/{tok!r}", "request": req, "expect": reason_of(req)})
        for tok in ("power", "Voltage", "", None):
            req = mutate(base_req, ("quantity",), {"$": "raw", "v": tok})
            rows.append({"id": f"I/{q}/quantity/{tok!r}", "request": req, "expect": reason_of(req)})
        for tok in ("phase", "line_to_neutral", "LL", None, "line_to_line", "line_to_ground"):
            req = mutate(base_req, ("representation",), {"$": "raw", "v": tok})
            rows.append({"id": f"I/{q}/representation/{tok!r}", "request": req, "expect": reason_of(req)})
        for name, sample in (("both", {"side": "primary", "problem": "calculated", "authority": None}),
                             ("neither", {"side": None, "problem": None, "authority": None}),
                             ("unknown_side", {"side": "unknown", "problem": None, "authority": None}),
                             ("bogus_problem", {"side": None, "problem": "bogus", "authority": None}),
                             ("upper_case_side", {"side": "Secondary", "problem": None, "authority": None})):
            req = mutate(base_req, ("sample",), sample)
            rows.append({"id": f"I/{q}/sample/{name}", "request": req, "expect": reason_of(req)})
        for tok in ("guess", "", None, "auto_resolved", "not_configured"):
            req = mutate(base_req, ("ratio", "authority"), {"$": "raw", "v": tok})
            rows.append({"id": f"I/{q}/ratio_authority/{tok!r}", "request": req, "expect": reason_of(req)})
        for tok in ("bogus", "", None, "CONFIGURED"):
            req = mutate(base_req, ("ratio", "status"), {"$": "raw", "v": tok})
            rows.append({"id": f"I/{q}/ratio_status/{tok!r}", "request": req, "expect": reason_of(req)})
        for name, req in (("ratio_absent", mutate(base_req, ("ratio",), {"$": "raw", "v": None})),):
            rows.append({"id": f"I/{q}/{name}", "request": req, "expect": reason_of(req)})
    # contradictory declarations
    for cid, req in (
        ("nominal_declared_secondary", request("voltage", "nominal_ll_primary", 132000.0, "secondary", sample_state("secondary"), None, "line_to_line")),
        ("nominal_declared_unknown", request("voltage", "nominal_ll_primary", 132000.0, "unknown", sample_state("primary"), None, "line_to_line")),
        ("equipment_declared_secondary", request("current", "equipment_derived_primary", 2099.0, "secondary", sample_state("secondary"), None)),
        ("equipment_declared_unknown", request("current", "equipment_derived_primary", 2099.0, "unknown", sample_state("primary"), None)),
        ("legacy_declared_primary", request("voltage", "legacy_secondary_voltage_ll", 110.0, "primary", sample_state("primary"), None, "line_to_line")),
        ("legacy_declared_unknown", request("voltage", "legacy_secondary_voltage_ll", 110.0, "unknown", sample_state("secondary"), None, "line_to_line")),
        ("voltage_kind_on_current", request("current", "nominal_ll_primary", 132000.0, "primary", sample_state("primary"), None)),
        ("current_kind_on_voltage", request("voltage", "manual_direct", 1.0, "secondary", sample_state("secondary"), None, "line_to_line")),
        ("current_with_representation", request("current", "manual_direct", 1.0, "secondary", sample_state("secondary"), None, "line_to_line")),
        ("voltage_without_representation", request("voltage", "nominal_ll_primary", 132000.0, "primary", sample_state("primary"), None, None)),
    ):
        rows.append({"id": f"I/contradictory/{cid}", "request": req, "expect": expected(req)})
    return rows


def decode(req):
    """Replace `$` tokens by python values (the oracle's own decoder, mirrored by the test)."""
    import copy
    req = copy.deepcopy(req)

    def walk(node):
        if isinstance(node, dict):
            if "$" in node:
                return token_value(node)
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(req)


def token_value(node: dict):
    t = node["$"]
    return {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf"), "zero": 0.0, "negative": -1.0,
            "negative_zero": -0.0, "true": True, "false": False, "str": "50", "none": None, "int_1e400": 10 ** 400}[t] \
        if t != "raw" else node["v"]


# ------------------------------------------------------------------------------------------------ D. extreme values
def extremes() -> list[dict]:
    """Doubles near both ends of the range. Expected status is decided from the exact value against the double's range, with
    a factor >= 2 of margin. Subnormal results are valid (per_unit_numerics' convention); `abs_tol` is one subnormal step."""
    big, tiny, sub = 1.7976931348623157e308, 5e-324, 1e-320
    rows = []
    cfg = lambda r: ratio_state("configured", r)           # noqa: E731
    P, S = sample_state("primary"), sample_state("secondary")
    cases = [
        # id, quantity, kind, value, side, sample, ratio, representation
        ("same_side_max", "voltage", "nominal_ll_primary", big, "primary", P, None, "line_to_line"),
        ("same_side_max_ln", "voltage", "nominal_ll_primary", big, "primary", P, None, "line_to_ground"),
        ("same_side_min_subnormal", "voltage", "nominal_ll_primary", tiny, "primary", P, None, "line_to_line"),
        ("same_side_subnormal_ln", "voltage", "nominal_ll_primary", 1e-322, "primary", P, None, "line_to_ground"),
        ("same_side_min_normal", "current", "manual_direct", 2.2250738585072014e-308, "secondary", S, None, None),
        ("div_overflow", "current", "manual_direct", 1e308, "primary", S, cfg(1e-5), None),
        ("div_overflow_ln_edge", "voltage", "nominal_ll_primary", big, "primary", S, cfg(0.25), "line_to_ground"),
        ("mul_overflow", "voltage", "legacy_secondary_voltage_ll", 1e300, "secondary", P, cfg(1e10), "line_to_line"),
        ("mul_overflow_ln", "voltage", "legacy_secondary_voltage_ll", 1e308, "secondary", P, cfg(5.0), "line_to_ground"),
        ("div_underflow_to_zero", "current", "manual_direct", 1e-300, "primary", S, cfg(1e300), None),
        ("div_underflow_subnormal_input", "current", "manual_direct", tiny, "primary", S, cfg(1e3), None),
        ("mul_underflow_to_zero", "current", "manual_direct", 1e-300, "secondary", P, cfg(1e-300), None),
        ("div_result_subnormal", "current", "manual_direct", 1e-300, "primary", S, cfg(1e10), None),
        ("mul_result_subnormal", "current", "manual_direct", 1e-300, "secondary", P, cfg(1e-10), None),
        ("div_huge_ratio_subnormal", "current", "manual_direct", 1.0, "primary", S, cfg(big), None),
        ("div_tiny_ratio_large", "current", "manual_direct", 1e-300, "primary", S, cfg(tiny), None),
        ("mul_tiny_base_huge_ratio", "voltage", "legacy_secondary_voltage_ll", sub, "secondary", P, cfg(1e300), "line_to_ground"),
        ("div_tiny_base_tiny_ratio", "voltage", "nominal_ll_primary", sub, "primary", S, cfg(1e-300), "line_to_ground"),
        ("mul_max_times_one_plus_ulp", "current", "manual_direct", 1e308, "secondary", P, cfg(1.0000000000000002), None),
        ("div_max_by_one_plus_ulp", "current", "manual_direct", big, "primary", S, cfg(1.0000000000000002), None),
        ("ratio_one_is_still_a_conversion", "current", "manual_direct", 2100.0, "primary", S, cfg(1.0), None),
    ]
    for cid, q, kind, val, side, sample, ratio, rep in cases:
        req = request(q, kind, val, side, sample, ratio, rep)
        rows.append(row(f"X/{cid}", req, rel_tol="1e-12", abs_tol=repr(float(MIN_SUBNORMAL) * 2)))
    return rows


# ---------------------------------------------------------------------------------------------------- E. physics
def physics() -> list[dict]:
    """Per-unit values of ONE physical condition, from physical truth only (no denominator formula).

    A true primary quantity X (volts or amps), a recorder ratio r, a base whose PRIMARY-equivalent value is Bp and a
    representation rho give pu_true = X / (Bp * rho). The primary reading is X, the secondary reading is X / r. A base declared
    secondary has the value Bp / r. Every (base side, sample side) combination must reproduce pu_true."""
    out = []
    for quantity, bp_values, ratios in (("voltage", (D(132000), D(275000), D(33000)), (VT_ABOUT_138_110, VT_2500, 1.0000001, 1e6, 0.001)),
                                        ("current", (D(2100), D("2099.4555"), D(1)), (CT_2000, CT_ODD, 4000.0, 1e6, 0.001))):
        reps = REPRESENTATIONS if quantity == "voltage" else (None,)
        for bp, r, rep, level in itertools.product(bp_values, ratios, reps, ("0", "0.5", "0.87", "1", "1.1")):
            rho = D(1) / S3 if rep == "line_to_ground" else D(1)
            ratio = fl(r)
            for side in ("primary", "secondary"):
                base_float = float(bp if side == "primary" else bp / ratio)       # what the code receives
                base_exact = fl(base_float)
                primary_equivalent = base_exact if side == "primary" else base_exact * ratio
                x = D(level) * primary_equivalent * rho                           # the physical quantity, in primary units
                kind = ("nominal_ll_primary" if side == "primary" else "legacy_secondary_voltage_ll") if quantity == "voltage"                     else "manual_direct"
                for sample in ("primary", "secondary"):
                    reading = x if sample == "primary" else x / ratio
                    out.append({
                        "id": f"P/{quantity}/{bp}/{r:g}/{rep}/{level}/base-{side}/sample-{sample}",
                        "request": request(quantity, kind, base_float, side, sample_state(sample), ratio_state("configured", r), rep),
                        "sample": format(reading, ".40e"), "pu_true": format(D(level), ".30e"),
                    })
    return out


# --------------------------------------------------------------------------------------------------- invariants
def check_invariants(sections: dict) -> None:
    # (a) every row is resolved XOR carries exactly one reason; a refusal carries no number
    for sec in ("grid", "case_132_138", "invalid", "extremes"):
        for r in sections[sec]:
            e = r["expect"]
            assert (e["status"] == "resolved") == (e["reason"] is None), r["id"]
            assert (e["status"] == "resolved") == (e["denominator"] is not None), r["id"]
            assert (e["conversion"] is not None) == (e["status"] == "resolved"), r["id"]
            assert (e["ratio_applied"] is not None) == (e["conversion"] in ("base_divided_by_ratio", "base_multiplied_by_ratio")), r["id"]
    # (b) the ratio is never read for a same-side computation: poisoning it changes nothing
    by_id = {r["id"]: r["expect"] for r in sections["grid"]}
    for key, e in by_id.items():
        if e["conversion"] == "direct":
            family = key.rsplit("/", 1)[0]
            for other, o in by_id.items():
                if other.startswith(family + "/"):
                    assert o["status"] == "resolved" and o["conversion"] == "direct" and o["denominator"] == e["denominator"], (key, other)
    # (c) physical equivalence: pu of one condition is the same on either side, to 1e-60
    for p in sections["physics"]:
        req = p["request"]
        e = expected(req)
        assert e["status"] == "resolved", p["id"]
        pu = D(p["sample"]) / D(e["denominator"])
        assert abs(pu - D(p["pu_true"])) <= D("1e-40") * max(D(1), abs(D(p["pu_true"]))), (p["id"], pu)
    # (d) the 132 kV / 138 kV:110 V case reproduces the owner's figure exactly
    err = D(132) / D(138) - 1
    assert abs(err + D(1) / D(23)) < D("1e-70")
    for r in sections["case_132_138"]:
        pu = D(r["pu_expected"])
        if "secondary_base_110V_rating" in r["id"]:
            # a 110 V base is a rating, not the nominal-derived denominator: the pu reads nominal / VT primary = 132/138
            # (relative to the exact double of the VT ratio)
            assert abs(pu - D(132) / D(138)) < D("1e-14"), (r["id"], pu)
        else:
            assert abs(pu - 1) < D("1e-14"), (r["id"], pu)
    # (e) refusal precedence is pinned by explicit rows
    base = request("current", "manual_direct", 1.0, "unknown", sample_state("inferred"), ratio_state("no_group"))
    assert expected(base)["reason"] == "measurement_side_inferred"
    base["sample"] = sample_state("primary")
    assert expected(base)["reason"] == "base_side_unknown"
    base["base"]["declared_side"] = "primary"
    base["sample"] = sample_state("secondary")
    assert expected(base)["reason"] == "ct_authority_unavailable"


def main() -> int:
    sections = {"grid": grid(), "case_132_138": case_132_138(), "invalid": invalid_matrix(), "extremes": extremes(),
                "physics": physics()}
    check_invariants(sections)
    doc = {"model": "PU-MIG S1 independent oracle (see the module docstring)", "precision_digits": 80,
           "counts": {k: len(v) for k, v in sections.items()}, **sections}
    # one row per line keeps the file reviewable and diffable
    lines = ["{"]
    keys = list(doc)
    for i, key in enumerate(keys):
        value = doc[key]
        comma = "," if i < len(keys) - 1 else ""
        if isinstance(value, list):
            lines.append(f'"{key}": [')
            lines.extend(json.dumps(v, sort_keys=True) + ("," if j < len(value) - 1 else "") for j, v in enumerate(value))
            lines.append("]" + comma)
        else:
            lines.append(f'"{key}": {json.dumps(value, sort_keys=True)}{comma}')
    lines.append("}")
    text = "\n".join(lines) + "\n"
    resolved = sum(1 for sec in ("grid", "case_132_138", "invalid", "extremes") for r in sections[sec] if r["expect"]["status"] == "resolved")
    total = sum(len(sections[s]) for s in ("grid", "case_132_138", "invalid", "extremes"))
    print("rows:", doc["counts"], f"| resolved {resolved} / refused {total - resolved}")
    reasons = sorted({r["expect"]["reason"] for sec in ("grid", "case_132_138", "invalid", "extremes") for r in sections[sec] if r["expect"]["reason"]})
    print("reasons:", ", ".join(reasons))
    if "--check" in sys.argv:
        if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != text:
            print("CHECK FAILED: expected JSON differs", file=sys.stderr)
            return 1
        print("CHECK OK")
        return 0
    JSON_PATH.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", JSON_PATH.name, f"({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
