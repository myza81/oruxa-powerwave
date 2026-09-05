"""Structural checks for the Preparation Status integrity guardrail:
"Detection is not configuration. A draft is not an applied Time Axis."

Confirms:
1. A single canonical body-building function (`wwDataPrepTimeAxisConfigBody`)
   is shared by the real Save PUT body and the draft/applied comparison,
   so the two can never silently drift apart.
2. The dirty check (`wwDataPrepTimeAxisDraftIsDirty`) is purely
   client-side (no fetch), returns false when nothing is applied yet
   (that state is its own separate blocker), and compares via the shared
   canonical shape.
3. Preparation Status headline/counts, View Issues, Continue-to-Powerwave,
   and Export Cleaned Data ALL read through the one effective-state
   function (`wwDataPrepEffectiveIssueSummary`) rather than the raw
   backend summary directly -- so they can never disagree.
4. A delegated input/change listener on the Time Axis Details container
   re-renders live on every user edit, with no dedicated per-field
   listener needed.

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


class TestSharedConfigBodyArchitecture:
    def test_only_one_config_body_builder_exists(self):
        source = _source()
        assert source.count("function wwDataPrepTimeAxisConfigBody(") == 1

    def test_save_reuses_the_current_draft_body_builder(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepSetTimeAxis()", "async function wwDataPrepClearTimeAxis()",
        )
        assert "wwDataPrepCurrentTimeAxisDraftBody()" in body
        # No second, independently-maintained body literal for Save.
        assert "column_indices: columnIndices, interpreter_id: interpreterId" not in body

    def test_applied_body_projects_the_last_fetched_summary(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepAppliedTimeAxisDraftBody()",
            "function wwDataPrepTimeAxisDraftIsDirty()",
        )
        assert "wwDataPrep.timeAxisSummary" in body
        assert "wwDataPrepTimeAxisConfigBody(summary.interpreter_id" in body
        # Nothing applied yet is a distinct case, not "dirty".
        assert "if (!summary || !summary.interpreter_id) return null;" in body


class TestConfirmedFieldExcludedWhenNotMeaningful:
    """UAT finding: `wwDataPrepRenderTimeAxisDetectResult()` forces the
    Confirmed checkbox back to `false` on every render for anything
    other than Manual or an offered reconstruction, regardless of what
    the APPLIED configuration's own `confirmed` value actually is (e.g.
    a Time of Day config saved with confirmed=true via direct API/a
    restored session) -- comparing it unconditionally produced a false
    "unsaved changes" positive on a perfectly clean, just-loaded Ready
    source. `confirmed` must only be compared when the checkbox is
    actually a meaningful, user-editable control right now."""

    def test_confirmed_field_comparability_helper_exists(self):
        source = _source()
        assert "function wwDataPrepTimeAxisConfirmedFieldIsComparable()" in source
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisConfirmedFieldIsComparable()",
            "function wwDataPrepTimeAxisDraftIsDirty()",
        )
        assert 'document.getElementById("wwDataPrepTimeAxisConfirmedField").hidden' in body

    def test_dirty_check_normalizes_confirmed_when_not_comparable(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDraftIsDirty()",
            "function wwDataPrepEffectiveIssueSummary()",
        )
        assert "wwDataPrepTimeAxisConfirmedFieldIsComparable()" in body
        assert "draft.confirmed = null;" in body
        assert "applied.confirmed = null;" in body


class TestFetchOrderingKeepsDirtyCheckAccurate:
    """UAT finding: wwDataPrepFetchPreview() calls wwDataPrepFetchIssues()
    (whose own trailing render computes the draft-vs-applied dirty
    check) BEFORE wwDataPrepFetchTimeAxis() repopulates the form to
    match the newly-fetched applied config -- without a second render,
    the dirty check could freeze on a stale verdict computed against
    the PREVIOUS source's form state."""

    def test_fetch_time_axis_re_renders_issues_after_repopulating_the_form(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepFetchTimeAxis()", "function wwDataPrepTimeAxisUnitAndIntervalFromForm(",
        )
        assert "wwDataPrepRenderTimeAxisForm();" in body
        assert "wwDataPrepRenderIssues();" in body
        # The render-form call must come BEFORE the issues re-render, so
        # the dirty check runs against the freshly-repopulated form.
        assert body.index("wwDataPrepRenderTimeAxisForm();") < body.index("wwDataPrepRenderIssues();")


class TestDraftIsDirtyIsClientSideOnly:
    def test_dirty_check_never_fetches(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDraftIsDirty()",
            "function wwDataPrepEffectiveIssueSummary()",
        )
        assert "fetch(" not in body
        assert "JSON.stringify(draft) !== JSON.stringify(applied)" in body

    def test_nothing_applied_yet_is_not_dirty(self):
        # Scenario 1 (never saved) is its OWN separate blocker
        # (ISSUE_TIME_AXIS_UNCONFIGURED) -- must not ALSO show a
        # confusing "unsaved changes" message on top of it.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDraftIsDirty()",
            "function wwDataPrepEffectiveIssueSummary()",
        )
        assert "if (!applied) return false;" in body


class TestEffectiveIssueSummaryIsTheSingleSourceOfTruth:
    def test_headline_and_counts_use_the_effective_summary(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderIssues()", "function wwDataPrepIsIndexOnlyWithoutInterval()",
        )
        assert "wwDataPrepEffectiveIssueSummary()" in body
        assert "wwDataPrep.issueSummary" not in body

    def test_continue_button_gating_uses_the_effective_summary(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderConversionAction()", "function wwDataPrepConversionErrorMessage(",
        )
        assert "wwDataPrepEffectiveIssueSummary()" in body
        assert "wwDataPrep.issueSummary" not in body

    def test_export_button_gating_uses_the_effective_summary(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderExportAction()", "function wwDataPrepConvert()",
        )
        assert "wwDataPrepEffectiveIssueSummary()" in body
        assert "wwDataPrep.issueSummary" not in body

    def test_effective_summary_synthesizes_a_blocking_unsaved_changes_issue(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepEffectiveIssueSummary()",
            "async function wwDataPrepSetTimeAxis()",
        )
        assert '"time_axis_unsaved_changes"' in body
        assert '"blocking"' in body
        assert "is_ready: false" in body
        assert "blocking_count: base.blocking_count + 1" in body

    def test_only_one_effective_issue_summary_function_exists(self):
        source = _source()
        assert source.count("function wwDataPrepEffectiveIssueSummary()") == 1


class TestLiveDirtyDetectionWiring:
    def test_time_axis_details_has_a_delegated_input_and_change_listener(self):
        source = _source()
        assert (
            'document.getElementById("wwDataPrepTimeAxisDetails").addEventListener("input", wwDataPrepRenderIssues);'
            in source
        )
        assert (
            'document.getElementById("wwDataPrepTimeAxisDetails").addEventListener("change", wwDataPrepRenderIssues);'
            in source
        )
