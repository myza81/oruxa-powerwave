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
        assert 'id="wwUnitEngineeringBtn"' in source
        assert 'id="wwUnitPerUnitBtn"' in source

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


class TestBothChildModalsRemainReachable:
    """PU-UI-001 Slice B: both modals remain fully functional, now
    accessed directly (not routed through the removed Hub)."""

    def test_measurement_groups_modal_still_exists(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' in source

    def test_source_default_modal_still_exists(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' in source

    def test_existing_modal_functions_are_unmodified_and_still_present(self):
        source = _source()
        for fn in (
            "async function wwOpenPerUnitProfilesModal(preselectedSourceId)",
            "function wwClosePerUnitProfilesModal()",
            "async function wwOpenMeasurementGroupsModal()",
            "function wwCloseMeasurementGroupsModal()",
        ):
            assert fn in source

    def test_hub_routing_buttons_are_gone(self):
        """Hub routing buttons removed; modals accessed directly via
        Recording Details, not via a toolbar Hub surface."""
        source = _source()
        assert 'id="wwOpenPerUnitProfilesFromSettingsBtn"' not in source
        assert 'id="wwOpenMeasurementGroupsFromSettingsBtn"' not in source
        assert 'id="wwPerUnitProfilesBackToSettingsBtn"' not in source
        assert 'id="wwMeasurementGroupsBackToSettingsBtn"' not in source


class TestSourceDefaultStaleHintFixed:
    """Checklist item 6: the pre-DEC-051 stale hint must be gone."""

    def test_stale_every_eligible_channel_claim_is_gone(self):
        source = _source()
        assert "uses its own configuration" not in source

    def test_source_default_modal_states_its_actual_current_scope(self):
        source = _source()
        body = _function_body(source, 'id="perUnitProfilesOverlay"', 'id="measurementGroupsOverlay"')
        assert "not covered by a Measurement Group" in body


class TestPrecedenceExplanationPresent:
    """Precedence copy is present in both child modals, and never
    implies save-order-based "winning" or a grouped-but-incomplete
    channel falling back.  The Hub surface that previously also carried
    this copy has been retired (PU-UI-001 Slice B)."""

    def test_measurement_groups_modal_states_precedence(self):
        source = _source()
        body = _function_body(source, 'id="measurementGroupsOverlay"', 'id="measurementGroupsSourceSelect"')
        assert "take precedence over Source Default" in body

    def test_source_default_modal_states_group_authority(self):
        source = _source()
        body = _function_body(source, 'id="perUnitProfilesOverlay"', 'id="perUnitSourceSelect"')
        assert "remain authoritative" in body


class TestUnitModeControlsUnchanged:
    """PU-UI-001 Slice B: Engineering Units / Per Unit display-mode
    switching is untouched.  The Hub settings button that previously sat
    adjacent has been removed but the toggle buttons are unaffected."""

    def test_unit_mode_buttons_unchanged(self):
        source = _source()
        assert 'id="wwUnitEngineeringBtn"' in source
        assert 'id="wwUnitPerUnitBtn"' in source

    def test_per_unit_selection_still_calls_apply_unit_mode(self):
        source = _source()
        wiring = _function_body(
            source,
            'document.getElementById("wwUnitPerUnitBtn").addEventListener',
            '// Phase 5C: "Manage Per-Unit Bases" modal wiring',
        )
        assert 'await wwApplyUnitMode("per_unit");' in wiring

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
        wiring = _function_body(
            source,
            'document.getElementById("wwUnitPerUnitBtn").addEventListener',
            '// Phase 5C: "Manage Per-Unit Bases" modal wiring',
        )
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

    def test_existing_api_paths_are_untouched(self):
        source = _source()
        assert '"/per-unit/sources"' in source
        assert "/measurement-groups" in source
