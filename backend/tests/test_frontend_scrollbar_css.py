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
    assert "border-right: 1px solid var(--panel-border);" in workspace_sidebar
    assert "background: var(--bg);" in workspace_sidebar

    assert "border: 1px solid var(--panel-border);" in group
    assert "overflow: hidden;" in group
    assert "overflow-x: auto;" in group_body

    assert "background: var(--panel);" in editor
    assert "border: 1px solid var(--panel-border);" in editor
    assert "overflow-y: auto;" in editor
    assert "overflow-x: hidden;" in editor
