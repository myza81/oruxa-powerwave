"""Static guard for the DEC-117 voltage-notation convention (single-phase
amendment, 2026-09-26): one shared formatter, one shared subscript CSS
rule, no component-specific variants. Same source-text pattern as the
other test_frontend_*.py checks -- behaviour is covered by the browser
suites (line-to-line-voltage, phasor, related waveforms, ...).
"""

from __future__ import annotations

import re
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def test_one_shared_subscript_rule_and_no_legacy_class():
    source = _source()
    assert len(re.findall(r"^\s*\.ww-voltage-sub\s*\{", source, flags=re.MULTILINE)) == 1
    assert "ww-ll-sub" not in source


def test_every_classed_sub_uses_the_shared_rule():
    source = _source()
    classes = set(re.findall(r'<sub class="([^"]+)"', source))
    assert classes == {"ww-voltage-sub"}


def test_shared_voltage_notation_api_exists():
    source = _source()
    for helper in (
        "function wwVoltageSymbolHtml(subscript)",
        "function wwVoltageSymbolPlotly(subscript)",
        "function wwVoltageSymbolSvg(subscript)",
        "function wwVoltageSymbolText(subscript)",
        "function wwPhaseVoltageHtml(phase)",
        "function wwLineToLinePairHtml(pair)",
        "function wwLineToLineFormulaHtml(pair)",
        "function wwRoleLabelHtml(roleKey)",
        "function wwRoleLabelPlotly(roleKey)",
        "function wwRoleLabelSvg(roleKey)",
    ):
        assert helper in source, helper


def test_only_voltage_role_keys_are_formatted():
    source = _source()
    assert 'const WW_VOLTAGE_ROLE_SUBSCRIPTS = { Va: "A", Vb: "B", Vc: "C" };' in source
    assert 'const WW_VOLTAGE_PHASES = ["A", "B", "C"];' in source
    assert 'const WW_LL_NOTATION_PAIRS = ["AB", "BC", "CA"];' in source


def test_related_waveform_identity_is_meta_not_display_name():
    source = _source()
    assert "meta: role.roleKey," in source
