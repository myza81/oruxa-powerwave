"""PU-MIG S1 -- the pure side-denominator resolver, against independently derived numerical oracles.

`resolve_side_denominator` is a pure function that is not connected to any consumer (an import tripwire below proves it). These
tests pin its mathematical contract:

* every row of the S0 final-contract table (324 rows, unchanged, sha256-pinned) and of the S1 oracle (858-row exhaustive grid,
  the 132 kV / 138 kV:110 V case, 122 invalid or contradictory inputs, 21 extreme doubles) -- see
  `fixtures/pu_side_denominator/pu_side_denominator_oracle.py`, which imports no application code;
* the physical-equivalence property: one condition read on either side gives the same per-unit value, from physical truth;
* Primary/Primary and same-side denominators are bit-identical to the production base resolvers they stand beside;
* refusals carry no number, precedence is deterministic, the ratio is never read for a same-side result;
* wide-range numeric properties against exact decimal arithmetic, and a never-raises fuzz.

A failure is a regression in the contract; the frozen expectations are never regenerated to make a test pass.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import math
import random
import subprocess
import sys
from decimal import Decimal, getcontext
from pathlib import Path

import pytest

from app.domain import side_denominator as sd
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.per_unit import PerUnitBaseProfile, resolve_per_unit
from app.domain.per_unit_numerics import SQRT_3
from app.domain.side_denominator import (
    SampleSide, SideBase, SideDenominator, SideRatio, resolve_side_denominator,
)
from app.domain.voltage_group_config import VoltageBaseConfiguration, resolve_voltage_base_for_group
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE

getcontext().prec = 80

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pu_side_denominator"
APP_DIR = Path(__file__).resolve().parents[1] / "app"
ORACLE_PATH = FIXTURES / "pu_side_denominator_oracle.py"
ORACLE = json.loads((FIXTURES / "pu_side_denominator_expected.json").read_text(encoding="utf-8"))
S0_PATH = FIXTURES / "pu_mig_s0_final_expected.json"
S0 = json.loads(S0_PATH.read_text(encoding="utf-8"))
S0_SHA256_PREFIX = "7eb5070144cd8d24"      # LF-normalised sha256 of the unchanged S0 final-contract expected table (git blob d387033)


# ------------------------------------------------------------------------------------------------------ adapters
_TOKENS = {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf"), "zero": 0.0, "negative": -1.0,
           "negative_zero": -0.0, "true": True, "false": False, "str": "50", "none": None, "int_1e400": 10 ** 400}


def _decode(node):
    if isinstance(node, dict):
        if "$" in node:
            return node["v"] if node["$"] == "raw" else _TOKENS[node["$"]]
        return {k: _decode(v) for k, v in node.items()}
    return node


def build(request: dict, *, default_authority: str | None = None, numeric_strings: bool = False):
    """(positional args, kwargs) for `resolve_side_denominator` from a frozen request row."""
    req = _decode(request)
    b, s, r = req["base"], req["sample"], req["ratio"]
    num = (lambda v: float(v)) if numeric_strings else (lambda v: v)       # only the S0 table encodes numbers as strings
    base = SideBase(kind=b["kind"], value=num(b["value"]), declared_side=b["declared_side"])
    sample = SampleSide(side=s["side"], problem=s["problem"], authority=s.get("authority"))
    ratio = None if r is None else SideRatio(
        status=r["status"], value=None if r["value"] is None else num(r["value"]),
        authority=r.get("authority", default_authority) if r["status"] == "configured" else r.get("authority"),
        group_ids=tuple(r.get("group_ids", ())))
    return (req["quantity"], base, sample, ratio), {"representation": req.get("representation")}


def run(request: dict, **kw) -> SideDenominator:
    args, kwargs = build(request, **kw)
    return resolve_side_denominator(*args, **kwargs)


def check(result: SideDenominator, expect: dict, *, rel_tol: Decimal | None = None, abs_tol: Decimal | None = None) -> None:
    assert result.status == expect["status"], (result.status, result.reason, expect)
    assert result.reason == expect["reason"], (result.reason, expect)
    if "detail" in expect:
        assert result.detail == expect["detail"], (result.detail, expect)
    assert result.conversion == expect["conversion"], (result.conversion, expect)
    if expect["denominator"] is None:
        assert result.denominator is None and result.ratio_applied is None and result.ratio_authority is None
        assert result.ratio_group_ids == () and result.resolved is False
        return
    rel = Decimal(expect.get("rel_tol", "1e-15")) if rel_tol is None else rel_tol
    absolute = Decimal(expect.get("abs_tol", "0")) if abs_tol is None else abs_tol
    exact = Decimal(expect["denominator"])
    assert math.isfinite(result.denominator) and result.denominator > 0
    assert abs(Decimal(result.denominator) - exact) <= rel * abs(exact) + absolute, (result.denominator, expect)
    assert result.denominator_side == result.sample_side
    if expect["ratio_applied"] is None:
        assert result.ratio_applied is None and result.ratio_authority is None
    else:
        assert math.isclose(result.ratio_applied, float(Decimal(expect["ratio_applied"])), rel_tol=1e-15)


# ------------------------------------------------------------------------------------- the frozen S0 contract table
def test_s0_expected_table_is_the_unchanged_s0_artefact():
    assert hashlib.sha256(S0_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest().startswith(S0_SHA256_PREFIX)
    assert S0["table_rows"] == len(S0["table"]) == 324


@pytest.mark.parametrize("row", S0["table"], ids=[r["id"] for r in S0["table"]])
def test_s0_table_row(row):
    """The S0 table carries no ratio authority; a configured ratio is given the consumable authority `manual`."""
    result = run(row["request"], default_authority="manual", numeric_strings=True)
    check(result, {"status": row["status"], "reason": row["reason"], "conversion": row["conversion"],
                   "denominator": row["denominator"], "ratio_applied": row["ratio_applied"]}, rel_tol=Decimal("1e-12"))


# ----------------------------------------------------------------------------------------------- the S1 oracle
def test_oracle_json_is_current_and_independent():
    """The frozen JSON is exactly what the oracle regenerates, and the oracle imports no application code."""
    completed = subprocess.run([sys.executable, "-I", str(ORACLE_PATH), "--check"], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    tree = ast.parse(ORACLE_PATH.read_text(encoding="utf-8"))
    imported = {n.module.split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
                for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [None])}
    assert imported <= {"__future__", "itertools", "json", "sys", "decimal", "pathlib", "copy"}, imported


def test_oracle_counts_cover_the_required_matrix():
    assert ORACLE["counts"] == {"grid": 858, "case_132_138": 12, "invalid": 122, "extremes": 21, "physics": 900}
    reasons = {r["expect"]["reason"] for sec in ("grid", "invalid", "extremes") for r in ORACLE[sec] if r["expect"]["reason"]}
    assert reasons == {
        "base_side_unknown", "calculated_channel_side_unavailable", "ct_authority_unavailable", "denominator_not_representable",
        "invalid_base_declaration", "invalid_base_value", "invalid_quantity", "invalid_representation", "invalid_sample_side",
        "measurement_group_side_conflict", "measurement_side_inferred", "measurement_side_unresolved", "vt_authority_unavailable",
    }
    grid = ORACLE["grid"]
    assert {r["request"]["quantity"] for r in grid} == {"voltage", "current"}
    assert {r["request"]["representation"] for r in grid if r["request"]["quantity"] == "voltage"} == {"line_to_line", "line_to_ground"}
    assert {(r["request"]["base"]["declared_side"]) for r in grid} == {"primary", "secondary", "unknown"}


def test_exhaustive_grid():
    failures = []
    for row in ORACLE["grid"]:
        try:
            check(run(row["request"]), row["expect"])
        except AssertionError as exc:
            failures.append(f"{row['id']}: {exc}")
    assert not failures, "\n".join(failures[:8]) + f"\n... {len(failures)} of {len(ORACLE['grid'])} rows differ"


@pytest.mark.parametrize("row", ORACLE["invalid"], ids=[r["id"] for r in ORACLE["invalid"]])
def test_invalid_or_contradictory_input_is_refused_with_a_reason(row):
    result = run(row["request"])
    check(result, row["expect"])
    # an invalid request is never silently repaired into a number, unless the mutated field was irrelevant to the result
    if row["expect"]["status"] == "unavailable":
        assert result.denominator is None and result.reason is not None


@pytest.mark.parametrize("row", ORACLE["extremes"], ids=[r["id"] for r in ORACLE["extremes"]])
def test_extreme_doubles(row):
    check(run(row["request"]), row["expect"])


@pytest.mark.parametrize("row", ORACLE["case_132_138"], ids=[r["id"] for r in ORACLE["case_132_138"]])
def test_132_kv_system_with_a_138_kv_110_v_vt(row):
    """One base at a time: the resolver never chooses between a stored 110 V rating and a nominal-derived denominator (D-4)."""
    result = run(row["request"])
    check(result, row["expect"])
    pu = float(Decimal(row["sample_physical"])) / result.denominator
    expected = float(Decimal(row["pu_expected"]))
    assert math.isclose(pu, expected, rel_tol=1e-13)
    if "rating" in row["id"]:
        assert math.isclose(pu, 132 / 138, rel_tol=1e-13)           # the 4.35 % difference is a property of the BASE, not of the resolver
    else:
        assert math.isclose(pu, 1.0, rel_tol=1e-13)


def test_the_owner_132_138_figure_is_minus_one_twenty_third():
    assert Decimal(132) / Decimal(138) - 1 == Decimal(-1) / Decimal(23) or abs(Decimal(132) / Decimal(138) - 1 + Decimal(1) / Decimal(23)) < Decimal("1e-70")


# ---------------------------------------------------------------------------------------- P1 physical equivalence
def test_one_physical_condition_has_one_per_unit_value_on_either_side():
    failures = []
    for row in ORACLE["physics"]:
        result = run(row["request"])
        if not result.resolved:
            failures.append(f"{row['id']}: refused {result.reason}")
            continue
        pu = float(Decimal(row["sample"])) / result.denominator
        if not math.isclose(pu, float(Decimal(row["pu_true"])), rel_tol=1e-13, abs_tol=1e-13):
            failures.append(f"{row['id']}: pu {pu!r} != {row['pu_true']}")
    assert not failures, "\n".join(failures[:8]) + f"\n... {len(failures)} of {len(ORACLE['physics'])} rows differ"


# --------------------------------------------------------------------------------- P2/P3 identity, ratio not read
class _PoisonedRatio:
    """Any attribute access fails: proves a same-side computation never reads the ratio."""

    def __getattribute__(self, name):
        raise AssertionError("the ratio was read for a same-side computation")


SAME_SIDE_BASES = [
    ("voltage", sd.BASE_NOMINAL_LL_PRIMARY, "primary", 132000.0), ("voltage", sd.BASE_NOMINAL_LL_PRIMARY, "primary", 275000.0),
    ("voltage", sd.BASE_NOMINAL_LL_PRIMARY, "primary", 0.0000123), ("voltage", sd.BASE_LEGACY_SECONDARY_VOLTAGE_LL, "secondary", 110.0),
    ("voltage", sd.BASE_LEGACY_SECONDARY_VOLTAGE_LL, "secondary", 105.21739130434783),
    ("current", sd.BASE_EQUIPMENT_DERIVED_PRIMARY, "primary", 2099.4555241), ("current", sd.BASE_MANUAL_DIRECT, "primary", 2100.0),
    ("current", sd.BASE_MANUAL_DIRECT, "secondary", 1.0), ("current", sd.BASE_RESULT_MANUAL, "secondary", 5.0),
    ("current", sd.BASE_RESULT_MANUAL, "primary", 1000.0),
]


@pytest.mark.parametrize("quantity,kind,side,value", SAME_SIDE_BASES)
@pytest.mark.parametrize("rep", ["line_to_line", "line_to_ground"])
def test_same_side_result_is_the_existing_arithmetic_and_never_reads_the_ratio(quantity, kind, side, value, rep):
    if quantity == "current" and rep == "line_to_ground":
        pytest.skip("representation applies to Voltage only")
    representation = rep if quantity == "voltage" else None
    expected = value / SQRT_3 if rep == "line_to_ground" and quantity == "voltage" else value
    junk_ratios = [None, _PoisonedRatio(), SideRatio("conflict"), SideRatio("configured", float("nan"), "manual"),
                   SideRatio("configured", -5.0, "guess"), SideRatio("not_configured", 2500.0, "manual"), "garbage"]
    for ratio in junk_ratios:
        result = resolve_side_denominator(quantity, SideBase(kind, value, side), SampleSide(side), ratio, representation=representation)
        assert result.resolved and result.conversion == sd.CONVERSION_DIRECT
        assert result.denominator == expected                  # bit-for-bit, not "close"
        assert result.ratio_applied is None and result.ratio_authority is None and result.ratio_group_ids == ()


# ------------------------------------------------------------------- T8/T9 identity with the production resolvers
def _profile(kv: float) -> PerUnitBaseProfile:
    return PerUnitBaseProfile(
        source_id="s", workspace_id="w", voltage_base_value=kv, voltage_reference_mode="auto", voltage_reference_override=None,
        current_base_mode="direct", apparent_power_base_value=None, direct_current_base_value=None)


@pytest.mark.parametrize("kv", [0.4, 11.0, 33.0, 66.0, 110.0, 132.0, 220.0, 275.0, 400.0, 500.0, 765.0, 1e-9, 1e6])
@pytest.mark.parametrize("reference,rep", [(LINE_TO_LINE, "line_to_line"), (LINE_TO_GROUND, "line_to_ground")])
def test_primary_primary_voltage_matches_the_source_wide_production_denominator(kv, reference, rep):
    production = resolve_per_unit(VOLTAGE, _profile(kv), explicit_voltage_reference=reference)
    assert production.status == "configured"
    result = resolve_side_denominator(
        "voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, kv * 1000.0, "primary"), SampleSide("primary"), None, representation=rep)
    assert result.denominator == production.base_amount


@pytest.mark.parametrize("kv", [33.0, 132.0, 275.0, 0.4])
@pytest.mark.parametrize("reference,rep", [(LINE_TO_LINE, "line_to_line"), (LINE_TO_GROUND, "line_to_ground")])
def test_primary_primary_voltage_matches_the_group_production_denominator(kv, reference, rep):
    group = MeasurementGroup(id="mg", workspace_id="w", source_id="s", kind=KIND_VOLTAGE, display_name="G", status=STATUS_CONFIRMED,
                             channel_refs=[ChannelRef(kind="source", source_id="s", channel_name=n) for n in ("VR", "VY", "VB")])
    cfg = VoltageBaseConfiguration(measurement_group_id="mg", workspace_id="w", nominal_voltage_ll_kv=kv)
    production = resolve_voltage_base_for_group(group, cfg, explicit_reference=reference)
    result = resolve_side_denominator(
        "voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, kv * 1000.0, "primary"), SampleSide("primary"), None, representation=rep)
    assert result.denominator == production.denominator_volts


@pytest.mark.parametrize("secondary_v", [110.0, 63.5, 105.21739130434783, 120.0, 100.0])
@pytest.mark.parametrize("reference,rep", [(LINE_TO_LINE, "line_to_line"), (LINE_TO_GROUND, "line_to_ground")])
def test_legacy_secondary_base_on_secondary_samples_reproduces_todays_denominator(secondary_v, reference, rep):
    """T9: the legacy `secondary_voltage_ll_v` path (including a group with NO primary nominal and no VT) is unchanged."""
    group = MeasurementGroup(id="mg", workspace_id="w", source_id="s", kind=KIND_VOLTAGE, display_name="G", status=STATUS_CONFIRMED,
                             channel_refs=[ChannelRef(kind="source", source_id="s", channel_name=n) for n in ("VR", "VY", "VB")])
    cfg = VoltageBaseConfiguration(measurement_group_id="mg", workspace_id="w", nominal_voltage_ll_kv=None,
                                   base_reference_side="secondary", secondary_voltage_ll_v=secondary_v)
    production = resolve_voltage_base_for_group(group, cfg, explicit_reference=reference)
    assert production.status == "configured"
    result = resolve_side_denominator(
        "voltage", SideBase(sd.BASE_LEGACY_SECONDARY_VOLTAGE_LL, secondary_v, "secondary"), SampleSide("secondary"),
        SideRatio("no_group"), representation=rep)
    assert result.denominator == production.denominator_volts


@pytest.mark.parametrize("amps_kilo", [0.001, 1.0, 2.1, 40.0])
def test_direct_current_base_primary_primary_matches_the_production_denominator(amps_kilo):
    profile = PerUnitBaseProfile(
        source_id="s", workspace_id="w", voltage_base_value=None, voltage_reference_mode="auto", voltage_reference_override=None,
        current_base_mode="direct", apparent_power_base_value=None, direct_current_base_value=amps_kilo)
    production = resolve_per_unit(CURRENT, profile, voltage_channel_names=[])
    assert production.status == "configured"
    result = resolve_side_denominator("current", SideBase(sd.BASE_MANUAL_DIRECT, amps_kilo * 1000.0, "primary"), SampleSide("primary"), None)
    assert result.denominator == production.base_amount


# --------------------------------------------------------------------- P4 round trip, P5 commutation, randomised
def _random_cases(seed: int, n: int):
    rng = random.Random(seed)
    for _ in range(n):
        yield 10 ** rng.uniform(-60, 60), 10 ** rng.uniform(-6, 9), rng.choice(("line_to_line", "line_to_ground"))


def test_round_trip_and_commutation_properties():
    for base, ratio, rep in _random_cases(20261124, 3000):
        r = SideRatio("configured", ratio, "manual", ("g",))
        a = resolve_side_denominator("voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, base, "primary"), SampleSide("secondary"), r, representation=rep)
        # P4: a Primary base B on Secondary samples == a Secondary base B/r on Secondary samples
        secondary_base = a.denominator * (SQRT_3 if rep == "line_to_ground" else 1.0)
        b = resolve_side_denominator("voltage", SideBase(sd.BASE_LEGACY_SECONDARY_VOLTAGE_LL, base / ratio, "secondary"),
                                     SampleSide("secondary"), None, representation=rep)
        assert math.isclose(a.denominator, b.denominator, rel_tol=1e-14), (base, ratio, rep)
        # ... and a Secondary base B/r on Primary samples recovers B (arithmetic only; D-6 is pending)
        c = resolve_side_denominator("voltage", SideBase(sd.BASE_LEGACY_SECONDARY_VOLTAGE_LL, base / ratio, "secondary"),
                                     SampleSide("primary"), r, representation=rep)
        d = resolve_side_denominator("voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, base, "primary"), SampleSide("primary"), None, representation=rep)
        assert math.isclose(c.denominator, d.denominator, rel_tol=1e-14), (base, ratio, rep)
        # P5: rho and r are scalars -- the line-to-ground denominator is the line-to-line one divided by sqrt(3)
        ll = resolve_side_denominator("voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, base, "primary"), SampleSide("secondary"), r, representation="line_to_line")
        ln = resolve_side_denominator("voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, base, "primary"), SampleSide("secondary"), r, representation="line_to_ground")
        assert math.isclose(ll.denominator / ln.denominator, SQRT_3, rel_tol=1e-14)
        assert secondary_base > 0


def test_ratio_is_applied_exactly_once():
    base = SideBase(sd.BASE_NOMINAL_LL_PRIMARY, 275000.0, "primary")
    r = SideRatio("configured", 2500.0, "manual")
    one = resolve_side_denominator("voltage", base, SampleSide("secondary"), r, representation="line_to_line")
    assert one.denominator == 110.0 and one.ratio_applied == 2500.0 and one.conversion == sd.CONVERSION_BASE_DIVIDED_BY_RATIO
    twice = resolve_side_denominator("voltage", SideBase(sd.BASE_NOMINAL_LL_PRIMARY, one.denominator, "primary"), SampleSide("secondary"), r,
                                     representation="line_to_line")
    assert twice.denominator == pytest.approx(110.0 / 2500.0)      # a second application is a different request, never implicit


# ----------------------------------------------------------------------------- precedence and refusal properties
def _p(value="primary", problem=None):
    return SampleSide(value if problem is None else None, problem)


@pytest.mark.parametrize("name,args,reason", [
    ("invalid value beats a non-strict sample",
     ("current", SideBase("manual_direct", -1.0, "primary"), SampleSide(None, "calculated"), None), "invalid_base_value"),
    ("invalid declaration beats an invalid value",
     ("current", SideBase("equipment_derived_primary", -1.0, "secondary"), SampleSide("primary"), None), "invalid_base_declaration"),
    ("sample problem beats unknown base",
     ("current", SideBase("manual_direct", 1.0, "unknown"), SampleSide(None, "inferred"), None), "measurement_side_inferred"),
    ("unknown base beats a missing ratio",
     ("current", SideBase("manual_direct", 1.0, "unknown"), SampleSide("secondary"), SideRatio("no_group")), "base_side_unknown"),
    ("ratio refusal beats representability",
     ("current", SideBase("manual_direct", 1e308, "primary"), SampleSide("secondary"), SideRatio("no_group")), "ct_authority_unavailable"),
    ("representability last",
     ("current", SideBase("manual_direct", 1e308, "primary"), SampleSide("secondary"), SideRatio("configured", 1e-5, "manual")),
      "denominator_not_representable"),
])
def test_refusal_precedence(name, args, reason):
    result = resolve_side_denominator(*args)
    assert result.status == "unavailable" and result.reason == reason, name
    assert result.denominator is None and result.conversion is None


@pytest.mark.parametrize("problem,reason", [
    ("calculated", "calculated_channel_side_unavailable"), ("unresolved", "measurement_side_unresolved"),
    ("inferred", "measurement_side_inferred"), ("group_conflict", "measurement_group_side_conflict")])
def test_a_non_strict_sample_side_never_yields_a_number_even_with_a_perfect_ratio(problem, reason):
    result = resolve_side_denominator("voltage", SideBase("nominal_ll_primary", 132000.0, "primary"), SampleSide(None, problem),
                                      SideRatio("configured", 1254.5454545454545, "manual"), representation="line_to_line")
    assert result.reason == reason and result.denominator is None


@pytest.mark.parametrize("status", ["no_channels", "no_group", "not_configured", "untrusted_authority", "invalid", "conflict"])
@pytest.mark.parametrize("quantity,kind,reason", [("voltage", "nominal_ll_primary", "vt_authority_unavailable"),
                                                   ("current", "manual_direct", "ct_authority_unavailable")])
def test_a_needed_conversion_without_an_authoritative_ratio_is_refused(status, quantity, kind, reason):
    rep = "line_to_line" if quantity == "voltage" else None
    result = resolve_side_denominator(quantity, SideBase(kind, 100.0, "primary"), SampleSide("secondary"),
                                      SideRatio(status, 2500.0, "manual"), representation=rep)
    assert result.reason == reason and result.detail == status and result.denominator is None


@pytest.mark.parametrize("authority", ["manual", "recording_metadata", "auto_nominal", "mixed"])
def test_every_consumable_ratio_authority_is_echoed(authority):
    result = resolve_side_denominator("current", SideBase("manual_direct", 2100.0, "primary"), SampleSide("secondary", None, "engineer_group_override"),
                                      SideRatio("configured", 4000.0, authority, ("g1", "g2")))
    assert (result.ratio_authority, result.ratio_group_ids, result.sample_authority) == (authority, ("g1", "g2"), "engineer_group_override")
    assert (result.base_kind, result.base_side, result.sample_side, result.denominator_side) == ("manual_direct", "primary", "secondary", "secondary")
    assert result.denominator == 0.525


def test_an_unknown_base_side_is_never_assumed_primary():
    for sample in ("primary", "secondary"):
        result = resolve_side_denominator("current", SideBase("manual_direct", 1.0, "unknown"), SampleSide(sample), SideRatio("configured", 2000.0, "manual"))
        assert result.reason == "base_side_unknown" and result.denominator is None


def test_secondary_base_on_secondary_samples_is_independent_of_any_ratio():
    """Independent Secondary engineering bases are preserved: no ratio, no group, no VT/CT are needed."""
    for ratio in (None, SideRatio("no_group"), SideRatio("not_configured")):
        result = resolve_side_denominator("voltage", SideBase("legacy_secondary_voltage_ll", 110.0, "secondary"), SampleSide("secondary"),
                                          ratio, representation="line_to_line")
        assert result.denominator == 110.0 and result.conversion == "direct"


def test_results_are_immutable_value_objects():
    result = resolve_side_denominator("current", SideBase("manual_direct", 1.0, "secondary"), SampleSide("secondary"), None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.denominator = 2.0                                           # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        SideBase("manual_direct", 1.0, "secondary").value = 2.0            # type: ignore[misc]


# ------------------------------------------------------------------------ never raises; wide-range numeric property
_JUNK = [None, True, False, 0, -1, 1, 1.5, float("nan"), float("inf"), "x", "", b"b", [], [1], {}, {"a": 1}, object(), 10 ** 400, -(10 ** 400),
         (), type, len, Decimal("1"), 1j, SideBase, SampleSide("primary"), SideRatio("configured", 2.0, "manual")]


def test_the_resolver_never_raises_and_never_returns_a_non_finite_number():
    good = dict(quantity="voltage", base=SideBase("nominal_ll_primary", 132000.0, "primary"), sample=SampleSide("secondary"),
                ratio=SideRatio("configured", 1254.5, "manual"), representation="line_to_line")
    for field in ("quantity", "base", "sample", "ratio", "representation"):
        for junk in _JUNK:
            args = dict(good, **{field: junk})
            result = resolve_side_denominator(args["quantity"], args["base"], args["sample"], args["ratio"], representation=args["representation"])
            assert isinstance(result, SideDenominator)
            assert (result.denominator is None) == (not result.resolved)
            if result.resolved:
                assert math.isfinite(result.denominator) and result.denominator > 0
    for sub in ("kind", "value", "declared_side"):
        for junk in _JUNK:
            base = dataclasses.replace(good["base"], **{sub: junk})
            assert isinstance(resolve_side_denominator("voltage", base, good["sample"], good["ratio"], representation="line_to_line"), SideDenominator)
    for sub in ("side", "problem", "authority"):
        for junk in _JUNK:
            sample = dataclasses.replace(good["sample"], **{sub: junk})
            assert isinstance(resolve_side_denominator("voltage", good["base"], sample, good["ratio"], representation="line_to_line"), SideDenominator)
    for sub in ("status", "value", "authority", "group_ids"):
        for junk in _JUNK:
            ratio = dataclasses.replace(good["ratio"], **{sub: junk})
            assert isinstance(resolve_side_denominator("voltage", good["base"], good["sample"], ratio, representation="line_to_line"), SideDenominator)


def test_wide_range_against_exact_arithmetic():
    """Log-uniform over (almost) the whole double range: resolved exactly when the exact value is representable, refused when it is
    not, and never anything in between (a subnormal result is valid)."""
    rng = random.Random(7)
    s3 = Decimal(3).sqrt()
    max_f, min_sub = Decimal(sys.float_info.max), Decimal(5e-324)
    seen = {"resolved": 0, "refused": 0, "subnormal": 0}
    for _ in range(6000):
        base = 10 ** rng.uniform(-322, 307)
        ratio = 10 ** rng.uniform(-300, 300)
        side, sample = rng.choice((("primary", "secondary"), ("secondary", "primary")))
        ln = rng.random() < 0.5
        exact = Decimal(base) / (s3 if ln else 1)
        exact = exact / Decimal(ratio) if side == "primary" else exact * Decimal(ratio)
        result = resolve_side_denominator(
            "voltage", SideBase("nominal_ll_primary" if side == "primary" else "legacy_secondary_voltage_ll", base, side),
            SampleSide(sample), SideRatio("configured", ratio, "manual"), representation="line_to_ground" if ln else "line_to_line")
        if exact > min_sub * 2 and exact < max_f / 2:
            assert result.resolved, (base, ratio, side, ln, result.reason)
            seen["resolved"] += 1
            tolerance = Decimal("1e-14") * exact + Decimal(2) * min_sub
            assert abs(Decimal(result.denominator) - exact) <= tolerance, (base, ratio, side, ln, result.denominator, exact)
            seen["subnormal"] += result.denominator < sys.float_info.min
        elif exact < min_sub / 4 or exact > max_f * 2:
            assert result.reason == "denominator_not_representable" and result.denominator is None, (base, ratio, side, ln)
            seen["refused"] += 1
    assert min(seen.values()) > 50, seen          # the sweep really exercised each regime


# ---------------------------------------------------------------------------------------------- vocabulary / isolation
def test_vocabulary_mirrors_the_existing_service_constants():
    from app.services import protection_instrument_context as pic, recorded_side_authority as rsa
    assert (sd.PROBLEM_CALCULATED, sd.PROBLEM_UNRESOLVED, sd.PROBLEM_INFERRED, sd.PROBLEM_GROUP_CONFLICT) == (
        rsa.PROBLEM_CALCULATED, rsa.PROBLEM_UNRESOLVED, rsa.PROBLEM_INFERRED, rsa.PROBLEM_GROUP_CONFLICT)
    assert sd.RATIO_STATUSES == (pic.RATIO_CONFIGURED, pic.RATIO_NO_CHANNELS, pic.RATIO_NO_GROUP, pic.RATIO_NOT_CONFIGURED,
                                 pic.RATIO_UNTRUSTED_AUTHORITY, pic.RATIO_INVALID, pic.RATIO_CONFLICT)
    assert set(sd.RATIO_AUTHORITIES) >= set(pic.CONSUMABLE_AUTHORITIES) | {"auto_nominal"}
    assert (sd.REASON_VT_AUTHORITY_UNAVAILABLE, sd.REASON_CT_AUTHORITY_UNAVAILABLE) == ("vt_authority_unavailable", "ct_authority_unavailable")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_the_module_imports_only_the_standard_library_and_the_existing_numeric_helper():
    assert _imported_modules(APP_DIR / "domain" / "side_denominator.py") <= {
        "__future__", "math", "sys", "dataclasses", "app.domain.per_unit_numerics"}


#: PU-MIG S2 (raw Voltage) connects the resolver at exactly these production points, and nowhere else. They import its
#: vocabulary (base kinds, sides, `SideBase` / `SampleSide` / `SideRatio`); only `per_unit_reference` CALLS it.
S2_IMPORTERS = {
    "domain/per_unit.py",                      # the Source Default base descriptor
    "domain/per_unit_reference.py",            # the one gate that calls resolve_side_denominator()
    "domain/voltage_group_config.py",          # the established group base (kind) the base resolver already chose
    "services/group_aware_per_unit.py",        # carries that base to the gate
    "services/per_unit_side_authority.py",     # Recording Details' side / VT, translated for the gate
    "domain/calculated_side_lineage.py",       # S3: only the `SampleSide` vocabulary; it never calls the resolver
    "services/calculated_current_per_unit.py", # S4: vocabulary only; the K-3 comparison calls `per_unit_reference.place_current_base`
}
S2_CALLERS = {"domain/per_unit_reference.py"}


def test_the_resolver_is_connected_only_at_the_s2_integration_points():
    """S1 wired nothing; S2 connects raw Voltage at the points above. Any other import, and any second caller of
    `resolve_side_denominator()` (denominator arithmetic duplicated in a consumer), fails here."""
    importers, callers = set(), set()
    for path in APP_DIR.rglob("*.py"):
        relative = path.relative_to(APP_DIR).as_posix()
        if relative == "domain/side_denominator.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "side_denominator" in text and any("side_denominator" in m for m in _imported_modules(path)):
            importers.add(relative)
        calls = (n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call))
        if any(getattr(c.func, "id", getattr(c.func, "attr", None)) == "resolve_side_denominator" for c in calls):
            callers.add(relative)
    assert importers == S2_IMPORTERS
    assert callers == S2_CALLERS


def test_the_frontend_and_public_schemas_do_not_mention_the_resolver():
    root = APP_DIR.parents[1]
    for path in [*(APP_DIR / "schemas").rglob("*.py"), *(APP_DIR / "api").rglob("*.py"), root / "frontend" / "index.html"]:
        assert "side_denominator" not in path.read_text(encoding="utf-8", errors="ignore"), path
