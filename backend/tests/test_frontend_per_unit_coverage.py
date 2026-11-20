"""Static regression checks verifying that the Per-Unit Settings Hub
coverage section has been retired (PU-UI-001 Slice B).

The Hub (`#perUnitSettingsOverlay`) and its associated coverage section,
state variables, and functions (`wwFetchPerUnitCoverage`,
`wwLoadAndRenderPerUnitCoverage`, `wwPuCoverageRowHtml`) have been
removed from frontend/index.html.  Per-unit configuration is managed
via Recording Details; the backend coverage endpoint
(`GET .../per-unit/sources/{id}/coverage`) remains unaffected.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


class TestHubCoverageSectionIsRemoved:
    """PU-UI-001 Slice B: the Hub surface and its coverage section have
    been retired.  These tests verify the removal is complete."""

    def test_hub_overlay_is_absent(self):
        source = _source()
        assert 'id="perUnitSettingsOverlay"' not in source
        assert 'id="wwPuCoverageSection"' not in source
        assert 'id="wwPuCoverageBody"' not in source

    def test_hub_coverage_functions_are_removed(self):
        source = _source()
        assert 'async function wwFetchPerUnitCoverage(' not in source
        assert 'async function wwLoadAndRenderPerUnitCoverage()' not in source
        assert 'function wwPuCoverageRowHtml(' not in source

    def test_hub_state_variables_are_removed(self):
        source = _source()
        assert 'let wwPuSettingsSourcesList' not in source
        assert 'let wwPuSettingsSelectedSourceId' not in source

    def test_hub_css_classes_are_removed(self):
        source = _source()
        assert '.ww-pu-settings-actions' not in source
        assert '.ww-pu-settings-back-link' not in source

    def test_hub_toolbar_button_is_removed(self):
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' not in source
        assert 'async function wwOpenPerUnitSettingsModal()' not in source


class TestChildModalsSurviveHubRemoval:
    """The two modals that the Hub formerly routed to are still present
    and fully functional -- only the Hub routing layer is gone."""

    def test_source_default_modal_still_present(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' in source
        assert 'async function wwOpenPerUnitProfilesModal(preselectedSourceId)' in source

    def test_measurement_groups_modal_still_present(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' in source
        assert 'async function wwOpenMeasurementGroupsModal()' in source

    def test_recommended_fallback_badges_still_present(self):
        source = _source()
        assert '.ww-mg-badge--recommended' in source
        assert '.ww-mg-badge--fallback' in source

    def test_backend_api_paths_untouched(self):
        source = _source()
        assert '"/per-unit/sources"' in source
        assert '/measurement-groups' in source
