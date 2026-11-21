"""Static regression tests for PU-UI-001 Correction — Automatic Acceptance
of Reliably Detected Measurement Groups in Recording Details (DEC-214).

Covers scenarios 1, 2, 15 of the owner-approved correction spec:
  1. Reliable automatic Voltage Group detected — no Suggested badge.
  2. Reliable automatic Current Group detected — no Suggested badge.
 15. No permanent Suggest Groups control or routine Suggested badges appear
     in Recording Details.

Also verifies that contextual warnings for genuine problems remain intact:
  - needs_review badge still present (contradictory evidence must stay blocked).
  - manual badge still present (user-created groups are distinct from auto-detected).

Backend domain-level tests for scenarios 3-14 live in
test_automatic_group_acceptance.py.
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


class TestNoSuggestedBadgeInRecordingDetails:
    """Scenarios 1 and 2: reliably auto-detected groups (STATUS_SUGGESTED)
    appear as ordinary groups — no Suggested badge, no approval indicator."""

    def test_suggested_status_produces_no_badge_label(self):
        """The 'Suggested' string no longer maps to a badge in wwRdRenderGroups().
        A Voltage or Current group that arrives as suggested is rendered
        identically to a confirmed group: name + kind badge only."""
        source = _source()
        render_body = _function_body(
            source,
            "function wwRdRenderGroups()",
            "function wwRdRenderDetails()",
        )
        # The old conditional that produced a 'Suggested' label must be gone.
        assert '"Suggested"' not in render_body
        assert "'Suggested'" not in render_body

    def test_suggested_status_string_never_reaches_badge_html(self):
        """ww-rd-group-status--suggested CSS modifier is not emitted for any
        group, because the status label for 'suggested' was removed."""
        source = _source()
        render_body = _function_body(
            source,
            "function wwRdRenderGroups()",
            "function wwRdRenderDetails()",
        )
        assert "ww-rd-group-status--suggested" not in render_body

    def test_suggested_css_modifier_removed_from_stylesheet(self):
        """The .ww-rd-group-status--suggested CSS rule is removed — it is
        no longer needed and must not accumulate as dead code."""
        source = _source()
        # The rule was formerly combined with --needs-review; it must now
        # be absent entirely while --needs-review is kept.
        assert ".ww-rd-group-status--suggested" not in source

    def test_no_suggested_badge_applies_to_both_voltage_and_current_groups(self):
        """The status-badge switch has no Voltage/Current branch for 'suggested'
        — the same code path removes it for both kinds, since the removal is
        unconditional on group kind."""
        source = _source()
        render_body = _function_body(
            source,
            "function wwRdRenderGroups()",
            "function wwRdRenderDetails()",
        )
        # The only condition that triggers a badge is needs_review or manual.
        assert 'g.status === "needs_review"' in render_body
        assert 'g.status === "manual"' in render_body
        assert 'g.status === "suggested"' not in render_body


class TestNeedsReviewAndManualBadgesPreserved:
    """Genuine problem indicators must survive the removal of routine
    Suggested badges — removing unnecessary UI must not weaken safety."""

    def test_needs_review_badge_still_rendered(self):
        """needs_review groups have contradictory automatic evidence.
        Their warning badge is a contextual signal, not a routine indicator."""
        source = _source()
        render_body = _function_body(
            source,
            "function wwRdRenderGroups()",
            "function wwRdRenderDetails()",
        )
        assert '"Review"' in render_body
        assert 'g.status === "needs_review"' in render_body
        # The CSS modifier is built dynamically via g.status.replace("_","-");
        # the template string prefix confirms the pattern is wired.
        assert 'ww-rd-group-status ww-rd-group-status--' in render_body

    def test_manual_badge_still_rendered(self):
        """manual groups were explicitly created by an engineer, not by
        automatic detection. Their distinct badge identifies the origin."""
        source = _source()
        render_body = _function_body(
            source,
            "function wwRdRenderGroups()",
            "function wwRdRenderDetails()",
        )
        assert '"Manual"' in render_body
        assert 'g.status === "manual"' in render_body
        # CSS modifier is built dynamically via g.status.replace("_","-");
        # the template string prefix confirms the pattern is wired.
        assert 'ww-rd-group-status ww-rd-group-status--' in render_body

    def test_needs_review_css_rule_still_present(self):
        source = _source()
        assert ".ww-rd-group-status--needs-review" in source

    def test_manual_css_rule_still_present(self):
        source = _source()
        assert ".ww-rd-group-status--manual" in source


class TestNoSuggestGroupsControlInRecordingDetails:
    """Scenario 15: no permanent Suggest Groups control or routine Suggested
    badges appear in Recording Details.

    Group detection already runs automatically on import via
    workspace_preparation_service.prepare_workspace_source() (DEC-104).
    A permanent 'Suggest Groups' button implies that detection requires
    a user action — the opposite of the owner-approved behavior."""

    def test_suggest_groups_button_absent_from_rd_panel(self):
        """wwRdSuggestGroupsBtn is removed from the Recording Details groups
        panel header — detection is automatic, not user-triggered."""
        source = _source()
        assert 'id="wwRdSuggestGroupsBtn"' not in source

    def test_suggest_groups_function_absent_from_rd(self):
        """wwRdSuggestGroups() is removed — it was the click handler for
        the removed button; keeping an orphaned function would be dead code."""
        source = _source()
        assert "wwRdSuggestGroups()" not in source
        assert "async function wwRdSuggestGroups()" not in source

    def test_suggest_btn_css_absent(self):
        """The .ww-rd-suggest-btn CSS rule is removed alongside the button
        element it styled."""
        source = _source()
        assert ".ww-rd-suggest-btn" not in source

    def test_pu_config_banner_exists_for_compliance_access(self):
        """The Waveform PU config banner button ('Configure in Recording Details')
        is the legitimate compliance-side access point for PU base configuration,
        replacing the former MG modal's suggest button."""
        source = _source()
        assert 'id="wwPuConfigBannerBtn"' in source
        assert "wwNavigateToRdForPuConfiguration" in source

    def test_navigate_to_rd_for_pu_configuration_routes_to_recording_details_groups(self):
        """wwNavigateToRdForPuConfiguration() is the navigation function that
        routes compliance-side PU configuration access to Recording Details
        with the groups panel pre-selected — it replaces wwSuggestMeasurementGroups()."""
        source = _source()
        body = _function_body(
            source,
            "function wwNavigateToRdForPuConfiguration(sourceId)",
            "function wwNavigateToRdForGroup(sourceId, groupId)",
        )
        assert 'shellSetCurrentPage("recording-details")' in body
        assert '"groups"' in body
