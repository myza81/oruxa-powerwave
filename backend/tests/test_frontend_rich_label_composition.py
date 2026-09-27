"""Static guardrails for composed rich labels (owner UAT, 2026-09-27).

Defect: "Default ContextV<sub>AB</sub>" in the Calculated Channels success
banner. The name was built as bare text + an electrical symbol
("Default Context " + <span class="ww-electrical-symbol">); inside a flex
row each text run became its own anonymous flex item and its trailing space
was trimmed. The DOM text still read "Default Context VAB".

Rule: every label that mixes ordinary words with rich markup (a symbol, a
formatted name, a formula) is composed through the ONE helper
`wwRichLabelHtml()`, a plain-inline `.ww-rich-label` unit. Readable operation
descriptions use a space before "(" -- "RMS (channel, ...)".

Rendered spacing (glyph gaps, flex/grid/inline-flex hosts, wrapping) is
covered by browser-tests/text-spacing.spec.js.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend" / "index.html"

# HTML helpers that return rich markup (an electrical symbol, or a name /
# formula that may contain one).
_RICH_HELPER_CALL = re.compile(
    r"\bww(?:ElectricalSymbol|VoltageSymbol|RoleLabel|PhaseVoltage|LineToLinePair|LineToLineFormula|"
    r"LineToLineName|CalculatedChannelName|ChannelDisplayName|CcInputDisplayName)Html\(|\bwwCcExpressionHtmlFor\("
)
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")

# Functions that return rich HTML composed with words -- each must return
# ONE wwRichLabelHtml() unit.
_COMPOSERS = [
    "function wwLineToLineFormulaHtml(pair, phaseDisplay)",
    "function wwLineToLineNameHtml(name, bayName, pair, phaseDisplay)",
    "function wwCalculatedChannelNameHtml(calc)",
    "function wwCcComputeExpressionPreview(html)",
    "function wwCcExpressionFor(calc, html)",
    "function wwCcLlExpressionPreviewHtml()",
    "function wwCcLlPlannedNamesHtml()",
    "function wwRefDescribeAssessmentDefinition(definition, options)",
]
# Their unwrapped parts; the one caller above wraps the result.
_WRAPPED_BY_CALLER = [
    "function wwCcComputeExpressionPreviewParts(html)",
    "function wwCcExpressionParts(calc, html)",
]
# Readable operation text (names, previews, formulas, summaries).
_OPERATION_TEXT = [
    "function wwCcComputeSuggestedName()",
    "function wwCcComputeExpressionPreviewParts(html)",
    "function wwCcExpressionParts(calc, html)",
    "function wwCcOperationSummaryText(calc)",
]


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = source.index("\n        }\n", start)
    return source[start:end]


def _code_lines(source: str):
    blank = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    source = re.sub(r"/\*.*?\*/", blank, source, flags=re.DOTALL)
    source = re.sub(r"<!--.*?-->", blank, source, flags=re.DOTALL)
    for number, line in enumerate(source.splitlines(), 1):
        if line.strip().startswith("//"):
            continue
        yield number, line


def _statement(lines: list[str], index: int) -> str:
    """The statement around lines[index]: back to the previous line that ends
    a statement/opens a block, forward to the line that ends this one."""
    start = index
    while start > 0 and not lines[start - 1].rstrip().endswith((";", "{", "}")):
        start -= 1
    end = index
    while end < len(lines) - 1 and not lines[end].rstrip().endswith((";", "{")):
        end += 1
    return "\n".join(lines[start:end + 1])


def _has_visible_text(literal: str) -> bool:
    body = literal[1:-1]
    body = re.sub(r"<[^>]*>", "", body)          # whole tags
    body = re.sub(r"^[^<]*>|<[^>]*$", "", body)   # tag fragments split across literals
    return bool(body.strip())


def test_one_rich_label_rule_plain_inline_so_labels_still_wrap():
    source = _source()
    rules = re.findall(r"^\s*\.ww-rich-label\s*\{([^}]*)\}", source, flags=re.MULTILINE)
    assert len(rules) == 1
    rule = rules[0]
    # !important: generic rules such as `.ww-cc-field span { display: flex }`
    # must not turn the unit back into a flex container.
    assert "display: inline !important" in rule
    # Never an unbreakable string: no inline-block/nowrap on the whole label.
    assert "inline-block" not in rule
    assert "nowrap" not in rule


def test_helper_is_the_one_emitter_of_the_rich_label_shape():
    source = _source()
    body = _function_body(source, "function wwRichLabelHtml(html)")
    assert "return '<span class=\"ww-rich-label\">' + html + '</span>';" in body
    # Anything else carrying the class is static markup that cannot call the
    # helper (the Distance manual labels), in the same exact shape.
    others = [line for _, line in _code_lines(source)
              if 'class="ww-rich-label"' in line and "return '<span class=\"ww-rich-label\">'" not in line]
    assert others, "expected the static Distance manual labels"
    for line in others:
        assert '<span class="ww-rich-label"><span class="ww-electrical-symbol">' in line, line
    # No &nbsp; spacing workarounds around symbols/names.
    assert not re.search(r"&nbsp;\s*['\"]?\s*\+\s*ww\w*Html\(", source)
    assert not re.search(r"Html\([^)]*\)\s*\+\s*['\"]&nbsp;", source)


def test_shared_composers_return_one_rich_label_unit():
    source = _source()
    for signature in _COMPOSERS:
        assert "wwRichLabelHtml(" in _function_body(source, signature), signature


_ESCAPED_TEXT_JOIN = re.compile(r"escapeHtml\([^()]*(?:\([^()]*\)[^()]*)*\)\s*\+|\+\s*escapeHtml\(")


def _bare_compositions(source: str, exempt: frozenset = frozenset()) -> list[str]:
    lines = source.splitlines()
    offenders = []
    for number, line in _code_lines(source):
        if number in exempt or not _RICH_HELPER_CALL.search(line) or line.lstrip().startswith("function "):
            continue
        # A literal compared against (=== "all_three") is a value, not text.
        displayed = re.sub(r"[=!]==?\s*(?:" + _STRING_LITERAL.pattern + ")", "", line)
        texty = any(_has_visible_text(lit) for lit in _STRING_LITERAL.findall(displayed)) or _ESCAPED_TEXT_JOIN.search(line)
        if texty and "+" in line and "wwRichLabelHtml(" not in _statement(lines, number - 1):
            offenders.append(f"{number}: {line.strip()}")
    return offenders


def test_no_bare_text_plus_rich_markup_composition():
    """The root-cause shape: a word-bearing string (or escapeHtml(text))
    concatenated with a rich helper, outside one wwRichLabelHtml() unit."""
    source = _source()
    exempt = set()
    for signature in _WRAPPED_BY_CALLER + ["function wwRichLabelHtml(html)"]:
        start = source.index(signature)
        first = source.count("\n", 0, start) + 1
        last = first + _function_body(source, signature).count("\n")
        exempt.update(range(first, last + 1))
    offenders = _bare_compositions(source, frozenset(exempt))
    assert offenders == [], "compose mixed text + rich markup through wwRichLabelHtml():\n" + "\n".join(offenders)


def test_composition_guard_flags_the_pre_fix_shapes():
    # Exactly the lines that rendered "Default ContextV<sub>AB</sub>" and
    # "Selected: ..." before the fix -- and their wrapped replacements.
    pre_fix = "\n".join([
        "            return parts ? escapeHtml(parts.prefix) + wwLineToLinePairHtml(parts.pair, parts.phaseDisplay) : escapeHtml(calc ? calc.name : \"\");",
        "            statusEl.innerHTML = \"Selected: \" + wwCalculatedChannelNameHtml(calc) + (isVisible ? \"\" : \" (hidden)\") +",
        "                escapeHtml(countText);",
        "            if (el) el.innerHTML = wwRoleLabelHtml(roleKey) + \" magnitude\";",
    ])
    assert len(_bare_compositions(pre_fix)) == 3
    fixed = "\n".join([
        "            return parts ? wwRichLabelHtml(escapeHtml(parts.prefix) + wwLineToLinePairHtml(parts.pair, parts.phaseDisplay)) : escapeHtml(calc ? calc.name : \"\");",
        "            if (el) el.innerHTML = wwRichLabelHtml(wwRoleLabelHtml(roleKey) + \" magnitude\");",
        "            html += '<span>' + (all ? escapeHtml(option.label) : wwLineToLinePairHtml(option.value, pd)) + '</span>';",
    ])
    assert _bare_compositions(fixed) == []


def test_readable_operation_words_take_a_space_before_the_parenthesis():
    source = _source()
    for signature in _OPERATION_TEXT:
        body = _function_body(source, signature)
        joined = [lit for lit in _STRING_LITERAL.findall(body) if re.search(r"[A-Za-z]\($", lit[1:-1])]
        assert joined == [], f"{signature}: {joined} -- use 'Name (' (e.g. \"RMS (\")"
    assert '"RMS (" + labels[0] + ")"' in _function_body(source, "function wwCcComputeSuggestedName()")
    assert '"Abs (" + labels[0] + ")"' in _function_body(source, "function wwCcComputeSuggestedName()")
    assert '"Result = RMS (" + labels[0]' in _function_body(source, "function wwCcComputeExpressionPreviewParts(html)")
    assert 'return "RMS (" + names[0]' in _function_body(source, "function wwCcExpressionParts(calc, html)")


def test_symbolic_operation_forms_are_unchanged():
    # Mathematical forms stay symbolic: −x, |x|, k × x, A + B, A − B.
    body = _function_body(source := _source(), "function wwCcComputeExpressionPreviewParts(html)")
    for form in ('"Result = −" + labels[0]', '"Result = |" + labels[0] + "|"', '" × " + labels[0]',
                 'labels.join(" + ")', 'labels.join(" − ")'):
        assert form in body, form
    stored = _function_body(source, "function wwCcExpressionParts(calc, html)")
    for form in ('"-1 × " + names[0]', '"|" + names[0] + "|"', 'names.join(" + ")', 'names.join(" − ")'):
        assert form in stored, form
