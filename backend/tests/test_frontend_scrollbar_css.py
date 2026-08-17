"""Source-level checks for the shared frontend scrollbar styling."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THEME_CSS = ROOT / "frontend" / "theme.css"
INDEX_HTML = ROOT / "frontend" / "index.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def declaration_block(source: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}", source)
    assert match, f"Missing CSS declaration block for {selector}"
    return match.group("body")


def declaration_blocks(source: str, selector: str) -> list[str]:
    return [
        match.group("body")
        for match in re.finditer(
            rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}",
            source,
        )
    ]


def section(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_global_scrollbar_baseline_stays_slim_and_borderless():
    css = read(THEME_CSS)

    universal = declaration_block(css, "*")
    webkit_scrollbar = declaration_block(css, "*::-webkit-scrollbar")
    webkit_track = declaration_block(css, "*::-webkit-scrollbar-track")
    webkit_thumb = declaration_block(css, "*::-webkit-scrollbar-thumb")

    assert "scrollbar-width: thin;" in universal
    assert "scrollbar-color: var(--scrollbar-thumb) transparent;" in universal
    assert "width: 6px;" in webkit_scrollbar
    assert "height: 6px;" in webkit_scrollbar
    assert "background: transparent;" in webkit_track
    assert "border: 0;" in webkit_track
    assert "background: var(--scrollbar-thumb);" in webkit_thumb
    assert "border: 0;" in webkit_thumb
    assert "border-radius: 999px;" in webkit_thumb


def test_targeted_scrollbar_tracks_blend_with_local_surfaces():
    css = read(THEME_CSS)

    assert (
        "#mainSidebarMenu {\n"
        "    scrollbar-color: var(--scrollbar-thumb) var(--panel);\n"
        "}"
    ) in css
    assert (
        "#mainSidebarMenu::-webkit-scrollbar-track,\n"
        "#mainSidebarMenu::-webkit-scrollbar-track-piece {\n"
        "    background: var(--panel);\n"
        "    border: 0;\n"
        "}"
    ) in css
    assert (
        "#workspaceSidebar {\n"
        "    scrollbar-color: var(--scrollbar-thumb) var(--bg);\n"
        "}"
    ) in css
    assert (
        "#workspaceSidebar::-webkit-scrollbar-track,\n"
        "#workspaceSidebar::-webkit-scrollbar-track-piece {\n"
        "    background: var(--bg);\n"
        "    border: 0;\n"
        "}"
    ) in css
    assert (
        ".group-editor-box,\n"
        ".group-body {\n"
        "    scrollbar-color: var(--scrollbar-thumb) var(--panel);\n"
        "}"
    ) in css
    assert (
        ".group-editor-box::-webkit-scrollbar-track,\n"
        ".group-editor-box::-webkit-scrollbar-track-piece,\n"
        ".group-body::-webkit-scrollbar-track,\n"
        ".group-body::-webkit-scrollbar-track-piece {\n"
        "    background: var(--panel);\n"
        "    border: 0;\n"
        "}"
    ) in css


def test_uat10_scrollbar_fix_does_not_change_layout_rules():
    css = read(THEME_CSS)
    uat10 = section(
        css,
        "/* Phase 3B-UAT10:",
        "/* Appearance selector",
    )

    assert "width:" not in uat10
    assert "height:" not in uat10
    assert "overflow" not in uat10
    assert "border-right" not in uat10


def test_scroll_container_overflow_and_structural_borders_are_preserved():
    html = read(INDEX_HTML)

    main_sidebar = declaration_block(html, "#mainSidebarMenu")
    workspace_sidebar = declaration_block(html, "#workspaceSidebar")
    group = declaration_block(html, "details.channel-group")
    group_body = declaration_block(html, ".group-body")
    editor = declaration_block(html, ".group-editor-box")

    assert "overflow-y: auto;" in main_sidebar
    assert "overflow-x: hidden;" in main_sidebar
    assert "border-right: 1px solid var(--panel-border);" in main_sidebar
    assert "background: var(--panel);" in main_sidebar

    assert "overflow-y: auto;" in workspace_sidebar
    assert "width: 320px;" in workspace_sidebar
    assert "background: var(--bg);" in workspace_sidebar

    assert "border: 1px solid var(--panel-border);" in group
    assert "overflow: hidden;" in group
    assert "overflow-x: auto;" in group_body

    assert "background: var(--panel);" in editor
    assert "border: 1px solid var(--panel-border);" in editor
    assert "overflow-y: auto;" in editor
    assert "overflow-x: hidden;" in editor


def test_workspace_sidebar_divider_is_on_resize_handle_not_scrollbar_edge():
    html = read(INDEX_HTML)

    workspace_blocks = declaration_blocks(html, "#workspaceSidebar")
    assert workspace_blocks, "Missing #workspaceSidebar CSS"
    assert sum("border-right: 0;" in block for block in workspace_blocks) >= 2
    assert all(
        "border-right: 1px solid var(--panel-border);" not in block
        for block in workspace_blocks
    )

    split_handle = declaration_block(html, ".shell-split-handle")
    split_handle_after = declaration_block(html, ".shell-split-handle::after")
    split_handle_active = declaration_block(
        html,
        ".shell-split-handle:hover::after,\n        .shell-split-handle.shell-split-active::after",
    )

    assert "width: 6px;" in split_handle
    assert "cursor: col-resize;" in split_handle
    assert "touch-action: none;" in split_handle
    assert "left: 2px;" in split_handle_after
    assert "width: 2px;" in split_handle_after
    assert "background: var(--panel-border);" in split_handle_after
    assert "background: var(--accent);" in split_handle_active
    assert 'id="workspaceSplitHandle"' in html
    assert 'role="separator"' in html
    assert 'aria-label="Resize Workspace Sidebar"' in html


def test_workspace_sidebar_resize_and_drawer_rules_are_preserved():
    html = read(INDEX_HTML)
    drawer = section(html, "@media (max-width: 900px)", "@media (max-width: 640px)")

    assert "const SHELL_WORKSPACE_SIDEBAR_DEFAULT_WIDTH = 320;" in html
    assert "const SHELL_WORKSPACE_SIDEBAR_MIN_WIDTH = 240;" in html
    assert "const SHELL_WORKSPACE_SIDEBAR_MAX_WIDTH = 520;" in html
    assert "panelEl: document.getElementById(\"workspaceSidebar\")," in html
    assert "handleEl: document.getElementById(\"workspaceSplitHandle\")," in html
    assert "onResize: wwResizeAllVisiblePlots," in html

    assert "width: min(320px, 82vw);" in drawer
    assert "position: absolute;" in drawer
    assert "border-right: 0;" in drawer
    assert "box-shadow: 2px 0 12px rgba(0, 0, 0, 0.18);" in drawer
    assert "transform: translateX(-110%);" in drawer
    assert ".shell-split-handle { display: none; }" in drawer
