"""Table View empty-state rendering fix (2026-09-06).

Root cause: `.ww-data-prep-pagination` (a class Table View's own pager
shares with Data Preparation's) sets `display: flex` as an author rule,
which wins over the `hidden` ATTRIBUTE by CSS-origin precedence
regardless of specificity -- the SAME bug class already fixed several
times elsewhere in this file for other elements (e.g.
`#wwDataPrepTimeAxisDetectCard[hidden]`,
`.ww-data-prep-conversion-action[hidden]`). `wwTableRenderEmptyState()`/
`wwTableFetchPage()` were already correctly setting
`wwTablePagination.hidden = true`, but it had zero visual effect: the
First/Previous/Page/Next/Last controls stayed rendered even with no
recordings loaded or a selected recording with zero rows.

This module only checks the fix's own static source-text footprint
(same convention every other test_frontend_*.py file in this suite
uses -- no JS execution engine is part of this repo's test harness),
scoped strictly to Table View's own ids/functions. It does not touch
or re-test anything about the Data Preparation page, which is out of
scope for this fix and has its own dedicated test module.
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


class TestTablePaginationHiddenAttributeBugFix:
    """The CSS root cause: an ID-scoped override restores `hidden`'s
    effect for Table View's own pagination row without touching the
    shared `.ww-data-prep-pagination` class Data Preparation's own
    pagination also relies on."""

    def test_pagination_hidden_override_exists_and_is_scoped_to_the_table_id(self):
        source = _source()
        assert "#wwTablePagination[hidden] { display: none; }" in source

    def test_shared_pagination_class_itself_is_untouched(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-pagination {", "}")
        assert "display: flex" in rule


class TestTableEmptyStateMessageVariesByState:
    """Requirement 1 vs 2: a zero-recordings workspace and an ordinary
    "nothing selected yet" state must show DIFFERENT messages, both
    read from the SAME `wwTable.availableSources` list
    `wwTableRenderSourceSelect()` already keys its own disabled state
    off -- never a second, duplicated source-count check."""

    def test_empty_state_function_branches_on_available_sources_length(self):
        source = _source()
        body = _function_body(source, "function wwTableRenderEmptyState() {", "}\n")
        assert "wwTable.availableSources.length === 0" in body
        assert "No recordings available" in body
        assert "Select or open a recording to view table data." in body

    def test_empty_state_still_hides_pagination_and_the_table(self):
        source = _source()
        body = _function_body(source, "function wwTableRenderEmptyState() {", "}\n")
        assert 'getElementById("wwTablePagination").hidden = true;' in body
        assert 'getElementById("wwTableWrap").hidden = true;' in body

    def test_source_selector_is_disabled_only_when_there_are_zero_recordings(self):
        # Pre-existing logic (unchanged by this fix) -- asserted here
        # too since it is load-bearing for requirement 1/2's "selector
        # enabled/disabled" distinction and this module is the one place
        # Table View's own empty-state behavior is now covered end to
        # end.
        source = _source()
        body = _function_body(source, "function wwTableRenderSourceSelect() {", "function wwTableOnActivated() {")
        assert "wwTable.availableSources.length === 0" in body
        assert "select.disabled = true;" in body
        assert "select.disabled = false;" in body


class TestTableSelectedRecordingWithZeroRows:
    """Requirement 3: a selected recording whose table has zero rows
    must show an empty-table message and never fall through to
    wwTableRenderTable()/wwTableRenderPagination() (which previously
    rendered an empty table WITH a live "Page 1 of 1" pager -- the same
    "looks broken" symptom this task exists to fix, just for a
    different trigger than zero recordings)."""

    def _fetch_page_body(self, source: str) -> str:
        return _function_body(
            source, "async function wwTableFetchPage() {", "\n        document.getElementById(\"wwTableSourceSelect\").addEventListener"
        )

    def test_zero_row_response_shows_a_message_and_skips_table_and_pagination_render(self):
        source = _source()
        body = self._fetch_page_body(source)
        assert "if (body.total_row_count === 0) {" in body
        assert "This recording has no table rows." in body

    def test_zero_row_branch_hides_wrap_and_pagination(self):
        source = _source()
        body = self._fetch_page_body(source)
        zero_row_start = body.index("if (body.total_row_count === 0) {")
        zero_row_end = body.index("}", zero_row_start)
        zero_row_branch = body[zero_row_start:zero_row_end]
        assert 'getElementById("wwTableWrap").hidden = true;' in zero_row_branch
        assert 'getElementById("wwTablePagination").hidden = true;' in zero_row_branch

    def test_nonzero_row_response_still_renders_table_and_pagination(self):
        # Requirement 4: existing populated-recording behavior preserved
        # exactly -- the zero-row short-circuit must not affect the
        # normal success path below it.
        source = _source()
        body = self._fetch_page_body(source)
        assert "wwTableRenderTable(body);" in body
        assert "wwTableRenderPagination(body);" in body
        # The populated-path calls must come AFTER the zero-row
        # short-circuit's own `return;`, i.e. still reachable only when
        # that branch is not taken.
        zero_row_pos = body.index("if (body.total_row_count === 0) {")
        render_table_pos = body.index("wwTableRenderTable(body);")
        assert zero_row_pos < render_table_pos
