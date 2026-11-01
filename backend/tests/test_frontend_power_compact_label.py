"""Static regression checks for the power-channel compact label feature
(DEC-208 / DEC-202 display improvement).

wwPowerCompactLabel() returns a plain-text compact label for single- and
three-phase power calculated channels (e.g. "P₃ · PMJY1 · IBT1 HV VA"),
or null when no compact label is appropriate (multi-source, missing
inventory, collision, non-power operation, user alias).

All callers (wwCalculatedChannelDisplayText, wwCalculatedChannelNameHtml,
wwCalculatedChannelNamePlotly) are verified to call the helper and follow
the same priority order: user alias → compact power label → L-L notation →
canonical name.
"""

from __future__ import annotations

import re
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


# ------------------------------------------------------------------
# WW_POWER_COMPACT_GLYPHS — six power operations, no (t)
# ------------------------------------------------------------------


def test_compact_glyphs_defined_for_all_six_power_operations():
    source = _source()
    body = _function_body(source, "const WW_POWER_COMPACT_GLYPHS = {", "// Returns a plain-text compact label")
    for key in ("active_power", "reactive_power", "apparent_power",
                "three_phase_active_power", "three_phase_reactive_power", "three_phase_apparent_power"):
        assert key + ":" in body, f"WW_POWER_COMPACT_GLYPHS missing key: {key}"


def test_compact_glyphs_have_no_parenthetical_t():
    source = _source()
    body = _function_body(source, "const WW_POWER_COMPACT_GLYPHS = {", "// Returns a plain-text compact label")
    assert "(t)" not in body, "compact glyphs must not contain (t) — display-only form"


def test_compact_glyphs_single_phase_values():
    source = _source()
    body = _function_body(source, "const WW_POWER_COMPACT_GLYPHS = {", "// Returns a plain-text compact label")
    assert '"P"' in body
    assert '"Q"' in body
    assert '"|S|"' in body


def test_compact_glyphs_three_phase_values_use_subscript_three():
    source = _source()
    body = _function_body(source, "const WW_POWER_COMPACT_GLYPHS = {", "// Returns a plain-text compact label")
    # U+2083 is the subscript digit 3 (₃); these must appear literally in the source
    assert "P₃" in body  # P₃
    assert "Q₃" in body  # Q₃
    assert "|S₃|" in body  # |S₃|


# ------------------------------------------------------------------
# wwPowerCompactLabel — safety checks
# ------------------------------------------------------------------


def _compact_label_body(source: str) -> str:
    return _function_body(source, "function wwPowerCompactLabel(calc)", "// Plain-text display name")


def test_power_compact_label_guards_null_calc():
    source = _source()
    body = _compact_label_body(source)
    assert "if (!calc) return null;" in body


def test_power_compact_label_returns_null_for_non_power_operation():
    source = _source()
    body = _compact_label_body(source)
    assert "const glyph = WW_POWER_COMPACT_GLYPHS[calc.operation];" in body
    assert "if (!glyph) return null;" in body


def test_power_compact_label_guards_missing_first_input():
    source = _source()
    body = _compact_label_body(source)
    assert "v1.kind !== \"source\"" in body


def test_power_compact_label_falls_back_for_multi_source():
    # Owner requirement: do not identify a multi-source power calculation
    # solely by its voltage recording.
    source = _source()
    body = _compact_label_body(source)
    assert "inp.source_id !== v1.source_id" in body
    assert "return null;" in body


def test_power_compact_label_falls_back_when_inventory_unavailable():
    # Owner requirement: when source metadata is unavailable, fall back to calc.name.
    source = _source()
    body = _compact_label_body(source)
    assert "ww.sourceChannelInventory.get(calc.reference_source_id)" in body
    assert "if (!inv) return null;" in body


def test_power_compact_label_collision_check_iterates_loaded_calcs():
    # Owner requirement: collision-safe fallback — two distinguishable channels
    # must not receive the same compact label.
    source = _source()
    body = _compact_label_body(source)
    assert "for (const [id, other] of ww.calculatedChannels)" in body
    assert "if (id === calc.id) continue;" in body
    # When a collision is found, both fall back to calc.name (return null).
    assert "=== raw) return null;" in body


def test_power_compact_label_label_format():
    # The label must be: glyph + " · " + sourceName + " · " + channelDisplayName
    source = _source()
    body = _compact_label_body(source)
    assert "inv.sourceName" in body
    assert "wwChannelDisplayName(v1.source_id, v1.channel_name)" in body
    # Separator is U+00B7 (middle dot) with spaces
    assert "·" in body  # ·


# ------------------------------------------------------------------
# Caller integration — priority chain
# ------------------------------------------------------------------


def test_display_text_calls_compact_label():
    # wwCalculatedChannelDisplayText: user alias → compact power label → canonical name
    source = _source()
    body = _function_body(
        source,
        "function wwCalculatedChannelDisplayText(calc)",
        "// Calculated-channel name for HTML surfaces.",
    )
    assert "wwCalculatedChannelUserName(calc)" in body
    assert "wwPowerCompactLabel(calc)" in body
    assert "calc.name" in body
    # Explicit priority: user alias checked first
    assert body.index("wwCalculatedChannelUserName") < body.index("wwPowerCompactLabel")


def test_name_html_calls_compact_label():
    # wwCalculatedChannelNameHtml: user alias → compact power label → L-L → canonical name
    source = _source()
    body = _function_body(
        source,
        "function wwCalculatedChannelNameHtml(calc)",
        "// Plotly trace-name variant",
    )
    assert "wwPowerCompactLabel(calc)" in body
    assert "if (powerLabel) return escapeHtml(powerLabel);" in body
    # Must precede L-L check
    assert body.index("wwPowerCompactLabel") < body.index("wwLineToLineSystemName")


def test_name_plotly_calls_compact_label():
    # wwCalculatedChannelNamePlotly: user alias → compact power label → L-L → canonical name
    source = _source()
    body = _function_body(
        source,
        "function wwCalculatedChannelNamePlotly(calc)",
        "// Any analog channel's display name",
    )
    assert "wwPowerCompactLabel(calc)" in body
    assert "if (powerLabel) return powerLabel;" in body
    # Must precede L-L check
    assert body.index("wwPowerCompactLabel") < body.index("wwLineToLineSystemName")


def test_user_alias_checked_before_compact_label_in_all_callers():
    source = _source()
    for sig, next_sig in [
        ("function wwCalculatedChannelDisplayText(calc)", "// Calculated-channel name for HTML surfaces."),
        ("function wwCalculatedChannelNameHtml(calc)", "// Plotly trace-name variant"),
        ("function wwCalculatedChannelNamePlotly(calc)", "// Any analog channel's display name"),
    ]:
        body = _function_body(source, sig, next_sig)
        assert body.index("wwCalculatedChannelUserName") < body.index("wwPowerCompactLabel"), \
            f"user alias must be checked before compact label in {sig}"


# ------------------------------------------------------------------
# L-L voltage and non-power operations — unchanged behavior
# ------------------------------------------------------------------


def test_ll_voltage_not_handled_by_compact_label():
    # line_to_line_voltage is not in WW_POWER_COMPACT_GLYPHS; its display
    # path is unchanged (wwLineToLineSystemName).
    source = _source()
    glyph_body = _function_body(source, "const WW_POWER_COMPACT_GLYPHS = {", "// Returns a plain-text compact label")
    assert "line_to_line_voltage" not in glyph_body


def test_ll_path_still_present_in_name_html_after_compact_label_check():
    source = _source()
    body = _function_body(source, "function wwCalculatedChannelNameHtml(calc)", "// Plotly trace-name variant")
    assert "wwLineToLineSystemName(calc)" in body
    assert "wwLineToLinePairHtml" in body


def test_ll_path_still_present_in_name_plotly_after_compact_label_check():
    source = _source()
    body = _function_body(source, "function wwCalculatedChannelNamePlotly(calc)", "// Any analog channel's display name")
    assert "wwLineToLineSystemName(calc)" in body
    assert "wwLineToLinePairPlotly" in body


# ------------------------------------------------------------------
# CC list summary row — no repeated input names
# ------------------------------------------------------------------


def test_summary_row_no_longer_contains_input_names_html():
    # Owner requirement: remove repeated input-channel names from the CC
    # list summary row. Full expression stays in the expression row.
    source = _source()
    body = _function_body(
        source,
        "function wwRenderCalculatedChannelManagerList()",
        "function wwRenderCalculatedChannelsPage()",
    )
    # The inputNamesHtml variable must no longer be declared in this function.
    assert "const inputNamesHtml" not in body
    # The summary row must not join input display names.
    assert "wwCcInputDisplayNameHtml).join" not in body


def test_summary_row_retains_operation_label_and_null_policy():
    # After removing input names, the summary must still show the operation
    # label and null-handling policy summary (e.g. "Active Power · Null: Propagate").
    source = _source()
    body = _function_body(
        source,
        "function wwRenderCalculatedChannelManagerList()",
        "function wwRenderCalculatedChannelsPage()",
    )
    assert "meta ? meta.label : calc.operation" in body
    assert "wwCcNullPolicySummaryText(calc)" in body


def test_expression_row_still_present_for_full_details():
    # Full expression (all input channel identities) must remain accessible
    # in the expression row — the owner's requirement for accessible details.
    source = _source()
    body = _function_body(
        source,
        "function wwRenderCalculatedChannelManagerList()",
        "function wwRenderCalculatedChannelsPage()",
    )
    assert "ww-cc-list-row-expr" in body
    assert "wwCcExpressionHtmlFor(calc)" in body
