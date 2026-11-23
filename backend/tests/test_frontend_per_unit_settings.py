"""Static regression checks for the Per-Unit Settings area of
frontend/index.html following PU-UI-001 Slice B.

The Per-Unit Settings Hub (`#perUnitSettingsOverlay`,
`#wwOpenPerUnitSettingsBtn`, `wwOpenPerUnitSettingsModal()`) has been
retired.  PU configuration is now managed via Recording Details.  These
tests verify the Hub is fully absent and that all surviving controls
(ENG/PU toggle, Source Default modal, Measurement Groups modal) remain
intact.

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses.
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


class TestUnitModeToolbarAfterHubRemoval:
    """PU-UI-001 Slice B: the Hub (#wwOpenPerUnitSettingsBtn /
    #perUnitSettingsOverlay) has been retired.  The toolbar's unit-mode
    area now contains only the ENG/PU toggle buttons; PU configuration
    is managed via Recording Details."""

    def test_toolbar_has_eng_pu_toggle_only_no_hub_entry(self):
        source = _source()
        # Legacy dropdown and Hub entry point are both gone
        assert 'id="wwUnitModeMenu"' not in source
        assert 'id="wwOpenPerUnitSettingsBtn"' not in source
        # No competing management buttons in the unit-mode area
        assert 'id="wwManageMeasurementGroupsBtn"' not in source
        assert 'id="wwManagePerUnitBasesBtn"' not in source
        # ENG/PU display-mode toggle remains
        assert 'data-pane-unit-mode="engineering"' in source
        assert 'data-pane-unit-mode="per_unit"' in source

    def test_hub_open_and_close_functions_are_removed(self):
        source = _source()
        assert 'async function wwOpenPerUnitSettingsModal()' not in source
        assert 'function wwClosePerUnitSettingsModal()' not in source


class TestHubOverlayIsAbsent:
    """PU-UI-001 Slice B: the Per-Unit Settings Hub overlay is retired.
    Configuration surfaces (MG modal, Source Default modal) are now
    accessed directly via Recording Details."""

    def test_hub_overlay_markup_is_removed(self):
        source = _source()
        assert 'id="perUnitSettingsOverlay"' not in source
        assert 'id="perUnitSettingsTitle"' not in source
        assert 'id="perUnitSettingsSourceSelect"' not in source

    def test_hub_routing_buttons_are_removed(self):
        source = _source()
        assert 'id="wwOpenPerUnitProfilesFromSettingsBtn"' not in source
        assert 'id="wwOpenMeasurementGroupsFromSettingsBtn"' not in source
        assert 'id="wwPerUnitProfilesBackToSettingsBtn"' not in source
        assert 'id="wwMeasurementGroupsBackToSettingsBtn"' not in source

    def test_badges_are_informational_not_warning_styled(self):
        """Owner requirement: Recommended/Fallback must never use
        warning/error styling, and Source Default must not be dimmed as
        deprecated."""
        source = _source()
        assert ".ww-mg-badge--recommended" in source
        assert ".ww-mg-badge--fallback" in source
        recommended_rule = _function_body(source, ".ww-mg-badge--recommended {", "}")
        fallback_rule = _function_body(source, ".ww-mg-badge--fallback {", "}")
        for rule in (recommended_rule, fallback_rule):
            assert "var(--warn)" not in rule


class TestNoLegacyWordingUserFacing:
    """Checklist item 3."""

    def test_no_legacy_wording_remains_anywhere(self):
        source = _source()
        assert "Legacy source-wide base settings" not in source
        assert 'ww-split-menu-item--legacy' not in source


class TestBothChildModalsRemovedInPuUi001:
    """PU-UI-001 Steps B and C: both the SD modal and the MG modal/drawer
    have been removed.  PU configuration is managed exclusively via
    Recording Details."""

    def test_measurement_groups_modal_removed(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' not in source
        assert 'async function wwOpenMeasurementGroupsModal()' not in source
        assert 'function wwCloseMeasurementGroupsModal()' not in source

    def test_source_default_modal_removed(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' not in source
        assert 'async function wwOpenPerUnitProfilesModal(' not in source
        assert 'function wwClosePerUnitProfilesModal()' not in source

    def test_mg_drawer_removed(self):
        source = _source()
        assert 'id="wwMgDrawer"' not in source
        assert 'id="wwMgDrawerBackdrop"' not in source

    def test_rd_navigation_helpers_replace_modal_entry_points(self):
        source = _source()
        assert 'function wwNavigateToRdForPuConfiguration(' in source
        assert 'function wwNavigateToRdForGroup(' in source

    def test_hub_routing_buttons_were_already_gone_still_gone(self):
        source = _source()
        assert 'id="wwOpenPerUnitProfilesFromSettingsBtn"' not in source
        assert 'id="wwOpenMeasurementGroupsFromSettingsBtn"' not in source
        assert 'id="wwPerUnitProfilesBackToSettingsBtn"' not in source
        assert 'id="wwMeasurementGroupsBackToSettingsBtn"' not in source


class TestSourceDefaultStaleHintFixed:
    """Checklist item 6: the pre-DEC-051 stale hint must be gone.
    PU-UI-001 Step B: the SD modal is removed so the second check no
    longer applies -- the stale hint can't reappear in a removed modal."""

    def test_stale_every_eligible_channel_claim_is_gone(self):
        source = _source()
        assert "uses its own configuration" not in source

    def test_sd_modal_is_removed_so_scope_text_is_gone_with_it(self):
        """PU-UI-001 Step B: the entire SD modal is removed; the
        "not covered by a Measurement Group" copy no longer exists."""
        source = _source()
        assert 'id="perUnitProfilesOverlay"' not in source


class TestPrecedenceExplanationAbsenceAfterPuUi001:
    """PU-UI-001 Steps B and C: both child modals are removed.  The
    DEC-051 precedence (group-aware > Source Default) is now described
    exclusively in Recording Details and backend documentation -- it
    no longer needs a user-facing copy in a modal that no longer exists."""

    def test_mg_modal_is_removed_so_precedence_copy_is_gone_with_it(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' not in source

    def test_sd_modal_is_removed_so_authority_copy_is_gone_with_it(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' not in source


class TestUnitModeControlsUnchanged:
    """PU-UI-001 Slice B: Engineering Units / Per Unit display-mode
    switching is untouched.  The Hub settings button that previously sat
    adjacent has been removed but the toggle buttons are unaffected."""

    def test_unit_mode_buttons_unchanged(self):
        source = _source()
        assert 'data-pane-unit-mode="engineering"' in source
        assert 'data-pane-unit-mode="per_unit"' in source

    def test_per_unit_selection_still_calls_apply_unit_mode(self):
        source = _source()
        # Bound directly by the handler's closing }); — exact same pattern
        # as test_frontend_per_unit_mode.py's own version.
        start = source.index('async function wwApplyPaneUnitMode(panel, button)')
        end = source.index("function wwWaveformPaneHeaderHtml", start)
        wiring = source[start:end]
        assert 'wwApplyUnitMode(button.dataset.paneUnitMode)' in wiring

    def test_hub_button_is_absent_no_separate_settings_action(self):
        """PU-UI-001 Slice B: the Hub settings button is gone; clicking
        Per Unit only switches display mode."""
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' not in source
        assert 'async function wwOpenPerUnitSettingsModal()' not in source

    def test_selecting_per_unit_never_opens_any_configuration_surface(self):
        """UAT fix preserved: wwUnitPerUnitBtn's own listener must ONLY
        call wwApplyUnitMode, never open any configuration overlay."""
        source = _source()
        start = source.index('async function wwApplyPaneUnitMode(panel, button)')
        end = source.index("function wwWaveformPaneHeaderHtml", start)
        wiring = source[start:end]
        assert "wwOpenPerUnitProfilesModal" not in wiring
        assert "wwOpenPerUnitSettingsModal" not in wiring
        assert "wwOpenMeasurementGroupsModal" not in wiring


class TestNoBackendOrApiChange:
    """PU-UI-001 Slice B: no backend/API changes.  The Hub's read-only
    GET /coverage fetch is gone with the Hub itself; the DEC-049/050
    API paths used by the two surviving modals are untouched."""

    def test_hub_state_variables_are_removed(self):
        source = _source()
        assert 'let wwPuSettingsSourcesList' not in source
        assert 'let wwPuSettingsSelectedSourceId' not in source

    def test_hub_coverage_functions_are_removed(self):
        source = _source()
        assert 'async function wwFetchPerUnitCoverage(' not in source
        assert 'async function wwLoadAndRenderPerUnitCoverage()' not in source
        assert 'function wwPuCoverageRowHtml(' not in source

    def test_measurement_group_api_path_still_used_by_rd(self):
        """PU-UI-001 Steps B and C: the SD modal's /per-unit/sources calls
        are gone with the modal; the /measurement-groups endpoints are
        still called from Recording Details."""
        source = _source()
        assert '"/per-unit/sources"' not in source
        assert "/measurement-groups" in source
