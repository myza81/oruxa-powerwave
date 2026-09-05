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


class TestDateOrderExcludedWhenNotAmbiguous:
    """UAT finding (Time Setup redesign): an UNAMBIGUOUS absolute_datetime/
    split_date_time detection still resolves a real `date_order`
    server-side (e.g. "ymd" for a clean ISO-8601 source) and echoes it
    back on the applied summary, even though the date-order radio group
    was never shown/checked in the draft -- comparing it unconditionally
    produced a PERMANENT false-positive "unsaved changes" for every
    plain, non-ambiguous absolute/split-date-time save (discovered via
    live browser UAT: Save, then the headline never left "Unsaved Time
    Axis changes"). Only compared when the date-order field is the
    user's own live decision to make (genuinely ambiguous)."""

    def test_date_order_comparability_helper_exists(self):
        source = _source()
        assert "function wwDataPrepTimeAxisDateOrderIsComparable()" in source
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDateOrderIsComparable()",
            "function wwDataPrepTimeAxisDraftIsDirty()",
        )
        assert 'document.getElementById("wwDataPrepTimeAxisDateOrderField").hidden' in body

    def test_dirty_check_normalizes_date_order_when_not_comparable(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDraftIsDirty()",
            "function wwDataPrepEffectiveIssueSummary()",
        )
        assert "wwDataPrepTimeAxisDateOrderIsComparable()" in body
        assert "delete draft.options.date_order;" in body
        assert "delete applied.options.date_order;" in body

    def test_detected_format_is_always_excluded_unconditionally(self):
        # UAT finding: `detected_format` (e.g. "ISO-8601") is a purely
        # backend-computed diagnostic annotation on `resolved_options` --
        # the user never sets it anywhere in the form, so it can NEVER
        # match an equivalent draft value and must be excluded
        # unconditionally (unlike date_order/confirmed, which are only
        # conditionally excluded). Its absence caused every successful
        # Absolute Datetime/Date + Time save to show a permanent false
        # "Unsaved Time Axis changes" (discovered via live browser UAT).
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDraftIsDirty()",
            "function wwDataPrepEffectiveIssueSummary()",
        )
        assert "delete draft.options.detected_format;" in body
        assert "delete applied.options.detected_format;" in body

    def test_dirty_check_deep_clones_before_deleting_fields(self):
        # UAT finding: wwDataPrepTimeAxisConfigBody()'s own `options`
        # field is a DIRECT reference to the source object it was built
        # from (wwDataPrep.timeAxisSummary.options on the applied side)
        # -- deleting a key in place silently corrupted the real stored
        # summary (Advanced details' own "Detected format" row went
        # permanently blank the moment any dirty check ran). Both sides
        # must be deep-cloned before any `delete` below.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisDraftIsDirty()",
            "function wwDataPrepEffectiveIssueSummary()",
        )
        assert "JSON.parse(JSON.stringify(appliedSource))" in body
        assert "JSON.parse(JSON.stringify(wwDataPrepCurrentTimeAxisDraftBody()))" in body


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
        assert "if (!appliedSource) return false;" in body


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
        # Time Setup redesign: the delegated listener now calls a small
        # wrapper (wwDataPrepRefreshTimeAxisLiveState) that refreshes
        # BOTH wwDataPrepRenderIssues() (the global Preparation Status
        # consumers) AND the local Time Setup validity line, rather than
        # wwDataPrepRenderIssues() directly.
        source = _source()
        assert (
            'document.getElementById("wwDataPrepTimeAxisDetails").addEventListener("input", wwDataPrepRefreshTimeAxisLiveState);'
            in source
        )
        assert (
            'document.getElementById("wwDataPrepTimeAxisDetails").addEventListener("change", wwDataPrepRefreshTimeAxisLiveState);'
            in source
        )
        body = _function_body(
            source, "function wwDataPrepRefreshTimeAxisLiveState()", "document.getElementById(\"wwDataPrepTimeAxisDetails\").addEventListener",
        )
        assert "wwDataPrepRenderIssues();" in body
        assert "wwDataPrepRenderTimeAxisValidity();" in body


class TestManualMultiColumnCapabilityPreserved:
    """UAT follow-up: the previous UI allowed Manual to select 2+
    Time-Axis-role columns, and the backend's `_ManualInterpreter.
    accepts()` still intentionally permits any non-empty column count
    (it never parses per-row values, so it imposes no fixed cardinality
    the way every real interpreter does). The Time Setup redesign's
    first pass silently limited Manual to a single-select, removing a
    previously-reachable capability -- restored here as a compact
    checkbox list, scoped to Manual alone, and only once there is a
    genuine multi-column choice to make (2+ eligible columns); one
    eligible column still falls through to the SAME shared resolved-
    value field every other interpreter uses (no checkbox for a choice
    that doesn't exist)."""

    def test_manual_columns_field_exists_and_is_scoped_to_manual(self):
        source = _source()
        assert 'id="wwDataPrepTimeAxisManualColumnsField"' in source
        assert 'id="wwDataPrepTimeAxisManualColumnChecks"' in source
        # Lives inside the Manual fields block, never inside the shared
        # Detect-flow fields real interpreters use.
        body = _function_body(
            source, 'id="wwDataPrepTimeAxisManualFields"', "<!-- Absolute Datetime",
        )
        assert "wwDataPrepTimeAxisManualColumnsField" in body

    def test_manual_checked_columns_helper_exists(self):
        source = _source()
        assert "function wwDataPrepTimeAxisManualCheckedColumns()" in source
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisManualCheckedColumns()",
            "function wwDataPrepTimeAxisColumnIndicesForSubmit()",
        )
        assert ".ww-data-prep-time-axis-manual-col-check:checked" in body

    def test_column_indices_for_submit_uses_manual_checkboxes_only_when_multiple_eligible(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisColumnIndicesForSubmit()",
            "function wwDataPrepRenderTimeAxisSummary()",
        )
        assert 'interpreterId === "manual" && wwDataPrepTimeAxisEligibleColumns().length > 1' in body
        assert "wwDataPrepTimeAxisManualCheckedColumns()" in body
        # The single resolved-value/select path remains the fallback for
        # Manual with exactly one eligible column -- never both compete.
        assert "wwDataPrepTimeAxisSimpleSelectedColumn()" in body

    def test_eligible_columns_render_routes_manual_multi_column_to_the_checkbox_list(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisEligibleColumns()",
            "function wwDataPrepRenderTimeAxisManualColumnChecks(",
        )
        assert 'interpreterId === "manual" && eligible.length > 1' in body
        assert "wwDataPrepRenderTimeAxisManualColumnChecks(eligible);" in body
        # The shared single-column field is explicitly hidden in that
        # branch, and the checkbox field is hidden in every OTHER branch
        # -- never both visible, never neither for a real choice.
        assert "manualColumnsFieldEl.hidden = true;" in body
        assert "manualColumnsFieldEl.hidden = false;" in body

    def test_manual_column_checks_reuses_the_shared_display_label_helper(self):
        # Never a second, divergent "letter + header text" implementation.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisManualColumnChecks(",
            "// Renders a detection-shaped object",
        )
        assert "wwDataPrepTimeAxisColumnDisplayLabel(c)" in body

    def test_column_indices_for_submit_is_still_the_one_function_the_draft_builder_calls(self):
        # DEC-083's own draft-vs-applied comparison must automatically
        # cover Manual's multi-column selection too -- verified here by
        # confirming wwDataPrepCurrentTimeAxisDraftBody() still calls
        # THIS one function for its column_indices, unchanged, rather
        # than a second, parallel column-reading path only some callers
        # know about.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepCurrentTimeAxisDraftBody()",
            "function wwDataPrepAppliedTimeAxisDraftBody()",
        )
        assert "wwDataPrepTimeAxisColumnIndicesForSubmit()" in body
