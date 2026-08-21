"""Source-level checks for workspace-sidebar typography."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = ROOT / "frontend" / "index.html"


def read_index() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


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


def assert_font_size(source: str, selector: str, size: str) -> None:
    blocks = declaration_blocks(source, selector)
    assert blocks, f"Missing CSS declaration block for {selector}"
    assert any(f"font-size: {size};" in block for block in blocks)


def test_workspace_sidebar_normal_text_uses_requested_size():
    html = read_index()

    assert_font_size(html, "#workspaceSidebar", "0.7rem")
    assert_font_size(html, "#workspaceSidebar section.panel h2", "0.7rem")
    assert_font_size(html, ".active-recording h2", "0.7rem")
    assert_font_size(html, ".active-recording-name", "0.7rem")
    assert_font_size(html, ".active-recording-meta", "0.7rem")
    assert_font_size(html, "#workspaceSidebar .empty-state", "0.7rem")
    assert_font_size(html, "table.channels", "0.7rem")
    assert_font_size(html, "table.channels caption", "0.7rem")
    assert_font_size(html, "table.channels th", "0.7rem")
    assert_font_size(html, ".digital-cur-badge", "0.7rem")
    assert_font_size(html, "#workspaceSidebar input[type=\"search\"]", "0.7rem")
    assert_font_size(html, "#channelSearchCount", "0.7rem")
    assert_font_size(
        html,
        "details.channel-group summary,\n        details.channel-subgroup summary",
        "0.7rem",
    )
    assert_font_size(html, "#workspaceSidebar .chevron", "0.7rem")
    assert_font_size(html, "#workspaceSidebar .count-badge", "0.7rem")
    assert_font_size(html, "details.channel-subgroup summary", "0.7rem")


def test_shared_non_sidebar_typography_stays_unchanged():
    html = read_index()

    assert_font_size(html, "input[type=\"search\"]", "0.75rem")
    assert_font_size(html, ".chevron", "0.75rem")
    assert_font_size(html, ".count-badge", "0.78rem")


def test_sidebar_buttons_keep_existing_font_sizes():
    html = read_index()

    assert "--button-font-size-compact: 0.8rem;" in html
    assert_font_size(html, "button", "var(--button-font-size-compact)")
    assert_font_size(html, "button.secondary", "var(--button-font-size-compact)")
    assert_font_size(html, "button.danger", "var(--button-font-size-compact)")
    assert_font_size(html, ".group-toggle-btn", "0.6rem")
    assert "#workspaceSidebar button" not in html
