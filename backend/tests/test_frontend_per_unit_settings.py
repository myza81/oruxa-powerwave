"""Static regression checks for Slice 1 of the Per-Unit Settings
hierarchy (frontend/index.html) -- the new lightweight parent surface
that presents Measurement Groups (DEC-050, "Recommended") and Source
Default (DEC-049's existing source-wide modal, "Fallback") as one
coherent Per-Unit system, per the owner-approved UI formalization of
DEC-051 (see docs/project-memory/DECISIONS.md#dec-051).

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses -- this repo has no
browser/DOM test runner for the single-file frontend. Slice 1 is
deliberately UI-only: no backend/API behaviour changes, so these tests
never touch the backend at all.
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


class TestUnitModeMenuHasOneSettingsEntry:
    """Checklist item 1: the Unit Mode menu must no longer expose two
    directly-competing management options."""

    def test_menu_contains_exactly_one_management_entry(self):
        source = _source()
        menu_body = _function_body(source, 'id="wwUnitModeMenu"', "</div>\n                        </div>")
        assert 'id="wwOpenPerUnitSettingsBtn"' in menu_body
        assert "Per-Unit Settings" in menu_body
        assert 'id="wwManageMeasurementGroupsBtn"' not in menu_body
        assert 'id="wwManagePerUnitBasesBtn"' not in menu_body

    def test_settings_button_opens_the_new_parent_surface(self):
        source = _source()
        wiring = _function_body(source, 'document.getElementById("wwOpenPerUnitSettingsBtn")', "document.addEventListener")
        assert "wwOpenPerUnitSettingsModal()" in wiring


class TestParentSurfaceContent:
    """Checklist item 2: the parent surface's required terminology."""

    def test_parent_surface_markup_exists(self):
        source = _source()
        assert 'id="perUnitSettingsOverlay"' in source
        assert 'id="perUnitSettingsTitle"' in source
        assert "Per-Unit Settings" in source

    def test_parent_surface_contains_required_terminology(self):
        source = _source()
        body = _function_body(source, 'id="perUnitSettingsOverlay"', '<!-- Phase 5C (DEC-049): "Manage Per-Unit Bases"')
        assert "Measurement Groups" in body
        assert "Recommended" in body
        assert "Source Default" in body
        assert "Fallback" in body

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
    """Checklist items 4 and 5: both existing modals stay fully
    functional and reachable, only their entry path changes."""

    def test_measurement_groups_modal_reachable_from_parent(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' in source
        wiring = _function_body(source, 'document.getElementById("wwOpenMeasurementGroupsFromSettingsBtn")', "document.addEventListener")
        assert "wwOpenMeasurementGroupsModal()" in wiring

    def test_source_default_modal_reachable_from_parent(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' in source
        wiring = _function_body(source, 'document.getElementById("wwOpenPerUnitProfilesFromSettingsBtn")', "document.addEventListener")
        assert "wwOpenPerUnitProfilesModal()" in wiring

    def test_existing_modal_functions_are_unmodified_and_still_present(self):
        source = _source()
        for fn in (
            "async function wwOpenPerUnitProfilesModal()",
            "function wwClosePerUnitProfilesModal()",
            "async function wwOpenMeasurementGroupsModal()",
            "function wwCloseMeasurementGroupsModal()",
        ):
            assert fn in source

    def test_each_child_modal_offers_a_way_back_to_the_parent(self):
        source = _source()
        assert 'id="wwPerUnitProfilesBackToSettingsBtn"' in source
        assert 'id="wwMeasurementGroupsBackToSettingsBtn"' in source
        back_wiring_1 = _function_body(source, 'document.getElementById("wwPerUnitProfilesBackToSettingsBtn")', "document.addEventListener")
        assert "wwOpenPerUnitSettingsModal()" in back_wiring_1
        back_wiring_2 = _function_body(source, 'document.getElementById("wwMeasurementGroupsBackToSettingsBtn")', "document.addEventListener")
        assert "wwOpenPerUnitSettingsModal()" in back_wiring_2


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
    """Checklist item 7: precedence copy is present in the parent surface
    AND in both child modals, and never implies save-order-based
    "winning" or a grouped-but-incomplete channel falling back."""

    def test_parent_surface_states_the_precedence_rule(self):
        source = _source()
        body = _function_body(source, 'id="perUnitSettingsOverlay"', '<!-- Phase 5C (DEC-049): "Manage Per-Unit Bases"')
        assert "used where available" in body
        assert "outside" in body

    def test_measurement_groups_modal_states_precedence(self):
        source = _source()
        body = _function_body(source, 'id="measurementGroupsOverlay"', 'id="measurementGroupsSourceSelect"')
        assert "take precedence over Source Default" in body

    def test_source_default_modal_states_group_authority(self):
        source = _source()
        body = _function_body(source, 'id="perUnitProfilesOverlay"', 'id="perUnitSourceSelect"')
        assert "remain authoritative" in body


class TestUnitModeControlsUnchanged:
    """Checklist item 8: Engineering Units / Per Unit display-mode
    switching is untouched by this slice."""

    def test_unit_mode_radio_items_unchanged(self):
        source = _source()
        assert 'data-unit-mode="engineering"' in source
        assert 'data-unit-mode="per_unit"' in source

    def test_per_unit_selection_still_calls_apply_unit_mode(self):
        source = _source()
        wiring = _function_body(
            source,
            'document.querySelector(\'#wwUnitModeMenu .ww-split-menu-item[data-unit-mode="per_unit"]\')',
            'document.getElementById("wwOpenPerUnitSettingsBtn")',
        )
        assert 'await wwApplyUnitMode("per_unit");' in wiring

    def test_opening_settings_is_a_separate_action_from_activating_per_unit(self):
        source = _source()
        settings_wiring = _function_body(source, 'document.getElementById("wwOpenPerUnitSettingsBtn")', "document.addEventListener")
        assert "wwApplyUnitMode" not in settings_wiring

    def test_selecting_per_unit_never_opens_any_configuration_surface(self):
        """UAT fix: clicking "Per Unit" must ONLY switch display mode --
        it must never open Source Default, Measurement Groups, or the
        new Per-Unit Settings parent surface as a side effect. Opening a
        configuration surface is always a separate, explicit action via
        "Per-Unit Settings..."."""
        source = _source()
        wiring = _function_body(
            source,
            'document.querySelector(\'#wwUnitModeMenu .ww-split-menu-item[data-unit-mode="per_unit"]\')',
            'document.getElementById("wwOpenPerUnitSettingsBtn")',
        )
        assert "wwOpenPerUnitProfilesModal" not in wiring
        assert "wwOpenPerUnitSettingsModal" not in wiring
        assert "wwOpenMeasurementGroupsModal" not in wiring


class TestNoBackendOrApiChange:
    """Checklist item 9: Slice 1 is UI-only -- no new fetch/mutating
    request anywhere in the new code, and the existing DEC-049/DEC-050
    API paths are untouched."""

    def test_new_functions_never_fetch(self):
        source = _source()
        body = _function_body(source, "function wwOpenPerUnitSettingsModal()", "function wwClosePerUnitSettingsModal()")
        assert "fetch(" not in body
        body2 = _function_body(source, "function wwClosePerUnitSettingsModal()", "// ------")
        assert "fetch(" not in body2

    def test_existing_api_paths_are_untouched(self):
        source = _source()
        assert '"/per-unit/sources"' in source
        assert "/measurement-groups" in source
