"""Structural checks for the shared recording/event time-identity
presentation fix: `wwFormatRecordingTimeIdentity(source, opts)` is the
ONE function that decides how a recording/event's start time / time
identity is displayed, reused by both the Recording Events table
(`formatRecordingStartTime()`) and the Recording sidebar
(`wwFormatSourceTimeIdentity()`) rather than each screen maintaining its
own partial copy of this policy.

Policy, in order:
  1. Time of Day -> the known clock-time origin, never a fabricated date.
  2. A real `start_time` -> the actual absolute DateTime.
  3. Neither -> a named label for the non-positional Time Axis kind
     (Elapsed Time / Sample Number / Index / Reconstructed Time / Manual
     Interpretation), reusing WW_DATA_PREP_INTERPRETER_LABELS -- never
     "—" merely because a timeline is non-absolute.

Same static source-text convention every other test_frontend_*.py file
in this suite uses -- no JS execution engine is part of this repo's
test harness.
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


class TestSharedHelperExistsAndIsReused:
    def test_only_one_shared_time_identity_function_exists(self):
        source = _source()
        assert source.count("function wwFormatRecordingTimeIdentity(source, opts)") == 1

    def test_recording_events_table_delegates_to_the_shared_helper(self):
        source = _source()
        body = _function_body(
            source, "function formatRecordingStartTime(source)", "function formatSamplingRate(rate)",
        )
        assert "return wwFormatRecordingTimeIdentity(source);" in body

    def test_sidebar_delegates_to_the_shared_helper_in_compact_mode(self):
        source = _source()
        body = _function_body(
            source, "function wwFormatSourceTimeIdentity(source)", "function wwFormatSourceSummaryLine(source)",
        )
        assert "return wwFormatRecordingTimeIdentity(source, { compact: true });" in body

    def test_sidebar_no_longer_omits_the_segment_when_start_time_is_null(self):
        # UAT root cause: the OLD wwFormatSourceStartTimestamp(startTime)
        # returned "" whenever start_time was null, and the caller
        # conditionally omitted the whole segment -- silently hiding
        # Time of Day/Elapsed/etc. recordings' own time identity. Both
        # are gone; the new function always returns a real value.
        source = _source()
        assert "function wwFormatSourceStartTimestamp(startTime)" not in source
        assert 'if (!startTime) return "";' not in source


class TestSharedPolicyBranches:
    def _shared_body(self, source: str) -> str:
        return _function_body(
            source, "function wwFormatRecordingTimeIdentity(source, opts)", "function formatRecordingStartTime(source)",
        )

    def test_time_of_day_branch_never_fabricates_a_date(self):
        source = _source()
        body = self._shared_body(source)
        assert 'source.timing_reference === "time_of_day"' in body
        assert "wwFormatClockTimeFromTotalSeconds(source.time_of_day_reference_seconds, 3, false)" in body

    def test_absolute_branch_reads_start_time(self):
        source = _source()
        body = self._shared_body(source)
        assert "if (source.start_time) {" in body
        assert 'source.start_time.replace("T", " ")' in body

    def test_compact_option_only_affects_absolute_truncation(self):
        source = _source()
        body = self._shared_body(source)
        assert "if (!opts.compact) return spaced;" in body
        assert "spaced.slice(0, dotIndex + 5)" in body

    def test_fallback_uses_the_shared_interpreter_label_map_not_a_dash_only(self):
        source = _source()
        body = self._shared_body(source)
        assert "WW_DATA_PREP_INTERPRETER_LABELS[source.preparation_interpreter_id] || \"—\"" in body

    def test_fallback_label_map_has_all_four_required_policy_labels(self):
        # The exact user-facing fallback labels the task requires --
        # reused verbatim from the Data Preparation Time Format dropdown's
        # own label map, never a second, divergent label set.
        source = _source()
        assert 'elapsed_numeric: "Elapsed Time",' in source
        assert 'sample_index: "Sample Number / Index",' in source
        assert 'repeated_timestamp_precision_loss: "Reconstructed Time",' in source
        assert 'manual: "Manual Interpretation",' in source


class TestSidebarTimeIdentityIsItsOwnLine:
    def test_time_identity_span_is_rendered_alongside_the_stats_span(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderSourceRecordingHtml(sourceSummary, isFirst)", "async function wwRenderWorkspaceRecordings",
        )
        assert '<span class="source-recording-meta">' in body
        assert '<span class="source-recording-time-identity">' in body
        assert "wwFormatSourceTimeIdentity(sourceSummary)" in body

    def test_time_identity_css_class_exists_as_its_own_block_line(self):
        source = _source()
        assert ".source-recording-time-identity {" in source
        body = _function_body(source, ".source-recording-time-identity {", "}")
        assert "display: block;" in body
