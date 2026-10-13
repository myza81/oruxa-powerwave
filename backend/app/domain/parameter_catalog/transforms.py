"""Transformation primitives: the only behaviour an OEM catalog may invoke.

A catalog never contains code. It names a primitive from `PRIMITIVES` and gives it parameters;
the primitive is implemented here, once, for every relay. Adding a primitive is a code change
(and must be generic); using one in a catalog is a data change.

Each primitive declares:

* ``inputs`` -- how many named inputs it takes (``"one"``: the mapping's ``source``; ``"many"``:
  the mapping's ``sources``; ``"none"``: no input, e.g. a constant);
* ``in_types`` / ``out_type`` -- value types in the chain (``number``, ``text``, ``boolean``,
  ``value`` for "any literal", ``impedance``, ``same`` = unchanged);
* the parameter names it accepts.

The catalog validator type-checks every chain against these declarations before a catalog can
be used, so an unsupported primitive or a mistyped chain is a load-time error.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from app.domain.parameter_catalog.units import conversion_factor, is_known_unit
from app.domain.relay_import.canonical_distance import ImpedanceValue


class TransformError(Exception):
    """A value could not be transformed. ``cause`` is an `UnresolvedCause` value name
    (``unreadable`` / ``unsupported`` / ``conflict``)."""

    def __init__(self, message: str, cause: str = "unreadable") -> None:
        super().__init__(message)
        self.cause = cause


def fmt(value: Any) -> str:
    """A number as short text (``7`` not ``7.0``), anything else as ``str``."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value) == int(value) and abs(value) < 1e15 else f"{value:.10g}"
    return str(value)


def norm_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text if text is not None else "").replace("’", "'")).strip().casefold()


# ---------------------------------------------------------------------------
# The primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Primitive:
    name: str
    inputs: str                          # "one" | "many" | "none"
    in_type: str                         # type of the single input (or "-" for many / none)
    out_type: str                        # "same" keeps the input type
    params: frozenset[str] = frozenset()
    required: frozenset[str] = frozenset()
    #: For "many": the input names the primitive reads (the mapping's ``sources`` must provide them).
    input_names: tuple[str, ...] = ()
    #: ``(params, inputs) -> (value, sentence-or-None)``. ``inputs`` is a dict name -> value.
    run: Callable[[dict, dict], tuple[Any, str | None]] | None = None


def _number(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        raise TransformError("the value is not a finite number")
    return float(v)


def _direct(p, i):
    return i["value"], None


def _enum(p, i):
    key = norm_text(i["value"])
    table = {norm_text(k): v for k, v in p["map"].items()}
    if key not in table:
        raise TransformError("the value is not recognised by the catalog", "unsupported")
    return table[key], None


_TRUE = ("on", "true", "yes", "enabled", "enable", "1")
_FALSE = ("off", "false", "no", "disabled", "disable", "0")


def _boolean(p, i):
    key = norm_text(i["value"])
    trues = {norm_text(x) for x in p.get("true_values", _TRUE)}
    falses = {norm_text(x) for x in p.get("false_values", _FALSE)}
    if key in trues:
        return True, None
    if key in falses:
        return False, None
    raise TransformError("the value is not recognised by the catalog", "unsupported")


def _scale(p, i):
    x = _number(i["value"])
    y = x * float(p["factor"]) + float(p.get("offset", 0.0))
    return y, f"{fmt(x)} × {fmt(p['factor'])}" + (f" + {fmt(p['offset'])}" if p.get("offset") else "") + f" = {fmt(y)}"


def _divide(p, i):
    x = _number(i["value"])
    y = x / float(p["by"])
    return y, f"{fmt(x)} ÷ {fmt(p['by'])} = {fmt(y)}"


def _ratio(p, i):
    num, den = _number(i["numerator"]), _number(i["denominator"])
    if den == 0:
        raise TransformError("the denominator is zero")
    y = num / den
    return y, f"{fmt(num)} ÷ {fmt(den)} = {fmt(y)}"


def _unit_conversion(p, i):
    x = _number(i["value"])
    factor = conversion_factor(p["from"], p["to"])
    if factor is None:
        raise TransformError(f"no conversion from {p['from']} to {p['to']}", "unsupported")
    y = x * factor
    return y, f"{fmt(x)} {p['from']} → {fmt(y)} {p['to']}"


def _percentage(p, i):
    x = _number(i["value"])
    if p["direction"] == "to_fraction":
        return x / 100.0, f"{fmt(x)} % → {fmt(x / 100.0)}"
    return x * 100.0, f"{fmt(x)} → {fmt(x * 100.0)} %"


def _bitmask(p, i):
    x = _number(i["value"])
    if x != int(x) or x < 0:
        raise TransformError("the value is not a non-negative integer")
    mask = (1 << int(p["bit"])) if "bit" in p else int(p["mask"])
    return bool(int(x) & mask), None


def _regex(p, i):
    m = re.search(p["pattern"], str(i["value"]))
    if not m:
        raise TransformError("the value does not match the expected pattern")
    group = m.group(int(p.get("group", 1)))
    if p.get("as") == "number":
        try:
            return float(group), None
        except ValueError as exc:
            raise TransformError("the extracted text is not a number") from exc
    return group, None


def _constant(p, i):
    return p["value"], None


def _decision_table(p, i):
    """First matching rule wins. A rule matches when every input it names is *available* and its
    (case-folded) text is one of the rule's listed texts; an input that is unavailable never matches
    (so a rule on another input can still decide)."""
    for rule in p["rules"]:
        when = rule["when"]
        if all(name in i and norm_text(i[name]) in {norm_text(t) for t in _as_list(want)} for name, want in when.items()):
            return rule["value"], None
    if "default" in p:
        return p["default"], None
    raise TransformError("no rule of the decision table applies to the available values", "missing")


def _as_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _impedance_rx(p, i):
    r, x = _number(i["r"]), _number(i["x"])
    return ImpedanceValue(r_ohm=r, x_ohm=x), f"R {fmt(r)} + jX {fmt(x)}"


def _impedance_polar(p, i):
    m, a = _number(i["magnitude"]), _number(i["angle"])
    return ImpedanceValue(magnitude_ohm=m, angle_deg=a), f"{fmt(m)} ∠ {fmt(a)}°"


_PARAM = frozenset
PRIMITIVES: dict[str, Primitive] = {
    p.name: p
    for p in (
        Primitive("direct", "one", "any", "same", run=_direct),
        Primitive("enum", "one", "text", "value", _PARAM({"map"}), _PARAM({"map"}), run=_enum),
        Primitive("boolean", "one", "text", "boolean", _PARAM({"true_values", "false_values"}), run=_boolean),
        Primitive("scale", "one", "number", "number", _PARAM({"factor", "offset"}), _PARAM({"factor"}), run=_scale),
        Primitive("multiply", "one", "number", "number", _PARAM({"factor"}), _PARAM({"factor"}),
                  run=lambda p, i: _scale({"factor": p["factor"]}, i)),
        Primitive("divide", "one", "number", "number", _PARAM({"by"}), _PARAM({"by"}), run=_divide),
        Primitive("ratio", "many", "-", "number", input_names=("numerator", "denominator"), run=_ratio),
        Primitive("unit_conversion", "one", "number", "number", _PARAM({"from", "to"}), _PARAM({"from", "to"}),
                  run=_unit_conversion),
        Primitive("percentage", "one", "number", "number", _PARAM({"direction"}), _PARAM({"direction"}), run=_percentage),
        Primitive("bitmask", "one", "number", "boolean", _PARAM({"bit", "mask"}), run=_bitmask),
        Primitive("regex", "one", "text", "text", _PARAM({"pattern", "group", "as"}), _PARAM({"pattern"}), run=_regex),
        Primitive("constant", "none", "-", "value", _PARAM({"value"}), _PARAM({"value"}), run=_constant),
        Primitive("decision_table", "many", "-", "value", _PARAM({"rules", "default"}), _PARAM({"rules"}), run=_decision_table),
        Primitive("impedance_rx", "many", "-", "impedance", input_names=("r", "x"), run=_impedance_rx),
        Primitive("impedance_polar", "many", "-", "impedance", input_names=("magnitude", "angle"), run=_impedance_polar),
    )
}


def expected_unit(first_step: str | None, input_name: str, canonical_unit: str, has_unit_conversion: bool) -> str | None:
    """The unit a numeric input is converted to when read, or ``None`` when it is not converted
    (an explicit ``unit_conversion`` step does it, or the primitive's inputs carry their own meaning).

    A single-source mapping reads in the canonical unit. An impedance assembly reads resistances and
    reactances in ohms and an angle in degrees; ratios and decision tables take inputs as stated."""
    if has_unit_conversion:
        return None
    if first_step is None or input_name == "value":
        return canonical_unit
    if first_step in ("impedance_rx", "impedance_polar"):
        return "deg" if input_name == "angle" else "ohm"
    return None


def check_params(primitive: Primitive, params: dict) -> list[str]:
    """Problems with a step's parameters (names, presence and basic types); empty when valid."""
    problems: list[str] = []
    for name in params:
        if name not in primitive.params:
            problems.append(f"unknown parameter {name!r} for '{primitive.name}'")
    for name in primitive.required:
        if name not in params:
            problems.append(f"'{primitive.name}' needs parameter {name!r}")
    n = primitive.name
    if n in ("scale", "multiply") and not _is_number(params.get("factor")):
        problems.append("'factor' must be a number")
    if n == "scale" and "offset" in params and not _is_number(params["offset"]):
        problems.append("'offset' must be a number")
    if n == "divide":
        if not _is_number(params.get("by")):
            problems.append("'by' must be a number")
        elif params["by"] == 0:
            problems.append("'by' must not be zero (division by zero)")
    if n == "unit_conversion":
        for key in ("from", "to"):
            if not isinstance(params.get(key), str) or not is_known_unit(params[key]):
                problems.append(f"'{key}' must be a known unit")
        if not problems and conversion_factor(params["from"], params["to"]) is None:
            problems.append(f"there is no conversion from {params['from']} to {params['to']}")
    if n == "percentage" and params.get("direction") not in ("to_fraction", "to_percent"):
        problems.append("'direction' must be 'to_fraction' or 'to_percent'")
    if n == "bitmask":
        has_bit, has_mask = "bit" in params, "mask" in params
        if has_bit == has_mask:
            problems.append("'bitmask' needs exactly one of 'bit' or 'mask'")
        elif has_bit and not (isinstance(params["bit"], int) and 0 <= params["bit"] <= 63):
            problems.append("'bit' must be an integer 0-63")
        elif has_mask and not (isinstance(params["mask"], int) and params["mask"] > 0):
            problems.append("'mask' must be a positive integer")
    if n == "regex":
        try:
            pat = re.compile(params.get("pattern", ""))
            if pat.groups < 1:
                problems.append("'pattern' needs at least one capture group")
            if params.get("as") not in (None, "number", "text"):
                problems.append("'as' must be 'number' or 'text'")
        except (re.error, TypeError):
            problems.append("'pattern' is not a valid regular expression")
    if n == "enum":
        if not isinstance(params.get("map"), dict) or not params["map"]:
            problems.append("'map' must be a non-empty object")
    if n == "boolean":
        for key in ("true_values", "false_values"):
            if key in params and not (isinstance(params[key], list) and all(isinstance(x, str) for x in params[key])):
                problems.append(f"'{key}' must be a list of strings")
    if n == "decision_table":
        rules = params.get("rules")
        if not isinstance(rules, list) or not rules:
            problems.append("'rules' must be a non-empty list")
        else:
            for k, rule in enumerate(rules):
                if not isinstance(rule, dict) or set(rule) != {"when", "value"} or not isinstance(rule.get("when"), dict) or not rule["when"]:
                    problems.append(f"rules[{k}] needs a non-empty 'when' object and a 'value'")
    return problems


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
