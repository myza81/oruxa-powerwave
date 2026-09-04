"""Static checks for the Angle-axis enhancement (DEC-078): Voltage Angle/
Current Angle channels plot against a genuine secondary (right) Plotly
y-axis, keyed purely on the canonical `channel.engineeringQuantity` --
never source format, never channel name, never re-classified in the
frontend. Grouping itself (which panel a channel lands in) is
unchanged, still keyed on the broad `engineeringType`.

These are structural/source-text checks (the same convention every
other test_frontend_*.py file in this suite uses) -- real behavioral
proof lives in the throwaway live-browser Playwright UAT run for this
enhancement (not committed, per this suite's own established
convention for genuinely visual/interactive verification).
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class TestEngineeringQuantityThreadedToPlottingState:
    """Task section C: engineering_quantity must reach the plotted
    channel object via the existing hop chain, using the canonical API
    value verbatim -- never re-classified, never inferred from a
    channel's own name."""

    def test_row_attrs_carries_engineering_quantity_from_the_api_value(self):
        source = _source()
        body = _function_body(source, "function analogChannelRowAttrs(source, channel, timebase)", "function digitalChannelRowAttrs")
        assert 'data-engineering-quantity="' in body
        assert "channel.engineering_quantity" in body

    def test_meta_from_row_reads_engineering_quantity_back(self):
        source = _source()
        body = _function_body(source, "function analogMetaFromRow(row)", "function digitalMetaFromRow")
        assert "engineeringQuantity: row.dataset.engineeringQuantity" in body

    def test_add_selected_channels_carries_engineering_quantity_onto_the_channel_entry(self):
        source = _source()
        body = _function_body(source, "async function wwAddSelectedChannels(channelMetas, options)", "function wwRemoveChannelByKey")
        assert body.count("engineeringQuantity: meta.engineeringQuantity") == 2  # ww.channelMeta AND channelEntry


class TestAngleAxisRule:
    """Task section D/G: the ONE explicit rule -- Voltage Angle/Current
    Angle to secondary, everything else (including "Undefined")
    preserves existing behavior. Never a broad-engineering_type check."""

    def test_wwChannelUsesAngleQuantity_checks_exact_quantity_strings(self):
        source = _source()
        body = _function_body(source, "function wwChannelUsesAngleQuantity(channel)", "function wwPanelNeedsSecondaryAxis")
        assert 'channel.engineeringQuantity === "Voltage Angle"' in body
        assert 'channel.engineeringQuantity === "Current Angle"' in body

    def test_wwBuildTrace_assigns_y2_only_via_the_angle_quantity_check(self):
        source = _source()
        body = _function_body(source, "function wwBuildTrace(channel, panel)", "function wwBuildLayout(panel, colors)")
        assert 'trace.yaxis = "y2"' in body
        assert "wwChannelUsesAngleQuantity(channel)" in body
        assert "wwPanelNeedsSecondaryAxis(panel)" in body
        # Never keyed on broad engineeringType or source format.
        assert "channel.engineeringType" not in body
        assert "file_format" not in body
        assert "source_format" not in body
        assert "provider_type" not in body


class TestSecondaryAxisLazyCreation:
    """Task section E/F: a genuine Plotly yaxis2, created only when the
    panel actually mixes an angle channel with a non-angle one."""

    def test_yaxis2_only_added_when_panel_needs_it(self):
        source = _source()
        body = _function_body(source, "function wwBuildLayout(panel, colors)", "function wwInitPanelPlot(panel)")
        assert "if (wwPanelNeedsSecondaryAxis(panel)) {" in body
        assert "layout.yaxis2 = wwPanelYAxis2Layout(colors);" in body

    def test_yaxis2_layout_overlays_right_never_a_second_panel(self):
        source = _source()
        body = _function_body(source, "function wwPanelYAxis2Layout(colors)", "function wwSyncPanelAngleAxis(panel)")
        assert 'overlaying: "y"' in body
        assert 'side: "right"' in body

    def test_needs_secondary_axis_requires_a_genuine_mix(self):
        # A panel of ONLY angle channels (or only non-angle channels)
        # must NOT be treated as needing a secondary axis -- task
        # section L's own "no awkward isolated right axis" guardrail.
        source = _source()
        body = _function_body(source, "function wwPanelNeedsSecondaryAxis(panel)", "function wwPanelYAxisTitle(panel)")
        assert "angleCount > 0 && angleCount < panel.channels.length" in body


class TestAxisTitles:
    """Task section J: right axis title is always the safe literal
    "Angle", never a guessed unit ("deg"/"rad"), never "Undefined"."""

    def test_secondary_axis_title_is_the_literal_angle(self):
        source = _source()
        body = _function_body(source, "function wwPanelYAxis2Layout(colors)", "function wwSyncPanelAngleAxis(panel)")
        assert '{ text: "Angle" }' in body
        for forbidden in ("deg", "rad", "°"):
            assert forbidden not in body.lower()

    def test_primary_axis_title_unchanged_for_non_angle_panels(self):
        source = _source()
        body = _function_body(source, "function wwPanelYAxisTitle(panel)", "function wwPanelYAxis2Layout(colors)")
        # Existing "first channel's own unit" rule, verbatim.
        assert "panel.channels.length ? panel.channels[0].unit : \"\"" in body
        # Angle-only exception.
        assert 'return "Angle";' in body


class TestSeparateModeAngleOnlyPanel:
    """Task section L: a standalone angle channel (Separate mode, or an
    angle-only Custom group) keeps its ONE axis (retitled "Angle")
    rather than an isolated, empty-left/lone-right split."""

    def test_angle_only_panel_never_needs_a_secondary_axis(self):
        source = _source()
        body = _function_body(source, "function wwPanelNeedsSecondaryAxis(panel)", "function wwPanelYAxisTitle(panel)")
        # angleCount < panel.channels.length is false when ALL channels
        # are angle -- so an angle-only panel never satisfies this
        # function's own condition, confirmed structurally here.
        assert "angleCount < panel.channels.length" in body

    def test_angle_only_panel_retitles_its_one_axis(self):
        source = _source()
        body = _function_body(source, "function wwPanelYAxisTitle(panel)", "function wwPanelYAxis2Layout(colors)")
        assert "panel.channels.every(wwChannelUsesAngleQuantity)" in body


class TestDynamicPanelMembershipReconciliation:
    """Task sections F/K/M: adding/removing a channel from an
    already-rendered panel must immediately reconcile which traces use
    which axis, and whether the secondary axis itself should exist."""

    def test_add_trace_to_panel_reconciles_after_adding(self):
        source = _source()
        body = _function_body(source, "function wwAddTraceToPanel(panel, channelEntry)", "// Shared X/time viewport")
        assert "wwSyncPanelAngleAxis(panel);" in body

    def test_remove_channel_reconciles_when_panel_survives(self):
        source = _source()
        body = _function_body(source, "function wwRemoveChannel(panel, channel)", "function wwRemovePanelDom(panel)")
        assert "wwSyncPanelAngleAxis(panel);" in body

    def test_remove_channels_by_keys_reconciles_per_surviving_panel(self):
        source = _source()
        body = _function_body(source, "function wwRemoveChannelsByKeys(keys)", "wwUpdateEmptyState();")
        assert "wwSyncPanelAngleAxis(panel);" in body

    def test_sync_restyles_traces_and_toggles_yaxis2(self):
        source = _source()
        body = _function_body(source, "function wwSyncPanelAngleAxis(panel)", "function wwBuildTrace(channel, panel)")
        assert "Plotly.restyle(panel.chartEl, { yaxis: yaxisPerTrace }" in body
        assert "yaxis2: needsSecondary ? wwPanelYAxis2Layout(colors) : null" in body


class TestGroupingUnchanged:
    """Task section A/H/I: grouping (wwPanelGroupKeyFor) must NOT be
    touched -- Voltage + Voltage Angle already land in the same panel
    today via the broad engineeringType key; only axis selection within
    that panel is new."""

    def test_panel_group_key_still_keyed_on_broad_engineering_type_only(self):
        source = _source()
        body = _function_body(source, "function wwPanelGroupKeyFor(channel)", "function wwTimeGroupLabelSuffix(channel)")
        assert 'baseKey = channel.engineeringType || "Undefined";' in body
        assert "engineeringQuantity" not in body


class TestFormatIndependence:
    """Task section B/H: no CSV/Excel/COMTRADE branching anywhere in the
    new angle-axis code."""

    def test_no_format_branching_in_any_new_helper(self):
        source = _source()
        start = source.index("function wwChannelUsesAngleQuantity(channel)")
        end = source.index("function wwBuildLayout(panel, colors)", start)
        combined = source[start:end]
        for forbidden in ("file_format", "source_format", "provider_type", '"COMTRADE"', '"CSV"', '"Excel"'):
            assert forbidden not in combined
