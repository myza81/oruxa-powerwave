"""PU-CORE-001: no production call path may omit the group registries.

`waveform_service._resolve_effective_per_unit()` and the four public
functions that feed it take the Measurement Group registries as optional
parameters (default None) and, when any is missing, resolve through the
DEC-049 Source Default path. That is only safe while every production
caller supplies all four. HTTP-level DEC-051 precedence is covered in
test_group_aware_per_unit_endpoints.py; this guard closes the structural
gap: a future call site that omits the registries would silently let a
grouped channel fall back to Source Default.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

GUARDED_CALLS = {
    "_resolve_effective_per_unit",
    "extract_waveform_range",
    "extract_cursor_values",
    "resolve_annotation_anchor",
    "resolve_peak_value",
}
REQUIRED_KEYWORDS = {"workspace_id", "group_registry", "voltage_config_registry", "current_config_registry"}


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _violations(source: str, label: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _call_name(node) in GUARDED_CALLS:
            keywords = {kw.arg for kw in node.keywords}
            if any(kw.arg is None for kw in node.keywords):
                continue  # **kwargs forwarding cannot be checked statically
            missing = REQUIRED_KEYWORDS - keywords
            if missing:
                found.append(f"{label}:{node.lineno} {_call_name(node)}() omits {sorted(missing)}")
    return found


def test_guard_detects_an_omitted_registry():
    bad = "extract_waveform_range(active, channel_name='x', workspace_id='w', group_registry=g)"
    assert _violations(bad, "synthetic")
    good = (
        "extract_waveform_range(active, workspace_id='w', group_registry=g, "
        "voltage_config_registry=v, current_config_registry=c)"
    )
    assert _violations(good, "synthetic") == []


def test_every_production_call_supplies_all_group_registries():
    violations = []
    sites = 0
    for path in sorted(APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not any(name in source for name in GUARDED_CALLS):
            continue
        tree = ast.parse(source)
        sites += sum(
            1 for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) in GUARDED_CALLS
        )
        violations.extend(_violations(source, str(path.relative_to(APP))))
    assert sites >= 9, "expected the 4 waveform_service + 4 sources.py + compliance_series call sites"
    assert not violations, "\n".join(violations)
