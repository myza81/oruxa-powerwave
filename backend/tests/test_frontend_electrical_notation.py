"""Static guardrails for the DEC-117 electrical-notation convention.

rich surface  -> real subscript via the ONE shared formatter
                 (V<sub>A</sub>, V<sub>AB</sub>, V<sub>1</sub>, I<sub>2</sub>)
plain surface -> concatenated fallback (VA, VAB, V1, I2)
never         -> an underscore-joined form

Same source-text pattern as the other test_frontend_*.py checks. Rendering
behaviour (true visual subscript position, formula content, source/custom/
editable/phase values staying plain) is covered by
browser-tests/electrical-notation.spec.js and the per-area suites.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend" / "index.html"
BROWSER_TESTS = REPO / "browser-tests"

# Built from parts so this file never contains the forbidden literal itself.
# DEC-118 adds the R/Y/B display spellings (VR, VRY ...) to the ban, and
# phase-to-neutral adds AN..CN / RN, YN (and so the hyphenated "R-N" form).
_UNDERSCORE_SYMBOL = re.compile(
    r"(?<![A-Za-z0-9_])[VI]" + "_" + r"\{?(?:AB|BC|CA|RY|YB|BR|AN|BN|CN|RN|YN|A|B|C|R|Y|0|1|2)\}?(?![A-Za-z0-9])"
)


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _blank_block_comments(source: str) -> str:
    # Keep newlines so line numbers stay accurate.
    blank = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    source = re.sub(r"/\*.*?\*/", blank, source, flags=re.DOTALL)
    return re.sub(r"<!--.*?-->", blank, source, flags=re.DOTALL)


def _code_lines(source: str):
    """(line number, text) for non-comment lines -- comments may discuss
    markup; only executable code/markup is policed."""
    for number, line in enumerate(_blank_block_comments(source).splitlines(), 1):
        if line.strip().startswith("//"):
            continue
        yield number, line


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = source.index("\n        }\n", start)
    return source[start:end]


def test_one_shared_css_rule_each_and_no_legacy_classes():
    source = _source()
    assert len(re.findall(r"^\s*\.ww-electrical-symbol\s*\{", source, flags=re.MULTILINE)) == 1
    assert len(re.findall(r"^\s*\.ww-electrical-sub\s*\{", source, flags=re.MULTILINE)) == 1
    for legacy in ("ww-ll-sub", "ww-voltage-sub"):
        assert legacy not in source, legacy


def test_wrapper_css_cannot_be_restyled_by_generic_descendant_rules():
    # The owner-UAT superscript defect: `.ww-cc-field span { display: flex }`
    # blockified the <sub>. The wrapper must stay one atomic inline box.
    source = _source()
    rule = re.search(r"^\s*\.ww-electrical-symbol\s*\{([^}]*)\}", source, flags=re.MULTILINE).group(1)
    assert "display: inline-block !important" in rule
    sub_rule = re.search(r"^\s*\.ww-electrical-sub\s*\{([^}]*)\}", source, flags=re.MULTILINE).group(1)
    assert "display: inline !important" in sub_rule


def test_every_sub_comes_from_the_shared_formatter_shape():
    source = _source()
    allowed_bodies = [
        _function_body(source, "function wwElectricalSymbolHtml(quantity, subscript)"),
        _function_body(source, "function wwElectricalSymbolPlotly(quantity, subscript)"),
    ]
    static_shape = re.compile(r'<span class="ww-electrical-symbol">[VI]<sub class="ww-electrical-sub">(?:AB|BC|CA|LL|A|B|C|0|1|2)</sub></span>')
    offenders = []
    for number, line in _code_lines(source):
        if "<sub" not in line:
            continue
        if any(line.strip() in body for body in allowed_bodies):
            continue
        remainder = static_shape.sub("", line)
        if "<sub" in remainder:
            offenders.append((number, line.strip()[:120]))
    assert offenders == [], offenders


def test_no_plain_symbol_concatenation_bypasses_the_formatter():
    # "V" + pair, " = V" + x, "(V" + x ... must go through
    # wwElectricalSymbolText()/wwVoltageSymbolText(). The only allowed
    # concatenations build INTERNAL analysis role keys ("V" + "a" -> "Va").
    bypass = re.compile(r"""["'][VI]["']\s*\+|["'][^"'\n]*[ (=][VI]["']\s*\+""")
    offenders = [
        (number, line.strip()[:120])
        for number, line in _code_lines(_source())
        if bypass.search(line) and ".toLowerCase()" not in line and "wwLineToLineDefaultName" not in line
        and "function wwLineToLineDefaultName" not in line and 'trim() + " V" + pair' not in line
    ]
    assert offenders == [], offenders


def test_generalized_symbol_contract_and_role_map():
    source = _source()
    for helper in (
        "function wwElectricalSymbolHtml(quantity, subscript)",
        "function wwElectricalSymbolPlotly(quantity, subscript)",
        "function wwElectricalSymbolSvg(quantity, subscript)",
        "function wwElectricalSymbolText(quantity, subscript)",
        "function wwVoltageSymbolHtml(subscript)",
        "function wwVoltageSymbolText(subscript)",
        # DEC-118: context-specific helpers take an optional phase display.
        "function wwLineToLinePairHtml(pair, phaseDisplay)",
        "function wwLineToLinePairText(pair, phaseDisplay)",
        "function wwLineToLineFormulaHtml(pair, phaseDisplay)",
        "function wwLineToLineFormulaText(pair, phaseDisplay)",
        "function wwPhaseVoltageHtml(phase, phaseDisplay)",
        # Explicit phase-to-neutral voltage: V<sub>AN</sub> / V<sub>RN</sub>.
        "function wwPhaseToNeutralVoltageHtml(phase, phaseDisplay)",
        "function wwPhaseToNeutralVoltageText(phase, phaseDisplay)",
        "function wwPhaseToNeutralVoltageSvg(phase, phaseDisplay)",
        "function wwLineToLinePhaseToNeutralFormulaHtml(pair, phaseDisplay)",
        "function wwLineToLinePhaseToNeutralFormulaText(pair, phaseDisplay)",
        # Phase currents share the same context map (2026-09-30).
        "function wwPhaseCurrentHtml(phase, phaseDisplay)",
        "function wwPhaseCurrentText(phase, phaseDisplay)",
        "function wwRoleLabelHtml(roleKey, phaseDisplay)",
        "function wwRoleLabelPlotly(roleKey, phaseDisplay)",
        "function wwRoleLabelSvg(roleKey, phaseDisplay)",
        "function wwRoleLabelText(roleKey, phaseDisplay)",
        "function wwNormalizePhaseDisplay(value)",
        "function wwEngineeringContextPhaseDisplay(contextId)",
    ):
        assert helper in source, helper
    assert (
        'V: [...WW_VOLTAGE_PHASES, ...WW_LL_NOTATION_PAIRS, ...WW_SEQUENCE_SUBSCRIPTS, ...WW_PHASE_DISPLAY_SUBSCRIPTS, '
        '...WW_PHASE_TO_NEUTRAL_SUBSCRIPTS, WW_GENERIC_LL_SUBSCRIPT],'
        in source
    )
    # Phase-to-neutral tokens come from the SAME phase display map (no second
    # convention table), and are voltage-only.
    assert 'const WW_NEUTRAL_SUBSCRIPT = "N";' in source
    assert (
        "const WW_PHASE_TO_NEUTRAL_SUBSCRIPTS = WW_PHASE_DISPLAY_SINGLE_SUBSCRIPTS.map((p) => p + WW_NEUTRAL_SUBSCRIPT);"
        in source
    )
    # Currents: phase (canonical + single-phase display tokens) and sequence;
    # never a line-to-line pair (no I<sub>AB</sub> / I<sub>RY</sub>).
    assert 'I: [...WW_VOLTAGE_PHASES, ...WW_SEQUENCE_SUBSCRIPTS, ...WW_PHASE_DISPLAY_SINGLE_SUBSCRIPTS],' in source
    assert "flatMap((symbols) => WW_VOLTAGE_PHASES.map((p) => symbols[p]))" in source
    roles = re.search(r"const WW_ELECTRICAL_ROLE_SYMBOLS = \{(.*?)\};", source, flags=re.DOTALL).group(1)
    for key, pair in (("Va", '["V", "A"]'), ("Vb", '["V", "B"]'), ("Vc", '["V", "C"]'),
                      ("Ia", '["I", "A"]'), ("Ib", '["I", "B"]'), ("Ic", '["I", "C"]'),
                      ("V1", '["V", "1"]'), ("I1", '["I", "1"]'), ("I2", '["I", "2"]'), ("I0", '["I", "0"]')):
        assert f"{key}: {pair}" in roles, key
    # Impedance keys are deliberately NOT formatted.
    assert "Za:" not in roles


def test_phase_display_table_mirrors_the_backend():
    """DEC-118: the frontend renders a backend phase-display map only when
    every token is in its own table, so the two tables must agree."""
    from app.domain.phase_identity import PHASE_DISPLAY_SYMBOLS_BY_CONVENTION

    block = re.search(
        r"const WW_PHASE_DISPLAY_SYMBOLS_BY_CONVENTION = \{(.*?)\n        \};", _source(), flags=re.DOTALL
    ).group(1)
    frontend = {
        convention: dict(re.findall(r'(\w+): "(\w+)"', body))
        for convention, body in re.findall(r"(\w+): \{([^}]*)\}", block)
    }
    assert frontend == PHASE_DISPLAY_SYMBOLS_BY_CONVENTION


def test_phase_convention_is_never_detected_from_names_in_the_frontend():
    """DEC-118: the convention comes only from the backend's resolved-phase
    derivation. No frontend regex may look for R/Y/B letters in names."""
    offenders = [
        (number, line.strip()[:120])
        for number, line in _code_lines(_source())
        if re.search(r"/[^/\n]*\[?RYB\]?[^/\n]*/[gimsuy]*\.test\(|includes\(\s*\"[RY]\"\s*\)", line)
    ]
    assert offenders == [], offenders


def test_plain_fallback_is_concatenated():
    body = _function_body(_source(), "function wwElectricalSymbolText(quantity, subscript)")
    assert 'return String(quantity || "") + sub;' in body
    assert "_" not in body.replace("subscript", "").replace("sub", "")


def test_no_underscore_symbol_in_frontend_or_browser_tests():
    offenders = []
    files = [FRONTEND, *sorted(BROWSER_TESTS.glob("*.spec.js"))]
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _UNDERSCORE_SYMBOL.search(line):
                offenders.append((path.name, number, line.strip()[:120]))
    assert offenders == [], offenders


def test_underscore_guard_does_not_flag_channel_names_or_identifiers():
    for harmless in ("KPDN1_VR", "SLKS_VB", "phase_a_channel_ref", "WW_V_A_TOTAL", "line_to_line_multibay", "V1_label"):
        assert not _UNDERSCORE_SYMBOL.search(harmless), harmless
    for forbidden in ("V" + "_A", "V" + "_AB", "V" + "_1", "I" + "_2", "V" + "_{A}", "V" + "_R", "V" + "_RY", "V" + "_BR",
                      "I" + "_A", "I" + "_R", "I" + "_Y", "I" + "_B", "I" + "_1",
                      "V" + "_RN", "V" + "_YN", "V" + "_BN", "V" + "_AN", "V" + "_CN", "V" + "_{RN}", "V" + "_R-N"):
        assert _UNDERSCORE_SYMBOL.search(forbidden), forbidden


def test_related_waveform_identity_is_meta_not_display_name():
    assert "meta: role.roleKey," in _source()
