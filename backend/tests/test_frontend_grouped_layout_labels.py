"""Static regression checks for grouped-layout analog canvas labels.

The frontend is a single HTML file and this suite's established pattern is
source-text assertions for render/lifecycle invariants. These checks guard the
Phase 4A-UAT4 rule that Grouped/Custom analog panels do not render per-channel
canvas legend chips; Separate mode keeps its per-lane chip.
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


def test_non_initial_refetch_only_refreshes_canvas_legend_in_separate_mode():
    source = _source()
    body = _function_body(source, "async function wwLoadChannelRange", "function wwCreatePanelObject")

    legend_idx = body.index("wwRenderLegend(panel);")
    guard_idx = body.rfind('if (ww.layoutMode === "separate")', 0, legend_idx)

    assert guard_idx != -1


def test_adding_channels_renders_canvas_legend_only_for_separate_mode():
    source = _source()
    body = _function_body(source, "async function wwAddSelectedChannels", "function wwRemoveChannelByKey")

    assert 'if (ww.layoutMode === "separate") {' in body
    assert 'for (const panel of touchedPanels) wwRenderLegend(panel);' in body


def test_removing_from_grouped_panel_does_not_rerender_canvas_legend():
    source = _source()
    body = _function_body(source, "function wwRemoveChannel(panel, channel)", "function wwRemovePanelDom(panel)")

    assert "wwRenderLegend(panel)" not in body


def test_batched_remove_from_grouped_panel_does_not_rerender_canvas_legend():
    source = _source()
    body = _function_body(source, "function wwRemoveChannelsByKeys(keys)", "// ==================================================================\n        // Phase 4A: Digital channel region")

    assert "wwRenderLegend(panel)" not in body


def test_layout_rebuild_clears_grouped_canvas_legend_and_restores_separate_only():
    """Time Group Canvas: wwRebuildLayout() clears each EXISTING canvas's
    own `.ww-tg-panels` container (not a single workspace-wide
    #wwPanels) -- the canvas root itself survives a layout-mode switch
    unchanged."""
    source = _source()
    body = _function_body(source, "function wwRebuildLayout()", "// Phase 4A-UAT7")

    assert 'const panelsEl = canvasEl.querySelector(".ww-tg-panels");' in body
    assert "panelsEl.innerHTML = \"\";" in body
    assert 'if (ww.layoutMode === "separate") wwRenderLegend(panel);' in body
