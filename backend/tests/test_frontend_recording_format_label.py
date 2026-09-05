"""Structural checks for the Recording Events File Format display-
consistency fix: the raw format value's CASING differs depending on
which backend code path produced it (COMTRADE ingestion sets
`provider_type = "COMTRADE"`; a "Needs Preparation" CSV/Excel row uses
`file_format` verbatim, "CSV"/"Excel"; a source already converted to
Ready lowercases it to "csv"/"excel") -- so the SAME file type could
previously display differently depending on status/origin.
`formatFileFormatLabel()` is the ONE shared presentation-layer
normalizer (uppercase, display only) both display sites now route
through, rather than a per-row/per-workflow special case.

These are static source-text checks, the same convention every other
test_frontend_*.py file in this suite uses -- no JS execution engine is
part of this repository's test harness.
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


class TestSharedFormatter:
    def test_formatter_exists_and_uppercases(self):
        source = _source()
        body = _function_body(
            source,
            "function formatFileFormatLabel(rawFormat)",
            "function recordingFormatLabel(source)",
        )
        assert ".toUpperCase()" in body
        # Falsy input (no format known yet) must not become a literal
        # "NULL"/"UNDEFINED" string -- callers supply their own fallback.
        assert "rawFormat ? " in body

    def test_only_one_file_format_uppercasing_implementation_exists(self):
        # Guards against a future regression re-introducing a second,
        # independently-drifting file-format normalizer instead of
        # reusing this one (other unrelated `.toUpperCase()` uses
        # elsewhere in this file, e.g. column letters, are out of scope).
        source = _source()
        assert source.count("function formatFileFormatLabel(rawFormat)") == 1


class TestRecordingEventsTableUsesSharedFormatter:
    def test_recording_format_label_delegates_to_shared_formatter(self):
        source = _source()
        body = _function_body(
            source,
            "function recordingFormatLabel(source)",
            "function formatRecordingDuration(seconds)",
        )
        assert "formatFileFormatLabel(source.provider_type)" in body
        # Never re-implements its own casing/derivation.
        assert ".toUpperCase()" not in body


class TestDataPreparationWorkspaceUsesSharedFormatter:
    """Task's own 'check whether the same file-format value is rendered
    elsewhere in closely related Recording Events UI components' --
    the Data Preparation Workspace's own 'Source' fact is opened
    directly from a Recording Events row and displays the exact same
    underlying value."""

    def test_source_fact_display_uses_shared_formatter(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderMeta()",
            "function wwDataPrepRenderWorksheetSelector()",
        )
        assert "formatFileFormatLabel(wwDataPrep.format)" in body

    def test_underlying_wwdataprep_format_value_and_its_branches_are_unchanged(self):
        # Presentation-layer-only requirement: every existing
        # `wwDataPrep.format` equality check (worksheet handling, region
        # wording) must keep comparing the RAW, un-uppercased value --
        # never the display-normalized one.
        source = _source()
        assert 'wwDataPrep.format = summary.file_format' in source
        assert 'wwDataPrep.format === "Excel"' in source
        assert 'wwDataPrep.format !== "Excel"' in source
